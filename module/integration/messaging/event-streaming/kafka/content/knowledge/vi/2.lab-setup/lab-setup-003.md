# Khởi tạo cụm KRaft một nút bằng Docker Compose

Apache Kafka có thể chạy ở chế độ KRaft, trong đó metadata của cụm được quản lý bằng một quorum controller tích hợp trong Kafka. Với môi trường học tập, một container có thể đồng thời đảm nhiệm vai trò broker và controller. Docker Compose giúp khai báo cấu hình, cổng mạng và vùng lưu trữ trong một file để có thể khởi động, dừng và dựng lại môi trường nhất quán.

Bài thực hành này dựng một cụm Kafka KRaft một nút bằng image chính thức `apache/kafka`. Sau khi hoàn thành, người học có thể kết nối từ máy host hoặc từ container khác trong cùng mạng Docker, tạo topic, gửi và đọc record, kiểm tra trạng thái quorum và xác minh dữ liệu còn tồn tại sau khi container được tạo lại.

## 1. Mục tiêu và giới hạn của lab

Mô hình sử dụng một tiến trình Kafka duy nhất với hai vai trò:

- **Broker:** nhận record từ producer, lưu partition và phục vụ consumer.
- **Controller:** quản lý metadata như topic, partition, trạng thái broker và phân công replica thông qua KRaft metadata quorum.

~~~mermaid
flowchart TB
    subgraph Docker["Docker Compose network"]
        C["Kafka container: broker + controller"]
        D[("Named volume: kafka-data")]
        A["Container client"]
        A -->|"broker:19092"| C
        C <-->|"KRaft metadata"| C
        C <--> D
    end
    H["Ứng dụng trên máy host"] -->|"localhost:9092"| C
~~~

Đây là chế độ **combined mode**: cùng một node có cả `broker` và `controller` trong `process.roles`. Nó phù hợp cho học tập, phát triển cục bộ, thử nghiệm cấu hình và chạy test tích hợp.

Một node không tạo ra khả năng chịu lỗi thực sự:

- Khi container hoặc máy Docker dừng, broker và controller đều ngừng hoạt động.
- Metadata quorum chỉ có một voter nên không thể duy trì quorum khi node đó mất.
- Topic trong lab nên dùng replication factor bằng 1; không có replica dự phòng trên broker khác.
- Việc đặt các replication factor nội bộ bằng 1 chỉ làm cấu hình tương thích với một node, không biến cụm thành môi trường có độ bền cao.

Không dùng mô hình này làm cụm production. Cụm production cần nhiều broker, controller quorum có số voter phù hợp, phân bố broker theo rack hoặc availability zone, bảo mật kết nối, giám sát và quy trình sao lưu/phục hồi.

## 2. Chuẩn bị môi trường

Cần có:

- Docker Engine hoặc Docker Desktop đang chạy.
- Docker Compose V2, sử dụng lệnh `docker compose`.
- Docker phiên bản 20.10.4 trở lên để tránh một số vấn đề quyền ghi thư mục cấu hình trong image Kafka.
- Cổng TCP 9092 còn trống trên máy host.
- Kết nối Internet trong lần đầu để tải image `apache/kafka:4.4.0`.

Không cần cài Java trên máy host khi toàn bộ Kafka server và các lệnh CLI đều chạy bên trong container. Image JVM chính thức đã đóng gói runtime cần thiết.

Kiểm tra Docker và Compose:

~~~powershell
docker version
docker compose version
docker info
~~~

Nếu Docker Desktop chưa khởi động, hãy mở Docker Desktop và chờ Docker Engine sẵn sàng trước khi chạy các lệnh tiếp theo.

## 3. Tạo thư mục lab

Tạo một thư mục riêng để lưu file Compose:

~~~powershell
mkdir kafka-kraft-lab
cd kafka-kraft-lab
~~~

Tạo file có tên `compose.yaml` trong thư mục này. File sẽ chứa một service Kafka và một named volume để giữ dữ liệu log.

## 4. Khai báo Kafka KRaft trong Docker Compose

Nội dung đầy đủ của `compose.yaml`:

~~~yaml
services:
  broker:
    image: apache/kafka:4.4.0
    hostname: broker
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: "1"
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT"
      KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT_HOST://localhost:9092,PLAINTEXT://broker:19092"
      KAFKA_PROCESS_ROLES: "broker,controller"
      KAFKA_CONTROLLER_QUORUM_VOTERS: "1@broker:29093"
      KAFKA_LISTENERS: "CONTROLLER://:29093,PLAINTEXT_HOST://:9092,PLAINTEXT://:19092"
      KAFKA_INTER_BROKER_LISTENER_NAME: "PLAINTEXT"
      KAFKA_CONTROLLER_LISTENER_NAMES: "CONTROLLER"
      CLUSTER_ID: "4L6g3nShT-eMCtK--X86sw"
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: "1"
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: "0"
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: "1"
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: "1"
      KAFKA_SHARE_COORDINATOR_STATE_TOPIC_REPLICATION_FACTOR: "1"
      KAFKA_SHARE_COORDINATOR_STATE_TOPIC_MIN_ISR: "1"
      KAFKA_LOG_DIRS: "/tmp/kraft-combined-logs"
    volumes:
      - kafka-data:/tmp/kraft-combined-logs
    restart: unless-stopped

volumes:
  kafka-data:
~~~

Cấu hình trên dùng image JVM chính thức của Apache Kafka phiên bản 4.4.0. Tag phiên bản được cố định để các lần dựng lab không tự thay đổi theo tag `latest`. Khi chuyển sang phiên bản khác, hãy kiểm tra lại các thuộc tính cấu hình và ví dụ Docker tương ứng.

### 4.1 Giải thích vai trò KRaft

| Thuộc tính | Giá trị trong lab | Ý nghĩa |
|---|---|---|
| `KAFKA_NODE_ID` | `1` | ID duy nhất của node trong cụm |
| `KAFKA_PROCESS_ROLES` | `broker,controller` | Node chạy đồng thời broker và controller |
| `KAFKA_CONTROLLER_QUORUM_VOTERS` | `1@broker:29093` | Khai báo voter controller: node 1 tại hostname broker, cổng 29093 |
| `KAFKA_CONTROLLER_LISTENER_NAMES` | `CONTROLLER` | Tên listener dành cho giao tiếp controller |
| `CLUSTER_ID` | Giá trị UUID cố định | Định danh cụm KRaft được lưu cùng metadata |
| `KAFKA_LOG_DIRS` | `/tmp/kraft-combined-logs` | Nơi lưu partition log và metadata log mặc định khi không cấu hình thư mục metadata riêng |

`broker` và `controller` là hai vai trò logic của cùng một tiến trình. Cấu hình `process.roles` không tạo hai container độc lập. Đây là lựa chọn đơn giản cho lab; trong một cụm lớn có thể tách controller và broker thành các node riêng.

### 4.2 Vì sao cần ba listener?

Kafka dùng địa chỉ được quảng bá cho client sau khi client kết nối bootstrap. Vì vậy, địa chỉ trong `advertised.listeners` phải truy cập được từ chính môi trường chạy client.

File Compose khai báo ba listener:

| Listener | Địa chỉ lắng nghe | Địa chỉ quảng bá | Mục đích |
|---|---|---|---|
| `CONTROLLER` | Cổng 29093 trong container | Không quảng bá cho client | Giao tiếp controller và metadata quorum |
| `PLAINTEXT` | Cổng 19092 trong container | `broker:19092` | Giao tiếp broker và client nằm trong Docker network |
| `PLAINTEXT_HOST` | Cổng 9092 trong container | `localhost:9092` | Client chạy trên máy host |

`KAFKA_LISTENERS` quy định Kafka bind vào địa chỉ và cổng nào bên trong container. `KAFKA_ADVERTISED_LISTENERS` quy định địa chỉ Kafka trả về cho client để tiếp tục kết nối. Hai cấu hình có liên quan nhưng không thể thay thế cho nhau.

Ví dụ:

- Ứng dụng Java chạy trực tiếp trên máy host dùng `localhost:9092`.
- Ứng dụng chạy trong một container khác cùng Compose network dùng `broker:19092`.
- Client trong container không nên dùng `localhost:9092` để tìm broker: `localhost` lúc đó trỏ về chính container client.
- Ứng dụng trên host không thể phân giải hostname nội bộ `broker`, nên không dùng `broker:19092`.

Listener `CONTROLLER` không được publish ra máy host. Client producer và consumer thông thường không kết nối vào listener này.

