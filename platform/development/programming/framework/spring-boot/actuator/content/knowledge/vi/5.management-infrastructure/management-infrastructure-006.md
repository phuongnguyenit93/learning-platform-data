# Giới hạn khả năng truy cập qua mạng nội bộ, reverse proxy và firewall

## 1. Vì sao Actuator cần một đường truy cập riêng?

API nghiệp vụ phục vụ người dùng; Actuator phục vụ giám sát và vận hành ứng dụng. Hai nhóm người dùng này thường cần những đường truy cập khác nhau. Ví dụ, khách hàng cần gọi API đặt hàng, còn hệ thống giám sát chỉ cần đọc tình trạng hoạt động và một số chỉ số.

Một mật khẩu đúng vẫn không phải lý do để mở cổng quản trị cho toàn Internet. Ngược lại, một địa chỉ thuộc mạng nội bộ cũng chưa chứng minh người gọi có quyền quản trị. Khi thiết kế hạ tầng, cần trả lời hai câu hỏi riêng:

- **Khả năng tiếp cận qua mạng:** máy nào có thể thiết lập kết nối đến dịch vụ quản trị?
- **Quyền sử dụng:** sau khi kết nối được, danh tính nào được đọc hoặc thực hiện từng thao tác?

Bài này tập trung vào câu hỏi thứ nhất và mối liên hệ với câu hỏi thứ hai. Các ví dụ dùng tên thuộc tính của **Spring Boot 3.3.x** và mô hình ứng dụng web chạy bằng JAR. Bài thực hành dùng Java 21, Spring MVC và Spring Boot 3.3.13 để có một phiên bản xác định; đây không phải chỉ dẫn chọn phiên bản mới nhất cho sản phẩm.

### Các thuật ngữ sẽ dùng

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| Địa chỉ lắng nghe, hay bind address | Địa chỉ giao diện mạng mà tiến trình nhận kết nối |
| Loopback | Đường kết nối quay về chính môi trường mạng hiện tại, như `127.0.0.1` |
| Mạng quản trị | Phân đoạn mạng dành cho giám sát và vận hành, có nguồn truy cập được kiểm soát |
| Reverse proxy | Máy chủ nhận yêu cầu rồi chuyển tiếp đến ứng dụng phía sau |
| Firewall | Bộ lọc kết nối/gói tin theo chính sách mạng |
| Danh sách cho phép, hay allowlist | Chỉ cho phép những nguồn hoặc đường dẫn đã xác định |
| Ranh giới tin cậy | Vị trí phải kiểm tra dữ liệu hoặc danh tính trước khi tin thông tin từ phía khác |

Hãy đi theo thứ tự: vẽ đường kết nối → chọn địa chỉ/cổng → đặt quy tắc tại proxy và firewall → kiểm chứng từ nhiều vị trí.

## 2. Ghép đúng các lớp kiểm soát

Một yêu cầu đọc Actuator phải vượt qua nhiều điều kiện:

```text
Máy gọi
  → có tuyến mạng đến đích
  → firewall cho phép kết nối
  → có tiến trình lắng nghe đúng địa chỉ và cổng
  → reverse proxy cho phép đường dẫn, nếu đi qua proxy
  → endpoint được công bố qua HTTP
  → chính sách xác thực/phân quyền cho phép, nếu được cấu hình
  → Actuator xử lý
```

Đây là mô hình phân tích đường đi, không khẳng định thứ tự xử lý nội bộ giống nhau ở mọi hạ tầng. Chẳng hạn, firewall có thể xuất hiện ở cả trước và sau proxy.

