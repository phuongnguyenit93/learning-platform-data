# Định tuyến theo máy chủ, đường dẫn, vị trí và độ trễ

Khi người dùng truy cập một ứng dụng cloud, request phải đi qua một hoặc nhiều **điểm vào hệ thống** trước khi đến đúng dịch vụ. Cùng một tên miền có thể phục vụ trang web, API, ảnh và trang quản trị. Người dùng ở nhiều khu vực địa lý có thể cần điểm tiếp nhận gần mình, nhưng không phải mọi request đều được phép xử lý ở mọi nơi. Nếu một cụm bị lỗi, hệ thống phải biết chuyển lưu lượng đi đâu và dữ liệu cần có mặt tại đó như thế nào.

Các câu hỏi này dẫn tới bốn cách định tuyến quan trọng:

- **Theo máy chủ (host-based routing):** dựa vào tên miền đích như **app.example.com** hoặc **api.example.com**.
- **Theo đường dẫn (path-based routing):** dựa vào phần đường dẫn của URL như **/api/bookings** hoặc **/static/**.
- **Theo vị trí (geographic routing):** dựa vào địa điểm được suy ra của nguồn yêu cầu, vùng chính sách hoặc khu vực đích đã định nghĩa.
- **Theo độ trễ (latency-based routing):** chọn đích dự kiến có thời gian phản hồi mạng tốt hơn theo tín hiệu đo mà nền tảng định tuyến hỗ trợ.

Những phương thức này thường **được kết hợp qua nhiều tầng**, không phải bốn lựa chọn loại trừ nhau. Hệ thống có thể chọn edge gần người dùng, xác định dịch vụ theo host/path, rồi đưa tác vụ ghi về vùng có thẩm quyền đối với dữ liệu.

Bài học thuộc chương **Điểm vào hệ thống** của module **CLOUD_ARCHITECTURE**. Mục tiêu là thiết kế điểm tiếp nhận và luồng mạng theo yêu cầu nghiệp vụ, đồng thời cân bằng độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành theo nguyên tắc Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt vai trò của DNS, CDN/edge, global traffic manager, load balancer, reverse proxy, API gateway và ingress controller trong một luồng request.
2. Thiết kế quy tắc định tuyến theo hostname và path, bao gồm độ ưu tiên, rewrite, default route và trường hợp không tìm thấy tuyến hợp lệ.
3. Giải thích khác biệt giữa định tuyến theo vị trí, định tuyến theo độ trễ, Anycast và cân bằng tải theo tình trạng hoạt động.
4. Kết hợp định tuyến với yêu cầu về session, dữ liệu, RTO/RPO, chủ quyền dữ liệu và khả năng chịu lỗi đa vùng.
5. Nhận diện các rủi ro bảo mật như giả mạo Host, tin vào forwarded header chưa xác thực, bypass do chuẩn hóa path và truy cập trái phép tới endpoint quản trị.
6. Kiểm thử cấu hình định tuyến, đo chất lượng phục vụ theo vùng và xây dựng phương án failover có bằng chứng vận hành.

## 2. Request đi qua những tầng nào?

Một kiến trúc web cloud thường có các lớp sau:

~~~mermaid
flowchart LR
    U[Người dùng / Client] --> DNS[DNS / Traffic policy]
    DNS --> EDGE[CDN / WAF / Global entry]
    EDGE --> LB[Load balancer / Reverse proxy]
    LB --> GW[API Gateway / Ingress]
    GW --> WEB[Web service]
    GW --> API[API service]
    API --> DATA[(Database / Cache)]
~~~

Đây là sơ đồ logic. Một sản phẩm thực tế có thể hợp nhất CDN, WAF, global load balancing và định tuyến L7 trong một dịch vụ; một hệ thống nội bộ có thể bỏ qua CDN. Không nên suy ra tất cả request đều đi qua đúng số tầng trong hình.

| Tầng | Thông tin có thể sử dụng để đưa ra quyết định | Ví dụ kết quả |
|---|---|---|
| **DNS / traffic manager** | Tên miền được truy vấn; chính sách trọng số, địa lý, độ trễ hoặc trạng thái endpoint tùy tính năng | Trả lời địa chỉ hoặc tên đích cho một khu vực |
| **Anycast / global network / edge** | Đường đi mạng, điểm hiện diện gần/khả dụng, chính sách nhà cung cấp | Đưa kết nối tới một điểm tiếp nhận trên mạng toàn cầu |
| **Load balancer lớp 4 (L4)** | IP, cổng, TCP/UDP và tín hiệu sức khỏe | Phân phối kết nối đến target còn hoạt động |
| **Reverse proxy / load balancer lớp 7 (L7)** | HTTP Host, path, method, header và chính sách HTTP nếu được hỗ trợ | Gửi **/api/** tới dịch vụ API, **/assets/** tới static service |
| **API gateway / ingress** | Route, auth, quota, version, tenant và policy ứng dụng | Kiểm tra quyền, giới hạn tốc độ rồi chuyển đến đúng backend |
| **Ứng dụng** | Quy tắc nghiệp vụ, quyền người dùng và trạng thái dữ liệu | Xác nhận booking, tìm chỗ trống, chọn phân vùng dữ liệu |

**L4 không tự đọc và hiểu đường dẫn HTTP.** Ngược lại, để L7 phân tích hostname và path của lưu lượng HTTPS, nền tảng thường cần kết thúc TLS tại điểm phù hợp hoặc có khả năng xử lý giao thức theo thiết kế đã chọn.

### 2.1. Một yêu cầu có nhiều quyết định định tuyến

Giả sử client gọi **https://api.example.com/v1/bookings/123**. Hệ thống có thể phải ra lần lượt các quyết định:

1. Resolver tìm địa chỉ đích của **api.example.com** theo chính sách DNS hiện hành.
2. Kết nối tới điểm edge hoặc load balancer; chứng chỉ TLS được xác thực.
3. Proxy nhận diện hostname **api.example.com**, sau đó khớp path **/v1/bookings/123**.
4. Gateway xác thực người gọi, gán request tới Booking API.
5. Booking API kiểm tra quyền và xác định nơi đọc dữ liệu chuẩn theo tenant, chính sách lưu trữ và tính nhất quán yêu cầu.

Quyết định ở bước 1 không đảm bảo bước 5 được thực thi tại cùng quốc gia. Đường đi từ edge tới origin, từ API tới database và các dịch vụ bên thứ ba cần được thiết kế và kiểm chứng riêng.

## 3. Định tuyến theo máy chủ (Host-based routing)

### 3.1. Hostname là tiêu chí chọn ứng dụng hoặc tenant

