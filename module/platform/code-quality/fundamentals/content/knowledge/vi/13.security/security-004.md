# Tách dữ liệu khỏi câu lệnh hoặc cấu trúc thực thi

Một chuỗi do người dùng nhập có thể được dùng để tìm kiếm, đặt tên tệp, hiển thị trên trang web hoặc truyền cho một chương trình bên ngoài. Nguy hiểm xuất hiện khi ứng dụng **ghép chuỗi đó vào nơi hệ thống khác đang phân tích cú pháp**: câu SQL, lệnh shell, HTML, JavaScript hoặc biểu thức tìm kiếm. Dữ liệu lúc ấy có nguy cơ bị hiểu thành một phần câu lệnh hoặc cấu trúc điều khiển.

Trong chương **Bảo mật** của module **CODE_QUALITY_FUNDAMENTALS**, cách tách dữ liệu khỏi cú pháp là một thuộc tính quan trọng để mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Lập trình viên phải xác định rõ phần nào là **cấu trúc do ứng dụng kiểm soát**, phần nào là **giá trị đến từ bên ngoài**, và cơ chế nào giữ chúng ở hai vai trò khác nhau.

Nguyên tắc thực hành:

> Để trình thực thi nhận cấu trúc lệnh từ ứng dụng và giá trị qua kênh dữ liệu riêng. Khi cần chọn cấu trúc động, chỉ chọn từ các phương án được định nghĩa trước.

Đây là một cách phòng tránh nhiều dạng **injection**. Tuy nhiên, dùng tham số hóa đúng không thay thế kiểm tra quyền truy cập, tính hợp lệ nghiệp vụ hoặc giới hạn tài nguyên.

## 1. Nhìn từ nguồn dữ liệu tới điểm diễn giải

~~~text
Nguồn: Form, URL, JSON, CSV, DB, message
            |
            v
Ứng dụng Java: đọc, kiểm tra, biến đổi
            |
            v
Điểm diễn giải: SQL, shell, HTML, JS,
                template, XPath, regex, ...
~~~

**Nguồn dữ liệu** (*source*) là nơi một giá trị được nhập hoặc được lấy vào hệ thống. **Điểm sử dụng có khả năng diễn giải cú pháp** (*sink*) là nơi hệ thống khác có thể hiểu các ký tự của giá trị như một phần ngôn ngữ điều khiển.

Chẳng hạn, tên đăng nhập có dấu nháy có thể là dữ liệu hợp lệ. Nhưng nếu tên đó được nối thẳng vào văn bản SQL, trình phân tích SQL sẽ đọc cả những dấu nháy ấy như ký tự trong câu lệnh. Lỗi xuất hiện **ở điểm ghép vào truy vấn**, không nhất thiết tại thời điểm nhận tên đăng nhập.

### 1.1. Phân biệt các lớp bảo vệ

| Cơ chế | Mục tiêu | Không tự bảo đảm |
| --- | --- | --- |
| **Validation** | Kiểm tra loại, miền giá trị, độ dài và quy tắc nghiệp vụ | Không thay thế bind parameter |
| **Tham số hóa** | Truyền giá trị tách khỏi cấu trúc SQL hoặc API tương tự | Không thay thế phân quyền trên bản ghi |
| **Mã hóa đầu ra theo ngữ cảnh** | Hiển thị giá trị mà không biến thành cú pháp HTML/JS | Không có một cách mã hóa chung cho mọi ngôn ngữ |
| **Allowlist cấu trúc** | Giới hạn tên cột, hướng sắp xếp, loại thao tác | Không tự xác nhận người dùng được phép thao tác |
| **Authorization** | Kiểm soát ai được đọc hoặc sửa dữ liệu nào | Không khắc phục câu lệnh bị ghép chuỗi sai |

Những lớp bảo vệ này **bổ sung nhau**. Một email đã được kiểm tra đúng định dạng vẫn cần truyền dưới dạng tham số SQL. Ngược lại, SQL đã tham số hóa vẫn có thể vô tình trả dữ liệu thuộc tài khoản khác nếu thiếu điều kiện quyền truy cập.

## 2. SQL: tách giá trị khỏi cấu trúc truy vấn

### 2.1. Cách dễ mắc lỗi: nối chuỗi

~~~java
// Không nên dùng nếu username đến từ bên ngoài.
String sql = "SELECT id FROM accounts WHERE username = '"
        + username + "'";
Statement statement = connection.createStatement();
ResultSet rows = statement.executeQuery(sql);
~~~

