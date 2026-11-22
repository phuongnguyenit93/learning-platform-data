# Phân biệt văn bản thông thường với cấu trúc có ngữ pháp khi thiết kế API Java

## Mục tiêu

Một biến Java có kiểu `String` chỉ cho biết nó chứa một chuỗi ký tự Unicode. Kiểu `String` **không cho biết** nội dung đó là câu văn để hiển thị, mã đơn hàng, địa chỉ URL, biểu thức chính quy, truy vấn SQL hay tài liệu JSON. Những loại nội dung này có thể cùng được truyền qua `String`, nhưng mỗi loại có **quy tắc cấu trúc, ý nghĩa và cách xử lý khác nhau**.

Khi thiết kế API, cần nhận ra ranh giới quan trọng:

- **Văn bản thông thường (plain/free text):** chủ yếu là nội dung dành cho con người, ví dụ tên hiển thị, nhận xét, mô tả sản phẩm. Những ký tự như dấu phẩy, dấu ngoặc hoặc dấu `*` có thể chỉ là chính chúng.
- **Văn bản có ngữ pháp (structured text):** dãy ký tự được đọc bởi một bộ phân tích cú pháp, ví dụ `ORD-0042` theo quy tắc mã đơn hàng, `https://example.com?q=java` theo cú pháp URI, hoặc `a.*b` theo cú pháp regular expression.
- **Biểu diễn dữ liệu có cấu trúc:** dữ liệu có trường, phần tử, kiểu và quy tắc ràng buộc, ví dụ JSON hoặc CSV. Ở Java, có thể nhận dữ liệu dưới dạng văn bản, nhưng phải phân tích theo đúng ngữ pháp mới hiểu được cấu trúc.

Bài học giúp bạn xác định khi nào cần giữ nguyên chuỗi, khi nào cần parse và validate, và khi nào phải dùng API tạo cấu trúc thay vì ghép chuỗi thủ công.

## 1. Cùng là `String`, nhưng không cùng ý nghĩa

Hãy xét:

```java
String comment = "Tôi thích ký hiệu .* trong ví dụ";
String regex = ".*";
String productCode = "ORD-0042";
String jsonText = "{\"name\":\"Java\",\"count\":3}";
```

Bốn biến đều là `String`. Tuy nhiên:

| Giá trị | Vai trò | Cách xử lý đúng |
| --- | --- | --- |
| `comment` | Văn bản tự do để hiển thị hoặc lưu trữ | Giữ nguyên nội dung theo hợp đồng API; escape đúng khi đưa vào môi trường hiển thị có cú pháp |
| `regex` | Biểu thức chính quy | Đưa qua `Pattern.compile` nếu ứng dụng thực sự muốn diễn giải regex |
| `productCode` | Mã định danh có mẫu hợp lệ | Kiểm tra toàn bộ chuỗi theo quy tắc nghiệp vụ; cân nhắc value object riêng |
| `jsonText` | Tài liệu JSON | Dùng JSON parser để kiểm tra cú pháp và dựng kiểu dữ liệu; không tự tách bằng `split` đơn giản |

**Dấu câu không có ý nghĩa cố định cho mọi `String`.** Dấu `.` trong câu văn là dấu chấm, nhưng trong regex nó có thể đại diện cho một ký tự bất kỳ. Dấu `&` là một ký tự trong tên người dùng; khi đặt trong query string URL, nó thường ngăn cách các tham số. Ký tự `"` trong câu trích dẫn không đồng nghĩa với dấu mở/đóng chuỗi trong JSON nếu chưa đi qua bộ mã hóa JSON.

Nói cách khác, **ý nghĩa đến từ hợp đồng API và parser**, không phải chỉ từ việc giá trị có kiểu `String`.

## 2. Thiết kế API: nêu rõ đầu vào là nội dung hay cú pháp

Một API khó dùng thường gom mọi thứ vào tham số tên chung chung:

```java
void process(String value); // value là nội dung, URL, biểu thức hay mã?
```

