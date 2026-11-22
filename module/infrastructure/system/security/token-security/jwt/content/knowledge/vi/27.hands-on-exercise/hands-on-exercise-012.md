# Đánh giá lựa chọn JWT trước yêu cầu thay đổi quyền tức thời

## 1. Mục tiêu thực hành

Trong bài này, bạn sẽ đánh giá một hệ thống đang dùng JSON Web Token (JWT) access token tự chứa, sau đó nhận yêu cầu nghiệp vụ mới: khi quản trị viên thu hồi quyền của một người dùng, mọi request tiếp theo phải mất quyền gần như tức thời.

Bạn sẽ so sánh các cách triển khai, định lượng độ trễ thu hồi, chọn mô hình phù hợp với mức rủi ro và thiết kế kiểm thử để chứng minh hệ thống thực sự đáp ứng yêu cầu. Trọng tâm là quyết định kiến trúc và hợp đồng vận hành, không phụ thuộc ngôn ngữ lập trình hoặc framework.

Sau bài thực hành, bạn cần có thể:

1. Phân biệt xác thực token với quyết định authorization hiện tại.
2. Giải thích vì sao JWT tự chứa được xác minh ngoại tuyến không tự nhận biết quyền vừa thay đổi.
3. Chuyển yêu cầu “tức thời” thành một Service Level Objective (SLO) có mốc thời gian và phạm vi rõ ràng.
4. So sánh token lifetime ngắn, denylist theo jti, authorization version, introspection và cache invalidation.
5. Thiết kế mô hình lai giữa xác minh chữ ký JWT và kiểm tra trạng thái trực tuyến.
6. Xử lý cache, replication, network partition, retry và request đang chạy dở.
7. Viết pseudocode, ma trận quyết định, test plan và runbook cho thay đổi quyền.

## 2. Tình huống nghiệp vụ

Một hệ thống thương mại điện tử có Identity Service phát hành JWT access token và Orders API xác minh token cục bộ bằng public key đã cache.

Token chứa các thông tin như subject, audience, expiration và scope. Người dùng có quyền đọc đơn hàng và tạo đơn hàng. Quản trị viên có thể khóa tài khoản hoặc thu hồi quyền tạo đơn hàng.

Yêu cầu ban đầu:

- Access token có thời hạn 15 phút.
- Orders API xác minh chữ ký và claims cục bộ.
- Không gọi Identity Service cho mỗi request.
- Quyền trong token được dùng để quyết định scope của endpoint.

Yêu cầu mới:

> Khi quản trị viên thu hồi quyền tạo đơn hàng của một người dùng, request tạo đơn hàng mới phải bị từ chối trong vòng 2 giây kể từ khi thay đổi quyền được commit thành công.

Yêu cầu này tạo ra một thay đổi kiến trúc. Token đã phát hành là một snapshot của trạng thái tại thời điểm phát hành. Nếu Orders API chỉ kiểm tra chữ ký, issuer, audience và expiration, API không biết scope trong token đã bị thu hồi sau đó.

## 3. Phân biệt xác thực và authorization hiện tại

Hai câu hỏi cần được trả lời riêng:

**Authentication / token validation:** Token có được phát hành bởi issuer tin cậy, dành cho API này, còn hiệu lực và đúng profile không?

**Authorization:** Tại thời điểm thực hiện request, chủ thể có còn được phép thực hiện hành động trên tài nguyên cụ thể không?

Chữ ký JWT giúp xác minh tính toàn vẹn và nguồn ký theo khóa đã tin cậy. Nó không tự đồng bộ trạng thái quyền mới từ Identity Service đến resource server.

Ví dụ token được phát hành lúc 10:00:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-482",
  "aud": "https://api.orders.example.com",
  "iat": 1893456000,
  "exp": 1893456900,
  "jti": "token-7f31",
  "scope": "orders:read orders:write"
}
~~~

Lúc 10:03, quản trị viên thu hồi orders:write. Chữ ký token vẫn hợp lệ, exp vẫn ở tương lai và payload vẫn chứa scope cũ. Nếu API chỉ kiểm tra token, nó vẫn có thể cho phép tạo đơn hàng.

Điều này không phải lỗi của thuật toán JWT. Đây là hệ quả của mô hình token tự chứa và xác minh không cần hỏi trạng thái bên ngoài.

### 3.1. JWT không bắt buộc hệ thống phải stateless

JWT là định dạng biểu diễn claims. Hệ thống có thể:

- Xác minh JWT hoàn toàn cục bộ.
- Xác minh chữ ký cục bộ rồi kiểm tra authorization state trực tuyến.
- Gọi introspection để hỏi token còn active hay không.
- Kết hợp JWT với session version, authorization version hoặc denylist.

Do đó, câu hỏi kiến trúc không đơn giản là “JWT hay session”. Câu hỏi chính là resource server lấy trạng thái quyền hiện tại từ đâu, mức nhất quán nào được bảo đảm và khi không lấy được trạng thái thì xử lý ra sao.

## 4. Định nghĩa “tức thời” thành SLO có thể đo

Không có hệ thống phân tán nào nên dùng từ “tức thời” mà không định nghĩa điểm bắt đầu, điểm kết thúc và sai số chấp nhận được.

Trong bài tập, dùng SLO minh họa:

~~~text
Permission revocation SLO:
  Start:
    authoritative permission change is committed successfully

  End:
    every new protected request evaluated after the SLO deadline
    is denied when it depends on the revoked permission

  Maximum propagation time:
    2 seconds

  Measurement:
    p99 <= 2 seconds
    no request admitted using stale permission after the deadline
~~~

Đây là ngưỡng minh họa. Hệ thống thực tế phải chọn SLO theo mức độ nhạy cảm, tải, topology và khả năng vận hành.

