# Alert token theft indicators

Token theft thường không xuất hiện dưới dạng một lỗi xác thực rõ ràng. Kẻ tấn công có thể dùng access token hợp lệ bị đánh cắp để gọi API, vì chữ ký, thời hạn và issuer của token vẫn đúng. Hệ thống cần quan sát cách token được sử dụng, phát hiện các dấu hiệu bất thường, liên kết sự kiện giữa Authorization Server và Resource Server, rồi cảnh báo theo mức độ rủi ro.

Bài học thuộc chương **Observability** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là xây dựng telemetry đủ để phát hiện token theft và replay, đặc biệt với JWT, opaque access token và refresh token trong OAuth 2.0/OIDC, đồng thời bảo vệ bí mật và dữ liệu người dùng trong log, metric và trace.

## 1. Vì sao cần phát hiện token theft?

Access token dạng Bearer cho phép bên giữ token sử dụng token theo phạm vi đã cấp. Nếu token bị lộ qua log, browser storage, thiết bị bị xâm nhập, proxy hoặc malware, kẻ tấn công có thể gửi lại token cho API cho đến khi token hết hạn, bị thu hồi hoặc bị chặn bởi một cơ chế ràng buộc bổ sung.

Một số tình huống thường gặp:

- Kẻ tấn công lấy access token từ thiết bị hoặc bộ nhớ trình duyệt rồi gọi API từ một mạng khác.
- Refresh token bị đánh cắp và được sử dụng để xin access token mới.
- Một token bị phát lại đồng thời từ nhiều địa điểm hoặc nhiều thiết bị.
- Token đã bị thu hồi nhưng một Resource Server vẫn chấp nhận do cache hoặc đồng bộ trạng thái chậm.
- Một client/service vốn chỉ gọi một nhóm API bắt đầu truy cập endpoint hoặc phạm vi dữ liệu bất thường.

**Không có một chỉ báo đơn lẻ nào luôn chứng minh token đã bị đánh cắp.** Địa chỉ IP thay đổi có thể do mạng di động, VPN, NAT hoặc roaming; user-agent có thể thay đổi sau khi cập nhật trình duyệt; một người dùng có thể làm việc từ nhiều thiết bị. Hệ thống nên kết hợp nhiều tín hiệu, baseline hành vi, mức độ nhạy cảm của hành động và thông tin xác thực bổ sung trước khi khóa tài khoản hoặc thu hồi phiên.

## 2. Phân biệt sự kiện, chỉ báo và kết luận

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Security event | Một sự kiện đã xảy ra và được ghi nhận | Access token được dùng tại `orders-api` |
| Indicator | Dấu hiệu có thể liên quan đến tấn công | Cùng token xuất hiện từ hai khu vực địa lý xa trong khoảng thời gian ngắn |
| Correlation | Kết hợp nhiều sự kiện theo chủ thể/token/client/thời gian | Refresh token reuse đi cùng access token mới từ ASN lạ |
| Alert | Thông báo cần người hoặc hệ thống xử lý | Nghi ngờ refresh token family bị compromise |
| Incident | Sự cố đã được điều tra và xác nhận theo quy trình | Credential bị lộ và được dùng trái phép |

Alert nên diễn đạt mức độ chắc chắn: **nghi ngờ**, **rủi ro cao** hoặc **đã xác nhận**. Không đổi tên một anomaly thành “token stolen” khi chưa có bằng chứng. Cách đặt tên đúng giúp đội vận hành tránh phản ứng quá mức với các thay đổi hành vi hợp lệ.

## 3. Những chỉ báo token theft và replay

### 3.1. Một token được sử dụng từ nhiều vị trí không tương thích

Nếu cùng một token fingerprint xuất hiện ở hai khu vực địa lý rất xa trong khoảng thời gian không thể di chuyển hợp lý, đó là tín hiệu đáng chú ý. Ví dụ, một token được dùng tại Việt Nam rồi vài phút sau được dùng tại một quốc gia khác.

Để giảm false positive:

- So sánh thời gian, khoảng cách, ASN và loại mạng thay vì chỉ dựa vào country code.
- Tính đến VPN doanh nghiệp, Secure Web Gateway, mobile carrier NAT và proxy tập trung.
- Xem xét cùng token có được sử dụng đồng thời hay chỉ là hai request kế tiếp sau khi người dùng chuyển mạng.
- Kết hợp với thiết bị, client ID, DPoP/mTLS binding và hành động được thực hiện.

