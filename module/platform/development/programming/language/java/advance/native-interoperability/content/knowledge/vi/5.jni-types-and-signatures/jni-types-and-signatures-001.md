# Ánh xạ boolean, byte, char, số nguyên và số thực sang kiểu JNI

## Mục tiêu

Khi một phương thức Java được khai báo `native`, JVM cần chuyển các **giá trị nguyên thủy** (primitive values) qua ranh giới Java ↔ mã native theo Java Native Interface (JNI). Để khai báo hàm C/C++ và gọi các API JNI đúng, cần phân biệt ba thứ:

1. **Kiểu trong khai báo Java**, ví dụ `boolean`, `byte`, `char`, `long`.
2. **Kiểu JNI tương ứng ở phía C/C++**, ví dụ `jboolean`, `jbyte`, `jchar`, `jlong`. Đây là các typedef được quy định bởi JNI và đi kèm header `jni.h`.
3. **Ký hiệu trong JNI type descriptor (chữ ký kiểu)**, ví dụ `Z`, `B`, `C`, `J`. Descriptor mã hóa kiểu cho JVM; nó không phải tên kiểu C và không phải chuỗi lệnh để ép kiểu.

Học xong, bạn sẽ biết cách đọc bảng ánh xạ, định nghĩa đúng chữ ký hàm native, nhận diện signedness và độ rộng số, xử lý ký tự UTF-16, tránh mất chính xác khi đổi số thực và kiểm tra kết quả bằng một chương trình Java/JNI có thể chạy.

## 1. Bảng ánh xạ chuẩn: tám primitive và `void`

| Kiểu Java | Kiểu JNI trong C/C++ | Kích thước/ý nghĩa logic | JNI descriptor | Ghi chú quan trọng |
| --- | --- | --- | --- | --- |
| `boolean` | `jboolean` | Giá trị false/true; biểu diễn JNI 8 bit không dấu | `Z` | Dùng `JNI_FALSE` (0), `JNI_TRUE` (1); đừng giả định C `bool`/`int` có cùng ABI |
| `byte` | `jbyte` | Số nguyên có dấu 8 bit: -128 đến 127 | `B` | Byte có bit mẫu `0xFF` mang giá trị `-1` nếu diễn giải như `jbyte` |
| `char` | `jchar` | Một **UTF-16 code unit** không dấu 16 bit: 0 đến 65535 | `C` | Không tương đương C `char` hoặc `wchar_t` |
| `short` | `jshort` | Số nguyên có dấu 16 bit | `S` | -32768 đến 32767 |
| `int` | `jint` | Số nguyên có dấu 32 bit | `I` | -2³¹ đến 2³¹ - 1 |
| `long` | `jlong` | Số nguyên có dấu 64 bit | `J` | Không thay thế bằng C `long` nếu chưa chứng minh ABI |
| `float` | `jfloat` | Số thực 32 bit IEEE 754 binary32 | `F` | Có NaN, ±Infinity, +0.0 và -0.0 |
| `double` | `jdouble` | Số thực 64 bit IEEE 754 binary64 | `D` | Nhiều chữ số chính xác hơn `float` nhưng vẫn là số nhị phân xấp xỉ |
| `void` (kiểu trả về) | C/C++ `void` | Không trả về giá trị | `V` | `V` chỉ hợp lệ ở kiểu trả về của method descriptor, không là tham số Java |

**Đây là ánh xạ kiểu, không phải ép kiểu tùy ý.** Khi định nghĩa JNI entry point, hãy dùng chính xác các kiểu `j...` từ header được JDK cung cấp. `jni.h` và `jni_md.h` sẽ chọn khai báo C thích hợp cho nền tảng để giữ bề rộng và quy ước gọi được yêu cầu. Ví dụ, Java `long` luôn có 64 bit nhưng C `long` có thể rộng 32 bit trên Windows 64-bit; `jlong` mới là tên tương thích cần dùng.

Ngược lại, `jint` khác `jobject`: primitive truyền **theo giá trị**, còn `String`, array và instance Java được JNI biểu diễn bằng **reference handles** như `jstring`, `jbyteArray` và `jobject`. Không được diễn giải `jbyteArray` như con trỏ C trỏ thẳng tới một dãy `jbyte`.

## 2. Vì sao cần các kiểu JNI thay vì C `int`, `long`, `char`?

JNI là hợp đồng giữa JVM và mã native, có thể hoạt động trên nhiều hệ điều hành, kiến trúc CPU, C compiler và C data model:

- `char` của C thường rộng 8 bit, có thể signed hoặc unsigned tùy compiler; `jchar` mang đúng một UTF-16 code unit **không dấu 16 bit**.
- `long` của C không có độ rộng cố định trên mọi ABI: LP64 thường có `long` 64 bit, LLP64 thường có `long` 32 bit. Java `long` và `jlong` là kiểu **có dấu 64 bit**.
- C `bool`/`_Bool` là kiểu logic của ngôn ngữ C; `jboolean` là kiểu JNI với biểu diễn và quy ước API do JNI xác định.
- C `float`/`double` thường tương ứng cách lưu trữ JNI `jfloat`/`jdouble` trên nền tảng Java được hỗ trợ, nhưng lời khai báo native phải vẫn dùng `jfloat` và `jdouble` để đúng giao diện được xuất bởi `jni.h`.

