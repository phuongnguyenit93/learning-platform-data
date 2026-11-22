# Vì sao C `long`, `size_t` và con trỏ không mặc nhiên tương ứng với Java `long`

Khi gọi thư viện C từ Java qua JNI hoặc Foreign Function & Memory API (FFM), không thể suy ra kiểu Java chỉ từ tên kiểu C hay từ việc máy đang chạy hệ điều hành 64-bit. `long` của Java, `long` của C, `size_t` và con trỏ phục vụ những mục đích khác nhau; kích thước, dấu, cách truyền tham số và vòng đời dữ liệu được quy định bởi những hợp đồng khác nhau.

**Ý chính:** Java `long` luôn là số nguyên **có dấu 64 bit**; C `long` có kích thước phụ thuộc mô hình dữ liệu/ABI; C `size_t` là số nguyên **không dấu** dành cho kích thước đối tượng; con trỏ là **địa chỉ/tham chiếu đến vùng nhớ native** với các ràng buộc về tính hợp lệ và vòng đời. Trùng số byte trong một môi trường không đồng nghĩa với cùng kiểu hoặc cùng ngữ nghĩa.

## 1. Đọc đúng bốn loại hợp đồng

| Khái niệm | Vai trò | Độ rộng và dấu | Điều cần giữ tại ranh giới Java–C |
| --- | --- | --- | --- |
| Java `long` | Số nguyên của ngôn ngữ Java | Luôn 64 bit, **signed**, từ `-2^63` đến `2^63 - 1` | Giá trị số và phép toán Java có nghĩa cố định trên mọi JVM phù hợp đặc tả |
| C `long` / `long int` | Số nguyên có dấu của C | **Ít nhất 32 bit**; thường 32 hoặc 64 bit tùy ABI | Dùng đúng kích thước, alignment và calling convention của ABI đang gọi |
| C `size_t` | Kiểu kết quả `sizeof`, kích thước cấp phát/buffer, số phần tử | Kiểu **unsigned** do implementation quy định; thường 32/64 bit | Giữ cả độ rộng lẫn ngữ nghĩa unsigned, kiểm tra miền giá trị khi chuyển |
| C `T *` / `void *` | Con trỏ trỏ tới đối tượng/vùng nhớ native | Kích thước biểu diễn phụ thuộc nền tảng; thường 32/64 bit | Truyền như pointer/address; giữ lifetime, alignment, quyền truy cập và nullability |

Không được dùng kết luận “64-bit ⇒ tất cả đều là 8 byte”. CPU, tiến trình, Java primitive và C ABI là các khái niệm riêng. ABI (*Application Binary Interface*) định nghĩa cách C biên dịch kiểu dữ liệu và bố trí/gọi hàm trên tổ hợp hệ điều hành, kiến trúc và trình biên dịch cụ thể.

Trong C, `sizeof(T)` trả số **C byte**; `CHAR_BIT` cho biết số bit trong một byte C (thường là 8 trên các hệ thống được xét ở đây). Trong Java, `Long.SIZE == 64` và `Long.BYTES == 8` là hằng số theo đặc tả.

## 2. Vì sao C `long` khác Java `long`?

C chỉ bảo đảm `sizeof(char) <= sizeof(short) <= sizeof(int) <= sizeof(long) <= sizeof(long long)` theo thứ tự độ rộng phù hợp, đồng thời `long` có miền giá trị ít nhất 32 bit. Các ABI phổ biến chọn các mô hình dữ liệu sau, với số liệu là **byte thông thường 8 bit**:

| Mô hình thường gặp | `int` | C `long` | `size_t` | `void *` | Java `long` |
| --- | ---: | ---: | ---: | ---: | ---: |
| ILP32 (ứng dụng 32-bit phổ biến) | 4 | 4 | 4 | 4 | 8 |
| LP64 (Linux/macOS 64-bit phổ biến) | 4 | 8 | 8 | 8 | 8 |
| LLP64 (Windows 64-bit phổ biến) | 4 | 4 | 8 | 8 | 8 |

