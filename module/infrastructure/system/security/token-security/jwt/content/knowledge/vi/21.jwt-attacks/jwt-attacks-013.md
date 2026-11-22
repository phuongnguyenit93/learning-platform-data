# Rò rỉ dữ liệu qua lỗi, nhật ký, nén hoặc công cụ xem token

## 1. JWT có thể làm lộ dữ liệu ở những đâu?

JWT thường được xem là một chuỗi credential gọn, nhưng trong vòng đời của nó có nhiều điểm dữ liệu có thể bị sao chép hoặc hiển thị ngoài dự kiến: request, response, log, trace, báo cáo lỗi, công cụ debug, trình duyệt, clipboard, hệ thống hỗ trợ và các công cụ trực tuyến.

Một JWT có thể chứa thông tin nhận dạng, tenant, vai trò, scope, email, mã tài khoản hoặc metadata nội bộ. Ngoài dữ liệu trong payload, bản thân token còn có thể là **bearer credential**: ai lấy được token có thể thử sử dụng nó trong phạm vi và thời hạn mà Resource Server chấp nhận.

Các nguồn rò rỉ thường gặp:

- **Lỗi xác minh:** response hoặc stack trace chứa nguyên token, payload đã decode, claim nhạy cảm, tên khóa nội bộ hoặc chi tiết cấu hình.
- **Nhật ký và quan sát hệ thống:** access log, application log, WAF, API gateway, APM, distributed trace, crash dump và SIEM ghi lại Authorization header hoặc Cookie.
- **Nén:** độ dài ciphertext hoặc response có thể tiết lộ thông tin về plaintext trong một số mô hình tấn công side-channel.
- **Công cụ xem token:** token được dán vào website, browser extension, debugger, ticket hỗ trợ, chat hoặc công cụ không được phê duyệt.
- **Thiết bị và thao tác vận hành:** DevTools, HAR export, screenshot, clipboard manager, shell history, process arguments và file tạm.

Cần phân biệt hai loại dữ liệu bị lộ:

1. **Nội dung claims:** có thể chứa dữ liệu cá nhân hoặc thông tin nội bộ.
2. **Credential token:** có thể cho phép người khác sử dụng quyền của chủ thể, ngay cả khi payload không chứa dữ liệu bí mật.

**Nguyên tắc:** không đưa token hoặc claims nhạy cảm vào nơi không cần chúng; lỗi và telemetry chỉ nên chứa thông tin tối thiểu để chẩn đoán mà không tiết lộ credential.

## 2. Chữ ký JWT không che giấu payload

### JWS chỉ bảo vệ tính toàn vẹn và nguồn phát hành

JWT thường được biểu diễn bằng JWS Compact:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Base64url là phép mã hóa biểu diễn dữ liệu, không phải mã hóa bảo mật. Bất kỳ ai có chuỗi JWS đều có thể decode protected header và payload mà không cần khóa ký. Chữ ký giúp phát hiện việc sửa đổi và xác minh bằng khóa phù hợp; nó không làm claims trở nên bí mật.

Ví dụ payload:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "email": "person@example.test",
  "tenant_id": "tenant-17",
  "roles": ["admin"],
  "scope": "orders:read orders:write",
  "exp": 1893459600
}
~~~

Nếu đây là JWS, người có token có thể đọc các giá trị trên. Không đưa mật khẩu, API key, số thẻ, bí mật nghiệp vụ hoặc dữ liệu cá nhân không cần thiết vào payload chỉ vì JWT đã được ký.

### JWE cung cấp tính bí mật nhưng vẫn là dữ liệu nhạy cảm

JWE mã hóa plaintext để chỉ bên có khóa phù hợp mới giải mã được. Điều đó bảo vệ nội dung trên đường truyền và tại các thành phần không có khóa giải mã, nhưng không loại bỏ mọi nguy cơ:

- Protected Header của JWE được Base64url encode và vẫn có thể đọc; unprotected header cũng không được mã hóa.
- Người có khóa giải mã hoặc endpoint đã giải mã vẫn có thể ghi plaintext vào log.
- JWE vẫn có thể là bearer credential và bị phát lại nếu bị đánh cắp.
- Ciphertext length và metadata xung quanh có thể tiết lộ một số đặc điểm về thông điệp.
- Công cụ xem token có quyền giải mã có thể làm lộ nội dung nếu được dùng không an toàn.

