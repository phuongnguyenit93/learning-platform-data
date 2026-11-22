# Không block cả người dùng hợp lệ qua NAT

Một địa chỉ IP không tương đương với một người dùng. Trong mạng gia đình, văn phòng, trường học, mạng di động và nhiều VPN, hàng chục hoặc hàng nghìn người có thể cùng đi ra Internet qua một IP công cộng. Carrier-Grade NAT (CGNAT) của nhà mạng còn có thể gom lưu lượng của nhiều thuê bao vào một số lượng IP công cộng nhỏ. Nếu API áp một ngưỡng request thấp cho mỗi IP rồi khóa toàn bộ IP khi vượt ngưỡng, hành vi của một người có thể làm gián đoạn dịch vụ cho rất nhiều người vô can.

Đây là một vấn đề quan trọng trong API abuse prevention: hệ thống cần phát hiện và hạn chế hành vi lạm dụng nhưng vẫn giữ quyền truy cập cho người dùng hợp lệ cùng chia sẻ một địa chỉ mạng. IP là một tín hiệu hữu ích về nguồn kết nối, nhưng không đủ để đại diện cho danh tính, quyền hoặc mức độ đáng tin của từng caller.

Trong phạm vi `SECURITY_API_SECURITY`, quyết định chống abuse cần kết hợp danh tính đã xác thực, API key/client, tenant, session, endpoint, hành vi, chi phí request và tín hiệu mạng. Phản ứng nên nhắm vào actor hoặc action có rủi ro khi có đủ bằng chứng; giới hạn theo IP chủ yếu hỗ trợ bảo vệ biên và phát hiện lưu lượng bất thường trên diện rộng.

## 1. Vì sao nhiều người dùng có chung một IP?

### 1.1. NAT trong mạng gia đình và doanh nghiệp

Network Address Translation (NAT) cho phép nhiều thiết bị dùng địa chỉ IP private ở mạng nội bộ và chia sẻ một hoặc một số IP public khi truy cập Internet. Router văn phòng, trường học, khách sạn hoặc quán cà phê thường hoạt động theo cách này.

Ví dụ, một văn phòng có 300 nhân viên có thể chỉ có hai IP public. Nếu mỗi IP được giới hạn 100 request/phút, giờ cao điểm có thể khiến toàn văn phòng bị giới hạn dù từng nhân viên đều sử dụng API bình thường.

### 1.2. Carrier-Grade NAT (CGNAT)

Nhà mạng di động hoặc ISP có thể dùng CGNAT để chia sẻ một IPv4 public cho nhiều thuê bao. Người dùng không kiểm soát được việc mình được ghép chung với ai. Một thuê bao có hành vi abuse có thể làm tăng lưu lượng trên IP chung và ảnh hưởng đến người khác nếu API áp block IP cứng.

### 1.3. VPN, proxy và mạng tập trung

VPN doanh nghiệp, secure web gateway, proxy trường học và dịch vụ VPN thương mại có thể gom nhiều người dùng qua một vài egress IP. IP đó phản ánh điểm ra mạng của tổ chức hoặc nhà cung cấp, không phản ánh từng thiết bị hoặc user.

### 1.4. IPv6 cũng có cấu trúc chia sẻ

IPv6 làm giảm nhu cầu NAT trong nhiều mạng, nhưng không loại bỏ mọi hình thức chia sẻ địa chỉ hoặc proxy. Một thiết bị có thể dùng nhiều địa chỉ tạm thời; một mạng có prefix chung; proxy hoặc gateway vẫn có thể gom nhiều client. Rate limit theo địa chỉ IPv6 đơn lẻ có thể bị né bằng cách đổi địa chỉ trong cùng prefix, trong khi block prefix quá rộng có thể ảnh hưởng nhiều người.

Vì vậy, không nên giả định một IP = một user, cũng không nên giả định một prefix = một tổ chức hoặc một actor.

## 2. Rủi ro khi dùng IP làm khóa định danh duy nhất

Một thiết kế đơn giản thường tạo bucket theo IP:

```text
rate_limit_key = client_ip
if requests_from_ip > threshold:
    block(client_ip)
```

Cách làm này dễ gây false positive:

- Một user gửi nhiều request có thể đẩy cả nhóm người dùng chung IP vượt ngưỡng.
- Một người dùng độc hại có thể làm cạn quota chung của văn phòng hoặc mạng di động.
- Nhiều request hợp lệ đồng thời trong giờ cao điểm bị xem như một cuộc tấn công.
- Một IP VPN hoặc proxy có reputation xấu có thể khiến người dùng mới bị từ chối dù tài khoản và hành vi của họ bình thường.
- Khi IP bị đổi hoặc attacker dùng botnet, block IP vẫn có thể không chặn được actor thực sự.

Hệ quả là vừa ảnh hưởng availability vừa tạo cơ hội DoS gián tiếp: attacker chỉ cần dùng chung mạng với nạn nhân rồi tạo đủ request để kích hoạt block. Đây là dạng collateral damage do chính cơ chế chống abuse gây ra.

IP vẫn có ích để giới hạn lưu lượng thô trước authentication, nhận diện burst, phát hiện nhiều tài khoản từ cùng một nguồn và bảo vệ hạ tầng. Nhưng hành động khóa một IP cần có ngưỡng, thời hạn, phạm vi endpoint và mức độ bằng chứng phù hợp.

## 3. Xác định actor theo nhiều chiều

Thay vì dùng IP làm định danh duy nhất, hãy tạo các khóa giới hạn theo nhiều chiều có độ tin cậy khác nhau.

| Tín hiệu | Đại diện cho | Cách sử dụng phù hợp |
|---|---|---|
| User ID đã xác thực | Tài khoản người dùng | Quota và rate limit chính theo user |
| API key/client ID | Integration hoặc workload | Giới hạn riêng cho ứng dụng gọi API |
| Tenant/account ID | Khách hàng hoặc tổ chức | Quota tổng để chống chia nhỏ key/user nhằm né hạn mức |
| Session ID | Phiên đăng nhập cụ thể | Hạn chế burst và hành vi trong một phiên |
| Device/app instance ID | Cài đặt ứng dụng hoặc thiết bị theo cơ chế đã đăng ký | Tín hiệu bổ sung, không phải bằng chứng danh tính tuyệt đối |
| IP address | Điểm ra mạng quan sát được | Giới hạn thô, tín hiệu rủi ro và phát hiện burst |
| IP prefix/ASN | Nhóm địa chỉ hoặc mạng nhà cung cấp | Phân tích lưu lượng ở mức tổng hợp, cần thận trọng khi block |
| Endpoint/action | Chức năng đang bị gọi | Ngưỡng riêng theo chi phí và rủi ro |
| Destination/resource | Email, số điện thoại hoặc object đích | Chống spam và lạm dụng một mục tiêu cụ thể |

Một request đã xác thực có thể được giới hạn bằng tổ hợp:

```text
user:U123 + endpoint:search
tenant:T15 + endpoint:export
api_key:K88 + endpoint:orders-write
session:S456 + action:send-otp
ip:203.0.113.10 + endpoint:login
```

Các bucket này giải quyết những mục tiêu khác nhau. User bucket bảo vệ một tài khoản; tenant bucket bảo vệ tổng quota của khách hàng; IP bucket phát hiện burst tại nguồn mạng. Không nên gộp tất cả thành một điểm duy nhất rồi block toàn bộ các chiều khi một bucket chạm ngưỡng.

### 3.1. Ưu tiên principal đã xác thực

Sau khi xác thực, user ID, client ID hoặc API key ID thường là khóa phù hợp hơn cho quota nghiệp vụ. Một user dùng chung IP với 200 người khác vẫn có quota riêng. Nếu user đó lạm dụng endpoint export, hệ thống có thể giới hạn export của user đó mà không khóa truy cập đọc thông thường của cả văn phòng.