Tên gọi LP64 mô tả `long` và pointer rộng 64 bit; LLP64 mô tả `long long` và pointer rộng 64 bit, còn `long` vẫn 32 bit. Đây là **các mô hình phổ biến**, không phải định nghĩa cho mọi hệ C hay mọi loại pointer.

Ví dụ, thư viện native công khai:

```c
long calculate(long value);
```

Trên Linux/x64 LP64, tham số và kết quả `long` thường là 8 byte. Trên Windows/x64 LLP64, chúng thường là 4 byte. Nếu mô tả hàm này bằng một tham số/kết quả Java `long` 8 byte trong FFM trên Windows, mô tả ABI sai. Việc “số Java cũng có tên là long” hoàn toàn không giúp xác định lời gọi native. Tương tự, ép `4294967296L` từ Java vào C `long` 32 bit vượt miền biểu diễn; kết quả của phép chuyển đổi sang kiểu signed C ngoài miền không có giá trị portable được bảo đảm.

### Thực nghiệm C: đo ABI thực tế

Tạo tệp `abi_probe.c` (C99 trở lên):

```c
#include <limits.h>
#include <stddef.h>
#include <stdio.h>

int main(void) {
    printf("CHAR_BIT=%d\n", CHAR_BIT);
    printf("sizeof(int)=%zu\n", sizeof(int));
    printf("sizeof(long)=%zu\n", sizeof(long));
    printf("sizeof(long long)=%zu\n", sizeof(long long));
    printf("sizeof(size_t)=%zu\n", sizeof(size_t));
    printf("sizeof(void*)=%zu\n", sizeof(void *));
    printf("LONG_MAX=%ld\n", LONG_MAX);
    return 0;
}
```

Với GCC hoặc Clang: `cc -std=c11 -Wall -Wextra -o abi_probe abi_probe.c`, rồi `./abi_probe` (trên Windows chạy tệp thực thi tương ứng). Định dạng `%zu` là dành cho một giá trị `size_t`/kết quả `sizeof`; `%ld` dành cho `long`. Không sử dụng `%ld` để in `size_t`.

**Ví dụ đầu ra trên Linux/x64 LP64 thông dụng:**

```text
CHAR_BIT=8
sizeof(int)=4
sizeof(long)=8
sizeof(long long)=8
sizeof(size_t)=8
sizeof(void*)=8
LONG_MAX=9223372036854775807
```

**Ví dụ đầu ra trên Windows/x64 LLP64 thông dụng:**

```text
CHAR_BIT=8
sizeof(int)=4
sizeof(long)=4
sizeof(long long)=8
sizeof(size_t)=8
sizeof(void*)=8
LONG_MAX=2147483647
```

Đây là hai đầu ra **có điều kiện theo ABI**, không phải kết quả cố định cho mọi hệ thống. Biên dịch đúng mục tiêu native mà thư viện sẽ chạy; không dùng kích thước của máy phát triển để suy ra kích thước trên hệ khác.

### Thực nghiệm Java: kích thước cố định, giá trị signed

Tạo `JavaLongProbe.java` (Java 17+):

```java
public class JavaLongProbe {
    public static void main(String[] args) {
        long rawBits = Long.parseUnsignedLong("18446744073709551615");

        System.out.println("int bytes=" + Integer.BYTES);
        System.out.println("long bytes=" + Long.BYTES);
        System.out.println("signed bits=" + rawBits);
        System.out.println("unsigned bits=" + Long.toUnsignedString(rawBits));
    }
}
```

Chạy `javac JavaLongProbe.java` và `java JavaLongProbe`. Kết quả **giống nhau trên các JVM tuân thủ Java 17+**:

```text
int bytes=4
long bytes=8
signed bits=-1
unsigned bits=18446744073709551615
```

Cùng mẫu 64 bit toàn số 1 được Java `long` diễn giải signed là `-1`; phương thức unsigned chỉ **diễn giải lại bit pattern** thành chuỗi số không dấu. Nó không biến kiểu primitive `long` thành một kiểu unsigned mới.

## 3. `size_t`: cùng 8 byte vẫn có thể khác miền giá trị

