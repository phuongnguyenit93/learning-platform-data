# Triển khai sau proxy, DNS hoặc mạng riêng với địa chỉ kết nối đúng

## 1. Bài toán triển khai: chạy được trên server nhưng ứng dụng không kết nối được

Một dịch vụ Java sử dụng **Neo4j Java Driver** có thể chạy tốt khi đặt cạnh database, nhưng gặp lỗi kết nối sau khi triển khai lên môi trường mới:

- Java service chạy trong Docker không truy cập được `localhost:7687`.
- Ứng dụng ở subnet riêng kết nối được cổng proxy nhưng nhận **routing table** chứa địa chỉ mạng không thể đi tới.
- Neo4j Browser tải được ở cổng HTTP, còn Java Driver thất bại với Bolt.
- DNS trỏ về load balancer mới, nhưng server công bố địa chỉ cũ.
- TCP đã mở, nhưng kết nối `neo4j+s://` thất bại vì certificate không khớp hostname.
- Sau khi chuyển sang Kubernetes, driver không phân giải được tên `*.svc.cluster.local` từ bên ngoài cluster.

Đây không đơn thuần là lỗi “mở đúng port chưa”. Cần hiểu **toàn bộ đường đi** giữa ứng dụng, DNS, proxy, firewall, các cổng và các endpoint được Neo4j công bố.

Trong module DATABASE_ENGINE_GRAPH_NEO4J, ứng dụng dùng property graph để truy vấn node, relationship và đường đi bằng Cypher, đồng thời có thể sử dụng Java Driver hoặc Spring Data Neo4j. Bất kỳ truy vấn nào cũng cần **một kết nối Bolt đúng, có bảo mật và có thể định tuyến** trước khi bàn tới index, tối ưu traversal hay transaction.

> **Mục tiêu bài học:** Thiết kế và kiểm chứng một triển khai Neo4j sau proxy, DNS hoặc mạng riêng, bảo đảm các địa chỉ mà **Java Driver thực sự sử dụng** đều reachable, DNS/TLS phù hợp và truy cập được giới hạn theo chính sách an ninh.

## 2. Hiểu các lớp trong một đường kết nối

Ví dụ triển khai một Neo4j server sau TCP load balancer:

~~~mermaid
flowchart LR
    A["Java / Spring service"] -->|"neo4j+s://graph.example.com:7687"| D["DNS"]
    D --> L["TCP Load Balancer / Proxy"]
    L -->|"private IP:7687"| N["Neo4j Bolt listener"]
    N --> G["Property graph / Cypher"]
~~~

Ở thực tế, có ít nhất sáu giá trị cần thống nhất:

| Giá trị | Ví dụ minh họa | Câu hỏi cần trả lời |
|---|---|---|
| Client URI | `neo4j+s://graph.example.com:7687` | Ứng dụng gọi tới đâu, dùng routing/TLS như thế nào? |
| DNS | `graph.example.com → 203.0.113.20` | Hostname được phân giải thành IP nào từ mạng của ứng dụng? |
| Proxy listener | `203.0.113.20:7687` | Proxy/LB có nhận giao thức TCP Bolt tại port đó không? |
| Upstream target | `10.20.1.15:7687` | Proxy có chuyển được traffic đến Neo4j không? |
| Neo4j listen address | `0.0.0.0:7687` | Neo4j có bind đúng interface/port trong network namespace không? |
| Neo4j advertised address | `graph.example.com:7687` | Neo4j công bố hostname/port mà client có thể dùng chưa? |

**Listen address** là địa chỉ tiến trình Neo4j nhận kết nối. **Advertised address** là địa chỉ được Neo4j cung cấp để bên ngoài tìm đến server. Địa chỉ client cần kết nối được có thể là hostname proxy, không phải IP nội bộ thực sự được Neo4j dùng để bind.

Ví dụ NAT:

~~~text
Ứng dụng Java                    Proxy / NAT                     Neo4j
graph.example.com:17687  --->   public:17687  ------------->  10.20.1.15:7687
                                                                      |
                                                        listen 0.0.0.0:7687
                                                        advertise graph.example.com:17687
~~~

Ở đây, **17687** là port client nhìn thấy, **7687** là port Neo4j thực sự nhận. Nếu địa chỉ được công bố là `10.20.1.15:7687` cho client ở mạng ngoài, routing có thể thất bại vì client không có đường đến IP private.

### 2.1. Ba điều kiện bắt buộc đồng thời

1. **Listener tồn tại:** Neo4j thực sự mở Bolt ở nơi proxy/ứng dụng gửi đến.
2. **Đường mạng hoạt động:** DNS, route, firewall, network policy, NAT và proxy cho phép traffic.
3. **Địa chỉ được công bố đúng:** những endpoint mà driver nhận được có thể được phân giải và truy cập từ chính môi trường ứng dụng.

Ngoài ra, một kết nối sử dụng TLS còn cần **certificate phù hợp hostname và trust chain**, còn truy vấn cần authentication, authorization và database name đúng.

### 2.2. 0.0.0.0 có hai ý nghĩa dễ bị nhầm

~~~properties
server.bolt.listen_address=0.0.0.0:7687
~~~

Giá trị này cho phép Neo4j bind trên những interface IPv4 phù hợp **trong network namespace của tiến trình**. Nó không phải tên host để một client ở xa gọi tới.

**Không dùng**:

~~~properties
server.bolt.advertised_address=0.0.0.0:7687
~~~

làm địa chỉ cho routing client. Wildcard `0.0.0.0` không xác định một đích mạng cụ thể để kết nối. Dùng một hostname/IP có thể route được theo phạm vi client.

## 3. Bolt, HTTP và HTTPS: chọn đúng connector

Triển khai Neo4j thường dùng các connector:

| Connector | Port thường gặp | Chức năng |
|---|---:|---|
| **Bolt** | 7687 | Java Driver, Spring Data Neo4j, Cypher Shell và các client Cypher |
| **HTTP** | 7474 | Giao diện web/Neo4j Browser và những chức năng HTTP được hỗ trợ |
| **HTTPS** | 7473 | Web/HTTP trên TLS khi đã bật và cấu hình phù hợp |
| **Các connector nội bộ cluster** | Tùy phiên bản | Trao đổi server–server, không phải cổng Bolt công khai |

Cổng mặc định **có thể thay đổi**; cần kiểm tra cấu hình đang áp dụng thay vì chỉ nhớ 7687/7474/7473.

### 3.1. Truy cập được Browser không chứng minh Bolt reachable

Một triển khai có thể cho phép:

~~~text
GET https://graph-admin.example.com  → tải trang Neo4j Browser
Neo4j Java Driver                    → timeout khi kết nối Bolt
~~~

Browser/web và Bolt là **hai đường giao thức khác nhau**. Ngay cả khi giao diện web tải được, chạy Cypher vẫn có thể cần kết nối Bolt riêng. Proxy chỉ hỗ trợ HTTP không tự chuyển tiếp giao thức Bolt.

### 3.2. Không dùng HTTP reverse proxy thay TCP proxy cho Bolt

URI dưới đây **không phải** cách kết nối Bolt chỉ nhờ một HTTP path:

~~~text
https://example.com/neo4j/bolt
~~~

Đối với Java Driver, cần endpoint Bolt hợp lệ, ví dụ:

~~~text
neo4j+s://graph.example.com:7687
~~~

Proxy phải hỗ trợ **TCP forwarding**, hoặc cấu hình chuyên biệt được phiên bản/phần mềm triển khai hỗ trợ. Chỉ khai báo quy tắc HTTP path-routing trong một web ingress không đủ nếu không có TCP/stream proxy cho port Bolt.

