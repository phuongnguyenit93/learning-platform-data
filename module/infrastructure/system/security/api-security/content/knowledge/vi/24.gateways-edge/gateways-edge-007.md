# Failover không làm mất kiểm soát

Failover giúp API tiếp tục phục vụ khi gateway, load balancer, availability zone, region hoặc dịch vụ phụ thuộc gặp sự cố. Tuy nhiên, chuyển traffic sang một node hay một đường mạng khác có thể vô tình làm thay đổi các kiểm soát bảo mật đang được áp dụng. Một gateway dự phòng có thể thiếu policy mới, một region khác có thể chưa nhận trạng thái thu hồi token, một rate limiter local có thể cấp lại toàn bộ quota, hoặc traffic có thể đi thẳng vào origin và bỏ qua WAF.

Trong bảo mật API, failover chỉ thành công khi hệ thống duy trì được các security invariant trong chế độ bình thường và chế độ dự phòng. Availability không được tạo ra bằng cách bỏ qua authentication, authorization, tenant isolation, validation, rate limit hoặc audit. Nếu không thể duy trì một kiểm soát bắt buộc, hệ thống cần chuyển sang degraded mode có giới hạn hoặc từ chối thao tác theo chính sách đã định.

## 1. Hiểu failover trong kiến trúc API

Failover là quá trình chuyển xử lý sang thành phần dự phòng khi thành phần đang hoạt động không còn đáp ứng yêu cầu về sức khỏe, khả năng phục vụ hoặc kết nối. Việc chuyển có thể diễn ra tự động bởi load balancer, DNS, service mesh, gateway cluster hoặc do operator kích hoạt.

Các phạm vi failover thường gặp:

| Phạm vi | Ví dụ | Rủi ro bảo mật cần kiểm soát |
|---|---|---|
| Gateway instance | Chuyển từ gateway A sang gateway B | Policy, plugin và config giữa các node phải tương đương |
| Availability zone | Chuyển sang zone khác | Secret, certificate, session và rate limit phải sẵn sàng |
| Region | Chuyển từ region chính sang region dự phòng | Token revocation, tenant state, audit và dữ liệu nghiệp vụ có thể bị trễ |
| Upstream service | Chuyển sang provider hoặc replica khác | Endpoint thay thế phải có trust, identity và contract phù hợp |
| Control plane | Dùng config cache khi config service lỗi | Cache cũ có thể thiếu rule bảo mật mới |
| Data store | Chuyển sang replica database hoặc cache | Replica lag có thể làm sai quyền, trạng thái hoặc quota |

Failover khác với load balancing thông thường. Load balancing phân phối request giữa các node đủ điều kiện; failover phản ứng với sự cố hoặc suy giảm dịch vụ và có thể thay đổi đường đi, dữ liệu hoặc chính sách được sử dụng. Cả hai đều cần bảo đảm mọi node nhận traffic đã được cấu hình và kiểm tra theo cùng baseline bảo mật.

### 1.1. Phân biệt failover, fallback và degraded mode

- **Failover:** chuyển xử lý sang một thành phần dự phòng.
- **Fallback:** dùng hành vi hoặc nguồn thay thế khi chức năng chính không khả dụng, ví dụ trả dữ liệu cache có thời hạn.
- **Degraded mode:** tiếp tục cung cấp một tập chức năng bị giới hạn trong khi một số dependency hoặc kiểm soát không sẵn sàng.

Ba cơ chế này cần được thiết kế riêng. Chuyển sang gateway dự phòng không đồng nghĩa được phép bỏ qua xác thực. Dùng cache không đồng nghĩa dữ liệu cache còn đủ mới để quyết định quyền. Degraded mode không nên mở rộng quyền hoặc tạo side effect không thể đối soát.

## 2. Xác định security invariant phải giữ khi failover

Trước khi chọn cơ chế chuyển traffic, hãy xác định những điều kiện bảo mật không được thay đổi giữa các đường xử lý.

Các invariant quan trọng:

1. Mỗi request được xác thực bằng cùng trust model và kiểm tra credential tương đương.
2. Function authorization và object/tenant authorization vẫn được thực thi.
3. Validation, giới hạn kích thước và kiểm tra trạng thái nghiệp vụ không bị bỏ qua.
4. Rate limit, quota và concurrency limit không bị nhân lên ngoài mức dung sai đã thiết kế.
5. TLS, mTLS, certificate validation và outbound allowlist vẫn có hiệu lực.
6. Secret và signing key chỉ được truy cập bởi workload identity có quyền phù hợp.
7. Audit event được ghi với request ID, actor, tenant, action và kết quả có thể truy vết.
8. Retry hoặc chuyển vùng không tạo side effect trùng.
9. Traffic không thể đi vòng qua gateway/WAF để truy cập origin ngoài chính sách.
10. Nếu không thể xác minh một kiểm soát bắt buộc, hệ thống áp dụng fail-safe đã định nghĩa.

