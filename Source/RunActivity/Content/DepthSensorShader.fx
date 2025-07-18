// COPYRIGHT 2009, 2010, 2011, 2012, 2013 by the Open Rails project.
// 
// This file is part of Open Rails.
// 
// Open Rails is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
// 
// Open Rails is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
// 
// You should have received a copy of the GNU General Public License
// along with Open Rails.  If not, see <http://www.gnu.org/licenses/>.

// This file is the responsibility of the 3D & Environment Team. 

////////////////////////////////////////////////////////////////////////////////
//                 S C E N E R Y   O B J E C T   S H A D E R                  //
////////////////////////////////////////////////////////////////////////////////

////////////////////    G L O B A L   V A L U E S    ///////////////////////////

float4x4 World;         // model -> world
float4x4 View;          // world -> view
float4x4 Projection;    // view -> projection

float3   ViewerPos;     // Viewer's world coordinates.
float    ImageTextureIsNight;
float4   EyeVector;
float3   SideVector;
float    ReferenceAlpha;
texture  ImageTexture;

float    ObjectClassifier;
float    MaxDistance;
float    BaseIntensity;
bool     TrackClipping;

float4   ZBias_Lighting;  // x = z-bias, y = diffuse, z = specular, w = step(1, z)


sampler Image = sampler_state
{
	Texture = (ImageTexture);
	MagFilter = Linear;
	MinFilter = Anisotropic;
	MipFilter = Linear;
	MaxAnisotropy = 16;
};

sampler Overlay = sampler_state
{
	Texture = (OverlayTexture);
	MagFilter = Linear;
	MinFilter = Linear;
	MipFilter = Linear;
	MipLodBias = 0;
	AddressU = Wrap;
	AddressV = Wrap;
};


////////////////////    V E R T E X   I N P U T S    ///////////////////////////

struct VERTEX_INPUT
{
	float4 Position  : POSITION;
	float2 TexCoords : TEXCOORD0;
	float3 Normal    : NORMAL;
	float4x4 Instance : TEXCOORD1;
};

struct VERTEX_INPUT_FOREST
{
	float4 Position  : POSITION;
	float2 TexCoords : TEXCOORD0;
	float3 Normal    : NORMAL;
};

struct VERTEX_INPUT_SIGNAL
{
	float4 Position  : POSITION;
	float2 TexCoords : TEXCOORD0;
	float4 Color     : COLOR0;
};

struct VERTEX_INPUT_TRANSFER
{
	float4 Position  : POSITION;
	float2 TexCoords : TEXCOORD0;
};

////////////////////    V E R T E X   O U T P U T S    /////////////////////////

struct VERTEX_OUTPUT
{
	float4 Position     : POSITION;  // position x, y, z, w
	float4 RelPosition  : TEXCOORD0; // rel position x, y, z; position z
	float2 TexCoords    : TEXCOORD1; // tex coords x, y
	float4 Color        : COLOR0;    // color r, g, b, a
	float3 Normal       : TEXCOORD2;  //
};

////////////////////    V E R T E X   S H A D E R S    /////////////////////////

void _VSNormalProjection(in VERTEX_INPUT In, inout VERTEX_OUTPUT Out)
{
	// Project position, normal and copy texture coords
	Out.Position = mul(mul(mul(In.Position, World), View), Projection);
	Out.RelPosition = mul(mul(In.Position, World), View);
	Out.Normal = mul(mul(In.Normal, World), View);
    Out.TexCoords.xy = In.TexCoords;

}

void _VSSignalProjection(uniform bool Glow, in VERTEX_INPUT_SIGNAL In, inout VERTEX_OUTPUT Out)
{
	// Project position, normal and copy texture coords
	float3 relPos = mul(In.Position, World).xyz - ViewerPos;
	// Position 1.5cm in front of signal.
	In.Position.z += 0.015;
	Out.Position = mul(mul(mul(In.Position, World), View), Projection);
	Out.RelPosition = mul(mul(In.Position, World), View);
    
}

void _VSTransferProjection(in VERTEX_INPUT_TRANSFER In, inout VERTEX_OUTPUT Out)
{
	// Project position, normal and copy texture coords
	Out.Position = mul(mul(mul(In.Position, World), View), Projection);
	Out.RelPosition = mul(mul(In.Position, World), View);
	Out.TexCoords.xy = In.TexCoords;
}


VERTEX_OUTPUT VSGeneral(uniform bool ShaderModel3, in VERTEX_INPUT In)
{
	VERTEX_OUTPUT Out = (VERTEX_OUTPUT)0;
	
	if (ShaderModel3) {
		if (determinant(In.Instance) != 0) {
			In.Position = mul(In.Position, transpose(In.Instance));
			In.Normal = mul(In.Normal, (float3x3)transpose(In.Instance));
		}
	}

	_VSNormalProjection(In, Out);

	// Z-bias to reduce and eliminate z-fighting on track ballast. ZBias is 0 or 1.
	Out.Position.z -= ZBias_Lighting.x * saturate(In.TexCoords.x) / 1000;
	
	return Out;
}