Trong Spring Boot 3.3, `management.endpoints.web.exposure.include` chọn endpoint được công bố qua HTTP; nó không chọn subnet được phép kết nối. `health` là endpoint được công bố qua HTTP mặc định. Chính sách Spring Security là một lớp riêng; khi tự khai báo `SecurityFilterChain`, phải tự bảo đảm quy tắc bảo vệ cần thiết. [Tài liệu Endpoints 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

Ví dụ, một endpoint được đưa vào `include` vẫn có thể không đến được từ máy giám sát vì firewall chặn cổng. Ngược lại, cho phép kết nối đến cổng không làm xuất hiện endpoint chưa được công bố.

**Mục tiêu thiết kế:** với mỗi đường có thể đến Actuator, phải chỉ ra nguồn được phép, điểm chặn nguồn khác và bằng chứng kiểm tra. Đừng chỉ xem một URL qua tên miền công khai rồi kết luận toàn bộ hệ thống đã được giới hạn.

## 3. Chọn mô hình mạng phù hợp

### 3.1. Proxy và ứng dụng cùng máy

```text
Internet → NGINX :443 → 127.0.0.1:8080, API nghiệp vụ

Mạng vận hành → NGINX 10.20.0.10:9443
             → 127.0.0.1:9090, Actuator

Kết nối từ máy khác → địa chỉ máy chủ:9090
                   → không có listener tương ứng
```

Ở đây, `10.20.0.10` là địa chỉ minh họa phải thực sự được gán cho máy chạy NGINX. NGINX và JVM phải nằm trong **cùng không gian mạng** để NGINX truy cập được loopback của JVM.

Mô hình này thu hẹp đường vào backend: máy khác phải đi qua listener quản trị của NGINX. Tuy vậy, tiến trình trên cùng máy vẫn có thể truy cập loopback; tài khoản máy chủ bị chiếm quyền hoặc lỗi SSRF có khả năng tạo thêm đường đi. Vì thế, loopback không thay cho chính sách quyền.

### 3.2. Proxy và ứng dụng khác máy

Nếu proxy ở máy A, JVM ở máy B, `127.0.0.1` trên A là chính A. Muốn proxy kết nối đến JVM, dùng địa chỉ riêng thực sự của B, rồi giới hạn nguồn ở firewall của B:

```text
Proxy quản trị 10.20.0.10
  → firewall ứng dụng: chỉ nhận từ proxy cần thiết
  → JVM 10.20.0.20:9090
```

Nếu hệ thống giám sát truy cập trực tiếp B thì phải cấp quyền mạng cho chính nguồn đó. Không thêm cả dải mạng lớn chỉ để làm một lần kiểm tra thành công.

### 3.3. Cùng cổng và khác cổng

| Phương án | Có thể kiểm soát ở đâu? | Điểm cần cân nhắc |
| --- | --- | --- |
| API và Actuator cùng cổng | Proxy theo đường dẫn và chính sách ứng dụng | Firewall TCP thông thường không phân biệt API với Actuator trên cùng cổng |
| Actuator dùng cổng riêng | Có thêm khả năng lọc theo cổng, địa chỉ lắng nghe và tuyến mạng | Cổng mới vẫn có thể bị mở công khai nếu cấu hình mạng sai |
| Không cần Actuator qua HTTP | Tắt đường HTTP quản trị | Cần chọn phương thức giám sát khác phù hợp |

Đổi `/actuator` thành một đường khó đoán chỉ đổi tên đường dẫn; chính sách truy cập vẫn phải được thiết kế đầy đủ.

## 4. Cấu hình địa chỉ và cổng trong Spring Boot

Với phương án proxy và JVM cùng máy, cấu hình nền có thể là:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  forward-headers-strategy: none

management:
  server:
    address: 127.0.0.1
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      show-details: never
      show-components: never
```

`server.address` áp dụng cho listener chính; `management.server.address` áp dụng cho listener quản trị riêng. Trong Spring Boot 3.3, cấu hình địa chỉ quản trị khác chỉ được hỗ trợ khi cổng quản trị khác cổng chính. Tắt HTTP quản trị bằng `management.server.port=-1` là một phương án khi không cần kênh này. [Monitoring and Management Over HTTP 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

Cấu hình trên lựa chọn hai listener loopback. Chúng được dùng lại trong bài thực hành phía dưới. Việc chỉ công bố `health` và `info` là quyết định của ví dụ; một hệ thống thu thập Prometheus phải bổ sung đúng thư viện và endpoint cần thiết, rồi mở đúng đường cho bộ thu thập.

`show-details` và `show-components` giới hạn nội dung trả về của health; chúng không phải quy tắc lọc IP. Chọn endpoint ít nhất cần dùng, và chọn nguồn truy cập ít nhất cần dùng là hai quyết định bổ sung cho nhau. [Danh mục thuộc tính Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

Nếu JVM nằm trên máy riêng thay vì cùng proxy, phần thay thế có thể là:

```yaml
management:
  server:
    address: 10.20.0.20
    port: 9090
```

Đây là **đoạn thay thế**, không phải một tài liệu YAML thứ hai để ghép thêm trùng khóa `management`. Địa chỉ phải thuộc giao diện mạng của máy chạy JVM. Không thể lấy địa chỉ riêng bất kỳ rồi mong tiến trình tự tạo giao diện tương ứng.

Sau khi triển khai, kiểm tra cấu hình có hiệu lực từ listener thực tế. Biến môi trường, tham số khởi động hoặc profile triển khai có thể làm kết quả khác với file đang đọc.

## 5. Reverse proxy: tách lối vào công khai và lối vào quản trị

Ví dụ dưới đây là **hai khối `server` đặt trong ngữ cảnh `http` của NGINX**, không phải toàn bộ `nginx.conf`. NGINX và JVM dùng chung máy; backend vẫn là hai listener loopback ở phần 4.

Điều kiện triển khai:

- Máy có địa chỉ riêng `10.20.0.10`.
- Các file chứng thư/khóa TLS nêu trong cấu hình đã được cấp phù hợp với tên miền.
- Nguồn vận hành mà NGINX thực sự nhìn thấy thuộc `10.20.30.0/24`.
- Proxy giữ cơ chế xác thực cần thiết của hệ thống; đoạn này minh họa phần giới hạn mạng và định tuyến.

### 5.1. Lối vào công khai chỉ chuyển đến cổng nghiệp vụ

```nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/tls/app.crt;
    ssl_certificate_key /etc/nginx/tls/app.key;

    location = /actuator {
        return 404;
    }

    location ^~ /actuator/ {
        return 404;
    }

    location / {
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:8080;
    }
}
```

Hai quy tắc đầu bao phủ cả đường gốc `/actuator` và các đường con theo cấu hình đang dùng. `location =` là khớp chính xác; `^~` dành ưu tiên cho tiền tố phù hợp trước các location biểu thức chính quy. Khi cấu hình thực tế có thêm virtual host, rewrite hoặc location khác, cần kiểm tra lại toàn bộ đường đi. [NGINX location](https://nginx.org/en/docs/http/ngx_http_core_module.html#location)

Giới hạn quan trọng hơn trong mô hình này là **upstream công khai chỉ trỏ cổng 8080**. Không tạo một đường quản trị khác dưới tên `/internal`, một virtual host dự phòng hoặc một HTTP listener phụ rồi chuyển nó sang 9090 mà quên chính sách tương đương.

Nếu thay base path hoặc context path, phải cập nhật và thử lại quy tắc proxy. Chuỗi `/actuator` trong ví dụ không tự bám theo cấu hình Spring Boot.

### 5.2. Lối vào quản trị nhận từ subnet đã chọn

```nginx
server {
    listen 10.20.0.10:9443 ssl;
    server_name ops.example.com;

    ssl_certificate     /etc/nginx/tls/ops.crt;
    ssl_certificate_key /etc/nginx/tls/ops.key;

    allow 10.20.30.0/24;
    deny all;

    location = /actuator/health {
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:9090;
    }

    location = /actuator/info {
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:9090;
    }

    location / {
        return 404;
    }
}
```

NGINX xét các quy tắc `allow`/`deny` theo thứ tự đến khi khớp. Trong ví dụ, nguồn được phép đi vào hai location proxy là subnet đã nêu; nguồn còn lại nhận từ chối tại lớp kiểm soát truy cập. Các location không khai báo lại `allow`/`deny` nên nhận các quy tắc này từ mức server. [NGINX access module](https://nginx.org/en/docs/http/ngx_http_access_module.html)

Đường không thuộc hai endpoint đã chọn trả 404 bằng location dự phòng. Không dùng mã trả về của đường dự phòng để suy luận rằng ACL đã chạy: lệnh `return` có thể kết thúc yêu cầu trước giai đoạn kiểm soát truy cập.

Các `proxy_pass` không có phần URI phía sau cổng nên giữ đường yêu cầu cho backend. Tránh thêm dấu `/` cuối hoặc một rewrite mà chưa hiểu cách NGINX thay phần URI. [NGINX proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)

Nếu cần nhóm health có đường con, chỉ thêm những đường được dùng thực tế; cấu hình exact-match hiện tại cố ý chưa cho phép chúng. Tương tự, cần endpoint khác thì bổ sung cả công bố HTTP, đường proxy và quyền ứng dụng tương ứng.

### 5.3. TLS và danh tính

Kết nối từ máy vận hành qua mạng đến proxy nên dùng TLS với kiểm tra chứng thư. Nếu proxy và JVM khác máy, cân nhắc TLS cho cả chặng proxy–JVM theo yêu cầu hạ tầng.

Có thể thêm mTLS ở lối vào quản trị để xác minh máy gọi, hoặc giữ cơ chế xác thực của ứng dụng. Danh sách IP chỉ mô tả nguồn mạng, đặc biệt khi nhiều người cùng đi qua một VPN/NAT; nó không phân biệt từng người dùng trong nguồn đó.

## 6. Firewall: giới hạn kết nối trước khi HTTP được xử lý

Trước khi viết lệnh, lập bảng chính sách cho mô hình cùng máy:

| Đích | Nguồn được phép | Chính sách dự kiến |
| --- | --- | --- |
| NGINX 443/TCP | Nguồn người dùng của sản phẩm | Cho phép theo yêu cầu API nghiệp vụ |
| NGINX 10.20.0.10:9443/TCP | Mạng vận hành 10.20.30.0/24 | Chỉ cho phép subnet này |
| JVM 8080/TCP | Tiến trình trên cùng máy | Listener loopback, không mở trực tiếp từ xa |
| JVM 9090/TCP | Proxy/tiến trình trên cùng máy | Listener loopback, không mở trực tiếp từ xa |
| SSH 22/TCP | Nguồn quản trị máy chủ đã phê duyệt | Quy tắc riêng, không mở rộng theo API |

Với một máy Ubuntu lab mới, UFW đang được quản lý có chủ đích và chưa có quy tắc mở rộng xung đột, có thể diễn đạt một phần chính sách như sau:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow proto tcp from 10.20.30.0/24 to any port 22
sudo ufw allow 443/tcp
sudo ufw allow proto tcp from 10.20.30.0/24 to 10.20.0.10 port 9443
sudo ufw enable
sudo ufw status numbered
```

