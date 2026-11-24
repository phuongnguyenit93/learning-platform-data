# Chuẩn bị Kafka hoặc RabbitMQ cục bộ bằng Docker Compose

Để bắt đầu phát triển ứng dụng Spring Cloud Stream, nhóm cần một broker có thể khởi động nhanh, dễ quan sát và có dữ liệu độc lập với môi trường production. Docker Compose cho phép mô tả broker cùng cổng, thông tin đăng nhập, volume và health check trong một file. Sau khi khởi động, ứng dụng Spring chạy trên máy phát triển có thể kết nối qua cổng được ánh xạ; ứng dụng chạy trong container dùng tên service trên mạng Compose.

Bài này hướng dẫn chuẩn bị một node Kafka chạy KRaft hoặc một node RabbitMQ có giao diện quản trị. Chọn broker phù hợp với bài thực hành. Cấu hình một node đủ cho việc học binding, consumer group, queue, partition và kiểm thử luồng sự kiện; nó không mô phỏng đầy đủ tính sẵn sàng cao hay bảo mật của cụm production.

## 1. Chuẩn bị môi trường

Cài Docker Desktop hoặc Docker Engine có hỗ trợ Docker Compose v2. Trên Windows, Docker Desktop thường chạy với backend WSL 2. Mở terminal tại thư mục dự án hoặc thư mục thực hành và kiểm tra:

```bash
docker version
docker compose version
```

Hai lệnh cần trả về thông tin phiên bản hợp lệ. Nếu `docker version` chỉ hiển thị phần Client và báo không kết nối được daemon, hãy khởi động Docker Desktop hoặc Docker Engine trước khi tiếp tục.

Tạo một thư mục làm việc, ví dụ `local-broker`, rồi đặt file Compose tương ứng vào đó. Có thể lưu hai cấu hình dưới hai tên riêng để chuyển broker mà không phải sửa file mỗi lần:

- `compose.kafka.yaml` cho Kafka.
- `compose.rabbitmq.yaml` cho RabbitMQ.

Kiểm tra cấu trúc Compose trước khi khởi chạy bằng `docker compose -f compose.kafka.yaml config` hoặc `docker compose -f compose.rabbitmq.yaml config`. Lệnh `config` phân tích cú pháp và hiển thị cấu hình sau khi nội suy biến; nó chưa khởi tạo container.

## 2. Khởi chạy Kafka cục bộ

Kafka lưu thông điệp trong topic và chia topic thành các partition. Consumer group phối hợp việc phân công partition giữa các consumer cùng nhóm. Cấu hình dưới đây dùng một broker kiêm controller theo chế độ KRaft, không cần ZooKeeper. Hai listener tách kết nối từ máy phát triển và kết nối từ container khác trong cùng mạng Compose.

Tạo file `compose.kafka.yaml`:

```yaml
services:
  kafka:
    image: apache/kafka:4.0.0
    hostname: kafka
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: EXTERNAL://:9092,INTERNAL://:29092,CONTROLLER://:9093
      KAFKA_ADVERTISED_LISTENERS: EXTERNAL://localhost:9092,INTERNAL://kafka:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: EXTERNAL:PLAINTEXT,INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: INTERNAL
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_NUM_PARTITIONS: 3
      KAFKA_LOG_DIRS: /var/lib/kafka/data
    volumes:
      - kafka-data:/var/lib/kafka/data
    healthcheck:
      test: ["CMD-SHELL", "/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092 >/dev/null 2>&1"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

volumes:
  kafka-data:
```

Các thiết lập đáng chú ý:

- `KAFKA_PROCESS_ROLES` cho phép tiến trình đơn đảm nhiệm cả broker và controller. Đây là cấu hình gọn cho môi trường học tập.
- `EXTERNAL` quảng bá `localhost:9092` để ứng dụng chạy trực tiếp trên máy phát triển kết nối được.
- `INTERNAL` quảng bá `kafka:29092` để container khác dùng DNS service `kafka` trên mạng Compose.
- `CONTROLLER` dùng cổng 9093 cho giao tiếp điều khiển nội bộ; không cần ánh xạ cổng này ra máy host.
- Các replication factor bằng `1` phù hợp với một broker. Chúng không cung cấp khả năng chịu lỗi khi node dừng.
- Volume `kafka-data` giữ dữ liệu broker qua các lần dừng và tạo lại container. `KAFKA_LOG_DIRS` trỏ tới đúng thư mục được mount.
- Health check gọi Kafka broker API để xác nhận broker đã phản hồi, thay vì chỉ kiểm tra tiến trình container còn chạy.

