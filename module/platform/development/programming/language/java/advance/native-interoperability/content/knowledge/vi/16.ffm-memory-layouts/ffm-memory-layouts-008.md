# Dùng canonicalLayouts của Linker để đối chiếu kiểu C của ABI

Khi Java gọi thư viện C qua **Foreign Function & Memory API (FFM)**, bạn phải mô tả đúng kích thước, alignment và kiểu truyền giá trị của mỗi tham số/giá trị trả về trong **ABI** (Application Binary Interface) đang sử dụng. Một nhầm lẫn quen thuộc là xem C `long` luôn tương ứng Java `long` (64 bit). Điều đó đúng trên Linux/x64 theo mô hình LP64, nhưng **không đúng trên Windows/x64** theo LLP64, nơi C `long` thường chỉ có 32 bit.

Từ JDK 22, FFM API ổn định cung cấp:

```java
Map<String, MemoryLayout> layouts =
    Linker.nativeLinker().canonicalLayouts();
```

Đây là **một đoạn trong phương thức Java**, chưa phải chương trình độc lập. `canonicalLayouts()` trả về tập các `MemoryLayout` chuẩn của **ABI native mà JVM hiện tại sử dụng**. Thay vì đoán theo tên kiểu Java hay theo hệ điều hành, ta hỏi `Linker` về C `int`, `long`, `size_t`, `wchar_t` và `void*`, sau đó kiểm tra `byteSize()`, `byteAlignment()` và carrier của layout. Khi cần mức độ tin cậy cao, nên so sánh kết quả ấy với mã C biên dịch **bằng chính toolchain tạo thư viện đích**, dùng `sizeof`, `_Alignof` và `offsetof`.

Bài thuộc nhóm **Bố trí dữ liệu** của Java Advance — native-interoperability. Các phần quan trọng là: nguồn ABI, danh sách tên được bảo đảm, vì sao kiểu unsigned không có layout riêng phổ quát, cách xây `FunctionDescriptor` và `structLayout`, chương trình đối chiếu Java ↔ C, rồi những sai lầm có thể làm downcall sai chữ ký.

> **Phạm vi phiên bản:** Ví dụ sử dụng `java.lang.foreign` ổn định trong **JDK 22 trở lên** (JEP 454). JDK 21 còn dùng FFM preview; Java 17 không có bộ API chuẩn này. Các lệnh minh họa trên **Linux/x86-64**; phép hỏi `canonicalLayouts()` thì dùng được trên những ABI mà native linker hỗ trợ.

## 1. Vì sao "cùng là kiểu C" lại có nhiều cách bố trí?

Một khai báo C:

```c
long calculate(long value);
```

không mô tả hết hợp đồng binary. Để gọi được từ Java, runtime cần biết:

1. **Kích thước** của C `long`: thường 4 hoặc 8 byte.
2. **Alignment** của giá trị: có thể ảnh hưởng layout của `struct` và cách truy cập vùng nhớ.
3. **Cách chuyển tham số/giá trị về** qua register, stack và calling convention.
4. **Quy tắc ABI** cho aggregate, pointer, return-by-value, varargs.
5. **Ký hiệu và calling convention** của thư viện C cụ thể, kể cả compiler flags làm thay đổi layout.

Không thể chỉ nhìn CPU “64 bit” rồi suy ra tất cả C integers đều 64 bit. Java định nghĩa `int` là 32 bit và `long` là 64 bit, còn C dựa vào ABI/implementation. Một số data model hay gặp:

| Data model | `int` C | `long` C | `long long` C | pointer | Ví dụ điển hình |
| --- | ---: | ---: | ---: | ---: | --- |
| ILP32 | 32 bit | 32 bit | 64 bit | 32 bit | Môi trường 32-bit phổ biến |
| LP64 | 32 bit | 64 bit | 64 bit | 64 bit | Linux/x64, macOS/x64 |
| LLP64 | 32 bit | 32 bit | 64 bit | 64 bit | Windows/x64 |

Đây là **mô hình phổ biến**, không thay cho việc đối chiếu ABI cụ thể. Chẳng hạn `wchar_t` thường 4 byte trên Linux/x64 và 2 byte trên Windows/x64, nhưng không nên suy luận điều đó chỉ từ kiểu `char` hay `long`. Data model cũng không nói hết calling convention, alignment tùy compiler hoặc quy tắc của một `struct` đặc biệt.

FFM có một native linker cho tổ hợp **OS + processor hiện tại**. `Linker.nativeLinker()` không phải công cụ mô phỏng ABI khác trên máy đang chạy: nếu JVM là Linux/x64, nó cho biết ABI được runtime đó hỗ trợ, chứ không tự chuyển sang Windows/x64 chỉ vì bạn muốn đọc một DLL.

### 1.1. MemoryLayout và ABI không phải cùng một thứ

`MemoryLayout` mô tả kích thước, alignment, dạng dữ liệu và bố trí trường. `Linker` biết cách sử dụng các layout được hỗ trợ khi tạo method handle gọi native function theo ABI. Hai đối tượng này có trách nhiệm khác nhau:

- `MemoryLayout` trả lời: vùng này có bao nhiêu byte, canh lề như thế nào, field ở offset nào?
- `ValueLayout` là một layout nguyên tử có **Java carrier** như `int.class`, `long.class`, `float.class`, `MemorySegment.class`.
- `FunctionDescriptor` mô tả layout tham số và return của một chữ ký native.
- `Linker` kiểm tra/bố trí lời gọi từ descriptor theo calling convention, đồng thời cung cấp **canonical layouts** làm điểm tựa.

Một descriptor có kích thước phù hợp nhưng sai loại C, sai số tham số hoặc sai calling convention vẫn có thể làm chương trình lỗi nghiêm trọng. FFM không có metadata từ symbol C để chứng minh descriptor bạn viết khớp prototype; **trách nhiệm xác nhận chữ ký native thuộc về người tích hợp**.

## 2. Cách truy cập `canonicalLayouts()`

Các API then chốt:

```java
Linker linker = Linker.nativeLinker();
Map<String, MemoryLayout> canonical = linker.canonicalLayouts();

MemoryLayout cLong = canonical.get("long");
MemoryLayout cSizeT = canonical.get("size_t");
MemoryLayout pointer = canonical.get("void*");
```

Đây là đoạn trong Java method đã import `java.lang.foreign.*` và `java.util.Map`. Tên các key là **tên kiểu C đúng cú pháp theo API**, không phải cú pháp class Java. Ví dụ:

- Đúng: `"long"`, `"long long"`, `"size_t"`, `"void*"`.
- Không phải key được bảo đảm: `"long_long"`, `"java.lang.Long"`, `"sizeT"`, `"void *"` (có dấu cách), `"unsigned long"`.
- Thực tế có thể có key bổ sung tùy native linker; mã portable chỉ nên **phụ thuộc các key được đặc tả bảo đảm**, hoặc kiểm tra presence khi dùng extension.

### 2.1. Mười một key chuẩn được bảo đảm

Javadoc của `Linker` bảo đảm native linker cung cấp canonical layouts cho:

| Key chính xác | Kiểu C mục tiêu | Gợi ý khi chọn layout |
| --- | --- | --- |
| `"bool"` | C `_Bool`/`bool` | Java carrier boolean; không phải pointer hay integer tự chọn |
| `"char"` | C `char` | Mô tả một C char; signedness của plain char do implementation quyết định |
| `"short"` | C `short` | Kích thước và alignment theo ABI |
| `"int"` | C `int` | Không suy từ việc Java cũng có tên `int` |
| `"long"` | C `long` | Đặc biệt khác nhau giữa LP64 và LLP64 |
| `"long long"` | C `long long` | Thường carrier `long` Java trong các ABI phổ biến |
| `"float"` | C `float` | Thường `ValueLayout.JAVA_FLOAT` |
| `"double"` | C `double` | Thường `ValueLayout.JAVA_DOUBLE` |
| `"size_t"` | C `size_t`, kiểu kích thước không dấu | 32 bit hay 64 bit tùy ABI |
| `"wchar_t"` | C `wchar_t` | Độ rộng khác platform, không đồng nhất với Java `char` |
| `"void*"` | C pointer | Được mô tả bằng address layout, Java carrier `MemorySegment` |

Lưu ý: các phép thử chỉ dựa trên giá trị `Map.get(...) != null` khi biết key trong danh sách bảo đảm. Với kiểu C mở rộng hay typedef riêng, phải xem C header, compiler và ABI; **không** tự nhận mọi tên typedef C sẽ xuất hiện trong map.

### 2.2. Map là read-only

`canonicalLayouts()` trả **unmodifiable map**. Bạn có thể đọc nhưng không được dùng `put` để “sửa C long thành 8 byte”. Nếu mapping không phù hợp với binary C thực tế, vấn đề nằm ở **ABI mismatch hoặc library build**, không phải thiếu thao tác chỉnh map.

Mỗi layout là object mô tả. Khi cần tên field trong `struct`, bạn có thể tạo *derived layout* bằng `layout.withName("field")`; điều đó **không sửa map gốc**. Khi cần thay alignment cho dữ liệu packed, phải cân nhắc kỹ vì layout không còn là canonical natural-aligned layout được ABI mặc định hỗ trợ.

### 2.3. Có gì trong từng `MemoryLayout`?

```java
MemoryLayout l = canonical.get("size_t");

long bytes = l.byteSize();
long alignment = l.byteAlignment();

if (l instanceof ValueLayout v) {
    Class<?> carrier = v.carrier();
    System.out.println(carrier.getName());
}
```

Đoạn code minh họa, không phải file độc lập. `byteSize()` và `byteAlignment()` là **số byte**, không phải số bit. `ValueLayout.carrier()` cho biết kiểu Java được dùng khi get/set hoặc khi `MethodHandle` mang giá trị by-value qua native boundary. Ví dụ, C `long` 4 byte thường cần carrier `int.class`, không phải `long.class` dù tên C chứa chữ “long”.

Tương tự, C `void*` dùng `AddressLayout`, carrier `MemorySegment.class`. Chỉ vì pointer ABI có 8 byte không có nghĩa nó nên được mô tả bằng `ValueLayout.JAVA_LONG`; **pointer calling convention và ownership không giống một số nguyên 64 bit**.

## 3. Bảng đối chiếu điển hình, tránh hard-code

Bảng này mô tả **Linux/x86-64 LP64** thông dụng, nơi C compiler sử dụng System V ABI:

| C type | Layout thường tương ứng | Java carrier | Số byte thường gặp |
| --- | --- | --- | ---: |
| `bool` | `ValueLayout.JAVA_BOOLEAN` | `boolean` | 1 |
| `char` | `ValueLayout.JAVA_BYTE` | `byte` | 1 |
| `short` | `ValueLayout.JAVA_SHORT` | `short` | 2 |
| `int` | `ValueLayout.JAVA_INT` | `int` | 4 |
| `long` | `ValueLayout.JAVA_LONG` | `long` | 8 |
| `long long` | `ValueLayout.JAVA_LONG` | `long` | 8 |
| `float` | `ValueLayout.JAVA_FLOAT` | `float` | 4 |
| `double` | `ValueLayout.JAVA_DOUBLE` | `double` | 8 |
| `size_t` | `ValueLayout.JAVA_LONG` | `long` | 8 |
| `wchar_t` | Thường một integer layout 4 byte | `int` | 4 |
| `void*` | `ValueLayout.ADDRESS` | `MemorySegment` | 8 |

Bảng này **không phải giả định được phép đưa thẳng vào mọi chương trình**. Trên Windows/x64 LLP64, C `long` thường là 4 byte (carrier `int`), trong khi `size_t` và C pointer thường là 8 byte. `wchar_t` thường 2 byte và khác Java `char` về ý nghĩa ABI/encoding. Nếu bạn đang liên kết một thư viện C được build bằng compiler với chế độ packing/ABI khác, kết quả còn có thể khác dự tính.