JWE không phải lý do để đưa mọi dữ liệu nhạy cảm vào token. Hãy giảm dữ liệu mang theo và chỉ giải mã tại thành phần thực sự cần nội dung đó.

## 3. Rò rỉ qua thông báo lỗi và stack trace

Khi JWT sai định dạng, hết hạn, sai chữ ký hoặc không đáp ứng policy, thư viện và ứng dụng có thể tạo thông tin lỗi chi tiết. Nếu trả trực tiếp các chi tiết này cho client hoặc ghi nguyên exception vào log, dữ liệu có thể bị lộ.

Ví dụ phản hồi không an toàn:

~~~json
{
  "error": "invalid_token",
  "message": "Signature validation failed for token eyJhbGciOi...",
  "decoded_subject": "user-123",
  "expected_issuer": "https://internal-identity.example",
  "key_location": "vault/prod/signing/key-17"
}
~~~

Phản hồi này tiết lộ token, subject, issuer nội bộ và vị trí khóa. Một số chi tiết còn giúp attacker dò tìm cấu hình hoặc xác định token nào gần hợp lệ.

### Không phản chiếu token hoặc claims vào response

Response cho client nên dùng mã lỗi ổn định và nội dung tổng quát, ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_token",
  "request_id": "req-7c91"
}
~~~

Nếu credential hợp lệ nhưng không đủ quyền, API có thể trả lỗi authorization phù hợp theo hợp đồng, thường là 403. Không cần tiết lộ claim nào thiếu, khóa nào được dùng hoặc bước mật mã cụ thể nào thất bại cho một caller không đáng tin.

### Chi tiết nội bộ vẫn cần được kiểm soát

Đội vận hành cần biết nguyên nhân để xử lý. Hãy dùng reason code có giới hạn và log metadata an toàn, ví dụ:

~~~text
TOKEN_MALFORMED
SIGNATURE_INVALID
ISSUER_NOT_TRUSTED
AUDIENCE_MISMATCH
TOKEN_EXPIRED
KEY_NOT_FOUND
CLAIM_PROFILE_INVALID
~~~

Reason code không cần kèm token hoặc toàn bộ claims. Log cần được giới hạn quyền truy cập, thời gian lưu và khả năng xuất dữ liệu. Stack trace nên được xử lý trong hệ thống nội bộ có kiểm soát; không trả nguyên stack trace cho client.

### Kiểm tra các đường lỗi ít được chú ý

Rò rỉ có thể xuất hiện ở nhiều nhánh khác nhau:

- Parser lỗi khi Base64url decode hoặc parse JSON.
- Lỗi lấy JWKS hoặc tra cứu kid.
- Lỗi xác minh chữ ký/MAC hoặc giải mã JWE.
- Lỗi kiểm tra issuer, audience, thời gian và claim profile.
- Lỗi refresh token, token exchange hoặc introspection.
- Exception được serialize bởi middleware, gateway hoặc error tracker.
- Debug page chỉ bật trong môi trường staging nhưng vô tình mở ra bên ngoài.

Mọi đường lỗi đều cần được kiểm tra xem có chứa raw token, payload, key material, secret hoặc dữ liệu cá nhân hay không.

## 4. Rò rỉ qua log, tracing và hệ thống giám sát

HTTP header thường được log để chẩn đoán request. Nếu cấu hình ghi toàn bộ headers, các credential có thể bị lưu lại mà người vận hành không nhận ra.

Những trường cần được xem là nhạy cảm:

- Authorization, đặc biệt là giá trị Bearer.
- Cookie và Set-Cookie.
- access_token, refresh_token, id_token.
- assertion, client_assertion và DPoP proof.
- Request/response body có chứa token hoặc claims.
- Các trường sub, email, tenant, role hoặc dữ liệu nhận dạng tùy chính sách dữ liệu.

### Log có thể tồn tại ở nhiều hệ thống

