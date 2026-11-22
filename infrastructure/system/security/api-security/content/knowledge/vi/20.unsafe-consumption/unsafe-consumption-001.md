# API10: Unsafe Consumption of APIs

API thường phải gọi đến hệ thống bên ngoài để lấy thông tin thanh toán, vận chuyển, định danh, bản đồ, email, dữ liệu đối tác hoặc các dịch vụ SaaS. Các API này giúp mở rộng chức năng, nhưng response từ một nhà cung cấp bên ngoài không tự động trở thành dữ liệu đáng tin cậy. Hệ thống đối tác có thể bị xâm nhập, cấu hình sai, thay đổi contract, trả dữ liệu lỗi hoặc bị một bên thứ ba thao túng.

**Unsafe Consumption of APIs** là rủi ro phát sinh khi ứng dụng tiêu thụ API khác mà tin tưởng quá mức vào dữ liệu, hành vi hoặc mức bảo vệ của hệ thống đó. Nhà phát triển có thể kiểm tra dữ liệu do người dùng gửi rất kỹ nhưng lại bỏ qua validation đối với dữ liệu nhận từ API đối tác. Kẻ tấn công khi đó có thể tác động gián tiếp vào ứng dụng thông qua một API bên ngoài, một tài khoản đối tác bị chiếm quyền hoặc một response được tạo sai.

Trong phạm vi bảo mật API theo endpoint, object và workflow, cần coi mỗi lần gọi API khác là một ranh giới tin cậy. Ứng dụng phải xác minh đúng đối tác, bảo vệ credential outbound, giới hạn tài nguyên, kiểm tra response theo contract và chỉ chuyển dữ liệu đã được xác nhận vào nghiệp vụ.

## 1. Hiểu rủi ro Unsafe Consumption of APIs

OWASP API Security Top 10 2023 mô tả API10: Unsafe Consumption of APIs như một nhóm rủi ro khi ứng dụng tiêu thụ API bên thứ ba mà không áp dụng mức kiểm soát phù hợp. Một quan niệm sai phổ biến là API đối tác đáng tin hơn dữ liệu do người dùng gửi, vì nhà cung cấp đã có đội ngũ kỹ thuật và cơ chế bảo mật riêng. Thực tế, hệ thống của đối tác có thể có lỗ hổng, bị chiếm tài khoản, trả dữ liệu không đúng contract hoặc bị tấn công qua chuỗi tích hợp.

Các tình huống thường gặp:

- Ứng dụng dùng trực tiếp giá, trạng thái thanh toán hoặc thông tin người nhận do API đối tác trả về mà không kiểm tra lại.
- Response có trường bất ngờ, kiểu dữ liệu sai, giá trị ngoài khoảng hoặc cấu trúc quá lớn khiến parser và nghiệp vụ xử lý không an toàn.
- Dữ liệu trả về được đưa thẳng vào SQL, shell command, template, HTML hoặc đường dẫn file.
- Ứng dụng tự động theo redirect đến host khác và vô tình gửi credential hoặc truy cập vùng mạng không được phép.
- Client gọi API đối tác không có timeout, giới hạn response, concurrency hoặc retry hợp lý, làm cạn tài nguyên khi upstream chậm hoặc lỗi.
- Ứng dụng tin mã trạng thái 2xx là bằng chứng giao dịch đã hoàn tất, dù response nghiệp vụ mâu thuẫn hoặc không được xác thực.
- Credential dùng chung cho nhiều tích hợp, có scope quá rộng hoặc bị ghi vào log.
- Contract đối tác thay đổi nhưng ứng dụng không có kiểm thử tương thích và giám sát.

### 1.1. Phân biệt lỗi của nhà cung cấp và lỗi tiêu thụ không an toàn

Một API đối tác trả dữ liệu sai không nhất thiết tự nó tạo thành lỗ hổng trong ứng dụng của bạn. Rủi ro xuất hiện khi hệ thống tiêu thụ dữ liệu đó theo cách làm phát sinh hậu quả bảo mật hoặc nghiệp vụ.

Ví dụ, đối tác vận chuyển trả thời gian giao hàng sai. Nếu ứng dụng chỉ hiển thị một dự báo, tác động có thể giới hạn. Nhưng nếu ứng dụng dùng response đó để tự động hoàn tiền, thay đổi trạng thái đơn hoặc xác nhận đã giao hàng, dữ liệu sai có thể tạo hậu quả tài chính. Cùng một response, mức rủi ro phụ thuộc vào cách ứng dụng sử dụng nó.

### 1.2. Những thành phần cần bảo vệ

