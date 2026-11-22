# Lab: Passing Nested Structs and Verifying Size and Offsets Between Java and C

## 1. Objectives and Expected Outcomes

This lab builds a **Java 17+ program calling C via JNI** to exchange data of a **nested struct**. Java and C must agree on **object size**, **alignment**, **field offsets**, **byte order**, and **memory region lifecycle**. The program must **compare the layout independently calculated by Java against the actual layout reported by the C compiler** before reading or writing data.

Upon completion, you will be able to do the following:

1. Declare two C types, **Point** and **Packet**, where **Packet directly contains Point** (not a pointer to Point).
2. Use **sizeof**, **_Alignof**, and **offsetof** in C11 to measure the actual layout after the compiler applies padding.
3. Calculate the layout on the Java side yourself according to the chosen ABI rules, then compare every important field with the result from C; **do not treat the metadata returned by C as proof that Java designed the layout correctly on its own**.
4. Use **ByteBuffer.allocateDirect** and **ByteOrder.nativeOrder()** to pass a byte region meaningfully as a Packet between Java and JNI.
5. Have C read the Packet, modify the nested fields, and write the result back to the same memory region; Java verifies the values after the round-trip.
6. Intentionally create a mismatch and verify that the program **detects the error before transferring data using the wrong layout**.
7. Explain portability limits, padding, C structs containing pointers, ownership, and situations where interpreting raw bytes as a struct should not be used.

**Primary runnable scope:** Linux **x86-64**, GCC supporting C11, OpenJDK/JDK 17 or newer. The example was tested with GCC and OpenJDK on Linux x86-64. On other ABIs (32-bit, different packing, different double alignment, or different architectures), results **may differ**: the lab will fail fast at the verification step rather than silently using wrong offsets. The FFM extension at the end requires **JDK 22+**, because FFM was standardized in Java 22.

## 2. Scenario: Java Sends a Packet Containing a Point to C

Suppose a library processes coordinate data in C. Each record has a message kind (**kind**), a two-dimensional position (**point.x, point.y**), a weight (**weight**), and a processing count (**count**).

C11 definition:

~~~c
#include <stdint.h>

typedef struct {
    int32_t x;
    int32_t y;
} Point;

typedef struct {
    uint8_t kind;
    Point point;
    double weight;
    int32_t count;
} Packet;
~~~

**Point is an embedded field inside Packet**, so Point's memory lies directly inside Packet's memory region. This differs from **Point *point**: if it were a pointer, the struct would only contain an address, while the Point object would reside elsewhere and require separate allocation/lifetime management.

C uses types like **int32_t** and **uint8_t** to express intent about bit width. However, **data width does not fully determine layout**: the compiler must also obey type and ABI alignment. **double** in this lab uses an environment where it is 8 bytes in size and has a representation compatible with Java double.

You should not model Packet as a byte sequence of **1 + 8 + 8 + 4 = 21 bytes** and assume **sizeof(Packet) == 21**. The compiler may insert padding between fields and at the end of the struct so that every element in an array of structs satisfies alignment.

## 3. Calculating the Predicted Layout on Linux x86-64

In this lab, assume the ABI has the following properties:

| C Type | Size | Alignment |
| --- | ---: | ---: |
| **uint8_t** | 1 | 1 |
| **int32_t** | 4 | 4 |
| **double** | 8 | 8 |
| **Point** | 8 | 4 |
| **Packet** | 32 | 8 |

Basic rule: the position of each member must be rounded up to a multiple of that member's alignment. For a positive **alignment** that is a power of two, the general formula is:

~~~text
alignUp(offset, alignment) =
    ((offset + alignment - 1) / alignment) * alignment
~~~

This is integer arithmetic, assuming no overflow. **sizeof(struct)** is also rounded up to a multiple of the entire struct's alignment so that subsequent elements in an array have the same alignment constraints.

### 3.1. Point

- **x**: offset 0, length 4 bytes.
- **y**: offset 4, length 4 bytes.
- Data ends at byte 8; **alignof(Point) = 4**, so **sizeof(Point) = 8**.

### 3.2. Packet

- **kind**: offset 0, length 1 byte.
- 3 bytes of padding at offsets 1–3 so that **point** starts at a multiple of 4.
- **point**: offset 4, length 8 bytes; **point.x** is at total offset 4 and **point.y** is at total offset 8.
- 4 bytes of padding at offsets 12–15 so that **weight** starts at a multiple of 8.
- **weight**: offset 16, length 8 bytes.
- **count**: offset 24, length 4 bytes.
- 4 bytes of tail padding at offsets 28–31 so that the stride of a **Packet[]** array is 32 bytes.
- **alignof(Packet) = 8** and **sizeof(Packet) = 32**.