Các tên và kiểu có ý nghĩa giúp người gọi hiểu rõ kỳ vọng:

```java
void saveDisplayName(String displayName);
void addOrderByCode(OrderCode code);
void fetchDocument(java.net.URI documentUri);
void searchLiteralText(String literalText);
void searchByPattern(java.util.regex.Pattern pattern);
```

Đây là **chữ ký minh họa**, không phải lớp Java chạy độc lập. `OrderCode` trong ví dụ là một value object do ứng dụng định nghĩa.

Một số quy tắc thiết kế có ích:

1. Với dữ liệu **hiển thị**, xác định có cần bảo toàn chính xác chữ hoa/thường, Unicode, dấu cách, xuống dòng và ký tự đặc biệt hay không. Đừng tự sửa văn bản gốc chỉ vì nó chứa ký tự trùng với dấu cú pháp của một định dạng khác.
2. Với **mã định danh**, định nghĩa tập ký tự, độ dài, phần tiền tố, chính sách hoa/thường, cách báo lỗi và việc có chuẩn hóa hay không.
3. Với **cú pháp dành cho máy**, ưu tiên loại đối tượng đã được parse khi thích hợp: `URI`, `Path`, `Pattern`, `LocalDate`, enum hoặc record giá trị đã kiểm chứng.
4. Với tài liệu **JSON/XML/CSV**, xác định parser/serializer và mô hình dữ liệu. Một JSON string bất kỳ chưa chắc là JSON hợp lệ.
5. Với dữ liệu người dùng được đưa vào **cú pháp khác**, hiểu cách encode hoặc parameterize đúng ngữ cảnh. Không đặt dữ liệu tùy ý vào vị trí mã lệnh bằng nối chuỗi.

API nên tách riêng hai trường hợp: **người dùng nhập các ký tự theo nghĩa nguyên văn** và **người dùng chủ động cung cấp một biểu thức theo cú pháp đã được công bố**. Ví dụ ô tìm kiếm thông thường không nên âm thầm hiểu dấu `*` hoặc `.` thành regex nếu giao diện chưa nói rõ điều đó.

## 3. Phân biệt xác thực dữ liệu với phân tích cú pháp

Ba thao tác liên quan nhưng không đồng nghĩa:

- **Validation:** kiểm tra giá trị có thỏa ràng buộc đã định không. Ví dụ mã đơn hàng phải khớp `ORD-` và bốn chữ số ASCII.
- **Parsing:** diễn giải chuỗi theo ngữ pháp và chuyển thành cấu trúc hoặc kiểu có ý nghĩa. Ví dụ `LocalDate.parse("2026-10-23")` tạo đối tượng ngày hoặc báo lỗi cú pháp.
- **Encoding/escaping:** chuyển ký tự dữ liệu thành biểu diễn hợp lệ ở một ngữ cảnh đầu ra, như tham số URL, chuỗi JSON, văn bản HTML. Việc này không tự chứng minh nội dung đầu vào là hợp lệ theo quy tắc nghiệp vụ.

Ví dụ `"ORD-0042"` có thể là mã đơn hàng hợp lệ theo chính sách ứng dụng, còn `"ORD-42 abc"` không hợp lệ. Dùng `Pattern.matcher(value).matches()` để yêu cầu **khớp toàn bộ chuỗi**:

```java
import java.util.regex.Pattern;

Pattern orderCode = Pattern.compile("ORD-[0-9]{4}");

System.out.println(orderCode.matcher("ORD-0042").matches()); // true
System.out.println(orderCode.matcher("ORD-42 abc").matches()); // false
```

`find()` tìm một đoạn con khớp mẫu; `matches()` yêu cầu cả input khớp. Với mã định danh, dùng `find()` có thể vô tình cho phép tiền tố/hậu tố thừa.

Cần phân biệt **hợp lệ về cú pháp** và **hợp lệ về nghiệp vụ**. `ORD-0042` đúng định dạng nhưng có thể không tồn tại trong cơ sở dữ liệu, không thuộc người gọi hoặc đã hết hiệu lực. Regex không thể thay thế kiểm tra quyền, trạng thái và tính duy nhất.

