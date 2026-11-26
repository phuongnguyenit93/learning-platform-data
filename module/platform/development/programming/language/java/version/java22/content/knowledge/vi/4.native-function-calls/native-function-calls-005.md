# Truyền số nguyên, số thực, con trỏ và cấu trúc giữa Java với C

## Mục tiêu

Khi Java cần gọi một hàm trong thư viện C, hai phía phải thống nhất cách biểu diễn tham số, giá trị trả về và địa chỉ bộ nhớ. Ví dụ, Java `int` phải được ánh xạ tới kiểu số nguyên C phù hợp; một con trỏ C phải được truyền như địa chỉ vùng nhớ; còn một `struct` phải được mô tả đúng kích thước, căn chỉnh và padding theo ABI của thư viện.

Foreign Function & Memory API (FFM) cung cấp các thành phần để thực hiện việc này:

- `Linker`: kết nối Java với hàm native theo ABI của nền tảng.
- `SymbolLookup`: tìm địa chỉ hàm trong thư viện native.
- `FunctionDescriptor`: mô tả kiểu tham số và kiểu trả về của hàm C.
- `ValueLayout`, `AddressLayout` và `StructLayout`: mô tả dữ liệu được truyền.
- `MemorySegment` và `Arena`: biểu diễn, cấp phát và quản lý vùng nhớ.

FFM API được hoàn thiện trong JDK 22 theo JEP 454 và vẫn là API chuẩn trong các JDK hiện đại. Bài học sử dụng API ổn định từ JDK 22 trở lên, với tài liệu Java SE 27 làm mốc tham chiếu hiện hành. Không cần bật preview.

## Luồng gọi hàm C từ Java

Khi Java gọi một hàm native, thao tác này được gọi là *downcall*. Quy trình thường gồm các bước:

1. Lấy native linker phù hợp với hệ điều hành và kiến trúc đang chạy.
2. Tìm địa chỉ hàm C trong thư viện.
3. Mô tả chữ ký C bằng `FunctionDescriptor`.
4. Tạo `MethodHandle` bằng `Linker.downcallHandle(...)`.
5. Chuẩn bị vùng nhớ và tham số.
6. Gọi `MethodHandle` với kiểu Java khớp chính xác với descriptor.

Sơ đồ tổng quát:

~~~text
Java code
   |
   | Linker.nativeLinker()
   v
Native Linker ---- SymbolLookup ----> địa chỉ hàm C
   |
   | FunctionDescriptor
   v
Downcall MethodHandle
   |
   | primitive / MemorySegment
   v
C function theo ABI của nền tảng
~~~

Linker chịu trách nhiệm chuyển các giá trị Java sang quy ước gọi hàm native của nền tảng, chẳng hạn System V ABI trên Linux/x64 hoặc ABI tương ứng trên Windows. Mã Java vẫn phải mô tả đúng chữ ký của hàm C; linker không thể tự suy ra chữ ký chỉ từ tên symbol.

## Ánh xạ kiểu dữ liệu giữa C và Java

### Số nguyên và số thực

Các kiểu C cơ bản thường được ánh xạ qua `ValueLayout`:

| Kiểu C | Layout thường dùng | Carrier Java |
|---|---|---|
| `_Bool` / `bool` | `ValueLayout.JAVA_BOOLEAN` | `boolean` |
| `int8_t`, `char` | `ValueLayout.JAVA_BYTE` | `byte` |
| `int16_t`, `short` | `ValueLayout.JAVA_SHORT` | `short` |
| `int32_t`, `int` trên ABI có int 32 bit | `ValueLayout.JAVA_INT` | `int` |
| `int64_t`, `long long` trên ABI có long long 64 bit | `ValueLayout.JAVA_LONG` | `long` |
| `float` | `ValueLayout.JAVA_FLOAT` | `float` |
| `double` | `ValueLayout.JAVA_DOUBLE` | `double` |
| Con trỏ như `char *`, `Point *` | `ValueLayout.ADDRESS` | `MemorySegment` |

Bảng trên mô tả các ánh xạ thường gặp. Khi làm việc với kiểu C phụ thuộc nền tảng như `long`, `size_t` hoặc `wchar_t`, không nên tự giả định kích thước. Hãy lấy layout chuẩn từ linker:

`int8_t` luôn là số nguyên có dấu 8 bit. Kiểu `char` của C cũng chiếm một byte, nhưng việc `char` là signed hay unsigned phụ thuộc implementation; nếu hợp đồng cần độ rộng và dấu rõ ràng, hãy dùng `int8_t` hoặc `uint8_t` trong header C.

~~~java
Linker linker = Linker.nativeLinker();

MemoryLayout cLong = linker.canonicalLayouts().get("long");
MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
~~~

Ví dụ, trên Linux/x64, C `long` và `size_t` thường có kích thước 8 byte; trên Windows/x64, C `long` thường có kích thước 4 byte trong khi `size_t` có kích thước 8 byte. Java `long` luôn có kích thước 8 byte, nên không thể dùng nó để thay thế mọi kiểu C `long` trên mọi nền tảng.

Với các kiểu có độ rộng cố định như `int32_t`, `int64_t`, `float` và `double`, ánh xạ sẽ dễ dự đoán hơn. Các ví dụ chính trong bài dùng `int32_t` để tránh phụ thuộc vào kích thước của C `long`.

### Kiểu unsigned

C có các kiểu unsigned như `uint8_t`, `uint16_t`, `uint32_t` và `uint64_t`. Linker thường dùng cùng layout có độ rộng tương ứng với kiểu signed; Java carrier vẫn là `byte`, `short`, `int` hoặc `long`.

Ví dụ, nếu đọc `uint32_t` qua `JAVA_INT`, giá trị bit được giữ nguyên nhưng một số giá trị lớn hơn `Integer.MAX_VALUE` sẽ xuất hiện dưới dạng số âm khi diễn giải như `int`. Có thể đổi cách diễn giải:

~~~java
int raw = segment.get(ValueLayout.JAVA_INT, 0);
long unsignedValue = Integer.toUnsignedLong(raw);
~~~

Với `uint8_t` và `uint16_t`, dùng `Byte.toUnsignedInt` và `Short.toUnsignedInt`. Với `uint64_t`, `long` giữ nguyên 64 bit; nếu cần biểu diễn số dương vượt quá `Long.MAX_VALUE`, dùng phép toán unsigned của `Long` hoặc `BigInteger`.

## Con trỏ C được biểu diễn bằng MemorySegment

Một con trỏ C là địa chỉ vùng nhớ. Trong FFM, `ValueLayout.ADDRESS` mô tả giá trị địa chỉ và carrier Java tương ứng là `MemorySegment`.

Ví dụ, hàm C nhận một con trỏ tới mảng số thực:

~~~c
void scale_values(float *values, int32_t length, float factor);
~~~

Trong Java, vùng dữ liệu được cấp phát bằng `Arena`; `MemorySegment` được truyền vào vị trí con trỏ:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment values = arena.allocate(
        MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_FLOAT)
    );

    values.set(ValueLayout.JAVA_FLOAT, 0, 1.5f);
    values.set(ValueLayout.JAVA_FLOAT, 4, 2.5f);
    values.set(ValueLayout.JAVA_FLOAT, 8, 3.5f);

    // values được truyền vào hàm C có tham số float*.
}
~~~

Có thể gắn layout đích vào address layout khi biết kiểu và kích thước vùng nhớ mà con trỏ trỏ tới:

~~~java
AddressLayout floatArrayPointer = ValueLayout.ADDRESS.withTargetLayout(
    MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_FLOAT)
);
~~~

Layout đích giúp mô tả dữ liệu mà con trỏ tham chiếu. Nó không cấp phát vùng nhớ và cũng không chứng minh rằng địa chỉ native thực sự hợp lệ; lập trình viên vẫn phải bảo đảm segment đủ lớn và còn sống trong suốt thời gian gọi.

Nếu con trỏ là con trỏ tới một struct, dùng target layout là struct tương ứng:

~~~java
AddressLayout pointPointer =
    ValueLayout.ADDRESS.withTargetLayout(POINT_LAYOUT);
~~~

Khi C nhận một con trỏ có thể là null, Java có thể truyền `MemorySegment.NULL` nếu hợp đồng hàm cho phép. Không truyền null cho hàm yêu cầu con trỏ hợp lệ.

## StructLayout mô tả struct C