Ở đây **username** vốn là giá trị cần so sánh nhưng lại được đưa trực tiếp vào **văn bản SQL**. Dữ liệu chứa ký tự có ý nghĩa đối với cú pháp SQL có thể làm truy vấn bị diễn giải khác ý định hoặc gây lỗi cú pháp.

Không nên tự chế bộ thay thế dấu nháy hay lọc vài ký tự “đáng ngờ”. Cơ chế chuẩn là **PreparedStatement** cùng **bind parameter**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class AccountRepository {
    public List<Long> findIdsByUsername(
            Connection connection, String username)
            throws SQLException {

        String sql = """
                SELECT id FROM accounts
                WHERE username = ?
                """;
        List<Long> ids = new ArrayList<>();

        try (PreparedStatement query =
                     connection.prepareStatement(sql)) {
            query.setString(1, username);

            try (ResultSet result = query.executeQuery()) {
                while (result.next()) {
                    ids.add(result.getLong("id"));
                }
            }
        }
        return ids;
    }
}
~~~

Trong ví dụ:

1. Ứng dụng chọn cố định bảng, cột và phép so sánh.
2. **?** đánh dấu vị trí dành cho **giá trị**, không phải nơi để chèn câu SQL tùy ý.
3. **setString(1, username)** để driver truyền giá trị như dữ liệu; dấu nháy hay từ khóa trong tên không biến thành điều kiện SQL.
4. **try-with-resources** đóng các đối tượng JDBC thuộc phạm vi phương thức.
5. **Connection** do bên gọi truyền vào, nên phương thức không tự đóng. Chủ sở hữu lượt mượn connection phải dọn dẹp theo hợp đồng.

Mã sử dụng **text block**, có trong Java 15 trở lên. Cú pháp text block chỉ giúp trình bày SQL; **không tự chống injection** nếu nội dung bên trong vẫn được ghép từ dữ liệu không đáng tin.

JDBC có các phương thức bind kiểu phù hợp như **setString**, **setLong**, **setInt**, **setTimestamp** và **setNull**. Không cần chuyển mọi đầu vào thành chuỗi rồi ghép thủ công vào SQL. Bind đúng vẫn cần đi cùng validation: một ID âm hoặc giới hạn truy vấn cực lớn có thể không phải injection nhưng vẫn sai hợp đồng.

### 2.2. Truy vấn động không có nghĩa cú pháp tùy ý

Một trường hợp khó là sắp xếp theo cột người dùng chọn. **PreparedStatement** thường bind **giá trị biểu thức**, không dùng dấu **?** làm tên bảng, tên cột hay từ khóa:

~~~java
// ORDER BY ? thường sắp theo một giá trị, không phải chọn cột động.
String sql = "SELECT id FROM orders ORDER BY ?";
~~~

Cũng không an toàn khi nối thẳng một query parameter vào SQL:

~~~java
// Rủi ro nếu sortBy đến trực tiếp từ HTTP:
String sql = "SELECT id FROM orders ORDER BY " + sortBy;
~~~

Hãy ánh xạ lựa chọn bên ngoài sang **cú pháp thuộc quyền sở hữu của ứng dụng**:

~~~java
public final class OrderSortSql {
    private OrderSortSql() {}

    public static String orderBy(String requestedField,
                                 boolean descending) {
        if (requestedField == null) {
            throw new IllegalArgumentException("Missing sort field");
        }

        String column = switch (requestedField) {
            case "createdAt" -> "created_at";
            case "totalVnd" -> "total_vnd";
            default -> throw new IllegalArgumentException(
                    "Unsupported sort field");
        };
        String direction = descending ? "DESC" : "ASC";
        return " ORDER BY " + column + " " + direction;
    }
}
~~~

Khi tạo truy vấn:

~~~java
String sql = """
        SELECT id, total_vnd FROM orders
        WHERE customer_id = ?
        """ + OrderSortSql.orderBy(requestedField, descending);

try (PreparedStatement query = connection.prepareStatement(sql)) {
    query.setLong(1, customerId);
    // Đọc ResultSet trong một try-with-resources tương ứng.
}
~~~

Phép nối chuỗi trong ví dụ thứ hai chỉ sử dụng **các hằng thuộc allowlist**. Giá trị **customerId** tiếp tục được bind. Cách làm này khác căn bản với nối một đoạn SQL tùy ý do người dùng cung cấp.

Nếu ứng dụng dùng ORM, query builder hoặc native SQL, vẫn cần rà soát xem **các giá trị thực sự được bind** và **các thành phần cú pháp động chỉ đến từ cấu trúc đã định nghĩa** hay không. Việc dùng framework không tự động xóa mọi nguy cơ injection.