Host-based routing dựa vào tên máy chủ mà client yêu cầu. Trong HTTP/1.1, tên này thường được mang bởi trường **Host**; với HTTP/2 và HTTP/3, thông tin thẩm quyền của URL được biểu diễn bằng pseudo-header **:authority**.

| Host được yêu cầu | Dịch vụ đích có thể chọn | Mục đích |
|---|---|---|
| **www.example.com** | Web frontend | Trang công khai |
| **api.example.com** | Public API gateway | Endpoint cho mobile/web |
| **admin.example.com** | Admin gateway | Giao diện và API vận hành có kiểm soát đặc quyền |
| **files.example.com** | Download service / object CDN | Tài nguyên tĩnh và tải tệp có kiểm soát |
| **customer-a.example.com** | Tenant frontend hoặc route tenant | Trải nghiệm theo khách hàng nếu chính sách đa tenant cho phép |

Ví dụ một bộ luật ở L7:

~~~text
IF host == "www.example.com"   -> web-frontend
IF host == "api.example.com"   -> public-api-gateway
IF host == "admin.example.com" -> admin-gateway
ELSE                           -> 404 hoặc từ chối host không được khai báo
~~~

Đây là **mã giả về chính sách định tuyến**, không phải cấu hình có thể áp dụng nguyên trạng cho một nhà cung cấp cụ thể.

### 3.2. TLS SNI và HTTP Host có vai trò khác nhau

Với HTTPS, client thường gửi **Server Name Indication (SNI)** trong quá trình bắt tay TLS để bên nhận chọn cấu hình/chứng chỉ thích hợp. HTTP Host hoặc :authority được xử lý ở lớp HTTP sau đó. Trong nhiều trường hợp chúng khớp nhau, nhưng **không được mặc định luôn trùng**.

Kiến trúc sư cần kiểm tra:

- Chứng chỉ có bao phủ các hostname công khai được sử dụng không; TLS kết thúc ở edge, ingress hay backend?
- Lớp proxy nào nhận Host, lớp nào chuyển tiếp SNI và có thay Host khi gọi origin không?
- Chính sách nào xử lý các yêu cầu có Host không được khai báo hoặc không phù hợp với kết nối TLS?
- Hệ thống có vô tình cho phép một hostname công khai truy cập backend nội bộ do luật mặc định quá rộng không?

Host header là **dữ liệu đầu vào của client**. Không dùng nó một mình làm bằng chứng khách hàng đã được xác thực hoặc được quyền truy cập tenant. Nếu dùng hostname để định danh tenant, phải xác thực ánh xạ tenant với danh tính đã đăng nhập và dữ liệu được yêu cầu.

### 3.3. Exact host, wildcard và default route

Một wildcard như **\*.example.com** có thể thuận tiện khi cung cấp subdomain cho nhiều tenant, nhưng phải xác định độ ưu tiên giữa hostname cụ thể và wildcard. Tên miền không hợp lệ phải có hành vi chặn rõ ràng. Tránh cấu hình default backend vô tình trỏ tới admin service hoặc dịch vụ nội bộ.

Các chi tiết cần thống nhất: chữ hoa/chữ thường trong hostname (tên DNS không phân biệt hoa thường), cổng gắn kèm trong authority, hostname quốc tế hóa, cách xử lý dấu chấm cuối và hostname chưa được cấp phép. Hãy dựa vào hành vi chuẩn hóa thực tế của gateway dùng trong dự án và kiểm thử.

## 4. Định tuyến theo đường dẫn (Path-based routing)

### 4.1. Path chia một domain thành nhiều nhóm chức năng

Với cùng tên miền **app.example.com**, hệ thống có thể chọn đích dựa trên đường dẫn:

| Quy tắc path | Backend | Ghi chú |
|---|---|---|
| **/** (exact) | Landing page | Chỉ trang chủ |
| **/app/** (prefix có ranh giới) | Web frontend | Ứng dụng khách hàng |
| **/api/bookings/** | Booking API | Chức năng đặt chỗ |
| **/api/listings/** | Listing API | Danh mục chỗ ở |
| **/assets/** | Static origin/CDN | Nội dung tĩnh, cache theo chính sách |
| **/internal/** | Từ chối ở public gateway | Không để đường dẫn bí mật trở thành cơ chế bảo mật |

Luật khớp **exact**, **prefix** và **regular expression** có thứ tự ưu tiên khác nhau tùy proxy/ingress. Nếu một route dài hơn và cụ thể hơn tồn tại, hãy xác minh nó không bị luật tổng quát đứng trước “nuốt” mất.

### 4.2. Các bẫy khi so khớp path

1. **Prefix quá rộng:** tiền tố **/api** có thể khớp cả **/apix** ở một số cơ chế khớp chuỗi. Nên sử dụng cơ chế so khớp segment phù hợp, hoặc tách **/api/** và **/api** theo quy ước.
2. **Dấu gạch chéo cuối:** **/api/bookings** và **/api/bookings/** có thể được xử lý khác nhau; quyết định có redirect, rewrite hay chấp nhận cả hai.
3. **URL-encoding và chuẩn hóa:** **%2F**, đường dẫn **..**, dấu **//**, ký tự Unicode hoặc thay đổi chữ hoa/chữ thường có thể được diễn giải khác nhau ở CDN, WAF, proxy và backend. Cần thống nhất quy tắc chuẩn hóa và kiểm tra chống bypass.
4. **Query string:** **/search?q=room** có path là **/search**; query có thể ảnh hưởng logic ứng dụng hoặc cache key nhưng không phải một phần của path theo nghĩa định tuyến thông thường.
5. **HTTP method:** cùng path nhưng GET và POST có ý nghĩa khác nhau. Phân biệt route và phân quyền theo method khi cần; đừng dựa vào path để suy ra quyền ghi.
6. **Rewrite:** gateway có thể nhận **/api/v1/bookings** rồi chuyển đến backend thành **/v1/bookings**. Hai bên phải thống nhất base path và tránh tạo redirect sai, asset URL lỗi hoặc bỏ sót log.

Một chính sách ví dụ:

~~~text
Host: api.example.com

1. exact /healthz                  -> health-handler (giới hạn thông tin phản hồi)
2. prefix /v1/bookings/            -> booking-api
3. prefix /v1/listings/            -> listing-api
4. prefix /v1/                    -> api-not-found
5. fallback                       -> 404
~~~

Đừng cho rằng health endpoint công khai có thể thay thế health check nội bộ; một endpoint chỉ trả 200 mà không kiểm tra dependency quan trọng có thể làm hệ thống gửi traffic tới backend chưa sẵn sàng.

### 4.3. Tách route khỏi kiểm soát quyền

