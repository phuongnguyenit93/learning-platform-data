# Cấu hình controller listener và kết nối giữa các nút

Trong Kafka chạy ở chế độ KRaft, các nút phải trao đổi với nhau qua những listener có vai trò rõ ràng. Client kết nối vào broker để ghi và đọc record; broker kết nối với broker khác để replication; broker và controller trao đổi metadata qua controller listener; các controller duy trì metadata quorum với nhau.

Nếu cấu hình nhầm listener, cluster có thể khởi động nhưng client không truy cập được broker được quảng bá, broker không liên lạc được với controller, hoặc quorum không hình thành. Bài này giải thích các loại listener, cách cấu hình node KRaft, cách công bố địa chỉ đúng trong Docker và môi trường nhiều mạng, cùng quy trình kiểm tra kết nối.

## 1. Phân biệt các đường kết nối trong KRaft

Một cluster KRaft có hai nhóm vai trò chính:

- **Broker:** nhận yêu cầu produce/fetch từ client, lưu partition log và replication dữ liệu topic.
- **Controller:** quản lý metadata cluster, trạng thái broker, topic, partition và quá trình bầu chọn leader.

Một node có thể chạy vai trò broker, controller hoặc cả hai. Khi broker và controller được tách riêng, chúng vẫn cần kết nối mạng với nhau để broker nhận metadata và controller quản lý cluster.

Các listener thường được phân biệt như sau:

| Listener | Ai kết nối? | Dùng cho việc gì? | Có quảng bá cho client không? |
|---|---|---|---|
| Client listener | Ứng dụng producer/consumer, công cụ quản trị | Produce, fetch, metadata API và các API broker khác | Có, thông qua **advertised.listeners** |
| Inter-broker listener | Broker với broker | Replication partition và giao tiếp broker-to-broker | Có thể được quảng bá theo cấu hình broker |
| Controller listener | Broker với controller và controller với controller | Gửi yêu cầu metadata, quản lý controller quorum và điều phối cluster | Không quảng bá như listener client thông thường |

Một listener có thể dùng chung cho client và inter-broker nếu kiến trúc cho phép, nhưng tách riêng thường giúp kiểm soát mạng và bảo mật dễ hơn. Controller listener nên được giữ riêng để tránh client thông thường truy cập vào mặt phẳng điều khiển của cluster.

Sơ đồ kết nối:

~~~mermaid
flowchart TB
    P["Producer / Consumer"] -->|"Client listener"| B1["Broker 1"]
    P -->|"Client listener"| B2["Broker 2"]
    B1 <-->|"Inter-broker listener<br/>replication"| B2
    B1 <-->|"Controller listener"| C1["Controller 1"]
    B2 <-->|"Controller listener"| C2["Controller 2"]
    C1 <-->|"Controller quorum traffic"| C2
    C1 <-->|"Controller quorum traffic"| C3["Controller 3"]
    C2 <-->|"Controller quorum traffic"| C3
~~~

Trong mô hình kết hợp, cùng một tiến trình có thể vừa là broker vừa là controller. Khi đó node vẫn cần phân biệt listener nào nhận client traffic, listener nào nhận controller traffic và listener nào dùng cho inter-broker traffic.

## 2. Listener, advertised.listeners và địa chỉ kết nối

Kafka có hai khái niệm dễ nhầm:

- **listeners**: địa chỉ và cổng mà tiến trình broker bind để lắng nghe kết nối.
- **advertised.listeners**: địa chỉ mà broker trả về cho client trong metadata để client kết nối tiếp đến broker đó.

Ví dụ:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
advertised.listeners=INTERNAL://kafka-1:9092
~~~

**0.0.0.0** phù hợp làm địa chỉ bind để tiến trình nhận kết nối trên các interface. Nó không phải địa chỉ mà client nên dùng để kết nối. Địa chỉ quảng bá cần là hostname hoặc IP mà bên kết nối thực sự phân giải và truy cập được.

