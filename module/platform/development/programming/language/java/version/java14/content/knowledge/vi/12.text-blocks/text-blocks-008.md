# Text blocks trong Java: tạo SQL, JSON, HTML và mẫu thông điệp nhiều dòng

## 1. Vì sao nên dùng text block?

Khi một chuỗi Java chứa nhiều dòng SQL, JSON, HTML hoặc nội dung thông báo, cách viết bằng nhiều chuỗi nối `+` dễ bị rối bởi dấu xuống dòng, dấu nháy kép và ký tự escape. **Text block** cho phép viết nội dung nhiều dòng gần giống với văn bản thực tế, ngay trong mã nguồn Java:

```java
String greeting = """
        Xin chào,
        Chào mừng bạn đến với Java.
        """;
```

Biểu thức trên tạo chuỗi có hai dòng nội dung và một ký tự xuống dòng cuối chuỗi:

```text
Xin chào,
Chào mừng bạn đến với Java.
```

Trong chuỗi Java, nội dung tương ứng là `"Xin chào,\nChào mừng bạn đến với Java.\n"`. Khoảng thụt lề để canh mã nguồn thường được Java loại bỏ theo quy tắc *incidental indentation*, không trở thành một loạt dấu cách đầu mỗi dòng của kết quả.

**Trạng thái hiện hành:** Text blocks có mặt ở Java 13/14 dưới dạng preview, trở thành tính năng **chính thức từ Java 15** (JEP 378), và dùng bình thường trên Java 17, 21 cùng các phiên bản Java mới hơn. Các ví dụ trong bài không cần `--enable-preview`. Mặc dù học trong chủ đề Java 14, nên dùng cú pháp **đã ổn định** thay vì hướng dẫn preview cũ.

Text block là **một biểu thức `String`**, không phải kiểu dữ liệu mới, không phải trình phân tích SQL/JSON/HTML, và **không tự thay biến hay tự escape dữ liệu không tin cậy**. Phần tạo văn bản và phần xử lý an toàn cần được phân biệt rõ.

## 2. Cú pháp cơ bản và ý nghĩa xuống dòng

Mẫu khai báo:

```java
String text = """
        Dòng thứ nhất
        Dòng thứ hai
        """;
```

Một text block có:

1. **Opening delimiter** `"""`, theo sau bởi khoảng trắng tùy chọn rồi **bắt buộc có một dấu xuống dòng**; nội dung không bắt đầu ngay sau `"""` trên cùng dòng.
2. **Nội dung**: một hoặc nhiều dòng. Có thể chứa dấu `"` thường mà không phải viết `\"` cho từng dấu nháy.
3. **Closing delimiter** `"""`, có thể đặt trên dòng riêng hoặc ngay sau ký tự cuối của nội dung. Vị trí này ảnh hưởng tới chuỗi kết quả, đặc biệt là xuống dòng cuối.

Ví dụ cùng văn bản nhưng khác dấu xuống dòng cuối:

```java
String hasFinalNewline = """
        A
        B
        """;

String noFinalNewline = """
        A
        B""";

System.out.println(hasFinalNewline.endsWith("\n")); // true
System.out.println(noFinalNewline.endsWith("\n"));  // false
```

Đây là đoạn đặt trong một phương thức, không phải chương trình độc lập. Chuỗi thứ nhất chứa `"A\nB\n"`; chuỗi thứ hai chứa `"A\nB"`. Sự khác biệt quan trọng khi tạo thông báo, SQL gửi qua công cụ khác hoặc chuỗi cần so sánh chính xác trong kiểm thử.

Java chuẩn hóa các dấu kết thúc dòng trong nội dung text block về **LF** (`\n`) và loại thụt lề phụ thuộc vào bố cục mã nguồn. Vì vậy đừng mặc định text block giữ nguyên mọi khoảng trắng, tab hoặc kiểu xuống dòng trong tệp nguồn; nếu định dạng là một phần của giao thức, hãy kiểm tra chính xác chuỗi kết quả.