Byte diagram of a Packet with GCC on Linux x86-64:

~~~text
Offset    0     1..3      4..7      8..11    12..15    16..23      24..27    28..31
         +-----+---------+---------+--------+---------+-----------+---------+--------+
Packet:  |kind | padding | point.x |point.y | padding |  weight   |  count  |padding |
         +-----+---------+---------+--------+---------+-----------+---------+--------+
          1 B     3 B       4 B      4 B       4 B        8 B         4 B      4 B
         <------------------------------ sizeof(Packet) = 32 ------------------------>
                       <---- sizeof(Point) = 8 ---->
~~~

This diagram is the **Java-side hypothesis** for the lab ABI. It must be verified using **sizeof/offsetof from the compiler building the C library**, because packing configuration, compiler version, target ABI, or actual C declarations can change the result.

## 4. Data Transfer Strategy and Why Direct ByteBuffer Is Used

There are several ways to pass a struct across the Java/native boundary:

| Approach | Mechanism | When Appropriate |
| --- | --- | --- |
| Separate primitive parameters | Java passes **x, y, weight, count** as JNI arguments | Few fields, want to avoid sharing raw memory layout |
| Formatted serialization | Java writes into **byte[]**/ByteBuffer using a custom protocol | File/network storage, cross-ABI portability required |
| **Direct ByteBuffer** | Java places values at ABI offsets; C gets backing address via JNI | Need to practice memory layout and synchronous native access |
| FFM **MemorySegment + structLayout** | Java describes C layout using standard JDK 22+ API | Want to manage native memory and access fields with explicit layout |
| JNI mapping each Java object to a C struct | C reads Java fields, constructs an internal C struct | Don't want Java to depend on raw C ABI, accept mapping cost |

This lab uses **direct ByteBuffer** because Java can manipulate bytes at absolute offsets, while JNI **GetDirectBufferAddress** retrieves the backing memory address. The buffer is kept alive throughout the **synchronous native call**; C does not retain the pointer after returning.

**Direct ByteBuffer does not automatically create a C struct.** By itself, it is just a region of bytes. Correctness depends on agreement on field order, sizes, padding, byte order, and ownership. Java will verify the layout **before** writing the Packet.

## 5. Lab Project Structure

Create a separate directory with two source files:

~~~text
nested-struct-lab/
  PacketInterop.java
  packet_interop.c
~~~

After running **javac -h .**, the directory will also contain **PacketInterop.h** generated by Java. After the GCC step, there will be **libpacketinterop.so**; Java will load the library using **System.loadLibrary("packetinterop")**. Do not hand-write the JNI header if it can be generated from the exact class being used, because generating the header reduces mistakes in JNI symbol names and parameter signatures.

**Environment requirements:** JDK 17+ (both javac and java), GCC supporting C11, Linux x86-64 target, **JAVA_HOME** variable pointing to the **JDK root directory** containing **include/jni.h**. Both Java and C programs must be built for the same target architecture; a 64-bit JVM cannot load a 32-bit shared library.

## 6. Java 17+ Code: Self-Calculating Offsets and Checking C Metadata

Create **PacketInterop.java** with the **entire content** below. The program does not read C metadata and blindly accept it. It calculates offsets based on the expected ABI first, then asks the C compiler to confirm the entire metadata array. If there is a mismatch, it throws **IllegalStateException** and **does not call nativeTransform**.

~~~java
// PacketInterop.java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;

public final class PacketInterop {
    private static final int P_SIZE = 0, P_ALIGN = 1, P_X = 2, P_Y = 3;
    private static final int E_SIZE = 4, E_ALIGN = 5, E_KIND = 6;
    private static final int E_POINT = 7, E_X = 8, E_Y = 9;
    private static final int E_WEIGHT = 10, E_COUNT = 11;

    static { System.loadLibrary("packetinterop"); }

    private static native int[] nativeLayout();
    private static native int nativeTransform(ByteBuffer packet);

    private static int alignUp(int value, int alignment) {
        return ((value + alignment - 1) / alignment) * alignment;
    }

    private static int[] expectedLinuxX64Layout() {
        // C ABI for this lab: int32_t align 4, double align 8.
        int x = 0;
        int y = alignUp(x + 4, 4);
        int pointSize = alignUp(y + 4, 4);
        int kind = 0;
        int point = alignUp(kind + 1, 4);
        int weight = alignUp(point + pointSize, 8);
        int count = alignUp(weight + 8, 4);
        int packetSize = alignUp(count + 4, 8);
        return new int[] {
                pointSize, 4, x, y,
                packetSize, 8, kind, point,
                point + x, point + y, weight, count
        };
    }

