# Định tuyến HTTP với Azure Application Gateway

Một ứng dụng có thể gồm nhiều thành phần cùng phục vụ người dùng: trang web, API, trang quản trị và dịch vụ lưu trữ nội dung tĩnh. Nếu đưa mỗi thành phần lên Internet qua một địa chỉ riêng, nhóm vận hành sẽ phải quản lý nhiều điểm truy cập, chứng chỉ, quy tắc bảo mật và cấu hình giám sát. **Azure Application Gateway** cho phép đặt một điểm tiếp nhận HTTP/HTTPS ở phía trước rồi chuyển yêu cầu đến đúng backend theo **hostname**, **đường dẫn URL** và các quy tắc đã cấu hình.

Application Gateway là bộ cân bằng tải **Layer 7 (lớp ứng dụng)** của Microsoft Azure. Nó có thể kiểm tra nội dung cần thiết trong yêu cầu HTTP, kết thúc phiên TLS tại gateway, phân phối yêu cầu giữa các backend khỏe mạnh và, khi dùng WAF, áp dụng các quy tắc bảo vệ ứng dụng web. Để sử dụng hiệu quả, cần hiểu listener, request routing rule, URL path map, backend pool, backend settings và health probe phối hợp với nhau như thế nào.

Bài học này thuộc chương **Cân bằng tải và phân phối ứng dụng** trong lộ trình Azure: từ subscription và resource group đến mạng ảo, dịch vụ tính toán, dữ liệu, giám sát, bảo mật và quản lý chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt Application Gateway với Azure Load Balancer và Azure Front Door.
2. Mô tả luồng một yêu cầu HTTP/HTTPS đi qua Application Gateway.
3. Giải thích listener, backend pool, backend settings, health probe và routing rule.
4. Thiết kế định tuyến theo hostname và URL path, gồm tuyến mặc định.
5. Hiểu cách kết hợp TLS, WAF, DNS, mạng riêng và tính sẵn sàng.
6. Thực hiện cấu hình mẫu trên Azure portal và kiểm tra bằng Azure CLI, curl.
7. Chẩn đoán các trường hợp 502, 403, định tuyến sai backend và backend unhealthy.

## 1. Application Gateway giải quyết vấn đề gì?

Giả sử một hệ thống bán hàng có:

- Giao diện khách hàng ở **shop.example.com**.
- API xử lý đơn hàng ở **shop.example.com/api/**.
- Giao diện quản trị ở **admin.example.com**.
- Nhiều instance web và API để tránh phụ thuộc một máy chủ.

Nhóm muốn người dùng chỉ truy cập HTTPS ở một điểm vào, nhưng yêu cầu phải được đưa đúng dịch vụ. Application Gateway cho phép định tuyến:

| Yêu cầu từ client | Cách khớp | Backend đích |
|---|---|---|
| https://shop.example.com/ | Host shop + tuyến mặc định | Nhóm máy chủ web |
| https://shop.example.com/products/15 | Host shop + tuyến mặc định | Nhóm máy chủ web |
| https://shop.example.com/api/orders | Host shop + path /api/* | Nhóm API |
| https://admin.example.com/ | Host admin | Nhóm ứng dụng quản trị |

Đó là điểm khác biệt quan trọng với cân bằng tải chỉ dựa trên IP và cổng: Application Gateway có thể định tuyến theo thông tin **HTTP Host** và **URL path**, rồi chọn một backend phù hợp trong pool.

### So sánh các dịch vụ phân phối lưu lượng

| Dịch vụ | Lớp giao thức và phạm vi | Ví dụ phù hợp |
|---|---|---|
| **Azure Load Balancer** | Layer 4, TCP/UDP, cân bằng tải theo IP/cổng | Cân bằng kết nối TCP tới VM hoặc dịch vụ nội bộ |
| **Azure Application Gateway** | Layer 7, HTTP/HTTPS, gateway theo region và VNet | Định tuyến /api/*, nhiều hostname, TLS và WAF ở frontend |
| **Azure Front Door** | Layer 7, điểm vào toàn cầu tại mạng biên Microsoft | Ứng dụng nhiều region, chọn origin theo định tuyến toàn cầu và tăng tốc phân phối |

Có thể kết hợp dịch vụ. Ví dụ, Front Door xử lý người dùng toàn cầu rồi chuyển tới Application Gateway theo region. Lựa chọn phụ thuộc kiến trúc, phạm vi địa lý, yêu cầu bảo mật, tính năng và chi phí; Application Gateway không tự động thay thế mọi vai trò của Load Balancer hoặc Front Door.

## 2. Cách một yêu cầu được xử lý

Luồng logic:

~~~text
Client: https://shop.example.com/api/orders
                   |
                   v
DNS: shop.example.com -> Public IP của Application Gateway
                   |
                   v
Frontend IP + cổng 443
                   |
                   v
HTTPS listener (hostname + chứng chỉ)
                   |
                   v
Request routing rule (độ ưu tiên)
                   |
                   v
URL path map: /api/*  -> API backend pool
              default -> Web backend pool
                   |
                   v
Backend settings (HTTP/HTTPS, cổng, host, timeout, ...)
                   |
                   v
Health probe -> chỉ chọn backend khỏe mạnh
                   |
                   v
API backend: 10.44.2.10:8080
~~~

Đối với gateway có WAF, yêu cầu còn được kiểm tra theo WAF policy áp dụng tại phạm vi phù hợp. WAF có thể ghi log hoặc chặn yêu cầu trước khi nó tới backend, tùy rule, chế độ và chính sách đang dùng.

Một số điểm cần nhớ:

- **DNS** giúp client tìm được IP hoặc tên frontend; nó không quyết định backend web hay API.
- **Listener** xác định gateway chấp nhận yêu cầu nào, ví dụ HTTPS trên cổng 443 cho hostname cụ thể.
- **Routing rule** gắn listener với hành động định tuyến hoặc chuyển hướng.
- **Path map** chọn backend theo đường dẫn khi rule thuộc loại path-based.
- **Backend settings** xác định cách gateway giao tiếp tới backend.
- **Health probe** quyết định backend nào đủ điều kiện nhận lưu lượng.

Application Gateway là một **reverse proxy**: client tạo kết nối tới gateway; gateway tạo kết nối riêng tới backend được chọn. Vì vậy, phải kiểm tra cả đường client → gateway và đường gateway → backend.

## 3. Các thành phần cấu hình cốt lõi

### 3.1. Frontend IP và frontend port

**Frontend IP** là địa chỉ mà client dùng để tiếp cận gateway. Tùy SKU và kiểu triển khai được hỗ trợ, gateway có thể dùng frontend công cộng, riêng hoặc kết hợp theo kiến trúc. Frontend công cộng thường gắn với **Public IP** của Azure; frontend riêng dùng một IP từ subnet của gateway.

**Frontend port** là cổng mở trên gateway, thường là 80 cho HTTP hoặc 443 cho HTTPS. Tạo frontend IP/cổng chưa đủ để ứng dụng hoạt động: còn cần listener và rule gắn với backend.

### 3.2. Listener

**HTTP listener** định nghĩa cách gateway nhận yêu cầu vào:

- Protocol: HTTP hoặc HTTPS.
- Frontend IP và cổng.
- Hostname hoặc tập hostname áp dụng, khi cấu hình multi-site listener.
- Chứng chỉ TLS nếu listener dùng HTTPS.

Hai mô hình thường gặp:

- **Basic listener:** nhận yêu cầu trên frontend/cổng theo cấu hình, không giới hạn vào một hostname cụ thể theo kiểu multi-site.
- **Multi-site listener:** khớp hostname như **shop.example.com** hoặc **admin.example.com**, phù hợp khi một gateway phục vụ nhiều site; các tùy chọn wildcard hostname phụ thuộc khả năng hỗ trợ và quy tắc cấu hình.

Với HTTPS nhiều hostname, cần chứng chỉ tương ứng và cấu hình SNI/hostname đúng theo kiểu listener. Nếu hostname không khớp, gateway có thể không chọn listener bạn mong đợi.

### 3.3. Backend pool

**Backend pool** là tập hợp endpoint có thể nhận yêu cầu, chẳng hạn:

- Private IP của VM hoặc VM Scale Sets.
- Địa chỉ IP hoặc FQDN của dịch vụ chạy trong VNet hoặc mạng có kết nối hợp lệ.
- FQDN của một dịch vụ PaaS như Azure App Service khi kiến trúc hỗ trợ.

Pool có thể có nhiều backend để cân bằng tải. Việc tạo pool không có nghĩa mọi endpoint đều nhận lưu lượng; gateway dùng kết quả health probe để chọn backend được xem là khỏe mạnh.

Ví dụ:

~~~text
pool-web
  - 10.44.1.10
  - 10.44.1.11

pool-api
  - 10.44.2.10
  - 10.44.2.11
~~~

Backend có thể được khai báo bằng FQDN khi IP có thể thay đổi; gateway cần phân giải DNS đúng và có tuyến mạng tới endpoint được chỉ định.

### 3.4. Backend HTTP settings

**Backend settings** (có giao diện hoặc API gọi là *HTTP settings*) quy định gateway kết nối tới backend như thế nào:

| Thuộc tính | Vai trò |
|---|---|
| Protocol | HTTP hoặc HTTPS giữa gateway và backend |
| Port | Cổng backend lắng nghe, ví dụ 8080 hoặc 443 |
| Host name | Host header gửi đến backend; có thể cần override theo backend |
| Request timeout | Thời gian gateway chờ phản hồi theo thiết lập |
| Cookie-based affinity | Tùy chọn duy trì affinity cho phiên khi ứng dụng cần |
| Connection draining | Hỗ trợ chờ kết nối hiện có khi thay đổi backend theo khả năng dịch vụ |
| Custom probe | Liên kết cấu hình health probe dành cho backend |
| Path override | Tùy chọn xử lý đường dẫn backend, cần kiểm thử kỹ khi sử dụng |

Phải phân biệt **backend pool** (đi tới máy/dịch vụ nào) với **backend settings** (giao tiếp bằng giao thức, host và cổng nào).

Ví dụ, backend API chạy HTTP tại **10.44.2.10:8080**. Pool chỉ định IP; settings phải chỉ định HTTP cổng 8080. Nếu settings chọn HTTPS cổng 443 trong khi API không phục vụ TLS tại đó, health probe và yêu cầu thực tế có thể thất bại.

### 3.5. Health probe

**Health probe** là kiểm tra định kỳ gateway gửi tới backend để xác định endpoint có thể phục vụ lưu lượng không. Có probe mặc định và probe tùy chỉnh. Với ứng dụng thực tế, probe tùy chỉnh thường có giá trị hơn vì bạn chọn được:

- Protocol HTTP/HTTPS.
- Hostname và cổng phù hợp với backend.
- Path, chẳng hạn **/healthz** hoặc **/api/health**.
- Khoảng kiểm tra, timeout, ngưỡng lỗi và tiêu chí chấp nhận kết quả theo tính năng.