### 4.3 Vì sao các replication factor nội bộ bằng 1?

Một số topic nội bộ được Kafka sử dụng để lưu offset consumer group, trạng thái giao dịch và trạng thái share coordinator. Giá trị mặc định của các topic này có thể lớn hơn số broker trong lab một nút.

Vì vậy, Compose đặt:

- `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1`.
- `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1`.
- `KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1`.
- `KAFKA_SHARE_COORDINATOR_STATE_TOPIC_REPLICATION_FACTOR=1`.
- `KAFKA_SHARE_COORDINATOR_STATE_TOPIC_MIN_ISR=1`.

Các giá trị này giúp Kafka tạo topic nội bộ tương thích với một broker. Chúng không phải cấu hình khuyến nghị cho production. Khi tăng số broker, cần thiết kế lại replication factor và min ISR theo mục tiêu chịu lỗi.

### 4.4 Cluster ID và vùng lưu trữ

`CLUSTER_ID` là định danh của cụm Kafka. Image chính thức có giá trị mặc định cho lab, nhưng Compose khai báo rõ một giá trị để cấu hình dễ đọc và có thể tái lập. Trong một cụm thật, tất cả node thuộc cùng cụm phải dùng cùng cluster ID.

Volume `kafka-data` được mount vào `/tmp/kraft-combined-logs`. Nó giữ dữ liệu log và metadata qua các lần container bị dừng hoặc tạo lại. Nếu bỏ named volume, dữ liệu có thể mất khi container bị xóa.

Không thay cluster ID trong khi vẫn giữ volume chứa metadata của cụm cũ. Metadata trên đĩa lưu thông tin cluster ID; nếu ID cấu hình và metadata hiện có không khớp, Kafka có thể từ chối khởi động.

## 5. Kiểm tra và khởi động cụm

Trước khi chạy, xác minh Compose có thể phân tích file:

~~~powershell
docker compose config --quiet
~~~

Nếu lệnh không báo lỗi, khởi động Kafka ở chế độ nền:

~~~powershell
docker compose up -d
~~~

Kiểm tra trạng thái container:

~~~powershell
docker compose ps
~~~

Xem log khởi động:

~~~powershell
docker compose logs -f broker
~~~

Khi log cho thấy Kafka đã khởi động và không còn lỗi cấu hình, nhấn `Ctrl+C` để thoát chế độ theo dõi log. Lệnh này chỉ ngừng hiển thị log; container vẫn tiếp tục chạy ở chế độ nền.

Nếu container thoát hoặc liên tục restart, xem log đầy đủ bằng `docker compose logs broker` trước khi thử sửa cấu hình.

### 5.1 Kiểm tra kết nối broker và metadata quorum

Chạy lệnh kiểm tra API broker bên trong container:

~~~powershell
docker compose exec broker /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092
~~~

Lệnh trả về thông tin API của broker nếu kết nối thành công.

Kiểm tra trạng thái KRaft metadata quorum:

~~~powershell
docker compose exec broker /opt/kafka/bin/kafka-metadata-quorum.sh --bootstrap-server localhost:9092 describe --status
~~~

Với lab một nút, kết quả cần cho thấy một voter và leader controller tương ứng node ID 1. Nếu quorum chưa sẵn sàng, kiểm tra log broker và cấu hình controller listener, voter endpoint cùng cluster ID.

## 6. Tạo topic và trao đổi record

Tạo topic `orders` với ba partition và replication factor 1:

~~~powershell
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic orders --partitions 3 --replication-factor 1
~~~

Kiểm tra topic:

~~~powershell
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Kết quả cần hiển thị ba partition. Mỗi partition có một replica và ISR gồm đúng broker duy nhất đang chạy. Trong lab một nút, replication factor 1 là phù hợp với số broker hiện có.

### 6.1 Gửi record bằng console producer

Mở một terminal và chạy:

~~~powershell
docker compose exec -it broker /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic orders
~~~

Nhập một số record, mỗi dòng là một record:

~~~text
order-1001,CREATED
order-1002,PAID
order-1003,SHIPPED
~~~

Nhấn `Ctrl+C` để kết thúc producer.

### 6.2 Đọc record bằng console consumer

Mở terminal khác:

~~~powershell
docker compose exec -it broker /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders --from-beginning --group orders-lab
~~~