Các kiểu dữ liệu tổng hợp như `struct` trong C được mô tả bằng `StructLayout`, một dạng `GroupLayout`. Mỗi trường là một layout thành viên. Các trường phải xuất hiện đúng thứ tự, kích thước, căn chỉnh và padding giống cấu trúc C đã biên dịch.

Ví dụ C:

~~~c
#include <stdint.h>

#if defined(_WIN32)
#define NATIVE_API __declspec(dllexport)
#else
#define NATIVE_API
#endif

typedef struct Point {
    int32_t x;
    int32_t y;
} Point;
~~~

Layout tương ứng trong Java:

~~~java
static final StructLayout POINT_LAYOUT = MemoryLayout.structLayout(
    ValueLayout.JAVA_INT.withName("x"),
    ValueLayout.JAVA_INT.withName("y")
).withName("Point");
~~~

Cấu trúc này có kích thước 8 byte và căn chỉnh 4 byte trên ABI thông thường. Hai trường nằm tại offset 0 và 4. Có thể truy cập theo tên thay vì hard-code offset:

~~~java
static final VarHandle POINT_X =
    POINT_LAYOUT.varHandle(MemoryLayout.PathElement.groupElement("x"));

static final VarHandle POINT_Y =
    POINT_LAYOUT.varHandle(MemoryLayout.PathElement.groupElement("y"));

static void setPoint(MemorySegment point, int x, int y) {
    POINT_X.set(point, 0L, x);
    POINT_Y.set(point, 0L, y);
}
~~~

### Padding phải khớp với ABI

Không được giả định `structLayout(...)` tự chèn padding như compiler C. Ví dụ:

~~~c
struct Sample {
    int8_t kind;
    int32_t value;
};
~~~

Trên ABI phổ biến, `value` cần căn chỉnh 4 byte nên có 3 byte đệm sau `kind`. Layout phải mô tả khoảng đệm đó:

~~~java
static final StructLayout SAMPLE_LAYOUT = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("kind"),
    MemoryLayout.paddingLayout(3),
    ValueLayout.JAVA_INT.withName("value")
).withName("Sample");
~~~

Vị trí trường:

| Thành phần | Offset | Kích thước |
|---|---:|---:|
| `kind` | 0 | 1 byte |
| Padding | 1 | 3 byte |
| `value` | 4 | 4 byte |

Struct có kích thước 8 byte và căn chỉnh 4 byte. Với cấu trúc phức tạp hơn, có thể cần padding giữa các trường và padding ở cuối để kích thước của mỗi phần tử trong mảng là bội số của căn chỉnh struct.

Hãy đối chiếu header C, compiler, kiến trúc và ABI thực tế. Ví dụ về padding chỉ đúng với các giả định nền tảng đã nêu; không sao chép layout của một nền tảng sang nền tảng khác nếu chưa xác minh.

## Truyền struct bằng con trỏ và truyền struct theo giá trị

C có thể nhận struct theo hai cách:

~~~c
void move_point(Point *point, int32_t dx, int32_t dy);
int32_t point_manhattan(Point point);
~~~

- `Point *point`: hàm nhận địa chỉ và có thể sửa trực tiếp vùng nhớ của struct.
- `Point point`: hàm nhận một bản sao struct theo quy ước gọi hàm C.

Cả hai đều có thể được mô tả bằng FFM. Trường hợp con trỏ dùng `ADDRESS` với target layout; trường hợp truyền theo giá trị dùng trực tiếp `POINT_LAYOUT` trong `FunctionDescriptor`.

~~~java
FunctionDescriptor movePointDescriptor = FunctionDescriptor.ofVoid(
    ValueLayout.ADDRESS.withTargetLayout(POINT_LAYOUT),
    ValueLayout.JAVA_INT,
    ValueLayout.JAVA_INT
);

FunctionDescriptor manhattanDescriptor = FunctionDescriptor.of(
    ValueLayout.JAVA_INT,
    POINT_LAYOUT
);
~~~

Với group layout làm tham số, carrier Java là `MemorySegment`. Với group layout làm giá trị trả về, downcall handle cần thêm một tham số `SegmentAllocator` ở đầu để cấp phát vùng nhớ chứa struct kết quả. Không phải mọi hình dạng struct đều được mọi ABI hỗ trợ; linker có thể từ chối layout không phù hợp quy tắc gọi hàm của nền tảng.

## Ví dụ hoàn chỉnh: Java gọi thư viện C