Ví dụ API:

~~~http
GET /healthz HTTP/1.1
Host: api.internal.example.com
~~~

Nếu API trả kết quả phù hợp với tiêu chí probe, endpoint được xem là healthy. Nếu probe thất bại, gateway có thể ngừng gửi yêu cầu đến backend đó. Một health endpoint nên phản ánh trạng thái sẵn sàng phục vụ yêu cầu chính mà không thực hiện thao tác nặng hoặc làm thay đổi dữ liệu.

**Sai Host header, path, chứng chỉ hoặc cổng có thể làm probe unhealthy dù ứng dụng vẫn chạy.** Đây là một trong những nguyên nhân thường gặp của lỗi 502.

### 3.6. Request routing rule

**Request routing rule** nối listener với backend hoặc hành động routing. Hai kiểu chính:

1. **Basic rule:** listener chuyển yêu cầu tới một backend pool với backend settings đã chọn.
2. **Path-based rule:** listener dùng một **URL path map** để chọn backend pool/settings theo đường dẫn URL; có tuyến mặc định cho các path không khớp.

Với Application Gateway v2, hãy đặt **priority** rõ ràng cho các request routing rule. Quy tắc có số priority nhỏ hơn được ưu tiên cao hơn khi các điều kiện khớp cạnh tranh. Bên trong path map, thứ tự các path rule cũng cần được thiết kế cẩn thận khi pattern chồng lấn.

## 4. Định tuyến theo hostname (multi-site)

Một Application Gateway có thể tiếp nhận nhiều website trên cùng frontend và cổng.

Ví dụ:

| Host client gửi | Listener | Rule | Backend |
|---|---|---|---|
| shop.example.com | listener-shop-https | rule-shop, priority 100 | pool-web hoặc path map |
| admin.example.com | listener-admin-https | rule-admin, priority 200 | pool-admin |

Để cấu hình:

1. DNS của hai hostname phải trỏ tới frontend thích hợp.
2. Tạo listener HTTPS cho mỗi hostname và cấu hình chứng chỉ hợp lệ.
3. Tạo backend pool/settings cho từng ứng dụng.
4. Tạo rule gắn listener với backend hoặc URL path map.
5. Kiểm tra Host header, SNI, backend health và request thực tế.

Trong trình duyệt, người dùng truy cập **https://admin.example.com**. Gateway nhận kết nối TLS, xác định listener cho hostname này rồi chuyển tới **pool-admin** nếu rule và backend có trạng thái phù hợp.

Nếu cả hai hostname cùng trỏ về Public IP nhưng bạn chỉ tạo listener cho **shop.example.com**, không nên giả định **admin.example.com** sẽ tự hoạt động. DNS chỉ giải quyết phần tìm frontend.

## 5. Định tuyến theo đường dẫn URL (path-based)

Path-based routing giúp tách các chức năng của cùng một tên miền thành những backend riêng.

Giả sử listener cho **shop.example.com** dùng:

| Path pattern | Backend pool | Backend settings |
|---|---|---|
| `/api/*` | pool-api | settings-api |
| `/assets/*` | pool-static | settings-static |
| Mặc định | pool-web | settings-web |

Khi truy cập:

- **/api/orders** → pool-api.
- **/assets/logo.svg** → pool-static.
- **/products/15** → pool-web theo tuyến mặc định.

### Cách hiểu path map

Một URL path map bao gồm các **path rule** và một **default backend**. Gateway so khớp đường dẫn theo các pattern được hỗ trợ rồi chọn backend tương ứng. Các pattern chồng lấn có thể khiến kết quả không như mong muốn nếu thứ tự và mức cụ thể không được thiết kế đúng.

Ví dụ có cả:

~~~text
/api/admin/*
/api/*
~~~

Hãy đặt pattern cụ thể `/api/admin/*` trước pattern rộng `/api/*` trong path map và kiểm thử thực tế. Nếu không, yêu cầu quản trị có thể đi vào backend API chung.

Tuyến mặc định rất quan trọng. Nếu không khớp các path rule, request sẽ theo default backend của URL path map; đừng mặc định gateway sẽ tự trả 404. Nếu muốn trả 404 cho một nhóm path, hãy thiết kế backend hoặc cơ chế xử lý có hành vi đó.

### Đường dẫn được giữ hay đổi?

**Định tuyến theo path không đồng nghĩa xóa tiền tố path.** Ví dụ **/api/orders** thường vẫn được gửi tới backend dưới dạng đường dẫn tương ứng, trừ khi bạn cấu hình override/rewrite thích hợp. Nếu API backend chỉ phục vụ **/orders**, cần xử lý tiền tố **/api** bằng cấu hình phù hợp hoặc sửa ứng dụng.

Application Gateway cũng hỗ trợ một số chức năng **URL rewrite** và **redirect**. Rewrite thay đổi thông tin yêu cầu/phản hồi theo điều kiện được hỗ trợ; redirect trả phản hồi chuyển hướng cho client, ví dụ HTTP sang HTTPS. Đây là hai hành vi khác nhau và cần kiểm thử riêng.

### Định tuyến host + path cùng lúc

Có thể kết hợp:

~~~text
HTTPS listener: shop.example.com
  rule-shop, priority 100
    /api/*       -> pool-api
    /assets/*    -> pool-static
    default      -> pool-web

HTTPS listener: admin.example.com
  rule-admin, priority 200
    default      -> pool-admin
~~~

Mục tiêu là tổ chức rõ ràng điểm vào và backend. Một rule quá rộng có thể nhận request không mong muốn; một rule quá hẹp có thể bỏ qua URL cần thiết. Nên có bộ test cho từng hostname, path, redirect và tình huống không khớp.

## 6. HTTPS: kết thúc TLS tại gateway hay mã hóa tới backend?

Application Gateway có thể tiếp nhận HTTPS từ client và quản lý kết nối tới backend theo backend settings.

### TLS termination tại frontend

Client thiết lập HTTPS với gateway. Gateway giải mã lưu lượng để thực hiện định tuyến Layer 7 và áp dụng tính năng có liên quan. Sau đó gateway kết nối tới backend bằng giao thức được cấu hình:

~~~text
Client --HTTPS--> Application Gateway --HTTP--> Backend
~~~

Mô hình này đơn giản khi backend nằm trong mạng tin cậy theo chính sách, nhưng đoạn gateway → backend dùng HTTP **không được mã hóa bằng TLS**. Cần đánh giá yêu cầu bảo mật dữ liệu trước khi chọn.

### End-to-end TLS

Gateway vẫn kết thúc phiên TLS phía client để xử lý yêu cầu, rồi tạo **một phiên HTTPS khác** tới backend:

~~~text
Client --HTTPS--> Application Gateway --HTTPS--> Backend
       TLS #1                          TLS #2
~~~

Với backend HTTPS, cần bảo đảm:

- Backend thực sự nghe ở cổng HTTPS đã cấu hình.
- Chứng chỉ backend còn hạn, tên chứng chỉ khớp hostname phù hợp và chuỗi tin cậy được xác minh.
- Nếu dùng CA nội bộ hoặc self-signed, cần cấu hình trusted root certificate theo khả năng và yêu cầu của gateway.
- Host header và Server Name Indication (**SNI**) phù hợp với backend.
- Health probe cũng dùng protocol, host và path tương thích.

Ví dụ backend là Azure App Service với endpoint HTTPS yêu cầu Host header theo domain riêng. Nếu gateway gửi Host header là một private IP hoặc hostname không khớp, backend có thể trả mã lỗi, probe thất bại hoặc việc kiểm tra chứng chỉ không thành công. Cần lựa chọn backend FQDN, hostname override và chứng chỉ đồng bộ với nhau.

### Chứng chỉ và vòng đời

Chứng chỉ frontend được gắn vào HTTPS listener. Có thể quản lý chứng chỉ trực tiếp hoặc tích hợp Azure Key Vault khi tính năng/SKU phù hợp, theo yêu cầu danh tính và quyền truy cập. Nhóm vận hành phải theo dõi ngày hết hạn, kế hoạch gia hạn và kiểm tra cấu hình sau khi thay chứng chỉ.

Nếu cần HTTP → HTTPS, tạo listener/rule hoặc cấu hình redirect phù hợp. Việc đặt listener HTTPS không tự tạo redirect từ cổng 80.

## 7. Web Application Firewall (WAF)

**Application Gateway WAF_v2** bổ sung tường lửa ứng dụng web cho những mô hình triển khai hỗ trợ. WAF giúp kiểm tra yêu cầu HTTP(S) dựa trên tập quy tắc và WAF policy, nhằm giảm rủi ro từ các kiểu tấn công web thường gặp.

Hai chế độ thường gặp:

- **Detection:** đánh giá và ghi nhận yêu cầu phù hợp quy tắc, phục vụ quan sát và điều chỉnh.
- **Prevention:** có thể chặn yêu cầu bị đánh giá vi phạm policy.

WAF không thay thế việc sửa lỗi ứng dụng, xác thực, phân quyền, quản lý bí mật hoặc bảo mật cơ sở dữ liệu. Một request hợp lệ vẫn phải được backend xác thực. Một request bị WAF chặn có thể trả **403** ngay tại gateway, khác với **502** do backend không khỏe mạnh.

Khi bật WAF cho ứng dụng đang hoạt động, nên kiểm thử các đường dẫn, payload hợp lệ và tích hợp của ứng dụng để tránh false positive. Xem WAF logs, rule ID, request ID và policy áp dụng trước khi loại trừ hoặc điều chỉnh rule. Không tắt toàn bộ WAF chỉ vì một endpoint gặp lỗi.

## 8. Mạng, subnet, DNS và khả năng truy cập backend

Application Gateway là tài nguyên được triển khai trong **Azure Virtual Network** và sử dụng subnet dành riêng cho gateway theo yêu cầu dịch vụ.

### Subnet dành riêng

Trong ví dụ:

~~~text
VNet: vnet-sales          10.44.0.0/16
  snet-appgw              10.44.0.0/24
  snet-web                10.44.1.0/24
  snet-api                10.44.2.0/24
~~~

Subnet **snet-appgw** dành riêng cho Application Gateway, không chứa VM hoặc tài nguyên ứng dụng thông thường. Với thế hệ v2, một subnet **/24** thường được khuyến nghị cho khả năng mở rộng, dù kích thước tối thiểu còn phụ thuộc SKU và thiết kế. Khi tạo hoặc thay đổi subnet, hãy kiểm tra tài liệu hiện hành và số instance dự kiến.

Không tự áp NSG hoặc UDR chặn lưu lượng hạ tầng/control-plane mà Application Gateway cần. Nếu thêm NSG, route table hay firewall vào đường đi, phải tuân thủ các yêu cầu riêng của Application Gateway về lưu lượng quản trị và lưu lượng tới backend.