    private static String fields(ByteBuffer b, int[] l) {
        return "kind=" + Byte.toUnsignedInt(b.get(l[E_KIND]))
                + " x=" + b.getInt(l[E_X])
                + " y=" + b.getInt(l[E_Y])
                + " weight=" + b.getDouble(l[E_WEIGHT])
                + " count=" + b.getInt(l[E_COUNT]);
    }

    public static void main(String[] args) {
        int[] expected = expectedLinuxX64Layout();
        int[] actual = nativeLayout();
        if (!Arrays.equals(expected, actual)) {
            throw new IllegalStateException(
                    "ABI mismatch: expected=" + Arrays.toString(expected)
                            + ", actual=" + Arrays.toString(actual));
        }
        System.out.println("ABI layout match: true");
        System.out.println("Point: size=" + actual[P_SIZE]
                + " align=" + actual[P_ALIGN]
                + " x=" + actual[P_X] + " y=" + actual[P_Y]);
        System.out.println("Packet: size=" + actual[E_SIZE]
                + " align=" + actual[E_ALIGN]
                + " kind=" + actual[E_KIND]
                + " point=" + actual[E_POINT]
                + " point.x=" + actual[E_X]
                + " point.y=" + actual[E_Y]
                + " weight=" + actual[E_WEIGHT]
                + " count=" + actual[E_COUNT]);

        ByteBuffer packet = ByteBuffer.allocateDirect(expected[E_SIZE])
                .order(ByteOrder.nativeOrder());
        packet.put(expected[E_KIND], (byte) 7);
        packet.putInt(expected[E_X], 10);
        packet.putInt(expected[E_Y], -3);
        packet.putDouble(expected[E_WEIGHT], 2.5);
        packet.putInt(expected[E_COUNT], 4);

        System.out.println("Before: " + fields(packet, expected));
        int checksum = nativeTransform(packet);
        System.out.println("After:  " + fields(packet, expected));
        System.out.println("Native checksum=" + checksum);
    }
}
~~~

**Explanation of essential points:**

- **expectedLinuxX64Layout()** calculates byte offsets itself, including **point.x/point.y inside Packet**, and rounds **Packet sizeof** after the last field. It represents the Linux x86-64 ABI assumption, **not a C introspection API**.
- The array contains **12 numbers** in the order: **Point.size**, **Point.alignment**, **Point.x offset**, **Point.y offset**, **Packet.size**, **Packet.alignment**, **Packet.kind offset**, **Packet.point offset**, **Packet.point.x offset**, **Packet.point.y offset**, **Packet.weight offset**, **Packet.count offset**. Both sides must agree on the order of numbers as well.
- **Arrays.equals(expected, actual)** is the barrier before transferring data. If C changes declarations or packing, Java detects the difference.
- **allocateDirect(expected[E_SIZE])** creates a buffer with enough 32 bytes. **order(ByteOrder.nativeOrder())** sets the endianness for **putInt/putDouble/getInt/getDouble**, matching the C system used in this lab.
- The **put(index, ...)** calls are **absolute access**: they do not advance the buffer's position. C is passed the backing region starting from offset 0. When using relative APIs (**putInt(value)**), **position/limit** must be managed differently.
- **Byte.toUnsignedInt** causes **kind** to be displayed in the 0–255 range corresponding to **uint8_t**, rather than treating it as a signed Java byte.
- **nativeTransform()** receives and modifies the allocated buffer itself, then Java reads back the fields to demonstrate two-way transfer. The checksum value is just an easily observable check, not a security mechanism.

The program uses **Java 17** and standard JNI, without needing the **java.lang.foreign** module. The native call is **synchronous**; if C retains the pointer for processing after returning, a different memory lifecycle must be designed.

## 7. C11 Code: sizeof, alignof, offsetof, and Round-Trip

Create **packet_interop.c** with the **entire content** below. The file includes **PacketInterop.h** generated by **javac -h .**; that header already includes **jni.h** and declares the exact native methods.

~~~c
// packet_interop.c
#include "PacketInterop.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef struct {
    int32_t x;
    int32_t y;
} Point;

typedef struct {
    uint8_t kind;
    Point point;
    double weight;
    int32_t count;
} Packet;

