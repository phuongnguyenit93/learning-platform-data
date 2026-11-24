# TLS certificate expiry: Theo dõi và xử lý chứng thư sắp hết hạn

## 1. Mục tiêu vận hành

Hệ thống xác thực và phân quyền dựa vào nhiều kết nối TLS: ứng dụng gọi Authorization Server, resource server gọi introspection endpoint, client tải JWKS, dịch vụ trao đổi token gọi STS, và các thành phần có thể xác thực lẫn nhau bằng mutual TLS (mTLS). Nếu chứng thư TLS hết hạn, sai hostname hoặc chuỗi tin cậy không còn hợp lệ, handshake có thể thất bại. Hậu quả là người dùng không lấy được token, API không introspect được opaque token, service-to-service request bị từ chối hoặc hệ thống không tải được khóa xác minh JWT.

**TLS certificate expiry** là chủ đề vận hành nhằm phát hiện sớm chứng thư sắp hết hạn, gia hạn và triển khai chứng thư mới an toàn, xác minh toàn bộ đường kết nối sau khi thay đổi. Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học liên hệ trực tiếp chứng thư TLS với mô hình tin cậy và vòng đời token: bảo vệ token khi truyền, xác thực server/client, duy trì khả năng truy cập token endpoint, introspection và JWKS.

Sau bài học, người học có thể:

- Xác định các endpoint và kết nối TLS ảnh hưởng đến phát hành, kiểm tra và sử dụng token.
- Theo dõi ngày hết hạn, hostname/SAN, issuer, chain và mục đích sử dụng của certificate.
- Thiết kế cảnh báo theo nhiều mốc thời gian và kiểm tra từ góc nhìn client thực tế.
- Gia hạn, phân phối và xoay chứng thư mà không làm gián đoạn luồng OAuth/OIDC.
- Xử lý sự cố handshake, truststore, mTLS và lỗi certificate rotation.
- Phân biệt TLS certificate với khóa ký JWT/JWK để tránh xoay nhầm loại khóa.

## 2. Chứng thư TLS bảo vệ những kết nối nào?

TLS tạo kênh truyền được mã hóa và xác thực peer theo certificate chain. Trong mô hình token security, cần lập danh mục tất cả các kết nối có liên quan:

| Kết nối | Vai trò trong vòng đời token | Rủi ro khi certificate hết hạn |
| --- | --- | --- |
| Client → Authorization Server | Đăng nhập, authorization endpoint, token endpoint | Không lấy được access token/refresh token |
| Resource Server → Introspection endpoint | Kiểm tra trạng thái opaque token | Token không được xác minh; API có thể từ chối request |
| Resource Server → JWKS endpoint | Tải public keys để xác minh JWT khi JWKS được phân phối qua HTTPS | Không tải được key mới hoặc refresh cache |
| Service → STS/token exchange endpoint | Đổi token cho audience/resource khác | Luồng token exchange thất bại |
| Service → Service bằng mTLS | Xác thực cả server và client ở tầng TLS | Handshake bị từ chối khi cert client/server hết hạn hoặc không tin cậy |
| Gateway/Ingress → backend | Bảo vệ traffic giữa các tầng | Lỗi TLS có thể làm gián đoạn token API hoặc resource API |
| Monitoring/automation → endpoint | Probe health và thu thập trạng thái | Không phát hiện được lỗi hoặc chính monitoring bị mất kết nối |

Danh mục cần bao gồm cả certificate ở load balancer, ingress, reverse proxy, service mesh, application keystore, truststore và client certificate. Một endpoint có thể kết thúc TLS ở gateway; khi đó cần theo dõi cả chứng thư public tại gateway và chứng thư riêng trên kết nối gateway → backend nếu kết nối này cũng dùng TLS.

Không phải mọi hệ thống đều dùng mTLS hoặc cùng một vị trí terminate TLS. Hãy lập bản đồ theo kiến trúc triển khai thật, xác định chủ sở hữu, nơi lưu private key, nơi phân phối certificate và dịch vụ phụ thuộc.

### 2.1 Phân biệt certificate TLS với khóa ký token