Lời khuyên lập trình là **lấy map và kiểm tra trên runtime đích**:

```java
MemoryLayout cLong = linker.canonicalLayouts().get("long");
System.out.println("C long bytes=" + cLong.byteSize());
```

Hãy để runtime nói con số thật, thay vì viết:

```java
// Cách viết không portable: mặc định C long = Java long.
FunctionDescriptor wrong = FunctionDescriptor.of(
    ValueLayout.JAVA_LONG, ValueLayout.JAVA_LONG);
```

Hai đoạn trên là minh họa; đoạn thứ hai **có thể sai ABI** nếu prototype native dùng C `long` ở môi trường LLP64. Khi descriptor không khớp, runtime không thể suy ra từ symbol C để tự sửa cho bạn.

## 4. Carrier khác signedness và khác đối tượng Java

### 4.1. C unsigned vẫn có thể dùng một signed Java carrier

C có `unsigned char`, `unsigned int`, `unsigned long`, `size_t`; Java không có các kiểu primitive unsigned tương ứng với đầy đủ miền giá trị. Canonical layout thường dùng **cùng dạng lưu trữ/calling convention** với kiểu signed cùng độ rộng. Nhưng Java vẫn diễn giải `byte/int/long` là signed.

Ví dụ về bit pattern khi ABI của C `unsigned int` là 32 bit:

```java
int raw = -1; // Cùng 32 bit toàn giá trị 1 khi nhìn bit-level.
long unsigned = Integer.toUnsignedLong(raw);

System.out.println(unsigned); // 4294967295
```

Đây là đoạn Java method. Giá trị `-1` Java và `4294967295` là hai cách diễn giải **cùng bit pattern 32 bit**, không phải hai cách bố trí bộ nhớ khác nhau. Với C `size_t` 32 bit, `Integer.toUnsignedLong` giúp hiển thị chiều dài lớn hơn `Integer.MAX_VALUE` dưới dạng số dương Java `long`.

Với C `size_t` 64 bit, Java carrier thường là `long`. Khi bit cao = 1, giá trị Java `long` có thể âm; dùng `Long.toUnsignedString(value)` hoặc `Long.compareUnsigned(...)` khi cần hiển thị/so sánh unsigned 64 bit. Không dùng `Math.abs` để “đổi unsigned” vì `Long.MIN_VALUE` vẫn là số âm và toàn miền 64 bit không thể biểu diễn bằng Java signed long dương.

Một hàm C nhận `size_t length` cần thêm kiểm tra nghiệp vụ: `length` là số byte, không nhất thiết bằng Java `String.length()` (số UTF-16 code units). Nếu nhận byte buffer, đảm bảo độ dài không vượt `MemorySegment.byteSize()` và không làm native code đọc ngoài phạm vi.

### 4.2. C `char` và `wchar_t` không phải Java `char`

- C `char` thường là đơn vị byte 8 bit; signedness của **plain `char`** phụ thuộc implementation.
- Java `char` là **UTF-16 code unit 16 bit không dấu**; không tự dùng nó làm carrier của C `char`.
- C `wchar_t` có kích thước và encoding phụ thuộc hệ điều hành/toolchain. Nó có thể 2 byte hoặc 4 byte, nhưng **không cam kết cùng semantic encoding** với Java `char`.
- Với UTF-8/C string API, truyền `MemorySegment` chứa bytes theo encoding đã thỏa thuận và NUL terminator khi C API yêu cầu.
- Với wide-character API, phải làm rõ encoding và kích thước `wchar_t` thực tế; không copy trực tiếp `char[]` Java rồi coi đó là `wchar_t[]` portable.

Canonical layout giúp định dạng **nhị phân** đúng ABI, không tự động giải quyết **ngữ nghĩa chuỗi ký tự**.

### 4.3. Pointer khác `long`

C `void*`, `char*`, `struct Foo*` được mô tả bằng address layout, carrier `MemorySegment`. Ví dụ:

```java
MemoryLayout pointer = linker.canonicalLayouts().get("void*");
if (!(pointer instanceof AddressLayout)) {
    throw new IllegalStateException("Unexpected pointer layout");
}
```

Dù `byteSize()` của pointer bằng 8, bạn không nên đổi nó thành `JAVA_LONG` trong `FunctionDescriptor`. Khi pointer trả về từ C, Java `MemorySegment` nhận address nhưng **không tự biết độ dài vùng nhớ đích**. Bạn phải có contract về bounds, ownership, alignment, liveness và lúc nào C được phép free. Một pointer không hợp lệ có thể gây crash ngay cả khi descriptor dùng đúng `AddressLayout`.

## 5. Chương trình Java 22+ hoàn chỉnh: in layout theo ABI và dựng struct

Để tránh kết luận bằng cảm giác, ta viết chương trình Java hỏi `canonicalLayouts()` của runtime hiện tại, in **11 loại C bắt buộc**, rồi dựng một `struct` có các trường C `char`, `long` và `size_t`. Chương trình **không gọi native function** nên không cần thư viện C hay quyền restricted native access để chỉ kiểm tra các layout.

Cấu trúc C cần mô phỏng:

```c
typedef struct AbiRecord {
    char tag;
    long count;
    size_t bytes;
} AbiRecord;
```

Đây là khai báo C minh họa; ở mục tiếp theo có file C hoàn chỉnh để in `sizeof`, `_Alignof` và `offsetof` của struct thật.