Ví dụ gồm số nguyên, số thực, mảng con trỏ và struct. Mã C:

~~~c
#include <stdint.h>

typedef struct Point {
    int32_t x;
    int32_t y;
} Point;

NATIVE_API int32_t add_i32(int32_t a, int32_t b) {
    return a + b;
}

NATIVE_API float multiply_f32(float a, float b) {
    return a * b;
}

NATIVE_API double average_f64(double a, double b) {
    return (a + b) / 2.0;
}

NATIVE_API void scale_values(float *values, int32_t length, float factor) {
    for (int32_t i = 0; i < length; i++) {
        values[i] *= factor;
    }
}

NATIVE_API void move_point(Point *point, int32_t dx, int32_t dy) {
    point->x += dx;
    point->y += dy;
}

NATIVE_API int32_t point_manhattan(Point point) {
    int32_t x = point.x < 0 ? -point.x : point.x;
    int32_t y = point.y < 0 ? -point.y : point.y;
    return x + y;
}

NATIVE_API Point translate_point(Point point, int32_t dx, int32_t dy) {
    Point result = { point.x + dx, point.y + dy };
    return result;
}
~~~

Mã Java:

~~~java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SegmentAllocator;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.nio.file.Path;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class NativeCallExample {

    private static final ValueLayout.OfInt I32 = ValueLayout.JAVA_INT;
    private static final ValueLayout.OfFloat F32 = ValueLayout.JAVA_FLOAT;
    private static final ValueLayout.OfDouble F64 = ValueLayout.JAVA_DOUBLE;

    private static final StructLayout POINT_LAYOUT = MemoryLayout.structLayout(
        I32.withName("x"),
        I32.withName("y")
    ).withName("Point");

    private static final AddressLayout FLOAT_ARRAY_POINTER =
        ValueLayout.ADDRESS.withTargetLayout(
            MemoryLayout.sequenceLayout(3, F32)
        );

    private static final AddressLayout POINT_POINTER =
        ValueLayout.ADDRESS.withTargetLayout(POINT_LAYOUT);

    private static final VarHandle POINT_X =
        POINT_LAYOUT.varHandle(groupElement("x"));

    private static final VarHandle POINT_Y =
        POINT_LAYOUT.varHandle(groupElement("y"));

    public static void main(String[] args) throws Throwable {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Truyền đường dẫn tới thư viện native làm đối số đầu tiên"
            );
        }

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup library =
                SymbolLookup.libraryLookup(Path.of(args[0]), arena);

            MethodHandle addI32 = linker.downcallHandle(
                library.findOrThrow("add_i32"),
                FunctionDescriptor.of(I32, I32, I32)
            );

            MethodHandle multiplyF32 = linker.downcallHandle(
                library.findOrThrow("multiply_f32"),
                FunctionDescriptor.of(F32, F32, F32)
            );

            MethodHandle averageF64 = linker.downcallHandle(
                library.findOrThrow("average_f64"),
                FunctionDescriptor.of(F64, F64, F64)
            );

            MethodHandle scaleValues = linker.downcallHandle(
                library.findOrThrow("scale_values"),
                FunctionDescriptor.ofVoid(
                    FLOAT_ARRAY_POINTER,
                    I32,
                    F32
                )
            );

            MethodHandle movePoint = linker.downcallHandle(
                library.findOrThrow("move_point"),
                FunctionDescriptor.ofVoid(
                    POINT_POINTER,
                    I32,
                    I32
                )
            );

            MethodHandle pointManhattan = linker.downcallHandle(
                library.findOrThrow("point_manhattan"),
                FunctionDescriptor.of(I32, POINT_LAYOUT)
            );

            MethodHandle translatePoint = linker.downcallHandle(
                library.findOrThrow("translate_point"),
                FunctionDescriptor.of(
                    POINT_LAYOUT,
                    POINT_LAYOUT,
                    I32,
                    I32
                )
            );

            int sum = (int) addI32.invokeExact(12, 30);
            float product = (float) multiplyF32.invokeExact(1.5f, 4.0f);
            double average = (double) averageF64.invokeExact(10.0, 14.0);

            MemorySegment values = arena.allocate(
                MemoryLayout.sequenceLayout(3, F32)
            );
            values.set(F32, 0, 1.0f);
            values.set(F32, 4, 2.0f);
            values.set(F32, 8, 3.0f);
            scaleValues.invokeExact(values, 3, 2.0f);

            MemorySegment point = arena.allocate(POINT_LAYOUT);
            POINT_X.set(point, 0L, 10);
            POINT_Y.set(point, 0L, 20);

            movePoint.invokeExact(point, 1, -2);
            int x = (int) POINT_X.get(point, 0L);
            int y = (int) POINT_Y.get(point, 0L);

            // Tham số struct được truyền theo giá trị.
            int manhattan = (int) pointManhattan.invokeExact(point);

            // Struct trả về theo giá trị cần SegmentAllocator ở đầu.
            MemorySegment translated = (MemorySegment)
                translatePoint.invokeExact(
                    (SegmentAllocator) arena,
                    point,
                    5,
                    7
                );

            int translatedX = (int) POINT_X.get(translated, 0L);
            int translatedY = (int) POINT_Y.get(translated, 0L);

            System.out.println("add_i32 = " + sum);
            System.out.println("multiply_f32 = " + product);
            System.out.println("average_f64 = " + average);
            System.out.println("scaled values = "
                + values.get(F32, 0) + ", "
                + values.get(F32, 4) + ", "
                + values.get(F32, 8));
            System.out.println("moved point = (" + x + ", " + y + ")");
            System.out.println("point_manhattan = " + manhattan);
            System.out.println("translated point = ("
                + translatedX + ", " + translatedY + ")");
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
add_i32 = 42
multiply_f32 = 6.0
average_f64 = 12.0
scaled values = 2.0, 4.0, 6.0
moved point = (11, 18)
point_manhattan = 29
translated point = (16, 25)
~~~