## 4. Regex: văn bản literal và ngôn ngữ biểu thức chính quy

Regex là ví dụ dễ thấy nhất cho việc chuỗi có ngữ pháp. Trong regex:

- `.` có nghĩa là một ký tự phù hợp, thay vì dấu chấm văn bản;
- `*` là toán tử lặp cho biểu thức đứng trước;
- `[ab]` là lớp ký tự gồm `a` hoặc `b`;
- `|` có nghĩa là lựa chọn giữa hai nhánh.

Nếu người dùng muốn tìm đúng chuỗi `a.b`, thì:

```java
Pattern wrong = Pattern.compile("a.b");
System.out.println(wrong.matcher("axb").find()); // true
```

Regex `a.b` cũng khớp `axb`. Đó không phải hành vi tìm kiếm literal.

Khi nhận **nội dung cần tìm nguyên văn**, dùng `Pattern.quote(literal)` để tạo một regex khớp đúng các ký tự của chuỗi literal:

```java
String literal = "a.b";
Pattern exactText = Pattern.compile(Pattern.quote(literal));

System.out.println(exactText.matcher("read a.b now").find()); // true
System.out.println(exactText.matcher("read axb now").find()); // false
```

Không cần biến mọi thao tác tìm chuỗi thành regex. Nếu yêu cầu chỉ là tìm đoạn con theo đúng ký tự, `String.contains` hoặc `indexOf` thường trực tiếp và dễ hiểu hơn:

```java
System.out.println("read a.b now".contains("a.b")); // true
```

**Bẫy của `String.split`:** tham số của `split(regex)` là **regex**, không phải dấu phân cách literal. Ví dụ `"A|B|C".split("|")` không thể được hiểu đơn giản là tách theo dấu `|`, vì `|` là toán tử regex. Để tách theo đúng một dấu phân cách từ biến:

```java
String delimiter = "|";
String[] parts = "A|B|C".split(Pattern.quote(delimiter), -1);
```

Tham số `-1` giữ cả các phần tử rỗng cuối chuỗi. Với định dạng CSV, chỉ dùng `split(",")` vẫn chưa đủ nếu có dấu phẩy bên trong trường được bao bởi dấu nháy; trường hợp đó cần parser CSV đúng quy tắc.

## 5. Khi chuỗi chứa URI, ý nghĩa các dấu phân cách đến từ cú pháp

