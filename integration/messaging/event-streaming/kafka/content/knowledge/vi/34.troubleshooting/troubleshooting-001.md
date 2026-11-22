# Không kết nối được do bootstrap, DNS hoặc advertised.listeners

Lỗi kết nối Kafka thường xuất hiện dưới dạng timeout, connection refused, UnknownHost hoặc producer/consumer liên tục reconnect. Ba nhóm nguyên nhân cần kiểm tra đầu tiên là cấu hình bootstrap của client, phân giải DNS trong môi trường chạy ứng dụng và địa chỉ broker được công bố qua `advertised.listeners`.

Một tình huống dễ gây nhầm lẫn là client kết nối được bootstrap broker nhưng vẫn không produce hoặc consume được. Kafka dùng kết nối ban đầu để lấy metadata cluster; sau đó client kết nối trực tiếp tới broker đang giữ partition leader hoặc coordinator. Nếu metadata chứa hostname/port không truy cập được từ phía client, bước bootstrap có thể thành công nhưng các request tiếp theo vẫn thất bại.

Bài học này xây dựng quy trình chẩn đoán từ đúng môi trường chạy client, đọc địa chỉ broker trong metadata, đối chiếu listener và sửa cấu hình theo topology bare metal, Docker hoặc Kubernetes.

## 1. Mục tiêu bài học

Sau bài học, người học có thể:

- Giải thích vai trò của `bootstrap.servers` và vì sao danh sách bootstrap không cần chứa mọi broker.
- Phân biệt `listeners` với `advertised.listeners`.
- Hiểu listener name, port và `listener.security.protocol.map`.
- Nhận biết lỗi DNS, TCP, TLS, SASL và lỗi metadata routing qua thông báo client.
- Kiểm tra hostname và port từ đúng máy, container hoặc pod đang chạy ứng dụng.
- Dùng `kcat -L` hoặc Kafka CLI để xem broker endpoints mà cluster trả về.
- Cấu hình listener nội bộ và listener bên ngoài cho Docker/Kubernetes.
- Lập runbook xử lý lỗi kết nối mà không mở rộng port hoặc thay đổi cấu hình tùy tiện.

## 2. Luồng kết nối Kafka

### 2.1. Bootstrap chỉ là điểm vào ban đầu

`bootstrap.servers` là danh sách host/port client dùng để mở kết nối ban đầu tới cluster. Client lấy metadata từ một broker có thể truy cập được, sau đó tự khám phá broker và partition leader.

Ví dụ:

~~~properties
bootstrap.servers=broker-1.example.net:9092,broker-2.example.net:9092
~~~

Danh sách này:

- Nên có nhiều hơn một endpoint để client vẫn có thể bootstrap khi một broker ngừng hoạt động.
- Không cần liệt kê toàn bộ broker.
- Phải chứa hostname/port mà chính môi trường chạy client có thể truy cập.
- Không phải danh sách thay thế cho địa chỉ broker trong metadata.

Nếu một endpoint bootstrap phân giải được nhưng broker down hoặc TCP không kết nối được, client có thể thử endpoint khác trong danh sách. Không dựa vào cơ chế này để bỏ qua hostname bootstrap sai: trong Kafka 4.4, bootstrap DNS mặc định được phân giải đồng bộ khi tạo client và lỗi phân giải có thể làm client construction thất bại. Nhưng nếu tất cả broker được metadata trả về đều không thể truy cập, việc thêm nhiều bootstrap endpoint không sửa được lỗi gốc.

### 2.2. Client dùng metadata để kết nối broker thật

~~~mermaid
sequenceDiagram
    participant App as Producer / Consumer
    participant B1 as Bootstrap broker
    participant B2 as Partition leader
    App->>B1: TCP + Kafka protocol
    B1-->>App: Metadata: broker IDs, hostnames, ports
    App->>B2: Kết nối endpoint của leader
    B2-->>App: Produce / Fetch response
~~~

Ví dụ:

1. Client kết nối `bootstrap.servers=localhost:9092` thành công.
2. Broker trả metadata cho ba broker: `kafka-1:9092`, `kafka-2:9092` và `kafka-3:9092`.
3. Client đang chạy trên laptop, không phân giải được tên `kafka-2`.
4. Khi partition leader nằm trên broker 2, producer/consumer timeout dù bootstrap broker 1 vẫn reachable.

Đó là lý do cần kiểm tra metadata sau khi bootstrap, không chỉ kiểm tra cổng bootstrap.

### 2.3. Ba lớp cần tách riêng

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Bootstrap | Client gọi địa chỉ nào đầu tiên? | `broker-1.example.net:9092` |
| Listener bind | Broker đang lắng nghe ở địa chỉ/interface nào? | `CLIENT://0.0.0.0:9092` |
| Advertised endpoint | Broker công bố địa chỉ nào để client kết nối? | `CLIENT://broker-1.example.net:9092` |

