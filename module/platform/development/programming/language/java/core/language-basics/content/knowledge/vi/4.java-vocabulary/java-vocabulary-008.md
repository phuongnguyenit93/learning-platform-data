# Unicode trong mã nguồn và xử lý Unicode escape trước phân tích token — Java 17+

Trong Java, một chuỗi ký tự giống `\u0041` không nhất thiết được chờ đến lúc chương trình chạy mới chuyển thành chữ `A`. **Unicode escape hợp lệ trong mã nguồn được xử lý rất sớm, trước khi Java nhận diện comment, string literal, identifier hoặc từ khóa.**

Đây là một đặc điểm quan trọng của *quá trình dịch mã nguồn* trong Java. Nó giải thích vì sao một ký tự viết dưới dạng `\u0061` có thể trở thành một phần tên biến; vì sao `\u000a` có thể kết thúc comment; và vì sao một cách viết tưởng như nằm trong string lại gây lỗi biên dịch.

Mục tiêu của bài: hiểu thứ tự xử lý, phân biệt Unicode escape của **mã nguồn** với escape của **string/char literal**, và tự kiểm chứng trên **JDK 17 trở lên**.

## 1. Ba tầng xử lý dễ bị nhầm

Hãy hình dung tệp `.java` được xử lý theo thứ tự:

~~~text
Tệp .java lưu dưới UTF-8
        │ javac -encoding UTF-8
        ▼
Ký tự đầu vào đã được giải mã từ byte
        │ Bước xử lý Unicode escape hợp lệ: \uXXXX
        ▼
Chuỗi ký tự Java sau chuyển đổi Unicode escape
        │ Nhận diện kết thúc dòng, comment, identifier,
        │ keyword, toán tử, string/char literal ...
        ▼
Các token để phân tích cú pháp và kiểm tra kiểu
        │
        ▼
Bytecode (.class), nếu mã hợp lệ
~~~

**Thứ tự là điểm cốt lõi.** Unicode escape được xử lý **trước khi** token hóa; điều này áp dụng ngay cả khi văn bản trông như đang nằm trong comment hoặc string.

| Thứ cần phân biệt | Ví dụ | Giai đoạn/ý nghĩa |
| --- | --- | --- |
| Mã hóa tệp nguồn | UTF-8 | Quy tắc giải mã byte thành ký tự khi đọc tệp |
| Unicode escape trong nguồn | `\u0041` | Được chuyển thành ký tự `A` trước khi phân tích token, nếu đủ điều kiện |
| Escape trong Java string | `\n`, `\t`, `\\`, `\"` | Được hiểu theo cú pháp string/char literal sau bước Unicode escape |
| Unicode code point | U+1F680 (🚀) | Một ký tự Unicode có thể cần **hai** đơn vị mã UTF-16 |
| Kiểu `char` | `'A'` | Một **UTF-16 code unit**, không nhất thiết là một Unicode code point đầy đủ |

Cú pháp Unicode escape thông thường là **dấu gạch chéo ngược**, một hoặc nhiều chữ `u` thường, rồi **chính xác bốn chữ số thập lục phân** (`0–9`, `a–f`, `A–F`). Ví dụ `\u0041` và `\uuuu0041` đều biểu diễn `A` ở bước chuyển đổi của mã nguồn. Nó **không** có dạng `\u{1F680}` trong Java.

## 2. Ví dụ runnable: escape làm thay đổi cả tên biến

Tạo tệp **`UnicodeStageDemo.java`** dưới dạng UTF-8:

~~~java
public class UnicodeStageDemo {
    public static void main(String[] args) {
        int ca\u0074 = 3;             // Ten bien sau dich: cat.
        String fromEscape = "\u0041";  // Sau dich: "A".
        String literalText = "\\u0041";
        String rocket = "🚀";

        System.out.println("cat=" + cat);
        System.out.println("fromEscape=" + fromEscape);
        System.out.println("literalText=" + literalText);
        System.out.println("utf16Length=" + rocket.length());
        System.out.println(
                "codePoints=" +
                rocket.codePointCount(0, rocket.length()));
    }
}
~~~