Một quy tắc hữu ích là lập bảng so sánh các invariant giữa primary và standby. Nếu một kiểm soát chỉ tồn tại ở primary, standby chưa đủ điều kiện nhận traffic production.

## 3. Các kiểu failover và trade-off

| Kiểu triển khai | Cách hoạt động | Ưu điểm | Điểm cần chú ý |
|---|---|---|---|
| Active-passive | Một cụm phục vụ chính, cụm còn lại chờ | Dễ xác định vai trò và phạm vi ghi | Standby có thể bị stale config hoặc chưa được kiểm thử dưới tải |
| Active-active | Nhiều cụm cùng nhận traffic | Tăng khả năng chịu lỗi và phân phối tải | Cần đồng bộ policy, key, quota, revocation và audit |
| Zone failover | Chuyển sang zone khác trong cùng region | Thường có độ trễ và khác biệt dữ liệu thấp hơn | Phụ thuộc vào replication và network giữa zone |
| Regional failover | Chuyển sang region địa lý khác | Chịu được sự cố diện rộng | Có thể có replica lag, khác biệt pháp lý và data residency |
| Upstream failover | Chuyển sang provider/endpoint thay thế | Giữ được một chức năng khi dependency lỗi | Provider thay thế phải được thẩm định và có contract tương thích |

Không có kiểu failover nào tự động an toàn. Active-active có thể làm quota bị tính riêng trên từng region; active-passive có thể chạy standby với policy cũ; regional failover có thể dùng dữ liệu membership chưa cập nhật. Các trade-off cần được ghi rõ trong thiết kế và runbook.

## 4. Kiến trúc failover có kiểm soát

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    C[API clients] --> E[DNS / global traffic manager]
    E --> W[WAF and edge policy]
    W --> G1[Primary gateway cluster]
    W --> G2[Standby gateway cluster]
    G1 --> S1[Application services]
    G2 --> S2[Application services]
    G1 --> P[Shared or replicated security policy]
    G2 --> P
    G1 --> A[Audit pipeline]
    G2 --> A
    S1 --> D[Data and business systems]
    S2 --> D
    H[Health and failover controller] --> E
    H --> G1
    H --> G2
~~~

Trong kiến trúc thực tế, policy có thể được phân phối qua control plane, config repository hoặc policy service; audit có thể được buffer khi đường truyền gián đoạn. Dù triển khai theo cách nào, cần có một nguồn policy được quản lý và một cơ chế xác minh node đã nạp đúng version trước khi nhận traffic.

### 4.1. Tách data plane và control plane

Data plane xử lý request thực tế: routing, TLS termination, authentication, rate limiting, filtering và forwarding. Control plane quản lý route, certificate, policy, feature và cấu hình của data plane.

Khi control plane lỗi, data plane có thể tiếp tục dùng cấu hình đã được xác minh gần nhất trong một khoảng thời gian. Tuy nhiên:

- Cấu hình cache cần có version, thời điểm nạp và thời hạn hợp lệ.
- Policy hết hạn hoặc bị thu hồi phải có hành vi rõ ràng.
- Thay đổi khẩn cấp như thu hồi key hoặc tắt endpoint nhạy cảm cần đường phân phối ưu tiên.
- Không cho phép data plane tự chuyển sang policy mặc định rộng quyền khi không liên lạc được control plane.
- Node mới không được nhận traffic nếu chưa nạp và xác minh policy bắt buộc.

Nếu không thể xác định cấu hình hiện tại có còn hợp lệ hay không, readiness cần phản ánh điều đó để traffic manager không gửi request đến node chưa đủ điều kiện.

## 5. Authentication phải nhất quán giữa các node

Failover không được làm thay đổi ý nghĩa của credential. Một token hợp lệ ở primary phải được đánh giá theo cùng issuer, audience, thuật toán, thời hạn và trust anchor ở standby.

### 5.1. JWT và signing key

Nếu gateway xác minh JWT offline bằng JWKS hoặc public key, mọi node cần có cấu hình issuer/audience và danh sách thuật toán được phép tương đương. Cần:

- Chỉ chấp nhận thuật toán đã cấu hình; không suy đoán thuật toán từ header token.
- Xác minh chữ ký, issuer, audience, expiration và not-before.
- Kiểm tra key ID và chỉ dùng key thuộc issuer đã tin cậy.
- Đồng bộ key rotation để cả primary và standby chấp nhận key mới trong thời gian chuyển tiếp được định nghĩa.
- Loại bỏ key cũ sau khi hết cửa sổ token hợp lệ và theo quy trình thu hồi.
- Không lấy JWKS URL tùy ý từ token.