Ba giá trị có thể khác nhau. Phải bảo đảm đường đi từ client đến endpoint được quảng bá tồn tại, DNS phân giải đúng và port tương ứng đang được mở.

## 3. Phân biệt listeners và advertised.listeners

### 3.1. listeners: địa chỉ broker bind để nhận kết nối

`listeners` xác định các endpoint broker mở socket để nhận request. Cú pháp:

~~~text
LISTENER_NAME://hostname:port
~~~

Ví dụ:

~~~properties
listeners=CLIENT://0.0.0.0:9092
~~~

`0.0.0.0` có nghĩa bind trên tất cả network interface IPv4 của máy. Nó phù hợp khi broker cần nhận kết nối qua interface/container network khác nhau.

Nếu để hostname là `localhost`, broker chỉ bind loopback. Client ở máy khác hoặc container khác thường không thể truy cập socket đó.

Một số cấu hình hợp lệ:

~~~properties
listeners=PLAINTEXT://myhost:9092,SSL://:9093
~~~

~~~properties
listeners=CLIENT://0.0.0.0:9092,REPLICATION://10.10.0.5:9093
~~~

Tên listener là nhãn định danh. Nếu tên listener không trùng tên security protocol chuẩn, phải ánh xạ nó bằng `listener.security.protocol.map`.

### 3.2. advertised.listeners: địa chỉ broker công bố cho client

`advertised.listeners` xác định địa chỉ broker công bố cho client và broker khác. Trong môi trường cloud/NAT/container, địa chỉ bind có thể khác địa chỉ mà client cần dùng.

Ví dụ:

~~~properties
listeners=CLIENT://0.0.0.0:9092
advertised.listeners=CLIENT://broker-1.example.net:9092
~~~

Broker bind trên tất cả interface nhưng công bố hostname DNS mà client có thể truy cập.

Các nguyên tắc:

- Hostname phải phân giải được từ môi trường client.
- Port phải được route tới đúng broker.
- Không quảng bá `0.0.0.0`; đây là địa chỉ bind, không phải đích kết nối của client.
- Nếu `advertised.listeners` không được cấu hình, Kafka dùng giá trị từ `listeners`. Vì vậy, khi `listeners` bind bằng `0.0.0.0`, hãy khai báo `advertised.listeners` bằng hostname/IP cụ thể; không để địa chỉ wildcard trở thành endpoint client nhận được.
- Mỗi broker phải công bố endpoint đúng với listener mà client đã chọn.

Trong KRaft, địa chỉ advertised broker được controller quản lý và broker lấy lại khi cần. Vì vậy, cần kiểm tra trạng thái/cấu hình broker và metadata mà cluster thực sự trả về, không chỉ nhìn một biến môi trường ở container.

### 3.3. Listener name và security protocol

Ví dụ:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:29092
advertised.listeners=INTERNAL://kafka-1:9092,EXTERNAL://broker-1.example.net:29092
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:SASL_SSL
inter.broker.listener.name=INTERNAL
~~~

Ý nghĩa:

- `INTERNAL` là listener nội bộ dùng PLAINTEXT trong ví dụ.
- `EXTERNAL` là listener client bên ngoài dùng SASL_SSL.
- `inter.broker.listener.name` chọn listener cho traffic giữa broker.
- Client bên ngoài dùng endpoint `broker-1.example.net:29092` cùng cấu hình TLS/SASL tương ứng.

Tên listener phải khớp giữa `listeners`, `advertised.listeners` và `listener.security.protocol.map`.

Không cấu hình một listener tên `EXTERNAL` nhưng lại thiếu mapping protocol. Khi đó broker có thể không khởi động hoặc không nhận kết nối theo cấu hình mong muốn.

### 3.4. Listener broker, inter-broker và controller

Trong KRaft, các luồng giao tiếp có mục đích khác nhau:

- Client kết nối tới listener broker.
- Broker dùng `inter.broker.listener.name` cho giao tiếp broker-to-broker.
- Controller dùng `controller.listener.names` cho giao tiếp KRaft quorum.

Controller listener cần được cô lập khỏi mạng client thông thường. Client producer/consumer không dùng controller listener để gửi hoặc đọc record. Nếu client được cấu hình trỏ vào controller port, cần sửa endpoint sang broker listener phù hợp.

## 4. Nhận diện lỗi theo thông báo

Thông báo lỗi giúp khoanh vùng lớp bị lỗi. Một lỗi DNS khác với lỗi TCP refused; một lỗi TLS khác với lỗi SASL.

