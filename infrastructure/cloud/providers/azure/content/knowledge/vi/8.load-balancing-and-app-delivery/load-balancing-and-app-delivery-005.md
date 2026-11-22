# TLS termination, listener và backend pool

Một ứng dụng được truy cập qua tên miền `https://shop.example.com` có thể chạy trên nhiều máy ảo, App Service hoặc một nhóm dịch vụ phía sau. Người dùng chỉ nhìn thấy một tên miền HTTPS, nhưng hệ thống phải giải quyết đồng thời ba câu hỏi: **kết nối TLS được xử lý ở đâu, yêu cầu HTTP được tiếp nhận theo điều kiện nào và yêu cầu sẽ chuyển đến backend nào?**

Trong Azure, **Application Gateway** là một lựa chọn điển hình cho mô hình cân bằng tải **Layer 7 (HTTP/HTTPS)**. Ba khái niệm **TLS termination**, **listener** và **backend pool** cùng với **request routing rule**, **backend settings** và **health probe** tạo thành một luồng xử lý hoàn chỉnh. Hiểu mối quan hệ này giúp cấu hình đúng tên miền, chứng chỉ, định tuyến, bảo mật và khả năng sẵn sàng.

Bài học thuộc chương **Cân bằng tải và phân phối ứng dụng** của module `CLOUD_PROVIDERS_AZURE`. Module giới thiệu Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; sau đó áp dụng vào triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Nội dung dưới đây tập trung vào Azure Application Gateway; đồng thời chỉ ra điểm khác biệt với Azure Load Balancer và Azure Front Door khi cần.

## 1. Mục tiêu bài học

Sau khi hoàn thành bài, bạn có thể:

1. Giải thích **TLS termination** và sự khác nhau giữa TLS ở frontend với TLS ở backend.
2. Mô tả thành phần của một **HTTP/HTTPS listener**: frontend IP, port, protocol, hostname và chứng chỉ.
3. Tổ chức **backend pool** gồm IP/FQDN hoặc các đích được Application Gateway hỗ trợ.
4. Ghép **listener → request routing rule → backend pool + backend settings**.
5. Thiết kế **health probe** để chỉ điều hướng tới backend đủ điều kiện nhận traffic.
6. Chọn mô hình HTTPS→HTTP hay HTTPS→HTTPS theo nhu cầu bảo mật.
7. Xử lý các lỗi thực tế: chứng chỉ sai, tên host không khớp, backend Unhealthy, HTTP 502 và vòng lặp chuyển hướng.
8. Kiểm tra bằng Azure Portal và Azure CLI trước khi nghiệm thu.

## 2. Đặt Application Gateway trong bức tranh cân bằng tải Azure

Các dịch vụ Azure cùng thực hiện “phân phối lưu lượng” nhưng ở các lớp khác nhau:

| Dịch vụ | Đặc trưng chính | Bài toán phù hợp |
|---|---|---|
| **Azure Load Balancer** | Cân bằng tải **Layer 4** theo TCP/UDP, hoạt động trên IP và port. | Dịch vụ TCP/UDP, cân bằng tải mạng nội bộ hoặc công khai. |
| **Azure Application Gateway** | Reverse proxy và cân bằng tải **Layer 7**, hiểu HTTP/HTTPS; hỗ trợ TLS termination, host/path routing, health probes, WAF theo SKU. | Ứng dụng web/API trong một kiến trúc Azure khu vực. |
| **Azure Front Door** | Dịch vụ phân phối ứng dụng ở edge toàn cầu, có TLS, routing và các tính năng bảo mật theo gói. | Ứng dụng public nhiều region, tối ưu truy cập toàn cầu và chuyển vùng. |

**Azure Load Balancer không thực hiện TLS termination ở cấp HTTP**. Nếu dùng Load Balancer, TLS thường được giải mã bởi ứng dụng hoặc proxy phía sau. Application Gateway có thể giải mã HTTPS để đọc hostname, đường dẫn, header và áp dụng quy tắc Layer 7. Azure Front Door cũng xử lý TLS nhưng có vị trí và phạm vi phân phối toàn cầu khác Application Gateway.

Trong bài, ví dụ sử dụng **Application Gateway v2** (Standard_v2 hoặc WAF_v2 tùy nhu cầu). Các tùy chọn cụ thể thay đổi theo SKU, region và phiên bản; hãy kiểm tra tính năng đang hỗ trợ trước khi triển khai Production.

## 3. Luồng tổng thể từ trình duyệt đến backend

Mỗi yêu cầu HTTP(S) đi qua nhiều đối tượng cấu hình:

```text
                     DNS: shop.example.com
                               |
                         HTTPS :443
                               v
                      +-----------------+
Internet / Client --->| Frontend IP     |
                      | Application     |
                      | Gateway         |
                      +--------+--------+
                               |
                       HTTPS Listener
                 host=shop.example.com
                 protocol=HTTPS, port=443
                 TLS certificate: shop.example.com
                               |
                    Request routing rule
                  (Basic hoặc path-based)
                               |
                      +--------+--------+
                      |                 |
               Backend pool        Backend settings
              [web-01, web-02]     HTTP/HTTPS, port,
                                  host, timeout, affinity,
                                  custom health probe
                      |                 |
                      +--------+--------+
                               |
                 Chỉ chọn endpoint healthy
                       /              \
                      v                v
                   web-01            web-02
                10.20.1.10         10.20.1.11
```

Luồng trong hình gồm những bước logic:

1. Client phân giải DNS rồi mở kết nối TCP/TLS đến **frontend IP** của gateway.
2. **HTTPS listener** nhận kết nối tương ứng với protocol, port và hostname.
3. Gateway thực hiện **TLS handshake** với client bằng chứng chỉ được cấu hình cho listener.
4. Gateway kiểm tra **request routing rule** để chọn backend pool và backend settings, hoặc redirect sang URL khác.
5. **Health probe** xác định các backend nào sẵn sàng.
6. Gateway gửi yêu cầu tới một backend khỏe mạnh qua HTTP hoặc HTTPS theo backend settings.
7. Backend trả phản hồi qua gateway, gateway gửi lại cho client trên kết nối frontend.

