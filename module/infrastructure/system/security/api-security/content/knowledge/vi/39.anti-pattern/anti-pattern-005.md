# Rate limit chỉ theo IP

## 1. Anti-pattern là gì?

Rate limit chỉ theo IP là cách giới hạn số request bằng một counter gắn với địa chỉ IP nguồn, ví dụ mỗi IP được gọi tối đa 100 request/phút. Khi vượt ngưỡng, hệ thống trả 429 Too Many Requests.

IP là một tín hiệu hữu ích ở lớp mạng và edge, nhưng không phải danh tính ổn định của user, partner, application hay tenant. Một IP có thể đại diện cho hàng nghìn người dùng hợp lệ; một người dùng hoặc bot có thể thay đổi IP liên tục. Vì vậy, dùng IP làm khóa duy nhất cho mọi API rate limit tạo ra hai kết quả xấu:

- **False positive:** nhiều người dùng hợp lệ dùng chung IP bị giới hạn như một người.
- **False negative:** một attacker phân tán request qua nhiều IP để vượt giới hạn.

Ví dụ đơn giản:

~~~text
Rate limit key = source IP
Limit          = 100 requests / minute

NAT gateway
  ├── User A
  ├── User B
  ├── User C
  ├── Mobile app D
  └── Partner E

Tất cả cùng bị tính vào một bucket IP.
~~~

Ở chiều ngược lại, bot có thể dùng nhiều proxy, mạng di động hoặc địa chỉ IPv6 khác nhau để nhận nhiều bucket mới. Nếu mỗi IP có 100 request/phút, 1.000 IP có thể tạo ra tổng lưu lượng lớn hơn rất nhiều giới hạn dự kiến.

Rate limit theo IP có thể là một lớp bảo vệ ở edge, nhất là trước authentication hoặc với endpoint public. Anti-pattern xuất hiện khi coi nó là cơ chế duy nhất để bảo vệ tài nguyên, account, tenant và business operation.

## 2. IP không phải user identity

Địa chỉ IP mô tả điểm mạng mà server quan sát được tại một thời điểm. Nó không chứng minh:

- Ai đang đăng nhập.
- Request thuộc account nào.
- Client application hoặc partner nào đang gọi.
- Tenant nào sở hữu dữ liệu.
- User có quyền thực hiện operation hay không.
- Các request từ cùng IP có cùng người điều khiển hay không.

Một IP public có thể là:

- NAT của văn phòng hoặc gia đình.
- Carrier-grade NAT của nhà mạng di động.
- Egress gateway của Kubernetes, cloud hoặc corporate proxy.
- VPN gateway hoặc secure web gateway.
- Proxy/CDN/WAF đứng trước API.
- Địa chỉ của một máy chủ hoặc bot.

Ngược lại, một principal có thể xuất hiện từ nhiều IP do chuyển mạng Wi-Fi/4G/5G, VPN, roaming, IPv6 privacy address hoặc hạ tầng cloud thay đổi.

Do đó, không dùng IP làm khóa duy nhất cho quota user, quota tenant, giới hạn thao tác nhạy cảm hoặc chính sách chống brute force.

## 3. False positive do NAT và mạng dùng chung

NAT cho nhiều thiết bị chia sẻ một public IP. Nếu API đặt giới hạn 100 request/phút/IP, một văn phòng có 300 nhân viên có thể vượt ngưỡng dù từng người chỉ gọi API bình thường.

Các tình huống thường gặp:

- Mobile carrier gom nhiều thuê bao qua một số địa chỉ egress.
- Nhiều pod hoặc service trong cùng cluster đi ra qua một NAT gateway.
- Nhiều người dùng của một doanh nghiệp dùng chung proxy.
- Một trường học, thư viện hoặc điểm Wi-Fi có nhiều người truy cập.
- Nhiều tenant của SaaS đi qua cùng một corporate egress.

Hậu quả không chỉ là trải nghiệm kém. Một user có thể vô tình làm các user khác mất khả năng đăng nhập, tra cứu hoặc hoàn tất giao dịch. Đây là dạng noisy neighbor do chọn sai dimension của limiter.

IP bucket vẫn có ích để hạn chế burst từ một nguồn mạng, nhưng ngưỡng phải đủ phù hợp với traffic chia sẻ và cần các bucket khác để bảo vệ từng account/tenant.

## 4. False negative do attacker thay đổi IP

Nếu limiter chỉ có một bucket cho mỗi IP, attacker có thể tăng tổng tốc độ bằng cách phân tán request:

- Dùng botnet với nhiều thiết bị/địa chỉ.
- Luân phiên proxy hoặc VPN exit.
- Tạo request qua nhiều cloud egress.
- Dùng nhiều mạng di động hoặc kết nối khác nhau.
- Thay đổi IPv6 address trong cùng một prefix được cấp.

Ví dụ, nếu một IP được phép 60 request/phút, 500 IP có thể tạo 30.000 request/phút mà mỗi bucket riêng lẻ vẫn nằm dưới ngưỡng.