Với anonymous endpoint như login, signup hoặc password reset, chưa có principal tin cậy. Có thể kết hợp IP, destination, session/cookie tạm thời, challenge và tín hiệu hành vi. Khi user đăng nhập thành công, chuyển sang các bucket theo account/session/client phù hợp.

### 3.2. Tenant quota chống chia nhỏ danh tính

Nếu quota chỉ gắn với user hoặc API key, một tổ chức có thể tạo nhiều tài khoản/key để né hạn mức. Với tài nguyên được tính theo khách hàng, cần có quota tổng ở cấp tenant hoặc account. Tenant ID phải lấy từ security context hoặc mapping server-side đã xác minh, không lấy từ header/body tự khai báo.

### 3.3. Device ID là tín hiệu phụ

Một app có thể có installation ID hoặc device registration ID, nhưng giá trị này có thể bị reset, sao chép hoặc giả mạo. Device ID không thay thế authentication và không nên là lý do duy nhất để block. Tránh fingerprinting quá mức hoặc thu thập thuộc tính thiết bị không cần thiết; dữ liệu nhận diện thiết bị cần có mục đích, thời hạn lưu và quyền truy cập rõ ràng.

## 4. Thiết kế rate limit phân tầng để giảm collateral damage

Rate limit tốt thường có nhiều tầng:

1. **Global/edge limit:** bảo vệ gateway, TLS termination và hạ tầng trước volumetric traffic.
2. **IP/network limit:** phát hiện burst hoặc hành vi tự động bất thường từ một nguồn; ngưỡng phải tính đến mạng chia sẻ.
3. **Principal limit:** áp quota theo user, API key, client hoặc session.
4. **Tenant limit:** kiểm soát tổng tài nguyên của tổ chức.
5. **Endpoint/action limit:** áp mức giới hạn theo chi phí và mức độ nhạy cảm.
6. **Resource/destination limit:** giới hạn hành động lặp lên cùng email, số điện thoại, object hoặc tài nguyên.

Ví dụ, endpoint gửi OTP có thể có cooldown theo số điện thoại, giới hạn theo account, giới hạn burst theo IP và quota tổng theo tenant. Nếu một IP chung gửi nhiều OTP do hàng trăm nhân viên đăng nhập hợp lệ, destination/account bucket giúp phân biệt từng yêu cầu; IP bucket có thể cảnh báo hoặc áp challenge có chọn lọc thay vì khóa mọi người.

### 4.1. IP limit nên rộng hơn principal limit

Với mạng có khả năng chia sẻ, ngưỡng IP thường cần cao hơn ngưỡng user/session. Có thể dùng token bucket cho IP để cho phép burst ngắn trong giờ cao điểm, nhưng vẫn giới hạn tốc độ trung bình dài hạn. Ngưỡng cụ thể cần dựa trên traffic thực tế và load test, không dùng một con số mặc định cho mọi endpoint.

IP limit có thể áp dụng khác nhau theo endpoint: login và endpoint cấp token cần bảo vệ trước authentication; endpoint export có thể ưu tiên quota theo account/tenant vì chi phí gắn với người gọi đã xác thực.

### 4.2. Không để một user chiếm hết quota chung của IP

Nếu chỉ có bucket IP, một client gây burst có thể tiêu hết quota chung. Có thể dùng kết hợp:

- Per-user/session bucket để giới hạn actor đã xác thực.
- IP aggregate bucket có capacity đủ lớn để hấp thụ traffic hợp lệ của mạng chia sẻ.
- Per-IP concurrency cap để hạn chế số kết nối đồng thời bất thường, có ngưỡng phù hợp cho proxy/NAT lớn.
- Fair scheduling hoặc quota reservation để một principal không chiếm hết worker/connection pool.
- Risk-based throttling tập trung vào principal có hành vi bất thường.

Không thể đảm bảo công bằng tuyệt đối chỉ bằng một IP counter. Với hệ thống có lưu lượng lớn, cần kiểm soát cả concurrency và admission ở cấp principal/tenant.

## 5. Phân biệt volumetric abuse và abuse ở cấp tài khoản

