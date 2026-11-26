# Cấu hình kết nối mạng, địa chỉ lắng nghe và địa chỉ công bố

## 1. Hai địa chỉ khác nhau trong cùng một kết nối Neo4j

Một ứng dụng Java có thể kết nối Neo4j thành công khi chạy trên máy chủ database, nhưng lại bị **connection refused**, **timeout**, hoặc lỗi **routing table** khi chạy từ một máy khác. Một nguyên nhân thường gặp là nhầm lẫn giữa:

- **Địa chỉ lắng nghe (listen address):** địa chỉ IP/interface và cổng mà **tiến trình Neo4j bind** để nhận kết nối.
- **Địa chỉ công bố (advertised address):** địa chỉ host và cổng mà **Neo4j thông báo để client hoặc thành phần khác biết nơi cần kết nối**.

Hai địa chỉ có thể giống nhau trong môi trường đơn giản, nhưng **không bắt buộc giống nhau** khi có Docker, NAT, load balancer, reverse proxy, nhiều giao diện mạng hay cluster.

Ví dụ một server chạy trong mạng riêng:

~~~text
Ứng dụng Java                                Neo4j server
neo4j+s://graph.example.com:7687               10.10.0.15
       |                                              |
       | DNS: graph.example.com -> 203.0.113.20       |
       v                                              |
Firewall/NAT: 203.0.113.20:7687 ------------------> 10.10.0.15:7687
                                                           |
                                              Listen: 0.0.0.0:7687
                                              Advertise: graph.example.com:7687
~~~

Trong hình:

- `0.0.0.0:7687` là cách server **nhận** kết nối trên những giao diện phù hợp.
- `graph.example.com:7687` là địa chỉ **ứng dụng dùng để truy cập** qua DNS và mạng.
- `0.0.0.0` **không** phải một tên host hợp lệ để đưa cho mọi client ở xa.
- Nếu NAT dịch cổng, **cổng được công bố** có thể khác cổng bên trong server.

Bài học thuộc chương **Cấu hình tài nguyên** của Neo4j, tập trung vào cấu hình kết nối mạng cho property graph và các ứng dụng Cypher, Java Driver, Spring Data Neo4j. Trọng tâm là cấu hình **đúng đường đi kết nối**, kiểm tra tính truy cập được và tránh vô tình công khai database ra Internet.

## 2. Bộ ba cần đồng thời đúng: listen, advertise và đường đi mạng

Kết nối thành công đòi hỏi ba nhóm điều kiện:

1. **Neo4j thực sự lắng nghe** tại IP/interface và port mà gói tin đi đến.
2. **Địa chỉ client sử dụng hoặc được Neo4j công bố** phân giải DNS và trỏ đến nơi client truy cập được.
3. **Mạng trung gian cho phép traffic** qua firewall, security group, container port mapping, Kubernetes Service, NAT, proxy và chính sách TLS.

Có thể biểu diễn:

~~~text
Client URI
  |
  v
DNS / IP công bố
  |
  v
Firewall / Load Balancer / NAT / Proxy
  |
  v
IP:port được chuyển tới server
  |
  v
Neo4j listen socket
  |
  v
Xác thực / TLS / Bolt hoặc HTTP(S)
~~~

**Đổi `advertised_address` không mở port.** Nó cũng không tự cấu hình DNS, tạo route mạng hoặc đặt quy tắc firewall. Ngược lại, mở port 7687 không sửa một routing table đang trả về địa chỉ mà client không thể truy cập.

### 2.1. Listen address là gì?

Địa chỉ lắng nghe có dạng **host/IP:port** (cú pháp chi tiết tùy setting). Host/IP có thể là:

| Listen host | Ý nghĩa điển hình | Khi nào dùng? |
|---|---|---|
| `127.0.0.1` | Chỉ nhận kết nối qua loopback IPv4 của chính môi trường chạy | Phát triển local, quản trị qua SSH tunnel |
| `0.0.0.0` | Bind trên tất cả giao diện IPv4 phù hợp trong network namespace | Container/server cần nhận traffic từ bên ngoài namespace |
| Một IP riêng, ví dụ `10.10.0.15` | Bind vào giao diện có IP đó trên host | Server nhiều NIC, cần giới hạn interface |
| Một địa chỉ IPv6 cụ thể hoặc wildcard IPv6 | Bind qua IPv6 theo cấu hình hệ điều hành | Hệ thống dùng IPv6; cần xác minh cú pháp và firewall |

**Lưu ý:** `127.0.0.1` bên trong container là **loopback của container**, không phải loopback của máy host. `0.0.0.0` bên trong container bind mọi giao diện của **container**, nhưng không đồng nghĩa port được công khai tới mạng ngoài nếu chưa có cơ chế publish/expose tương ứng.

Không bind vào một public IP **không thuộc interface của máy đang chạy**; trong môi trường NAT/container, cách cấu hình này có thể khiến Neo4j không khởi động được vì không thể bind socket.

### 2.2. Advertised address là gì?

Địa chỉ công bố nên là **địa chỉ mà bên cần kết nối có thể sử dụng thực tế**. Nó thường là hostname hoặc IP cộng port, ví dụ:

~~~text
graph.internal.example:7687
graph.example.com:17687
neo4j-0.graph.svc.cluster.local:7687
~~~

Cần chọn địa chỉ dựa trên **phạm vi client**: ứng dụng trong cùng VPC, Java service trong Kubernetes, laptop qua VPN hay các client công khai có thể thấy các đường mạng khác nhau.

**Không dùng `0.0.0.0` làm địa chỉ công bố cho ứng dụng.** Wildcard listen mô tả giao diện bind; nó không nói một client ở máy khác phải gửi gói tin tới đâu.

### 2.3. Không nhầm với URL/URI

Setting trong `neo4j.conf` chứa **địa chỉ host:port**, không phải một URI có scheme:

~~~properties
# Đúng dạng địa chỉ:
server.bolt.advertised_address=graph.example.com:7687
~~~

~~~text
# URI dùng bên Java Driver:
neo4j+s://graph.example.com:7687
~~~

Không đặt `neo4j+s://` vào giá trị `server.bolt.advertised_address`. Scheme thuộc về **cấu hình client**, quyết định routing/TLS theo khả năng của driver.

## 3. Các connector thường gặp và port mặc định

Neo4j phục vụ nhiều giao thức. Trong một triển khai phổ biến:

| Giao thức/connector | Cổng thường dùng | Ai sử dụng? | Ghi chú |
|---|---:|---|---|
| **Bolt** | **7687** | Java Driver, Spring Data Neo4j, Cypher Shell, Neo4j Browser khi thực thi truy vấn | Giao thức phục vụ thao tác database |
| **HTTP** | **7474** | Giao diện quản trị/Browser và API HTTP được hỗ trợ | Không thay thế được Bolt |
| **HTTPS** | **7473** | HTTP/Browser qua TLS khi được bật và cấu hình chứng chỉ | Có thể không bật sẵn |
| **Giao tiếp cluster nội bộ** | Phụ thuộc phiên bản/kiến trúc | Các server Neo4j trao đổi với nhau | Không đồng nhất với port Bolt cho client |

