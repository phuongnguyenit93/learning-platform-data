# Chuyển số thực sang số nguyên và cắt phần thập phân — Java 17+

## 1. Hiểu đúng phép chuyển đổi

Trong Java, ép kiểu một giá trị `float` hoặc `double` sang `int` hay `long` là **narrowing primitive conversion** (chuyển kiểu nguyên thủy thu hẹp). Với số **hữu hạn** nằm trong miền kiểu đích, Java **loại bỏ phần thập phân theo hướng về 0** (*truncate toward zero*).

~~~java
double price = 12.9;
int whole = (int) price;
System.out.println(whole); // 12

double adjustment = -12.9;
int negative = (int) adjustment;
System.out.println(negative); // -12
~~~

Không được nhầm phép cast này với **làm tròn đến số nguyên gần nhất**:

- `(int) 12.9` → `12`.
- `(int) -12.9` → `-12`.
- Không có chuyện số âm được tự làm tròn xuống `-13`.
- Phép cast không tự xác thực xem dữ liệu có phần lẻ hay có nằm trong giới hạn ứng dụng hay không.

**Ý tưởng chủ đạo:** `(int) value` là **chuyển kiểu**, không phải một hàm làm tròn tùy chọn và cũng không phải cơ chế kiểm tra an toàn dữ liệu.

## 2. Cú pháp cast: kiểu đích trong dấu ngoặc

~~~java
double reading = 17.75;
int valueAsInt = (int) reading;
long valueAsLong = (long) reading;

System.out.println(valueAsInt);  // 17
System.out.println(valueAsLong); // 17
~~~

Dấu `(int)` hoặc `(long)` nói với compiler rằng bạn chủ động yêu cầu **chuyển giá trị**. Nếu nguồn là biến `double`, Java không cho gán trực tiếp sang `int` không có cast:

~~~java
double reading = 17.75;
// int wrong = reading; // Lỗi biên dịch: possible lossy conversion
int correct = (int) reading;
~~~

Bảng ví dụ cho **giá trị hữu hạn và vừa miền `int`**:

| Giá trị nguồn | `(int)` | Giải thích |
|---|---:|---|
| `12.9` | 12 | Bỏ phần lẻ, tiến về 0 |
| `12.1` | 12 | Không làm tròn lên |
| `-12.9` | -12 | Không phải -13 |
| `-12.1` | -12 | Tiến về 0 |
| `0.99` | 0 | Phần nguyên bằng 0 |
| `-0.99` | 0 | `int` không có âm 0 |
| `12.0` | 12 | Không có phần lẻ |
| `-0.0` | 0 | Mất dấu âm của zero khi thành `int` |

Ở đây **cắt phần thập phân** có nghĩa với các số hữu hạn thông thường: kết quả là số nguyên có độ lớn **không vượt quá** độ lớn của nguồn, trừ khi xuất hiện các quy tắc giới hạn miền cần xử lý riêng.

## 3. Cắt về 0 khác `floor`, `ceil`, `round` và `rint`

Java có nhiều API liên quan tới số thực, nhưng chúng giải quyết **những mục đích khác nhau**.

| Biểu thức | Giá trị | Quy tắc |
|---|---:|---|
| `(int) 12.9` | `12` | Cắt về 0 |
| `(int) -12.9` | `-12` | Cắt về 0 |
| `Math.floor(12.9)` | `12.0` | Số nguyên lớn nhất không vượt giá trị nguồn |
| `Math.floor(-12.9)` | `-13.0` | Làm tròn xuống theo trục số |
| `Math.ceil(12.1)` | `13.0` | Làm tròn lên theo trục số |
| `Math.ceil(-12.9)` | `-12.0` | Làm tròn lên theo trục số |
| `Math.round(12.5)` | `13` | Làm tròn theo quy tắc của `Math.round` |
| `Math.round(-12.5)` | `-12` | Trường hợp nửa đơn vị theo hướng +∞ |
| `Math.rint(12.5)` | `12.0` | Nửa đường chọn số nguyên chẵn |
| `Math.rint(13.5)` | `14.0` | Nửa đường chọn số nguyên chẵn |

