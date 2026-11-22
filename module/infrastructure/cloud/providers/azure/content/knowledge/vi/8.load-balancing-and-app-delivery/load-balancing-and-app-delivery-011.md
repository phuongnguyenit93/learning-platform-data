# Chẩn đoán lỗi TLS, health probe và HTTP gateway

> **Chương:** Cân bằng tải và phân phối ứng dụng  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Vẽ đường đi của một yêu cầu HTTPS qua **Azure Application Gateway** và xác định vị trí có thể phát sinh lỗi.
2. Phân biệt lỗi TLS ở kết nối **client → gateway** với lỗi TLS ở kết nối **gateway → backend**.
3. Giải thích cách **health probe** chọn backend là `Healthy`, `Unhealthy` hoặc `Unknown`, và vì sao ứng dụng vẫn chạy nhưng bị đánh dấu không khỏe.
4. Phân tích mã HTTP `502`, `503`, `504`, lỗi chứng chỉ, redirect, lỗi WAF và các trường hợp DNS/mạng thường gặp.
5. Dùng Azure portal, Azure CLI, `curl`, `openssl` và Azure Monitor để khoanh vùng nguyên nhân bằng chứng cứ.
6. Lập một quy trình xử lý an toàn, có bước xác minh và theo dõi sau thay đổi.

## 1. Một request HTTPS đi qua những lớp nào?

Giả sử tổ chức triển khai trang API trên Azure:

- Người dùng truy cập `https://api.contoso.example/orders`.
- **Azure Application Gateway** nhận HTTPS tại frontend public IP.
- **Listener** lắng nghe cổng 443 và chọn website theo host name.
- **Request routing rule** chuyển request đến backend pool.
- Backend pool có hai VM hoặc các endpoint của ứng dụng ở mạng riêng.
- Backend HTTP settings xác định giao thức HTTP/HTTPS, port, timeout, host name và probe sử dụng.
- Health probe kiểm tra backend; gateway chỉ định tuyến đến backend được đánh giá khả dụng theo cấu hình.

~~~mermaid
flowchart LR
    C["Client\nBrowser / curl"]
    F["Frontend IP :443"]
    L["HTTPS listener\nCert + host name"]
    R["Routing rule\nURL path / host"]
    H["Backend settings\nHTTP(S), port, host"]
    P["Health probe\nHealthy?"]
    B["Backend pool\nAPI 10.20.2.4 / 10.20.2.5"]
    DB["Database / dependencies"]
    C -->|"TLS số 1"| F --> L --> R --> H
    H -->|"TLS số 2 nếu HTTPS backend"| B --> DB
    P -.->|"Đánh giá endpoint"| B
    P -.->|"Ảnh hưởng chọn backend"| R
~~~

Đây là sơ đồ logic: health probe chạy độc lập với request của người dùng. Không phải mỗi request đều chờ probe chạy xong.

### Hai kết nối TLS trong mô hình end-to-end HTTPS

Nếu frontend và backend cùng dùng HTTPS, **Application Gateway chấm dứt TLS phía client rồi thiết lập một kết nối TLS khác tới backend**. Đây không phải một đường TCP/TLS xuyên suốt nguyên vẹn giữa trình duyệt và máy backend.

| Kết nối | Endpoint phát chứng chỉ | Tên được kiểm tra | Lỗi thường quan sát |
| --- | --- | --- | --- |
| **Client → Gateway** | Chứng chỉ được gắn với HTTPS listener | Tên miền người dùng truy cập, ví dụ `api.contoso.example` | Trình duyệt báo chứng chỉ, TLS handshake thất bại; request có thể chưa tới HTTP gateway |
| **Gateway → Backend** | Chứng chỉ do máy chủ backend cung cấp | Host name/SNI phù hợp cấu hình backend và probe | Gateway không thiết lập được HTTPS, backend `Unhealthy`, có thể gây phản hồi `502` |

Nếu backend dùng **HTTP**, chỉ có TLS phía frontend; dữ liệu từ gateway đến backend không được mã hóa bằng TLS trên đoạn đó. Việc chọn HTTP backend hay HTTPS backend phải phù hợp yêu cầu bảo mật và kiến trúc nội bộ.

### Khác nhau giữa ba dịch vụ Azure dễ nhầm

| Thành phần | Lớp hoạt động chính | Vai trò health check/TLS | Tình huống |
| --- | --- | --- | --- |
| **Azure Application Gateway** | L7 HTTP/HTTPS | HTTPS listener, TLS termination, backend HTTPS, probe theo cấu hình HTTP settings | Website/API trong region, path-based routing, WAF |
| **Azure Front Door** | L7 ở biên toàn cầu | TLS phía client và kết nối origin, origin health probe; tên mục cấu hình và log khác Application Gateway | Ứng dụng đa vùng, CDN/edge routing, WAF |
| **Azure Load Balancer** | L4 TCP/UDP | Không chấm dứt TLS của ứng dụng; probe kiểm tra endpoint theo kiểu được hỗ trợ | Cân bằng tải kết nối TCP/UDP, không routing HTTP theo đường dẫn |

Bài học dùng **Application Gateway** làm ví dụ chính. Khi xử lý Front Door hoặc Load Balancer, giữ tư duy phân lớp nhưng dùng đúng health probe, chứng chỉ và telemetry **của sản phẩm đó**.

## 2. Phân loại lỗi từ tín hiệu đầu tiên

Người dùng thường báo “HTTPS lỗi” hoặc “gateway không lên”, nhưng biểu hiện có thể rất khác.

| Triệu chứng | Lớp cần kiểm tra trước | Giải thích sơ bộ |
| --- | --- | --- |
| Trình duyệt báo `ERR_CERT_AUTHORITY_INVALID` | Frontend TLS | Chứng chỉ không được client tin cậy |
| `ERR_CERT_COMMON_NAME_INVALID` hoặc tên miền không khớp | Frontend TLS | Chứng chỉ không bao phủ hostname |
| `curl` báo TLS handshake failure | TLS/cipher/version, SNI, đường mạng | Chưa xác định là frontend hay backend nếu chưa biết điểm kết nối |
| HTTP `502 Bad Gateway` | Gateway ↔ backend, backend health, TLS backend | Gateway không nhận được phản hồi hợp lệ từ upstream hoặc không có backend dùng được tùy nguyên nhân/sản phẩm |
| HTTP `503 Service Unavailable` | Khả dụng backend, quota hoặc origin/service | Có thể không có backend khỏe, service đang quá tải hoặc do sản phẩm khác trên đường đi |
| HTTP `504 Gateway Timeout` | Gateway/origin timeout | Upstream không đáp ứng trước thời hạn; cần phân biệt timeout request và timeout probe |
| HTTP `401/403` | Xác thực, phân quyền, WAF hoặc probe | Request có thể đến ứng dụng/WAF; không mặc nhiên là lỗi TLS |
| HTTP `301/302` | Redirect từ backend hoặc routing | Có thể là hành vi bình thường hoặc vòng lặp redirect |
| Một số URL chạy, URL khác lỗi | Path-based rule, backend pool, application endpoint | Các path có thể trỏ backend/settings khác nhau |
| Backend `Unhealthy` nhưng truy cập thẳng VM được | Probe path, hostname, TLS/SNI, source và routing | Request probe có thể khác request thử tay |
| Backend `Unknown` | Trạng thái gateway/đường kiểm tra/telemetry | Cần xem chi tiết; không mặc định là ứng dụng chết |