Các cổng trên là **giá trị thường gặp**, không phải cổng bất biến. Có thể thay đổi chúng qua cấu hình, mapping container hoặc load balancer.

### 3.1. Mở Neo4j Browser không chứng minh Bolt đã hoạt động

Trường hợp thường gặp:

~~~text
Trình duyệt mở http://graph.example.com:7474    -> thành công
Chạy Cypher trong Browser                       -> lỗi kết nối Bolt
~~~

Browser có thể tải giao diện qua HTTP, nhưng việc thực thi truy vấn qua Bolt vẫn đòi hỏi **cổng Bolt và hostname Bolt** mà trình duyệt nhìn thấy phải truy cập được. Cấu hình firewall chỉ mở 7474 không đủ cho Java Driver trên 7687.

### 3.2. HTTP/HTTPS không nên được công khai mặc định

Nếu ứng dụng chỉ cần Bolt, có thể hạn chế hoặc tắt connector HTTP tùy nhu cầu quản trị. Nếu cần Browser, ưu tiên truy cập nội bộ/VPN hoặc HTTPS có xác thực phù hợp.

Đừng mở mọi connector ra Internet chỉ để giải quyết lỗi “không kết nối được”. Trước tiên xác định **client nào cần giao thức nào** và mở phạm vi tối thiểu.

## 4. Các setting mạng thường dùng trong Neo4j 5.x

Neo4j 5.x và nhiều bản mới sử dụng nhóm setting dưới đây. **Tên setting có thể khác giữa các đời Neo4j**, đặc biệt khi đối chiếu với hướng dẫn Neo4j 4.x dùng tiền tố `dbms.connector.*`. Trước khi dùng trên hệ thống thực, hãy kiểm tra tài liệu cấu hình đúng phiên bản đang chạy.

| Setting | Vai trò |
|---|---|
| `server.default_listen_address` | Host/IP mặc định dùng cho nhiều connector nếu không override |
| `server.default_advertised_address` | Hostname/IP công bố mặc định nếu connector không chỉ định riêng |
| `server.bolt.enabled` | Bật/tắt Bolt |
| `server.bolt.listen_address` | Địa chỉ/cổng Bolt bind |
| `server.bolt.advertised_address` | Địa chỉ/cổng Bolt công bố |
| `server.http.enabled` | Bật/tắt HTTP |
| `server.http.listen_address` | Địa chỉ/cổng HTTP bind |
| `server.http.advertised_address` | Địa chỉ/cổng HTTP công bố |
| `server.https.enabled` | Bật/tắt HTTPS |
| `server.https.listen_address` | Địa chỉ/cổng HTTPS bind |
| `server.https.advertised_address` | Địa chỉ/cổng HTTPS công bố |

**Quy tắc thiết kế:** có thể dùng giá trị `default_*` để giảm lặp, nhưng khi NAT, proxy hoặc nhiều connector có các hostname/port khác nhau, nên **cấu hình advertised address riêng** cho connector liên quan. Không đặt một hostname mặc định rồi mặc nhiên cho rằng mọi giao thức đều được route qua đó.

### 4.1. Cấu hình Bolt minh họa

~~~properties
# neo4j.conf — ví dụ cho Neo4j 5.x
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.bolt.advertised_address=graph.example.com:7687
~~~

Ý nghĩa:

- Bolt nhận kết nối trên IPv4 interface của tiến trình tại port 7687.
- Khi cần công bố endpoint Bolt, hostname được sử dụng là `graph.example.com`.
- DNS cho `graph.example.com`, đường chuyển tiếp tới server và firewall phải được cấu hình **ngoài Neo4j**.

**Cảnh báo:** Ví dụ không phải cấu hình production hoàn chỉnh; nó chưa thể hiện TLS, xác thực, giới hạn truy cập và policy mạng.

### 4.2. Dùng default listen/advertised address

~~~properties
server.default_listen_address=0.0.0.0
server.default_advertised_address=graph.internal.example

server.bolt.listen_address=:7687
server.bolt.advertised_address=graph.internal.example:7687
~~~

Đoạn trên minh họa ý tưởng tách **host mặc định** với **port connector**; cú pháp giá trị bắt đầu bằng dấu hai chấm và cách kế thừa có thể cần đối chiếu tài liệu phiên bản. Nếu muốn cấu hình minh bạch, ưu tiên ghi đầy đủ `IP:port` trong `server.bolt.listen_address` và `host:port` trong `server.bolt.advertised_address`.

Các setting `server.default_*` không thay thế cho việc kiểm tra connector nào được bật và cấu hình TLS nào được sử dụng.

### 4.3. Thay đổi setting có cần khởi động lại?

Nhiều setting liên quan địa chỉ bind/socket đòi hỏi **khởi động lại server** để socket mới có hiệu lực. Đừng giả định sửa file `neo4j.conf` là mọi client sẽ nhìn thấy thay đổi ngay lập tức.

Quy trình an toàn:

1. Xác nhận phiên bản và cú pháp setting.
2. Thay đổi trong cấu hình hoặc nguồn cấu hình được quản lý.
3. Đánh giá tác động tới traffic và connection pool của ứng dụng.
4. Restart/rolling restart theo chính sách triển khai.
5. Đọc lại **giá trị cấu hình hiệu lực**, kiểm tra socket và thử kết nối từ client thật.

## 5. Môi trường phát triển: chỉ lắng nghe tại localhost

Khi Neo4j và Java service cùng chạy **trên một máy, không qua container mạng riêng**, có thể giới hạn Bolt và HTTP ở loopback:

~~~properties
server.bolt.enabled=true
server.bolt.listen_address=127.0.0.1:7687
server.bolt.advertised_address=localhost:7687

server.http.enabled=true
server.http.listen_address=127.0.0.1:7474
server.http.advertised_address=localhost:7474
~~~

Java Driver có thể kết nối trực tiếp:

~~~text
bolt://localhost:7687
~~~

Trình duyệt truy cập giao diện:

~~~text
http://localhost:7474
~~~

Khi thử từ **một máy khác**, `localhost` trỏ về **máy client đó**, không phải máy database. Cần đổi đường đi phù hợp (VPN, SSH tunnel, hoặc cấu hình server truy cập từ xa có bảo vệ), chứ không chỉ thay URI trong Java thành `localhost`.

### 5.1. Localhost trong Docker có nghĩa khác