Một rule đưa **/admin/** tới admin service không có nghĩa chỉ quản trị viên truy cập được. Phải áp dụng authentication và authorization tại lớp phù hợp, có kiểm tra ở backend cho thao tác nhạy cảm. Proxy có thể xác thực trước, nhưng service owner vẫn phải bảo vệ quyền nghiệp vụ của mình.

Với API đa tenant, route theo path hoặc hostname có thể chọn đúng dịch vụ, song backend phải kiểm tra quyền truy cập tới từng tài nguyên và từng tenant; không tin tenant ID do client tự gửi.

## 5. Định tuyến theo vị trí (Geographic routing)

### 5.1. Vị trí nào đang được đo?

Một DNS traffic manager có thể sử dụng địa chỉ của **recursive DNS resolver** để suy ra khu vực của người hỏi; một số hệ thống sử dụng thông tin **EDNS Client Subnet (ECS)** khi có và được hỗ trợ. Vì vậy, vị trí DNS suy ra không phải lúc nào cũng là vị trí thiết bị người dùng.

Ở edge hoặc proxy, nền tảng có thể ước lượng vị trí từ **địa chỉ IP kết nối đến**. Kết quả vẫn có thể sai do VPN, proxy, CGNAT, mạng doanh nghiệp, roaming, dữ liệu geolocation chưa cập nhật hoặc người dùng ở gần ranh giới địa lý.

| Điểm ra quyết định | Dữ liệu vị trí thường có | Lưu ý |
|---|---|---|
| DNS resolver / traffic policy | IP resolver, đôi khi subnet client qua ECS | Không phải tọa độ chính xác của người dùng; DNS cache ảnh hưởng kết quả |
| CDN / edge | IP client nhìn thấy tại edge, dữ liệu IP geolocation | IP có thể thuộc VPN/proxy; kết quả dự đoán thay đổi |
| Ứng dụng | Địa chỉ/tài khoản đã xác minh hoặc vùng do người dùng chọn, kết hợp IP | Cần chính sách quyền riêng tư, xác thực và giải quyết mâu thuẫn |
| Hệ thống xử lý dữ liệu | Thuộc tính tenant, phân loại dữ liệu, chính sách vị trí được phê duyệt | Đây mới là lớp cần ra quyết định có thẩm quyền cho yêu cầu residency/sovereignty |

### 5.2. Khi nào định tuyến theo vị trí hữu ích?

- Phục vụ giao diện, ngôn ngữ hoặc nội dung phù hợp thị trường.
- Chọn khu vực đặt frontend/edge gần người dùng.
- Hướng người dùng đến trung tâm hỗ trợ theo phạm vi phục vụ.
- Đáp ứng một phần chính sách phân vùng khách hàng khi có định nghĩa và kiểm chứng bổ sung.
- Kiểm soát năng lực phục vụ từng thị trường, ví dụ khi một tính năng chỉ được mở tại một số quốc gia.

**Không nên dùng IP geolocation làm biện pháp duy nhất để bảo đảm tuân thủ dữ liệu.** Địa điểm request xuất phát không nhất thiết quyết định nơi dữ liệu được phép lưu hoặc xử lý. Dữ liệu có thể đi tiếp tới origin, replica, backup, log và nhà cung cấp bên thứ ba.

### 5.3. Geographic routing khác với ràng buộc vị trí dữ liệu

Giả sử khách hàng thuộc tenant có chính sách lưu dữ liệu trong một khu vực được phê duyệt, nhưng người dùng của tenant đang đi công tác ở nước khác. Định tuyến theo IP gần họ có thể đưa request tới edge ở nước ngoài. Thiết kế phải phân biệt:

- **Nơi tiếp nhận kết nối và cache:** edge có thể xử lý TLS, WAF và nội dung công khai; cần xem kỹ việc cache dữ liệu nhạy cảm.
- **Nơi xử lý dữ liệu nghiệp vụ:** API/backend có thể cần chạy ở khu vực hợp lệ.
- **Nơi lưu dữ liệu, log và backup:** phải theo chính sách riêng cho từng loại dữ liệu.
- **Quyền truy cập từ xa:** có thể tồn tại yêu cầu kiểm soát người vận hành và bên xử lý dữ liệu, vượt ra ngoài tên region.

Nếu thiếu vùng đích thỏa chính sách, không được tự động failover sang một vùng bất kỳ chỉ vì nó còn hoạt động. Hệ thống cần hành vi đã được chấp thuận: chuyển tới vùng dự phòng hợp lệ, giảm chức năng hoặc tạm từ chối tác vụ.

### 5.4. Geographic routing và geoproximity không hoàn toàn giống nhau

Một số nền tảng phân biệt:

- **Geolocation:** luật dựa trên quốc gia, châu lục hoặc phạm vi địa lý được cấu hình.
- **Geoproximity:** luật dựa trên khoảng cách địa lý tới vị trí tài nguyên, đôi khi có cơ chế điều chỉnh vùng ảnh hưởng.
- **Latency-based:** luật dựa trên ước lượng hoặc đo lường độ trễ mạng tới endpoint.

Khoảng cách địa lý ngắn **không đảm bảo** độ trễ mạng ngắn: đường truyền Internet, peering, sự cố tuyến và chất lượng mạng có thể khiến điểm ở xa hơn phản hồi nhanh hơn.

## 6. Định tuyến theo độ trễ (Latency-based routing)

### 6.1. Mục đích và nguồn tín hiệu

Latency-based routing chọn endpoint được hệ thống đánh giá là có độ trễ thích hợp hơn đối với vùng mạng của người hỏi. Nền tảng có thể dựa trên số liệu lịch sử, phép đo từ mạng toàn cầu hoặc chỉ số do operator cung cấp. Thuật toán và độ bao phủ khác nhau theo CSP/sản phẩm.

Khác với cân bằng tải **theo trọng số**, phương thức này không chủ yếu phân phối một tỷ lệ lưu lượng cố định. Khác với định tuyến **theo vị trí**, nó không chỉ dựa trên ranh giới địa lý. Cũng không thể coi đây là phép đo trực tiếp độ trễ của từng request tại thời điểm nó được gửi.

### 6.2. Độ trễ mạng thấp chưa chắc giao dịch nhanh

Độ trễ đầu cuối của một tác vụ bao gồm nhiều thành phần:

~~~text
Thời gian trải nghiệm ~ DNS / kết nối / TLS
                       + client -> điểm vào
                       + điểm vào -> backend
                       + backend -> database / dependency
                       + xử lý ứng dụng
                       + truyền phản hồi / render trên client
~~~

Đây là mô hình cộng các phần thời gian để suy nghĩ về đường đi, **không phải công thức đo chính xác cho mọi ứng dụng**; các thao tác song song, streaming, cache và pipelining có thể làm tổng thời gian khác.

Ví dụ minh họa: Edge A ở gần client với đường mạng 20 ms tới API, nhưng API cần truy vấn DB ở xa khiến một thao tác mất thêm 180 ms. Edge B xa hơn với đường mạng 80 ms nhưng backend và DB cùng khu vực chỉ thêm 15 ms. Với request cần DB, đường B **có thể** phản hồi nhanh hơn. Để quyết định phải đo end-to-end p50/p95/p99, không chỉ RTT đến edge.

### 6.3. Kết hợp latency với health và chính sách

Một chính sách định tuyến thực tế nên xem xét:

1. Endpoint có nằm trong tập **được phép** với loại dữ liệu và tenant hay không?
2. Endpoint có **healthy** theo kiểm tra phù hợp không?
3. Endpoint có đủ **capacity/quota** và đạt giới hạn tải không?
4. Số liệu latency có liên quan tới loại request thực tế không?
5. Chuyển đích có vi phạm session affinity hoặc tính nhất quán đọc-sau-ghi không?

Chỉ sau các bộ lọc trên mới nên ưu tiên endpoint có độ trễ dự kiến tốt hơn. Nếu không, một vùng “nhanh” nhưng thiếu dữ liệu hoặc không được phép xử lý dữ liệu có thể tạo lỗi nghiêm trọng.

### 6.4. Đừng nhầm latency routing với autoscaling hoặc failover

Latency routing không tự tạo thêm instance khi tải tăng, không tự khôi phục database và không đảm bảo chuyển vùng an toàn khi lỗi. Các nhiệm vụ đó thuộc autoscaling, load balancing, kiểm tra sức khỏe, replication, kế hoạch DR và quy trình ứng dụng.

Một thiết kế có thể đặt global traffic manager chọn region, rồi load balancer trong region phân phối đến các instance còn khỏe. Cần quy định hành vi khi **tất cả region hợp lệ đều không khỏe**: trả lỗi có kiểm soát, bật chế độ suy giảm hoặc tiến hành DR thủ công theo runbook, thay vì chuyển bất chấp chính sách.

## 7. Kết hợp bốn cách định tuyến trong một hệ thống

### 7.1. Thứ tự quyết định nên bắt đầu từ ràng buộc bắt buộc

Không có một thứ tự vật lý cố định cho mọi nhà cung cấp: DNS/Anycast có thể chọn edge trước khi L7 đọc Host/path, và ứng dụng có thể kiểm tra tenant sau đó. Nhưng về **quyết định thiết kế**, nên tách các lớp:

1. **Danh tính endpoint và giao thức:** domain được phép, TLS, chuẩn hóa Host và path, từ chối đích không hợp lệ.
2. **Năng lực nghiệp vụ:** xác định tuyến theo host/path/method và yêu cầu xác thực, phân quyền.
3. **Phạm vi dữ liệu và tenant:** xác định những origin/region được phép xử lý request cụ thể.
4. **Sức khỏe và năng lực phục vụ:** loại trừ đích lỗi, quá tải hoặc không đủ dependency.
5. **Tối ưu phân phối:** trong các đích hợp lệ, cân nhắc vị trí, độ trễ, trọng số, chi phí hoặc phiên bản canary.
6. **Kiểm tra sau định tuyến:** đo latency và trạng thái giao dịch, thực hiện retry/fallback theo quy tắc nghiệp vụ.

Ở các tầng trước khi giải mã được request hoặc xác thực tenant, quyết định định tuyến chỉ có thể là **tạm thời**. Các luật tại ứng dụng/gateway phải bảo vệ ràng buộc dữ liệu khi có đủ thông tin.

### 7.2. Một bảng policy mẫu

Giả sử sản phẩm đặt chỗ có ba nhóm dữ liệu: ảnh công khai, tìm kiếm có thể cache và giao dịch đặt phòng cần chính sách dữ liệu chặt.

| Host + path | Backend logic | Chính sách vị trí/độ trễ | Ghi chú |
|---|---|---|---|
| **www.example.com/** | Web frontend | Phục vụ từ CDN/edge phù hợp | Cache asset công khai theo policy |
| **www.example.com/assets/** | Object storage qua CDN | Edge gần client | Kiểm tra purge, cache key, quyền truy cập |
| **api.example.com/v1/search/** | Search API | Có thể chọn region healthy độ trễ thấp trong danh sách hợp lệ | Kết quả có thể hơi trễ so với nguồn chuẩn nếu hợp đồng cho phép |
| **api.example.com/v1/bookings/** | Booking API | Region của tenant/dữ liệu có thẩm quyền; HA theo thiết kế | Cần idempotency, state consistency, DR |
| **admin.example.com/** | Admin gateway | Chỉ endpoint bảo vệ; không mở tự do theo vị trí IP | SSO/MFA, authz, audit, giới hạn mạng nếu phù hợp |
| Host hoặc path không hợp lệ | Deny/default | Không tự gửi tới backend nhạy cảm | 404/403/421 theo giao thức và chính sách triển khai |

### 7.3. Sơ đồ kết hợp

~~~mermaid
flowchart TB
    U[Client tại nhiều khu vực] --> G[DNS / Anycast / Global entry]
    G --> EDGE[Edge: TLS / WAF / Host + Path]
    EDGE -->|www / assets| CDN[CDN + Static origin]
    EDGE -->|api / search| SR[Search routing]
    EDGE -->|api / bookings| BR[Booking routing]
    EDGE -->|admin| ADMIN[Admin gateway có kiểm soát]
    SR --> POLICY{Đích hợp lệ và khỏe?}
    POLICY -->|Có| FAST[Search API tại region phù hợp]
    POLICY -->|Không| DEG[Giảm chức năng / lỗi có kiểm soát]
    BR --> TENANT[Authz + tenant / data policy]
    TENANT --> ALLOWED{Region được phép + healthy?}
    ALLOWED -->|Có| BOOK[Booking API + dữ liệu có thẩm quyền]
    ALLOWED -->|Không| DR[DR hợp lệ / báo lỗi]
    FAST --> READ[(Search index / read model)]
    BOOK --> DB[(Booking database)]
~~~

Sơ đồ mang tính logic. Điểm edge không tự biết quyền tenant chỉ từ domain/path. Việc kiểm tra tenant và chính sách dữ liệu phải nằm tại thành phần có thông tin đáng tin cậy, trước khi xử lý dữ liệu ở một đích bị hạn chế.

### 7.4. Ví dụ cấu hình chính sách ở dạng mô tả

~~~yaml
# Mã giả theo dạng YAML, KHÔNG áp dụng trực tiếp cho một ingress cụ thể.
virtualHosts:
  - host: www.example.com
    paths:
      - match: /assets/*
        backend: static-origin
        cachePolicy: public-assets
      - match: /*
        backend: web-frontend
  - host: api.example.com
    paths:
      - match: /v1/search/*
        backend: search-router
        regionPolicy: allowed-healthy-low-latency
      - match: /v1/bookings/*
        backend: booking-router
        regionPolicy: tenant-authoritative-region
  - host: admin.example.com
    paths:
      - match: /*
        backend: protected-admin
        authentication: required
defaultAction: reject-unknown-host
~~~

Khi chuyển thành cấu hình thực tế, phải kiểm tra cú pháp, mức hỗ trợ wildcard, thứ tự match, path rewrite, authentication và khả năng áp dụng chính sách vùng của sản phẩm đang dùng. Đừng đưa giả mã vào production như thể đã là cấu hình hoàn chỉnh.

## 8. Những quyết định liên quan đến trạng thái và tính nhất quán

### 8.1. Session affinity không phải câu trả lời cho mọi trạng thái

Một số ứng dụng giữ session trong bộ nhớ tiến trình và dùng sticky session để tránh mất phiên. Cách này có thể đơn giản trong ngắn hạn, nhưng khi instance hoặc region lỗi, phiên có thể bị mất. Nên cân nhắc cookie được ký đúng cách, state store chia sẻ có quyền phù hợp hoặc mô hình xác thực không phụ thuộc instance khi yêu cầu cho phép.

Sticky session có thể gây mất cân bằng tải; không nên dùng nó để che giấu việc một dịch vụ phụ thuộc trạng thái cục bộ mà không có phương án khôi phục.

### 8.2. Đọc và ghi có thể cần chính sách khác nhau

Một API đọc danh sách sản phẩm có thể phục vụ từ cache hoặc read replica gần client; một request ghi booking phải đảm bảo không bán trùng phòng. Vì vậy:

- **Read:** có thể cho phép dữ liệu chậm cập nhật nếu trải nghiệm và hợp đồng API cho phép; có chính sách TTL hoặc cơ chế invalidation.
- **Write:** cần tới nơi có thẩm quyền ghi, quy tắc kiểm tra đồng thời và khóa idempotency để chống thao tác trùng khi retry.
- **Read after write:** nếu người dùng cần thấy kết quả vừa đặt ngay, phải đọc từ nguồn phù hợp hoặc có cơ chế chờ projection đạt phiên bản yêu cầu.

Việc chuyển request ghi đến region “gần nhất” có thể tăng xung đột, thêm hop tới database chính hoặc tạo ghi phân tán khó nhất quán. Thiết kế theo yêu cầu giao dịch trước, rồi mới tối ưu độ trễ.

### 8.3. Retry và failover phải hiểu ngữ nghĩa request

GET không làm thay đổi trạng thái theo hợp đồng có thể dễ thử lại hơn, nhưng vẫn phải tránh retry vô hạn. POST thanh toán hoặc đặt phòng có thể đã hoàn thành ở backend dù response mất; retry qua region mới có nguy cơ tạo giao dịch kép nếu không có cơ chế idempotency xuyên các đích có thể tiếp nhận request.

Khi định tuyến qua nhiều region, cần quyết định rõ: ai cấp idempotency key, phạm vi hiệu lực, nơi lưu kết quả, thời gian retention, chính sách đối soát và điều kiện được phép failover thao tác ghi.

## 9. Tính sẵn sàng, health check và khôi phục

### 9.1. Health check cần đo đúng cấp

| Cấp | Có thể kiểm tra | Không tự chứng minh |
|---|---|---|
| TCP / TLS | Kết nối tới target, chứng chỉ/giao thức có thể hoạt động | API trả kết quả đúng hoặc database sẵn sàng |
| HTTP /ready | Ứng dụng đã khởi tạo và có thể nhận một số request | Luồng đặt phòng đầu cuối thành công |
| Synthetic transaction | Một thao tác nghiệp vụ mô phỏng được thực hiện trong phạm vi an toàn | Mọi loại yêu cầu và tải đều ổn định |
| SLI production | Tỷ lệ thành công, p95/p99, lỗi theo host/path/region | Hệ thống có thể phục hồi khi một region mất hoàn toàn |
| DR exercise | Có thể chuyển vùng và khôi phục dữ liệu theo kịch bản thử | Mọi loại sự cố tương lai đều được bao phủ |

Một backend có thể trả 200 ở **/healthz** nhưng Booking DB không truy cập được. Nếu global traffic manager chỉ dựa vào health endpoint quá nông, lưu lượng tiếp tục bị đưa tới region không thể hoàn tất giao dịch.