### 3.2. Sử dụng đồng thời hoặc tăng đột biến

Một token thường có nhịp sử dụng tương đối ổn định. Các dấu hiệu bất thường gồm:

- Số request đồng thời tăng mạnh so với baseline của chủ thể hoặc client.
- Token xuất hiện trên nhiều thiết bị hoặc user-agent khác nhau trong một cửa sổ ngắn.
- Tốc độ gọi API tăng đột ngột, đặc biệt với endpoint export, download hoặc truy cập dữ liệu nhạy cảm.
- Cùng token được dùng để truy cập nhiều tenant hoặc nhiều nhóm tài nguyên vốn không thuộc hành vi thông thường.

Burst traffic có thể do retry, batch job hoặc lỗi client. Cần đối chiếu request ID, retry pattern, client identity và lịch triển khai trước khi kết luận.

### 3.3. Refresh token reuse sau rotation

Với refresh token rotation, Authorization Server phát hành refresh token mới và vô hiệu hóa token cũ sau mỗi lần sử dụng thành công. Nếu token cũ được gửi lại sau khi đã xoay vòng, đây là dấu hiệu mạnh cho thấy token có thể đã bị sao chép hoặc client có lỗi lưu trữ/đồng bộ.

Khi phát hiện reuse:

1. Ghi nhận refresh token family, client ID, subject, thời điểm và kết quả kiểm tra.
2. Đánh giá chính sách rotation và grace period (nếu hệ thống có hỗ trợ) để phân biệt retry hợp lệ với replay.
3. Áp dụng chính sách của Authorization Server, thường là vô hiệu hóa token family liên quan và yêu cầu xác thực lại.
4. Phát cảnh báo có độ ưu tiên cao nếu reuse đi cùng IP/ASN/device bất thường hoặc có access token mới được sử dụng.

Không ghi refresh token nguyên văn vào log. Việc nhận diện reuse phải dựa trên trạng thái token family hoặc fingerprint bảo vệ bằng HMAC, không dựa vào việc lưu bearer credential dạng rõ.

### 3.4. Token tiếp tục hoạt động sau khi bị thu hồi

Một access token bị sử dụng thành công sau thời điểm thu hồi có thể chỉ ra:

- Resource Server chưa kiểm tra trạng thái thu hồi hoặc chưa nhận được cập nhật.
- Cache introspection hoặc authorization quá lâu.
- Đồng hồ giữa các thành phần lệch nhau.
- Token bị đánh cắp và đang được sử dụng trước khi trạng thái thu hồi có hiệu lực.
- Một API hoặc gateway đang bỏ qua middleware xác minh chung.

Đây vừa là tín hiệu bảo mật vừa là tín hiệu lỗi kiến trúc. Cần đối chiếu thời điểm revoke, propagation delay, cache TTL và log xác thực ở từng Resource Server.

### 3.5. Bất thường về scope, audience hoặc loại token

Các request bị từ chối vì sai audience, sai loại token, scope không hợp lệ hoặc issuer không được tin cậy có thể cho thấy client bị cấu hình sai, token confusion hoặc hành vi dò quét. Nếu một client vốn chỉ dùng `orders:read` liên tục thử các scope quản trị hoặc gửi ID token/refresh token tới Resource Server, nên tạo cảnh báo theo tần suất và nguồn phát.

Token validation failure không tự động chứng minh token theft. Nhưng nếu có thêm dấu hiệu truy cập nhiều endpoint, nhiều tenant hoặc nhiều subject, mức rủi ro tăng lên.

### 3.6. Proof-of-possession không khớp

Với DPoP hoặc certificate-bound access token, API có thể kiểm tra proof hoặc chứng thư gắn với token. Các sự kiện đáng chú ý gồm:

- Thumbprint chứng thư mTLS không khớp claim confirmation trong token.
- DPoP proof dùng key khác với key đã ràng buộc access token.
- DPoP proof bị replay, sai nonce hoặc sai HTTP method/URI theo chính sách.
- Một token bị gửi từ nhiều key khác nhau trong thời gian ngắn.

Các lỗi này có thể là lỗi client hoặc clock/nonce synchronization. Tuy vậy, nếu lặp lại từ nhiều nguồn hoặc đi cùng hành vi đáng ngờ, cần cảnh báo có mức độ ưu tiên cao.

## 4. Thiết kế security event cho token