Hai dòng đo lường trên có ý nghĩa khác nhau: p99 là mục tiêu thống kê về độ trễ propagation; điều kiện không chấp nhận stale permission sau deadline là invariant bảo mật cứng. Nếu tổ chức chỉ cam kết p99, phải công bố rằng một tỷ lệ nhỏ request có thể vượt 2 giây và không được diễn đạt cam kết đó như bảo đảm tuyệt đối.

### 4.1. Cần định nghĩa những mốc nào?

| Mốc | Ý nghĩa |
| --- | --- |
| T0 | Thay đổi quyền được commit tại nguồn dữ liệu có thẩm quyền |
| T1 | Sự kiện thay đổi được phát đi |
| T2 | Các node resource server nhận và áp dụng invalidation |
| T3 | Cache hoặc authorization snapshot cũ không còn được dùng |
| T4 | Request mới được đánh giá theo trạng thái mới |

Độ trễ thu hồi thực tế là T4 - T0. Chỉ đo thời gian publish event hoặc thời gian API quản trị trả response là chưa đủ.

### 4.2. Xác định phạm vi request

Contract cần làm rõ:

- Request bắt đầu sau T0 có được phép dùng quyền cũ trong thời gian propagation không?
- Request đến sau T0 nhưng trước deadline có được phép hay phải bị từ chối ngay khi nguồn dữ liệu commit?
- Request đã được authorize trước T0 nhưng commit side effect sau T0 có được hoàn tất không?
- SLO áp dụng cho mọi endpoint hay chỉ hành động nhạy cảm?
- SLO áp dụng trên mọi region, replica và worker hay chỉ một cụm?

Nếu yêu cầu là không có request nào được chấp nhận sau T0, đó là yêu cầu mạnh hơn SLO 2 giây. Khi đó cần một điểm đồng bộ authorization có tính nhất quán phù hợp, và có thể phải chấp nhận thêm latency hoặc giảm availability.

## 5. Baseline: JWT tự chứa với expiration

Phương án hiện tại chỉ verify chữ ký và claims cục bộ. Quyền trong token được giữ đến khi token hết hạn.

### 5.1. Cách hoạt động

1. Issuer xác thực người dùng và phát hành access token.
2. Token chứa scope được cấp tại thời điểm phát hành.
3. Orders API lấy public key từ JWKS cache.
4. API verify chữ ký, issuer, audience, token type và thời gian.
5. API đọc scope đã xác minh và thực hiện authorization.
6. Không có truy vấn trạng thái quyền hiện tại.

### 5.2. Độ trễ thu hồi

Nếu access token còn 15 phút, quyền bị thu hồi có thể vẫn được sử dụng trong gần 15 phút còn lại. Clock skew và cách áp dụng expiration có thể làm cửa sổ thực tế dài hơn một chút.

Đặt TTL token ngắn hơn giúp giảm cửa sổ rủi ro, nhưng không tạo ra thu hồi tức thời.

| Token lifetime | Cửa sổ quyền cũ có thể tồn tại tối đa gần đúng |
| --- | --- |
| 15 phút | Gần 15 phút |
| 5 phút | Gần 5 phút |
| 1 phút | Gần 1 phút |
| 30 giây | Gần 30 giây |

Đây là ước lượng trong điều kiện token vừa được phát hành trước khi quyền thay đổi. Cần tính thêm clock skew và quy tắc chấp nhận thời gian của verifier.

### 5.3. Ưu và nhược điểm

**Ưu điểm**

- Không cần trạng thái tập trung cho mỗi request.
- Độ trễ xác minh ổn định và thấp.
- Resource server có thể hoạt động khi issuer tạm thời không truy cập được, miễn key cache còn hợp lệ.
- Dễ mở rộng ngang khi chỉ có verify cục bộ.

**Hạn chế**

- Không đáp ứng SLO 2 giây nếu token lifetime dài hơn đáng kể.
- Token đã phát hành giữ quyền cũ đến khi hết hạn.
- Rút ngắn TTL làm tăng tần suất refresh và tải lên issuer.
- Không giải quyết ngay việc khóa tài khoản hoặc thu hồi session nếu API không kiểm tra trạng thái.

**Kết luận:** Chỉ dùng expiration là không đáp ứng yêu cầu mới. Nó phù hợp khi nghiệp vụ chấp nhận một cửa sổ thu hồi bằng thời hạn token còn lại.

## 6. Phương án A: Denylist theo jti

Issuer cấp mỗi token một jti duy nhất. Khi cần thu hồi một token, hệ thống ghi nhận jti đó vào kho trạng thái; resource server kiểm tra denylist trước khi cho phép request.

### 6.1. Cách hoạt động

1. Verify chữ ký và toàn bộ claims của JWT.
2. Lấy jti từ claims đã xác minh.
3. Tra cứu trạng thái thu hồi theo namespace issuer + jti.
4. Nếu tồn tại marker thu hồi, từ chối token.
5. Nếu không tồn tại, tiếp tục authorization.

Không tra cứu denylist dựa trên jti chưa xác minh. Attacker có thể tự tạo token với jti tùy ý để gây tải hoặc tác động nhầm vào namespace.

### 6.2. Vòng đời marker

Marker phải tồn tại đến khi token không còn được bất kỳ verifier nào chấp nhận. Thời hạn lưu cần tính đến:

- exp của token.
- Clock skew được phép.
- Khác biệt đồng hồ giữa các node.
- Cache hoặc replication delay.
- Quy tắc expiration của verifier.

Có thể lưu hash/fingerprint của định danh token thay vì raw JWT. Không cần lưu toàn bộ bearer token trong denylist.

### 6.3. Ưu và nhược điểm