## 3. Dùng text block cho SQL

### 3.1. Viết truy vấn dễ đọc

Không cần ghép chuỗi trên nhiều dòng:

```java
String sql = """
        SELECT id, name, created_at
        FROM customers
        WHERE status = ?
        ORDER BY created_at DESC
        """;
```

Nhờ cú pháp nhiều dòng, các mệnh đề `SELECT`, `FROM`, `WHERE` và `ORDER BY` được trình bày như truy vấn SQL thực tế. Đây vẫn là **một đối tượng `String`**; text block không hiểu cú pháp SQL và không kiểm tra tên bảng, cột hay tính tương thích với hệ quản trị cơ sở dữ liệu.

**Vấn đề bảo mật quan trọng:** text block **không ngăn SQL injection**. Khi điều kiện truy vấn đến từ đầu vào người dùng, hãy dùng **prepared statement và bind parameter**, không nối trực tiếp dữ liệu vào chuỗi SQL.

### 3.2. Bind parameter bằng JDBC

Ví dụ phương thức Java sau nhận kết nối JDBC đã mở và một trạng thái do người dùng nhập:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class CustomerQuery {
    static void printCustomers(Connection connection, String status)
            throws SQLException {
        String sql = """
                SELECT id, name
                FROM customers
                WHERE status = ?
                ORDER BY id
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, status);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    System.out.println(rows.getLong("id")
                            + ": " + rows.getString("name"));
                }
            }
        }
    }
}
```

Đây là **lớp hợp lệ** có phương thức gọi từ mã ứng dụng; để chạy thực sự cần một `Connection` đến cơ sở dữ liệu có bảng và cột tương ứng, cùng JDBC driver. Không có stdout cố định vì kết quả phụ thuộc dữ liệu trong database.

- `?` là placeholder cho **giá trị dữ liệu**, được cung cấp qua `statement.setString(1, status)`.
- Truy vấn giữ nguyên cấu trúc SQL; dữ liệu nhập không bị diễn giải thành một phần lệnh SQL.
- `PreparedStatement` và `ResultSet` được đóng bằng *try-with-resources*.
- Placeholder JDBC thường **không dùng để thay tên bảng, tên cột hoặc từ khóa ORDER BY**. Nếu có trường hợp tên cột cần thay đổi, dùng danh sách tên cột được cho phép (*allowlist*), không ghép chuỗi tùy ý từ người dùng.

**Sai về bảo mật:**

```java
// Không thực hiện với dữ liệu không tin cậy:
String unsafeSql = """
        SELECT id, name
        FROM customers
        WHERE status = '%s'
        """.formatted(status);
```

Dùng `formatted` chỉ thay chữ vào chuỗi, không bind parameter, không escape SQL đúng chuẩn và có thể tạo SQL injection. Việc xuống dòng đẹp không làm truy vấn an toàn hơn.

## 4. Dùng text block cho JSON

### 4.1. Dữ liệu JSON tĩnh

Text block đặc biệt thuận tiện với JSON vì dấu `"` xuất hiện thường xuyên:

```java
String json = """
        {
          "event": "created",
          "count": 2,
          "active": true,
          "tags": ["java", "text-block"]
        }
        """;
```

Đoạn mã này là **giá trị chuỗi JSON cố định** trong một phương thức, phù hợp với mẫu response, fixture kiểm thử hoặc ví dụ tài liệu. Những dấu nháy kép trong JSON **không cần** `\"` chỉ vì chúng nằm trong text block.

Tuy nhiên:

- Text block **không tự kiểm tra** JSON hợp lệ. Dấu phẩy sai, key trùng hoặc sai kiểu vẫn là trách nhiệm của parser/schema và logic ứng dụng.
- **Không có interpolation tự động**: các chuỗi như `%s` không tự được thay; phải gọi `formatted(...)` nếu thật sự muốn dùng định dạng đó.
- Nếu JSON chứa ký tự đặc biệt trong một **giá trị động** (dấu nháy, ký tự điều khiển, xuống dòng, dấu gạch chéo ngược), phép thay chuỗi đơn giản **không bảo đảm JSON hợp lệ hoặc đúng ý**.

### 4.2. JSON động: nên dùng serializer

Với dữ liệu lấy từ request hoặc database, chọn thư viện serialization phù hợp dự án (ví dụ Jackson) thay vì tự ghép JSON bằng `String.formatted`:

```java
// Minh họa khi dự án có dependency Jackson databind:
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

class JsonExample {
    static String toJson(String userInput) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        return mapper.writeValueAsString(
                Map.of("message", userInput, "active", true)
        );
    }
}
```

Đoạn này cần dependency **Jackson databind** trên classpath/module path; không phải ví dụ chỉ dùng Java SE. Serializer sẽ xử lý escaping JSON cho giá trị `userInput`. Ví dụ, đầu vào chứa dấu `"` hoặc ký tự xuống dòng được mã hóa đúng theo quy tắc JSON; tự viết `"""{"message": "%s"}"""` rồi gọi `formatted(...)` không làm được việc đó.

**Ngoại lệ thực tế:** Khi mọi giá trị trong JSON đều là hằng đã kiểm soát, text block tĩnh vẫn rất hữu ích. Khi giá trị là động, việc build mô hình đối tượng rồi serialize thường an toàn, dễ mở rộng và dễ kiểm thử hơn.

### 4.3. Text block không phải chuỗi raw

Dù giảm đáng kể số dấu escape, text block **vẫn xử lý escape sequence của Java**. Ví dụ Java mã nguồn chứa `\n` sẽ cho ra ký tự xuống dòng trong chuỗi; nếu JSON cần **hai ký tự** backslash và `n` bên trong một giá trị, mã nguồn Java phải escape backslash thích hợp. Với dấu `"""` thực sự cần xuất hiện trong nội dung, phải escape ít nhất một dấu nháy, tránh bị nhận thành delimiter đóng.

Đây là lý do việc tạo **JSON có dữ liệu động** nên giao cho serializer. Không nên suy luận rằng nhìn giống JSON trong text block thì chắc chắn đã có JSON encoding đúng.

## 5. Dùng text block cho HTML

### 5.1. Khai báo markup nhiều dòng

```java
String html = """
        <section class="notice">
          <h2>Thông báo</h2>
          <p>Nội dung đã sẵn sàng.</p>
        </section>
        """;
```

Dấu `"` trong thuộc tính HTML được viết trực tiếp; không cần ghép nhiều chuỗi hoặc lặp lại `\n`. Text block thích hợp với HTML fixture, thư mẫu, đoạn thông báo tĩnh hoặc output mẫu trong kiểm thử.

Nhưng text block chỉ cho ra **String**. Nó không chạy HTML parser, không thực hiện kiểm tra DOM, không ngăn XSS, không tự encode ký tự khi chèn dữ liệu do người dùng nhập.

### 5.2. Chèn văn bản động vào HTML cần escaping

Với vị trí là **nội dung văn bản bên trong một phần tử HTML**, cần escape những ký tự có ý nghĩa cú pháp như `&`, `<`, `>` trước khi chèn:

```java
static String escapeHtmlText(String input) {
    return input.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;");
}

static String notice(String userInput) {
    return """
            <section class="notice">
              <p>%s</p>
            </section>
            """.formatted(escapeHtmlText(userInput));
}
```

Hai phương thức đặt trong một lớp Java. Nếu `userInput` là `"A&B <ready>"`, phần văn bản được chèn là `A&amp;B &lt;ready&gt;`; trình duyệt có thể hiển thị văn bản nguyên nghĩa, thay vì coi `<ready>` là markup.

**Giới hạn quan trọng:** Hàm `escapeHtmlText` ở trên **chỉ minh họa trường hợp chèn vào HTML text node**. Nó **không** tự trở thành giải pháp escaping đầy đủ cho:

- Giá trị thuộc tính HTML (như `href`, `title`, `data-*`).
- Ngữ cảnh URL, CSS, JavaScript nằm trong HTML.
- Những nơi cần kiểm tra giao thức URL hoặc chính sách HTML sanitizer/CSP.

Với HTML động ở ứng dụng thực tế, nên dùng **template engine có escaping phù hợp ngữ cảnh** và cơ chế bảo vệ XSS của framework. Không tự ghép dữ liệu không tin cậy vào `<script>` hoặc thuộc tính sự kiện chỉ vì chuỗi nguồn là text block.

## 6. Dùng text block cho mẫu thông điệp

Text blocks tạo mẫu thông báo nhiều dòng dễ đọc:

```java
String template = """
        Xin chào %s,
        Đơn hàng %s đã được xác nhận.
        Cảm ơn bạn đã sử dụng dịch vụ.
        """;

String message = template.formatted("Lan", "DH-42");
System.out.println(message);
```

Đây là đoạn đặt trong phương thức; giá trị `message` bao gồm ba dòng và xuống dòng cuối:

```text
Xin chào Lan,
Đơn hàng DH-42 đã được xác nhận.
Cảm ơn bạn đã sử dụng dịch vụ.
```

`String.formatted(...)` dùng cú pháp format kiểu `Formatter` (`%s` cho chuỗi, `%d` cho số nguyên theo ngữ cảnh thích hợp, `%%` cho dấu phần trăm nguyên nghĩa). Phương thức `formatted` có trên Java hiện đại từ Java 15 và hoạt động với text block như mọi chuỗi khác.

Lưu ý:

- Chọn **chuỗi template do ứng dụng kiểm soát**, rồi truyền giá trị vào `formatted`. Không sử dụng dữ liệu không tin cậy làm chính chuỗi format, vì ký hiệu `%` trong format có nghĩa đặc biệt.
- `formatted` **không tự làm SQL parameter binding, JSON escaping hoặc HTML escaping**. Chỉ dùng để trình bày một chuỗi khi việc chèn trực tiếp phù hợp ngữ cảnh.
- Số lượng/ký hiệu định dạng phải đúng với đối số; nếu sai, `Formatter` có thể ném ngoại lệ như `MissingFormatArgumentException` hoặc `IllegalFormatConversionException`.
- Mẫu thông điệp nhiều ngôn ngữ, quy tắc số nhiều hoặc nội dung được dịch nên dùng hệ thống i18n/resource và cơ chế template phù hợp, thay vì hard-code mọi bản dịch trong mã nguồn.

Nếu không muốn một dòng trống ở cuối thông điệp, hãy kiểm soát **dấu xuống dòng cuối** trong text block hoặc sử dụng phép biến đổi có chủ đích như `stripTrailing()`; tránh `trim()` hoặc `strip()` vô tình xóa khoảng trắng có ý nghĩa ở cả hai đầu nội dung.

## 7. Chương trình Java 17+ hoàn chỉnh minh họa bốn loại nội dung

Lưu toàn bộ chương trình sau vào **`Main.java`**. Nó sử dụng text block cho SQL, JSON, HTML và mẫu thông điệp; chỉ in một số kết quả kiểm chứng để đầu ra ngắn và dễ đối chiếu. Không cần JDBC driver hay thư viện JSON vì SQL và JSON ở đây chỉ là các **chuỗi minh họa tĩnh**.

```java
public class Main {
    static String escapeHtmlText(String input) {
        return input.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;");
    }

    public static void main(String[] args) {
        String sql = """
                SELECT id, name
                FROM customers
                WHERE status = ?
                ORDER BY id
                """;

        String json = """
                {
                  "event": "created",
                  "count": 2
                }
                """;

        String html = """
                <div class="notice">
                  <strong>Thông báo</strong>
                  <p>%s</p>
                </div>
                """.formatted(escapeHtmlText("A&B <ready>"));

        String message = """
                Xin chào %s,
                Đơn %s đã được xác nhận.
                """.formatted("Lan", "DH-42");

        System.out.println("SQL=" + sql.stripTrailing().replace("\n", " | "));
        System.out.println("JSON=" + json.contains("\"count\": 2"));
        System.out.println("HTML=" + html.contains("A&amp;B &lt;ready&gt;"));
        System.out.println("MESSAGE=" + message.stripTrailing().replace("\n", " | "));
        System.out.println("TRAILING_NEWLINE=" + message.endsWith("\n"));
    }
}
```

Biên dịch bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Stdout chính xác khi chạy chương trình:**

```text
SQL=SELECT id, name | FROM customers | WHERE status = ? | ORDER BY id
JSON=true
HTML=true
MESSAGE=Xin chào Lan, | Đơn DH-42 đã được xác nhận.
TRAILING_NEWLINE=true
```

Giải thích kết quả:

1. `sql.stripTrailing().replace("\n", " | ")` biến các lần xuống dòng của truy vấn thành ` | ` chỉ để **dễ quan sát**. Bản SQL gốc vẫn giữ cấu trúc nhiều dòng và ký hiệu tham số `?`. `stripTrailing()` loại ký tự xuống dòng cuối trong chuỗi dùng để in.
2. `json.contains("\"count\": 2")` là `true`, chứng minh dấu `"` nằm đúng trong chuỗi JSON; đây **không phải** một bài kiểm thử JSON parser và không chứng minh dữ liệu JSON bất kỳ đều hợp lệ.
3. `html.contains(...)` là `true` vì dữ liệu `A&B <ready>` được escape khi chèn vào text node, tạo các entity HTML tương ứng.
4. `message` được tạo bằng `.formatted("Lan", "DH-42")`; `stripTrailing()` dùng riêng để in một dòng kiểm chứng với dấu phân cách ` | `.
5. `message.endsWith("\n")` là `true`, vì closing delimiter của text block đứng ở dòng riêng và văn bản có ký tự LF cuối. Hành vi này cần để ý khi so sánh chuỗi hoặc gửi nội dung ra hệ thống khác.

## 8. Kiểm soát indentation, whitespace và ký tự đặc biệt

### 8.1. Thụt lề trong mã nguồn không đồng nghĩa thụt lề trong String

```java
String sample = """
        first
          second
        """;
```

Nội dung thực tế là `"first\n  second\n"`: Java bỏ phần lề chung của các dòng theo quy tắc text block, nhưng giữ **hai dấu cách có chủ ý** trước `second`. Đây là cách viết thích hợp khi muốn JSON/HTML có mức lồng nhau dễ nhìn mà không phải đếm thủ công toàn bộ khoảng trắng thụt lề của Java.

Vị trí dấu `"""` đóng có thể ảnh hưởng tới mức lề được loại bỏ. Khi thay đổi định dạng mã bằng IDE, cần kiểm tra xem chuỗi kết quả còn đúng ý hay không, nhất là với SQL nhạy cảm về ký tự hoặc kiểm thử snapshot.

### 8.2. Chuỗi có xuống dòng cuối hay không?

```java
String withNewline = """
        hello
        """;

String withoutNewline = """
        hello""";

System.out.println(withNewline.equals("hello\n")); // true
System.out.println(withoutNewline.equals("hello")); // true
```

Hai đoạn text block tương tự nhau ở mắt người đọc nhưng **khác chuỗi kết quả**. Nếu định dạng cần khớp chính xác với tiêu chuẩn bên ngoài, hãy xác định trước có cần xuống dòng kết thúc hay không và viết test tương ứng.

### 8.3. Text block vẫn hỗ trợ escape sequence

Text blocks không phải *raw string*. Các escape thông thường như `\n`, `\t`, `\"`, `\\` vẫn được xử lý theo quy tắc Java. Ngoài ra:

- `\s` biểu diễn **một dấu cách** có thể giúp giữ khoảng trắng cuối dòng khi cần.
- Dấu backslash ở cuối dòng nội dung có thể **nối dòng**, không đưa ký tự xuống dòng đó vào chuỗi kết quả.
- Muốn chứa chuỗi có ba dấu nháy kép liên tiếp, phải escape ít nhất một dấu nháy để không vô tình kết thúc text block.

Những kỹ thuật này dành cho **trường hợp cần định dạng thật sự chính xác**. Trong SQL/JSON/HTML thông thường, hãy giữ cấu trúc đơn giản và tránh dùng escape phức tạp khi không cần.

### 8.4. Ký tự `%` và định dạng thông điệp

Với `String.formatted`, `%` là ký hiệu bắt đầu format specifier. Nếu mẫu thông điệp muốn in dấu phần trăm thực sự, viết `%%` trong mẫu khi gọi `formatted`:

```java
String notice = """
        Hoàn tất 100%%.
        Tác vụ: %s
        """.formatted("Tải dữ liệu");

System.out.println(notice);
```

Đầu ra:

```text
Hoàn tất 100%.
Tác vụ: Tải dữ liệu
```

Không cần `%%` khi chỉ dùng text block như một `String` thông thường mà **không gọi** `formatted`/`String.format`. Lựa chọn công cụ định dạng ảnh hưởng đến cách diễn giải `%`.

## 9. Những lỗi thường gặp khi dùng text block theo từng định dạng

| Tình huống | Hệ quả hoặc hiểu nhầm | Cách dùng đúng |
| --- | --- | --- |
| Viết text block rồi nghĩ nó tự chạy SQL | `String` không phải câu lệnh thực thi | Truyền `String` cho JDBC hoặc công cụ truy vấn phù hợp |
| Dùng `formatted(userInput)` để nhét giá trị vào SQL | Có nguy cơ SQL injection và lỗi dấu nháy | `PreparedStatement` + `?` + `setXxx` |
| Ghép giá trị động trực tiếp vào JSON | Dấu nháy, backslash và ký tự điều khiển có thể làm JSON sai | Dùng JSON serializer |
| Dùng `formatted` cho HTML chứa dữ liệu người dùng | Có nguy cơ XSS | Escape đúng **ngữ cảnh HTML** hoặc dùng template engine |
| Coi text block là raw string | Escape sequence vẫn được Java xử lý | Kiểm tra backslash, `\n`, `\t` và nháy kép |
| Bỏ qua newline cuối | Test hoặc nội dung gửi đi có ký tự `\n` ngoài ý muốn | Kiểm tra vị trí delimiter đóng / `endsWith("\n")` |
| Cho rằng indentation Java giữ nguyên tất cả | Chuỗi có thể mất phần thụt lề chung | Thử `equals` với chuỗi mong đợi, kiểm tra bản in |
| Chèn `%` vào template có gọi `formatted` | `Formatter` diễn giải dấu `%` | Dùng `%%` cho dấu phần trăm nguyên nghĩa |
| Không có newline sau dấu `"""` mở | Sai cú pháp text block | Đặt nội dung ở dòng sau opening delimiter |
| Đặt dữ liệu không tin cậy vào chính format string | Có thể làm hỏng định dạng hoặc gây lỗi format | Giữ mẫu cố định, truyền dữ liệu làm đối số |

### Ví dụ không hợp lệ về cú pháp

```java
// Sai: opening delimiter của text block phải được theo sau bởi line terminator.
// String invalid = """one line""";
```

Dòng trên được comment để nhấn mạnh **đây không phải cú pháp Java hợp lệ**. Nếu chỉ cần một chuỗi một dòng, dùng string literal `"one line"`.

## 10. Khi nào chọn text block, khi nào chọn công cụ khác?

**Chọn text block** khi phần lớn nội dung là **văn bản cố định nhiều dòng** và việc trình bày gần với định dạng đích làm mã nguồn dễ hiểu hơn:

- SQL truy vấn tương đối dài, với placeholder phù hợp.
- JSON fixture hoặc payload mẫu cố định trong kiểm thử.
- HTML fragment tĩnh hay markup đơn giản.
- Mẫu thông báo nhiều dòng có vài đối số định dạng đã kiểm soát.

**Chọn công cụ chuyên dụng** khi nội dung có nhiều dữ liệu động hoặc yêu cầu kiểm tra an toàn/đúng định dạng:

- **SQL:** JDBC prepared statements, API truy vấn tham số hóa hoặc ORM có hỗ trợ bind.
- **JSON:** serializer/parser có kiểm tra và mã hóa đúng.
- **HTML:** template engine, escaping theo ngữ cảnh, HTML sanitizer khi chấp nhận markup đầu vào.
- **Thông báo đa ngôn ngữ/phức tạp:** resource bundles, message template engine hoặc i18n framework có xử lý locale/plural.

Text block và công cụ chuyên dụng **không loại trừ nhau**. Ví dụ một prepared statement vẫn lấy chuỗi SQL từ text block; HTML template có thể sử dụng text block làm nguồn mẫu cố định; một JSON serializer có thể dùng text block làm fixture kiểm thử trong khi payload động vẫn được serialize chính xác.

## 11. Tự kiểm tra

**Câu 1.** Vì sao đoạn SQL bên dưới chưa an toàn khi `status` là dữ liệu người dùng?

```java
String query = """
        SELECT id FROM orders WHERE status = '%s'
        """.formatted(status);
```

Vì `formatted` **chèn chữ vào cú pháp SQL**, không dùng bind parameter. Cách tốt hơn là `WHERE status = ?` rồi `PreparedStatement.setString(...)`.

**Câu 2.** Text block này chứa bao nhiêu lần xuống dòng cuối nội dung?

```java
String html = """
        <p>Hello</p>
        """;
```

Nó có **một dấu LF kết thúc** sau `</p>`. Không có một dòng rỗng thứ hai chỉ vì delimiter đóng nằm ở dòng riêng.

**Câu 3.** Tại sao không nên dùng `"<p>%s</p>".formatted(userInput)` với dữ liệu người dùng tùy ý?

Vì nội dung có thể chứa HTML markup. Với text node, phải escape ký tự thích hợp hoặc dùng công cụ render có bảo vệ XSS theo ngữ cảnh.

**Câu 4.** Có thể giữ text block để làm JSON mẫu cố định mà vẫn dùng serializer cho dữ liệu JSON sinh động không?

Có. Text block chỉ là `String`. Dữ liệu tĩnh do ứng dụng kiểm soát có thể được ghi trực tiếp; dữ liệu động nên được tạo qua serializer.

**Ghi nhớ:** Text blocks giúp viết **chuỗi nhiều dòng dễ đọc**. Dấu nháy kép thông thường ít phải escape, nhưng Java vẫn áp dụng quy tắc indentation, escape và newline. Với SQL, JSON và HTML, **an toàn của dữ liệu động không đến từ text block**: hãy bind tham số SQL, serialize JSON, escape HTML đúng ngữ cảnh; với mẫu thông điệp, kiểm soát format string và số lượng đối số.

### Tham khảo chính thức

- [JEP 378 — Text Blocks, chuẩn từ Java 15](https://openjdk.org/jeps/378).
- [Java Language Specification — Text Blocks (`3.10.6)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.6).
- [Java SE API — String.formatted](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)).
- [Java SE API — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html).
