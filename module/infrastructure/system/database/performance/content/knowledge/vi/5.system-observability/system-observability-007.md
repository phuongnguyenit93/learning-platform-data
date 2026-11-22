# Ẩn dữ liệu nhạy cảm trong câu SQL, tham số và bản ghi chẩn đoán

Quan sát hiệu năng cơ sở dữ liệu cần đủ thông tin để xác định truy vấn chậm, giao dịch lỗi, tranh chấp khóa và nút thắt tài nguyên. Tuy nhiên, câu SQL, giá trị tham số và thông báo lỗi đôi khi chứa email, số điện thoại, địa chỉ, mã khách hàng, dữ liệu tài chính, token xác thực hoặc bí mật kết nối. Nếu những giá trị này xuất hiện trong log, trace, công cụ APM hay bản ghi truy vấn chậm, hệ thống quan sát có thể trở thành một nơi làm lộ dữ liệu.

Trong module **DATABASE_PERFORMANCE**, việc ẩn dữ liệu nhạy cảm là một phần của thiết kế khả năng quan sát. Mục tiêu là giữ lại thông tin cần thiết để phân tích hiệu năng và độ tin cậy, đồng thời giảm tối đa dữ liệu có thể nhận diện người dùng hoặc cấp quyền truy cập. Cần thực hiện điều này xuyên suốt từ ứng dụng, driver cơ sở dữ liệu và máy chủ cơ sở dữ liệu đến hệ thống thu thập, lưu trữ và xuất log.

## 1. Nhận diện dữ liệu nhạy cảm trong hoạt động truy cập cơ sở dữ liệu

Dữ liệu nhạy cảm không chỉ nằm trong các cột có tên dễ nhận biết như `email` hay `phone`. Nó có thể xuất hiện trong câu SQL được ghép chuỗi, giá trị bind parameter, điều kiện lọc, thông báo ngoại lệ, comment của câu truy vấn, thuộc tính trace hoặc thông tin kết nối.

| Vị trí | Ví dụ dữ liệu có thể bị lộ | Rủi ro |
|---|---|---|
| Câu SQL chứa literal | Email, số tài khoản, mã đơn hàng, tên người dùng | Log câu lệnh có thể lưu nguyên giá trị nghiệp vụ |
| Bind parameter | Mật khẩu, token, số thẻ, số điện thoại, địa chỉ | Công cụ debug hoặc driver có thể ghi lại giá trị tham số |
| Thông báo lỗi | Giá trị đầu vào không hợp lệ, nội dung bản ghi, câu SQL đầy đủ | Ngoại lệ có thể đưa dữ liệu vào log ứng dụng hoặc hệ thống theo dõi lỗi |
| Connection string | Mật khẩu, token, tên máy chủ nội bộ, thông tin định danh | Log cấu hình có thể làm lộ thông tin truy cập và cấu trúc mạng |
| Trace và thuộc tính APM | User ID, session ID, câu SQL, tham số, request body | Dữ liệu có thể được sao chép sang nhiều nền tảng quan sát |
| SQL comment và nhãn truy vấn | ID người dùng, mã yêu cầu có thể liên kết danh tính | Nội dung comment có thể xuất hiện trong log máy chủ hoặc công cụ phân tích |
| Kế hoạch thực thi và bản ghi chẩn đoán | Literal, tên bảng/cột nhạy cảm, cấu trúc nội bộ | Có thể tiết lộ dữ liệu hoặc thông tin kiến trúc ngoài phạm vi cần thiết |

Hãy phân loại dữ liệu trước khi quyết định cách ghi nhận. Một chính sách thường chia thành các nhóm sau:

- **Bí mật xác thực:** mật khẩu, access token, refresh token, API key, khóa mã hóa và chuỗi kết nối có thông tin xác thực. Không ghi giá trị thô vào log.
- **Dữ liệu nhận diện cá nhân:** họ tên, email, số điện thoại, địa chỉ, định danh cá nhân hoặc mã có thể liên kết đến một người.
- **Dữ liệu tài chính và nghiệp vụ hạn chế:** số tài khoản, dữ liệu thanh toán, giá trị giao dịch hoặc thông tin hợp đồng tùy phạm vi hệ thống.
- **Dữ liệu nhạy cảm theo miền:** hồ sơ sức khỏe, dữ liệu nhân sự hoặc dữ liệu khác có yêu cầu bảo vệ riêng.
- **Thông tin vận hành nội bộ:** địa chỉ máy chủ, tên schema, cấu trúc bảng, thông tin tenant và định danh nội bộ có thể hỗ trợ việc dò tìm hệ thống.