Nếu Neo4j chạy trong Docker nhưng Java chạy **trên host**, client có thể dùng `localhost:7687` **nếu port đã được publish ra host**.

Nếu Java chạy trong **container khác**, `localhost:7687` trỏ về container Java; thường cần dùng tên Service/container trong cùng Docker network, ví dụ `neo4j:7687`, với cấu hình địa chỉ công bố phù hợp phạm vi mạng đó.

## 6. Máy chủ nội bộ/VPC: listen trên interface thích hợp, advertise theo DNS

Giả sử server có IP private `10.10.0.15` và Java service ở cùng VPC có thể phân giải `graph.internal.example` tới IP này.

~~~properties
server.bolt.enabled=true
server.bolt.listen_address=10.10.0.15:7687
server.bolt.advertised_address=graph.internal.example:7687

# Chỉ cần khi có giao diện HTTP phục vụ quản trị.
server.http.enabled=false
server.https.enabled=false
~~~

Vì database chỉ phục vụ qua Bolt, HTTP/HTTPS không được bật trong ví dụ này. Nếu cần Browser/HTTPS, phải thiết kế thêm đường truy cập và cấu hình chứng chỉ.

Có thể thay listen IP thành `0.0.0.0:7687` nếu máy có nhiều interface và môi trường yêu cầu bind rộng hơn, **nhưng firewall/security group vẫn phải giới hạn client**.

### 6.1. Không dùng public hostname nếu DNS không phù hợp đường đi

Giả sử máy Java trong VPC chỉ được phép kết nối IP nội bộ, nhưng Neo4j công bố `db-public.example.com` trỏ về Internet public IP. Client có thể:

- Không kết nối được do VPC không hỗ trợ hairpin NAT.
- Đi đường mạng dài hơn hoặc không được phép.
- Chịu policy firewall/TLS khác mong muốn.

Trong hệ thống nội bộ, nên dùng hostname ổn định có thể resolve và route nội bộ, ví dụ `graph.internal.example`; nếu vừa có client nội bộ vừa có client bên ngoài, hãy thiết kế DNS/proxy để cùng endpoint được truy cập đúng theo từng phạm vi.

## 7. Docker: port publish và advertised port không nhất thiết trùng

Docker tạo một **network namespace riêng** cho container. Neo4j có thể listen tại `0.0.0.0:7687` trong container, còn host cung cấp port khác cho client.

Ví dụ:

~~~yaml
services:
  neo4j:
    image: neo4j:5
    ports:
      - "127.0.0.1:17474:7474"
      - "17687:7687"
    environment:
      NEO4J_server_bolt_listen__address: "0.0.0.0:7687"
      NEO4J_server_bolt_advertised__address: "graph.example.com:17687"
~~~

Đoạn Compose trên **chỉ minh họa mapping mạng**, chưa phải triển khai bảo mật hoàn chỉnh: phải bổ sung xác thực, volume lưu dữ liệu, TLS và policy firewall theo môi trường. Không đưa mật khẩu production dạng plain text vào tài liệu Compose hoặc repository.

### 7.1. Phân tích đường đi cổng

~~~text
Java ở máy ngoài
neo4j+s://graph.example.com:17687
           |
           | DNS + firewall
           v
Docker host, port 17687
           |
           | Docker port mapping 17687:7687
           v
Neo4j container, port 7687
           |
           | listen = 0.0.0.0:7687
           | advertised = graph.example.com:17687
~~~

Cặp `17687:7687` nghĩa là **host port 17687** chuyển tiếp tới **container port 7687**. Do đó, nếu routing/client bên ngoài cần dùng địa chỉ công bố thì nó phải thấy **17687**, không phải 7687, trừ khi có một route khác.

Ví dụ dùng URI `neo4j+s://` giả định đầu cuối Bolt đã được cấu hình TLS hợp lệ. Nếu chưa có TLS, phải cấu hình TLS trước thay vì đổi sang kết nối không mã hóa trên mạng không tin cậy.

### 7.2. Quy tắc biến môi trường Neo4j trong container

Với ảnh Neo4j hỗ trợ quy tắc ánh xạ tên biến cấu hình:

- Dấu **chấm** trong tên setting thường chuyển thành một dấu gạch dưới.
- Dấu **gạch dưới có sẵn** trong tên setting thường chuyển thành **hai dấu gạch dưới**.

Vì vậy:

~~~text
server.bolt.listen_address
  -> NEO4J_server_bolt_listen__address

server.bolt.advertised_address
  -> NEO4J_server_bolt_advertised__address
~~~

Cần kiểm tra quy ước của đúng image/version đang chạy; một biến bị viết sai có thể bị bỏ qua hoặc không đặt được setting như mong muốn.

### 7.3. Trường hợp Java service cùng Docker network

Nếu client Java nằm trong cùng Compose network, endpoint nội bộ có thể là:

~~~text
neo4j:7687
~~~

Nhưng advertised hostname `graph.example.com:17687` ở cấu hình trước có thể khiến driver routing nhận địa chỉ **không phù hợp** với mạng container nội bộ.

Các lựa chọn có thể gồm:

- Sử dụng một hostname chung có DNS/route hoạt động từ **cả hai phạm vi**.
- Thiết kế riêng deployment cho traffic nội bộ và bên ngoài.
- Dùng cấu hình/đường truy cập được hỗ trợ phù hợp kiến trúc, thay vì đổi URI thành một tên nội bộ nhưng giữ advertised address sai.

Trong một deployment chỉ có client Java cùng Docker network, có thể công bố `neo4j:7687` và không publish Bolt ra bên ngoài nếu không cần.

## 8. Kubernetes: Service, Pod DNS và network policy

Kubernetes cung cấp tên Service và các lớp cân bằng tải, nhưng **không làm biến mất sự khác biệt giữa địa chỉ listen và địa chỉ công bố**.

Một Pod Neo4j thường bind cổng Bolt trên interface phù hợp bên trong Pod. Java application trong cùng cluster có thể kết nối qua một Kubernetes Service, ví dụ:

~~~text
neo4j.default.svc.cluster.local:7687
~~~

Với triển khai **một instance** hoặc một endpoint được sản phẩm hỗ trợ, địa chỉ này có thể là điểm truy cập nội bộ ổn định. Nếu client chạy ngoài cluster, hostname `*.svc.cluster.local` thường **không resolve/không route được** từ Internet.

### 8.1. Mô hình kết nối bên trong cluster

~~~text
Java Pod
   |
   | neo4j.default.svc.cluster.local:7687
   v
Kubernetes Service
   |
   v
Neo4j Pod:7687
   |
   | server.bolt.listen_address=0.0.0.0:7687
~~~