## 4. Listen và advertised address trong Neo4j

Với những triển khai Neo4j 5.x dùng tên setting tương ứng, có thể gặp:

~~~properties
server.default_listen_address=0.0.0.0
server.default_advertised_address=graph.internal.example

server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.bolt.advertised_address=graph.internal.example:7687
~~~

Ở đây:

- `server.default_listen_address` thiết lập mặc định cho giao diện bind khi connector dùng giá trị kế thừa phù hợp.
- `server.default_advertised_address` là host mặc định công bố khi không override.
- `server.bolt.listen_address` chỉ ra endpoint Bolt mà server nhận.
- `server.bolt.advertised_address` chỉ ra endpoint Bolt được công bố.

**Tên setting phải khớp phiên bản Neo4j đang dùng.** Tài liệu Neo4j 4.x có thể dùng nhóm `dbms.connector.*`; không sao chép nguyên setting của bản cũ vào một bản khác mà chưa kiểm tra migration guide và cấu hình hiệu lực.

### 4.1. Một cấu hình đơn máy có DNS nội bộ

~~~properties
server.bolt.enabled=true
server.bolt.listen_address=10.20.1.15:7687
server.bolt.advertised_address=graph.internal.example:7687

server.http.enabled=false
server.https.enabled=false
~~~

Mô hình giả định Java service chạy trong VPC/VPN có thể phân giải `graph.internal.example` thành IP phù hợp và mở TCP 7687 tới server.

Bind IP riêng phù hợp khi máy sở hữu `10.20.1.15` trên interface. Nếu Neo4j chạy trong container hoặc sau NAT, **không bind vào IP public mà container không sở hữu**, vì socket có thể không mở được.

### 4.2. Khi proxy dùng port bên ngoài khác

~~~properties
# Neo4j nhận Bolt trong mạng private
server.bolt.listen_address=0.0.0.0:7687

# Client nhìn thấy port đã được proxy/NAT công bố
server.bolt.advertised_address=graph.example.com:17687
~~~

Đây là cấu hình minh họa cho một server, với điều kiện proxy chuyển `graph.example.com:17687` tới `Neo4j:7687` và các yêu cầu routing/TLS được đáp ứng.

**Advertised address không tự tạo DNS hay NAT.** Nếu chưa có route từ hostname bên ngoài tới Neo4j, thay setting trong `neo4j.conf` không sửa được vấn đề.

### 4.3. Kiểm tra cấu hình thực tế thay vì chỉ kiểm tra file

Trên phiên bản có hỗ trợ và tài khoản đủ quyền:

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
  'server.https.enabled'
]
RETURN name, value
ORDER BY name;
~~~

Cần phân biệt **cấu hình mong muốn** trong file/biến môi trường với **cấu hình đang có hiệu lực** trong tiến trình. Nhiều thay đổi listener cần restart/redeploy theo tài liệu phiên bản. Ngoài ra, cấu hình container/Helm có thể ghi đè những dòng trong file mà người vận hành đã sửa.

## 5. Chọn URI Java Driver: direct và routing

Neo4j Java Driver có các scheme thường gặp:

| Scheme | Ý nghĩa triển khai |
|---|---|
| `bolt://host:port` | Kết nối Bolt trực tiếp, không dùng routing discovery theo scheme `neo4j` |
| `neo4j://host:port` | Dùng cơ chế routing/discovery của Neo4j Driver |
| `bolt+s://host:port` | Direct Bolt với TLS và xác minh certificate qua trust chain |
| `neo4j+s://host:port` | Routing với TLS và xác minh certificate |
| `bolt+ssc://host:port` | Direct Bolt qua TLS, chế độ chấp nhận certificate self-signed |
| `neo4j+ssc://host:port` | Routing qua TLS, chế độ chấp nhận certificate self-signed |

Dùng `+s` với certificate và trust chain hợp lệ cho môi trường cần bảo mật. `+ssc` có thể giúp thử nghiệm có kiểm soát với certificate self-signed, nhưng **không nên coi nó là giải pháp production cho lỗi TLS/certificate**.

### 5.1. Direct connection

~~~text
Java Driver -- bolt+s://graph.example.com:7687 --> TCP proxy --> Neo4j
~~~

Đây là đường kết nối trực tiếp tới endpoint được chỉ định. Phù hợp khi ứng dụng được thiết kế truy cập một endpoint Neo4j duy nhất qua proxy phù hợp.

**Không chuyển sang `bolt://` chỉ để che một lỗi routing trong cluster** nếu ứng dụng cần automatic routing/failover. Việc đó thay đổi semantics kết nối và có thể làm tính sẵn sàng kém đi.

### 5.2. Routing connection

~~~text
Java Driver
   |
   | neo4j+s://bootstrap.example.com:7687
   v
Bootstrap server / proxy
   |
   | routing discovery
   v
Routing table: [server-a:7687, server-b:7687, server-c:7687]
   |
   v
Driver kết nối trực tiếp đến endpoint được chọn
~~~

Điểm mấu chốt: **bootstrap reachable chưa đủ**. Những hostname/port **được trả về trong routing table** cũng phải reachable từ nơi Java Driver chạy. Một client ngoài VPC nhận `10.20.1.15:7687` có thể kết nối bootstrap rồi vẫn thất bại khi thực hiện truy vấn.

### 5.3. Không đưa mọi member cluster về một hostname tùy tiện

Một cluster Neo4j có thể có nhiều thành viên, vai trò đọc/ghi và endpoint được khám phá qua routing. Nếu tất cả member cùng công bố một hostname load balancer không có cơ chế routing phù hợp, driver có thể không định tuyến được theo thông tin server/role mà nó nhận.

Với cluster, cần dùng **kiến trúc exposure/routing được hỗ trợ cho đúng phiên bản và môi trường**. Thiết kế DNS/port cho từng thành viên hoặc gateway chuyên biệt phải được đánh giá đồng bộ, thay vì áp dụng máy móc cấu hình dành cho một server.

## 6. Thiết kế theo phạm vi mạng của client

Trước khi triển khai, xác định **client chạy ở đâu** và muốn đi qua ranh giới mạng nào.

| Client | Điểm truy cập phù hợp | Những điều phải xác minh |
|---|---|---|
| Java app cùng VM với Neo4j | `localhost:7687` nếu listener loopback và deployment cho phép | Không có container namespace riêng |
| Java app cùng private subnet/VPC | `graph.internal.example:7687` | Private DNS, route, firewall/security group |
| App trong Docker network | `neo4j:7687` theo tên service | DNS mạng container, listener, advertised phù hợp |
| App trong Kubernetes | Service DNS hoặc endpoint nội bộ được hỗ trợ | Namespace, Service selector, NetworkPolicy, topology |
| App chạy ngoài VPC qua VPN | Hostname nội bộ khi VPN cấp DNS/route | Split DNS, route VPN, firewall |
| App chạy từ Internet qua proxy | Public FQDN và port được bảo vệ | TCP proxy, TLS, authentication, exposure policy |
| Java client của Neo4j cluster | Bootstrap và endpoint thành viên mà routing trả về | Mọi advertised Bolt address reachable |

### 6.1. Localhost luôn trỏ về chính môi trường đang chạy client

Ví dụ Java chạy trong Pod còn Neo4j ở Pod khác:

~~~text
bolt://localhost:7687
~~~

sẽ trỏ về loopback của Pod Java, **không trỏ về Pod Neo4j**. Tương tự, Java trong container Docker không thể truy cập container database khác bằng `localhost` trừ khi có mô hình network namespace đặc biệt được thiết kế riêng.