### 9.2. DNS failover có độ trễ riêng

Thay đổi bản ghi DNS không đồng nghĩa mọi client lập tức đến địa chỉ mới. Resolver và client có thể cache theo TTL; hệ thống mạng, kết nối đang mở và DNS caching ngoài dự đoán cũng ảnh hưởng thời gian chuyển. TTL ngắn hơn có thể giúp trong một số tình huống, nhưng tăng số lượng truy vấn và **không bảo đảm** RTO.

Với Anycast hoặc global proxy, khả năng loại bỏ một backend khỏi tập khỏe có thể nhanh hơn trong một số mô hình, nhưng thời gian failover thực tế vẫn phụ thuộc dữ liệu, capacity, kiểm tra sức khỏe và hành vi kết nối. Chỉ có diễn tập mới cho biết mức phục hồi đạt được.

### 9.3. Multi-region không tự đồng nghĩa highly available

Để chuyển vùng mà giao dịch vẫn đúng cần:

- Region dự phòng **được phép** xử lý dữ liệu liên quan.
- Application/config/secret/identity và quota có thể khởi chạy hoặc đã sẵn sàng.
- Database replica hoặc bản sao lưu đáp ứng RPO/RTO nghiệp vụ, có kiểm tra nhất quán sau failover.
- Quy tắc DNS/global routing biết vùng mới đang thực sự phục vụ được.
- Cơ chế xử lý request đang dở, message trùng và đối soát thanh toán/đặt phòng.
- Runbook và người trực xử lý, quan sát lỗi và có kế hoạch chuyển lại khi vùng chính hồi phục.