Không nên chỉ dựa vào tên cột để nhận diện. Một cột `value`, `payload`, `metadata` hoặc `reference` vẫn có thể chứa dữ liệu nhạy cảm. Cần hiểu ngữ nghĩa của dữ liệu và đường đi của nó qua các thành phần.

## 2. Phân biệt câu SQL, tham số và bản ghi quan sát

Một truy vấn thường có ba phần cần xem xét riêng:

1. **Mẫu câu SQL:** cấu trúc lệnh và placeholder, ví dụ `WHERE customer_id = ?`.
2. **Giá trị tham số:** giá trị thực được truyền cho placeholder khi thực thi.
3. **Bản ghi quan sát:** dữ liệu được ghi lại để theo dõi lần thực thi, ví dụ mã truy vấn, thời gian, số hàng trả về, trạng thái lỗi và thông tin tham số.

Việc dùng prepared statement giúp tách cấu trúc SQL khỏi dữ liệu đầu vào và giảm nguy cơ SQL injection. Nhưng prepared statement **không tự động bảo đảm tham số được ẩn trong log**. Driver, thư viện truy cập dữ liệu, proxy, công cụ APM hoặc cấu hình log của máy chủ vẫn có thể ghi lại giá trị bind parameter.

Ví dụ, mẫu truy vấn sau không chứa email cụ thể:

```sql
SELECT customer_id, status
FROM customer
WHERE email = ?;
```

Khi chạy, ứng dụng có thể truyền `person@example.test` vào vị trí tham số. Nếu log chỉ lưu mẫu SQL và mã truy vấn, dữ liệu nhận diện được giữ ngoài log. Nếu bật chế độ ghi toàn bộ bind value, email vẫn có thể bị lưu dù câu SQL dùng placeholder.

Ngược lại, cách ghép giá trị trực tiếp vào câu lệnh làm dữ liệu xuất hiện ngay trong chuỗi SQL:

```java
// Không nên: giá trị đầu vào trở thành một phần của chuỗi SQL.
String sql = "SELECT customer_id FROM customer WHERE email = '" + email + "'";
```

Ngoài rủi ro injection, cách viết này khiến câu SQL được ghi lại có thể chứa dữ liệu thật. Hãy dùng tham số hóa và áp dụng chính sách log riêng cho tham số.

## 3. Nguyên tắc thiết kế chính sách che giấu

### Thu thập tối thiểu theo mục đích

Trước khi ghi một trường dữ liệu, hãy hỏi nó giúp trả lời câu hỏi vận hành nào. Để xác định truy vấn chậm, thường cần mã truy vấn, mẫu SQL, thời gian thực thi, số hàng đọc hoặc trả về, trạng thái lỗi, số lần thực thi và thời điểm. Thường không cần email, số điện thoại hay toàn bộ nội dung bản ghi.

Ưu tiên **allowlist**: chỉ cho phép các trường đã được xác định là an toàn và có mục đích rõ ràng. Cách này dễ kiểm soát hơn denylist, vì dữ liệu mới có thể xuất hiện trong payload mà danh sách cấm chưa biết đến.

Một bản ghi sự kiện tối thiểu có thể gồm:

```json
{
  "event": "db.query.completed",
  "query_id": "customer.lookup",
  "duration_ms": 84,
  "rows_returned": 1,
  "parameter_count": 1,
  "parameter_types": ["STRING"],
  "outcome": "success"
}
```

Bản ghi trên cung cấp thông tin để nhóm vận hành tìm mẫu truy vấn và đánh giá thời gian thực thi mà không cần ghi giá trị email được truyền vào.

### Che giấu trước khi ghi và xuất dữ liệu

Việc lọc nên diễn ra ở nguồn phát sinh log, trước khi dữ liệu được serialize, ghi xuống đĩa hoặc gửi qua mạng. Nếu chỉ che ở giao diện dashboard, giá trị thô vẫn có thể tồn tại trong log gốc, bản sao lưu, hàng đợi hoặc nền tảng APM.