Ở phía bên trong, cần xác định địa chỉ mà Neo4j/cluster **công bố** có thể được Java Pod truy cập. Đồng thời kiểm tra Kubernetes **NetworkPolicy**, Service selector, EndpointSlice và readiness; setting Neo4j không sửa được Service trỏ sai Pod.

### 8.2. Client bên ngoài cluster

Một client ngoài cluster thường cần Ingress/LoadBalancer/TCP proxy hoặc cơ chế xuất bản được hỗ trợ. Đối với Bolt, không thể giả định mọi HTTP Ingress controller đều hỗ trợ truyền giao thức TCP trên port 7687.

Nếu client dùng routing (`neo4j://` hoặc `neo4j+s://`), driver có thể nhận **địa chỉ của các server khác** từ routing table. Vì vậy, chỉ làm cho **điểm bootstrap qua LoadBalancer** truy cập được là **chưa đủ** nếu các endpoint được trả về vẫn là DNS Pod nội bộ.

Trong Neo4j cluster, cấu hình quảng bá endpoint cho từng thành viên, DNS và loại exposure phải tương thích với cách Neo4j Driver khám phá các server; triển khai Helm/Operator được hỗ trợ nên được ưu tiên và kiểm tra đúng phiên bản.

### 8.3. Không nhầm giao tiếp cluster nội bộ với Bolt cho ứng dụng

Cluster Neo4j còn có những kết nối **server–server** phục vụ điều phối, đồng bộ hoặc phân tán. Các địa chỉ/cổng nội bộ này được cấu hình riêng theo phiên bản/edition/topology; không được tự quy về `server.bolt.listen_address` hoặc mở toàn bộ cổng cluster ra Internet.

Chỉ expose những connector mà đối tượng bên ngoài thực sự cần; giữ traffic nội bộ cluster trong mạng được kiểm soát.

## 9. Direct connection và routing của Neo4j Java Driver

Java Driver phân biệt các **scheme** kết nối có chế độ định tuyến và mã hóa khác nhau:

| Scheme URI | Ý nghĩa chính |
|---|---|
| `bolt://host:port` | Kết nối **trực tiếp** tới Bolt endpoint |
| `neo4j://host:port` | Dùng cơ chế **routing/discovery** của Neo4j Driver |
| `bolt+s://host:port` | Direct Bolt với TLS và xác minh certificate theo trust chain |
| `neo4j+s://host:port` | Routing qua Bolt với TLS và xác minh certificate theo trust chain |
| `bolt+ssc://host:port` | Direct Bolt qua TLS theo chế độ chấp nhận certificate self-signed |
| `neo4j+ssc://host:port` | Routing qua TLS theo chế độ chấp nhận certificate self-signed |

Các scheme `+ssc` thích hợp cho mục đích thử nghiệm có kiểm soát; trong production nên ưu tiên `+s` với certificate và hostname được xác minh bằng trust chain được quản lý. Không dùng `+ssc` như một giải pháp lâu dài cho lỗi tên certificate.

**Quan trọng:** `neo4j://` khác `bolt://` ở cách driver **lấy và sử dụng routing information**, không chỉ khác chữ trong URI.

### 9.1. Direct Bolt

~~~text
Client Java -- bolt://graph.example.com:7687 --> Server
~~~

Ở chế độ direct, driver hướng kết nối tới endpoint đã chỉ định theo hợp đồng driver. Mô hình này hữu ích khi chủ đích chỉ dùng **một endpoint trực tiếp**.

Không coi `bolt://` là cách sửa lâu dài một cluster có routing address sai nếu ứng dụng thực sự cần phân phối đọc/ghi hoặc khả năng failover qua routing.

### 9.2. Routing driver

~~~text
Client Java -- neo4j://gateway.example.com:7687 --> Bootstrap endpoint
                               |
                               | yêu cầu routing table
                               v
                    Địa chỉ server A / B / C
                               |
                     Java Driver mở kết nối tới
                     các endpoint được công bố
~~~

Khi routing table chứa `10.0.0.5:7687` nhưng Java app chạy ngoài VPC, việc **kết nối bootstrap thành công** vẫn có thể đi kèm lỗi kết nối ở bước tiếp theo.

**Điểm cần kiểm tra:** mọi địa chỉ Bolt mà driver **thực sự có thể được điều hướng tới** phải resolve, route và đáp ứng TLS/xác thực từ **môi trường chạy của driver**, không chỉ từ máy chủ Neo4j.

### 9.3. Không cho mọi cluster member công bố cùng một địa chỉ tùy tiện

Đặt tất cả thành viên cluster công bố cùng một hostname load balancer **không phải** một quy tắc an toàn chung. Routing driver cần biết endpoint nào dùng cho vai trò nào và thường có thông tin về từng server. Một cấu hình đưa mọi server về một địa chỉ chung có thể che giấu vai trò, phá routing hoặc tạo các vòng chuyển tiếp sai.

Chọn kiến trúc exposure/routing đã được hỗ trợ cho phiên bản Neo4j và hạ tầng; kiểm thử từ đúng mạng client. Có những cấu hình dùng routing/proxy chuyên biệt, nhưng không tự phát minh mapping cho cluster nhiều node.

## 10. Reverse proxy, NAT và load balancer

Một reverse proxy có thể nhận traffic tại `db.example.com:443` và chuyển tới Bolt tại `10.10.0.15:7687`. Khi đó:

~~~text
Client Bolt/TLS           TCP proxy/LB                  Neo4j
db.example.com:443 -----> proxy:443 -----------------> 10.10.0.15:7687
                                                       listen: 0.0.0.0:7687
                                                       advertise: db.example.com:443
~~~

Địa chỉ công bố phản ánh endpoint mà client thấy, không bắt buộc là port nội bộ. Nhưng cần kiểm tra:

- Proxy có **hỗ trợ TCP forwarding cho Bolt** hay chỉ hỗ trợ HTTP path routing?
- TLS được **passthrough**, terminate tại proxy hay terminate và mã hóa lại?
- Certificate mà Java Driver xác minh có khớp hostname `db.example.com` không?
- Cơ chế routing có trả về những địa chỉ khác mà proxy không cho phép truy cập không?
- Có giới hạn idle timeout, connection lifetime và health check phù hợp Bolt không?

### 10.1. Không route Bolt như HTTP

Bolt là giao thức kết nối database; không thể đơn giản đặt URI `neo4j://` sau một đường HTTP như:

~~~text
https://example.com/neo4j/bolt
~~~

rồi mong Java Driver dùng nó như một địa chỉ Bolt mặc định. Proxy cần khả năng chuyển tiếp giao thức đúng, trên host/port hoặc gateway được hỗ trợ.

### 10.2. TLS termination quyết định cách client nhìn kết nối

Nếu proxy nhận kết nối TLS, certificate của proxy phải tương thích với hostname client dùng. Nếu TLS được passthrough, Neo4j phải được cấu hình để chấp nhận kết nối TLS và cung cấp certificate phù hợp.

