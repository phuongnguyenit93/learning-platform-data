# Bảo vệ availability mà không chặn user hợp lệ

Trong một đợt cao điểm mua sắm, hệ thống nhận lượng truy cập tăng mạnh. Cùng lúc, một cuộc tấn công **Distributed Denial of Service (DDoS)** cũng có thể làm cạn băng thông, kết nối hoặc tài nguyên ứng dụng. Nếu đội vận hành phản ứng bằng cách chặn mọi truy cập vượt một ngưỡng IP cố định, máy chủ có thể giảm tải nhưng nhiều khách hàng thực sự lại không thể đăng nhập, thanh toán hay sử dụng dịch vụ. Khi ấy, mục tiêu **availability (tính sẵn sàng)** chưa chắc đã đạt được từ góc nhìn người dùng.

**Bảo vệ availability mà không chặn user hợp lệ** là bài toán thiết kế phòng vệ DDoS dựa trên hai mục tiêu đồng thời: **giảm tác động của lưu lượng độc hại** và **duy trì khả năng hoàn tất các thao tác quan trọng cho người dùng được phép**. Một giải pháp tốt không chỉ nhìn vào lượng traffic bị drop mà còn theo dõi giao dịch thành công, tỷ lệ chặn nhầm, độ trễ và khả năng phục hồi.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, phòng vệ DDoS phối hợp với phân đoạn mạng, firewall, VPN, IDS/IPS, bảo vệ DNS, Wi-Fi, xác thực kết nối và hạ tầng đám mây. Giải pháp cần kết hợp quan sát lưu lượng, mô hình hóa mối đe dọa, giới hạn tài nguyên, điều phối nhà cung cấp mạng, quản trị rủi ro và kiểm thử có phép.

> **Nguyên tắc cốt lõi:** Không dùng số lượng request bị chặn làm chỉ số thành công duy nhất. Nếu người dùng thật không hoàn tất được tác vụ, hệ thống vẫn đang gặp sự cố availability dù firewall/WAF báo đã giảm traffic.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt availability của **hạ tầng** với availability của **dịch vụ từ góc nhìn người dùng**.
2. Nhận biết đặc điểm của DDoS dạng **volumetric, protocol/state exhaustion và application-layer**.
3. Giải thích vai trò của **Anycast, CDN, scrubbing, rate limiting, WAF, load balancing, caching, autoscaling và origin protection**.
4. Thiết kế giới hạn truy cập có tính tới **NAT/CGNAT, IPv6, API clients, retry và người dùng có nhu cầu trợ năng**.
5. Đánh giá tác dụng phụ của **challenge, CAPTCHA, IP reputation, địa lý và các rule adaptive mitigation**.
6. Xây dựng dashboard theo dõi **legitimate goodput, tỷ lệ lỗi, p95/p99 latency, challenge failure, false block và sức khỏe backend**.
7. Tổ chức một **runbook ứng cứu DDoS** gồm phát hiện, phân loại, giảm thiểu, xác nhận người dùng hợp lệ và rollback.

## 2. Tại sao “drop được nhiều gói” không đồng nghĩa dịch vụ sẵn sàng?

Availability nghĩa là người dùng được phép có thể sử dụng dịch vụ **trong điều kiện chất lượng và thời gian chấp nhận được**. Với một cửa hàng trực tuyến, có thể đo bằng việc mở trang, tìm kiếm sản phẩm, đăng nhập và thanh toán thành công; với API, đó là yêu cầu hợp lệ được xử lý đúng hợp đồng dịch vụ.

Phân biệt:

| Góc nhìn | Ví dụ chỉ số | Giới hạn |
|---|---|---|
| **Network availability** | Gói tới được edge, băng thông còn khả dụng, mất gói và lỗi kết nối | Đường mạng hoạt động không có nghĩa ứng dụng đáp ứng |
| **Infrastructure availability** | CPU/memory, trạng thái load balancer, số backend khỏe, kết nối được mở | Backend vẫn có thể lỗi logic hoặc chậm |
| **Application availability** | HTTP 2xx/3xx phù hợp nghiệp vụ, 5xx, lỗi database, thời gian xử lý | HTTP 200 không đảm bảo giao dịch được hoàn tất đúng |
| **User-perceived availability** | Tỷ lệ đăng nhập, tra cứu, đặt hàng, thanh toán hoặc API call hợp lệ thành công | Cần dữ liệu từ client và xác định hành trình người dùng |
| **Security-control availability** | Khả năng áp rule, độ trễ WAF, tỷ lệ challenge hợp lệ vượt qua | Bảo vệ có thể thành điểm nghẽn hoặc gây chặn nhầm |

Ví dụ đội bảo mật làm giảm 90% lượng yêu cầu đi tới origin nhưng 40% khách hàng hợp lệ bị CAPTCHA chặn hoặc API đối tác nhận HTTP 429 liên tục. Hệ thống được bảo vệ trước tải giả, nhưng **trải nghiệm thật đã suy giảm nghiêm trọng**. Hai kết quả phải được báo cáo cùng nhau.

### Ba khái niệm cần tách

- **Attack traffic:** lưu lượng có mục đích gây gián đoạn hoặc vượt phạm vi sử dụng được phép; xác định qua bằng chứng và ngữ cảnh.
- **Legitimate traffic:** lưu lượng thuộc nhu cầu, quyền và hành vi được chấp nhận; có thể rất lớn trong sự kiện kinh doanh.
- **Unknown traffic:** lưu lượng chưa đủ dữ liệu để khẳng định là hợp lệ hay độc hại. Không nên tự gắn tất cả yêu cầu vượt ngưỡng là tấn công.

Một bot được tổ chức ủy quyền làm kiểm thử hiệu năng hoặc thu thập dữ liệu theo hợp đồng có thể gửi nhiều yêu cầu hợp lệ. Ngược lại, kẻ tấn công có thể dùng những HTTP request nhìn bề ngoài bình thường nhưng tạo tải không hợp lý. Cần xét **ý định, quyền, cơ chế sử dụng và tác động tài nguyên**.

## 3. Mô hình mối đe dọa DDoS

**DDoS** dùng nhiều nguồn hoặc một hạ tầng phân tán để gây suy giảm/từ chối dịch vụ cho một tài nguyên. Mục tiêu có thể là đường truyền, thiết bị mạng, hệ thống kết nối hoặc lớp ứng dụng.