Từ một listener có thể cấu hình những kiểu route khác nhau tùy quy tắc được hỗ trợ. Một backend pool cũng có thể được tham chiếu bởi nhiều routing rules. Các thành phần cần ghép đúng với nhau; tạo backend pool thôi chưa đủ để traffic đi đến ứng dụng.

## 4. TLS termination là gì?

**TLS (Transport Layer Security)** tạo kênh mã hóa và xác thực server cho kết nối mạng, thường dùng với HTTPS. Khi trình duyệt truy cập `https://shop.example.com`, trình duyệt kiểm tra chứng chỉ TLS và thiết lập kết nối mã hóa tới điểm tiếp nhận HTTPS.

**TLS termination tại Application Gateway** nghĩa là gateway là nơi **kết thúc kết nối TLS của client**. Gateway có quyền giải mã nội dung HTTP để định tuyến, kiểm tra header hoặc áp dụng WAF (nếu bật).

```text
Client                  Application Gateway               Backend
  |     TLS session A           |                           |
  |============================>|                           |
  |  HTTPS encrypted            |  HTTP request đã giải mã   |
  |                             |---------- HTTP ---------->|  (tùy chọn 1)
  |                             |                           |
  |                             |==== TLS session B =======>|  (tùy chọn 2)
  |                             |    HTTPS tới backend      |
```

Điểm then chốt: **TLS session A và TLS session B là hai kết nối khác nhau**. Trong mô hình HTTPS→HTTPS, gateway giải mã request ở frontend rồi tạo kết nối TLS mới tới backend. Đây thường được gọi là **end-to-end TLS** trong tài liệu Application Gateway, nhưng không phải một phiên TLS duy nhất xuyên suốt client đến backend.

### HTTPS ở frontend, HTTP ở backend

- Trình duyệt ↔ Application Gateway: **HTTPS**, mã hóa.
- Application Gateway ↔ backend: **HTTP**, không mã hóa ở lớp TLS.
- Cấu hình đơn giản hơn và có thể phù hợp một số môi trường lab hoặc phạm vi tin cậy được kiểm soát.

Rủi ro: lưu lượng **phía sau gateway không còn được TLS bảo vệ**. Chỉ dùng nếu được phép theo mô hình bảo mật, vùng mạng và chính sách tổ chức.

### HTTPS ở frontend, HTTPS ở backend

- Trình duyệt ↔ Application Gateway: **HTTPS**, gateway dùng chứng chỉ frontend.
- Application Gateway ↔ backend: **HTTPS**, gateway trở thành TLS client và xác thực backend theo cấu hình.
- Phù hợp khi dữ liệu phải được mã hóa trên cả hai chặng hoặc chính sách bảo mật yêu cầu.

Cấu hình backend HTTPS cần chú ý **chứng chỉ backend**, hostname được xác thực, trust chain, SNI và khả năng kết nối cổng TLS. Chứng chỉ phía client-facing listener **không tự động** trở thành chứng chỉ được backend sử dụng. Backend phải có chứng chỉ server phù hợp riêng.

### TLS termination khác TLS passthrough

- **Termination:** gateway giải mã và hiểu HTTP để áp dụng Layer 7 routing, WAF.
- **Passthrough:** thiết bị chuyển tiếp dữ liệu TLS được mã hóa mà không giải mã HTTP.

Application Gateway là reverse proxy Layer 7 nên mô hình của nó dựa trên **TLS termination**. Nếu yêu cầu TLS passthrough thực sự ở lớp TCP, cần xem xét dịch vụ/kiến trúc khác phù hợp thay vì mong listener HTTPS của Application Gateway chuyển tiếp nguyên phiên TLS.

## 5. Chứng chỉ TLS phía frontend

HTTPS listener cần chứng chỉ cho tên miền phục vụ người dùng, ví dụ `shop.example.com`.

Các yếu tố cần kiểm tra:

| Yếu tố | Cần bảo đảm |
|---|---|
| **Subject/SAN** | Chứng chỉ bao phủ chính xác hostname mà client truy cập. |
| **Hiệu lực** | Không hết hạn hoặc chưa đến ngày có hiệu lực. |
| **Chuỗi tin cậy** | Có chuỗi CA phù hợp để trình duyệt xác minh. |
| **Private key** | Có thể sử dụng bởi gateway thông qua phương thức nhập chứng chỉ được hỗ trợ. |
| **TLS policy** | Phiên bản TLS và cipher suites phù hợp yêu cầu bảo mật/khả năng tương thích của client. |
| **Gia hạn** | Có quy trình xoay vòng, giám sát hạn dùng và kiểm tra sau gia hạn. |

Trong Application Gateway, chứng chỉ frontend thường có thể được cung cấp bằng file **PFX/PKCS#12** chứa private key hoặc tham chiếu tới chứng chỉ/secret được quản lý trong **Azure Key Vault** bằng cơ chế được SKU hỗ trợ. Khi tích hợp Key Vault, gateway cần **managed identity** và quyền truy xuất secret/certificate phù hợp, cùng đường mạng có thể truy cập vault theo cấu hình.

Không đưa mật khẩu PFX, private key, client secret hoặc file chứng chỉ có private key vào repository, log hoặc ví dụ học tập. Với Production, nên quản lý vòng đời chứng chỉ tập trung, phân quyền tối thiểu và theo dõi lỗi truy xuất Key Vault.

### SNI và nhiều tên miền

**Server Name Indication (SNI)** là phần mở rộng của TLS cho phép client cho biết hostname đích trong quá trình handshake. Gateway có thể chọn chứng chỉ/listener phù hợp khi nhiều tên miền cùng dùng một frontend IP và port.

Ví dụ:

| Hostname | HTTPS listener | Chứng chỉ frontend |
|---|---|---|
| `shop.example.com` | `listener-shop-https` | Chứng chỉ chứa `shop.example.com` |
| `admin.example.com` | `listener-admin-https` | Chứng chỉ chứa `admin.example.com` |
| `api.example.com` | `listener-api-https` | Chứng chỉ chứa `api.example.com` |