Hai tình huống cần cách phản ứng khác nhau.

| Tình huống | Dấu hiệu | Phản ứng phù hợp |
|---|---|---|
| Volumetric traffic từ một nguồn | Lưu lượng tổng tăng mạnh, nhiều request không có principal hoặc nhiều kết nối bất thường | Edge throttling, connection cap, challenge hoặc chặn tạm thời nguồn có bằng chứng rõ |
| Một user lạm dụng API | Một account gọi export/search/OTP vượt mức | Throttle hoặc tạm hạn chế action của user đó |
| Một API key tạo tải bất thường | Một integration có request rate/cost tăng đột biến | Giới hạn key/client, thông báo owner, có thể revoke nếu compromise |
| Nhiều user hợp lệ cùng IP | Nhiều principal độc lập, hành vi đa dạng, traffic tăng theo giờ làm việc | Giữ quyền truy cập; tăng ngưỡng IP, dùng quota theo principal và giám sát |
| Nhiều tài khoản giả từ một mạng | Tài khoản mới, pattern request giống nhau, destination lặp hoặc hành vi automation | Risk scoring, challenge theo account/session, giới hạn signup/destination |
| Một actor phân tán qua nhiều IP | Cùng account/key/session hoặc pattern nghiệp vụ xuất hiện ở nhiều nguồn | Giới hạn theo principal/resource, không phụ thuộc IP |

IP aggregate traffic cao tự nó không chứng minh tất cả người dùng trên IP đều độc hại. Hãy xem số lượng principal khác nhau, lịch sử hoạt động, endpoint, destination, tần suất, chi phí và kết quả xác thực trước khi chọn hành động.

## 6. Risk scoring và phản ứng tăng dần

Thay vì chuyển trực tiếp từ “bình thường” sang “block IP”, có thể xây dựng risk score dựa trên nhiều tín hiệu. Ví dụ:

- Tốc độ request tăng bất thường so với baseline của principal.
- Nhiều lần thử credential sai trên cùng account hoặc session.
- Nhiều account mới được tạo từ một nguồn trong thời gian ngắn.
- Một destination nhận quá nhiều OTP/email.
- Một client lặp cùng request hoặc tạo nhiều object không sử dụng.
- Request có cost cao, payload bất thường hoặc pattern tự động hóa.
- IP thuộc hosting/proxy network có reputation rủi ro, nhưng chỉ là tín hiệu phụ.
- Nhiều principal độc lập cùng IP có lịch sử sử dụng lâu dài và hành vi bình thường, đây có thể là tín hiệu mạng chia sẻ.

Risk score nên gắn với principal hoặc action khi có thể. Nếu chỉ có IP, mức tin cậy thấp hơn và phản ứng nên nhẹ hơn trừ khi có bằng chứng volumetric attack rõ.

### 6.1. Các mức phản ứng

| Mức | Phản ứng | Khi phù hợp |
|---|---|---|
| 0 – Normal | Cho phép, ghi metric | Hành vi trong baseline |
| 1 – Observe | Tăng logging/telemetry, không thay đổi quyền | Tín hiệu bất thường nhẹ hoặc chưa đủ bằng chứng |
| 2 – Soft throttle | Giảm tốc hoặc giới hạn riêng endpoint/action | Principal có burst vượt baseline |
| 3 – Challenge | Yêu cầu xác minh bổ sung, step-up hoặc proof-of-work phù hợp | Rủi ro trung bình, cần phân biệt automation với người thật |
| 4 – Temporary restriction | Tạm hạn chế principal, API key hoặc destination | Có bằng chứng rõ về abuse và phạm vi ảnh hưởng xác định |
| 5 – Network-level block | Chặn IP/prefix có thời hạn và phạm vi hẹp | Volumetric attack rõ, nguồn không có lưu lượng hợp lệ đáng kể hoặc cần biện pháp khẩn cấp |