Muốn correlation chính xác, các thành phần phải phát ra sự kiện có schema nhất quán. Một event có thể chứa:

| Field | Mục đích | Lưu ý |
| --- | --- | --- |
| `event_time` | Thời điểm sự kiện theo UTC | Đồng bộ clock giữa các dịch vụ |
| `event_name` | Loại sự kiện | Ví dụ `token.accepted`, `token.rejected`, `refresh.reuse_detected` |
| `service.name` | Dịch vụ phát sự kiện | Tên service ổn định |
| `issuer_id` | Issuer đã xác minh | Dùng định danh cấu hình, tránh tin issuer tùy ý từ token lỗi |
| `subject_ref` | Tham chiếu subject | Pseudonymize nếu không cần user ID trực tiếp |
| `client_id` | OAuth client hoặc service client | Không ghi client secret |
| `token_fingerprint` | Liên kết các lần dùng cùng token | HMAC fingerprint, không ghi token thô |
| `jti` | Định danh JWT nếu có | Chỉ ghi nếu issuer bảo đảm không chứa dữ liệu nhạy cảm; kiểm soát quyền truy cập |
| `audience` | Resource server dự định nhận token | Chuẩn hóa giá trị |
| `scope_set` | Quyền được cấp/được yêu cầu | Chỉ ghi scope cần thiết; tránh log claim nhạy cảm |
| `auth_result` | Kết quả xác thực | `accepted`, `rejected`, `revoked`, `introspection_error` |
| `reason_code` | Lý do chuẩn hóa | `expired`, `bad_audience`, `revoked`, `proof_mismatch` |
| `source_ip` / `asn` | Ngữ cảnh nguồn | Bảo vệ như dữ liệu nhạy cảm; cân nhắc retention và masking |
| `device_ref` | Tham chiếu thiết bị | Không dùng raw fingerprint có thể nhận diện người dùng nếu không cần |
| `request_id` | Liên kết request giữa gateway và service | Tránh dùng token làm request ID |
| `tenant_ref` | Tenant được ủy quyền | Chỉ ghi tenant đã được xác minh theo policy |

Ví dụ event đã loại bỏ bí mật:

~~~json
{
  "event_time": "2026-11-23T10:15:30Z",
  "event_name": "token.accepted",
  "service.name": "orders-api",
  "issuer_id": "primary-oidc",
  "subject_ref": "sub-hmac:4f8a...",
  "client_id": "web-client",
  "token_fingerprint": "hmac-v3:91bd...",
  "audience": ["orders-api"],
  "scope_set": ["orders:read"],
  "auth_result": "accepted",
  "source_ip": "203.0.113.24",
  "asn": 64500,
  "device_ref": "device-hmac:18c2...",
  "request_id": "req-7a92",
  "tenant_ref": "tenant-42"
}
~~~

Địa chỉ IP và ASN trong ví dụ là dữ liệu minh họa. Trong môi trường thật, cần xác định nguồn IP đáng tin cậy tại ingress/proxy và chỉ tin header forwarding do proxy được quản lý ghi vào. Không lấy `X-Forwarded-For` do client tự gửi làm bằng chứng nguồn IP.

## 5. Bảo vệ log, metric và trace

**Không ghi raw access token, refresh token, ID token, authorization code, client secret, private key hoặc toàn bộ Authorization header.** Token thường là bearer credential; log có thể được sao chép sang nhiều hệ thống, lưu lâu và được nhiều người truy cập.

Để liên kết các sự kiện mà không lưu token:

- Dùng HMAC-SHA-256 với khóa riêng cho telemetry để tạo fingerprint ổn định trong phạm vi cần correlation.
- Lưu `key_version` hoặc prefix phiên bản để hỗ trợ xoay khóa HMAC.
- Không dùng plain SHA-256 làm lựa chọn mặc định nếu muốn tránh tạo fingerprint có thể liên kết qua nhiều hệ thống; HMAC giúp kiểm soát khả năng tạo fingerprint.
- Phân quyền truy cập log, mã hóa dữ liệu lưu trữ, đặt retention theo mục đích điều tra và audit truy cập.
- Che hoặc pseudonymize subject, IP, device identifier và tenant identifier khi không cần giá trị gốc.

Metrics nên dùng label có cardinality thấp, chẳng hạn service, kết quả, reason code, grant type hoặc audience đã chuẩn hóa. Không đưa token fingerprint, user ID, IP, `jti`, request ID hoặc device ID vào metric labels vì số lượng giá trị có thể tăng không giới hạn và làm hệ thống metrics quá tải.