Consumer sẽ đọc các record đã gửi. Tham số `--from-beginning` cho phép đọc từ đầu log khi group chưa có offset đã commit phù hợp. Tham số `--group` đặt tên consumer group để có thể quan sát offset.

Nhấn `Ctrl+C` để dừng consumer. Kiểm tra tiến độ group:

~~~powershell
docker compose exec broker /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orders-lab
~~~

Kết quả hiển thị partition, current offset, log end offset và lag của consumer group. Nếu consumer đã đọc hết record và commit offset, lag thường trở về 0.

### 6.3 Kết nối từ ứng dụng ngoài container

Với ứng dụng Java hoặc Spring Boot chạy trực tiếp trên máy host, cấu hình bootstrap server:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

Nếu ứng dụng cũng chạy trong Docker Compose network, cấu hình:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker:19092
~~~

Không dùng một địa chỉ bootstrap chung cho cả hai môi trường nếu listener được quảng bá khác nhau. Kafka client lấy metadata từ broker rồi kết nối đến địa chỉ được quảng bá; do đó, bootstrap ban đầu thành công nhưng listener quảng bá sai vẫn có thể khiến producer hoặc consumer thất bại ở bước tiếp theo.

## 7. Xác minh volume giữ dữ liệu

Để kiểm tra named volume hoạt động:

1. Gửi một record có nội dung dễ nhận diện, ví dụ `persistence-check-001`.
2. Dừng và xóa container bằng `docker compose down`.
3. Khởi động lại bằng `docker compose up -d`.
4. Đọc lại topic từ đầu bằng console consumer.
5. Xác minh record `persistence-check-001` vẫn xuất hiện.

Các lệnh:

~~~powershell
docker compose down
docker compose up -d
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
docker compose exec -it broker /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders --from-beginning --group persistence-check
~~~

`docker compose down` xóa container và network của Compose nhưng giữ named volume. Khi container mới được tạo, Kafka đọc lại log và metadata từ volume đó.

Không dùng `docker compose down -v` trong bước kiểm tra persistence. Tùy chọn `-v` xóa cả named volume do Compose quản lý, đồng nghĩa xóa dữ liệu Kafka của lab.

## 8. Dừng, khởi động lại và dọn dẹp

Dừng container nhưng giữ container và volume:

~~~powershell
docker compose stop
~~~

Khởi động lại container đã dừng:

~~~powershell
docker compose start
~~~

Dừng và xóa container/network, vẫn giữ named volume:

~~~powershell
docker compose down
~~~

Xóa cả dữ liệu lab khi không còn cần:

~~~powershell
docker compose down -v
~~~

Hãy xem `down -v` là thao tác xóa dữ liệu. Chỉ chạy khi đã xác nhận không cần giữ topic, record, consumer offset và metadata hiện có.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Port 9092 đã được sử dụng | Một tiến trình hoặc container khác đang chiếm cổng | Dừng dịch vụ đang chiếm cổng hoặc đổi port host; nếu đổi port host, cập nhật cả địa chỉ `PLAINTEXT_HOST` trong `KAFKA_ADVERTISED_LISTENERS` |
| Container liên tục restart | Sai cấu hình listener, voter, cluster ID hoặc lỗi quyền ghi volume | Đọc `docker compose logs broker`; kiểm tra các thuộc tính KRaft và quyền trên Docker volume |
| Ứng dụng host không phân giải được `broker` | Ứng dụng host đang dùng hostname chỉ tồn tại trong Docker network | Dùng `localhost:9092` từ máy host |
| Ứng dụng container không kết nối được `localhost:9092` | `localhost` trỏ về container ứng dụng | Dùng `broker:19092` trong cùng Compose network |
| Bootstrap kết nối được nhưng gửi/đọc thất bại | Kafka trả về advertised listener không truy cập được từ môi trường client | Kiểm tra `KAFKA_ADVERTISED_LISTENERS` và chọn listener phù hợp |
| Lỗi replication factor lớn hơn số broker | Topic hoặc topic nội bộ yêu cầu nhiều replica hơn số broker hiện có | Với lab một nút, dùng replication factor 1 và đặt các topic nội bộ tương thích một node |
| Cluster ID không khớp metadata trên đĩa | Đổi `CLUSTER_ID` trong khi volume cũ vẫn được sử dụng | Khôi phục đúng cluster ID đã dùng với volume; chỉ xóa volume nếu dữ liệu lab có thể bỏ |
| Topic không xuất hiện sau khi dựng lại | Dữ liệu nằm trong filesystem container thay vì named volume, hoặc volume đã bị xóa | Kiểm tra mục `volumes` và lệnh dọn dẹp đã chạy |