Một người dùng có thể gõ \`An & Binh\` như tên hiển thị, nhưng khi chuỗi ấy trở thành **giá trị query** thì \`&\` có thể bị hiểu là dấu phân cách tham số nếu được nối trực tiếp. Với form-style query value, \`URLEncoder\` xử lý dữ liệu theo đúng quy tắc:

~~~java
String value = "An & Binh";
String encoded = java.net.URLEncoder.encode(
        value, java.nio.charset.StandardCharsets.UTF_8);
System.out.println(encoded); // An+%26+Binh
~~~

\`URLEncoder\` không phải bộ mã hóa chung cho **toàn URI, path segment hoặc fragment**. Nếu hợp đồng yêu cầu địa chỉ, dùng \`java.net.URI\`/URI builder phù hợp, phân tích scheme, host, path và kiểm tra đích sau khi resolve. Parse thành công không chứng minh địa chỉ được phép truy cập.

## 6. JSON và CSV là tài liệu có cấu trúc, không phải một danh sách ký tự

Với JSON, dấu \`",\`, backslash, cặp ngoặc, array/object và các kiểu dữ liệu mang nghĩa cú pháp. Với CSV, một dấu phẩy hoặc newline **có thể nằm bên trong trường được quote**, còn \`""\` là cách diễn tả dấu nháy trong dialect thông dụng. Vì vậy \`split(",")\` và \`split("\n")\` không đủ để phân tích tài liệu tổng quát.

~~~json
{"title":"Java, Strings","completed":true}
~~~

~~~csv
name,note
"Nguyễn, An","Câu nói ""Java"" rất hay"
~~~

Dùng JSON parser/serializer như Jackson hoặc CSV parser/writer theo dialect đã thống nhất; Java SE 17 không tích hợp serializer JSON tổng quát. Truyền object/record đã parse cho domain thay vì truyền JSON/CSV string mơ hồ đi qua nhiều tầng. Bài kế tiếp trình bày riêng các edge case và cách dùng thư viện.

## 7. Những cú pháp có thể thực thi cần tách biệt dữ liệu

Với SQL, truyền giá trị bằng \`PreparedStatement\` thay vì nối thành câu truy vấn. Với HTML, render văn bản bằng text node hoặc template có auto-escaping đúng vị trí; tránh ghép nội dung người dùng thành markup. Với lệnh hệ thống, ưu tiên \`ProcessBuilder\` truyền executable và từng đối số thay vì đưa cả chuỗi người dùng qua shell.

~~~java
String sql = "SELECT id FROM users WHERE name = ?";
try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, userInput); // userInput là dữ liệu, không phải cú pháp SQL
}
~~~

Đây là đoạn code minh họa, giả định có \`java.sql.Connection connection\` và \`String userInput\`. Tham số SQL không thể thay tên bảng/cột; phần cấu trúc động vẫn cần allowlist. Trong HTML, JavaScript, CSS, SQL hoặc command, mỗi ranh giới có cú pháp riêng: một phép escape chung cho tất cả đều không đủ. Bài cuối chương đi sâu vào **trách nhiệm của từng output adapter**, bao gồm double escaping và decode nhiều lần.

## 8. Một kiểu dữ liệu riêng giúp API rõ hợp đồng

Một value object là lựa chọn hữu ích nếu chuỗi được dùng nhiều nơi với cùng cấu trúc. Ví dụ mã đơn hàng `ORD-` cộng bốn chữ số ASCII:

```java
import java.util.Objects;
import java.util.regex.Pattern;

record OrderCode(String value) {
    private static final Pattern FORMAT = Pattern.compile("ORD-[0-9]{4}");

    OrderCode {
        Objects.requireNonNull(value, "value");
        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid order code");
        }
    }
}
```

Đây là định nghĩa `record` Java 17 hợp lệ để đặt ở cấp top-level không `public` hoặc lồng trong lớp. Sau khi tạo thành công, đối tượng `OrderCode` đại diện cho giá trị đã được kiểm tra **theo mẫu quy định**. Những API cần mã đơn hàng có thể nhận `OrderCode` thay vì `String` không rõ ý nghĩa. Lưu ý không dùng mã hợp lệ về mặt cú pháp làm bằng chứng rằng đơn hàng thực sự tồn tại.

Không cần tạo một lớp mới cho mọi chuỗi thông thường. Các trường tên hiển thị, nội dung ghi chú, tiêu đề bài viết có thể vẫn là `String` nếu hợp đồng đủ rõ. Value object đem lại lợi ích lớn hơn khi một chuỗi có ngữ pháp/ràng buộc lặp lại ở nhiều API hoặc dễ bị nhầm với loại chuỗi khác.

## 9. Ví dụ Java 17+ chạy hoàn chỉnh

Ví dụ tổng hợp cách:

- giữ văn bản hiển thị đúng như đầu vào;
- xác thực toàn bộ chuỗi mã bằng ngữ pháp quy định;
- tìm literal chứa dấu chấm mà không coi nó là regex;
- mã hóa **giá trị query form**;
- tách bằng một delimiter literal có ý nghĩa đặc biệt trong regex.

Tạo file **`TextVsSyntaxDemo.java`**:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.regex.Pattern;

public class TextVsSyntaxDemo {

    private static final Pattern ORDER_CODE =
            Pattern.compile("ORD-[0-9]{4}");

    public static void main(String[] args) {
        String display = "  Mon an #42  ";
        System.out.println("Display: [" + display + "]");

        System.out.println(
                "Valid code: " + ORDER_CODE.matcher("ORD-0042").matches()
        );
        System.out.println(
                "Invalid code: " + ORDER_CODE.matcher("ORD-42 extra").matches()
        );

        String literal = "a.b";
        Pattern literalPattern = Pattern.compile(Pattern.quote(literal));

        System.out.println(
                "Literal found: "
                        + literalPattern.matcher("read a.b now").find()
        );
        System.out.println(
                "Not a regex wildcard: "
                        + literalPattern.matcher("read axb now").find()
        );

        String parameterValue = "An & Binh";
        String formEncoded = URLEncoder.encode(
                parameterValue,
                StandardCharsets.UTF_8
        );
        System.out.println("Query component: name=" + formEncoded);

        String[] parts = "A|B|C".split(Pattern.quote("|"), -1);
        System.out.println("Parts: " + Arrays.toString(parts));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TextVsSyntaxDemo.java
java TextVsSyntaxDemo
```

