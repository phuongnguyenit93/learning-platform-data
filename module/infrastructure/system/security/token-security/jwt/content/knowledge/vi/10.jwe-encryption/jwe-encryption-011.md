# Trả lỗi giải mã an toàn và tránh tiết lộ chi tiết xử lý

> **Chương:** Mã hóa JWE  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung tập trung vào cách xử lý lỗi khi xác minh và giải mã JSON Web Encryption (JWE), áp dụng cho hệ thống JOSE nói chung, độc lập với ngôn ngữ lập trình và framework.

## 1. Vì sao phản hồi lỗi JWE cần được thiết kế cẩn thận?

Khi một hệ thống nhận JWE, quá trình xử lý có thể thất bại ở nhiều giai đoạn:

- Chuỗi Compact Serialization sai cấu trúc hoặc Base64url không hợp lệ.
- Protected Header chứa thuật toán không được phép.
- `kid` không ánh xạ đến khóa recipient được cấu hình.
- Không phục hồi hoặc thiết lập được Content Encryption Key (CEK).
- Giải mã thất bại hoặc authentication tag/AAD không hợp lệ.
- Plaintext không đúng kiểu nội dung mà endpoint yêu cầu.
- JWT lồng bên trong không hợp lệ.
- Claims hết hạn, sai issuer/audience hoặc không đủ quyền.

Nếu API trả về thông báo khác nhau cho từng trường hợp, người gọi có thể suy ra thông tin về cấu trúc token, khóa, thuật toán hoặc trạng thái xác thực bên trong. Một hệ thống có phản hồi khác nhau theo từng lỗi có thể trở thành **oracle**: kẻ tấn công gửi đầu vào được điều chỉnh và quan sát phản hồi để thu thập thông tin.

Các tín hiệu có thể bị khai thác không chỉ là nội dung thông báo:

- HTTP status code.
- Response body, error code, response length và headers.
- Thời gian phản hồi.
- Số lần retry hoặc sự khác nhau giữa các lần retry.
- Kết nối bị đóng, timeout hoặc cách server xử lý dữ liệu lỗi.
- Hành vi khác nhau giữa các endpoint dùng chung một loại token.

**Mục tiêu:** người gọi chỉ nhận được thông tin đủ để biết yêu cầu xác thực không thành công; hệ thống nội bộ vẫn ghi nhận được nguyên nhân cụ thể để giám sát và điều tra.

## 2. Hiểu các giai đoạn có thể phát sinh lỗi

Một validator JWE thường đi qua các bước sau:

~~~mermaid
flowchart TD
    A["Nhận request và JWE"] --> B["Kiểm tra cấu trúc, kích thước"]
    B --> C["Kiểm tra header và policy alg/enc"]
    C --> D["Tra khóa recipient"]
    D --> E["Phục hồi CEK và giải mã"]
    E --> F["Xác thực tag và AAD"]
    F --> G["Kiểm tra kiểu plaintext"]
    G --> H["Xác minh JWT bên trong nếu có"]
    H --> I["Kiểm tra claims và authorization"]
~~~

Mỗi bước có thể thất bại vì lý do khác nhau. Những lý do này hữu ích cho vận hành, nhưng không nhất thiết phải được công bố chi tiết cho client.

| Giai đoạn | Ví dụ lỗi nội bộ | Thông tin không nên tiết lộ ra ngoài |
|---|---|---|
| Cấu trúc | Sai số phần Compact, Base64url lỗi, JSON header không hợp lệ, tham số trùng. | Phần nào của token sai, parser dừng ở byte nào. |
| Chính sách | `alg` hoặc `enc` không nằm trong allowlist, thiếu tham số bắt buộc. | Danh sách thuật toán nội bộ hoặc cấu hình bảo mật đang dùng. |
| Khóa | Không tìm thấy `kid`, khóa không tương thích, khóa bị thu hồi. | Khóa nào tồn tại, khóa nào đang hoạt động hoặc alias của kho khóa. |
| Quản lý khóa | RSA-OAEP thất bại, ECDH-ES không thiết lập được CEK, lỗi KMS/HSM. | Chi tiết unwrap, thông tin khóa hoặc lỗi nội bộ của KMS/HSM. |
| Giải mã/xác thực | Tag sai, AAD không khớp, ciphertext bị sửa. | Phân biệt sai tag, sai khóa hay ciphertext bị thay đổi. |
| Nội dung | Plaintext không phải JWT/JSON theo profile. | Nội dung plaintext, cấu trúc claims hoặc byte gây lỗi. |
| JWT bên trong | Chữ ký sai, issuer không tin cậy, nesting sai. | Lớp nào thất bại và danh tính signer chưa được xác minh. |
| Claims/ủy quyền | Token hết hạn, audience sai, thiếu scope. | Chi tiết claims hoặc quyền của một chủ thể chưa được xác thực. |

