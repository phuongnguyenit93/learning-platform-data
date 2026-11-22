# Giữ trách nhiệm mã hóa và escape tại đúng ranh giới trong thiết kế API Java String

## 1. Vấn đề cốt lõi

Cùng một **String** có thể đi qua nhiều hệ thống: request HTTP, service Java, cơ sở dữ liệu, JSON, HTML, URL, log hay lệnh hệ điều hành. Giá trị nghiệp vụ có thể giống nhau ở mọi nơi, nhưng **cách biểu diễn an toàn và hợp lệ** tại từng ranh giới lại khác nhau.

Ví dụ người dùng nhập:

~~~text
Cà phê & trà "đặc biệt"
~~~

Các thành phần có những quy tắc riêng:

- Trên đường truyền dạng byte, ta cần biết **charset**, ví dụ UTF-8, để biến các ký tự thành byte và giải mã lại.
- Trong nội dung JSON, dấu nháy kép và ký tự điều khiển cần được **JSON serializer** thể hiện theo cú pháp JSON.
- Trong phần văn bản HTML, **&** và **<** cần được **HTML text encoder** xử lý theo quy tắc của HTML.
- Trong giá trị một tham số truy vấn URL, dấu cách, **&**, **+** và các ký tự dành riêng cần được **component encoder** mã hóa theo đúng loại thành phần URL.
- Trong câu lệnh SQL, giá trị dữ liệu nên đi qua **tham số truy vấn**, không nối chuỗi để tự escape SQL.

**Không tồn tại một hàm escape chung an toàn cho mọi đích đến.** Lỗi thường gặp là escape quá sớm trong tầng nghiệp vụ, để một tầng khác escape thêm lần nữa, hoặc dùng phép escape dành cho ngữ cảnh này tại ngữ cảnh khác.

Mục tiêu của bài: xác định **ai chịu trách nhiệm chuyển đổi**, **chuyển đổi tại ranh giới nào**, **giữ dạng dữ liệu gì trong API**, và **làm sao tránh mã hóa hai lần** mà không làm mất nội dung gốc.

## 2. Phân biệt bốn khái niệm thường bị trộn lẫn

| Khái niệm | Câu hỏi cần trả lời | Ví dụ Java và ứng dụng |
| --- | --- | --- |
| **Charset encoding/decoding** | Ký tự được chuyển sang byte và ngược lại bằng charset nào? | **getBytes(StandardCharsets.UTF_8)**, **new String(bytes, UTF_8)** |
| **Escaping theo cú pháp/ngữ cảnh** | Những ký tự nào phải được thể hiện khác khi nhúng vào ngôn ngữ đích? | JSON string escaping, HTML text/attribute escaping, Java string literal |
| **Percent/form encoding của URL** | Dữ liệu chiếm vị trí nào trong URL và cần biểu diễn ký tự ra sao? | **URLEncoder.encode(value, UTF_8)** cho dữ liệu form |
| **Ràng buộc tham số hoặc API có cấu trúc** | Có thể chuyển dữ liệu riêng khỏi phần cú pháp để khỏi ghép chuỗi hay không? | JDBC **PreparedStatement.setString(...)**, serializer JSON, HTML template engine |

Cụ thể:

- **Encoding** có nhiều nghĩa tùy ngữ cảnh. “UTF-8 encoding” chuyển ký tự sang byte; “URL encoding” thường ám chỉ percent-encoding. Hai thao tác này không thể hoán đổi.
- **Escaping** là biểu diễn ký tự theo quy tắc của cú pháp đích. Ví dụ Java source code viết **"A\nB"** để chứa ký tự xuống dòng trong một String, còn JSON serializer phải xuất một JSON string token với dấu nháy và escape phù hợp.
- **Base64** là cách biểu diễn byte bằng bảng chữ cái ASCII, hữu ích cho vận chuyển dữ liệu nhị phân trong một số giao thức. **Base64 không phải cơ chế escape an toàn cho HTML/SQL/URL**, cũng không tự mã hóa bảo mật dữ liệu.
- **Validation** kiểm tra giá trị có hợp lệ theo nghiệp vụ hay không. **Escaping/parameter binding** bảo đảm dữ liệu không trở thành cú pháp của ngôn ngữ đích. Hai trách nhiệm này bổ sung cho nhau, không thay thế nhau.