### 2.3. LIKE: bind tham số và xử lý ký tự đại diện là hai việc khác nhau

Giá trị **%** và **_** có ý nghĩa ký tự đại diện trong nhiều cách dùng SQL **LIKE**. Bind parameter giúp chúng không trở thành cấu trúc SQL, nhưng **không tự khiến chúng có nghĩa là ký tự nguyên văn**.

Nếu yêu cầu nghiệp vụ là tìm chuỗi *nguyên văn* bên trong một trường, có thể tạo mẫu:

~~~java
public static String literalContainsPattern(String text) {
    String escaped = text
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    return "%" + escaped + "%";
}
~~~

Với hệ quản trị hỗ trợ cú pháp này:

~~~sql
SELECT id FROM products
WHERE name LIKE ? ESCAPE '!'
~~~

Sau đó **bind** kết quả từ **literalContainsPattern** vào dấu **?**. Cần kiểm tra cú pháp, collation và quy tắc chữ hoa/thường của DB thật. **ESCAPE '!'** xử lý ý nghĩa của LIKE; nó không thay thế **PreparedStatement**.

## 3. Lệnh hệ điều hành: đối số không phải một chuỗi shell

Ví dụ không nên dùng với tên tệp do người dùng nhập:

~~~java
// Không an toàn: dữ liệu trở thành một phần chuỗi lệnh shell.
new ProcessBuilder(
        "sh", "-c", "cat /srv/reports/" + fileName
).start();
~~~

Lời gọi này chủ động yêu cầu **sh -c** phân tích một chuỗi lệnh. Nếu **fileName** đến từ ngoài ứng dụng, shell có thể hiểu ký tự của nó như cú pháp thay vì tên tệp thuần túy.

### 3.1. Ưu tiên API chuyên dụng khi chỉ thao tác dữ liệu

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static String readReport(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}
~~~

**Files.readString** không cần shell. Tuy nhiên, đoạn mã chỉ loại bỏ ranh giới phân tích lệnh; nó **chưa bảo đảm đường dẫn thuộc phạm vi được phép**. Nếu nhận đường dẫn từ người dùng, vẫn cần kiểm soát thư mục cho phép, symlink và quyền truy cập.

### 3.2. Nếu buộc phải chạy một chương trình bên ngoài

~~~java
public static ProcessBuilder buildExport(String customerCode) {
    if (customerCode == null
            || !customerCode.matches(
                    "[A-Za-z0-9][A-Za-z0-9_-]{0,39}")) {
        throw new IllegalArgumentException("Invalid customer code");
    }

    return new ProcessBuilder(
            "/opt/tools/export-report",
            "--customer-code",
            customerCode);
}
~~~

Ví dụ giả định công cụ **/opt/tools/export-report** đã được ứng dụng cài đặt và tin cậy, hỗ trợ tham số **--customer-code**. Đây là đường dẫn minh họa, không phải một công cụ mặc định của Java.

**ProcessBuilder** nhận executable và các đối số riêng biệt, nên không cần nhờ shell phân tích một chuỗi lệnh. Tuy nhiên, **chương trình đích** vẫn có cú pháp lựa chọn riêng. Cần cố định executable, chỉ cho phép những giá trị đúng hợp đồng, hạn chế quyền tiến trình và kiểm soát timeout, kích thước đầu ra cùng tài nguyên.

Đừng kết luận **Runtime.exec(String)** luôn tương đương **sh -c**: cách Java xử lý chuỗi cho API đó không giống việc chủ động gọi shell. Quy tắc thiết kế là **không ghép dữ liệu không đáng tin thành một chuỗi chương trình để trình diễn giải lệnh tự đọc**, và ưu tiên đối số được truyền có cấu trúc.

## 4. HTML và JavaScript: nội dung hiển thị không phải mã thực thi

Giả sử ứng dụng hiển thị lời chào theo tên người dùng:

~~~java
// Dễ sai nếu displayName do người dùng cung cấp.
String html = "<p>Xin chào, " + displayName + "</p>";
~~~

Các ký tự trong **displayName** có thể được trình duyệt xem như cú pháp HTML thay vì văn bản, tạo nguy cơ **cross-site scripting (XSS)**. Không nên xử lý vấn đề này bằng cách tự xóa một vài ký tự hoặc dùng một hàm escape chung cho mọi nơi.

### 4.1. Mã hóa theo đúng ngữ cảnh

Nếu giá trị chỉ là **văn bản bên trong một phần tử HTML**, có thể dùng thư viện mã hóa đầu ra theo ngữ cảnh. Ví dụ với dependency **OWASP Java Encoder**:

~~~java
import org.owasp.encoder.Encode;