Phân loại nội bộ vẫn cần thiết. Nguyên tắc là **phân biệt lỗi trong hệ thống quan sát, nhưng thống nhất cách phản hồi cho các lỗi xác thực token ở giao diện bên ngoài**.

## 3. Oracle giải mã JWE hình thành như thế nào?

Một oracle xuất hiện khi kẻ gửi có thể quan sát phản hồi và phân biệt các trạng thái xử lý mà lẽ ra phải được giữ kín.

### 3.1. Oracle dựa trên thông báo lỗi

Ví dụ API trả về:

| Đầu vào | Phản hồi dễ gây lộ thông tin |
|---|---|
| `kid` không tồn tại | `Unknown recipient key` |
| `kid` tồn tại nhưng unwrap thất bại | `Key decryption failed` |
| CEK phục hồi được nhưng tag sai | `Authentication tag mismatch` |
| Tag hợp lệ nhưng plaintext sai định dạng | `Invalid inner JWT` |

Kẻ tấn công có thể dùng khác biệt đó để dò tìm key identifier hợp lệ, hiểu pipeline xác minh hoặc xác định một ciphertext đã qua được một số bước xử lý.

**Cách xử lý:** các lỗi xác thực JWE và nội dung bên trong nên được ánh xạ về một phản hồi xác thực chung, ví dụ `invalid_token`. Không đưa nguyên nhân mật mã vào response body, header hoặc URL.

### 3.2. Oracle dựa trên HTTP status và response shape

Nếu một endpoint trả 400 cho sai định dạng, 401 cho sai tag, 404 cho `kid` không tồn tại và 422 cho plaintext sai, kẻ tấn công có thể phân loại đầu vào theo từng giai đoạn.

Không nhất thiết mọi lỗi request phải dùng cùng status. Ví dụ, request thiếu hẳn Authorization header có thể là lỗi request; một token đã được nhận nhưng không vượt qua xác thực nên được xử lý theo hợp đồng token không hợp lệ. Tuy nhiên, **các nguyên nhân nội bộ khác nhau trong cùng nhóm xác thực token** không nên tạo ra những phản hồi giúp phân biệt trạng thái khóa hoặc mật mã.

Ngoài status code, cần giữ nhất quán:

- Kiểu response body và tên trường.
- Số lượng header tùy chỉnh.
- Kích thước phản hồi trong phạm vi hợp lý.
- Cách đóng kết nối và xử lý timeout.
- Cách phản hồi giữa các endpoint có cùng profile token.

### 3.3. Oracle dựa trên thời gian

Một số nhánh xử lý có thể mất thời gian khác nhau:

- Key lookup thất bại nhanh, trong khi unwrap bằng KMS mất nhiều thời gian.
- Tag sai dừng ngay, còn tag hợp lệ tiếp tục parse plaintext.
- Một loại lỗi kích hoạt retry hoặc thử khóa khác.
- Một endpoint thực hiện nhiều bước hơn endpoint khác.

Kẻ tấn công có thể gửi nhiều mẫu và thống kê thời gian để tìm ra khác biệt có ý nghĩa.