Khi client bootstrap vào một broker, broker trả metadata gồm địa chỉ của các broker. Client sau đó có thể mở kết nối trực tiếp đến leader của từng partition. Do đó, bootstrap có thể thành công nhưng thao tác produce/fetch vẫn thất bại nếu địa chỉ được quảng bá sai.

Ví dụ một cluster có ba broker trong Docker network:

| Broker | Listener nội bộ được quảng bá |
|---|---|
| kafka-1 | **kafka-1:9092** |
| kafka-2 | **kafka-2:9092** |
| kafka-3 | **kafka-3:9092** |

Các container trên cùng Docker network có thể phân giải service name của nhau. Một ứng dụng chạy trên host Windows không nhất thiết phân giải được **kafka-2**; nó cần listener external được quảng bá bằng địa chỉ host và port mapping tương ứng.

**Không đưa controller listener vào advertised.listeners cho client thông thường.** advertised.listeners công bố các endpoint broker mà client dùng. Controller listener được khai báo riêng bằng **controller.listener.names** và địa chỉ quorum tương ứng.

## 3. Các thuộc tính KRaft quan trọng

Một node KRaft thường cần các thuộc tính sau:

| Thuộc tính | Vai trò |
|---|---|
| **process.roles** | Chỉ định node là broker, controller hay cả hai |
| **node.id** | ID duy nhất của node trong cluster |
| **listeners** | Các listener mà tiến trình bind |
| **advertised.listeners** | Endpoint broker công bố cho client |
| **listener.security.protocol.map** | Ánh xạ tên listener sang PLAINTEXT, SSL, SASL_PLAINTEXT hoặc SASL_SSL |
| **controller.listener.names** | Tên listener dùng cho giao tiếp controller |
| **inter.broker.listener.name** | Listener broker dùng để giao tiếp với broker khác |
| **controller.quorum.voters** | Danh sách controller tĩnh trong static quorum |
| **controller.quorum.bootstrap.servers** | Điểm bootstrap controller trong dynamic quorum ở các phiên bản hỗ trợ |
| **log.dirs** | Thư mục lưu partition log và, nếu không đặt riêng, metadata log của KRaft |
| **metadata.log.dir** | Thư mục metadata log riêng nếu được cấu hình |

Tên listener là nhãn do người vận hành đặt, ví dụ **INTERNAL**, **EXTERNAL**, **CONTROLLER**. Tên đó phải được khai báo nhất quán trong các thuộc tính liên quan và trong **listener.security.protocol.map**.

Ví dụ:

~~~properties
listener.security.protocol.map=INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT,EXTERNAL:PLAINTEXT
~~~

Trong môi trường production, thường không nên dùng PLAINTEXT cho các đường kết nối qua mạng không tin cậy. Phần bảo mật ở mục 8 sẽ trình bày các điểm cần cấu hình.

## 4. Cấu hình static controller quorum cho cluster KRaft

Phần ví dụ này dùng **static quorum**, phù hợp với các phiên bản Kafka hỗ trợ cấu hình **controller.quorum.voters**. Cần đối chiếu tài liệu đúng phiên bản Kafka đang triển khai. Các phiên bản hỗ trợ dynamic quorum dùng cấu hình bootstrap khác, được giải thích ở mục 5; không cấu hình hai cơ chế quorum cùng lúc.

Giả sử có ba node KRaft kết hợp broker và controller:

| Node | node.id | Internal broker listener | Controller listener |
|---|---:|---|---|
| kafka-1 | 1 | **kafka-1:9092** | **kafka-1:9093** |
| kafka-2 | 2 | **kafka-2:9092** | **kafka-2:9093** |
| kafka-3 | 3 | **kafka-3:9092** | **kafka-3:9093** |

Ba node có cấu hình quorum chung:

~~~properties
process.roles=broker,controller
controller.listener.names=CONTROLLER
inter.broker.listener.name=INTERNAL