HA trong một region với nhiều zone và DR giữa nhiều region giải quyết những phạm vi lỗi khác nhau. Cần chọn theo failure domain và độ quan trọng nghiệp vụ.

## 10. Bảo mật tại điểm vào và ranh giới tin cậy

### 10.1. Host/path là dữ liệu điều hướng, không là chứng nhận quyền truy cập

Một reverse proxy có thể dựa trên hostname hoặc path để chọn dịch vụ, nhưng attacker có thể tự tạo request mang Host/path bất kỳ. Vì vậy:

- Chỉ chấp nhận hostname đã đăng ký; dùng default route an toàn.
- Kiểm tra TLS certificate/SNI/Host theo khả năng gateway; không sử dụng Host chưa kiểm chứng để xây dựng URL reset password, callback hoặc redirect.
- Chỉ tin **X-Forwarded-For, X-Forwarded-Host, Forwarded** từ các reverse proxy được cấu hình tin cậy; không để client tự khai báo IP hoặc scheme có quyền đặc biệt.
- Thống nhất cách normalize/decode path giữa CDN, WAF, proxy và backend; kiểm tra đường dẫn nhập nhằng.
- Đặt authn/authz cho admin API và cho từng tài nguyên nghiệp vụ ở lớp backend.
- Dùng TLS, WAF, rate limiting và giới hạn kích thước request theo rủi ro; giám sát traffic bất thường.