String html = "<p>Xin chào, "
        + Encode.forHtmlContent(displayName)
        + "</p>";
~~~

Phương thức **forHtmlContent** phù hợp với nội dung văn bản HTML. Nó **không** phải giải pháp duy nhất cho giá trị thuộc tính HTML, URL, CSS hay mã JavaScript. Mỗi ngữ cảnh có quy tắc riêng; phải chọn API mã hóa theo vị trí dữ liệu **thực sự được xuất ra**, không chỉ theo nguồn dữ liệu.

Khi dùng template engine hoặc framework web, nên sử dụng cơ chế **tự mã hóa nội dung biến theo ngữ cảnh**. Tránh cơ chế xuất HTML thô nếu người dùng chỉ nhập văn bản. Trên DOM, gán **textContent** để hiển thị văn bản thuần; **innerHTML** yêu cầu trình duyệt diễn giải chuỗi như HTML, nên có rủi ro nếu chuỗi không đáng tin.

### 4.2. Khi ứng dụng thực sự muốn nhận HTML có định dạng

Một trình soạn thảo bài viết có thể cho phép người dùng dùng tiêu đề, in đậm hoặc danh sách. Khi đó, mã hóa toàn bộ thành văn bản có thể không đáp ứng nhu cầu, nhưng đưa HTML thô vào trang cũng không an toàn.

Cần dùng **HTML sanitizer chuyên dụng** với chính sách **allowlist** các phần tử và thuộc tính được phép, bảo vệ các ngữ cảnh URL/thuộc tính, và kiểm thử với các biến thể đầu vào. Không nên tự xây sanitizer bằng regex thay thế vài chuỗi.

**Mã hóa đầu ra** và **sanitization** là hai nhiệm vụ khác nhau:

- Mã hóa đầu ra khiến dữ liệu được hiển thị an toàn ở một vị trí cụ thể.
- Sanitization có chủ đích giữ lại một tập con của một ngôn ngữ đánh dấu, đồng thời loại bỏ cấu trúc không được phép.

**Content Security Policy (CSP)** là một lớp phòng vệ bổ sung hữu ích, nhưng không thay thế mã hóa đầu ra đúng ngữ cảnh.

### 4.3. Tạo JSON bằng serializer, không ghép chuỗi

~~~java
// Không nên tạo JSON bằng nối dữ liệu tùy ý:
String json = "{\"name\":\"" + displayName + "\"}";
~~~

Ký tự dấu nháy, xuống dòng hoặc backslash trong dữ liệu có thể làm cấu trúc JSON bị sai. Nên dùng **JSON serializer** tin cậy, ví dụ Jackson, Gson hoặc cơ chế của framework, với kiểu dữ liệu rõ ràng. Nhưng JSON được tạo hợp lệ **không tự bảo đảm an toàn** khi lại nhúng trực tiếp vào một khối JavaScript hay HTML: cần bảo vệ theo ngữ cảnh nơi nó xuất hiện.

Không nên dùng chuỗi người dùng làm **mã JavaScript** hoặc nguồn của một template được thực thi nếu chức năng chỉ cần truyền một giá trị văn bản.

## 5. Các trình diễn giải khác: template, regex và truy vấn chuyên biệt

Nguyên tắc tách dữ liệu khỏi cú pháp áp dụng rộng hơn SQL và shell:

| Điểm sử dụng | Rủi ro nếu biến dữ liệu thành cú pháp | Hướng bảo vệ |
| --- | --- | --- |
| SQL, JPQL, HQL, truy vấn ORM thô | Điều kiện và cấu trúc truy vấn bị thay đổi | Bind giá trị; allowlist phần cú pháp động |
| Shell hoặc chương trình bên ngoài | Dữ liệu thành cú pháp shell, option hay đối số điều khiển | API riêng, đối số tách biệt, kiểm tra hợp đồng công cụ |
| HTML và DOM | Dữ liệu thành thẻ hoặc thuộc tính thay vì văn bản | Contextual output encoding, DOM text API |
| JSON hoặc mã JavaScript | Văn bản làm sai cấu trúc hay trở thành mã | Serializer và ranh giới dữ liệu riêng |
| Template engine | Dữ liệu người dùng bị phân tích thành biểu thức template | Template cố định do ứng dụng sở hữu; truyền giá trị qua biến |
| XPath, LDAP filter, bộ lọc chuyên dụng | Dữ liệu thay đổi điều kiện lọc | API bind hoặc escaping đặc thù cho ngôn ngữ |
| Regular expression | Chuỗi literal bị hiểu thành mẫu, hoặc gây tiêu tốn tài nguyên | API tìm literal hoặc Pattern.quote |
| Log và định dạng máy đọc | Dữ liệu tạo thêm dòng, trường hoặc thông tin giả | Structured logging, xử lý ký tự điều khiển, giới hạn độ dài |