listener.security.protocol.map=INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT

controller.quorum.voters=1@kafka-1:9093,2@kafka-2:9093,3@kafka-3:9093
~~~

Mỗi node có **node.id** riêng và địa chỉ listener riêng. Ví dụ cấu hình cho kafka-1:

~~~properties
process.roles=broker,controller
node.id=1

listeners=INTERNAL://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
advertised.listeners=INTERNAL://kafka-1:9092

listener.security.protocol.map=INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER

controller.quorum.voters=1@kafka-1:9093,2@kafka-2:9093,3@kafka-3:9093

log.dirs=/var/lib/kafka/data
~~~

Trên kafka-2, thay **node.id=2** và **advertised.listeners=INTERNAL://kafka-2:9092**; trên kafka-3 dùng **node.id=3** và **INTERNAL://kafka-3:9092**. Danh sách **controller.quorum.voters** giống nhau trên các node và chứa đúng các controller member cùng node ID và địa chỉ controller listener của chúng.

Trong static quorum:

- Mỗi controller voter phải có node ID duy nhất.
- Node ID trong **controller.quorum.voters** phải khớp **node.id** của controller tương ứng.
- Hostname và port controller phải phân giải và truy cập được từ mọi thành viên quorum.
- Các node cần cùng nhận diện một cluster và được format storage theo cùng cluster ID.
- Không tự ý đổi node ID hoặc địa chỉ controller sau khi cluster đã có metadata mà không có kế hoạch di trú.

Với ba voter, quorum cần đa số, tức ít nhất hai controller còn hoạt động và liên lạc được. Nếu chỉ còn một controller, quorum không thể tiếp tục chấp nhận thay đổi metadata theo cơ chế bình thường.

## 5. Controller quorum tĩnh và dynamic quorum

Kafka có hai cách cấu hình thành viên controller quorum, tùy phiên bản và cách khởi tạo cluster:

| Cơ chế | Thuộc tính chính | Đặc điểm |
|---|---|---|
| Static quorum | **controller.quorum.voters** | Danh sách controller voter được khai báo tĩnh trong cấu hình |
| Dynamic quorum | **controller.quorum.bootstrap.servers** | Dùng các địa chỉ bootstrap để tìm quorum; membership được quản lý động theo cơ chế của phiên bản hỗ trợ |

Với dynamic quorum, ví dụ khai báo điểm bootstrap:

~~~properties
controller.quorum.bootstrap.servers=kafka-1:9093,kafka-2:9093,kafka-3:9093
controller.listener.names=CONTROLLER
~~~

Các node vẫn phải có **node.id**, controller listener và cấu hình bảo mật tương ứng. Danh sách bootstrap giúp node tìm controller quorum; nó không có nghĩa mọi địa chỉ trong danh sách đều là voter hiện tại. Thành viên quorum thực tế được quản lý theo quy trình dynamic quorum.

Không chuyển một cluster đang chạy từ static sang dynamic chỉ bằng cách thay tên thuộc tính. Quá trình khởi tạo storage, cluster ID, metadata quorum và membership phụ thuộc phiên bản Kafka và trạng thái cluster. Hãy theo hướng dẫn migration/upgrade chính thức của đúng phiên bản, có backup và kế hoạch phục hồi trước khi thực hiện.

Không cấu hình đồng thời **controller.quorum.voters** và **controller.quorum.bootstrap.servers** cho cùng một node. Chọn cơ chế mà phiên bản Kafka và cluster đã khởi tạo hỗ trợ.

## 6. Tách riêng broker và controller

Với cluster production lớn, có thể chạy các controller chuyên dụng và broker chuyên dụng. Tách vai trò giúp controller tập trung xử lý metadata, giảm cạnh tranh tài nguyên với lưu lượng produce/fetch. Nó cũng tăng số thành phần cần triển khai, giám sát và vận hành.