Đây là mô hình tham khảo. Không phải mọi request cần đi qua challenge. CAPTCHA hoặc challenge khác có thể gây khó khăn về accessibility, mobile client và automation hợp lệ; chỉ dùng khi tín hiệu rủi ro đủ cao và cung cấp cách xử lý phù hợp cho người dùng không thể hoàn thành challenge.

### 6.2. Giới hạn theo endpoint thay vì khóa toàn bộ tài khoản

Nếu user lạm dụng endpoint gửi OTP, có thể cooldown riêng action gửi OTP trong khi vẫn cho phép đọc profile hoặc kiểm tra trạng thái đơn hàng. Nếu một API key bị nghi compromise, giới hạn hoặc thu hồi key đó thay vì block IP chung của integration provider. Phạm vi phản ứng càng gần actor/action gây ra rủi ro thì collateral damage càng thấp.

### 6.3. Thời hạn và tự động gỡ hạn chế

Temporary restriction phải có TTL, điều kiện gia hạn và cơ chế tự gỡ khi hết thời hạn nếu không có bằng chứng mới. Tránh block vô thời hạn chỉ dựa trên một lần vượt ngưỡng. Với block network-level, lưu lý do, người/phần mềm tạo quyết định, thời gian hết hạn và phạm vi endpoint bị ảnh hưởng.

## 7. Ví dụ thiết kế nhiều bucket

Giả sử API có ba endpoint:

- `GET /api/orders`: đọc danh sách đơn hàng, chi phí thấp.
- `POST /api/reports/export`: tạo báo cáo, chi phí cao.
- `POST /api/otp/send`: gửi OTP, có chi phí và rủi ro spam.

Một chính sách minh họa:

| Endpoint | IP bucket | Principal bucket | Tenant/destination bucket | Phản ứng khi vượt |
|---|---|---|---|---|
| Orders read | Ngưỡng rộng, chống burst | Per-user rate | Tenant quota tổng | `429` cho principal hoặc tenant vượt mức |
| Export | Chỉ giới hạn thô | Per-user concurrency và quota | Per-tenant job quota | Từ chối tạo job mới, không block IP chung |
| OTP send | IP burst signal | Per-user/session cooldown | Per-destination và tenant cost quota | Cooldown destination/account, challenge theo rủi ro |

Các giá trị số cụ thể cần được xác định từ load test và hợp đồng dịch vụ. Mục tiêu của bảng là chỉ ra mỗi endpoint cần khóa giới hạn riêng; không có một IP threshold áp dụng giống nhau cho mọi loại request.

Pseudo-code minh họa:

```java
Decision evaluate(RequestContext ctx) {
    // Edge bucket protects the service from raw bursts.
    if (!globalLimiter.allow(ctx.route(), ctx.cost())) {
        return Decision.serviceBusy();
    }

    // IP is an aggregate signal, especially for shared networks.
    IpSignal ipSignal = ipLimiter.observe(
        ctx.trustedClientIp(), ctx.route(), ctx.cost());

    if (ctx.isAuthenticated()) {
        if (!principalLimiter.allow(
                ctx.principalId(), ctx.route(), ctx.cost())) {
            return Decision.throttlePrincipal();
        }

        if (!tenantLimiter.allow(
                ctx.tenantId(), ctx.route(), ctx.cost())) {
            return Decision.tenantQuotaExceeded();
        }
    }

    if (ipSignal.isHighRisk() && ctx.isAnonymous()) {
        return Decision.requireChallenge();
    }

    return Decision.allow();
}
```

Đây chỉ là phác thảo. Trong triển khai thực tế, các limiter phải cập nhật state atomic, xử lý concurrency, phân biệt `429` do principal với `503` do hệ thống và không gọi `trustedClientIp()` từ header chưa được xác minh. `observe()` không được âm thầm block mọi caller trên IP chỉ vì aggregate traffic cao.

## 8. Xử lý proxy và xác định client IP đáng tin

IP quan sát được có thể là IP của CDN, load balancer hoặc reverse proxy. Nếu ứng dụng lấy IP sai, rate limit và risk score đều có thể bị thao túng.