**Kiểu trả về cũng khác:**

- `(int) d` trả `int`; `(long) d` trả `long`.
- `Math.floor(double)`, `Math.ceil(double)`, `Math.rint(double)` trả **`double`**, dù giá trị có phần lẻ bằng 0.
- `Math.round(double)` trả **`long`**; còn `Math.round(float)` trả **`int`**.

Ví dụ:

~~~java
double value = -12.9;
System.out.println((int) value);       // -12
System.out.println(Math.floor(value)); // -13.0
System.out.println(Math.ceil(value));  // -12.0
~~~

**Đừng chọn một API chỉ vì tên nghe giống “làm tròn”.** Hãy xác định rõ nghiệp vụ muốn **cắt**, **làm tròn xuống**, **làm tròn lên** hay **chọn số nguyên gần nhất**.

## 4. Trường hợp đặc biệt: NaN, vô cực và vượt miền

Ép `double`/`float` sang kiểu nguyên **không mặc định ném exception** khi đầu vào bất thường. Java có những quy tắc bắt buộc:

1. **NaN** chuyển thành `0`.
2. **Dương vô cực** hoặc giá trị quá lớn theo hướng dương chuyển thành **giá trị lớn nhất** của kiểu đích nguyên đang xét.
3. **Âm vô cực** hoặc giá trị quá nhỏ theo hướng âm chuyển thành **giá trị nhỏ nhất** của kiểu đích nguyên đang xét.
4. Với giá trị hữu hạn trong miền có thể biểu diễn, bỏ phần lẻ theo hướng về 0.

~~~java
System.out.println((int) Double.NaN);               // 0
System.out.println((int) Double.POSITIVE_INFINITY); // 2147483647
System.out.println((int) Double.NEGATIVE_INFINITY); // -2147483648
System.out.println((int) 1.0e100);                  // 2147483647
System.out.println((long) 1.0e100);                 // 9223372036854775807
~~~

Giá trị trên thuộc **narrowing conversion**, không phải một phép kiểm tra giá trị hợp lệ. Nếu đầu vào NaN mà cast ra 0, không thể suy ra người dùng thực sự cung cấp số 0.

### Sơ đồ quyết định cho dữ liệu cần chuyển an toàn

~~~mermaid
flowchart TD
    A["Giá trị float / double"] --> B{"Double.isFinite(value)?"}
    B -- "Không" --> X["Từ chối hoặc xử lý NaN / Infinity"]
    B -- "Có" --> C{"Trong miền kiểu đích?"}
    C -- "Không" --> Y["Từ chối hoặc chọn kiểu rộng hơn"]
    C -- "Có" --> D{"Nghiệp vụ cho mất phần lẻ?"}
    D -- "Có" --> E["Cast (int) hoặc (long): cắt về 0"]
    D -- "Không" --> F{"Giá trị là số nguyên?"}
    F -- "Không" --> Z["Từ chối hoặc áp dụng quy tắc làm tròn"]
    F -- "Có" --> E
~~~

Khi làm việc với dữ liệu tài chính, số lượng hoặc chỉ số mảng, **không nên coi NaN → 0 hoặc Infinity → MAX_VALUE là lựa chọn an toàn mặc định**.

## 5. Đúng miền `int`: chú ý cận trên khi so với double

`int` có miền:

~~~text
Integer.MIN_VALUE = -2147483648
Integer.MAX_VALUE =  2147483647
~~~

Khi nguồn là `double`, cách kiểm tra chính xác và dễ lý giải là:

~~~java
static boolean inIntInputRange(double value) {
    return Double.isFinite(value)
            && value >= -2147483648.0
            && value <  2147483648.0;
}
~~~