Đây là ví dụ cấu hình cho **máy lab thuộc mô hình đã nêu**, không phải lệnh phải chạy để đọc bài. Trước khi bật firewall trên máy đang quản trị từ xa, nguồn SSH thực tế phải khớp chính sách và phải có đường khôi phục truy cập. Không tự đổi default policy trên hệ thống đang dùng mà chưa rà soát các dịch vụ khác.

UFW hỗ trợ quy tắc theo nguồn/đích/cổng và có `--dry-run` để xem trước. Phải đọc trạng thái hiện tại: default deny không tự xóa một quy tắc allow rộng đã tồn tại. [Ubuntu Server: Firewall](https://ubuntu.com/server/docs/how-to/security/firewalls/)

Trong cloud, áp dụng cùng bảng chính sách cho security group/firewall và load balancer. Nếu nhiều tập quy tắc cho phép cùng áp dụng, phải xem kết quả kết hợp; chỉ thêm một quy tắc hẹp không chứng minh quy tắc rộng cũ đã mất hiệu lực.

Đối với mô hình khác máy, firewall trên máy JVM phải chặn truy cập trực tiếp đến backend, chỉ nhận từ proxy hoặc bộ thu thập được chỉ định. Một ACL tốt trên proxy sẽ bị bỏ qua nếu máy gọi còn truy cập được cổng 9090 của JVM qua đường khác.

### IPv4 và IPv6 phải được xét riêng

`0.0.0.0` biểu thị mọi địa chỉ IPv4 cục bộ; `::` là địa chỉ wildcard IPv6. Khả năng một listener IPv6 nhận cả IPv4 phụ thuộc hệ điều hành/cấu hình socket. Không suy luận trạng thái IPv6 từ một lần thử IPv4.

Đọc cả listener, bản ghi DNS A/AAAA và quy tắc mạng tương ứng. Nếu chỉ thiết kế đường quản trị IPv4, phải xác nhận không có listener hay tuyến công bố IPv6 ngoài ý muốn.

## 7. Không biến forwarded header thành giấy phép truy cập

Sau reverse proxy có hai thông tin khác nhau:

- Địa chỉ đầu bên kia của kết nối TCP mà từng lớp nhìn thấy.
- Địa chỉ được một HTTP header khai báo là địa chỉ người gọi ban đầu.

Một máy ngoài mạng có thể tự gửi:

```http
X-Forwarded-For: 10.20.30.25
```

Header này không làm địa chỉ nguồn của gói TCP trở thành `10.20.30.25`. Trong cấu hình NGINX trực tiếp nhận kết nối ở phần 5, ACL mặc định không dựa vào header tự khai báo đó.

Nếu có load balancer phía trước NGINX, NGINX có thể chỉ thấy IP của load balancer. Khi đó:

1. Xác định chính xác proxy tin cậy và đường kết nối đến nó.
2. Chặn đường truy cập trực tiếp có thể bỏ qua proxy đó.
3. Proxy ở ranh giới phải loại bỏ hoặc ghi lại header do máy ngoài gửi.
4. Chỉ khôi phục địa chỉ người gọi từ proxy đã được tin cậy.
5. Kiểm tra lại IP mà ACL và nhật ký thực sự sử dụng, kể cả khi có NAT.

NGINX real-IP module có `set_real_ip_from`, `real_ip_header` và `real_ip_recursive` để cấu hình quan hệ này. Không khai báo toàn Internet là nguồn được tin cậy. Việc dùng module cũng đòi hỏi bản NGINX được xây dựng với hỗ trợ tương ứng. [NGINX real-IP module](https://nginx.org/en/docs/http/ngx_http_realip_module.html)

Phía Spring Boot, `server.forward-headers-strategy` điều khiển cách xử lý thông tin chuyển tiếp. `NATIVE` dùng cơ chế của web server; `FRAMEWORK` dùng hỗ trợ của Spring Framework. Các lựa chọn này không tự xác thực máy gửi header. Bài lab giữ `none` vì không cần suy ra địa chỉ hay giao thức từ proxy. [Spring Boot 3.3: Front-end Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)

Nếu ứng dụng cần tạo URL/redirect đúng khi TLS kết thúc ở proxy, hãy thiết kế và thử riêng chuỗi tin cậy đó. Chỉ bật đọc forwarded header chưa đủ để bảo vệ một kiểm tra IP trong mã ứng dụng. [Spring Framework: Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)

## 8. Container và Kubernetes: mạng nội bộ có nhiều phạm vi

### 8.1. Loopback của container khác loopback của máy chủ

Hai container thông thường không chia sẻ loopback. NGINX trong container A không thể dùng `127.0.0.1:9090` để gọi JVM ở container B. Cần dùng địa chỉ/tên dịch vụ trong mạng container, và listener JVM phải nhận kết nối trên giao diện phù hợp.

Cũng cần tách hai quyết định:

- JVM lắng nghe ở đâu **bên trong container**.
- Docker công bố cổng nào, trên địa chỉ nào **của host**.

Ví dụ ánh xạ sau dành cho tình huống JVM nhận kết nối trên cổng 9090 của giao diện container:

```text
127.0.0.1:9090:9090
```

Nó mô tả cổng host bind vào loopback; không phải yêu cầu JVM bind loopback bên trong container. Với mạng bridge thông thường, nếu JVM chỉ nghe `127.0.0.1` trong container, lưu lượng chuyển đến địa chỉ giao diện container sẽ không đến listener đó.

Docker công bố cổng không ghi rõ địa chỉ host có thể làm cổng truy cập được từ bên ngoài. Không công bố cổng quản trị nếu chỉ các container được phép cần gọi nó; đồng thời kiểm tra các container cùng mạng vì chúng cũng có thể tiếp cận dịch vụ. [Docker: Port Publishing](https://docs.docker.com/engine/network/port-publishing/)

Trên Linux, đường chuyển tiếp của Docker có thể đi trước các quy tắc UFW thông thường. Vì vậy, nhìn thấy UFW deny chưa chứng minh cổng container đã bị chặn. Kiểm tra cách Docker quản lý firewall và thử từ máy khác sau khi publish. [Docker: Packet Filtering and Firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/)

### 8.2. Kubernetes

Không thêm cổng quản trị vào Ingress/LoadBalancer công khai chỉ vì đã có một Service nội bộ khác. Service kiểu ClusterIP không tự tạo danh sách pod được phép gọi.

NetworkPolicy có thể giới hạn kết nối giữa các pod nếu bộ mạng của cụm thực thi nó. Các policy cộng dồn quyền cho phép; một policy rộng khác có thể làm phạm vi lớn hơn dự kiến. Nếu cả nguồn và đích bị cô lập, kết nối phải được cả egress nguồn và ingress đích cho phép. [Kubernetes: Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

Khi áp dụng, xác định nguồn thực tế của bộ thu thập và health probe. Không mở toàn cụm để chữa một probe thất bại mà chưa biết probe xuất phát từ đâu.

## 9. Bài thực hành cục bộ: kiểm chứng proxy và header giả

Bài này dùng Linux hoặc WSL có Java 21, Maven 3.9+, NGINX và `curl`. Chạy JVM và NGINX trực tiếp trong cùng môi trường mạng, không đặt một tiến trình trên Windows và tiến trình còn lại trong container/WSL khác.

Mục tiêu là quan sát đường đi và ACL. Tất cả listener đều bind loopback và dùng HTTP; bài này chưa mô phỏng TLS, VPN hay firewall ở máy thật.

### 9.1. Tạo ứng dụng độc lập

Tạo thư mục làm việc riêng với cấu trúc:

```text
actuator-network-lab/
├── pom.xml
├── nginx.conf
└── src/main/
    ├── java/lab/NetworkLabApplication.java
    └── resources/application.yml
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>lab</groupId>
    <artifactId>actuator-network-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/lab/NetworkLabApplication.java`:

```java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class NetworkLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(NetworkLabApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "hello\n";
    }
}
```

Dùng nguyên cấu hình YAML ở phần 4 làm `src/main/resources/application.yml`. Dự án này không thêm Spring Security để tách riêng hiện tượng mạng/ACL; chưa dùng cấu hình lab làm chính sách bảo vệ cho một dịch vụ quản trị thật.

Đây là chương trình Spring Boot có dependency, nên dùng Maven để biên dịch/đóng gói thay vì chạy `javac` riêng trên một file:

```bash
mvn package
java -jar target/actuator-network-lab-1.0.0.jar
```

Lần đầu cần truy cập kho Maven để tải dependency. Giữ JVM chạy ở terminal thứ nhất và đợi ứng dụng khởi động thành công.

### 9.2. Cấu hình NGINX lab

Đặt nội dung sau vào `nginx.conf` tại thư mục gốc bài lab. Đây là **file cấu hình hoàn chỉnh cho tiến trình NGINX lab riêng**, khác các khối production minh họa ở phần 5.

```nginx
pid nginx.pid;
error_log error.log;

events {
    worker_connections 128;
}

http {
    access_log access.log;

    server {
        listen 127.0.0.1:8088;
        server_name localhost;

        location = /actuator {
            return 404;
        }

        location ^~ /actuator/ {
            return 404;
        }

        location / {
            proxy_pass http://127.0.0.1:8080;
        }
    }

    server {
        listen 127.0.0.1:9099;
        server_name localhost;

        location = /actuator/health {
            allow 127.0.0.1;
            deny all;

            proxy_pass http://127.0.0.1:9090;
        }

        location / {
            return 404;
        }
    }
}
```

Mở terminal thứ hai tại thư mục gốc bài lab. Các cổng 8080, 9090, 8088 và 9099 phải đang trống:

```bash
nginx -p "$PWD/" -c nginx.conf -t
nginx -p "$PWD/" -c nginx.conf -g 'daemon off;'
```

Lệnh đầu kiểm tra cấu hình; lệnh sau giữ NGINX ở foreground. Nếu hệ thống đã có NGINX khác, dùng đúng lệnh lab này và không thay cấu hình dịch vụ đang chạy.

### 9.3. Kiểm tra bằng curl

Trong terminal thứ ba, gọi trực tiếp API nghiệp vụ:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8080/hello
curl --noproxy '*' -sS http://127.0.0.1:8088/hello
```

Mỗi lệnh in đúng một dòng:

```text
hello
```

API nghiệp vụ vẫn hoạt động khi đi qua cổng proxy công khai mô phỏng. Tiếp theo chỉ in HTTP status để dễ so sánh:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:9090/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8088/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  --interface 127.0.0.1 \
  http://127.0.0.1:9099/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  --interface 127.0.0.2 \
  http://127.0.0.1:9099/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  --interface 127.0.0.2 \
  -H 'X-Forwarded-For: 127.0.0.1' \
  http://127.0.0.1:9099/actuator/health
```

Với đúng cấu hình, ứng dụng khỏe và môi trường Linux cho phép dùng `127.0.0.2` làm địa chỉ nguồn loopback, năm lệnh lần lượt có stdout dự kiến:

```text
200
404
200
403
403
```

Giải thích:

1. Gọi trực tiếp listener quản trị cục bộ thành công.
2. Proxy nghiệp vụ chặn đường Actuator.
3. Proxy quản trị cho nguồn `127.0.0.1`.
4. Nguồn `127.0.0.2` không thuộc allowlist một địa chỉ.
5. Header tự nhận là `127.0.0.1` không thay kết quả ACL.

`127.0.0.2` vẫn là loopback; nó chỉ mô phỏng một nguồn khác cho ACL. Nếu `curl --interface` không bind được nguồn này, bài kiểm tra đó chưa thực hiện được, không được ghi nhận là firewall đã chặn.

Thử thêm hai trường hợp:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:9099/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:9090/actuator/info
```

Stdout dự kiến lần lượt là `404` và `200`. Endpoint info có trong danh sách công bố HTTP, nhưng proxy quản trị lab chỉ chuyển tiếp health. Đây là ví dụ cụ thể về việc kết quả truy cập là giao của nhiều lớp chính sách.

Kết thúc bằng Ctrl+C ở các terminal chạy NGINX/JVM. Bài lab chỉ kiểm chứng định tuyến và ACL cục bộ; muốn kết luận không thể truy cập từ xa phải làm bước kiểm tra hạ tầng tiếp theo.

## 10. Kiểm chứng hạ tầng từ nguồn được phép và nguồn bị cấm

Trên máy ứng dụng Linux, xem listener:

```bash
ss -lnt
```

Với bài lab, cần thấy 8080, 9090, 8088, 9099 gắn với `127.0.0.1`. Không mong đợi một bảng stdout cố định vì cột, thứ tự và các dịch vụ khác phụ thuộc máy.

Với triển khai thật, chọn ít nhất ba điểm quan sát: chính máy ứng dụng, một máy vận hành được cấp quyền, một máy ngoài phạm vi được phép. Dùng địa chỉ/tên miền của hệ thống mình quản lý:

```bash
curl --noproxy '*' --connect-timeout 3 --max-time 5 \
  --cacert ops-ca.pem \
  -i https://ops.example.com:9443/actuator/health
```

`ops-ca.pem` là CA tin cậy đã cấp chứng thư cho máy chủ quản trị; nếu dùng CA đã nằm trong kho tin cậy hệ điều hành, không cần tham số này. Không dùng `-k` để biến lỗi chứng thư thành một lần kiểm tra đạt.

| Kiểm tra | Kết quả cần chứng minh |
| --- | --- |
| Máy vận hành → đường quản trị hợp lệ | Kết nối/TLS thành công; sau đó endpoint trả theo sức khỏe và quyền ứng dụng |
| Máy ngoài allowlist → listener quản trị | Bị chặn ở mạng hoặc proxy, không lấy được dữ liệu quản trị |
| Internet → tên miền nghiệp vụ với đường Actuator | Không được chuyển sang backend quản trị |
| Máy từ xa → địa chỉ backend:9090 trực tiếp | Không bỏ qua proxy được |
| Nguồn bị cấm thêm forwarded header giả | Không trở thành nguồn hợp lệ |
| Đường IPv6 nếu có DNS/listener IPv6 | Tuân cùng chủ đích giới hạn |
| Đường health probe/bộ thu thập thật | Vẫn hoạt động theo chính sách đã duyệt |

Mã `200` ở health không được bảo đảm cho hệ thống thật: trạng thái DOWN hoặc OUT_OF_SERVICE thường có thể trả `503`. Nếu có xác thực, một lần thử thiếu thông tin đăng nhập cũng chưa là phép thử đầy đủ của nguồn hợp lệ.

### Phân biệt kết quả thay vì gộp mọi lỗi thành “đã an toàn”

| Quan sát | Có thể nói được gì? |
| --- | --- |
| HTTP 401 | Đã nhận được HTTP từ một lớp yêu cầu xác thực |
| HTTP 403 | Một lớp HTTP từ chối; cần nhật ký để xác định lớp nào |
| HTTP 404 | URL không được phục vụ ở đường đang thử; chưa chứng minh mọi đường khác bị chặn |
| HTTP 502/504 từ proxy | Proxy có vấn đề với upstream; chưa phải bằng chứng chính sách chặn đúng |
| Connection refused | Thường không có listener phù hợp hoặc có lớp chủ động reject |
| Timeout | Có thể do drop, mất tuyến, DNS hay sự cố; cần đối chiếu thêm |
| Lỗi chứng thư TLS | Chưa qua xác minh danh tính máy chủ; không quy thành thành công |

Khi `curl -w` in `000`, đó không phải mã HTTP của máy chủ. Hãy đọc lỗi và mã thoát của curl. Không có một stdout lỗi mạng cố định dùng cho tất cả hệ điều hành.

Trong NGINX lab, xem `access.log` để kiểm tra địa chỉ nguồn và status. Khi có nhiều proxy, bổ sung nhật ký từng chặng, cấu hình đang có hiệu lực và số đếm firewall để đối chiếu. Chỉ ghi trường cần thiết; tránh ghi credential hoặc toàn bộ dữ liệu endpoint vào log.

## 11. Các lỗi triển khai hay gặp và cách sửa

| Lỗi | Vì sao gây hiểu nhầm hoặc mở rộng truy cập? | Cách xử lý |
| --- | --- | --- |
| Chỉ đổi cổng quản trị sang 9090 | Một cổng mở công khai vẫn có thể được dò ra | Chọn bind address và lọc nguồn mạng rõ ràng |
| Chỉ bảo vệ tên miền quản trị | Backend còn có đường IP:cổng trực tiếp | Chặn đường bỏ qua proxy và thử từ máy khác |
| Thấy IP riêng nên cho rằng đã giới hạn đủ | Nhiều máy/pod khác có thể cùng có tuyến đến đó | Liệt kê nguồn cần dùng và chặn nguồn khác |
| Đặt proxy ở container khác nhưng gọi localhost | Localhost thuộc môi trường của chính proxy | Dùng mạng dịch vụ đúng và listener phù hợp |
| Cho phép cả subnet NAT/VPN mà không kiểm tra danh tính | Nhiều người dùng chung IP đầu ra | Giữ xác thực/phân quyền riêng |
| Tin X-Forwarded-For do máy gọi tự gửi | Dữ liệu header không chứng minh nguồn thật | Xác định proxy tin cậy, làm sạch header, kiểm thử giả mạo |
| Thêm allow hẹp nhưng quên allow rộng cũ | Kết quả kết hợp có thể vẫn cho mọi nguồn | Rà soát toàn bộ quy tắc đang hiệu lực |
| Chỉ thử health từ chính máy chủ | Không kiểm tra được tuyến từ nguồn bị cấm | Thử đủ các vị trí trong ma trận |
| Chặn được probe rồi mở 9090 cho mọi nguồn | Chữa triệu chứng bằng cách phá ranh giới | Xác định nguồn probe và cấp đúng quyền cần thiết |
| Dùng CORS để “khóa” Actuator | Giới hạn trình duyệt không ngăn curl/kết nối mạng | Dùng chính sách mạng và quyền ứng dụng |
| Chỉ kiểm tra IPv4 | Có thể còn listener hoặc tên miền IPv6 | Thử cả hai họ địa chỉ nếu hệ thống hỗ trợ |
| Đổi base path nhưng giữ ACL cũ | Đường mới có thể đi qua location khác | Cập nhật đường và chạy lại ma trận kiểm tra |

Giới hạn mạng không tắt các kênh quản trị khác như JMX đã được bật riêng. Phải kiểm kê riêng những kênh đang sử dụng; bài này chỉ xác minh đường HTTP Actuator.

## 12. Bài tập áp dụng

### Bài tập 1: chọn ranh giới cho một máy chủ

Một máy chạy JVM và NGINX; chỉ máy giám sát trong subnet `10.20.30.0/24` cần đọc health. Vẽ đường từ máy giám sát đến JVM và ghi địa chỉ/cổng ở mỗi chặng.

**Tiêu chí tự kiểm tra:** JVM có thể chỉ bind loopback; NGINX có listener quản trị trên địa chỉ riêng; cả firewall và ACL phù hợp nguồn giám sát; không còn đường truy cập từ xa trực tiếp vào backend.

### Bài tập 2: tìm đường bỏ qua proxy

Tên miền `ops.example.com` có ACL đúng, nhưng JVM nghe `0.0.0.0:9090` và cloud firewall vẫn cho nguồn `0.0.0.0/0`.

**Phân tích:** máy ngoài có thể thử IP backend trực tiếp, không cần qua tên miền/proxy đó. Cần thu hẹp listener hoặc mạng vào backend theo mô hình đã chọn, rồi thử lại cả đường hợp lệ lẫn đường trực tiếp. Thay tên miền không giải quyết nguyên nhân.

### Bài tập 3: kiểm tra khi đổi môi trường

Chuyển JVM sang container riêng trong khi NGINX vẫn chạy trên host. Cấu hình nào của bài cùng máy không thể giữ nguyên một cách máy móc?

**Phân tích:** phải xét lại phạm vi loopback, địa chỉ listener trong container, ánh xạ cổng host và đường firewall Docker. Cần kiểm tra cả kết nối từ NGINX lẫn từ một máy khác; một lần curl thành công trên host chưa đủ.

### Bài tập 4: lập bằng chứng trước khi bàn giao

Tạo bảng gồm nguồn gọi, URL đích, đường qua từng lớp, kết quả mong đợi và kết quả thực tế. Bao gồm nguồn bị cấm, header giả, đường trực tiếp và IPv6 nếu có.

**Tiêu chí tự kiểm tra:** chỉ đánh dấu đạt khi có bằng chứng cho cả đường cần hoạt động và đường phải bị chặn. Ghi rõ lớp chặn và giới hạn của phép thử, thay vì coi mọi lỗi kết nối là một kết quả đạt.