| Tiêu chí | Đánh giá |
| --- | --- |
| Thu hồi một token | Phù hợp |
| Thu hồi tất cả token của một user | Cần liệt kê token hoặc bổ sung trạng thái theo subject/session |
| Latency | Có thêm state lookup |
| Availability | Phụ thuộc denylist store |
| Khả năng mở rộng | Cần partitioning, TTL và kiểm soát tăng trưởng |
| Độ nhất quán | Phải bảo đảm marker đã ghi được mọi verifier nhìn thấy trong SLO |

Denylist theo jti phù hợp với thu hồi token cụ thể, nhưng không phải lựa chọn hiệu quả nhất nếu mỗi thay đổi quyền phải vô hiệu hóa hàng nghìn token của cùng một subject.

### 6.4. Điểm cần kiểm thử

- Marker được ghi thành công trước khi API quản trị báo thay đổi hoàn tất.
- Mọi resource server đều nhìn thấy marker trong SLO.
- Marker không hết TTL trước cửa sổ chấp nhận token.
- Hai request đồng thời không vượt qua kiểm tra khi marker vừa được commit.
- Store outage không biến trạng thái unknown thành “chưa bị thu hồi”.

## 7. Phương án B: Authorization version hoặc session version

Thay vì thu hồi từng token, issuer đưa một phiên bản trạng thái vào token. Khi quyền của subject hoặc session thay đổi, hệ thống tăng version tại nguồn có thẩm quyền. Resource server so sánh version trong token với version hiện tại.

### 7.1. Ví dụ

Token được phát hành với:

~~~json
{
  "sub": "user-482",
  "authz_ver": 12,
  "scope": "orders:read orders:write",
  "exp": 1893456900
}
~~~

Khi quản trị viên thu hồi orders:write, hệ thống cập nhật trạng thái authorization của subject:

~~~text
user-482:
  authz_ver: 13
  scopes:
    - orders:read
~~~

Request tiếp theo mang token có authz_ver = 12. Resource server đọc version hiện tại là 13 và từ chối token cũ hoặc yêu cầu cấp lại token theo policy.

authz_ver là claim tùy biến do contract định nghĩa, không phải registered claim của JWT. Trong môi trường có nhiều issuer/consumer, nên dùng tên claim có namespace tránh xung đột hoặc một định danh URI collision-resistant; phải chốt kiểu dữ liệu, phạm vi version và semantics khi version thay đổi.

### 7.2. Chọn phạm vi version

Có thể dùng các phạm vi khác nhau:

| Version scope | Tác dụng |
| --- | --- |
| Subject authorization version | Vô hiệu hóa token cũ của subject khi quyền user thay đổi |
| Session version | Thu hồi token của một phiên hoặc thiết bị |
| Client version | Vô hiệu hóa token của một client cụ thể |
| Tenant/policy version | Làm mới token hoặc policy khi cấu hình tenant thay đổi |

Không dùng một version toàn hệ thống nếu thay đổi nhỏ của một user sẽ làm vô hiệu hóa token của tất cả người dùng.

### 7.3. Version mismatch có nghĩa gì?

Có hai cách xử lý:

**Từ chối token cũ:** Version không khớp thì trả lỗi xác thực hoặc trạng thái cần cấp token mới. Cách này đơn giản và an toàn, nhưng người dùng có thể phải lấy access token mới.

**Đánh giá quyền hiện tại:** Version không khớp thì tải entitlement hiện tại và tạo authorization context mới theo policy. Cách này có thể giữ session nhưng cần định nghĩa rõ liệu token cũ còn được dùng làm danh tính hay phải cấp token mới.

Không âm thầm thay claims trong token. JWT đã ký là bất biến; trạng thái hiện tại phải được lấy từ nguồn có thẩm quyền.

### 7.4. Ưu và nhược điểm

**Ưu điểm**

- Thu hồi tất cả token cũ của một subject/session bằng một thay đổi version.
- Không cần lưu từng jti đã phát hành.
- Có thể kết hợp với JWT tự chứa để giảm dữ liệu cần truy vấn.

**Hạn chế**

- Resource server phải đọc version hiện tại hoặc dùng cache có giới hạn.
- Version cache stale sẽ làm chậm hiệu lực thu hồi.
- Cần namespace và semantics rõ giữa subject, session, client và tenant.
- Nếu version và entitlement không được cập nhật nguyên tử, có thể xuất hiện trạng thái không nhất quán.

Đây là phương án phù hợp khi hệ thống muốn giữ JWT nhưng cần khả năng vô hiệu hóa hàng loạt token theo subject/session.

## 8. Phương án C: Introspection trực tuyến

Với OAuth 2.0 Token Introspection theo RFC 7662, resource server gửi token đến authorization server hoặc introspection endpoint được tin cậy để hỏi token có đang active hay không.

### 8.1. Cách hoạt động

1. Client gửi access token đến Orders API.
2. Orders API gọi introspection endpoint qua kênh được bảo vệ.
3. Authorization server xác định token, trạng thái và các metadata được phép trả về.
4. Orders API kiểm tra active cùng các thuộc tính cần thiết như audience, scope và client.
5. API thực hiện authorization cho resource.

Với JWT, resource server vẫn có thể xác minh chữ ký cục bộ trước hoặc theo contract kết hợp. Introspection không tự thay thế mọi kiểm tra profile. Hợp đồng phải xác định nguồn nào có thẩm quyền cho trạng thái token và claims.

### 8.2. Định nghĩa active

Không nên giả định active chỉ có nghĩa “chữ ký hợp lệ và chưa hết hạn”. Authorization server cần định nghĩa rõ active có phản ánh:

- Token đã bị revoke hay chưa.
- Session hoặc grant có còn hiệu lực không.
- Subject có bị disable không.
- Client có còn được phép không.
- Audience/resource có phù hợp không.
- Quyền đã bị thu hồi có được phản ánh vào scope/entitlement trả về không.