| Nhóm | Tài nguyên thường bị ảnh hưởng | Dấu hiệu phòng thủ cần quan sát | Ví dụ lớp phòng vệ |
|---|---|---|---|
| **Volumetric (L3/L4)** | Băng thông Internet, thiết bị biên và năng lực xử lý gói | bps, pps, traffic theo protocol/đích, saturation upstream | ISP/upstream filtering, Anycast, scrubbing, DDoS edge |
| **Protocol/state exhaustion** | Bảng trạng thái firewall, kết nối, socket, load balancer | SYN/new connection rate, state table, drops, reset, queue length | SYN protection, rate controls, connection limits có kiểm soát, năng lực hạ tầng |
| **Application-layer (L7)** | HTTP worker, API, database, cache, CPU | request rate, latency, URL/method, session, lỗi 5xx, workload | CDN/cache, WAF/bot mitigation, quota theo danh tính, bảo vệ endpoint tốn tài nguyên |
| **Multi-vector** | Nhiều lớp cùng lúc, có thể đổi đặc điểm theo thời gian | Biến động mạng + ứng dụng, thay đổi đích và chiến thuật | Điều phối nhiều lớp và runbook liên chức năng |

Một cuộc tấn công có thể thay đổi dạng, trộn nhiều kỹ thuật hoặc tập trung vào điểm nghẽn nhỏ thay vì tạo lưu lượng tổng thể cực lớn. **Không thể suy quy mô tác động chỉ từ số request/giây (RPS)**; một request tới báo cáo phức tạp có thể tốn tài nguyên hơn nhiều request tới tài nguyên tĩnh được cache.

### Đường truyền trước firewall là một ranh giới quan trọng

Nếu đường Internet tới origin chỉ còn một phần băng thông do lưu lượng lớn, firewall đặt **sau** đường bị nghẽn không thể khôi phục dung lượng đã mất trên đường truyền. Khi ấy cần khả năng lọc/scrubbing ở **upstream** hoặc thông qua hệ thống edge của nhà cung cấp.

~~~text
             Lưu lượng Internet
                     |
            [ISP / DDoS edge]
             |            |
       Traffic xấu      Traffic đã lọc
        bị giảm              |
                             v
                      [Load balancer]
                             |
                       [WAF / App]
                             |
                          [Origin]

 Nếu upstream đã bão hòa trước điểm lọc,
 policy tại origin không cứu được đường truyền đó.
~~~

Lưu ý việc chuyển hướng lưu lượng qua scrubbing hay nhà cung cấp còn phụ thuộc kiến trúc định tuyến, DNS/Anycast, hợp đồng, năng lực nhà cung cấp và thời gian kích hoạt. Không phải mọi tổ chức đều có cùng mô hình bảo vệ.

## 4. DDoS và flash crowd: làm sao tránh chặn nhầm?

**Flash crowd** là tăng trưởng truy cập hợp lệ trong thời gian ngắn, ví dụ mở bán vé, livestream hoặc phát hành sản phẩm. Flash crowd và DDoS có thể cùng gây:

- Tăng kết nối/giây, request/giây và CPU.
- Tăng độ trễ, timeout, lỗi 429/503/504.
- Mất cân bằng tải theo địa lý hoặc CDN PoP.
- Hàng đợi dài ở API, database hoặc dịch vụ đăng nhập.

Không có một chỉ số duy nhất đủ phân biệt hai trường hợp. Nên xem:

| Tín hiệu | Gợi ý điều tra | Vì sao không đủ kết luận? |
|---|---|---|
| Thời điểm so với lịch chiến dịch | Lưu lượng tăng trùng giờ mở bán có thể hợp lệ | Kẻ tấn công cũng có thể chọn thời điểm cao điểm |
| Tỷ lệ hoàn tất giao dịch | Nhiều người truy cập và hoàn tất đúng luồng có thể là nhu cầu thật | Luồng có lỗi do quá tải cũng làm tỷ lệ hoàn tất giảm |
| Endpoint và method | Traffic hợp lệ thường theo hành trình nghiệp vụ đã biết | Bot độc hại có thể mô phỏng luồng phổ biến |
| Danh tính/session | User đăng nhập hoặc API key hợp lệ giúp phân nhóm | Tài khoản cũng có thể bị lạm dụng hoặc bị chiếm |
| Tốc độ theo client | Một số nguồn gửi quá nhiều request | NAT/CGNAT có thể đại diện nhiều user |
| Tài nguyên mỗi request | Một endpoint tạo chi phí backend bất thường | Request nghiệp vụ thật cũng có thể nặng |
| IP/ASN/địa lý | So sánh với phân bố bình thường | Dịch vụ VPN, roaming, CDN và người dùng quốc tế làm phân bố thay đổi |

**Cách tiếp cận:** xây baseline cho từng luồng quan trọng, đối chiếu dữ liệu kinh doanh và dùng nhiều tín hiệu trước khi chuyển sang chính sách chặn rộng.

## 5. Chiến lược bảo vệ nhiều lớp

Một kiến trúc tham chiếu:

~~~text
                  Người dùng / API clients
                            |
                      Public DNS
                            |
                 [CDN / Anycast Edge]
                  |                |
             L3/L4 mitigation   WAF / Bot policy
                  \                /
                   [Traffic steering]
                            |
                    [Load balancer]
                            |
                  [Application gateway]
                     /            \
                 [App A]          [App B]
                     \            /
                       [Database]

             Telemetry bổ trợ:
       Edge metrics, WAF logs, LB health,
       API/gateway, tracing, SLO, user journeys
~~~

### 5.1. Anycast, CDN và edge protection

**Anycast** cho phép nhiều địa điểm cung cấp cùng một điểm đến mạng; định tuyến đưa traffic tới các điểm edge theo quyết định của mạng. Điều này có thể phân tán một phần tải và đặt kiểm soát gần nguồn hơn. **Anycast không đảm bảo mọi cuộc tấn công đều được hấp thụ**: một PoP có thể chịu tải lớn, tuyến có thể thay đổi và năng lực toàn hệ thống vẫn có giới hạn.

**CDN** phục vụ nội dung cacheable từ edge, giảm request tới origin và rút ngắn đường truyền. Với trang động, API có danh tính hoặc giao dịch nhạy cảm, cần chính sách cache riêng để tránh trả sai dữ liệu giữa các user.

**DDoS scrubbing** là quá trình lọc/giảm traffic đáng ngờ tại hạ tầng được thiết kế cho mục đích đó, thường do ISP hoặc nhà cung cấp thực hiện. Mục tiêu là chỉ chuyển traffic phù hợp về hệ thống được bảo vệ. Cần đo cả **lưu lượng đã giảm** và **lưu lượng hợp lệ vẫn tới đích**.

### 5.2. Load balancing, scaling và khả năng chịu lỗi