| Thành phần | Rủi ro nếu tiêu thụ không an toàn |
|---|---|
| Dữ liệu nghiệp vụ | Giá, số tiền, trạng thái, chủ sở hữu hoặc quyền lợi bị thay đổi |
| Danh tính và quyền | Token, role hoặc thông tin người dùng bị tin sai |
| Tài nguyên ứng dụng | CPU, heap, thread, connection pool và queue bị tiêu thụ quá mức |
| Hệ thống nội bộ | Dữ liệu từ response gây injection hoặc kích hoạt truy cập không mong muốn |
| Dữ liệu nhạy cảm | Thông tin cá nhân hoặc bí mật bị ghi log, trả lại hoặc chuyển tiếp |
| Tính sẵn sàng | Upstream chậm, lỗi hoặc retry tạo hiệu ứng dây chuyền |
| Tính toàn vẹn | Trạng thái nội bộ không khớp với hệ thống đối tác |

## 2. Lập danh mục API bên ngoài và trust boundary

Trước khi tích hợp hoặc đánh giá bảo mật, cần biết ứng dụng đang gọi hệ thống nào, vì mục đích gì và dữ liệu đi qua ranh giới nào. Danh mục không chỉ gồm nhà cung cấp Internet; các service nội bộ, SaaS, API đối tác, hệ thống thanh toán và dịch vụ do nhóm khác vận hành cũng có thể là dependency cần đánh giá.

Với mỗi tích hợp, ghi nhận:

- Tên nhà cung cấp, chủ sở hữu nội bộ và đầu mối xử lý sự cố.
- Base URL, môi trường và các hostname được phép.
- Endpoint, HTTP method và chức năng nghiệp vụ được sử dụng.
- Dữ liệu gửi đi và dữ liệu nhận về, bao gồm dữ liệu cá nhân hoặc tài chính.
- Cơ chế xác thực, scope, audience, credential và quy trình xoay vòng.
- Contract/schema, phiên bản API và chính sách tương thích.
- Timeout, response size, rate limit, quota và concurrency.
- Retry, redirect, webhook/callback và cách xử lý lỗi.
- Hệ thống nội bộ hoặc workflow phụ thuộc vào response.

### 2.1. Vẽ luồng dữ liệu outbound

Một luồng tích hợp điển hình:

~~~mermaid
flowchart TD
    A[Client request] --> B[Authenticate caller]
    B --> C[Authorize function and object]
    C --> D[Build outbound request from trusted config]
    D --> E[Authenticate partner connection]
    E --> F[Receive bounded response]
    F --> G[Validate status, content type and schema]
    G --> H[Validate business invariants]
    H --> I[Map external DTO to internal domain model]
    I --> J[Apply business transition and audit]
~~~

Ở từng bước, xác định dữ liệu nào đến từ client, dữ liệu nào đến từ nhà cung cấp và dữ liệu nào được tạo bởi hệ thống nội bộ. Không để một giá trị chưa xác minh từ response được dùng làm bằng chứng về danh tính, quyền truy cập, tenant hoặc kết quả tài chính.

### 2.2. Đánh giá mức độ tin cậy của nhà cung cấp

Đánh giá nhà cung cấp cần dựa trên mục đích và tác động tích hợp:

- Có tài liệu contract và quy trình thông báo thay đổi không?
- Có hỗ trợ TLS, xác thực mạnh, credential rotation và audit không?
- Có cam kết về availability, rate limit và incident notification không?
- Dữ liệu được lưu, xử lý và chia sẻ ở đâu?
- Có môi trường sandbox hoặc test để xác minh tích hợp không?
- Có cơ chế ký response, webhook hoặc đối soát khi workflow yêu cầu không?
- Có thể tạm ngắt tích hợp hoặc chuyển sang chế độ an toàn khi có sự cố không?

Đánh giá nhà cung cấp không thay thế validation tại consumer. Dù đối tác có chứng nhận hoặc SLA tốt, ứng dụng vẫn phải kiểm tra dữ liệu nhận được trước khi sử dụng.

## 3. Bảo vệ kết nối và xác thực outbound

### 3.1. Sử dụng TLS đúng cách

Kết nối đến API đối tác cần dùng HTTPS với kiểm tra chứng thư và hostname. Không tắt certificate validation hoặc hostname verification chỉ để xử lý lỗi môi trường. Nếu nhà cung cấp sử dụng private CA, hãy cài đặt trust chain phù hợp và quản lý việc cập nhật CA có kiểm soát.

TLS bảo vệ dữ liệu trên đường truyền và giúp xác minh máy chủ theo trust store; TLS không chứng minh response đúng nghiệp vụ hoặc không bị tạo sai từ chính hệ thống đối tác. Vì vậy, vẫn cần xác thực ứng dụng, validation response và kiểm soát workflow.

### 3.2. Chọn cơ chế xác thực phù hợp

Tùy nhà cung cấp, có thể dùng OAuth 2.0 client credentials, mTLS, API key hoặc chữ ký request. Cần:

- Tạo identity riêng cho từng tích hợp và từng môi trường.
- Chỉ cấp scope/permission tối thiểu cần thiết.
- Giới hạn audience và endpoint mà credential được phép gọi.
- Xoay vòng, thu hồi và theo dõi credential.
- Không nhúng secret trong mã nguồn, container image, URL hoặc log.
- Không dùng một API key quản trị chung cho mọi dịch vụ.

Không gửi access token của người dùng đến API đối tác chỉ vì ứng dụng đang có token đó. Nếu cần gọi thay mặt người dùng, dùng cơ chế delegation hoặc token exchange được thiết kế rõ ràng; giới hạn audience và scope theo mục đích. Việc chuyển tiếp token tùy tiện có thể làm lộ credential hoặc cấp quyền rộng hơn dự kiến.

### 3.3. Không đặt credential trong URL

Tránh truyền API key hoặc token trong query string. URL thường xuất hiện trong access log, proxy log, lịch sử trình duyệt, trace và thông báo lỗi. Ưu tiên header xác thực theo contract của nhà cung cấp, dùng TLS và lọc credential khỏi log.

Ví dụ header:

~~~http
Authorization: Bearer <short-lived-access-token>
Accept: application/json
~~~

Giá trị placeholder chỉ minh họa vị trí truyền token; không ghi token thật vào source code hoặc tài liệu.

### 3.4. Giới hạn endpoint và redirect

Base URL của tích hợp nên đến từ cấu hình được quản lý, không lấy trực tiếp từ response đối tác hoặc input tùy ý của người dùng. Chỉ cho phép hostname và scheme đã phê duyệt. Nếu client HTTP tự động follow redirect, một response 302 có thể chuyển request sang host khác.

Với tích hợp nhạy cảm, nên tắt automatic redirect hoặc kiểm tra từng redirect theo allowlist. Không chuyển Authorization header sang host khác. Nếu nghiệp vụ cần redirect, xác minh scheme, hostname, port và địa chỉ đích theo chính sách; đồng thời cân nhắc DNS rebinding và việc phân giải lại tên miền.

Kiểm soát này cũng giúp giảm nguy cơ SSRF. Nếu ứng dụng có chức năng gọi URL do người dùng cung cấp, phải áp dụng thiết kế SSRF riêng: allowlist đích, chặn địa chỉ loopback/private/link-local và metadata, kiểm tra DNS/IP sau phân giải, kiểm soát redirect và giới hạn response. Không coi việc URL bắt đầu bằng một hostname hợp lệ là đủ.

## 4. Xác minh response trước khi dùng

Một response HTTP 200 chỉ cho biết tầng HTTP trả về thành công theo giao thức. Nó không chứng minh dữ liệu đúng schema, đúng tenant, đúng chủ thể hoặc hợp lệ với nghiệp vụ.

### 4.1. Kiểm tra status code và Content-Type

Consumer cần xác định rõ status code nào được chấp nhận cho từng operation. Không coi mọi mã 2xx là cùng một kết quả. Ví dụ 202 Accepted có thể chỉ có nghĩa yêu cầu đã được nhận để xử lý; 204 No Content không có body; 206 Partial Content có thể chỉ trả một phần dữ liệu.

Kiểm tra Content-Type đúng với contract, chẳng hạn application/json. Không cố parse HTML error page hoặc nội dung tùy ý như JSON chỉ vì request mong đợi JSON. Nếu API hỗ trợ nhiều định dạng, chỉ bật parser cho những định dạng được công bố.

### 4.2. Kiểm tra cấu trúc và kiểu dữ liệu

Response nên được parse vào DTO chuyên biệt thay vì bind trực tiếp vào entity/domain object. Xác minh:

- Trường bắt buộc có mặt và không null khi contract yêu cầu.
- Kiểu dữ liệu đúng; không tự động chuyển chuỗi thành số hoặc boolean ngoài dự kiến.
- Chuỗi, số, mảng và object nằm trong giới hạn.
- Enum thuộc tập giá trị được hỗ trợ.
- Timestamp, timezone, currency và đơn vị đo được hiểu đúng.
- ID và reference có định dạng phù hợp.
- Không có cấu trúc lồng nhau hoặc số lượng phần tử vượt giới hạn.

Chính sách với field không biết cần được quyết định theo contract. Có thể bỏ qua field mở rộng vô hại để tương thích với thay đổi bổ sung, nhưng không được để field lạ tự bind vào quyền, trạng thái, owner hoặc thuộc tính nhạy cảm. Với trường có ý nghĩa bảo mật, cần kiểm tra rõ ràng và từ chối dữ liệu mơ hồ.

### 4.3. Kiểm tra ngữ nghĩa nghiệp vụ

Ngay cả response đúng schema vẫn có thể sai nghiệp vụ. Ví dụ:

- Amount âm hoặc vượt hạn mức.
- Currency không khớp với order.
- Payment reference thuộc giao dịch khác.
- Tenant hoặc merchant ID không khớp với request gốc.
- Trạng thái không thể chuyển từ trạng thái hiện tại.
- Thời gian hiệu lực đã hết hoặc timestamp nằm ngoài khoảng hợp lý.
- Một response thông báo thành công nhưng operation ID không khớp với yêu cầu.