Nếu introspection chỉ kiểm tra token tồn tại và chưa hết hạn, nó không tự giải quyết thay đổi quyền nghiệp vụ.

### 8.3. Cache introspection

Cache active response giúp giảm latency và tải lên authorization server, nhưng tạo cửa sổ stale. Nếu cache TTL là 30 giây, một token vừa bị revoke có thể tiếp tục được coi là active gần 30 giây, cộng thêm propagation và replication delay.

Với SLO 2 giây, cache active 30 giây không phù hợp. Cần TTL nhỏ hơn ngân sách SLO hoặc invalidation có bảo đảm. Nếu cache không thể bị invalidated đáng tin cậy, TTL là giới hạn trên của thời gian stale.

### 8.4. Ưu và nhược điểm

| Tiêu chí | Đánh giá |
| --- | --- |
| Thu hồi token tập trung | Tốt nếu authorization server cập nhật trạng thái đúng |
| Kiểm tra mỗi request | Có thể tăng latency và tải |
| Availability | Phụ thuộc introspection endpoint |
| Cache | Giảm tải nhưng làm chậm revocation |
| Nhiều resource server | Có thể dùng chung một trạng thái trung tâm |
| Phân vùng mạng | Cần quyết định fail-closed hoặc policy dự phòng |

Introspection là lựa chọn phù hợp khi cần trạng thái token tập trung và có thể chấp nhận dependency trực tuyến.

## 9. Phương án D: Push invalidation và phân phối sự kiện

Khi quyền thay đổi, nguồn dữ liệu có thẩm quyền phát một sự kiện để các resource server xóa cache hoặc cập nhật version.

Ví dụ sự kiện:

~~~json
{
  "event_id": "evt-90182",
  "event_type": "subject.authorization.changed",
  "subject": "user-482",
  "new_authz_version": 13,
  "committed_at": "2026-11-16T10:03:00Z"
}
~~~

### 9.1. Luồng xử lý

1. Thay đổi quyền và tăng version được commit trong cùng transaction tại nguồn dữ liệu.
2. Transactional outbox ghi sự kiện cần phát.
3. Event publisher gửi sự kiện đến các consumer.
4. Mỗi resource server cập nhật version hoặc invalidates cache tương ứng.
5. Consumer xác nhận event đã áp dụng.
6. Hệ thống theo dõi propagation lag và consumer không hoạt động.

### 9.2. Tại sao chỉ dùng pub/sub là chưa đủ?

Thông điệp có thể:

- Bị trễ.
- Bị gửi lặp.
- Đến sai thứ tự.
- Bị mất khi consumer ngắt kết nối.
- Chưa đến một region đang bị partition.
- Được ACK trước khi cache thực sự bị invalidated nếu consumer xử lý sai.

Do đó, event delivery không tự bảo đảm mọi node đã cập nhật trong 2 giây.

### 9.3. Điều kiện để push invalidation đáng tin

- Event có ID duy nhất và xử lý idempotent.
- Event có version tăng đơn điệu hoặc sequence để phát hiện thứ tự cũ.
- Consumer ACK sau khi trạng thái đã được áp dụng.
- Có retry, dead-letter handling và cảnh báo consumer lag.
- Consumer reconnect phải resync từ nguồn có thẩm quyền.
- Có cơ chế phát hiện event gap.
- Khi vượt propagation deadline, resource server không được tiếp tục dùng cache cũ cho hành động bị bảo vệ.

Push invalidation thường nên kết hợp với một fallback có giới hạn, ví dụ cache TTL ngắn hoặc version lookup. Nếu chỉ dựa vào event, một node bị mất kết nối có thể giữ quyền cũ vô thời hạn.

## 10. Phương án E: Kiểm tra entitlement hiện tại tại thời điểm request

Thay vì xem scope trong token là quyền cuối cùng, API dùng token để xác định subject/client, sau đó hỏi authorization service hoặc policy store về quyền hiện tại cho hành động và resource cụ thể.

Ví dụ:

~~~text
function authorizeCurrentRequest(principal, action, resource):
    currentEntitlements = authorizationStore.getCurrent(
        subject = principal.subject,
        resource = resource
    )

    require currentEntitlements.allows(action)
    allow
~~~

Token vẫn xác minh danh tính và ràng buộc issuer/audience. Quyền thực tế được quyết định từ trạng thái hiện tại.

### 10.1. Khi nào nên dùng?

- Quyền thay đổi thường xuyên.
- Quyền phụ thuộc trạng thái tài nguyên.
- Cần áp dụng chính sách mới mà không chờ access token hết hạn.
- Các hành động có hậu quả lớn cần quyết định mới nhất.

### 10.2. Trade-off

Mỗi request có thể cần thêm một hoặc nhiều truy vấn. Cần cache policy có version, timeout, bulkhead và chiến lược fail-closed. Nếu policy service không khả dụng, không tự cấp quyền dựa trên claim cũ khi SLO yêu cầu thu hồi tức thời.

Với thao tác nhạy cảm, cần kiểm tra quyền lại gần thời điểm commit side effect để tránh race giữa authorization và ghi dữ liệu.

## 11. So sánh các lựa chọn