Ví dụ minh họa cho static quorum với ba controller và broker-only nodes.

**Controller-only node** (ví dụ controller-1):

~~~properties
process.roles=controller
node.id=101

listeners=CONTROLLER://0.0.0.0:9093
controller.listener.names=CONTROLLER
listener.security.protocol.map=CONTROLLER:PLAINTEXT

controller.quorum.voters=101@controller-1:9093,102@controller-2:9093,103@controller-3:9093

log.dirs=/var/lib/kafka/controller
~~~

**Broker-only node** (ví dụ broker-1):

~~~properties
process.roles=broker
node.id=1

listeners=INTERNAL://0.0.0.0:9092
advertised.listeners=INTERNAL://broker-1:9092

inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER

listener.security.protocol.map=INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
controller.quorum.voters=101@controller-1:9093,102@controller-2:9093,103@controller-3:9093

log.dirs=/var/lib/kafka/broker-data
~~~

Trong cấu hình broker-only, controller listener name vẫn xác định endpoint/protocol dùng để broker kết nối tới controller, nhưng broker-only node không cần bind controller listener như một controller member. Broker cần kết nối được tới các controller voter theo danh sách quorum. Controller-only node không cần client listener hay inter-broker listener để nhận traffic dữ liệu topic.

Trong kiến trúc tách vai trò:

- Controller nodes nên dùng số lượng lẻ, thường là 3 hoặc 5, để có đa số quorum.
- Broker nodes có node ID riêng, không trùng với controller nodes.
- Controller listener phải được bảo vệ và chỉ cho phép các node cần thiết truy cập.
- Inter-broker listener phải kết nối được giữa các broker để replication.
- Client listener chỉ nên mở cho các ứng dụng và công cụ được cấp quyền.

Không nên tách controller và broker chỉ vì muốn có nhiều container hơn trong lab. Với bài thực hành nhỏ, node kết hợp **broker,controller** thường dễ thiết lập; production cần quyết định theo tải, khả năng chịu lỗi và năng lực vận hành.

## 7. Kết nối giữa các node trong Docker Compose

Trong Docker Compose, các service trên cùng network có thể dùng service name làm hostname. Không nên dùng **localhost** để một container kết nối đến container khác, vì **localhost** bên trong container trỏ về chính container đó.

Ví dụ phần network và service rút gọn:

~~~yaml
services:
  kafka-1:
    hostname: kafka-1
    networks: [kafka-net]
    ports:
      - "29092:29092"

  kafka-2:
    hostname: kafka-2
    networks: [kafka-net]
    ports:
      - "39092:29092"

  kafka-3:
    hostname: kafka-3
    networks: [kafka-net]
    ports:
      - "49092:29092"

networks:
  kafka-net:
    driver: bridge
~~~

Đây chỉ là phần minh họa network và port mapping; mỗi service vẫn cần image, volume, environment, node ID, listener và quorum config phù hợp. Với client bên trong network, dùng các địa chỉ như **kafka-1:9092**, **kafka-2:9092**, **kafka-3:9092**.

Nếu client chạy trên host, mỗi broker cần một endpoint external riêng. Ví dụ:

| Broker | Port host | External endpoint được quảng bá |
|---|---:|---|
| kafka-1 | 29092 | **localhost:29092** |
| kafka-2 | 39092 | **localhost:39092** |
| kafka-3 | 49092 | **localhost:49092** |

Trên từng broker, khai báo listener external bind vào port trong container (ví dụ 29092) và quảng bá port host tương ứng. Ví dụ riêng cho kafka-1:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,EXTERNAL://0.0.0.0:29092
advertised.listeners=INTERNAL://kafka-1:9092,EXTERNAL://localhost:29092
listener.security.protocol.map=INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT,EXTERNAL:PLAINTEXT
inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER
~~~