Đây là điểm dễ nhầm khi vận hành:

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| TLS server certificate | Xác thực máy chủ trong TLS handshake và thiết lập kênh bảo mật | Certificate cho auth.example.internal |
| TLS client certificate | Xác thực client khi dùng mTLS | Certificate của orders-api |
| JWT signing key | Ký JWT để resource server xác minh tính toàn vẹn và issuer | RSA/EC private key có kid trong JWKS |
| JWT verification key | Public key để xác minh chữ ký JWT | JWK public key được công bố qua JWKS |

Gia hạn TLS certificate của Authorization Server không tự động xoay JWT signing key. Xoay signing key cũng không tự động thay certificate của HTTPS endpoint. Nếu hệ thống dùng X.509 certificate để mang public key hoặc trường x5c trong JWK, cần xem rõ từng mục đích và chính sách trust; không suy ra hai vòng đời giống nhau.

Khi TLS certificate hết hạn, TLS handshake có thể thất bại trước khi ứng dụng kịp gửi token. Khi JWT signing key bị xoay hoặc ngừng tin cậy, token có thể bị từ chối ở bước kiểm tra chữ ký dù HTTPS vẫn hoạt động. Hai loại sự cố cần runbook và metric riêng.

## 3. Những thuộc tính cần theo dõi

Không chỉ kiểm tra ngày hết hạn. Một certificate còn hạn nhưng không phù hợp hostname, thiếu intermediate CA hoặc sai Extended Key Usage vẫn có thể gây lỗi.

| Thuộc tính | Ý nghĩa | Kiểm tra vận hành |
| --- | --- | --- |
| Not Before / Not After | Khoảng thời gian certificate có hiệu lực | Còn hiệu lực theo UTC; cảnh báo trước Not After |
| Subject Alternative Name (SAN) | Tên DNS/IP mà certificate bảo vệ | SAN khớp hostname client thực sự gọi |
| Issuer | CA phát hành certificate | Nằm trong trust chain được phép |
| Serial Number / Fingerprint | Định danh certificate cụ thể | Nhận biết bản mới/cũ khi deploy |
| Basic Constraints | Xác định CA hay end-entity | Chain có cấu trúc hợp lệ |
| Key Usage / Extended Key Usage | Mục đích sử dụng key/certificate | Server Authentication hoặc Client Authentication đúng vai trò |
| Signature Algorithm / Key Size | Thuật toán và độ mạnh khóa | Phù hợp baseline bảo mật hiện hành |
| Chain | Leaf, intermediate và root trust anchor | Đủ intermediate; root được truststore tin cậy |
| OCSP/CRL (nếu áp dụng) | Trạng thái thu hồi certificate | Có thể truy cập và xử lý theo policy |
| Private key | Khóa bí mật tương ứng certificate | Có mặt đúng nơi, quyền đọc tối thiểu, không lộ ra log |

Thời gian phải được so sánh theo UTC và đồng hồ máy chủ cần đồng bộ. Clock lệch có thể khiến certificate bị coi là chưa có hiệu lực hoặc đã hết hạn dù lịch thực tế chưa đến mốc. Cảnh báo nên dùng số ngày còn lại từ thời điểm UTC và lưu timestamp quan sát.

## 4. Theo dõi thời hạn certificate

### 4.1 Lập inventory có chủ sở hữu

Mỗi certificate nên có một bản ghi quản lý gồm:

- Tên dịch vụ và endpoint/hostname.
- Môi trường (development, staging, production).
- Loại certificate (server, client/mTLS, intermediate nếu tổ chức quản lý).
- Serial number hoặc fingerprint hiện tại.
- Not Before, Not After và số ngày còn lại.
- Issuer/CA, SAN, EKU và vị trí terminate TLS.
- Nơi lưu private key/secret reference; không ghi nội dung private key.
- Chủ sở hữu kỹ thuật và đội chịu trách nhiệm gia hạn.
- Phương thức phát hành/gia hạn (ACME, CA nội bộ, cloud certificate manager).
- Quy trình phân phối, reload và rollback.
- Các dịch vụ phụ thuộc, truststore và client certificate liên quan.

