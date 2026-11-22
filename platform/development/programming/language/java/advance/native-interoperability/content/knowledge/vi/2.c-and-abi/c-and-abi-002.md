# Kích thước, dấu và giới hạn của kiểu số nguyên trên từng nền tảng (C và ABI)

Trong tương tác Java với mã native, cùng một tên kiểu như **long** có thể chỉ hai miền giá trị khác nhau. Java quy định độ rộng của các kiểu số nguyên nguyên thủy, còn C cho phép các implementation chọn độ rộng theo nền tảng và ABI. Vì vậy một thư viện C chạy đúng trên Linux 64-bit vẫn có thể nhận sai dữ liệu trên Windows 64-bit nếu lập trình viên đồng nhất **C long**, **Java long** và con trỏ.

## 1. Cần phân biệt những khái niệm nào?

- **Kích thước lưu trữ**: **sizeof(T)** trả về số *byte theo định nghĩa của C* dành cho một đối tượng kiểu T; kiểu trả về là **size_t**.
- **Số bit trong một byte C**: **CHAR_BIT** trong **<limits.h>**; chuẩn C yêu cầu ít nhất 8 bit/byte nhưng không buộc mọi hệ thống có byte 8 bit. **sizeof(char)** luôn bằng 1.
- **Độ rộng giá trị**: số bit dùng biểu diễn giá trị; ở những implementation cũ có thể tồn tại bit đệm, nên không nên suy ra mọi giới hạn chỉ từ **sizeof(T) * CHAR_BIT**.
- **Dấu**: signed có thể biểu diễn số âm và dương; unsigned chỉ biểu diễn số không âm, với phép toán modulo theo độ rộng.
- **Giới hạn**: giá trị nhỏ nhất/lớn nhất thực sự được implementation công bố qua các macro như **INT_MIN**, **INT_MAX**, **UINT_MAX**, **LONG_MAX**.
- **ABI (Application Binary Interface)**: thỏa thuận nhị phân về kích thước/độ căn chỉnh kiểu, truyền tham số, giá trị trả về, bố trí cấu trúc và calling convention giữa các thành phần đã biên dịch.

**Điểm then chốt:** máy có CPU 64 bit hoặc tiến trình có con trỏ 64 bit không suy ra **int** hay **long** đều 64 bit.

## 2. Các kiểu số nguyên cơ bản trong C

| Kiểu C | Ý nghĩa | Độ rộng tối thiểu theo C |
| --- | --- | ---: |
| **char**, **signed char**, **unsigned char** | Ba kiểu riêng; signedness của **char** thường phụ thuộc compiler/target | Ít nhất 8 bit |
| **short** / **unsigned short** | Số nguyên ngắn | Ít nhất 16 bit |
| **int** / **unsigned int** | Số nguyên thông dụng | Ít nhất 16 bit |
| **long** / **unsigned long** | Số nguyên dài | Ít nhất 32 bit |
| **long long** / **unsigned long long** | Số nguyên rất dài, từ C99 | Ít nhất 64 bit |

Chuẩn bảo đảm quan hệ kích thước: **sizeof(char) ≤ sizeof(short) ≤ sizeof(int) ≤ sizeof(long) ≤ sizeof(long long)**. Đây là quan hệ *không giảm*, các kiểu có thể cùng kích thước; chuẩn không bảo đảm **long** lớn hơn **int**. Khi không ghi **unsigned**, **short**, **int**, **long** và **long long** mặc định là signed. Riêng **char** không đồng nghĩa với **signed char**: cả ba là các kiểu khác nhau.

Ngoài các kiểu trên còn có **_Bool** (C99; từ C23 có cách viết **bool** như một keyword), kiểu liệt kê (**enum**) và các kiểu số nguyên mở rộng. **_Bool** có giá trị logic 0 hoặc 1, nhưng **sizeof(_Bool)** không được phép suy ra bằng 1 trên mọi target. Kiểu cơ sở và kích thước của **enum**, cách sắp xếp bit-field, kiểu **wchar_t**, cùng các mở rộng như **__int128** không tạo thành một hợp đồng ABI chung cho mọi compiler. C23 còn bổ sung kiểu độ rộng bit **_BitInt(N)**, với mức hỗ trợ phụ thuộc compiler; không dùng chúng như giả định mặc định cho thư viện portable.