> **Lưu ý về địa chỉ kết nối:** `localhost` trong `KAFKA_ADVERTISED_LISTENERS` dành cho client chạy trên máy host. Client chạy trong container phải dùng `kafka:29092`. Kafka trả địa chỉ broker đã quảng bá trong metadata; vì vậy, cấu hình sai advertised listener có thể khiến client kết nối bootstrap ban đầu được nhưng lỗi khi truy cập topic hoặc partition.

Khởi chạy và kiểm tra trạng thái:

```bash
docker compose -f compose.kafka.yaml config
docker compose -f compose.kafka.yaml up -d
docker compose -f compose.kafka.yaml ps
docker compose -f compose.kafka.yaml logs -f kafka
```

Đợi trạng thái health chuyển thành `healthy`. Nhấn `Ctrl+C` để thoát chế độ theo dõi log; container vẫn chạy nền. Có thể xem các topic hiện có bằng:

```bash
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

### 2.1. Tạo topic và thử gửi thông điệp

Tạo topic `orders` với ba partition và replication factor bằng một:

```bash
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic orders --partitions 3 --replication-factor 1
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
```

Mở terminal thứ nhất để chạy consumer đọc từ đầu topic:

```bash
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders --from-beginning
```

Mở terminal thứ hai để chạy producer:

```bash
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic orders
```

Nhập một dòng JSON, nhấn Enter và quan sát dòng đó xuất hiện ở terminal consumer:

```json
{"eventId":"evt-001","orderId":"ord-100","status":"CREATED"}
```

Nhấn `Ctrl+C` trong từng terminal để kết thúc lệnh tương tác. Lệnh `--describe` cho biết số partition và leader hiện tại; nó giúp xác nhận topic được tạo theo cấu hình mong muốn.

## 3. Khởi chạy RabbitMQ cục bộ

RabbitMQ thường được dùng theo mô hình exchange định tuyến thông điệp đến queue. Consumer nhận thông điệp từ queue và xác nhận xử lý bằng acknowledgement. Spring Cloud Stream Rabbit binder ánh xạ destination sang exchange và consumer group sang queue gắn với exchange đó.

Tạo file `compose.rabbitmq.yaml`:

```yaml
services:
  rabbitmq:
    image: rabbitmq:4.1-management
    hostname: rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: stream
      RABBITMQ_DEFAULT_PASS: stream-local
      RABBITMQ_DEFAULT_VHOST: /
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 15s

volumes:
  rabbitmq-data:
```

Hai cổng được ánh xạ có mục đích khác nhau:

- `5672` là cổng AMQP để ứng dụng Spring kết nối.
- `15672` là giao diện quản trị web do image `management` cung cấp.

Tài khoản `stream` và mật khẩu `stream-local` chỉ dùng cho ví dụ cục bộ. Tạo user riêng giúp tránh vướng giới hạn của tài khoản mặc định `guest`, vốn thường chỉ được phép kết nối từ loopback của chính RabbitMQ. Không dùng mật khẩu mẫu này trong môi trường chia sẻ hoặc production.

Các biến `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS` và `RABBITMQ_DEFAULT_VHOST` được dùng khi RabbitMQ khởi tạo cơ sở dữ liệu lần đầu. Nếu named volume đã có dữ liệu từ lần chạy trước, đổi các biến trong Compose không tự thay đổi tài khoản hiện có; cần cập nhật user trong RabbitMQ hoặc tạo lại volume khi có thể xóa dữ liệu.

Khởi chạy và kiểm tra:

```bash
docker compose -f compose.rabbitmq.yaml config
docker compose -f compose.rabbitmq.yaml up -d
docker compose -f compose.rabbitmq.yaml ps
docker compose -f compose.rabbitmq.yaml logs -f rabbitmq
```

Đợi trạng thái health chuyển thành `healthy`. Nhấn `Ctrl+C` để thoát chế độ theo dõi log; container vẫn chạy nền. Mở `http://localhost:15672` trên trình duyệt và đăng nhập bằng:

| Trường | Giá trị |
|---|---|
| Username | `stream` |
| Password | `stream-local` |

Giao diện quản trị cho phép xem connection, exchange, queue, số thông điệp sẵn sàng và số thông điệp chưa được xác nhận. Có thể kiểm tra queue từ terminal:

```bash
docker compose -f compose.rabbitmq.yaml exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged
```

Khi ứng dụng Spring Cloud Stream khởi tạo consumer binding, Rabbit binder có thể tự khai báo exchange, queue và binding cần thiết nếu user có đủ quyền. Sau đó, tên queue và trạng thái thông điệp sẽ xuất hiện trong giao diện quản trị hoặc kết quả `list_queues`.

## 4. Kết nối ứng dụng Spring Cloud Stream

Ứng dụng cần starter của binder tương ứng. Dùng Spring Cloud BOM phù hợp với phiên bản Spring Boot của dự án để quản lý phiên bản Spring Cloud Stream và binder; không tự chọn các phiên bản thư viện rời rạc.