Không dùng một danh sách certificate thủ công làm nguồn duy nhất nếu hệ thống có thể tự khám phá certificate đang được phục vụ. So sánh inventory mong đợi với certificate quan sát được từ mạng và từ workload để phát hiện trường hợp gia hạn thành công ở secret store nhưng ingress vẫn đang phục vụ certificate cũ.

### 4.2 Ngưỡng cảnh báo

Ngưỡng cụ thể phụ thuộc chu kỳ phát hành, SLA của CA, khả năng tự động gia hạn và thời gian triển khai. Ví dụ chính sách:

| Thời gian còn lại | Mức cảnh báo | Hành động |
| --- | --- | --- |
| 30 ngày | Informational | Tạo việc gia hạn, xác nhận owner và dependency |
| 14 ngày | Warning | Kiểm tra CA/automation, xác minh private key và kế hoạch triển khai |
| 7 ngày | High | Hoàn tất gia hạn ở staging, xác nhận thời gian rollout production |
| 72 giờ | Critical | Escalate owner/on-call, ưu tiên deploy và kiểm tra từng endpoint |
| 24 giờ hoặc đã hết hạn | Emergency | Kích hoạt runbook khẩn cấp, đánh giá ảnh hưởng và khôi phục kết nối |

Đây là ngưỡng tham khảo, không phải tiêu chuẩn bắt buộc. Với certificate ngắn hạn được tự động gia hạn liên tục, nên cảnh báo khi renewal job thất bại hoặc certificate còn ít hơn một tỷ lệ của chu kỳ. Với certificate CA/intermediate hoặc client certificate phân phối rộng, cần thời gian báo trước dài hơn vì cập nhật truststore và rollout có thể mất nhiều ngày.

### 4.3 Kiểm tra certificate từ bên ngoài

OpenSSL có thể xem certificate mà endpoint đang phục vụ:

~~~bash
openssl s_client -connect auth.example.internal:443 +  -servername auth.example.internal -showcerts </dev/null
~~~

Để đọc thời hạn và SAN từ certificate đã lưu:

~~~bash
openssl x509 -in server-cert.pem -noout +  -subject -issuer -serial -dates -ext subjectAltName
~~~

Để xem fingerprint:

~~~bash
openssl x509 -in server-cert.pem -noout -fingerprint -sha256
~~~

Để xác minh chain với CA bundle phù hợp:

~~~bash
openssl verify -CAfile trusted-ca-bundle.pem server-cert.pem
~~~

Các lệnh trên chỉ là ví dụ chẩn đoán; cần dùng đúng SNI, port, CA bundle và hostname của môi trường. Lệnh xem certificate không tự chứng minh ứng dụng Java, sidecar hoặc client khác đang dùng cùng truststore. Hãy kiểm tra từ chính network path và runtime của consumer.

## 5. Gia hạn và xoay certificate an toàn

Quy trình thay certificate cần giữ dịch vụ hoạt động trong suốt quá trình phân phối:

1. **Xác định phạm vi:** endpoint, gateway, service mesh, workload, client mTLS và truststore nào sẽ bị ảnh hưởng.
2. **Phát hành certificate mới:** tạo private key tại nơi được bảo vệ; CSR có SAN/EKU đúng; chọn CA được trust.
3. **Kiểm tra trước deploy:** xác minh chain, hostname, thời hạn, key usage, key pair khớp và private key đọc được bởi đúng workload.
4. **Cập nhật trust trước khi cần:** nếu CA/intermediate thay đổi, phân phối trust anchor/intermediate đến client trước khi chuyển server certificate.
5. **Triển khai song song hoặc canary:** cập nhật một instance/gateway trước, giữ certificate cũ trong thời gian overlap nếu policy cho phép.
6. **Reload/restart có kiểm soát:** bảo đảm process thực sự nạp certificate mới; mount secret được cập nhật không đồng nghĩa JVM hoặc proxy tự reload.
7. **Kiểm tra từ client:** TLS handshake, hostname validation, mTLS identity, token endpoint, introspection và JWKS.
8. **Mở rộng rollout:** triển khai đến toàn bộ instance/region sau khi canary ổn định.
9. **Xác minh sau deploy:** kiểm tra fingerprint/serial đang phục vụ, lỗi TLS, tỷ lệ token request và API error.
10. **Thu hồi/loại bỏ certificate cũ:** chỉ sau khi chắc chắn không còn consumer phụ thuộc và theo quy trình CA/security.