## 3. Miền giá trị signed/unsigned

Với một kiểu unsigned có **N bit giá trị**, miền giá trị là **0 .. (2^N − 1)** và kết quả số học unsigned được lấy modulo **2^N**. Với signed hai-bù có **N bit tổng cộng**, miền giá trị là **−2^(N−1) .. 2^(N−1)−1**. Đó là biểu diễn bắt buộc từ C23 và phổ biến trên các máy hiện đại; khi viết C17 cho hệ thống ít gặp, vẫn nên dùng macro giới hạn thực tế thay vì mặc định mọi signed đều hai-bù.

| Độ rộng và dấu | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: |
| signed 8 bit | −128 | 127 |
| unsigned 8 bit | 0 | 255 |
| signed 16 bit | −32.768 | 32.767 |
| unsigned 16 bit | 0 | 65.535 |
| signed 32 bit | −2.147.483.648 | 2.147.483.647 |
| unsigned 32 bit | 0 | 4.294.967.295 |
| signed 64 bit | −9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |
| unsigned 64 bit | 0 | 18.446.744.073.709.551.615 |

Bảng trên dùng số bit đã nêu rõ, **không** khẳng định rằng C **int** luôn 32 bit hay **long** luôn 64 bit. Ví dụ, **long** 32-bit có giới hạn **−2.147.483.648 .. 2.147.483.647**; **long** 64-bit hai-bù có giới hạn **−9.223.372.036.854.775.808 .. 9.223.372.036.854.775.807**.

Các macro đáng dùng trong **<limits.h>** gồm **CHAR_BIT**, **CHAR_MIN/MAX**, **SCHAR_MIN/MAX**, **UCHAR_MAX**, **SHRT_MIN/MAX**, **USHRT_MAX**, **INT_MIN/MAX**, **UINT_MAX**, **LONG_MIN/MAX**, **ULONG_MAX**, **LLONG_MIN/MAX** và **ULLONG_MAX**. Trong C23 còn có các macro độ rộng như **INT_WIDTH**, **LONG_WIDTH** khi compiler hỗ trợ. **INT_MIN** là macro đúng cho C **int**; không dùng **Integer.MIN_VALUE** của Java để thay thế khi lập trình C tổng quát.

## 4. Các data model thường gặp: ILP32, LP64, LLP64

Tên data model cho biết những kiểu nào dài 32/64 bit. Bảng sau mô tả các ABI phổ biến với **CHAR_BIT = 8**; giá trị là số byte C, không phải ràng buộc chung của chuẩn C.

| Kiểu | ILP32 (đa số ABI 32-bit) | LP64 (Linux/macOS Unix-like 64-bit) | LLP64 (Windows 64-bit) |
| --- | ---: | ---: | ---: |
| **char** | 1 | 1 | 1 |
| **short** | 2 | 2 | 2 |
| **int** | 4 | 4 | 4 |
| **long** | 4 | 8 | 4 |
| **long long** | 8 | 8 | 8 |
| **void \*** | 4 | 8 | 8 |

- **ILP32**: **int**, **long**, pointer thường 32 bit. **long long** vẫn thường 64 bit.
- **LP64**: **long** và pointer thường 64 bit, **int** giữ 32 bit.
- **LLP64**: **long long** và pointer thường 64 bit, **long** vẫn 32 bit. Đây là model của Windows 64-bit.
- Có các model khác và ABI khác trên hệ thống nhúng/kiến trúc đặc biệt. Không suy ra data model chỉ từ tên CPU, hệ điều hành hoặc **System.getProperty("os.arch")**; hãy kiểm tra ABI/target thực tế.

