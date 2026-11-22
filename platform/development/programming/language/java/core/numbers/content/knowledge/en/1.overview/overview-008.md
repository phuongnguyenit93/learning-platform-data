# Phạm vi Java Core và cách đối chiếu phiên bản JDK — Java Core: Numbers

## 1. Bài này giải quyết vấn đề gì?

Khi học xử lý số trong Java, dễ gặp hai câu hỏi tưởng đơn giản: “`BigDecimal` có phải thư viện ngoài không?” và “Ví dụ dùng `Math.clamp` có chạy trên JDK 17 không?”. Muốn trả lời, phải phân biệt **phạm vi kiến thức Java Core**, **API chuẩn**, **phiên bản JDK dùng để biên dịch**, **phiên bản Java nơi chương trình chạy** và **phiên bản mà dự án cam kết hỗ trợ**.

Bài này tập trung vào **Java Core — Numbers**. Mục tiêu là giúp bạn:

1. Biết những thành phần xử lý số nào thuộc cú pháp ngôn ngữ Java, thư viện chuẩn `java.base` hoặc các API chuẩn khác; không nhầm với thư viện của ứng dụng.
2. Xác định API/phương thức tồn tại từ Java nào bằng tài liệu phiên bản cụ thể, đặc biệt các mục `Since`, `Deprecated` và `Preview`.
3. Hiểu khác nhau giữa khả năng biên dịch mã nguồn, khả năng gọi API, phiên bản bytecode và khả năng chạy thực tế.
4. Tự kiểm tra với `java`, `javac` và `javac --release` trước khi kết luận mã chạy được trên JDK đích.
5. Xây dựng quy trình đối chiếu phiên bản có thể áp dụng cho mọi bài Numbers tiếp theo.

**Giới hạn phạm vi:** đây là bài định hướng và đối chiếu phiên bản, không phải tài liệu tra cứu mọi phép toán số hay bảng liệt kê toàn bộ thay đổi của từng bản JDK. Các phiên bản 8, 11, 17 và 21 được dùng làm **mốc kiểm tra**; chúng không có nghĩa là chỉ tồn tại bốn bản Java hoặc phiên bản mới nhất của Java luôn là 21.

## 2. Năm khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa thực hành | Ví dụ liên quan Numbers |
| --- | --- | --- |
| **Java (ngôn ngữ)** | Cú pháp, kiểu primitive, toán tử, quy tắc chuyển kiểu được quy định bởi Java Language Specification | `int`, `double`, `+`, `/`, numeric promotion |
| **Java SE (nền tảng chuẩn)** | Bộ API, mô hình thực thi và đặc tả chuẩn theo một bản phát hành | `java.lang.Math`, `java.math.BigDecimal`, `java.text.NumberFormat` |
| **JDK (Java Development Kit)** | Bộ công cụ phát triển gồm trình biên dịch, công cụ tài liệu và môi trường chạy | `javac`, `java`, `javadoc`, `jshell` (từ JDK 9) |
| **JVM/runtime** | Môi trường tải, xác minh và thực thi bytecode; một ứng dụng còn phụ thuộc API/runtime có sẵn | Chạy `NumbersDemo.class`; có thể gặp `UnsupportedClassVersionError` hoặc `NoSuchMethodError` |
| **Bản phân phối JDK** | Một bản dựng của Java từ nhà cung cấp cụ thể, theo version, bản vá và chính sách hỗ trợ của họ | OpenJDK build, Oracle JDK, Eclipse Temurin hoặc bản dựng khác |

**Java Core** là cách gọi trong học tập cho kiến thức nền của Java và thư viện chuẩn thường dùng, không phải tên một module Java SE độc lập. Từ Java 9, Java SE có hệ thống module; nhiều lớp xử lý số phổ biến nằm trong module **`java.base`**, được mọi module Java đọc ngầm.

**JRE** từng được phân phối riêng trong nhiều dòng Java cũ; với các bản JDK hiện đại, khi nói “runtime” nên xác nhận đúng bộ chạy thực tế thay vì giả định máy nhất thiết có một bản cài JRE độc lập.

