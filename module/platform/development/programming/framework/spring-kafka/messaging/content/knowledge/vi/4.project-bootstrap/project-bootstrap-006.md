# Cấu hình broker cục bộ bằng Docker Compose

Ứng dụng Spring Kafka cần kết nối đến một Kafka broker đang hoạt động. Khi phát triển trên máy cá nhân, Docker Compose giúp khởi chạy broker cùng cấu hình mạng và vùng lưu trữ chỉ bằng một lệnh. Cách làm này tạo môi trường lặp lại được giữa các thành viên trong nhóm, thuận tiện để thử `KafkaTemplate`, `@KafkaListener`, topic, partition, consumer group và các kịch bản lỗi.

Bài này dựng một Kafka broker đơn nút ở chế độ KRaft bằng image chính thức `apache/kafka`. Cấu hình hướng đến local development và kiểm thử tích hợp. Nó dùng plaintext, một broker và replication factor bằng một nên không có tính sẵn sàng cao hoặc bảo vệ dữ liệu như một cluster production.

## 1. Chuẩn bị Docker và Docker Compose

Cần cài Docker Engine hoặc Docker Desktop có hỗ trợ Docker Compose v2. Kiểm tra các lệnh sau trong terminal:

```bash
docker --version
docker compose version
```

Image Kafka chính thức yêu cầu Docker phiên bản 20.10.4 trở lên để tránh một số lỗi quyền ghi khi container khởi tạo cấu hình. Nên dùng Docker Desktop hoặc Docker Engine đang được hỗ trợ và cập nhật.

Tạo một thư mục riêng cho hạ tầng local, ví dụ:

```text
local-infrastructure/
└── kafka/
    └── compose.yaml
```

Đặt file Compose ở thư mục `kafka` để các lệnh `docker compose` bên dưới được chạy từ đúng vị trí.

## 2. Hiểu KRaft và các vai trò của một node

Kafka hiện đại có thể chạy ở chế độ KRaft, sử dụng quorum controller để quản lý metadata mà không cần ZooKeeper. Trong cấu hình local đơn giản, một tiến trình Kafka có thể đồng thời giữ hai vai trò:

- **broker:** nhận request từ producer và consumer, lưu partition log và phục vụ đọc/ghi.
- **controller:** tham gia quản lý metadata và trạng thái cluster.

Khi `process.roles` chứa cả `broker,controller`, node chạy ở combined mode. Đây là cấu hình tiện cho máy cá nhân; cluster production thường tách controller và broker theo kiến trúc, số lượng node và yêu cầu vận hành phù hợp.

Một điểm cần hiểu trước khi viết Compose là Kafka có hai địa chỉ kết nối khác nhau:

1. `listeners` xác định địa chỉ và cổng mà broker bind để nhận kết nối.
2. `advertised.listeners` xác định địa chỉ broker trả về cho client trong metadata. Client sẽ dùng các địa chỉ này cho những kết nối tiếp theo.

Vì ứng dụng có thể chạy trực tiếp trên máy host hoặc chạy trong container khác, một địa chỉ duy nhất thường không phù hợp cho cả hai trường hợp. Cấu hình dưới đây dùng hai listener:

| Listener | Địa chỉ quảng bá | Client sử dụng |
| --- | --- | --- |
| `PLAINTEXT_HOST` | `localhost:9092` | Ứng dụng chạy trực tiếp trên máy phát triển |
| `PLAINTEXT` | `broker:19092` | Ứng dụng chạy trong cùng Docker Compose network |
| `CONTROLLER` | `broker:29093` | Giao tiếp nội bộ của KRaft controller |

Không cấu hình Spring Boot trong container trỏ đến `localhost:9092`: bên trong container, `localhost` là chính container ứng dụng. Khi hai container ở cùng Compose network, hãy dùng tên service `broker` và cổng nội bộ `19092`.

## 3. Tạo file `compose.yaml`

Tạo file `compose.yaml` với nội dung sau:

```yaml
services:
  broker:
    image: apache/kafka:4.4.0
    hostname: broker
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: "broker,controller"
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT"
      KAFKA_LISTENERS: "CONTROLLER://:29093,PLAINTEXT_HOST://:9092,PLAINTEXT://:19092"
      KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT_HOST://localhost:9092,PLAINTEXT://broker:19092"
      KAFKA_CONTROLLER_QUORUM_VOTERS: "1@broker:29093"
      KAFKA_CONTROLLER_LISTENER_NAMES: "CONTROLLER"
      KAFKA_INTER_BROKER_LISTENER_NAME: "PLAINTEXT"
      CLUSTER_ID: "4L6g3nShT-eMCtK--X86sw"
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_SHARE_COORDINATOR_STATE_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_SHARE_COORDINATOR_STATE_TOPIC_MIN_ISR: 1
      KAFKA_LOG_DIRS: "/tmp/kraft-combined-logs"
    volumes:
      - kafka-data:/tmp/kraft-combined-logs
    healthcheck:
      test:
        - CMD-SHELL
        - "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1"
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s
    restart: unless-stopped

volumes:
  kafka-data:
```