| Dấu hiệu | Lớp có khả năng lỗi | Hướng kiểm tra đầu tiên |
|---|---|---|
| `UnknownHostException`, `Name or service not known` | DNS | Hostname bootstrap hoặc hostname advertised |
| `ConfigException: No resolvable bootstrap urls` | Bootstrap/DNS | Cú pháp và DNS của `bootstrap.servers` |
| `Connection refused` | TCP/listener | Sai port, broker không listen hoặc port mapping |
| `Connection timed out` | Network path | Firewall, security group, route, NAT hoặc packet drop |
| `Node ... disconnected` sau bootstrap | Metadata endpoint/TCP | Host/port broker trong metadata |
| `SSLHandshakeException` | TLS | Trust chain, protocol, certificate |
| `No subject alternative DNS name matching` | TLS hostname | SAN certificate không khớp hostname advertised |
| `SaslAuthenticationException` | SASL | Mechanism, username/password, JAAS |
| `TopicAuthorizationException` | ACL | Quyền topic, không phải lỗi DNS/bootstrap |

Một số client chỉ hiển thị lỗi tổng hợp sau nhiều lần retry. Hãy tìm nguyên nhân đầu tiên trong log, hostname và port đang được thử kết nối.

## 5. Quy trình chẩn đoán từ client

### Bước 1: Xác định chính xác môi trường chạy client

Kiểm tra client chạy ở đâu:

- Máy developer.
- Máy ảo hoặc server application.
- Docker container.
- Kubernetes pod.
- Cloud VM hoặc mạng VPC.
- CI runner.

DNS và route phụ thuộc network namespace. `localhost` trong container là loopback của container; nó không tự trỏ tới host hoặc container Kafka khác.

Chạy mọi phép kiểm tra từ đúng môi trường đó. Kiểm tra thành công trên laptop không chứng minh pod production cũng truy cập được broker.

### Bước 2: Xác nhận bootstrap.servers

Đọc cấu hình thực tế của ứng dụng, ví dụ:

~~~properties
bootstrap.servers=broker-1.example.net:9092,broker-2.example.net:9092
~~~

Với Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - broker-1.example.net:9092
      - broker-2.example.net:9092
~~~

Kiểm tra:

- Hostname có đúng môi trường không?
- Có thiếu port không?
- Có vô tình dùng port nội bộ từ bên ngoài không?
- Có ký tự thừa, dấu cách hoặc dấu phẩy sai không?
- DNS có phân giải trong process/container không?
- Các endpoint có cùng listener/security protocol không?

Đưa ít nhất hai bootstrap endpoint độc lập vào cấu hình production nếu topology cho phép. Nhưng không thêm địa chỉ ngẫu nhiên hoặc controller endpoint chỉ để giảm lỗi.

### Bước 3: Kiểm tra DNS

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName broker-1.example.net
Resolve-DnsName broker-2.example.net
~~~

Trên Linux:

~~~bash
getent hosts broker-1.example.net
nslookup broker-1.example.net
dig +short broker-1.example.net
~~~

Kiểm tra mọi hostname trong `bootstrap.servers` và mọi hostname nhận được từ metadata.

Nếu DNS trả về nhiều IP, kiểm tra từng IP có cùng route và listener không. DNS có thể trả cả IPv4 và IPv6; một bản ghi AAAA sai hoặc chỉ có route IPv4 có thể khiến một số lần kết nối thất bại.

### Bước 4: Kiểm tra TCP tới port

Trên Windows:

~~~powershell
Test-NetConnection broker-1.example.net -Port 9092
Test-NetConnection broker-2.example.net -Port 9092
~~~

Tập trung vào `TcpTestSucceeded`.

Trên Linux:

~~~bash
nc -vz broker-1.example.net 9092
nc -vz broker-2.example.net 9092
~~~

Nếu DNS đúng nhưng TCP thất bại, kiểm tra:

- Broker có bind đúng interface không?
- Port container có được publish không?
- Firewall host có cho phép port không?
- Cloud security group/network ACL có cho phép cả chiều đi và chiều về không?
- Kubernetes Service/Endpoint có trỏ đúng pod và targetPort không?
- NAT hoặc load balancer có chuyển tới đúng broker không?

Ping thành công không chứng minh TCP port Kafka mở. Ngược lại, ping có thể bị chặn trong khi TCP vẫn hoạt động. Hãy kiểm tra đúng port.

### Bước 5: Lấy metadata và xem broker endpoints

Nếu có `kcat`:

~~~bash
kcat -b broker-1.example.net:9092 -L
~~~

Khi cần debug sâu hơn:

~~~bash
kcat -b broker-1.example.net:9092 -L -d broker,metadata
~~~

Output metadata sẽ liệt kê broker ID, hostname và port mà client nhận được. Ghi lại tất cả endpoint và kiểm tra DNS/TCP tới từng endpoint.

Nếu môi trường dùng SASL/TLS, truyền cấu hình xác thực phù hợp cho kcat; không kết luận lỗi advertised.listeners khi lệnh metadata bị dừng trước đó do authentication hoặc TLS.

Có thể dùng Kafka CLI:

~~~bash
bin/kafka-broker-api-versions.sh --bootstrap-server broker-1.example.net:9092
~~~

