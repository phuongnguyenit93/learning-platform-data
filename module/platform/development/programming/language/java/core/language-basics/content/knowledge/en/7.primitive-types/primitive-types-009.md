# Giới hạn giá trị với `MIN_VALUE`, `MAX_VALUE` và `SIZE` — Java 17+

## 1. Vấn đề cần giải quyết

Mỗi kiểu nguyên thủy Java có một **miền giá trị** hoặc một tập giá trị xác định. Muốn chọn kiểu lưu dữ liệu, kiểm tra đầu vào, hoặc tránh tràn số, bạn cần biết:

- **`MIN_VALUE`**: giới hạn dưới theo định nghĩa của kiểu (với số dấu phẩy động có một ngoại lệ rất quan trọng).
- **`MAX_VALUE`**: giá trị hữu hạn lớn nhất được biểu diễn theo kiểu đó.
- **`SIZE`**: số **bit** dùng để biểu diễn một giá trị của kiểu, **không phải số byte** và không phải kích thước object.

Trong Java, các hằng này nằm trong **wrapper classes** thuộc `java.lang`: `Byte`, `Short`, `Integer`, `Long`, `Character`, `Float` và `Double`. Bạn có thể tra chúng mà không cần tự nhập những số dài:

~~~java
System.out.println(Integer.MIN_VALUE); // -2147483648
System.out.println(Integer.MAX_VALUE); // 2147483647
System.out.println(Integer.SIZE);      // 32
~~~

**Điểm chính:** không phải mọi kiểu đều hiểu `MIN_VALUE` giống nhau. Đặc biệt, `Float.MIN_VALUE` và `Double.MIN_VALUE` **không phải giá trị âm thấp nhất**.

## 2. Bảng đầy đủ cho bốn kiểu số nguyên có dấu

| Kiểu primitive | Wrapper | `MIN_VALUE` | `MAX_VALUE` | `SIZE` (bit) | `BYTES` |
|---|---|---:|---:|---:|---:|
| `byte` | `Byte` | -128 | 127 | 8 | 1 |
| `short` | `Short` | -32.768 | 32.767 | 16 | 2 |
| `int` | `Integer` | -2.147.483.648 | 2.147.483.647 | 32 | 4 |
| `long` | `Long` | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | 64 | 8 |

**`SIZE` đo bit; `BYTES` đo byte trong biểu diễn giá trị.** Ví dụ `Integer.SIZE == 32` và `Integer.BYTES == 4`.

Với số nguyên có dấu có độ rộng `n` bit và dùng biểu diễn bù hai, miền giá trị là:

\[
-2^{n-1} \;\leq x \leq\; 2^{n-1}-1.
\]

Nhờ đó `byte` 8 bit có giá trị từ \(-2^7=-128\) đến \(2^7-1=127\). Miền âm có một giá trị nhiều hơn miền dương. Vì thế `Integer.MIN_VALUE` không thể đổi thành số dương bằng `Math.abs` trong cùng kiểu `int`.

### Ví dụ tra cứu không cần ghi nhớ số

~~~java
int smallestInt = Integer.MIN_VALUE;
int largestInt = Integer.MAX_VALUE;
long smallestLong = Long.MIN_VALUE;
long largestLong = Long.MAX_VALUE;

System.out.println(smallestInt); // -2147483648
System.out.println(largestInt);  // 2147483647
System.out.println(Long.SIZE);   // 64
~~~

**Giới hạn cố định trên mọi nền tảng Java:** `int` luôn là giá trị 32 bit và `long` luôn là giá trị 64 bit theo đặc tả, bất kể Windows, Linux, hệ điều hành hay JVM 32/64 bit.

## 3. `char`: 16 bit nhưng không thuộc nhóm số nguyên có dấu

`char` là một kiểu nguyên thủy đại diện cho **một đơn vị mã UTF-16**, không phải kiểu `short` có dấu. Java có:

| Hằng | Giá trị |
|---|---|
| `Character.MIN_VALUE` | U+0000 (giá trị số 0) |
| `Character.MAX_VALUE` | U+FFFF (giá trị số 65535) |
| `Character.SIZE` | 16 bit |
| `Character.BYTES` | 2 byte |

~~~java
System.out.println((int) Character.MIN_VALUE); // 0
System.out.println((int) Character.MAX_VALUE); // 65535
System.out.println(Character.SIZE);           // 16
~~~

**Lưu ý Unicode:** một `char` là một **UTF-16 code unit**; một ký tự Unicode ngoài vùng BMP có thể cần **hai `char`** (surrogate pair). Vì vậy `Character.SIZE == 16` không có nghĩa Java chỉ hỗ trợ Unicode đến U+FFFF, cũng không có nghĩa mọi ký tự người dùng nhìn thấy chiếm đúng một `char`.

`Character.MIN_VALUE` là ký tự điều khiển có mã 0, không phải một ký tự thường dễ nhìn thấy trên màn hình. Khi muốn in giới hạn của `char`, hãy **ép sang `int`** như ví dụ, thay vì cố hiển thị trực tiếp ký tự U+0000.

## 4. `float` và `double`: ý nghĩa `MIN_VALUE` khác số nguyên

Đây là bẫy quan trọng nhất của bài.

| Hằng | `float` | `double` |
|---|---:|---:|
| `SIZE` | 32 bit | 64 bit |
| `BYTES` | 4 byte | 8 byte |
| `MAX_VALUE` | `3.4028235E38` | `1.7976931348623157E308` |
| `MIN_VALUE` | `1.4E-45` | `4.9E-324` |
| `MIN_NORMAL` | `1.17549435E-38` | `2.2250738585072014E-308` |

**`Float.MIN_VALUE` và `Double.MIN_VALUE` là số dương nhỏ nhất khác 0 có thể biểu diễn**, ở dạng **subnormal**. Chúng **không phải** `-Float.MAX_VALUE` hoặc `-Double.MAX_VALUE`.

~~~java
System.out.println(Float.MIN_VALUE);  // 1.4E-45
System.out.println(Float.MAX_VALUE);  // 3.4028235E38
System.out.println(-Float.MAX_VALUE); // -3.4028235E38
~~~

Nếu cần **số hữu hạn thấp nhất** theo thứ tự số học, dùng **`-Float.MAX_VALUE`** hoặc **`-Double.MAX_VALUE`**.

### Vì sao có `MIN_NORMAL`?

Số dấu phẩy động nhị phân có dấu, số mũ và phần định trị. Giá trị rất gần 0 có thể nằm trong vùng **subnormal**, nơi độ chính xác hiệu dụng giảm để tạo ra các bước nhỏ tiếp cận 0. `MIN_NORMAL` là số dương nhỏ nhất ở vùng normal, còn `MIN_VALUE` là số dương subnormal nhỏ nhất khác 0.

Cặp hằng này đo **ngưỡng độ lớn của giá trị**, không bảo đảm một phép tính thập phân là chính xác. Chẳng hạn `0.1 + 0.2` ở `double` có thể khác chính xác `0.3` vì giới hạn độ chính xác nhị phân.

### Vô cực và NaN vẫn tồn tại

`MAX_VALUE` nghĩa là **giá trị hữu hạn lớn nhất**, không có nghĩa tập giá trị `double` chỉ từ `-Double.MAX_VALUE` đến `Double.MAX_VALUE`. Kiểu dấu phẩy động còn có `Infinity`, `-Infinity` và `NaN`.

~~~java
double tooLarge = Double.MAX_VALUE * 2;
System.out.println(tooLarge);           // Infinity
System.out.println(Double.isFinite(tooLarge)); // false
System.out.println(Double.isNaN(0.0 / 0.0));  // true
~~~

Nếu yêu cầu một số thực hữu hạn, **kiểm tra `Double.isFinite(value)`** (hoặc `Float.isFinite`) trước khi sử dụng. Chỉ kiểm tra `value <= Double.MAX_VALUE` chưa đủ để xác định dữ liệu hợp lệ vì NaN và các quy tắc so sánh đặc biệt.