Trước khi sửa cấu hình Neo4j, hãy xác nhận **client đang chạy trong namespace/container/host nào**.

### 6.2. Một FQDN dùng được từ nhiều nơi

Nếu client nội bộ và client ngoài VPC đều cần sử dụng `graph.example.com`, có thể cân nhắc **split-horizon DNS**:

~~~text
Java trong VPC:
graph.example.com → private proxy IP

Java ngoài VPC:
graph.example.com → public proxy IP
~~~

Cách này chỉ hoạt động nếu hai đường đến đều truy cập được một endpoint tương thích cùng hostname/port và chính sách TLS. Split DNS là giải pháp của DNS/hạ tầng, không được Neo4j tự tạo từ advertised setting.

## 7. Triển khai sau TCP proxy hoặc load balancer

Một TCP load balancer có thể đặt giữa Java service và Neo4j nhằm che IP riêng, áp dụng firewall và quản lý endpoint ổn định.

~~~mermaid
flowchart LR
  A["Java Service"] -->|"graph.example.com:17687"| B["TCP Load Balancer"]
  B -->|"10.20.1.15:7687"| C["Neo4j Server"]
  C --> D["Graph database"]
~~~

Một bản thiết kế tối thiểu gồm:

1. **Frontend listener**: hostname/IP và port mà client gọi tới.
2. **Backend target**: IP/port Neo4j mà LB chuyển tiếp.
3. **Health check**: đánh giá server đủ khả năng nhận request theo cơ chế LB hỗ trợ.
4. **TLS**: xác định passthrough/termination/re-encryption.
5. **Firewall**: cho phép những nguồn cần thiết đến frontend và chỉ LB đến backend.
6. **Idle timeout/connection lifetime**: phù hợp với kết nối Bolt tương đối lâu dài.
7. **Advertised endpoint**: các hostname/port được công bố phù hợp với tuyến mà driver sử dụng.

### 7.1. Proxy TCP khác proxy HTTP

Một HTTP reverse proxy phục vụ website có thể chỉ chuyển các request theo HTTP host/path. Bolt dùng protocol riêng trên kết nối TCP; phải dùng **TCP stream/forwarding** hoặc giải pháp gateway được hỗ trợ.

Ví dụ minh họa cấu hình NGINX stream cho một Neo4j instance (chỉ áp dụng nếu bản NGINX có module `stream`):

~~~nginx
stream {
    upstream neo4j_bolt {
        server 10.20.1.15:7687;
    }

    server {
        listen 17687;
        proxy_pass neo4j_bolt;
        proxy_connect_timeout 5s;
        proxy_timeout 1h;
    }
}
~~~

Đây là **cấu hình minh họa**, chưa có policy IP allowlist, giới hạn kết nối, TLS, giám sát và cấu hình hệ thống cần thiết. Không sao chép nguyên vào production nếu chưa rà soát bảo mật và mô hình cluster.

### 7.2. TLS passthrough và TLS termination

| Kiểu | Ai chấm dứt TLS với client? | Cần kiểm tra |
|---|---|---|
| **Passthrough** | Neo4j backend | Neo4j có Bolt TLS và certificate khớp FQDN client |
| **Termination tại proxy** | TCP proxy | Proxy có certificate hợp lệ; upstream cần được bảo vệ bằng mạng hoặc TLS riêng |
| **Termination + re-encryption** | Proxy và backend theo hai phiên TLS | Trust, hostname và policy ở cả hai đoạn |

Nếu client dùng `neo4j+s://graph.example.com:17687`, đầu cuối TLS mà client nhìn thấy phải trình bày certificate đáng tin cậy cho `graph.example.com`. Việc TCP đã mở thành công **không chứng minh TLS handshake sẽ thành công**.

### 7.3. Load balancer không sửa routing table sai

Nếu proxy chỉ nhận bootstrap, còn Neo4j công bố các endpoint private như `10.20.1.15:7687` hoặc các tên Pod nội bộ, một routing driver ở ngoài mạng vẫn có thể lỗi. Để khắc phục, thiết kế advertised endpoint và khả năng kết nối của **tất cả server được driver chọn**, không chỉ frontend proxy.

### 7.4. Health check phải trả lời đúng câu hỏi

Kiểm tra TCP connect có thể phát hiện backend không mở socket, nhưng **không khẳng định**:

- Database đã sẵn sàng chạy Cypher.
- Authentication/TLS của client hợp lệ.
- Server ở đúng vai trò cho truy vấn ghi.
- Routing table đang chứa các endpoint reachable.
- Query workload thực tế sẽ hoàn thành đúng SLO.

Tùy hạ tầng, có thể kết hợp TCP readiness với phép thử Bolt/Driver ở pipeline giám sát riêng; không đặt health check tốn kém lên từng request người dùng.

## 8. Docker Compose: phân biệt cổng host và cổng container

Giả sử Neo4j chạy trong Docker và muốn Java service ngoài host Docker kết nối qua port `17687`.

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
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
~~~

Ví dụ chỉ thể hiện một phần cấu hình mạng/volume. Khi triển khai thật cần quản lý auth, secret, TLS, quyền volume, network policy và backup; **không dùng ví dụ như Docker Compose production hoàn chỉnh**.

### 8.1. Quy tắc mapping

~~~text
Client Java
  graph.example.com:17687
          |
Docker host:17687
          |
Docker port mapping 17687:7687
          |
Neo4j container:7687
listen 0.0.0.0:7687
~~~

Trong Docker Compose, `17687:7687` có nghĩa **host port → container port**. Nếu Java nằm ngoài mạng container, dùng port bên ngoài. Nếu Java trong cùng Docker network, nó có thể dùng service name và container port `neo4j:7687` khi tuyến và cấu hình được thiết kế cho client nội bộ.

### 8.2. Biến môi trường và dấu gạch dưới

Với quy tắc environment variable của Neo4j Docker image phù hợp:

~~~text
server.bolt.listen_address
    → NEO4J_server_bolt_listen__address

server.bolt.advertised_address
    → NEO4J_server_bolt_advertised__address
~~~

Một dấu chấm trong setting thường tương ứng một dấu gạch dưới, còn dấu gạch dưới vốn có trong tên setting được escape thành **hai dấu gạch dưới**. Kiểm tra chính xác theo image/tag đang chạy; sai tên có thể khiến setting không có hiệu lực.

### 8.3. Chú ý Docker port không tự giới hạn nguồn truy cập

Dòng:

~~~yaml
ports:
  - "17687:7687"
~~~

có thể publish lên những interface của host theo quy tắc Docker. Nếu không muốn công khai, phải chỉ định host binding phù hợp, dùng private network/firewall và tránh mở port ra Internet.

Ví dụ bind chỉ loopback của host:

~~~yaml
ports:
  - "127.0.0.1:17687:7687"
~~~

Cấu hình này phù hợp cho ứng dụng **cùng host** hoặc kết nối qua tunnel, không cho client ở máy khác truy cập trực tiếp theo mặc định.

### 8.4. Khi có cả client nội bộ và bên ngoài Docker

Một connector thường chỉ có **một advertised address hiệu lực** tại thời điểm chạy. Nếu client nội bộ chỉ resolve `neo4j` còn client ngoài chỉ resolve `graph.example.com`, routing có thể không tương thích với cả hai.

Giải pháp có thể là FQDN chung với DNS/route hoạt động ở cả hai phạm vi, hoặc tách kiến trúc endpoint/triển khai được hỗ trợ. **Không tùy tiện đặt advertised theo hostname của Docker rồi hy vọng client bên ngoài tự hiểu**.

## 9. Kubernetes: Service, private DNS và kết nối Bolt