Với Gradle, chọn một dependency:

```kotlin
// Dùng khi kết nối Kafka
implementation("org.springframework.cloud:spring-cloud-starter-stream-kafka")

// Hoặc dùng khi kết nối RabbitMQ
implementation("org.springframework.cloud:spring-cloud-starter-stream-rabbit")
```

Không cần khai báo cả hai starter nếu ứng dụng chỉ thực hành với một broker. Nếu ứng dụng cần kiểm thử nhiều binder trong cùng một bài thực hành, hãy quản lý dependency và cấu hình rõ ràng để tránh khởi tạo nhầm binder.

Ví dụ consumer nhận sự kiện tạo đơn hàng:

```java
@Bean
public Consumer<OrderCreated> processOrder(InventoryService inventory) {
    return event -> inventory.reserve(event.orderId(), event.items());
}
```

Khai báo phần cấu hình chung trong `application.yml`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: inventory
```

Tên `processOrder-in-0` là binding đầu vào thứ nhất của bean hàm `processOrder`. `destination` là topic hoặc exchange logic có tên `orders`. `group` định danh nhóm xử lý. Với Kafka, các instance dùng cùng group sẽ chia nhau partition được gán; với Rabbit binder, group được dùng để tạo queue dành cho nhóm consumer đó. Một group khác có thể nhận bản sao sự kiện qua queue riêng trong RabbitMQ hoặc consumer group riêng trong Kafka.

### 4.1. Kết nối Kafka

Khi ứng dụng chạy trực tiếp từ IDE hoặc terminal trên máy phát triển, cấu hình binder dùng listener ngoài:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
```

Khi ứng dụng chạy trong một container cùng mạng Compose với Kafka, đổi địa chỉ thành:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: kafka:29092
```

Không dùng `localhost:9092` bên trong container ứng dụng: `localhost` khi đó trỏ về chính container ứng dụng. Hãy dùng tên service `kafka` và listener nội bộ `29092`.

### 4.2. Kết nối RabbitMQ

Với ứng dụng chạy trên máy phát triển, cấu hình kết nối AMQP:

```yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: stream
    password: stream-local
    virtual-host: /
```

Nếu ứng dụng chạy trong container cùng mạng Compose, đặt `host: rabbitmq`. Các thông tin cổng, user, password và virtual host giữ nguyên theo file Compose.

Có thể tách cấu hình theo profile `kafka` và `rabbit` để đổi broker bằng `SPRING_PROFILES_ACTIVE`, đồng thời giữ nguyên định nghĩa hàm và binding chung. Cách này giúp nhóm so sánh cách binder ánh xạ cùng một luồng nghiệp vụ lên hai broker.

## 5. Chạy ứng dụng trong Docker Compose

Khi broker và ứng dụng nằm trong cùng một file Compose hoặc cùng một mạng Compose, ứng dụng có thể dùng tên service làm hostname. Ví dụ phần bổ sung cho service ứng dụng khi dùng Kafka:

```yaml
services:
  order-service:
    build: .
    environment:
      SPRING_PROFILES_ACTIVE: kafka
    depends_on:
      kafka:
        condition: service_healthy