Load balancer có thể phân phối request tới nhiều backend khỏe; autoscaling có thể thêm năng lực khi có điều kiện. Tuy nhiên:

- **Autoscaling không phải giải pháp DDoS độc lập.** Nếu traffic không kiểm soát tiếp tục tăng, tài nguyên mới cũng có thể bão hòa và chi phí phình to.
- Hệ thống có thể bị giới hạn ở database, cache, queue, authentication service hoặc kết nối upstream, dù số web worker tăng.
- Scaling có độ trễ; nếu health check cấu hình sai, backend có thể bị loại khỏi vòng phục vụ không cần thiết.
- Nếu mọi backend cùng phụ thuộc một tài nguyên trung tâm, tăng số instance không giải quyết điểm nghẽn.

Ưu tiên **giảm chi phí phục vụ mỗi request**, caching hợp lý, giới hạn tài nguyên và **load shedding có chủ đích** trước khi tăng năng lực không giới hạn.

### 5.3. Firewall L3/L4 và WAF L7

| Lớp | Bảo vệ chính | Giới hạn |
|---|---|---|
| **Firewall / network ACL** | Kiểm soát IP, cổng, protocol, trạng thái kết nối và phân đoạn | Không mặc nhiên phân biệt người dùng ứng dụng thật hay giả |
| **IDS/IPS/NDR** | Phát hiện/chặn tại điểm quan sát và cung cấp telemetry | Lưu lượng TLS/QUIC mã hóa làm giảm khả năng thấy payload |
| **WAF / bot management** | Quy tắc HTTP, hành vi client, challenge, quota theo endpoint | Có thể chặn nhầm request hợp lệ; không thay thế tính sẵn sàng upstream |
| **Application/API gateway** | Danh tính, authorization, quota theo khóa/tenant, ưu tiên công việc | Nếu quá tải xảy ra trước gateway, bảo vệ tại đây có thể quá muộn |
| **Platform resilience** | Cache, queue, circuit breaker, timeout, autoscale, redundancy | Không thay thế chính sách giảm traffic độc hại từ bên ngoài |

Kết hợp các lớp thay vì chỉ đặt một quy tắc chặn lưu lượng tổng quát.

## 6. Vì sao rate limit theo IP dễ chặn người dùng thật?

**Rate limiting** giới hạn lượng yêu cầu được xử lý trong một khoảng thời gian hoặc theo một đơn vị định danh. Cách đơn giản là đặt ngưỡng cho mỗi địa chỉ IP, nhưng địa chỉ IP **không đồng nghĩa một người dùng**.

Các trường hợp cần chú ý:

1. **CGNAT/NAT doanh nghiệp:** hàng trăm hoặc hàng nghìn người có thể dùng chung một IP công khai.
2. **Mạng di động:** IP thay đổi, roaming và nhiều thiết bị chia sẻ địa chỉ ở hạ tầng nhà mạng.
3. **IPv6:** một client có thể có nhiều địa chỉ trong cùng prefix; chỉ đặt ngưỡng theo từng địa chỉ có thể thiếu hiệu quả, còn giới hạn cả prefix quá rộng có thể gây chặn nhầm.
4. **Proxy/VPN hợp lệ:** nhiều user có thể xuất hiện từ một egress IP.
5. **API đối tác:** batch processing và retry hợp lệ có thể tạo burst, không giống tốc độ duyệt web.
6. **Người dùng nhiều tab/thiết bị:** request đồng thời có thể tăng đột biến trong một phiên hợp lệ.

**Không nên quyết định “IP này là bot” chỉ dựa vào RPS cao.** Tín hiệu đáng tin hơn thường là tổ hợp **API key, tenant, session đã xác thực, device/client identity, endpoint, hành vi và mức tiêu thụ tài nguyên**. Tuy nhiên, chính các định danh này cũng phải có khả năng chống giả mạo và quản lý vòng đời.

### Mô hình quota theo nhiều cấp

Một thiết kế có thể dùng:

- **Global capacity guardrail:** bảo vệ tổng ngân sách CPU, DB connection hoặc chi phí upstream.
- **Per-route quota:** giới hạn chặt hơn với endpoint tốn tài nguyên, khác với trang tĩnh.
- **Per-user/API key/tenant quota:** chia quyền sử dụng công bằng theo danh tính hợp lệ.
- **Per-IP/network anomaly guardrail:** là tín hiệu bổ sung trước xác thực, nhưng không dùng một mình để chặn người dùng chung NAT.
- **Priority tiers:** ưu tiên giao dịch quan trọng hoặc tác vụ đã xác thực hơn các thao tác ít cấp bách khi tài nguyên khan hiếm.

Quota phải phù hợp với mô hình quyền và điều khoản dịch vụ. Không phải lúc nào tất cả nhóm khách hàng cũng có quyền sử dụng giống nhau; điều quan trọng là **quy tắc minh bạch, kiểm chứng được và không tự tạo sự bất công ngoài dự kiến**.

## 7. Token bucket, burst và công bằng tài nguyên

Một cách triển khai rate limiting phổ biến là **token bucket**: mỗi định danh có một số token, được bổ sung theo tốc độ cấu hình; một request cần token để được xử lý. Dung lượng bucket cho phép **burst ngắn** mà không mở vô hạn.

~~~text
   Tốc độ bổ sung token (r)
               |
               v
         +-----------+
         |  BUCKET   | <--- Sức chứa tối đa (B)
         +-----------+
               |
        Request cần token
          /          \
    Có đủ token    Không đủ
        |              |
    Cho xử lý      Chờ / 429 / hạn chế
                     theo chính sách
~~~

**Ý nghĩa cấu hình:**

- **r:** tốc độ cấp token trung bình; cần dựa vào khả năng hệ thống và quyền sử dụng.
- **B:** mức burst có thể chấp nhận trong thời gian ngắn.
- **Cost per request:** có thể là 1 đơn vị/request hoặc chi phí khác nhau theo endpoint nếu nền tảng hỗ trợ.
- **Identity key:** chọn theo user/API key/tenant hoặc nguồn đã xác minh để tránh một IP chung chiếm toàn quota.
- **Retry policy:** client biết khi nào nên thử lại, tránh sinh thêm quá tải.

Một ngưỡng quá thấp gây false positive ở người dùng thật; một bucket quá lớn lại không bảo vệ backend khỏi burst nguy hiểm. Cần xem **chi phí xử lý thực tế**, không chọn giá trị tùy ý vì “trông có vẻ an toàn”.

### Leaky bucket, concurrency limit và queue