Có thể dùng chứng chỉ SAN hoặc wildcard nếu thỏa phạm vi tên miền và chính sách quản lý khóa. Chứng chỉ wildcard không bao phủ tùy ý mọi cấp miền con. Ví dụ `*.example.com` thường bao phủ `shop.example.com`, nhưng không tự động bao phủ `api.eu.example.com`.

Tên miền được ánh xạ tới listener qua cấu hình hostname, DNS và TLS certificate. Nếu client dùng tên khác tên trên chứng chỉ, trình duyệt có thể báo lỗi **hostname mismatch** ngay trong TLS handshake.

## 6. Listener: cửa nhận yêu cầu

**Listener** là thành phần khai báo gateway sẽ **lắng nghe lưu lượng nào**. Với Application Gateway, listener thường gắn các thuộc tính:

- **Frontend IP configuration:** frontend công khai hoặc riêng tư tùy kiến trúc.
- **Frontend port:** ví dụ `80` cho HTTP hoặc `443` cho HTTPS.
- **Protocol:** HTTP hoặc HTTPS.
- **Hostname(s):** tên miền cần nhận, khi dùng listener theo host.
- **TLS certificate:** cần cho HTTPS listener.
- **Các cấu hình TLS bổ sung:** như SSL profile hoặc tính năng xác thực client nếu được sử dụng và SKU hỗ trợ.

Một listener không tự chỉ định đích xử lý hoàn chỉnh. Bạn cần **request routing rule** liên kết listener với backend pool và backend settings, hoặc với redirect configuration.

### Basic listener và multi-site listener

| Loại | Nguyên tắc chọn request | Ứng dụng |
|---|---|---|
| **Basic** | Nhận request dựa trên tổ hợp frontend IP, port, protocol theo cấu hình; không phân biệt host như multi-site. | Một website hoặc một endpoint đơn giản. |
| **Multi-site** | Xác định request bằng hostname/hostnames bổ sung vào frontend IP, port và protocol. | Nhiều website/API chung gateway nhưng khác host. |

Với multi-site listener, hostname được gửi trong HTTP Host header và hostname phục vụ TLS/SNI phải được cấu hình nhất quán với chứng chỉ. Nếu không khớp, có thể gặp lỗi chọn listener, chứng chỉ hoặc route.

Ví dụ có hai website cùng dùng một public IP:

```text
https://shop.example.com:443  ──> listener-shop  ──> pool-shop
https://admin.example.com:443 ──> listener-admin ──> pool-admin
```

Cách phân tách dựa trên hostname giúp giảm nhu cầu cấp IP/port riêng cho từng website. Tuy nhiên, admin endpoint có thể cần truy cập nội bộ, xác thực mạnh hoặc ràng buộc bảo mật bổ sung; việc đặt hostname `admin` không tự bảo vệ ứng dụng khỏi truy cập trái phép.

### Chọn public hay private frontend

- **Public frontend IP:** dùng cho ứng dụng phục vụ client qua Internet. Cần DNS và chính sách bảo mật phù hợp.
- **Private frontend IP:** dùng cho ứng dụng chỉ truy cập qua mạng riêng, chẳng hạn từ VNet peering, VPN hoặc ExpressRoute nếu đường đi và DNS cho phép.
- Một số cấu hình có thể dùng các frontend khác nhau theo nhu cầu. Xem giới hạn SKU và quy tắc trùng listener/port trước khi tạo.

**Không nhầm frontend IP với địa chỉ của backend.** Frontend là địa chỉ khách truy cập; backend pool gồm những endpoint nhận request sau khi gateway định tuyến.

## 7. Backend pool: tập hợp các đích phục vụ ứng dụng

**Backend pool** là tập các đích có thể nhận yêu cầu do gateway chuyển đến. Những kiểu đích được hỗ trợ có thể gồm:

- Private IP của VM/NIC hoặc máy chủ trong VNet có kết nối.
- FQDN của ứng dụng/backend mà gateway có thể phân giải và tiếp cận.
- Các đích tích hợp theo tính năng như VM Scale Sets hoặc App Service, tùy cách tạo và SKU.

Ví dụ pool `pool-shop` gồm:

| Backend | Địa chỉ | Ứng dụng | Ghi chú |
|---|---|---|---|
| `web-01` | `10.20.1.10` | Shop API instance 1 | Private IP |
| `web-02` | `10.20.1.11` | Shop API instance 2 | Private IP |
| `web-03` | `10.20.1.12` | Shop API instance 3 | Private IP |

Pool mô tả **thành viên**, không chỉ ra đầy đủ cách gateway mở kết nối. Muốn kết nối tới các backend, gateway cần **backend settings** (trước đây thường gọi là HTTP settings) xác định protocol, port và hành vi HTTP/TLS.

**Lưu ý:** một backend có tên DNS thay đổi IP cần được gateway phân giải theo cơ chế hỗ trợ. Cần thiết kế DNS và giám sát backend thực tế; đặt FQDN vào pool không tự đảm bảo có đường mạng hoặc ứng dụng đang chạy.

### Backend pool không phải DNS của người dùng

Client dùng `shop.example.com` để tìm **frontend** gateway. Nó không cần biết `10.20.1.10` hay danh sách nội bộ của pool. Gateway quyết định backend khỏe mạnh dựa trên cấu hình và health probe.

### Có thể đặt backend ở mạng khác không?

Có thể theo kịch bản và loại đích được dịch vụ hỗ trợ, nếu gateway có **network reachability** tới backend qua routing, peering, VPN/ExpressRoute hoặc mạng thích hợp. Nếu FQDN trỏ tới địa chỉ unreachable, NSG chặn hoặc DNS không phân giải được, pool có thành viên nhưng vẫn không phục vụ traffic.

Không cấu hình pool bằng dải địa chỉ chồng lấn hoặc endpoint nằm sau firewall mà thiếu route trả về. Bảo mật và định tuyến phải được thiết kế hai chiều.

## 8. Backend settings: nối từ gateway đến backend bằng cách nào?