Đầu ra:

```text
Display: [  Mon an #42  ]
Valid code: true
Invalid code: false
Literal found: true
Not a regex wildcard: false
Query component: name=An+%26+Binh
Parts: [A, B, C]
```

Giải thích kết quả:

- `display` được in nguyên vẹn, gồm hai dấu cách ở hai đầu. Giá trị là nội dung dành cho hiển thị nên không tự cắt hoặc parse thành ngữ pháp khác.
- `matches()` chấp nhận mã `ORD-0042` và từ chối `ORD-42 extra`, bởi regex bắt buộc toàn bộ mã có tiền tố và đúng bốn chữ số.
- `Pattern.quote("a.b")` khiến dấu chấm được tìm đúng như ký tự thật; nó không tùy ý khớp chữ `x`.
- `URLEncoder` xử lý dấu cách và `&` theo form encoding của giá trị tham số.
- `Pattern.quote("|")` giúp `split` hiểu `|` là dấu phân cách nguyên văn, không phải toán tử regex.

## 10. Bảng quyết định khi thiết kế một tham số `String`

| Câu hỏi cần hỏi | Nếu câu trả lời là… | Hướng thiết kế |
| --- | --- | --- |
| Giá trị có được hiển thị nguyên văn không? | Tên, mô tả, bình luận | Bảo toàn nội dung, xác định chính sách whitespace/Unicode riêng; escape khi xuất ra định dạng khác |
| Giá trị có một mẫu hợp lệ rõ ràng không? | Mã đơn, định danh phiên bản | Validate toàn bộ, báo lỗi rõ; cân nhắc value object |
| Giá trị là cú pháp do người dùng chủ động nhập không? | Regex, filter expression | Công bố ngữ pháp, parse/catch lỗi; phân biệt với tìm kiếm literal |
| Giá trị mang cấu trúc nhiều trường không? | JSON, CSV | Dùng parser/serializer phù hợp; không split hoặc nối tay |
| Giá trị được đặt vào một văn bản có cú pháp khác không? | URL, SQL, HTML, shell | Dùng encoding, parameterization hoặc API dựng cấu trúc đúng theo ngữ cảnh |
| Giá trị được so sánh trong collection không? | Key của map/set | Quyết định có chuẩn hóa hay giữ nguyên; kiểm tra collisions |
| Giá trị qua nhiều tầng API không? | HTTP input → service → repository | Tách ranh giới parse/validate ở tầng thích hợp, ưu tiên truyền kiểu đã kiểm chứng vào nội bộ |

Cần nhớ rằng **validation, escaping và authorization là ba việc độc lập**. Chuỗi đúng cú pháp vẫn có thể đề cập đến tài nguyên mà người dùng không có quyền truy cập; một giá trị đã được HTML-escape vẫn có thể vi phạm quy tắc dữ liệu; và giá trị hợp lệ trong JSON không có nghĩa sẽ an toàn nếu sau đó đưa nguyên văn vào câu SQL.