### 5.1. Khi chỉ muốn tìm chuỗi nguyên văn, đừng biến nó thành regex

Nếu chức năng chỉ yêu cầu xác định một chuỗi con, cách trực tiếp là:

~~~java
boolean containsLiteral(String source, String term) {
    return source.contains(term);
}
~~~

Nếu một API buộc dùng regex nhưng giá trị nhập phải là chuỗi nguyên văn, có thể dùng **Pattern.quote**:

~~~java
import java.util.regex.Pattern;

boolean matchesLiteral(String source, String term) {
    return Pattern.compile(Pattern.quote(term))
            .matcher(source)
            .find();
}
~~~

Hai ví dụ giả định đầu vào không null. **Pattern.quote** bảo vệ ý nghĩa của một **mẫu literal**; nó không đủ để kiểm soát độ phức tạp nếu ứng dụng thực sự cho phép người dùng gửi **regex tùy ý**. Khi đó cần chính sách riêng cho tập biểu thức được hỗ trợ, giới hạn kích thước và khả năng tiêu tốn CPU.

### 5.2. Template và biểu thức động

Khi muốn gửi lời chào, hãy truyền tên người dùng như **biến dữ liệu** vào một template được ứng dụng quản lý. Không nên nhận một chuỗi từ người dùng rồi dùng nó làm **nguồn template để biên dịch và thực thi**.

Tương tự, nếu giao diện chỉ cần cho chọn một trong vài thao tác, hãy dùng **enum hoặc danh sách tên hành động được phép** thay vì nhận một “biểu thức thực thi” tùy ý qua các cơ chế script, eval hoặc ngôn ngữ truy vấn tùy biến.

Việc làm rõ ranh giới cú pháp còn cải thiện khả năng đọc: khi review, người đọc biết chính xác **đâu là thao tác được chọn** và **đâu chỉ là giá trị của thao tác**.

## 6. Đường dẫn và URL: dữ liệu có cấu trúc cũng mang rủi ro

Một đường dẫn hoặc URL không nhất thiết được thực thi như mã, nhưng vẫn có **ý nghĩa điều hướng và quyền truy cập**. Việc tách câu lệnh khỏi dữ liệu chỉ là một phần của thiết kế an toàn.

### 6.1. Đọc tệp theo đường dẫn người dùng cung cấp

~~~java
// Chưa đủ an toàn nếu requestedName không đáng tin:
Path candidate = rootDirectory.resolve(requestedName);
String content = Files.readString(candidate);
~~~

Ký tự đi lên thư mục hoặc đường dẫn tuyệt đối có thể đưa chương trình ra ngoài phạm vi dự kiến. Một bước kiểm tra cho **tệp đã tồn tại** có thể là:

~~~java
Path root = rootDirectory.toRealPath();
Path candidate = root.resolve(requestedName).toRealPath();

if (!candidate.startsWith(root)) {
    throw new SecurityException("Outside permitted directory");
}

String content = Files.readString(candidate);
~~~

**toRealPath** giúp xác định đường dẫn thực, bao gồm việc giải quyết symlink theo cấu hình mặc định. Nhưng giữa **kiểm tra** và **mở tệp** có thể có race condition (*time of check to time of use*) nếu bên khác có thể thay đổi cây thư mục. Với thư mục bị người dùng không đáng tin thao tác đồng thời, còn cần phân quyền hệ thống tệp hoặc cơ chế mở tệp an toàn hơn, ví dụ **SecureDirectoryStream** khi nền tảng hỗ trợ.

Với tài nguyên nghiệp vụ, thiết kế tốt hơn thường là nhận **reportId**, kiểm tra người dùng được phép đọc báo cáo đó, rồi tra cứu đường dẫn đã được hệ thống kiểm soát. Tên tệp có cú pháp hợp lệ không chứng minh người gọi được quyền truy cập.

### 6.2. URL và SSRF

Nếu ứng dụng nhận URL từ client và tự tải nội dung, người dùng có thể chi phối **đích mạng**. Rủi ro **server-side request forgery (SSRF)** không được giải quyết bằng cách chỉ URL-encode chuỗi.

Các lớp bảo vệ tùy kiến trúc bao gồm:

- Hạn chế host, scheme, cổng và endpoint được phép.
- Dùng parser URL chuẩn và kiểm soát chuyển hướng.
- Kiểm soát địa chỉ thực sự sẽ kết nối, kể cả thay đổi DNS hoặc redirect.
- Giới hạn timeout, kích thước phản hồi và loại dữ liệu trả về.
- Không chuyển token hay thông tin xác thực nhạy cảm tới đích do người dùng quyết định.

**URL encoding** xử lý cách biểu diễn giá trị trong URL; nó không quyết định **host nào được phép truy cập**.

## 7. Kiểm thử: dữ liệu đặc biệt vẫn chỉ là dữ liệu

Kiểm thử bảo mật nên xác minh ít nhất hai điều:

1. **Giá trị hợp lệ nhưng khác thường** được xử lý đúng, không bị từ chối tùy tiện chỉ vì có dấu nháy, ký tự Unicode, dấu phần trăm hoặc dấu xuống dòng.
2. Dữ liệu đầu vào **không thể thay đổi cấu trúc thực thi**, không truy cập vượt phạm vi và không tạo tác dụng phụ ngoài hợp đồng.

Đừng chỉ thử chuỗi có ký tự lạ rồi kết luận toàn bộ hệ thống đã an toàn. Cần xác định **oracle** của từng điểm sử dụng: SQL phải giữ điều kiện truy vấn, HTML phải hiển thị văn bản, quyền truy cập phải chặn bản ghi không được phép.

### 7.1. Kiểm thử JDBC tích hợp bằng JUnit 5

Ví dụ sau dùng **JUnit 5** và cơ sở dữ liệu **H2 in-memory**. H2 cần dependency kiểm thử riêng; ví dụ minh họa cơ chế bind tham số, không phải báo cáo đã chạy trên mọi driver và hệ quản trị.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import org.junit.jupiter.api.Test;

class ParameterBindingTest {
    private int countByUsername(
            Connection connection, String input) throws Exception {
        String sql =
                "SELECT COUNT(*) FROM accounts WHERE username = ?";

        try (PreparedStatement query =
                     connection.prepareStatement(sql)) {
            query.setString(1, input);
            try (ResultSet rows = query.executeQuery()) {
                rows.next();
                return rows.getInt(1);
            }
        }
    }

    @Test
    void specialCharactersDoNotAlterSqlStructure() throws Exception {
        try (Connection connection =
                     DriverManager.getConnection("jdbc:h2:mem:")) {

            try (Statement setup = connection.createStatement()) {
                setup.execute(
                        "CREATE TABLE accounts (username VARCHAR(100))");
                setup.execute(
                        "INSERT INTO accounts (username) VALUES ('alice')");
            }

            assertEquals(1, countByUsername(connection, "alice"));
            assertEquals(0, countByUsername(
                    connection, "' OR '1'='1"));
            assertEquals(0, countByUsername(
                    connection, "O'Brian"));
        }
    }
}
~~~

Các chuỗi lạ trong bài kiểm thử là **giá trị tìm kiếm**, không phải yêu cầu thực thi một điều kiện SQL khác. Với các giá trị không tồn tại trong dữ liệu thử, kết quả mong đợi là **0 bản ghi**. Kiểm thử giúp phát hiện thay đổi triển khai khiến giá trị không còn được bind đúng cách.

Một bảng bị tạo và dữ liệu mẫu được thêm bằng SQL cố định trong phần setup kiểm thử không có cùng rủi ro như ghép trực tiếp chuỗi không đáng tin vào truy vấn ứng dụng. Nhưng ngay cả khi kiểm thử trên xanh, ứng dụng vẫn cần kiểm tra những truy vấn còn lại, phân quyền và môi trường triển khai thực.

### 7.2. Kiểm thử allowlist phần cấu trúc

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class OrderSortSqlTest {
    @Test
    void mapsKnownChoicesToOwnedSql() {
        assertEquals(" ORDER BY created_at DESC",
                OrderSortSql.orderBy("createdAt", true));
        assertEquals(" ORDER BY total_vnd ASC",
                OrderSortSql.orderBy("totalVnd", false));
    }

    @Test
    void rejectsUnknownStructure() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderSortSql.orderBy(
                        "arbitraryExpression", true));
    }

    @Test
    void rejectsMissingSortField() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderSortSql.orderBy(null, false));
    }
}
~~~

Kiểm thử này không gọi DB, nhưng chứng minh rằng lựa chọn ngoài allowlist không được biến thành một mảnh SQL từ đầu vào tùy ý. Kiểm thử ở tầng tích hợp vẫn cần để xác nhận truy vấn đầy đủ trả dữ liệu đúng và bảo vệ quyền.

### 7.3. Ma trận dữ liệu bất thường