**Leaky bucket** có thể làm mượt tốc độ đầu ra; **concurrency limit** giới hạn số công việc đang thực hiện; **queue** tạm hoãn công việc khi tài nguyên bận. Những cơ chế này giải quyết các bài toán khác nhau:

| Cơ chế | Kiểm soát | Lưu ý availability |
|---|---|---|
| Rate limit | Tần suất nhận request | Có thể chặn burst hợp lệ nếu không có budget phù hợp |
| Concurrency limit | Số request/job đang xử lý đồng thời | Hữu ích với operation nặng, nhưng cần tránh giữ slot bởi request treo |
| Queue | Số công việc chờ | Queue quá dài làm tăng latency và giữ nhiều tài nguyên |
| Timeout/deadline | Thời gian giữ tài nguyên | Quá ngắn gây lỗi hợp lệ; quá dài gây tích tụ |
| Circuit breaker | Giảm yêu cầu tới dependency đang lỗi/quá tải | Cần fallback rõ, tránh lan truyền sự cố |
| Cache | Giảm số request cần origin xử lý | Phải tránh cache nhầm dữ liệu riêng tư hoặc nội dung không còn hợp lệ |

**Trả 429** thường biểu thị client gửi quá nhiều yêu cầu theo chính sách; **503** thường biểu thị dịch vụ tạm thời không thể phục vụ. Khi phù hợp, thông tin **Retry-After** giúp client chọn thời điểm thử lại. Không phải mọi hệ thống đều dùng các mã này nhất quán; cần thiết kế API contract và SDK client tương ứng.

## 8. Challenge, CAPTCHA và bot detection: có thể bảo vệ nhưng cũng gây hại

Challenge thường yêu cầu client chứng minh một thuộc tính bổ sung trước khi truy cập. Một số dạng: CAPTCHA, thử thách JavaScript/trình duyệt, xác minh đăng nhập hoặc cơ chế đánh giá hành vi.

| Đối tượng | Rủi ro nếu áp challenge không phù hợp | Thiết kế giảm tác động |
|---|---|---|
| Người dùng trình duyệt thông thường | Tăng friction, bỏ giỏ hàng, lỗi phiên | Chỉ challenge khi có đủ tín hiệu rủi ro, theo dõi success rate |
| Người dùng có nhu cầu trợ năng | CAPTCHA không phù hợp có thể cản trở hoàn toàn | Cung cấp phương án truy cập thay thế khả dụng và kiểm thử trợ năng |
| Người dùng mạng chậm/di động | Challenge tải nặng, mất kết nối hoặc timeout | Giảm bước, kiểm thử trong điều kiện mạng yếu |
| API máy–máy / webhook | Không có trình duyệt để xử lý JavaScript/CAPTCHA | Xác thực client bằng API key, mTLS, signed request hoặc phương án phù hợp |
| Người dùng sau NAT/CGNAT | Cả nhóm bị challenge do điểm rủi ro của một IP | Xét thêm session/danh tính/hành vi cá thể |
| Bot hợp lệ được ủy quyền | Giám sát, indexing hoặc tích hợp bị gián đoạn | Xác minh danh tính/phạm vi, đặt policy minh bạch |

**Challenge không phải là xác thực người dùng đầy đủ**, cũng không thay thế authorization ở backend. Một client vượt qua challenge vẫn phải đáp ứng quyền sử dụng dịch vụ.

### Geoblocking và IP reputation

Chặn theo quốc gia, ASN hoặc danh sách IP reputation có thể giảm một số traffic không mong muốn nhưng có thể chặn **khách quốc tế, người dùng VPN, nhân viên đi công tác hoặc người dùng bị gán địa lý sai**. Các thuộc tính đó mang tính tín hiệu, không phải bằng chứng danh tính hoặc ý định.

Nếu phải dùng, cần xác định phạm vi nghiệp vụ, đánh giá tác động, cơ chế hỗ trợ người dùng thật và thời điểm rà soát. **Không xem việc chặn diện rộng là biện pháp mặc định** cho mọi đợt DDoS.

## 9. Bảo vệ origin: không để traffic bỏ qua lớp edge

Khi CDN/WAF có khả năng lọc, nhưng một kênh khác vẫn truy cập trực tiếp được **origin**, lưu lượng có thể bỏ qua phần lớn lớp kiểm soát edge.

~~~text
                   Internet
                      |
                 [CDN / WAF]
                      |
               [Protected Origin]

        Đường đi ngoài dự kiến:
        Client --------> [Origin]  (bypass edge)
~~~

Thiết kế cần cân nhắc:

1. Origin chỉ chấp nhận traffic từ **đường edge/gateway được quản lý** theo cơ chế thích hợp (mạng, xác thực nguồn hoặc kênh riêng).
2. Hạn chế public exposure của backend, cổng quản trị và service phụ trợ.
3. Kiểm soát DNS, bản ghi cũ, IP công khai, load balancer phụ hoặc đường kết nối VPN/peering.
4. Duy trì **health check, deployment, backup và monitoring** qua các đường đã phê duyệt.
5. Xem xét xác thực kết nối giữa edge và origin, không chỉ dựa vào một allowlist IP có thể thay đổi.

**Không nên thay đổi firewall origin đột ngột** mà chưa kiểm kê luồng hợp lệ; có thể chặn cả edge health check hoặc đường vận hành khôi phục sự cố. Cần test kỹ đường đi trong môi trường có phép và có rollback.

## 10. DNS, TLS, QUIC và IPv6 trong phòng vệ availability

### DNS và đường vào dịch vụ

Một dịch vụ vẫn có thể bị gián đoạn dù máy chủ backend khỏe nếu hệ thống DNS authoritative, DNS resolver trong đường truy cập hoặc quá trình thay đổi routing không hoạt động đúng. Vì thế kế hoạch DDoS cần:

- Xác định khả năng chịu tải và phụ thuộc của authoritative DNS/CDN/DNS provider.
- Có quy trình thay đổi DNS/routing với TTL, cache và thời gian hội tụ thực tế được xem xét.
- Kiểm tra đường vào chính và dự phòng trong quá trình chuyển hướng mitigation.
- Theo dõi cả **DNS resolution success** và thời gian kết nối từ bên ngoài.

### HTTPS/TLS và HTTP/3

TLS handshake và việc kết thúc TLS có chi phí tài nguyên; các lớp bảo vệ cần đánh giá **tốc độ thiết lập phiên, năng lực crypto và chi phí WAF inspection**. Với **HTTP/3 dùng QUIC trên UDP**, một hệ thống chỉ có policy cho TCP/443 sẽ không bao phủ đầy đủ giao thức mới.