### Đường kết nối tới backend

Backend có thể nằm trong cùng VNet, VNet peered hoặc mạng có kết nối hợp lệ khác, miễn gateway phân giải và định tuyến tới được theo kiến trúc được hỗ trợ. Với backend nội bộ, cần kiểm tra:

1. CIDR không chồng lấn trên các mạng cần kết nối.
2. Effective routes từ subnet gateway tới backend.
3. NSG và firewall cho phép cổng backend, cả luồng probe và lưu lượng yêu cầu.
4. Backend đang lắng nghe trên IP/cổng tương ứng.
5. DNS trả về IP đúng nếu pool dùng FQDN.

Ứng dụng PaaS không luôn hoạt động giống VM trong subnet. Ví dụ, App Service có yêu cầu hostname, TLS và tích hợp mạng riêng riêng. Khi dùng Private Endpoint hoặc cơ chế mạng khác, phải tuân thủ cấu hình được hỗ trợ của từng dịch vụ.

### Public DNS và private DNS

DNS công cộng có thể đưa **shop.example.com** tới frontend Public IP. Khi pool dùng một backend FQDN nội bộ, DNS phía gateway cần phân giải được tên đó thành địa chỉ có thể kết nối. DNS client → gateway và DNS gateway → backend là **hai bước độc lập**.

Nếu hệ thống dùng Private DNS Zone, custom DNS server hoặc Azure DNS Private Resolver, cần xác minh kết quả phân giải từ phía thích hợp. Việc sửa bản ghi public DNS không tự sửa lỗi backend FQDN nội bộ.

## 9. Tính sẵn sàng, hiệu năng và giới hạn

Với Application Gateway **Standard_v2** hoặc **WAF_v2**, có những khả năng như autoscaling và triển khai theo availability zone ở các region/tổ hợp tính năng được hỗ trợ. Khi thiết kế production:

- Chọn SKU theo nhu cầu WAF, quy mô và tính năng.
- Cấu hình autoscaling/minimum instances theo mức tải và yêu cầu sẵn sàng.
- Đặt backend ở nhiều instance, zone hoặc cụm khi phù hợp.
- Thiết lập health probe phản ánh khả năng xử lý thực tế.
- Dùng session affinity chỉ khi ứng dụng yêu cầu; ưu tiên thiết kế ứng dụng stateless khi có thể.
- Giám sát latency, số lượng request, status code, kết nối backend và độ khỏe của các instance.

Gateway là thành phần **regional**. Nó không tự cung cấp failover giữa hai Azure region. Nếu ứng dụng cần khôi phục khi mất cả region, cần thiết kế thêm cơ chế định tuyến toàn cầu, bản sao ứng dụng và dữ liệu ở region khác.

Ứng dụng phải chịu được yêu cầu thất bại hoặc bị thử lại. Health probe giúp tránh backend hỏng nhưng không thay thế thiết kế retry idempotent, timeout hợp lý và chiến lược triển khai không gián đoạn.

## 10. Thực hành: cấu hình định tuyến HTTP trên Azure portal

Tình huống thực hành: một ứng dụng bán hàng chạy hai backend web và hai backend API. Mục tiêu:

- Người dùng truy cập **https://shop.example.com** qua Application Gateway.
- Request `/api/*` chuyển tới pool API.
- Những path khác chuyển tới pool web.
- Backend không khỏe mạnh không nhận request mới theo kết quả probe.

Các tên, IP và domain dưới đây là **giả định để học**, không trỏ tới tài nguyên đã tồn tại. Chỉ triển khai trong subscription được cấp quyền, sau khi xác nhận ngân sách vì Application Gateway và Public IP có thể phát sinh phí.

### Bước 1: chuẩn bị môi trường mạng

Chuẩn bị một VNet, ví dụ **vnet-sales (10.44.0.0/16)**, cùng subnet dành riêng **snet-appgw (10.44.0.0/24)** và các subnet web/API. Triển khai backend hoặc chuẩn bị backend FQDN/IP có thể kết nối từ subnet gateway.

Trước khi tạo gateway, cần xác nhận:

- Có đúng subscription, resource group và region.
- Subnet gateway không dùng chung cho VM.
- Subnet có số IP đủ cho instance và tăng trưởng.
- NSG, UDR và DNS đáp ứng yêu cầu của Application Gateway.
- Backend trả về HTTP/HTTPS và có health endpoint.

### Bước 2: tạo Application Gateway

Trong **Azure portal**, tìm **Application Gateways** rồi chọn tạo tài nguyên. Chọn:

1. Resource group và region.
2. SKU **Standard_v2** cho định tuyến ứng dụng hoặc **WAF_v2** nếu cần WAF.
3. VNet và subnet dành riêng đã chuẩn bị.
4. Frontend công cộng hoặc riêng theo kiến trúc được hỗ trợ.
5. Public IP Standard nếu dùng frontend công cộng và portal yêu cầu.

Cấu hình instance, zone và các lựa chọn bổ sung theo yêu cầu. Không nên bật mọi tính năng chỉ vì chúng hiển thị trong màn hình.

### Bước 3: cấu hình backend pools

Tạo:

| Pool | Thành viên ví dụ |
|---|---|
| **pool-web** | 10.44.1.10, 10.44.1.11 |
| **pool-api** | 10.44.2.10, 10.44.2.11 |

Các IP giả định phải được thay bằng IP hoặc FQDN của tài nguyên thật. Không thêm endpoint không thuộc quyền quản trị hoặc không có đường mạng hợp lệ.