Không xóa certificate cũ khỏi truststore quá sớm nếu còn server instance hoặc client chưa được cập nhật. Nếu cần chuyển CA, giai đoạn overlap có thể yêu cầu truststore tin cả CA cũ và CA mới trước khi certificate mới được sử dụng.

### 5.1 Ví dụ triển khai với Kubernetes Secret

Certificate và private key có thể được lưu trong Kubernetes Secret, sau đó mount vào ingress hoặc workload. Quy trình cần xác minh:

- Secret mới có certificate và private key tương ứng.
- SAN bao gồm hostname thực tế.
- Workload có quyền đọc Secret tối thiểu.
- Ingress/controller hoặc application reload certificate mới.
- Pod/instance cũ không còn phục vụ certificate hết hạn.
- Secret cũ được giữ trong thời gian rollback đã phê duyệt rồi mới dọn.

Nếu dùng cert-manager/ACME, theo dõi cả trạng thái Certificate, CertificateRequest, Order/Challenge và renewal failure. Tự động gia hạn chỉ có ích khi kết quả được phân phối và endpoint thực sự phục vụ bản mới. Alert vào renewal job và certificate đang được serve để phát hiện lệch trạng thái.

### 5.2 Client certificate và mTLS

Trong mTLS, cả server và client đều trình certificate. Gia hạn client certificate cần cập nhật client keystore/secret, đảm bảo client gửi certificate mới, và bảo đảm server truststore chấp nhận CA mới. Nếu server dùng allowlist theo subject hoặc SAN, phải cập nhật policy theo cách có kiểm soát.

Kiểm thử cả hai hướng:

- Client xác minh server certificate mới.
- Server xác minh client certificate mới.
- Certificate cũ bị từ chối sau thời điểm chuyển đổi/revoke theo policy.
- Client không có certificate hoặc certificate sai CA bị từ chối.

Không hạ chế độ mTLS thành TLS một chiều chỉ để khắc phục nhanh lỗi certificate. Nếu cần rollback, dùng certificate/CA còn hợp lệ theo trust policy.

## 6. Tác động đến OAuth 2.0/OIDC và token

Certificate hết hạn có thể tác động gián tiếp đến từng giai đoạn:

| Luồng | Triệu chứng có thể thấy | Cần kiểm tra |
| --- | --- | --- |
| Authorization endpoint | Người dùng không đăng nhập/consent được | TLS certificate của IdP, ingress, hostname và chain |
| Token endpoint | Không cấp được access/refresh token | TLS từ client đến AS, mTLS/client authentication nếu dùng |
| Introspection | Resource server không xác minh opaque token | TLS và client certificate giữa resource server và AS |
| JWKS | Không tải được signing public key mới | HTTPS certificate, cache JWKS, DNS/SNI |
| Token exchange | STS không nhận request hoặc không gọi được dependency | TLS ở client→STS, STS→introspection/key service |
| Resource API | Client không gọi được API hoặc mTLS bị từ chối | Server cert của API, client cert, truststore |

Khi TLS handshake thất bại, resource server không thể coi token là hợp lệ chỉ vì lần kiểm tra trước thành công. Với luồng cần introspection trực tuyến, chính sách an toàn là không cấp quyền khi không thể xác minh trạng thái token, trừ khi hệ thống có một cơ chế cache/fallback được đánh giá và phê duyệt rõ ràng.

### 6.1 Phân biệt certificate TLS và JWKS rotation

JWKS thường công bố public key để resource server xác minh chữ ký JWT. Việc xoay signing key cần có giai đoạn công bố key mới, phát hành token với kid mới, chờ cache refresh và giữ public key cũ đủ lâu để xác minh token chưa hết hạn. Đây là quy trình khác với gia hạn TLS server certificate.