Consumer cần kiểm tra các invariant quan trọng trước khi cập nhật trạng thái nội bộ. Với dữ liệu tài chính, nên đối chiếu amount, currency, merchant, transaction ID và trạng thái với operation đã tạo trước đó.

### 4.4. Xác minh nguồn và tính toàn vẹn khi cần

TLS xác minh kết nối đến endpoint, nhưng một số workflow có thể cần bằng chứng mạnh hơn về nguồn response hoặc callback. Ví dụ webhook thanh toán nên xác minh chữ ký theo cơ chế của nhà cung cấp, timestamp, event ID và chống replay. Không chấp nhận callback chỉ vì payload có trường status là paid.

Nếu provider cung cấp chữ ký cho response, kiểm tra chữ ký trên đúng bytes hoặc canonical representation theo tài liệu của họ. Quản lý key rotation và thời gian hiệu lực; không tự thiết kế thuật toán chữ ký riêng nếu nhà cung cấp đã có chuẩn được hỗ trợ.

## 5. Parse và deserialize an toàn

Dữ liệu bên ngoài phải được coi là không tin cậy khi đi vào parser. Một response có thể chứa JSON sâu, mảng lớn, chuỗi rất dài, key trùng lặp hoặc dữ liệu được tạo để kích hoạt lỗi parser.

Các nguyên tắc:

- Giới hạn response bytes trước khi đọc toàn bộ body vào memory.
- Giới hạn kích thước sau giải nén nếu chấp nhận content encoding.
- Giới hạn độ sâu, chiều dài string/number và số token theo khả năng parser.
- Tắt polymorphic default typing hoặc cơ chế cho phép dữ liệu chọn class tùy ý.
- Không deserialize trực tiếp vào class có setter hoặc side effect nhạy cảm.
- Chỉ chấp nhận định dạng cần thiết; cấu hình parser XML an toàn nếu có hỗ trợ XML.
- Không dùng Java native deserialization cho dữ liệu đến từ hệ thống bên ngoài.

### 5.1. Dùng DTO biên giới

DTO bên ngoài chỉ nên chứa những field mà tích hợp cần. Sau khi parse, validate và kiểm tra quan hệ, chuyển đổi sang domain model nội bộ. Điều này ngăn response ngoài hệ thống trực tiếp điều khiển field nội bộ như owner, tenant, role hoặc trạng thái.

Ví dụ DTO:

~~~java
public record PartnerPaymentResponse(
    String transactionId,
    String merchantReference,
    String status,
    BigDecimal amount,
    String currency
) {}
~~~

Sau khi parse, cần kiểm tra transactionId khớp operation đã gửi, merchantReference khớp merchant hiện tại, amount/currency khớp dữ liệu được server tính và status nằm trong tập giá trị được hỗ trợ. Chỉ sau đó mới chuyển thành domain event hoặc cập nhật trạng thái payment.

### 5.2. Ví dụ giới hạn parser Jackson

Với Jackson 2.15 trở lên, có thể cấu hình giới hạn đọc:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(64)
    .maxStringLength(100_000)
    .maxNumberLength(128)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper partnerMapper = JsonMapper.builder(factory)
    .build();
~~~

Các ngưỡng chỉ là ví dụ. Cần xác nhận phiên bản Jackson và bảo đảm mapper này thực sự được dùng cho response của WebClient hoặc HTTP client tương ứng. Parser constraint không thay thế response byte limit, schema validation hoặc business validation.

## 6. Ngăn dữ liệu response gây injection

Dữ liệu từ API đối tác có thể trở thành đầu vào nguy hiểm khi được chuyển đến một sink khác. Việc dữ liệu đến từ một server có thương hiệu không làm cho nó an toàn đối với SQL, shell, HTML hoặc template.

| Sink sử dụng dữ liệu | Rủi ro | Cách xử lý |
|---|---|---|
| SQL/query builder | SQL injection hoặc thay đổi phạm vi truy vấn | Prepared statement, parameter binding và allowlist tên cột/toán tử |
| Shell/process | Command injection | Tránh shell; dùng API tham số riêng và allowlist executable/argument |
| HTML/web UI | XSS hoặc nội dung giả mạo | Contextual output encoding và sanitization theo loại nội dung |
| Template engine | Template injection | Không coi dữ liệu ngoài là template hoặc biểu thức thực thi |
| File path/storage key | Path traversal hoặc ghi đè file | Sinh tên lưu trữ nội bộ, chuẩn hóa và giới hạn thư mục |
| URL/outbound call | SSRF hoặc redirect đến đích không an toàn | Allowlist đích, kiểm tra DNS/IP, scheme, port và redirect |
| Log | Log injection hoặc lộ dữ liệu | Structured logging, giới hạn độ dài, escape và redact |
| HTML email/notification | XSS hoặc nội dung giả mạo | Escape theo ngữ cảnh và kiểm tra template |