Tình huống: một hàm C khai báo **long read_id(void)** trả về giá trị 5.000.000.000. Trên LP64, **long** 64-bit thường chứa được số đó; trên LLP64, **long** 32-bit không thể biểu diễn nó. Thay đổi ABI bằng cách thay **long** thành **int64_t** trong API là một lựa chọn hợp lý *nếu* bạn kiểm soát đồng thời hai phía và cần miền signed 64-bit. Nếu thư viện bên thứ ba đã cố định **long**, phải dùng đúng ABI của thư viện và kiểm tra giới hạn khi chuyển đổi.

**Không đồng nhất độ rộng và calling convention.** Hai nền tảng đều có **int** 32-bit vẫn có thể khác cách truyền đối số qua thanh ghi/stack, quy tắc căn chỉnh, symbol name và cách trả về struct. Data model chỉ giải quyết một phần của ABI.

## 5. Ba kiểu char và bẫy signedness

Trong C, **char**, **signed char** và **unsigned char** là ba kiểu khác nhau. Compiler/target quyết định **char** có cùng miền giá trị với **signed char** hay **unsigned char**. Với byte 8 bit, một byte có bit cao bằng 1 có thể được đọc là **−1** nếu **char** signed, hoặc **255** nếu **char** unsigned. Không có một kết quả thống nhất cho mã sau trên mọi compiler:

~~~c
char c = (char)0xFF;
/* Giá trị c phụ thuộc signedness của plain char và conversion khi cần. */
~~~

Muốn chứa byte nhị phân/giá trị 0..255 trên nền tảng 8-bit, thường dùng **unsigned char** hoặc **uint8_t** khi có. Muốn số âm/dương 8-bit cụ thể, dùng **int8_t** khi có; đừng đổi sang **char** chỉ vì chúng cùng kích thước trên máy đang chạy. Dùng **CHAR_MIN < 0** để kiểm tra signedness của **char**, và **UCHAR_MAX** để kiểm tra miền unsigned thực tế.

**C char khác Java char.** Java **char** luôn là UTF-16 code unit không dấu 16-bit (0..65535); C **char** là đơn vị byte C, thường 8-bit, không tự mang ngữ nghĩa Unicode. Các chuỗi C có thể chứa UTF-8 theo quy ước API, nhưng mỗi byte UTF-8 không phải một Java **char**.

## 6. Chọn kiểu portable bằng <stdint.h>, <stddef.h>, <inttypes.h>

| Nhu cầu | Kiểu hoặc macro khuyên dùng | Lưu ý |
| --- | --- | --- |
| Miền signed chính xác 32/64 bit trên giao thức/API | **int32_t**, **int64_t** | Có điều kiện: chỉ tồn tại nếu implementation hỗ trợ kiểu đúng độ rộng |
| Miền unsigned chính xác 8/32/64 bit | **uint8_t**, **uint32_t**, **uint64_t** | Dùng tốt với định dạng byte có quy ước rõ; kiểm tra availability |
| Cần *ít nhất* N bit | **int_leastN_t**, **uint_leastN_t** | Độ rộng thực tế có thể lớn hơn N |
| Cần kiểu thuận lợi cho hiệu năng với *ít nhất* N bit | **int_fastN_t**, **uint_fastN_t** | Có thể lớn hơn N; không dùng làm layout lưu trữ cố định |
| Kích thước đối tượng và số phần tử | **size_t** từ **<stddef.h>** | Unsigned, cùng với kết quả **sizeof**; in bằng **%zu** |
| Hiệu hai con trỏ hợp lệ trong cùng mảng | **ptrdiff_t** từ **<stddef.h>** | Signed; in bằng **%td**; hiệu phải nằm trong miền biểu diễn |
| Số nguyên có thể giữ con trỏ **void \*** | **intptr_t**, **uintptr_t** nếu có | Optional; không thay **size_t** và không là hợp đồng serialize con trỏ |
| Kiểu nguyên có độ rộng ít nhất bằng các kiểu chuẩn liên quan | **intmax_t**, **uintmax_t** | Dùng **PRIdMAX**, **PRIuMAX** khi in |