## 11. Lỗi thường gặp

1. **Xem mọi `String` là plain text.** Truyền văn bản người dùng vào `Pattern.compile`, SQL hay biểu thức template khiến các dấu có nghĩa điều khiển.
2. **Xem mọi dấu câu là cấu trúc.** Tự tách dấu phẩy, dấu chấm hoặc ký tự `&` trong tên/nhận xét dù chúng chỉ là văn bản hiển thị.
3. **Dùng `split` thay parser chuẩn.** JSON/CSV/URL có quy tắc quoting, escaping, nesting hoặc encoding; tách chuỗi đơn giản làm hỏng dữ liệu hợp lệ.
4. **Dùng `matches()` và `find()` lẫn lộn.** Mã định danh cần hợp lệ toàn bộ; tìm một đoạn nội dung thì cần semantics khác.
5. **Dùng một dạng escaping cho nhiều ngữ cảnh.** SQL parameter, JSON escaping, URL encoding và HTML escaping giải quyết các ngữ pháp khác nhau.
6. **Đổi nội dung hiển thị khi tạo khóa.** Việc chuẩn hóa để so khớp có thể cần thiết, nhưng nên giữ văn bản gốc nếu người dùng cần xem lại đúng chuỗi đã nhập.
7. **Cho rằng parse thành công đồng nghĩa hợp lệ hoàn toàn.** URI đúng cú pháp chưa chắc có scheme/host hợp lệ cho nghiệp vụ; mã đơn hàng đúng mẫu chưa chắc tồn tại.
8. **Xây API nhận `String` mà không ghi hợp đồng.** Người gọi không biết nên gửi văn bản nguyên dạng, mã đã chuẩn hóa, JSON raw hay đối tượng đã parse.

## 12. Tự kiểm tra

**Câu 1.** API tìm kiếm cho người dùng nhập `"a.b"` và muốn tìm chính xác ba ký tự `a`, `.`, `b`. Có nên gọi `Pattern.compile(userInput)` không?

**Đáp án:** Không. Đây là tìm kiếm literal; có thể dùng `String.contains(userInput)` hoặc `Pattern.compile(Pattern.quote(userInput))` nếu cần regex API.

**Câu 2.** Vì sao `"A,B"` không đủ để xác định nó có hai cột CSV?

**Đáp án:** Một chuỗi văn bản có dấu phẩy có thể chỉ là nội dung thông thường. Đối với CSV, số cột còn phụ thuộc quy tắc quoting, delimiter và cú pháp toàn bản ghi. Chỉ parser CSV mới xác định đúng cấu trúc theo dialect được chọn.

**Câu 3.** `ORD-0042` khớp regex yêu cầu. Điều đó chứng minh gì?

**Đáp án:** Chỉ chứng minh chuỗi thỏa mẫu cú pháp. Nó chưa chứng minh có đơn hàng tương ứng, giá trị là duy nhất hoặc người gọi có quyền truy cập.

**Câu 4.** Nếu một tên người dùng chứa `&`, có thể đặt trực tiếp vào query URL bằng cách nối chuỗi không?

**Đáp án:** Không nên. Khi đặt làm giá trị tham số, phải dùng cơ chế mã hóa đúng thành phần, ví dụ form encoding trong ngữ cảnh tương ứng; dấu `&` phải được bảo toàn như dữ liệu thay vì bị diễn giải làm dấu ngăn tham số.

## Ghi nhớ

**`String` là nơi chứa ký tự; hợp đồng API mới quyết định ký tự đó là nội dung hay cú pháp.** Với plain text, bảo toàn nội dung và xử lý đúng khi xuất. Với structured text, xác định ngữ pháp, parse/validate bằng công cụ chuyên dụng và chuyển sang kiểu dữ liệu phù hợp khi có thể. Khi dữ liệu đi vào SQL, URL, JSON, HTML, regex hay shell, phải giữ ranh giới giữa **dữ liệu** và **cú pháp điều khiển** bằng API đúng ngữ cảnh.