| Phương án | Cách phản ánh thay đổi quyền | Độ trễ có thể đạt | Chi phí request | Rủi ro chính |
| --- | --- | --- | --- | --- |
| JWT local + exp ngắn | Chờ token hết hạn | Bị chặn bởi TTL còn lại | Thấp | Không đáp ứng SLO nhỏ hơn TTL |
| Denylist jti | Tra trạng thái token bị revoke | Phụ thuộc write/read propagation | State lookup mỗi request hoặc cache | Tăng trưởng store, consistency |
| Subject/session version | So sánh version hiện tại | Phụ thuộc version lookup/cache | Một state lookup hoặc cache | Cache stale, version update không nguyên tử |
| Introspection | Hỏi authorization server | Phụ thuộc endpoint và cache TTL | Network call hoặc cache | Availability và tail latency |
| Push invalidation | Phân phối thay đổi đến node | Phụ thuộc event propagation/ACK | Event traffic và consumer state | Event loss, lag, partition |
| Current entitlement check | Đọc quyền hiện tại | Phụ thuộc policy store | Policy lookup | Dependency tập trung, latency |
| Mô hình lai | Kết hợp các cơ chế | Theo SLO và consistency của thành phần mạnh nhất | Trung bình đến cao | Phức tạp vận hành |

Không có phương án nào tự động tốt nhất. Lựa chọn phải dựa trên:

- Thời gian tối đa cho phép quyền cũ còn hiệu lực.
- Quy mô số request và số subject/token.
- Số region và topology.
- Mức độ chấp nhận dependency trực tuyến.
- Khả năng vận hành event, cache và trạng thái tập trung.
- Hậu quả khi cho phép sai một request sau khi quyền đã bị thu hồi.

## 12. Thiết kế mô hình lai tham chiếu

Với tình huống Orders API, có thể chọn:

1. JWT vẫn được dùng để xác minh issuer, subject, client, audience, token type và thời hạn.
2. Token chứa authz_ver tại thời điểm phát hành.
3. Nguồn dữ liệu quyền tăng authz_ver nguyên tử khi quyền của subject thay đổi.
4. Resource server nhận push invalidation để cập nhật cache nhanh.
5. Resource server có version lookup trực tuyến hoặc cache có TTL ngắn làm nguồn kiểm chứng/fallback.
6. Hành động tạo/hủy đơn hàng dùng authorization check gần thời điểm commit.
7. Nếu không xác định được version hiện tại trong thời hạn policy, từ chối hành động nhạy cảm.

### 12.1. Luồng request

~~~text
Client
  |
  | Bearer access token
  v
Orders API
  |
  | 1. Verify JWS, issuer, audience, time, profile
  |
  | 2. Read subject authz_ver from trusted state/cache
  |
  | 3. Compare token.authz_ver with current version
  |
  | 4. Evaluate current scope/entitlement for action
  |
  | 5. Recheck at commit for high-impact operation
  v
Allow or Deny

Admin
  |
  | Revoke permission
  v
Authoritative authorization store
  |
  | Atomic update permission + authz_ver
  v
Transactional outbox / event publisher
  |
  v
Resource server instances invalidate/update cache
~~~

### 12.2. Pseudocode xác minh và so sánh version

~~~text
function authorizeOrdersRequest(request):
    token = extractBearerToken(request)
    verified = verifyJwtAndValidateProfile(
        token,
        expectedIssuer,
        expectedAudience,
        allowedAlgorithms,
        expectedTokenType
    )
    require verified

    claims = verified.claims
    require claims.sub exists
    require claims.authz_ver is a valid non-negative integer

    current = authorizationState.getVersion(
        subject = claims.sub,
        consistency = "required-by-revocation-SLO"
    )
    require current is known
    require claims.authz_ver == current.version

    decision = authorizationPolicy.evaluate(
        subject = claims.sub,
        action = request.action,
        resource = request.resource,
        currentState = current
    )
    require decision.allowed

    return authorizationContext(claims.sub, decision)
~~~

Đây là pseudocode khái niệm. Tên hàm consistency không đại diện API cụ thể; contract triển khai phải chỉ rõ nguồn dữ liệu, mức nhất quán, cache TTL, timeout và hành vi khi không đọc được trạng thái.

### 12.3. Lưu ý về cấp quyền mới

Khi thêm quyền, token cũ có thể không chứa scope mới. Có hai chính sách:

- Yêu cầu client lấy access token mới để nhận scope mới.
- API đánh giá entitlement hiện tại độc lập với scope cũ nếu profile và authorization contract cho phép.

Không tự thêm quyền vào principal chỉ vì version mới hơn. Việc cấp quyền phải đến từ nguồn policy có thẩm quyền. Cũng không để token cũ giữ quyền đã bị thu hồi.

## 13. Chọn mô hình theo mức độ rủi ro

Một thiết kế có thể phân loại hành động:

| Hành động | Ví dụ | Cách kiểm tra tham chiếu |
| --- | --- | --- |
| Đọc ít nhạy cảm | Đọc nội dung công khai hoặc dữ liệu ít rủi ro | JWT local và token lifetime phù hợp |
| Đọc dữ liệu cá nhân | Xem đơn hàng hoặc thông tin tài khoản | JWT verify và entitlement/session state theo SLO |
| Thay đổi dữ liệu thông thường | Cập nhật thông tin đơn hàng | JWT verify, current authorization và resource ownership |
| Thao tác có hậu quả lớn | Hoàn tiền, hủy đơn, đổi thông tin bảo mật | Current authorization, recheck tại commit, audit |
| Quản trị | Cấp/thu hồi role, khóa tài khoản | Authorization state có tính nhất quán mạnh và audit đầy đủ |

Không nên chỉ dựa vào HTTP method để phân loại. Một GET có thể trả dữ liệu rất nhạy cảm; một POST có thể là thao tác ít rủi ro. Policy phải gắn với action và resource thực tế.

## 14. Xử lý cache và consistency

Cache là yếu tố trực tiếp quyết định thời gian quyền cũ còn được chấp nhận.

### 14.1. Tính ngân sách stale

Nếu dùng cache TTL, thời gian stale tối đa gần đúng gồm:

~~~text
stale_window =
    event_delivery_delay
  + cache_invalidation_delay
  + fallback_cache_ttl
  + clock_or_scheduling_margin
~~~