Nếu CDN cho phép truy cập origin trực tiếp, các quy tắc WAF/route tại edge có thể bị bỏ qua. Cần giới hạn quyền truy cập origin theo mô hình phù hợp, đồng thời tránh tin vào một header do bên ngoài có thể giả mạo.

### 10.2. Geo-blocking không phải kiểm soát danh tính

Chặn lưu lượng từ một quốc gia có thể là một tín hiệu giảm bớt nguy cơ lạm dụng cho một số nghiệp vụ, nhưng IP geolocation có sai số và có thể bị thay đổi qua VPN/proxy. Không dùng quốc gia được suy ra thay cho xác thực, quyền truy cập hoặc chính sách bảo vệ dữ liệu.

### 10.3. Bảo vệ cache và dữ liệu riêng tư

Tại CDN cần xem **cache key** có tính tới host, path, query và header nào; đặc biệt với response theo tài khoản hoặc cookie. Nếu cache key hoặc chính sách cache sai, response của người dùng này có thể bị phục vụ cho người khác. Chỉ cache dữ liệu có thể chia sẻ theo chính sách; với dữ liệu nhạy cảm, sử dụng cơ chế private/no-store hoặc lựa chọn có cơ sở và kiểm thử.

## 11. Quan sát, kiểm thử và xử lý sự cố định tuyến

### 11.1. Metric và log nên gắn với quyết định route

Các tín hiệu hữu ích:

| Nhóm | Ghi nhận / giám sát | Dùng để phát hiện |
|---|---|---|
| Route | Host đã chuẩn hóa, route ID, backend ID, region/zone đích, policy version | Lưu lượng tới sai dịch vụ hoặc region |
| Hiệu năng | p50/p95/p99 latency, TTFB, upstream connect time, retry count | Định tuyến “gần” nhưng backend chậm |
| Chất lượng nghiệp vụ | Tỷ lệ tạo booking thành công, lỗi đăng nhập, tìm kiếm thất bại | Proxy khỏe nhưng tác vụ quan trọng lỗi |
| Sức khỏe và capacity | Target healthy, saturation, queue, quota, autoscaling | Mất đích hoặc quá tải khi chuyển vùng |
| Dữ liệu | Replica lag, region xử lý, lỗi policy, luồng dữ liệu không dự kiến | Chọn đích không phù hợp tính nhất quán/chủ quyền |
| An ninh | Host lạ, path bị chặn, WAF action, auth failure, rate limit | Scanning, bypass attempt và bất thường truy cập |
| Chi phí | CDN requests, cache-hit ratio, inter-region transfer, egress | Đường đi quá xa hoặc cache hoạt động kém |

Không ghi token, thông tin thẻ, payload nhạy cảm hoặc IP đầy đủ nếu không có mục đích/chính sách phù hợp. Nhãn metric phải có cardinality được kiểm soát; không đưa bookingId hay userId vào label gây nổ số chuỗi metric.

### 11.2. Ma trận kiểm thử tuyến

| Thử nghiệm | Kết quả mong đợi | Cách xác minh |
|---|---|---|
| Host hợp lệ cho web và API | Đúng backend, chứng chỉ phù hợp | Gọi HTTPS tới từng hostname, kiểm tra route ID/log |
| Host không được khai báo | Từ chối, không tới admin/internal backend | Request với hostname lạ tại môi trường test |
| Path chính xác và tiền tố | **/api/** và **/apix** không bị nhầm | Bộ test exact/prefix, slash, encoded path |
| Rewrite và query | Backend nhận URI theo hợp đồng | Integration test và trace gateway→backend |
| Request không có quyền | 401/403, không lộ dữ liệu | Test theo tenant/role, kể cả gọi thẳng origin khi có thể |
| Request từ nhiều khu vực | Đến vùng phù hợp chính sách, độ trễ được đo | Probe từ các khu vực thực tế, kiểm tra trace/region |
| Region hoặc endpoint unhealthy | Chuyển tới đích hợp lệ hoặc trả lỗi đúng | Diễn tập ngắt backend, đo failover và RTO |
| Retry POST sau timeout | Không tạo giao dịch kép | Test idempotency, đối soát và trạng thái cuối |
| CDN cache | Nội dung công khai được cache, nội dung riêng không lộ | Kiểm tra cache headers/key với nhiều tài khoản |

Ví dụ lệnh thử host/path ở môi trường đã được phép kiểm tra:

~~~bash
# Kiểm tra URL và certificate qua đường phân giải DNS bình thường.
curl -i https://api.example.com/v1/bookings/booking_123

# Ép tên miền dùng IP của điểm vào trong môi trường thử nghiệm;
# curl vẫn giữ hostname URL cho HTTPS, SNI và HTTP Host.
curl --resolve api.example.com:443:203.0.113.10 \
  -i https://api.example.com/v1/bookings/booking_123
~~~

**203.0.113.10** thuộc dải địa chỉ dành cho ví dụ tài liệu; thay bằng endpoint được phép trong môi trường thử nghiệm. Lệnh chỉ minh họa cách xác minh route; không khẳng định API sẽ trả thành công khi thiếu token hoặc ID hợp lệ.

Khi kiểm tra geographic routing, không nên chỉ tự đặt header **X-Forwarded-For**: hệ thống đúng phải bỏ qua nguồn header không đáng tin. Hãy dùng probe tại các mạng/khu vực thật hoặc công cụ kiểm thử địa lý chính thức, sau đó đối chiếu region thực tế qua log/trace.

### 11.3. Một runbook chẩn đoán khi định tuyến sai