### 6.1. Dùng parameterized query

Không nối chuỗi response vào SQL:

~~~java
// Không an toàn: dữ liệu bên ngoài được nối trực tiếp vào câu SQL.
String sql = "SELECT * FROM partner_orders WHERE reference = '" + reference + "'";
~~~

Dùng tham số:

~~~java
String sql = "SELECT * FROM partner_orders WHERE reference = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, reference);
    try (ResultSet result = statement.executeQuery()) {
        // Xử lý kết quả trong phạm vi đã được phân quyền.
    }
}
~~~

Parameter binding bảo vệ giá trị dữ liệu. Nếu response quyết định tên bảng, tên cột hoặc toán tử, các thành phần đó không thể được bảo vệ chỉ bằng bind parameter; cần allowlist ánh xạ từ giá trị hợp lệ sang identifier cố định.

### 6.2. Escape theo ngữ cảnh hiển thị

Nếu response chứa tên, mô tả hoặc nội dung HTML, hãy escape theo đúng context khi hiển thị. HTML text, HTML attribute, JavaScript, URL và CSS có quy tắc encoding khác nhau. Không dùng một hàm escape chung cho mọi context.

Nếu nghiệp vụ cần hiển thị rich text, dùng HTML sanitizer có allowlist tag/attribute và cấu hình an toàn. Không đưa nội dung bên ngoài vào innerHTML hoặc template engine như mã đáng tin cậy.

## 7. Kiểm soát kích thước và tài nguyên response

API đối tác có thể trả body rất lớn, không kết thúc, bị nén quá mức hoặc chứa nhiều phần tử. Consumer cần giới hạn:

- Tổng response bytes.
- Kích thước sau giải nén.
- Thời gian kết nối, thời gian nhận response và tổng deadline.
- Số phần tử, số trang và tổng số trang được phép đọc.
- Độ sâu và độ phức tạp parser.
- Số request đồng thời đến từng provider.
- Số lần retry và tổng thời gian retry.

Không tải toàn bộ response hoặc file lớn vào heap nếu có thể xử lý streaming. Với pagination, giới hạn page size và tổng số trang; không theo một next URL tùy ý từ response nếu chưa kiểm tra host và scheme. Với file, dùng streaming có quota và xác minh kích thước thực tế.

### 7.1. Pagination và batch

Một provider có thể trả nextPage, nextCursor hoặc link trang kế tiếp. Không giả định provider luôn trả số trang hữu hạn hoặc link cùng host. Hãy:

- Kiểm tra URL trang tiếp theo theo allowlist.
- Giới hạn tổng số trang và tổng record.
- Phát hiện cursor lặp hoặc vòng lặp pagination.
- Dừng khi vượt deadline hoặc quota.
- Giữ tenant và operation context khi xử lý từng trang.

Nếu một response chứa nhiều record, cần xác minh phạm vi từng record khi chúng được dùng cho dữ liệu của tenant hoặc user. Không để batch response từ provider trở thành đường ghi hàng loạt vào tenant không liên quan.

## 8. Timeout, retry và khả năng phục hồi

Upstream chậm hoặc lỗi có thể làm thread, connection và queue của consumer bị giữ lâu. Một tích hợp an toàn cần timeout rõ ràng và giới hạn công việc đồng thời.

### 8.1. Timeout theo từng giai đoạn

Đặt timeout cho:

- DNS resolution nếu client cho phép cấu hình.
- TCP connect.
- TLS handshake.
- Chờ response headers.
- Đọc response body.
- Tổng deadline của workflow.

Tổng deadline phải được truyền qua các bước để một request không tiêu tốn thời gian vô hạn. Không chỉ đặt read timeout mà bỏ quên thời gian kết nối hoặc thời gian xử lý sau khi nhận body.

### 8.2. Retry có điều kiện

Retry chỉ phù hợp khi lỗi có thể tạm thời và operation an toàn khi thực hiện lại. Cần:

- Chỉ retry lỗi mạng hoặc status được policy cho phép.
- Dùng exponential backoff và jitter.
- Đặt số lần retry tối đa và tổng deadline.
- Tôn trọng Retry-After khi phù hợp.
- Không retry liên tục khi provider đang quá tải.
- Dùng idempotency key cho operation có side effect.
- Không retry lỗi validation, authentication hoặc authorization như thể đó là lỗi tạm thời.

Một request POST thanh toán có thể đã được provider xử lý dù consumer timeout trước khi nhận response. Gửi lại một POST mới mà không có idempotency có thể thu tiền hai lần. Trong tình huống kết quả không xác định, cần tra cứu operation bằng reference/idempotency key hoặc đối soát trước khi tạo yêu cầu mới.

### 8.3. Circuit breaker và bulkhead