| Điểm sử dụng | Đầu vào nên thử | Bằng chứng cần tìm |
| --- | --- | --- |
| SQL tham số hóa | Tên chứa dấu nháy, khoảng trắng, Unicode | Dấu nháy thuộc giá trị, không mở thêm điều kiện |
| LIKE | Từ khóa chứa **%**, **_**, ký tự thoát | Khớp nguyên văn hay dùng wildcard đúng hợp đồng |
| Cột/hướng ORDER BY | Lựa chọn hợp lệ, giá trị lạ, null | Chỉ tạo cú pháp được allowlist cho phép |
| Đối số chương trình ngoài | Ký tự đặc biệt, chuỗi dài, giá trị trông như tùy chọn | Dữ liệu không tạo thêm câu lệnh hay thay chế độ chạy |
| Nội dung HTML | Dấu ngoặc, dấu nháy, chuỗi giống thẻ | Được hiển thị như văn bản, không sinh cấu trúc DOM ngoài ý muốn |
| Template | Nội dung giống biểu thức template | Được truyền như giá trị, không được tính như biểu thức |
| File path | Thành phần đi lên thư mục, symlink, tên trùng | Không đọc ra ngoài thư mục và quyền cho phép |
| URL | Host ngoài allowlist, redirect, đích mạng nội bộ | Client không kết nối tới endpoint bị cấm |
| Dữ liệu nhiều dòng | Xuống dòng hoặc ký tự điều khiển trong log | Không gây hiểu nhầm bản ghi log hoặc làm lộ dữ liệu nhạy cảm |
| API có quyền | ID bản ghi thuộc người dùng khác | Bị từ chối dù SQL đã tham số hóa an toàn |

Lưu ý **dữ liệu có ký tự đặc biệt không mặc nhiên là dữ liệu không hợp lệ**. Tên một người có dấu nháy hoặc tiếng Việt có thể hoàn toàn hợp lệ. Bộ kiểm thử cần phân biệt lỗi định dạng nghiệp vụ với lỗi dữ liệu bị biến thành cấu trúc thực thi.

## 8. Cách review đường đi của dữ liệu

Khi review một API, hãy đi theo thứ tự:

1. **Xác định nguồn:** Giá trị đến từ query parameter, HTTP body, header, cookie, DB, file hay message?
2. **Theo dõi biến đổi:** Có trim, decode, normalize, nối chuỗi, serialize, ghi cache hoặc chuyển qua hàm helper không?
3. **Xác định điểm diễn giải:** SQL, shell, HTML, template, regex, file path hay URL?
4. **Chỉ ra phần cú pháp đáng tin:** SQL cố định, executable cố định, template do ứng dụng sở hữu hoặc các trường sort đã allowlist.
5. **Kiểm tra kênh truyền giá trị:** Bind SQL, đối số ProcessBuilder riêng, API DOM văn bản, serializer hay contextual encoder?
6. **Tách cấu trúc động:** Nếu có yêu cầu điều khiển tên cột hoặc hành động, dữ liệu đã được ánh xạ sang lựa chọn định nghĩa trước chưa?
7. **Kiểm soát quyền:** Người gọi có được đọc bản ghi, mở tệp hoặc truy cập endpoint đó không?
8. **Kiểm thử tình huống bất thường:** Giá trị có dấu nháy, Unicode, ký tự đặc biệt hoặc đường dẫn ngoài phạm vi có tạo kết quả đúng không?
9. **Xử lý lỗi:** Thông báo có tránh tiết lộ chi tiết nhạy cảm không? Log có tránh ghi token/mật khẩu? Tài nguyên có được giải phóng?

Một thiết kế dễ review thường biểu diễn đường đi:

~~~text
HTTP request
      |
      v
Parse và kiểm tra hợp đồng
      |
      +--> Giá trị lọc ------> PreparedStatement bind
      |
      +--> Chọn sort --------> enum / allowlist -> SQL cố định
      |
      +--> Văn bản hiển thị -> output encoding / textContent
      |
      +--> Mã báo cáo -------> kiểm tra quyền -> tra cứu path
~~~

Mỗi nhánh dùng dữ liệu đầu vào nhưng có **điểm sử dụng** khác nhau, vì vậy cần cơ chế bảo vệ thích hợp. Một hàm tên **sanitizeInput** dùng chung cho mọi nhánh thường che giấu khác biệt giữa các ngữ cảnh, gây khó hiểu và dễ sửa sai khi thêm tính năng.

## 9. Những hiểu nhầm thường gặp

**“Đã kiểm tra đầu vào nên nối vào SQL được.”** Validation xác nhận tính hợp lệ nghiệp vụ, không tạo ranh giới cú pháp. Giá trị vẫn nên được bind.