IP rotation không nhất thiết cần một attacker có hạ tầng lớn. Một script có thể gọi API từ nhiều môi trường hoặc người dùng thật có thể vô tình tạo ra nhiều nguồn IP khác nhau. Limiter cần quan sát identity và hành vi ở cấp account/client/tenant, đồng thời giữ một giới hạn tổng thể cho service.

## 5. IPv4, IPv6 và chuẩn hóa địa chỉ

Không nên giả định một user luôn có một địa chỉ IP cố định.

Với IPv4, NAT và proxy làm nhiều user chia sẻ địa chỉ. Với IPv6, client có thể dùng privacy address hoặc thay interface identifier trong cùng một network prefix. Nếu tạo bucket cho từng địa chỉ IPv6 đầy đủ, một client có thể nhận nhiều bucket bằng cách thay địa chỉ trong prefix được cấp.

Một số hệ thống gom IPv6 theo prefix, ví dụ /64, nhưng đây chỉ là heuristic. Mạng di động, ISP và enterprise có cách cấp prefix khác nhau; chọn prefix quá rộng có thể gom nhiều user hợp lệ vào một bucket. Hãy cấu hình prefix theo threat model và dữ liệu thực tế, không hard-code một giá trị cho mọi network.

Chuẩn hóa IP trước khi dùng làm key:

- Parse địa chỉ bằng thư viện IP đáng tin cậy, không xử lý bằng regex đơn giản.
- Chuẩn hóa IPv4-mapped IPv6 theo chính sách nhất quán.
- Xác định cách xử lý zone identifier của IPv6; không để chuỗi không hợp lệ tạo key tùy ý.
- Nếu dùng prefix, tính prefix từ binary address sau khi parse.
- Giới hạn key length và từ chối input không hợp lệ.
- Không dùng chuỗi header thô làm IP key.

Không dùng reverse DNS hoặc geolocation làm identity. Những dữ liệu đó có thể thay đổi, chậm, không chính xác và không phù hợp làm khóa bảo mật.

## 6. Proxy header có thể làm sai IP key

Khi API đứng sau load balancer, CDN hoặc gateway, socket peer thường là proxy. Hệ thống có thể dùng Forwarded hoặc X-Forwarded-For để xác định client IP gốc.

Các header này không tự động đáng tin. Client có thể tự gửi:

~~~http
X-Forwarded-For: 203.0.113.10
Forwarded: for=203.0.113.10
~~~

Nếu application lấy giá trị đầu tiên trong X-Forwarded-For mà không xác định trusted proxy, attacker có thể chọn IP key của mình hoặc của người khác. Điều này có thể gây bypass, chia nhỏ bucket hoặc làm nạn nhân bị rate limit.

Quy tắc an toàn:

1. Chỉ chấp nhận forwarding metadata từ proxy nằm trong trusted proxy configuration.
2. Edge phải xóa header client tự gửi hoặc ghi đè bằng thông tin đã xác minh.
3. Chỉ cho phép upstream nhận traffic từ proxy/gateway được chỉ định.
4. Parse proxy chain theo cấu hình thực tế; không mặc định phần tử đầu tiên là client.
5. Đi từ socket peer đáng tin cậy và xử lý chain theo đúng quy ước append/overwrite của proxy.
6. Nếu không xác minh được client IP, dùng peer IP hoặc phân loại nguồn là unknown theo policy.

Không cho client truy cập trực tiếp application port nếu application tin X-Forwarded-For do gateway tạo. Cần khóa đường direct access bằng network policy/firewall và kiểm tra ở application.

## 7. Tại sao chỉ thêm X-API-Key hoặc User-Agent cũng chưa đủ?

Một số hệ thống thay IP bằng User-Agent, custom header hoặc device ID do client gửi. Các giá trị này dễ bị giả mạo và không chứng minh danh tính.

Ví dụ không an toàn:

~~~text
rateLimitKey = request.header["X-User-ID"]
rateLimitKey = request.header["X-Device-ID"]
rateLimitKey = request.header["User-Agent"]
~~~

Attacker có thể đổi giá trị mỗi request hoặc dùng ID của người khác. API key chỉ hữu ích làm identity dimension khi key đã được xác thực, có trạng thái active/revoked và được ánh xạ tới client principal. Không dùng raw API key làm Redis key hoặc log; dùng ID nội bộ ổn định.

User-Agent, device fingerprint và client-supplied version có thể hỗ trợ risk signal, nhưng không thay thế authenticated principal.

## 8. Những dimension nên cân nhắc

Rate limit hiệu quả cần chọn dimension theo mục tiêu bảo vệ:

| Dimension | Khóa gợi ý | Bảo vệ điều gì? | Hạn chế |
|---|---|---|---|
| Source IP | IP/prefix đã chuẩn hóa | Burst từ một nguồn mạng | NAT, proxy, IP rotation |
| Authenticated subject | Principal ID ổn định | Một account/user | Một user có thể dùng nhiều account |
| API client | Client ID/API key ID đã xác thực | Partner hoặc application | Credential bị chia sẻ/compromise |
| Tenant | Tenant ID đã xác minh | Fairness và quota tổ chức | Tenant lớn có traffic hợp lệ lớn |
| Route/operation | Route ID + method/action | Bảo vệ endpoint nhạy cảm | Không phân biệt caller nếu đứng riêng |
| Global service | Service/route group | Bảo vệ tổng capacity | Có thể gây noisy neighbor |
| Resource/object | Resource ID hoặc aggregate ID | Thao tác lặp trên một object | Cần kiểm soát cardinality và privacy |
| Concurrency | Principal/tenant/route | Công việc đang chạy đồng thời | Cần lease/timeout và cleanup |
| Cost/weight | Operation cost class | Tài nguyên tiêu thụ khác nhau | Cần ước lượng cost hợp lý |