Không nên mặc định chặn mọi UDP/443 là cách khắc phục đơn giản và không có tác dụng phụ. Có thể ảnh hưởng hiệu năng hoặc trải nghiệm ứng dụng; cần kiểm tra khả năng xử lý HTTP/3 của CDN/WAF và cách client chuyển giao thức khi có thay đổi.

### IPv6 và dual-stack

IPv6 có không gian địa chỉ, cơ chế cấp phát và routing khác IPv4. Nếu hạ tầng public hỗ trợ dual-stack nhưng chính sách DDoS chỉ bảo vệ IPv4, một phần traffic có thể đi qua đường xử lý khác. Ngược lại, giới hạn quá rộng trên một **IPv6 prefix** có thể ảnh hưởng tới nhiều client hợp lệ. Cần kiểm thử khả năng bao phủ theo cả IPv4 và IPv6.

## 11. Quan sát và SLI: đo user hợp lệ có dùng được dịch vụ không?

**Service Level Indicator (SLI)** là chỉ số phản ánh chất lượng một khía cạnh của dịch vụ; **Service Level Objective (SLO)** là mục tiêu mong muốn cho chỉ số trong một giai đoạn. Trong ứng cứu DDoS, SLI nên được đo từ **nhiều vị trí**, không chỉ tại firewall.

| Nhóm SLI/telemetry | Ví dụ | Cần phân biệt |
|---|---|---|
| **Legitimate goodput** | Số yêu cầu/giao dịch hợp lệ hoàn tất mỗi giây | Không đồng nhất với tổng RPS trước WAF |
| **Availability theo hành trình** | Tỷ lệ login/search/checkout/API call thành công | HTTP 200 không luôn nghĩa nghiệp vụ hoàn tất |
| **Latency** | p50/p95/p99 theo endpoint và user region | Độ trễ trung bình có thể che đuôi dài gây lỗi |
| **Errors** | 5xx, timeout, 429, challenge failure và lỗi client | Cần biết lỗi do edge, proxy, app hay backend |
| **Traffic** | bps, pps, new connection rate, RPS, UDP/TCP, IPv4/IPv6 | Tăng traffic chưa tự chứng minh DDoS |
| **Mitigation** | Rule hits, drop/challenge, thời gian kích hoạt | Drop nhiều không bảo đảm FP thấp |
| **Capacity** | Link saturation, conntrack, CPU, DB pool, queue, backend health | Tắc nghẽn có thể ở dependency khác |
| **Recovery** | Thời gian phát hiện, giảm thiểu, phục hồi SLO | Cần đo từ góc nhìn client |

### False positive rate và false block

Khi có dữ liệu đã được xác minh:

~~~text
False positive rate (FPR) =
    Số yêu cầu hợp lệ bị đánh là độc hại
    -----------------------------------
    Tổng số yêu cầu hợp lệ được đánh giá

False block rate =
    Số yêu cầu hợp lệ thực sự bị chặn
    --------------------------------
    Tổng số yêu cầu hợp lệ
~~~

**Vấn đề nhãn:** Production thường không có ground truth cho mọi yêu cầu; client bị challenge hoặc block không thể tự báo toàn bộ thông tin. Vì vậy các tỷ lệ này thường là **ước lượng từ mẫu xác minh, tổng hợp ticket hỗ trợ, synthetic test hoặc hành trình đo được**. Phải nêu rõ phương pháp lấy mẫu, độ bao phủ và sai lệch.

### Dashboard tối thiểu trong sự cố

~~~text
Service:                [dịch vụ/hostname]
Incident window:        [timestamp + timezone]
User success rate:      [theo hành trình quan trọng]
Legitimate goodput:     [requests/transactions per second]
p95/p99 latency:        [theo endpoint và vùng]
HTTP 429 / 5xx:         [rate, top paths]
Challenge pass/fail:    [tỷ lệ, phân nhóm client]
Network bps / pps:      [trước và sau mitigation]
Origin CPU/DB/queue:    [sức khỏe từng dependency]
Rules activated:        [ID, time, scope, owner]
False block evidence:   [verified samples, ticket IDs]
Current decision:       [maintain / narrow / rollback]
~~~

Sử dụng timestamp nhất quán để đối chiếu dữ liệu giữa CDN, ISP, firewall, WAF và ứng dụng. Log bị trễ hoặc thiếu có thể khiến một thay đổi có vẻ hiệu quả dù người dùng vẫn gặp lỗi.

## 12. Quy trình phản ứng từng giai đoạn

Một **DDoS runbook** nên giúp các đội vận hành, mạng, ứng dụng, bảo mật và nhà cung cấp phối hợp trong áp lực sự cố.

### Giai đoạn 0 — Chuẩn bị trước sự cố

1. Kiểm kê tài sản public: domain, IP, origin, DNS, CDN, API và đường dự phòng.
2. Xác định **điểm nghẽn** và nhu cầu công suất: upstream bandwidth, firewall state, LB, proxy, app worker, DB, cache.
3. Thiết lập baseline, SLO cho hành trình quan trọng, cảnh báo theo traffic **và** user success.
4. Ký hợp đồng/thiết lập điểm liên hệ với ISP, CDN, DDoS provider và nhà cung cấp hạ tầng.
5. Chuẩn bị policy mẫu có phạm vi, quyền thay đổi, cách rollback và liên hệ on-call.
6. Kiểm thử cấu hình qua lab/staging hoặc bài diễn tập được phê duyệt; không thực hiện flood ngoài phạm vi.

### Giai đoạn 1 — Phát hiện và phân loại

1. Xác nhận **tác động**: người dùng nào, endpoint nào, lỗi 429/5xx/timeout hay DNS không phân giải.
2. Phân loại lớp ảnh hưởng: link/packets, connection state, HTTP/app/DB.
3. Xác minh thay đổi bình thường: chiến dịch, deployment, batch, peak hours.
4. Ghi nhận mức độ chắc chắn của giả thuyết và nguồn telemetry.
5. Chỉ định incident commander và kênh cập nhật giữa các bên.

### Giai đoạn 2 — Giảm thiểu có kiểm soát

1. Nếu **upstream bão hòa**, phối hợp upstream/edge mitigation; firewall origin không thể giải quyết điểm nghẽn trước nó.
2. Nếu **L7/endpoint nặng**, ưu tiên caching, quota theo endpoint/danh tính, hạn concurrency và load shedding cho tác vụ ít ưu tiên.
3. Chỉ áp rule WAF/bot/challenge có phạm vi phù hợp; tránh chặn toàn vùng địa lý hoặc dải NAT chỉ từ dấu hiệu yếu.
4. Theo dõi user success, legitimate goodput và lỗi trong lúc thay đổi, không chỉ số drop.
5. Nếu biện pháp khiến người dùng hợp lệ bị ảnh hưởng nghiêm trọng, thu hẹp hoặc rollback theo phương án đã phê duyệt.