Dùng cận trên **loại trừ `2147483648.0` (2³¹)**. Vì sao không viết đơn giản `value <= Integer.MAX_VALUE` ở mọi ngữ cảnh? Phép so sánh hỗn hợp có thể chuyển `Integer.MAX_VALUE` thành `double`; với `int` việc này vẫn chính xác, nhưng viết cận trên loại trừ làm rõ ranh giới kiểu đích và tránh vô ý chấp nhận một giá trị ngoài miền.

Cần hiểu chính sách kiểm tra: `-2147483648.5` là một số có phần nguyên sau khi cắt có thể bằng `Integer.MIN_VALUE`, nhưng **đầu vào thực ban đầu nằm ngoài miền giá trị nguyên**. Hàm trên chủ động từ chối giá trị nằm ngoài miền **trước khi cắt**, để không che lỗi dữ liệu.

`double` cũng biểu diễn chính xác hai giá trị cận `-2147483648.0`, `2147483648.0`, nên so sánh này rõ ràng.

### Miền `long` có bẫy lớn hơn

`Long.MAX_VALUE` bằng `9223372036854775807`, nhưng **`double` không thể biểu diễn chính xác số nguyên ấy**. Giá trị `double` của `Long.MAX_VALUE` khi chuyển đổi mở rộng được làm tròn lên **2⁶³**.

Vì vậy **không dùng đơn thuần `value <= Long.MAX_VALUE` để chứng minh giá trị double nằm trong miền long**. Một phép kiểm tra phạm vi theo chính `double` là:

~~~java
static boolean inLongInputRange(double value) {
    return Double.isFinite(value)
            && value >= -0x1.0p63
            && value <   0x1.0p63;
}
~~~

`0x1.0p63` là literal `double` hệ 16 dạng dấu phẩy động, biểu diễn chính xác \(2^{63}\). Cận dưới \(-2^{63}\) được phép, cận trên \(2^{63}\) bị loại.

Nếu dữ liệu ban đầu là một số nguyên `long`, **đừng đi vòng qua double** để rồi hy vọng nhận lại chính xác mọi chữ số. Hãy giữ dữ liệu ở kiểu nguyên khi yêu cầu tính chính xác từng đơn vị.

## 6. Khi cần loại bỏ phần lẻ nhưng từ chối NaN và overflow

Đây là hàm cho trường hợp **cho phép cắt phần lẻ**, nhưng đầu vào phải hữu hạn và nằm trong miền int:

~~~java
static int truncateIntChecked(double value) {
    if (!Double.isFinite(value)
            || value < -2147483648.0
            || value >= 2147483648.0) {
        throw new IllegalArgumentException("outside int input range");
    }
    return (int) value;
}
~~~

Ví dụ:

~~~java
System.out.println(truncateIntChecked(42.75)); // 42
System.out.println(truncateIntChecked(-42.75)); // -42
~~~

Những giá trị `Double.NaN`, `Double.POSITIVE_INFINITY`, `2147483648.0` sẽ bị **từ chối có chủ đích** thay vì âm thầm chuyển thành 0 hoặc giá trị sát giới hạn.

**Đặc điểm nghiệp vụ:** hàm này cho phép mất phần lẻ sau cast. Nếu yêu cầu “phải là số nguyên thật sự”, cần thêm kiểm tra khác trước khi cast.

## 7. Khi không được phép mất phần lẻ

Ví dụ số lượng món hàng phải nguyên; nhận dữ liệu `42.75` rồi cắt thành 42 có thể là lỗi nghiệp vụ. Hãy kiểm tra:

~~~java
static int requireWholeInt(double value) {
    if (!Double.isFinite(value)
            || value < -2147483648.0
            || value >= 2147483648.0
            || value != Math.rint(value)) {
        throw new IllegalArgumentException("not a finite whole int");
    }
    return (int) value;
}
~~~