Không cộng các thành phần một cách máy móc nếu chúng chồng lấp; hãy đo end-to-end từ commit đến quyết định cuối cùng. Nhưng mọi thành phần đều phải được tính vào ngân sách SLO.

### 14.2. Event invalidation và TTL fallback

Ví dụ:

- Event thường đến trong 100 ms.
- Consumer áp dụng invalidation trong 100 ms tiếp theo.
- Nếu event bị mất, fallback cache TTL là 1 giây.
- Hệ thống phát hiện consumer lag và fail-closed khi vượt deadline.

Các con số chỉ minh họa. Để tuyên bố đáp ứng SLO 2 giây, cần chứng minh cả đường bình thường lẫn đường fallback trong điều kiện tải và lỗi.

### 14.3. Strong consistency và eventual consistency

Nếu mọi request sau commit phải thấy version mới ngay, nguồn đọc phải cung cấp mức nhất quán đáp ứng yêu cầu đó. Một replica eventual consistency có thể trả version cũ sau khi primary đã commit.

Có thể:

- Đọc từ nguồn có tính nhất quán mạnh.
- Dùng cơ chế đồng bộ/lease có semantics rõ.
- Dùng event invalidation nhưng phải có ACK và fallback khi node không đồng bộ.
- Giới hạn hành động trên node/region không chứng minh được freshness.

Không gọi một hệ thống là “tức thời” chỉ vì event thường đến nhanh trong môi trường bình thường.

## 15. Network partition và fail-open/fail-closed

Giả sử Orders API ở region B mất kết nối đến authorization store và cũng không nhận được event invalidation. Region B chỉ còn cache version cũ.

Có hai lựa chọn:

**Fail-open:** tiếp tục cho phép request bằng trạng thái cache cũ. Availability cao hơn, nhưng không thể bảo đảm SLO thu hồi quyền.

**Fail-closed:** từ chối hoặc tạm dừng hành động cần kiểm tra trạng thái. Bảo vệ yêu cầu thu hồi, nhưng một lỗi mạng có thể làm giảm availability.

Với yêu cầu thu hồi quyền tức thời cho hành động nhạy cảm, fail-closed là lựa chọn tham chiếu. Nếu nghiệp vụ chọn fail-open, phải công bố rõ SLO bị nới lỏng và rủi ro chấp nhận.

### 15.1. Trạng thái unknown không phải trạng thái active

Khi không đọc được authorization state, kết quả là unknown. Không được diễn giải unknown thành:

- Subject vẫn active.
- Permission vẫn được cấp.
- Token chưa bị revoke.
- Cache cũ chắc chắn còn đúng.

Phân biệt rõ active, revoked và unknown trong API nội bộ cũng như metric vận hành.

## 16. Request đang chạy khi quyền bị thu hồi

Một điểm thường bị bỏ sót: request có thể đã vượt qua authorization trước khi quản trị viên thu hồi quyền nhưng chưa commit side effect.

Ví dụ:

1. Request tạo đơn hàng được authorize lúc T0 - 100 ms.
2. Admin thu hồi orders:write tại T0.
3. Request ghi dữ liệu tại T0 + 300 ms.

Nếu hệ thống chỉ kiểm tra ở đầu request, side effect vẫn có thể xảy ra sau khi quyền đã bị thu hồi.

Contract cần chọn semantics:

- **Admission-time authorization:** quyền được quyết định tại thời điểm request bắt đầu xử lý.
- **Commit-time authorization:** quyền phải còn hiệu lực tại thời điểm side effect được commit.
- **Lease/transaction authorization:** request có một khoảng lease hoặc transaction snapshot được định nghĩa rõ.

Với thao tác có hậu quả lớn, cân nhắc kiểm tra lại version/entitlement ngay trước commit hoặc ràng buộc thay đổi quyền và side effect bằng transaction/serialization phù hợp.

Không phải mọi hệ thống đều có thể thu hồi một side effect đã commit. Cần định nghĩa ranh giới nghiệp vụ: request đã được chấp nhận trước thời điểm thu hồi có thể hoàn tất hay phải bị hủy.

## 17. Kiểm thử SLO thu hồi quyền

Test phải đo từ thời điểm thay đổi quyền được commit, không chỉ từ lúc event được publish.

### 17.1. Functional tests

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token cũ có orders:write trước khi thu hồi | Ban đầu được phép |
| Admin thu hồi orders:write và commit | Version hoặc trạng thái quyền thay đổi |
| Request mới dùng token cũ sau khi propagation hoàn tất | Bị từ chối |
| Token mới chỉ có orders:read | Đọc được nếu các điều kiện khác hợp lệ |
| Token mới cố tạo đơn hàng | Bị từ chối |
| Thu hồi một permission | Không vô tình thu hồi quyền không liên quan nếu policy yêu cầu giữ lại |
| Khóa tài khoản | Mọi hành động bị cấm theo account policy |
| Thu hồi một session | Session khác không bị ảnh hưởng nếu phạm vi là session-level |

### 17.2. Timing tests

- Đo T0 đến khi từng instance áp dụng thay đổi.
- Gửi request liên tục trong cửa sổ propagation.
- Xác nhận p50, p95, p99 và maximum observed delay.
- Chạy với cold cache và warm cache.
- Chạy trong giờ tải cao.
- Chạy khi event queue có backlog.
- Chạy khi một instance vừa restart.
- Chạy khi có nhiều region.

Nếu SLO quy định chỉ sau deadline mới bắt buộc deny, test phải kiểm tra tất cả request bắt đầu sau deadline. Nếu contract yêu cầu deny ngay tại commit, mọi request được authorize sau T0 phải bị từ chối.

### 17.3. Concurrency và race tests