## 5. `boolean` không có MIN_VALUE, MAX_VALUE hoặc SIZE

`boolean` chỉ có **`true` và `false`**; wrapper `Boolean` định nghĩa các giá trị như `Boolean.TRUE`, `Boolean.FALSE`.

Không có API chuẩn:

~~~java
// Boolean.MIN_VALUE // Không tồn tại
// Boolean.MAX_VALUE // Không tồn tại
// Boolean.SIZE      // Không tồn tại
~~~

Ngôn ngữ Java không đưa ra một giá trị `Boolean.SIZE` tương tự `Integer.SIZE`. Đừng tự suy ra “boolean luôn chiếm 1 bit bộ nhớ” từ việc kiểu chỉ có hai trạng thái: cách JVM lưu field, biến cục bộ, array, header và căn chỉnh là chuyện triển khai khác với **miền giá trị trừu tượng** của kiểu `boolean`.

## 6. SIZE và BYTES không đo kích thước object trong heap

Ví dụ:

~~~java
System.out.println(Byte.SIZE);      // 8
System.out.println(Integer.SIZE);   // 32
System.out.println(Long.BYTES);     // 8
System.out.println(Double.BYTES);   // 8
~~~

Các hằng này mô tả **độ rộng biểu diễn giá trị**, không phải kết quả của `sizeof` như một số ngôn ngữ khác. Java không có toán tử `sizeof` cho object.

- Một biến primitive có độ rộng giá trị xác định.
- Một instance `Integer` có thể có overhead đối tượng, tham chiếu và yêu cầu căn chỉnh riêng.
- Một field `byte` trong object không nhất thiết làm kích thước object tăng đúng 1 byte, do bố trí bộ nhớ của JVM.
- Mảng có overhead và layout ngoài số byte tương ứng với từng phần tử.

Nếu làm việc với **buffer nhị phân**, `Integer.BYTES` hữu ích để tính số byte cho giá trị 32 bit. Nhưng nếu đo bộ nhớ thực tế trên heap, cần công cụ đo/quan sát JVM phù hợp, không nhân `SIZE` rồi kết luận tổng dung lượng object.

## 7. Dùng MIN_VALUE/MAX_VALUE kiểm tra trước khi thu hẹp kiểu

Thay vì ép kiểu rồi hy vọng giá trị không mất dữ liệu, hãy **kiểm tra miền trước khi cast**.

~~~java
static boolean fitsInByte(long value) {
    return value >= Byte.MIN_VALUE && value <= Byte.MAX_VALUE;
}

static byte toByteChecked(long value) {
    if (!fitsInByte(value)) {
        throw new IllegalArgumentException("Out of byte range: " + value);
    }
    return (byte) value;
}
~~~

Ví dụ:

~~~java
System.out.println(fitsInByte(127));  // true
System.out.println(fitsInByte(128));  // false
System.out.println(toByteChecked(127)); // 127
~~~

Nếu thay bằng `(byte) 128` mà không kiểm tra, kết quả thành `-128`, vì phép thu hẹp giữ các bit thấp và diễn giải theo `byte` có dấu.

Các wrapper limit giúp kiểm tra rõ ràng hơn việc hardcode `-128`/`127`, nhất là khi sau này đổi kiểu tham số hoặc đọc giá trị từ bên ngoài.

### Dùng API kiểm tra chuyển kiểu sẵn có

Khi chuyển một `long` sang `int`, bạn còn có:

~~~java
long input = (long) Integer.MAX_VALUE + 1L;
// int invalid = Math.toIntExact(input); // Ném ArithmeticException khi chạy
~~~

`Math.toIntExact` báo tràn thay vì âm thầm cắt bit. Nó không thay thế việc xác định giá trị nào là hợp lệ theo quy tắc nghiệp vụ, nhưng tránh một lỗi mất dữ liệu phổ biến.


## 8. Ứng dụng `BYTES`: mô tả bản ghi nhị phân