Circuit breaker tạm ngừng gọi upstream khi tỷ lệ lỗi hoặc timeout vượt ngưỡng, giúp tránh tiếp tục tạo tải lên dịch vụ đang hỏng. Bulkhead giới hạn concurrency hoặc connection dành cho từng provider để một tích hợp không chiếm hết tài nguyên dùng chung.

Fallback phải an toàn về nghiệp vụ. Nếu dịch vụ định danh không khả dụng, không nên tự động chấp nhận user; nếu payment provider timeout, không nên tự đánh dấu thanh toán thành công hoặc thất bại khi chưa biết kết quả. Có thể trả trạng thái pending, đưa vào reconciliation hoặc chuyển manual review.

## 9. Xử lý dữ liệu nhạy cảm và quyền riêng tư

Chỉ gửi cho provider dữ liệu cần thiết để thực hiện chức năng. Không gửi toàn bộ object hoặc thông tin cá nhân chỉ vì endpoint của đối tác chấp nhận nhiều trường.

Trước khi gọi:

- Xác định dữ liệu nào được chia sẻ và mục đích sử dụng.
- Loại bỏ field không cần thiết.
- Mask hoặc tokenize thông tin nhạy cảm khi có thể.
- Kiểm tra tenant và object authorization trước khi gửi.
- Dùng credential có scope phù hợp.

Sau khi nhận:

- Chỉ lưu field cần cho nghiệp vụ.
- Không đưa response thô vào log.
- Không trả lại field nội bộ hoặc dữ liệu của provider cho client nếu không cần.
- Áp dụng retention và quyền truy cập theo phân loại dữ liệu.
- Xóa dữ liệu tạm sau khi xử lý nếu không cần giữ.

Nếu provider trả dữ liệu của nhiều tenant hoặc nhiều người dùng, consumer phải kiểm tra reference và tenant mapping trước khi ghi. Không dùng tenant ID từ response làm căn cứ duy nhất để chọn nơi lưu.

## 10. Xử lý lỗi từ API bên ngoài

Không chuyển nguyên response lỗi của provider đến client. Nội dung lỗi có thể chứa stack trace, hostname nội bộ, token, SQL, request ID riêng của đối tác hoặc dữ liệu người dùng khác.

Nên ánh xạ lỗi bên ngoài sang lỗi nội bộ ổn định:

| Lỗi upstream | Hành vi consumer |
|---|---|
| 400 do request tích hợp sai | Ghi lỗi tích hợp nội bộ, không đổ lỗi cho client nếu input của client hợp lệ |
| 401/403 từ provider | Kiểm tra credential/scope; không tự động chuyển thành 401 của người dùng |
| 404 | Phân biệt tài nguyên provider không tồn tại với object nội bộ không tồn tại |
| 429 | Tôn trọng quota và Retry-After; không retry dồn dập |
| 5xx hoặc timeout | Retry có giới hạn nếu an toàn; nếu không, trả trạng thái tạm thời hoặc pending |
| Response sai schema | Từ chối dữ liệu, ghi reason code và cảnh báo contract drift |

API nội bộ có thể trả 502 Bad Gateway khi upstream trả response không hợp lệ, 503 Service Unavailable khi dependency tạm thời không sẵn sàng, hoặc 504 Gateway Timeout khi chờ upstream quá lâu. Chọn status theo contract và giữ response không tiết lộ chi tiết nội bộ.

## 11. Ví dụ triển khai với Java và Spring WebClient

Ví dụ sau minh họa một client được cấu hình cho provider cố định, có timeout, giới hạn bộ nhớ giải mã và tắt redirect tự động. Các giá trị là ví dụ; cần điều chỉnh theo SLA và contract của provider.

### 11.1. Cấu hình client

~~~java
HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
    .responseTimeout(Duration.ofSeconds(3))
    .followRedirect(false);

ExchangeStrategies strategies = ExchangeStrategies.builder()
    .codecs(codecs -> codecs.defaultCodecs()
        .maxInMemorySize(1 * 1024 * 1024))
    .build();

WebClient partnerClient = WebClient.builder()
    .baseUrl("https://api.partner.example")
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .exchangeStrategies(strategies)
    .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
    .build();
~~~

Base URL cần đến từ cấu hình được quản lý và allowlist; không ghép URL do người dùng hoặc response đối tác cung cấp. Giới hạn maxInMemorySize giúp tránh buffer response quá lớn khi codec giải mã vào bộ nhớ, nhưng không thay thế giới hạn ở gateway/network, timeout tổng hoặc streaming policy.

### 11.2. Gọi API và ánh xạ lỗi

~~~java
Mono<PartnerPaymentResponse> fetchPayment(
        String reference,
        PaymentOperation expected) {
    return partnerClient.get()
        .uri("/v1/payments/{reference}", reference)
        .retrieve()
        .onStatus(HttpStatusCode::isError,
            response -> response.createException())
        .bodyToMono(PartnerPaymentResponse.class)
        .map(response -> validatePartnerPayment(response, expected));
}
~~~