`Math.rint(value)` trả về một giá trị double đã làm tròn tới số nguyên gần nhất theo quy tắc nửa tới số chẵn. Ở đây **không dùng kết quả ấy để sửa giá trị**; chỉ dùng phép so sánh `value == Math.rint(value)` để kiểm tra giá trị nguồn **đã nguyên**.

Ví dụ:

~~~java
System.out.println(requireWholeInt(42.0)); // 42
// requireWholeInt(42.5); // Ném IllegalArgumentException
~~~

**Chú ý sai số trước đó:** nếu một phép tính floating-point đáng lẽ ra số nguyên nhưng thực tế tạo `41.99999999999999`, kiểm tra exact sẽ từ chối. Đây không phải bug của `Math.rint`, mà là yêu cầu nghiệp vụ cần quyết định **chấp nhận xấp xỉ có dung sai hay cần tính toán thập phân chính xác**. Không tùy tiện “cứ gần số nguyên là ép kiểu” cho dữ liệu quan trọng.

## 8. Thu hẹp tiếp thành `byte`, `short`, `char`

Chuyển từ dấu phẩy động sang kiểu nguyên nhỏ hơn diễn ra qua **bước chuyển sang `int` rồi thu hẹp tiếp**. Hành vi có thể khác nhiều so với việc chỉ bỏ phần lẻ.

~~~java
double input = 130.9;
byte asByte = (byte) input;
System.out.println(asByte); // -126
~~~

Giải thích theo hai bước:

1. `130.9` được chuyển thành giá trị `int` là `130`.
2. `130` bị thu hẹp về `byte`, giữ 8 bit thấp và diễn giải thành `-126`.

Với `char`:

~~~java
double input = 65536.9;
char asChar = (char) input;
System.out.println((int) asChar); // 0
~~~

`65536.9` → `int` 65536 → `char` giữ 16 bit thấp thành 0.

**Không nhầm hai cơ chế:** cắt phần lẻ là chuyện chuyển float/double thành int/long; cắt bit thấp là chuyện **thu hẹp tiếp từ int xuống byte/short/char**. Nếu nghiệp vụ cần một giá trị byte/short/char chính xác, hãy validation theo miền của **kiểu đích cuối cùng**.

## 9. Sai số biểu diễn có thể thay đổi phần nguyên trước khi cast

`float` và `double` biểu diễn số theo dấu phẩy động **nhị phân**. Một kết quả tính toán có thể nhỏ hơn hoặc lớn hơn một số nguyên dự kiến vì sai số làm tròn:

~~~java
double computed = 2.9999999999999996;
System.out.println(computed);       // 2.9999999999999996
System.out.println((int) computed); // 2
~~~

Mặc dù người dùng có thể nghĩ tới kết quả toán học là 3, Java **chuyển chính giá trị đang lưu** và cắt về 0 nên cho 2.

Không nên tự động áp dụng `(int) (computed + 0.000001)` như một “mẹo sửa” chung: nó thay đổi dữ liệu, có thể sai với số âm, số gần ranh giới hoặc các thang đo khác.

Nếu cần làm tròn, hãy chọn `Math.round`, `Math.floor`, `Math.ceil` hoặc quy tắc thập phân phù hợp. Nếu cần tính chính xác theo decimal, hãy xem xét `BigDecimal` hoặc số nguyên biểu diễn đơn vị nhỏ nhất.

## 10. BigDecimal khi nghiệp vụ không chấp nhận sai số/cắt ngầm

Khi giá trị đầu vào vốn là **số thập phân chính xác** (ví dụ nhập `"42.75"`), `BigDecimal` có thể diễn đạt rõ hành vi cần thiết:

~~~java
java.math.BigDecimal value = new java.math.BigDecimal("42.75");

System.out.println(value.toBigInteger()); // 42: cắt phần lẻ
// value.intValueExact(); // Ném ArithmeticException: không phải số nguyên
~~~

`toBigInteger()` trả phần nguyên bằng cách cắt phần lẻ về 0. Trong khi đó `intValueExact()` yêu cầu không mất phần thập phân và nằm trong miền `int`; nếu không, nó ném `ArithmeticException`.