```

Với RabbitMQ, thay dependency bằng service `rabbitmq` và dùng profile `rabbit`. Khai báo `depends_on` với `condition: service_healthy` giúp Compose đợi health check của broker đạt trước khi khởi động ứng dụng. Nếu chỉ dùng dạng `depends_on` không có health condition, Compose chỉ sắp xếp thứ tự khởi động; nó không bảo đảm broker đã sẵn sàng nhận kết nối.

Nếu ứng dụng được khởi chạy riêng từ IDE, không cần thêm service ứng dụng vào file Compose. Chỉ cần đợi broker khỏe mạnh rồi chạy ứng dụng với cấu hình host tương ứng.

## 6. Xác minh kết nối từ ứng dụng

Sau khi broker sẵn sàng, chạy ứng dụng và quan sát log khởi tạo binding. Kiểm tra các dấu hiệu sau:

1. Ứng dụng đọc đúng profile và địa chỉ broker.
2. Binder tạo hoặc kết nối được destination.
3. Consumer binding được khởi tạo với đúng tên group.
4. Gửi một sự kiện thử nghiệm vào topic hoặc exchange và xác nhận hàm `processOrder` nhận được payload.
5. Kiểm tra thông tin consumer group/partition trên Kafka hoặc queue/consumer trên RabbitMQ.

Với Kafka, có thể kiểm tra lại topic bằng `kafka-topics.sh --describe`. Với RabbitMQ, mở trang quản trị để xem exchange, queue, binding và bộ đếm thông điệp. Nếu dùng ứng dụng producer riêng, xác nhận cả số thông điệp đã publish lẫn số thông điệp được consumer xử lý.

Kết nối broker thành công chưa chứng minh toàn bộ hợp đồng sự kiện đúng. Hãy kiểm tra thêm kiểu payload, tên trường, header và schema version. Trong thực hành tiếp theo, cần thử tình huống consumer dừng, broker khởi động lại và thông điệp được giao lại để quan sát hành vi retry, acknowledgement và idempotency.

## 7. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc khắc phục |
|---|---|---|
| `docker compose` không kết nối được daemon | Docker Desktop/Engine chưa chạy | Khởi động daemon rồi chạy lại `docker version` |
| Cổng 9092, 5672 hoặc 15672 đã được sử dụng | Một tiến trình hoặc container khác đang chiếm cổng | Dừng dịch vụ xung đột hoặc đổi cổng host ở phần bên trái của ánh xạ `HOST:CONTAINER` |
| Ứng dụng trên máy host không kết nối Kafka | Broker chưa healthy hoặc listener ngoài không quảng bá đúng địa chỉ | Xem `docker compose logs kafka`, kiểm tra `EXTERNAL://localhost:9092` và health status |
| Ứng dụng trong container báo không phân giải được `localhost` | Dùng địa chỉ của máy host thay cho service DNS | Dùng `kafka:29092` hoặc `rabbitmq:5672` từ mạng Compose |
| Kafka bootstrap kết nối được nhưng truy cập partition bị timeout | Broker quảng bá địa chỉ không thể truy cập từ client | Kiểm tra `KAFKA_ADVERTISED_LISTENERS` và chọn đúng listener theo vị trí client |
| RabbitMQ báo access refused | Sai user/password hoặc virtual host; có thể đang dùng `guest` từ máy khác | Kiểm tra biến `RABBITMQ_DEFAULT_*` và cấu hình `spring.rabbitmq.*` |
| Ứng dụng chạy trước khi broker sẵn sàng | Chỉ dùng thứ tự `depends_on` mà không chờ health | Thêm health check và `condition: service_healthy`, đồng thời cấu hình retry kết nối phù hợp |
| Consumer không nhận thông điệp | Sai destination/group, chưa có queue hoặc payload không giải mã được | Kiểm tra binding, topic/queue, log binder và định dạng payload |

Khi cần xem log broker:

```bash
docker compose -f compose.kafka.yaml logs --tail=100 kafka
docker compose -f compose.rabbitmq.yaml logs --tail=100 rabbitmq
```

Chỉ chạy lệnh tương ứng với file Compose đang dùng. Không nên sửa đồng thời nhiều thuộc tính kết nối khi chưa xác định lỗi nằm ở địa chỉ, cổng, thông tin xác thực hay trạng thái broker.

## 8. Dừng môi trường và quản lý dữ liệu

Dừng và xóa container cùng network do Compose tạo:

```bash
docker compose -f compose.kafka.yaml down
docker compose -f compose.rabbitmq.yaml down
```

Named volume vẫn được giữ sau `down`, vì vậy topic, queue và dữ liệu broker có thể còn khi khởi động lại. Khi muốn xóa toàn bộ dữ liệu thực hành và tạo môi trường sạch, dùng `down -v` cho đúng broker:

```bash
docker compose -f compose.kafka.yaml down -v
docker compose -f compose.rabbitmq.yaml down -v
```

Lệnh `down -v` xóa volume được khai báo trong file tương ứng và làm mất dữ liệu broker cục bộ. Chỉ dùng khi chắc chắn không cần giữ topic, queue hoặc thông điệp đã tạo.

## 9. Phạm vi và nguyên tắc sử dụng

Cấu hình trong bài phục vụ học tập trên máy cá nhân: Kafka chỉ có một node, replication factor bằng một, listener dùng PLAINTEXT; RabbitMQ dùng tài khoản và mật khẩu mẫu. Môi trường này không có đủ cơ chế bảo mật, dự phòng và giám sát cho production. Khi triển khai thật, cần cấu hình TLS, xác thực và phân quyền, network policy, replication hoặc cluster phù hợp, backup, cảnh báo, giới hạn tài nguyên và quản lý bí mật.

Trong Spring Cloud Stream, binder giúp ứng dụng khai báo binding theo một mô hình hàm chung. Tuy nhiên, topic/partition/consumer group của Kafka và exchange/queue/acknowledgement của RabbitMQ vẫn có ngữ nghĩa riêng. Bắt đầu bằng một broker cục bộ, xác nhận kết nối từ đúng vị trí chạy ứng dụng, rồi kiểm tra luồng publish-consume sẽ tạo nền tảng vững chắc để học schema, retry/DLQ, kiểm thử và bảo đảm giao nhận ở các bước tiếp theo.