Trong Kubernetes, một Java service thường truy cập Neo4j qua **Kubernetes Service**, ví dụ:

~~~text
neo4j.graph.svc.cluster.local:7687
~~~

Nhưng hostname `*.svc.cluster.local` thường chỉ được phân giải và route trong cluster (hoặc qua cấu hình DNS/mạng đặc biệt). Một client ngoài cluster không nên nhận tên này trong routing table nếu không có đường tới đó.

### 9.1. Ví dụ Service nội bộ cho triển khai đơn server

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: neo4j-bolt
  namespace: graph
spec:
  type: ClusterIP
  selector:
    app: neo4j
  ports:
    - name: bolt
      protocol: TCP
      port: 7687
      targetPort: 7687
~~~

Ví dụ giả định Pod Neo4j thực sự có label `app: neo4j` và đang nghe Bolt tại port 7687. Kubernetes Service không tự khởi tạo Neo4j, dữ liệu volume, certificate hay quyền người dùng.

Đường đi:

~~~text
Java Pod
   |
   | neo4j-bolt.graph.svc.cluster.local:7687
   v
ClusterIP Service
   |
   v
Neo4j Pod Bolt listener:7687
~~~

Cần kiểm tra Service selector/EndpointSlice/Pod readiness và **NetworkPolicy**. Nếu Service không có endpoint, việc sửa `server.bolt.advertised_address` trong Neo4j thường không giúp Pod Java đi qua Service được.

### 9.2. Địa chỉ công bố cho client nội bộ

Với một database server trong cluster, nếu client nội bộ dùng Service FQDN và routing tương thích, có thể cân nhắc công bố hostname mà các client đó truy cập được. Tuy nhiên, topology cluster và cách service cân bằng tải có thể đòi hỏi cấu hình per-member riêng.

Trong cluster, không mặc định một Service ClusterIP chung là advertised address đúng cho **mọi thành viên**.

### 9.3. Client bên ngoài Kubernetes

Nếu Java chạy ngoài cluster, cần quyết định có cho phép truy cập không và dùng kiến trúc xuất bản được hỗ trợ:

- VPN/private interconnect vào VPC/VNet rồi dùng private DNS nếu phù hợp.
- TCP LoadBalancer hoặc TCP proxy.
- Định tuyến riêng cho từng member cluster khi routing yêu cầu.
- Certificate/TLS và firewall tương ứng.

Một HTTP Ingress controller thông thường không đảm bảo chuyển tiếp Bolt chỉ vì đã tạo rule path. Phải cấu hình TCP proxy/Ingress hỗ trợ stream hoặc controller/gateway tương ứng.

### 9.4. Tránh công bố Pod IP không ổn định

Pod IP có thể thay đổi khi restart/reschedule. Nếu client ở ngoài cluster nhận Pod IP từ routing table, kết nối có thể mất khi Pod thay đổi hoặc do IP không route được.

Với topology cần từng member có identity ổn định, kiến trúc thường cần hostname/dịch vụ ổn định phù hợp StatefulSet/cluster deployment được hỗ trợ. Đừng suy đoán rằng một Pod IP tạm thời là endpoint public bền vững.

## 10. Neo4j cluster: routing và địa chỉ của từng thành viên

Đối với cluster, kết nối từ Java Driver có thêm bước **khám phá topology**. Một ứng dụng thường dùng scheme `neo4j://`/`neo4j+s://` để driver nhận thông tin routing.

~~~mermaid
flowchart LR
  J["Java Driver"] -->|"Bootstrap"| B["Gateway / bootstrap"]
  B --> R["Routing table"]
  R --> A["Member A: Bolt endpoint"]
  R --> C["Member B: Bolt endpoint"]
  R --> D["Member C: Bolt endpoint"]
~~~

Khi triển khai:

1. Chọn bootstrap hostname/port mà Java reachable.
2. Đảm bảo các member Neo4j công bố địa chỉ Bolt phù hợp với mạng client.
3. Đảm bảo DNS cho từng endpoint có tính ổn định theo topology.
4. Nếu có TLS, certificate và routing qua proxy phải hợp lệ cho hostname mà client dùng.
5. Kiểm tra cả hoạt động **read** và **write**, không chỉ kết nối tới bootstrap.
6. Kiểm tra tình huống server đổi vai trò, failover và thay đổi thành viên.
7. Giới hạn các cổng giao tiếp **server–server** ở mạng nội bộ; không mở bừa ra ngoài chỉ vì Bolt client cần routing.

### 10.1. Mọi advertised endpoint đều phải reachable

Giả sử routing table trả về:

~~~text
server-a.internal:7687
server-b.internal:7687
server-c.internal:7687
~~~

Nếu Java ở ngoài mạng có thể connect bootstrap qua `graph.example.com` nhưng không resolve các hostname trên, truy vấn có thể thất bại sau discovery.

Một kế hoạch xuất bản hợp lệ phải giải quyết **cả ba endpoint** hoặc dùng gateway/routing architecture được sản phẩm hỗ trợ. **Không chỉ tạo DNS public cho bootstrap rồi dừng**.

### 10.2. Cluster address nội bộ khác Bolt address cho client

Neo4j cluster có thể cần các địa chỉ server–server để điều phối/trao đổi dữ liệu theo phiên bản và kiến trúc. Các địa chỉ nội bộ này không nhất thiết trùng với `server.bolt.advertised_address`.

Không sao chép cấu hình Bolt public vào tất cả setting cluster, cũng không để các cổng nội bộ cluster lộ ra Internet nếu không có yêu cầu rõ ràng và biện pháp bảo mật được duyệt.

### 10.3. Routing table có thể thay đổi theo thời gian

Trong một cluster hoạt động, server có thể đổi vai trò hoặc thay đổi số thành viên. Kiểm thử nên bao gồm:

- Client khởi động mới sau deploy.
- Reconnect khi proxy/LB bị thay thế.
- Failover của server đang phục vụ write.
- Cập nhật DNS với TTL thực tế.
- Tác động của connection pool và retry trong Java Driver.

Một phép `RETURN 1` thành công ngay sau deployment không chứng minh toàn bộ đường routing sẽ ổn định khi failover.

## 11. VPN, private DNS và mạng riêng

Không phải database nào cũng cần công khai ra Internet. Với ứng dụng doanh nghiệp, thường ưu tiên Neo4j trong **private subnet/VPC/VNet** và chỉ cho phép service được phê duyệt truy cập.

Ví dụ:

~~~text
Java Service subnet A                 Neo4j subnet B
10.30.1.0/24                         10.30.2.0/24
       |                                    |
       | private DNS graph.internal.example|
       +---------- private route ---------->|
                                             |
                                 listen 10.30.2.15:7687
                                 advertise graph.internal.example:7687
~~~

Các yếu tố cần xác minh:

- Private DNS resolve từ **subnet của client**.
- Route giữa subnet/VPC, NAT hoặc peering phù hợp.
- Firewall/security group cho phép nguồn Java đến Bolt 7687.
- Database không phải mở port public không cần thiết.
- Các ứng dụng ngoài mạng dùng VPN/private link hoặc proxy được phê duyệt.
- Certificate dùng tên nội bộ hoặc tên DNS thống nhất theo thiết kế.

### 11.1. DNS resolve đúng nhưng route vẫn có thể sai

`graph.internal.example` có thể trả về IP đúng nhưng client không có route tới subnet đích. Khi đó lỗi là **đường mạng**, không phải Neo4j authentication.

Cần phân biệt:

1. Resolve DNS.
2. Mở TCP tới IP:port.
3. Hoàn tất TLS/Bolt handshake.
4. Xác thực.
5. Routing/discovery.
6. Chạy Cypher.