VERTEX_OUTPUT VSGeneral9_3(in VERTEX_INPUT In)
{
    return VSGeneral(true, In);
}

VERTEX_OUTPUT VSGeneral9_1(in VERTEX_INPUT In)
{
    return VSGeneral(false, In);
}

VERTEX_OUTPUT VSTransfer(uniform bool ShaderModel3, in VERTEX_INPUT_TRANSFER In)
{
	VERTEX_OUTPUT Out = (VERTEX_OUTPUT)0;
	_VSTransferProjection(In, Out);
	
	// Z-bias to reduce and eliminate z-fighting on track ballast. ZBias is 0 or 1.
	Out.Position.z -= ZBias_Lighting.x * saturate(In.TexCoords.x) / 1000;

	return Out;
}

VERTEX_OUTPUT VSTransfer3(in VERTEX_INPUT_TRANSFER In)
{
    return VSTransfer(true, In);
}

VERTEX_OUTPUT VSTransfer9_1(in VERTEX_INPUT_TRANSFER In)
{
    return VSTransfer(false, In);
}

VERTEX_OUTPUT VSTerrain(uniform bool ShaderModel3, in VERTEX_INPUT In)
{
	VERTEX_OUTPUT Out = (VERTEX_OUTPUT)0;
	_VSNormalProjection(In, Out);
	return Out;
}

VERTEX_OUTPUT VSTerrain9_3(in VERTEX_INPUT In)
{
    return VSTerrain(true, In);
}

VERTEX_OUTPUT VSTerrain9_1(in VERTEX_INPUT In)
{
    return VSTerrain(false, In);
}

VERTEX_OUTPUT VSForest(in VERTEX_INPUT_FOREST In)
{
	VERTEX_OUTPUT Out = (VERTEX_OUTPUT)0;

	// Start with the three vectors of the view.
	float3 upVector = float3(0, -1, 0); // This constant is also defined in Shareds.cs

	// Move the vertex left/right/up/down based on the normal values (tree size).
	float3 newPosition = In.Position.xyz;
	newPosition += (In.TexCoords.x - 0.5f) * SideVector * In.Normal.x;
	newPosition += (In.TexCoords.y - 1.0f) * upVector * In.Normal.y;
	In.Position = float4(newPosition, 1);

	// Project vertex with fixed w=1 and normal=eye.
	Out.Position = mul(mul(mul(In.Position, World), View), Projection);
	Out.RelPosition = mul(mul(In.Position, World), View);
    Out.TexCoords.xy = In.TexCoords;
	
	
	return Out;
}

VERTEX_OUTPUT VSSignalLight(in VERTEX_INPUT_SIGNAL In)
{
	VERTEX_OUTPUT Out = (VERTEX_OUTPUT)0;
	_VSSignalProjection(false, In, Out);
	return Out;
}

VERTEX_OUTPUT VSSignalLightGlow(in VERTEX_INPUT_SIGNAL In)
{
	VERTEX_OUTPUT Out = (VERTEX_OUTPUT)0;
	_VSSignalProjection(true, In, Out);
	return Out;
}

////////////////////    P I X E L   S H A D E R S    ///////////////////////////

// Depth sensor emulation

// debugging output. For debugging, we produce visual output that uses a color gradient to visualize depth sensor features
#define DEBUG 0 // no debug mode
// #define DEBUG 1 // visualize depth info
// #define DEBUG 2 // visualize object classification
 
float4 PSDepthSensor(in VERTEX_OUTPUT In) : COLOR0
{
    float3 Ray = In.RelPosition.xyz;
    float Dist = length(Ray);
    clip(MaxDistance - Dist);
	Dist = Dist / MaxDistance;
	float Intensity = BaseIntensity;
	if (any(In.Normal) && any(Ray))
	    Intensity = abs(Intensity * mul(In.Normal, Ray) * rsqrt(mul(In.Normal, In.Normal) * mul(Ray, Ray)));
	
	#if DEBUG != 0 
	    #if DEBUG == 1
		    float Value = Dist;
		#elif DEBUG == 2
		    float Value = ObjectClassifier;
		#endif
	    float3 Color = { 
			1 - smoothstep(0.167, 0.333, Value) + smoothstep(0.667, 0.833, Value), 
			smoothstep(0.0, 0.167, Value) - smoothstep(0.5, 0.667, Value),
			smoothstep(0.333, 0.5, Value) - smoothstep(0.833, 1.0, Value)};
		return float4(Color * (0.5 + 0.5 * Intensity), 1.0);
	#else
		return float4(ObjectClassifier, Dist, Intensity, 1.0);
	#endif
}