Luồng xử lý nên theo thứ tự:

1. Xác định mẫu sự kiện và phân loại trường dữ liệu.
2. Loại bỏ hoặc biến đổi trường nhạy cảm ở ứng dụng, driver hay thành phần phát log.
3. Kiểm tra bản ghi sau biến đổi bằng quy tắc cho phép.
4. Ghi hoặc gửi bản ghi đã được làm sạch đến hệ thống quan sát.
5. Áp dụng quyền truy cập, thời hạn lưu trữ và kiểm soát xuất dữ liệu.

Nếu không xác định được trường có an toàn hay không, chính sách nên bỏ trường đó hoặc thay bằng thông tin tổng quát. Không nên mặc định ghi dữ liệu thô khi bộ lọc gặp lỗi.

### Không nhầm che giấu với mã hóa

Mã hóa ổ đĩa hoặc mã hóa đường truyền bảo vệ dữ liệu khi lưu trữ và truyền tải, nhưng người có quyền đọc log vẫn có thể thấy nội dung sau khi hệ thống giải mã. Che giấu dữ liệu làm giảm lượng thông tin nhạy cảm được ghi ngay từ đầu. Hai biện pháp bổ trợ cho nhau và không thay thế nhau.

## 4. Chọn cách xử lý giá trị nhạy cảm

Không có một kỹ thuật phù hợp cho mọi loại dữ liệu. Hãy chọn dựa trên mục đích phân tích và mức độ nhạy cảm.

| Kỹ thuật | Cách hoạt động | Khi phù hợp | Giới hạn cần lưu ý |
|---|---|---|---|
| Loại bỏ (*omit*) | Không ghi trường hoặc giá trị | Bí mật, token, mật khẩu, nội dung không cần cho chẩn đoán | Không thể truy vấn lại theo giá trị đã loại bỏ |
| Che một phần (*mask*) | Thay một phần bằng ký tự che | Giao diện hỗ trợ vận hành cần nhận biết định dạng ở mức hạn chế | Phần còn lộ vẫn có thể đủ để nhận diện hoặc suy đoán |
| Thay bằng nhãn cố định | Ghi `REDACTED` hoặc kiểu dữ liệu thay cho giá trị | Log cần thể hiện vị trí có tham số nhưng không cần nội dung | Không hỗ trợ liên kết cùng một thực thể qua nhiều sự kiện |
| Giả danh bằng HMAC | Tạo mã ổn định bằng khóa bí mật tách biệt | Cần liên kết các sự kiện của cùng một thực thể trong phạm vi kiểm soát | Vẫn là dữ liệu có thể liên kết; cần bảo vệ khóa và giới hạn mục đích |
| Tổng hợp hoặc phân nhóm | Ghi số lượng, kiểu, độ dài theo khoảng hoặc nhóm giá trị | Phân tích tải, kích thước tham số và hành vi truy vấn | Không giữ được chi tiết của từng bản ghi |

Với mật khẩu, token và khóa bí mật, lựa chọn an toàn là không ghi giá trị. Che một phần hoặc băm cũng không cần thiết cho mục tiêu chẩn đoán và có thể tạo cảm giác an toàn sai.

Với định danh cần liên kết giữa nhiều sự kiện, có thể dùng HMAC với khóa được quản lý riêng. Không nên dùng SHA-256 đơn thuần cho email, số điện thoại hoặc giá trị có không gian đoán nhỏ: người có bản băm có thể thử danh sách giá trị phổ biến để tìm lại dữ liệu. HMAC giảm khả năng dò ngoại tuyến nếu khóa được giữ bí mật, nhưng kết quả vẫn có thể liên kết các hoạt động với nhau và cần được bảo vệ như dữ liệu giả danh.

Nếu chỉ cần phân tích tải, thay giá trị cụ thể bằng kiểu dữ liệu, số lượng tham số, trạng thái null hoặc nhóm kích thước thường đã đủ. Ví dụ, ghi `STRING`, `length_bucket=16-32` hoặc `is_null=false` thay vì ghi chuỗi thực.

## 5. Ghi nhận truy vấn an toàn trong ứng dụng Java