~~~java
java.math.BigDecimal whole = new java.math.BigDecimal("42");
System.out.println(whole.intValueExact()); // 42
~~~

Đừng tạo `new BigDecimal(0.1)` rồi kỳ vọng có chính xác giá trị decimal 0.1; constructor từ `double` nhận giá trị nhị phân đã được làm tròn trước đó. Với dữ liệu decimal đầu vào, dùng chuỗi decimal hoặc một cơ chế chuyển tương đương có chủ đích.

**Điểm quyết định:** dùng cast khi bạn **chấp nhận cắt phần lẻ và đã kiểm tra miền**, hoặc dùng API exact khi **mất phần lẻ phải bị từ chối**.

## 11. Chương trình Java 17 hoàn chỉnh, runnable

Tạo đúng tệp **`FloatingToIntegerDemo.java`**:

~~~java
import java.math.BigDecimal;

public final class FloatingToIntegerDemo {
    private FloatingToIntegerDemo() {}

    static int truncateIntChecked(double value) {
        if (!Double.isFinite(value)
                || value < -2147483648.0
                || value >= 2147483648.0) {
            throw new IllegalArgumentException("outside int input range");
        }
        return (int) value;
    }

    static int requireWholeInt(double value) {
        if (!Double.isFinite(value)
                || value < -2147483648.0
                || value >= 2147483648.0
                || value != Math.rint(value)) {
            throw new IllegalArgumentException("not a finite whole int");
        }
        return (int) value;
    }

