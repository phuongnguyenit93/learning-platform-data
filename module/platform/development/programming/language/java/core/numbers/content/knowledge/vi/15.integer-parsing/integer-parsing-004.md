# `parseUnsignedInt` và `parseUnsignedLong` trong Java

## 1. Mục tiêu: đọc chuỗi biểu diễn số nguyên **không dấu**

Java có primitive `int` (32 bit) và `long` (64 bit) **có dấu**, nhưng các giao thức nhị phân, dữ liệu hệ thống, checksum, mã định danh hoặc trường bit có thể mô tả cùng 32/64 bit dưới dạng **số nguyên không dấu** (*unsigned integer*).

Hai phương thức:

- `Integer.parseUnsignedInt(String s)`
- `Long.parseUnsignedLong(String s)`

giúp **phân tích một chuỗi ký tự chứa giá trị không dấu** rồi đưa **mẫu bit tương ứng** vào primitive `int` hoặc `long`. Chúng cũng có overload nhận **cơ số** (`radix`) và overload đọc một **đoạn `CharSequence`** theo chỉ số.

Điều đặc biệt: Java **không có primitive riêng `uint` hoặc `ulong`**. Vì vậy giá trị toán học không dấu ở nửa trên của miền sẽ được lưu trong `int`/`long` dưới dạng số **âm khi diễn giải có dấu**. Đây là hành vi có chủ đích, không có nghĩa quá trình parse đã thất bại.

Ví dụ:

~~~java
int bits32 = Integer.parseUnsignedInt("4294967295");
long bits64 = Long.parseUnsignedLong("18446744073709551615");

System.out.println(bits32);                    // -1
System.out.println(bits64);                    // -1
System.out.println(Integer.toUnsignedString(bits32)); // 4294967295
System.out.println(Long.toUnsignedString(bits64));    // 18446744073709551615
~~~

Đây là **mã minh họa**, chưa phải một chương trình Java độc lập. Hai giá trị âm `-1` chỉ là cách **diễn giải có dấu** của những bit toàn 1. Các hàm `toUnsignedString` hiển thị cùng bit dưới dạng giá trị không dấu như văn bản.

**Ý chính:** `parseUnsigned...` phân tích **chuỗi không dấu**, không tự tạo kiểu số nguyên không dấu mới. Để so sánh, chia, lấy dư hoặc in theo nghĩa unsigned, phải tiếp tục sử dụng các API unsigned phù hợp.

## 2. Miền biểu diễn và ý nghĩa của mẫu bit

| Primitive lưu kết quả | Độ rộng | Miền signed thường gặp | Miền giá trị unsigned mà parser chấp nhận |
|---|---:|---|---|
| `int` | 32 bit | `-2147483648` đến `2147483647` | `0` đến `4294967295` (`2^32 - 1`) |
| `long` | 64 bit | `-9223372036854775808` đến `9223372036854775807` | `0` đến `18446744073709551615` (`2^64 - 1`) |

Các ngưỡng quan trọng:

- `Integer.MAX_VALUE = 2147483647`: giá trị dương signed lớn nhất của `int`.
- `2147483648`: giá trị unsigned đầu tiên vượt miền dương signed `int`, lưu được bằng mẫu bit `0x80000000` và khi in signed sẽ là `-2147483648`.
- `4294967295`: unsigned 32 bit lớn nhất, mẫu bit `0xFFFFFFFF`, khi in signed là `-1`.
- `Long.MAX_VALUE = 9223372036854775807`.
- `9223372036854775808`: giá trị unsigned đầu tiên vượt miền dương signed `long`, mẫu bit `0x8000000000000000` và khi in signed là `Long.MIN_VALUE`.
- `18446744073709551615`: unsigned 64 bit lớn nhất, mẫu bit toàn 1, khi in signed là `-1L`.

Khi parser nhận một giá trị `u` trong miền unsigned của độ rộng `N`:

\[
\text{stored signed} =
\begin{cases}
u & 0 \le u < 2^{N-1}\\
u - 2^N & 2^{N-1} \le u < 2^N
\end{cases}
\]

Công thức dùng để giải thích hai cách diễn giải **cùng một mẫu bit**; đây không phải quy tắc “Java đã tự động trừ đi `2^N` trong giao thức”. Giá trị âm mà bạn thấy là biểu diễn signed của kết quả.