Để so sánh tính khả dụng của một API, luôn ghi **số phiên bản tính năng (feature release)**, ví dụ 17 hay 21, rồi mới xét cập nhật vá lỗi như 17.0.x hoặc 21.0.x. Một bản cập nhật vá lỗi và một feature release mới không có cùng ý nghĩa tương thích.

## 3. Bản đồ Numbers trong phạm vi Java Core

### 3.1. Phần thuộc ngôn ngữ Java

Các kiểu primitive `byte`, `short`, `int`, `long`, `float` và `double`; literal như `42`, `42L`, `1.5F`; toán tử `+`, `-`, `*`, `/`, `%`; ép kiểu và quy tắc nâng kiểu số nằm ở **ngôn ngữ Java**. Không cần cài thư viện số bên ngoài để sử dụng chúng.

Những quy tắc cơ bản cần kiểm tra theo **Java Language Specification (JLS)** của phiên bản mục tiêu, chẳng hạn cách tính `7 / 2`, tràn `int` và sự khác biệt giữa số thực gần đúng với số thập phân chính xác. Phần lớn nền tảng này ổn định qua nhiều phiên bản, nhưng không vì vậy mà bỏ qua những thay đổi đặc tả về xử lý dấu phẩy động hoặc tính năng ngôn ngữ khác.

### 3.2. Các lớp/thư viện chuẩn thường gặp

| Nhu cầu | Các API tiêu biểu | Thuộc đâu? |
| --- | --- | --- |
| Hằng số và phép toán toán học cơ bản | `Math`, `StrictMath` | `java.lang` / `java.base` |
| Bao kiểu và xử lý số nguyên | `Number`, `Integer`, `Long`, `Short`, `Byte` | `java.lang` / `java.base` |
| Bao kiểu số thực và kiểm tra trạng thái | `Float`, `Double` | `java.lang` / `java.base` |
| Số nguyên lớn | `BigInteger` | `java.math` / `java.base` |
| Số thập phân, độ chính xác, làm tròn | `BigDecimal`, `MathContext`, `RoundingMode` | `java.math` / `java.base` |
| Parse/định dạng theo vùng | `NumberFormat`, `DecimalFormat`, `DecimalFormatSymbols` | `java.text` / `java.base` |
| Quy định vùng/ngôn ngữ | `Locale` | `java.util` / `java.base` |
| Sinh số giả ngẫu nhiên | `Random`, `SplittableRandom`; `RandomGenerator` từ JDK 17 | `java.util` và `java.util.random` / `java.base` |
| Dạng số làm đầu vào/đầu ra | `Scanner`, `Formatter` | `java.util` / `java.base` |

`java.lang` được import tự động. Các package khác như `java.math`, `java.text`, `java.util` cần import hoặc dùng tên đầy đủ.

Ví dụ, `BigDecimal` là API tiêu chuẩn của Java SE. Cú pháp `import java.math.BigDecimal;` không thể hiện phụ thuộc Maven hoặc Gradle ngoài JDK. Ngược lại, một kiểu số do một thư viện bên thứ ba định nghĩa phải tra tài liệu/phiên bản **của chính thư viện đó**, không gán phiên bản ra đời của nó cho Java SE.

### 3.3. Những gì nằm ngoài bài

JNI, Vector API ươm thử (incubator), cơ chế JVM nội bộ, thuật toán toán học chuyên ngành, SQL/JPA mapping và thư viện số khoa học là các chủ đề liên quan nhưng **không phải điều kiện bắt buộc** để hiểu phạm vi Numbers của Java Core. Chỉ mở rộng khi bài toán cụ thể yêu cầu.

## 4. “Chạy trên Java X” thực ra có những lớp tương thích nào?

Một câu “đoạn code chạy trên Java 17” là chưa đủ chính xác nếu chưa xác định:

1. **Source compatibility:** trình biên dịch có chấp nhận cú pháp/ngữ nghĩa của phiên bản ngôn ngữ mục tiêu không? Một tính năng cú pháp phát hành sau Java 17 sẽ không thể dùng trong chế độ source 17.
2. **API compatibility:** tất cả lớp và phương thức có trong Java SE API của phiên bản đích không? Mã cú pháp cũ vẫn có thể gọi một API chỉ ra đời ở Java 21.
3. **Binary/class-file compatibility:** class được biên dịch ra phiên bản bytecode nào; runtime đích có đọc được không?
4. **Runtime behavior:** API có thể tồn tại nhưng dữ liệu locale, provider, triển khai, cấu hình, hành vi được đặc tả hoặc lỗi sửa trong bản vá có thể ảnh hưởng kết quả.
5. **Support/security:** JDK của nhà cung cấp còn nhận cập nhật bảo mật hay không và bản cụ thể nào được tổ chức hỗ trợ? Đây là quyết định vận hành, không suy ra từ việc code biên dịch được.

Ví dụ: build một `.class` bằng JDK 21 ở mặc định rồi đưa cho runtime Java 17 thường vướng class-file version mới hơn. Nhưng ngay cả nếu ép class-file target về 17, mã vẫn có thể vô tình tham chiếu API chỉ có trong 21 nếu không kiểm soát API khi biên dịch.

### 4.1. Quy tắc chiều tương thích

- JDK mới thường có thể **biên dịch mã nhắm phiên bản cũ được hỗ trợ** qua `--release`. Mức hỗ trợ cụ thể phải xem `javac --help` của bản đang cài.
- JDK cũ **không thể** biên dịch source/API được đưa vào ở phiên bản tương lai.
- Runtime cũ không được bảo đảm chạy class file sinh cho Java mới hơn.
- Runtime mới có mức tương thích ngược rất cao nhưng không phải cam kết mọi chương trình cũ đều không cần điều chỉnh; thay đổi API đã loại bỏ, module encapsulation, phụ thuộc thư viện, môi trường và thiết lập có thể gây lỗi.

**Tuyên bố chính xác** nên là: “Được biên dịch bằng JDK 21 với `--release 17`, chỉ dùng Java SE API nằm trong Java 17, và đã chạy thử trên JDK 17 được chỉ định.” Tuyên bố này có bằng chứng rõ hơn “viết bằng Java 21 nhưng chạy mọi nơi”.

## 5. Tra được phiên bản thực tế trước khi học hoặc sửa code

Trên terminal, chạy:

```bash
java -version
javac -version
javac --help
```

- `java -version` cho biết bản runtime được chọn bởi lệnh `java` hiện tại.
- `javac -version` cho biết bản compiler được chọn; không nên mặc định hai lệnh cùng trỏ tới một JDK khi máy có nhiều bản Java.
- `javac --help` cho phép kiểm tra bản compiler chấp nhận các giá trị `--release` nào.
- Từ JDK 9, `java --list-modules` có thể liệt kê các module của runtime hiện tại, bao gồm `java.base`.

Nếu kết quả khác dự kiến, kiểm tra đường dẫn công cụ và cấu hình của terminal, IDE, Gradle hoặc CI:

```powershell
# Windows PowerShell
Get-Command java
Get-Command javac
```

```bash
# Linux/macOS
command -v java
command -v javac
```

Lệnh trên giúp xác định **lệnh nào được shell tìm thấy**. Với dự án sử dụng IDE, Gradle toolchain, Maven toolchains, container hoặc CI, cần kiểm tra thêm cấu hình từng công cụ vì compiler/runtime mà build dùng có thể khác kết quả shell.

Trong ứng dụng Java, có thể truy vấn:

```java
System.out.println(System.getProperty("java.version"));
System.out.println(Runtime.version().feature());
```

Hai dòng này chỉ là **mảnh mã** chạy trong một phương thức; `Runtime.version()` có từ Java 9. Đầu ra phụ thuộc runtime, nên không ghi cố định là “17” hoặc “21” nếu chưa kiểm tra. Thông tin build JDK và runtime JDK nên được ghi nhận riêng khi tái hiện lỗi.