Không chia sẻ private signing key cho mọi gateway nếu gateway chỉ cần xác minh chữ ký. Ưu tiên public key/JWKS cho verification và giữ private key trong KMS/HSM hoặc identity provider có quyền ký.

### 5.2. Token revocation và session state

JWT offline có thể tiếp tục hợp lệ đến khi hết hạn nếu hệ thống không có cơ chế kiểm tra thu hồi hoặc version session. Nếu primary nhận thông tin user bị khóa nhưng standby chưa nhận event, failover có thể cho phép token cũ tiếp tục hoạt động.

Các lựa chọn:

- Access token ngắn hạn và refresh token được quản lý tập trung.
- Token introspection cho action cần trạng thái mới nhất.
- Denylist hoặc session version được chia sẻ với mức nhất quán phù hợp.
- Event thu hồi được phát và xác nhận trên các region.
- Step-up hoặc xác minh lại cho thao tác có tác động cao khi trạng thái session không chắc chắn.

Không dùng cache revocation không giới hạn thời gian. Cần xác định độ trễ tối đa được chấp nhận và hành vi khi nguồn revocation không khả dụng. Với action nhạy cảm, nếu không thể xác minh trạng thái thu hồi theo yêu cầu, có thể phải từ chối hoặc chuyển manual review.

### 5.3. Session cookie và sticky session

Sticky session có thể giảm việc chuyển request giữa node, nhưng không nên là cơ chế bảo mật duy nhất. Nếu node chứa session bị hỏng, failover phải có thể xác minh session qua kho dùng chung hoặc yêu cầu đăng nhập lại theo chính sách.

Không sao chép session state bằng một cookie tự tạo không có chữ ký hoặc mã hóa phù hợp. Cookie cần giữ Secure, HttpOnly và SameSite theo loại client; session ID cần đủ entropy, rotation sau xác thực và thu hồi khi logout hoặc có sự cố.

## 6. Authorization và tenant isolation khi chuyển vùng

Gateway có thể kiểm tra scope tổng quát, nhưng object authorization thường cần được thực thi ở application/domain service. Failover gateway không được trở thành con đường bỏ qua lớp kiểm tra sâu hơn.

Các nguyên tắc:

- Policy theo principal, action, object và context phải nhất quán giữa primary/standby.
- Tenant context phải đến từ credential hoặc membership đã xác minh.
- Không tin X-Tenant-ID hoặc header nội bộ do client gửi trực tiếp.
- Service nhận request cần xác minh nguồn gateway bằng mTLS hoặc workload identity.
- Tenant/object filter phải được áp dụng tại service hoặc repository phù hợp.
- Policy cache cần tenant scope và version; không dùng cache của tenant này cho tenant khác.

### 6.1. Không tin header nội bộ nếu không xác minh nguồn

Gateway thường thêm các header như X-Authenticated-User, X-Tenant-ID hoặc X-Forwarded-For. Nếu origin có thể được truy cập trực tiếp từ Internet hoặc mạng không tin cậy, attacker có thể tự gửi các header đó để giả principal hoặc tenant.

Để bảo vệ:

1. Origin chỉ nhận traffic từ gateway hoặc service identity được phép.
2. Gateway xóa header định danh do client gửi rồi tự tạo header mới.
3. Kết nối gateway-to-origin dùng mTLS hoặc cơ chế workload identity phù hợp.
4. Application xác minh caller gateway và định dạng/nguồn của security context.
5. Với action nhạy cảm, application vẫn xác minh permission và object scope theo dữ liệu tin cậy.

Failover sang gateway khác phải giữ cùng hành vi xóa/ghi đè header. Không để standby thiếu một plugin hoặc rule làm client tự giả mạo context.

### 6.2. Replica lag của membership và ownership

Trong multi-region, membership, owner, assignment hoặc trạng thái khóa user có thể được replicate bất đồng bộ. Nếu failover sang region có dữ liệu cũ, user đã bị thu hồi quyền có thể vẫn được phép thao tác.

Xác định dữ liệu nào cần strong consistency:

- Thay đổi role và permission quản trị.
- Thu hồi tenant membership hoặc API key.
- Thay đổi owner, assignment hoặc quyền chia sẻ.
- Trạng thái khóa tài khoản hoặc hạn chế bảo mật.
- Approval và trạng thái giao dịch tài chính.

Nếu không thể bảo đảm dữ liệu đủ mới, hạn chế action dựa trên dữ liệu đó hoặc yêu cầu xác minh qua nguồn có tính nhất quán cao hơn. Không tự giả định replication đã hoàn tất chỉ vì node standby đang healthy.

## 7. Rate limit, quota và abuse control khi failover