**<stdint.h>** (C99+) định nghĩa các typedef chuẩn theo độ rộng, giới hạn tương ứng như **INT32_MIN/MAX**, **UINT64_MAX**, cùng các macro hằng như **INT64_C(123)**, **UINT64_C(123)**. **<inttypes.h>** có macro định dạng **PRId32**, **PRIu64**, **PRIxPTR** cho **printf**; các macro **SCN...** liên quan đọc bằng **scanf**. Đừng giả định **int64_t** được typedef thành **long**: LP64 thường dùng **long**, LLP64 thường dùng kiểu 64-bit khác. Vì thế **printf("%ld", (int64_t)value)** có thể sai kiểu đối số, thậm chí gây undefined behavior; dùng:

~~~c
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

void print_id(int64_t id, uint64_t flags) {
    printf("id=%" PRId64 ", flags=0x%" PRIx64 "\n", id, flags);
}
~~~

Đoạn trên là hàm minh họa, yêu cầu implementation cung cấp **int64_t/uint64_t**. **%zu** áp dụng cho **size_t**, **%td** cho **ptrdiff_t**, **%ld** chỉ cho **long**, **%lld** chỉ cho **long long**. Đây là hợp đồng kiểu của varargs, không phải “định dạng tùy chọn theo số bit”.

## 7. Chạy chương trình đo trực tiếp trên target

Tạo file **c_integer_probe.c**:

~~~c
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>

int main(void) {
    printf("CHAR_BIT=%d\n", CHAR_BIT);
    printf("sizeof: char=%zu short=%zu int=%zu long=%zu "
           "long long=%zu void*=%zu\n",
           sizeof(char), sizeof(short), sizeof(int),
           sizeof(long), sizeof(long long), sizeof(void *));
    printf("plain char signed=%s\n", CHAR_MIN < 0 ? "yes" : "no");
    printf("int: %d..%d; unsigned int max=%u\n",
           INT_MIN, INT_MAX, UINT_MAX);
    printf("long: %ld..%ld\n", LONG_MIN, LONG_MAX);
#ifdef INT64_MAX
    printf("int64_t max=%" PRId64 "\n", INT64_MAX);
#else
    puts("int64_t is unavailable");
#endif
    return 0;
}
~~~

Biên dịch bằng GCC/Clang trong môi trường có C17:

~~~bash
cc -std=c17 -Wall -Wextra -Wpedantic c_integer_probe.c -o c_integer_probe
./c_integer_probe
~~~

Với MSVC Developer Command Prompt, có thể dùng **cl /std:c17 /W4 c_integer_probe.c** rồi chạy **c_integer_probe.exe**. Các cờ biên dịch giữa compiler khác nhau; không dùng cờ GCC nguyên xi với MSVC.

Ví dụ output **cho Linux x86-64 LP64 có plain char signed**:

~~~text
CHAR_BIT=8
sizeof: char=1 short=2 int=4 long=8 long long=8 void*=8
plain char signed=yes
int: -2147483648..2147483647; unsigned int max=4294967295
long: -9223372036854775808..9223372036854775807
int64_t max=9223372036854775807
~~~

Ví dụ output **cho Windows x64 LLP64 với MSVC**:

~~~text
CHAR_BIT=8
sizeof: char=1 short=2 int=4 long=4 long long=8 void*=8
plain char signed=yes
int: -2147483648..2147483647; unsigned int max=4294967295
long: -2147483648..2147483647
int64_t max=9223372036854775807
~~~

Các kết quả trên là *hai ví dụ được gắn điều kiện về ABI/compiler*, không phải stdout duy nhất cho chương trình. Chạy bản biên dịch native đúng bitness/compiler/target mới xác nhận được kết quả thực tế. Cũng cần phân biệt target của thư viện C với JVM đang chạy: cả hai thành phần trong cùng một tiến trình phải tương thích kiến trúc và ABI.