Không phải endpoint nào cũng cần tất cả dimension. Hãy chọn theo tài sản cần bảo vệ, mức xác thực, mức tiêu thụ tài nguyên và khả năng nhận diện principal.

## 9. Thiết kế nhiều lớp thay vì một IP bucket

Một request có thể chịu nhiều giới hạn đồng thời:

~~~text
Incoming request
      |
      v
Trusted source / edge IP limit
      |
      v
Authentication
      |
      v
Authenticated client / subject limit
      |
      v
Verified tenant limit
      |
      v
Route / operation cost limit
      |
      v
Global service capacity
      |
      v
Business operation
~~~

Ví dụ với API tạo báo cáo:

- IP bucket: hạn chế burst từ một nguồn.
- Client bucket: giới hạn partner integration.
- Tenant bucket: bảo đảm một tổ chức không chiếm hết worker.
- Subject bucket: giới hạn user tạo báo cáo.
- Route bucket: bảo vệ endpoint export đắt tiền.
- Global concurrency: bảo vệ database và report workers.

Request phải vượt qua mọi policy áp dụng. Các bucket nên có owner, limit, window, action khi vượt và cách override được audit.

Không dùng một composite key duy nhất kiểu IP + user + tenant cho mọi trường hợp. Nếu key là tổ hợp tất cả dimension, attacker đổi một dimension có thể tạo bucket mới và né giới hạn dimension còn lại. Dùng các bucket độc lập hoặc hierarchical limits để mỗi chiều vẫn có tác dụng.

## 10. Pre-authentication và post-authentication limit

Một số endpoint cần rate limit trước khi xác thực:

- Login, token issuance và password reset.
- Endpoint public hoặc registration.
- Webhook handshake chưa xác định được partner.
- Endpoint tốn tài nguyên trước khi có principal.

Ở giai đoạn pre-auth, có thể dùng source IP/prefix, network reputation, route và global capacity. Đây là lớp bảo vệ tạm thời, không phải danh tính người gọi.

Sau khi authentication thành công, áp dụng thêm limit theo:

- User/subject ID đã xác minh.
- OAuth client ID hoặc partner ID.
- API key ID đã ánh xạ.
- Tenant context đã xác minh.
- Route/operation và resource scope.

Không cho request vượt qua authentication rồi bỏ toàn bộ IP/network control. Cũng không áp dụng IP limit quá chặt trước authentication đến mức một văn phòng hoặc mạng di động không thể đăng nhập.

## 11. Login và password reset cần nhiều dimension

Rate limit login chỉ theo IP có hai lỗ hổng:

1. Nhiều user sau NAT bị ảnh hưởng khi một user gửi nhiều lần.
2. Attacker thử cùng một account từ nhiều IP để né IP bucket.

Nên phối hợp:

- Per-account hoặc per-subject attempt budget.
- Per-source IP/prefix budget.
- Global authentication capacity.
- Risk signal như thiết bị, ASN hoặc reputation nếu có căn cứ.
- Progressive delay hoặc challenge khi hành vi bất thường.
- Credential stuffing detection theo nhiều account và nhiều nguồn.

Với account chưa tồn tại, vẫn cần một cách tính budget chống enumeration và abuse mà không tiết lộ account có tồn tại. Có thể dùng key được HMAC từ normalized login identifier để tránh lưu email/username thô trong limiter.

Không khóa account vô thời hạn chỉ vì vượt attempt limit. Attacker có thể cố ý gửi sai password để khóa tài khoản của nạn nhân (account lockout DoS). Dùng delay, challenge, temporary throttling và luồng recovery có kiểm soát; giữ thông báo lỗi không tiết lộ account state.

Password reset, OTP, email verification và token resend nên có limit theo account/recipient, source và global provider quota. Nếu chỉ limit IP, attacker có thể gửi nhiều request từ nhiều IP để spam một email hoặc số điện thoại.

## 12. API client và partner quota

Với machine-to-machine API, client ID đã xác thực thường là dimension quan trọng hơn IP. Partner có thể chạy nhiều region, NAT gateway hoặc worker pool; IP thay đổi không đồng nghĩa partner thay đổi.

Mỗi client nên có:

- Client ID ổn định và owner.
- Allowed API/operation scopes.
- Per-client rate và quota.
- Per-route limit cho operation đắt tiền.
- Burst allowance và concurrency cap.
- Credential rotation/revocation.
- Audit và contact khi vượt quota.

Không dùng IP allowlist làm thay thế client authentication. IP allowlist có thể là lớp network defense bổ sung, nhưng partner vẫn phải chứng minh identity bằng mTLS, OAuth2 client credentials hoặc API key được quản lý.