Không bật/tắt mã hóa ở một lớp mà không kiểm tra hai lớp còn lại. Một kết nối TCP mở thành công vẫn có thể thất bại ở bước **TLS handshake** hoặc **Bolt handshake**.

### 10.3. Chỉ một hostname cho client nội bộ và ngoài

Trong hệ thống hỗn hợp, cùng hostname `graph.example.com` có thể được triển khai bằng **split-horizon DNS**: client nội bộ resolve tới IP private, client bên ngoài resolve tới public proxy. Điều kiện là cả hai đường đi thực sự đến endpoint hỗ trợ cùng host/port và chứng chỉ hợp lệ.

Đây là **một chiến lược hạ tầng**, không phải chức năng do `server.bolt.advertised_address` tự cung cấp. Không dùng khi network policy hoặc proxy không hỗ trợ.

## 11. HTTPS và TLS: có listener vẫn chưa đủ

Hai khía cạnh cần tách:

- **Lắng nghe/công bố:** ứng dụng liên hệ host và port nào?
- **Bảo mật kênh:** dữ liệu trên kết nối có được mã hóa và chứng thực server đúng cách không?

Ví dụ bật HTTPS thường cần hơn một dòng `server.https.enabled=true`. Phải cấu hình **SSL policy**, certificate và private key theo phiên bản Neo4j và thiết kế TLS. Tương tự, Bolt muốn yêu cầu TLS phải cấu hình policy và chế độ TLS phù hợp, hoặc sử dụng proxy TLS được hỗ trợ.

### 11.1. Ví dụ định hướng bảo mật

~~~properties
# Minh họa listener, không phải cấu hình TLS hoàn chỉnh.
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.bolt.advertised_address=graph.example.com:7687

server.http.enabled=false
server.https.enabled=true
server.https.listen_address=0.0.0.0:7473
server.https.advertised_address=graph-admin.example.com:7473
~~~

**Để đoạn trên hoạt động như hệ thống HTTPS bảo mật**, cần bổ sung các setting certificate/SSL policy theo phiên bản. Không sao chép nó rồi kết luận HTTPS đã chạy nếu chưa kiểm tra log khởi động và handshake.

### 11.2. Certificate phải khớp tên client sử dụng

Nếu Java Driver kết nối `neo4j+s://graph.example.com:7687`, certificate đầu cuối TLS phải được cấp và tin cậy cho **graph.example.com** theo quy tắc xác thực hostname của driver.

Một certificate chỉ dành cho `localhost` hoặc `db.internal` không tự hợp lệ cho `graph.example.com`. Đổi client URI sang IP cũng có thể tạo lỗi hostname mismatch nếu certificate không có SAN cho IP đó.

### 11.3. 0.0.0.0 không phải một security control

Listen trên `0.0.0.0` có thể hợp lý trong container/network private, nhưng:

- Không xác định được **ai** được phép truy cập.
- Không thay thế authentication/authorization.
- Không thay thế TLS.
- Không tự giới hạn IP nguồn.
- Không bảo đảm firewall chặn traffic công khai.

Bảo vệ server bằng cấu hình xác thực, firewall/security group, TLS, network policy và nguyên tắc **least privilege**. Tránh dùng truy cập admin database từ Internet nếu không có thiết kế an ninh được phê duyệt.

## 12. Kiểm tra cấu hình hiệu lực trong Neo4j

Một lỗi vận hành phổ biến là **chỉnh đúng file nhưng sai instance**: ví dụ sửa `neo4j.conf` trên host trong khi Neo4j chạy từ container với volume/config khác, hoặc đặt biến môi trường ghi đè setting trong file.

Trên Neo4j version và quyền cho phép, có thể xem setting hiệu lực:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'server.default_listen_address',
  'server.default_advertised_address',
  'server.bolt.enabled',
  'server.bolt.listen_address',
  'server.bolt.advertised_address',
  'server.http.enabled',
  'server.http.listen_address',
  'server.http.advertised_address',
  'server.https.enabled',
  'server.https.listen_address',
  'server.https.advertised_address'
]
RETURN name, value
ORDER BY name;
~~~

**Lưu ý:** khả năng sử dụng `SHOW SETTINGS`, trường kết quả và quyền truy cập phụ thuộc phiên bản/edition và quyền quản trị. Nếu không đủ quyền, yêu cầu người vận hành xem lại cấu hình hiệu lực hoặc công cụ giám sát được cấp phép.

### 12.1. So sánh cấu hình kỳ vọng và cấu hình đang chạy

Nên lưu một bảng đối chiếu:

| Nội dung | Kỳ vọng | Quan sát |
|---|---|---|
| Bolt enabled | true | từ SHOW SETTINGS/log |
| Bolt listen | 0.0.0.0:7687 | socket thực tế trong container/host |
| Bolt advertise | graph.example.com:17687 | giá trị Neo4j trả về |
| DNS cho hostname | IP gateway phù hợp | kiểm tra từ máy Java |
| Port mapping | 17687 → 7687 | cấu hình NAT/Compose/Service |
| TLS | certificate hợp lệ với hostname | thử handshake từ client |
| Firewall | chỉ nguồn được phép | kiểm tra rule và đường mạng |

Việc xuất hiện giá trị `graph.example.com:17687` trong SHOW SETTINGS **không tự chứng minh client bên ngoài truy cập được**. Bước kiểm tra mạng là bắt buộc.

### 12.2. Xác định setting có bị thay bằng tên đời cũ không

Nếu áp dụng hướng dẫn Neo4j 4.x vào Neo4j 5.x, tên như `dbms.connector.bolt.listen_address` có thể không còn phù hợp với phiên bản mới. Không nên thêm cả setting cũ và mới “cho chắc” vì có thể gây lỗi cấu hình, cảnh báo hoặc tác động không dự đoán được.

Phải chọn **một bộ setting đúng phiên bản** và kiểm tra log startup cùng giá trị hiệu lực. Khi nâng cấp, xem hướng dẫn migration của Neo4j trước khi đổi tên hàng loạt.

## 13. Kiểm tra từ đúng vị trí của client

Một phép thử chạy trên server Neo4j không đại diện cho Java service chạy trong container, subnet hoặc mạng Internet khác. Hãy kiểm tra từ **nơi ứng dụng thực sự chạy**.

### 13.1. Kiểm tra DNS và port

Trên môi trường có các công cụ tương ứng:

~~~bash
# Trên máy client Linux/macOS, nếu có các lệnh này:
getent hosts graph.example.com
nc -vz graph.example.com 7687
~~~