Các hằng `SIZE`/`BYTES` hữu ích khi cần biết **bao nhiêu byte dữ liệu giá trị** sẽ ghi ra một định dạng nhị phân. Ví dụ, bản ghi gồm một số `int` và một số `long` cần `Integer.BYTES + Long.BYTES == 12` byte cho hai giá trị (chưa tính phần header/metadata nếu định dạng có thêm).

~~~java
import java.nio.ByteBuffer;

public class BinaryRecordSizeDemo {
    public static void main(String[] args) {
        ByteBuffer record = ByteBuffer.allocate(Integer.BYTES + Long.BYTES);
        record.putInt(42);
        record.putLong(9_000_000_000L);
        System.out.println(record.position()); // 12
    }
}
~~~

Biên dịch và chạy `BinaryRecordSizeDemo.java` để kiểm chứng đầu ra `12`. `ByteBuffer` mặc định dùng thứ tự byte big-endian; khi đọc/ghi định dạng mạng hoặc file, phải thống nhất byte order với bên còn lại. `BYTES` không nói kích thước thực tế của object `Integer`, `Long` hoặc `ByteBuffer` trong bộ nhớ JVM.

Giới hạn kiểu cũng không tự phát hiện overflow: `Integer.MAX_VALUE + 1` vẫn quay vòng khi cộng `int`; nếu cần kết quả đáng tin, hãy kiểm tra miền hoặc dùng `Math.*Exact`. Chương trình dưới đây có ví dụ xác minh những tình huống biên này.

## 9. Ví dụ Java 17 hoàn chỉnh — tra giới hạn và phát hiện vượt miền

Tạo file **`PrimitiveLimitsDemo.java`** với mã sau:

~~~java
public final class PrimitiveLimitsDemo {
    private PrimitiveLimitsDemo() {}

    static boolean fitsInByte(long value) {
        return value >= Byte.MIN_VALUE && value <= Byte.MAX_VALUE;
    }

    static byte toByteChecked(long value) {
        if (!fitsInByte(value)) {
            throw new IllegalArgumentException("Out of byte range: " + value);
        }
        return (byte) value;
    }

    public static void main(String[] args) {
        System.out.println("byte: " + Byte.MIN_VALUE
                + ".." + Byte.MAX_VALUE + ", " + Byte.SIZE + " bits");
        System.out.println("short: " + Short.MIN_VALUE
                + ".." + Short.MAX_VALUE + ", " + Short.SIZE + " bits");
        System.out.println("int: " + Integer.MIN_VALUE
                + ".." + Integer.MAX_VALUE + ", " + Integer.SIZE + " bits");
        System.out.println("long: " + Long.MIN_VALUE
                + ".." + Long.MAX_VALUE + ", " + Long.SIZE + " bits");

        System.out.println("char code units: "
                + (int) Character.MIN_VALUE + ".."
                + (int) Character.MAX_VALUE
                + ", " + Character.SIZE + " bits");
        System.out.println("byte bytes=" + Byte.BYTES);
        System.out.println("int bytes=" + Integer.BYTES);

        System.out.println("float: " + Float.SIZE + " bits"
                + ", min positive=" + Float.MIN_VALUE
                + ", max finite=" + Float.MAX_VALUE);
        System.out.println("float min normal=" + Float.MIN_NORMAL);
        System.out.println("double: " + Double.SIZE + " bits"
                + ", min positive=" + Double.MIN_VALUE
                + ", max finite=" + Double.MAX_VALUE);

        System.out.println("fits 127=" + fitsInByte(127));
        System.out.println("fits 128=" + fitsInByte(128));
        System.out.println("checked byte=" + toByteChecked(127));
        try {
            toByteChecked(128);
        } catch (IllegalArgumentException ex) {
            System.out.println("range error=" + ex.getMessage());
        }

        System.out.println("int wrapped=" + (Integer.MAX_VALUE + 1));
        System.out.println("abs int min=" + Math.abs(Integer.MIN_VALUE));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("checked add=overflow");
        }