Nếu một client ID được nhiều ứng dụng hoặc nhiều tenant dùng chung, cần cân nhắc cấp client identity riêng hoặc thêm tenant bucket. Không để một integration dùng chung credential làm mọi khách hàng của partner bị tính vào cùng một quota mà không có chủ đích.

## 13. Tenant fairness và noisy neighbor

Trong SaaS multi-tenant, rate limit theo IP không thể đảm bảo công bằng giữa tenant. Nhiều tenant có thể dùng chung corporate egress; một tenant cũng có thể phát request từ nhiều IP.

Tenant bucket nên lấy từ context đã xác minh:

- Membership/delegated grant đã được kiểm tra.
- Tenant của resource được tải trong đúng scope.
- Client-to-tenant mapping đã đăng ký.
- Workload identity được phép hành động cho tenant đó.

Không tin tenant ID từ header/body chỉ để chọn limiter key. Nếu attacker chọn tenant khác, họ có thể tiêu quota của nạn nhân hoặc tự tạo bucket mới.

Kết hợp:

- Per-tenant request rate/quota.
- Per-tenant concurrency.
- Per-subject limit để ngăn một user chiếm quota tenant.
- Global service limit để bảo vệ capacity.
- Route cost để operation đắt bị giới hạn chặt hơn.

Quota tenant cần được thiết kế cùng hợp đồng dịch vụ và billing. Rate limit ngắn hạn và quota theo ngày/tháng là hai khái niệm khác nhau; không nên gộp thành một counter không rõ semantics.

## 14. Limit theo operation và chi phí

Một request GET đơn giản và một request export một triệu bản ghi không tiêu thụ tài nguyên như nhau. Nếu mỗi request tính một đơn vị, attacker có thể dùng endpoint đắt để làm cạn CPU, database, memory hoặc downstream provider.

Gán cost class hoặc weight theo operation:

| Operation | Chi phí tương đối | Biện pháp |
|---|---|---|
| GET metadata | Thấp | Rate limit thông thường |
| Search với filter/index | Trung bình | Page size cap, per-subject rate |
| Generate report | Cao | Quota, concurrency và async job budget |
| Bulk export | Rất cao | Permission riêng, row cap, tenant quota |
| Password reset/email send | Có chi phí provider | Per-recipient, per-account và global provider cap |
| Payment/refund | Chi phí nghiệp vụ cao | Function authorization, idempotency và operation-specific limit |

Cost không nên chỉ dựa vào số byte request vì payload nhỏ vẫn có thể kích hoạt query đắt. Dùng operation metadata, page size, số object, thời gian xử lý ước lượng hoặc cost model đã đo.

Rate limit không thay thế pagination, query timeout, maximum payload, concurrency control hoặc authorization. Nó là một lớp trong resource-consumption defense.

## 15. Rate, quota và concurrency là ba giới hạn khác nhau

| Cơ chế | Giới hạn | Ví dụ |
|---|---|---|
| Rate limit | Tốc độ request trong cửa sổ thời gian | 30 request/giây |
| Quota | Tổng mức sử dụng trong chu kỳ | 100.000 API units/tháng |
| Concurrency limit | Số tác vụ đang chạy cùng lúc | Tối đa 3 report jobs/tenant |

Một user có thể gửi ít request nhưng mỗi request chạy 10 phút, làm cạn worker. Ngược lại, nhiều request nhẹ có thể tạo burst CPU/network dù không có job dài.

Endpoint bất đồng bộ cần limit cả job submission rate, số job pending, số job running, thời gian giữ tài nguyên và số lần retry. Khi job hoàn tất hoặc hết hạn, release concurrency lease an toàn.

## 16. Thuật toán và cách áp dụng bucket

Các thuật toán phổ biến:

| Thuật toán | Đặc điểm | Khi phù hợp |
|---|---|---|
| Fixed window | Đơn giản, reset theo cửa sổ | Policy cơ bản, chấp nhận burst ở biên |
| Sliding log | Chính xác theo từng timestamp | Limit nhỏ, chi phí lưu cao hơn |
| Sliding window counter | Ước lượng mượt giữa hai cửa sổ | Cân bằng chi phí và độ chính xác |
| Token bucket | Cho phép burst có kiểm soát | API có traffic dao động |
| Leaky bucket | Làm mượt tốc độ xử lý | Queue hoặc downstream cần throughput ổn định |

Mỗi dimension có thể dùng thuật toán khác nhau. Ví dụ IP edge dùng token bucket, per-account login dùng progressive delay, tenant export dùng quota và concurrency.

Không chỉ đặt một fixed window cho toàn bộ API. Request có thể dồn vào ranh giới hai cửa sổ và tạo burst gần gấp đôi ngưỡng danh nghĩa. Chọn thuật toán theo cách hệ thống xử lý burst và mục tiêu bảo vệ.

## 17. Distributed rate limiter phải nhất quán giữa nhiều replica

Nếu mỗi application pod giữ counter trong memory, scale-out làm giới hạn bị nhân lên:

~~~text
Limit configured = 100 requests/minute

Pod A: allows 100
Pod B: allows 100
Pod C: allows 100

Effective limit can approach 300 requests/minute.
~~~