## 8. Chuyển đổi, promotion, overflow và lỗi khó thấy

### 8.1. Integer promotions và trộn signed/unsigned

Trong phần lớn phép toán, **char**, **signed char**, **unsigned char**, **short** và **unsigned short** được *integer promotion* thành **int** nếu **int** biểu diễn được toàn bộ miền giá trị nguồn; nếu không, thành **unsigned int**. Khi hai toán hạng có thứ hạng và dấu khác nhau, *usual arithmetic conversions* chọn kiểu chung theo các quy tắc của C. Do đó kích thước lưu trữ ban đầu không đủ để đoán kiểu của kết quả biểu thức.

Ví dụ C17 độc lập:

~~~c
#include <stdio.h>

int main(void) {
    int debt = -1;
    unsigned int one = 1U;
    printf("%d\n", debt < one);
    return 0;
}
~~~

Kết quả:

~~~text
0
~~~

Vì **int** và **unsigned int** cùng conversion rank, **debt** được chuyển sang **unsigned int**; giá trị **−1** thành **UINT_MAX**, nên so sánh với 1U là sai. Cảnh báo **-Wsign-compare** giúp phát hiện lỗi phổ biến này, nhưng không thay việc thiết kế miền giá trị thống nhất. Kiểm tra dấu âm/range *trước* khi chuyển sang unsigned; không ép kiểu tùy tiện để “hết warning”.

### 8.2. Overflow signed khác unsigned

~~~c
#include <limits.h>
#include <stdio.h>

int main(void) {
    unsigned int wrapped = UINT_MAX;
    wrapped++;
    printf("%u\n", wrapped);
    return 0;
}
~~~

Kết quả được chuẩn C bảo đảm:

~~~text
0
~~~

Trái lại, **INT_MAX + 1** khi tính bằng **int** signed gây **undefined behavior**; việc phần cứng dùng hai-bù không làm overflow signed trở nên an toàn theo chuẩn C (kể cả C23). Cần kiểm tra trước khi cộng, ví dụ **if (b > 0 && a > INT_MAX - b)** cho trường hợp a và b kiểu **int** và b dương; với b âm cần kiểm tra **a < INT_MIN - b**. Phép dịch trái có thể gây undefined behavior nếu sai độ rộng/không biểu diễn được kết quả; với bit mask hãy dùng kiểu unsigned đủ độ rộng, và kiểm tra số bit dịch nhỏ hơn độ rộng kiểu đã được promotion.

### 8.3. Chuyển kiểu ngoài miền

Ép một số nguyên signed có giá trị dương/âm sang kiểu unsigned tạo kết quả modulo phạm vi của kiểu unsigned đích. Khi chuyển một giá trị nguyên sang kiểu **signed** không thể biểu diễn, hành vi tùy implementation hoặc có thể phát sinh tín hiệu theo quy tắc conversion của C; không nên kỳ vọng giá trị luôn “quấn vòng”. Điều này khác với overflow *của phép toán* signed, vốn undefined. Ví dụ chuyển **jlong** (signed 64-bit) sang C **long** trên LLP64 có thể làm mất giá trị: cần so sánh với **LONG_MIN/LONG_MAX** trước khi cast.

Một hàm phụ trợ khi viết JNI (đoạn minh họa yêu cầu header JNI, không phải chương trình C độc lập):

~~~c
#include <jni.h>
#include <limits.h>

static int checked_jlong_to_long(jlong input, long *result) {
    if (result == NULL) {
        return 0;
    }
    if (input < LONG_MIN || input > LONG_MAX) {
        return 0;
    }
    *result = (long)input;
    return 1;
}
~~~

Nếu API native cần nhận toàn miền signed 64-bit, hãy cân nhắc dùng **int64_t** hoặc kiểu C tương ứng **jlong** thay vì cố ép sang **long** 32-bit; thay chữ ký của API công khai phải được thống nhất với bên gọi để giữ ABI tương thích.