float4 PSDepthSensorWithClip(uniform bool ShaderModel3, uniform bool ClampTexCoords, in VERTEX_OUTPUT In) : COLOR0
{
	float4 Color = tex2D(Image, In.TexCoords.xy);
	if (ShaderModel3 && ClampTexCoords) {
		// We need to clamp the rendering to within the [0..1] range only.
		if (saturate(In.TexCoords.x) != In.TexCoords.x || saturate(In.TexCoords.y) != In.TexCoords.y) {
			Color.a = 0;
		}
	}
    // Alpha testing:
    clip(TrackClipping ? -1 : Color.a - ReferenceAlpha);

	return PSDepthSensor(In);
}

float4 PSImage9_3(in VERTEX_OUTPUT In) : COLOR0
{
    return PSDepthSensorWithClip(true, false, In);
}

float4 PSImage9_3Clamp(in VERTEX_OUTPUT In) : COLOR0
{
    return PSDepthSensorWithClip(true, true, In);
}

float4 PSImage9_1(in VERTEX_OUTPUT In) : COLOR0
{
    return PSDepthSensorWithClip(false, false, In);
}

float4 PSVegetation(in VERTEX_OUTPUT In) : COLOR0
{
	return PSDepthSensorWithClip(false, false, In);
}

float4 PSTerrain(in VERTEX_OUTPUT In) : COLOR0
{
	return PSDepthSensor(In); 
}

float4 PSDarkShade(in VERTEX_OUTPUT In) : COLOR0
{
	return PSDepthSensorWithClip(false, false, In);
}

float4 PSHalfBright(in VERTEX_OUTPUT In) : COLOR0
{
	return PSDepthSensorWithClip(false, false, In);
}

float4 PSFullBright(in VERTEX_OUTPUT In) : COLOR0
{
	return PSDepthSensorWithClip(false, false, In);
}

float4 PSSignalLight(in VERTEX_OUTPUT In) : COLOR0
{
	clip(-1.0);
	return PSDepthSensor(In);
}




////////////////////    T E C H N I Q U E S    /////////////////////////////////

////////////////////////////////////////////////////////////////////////////////
// IMPORTANT: ATI graphics cards/drivers do NOT like mixing shader model      //
//            versions within a technique/pass. Always use the same vertex    //
//            and pixel shader versions within each technique/pass.           //
////////////////////////////////////////////////////////////////////////////////

technique ImageLevel9_1 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSGeneral9_1();
		PixelShader = compile ps_4_0_level_9_1 PSImage9_1();
	}
}

technique ImageLevel9_3 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_3 VSGeneral9_3();
		PixelShader = compile ps_4_0_level_9_3 PSImage9_3();
	}
}

technique TransferLevel9_1 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSTransfer9_1();
		PixelShader = compile ps_4_0_level_9_1 PSImage9_1();
	}
}

technique TransferLevel9_3 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_3 VSTransfer3();
		PixelShader = compile ps_4_0_level_9_3 PSImage9_3Clamp();
	}
}

technique Forest {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSForest();
		PixelShader = compile ps_4_0_level_9_1 PSVegetation();
	}
}

technique VegetationLevel9_1 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSGeneral9_1();
		PixelShader = compile ps_4_0_level_9_1 PSVegetation();
	}
}

technique VegetationLevel9_3 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_3 VSGeneral9_3();
		PixelShader = compile ps_4_0_level_9_3 PSVegetation();
	}
}

technique TerrainLevel9_1 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSTerrain9_1();
		PixelShader = compile ps_4_0_level_9_1 PSTerrain();
	}
}

technique TerrainLevel9_3 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_3 VSTerrain9_3();
		PixelShader = compile ps_4_0_level_9_3 PSTerrain();
	}
}

technique DarkShadeLevel9_1 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSGeneral9_1();
		PixelShader = compile ps_4_0_level_9_1 PSDarkShade();
	}
}

technique DarkShadeLevel9_3 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_3 VSGeneral9_3();
		PixelShader = compile ps_4_0_level_9_3 PSDarkShade();
	}
}

technique HalfBrightLevel9_1 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSGeneral9_1();
		PixelShader = compile ps_4_0_level_9_1 PSHalfBright();
	}
}

technique HalfBrightLevel9_3 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_3 VSGeneral9_3();
		PixelShader = compile ps_4_0_level_9_3 PSHalfBright();
	}
}

technique FullBrightLevel9_1 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSGeneral9_1();
		PixelShader = compile ps_4_0_level_9_1 PSFullBright();
	}
}

technique FullBrightLevel9_3 {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_3 VSGeneral9_3();
		PixelShader = compile ps_4_0_level_9_3 PSFullBright();
	}
}

technique SignalLight {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSSignalLight();
		PixelShader = compile ps_4_0_level_9_1 PSSignalLight();
	}
}

technique SignalLightGlow {
	pass Pass_0 {
		VertexShader = compile vs_4_0_level_9_1 VSSignalLightGlow();
		PixelShader = compile ps_4_0_level_9_1 PSSignalLight();
	}
}
