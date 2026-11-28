# Safe API thay cho string concatenation

## 1. Vấn đề không phải ký tự `+`, mà là quyền điều khiển cấu trúc

Ứng dụng thường cần kết hợp phần cố định và dữ liệu đầu vào: tìm một khách hàng trong database, gọi công cụ tạo báo cáo, dựng một trang hiển thị hoặc gửi request đến dịch vụ khác. Rủi ro injection xuất hiện khi dữ liệu không đáng tin được ghép vào một biểu diễn mà thành phần phía sau sẽ phân tích như câu lệnh hoặc ngôn ngữ có cấu trúc.

Ví dụ, một tên khách hàng được ghép vào SQL có thể làm thay đổi cú pháp query. Một tên file được ghép vào shell command có thể làm thay đổi thao tác chạy. Một đoạn văn bản được ghép vào HTML có thể trở thành phần tử hoặc thuộc tính thay vì chỉ được hiển thị.

Safe API trong bài này là API được chọn và sử dụng theo một hợp đồng rõ ràng, để dữ liệu nằm ở vị trí dữ liệu và cấu trúc thao tác vẫn do ứng dụng kiểm soát. Không có một nhãn “safe” áp dụng tuyệt đối cho mọi phương thức của một thư viện.

Một yêu cầu bảo mật có thể kiểm chứng là:

> Dữ liệu không đáng tin không được nối hoặc nội suy vào cấu trúc câu lệnh tại các sink có khả năng diễn giải. Ứng dụng phải dùng cơ chế bind giá trị, truyền đối số có cấu trúc hoặc API xuất dữ liệu theo đúng ngữ cảnh. Những lựa chọn mang ý nghĩa cấu trúc phải được ánh xạ sang tập giá trị do server sở hữu.

Mục tiêu này không cấm mọi phép nối chuỗi trong chương trình. Nối một mã hiển thị từ các giá trị thường khác với đưa chuỗi đó vào SQL, shell hoặc HTML. Điều cần kiểm soát là **đích sử dụng, quyền chọn cấu trúc và cách thành phần nhận diễn giải dữ liệu**.

## 2. Đánh giá một API bằng hợp đồng, không bằng tên gọi

Trước khi gọi một API là lựa chọn an toàn cho một luồng dữ liệu, cần trả lời:

1. API nhận riêng cấu trúc và giá trị hay chỉ nhận một string đã ghép xong?
2. Tham số nào là dữ liệu, tham số nào chọn field, toán tử, template, chương trình hoặc chế độ thực thi?
3. API có phương thức `raw`, `unsafe`, bỏ escaping hoặc đánh giá biểu thức không?
4. Có thành phần nào parse hoặc đánh giá lại dữ liệu sau bước API này không?
5. Hành vi có phụ thuộc driver, hệ điều hành, cấu hình hoặc chế độ ngôn ngữ không?
6. Những thuộc tính nào vẫn phải được kiểm tra ngoài cơ chế chống injection?

Một hàm builder có thể giúp viết code có cấu trúc nhưng vẫn nhận tên field tùy ý. Một template engine có thể escape mặc định nhưng vẫn có chế độ xuất HTML thô. Một process API có thể tách đối số nhưng chương trình con vẫn hiểu một đối số là option có khả năng thay đổi hành vi.

Do đó, yêu cầu cần chỉ ra mẫu sử dụng được phép. “Dùng thư viện X” chưa đủ nếu cùng thư viện có cả đường bind giá trị và đường chạy biểu thức thô.

### Ba lớp trách nhiệm cần tách rõ

| Trách nhiệm | Điều phải được quyết định |
|---|---|
| Kiểm soát cú pháp | Dữ liệu không thay đổi cấu trúc của ngôn ngữ tại sink |
| Kiểm soát năng lực | Người gọi chỉ được chọn thao tác, field, option và tài nguyên đã được cấp |
| Kiểm soát nghiệp vụ và tài nguyên | Giá trị đúng miền, đúng quyền, đúng thời điểm và trong giới hạn xử lý |

Bind một ID đúng cách không chứng minh người gọi được đọc tài nguyên có ID đó. Tạo URL đúng cú pháp không chứng minh đích mạng được phép. Tách argv đúng cách không chứng minh chương trình con được phép đọc đường dẫn đó.

## 3. Chọn API theo từng ngữ cảnh diễn giải