Không phải mọi đường đi đều có thể hoặc cần có thời gian thực thi tuyệt đối bằng nhau. Tuy nhiên, không được cố ý tạo ra khác biệt dễ quan sát làm lộ trạng thái bí mật. Dùng thư viện mật mã đáng tin cậy, thao tác so sánh tag theo cách constant-time do thư viện cung cấp, giới hạn retry và tránh các nhánh xử lý tiết lộ sự tồn tại của khóa.

## 4. Phản hồi bên ngoài nên như thế nào?

### 4.1. Dùng một lỗi xác thực token chung

Với endpoint nhận bearer token, có thể dùng hợp đồng tương thích OAuth Bearer Token:

- HTTP `401 Unauthorized`.
- Header `WWW-Authenticate: Bearer error="invalid_token"`.
- Response body chung, không chứa chi tiết về JWE, khóa hoặc thuật toán.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_token",
  "message": "Thông tin xác thực không hợp lệ."
}
~~~

[RFC 6750 §3.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-3.1) định nghĩa `invalid_token` cho bearer token không hợp lệ. Nếu API không dùng OAuth Bearer Token, hãy áp dụng một error contract tương đương theo giao thức của hệ thống.

Không nên trả các thông báo như:

- "Không tìm thấy key ID này."
- "Khóa tồn tại nhưng sai private key."
- "RSA-OAEP unwrap thất bại."
- "GCM tag sai."
- "Plaintext giải mã được nhưng JWT bên trong sai chữ ký."
- "Issuer này có trong trust store nhưng audience không khớp."

Các thông tin này có thể được lưu trong log nội bộ với quyền truy cập được kiểm soát.

### 4.2. Không đưa chi tiết vào error_description

Với bearer token, RFC 6750 có trường `error_description` tùy chọn. Không nên dùng trường này để trả lỗi mật mã chi tiết.

Ví dụ nên tránh:

~~~http
WWW-Authenticate: Bearer error="invalid_token",
  error_description="kid billing-recipient-enc-04 tồn tại nhưng authentication tag sai"
~~~

Có thể chỉ trả:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

### 4.3. Phân biệt token không hợp lệ với lỗi dịch vụ

Không được biến mọi lỗi thành `invalid_token`. Một số lỗi là lỗi hạ tầng, không phải bằng chứng token không hợp lệ:

| Tình huống | Phân loại phù hợp |
|---|---|
| Sai serialization, thuật toán không được phép, key ID không hợp lệ, tag sai. | Lỗi xác thực token; trả lỗi token chung. |
| Token đã xác thực nhưng thiếu quyền. | Lỗi authorization theo hợp đồng API, thường là 403 hoặc lỗi insufficient scope. |
| KMS/HSM ngừng hoạt động, timeout mạng đến kho khóa, dịch vụ tin cậy không sẵn sàng. | Lỗi dịch vụ tạm thời; trả 5xx phù hợp, thường là 503 nếu dịch vụ phụ thuộc không khả dụng. |
| Lỗi lập trình hoặc cấu hình nội bộ. | Lỗi server; không trả stack trace hoặc chi tiết cấu hình. |

Nếu KMS/HSM tạm thời không hoạt động, trả `invalid_token` có thể khiến client hiểu nhầm token của họ sai và không thử lại sau. Ngược lại, trả 503 kèm tên khóa hoặc lỗi KMS có thể tiết lộ kiến trúc nội bộ. Hãy phân biệt lỗi vận hành trong hệ thống, nhưng giữ response công khai ở mức tổng quát.

## 5. Không tạo khác biệt qua retry và fallback

Khi giải mã JWE thất bại, không nên thử hàng loạt cách khác nhau cho đến khi một cách thành công.

Không được:

- Thử tất cả khóa trong kho chỉ vì `kid` không khớp.
- Thử nhiều thuật toán `alg` hoặc `enc` ngoài allowlist.
- Thử diễn giải JWE Compact thành một định dạng khác.
- Bỏ qua authentication tag.
- Chuyển sang parse plaintext như JSON nếu profile yêu cầu JWT.
- Chấp nhận JWE không có lớp chữ ký khi endpoint yêu cầu chữ ký bên trong.
- Tự tải khóa từ URL do token cung cấp.