Đừng dùng `typedef` tự chế theo `sizeof(long)` hoặc độ rộng của máy hiện tại để thay cho `jint`/`jlong`. Ví dụ JNI prototype bắt đầu bằng `JNIEXPORT jlong JNICALL`, không phải tự chọn `long WINAPI` hoặc `long long` một cách thiếu kiểm chứng. Macro `JNIEXPORT` đảm bảo symbol có visibility phù hợp; `JNICALL` dùng calling convention mà JNI yêu cầu ở nền tảng đó.

**Quan trọng về endianness:** khi JVM gọi JNI method với tham số `jint`/`jlong`, phía C nhận **giá trị số** theo ABI; thông thường không cần tự đảo byte vì CPU là little-endian hay big-endian. Endianness trở thành vấn đề khi mã ứng dụng đọc/ghi **raw bytes**, ép con trỏ hoặc giao tiếp giao thức trên mạng/tệp. Không trộn lẫn hai lớp này.

## 3. Boolean: `boolean` ↔ `jboolean`

Một `boolean` trong Java chỉ biểu diễn `true` hoặc `false`. JNI định nghĩa hai hằng:

~~~c
JNI_FALSE  /* 0 */
JNI_TRUE   /* 1 */
~~~

Ví dụ xử lý an toàn trong hàm JNI:

~~~c
JNIEXPORT jboolean JNICALL Java_Example_isPositive(
        JNIEnv *env, jclass cls, jint value) {
    (void) env;
    (void) cls;
    return value > 0 ? JNI_TRUE : JNI_FALSE;
}
~~~

Đây là **đoạn minh họa hàm native**, không phải một chương trình C độc lập. Nó yêu cầu `jni.h`, khai báo native Java phù hợp và header do `javac -h` sinh ra. Tham số đầu là `JNIEnv *` (giao diện gọi dịch vụ JVM), tham số thứ hai là `jclass` do phương thức ví dụ là `static native`. Các tham số primitive của Java bắt đầu từ tham số thứ ba.

Lưu ý:

- `jboolean` không phải `jint`. Đừng khai báo Java `boolean` thành C `int` dù đôi khi kiểm thử đơn giản dường như vẫn chạy.
- Khi **trả về** cho Java, chuẩn hóa thành `JNI_TRUE` hoặc `JNI_FALSE`. Không truyền trực tiếp một số tùy ý hay giá trị byte cao rồi giả định mọi JVM sẽ diễn giải giống nhau.
- Mảng `boolean[]` tương ứng `jbooleanArray`, không phải `jboolean *`. Cần gọi các API JNI cho mảng để truy cập phần tử khi cần.

## 4. Byte: `byte` ↔ `jbyte`, signedness và dữ liệu nhị phân

Java `byte` và JNI `jbyte` đều có dấu, giới hạn từ -128 đến 127. Nếu dữ liệu thực tế là một octet với giá trị 0..255, vẫn có thể giữ nguyên tám bit trong `byte`; chỉ **cách diễn giải số học** thay đổi.

~~~java
byte raw = (byte) 0xFE;
System.out.println(raw);           // -2
System.out.println(raw & 0xFF);    // 254
~~~

Trong C khi nhận `jbyte raw`, có thể lấy giá trị unsigned bằng cách mở rộng lên `jint` rồi mask:

~~~c
jint unsigned_value = ((jint) raw) & 0xFF;
~~~

Cả hai cách ở trên tạo `254` từ mẫu bit `0xFE`. Đừng làm toán trên `jbyte` như thể nó luôn là số không dấu; phép promotion sang kiểu nguyên lớn hơn vẫn giữ dấu của giá trị ban đầu. Đối với mã giao thức, checksum, cấu trúc binary, cần xác định chính xác yêu cầu signed/unsigned.

Nếu Java có `byte[]`, JNI nhận kiểu **`jbyteArray`**; mảng Java là đối tượng được quản lý bởi JVM. Để đọc hoặc ghi nội dung, dùng API như `GetByteArrayRegion`, `SetByteArrayRegion` hoặc cặp `GetByteArrayElements`/`ReleaseByteArrayElements`, đồng thời tôn trọng độ dài và vòng đời. **Không ép trực tiếp `jbyteArray` thành `jbyte *`.**

## 5. Char: `char` ↔ `jchar` là UTF-16 code unit, không phải byte C

`char` của Java và `jchar` của JNI là số **không dấu 16 bit**. Chúng giữ **một đơn vị mã UTF-16**, không nhất thiết tương đương một ký tự Unicode hoàn chỉnh và không nên tự động coi là ASCII.

Ví dụ:

- `'A'` có giá trị UTF-16 `0x0041` (65).
- `'中'` có giá trị `0x4E2D` (20013), vượt giới hạn một byte.
- Ký tự Unicode ngoài Basic Multilingual Plane (BMP), chẳng hạn U+1F642, được mã hóa bằng **hai UTF-16 code unit (surrogate pair)**, vì vậy không thể chứa trọn trong một `char`/`jchar`.

~~~java
char han = '中';
String smile = new String(Character.toChars(0x1F642));

System.out.println((int) han);       // 20013
System.out.println(smile.length());  // 2 UTF-16 code units
System.out.println(smile.codePointCount(0, smile.length())); // 1 code point
~~~

Phía C:

~~~c
jchar unit = /* tham số jchar nhận từ Java */;
jint numeric_value = (jint) unit; /* 0..65535 */
~~~

Đoạn C trên chỉ minh họa kiểu biến bên trong native method. Trong chương trình thực tế, `unit` là tham số do JVM truyền hoặc đọc từ `jcharArray`.

**Ba nhầm lẫn thường gặp:**

1. `jchar` **khác C `char`**: ép về C `char` có thể làm mất các bit cao.
2. `jchar` **khác `wchar_t`**: `wchar_t` có độ rộng và cách dùng phụ thuộc nền tảng (ví dụ 16 hoặc 32 bit). Không dùng trực tiếp pointer `wchar_t *` như `jchar *`.
3. `jchar` **khác Unicode code point**: surrogate đơn lẻ là code unit hợp lệ ở mức biểu diễn UTF-16; để xử lý văn bản theo code point, cần xét cặp surrogate.

Khi truyền cả chuỗi qua JNI, `String` được biểu diễn bằng `jstring`. `GetStringChars` cung cấp các `jchar` của UTF-16 sau khi lấy bằng JNI API; `GetStringUTFChars` sử dụng **Modified UTF-8** của JNI, không phải UTF-8 chuẩn. Không suy ra `String` là mảng `jchar` chỉ từ tên kiểu.

## 6. Số nguyên: `short`, `int`, `long` và độ rộng cố định

Các cặp chuẩn là:

~~~text
Java short  -> jshort : 16-bit signed
Java int    -> jint   : 32-bit signed
Java long   -> jlong  : 64-bit signed
~~~

C++ không tự động hiểu Java `long` giống C++ `long` ở mọi platform. Một method Java `native long getCounter()` phải trả kiểu **`jlong`**. Nếu library C bên dưới có kiểu `long`, việc chuyển cần dựa trên miền giá trị thực tế, giới hạn của type và ABI.

Ví dụ:

~~~java
long big = 5_000_000_000L;
int narrow = (int) big;
System.out.println(big);    // 5000000000
System.out.println(narrow); // 705032704
~~~

Java cho phép ép tường minh từ `long` sang `int`; kết quả giữ 32 bit thấp, nên số bị mất giá trị. Đây chỉ là **hành vi của phép cast trong Java**. Khi C chuyển từ một kiểu nguyên lớn sang kiểu nguyên có dấu nhỏ hơn, kết quả ngoài phạm vi biểu diễn là trường hợp chịu quy tắc chuyển đổi của C/implementation, không được mặc định giống Java. Vì vậy nên **kiểm tra miền giá trị trước khi ép**.

Ví dụ nếu hàm C cần đưa một `jlong` dương về `jint`:

~~~c
#include <stdint.h> /* INT32_MAX, INT32_MIN thường ở <stdint.h> */

int fits_in_jint(jlong value) {
    return value >= (-2147483647LL - 1LL)
        && value <= 2147483647LL;
}
~~~

Hàm trên là helper C minh họa; nó không phải JNI entry point. Khi đã xác nhận nằm trong [-2³¹, 2³¹-1], có thể cast sang `jint` mà không làm đổi giá trị. Nếu viết code portable cho nhiều kiểu gốc, có thể dùng `INT32_MIN`/`INT32_MAX` từ `<stdint.h>` trên môi trường hỗ trợ kiểu 32 bit, nhưng đừng tự gán giới hạn của `size_t` hay `long` bằng giới hạn `jint`.

**Trường hợp không dấu:** Java nguyên thủy không có `unsigned int`/`unsigned long` riêng như C. Khi native API dùng `uint32_t` hoặc `uint64_t`, hãy thống nhất kiểu và cách diễn giải bit pattern, phép so sánh, chuỗi hóa và miền giá trị. Java cung cấp các phép toán không dấu như `Integer.toUnsignedLong`, `Integer.compareUnsigned`, `Long.compareUnsigned`. JNI `jint`/`jlong` vẫn là kiểu có dấu; đặc tả giao tiếp phải nói rõ cách xử lý giá trị vượt ngưỡng signed.

## 7. Số thực: `float` ↔ `jfloat`, `double` ↔ `jdouble`

`jfloat` và `jdouble` đại diện cho hai định dạng dấu phẩy động IEEE 754 trong Java: **binary32 (32 bit)** và **binary64 (64 bit)**. Đây không phải biểu diễn số thập phân chính xác cho mọi giá trị.

~~~java
float a = 0.1f;
double b = 0.1;