| Ngữ cảnh | Mẫu rủi ro | Hướng thiết kế |
|---|---|---|
| SQL hoặc ngôn ngữ query của ORM | Ghép input vào text query | Bind giá trị; cấu trúc động đi qua ánh xạ hữu hạn |
| Query document hoặc pipeline | Chuyển nguyên object client thành thao tác database | Command có schema hẹp; field và toán tử do server dựng |
| Chạy chương trình ngoài | Ghép một command string hoặc đưa input vào shell | Ưu tiên thư viện trực tiếp; nếu cần tiến trình thì cố định chương trình và truyền từng đối số |
| Hiển thị văn bản trên trang | Ghép dữ liệu vào HTML thô | API text hoặc template có escaping đúng vị trí sử dụng |
| Đường dẫn file | Ghép đường dẫn rồi tin đó là tài nguyên được phép | API đường dẫn kết hợp kiểm tra phạm vi và quyền; không chỉ nối separator |
| URL đến dịch vụ ngoài | Ghép scheme, host, path và query tùy ý | API URL có cấu trúc kết hợp chính sách đích và chuyển hướng |

Bảng thể hiện trách nhiệm thiết kế, không khẳng định chỉ cần gọi một hàm là hoàn thành toàn bộ phòng vệ. Với path và URL, việc biểu diễn đúng cú pháp vẫn cần kiểm tra quyền truy cập tài nguyên hoặc đích kết nối.

Không có một hàm `sanitize(String)` chung đủ để chuẩn bị cùng dữ liệu cho mọi dòng trong bảng. Quy tắc của một ngôn ngữ không tự bảo vệ ngôn ngữ khác, và dữ liệu đã được xử lý cho một ngữ cảnh có thể cần được xử lý khác ở ngữ cảnh tiếp theo.

## 4. Kiểm kê luồng dữ liệu trước khi thay code

Đơn vị rà soát hữu ích là một luồng từ nguồn đến sink:

```text
Nguồn không đáng tin
  -> parse / chuyển kiểu / chuẩn hóa
  -> command nghiệp vụ
  -> kiểm tra quyền và điều kiện
  -> dựng cấu trúc do ứng dụng sở hữu
  -> truyền giá trị qua vị trí dữ liệu của API
  -> sink thực hiện hoặc hiển thị
```

Nguồn không chỉ là HTTP body. Dữ liệu có thể đến từ query parameter, message, file import, nội dung đã lưu hoặc response của một dịch vụ khác. Nếu người dùng từng kiểm soát giá trị, việc lưu nó vào database không làm nó đủ tin cậy để ghép vào câu lệnh ở lần sử dụng sau.

Một danh mục sink nên ghi ít nhất: vị trí gọi, ngôn ngữ được diễn giải, API đang dùng, nguồn của từng tham số, quyền thực thi và mẫu thay thế dự kiến. Khi gặp wrapper, phải đọc hợp đồng của wrapper hoặc theo luồng đến API thực sự, thay vì dừng tại tên như `safeExecute`.

Ví dụ, wrapper nhận `String sql` và gọi `prepareStatement(sql)` không tự bảo vệ được chuỗi SQL đã bị ghép ở caller. Ranh giới tách cấu trúc và dữ liệu đã mất trước khi wrapper nhận tham số.

## 5. Ví dụ JDBC: giữ query cố định và bind giá trị

Oracle mô tả việc dùng `PreparedStatement` để truyền dữ liệu qua tham số thay vì để dữ liệu trở thành một phần của text SQL. Cơ chế này bảo vệ những giá trị thực sự được bind; nó không sửa các đoạn text không đáng tin đã được nối vào query trước đó. Xem [Oracle JDBC — Using Prepared Statements](https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html).