`size_t` được khai báo qua `<stddef.h>` và là kiểu số nguyên **không dấu** dùng cho `sizeof`, `malloc`, `strlen`, kích thước đối tượng/buffer. Trên một hệ 64-bit thông dụng, `size_t` thường biểu diễn `0 … 2^64-1`, trong khi Java `long` signed biểu diễn `-2^63 … 2^63-1`.

Vì thế, khi native trả về một `size_t` có bit cao nhất bằng 1, đưa cùng 64 bit đó vào Java `long` sẽ cho giá trị **âm nếu nhìn theo signed**. Không được dùng điều kiện `result < 0` để suy ra lỗi native nếu đặc tả hàm C định nghĩa kết quả là `size_t` hợp lệ. Cần đọc contract của API: ví dụ `strlen` không dùng số âm làm mã lỗi, nhưng nhiều API khác dùng `ssize_t` (kiểu signed khác với `size_t`) hoặc sentinel riêng.

Những phép xử lý quan trọng:

- Nếu `size_t` có bề rộng **32 bit** và FFM dùng Java `int` carrier: `Integer.toUnsignedLong(rawInt)` cho giá trị unsigned trong `0 … 2^32-1`.
- Nếu `size_t` có bề rộng **64 bit** và FFM dùng Java `long` carrier: `Long.toUnsignedString(rawLong)`, `Long.compareUnsigned`, `Long.divideUnsigned` hoặc `BigInteger` giúp xử lý/hiển thị miền unsigned. Một số phép tính signed thông thường không còn phù hợp.
- Khi **chuyển kích thước Java xuống native**, kiểm tra giới hạn của kiểu đích và số byte/buffer thực tế. Với API chỉ chấp nhận độ dài không âm trong miền signed Java `long`, `Math.toIntExact` hữu ích nếu đích yêu cầu signed 32 bit; nó **không tự thay thế kiểm tra kiểu unsigned `size_t`**.
- Khi C dùng `size_t` để mô tả số byte, Java phải cấp vùng nhớ đủ kích thước; số học đúng kiểu nhưng đọc vượt vùng vẫn là lỗi bộ nhớ.

Cần phân biệt thêm `ptrdiff_t` (hiệu hai con trỏ hợp lệ, kiểu signed) và `ssize_t` (kiểu signed phổ biến trong POSIX, không phải `size_t`). Trong JNI, `jsize` được định nghĩa là `jint` (signed 32 bit) để biểu diễn độ dài/chỉ số mảng Java; nó **không phải** alias trực tiếp của `size_t`. Vì vậy không đẩy một `size_t` 64-bit bất kỳ vào `jsize` mà bỏ qua kiểm tra miền.

## 4. Con trỏ: địa chỉ và quyền truy cập, không phải số nguyên dài

`void *` hay `char *` biểu thị một vị trí trong không gian địa chỉ của tiến trình và ngữ nghĩa trỏ tới đối tượng. Dù `sizeof(void *) == 8` và `sizeof(long) == 8` trên LP64, C vẫn phân biệt pointer và integer. Pointer còn gắn với:

1. **Null và hợp lệ:** null pointer không trỏ tới đối tượng; một địa chỉ khác null cũng có thể đã hết hiệu lực.
2. **Lifetime/ownership:** vùng được `malloc` cần `free` theo đúng hợp đồng; pointer tới biến stack hết hợp lệ khi phạm vi tồn tại của biến kết thúc; vùng Java heap có thể được JVM quản lý/di chuyển.
3. **Bounds và alignment:** biết địa chỉ chưa đủ để đọc N byte hoặc diễn giải thành `struct`; phải biết kích thước, layout, alignment và phép truy cập được phép.
4. **Kiểu và calling convention:** `void *` (con trỏ dữ liệu) và con trỏ hàm không được mặc nhiên xem là biểu diễn giống nhau trên mọi C implementation.