### 5.1. File `AbiLayoutsDemo.java`

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.StructLayout;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class AbiLayoutsDemo {
    private static final String[] C_TYPES = {
        "bool", "char", "short", "int", "long", "long long",
        "float", "double", "size_t", "wchar_t", "void*"
    };

    private AbiLayoutsDemo() {}

    private static MemoryLayout require(
        Map<String, MemoryLayout> abi, String type) {

        MemoryLayout layout = abi.get(type);
        if (layout == null) {
            throw new IllegalStateException(
                "Missing canonical layout: " + type);
        }
        return layout;
    }

    private static long padTo(long offset, long alignment) {
        return (alignment - (offset % alignment)) % alignment;
    }

    private static StructLayout abiRecordLayout(
        Map<String, MemoryLayout> abi) {

        String[] types = {"char", "long", "size_t"};
        String[] names = {"tag", "count", "bytes"};

        List<MemoryLayout> members = new ArrayList<>();
        long offset = 0;
        long maxAlign = 1;

        for (int i = 0; i < types.length; i++) {
            MemoryLayout field = require(abi, types[i])
                .withName(names[i]);
            long align = field.byteAlignment();
            long padding = padTo(offset, align);

            if (padding > 0) {
                members.add(MemoryLayout.paddingLayout(padding));
            }
            members.add(field);

            offset += padding + field.byteSize();
            maxAlign = Math.max(maxAlign, align);
        }

        long trailing = padTo(offset, maxAlign);
        if (trailing > 0) {
            members.add(MemoryLayout.paddingLayout(trailing));
        }

        return MemoryLayout.structLayout(
            members.toArray(MemoryLayout[]::new));
    }

    public static void main(String[] args) {
        Linker linker = Linker.nativeLinker();
        Map<String, MemoryLayout> abi = linker.canonicalLayouts();

        System.out.printf("%-10s %4s %5s%n",
                          "C type", "size", "align");

        for (String type : C_TYPES) {
            MemoryLayout layout = require(abi, type);
            System.out.printf("%-10s %4d %5d%n",
                              type,
                              layout.byteSize(),
                              layout.byteAlignment());
        }

        StructLayout record = abiRecordLayout(abi);

        System.out.printf("record-size=%d%n",
                          record.byteSize());
        System.out.printf("record-align=%d%n",
                          record.byteAlignment());

        for (String name : new String[] {
                "tag", "count", "bytes"}) {
            long offset = record.byteOffset(
                PathElement.groupElement(name));
            System.out.printf("offset-%s=%d%n", name, offset);
        }
    }
}
```

Đây là **file Java hoàn chỉnh**. Mỗi dòng bảng in `byteSize/byteAlignment` do chính native linker cung cấp, không hard-code theo OS. Không dùng `Map.entrySet()` để in tất cả key, bởi ngoài 11 key bắt buộc, thứ tự và tập các key bổ sung có thể khác JVM. Mảng `C_TYPES` cố định giúp kết quả có thứ tự rõ ràng để so với output C.

Phần dựng `AbiRecord` sử dụng các layout C **theo ABI hiện tại**. Nó tính padding cần thiết trước mỗi field theo alignment của field, rồi thêm trailing padding để kích thước struct là bội số của max alignment. Chẳng hạn trên Linux/x64, `char tag` chiếm byte 0, `long count` cần alignment 8 nên có 7 byte padding, `size_t bytes` ở offset 16, struct có 24 byte. Trên Windows/x64, C `long` thường 4 byte nên offset `count` là 4 và `bytes` là 8, tổng struct 16 byte.

**Quan trọng:** `MemoryLayout.structLayout(...)` **không tự chèn padding giúp bạn**; nếu các members không aligned, nó có thể báo lỗi. Việc tính alignment ở mã trên áp dụng cho struct **bình thường**, không có `#pragma pack`, bit-fields hay extension khác. Một ABI phức tạp có thể có thêm quy tắc về aggregate và argument passing; nhất thiết đối chiếu C compiler.

## 6. Chương trình C11 hoàn chỉnh: `sizeof`, `_Alignof` và `offsetof`

Mã C sau được biên dịch bằng toolchain native để đo **chính ABI mà library dùng**. Thực tế production nên dùng compiler, target triple và packing options khớp với thư viện C cần tích hợp.

### 6.1. File `abi_probe.c`

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <wchar.h>

typedef struct AbiRecord {
    char tag;
    long count;
    size_t bytes;
} AbiRecord;

#define PRINT_TYPE(label, type) \
    printf("%-10s %4zu %5zu\n", \
           label, sizeof(type), (size_t)_Alignof(type))

int main(void) {
    printf("%-10s %4s %5s\n",
           "C type", "size", "align");

    PRINT_TYPE("bool", bool);
    PRINT_TYPE("char", char);
    PRINT_TYPE("short", short);
    PRINT_TYPE("int", int);
    PRINT_TYPE("long", long);
    PRINT_TYPE("long long", long long);
    PRINT_TYPE("float", float);
    PRINT_TYPE("double", double);
    PRINT_TYPE("size_t", size_t);
    PRINT_TYPE("wchar_t", wchar_t);
    PRINT_TYPE("void*", void *);

    printf("record-size=%zu\n", sizeof(AbiRecord));
    printf("record-align=%zu\n",
           (size_t)_Alignof(AbiRecord));
    printf("offset-tag=%zu\n", offsetof(AbiRecord, tag));
    printf("offset-count=%zu\n", offsetof(AbiRecord, count));
    printf("offset-bytes=%zu\n", offsetof(AbiRecord, bytes));

    return 0;
}
```

`sizeof(type)` và `_Alignof(type)` là toán tử C11 trả về đơn vị **byte**; `offsetof(structType, member)` đo offset byte từ đầu struct tới field. Header `<stddef.h>` cung cấp `size_t`/`offsetof`, `<stdbool.h>` cho alias `bool` trong C11, `<wchar.h>` cung cấp `wchar_t`.

Macro `PRINT_TYPE` chỉ rút gọn in bảng; mỗi lần dùng đều truyền một **C type** hợp lệ, kể cả `long long` và `void *`. Không dùng một `unsigned long` label để tuyên bố có key canonical riêng: unsigned và signed có thể dùng cùng layout nhưng khác diễn giải miền giá trị.

### 6.2. Biên dịch và so sánh trên Linux

Cần **JDK 22+** (lệnh `javac` và `java` cùng một JDK) cùng GCC hoặc Clang hỗ trợ C11.

```bash
javac AbiLayoutsDemo.java
cc -std=c11 -Wall -Wextra -Wpedantic \
   abi_probe.c -o abi_probe