`getent` không có sẵn trong mọi hệ điều hành; có thể thay bằng công cụ DNS phù hợp như `nslookup` hoặc `dig`. `nc` chỉ kiểm tra khả năng mở TCP tới cổng; nó **không** chứng minh xác thực/TLS/Bolt routing thành công.

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName graph.example.com
Test-NetConnection -ComputerName graph.example.com -Port 7687
~~~

Nếu DNS không trả đúng IP, sửa **DNS/hostname**. Nếu DNS đúng nhưng cổng không mở, kiểm tra **port mapping, firewall, listener và network policy** trước khi thay đổi username/password Neo4j.

### 13.2. Kiểm tra socket trên host hoặc trong container

Trên Linux có quyền phù hợp:

~~~bash
ss -lnt
~~~

Tìm listener tương ứng port 7687, 7474, 7473 và IP bind. Nếu Neo4j chạy trong container, cần kiểm tra socket **bên trong đúng network namespace/container** và port mapping ở host; nhìn mỗi danh sách socket của host chưa đủ để kết luận.

### 13.3. Kiểm tra giao thức thực sự

Một khi TCP mở được, dùng **Cypher Shell** hoặc Java Driver với URI phù hợp:

~~~bash
cypher-shell -a "neo4j+s://graph.example.com:7687" -u neo4j
~~~

Lệnh minh họa giả định server đã có Bolt TLS và trust chain hợp lệ; công cụ có thể yêu cầu nhập mật khẩu theo cách an toàn. **Không đặt mật khẩu production vào dòng lệnh hoặc log** nếu nó có thể bị lưu trong shell history/process list.

Nếu URI TCP hoạt động nhưng Cypher Shell thất bại, kiểm tra thông báo về:

- Chứng chỉ, TLS version và hostname.
- Authentication/authorization.
- Phiên bản client/server và Bolt handshake.
- Routing discovery nếu sử dụng scheme `neo4j://`.
- Database được chỉ định và quyền truy cập.

### 13.4. Tách lỗi direct và routing để khoanh vùng

Nếu được phép và kiến trúc hỗ trợ, thử hai URI trên cùng endpoint:

~~~text
bolt+s://graph.example.com:7687    (direct)
neo4j+s://graph.example.com:7687   (routing)
~~~

Nếu direct chạy nhưng routing lỗi, cần kiểm tra **routing table và advertised endpoint** thay vì chỉ kết luận cổng 7687 đã mở. Nhưng đừng dùng direct lâu dài để “né” một lỗi cấu hình cluster nếu ứng dụng thật cần routing.

## 14. Java Driver: URI, session, connection pool và kiểm tra kết nối

Trong ứng dụng Java, URI kết nối nên được quản lý bằng cấu hình môi trường/secret manager. `Driver` thường được tạo **một lần** và tái sử dụng, còn `Session` sống ngắn cho từng thao tác.

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jNetworkCheck {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        if (uri == null || user == null || password == null) {
            throw new IllegalArgumentException(
                "NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD are required"
            );
        }

        Config config = Config.builder()
            .withConnectionTimeout(5, TimeUnit.SECONDS)
            .withMaxConnectionPoolSize(30)
            .build();

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password), config)) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase("neo4j"))) {
                int value = session.executeRead(tx ->
                    tx.run("RETURN 1 AS ok")
                      .single()
                      .get("ok")
                      .asInt()
                );
                System.out.println("Neo4j query ok = " + value);
            }
        }
    }
}
~~~

Ví dụ sử dụng API thường gặp của **Neo4j Java Driver 5.x**; khi nâng phiên bản, cần kiểm tra chữ ký cấu hình và yêu cầu của môi trường. Chạy chương trình **ở đúng môi trường Java service** để kiểm tra kết nối end-to-end.

### 14.1. Phân tích `verifyConnectivity()`

`verifyConnectivity()` yêu cầu driver thử xác nhận có thể kết nối theo cấu hình đã tạo. Nó hữu ích khi khởi động ứng dụng hoặc trong công cụ kiểm tra.

Tuy vậy:

- Một lần kiểm tra thành công không bảo đảm mọi kết nối tương lai đều thành công.
- Với routing/cluster, failover hoặc endpoint khác có thể chỉ được dùng trong tình huống thực tế.
- `RETURN 1` chứng minh truy vấn cơ bản hoạt động; nó không benchmark query path dài, quyền ghi hoặc khả năng truy cập mọi database.

Không tạo `Driver` mới mỗi request để “chắc kết nối”: làm vậy phá lợi ích pool và gây overhead. Giới hạn pool, timeout và transaction retry nên được chọn dựa trên tải thực, không dùng chúng như cách sửa sai DNS hoặc advertised address.

### 14.2. Ảnh hưởng của connection pool và cổng mạng

Nếu nhiều request đồng thời thất bại vì **không lấy được connection từ pool**, nguyên nhân có thể là pool quá nhỏ, các transaction giữ connection quá lâu hoặc hệ thống quá tải — khác với lỗi `Connection refused` do listener/port.

Một số triệu chứng cần phân biệt:

| Triệu chứng | Gợi ý nguyên nhân |
|---|---|
| `Connection refused` ngay | Không có listener tương ứng, port mapping sai hoặc rule chủ động từ chối |
| Timeout khi mở TCP | Firewall drop, route sai, endpoint không phản hồi |
| Không resolve hostname | DNS hoặc tên được công bố không phù hợp |
| TLS certificate mismatch | Certificate/SAN và hostname không khớp |
| Routing table không dùng được | Advertised endpoints không reachable, topology hoặc discovery sai |
| Pool acquisition timeout | Pool bận/quá nhỏ hoặc transaction giữ kết nối lâu |
| Authentication failed | Thông tin đăng nhập hoặc policy bảo mật |
| Query chậm sau khi đã kết nối | Query plan, index, dữ liệu hoặc contention; không nhất thiết lỗi mạng |

Dựa vào lỗi cụ thể, log server/driver và đo thời gian từng giai đoạn thay vì đổi hàng loạt tham số pool, timeout và listener cùng lúc.

## 15. Spring Data Neo4j: cấu hình địa chỉ ở tầng ứng dụng

Với ứng dụng Spring Boot sử dụng Spring Data Neo4j, một cấu hình phổ biến có thể đi qua property ứng dụng:

~~~properties
# application.properties — ví dụ định hướng
spring.neo4j.uri=neo4j+s://graph.example.com:7687
spring.neo4j.authentication.username=app_user
spring.neo4j.authentication.password=... 
~~~

**Không commit mật khẩu thật vào repository.** Dùng biến môi trường, secret manager hoặc cơ chế quản lý bí mật được phê duyệt. Cú pháp property Spring Boot có thể thay đổi theo phiên bản; cần đối chiếu dependency và tài liệu của phiên bản ứng dụng.