**Câu hỏi đầu tiên cần trả lời:** lỗi xuất hiện **trước khi nhận được phản hồi HTTP**, hay gateway đã trả về một HTTP status? Lỗi certificate ở trình duyệt thường xảy ra trước HTTP; mã 502 là phản hồi HTTP và cho thấy đã đi xa hơn trong chuỗi xử lý.

### Trình tự khoanh vùng năm điểm

1. **DNS và đường mạng:** tên miền người dùng có trỏ tới đúng frontend của gateway không?
2. **Frontend listener/TLS:** listener có đúng host, port, chứng chỉ và TLS policy không?
3. **Routing:** URL path, host và rule dẫn tới backend pool/settings nào?
4. **Backend health:** gateway thực sự nhìn backend là Healthy hay Unhealthy? Vì sao?
5. **Backend và phụ thuộc:** server có lắng nghe đúng cổng, trả đúng HTTP, chứng chỉ phù hợp và còn kết nối tới database/dịch vụ cần thiết không?

Một lỗi có thể xảy ra tại nhiều điểm cùng lúc. Để tránh sửa nhầm, luôn chọn kiểm tra có bằng chứng xác nhận tầng bị lỗi.

## 3. TLS hoạt động thế nào ở frontend?

### 3.1. Vai trò chứng chỉ và TLS handshake

Khi client truy cập `https://api.contoso.example`, trình duyệt kết nối tới gateway ở cổng 443 và gửi thông tin TLS, thường bao gồm **Server Name Indication (SNI)** để chỉ rõ hostname mong muốn. Gateway chọn chứng chỉ/listener tương ứng theo cấu hình.

Client sau đó kiểm tra:

- Chứng chỉ có được cấp cho `api.contoso.example` hay nằm trong danh sách **Subject Alternative Name (SAN)** hay không.
- Chứng chỉ còn hiệu lực, chuỗi chứng chỉ dẫn tới CA tin cậy của client hay không.
- TLS protocol/cipher có được hai bên hỗ trợ và không bị policy chặn.
- Các kiểm tra bảo mật bổ sung của ứng dụng/client, tùy môi trường.

**SAN** là nơi cần kiểm tra đầu tiên khi đối chiếu hostname; đừng chỉ nhìn tên file `.pfx` hoặc nhãn chứng chỉ trong Azure portal.

### 3.2. Các lỗi frontend TLS thường gặp

| Nguyên nhân | Dấu hiệu | Cách xác minh |
| --- | --- | --- |
| Chứng chỉ hết hạn hoặc chưa có hiệu lực | Browser báo validity/certificate error | Xem `Not Before`, `Not After` và thời gian hệ thống |
| SAN không khớp FQDN | Hostname mismatch | So sánh hostname truy cập với SAN |
| Chuỗi CA không đầy đủ hoặc CA riêng chưa được client tin cậy | Client báo authority/chain | Kiểm tra chain được server cung cấp và trust store của client |
| Listener gắn chứng chỉ không đúng | Một hostname gặp lỗi, hostname khác chạy | Xem multi-site listener, host name, binding và SNI |
| TLS policy quá hạn chế với client | Handshake failure, không có HTTP response | Kiểm tra TLS version/cipher hai phía, dùng client TLS hợp lệ |
| DNS trỏ nhầm frontend | Chứng chỉ của hệ thống khác được trả về | `nslookup`/`dig`, public IP, listener |
| Rotation qua Key Vault có sự cố | Sau thay đổi certificate, frontend gặp lỗi | Kiểm tra version/secret, managed identity, quyền truy cập và trạng thái gateway |

Đối với listener HTTPS của Application Gateway, chứng chỉ thường được cấu hình từ PFX hoặc tích hợp Key Vault theo khả năng SKU. Chứng chỉ phải có private key đúng và có thể được gateway sử dụng. Một file `.cer` chỉ chứa public certificate **không tự thay thế được** PFX cần cho TLS termination ở listener.

### 3.3. Phân biệt SNI và HTTP Host

Hai trường cùng liên quan tới tên miền nhưng ở **hai giai đoạn khác nhau**:

- **TLS SNI:** tên miền client gửi trong quá trình handshake để server chọn chứng chỉ/ngữ cảnh TLS.
- **HTTP Host header:** tên miền trong request HTTP sau khi TLS đã thiết lập, được gateway hoặc backend dùng để định tuyến virtual host.

Một client có thể gửi SNI đúng nhưng HTTP Host khác; tùy gateway, listener và routing rule, request có thể vào site sai hoặc bị từ chối. Backend cũng có thể dựa vào Host header khác với tên public.

**Vì vậy:** “Chứng chỉ hợp lệ” chưa chứng minh routing đúng; “Host header đúng” chưa chứng minh HTTPS handshake backend hợp lệ.

## 4. TLS từ Application Gateway tới backend

### 4.1. Vì sao backend HTTPS hay gây 502?

Ví dụ:

- Người dùng gọi `https://api.contoso.example`.
- HTTPS listener dùng chứng chỉ public có SAN `api.contoso.example` — hoàn toàn hợp lệ.
- Routing rule chuyển đến backend `api.internal.contoso.example:443`.
- Backend certificate có SAN `api.internal.contoso.example`.
- Backend settings lại gửi/tin rằng hostname là `10.20.2.4` hoặc `api.contoso.example`.

Gateway có thể không xác nhận được chứng chỉ backend vì **hostname không trùng tên trong cert**, hoặc vì chuỗi CA không được tin cậy. Health probe HTTPS cũng có thể thất bại vì chính vấn đề này.

Các bước TLS backend liên quan:

1. Gateway có đường mạng tới IP và port backend không?
2. Backend có chấp nhận TLS protocol/cipher mà gateway sử dụng không?
3. Hostname/SNI của kết nối backend có phù hợp với chứng chỉ backend không?
4. Chứng chỉ còn hạn và chuỗi CA có được gateway tin cậy theo cấu hình không?
5. Sau TLS, HTTP Host/path do gateway gửi có được backend chấp nhận không?

**Không sửa lỗi chứng chỉ backend bằng cách đổi certificate ở frontend listener** trừ khi thực sự đó là cùng chứng chỉ được dùng và xác định đúng nguyên nhân.

### 4.2. Backend settings và Host name override

Trong Azure Application Gateway, backend settings có thể chỉ định:

- Protocol: `HTTP` hoặc `HTTPS`.
- Port: ví dụ `80` hoặc `443`.
- Host name phía backend: lấy theo cấu hình, địa chỉ backend hoặc override rõ ràng tùy trường hợp.
- Trusted root certificates khi backend dùng CA riêng và SKU/cấu hình yêu cầu.
- Request timeout và custom health probe.

Đối với backend HTTPS, **tên hostname dùng để xác minh chứng chỉ và SNI phải được cấu hình nhất quán với cert backend**. Đối với virtual-host application, Host header cũng cần đúng site mà server phục vụ.