| Vị trí | Ví dụ dữ liệu có thể bị ghi |
| --- | --- |
| CDN / WAF | Request headers, cookie, rule match và mẫu request |
| API Gateway / reverse proxy | Authorization header, cookie, upstream request |
| Application log | Raw token, decoded claims, exception message |
| APM / distributed tracing | Header attributes, span tags, baggage, request snapshot |
| Error tracker | Local variables, stack trace, request context |
| SIEM / log warehouse | Bản sao log, index, export và truy vấn điều tra |
| Crash dump / diagnostic bundle | Memory snapshot, object chứa token hoặc plaintext |
| CI/CD và test report | Test token, fixture, biến môi trường và output lệnh |

Xóa token khỏi application log không đủ nếu gateway hoặc APM đã ghi token trước đó. Cần kiểm tra toàn bộ đường đi từ ingress đến hệ thống lưu trữ và export.

### Không log nguyên request để tiện debug

Cấu hình “log all headers” hoặc “capture request/response body” có thể hữu ích khi debug ngắn hạn nhưng dễ biến telemetry thành kho bearer credential. Không bật mặc định trong production. Nếu cần bật tạm thời, phải có phê duyệt, phạm vi hẹp, redaction trước khi ghi, thời hạn tự tắt và kiểm soát quyền truy cập.

## 5. Thiết kế logging an toàn cho JWT

Một cách tiếp cận tốt là **allowlist dữ liệu được phép ghi**, thay vì ghi tất cả rồi cố gắng xóa một số trường nhạy cảm.

### Những thông tin có thể hữu ích

Tùy chính sách dữ liệu, log có thể ghi:

- Request/correlation ID.
- Thời điểm, route, service và region.
- Kết quả xác minh tổng quát và reason code.
- Token profile hoặc loại credential.
- Thuật toán đã được policy cho phép và kid nếu không nhạy cảm trong hệ thống.
- Kích thước token theo byte, không ghi giá trị token.
- Phiên bản JWKS/policy hoặc authorization decision version.
- Thời gian xử lý và mã response.

Không phải mọi hệ thống đều có thể log iss, sub, kid hoặc tenant ở dạng rõ. Hãy áp dụng phân loại dữ liệu và pseudonymization theo chính sách riêng.

### Dữ liệu không nên ghi

- Raw JWT hoặc JWE.
- Refresh token và client assertion.
- Private key, shared secret, decrypted key hoặc plaintext nhạy cảm.
- Toàn bộ claims set.
- Cookie header nguyên vẹn.
- Nội dung request/response có chứa credential.
- Dữ liệu cá nhân không cần cho mục đích điều tra.

### Redaction phải xảy ra trước khi ghi

Ví dụ policy:

~~~text
Authorization     -> [REDACTED]
Cookie            -> [REDACTED]
Set-Cookie        -> [REDACTED]
access_token      -> [REDACTED]
refresh_token     -> [REDACTED]
client_assertion  -> [REDACTED]
~~~

Redaction cần áp dụng ở mọi lớp có thể ghi dữ liệu: gateway, proxy, ứng dụng, APM, error tracker và công cụ hỗ trợ. Kiểm tra cả tên field viết hoa/thường, header lặp, cấu trúc lồng nhau và cách middleware chuyển header thành thuộc tính trace.

Không nên chỉ dùng một regex đơn giản trên chuỗi log sau khi dữ liệu đã được ghi vào buffer, file tạm hoặc hệ thống telemetry. Hãy loại bỏ hoặc thay thế giá trị nhạy cảm ngay tại điểm thu thập.

### Fingerprint để tương quan mà không lưu token

Nếu cần biết nhiều log có liên quan cùng một token hay không, có thể tạo fingerprint bằng HMAC với khóa bí mật riêng cho mục đích logging:

~~~text
tokenFingerprint = HMAC-SHA-256(loggingKey, rawToken)
~~~

Fingerprint ổn định có thể hỗ trợ điều tra nhưng vẫn là dữ liệu có thể liên kết các lần sử dụng. Cần bảo vệ logging key, giới hạn quyền truy cập fingerprint, xoay khóa và đặt retention phù hợp. Không dùng raw token hash như một cách thay thế hoàn toàn cho redaction; cũng không đưa fingerprint vào public response.

## 6. Nén có thể tạo side-channel làm lộ thông tin như thế nào?

Nén giảm kích thước dữ liệu bằng cách tận dụng mẫu lặp. Nếu secret và dữ liệu do attacker kiểm soát cùng tham gia một luồng nén, độ dài sau nén có thể thay đổi theo mức độ trùng khớp giữa chúng.