Ví dụ một tên hiển thị có dấu **<** có thể được cho phép theo nghiệp vụ nhưng vẫn phải được HTML-escape khi chèn vào **HTML text context**. Không cần biến giá trị nghiệp vụ thành chuỗi escape từ lúc nhận vào.

## 3. Nguyên tắc: giữ dữ liệu ngữ nghĩa, chuyển đổi khi đi qua ranh giới

Một thiết kế dễ kiểm soát:

~~~text
HTTP input (byte + quy tắc protocol)
        |
        v
HTTP framework giải mã đúng lần vào String
        |
        v
Controller -> Service -> Domain: String nguyên nghĩa
        |
        +--> JDBC parameter binding -> Database
        |
        +--> JSON serializer -> HTTP application/json
        |
        +--> HTML template engine -> HTML text/attribute
        |
        +--> URL component encoder -> giá trị query/path tương ứng
        |
        +--> Logger với chính sách hiển thị/ghi log riêng
~~~

**“Nguyên nghĩa”** không có nghĩa là bỏ mọi validation hoặc giữ nguyên byte thô. Nó có nghĩa String trong service đại diện cho giá trị của người dùng, ví dụ **Cà phê & trà**, thay vì mã escape phục vụ một output chưa được chọn.

Trách nhiệm thường chia như sau:

1. **Input adapter** biết charset/protocol và giải mã input thành giá trị Java; kiểm tra giới hạn kích thước, hình thức dữ liệu và hợp đồng API.
2. **Service/domain** xử lý ý nghĩa của giá trị. Đừng gắn HTML entities hoặc percent-encoded query component vào thuộc tính domain chỉ để “an toàn chung”.
3. **Output adapter/serializer** biết ngữ cảnh đích và thực hiện escape/encode tương ứng tại thời điểm xuất.
4. **Database adapter** dùng tham số truy vấn, không dựa vào dữ liệu đã được escape thủ công.
5. **Giao diện API và tài liệu hợp đồng** phải nói rõ khi nào tham số là giá trị thô, khi nào là một chuỗi đã mã hóa theo chuẩn xác định.

Đây là **quy tắc thiết kế mặc định**, không phải cấm tuyệt đối mọi kiểu dữ liệu đã mã hóa. Một hệ thống có thể cố ý lưu **HTML sanitized** hoặc nội dung đã ở dạng **JSON document**; khi đó cần mô hình/kiểu API riêng, chính sách rõ ràng và không nhầm nó với văn bản thông thường.

## 4. Java String khác byte: charset là trách nhiệm của ranh giới I/O

Một **String** Java biểu diễn nội dung ký tự bằng UTF-16 theo API của Java; không nên gọi nó là “String được UTF-8 hóa”. UTF-8 là cách biểu diễn khi chuyển nội dung ký tự sang byte.

~~~java
import java.nio.charset.StandardCharsets;

String value = "Cà phê";
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);

System.out.println(restored.equals(value)); // true
~~~

Đây là một vòng đi và về **giữa String và byte** qua UTF-8. Nếu lúc mã hóa dùng UTF-8 nhưng lúc giải mã dùng charset không tương ứng, các ký tự có dấu có thể bị lỗi (mojibake).

**Quy tắc thực hành:**

- Khi API nhận hoặc trả **byte[]**, chỉ rõ charset tại ranh giới chuyển từ/đến String.
- Khi xử lý file text, dùng API có đối số charset, như **Files.readString(path, StandardCharsets.UTF_8)** và **Files.writeString(path, text, StandardCharsets.UTF_8)** khi hợp đồng yêu cầu UTF-8.
- Với request/response HTTP, cấu hình và tuân theo Content-Type/charset cùng quy tắc framework; tránh giải mã một giá trị đã được framework giải mã.
- Không gọi **new String(bytes)** hoặc **getBytes()** không đối số nếu tính đúng đắn của giao tiếp yêu cầu charset cụ thể.
- Không giả định độ dài **String.length()** bằng số byte UTF-8 hoặc số code point Unicode. Java String tính theo đơn vị UTF-16.

**Tách biệt:** chuyển sang UTF-8 **không** làm cho nội dung phù hợp để chèn thẳng vào HTML, JSON string, SQL hay URL. Đây là các ranh giới tiếp theo với ngữ pháp riêng.

## 5. Mã hóa URL: chỉ mã hóa thành phần dữ liệu đúng vị trí