Ví dụ cấu hình khái niệm:

~~~text
Frontend:       https://api.contoso.example:443
Listener cert:  SAN = api.contoso.example

Backend pool:   10.20.2.4, 10.20.2.5
Backend HTTPS:  port = 443
Backend host:   api.internal.contoso.example
Backend cert:   SAN = api.internal.contoso.example
Health probe:   HTTPS /ready, host = api.internal.contoso.example
~~~

Nếu backend chỉ có private IP trong pool nhưng certificate được cấp cho FQDN, đừng mặc định dùng IP làm tên xác minh TLS. Cấu hình host backend và probe phù hợp để tránh lỗi mismatch.

### 4.3. CA công cộng và CA nội bộ

Nếu backend certificate do một **CA công cộng được gateway tin cậy** ký, Application Gateway v2 có thể xác minh qua kho CA tin cậy theo cơ chế dịch vụ. Nếu backend dùng **Private CA**, cấu hình trusted root certificate đúng cách cho backend settings có thể cần thiết.

Khi xử lý certificate chain:

- Xác nhận chứng chỉ **leaf** có SAN đúng hostname và còn hiệu lực.
- Kiểm tra các **intermediate CA** cần thiết được trình bày đúng.
- Xác định **root CA** cần tin cậy ở đúng nơi (frontend client khác với backend gateway).
- Xác minh backend thật sự đang trình bày cert mới sau rotation.
- Không tắt kiểm tra chứng chỉ ở production chỉ để “cho request chạy”.

### 4.4. TLS policy không phải health policy

**TLS policy** quyết định protocol/cipher hoặc mức bảo mật của kết nối. **Health probe** quyết định endpoint backend có được coi là khả dụng không. Một backend có thể không qua probe vì:

- Kết nối TLS thất bại do cert/hostname.
- TLS thành công nhưng URL probe trả HTTP `401`.
- TLS và HTTP đều tốt nhưng probe timeout vì endpoint quá chậm.

Chẩn đoán phải xem chính **lý do Unhealthy** và đối chiếu với kiểm thử TLS, HTTP path.

## 5. Health probe kiểm tra điều gì?

### 5.1. Cơ chế cơ bản

Application Gateway liên tục gửi probe tới các backend target theo **probe configuration** tương ứng với backend settings. Gateway dùng kết quả để quyết định backend nào được đưa vào cân bằng tải.

Các yếu tố quan trọng:

| Thuộc tính | Ý nghĩa | Lỗi cấu hình hay gặp |
| --- | --- | --- |
| **Protocol** | HTTP hoặc HTTPS | Backend nghe HTTPS nhưng probe gửi HTTP |
| **Port** | Cổng probe dùng; có thể theo backend settings hoặc port riêng | API chạy 8443 nhưng probe kiểm tra 443 |
| **Host** | Hostname dùng trong probe, ảnh hưởng HTTP virtual host và HTTPS | Host mặc định không khớp backend virtual host/certificate |
| **Path** | Đường dẫn được gọi như `/healthz` | Dùng `/` trả 401/404 hoặc redirect ngoài ý muốn |
| **Interval** | Chu kỳ probe | Quá dài khiến phát hiện chậm; quá ngắn tăng tần suất |
| **Timeout** | Thời gian chờ mỗi probe | Dịch vụ trả chậm hơn timeout |
| **Unhealthy threshold** | Số lần probe lỗi liên tiếp trước khi coi backend không khỏe | Không phản ánh đúng độ nhạy cần có |
| **Healthy status match** | Mã HTTP được chấp nhận | Probe trả mã ngoài dải chấp nhận |
| **Body match** (nếu dùng) | Nội dung mong đợi trong response | Endpoint thay đổi format/body |

Với **Application Gateway**, dải mã HTTP mặc định thường chấp nhận **200–399** khi dùng probe cấu hình thông thường, nhưng nên xác minh đúng loại gateway và custom probe đang triển khai. Đừng mang quy tắc này áp dụng cho **Azure Load Balancer** hoặc **Front Door**, vì chúng có cơ chế health probe riêng.

### 5.2. Default probe và custom probe

Default probe của Application Gateway có thể dùng một **Host header mặc định** và path `/`. Với nhiều ứng dụng hiện đại:

- Ứng dụng chỉ trả kết quả đúng khi Host là `api.internal.contoso.example`.
- Endpoint `/` trả `404` vì API chỉ có `/v1`.
- Endpoint `/` chuyển người dùng tới login rồi trả `401` hoặc redirect.
- Backend HTTPS certificate không phù hợp hostname mặc định.
- Backend chạy trên port hoặc đường dẫn riêng.

Khi đó default probe có thể đánh dấu backend **Unhealthy** dù người vận hành `curl` tới URL khác vẫn thấy API chạy.

**Custom probe** thường phù hợp hơn cho backend HTTPS và những ứng dụng có virtual host. Ví dụ:

~~~text
Probe name:     probe-api-ready
Protocol:       HTTPS
Host:           api.internal.contoso.example
Path:           /ready
Port:           443 (hoặc dùng port trong backend settings)
Interval:       30 giây (ví dụ)
Timeout:        20 giây (ví dụ)
Healthy codes:  200–399, hoặc dải được thống nhất
Expected:       HTTP 200 khi backend sẵn sàng nhận request
~~~

Các số giây chỉ là **ví dụ thiết kế**, không phải mặc định được đảm bảo cho mọi SKU/phiên bản. Hãy chọn tùy theo SLO, độ trễ và trạng thái ứng dụng.

### 5.3. Phân biệt liveness, readiness và dependency check

Một health endpoint tốt cần cho gateway biết **backend có nên nhận request mới không**:

- **Liveness:** tiến trình còn chạy hay không? Có thể trả 200 dù backend chưa phục vụ request được.
- **Readiness:** backend đã khởi động, có thể nhận request và các thành phần bắt buộc sẵn sàng chưa?
- **Deep dependency check:** kiểm tra hàng loạt dependency. Nếu quá nặng hoặc phụ thuộc dịch vụ không thiết yếu, có thể làm tất cả backend Unhealthy trong một sự cố thoáng qua.

Ví dụ API Node.js hoặc Java có `/ready` trả HTTP 200 khi hoàn thành khởi tạo và có các dependency thiết yếu. Endpoint này nên **nhanh, ổn định, không đòi tương tác đăng nhập**, và chỉ tiết lộ thông tin cần thiết. Có thể giới hạn truy cập bằng chính sách mạng thay vì yêu cầu phiên đăng nhập người dùng cho probe.

### 5.4. Probe timeout khác request timeout

- **Probe timeout:** thời gian gateway đợi một health check trước khi coi lần kiểm tra đó thất bại.
- **Backend request timeout:** thời gian gateway chờ phản hồi của request người dùng từ backend.

Có thể có tình huống `/ready` trả trong 100 ms nhưng endpoint xuất báo cáo mất 70 giây và bị gateway timeout vì backend request timeout chỉ 30 giây. **Backend vẫn Healthy**, trong khi người dùng gặp `502` hoặc `504` tùy hành vi/thiết bị. Đừng điều chỉnh probe khi vấn đề là thời gian xử lý request thật.