Backend settings bổ sung chi tiết của **chặng kết nối phía sau gateway**.

| Thuộc tính | Ví dụ | Tác dụng |
|---|---|---|
| **Protocol** | HTTP hoặc HTTPS | Chọn có tạo phiên TLS đến backend không. |
| **Port** | `80`, `8080`, `443`, `8443` | Cổng dịch vụ backend thực sự lắng nghe. |
| **Request timeout** | Một khoảng giây phù hợp | Quy định thời gian gateway chờ phản hồi theo cấu hình. |
| **Cookie-based affinity** | Enabled/Disabled | Có thể duy trì request của một phiên client tới cùng backend trong mô hình được hỗ trợ. |
| **Host name** | `shop.internal.example` | Đặt Host header/tên dùng cho backend, quan trọng với virtual host và TLS. |
| **Trusted root CA / validation** | CA đáng tin cậy theo cấu hình | Giúp gateway xác thực chứng chỉ của backend HTTPS. |
| **Custom probe** | `probe-shop` | Xác định health check tương ứng pool và cài đặt backend. |

Ví dụ frontend là `HTTPS :443` nhưng ứng dụng chạy `HTTP :8080`:

```text
Client  -- HTTPS/443 -->  Application Gateway  -- HTTP/8080 -->  web-01, web-02
```

Nếu backend chạy HTTPS trên 8443:

```text
Client  -- HTTPS/443 -->  Application Gateway  -- HTTPS/8443 -->  web-01, web-02
```

Port frontend **không cần bằng** port backend. Backend settings cũng không tự cho phép đường truyền nếu NSG/firewall đang chặn cổng hoặc app không lắng nghe.

### Backend TLS và tên host

Khi dùng **HTTPS backend**, cần xác minh:

1. Backend trình bày **server certificate còn hạn**.
2. Certificate SAN/CN phù hợp **hostname mà Application Gateway dùng để kết nối và xác thực**.
3. Chain được tin cậy; nếu dùng private CA, cấu hình trusted root certificate phù hợp theo dịch vụ.
4. Gateway có thể phân giải hostname và kết nối tới đúng IP, port qua mạng.
5. Health probe dùng host và protocol phù hợp để không đánh dấu healthy sai hoặc false negative.

Ví dụ backend là App Service mặc định có hostname `store-prod.azurewebsites.net`, nhưng listener nhận `shop.example.com`. Nếu App Service chưa cấu hình custom domain/certificate cho `shop.example.com`, việc gateway gửi hostname frontend sang backend có thể khiến TLS/host routing không khớp. Có thể phải chọn host name từ backend target hoặc đặt explicit backend hostname phù hợp, rồi kiểm tra ứng dụng vẫn tạo URL và cookie đúng.

Nếu app phụ thuộc vào **original Host header**, việc thay Host để phù hợp backend có thể ảnh hưởng redirect, cookie hoặc routing bên trong app. Hãy thiết kế đầy đủ **hostname frontend, hostname backend và forwarded headers**, không sửa riêng lẻ một trường để “hết lỗi 502”.

## 9. Request routing rule: ghép listener với backend

Listener nhận request, còn **request routing rule** quyết định xử lý request bằng cách nào.

Hai dạng routing phổ biến:

- **Basic rule:** dùng backend pool và backend settings để xử lý các request khớp listener theo một đích logic.
- **Path-based rule:** chọn backend theo URL path map, ví dụ `/api/*` đến API pool và `/images/*` đến static pool.

Ví dụ cho hostname `shop.example.com`:

| Listener | Điều kiện URL | Backend pool | Backend settings |
|---|---|---|---|
| `listener-shop-https` | `/api/*` | `pool-api` | HTTPS port 8443 |
| `listener-shop-https` | `/images/*` | `pool-images` | HTTP port 8080 |
| `listener-shop-https` | Các đường dẫn còn lại | `pool-web` | HTTPS port 443 |

Trong Application Gateway, đây là biểu diễn logic của **một path-based routing rule** với URL path map; không có nghĩa phải tạo ba basic rules xung đột trên cùng listener. Với v2, các request routing rules có thứ tự ưu tiên để tránh lựa chọn mơ hồ khi nhiều cấu hình khớp.

### Chuyển hướng HTTP sang HTTPS

Để người dùng vào `http://shop.example.com` được đưa tới HTTPS:

1. Tạo HTTP listener port 80 cho hostname phù hợp.
2. Tạo HTTPS listener port 443 với certificate hợp lệ.
3. Tạo **redirect configuration** từ HTTP listener sang HTTPS listener hoặc target phù hợp.
4. Gắn redirect vào routing rule của HTTP listener.
5. Chọn mã chuyển hướng phù hợp, thường dùng permanent redirect khi chắc chắn cấu hình ổn định.

HTTP listener 80 **không nhất thiết** phải trỏ trực tiếp tới backend pool nếu nhiệm vụ chỉ là redirect. TLS handshake chỉ diễn ra khi client kết nối HTTPS tới listener 443.

Không chỉ dựa vào redirect để khẳng định mọi kết nối đều đã mã hóa. Cần bảo vệ listener HTTPS, áp dụng policy TLS phù hợp, và cân nhắc HSTS khi ứng dụng/miền đã sẵn sàng.

## 10. Health probe: backend có thực sự sẵn sàng?

**Health probe** là phép kiểm tra định kỳ do gateway thực hiện tới backend. Chỉ những endpoint được coi là **healthy** mới phù hợp để nhận request theo cơ chế cân bằng tải của gateway.

Probe có thể dùng:

- **Protocol:** HTTP hoặc HTTPS.
- **Port:** theo backend settings hoặc cấu hình probe được hỗ trợ.
- **Host header:** tên ứng dụng/virtual host backend mong đợi.
- **Path:** ví dụ `/healthz` hoặc `/ready`.
- **Interval, timeout và unhealthy threshold:** tần suất, thời gian chờ và ngưỡng đánh giá.
- **Status code match:** mặc định thường chấp nhận HTTP 200–399; có thể cấu hình dải theo nhu cầu.