## 6. Dùng tài liệu theo đúng phiên bản: phương pháp đối chiếu

Đừng chỉ tìm “Java Math docs” rồi mở trang tìm kiếm đầu tiên. Một trang API của JDK mới có thể liệt kê phương thức mà bản đích chưa có. Hãy làm theo thứ tự:

1. Chốt **JDK đích**, ví dụ Java SE 17; ghi cả phiên bản dùng để build nếu khác.
2. Mở **API Specification** của đúng version, vào package/lớp/phương thức có liên quan. Ví dụ `java.lang.Math`, `java.math.BigDecimal`, `java.text.NumberFormat`.
3. Đọc **Since** ở phương thức, constructor hoặc lớp để biết lần đầu được giới thiệu. Kiểm tra cả **overload**: tên phương thức đã tồn tại từ trước không đồng nghĩa mọi chữ ký đều có từ trước.
4. Đọc **Deprecated** (đặc biệt `forRemoval`), **Preview**, **API Note**, **Throws**, lưu ý hành vi các giá trị biên và điều kiện rỗng/null.
5. Nếu API có trong JDK đích, kiểm tra lại bằng `javac --release <đích>`; nếu không có, cân nhắc giải pháp API cũ hoặc tăng minimum JDK một cách có chủ đích.
6. Khi nâng JDK, đọc **release notes** và **migration guide**, rồi thực thi bài kiểm thử trên đúng runtime triển khai; tài liệu API không thay thế kiểm chứng thực tế.

Các địa chỉ gốc hữu ích (nên mở và chuyển sang đúng phiên bản khi cần):