java AbiLayoutsDemo
./abi_probe
```

Với **Linux/x86-64 thông dụng, GCC/Clang theo System V LP64 ABI**, hai chương trình dự kiến in **cùng một stdout** như sau. Đây là output minh họa cho môi trường đã chỉ định, **không phải hằng số mọi platform**:

```text
C type     size align
bool          1     1
char          1     1
short         2     2
int           4     4
long          8     8
long long     8     8
float         4     4
double        8     8
size_t        8     8
wchar_t       4     4
void*         8     8
record-size=24
record-align=8
offset-tag=0
offset-count=8
offset-bytes=16
```

Điểm cần đọc từ output:

- `long` có size 8, `size_t` có size 8, pointer size 8 → chúng **cùng kích thước** nhưng vẫn là những loại C khác nhau về signedness/semantics.
- `wchar_t` 4 byte trong môi trường này; không lấy số 4 để áp dụng cho Windows.
- `record-size=24` vì có padding sau `char tag`, và `offset-count=8` theo alignment của `long`.
- Kết quả Java và C phải khớp về **kích thước, alignment, field offset** khi thật sự dùng cùng ABI. Nếu không khớp, đừng bỏ qua mà dùng descriptor; cần điều tra compiler flags, architecture và chính thư viện đích.

Trong Bash, có thể đối chiếu byte-for-byte mà không cần tạo file trung gian:

```bash
diff -u <(java AbiLayoutsDemo) <(./abi_probe)
```

Nếu hai kết quả giống nhau, `diff` không in gì và trả exit code 0. Trên một ABI khác, **cả hai output có thể khác ví dụ Linux** nhưng vẫn khớp nhau; hãy so sánh Java với C tại đúng môi trường đích, không so với bảng cố định.

### 6.3. Sai khác phải được xử lý thế nào?

Giả sử Java in `long=8` nhưng C probe in `long=4`. Điều đó cho thấy ít nhất một giả định đang sai: có thể Java chạy 64-bit Linux LP64 nhưng C biên dịch theo 32-bit ABI, hoặc bạn đã biên dịch C cho một target khác. Không cố “ép” Java dùng `JAVA_LONG` chỉ vì có tên `long`.

Thử kiểm tra:

1. `java -version`, `javac -version` và kiến trúc JVM thực sự.
2. `cc -v` hoặc target triple; compiler/linker flags như `-m32`, `-m64`, ABI variants.
3. C header mà library sử dụng có typedef, alignment attributes, `#pragma pack` hay macro thay đổi struct không.
4. Thư viện binary đang load là bản x86-64/ARM64/x86-32 nào, có cross-compile hoặc compatibility mode không.
5. Java FFM linker được tạo trong **chính JVM dùng để chạy ứng dụng** hay chỉ được hỏi từ một JVM khác.

Chỉ sau khi xác nhận cùng ABI và cùng phiên bản header/compiler cần mới dùng kết quả làm căn cứ cho FFM descriptor của production.

## 7. Từ canonical layout đến `FunctionDescriptor` chính xác

Giả sử C header khai báo:

```c
size_t strlen(const char *s);
```

Đầu vào là pointer tới C string có NUL terminator; return là **C `size_t`**, không phải “Java long” theo định nghĩa cố định.

Một cách viết theo ABI hiện tại:

```java
Linker linker = Linker.nativeLinker();
Map<String, MemoryLayout> abi = linker.canonicalLayouts();

MemoryLayout cSizeT = abi.get("size_t");
MemoryLayout cPointer = abi.get("void*");

FunctionDescriptor fd = FunctionDescriptor.of(
    cSizeT, cPointer);
```

Đây là **đoạn Java trong method**; cần import `java.lang.foreign.*` và `java.util.Map`. `FunctionDescriptor.of(returnLayout, argumentLayouts...)` dùng canonical layout của C return và pointer param. Còn `FunctionDescriptor.ofVoid(...)` được dùng khi native function trả C `void`.

Một pointer thực sự là `const char*` thì layout vẫn có thể dùng address layout của `void*` cho mục đích gọi theo ABI, nhưng **constness, kích thước chuỗi, encoding, NUL và quyền sở hữu không tự sinh ra từ layout**. Bạn phải truyền `MemorySegment` hợp lệ, không sửa dữ liệu qua pointer chỉ vì API Java cho phép ghi.

### 7.1. Đừng biến `size_t` thành `JAVA_LONG` ở mọi platform

Trên hệ thống 64-bit thông dụng, `size_t` thường 8 byte, Java carrier `long.class`. Trên hệ thống 32-bit, `size_t` có thể 4 byte, carrier `int.class`. Downcall `MethodHandle` sẽ có type theo descriptor.

Mã giả minh họa ý tưởng:

```java
MemoryLayout layout = abi.get("size_t");
if (layout instanceof ValueLayout value) {
    Class<?> carrier = value.carrier();
    // Nếu carrier == long.class -> invokeExact trả long.
    // Nếu carrier == int.class  -> invokeExact trả int.
}
```

Mã thực tế ở phần 8 chọn nhánh dựa trên carrier, thay vì gọi `invokeExact` với kiểu return sai. `MethodHandle.invokeExact` yêu cầu static Java method type **trùng khớp tuyệt đối**; một nhánh cast sang `long` trong lúc handle trả `int` có thể gây `WrongMethodTypeException`. Với native link error ở mức C, sai descriptor còn nghiêm trọng hơn lỗi Java type check thông thường.

### 7.2. Mô tả struct bằng canonical fields

Nếu C nhận:

```c
void consume_record(const struct AbiRecord *r);
```

Cần mô tả pointer bằng `AddressLayout` (thường từ `"void*"`), dữ liệu của `AbiRecord` bằng `StructLayout` với field offsets đã kiểm tra. Bạn có thể sử dụng `AddressLayout.withTargetLayout(recordLayout)` khi muốn gắn thông tin vùng đích để hỗ trợ việc thao tác pointer theo FFM API.

Tuy nhiên:

- `withTargetLayout` **không xác minh** C pointer thực sự trỏ tới vùng có kích thước/loại như vậy.
- Pointer đọc từ native memory phải có lifetime hợp lệ; nếu C đã free vùng đích, một Java layout đúng vẫn không cứu được dangling pointer.
- Với C function **truyền struct by value**, ABI có thể có quy tắc đặc biệt về register/stack. Không đơn giản thay `struct` bằng pointer hay ngược lại.
- FFM yêu cầu các layout cho downcall thuộc tập **supported** của linker; một `structLayout` có padding sai hoặc alignment lạ có thể bị từ chối.

## 8. Ví dụ downcall thực sự: `strlen` với C `size_t` của ABI

Phần này **có native call thật**, nên khác chương trình chỉ xem layout ở phần 5. Nó dành cho **Linux/x86-64 có `strlen` trong default symbol lookup**, JDK 22+, và được cấp quyền native access.

### 8.1. File `CanonicalStrlenDemo.java`

```java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.util.Map;

public final class CanonicalStrlenDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        Map<String, MemoryLayout> abi = linker.canonicalLayouts();

        MemoryLayout returnLayout = abi.get("size_t");
        MemoryLayout pointerLayout = abi.get("void*");

        if (!(returnLayout instanceof ValueLayout sizeT)
                || !(pointerLayout instanceof AddressLayout)) {
            throw new IllegalStateException(
                "Unexpected canonical layouts");
        }

        MemorySegment symbol =
            linker.defaultLookup().find("strlen").orElseThrow();

        FunctionDescriptor signature =
            FunctionDescriptor.of(sizeT, pointerLayout);

        MethodHandle strlen =
            linker.downcallHandle(symbol, signature);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment text = arena.allocateFrom("Hello");

            if (sizeT.carrier() == long.class) {
                long n = (long) strlen.invokeExact(text);
                System.out.println("strlen(Hello)="
                                   + Long.toUnsignedString(n));
            } else if (sizeT.carrier() == int.class) {
                int n = (int) strlen.invokeExact(text);
                System.out.println("strlen(Hello)="
                                   + Integer.toUnsignedLong(n));
            } else {
                throw new IllegalStateException(
                    "Unsupported size_t carrier: "
                        + sizeT.carrier());
            }
        }
    }
}
```

Đây là **file Java hoàn chỉnh** sử dụng `Linker` và native library symbol. Nó yêu cầu `strlen` có mặt trong default native lookup; điều này phổ biến trên Linux với libc phù hợp, nhưng không được **bảo đảm** trên mọi OS/JVM. Nếu default lookup không tìm thấy symbol, code ném exception thay vì gọi một địa chỉ tùy đoán.

`arena.allocateFrom("Hello")` tạo C string mã hóa UTF-8 có NUL terminator với bytes sống đến khi arena đóng. Giá trị `strlen` là **số byte trước NUL**, với ASCII `"Hello"` là 5. Nếu chuỗi chứa nhiều ký tự Unicode không phải ASCII, số byte có thể khác Java `String.length()`.

`Long.toUnsignedString` và `Integer.toUnsignedLong` ở đây không thay đổi ABI; chúng chỉ **diễn giải số C không dấu** một cách phù hợp khi Java carrier signed.

### 8.2. Lệnh chạy

```bash
javac CanonicalStrlenDemo.java
java --enable-native-access=ALL-UNNAMED CanonicalStrlenDemo
```

Với runtime Linux phù hợp và symbol lookup thành công, **stdout chính xác**:

```text
strlen(Hello)=5
```

`--enable-native-access=ALL-UNNAMED` cấp quyền native access cho code ở classpath/unnamed module khi sử dụng các FFM restricted methods như `downcallHandle`. Ở ứng dụng có named JPMS module, phải cấp quyền phù hợp cho module đó theo JDK. Chỉ đọc `canonicalLayouts()` và `byteSize()` như chương trình ở phần 5 **không yêu cầu phải gọi native function**, và thường không cần flag này.

**Chú ý quan trọng:** FFM không thể kiểm tra địa chỉ `strlen` có thực sự là function prototype bạn khai báo trong `FunctionDescriptor` hay không. Nếu lấy sai symbol hoặc truyền descriptor sai, kết quả có thể không xác định hoặc làm JVM crash. Không lấy tên C function trên mạng rồi tự đoán ABI/descriptor cho binary nội bộ chưa được xác minh.

## 9. So sánh với C struct và hiểu padding thực tế

Hãy quay lại ví dụ:

```c
typedef struct AbiRecord {
    char tag;
    long count;
    size_t bytes;
} AbiRecord;
```

Trên Linux/x64 LP64, ý nghĩa thường là:

```text
Byte offset:    0        1..7         8..15         16..23
                +---------+-----------+-------------+
AbiRecord:      | tag (1) | padding 7 | count (8)   |
                +---------+-----------+-------------+
                | bytes (8)                          |
                +------------------------------------+
sizeof(AbiRecord) = 24, alignof(AbiRecord) = 8
offsetof(tag) = 0; offsetof(count) = 8; offsetof(bytes) = 16
```

Sơ đồ mô tả **byte offsets**; đây không phải thứ tự bits của từng field. Khi C `long` giảm xuống 4 byte ở Windows/x64 LLP64, các offsets sẽ khác. Cùng một header có thể tạo ra các struct binaries khác nhau nếu ABI khác nhau.

Nếu bạn tự tạo:

```java
MemoryLayout wrong = MemoryLayout.structLayout(
    abi.get("char").withName("tag"),
    abi.get("long").withName("count"),
    abi.get("size_t").withName("bytes"));
```

thì `MemoryLayout.structLayout` không tự padding; khi field `long` yêu cầu alignment lớn hơn offset 1, layout có thể bị từ chối vì misaligned field. Không sửa bằng việc tùy tiện ép `long.withByteAlignment(1)` nếu C struct không thực sự packed; làm vậy có thể che lỗi và tạo layout không thuộc tập supported của linker.