1. Xác nhận triệu chứng và ảnh hưởng: host, path, method, thời điểm, vùng người dùng và SLI bị tác động.
2. Kiểm tra DNS/TTL, certificate và điểm vào thực tế; phân biệt lỗi giải tên, lỗi bắt tay TLS và lỗi HTTP.
3. Xem route rule/version, thứ tự match, host/path normalize, rewrite và backend đang được chọn.
4. Kiểm tra trạng thái target, WAF, auth, rate limit, trace upstream, DB và dependency.
5. So sánh region được chọn với policy tenant/data, metrics độ trễ và sức khỏe.
6. Rollback cấu hình gây lỗi hoặc failover theo runbook; tránh làm mất tính nhất quán giao dịch.
7. Xác minh bằng synthetic test và SLI nghiệp vụ, rồi cập nhật tài liệu/sơ đồ và nguyên nhân gốc.

## 12. Tình huống thực hành: nền tảng đặt chỗ ở nhiều khu vực

Một sản phẩm giả định phục vụ khách hàng tại Việt Nam và một số thị trường quốc tế, gồm trang web, hình ảnh công khai, tìm kiếm chỗ ở, đặt phòng và cổng quản trị. Các yêu cầu dưới đây là **mục tiêu minh họa**, không phải cam kết của cloud provider:

- Người dùng muốn tải ảnh nhanh ở nhiều thị trường.
- Chức năng đặt phòng có yêu cầu tránh đặt trùng và xử lý được retry khi kết nối không ổn định.
- Chủ sở hữu dữ liệu phê duyệt danh sách region được phép lưu/xử lý từng nhóm dữ liệu.
- SLO tạo booking và mục tiêu DR phải được xác định bằng đo lường và diễn tập; việc chọn multi-region không tự chứng minh đạt yêu cầu.
- Cổng quản trị yêu cầu MFA, quyền hạn phù hợp và audit.

### 12.1. Thiết kế sơ bộ

