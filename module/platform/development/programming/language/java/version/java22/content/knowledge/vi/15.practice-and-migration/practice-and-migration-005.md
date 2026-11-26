# Bài tập FFM: đọc cấu trúc nhị phân và gọi một hàm trong thư viện native

## Phạm vi và mục tiêu

Bài thực hành thuộc chương **Vận dụng và nâng cấp** của module **JAVA_VERSION_JAVA22**. Bạn sẽ đọc một gói dữ liệu cảm biến bằng Foreign Function & Memory API (FFM), chuyển dữ liệu sang vùng nhớ phù hợp với C, rồi gọi một hàm trong thư viện native để tính nhiệt độ trung bình.

FFM trở thành API chính thức từ Java 22, nằm trong package `java.lang.foreign` của `java.base`. Bài dùng API chính thức này; các cơ chế được thực hành vẫn có mặt trong [tài liệu FFM của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/package-summary.html). Bạn không cần bật preview hay thêm module incubator. Xem thêm [hướng dẫn FFM của Java 22](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html).

Sau bài học, bạn cần giải thích được:

- Cách mô tả kích thước, offset, byte order và alignment của dữ liệu nhị phân.
- Cách phân biệt định dạng lưu trữ với cách biểu diễn dữ liệu theo ABI của thư viện C.
- Cách dùng `SymbolLookup`, `FunctionDescriptor` và `Linker` để tạo một downcall.
- Ai sở hữu vùng nhớ, vùng nhớ sống bao lâu và con trỏ được dùng trong khoảng thời gian nào.
- Cách nhận diện lỗi dữ liệu, lỗi liên kết và lỗi trả về từ hàm C.

## 1. Tình huống và yêu cầu bài tập

Một thiết bị gửi gói dữ liệu gồm header và một dãy bản ghi cảm biến. Mỗi bản ghi chứa loại cảm biến, mã cảm biến và nhiệt độ. Một thư viện C có hàm tính trung bình của mảng `double`.

Luồng xử lý cần xây dựng:

```text
Gói byte little-endian, bản ghi 7 byte
                 |
                 v
Kiểm tra header, số bản ghi, độ dài và giá trị
                 |
                 v
Các Reading trong Java, nhiệt độ theo độ C
                 |
                 v
Mảng double trong bộ nhớ native, theo ABI của máy
                 |
                 v
average_temperature(values, count, result)
                 |
                 v
Kiểm tra mã trả về và đọc kết quả
```

Chương trình phải từ chối gói không hợp lệ trước khi gọi native. Hàm C chỉ nhận các giá trị đã giải mã; nó không nhận trực tiếp các bản ghi đóng gói.

### Điều kiện thực hành

- JDK 22 trở lên; `java` và `javac` cần trỏ tới phiên bản phù hợp.
- Máy 64 bit với ABI C thông dụng trên Windows, Linux hoặc macOS.
- Compiler C hỗ trợ C11. Thư viện native phải được build cho cùng hệ điều hành và kiến trúc với JVM đang chạy.
- Các lệnh dưới đây chạy trong thư mục thực hành riêng, nơi bạn lưu `sensor.c` và `FfmSensorExercise.java`.

Trong ví dụ, C `int` có kích thước 4 byte và C `double` có kích thước 8 byte, dùng biểu diễn nhị phân thông dụng của các nền tảng trên. Mã C có kiểm tra một số giả định này ở thời điểm biên dịch.

## 2. Đặc tả gói nhị phân

### 2.1. Header dài 8 byte

| Offset | Số byte | Trường | Quy tắc |
| --- | ---: | --- | --- |
| 0 | 4 | `magic` | Bốn byte ASCII `FFM1`: `46 46 4D 31`. |
| 4 | 2 | `version` | Số nguyên không dấu, little-endian; giá trị hợp lệ là 1. |
| 6 | 2 | `count` | Số nguyên không dấu, little-endian; từ 1 đến 65.535. |

### 2.2. Mỗi bản ghi dài 7 byte, không có padding

Offset trong bảng tính từ đầu từng bản ghi.

| Offset | Số byte | Trường | Quy tắc |
| --- | ---: | --- | --- |
| 0 | 1 | `kind` | Số nguyên không dấu; bài này chỉ chấp nhận 1. |
| 1 | 4 | `sensorId` | Số nguyên không dấu 32 bit, little-endian. |
| 5 | 2 | `temperatureTenths` | Số nguyên có dấu 16 bit, little-endian; đơn vị 0,1 °C. |