Các nguyên tắc:

- Chỉ tin forwarding header từ proxy nằm trong trust configuration.
- Proxy biên phải xóa header `Forwarded`/`X-Forwarded-For` do client gửi và ghi lại giá trị do nó quan sát.
- Xác định rõ thứ tự hop và proxy nào có quyền thêm giá trị.
- Không lấy IP đầu tiên trong chuỗi header một cách mù quáng.
- Nếu không thể xác minh chuỗi proxy, dùng địa chỉ peer kết nối trực tiếp hoặc đánh dấu IP là không chắc chắn.
- Giữ riêng `peer_ip` và `client_ip_observed` nếu cần điều tra đường đi qua proxy.

Ví dụ, nếu request đến từ CDN, địa chỉ socket của application có thể luôn là IP CDN. Chỉ dùng header client IP khi kết nối đến từ CDN đã xác thực và header được CDN ghi đè theo hợp đồng. Không để client truy cập thẳng origin rồi tự khai `X-Forwarded-For`.

## 9. IPv4, IPv6 và prefix-based controls

Block một IPv4 có thể ảnh hưởng toàn bộ mạng NAT/CGNAT. Block một IPv6 prefix rộng có thể ảnh hưởng nhiều thiết bị hoặc cả tổ chức. Ngược lại, chỉ giới hạn IPv6 theo địa chỉ đơn lẻ có thể bị né bằng privacy address rotation.

Khi cần phân tích theo prefix:

- Chọn độ dài prefix dựa trên kiến trúc mạng và dữ liệu traffic; không mặc định một prefix đại diện cho một user.
- Tách prefix telemetry khỏi quyết định block.
- Đặt TTL ngắn và phạm vi endpoint cụ thể cho network-level restriction.
- Theo dõi số lượng principal hợp lệ và lịch sử traffic trong prefix trước khi áp dụng block rộng.
- Cho phép ngoại lệ có kiểm soát cho egress IP của đối tác/doanh nghiệp khi có bằng chứng sở hữu, nhưng vẫn giữ quota theo principal/tenant.

Không nên dùng ASN hoặc geolocation như bằng chứng duy nhất để chặn. Nhiều mạng di động, cloud egress hoặc VPN hợp lệ có thể dùng chung ASN/địa lý với traffic rủi ro.

## 10. Challenge mà không làm khó người dùng hợp lệ

Challenge là một công cụ để tăng độ tin cậy khi rủi ro cao, nhưng triển khai không hợp lý có thể gây hại cho người dùng hợp lệ:

- CAPTCHA liên tục làm giảm accessibility và trải nghiệm mobile.
- Challenge mỗi request trên IP dùng chung có thể buộc toàn văn phòng xác minh lặp lại.
- OTP challenge có thể phát sinh chi phí và bị lạm dụng chính endpoint gửi OTP.
- Challenge quá khó có thể khóa nhầm người dùng dùng assistive technology hoặc kết nối mạng yếu.

Hãy áp dụng challenge ở mức session/account hoặc action nghi vấn khi có thể. Cho phép session đã xác minh duy trì trạng thái trong thời gian hợp lý; tăng mức xác minh khi xuất hiện hành vi mới hoặc thao tác nhạy cảm. Có phương án hỗ trợ người dùng không thể hoàn thành challenge và không tiết lộ quá nhiều về ngưỡng chống abuse.

## 11. Quan sát, giải thích và xử lý false positive

Một hệ thống chống abuse cần ghi nhận lý do quyết định để đội vận hành biết vì sao request bị throttle hoặc block. Các metric nên phân biệt:

- `rate_limited_by_ip` – bị giới hạn bởi bucket IP.
- `rate_limited_by_user` – bị giới hạn theo user.
- `rate_limited_by_api_key` – bị giới hạn theo integration.
- `quota_exceeded_by_tenant` – vượt quota khách hàng.
- `destination_cooldown` – destination đang trong cooldown.
- `challenge_required` – cần xác minh bổ sung.
- `network_block_applied` – có network-level restriction.