- Hai request đồng thời dùng cùng token trong khi permission update commit.
- Permission update xảy ra giữa authorization và database commit.
- Hai event version đến sai thứ tự.
- Event bị gửi lặp.
- Consumer ACK nhưng cache chưa cập nhật.
- Subject bị thu hồi rồi được cấp lại quyền.
- Token cũ được gửi sau khi version đã tăng nhiều lần.

Invariant quan trọng: version cũ không được làm trạng thái quyền mới bị ghi đè hoặc hạ xuống.

### 17.4. Failure tests

- Introspection timeout.
- Authorization store timeout.
- Event broker outage.
- Consumer offline quá SLO.
- Region partition.
- Cache không thể invalidated.
- Replication lag vượt ngưỡng.
- Clock drift giữa các node.
- Retry sau timeout khi không biết lần ghi trước đã commit hay chưa.

Kết quả unknown phải tuân theo fail-closed/fail-open policy đã định nghĩa. Không để fallback vô tình chấp nhận quyền cũ.

## 18. Metric và vận hành

Theo dõi các chỉ số:

| Metric | Ý nghĩa |
| --- | --- |
| permission_change_commit_timestamp | Mốc bắt đầu SLO |
| authorization_invalidation_lag | Độ trễ từ commit đến áp dụng |
| revocation_denied_request_count | Request bị từ chối do trạng thái đã thu hồi |
| stale_authorization_cache_age | Tuổi dữ liệu quyền trong cache |
| authz_version_mismatch_count | Token có version cũ |
| introspection_latency/error | Sức khỏe introspection |
| authorization_store_latency/error | Sức khỏe nguồn trạng thái |
| event_consumer_lag | Độ trễ consumer |
| event_gap_or_duplicate_count | Sự kiện mất thứ tự/lặp |
| fail_closed_request_count | Request bị từ chối do không xác minh được trạng thái |
| post_revocation_admission_count | Request được cho phép sau mốc deadline |

Metric cuối cùng cần bằng zero trong điều kiện SLO được cam kết. Không log raw JWT hoặc Authorization header. Dùng subject identifier đã kiểm soát hoặc pseudonymous ID phù hợp với chính sách dữ liệu.

### 18.1. Runbook khi SLO bị vi phạm

1. Xác định T0 từ audit record của thay đổi quyền.
2. Xác định resource server/region nào còn dùng version cũ.
3. Kiểm tra event delivery, consumer lag và ACK.
4. Kiểm tra cache TTL, invalidation và fallback path.
5. Kiểm tra replica lag hoặc partition.
6. Chuyển hành động nhạy cảm sang fail-closed nếu freshness không còn được bảo đảm.
7. Resync trạng thái từ nguồn có thẩm quyền.
8. Xác minh request sau deadline đều bị từ chối.
9. Ghi nhận nguyên nhân gốc và cập nhật SLO/test.

## 19. Bài tập thiết kế

Hãy giả định bạn chịu trách nhiệm cho Orders API và phải trình bày quyết định trước hội đồng kiến trúc.

### 19.1. Dữ kiện

- 20.000 request/giây trên toàn hệ thống.
- 8 resource server instance ở 2 region.
- JWT access token lifetime 15 phút.
- Quyền user có thể thay đổi bất kỳ lúc nào.
- Yêu cầu: request mới phải phản ánh quyền bị thu hồi trong 2 giây kể từ commit.
- API quản trị cần báo thành công chỉ sau khi thay đổi quyền được commit.
- Một số thao tác tạo/hủy đơn hàng có hậu quả nghiệp vụ cao.
- Khi không thể xác minh trạng thái mới, hệ thống không được tiếp tục dùng quyền cũ cho thao tác nhạy cảm.

### 19.2. Nhiệm vụ

1. Tính cửa sổ rủi ro của thiết kế JWT local hiện tại.
2. Chọn ít nhất ba phương án để so sánh.
3. Chọn nguồn dữ liệu có thẩm quyền cho permission/version.
4. Xác định phạm vi version: subject, session, client hay tenant.
5. Định nghĩa event invalidation, ACK, retry và resync.
6. Chọn cache TTL và ngân sách propagation sao cho tổng thể đáp ứng 2 giây.
7. Định nghĩa fail-open/fail-closed khi một region bị partition.
8. Xác định cách xử lý request đã authorize nhưng chưa commit.
9. Viết ít nhất 10 positive, negative, timing, concurrency và failure tests.
10. Đề xuất metric, dashboard và runbook.

### 19.3. Mẫu bảng quyết định

| Tiêu chí | JWT local + TTL | jti denylist | authz version + push | Introspection |
| --- | --- | --- | --- | --- |
| Đáp ứng 2 giây |  |  |  |  |
| Latency mỗi request |  |  |  |  |
| Tải lên dịch vụ trung tâm |  |  |  |  |
| Hành vi khi partition |  |  |  |  |
| Thu hồi một token |  |  |  |  |
| Thu hồi quyền của subject |  |  |  |  |
| Độ phức tạp vận hành |  |  |  |  |
| Khả năng kiểm chứng SLO |  |  |  |  |

Không điền bảng chỉ bằng “nhanh/chậm” hoặc “an toàn/không an toàn”. Ghi rõ điều kiện, TTL, consistency và failure behavior của từng phương án.

## 20. Đáp án tham khảo

Một phương án hợp lý cho dữ kiện bài tập là giữ JWT để xác minh danh tính và nguồn phát hành, kết hợp authorization version cùng push invalidation, và có version lookup có kiểm soát làm nguồn xác nhận.

Lý do:

- JWT local vẫn giữ được ưu điểm xác minh chữ ký và kiểm tra issuer/audience mà không phải introspect mọi thứ.
- Authorization version cho phép vô hiệu hóa toàn bộ token cũ của một subject/session bằng một cập nhật nhỏ.
- Push invalidation giúp các instance nhận thay đổi nhanh.
- Version lookup hoặc fallback freshness check giúp phát hiện node bị lỡ event.
- Fail-closed cho thao tác nhạy cảm khi không chứng minh được trạng thái hiện tại.
- Commit-time recheck giảm race giữa thu hồi quyền và side effect.