    public static void main(String[] args) {
        double positive = 12.9;
        double negative = -12.9;
        float small = 3.99f;

        System.out.println("positive int=" + (int) positive);
        System.out.println("negative int=" + (int) negative);
        System.out.println("positive long=" + (long) positive);
        System.out.println("negative long=" + (long) negative);
        System.out.println("small negative int=" + (int) -0.99);
        System.out.println("float int=" + (int) small);

        System.out.println("byte after double=" + (byte) 130.9);
        System.out.println("char after double=" + (int) (char) 65536.9);

        System.out.println("NaN int=" + (int) Double.NaN);
        System.out.println("+Infinity int="
                + (int) Double.POSITIVE_INFINITY);
        System.out.println("-Infinity int="
                + (int) Double.NEGATIVE_INFINITY);
        System.out.println("large int=" + (int) 1.0e100);
        System.out.println("large long=" + (long) 1.0e100);

        System.out.println("round positive half=" + Math.round(12.5));
        System.out.println("round negative half=" + Math.round(-12.5));
        System.out.println("floor negative=" + Math.floor(-12.9));
        System.out.println("ceil negative=" + Math.ceil(-12.9));
        System.out.println("rint even=" + Math.rint(12.5));
        System.out.println("rint odd=" + Math.rint(13.5));

        double computed = 2.9999999999999996;
        System.out.println("precision before cast=" + computed);
        System.out.println("precision after cast=" + (int) computed);

        System.out.println("checked truncate=" + truncateIntChecked(42.75));
        System.out.println("checked exact=" + requireWholeInt(42.0));

        try {
            requireWholeInt(42.75);
        } catch (IllegalArgumentException ex) {
            System.out.println("fraction rejected");
        }
        try {
            truncateIntChecked(Double.NaN);
        } catch (IllegalArgumentException ex) {
            System.out.println("NaN rejected");
        }
        try {
            truncateIntChecked(2147483648.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("overflow rejected");
        }

        System.out.println("decimal whole="
                + new BigDecimal("42").intValueExact());
        try {
            new BigDecimal("42.75").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("decimal fractional rejected");
        }
    }
}
~~~

Yêu cầu **JDK 17 hoặc mới hơn**, terminal đặt trong thư mục có tệp.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 FloatingToIntegerDemo.java
java -cp . FloatingToIntegerDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\FloatingToIntegerDemo.java
java -cp . FloatingToIntegerDemo
~~~

**Expected output chính xác:**

~~~text
positive int=12
negative int=-12
positive long=12
negative long=-12
small negative int=0
float int=3
byte after double=-126
char after double=0
NaN int=0
+Infinity int=2147483647
-Infinity int=-2147483648
large int=2147483647
large long=9223372036854775807
round positive half=13
round negative half=-12
floor negative=-13.0
ceil negative=-12.0
rint even=12.0
rint odd=14.0
precision before cast=2.9999999999999996
precision after cast=2
checked truncate=42
checked exact=42
fraction rejected
NaN rejected
overflow rejected
decimal whole=42
decimal fractional rejected
~~~

Chương trình không cần Maven/Gradle hoặc thư viện ngoài JDK. Không in thông điệp exception phụ thuộc cài đặt hệ thống; các dòng báo lỗi do code chủ động xác định.

**Cần hiểu rõ các nhóm kết quả:**

- Hai dấu của `12.9` chứng minh **cắt về 0**, không luôn “làm tròn xuống”.
- Các dòng NaN/vô cực minh họa **quy tắc ngôn ngữ**, không có nghĩa các đầu vào đó nên được chấp nhận.
- `byte after double`/`char after double` diễn ra theo **hai bước thu hẹp**.
- Các dòng `Math.round`, `Math.floor`, `Math.ceil`, `Math.rint` cho thấy cast **khác làm tròn**.
- Hai hàm kiểm tra thể hiện **hai hợp đồng khác nhau**: được phép cắt phần lẻ hoặc yêu cầu số nguyên chính xác.

## 12. Các lỗi thường gặp

| Lỗi hoặc giả định | Tại sao sai? | Cách xử lý |
|---|---|---|
| `int n = doubleValue;` | Double → int là narrowing, không gán ngầm | Cast có chủ đích và kiểm tra |
| `(int) -12.9` được nghĩ là -13 | Cast cắt về 0 | Kết quả -12; muốn floor dùng `Math.floor` |
| `(int) 12.9` được nghĩ là 13 | Cast không làm tròn gần nhất | Kết quả 12; xem `Math.round` |
| NaN được cast thành 0 rồi coi là dữ liệu hợp lệ | Cast không validation | Dùng `Double.isFinite` |
| Dương Infinity cast về int thành max mà không báo lỗi | Quy tắc bão hòa | Từ chối dữ liệu vô cực nếu nghiệp vụ yêu cầu |
| Dùng `(int) 1e100` để kiểm tra miền | Cast bão hòa về MAX_VALUE | Kiểm tra giới hạn trước |
| `(byte) 130.9` cho 130 | Hai lần narrowing tạo -126 | Kiểm tra miền byte |
| `(int) 2.9999999999999996` cho 3 | Không có làm tròn | Giá trị thực đang lưu dẫn tới 2 |
| So `double <= Long.MAX_VALUE` đủ kiểm tra long | MAX_VALUE long làm tròn lên khi đổi thành double | Dùng ranh giới `±2^63` phù hợp |
| `Math.round` luôn cùng quy tắc với `Math.rint` | Khác quy tắc tie và kiểu trả về | Chọn đúng API theo yêu cầu |
| Cast sang int để loại bỏ phần lẻ dù dữ liệu cần giữ chính xác | Mất dữ liệu không có cảnh báo | `intValueExact` của BigDecimal hoặc validation rõ |
| Dùng `new BigDecimal(double)` cho decimal chính xác | Lấy binary approximation của double | Tạo từ chuỗi decimal khi dữ liệu nguồn là decimal |

## 13. Bài tập có đáp án

### Bài A — số dương và âm

~~~java
System.out.println((int) 8.99);
System.out.println((int) -8.99);
System.out.println((int) -0.75);
~~~

**Đáp án:**

~~~text
8
-8
0
~~~

Cast loại bỏ phần lẻ theo hướng về 0.

### Bài B — làm tròn xuống khác cắt

~~~java
double x = -3.8;
System.out.println((int) x);
System.out.println(Math.floor(x));
~~~

**Đáp án:**

~~~text
-3
-4.0
~~~

### Bài C — NaN và vô cực

~~~java
System.out.println((int) Double.NaN);
System.out.println((int) Double.POSITIVE_INFINITY);
System.out.println((long) Double.NEGATIVE_INFINITY);
~~~

**Đáp án:**

~~~text
0
2147483647
-9223372036854775808
~~~

Những giá trị này do quy tắc narrowing quy định. Chúng không chứng minh đầu vào được phép dùng làm số lượng hợp lệ.

### Bài D — byte sau khi chuyển từ double

~~~java
double value = 255.9;
System.out.println((byte) value);
~~~

**Đáp án:** `-1`. Đầu tiên `255.9` thành `int` 255, sau đó thành `byte` có dấu -1.

### Bài E — số lượng phải là số nguyên

Bạn nhận một giá trị `double quantity = 7.25;` và **không được phép làm mất phần lẻ**. Có nên dùng `(int) quantity`?

**Đáp án:** không. Cast cho 7 và làm mất 0.25. Hãy yêu cầu số hữu hạn, trong miền kiểu đích và có giá trị nguyên trước khi chuyển. Với nguồn decimal chính xác, có thể dùng `BigDecimal.intValueExact()`.

### Bài F — kiểm tra cận `long` từ double

Vì sao so sánh `value <= Long.MAX_VALUE` không phải cách đủ an toàn để xác nhận mọi `double` có thể chuyển về `long` đúng giá trị?

**Đáp án:** `Long.MAX_VALUE = 2^63-1` không biểu diễn chính xác được bởi `double`; khi đổi sang double nó làm tròn thành `2^63`. Cần kiểm tra `value < 0x1.0p63` và `value >= -0x1.0p63`, đồng thời kiểm tra hữu hạn; nếu yêu cầu không mất phần lẻ, thêm điều kiện giá trị đã nguyên.

## 14. Checklist và kết luận

- [ ] Phân biệt **cast về int/long** với **làm tròn**.
- [ ] Biết `(int) 12.9 == 12`, `(int) -12.9 == -12`.
- [ ] Nhớ `Math.floor`/`ceil`/`round`/`rint` có quy tắc khác nhau.
- [ ] Hiểu chuyển đổi NaN → 0, ±Infinity → giới hạn kiểu đích.
- [ ] Biết ép kiểu không tự ném lỗi khi giá trị floating-point vượt miền.
- [ ] Kiểm tra `Double.isFinite` trước khi dùng dữ liệu yêu cầu hữu hạn.
- [ ] Hiểu vì sao cận `long` cần so với `±2^63` bằng double.
- [ ] Phân biệt cast sang byte/short/char với cast trực tiếp sang int/long.
- [ ] Biết lỗi xấp xỉ floating-point có thể làm phần nguyên sau cast thay đổi.
- [ ] Chọn hàm kiểm tra **cho cắt phần lẻ** hoặc **không cho mất phần lẻ** theo yêu cầu.
- [ ] Biết `BigDecimal.intValueExact()` từ chối dữ liệu có phần lẻ.
- [ ] Chạy `FloatingToIntegerDemo.java` bằng `javac`/`java` Java 17+ và đối chiếu từng dòng.

**Kết luận:** Ép `float`/`double` sang số nguyên trong Java **cắt phần thập phân theo hướng về 0** khi giá trị hữu hạn nằm trong miền. Với NaN, vô cực hoặc dữ liệu vượt miền, Java áp dụng các quy tắc chuyển đổi đặc biệt mà không tự xem đó là lỗi nghiệp vụ. Hãy lựa chọn rõ yêu cầu **cắt**, **làm tròn**, hay **chuyển đổi chính xác**, rồi kiểm tra dữ liệu trước khi cast.