URL có nhiều thành phần: scheme, host, path, query, fragment. Cùng một ký tự có thể có ý nghĩa khác nhau trong từng thành phần. Ví dụ dấu **/** thường phân tách path segments; dấu **&** phân tách các cặp query parameters trong một số quy ước; dấu **+** có ý nghĩa đặc biệt khi xử lý **application/x-www-form-urlencoded**.

Trong Java:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String keyword = "cà phê & trà";
String encoded = URLEncoder.encode(keyword, StandardCharsets.UTF_8);

String url = "https://example.org/search?q=" + encoded;
~~~

**URLEncoder** được thiết kế cho quy tắc mã hóa **application/x-www-form-urlencoded**, thường dùng với **giá trị form/query parameter**. Nó thể hiện khoảng trắng dưới dạng **+**. Vì vậy, **không dùng URLEncoder để mã hóa toàn bộ URL**, URL path hoặc cả chuỗi query đã ghép sẵn.

Ví dụ trên, chỉ **keyword** là giá trị dữ liệu cần mã hóa. Các ký tự cấu trúc của URL, như **?**, **=**, dấu **&** giữa nhiều tham số, phải được tạo ra bởi bộ xây dựng URL hoặc code có hợp đồng rõ.

### 5.1. Giá trị query khác cả đường dẫn

~~~text
Đúng ý định:
  https://example.org/search?q=<giá trị q đã form-encode>

Sai ý định:
  form-encode toàn bộ "https://example.org/search?q=..." rồi coi đó là URL
~~~

Đối với **path segment**, không đánh đồng dấu cách cần percent-encoding với dấu **+** theo form encoding. Nên dùng URI/URL builder của framework hoặc thư viện HTTP với phương thức **encode path segment** rõ ràng. Một hàm cho “mọi URL” dễ làm thay đổi dấu phân cách và semantics.

Lưu ý: percent-encoding thể hiện dữ liệu cho URL, **không tự ngăn path traversal** hoặc cấp quyền truy cập. Đường dẫn tệp/tài nguyên vẫn phải được xác thực, chuẩn hóa và kiểm tra phạm vi được phép ở nơi sử dụng.

### 5.2. Mã hóa hai lần và giải mã hai lần

Một lỗi thường gặp:

~~~java
String raw = "A&B";
String once = URLEncoder.encode(raw, StandardCharsets.UTF_8);
String twice = URLEncoder.encode(once, StandardCharsets.UTF_8);

System.out.println(once);  // A%26B
System.out.println(twice); // A%2526B
~~~

Trong **twice**, dấu **%** của dữ liệu đã percent-encode trước đó bị mã hóa thành **%25**. Nếu bên nhận giải mã một lần, giá trị còn **A%26B** thay vì **A&B**.

Giải pháp thiết kế:

- Phương thức nhận **rawQueryValue** và **chính nó** chịu trách nhiệm encode đúng một lần.
- Hoặc phương thức nhận **encodedQueryComponent** với hợp đồng rõ và **không encode lại**. Tránh để cùng một tham số String mơ hồ có thể thuộc cả hai trạng thái.
- Không tự động decode mọi chuỗi có **%**. Chuỗi **"50% off"** có dấu phần trăm hợp lệ như dữ liệu thông thường.
- Không decode lặp để “đạt dạng dễ đọc” vì có thể thay đổi ý nghĩa, phá validation và gây lỗi tại các tầng khác.

## 6. JSON: giao cho serializer thay vì nối chuỗi thủ công

Một JSON string là token có cú pháp riêng. Dữ liệu chứa dấu nháy kép, backslash, newline hoặc ký tự điều khiển phải được serializer thể hiện hợp lệ.

**Không nên ghép thủ công:**

~~~java
// KHÔNG AN TOÀN/CHÍNH XÁC khi userName chứa quote hoặc xuống dòng:
String json = "{\"name\":\"" + userName + "\"}";
~~~

Giả sử **userName** là **A" B**, việc nối trực tiếp có thể phá JSON string. Cách giải quyết không phải viết một danh sách thay thế ký tự đơn giản rồi dùng cho mọi trường hợp; hãy dùng serializer JSON của môi trường ứng dụng, ví dụ Jackson trong dự án có dependency tương ứng.

Ví dụ **đoạn minh họa cần thư viện Jackson** (không phải chương trình Java SE chạy độc lập):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

record Profile(String displayName) {}

ObjectMapper mapper = new ObjectMapper();
Profile value = new Profile("A\"B\nC");
String json = mapper.writeValueAsString(value);

// Serializer chịu trách nhiệm dấu nháy, backslash và newline trong JSON.
~~~

Khi đọc JSON, **JSON parser** biến JSON string token trở về giá trị Java tương ứng. Service nên làm việc với **displayName** dạng String theo ngữ nghĩa, không cần tự thêm backslash escape để lưu dữ liệu thông thường.

**Phân biệt source literal với dữ liệu runtime:**

- Trong **Java source code**, **"A\nB"** là cú pháp diễn tả một String có ký tự LF.
- Trong **JSON text**, dấu xuống dòng trong một chuỗi JSON phải được thể hiện theo cú pháp JSON, ví dụ chuỗi ký tự **\n** trong JSON wire text.
- Đừng tự lấy chuỗi source của Java và cho rằng nó đã trở thành JSON hợp lệ.

Khi dữ liệu JSON được nhúng vào **HTML**, ranh giới HTML/script có thêm quy tắc riêng. Một JSON serializer đơn thuần không phải bảo đảm toàn bộ việc nhúng nội dung vào **<script>** an toàn. Thiết kế tốt là trả JSON qua response **application/json** và để frontend parse; nếu thật sự cần nhúng vào HTML, phải dùng giải pháp escape đúng ngữ cảnh nhúng đó.

## 7. HTML: escape theo context, không có một “HTML escape” dùng mọi nơi

HTML có nhiều context: **text node**, **attribute**, **URL attribute**, JavaScript trong script, CSS trong style. Các quy tắc escape và rủi ro khác nhau.

Ví dụ dữ liệu nghiệp vụ:

~~~text
A&B <Admin>
~~~

Nếu đưa vào **HTML text node**, các ký tự mang ý nghĩa cú pháp như **&**, **<** cần được thể hiện an toàn để người dùng nhìn thấy đúng dữ liệu mà nội dung không trở thành thẻ HTML.

Nguyên tắc:

1. Khi tạo HTML, dùng **template engine có auto-escaping phù hợp với vị trí chèn** hoặc API DOM với thao tác **textContent** khi chèn văn bản.
2. Với **HTML attribute**, dùng cơ chế escape dành riêng cho attribute; không lấy hàm chỉ dành cho HTML text rồi mặc định dùng an toàn trong mọi trường hợp.
3. Với **href/src**, ngoài escape HTML attribute, còn cần **kiểm soát URL scheme và nguồn đích**. Escape dấu nháy không vô hiệu hóa một URL có scheme nguy hiểm.
4. Với **JavaScript/CSS context**, tránh nhúng chuỗi động trực tiếp; sử dụng cách truyền dữ liệu riêng hoặc encoder dành cho context chính xác.
5. Nếu mục tiêu là **cho phép nội dung HTML có giới hạn**, cần quy trình **sanitization** theo allowlist và policy rõ ràng. Escaping toàn bộ thì hiển thị markup như văn bản; sanitization có mục tiêu khác.

**Phòng XSS bằng output encoding là trách nhiệm của nơi render.** Một service Java không nên biến mọi tên người dùng thành chuỗi chứa HTML entities rồi dùng chuỗi ấy cho email, JSON, SQL và log.

### 7.1. Double escaping trong HTML

Nếu tầng service đã thay **&** bằng **&amp;**, rồi template engine escape tiếp dấu **&**, người dùng có thể nhìn thấy chữ **&amp;** thay vì dấu **&**.

Đó không phải lỗi “thiếu unescape ở frontend”; lỗi thiết kế là **hai tầng cùng cho rằng mình sở hữu trách nhiệm escape**.

Nên giữ mô hình:

~~~text
Domain String:       "A&B"
Template nhận:       "A&B"
HTML renderer xuất:  "A&amp;B"
Trình duyệt hiển thị: A&B
~~~

Nếu phải lưu rich HTML an toàn, hãy mô hình hóa nó khác với String văn bản thường, và khai báo rõ renderer có được xuất như markup hay phải escape như text.

## 8. SQL: dùng parameter binding, không tự escape giá trị

Các toán tử và cú pháp SQL cần được giữ tách biệt khỏi dữ liệu do người dùng nhập. **Không** xây query bằng nối chuỗi:

~~~java
// Ví dụ không nên dùng:
String sql = "SELECT id FROM users WHERE email = '" + email + "'";
~~~

Đây là rủi ro SQL injection và lỗi xử lý dấu nháy. Cách đúng là dùng tham số JDBC:

~~~java
// Đoạn minh họa: giả định có java.sql.Connection connection.
String sql = "SELECT id FROM users WHERE email = ?";

try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (java.sql.ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            // Xử lý bản ghi theo nghiệp vụ.
        }
    }
}
~~~

**PreparedStatement.setString(...)** truyền giá trị như dữ liệu, không để dấu nháy trong **email** trở thành cú pháp SQL. Nó cũng giúp không phải viết cách escape thủ công phụ thuộc database.

Cần nhớ:

- Tham số có thể thay **giá trị dữ liệu**, không thay tên bảng, cột hoặc từ khóa SQL. Nếu tên cột cần chọn động, dùng **allowlist identifier** và dựng cú pháp từ các lựa chọn tin cậy.
- Điều kiện **LIKE** còn có ký tự pattern của SQL như **%** và **_**. Parameter binding ngăn injection qua cú pháp SQL nhưng **không tự biến chúng thành ký tự literal trong LIKE pattern**; nếu muốn tìm dấu **%** thật, cần quy tắc escape LIKE và cú pháp **ESCAPE** thích hợp với database.
- Dữ liệu trước khi gửi database vẫn có thể chứa **<**, **&** hoặc dấu nháy. Đừng HTML-escape để “chống SQL injection”; đây là hai ranh giới khác nhau.

Một cột chứa tên người dùng nên lưu **tên người dùng theo ngữ nghĩa**. Khi ứng dụng đọc nó và đưa vào trang HTML, lúc đó renderer HTML chịu trách nhiệm HTML-escape.

## 9. Regex, shell, CSV và log có ranh giới riêng

Khi nhập **từ khóa để tìm nguyên văn**, \`Pattern.compile(input)\` có thể biến dấu \`.\` hoặc \`*\` thành toán tử regex. Nếu vẫn dùng regex API, quote đúng phần dữ liệu:

~~~java
String literalText = "a.b";
java.util.regex.Pattern pattern =
        java.util.regex.Pattern.compile(
                java.util.regex.Pattern.quote(literalText));
System.out.println(pattern.matcher("x a.b y").find()); // true
System.out.println(pattern.matcher("x acb y").find()); // false
~~~

Khi gọi tiến trình, truyền executable và các đối số riêng qua \`ProcessBuilder\`, kiểm soát argument được công cụ đích hiểu là option; tránh đưa input vào shell script ghép chuỗi. Khi ghi CSV, dùng CSV writer với quoting/escape đúng dialect, và xem xét **formula injection** nếu tệp sẽ mở trong spreadsheet. Khi ghi log, để logging sink quyết định escape cho cấu trúc log và kiểm soát CR/LF, ký tự điều khiển, dữ liệu nhạy cảm; parameterized log message không mặc nhiên loại mọi ký tự gây log injection.

Điểm chung: \`Pattern.quote\` chỉ phục vụ regex, CSV writer chỉ phục vụ CSV, logging formatter chỉ phục vụ log. Những phép chuyển đổi đó **không** phải giá trị để ghi ngược vào domain \`String\` và tái sử dụng ở một đích khác. Phần giải thích cú pháp chi tiết và ví dụ parser/serializer nằm tại hai bài về text có ngữ pháp và xử lý định dạng.

## 10. Ví dụ Java 17+ độc lập: đúng ranh giới, tránh mã hóa hai lần

Tạo tệp **EncodingBoundaryDemo.java**:

~~~java
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.regex.Pattern;

public class EncodingBoundaryDemo {
    public static void main(String[] args) {
        String raw = "cà phê & trà";

        byte[] utf8 = raw.getBytes(StandardCharsets.UTF_8);
        String restored = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("UTF-8 round trip: " + restored.equals(raw));

        String formValue = URLEncoder.encode(raw, StandardCharsets.UTF_8);
        System.out.println("Form value: " + formValue);
        System.out.println("Form round trip: "
                + URLDecoder.decode(formValue, StandardCharsets.UTF_8).equals(raw));

        String twice = URLEncoder.encode(formValue, StandardCharsets.UTF_8);
        System.out.println("Double encoding contains %25: "
                + twice.contains("%25"));

        String base64 = Base64.getEncoder().encodeToString(utf8);
        byte[] decodedBytes = Base64.getDecoder().decode(base64);
        System.out.println("Base64 round trip: "
                + new String(decodedBytes, StandardCharsets.UTF_8).equals(raw));

        String keyword = "a.b";
        Pattern literal = Pattern.compile(Pattern.quote(keyword));
        System.out.println("Regex literal matches dot: "
                + literal.matcher("x a.b y").find());
        System.out.println("Regex literal rejects wildcard match: "
                + !literal.matcher("x acb y").find());
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac EncodingBoundaryDemo.java
java EncodingBoundaryDemo
~~~

Kết quả:

~~~text
UTF-8 round trip: true
Form value: c%C3%A0+ph%C3%AA+%26+tr%C3%A0
Form round trip: true
Double encoding contains %25: true
Base64 round trip: true
Regex literal matches dot: true
Regex literal rejects wildcard match: true
~~~

Giải thích:

1. **UTF-8** xử lý String thành byte và ngược lại. Nó không tự escape cho HTML/SQL.
2. **URLEncoder** đổi giá trị của một form/query parameter; dấu cách trở thành **+**, dấu **&** trong giá trị thành **%26**.
3. **URLDecoder** nhận đầu vào đúng loại **form-encoded value**, giải mã trở về String theo ngữ nghĩa.
4. Encode lại **formValue** làm percent sign trong các chuỗi **%XX** thành **%25**: đây là dấu hiệu của tình huống mã hóa hai lần, không phải lớp bảo vệ bổ sung.
5. **Base64** xử lý byte thành văn bản ASCII và giải mã lại. Nó không phải phép escape HTML/SQL.
6. **Pattern.quote** bảo toàn ý nghĩa literal của dấu chấm trong regex.

**Chỉ đưa String đã encode vào đúng vị trí và đúng giao thức mà nó được tạo ra cho.** Không gán **formValue** vào domain field tên **displayName** và sau đó đem field đó lưu database hoặc trả JSON như tên người dùng.

## 11. Một thiết kế API dễ mắc lỗi và cách sửa

### 11.1. Thiết kế dễ double escaping

~~~java
// Tình huống xấu mang tính minh họa:
String saveDisplayName(String submittedName) {
    return submittedName.replace("&", "&amp;");
}
~~~

Nếu kết quả được lưu như tên hiển thị, trang HTML có thể escape lần nữa; JSON API có thể trả tên đã biến dạng thành **&amp;**; tìm kiếm tên người dùng cũng không còn so sánh trên dữ liệu nguyên nghĩa.

### 11.2. Thiết kế rõ trách nhiệm hơn

Giữ giá trị gốc trong API nghiệp vụ:

~~~java
record UserProfile(String displayName) {}

UserProfile profile = new UserProfile("A&B");
~~~

Khi xuất dữ liệu:

- HTTP JSON response: **JSON serializer** đọc **profile.displayName()** và tạo JSON text hợp lệ.
- HTML view: **template engine** đặt giá trị vào text/attribute context với output encoding phù hợp.
- Query đến dịch vụ khác: **HTTP client/URI builder** mã hóa giá trị trong thành phần URL chính xác.
- JDBC: **PreparedStatement.setString(...)** truyền chuỗi dạng dữ liệu.
- Logging: **logger** serialize/format theo sink, có quy tắc chống log injection và lộ thông tin riêng.

**Không phải tạo một biến tên escapedDisplayName dùng chung cho tất cả đích xuất.**

Nếu API thật sự nhận hoặc trả văn bản đã encode, hãy diễn tả điều đó trong tên và hợp đồng, ví dụ **rawQueryValue** khác **encodedFormComponent**, kèm quy định charset/dialect. Với dự án lớn có thể dùng các value object/wrapper type riêng để tránh trộn trạng thái.

## 12. Không giải mã quá mức ở input

Nguyên tắc “escape ở output” không đồng nghĩa “decode mọi thứ nhiều lần khi input”.

Hãy phân biệt:

- HTTP framework thường đã decode query parameter theo protocol. Controller nhận **String parameter** và không cần **URLDecoder.decode(...)** lần nữa.
- JSON parser đã giải mã escape trong JSON string. Service nhận giá trị String đã parse và không cần tự **unescape JSON**.
- HTML entities trong một chuỗi người dùng có thể là **văn bản họ muốn nhập**. Không tự chuyển **&amp;** thành **&** chỉ vì nhìn giống HTML entity.
- Nếu một endpoint **cố ý** nhận toàn bộ form-encoded payload ở dạng raw, adapter xử lý việc parse/decode **đúng một lần** theo Content-Type và charset đã định nghĩa.

Giải mã nhiều lần có thể phá validation hoặc tạo ra ký tự phân cách mới chỉ sau vòng decode thứ hai. Vì vậy, **hợp đồng API phải xác định trạng thái dữ liệu tại mỗi bước** và không dùng “thử decode đến khi hết ký tự đặc biệt”.

Một ví dụ kiểm soát:

~~~text
Raw HTTP request: q=A%26B
Framework parse query: parameter q = "A&B"
Service nhận: "A&B"
Service KHÔNG tự URLDecode(q) nữa
~~~

Nếu dữ liệu thực sự chứa dấu phần trăm, nó vẫn là dữ liệu hợp lệ. Việc kiểm tra hợp lệ phải dựa trên giá trị theo hợp đồng của API, không dựa trên phỏng đoán rằng mọi ký hiệu percent luôn là escape.

## 13. Validation, canonicalization và bảo vệ ranh giới

Mã hóa/escape đúng context **không thể thay thế** các kiểm tra khác:

- **Giới hạn độ dài và kiểu dữ liệu:** kiểm tra trước khi xử lý để tránh input không hợp lệ và sử dụng tài nguyên quá mức.
- **Unicode normalization:** đôi khi cần NFC/NFKC để so sánh danh tính/tìm kiếm nhất quán, nhưng phải có chính sách nghiệp vụ; normalization không phải một loại HTML escape.
- **Authorization:** URL encoding không làm một đường dẫn hoặc ID trở thành tài nguyên người dùng có quyền truy cập.
- **Path validation:** chuẩn hóa và kiểm tra đường dẫn trong thư mục gốc, xem xét symbolic link/race condition; percent-encoding không thay thế các kiểm tra này.
- **HTML sanitization:** cần khi cho phép một phần markup từ bên ngoài; HTML escaping toàn bộ sẽ hiển thị markup thành văn bản.
- **SQL parameterization:** dùng cho giá trị; tên bảng/cột động cần allowlist.
- **Content-Type:** đặt đúng media type để bên nhận biết bộ parser và quy tắc encode/decode.

Trình tự kiểm soát có thể là: **parse đúng giao thức → xây dữ liệu có kiểu → validate ý nghĩa và quyền truy cập → xử lý nghiệp vụ → serialize/encode đúng output context**. Đừng gộp các thao tác này thành một hàm mang tên chung **sanitizeString** rồi gọi ở mọi tầng.

## 14. Thiết kế test theo ranh giới

Để kiểm tra hệ thống thực sự phân công trách nhiệm đúng, hãy thử những String chứa các ký tự “khó”:

~~~text
A&B
A<B
A"B
A'B
a+b
a%2Bb
Dòng 1
Dòng 2
cà phê
中文
😀
~~~

Những test có giá trị:

1. **UTF-8 round-trip:** một String Unicode bất kỳ chuyển sang byte rồi về String vẫn bằng đầu vào.
2. **Form encoding round-trip:** giá trị chứa **&**, **+**, dấu cách, dấu **%** được encode/decode **đúng một lần** tại đúng parser.
3. **JSON round-trip:** serialize rồi parse lại cho ra cùng giá trị String, kể cả dấu nháy kép, backslash và newline.
4. **HTML rendering:** giá trị chứa **<** được hiển thị như text, không tạo phần tử HTML ngoài ý định; attribute và URL được kiểm tra theo context riêng.
5. **SQL parameter binding:** giá trị chứa dấu nháy đơn vẫn được lưu/tìm như dữ liệu và không thay đổi cấu trúc câu SQL.
6. **No-double-escape:** renderer nhận **A&B** từ service và hiển thị **A&B**; không hiển thị **&amp;**.
7. **Input framework:** endpoint không decode lần thứ hai một tham số mà framework đã parse.
8. **Cross-layer contract:** giá trị đọc từ database, trả qua JSON và render HTML vẫn giữ cùng **ý nghĩa**, dù byte representation và escape representation khác nhau.

Lưu ý: so sánh nội dung trên wire phải đối chiếu **đúng lớp**. Chuỗi JSON có thể chứa backslash escaping mà giá trị String sau parse không chứa backslash ấy. HTML source có thể chứa entities mà text hiển thị không chứa các chuỗi entity.

## 15. Lỗi thường gặp và cách khắc phục

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Lưu tên người dùng đã HTML-escape vào domain/database | Double escaping hoặc tên bị biến dạng ở JSON/email | Lưu giá trị String theo ngữ nghĩa; escape tại HTML view |
| Dùng **URLEncoder** cho cả URL | Các dấu phân cách cấu trúc bị mã hóa sai | Encode riêng query/form value hoặc path segment bằng builder phù hợp |
| Encode một query value hai lần | **%** đổi thành **%25**, kết quả hiển thị sai | Quy định rõ raw value và encoded component |
| Tự **URLDecoder** trên parameter đã được framework parse | Double decode, thay đổi ý nghĩa/validation | Để input adapter decode đúng một lần |
| Ghép dấu nháy vào JSON bằng nối String | JSON không hợp lệ hoặc dữ liệu sai | Dùng serializer JSON |
| Dùng HTML escape để chống SQL injection | Không xử lý rủi ro SQL | JDBC PreparedStatement/parameterized SQL |
| Tự replace dấu nháy đơn trong SQL | Dễ sai theo dialect/cấu hình | Bind tham số, allowlist identifier |
| Dùng JSON escape cho HTML text/attribute | Không bảo đảm an toàn ngữ cảnh HTML | HTML encoder/template engine đúng context |
| Coi Base64 là mã hóa bảo mật | Không tạo tính bí mật hay xác thực | Dùng cơ chế bảo mật riêng nếu cần |
| Coi Java **String.length()** là độ dài byte UTF-8 | Sai giới hạn kích thước truyền dẫn | Đo trên byte được encode đúng charset |
| Dùng **Pattern.compile(userInput)** khi cần tìm literal | Ký tự regex biến thành toán tử | Dùng **Pattern.quote(userInput)** |
| Dùng **escape()** chung cho mọi tầng | Không rõ context, dễ double-escape | API có tên/hợp đồng theo từng ranh giới |

## 16. Checklist áp dụng trong code review

- [ ] Dữ liệu ở tầng domain/service còn mang **giá trị theo ngữ nghĩa** hay đã bị mã hóa cho một output cụ thể?
- [ ] API input ghi rõ dữ liệu là raw String hay đã ở một encoding/format cụ thể?
- [ ] Charset tại ranh giới byte/String có được chỉ rõ và khớp hai đầu không?
- [ ] JSON và HTML có serializer/renderer chịu trách nhiệm phù hợp với **context** không?
- [ ] URL chỉ encode **component dữ liệu** cần thiết, không encode toàn chuỗi hoặc mã hóa trùng?
- [ ] SQL có dùng parameter binding? Identifier động có được giới hạn bằng allowlist?
- [ ] Các giá trị đã parse bởi framework có bị decode lặp lại không?
- [ ] Có test round-trip và test nội dung chứa **&**, **+**, **%**, dấu nháy, newline, Unicode không?
- [ ] Có kiểm tra validation, phân quyền và cấu trúc dữ liệu độc lập với output encoding không?
- [ ] Nếu buộc phải giữ chuỗi encoded, kiểu/tên biến/hợp đồng có làm trạng thái ấy rõ ràng không?

## 17. Ghi nhớ

**Một String không tự “an toàn” cho mọi đích.** Giá trị ở tầng nghiệp vụ nên giữ nguyên ý nghĩa; khi chuyển sang byte, HTML, JSON, URL, SQL, regex hoặc log, dùng **bộ chuyển đổi dành riêng cho đích đến** tại ranh giới thực sự:

- **Byte/String:** charset đã định, ví dụ UTF-8.
- **JSON:** serializer và parser JSON.
- **HTML:** encoder/template đúng text, attribute, URL hoặc context tương ứng.
- **URL:** encoder cho đúng query value/path segment; decode theo protocol một lần.
- **SQL:** parameter binding và kiểm soát identifier.
- **Regex:** **Pattern.quote** nếu dữ liệu là literal.
- **Log/CSV/shell:** API cấu trúc hoặc serializer phù hợp với format/command đích.

Cách làm này vừa giữ đúng dữ liệu vừa hạn chế **double encoding**, **double escaping**, lỗi cú pháp và rủi ro injection do trách nhiệm bị đặt sai chỗ.

### Tài liệu tham khảo

- Java SE 17, **java.lang.String** và **java.nio.charset.StandardCharsets**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, **java.net.URLEncoder**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html
- Java SE 17, **java.net.URLDecoder**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html
- Java SE 17, **java.sql.PreparedStatement**: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java SE 17, **java.util.regex.Pattern**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
- OWASP, **Cross Site Scripting Prevention Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP, **SQL Injection Prevention Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