Miền nhiệt độ của bài là từ -40,0 °C đến 125,0 °C, tức giá trị lưu từ `-400` đến `1250`. Mã cảm biến được lưu trong Java bằng `long` để biểu diễn đầy đủ miền `uint32`.

Gói hợp lệ có đúng:

```text
8 + count × 7 byte
```

Không chấp nhận byte thừa ở cuối. Đây là quy tắc của định dạng bài tập; nếu giao thức thực tế cho phép extension hoặc nhiều gói nối tiếp, parser phải có hợp đồng khác.

### 2.3. Dữ liệu mẫu có thể kiểm tra bằng tay

```text
46 46 4D 31 01 00 03 00
01 E9 03 00 00 EB 00
01 EA 03 00 00 CE FF
01 EB 03 00 00 36 01
```

| Bản ghi | sensorId | Giá trị lưu | Nhiệt độ |
| --- | ---: | ---: | ---: |
| 1 | 1001 | 235 | 23,5 °C |
| 2 | 1002 | -50 | -5,0 °C |
| 3 | 1003 | 310 | 31,0 °C |

Gói có 29 byte. Trung bình cần thu được là `16.5` °C.

Các byte `CE FF` được đọc thành `short` có dấu `-50`. Không chuyển trường nhiệt độ sang số không dấu; chỉ `version`, `count` và `sensorId` cần được mở rộng theo quy tắc unsigned tương ứng.

## 3. Mô tả layout đúng với định dạng

Một `ValueLayout` có kiểu Java dùng để truy cập, kích thước, alignment và byte order. Các layout Java mặc định dùng byte order của máy. Với định dạng quy định little-endian, bạn phải chỉ định rõ thay vì dựa vào máy phát triển. Xem [ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html).

Phần quan trọng của layout bản ghi:

```java
ValueLayout.OfInt leInt =
        ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.LITTLE_ENDIAN);
ValueLayout.OfShort leShort =
        ValueLayout.JAVA_SHORT_UNALIGNED.withOrder(ByteOrder.LITTLE_ENDIAN);

StructLayout recordLayout = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        leInt.withName("sensorId"),
        leShort.withName("temperatureTenths")
);
```

Ở đây `sensorId` bắt đầu tại offset 1, nên cần layout có alignment 1. Trường nhiệt độ cũng dùng alignment 1 vì bản ghi được đóng gói và bước giữa hai bản ghi là 7 byte.