- [Java SE 8 API](https://docs.oracle.com/javase/8/docs/api/) — mốc đối chiếu các API lâu đời.
- [Java SE 11 API](https://docs.oracle.com/en/java/javase/11/docs/api/) — so sánh với hệ API trước JDK 12.
- [Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/) — mốc của các ví dụ Java 17+.
- [Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/) — kiểm tra API và phương thức bổ sung ở 21.
- [Java Language Specification](https://docs.oracle.com/javase/specs/) — quy tắc kiểu, toán tử và ngôn ngữ.
- [JDK Enhancement Proposals (JEP)](https://openjdk.org/jeps/0) — ngữ cảnh và trạng thái các thay đổi lớn.

**Đọc đúng cấp:** JLS dùng để xác minh phép `int / int` và chuyển kiểu; API docs dùng để xác minh `Math.addExact` hoặc `NumberFormat.getCompactNumberInstance`; release notes/migration docs dùng để điều tra hành vi bị ảnh hưởng khi nâng JDK.

## 7. Các mốc phiên bản minh họa trực tiếp bằng Numbers

Bảng sau tập trung vào một vài API kiểm chứng được, **không phải danh sách thay đổi đầy đủ** của mỗi phiên bản.

| Mốc | Ví dụ thuộc Numbers | Từ phiên bản | Ý nghĩa khi đối chiếu |
| --- | --- | --- | --- |
| Java 8 | `Math.addExact(int, int)`, `Integer.compareUnsigned` | 8 | Khi đích thấp hơn 8, không thể giả định các API này tồn tại |
| Java 9 | `Math.multiplyHigh(long, long)` | 9 | Phải kiểm tra `Since` của đúng overload |
| Java 12 | `NumberFormat.getCompactNumberInstance(...)`, `CompactNumberFormat` | 12 | Có cú pháp Java 11 hợp lệ vẫn không được dùng API này nếu target 11 |
| Java 17 | `java.util.random.RandomGenerator` và họ API random mới | 17 | Phải kiểm tra version khi đổi từ `Random` truyền thống sang API mới |
| Java 17 | JEP 306 khôi phục floating-point semantics luôn strict | 17 | Đối chiếu số thực không chỉ là tìm API mới |
| Java 21 | `Math.clamp(...)` | 21 | Phương thức không sẵn có trong Java 17; cần target 21 hoặc tự viết logic tương đương |

**Một lỗi dễ gặp:** nhìn thấy `Math` có từ lâu rồi cho rằng `Math.clamp` dùng được trên Java 8. Tuổi đời **lớp** và **phương thức** là hai thông tin khác nhau.

**Lưu ý số thực:** JEP 306 ở Java 17 làm phép toán dấu phẩy động tuân theo ngữ nghĩa strict thống nhất, thay cho phân biệt strict/default trước đó. Điều đó không làm `double` trở thành số thập phân chính xác. Với mã phụ thuộc kết quả dấu phẩy động hay hiệu năng, cần đọc đặc tả và chạy kiểm thử độ chính xác trên các runtime liên quan.

**Lưu ý sinh số ngẫu nhiên:** `RandomGenerator` cung cấp giao diện/thuật toán giả ngẫu nhiên mới từ 17; không mặc nhiên dùng nó cho mật mã. Khi cần số ngẫu nhiên phục vụ bảo mật, dùng `SecureRandom` theo hợp đồng bảo mật phù hợp.

## 8. Ví dụ A — Những phép tính Numbers cơ bản chạy với JDK 17+

Ví dụ minh họa các API tiêu chuẩn cũ, không phụ thuộc tính năng mới của JDK 21. Lưu tệp **`NumbersBase.java`**:

```java
import java.math.BigDecimal;

public class NumbersBase {
    public static void main(String[] args) {
        int total = 7;
        int groups = 2;

        System.out.println(total / groups);
        System.out.println((double) total / groups);
        System.out.println(Math.addExact(20, 22));

        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println(exact);
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac NumbersBase.java
java NumbersBase
```

Kết quả:

```text
3
3.5
42
0.3
```

Giải thích:

- `int / int` bỏ phần thập phân; khi ép một toán hạng sang `double` **trước phép chia**, kết quả là `3.5`.
- `Math.addExact` thực hiện phép cộng số nguyên có kiểm tra tràn. `20 + 22` nằm trong miền `int` nên trả `42`.
- `BigDecimal` khởi tạo từ **chuỗi thập phân** cho phép cộng thập phân chính xác ở ví dụ này.
- Kết quả dựa trên quy tắc số học chuẩn; sự tồn tại của API cần đối chiếu từ tài liệu phiên bản tương ứng, không dựa vào việc dùng JDK mới để biên dịch mặc định.

Nếu chương trình này cần tương thích Java 17 khi build trên JDK 21, sử dụng:

```bash
javac --release 17 NumbersBase.java
java NumbersBase
```

`--release 17` yêu cầu compiler biên dịch theo quy tắc ngôn ngữ, tạo class file và giới hạn Java SE/JDK API theo bản 17. Dòng `java NumbersBase` ở trên chạy bằng **runtime được terminal chọn**, nên vẫn cần thử trên JDK 17 thật nếu đó là bản phải hỗ trợ.

## 9. Ví dụ B — API ra đời sau bản đích: compact number formatting

Tạo tệp **`CompactNumbers.java`**:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class CompactNumbers {
    public static void main(String[] args) {
        NumberFormat format = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.SHORT);
        System.out.println(format.format(1200));
    }
}
```

`NumberFormat.getCompactNumberInstance` được giới thiệu từ **Java 12**. Vì vậy với compiler JDK 17 hoặc 21 hỗ trợ target 11:

```bash
javac --release 11 CompactNumbers.java
```

Lệnh **phải báo lỗi biên dịch** do phương thức compact formatting không tồn tại trong API Java 11; wording/line number của lỗi phụ thuộc phiên bản và cách chạy `javac`. Tiếp theo:

```bash
javac --release 17 CompactNumbers.java
java CompactNumbers
```

Mã có thể biên dịch vì Java 17 chứa API này. Chuỗi compact được in phụ thuộc dữ liệu locale và phiên bản runtime, nên không lấy một chuỗi đầu ra quan sát trên máy này làm hợp đồng bất biến của mọi JDK. Nếu dự án bắt buộc Java 11, hãy chọn `NumberFormat` kiểu cũ hoặc tự định nghĩa quy tắc viết gọn một cách có kiểm thử; đừng chỉ thay `--target`.

### Tại sao `--source` và `--target` riêng lẻ chưa đủ?

- `--source 11` xét **quy tắc cú pháp/ngôn ngữ** của Java 11.
- `--target 11` chọn **định dạng class file** cho phiên bản đích.
- Hai tùy chọn này **không tự bảo đảm** mọi Java SE API đang được tham chiếu đều tồn tại ở Java 11 nếu dùng classpath/platform API hiện tại.
- `--release 11` kết hợp cả ba ý: cú pháp, class file và Java SE/JDK API được tài liệu hóa của phiên bản 11. Không được kết hợp `--release` với `--source` hay `--target` trong cùng lời gọi.

Do đó, đối với dự án cần chạy trên bản Java cũ, **`--release` là điểm xuất phát phù hợp**. Vẫn cần rà các thư viện phụ thuộc và kiểm thử với runtime đích thật.

## 10. Ví dụ C — Nhìn đúng `Since` của phương thức JDK 21

Tạo tệp **`ClampNumbers.java`**:

```java
public class ClampNumbers {
    public static void main(String[] args) {
        System.out.println(Math.clamp(150, 0, 100));
        System.out.println(Math.clamp(-5, 0, 100));
    }
}
```

Các overload `Math.clamp` có từ **Java 21**. Chạy với JDK 21:

```bash
javac --release 21 ClampNumbers.java
java ClampNumbers
```

Kết quả:

```text
100
0
```

Nếu compiler hỗ trợ `--release 17`, chạy `javac --release 17 ClampNumbers.java` sẽ báo không tìm thấy phương thức tương ứng trong API 17. Đó là lỗi **API-version**, không có nghĩa phép so sánh giới hạn số là bất khả thi trên Java 17.

Trường hợp phải hỗ trợ Java 17, có thể viết hàm tương đương cho miền dữ liệu cụ thể:

```java
public static int clampInt(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    return Math.max(min, Math.min(max, value));
}
```

Đoạn trên là **phương thức minh họa**, đặt trong một class trước khi gọi; nó không thay thế mọi overload và mọi chi tiết hợp đồng của `Math.clamp` (đặc biệt số thực, `NaN`, signed zero). Đây chính là lý do phải đọc **chữ ký và hợp đồng** trước khi tự viết bản thay thế.

## 11. Bytecode: tại sao đã biên dịch vẫn có thể không chạy?

Một source file có thể compile thành class file ở phiên bản mới hơn runtime đích. Các mốc **class-file major version** thường thấy:

| Java release | Class-file major |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

Khi lớp được biên dịch theo Java 21 (major 65), runtime Java 17 (hỗ trợ đến major 61) không thể tải nó. Thông báo thường có `UnsupportedClassVersionError`. Đây là lỗi về **mức bytecode**, khác với thiếu một class hoặc method ở runtime.

Có thể xem thông tin class file bằng:

```bash
javap -verbose NumbersBase
```

Tìm dòng `major version: ...` trong kết quả. Lệnh `javap` được cung cấp cùng bộ công cụ JDK. Cách kiểm tra thực tế:

1. Biên dịch bằng compiler dự án với `--release` đặt đúng target.
2. Kiểm tra major version nếu cần chứng minh artifact phù hợp target.
3. Chạy bài test bằng Java runtime thực sự triển khai.
4. Đảm bảo mọi dependency dùng class file và API được runtime đích hỗ trợ.

`--release` điều khiển compilation của **source được biên dịch trong lời gọi đó**; nó không tự dịch lại JAR phụ thuộc đã build bằng JDK mới hoặc khắc phục khác biệt của provider ngoài Java SE.

## 12. Các khác biệt dễ bỏ sót dù chương trình vẫn compile

### 12.1. Hành vi so sánh và precision

Một phép toán `double` có thể cho kết quả gần đúng vì biểu diễn nhị phân. Thay đổi JDK không tự chữa `0.1 + 0.2 == 0.3`. Đặt tolerance khi đo đạc, hoặc dùng `BigDecimal` và quy tắc scale/rounding khi cần số thập phân có hợp đồng chính xác. Những phép toán có tính nhạy số học nên có test với dữ liệu biên trên các JDK được hỗ trợ.

### 12.2. Locale và dữ liệu định dạng

`NumberFormat`, `DecimalFormat`, dữ liệu locale/CLDR và nhà cung cấp dịch vụ locale có thể ảnh hưởng cách hiển thị cùng một số giữa các môi trường. Không viết test so sánh tuyệt đối chuỗi “1.234,50” trên máy này với chuỗi từ mọi locale khác.

Muốn kết quả dự đoán được, truyền `Locale` cụ thể, thống nhất currency, quy tắc rounding và dữ liệu provider; tránh vô tình dùng locale mặc định. Dù đã cố định locale, dữ liệu/nguyên tắc định dạng có thể được cập nhật giữa JDK; test nào phụ thuộc từng ký tự cần nêu rõ phiên bản runtime và yêu cầu nghiệp vụ.

### 12.3. Deprecation, Preview, Incubator, API nội bộ

- Một API được gắn `@Deprecated` có thể **vẫn compile** trên bản hiện tại, nhưng cần xem lý do, ngày giới thiệu cảnh báo và có đánh dấu “for removal” không.
- **Preview feature/API** có điều kiện kích hoạt riêng và có thể đổi hoặc bị loại bỏ ở bản sau. Đừng dựa vào preview cho bài Numbers cơ bản trừ khi thực sự phải thử tính năng đó.
- **Incubator module** không đồng nghĩa API chuẩn ổn định của `java.base`; kiểm tra trạng thái cụ thể ở version sử dụng.
- `sun.*`, `jdk.internal.*` không phải bề mặt API chuẩn nên tránh dựa vào chúng chỉ để thực hiện phép toán số thường ngày.

### 12.4. Khác nhau giữa version và nhà cung cấp

Cùng Java SE feature release nhưng vendor/build/update khác nhau có thể mang bản vá, dữ liệu hệ thống hoặc lịch hỗ trợ khác. Khi tái hiện lỗi, ghi nguyên đầu ra `java -version`, bản OS/architecture, cờ JVM cần thiết và dữ liệu input. Khi quyết định nâng cấp JDK, đối chiếu chính sách hỗ trợ của **nhà cung cấp đang dùng**, không suy ra từ nhãn LTS chung chung.

## 13. Quy trình 7 bước để kiểm tra một đoạn code Numbers bất kỳ

Giả sử bạn thấy đoạn `Math.clamp(amount, 0, 100)` trong tài liệu hoặc trên diễn đàn.

**Bước 1 — Ghi môi trường đích.** Ví dụ: dự án biên dịch trên JDK 21 nhưng sản phẩm phải chạy trên Java 17; ghi rõ 17 là **minimum runtime**.

**Bước 2 — Tách cú pháp với lời gọi API.** `amount` là `int`, lời gọi `Math.clamp` thuộc thư viện chuẩn; vấn đề có thể ở phương thức, không phải toán tử hoặc cú pháp Java.

**Bước 3 — Tìm đúng chữ ký.** Mở API `Math` của Java 17 và 21, đối chiếu tên, parameter types, overload, `Since` và `Throws`.

**Bước 4 — Thử biên dịch theo target.** Trên compiler mới có hỗ trợ target 17, chạy `javac --release 17 ...`. Nếu báo lỗi, đọc lỗi để phân biệt thiếu API, lỗi kiểu, lỗi tên class và lỗi cú pháp.

**Bước 5 — Chọn hành động.** Nếu API có từ 21, hoặc nâng mức tối thiểu runtime **theo quyết định của dự án**, hoặc thay bằng logic tương thích 17 và test ranh giới.

**Bước 6 — Test runtime thực.** Kiểm tra class-file major và chạy test trên JDK 17 đã cam kết. Với dữ liệu số, bao gồm 0, số âm, min/max, sai số, `NaN`/vô cực (nếu nhận `double`), scale/rounding và locale khi liên quan.

**Bước 7 — Ghi lại bằng chứng.** Một mô tả có thể lặp lại gồm code, target release, compile JDK, runtime JDK, lệnh test, output và nguồn tài liệu API; đừng ghi đơn thuần “hỗ trợ Java 17” khi mới chỉ nhìn mã.

Ví dụ báo cáo kỹ thuật đủ rõ:

```text
Mục tiêu: chạy trên Java 17
Build JDK: 21
Compiler flags: javac --release 17
API kiểm tra: Math.addExact(int,int) - Since 8
Kiểm tra runtime: test trên JDK 17 của môi trường triển khai
Rủi ro còn lại: dependency ngoài JDK và provider/locale cần test riêng
```

Đây là **mẫu báo cáo**, không phải kết quả kiểm thử đã thực hiện cho một dự án có thật.

## 14. Các câu hỏi tự kiểm tra

1. `BigInteger` và `BigDecimal` có phải cài thêm dependency Maven không? **Không.** Đây là API chuẩn trong `java.math`.
2. Tại sao code gọi `NumberFormat.getCompactNumberInstance` chạy trên JDK 17 nhưng bị lỗi khi biên dịch với `--release 11`? **Vì API này được giới thiệu từ Java 12**, không nằm trong API đích 11.
3. Dùng JDK 21, compile `--source 17 --target 17` có tự ngăn tham chiếu method chỉ có trong 21 không? **Không bảo đảm**; dùng `--release 17` để giới hạn cả API.
4. Class file major 65 chạy trên Java 17 được không? **Không**; Java 17 hỗ trợ class file đến major 61.
5. `Math` có từ Java lâu rồi, vậy `Math.clamp` có trong Java 17? **Không**; kiểm tra `Since 21` của overload tương ứng.
6. Hai JDK cùng Java 17 có thể khác dữ liệu locale hoặc bản vá không? **Có thể**; cần ghi vendor/build/update và thử trong môi trường thực tế.
7. Chỉ cần biên dịch được là đủ khẳng định “chạy trên Java 17”? **Chưa.** Phải đối chiếu APIs, class file, dependencies và runtime.
8. Khi học Numbers, đâu là điểm xuất phát phù hợp? **Bám JDK mục tiêu**, luyện primitives/`Math`/wrapper/`BigDecimal` theo API tương ứng, sau đó mới thử các tính năng mới hơn.

## 15. Checklist khi đọc mỗi bài Java Core — Numbers tiếp theo

- [ ] Tôi biết **minimum supported Java release** của bài tập/dự án.
- [ ] Tôi đã tách cú pháp ngôn ngữ với lớp/phương thức thuộc Java SE API.
- [ ] Tôi mở đúng tài liệu **API của phiên bản đích**, không chỉ trang JDK mới nhất.
- [ ] Tôi kiểm tra `Since` trên chính **phương thức/overload** đang dùng, cùng `Throws`, `Deprecated` và trạng thái preview nếu có.
- [ ] Tôi biết compiler JDK và runtime JDK hiện hành, không nhầm cài đặt IDE/CI/shell.
- [ ] Tôi dùng `--release` khi biên dịch theo bản đích cũ được compiler hỗ trợ.
- [ ] Tôi thử chạy trên runtime đích, rà cả phụ thuộc bên ngoài và class-file version.
- [ ] Tôi kiểm tra kết quả số, overflow, precision, rounding, locale và dữ liệu biên khi có liên quan.
- [ ] Tôi lưu lại phiên bản, lệnh và kết quả để người khác có thể tái hiện.

**Tài liệu tham khảo chính thức** để tự xác minh: [JDK 17 Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html), [JDK 21 Math API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html), [JDK 17 BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [JDK 12 NumberFormat API](https://docs.oracle.com/en/java/javase/12/docs/api/java.base/java/text/NumberFormat.html), [JDK 17 random package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html), [javac command specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) và [JDK 17 migration notes](https://docs.oracle.com/en/java/javase/17/migrate/significant-changes-jdk-release.html).