Trong một số mô hình tấn công, attacker có thể gửi nhiều đầu vào được lựa chọn, quan sát độ dài response hoặc ciphertext và suy luận dần nội dung bí mật. Đây là nhóm **compression side-channel**; các kỹ thuật nổi tiếng gồm CRIME và BREACH trong những bối cảnh cụ thể.

Điều kiện tấn công thường cần nhiều yếu tố kết hợp:

- Secret được đưa vào cùng một ngữ cảnh nén với dữ liệu attacker có thể kiểm soát.
- Attacker có thể tạo nhiều request hoặc quan sát nhiều phản hồi.
- Kích thước dữ liệu sau nén có thể quan sát được, trực tiếp hoặc qua kích thước TLS record/response.
- Có đủ tín hiệu để phân biệt thay đổi độ dài do dữ liệu đoán đúng.

Không phải mọi hệ thống bật compression đều tự động bị khai thác. Rủi ro phụ thuộc vào nơi nén, dữ liệu được ghép chung, khả năng kiểm soát input và khả năng quan sát kích thước.

## 7. Nén trong JWE và tham số zip

JWE có thể sử dụng tham số protected header zip để nén plaintext trước khi mã hóa. Ví dụ:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "zip": "DEF"
}
~~~

Trong ví dụ, plaintext được nén bằng DEFLATE trước khi mã hóa theo thuật toán JWE đã chọn. Ciphertext vẫn được bảo vệ mật mã, nhưng độ dài ciphertext phản ánh độ dài plaintext sau nén cùng các thành phần giao thức liên quan.

Nếu attacker có thể tác động một phần plaintext và quan sát nhiều ciphertext length, sự thay đổi độ dài có thể tiết lộ thông tin về phần bí mật được nén chung. Đây là lý do cần thận trọng khi nén dữ liệu chứa cả secret và input do attacker kiểm soát.

RFC 8725 khuyến nghị tránh nén dữ liệu đầu vào của quá trình mã hóa khi chưa có biện pháp giảm thiểu phù hợp, vì độ dài sau nén có thể tạo side-channel. Với JWT, không nên bật tham số zip theo mặc định chỉ để tiết kiệm vài byte.

### Cách giảm rủi ro với JWE compression

- Không bật zip chỉ để làm token ngắn hơn khi chưa có yêu cầu và đánh giá bảo mật.
- Tránh nén chung dữ liệu bí mật với dữ liệu do attacker kiểm soát.
- Nếu profile không cần compression, từ chối hoặc không phát hành JWE có zip.
- Nếu bắt buộc dùng compression, đánh giá side-channel theo threat model và áp dụng biện pháp giảm thiểu phù hợp.
- Giới hạn kích thước plaintext sau giải nén, tỷ lệ nén và tài nguyên CPU/bộ nhớ.
- Không coi encryption là biện pháp che giấu độ dài.

Compression không thay thế data minimization. Một JWT nhỏ hơn không nhất thiết là JWT an toàn hơn.

## 8. Nén HTTP response và rủi ro kiểu BREACH

Một tình huống khác là HTTP server nén response body bằng gzip hoặc Brotli trước khi gửi qua TLS. Nếu response chứa secret như CSRF token hoặc dữ liệu xác thực, đồng thời phản chiếu input do attacker kiểm soát, attacker có thể quan sát độ dài response qua nhiều lần thử.

Đây là mô hình liên quan đến BREACH. Nó khác với việc chỉ đặt JWT trong Authorization header. Rủi ro phát sinh từ cách response được tạo và nén, đặc biệt khi secret và input attacker nằm trong cùng compression context.

Các biện pháp có thể cân nhắc:

- Không nén response chứa secret nếu có thể kết hợp với input attacker kiểm soát.
- Tách secret khỏi phần nội dung có thể bị phản chiếu và nén.
- Tránh phản chiếu trực tiếp dữ liệu attacker vào response chứa secret.
- Dùng token/nonce ngẫu nhiên theo từng response khi phù hợp với giao thức.
- Giới hạn số lần thử và theo dõi hành vi đoán lặp bất thường.
- Đánh giá padding hoặc biện pháp làm nhiễu kích thước chỉ khi hiểu rõ giới hạn của chúng; padding không phải bảo đảm tuyệt đối.