## 9. So sánh trực tiếp với Java và JNI

Java định nghĩa độ rộng bit của kiểu nguyên primitive độc lập với LP64/LLP64: **byte** 8 signed; **short** 16 signed; **int** 32 signed; **long** 64 signed; **char** 16 unsigned (UTF-16 code unit); **boolean** không phải số nguyên C với layout lưu trữ được quy định giống **_Bool**.

Tạo file **JavaWidths.java**:

~~~java
public class JavaWidths {
    public static void main(String[] args) {
        System.out.printf(
                "byte=%d short=%d int=%d long=%d char=%d%n",
                Byte.BYTES, Short.BYTES, Integer.BYTES,
                Long.BYTES, Character.BYTES);
        System.out.println(
                "Java long: " + Long.MIN_VALUE + ".." + Long.MAX_VALUE);
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac JavaWidths.java
java JavaWidths
~~~

Stdout chính xác:

~~~text
byte=1 short=2 int=4 long=8 char=2
Java long: -9223372036854775808..9223372036854775807
~~~

Java **Byte.BYTES** tính theo octet 8-bit của Java; không dùng nó thay **CHAR_BIT** của C. **Java long 64-bit** vẫn không chứng minh **C long 64-bit**.

JNI định nghĩa các kiểu native có độ rộng tương ứng với Java, dùng các tên trong **jni.h**:

| Java primitive | JNI C type | Miền/độ rộng |
| --- | --- | --- |
| **boolean** | **jboolean** | unsigned 8-bit, dùng **JNI_FALSE/JNI_TRUE** |
| **byte** | **jbyte** | signed 8-bit |
| **char** | **jchar** | unsigned 16-bit |
| **short** | **jshort** | signed 16-bit |
| **int** | **jint** | signed 32-bit |
| **long** | **jlong** | signed 64-bit |

**jsize** được định nghĩa bằng **jint** và thường dùng cho độ dài/chỉ số trong JNI; không đổi tùy tiện sang **size_t**, nhất là khi số phần tử có thể vượt miền **jint**. Khi viết chữ ký JNI, dùng **jint/jlong/jchar** thay cho giả định “tình cờ cùng sizeof” của **int/long/char**. Chữ ký Java **(J)I** nghĩa là nhận **long** và trả **int**; chữ cái **J** ở đây không đồng nghĩa C **long**.

Chẳng hạn hàm native cần cộng hai **jint** và trả kết quả rộng hơn có thể thực hiện bằng cách nâng kiểu *trước phép cộng*:

~~~c
#include <jni.h>

/* Tên hàm phải khớp lớp/package Java và quy tắc đặt tên JNI. */
JNIEXPORT jlong JNICALL
Java_example_NativeMath_sumWide(JNIEnv *env, jclass owner, jint a, jint b) {
    (void)env;
    (void)owner;
    return (jlong)a + (jlong)b;
}
~~~

Đây là hàm JNI, không phải chương trình C có **main**; để chạy cần lớp Java khai báo **static native long sumWide(int a, int b)** trong package **example**, build shared library đúng JDK header/target, rồi nạp thư viện. Việc cast hai toán hạng sang **jlong** *trước khi cộng* tránh overflow 32-bit khi tổng vượt **jint**.

Với Foreign Function & Memory API ở các phiên bản JDK hỗ trợ, layout để gọi C cũng phải phù hợp *ABI native*: đừng mặc định mọi C **long** là layout Java **long** 64-bit. Cần đối chiếu mô tả linker/canonical layouts của phiên bản JDK đang dùng và chữ ký thư viện thực tế.

## 10. ABI, struct, alignment và định dạng dữ liệu

Kích thước kiểu là một phần của ABI, còn **alignment** và **padding** ảnh hưởng tới offset của thành viên struct. Ví dụ:

~~~c
#include <stdint.h>

struct Record {
    uint8_t kind;
    uint32_t count;
};
~~~

Ngay cả khi **uint8_t** là 1 byte và **uint32_t** là 4 byte, **sizeof(struct Record)** không nhất thiết bằng 5; ABI có thể chèn byte đệm trước **count** hoặc ở cuối struct. Thứ tự byte (endianness) cũng không suy ra từ **LP64/LLP64**. Không dùng **memcpy** nguyên struct rồi gửi qua mạng/lưu file như một format bền vững nếu chưa định nghĩa và kiểm soát toàn bộ layout, packing, endian và version.

Đối với một giao thức cố định 8-bit/octet và trường số unsigned 32-bit big-endian, hãy mã hóa từng byte với quy ước rõ:

~~~c
#include <limits.h>
#include <stdint.h>

/* Ví dụ yêu cầu byte 8 bit và kiểu uint32_t có sẵn. */
_Static_assert(CHAR_BIT == 8, "wire format requires 8-bit bytes");

static void write_u32_be(uint8_t out[4], uint32_t value) {
    out[0] = (uint8_t)(value >> 24);
    out[1] = (uint8_t)(value >> 16);
    out[2] = (uint8_t)(value >> 8);
    out[3] = (uint8_t)value;
}
~~~

Với **value = 0x01020304**, bốn byte nhận được là **01 02 03 04** trên cả máy little-endian và big-endian. Đây là helper C (không có **main**); caller phải cấp mảng ít nhất 4 phần tử. Nếu thư viện phải hỗ trợ môi trường không có **uint32_t** hoặc **CHAR_BIT != 8**, cần chọn giao thức/kiểu thay thế hay từ chối target, chứ không mặc nhiên giả lập bằng **long**.

Ở ranh giới Java–native, hãy xác định rõ:
1. Trường dữ liệu là signed hay unsigned; nếu một **uint64_t** C đi vào **Java long**, Java không có primitive unsigned long riêng để biểu diễn toàn bộ miền 0..2^64−1 theo nghĩa signed. Có thể giữ *bit pattern* trong **long** với phép toán unsigned (**Long.compareUnsigned**, **Long.toUnsignedString**) hoặc dùng **BigInteger** khi cần biểu diễn giá trị toán học dương đầy đủ.
2. Native API nhận đúng kiểu và calling convention, không suy ra chỉ từ **sizeof**.
3. Có chuẩn byte order, encoding và quy tắc kiểm tra range nếu dữ liệu đi qua file/socket/shared memory.
4. Không ép pointer thành **int** hoặc C **long** một cách vô điều kiện; Windows LLP64 có pointer 64-bit nhưng **long** 32-bit. **intptr_t/uintptr_t** nếu có là lựa chọn dành cho nhu cầu giữ biểu diễn con trỏ; không biến con trỏ thành ID có thể lưu truyền lâu dài.

## 11. Các lỗi phổ biến và cách sửa

| Sai lầm | Vì sao hỏng | Cách làm vững hơn |
| --- | --- | --- |
| “64-bit OS ⇒ C long 64-bit” | LLP64 giữ **long** 32-bit | Xem ABI và đo **sizeof(long)**/**LONG_MAX** |
| Dùng **long** C để tương ứng Java **long** | Java **long** luôn 64-bit, C **long** biến đổi | Dùng **jlong** trong JNI; kiểm tra range khi chuyển C **long** |
| Dùng **char** cho byte nhị phân rồi so sánh với giá trị 128..255 | Plain **char** có thể signed | Dùng **unsigned char**/**uint8_t** |
| Dùng **sizeof(int) == 4** như bảo đảm chuẩn C | C chỉ bảo đảm **int** tối thiểu 16-bit | Giới hạn runtime bằng **limits.h** hoặc dùng kiểu fixed-width phù hợp |
| In **sizeof** bằng **%d**, in **int64_t** bằng **%ld** | Sai kiểu đối số của **printf** | **%zu**, **PRId64** tương ứng |
| Tính **a + b** signed rồi mới cast sang kiểu rộng | Overflow có thể xảy ra *trước* cast | Cast/kiểm tra *trước* phép toán |
| So sánh **int** âm với **unsigned** | Conversion có thể biến âm thành số dương rất lớn | Thống nhất miền giá trị, kiểm tra âm trước chuyển |
| Giả định struct có layout bằng tổng **sizeof** thành viên | Có alignment/padding/packing theo ABI | ABI rõ ràng hoặc mã hóa từng trường |
| Coi **size_t**, **ptrdiff_t**, **intptr_t** là cùng một kiểu | Mỗi kiểu có hợp đồng khác nhau | Chọn theo vai trò kích thước, hiệu con trỏ, giữ địa chỉ |
| Cast số ngoài miền sang signed và chờ wrap | Kết quả conversion phụ thuộc implementation; overflow phép toán signed còn undefined | Kiểm tra macro MIN/MAX, xử lý lỗi |

Cách kiểm tra khi port JNI/JNA/FFM hay thư viện C: ghi rõ target triple/compiler, word size, data model, các header ABI; chạy chương trình probe trên *mỗi build target*; kiểm tra kiểu đầu vào/đầu ra từng hàm, định dạng varargs, offset struct, endian và miền giá trị trước mọi chuyển đổi hẹp. Unit test nên bao phủ **MIN**, **MAX**, **0**, **−1**, giá trị quanh **2^31** và **2^32** khi phù hợp với miền API.

## 12. Tự kiểm tra hiểu bài

**Tình huống A.** Linux x86-64 và Windows x64 đều chạy JVM 64-bit. Java gửi số **3.000.000.000L** đến hàm C nhận **long**. Có được cast trực tiếp trên hai hệ điều hành không?

**Đáp án:** Trên LP64, C **long** thường signed 64-bit nên biểu diễn được. Trên LLP64, C **long** signed 32-bit nên giá trị nằm ngoài miền; phải báo lỗi hoặc đổi hợp đồng API sang kiểu native có đủ miền. Cả hai JVM cùng có Java **long** 64-bit không thay đổi điều đó.

**Tình huống B.** Vì sao **printf("%ld", x)** với **int64_t x** có thể đúng trên Linux nhưng sai trên Windows, dù **sizeof(x) == 8** ở cả hai?

**Đáp án:** **int64_t** là alias cho kiểu 64-bit phù hợp target, không bảo đảm alias **long**. **%ld** yêu cầu **long** theo hợp đồng varargs; dùng **"%" PRId64** để in đúng kiểu thực sự.

**Tình huống C.** Một byte mạng có giá trị hex **FF** được đưa vào biến **char**; vì sao nhánh **if (c < 0)** chạy trên compiler này nhưng không chạy trên compiler khác?

**Đáp án:** Plain **char** có signedness phụ thuộc implementation. Cần **unsigned char** hoặc **uint8_t** để làm việc với octet 0..255; nếu muốn diễn giải signed 8-bit, chuyển có kiểm tra/định nghĩa rõ thay vì dựa vào plain **char**.

## Tài liệu chuẩn để tra cứu

- C arithmetic integer types, data models: https://en.cppreference.com/w/c/language/arithmetic_types
- C integer limits, **CHAR_BIT**, **LONG_MAX**: https://en.cppreference.com/w/c/types/limits
- C fixed-width integer types, **stdint.h/inttypes.h**: https://en.cppreference.com/w/c/types/integer
- Windows ILP32/LLP64 data model: https://learn.microsoft.com/en-us/windows/win32/winprog64/abstract-data-models
- JNI primitive/native type mapping: https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html
- GCC integer representation and C23 notes: https://gcc.gnu.org/onlinedocs/gcc/Integers-implementation.html

**Kết luận học tập:** Khi đi qua ranh giới Java/C, xác định **kiểu và giới hạn theo hợp đồng ABI thực tế**, dùng kiểu có độ rộng đã quy định khi cần, đọc macro giới hạn của C, chuyển đổi có kiểm tra, và kiểm chứng trên đúng platform mục tiêu.