Image `apache/kafka:4.4.0` là image JVM chính thức của Apache Kafka. Hãy pin một tag cụ thể để những lần chạy sau sử dụng cùng phiên bản; khi nâng tag, đọc release notes và chạy lại kiểm thử tích hợp trước khi dùng trong dự án.

### Giải thích cấu hình quan trọng

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `KAFKA_NODE_ID` | ID duy nhất của node trong cluster |
| `KAFKA_PROCESS_ROLES` | Cho node đảm nhận vai trò broker và controller |
| `KAFKA_LISTENERS` | Các địa chỉ/cổng Kafka bind bên trong container |
| `KAFKA_ADVERTISED_LISTENERS` | Địa chỉ broker công bố cho client sau khi bootstrap |
| `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP` | Ánh xạ tên listener sang giao thức bảo mật |
| `KAFKA_CONTROLLER_QUORUM_VOTERS` | Danh sách node controller và địa chỉ quorum |
| `KAFKA_CONTROLLER_LISTENER_NAMES` | Listener dùng cho giao tiếp controller |
| `KAFKA_INTER_BROKER_LISTENER_NAME` | Listener dùng cho giao tiếp broker với broker |
| `CLUSTER_ID` | Định danh cluster KRaft khi format storage |
| `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR` | Replication factor của topic nội bộ lưu offset consumer group |
| `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR` | Replication factor của topic lưu trạng thái transaction |
| `KAFKA_LOG_DIRS` | Thư mục lưu dữ liệu log của Kafka |
| `kafka-data` | Named volume giúp dữ liệu tồn tại qua lần recreate container |

Vì chỉ có một broker, các topic nội bộ cần replication factor bằng một. Đây là lựa chọn để broker đơn nút có thể khởi động; nó không cung cấp khả năng chịu lỗi broker. Các giá trị `KAFKA_SHARE_COORDINATOR_*` cũng được đặt bằng một để phù hợp môi trường một node khi dùng các chức năng share group/coordinator ở phiên bản Kafka mới.

`CLUSTER_ID` là ID mẫu dùng cho môi trường học tập. Giữ ổn định giá trị này khi tiếp tục dùng lại volume đã format. Nếu tạo một cluster mới với storage trống, hãy tạo ID hợp lệ mới hoặc dùng ID mẫu cho một môi trường local độc lập; không đổi tùy tiện ID khi dữ liệu cluster cũ vẫn còn.

## 4. Khởi động và kiểm tra broker

Từ thư mục chứa `compose.yaml`, kiểm tra cú pháp và cấu hình Compose:

```bash
docker compose config
```

Khởi động broker ở chế độ nền:

```bash
docker compose up -d
```

Kiểm tra trạng thái:

```bash
docker compose ps
```

Theo dõi log nếu broker chưa healthy hoặc khởi động thất bại:

```bash
docker compose logs -f broker
```

Healthcheck trong file Compose gọi Kafka CLI để kiểm tra broker có nhận request metadata qua listener host hay chưa. Khi trạng thái chuyển sang `healthy`, có thể bắt đầu kết nối từ ứng dụng. Nếu healthcheck thất bại, đọc log để tìm nguyên nhân như cổng đã bị chiếm, sai cấu hình listener, lỗi quyền ghi volume hoặc lỗi format storage.

Kiểm tra broker bằng Kafka CLI bên trong container:

```bash
docker compose exec broker /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server broker:19092
```

Nếu lệnh trả về thông tin broker và API versions, listener nội bộ đã phục vụ kết nối. Có thể dùng listener host từ máy phát triển bằng `localhost:9092`.

## 5. Tạo topic và gửi/nhận thử dữ liệu

Tạo topic `orders.created` với ba partition và replication factor một:

```bash
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server broker:19092 --create --topic orders.created --partitions 3 --replication-factor 1
```

Liệt kê topic:

```bash
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server broker:19092 --list
```

Xem partition và metadata của topic:

```bash
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server broker:19092 --describe --topic orders.created
```

Mở một terminal để nhận dữ liệu từ đầu topic:

```bash
docker compose exec broker /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server broker:19092 --topic orders.created --from-beginning
```

Mở terminal thứ hai để gửi dữ liệu:

```bash
docker compose exec -it broker /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server broker:19092 --topic orders.created
```

Nhập vài dòng, mỗi dòng là một message, rồi quan sát terminal consumer. Nhấn `Ctrl+C` để dừng producer hoặc consumer. Các lệnh này dùng listener nội bộ của Docker network; Kafka CLI trong container có thể phân giải tên `broker`.

## 6. Kết nối ứng dụng Spring Boot

### Ứng dụng chạy trực tiếp trên máy host

Nếu chạy Spring Boot bằng IDE hoặc Maven/Gradle trên máy phát triển, dùng listener host:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
```

`localhost:9092` là cổng host được ánh xạ đến listener `PLAINTEXT_HOST` của broker. Nếu cổng 9092 đã được một tiến trình khác sử dụng, đổi port mapping và advertised listener tương ứng, sau đó cập nhật `bootstrap-servers`.

### Ứng dụng Spring Boot cũng chạy trong Docker Compose

Khi ứng dụng nằm trong cùng Compose project/network, dùng tên service và listener nội bộ:

```yaml
spring:
  kafka:
    bootstrap-servers: broker:19092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