### Giai đoạn 3 — Kiểm chứng và phục hồi

1. Xác minh hành trình khách hàng **thực sự hoàn tất**, API đối tác và tác vụ máy–máy chạy được.
2. Kiểm tra DNS, TLS, IPv4/IPv6, đường QUIC/TCP, vùng địa lý, mạng di động và shared NAT khi có thể.
3. So sánh p95/p99, 5xx, 429, queue, DB health và traffic với baseline.
4. Thu hồi rule tạm khi không còn cần, giữ những cải tiến đã được đánh giá.
5. Bảo toàn log đúng thời hạn và ghi lại từng thay đổi cùng người phê duyệt.

### Giai đoạn 4 — Hậu kiểm

Đánh giá cùng hai câu hỏi: **“đã giảm ảnh hưởng của DDoS như thế nào?”** và **“người dùng thật bị ảnh hưởng đến mức nào bởi chính biện pháp giảm thiểu?”**. Cập nhật runbook, cảnh báo, quota, capacity, ưu tiên nghiệp vụ và cách xác minh false positive.

## 13. Chiến lược giảm tải an toàn cho ứng dụng

Không phải mọi request hợp lệ đều có thể được xử lý ngay khi backend bão hòa. Cần thiết kế **graceful degradation (suy giảm chức năng có kiểm soát)** để giữ phần quan trọng nhất của dịch vụ.

| Biện pháp | Ví dụ ứng dụng | Rủi ro nếu triển khai sai |
|---|---|---|
| **Serve stale/edge cache** | Trang danh mục, ảnh, nội dung công khai có thể cache | Trả dữ liệu sai hạn hoặc lộ dữ liệu cá nhân do cache key sai |
| **Hàng đợi có giới hạn** | Đặt lịch xử lý tác vụ không đồng bộ | Queue vô hạn tạo latency và làm tăng bộ nhớ |
| **Ưu tiên giao dịch trọng yếu** | Giữ đăng nhập/checkout hơn báo cáo không cấp thiết | Rule ưu tiên có thể sai quyền hoặc bất công nếu không kiểm soát |
| **Disable tạm tính năng phụ** | Gợi ý sản phẩm, báo cáo nặng | Phải thông báo trạng thái và có cách khôi phục |
| **Circuit breaker** | Bảo vệ dịch vụ phụ thuộc đang lỗi | Mở circuit quá sớm khiến yêu cầu hợp lệ không được xử lý |
| **Concurrency budget** | Giới hạn số truy vấn database nặng cùng lúc | Budget quá thấp làm nghẽn yêu cầu hợp lệ |
| **Retry with backoff/jitter** | SDK giảm retry đồng loạt sau 429/503 | Retry liên tục không kiểm soát làm quá tải nặng hơn |

Khi có thể, **phân biệt khả năng tiếp nhận request mới với khả năng hoàn thành giao dịch đang thực hiện**. Ví dụ, không nên ngắt giữa chừng các bước thanh toán đã được chấp thuận nếu việc đó gây trạng thái không nhất quán hoặc giao dịch lặp.

### Idempotency và retry storm

Trong đợt suy giảm dịch vụ, client có thể tự động gửi lại request. Nếu quá nhiều client retry cùng lúc, hệ thống tạo **retry storm** dù ban đầu tải hợp lệ. API cần mô tả cơ chế:

- **Exponential backoff có jitter** để giảm đồng bộ hóa lần thử lại.
- **Giới hạn số lần retry và deadline** phù hợp.
- **Idempotency key** cho thao tác có nguy cơ ghi lặp hoặc thanh toán, khi hệ thống hỗ trợ.
- Phản hồi rõ **429/503 và Retry-After** khi thích hợp.
- **Circuit breaker** và feedback từ server khi tải không phục vụ được.

Giảm retry không thay thế giảm DDoS, nhưng giúp tránh biến lỗi nhỏ hoặc policy chặn nhầm thành gián đoạn diện rộng.

## 14. Tình huống thực hành: mở bán sản phẩm trùng đợt DDoS

**Bối cảnh giả định:** Nền tảng thương mại điện tử mở bán sản phẩm lúc 09:00. RPS tăng gấp nhiều lần thông thường. Hệ thống WAF tự kích hoạt rate limit cho mỗi IP; các khách dùng mạng di động hoặc Wi-Fi công cộng chung NAT nhận 429, trong khi một phần lưu lượng bất thường vẫn tiếp tục gây tải lớn ở endpoint tìm kiếm.

### Dữ liệu ban đầu (mô phỏng)

~~~text
Time:           09:00 - 09:30
Business event: Product launch
Frontend:       RPS tăng, nhiều session mới
Checkout:       Tỷ lệ hoàn tất giảm
WAF policy:     Fixed per-IP rate limit
Observed:       429 tăng mạnh ở nhóm mobile/CGNAT
Origin:         Search API có p99 latency tăng
Security:       Có tín hiệu traffic bất thường chưa phân loại đầy đủ
Conclusion:     Chưa thể gán mọi traffic vượt ngưỡng là DDoS
~~~

### Những sai lầm dễ xảy ra

- **Đánh đồng traffic lớn là tấn công:** mở bán tạo lưu lượng thật.
- **Chặn toàn bộ IP có RPS cao:** có thể chặn hàng trăm khách chia sẻ NAT.
- **Chỉ theo dõi drop count:** bỏ qua checkout failures và 429.
- **Bật CAPTCHA cho mọi API:** làm hỏng machine-to-machine clients.
- **Tăng scale toàn bộ hệ thống không giới hạn:** database vẫn có thể là điểm nghẽn và chi phí tăng.

### Cách tiếp cận có kiểm soát