Nếu chuỗi đầu vào là `"4294967296"` hoặc `"18446744073709551616"`, nó **vượt miền unsigned** tương ứng và parser ném `NumberFormatException`. Parser **không lấy phần dư modulo `2^N` để im lặng nhận chuỗi vượt miền**.

## 3. Các overload và kiểu trả về

### `Integer.parseUnsignedInt`

~~~java
static int Integer.parseUnsignedInt(String s)
static int Integer.parseUnsignedInt(String s, int radix)
static int Integer.parseUnsignedInt(
        CharSequence s, int beginIndex, int endIndex, int radix)
~~~

Đây là **chữ ký API rút gọn** để đọc, không phải các khai báo bạn cần tự viết trong Java.

- Không có tham số `radix`: sử dụng **cơ số 10**.
- Có `radix`: diễn giải chữ số trong **cơ số chỉ định**.
- Có `CharSequence` và chỉ số: chỉ phân tích đoạn **`[beginIndex, endIndex)`**, tức lấy `beginIndex` nhưng **không lấy** ký tự ở `endIndex`.
- Kết quả là primitive **`int`**, không phải `long` hoặc đối tượng unsigned riêng.

### `Long.parseUnsignedLong`

~~~java
static long Long.parseUnsignedLong(String s)
static long Long.parseUnsignedLong(String s, int radix)
static long Long.parseUnsignedLong(
        CharSequence s, int beginIndex, int endIndex, int radix)
~~~

Tương tự, kết quả là primitive **`long`** với mẫu 64 bit tương ứng.

Hai overload `CharSequence` có trong các JDK hiện đại và **sử dụng được với Java 17+**. Chúng hữu ích khi bạn cần trích số từ bản ghi chứa nhiều trường mà không muốn tạo `substring` trung gian chỉ để gọi parser. Dữ liệu nguồn vẫn phải hợp lệ trong phạm vi chỉ số; nếu `CharSequence` bị sửa đồng thời khi parse, không nên giả định hành vi ổn định.

### API đối chiếu

| Phương thức | Miền chuỗi chấp nhận | Trả về |
|---|---|---|
| `Integer.parseInt` | Số nguyên signed 32 bit | `int` |
| `Integer.parseUnsignedInt` | Số nguyên unsigned 32 bit | `int` |
| `Long.parseLong` | Số nguyên signed 64 bit | `long` |
| `Long.parseUnsignedLong` | Số nguyên unsigned 64 bit | `long` |

Một chuỗi giá trị 4.000.000.000 là hợp lệ cho `Integer.parseUnsignedInt` nhưng không hợp lệ cho `Integer.parseInt`, vì vượt `Integer.MAX_VALUE`. **Cùng kiểu trả về không có nghĩa hai parser kiểm tra cùng miền đầu vào.**

## 4. Ví dụ Java 17+: biên signed và unsigned

Tạo tệp `UnsignedParsingBasicsDemo.java`:

~~~java
public class UnsignedParsingBasicsDemo {
    public static void main(String[] args) {
        int intMaxBits = Integer.parseUnsignedInt("4294967295");
        int intHighBits = Integer.parseUnsignedInt("2147483648");
        long longMaxBits =
                Long.parseUnsignedLong("18446744073709551615");
        long longHighBits =
                Long.parseUnsignedLong("9223372036854775808");

        System.out.println("intMaxSigned=" + intMaxBits);
        System.out.println("intMaxUnsigned="
                + Integer.toUnsignedString(intMaxBits));
        System.out.println("intHighSigned=" + intHighBits);
        System.out.println("intHighUnsigned="
                + Integer.toUnsignedString(intHighBits));

        System.out.println("longMaxSigned=" + longMaxBits);
        System.out.println("longMaxUnsigned="
                + Long.toUnsignedString(longMaxBits));
        System.out.println("longHighSigned=" + longHighBits);
        System.out.println("longHighUnsigned="
                + Long.toUnsignedString(longHighBits));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac UnsignedParsingBasicsDemo.java
java UnsignedParsingBasicsDemo
~~~

Đầu ra:

~~~text
intMaxSigned=-1
intMaxUnsigned=4294967295
intHighSigned=-2147483648
intHighUnsigned=2147483648
longMaxSigned=-1
longMaxUnsigned=18446744073709551615
longHighSigned=-9223372036854775808
longHighUnsigned=9223372036854775808
~~~

**Giải thích:** cùng một biến `intMaxBits` có thể được hiển thị là `-1` hoặc `4294967295`, tùy chọn cách diễn giải signed/unsigned khi chuyển thành văn bản. Không có thao tác nào “sửa lại” bit trong biến: `Integer.toUnsignedString` chỉ dùng **quy tắc định dạng không dấu**.

## 5. Cơ số từ 2 đến 36 và các ký tự chữ số

Khi chỉ định `radix`, Java hỗ trợ các cơ số hợp lệ từ `Character.MIN_RADIX` (2) đến `Character.MAX_RADIX` (36). Những ký tự `0..9` được dùng cho các giá trị 0..9; ở cơ số lớn hơn 10, `A..Z` hoặc `a..z` có thể biểu diễn giá trị từ 10 đến 35 theo các quy tắc phân tích chữ số của Java.

Một vài ví dụ:

~~~java
int binary = Integer.parseUnsignedInt("1010", 2);  // 10
int hex = Integer.parseUnsignedInt("ff", 16);      // 255
int base36 = Integer.parseUnsignedInt("Z", 36);    // 35
long maxHex = Long.parseUnsignedLong(
        "FFFFFFFFFFFFFFFF", 16); // mẫu bit 64 bit toàn 1, signed -1
~~~

Đây là đoạn minh họa. Khi in dưới dạng unsigned:

~~~java
Integer.toUnsignedString(hex, 16);    // "ff"
Long.toUnsignedString(maxHex, 16);   // "ffffffffffffffff"
~~~

Cơ số `10` là mặc định cho overload chỉ có `String`. **Không nhầm radix với tiền tố văn bản**: `parseUnsignedInt("0xFF", 16)` không tự bỏ `0x`. Nếu chuỗi giao thức có tiền tố `0x`, bạn phải kiểm tra và bỏ tiền tố trước, rồi parse phần chữ số ở cơ số 16.

Tương tự, `0b` không tự được nhận diện. `Integer.parseUnsignedInt("0007")` trong cơ số 10 trả 7; các số 0 đứng đầu **không tự chuyển chuỗi thành cơ số 8**.

### Chữ số Unicode và ràng buộc giao thức

Parser sử dụng quy tắc nhận diện chữ số theo Java/Unicode; không nên mặc định tất cả đầu vào hợp lệ **chỉ gồm ASCII** trong mọi cơ số. Nếu giao thức mạng hoặc định dạng bảo mật đòi đúng dãy ASCII `0-9` hoặc `0-9A-Fa-f`, phải **kiểm tra tập ký tự được phép** trước khi parse, không chỉ dựa vào `NumberFormatException`.

Điều này khác với việc cú pháp **literal Java trong mã nguồn** chấp nhận những dạng như `0xFF`, `0b1010` hoặc dấu gạch dưới `1_000`. Parser đang xử lý **chuỗi runtime**, không phân tích literal Java.

## 6. Đầu vào hợp lệ, dấu cộng và những trường hợp phải từ chối

Với parser unsigned, chuỗi có thể có **dấu cộng `+` đứng đầu** và các chữ số hợp lệ, nhưng **không chấp nhận dấu trừ `-` như giá trị âm**.

Một số ví dụ cơ số 10:

| Chuỗi `String` | `parseUnsignedInt` | Lý do |
|---|---|---|
| `"0"` | `0` | Cận dưới |
| `"42"` | `42` | Số dương trong miền |
| `"+42"` | `42` | Dấu `+` đầu hợp lệ |
| `"0007"` | `7` | Các số 0 đầu |
| `"4294967295"` | `-1` khi in signed | Sát cận trên unsigned 32 bit |
| `"4294967296"` | Ném `NumberFormatException` | Vượt miền unsigned 32 bit |
| `"-1"` | Ném `NumberFormatException` | Dấu trừ không được chấp nhận |
| `" 42"` | Ném `NumberFormatException` | Không tự trim khoảng trắng |
| `"4_2"` | Ném `NumberFormatException` | Dấu gạch dưới trong chuỗi runtime không hợp lệ |
| `"0xFF"` ở radix 10 | Ném `NumberFormatException` | Không tự hiểu tiền tố cơ số |

Với `Long.parseUnsignedLong`, chuỗi `"18446744073709551615"` là hợp lệ, còn `"18446744073709551616"` vượt cận trên và ném `NumberFormatException`.

**Phân biệt lỗi dữ liệu với lỗi chương trình:**

- `NumberFormatException` biểu thị chuỗi không phân tích được thành giá trị hợp lệ trong miền và cơ số chỉ định.
- Cơ số ngoài miền 2..36 làm thao tác không hợp lệ; đừng gửi radix từ người dùng vào API mà không kiểm tra.
- Với overload đoạn `CharSequence`, chỉ số ngoài biên hoặc đoạn không hợp lệ là lỗi của phạm vi đọc, cần kiểm soát riêng.
- Đừng dựa vào **nội dung thông điệp exception** làm giao thức xử lý lỗi: các phiên bản JDK có thể mô tả lỗi khác nhau.

Nên quyết định rõ liệu ứng dụng có cho phép khoảng trắng đầu/cuối, dấu cộng, số 0 thừa, chữ cái hex viết hoa/thường hoặc các dạng chữ số Unicode. Parser không thay thế **quy tắc định dạng dữ liệu của giao thức**.

## 7. Ví dụ Java 17+: bắt lỗi parse và xác thực miền

Tạo tệp `UnsignedInputValidationDemo.java`:

~~~java
public class UnsignedInputValidationDemo {
    static void checkInt(String source) {
        try {
            int bits = Integer.parseUnsignedInt(source);
            System.out.println("int[" + source + "]="
                    + Integer.toUnsignedString(bits));
        } catch (NumberFormatException ex) {
            System.out.println("int[" + source + "]=INVALID");
        }
    }

    static void checkLong(String source) {
        try {
            long bits = Long.parseUnsignedLong(source);
            System.out.println("long[" + source + "]="
                    + Long.toUnsignedString(bits));
        } catch (NumberFormatException ex) {
            System.out.println("long[" + source + "]=INVALID");
        }
    }

    public static void main(String[] args) {
        checkInt("4294967295");
        checkInt("4294967296");
        checkInt("-1");
        checkInt("+42");
        checkInt(" 42");
        checkInt("4_2");
        checkInt("0xFF");

        checkLong("18446744073709551615");
        checkLong("18446744073709551616");
        checkLong("-1");
    }
}
~~~

~~~bash
javac UnsignedInputValidationDemo.java
java UnsignedInputValidationDemo
~~~

Đầu ra:

~~~text
int[4294967295]=4294967295
int[4294967296]=INVALID
int[-1]=INVALID
int[+42]=42
int[ 42]=INVALID
int[4_2]=INVALID
int[0xFF]=INVALID
long[18446744073709551615]=18446744073709551615
long[18446744073709551616]=INVALID
long[-1]=INVALID
~~~

Ví dụ bắt đúng `NumberFormatException` rồi hiển thị **giá trị unsigned** hoặc trạng thái `INVALID`. Ứng dụng thực tế nên cung cấp lỗi có ngữ cảnh như trường nào sai, miền nào cho phép, và có thể hạn chế độ dài/tập ký tự trước khi parse để tránh đầu vào không phù hợp với giao thức.

Không nên nuốt mọi exception bằng `catch (Exception)` và trả `0`: điều đó trộn lẫn số 0 hợp lệ với chuỗi hỏng, che khuất lỗi và khiến khó chẩn đoán.

## 8. Dùng overload `CharSequence` cho một phần chuỗi

Từ Java 9, các overload sau cho phép parse trực tiếp **một khoảng chỉ số** của chuỗi:

~~~java
Integer.parseUnsignedInt(text, beginIndex, endIndex, radix)
Long.parseUnsignedLong(text, beginIndex, endIndex, radix)
~~~

Dữ liệu được xem là dãy ký tự `text[beginIndex .. endIndex-1]`. Ví dụ, một bản ghi lưu hex 16 bit trong chuỗi `"id=FFFF;"` có phần số bắt đầu từ chỉ số 3 và kết thúc **trước** chỉ số 7.

Tạo tệp `UnsignedRadixSliceDemo.java`:

~~~java
public class UnsignedRadixSliceDemo {
    public static void main(String[] args) {
        int binary = Integer.parseUnsignedInt("1010", 2);
        int hex = Integer.parseUnsignedInt("ff", 16);
        int base36 = Integer.parseUnsignedInt("Z", 36);

        String record = "id=FFFF;";
        int sliced = Integer.parseUnsignedInt(record, 3, 7, 16);

        long longHex =
                Long.parseUnsignedLong("FFFFFFFFFFFFFFFF", 16);

        System.out.println("binary=" + binary);
        System.out.println("hex=" + hex);
        System.out.println("base36=" + base36);
        System.out.println("slice=" + sliced);
        System.out.println("hexBack="
                + Integer.toUnsignedString(hex, 16));
        System.out.println("longHex="
                + Long.toUnsignedString(longHex, 16));
    }
}
~~~

~~~bash
javac UnsignedRadixSliceDemo.java
java UnsignedRadixSliceDemo
~~~

Đầu ra:

~~~text
binary=10
hex=255
base36=35
slice=65535
hexBack=ff
longHex=ffffffffffffffff
~~~

Cần **tự xác minh ranh giới trường** `beginIndex`/`endIndex` trước khi dùng với bản ghi biến độ dài. Nếu chuỗi có dấu phân cách, không lấy vị trí cố định khi định dạng có thể thay đổi. Việc dùng overload đoạn giúp tránh tạo thêm `substring` trong một số tình huống, nhưng **không bảo đảm** nhanh hơn cho mọi đầu vào/JVM; đo đạc nếu hiệu năng là yêu cầu thực sự.

## 9. Parse unsigned không đồng nghĩa toán tử số học thành unsigned

Sau khi parse, biến vẫn là `int` hoặc `long` signed. Vì vậy:

~~~java
int a = Integer.parseUnsignedInt("4294967295");
int b = 2;

System.out.println(a);           // -1
System.out.println(a > b);       // false: phép so sánh signed!
System.out.println(a / b);       // 0: phép chia signed (-1 / 2)
~~~

Đây là đoạn minh họa. Nếu mong ý nghĩa “4.294.967.295 lớn hơn 2”, `a > b` không phù hợp. Java cung cấp các API unsigned:

| Mục tiêu | Dạng 32 bit | Dạng 64 bit |
|---|---|---|
| So sánh | `Integer.compareUnsigned(a,b)` | `Long.compareUnsigned(a,b)` |
| Chia | `Integer.divideUnsigned(a,b)` | `Long.divideUnsigned(a,b)` |
| Lấy dư | `Integer.remainderUnsigned(a,b)` | `Long.remainderUnsigned(a,b)` |
| Hiển thị thập phân | `Integer.toUnsignedString(a)` | `Long.toUnsignedString(a)` |
| Hiển thị cơ số khác | `Integer.toUnsignedString(a,radix)` | `Long.toUnsignedString(a,radix)` |

Với mẫu 32 bit, `Integer.toUnsignedLong(a)` chuyển **giá trị unsigned 32 bit** thành `long` không âm, vì toàn bộ khoảng 0..4294967295 vừa trong `long`.

Với mẫu 64 bit, **không thể lưu tất cả các giá trị unsigned 64 bit dưới dạng số dương trong primitive `long`**. Nếu bài toán cần độ lớn dương chính xác của những số vượt `Long.MAX_VALUE`, dùng `BigInteger` hoặc biểu diễn chuỗi unsigned.

### Ví dụ Java 17+: so sánh, chia và lấy dư không dấu

Tạo tệp `UnsignedArithmeticDemo.java`:

~~~java
public class UnsignedArithmeticDemo {
    public static void main(String[] args) {
        int a = Integer.parseUnsignedInt("4294967295");
        int two = 2;

        System.out.println("signedValue=" + a);
        System.out.println("unsignedValue="
                + Integer.toUnsignedString(a));
        System.out.println("signedCompare=" + (a > two));
        System.out.println("unsignedCompare="
                + (Integer.compareUnsigned(a, two) > 0));
        System.out.println("unsignedDivision="
                + Integer.divideUnsigned(a, two));
        System.out.println("unsignedRemainder="
                + Integer.remainderUnsigned(a, two));
        System.out.println("widenedUnsigned="
                + Integer.toUnsignedLong(a));

        long big = Long.parseUnsignedLong("18446744073709551615");
        System.out.println("bigUnsigned="
                + Long.toUnsignedString(big));
        System.out.println("bigCompare="
                + (Long.compareUnsigned(big, 1L) > 0));
        System.out.println("bigDivision="
                + Long.toUnsignedString(Long.divideUnsigned(big, 2L)));
        System.out.println("bigRemainder="
                + Long.toUnsignedString(Long.remainderUnsigned(big, 2L)));
    }
}
~~~

~~~bash
javac UnsignedArithmeticDemo.java
java UnsignedArithmeticDemo
~~~

Đầu ra:

~~~text
signedValue=-1
unsignedValue=4294967295
signedCompare=false
unsignedCompare=true
unsignedDivision=2147483647
unsignedRemainder=1
widenedUnsigned=4294967295
bigUnsigned=18446744073709551615
bigCompare=true
bigDivision=9223372036854775807
bigRemainder=1
~~~

Chỉ có **cách diễn giải mẫu bit** thay đổi, không phải kiểu primitive. Chú ý `Integer.divideUnsigned` trả **`int`** và `Long.divideUnsigned` trả **`long`**: nếu thương unsigned lại vượt miền signed, in trực tiếp bằng `println` vẫn có thể trông âm; nên dùng `toUnsignedString` nếu cần hiển thị đúng.

**Cộng, trừ, nhân trong `int`/`long`** vẫn tính theo độ rộng cố định modulo `2^32`/`2^64` khi overflow theo cách Java quy định. Parse unsigned không ngăn wraparound. Nếu cần kiểm tra miền unsigned mà không được cuốn vòng, phải xây dựng logic kiểm tra riêng hoặc chọn kiểu số rộng đủ.

## 10. `BigInteger` khi cần giá trị toán học chính xác ngoài miền signed

Với unsigned 32 bit, cách dễ hiểu để có giá trị **không âm trong primitive** là:

~~~java
int bits = Integer.parseUnsignedInt("4294967295");
long unsignedMagnitude = Integer.toUnsignedLong(bits); // 4294967295
~~~

Với unsigned 64 bit, hãy dùng `BigInteger` nếu chương trình cần tính **độ lớn toán học chính xác** của 18.446.744.073.709.551.615:

~~~java
String text = "18446744073709551615";
long bits = Long.parseUnsignedLong(text);
java.math.BigInteger magnitude =
        new java.math.BigInteger(Long.toUnsignedString(bits));
~~~

Đây là đoạn minh họa. `new BigInteger(text)` cũng phân tích được chuỗi thập phân unsigned lớn đó vì `BigInteger` không giới hạn ở 64 bit. Nhưng `Long.parseUnsignedLong` vẫn hữu ích nếu mục tiêu trước hết là giữ **64 bit** để trao đổi trong cấu trúc/protocol Java.

### Ví dụ Java 17+: đối chiếu giá trị chính xác và wraparound

Tạo tệp `UnsignedBigIntegerDemo.java`:

~~~java
import java.math.BigInteger;

public class UnsignedBigIntegerDemo {
    public static void main(String[] args) {
        String maxUnsigned = "18446744073709551615";

        long bits = Long.parseUnsignedLong(maxUnsigned);
        BigInteger exact = new BigInteger(maxUnsigned);
        BigInteger recovered =
                new BigInteger(Long.toUnsignedString(bits));

        System.out.println("storedSigned=" + bits);
        System.out.println("recovered=" + recovered);
        System.out.println("matches=" + exact.equals(recovered));
        System.out.println("exactPlusOne="
                + exact.add(BigInteger.ONE));
        System.out.println("longPlusOneUnsigned="
                + Long.toUnsignedString(bits + 1L));
    }
}
~~~

~~~bash
javac UnsignedBigIntegerDemo.java
java UnsignedBigIntegerDemo
~~~

Đầu ra:

~~~text
storedSigned=-1
recovered=18446744073709551615
matches=true
exactPlusOne=18446744073709551616
longPlusOneUnsigned=0
~~~

Dòng `longPlusOneUnsigned=0` là **wraparound**: mẫu bit 64 bit toàn 1 cộng 1 trở thành 64 bit toàn 0. `BigInteger` tiếp tục biểu diễn kết quả tăng thêm 1 chính xác. Lựa chọn nào đúng tùy giao thức: checksum/bit field có thể cố ý làm modulo `2^64`, trong khi tính tiền/số lượng/bản ghi phải có chính sách không làm mất giá trị.

## 11. Chuyển đổi qua lại và round-trip đúng nghĩa

Nếu một trường được định nghĩa **unsigned 32 bit** hoặc **unsigned 64 bit**, hãy thiết kế luồng xử lý rõ ràng:

1. **Đầu vào từ chuỗi:** parse bằng `Integer.parseUnsignedInt` / `Long.parseUnsignedLong` với radix đã định.
2. **Lưu trữ:** giữ mẫu bit trong `int` / `long`.
3. **Tính toán:** dùng các API signed/unsigned theo đúng ngữ nghĩa mong muốn.
4. **Xuất văn bản:** dùng `Integer.toUnsignedString` / `Long.toUnsignedString` với radix mong muốn.
5. **Kiểm tra:** round-trip chuỗi → mẫu bit → chuỗi → mẫu bit có giữ nguyên giá trị/số bit hay không.

Ví dụ:

~~~java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
String out = Integer.toUnsignedString(bits, 16); // "ffffffff"
int parsedAgain = Integer.parseUnsignedInt(out, 16);
boolean sameBits = bits == parsedAgain; // true
~~~

Round-trip ở đây giữ giá trị **bit**, nhưng **không giữ nguyên kiểu chữ hoa/thường của chuỗi ban đầu**. Nếu giao thức yêu cầu hex uppercase hoặc đệm đúng 8/16 chữ số, hãy định dạng riêng; `toUnsignedString` không tự chèn số 0 đứng đầu và thường xuất chữ cái thường theo radix.

**Kiểm thử biên bắt buộc:** `0`, `1`, signed max, unsigned min nằm trên signed max, unsigned max, chuỗi vượt cận trên đúng 1, các cơ số 2/10/16, prefix, leading plus, khoảng trắng, ký tự không hợp lệ.

## 12. Lỗi phổ biến và cách tránh

| Nhầm lẫn | Sự thật |
|---|---|
| “`parseUnsignedInt` trả về kiểu `uint`.” | Java không có primitive `uint`; kết quả vẫn là `int`. |
| “Chuỗi `4294967295` parse ra `-1` là bị mất dữ liệu.” | Không: mẫu 32 bit đúng, chỉ đang hiển thị signed. |
| “`parseUnsignedLong` trả về `BigInteger` khi quá `Long.MAX_VALUE`.” | Không: trả `long` giữ mẫu 64 bit; cần `BigInteger` nếu muốn độ lớn dương rộng hơn signed. |
| “`parseUnsignedInt("4294967296")` sẽ thành 0.” | Không: parser từ chối giá trị vượt miền unsigned bằng `NumberFormatException`. |
| “Unsigned parser tự cho phép dấu trừ vì kết quả có thể âm.” | Không: `"-1"` bị từ chối; số âm khi in là cách hiểu signed của mẫu bit. |
| “Có thể đưa `"0xFF"` vào radix 16 trực tiếp.” | Không: phải xử lý tiền tố `0x` trước khi parse. |
| “Gạch dưới trong literal Java cũng dùng được trong String parse.” | Không: `"1_000"` không phải chuỗi chữ số hợp lệ của parser. |
| “`parseUnsignedInt` sẽ tự trim khoảng trắng.” | Không: cần chính sách normalize/trim ngoài parser nếu cho phép. |
| “Dùng toán tử `>` sau khi parse là so sánh unsigned.” | Không: `int`/`long` vẫn so sánh signed; dùng `compareUnsigned`. |
| “Dùng `/` là chia không dấu vì số được parse unsigned.” | Không: dùng `divideUnsigned` khi cần nghĩa unsigned. |
| “Unsigned parser tự ngăn overflow khi cộng.” | Không: nó chỉ kiểm tra giới hạn **lúc parse**; các phép tính tiếp theo cần chính sách riêng. |
| “`Integer.toUnsignedString` phải trả chuỗi y hệt đầu vào.” | Không: giá trị/bit giữ, nhưng format có thể thay đổi, ví dụ hex uppercase thành lowercase. |

## 13. Checklist tích hợp vào ứng dụng thực tế

1. **Xác định độ rộng và ngữ nghĩa:** trường là signed hay unsigned, 32 hay 64 bit?
2. **Xác định radix:** 10, 16 hoặc cơ số khác; chuỗi có prefix không?
3. **Quy định dạng đầu vào:** có cho phép dấu `+`, leading zero, khoảng trắng, chữ số Unicode không? Nếu không, kiểm tra trước.
4. **Dùng đúng parser:** `Integer.parseUnsignedInt` hoặc `Long.parseUnsignedLong`; đừng dùng `parseInt`/`parseLong` nếu giá trị giao thức có thể vượt signed max.
5. **Bắt `NumberFormatException` tại ranh giới đầu vào:** biến thành lỗi cụ thể của trường dữ liệu, không âm thầm thay 0.
6. **Lưu giữ rõ nghĩa unsigned:** tên biến như `unsignedBits` hoặc mô tả cấu trúc; người đọc không được nhầm `-1` signed với lỗi.
7. **Dùng so sánh/chia/lấy dư unsigned khi cần:** `compareUnsigned`, `divideUnsigned`, `remainderUnsigned`.
8. **Dùng hàm xuất chuỗi phù hợp:** `toUnsignedString` thay vì in raw signed khi hiển thị số không dấu.
9. **Kiểm soát overflow phép tính về sau:** sử dụng `BigInteger` khi không được mất độ lớn toán học; hoặc document modulo bit-width nếu đó là chủ đích giao thức.
10. **Thử biên, radix và round-trip:** tối thiểu có unsigned max, unsigned max + 1, giá trị với bit dấu bật, ký tự sai và mọi định dạng được phép.

## 14. Bài tập tự kiểm tra

1. Vì sao `Integer.parseUnsignedInt("4294967295")` trả `int` có thể in là `-1` nhưng vẫn thành công?
2. Có thể dùng `Integer.parseInt("4294967295")` thay thế không? Vì sao?
3. `Long.parseUnsignedLong("18446744073709551615")` trả kiểu nào, và khi in signed cho số nào?
4. Chuỗi `"4294967296"` có được parser unsigned 32 bit tự lấy modulo không?
5. `Integer.parseUnsignedInt("FF", 16)` trả bao nhiêu? Chuỗi `"0xFF"` với cùng radix có được parse trực tiếp không?
6. `Integer.parseUnsignedInt("+42")` và `Integer.parseUnsignedInt("-42")` khác nhau thế nào?
7. Vì sao `Integer.parseUnsignedInt("4294967295") > 0` cho `false` dù giá trị unsigned là số dương lớn?
8. Nếu cần chia unsigned 32-bit max cho 2, nên gọi API nào?
9. Nếu cần cộng 1 vào unsigned 64-bit max **mà vẫn giữ kết quả toán học chính xác**, chọn kiểu nào?
10. Vì sao `toUnsignedString(bits, 16)` có thể không tái tạo nguyên vẹn cách viết hoa/thường của chuỗi hex đầu vào?

**Gợi ý đáp án:** (1) Mẫu 32 bit toàn 1 là unsigned max nhưng signed `-1`. (2) Không, vượt `Integer.MAX_VALUE`. (3) Primitive `long`, in signed `-1`. (4) Không, ném `NumberFormatException`. (5) 255; `"0xFF"` cần bỏ prefix. (6) `+42` hợp lệ, `-42` không hợp lệ. (7) Toán tử `>` trên `int` là signed; dùng `Integer.compareUnsigned`. (8) `Integer.divideUnsigned(bits, 2)`. (9) `BigInteger`. (10) Hàm trả biểu diễn số normalized theo radix, không giữ định dạng văn bản đầu vào.

**Ghi nhớ:** `parseUnsignedInt` và `parseUnsignedLong` kiểm tra **miền chuỗi không dấu** nhưng vẫn trả về primitive có dấu `int`/`long` **giữ nguyên mẫu bit**. Khi muốn hiển thị đúng độ lớn unsigned, dùng `toUnsignedString`; khi cần so sánh, chia hoặc lấy dư unsigned, dùng các API tương ứng. Nếu phải tính toán chính xác vượt 64 bit không dấu, dùng `BigInteger`.