Mỗi tầng có cách chẩn đoán khác nhau; việc tăng connection timeout có thể che triệu chứng nhưng không tạo route còn thiếu.

### 11.2. Split-horizon DNS có thể giúp dùng một hostname

Một FQDN có thể resolve tới private IP từ nội bộ và public proxy từ bên ngoài. Nhưng thiết kế này cần kiểm tra tương thích TLS, advertised port và routing trong cả hai phạm vi; không nên dựa vào một mục ghi tạm trong `hosts` trên từng máy để duy trì production.

## 12. Bảo mật: DNS và proxy không thay thế TLS, xác thực

Đặt Neo4j sau proxy hoặc private subnet giúp kiểm soát **khả năng truy cập mạng**, nhưng không tự tạo đầy đủ bảo mật ứng dụng.

Cần xem xét:

- **TLS mã hóa kết nối Bolt**, kiểm tra hostname và trust chain.
- **Authentication** cho tài khoản Neo4j.
- **Authorization** theo database, role và các quyền cần thiết.
- **Network segmentation** hạn chế nguồn được phép đến listener.
- **Secrets management** cho mật khẩu, token, certificate/private key.
- **Log redaction** để không lộ credentials, Cypher parameters hoặc dữ liệu node/relationship.
- **Backup/restore** và kiểm thử khôi phục trên hạ tầng mới.

### 12.1. TLS hostname phải khớp nơi Java kết nối

Nếu client dùng:

~~~text
neo4j+s://graph.example.com:7687
~~~

đầu cuối TLS mà client nhìn thấy cần có certificate hợp lệ cho `graph.example.com`. Nếu certificate chỉ được cấp cho `db.internal`, có thể gặp hostname mismatch.

Đừng tự động chuyển sang `neo4j+ssc://` hoặc tắt kiểm tra certificate chỉ để qua lỗi production. Thay vào đó, sửa certificate, FQDN hoặc điểm chấm dứt TLS cho đúng thiết kế.

### 12.2. Hai đoạn TLS qua proxy

Ví dụ terminate tại proxy:

~~~text
Java --TLS--> Proxy --private TCP/TLS--> Neo4j
~~~

Cần quyết định rõ upstream từ proxy đến Neo4j có được mã hóa không, mạng backend có đáng tin không, và có cơ chế xác thực/ủy quyền nào được thiết lập. **TLS ở đoạn client→proxy không tự mã hóa đoạn proxy→database**.

### 12.3. Đừng công khai HTTP quản trị khi chỉ cần Bolt

Nếu Java service chỉ cần truy cập database qua Bolt, không có lý do mặc định mở cổng HTTP/HTTPS quản trị cho Internet.

Ví dụ định hướng:

~~~properties
server.bolt.enabled=true
server.http.enabled=false
server.https.enabled=false
~~~

Nếu đội vận hành cần Neo4j Browser, triển khai đường truy cập quản trị riêng qua VPN, HTTPS hoặc mạng được kiểm soát. Những setting trên chỉ là định hướng bật/tắt connector, không thay thế chính sách xác thực database.

### 12.4. Secrets không nằm trong URI/log

Không đưa mật khẩu vào log hoặc source code:

~~~text
# Không nên lưu hoặc ghi log ở dạng này:
neo4j://user:actual-password@graph.example.com:7687
~~~

Dùng URI chỉ chứa endpoint, còn username/password được cấp qua cơ chế authentication của Driver và secret manager. Khi debug, log **operation name, error category, latency** thay vì toàn bộ thông tin kết nối và bí mật.

## 13. Java Driver: kiểm chứng kết nối từ môi trường ứng dụng

Một phép thử bằng Cypher Shell trên Neo4j server không đủ để khẳng định Java Pod hoặc container ứng dụng có đường mạng đúng.

Ví dụ Java Driver có phương thức xác nhận kết nối và một truy vấn tối thiểu:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jConnectivitySmokeTest {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        if (uri == null || uri.isBlank()
                || username == null || username.isBlank()
                || password == null || password.isBlank()) {
            throw new IllegalArgumentException(
                "Neo4j connection environment is incomplete"
            );
        }

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase("neo4j"))) {
                int one = session.executeRead(tx ->
                    tx.run("RETURN 1 AS value")
                      .single()
                      .get("value")
                      .asInt()
                );
                if (one != 1) {
                    throw new IllegalStateException(
                        "Unexpected Neo4j smoke-test value"
                    );
                }
                System.out.println("Neo4j Bolt smoke test succeeded");
            }
        }
    }
}
~~~

Đoạn code minh họa API thường gặp của Java Driver. Trong ứng dụng thực, **Driver nên được tái sử dụng theo vòng đời ứng dụng**, không tạo/đóng lại ở mỗi request. Smoke test dạng `main` được tách riêng nhằm kiểm tra một lần.

### 13.1. Test theo tầng

- `verifyConnectivity()`: xác minh Driver có thể thiết lập kết nối theo URI và authentication phù hợp.
- `RETURN 1`: kiểm tra có thể chạy một truy vấn Cypher đọc tối thiểu.
- Truy vấn nghiệp vụ đại diện: kiểm tra quyền, database đúng và đường đi đã được thiết kế.
- Với routing cluster: kiểm tra read/write transaction theo topology và failover được cho phép.
- Với TLS: kiểm tra certificate khớp URI, không bỏ qua hostname validation.

Một phép kiểm tra thành công không đảm bảo mọi lần kết nối và mọi thành viên cluster sau này đều luôn sẵn sàng. Cần monitoring và retry phù hợp ở tầng ứng dụng.

### 13.2. Managed transaction và retry không sửa DNS

`session.executeRead` và `session.executeWrite` có thể retry các lỗi tạm thời mà Driver phân loại là phù hợp. Chúng **không thể sửa**:

- DNS không tồn tại.
- IP không có route.
- Firewall chặn vĩnh viễn.
- Certificate không hợp lệ.
- Advertised endpoint không reachable từ mạng client.
- Database/user không có quyền.

Không tăng retry time hoặc pool size vô hạn khi nguyên nhân là mạng/cấu hình. Retry quá nhiều có thể làm request chậm và tăng tải hệ thống.

### 13.3. Truyền tham số và giữ kết quả nhỏ

Trong kiểm thử truy vấn sau deploy, luôn dùng Cypher parameters:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
RETURN c.customerId AS customerId,
       c.status AS status
LIMIT 1;
~~~

Tránh log giá trị nhạy cảm của `$customerId`, email, token hoặc record graph. Lấy dữ liệu tối thiểu phục vụ smoke test và vận hành; không chạy traversal/path lớn chỉ để chứng minh port Bolt đã hoạt động.

## 14. Spring Data Neo4j: phân tách client URI và server topology

Với Spring Boot sử dụng Spring Data Neo4j, một mẫu cấu hình ứng dụng:

~~~properties
# application.properties — minh họa, không lưu mật khẩu thực trong repo.
spring.neo4j.uri=neo4j+s://graph.example.com:7687
spring.neo4j.authentication.username=app_user
spring.neo4j.authentication.password=USE_SECRET_PROVIDER
~~~

Ví dụ cho thấy **URI của client**, không phải tên setting để Neo4j server bind port. Trong triển khai thực, mật khẩu phải được lấy từ secret manager/biến môi trường được quản lý, và property cần được kiểm tra theo phiên bản Spring Boot đang dùng.

### 14.1. Configuration per environment