Ví dụ thể hiện các kiểu truyền dữ liệu:

| Hàm C | Kiểu tham số / trả về | Biểu diễn trong Java |
|---|---|---|
| `add_i32` | `int32_t, int32_t -> int32_t` | `int, int -> int` |
| `multiply_f32` | `float, float -> float` | `float, float -> float` |
| `average_f64` | `double, double -> double` | `double, double -> double` |
| `scale_values` | `float *, int32_t, float` | `MemorySegment, int, float` |
| `move_point` | `Point *, int32_t, int32_t` | `MemorySegment, int, int` |
| `point_manhattan` | `Point -> int32_t` | `MemorySegment -> int` |
| `translate_point` | `Point, int32_t, int32_t -> Point` | `SegmentAllocator, MemorySegment, int, int -> MemorySegment` |

## Biên dịch thư viện C và chạy Java

Lưu mã C thành `native_demo.c`. Tạo thư viện dùng chung theo hệ điều hành:

~~~bash
# Linux
cc -std=c11 -fPIC -shared -o libnative_demo.so native_demo.c

# macOS
cc -std=c11 -dynamiclib -o libnative_demo.dylib native_demo.c

# Windows (Developer Command Prompt của Visual Studio)
cl /LD native_demo.c /link /OUT:native_demo.dll
~~~

Lưu mã Java thành `NativeCallExample.java`, sau đó biên dịch bằng JDK 22 trở lên:

~~~bash
javac NativeCallExample.java
~~~

Chạy với đường dẫn tới thư viện vừa tạo:

~~~bash
# Windows
java --enable-native-access=ALL-UNNAMED NativeCallExample native_demo.dll

# Linux
java --enable-native-access=ALL-UNNAMED NativeCallExample ./libnative_demo.so

# macOS
java --enable-native-access=ALL-UNNAMED NativeCallExample ./libnative_demo.dylib
~~~

`--enable-native-access=ALL-UNNAMED` bật native access cho mã chạy trên classpath. Nếu ứng dụng chạy trên module path, hãy bật native access cho đúng tên module, ví dụ `--enable-native-access=com.example.app`.

## Quy tắc quan trọng về ABI và an toàn

### FunctionDescriptor phải khớp tuyệt đối với hàm C

`FunctionDescriptor` mô tả số lượng, thứ tự, kích thước và kiểu của mọi tham số cũng như giá trị trả về. Linker không đọc được prototype từ symbol để tự kiểm tra descriptor. Nếu khai báo sai kiểu, sai thứ tự hoặc sai ABI, lời gọi có thể gây hành vi không xác định, hỏng bộ nhớ hoặc làm JVM dừng đột ngột.