Với nhiều replica, cần limiter dùng state chung hoặc gateway/distributed service có semantics rõ. Redis, database atomic counter hoặc managed rate-limit service là các lựa chọn tùy yêu cầu.

Các điểm cần kiểm tra:

- Increment và kiểm tra limit phải atomic.
- Nhiều dimension cần được kiểm tra nhất quán.
- Đồng hồ giữa node không làm lệch cửa sổ đáng kể.
- TTL tự xóa bucket sau khi hết window.
- Key không tăng vô hạn theo input attacker.
- Redis failover/replication và network partition có behavior được định nghĩa.
- Limiter có capacity riêng để không trở thành điểm DoS.

Với Redis, có thể dùng Lua script hoặc primitive atomic phù hợp để đọc counter, cập nhật token và quyết định allow/deny trong một thao tác. Nếu dùng Redis Cluster, thiết kế key/hash slot cho multi-key operation; không giả định mọi key ở mọi shard có thể được cập nhật nguyên tử bằng một script.

## 18. Multi-dimensional check và tránh tiêu quota sai

Khi một request phải qua IP, client, tenant và route bucket, thứ tự kiểm tra có thể ảnh hưởng việc tính usage:

- Nếu consume IP bucket rồi tenant bucket từ chối, request có bị tính vào IP budget không?
- Nếu consume nhiều bucket nhưng một bước lỗi, có rollback reservation không?
- Hai request đồng thời có thể cùng thấy còn quota và vượt ngưỡng không?
- Retry có bị tính hai lần không?

Với policy cần chính xác, dùng atomic multi-bucket decision hoặc reservation/commit model. Có thể kiểm tra các giới hạn rẻ trước, nhưng cần định nghĩa rõ bucket nào tính attempted traffic và bucket nào chỉ tính accepted operation.

Một cách thực tế là:

1. Edge IP bucket tính mọi attempt để chống flood.
2. Authentication bucket tính các attempt login theo account/source.
3. Authenticated operation bucket chỉ consume khi request đủ điều kiện vào operation.
4. Quota/concurrency được reserve khi tạo job và settle/release theo lifecycle.

Không để request bị từ chối ở một bucket làm tăng vô hạn usage ở bucket khác ngoài mục đích đã định.

## 19. Key design, privacy và cardinality

Limiter key thường được lưu trong Redis hoặc metrics/log. Không đưa dữ liệu nhạy cảm thô vào key:

- Không dùng access token, API key hoặc password.
- Không dùng email/phone thô nếu có thể.
- Không ghi full request URL có object ID.
- Không dùng user-supplied header làm principal.

Nên dùng ID nội bộ ổn định hoặc HMAC của identifier đã chuẩn hóa:

~~~text
rl:ip:<normalized-ip-or-prefix>:<route-group>
rl:subject:<opaque-subject-id>:<route-group>
rl:client:<verified-client-id>:<route-group>
rl:tenant:<verified-tenant-id>:<route-group>
rl:global:<service>:<route-group>
~~~

HMAC giúp tránh lộ identifier trong key store nhưng không thay thế access control. Secret dùng HMAC phải được quản lý và có kế hoạch rotation; khi đổi key cần tính tới bucket cũ trong thời gian overlap.

Đặt TTL cho bucket, giới hạn độ dài và số lượng dimension, validate identifier trước khi tạo key. Nếu attacker có thể tạo hàng triệu tenant ID hoặc device ID tùy ý, limiter store có thể bị memory exhaustion.

Không dùng mỗi IP hoặc user ID làm label metric có cardinality không giới hạn. Metrics nên dùng route group, status class, policy ID và dimension category; chi tiết định danh đặt trong audit/log có kiểm soát.

## 20. Xử lý request khi vượt limit

Khi một policy thực sự bị vượt, API thường trả 429 Too Many Requests:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 30
Cache-Control: no-store
~~~

~~~json
{
  "code": "RATE_LIMITED",
  "message": "Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
  "retryAfterSeconds": 30
}
~~~

Có thể dùng RateLimit fields theo RFC 9333 nếu API/gateway hỗ trợ và contract quy định. Chỉ trả limit/remaining/reset phù hợp với chính sách công khai; không tiết lộ ngưỡng nội bộ hoặc quota của tenant khác.

Retry-After nên phản ánh thời điểm retry hợp lý. Client cần exponential backoff với jitter và không retry vô hạn. Với POST tạo side effect, cần idempotency key để retry không tạo đơn, payment hoặc job trùng.

Không trả 429 cho mọi lỗi authentication:

- Credential thiếu/sai thường là 401 theo contract.
- Principal đã xác thực nhưng thiếu quyền thường là 403.
- 429 dành cho request bị policy rate/quota thực sự từ chối.
- 503 có thể phù hợp khi service/limiter dependency không sẵn sàng theo contract, nhưng không dùng để che mọi deny.

Không đưa IP, account hoặc tenant của người khác vào error message.

## 21. Fail-open hay fail-closed khi limiter lỗi?

Nếu Redis hoặc rate-limit service không khả dụng, API cần policy rõ:

| Endpoint/operation | Hướng xử lý có thể phù hợp |
|---|---|
| Public read nhẹ | Có thể dùng local emergency cap hoặc fail-open có giám sát |
| Login/password reset | Giữ giới hạn bảo vệ bằng fallback; tránh mở flood hoàn toàn |
| Payment/refund/secret rotation | Fail-closed hoặc yêu cầu kiểm tra thay thế an toàn |
| Export/report đắt | Từ chối tạm hoặc queue có quota dự phòng |
| Health check | Không phụ thuộc business limiter nếu probe cần hoạt động |

Không có một lựa chọn duy nhất cho mọi endpoint. Fail-open tăng availability nhưng có thể mở đường resource exhaustion; fail-closed bảo vệ tài nguyên nhưng có thể gây outage diện rộng nếu limiter là dependency dùng chung.

Thiết kế nên:

- Có local emergency limit giới hạn khi shared limiter down.
- Có circuit breaker và timeout ngắn cho limiter call.
- Không retry limiter vô hạn.
- Phân loại endpoint theo criticality.
- Alert khi fallback mode được kích hoạt.
- Có kill switch/override được audit và expiry.
- Kiểm thử behavior khi limiter timeout, partition hoặc trả dữ liệu sai.

## 22. Không dùng rate limit thay authorization hoặc business control

Rate limit không quyết định caller có quyền làm gì. Một user có permission users:delete vẫn cần object authorization; một user không có permission không được phép gọi function chỉ vì còn quota.

Tương tự:

- Quota còn không đồng nghĩa được truy cập tenant khác.
- IP trong allowlist không chứng minh partner identity.
- Client ID hợp lệ không tự cấp quyền export mọi dữ liệu.
- Limit thấp không sửa được SSRF, injection hoặc BOLA.
- 429 không thay thế kiểm tra authentication/authorization.

Thứ tự xử lý phải được cân nhắc để tránh lộ thông tin. Có thể áp dụng coarse IP/global limit ở edge trước authentication, sau đó xác thực và authorize, rồi áp dụng per-principal/per-tenant/resource limit trước side effect.

## 23. Ví dụ policy nhiều chiều

Một policy có thể mô tả các bucket theo operation:

~~~yaml
policies:
  - route: auth.login
    dimensions:
      - key: source-ip-prefix
        algorithm: token-bucket
        rate: 20/minute
        burst: 10
      - key: normalized-account-hmac
        algorithm: sliding-window
        rate: 8/15-minutes
      - key: global-auth
        algorithm: token-bucket
        rate: 500/second

  - route: reports.create
    dimensions:
      - key: verified-subject
        rate: 5/minute
      - key: verified-tenant
        rate: 50/hour
      - key: report-concurrency-per-tenant
        limit: 3
      - key: global-report-workers
        limit: 100
~~~

Đây là policy minh họa, không phải cú pháp chuẩn của gateway hay limiter. Giá trị limit phải được xác định từ capacity, traffic baseline, SLA và business contract. Không copy nguyên các con số vào production.

## 24. Ví dụ luồng xử lý trong Java

Pseudo-code cho bước limiter sau khi caller đã được xác thực và context đã được resolve:

~~~java
RateLimitDecision decision = limiter.checkAll(
    RateLimitKey.client(authenticatedClient.id(), routeGroup),
    RateLimitKey.subject(principal.subjectId(), routeGroup),
    RateLimitKey.tenant(verifiedTenant.id(), routeGroup),
    RateLimitKey.global(serviceId, routeGroup),
    operationCost
);

if (!decision.allowed()) {
    throw new RateLimitExceededException(decision.retryAfter());
}

authorization.require(principal, operation.permission());
objectPolicy.requireAccess(principal, resource);
return operation.execute();
~~~

Source IP không xuất hiện trong đoạn này vì coarse IP/global attempt limit đã được áp dụng ở edge trước authentication. Không thể dùng authenticatedClient, principal hoặc verifiedTenant trước khi chúng tồn tại và đã được xác minh. Authorization vẫn phải được enforce trước side effect. Với operation đắt, có thể áp dụng route-level limit trước query nặng, sau đó kiểm tra permission/object và reserve quota/concurrency trước khi thực thi.

Một flow rõ hơn:

~~~text
1. Resolve trusted source IP and route
2. Apply coarse IP/global attempt limit
3. Authenticate caller
4. Resolve verified client, subject and tenant context
5. Apply principal/client/tenant/operation limits
6. Authorize function and object
7. Reserve quota/concurrency for expensive work
8. Execute or enqueue operation
9. Settle/release reservation and record usage
~~~

Không tin IP từ raw header và không tin tenant từ request body. Mọi dimension phải lấy từ context đã được xác minh hoặc từ nguồn server-side.

## 25. Vị trí triển khai limiter

Rate limiting có thể được đặt ở nhiều lớp:

| Vị trí | Phù hợp | Giới hạn |
|---|---|---|
| CDN/WAF | Flood/burst ở public edge, source network | Thường không biết business principal/tenant |
| API Gateway | Route, client credential, coarse quota | Có thể thiếu object/business context |
| Application filter/interceptor | Principal, tenant, operation và cost | Phải bảo vệ mọi instance và đường direct access |
| Service/domain layer | Business action, resource và workflow | Không thay thế edge flood defense |
| Worker/queue | Job rate, concurrency, retry và provider quota | Cần quản lý job identity và lifecycle |