JNIEXPORT jintArray JNICALL
Java_PacketInterop_nativeLayout(JNIEnv *env, jclass cls) {
    (void)cls;
    const jint values[] = {
        (jint)sizeof(Point), (jint)_Alignof(Point),
        (jint)offsetof(Point, x), (jint)offsetof(Point, y),
        (jint)sizeof(Packet), (jint)_Alignof(Packet),
        (jint)offsetof(Packet, kind), (jint)offsetof(Packet, point),
        (jint)(offsetof(Packet, point) + offsetof(Point, x)),
        (jint)(offsetof(Packet, point) + offsetof(Point, y)),
        (jint)offsetof(Packet, weight), (jint)offsetof(Packet, count)
    };
    const jsize length = (jsize)(sizeof(values) / sizeof(values[0]));
    jintArray result = (*env)->NewIntArray(env, length);
    if (result == NULL) return NULL;
    (*env)->SetIntArrayRegion(env, result, 0, length, values);
    return result;
}

static void fail(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (type != NULL) (*env)->ThrowNew(env, type, message);
}

JNIEXPORT jint JNICALL
Java_PacketInterop_nativeTransform(
        JNIEnv *env, jclass cls, jobject buffer) {
    (void)cls;
    void *raw = (*env)->GetDirectBufferAddress(env, buffer);
    jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);
    if (raw == NULL || capacity < (jlong)sizeof(Packet)) {
        fail(env, "Expected a sufficiently large direct ByteBuffer");
        return 0;
    }

    Packet packet;
    memcpy(&packet, raw, sizeof(packet));
    if (packet.kind != 7) {
        fail(env, "Unexpected packet kind");
        return 0;
    }
    packet.point.x += 100;
    packet.point.y *= 2;
    packet.weight *= 2.0;
    packet.count += 1;
    memcpy(raw, &packet, sizeof(packet));
    return (jint)(packet.point.x + packet.point.y + packet.count);
}
~~~

**Meaning of the C code:**

1. **sizeof(Point)/sizeof(Packet)** measures the type size **including padding**. **_Alignof** (C11) measures the alignment requirement. **offsetof** (from **stddef.h**) measures the field offset relative to the start of its containing struct.
2. Nested offsets are calculated as **offsetof(Packet, point) + offsetof(Point, x/y)**. Because **point** is a directly embedded object, this addition gives the offset of **point.x/point.y** from the start of Packet. This differs from a **Point*** field.
3. **nativeLayout** returns the actual metadata of the binary built by the C compiler. Java compares this against the layout calculated from the ABI before using any raw field offsets.
4. **GetDirectBufferAddress** returns the backing address; **GetDirectBufferCapacity** checks the capacity. The code **does not** use **buffer.position()** or **buffer.limit()** in C; both sides agreed that the payload starts at byte 0 and has exactly **sizeof(Packet)** bytes.
5. **memcpy(&packet, raw, sizeof packet)** copies bytes into a local **Packet** with proper alignment. Do not directly cast an arbitrary **void*** to **Packet*** to dereference: the backing ByteBuffer address is not proven by this code to have proper alignment for Packet, and casting also has object type/effective type issues.
6. C modifies **packet.point.x**, **packet.point.y**, **weight**, and **count**, then calls **memcpy(raw, &packet, sizeof packet)** to write back to the ByteBuffer. Java sees the new values when the function returns.
7. **GetDirectBufferAddress** may return **NULL** and **GetDirectBufferCapacity** may return **-1** if the buffer is not accessible via JNI; the code throws a valid exception. If **NewIntArray** runs out of memory, JNI has usually already set a pending exception and the function returns NULL.
8. **raw** is only used during the **nativeTransform** call. The code does not store the pointer in a global variable and does not allocate C memory that needs to be freed separately.

**Safety scope of memcpy:** the lab tests the Linux x86-64 ABI, where byte order and representations of **int32_t** and **double** are compatible between Java and C. Copying all 32 bytes including padding is only to illustrate the path of a struct. In real applications, **padding is not meaningful data**; do not put unnormalized padding into files, network payloads, hashes, or digital signatures. When designing a stable binary protocol across machines with different ABIs, serialize each field with fixed endianness and width instead of dumping **sizeof(struct)** directly.

## 8. Compiling and Running in Practice

Make sure you are in the directory containing **PacketInterop.java** and **packet_interop.c**, and set **JAVA_HOME** to the JDK 17+ directory in use. For example, on Linux, replace the path with your machine's JDK:

~~~bash
export JAVA_HOME=/path/to/jdk-17-or-newer
javac -h . PacketInterop.java
gcc -std=c11 -O2 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  packet_interop.c -o libpacketinterop.so
java -Djava.library.path=. PacketInterop
~~~

**javac -h .** compiles Java and generates the **PacketInterop.h** header matching the declared native methods. **-shared -fPIC** builds a shared object that can be loaded by the JVM; the name **libpacketinterop.so** matches **System.loadLibrary("packetinterop")** on Linux. The directory containing **libpacketinterop.so** is specified via **-Djava.library.path=.**. The library must use the same architecture as the JVM.

When compiled/run with a compatible JDK and Linux x86-64 GCC as assumed, stdout is **exact**:

~~~text
ABI layout match: true
Point: size=8 align=4 x=0 y=4
Packet: size=32 align=8 kind=0 point=4 point.x=4 point.y=8 weight=16 count=24
Before: kind=7 x=10 y=-3 weight=2.5 count=4
After:  kind=7 x=110 y=-6 weight=5.0 count=5
Native checksum=109
~~~

This is the output from the **compiled and executed example** using OpenJDK/GCC on Linux x86-64. There are **two spaces** after the colon in **After:  ** because the display string was intentionally written that way.

**Output explanation:**

- Point size 8, alignment 4, x offset 0, y offset 4.
- Packet size 32, alignment 8. **point.x** offset 4, **point.y** offset 8 from the start of Packet.
- C reads **kind 7**, **x 10**, **y -3**, **weight 2.5**, **count 4**, then writes back **x = 110**, **y = -6**, **weight = 5.0**, **count = 5**.
- The checksum returned by C is **110 + (-6) + 5 = 109**.
- Because Java still holds the same direct ByteBuffer, subsequent **getInt/getDouble** calls read the results after JNI returns.

If stdout does not match, **do not skip the ABI check step** to force the rest to run. Find the cause of the mismatch in the C declaration, compiler flags, JVM/native library architecture, packing, or byte order conventions.

## 9. Why sizeof Alone Is Not Enough: Every Offset Must Be Checked

Two structs can have the same **sizeof** yet different field layouts. For example, if C swaps the order of **kind** and **point**, the total sizeof of Packet can still be 32. If Java only checks **sizeof(Packet)==32** and then reads at the old offsets, data can be misinterpreted without throwing any exception.

Therefore, the lab checks all layers:

| What to Check | Java Side | C Side |
| --- | --- | --- |
| **Point.size** | Self-calculated end offset rounded to alignment | **sizeof(Point)** |
| **Point.align** | ABI assumption (4) | **_Alignof(Point)** |
| **Point.x/y** | Self-calculated 0 and 4 | **offsetof(Point, x/y)** |
| **Packet.size** | Round end offset of count up to struct align | **sizeof(Packet)** |
| **Packet.align** | ABI assumption (8) | **_Alignof(Packet)** |
| **Packet.kind/point** | Self-calculated 0 and 4 | **offsetof(Packet, kind/point)** |
| **Packet.point.x/y** | Offset of point + child field offset | Sum of **offsetof** in C |
| **Packet.weight/count** | Self-calculated 16 and 24 | **offsetof(Packet, weight/count)** |

There is no check on the actual alignment of the **ByteBuffer backing address** in this lab; that is why C uses **memcpy** into a local Packet allocated by the compiler with proper alignment. If C code reads directly as **Packet***, it must also prove that the address, ownership, and effective type are valid.

### 9.1. Nested Structs and Pointers Are Different

If **Point point** is replaced by **Point *point**, the field size in Packet is the **pointer size** of the target ABI. **offsetof(Packet, point)** only points to **where the address is stored**, not the **x/y** data. To read **point->x**, C needs to dereference a valid pointer whose lifetime exceeds the usage; Java cannot simply add **offsetof(Point,x)** to the pointer field's offset to read x.

Similarly, a **char name[16]** is an inline fixed-size array inside the struct; **char *name** is just a pointer. When designing FFM/JNA/JNI mappings, these two forms must be distinguished.

## 10. Intentional Failure Experiments

Perform these one by one on a **copy of the lab directory** and rebuild the C library. Each experiment should note the error that occurs before fixing it, then restore the source to its original state.

### Experiment A — Change the C Struct While Keeping Java Unchanged

In C, swap the positions of **kind** and **point**:

~~~c
typedef struct {
    Point point;
    uint8_t kind;
    double weight;
    int32_t count;
} Packet;
~~~