Những fallback này vừa làm tăng chi phí xử lý vừa tạo khác biệt thời gian và hành vi, đồng thời làm suy yếu hợp đồng bảo mật.

### 5.1. Xoay vòng khóa có kiểm soát

Xoay vòng khóa có thể yêu cầu hỗ trợ nhiều khóa trong một khoảng thời gian. Điều đó không có nghĩa là thử mọi khóa tùy ý.

- Dùng `kid` để chọn khóa trong tập khóa recipient đã được cấu hình.
- Ràng buộc mỗi khóa với thuật toán, mục đích và thời hạn hiệu lực.
- Chỉ cho phép một tập khóa đang hoạt động và khóa cũ còn trong giai đoạn chuyển tiếp.
- Nếu `kid` không hợp lệ hoặc không tồn tại, dừng theo cùng hợp đồng lỗi token.
- Không tiết lộ cho client `kid` nào đã được tìm thấy.

### 5.2. Retry lỗi hạ tầng khác với retry lỗi mật mã

Nếu KMS/HSM gặp lỗi tạm thời, hệ thống có thể có retry nội bộ có giới hạn, deadline và backoff theo chính sách vận hành. Đây là xử lý lỗi phụ thuộc dịch vụ, không phải thử các khóa/thuật toán khác để tìm cách giải mã token.

Không retry vô hạn hoặc làm tăng thời gian phản hồi theo cách tiết lộ trạng thái khóa. Nếu hết deadline, trả lỗi dịch vụ tổng quát và ghi nhận sự cố nội bộ.

## 6. Giữ thời gian phản hồi và hành vi xử lý ổn định

### 6.1. Dùng thư viện JOSE và mật mã đáng tin cậy

- Dùng thư viện JOSE được duy trì và có kiểm thử bảo mật.
- Không tự triển khai RSA-OAEP, ECDH-ES, AES-GCM, AES-CBC-HMAC hoặc kiểm tra authentication tag.
- Không tự so sánh tag bằng phép so sánh chuỗi thông thường nếu thư viện cung cấp phép so sánh constant-time.
- Tuân thủ đúng quy tắc xác thực trước khi công bố plaintext.
- Giới hạn kích thước và thời gian xử lý trước khi thực hiện thao tác mật mã tốn kém.

### 6.2. Tránh phản hồi có thời gian dễ phân biệt

- Không trả lỗi ngay theo các thông báo khác nhau cho "không có key" và "tag sai".
- Không thực hiện nhiều lần key lookup hoặc decryption fallback.
- Dùng cache khóa có kiểm soát, nhưng tránh để trạng thái cache trở thành tín hiệu công khai về một `kid`.
- Hạn chế số lần thử theo client, nguồn gửi hoặc tenant.
- Theo dõi phân bố latency để phát hiện khác biệt bất thường.
- Dùng deadline thống nhất cho pipeline xác thực.

Không cần thêm một khoảng delay cố định cho mọi request một cách máy móc. Delay nhân tạo có thể làm tăng nguy cơ cạn tài nguyên. Ưu tiên loại bỏ nhánh xử lý không cần thiết, dùng crypto constant-time ở nơi phù hợp và kiểm soát tần suất request.

### 6.3. Không dùng plaintext hoặc dữ liệu chưa xác thực làm tín hiệu phụ

Trước khi authentication tag thành công, không được:

- Parse Claims Set.
- Kiểm tra `iss`, `aud` hoặc `scope` để tạo thông báo riêng.
- Ghi plaintext vào log.
- Gọi dịch vụ nghiệp vụ dựa trên nội dung đó.
- Trả lỗi khác nhau dựa trên trường dữ liệu chưa được xác thực.

Nếu JWE chứa JWT lồng bên trong, chỉ parse và xác minh JWT đó sau khi JWE ngoài đã được xác thực hoàn toàn.

## 7. Ghi log nội bộ mà không làm lộ bí mật

Phản hồi công khai cần chung, nhưng log nội bộ vẫn phải đủ chi tiết để điều tra và vận hành.

### 7.1. Các trường log nên có