        try {
            Math.toIntExact((long) Integer.MAX_VALUE + 1L);
        } catch (ArithmeticException ex) {
            System.out.println("checked narrowing=overflow");
        }

        double tooLarge = Double.MAX_VALUE * 2.0;
        System.out.println("finite overflow=" + tooLarge);
        System.out.println("is finite=" + Double.isFinite(tooLarge));
    }
}
~~~

Mở terminal trong thư mục chứa file và dùng **JDK 17 trở lên**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PrimitiveLimitsDemo.java
java -cp . PrimitiveLimitsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PrimitiveLimitsDemo.java
java -cp . PrimitiveLimitsDemo
~~~

**Expected output chính xác:**

~~~text
byte: -128..127, 8 bits
short: -32768..32767, 16 bits
int: -2147483648..2147483647, 32 bits
long: -9223372036854775808..9223372036854775807, 64 bits
char code units: 0..65535, 16 bits
byte bytes=1
int bytes=4
float: 32 bits, min positive=1.4E-45, max finite=3.4028235E38
float min normal=1.17549435E-38
double: 64 bits, min positive=4.9E-324, max finite=1.7976931348623157E308
fits 127=true
fits 128=false
checked byte=127
range error=Out of byte range: 128
int wrapped=-2147483648
abs int min=-2147483648
checked add=overflow
checked narrowing=overflow
finite overflow=Infinity
is finite=false
~~~

Mọi dòng trong ví dụ đều do API và hằng chuẩn của JDK tạo ra; không phụ thuộc file dữ liệu hoặc thư viện ngoài. Đầu ra là kết quả kỳ vọng để tự đối chiếu sau khi biên dịch/chạy.

## 10. Các sai lầm thường gặp

| Nhận định/cách viết | Vấn đề | Cách hiểu đúng |
|---|---|---|
| `Byte.MAX_VALUE == 255` | Sai, `byte` là kiểu có dấu | `Byte.MAX_VALUE == 127` |
| `Integer.SIZE == 4` | Nhầm bit với byte | `Integer.SIZE == 32`; `Integer.BYTES == 4` |
| `Long.MIN_VALUE == -Long.MAX_VALUE` | Quên miền âm có thêm một giá trị | `Long.MIN_VALUE == -Long.MAX_VALUE - 1` |
| `Float.MIN_VALUE` là âm vô cùng hoặc giá trị âm thấp nhất | Sai nghĩa hằng của floating point | Đây là số **dương** nhỏ nhất khác 0 |
| `Double.MAX_VALUE` bằng `Infinity` | Một giá trị hữu hạn bị nhầm với vô cực | `Double.isFinite(Double.MAX_VALUE)` là true |
| `Character.SIZE == 8` | `char` dùng một code unit UTF-16 | `Character.SIZE == 16` |
| `Boolean.SIZE` có tồn tại | Java không công bố hằng đó | Chỉ có true/false, không có `Boolean.SIZE` |
| `(byte) 128` vẫn là 128 | Ép thu hẹp cắt bit | Kết quả là -128 |
| `Integer.MAX_VALUE + 1` được tự mở rộng thành long | Toán hạng vẫn là int | Tràn int, kết quả là `Integer.MIN_VALUE` |
| `Math.abs(Integer.MIN_VALUE)` luôn dương | Trị tuyệt đối không vừa int | Kết quả vẫn là `Integer.MIN_VALUE` |

### Quy tắc kiểm tra dữ liệu số thực

Nếu người dùng nhập giá trị `double` từ bên ngoài, hãy phân biệt:

- **Không hợp lệ về định dạng**: không phân tích được thành số.
- **Không hữu hạn**: `NaN` hoặc `Infinity`.
- **Hữu hạn nhưng ngoài miền nghiệp vụ**: ví dụ số lượng âm hoặc vượt mức cho phép.

`MIN_VALUE`/`MAX_VALUE` của kiểu **không tự xác định miền nghiệp vụ**. Chẳng hạn, số lượng sản phẩm phải không âm có thể bị ràng buộc từ 0 đến 100, không nhất thiết sử dụng toàn bộ miền của `int`.