Keep the Java code unchanged, recompile **libpacketinterop.so**, and run. The expected result is **IllegalStateException** containing **ABI mismatch**, because the **nativeLayout()** array differs from what was expected. Java **does not run nativeTransform**. Even though sizeof may still be 32, the positions of **kind** or **point** have changed: checking size alone is not enough.

There is no need to memorize the entire stack trace string because line numbers/paths vary across JDKs; what matters is failing fast and printing both the expected and actual arrays.

### Experiment B — Use a Heap ByteBuffer

In Java, change **ByteBuffer.allocateDirect(expected[E_SIZE])** to **ByteBuffer.allocate(expected[E_SIZE])**, still setting **ByteOrder.nativeOrder()** as before. When running **nativeTransform**, the JNI direct-buffer address is invalid and C throws **IllegalArgumentException: Expected a sufficiently large direct ByteBuffer** (on a JVM that supports normal JNI direct access). This shows that a heap ByteBuffer cannot be treated the same as a direct buffer via **GetDirectBufferAddress**.

### Experiment C — Intentionally Wrong Endianness

In Java, remove **.order(ByteOrder.nativeOrder())**. A new **ByteBuffer** defaults to **BIG_ENDIAN**. On a typical **little-endian** Linux x86-64 system, **putInt/putDouble** produce bytes in a different order than C. **ABI layout match** can still be **true** because sizes/offsets have not changed, but the values of **x/y/weight/count** are no longer correct. This proves:

**Correct layout size/offsets ≠ correct byte representation ≠ correct data semantics.**

Restore native order after the experiment. When data is exchanged over a network or saved to files across different systems, a serialization format with fixed endianness is needed, rather than using the sender's byte order as the protocol standard.

### Experiment D — Insufficient Buffer Capacity

Change the allocation to **allocateDirect(expected[E_SIZE] - 1)**. In the original program, a **put** call may already throw **IndexOutOfBoundsException** before calling C, because Java checks bounds. If you want to specifically test the **capacity** branch in C, pass a short direct buffer **that was not written to beforehand by Java** to **nativeTransform**; C will detect insufficient capacity and throw **IllegalArgumentException**. This is an example of why bounds must be checked on **both sides**.

### Experiment E — Checking Tail Padding and Stride

Create **Packet array[2]** in C and measure:

~~~c
size_t stride = (size_t)((const unsigned char *)&array[1]
        - (const unsigned char *)&array[0]);
~~~

In the context of a C function with **Packet array[2];**, the snippet above gives **stride == sizeof(Packet)**. On the lab ABI, stride is **32**, not **21**. Therefore, Java must use **index * sizeof(Packet)** when modeling an array of structs as raw bytes, not the sum of the declared field sizes.

## 11. Padding, Alignment, and Production Pitfalls

### 11.1. Padding Does Not Belong to Business Data

Padding bytes may contain stale values or differ across compilers/builds. **memcmp** on an entire struct, hashing raw bytes, sending a C struct verbatim over the network, or using a struct as a long-term file format can fail even when all meaningful fields are identical. If you need to compare, compare field by field; if you need to serialize, create a deterministic format and omit padding.

In the lab program, **ByteBuffer.allocateDirect** allocates fresh memory, and C copies the entire struct region to demonstrate a round trip. This **does not mean** exchanging the full sizeof(struct) is a good design for a public protocol. Only use it at an in-process boundary with a verified binary ABI.

### 11.2. Does Not Apply Directly to Structs Containing Pointers or Flexible Array Members

For **char***, **void***, **Point***, or pointer fields, copying the raw bytes of a struct only copies the **address value**, not the object the pointer points to. You cannot serialize a pointer to another process, another machine, or save it to a file and reuse it. If a struct has a **flexible array member** (for example **char payload[]** at the end), **sizeof** only reflects the fixed part and corresponding padding, not the dynamically allocated payload. Both cases require separate layout and ownership design.

### 11.3. Packing, Alignment Overrides, and ABI

**#pragma pack**, compiler-specific attributes like **__attribute__((packed))**, or build flags can change alignment and offsets. With a packed struct, a pointer to a member may not be properly aligned for that member's native type; careless dereferencing can fault on strict architectures. Do not try to force Java to match by shrinking **sizeof** while ignoring alignment and how C accesses the data.

Another dimension: some ABIs have special rules for **bit-fields**, unions, vector types, long double, or struct return-by-value. Do not generalize the simple Packet formula to every C type. In complex cases, use compiler **sizeof/offsetof/alignof**, ABI documentation, and a binding generator (if appropriate).

### 11.4. Lifecycle and Concurrency