| Trường | Ví dụ | Mục đích |
|---|---|---|
| `event` | `jwe_validation_failed` | Nhóm sự kiện. |
| `reason_code` | `JWE_AUTH_TAG_INVALID` | Phân loại lỗi nội bộ. |
| `correlation_id` | ID ngẫu nhiên của request | Kết nối log giữa các thành phần. |
| `endpoint` | `/api/invoices` | Xác định nơi xảy ra lỗi. |
| `layer_type` | `JWE_OUTER` | Lớp đang được xử lý. |
| `algorithm_profile` | Tên profile đã cấu hình | Phân tích cấu hình mà không lộ chi tiết khóa. |
| `duration_ms` | Thời gian xử lý | Phát hiện latency bất thường. |
| `dependency_status` | `KMS_TIMEOUT` | Phân biệt lỗi token với lỗi hạ tầng. |
| `decision` | `REJECTED` | Kết quả cuối cùng. |

Có thể dùng mã khóa nội bộ đã được kiểm soát để điều tra, nhưng cần đánh giá liệu log đó có thể bị lộ ra ngoài hay không. Không dùng dữ liệu do client cung cấp làm nhãn metric có cardinality không giới hạn.

### 7.2. Không ghi log các dữ liệu sau

- Toàn bộ JWE hoặc bearer token nguyên vẹn.
- Plaintext sau giải mã.
- CEK, private key, shared secret hoặc dữ liệu nhạy cảm từ HSM/KMS.
- Claims Set chứa thông tin cá nhân hoặc nghiệp vụ.
- Authentication tag, ciphertext hoặc encrypted key nếu chúng không cần thiết cho điều tra và có thể làm lộ dữ liệu liên quan.
- Stack trace hoặc thông tin nội bộ trong response gửi client.

Nếu cần liên kết nhiều sự kiện liên quan đến cùng token, cân nhắc fingerprint bằng HMAC với khóa log riêng được bảo vệ. Không dùng fingerprint như bằng chứng xác thực token và không lưu khóa HMAC cùng log.

### 7.3. Phân quyền và thời hạn lưu log

- Giới hạn người có thể xem reason code chi tiết.
- Tách log bảo mật khỏi log truy cập thông thường khi cần.
- Áp dụng thời hạn lưu trữ và chính sách xóa.
- Audit việc truy cập log có dữ liệu nhạy cảm.
- Không để dashboard hoặc metric công khai hiển thị `kid`, issuer chưa xác thực hoặc nguyên nhân giải mã chi tiết.

## 8. Bảng ánh xạ lỗi nội bộ và phản hồi công khai

Một thiết kế rõ ràng giúp giữ nguyên thông tin vận hành mà không biến response thành oracle.

| Reason code nội bộ | Xử lý nội bộ | Phản hồi token cho client |
|---|---|---|
| `JWE_MALFORMED` | Ghi nhận serialization không hợp lệ. | `invalid_token` |
| `JWE_ALGORITHM_REJECTED` | Ghi nhận profile/allowlist không khớp. | `invalid_token` |
| `JWE_KID_NOT_FOUND` | Ghi nhận không tìm thấy khóa recipient. | `invalid_token` |
| `JWE_KEY_UNWRAP_FAILED` | Ghi nhận CEK không phục hồi được. | `invalid_token` |
| `JWE_AUTH_TAG_INVALID` | Ghi nhận tag/AAD không hợp lệ. | `invalid_token` |
| `JWE_INNER_CONTENT_INVALID` | Ghi nhận plaintext sai kiểu nội dung. | `invalid_token` |
| `JWE_INNER_JWT_INVALID` | Ghi nhận JWT bên trong không hợp lệ. | `invalid_token` |
| `JWE_CLAIMS_INVALID` | Ghi nhận issuer/audience/time không đạt. | `invalid_token` |
| `JWE_KMS_UNAVAILABLE` | Ghi nhận lỗi phụ thuộc hạ tầng. | Lỗi dịch vụ tổng quát, ví dụ 503. |
| `AUTHORIZATION_DENIED` | Token đã xác thực nhưng không đủ quyền. | Lỗi authorization theo hợp đồng, ví dụ 403. |