Hãy đối chiếu prototype trong header C và layout thực tế. Không dùng `JAVA_LONG` thay cho C `long` trên mọi nền tảng; dùng `Linker.canonicalLayouts()` cho các kiểu ABI phụ thuộc nền tảng.

### Con trỏ và vòng đời bộ nhớ

- Vùng nhớ truyền qua con trỏ phải còn sống trong suốt lời gọi native.
- Không đóng arena khi hàm C còn đang sử dụng segment.
- Nếu C lưu con trỏ để sử dụng sau khi hàm trả về, vùng nhớ Java phải có vòng đời đủ dài; không dùng confined arena ngắn hạn.
- Khi hàm C trả về con trỏ, Java thường nhận một segment có kích thước 0 và không tự biết vùng nhớ dài bao nhiêu hoặc ai chịu trách nhiệm giải phóng. Chỉ tạo segment có kích thước lớn hơn khi đã biết chắc kích thước và vòng đời từ hợp đồng native.
- Nếu descriptor của giá trị trả về dùng `ADDRESS.withTargetLayout(layout)`, segment kết quả được gán kích thước theo `layout.byteSize()`. Layout đích vẫn phải đúng với vùng nhớ thật.
- Nếu C cấp phát bằng `malloc`, phải giải phóng bằng hàm giải phóng tương ứng của thư viện, chẳng hạn `free`; không để Java tự đóng một vùng nhớ mà C đang sở hữu.
- Dùng `MemorySegment.NULL` chỉ khi API C cho phép con trỏ null.

### Native access là quyền cần bật

Một số thao tác FFM là restricted methods, trong đó có `Linker.downcallHandle`, `Linker.upcallStub`, `SymbolLookup.libraryLookup` và `AddressLayout.withTargetLayout`. Chúng có thể làm JVM crash hoặc gây memory corruption nếu chữ ký, địa chỉ hoặc layout đích không chính xác.

Từ JDK 24, mặc định runtime cảnh báo khi module thực hiện native access mà chưa được bật quyền. Tài liệu hiện hành khuyến nghị bật quyền tường minh bằng `--enable-native-access`; trong các phiên bản tương lai, truy cập native không được bật sẽ bị từ chối theo mặc định. Hãy chỉ cấp quyền cho module thực sự cần gọi native.

### Hàm C có số lượng tham số biến đổi

Các hàm variadic như `printf(const char *format, ...)` có quy tắc gọi hàm đặc biệt. FFM yêu cầu mô tả dạng lời gọi đã chuyên biệt hóa và cung cấp `Linker.Option.firstVariadicArg(index)`. Các tham số variadic cũng chịu default argument promotions của C; ví dụ `float` được nâng thành `double`. Không dùng descriptor của hàm variadic như thể đó là hàm có chữ ký cố định.

## Chọn cách truyền dữ liệu

| Nhu cầu | C | Java / FFM |
|---|---|---|
| Truyền số nguyên 32 bit | `int32_t` | `JAVA_INT`, carrier `int` |
| Truyền số thực 32 bit | `float` | `JAVA_FLOAT`, carrier `float` |
| Truyền số thực 64 bit | `double` | `JAVA_DOUBLE`, carrier `double` |
| Truyền con trỏ tới mảng | `float *` | `ADDRESS` và `MemorySegment` |
| Truyền con trỏ tới struct | `Point *` | `ADDRESS.withTargetLayout(POINT_LAYOUT)` |
| Truyền struct theo giá trị | `Point` | `StructLayout` trong `FunctionDescriptor` |
| Trả về struct theo giá trị | `Point` | Group layout và `SegmentAllocator` |
| Truyền kiểu phụ thuộc ABI | `long`, `size_t` | `Linker.canonicalLayouts()` |

## Tài liệu tham khảo

- [JEP 454 – Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [Foreign Function and Memory API – Oracle Java SE 27](https://docs.oracle.com/en/java/javase/27/core/foreign-function-and-memory-api.html)
- [Calling a C Library Function with the FFM API – Java SE 27](https://docs.oracle.com/en/java/javase/27/core/calling-c-library-function-foreign-function-and-memory-api.html)
- [Linker – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.html)
- [FunctionDescriptor – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [SymbolLookup – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [ValueLayout – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Restricted Methods – Oracle Java SE 27](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html)