Một lỗi thường gặp là rate limiter lưu counter trong bộ nhớ từng gateway. Khi primary có 100 request/phút và standby cũng có 100 request/phút, failover hoặc active-active có thể làm tổng giới hạn tăng gấp đôi. Attacker có thể cố tình tạo lỗi để nhận thêm ngân sách.

### 7.1. Chọn cách duy trì quota

| Cách triển khai | Hành vi khi failover | Lưu ý |
|---|---|---|
| Counter tập trung | Các gateway dùng chung bucket | Cần HA, atomic update và xử lý latency |
| Counter replicate | Bucket được đồng bộ giữa vùng | Có thể overshoot khi replication trễ |
| Budget phân bổ theo region | Mỗi region có một phần quota | Tổng budget bị giới hạn nếu cấp phát đúng |
| Local fallback budget | Node dùng ngân sách dự phòng giới hạn | Cần TTL, cap và metric; không reset vô hạn |
| Fail closed | Từ chối khi không kiểm tra được quota | Phù hợp với action có rủi ro hoặc chi phí cao |

Với hard quota, cần tính đến consistency và overshoot. Nếu dùng local fallback, cấp một ngân sách nhỏ có thời hạn, gắn với tenant/action và giới hạn tổng toàn hệ thống. Không cấp lại đầy đủ quota cho mỗi lần gateway restart.

### 7.2. Giữ nguyên các chiều rate limit

Rate limit có thể dựa trên:

- Tenant và plan.
- User hoặc API client.
- Endpoint/action và cost unit.
- IP hoặc network signal như một lớp bổ sung.
- Global capacity và upstream provider.

Failover không được làm mất các chiều này hoặc chuyển tất cả traffic sang một bucket chung. IP cần được lấy từ proxy tin cậy; không tin X-Forwarded-For do client tự gửi. Các key của rate limit không nên chứa email hoặc dữ liệu cá nhân trực tiếp.

### 7.3. Abuse control và challenge

Các tín hiệu như credential stuffing, enumeration, scraping, tốc độ request và challenge state cần được chia sẻ hoặc đánh giá lại theo policy. Nếu primary đã challenge một session, standby không nên bỏ qua chỉ vì không có local state. Challenge token phải được ràng buộc với principal, tenant, action, thời hạn và trạng thái dùng một lần; kho trạng thái phải chống replay giữa các node/region theo yêu cầu.

Nếu risk service không sẵn sàng, chọn fallback theo action. Đọc dữ liệu công khai có thể tiếp tục dưới rate limit dự phòng; refund, thay đổi credential hoặc cấp quyền có thể cần fail closed hoặc manual review.

## 8. WAF, routing và bảo vệ origin

Failover ở edge có thể tạo đường đi mới đến origin. Một cấu hình DNS hoặc load balancer sai có thể khiến traffic bỏ qua WAF, bot protection, request size limit hoặc TLS policy.

### 8.1. Origin không được mở đường vòng

- Firewall/security group chỉ cho phép nguồn gateway/load balancer được phê duyệt.
- Origin không có public ingress nếu kiến trúc yêu cầu chỉ gateway được truy cập.
- Dùng mTLS hoặc identity giữa edge và origin.
- Gateway dự phòng phải nằm trong allowlist của origin.
- Kiểm tra IPv4, IPv6, hostname phụ và port quản trị để tránh đường vòng.
- Không để DNS failover trỏ thẳng đến application node nếu node đó không có cùng lớp kiểm soát.

### 8.2. Đồng bộ WAF và API policy

Primary và standby cần cùng baseline cho:

- Request size, header size và body parsing.
- Allowed HTTP methods, path normalization và content types.
- IP/network policy và bot controls.
- Rate limit, burst và connection limits.
- API schema hoặc rule phát hiện payload bất thường.
- Denylist, allowlist và emergency block.

WAF không thay thế authorization ở application. Một request không bị WAF chặn vẫn cần authentication, function permission, object authorization và validation.

### 8.3. Path normalization và routing

Gateway và origin cần hiểu path nhất quán. Nếu primary normalize path khác standby, một route bị chặn ở primary có thể map sang endpoint nhạy cảm ở standby. Kiểm tra:

- Encoded slash, dot segment và repeated slash.
- Case sensitivity theo framework.
- Trailing slash và path parameter.
- Header override hoặc method override.
- Duplicate HTTP headers.
- HTTP/2 to HTTP/1 translation.

Không chỉ dựa vào rule theo chuỗi path thô nếu router phía sau diễn giải path khác. Cần contract test qua cả gateway và origin để bảo đảm route cuối cùng và policy tương ứng.

## 9. TLS, mTLS và certificate trong failover

Gateway dự phòng cần có certificate, private key access, trust store và cấu hình TLS tương đương. Không được dùng chứng thư hết hạn, hostname không khớp hoặc tắt xác minh peer để nhanh chóng khôi phục traffic.