Nếu JWKS endpoint dùng HTTPS, có thể đồng thời có hai hoạt động:

- Gia hạn certificate bảo vệ kết nối HTTPS đến JWKS endpoint.
- Xoay key ký JWT được công bố bên trong JWKS.

Kiểm thử và monitoring phải phân biệt lỗi TLS (không tải được JWKS) với lỗi JWT (kid không tìm thấy, chữ ký sai hoặc signing key không còn tin cậy). Không xoay JWT signing key chỉ để chữa lỗi TLS certificate expiry.

## 7. Giám sát và alert trong production

Nên theo dõi tối thiểu:

| Tín hiệu | Ý nghĩa | Hướng cảnh báo |
| --- | --- | --- |
| Certificate days-to-expiry | Số ngày còn lại của certificate đang phục vụ | Theo ngưỡng 30/14/7/3/1 ngày đã chọn |
| Certificate fingerprint/serial changed | Xác nhận endpoint đã chuyển sang bản mới | Thông báo rollout và phát hiện thay đổi ngoài kế hoạch |
| TLS handshake failures | Kết nối bị lỗi ở tầng TLS | Alert theo tỷ lệ và nhóm lỗi |
| Certificate verify errors | Hostname, chain, trust hoặc expiry không hợp lệ | High/Critical theo dịch vụ |
| mTLS client auth failures | Client certificate không được chấp nhận | Theo client/service alias |
| Renewal job status | Automation có phát hành certificate mới thành công không | Alert khi job fail hoặc không chạy đúng lịch |
| Served certificate vs inventory | Certificate thực tế có khớp bản mong đợi không | Alert khi fingerprint/serial lệch |
| OAuth token endpoint error rate | Khả năng cấp token bị ảnh hưởng | Correlate với TLS/IdP metrics |
| Introspection/JWKS dependency failures | Resource server không xác minh token được | Alert theo dependency và latency |

Không dùng raw hostname hoặc certificate serial làm label metric có cardinality không kiểm soát. Dùng service/endpoint alias hữu hạn; chi tiết fingerprint/serial có thể lưu trong event/log có kiểm soát. Tránh log private key, PEM body hoặc full TLS handshake payload.

Alert nên có owner, runbook link, endpoint alias, thời điểm quan sát, ngày hết hạn UTC và fingerprint đang phục vụ. Cảnh báo không chỉ nói certificate còn 3 ngày; nó phải chỉ rõ dịch vụ nào, ai chịu trách nhiệm và hành động kế tiếp.

## 8. Runbook xử lý certificate sắp hết hạn hoặc đã hết hạn

### 8.1 Khi còn thời gian gia hạn

1. Xác minh alert bằng cách đọc certificate đang được endpoint phục vụ từ network path thực tế.
2. Kiểm tra Not After, SAN, issuer, chain, EKU và fingerprint.
3. Xác định owner, CA, secret/keystore và các client phụ thuộc.
4. Kiểm tra trạng thái renewal automation; nếu thất bại, tìm nguyên nhân ACME challenge, quota CA, DNS hoặc quyền truy cập secret.
5. Phát hành certificate mới và xác minh chain/key pair.
6. Cập nhật truststore trước nếu CA thay đổi.
7. Deploy canary, reload và kiểm tra handshake từ client đại diện.
8. Kiểm tra authorization/token/introspection/JWKS flows.
9. Rollout toàn bộ, xác minh không còn instance phục vụ certificate cũ.
10. Cập nhật inventory, ngày hết hạn mới, fingerprint, owner và lịch cảnh báo tiếp theo.

### 8.2 Khi certificate đã hết hạn và dịch vụ lỗi