Cần phân biệt **trailing padding**: một struct có field cuối nhỏ hơn alignment lớn nhất thường có padding cuối để các phần tử trong một C array of structs luôn được aligned. Chỉ tính vị trí trường cuối chưa đủ; phải so sánh `sizeof(CStruct)` với `layout.byteSize()`.

### 9.1. Những trường hợp canonicalLayouts chưa đủ để tự dựng struct

Đặc tả chỉ bảo đảm canonical **scalar/pointer** layouts; nó không sinh tự động toàn bộ:

- `struct`, `union`, C arrays và aggregate nested nhiều tầng.
- Bit-fields, anonymous aggregates, flexible array members.
- `#pragma pack`, `__attribute__((packed))`, compiler-specific alignas/align attributes.
- Platform typedef như `DWORD`, `HANDLE`, `off_t`, `ssize_t`, `time_t` khi không có key chuẩn tương ứng.
- Calling convention cho varargs, return-by-value, function pointer callbacks.
- ABI riêng của compiler/OS/toolchain không trùng JVM native linker.

Với các trường hợp ấy, kiểm tra bằng C `sizeof/_Alignof/offsetof`, đọc header và ABI specification, rồi xây `MemoryLayout`/`FunctionDescriptor` theo hợp đồng thật. Có thể dùng một C shim nhỏ expose các giá trị kiểm tra hoặc chuyển các aggregate phức tạp thành API C ổn định với pointer/size, thay vì truyền struct by value qua FFM nếu không chắc chắn.

## 10. Varargs và default argument promotions

Một ví dụ dễ gây nhầm là C:

```c
int printf(const char *format, ...);
```

C compiler thực hiện **default argument promotions** cho các variadic arguments: `float` thường được promote thành `double`; các integer types nhỏ như `char` và `short` được promote thành `int` hoặc `unsigned int` tùy miền giá trị.

FFM linker không tự thực hiện promotions đó cho bạn. Với `Linker.Option.firstVariadicArg(index)`, bạn cần khai báo các argument layouts của **chữ ký đã specialize**, tương ứng với types thực sự sẽ truyền theo ABI.

Mã minh họa trên Linux/x64 (không phải file Java hoàn chỉnh):

```java
Linker linker = Linker.nativeLinker();
Map<String, MemoryLayout> abi = linker.canonicalLayouts();

FunctionDescriptor formatAndTwoInts = FunctionDescriptor.of(
    abi.get("int"),
    abi.get("void*"),
    abi.get("int"),
    abi.get("int"));

Linker.Option firstVariadic =
    Linker.Option.firstVariadicArg(1);
```

Hai số nguyên variadic đã được mô tả là C `int`. Nếu muốn truyền C `float` thành đối số variadic, phải mô tả dạng được promote (thường C `double`) theo quy tắc C và ABI. Đây là ví dụ về **descriptor**, chưa thực hiện downcall và không truyền format string cụ thể. Đừng dùng `printf` với format do người dùng cung cấp mà không kiểm soát: format string vulnerabilities tồn tại độc lập với FFM.

Không suy ra từ `canonicalLayouts().get("char")` rằng cứ dùng layout của C `char` cho variadic argument mang giá trị `char` là hợp lệ. C ABI nhìn thấy **promoted type** của đối số tại call site.

## 11. Những lỗi phổ biến khi dùng canonicalLayouts

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Hard-code `JAVA_LONG` cho C `long` | Sai trên LLP64 hoặc ABI khác | Dùng `canonicalLayouts().get("long")` |
| Hard-code `JAVA_LONG` cho `size_t` | Sai với `size_t` 32 bit | Lấy key `"size_t"` và xem carrier |
| Gọi `get("void *")` (có space) | Có thể trả `null` | Dùng key chuẩn `"void*"` |
| Giả định key `"unsigned long"` luôn có | Key không được bảo đảm | Dùng signed counterpart layout + xử lý unsigned |
| Thấy C pointer 8 byte rồi dùng `JAVA_LONG` | Sai carrier/calling semantics | `AddressLayout`, carrier `MemorySegment` |
| C `char` tương đương Java `char` | Sai width/encoding | C `char` thường tương ứng byte; hỏi linker |
| C `wchar_t` luôn 2 byte | Sai Linux/x64 thường 4 byte | Hỏi canonical layout và encoding contract |
| Xem `byteSize` là số bit | Struct offsets và ABI sai nghiêm trọng | Tất cả kích thước/alignment API này tính bằng byte |
| Dùng `structLayout` không padding | Alignment/offset sai hoặc bị từ chối | Chèn padding và trailing padding hợp lý |
| Chỉ so sánh kích thước struct, bỏ qua offsets | Hai layout có thể bằng size mà sai field order | So cả `offsetof` từng field |
| Dùng Java signed `int/long` như C unsigned mà không xử lý | Giá trị lớn bị xem là âm | Dùng unsigned conversions và bounds checks |
| Dùng layout chuẩn của JVM cho thư viện cross-compiled ABI khác | FFM gọi sai ABI | Match JVM/toolchain/library ABI hoặc dùng process boundary |
| Đổi alignment bất kỳ để “cho chạy” | Có thể tạo packed layout không đúng C | Theo C header/ABI; đo bằng C probe |
| Truyền pointer còn sống quá ngắn | Dangling pointer, crash | Rõ ownership, Arena scope và native lifetime |
| Cho rằng `Map` có mọi typedef/platform type | Null lookup hoặc suy luận sai | Chỉ dùng 11 key được bảo đảm; kiểm tra extras |
| Gọi `invokeExact` nhận `long` khi handle trả `int` | `WrongMethodTypeException` | Nhánh theo `ValueLayout.carrier()` |
| Dùng canonical layout đúng nhưng sai C prototype | Undefined behavior/crash native | Đối chiếu header, arity và return thật |
| Không kiểm tra variadic promotions | Gọi sai calling convention | Specialize descriptor theo promoted types |
| Mặc định `strlen` luôn có trong default lookup | Không portable mọi OS/VM | Kiểm tra symbol, dùng lookup/library phù hợp |
| Thay đổi compiler packing mà không kiểm tra lại | Struct offsets thay đổi nhưng Java layout giữ cũ | ABI probe trong CI với toolchain production |