## 6. Các nguyên nhân khiến backend Unhealthy

### 6.1. Sai network path hoặc port

Health probe của Application Gateway xuất phát từ hạ tầng gateway và cần kết nối đến endpoint backend qua mạng. Những vấn đề hay gặp:

- Backend NSG/firewall không cho phép lưu lượng từ Application Gateway subnet tới port ứng dụng.
- Route table (UDR) hoặc thiết bị mạng trung gian định tuyến sai.
- Backend chỉ lắng nghe trên `127.0.0.1`, không lắng nghe interface mà gateway truy cập.
- Backend service đang tắt hoặc nghe port khác.
- DNS trả IP cũ hoặc IP không đến được từ mạng gateway.
- Backend pool khai báo địa chỉ/hostname sai.

Kiểm tra cấu hình Application Gateway subnet và NSG phải tuân theo yêu cầu nền tảng của SKU đang dùng. Đừng xóa toàn bộ NSG hoặc mở rộng quyền truy cập tùy tiện để thử lỗi.

### 6.2. Sai HTTP status hoặc chuyển hướng

Ví dụ:

~~~text
GET /                → 404
GET /ready           → 200
GET /account         → 302 đến /login
GET /api/private     → 401 nếu không có token
~~~

Nếu default probe gọi `/`, backend có thể bị đánh dấu Unhealthy. Cách sửa thích hợp là gán custom probe tới `/ready`, bảo đảm endpoint có ý nghĩa sẵn sàng phục vụ.

Nếu probe nhận `301/302` và dải chấp nhận bao gồm mã đó, gateway có thể coi backend Healthy **mặc dù URL đích chuyển hướng không hoạt động**. Vì vậy, chỉ kiểm tra mã HTTP chưa đủ; endpoint readiness nên trả một mã rõ ràng như `200` khi thành công.

### 6.3. Host header và SNI không khớp

Giả sử backend dùng Nginx với virtual host:

~~~nginx
server {
    listen 443 ssl;
    server_name api.internal.contoso.example;

    ssl_certificate     /etc/nginx/certs/api-fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/api-key.pem;

    location = /ready {
        return 200 "ready\n";
        add_header Content-Type text/plain;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

Đoạn cấu hình **minh họa backend**, không phải yêu cầu sửa máy thực tế. Nếu probe chỉ gửi `Host: 127.0.0.1` hoặc SNI không khớp, Nginx có thể phục vụ default server với cert hoặc route khác. Cần kiểm tra host trong probe và backend settings, cùng cách Nginx ánh xạ TLS server block.

### 6.4. Backend certificate không được tin cậy

Có thể thấy thông báo backend health liên quan chứng chỉ như không thể xác minh certificate chain hoặc common name mismatch. Khi gặp trường hợp này:

1. Xem certificate thực sự được backend trả ra.
2. Kiểm tra SAN với hostname mà gateway dùng.
3. Kiểm tra ngày hết hạn và chain.
4. Xem backend settings đã có trusted root certificate phù hợp khi dùng private CA chưa.
5. Kiểm tra custom probe có cùng protocol/host/port hay không.

Đừng nhầm “CA được trình duyệt trên laptop tin cậy” với “gateway tin cậy backend CA”. Hai phía có kho chứng chỉ/ngữ cảnh xác minh khác nhau.

### 6.5. Có sự cố ứng dụng hoặc tài nguyên

Health endpoint có thể trả `500`, `503` hoặc timeout khi:

- API đang khởi động sau deployment.
- Thread pool, CPU, memory hoặc connection pool quá tải.
- Database bắt buộc không kết nối được.
- Pod/container/VM bị crash hoặc đang recycle.
- Probe endpoint phụ thuộc vào một dịch vụ thứ ba chậm.

Đối chiếu application logs, deployment timeline, metric tài nguyên và số backend Healthy/Unhealthy để xác định lỗi bắt đầu ở backend hay gateway.

## 7. Chẩn đoán thực tế bằng Azure portal và Azure CLI

### 7.1. Kiểm tra đúng subscription, gateway và backend health

Các lệnh sau **chỉ đọc thông tin**, phù hợp để quan sát trong môi trường được cấp quyền:

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Chọn đúng subscription được phép truy cập nếu cần.
az account set --subscription "<SUBSCRIPTION_ID>"

# Xác nhận gateway đích và trạng thái provisioning.
az network application-gateway show \
  --resource-group rg-edge-prod \
  --name appgw-api-prod \
  --query "{name:name, location:location, provisioningState:provisioningState}" \
  --output json

# Xem trạng thái từng backend mà Application Gateway đang đánh giá.
az network application-gateway show-backend-health \
  --resource-group rg-edge-prod \
  --name appgw-api-prod \
  --output json
~~~

Thay tên resource group và gateway bằng đối tượng thực tế. Đầu ra backend health có thể gồm target, trạng thái và thông báo chi tiết. Hãy ghi nguyên văn **reason/message**, thời điểm quan sát và backend settings liên quan.

**Trong portal:** mở **Application Gateway → Backend health** (hoặc khu vực trạng thái backend tương ứng). Nếu một pool có hai backend và chỉ một backend Unhealthy, ưu tiên kiểm tra target cụ thể. Nếu tất cả đều Unhealthy ngay sau thay đổi settings/probe, nghi ngờ cấu hình chung trước.

### 7.2. Đối chiếu listeners, rules, backend settings và probes

~~~bash
# HTTPS listeners: hostname và frontend liên quan.
az network application-gateway http-listener list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json

# Routing rules: listener liên kết backend pool/settings nào.
az network application-gateway rule list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json

# Protocol, port, host override, timeout của backend.
az network application-gateway http-settings list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json

# Probe path, protocol, host, status match và timeout.
az network application-gateway probe list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json
~~~

Các lệnh trên giả định phiên bản Azure CLI hỗ trợ nhóm lệnh này. Nếu tên tham số khác ở phiên bản bạn dùng, kiểm tra trợ giúp `az network application-gateway ... --help`. Không chạy lệnh `update` chỉ để kiểm tra.

### 7.3. Kiểm tra chứng chỉ listener

~~~bash
az network application-gateway ssl-cert list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json
~~~

Lệnh giúp xem metadata cấu hình; **không mặc định hiển thị private key, chứng chỉ đầy đủ hoặc mọi thông tin xác minh CA**. Cần kết hợp truy vấn TLS từ máy khách và kiểm tra cấu hình listener trong portal.

### 7.4. Ghi lại mối quan hệ cấu hình

Một bảng ngắn giúp tránh nhìn nhầm rule:

| Thành phần | Ví dụ | Cần xác minh |
| --- | --- | --- |
| Public FQDN | `api.contoso.example` | DNS trỏ đúng frontend |
| Listener | `listener-api-443` | HTTPS, host, cert, port |
| Rule | `rule-api` | Rule priority, path, pool/settings |
| Backend pool | `pool-api` | Đúng hai backend `10.20.2.4/.5` |
| Backend settings | `https-api-443` | HTTPS, 443, host, timeout |
| Probe | `probe-api-ready` | HTTPS, `/ready`, hostname đúng |
| Backend health | Healthy/Unhealthy | Lý do cho từng server |

Nếu có URL path map, cần kiểm tra **path thực tế người dùng truy cập** và backend settings mà path đó chọn. Một gateway có thể có listener khỏe nhưng rule dẫn `/admin/*` tới pool khác đang lỗi.

## 8. Kiểm tra từ máy khách và từ mạng backend

### 8.1. Kiểm tra DNS và HTTP/TLS phía public

~~~bash
# Xem địa chỉ mà DNS public trả về.
nslookup api.contoso.example

# Xem status và response headers, theo dõi redirect.
curl -I -v https://api.contoso.example/

# Gọi endpoint thật; không dùng -k trong kiểm tra chứng chỉ thông thường.
curl -v https://api.contoso.example/ready
~~~

Ghi lại hostname, IP resolved, HTTP status, certificate name, thời gian và response headers. `curl -I` gửi HEAD request; nếu ứng dụng không hỗ trợ HEAD, dùng `curl -v` với GET. Nếu có gateway khác hoặc CDN trước Application Gateway, hãy xác định request thực sự đi qua thiết bị nào.

### 8.2. Thử đúng một frontend IP mà vẫn giữ hostname/SNI

Khi DNS đang chuyển đổi, có thể cần xác minh listener tại một IP cụ thể:

~~~bash
# 203.0.113.10 là IP dùng cho tài liệu, hãy thay bằng frontend IP thật.
curl -v \
  --resolve api.contoso.example:443:203.0.113.10 \
  https://api.contoso.example/ready
~~~

`--resolve` ép kết nối tới IP được chỉ định nhưng vẫn giữ URL hostname cho SNI và HTTP Host. Đây là cách tốt hơn `curl https://203.0.113.10` khi chứng chỉ được cấp theo FQDN.

Nếu phải dùng `-k`/`--insecure` để chẩn đoán, kết quả chỉ có giá trị chứng minh ứng dụng có phản hồi **khi bỏ qua xác minh certificate**; không coi đó là lời giải cho production hoặc bằng chứng TLS đang đúng.

### 8.3. Kiểm tra certificate phía backend

Từ VM kiểm thử **được cấp quyền và có đường mạng tới backend**:

~~~bash
# Kết nối tới IP riêng nhưng gửi SNI đúng hostname chứng chỉ backend.
openssl s_client \
  -connect 10.20.2.4:443 \
  -servername api.internal.contoso.example \
  -showcerts
~~~

Trong kết quả, kiểm tra subject/SAN, issuer, ngày hiệu lực, chain và lỗi handshake. Lưu ý `openssl s_client` có thể hiển thị chain mà vẫn không từ chối kết nối ngay cả khi xác minh thất bại; cần đọc mã xác minh hoặc dùng tùy chọn kiểm tra phù hợp.

Kiểm tra rõ tên máy với phiên bản OpenSSL có hỗ trợ:

~~~bash
openssl s_client \
  -connect 10.20.2.4:443 \
  -servername api.internal.contoso.example \
  -verify_hostname api.internal.contoso.example \
  -verify_return_error
~~~

Trust store trên VM chạy OpenSSL **có thể khác trust store của Application Gateway**. Phép thử giúp nhận diện lỗi nhưng không tự chứng minh gateway đã tin cậy backend certificate.

### 8.4. Kiểm tra HTTP path và Host trên backend

~~~bash
# Dùng kết nối TLS hostname đúng, đồng thời ép IP backend.
curl -v \
  --resolve api.internal.contoso.example:443:10.20.2.4 \
  https://api.internal.contoso.example/ready
~~~

Điều cần quan sát:

- HTTPS handshake có thành công không?
- Backend certificate có SAN trùng hostname không?
- `GET /ready` trả status nào?
- Response có nhanh hơn probe timeout không?
- Backend `10.20.2.5` có cùng kết quả không?

**Không suy luận từ một backend sang toàn pool.** Nếu một máy được cấu hình khác, gateway có thể trả lỗi không ổn định tùy máy nhận request.

### 8.5. Kiểm tra kết nối TCP khi không dùng OpenSSL

Trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName api.internal.contoso.example -Port 443
~~~

Trên Linux:

~~~bash
nc -vz api.internal.contoso.example 443
~~~

Các lệnh này giúp kiểm tra kết nối TCP từ máy hiện tại, **không kiểm tra TLS certificate hoặc HTTP response**. Kết quả thành công từ laptop/VPN chưa chứng minh Application Gateway subnet cũng đi được cùng đường mạng.

## 9. Diễn giải HTTP 502, 503 và 504 đúng bối cảnh

### 9.1. 502 Bad Gateway

Ở ứng dụng dùng Application Gateway, 502 thường khiến bạn kiểm tra:

- Backend pool có backend Healthy nào không?
- Gateway tới backend có đúng port và protocol không?
- Backend TLS handshake có thất bại vì certificate chain/SNI/hostname không?
- Backend gửi HTTP response không hợp lệ hay reset connection?
- Gateway và backend có đường mạng không?
- Có deployment gần đây hoặc sự cố backend không?

**502 không phải lúc nào cũng do chứng chỉ.** Cần đọc backend health detail, access logs và timeline thay đổi.

### 9.2. 503 Service Unavailable

503 có thể được trả về bởi gateway/front door/origin hoặc **chính ứng dụng backend**. Điều quan trọng là xác định **ai trả mã này**. Các trường cần tìm trong log thường gồm frontend status, backend/origin status, backend server, route và transaction/correlation ID.

Nếu backend trả `503` vì đang bảo trì, gateway có thể chuyển tiếp mã đó tới client dù bản thân gateway hoạt động bình thường. Trong một số sản phẩm/đường đi, 503 còn xuất hiện khi không có origin khả dụng hoặc hệ thống quá tải. Không dùng mỗi mã status để xác định nguyên nhân.

### 9.3. 504 Gateway Timeout

504 thường dẫn tới câu hỏi: có upstream nào **không hoàn tất request đúng thời hạn**?

- Request xử lý quá lâu trong API?
- App thread hoặc database connection pool bị nghẽn?
- Backend settings/request timeout thấp hơn thời gian xử lý cần thiết?
- Một thiết bị trung gian khác có timeout riêng?
- Có tình trạng kết nối bị ngắt, DNS chậm, hoặc server không phản hồi không?

**Điều chỉnh timeout chỉ sau khi hiểu vì sao backend chậm.** Tăng timeout bừa bãi có thể che lỗi hiệu năng và khiến request treo lâu hơn.

### 9.4. Phân biệt mã từ gateway và mã từ backend

Giả sử log cho thấy:

~~~text
Time:                2026-11-20 10:15:00 UTC
Client path:         GET /orders
Gateway status:      502
Backend status:      (không có response hợp lệ)
Backend health:      Unhealthy
Probe error:         TLS certificate hostname mismatch
~~~

Đây là **dữ liệu mô phỏng**. Nó hỗ trợ giả thuyết lỗi gateway ↔ backend, khác với tình huống:

~~~text
Gateway status:      503
Backend status:      503
Backend health:      Healthy
App log:             Database connection pool exhausted
~~~

Trường hợp thứ hai nghiêng về lỗi ứng dụng hoặc dependency. Trong dữ liệu thật, tên trường và cách ghi log phụ thuộc tài nguyên/SKU và chế độ log.

### Bảng quyết định nhanh

| Bằng chứng | Giả thuyết mạnh hơn | Bước tiếp |
| --- | --- | --- |
| Client chưa thiết lập được TLS đến gateway | Frontend cert/listener/TLS policy | Kiểm tra SNI, SAN, chain, DNS |
| Client vào được HTTPS nhưng nhận 502, tất cả backend Unhealthy | Probe/settings/TLS backend/network | Đọc backend health reason, thử backend từ mạng phù hợp |
| Một backend Healthy, một Unhealthy | Cấu hình hoặc runtime lệch giữa backend | So sánh cert, port, app logs của từng target |
| Probe Healthy nhưng một endpoint trả 504 | Request thực tế chậm hơn timeout | Kiểm tra request timing, backend/DB |
| `/` trả 404 nhưng `/ready` trả 200 | Sai probe path | Dùng custom probe rõ ràng |
| Probe trả 401 | Health endpoint yêu cầu auth | Thiết kế endpoint readiness phù hợp, giữ bảo vệ mạng |
| Chỉ lỗi một hostname trên cùng frontend IP | Multi-site listener/SNI/rule | Kiểm tra cert và host binding cho hostname đó |
| Chỉ lỗi sau khi bật HTTPS backend | Certificate trust/SNI hoặc HTTPS port | So sánh protocol, cert và backend settings |
| Client nhận 403, WAF logs ghi block | WAF policy | Xem rule, false positive, không sửa probe tùy tiện |

## 10. Azure Monitor: đo thay vì đoán

### 10.1. Metric nên đối chiếu

Để điều tra Application Gateway, theo dõi những nhóm metric mà SKU hỗ trợ:

- **Healthy host count** và **Unhealthy host count**, có thể lọc theo pool/settings.
- **Failed requests**, **Total requests** và mã HTTP status ở phía frontend.
- **Response time / latency**, throughput, connection và năng lực gateway.
- Các chỉ số WAF/block khi dùng WAF SKU.
- Backend VM/container/API: CPU, memory, request latency, error rate và dependency health.

Ví dụ, nếu healthy host count tụt từ 2 xuống 0 ngay khi triển khai certificate mới, đây là bằng chứng ưu tiên kiểm tra TLS backend, probe hoặc thay đổi chung. Nếu Healthy vẫn là 2 nhưng `/reports` tăng latency, xem path mapping, API và database trước.

Tên metric và dimensions trong portal có thể khác theo SKU; chọn **metric thực tế được tài nguyên phát hành**.

### 10.2. Diagnostic settings và access logs

Trong Azure portal:

1. Chọn Application Gateway cần điều tra.
2. Mở **Diagnostic settings**.
3. Chọn các log khả dụng như **Access log** và **Firewall log** nếu dùng WAF.
4. Chọn đích phù hợp, ví dụ **Log Analytics workspace**, Storage Account hoặc Event Hubs.
5. Chọn kiểu bảng lưu log (resource-specific hoặc legacy `AzureDiagnostics`) theo nhu cầu và khả năng hiện hành.
6. Xác minh sự kiện thực sự xuất hiện; việc bật log sau một sự cố không tự tạo lại những bản ghi quá khứ chưa được lưu.

Log có thể chứa client IP, URL path, hostname và chi tiết kết nối. Cần có chính sách quyền truy cập, retention và chi phí nạp/lưu giữ dữ liệu.

### 10.3. KQL cho access logs dạng resource-specific

Khi Application Gateway gửi access logs vào bảng `AGWAccessLogs` của Log Analytics:

~~~kusto
AGWAccessLogs
| where TimeGenerated >= ago(2h)
| summarize Requests = count()
    by bin(TimeGenerated, 5m), Status = tostring(HttpStatus)
| order by TimeGenerated asc
~~~

Truy vấn đếm số request theo mã HTTP trong từng khoảng năm phút. Sử dụng trong **đúng workspace có bảng `AGWAccessLogs`**; bảng chưa có dữ liệu sẽ không tạo kết quả, và workspace chưa triển khai schema đó có thể báo lỗi bảng không tồn tại.

Để tìm biến động `502`/`503`/`504`:

~~~kusto
AGWAccessLogs
| where TimeGenerated >= ago(24h)
| where tostring(HttpStatus) in ("502", "503", "504")
| summarize Errors = count()
    by bin(TimeGenerated, 15m), Status = tostring(HttpStatus)
| order by TimeGenerated asc
~~~

Khi cần điều tra một request cụ thể, xem thêm các trường về request URI, backend status, server routed và transaction ID **nếu chúng tồn tại trong schema thực tế**. Không mặc định mọi phiên bản log cung cấp tất cả trường.

### 10.4. Nếu log được lưu theo định dạng AzureDiagnostics

Ở workspace sử dụng legacy table `AzureDiagnostics`:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(2h)
| where Category == "ApplicationGatewayAccessLog"
| summarize Events = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Nếu không thấy bảng, không kết luận “Application Gateway không có lỗi”. Có thể chưa bật diagnostic settings, đích log sai workspace, chưa đến dữ liệu hoặc đang dùng **resource-specific tables** khác.

### 10.5. Một dashboard điều tra nên trả lời gì?

| Panel | Câu hỏi |
| --- | --- |
| Healthy/Unhealthy backend count | Có backend nào mất trạng thái Healthy đúng thời điểm lỗi? |
| HTTP status theo thời gian | Lỗi 502/503/504 tăng từ lúc nào, ảnh hưởng URL nào? |
| Request latency và timeout | Backend phản hồi chậm hay gateway không kết nối được? |
| WAF blocks | 403 đến từ WAF hay backend? |
| Backend metrics/logs | CPU, memory, app exception, database errors có tăng không? |
| Deployment/certificate changes | Có đổi cert, probe, listener, DNS hoặc rule trước khi lỗi không? |

Cần giữ thời gian **UTC** hoặc chuyển đổi múi giờ có ghi chú. Không so sánh biểu đồ 10:15 UTC với log 10:15 giờ địa phương như thể chúng cùng một thời điểm.

## 11. Ba ca chẩn đoán có hướng dẫn

### Ca A — Cập nhật chứng chỉ backend xong thì 502

**Bối cảnh:** Gateway đã dùng HTTPS frontend từ trước. Sau khi đội backend thay certificate trên hai VM, khách hàng thấy `502`. Trong Backend health, cả hai VM là `Unhealthy`, thông báo liên quan TLS hostname.

**Thông tin mô phỏng:**

~~~text
Frontend URL:         https://api.contoso.example
Backend FQDN config:  api.internal.contoso.example
Certificate SAN mới: api-new.internal.contoso.example
Probe:                HTTPS /ready
Backend port:         443
~~~

**Phân tích:**

1. Frontend TLS vẫn hoạt động vì client nhận HTTP `502` thay vì lỗi cert của browser.
2. Gateway kết nối backend HTTPS và xác minh hostname `api.internal.contoso.example`.
3. SAN mới chỉ bao phủ `api-new.internal.contoso.example`.
4. Probe và request backend có nguy cơ thất bại do mismatch.

**Hướng khắc phục:** phát hành/cấu hình cert backend có SAN đúng hostname đang sử dụng **hoặc** thay đổi backend hostname/định tuyến theo thiết kế đã được phê duyệt và đồng bộ DNS, SNI, Host header, probe. Không đổi thành `HTTP` chỉ để né xác minh TLS nếu chính sách yêu cầu mã hóa end-to-end.

**Xác minh:** `openssl` kiểm tra hostname, `curl --resolve` đến từng backend, Backend health trở lại Healthy, request thật trả mã mong đợi và không còn 502.

### Ca B — API chạy bình thường nhưng probe trả 401

**Bối cảnh:** Một backend trả `HTTP 200` cho request có bearer token, nhưng custom probe gọi `/api/status` mà không có token và nhận `401`. Gateway xem backend Unhealthy.

**Nguyên nhân:** health probe không mang phiên đăng nhập của người dùng và không nên phụ thuộc vào token dành cho request ứng dụng thông thường.

**Khắc phục:** tạo `/ready` riêng, trả `200` khi service thực sự sẵn sàng, hoặc dùng cơ chế kiểm tra được gateway hỗ trợ và chính sách phù hợp. Hạn chế thông tin nhạy cảm, chỉ cho phép đường mạng cần thiết. Tránh “sửa” bằng cách chấp nhận toàn bộ mã `401` như Healthy, vì làm vậy có thể bỏ qua trạng thái readiness thực.

**Xác minh:** thử `/ready` từ đường mạng phù hợp, xem Backend health và thử lại các chức năng API cần xác thực.

### Ca C — Gateway Healthy nhưng endpoint báo cáo trả 504

**Bối cảnh:** Probe `GET /ready` trả `200` trong 50 ms, cả hai backend Healthy. Riêng `GET /reports/monthly` mất hơn một phút và request qua gateway báo timeout.

**Phân tích:** probe đánh giá khả năng nhận request, không đo được độ trễ của mọi endpoint. Truy vấn báo cáo có thể quá lâu so với request timeout trong backend settings hoặc một proxy khác.

**Hướng xử lý:** xem request tracing/log backend, database query, connection pool, thời gian xử lý thực tế và timeout ở từng lớp. Cải thiện backend, dùng xử lý bất đồng bộ cho tác vụ dài hoặc điều chỉnh timeout **có căn cứ**.

**Xác minh:** request trả kết quả trong SLO được thống nhất, tỷ lệ timeout giảm và các backend tiếp tục Healthy.

## 12. Quy trình xử lý sự cố từng bước

Giả sử bạn trực vận hành và nhận cảnh báo “tỷ lệ 502 trên Application Gateway tăng”.

### Bước 1 — Chụp trạng thái và xác định phạm vi

Ghi nhận thời gian, subscription, gateway, hostname, URL/path, số lượng người dùng ảnh hưởng, status code và một transaction/correlation ID nếu có. Không thay đổi cấu hình ngay khi chưa biết phạm vi.

### Bước 2 — Kiểm tra DNS và frontend TLS

Từ client bị ảnh hưởng, xác nhận DNS đến đúng frontend; thử `curl -v` với hostname và kiểm tra certificate/SAN/expiry. Nếu không thiết lập được TLS, ưu tiên listener, DNS, policy và certificate rotation.

### Bước 3 — Xác định route thực tế

Kiểm tra listener, rule, URL path map, backend pool và backend settings. Đừng suy từ tên API ra backend pool; phải xác minh rule hiện dùng.

### Bước 4 — Xem Backend health

Kiểm tra từng target Healthy/Unhealthy/Unknown. Lưu thông báo chi tiết. Nếu tất cả Unhealthy, so sánh các yếu tố dùng chung như probe, TLS hostname, backend settings và networking. Nếu chỉ một target hỏng, kiểm tra cấu hình/ứng dụng máy đó.

### Bước 5 — Kiểm tra probe và backend từ mạng phù hợp

So sánh probe protocol, host, path, port, timeout, accepted status. Từ host kiểm thử hợp lệ, kiểm tra TCP, TLS certificate và HTTP `/ready` trên **từng backend**. Lưu ý đường mạng của máy kiểm thử có thể khác subnet gateway.

### Bước 6 — Đối chiếu log và metric

Tìm mốc thay đổi healthy host count, request error và backend latency. Đối chiếu Application Gateway logs với app/dependency logs và hoạt động triển khai gần nhất.

### Bước 7 — Sửa đúng nguyên nhân

Ví dụ:

- Sai SAN → phát hành/cài đúng backend cert hoặc đồng bộ hostname.
- Probe `/` trả 404 → cấu hình custom probe tới `/ready`.
- Backend port sai → sửa backend settings khi đã xác nhận port thật.
- NSG chặn → cập nhật rule giới hạn đúng nguồn/port cần thiết.
- Backend quá tải → xử lý hiệu năng/capacity theo nguyên nhân.
- WAF false positive → phân tích rule log trước khi tinh chỉnh ngoại lệ.

Thay đổi theo quy trình phê duyệt hiện hành. Tránh tắt HTTPS validation, mở firewall rộng hoặc bỏ mọi health probe như cách “khôi phục nhanh”.

### Bước 8 — Xác minh sau thay đổi và rút kinh nghiệm

Xác nhận từng backend trở lại Healthy, các URL đại diện trả status đúng, TLS valid, lỗi 502/503/504 giảm và SLO ổn định. Ghi thay đổi, người thực hiện, mốc thời gian và cách phòng tái diễn.

## 13. Thực hành phân tích không cần tạo tài nguyên

### Tình huống

Một ứng dụng có:

- Public FQDN: `shop.contoso.example`.
- Azure Application Gateway HTTPS listener: port 443, certificate SAN bao phủ `shop.contoso.example`.
- Backend pool: `10.30.2.10` và `10.30.2.11`.
- Backend settings: HTTPS port 443; host `shop-api.internal.contoso.example`.
- Custom probe: HTTPS `/ready`, host `shop-api.internal.contoso.example`.
- Backend certificate SAN: `shop-api.internal.contoso.example`.
- Request timeout: 30 giây (giả định).

Trong lúc triển khai bản mới, bạn nhận được dữ liệu sau:

| Mốc UTC | Backend .10 | Backend .11 | Client status | Ghi chú |
| --- | --- | --- | --- | --- |
| 08:00 | Healthy | Healthy | 200 | Bình thường |
| 08:07 | Unhealthy | Healthy | Thỉnh thoảng 200 | .10 đã deploy bản mới |
| 08:10 | Unhealthy | Unhealthy | 502 tăng | .11 cũng được deploy |
| 08:12 | Unhealthy | Unhealthy | 502 | Probe `GET /ready` trả 401 trên cả hai |

**Câu hỏi 1.** Chứng chỉ frontend có phải nghi phạm hàng đầu không?

*Đáp án:* Không. Client nhận được HTTP 502 và listener đã có chứng chỉ đúng. Bằng chứng cho thấy probe backend chuyển từ Healthy sang Unhealthy sau deployment.

**Câu hỏi 2.** Probe `/ready` trả 401 nói gì?

*Đáp án:* Backend có khả năng đang yêu cầu authentication với health endpoint hoặc bị middleware chặn. Cần xác minh tại backend. Với matcher chấp nhận 200–399, 401 làm probe thất bại.

**Câu hỏi 3.** Nên thay đổi accepted status thành `200–499` để nhanh đưa backend Healthy không?

*Đáp án:* Không nên. Làm vậy đánh dấu cả 401/403/404 là khỏe, che nguyên nhân và có thể định tuyến request tới backend chưa phục vụ đúng.

**Câu hỏi 4.** Sửa middleware để `/ready` trả 200 khi service thực sự sẵn sàng xong thì cần kiểm gì?

*Đáp án:* Kiểm tra endpoint từ mạng phù hợp, TLS vẫn hợp lệ, cả hai backend Healthy, application request xác thực vẫn vận hành, tỷ lệ 502 giảm và không phát sinh phơi lộ dữ liệu nhạy cảm từ health endpoint.

### Bài thực hành KQL (khi có Log Analytics)

Nếu workspace đã thu thập access logs dạng `AGWAccessLogs`, dùng:

~~~kusto
AGWAccessLogs
| where TimeGenerated >= ago(1h)
| summarize Requests = count() by HttpStatus = tostring(HttpStatus)
| order by Requests desc
~~~

Ghi lại mã phổ biến nhất. Sau đó so sánh với **Backend health** cùng mốc thời gian; nếu chưa có dữ liệu access log, nêu lý do cần kiểm tra diagnostic settings thay vì kết luận gateway không gặp lỗi.

### Bài thực hành nhận diện sai cấu hình TLS

Cho ba phương án:

| Phương án | Listener certificate | Backend hostname | Backend certificate SAN | Đánh giá |
| --- | --- | --- | --- | --- |
| A | `shop.contoso.example` | `shop-api.internal.contoso.example` | `shop-api.internal.contoso.example` | Tên phù hợp, tiếp tục kiểm tra trust chain/port/path |
| B | `shop.contoso.example` | `shop-api.internal.contoso.example` | `new-shop-api.internal.contoso.example` | Mismatch phía backend, có nguy cơ probe/TLS lỗi |
| C | `other.contoso.example` | `shop-api.internal.contoso.example` | `shop-api.internal.contoso.example` | Mismatch phía frontend với `shop.contoso.example` |

**Yêu cầu:** xác định kết nối TLS nào có vấn đề trong từng phương án, và nêu một phép kiểm tra tương ứng.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “502 chắc chắn do TLS.” | 502 còn có thể do backend unresponsive, network, reset hoặc health/routing. |
| “Probe Healthy nghĩa là toàn bộ API chạy tốt.” | Probe chỉ kiểm tra điều kiện đã định nghĩa trên endpoint/path cụ thể. |
| “Trình duyệt tin cert nên gateway chắc chắn tin cert backend.” | Frontend trust và backend trust dùng ngữ cảnh khác nhau. |
| “Đổi cert listener sẽ sửa cert backend.” | Đây là hai kết nối TLS riêng khi Application Gateway termination + HTTPS backend. |
| “Probe 401 có thể chấp nhận như Healthy để sửa nhanh.” | Cần thiết kế health endpoint thực sự chỉ báo readiness. |
| “TCP 443 mở nghĩa là TLS và HTTP đều đúng.” | TCP thành công chưa xác minh certificate, SNI hoặc response. |
| “Client nhận 503 nghĩa là gateway hỏng.” | 503 có thể được backend trả và gateway chuyển tiếp; cần xem log. |
| “Tăng timeout sẽ giải quyết mọi 504.” | Cần điều tra request latency, hiệu năng và dependency. |
| “Front Door probe giống Application Gateway probe.” | Mỗi sản phẩm có cấu hình, hành vi, metric và log riêng. |
| “Không có log chứng tỏ không có lỗi.” | Có thể chưa bật diagnostic settings hoặc log gửi sang workspace khác. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Gateway có HTTPS listener cert đúng `api.example.com`, nhưng backend cert chỉ chứa `internal-v2.example.com` trong SAN còn backend settings dùng host `internal-v1.example.com`. Lỗi nằm ở TLS nào?

**Đáp án:** TLS giữa gateway và backend có nguy cơ không xác minh được hostname. Frontend TLS có thể vẫn hoạt động bình thường.

**Câu 2.** Một backend trả 200 cho `/ready` nhưng `/reports` thường timeout. Vì sao Backend health vẫn Healthy?

**Đáp án:** Health probe kiểm tra readiness endpoint, không đo tất cả đường xử lý. Cần theo dõi request thật và backend request timeout.

**Câu 3.** Vì sao `curl --resolve` thường tốt hơn gọi trực tiếp `https://10.20.2.4` để chẩn đoán HTTPS virtual host?

**Đáp án:** Nó cho phép giữ đúng hostname trong URL cho TLS SNI và HTTP Host, đồng thời ép kết nối tới IP cần thử.

**Câu 4.** Backend health là Unhealthy và reason báo probe trả 404. Hãy nêu hai nguyên nhân có thể.

**Đáp án:** Sai path (ví dụ default `/` không tồn tại), hoặc Host header khiến request vào virtual host/default site không có endpoint đó.

**Câu 5.** Hai backend đều Unhealthy ngay sau khi sửa HTTPS settings. Bạn ưu tiên kiểm tra gì?

**Đáp án:** Protocol/port, hostname/SNI, chứng chỉ/CA, custom probe và network path chung, rồi kiểm tra riêng từng backend.

**Câu 6.** Nếu client nhận 403, có phải probe đang đánh dấu backend Unhealthy?

**Đáp án:** Chưa đủ căn cứ. 403 có thể từ WAF, gateway, authentication hoặc backend. Cần xem WAF/access logs và Backend health riêng.

**Câu 7.** Có nên bật `curl -k` thường xuyên trong giám sát production vì API “vẫn trả 200”?

**Đáp án:** Không. `-k` bỏ qua xác minh chứng chỉ phía client và có thể che lỗi TLS. Chỉ dùng tạm thời trong tình huống chẩn đoán đã kiểm soát, không coi là cách sửa.

## Ghi nhớ

- Luôn xác định **request dừng tại DNS, frontend TLS, routing, backend health, backend TLS hay ứng dụng** trước khi thay đổi cấu hình.
- Application Gateway có thể có **hai kết nối TLS độc lập**: client → gateway và gateway → backend.
- **TLS SNI, HTTP Host, certificate SAN và backend hostname** phải nhất quán với kiến trúc và routing.
- **Health probe** cần kiểm tra đúng protocol, port, host, path và mã trạng thái; `/ready` thường phù hợp hơn một URL yêu cầu đăng nhập.
- **502/503/504** là dấu hiệu để điều tra theo sản phẩm và log; một mã đơn lẻ chưa xác định được nguồn gây lỗi.
- Dùng **Backend health + Azure Monitor + lệnh kiểm tra có kiểm soát** để đối chiếu nguyên nhân, theo dõi cải thiện và bảo đảm ứng dụng phục hồi thực sự.