1. **Global entry + CDN:** phục vụ asset công khai tại edge phù hợp, có quy tắc cache và invalidation.
2. **Host routing:** **www.example.com** tới frontend, **api.example.com** tới API, **admin.example.com** tới cổng bảo vệ.
3. **Path routing:** dưới **api.example.com**, **/v1/search/** tới Search, **/v1/bookings/** tới Booking.
4. **Geo/latency routing:** Search có thể được phục vụ tại nhiều region khỏe và hợp lệ; định tuyến ưu tiên độ trễ đo được trong phạm vi này.
5. **Data-aware routing:** Booking xác thực tenant và gửi thao tác ghi tới vùng có thẩm quyền, với giải pháp dự phòng được phê duyệt; không tùy tiện ghi ở edge gần nhất.
6. **Observability:** dashboard theo host, path group, region, health, cache-hit, replication lag, độ trễ và tỷ lệ thành công giao dịch.

### 12.2. Đánh đổi ba phương án

| Phương án | Lợi ích | Rủi ro / chi phí | Phù hợp khi |
|---|---|---|---|
| **A – Một region, đa zone, CDN toàn cầu** | Đơn giản hơn cho dữ liệu ghi, CDN cải thiện nội dung tĩnh | API ở xa có thể chậm; cần kế hoạch DR khi mất region | Đội nhỏ, ưu tiên nhất quán và chưa cần xử lý API đa vùng |
| **B – Multi-region cho Search, Booking ghi tập trung** | Giảm độ trễ đọc ở nhiều khu vực, giữ đường ghi có thẩm quyền | Cần projection/index, replication, chính sách dữ liệu và theo dõi lag | Lưu lượng đọc cao và cho phép độ trễ đồng bộ dữ liệu tìm kiếm |
| **C – Multi-region cho cả giao dịch ghi** | Có thể giảm khoảng cách đến người dùng và tăng năng lực phục vụ vùng | Khó nhất về xung đột ghi, transaction, consistency, DR và chi phí | Nghiệp vụ có yêu cầu mạnh và đội ngũ đủ năng lực vận hành ghi phân tán |

Không nên chọn phương án C chỉ vì tưởng rằng “region gần nhất luôn nhanh hơn”. Đối với booking có invariant không cho đặt trùng, tính đúng đắn của giao dịch và quyền sở hữu dữ liệu phải được giải quyết trước khi cho phép ghi ở nhiều nơi.

### 12.3. Thử lỗi và đánh giá

**Tình huống 1 – Search region A không khỏe:** global routing loại bỏ A khỏi tập hợp đích, chỉ chọn B nếu B thỏa policy và có capacity; Search có thể giảm chức năng nếu mọi đích hợp lệ đều lỗi.

**Tình huống 2 – Booking API trả timeout sau POST:** client sử dụng cùng idempotency key và truy vấn trạng thái/đối soát trước khi thử lại; không tùy tiện chuyển sang region khác với một giao dịch mới.

**Tình huống 3 – IP geolocation xác định sai khu vực:** người dùng vẫn được phục vụ theo quyền tài khoản và chính sách dữ liệu; hệ thống không dựa duy nhất vào vị trí IP để xác định nơi lưu thông tin đặt phòng.

**Tình huống 4 – thay path từ /api/bookings sang /v1/bookings:** gateway phải giữ tương thích theo lịch, cập nhật contract, test rewrite, cache và giám sát tỷ lệ truy cập phiên bản cũ trước khi ngừng tuyến.

## 13. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi phải trả lời | Minh họa đánh đổi |
|---|---|---|
| **Operational Excellence** | Route do ai sở hữu, thay đổi bằng IaC/PR thế nào, ai trực sự cố và kiểm chứng rollback? | Nhiều luật host/path/region tăng độ linh hoạt nhưng cần kiểm thử và quan sát rõ |
| **Security** | TLS, WAF, Host validation, authz, origin access và phân vùng dữ liệu có được kiểm soát? | Định tuyến linh hoạt dễ tạo cấu hình nhầm nếu thiếu policy và kiểm tra |
| **Reliability** | Route có biết đích khỏe? DNS TTL, failover, consistency, RTO/RPO có được diễn tập? | Đa vùng giảm một số điểm lỗi nhưng làm phức tạp dữ liệu và xử lý sự cố |
| **Performance Efficiency** | p95/p99 end-to-end theo khu vực có tốt hơn, hay chỉ RTT đến edge giảm? | Edge gần client có thể vẫn phải gọi DB xa; cache và đọc phân tán cần đúng ngữ nghĩa |
| **Cost Optimization** | CDN, WAF, gateway, load balancer, inter-region traffic, egress và log tốn bao nhiêu? | Chuyển request nhiều vùng có thể tăng chi phí băng thông và vận hành |
| **Sustainability** | Có nhân bản compute, cache hoặc truyền dữ liệu vượt nhu cầu không? | Chỉ phân tán thành phần thực sự cần giúp giảm tài nguyên và traffic vô ích |

Không có một chính sách định tuyến duy nhất tối ưu mọi trụ cột. Yêu cầu nghiệp vụ và ràng buộc dữ liệu là điều kiện bắt buộc; độ trễ và chi phí là đối tượng tối ưu trong tập phương án hợp lệ.

## 14. Các sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách cải thiện |
|---|---|---|
| Cho rằng DNS biết chính xác vị trí người dùng | Resolver, VPN và ECS gây sai số | Đo endpoint thực tế, xem vị trí chỉ là tín hiệu có sai số |
| Chọn region gần nhất cho mọi request | Giao dịch có thể phụ thuộc DB xa hoặc quy định dữ liệu | Phân loại read/write và policy tenant, đo end-to-end |
| Dùng Host hoặc path thay xác thực | Client có thể tự gửi Host/path tùy ý | Authentication/authorization, default deny và kiểm tra resource |
| Dùng một prefix /api quá rộng | Có thể khớp route không mong muốn | Xác minh segment, exact/prefix priority và normalization |
| Tin mọi X-Forwarded-For là IP thật | Client có thể giả mạo | Chỉ tin header từ trusted proxies |
| Chỉ kiểm tra /healthz là đủ cho booking | Backend có thể khỏe nhưng DB hoặc luồng nghiệp vụ hỏng | Health theo cấp, synthetic transaction và SLI đầu cuối |
| Coi TTL thấp là failover tức thời | DNS cache và kết nối còn tồn tại | Đo failover, thiết kế DR và chấp nhận giới hạn DNS |
| Multi-region nghĩa là ghi được từ mọi nơi | Replication không bảo đảm consistency hoặc quyền dữ liệu | Thiết kế nguồn có thẩm quyền, idempotency, failover được phép |
| CDN cache tất cả response /api | Có thể rò dữ liệu giữa các tài khoản | Cache policy theo nội dung, cache key và thử phân tách tenant |
| Route dự phòng qua bất kỳ region còn sống | Có thể vi phạm data residency và tạo lỗi nghiệp vụ | Giới hạn đích hợp lệ trước khi tối ưu availability |

## 15. Bài tập áp dụng

### Bài tập A – Host và path

Một gateway có hai luật: mọi request đến **api.example.com** gửi tới Legacy API; mọi request có path **/v2/orders/** gửi tới New API. Người quản trị nghĩ rằng **api.example.com/v2/orders/1** chắc chắn sẽ tới New API.

**Câu hỏi:** Có thể kết luận như vậy không?

**Gợi ý:** Chưa thể. Cần biết các luật được đặt tại cùng tầng hay nhiều tầng, độ ưu tiên và cách nền tảng so khớp hostname/path. Nên định nghĩa một virtual host cho **api.example.com**, sau đó tạo route path cụ thể trước default route, kèm kiểm thử đường dẫn và version.

### Bài tập B – Người dùng qua VPN

Khách hàng thuộc tenant có dữ liệu được phép ở region A nhưng đang dùng VPN có IP ở quốc gia B. DNS chọn edge B có RTT thấp, rồi gateway định gửi request ghi tới database B.

**Câu hỏi:** Rủi ro và cách xử lý?

**Gợi ý:** Vị trí IP không xác định nơi xử lý dữ liệu được phép. Edge B có thể là điểm nhận kết nối nếu chính sách cho phép, nhưng Booking phải xác thực tenant và gửi dữ liệu ghi tới region A hoặc một vùng dự phòng đã được phê duyệt. Kiểm tra thêm log, cache và backup.

### Bài tập C – Failover nhưng tạo giao dịch kép

Client POST đặt phòng tới region A. Region A commit booking nhưng kết nối bị mất trước phản hồi. DNS chuyển client sang region B, client POST lại và tạo booking thứ hai.

**Câu hỏi:** Thiết kế thiếu gì?

**Gợi ý:** Thiếu cơ chế nhận diện cùng một intent giao dịch và trạng thái nhất quán xuyên các đích có thể nhận yêu cầu. Cần idempotency key, nơi lưu và thời hạn hiệu lực phù hợp, truy vấn kết quả khi timeout, điều phối failover và chiến lược đối soát.

### Bài tập D – Độ trễ “gần nhất” không tốt nhất

Hai region đều healthy. Region A có RTT client→API nhỏ hơn B, nhưng backend A truy vấn DB ở region xa hơn. Người dùng vẫn thấy p95 giao dịch cao hơn.

**Câu hỏi:** Nên đo và thay đổi gì?

**Gợi ý:** Đo latency đầu cuối theo route/region, span backend→DB, cache hit, connection và tail latency. Có thể giữ compute gần dữ liệu có thẩm quyền cho thao tác ghi, thêm cache/read model cho truy vấn đọc phù hợp hoặc điều chỉnh chính sách route. Không tối ưu dựa duy nhất vào RTT edge.

## 16. Checklist trước khi đưa định tuyến vào production

- [ ] Mỗi hostname công khai có chứng chỉ, owner, default route và chính sách TLS rõ ràng.
- [ ] Host/path/method được khớp theo thứ tự xác định; đã kiểm thử exact, prefix, slash, encoding, rewrite và route không hợp lệ.
- [ ] Chỉ trusted proxy được cung cấp forwarded header dùng cho quyết định an ninh.
- [ ] API và admin endpoint có authentication, authorization theo tenant/tài nguyên và rate limiting phù hợp.
- [ ] Đã phân biệt route theo vị trí, latency, health, trọng số và stateful routing.
- [ ] Đã xác minh origin, log, cache, replica, backup và đối tác bên ngoài phù hợp chính sách dữ liệu.
- [ ] Read/write và luồng giao dịch có quy tắc consistency, session, idempotency và retry/failover cụ thể.
- [ ] Có metric p50/p95/p99, tỷ lệ lỗi, SLI nghiệp vụ, health và capacity theo route/region.
- [ ] Có test từ nhiều khu vực, diễn tập region unhealthy, DNS cache và phương án phục hồi được đo.
- [ ] Đã tính chi phí edge/CDN, global routing, gateway, egress, replica, observability và vận hành.
- [ ] Route và policy được quản lý bằng cấu hình có version, review, rollout và rollback.
- [ ] Sơ đồ luồng request, ranh giới bảo mật, runbook và chủ sở hữu route phản ánh hệ thống thực tế.

**Điểm cần nhớ:** host routing chọn **ứng dụng theo tên miền**; path routing chọn **chức năng theo URL**; geographic routing dùng **vị trí suy ra hoặc quy tắc lãnh thổ**; latency routing ưu tiên **đường tới đích dự kiến nhanh hơn**. Kiến trúc cloud đáng tin cậy kết hợp chúng với kiểm tra quyền, sức khỏe, nguồn dữ liệu có thẩm quyền, phạm vi địa lý được phép và đo lường trải nghiệm đầu cuối.