Ví dụ Java 17 sau tìm đơn hàng trong phạm vi tenant đã được xác minh. Schema database, quyền tìm kiếm và nguồn tạo scope là các giả định của tình huống minh họa.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class OrderLookupRepository {

    private static final String FIND_BY_CUSTOMER = """
        SELECT order_id, state
        FROM orders
        WHERE tenant_id = ? AND customer_name = ?
        ORDER BY created_at DESC, order_id DESC
        """;

    public record AuthorizedScope(String tenantId) {
    }

    public record OrderRow(String orderId, String state) {
    }

    public List<OrderRow> findByCustomer(
            Connection connection,
            AuthorizedScope scope,
            String customerName
    ) throws SQLException {
        if (scope == null
                || scope.tenantId() == null
                || scope.tenantId().isBlank()) {
            throw new IllegalStateException("ACCESS_SCOPE_REQUIRED");
        }
        if (customerName == null
                || customerName.isBlank()
                || customerName.length() > 128) {
            throw new IllegalArgumentException("INVALID_CUSTOMER_NAME");
        }

        List<OrderRow> rows = new ArrayList<>();
        try (PreparedStatement statement =
                connection.prepareStatement(FIND_BY_CUSTOMER)) {
            statement.setString(1, scope.tenantId());
            statement.setString(2, customerName);
            statement.setMaxRows(100);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    rows.add(new OrderRow(
                        result.getString("order_id"),
                        result.getString("state")
                    ));
                }
            }
        }
        return List.copyOf(rows);
    }
}
```

Tên như `O'Connor` được truyền nguyên vẹn ở vị trí tham số. Không tự bỏ dấu nháy hoặc thay tên khách hàng chỉ để tránh cú pháp SQL. Quy tắc định dạng nghiệp vụ vẫn áp dụng, nhưng không dùng nó thay cho binding.

Những điểm cần hiểu đúng trong ví dụ:

- Placeholder không nằm trong cặp dấu nháy của một string literal SQL.
- Cả tenant và tên khách hàng đều được bind, không ghép vào text query.
- Scope phải do lớp xác thực và phân quyền tạo sau khi kiểm tra; record chỉ là mô hình dữ liệu, không tự chứng minh nguồn tin cậy.
- `PreparedStatement` và `ResultSet` được đóng; `Connection` do caller quản lý vòng đời.
- Các giới hạn 128 đơn vị UTF-16 và 100 dòng là lựa chọn minh họa, cần thay bằng hợp đồng của hệ thống thật.
- Giới hạn số dòng không thay thế ngân sách thời gian query, phân trang hoặc thiết kế index.
- Lỗi `SQLException` cần được ánh xạ ở lớp xử lý lỗi phù hợp, không trả nguyên chi tiết database cho người gọi.

Mẫu sau vẫn không đáp ứng yêu cầu dù có gọi `prepareStatement`:

```java
// Sai về ranh giới cấu trúc/dữ liệu: input đã đi vào text SQL.
String sql = "SELECT order_id FROM orders WHERE customer_name = '"
    + customerName + "'";
PreparedStatement statement = connection.prepareStatement(sql);
```

Việc một API được gọi ở cuối chuỗi không thể đảo ngược cách caller đã dựng nội dung của nó.

## 6. Phần cấu trúc động cần ánh xạ, không giả làm tham số dữ liệu