Với kafka-2, endpoint external phải là **localhost:39092**; kafka-3 là **localhost:49092**. Các địa chỉ external được quảng bá phải khớp với port mapping và phải truy cập được từ nơi ứng dụng chạy.

Nếu ứng dụng chạy trên một máy khác, không dùng **localhost** trong advertised endpoint. Hãy dùng DNS hoặc IP có thể truy cập từ máy đó. Một cluster có nhiều nhóm client ở nhiều mạng có thể cần listener riêng cho từng vùng mạng và DNS phù hợp.

## 8. Bảo mật kết nối listener

Trong lab cục bộ, PLAINTEXT có thể giúp người học tập trung vào luồng kết nối. Trong môi trường thật, cần xác định bảo mật riêng cho client, inter-broker và controller listener.

### 8.1. TLS

TLS mã hóa dữ liệu trên đường truyền và cho phép xác thực chứng thư của endpoint. Với mutual TLS, hai phía có thể xác thực chứng thư của nhau. Cần chuẩn bị truststore/keystore, CA, SAN trong certificate khớp hostname được dùng để kết nối và thời hạn chứng thư.

Nếu client kết nối **kafka-1.internal.example** nhưng certificate chỉ có SAN **localhost**, xác minh hostname có thể thất bại dù TCP port mở.

### 8.2. SASL

SASL xác thực client hoặc node bằng cơ chế được cấu hình, chẳng hạn SCRAM hoặc GSSAPI/Kerberos. Khi dùng SASL, cần khai báo đúng protocol map, cơ chế và credential cho từng loại listener.

Không đặt mật khẩu hoặc secret trực tiếp trong file cấu hình được commit vào Git. Dùng secret manager, Docker secrets hoặc cơ chế cấp phát bí mật phù hợp với môi trường.

### 8.3. Tách quyền theo listener

Có thể dùng cùng cơ chế TLS/SASL nhưng chính sách ACL và firewall khác nhau:

- Client listener: chỉ cho phép ứng dụng và công cụ cần truy cập.
- Inter-broker listener: chỉ cho phép broker nodes trao đổi dữ liệu và replication.
- Controller listener: chỉ cho phép broker/controller nodes cần giao tiếp quản trị quorum.

Controller listener không nên được mở công khai trên Internet. Ngoài xác thực, hãy giới hạn network path và quyền truy cập để giảm bề mặt tấn công.

## 9. Kiểm tra controller quorum và kết nối broker

Kiểm tra cần đi từ mạng đến giao thức Kafka. TCP port mở chỉ chứng minh có thể thiết lập kết nối ở tầng mạng; nó chưa chứng minh node ID, quorum hoặc metadata đã đúng.

### 9.1. Kiểm tra DNS và TCP

Từ một node hoặc container cần kết nối đến controller:

~~~bash
getent hosts kafka-1
nc -vz kafka-1 9093
nc -vz kafka-2 9093
nc -vz kafka-3 9093
~~~

Trên Windows host có thể dùng:

~~~powershell
Test-NetConnection localhost -Port 29092
Test-NetConnection localhost -Port 39092
Test-NetConnection localhost -Port 49092
~~~

Chạy kiểm tra từ đúng network namespace. Kiểm tra từ host không chứng minh rằng container broker cũng phân giải và truy cập được hostname đó.

### 9.2. Kiểm tra metadata và listener broker

Dùng công cụ Kafka client để yêu cầu metadata:

~~~bash
kafka-broker-api-versions.sh --bootstrap-server kafka-1:9092
~~~

Nếu có **kcat**, có thể xem broker metadata và địa chỉ được quảng bá:

~~~bash
kcat -b kafka-1:9092 -L
~~~

Kiểm tra output có đúng hostname, port, broker ID và partition leader mà client cần truy cập không. Nếu metadata trả về địa chỉ không thể phân giải từ client, sửa **advertised.listeners** và DNS/port mapping.

### 9.3. Kiểm tra metadata quorum