Trace có thể ghi span event như `token.validation` hoặc `authorization.decision`, nhưng không thêm bearer token vào span attribute, baggage hoặc exception message. Trace ID giúp nối các thành phần của một request; token fingerprint chỉ nên xuất hiện trong security event có kiểm soát nếu thực sự cần correlation.

## 6. Tạo baseline và risk score

Baseline mô tả hành vi thông thường của subject, client hoặc service trong một khoảng thời gian. Có thể theo dõi:

- Số request thành công theo phút/giờ và nhóm API.
- Tập ASN/khu vực thường dùng, có xét VPN và mạng di động.
- Số thiết bị hoặc user-agent thường gặp.
- Tần suất refresh token và thời điểm sử dụng.
- Phạm vi audience, scope, tenant và hành động nghiệp vụ.
- Tỷ lệ lỗi xác thực, lỗi authorization và proof-of-possession failure.

Không nên tạo baseline chỉ từ một vài request đầu tiên. Dùng thời gian quan sát đủ dài, loại bỏ giai đoạn triển khai hoặc sự cố, và cập nhật có kiểm soát để kẻ tấn công không dễ làm lệch baseline.

Một mô hình risk score đơn giản có thể cộng điểm theo chỉ báo:

| Chỉ báo | Điểm minh họa | Lý do |
| --- | ---: | --- |
| Cùng token fingerprint ở hai khu vực không thể di chuyển trong thời gian ngắn | +40 | Dấu hiệu replay mạnh |
| Refresh token cũ bị dùng lại sau rotation | +50 | Có thể là token family compromise |
| Proof-of-possession hoặc certificate binding mismatch | +40 | Credential không đi cùng khóa được ràng buộc |
| ASN/thiết bị mới so với baseline | +10 | Dấu hiệu yếu, dễ false positive |
| Tốc độ gọi API tăng bất thường | +15 | Có thể là automation hoặc replay |
| Token bị dùng sau khi revoke | +40 | Có thể có replay hoặc propagation failure |

Điểm số chỉ là ví dụ minh họa, cần hiệu chỉnh theo dữ liệu thật. Một hệ thống có thể dùng mức:

- **Low:** ghi nhận và tiếp tục theo dõi.
- **Medium:** tăng giám sát, yêu cầu xác thực bổ sung hoặc step-up authentication.
- **High:** thu hồi token family/phiên theo policy, chặn request rủi ro và mở incident.
- **Critical:** có nhiều bằng chứng compromise hoặc truy cập dữ liệu nhạy cảm; kích hoạt quy trình ứng phó sự cố.

Một số chỉ báo mạnh như refresh token reuse hoặc binding mismatch có thể kích hoạt hành động bảo vệ ngay theo policy, không nhất thiết phải chờ tổng điểm. Cần tách ngưỡng tạo alert khỏi ngưỡng tự động thu hồi để tránh false positive gây khóa hàng loạt người dùng.

## 7. Quy tắc cảnh báo thực tế

Các quy tắc nên có cửa sổ thời gian, ngưỡng, nhóm đối tượng và điều kiện loại trừ rõ ràng. Ví dụ:

| Alert | Điều kiện gợi ý | Ưu tiên |
| --- | --- | --- |
| `TOKEN_REPLAY_GEO` | Một fingerprint được chấp nhận từ hai vùng xa trong cửa sổ ngắn, vận tốc di chuyển không hợp lý và không thuộc egress VPN đã biết | High |
| `REFRESH_TOKEN_REUSE` | Refresh token đã bị rotate/revoke nhưng xuất hiện lại | High/Critical |
| `TOKEN_BINDING_MISMATCH` | DPoP key hoặc certificate thumbprint không khớp token binding | High |
| `REVOKED_TOKEN_ACCEPTED` | Resource Server chấp nhận token sau thời điểm revoke đã được xác nhận | High |
| `TOKEN_USAGE_SPIKE` | Request rate hoặc số endpoint khác biệt lớn so với baseline | Medium |
| `UNUSUAL_SCOPE_PROBING` | Client liên tục thử scope/endpoint ngoài profile được cấp | Medium |
| `AUTH_FAILURE_BURST` | Nhiều token validation failure từ một client/IP/ASN trong cửa sổ ngắn | Medium |

Ví dụ logic correlation giả mã:

~~~text
WINDOW = 5 minutes

for each token_fingerprint:
    events = accepted_requests(token_fingerprint, WINDOW)
    if distinct_trusted_regions(events) >= 2
       and geo_distance(events) is implausible_for_elapsed_time
       and not known_corporate_egress(events):
        emit_alert("TOKEN_REPLAY_GEO", severity="high")

for each refresh_token_family:
    if event == "refresh.reuse_detected":
        emit_alert("REFRESH_TOKEN_REUSE", severity="high")
        apply_refresh_family_policy(refresh_token_family)
~~~

Logic này mô tả cách correlation, không phải query chạy trực tiếp trên một SIEM cụ thể. Khi triển khai, cần dùng event time thay vì thời điểm ingest để xử lý log đến trễ; chuẩn hóa timezone; xử lý duplicate; giới hạn alert lặp; và giữ evidence để điều tra.

## 8. Dashboard quan sát token security

Dashboard nên giúp đội vận hành trả lời ba câu hỏi: token đang được sử dụng thế nào, có dấu hiệu bị lạm dụng không, và hệ thống xác minh/thu hồi có hoạt động đúng không.

Các nhóm panel hữu ích:

1. **Token validation:** số lần accepted/rejected theo service, issuer và reason code.
2. **Token lifecycle:** access token issuance, refresh success/failure, rotation, revoke và reuse detection.
3. **Anomaly:** token fingerprint đa vùng, thiết bị mới, ASN mới, request spike, proof mismatch.
4. **Authorization:** scope denial, tenant mismatch, truy cập tài nguyên nhạy cảm bị từ chối.
5. **Control health:** introspection latency/error, JWKS refresh, clock skew, revoke propagation delay, certificate/DPoP validation failures.
6. **Response:** alert theo severity, thời gian phát hiện, thời gian thu hồi và số incident đang mở.

Metric ví dụ:

~~~text
token_validation_total{service="orders-api",result="rejected",reason="expired"}
refresh_token_reuse_total{client_type="public"}
token_revocation_propagation_seconds{service="orders-api"}
token_binding_failure_total{method="mtls"}
token_introspection_duration_seconds{result="success"}
~~~

Các metric trên chỉ dùng nhãn có số lượng giá trị giới hạn. Không thêm token, subject, địa chỉ IP hoặc tenant ID làm label. Dashboard cần phân quyền vì ngay cả metadata đã pseudonymize vẫn có thể tiết lộ thói quen truy cập và mối quan hệ giữa các tài khoản.

## 9. Quy trình xử lý khi phát hiện token nghi bị đánh cắp

Khi alert được tạo, quy trình phản ứng cần có bước xác minh và containment theo mức rủi ro:

1. **Xác minh tín hiệu:** kiểm tra event gốc, request ID, token fingerprint, subject/client tham chiếu, thời gian, ASN, thiết bị và các rule loại trừ.
2. **Đánh giá phạm vi:** xác định token, token family, client, subject, tenant, API và dữ liệu đã truy cập.
3. **Ngăn chặn:** thu hồi token hoặc refresh token family theo policy; chặn request hoặc client bị compromise; yêu cầu xác thực lại/step-up khi phù hợp.
4. **Kiểm tra propagation:** xác minh Resource Server, gateway và cache đã nhận trạng thái thu hồi; kiểm tra không còn node chấp nhận token.
5. **Bảo toàn evidence:** lưu security event, audit record, correlation ID và thời điểm hành động; không sao chép token nguyên văn vào ticket.
6. **Khôi phục:** đổi credential hoặc secret có liên quan nếu bị lộ, kiểm tra thiết bị/client, khôi phục quyền sau khi xác minh an toàn.
7. **Học từ sự cố:** xác định token lộ ở đâu, khoảng thời gian tồn tại, điểm thiếu telemetry và cải thiện policy/alert.

Không phải mọi anomaly đều cần khóa tài khoản. Với dấu hiệu yếu, có thể tăng giám sát hoặc yêu cầu step-up. Với refresh token reuse, proof mismatch có độ tin cậy cao hoặc truy cập dữ liệu nhạy cảm trái phép, hành động containment cần nhanh hơn và theo policy đã thống nhất.

## 10. Kiểm thử alert trước khi đưa vào production