| Môi trường | URI ứng viên | Lưu ý |
|---|---|---|
| Local trên máy dev | `bolt://localhost:7687` | Chỉ dùng khi server local hoặc tunnel phù hợp |
| Java Docker cùng network | `bolt://neo4j:7687` | Service DNS, advertised/routing phù hợp |
| Java Pod cùng cluster | `neo4j+s://neo4j-bolt.graph.svc.cluster.local:7687` | DNS, TLS certificate và topology phải hỗ trợ |
| Java service trong VPC | `neo4j+s://graph.internal.example:7687` | Route private, DNS nội bộ |
| Java ngoài mạng qua proxy | `neo4j+s://graph.example.com:17687` | Proxy TCP/TLS, routing endpoints đều reachable |

Các giá trị là **ứng viên theo điều kiện**, không phải cấu hình mặc định áp dụng cho mọi topology. Ví dụ dùng `neo4j+s` giả định server/proxy thực sự hỗ trợ TLS với certificate hợp lệ. Nếu môi trường local dùng `bolt://` không mã hóa, chỉ nên dùng trong phạm vi thử nghiệm được bảo vệ.

### 14.2. Không để localhost lọt vào profile container

Một service chạy local trên máy dev có thể dùng `localhost:7687`. Khi deploy Pod/container, cùng địa chỉ trở thành **loopback của chính container**, thường không phải Neo4j.

Cần xác minh **cấu hình hiệu lực sau khi ứng dụng đã load profile, environment và secret**. Không chỉ kiểm tra file `application.properties` trong repository mà bỏ qua các giá trị override của môi trường chạy.

### 14.3. Database và quyền không đồng nghĩa network

Một request có thể kết nối Bolt thành công nhưng thất bại khi chọn database hoặc chạy Cypher do quyền. Hãy tách:

- Network/TLS.
- Authentication.
- Database name.
- Authorization.
- Query/schema/index và hiệu năng.

Tránh đổi listener/advertised address để xử lý một lỗi phân quyền khi handshake đã thành công.

## 15. Quy trình triển khai có kiểm soát

Một quy trình thực hành nên có các giai đoạn rõ ràng.

### 15.1. Bước 1 — Lập bản đồ topology trước khi thay đổi

Ghi lại:

| Thành phần | Thông tin cần biết |
|---|---|
| Client | Host/Pod/container, subnet, DNS resolver, URI |
| Neo4j | Phiên bản, số server, edition/topology, database |
| Listen | IP/interface và port theo connector |
| Advertised | FQDN/IP và port mà driver nhận |
| Proxy/LB | Frontend listener, backend target, protocol, health check |
| DNS | Zone, bản ghi, TTL, split DNS nếu có |
| Network | Route, firewall, security group, VPN/private link |
| TLS | Điểm termination, certificate/SAN và trust chain |
| Driver | Version, scheme direct/routing, timeout, pool |
| Security | Service account, roles, secrets, log retention |

Tạo **sơ đồ đường đi mạng** cho từng nhóm client. Nếu không thể giải thích một URI kết nối tới đâu ở từng bước, chưa đủ cơ sở để chốt cấu hình.

### 15.2. Bước 2 — Xây cấu hình cho đúng topology

- Với một server: chọn listen trong host/network namespace và advertised FQDN/port reachable.
- Với container: bổ sung host port mapping và tránh nhầm `localhost`.
- Với Kubernetes: kiểm tra Service, selector, endpoint và private DNS.
- Với cluster: đảm bảo **mọi endpoint** được routing trả về đều reachable.
- Với proxy: dùng TCP forwarding và quyết định TLS passthrough/termination.
- Với private network: firewall/route/DNS nội bộ phải phù hợp.

Không copy cả một file cấu hình từ local sang production mà không điều chỉnh hostname, port, secret và mức public exposure.

### 15.3. Bước 3 — Kiểm tra trước khi chuyển traffic

Tối thiểu:

1. Confirm Neo4j process khởi động được và mở listener.
2. Đọc lại cấu hình hiệu lực.
3. Kiểm tra DNS từ **nơi Java sẽ chạy**.
4. Kiểm tra TCP tới endpoint client.
5. Kiểm tra TLS certificate/hostname.
6. Test Driver, authentication và `RETURN 1`.
7. Với routing, kiểm tra endpoint thành viên và đường read/write.
8. Kiểm tra metric/log an toàn và backup trước thay đổi.
9. Xác nhận quyền truy cập không rộng hơn thiết kế.

### 15.4. Bước 4 — Cutover và quan sát

Khi chuyển DNS hoặc load balancer:

- Ghi lại thời điểm thay đổi và giá trị DNS trước/sau.
- Xem xét TTL DNS, cache client và connection pool.
- Duy trì thời gian chồng lấn endpoint cũ/mới khi kế hoạch cho phép.
- Theo dõi connection errors, TLS errors, routing failures, timeout và p95/p99.
- Kiểm tra đường đọc/ghi nghiệp vụ đại diện.
- Chỉ tăng traffic khi các điều kiện nghiệm thu được đáp ứng.

Không dùng việc “một request test thành công” làm bằng chứng toàn bộ client/cluster đã cutover đúng.

### 15.5. Bước 5 — Rollback có chuẩn bị

Trước khi deploy, xác định:

- Cấu hình listen/advertised và DNS/proxy trước thay đổi.
- Cách rollback load balancer target, Service hoặc version cấu hình.
- Điều kiện nào bắt buộc ngừng chuyển traffic.
- Tác động của DNS TTL và connection pool khi rollback.
- Cách xác minh database không bị mất dữ liệu và transaction vẫn thành công.

Rollback đường mạng không đồng nghĩa rollback dữ liệu. Nếu deployment đi kèm migration schema, phải có kế hoạch migration/backup riêng; không lẫn với việc đổi địa chỉ kết nối.

## 16. Chẩn đoán lỗi từ DNS đến Cypher

Nên kiểm tra **từ môi trường client thực tế**, không chỉ từ máy Neo4j.

### 16.1. Bước A: DNS

Trên hệ điều hành có công cụ tương ứng:

~~~bash
# Có thể dùng trên nhiều môi trường Linux:
getent hosts graph.example.com

# Hoặc công cụ DNS tương đương nếu có:
nslookup graph.example.com
~~~

Giải quyết lỗi DNS trước khi sửa Neo4j authentication hoặc database name. Với split-horizon DNS, chạy từ **mỗi subnet/client context** để thấy khác biệt.

### 16.2. Bước B: TCP

~~~bash
nc -vz graph.example.com 7687
~~~

Nếu cổng bên ngoài là 17687, phải kiểm tra đúng cổng đó:

~~~bash
nc -vz graph.example.com 17687
~~~

TCP connect thành công **không chứng minh** Neo4j Bolt/TLS/authentication hoạt động. TCP bị từ chối hoặc timeout có thể do firewall, route, proxy listener, port mapping hoặc server không lắng nghe.

### 16.3. Bước C: TLS, authentication và Bolt

Ở môi trường có Cypher Shell và quyền phù hợp:

~~~bash
cypher-shell -a "neo4j+s://graph.example.com:7687" -u app_user
~~~

Lệnh giả định endpoint đã có Bolt TLS với certificate phù hợp và user được phép. Đừng đưa mật khẩu production lên dòng lệnh nếu có thể bị lưu trong history/process list; sử dụng phương thức nhập secret an toàn.

Nếu lỗi TLS, kiểm tra certificate SAN, hostname, trust chain và nơi termination. Nếu lỗi authentication, kiểm tra user/secret/role, không thay đổi DNS để “thử”.

### 16.4. Bước D: routing

Nếu direct kết nối được nhưng `neo4j+s://` lỗi, cần kiểm tra endpoint do routing trả về và topology mà client thấy. Điều này **không có nghĩa** nên đổi sang direct lâu dài trong một cluster cần routing.