1. **Xác nhận tác động nghiệp vụ:** đo checkout/login/search success theo phân nhóm user và thời điểm.
2. **Phân tách tải:** đo endpoint search, checkout, static assets, mức tiêu thụ CPU/DB và nguồn traffic qua CDN.
3. **Tăng khả năng phục vụ hợp lệ:** cache tài nguyên tĩnh và response đủ điều kiện, mở rộng worker theo năng lực thực, tối ưu truy vấn tốn tài nguyên.
4. **Giảm chặn nhầm:** xem lại rate limit IP, thay bằng quota theo user/session/API identity khi an toàn và khả thi; giữ network guardrail cho nguồn chưa xác thực.
5. **Tối ưu quy tắc theo endpoint:** chi phí của tìm kiếm khác với checkout; dùng concurrency/rate budgets khác nhau và bảo vệ checkout khỏi suy giảm dây chuyền.
6. **Ứng phó traffic bất thường:** nếu có căn cứ về DDoS, áp mitigations tại edge/upstream hoặc WAF theo tín hiệu đa nguồn, không chỉ ngưỡng IP.
7. **Kiểm tra người dùng thật:** thử hành trình trên mạng di động, nhà mạng NAT và API đối tác bằng tài khoản được phép.
8. **Theo dõi và rollback:** nếu chính sách mới gây tăng 429 hoặc challenge fail, điều chỉnh và xác nhận SLO phục hồi.

### Ma trận quyết định minh họa

| Nhóm traffic | Tín hiệu | Biện pháp ưu tiên | Cần kiểm tra |
|---|---|---|---|
| Khách đăng nhập và mua hàng hợp lệ | Session, authorization và hành trình đúng | Giữ ưu tiên phục vụ; cache dữ liệu thích hợp | Checkout success, latency |
| API batch có danh tính hợp lệ | API key/tenant, lưu lượng burst theo lịch | Quota theo key và contract; retry có kiểm soát | API success, 429 theo tenant |
| Client chưa xác thực có dấu hiệu bất thường | Pattern kết nối, chi phí request, nhiều tín hiệu | Edge/WAF adaptive limits, challenge phù hợp | False block sample, origin health |
| Truy cập static assets công khai | Nội dung cacheable | CDN caching và bảo vệ edge | Cache hit, origin traffic |
| Endpoint search rất nặng | p99/DB tăng, concurrency cao | Concurrency limit, cache và tối ưu backend | Search success, queue, DB |

**Kết luận tình huống:** không thể giảm thiểu chỉ bằng một ngưỡng “X request/IP”. Thiết kế phải bảo vệ **đường vào, chi phí xử lý và fairness cho người dùng thật** cùng lúc.

## 15. Kiểm thử và diễn tập DDoS mà không gây gián đoạn

Đánh giá năng lực phòng vệ là cần thiết nhưng việc tạo tải lên hệ thống thật có thể gây ảnh hưởng lớn. **Không tự phát tán traffic flood, không dùng hệ thống bên thứ ba hoặc hạ tầng ngoài phạm vi được phép**. Các kỹ thuật kiểm thử sau tập trung vào sự an toàn và có thể kiểm toán:

### 15.1. Bài diễn tập bàn (tabletop)

Đội mạng, bảo mật, ứng dụng, kinh doanh và nhà cung cấp mô phỏng:

1. Cảnh báo p95 latency, 5xx và bps tăng.
2. Đường uplink bão hòa trong khi backend chưa quá tải.
3. WAF bật challenge làm API đối tác không hoạt động.
4. Cần chuyển hướng qua scrubbing hoặc thay đổi policy.
5. Quá trình giảm mitigation khi traffic bình thường.

Mỗi bước ghi rõ **ai quyết định, bằng chứng yêu cầu, quyền thay đổi, kênh liên lạc, điều kiện rollback và cách đánh giá trải nghiệm người dùng**.

### 15.2. Synthetic monitoring và traffic mẫu

- Dùng **synthetic checks** có tần suất thấp từ vùng địa lý và loại mạng đại diện.
- Kiểm tra DNS resolution, TCP/TLS connection, trang login và API có test account.
- Thực hiện load test **trong staging** hoặc phạm vi production đã được phê duyệt, với giới hạn tốc độ, thời gian và stop condition.
- Sử dụng traffic mẫu hoặc mô phỏng offline để xác minh rule logic, không cần tạo một cuộc tấn công thật.
- Với nhà cung cấp DDoS, thống nhất quy trình/điều kiện diễn tập chính thức trước khi thử tính năng trên tuyến public.

### 15.3. Test case tập trung vào người dùng hợp lệ

| Test ID | Tình huống | Kỳ vọng |
|---|---|---|
| AV-01 | Người dùng hợp lệ trong giờ cao điểm | Login và nghiệp vụ chính hoàn tất trong SLO |
| AV-02 | Nhiều user sau cùng NAT/CGNAT | Không bị chặn theo IP một cách không hợp lý |
| AV-03 | API đối tác có xác thực gửi batch được phép | Không bị browser CAPTCHA; quota/429 đúng contract |
| AV-04 | Người dùng qua IPv6 hoặc HTTP/3 | Chính sách tương ứng và chức năng hoạt động |
| AV-05 | Bật mitigation phạm vi hẹp | Tín hiệu xấu giảm nhưng legitimate goodput không suy giảm ngoài dự kiến |
| AV-06 | Backend vượt concurrency budget có kiểm soát | Degradation có thông báo; không sập toàn hệ thống |
| AV-07 | Edge/WAF mất một điểm phục vụ trong bài diễn tập | Hành vi failover phù hợp thiết kế, không mở quyền tùy tiện |
| AV-08 | Hoàn nguyên mitigation tạm | SLO phục hồi, không còn rule quá hạn |

Khi điều kiện thử không đủ để xác minh (ví dụ không có quyền xem WAF action hoặc không xác định được nguồn 429), ghi **INCONCLUSIVE** thay vì PASS.

### Biên bản phép thử

~~~text
Test ID:            AV-02
Environment:        [staging / approved production scope]
Time / timezone:    [thời gian cụ thể]
User/client class:  [mobile NAT / API partner / browser]
Scenario:           [mô tả sử dụng hợp lệ]
Expected:           [nghiệp vụ hoàn tất, policy phù hợp]
Observed:           [success, 429, challenge, latency]
Edge/WAF rule:      [ID và action nếu có]
Origin metrics:     [CPU, DB, queue, 5xx]
Evidence:           [request ID, logs, synthetic result]
False-block check:  [đã xác minh hay chưa]
Result:             [PASS / FAIL / INCONCLUSIVE]
Owner / rollback:   [người và kế hoạch]
~~~

## 16. Những quyết định khó khi giảm thiểu DDoS

### Fail-open hay fail-closed?

Nếu hệ thống WAF/challenge không thể đánh giá request, **fail-open** có thể giúp người dùng tiếp tục truy cập nhưng có nguy cơ mở đường cho lưu lượng độc hại. **Fail-closed** giảm nguy cơ bypass nhưng có thể làm mất availability khi cơ chế kiểm tra lỗi.