```

Nếu cấu hình qua environment variable của container ứng dụng, thuộc tính tương ứng là:

```yaml
environment:
  SPRING_KAFKA_BOOTSTRAP_SERVERS: broker:19092
```

Ứng dụng phải tham gia cùng Docker network với service `broker`. Có thể khai báo `depends_on` để điều phối thứ tự khởi động; nếu muốn đợi broker sẵn sàng, dùng điều kiện `service_healthy` với healthcheck như trong ví dụ. Chỉ dùng `depends_on` dạng danh sách mặc định không bảo đảm broker đã nhận kết nối khi ứng dụng bắt đầu.

## 7. Dừng, khởi động lại và quản lý dữ liệu

Dừng container nhưng giữ volume:

```bash
docker compose down
```

Khởi động lại:

```bash
docker compose up -d
```

Vì `kafka-data` là named volume, dữ liệu topic và metadata KRaft vẫn tồn tại qua các lần `down` rồi `up` thông thường. Điều này giúp không phải tạo lại topic và gửi lại dữ liệu sau mỗi lần dừng môi trường.

Nếu muốn xóa toàn bộ dữ liệu local và tạo cluster sạch, dùng:

```bash
docker compose down -v
```

Lệnh `-v` xóa named volume do Compose quản lý, vì vậy tất cả topic, bản ghi, offset và metadata lưu trong volume sẽ mất. Chỉ chạy khi chủ động muốn reset môi trường học tập.

## 8. Xử lý các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
| --- | --- | --- |
| Container thoát ngay sau khi start | Cấu hình KRaft thiếu hoặc sai, volume không ghi được | Xem `docker compose logs broker`; kiểm tra node ID, roles, quorum voters và quyền thư mục |
| Host kết nối được lúc đầu nhưng sau đó lỗi metadata | Advertised listener trả về hostname không phân giải được từ client | Dùng `localhost:9092` cho host và `broker:19092` cho container |
| Spring Boot trong container báo không resolve `localhost` | Ứng dụng đang trỏ về chính container Spring Boot | Đổi bootstrap server sang `broker:19092` |
| Port 9092 đã được sử dụng | Một Kafka broker hoặc tiến trình khác đang chiếm cổng | Dừng tiến trình đó hoặc đổi host port và advertised listener cho nhất quán |
| Topic không tạo được với replication factor ba | Cluster local chỉ có một broker | Dùng replication factor một cho bài tập đơn nút |
| Dữ liệu biến mất sau khi recreate container | Chưa mount named volume vào `KAFKA_LOG_DIRS` hoặc volume đã bị xóa | Xác minh mapping `kafka-data` và tránh `docker compose down -v` nếu muốn giữ dữ liệu |
| Broker vẫn chưa healthy | Broker chưa sẵn sàng hoặc healthcheck dùng listener không hoạt động | Xem log và chạy Kafka CLI thủ công để phân biệt lỗi broker với lỗi healthcheck |

## 9. Giới hạn của môi trường local

Cấu hình trên dùng một node ở combined mode, plaintext và replication factor một. Nó phù hợp để học API, thử listener, quan sát partition, offset, consumer group và chạy integration test đơn giản. Nó không mô phỏng đầy đủ một Kafka cluster production.

Khi triển khai thật, cần thiết kế nhiều broker và controller theo kiến trúc KRaft phù hợp, replication factor và `min.insync.replicas`, xác thực SASL, mã hóa TLS, phân quyền ACL, giám sát, backup/restore, dung lượng đĩa và quy trình nâng cấp. Không expose listener plaintext của môi trường local ra mạng công cộng hoặc dùng nguyên cấu hình này cho dữ liệu quan trọng.

## 10. Kết luận

Docker Compose giúp tạo một Kafka broker local nhất quán để phát triển ứng dụng Spring Kafka. Cấu hình KRaft một node dùng image Apache Kafka chính thức, named volume để giữ dữ liệu và hai listener để hỗ trợ cả ứng dụng chạy trên host lẫn ứng dụng chạy trong Docker network.

Khi debug kết nối, hãy kiểm tra cả địa chỉ mà broker bind (`listeners`) và địa chỉ broker công bố (`advertised.listeners`). Sau khi broker healthy, tạo topic, gửi/nhận thử bằng Kafka CLI rồi cấu hình `spring.kafka.bootstrap-servers` theo vị trí chạy của ứng dụng. Luôn nhớ rằng đây là môi trường local một node; cluster production cần cấu hình và vận hành riêng.

## Tài liệu tham khảo

- [Apache Kafka — Docker](https://kafka.apache.org/documentation/#docker)
- [Apache Kafka — Docker Compose single-node example](https://github.com/apache/kafka/blob/trunk/docker/examples/docker-compose-files/single-node/plaintext/docker-compose.yml)
- [Apache Kafka — Docker image examples](https://github.com/apache/kafka/blob/trunk/docker/examples/README.md)