System.out.println(a == (float) b); // true
System.out.println((double) a == b); // false
System.out.println(Float.floatToRawIntBits(1.5f) == 0x3FC00000); // true
System.out.println(Double.doubleToRawLongBits(1.5) == 0x3FF8000000000000L); // true
~~~

`0.1f` được làm tròn tới binary32, `0.1` được làm tròn tới binary64. So sánh `a == (float)b` cho true vì ép `b` về float sinh cùng giá trị binary32, trong khi mở rộng `a` sang double không thể khôi phục phần chính xác đã mất.

JNI cho phép truyền các giá trị ±Infinity, NaN và ±0.0 qua các tham số `jfloat`/`jdouble`. Khi triển khai C:

- Không giả định hai số thực cộng/trừ/nhân/chia sẽ bằng chính xác một kết quả thập phân mong muốn; quyết định chính sách sai số theo bài toán.
- `NaN` không bằng chính nó: `NaN == NaN` là false. Nếu xử lý tham số nhạy cảm, kiểm tra `isnan`/`isfinite` bằng C `<math.h>` trên nền tảng phù hợp.
- `+0.0` và `-0.0` so sánh bằng nhau về số học, nhưng có bit dấu khác nhau; các phép như chia có thể phân biệt chúng.
- `float` sang `double` giữ chính xác giá trị binary32 hiện tại, **không khôi phục** số thập phân trước khi làm tròn.
- Ép số thực NaN/vô cực hoặc quá lớn sang integer trong C có thể không có hành vi như phép ép của Java; cần kiểm tra miền giá trị và chính sách lỗi. Ví dụ ở phần JNI chỉ cast các giá trị hữu hạn, nhỏ, nằm trong giới hạn `jlong`.
- Đừng tự ý thay tham số `jfloat` bằng `jdouble` dù C có quy tắc integer/floating promotion ở một số ngữ cảnh. Chữ ký JNI của native method phải khớp kiểu khai báo Java.

Nếu native xử lý tiền tệ chính xác, thường cần mô hình **đơn vị nguyên** (ví dụ cents) hoặc một biểu diễn số thập phân theo hợp đồng thay vì trông chờ `float`/`double` lưu đúng mọi số tiền.

## 8. Method descriptor: tên kiểu Java chuyển thành các ký tự `Z B C S I J F D`

JNI method descriptor theo dạng:

~~~text
(kiểu_tham_số_1 kiểu_tham_số_2 ...)kiểu_trả_về
~~~

Không đặt dấu phẩy hay khoảng trắng giữa các descriptor trong chuỗi thực. Ví dụ:

~~~java
static native long total(boolean enabled,
                         byte octet,
                         char unit,
                         short small,
                         int number,
                         long big,
                         float decimal32,
                         double decimal64);
~~~

Descriptor của đúng method này là:

~~~text
(ZBCSIJFD)J
~~~

Đọc từ trái sang phải: `Z` = boolean, `B` = byte, `C` = char, `S` = short, `I` = int, `J` = long, `F` = float, `D` = double; bên ngoài dấu `)` có `J` = kiểu trả về long.

Một số ví dụ độc lập để luyện đọc:

| Java method declaration | JVM/JNI descriptor | Giải thích |
| --- | --- | --- |
| `native boolean ready();` | `()Z` | Không có tham số, trả boolean |
| `native void set(byte x, short y);` | `(BS)V` | Byte và short, không có kết quả |
| `native char upper(char x);` | `(C)C` | Char vào/char ra |
| `native double average(int n, double x);` | `(ID)D` | Int và double, trả double |
| `native long tick(long delta);` | `(J)J` | Long vào/long ra |

Kiểu mảng và reference giúp phân biệt bối cảnh:

~~~text
byte[]                   [B
char[]                   [C
boolean[]                [Z
int[][]                  [[I
java.lang.String         Ljava/lang/String;
(byte[], String) -> void ([BLjava/lang/String;)V
~~~

Dấu `[` thêm một chiều mảng; kiểu object có dạng `L<internal-class-name>;`, với dấu `/` giữa package. Ký hiệu `V` chỉ dùng cho return type. Java `String` không có descriptor `C` và `byte[]` không có descriptor `B`: các kiểu đó là **reference**, không phải scalar primitive.

Muốn xác minh descriptor thật từ class đã biên dịch, dùng:

~~~bash
javap -p -s PrimitiveBridge
~~~

Lệnh này in thông tin method cùng dòng `descriptor: (ZBCSIJFD)J` cho method `total` trong ví dụ hoàn chỉnh dưới đây. `javap` không cần native library đang được nạp để đọc bytecode.

## 9. JNI entry point: tham số ẩn, thứ tự và kiểu trả về

Một lời khai báo `static native` như trên được triển khai bên C với prototype (tên lớp đúng ở phần ví dụ là `PrimitiveBridge`):

~~~c
JNIEXPORT jlong JNICALL Java_PrimitiveBridge_total(
    JNIEnv *env,
    jclass cls,
    jboolean enabled,
    jbyte octet,
    jchar unit,
    jshort small,
    jint number,
    jlong big,
    jfloat decimal32,
    jdouble decimal64);
~~~

Ở một instance method (không `static`), vị trí sau `JNIEnv *` là `jobject receiver` thay vì `jclass cls`. **Hai tham số đầu không có trong Java method descriptor**; chúng được JVM cung cấp khi gọi JNI entry point. Các giá trị primitive tiếp theo xuất hiện **đúng thứ tự khai báo trong Java**.

Quy tắc:

1. Dùng `JNIEXPORT <return-jni-type> JNICALL` ở function definition.
2. Dùng `JNIEnv *` đầu tiên; tham số thứ hai là `jobject`/`jclass` tùy phương thức instance/static.
3. Dùng đúng tám JNI primitive types, không thay bằng kiểu C đoán từ tên (`char`, `long`, `bool`).
4. Chữ ký C của hàm native và Java declaration phải tương thích; mismatched calling convention, thiếu tham số hoặc sai độ rộng có thể gây kết quả vô nghĩa hoặc lỗi tiến trình.
5. Dùng `javac -h` để **sinh header** thay vì tự đoán tên symbol, nhất là khi có package, method overload hoặc ký tự cần mã hóa trong JNI name mangling.

Một method native được khai báo `native void update(int x)` thì C entry point có return type `void`, argument `jint` và method descriptor `(I)V`. **Không** có kiểu `jvoid` cho giá trị trả về.

## 10. Ví dụ Java 17+ độc lập: quan sát giá trị và bit pattern

Tạo tệp `PrimitiveTypesOnly.java`, không cần thư viện native:

~~~java
public final class PrimitiveTypesOnly {
    public static void main(String[] args) {
        byte octet = (byte) 0xFE;
        char unit = '中';
        short small = -12345;
        int number = 2_000_000_000;
        long big = 5_000_000_000L;
        float decimal32 = 1.5f;
        double decimal64 = 1.5;

        System.out.println("byte=" + octet + ", unsigned=" + (octet & 0xFF));
        System.out.println("charCodeUnit=" + (int) unit);
        System.out.println("short=" + small + ", int=" + number);
        System.out.println("long=" + big);
        System.out.println("floatBits=" +
                Integer.toHexString(Float.floatToRawIntBits(decimal32)));
        System.out.println("doubleBits=" +
                Long.toHexString(Double.doubleToRawLongBits(decimal64)));
        System.out.println("supplementaryUnits=" +
                Character.charCount(0x1F642));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 PrimitiveTypesOnly.java
java PrimitiveTypesOnly
~~~

Stdout chính xác:

~~~text
byte=-2, unsigned=254
charCodeUnit=20013
short=-12345, int=2000000000
long=5000000000
floatBits=3fc00000
doubleBits=3ff8000000000000
supplementaryUnits=2
~~~

Đây là **phần Java kiểm tra dữ liệu**, dùng để hiểu chính xác các giá trị mà JNI sẽ nhận. `0xFE` trong Java byte hiển thị -2, còn Java char `中` là một code unit 20013; bit pattern của hai số thực `1.5` cho thấy bề rộng binary32/binary64.

## 11. Ví dụ JNI hoàn chỉnh: tám primitive đi vào C

Ví dụ này cho thấy cách khai báo chữ ký, nhận đủ các kiểu C/JNI, trả kết quả `jlong`, và khôi phục giá trị unsigned từ `jbyte`. Các phép tính dùng giá trị nhỏ, hữu hạn để tránh tràn hoặc chuyển đổi out-of-range; đây là **bài thực hành về ánh xạ kiểu**, không phải thuật toán tính tổng cho môi trường production.

### 11.1. Tệp Java `PrimitiveBridge.java`

~~~java
public final class PrimitiveBridge {
    static {
        System.loadLibrary("primitivebridge");
    }

    private static native long total(
            boolean enabled, byte octet, char unit, short small,
            int number, long big, float decimal32, double decimal64);

    private static native int unsignedByte(byte value);

    public static void main(String[] args) {
        long result = total(true, (byte) -2, 'A', (short) 1000,
                200_000, 3_000_000_000L, 1.5f, 2.5);
        System.out.println("total=" + result);
        System.out.println("unsignedByte=" + unsignedByte((byte) 0xFE));
    }
}
~~~

### 11.2. Tệp C `PrimitiveBridge.c`

~~~c
#include <jni.h>
#include "PrimitiveBridge.h" /* do javac -h . sinh ra */

JNIEXPORT jlong JNICALL Java_PrimitiveBridge_total(
        JNIEnv *env, jclass cls,
        jboolean enabled, jbyte octet, jchar unit, jshort small,
        jint number, jlong big, jfloat decimal32, jdouble decimal64) {
    (void) env;
    (void) cls;

    return (enabled == JNI_TRUE ? 1 : 0)
         + (jlong) octet
         + (jlong) unit
         + (jlong) small
         + (jlong) number
         + big
         + (jlong) decimal32
         + (jlong) decimal64;
}

JNIEXPORT jint JNICALL Java_PrimitiveBridge_unsignedByte(
        JNIEnv *env, jclass cls, jbyte value) {
    (void) env;
    (void) cls;
    return ((jint) value) & 0xFF;
}
~~~

Hàm `total` nhận các tham số đúng thứ tự Java. Giá trị `enabled` được chuẩn hóa bằng so sánh với `JNI_TRUE`. Các phép cộng được nâng lên `jlong` trước khi tính với những số nguyên ở ví dụ, giúp giữ kết quả lớn hơn phạm vi `jint`. Phép cast của `jfloat 1.5f` và `jdouble 2.5` về `jlong` lấy phần nguyên, lần lượt 1 và 2. Không áp cách cast này cho NaN, vô cực hoặc số ngoài phạm vi `jlong`.

Hàm `unsignedByte` nhận `jbyte -2` nhưng trả số `254` ở dạng `jint`, đúng với biểu diễn không dấu của một octet `0xFE`.

### 11.3. Biên dịch và chạy trên Linux

Yêu cầu: JDK 17+, compiler C hỗ trợ C11, biến môi trường `JAVA_HOME` trỏ tới cùng JDK đang dùng. Đặt hai tệp trên chung một thư mục rồi chạy bằng shell POSIX:

~~~bash
javac -encoding UTF-8 -h . PrimitiveBridge.java
javap -p -s PrimitiveBridge

cc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
   -I"$JAVA_HOME/include" \
   -I"$JAVA_HOME/include/linux" \
   PrimitiveBridge.c -o libprimitivebridge.so

java -Djava.library.path=. PrimitiveBridge
~~~

`javac -h .` tạo `PrimitiveBridge.class` và header `PrimitiveBridge.h`, trong đó khai báo đúng chữ ký JNI để compiler C kiểm tra. Các tệp `libprimitivebridge.so`, `primitivebridge.dll` hoặc `libprimitivebridge.dylib` có quy ước tên riêng theo nền tảng; lệnh `cc` và include path ở trên dành cho **Linux**. Đối với Windows hoặc macOS cần compiler, cờ tạo shared library và đường dẫn include JNI tương ứng; không sao chép nguyên cờ `-fPIC`/`include/linux` sang mọi hệ.

Kết quả của **lệnh Java cuối**:

~~~text
total=3000201067
unsignedByte=254
~~~

Có thể kiểm lại `total` theo phép cộng: `1 + (-2) + 65 + 1000 + 200000 + 3000000000 + 1 + 2 = 3000201067`. Nếu JVM không tìm thấy shared library, `System.loadLibrary` ném `UnsatisfiedLinkError` trước khi gọi method; đó là lỗi nạp thư viện, không phải bằng chứng bảng ánh xạ sai.

### 11.4. Điều cần kiểm tra trong header sinh tự động

Phần khai báo native C từ header sẽ có kiểu trả về và danh sách tham số tương đương:

~~~c
JNIEXPORT jlong JNICALL Java_PrimitiveBridge_total
  (JNIEnv *, jclass, jboolean, jbyte, jchar, jshort,
   jint, jlong, jfloat, jdouble);

JNIEXPORT jint JNICALL Java_PrimitiveBridge_unsignedByte
  (JNIEnv *, jclass, jbyte);
~~~

Đây là prototype minh họa phần có ý nghĩa; header thực còn có include guard và các macro/annotation do JDK sinh ra. Vì lớp `PrimitiveBridge` trong package mặc định và không có overload, symbol trong ví dụ đơn giản; các tên được tạo cho lớp có package hoặc overload có quy tắc JNI name mangling khác. Hãy dùng kết quả thực của `javac -h` làm nguồn xác nhận.

## 12. JNI API dùng đúng họ kiểu primitive

Kiểu JNI xuất hiện không chỉ trong tham số của native method mà còn trong các nhóm API gọi method, truy cập field và mảng. Chẳng hạn:

| Java kind | JNI scalar | Ví dụ method call API | Ví dụ field getter | Array reference |
| --- | --- | --- | --- | --- |
| boolean | `jboolean` | `CallBooleanMethod` | `GetBooleanField` | `jbooleanArray` |
| byte | `jbyte` | `CallByteMethod` | `GetByteField` | `jbyteArray` |
| char | `jchar` | `CallCharMethod` | `GetCharField` | `jcharArray` |
| short | `jshort` | `CallShortMethod` | `GetShortField` | `jshortArray` |
| int | `jint` | `CallIntMethod` | `GetIntField` | `jintArray` |
| long | `jlong` | `CallLongMethod` | `GetLongField` | `jlongArray` |
| float | `jfloat` | `CallFloatMethod` | `GetFloatField` | `jfloatArray` |
| double | `jdouble` | `CallDoubleMethod` | `GetDoubleField` | `jdoubleArray` |

Ví dụ một C function cần gọi instance Java method trả `int`:

~~~c
/* Đoạn minh họa bên trong native code có sẵn env, object, methodId. */
jint result = (*env)->CallIntMethod(env, object, methodId);
if ((*env)->ExceptionCheck(env)) {
    /* Không sử dụng result như kết quả bình thường khi còn exception. */
}
~~~

`CallIntMethod` phải ghép với Java method trả về `int`/descriptor `I`; nếu method trả `long`, dùng `CallLongMethod` và `jlong`. Với `static` có các họ API `CallStaticIntMethod`, `GetStaticIntField` tương ứng. Với instance method trả `void` dùng `CallVoidMethod`, không có `jvoid`.

Khi làm việc với array:

- `GetArrayLength` trả `jsize` (kiểu độ dài mảng trong JNI; tương đương `jint` theo đặc tả), **không** phải `size_t` của native allocator.
- `GetIntArrayRegion` và `SetIntArrayRegion` thao tác `jintArray` với buffer `jint *` theo offset và số phần tử.
- `GetFloatArrayElements` trả `jfloat *` có thể là copy hoặc vùng truy cập trực tiếp tùy JVM. Nếu gọi hàm Get...Elements, phải thực hiện đúng cặp Release...Elements và thời gian sống pointer.
- Từng loại mảng có API riêng: `GetByteArrayRegion` không được dùng với `jcharArray` hay `jintArray`.

Độ dài và các loại pointer có **quy tắc chuyển đổi riêng**. Truyền `jlong` tùy ý vào tham số `jsize` mà không kiểm tra giới hạn có thể khiến nó bị thu hẹp hoặc sai giá trị.

## 13. Các trường hợp biên phải hiểu rõ

### 13.1. `boolean` khác số nguyên 0/1 trong type descriptor

`boolean` có descriptor `Z`. `int` có descriptor `I`. Dù API nội bộ ứng dụng biểu diễn trạng thái bằng 0 và 1, Java method `native boolean isValid()` và `native int isValid()` có **chữ ký trả về khác nhau**. Không sửa prototype C từ `jboolean` thành `jint` chỉ vì “đều trả 0 hoặc 1”.

### 13.2. `char` không thể chứa mọi ký tự Unicode

Java `char` là code unit 16 bit, nên một code point ngoài BMP cần surrogate pair. JNI `jchar` truyền **một code unit**, không tự ghép cặp. Nếu muốn truyền Unicode code point đã giải mã, hãy xác định rõ hợp đồng nhận `jint` chứa scalar value hợp lệ hoặc truyền `String`/`jstring` và xử lý UTF-16 cho đầy đủ. Code point trong khoảng surrogate U+D800..U+DFFF không phải Unicode scalar value hợp lệ.

### 13.3. `jbyte` có dấu; số học bit có thể cần mask

Raw byte `0xFF` trong `jbyte` là -1. Cần xử lý dưới nghĩa unsigned? Hãy mask với `0xFF` sau khi mở rộng để được 255. Ngược lại, **không** mask mọi tham số `jbyte` nếu bài toán thực sự dùng số có dấu, ví dụ chênh lệch nhiệt độ mã hóa kiểu signed.

### 13.4. Native `long` khác `jlong`

Một C library có tham số `long nativeCounter` không tự đảm bảo nhận mọi giá trị Java `long`. Nếu muốn API JNI ổn định, nhận `jlong` rồi chuyển sang kiểu thư viện phía dưới sau kiểm tra min/max. Trên Windows 64-bit, C `long` thường có 32 bit dù con trỏ có 64 bit.

### 13.5. Tràn số và narrowing không tự có kiểm tra

JNI truyền giá trị primitive hợp lệ theo kiểu của nó. Nếu native code tự cộng hai `jint` lớn rồi gây **signed integer overflow** trong C, hành vi có thể không được xác định theo C; không dựa vào cơ chế Java `int` wrap 32-bit ở biểu thức tương ứng. Khi cần tính lớn hơn, mở rộng sang `jlong` trước khi cộng và kiểm tra tràn. Với tổng các `jlong` rất lớn, cần kiểm tra biên trước khi thực hiện phép cộng.

### 13.6. NaN, vô cực và signed zero

`jfloat`/`jdouble` mang số thực; NaN, infinity và dấu của zero phải được xem xét nếu thuật toán phụ thuộc giá trị biên. `==` không phải cách nhận diện NaN; trên Java dùng `Float.isNaN`/`Double.isNaN`, trên C dùng `isnan`. Raw bit pattern giữa các NaN có thể bị canonicalization ở một số thao tác; không sử dụng NaN payload làm kênh dữ liệu portable khi hợp đồng không quy định.

### 13.7. Descriptor và JNI name mangling là hai việc khác

`(I)J` mô tả method nhận int và trả long. Symbol C `Java_package_Class_method` gắn với cách JVM tìm JNI native implementation; khi method overload, tên native có thể thêm encoding của kiểu tham số. Không dựng symbol bằng cách ghép descriptor thủ công: `javac -h` sẽ tạo header chứa tên đúng và chữ ký C.

### 13.8. Primitive scalar và reference có quy tắc vòng đời khác

Scalar `jint`/`jdouble` là giá trị truyền vào hàm; không “release primitive value”. `jstring`, `jobject`, `jintArray` là JNI handles. Khi lấy pointer vào nội dung mảng/chuỗi qua JNI, phải tuân thủ acquire/release và hạn chế thời gian sử dụng. Đừng lưu pointer sang một hoạt động asynchronous sau khi release.

## 14. Checklist khi code review JNI primitive bridge

1. **Khớp bảng kiểu:** Java `boolean/byte/char/short/int/long/float/double` ↔ JNI `jboolean/jbyte/jchar/jshort/jint/jlong/jfloat/jdouble`?
2. **Khớp descriptor:** `Z/B/C/S/I/J/F/D` và return type; `V` chỉ cho method trả void?
3. **Đúng JNI entry point:** `JNIEXPORT`, `JNICALL`, `JNIEnv *`, `jobject` hoặc `jclass`, thứ tự tham số và header `javac -h`?
4. **Đúng ngữ nghĩa byte/char:** `jbyte` signed, `jchar` unsigned UTF-16 code unit, `String` là `jstring`, array là `j<type>Array`?
5. **Không dùng độ rộng C theo cảm giác:** `long`/`wchar_t`/`bool` và `size_t` không tự tương thích với `jlong`/`jchar`/`jboolean`/`jsize`?
6. **Kiểm tra narrowing/overflow:** mọi giá trị được biểu diễn trong kiểu đích, cộng/nhân số nguyên không tràn signed C?
7. **Số thực:** chấp nhận và kiểm soát rounding, NaN, infinities, ±0 và các phép cast không an toàn?
8. **Thử đúng các giá trị biên:** -128/127 cho byte; 0x00/0xFF theo nghĩa octet; U+0000/U+FFFF và surrogate cho char; min/max int/long; 0.1, NaN, ±Infinity cho float/double khi giao thức cho phép?
9. **Kiểm thử độc lập:** chạy `javac -h`, kiểm header, thử chương trình Java ↔ C trên ABI mục tiêu, đo kết quả thực thay vì chỉ nhìn code?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Java `native long convert(int a, short b);` có descriptor và kiểu C return gì?

Đáp án: descriptor `(IS)J`; return `jlong`, tham số Java lần lượt `jint` và `jshort`, ngoài hai tham số JNI ẩn.

**Câu 2.** Tại sao `char c = '中';` không tương ứng C `char c`?

Đáp án: Java `char`/JNI `jchar` là UTF-16 code unit 16 bit không dấu; `'中'` có giá trị 0x4E2D (20013). C `char` thường có 8 bit, không chứa được giá trị đó.

**Câu 3.** Nếu Java truyền `(byte)0xFF` cho native method nhận byte, `jbyte` có giá trị nào? Muốn đọc nó như unsigned octet thì làm gì?

Đáp án: giá trị `-1`; dùng `((jint)value) & 0xFF` để được 255, khi hợp đồng dữ liệu yêu cầu unsigned 8-bit.

**Câu 4.** C `long` có luôn đủ chứa `jlong` không?

Đáp án: không. `jlong` là signed 64-bit theo JNI; C `long` có thể 32-bit hoặc 64-bit tùy data model/ABI. Kiểm tra trước khi chuyển.

**Câu 5.** JNI method nhận `float` và trả `double` có descriptor gì?

Đáp án: `(F)D`; ở C tương ứng tham số `jfloat` và kiểu trả về `jdouble`.

**Câu 6.** Tại sao `double` không khôi phục được độ chính xác bị mất khi `float` đã được làm tròn?

Đáp án: mở rộng sang binary64 giữ chính xác **giá trị binary32 đã làm tròn**, không khôi phục giá trị số gốc trước đó.

**Câu 7.** `char[]` có descriptor `C` hay `[C`? Tham số JNI C là `jchar *` hay `jcharArray`?

Đáp án: `[C` và `jcharArray`. `C` chỉ là scalar `char`; muốn lấy các phần tử mảng phải qua JNI array APIs.

## Tài liệu đọc thêm

- [JNI Types and Data Structures (đặc tả JNI)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): bảng primitive, reference, `jvalue` và JNI type signatures.
- [JNI Native Method Interface (đặc tả)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): hàm native, dynamic linking, cách đặt tên native methods.
- [JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): các hàm làm việc với mảng, chuỗi, gọi method và truy cập field.
- [Java SE 17 `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tùy chọn `-h` sinh JNI header.
- [Java SE 17 `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): tùy chọn `-s` hiển thị descriptor.

**Ghi nhớ:** khi Java gọi JNI, giá trị scalar được trao đổi qua các kiểu `j...` có độ rộng và ý nghĩa xác định. `char` là UTF-16 code unit, `byte` có dấu, `long` là 64 bit, số thực có quy tắc IEEE 754; descriptor `Z B C S I J F D` mô tả kiểu cho JVM. Việc giữ nguyên giá trị phụ thuộc vào **đúng chữ ký và quy tắc chuyển đổi**, không phụ thuộc vào suy đoán kiểu C theo tên.