TLS mã hóa nội dung response nhưng không nhất thiết che giấu toàn bộ thông tin về kích thước và thời gian truyền. Chỉ bật HTTPS không loại bỏ mọi side-channel dựa trên độ dài.

### Nén header trong HTTP/2 và HTTP/3

HTTP/2 dùng HPACK và HTTP/3 dùng QPACK để nén header fields. Đây là cơ chế khác với nén response body và tham số zip của JWE. Các header chứa credential cần được xử lý như dữ liệu nhạy cảm: RFC 9113 yêu cầu encoder không dùng indexed representation cho field Authorization; encoder phải dùng cách biểu diễn never-indexed tương ứng. QPACK cũng có biểu diễn never-indexed cho field nhạy cảm.

Quy tắc never-indexed giúp tránh đưa giá trị Authorization vào dynamic compression table để tái sử dụng. Nó không ngăn ứng dụng, proxy hoặc APM ghi header vào log, cũng không bảo vệ token tại endpoint đã nhận được nó. Cần dùng thư viện HTTP tuân thủ giao thức và kiểm tra cấu hình của proxy/gateway; không tự triển khai header compression để xử lý credential.

## 9. Giới hạn giải nén và nguy cơ tiêu thụ tài nguyên

Compression còn tạo rủi ro availability. Dữ liệu nén nhỏ có thể giải nén thành dữ liệu rất lớn hoặc yêu cầu nhiều CPU, gây memory exhaustion hoặc CPU exhaustion.

Với JWE có zip hoặc bất kỳ định dạng nén nào được chấp nhận, bên nhận cần:

- Giới hạn kích thước ciphertext và plaintext tối đa.
- Giới hạn tỷ lệ giữa kích thước sau và trước giải nén.
- Giới hạn thời gian/CPU giải nén.
- Giải nén theo streaming với giới hạn output nếu thư viện hỗ trợ.
- Từ chối dữ liệu vượt ngưỡng và không tiếp tục parse claims.
- Không giải nén nội dung trước khi xác minh và giải mã JWE theo đúng quy trình mật mã.
- Kiểm thử trường hợp dữ liệu nén phình lớn, bị cắt cụt và sai định dạng.

Không chỉ dựa vào kích thước token trên dây. Một JWE nhỏ có thể tạo ra plaintext lớn sau giải nén.

## 10. Rò rỉ qua website và công cụ xem JWT

Nhiều công cụ cho phép dán JWT để decode header và payload. Việc decode có thể hữu ích trong môi trường phát triển, nhưng đưa token thật vào một website hoặc extension bên thứ ba tạo thêm một điểm xử lý dữ liệu.

Rủi ro có thể gồm:

- Trang gửi token đến backend hoặc dịch vụ analytics.
- JavaScript bên thứ ba, quảng cáo, extension hoặc script bị xâm nhập đọc nội dung trang.
- Token còn trong browser history, cache, local storage, session restore hoặc crash report.
- Clipboard manager lưu lịch sử token đã sao chép.
- Screenshot hoặc video màn hình chứa token và claims.
- Token bị lưu trong ticket hỗ trợ, chat, email hoặc tài liệu chia sẻ.
- Người dùng nhầm chức năng decode với verify và tin rằng token hợp lệ chỉ vì payload hiển thị được.

Ngay cả khi một website tuyên bố xử lý hoàn toàn trong trình duyệt, người dùng vẫn phải tin vào toàn bộ mã JavaScript, dependency, extension và phiên bản trang tại thời điểm sử dụng. Không nên dán production bearer token vào công cụ trực tuyến công cộng.

### Decode không phải verify

Công cụ xem JWT thường có thể decode Base64url và hiển thị JSON. Việc đó không chứng minh:

- Chữ ký hợp lệ.
- Issuer đáng tin.
- Audience đúng.
- Token chưa hết hạn hoặc chưa bị thu hồi.
- Claims đáp ứng profile của API.
- Token an toàn để sử dụng.

Chỉ verifier có cấu hình khóa, thuật toán và policy tin cậy mới có thể đưa ra quyết định xác minh phù hợp. Một token viewer không phải Authorization Server hay Resource Server.

## 11. Dùng công cụ debug an toàn