### 16.5. Bước E: query

Khi network đã thông, kiểm tra:

~~~cypher
RETURN 1 AS ok;
~~~

Sau đó chạy một truy vấn nghiệp vụ chỉ đọc với tham số giả và quyền phù hợp. Nếu query chậm, mới xem index, EXPLAIN/PROFILE trong môi trường được phép và tải graph, thay vì tiếp tục thay port.

## 17. Bảng đối chiếu lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra ưu tiên |
|---|---|---|
| Java trong container dùng `localhost` không kết nối | Đang gọi chính container Java | Dùng DNS/service name hợp lệ trong network |
| Proxy 17687 chuyển tới Neo4j 7687 nhưng driver gọi 7687 | Nhầm internal và external port | So frontend listener, mapping và URI |
| Neo4j không bind được IP public | IP không nằm trên interface của tiến trình | Bind IP nội bộ hoặc wildcard đúng phạm vi |
| DNS đúng nhưng TCP timeout | Route/firewall/NAT/Service sai | Kiểm tra từ client subnet và proxy target |
| `Connection refused` | Không có listener hoặc rule từ chối | Socket/listen/port mapping |
| TCP mở nhưng TLS fail | Certificate, scheme hoặc termination sai | Hostname, SAN, trust, passthrough |
| HTTP Browser lên nhưng Cypher lỗi | Bolt không mở/reachable | Kiểm tra Bolt riêng |
| Bootstrap cluster reachable, query fail | Advertised member address unreachable | Đối chiếu routing table và mạng client |
| Driver ngoài K8s nhận `*.svc.cluster.local` | Địa chỉ nội bộ bị công bố ra ngoài | Thiết kế exposure/routing |
| Đổi `neo4j.conf` nhưng không thấy tác dụng | Chưa restart, config bị override | SHOW SETTINGS, log startup và nguồn cấu hình |
| Spring profile vẫn dùng `localhost` | Override môi trường sai | Kiểm tra URI hiệu lực trong Pod |
| Connection pool timeout | Nhiều transaction/pool limit hoặc server tải cao | Pool wait, transaction latency, query plan |
| Authentication failed | Credentials/role sai | Secret và quyền, không chỉnh firewall tùy tiện |
| Routing chỉ lỗi sau failover | Endpoint mới không reachable/TLS sai | Test member mới từ client context |
| `+ssc` mới kết nối được | Certificate/trust chưa chuẩn | Sửa cert/trust thay vì bỏ kiểm chứng |
| Proxy health OK nhưng query lỗi | Chỉ TCP readiness thành công | Bolt/routing/read-write smoke test |
| Đổi DNS nhưng client vẫn tới IP cũ | TTL/cache/connection pool chưa refresh | Quan sát DNS và vòng đời kết nối |

### 17.1. Đừng sửa nhiều lớp cùng lúc

Nếu cùng lúc đổi URI, advertised address, TLS policy, proxy listener và firewall, rất khó biết thay đổi nào giải quyết hoặc gây ra lỗi. Khuyến nghị thay **một nhóm điều kiện có giả thuyết rõ**, ghi lại trước/sau và kiểm tra qua từng lớp.

## 18. SLO và giám sát sau triển khai

Một deployment kết nối đúng không chỉ là “không còn Connection refused”. Ứng dụng còn phải duy trì chất lượng truy vấn và transaction.

| Nhóm giám sát | Ví dụ chỉ số |
|---|---|
| Connectivity | Tỷ lệ kết nối Bolt thành công, timeout |
| Routing | Lỗi routing table, endpoint không reachable |
| TLS | Handshake/certificate failure |
| Authentication | Lỗi đăng nhập/quyền |
| Driver pool | Số connection, pool wait, acquisition timeout |
| Database | Transaction latency, deadlock, query error |
| Performance | p50/p95/p99 query/API latency, completed RPS |
| Proxy/LB | Frontend connections, backend failures, idle timeout |
| DNS/Network | Resolve failure, kết nối đến IP/cổng không đúng |
| Availability | Kết quả readiness, chuyển vai trò/failover |
| Data correctness | Kết quả read/write và kiểm tra nghiệp vụ cơ bản |

### 18.1. Không log dữ liệu nhạy cảm khi debug mạng

Một lỗi kết nối hoặc Cypher có thể khiến application log in URI kèm thông tin nhạy cảm, parameter hoặc node result. Khi triển khai hệ thống giám sát:

- Log **operation name, error category, thời lượng, endpoint alias đã duyệt**.
- Không log mật khẩu, token hoặc parameter map.
- Không ghi entire graph result vào APM/trace.
- Giới hạn quyền xem log và retention.
- Dùng canary dữ liệu giả để kiểm thử chính sách redaction.

Network debugging không cần email hoặc số tài khoản khách hàng thật.

### 18.2. Tách lỗi kết nối khỏi lỗi truy vấn

Nếu `RETURN 1` thành công nhưng truy vấn duyệt relationship vẫn chậm, nguyên nhân có thể nằm ở index, fan-out, cardinality hoặc contention. Không quy mọi latency cao cho proxy trước khi đo phần thời gian mạng, pool wait và thực thi database.

## 19. Ví dụ thiết kế ba môi trường

### 19.1. Môi trường local

~~~text
Java desktop → bolt://localhost:7687 → Neo4j local
~~~

Đặc điểm:

- Có thể bind Neo4j tại loopback nếu không cần kết nối ngoài máy.
- Không cần public DNS, NAT hoặc proxy.
- Không dùng môi trường này để chứng minh TLS/routing của production.

### 19.2. Môi trường staging trong private VPC

~~~text
Java Service private subnet
     |
     | neo4j+s://graph.staging.internal:7687
     v
Private TCP endpoint
     |
     v
Neo4j server private IP:7687
~~~

Điều kiện:

- DNS nội bộ resolve đúng.
- Firewall chỉ cho phép source ứng dụng.
- TLS có certificate cho FQDN staging.
- Địa chỉ được công bố phù hợp mạng staging.
- Có test đồng thời read/write và kiểm tra log không lộ secret.

### 19.3. Production cluster sau proxy

~~~text
Java Service / Client network
     |
     | neo4j+s://graph.prod.example.com:7687
     v
Approved bootstrap endpoint
     |
     v
Routing discovery
     |
     +--> Member A externally reachable endpoint
     +--> Member B externally reachable endpoint
     +--> Member C externally reachable endpoint
~~~

Điều kiện trọng tâm:

- Hệ thống routing được thiết kế **cho topology cluster thực tế**.
- Mọi endpoint mà Driver nhận đều được DNS và route tới đúng server.
- Certificate phù hợp từng hostname/điểm TLS.
- Firewall/secret/role được giới hạn.
- Có kế hoạch failover, cutover, rollback và giám sát.

Không dùng ví dụ production cluster như một recipe “cứ đặt một LB trước ba node là xong”; chi tiết exposure phụ thuộc phiên bản Neo4j, edition và nền tảng triển khai.

## 20. Bài tập vận dụng

### Bài 1 — NAT đổi port

Neo4j lắng nghe tại `10.20.1.15:7687`. Proxy có listener `graph.example.com:17687` và forward tới cổng đó. Java app nằm ngoài mạng nội bộ.

**Câu hỏi:** URI và advertised address nào phù hợp cho một instance có routing/TLS được hỗ trợ?