In this lab, Java creates a direct ByteBuffer, calls JNI **synchronously**, receives the result, and reads the buffer. C does not keep the pointer after returning, so no native worker is accessing the buffer after the call ends.

When used asynchronously, a C pointer retained across multiple calls may outlive the Java wrapper or be overwritten if the buffer is returned to a pool. You need clear ownership, a reference/lifetime keeping the data alive, a completion/cancellation mechanism, and a rule to close/reclaim only after C stops using it. **A direct buffer does not automatically manage a C pointer retained by a library.** If multiple threads write to a buffer, synchronization and visibility ordering must be defined; a single-threaded demo does not prove thread safety.

## 12. Extension with Foreign Function & Memory API (JDK 22+)

On **JDK 22 or newer**, **java.lang.foreign.MemoryLayout** can describe nested struct fields, allowing you to query **byteSize()**, **byteAlignment()**, and **byteOffset(PathElement...)**. **MemoryLayout.structLayout** does not insert padding automatically; you must explicitly declare **paddingLayout** if you want to match the C ABI. The example below is a **standalone program that does not call C**; it models the exact Linux x86-64 Packet layout from this lab. To prove actual C interoperability, you still need to compare against **sizeof/offsetof** metadata from the C library.

Create **PacketLayoutFFM.java** (JDK 22+ only):

~~~java
// PacketLayoutFFM.java -- JDK 22+
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

public class PacketLayoutFFM {
    public static void main(String[] args) {
        StructLayout point = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("x"),
                ValueLayout.JAVA_INT.withName("y")
        ).withName("point");

        StructLayout packet = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("kind"),
                MemoryLayout.paddingLayout(3),
                point,
                MemoryLayout.paddingLayout(4),
                ValueLayout.JAVA_DOUBLE.withName("weight"),
                ValueLayout.JAVA_INT.withName("count"),
                MemoryLayout.paddingLayout(4)
        );

        long nestedY = packet.byteOffset(
                MemoryLayout.PathElement.groupElement("point"),
                MemoryLayout.PathElement.groupElement("y"));

        System.out.println("Point size=" + point.byteSize());
        System.out.println("Packet size=" + packet.byteSize());
        System.out.println("Packet.point.y offset=" + nestedY);
    }
}
~~~

Compile and run with JDK 22+:

~~~bash
javac PacketLayoutFFM.java
java PacketLayoutFFM
~~~

Expected output with the described layout:

~~~text
Point size=8
Packet size=32
Packet.point.y offset=8
~~~

**Note:** this FFM example only **calculates the layout**; it does not perform a downcall into a C library. An actual FFM downcall must comply with the JDK version, native access permissions, linker ABI, Arena/MemorySegment lifecycle, and exact C signature. Do not use a MemoryLayout constructed by guesswork in place of actual verification against the C build. In particular, this standard FFM API **does not exist in Java 17**.

## 13. Lab Extension Directions

### 13.1. Extension One — Array of Multiple Packets

Modify C to accept a Packet count, and have Java allocate a direct buffer of size **count * verified sizeof(Packet)**. Native code processes each element using **memcpy** from **base + i * sizeof(Packet)** into a local Packet, modifies it, and copies it back. Check for integer overflow before multiplying **count * size**, bound the capacity, and do not access beyond the business data **limit**. Set at least two elements with different values to detect stride bugs.

### 13.2. Extension Two — Two-Level Nested Fields

Add a **struct Header** to **Point** or add a **struct Metadata** containing another **Point**. Measure the offset by summing **offsetof** across each level, such as **offsetof(Outer, mid) + offsetof(Mid, inner) + offsetof(Inner, value)**. Compare with the offset calculated independently on the Java side. Also check **sizeof** of each level and the alignment of the containing level.

### 13.3. Extension Three — Multiple ABIs and Different Endianness

Build separately on **Linux x86-64**, a suitable ARM64 system, and Windows x64 if tools are available; record **sizeof/alignof/offsetof** from C without assuming all results are identical. On a big-endian architecture (if available), observe **ByteOrder.nativeOrder()**. Only adjust the Java-side layout after identifying the ABI and establishing the correct expected table; do not disable the guard when a mismatch is detected.

### 13.4. Extension Four — Measuring Copy vs. Direct Cost

Compare a **byte[] + JNI GetByteArrayRegion** approach against the layout-verified direct ByteBuffer approach. Measure buffer creation/copy cost, JNI crossing, native processing, and readback. Do not measure only the C function and claim the entire pipeline is zero-copy. Use a sufficiently large workload and a reliable benchmark (JMH) when performance conclusions are needed; for the current layout task, correctness is the top priority.