Một path kiểm tra hữu ích nên trả lời nhanh và phản ánh khả năng phục vụ của instance. Ví dụ `/ready` có thể kiểm tra thành phần thiết yếu để tiếp nhận traffic, nhưng không nên thực hiện truy vấn nặng gây tải hoặc thay đổi dữ liệu ở mỗi lần probe.

### Default probe và custom probe

Default probe có thể kiểm tra đường dẫn gốc `/` theo backend settings. Nếu ứng dụng yêu cầu hostname riêng hoặc trả `401/403/404` ở `/`, gateway có thể đánh giá backend **unhealthy** mặc dù ứng dụng hoạt động ở endpoint khác.

Giải pháp thường là tạo **custom probe** trỏ tới endpoint health có phản hồi kỳ vọng, kèm host và protocol đúng. Không đơn giản mở rộng status match để chấp nhận mọi lỗi 500; như vậy có thể khiến backend hỏng vẫn được coi là healthy.

### Ví dụ

```http
GET /healthz HTTP/1.1
Host: shop.internal.example
```

Phản hồi kỳ vọng:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

ok
```

Đây là ví dụ logic. Trong hệ thống thật, endpoint nên phù hợp với cách ứng dụng công bố trạng thái, mạng bảo vệ và hành vi probe của gateway.

### Backend unhealthy ảnh hưởng thế nào?

Nếu một pool chỉ còn những backend Unhealthy, gateway có thể không còn endpoint đủ điều kiện xử lý request; client có thể nhận **502 Bad Gateway** trong những tình huống đó. Tuy nhiên, 502 cũng có thể đến từ các vấn đề khác như TLS handshake, timeout hoặc lỗi giao tiếp, nên phải đọc **Backend health** và log trước khi kết luận.

## 11. Thiết kế ứng dụng nhiều hostname và nhiều backend

Giả sử hệ thống có:

- Website công khai: `shop.example.com`.
- API công khai: `api.example.com`.
- Trang quản trị nội bộ: `admin.corp.example`.
- Backend web gồm hai App Service hoặc VM.
- Backend API gồm ba instance.
- Trang quản trị chỉ được truy cập từ mạng doanh nghiệp.

Kế hoạch cấu hình:

| Thành phần | Website | API | Admin |
|---|---|---|---|
| Client hostname | `shop.example.com` | `api.example.com` | `admin.corp.example` |
| Frontend | Public IP | Public IP | Private IP nếu kiến trúc/SKU hỗ trợ, kèm DNS nội bộ |
| HTTPS listener | `lis-shop` | `lis-api` | `lis-admin` |
| TLS certificate | Bao phủ shop | Bao phủ API | Bao phủ admin |
| Routing | Basic hoặc path map | API rule | Admin rule |
| Backend pool | `pool-shop` | `pool-api` | `pool-admin` |
| Backend protocol | HTTPS | HTTPS | HTTPS |
| Health probe | `/healthz` | `/ready` | `/healthz` |

Đây là **bảng thiết kế**, không phải cấu hình áp dụng tự động. Việc cùng lúc sử dụng frontend public và private, các listener cùng port và hostname riêng phải tuân theo giới hạn của SKU và yêu cầu routing thực tế. Tài nguyên admin phải có ràng buộc truy cập và chính sách xác thực phù hợp; private IP chỉ giải quyết phạm vi mạng.

### VNet/subnet và network security

Application Gateway được triển khai vào **subnet riêng dành cho Application Gateway**. Khi chọn kích thước subnet, tính khả năng autoscale và số địa chỉ mà instance có thể dùng; một subnet rộng, chẳng hạn /24 cho kiến trúc có nhu cầu scale lớn, thường tạo dư địa tốt hơn một subnet nhỏ. Đối chiếu tài liệu SKU/khu vực để xác định giới hạn và kích thước cần thiết.

Backend có thể nằm trong subnet/VNet khác nếu định tuyến cho phép. Đặt NSG, UDR, Azure Firewall và DNS phù hợp, tránh chặn đường probe hoặc đường dữ liệu cần thiết. Không đặt một VM ứng dụng tùy ý trong subnet chuyên dụng của gateway.

## 12. WAF, bảo mật và HTTP headers

**WAF_v2** bổ sung Web Application Firewall để kiểm tra request HTTP/HTTPS theo chính sách. TLS termination cho phép gateway/WAF kiểm tra request sau khi giải mã.

Các lớp bảo vệ có chức năng khác nhau:

- **TLS:** mã hóa và xác minh danh tính server theo chứng chỉ.
- **WAF:** nhận diện/ngăn chặn một số kiểu request độc hại Layer 7 theo rule và policy.
- **NSG/Firewall:** giới hạn đường truyền và các cổng mạng.
- **Authentication/authorization:** xác nhận người dùng hoặc workload có quyền sử dụng chức năng hay không.
- **Application validation:** kiểm tra dữ liệu đầu vào, phiên, CSRF và hành vi nghiệp vụ.

WAF không thay thế kiểm tra quyền người dùng hoặc bảo mật mã nguồn. Khi thử nghiệm WAF, theo dõi false positive và sử dụng log/ngoại lệ có kiểm soát.

### Forwarded headers và địa chỉ client

Vì gateway là reverse proxy, backend có thể thấy kết nối đến từ gateway thay vì IP trực tiếp của client. Application Gateway thêm các header hỗ trợ chuyển tiếp thông tin client, ví dụ `X-Forwarded-For`, `X-Forwarded-Proto` và những header khác theo khả năng dịch vụ.

Ứng dụng có thể dùng thông tin này để ghi log hoặc tạo URL chính xác, nhưng **phải cấu hình danh sách proxy đáng tin cậy** và xử lý header an toàn. Không mặc nhiên tin một header do client tự gửi tới ứng dụng qua đường khác.

### Lỗi redirect loop do scheme

Ví dụ client dùng HTTPS tới gateway, gateway dùng HTTP tới backend. Nếu ứng dụng chỉ nhìn thấy kết nối nội bộ HTTP và tự redirect sang HTTPS liên tục, người dùng có thể gặp vòng lặp.

Cách phân tích:

1. Xác định frontend đã thực sự là HTTPS.
2. Xem backend settings và chính sách redirect của ứng dụng.
3. Kiểm tra cách ứng dụng xử lý `X-Forwarded-Proto`/scheme và trusted proxies.
4. Điều chỉnh cấu hình reverse proxy và ứng dụng cho nhất quán, thay vì tắt HTTPS.

## 13. Quy trình triển khai qua Azure Portal

Các bước sau minh họa Application Gateway nhận `https://shop.example.com` và phân phối đến backend web.