### Dùng prepared statement và log metadata

Ví dụ sau dùng JDBC để truyền tham số riêng khỏi câu SQL. Log chỉ ghi mã truy vấn, thời gian và loại tham số, không ghi email:

```java
String queryId = "customer.lookup";
String sql = "SELECT customer_id, status "
        + "FROM customer WHERE email = ?";

long startedAt = System.nanoTime();
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);

    try (ResultSet resultSet = statement.executeQuery()) {
        // Xử lý kết quả nghiệp vụ.
    }

    long durationMs = (System.nanoTime() - startedAt) / 1_000_000;
    logger.debug(
            "db.query.completed queryId={} durationMs={} parameterTypes={}",
            queryId, durationMs, "[STRING]");
} catch (SQLException exception) {
    long durationMs = (System.nanoTime() - startedAt) / 1_000_000;
    logger.warn(
            "db.query.failed queryId={} durationMs={} sqlState={} errorType={}",
            queryId, durationMs, exception.getSQLState(),
            exception.getClass().getSimpleName());
    throw exception;
}
```

Ví dụ chỉ minh họa cách ghi nhận metadata. Trong ứng dụng thực tế, cần bảo đảm logger, interceptor JDBC và thư viện APM không tự động ghi giá trị bind parameter hoặc nội dung ngoại lệ đầy đủ ở một nơi khác.

### Tránh ghi trực tiếp đối tượng tham số

Các cách ghi sau có thể làm lộ dữ liệu:

```java
// Không nên: mảng tham số có thể chứa dữ liệu cá nhân hoặc bí mật.
logger.debug("SQL parameters: {}", parameters);

// Không nên: thông báo lỗi có thể chứa SQL hoặc giá trị đầu vào.
logger.error("Database query failed: {}", exception.getMessage());

// Không nên: chuỗi kết nối có thể chứa tên người dùng và mật khẩu.
logger.info("Connecting with URL: {}", jdbcUrl);
```

Hãy ghi mã lỗi, SQLState, loại ngoại lệ, mã truy vấn và thời gian xử lý. Nếu cần thông tin bổ sung, lấy từ trường đã được kiểm soát hoặc dùng thông báo lỗi đã làm sạch. Không đưa toàn bộ đối tượng request, entity hoặc map tham số vào logger theo cách tổng quát.

### Kiểm soát SQL động

Prepared statement tham số hóa giá trị, nhưng không phải mọi thành phần SQL đều có thể thay bằng placeholder. Tên bảng, tên cột, từ khóa `ORDER BY` hoặc hướng sắp xếp thường cần được chọn từ danh sách cho phép. Không ghép trực tiếp một chuỗi tùy ý từ người dùng vào câu lệnh.

```java
// Chỉ chọn identifier từ danh sách cố định trong chương trình.
String orderColumn = switch (requestedSort) {
    case "created" -> "created_at";
    case "status" -> "status";
    default -> "created_at";
};

String sql = "SELECT id, status FROM orders ORDER BY " + orderColumn;
```

Các lựa chọn được kiểm soát giúp câu SQL có hình dạng dự đoán được và tránh đưa dữ liệu tùy ý vào phần cấu trúc. Không ghi giá trị đầu vào ban đầu trong log lỗi khi lựa chọn không hợp lệ.

## 6. Bảo vệ log truy vấn chậm, audit log và kế hoạch thực thi

Ẩn dữ liệu ở logger ứng dụng là chưa đủ. Hệ quản trị cơ sở dữ liệu có thể cung cấp slow query log, general query log, audit log, lịch sử truy vấn, thống kê câu lệnh hoặc tiện ích chẩn đoán. Mỗi nguồn có thể ghi SQL text, literal, bind parameter hoặc thông tin phiên.

Khi cấu hình các nguồn này, cần xem xét:

- Chỉ bật loại log cần cho mục tiêu chẩn đoán và trong phạm vi thời gian phù hợp.
- Kiểm tra tùy chọn ghi tham số bind; tắt việc ghi giá trị thô nếu không có nhu cầu đã được phê duyệt.
- Ưu tiên fingerprint hoặc mẫu SQL đã chuẩn hóa, thay vì lưu câu lệnh chứa literal.
- Kiểm tra log lỗi, log audit và log truy vấn chậm riêng biệt; mỗi loại có thể có quy tắc ghi dữ liệu khác nhau.
- Giới hạn quyền đọc log theo vai trò vận hành và nhu cầu xử lý sự cố.
- Đặt thời hạn lưu trữ và quy trình xóa bản sao, bản xuất hoặc dữ liệu trong hệ thống phân tích.

Kế hoạch thực thi thường hữu ích để xem loại truy cập, thứ tự join, chỉ mục được chọn, ước lượng số hàng và chi phí. Tuy vậy, kế hoạch có thể chứa literal hoặc tên đối tượng nội bộ tùy hệ quản trị và cách thu thập. Hãy kiểm tra nội dung thực tế trước khi gửi kế hoạch đến dịch vụ bên ngoài. Khi phân tích hiệu năng, thường có thể thay literal bằng placeholder và giữ lại cấu trúc kế hoạch cần thiết.

Không nên bật chế độ debug ghi mọi câu SQL và tham số trên môi trường production trong thời gian dài. Nếu cần điều tra một sự cố cụ thể, hãy giới hạn phạm vi, thời gian, quyền truy cập và dữ liệu được thu thập; sau khi hoàn tất, tắt cấu hình tạm thời và xử lý các bản ghi theo chính sách lưu trữ.

## 7. Bảo vệ trace, metric và thông tin tương quan

### Trace và span

Trace thường mang theo thuộc tính như tên thao tác, câu SQL, database name, user ID, session ID và request ID. Không đưa toàn bộ request hoặc tham số truy vấn vào thuộc tính span. Hãy ưu tiên:

- Tên thao tác hoặc mã truy vấn ổn định, ví dụ `customer.lookup`.
- Loại cơ sở dữ liệu, trạng thái thành công/thất bại và thời gian thực thi.
- Số hàng trả về hoặc số hàng bị ảnh hưởng khi phù hợp.
- SQL fingerprint đã chuẩn hóa, nếu cần tìm nhóm truy vấn.
- Mã tương quan ngẫu nhiên, không chứa email, số điện thoại hoặc định danh có thể đoán.

Một trace ID ngẫu nhiên có thể giúp nối các sự kiện trong một yêu cầu mà không cần ghi danh tính người dùng. Tuy nhiên, nếu hệ thống lưu bảng ánh xạ trace ID sang người dùng ở nơi khác, quyền truy cập bảng ánh xạ vẫn cần được kiểm soát.

### Metric và nhãn có cardinality cao

Metric nên dùng nhãn có tập giá trị giới hạn như `operation`, `database_role`, `outcome` hoặc `query_group`. Không dùng email, user ID, order ID, session ID hoặc SQL text làm nhãn metric. Các giá trị duy nhất theo từng yêu cầu vừa có thể tiết lộ dữ liệu vừa làm cardinality tăng mạnh, gây tốn bộ nhớ và giảm hiệu quả của hệ thống giám sát.

Ví dụ, metric sau có nhãn ổn định:

```text
db_query_duration_seconds{operation="customer.lookup",outcome="success"}
```

Tránh tạo metric dạng:

```text
db_query_duration_seconds{email="person@example.test"}
```

### Comment trong câu SQL

Một số hệ thống thêm comment vào SQL để gắn mã dịch vụ, tên tác vụ hoặc trace ID. Đây là cách hữu ích để liên kết log ứng dụng với hoạt động ở máy chủ cơ sở dữ liệu, nhưng comment có thể được lưu trong log truy vấn. Chỉ đưa metadata đã được duyệt, có độ dài giới hạn và không chứa thông tin người dùng hoặc bí mật. Không thêm toàn bộ URL, request header hoặc payload vào comment.

## 8. Kiểm soát lỗi, ngoại lệ và cấu hình chẩn đoán

Thông báo ngoại lệ từ driver hoặc hệ quản trị có thể chứa câu SQL, tên bảng, dữ liệu đầu vào hoặc thông tin kết nối. Không giả định rằng `getMessage()` luôn an toàn để ghi. Hãy phân tách thông tin dành cho vận hành với thông tin dành cho người dùng:

| Đối tượng | Thông tin phù hợp |
|---|---|
| Log vận hành | mã truy vấn, SQLState, loại lỗi, thời gian, trace ID và thông tin đã làm sạch |
| Phản hồi cho người dùng | thông báo tổng quát, mã lỗi có thể tra cứu, không kèm SQL hoặc chi tiết nội bộ |
| Kênh điều tra hạn chế | chi tiết bổ sung đã được kiểm soát, chỉ khi cần thiết và có quyền truy cập phù hợp |

Không trả câu SQL, stack trace hoặc thông báo lỗi nguyên gốc cho client. Không ghi nguyên cấu hình kết nối khi khởi động ứng dụng. Nếu cần xác nhận cấu hình, chỉ ghi tên môi trường, loại kết nối, trạng thái thành công và mã cấu hình không nhạy cảm.

Cần kiểm tra cả những đường ghi gián tiếp: interceptor ORM, JDBC proxy, thư viện retry, bộ thu thập telemetry, công cụ giám sát lỗi, crash report và bản dump hỗ trợ. Một lớp đã che dữ liệu không có nghĩa các lớp khác cũng đã che.

## 9. Kiểm thử chính sách che giấu

Chính sách chỉ đáng tin khi được kiểm thử bằng dữ liệu giả lập có thể nhận diện rõ. Tạo bộ dữ liệu kiểm thử chứa các chuỗi canary giả như `TEST_EMAIL_7F3A`, `TEST_TOKEN_9C2D` hoặc số tài khoản giả. Chạy các luồng đọc, ghi, lỗi, timeout và retry; sau đó tìm các chuỗi canary trong mọi đầu ra quan sát.

Một quy trình kiểm thử có thể thực hiện như sau:

1. Lập danh sách nguồn log và telemetry: ứng dụng, driver, ORM, máy chủ cơ sở dữ liệu, proxy, APM, tracing, metric và hệ thống báo lỗi.
2. Xác định trường được phép, trường phải bỏ và trường cần biến đổi cho từng loại sự kiện.
3. Chạy truy vấn thành công có tham số nhạy cảm giả lập.
4. Tạo lỗi cú pháp, lỗi ràng buộc, timeout, rollback và lỗi kết nối để kiểm tra thông báo ngoại lệ.
5. Kiểm tra slow query log, audit log, trace span, metric label, log ứng dụng và dữ liệu đã xuất.
6. Tìm chuỗi canary và xác nhận không có giá trị thô xuất hiện ở bất kỳ đích nào.
7. Kiểm tra trường hợp bộ lọc lỗi hoặc không nhận diện được payload; hệ thống phải bỏ trường không an toàn hoặc từ chối ghi sự kiện đó.
8. Lặp lại khi nâng cấp driver, ORM, agent APM, cấu hình cơ sở dữ liệu hoặc thay đổi schema.

Ví dụ kiểm tra tự động có thể xác nhận rằng bản ghi log không chứa chuỗi canary:

```java
String canary = "TEST_TOKEN_9C2D";
String logEvent = captureDatabaseLogEvent(canary);

if (logEvent.contains(canary)) {
    throw new AssertionError("Sensitive test value leaked into log");
}
```

Đây là kiểm tra minh họa. Bộ kiểm thử đầy đủ nên kiểm tra mọi sink và mọi loại sự kiện, bao gồm log được tạo ở tầng driver hoặc máy chủ, chứ không chỉ logger của ứng dụng.

## 10. Quyền truy cập, lưu trữ và xử lý sự cố lộ dữ liệu

Log sau khi làm sạch vẫn có thể chứa metadata nội bộ và mã giả danh. Vì vậy, cần bảo vệ hệ thống quan sát bằng các biện pháp vận hành:

- Cấp quyền đọc log theo vai trò và nguyên tắc quyền tối thiểu.
- Tách quyền quản trị pipeline, quyền xem log và quyền xuất dữ liệu.
- Mã hóa đường truyền và nơi lưu trữ log; quản lý khóa riêng với dữ liệu.
- Ghi audit cho thao tác tìm kiếm, tải xuống, chia sẻ và thay đổi cấu hình log.
- Giới hạn thời gian lưu theo mục đích; xóa dữ liệu khỏi cả bản sao và nơi lưu trữ phụ theo quy trình.
- Kiểm soát môi trường phát triển và kiểm thử để log không vô tình được sao chép từ production.