### Bước 4: cấu hình backend settings và probes

Ví dụ:

| Settings | Protocol/port | Probe | Backend |
|---|---|---|---|
| **settings-web** | HTTP / 8080 | GET /healthz | pool-web |
| **settings-api** | HTTP / 8080 | GET /healthz | pool-api |

Đặt hostname, timeout và lựa chọn SSL/TLS theo cấu hình thực của backend. Nếu backend dùng HTTPS, thay bằng HTTPS và kiểm tra chứng chỉ, trusted root khi cần.

Đảm bảo **/healthz** thực sự tồn tại và trả mã trạng thái phù hợp. Có thể tạo custom probes riêng cho web và API nếu mỗi ứng dụng dùng hostname/path khác.

### Bước 5: tạo listener

Tạo HTTPS listener:

~~~text
Name: listener-shop
Frontend: public frontend
Port: 443
Hostname: shop.example.com
TLS certificate: chứng chỉ hợp lệ cho shop.example.com
~~~

Đồng thời cấu hình DNS để hostname đi tới frontend thật. Nếu chưa có domain/chứng chỉ hợp lệ, có thể minh họa định tuyến bằng HTTP trong môi trường thử nghiệm cách ly, sau đó chuyển sang HTTPS trước khi dùng production.

### Bước 6: tạo URL path map và rule

Ví dụ cấu hình logic:

~~~text
URL path map: map-shop
    /api/*  -> pool-api, settings-api
    default -> pool-web, settings-web

Request routing rule: rule-shop
    listener: listener-shop
    type: path-based
    URL path map: map-shop
    priority: 100
~~~

Tại màn hình rule hoặc path map, kiểm tra cặp backend pool/backend settings cho từng đường dẫn. Nếu có redirect hoặc rewrite, ghi rõ hành vi mong đợi; đừng thêm tùy chọn này chỉ để đổi backend.

### Bước 7: xác minh backend health

Mở phần **Backend health** của Application Gateway. Kiểm tra từng thành viên trong **pool-web** và **pool-api**:

- Healthy: probe thành công theo điều kiện đặt ra.
- Unhealthy: cần xem mã HTTP, timeout, chứng chỉ, hostname, cổng, mạng hoặc cấu hình backend.
- Unknown/không xác định: cần kiểm tra trạng thái provisioning và các điều kiện thu thập/quan sát liên quan.

Chưa nên kiểm thử từ người dùng thật khi tất cả backend đều unhealthy. Trước hết hãy sửa nguyên nhân probe thất bại.

### Bước 8: kiểm thử định tuyến và điều kiện biên

Sau khi DNS, listener, rule và backend sẵn sàng:

| Thử nghiệm | Kỳ vọng |
|---|---|
| GET / | Pool web trả trang chủ |
| GET /products/15 | Pool web xử lý |
| GET /api/orders | Pool API xử lý |
| GET /api/healthz | Pool API xử lý theo path backend thực tế |
| GET /unknown | Đi tới default pool web, nơi backend quyết định trả 404 hay nội dung khác |
| Hostname khác | Không nhận cấu hình route cho shop nếu không có listener/rule phù hợp |
| Một API instance unhealthy | Request mới được phân phối tới instance còn healthy, nếu pool còn backend khỏe |

Nếu chỉ có một backend healthy, tính chịu lỗi của pool vẫn còn hạn chế. Nên đánh giá thêm đường dữ liệu, session affinity và hành vi khi backend phục hồi.

## 11. Kiểm tra bằng Azure CLI và curl

Các lệnh CLI dưới đây là **read-only** để quan sát một gateway đã có. Không chạy lệnh tạo gateway hoặc sửa routing trên tài nguyên production chỉ để thực hành.

### Chọn subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az account show \
  --query "{name:name,id:id}" \
  --output table
~~~

### Liệt kê và xem gateway

~~~bash
az network application-gateway list \
  --resource-group "rg-sales-network" \
  --output table

az network application-gateway show \
  --resource-group "rg-sales-network" \
  --name "agw-sales-prod" \
  --query "{name:name,sku:sku.name,state:provisioningState,location:location}" \
  --output json
~~~

### Xem backend health

~~~bash
az network application-gateway show-backend-health \
  --resource-group "rg-sales-network" \
  --name "agw-sales-prod" \
  --output json
~~~

Kiểm tra backend pool, địa chỉ thành viên, trạng thái health và chi tiết lỗi nếu công cụ trả về. Một backend unhealthy có thể do chính ứng dụng, do probe hoặc do đường kết nối mạng.

### Kiểm tra Host + path mà chưa đổi DNS công cộng

Ví dụ sau dùng cờ **--resolve** của curl để gửi request HTTPS tới một IP gateway cụ thể nhưng vẫn sử dụng hostname **shop.example.com** cho Host/SNI:

~~~bash
curl -v \
  --resolve shop.example.com:443:<APPLICATION_GATEWAY_PUBLIC_IP> \
  https://shop.example.com/api/orders
~~~

Thay placeholder bằng Public IP thật và dùng một domain/chứng chỉ bạn kiểm soát. Vì **shop.example.com** chỉ là tên minh họa, không chạy nguyên xi trên Internet. Tránh dùng tùy chọn bỏ qua kiểm tra chứng chỉ trong bài kiểm thử production.

Lệnh kiểm tra khác:

~~~bash
curl -v https://shop.example.com/
curl -v https://shop.example.com/api/healthz
~~~

Nếu backend có endpoint ghi lại hostname hoặc tên instance để kiểm tra, bạn có thể xác định pool nào xử lý request. Khi thử nhiều lần, hãy lưu ý session affinity có thể ảnh hưởng việc request được chuyển tới instance nào.

## 12. Quan sát, ghi log và xử lý lỗi

Application Gateway có thể cung cấp metrics, access logs, firewall logs khi dùng WAF, và trạng thái backend health. Việc lưu log/metric vào Log Analytics hoặc đích khác cần được cấu hình theo dịch vụ Azure Monitor và diagnostic settings phù hợp.

### Những dấu hiệu cần theo dõi

- Tổng số request và tỉ lệ mã phản hồi **2xx, 3xx, 4xx, 5xx**.
- Backend health, số backend healthy/unhealthy.
- Thời gian phản hồi và độ trễ backend.
- Lưu lượng theo listener, rule, hostname hoặc backend theo dữ liệu hiện có.
- WAF block/detection logs và rule đang được kích hoạt.
- Dung lượng/khả năng xử lý, autoscaling và hiệu quả phân phối yêu cầu.

### Bảng xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| **502 Bad Gateway** | Backend unhealthy; sai probe; backend trả phản hồi không hợp lệ; lỗi TLS hoặc kết nối | Mở Backend health, kiểm tra DNS, port, probe path, Host/SNI, cert và NSG/UDR |
| **403 Forbidden** | WAF ở chế độ Prevention chặn, hoặc backend trả 403 | Đối chiếu access/WAF logs và response source, xem rule ID hoặc quyền backend |
| **404 Not Found** | Request tới sai pool/path hoặc backend trả 404 | Kiểm tra path rule, default route, path backend thực nhận và access log |
| **TLS/certificate error** | Chứng chỉ frontend không hợp hostname, hết hạn, hoặc backend TLS không được tin cậy | Kiểm tra chứng chỉ listener, hostname, SNI và trusted root của backend |
| **Host đúng nhưng vào sai website** | Listener/rule ưu tiên hoặc multi-site hostname cấu hình chưa đúng | Kiểm tra Host header, listener hostnames, priority, và DNS |
| **Đường dẫn `/api/*` vào frontend web** | Path map thiếu rule, pattern/priority bị chồng lấn | Xem thứ tự path rules và default backend |
| **Chỉ một số instance lỗi** | Probe khác nhau, backend không đồng nhất, session affinity hoặc lỗi mạng | Xem từng backend health, thử từng instance và kiểm tra deployment |
| **Gateway không tới được backend** | NSG, route, DNS, Private Endpoint hoặc firewall | Kiểm tra đường đi gateway → backend, effective routes và cổng |
| **Gateway hoạt động nhưng Internet không tới được** | DNS, Public IP, frontend listener/cổng hoặc mạng client | Xem public DNS, listener, IP/cổng và kết nối từ ngoài |
| **Thay đổi rule chưa phản ánh ngay** | Cấu hình đang provisioning, DNS cache hoặc thay đổi ngoài gateway | Xác nhận provisioning state, đối chiếu cấu hình, thử Host/IP chính xác |

### Phân biệt mã lỗi theo nơi phát sinh

Một mã **502** từ gateway gợi ý gateway chưa giao tiếp thành công với backend theo yêu cầu. Một mã **404** có thể hoàn toàn do backend trả về vì đường dẫn không tồn tại; không có nghĩa gateway luôn định tuyến sai. Một mã **403** có thể đến từ WAF hoặc chính ứng dụng. Muốn kết luận, cần dùng log, request ID, backend health và kết quả kiểm tra từng tầng.

Không nên sửa lỗi bằng cách tắt NSG, bỏ xác thực hoặc tắt toàn bộ WAF. Xác định rule/cổng/host cụ thể đang gây vấn đề rồi điều chỉnh theo nguyên tắc quyền tối thiểu.

## 13. Bảo mật và quản trị khi đưa vào production

Một gateway phục vụ nhiều ứng dụng trở thành thành phần quan trọng trong kiến trúc. Khi thiết kế production:

1. **Giới hạn bề mặt công cộng:** chỉ mở listener và hostname thực sự cần thiết; backend nhạy cảm dùng mạng riêng khi phù hợp.
2. **Dùng HTTPS và quản lý chứng chỉ:** theo dõi vòng đời cert, giới hạn giao thức và cipher theo khả năng dịch vụ và chính sách.
3. **Bảo vệ tới backend:** cân nhắc HTTPS end-to-end, cấu hình host/SNI chuẩn và kiểm tra CA.
4. **Thiết lập WAF khi cần:** dùng policy, kiểm tra false positive và logs; không cho rằng WAF thay thế an toàn mã ứng dụng.
5. **Phân quyền:** áp dụng Azure RBAC để giới hạn người sửa listener, rule, certificate, WAF policy và backend.
6. **Tự động hóa có kiểm soát:** quản lý cấu hình bằng IaC như ARM/Bicep/Terraform và review thay đổi trước triển khai.
7. **Giám sát:** bật metrics, diagnostic settings, alert và theo dõi backend health; đặt người chịu trách nhiệm xử lý.
8. **Dự phòng:** cân nhắc nhiều backend, zone redundancy và kế hoạch DR liên vùng khi có yêu cầu.
9. **Chi phí:** theo dõi SKU, thời gian hoạt động, capacity/autoscale, dữ liệu và các tính năng đi kèm.

Quy tắc quản trị tốt là mỗi listener/path map phải có chủ sở hữu ứng dụng và một bộ kiểm thử xác định hostname, đường dẫn, giao thức và backend mong đợi. Khi thêm một tuyến mới, hãy kiểm tra lại những tuyến có path chồng lấn để tránh phá vỡ chức năng đang hoạt động.

## 14. Ước tính chi phí và lựa chọn thiết kế

Application Gateway có thể phát sinh chi phí theo thành phần cố định và mức sử dụng/công suất tùy SKU, số instance/capacity, thời gian hoạt động và các yếu tố được sản phẩm tính phí. Ngoài ra có thể có chi phí Public IP, truyền dữ liệu, log/monitoring và dịch vụ WAF theo hình thức áp dụng.

Trước khi tạo gateway cho môi trường học tập hoặc sản xuất, hãy:

- Chọn SKU đúng tính năng: Standard_v2 hoặc WAF_v2 theo nhu cầu.
- Ước tính số request, lưu lượng, độ trễ và các peak traffic.
- Lựa chọn autoscaling và mức instance tối thiểu hợp lý.
- Xem liệu một gateway có thể phục vụ nhiều ứng dụng mà vẫn đảm bảo cô lập về quản trị và hiệu năng không.
- Kiểm tra chi phí của Azure Monitor/Log Analytics và retention.
- Đặt ngân sách, tag chủ sở hữu và kiểm tra Azure Cost Management.

Không suy ra rằng Application Gateway có mức giá cố định duy nhất hoặc luôn rẻ hơn Front Door/Load Balancer. Cần tra bảng giá hiện hành theo SKU, region và kiến trúc thực tế.

## 15. Bài tập tình huống

Một doanh nghiệp có ứng dụng tuyển dụng:

- **jobs.example.com** hiển thị danh sách vị trí.
- **jobs.example.com/api/** cung cấp API.
- **admin.example.com** cung cấp trang quản trị riêng.
- Backend web có hai VM, backend API có ba instance, backend admin có một dịch vụ HTTPS.

Yêu cầu: client truy cập qua HTTPS, API và web tách backend, admin dùng hostname riêng, các backend unhealthy không nhận lưu lượng mới, và dữ liệu quản trị phải được bảo vệ.

Hãy thiết kế:

1. Frontend IP/port và các HTTPS listener cần tạo.
2. Backend pools và backend settings cho web, API, admin.
3. Path map cho **jobs.example.com** với tuyến `/api/*` và default route.
4. Basic rule hoặc path-based rule cho **admin.example.com**.
5. Custom probe phù hợp với từng backend.
6. Chứng chỉ, Host/SNI và lựa chọn HTTPS backend.
7. Chính sách WAF, DNS, kiểm soát mạng và phương án quan sát khi có lỗi 403/502.
8. Bộ kiểm thử để chứng minh mỗi Host/path đến đúng backend, kể cả khi một API instance không khỏe.

Một phương án hợp lý dùng hai multi-site HTTPS listeners, một path-based rule cho **jobs.example.com** và một basic rule cho **admin.example.com**. Backend settings/probes được tách theo giao thức và hostname. Chỉ frontend cần công khai; quyền truy cập backend được giới hạn theo đường đi của gateway. Nếu admin không cần công khai cho mọi người, cần thêm kiểm soát mạng, danh tính hoặc điểm vào riêng theo chính sách.

## 16. Câu hỏi tự kiểm tra

1. Vì sao Application Gateway được xếp vào Layer 7, còn Azure Load Balancer thường ở Layer 4?
2. HTTP listener khác backend pool và backend settings ở điểm nào?
3. Một request đến **shop.example.com/api/orders** sẽ đi qua các bước nào trước khi tới API backend?
4. Khác biệt giữa basic rule và path-based rule là gì? URL path map có tác dụng gì?
5. Nếu cả `/api/admin/*` và `/api/*` cùng tồn tại, cần lưu ý điều gì về thứ tự khớp?
6. Vì sao DNS trỏ đúng Public IP vẫn chưa đủ để một hostname hoạt động?
7. Định tuyến theo `/api/*` có tự động bỏ tiền tố **/api** khi chuyển request tới backend không?
8. Vì sao backend probe có thể unhealthy dù ứng dụng web vẫn chạy?
9. Mô tả hai mô hình TLS termination và end-to-end TLS khi dùng Application Gateway.
10. Khi nhận lỗi 403, cần phân biệt WAF với lỗi ủy quyền của backend bằng cách nào?
11. Khi nhận lỗi 502, bạn sẽ kiểm tra backend health, cổng, DNS, TLS và NSG theo trình tự nào?
12. Vì sao một Application Gateway regional không tự cung cấp disaster recovery khi cả region gặp sự cố?

## Tài liệu tham khảo

- Microsoft Learn — *What is Azure Application Gateway?*: https://learn.microsoft.com/azure/application-gateway/overview
- Microsoft Learn — *Request routing rules*: https://learn.microsoft.com/azure/application-gateway/request-routing-rules
- Microsoft Learn — *URL path-based routing*: https://learn.microsoft.com/azure/application-gateway/url-route-overview
- Microsoft Learn — *Backend health and health probes*: https://learn.microsoft.com/azure/application-gateway/application-gateway-probe-overview
- Microsoft Learn — *TLS termination and end-to-end TLS*: https://learn.microsoft.com/azure/application-gateway/ssl-overview
- Microsoft Learn — *Application Gateway WAF*: https://learn.microsoft.com/azure/web-application-firewall/ag/ag-overview
- Microsoft Learn — *Application Gateway infrastructure configuration*: https://learn.microsoft.com/azure/application-gateway/configuration-infrastructure