### 13.5. Completion Criteria

- All offsets and sizeof/alignof predicted by Java **match** C, not just the total size.
- Java writes and reads all fields, including nested **point.x** and **point.y**.
- Native code modifies the fields and Java verifies the correct results **after JNI return**.
- An intentional C layout change triggers **fail fast** before raw offsets are used.
- The buffer is not read out of bounds and native code does not retain pointers beyond the permitted lifecycle.
- The learner can identify padding at 1–3, 12–15, and 28–31 on the sample ABI.
- There is a clear distinction between **embedded struct**, **pointer**, **array stride**, byte order, and binary protocol.

## 14. Common Issues and Diagnosis

| Symptom | Possible Cause | How to Check/Resolve |
| --- | --- | --- |
| **UnsatisfiedLinkError: no packetinterop in java.library.path** | JVM cannot find **libpacketinterop.so** | Check the file, working directory, and **-Djava.library.path=.** |
| **UnsatisfiedLinkError: Native method ...** | Wrong JNI symbol name, Java/C build version mismatch | Re-run **javac -h .**, include the generated header, and rebuild C |
| **fatal error: PacketInterop.h: No such file** | **javac -h .** was not run or working in the wrong directory | Generate the header before GCC build |
| **fatal error: jni.h: No such file** | **JAVA_HOME** does not point to JDK or missing include path | Use **$JAVA_HOME/include** and **include/linux** |
| Library exists but JVM cannot load it | Wrong target architecture or missing native dependency | Compare 64-bit JVM and binary using **file libpacketinterop.so**, check dependencies |
| **ABI mismatch** | C struct modified, different packing/alignment, different target ABI | Print expected/actual; check each **sizeof/_Alignof/offsetof** |
| **Point matches, Packet mismatches** | Outer struct padding or different field order | Check **point offset**, **weight offset**, **count offset**, tail padding |
| Size/offsets match but fields produce nonsense numbers | Wrong byte order, wrong **int32_t/double** interpretation, wrong write window | Keep **nativeOrder()**, check byte pattern and input |
| **IllegalArgumentException** in nativeTransform | Buffer is not direct or capacity is smaller than **sizeof(Packet)** | Use **allocateDirect**, compare capacity and verified size |
| **SIGSEGV/JVM crash** in manually modified version | Invalid pointer dereference, wrong alignment/lifetime, out-of-bounds access | Avoid raw pointer casts; check capacity and owner; use ASan/Valgrind if appropriate |
| Output changes randomly in padding | Unnormalized padding or code reading meaningless bytes | Do not compare/hash raw structs; serialize field by field |
| C compiled with different flags than previous run | Old shared object still loaded by Java | Clean build the **correct C file** and run from the right directory |

When investigating a mismatch, prioritize printing C's **actual metadata** alongside Java's **expected metadata**. Measuring offsets from the C library's output and immediately using those numbers to pack data may make the program run, but it skips the **independent layout verification** that this lab requires.

## 15. Key Takeaways

**sizeof** and **_Alignof** describe the actual size and alignment of a C type in the current build. **offsetof** describes the byte distance from the start of a struct to a direct field; for multi-level embedded structs, you can sum the offsets of each level. **sizeof(struct)** is often larger than the sum of field sizes due to padding.

Java **ByteBuffer** carries data at absolute offsets but does not know how much padding a C struct has. **ByteOrder.nativeOrder()** handles endianness within the current ABI scope; it does not replace verifying size, offsets, and representation. **GetDirectBufferAddress** gives JNI access to the backing memory of a supported direct buffer, while **GetDirectBufferCapacity** helps check capacity. Using **memcpy** into a local struct avoids pointer alignment assumptions.

The lab is only considered complete when both **layout verification** and **data round-trip** succeed. When packing data for a protocol or long-term storage, avoid serializing **sizeof(Packet)** bytes directly because of ABI, padding, and pointer dependencies. Designing a stable wire format with versioning, field encoding, and fixed endianness is appropriate.

## 16. References

- [JNI Functions: GetDirectBufferAddress, GetDirectBufferCapacity, NewDirectByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/functions.html)
- [Java 17 ByteBuffer API: absolute access, direct buffer, byte order](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java 22 MemoryLayout API: structLayout, paddingLayout, byteOffset and layout path](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Java 22 StructLayout API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html)
- [C language — sizeof, alignment and offsetof; verify against target ABI/compiler](https://en.cppreference.com/w/c/types/offsetof)