C có các kiểu `intptr_t` / `uintptr_t` trong `<stdint.h>` **nếu implementation cung cấp** để hỗ trợ biểu diễn integer có thể chứa con trỏ `void *`; ngay cả khi đổi qua lại đúng bit, giá trị số đó không tự bảo đảm vùng nhớ còn sống. `size_t` có mục đích lưu kích thước đối tượng, **không phải** kiểu chuẩn để chuyển con trỏ thành số. `long` của C càng không phải lựa chọn portable cho pointer vì trên LLP64 pointer 64 bit trong khi `long` 32 bit.

Trong FFM Java 22+, con trỏ native thường dùng `ValueLayout.ADDRESS` với carrier `MemorySegment`, thay vì ép vào `ValueLayout.JAVA_LONG`. Khi native trả về địa chỉ, Java cần hợp đồng xác định vùng nhớ được trỏ đến còn tồn tại bao lâu và đọc/ghi trong phạm vi nào. Chọn đúng layout mới là bước đầu; quản lý lifetime và vùng truy cập vẫn bắt buộc.

## 5. Chọn layout theo ABI bằng FFM (Java 22+)

FFM trở thành API chuẩn trong Java 22 (tên gói `java.lang.foreign`). `ValueLayout.JAVA_LONG` mô tả **Java long 8 byte**; `ValueLayout.ADDRESS` mô tả địa chỉ native với bề rộng phụ thuộc nền tảng. `Linker.nativeLinker().canonicalLayouts()` cung cấp layout chuẩn cho các tên kiểu C của **ABI đang chạy** như `long`, `size_t`, `void*`.

Tạo `NativeLayouts.java` và chạy với JDK 22+:

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.util.Map;