Không đưa reference vào URL tùy ý; path parameter cần được encode đúng và kiểm tra theo contract. Trong ứng dụng thực tế, cần phân loại lỗi upstream, timeout và response không hợp lệ thành exception nội bộ có reason code phù hợp.

### 11.3. Kiểm tra invariant trước khi cập nhật domain

~~~java
PartnerPaymentResponse validatePartnerPayment(
        PartnerPaymentResponse response,
        PaymentOperation expected) {

    if (response == null
            || response.transactionId() == null
            || response.merchantReference() == null
            || response.amount() == null
            || response.currency() == null) {
        throw new InvalidPartnerResponseException();
    }

    if (!expected.reference().equals(response.merchantReference())
            || expected.amount().compareTo(response.amount()) != 0
            || !expected.currency().equals(response.currency())) {
        throw new PartnerResponseMismatchException();
    }

    if (!Set.of("AUTHORIZED", "CAPTURED", "FAILED")
            .contains(response.status())) {
        throw new InvalidPartnerResponseException();
    }

    return response;
}
~~~

Ví dụ này cho thấy response phải khớp operation nội bộ đã tạo. Trong mã thật, tập trạng thái cần theo contract; không dùng một danh sách trạng thái chung cho mọi provider. Việc xác minh chữ ký callback, idempotency, tenant mapping và cập nhật ledger cần được thực hiện ở các bước phù hợp của workflow.

## 12. Kiểm thử tích hợp và contract

Kiểm thử không nên chỉ dùng một mock luôn trả response thành công. Cần xác minh consumer xử lý đúng khi provider thay đổi, lỗi hoặc trả dữ liệu độc hại.

| Nhóm test | Trường hợp | Kết quả mong đợi |
|---|---|---|
| TLS/authentication | Chứng thư không hợp lệ, token hết hạn hoặc sai scope | Kết nối/request bị từ chối; không tắt kiểm tra để tiếp tục |
| Status/content type | 3xx, 4xx, 5xx hoặc Content-Type không đúng | Xử lý theo contract, không parse tùy tiện |
| Schema | Thiếu field, sai type, enum lạ, key trùng | Từ chối hoặc xử lý tương thích có chủ đích |
| Business invariants | Sai amount, currency, tenant hoặc transaction reference | Không cập nhật trạng thái nghiệp vụ |
| Injection | Chuỗi response chứa payload SQL/HTML/shell | Không thực thi; được xử lý theo context |
| Parser/resource | Body quá lớn, JSON sâu, string dài hoặc nén quá mức | Bị giới hạn trước khi cạn tài nguyên |
| Redirect/URL | Redirect sang host lạ hoặc URL trang kế tiếp không hợp lệ | Không gửi credential hoặc gọi đích bị cấm |
| Timeout/retry | Upstream chậm, timeout hoặc 429 | Retry có giới hạn và tôn trọng deadline |
| Idempotency | POST bị gửi lại hoặc callback trùng | Không tạo side effect trùng |
| Contract drift | Provider thêm, bỏ hoặc đổi field | Có test/monitor phát hiện và xử lý theo policy |
| Privacy/logging | Response có token hoặc dữ liệu nhạy cảm | Không ghi dữ liệu thô vào log |

### 12.1. Contract test và kiểm thử tương thích

Contract test xác minh request/response mà consumer mong đợi. Có thể dùng schema hoặc consumer-driven contract để phát hiện thay đổi trước khi provider triển khai. Contract test không thay thế kiểm thử bảo mật: schema hợp lệ vẫn có thể chứa giá trị sai nghiệp vụ hoặc dữ liệu độc hại.

Nên kiểm thử với:

- Response mẫu hợp lệ.
- Response biên và giá trị null.
- Field bổ sung hoặc bị bỏ.
- Kiểu dữ liệu thay đổi.
- Status code mới.
- Pagination bất thường.
- Response lớn và chậm.
- Dữ liệu có ký tự điều khiển hoặc chuỗi có thể gây injection.

Không dùng dữ liệu production thật trong fixture nếu có thông tin cá nhân hoặc bí mật. Fixture cần được làm giả hoặc giả danh hóa.

### 12.2. Chaos và failure testing

Với tích hợp quan trọng, kiểm thử timeout, connection reset, DNS lỗi, provider unavailable, response một phần, callback đến trễ và callback trùng. Xác minh hệ thống giữ trạng thái nhất quán, không retry vô hạn và có thể đối soát sau khi dependency phục hồi.

## 13. Giám sát và quản lý thay đổi của provider

Theo dõi các tín hiệu:

- Request count, latency và error rate theo provider/endpoint.
- Tỷ lệ response sai schema hoặc sai business invariant.
- Số lần timeout, retry, circuit breaker open và fallback.
- Response bytes, số record và thời gian parse.
- Tỷ lệ callback sai chữ ký, trùng event hoặc correlation mismatch.
- Tuổi credential, thời điểm rotation và lỗi xác thực.
- Sai lệch giữa trạng thái nội bộ và trạng thái provider.

Log cần có provider name, endpoint template, operation ID, request/trace ID, status, latency và reason code. Không log Authorization header, API key, response body đầy đủ hoặc dữ liệu nhạy cảm. Nếu cần lưu mẫu response phục vụ điều tra, phải redact và áp dụng quyền truy cập, mã hóa cùng retention phù hợp.

Khi provider thay đổi contract, nhóm cần biết thay đổi nào có thể ảnh hưởng consumer. Nên theo dõi changelog, version sunset, thông báo bảo trì và advisory bảo mật. Mỗi tích hợp cần có owner, quy trình nâng cấp và phương án ngắt kết nối hoặc chuyển chế độ an toàn.

## 14. Những sai lầm thường gặp

- **Tin tưởng API bên thứ ba tuyệt đối:** dữ liệu bên ngoài vẫn có thể sai, độc hại hoặc bị thao túng.
- **Chỉ kiểm tra request từ client:** bỏ qua validation đối với response upstream.
- **Coi HTTP 200 là giao dịch thành công:** không kiểm tra trạng thái nghiệp vụ và reference.
- **Deserialize thẳng vào domain entity:** response có thể thay đổi owner, tenant hoặc field nhạy cảm.
- **Tắt TLS verification:** mở đường cho giả mạo hoặc can thiệp kết nối.
- **Chuyển tiếp token người dùng:** làm lộ credential hoặc cấp quyền sai audience.
- **Tin redirect và next-page URL:** có thể gửi credential hoặc request đến host không được phép.
- **Không giới hạn response:** upstream có thể làm cạn heap hoặc parser.
- **Retry mọi lỗi:** khuếch đại tải hoặc tạo giao dịch lặp.
- **Không có idempotency:** timeout có thể dẫn đến thanh toán hoặc refund nhiều lần.
- **Trả nguyên lỗi provider cho client:** làm lộ stack trace, hostname hoặc dữ liệu nhạy cảm.
- **Không kiểm thử contract drift:** thay đổi nhỏ của provider có thể phá vỡ workflow.
- **Log response thô:** biến log thành nơi lưu token và dữ liệu cá nhân.
- **Không có phương án khi upstream lỗi:** dependency bên ngoài có thể kéo sập toàn bộ API nội bộ.

## 15. Checklist trước khi phát hành tích hợp

- [ ] API provider, endpoint, owner và dữ liệu trao đổi được ghi trong inventory.
- [ ] Trust boundary và workflow phụ thuộc response đã được xác định.
- [ ] Kết nối dùng TLS với certificate và hostname verification.
- [ ] Base URL/host đến từ cấu hình được quản lý và allowlist.
- [ ] Redirect và pagination URL được kiểm soát; credential không bị chuyển sang host lạ.
- [ ] Outbound identity có scope tối thiểu, audience phù hợp và quy trình rotation/revoke.
- [ ] Không đặt secret trong URL, source code, image hoặc log.
- [ ] Status code, Content-Type và schema được kiểm tra.
- [ ] Response được parse vào DTO biên giới, không bind trực tiếp vào domain entity.
- [ ] Parser có giới hạn byte, độ sâu, chiều dài và số phần tử phù hợp.
- [ ] Business invariants như tenant, reference, amount, currency và state được xác minh.
- [ ] Dữ liệu response được xử lý an toàn trước SQL, shell, HTML, template, file path và log.
- [ ] Timeout, response size, concurrency, rate limit và tổng deadline được cấu hình.
- [ ] Retry có backoff, jitter, giới hạn và idempotency cho side effect.
- [ ] Circuit breaker, bulkhead và fallback không làm sai nghiệp vụ.
- [ ] Callback/webhook được xác minh chữ ký, correlation và chống replay khi có sử dụng.
- [ ] Error response được ánh xạ, không chuyển nguyên nội dung nhạy cảm từ provider.
- [ ] Có contract test, test dữ liệu độc hại, timeout, redirect, replay và failure.
- [ ] Log/metric/tracing hỗ trợ điều tra nhưng không lưu credential hoặc payload nhạy cảm.
- [ ] Có owner, quy trình theo dõi thay đổi provider và phương án ngắt tích hợp an toàn.

Unsafe Consumption of APIs nhắc rằng mọi response từ một hệ thống khác đều cần được xử lý theo ranh giới tin cậy. Khi consumer xác minh kết nối, giới hạn tài nguyên, kiểm tra contract và invariant nghiệp vụ, rồi chỉ chuyển dữ liệu đã xác nhận vào domain model, một lỗi hoặc sự cố ở upstream sẽ khó lan thành lỗ hổng trong API nội bộ.