Tên bảng, tên cột và hướng sort không phải các giá trị dữ liệu để thay thế tùy ý bằng placeholder. OWASP khuyến nghị giữ cố định hoặc ánh xạ những lựa chọn này sang tập giá trị do ứng dụng sở hữu. Xem [OWASP — SQL Injection Prevention, Allow-List Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html#allow-list-input-validation).

Ví dụ, API chỉ công bố hai cách sắp xếp:

```java
enum OrderSort {
    NEWEST,
    OLDEST
}

static String orderBy(OrderSort sort) {
    return switch (sort) {
        case NEWEST -> "created_at DESC, order_id DESC";
        case OLDEST -> "created_at ASC, order_id ASC";
    };
}
```

Phần text được trả về trong ví dụ là hằng do ứng dụng chọn, không phải string người dùng gửi. Khi ghép nó với một query cố định, cần giữ toàn bộ các giá trị dữ liệu trong vị trí bind riêng. Một enum không có ích nếu caller vẫn có đường truyền một `rawOrderBy` tùy ý để bỏ qua ánh xạ.

Với điều kiện `IN`, server có thể dựng số placeholder từ số phần tử đã kiểm tra và bind từng phần tử. Không ghép nội dung từng giá trị thành một danh sách SQL. Hợp đồng cần quy định mảng rỗng, phần tử `null`, giới hạn số phần tử và khả năng xử lý của driver.

Với tìm kiếm `LIKE`, binding bảo vệ ranh giới SQL nhưng không quyết định người dùng được tìm theo literal hay theo wildcard. Nếu nghiệp vụ yêu cầu tìm literal, cần chính sách xử lý wildcard theo dialect đang dùng. Không gọi việc query không bị injection là bằng chứng rằng chức năng tìm kiếm có đúng ý nghĩa hay không bị mở rộng ngoài dự kiến.

## 7. Ví dụ tiến trình: truyền đối số thay cho ghép shell command

Khi có thư viện thực hiện trực tiếp chức năng cần thiết, có thể tránh hẳn việc tạo command cho hệ điều hành. Nếu bắt buộc chạy công cụ ngoài, chương trình, chế độ và tài nguyên được phép cần do server xác định.

`ProcessBuilder` mô hình hóa chương trình và đối số bằng một danh sách string; tài liệu JDK lưu ý cách lệnh được biểu diễn có phụ thuộc nền tảng. Vì vậy cần kiểm chứng trên hệ điều hành và executable thực tế, không suy từ một bài test ở môi trường khác. Xem [Oracle JDK — ProcessBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html).

Ví dụ sau chỉ tạo builder cho một công cụ render giả định có hợp đồng option đã biết; nó không khởi chạy tiến trình:

```java
// Các path này đã được server phân giải từ job được cấp quyền.
// Không nhận executable hoặc đường dẫn tùy ý từ request body.
ProcessBuilder builder = new ProcessBuilder(
    approvedExecutable.toString(),
    "--format", "pdf",
    "--input", approvedInputPath.toString(),
    "--output", approvedOutputPath.toString()
);
builder.directory(approvedWorkingDirectory.toFile());
```

Mỗi option và giá trị được đưa vào vị trí đối số riêng. Không ghép toàn bộ chúng thành một command string, cũng không chuyển dữ liệu người dùng thành nội dung cho `sh -c`, `cmd /c` hoặc một trình thông dịch tương đương.

Tuy nhiên, tách đối số không tự ngăn **argument injection**: chương trình con vẫn có thể hiểu một giá trị được gửi là một option, biểu thức hoặc tên tài nguyên có ý nghĩa đặc biệt. Cần giới hạn đúng tập option và operand của công cụ được gọi. Chỉ dùng dấu kết thúc option như `--` khi công cụ thực sự hỗ trợ và hợp đồng đã được kiểm chứng. Xem [OWASP — OS Command Injection Defense](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html#argument-injection).

Một tên biến có tiền tố `approved` không làm path đáng tin. Thiết kế phải chỉ rõ bước phân giải ID sang tài nguyên, kiểm tra quyền đọc/ghi và cách xử lý filesystem thực tế. Việc nối path hoặc gọi `normalize()` không tự chứng minh file nằm trong phạm vi được phép, đặc biệt khi có liên kết hoặc thay đổi đồng thời.

Khi bổ sung bước chạy thật, còn cần hạn chế quyền tiến trình, environment, working directory, thời gian chạy và kích thước output. Phải quản lý stdout/stderr để không gây tắc nghẽn hoặc ghi dữ liệu nhạy cảm. Các điều kiện này bổ sung cho ranh giới đối số; chúng không được giải quyết chỉ bằng cách đổi constructor.

## 8. Ví dụ hiển thị: dùng API text khi yêu cầu là văn bản

Giả sử giao diện cần hiển thị tên khách hàng trong một `span` thông thường. Nếu chức năng chỉ cần văn bản, không cần tạo HTML bằng cách ghép tên vào một string markup.

```javascript
const customerLabel = document.createElement("span");
customerLabel.textContent = displayName;
container.append(customerLabel);
```

Trong ngữ cảnh phần tử văn bản này, nội dung được đặt như text thay vì đưa qua parser HTML. MDN phân biệt `textContent` với `innerHTML`, vốn xử lý HTML. Xem [MDN — Node.textContent](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent#differences_from_innerhtml).

Ví dụ không cấp quyền dùng cùng dữ liệu làm nội dung script, CSS, URL hoặc event handler. Nó cũng không có nghĩa được đọc text rồi đưa nguyên vào `innerHTML` ở một bước sau. Ranh giới phải được giữ đến sink cuối cùng.

Nếu nghiệp vụ thật sự cần rich text, cần một hợp đồng khác: những phần tử, thuộc tính và loại URL nào được phép; bộ xử lý nào thực thi chính sách; kết quả được chèn vào vị trí nào; thay đổi phiên bản được kiểm chứng ra sao. Không tự gắn nhãn “đã an toàn” vào một string chỉ vì client nói rằng nó là HTML đã làm sạch.

Template engine có escaping theo ngữ cảnh có thể là lựa chọn phù hợp. Tuy nhiên, chế độ xuất raw hoặc cơ chế tắt escaping phải được quản lý riêng. Yêu cầu cần chỉ rõ những đường nào bị cấm hoặc được phép theo một hợp đồng hẹp, thay vì chỉ ghi tên engine.

Tương tự, một JSON serializer tạo được JSON đúng cú pháp không tự bảo vệ mọi vị trí chèn vào trang HTML. Lớp chứa bên ngoài có ngữ pháp riêng; cần chọn cách truyền và tiêu thụ dữ liệu phù hợp với toàn bộ ngữ cảnh, không suy rằng đã serialize một lần là đủ cho mọi sink.

## 9. Thiết kế wrapper để caller không cần tự dựng ngôn ngữ

Một wrapper có ích khi nó thu hẹp quyền của caller và giữ các quyết định nhạy cảm ở nơi có thể rà soát. Nếu wrapper chỉ đổi tên một phương thức chạy raw string, lợi ích chống injection rất hạn chế.

| Hợp đồng dễ bị lạm dụng | Hợp đồng nghiệp vụ hẹp hơn |
|---|---|
| `execute(String query)` | Tìm đơn theo scope, tên khách hàng và sort enum |
| `run(String command)` | Render một tài liệu được cấp quyền theo định dạng đã công bố |
| `search(Map<String, Object> filter)` | Tìm theo command có field, kiểu và phép toán hữu hạn |
| `show(String html)` cho mọi nơi | Hiển thị text; rich text đi qua một luồng riêng có chính sách |

Caller của một chức năng xuất báo cáo thường chỉ cần chọn ID tài liệu và định dạng. Họ không cần biết executable, working directory, tên file tạm hoặc option của chương trình render. Giữ những chi tiết đó bên trong service giúp giảm số điểm có thể dựng thao tác không đúng hợp đồng.

Một facade kiểu dữ liệu hẹp có thể là:

```java
enum ReportFormat {
    PDF,
    CSV
}

record RenderRequest(String documentId, ReportFormat format) {
}
```

Service vẫn phải kiểm tra quyền với `documentId`, định dạng được hỗ trợ cho tài liệu đó và nguồn template được dùng. Kiểu enum chỉ giới hạn lựa chọn format; nó không tự cung cấp phân quyền hoặc chứng minh nội dung tài liệu an toàn.

Nếu tạo kiểu như `ValidatedPath`, `TrustedHtml` hoặc `AuthorizedScope`, cần bảo đảm chỉ những bước thực sự giữ được bất biến mới tạo được giá trị đó trong luồng đáng tin. Không deserialize trực tiếp một kiểu “đã xác minh” từ request rồi dùng tên kiểu làm bằng chứng.

### Giữ cấu trúc qua các lớp

Một đường đi tốt là truyền dữ liệu có kiểu và giá trị riêng đến repository hoặc renderer. Một đường đi kém là tạo query an toàn, chuyển nó thành text có giá trị, rồi gửi text đó cho một lớp khác parse lại.

Các hệ thống nhiều tầng cần kiểm kê nơi diễn giải lại: stored procedure dựng SQL động, worker đọc filter đã lưu, template con hoặc công cụ ngoài đọc một file cấu hình sinh từ input. Bảo vệ ở tầng trước không tự lan sang một ngôn ngữ mới phía sau.

Khi một procedure được gọi bằng tham số nhưng bên trong vẫn nối dữ liệu vào SQL động, cần bảo vệ cả điểm dựng SQL nội bộ. Tương tự, một process được gọi bằng argv nhưng tự đánh giá một đối số như biểu thức vẫn có một ranh giới cần đặc tả riêng.

## 10. Viết yêu cầu bảo mật đủ để nghiệm thu

Một câu “không nối chuỗi” thường dẫn đến tranh luận về cú pháp code hơn là rủi ro. Tập yêu cầu nên mô tả hành vi tại sink và bằng chứng tương ứng.

| Mã | Yêu cầu minh họa | Bằng chứng nghiệm thu |
|---|---|---|
| API-SAFE-01 | Mọi sink có khả năng diễn giải được kiểm kê cùng nguồn dữ liệu và ngữ cảnh | Danh mục luồng từ nguồn tới sink, bao gồm các worker và dữ liệu đã lưu |
| API-SAFE-02 | Giá trị động được truyền qua vị trí dữ liệu của API phù hợp; không nội suy vào cấu trúc | Rà soát lời gọi và kiểm tra tích hợp ở ranh giới API/driver |
| API-SAFE-03 | Tên field, toán tử, sort, chương trình và chế độ thực thi được ánh xạ từ tập server cho phép | Bảng ánh xạ và kịch bản gửi lựa chọn ngoài tập |
| API-SAFE-04 | Không có đường raw hoặc tắt escaping trong luồng thông thường để bỏ qua hợp đồng | Kiểm kê phương thức đặc biệt, quyền gọi và các đường xử lý lỗi |
| API-SAFE-05 | Scope quyền và các điều kiện bắt buộc không bị dữ liệu client ghi đè hoặc loại bỏ | Kịch bản đa tenant, tài nguyên ngoài quyền và điều kiện động |
| API-SAFE-06 | Không parse hoặc đánh giá lại giá trị đã nhận như một câu lệnh ngoài hợp đồng | Truy vết dữ liệu qua lưu trữ, hàng đợi và tầng xử lý tiếp theo |
| API-SAFE-07 | Lỗi bind, lỗi dựng thao tác hoặc input không hợp lệ phải dẫn tới từ chối có kiểm soát | Quan sát không có fallback sang nối chuỗi hoặc thao tác rộng hơn |
| API-SAFE-08 | Quyền thực thi và ngân sách tài nguyên của sink được giới hạn theo nghiệp vụ | Chính sách quyền, giới hạn thời gian, output và kiểm tra khả dụng |
| API-SAFE-09 | Dữ liệu hợp lệ có dấu phân cách hoặc ký tự đa ngôn ngữ giữ nguyên ý nghĩa | Các trường hợp tên có dấu nháy, Unicode và khoảng trắng theo schema |
| API-SAFE-10 | Driver, runtime và cấu hình ảnh hưởng cách diễn giải có baseline được kiểm chứng | Hồ sơ cấu hình và kết quả thử trên môi trường cần hỗ trợ |
| API-SAFE-11 | Lỗi và quan sát vận hành không lộ credential, nội dung nhạy cảm hoặc câu lệnh thô ngoài chính sách | Kiểm tra response, log, trace và báo cáo lỗi |
| API-SAFE-12 | Wrapper dùng chung duy trì ranh giới cấu trúc/dữ liệu và có owner | Hợp đồng wrapper, phạm vi caller và bằng chứng kiểm tra luồng thực tế |

Các yêu cầu trong bảng là mẫu xây dựng cho dự án, không phải tuyên bố rằng chỉ cần đủ 12 mã là hệ thống đã đạt một tiêu chuẩn cụ thể. Mỗi yêu cầu cần liên kết với threat model, phạm vi chức năng và owner thực thi.

Đội ứng dụng thường sở hữu cách gọi API và mô hình command. Đội nền tảng sở hữu cấu hình runtime hoặc công cụ dùng chung. Đội dữ liệu có thể sở hữu quyền database và các procedure. Đội kiểm thử xác nhận hành vi xuyên các lớp, thay vì chỉ xác nhận một phương thức có tên đúng đã được gọi.

## 11. Thiết kế kịch bản nghiệm thu theo từng sink

Các kịch bản dưới đây là hướng dẫn cho vòng kiểm chứng của dự án. Chúng không phải báo cáo rằng code trong bài đã được chạy trong một hệ thống thực tế.

| Kịch bản | Điều cần chứng minh |
|---|---|
| Tên khách hàng có dấu nháy đơn | Được xử lý như dữ liệu theo schema; query không đổi cấu trúc |
| Giá trị tìm kiếm có hình thức giống biểu thức SQL | Không tạo điều kiện mới hoặc mở rộng tập kết quả ngoài ý nghĩa literal |
| Client gửi tên cột hoặc hướng sort không công bố | Bị từ chối, không đi thẳng vào text query |
| Danh sách `IN` rỗng hoặc vượt giới hạn | Hành vi theo hợp đồng, không bỏ điều kiện lọc hoặc tạo query không giới hạn |
| Dữ liệu được lưu rồi được dùng trong báo cáo | Vẫn đi qua binding tại sink mới, không được tin vì đã nằm trong database |
| Đường dẫn công cụ có khoảng trắng | Được truyền theo cấu trúc đối số đúng trên môi trường cần hỗ trợ |
| Giá trị có hình thức giống option của chương trình con | Không chọn thêm năng lực ngoài hợp đồng; bị từ chối hoặc được xử lý như operand theo thiết kế |
| Client đề nghị executable hoặc shell riêng | Không thể thay chương trình cố định của chức năng |
| Tên hiển thị có dấu `<` và `>` | Trong phần tử text, ký tự được hiển thị chứ không tạo markup |
| Một wrapper chuyển dữ liệu qua worker | Worker giữ vị trí dữ liệu và không dựng lại raw string để thực thi |
| Binding hoặc dựng API thất bại | Không có đường dự phòng dùng nối chuỗi để “cứ chạy được” |
| Dữ liệu đúng cấu trúc nhưng ngoài quyền | Vẫn bị kiểm tra quyền từ chối trước tác động không được phép |
| Truy vấn hoặc chương trình con quá thời gian | Bị xử lý theo ngân sách; không chạy lại bằng đường rộng hoặc ít kiểm soát hơn |

Kiểm tra cần có dữ liệu đối chứng hợp lệ. Nếu tất cả input đều bị từ chối thì hệ thống có thể tránh được một số rủi ro nhưng không đáp ứng chức năng. Mục tiêu là giữ dữ liệu hợp lệ và từ chối khả năng điều khiển không được cấp.

Với SQL, có thể quan sát lời gọi ở driver hoặc kiểm tra cấu trúc thao tác và tập kết quả trên database thử nghiệm. Một dòng log hiển thị SQL kèm giá trị không tự chứng minh query đã bị nối ở code, vì công cụ chẩn đoán có thể tái dựng biểu diễn để hiển thị. Ngược lại, chỉ thấy tên `PreparedStatement` trong log cũng không chứng minh các vị trí động đều được bind.

Với chương trình con, có thể dùng một công cụ kiểm thử được kiểm soát để ghi nhận danh sách đối số thực tế, thay vì chạy một công cụ nguy hiểm với payload thử. Cần xác minh executable và đối số được nhận, không chỉ so sánh một command string do ứng dụng tự in ra trước khi chạy.

Với DOM, kiểm tra cấu trúc node và nội dung hiển thị. Không chỉ tìm một chuỗi trong HTML cuối cùng mà bỏ qua việc browser đã tạo ra phần tử hoặc thuộc tính khác với mục tiêu.

Trong mọi trường hợp, dữ liệu dùng để kiểm thử và đầu ra chẩn đoán phải tuân theo chính sách bảo mật. Không dùng credential thật hoặc bật log chứa dữ liệu sản xuất chỉ để tạo bằng chứng.

## 12. Chuyển một luồng cũ sang API có cấu trúc

Việc chuyển đổi nên tạo ra một hợp đồng cụ thể cho từng sink, không thay cú pháp nối chuỗi hàng loạt mà chưa hiểu ngữ nghĩa.

1. Xác định chức năng mong muốn và các nguồn input, kể cả dữ liệu đã lưu hoặc được đưa qua hàng đợi.
2. Tách phần cấu trúc do ứng dụng quyết định khỏi phần giá trị được người dùng đề nghị.
3. Chọn API và mẫu sử dụng có thể giữ sự tách biệt ở sink thực tế.
4. Thay những lựa chọn cấu trúc cần thiết bằng enum hoặc bảng ánh xạ theo chức năng và quyền.
5. Giữ kiểm tra kiểu, miền, quyền và tài nguyên; không xóa chúng vì đã chuyển sang API mới.
6. Xác minh hành vi hợp lệ, hành vi lỗi và các đường diễn giải tiếp theo trước khi kết luận đã thay thế xong.

Khi wrapper dùng chung được sửa, cần kiểm kê caller có thể phụ thuộc vào hành vi cũ. Ví dụ, một caller từng gửi wildcard trong tên tìm kiếm có thể đang dùng một chức năng khác với tìm literal. Chuyển đổi cần quyết định rõ chức năng nào được duy trì và chức năng nào phải có hợp đồng riêng.

Không để hai đường tồn tại vô thời hạn: đường mới dùng binding và đường cũ dùng raw string khi gặp trường hợp đặc biệt. Nếu có một nhu cầu chưa được API hẹp hỗ trợ, cần mô hình hóa nó thành chức năng được kiểm soát, thay vì thêm cờ `skipSafety` do người gọi tự chọn.

Các pattern search hoặc công cụ phân tích tĩnh có thể hỗ trợ tìm vị trí đáng rà soát. Chúng không tự chứng minh đã tìm đủ nguồn dữ liệu, wrapper, query động trong procedure hoặc template được nạp gián tiếp. Bằng chứng phải phù hợp với kiến trúc thực tế của hệ thống.

## 13. Những cách làm nhìn giống nhưng không giữ được ranh giới

| Cách làm | Vì sao chưa đáp ứng yêu cầu |
|---|---|
| Đổi `+` thành `String.format` hoặc nội suy | Dữ liệu vẫn có thể nằm trong cùng text được diễn giải |
| Gọi `prepareStatement` sau khi nối input | Query đã chứa cấu trúc không đáng tin trước bước prepare |
| Escape SQL một lần rồi dùng cho mọi nơi | Không giải quyết các ngữ cảnh khác hoặc mọi cấu hình ngôn ngữ |
| Dùng ORM nhưng vẫn nối text JPQL/HQL | Một ngôn ngữ query khác vẫn có ranh giới cấu trúc/dữ liệu |
| Đưa một command string duy nhất vào process API | Chưa mô hình hóa executable và từng đối số theo hợp đồng |
| Truyền argv rồi tin mọi option được nhận | Chưa kiểm soát ý nghĩa mà chương trình con gán cho đối số |
| Dùng template engine rồi xuất raw HTML | Đã bỏ cơ chế bảo vệ tại đúng vị trí tiêu thụ |
| Tạo JSON đúng cú pháp rồi chèn vào mọi ngữ cảnh | Ngôn ngữ bao ngoài có thể diễn giải khác |
| Dùng tên kiểu `TrustedValue` cho input client | Tên kiểu không xác lập nguồn tin cậy hoặc quyền |
| Chỉ chặn ký tự bị xem là nguy hiểm | Có thể phá dữ liệu hợp lệ mà chưa kiểm soát cấu trúc tại sink |

Một cơ chế parameter của logger cũng không phải cơ chế bind SQL hay escaping HTML. Nó có hợp đồng của logger. Mỗi lần dữ liệu đổi sink, phải xác định lại ngữ nghĩa và chính sách đầu ra của sink đó.

API có cấu trúc cũng không thay thế cập nhật thư viện, giảm quyền, kiểm tra nghiệp vụ, giới hạn tài nguyên hoặc phát hiện bất thường. Các lớp này bảo vệ những điều kiện khác nhau; không nên dùng thành công của một lớp để suy rằng mọi rủi ro đã biến mất.

## 14. Bài tập chuyển nguyên tắc thành yêu cầu

Một chức năng báo cáo nhận tên khách hàng, sort và định dạng file. Repository đang ghép tên vào SQL. Worker xuất báo cáo nhận một command string từ API. Giao diện hiển thị tên file bằng HTML thô. Dữ liệu báo cáo còn có thể được lấy từ một cấu hình lưu trước đó.

Hãy xây dựng:

1. Danh mục nguồn, phép biến đổi và sink cho cả luồng trực tiếp lẫn cấu hình đã lưu.
2. Hợp đồng repository phân biệt giá trị bind với lựa chọn sort do server sở hữu.
3. Command nghiệp vụ cho worker chỉ giữ những lựa chọn người gọi cần được phép chọn.
4. Mẫu hiển thị tên file đúng ngữ cảnh text và chính sách riêng nếu cần rich text.
5. Các yêu cầu xử lý lỗi để không quay lại đường raw khi API mới không chấp nhận input.
6. Ma trận nghiệm thu chứng minh dữ liệu hợp lệ giữ nguyên ý nghĩa, đồng thời không thể tạo thêm query, option hoặc markup ngoài quyền.

Kết quả cần chỉ ra API cụ thể, vị trí dữ liệu, phần cấu trúc cố định, owner và bằng chứng. Câu trả lời “escape hết input” chưa thể hiện được những ranh giới đó.

Safe API phát huy tác dụng khi cách dùng của nó giữ nguyên sự phân biệt giữa cấu trúc và dữ liệu đến điểm tiêu thụ cuối cùng. Lựa chọn một API phù hợp là bước triển khai; yêu cầu bảo mật phải mô tả cả những gì caller được điều khiển, những gì server giữ quyền quyết định và cách xác minh ranh giới này.