Khi thay đổi cổng host từ 9092 sang 19092, ví dụ:

~~~yaml
ports:
  - "19092:9092"
environment:
  KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT_HOST://localhost:19092,PLAINTEXT://broker:19092"
~~~

Phần cổng bên phải của mapping vẫn là cổng container đang lắng nghe. Địa chỉ quảng bá dành cho client host phải đổi sang cổng host mới. Sau khi sửa Compose, áp dụng lại cấu hình:

~~~powershell
docker compose up -d
~~~

## 10. Mở rộng từ lab một nút

Khi đã hiểu cấu hình một node, có thể mở rộng sang cụm nhiều node bằng cách:

- Cấp `node.id` duy nhất cho mỗi broker/controller.
- Đưa các node vào cùng Docker network và dùng hostname có thể phân giải giữa container.
- Khai báo danh sách `controller.quorum.voters` chứa các controller voter của cụm.
- Cân nhắc tách vai trò controller và broker bằng `process.roles` phù hợp.
- Cấu hình listener riêng cho controller, inter-broker và client.
- Đặt replication factor cho topic và topic nội bộ theo số broker thực tế.
- Phân bố replica trên các broker và rack/availability zone khác nhau.
- Bổ sung health check, resource limit, bảo mật TLS/SASL, metric và log tập trung.

Trong cụm nhiều controller voter, quorum cần đa số voter hoạt động để tiến hành thay đổi metadata. Vì vậy, cụm ba controller có thể chịu lỗi một controller; một controller đơn lẻ thì không. Cấu hình nhiều broker cũng không tự tạo khả năng chịu lỗi nếu các replica cùng nằm trên một máy vật lý hoặc cùng phụ thuộc một vùng lỗi.

Không sao chép cấu hình một node rồi chỉ tăng `KAFKA_NODE_ID` để tạo cụm production. Phải thiết kế lại voter, listener, advertised listener, storage, replication factor, bảo mật và phân bố failure domain cho toàn cụm.

## 11. Checklist hoàn thành lab

- [ ] Docker Engine và Docker Compose V2 hoạt động.
- [ ] `compose.yaml` được Docker Compose phân tích thành công.
- [ ] Container Kafka khởi động ổn định.
- [ ] Broker API trả về thông tin khi kiểm tra bằng CLI.
- [ ] Metadata quorum hiển thị node 1 là voter và leader trong lab.
- [ ] Topic `orders` được tạo với ba partition và replication factor 1.
- [ ] Producer gửi được record và consumer đọc được record.
- [ ] Consumer group `orders-lab` có thể được mô tả bằng CLI.
- [ ] Record vẫn còn sau `docker compose down` rồi `docker compose up -d`.
- [ ] Người học phân biệt được địa chỉ kết nối từ host và từ container.
- [ ] Người học hiểu rằng một node không cung cấp khả năng chịu lỗi cho broker hoặc controller.

## Tài liệu tham khảo

- [Apache Kafka Quickstart](https://kafka.apache.org/quickstart/) — tải image chính thức và chạy Kafka KRaft.
- [Apache Kafka Docker documentation](https://kafka.apache.org/documentation/#docker) — cách cấu hình image Kafka bằng mặc định, file cấu hình và biến môi trường.
- [Apache Kafka single-node Docker Compose example](https://github.com/apache/kafka/blob/trunk/docker/examples/docker-compose-files/single-node/plaintext/docker-compose.yml) — ví dụ chính thức về listener, cluster ID và cấu hình replication cho một node.
- [Apache Kafka Docker examples guide](https://github.com/apache/kafka/blob/trunk/docker/examples/README.md) — giải thích ví dụ single-node và multi-node.

Các ví dụ trong bài hướng đến môi trường học tập với image Apache Kafka 4.4.0. Khi sử dụng phiên bản khác, hãy đối chiếu tài liệu Docker và Compose example của đúng phiên bản đó.