Một kiến trúc có thể dùng nhiều lớp. Gateway chặn burst trước khi request vào cluster; application áp dụng per-subject/tenant; domain layer kiểm tra action cost; worker giữ concurrency quota cho job.

Nếu limiter chỉ nằm ở gateway, direct upstream path có thể bypass. Nếu chỉ nằm trong application memory, scale-out có thể nhân limit. Nếu chỉ nằm ở domain service, flood có thể tiêu tốn tài nguyên trước khi tới đó.

## 26. Quan sát, cảnh báo và điều tra

Theo dõi theo policy dimension và operation:

- Request allowed/denied theo route group và limit policy.
- Tỷ lệ 429 theo client, tenant và endpoint category.
- IP bucket hit tăng đột biến.
- Một subject/account bị thử từ nhiều IP.
- Một IP tạo nhiều account hoặc client identity.
- Tenant vượt quota/concurrency.
- Limiter latency, timeout, Redis error và fallback mode.
- Số key/bucket, memory và eviction.
- Job pending/running, retry và provider usage.

Không log token, password, raw account identifier hoặc payload để điều tra rate limit. Có thể dùng opaque ID/HMAC, request ID, route ID và reason code. Metric label phải có cardinality giới hạn; không đưa IP/user/tenant tùy ý thành label nếu số lượng lớn.

Alert nên phân biệt:

- Traffic burst nhưng chưa ảnh hưởng service.
- Nhiều account bị thử từ nhiều nguồn.
- Một tenant chiếm capacity bất thường.
- Limiter dependency đang fail-open.
- 429 tăng do ngưỡng cấu hình sai sau deploy.
- Bucket/key cardinality tăng bất thường.

Không coi mọi spike 429 là tấn công. Có thể là client retry loop, SDK lỗi hoặc limit cấu hình thấp hơn traffic hợp lệ. Kết hợp deployment, client version, request pattern và owner để phân tích.

## 27. Kiểm thử rate limit nhiều chiều

Test phải chứng minh limiter không chỉ hoạt động với một IP:

| Test | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Shared NAT | Nhiều principal hợp lệ cùng IP | Per-subject limit độc lập; IP cap không chặn quá sớm traffic hợp lệ |
| IP rotation | Một principal gọi từ nhiều IP | Subject/client limit vẫn áp dụng |
| Distributed source | Cùng một account bị gọi từ nhiều IP | Account/risk policy phát hiện tổng attempt |
| IPv6 rotation | Thay địa chỉ trong cùng prefix | Prefix policy hoạt động theo cấu hình |
| Proxy spoofing | Gửi X-Forwarded-For giả | Header bị strip/ignore nếu không đến từ trusted proxy |
| Direct upstream | Bỏ qua gateway | Network hoặc application limiter vẫn bảo vệ |
| Multi-pod | Gửi traffic qua nhiều replica | Tổng limit không bị nhân theo số pod |
| Concurrency | Gửi nhiều job cùng lúc | Không vượt concurrency cap |
| Multi-tenant | Nhiều tenant chung egress | Quota tenant tách biệt và global cap vẫn có hiệu lực |
| Account enumeration | Login/reset với account tồn tại và không tồn tại | Response không tiết lộ account state |
| Lockout DoS | Attacker cố ý nhập sai password cho nạn nhân | Không khóa account vô thời hạn |
| Weighted cost | Gọi operation đắt với payload nhỏ | Cost/concurrency limit vẫn chặn |
| Race condition | Nhiều request đồng thời ở gần ngưỡng | Atomic decision không vượt limit ngoài tolerance |
| Retry | Retry POST sau 429/timeout | Idempotency ngăn side effect trùng |
| Limiter outage | Redis timeout/partition | Fallback theo policy, có alert |
| Recovery | Limiter trở lại sau outage | Không tạo burst không kiểm soát hoặc giữ deny state sai |
| Key cardinality | Gửi nhiều identifier tùy ý | Store có TTL/limit và không tăng vô hạn |
| Credential revoke | Revoke API key/client | Identity bucket không tiếp tục tin credential cũ |

### 27.1 Test hiệu quả của dimension

Với mỗi endpoint, tạo ít nhất hai principal khác nhau từ cùng IP và một principal từ nhiều IP. So sánh kết quả để chứng minh bucket đúng chiều:

- Cùng IP, khác subject: subject bucket độc lập.
- Khác IP, cùng subject: subject limit vẫn dùng chung.
- Cùng tenant, nhiều subject: tenant quota vẫn cộng dồn.
- Khác tenant, cùng IP: tenant quota tách biệt, IP cap vẫn bảo vệ edge.

### 27.2 Test dưới tải và nhiều replica

Chạy concurrency test qua nhiều pod/instance, bao gồm request đồng thời ngay sát ngưỡng. Kiểm tra limiter atomicity, clock skew, failover và key expiration. Không chỉ test tuần tự trên một JVM rồi kết luận distributed limit đúng.

## 28. Các lỗi thiết kế thường gặp