Các thuộc tính `spring.neo4j.*` cấu hình **client** trong ứng dụng Java. Chúng **không thay thế** `server.bolt.listen_address` hoặc `server.bolt.advertised_address` trên máy Neo4j. Nếu server công bố endpoint sai, việc sửa URI bootstrap trong Spring chỉ giải quyết được một phần đường đi.

### 15.1. Kiểm tra đúng môi trường triển khai

Trong Kubernetes, service Spring có thể lấy `spring.neo4j.uri` từ ConfigMap/Secret hoặc biến môi trường. Khi chạy local trên laptop, URI `localhost` có thể hợp lệ; khi chạy trong Pod, cùng giá trị đó sẽ trỏ tới Pod ứng dụng.

Đừng dùng chung một file cấu hình local có `localhost:7687` cho container production mà không override. Kiểm tra giá trị **có hiệu lực sau khi Spring load profile/env** (không log mật khẩu), rồi chạy phép thử `RETURN 1` từ Pod thực tế.

## 16. Chọn advertised address theo phạm vi client

Trong một database đơn có ba nhóm client:

| Nhóm client | Đường truy cập | Địa chỉ ứng viên |
|---|---|---|
| Java service cùng host | Loopback | `localhost:7687` |
| Java service cùng VPC | DNS nội bộ | `graph.internal.example:7687` |
| Client bên ngoài qua proxy | FQDN public + NAT | `graph.example.com:17687` |

Vấn đề là **một connector thường có một advertised address hiệu lực trong từng cấu hình**. Không thể chỉ định ba giá trị khác nhau cho ba nhóm client bằng cách đặt ba URI bootstrap khác nhau.

Các hướng thiết kế:

1. **Dùng một FQDN có thể truy cập từ mọi nhóm** qua split DNS/route phù hợp.
2. **Tách đường truy cập theo deployment/endpoint được hỗ trợ**, tránh thay advertised address ngẫu nhiên theo client.
3. **Giới hạn đối tượng client** vào một mạng thống nhất như VPN/VPC và công bố hostname nội bộ.
4. Với **cluster**, dùng thiết kế exposure/routing riêng cho từng thành viên hoặc proxy được hỗ trợ, bảo đảm mọi endpoint mà routing driver nhận được đều reachable.

Không khuyến nghị tự sửa file `hosts` ở từng máy client như giải pháp production lâu dài: cách này khó quản trị, che giấu vấn đề DNS và dễ lỗi khi IP thay đổi.

## 17. Checklist cấu hình trước khi đưa vào vận hành

### 17.1. Về Neo4j server

- [ ] Đã xác định phiên bản Neo4j và **đúng tên setting** của phiên bản đó.
- [ ] Bolt/HTTP/HTTPS chỉ bật những connector cần thiết.
- [ ] `listen_address` bind vào interface và port có thật trong môi trường chạy.
- [ ] `advertised_address` dùng hostname/port client có thể truy cập; không dùng wildcard `0.0.0.0`.
- [ ] Hiểu giá trị kế thừa từ `server.default_listen_address` và `server.default_advertised_address`.
- [ ] Những thay đổi yêu cầu restart đã được áp dụng/rolling restart theo kế hoạch.
- [ ] Xác thực, TLS/certificate và phân quyền đã được cấu hình phù hợp.
- [ ] Nếu có cluster, đã kiểm tra các địa chỉ thành viên được driver routing nhận.

### 17.2. Về DNS, proxy và firewall

- [ ] DNS resolve đúng **từ nơi Java client chạy**.
- [ ] Firewall/security group chỉ mở traffic cần thiết.
- [ ] Docker port mapping hoặc Kubernetes Service/Ingress trỏ đúng destination port.
- [ ] Reverse proxy hỗ trợ **TCP Bolt**, không chỉ HTTP.
- [ ] Nếu NAT đổi cổng, advertised port phản ánh cổng client dùng.
- [ ] TLS termination/passthrough thống nhất với scheme `+s`/`+ssc` của client.
- [ ] Certificate hợp lệ cho hostname mà client thật sự sử dụng.
- [ ] Không để endpoint chỉ tồn tại trong private network xuất hiện trong routing table cho client ngoài mạng đó.

### 17.3. Về ứng dụng Java

- [ ] URI `bolt://` hoặc `neo4j://` được chọn phù hợp topology và yêu cầu routing.
- [ ] TLS được dùng và xác minh certificate cho môi trường cần bảo vệ.
- [ ] Driver được tái sử dụng; Session có vòng đời ngắn.
- [ ] Database name và tài khoản có quyền thích hợp.
- [ ] `verifyConnectivity()` và `RETURN 1` chạy được từ **đúng Pod/container/host**.
- [ ] Có log/tracing phân biệt DNS, TCP, TLS, authentication, routing và pool.
- [ ] Timeout/pool/retry được điều chỉnh sau khi xác nhận đường mạng đúng.

## 18. Các lỗi thường gặp và cách phân tích

| Hiện tượng | Nguyên nhân có thể | Bước kiểm tra/sửa |
|---|---|---|
| Chạy Neo4j local được, máy khác không được | Listen chỉ ở `127.0.0.1`, firewall chặn | Xem listen socket, mạng và rule; không mở public tùy tiện |
| Docker publish port 17687 nhưng Java kết nối 7687 | Nhầm host port với container port | Kiểm tra mapping, URI và advertised port |
| Browser mở trang nhưng không chạy Cypher | HTTP mở, Bolt bị chặn | Thử 7687 từ trình duyệt/client |
| Java bên ngoài nhận `*.svc.cluster.local` | Routing table chứa hostname Pod/Service nội bộ | Thiết kế advertised endpoints/exposure cho client ngoài |
| Kết nối direct được nhưng routing lỗi | Endpoint trong routing table không reachable | Kiểm tra địa chỉ công bố từng server |
| Báo lỗi cannot bind address khi start | Listen IP không thuộc interface hoặc port đang bị chiếm | Dùng IP hợp lệ, kiểm tra socket/port |
| Đổi advertised nhưng không thấy kết quả | Chưa restart hoặc cấu hình bị ghi đè | Đọc SHOW SETTINGS/log startup |
| TLS handshake fail | Proxy TLS, certificate hoặc policy không khớp | Kiểm tra scheme, cert/SAN, tầng terminate |
| Tăng pool vẫn connection refused | Pool không sửa listener/firewall | Kiểm tra TCP và listen address |
| HTTP port 7474 mở Internet | Connector quản trị bị expose không cần thiết | Giới hạn hoặc tắt HTTP, dùng HTTPS/VPN khi cần |
| Đặt `advertised=0.0.0.0:7687` | Dùng wildcard bind làm địa chỉ cho client | Dùng FQDN/IP có thể route từ client |
| Config Neo4j 4.x đặt vào Neo4j 5.x | Sai tên setting | Đối chiếu tài liệu đúng phiên bản và giá trị hiệu lực |
| Server có nhiều NIC, DNS trỏ interface khác | Mismatch DNS/listen interface | Sửa bind/route/DNS theo thiết kế mạng |
| Quá nhiều timeout sau khi truy vấn nặng | Query, pool hoặc tranh chấp DB | Phân tích query plan, pool wait, CPU/locks, không chỉ mạng |