Kiểm soát cần có:

- Certificate cho đúng hostname/SAN của endpoint dự phòng.
- Private key được quản lý trong KMS/HSM hoặc secret store phù hợp.
- Rotation và overlap window để tránh primary và standby dùng key khác nhau ngoài kế hoạch.
- Trust store và CA bundle được cập nhật đồng bộ.
- mTLS cho gateway-to-origin và service-to-service khi được yêu cầu.
- Không cho phép downgrade sang HTTP chỉ vì HTTPS endpoint gặp sự cố.
- Theo dõi expiry và lỗi handshake trên từng node/region.

Nếu failover chuyển sang hostname khác, client cần xác minh certificate của hostname mới. Không hướng dẫn client bỏ qua certificate warning hoặc dùng trust-all trong HTTP client.

## 10. Health check và điều kiện nhận traffic

Health check quyết định node nào được nhận request. Nếu chỉ kiểm tra TCP port hoặc process còn sống, traffic manager có thể gửi request đến node chưa nạp policy, thiếu key hoặc không kết nối được dependency bắt buộc.

Phân biệt:

- **Liveness:** process còn hoạt động và không bị deadlock.
- **Readiness:** node đã sẵn sàng phục vụ request theo các điều kiện bắt buộc.
- **Dependency health:** trạng thái của database, policy store, identity provider hoặc upstream.

Readiness cho gateway/API có thể kiểm tra:

- Route và policy version đã được nạp, xác minh.
- TLS certificate còn hiệu lực và key material sẵn sàng.
- Authentication/JWKS/introspection dependency ở trạng thái phù hợp.
- Rate limiter và quota store sẵn sàng hoặc fallback đã được kích hoạt đúng.
- Kết nối origin và service identity hoạt động.
- Audit pipeline hoặc buffer có khả năng ghi nhận event.

Không cần để mọi dependency phụ trợ làm node mất readiness nếu có fallback an toàn đã thiết kế. Nhưng dependency cần thiết cho security invariant phải được xem xét nghiêm túc. Health endpoint không được tiết lộ secret, token, topology nội bộ hoặc chi tiết nhạy cảm cho người gọi công khai.

### 10.1. Tránh health-check storm

Khi một dependency lỗi, mọi gateway có thể đồng thời probe liên tục hoặc cùng reconnect, làm dependency quá tải hơn. Dùng interval, timeout, jitter và circuit breaker phù hợp. Health check nên nhẹ và không tạo side effect nghiệp vụ.

### 10.2. Không failover chỉ dựa vào một lỗi thoáng qua

Một timeout đơn lẻ có thể do mạng tạm thời. Chuyển vùng liên tục có thể tạo flapping, làm mất cache, tăng retry và khiến request đi qua nhiều node khác nhau. Dùng ngưỡng, cửa sổ đánh giá, hysteresis và cooldown để quyết định failover. Với sự cố bảo mật, có thể cần một quy trình emergency override riêng có audit.

## 11. Retry, idempotency và state consistency

Client, gateway hoặc service mesh có thể retry request khi timeout hoặc connection reset. Một request đã được xử lý ở primary có thể chưa kịp trả response trước khi traffic chuyển sang standby. Nếu standby thực hiện lại side effect, hệ thống có thể tạo thanh toán, refund, đơn hàng hoặc email trùng.

### 11.1. Retry chỉ khi an toàn

- Không retry mù quáng các thao tác ghi.
- Dùng idempotency key ổn định cho cùng một operation.
- Gắn key với principal/tenant và loại action.
- Lưu kết quả idempotency ở nơi primary và standby cùng tra cứu được.
- Kiểm tra cùng key không được dùng với payload khác.
- Đặt retry budget, exponential backoff và jitter.
- Tôn trọng deadline và Retry-After.

Một request GET có thể retry nếu semantics và rate policy cho phép. Một request POST chuyển tiền chỉ được retry khi API/provider hỗ trợ idempotency hoặc hệ thống có cơ chế tra cứu operation để xác định kết quả trước khi gửi lại.

### 11.2. Xử lý kết quả không xác định

Nếu gateway mất kết nối sau khi application đã commit nhưng trước khi response đến client, client không biết operation thành công hay chưa. Không nên kết luận thất bại chỉ từ timeout.

Thiết kế operation resource:

1. Tạo operation ID duy nhất.
2. Ghi nhận request và idempotency key trước side effect.
3. Thực hiện thay đổi theo transaction/state machine.
4. Cho phép client truy vấn trạng thái operation theo quyền.
5. Dùng outbox/inbox hoặc deduplication cho event.
6. Đối soát với provider nếu kết quả bên ngoài chưa rõ.

### 11.3. Đồng bộ dữ liệu khi chuyển region

Failover region có thể đọc replica chưa nhận dữ liệu mới nhất. Cần phân loại dữ liệu:

- Dữ liệu có thể eventual consistency, ví dụ một số metric hoặc báo cáo.
- Dữ liệu cần consistency cao, ví dụ balance, payment state, role revocation hoặc idempotency record.
- Dữ liệu có thể tái tạo từ event log hoặc provider.

Không để replica lag làm lùi trạng thái payment hoặc cho phép một operation đã hoàn tất được chạy lại. Với dữ liệu quan trọng, dùng replication/consensus phù hợp hoặc chặn thao tác ghi cho đến khi hệ thống xác định được trạng thái an toàn.

## 12. Fail-open và fail-closed theo từng kiểm soát

Fail-open cho phép request tiếp tục khi một kiểm soát không khả dụng; fail-closed từ chối hoặc tạm dừng. Không nên chọn một chiến lược chung cho toàn hệ thống.

| Kiểm soát bị lỗi | Hành vi có thể phù hợp | Lý do |
|---|---|---|
| Authentication verifier | Từ chối hoặc yêu cầu xác thực lại | Không thể xác minh danh tính |
| Revocation check | Từ chối action nhạy cảm; có thể dùng token ngắn hạn theo policy cho tác vụ rủi ro thấp | Tránh tiếp tục chấp nhận credential đã thu hồi |
| Object authorization data | Từ chối thao tác trên object chưa xác minh | Tránh truy cập chéo user/tenant |
| Rate limit store | Dùng fallback budget nhỏ có hạn hoặc từ chối | Không để quota nhân lên theo node |
| WAF/policy engine | Dùng policy đã xác minh trong thời hạn hoặc rút node khỏi traffic | Không chuyển sang route mặc định rộng quyền |
| Audit pipeline | Buffer bền vững có giới hạn; với action cần audit bắt buộc có thể tạm dừng | Giữ bằng chứng và khả năng điều tra |
| Non-critical analytics | Có thể bỏ qua tạm thời | Không ảnh hưởng trực tiếp security invariant |
| Payment provider | Giữ trạng thái pending, không tự kết luận thành công | Tránh sai lệch tài chính |

Quyết định cần dựa trên tác động, yêu cầu pháp lý và khả năng khôi phục. Nếu buffer audit đầy hoặc không thể ghi event bắt buộc, cần có ngưỡng chuyển sang degraded mode hoặc từ chối action nhạy cảm.

## 13. Audit và observability xuyên suốt failover

Khi request chuyển node hoặc region, nhóm vận hành vẫn phải truy vết được toàn bộ hành trình. Dùng request ID/correlation ID ổn định và ghi thêm node, region, gateway version, policy version cùng failover event.

Audit event cho action bảo mật nên có:

- Actor hoặc service identity.
- Tenant và object reference theo chính sách dữ liệu.
- Action/endpoint template.
- Kết quả authentication và authorization ở dạng reason code.
- Node, region, route và policy version.
- Thời điểm, request ID, trace ID và operation ID.
- Kết quả side effect hoặc trạng thái pending.
- Lý do failover/degraded mode nếu có.

Không ghi access token, API key, session cookie hoặc payload nhạy cảm. Nếu audit pipeline tạm thời không liên lạc được, buffer phải được bảo vệ, có giới hạn dung lượng và cơ chế gửi lại chống trùng. Không coi log thường là bằng chứng thay thế audit bất biến nếu yêu cầu nghiệp vụ cần audit có kiểm soát chặt hơn.

### 13.1. Metric cần theo dõi

- Tỷ lệ traffic theo gateway, zone và region.
- Failover count, failover duration và flapping.
- Policy/config version mismatch giữa node.
- Authentication/authorization denial theo node.
- Rate limit decision và local fallback budget consumption.
- TLS handshake error và certificate expiry.
- Revocation propagation lag.
- Readiness failure và dependency health.
- Retry count, idempotency conflict và duplicate event.
- Audit buffer depth, delivery lag và dropped event.
- Upstream timeout, circuit breaker state và error rate.

Dashboard nên giúp so sánh primary và standby. Nếu sau failover tỷ lệ 401/403, 429 hoặc request thành công thay đổi bất thường, cần kiểm tra xem policy có bị mất hoặc quota có bị reset không.

## 14. Runbook failover an toàn

Runbook cần mô tả cả thao tác kỹ thuật lẫn các điều kiện bảo mật trước, trong và sau khi chuyển traffic.

### 14.1. Trước failover

1. Xác định phạm vi sự cố và node/region bị ảnh hưởng.
2. Kiểm tra standby có đúng image, patch, policy và config version.
3. Xác minh certificate, trust store và workload identity.
4. Kiểm tra authentication, revocation, tenant data và quota dependency.
5. Xác nhận WAF, route, origin allowlist và security group.
6. Kiểm tra audit pipeline/buffer và khả năng truy vết.
7. Xác định operation đang chạy hoặc đang pending.
8. Chọn failover mode và mức degraded mode cho từng nhóm action.