**“Chỉ cần escape dấu nháy.”** Cú pháp của SQL, shell, HTML, JavaScript và các ngôn ngữ khác không có cùng quy tắc. Không nên tự tạo một bộ escape dùng chung.

**“PreparedStatement giải quyết cả tên bảng và ORDER BY.”** Bind tham số dành cho giá trị; tên cột, tên bảng và từ khóa động cần allowlist cấu trúc.

**“Dùng ORM thì không có injection.”** Query thô hoặc đoạn SQL được nối chuỗi bên trong ORM vẫn có thể bị diễn giải sai.

**“ProcessBuilder tự động ngăn mọi command injection.”** Đối số riêng tránh nhiều vấn đề shell, nhưng executable và bộ phân tích tùy chọn của chương trình đích vẫn cần kiểm soát.

**“Một hàm encode HTML đủ cho tất cả.”** Nội dung văn bản HTML, thuộc tính, URL và JavaScript có ngữ cảnh khác nhau; dùng sai ngữ cảnh có thể không an toàn.

**“URL đã được encode nên gọi đi đâu cũng được.”** SSRF liên quan tới đích mạng được phép, không chỉ cách biểu diễn chuỗi URL.

**“Truy vấn không injection thì người dùng được phép thấy kết quả.”** Authorization vẫn cần bảo vệ từng dữ liệu và hành động.

## 10. Tình huống thực hành

Một API xuất danh sách đơn hàng nhận:

~~~text
GET /orders/export
  ?customerId=...
  &search=...
  &sortBy=...
  &direction=...
  &format=...
~~~

Một triển khai ban đầu sử dụng:

~~~java
String sql = "SELECT * FROM orders WHERE customer_id = "
        + customerId
        + " AND note LIKE '%" + search + "%'"
        + " ORDER BY " + sortBy + " " + direction;

String command = "export-tool --format " + format;
// Sau đó chạy command qua shell để tạo file.
~~~

Hãy phân tích:

1. Những đầu vào nào đang đi vào **cú pháp SQL**, và đầu vào nào vào **cú pháp shell**?
2. **customerId** và **search** cần được truyền vào PreparedStatement thế nào?
3. Vì sao **sortBy** và **direction** phải được ánh xạ qua allowlist thay vì dùng tùy ý?
4. Nếu chỉ hỗ trợ xuất **CSV** và **JSON**, API nên biểu diễn **format** như thế nào để tránh cấu trúc lệnh tùy ý?
5. Nếu tạo tệp xuất bất đồng bộ, bên nào sở hữu tệp tạm, khi nào xóa và làm sao tránh đọc ra ngoài thư mục?
6. Nếu người dùng cố chọn **customerId** thuộc tài khoản khác, việc tham số hóa SQL có đủ ngăn truy cập trái phép không?
7. Cần những ca kiểm thử nào cho ký tự đặc biệt, quyền truy cập, sắp xếp không hợp lệ và tệp xuất?

**Gợi ý đối chiếu:** **customerId** và mẫu **search** cần được bind; nếu tìm kiếm nguyên văn, còn cần escape wildcard theo quy tắc LIKE. **sortBy**, **direction** và **format** nên được ánh xạ từ các lựa chọn hữu hạn sang mã hoặc cấu trúc do ứng dụng sở hữu. Có thể dùng thư viện tạo CSV/JSON thay vì gọi shell. **CustomerId** phải được kiểm tra quyền truy cập độc lập. Tệp tạm cần vòng đời và cơ chế giới hạn đường dẫn phù hợp. Kiểm thử phải chứng minh dữ liệu không thay đổi cấu trúc câu lệnh, không vượt quyền và được xuất theo hợp đồng.

## 11. Ghi nhớ

- **Injection** xuất hiện khi dữ liệu không đáng tin được diễn giải như một phần câu lệnh hoặc cấu trúc điều khiển.
- Với SQL, dùng **bind parameter** cho giá trị; với phần cú pháp động, ánh xạ lựa chọn qua **allowlist** sang các hằng do ứng dụng sở hữu.
- Với hệ điều hành, ưu tiên **API chuyên dụng hoặc đối số riêng**, tránh ghép dữ liệu vào chuỗi shell.
- Với web, dùng **serializer, contextual output encoding và API DOM dành cho văn bản**; không dùng một kiểu escape cho mọi ngữ cảnh.
- Dù đã tách dữ liệu khỏi cú pháp, vẫn phải **kiểm tra quyền truy cập, đường dẫn, đích mạng, xử lý lỗi và các trường hợp bất thường**.