Hoặc:

~~~bash
bin/kafka-topics.sh --bootstrap-server broker-1.example.net:9092 --list
~~~

Các lệnh cần được cấp đúng client properties khi cluster bật SASL/SSL hoặc ACL.

### Bước 6: Kiểm tra từng advertised endpoint

Sau khi có metadata:

1. Lập danh sách broker ID, hostname và port.
2. Phân giải DNS từng hostname từ đúng client environment.
3. Kiểm tra TCP tới từng hostname/port.
4. Xác định listener/security protocol tương ứng.
5. Thử lại producer/consumer.

Không chỉ kiểm tra broker bootstrap. Partition leader hoặc group coordinator có thể nằm trên broker khác.

### Bước 7: Đối chiếu cấu hình broker

Kiểm tra cấu hình có hiệu lực của broker:

~~~properties
listeners=CLIENT://0.0.0.0:9092
advertised.listeners=CLIENT://broker-1.example.net:9092
listener.security.protocol.map=CLIENT:PLAINTEXT
~~~

Với mỗi broker, hostname/port advertised phải ánh xạ tới đúng broker ID và port đang được route. Nếu cấu hình nhiều listener, kiểm tra client đã kết nối vào đúng listener.

### Bước 8: Kiểm tra TLS/SASL sau khi TCP thông

Kết nối TCP thành công chỉ chứng minh socket reachable. Nó không chứng minh client và broker dùng cùng security protocol.

Nếu dùng TLS, kiểm tra certificate:

~~~bash
openssl s_client -connect broker-1.example.net:9093 -servername broker-1.example.net -showcerts
~~~

Xác nhận:

- Certificate chain được client trust.
- SAN có hostname client dùng để kết nối.
- Certificate còn hạn.
- Listener thực sự dùng SSL/SASL_SSL.
- Client truststore/keystore đúng file và đúng password.

Nếu dùng SASL, xác nhận mechanism và credential khớp listener. Lỗi authentication cần được xử lý sau khi đã xác nhận DNS/TCP/TLS cơ bản.

## 6. Chẩn đoán lỗi DNS

### 6.1. Hostname không tồn tại hoặc sai search domain

Ví dụ broker quảng bá:

~~~text
kafka-1:9092
~~~

Tên này có thể phân giải trong Docker network hoặc Kubernetes namespace nhưng không phân giải trên laptop.

Cách xử lý:

- Dùng DNS FQDN có thể truy cập từ client.
- Cấu hình split-horizon DNS nếu mạng nội bộ và bên ngoài dùng hostname/IP khác nhau.
- Kiểm tra search domain của pod/container.
- Không dùng tên service nội bộ cho client chạy ngoài cluster.
- Không dùng IP private cho client không có route tới VPC đó.

### 6.2. DNS trả IP sai hoặc cũ

Các nguyên nhân thường gặp:

- A record trỏ IP cũ sau khi thay broker.
- AAAA record tồn tại nhưng IPv6 route không hoạt động.
- DNS cache của JVM/OS còn giữ địa chỉ cũ.
- Split-horizon DNS trả kết quả khác nhau giữa host và container.
- DNS load balancing phân phối tới một endpoint không cùng cấu hình listener.

So sánh kết quả DNS từ host, container và pod. Nếu kết quả khác nhau, tìm nguyên nhân ở DNS view, namespace hoặc resolver trước khi thay cấu hình Kafka.

### 6.3. Nhiều IP và client.dns.lookup

Kafka client có cấu hình:

~~~properties
client.dns.lookup=use_all_dns_ips
~~~

Đây là giá trị mặc định trong Kafka 4.4. Client lần lượt thử các IP mà DNS trả về; sau khi dùng hết danh sách, client có thể phân giải lại hostname. Cơ chế này hữu ích khi một hostname có nhiều IP, nhưng không sửa được bản ghi DNS sai hoặc IP không thể route.

Tùy chọn khác:

~~~properties
client.dns.lookup=resolve_canonical_bootstrap_servers_only
~~~

Tùy chọn này phân giải bootstrap address thành danh sách canonical hostname trước bootstrap, rồi hoạt động như `use_all_dns_ips`.

Đừng đổi DNS lookup mode để che một hostname advertised sai. Hãy bảo đảm mọi IP và hostname được trả về đều hợp lệ trong mạng client.

### 6.4. bootstrap.resolve.timeout.ms trong Kafka 4.4

Kafka 4.4 có cấu hình:

~~~properties
bootstrap.resolve.timeout.ms=0
~~~

Giá trị mặc định 0 nghĩa là DNS được phân giải đồng bộ khi tạo client. Nếu phân giải thất bại, client nhận `ConfigException` và instance có thể không được tạo.

Đặt giá trị dương sẽ chuyển DNS resolution sang bất đồng bộ và cho phép retry trong khoảng thời gian đã đặt. Khi hết thời gian, client có thể nhận `BootstrapResolutionException` không thể phục hồi; cần đóng và tạo lại client sau khi sửa DNS hoặc `bootstrap.servers`.