Khi cần phân tích JWT, hãy ưu tiên môi trường và dữ liệu kiểm thử.

### Thực hành an toàn

- Dùng token synthetic hoặc token test được phát hành riêng cho môi trường không production.
- Nếu cần kiểm tra cấu trúc, dùng bản sao đã thay thế toàn bộ giá trị nhạy cảm và không còn giá trị xác thực.
- Ưu tiên công cụ offline/local đã được tổ chức kiểm tra và phê duyệt.
- Kiểm tra rõ công cụ chỉ decode hay thực sự verify; xác minh phải dùng đúng public key và policy.
- Không nhập private key hoặc shared secret production vào website, extension hay công cụ không được quản lý.
- Không để token trong URL, query string, shell command line hoặc file chia sẻ.
- Xóa token khỏi clipboard, DevTools, HAR, screenshot, terminal transcript và ticket sau khi hoàn tất; xử lý các bản sao đã được đồng bộ theo quy trình dữ liệu của tổ chức.
- Giới hạn quyền truy cập và thời gian lưu của diagnostic bundle.

### Cẩn trọng với terminal và script

Token truyền qua command-line argument có thể xuất hiện trong shell history, process listing, audit log hoặc output của công cụ. Token trong environment variable cũng có thể bị lộ qua crash dump, debug endpoint hoặc process inspection tùy môi trường.

Nếu cần tự động hóa kiểm tra, dùng secret manager hoặc cơ chế truyền bí mật được nền tảng hỗ trợ; không hardcode token trong script, repository, CI variable output hoặc lệnh được ghi vào transcript. File tạm cần quyền truy cập chặt, thời gian sống ngắn và quy trình xóa phù hợp; xóa file không bảo đảm mọi bản sao trong backup hoặc filesystem journal đã biến mất.

## 12. Giảm lượng dữ liệu nhạy cảm ngay từ thiết kế token

Phòng ngừa rò rỉ hiệu quả nhất là giảm dữ liệu cần bảo vệ.

- Chỉ đưa claims mà Resource Server cần để đưa ra quyết định.
- Ưu tiên identifier ổn định, ít nhạy cảm thay cho hồ sơ người dùng đầy đủ.
- Không đưa password, API key, refresh token khác hoặc secret vào claims.
- Tránh đưa danh sách quyền rất lớn; cân nhắc tra cứu authorization ở server.
- Dùng audience hẹp và token lifetime phù hợp.
- Phân biệt access token, ID token, assertion và token nội bộ theo profile.
- Dùng JWE khi thực sự cần bảo mật nội dung và có quản lý khóa giải mã phù hợp.
- Không dùng JWE như lý do để log plaintext sau giải mã.
- Cân nhắc opaque/reference token nếu cần giảm dữ liệu self-contained hoặc hỗ trợ thu hồi tập trung.

Nếu một claim không cần thiết cho bên nhận, không nên đưa claim đó vào token chỉ vì tiện.

## 13. Khi phát hiện token đã bị lộ

Cách xử lý phụ thuộc loại dữ liệu bị lộ và phạm vi compromise.

### Chỉ một access token bị lộ

- Xác định issuer, subject, audience, scope, thời hạn và phạm vi sử dụng.
- Thu hồi token/session/token family nếu hệ thống có cơ chế phù hợp.
- Nếu không có thu hồi tức thời, đánh giá rủi ro trong thời gian token còn hiệu lực và áp dụng biện pháp hạn chế.
- Kiểm tra refresh token có bị lộ hay không; nếu có, thu hồi hoặc rotate theo chính sách.
- Điều tra log, trace, ticket, clipboard, HAR và các bản sao liên quan.
- Không mặc định phải xoay signing key nếu private signing key không bị lộ.

### Private signing key hoặc shared secret bị lộ

Đây là sự cố nghiêm trọng hơn token đơn lẻ bị lộ:

- Vô hiệu hóa quyền sử dụng khóa/secret bị compromise.
- Phát hành khóa thay thế và cập nhật verifier theo quy trình khẩn cấp.
- Đánh dấu kid hoặc key version bị thu hồi để verifier từ chối token liên quan.
- Làm mới JWKS/cache và xác nhận mọi vùng đã áp dụng trạng thái mới.
- Đánh giá token giả mạo có thể đã được phát hành trong cửa sổ compromise.
- Thu hồi phiên hoặc yêu cầu xác thực lại theo mức độ ảnh hưởng.