## 11. Bài tập kèm đáp án

### Bài A — phân biệt bit và byte

Hỏi `Short.SIZE`, `Short.BYTES`, `Long.SIZE`, `Long.BYTES`.

**Đáp án:** lần lượt `16`, `2`, `64`, `8`.

### Bài B — giới hạn của char

~~~java
System.out.println((int) Character.MAX_VALUE);
System.out.println(Character.SIZE);
~~~

**Đáp án:**

~~~text
65535
16
~~~

Vì `char` là UTF-16 code unit 16 bit, khác kiểu `short` có dấu.

### Bài C — giới hạn float

`Float.MIN_VALUE` có âm không? Muốn biểu diễn số hữu hạn âm nhỏ nhất theo thứ tự số học thì dùng gì?

**Đáp án:** không; `Float.MIN_VALUE` là số dương subnormal nhỏ nhất khác 0. Số hữu hạn âm thấp nhất là `-Float.MAX_VALUE`.

### Bài D — phép ép kiểu thu hẹp

~~~java
System.out.println((byte) 128);
System.out.println((byte) 255);
~~~

**Đáp án:**

~~~text
-128
-1
~~~

Dữ liệu vượt miền byte, các bit thấp được giữ lại theo quy tắc chuyển kiểu.

### Bài E — kiểm tra overflow

Bạn muốn tăng `Integer.MAX_VALUE` thêm 1 nhưng **phải báo lỗi nếu tràn**. Dùng phép cộng thông thường hay `Math.addExact`?

**Đáp án:** dùng `Math.addExact(Integer.MAX_VALUE, 1)` và xử lý `ArithmeticException`; phép `+` thông thường sẽ cho giá trị đã tràn.

### Bài F — giới hạn nghiệp vụ

Một input `int age = -5;` hợp lệ theo miền `int`, nhưng có hợp lệ làm tuổi không?

**Đáp án:** không. `Integer.MIN_VALUE`/`MAX_VALUE` chỉ giới hạn **khả năng biểu diễn của kiểu**; miền nghiệp vụ của tuổi phải được kiểm tra bằng điều kiện riêng.

## 12. Checklist hoàn thành

- [ ] Nhớ `Byte`, `Short`, `Integer`, `Long` có `MIN_VALUE`, `MAX_VALUE` và `SIZE`.
- [ ] Đọc đúng các giới hạn `byte`/ `short`/ `int`/ `long` theo kiểu có dấu.
- [ ] Biết `SIZE` là số bit, `BYTES` là số byte của biểu diễn giá trị.
- [ ] Hiểu `Character.SIZE == 16` và `char` là UTF-16 code unit.
- [ ] Phân biệt `Float.MIN_VALUE`/`Double.MIN_VALUE` với số âm hữu hạn thấp nhất.
- [ ] Biết `MIN_NORMAL` của floating-point khác `MIN_VALUE`.
- [ ] Biết `Boolean` không có `MIN_VALUE`, `MAX_VALUE`, `SIZE`.
- [ ] Kiểm tra miền trước khi cast thu hẹp kiểu và chú ý overflow.
- [ ] Không nhầm giới hạn của kiểu với miền giá trị hợp lệ của nghiệp vụ.
- [ ] Biên dịch và chạy `PrimitiveLimitsDemo.java` bằng Java 17+, đối chiếu output.

**Kết luận:** `MIN_VALUE`, `MAX_VALUE` và `SIZE` giúp tra được giới hạn và độ rộng giá trị **đúng theo đặc tả Java**, tránh viết cứng các con số và hỗ trợ validation. Với số nguyên, `MIN_VALUE` là số âm nhỏ nhất; với `float`/`double`, `MIN_VALUE` là số **dương khác 0 nhỏ nhất**. Luôn phân biệt bit với byte, khả năng biểu diễn với yêu cầu nghiệp vụ, và kiểm tra trước những phép toán có thể tràn số.