### 18.1. Thứ tự chẩn đoán gợi ý

~~~mermaid
flowchart TD
    A["Java Driver không kết nối được"] --> B{"DNS resolve đúng?"}
    B -->|Không| C["Sửa hostname/DNS theo mạng client"]
    B -->|Có| D{"Mở được TCP host:port?"}
    D -->|Không| E["Kiểm tra listener, firewall, NAT, Service"]
    D -->|Có| F{"TLS/Bolt handshake thành công?"}
    F -->|Không| G["Kiểm tra certificate, scheme, proxy"]
    F -->|Có| H{"Authentication thành công?"}
    H -->|Không| I["Kiểm tra credentials/quyền"]
    H -->|Có| J{"Routing endpoint reachable?"}
    J -->|Không| K["Kiểm tra advertised address/cluster"]
    J -->|Có| L["Kiểm tra database, pool, query và tải"]
~~~

Sơ đồ là quy trình triage, không phải thứ tự kỹ thuật tuyệt đối của mọi handshake/routing phiên bản. Một lỗi có thể xuất hiện ở nhiều lớp; log chi tiết giúp xác nhận thay vì suy đoán.

## 19. Bài tập vận dụng

### Bài 1 — Listen và advertised khác nhau

Neo4j chạy trong container, lắng nghe `0.0.0.0:7687`. Docker publish `17687:7687`. Java service ngoài Docker kết nối bằng hostname `db.example.com`.

**Câu hỏi:** Nên công bố Bolt host:port nào?

**Đáp án:** Nếu `db.example.com:17687` được DNS và mạng chuyển đúng vào container, địa chỉ công bố phù hợp là `db.example.com:17687`. Giá trị listen bên trong vẫn có thể là `0.0.0.0:7687`.

### Bài 2 — Không kết nối được từ máy khác

File cấu hình có:

~~~properties
server.bolt.listen_address=127.0.0.1:7687
server.bolt.advertised_address=graph.internal.example:7687
~~~

Java app chạy ở máy khác trong cùng VPC và gặp timeout.

**Câu hỏi:** Chỉ đổi advertised address có đủ không?

**Đáp án:** Không. Server chỉ bind Bolt ở loopback, nên máy khác không truy cập trực tiếp được. Cần thiết kế listener trên interface mạng phù hợp hoặc dùng tunnel/proxy, đồng thời kiểm tra firewall. Không nhất thiết mở toàn bộ interface ra Internet.

### Bài 3 — Browser tải được nhưng Cypher lỗi

HTTP 7474 đã mở, Bolt 7687 đang bị firewall chặn.

**Câu hỏi:** Vì sao giao diện tải được nhưng không chạy truy vấn?

**Đáp án:** HTTP phục vụ giao diện không thay thế kết nối Bolt cần cho thao tác database. Kiểm tra Bolt từ vị trí của browser/driver và chỉ mở trong phạm vi được phép.

### Bài 4 — Bootstrap cluster thành công, query thất bại

Client ngoài Kubernetes kết nối được qua `db.example.com`, nhưng routing table trả `neo4j-1.svc.cluster.local:7687`.

**Câu hỏi:** Vấn đề nằm ở đâu?

**Đáp án:** Endpoint công bố cho server thành viên không reachable từ client ngoài cluster. Cần thiết kế routing/exposure per-member hoặc proxy được hỗ trợ, không chỉ chỉnh URI bootstrap.

### Bài 5 — Địa chỉ công bố dạng wildcard

Một cấu hình đặt:

~~~properties
server.bolt.advertised_address=0.0.0.0:7687
~~~

**Câu hỏi:** Vì sao cấu hình này sai mục đích?

**Đáp án:** `0.0.0.0` mô tả bind trên nhiều interface, không xác định hostname/IP cụ thể mà client có thể dùng để kết nối. Advertised phải là địa chỉ route được theo phạm vi client.

### Bài 6 — URI TLS và certificate

Java Driver dùng `neo4j+s://graph.example.com:7687` nhưng certificate đầu cuối chỉ có SAN cho `db.internal`.

**Câu hỏi:** Có nên đổi sang `neo4j+ssc://` để hết lỗi production?

**Đáp án:** Không nên coi đó là giải pháp production. Cần cung cấp certificate hợp lệ cho `graph.example.com` hoặc đổi endpoint theo tên được chứng thực, và giữ xác minh trust chain/hostname.

### Bài 7 — Java service trong Docker

Trong Compose network, service Java dùng `bolt://localhost:7687` nhưng Neo4j nằm ở container khác có service name `neo4j`.

**Câu hỏi:** Vì sao `localhost` không đúng?

**Đáp án:** `localhost` trong container Java trỏ về **container Java**. Cần endpoint mà container Java nhìn thấy, thường là `neo4j:7687` cùng Docker network, đồng thời chọn cấu hình advertised/routing phù hợp.

### Bài 8 — Đã thay neo4j.conf nhưng vẫn lỗi

Người vận hành sửa `server.bolt.advertised_address` và không restart. Sau đó Java vẫn nhận routing endpoint cũ.

**Câu hỏi:** Bước kiểm tra nên là gì?

**Đáp án:** Xác nhận đúng instance/config file/biến môi trường, kiểm tra setting hiệu lực, áp dụng restart nếu setting yêu cầu và kiểm tra lại từ client. Không mặc định sửa file được áp dụng ngay.

## 20. Ghi nhớ

**Listen address** trả lời câu hỏi **“tiến trình Neo4j nhận kết nối ở interface/port nào?”**; **advertised address** trả lời **“client nên liên hệ hostname/port nào?”**. Hai địa chỉ có thể khác nhau vì NAT, Docker, Kubernetes, reverse proxy hoặc cluster. `0.0.0.0` thường phù hợp để bind, nhưng **không phải địa chỉ công bố có thể truy cập được**.

Cấu hình kết nối đáng tin cậy phải được kiểm tra **từ đúng môi trường chạy Java Driver/Spring Data Neo4j**, qua từng lớp DNS, TCP, firewall, proxy, TLS, xác thực và routing. Khi dùng `neo4j://`, địa chỉ từng thành viên được trả qua routing cũng phải reachable; không chỉ endpoint bootstrap. Hãy sử dụng **đúng tên setting của phiên bản Neo4j**, bảo vệ connector bằng mạng/TLS/quyền truy cập tối thiểu, và đọc lại cấu hình hiệu lực sau khi triển khai.