Nếu phát hiện dữ liệu nhạy cảm đã đi vào log, cần xác định loại dữ liệu, khoảng thời gian, hệ thống nhận dữ liệu và nhóm người có quyền truy cập. Tạm dừng nguồn ghi gây lộ hoặc áp dụng cấu hình che giấu, hạn chế truy cập các bản ghi liên quan, đánh giá bản sao và bản xuất, rồi xử lý xóa hoặc lưu giữ theo quy trình ứng phó của tổ chức. Nếu dữ liệu lộ là thông tin xác thực, cần đánh giá việc thu hồi hoặc xoay vòng thông tin đó. Không nên chỉ sửa dashboard rồi coi sự cố đã được xử lý.

## 11. Những sai lầm thường gặp

1. **Cho rằng prepared statement tự che tham số:** driver hoặc APM vẫn có thể ghi bind value.
2. **Chỉ che ở giao diện:** dữ liệu thô còn trong log gốc, hàng đợi hoặc bản sao lưu.
3. **Ghi toàn bộ đối tượng để debug:** entity, request hoặc map tham số có thể chứa nhiều trường nhạy cảm ngoài dự kiến.
4. **Ghi nguyên thông báo ngoại lệ:** nội dung lỗi có thể chứa SQL, literal hoặc dữ liệu đầu vào.
5. **Dùng hash không khóa cho dữ liệu dễ đoán:** email và số điện thoại có thể bị dò bằng từ điển.
6. **Đưa định danh vào metric label:** vừa làm tăng cardinality vừa tạo thêm nơi lưu dữ liệu nhận diện.
7. **Bật log chi tiết vô thời hạn:** chế độ debug có thể làm tăng chi phí, dung lượng và nguy cơ lộ dữ liệu.
8. **Không kiểm tra nguồn log của máy chủ:** cấu hình ứng dụng an toàn không bảo đảm slow query log hoặc audit log an toàn.
9. **Không kiểm thử đường lỗi:** dữ liệu có thể chỉ bị lộ khi timeout, rollback hoặc phát sinh exception.
10. **Coi dữ liệu giả danh là dữ liệu vô danh:** mã ổn định vẫn có thể liên kết các sự kiện và cần được bảo vệ.

## 12. Danh sách kiểm tra trước khi triển khai

- [ ] Đã phân loại dữ liệu nhạy cảm có thể xuất hiện trong SQL, tham số, lỗi và metadata.
- [ ] Đã xác định allowlist trường an toàn cho từng loại log và trace.
- [ ] Đã dùng prepared statement cho giá trị đầu vào và allowlist cho thành phần SQL động.
- [ ] Đã ngăn logger ghi đối tượng tham số, request, entity hoặc thông báo lỗi nguyên gốc.
- [ ] Đã kiểm tra cấu hình bind parameter, slow query log, audit log và công cụ APM.
- [ ] Đã loại định danh cá nhân và SQL text khỏi metric label.
- [ ] Đã áp dụng che giấu tại nguồn trước khi ghi hoặc gửi telemetry.
- [ ] Đã đặt quyền truy cập, mã hóa, audit và thời hạn lưu trữ cho log.
- [ ] Đã kiểm thử bằng canary giả lập trên cả luồng thành công và luồng lỗi.
- [ ] Đã kiểm tra log sau khi nâng cấp driver, ORM, agent hoặc cấu hình cơ sở dữ liệu.

Ẩn dữ liệu nhạy cảm trong câu SQL, tham số và bản ghi chẩn đoán giúp nhóm vận hành duy trì khả năng quan sát mà không thu thập quá mức dữ liệu người dùng. Hãy ghi mẫu truy vấn và metadata phục vụ đo đạc, bỏ hoặc biến đổi giá trị nhạy cảm ngay tại nguồn, kiểm soát mọi đích nhận telemetry và kiểm thử cả đường thành công lẫn đường lỗi. Khi được thực hiện nhất quán, log vẫn hỗ trợ tìm truy vấn chậm, phân tích lỗi và theo dõi tải mà giảm đáng kể nguy cơ dữ liệu bị lộ qua hệ thống giám sát.