Đây là tính năng đang evolving trong Kafka 4.4, có thể thay đổi tương thích ở minor release. Không xem nó là cách chữa DNS sai; chỉ dùng khi đã hiểu vòng đời client và chính sách retry.

## 7. Chẩn đoán advertised.listeners theo topology

### 7.1. Bare metal hoặc VM

Giả sử có ba broker trong cùng mạng nội bộ:

Broker 1 (`kafka-1`):

~~~properties
listeners=CLIENT://0.0.0.0:9092
advertised.listeners=CLIENT://kafka-1.internal.example:9092
listener.security.protocol.map=CLIENT:PLAINTEXT
inter.broker.listener.name=CLIENT
~~~

Broker 2 (`kafka-2`):

~~~properties
listeners=CLIENT://0.0.0.0:9092
advertised.listeners=CLIENT://kafka-2.internal.example:9092
listener.security.protocol.map=CLIENT:PLAINTEXT
inter.broker.listener.name=CLIENT
~~~

Broker 3 (`kafka-3`):

~~~properties
listeners=CLIENT://0.0.0.0:9092
advertised.listeners=CLIENT://kafka-3.internal.example:9092
listener.security.protocol.map=CLIENT:PLAINTEXT
inter.broker.listener.name=CLIENT
~~~

Mỗi broker bind port 9092 trên interface của nó. DNS của từng hostname trỏ tới IP tương ứng. Client có thể bootstrap qua một hoặc nhiều hostname trong danh sách.

Nếu client ở mạng khác, phải bảo đảm route/firewall cho cả ba broker. Mở port tới broker 1 nhưng không mở broker 2/3 sẽ tạo ra lỗi chỉ xảy ra với partition có leader trên các broker đó.

### 7.2. Docker: ứng dụng chạy cùng Docker network

Giả sử một broker có service name là `kafka`, ứng dụng và Kafka cùng ở một Docker network:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:29092
advertised.listeners=INTERNAL://kafka:9092,EXTERNAL://localhost:29092
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT
inter.broker.listener.name=INTERNAL
~~~

Port mapping ví dụ:

~~~yaml
ports:
  - "29092:29092"
~~~

Ứng dụng trong cùng Docker network dùng:

~~~properties
bootstrap.servers=kafka:9092
~~~

Ứng dụng chạy trực tiếp trên chính Docker host dùng:

~~~properties
bootstrap.servers=localhost:29092
~~~

Điểm quan trọng:

- `kafka` là DNS service name chỉ có ý nghĩa trong Docker network tương ứng.
- `localhost` từ bên trong application container trỏ về application container, không trỏ tới Kafka container.
- `localhost:29092` chỉ phù hợp với client chạy trên Docker host đó.
- Client ở máy khác phải dùng hostname/IP bên ngoài mà máy đó phân giải và route được; không quảng bá `localhost` cho client từ xa.

Đây là ví dụ một broker. Với nhiều broker, mỗi broker cần endpoint ngoài riêng có thể định tuyến đến đúng broker. Một bootstrap load balancer duy nhất không tự giải quyết việc client cần kết nối đến từng broker được metadata trả về.

### 7.3. Kubernetes

Trong Kubernetes, cần phân biệt:

- Bootstrap Service: điểm vào ban đầu.
- Headless Service hoặc DNS StatefulSet: địa chỉ ổn định cho từng broker.
- External Service/LoadBalancer/NodePort: đường vào từ ngoài cluster.
- Controller listener: luồng nội bộ của KRaft.

Một mô hình nội bộ thường dùng:

~~~text
kafka-0.kafka-headless.namespace.svc.cluster.local:9092
kafka-1.kafka-headless.namespace.svc.cluster.local:9092
kafka-2.kafka-headless.namespace.svc.cluster.local:9092
~~~

Ứng dụng cùng cluster có thể bootstrap qua Service phù hợp, nhưng metadata broker vẫn cần trả về DNS của từng broker có thể truy cập từ namespace ứng dụng.

Với client ngoài Kubernetes:

- Cấp endpoint ngoài riêng cho từng broker, hoặc cơ chế định tuyến broker-aware.
- Cấu hình advertised listener ngoài theo endpoint thực tế.
- Kiểm tra NodePort/LoadBalancer, firewall, ingress và DNS.
- Kiểm tra TLS SAN khớp hostname bên ngoài.
- Không quảng bá `*.svc.cluster.local` cho client Internet hoặc máy ngoài cluster.
- Không dùng controller service làm bootstrap broker cho producer/consumer.

Một Service chung có thể là bootstrap entry point, nhưng không thay thế các endpoint per-broker cần thiết sau khi client nhận metadata.

### 7.4. Cloud, NAT và load balancer