Không trả reason code nội bộ cho client. Mã công khai chỉ nên mô tả trạng thái cần thiết để client xử lý.

## 9. Mã giả: phản hồi chung, log riêng

Mã giả sau minh họa việc phân loại lỗi nội bộ và ánh xạ response. Đây là quy trình khái niệm, không phải API của thư viện cụ thể.

~~~text
function handle_jwe_request(request, policy):
    correlation_id = create_random_correlation_id()
    start_time = monotonic_time()

    try:
        token = extract_token_from_expected_location(request)
        claims = validate_jwe_and_all_required_layers(token, policy)

        if not authorize(claims, request.operation):
            audit_event(
                event = "authorization_denied",
                correlation_id = correlation_id,
                reason_code = "AUTHORIZATION_DENIED"
            )
            return generic_authorization_response()

        return continue_request(claims)

    catch InvalidJweFormat:
        record_safe_failure(correlation_id, "JWE_MALFORMED")
        return generic_invalid_token_response()

    catch UnsupportedJweAlgorithm:
        record_safe_failure(correlation_id, "JWE_ALGORITHM_REJECTED")
        return generic_invalid_token_response()

    catch RecipientKeyNotFound:
        record_safe_failure(correlation_id, "JWE_KID_NOT_FOUND")
        return generic_invalid_token_response()

    catch JweAuthenticationFailed:
        record_safe_failure(correlation_id, "JWE_AUTH_TAG_INVALID")
        return generic_invalid_token_response()

    catch InvalidInnerJwt:
        record_safe_failure(correlation_id, "JWE_INNER_JWT_INVALID")
        return generic_invalid_token_response()

    catch InvalidClaims:
        record_safe_failure(correlation_id, "JWE_CLAIMS_INVALID")
        return generic_invalid_token_response()

    catch KeyServiceUnavailable:
        record_safe_failure(correlation_id, "JWE_KMS_UNAVAILABLE")
        return generic_service_unavailable_response()

    finally:
        record_duration_metric(monotonic_time() - start_time)
~~~

Trong triển khai thực tế:

- `generic_invalid_token_response()` phải dùng cùng response contract cho các lỗi xác thực token.
- `record_safe_failure()` chỉ ghi dữ liệu đã được làm sạch; không nhận raw token hoặc plaintext.
- Không để exception message, stack trace hoặc tên khóa tự động đi vào response.
- Cần bảo đảm exception từ thư viện được ánh xạ đúng nhóm; lỗi lập trình không được ngụy trang thành token không hợp lệ mãi mãi.
- Thời gian phản hồi vẫn cần được giám sát để tìm side channel; việc dùng chung response body không tự loại bỏ timing oracle.

## 10. Ma trận kiểm thử lỗi và chống oracle

| Trường hợp kiểm thử | Phản hồi công khai mong đợi | Quan sát nội bộ |
|---|---|---|
| JWE Compact sai định dạng. | Cùng lỗi token không hợp lệ. | `JWE_MALFORMED`. |
| `kid` không tồn tại. | Cùng lỗi token không hợp lệ. | `JWE_KID_NOT_FOUND`. |
| `kid` tồn tại nhưng unwrap thất bại. | Cùng lỗi token không hợp lệ. | `JWE_KEY_UNWRAP_FAILED`. |
| Authentication tag sai. | Cùng lỗi token không hợp lệ. | `JWE_AUTH_TAG_INVALID`. |
| AAD không khớp. | Cùng lỗi token không hợp lệ. | `JWE_AUTH_TAG_INVALID` hoặc mã chi tiết tương ứng. |
| Plaintext không đúng kiểu nội dung. | Cùng lỗi token không hợp lệ. | `JWE_INNER_CONTENT_INVALID`. |
| JWT bên trong sai chữ ký. | Cùng lỗi token không hợp lệ. | `JWE_INNER_JWT_INVALID`. |
| Token hết hạn hoặc sai audience. | Cùng lỗi token không hợp lệ. | `JWE_CLAIMS_INVALID`. |
| KMS/HSM tạm thời không khả dụng. | Lỗi dịch vụ tổng quát, không lộ tên khóa/dịch vụ. | `JWE_KMS_UNAVAILABLE`. |
| Token hợp lệ nhưng thiếu scope. | Lỗi authorization theo hợp đồng. | `AUTHORIZATION_DENIED`. |
| Header có thuật toán ngoài allowlist. | Cùng lỗi token không hợp lệ. | `JWE_ALGORITHM_REJECTED`. |
| Client gửi lặp nhiều token sai. | Response contract không tiết lộ thêm trạng thái; rate limit áp dụng. | Metric/rate-limit event được ghi nhận. |