## 12. Quy trình ứng dụng vào dự án thực tế

Một workflow an toàn cho Java ↔ C trong một hệ thống có nhiều kiến trúc CPU:

**Bước 1 — Ghi contract từ C header.** Đọc đúng declaration, các typedef, struct definitions, calling convention, ownership contract và compiler/architecture target. Không lập descriptor bằng việc đoán tên.

**Bước 2 — Hỏi linker runtime.** Lấy `Linker.nativeLinker().canonicalLayouts()` rồi chọn key chuẩn cho từng scalar/pointer C type. Dùng `byteSize()`, `byteAlignment()`, `carrier()` để xây descriptor động hoặc chọn đúng nhánh theo platform.

**Bước 3 — Xác nhận C thật.** Biên dịch một C ABI probe với cùng compiler flags và headers dùng cho thư viện native, in `sizeof`, `_Alignof`, `offsetof`. So sánh số đo Java với số đo C, đặc biệt cho `long`, `size_t`, `wchar_t`, pointers và structs.

**Bước 4 — Xây layout aggregate.** Chèn padding rõ ràng, đặt names cho fields, so offsets và total size. Nếu compiler có packing hoặc ABI khác, viết contract riêng thay vì tự giảm alignment tùy tiện.

**Bước 5 — Xây `FunctionDescriptor`.** Chọn đúng return layout, argument layouts, static MethodHandle type, vararg specialization và pointer target nếu cần. Không dùng C unsigned semantics như Java signed semantics mà quên conversions.

**Bước 6 — Quản lý bộ nhớ và an toàn.** Cấp phát `MemorySegment` qua `Arena` hoặc nguồn hợp lệ; giữ segment sống đủ lâu, xử lý out-of-bounds, tránh dangling pointers và memory corruption. Không xem canonical layout như một bộ kiểm chứng quyền sở hữu native memory.

**Bước 7 — Test theo ABI.** Chạy cả probe và downcall smoke test trên Linux/x64, Windows/x64, ARM64 hoặc các target thật sự được hỗ trợ. Lưu artifacts/diagnostics của target, không chỉ CI chạy trên một máy developer.

### 12.1. Bảng kiểm thử nên có trong CI

1. 11 canonical keys đều tồn tại trên native linker hiện tại.
2. Kích thước/alignment từng key khớp C probe cùng target.
3. `long` và `size_t` được kiểm tra riêng, không suy chúng luôn cùng size.
4. Pointer layout có Java carrier `MemorySegment`, không phải `long`.
5. Struct offsets `tag/count/bytes` và total size/alignment khớp C `offsetof/sizeof`.
6. Với unsigned 32 bit, bit pattern 0xFFFFFFFF được Java hiểu đúng là 4294967295 khi ứng dụng cần số dương.
7. Với unsigned 64 bit, hiển thị/comparison dùng unsigned APIs khi bit cao được set.
8. Downcall `strlen("Hello")` trả 5 trên native lookup của target hỗ trợ.
9. Gọi nhầm method type bị test phát hiện trước khi chạy production (không cố gọi sai native prototype để “xem crash thế nào”).
10. Trường hợp C struct có packing/bit-fields không được lặng lẽ xử lý bằng layout dành cho struct bình thường.
11. Trên hệ điều hành khác, symbol lookup và compiler build rules được tách riêng thay vì dùng cứng Linux command.
12. Các lỗi missing symbol, unsupported layout, invalid pointer và resource lifetime được trả status rõ ràng, không bị biến thành dữ liệu hợp lệ.

## 13. Những câu hỏi cần tự trả lời trước khi ship

- Binary C thư viện đang dùng **ABI nào**, được biên dịch bằng compiler/flags nào?
- C `long`, `size_t`, `wchar_t`, `void*` trên target thật có bao nhiêu byte, alignment bao nhiêu?
- Có đang hard-code `JAVA_INT/JAVA_LONG` do trùng tên thay vì dùng canonical C layout không?
- Có dùng đúng key không dấu cách của map, ví dụ `"void*"` và `"long long"`?
- Nếu `Map.get` trả `null` cho một extension type, hệ thống có báo lỗi rõ ràng hay tự fallback nguy hiểm?
- Có kiểm tra `ValueLayout.carrier()` trước khi gọi `MethodHandle.invokeExact` không?
- Với unsigned values, phần business logic có xử lý bit pattern và miền giá trị đúng chưa?
- Với struct C, các offsets, tail padding và alignment đã so với C `offsetof` chưa?
- Có sự khác nhau giữa Windows LLP64, Linux LP64 hoặc target 32-bit nào cần test không?
- Dữ liệu pointer có owner, bounds, writable/read-only và arena lifetime rõ ràng không?
- Downcall descriptor có khớp **đúng C prototype**, số đối số, varargs promotions và calling convention không?
- Có thể chạy ABI probe như một phần CI trên từng architecture/OS được hỗ trợ không?

**Kết luận:** `Linker.nativeLinker().canonicalLayouts()` là nguồn thông tin chuẩn để biết JVM native linker ánh xạ các kiểu C cơ bản thành `MemoryLayout` theo ABI đang chạy. Dùng nó để tránh giả định sai về `long`, `size_t`, `wchar_t` và pointer; sau đó **đối chiếu thực tế bằng C `sizeof/_Alignof/offsetof`** trước khi mô tả struct hay gọi function. Canonical layouts giúp xây contract binary đúng, nhưng **không tự xác minh C header, không thay thế ownership/lifetime, và không loại bỏ rủi ro crash nếu khai báo downcall sai**.

### Tài liệu tham khảo

- [Oracle Java SE 22 — Linker: canonicalLayouts, native ABI, supported layouts](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 22 — MemoryLayout, byteSize, byteAlignment, structLayout, paddingLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle Java SE 22 — ValueLayout và Java carrier](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Oracle Java SE 22 — Arena, native memory lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454)