Trong môi trường cloud, broker có thể bind private interface nhưng client ngoài VPC cần public DNS/port. `advertised.listeners` phải công bố địa chỉ mà client có thể kết nối.

Kiểm tra:

- Private/public DNS view.
- NAT mapping và port forwarding.
- Security group và network ACL.
- Route table giữa subnet/VPC.
- Firewall trên VM.
- Health check của load balancer.
- Endpoint per-broker và broker identity trong metadata.

Không cấu hình tất cả broker quảng bá cùng một hostname/port load balancer trừ khi thiết kế proxy có thể định tuyến chính xác các kết nối Kafka tới đúng broker theo metadata. Kafka client cần liên hệ broker ID cụ thể, không chỉ một điểm cân bằng tải chung.

## 8. Phân biệt lỗi network với lỗi TLS/SASL

Sau khi hostname phân giải đúng và TCP port mở, client vẫn có thể không hoàn tất Kafka handshake.

### 8.1. Protocol map sai

Ví dụ broker dùng:

~~~properties
listeners=EXTERNAL://0.0.0.0:9093
listener.security.protocol.map=EXTERNAL:SASL_SSL
~~~

Client phải dùng SASL_SSL, truststore và SASL mechanism tương ứng. Nếu client dùng PLAINTEXT hoặc SSL mà không có SASL, handshake sẽ thất bại dù TCP connect thành công.

### 8.2. Certificate hostname không khớp

Nếu broker quảng bá `broker-1.example.net` nhưng certificate chỉ có SAN `kafka-1.internal`, client có thể báo hostname verification failure.

Cách xử lý:

- Phát hành certificate có SAN bao gồm hostname advertised.
- Hoặc thay advertised hostname thành hostname đã có trong certificate và vẫn route được từ client.
- Giữ hostname verification bật trong production.
- Không tắt kiểm tra hostname để che lỗi DNS/certificate.

### 8.3. SASL authentication

Khi log báo `SaslAuthenticationException`, kiểm tra:

- SASL mechanism của client và listener.
- Username/password hoặc token.
- JAAS config.
- Credential rotation.
- Listener prefix của broker configuration.
- Clock skew nếu cơ chế xác thực dựa trên token có thời hạn.

Authentication failure khác với `UnknownHostException` và `Connection refused`; không nên đổi DNS để xử lý lỗi credential.

## 9. Các công cụ hữu ích

| Công cụ | Mục đích | Kết quả cần xem |
|---|---|---|
| `Resolve-DnsName` | DNS trên Windows | A/AAAA, IP trả về |
| `getent hosts` | DNS từ Linux | IP trong resolver của máy |
| `dig` / `nslookup` | Tra cứu DNS | Bản ghi và resolver |
| `Test-NetConnection` | TCP trên Windows | `TcpTestSucceeded` |
| `nc -vz` | TCP trên Linux | Connect thành công/thất bại |
| `kcat -L` | Lấy Kafka metadata | Broker IDs, hostnames, ports |
| `kafka-broker-api-versions.sh` | Kiểm tra Kafka protocol endpoint | API versions và kết nối broker |
| `openssl s_client` | Kiểm tra TLS | Certificate chain, SAN, handshake |

### 9.1. Chạy trong Docker container

Ví dụ kiểm tra từ application container:

~~~bash
docker exec -it app-container sh
~~~

Sau đó chạy:

~~~bash
getent hosts kafka-1
nc -vz kafka-1 9092
kcat -b kafka-1:9092 -L
~~~

Nếu image không có `getent`, `nc` hoặc `kcat`, dùng một debug container trong cùng network namespace/network policy để kiểm tra. Không kết luận dựa trên kết quả chạy từ host khi ứng dụng thực tế nằm trong container.

### 9.2. Chạy trong Kubernetes pod

Ví dụ:

~~~bash
kubectl exec -it deploy/order-service -- sh
~~~

Trong pod, kiểm tra:

~~~bash
getent hosts kafka-0.kafka-headless.messaging.svc.cluster.local
nc -vz kafka-0.kafka-headless.messaging.svc.cluster.local 9092
~~~

Nếu DNS phân giải được nhưng TCP không thông, kiểm tra Service endpoints, NetworkPolicy, port mapping và listener bind. Nếu TCP thông nhưng Kafka client vẫn lỗi, lấy metadata bằng client/tool có cấu hình xác thực tương ứng.

## 10. Bảng quyết định nhanh