### 14.2. Trong khi failover

1. Chuyển traffic theo từng bước hoặc theo tỷ lệ nếu hệ thống hỗ trợ.
2. Không mở direct-origin access để né gateway.
3. Theo dõi readiness và policy version của node nhận traffic.
4. Kiểm tra authentication, authorization và rate limit bằng request kiểm thử được kiểm soát.
5. Giữ nguyên idempotency key và operation ID.
6. Theo dõi retry, duplicate và trạng thái giao dịch không xác định.
7. Kích hoạt fail-closed/manual review cho action không thể xác minh an toàn.
8. Ghi lại thời điểm, người thực hiện và quyết định trong audit.

### 14.3. Sau failover

1. Xác minh mọi node nhận traffic đã dùng đúng policy/config.
2. Đối chiếu quota, revocation, session và state cần consistency cao.
3. Đối soát operation tài chính và event bất đồng bộ.
4. Kiểm tra audit event không bị mất hoặc trùng.
5. Xác minh origin vẫn chỉ nhận traffic từ gateway hợp lệ.
6. Theo dõi metric và error rate trong thời gian ổn định.
7. Chỉ failback khi primary được vá, đồng bộ và kiểm thử.
8. Ghi nhận nguyên nhân và cập nhật test/runbook.

Failback cũng là một lần chuyển trạng thái có rủi ro. Không tự động chuyển về primary chỉ vì health check xanh nếu policy, data replication hoặc certificate chưa được xác minh.

## 15. Ví dụ: failover giữa hai gateway cluster

Giả sử API có primary cluster tại region A và standby tại region B. Cả hai nhận traffic qua global traffic manager. Gateway xác minh JWT, áp dụng WAF/rate limit và forward request đến application service.

| Kiểm soát | Region A | Điều kiện Region B trước khi nhận traffic |
|---|---|---|
| JWT issuer/audience | Policy version 12 | Cùng policy hoặc version tương thích đã được phê duyệt |
| JWKS/public keys | Key set K1/K2 | Có K1/K2 và quy tắc rotation giống nhau |
| Revocation | Event stream hiện tại | Lag trong ngưỡng; action nhạy cảm có nguồn xác minh bổ sung |
| Tenant policy | Policy version 45 | Đã nạp và xác minh version 45 |
| Rate limit | Distributed bucket | Dùng chung bucket hoặc budget region được cấp |
| WAF | Ruleset 31 | Cùng ruleset và emergency block |
| TLS/mTLS | Certificate set C7 | Certificate hợp lệ, trust chain và SAN đúng |
| Audit | Pipeline A | Pipeline B hoặc durable buffer đã kiểm thử |
| Idempotency | Store dùng chung | Có thể tra cứu cùng operation/key |

Nếu region B chưa có revocation state mới nhất hoặc không truy cập được idempotency store, có thể cho phép một số thao tác đọc ít rủi ro theo policy nhưng phải chặn refund, thay đổi role hoặc chuyển tiền. Khi các dependency bắt buộc phục hồi, mở dần nhóm action theo runbook.

## 16. Kiểm thử failover và chaos engineering

Failover cần được kiểm thử định kỳ trong môi trường có kiểm soát. Một sơ đồ kiến trúc hoặc health check xanh không chứng minh standby có cùng security posture.

| Nhóm test | Cách thử | Kết quả mong đợi |
|---|---|---|
| Gateway loss | Dừng primary gateway | Traffic chuyển sang standby có policy tương đương |
| Policy drift | Làm standby chạy config cũ | Readiness từ chối hoặc cảnh báo; không nhận traffic ngoài policy |
| Token revocation | Thu hồi user rồi failover ngay | Token bị từ chối theo consistency requirement |
| Key rotation | Thay JWKS/signing key trong lúc chuyển node | Key hợp lệ được chấp nhận; key hết hiệu lực bị loại đúng thời điểm |
| Tenant isolation | Gửi tenant header giả qua standby | Không thể giả tenant hoặc truy cập chéo |
| Rate limit | Tạo tải ở primary rồi chuyển standby | Quota không bị reset hoặc nhân lên ngoài dung sai |
| WAF bypass | Thử truy cập origin trực tiếp | Origin từ chối nguồn không được phép |
| TLS/mTLS | Dùng cert hết hạn hoặc sai SAN | Handshake bị từ chối |
| Retry/replay | Timeout sau commit rồi retry qua standby | Không tạo side effect trùng |
| Replica lag | Làm chậm replication của permission/state | Action yêu cầu consistency cao bị hạn chế |
| Audit outage | Ngắt audit pipeline | Buffer/fail-safe hoạt động theo policy, không âm thầm mất event |
| Upstream failover | Chuyển sang provider dự phòng | Endpoint, credential, schema và response validation vẫn đúng |
| Health check | Làm một dependency security bắt buộc lỗi | Node không được đánh dấu ready sai |
| Failback | Khôi phục primary với config/data cũ | Không chuyển về trước khi đồng bộ và xác minh |