Với phiên bản Kafka hỗ trợ tùy chọn bootstrap controller, có thể xem trạng thái quorum bằng:

~~~bash
kafka-metadata-quorum.sh --bootstrap-controller kafka-1:9093 describe --status
~~~

Lệnh này cho biết trạng thái leader, epoch, high watermark và thông tin quorum theo phiên bản. Một số phiên bản hoặc công cụ đóng gói có cú pháp khác; kiểm tra **--help** của binary đang dùng.

Khi cần xem replication của metadata quorum, dùng lệnh **describe --replication** nếu phiên bản hỗ trợ:

~~~bash
kafka-metadata-quorum.sh --bootstrap-controller kafka-1:9093 describe --replication
~~~

### 9.4. Kiểm tra log của từng node

Tìm các dấu hiệu:

- Node không kết nối được tới controller listener.
- Không tìm thấy quorum leader hoặc quorum không đạt đa số.
- Node ID trùng hoặc không khớp cấu hình voter.
- Broker không đăng ký thành công với controller.
- Lỗi TLS handshake, SASL authentication hoặc hostname verification.
- Lỗi bind port hoặc hostname không phân giải được.
- Cluster ID hoặc metadata storage không tương thích.

Không chỉ kiểm tra log của một node. Một controller có thể ghi nhận lỗi kết nối từ broker, trong khi broker ghi lỗi không thể tìm controller; đối chiếu log và thời điểm giữa các node giúp tìm ra phía khởi phát lỗi.

## 10. Các lỗi cấu hình thường gặp

### 10.1. Bootstrap thành công nhưng client không fetch/produce được

Nguyên nhân phổ biến là **advertised.listeners** trả về hostname hoặc port mà client không truy cập được. Kiểm tra metadata bằng **kcat -L**, sau đó thử DNS và TCP đến từng broker endpoint được quảng bá.

### 10.2. Broker không kết nối được controller

Kiểm tra:

- **controller.listener.names** có khớp tên listener và protocol map không?
- Địa chỉ controller trong quorum config có đúng hostname và port không?
- Controller listener có bind trên interface phù hợp không?
- Firewall, Docker network và DNS có cho phép broker kết nối controller không?
- TLS/SASL có cùng trust, certificate và cơ chế xác thực không?

### 10.3. Controller quorum không có leader

Kiểm tra đa số voter có hoạt động và liên lạc được không. Với ba voter, cần ít nhất hai thành viên để hình thành quorum. Kiểm tra node ID, địa chỉ voter, storage metadata và log của tất cả controller. Không format lại storage chỉ để thử khởi động quorum; thao tác đó có thể làm mất metadata hiện tại.

### 10.4. Port đã mở nhưng Kafka vẫn báo lỗi

Một port TCP có thể mở nhưng listener dùng protocol hoặc TLS/SASL không tương thích. Kiểm tra **listener.security.protocol.map**, client security config, certificate, credential và đúng loại listener đang được sử dụng.

### 10.5. Container dùng localhost để gọi broker khác

Trong container, **localhost** trỏ về container hiện tại. Hãy dùng service DNS name trong cùng Docker network, ví dụ **kafka-2:9092**. Chỉ dùng **localhost** khi client và broker thực sự chạy trong cùng network namespace hoặc khi truy cập port đã publish trên host.

### 10.6. Controller listener xuất hiện trong advertised.listeners

Controller listener không phải endpoint client thông thường. Bỏ controller listener khỏi **advertised.listeners**; giữ nó trong **listeners** của controller và trong **controller.listener.names**. Broker-only node cần cấu hình đường kết nối đến controller nhưng không cần quảng bá controller endpoint cho producer/consumer.

### 10.7. Hai node dùng cùng node.id hoặc cùng storage directory