| Quan sát | Kết luận tạm thời | Việc tiếp theo |
|---|---|---|
| Không resolve bootstrap hostname | Lỗi bootstrap DNS | Sửa `bootstrap.servers` hoặc DNS |
| Bootstrap resolve được, TCP refused | Sai port/listener hoặc broker chưa listen | Kiểm tra `listeners`, process và port mapping |
| Bootstrap TCP được, `kcat -L` trả hostname nội bộ | Metadata advertised sai với client network | Sửa `advertised.listeners` |
| Metadata host resolve được, TCP timeout | Route/firewall/NAT | Mở đường tới từng broker advertised |
| TCP được, TLS handshake lỗi | Security protocol/certificate | Kiểm tra protocol map, trust chain, SAN |
| TLS được, SASL auth lỗi | Credential/mechanism | Kiểm tra SASL mechanism và JAAS |
| Chỉ một số partition hoặc broker lỗi | Endpoint per-broker không đồng nhất | So sánh metadata và connectivity từng broker |
| Chỉ app trong Docker lỗi | DNS/namespace/advertised listener | Kiểm tra từ container và listener nội bộ |
| Chỉ client ngoài Kubernetes lỗi | Endpoint external chưa đúng | Kiểm tra external advertised listener per broker |

## 11. Quy trình khắc phục có kiểm soát

Khi xử lý incident, nên đi theo thứ tự sau:

1. **Ghi nhận lỗi nguyên bản:** exception đầu tiên, hostname, port, client ID, thời điểm và môi trường chạy.
2. **Chụp cấu hình client:** `bootstrap.servers`, security protocol, SASL mechanism và TLS settings.
3. **Kiểm tra bootstrap DNS:** phân giải mọi hostname từ đúng container/pod/host.
4. **Kiểm tra bootstrap TCP:** thử từng host/port, ghi lại IP và kết quả.
5. **Lấy metadata:** dùng `kcat -L` hoặc Kafka CLI.
6. **Kiểm tra từng advertised endpoint:** DNS và TCP tới mọi broker trong metadata.
7. **Đối chiếu listener:** kiểm tra `listeners`, `advertised.listeners`, protocol map và inter-broker listener.
8. **Kiểm tra security:** chỉ sau khi network path đúng, xác minh TLS/SASL.
9. **Sửa đúng lớp:** sửa DNS, port route hoặc advertised address tại nguồn.
10. **Xác minh sau thay đổi:** tạo client mới, lấy metadata mới và thử produce/consume.
11. **Theo dõi toàn cluster:** kiểm tra tất cả broker và partition leader, không chỉ một node.
12. **Ghi lại runbook:** lưu endpoint đúng theo network zone và cách kiểm tra tái lập.

Khi thay đổi `advertised.listeners`, phải tính đến tất cả client đang dùng listener đó và cách broker được route từ từng network zone. Thực hiện thay đổi theo quy trình cấu hình của phiên bản Kafka và triển khai có kiểm soát; không thay đồng loạt hostname/port khi chưa xác minh metadata mới.

## 12. Lab: tái hiện và sửa lỗi advertised.listeners

### Mục tiêu

Tái hiện trường hợp bootstrap broker kết nối được nhưng metadata trả về địa chỉ broker không truy cập được, sau đó sửa listener và xác minh producer/consumer.

### Bước 1: Khởi động cluster lab

Dùng cluster một hoặc nhiều broker, ghi lại địa chỉ và port mà ứng dụng có thể truy cập. Nếu dùng Docker, bảo đảm ứng dụng và Kafka có network phù hợp.

### Bước 2: Cấu hình advertised hostname sai có chủ đích

Ví dụ broker bind được trên port 9092 nhưng quảng bá:

~~~properties
listeners=CLIENT://0.0.0.0:9092
advertised.listeners=CLIENT://kafka-internal-only:9092
listener.security.protocol.map=CLIENT:PLAINTEXT
~~~

Chạy client từ máy không thể resolve `kafka-internal-only`.

### Bước 3: Xác nhận bootstrap

Thử:

~~~bash
kcat -b localhost:9092 -L
~~~

Nếu bootstrap thành công, output vẫn có thể liệt kê `kafka-internal-only:9092`. Ghi nhận hostname đó.

### Bước 4: Kiểm tra DNS/TCP advertised endpoint

Trên Windows:

~~~powershell
Resolve-DnsName kafka-internal-only
Test-NetConnection kafka-internal-only -Port 9092
~~~

Hoặc Linux:

~~~bash
getent hosts kafka-internal-only
nc -vz kafka-internal-only 9092
~~~

Ghi lại lỗi DNS hoặc TCP.

### Bước 5: Sửa advertised.listeners

Cập nhật thành hostname mà client lab có thể truy cập:

~~~properties
listeners=CLIENT://0.0.0.0:9092
advertised.listeners=CLIENT://localhost:9092
listener.security.protocol.map=CLIENT:PLAINTEXT
~~~

Cấu hình này chỉ phù hợp nếu client và broker truy cập qua cùng host/loopback. Nếu client nằm trong container khác, dùng service DNS của Docker network; nếu client ở máy từ xa, dùng hostname/IP routable từ máy đó.

### Bước 6: Lấy lại metadata

Tạo kết nối client mới và chạy lại:

~~~bash
kcat -b localhost:9092 -L
~~~