1. **Một IP = một user:** gây false positive sau NAT/proxy.
2. **Chỉ có IP bucket:** attacker phân tán request qua nhiều IP để né limit.
3. **Tin X-Forwarded-For đầu tiên:** client có thể giả mạo IP key.
4. **Dùng User-Agent/device ID làm identity:** attacker đổi giá trị dễ dàng.
5. **Dùng tenant ID từ body:** attacker chọn bucket của tenant khác hoặc tạo bucket vô hạn.
6. **Dùng mỗi account bucket:** attacker dùng nhiều account hoặc nhiều nguồn để gây abuse.
7. **Dùng mỗi client ID:** một partner có thể tạo noisy neighbor giữa nhiều tenant.
8. **Local counter trong mỗi pod:** scale-out làm limit bị nhân lên.
9. **Fixed window không xem burst:** request dồn ở biên cửa sổ.
10. **Một request bằng một cost unit:** endpoint đắt không được bảo vệ đúng.
11. **Không có concurrency limit:** ít request dài vẫn làm cạn worker.
12. **Khóa account vô hạn:** tạo account lockout DoS.
13. **Trả 429 cho mọi auth failure:** sai semantics và che giấu lỗi credential.
14. **Không có fallback policy:** limiter outage làm mở flood hoặc gây outage.
15. **Key store không TTL/cardinality cap:** attacker gây memory exhaustion.
16. **Log raw token/IP/account:** limiter telemetry trở thành nơi rò rỉ dữ liệu.
17. **Không test direct upstream:** gateway limit bị bypass.
18. **Retry không idempotent:** request bị thử lại tạo side effect trùng.

## 29. Quy trình thay thế IP-only limiter

Khi phát hiện API đang rate limit chỉ theo IP:

1. Xác định endpoint, operation, tài nguyên và abuse scenario cần ngăn chặn.
2. Xác minh cách lấy source IP qua proxy chain; loại bỏ header client tự khai báo.
3. Đo traffic baseline, NAT sharing, IPv4/IPv6 behavior và số replica.
4. Xác định authentication state và principal/client/tenant context đáng tin.
5. Chọn dimension phù hợp: IP, subject, client, tenant, route, resource, global và cost.
6. Tách pre-auth attempt limit khỏi post-auth business limit.
7. Đặt quota và concurrency riêng cho operation đắt hoặc async job.
8. Chọn thuật toán và shared state có atomicity phù hợp.
9. Định nghĩa 429, Retry-After, idempotency và client backoff.
10. Chọn fail-open/fail-closed theo criticality và thêm emergency fallback.
11. Giới hạn key cardinality, TTL và dữ liệu nhận dạng lưu trong limiter.
12. Rollout quan sát/shadow trước khi enforce nếu có thể.
13. Test NAT, IP rotation, spoofed proxy headers, multi-pod, tenant fairness và outage.
14. Theo dõi 429, false positive, abuse và capacity sau deploy.
15. Review ngưỡng cùng owner API/client và điều chỉnh theo dữ liệu.

## 30. Checklist rà soát

- [ ] IP được xem là network signal, không phải user/client/tenant identity.
- [ ] Có trusted proxy configuration và cách parse Forwarded/X-Forwarded-For rõ ràng.
- [ ] Edge strip hoặc ghi đè forwarding header do client gửi.
- [ ] Có xử lý NAT/shared egress để tránh chặn nhiều user hợp lệ.
- [ ] Có xử lý IPv4/IPv6 normalization và prefix policy.
- [ ] Có per-subject hoặc per-account limit sau authentication.
- [ ] Có per-client/partner limit với client identity đã xác minh.
- [ ] Có per-tenant limit từ tenant context server-side đã xác minh.
- [ ] Có route/operation-specific limit và global service cap.
- [ ] Endpoint đắt có cost/weighted limit, page cap hoặc concurrency control.
- [ ] Login/reset có multi-dimensional throttling và chống account lockout DoS.
- [ ] Distributed limiter atomic giữa nhiều replica.
- [ ] Bucket có TTL, key length/cardinality cap và privacy protection.
- [ ] 429/Retry-After và client backoff được tài liệu hóa.
- [ ] Rate limit được phân biệt với 401/403, quota và concurrency.
- [ ] Có fail-open/closed policy và emergency fallback theo endpoint.
- [ ] Có metric/alert không làm lộ identifier hoặc tạo cardinality bùng nổ.
- [ ] Test shared NAT, IP rotation, account từ nhiều IP và spoofed proxy header.
- [ ] Test direct upstream, multi-pod, race, outage, retry và recovery.
- [ ] Có owner, runbook và review ngưỡng định kỳ.

IP-only rate limiting là một lớp bảo vệ mạng hữu ích nhưng không đủ để kiểm soát việc sử dụng API. Thiết kế an toàn cần kết hợp nguồn mạng đã xác minh với principal, client, tenant, operation, cost và concurrency; mỗi dimension phải lấy từ context đáng tin cậy và được kiểm thử độc lập. Cách tiếp cận nhiều lớp giảm chặn nhầm người dùng sau NAT, hạn chế attacker phân tán request và bảo vệ đúng tài nguyên mà API thực sự tiêu thụ.