`MemoryLayout.structLayout` không tự chèn padding để mô phỏng compiler C. Nếu dùng layout đòi alignment 4 cho trường ở offset 1, việc tạo struct layout có thể bị từ chối. Việc hạ alignment của toàn bộ struct sau đó không tự sửa alignment của từng thành viên. Quy tắc này được mô tả trong [MemoryLayout.structLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html#structLayout(java.lang.foreign.MemoryLayout...)).

Định dạng tệp được quyết định bởi đặc tả giao thức. Một C `struct` có các trường tương tự có thể có padding và kích thước khác. Vì vậy, bài giải mã dữ liệu trước rồi cấp phát một mảng `double` riêng cho hàm C.

## 4. Hợp đồng của hàm native

Thư viện xuất một hàm C:

```c
int average_temperature(const double *values, int count, double *result);
```

Hợp đồng cụ thể:

| Thành phần | Ý nghĩa |
| --- | --- |
| `values` | Trỏ tới ít nhất `count` phần tử `double` liên tiếp, được căn chỉnh phù hợp. |
| `count` | Số phần tử; phải lớn hơn 0. |
| `result` | Trỏ tới vùng ghi được, đủ chứa một `double`. |
| Giá trị trả về `0` | Thành công; `*result` chứa trung bình. |
| Giá trị trả về `-1` | Một con trỏ là NULL hoặc `count <= 0`; không sử dụng giá trị đầu ra. |
| Thời gian dùng con trỏ | Chỉ trong thời gian hàm chạy; thư viện không lưu con trỏ cho lần dùng sau. |
| Quyền sở hữu | Bên Java cấp phát và giải phóng; hàm C không gọi `free`. |

Kiểm tra NULL và `count` trong C không xác minh được kích thước thực của buffer. Bên gọi vẫn phải bảo đảm cấp phát đủ số phần tử. Khi con trỏ đã được đưa vào C, những phép đọc/ghi trong C không trở thành các thao tác có kiểm tra biên của `MemorySegment`.

### 4.1. Mã C đầy đủ: sensor.c

```c
#include <stddef.h>
#include <limits.h>
#include <float.h>

#if defined(_WIN32)
#define SENSOR_API __declspec(dllexport)
#else
#define SENSOR_API __attribute__((visibility("default")))
#endif

_Static_assert(CHAR_BIT == 8, "This exercise requires 8-bit bytes");
_Static_assert(sizeof(int) == 4, "This exercise requires 32-bit int");
_Static_assert(sizeof(double) == 8, "This exercise requires 64-bit double");
_Static_assert(FLT_RADIX == 2 && DBL_MANT_DIG == 53,
               "This exercise requires binary double precision");

SENSOR_API int average_temperature(
        const double *values,
        int count,
        double *result) {
    if (values == NULL || result == NULL || count <= 0) {
        return -1;
    }

    double sum = 0.0;
    for (int i = 0; i < count; i++) {
        sum += values[i];
    }

    *result = sum / count;
    return 0;
}
```

Hàm ngắn để tập trung vào cơ chế liên kết và vòng đời bộ nhớ. Trong một hệ thống thực, lợi ích của việc gọi C đến từ thư viện hoặc thuật toán đang có; thao tác tính trung bình đơn giản này cũng có thể viết trực tiếp bằng Java.

### 4.2. Biên dịch thư viện

**Windows, dùng MSVC:** mở terminal phát triển đã chọn toolchain x64 và cài thành phần C/C++ cần thiết.

```powershell
cl /nologo /std:c11 /TC /O2 /W4 /LD sensor.c /link /OUT:sensor.dll
```

Tệp `.c` được biên dịch như C; `/std:c11` cho phép dùng `_Static_assert`. Tham khảo [chuẩn ngôn ngữ của MSVC](https://learn.microsoft.com/en-us/cpp/build/reference/std-specify-language-standard-version) và [cách xuất hàm từ DLL](https://learn.microsoft.com/en-us/cpp/build/reference/dll-build-a-dll?view=msvc-170).

**Linux, dùng GCC:**

```bash
gcc -std=c11 -O2 -Wall -Wextra -fPIC -shared sensor.c -o libsensor.so
```

`-fPIC` tạo mã độc lập vị trí để dùng trong thư viện chia sẻ. Tham khảo [GCC: Code Generation Options](https://gcc.gnu.org/onlinedocs/gcc/Code-Gen-Options.html) và [GCC: Link Options](https://gcc.gnu.org/onlinedocs/gcc/Link-Options.html).

**macOS, dùng Apple Clang:**

```bash
clang -std=c11 -O2 -Wall -Wextra -dynamiclib sensor.c -o libsensor.dylib
```

Chọn kiến trúc build khớp với JVM, đặc biệt khi máy có thể chạy cả môi trường ARM64 và x64. Cách driver Clang xử lý thư viện động Darwin được thể hiện trong [mã nguồn toolchain Darwin của LLVM](https://github.com/llvm/llvm-project/blob/main/clang/lib/Driver/ToolChains/Darwin.cpp).

## 5. Từ chữ ký C đến downcall trong Java

### 5.1. FunctionDescriptor

Với các giả định ABI đã nêu, descriptor của hàm là:

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,  // giá trị trả về: int
        ValueLayout.ADDRESS,   // const double *values
        ValueLayout.JAVA_INT,  // int count
        ValueLayout.ADDRESS    // double *result
);
```

Đối số đầu tiên của `FunctionDescriptor.of` là layout của giá trị trả về. Những đối số còn lại là layout của tham số theo đúng thứ tự. Với hàm C trả `void`, dùng `FunctionDescriptor.ofVoid`. Xem [FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html).

Descriptor trên tạo kiểu gọi Java tương ứng:

```text
(MemorySegment, int, MemorySegment) -> int
```

Dấu `const` của tham số C không được descriptor tự kiểm tra. Đây là phần hợp đồng mà mã C phải tôn trọng.

Nếu đổi thư viện, hãy đối chiếu header và ABI thực tế. C `long` không có cùng kích thước trên mọi hệ điều hành; không thay mọi kiểu số nguyên C bằng `JAVA_LONG`. `Linker.canonicalLayouts()` cho phép tra layout chuẩn theo ABI, gồm các kiểu như `int`, `long`, `double` và `size_t`. Xem [Linker: mô tả chữ ký C](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).

### 5.2. SymbolLookup và MethodHandle

```java
SymbolLookup symbols = SymbolLookup.libraryLookup(libraryPath, arena);
MemorySegment symbol = symbols.find("average_temperature")
        .orElseThrow(() -> new IllegalStateException("Missing symbol"));
MethodHandle average = Linker.nativeLinker()
        .downcallHandle(symbol, descriptor);
```

Dùng đường dẫn tuyệt đối giúp xác định thư viện cần tải. `libraryLookup(Path, Arena)` gắn vòng đời lookup và thư viện với arena được truyền vào. Không giữ handle để gọi sau khi arena đó đã đóng. Xem [SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).

`invokeExact` yêu cầu kiểu đối số và kiểu trả về tại điểm gọi khớp chính xác với kiểu của handle:

```java
int status = (int) average.invokeExact(values, count, result);
```

Ở đây `values` và `result` được khai báo là `MemorySegment`, `count` là `int`, và kết quả được ép sang `int`. Đổi `count` thành `long` hoặc bỏ cách nhận giá trị trả về có thể dẫn tới `WrongMethodTypeException`. Xem [MethodHandle.invokeExact](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandle.html#invokeExact(java.lang.Object...)).

## 6. Mã Java đầy đủ

Lưu phần sau thành `FfmSensorExercise.java`.

Mã hỗ trợ hai cách nhận dữ liệu: dùng gói mẫu nếu chỉ truyền đường dẫn thư viện, hoặc đọc một tệp nhị phân nếu truyền thêm đường dẫn tệp.

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;
import static java.lang.foreign.ValueLayout.ADDRESS;
import static java.lang.foreign.ValueLayout.JAVA_BYTE;
import static java.lang.foreign.ValueLayout.JAVA_DOUBLE;
import static java.lang.foreign.ValueLayout.JAVA_INT;

public final class FfmSensorExercise {
    private static final ValueLayout.OfShort LE_I16 =
            ValueLayout.JAVA_SHORT_UNALIGNED
                    .withOrder(ByteOrder.LITTLE_ENDIAN);
    private static final ValueLayout.OfInt LE_I32 =
            ValueLayout.JAVA_INT_UNALIGNED
                    .withOrder(ByteOrder.LITTLE_ENDIAN);

    private static final StructLayout HEADER = MemoryLayout.structLayout(
            MemoryLayout.sequenceLayout(4, JAVA_BYTE).withName("magic"),
            LE_I16.withName("version"),
            LE_I16.withName("count")
    );

    private static final StructLayout RECORD = MemoryLayout.structLayout(
            JAVA_BYTE.withName("kind"),
            LE_I32.withName("sensorId"),
            LE_I16.withName("temperatureTenths")
    );

    private static final long VERSION_OFFSET =
            HEADER.byteOffset(groupElement("version"));
    private static final long COUNT_OFFSET =
            HEADER.byteOffset(groupElement("count"));
    private static final long KIND_OFFSET =
            RECORD.byteOffset(groupElement("kind"));
    private static final long ID_OFFSET =
            RECORD.byteOffset(groupElement("sensorId"));
    private static final long TEMPERATURE_OFFSET =
            RECORD.byteOffset(groupElement("temperatureTenths"));

    // 8 + 65_535 * 7; giới hạn của định dạng đã đặc tả.
    private static final int MAX_PACKET_BYTES = Math.toIntExact(
            HEADER.byteSize() + 65_535L * RECORD.byteSize()
    );

    private record Reading(long sensorId, double celsius) {}

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalArgumentException(message);
        }
    }

    private static byte[] samplePacket() {
        return HexFormat.of().parseHex(
                "46464D3101000300"
                + "01E9030000EB00"
                + "01EA030000CEFF"
                + "01EB0300003601"
        );
    }

    private static byte[] readPacket(Path path) throws IOException {
        try (InputStream input = Files.newInputStream(path)) {
            byte[] bytes = input.readNBytes(MAX_PACKET_BYTES + 1);
            require(bytes.length <= MAX_PACKET_BYTES,
                    "Packet exceeds format size limit");
            return bytes;
        }
    }

    private static List<Reading> decode(MemorySegment packet) {
        require(packet.byteSize() >= HEADER.byteSize(), "Truncated header");

        require(packet.get(JAVA_BYTE, 0) == (byte) 'F'
                && packet.get(JAVA_BYTE, 1) == (byte) 'F'
                && packet.get(JAVA_BYTE, 2) == (byte) 'M'
                && packet.get(JAVA_BYTE, 3) == (byte) '1',
                "Invalid magic");

        int version = Short.toUnsignedInt(
                packet.get(LE_I16, VERSION_OFFSET));
        require(version == 1, "Unsupported version: " + version);

        int count = Short.toUnsignedInt(
                packet.get(LE_I16, COUNT_OFFSET));
        require(count > 0, "Empty packet is not supported");

        long expectedBytes = Math.addExact(
                HEADER.byteSize(),
                Math.multiplyExact((long) count, RECORD.byteSize())
        );
        require(packet.byteSize() == expectedBytes,
                "Packet size does not match record count");

        List<Reading> readings = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            long offset = HEADER.byteSize() + (long) i * RECORD.byteSize();
            MemorySegment record = packet.asSlice(offset, RECORD.byteSize());

            int kind = Byte.toUnsignedInt(record.get(JAVA_BYTE, KIND_OFFSET));
            require(kind == 1, "Unsupported kind at record " + i);

            long sensorId = Integer.toUnsignedLong(
                    record.get(LE_I32, ID_OFFSET));
            short tenths = record.get(LE_I16, TEMPERATURE_OFFSET);
            require(tenths >= -400 && tenths <= 1250,
                    "Temperature out of range at record " + i);

            readings.add(new Reading(sensorId, tenths / 10.0));
        }
        return List.copyOf(readings);
    }

    private static double averageInJava(List<Reading> readings) {
        double sum = 0.0;
        for (Reading reading : readings) {
            sum += reading.celsius();
        }
        return sum / readings.size();
    }

    private static double averageInNative(
            Path libraryPath, List<Reading> readings) throws Throwable {
        int count = readings.size();
        require(count > 0 && count <= 65_535, "Invalid count");

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup symbols = SymbolLookup.libraryLookup(libraryPath, arena);
            MemorySegment symbol = symbols.find("average_temperature")
                    .orElseThrow(() -> new IllegalStateException(
                            "Missing native symbol: average_temperature"));

            FunctionDescriptor descriptor = FunctionDescriptor.of(
                    JAVA_INT, ADDRESS, JAVA_INT, ADDRESS);
            MethodHandle average = Linker.nativeLinker()
                    .downcallHandle(symbol, descriptor);

            // Native byte order và alignment phù hợp cho double.
            MemorySegment values = arena.allocate(JAVA_DOUBLE, count);
            MemorySegment result = arena.allocate(JAVA_DOUBLE);

            for (int i = 0; i < count; i++) {
                values.setAtIndex(JAVA_DOUBLE, i, readings.get(i).celsius());
            }

            int status = (int) average.invokeExact(values, count, result);
            if (status != 0) {
                throw new IllegalStateException(
                        "average_temperature returned status " + status);
            }

            double mean = result.get(JAVA_DOUBLE, 0);
            if (!Double.isFinite(mean)) {
                throw new IllegalStateException("Native result is not finite");
            }
            return mean;
        }
    }

    public static void main(String[] args) throws Throwable {
        require(args.length == 1 || args.length == 2,
                "Usage: java FfmSensorExercise <native-library> [packet-file]");

        Path libraryPath = Path.of(args[0]).toAbsolutePath().normalize();
        require(Files.isRegularFile(libraryPath),
                "Native library does not exist: " + libraryPath);

        byte[] bytes = args.length == 2
                ? readPacket(Path.of(args[1]))
                : samplePacket();

        List<Reading> readings = decode(MemorySegment.ofArray(bytes));

        for (Reading reading : readings) {
            System.out.printf(Locale.ROOT, "sensor=%d temperature=%.1f C%n",
                    reading.sensorId(), reading.celsius());
        }

        double javaMean = averageInJava(readings);
        double nativeMean = averageInNative(libraryPath, readings);

        // Ngưỡng đối chiếu của bài tập, đơn vị độ C.
        if (Math.abs(nativeMean - javaMean) > 1e-9) {
            throw new IllegalStateException(
                    "Native mean differs from Java baseline");
        }

        System.out.printf(Locale.ROOT, "javaMean=%.6f C%n", javaMean);
        System.out.printf(Locale.ROOT, "nativeMean=%.6f C%n", nativeMean);
    }
}
```

### 6.1. Vì sao kiểm tra độ dài trước vòng lặp?

Header có thể khai `count = 3` nhưng chỉ còn đủ dữ liệu cho hai bản ghi. Kiểm tra công thức kích thước giúp báo lỗi giao thức rõ ràng trước khi truy cập từng trường.

Các phép tính dùng `long` và `Math.addExact`/`Math.multiplyExact` để giữ ý định kiểm tra số học khi công thức được mở rộng. Riêng định dạng hiện tại bị giới hạn bởi `uint16`, nên kích thước tối đa chỉ là 458.753 byte.

`readPacket` đọc tối đa giới hạn cộng một byte để nhận diện tệp quá lớn. Cách này tránh tải không giới hạn một tệp vào mảng trước khi parser có cơ hội kiểm tra header.

### 6.2. Vì sao dùng asSlice?

Mỗi slice có kích thước đúng bằng một bản ghi. Nhờ đó, các offset của trường luôn được tính từ đầu bản ghi, thay vì trộn lẫn offset gói, offset bản ghi và offset trường.

`asSlice` tạo view dùng chung vùng nhớ; nó không sao chép dữ liệu. Phương thức truy cập kiểm tra biên của segment tương ứng. Xem [MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).

Nếu sau này thay đổi offset một trường, hãy thay layout và lấy offset bằng `byteOffset`; tránh duy trì thêm một bộ hằng số số học không gắn với đặc tả.

### 6.3. Vì sao mảng đưa vào C dùng JAVA_DOUBLE?

Dữ liệu trên đường truyền luôn little-endian, còn các giá trị mà C đọc qua `double *` cần được lưu theo biểu diễn native trên máy đang chạy. Hai lớp biểu diễn này có mục đích khác nhau.

Sau khi giải mã nhiệt độ thành `double`, chương trình dùng `arena.allocate(JAVA_DOUBLE, count)` để cấp phát cả dãy với kích thước và alignment lấy từ layout. Cấp phát một biến đầu ra dùng `arena.allocate(JAVA_DOUBLE)`. Xem [SegmentAllocator.allocate](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html#allocate(java.lang.foreign.MemoryLayout,long)).

Mảng byte ban đầu được bọc bằng `MemorySegment.ofArray` để đọc trong Java. Với downcall thông thường dùng ở đây, các đối số con trỏ được cấp phát thành native segment riêng.

### 6.4. Vì sao đọc result trước khi arena đóng?

`Arena.ofConfined()` phù hợp với luồng gọi đồng bộ trên một thread. Khi arena đóng, các vùng nhớ do arena cấp phát hết hiệu lực. Trả về một giá trị `double` đã đọc giúp kết quả sống độc lập với vùng nhớ native. Xem [Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).

Không đổi thành trả về segment `result` rồi mới đọc nó bên ngoài `try`. Tương tự, không lưu `values`, địa chỉ hàm hoặc handle để dùng sau khối quản lý vòng đời.

Việc hàm C không giữ con trỏ là một phần thiết yếu của thiết kế. Nếu API thực tế dùng con trỏ bất đồng bộ, cần quản lý arena theo vòng đời công việc và đợi native ngừng sử dụng trước khi đóng.

## 7. Biên dịch và chạy chương trình

Biên dịch Java:

```text
javac --release 22 FfmSensorExercise.java
```

Lệnh này kiểm tra mã nguồn dựa trên API Java 22 khi dùng một JDK có hỗ trợ target đó. Không truyền tùy chọn preview.

**Windows:**

```powershell
java --enable-native-access=ALL-UNNAMED -cp . FfmSensorExercise ".\sensor.dll"
```

**Linux:**

```bash
java --enable-native-access=ALL-UNNAMED -cp . FfmSensorExercise ./libsensor.so
```

**macOS:**

```bash
java --enable-native-access=ALL-UNNAMED -cp . FfmSensorExercise ./libsensor.dylib
```

`ALL-UNNAMED` phù hợp với ví dụ chạy trên classpath. Với ứng dụng module hóa, cấp native access cho tên module thực sự gọi các phương thức restricted, ví dụ `--enable-native-access=com.example.sensor`.

Tải thư viện và tạo downcall là các thao tác restricted. Linker không thể tự xác minh descriptor có đúng với chữ ký của symbol trong thư viện hay không. Cấu hình native access phải đi cùng hợp đồng ABI đúng; bật quyền không thay thế bước đối chiếu chữ ký. Xem [hướng dẫn restricted methods của Java hiện đại](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html).

Kết quả mong đợi với gói mẫu:

```text
sensor=1001 temperature=23.5 C
sensor=1002 temperature=-5.0 C
sensor=1003 temperature=31.0 C
javaMean=16.500000 C
nativeMean=16.500000 C
```

`Locale.ROOT` giúp cách in số trong ví dụ giữ dấu chấm thập phân trên các máy có thiết lập ngôn ngữ khác nhau.

Chương trình còn đối chiếu kết quả với phép tính Java theo cùng dãy nhiệt độ. Ngưỡng `1e-9` °C là tiêu chí của bài thực hành; dữ liệu cảm biến chỉ có độ phân giải 0,1 °C. Khi thay thuật toán hoặc miền dữ liệu, cần xác định lại tiêu chí số học theo yêu cầu ứng dụng.

## 8. Chạy với một tệp nhị phân thật

Để tạo đúng dữ liệu mẫu trên Windows, dùng PowerShell:

```powershell
[byte[]] $packetBytes = @(
    0x46, 0x46, 0x4D, 0x31, 0x01, 0x00, 0x03, 0x00,
    0x01, 0xE9, 0x03, 0x00, 0x00, 0xEB, 0x00,
    0x01, 0xEA, 0x03, 0x00, 0x00, 0xCE, 0xFF,
    0x01, 0xEB, 0x03, 0x00, 0x00, 0x36, 0x01
)
$packetPath = Join-Path (Get-Location) 'sample.bin'
[System.IO.File]::WriteAllBytes($packetPath, $packetBytes)
```

Sau đó:

```powershell
java --enable-native-access=ALL-UNNAMED -cp . FfmSensorExercise ".\sensor.dll" ".\sample.bin"
```

Trên hệ điều hành khác, tạo `sample.bin` bằng một công cụ ghi byte nhị phân rồi truyền đường dẫn làm đối số thứ hai. Không lưu chuỗi ký tự hex thành tệp văn bản: 29 byte dữ liệu và một đoạn văn bản biểu diễn hex là hai nội dung khác nhau.

Trong ví dụ, dữ liệu tệp được đọc vào mảng có giới hạn rồi truy cập qua segment. Khi cần xử lý tệp lớn hơn, có thể tìm hiểu `FileChannel.map(..., Arena)`; lúc đó vòng đời mapping và khả năng tệp bị thay đổi cũng trở thành phần của thiết kế.

## 9. Các tình huống cần tự kiểm tra

Các tình huống sau giúp bạn xác nhận hợp đồng của lời giải khi thực hành.

| Thay đổi | Kết quả cần quan sát |
| --- | --- |
| Giữ gói mẫu nguyên vẹn | Đọc ba bản ghi và nhận trung bình 16,5 °C. |
| Chỉ giữ 7 byte đầu | Từ chối do header chưa đủ. |
| Đổi byte đầu từ `46` thành `00` | Từ chối magic không hợp lệ. |
| Đổi version từ `01 00` thành `02 00` | Từ chối version chưa hỗ trợ. |
| Đổi count từ `03 00` thành `00 00` | Từ chối gói rỗng theo quy tắc bài. |
| Khai count là 4 nhưng giữ nguyên 29 byte | Từ chối vì độ dài không khớp. |
| Bỏ một byte cuối gói | Từ chối gói bị cắt. |
| Thêm một byte cuối gói | Từ chối byte thừa. |
| Đổi `kind` đầu tiên thành 2 | Từ chối loại cảm biến chưa hỗ trợ. |
| Đổi nhiệt độ thành `E3 04` tức 1251 | Từ chối vì vượt 125,0 °C. |
| Đổi sensorId đầu tiên thành `FF FF FF FF` | In mã 4294967295, không in -1. |
| Đổi tên symbol trong Java | Báo thiếu symbol, chưa gọi native. |

Riêng kiểm tra mã lỗi C, có thể thử một lời gọi hợp lệ về bộ nhớ nhưng truyền `count = 0`. Kết quả phải là `-1`, và bên Java không đọc ô kết quả. Không thử truyền một số đếm vượt kích thước buffer để tạo lỗi: hàm C trong bài không có thông tin để tự kiểm tra điều đó.

Để quan sát vòng đời arena, có thể cấp phát một segment nhỏ trong một `try (Arena ...)`, đóng arena rồi gọi `get` từ Java; truy cập sẽ thất bại vì segment hết hiệu lực. Thử nghiệm này khác với giữ một con trỏ trong C rồi dùng sau khi vùng nhớ đã được giải phóng.

## 10. Chẩn đoán lỗi theo đúng lớp

| Biểu hiện | Nơi cần kiểm tra |
| --- | --- |
| Không biên dịch được `java.lang.foreign` | Phiên bản JDK và cấu hình target; ví dụ yêu cầu API chính thức từ 22. |
| Không tìm thấy compiler C | Môi trường toolchain; trên Windows cần terminal phát triển có cấu hình phù hợp. |
| Không tải được thư viện dù tệp tồn tại | Kiến trúc, định dạng thư viện, thư viện phụ thuộc và quyền truy cập. |
| Không tìm thấy `average_temperature` | Tên export; đã build như C và đã xuất hàm hay chưa. |
| Nhiệt độ hoặc số bản ghi vô lý | Byte order, vị trí offset và signed/unsigned. |
| Lỗi alignment khi mô tả hoặc đọc bản ghi | Layout thành viên có phù hợp với dữ liệu đóng gói 7 byte hay không. |
| `WrongMethodTypeException` | Kiểu tại `invokeExact`, gồm cả kiểu trả về và kiểu của `count`. |
| Cảnh báo hoặc lỗi liên quan native access | Tùy chọn launcher đã cấp cho đúng module hoặc classpath hay chưa. |
| Truy cập segment sau khi đóng thất bại | Phạm vi arena và vị trí đọc kết quả. |
| Hàm C trả `-1` | Điều kiện lỗi đã đặc tả trong hàm, không phải lỗi tra symbol. |
| JVM lỗi nghiêm trọng trong lời gọi C | Đối chiếu chữ ký, ABI, kích thước buffer và thời gian sống của con trỏ. |

Giữ riêng thông báo lỗi parser và lỗi thư viện giúp tìm nguyên nhân nhanh hơn. Không bắt mọi lỗi rồi trả về trung bình `0.0`, vì `0.0` cũng có thể là một kết quả nhiệt độ hợp lệ.

Mã minh họa dùng `throws Throwable` để thể hiện trực tiếp yêu cầu của `MethodHandle.invokeExact`. Khi đưa vào ứng dụng, nên đóng gói downcall trong một lớp có hợp đồng lỗi rõ ràng, giữ nguyên nguyên nhân lỗi và quản lý arena ở phạm vi phù hợp.

## 11. Bài tập mở rộng có định hướng

1. **Đóng gói parser:** chuyển `decode` thành một thành phần nhận segment và trả dữ liệu Java độc lập với vùng nhớ đầu vào. Giữ quy tắc kiểm tra trước khi gọi native.

2. **Hỗ trợ version 2:** thêm một trường mới vào bản ghi và xây layout riêng theo version. Không đổi kích thước bản ghi version 1 khi vẫn phải đọc dữ liệu cũ.

3. **Tái sử dụng thư viện:** tách arena quản lý thư viện khỏi arena cho từng buffer. Arena của thư viện cần sống lâu hơn tất cả lời gọi dùng handle; arena cho mỗi yêu cầu có thể đóng sau khi lời gọi đồng bộ hoàn tất.

4. **Mô tả một C struct thật:** viết hàm C cung cấp `sizeof`, `_Alignof` và `offsetof` cho struct cần dùng, rồi đối chiếu layout Java. Bài này chuyển từ định dạng lưu trữ cố định sang vấn đề ABI; padding phải được xác minh theo compiler và nền tảng.

5. **Đặt giới hạn tài nguyên của ứng dụng:** ngoài giới hạn của định dạng, quy định số bản ghi tối đa phù hợp với dịch vụ. Kiểm tra ở đầu luồng và trả thông báo có ý nghĩa khi vượt giới hạn.

Sản phẩm hoàn thành của bài thực hành cần gồm đặc tả dữ liệu, parser có kiểm tra đầu vào, thư viện C có hợp đồng rõ, descriptor khớp chữ ký, lời gọi chạy trong vòng đời arena hợp lệ và kết quả số học đối chiếu được bằng dữ liệu mẫu.