Xác nhận broker endpoint trả về là hostname/port mong muốn.

### Bước 7: Produce và consume

Tạo topic lab, gửi và đọc một vài record:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic connectivity-lab --partitions 1 --replication-factor 1
~~~

~~~bash
bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic connectivity-lab
~~~

~~~bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic connectivity-lab --from-beginning
~~~

Nếu cluster dùng SASL/SSL, thêm client properties phù hợp cho từng lệnh.

### Bước 8: Ghi kết quả

Ghi lại:

- Bootstrap endpoint ban đầu.
- Broker endpoint trước và sau khi sửa.
- Kết quả DNS/TCP.
- Kết quả `kcat -L`.
- Kết quả produce/consume.
- Listener config cuối cùng và network zone áp dụng.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra bootstrap broker | Bỏ sót endpoint broker khác trong metadata | Kiểm tra toàn bộ broker được quảng bá |
| Dùng `localhost` trong Docker cho client container | Client kết nối nhầm loopback của chính container | Dùng service DNS trong cùng network |
| Quảng bá `0.0.0.0` | Client không có endpoint đích hợp lệ | Bind 0.0.0.0 nhưng advertise hostname/IP cụ thể |
| Quảng bá hostname nội bộ cho client bên ngoài | DNS/route không tồn tại ở phía client | Dùng listener ngoài và DNS routable |
| Chỉ mở port bootstrap | Client không kết nối được leader/coordinator trên broker khác | Mở đúng endpoint từng broker |
| Dùng một listener cho mọi network zone | Không phân biệt route nội bộ/bên ngoài | Thiết kế INTERNAL/EXTERNAL listener |
| Tất cả broker advertise cùng một endpoint | Client không tới đúng broker theo metadata | Cấp endpoint riêng hoặc proxy broker-aware |
| Kiểm tra DNS từ host nhưng app ở pod | Kết quả kiểm tra không đại diện môi trường app | Chạy test từ đúng network namespace |
| Đổi `client.dns.lookup` để né hostname sai | Vấn đề metadata/DNS vẫn còn | Sửa bản ghi DNS hoặc advertised endpoint |
| Tắt TLS hostname verification | Giảm bảo vệ kết nối và che certificate sai | Sửa SAN/certificate hoặc hostname |
| Dùng controller listener cho producer/consumer | Kết nối sai vai trò | Dùng broker client listener |
| Nhầm SASL error với network error | Sửa sai lớp cấu hình | Phân loại DNS, TCP, TLS, SASL riêng |
| Thêm nhiều bootstrap endpoint không kiểm tra | Vẫn lỗi nếu metadata endpoints không route | Kiểm tra metadata và từng broker |

## 14. Checklist production

- [ ] Ghi nhận client chạy trên host, container, pod hay VM nào.
- [ ] Kiểm tra `bootstrap.servers` có ít nhất hai endpoint phù hợp.
- [ ] Xác nhận mọi bootstrap hostname phân giải đúng.
- [ ] Kiểm tra TCP tới từng bootstrap port.
- [ ] Lấy metadata từ broker bằng `kcat -L` hoặc Kafka CLI.
- [ ] Kiểm tra DNS của tất cả broker endpoints trong metadata.
- [ ] Kiểm tra TCP tới tất cả advertised endpoints.
- [ ] Xác nhận `listeners` bind trên interface phù hợp.
- [ ] Xác nhận `advertised.listeners` công bố hostname/port routable.
- [ ] Không quảng bá `0.0.0.0` hoặc loopback cho client ngoài host.
- [ ] Xác nhận listener names và `listener.security.protocol.map` khớp.
- [ ] Phân biệt client, inter-broker và controller listeners.
- [ ] Xác nhận firewall, route, NAT, Service và NetworkPolicy.
- [ ] Xác nhận TLS certificate SAN khớp advertised hostname.
- [ ] Xác nhận SASL mechanism và credential.
- [ ] Kiểm tra từng broker, không chỉ bootstrap broker.
- [ ] Kiểm thử produce/consume từ đúng network zone.
- [ ] Lưu lại endpoint matrix theo từng môi trường.
- [ ] Theo dõi log reconnect, DNS và connection failure sau thay đổi.

## 15. Tài liệu tham khảo

- [Apache Kafka 4.4 – Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
- [Apache Kafka 4.4 – Consumer and Share Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 – Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 – Listener Configuration](https://kafka.apache.org/44/security/listener-configuration/)
- [Apache Kafka 4.4 – Security Model](https://kafka.apache.org/44/security/security-model/)

Khi chẩn đoán Kafka connection failure, hãy theo luồng bootstrap → metadata → broker endpoint. Bootstrap thành công chỉ chứng minh client đã chạm được một broker; producer/consumer chỉ hoạt động ổn định khi mọi broker endpoint mà metadata công bố đều phân giải được, route được và dùng đúng security protocol từ môi trường chạy client.