Quyết định phải dựa trên **loại dịch vụ, mức nhạy cảm, đường dự phòng và khả năng quan sát**. Có thể cần các chế độ suy giảm khác nhau cho API công khai, cổng quản trị và giao dịch nhạy cảm. Đừng coi một lựa chọn là đúng cho mọi dịch vụ.

### Có nên dùng allowlist?

Allowlist có thể phù hợp cho **đường vận hành, health check hoặc API partner được xác thực**, nhưng:

- Không nên cho phép vô điều kiện mọi request từ một địa chỉ shared NAT.
- Cần quản lý thay đổi IP, danh tính client và mức quyền API.
- Phải kiểm tra liệu allowlist có bỏ qua toàn bộ bảo vệ HTTP hay chỉ một loại kiểm tra.
- Có owner, thời hạn rà soát và audit.

### Có nên chặn vùng địa lý?

Chỉ khi có lý do nghiệp vụ và dữ liệu đáng tin, đồng thời đánh giá khách thật ở các vùng bị tác động. Geo-IP sai lệch, VPN và đi công tác khiến blanket block có thể gây hại. Thường nên ưu tiên **rate control theo hành vi, endpoint và danh tính**, có theo dõi false positive.

### Có nên bật challenge cho toàn bộ website?

Challenge toàn site có thể làm giảm tải một số dạng bot nhưng ảnh hưởng đăng nhập, checkout, API, người dùng trợ năng và trình duyệt đặc thù. Nếu dùng, phải xác nhận đường đi nào thực sự tương thích và đo **challenge success rate cho client hợp lệ**. Không nên xem challenge pass/fail là bằng chứng tuyệt đối về ý định.

## 17. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Thực hành đúng |
|---|---|---|
| Đo thành công bằng số gói bị drop | Có thể chặn cả người dùng thật | Đo legitimate goodput, SLO và false block |
| Coi mọi traffic tăng là DDoS | Chặn flash crowd hợp lệ | Đối chiếu lịch sự kiện, hành vi và ứng dụng |
| Rate limit chỉ theo IP | Ảnh hưởng NAT/CGNAT, VPN và API đối tác | Dùng nhiều khóa định danh, phân tầng quota |
| Blanket CAPTCHA cho tất cả client | API không trình duyệt và người dùng trợ năng bị loại | Challenge chọn lọc và lựa chọn thay thế |
| Chỉ tăng số instance | Điểm nghẽn DB hoặc chi phí tăng không giới hạn | Kết hợp cache, quota, queue và giảm tải |
| Chặn tại firewall sau đường đã bão hòa | Uplink vẫn nghẽn | Phối hợp ISP/edge/scrubbing |
| Có CDN/WAF nhưng origin truy cập trực tiếp | Traffic bypass lớp bảo vệ | Origin protection và kiểm thử đường đi |
| Chỉ theo dõi IPv4/TCP | Bỏ sót IPv6, QUIC/UDP hoặc DNS | Kiểm kê toàn bộ giao thức và đường vào |
| Allowlist dải IP lớn không xác thực | Tạo đường miễn trừ kiểm soát rộng | Xác thực nguồn và giới hạn dịch vụ |
| Bỏ qua retry của client | Retry storm khiến tải nặng thêm | Backoff/jitter, deadline, idempotency |
| Đổi policy mà không xem user journey | Hết alert nhưng giao dịch vẫn thất bại | Đối chiếu từ client tới backend |
| Giữ rule khẩn cấp vô thời hạn | Rủi ro lỗi nghiệp vụ và quyền bất hợp lý | Owner, expiry, hậu kiểm và rollback |

## 18. Câu hỏi tự kiểm tra

1. Vì sao firewall báo đã drop nhiều traffic nhưng availability của dịch vụ vẫn có thể tệ?
2. Điểm khác nhau giữa **volumetric DDoS**, **state exhaustion** và **L7 DDoS** là gì về tài nguyên bị ảnh hưởng?
3. Khi đường Internet bị bão hòa trước firewall, cần phối hợp lớp bảo vệ nào?
4. Vì sao nhiều người hợp lệ dùng chung NAT có thể bị chặn bởi rate limit theo IP?
5. Token bucket giúp chấp nhận burst ngắn như thế nào, và tại sao cần chọn cả tốc độ cấp token lẫn dung lượng bucket?
6. Khi nào CAPTCHA có thể làm giảm availability dù số lượng bot bị chặn tăng?
7. Vì sao cần chính sách khác nhau cho browser khách hàng và API machine-to-machine?
8. Autoscaling có thể giải quyết được mọi đợt DDoS không? Hãy nêu hai giới hạn.
9. Các chỉ số nào chứng minh checkout thành công hơn sau một thay đổi WAF?
10. Hãy phân biệt HTTP 429 với 503 và giải thích vai trò của Retry-After.
11. Vì sao origin không nên có đường truy cập bypass không được kiểm soát ngoài CDN/WAF?
12. Kiểm thử những nhóm người dùng nào để phát hiện chặn nhầm do IPv6, CGNAT, QUIC và challenge?
13. Trong case study mở bán sản phẩm, đội vận hành nên làm gì trước khi bật một rule chặn địa lý rộng?
14. Khi đổi cấu hình DDoS tạm thời, những dữ liệu nào phải lưu để có thể rollback và đánh giá hậu kiểm?

## 19. Ghi nhớ trọng tâm

**Bảo vệ availability không chỉ là giữ máy chủ hoạt động hoặc giảm số request đến origin; đó là bảo đảm người dùng hợp lệ hoàn thành được thao tác quan trọng trong giới hạn chất lượng dịch vụ.** DDoS có thể gây quá tải băng thông, bảng kết nối hoặc tài nguyên ứng dụng; mỗi dạng đòi hỏi điểm phòng vệ và chỉ số khác nhau. Năng lực upstream/Anycast/CDN/scrubbing, firewall/WAF, cache, load balancing và kiểm soát ở backend cần được phối hợp.

**Chặn nhầm cũng là một thất bại availability.** Rate limit theo IP, CAPTCHA và geo/IP reputation cần xem xét **CGNAT, IPv6, client API, mạng di động, khả năng trợ năng và nhu cầu burst hợp lệ**. Chính sách nên dựa trên nhiều tín hiệu, quyền tối thiểu, phạm vi hẹp, có logging và rollback. Thành công được xác minh bằng **legitimate goodput, tỷ lệ giao dịch thành công, p95/p99 latency, lỗi 429/5xx, false-block evidence và thời gian phục hồi**, thay vì chỉ bằng các bộ đếm drop của thiết bị bảo mật.