public class NativeLayouts {
    public static void main(String[] args) {
        Map<String, MemoryLayout> abi = Linker.nativeLinker().canonicalLayouts();

        System.out.println("Java long=" + ValueLayout.JAVA_LONG.byteSize());
        System.out.println("C long=" + abi.get("long").byteSize());
        System.out.println("C size_t=" + abi.get("size_t").byteSize());
        System.out.println("C void*=" + abi.get("void*").byteSize());
        System.out.println("Address=" + ValueLayout.ADDRESS.byteSize());
    }
}
```

Lệnh: `javac NativeLayouts.java` rồi `java NativeLayouts`. Với JVM x64 thông dụng, các dòng `Java long`, `C size_t`, `C void*` và `Address` là `8`; dòng `C long` thường là `8` trên Linux và `4` trên Windows. Đoạn trên **chỉ khảo sát layout**, không gọi hàm native nên không cần thư viện C tự viết.

Nếu header C công bố hàm giả định:

```c
long count_matches(size_t length, const void *data);
```

thì phần mô tả chữ ký trong Java có thể là:

```java
// Đoạn minh họa, đặt trong mã đã có biến 'abi' ở ví dụ trên.
var descriptor = java.lang.foreign.FunctionDescriptor.of(
        abi.get("long"),
        abi.get("size_t"),
        ValueLayout.ADDRESS
);
```

Đây là **một đoạn minh họa**, không phải chương trình độc lập và chưa thực hiện downcall vì chưa có địa chỉ symbol/thư viện native. Khi xây `MethodHandle` thật, carrier Java của tham số `length` có thể là `int` (native `size_t` 32 bit) hoặc `long` (native `size_t` 64 bit); pointer được truyền bằng `MemorySegment`. Việc `size_t` là unsigned còn phải xử lý ở **tầng giá trị**, ngoài việc chọn byte layout. Đọc header thật, xác định ABI và kiểm tra `MethodHandle.type()` trước khi gọi; khai báo sai function descriptor có thể gây lỗi nghiêm trọng, kể cả crash tiến trình.

**Không dùng `ValueLayout.JAVA_LONG` cho mọi cái tên có chữ “long”, “size” hoặc “pointer”.** Với đối số kiểu C `long` trên Windows/x64, layout ABI tương ứng thường là `ValueLayout.JAVA_INT`; trên Linux/x64 mới thường là `ValueLayout.JAVA_LONG`. Còn con trỏ dữ liệu vẫn dùng `ADDRESS` trên cả hai hệ, dù kích thước C `long` khác nhau.

## 6. JNI: `jlong` không phải C `long`

JNI cố định kiểu primitive tương ứng với Java: `jint` là signed 32 bit, `jlong` là signed 64 bit, `jsize` là typedef của `jint`. Vì thế hàm native được viết theo chữ ký JNI có thể nhận `jlong` 64 bit trên Windows/x64, nhưng **API C khác** mà hàm ấy gọi vẫn có tham số `long` 32 bit.

Giả sử Java truyền giá trị `long requestCount` đến JNI, rồi JNI cần gọi `long process(long count)` của thư viện C. Luồng đúng là:

1. JNI nhận `jlong requestCount` theo chữ ký JNI.
2. Kiểm tra `LONG_MIN <= requestCount <= LONG_MAX` theo `<limits.h>` của **C ABI đích** và xử lý lỗi rõ ràng nếu vượt miền.
3. Sau khi đạt điều kiện, mới chuyển thành C `long` và gọi `process`.
4. Khi trả kết quả, xác định C trả signed `long`, unsigned size hay mã lỗi, rồi chuyển sang kiểu Java theo **ngữ nghĩa** đó.

JNI không tự chuyển mọi C `size_t` thành `jsize`, và `jlong` không phải lời hứa rằng mọi handle/pointer có thể cất trực tiếp trong Java `long`. Một số thư viện chọn dùng số `jlong` làm **opaque native handle**, nhưng đó phải là hợp đồng API riêng: tạo/huỷ handle, nhận biết handle đã đóng, kiểm tra tính hợp lệ và đồng bộ truy cập. Tránh để Java thực hiện số học trên handle như trên một kích thước hoặc địa chỉ thông thường.

## 7. Các lỗi dễ gặp và cách sửa

| Cách viết/suy luận sai | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| “Ứng dụng 64-bit nên C `long` = Java `long`” | Windows/x64 LLP64 dùng C `long` 4 byte | Tra ABI/header; lấy layout chuẩn từ native linker |
| “`size_t` là `long` vì cả hai thường 8 byte” | `size_t` unsigned; C `long` signed và có thể 4 byte | Giữ layout `size_t` và kiểm tra/diễn giải unsigned |
| “`void *` là `long` vì cùng 64 bit” | Pointer có carrier, lifetime, alignment và quyền truy cập khác integer | Dùng pointer/address layout; quản lý vùng native |
| “`jlong` là alias của C `long`” | `jlong` cố định 64 bit, C `long` tùy ABI | Chuyển kiểu có kiểm tra miền tại biên JNI |
| “FFM `JAVA_LONG` biểu diễn mọi giá trị 64-bit” | Carrier signed không biểu diễn trực tiếp miền unsigned `2^63 … 2^64-1` | Dùng unsigned helpers hoặc `BigInteger` theo contract |
| “`sizeof(ptr)` là dung lượng vùng trỏ tới” | `sizeof(ptr)` đo kích thước **biến con trỏ**, không phải buffer | Truyền kích thước riêng; `sizeof(*ptr)` chỉ đo kiểu đối tượng trỏ tới |
| “Chạy được Linux là an toàn Windows” | Header, ABI, calling convention và thứ tự byte có thể khác | Kiểm tra từng native target và kiểm thử đường biên |

Lưu ý riêng về `sizeof`: với `char *p`, `sizeof(p)` là kích thước con trỏ, **không phải** độ dài chuỗi tại `p`; dùng `strlen(p)` chỉ khi `p` trỏ đến chuỗi C null-terminated hợp lệ. Khi truy cập mảng, số **phần tử** khác số **byte**: `sizeof(array) / sizeof(array[0])` chỉ có nghĩa khi `array` thực sự là array ngay tại biểu thức, không phải đã biến thành pointer khi truyền hàm.

## 8. Quy trình thiết kế một API Java ↔ C an toàn

1. **Bắt đầu từ header C thật:** ghi chính xác kiểu trả về/tham số, gồm pointer level, `const`, `size_t`, các kiểu `stdint.h` (như `int64_t`) và hợp đồng ownership/lỗi.
2. **Chốt native target:** hệ điều hành, kiến trúc, ABI, cách biên dịch native library/JVM. Đo kiểu bằng chương trình C hoặc tra tài liệu ABI; không suy từ tên hệ điều hành đơn thuần.
3. **Đổi kiểu theo ý nghĩa:** số signed 64-bit ⇄ Java `long` khi miền tương ứng; C `long` ⇄ layout ABI; `size_t` ⇄ unsigned native size; `T *` ⇄ native address/segment hoặc opaque handle có quản lý.
4. **Kiểm tra miền trước chuyển:** tránh narrowing, sign extension, overflow, số âm giả do diễn giải unsigned; xác minh length tương thích kích thước vùng nhớ thực.
5. **Tôn trọng calling convention:** FFM descriptor hoặc JNI signature phải phản ánh chữ ký native; không giả định layout struct, packing hoặc pointer chỉ từ cùng kích thước scalar.
6. **Kiểm thử theo nền tảng:** ít nhất đối chiếu LP64 và LLP64 nếu hỗ trợ cả Linux và Windows x64; thử giá trị biên `0`, `LONG_MAX`, `2^31`, `2^32` và mẫu bit cao của unsigned (chỉ khi contract có ý nghĩa).
7. **Kiểm thử lifetime:** native có thể giữ pointer sau khi hàm trả về không, ai giải phóng, lúc nào segment hết hiệu lực, xử lý gọi lặp/đóng hai lần thế nào?

Nếu kiểm soát được API C do mình thiết kế, kiểu `int32_t`/`int64_t` (khi được hỗ trợ) giúp nêu rõ **độ rộng số nguyên** hơn `long`; nhưng không thay thế xử lý signedness, layout struct, calling convention hay vòng đời con trỏ. Đừng tự đổi `size_t`/pointer của một thư viện C bên ngoài thành `int64_t` chỉ để khớp Java.

## 9. Tự kiểm tra hiểu bài

**Tình huống A.** Java chạy trên Windows x64, `Long.BYTES == 8`. Hàm C trả `long`. Có dùng `ValueLayout.JAVA_LONG` cho return không? **Không**: với ABI LLP64 thông dụng C `long` là 4 byte, chọn layout được native linker công bố cho `long` (thường `JAVA_INT`).

**Tình huống B.** C trả `size_t` 64-bit với bit pattern `0xFFFFFFFFFFFFFFFF`. Java nhìn kiểu `long` ra `-1`. Có thể kết luận native báo lỗi không? **Không**: nếu contract C trả unsigned size, cùng bit pattern biểu diễn `18446744073709551615`. Phải giải mã theo contract và kiểm tra xem giá trị đó có thực sự hợp lệ trong tình huống cụ thể.

**Tình huống C.** `sizeof(void*) == sizeof(long) == 8` trên Linux x64. Có thể đưa pointer vào Java `long`, rồi xem nó là một vùng nhớ 8 byte an toàn không? **Không**: trùng kích thước không cấp quyền đọc, không chỉ ra số byte được cấp phát và không giữ vùng nhớ còn sống. Phải dùng giao diện con trỏ/handle với bounds và lifecycle xác định.

**Tình huống D.** JNI có tham số `jlong`; có thể chuyển thẳng sang C `long` rồi gọi thư viện C trên mọi nền tảng không? **Không**: kiểm tra miền của C `long` đích trước khi chuyển và xử lý trường hợp ngoài miền.

## Tài liệu đối chiếu

- Oracle Java 22 `Long`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/Long.html
- Oracle Java 22 `Linker`, phần “Describing C signatures” và `canonicalLayouts()`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
- Oracle Java 22 `ValueLayout` và `ADDRESS`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html
- Java Native Interface Specification, primitive types và `jsize`: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/types.html
- C `size_t`: https://cppreference.com/c/types/size_t

**Kết luận kỹ thuật:** Chọn kiểu khi qua biên Java–C dựa vào **ngữ nghĩa + độ rộng + signedness + ABI + lifetime**, tuyệt đối không dựa vào việc hai kiểu cùng tên hoặc cùng số byte trên máy hiện tại.