Ngoài kiểm tra status và body, cần so sánh:

- Headers và response length.
- Thời gian phản hồi qua nhiều lần thử.
- Sự khác biệt khi `kid` tồn tại và không tồn tại.
- Sự khác biệt giữa sai encrypted key, sai tag và sai AAD.
- Số lần gọi KMS/HSM và retry.
- Khả năng một client tạo ra lượng log hoặc metric quá lớn.

Mục tiêu không phải chứng minh mọi request có thời gian tuyệt đối giống nhau, mà là loại bỏ các khác biệt không cần thiết có thể tiết lộ trạng thái bí mật.

## 11. Checklist thiết kế và vận hành

- [ ] Các lỗi xác thực JWE được ánh xạ về một response contract chung.
- [ ] Response không tiết lộ `kid`, tên khóa, thuật toán nội bộ hoặc trạng thái tag.
- [ ] Không trả exception message, stack trace hoặc plaintext cho client.
- [ ] Không sử dụng plaintext trước khi authentication tag/AAD được xác thực.
- [ ] Không thử khóa, thuật toán hoặc định dạng fallback ngoài hợp đồng.
- [ ] Xoay vòng khóa dùng tập khóa cấu hình sẵn và có giới hạn.
- [ ] Retry KMS/HSM có deadline và backoff; không retry lỗi mật mã.
- [ ] Lỗi token được phân biệt với lỗi dịch vụ hạ tầng.
- [ ] Log nội bộ có reason code, correlation ID và thời gian xử lý.
- [ ] Log không chứa raw token, CEK, private key hoặc plaintext nhạy cảm.
- [ ] Có rate limit và giám sát latency để phát hiện oracle.
- [ ] Kiểm thử status, body, headers, response length và timing cho các lỗi khác nhau.

## 12. Câu hỏi tự kiểm tra

1. Vì sao trả lỗi khác nhau cho sai `kid`, sai CEK và sai authentication tag có thể tạo oracle?
2. Vì sao dùng cùng response body vẫn chưa đủ nếu thời gian phản hồi khác biệt rõ rệt?
3. Khi nào nên trả `invalid_token` và khi nào nên trả lỗi dịch vụ 503?
4. Vì sao không nên trả `error_description` chứa tên khóa hoặc nguyên nhân giải mã?
5. Làm thế nào để log nội bộ vẫn có ích khi response công khai dùng một lỗi chung?
6. Vì sao không nên thử tất cả khóa hoặc thuật toán khi giải mã thất bại?
7. Tại sao lỗi authorization sau khi token đã xác thực có thể được xử lý khác lỗi giải mã?
8. Cần kiểm thử những tín hiệu nào ngoài HTTP status và response body?
9. Vì sao plaintext không được parse hoặc ghi log trước khi authentication tag hợp lệ?
10. HMAC fingerprint có thể hỗ trợ điều tra token như thế nào và vì sao không thay thế xác minh token?

## 13. Tài liệu tham khảo

- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): định dạng JWE, giải mã, xác thực nội dung và xử lý header/AAD.
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): thuật toán quản lý khóa, mã hóa nội dung và yêu cầu tham số mật mã.
- [RFC 6750 – The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): phản hồi lỗi bearer token, bao gồm `invalid_token` (§3.1).
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): rủi ro giải mã JWT mã hóa mà không xác minh chữ ký cần thiết (§2.3), xác minh mọi thao tác mật mã (§3.3) và tránh nén trước mã hóa (§3.6).