**Đáp án:** Nếu proxy hỗ trợ Bolt/TLS và hostname hợp lệ, Java có thể dùng `neo4j+s://graph.example.com:17687`; advertised Bolt endpoint cũng cần là `graph.example.com:17687`. Listen vẫn là địa chỉ/cổng nội bộ. Cần kiểm tra các điều kiện routing thực tế, không chỉ đặt string giống nhau.

### Bài 2 — Container localhost

Java và Neo4j chạy trong hai container thuộc cùng Docker network. Java được cấu hình `bolt://localhost:7687`.

**Câu hỏi:** Vì sao lỗi và cần kiểm tra gì?

**Đáp án:** `localhost` trỏ tới container Java. Thử DNS/service name của Neo4j trong cùng network, kiểm tra listener/container port và advertised/routing phù hợp.

### Bài 3 — Có TCP nhưng không có Bolt

Proxy nhận kết nối cổng 7687 nhưng chỉ được cấu hình HTTP reverse proxy.

**Câu hỏi:** Điều gì cần thay?

**Đáp án:** Cấu hình TCP forwarding/stream cho Bolt hoặc gateway được hỗ trợ; không coi một HTTP path là Bolt endpoint.

### Bài 4 — Routing table sai mạng

Java từ Internet kết nối bootstrap thành công, nhưng Neo4j cluster trả `10.20.1.15:7687` và `10.20.1.16:7687`.

**Câu hỏi:** Nguyên nhân lỗi có thể là gì?

**Đáp án:** Driver cần kết nối tới các endpoint từ routing table nhưng client không có route tới IP private. Phải thiết kế advertised endpoint/exposure toàn bộ member theo topology được hỗ trợ.

### Bài 5 — TLS certificate mismatch

Ứng dụng dùng `neo4j+s://graph.example.com:7687`, certificate mà client nhận chỉ hợp lệ với `db.internal`.

**Câu hỏi:** Có nên chuyển sang `neo4j+ssc` trong production?

**Đáp án:** Không nên dùng như cách giải quyết lâu dài. Cần certificate được cấp đúng hostname/trust chain, hoặc chọn hostname có certificate hợp lệ và DNS/route đúng.

### Bài 6 — Browser và Java Driver

Neo4j Browser tải qua HTTP cổng 7474, nhưng Java Driver báo timeout trên 7687.

**Câu hỏi:** Browser tải được có chứng minh Neo4j Bolt sẵn sàng không?

**Đáp án:** Không. Hai connector khác nhau; cần kiểm tra Bolt listener, firewall, proxy và TLS riêng.

### Bài 7 — Kubernetes service không có endpoint

Trong cluster, Java Pod resolve được `neo4j-bolt.graph.svc.cluster.local` nhưng Service không có EndpointSlice phù hợp.

**Câu hỏi:** Chỉ sửa advertised address có giải quyết được không?

**Đáp án:** Thường không. Cần kiểm tra selector, label Pod, readiness và backend Service trước. Advertised address là một lớp khác.

### Bài 8 — DNS cutover và connection pool

Sau khi đổi DNS từ proxy cũ sang proxy mới, một số Java instance vẫn kết nối IP cũ.

**Câu hỏi:** Những yếu tố nào cần xem xét?

**Đáp án:** DNS TTL/cache, phiên kết nối Bolt đã được tạo trong pool, proxy endpoint cũ còn phục vụ hay không và kế hoạch thoát traffic. Chuyển DNS không bắt buộc đóng ngay mọi connection cũ.

### Bài 9 — Kiểm tra nhanh bị hiểu nhầm

`nc -vz graph.example.com 7687` thành công nhưng Cypher Shell không xác thực được.

**Câu hỏi:** Đã đủ chứng minh hệ thống hoạt động chưa?

**Đáp án:** Chưa. TCP chỉ cho biết cổng mở. Phải kiểm tra TLS, Bolt handshake, username/password, database và authorization.

### Bài 10 — Deploy một server thành cluster

Nhóm vận hành giữ nguyên cấu hình advertised một hostname chung từ deployment single-instance, sau đó mở rộng Neo4j thành nhiều member.

**Câu hỏi:** Có thể coi cấu hình cũ là đúng cho cluster không?

**Đáp án:** Không. Cần thiết kế lại topology, endpoint của từng server/gateway, routing table và đường truy cập của Java Driver theo phiên bản cluster.

## 21. Checklist nghiệm thu triển khai

### 21.1. Database và cấu hình

- [ ] Đã xác minh phiên bản Neo4j/Driver, topology đơn server hay cluster.
- [ ] Các connector được bật theo nhu cầu thực; không mở HTTP quản trị tùy tiện.
- [ ] Neo4j bind đúng listen address và port trong network namespace.
- [ ] Advertised Bolt hostname/port phù hợp tuyến mạng của client.
- [ ] Đã kiểm tra cấu hình đang có hiệu lực, không chỉ nội dung file.
- [ ] Đã chuẩn bị migration/backup nếu deployment có thay đổi dữ liệu.

### 21.2. Mạng và proxy

- [ ] DNS resolve đúng từ chính host/container/Pod Java.
- [ ] Firewall/security group/NetworkPolicy cho phép nguồn cần thiết và chặn nguồn khác.
- [ ] Proxy hỗ trợ TCP Bolt, có frontend/backend port mapping chính xác.
- [ ] Không nhầm host port, container port, Service port và targetPort.
- [ ] Nếu dùng TLS, certificate/trust/hostname đúng ở điểm termination.
- [ ] Health check và timeout proxy phù hợp kết nối Bolt.

### 21.3. Routing và cluster

- [ ] Bootstrap endpoint reachable.
- [ ] Mọi endpoint trong routing table mà driver có thể chọn đều reachable.
- [ ] Client ngoài VPC/Kubernetes không bị trả các tên private không thể resolve.
- [ ] Read/write routing và failover được kiểm tra trong môi trường phù hợp.
- [ ] Không nhầm cổng cluster nội bộ với Bolt client port.

### 21.4. Java/Spring và vận hành

- [ ] URI được cấu hình theo environment, không dùng localhost sai namespace.
- [ ] Secret không hard-code hoặc xuất hiện trong log.
- [ ] Driver được tái sử dụng, session/transaction có vòng đời hợp lý.
- [ ] `verifyConnectivity()` và `RETURN 1` thành công từ app runtime.
- [ ] Có test query nghiệp vụ đại diện với quyền đúng.
- [ ] Có giám sát TLS/routing/timeout/pool wait và SLO.
- [ ] Có kế hoạch cutover DNS/proxy, rollback, TTL và connection pool.
- [ ] Đã ghi nhận mọi giả định về mạng riêng, proxy và topology.

## 22. Ghi nhớ

**Triển khai Neo4j sau proxy, DNS hoặc mạng riêng** phải đồng thời bảo đảm **listener đúng, mạng reachable và advertised address đúng**. Địa chỉ lắng nghe dùng để Neo4j nhận kết nối; địa chỉ công bố là endpoint mà client có thể phải kết nối, đặc biệt quan trọng khi dùng **Neo4j Java Driver ở chế độ routing**. Trong Docker, Kubernetes hoặc NAT, hostname/port bên ngoài có thể khác địa chỉ/cổng bên trong tiến trình.

Khi debug, kiểm tra theo thứ tự **DNS → TCP → proxy/NAT → TLS → authentication → routing → Cypher**, từ chính môi trường ứng dụng. Với cluster, endpoint bootstrap hoạt động **không chứng minh** mọi server trả qua routing đều reachable. Kết hợp cấu hình đúng phiên bản, TLS/certificate hợp lệ, quyền tối thiểu, smoke test Java Driver, giám sát và kế hoạch rollback sẽ giúp ứng dụng Neo4j truy vấn và ghi graph ổn định sau khi triển khai.