### 16.1. Kiểm thử negative path

Ngoài việc xác minh request hợp lệ thành công, cần xác minh request không hợp lệ vẫn bị chặn trên mọi đường:

- Anonymous gọi endpoint cần authentication.
- User không có function permission gọi action nhạy cảm.
- User cùng tenant nhưng không có quyền trên object.
- Token đã thu hồi hoặc sai audience.
- Request vượt quota hoặc gửi batch quá lớn.
- Origin nhận header identity do client tự giả.
- Request có path encoding khác biệt giữa gateway và application.

Chạy cùng test suite trên primary và standby, qua cả gateway, load balancer và đường mạng dự phòng. Không chỉ test trực tiếp vào application service nếu production traffic đi qua nhiều lớp.

## 17. Những sai lầm thường gặp

- **Standby chỉ kiểm tra process sống:** node chưa nạp policy vẫn nhận traffic.
- **Failover làm mất authorization:** gateway dự phòng chỉ xác thực token mà không áp dụng permission tương đương.
- **Tin header từ client:** origin chấp nhận tenant/user header không được xác minh.
- **Origin mở công khai:** attacker bỏ qua WAF và gateway bằng cách gọi trực tiếp.
- **Rate limit local bị reset:** mỗi node cấp lại quota đầy đủ khi failover.
- **Revocation bị trễ:** token đã thu hồi vẫn được chấp nhận ở region khác.
- **Config cache vô thời hạn:** policy cũ tiếp tục hoạt động khi control plane lỗi.
- **Tắt TLS verification:** dùng kết nối không an toàn để khôi phục dịch vụ.
- **Retry mọi request:** tạo thanh toán, refund hoặc message trùng.
- **Health check quá nông:** chỉ kiểm tra port mà không xác minh security dependency.
- **Fail-open toàn hệ thống:** dependency lỗi khiến mọi thao tác được phép.
- **Fail-closed không phân loại:** cả thao tác ít rủi ro cũng bị dừng không cần thiết.
- **Audit bị mất khi chuyển vùng:** không thể điều tra ai đã thực hiện action.
- **Failback quá sớm:** primary trở lại với dữ liệu hoặc config cũ.
- **Không kiểm thử định kỳ:** standby chỉ được phát hiện sai lệch khi có incident thật.

## 18. Checklist trước khi phát hành

- [ ] Có sơ đồ failover cho gateway, edge, zone, region và upstream dependency.
- [ ] Security invariant được xác định cho primary, standby và degraded mode.
- [ ] Standby dùng image, patch, route, WAF và policy version đã được phê duyệt.
- [ ] Authentication, issuer/audience, JWKS và key rotation nhất quán.
- [ ] Token revocation/session state có consistency requirement và giới hạn propagation lag.
- [ ] Function, object và tenant authorization vẫn được thực thi ở application.
- [ ] Header identity/tenant do client gửi bị xóa hoặc ghi đè; origin xác minh gateway.
- [ ] Origin chỉ nhận traffic từ gateway/load balancer được phép.
- [ ] Rate limit, quota và concurrency không bị reset hoặc nhân theo số node/region.
- [ ] TLS/mTLS, certificate, trust store và hostname verification được giữ nguyên.
- [ ] Health check phân biệt liveness/readiness và kiểm tra security dependency bắt buộc.
- [ ] Fail-open/fail-closed được chọn riêng cho authentication, authorization, quota, audit và nghiệp vụ.
- [ ] Retry có budget, backoff, deadline và idempotency cho side effect.
- [ ] Replica lag không làm lùi trạng thái permission, payment hoặc idempotency.
- [ ] Audit/trace giữ request ID, actor, tenant, region và policy version.
- [ ] Có runbook trước, trong, sau failover và quy trình failback.
- [ ] Đã test gateway loss, policy drift, revocation, quota, WAF bypass, TLS, replay và audit outage.
- [ ] Có cảnh báo khi primary/standby khác policy hoặc hành vi bảo mật.

Failover không làm mất kiểm soát khi mọi node và mọi đường dự phòng đều thực thi cùng các security invariant, hoặc chủ động giới hạn chức năng khi không thể xác minh chúng. Thiết kế tốt phải tính đến policy/config drift, token revocation, quota phân tán, tenant state, retry, audit và đường truy cập origin; đồng thời kiểm thử cả failover lẫn failback trước khi có sự cố thực tế.