Không thể phân biệt token thật với token giả được ký bằng cùng private key đã bị lộ chỉ bằng cách kiểm tra chữ ký. Cần xử lý toàn bộ phạm vi tin cậy của khóa.

### Claims nhạy cảm bị lộ nhưng token không còn dùng được

Nếu payload JWS chứa dữ liệu cá nhân, việc token hết hạn không làm dữ liệu đã bị sao chép biến mất. Cần đánh giá phạm vi dữ liệu, nơi lưu bản sao, yêu cầu thông báo sự cố và biện pháp giảm thiểu theo chính sách bảo vệ dữ liệu.

## 14. Checklist ngăn rò rỉ JWT

**Lỗi và response**

- Không phản chiếu raw token, decoded payload, secret hoặc key location vào response.
- Dùng error code ổn định và request ID để tra cứu nội bộ.
- Không trả stack trace hoặc exception message thô cho client.
- Kiểm tra mọi nhánh lỗi parser, signature, JWKS, claims và decryption.

**Log và telemetry**

- Redact Authorization, Cookie, Set-Cookie, token fields và assertion trước khi ghi.
- Dùng allowlist cho structured logging.
- Kiểm tra CDN, WAF, gateway, proxy, application, APM, tracing, SIEM và crash reporting.
- Không capture toàn bộ request/response mặc định trong production.
- Giới hạn quyền truy cập, retention, export và backup.
- Chỉ dùng fingerprint HMAC nếu thật sự cần tương quan token.

**Compression**

- Đánh giá zip của JWE và không bật nếu không cần.
- Không nén chung secret với dữ liệu attacker kiểm soát trong cùng context khi có thể quan sát độ dài.
- Đánh giá HTTP response compression theo mô hình BREACH.
- Đặt giới hạn kích thước sau giải nén, compression ratio và tài nguyên xử lý.
- Không cho rằng TLS che giấu mọi side-channel về kích thước.

**Công cụ và vận hành**

- Không dán production token vào website decoder, extension, chat hoặc ticket công cộng.
- Dùng synthetic token và công cụ offline được phê duyệt.
- Không để token trong URL, shell history, command arguments, screenshot hoặc HAR.
- Kiểm tra clipboard, browser DevTools và diagnostic bundles.
- Khi lộ token, thu hồi credential theo phạm vi; chỉ xoay signing key nếu khóa ký/secret thực sự bị compromise.
- Kiểm thử định kỳ để xác nhận token và claims không xuất hiện trong log hoặc response.

**Ghi nhớ:** JWS payload có thể đọc được dù chữ ký hợp lệ; JWE bảo vệ nội dung nhưng không loại bỏ nguy cơ token bị lộ, log plaintext hoặc side-channel. Error response, log, trace, compression, token viewer và công cụ debug đều có thể trở thành đường rò rỉ. Hãy giảm claims, redaction trước khi ghi, tránh đưa token production vào công cụ bên thứ ba, đánh giá compression theo threat model và có quy trình thu hồi phù hợp khi credential bị lộ.

### Tài liệu chuẩn để tra cứu

- **RFC 7515 — JSON Web Signature (JWS):** cấu trúc JWS Compact và protected header/payload/signature.
- **RFC 7516 — JSON Web Encryption (JWE):** mã hóa JWE và tham số zip cho compression.
- **RFC 7519 — JSON Web Token (JWT):** JWT claims và cách biểu diễn token.
- **RFC 8725 — JSON Web Token Best Current Practices:** giảm rủi ro khi phát hành và xử lý JWT.
- **RFC 9110 — HTTP Semantics:** HTTP fields và hành vi thông điệp HTTP.
- **RFC 9111 — HTTP Caching:** lưu cache và các rủi ro liên quan đến dữ liệu nhạy cảm trong response.
- **RFC 7541 — HPACK: Header Compression for HTTP/2:** cơ chế nén header HTTP/2.
- **RFC 9113 — HTTP/2:** xử lý header fields nhạy cảm và quy tắc không index field Authorization.
- **RFC 9204 — QPACK: Field Compression for HTTP/3:** nén header HTTP/3 và biểu diễn never-indexed.