**Biên dịch và chạy** trong thư mục chứa tệp, trên Windows PowerShell hoặc Linux/Bash:

~~~bash
java -version
javac -version
javac -encoding UTF-8 UnicodeStageDemo.java
java UnicodeStageDemo
~~~

Kết quả dự kiến:

~~~text
cat=3
fromEscape=A
literalText=\u0041
utf16Length=2
codePoints=1
~~~

**Giải thích từng kết quả:**

1. `ca\u0074` được chuyển thành `cat` **trước khi phân tích identifier**. Vì vậy mã có thể khai báo bằng cách viết có escape và sử dụng biến bằng `cat`.
2. `"\u0041"` trở thành chuỗi nguồn `"A"` trước khi token hóa; giá trị chạy là `A`.
3. `"\\u0041"` chứa **hai dấu backslash trong tệp nguồn**. Theo quy tắc *điều kiện nhận Unicode escape* của Java, dấu thứ hai trong cặp đó không bắt đầu Unicode escape; khi xử lý string literal, `\\` biểu diễn **một** backslash. Vì vậy chương trình thực sự in chuỗi ký tự `\u0041`.
4. `🚀` là Unicode code point U+1F680, nằm ngoài Basic Multilingual Plane. Một `String` Java lưu dưới dạng các đơn vị mã UTF-16: `length()` trả `2` cho surrogate pair, trong khi `codePointCount(...)` trả `1`.

Đoạn ví dụ chỉ in chữ ASCII và số ở đầu ra, nên kết quả ít phụ thuộc cách terminal hiển thị emoji; tuy nhiên **tệp nguồn phải được lưu đúng UTF-8**.

## 3. Unicode escape được xử lý cả ở nơi trông như comment

Xem đoạn sau — một ví dụ **cố ý gây bất ngờ**. Tạo riêng tệp **`CommentBoundary.java`**:

~~~java
public class CommentBoundary {
    public static void main(String[] args) {
        // \u000a System.out.println("THIS RUNS");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CommentBoundary.java
java CommentBoundary
~~~

Đầu ra:

~~~text
THIS RUNS
~~~

**Tại sao dòng tưởng là comment vẫn in ra?**

- `\u000a` biểu diễn ký tự xuống dòng LF.
- Trước khi Java nhận diện comment `//`, Unicode escape được chuyển thành **xuống dòng thật**.
- Vì vậy, Java nhìn thấy comment kết thúc ngay tại dòng mới ấy; câu lệnh `System.out.println(...)` nằm **sau comment** và được thực thi.

Nếu diễn tả mã **sau bước dịch Unicode escape**, nó tương đương về ý nghĩa với:

~~~java
// comment ket thuc tai day
System.out.println("THIS RUNS");
~~~

**Đừng dùng mẹo này trong mã thực tế.** Nó gây khó đọc, dễ làm công cụ phân tích/lint không theo đúng bước chuyển đổi hiểu sai và tạo nguy cơ khi review mã. Dùng xuống dòng thật và comment rõ ràng.

### Bẫy tương tự trong string và char literal

Các đoạn sau **cố ý không biên dịch** nếu đưa vào một phương thức:

~~~java
// String s = "\u000a"; // Khong dung: escape tao xuong dong
// char c = '\u000a';   // Khong dung: escape tao xuong dong
~~~

Hai dòng ở trên được viết dưới dạng comment để minh họa, **nhưng chính Unicode escape trong comment cũng vẫn có thể được chuyển đổi**. Vì thế **không nên chép chúng vào tệp Java để tắt lỗi bằng `//`**.

Trong tài liệu, ta hiểu các mẫu `"\u000a"` và `'\u000a'` là văn bản **trước** xử lý Unicode escape: chúng sẽ làm đứt literal thành nhiều dòng, gây lỗi biên dịch. Nếu muốn chứa ký tự xuống dòng trong một chuỗi Java bình thường, hãy dùng escape của string literal:

~~~java
String safe = "\n"; // Hop le, 1 ky tu xuong dong luc chay.
System.out.println(safe.length()); // 1
~~~

**Lưu ý an toàn về cách ghi ví dụ lỗi:** Đoạn `// String s = "\u000a";` trên được hiển thị trong README để phân tích, không phải câu lệnh để đưa vào file nguồn. Trong Java thật, lexer vẫn xử lý `\u000a` trong comment, nên cách comment-out thông thường **không che được** nó. Đây chính là nội dung bài học.

## 4. Phân biệt `\uXXXX` với các escape ở thời điểm chạy

| Trong tệp `.java` | Kết quả của bước Unicode escape | Giá trị/hiệu ứng |
| --- | --- | --- |
| `"\u0041"` | `"A"` | Chuỗi chứa chữ `A` |
| `'\u0042'` | `'B'` | `char` chứa chữ `B` |
| `"\\u0041"` | Không chuyển cặp `\\u0041` thành `A` | String chứa backslash và năm ký tự `u0041` |
| `"\n"` | Không phải Unicode escape | String có một ký tự xuống dòng nhờ escape của literal |
| `\u0069nt number = 1;` | `int number = 1;` | `int` được nhận diện là keyword |
| `// \u000a printSomething();` | Xuống dòng được chèn **trước** phân tích comment | Phần sau có thể trở thành mã Java ngoài comment |

Không phải cứ thấy backslash + `u` là mã chắc chắn chuyển đổi ngay. Java có **quy tắc xác định backslash nào đủ điều kiện mở Unicode escape**, phụ thuộc vào chuỗi backslash liền trước. Ví dụ nguồn `"\\u0041"` không dịch thành `"A"`. Không cần học thuộc công thức đếm mọi backslash khi mới bắt đầu; hãy nhớ **khác biệt giữa một và hai backslash**, và dùng `javac` để tự kiểm chứng khi mã phức tạp.

Cũng đừng nghĩ có thể viết `\u005c` (escape tạo ra ký tự backslash) rồi ghép thêm `u0041` để khiến compiler dịch nhiều lượt. **Unicode escape không được xử lý lặp vô hạn**; ký tự backslash sinh ra từ bước dịch không tự bắt đầu một Unicode escape mới.

## 5. Unicode trong identifier và quy tắc đặt tên

Java cho phép nhiều ký tự Unicode trong identifier, tùy các quy tắc `Character.isJavaIdentifierStart` / `Character.isJavaIdentifierPart` và các ngoại lệ theo đặc tả ngôn ngữ. Vì vậy, identifier không nhất thiết chỉ gồm `A-Z`, `a-z` và chữ số ASCII.

Ví dụ có thể khai báo identifier tiếng Việt:

~~~java
int sốNgày = 3;
System.out.println(sốNgày); // 3
~~~

Tuy nhiên:

- Java **phân biệt chữ hoa và chữ thường**; tên phải khớp chính xác.
- Hai ký tự **trông giống nhau** không bảo đảm là cùng code point. Ví dụ ký tự Latin `a` và một ký tự từ hệ chữ khác có hình tương tự có thể tạo hai identifier khác nhau.
- Dạng ký tự tổ hợp và dạng ký tự dựng sẵn có thể hiển thị gần giống; đừng giả định Java tự chuẩn hóa mọi identifier theo cách bạn mong muốn.
- Với code nhóm, ưu tiên tên dễ đánh máy, dễ tìm kiếm và nhất quán theo convention. Unicode escape để “giấu” một phần tên thường làm mã khó review.

Với chữ ngoài Basic Multilingual Plane, `String` Java có thể lưu bằng **surrogate pair**; `char` vẫn chỉ đại diện một đơn vị mã UTF-16. Vì vậy, muốn xử lý Unicode theo code point thay vì code unit, dùng các API như `codePointAt`, `codePointCount` và `String.codePoints()` khi phù hợp.

## 6. Lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân cần xem | Cách xử lý |
| --- | --- | --- |
| `illegal unicode escape` | `\u` không đủ bốn chữ số hex, hoặc chữ số sai | Sửa đúng escape hay bỏ backslash nếu muốn văn bản thuần |
| `unclosed string literal` | `\u000a` hoặc `\u000d` tạo line terminator trước khi phân tích literal | Dùng `\n` hoặc `\r` bên trong string literal |
| Dòng tưởng comment vẫn chạy | Escape trong `//` tạo newline | Không viết Unicode escape có hiệu ứng tách dòng trong comment |
| `cannot find symbol` với identifier | Tên sau xử lý escape khác tên bạn tham chiếu | Xem ký tự thật, chữ hoa/thường, code point |
| Ký tự tiếng Việt hoặc emoji bị lỗi khi biên dịch | Mã hóa file không khớp cách `javac` đọc nguồn | Lưu UTF-8, biên dịch với `-encoding UTF-8` |
| `String.length()` lớn hơn số ký tự nhìn thấy | Java đếm UTF-16 code unit, không phải code point hoặc grapheme cluster | Dùng API code point nếu đó là đơn vị muốn đếm |

`codePointCount` cũng **không** tự đếm “số ký tự người dùng nhìn thấy” (*grapheme clusters*): emoji ghép hoặc chữ có dấu kết hợp có thể gồm nhiều code point nhưng được hiển thị như một ký tự. Đừng dùng `length()` hay `codePointCount()` như một bộ đếm ký tự giao diện người dùng hoàn hảo nếu chưa xác định đơn vị cần đếm.

### Checklist kiểm tra khi gặp lỗi liên quan Unicode

1. File đang được lưu ở **mã hóa** nào? `javac` đang dùng encoding nào?
2. Chuỗi `\u....` có đủ điều kiện để trở thành Unicode escape không?
3. Sau khi dịch escape, ký tự đó có thể biến thành newline, dấu nháy, ký tự phân cách token hoặc một phần identifier không?
4. Thông báo lỗi xảy ra **khi biên dịch** hay sau khi chương trình đã chạy?
5. Bạn muốn đếm **UTF-16 code unit**, **code point**, hay **ký tự hiển thị**?

## 7. Bài tập thực hành

**Bài 1 — Dự đoán trước khi chạy.** Trong `UnicodeStageDemo`, nếu đổi `ca\u0074` thành `nu\u006Dber`, biến thực sự có tên gì?

*Đáp án:* `number`, vì `\u006D` được chuyển thành `m` trước khi lexer nhận diện identifier. Nhớ đổi nơi sử dụng biến tương ứng.

**Bài 2 — Một hay hai backslash?** So sánh hai dòng:

~~~java
String a = "\u0041";
String b = "\\u0041";
~~~

*Đáp án:* `a` chứa `A`; `b` chứa sáu ký tự gồm một backslash và `u0041`. Khi in, `b` hiển thị `\u0041`.

**Bài 3 — Vì sao comment có thể nguy hiểm?** Giải thích kết quả của `CommentBoundary` trước khi chạy. Tìm bước nào phải xảy ra **trước** phân tích `//`.

*Đáp án:* Unicode escape `\u000a` chuyển thành newline trước bước nhận diện comment, khiến phần sau trở thành câu lệnh thật.

**Bài 4 — Dùng string escape đúng.** Muốn string Java chứa một ký tự xuống dòng, nên viết `"\u000a"` hay `"\n"`?

*Đáp án:* `"\n"`. Unicode escape `\u000a` bị dịch thành line terminator quá sớm; `\n` là escape được phân tích trong string literal, tạo ký tự xuống dòng đúng ý định.

**Bài 5 — Code point và `char`.** Vì sao `"🚀".length()` trả về 2 nhưng `"🚀".codePointCount(0, "🚀".length())` trả về 1? Có thể dùng một `char` duy nhất để chứa toàn bộ code point U+1F680 không?

*Đáp án:* `String` dùng UTF-16; U+1F680 cần hai code unit (*surrogate pair*). Một `char` riêng lẻ không đủ để biểu diễn trọn code point đó.

## Ghi nhớ

**Unicode escape trong mã nguồn Java được xử lý trước khi tách token**, nên nó có thể thay đổi cả identifier, từ khóa, comment và ranh giới string literal. Điều này khác với escape như `\n` bên trong Java string, khác với encoding UTF-8 của tệp nguồn, và khác với quy tắc đếm UTF-16 của `String`. Khi gặp mã Unicode khó hiểu, hãy hình dung **tệp nguồn → dịch Unicode escape → nhận diện token → phân tích cú pháp**, rồi mới xem hành vi khi chạy.