1. Xác định phạm vi ảnh hưởng: token endpoint, introspection, JWKS, mTLS hay resource API.
2. Kiểm tra lỗi TLS cụ thể: certificate expired, hostname mismatch, unknown CA, incomplete chain, client certificate rejected hay clock skew.
3. Kiểm tra certificate đang được serve và thời gian UTC của client/server.
4. Phát hành hoặc lấy certificate thay thế hợp lệ từ CA tin cậy theo quy trình khẩn cấp.
5. Cập nhật secret/keystore/ingress và reload đúng thành phần terminate TLS.
6. Kiểm tra TLS handshake, SAN, chain và mTLS từ client thực tế.
7. Kiểm tra token endpoint cấp token, resource server introspection opaque token, JWKS download và service-to-service call.
8. Theo dõi tỷ lệ 401/403/5xx, TLS errors, token issuance latency và introspection failure để xác nhận phục hồi.
9. Sau khi ổn định, rà soát renewal automation, ownership và cảnh báo để ngăn tái diễn.

Không tắt hostname verification, trust validation hoặc mTLS để làm cho request chạy lại. Không đưa certificate tự ký không được quản lý vào truststore production như một cách chữa cháy. Nếu phải dùng quy trình khẩn cấp, certificate mới vẫn phải được phát hành bởi CA được tổ chức tin cậy và có thời hạn/owner rõ ràng.

### 8.3 Bằng chứng cần lưu sau sự cố

- Thời điểm bắt đầu/kết thúc và các endpoint bị ảnh hưởng.
- Fingerprint/serial certificate cũ và mới; không lưu private key.
- Lỗi TLS chính xác, client/runtime gặp lỗi và network path.
- Các bước gia hạn, deploy, reload và rollback đã thực hiện.
- Kết quả kiểm tra token endpoint, introspection, JWKS, mTLS và resource API.
- Thời điểm phục hồi, metric trước/sau và hành động phòng ngừa.

## 9. Kiểm thử vận hành certificate expiry

Không đợi certificate production sắp hết hạn mới kiểm thử. Dùng CA/test certificate riêng trong môi trường test để mô phỏng các trường hợp:

| ID | Fixture/kịch bản | Kết quả kỳ vọng |
| --- | --- | --- |
| TLS-01 | Certificate hợp lệ, SAN khớp | Handshake thành công |
| TLS-02 | Certificate hết hạn | Client từ chối handshake |
| TLS-03 | Certificate chưa đến Not Before | Client từ chối theo validation |
| TLS-04 | SAN không khớp hostname | Hostname verification thất bại |
| TLS-05 | Thiếu intermediate certificate | Chain validation thất bại trừ khi client có intermediate từ nguồn tin cậy khác |
| TLS-06 | Issuer không nằm trong truststore | Certificate bị từ chối |
| TLS-07 | Client mTLS certificate hết hạn | Server từ chối client authentication |
| TLS-08 | Server certificate mới được deploy | Client trust và handshake thành công |
| TLS-09 | Rotation CA có overlap | Client chấp nhận chain cũ/mới trong cửa sổ chuyển đổi theo policy |
| TLS-10 | Clock client lệch | Xác định được lỗi validity time và cảnh báo clock sync |
| TLS-11 | Renewal thành công nhưng proxy chưa reload | Probe phát hiện endpoint vẫn phục vụ fingerprint cũ |
| TLS-12 | JWKS signing key xoay trong khi TLS cert không đổi | JWT verification hoạt động theo quy trình kid/cache riêng |

### 9.1 Test bằng OpenSSL

Kiểm tra endpoint và thời hạn:

~~~bash
openssl s_client -connect auth.example.test:443 +  -servername auth.example.test -verify_return_error </dev/null
~~~

Kiểm tra certificate file:

~~~bash
openssl x509 -in server-cert.pem -noout -dates -issuer -subject
~~~

Để tạo test certificate, dùng CA test nội bộ hoặc thư viện test PKI. Không đưa private key của CA production vào test. Certificate hết hạn nên được tạo trong fixture kiểm thử, không sửa đồng hồ production để ép sự cố.

### 9.2 Kiểm thử từ ứng dụng Java

Ứng dụng Java có thể dùng SSLContext/TrustManager và HTTP client để kiểm tra handshake bằng test CA. Khi test certificate expiry hoặc hostname mismatch, giữ nguyên xác minh mặc định của TLS client; test phải xác nhận kết nối thất bại vì lý do dự kiến. Không cấu hình trust-all TrustManager hoặc disable hostname verification để làm test pass.

Trong test tích hợp OAuth:

- Stub hoặc triển khai Authorization Server trên TLS test endpoint.
- Dùng truststore chứa CA test hợp lệ.
- Gọi token endpoint và introspection endpoint qua HTTPS.
- Đổi fixture server certificate sang expired/wrong-SAN/untrusted để xác nhận client fail.
- Khôi phục certificate hợp lệ và xác nhận token flow hoạt động lại.

## 10. Lỗi thường gặp khi vận hành

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Renewal job thành công nhưng endpoint báo expired | Ingress/proxy chưa reload hoặc một instance cũ còn chạy | Kiểm tra fingerprint từ từng endpoint/instance |
| Chỉ một số client lỗi TLS | Truststore khác nhau, runtime cũ, SNI hoặc hostname khác | Kiểm tra từ đúng client và network path |
| Token endpoint hoạt động nhưng introspection lỗi | Resource server có truststore/client cert riêng | Kiểm tra outbound TLS và mTLS của resource server |
| JWKS không tải được sau gia hạn | Certificate mới thiếu SAN/chain hoặc client cache/CA khác | Kiểm tra TLS endpoint và cache JWKS |
| TLS thành công nhưng JWT bị invalid signature | Signing key/JWKS rotation hoặc kid mismatch | Điều tra signing key riêng, không thay TLS cert |
| mTLS bị từ chối sau rotation | Server chưa trust CA mới hoặc client chưa gửi cert mới | Kiểm tra truststore, alias và client certificate |
| Certificate bị coi là chưa hiệu lực | Clock skew hoặc Not Before ở tương lai | Kiểm tra NTP và UTC trên node |
| Alert không phát hiện expiry | Chỉ kiểm tra secret store, không kiểm tra certificate đang serve | Bổ sung external probe và so sánh fingerprint |

## 11. Checklist vận hành

- [ ] Có inventory certificate cho Authorization Server, STS, introspection, JWKS, resource server, gateway và mTLS client.
- [ ] Mỗi certificate có owner, endpoint, CA, SAN, EKU, vị trí private key và runbook.
- [ ] Theo dõi Not After theo UTC và cảnh báo nhiều mốc trước expiry.
- [ ] Kiểm tra certificate đang serve từ network path thực tế, không chỉ kiểm tra file/secret.
- [ ] Renewal automation có alert khi job fail và khi endpoint không chuyển sang fingerprint mới.
- [ ] Chain, hostname, truststore và key usage được xác minh trước deploy.
- [ ] Có overlap/rollout/rollback phù hợp khi thay CA hoặc certificate phân phối rộng.
- [ ] mTLS được kiểm tra cả client và server certificate.
- [ ] Sau rotation đã kiểm tra token endpoint, introspection, JWKS và service-to-service flow.
- [ ] TLS certificate rotation và JWT signing-key rotation có quy trình riêng.
- [ ] Không tắt hostname verification, chain validation hoặc mTLS để xử lý sự cố.
- [ ] Log/trace/alert không chứa private key, PEM secret hoặc bearer token.
- [ ] Đã kiểm thử certificate expired, wrong SAN, untrusted CA, incomplete chain và clock skew trong môi trường test.

## Tài liệu tham khảo

- **RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3:** handshake và xác thực peer trong TLS 1.3.
- **RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile:** certificate path validation và CRL.
- **RFC 6125 — Service Identity in TLS:** xác minh danh tính dịch vụ/hostname trong TLS.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS cho OAuth client authentication và certificate-bound tokens.
- **RFC 7662 — OAuth 2.0 Token Introspection:** introspection token qua endpoint được bảo vệ.
- **OpenSSL Documentation — x509 và s_client:** kiểm tra certificate, chain và TLS endpoint.

Quản lý certificate tốt cần nhìn thấy cả thời hạn trong kho lưu trữ lẫn certificate thực sự đang được phục vụ, có người chịu trách nhiệm và có quy trình gia hạn được kiểm chứng. Khi TLS của token endpoint, introspection, JWKS và mTLS được duy trì đúng cách, hệ thống có thể tiếp tục xác thực và phân quyền token mà không phải hạ thấp các kiểm soát tin cậy.