Alert rule phải được kiểm thử bằng event fixture hoặc môi trường tích hợp để xác nhận cả trường hợp phát hiện và không phát hiện:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Cùng token dùng từ hai khu vực không tương thích trong vài phút | Alert replay địa lý |
| Người dùng chuyển từ Wi-Fi sang mobile network, vùng vẫn gần và không có tín hiệu khác | Không tạo alert high chỉ vì IP đổi |
| Refresh token cũ được dùng lại sau rotation | Alert refresh reuse và policy token family được thực thi |
| Hai request retry hợp lệ trong grace period đã định nghĩa | Không gắn nhãn compromise nếu policy xác nhận retry hợp lệ |
| DPoP key hoặc mTLS certificate không khớp token binding | Alert binding mismatch |
| Token bị revoke nhưng API vẫn chấp nhận do cache quá hạn | Alert revoke propagation/control failure |
| Client có burst do batch job đã đăng ký | Rule nhận diện workload hợp lệ hoặc giảm mức cảnh báo |
| Scope probing lặp lại từ client lạ | Alert unusual scope probing |
| Log pipeline nhận Authorization header | Bộ lọc phải redact trước khi lưu |
| Metric chứa token fingerprint hoặc user ID | Kiểm tra phải thất bại; label không được có dữ liệu cardinality cao |

Nên chạy rule ở chế độ observe-only trước khi tự động khóa hoặc revoke diện rộng. Đo precision, recall, false positive, thời gian phát hiện và tác động lên người dùng. Sau khi hiệu chỉnh, triển khai theo từng nhóm client/service và giữ cơ chế rollback.

## 11. Checklist triển khai

- [ ] Resource Server và Authorization Server phát security event nhất quán.
- [ ] Event có timestamp, service, subject/client reference, kết quả và reason code.
- [ ] Có token fingerprint HMAC để correlation khi thực sự cần.
- [ ] Không log raw access token, refresh token, ID token hoặc Authorization header.
- [ ] Metric labels có cardinality thấp; không chứa token/user/IP/request ID.
- [ ] Có rule refresh token reuse và policy xử lý token family.
- [ ] Có rule phát hiện cùng token từ vị trí/thiết bị không tương thích.
- [ ] Có rule cho DPoP/mTLS binding mismatch nếu hệ thống sử dụng proof-of-possession.
- [ ] Theo dõi revoke propagation, introspection và cache behavior.
- [ ] Có baseline theo client/service/subject và xử lý VPN, NAT, mobile network.
- [ ] Alert nêu rõ mức độ chắc chắn, severity, evidence và owner xử lý.
- [ ] Có playbook xác minh, containment, revoke, kiểm tra propagation và khôi phục.
- [ ] Đã kiểm thử false positive, duplicate event, log đến trễ và alert storm.
- [ ] Có retention, access control và audit cho dữ liệu observability.

## 12. Tình huống tổng hợp

Một người dùng đăng nhập từ laptop và nhận access token. Trong vài phút, cùng token fingerprint được chấp nhận tại `orders-api` từ mạng văn phòng ở Việt Nam và một ASN lạ ở khu vực cách xa. Cùng thời điểm, số request export hóa đơn tăng mạnh. Hệ thống cũng ghi nhận refresh token cũ của cùng token family được gửi lại sau khi đã rotation.

Không nên chỉ dựa vào IP khác để kết luận. Nhưng ba tín hiệu kết hợp — cùng token ở hai vùng không tương thích, hành vi export tăng đột biến và refresh token reuse — tạo mức rủi ro cao. Hệ thống cần phát alert, kiểm tra event liên quan, thu hồi token family theo policy, xác minh revoke đã lan đến Resource Server và điều tra các dữ liệu đã được truy cập.

**Điều cần nhớ:** observability không thể tự ngăn token bị đánh cắp. Nó giúp hệ thống phát hiện dấu hiệu sử dụng bất thường, rút ngắn thời gian phát hiện, cung cấp evidence và kích hoạt phản ứng phù hợp. Chất lượng phát hiện phụ thuộc vào event an toàn, correlation đáng tin cậy, baseline phù hợp và quy trình xử lý đã được kiểm thử.

## 13. Tài liệu chuẩn tham khảo

- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): khuyến nghị bảo mật OAuth 2.0, gồm bảo vệ refresh token và phát hiện reuse trong rotation.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): ràng buộc proof với khóa client và cơ chế phát hiện proof replay.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): certificate-bound access token và mTLS.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): metadata trạng thái token cho Resource Server.
- [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/): mô hình telemetry cho metrics, traces và logs.