Theo dõi thêm:

- Số principal khác nhau trên một IP/prefix.
- Tỷ lệ user đã xác thực so với anonymous request.
- Traffic theo endpoint/action và cost estimate.
- Tỷ lệ request bị từ chối nhưng sau đó được support xác nhận là hợp lệ.
- Tỷ lệ challenge thành công/thất bại và abandon rate.
- Thời gian block, số lần gia hạn và số người dùng bị ảnh hưởng ước tính.
- Số khiếu nại hoặc ticket liên quan đến IP shared/VPN/CGNAT.

Không đưa raw IP, device fingerprint hoặc user identifier vào metric label có cardinality cao nếu hệ thống metrics không được thiết kế cho dữ liệu đó. Dùng log/audit có kiểm soát hoặc identifier đã pseudonymize cho điều tra; áp dụng retention và quyền truy cập phù hợp.

### 11.1. Quy trình xử lý false positive

Khi người dùng báo bị chặn:

1. Tra cứu quyết định bằng request/correlation ID và thời điểm, không yêu cầu họ gửi token hoặc secret.
2. Xác định bucket nào kích hoạt: IP, principal, tenant, destination hay endpoint.
3. Kiểm tra IP có thuộc NAT, CGNAT, VPN hoặc proxy dùng chung không.
4. Đếm số principal hợp lệ và phân bố hành vi trên IP đó.
5. Nếu block IP quá rộng, gỡ hoặc thu hẹp phạm vi/TTL; giữ giới hạn theo actor gây abuse.
6. Ghi nhận nguyên nhân và điều chỉnh threshold/model để giảm lặp lại.

Quy trình cần có người chịu trách nhiệm, SLA xử lý và audit thay đổi allowlist/blocklist. Không nên tạo ngoại lệ IP vĩnh viễn cho từng người dùng vì điều đó có thể trở thành đường bypass.

## 12. Kiểm thử tình huống NAT và shared IP

Kiểm thử chống abuse phải mô phỏng nhiều người dùng hợp lệ cùng IP, không chỉ chạy load test từ nhiều IP riêng biệt.

| Kịch bản | Kết quả mong đợi |
|---|---|
| 100 user hợp lệ cùng IP đọc API trong giờ cao điểm | Không block toàn IP chỉ vì tổng traffic cao; quota user/tenant được áp dụng |
| Một user trong nhóm gửi burst bất thường | Chỉ user/session/action đó bị throttle nếu có thể xác định |
| Một API key lạm dụng từ IP văn phòng | Giới hạn key/client; người dùng khác vẫn truy cập bình thường |
| Nhiều thuê bao CGNAT cùng gọi login | IP signal không tự động khóa toàn bộ thuê bao |
| Attacker tạo nhiều account từ cùng IP | Account/destination/signup risk controls phát hiện pattern; không chỉ dựa IP |
| Một account phân tán request qua nhiều IP | Principal bucket vẫn phát hiện và giới hạn |
| Client giả `X-Forwarded-For` | Không thay đổi IP được tin cậy hoặc bucket limit |
| IP VPN có reputation xấu nhưng user lâu năm hợp lệ | Không block chỉ dựa reputation; áp dụng risk response phù hợp |
| IPv6 privacy address thay đổi | Principal/account controls vẫn có hiệu lực |
| Block IP được áp dụng khẩn cấp | Có TTL, endpoint scope, reason và cơ chế review |
| Limiter store lỗi | Fallback theo policy, không vô tình mở quota vô hạn |
| User bị giới hạn nhầm | Có request ID, reason code và quy trình gỡ hạn chế |

### 12.1. Mô phỏng shared NAT

Trong integration/load test, tạo nhiều principal khác nhau nhưng cấu hình cùng `client_ip`. Cho một principal gửi burst vượt ngưỡng cá nhân, đồng thời các principal khác gửi lưu lượng bình thường. Xác minh:

1. Bucket của actor gây burst bị kích hoạt.
2. Principal khác trên cùng IP vẫn được phục vụ trong quota của họ.
3. IP aggregate metric tăng nhưng không tự động gây block toàn IP.
4. Tenant quota vẫn ngăn một tổ chức vượt tổng ngân sách.
5. Nếu global capacity bị đe dọa, edge có thể áp dụng throttling rộng theo policy nhưng response và phạm vi phải được giám sát.

Lặp lại với anonymous login/signup, nhiều API key, proxy chain, IPv6 và nhiều tenant để kiểm tra các đường đi khác nhau.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Một IP tương đương một user | NAT/CGNAT làm nhiều người bị block cùng lúc | Phân biệt IP với principal |
| Block IP ngay khi chạm một threshold thấp | Một user có thể gây DoS cho người dùng chung mạng | Dùng IP signal, threshold rộng và phản ứng tăng dần |
| Chỉ giới hạn theo user | Nhiều account giả có thể vượt tổng quota | Bổ sung tenant, destination và network signals |
| Chỉ giới hạn theo IP | Không phát hiện actor phân tán qua nhiều IP | Per-user/key/session controls |
| Block ASN/geolocation theo danh sách cứng | Chặn nhiều mạng hợp lệ | Dùng như tín hiệu risk, không phải bằng chứng duy nhất |
| Challenge mọi người trên IP rủi ro | Người dùng hợp lệ bị xác minh lặp lại | Challenge theo session/principal/action |
| Không có TTL cho block | False positive kéo dài vô hạn | Temporary restriction và review |
| Tin forwarding header từ client | Attacker thay IP bucket | Trust proxy configuration |
| Không theo dõi principal diversity | Không nhận ra IP dùng chung | Metrics số principal và lịch sử hoạt động |
| Ngoại lệ allowlist vĩnh viễn | Tạo đường bypass quota | Ngoại lệ có owner, scope, expiry và audit |

## 14. Checklist review anti-abuse cho mạng NAT

- [ ] IP được xem là tín hiệu mạng, không phải định danh duy nhất của user.
- [ ] Có quota theo user, API key/client, session, tenant, endpoint và destination khi phù hợp.
- [ ] IP bucket được thiết kế để chịu được lưu lượng hợp lệ từ NAT/CGNAT/proxy.
- [ ] Một principal vượt quota không làm cạn toàn bộ quota chung của IP.
- [ ] Có global/edge protection cho volumetric traffic nhưng tách khỏi business quota.
- [ ] Endpoint anonymous và endpoint đã xác thực có chính sách khác nhau.
- [ ] Tenant ID và principal được lấy từ nguồn tin cậy, không từ header/body tùy ý.
- [ ] Forwarding header chỉ được tin từ proxy đã cấu hình và được ghi đè ở edge.
- [ ] Risk scoring dùng nhiều tín hiệu và phân biệt principal với network.
- [ ] Phản ứng tăng dần: observe, soft throttle, challenge, temporary restriction, network block.
- [ ] Network block có lý do, scope, TTL, owner và cơ chế review/gỡ.
- [ ] CAPTCHA/challenge có cân nhắc accessibility và không áp dụng đại trà.
- [ ] IPv4, IPv6, prefix, ASN, VPN và CGNAT được tính đến trong threat model.
- [ ] Dashboard phân biệt limit theo IP, user, API key, tenant và destination.
- [ ] Có quy trình xử lý false positive và test nhiều user hợp lệ cùng IP.
- [ ] Có kiểm thử actor phân tán qua nhiều IP và attacker tạo nhiều account.

Chống abuse hiệu quả không có nghĩa là khóa mọi request đến từ một IP có lưu lượng cao. Khi IP được dùng như tín hiệu tổng hợp, quota nghiệp vụ gắn với principal/tenant/action, và phản ứng nhắm vào phạm vi nhỏ nhất có đủ bằng chứng, hệ thống vừa có thể bảo vệ hạ tầng trước burst vừa tránh biến NAT, CGNAT, VPN hoặc proxy dùng chung thành lý do từ chối hàng loạt người dùng hợp lệ.