Một thiết kế tham chiếu:

1. Cập nhật permission và tăng authz_ver trong cùng transaction.
2. Ghi event vào transactional outbox cùng transaction.
3. Publisher gửi event có event_id và authz_ver.
4. Resource server chỉ áp dụng version lớn hơn version hiện tại.
5. Consumer ACK sau khi cache đã được cập nhật.
6. Cache version có TTL nhỏ hơn ngân sách SLO.
7. Nếu event lag vượt ngưỡng, node không được dùng cache cũ cho action nhạy cảm.
8. Khi store không truy cập được, node từ chối action cần freshness.
9. Với tạo/hủy đơn hàng, kiểm tra version/entitlement lại trước commit.
10. Dashboard đo commit-to-deny trên từng region và instance.

Không thể khẳng định mô hình này tự động đạt 2 giây chỉ bằng cách đặt cache TTL 1 giây. Cần đo propagation, queue, invalidation, read consistency và scheduling dưới tải thực. Nếu một node có thể bị partition vô thời hạn mà vẫn tiếp tục cho phép bằng cache cũ, SLO không được bảo đảm.

## 21. Rubric đánh giá thiết kế

| Tiêu chí | Đạt yêu cầu khi |
| --- | --- |
| Hiểu JWT | Nêu đúng giới hạn của token tự chứa và phân biệt authentication/authorization |
| SLO | Có T0, deadline, phạm vi request và cách đo |
| So sánh | Đánh giá ít nhất ba phương án cùng latency, consistency, availability và chi phí |
| Trạng thái | Xác định nguồn có thẩm quyền và phạm vi version/revocation |
| Cache/event | Có TTL, invalidation, ACK, retry, gap detection và resync |
| Partition | Có hành vi fail-open/closed rõ theo mức rủi ro |
| Race | Xử lý request in-flight và commit-time authorization |
| Kiểm thử | Có timing, concurrency, multi-region và failure tests |
| Vận hành | Có metric, cảnh báo và runbook |
| Lập luận | Mọi đánh đổi được gắn với yêu cầu và bằng chứng đo lường |

## 22. Tình huống tự kiểm tra

Một subject có token chứa authz_ver = 4. Admin thu hồi quyền và nguồn dữ liệu commit authz_ver = 5. Region A nhận event sau 200 ms; Region B đang bị partition và tiếp tục dùng cache version 4. SLO quy định mọi request mới sau 2 giây phải bị từ chối nếu dùng quyền đã thu hồi.

**Câu hỏi 1:** Region B có thể tiếp tục cho phép request chỉ vì chữ ký JWT hợp lệ không?

**Trả lời:** Không. Chữ ký chỉ xác minh token được ký hợp lệ. Region B không thể chứng minh authorization state còn mới, nên phải áp dụng fallback freshness check hoặc fail-closed khi không thể xác minh.

**Câu hỏi 2:** Chỉ đặt cache TTL 1 giây có đủ không?

**Trả lời:** Chưa đủ nếu node có thể tiếp tục dùng cache hết hạn khi store không truy cập được. TTL chỉ giới hạn stale khi cache hết hạn thực sự buộc hệ thống refresh hoặc từ chối. Phải kiểm thử hành vi khi refresh thất bại.

**Câu hỏi 3:** Event version 4 đến sau event version 5 có được áp dụng không?

**Trả lời:** Không. Consumer phải bỏ qua version cũ hơn version hiện tại. Event ID/version giúp xử lý lặp và sai thứ tự.

**Câu hỏi 4:** Request đã authorize trước khi thu hồi nhưng chưa commit thì sao?

**Trả lời:** Kết quả phụ thuộc contract admission-time hay commit-time. Với hành động có hậu quả cao, kiểm tra lại quyền/version gần thời điểm commit để tránh side effect sau khi quyền đã mất.

**Câu hỏi 5:** Nếu introspection cache active trong 30 giây nhưng SLO là 2 giây thì sao?

**Trả lời:** Cache TTL đó không đáp ứng SLO nếu không có invalidation có bảo đảm. Phải giảm TTL, bổ sung invalidation đáng tin cậy hoặc chọn cơ chế khác.

## 23. Ghi nhớ

JWT tự chứa đã ký là snapshot của claims tại thời điểm phát hành. Xác minh chữ ký cục bộ không thể tự biết quyền vừa bị thu hồi. Token lifetime ngắn chỉ giới hạn cửa sổ rủi ro; nó không tạo thu hồi tức thời.

Muốn phản ánh quyền thay đổi nhanh, cần một nguồn trạng thái hiện tại và một hợp đồng về freshness: denylist, authorization/session version, introspection, current entitlement lookup hoặc push invalidation có fallback. Cache, event propagation và replication đều phải nằm trong ngân sách SLO.

Đừng quên request đang chạy dở. Nếu nghiệp vụ yêu cầu quyền còn hiệu lực tại thời điểm side effect commit, cần kiểm tra lại ở ranh giới commit. Khi không thể xác minh trạng thái trong điều kiện yêu cầu thu hồi nghiêm ngặt, fail-open sẽ phá vỡ bảo đảm.

**Quyết định đúng không nằm ở việc chọn JWT hay không chọn JWT; nó nằm ở cách hệ thống chứng minh quyền vẫn còn hiệu lực tại thời điểm thực hiện hành động.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc token, claims và thời hạn.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token tại authorization server.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): giao thức thu hồi token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh JWT an toàn.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access token, refresh token và thực hành OAuth 2.0.