Mỗi node phải có node ID riêng. Không cho hai broker cùng ghi vào một thư mục log hoặc volume. Nếu dùng static quorum, voter ID phải khớp node ID của controller. Nếu cấu hình storage đã format, không tự ý đổi node ID hoặc tái sử dụng volume cho node khác.

## 11. Quy trình cấu hình và đưa node vào cluster

Có thể triển khai theo thứ tự sau:

1. **Chọn topology:** quyết định dùng node kết hợp broker/controller cho lab hay tách controller chuyên dụng cho môi trường lớn.
2. **Chọn quorum mode:** xác định static hay dynamic theo phiên bản Kafka và cách khởi tạo cluster.
3. **Phân bổ node ID:** mỗi node một ID duy nhất; ghi lại vai trò của từng node.
4. **Thiết kế địa chỉ:** chọn hostname, port, DNS và network path cho client, inter-broker và controller.
5. **Khai báo listener:** cấu hình **listeners**, **advertised.listeners**, **listener.security.protocol.map**, **inter.broker.listener.name** và **controller.listener.names**.
6. **Khai báo quorum:** dùng danh sách voter static hoặc bootstrap servers dynamic đúng với phiên bản, không trộn hai cách.
7. **Chuẩn bị storage:** mỗi node có thư mục dữ liệu riêng; format storage theo quy trình khởi tạo cluster và cluster ID tương ứng.
8. **Khởi động controller/quorum:** kiểm tra quorum có leader và đạt đa số trước khi tiếp tục.
9. **Khởi động broker:** kiểm tra broker đăng ký được với controller và metadata cluster ổn định.
10. **Kiểm tra client:** dùng listener đúng mạng, yêu cầu metadata và thử produce/fetch trên topic thử nghiệm.
11. **Bật bảo mật:** triển khai TLS/SASL, ACL và firewall theo từng listener trước khi đưa vào môi trường chia sẻ.
12. **Giám sát:** theo dõi quorum state, controller log, broker registration, request errors và tình trạng replication.

Lệnh format storage chỉ dùng trong bước khởi tạo hoặc quy trình phục hồi đã được lập kế hoạch. Không chạy lại lệnh format mỗi lần restart container hoặc broker.

## 12. Checklist trước khi đưa KRaft cluster vào sử dụng

- [ ] Đã xác định node nào là broker, controller hay kết hợp cả hai.
- [ ] Mỗi node có **node.id** duy nhất và ổn định.
- [ ] Controller listener có tên và port thống nhất.
- [ ] Controller quorum addresses phân giải và truy cập được từ các thành viên cần thiết.
- [ ] Quorum mode phù hợp phiên bản Kafka; không cấu hình lẫn static và dynamic.
- [ ] **inter.broker.listener.name** trỏ đến listener broker-to-broker hợp lệ.
- [ ] **advertised.listeners** chỉ công bố endpoint broker mà client truy cập được.
- [ ] Controller listener không bị quảng bá như endpoint client thông thường.
- [ ] Hostname và port mapping đúng cho Docker network, host và client bên ngoài.
- [ ] TLS/SASL và ACL được cấu hình phù hợp với từng listener.
- [ ] Storage của từng node riêng biệt và đã được khởi tạo theo đúng cluster ID.
- [ ] Quorum đạt đa số và có leader ổn định.
- [ ] Broker đăng ký thành công và client lấy metadata được.
- [ ] Đã thử produce/fetch qua đúng listener của từng nhóm client.
- [ ] Đã kiểm tra log, DNS, TCP, TLS và quorum state.

KRaft tách mặt phẳng điều khiển metadata khỏi mặt phẳng dữ liệu của broker. Cấu hình listener đúng giúp controller, broker và client giao tiếp qua đúng đường, đúng địa chỉ và đúng chính sách bảo mật. Khi có sự cố, hãy kiểm tra metadata quảng bá, DNS/port, vai trò node, quorum membership và protocol của từng listener theo từng chặng; đừng chỉ dựa vào việc một cổng TCP đang mở.