### Giai đoạn A: Chuẩn bị

1. Xác nhận subscription, resource group, region và quyền triển khai.
2. Chuẩn bị VNet và **subnet dành riêng cho Application Gateway**; bảo đảm không chồng lấn địa chỉ.
3. Xác định public/private frontend, DNS record, tên miền cần phục vụ.
4. Chuẩn bị chứng chỉ frontend phù hợp và nơi lưu khóa/chứng chỉ an toàn.
5. Xác định pool backend, protocol/port, host header và endpoint probe.
6. Chọn SKU v2 và có cần WAF hay không; dự toán chi phí vận hành.

### Giai đoạn B: Tạo gateway và frontend

1. Mở [Azure Portal](https://portal.azure.com/) → **Application gateways** → tạo mới.
2. Chọn region, VNet, subnet, SKU và các thuộc tính theo mục đích.
3. Cấu hình **Frontend IP** công khai hoặc riêng tư theo kiến trúc.
4. Tạo hoặc chọn **Frontend port** 443 cho HTTPS.

### Giai đoạn C: Tạo backend pool và settings

1. Tạo `pool-shop` với hai hoặc nhiều backend IP/FQDN phù hợp.
2. Tạo backend settings chọn HTTPS port 443 (hoặc port backend thực tế).
3. Chọn hostname/backend TLS validation thích hợp.
4. Tạo custom probe `/healthz` với host và phản hồi mong đợi, gắn với backend settings.
5. Kiểm tra routing, NSG và DNS cho phép gateway kết nối backend.

### Giai đoạn D: Tạo listener, rule và DNS

1. Tạo HTTPS listener `listener-shop-https` trên frontend IP:443 với hostname `shop.example.com`.
2. Gắn chứng chỉ TLS frontend.
3. Tạo request routing rule liên kết listener tới `pool-shop` và backend settings tương ứng.
4. Nếu cần HTTP→HTTPS, tạo HTTP listener port 80 và redirect configuration riêng.
5. Tạo DNS record phù hợp để `shop.example.com` phân giải đến frontend public IP/FQDN của gateway hoặc private IP trong DNS nội bộ.

### Giai đoạn E: Kiểm thử

1. Mở `https://shop.example.com/healthz` (nếu endpoint được phép truy cập từ client) hoặc URL ứng dụng chính.
2. Xác nhận trình duyệt không báo lỗi chứng chỉ, hostname và chuỗi CA.
3. Kiểm tra **Backend health**: từng endpoint healthy và nhận request.
4. Thử URL routing, redirect HTTP→HTTPS và endpoint API nếu có.
5. Tạm loại một backend theo quy trình thử nghiệm an toàn để kiểm tra khả năng phục vụ từ backend còn lại.
6. Kiểm tra access logs, WAF logs (nếu dùng), metrics và cảnh báo.

Thao tác tạo Application Gateway, WAF hoặc chứng chỉ có thể phát sinh chi phí và đòi hỏi quyền phù hợp; các bước thay đổi trên môi trường thật chỉ thực hiện trong phạm vi dự án được cấp phép.

## 14. Kiểm tra hiện trạng bằng Azure CLI

Các lệnh minh họa dưới đây **chỉ đọc trạng thái**, thuận tiện kiểm tra môi trường đã triển khai. Thay tên gateway và resource group bằng dữ liệu thật.

### Kiểm tra subscription

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

### Liệt kê gateways

```bash
az network application-gateway list \
  --resource-group "rg-app-delivery" \
  --output table
```

### Xem cấu hình tổng thể

```bash
az network application-gateway show \
  --name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output json
```

### Xem listener và backend pools

```bash
az network application-gateway http-listener list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output table

az network application-gateway address-pool list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output table
```

### Xem backend settings, probes và rules

```bash
az network application-gateway http-settings list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output json

az network application-gateway probe list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output table

az network application-gateway rule list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output json
```

### Xem backend health

```bash
az network application-gateway show-backend-health \
  --name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output json
```

Backend health thường cho biết endpoint nào Healthy/Unhealthy và chi tiết chẩn đoán tương ứng. Khi dùng automation, hãy kiểm tra tên tham số của phiên bản CLI được cài đặt bằng `az network application-gateway --help` hoặc `... <subcommand> --help` trước khi xây pipeline.

Các lệnh đọc cấu hình **không thay thế việc kiểm thử request thực tế từ client**. Cần đối chiếu thêm DNS, network access và logs của backend khi có lỗi.

## 15. Tình huống lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| Trình duyệt báo chứng chỉ không hợp lệ | Cert frontend hết hạn, chain thiếu, hostname không khớp | Xem listener HTTPS, certificate, SAN và thời hạn |
| Domain A dùng được nhưng domain B không | Multi-site listener host/SNI hoặc DNS/rule sai | Đối chiếu hostname, listener, DNS, rule priority |
| Client nhận 502 | Backend Unhealthy, TLS backend thất bại, timeout hoặc lỗi upstream | Xem Backend health, probe, cert backend, NSG, access logs |
| Pool có backend nhưng không có request thành công | Chưa gắn routing rule/settings, backend unreachable | Kiểm tra listener→rule→pool/settings và đường mạng |
| Probe báo Unhealthy nhưng truy cập trực tiếp backend được | Probe sai Host/path/protocol/port, health endpoint trả status ngoài khoảng | Tạo custom probe đúng ứng dụng, kiểm tra HTTP status |
| Gateway chuyển request tới backend nhưng app trả 404 | Backend Host header hoặc path routing sai | Kiểm tra backend hostname, URL path map và route trong app |
| HTTP→HTTPS bị lặp vô hạn | App không nhận scheme thực, proxy trust sai | Kiểm tra redirect và forwarded proto |
| Backend HTTPS lỗi chứng chỉ | Backend cert không trusted hoặc hostname mismatch | Đối chiếu backend settings, SNI, CA chain, tên chứng chỉ |
| Tải tăng gây chậm hoặc lỗi | Backend không đủ công suất, autoscale/timeout chưa phù hợp | Xem latency, CPU, gateway metrics, logs và backend health |
| WAF chặn yêu cầu hợp lệ | Rule false positive hoặc request vi phạm chính sách | Xem WAF logs, rule ID và điều chỉnh có kiểm soát |
| Chỉ mạng nội bộ truy cập được | Frontend private, DNS/routing hoặc NSG hạn chế | Kiểm tra nguồn client và thiết kế frontend |
| App Service tạo URL sai hostname | Backend host override hoặc proxy headers chưa nhất quán | Kiểm tra frontend host, backend host, cookie, redirect |

### Quy trình xử lý lỗi 502

1. Ghi thời điểm UTC, hostname, URL path, mã HTTP, correlation/transaction ID nếu log có.
2. Xác nhận DNS của hostname trỏ tới đúng frontend.
3. Kiểm tra listener HTTPS và rule có trỏ đúng pool/settings không.
4. Mở **Backend health** và kiểm tra endpoint nào Unhealthy; đọc nguyên nhân.
5. Kiểm tra probe: protocol, port, host, path, status code.
6. Kiểm tra network connectivity giữa gateway và backend: NSG, route, DNS, firewall và cổng lắng nghe.
7. Nếu backend dùng HTTPS, kiểm tra chứng chỉ, CA chain, tên host và trạng thái TLS.
8. Kiểm tra access logs ở gateway, logs ở backend và thời gian xử lý request.
9. Sau khi sửa đúng nguyên nhân, kiểm tra health chuyển Healthy và thử lại request từ client.

Không nên kết luận “TLS frontend lỗi” khi thấy 502. Nếu client đã handshake HTTPS thành công với gateway nhưng request tới backend lỗi, nguyên nhân thường nằm ở **backend path** hoặc ứng dụng. Ngược lại, trình duyệt báo chứng chỉ trước khi có HTTP response là dấu hiệu nên kiểm tra **listener/certificate frontend**.

## 16. Giám sát, độ sẵn sàng và chi phí

### Giám sát

Thiết lập Azure Monitor metrics và diagnostic settings theo khả năng hỗ trợ của Application Gateway, chẳng hạn:

- **Healthy/Unhealthy host count** trong pool.
- **Total requests, failed requests, HTTP 4xx/5xx** theo cách dịch vụ cung cấp.
- **Response time/latency** và kết quả backend.
- **WAF logs**, nếu triển khai WAF_v2.
- **Access logs** để biết host, path, status và chi tiết request.
- **Certificate lifecycle** và kết nối tới Key Vault khi dùng tích hợp chứng chỉ.

Cần phân biệt lỗi **4xx do ứng dụng từ chối hợp lệ** với lỗi **5xx do gateway hoặc backend hỏng**. Mọi 404 không nhất thiết là sự cố hạ tầng.

### Độ sẵn sàng

Để tăng khả năng phục vụ:

1. Có ít nhất hai backend khỏe mạnh khi ứng dụng có thể scale theo chiều ngang.
2. Phân bố instance qua fault domain/availability zone theo khả năng của dịch vụ và region.
3. Dùng health probe phản ánh khả năng sẵn sàng thực tế.
4. Triển khai gateway với cấu hình scaling và availability phù hợp SKU.
5. Xác nhận backend có thể hoạt động độc lập khi một instance mất.
6. Nếu yêu cầu DR giữa nhiều region, cần kiến trúc phân phối đa region riêng, ví dụ Front Door hoặc cơ chế DNS/traffic routing phù hợp.

Application Gateway là dịch vụ **khu vực**; bản thân một gateway không biến ứng dụng thành dịch vụ đa region. Backend nhiều instance cũng không giúp ích nếu mọi instance cùng phụ thuộc một thành phần lỗi đơn khác.

### Chi phí

Các khoản cần xem xét gồm SKU Standard_v2/WAF_v2, công suất/autoscale, xử lý lưu lượng, public IP, Azure Key Vault, backend compute, log ingestion/retention và những dịch vụ bảo mật đi kèm. Mô hình giá thay đổi theo SKU và region, nên dùng công cụ dự toán giá Azure cùng các số liệu traffic dự kiến, không suy ra giá từ ví dụ bài học.

Để kiểm soát chi phí, phân tách gateway theo ranh giới bảo mật/quản trị hợp lý, tránh dựng một gateway độc lập cho mọi ứng dụng nhỏ khi có thể dùng nhiều listener/rule an toàn, đồng thời không gom các ứng dụng có yêu cầu cô lập nghiêm ngặt vào cùng gateway chỉ vì tiết kiệm.

## 17. Bài thực hành: từ listener đến backend pool

**Bối cảnh:** Nhóm triển khai website `shop.example.com`. Azure Application Gateway nhận HTTPS từ Internet. Hai backend VM có private IP trong VNet:

| Thông số | Giá trị minh họa |
|---|---|
| Frontend hostname | `shop.example.com` |
| Frontend protocol/port | HTTPS / 443 |
| Frontend certificate | Chứng chỉ hợp lệ cho `shop.example.com` |
| Backend pool | `pool-shop` |
| Backend 1 | `10.20.1.10` |
| Backend 2 | `10.20.1.11` |
| Backend protocol/port | HTTPS / 8443 |
| Backend hostname | `shop.internal.example` |
| Custom probe | HTTPS `/healthz` với Host `shop.internal.example` |
| Routing | Basic rule tới `pool-shop` |
| Redirect | HTTP / 80 → HTTPS / 443 |

**Nhiệm vụ:**

1. Vẽ đường đi của request từ DNS đến frontend IP, listener, routing rule, backend pool và hai backend.
2. Chỉ ra nơi TLS session A kết thúc và TLS session B bắt đầu.
3. Giải thích vì sao chứng chỉ frontend và backend phải được kiểm tra **độc lập**.
4. Nêu các thuộc tính backend settings cần cấu hình cho `HTTPS :8443`.
5. Tạo checklist health probe và định nghĩa phản hồi Healthy.
6. Giả sử VM1 bị ngừng dịch vụ trong khi VM2 vẫn healthy: dự đoán hành vi routing và cách quan sát.
7. Giả sử cả hai VM báo Unhealthy dù mở trực tiếp app vẫn hoạt động: đề xuất thứ tự kiểm tra.
8. Nêu phương án giám sát certificate expiry, Backend health và 5xx.

### Lời giải tham khảo

**Luồng xử lý:**

```text
Client / DNS
    |
    | HTTPS/TLS A :443, host shop.example.com
    v
Application Gateway
    |
    +-- HTTPS listener (cert cho shop.example.com)
    |
    +-- Basic routing rule
    |
    +-- Backend pool: 10.20.1.10, 10.20.1.11
    |
    +-- Backend settings: HTTPS :8443
    |                       Host shop.internal.example
    |                       Custom probe /healthz
    |
    +==== TLS B ====> Backend healthy: shop.internal.example
```

TLS A kết thúc ở gateway; TLS B nối gateway với backend và được xác thực bằng chứng chỉ backend đáng tin cậy đúng hostname. Backend không thể dùng chứng chỉ chỉ có tên `api.other.example` nếu gateway xác thực `shop.internal.example`.

**Health:** probe nên sử dụng HTTPS port 8443, Host `shop.internal.example`, path `/healthz` và mong đợi phản hồi trong ngưỡng hợp lệ. VM1 Unhealthy sẽ không được chọn cho request theo cơ chế của gateway nếu VM2 còn healthy. Nếu cả hai Unhealthy, cần kiểm tra probe trước rồi đến kết nối, TLS và ứng dụng; không được tắt xác thực chứng chỉ để che giấu vấn đề.

**Nghiệm thu:** request tới `https://shop.example.com` không báo TLS error; HTTP port 80 chuyển sang HTTPS; Backend health hiển thị đúng trạng thái; truy cập qua một backend vẫn thành công khi backend kia ngừng trong thử nghiệm; log cho phép đối chiếu yêu cầu và nguyên nhân lỗi.

## 18. Tự kiểm tra kiến thức

**Câu 1.** TLS termination tại Application Gateway có nghĩa là gì?

A. Gateway chuyển nguyên phiên TLS mà không đọc HTTP.  
B. Gateway kết thúc TLS từ client để có thể xử lý HTTP và định tuyến Layer 7.  
C. Chứng chỉ của backend không còn cần thiết trong mọi trường hợp.

**Đáp án: B.** Nếu backend cũng dùng HTTPS, gateway tạo một phiên TLS khác tới backend.

**Câu 2.** Cặp thành phần nào quyết định listener gửi request tới backend nào và theo protocol/port nào?

**Đáp án:** **Request routing rule** chọn backend pool và **backend settings**. Listener chỉ định đầu vào nhận request.

**Câu 3.** Một gateway phục vụ hai host trên cùng frontend IP:443. Thành phần gì giúp phân biệt website?

**Đáp án:** **Multi-site listeners** với hostname tương ứng, kết hợp SNI và certificate phù hợp để nhận HTTPS.

**Câu 4.** Backend HTTPS trả chứng chỉ cho `internal.example.com` nhưng backend settings xác thực `shop.example.com`. Có thể có vấn đề gì?

**Đáp án:** Hostname mismatch trong xác thực chứng chỉ backend, khiến TLS handshake hoặc health check thất bại. Cần thiết kế tên host/backend certificate nhất quán.

**Câu 5.** Probe gửi GET `/` và nhận 401, nhưng ứng dụng trả 200 tại `/healthz`. Nên làm gì?

**Đáp án:** Cấu hình custom health probe dùng host/protocol/port/path phù hợp, ví dụ `/healthz`, và xác minh endpoint thực sự phản ánh khả năng sẵn sàng.

**Câu 6.** Cả hai backend Unhealthy. Việc tạo thêm listener có tự sửa được lỗi không?

**Đáp án:** Không. Cần kiểm tra network reachability, backend settings, host, certificate, probe và ứng dụng. Listener không thay thế backend health.

**Câu 7.** Frontend HTTPS, backend HTTP có nghĩa toàn bộ đường truyền đã được TLS bảo vệ?

**Đáp án:** Không. Chặng gateway → backend là HTTP không có TLS. Chọn HTTPS backend nếu chính sách yêu cầu mã hóa hai chặng.

**Câu 8.** Azure Load Balancer có thể tự đọc URL path `/api/*` rồi route theo đường dẫn như Application Gateway không?

**Đáp án:** Không. Azure Load Balancer cân bằng tải Layer 4, không thực hiện HTTP path routing.

**Câu 9.** Tại sao ứng dụng đôi khi redirect vô hạn sau khi đặt Application Gateway phía trước?

**Đáp án:** Ứng dụng có thể tưởng request gốc dùng HTTP vì chặng gateway → backend là HTTP. Cần cấu hình forwarded scheme/header và trusted proxy đúng, đồng thời xem lại redirect rule.

**Câu 10.** Application Gateway WAF có thay thế authentication và authorization trong ứng dụng không?

**Đáp án:** Không. WAF xử lý một số rủi ro HTTP Layer 7; ứng dụng vẫn phải xác thực người dùng và kiểm tra quyền ở từng chức năng.

Một kiến trúc phân phối HTTPS đáng tin cậy cần ghép đúng **certificate → frontend listener → routing rule → backend pool + settings → health probe**. Khi có lỗi, xác định sự cố xảy ra ở **TLS frontend**, **routing** hay **backend connectivity/TLS/health** sẽ giúp điều tra nhanh và an toàn hơn.
