# Mô phỏng consumer lag trong Spring Kafka: phòng lab vận hành từ cơ bản đến xử lý sự cố

## 1. Vì sao cần mô phỏng consumer lag?

Trong hệ thống dùng Apache Kafka, một consumer vẫn có thể đang chạy, không ném exception và liên tục ghi log “processed”, nhưng **không theo kịp tốc độ dữ liệu mới**. Số lượng record chưa được consumer group xác nhận tăng lên — đó là một biểu hiện của **consumer lag**. Nếu kéo dài, dữ liệu đơn hàng, thanh toán, thông báo hoặc đồng bộ kho có thể đến hệ thống đích muộn hơn SLA.

Bài thực hành **Mô phỏng consumer lag**, thuộc *Spring Kafka Reliability Operations → Thực hành vận hành*, hướng dẫn tạo những tình huống lag **có kiểm soát** trong một môi trường Kafka riêng, đo đạc bằng công cụ vận hành và khôi phục theo từng nguyên nhân. Đây không phải một bài “cứ tăng concurrency lên 10 là hết lag”: ta cần hiểu offset, partition assignment, throughput, transaction, retry và khả năng xử lý lặp.

### Bạn sẽ thực hành được gì?

1. Tạo Kafka broker/topic và một Spring Boot consumer group độc lập.
2. Quan sát `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG` bằng Kafka CLI.
3. Tạo lag theo **năm nguyên nhân**: producer burst, consumer xử lý chậm, pause/stop, thiếu consumer capacity và partition/key skew.
4. Phân biệt lag tăng do input arrival rate cao với lag tăng vì committed offset không tiến.
5. Đo tốc độ sản xuất, tốc độ commit, xu hướng lag và ước lượng thời gian bắt kịp.
6. Kiểm tra mối quan hệ giữa `max.poll.records`, `max.poll.interval.ms` và rebalance.
7. So sánh khôi phục bằng giảm độ trễ, tăng concurrency, mở rộng partitions và giảm tải upstream.
8. Nhận biết “lag bằng 0 nhưng dữ liệu vẫn sai” do ack quá sớm hoặc xử lý lỗi sai.
9. Thiết kế dashboard, alert, runbook và kiểm thử hồi phục.
10. Dọn tài nguyên lab an toàn mà không thao tác nhầm consumer group production.

Code minh họa dùng **Java 17, Spring Boot 3.4.x, Spring Kafka 3.3.x**, Kafka broker dòng **3.9.x** và Docker Compose. Các lệnh trong bài là **lệnh người học có thể chạy trong lab riêng**; bài viết này không thực thi Docker, Gradle, Kafka hay gửi tải vào hệ thống thật.

### Phạm vi an toàn

Mọi topic, group và API điều khiển của bài đều đặt tên `lag.lab.*`, dùng broker **cục bộ**, không chứa dữ liệu khách hàng và không có security production. Không làm các thí nghiệm pause, lỗi có chủ đích, offset reset, quá tải hoặc producer burst trên cluster doanh nghiệp. Các thao tác đó có thể ảnh hưởng SLA, gây redelivery hoặc làm mất dữ liệu chưa xử lý nếu dùng sai.

---

## 2. Hiểu lag trước khi chạy thí nghiệm

### 2.1. Offset của một partition

Một topic Kafka được chia thành partitions. Trong mỗi partition, record nằm ở các offset tăng dần (không giả định liên tục trong mọi chính sách retention/compaction).

```text
Topic: lag.lab.orders
Partition: 0

offset       0   1   2   3   4   5   6   7   8   9  10 ...
record       ●   ●   ●   ●   ●   ●   ●   ●   ●   ●   ●
                         ▲                       ▲
             committed next offset = 4     log end = 11

Remaining consumer-group offset lag ≈ 11 - 4 = 7
```

**Lưu ý:** Kafka committed offset là vị trí **tiếp theo** consumer dự kiến đọc sau record đã commit. Nếu group đã commit 4, thường nghĩa là đã hoàn tất record trước offset 4 (tức 0–3) theo chính sách commit, chứ không có nghĩa mới xử lý đến đúng record 4.

### 2.2. Công thức lag theo consumer group và partition

Với partition `p`:

```text
L_p = max(0, logEndOffset_p - committedOffset_p)

L_total = Σ L_p
```

Ví dụ:

| Partition | CURRENT-OFFSET | LOG-END-OFFSET | LAG |
|---:|---:|---:|---:|
| 0 | 500 | 900 | 400 |
| 1 | 1.000 | 1.100 | 100 |
| 2 | 600 | 1.300 | 700 |
| **Tổng** | | | **1.200** |

Các con số là dữ liệu **minh họa**, không phải output đã đo từ lab.

Trong `kafka-consumer-groups.sh --describe`, `CURRENT-OFFSET` đại diện committed offset của group; `LOG-END-OFFSET` là end offset theo báo cáo của tool, còn `LAG` là chênh lệch. Một record đã được poll vào bộ nhớ nhưng **chưa commit** vẫn có thể thuộc lag theo committed offset.

### 2.3. Lag không phải lúc nào cũng là số business event chưa xử lý

Số offset không luôn bằng số business event chưa xử lý:

- Có record đã **xử lý xong** nhưng Kafka offset chưa commit.
- Một consumer commit offset trước khi business DB commit: lag có thể thấp nhưng dữ liệu bị thiếu.
- Trong topic compacted hoặc có transaction/control records, khoảng cách offset không nhất thiết tương ứng đúng số record business còn đọc được.
- Với consumer `isolation.level=read_committed`, vị trí có thể đọc còn liên quan **Last Stable Offset** của giao dịch Kafka; log end/broker metrics cần được diễn giải theo isolation và exporter.
- Record bị chuyển DLT có thể khiến offset của topic chính tiến dù business event vẫn đang chờ replay.
- Group chưa có committed offset có thể hiển thị `-` hoặc không có dòng tương ứng; khi đó không tính “lag bằng 0”.
- Kafka retention có thể xóa dữ liệu trước khi group đọc, làm chênh lệch offset không thể hiện chính xác những event đã mất.

**Quy tắc vận hành:** luôn xem lag cùng throughput, số records lỗi/DLT, tuổi event, trạng thái DB và SLA nghiệp vụ.

### 2.4. Lag tăng hay giảm phụ thuộc hai tốc độ

Trong một khoảng thời gian `Δt`:

```text
lag cuối kỳ ≈ max(
    0,
    lag đầu kỳ
      + số record mới có thể đọc
      - số offset được commit tiến lên
)
```

Giả sử producer tạo 120 record/giây, còn consumer group chỉ commit tương ứng 40 record/giây khi có backlog:

```text
Lag growth rate ≈ 120 - 40 = 80 records/s

Sau 60 giây, lag tăng xấp xỉ 4.800 records.
```

Nếu producer dừng và consumer duy trì 40 records/s, backlog 4.800 records cần khoảng 120 giây để bắt kịp, **trong điều kiện tốc độ xử lý thực được duy trì và không có record lỗi làm kẹt partition**.

### 2.5. Lag records khác lag time

Hai group cùng có 50.000 record lag có thể khác mức độ rủi ro:

- Group A xử lý 25.000 record/giây, có thể bắt kịp nhanh.
- Group B xử lý 50 record/giây, có thể backlog rất lâu.
- Một partition chứa record gần nhất cách hiện tại 45 phút, partition khác chỉ 10 giây.

Do đó cần quan sát **age of oldest unprocessed event**, ETA catch-up và business deadline, không chỉ một con số LAG.

---

## 3. Điều kiện làm bài và topology

### 3.1. Những thứ cần có

- Docker Engine/ Docker Desktop có Docker Compose.
- Java 17 và Gradle/Gradle Wrapper.
- Một cổng host `29092` dành cho Kafka và `8080` cho Spring Boot local.
- CLI `docker compose`.
- Terminal PowerShell hoặc shell tương đương.
- Chỉ sử dụng file dữ liệu giả lập.

Bài không cần tạo Kafka Connect, Schema Registry hoặc một hệ giám sát Prometheus thực để quan sát offset. Kafka CLI và endpoint Actuator là đủ cho vòng thực hành đầu tiên.

### 3.2. Topology

```text
                Docker Compose
          ┌────────────────────────┐
          │ Kafka KRaft single node│
          │ internal: kafka:9092   │
          │ host: localhost:29092  │
          └───────────┬────────────┘
                      │
              topic lag.lab.orders
                 3 partitions
                      │
       ┌──────────────┴────────────────┐
       │                               │
       ▼                               ▼
Producer perf CLI             Spring Boot app
thử các mức throughput        group lag-lab-v1
                              @KafkaListener
                                   │
                        ┌──────────┴──────────┐
                        │ delay/pause/resume  │
                        │ metrics / stats     │
                        └─────────────────────┘
                                   │
                                   ▼
                       kafka-consumer-groups CLI
                         offset / lag / members
```

**Single broker, replication factor 1 và plaintext chỉ phù hợp lab.** Đừng copy cấu hình dưới đây lên production: không có high availability, không có TLS/SASL, không bảo vệ multi-tenant và không thiết kế resource limits cho traffic thật.

---

## 4. Khởi tạo broker bằng Docker Compose

Tạo thư mục lab riêng, ví dụ `spring-kafka-lag-lab`. Tạo `compose.yaml`:

```yaml
services:
  kafka:
    image: apache/kafka:3.9.1
    hostname: kafka
    container_name: kafka-lag-lab
    ports:
      - "127.0.0.1:29092:29092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: "1@kafka:9093"
      KAFKA_LISTENERS: "PLAINTEXT://:9092,CONTROLLER://:9093,HOST://:29092"
      KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT://kafka:9092,HOST://localhost:29092"
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT,HOST:PLAINTEXT"
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
```

Ở đây:

- Container nội bộ truy cập broker qua `kafka:9092`.
- Ứng dụng Java chạy trên host truy cập `localhost:29092`.
- Cổng host chỉ bind loopback `127.0.0.1`; API Kafka không chủ ý mở cho toàn mạng.
- Một node vừa là broker vừa là controller ở KRaft mode; không có ZooKeeper.
- Các internal replication factor đặt 1 vì chỉ có một broker.
- Image đã pin version để tránh “latest” thay đổi hành vi ngoài ý muốn.

Đưa cluster lên:

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=80 kafka
```

Nếu broker chưa ready, lệnh Kafka CLI có thể báo kết nối từ chối trong lúc container khởi động. Kiểm tra logs và readiness trước khi chạy thí nghiệm; không mặc định container ở trạng thái “Up” là broker đã sẵn sàng.

### 4.1. Tạo topic ba partitions

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic lag.lab.orders --partitions 3 --replication-factor 1
```

Kiểm tra:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic lag.lab.orders
```

Kết quả kỳ vọng có `PartitionCount: 3` và `ReplicationFactor: 1`. Không cần reset/delete topic khi mỗi vòng thí nghiệm bắt đầu: có thể tạo group ID mới hoặc chốt mốc offset, tùy mục đích.

### 4.2. Kiểm tra broker từ host

Nếu có Kafka CLI trên host, dùng:

```bash
kafka-topics.sh --bootstrap-server localhost:29092 --list
```

Nếu chưa cài Kafka CLI trên host, toàn bộ lệnh đo đạc dưới đây chạy bằng `docker compose exec -T kafka`; không cần cài thêm broker tool.

### 4.3. Tránh chồng lấn nhiều lab

Không dùng topic `orders.events` và group `orders-prod` vốn có thể thuộc một hệ thống khác. Tên `lag.lab.orders` / `lag-lab-v1` dễ phân biệt, nhưng **tên không thay thế bảo vệ môi trường**: luôn xác nhận `--bootstrap-server kafka:9092` chỉ trỏ broker Docker cục bộ.

---

## 5. Tạo ứng dụng Spring Boot consumer có thể điều chỉnh độ trễ

### 5.1. Cấu trúc

```text
spring-kafka-lag-lab/
├── compose.yaml
├── build.gradle
├── settings.gradle
└── src/
    └── main/
        ├── java/com/example/laglab/
        │   ├── LagLabApplication.java
        │   ├── LagLabListener.java
        │   └── LagLabControlController.java
        └── resources/
            ├── application.yml
            └── application-lag-lab.yml
```

Dự án cung cấp:

- `@KafkaListener` tiêu thụ tuần tự record trên mỗi partition.
- `AtomicLong delayMs` để mô phỏng business processing chậm.
- `KafkaListenerEndpointRegistry` để pause/resume/stop/start consumer container.
- HTTP API local để thay delay trong lab.
- Micrometer Counter/Timer cho processing throughput.
- Spring Boot Actuator để xem metrics và health.

### 5.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.kafka:spring-kafka'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-kafka-lag-lab'
```

Phiên bản trên dùng cho hướng dẫn Spring Boot 3.4.x. Với Spring Boot 4/Spring Kafka 4, phải kiểm tra compatibility và thay đổi API, không nâng riêng một artifact không cùng BOM.

### 5.3. Spring Boot application

```java
package com.example.laglab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LagLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(LagLabApplication.class, args);
    }
}
```

### 5.4. application.yml

Đặt mặc định an toàn:

```yaml
spring:
  application:
    name: spring-kafka-lag-lab
  kafka:
    bootstrap-servers: "localhost:29092"
    consumer:
      group-id: "lag-lab-v1"
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      max-poll-records: 50
      properties:
        max.poll.interval.ms: 300000
    listener:
      type: single
      ack-mode: record
      concurrency: 1
      poll-timeout: 2s

app:
  lab:
    topic: "lag.lab.orders"
    group-id: "lag-lab-v1"
    concurrency: 1
    delay-ms: 0

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"

server:
  address: "127.0.0.1"
  port: 8080
```

Giải thích:

- `enable-auto-commit=false`: offset do Spring Kafka container quản lý.
- `ack-mode=record`: với record listener đồng bộ không transactional, container commit sau khi xử lý record thành công theo policy.
- `max-poll-records=50`: một lần poll lấy tối đa 50 records để giới hạn thời gian xử lý liên tục giữa hai polls.
- `max.poll.interval.ms=300000`: baseline 5 phút, tránh rebalance do processing quá dài trong bài tập bình thường.
- `auto-offset-reset=earliest`: chỉ áp dụng khi group không có committed offset hợp lệ, **không** tự tua group đã xử lý về đầu.
- `concurrency=1`: dễ thấy mức tiêu thụ ban đầu.
- `server.address=127.0.0.1`: HTTP API điều khiển lab không được phơi ra ngoài.
- Group ID xuất hiện ở cả `spring.kafka.consumer.group-id` và `app.lab.group-id` để listener có thể override tường minh; phải giữ hai giá trị nhất quán hoặc loại bỏ một nguồn config trong dự án thật.

File `application-lag-lab.yml` có thể chứa những override chỉ dành cho profile lab, nhưng ở ví dụ này giá trị nền đã an toàn cho localhost. Profile sẽ giới hạn bean listener/control xuất hiện trong ứng dụng.

### 5.5. Listener giả lập business processing chậm

Tạo `LagLabListener.java`:

```java
package com.example.laglab;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@Profile("lag-lab")
public class LagLabListener {

    private static final Logger log =
            LoggerFactory.getLogger(LagLabListener.class);

    private final AtomicLong delayMs;
    private final AtomicLong processed = new AtomicLong();

    private final Counter processedCounter;
    private final Timer processingTimer;

    public LagLabListener(
            @Value("${app.lab.delay-ms:0}") long initialDelay,
            MeterRegistry registry) {

        this.delayMs = new AtomicLong(initialDelay);

        this.processedCounter = Counter.builder(
                        "lag.lab.processed")
                .description("Successfully processed lab records")
                .register(registry);

        this.processingTimer = Timer.builder(
                        "lag.lab.processing.duration")
                .description("Lab listener processing latency")
                .register(registry);
    }

    @KafkaListener(
            id = "lag-lab-consumer",
            topics = "${app.lab.topic}",
            groupId = "${app.lab.group-id}",
            concurrency = "${app.lab.concurrency:1}")
    public void onRecord(ConsumerRecord<String, String> record)
            throws InterruptedException {

        long startNanos = System.nanoTime();
        try {
            long sleep = delayMs.get();
            if (sleep > 0) {
                // CỐ Ý gây chậm trong lab; không đưa vào production!
                Thread.sleep(sleep);
            }

            long count = processed.incrementAndGet();
            processedCounter.increment();

            // Không log mỗi record để tránh log I/O gây sai lệch.
            if (count % 500 == 0) {
                log.info(
                        "processed={}, partition={}, offset={}, delayMs={}",
                        count, record.partition(),
                        record.offset(), sleep);
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        } finally {
            processingTimer.record(
                    System.nanoTime() - startNanos,
                    TimeUnit.NANOSECONDS);
        }
    }

    public long getProcessed() {
        return processed.get();
    }

    public long getDelayMs() {
        return delayMs.get();
    }

    public void setDelayMs(long newDelay) {
        if (newDelay < 0 || newDelay > 5_000) {
            throw new IllegalArgumentException(
                    "Lab delay must be between 0 and 5000 ms");
        }
        delayMs.set(newDelay);
    }
}
```

**Vì sao có `AtomicLong`?** HTTP thread đổi giá trị delay trong khi Kafka consumer thread đang xử lý; `AtomicLong` cho visibility/thread safety của một biến trạng thái đơn giản.

**Giới hạn:** counter `processed` chỉ tính trong **đời sống JVM hiện tại**, không phải tổng số record đã commit của Kafka group qua tất cả lần restart. Thống kê group bền vững lấy từ Kafka committed offsets. Counter cũng không thể chứng minh database side effect đã commit vì demo chỉ sleep, không ghi DB.

**Không đưa `Thread.sleep` trong listener thật** để throttle production. Ở production, slowdown là triệu chứng để xác định nghẽn DB, network, external API, thread pool, GC, backpressure; giải quyết bằng timeout/rate limit/concurrency và kiến trúc bền vững.

### 5.6. Local control API để pause/resume/đổi delay

Tạo `LagLabControlController.java`:

```java
package com.example.laglab;

import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.kafka.config
        .KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@Profile("lag-lab")
@RequestMapping("/lab")
public class LagLabControlController {

    private final KafkaListenerEndpointRegistry registry;
    private final LagLabListener listener;

    public LagLabControlController(
            KafkaListenerEndpointRegistry registry,
            LagLabListener listener) {
        this.registry = registry;
        this.listener = listener;
    }

    private MessageListenerContainer container() {
        MessageListenerContainer result =
                registry.getListenerContainer(
                        "lag-lab-consumer");

        if (result == null) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Lab listener not registered");
        }
        return result;
    }

    @GetMapping("/status")
    public Map<String, Object> status() {
        MessageListenerContainer c = container();
        return Map.of(
                "processedSinceStartup", listener.getProcessed(),
                "delayMs", listener.getDelayMs(),
                "running", c.isRunning(),
                "pauseRequested", c.isPauseRequested(),
                "containerPaused", c.isContainerPaused());
    }

    @PostMapping("/delay")
    public Map<String, Object> setDelay(
            @RequestParam("ms") long ms) {

        if (ms < 0 || ms > 5_000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "ms must be between 0 and 5000");
        }

        listener.setDelayMs(ms);
        return Map.of("delayMs", listener.getDelayMs());
    }

    @PostMapping("/pause")
    public Map<String, Object> pause() {
        MessageListenerContainer c = container();
        c.pause();
        return Map.of(
                "pauseRequested", c.isPauseRequested());
    }

    @PostMapping("/resume")
    public Map<String, Object> resume() {
        MessageListenerContainer c = container();
        c.resume();
        return Map.of(
                "pauseRequested", c.isPauseRequested());
    }

    @PostMapping("/stop")
    public Map<String, Object> stop() {
        MessageListenerContainer c = container();
        c.stop();
        return Map.of("stopRequested", true);
    }

    @PostMapping("/start")
    public Map<String, Object> start() {
        MessageListenerContainer c = container();
        c.start();
        return Map.of("startRequested", true);
    }
}
```

**Cảnh báo:** API này chỉ để lab. Không đưa controller điều khiển consumer vào production mà không có authentication, authorization, audit và cơ chế kiểm soát người được phép. `server.address=127.0.0.1` giảm phạm vi tiếp cận, nhưng không thay thế security trong môi trường nhiều người dùng.

`pause()` có thể chưa hoàn tất ngay lúc HTTP response trả về; `isPauseRequested()` và `isContainerPaused()` có semantics khác nhau. Sau pause, chờ trạng thái thực sự paused trước khi đo.

`stop()` khiến container dừng consumer và có thể tác động group membership/rebalance. `pause()` trong Spring Kafka vẫn tiếp tục poll bên dưới để duy trì membership và tránh rebalance không cần thiết. Hai bài thí nghiệm này **không tương đương**.

---

## 6. Khởi động consumer và thiết lập baseline

### 6.1. Chạy Spring Boot

Với Gradle Wrapper trên Linux/macOS:

```bash
./gradlew bootRun --args='--spring.profiles.active=lag-lab'
```

Với PowerShell/Windows:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=lag-lab"
```

Đây là **lệnh mẫu để học viên tự chạy** trong project lab; không thực thi trong quá trình tạo bài viết.

Kiểm tra endpoint:

```bash
curl http://127.0.0.1:8080/lab/status
```

Kỳ vọng một JSON tương tự:

```json
{
  "processedSinceStartup": 0,
  "delayMs": 0,
  "running": true,
  "pauseRequested": false,
  "containerPaused": false
}
```

Trạng thái thực phụ thuộc lúc Kafka broker ready và Spring context startup. Nếu listener không start, kiểm tra connection, topic, group và exception logs trước khi tạo hàng nghìn messages.

### 6.2. Gửi một ít record khởi tạo group

Chạy Kafka producer performance tool với số lượng nhỏ:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 30 --record-size 128 --throughput 20 --producer-props bootstrap.servers=kafka:9092 acks=all
```

Producer này tạo payload giả kích thước 128 byte, không có dữ liệu thật. Khi app có `delayMs=0`, group sẽ nhanh chóng consume và commit những record vừa gửi.

### 6.3. Xem consumer group offsets

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1
```

Ví dụ output:

```text
GROUP       TOPIC           PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
lag-lab-v1  lag.lab.orders  0         11             11             0
lag-lab-v1  lag.lab.orders  1         10             10             0
lag-lab-v1  lag.lab.orders  2          9              9             0
```

Phân phối 30 record vào ba partitions không cố định; đây là một ví dụ số liệu sau khi các record đã được commit, **không phải lời hứa mỗi partition luôn có 10 records**.

### 6.4. Xem members và assignment

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --members --verbose
```

Khi chỉ một consumer thread, một group member thường nhận cả ba partitions. Nếu có ba consumer threads trong cùng group, assignments có thể được chia thành mỗi consumer một partition. Việc phân phối thực tế phụ thuộc subscription, group protocol và assignor.

### 6.5. Vì sao phải tạo baseline trước?

Nếu group chưa từng commit offset, một số phiên bản Kafka CLI hiển thị `CURRENT-OFFSET=-`, không trả lag có ý nghĩa như khi group đã active. Việc gửi 30 warm-up records và đợi commit đảm bảo có mốc so sánh.

Đừng thấy dấu `-` rồi ghi vào báo cáo “lag=0”. Hãy ghi là **offset chưa xác định/chưa được commit** và xác minh `auto.offset.reset` cùng trạng thái group.

---

## 7. Kịch bản 1: Producer burst làm lag tăng

### 7.1. Giả thiết

- Consumer chạy với `delayMs=0`, concurrency 1.
- Producer gửi một burst vài nghìn record.
- Mục tiêu: quan sát lag tăng trong lúc producer đẩy nhanh hơn consumer, sau đó giảm khi consumer catch up.

Lệnh producer:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 6000 --record-size 256 --throughput 500 --producer-props bootstrap.servers=kafka:9092 acks=all
```

`throughput=500` là mục tiêu rate của tool, không phải kết quả đảm bảo. Tool tự báo actual records/s; lưu lại số đo thay vì mặc định producer chính xác 500 mỗi giây.

### 7.2. Quan sát trong khi producer đang chạy

Mở terminal thứ hai:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1
```

Lặp câu lệnh sau vài giây. Trên PowerShell có thể dùng:

```powershell
1..10 | ForEach-Object {
    docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1
    Start-Sleep -Seconds 5
}
```

**Đừng mở hàng trăm tiến trình CLI cùng lúc**; describe group là thao tác quan sát, không cần poll quá dày.

### 7.3. Ghi bảng thí nghiệm

| Thời điểm | Tổng LOG-END-OFFSET | Tổng CURRENT-OFFSET | Tổng LAG | Nhận xét |
|---|---:|---:|---:|---|
| t0 | Đo | Đo | Đo | Trước burst |
| t1 | Đo | Đo | Đo | Producer đang gửi |
| t2 | Đo | Đo | Đo | Cuối burst |
| t3 | Đo | Đo | Đo | Consumer đang bắt kịp |
| t4 | Đo | Đo | Đo | Trở về baseline |

Nếu consumer đủ nhanh, lag có thể gần 0 trong mọi snapshot. Đây **không phải thí nghiệm thất bại**; nó chứng minh tải này chưa vượt capacity. Muốn tạo backlog rõ hơn, dùng scenario 2 với processing delay, thay vì cố gửi tải vô hạn.

### 7.4. Điều cần kết luận

- Lag tăng khi tốc độ append vượt tốc độ commit group.
- Sau khi burst dừng, lag giảm nếu consumer không bị lỗi.
- Một biểu đồ lag hình “núi” có thể hoàn toàn bình thường khi batch/burst được thiết kế trước.
- Chỉ cần alert nếu backlog/age vượt ngưỡng SLA, tăng liên tục hoặc không catch up đúng thời hạn.

---

## 8. Kịch bản 2: Business processing chậm

### 8.1. Đặt delay 100 ms mỗi record

Trên Linux/macOS:

```bash
curl -X POST "http://127.0.0.1:8080/lab/delay?ms=100"
```

Trên PowerShell có thể dùng:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/lab/delay?ms=100"
```

Nếu chỉ một consumer thread và chưa tính overhead, năng lực tối đa lý thuyết:

```text
1000 ms / 100 ms per record ≈ 10 records/s
```

Thực tế nhỏ hơn do poll/commit/logging/scheduling, và Kafka phân phối ba partitions nhưng consumer **vẫn xử lý lần lượt trên một thread** ở concurrency 1.

### 8.2. Tạo input nhanh hơn consumer

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 1200 --record-size 256 --throughput 150 --producer-props bootstrap.servers=kafka:9092 acks=all
```

Trong giai đoạn producer chạy, rate lý thuyết:

```text
Arrival rate ≈ 150 records/s
Consume rate ≈ 10 records/s
Lag growth ≈ 140 records/s
```

Thời gian producer gửi 1.200 record ở rate 150/s khoảng tám giây trong điều kiện lý tưởng; backlog gần cuối có thể quanh 1.000 record. Đây là **ước lượng**, không phải kết quả thực của tool.

### 8.3. Ghi nhận câu hỏi quan trọng

- `LOG-END-OFFSET` tăng nhanh hay chậm?
- `CURRENT-OFFSET` vẫn tiến hay đứng yên?
- Lag tăng ở cả ba partitions hay tập trung ở một partition?
- Có rebalance không? Group có `Stable` không?
- Business method chiếm bao lâu so với `max.poll.interval.ms`?
- CPU, GC, network hay database có phải bottleneck thực không? Trong lab, ta biết chắc nguyên nhân là sleep.

### 8.4. Hạ delay để bắt kịp

```bash
curl -X POST "http://127.0.0.1:8080/lab/delay?ms=10"
```

Consumer capacity lý thuyết tăng lên gần 100 records/s khi còn backlog, và lag có thể giảm nhanh hơn. Nếu producer đã dừng, tốc độ backlog tiêu thụ chỉ cần dương để eventually catch up. Nếu producer vẫn gửi 150 records/s, nâng capacity lên 100/s **vẫn khiến lag tiếp tục tăng**, chỉ chậm hơn.

### 8.5. Bài học reliability

Trong production, latency một record có thể do:

- SQL query không có index, connection pool chờ.
- HTTP call tới remote API có p99 cao.
- Lock contention hoặc transaction kéo dài.
- GC pause vì object allocations.
- Deserialization hoặc business code nặng.
- Retry/backoff, circuit breaker hoặc poison message.
- DLT publish chậm.

Không sửa bằng cách tăng `max.poll.interval.ms` vô hạn; phải tìm latency source và giải quyết về capacity, timeout, retry budget, bulkhead hoặc asynchronous durable handoff.

---

## 9. Kịch bản 3: Pause container nhưng vẫn giữ group membership

### 9.1. Điểm khác biệt với stop

Spring Kafka hỗ trợ `MessageListenerContainer.pause()`. Yêu cầu pause có hiệu lực ở ranh giới poll; container vẫn tiếp tục các poll cần thiết để duy trì consumer group nhưng **không dispatch record mới** khi đã paused.

Điều này rất phù hợp để thử **backpressure có chủ đích**.

### 9.2. Các bước

Đầu tiên giảm delay:

```bash
curl -X POST "http://127.0.0.1:8080/lab/delay?ms=0"
```

Gửi yêu cầu pause:

```bash
curl -X POST "http://127.0.0.1:8080/lab/pause"
curl "http://127.0.0.1:8080/lab/status"
```

Chờ đến khi `containerPaused=true`. Nếu còn các record trong poll đang xử lý, container có thể xử lý xong số đó trước khi pause hoàn toàn.

Gửi thêm 2.000 record:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 2000 --record-size 128 --throughput 200 --producer-props bootstrap.servers=kafka:9092 acks=all
```

Quan sát:

- `LOG-END-OFFSET` tăng.
- `CURRENT-OFFSET` giữ gần như nguyên khi paused ổn định.
- `LAG` tăng tương ứng.
- Consumer vẫn có thể nằm trong group và giữ assignment.
- Nếu chờ đủ lâu, broker vẫn nhận heartbeats/polls theo hành vi container.

Sau đó resume:

```bash
curl -X POST "http://127.0.0.1:8080/lab/resume"
```

Quan sát lag giảm khi consumer xử lý lại.

### 9.3. Không nhầm pause với xử lý xong

Khi paused, không có nghĩa những record đã fetch được tự ack. Nếu pause diễn ra trong lúc đang xử lý một poll, còn các record in-flight; cần theo dõi `isContainerPaused` và counter.

Không tự gọi `KafkaConsumer.pause()` từ một HTTP thread khác: KafkaConsumer không thread-safe và Spring Kafka có API container an toàn hơn để yêu cầu pause/resume.

### 9.4. Khi nào pause có ích ở production?

- Một downstream service tạm quá tải nhưng dự kiến hồi phục sớm.
- Có kế hoạch bảo trì database ngắn, không muốn consumer group rebalance.
- Đang khống chế tốc độ consume theo circuit breaker.
- Cần tạm chặn ingestion trong lúc kiểm tra sự cố data correctness.

Điều kiện quan trọng: pause làm **lag tăng**; không được duy trì quá lâu mà không giám sát retention và SLA. Nếu muốn dừng hẳn service hoặc không thể giữ group membership, stop có thể phù hợp hơn.

---

## 10. Kịch bản 4: Stop consumer và restart

### 10.1. Thao tác

```bash
curl -X POST "http://127.0.0.1:8080/lab/stop"
```

Đợi container dừng rồi mô phỏng nguồn vẫn gửi data:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-producer-perf-test.sh --topic lag.lab.orders --num-records 1000 --record-size 128 --throughput 200 --producer-props bootstrap.servers=kafka:9092 acks=all
```

Consumer group không còn active member từ listener này; Kafka vẫn lưu committed offsets theo retention policy. Tùy CLI/version/trạng thái group, describe có thể hiện group state `Empty` và các offsets tồn tại, hoặc có output khác khi group chưa hình thành/đã expired.

Bắt đầu lại:

```bash
curl -X POST "http://127.0.0.1:8080/lab/start"
```

Kiểm tra `--members --verbose` và lag.

### 10.2. Stop khác pause ở đâu?

| Khía cạnh | Pause | Stop |
|---|---|---|
| Consumer container còn running? | Thường vẫn running | Không |
| Tiếp tục poll để duy trì group? | Có, theo cơ chế pause | Không sau khi dừng |
| Rebalance do hành động này? | Thường tránh được | Có thể xảy ra khi group member rời |
| Thời gian resume | Thường nhanh hơn | Cần start và join group |
| Lag khi producer tiếp tục | Tăng | Tăng |
| Phù hợp | Backpressure tạm ngắn | Dừng triển khai/maintenance lâu hơn |

Nếu có **hai replica cùng group**, stop một replica làm các partitions có thể chuyển sang replica còn lại; lúc này lag **không nhất thiết tăng ngay** vì consumer khác xử lý thay. Quan sát assignment thực tế mới giải thích được.

### 10.3. Không xóa committed offsets khi restart

Spring Kafka container start lại thông thường tiếp tục theo committed offsets của group. Nếu bạn đổi group ID trong lúc restart, đó là một **subscription group mới**, không còn cùng checkpoint; `auto.offset.reset` có thể khiến nó đọc lịch sử từ đầu hoặc chỉ dữ liệu mới.

Đừng dùng đổi group ID như một cách “dọn lag” ở production.

---

## 11. Kịch bản 5: Concurrency so với số partition

### 11.1. Công thức cơ bản

Với một topic có ba partitions, số consumer child thực tế trong một consumer group xấp xỉ:

```text
total consumers = replicas × concurrency per listener
```

Nhưng số consumers có thể xử lý record đồng thời cho topic không vượt số partitions được assignment:

```text
active consumers ≤ min(total consumers, topic partitions)
```

Ví dụ:

| Replicas | Concurrency mỗi pod | Tổng consumers | Tối đa consumers active trên 3 partitions |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 |
| 1 | 2 | 2 | 2 |
| 1 | 3 | 3 | 3 |
| 1 | 6 | 6 | 3 |
| 2 | 2 | 4 | 3 |
| 3 | 3 | 9 | 3 |

Đây là giả định chỉ một topic và một group; với nhiều topic hoặc assignor khác, partition assignment cần xem thực tế.

### 11.2. Tăng concurrency bằng cách restart ứng dụng

Dừng ứng dụng rồi chạy:

```bash
./gradlew bootRun --args='--spring.profiles.active=lag-lab --app.lab.concurrency=3 --app.lab.delay-ms=100'
```

Hoặc trên Windows:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=lag-lab --app.lab.concurrency=3 --app.lab.delay-ms=100"
```

Annotation `@KafkaListener(concurrency="...")` được resolve khi tạo container, nên không tự thay đổi bằng HTTP runtime `/lab/delay`. Restart với tham số cấu hình là cách đơn giản để có ba consumer threads trong lab.

### 11.3. Dự đoán trước khi đo

Với 100 ms/record:

- Concurrency 1: năng lực lý thuyết gần 10 records/s tổng.
- Concurrency 3, ba partitions có phân phối đều: gần 30 records/s tổng.
- Concurrency 6 nhưng chỉ ba partitions: không tự thành 60 records/s, do tối đa ba consumer nhận partitions.

Thực tế thấp hơn do commit, context switching, workload skew và tài nguyên broker/CPU. Nếu downstream là một DB chỉ xử lý tối đa 20 requests/s, tăng concurrency lên ba có thể gây queue/timeout thay vì tăng throughput.

### 11.4. Đo assignment

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --members --verbose
```

Kiểm tra:

- Có bao nhiêu member?
- Member nào có `#PARTITIONS=0`?
- Mỗi member được gán partitions nào?
- Lag tập trung ở partition nào?
- Tăng concurrency có làm throughput và catch-up ETA tốt hơn không?

### 11.5. Tăng partition count có giá của nó

Nếu cần vượt throughput tối đa ba partitions, có thể thiết kế topic với nhiều partitions hơn. Nhưng việc tăng partitions trên topic đang chạy có thể **thay đổi cách key được ánh xạ vào partition** cho những record mới, từ đó ảnh hưởng ordering của cùng business key nếu producer không có chiến lược partitioning ổn định.

Trong lab, dễ hơn là tạo một topic khác có sáu partitions và group mới rồi thử so sánh. Trong production, thay partition count là quyết định kiến trúc và phải test key distribution, ordering, retention, replay và downstream state.

---

## 12. Kịch bản 6: Partition skew / hot key

### 12.1. Lag không phân phối đều

Một topic có ba partitions và ba consumers nhưng producer gửi 90% event về cùng một key. Kafka partitioner thường đưa cùng key vào cùng partition; một consumer trở thành “hot”, hai consumer còn lại rảnh.

```text
producer keys:
   customer-A 90%
   customer-B  5%
   customer-C  5%
          │
          ▼
      Kafka topic
  ┌────────┬────────┬────────┐
  │ p0     │ p1     │ p2     │
  │ 9000   │ 500    │ 500    │
  └───┬────┴───┬────┴───┬────┘
      ▼        ▼        ▼
   Worker 1 Worker 2 Worker 3

Lag p0 ↑↑↑ trong khi p1/p2 gần 0
```

Tăng concurrency vượt ba threads không giúp vì một partition không được nhiều members trong cùng group xử lý song song theo ordering của Kafka.

### 12.2. Tạo dữ liệu có cùng key

Kafka console producer có chế độ parse key theo separator. Ví dụ ở PowerShell, gửi nhiều message dùng cùng key `hot`:

```powershell
1..1000 | ForEach-Object { "hot:event-$_" } | docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:9092 --topic lag.lab.orders --property parse.key=true --property key.separator=:
```

Producer này khác với perf test ở trên: nó có explicit key, phù hợp thí nghiệm skew. Nếu muốn tái lập đo chính xác hơn, viết một producer Java gửi `ProducerRecord<>(topic,"hot",payload)` và đợi kết quả gửi theo quota mong muốn.

### 12.3. Cách nhận biết

- Xem `LAG` từng partition, không chỉ total.
- Xem `--members --verbose` để biết partition thuộc consumer nào.
- So sánh processing latency giữa các partition.
- Kiểm tra business key distribution mà không log PII.
- Nếu hot key nằm tại một partition, tăng consumer instances không giải quyết tận gốc.

### 12.4. Hướng xử lý

- Nếu ordering theo key bắt buộc, cần tối ưu xử lý của key hot hoặc điều chỉnh domain partitioning.
- Nếu cho phép sharding business key, thiết kế key phân bố rộng hơn và xử lý ordering trong từng shard.
- Nếu có một event rất nặng, tách workload, batch xử lý riêng hoặc dùng durable async handoff.
- Giảm p99 latency và khóa/DB contention ở partition hot.
- Không đổi key bằng random mỗi event khi nghiệp vụ cần thứ tự cập nhật cùng aggregate.

---

## 13. Kịch bản 7: max.poll.interval.ms và rebalance

### 13.1. Tại sao consumer xử lý quá lâu gây rebalancing?

Kafka consumer cần gọi `poll()` đủ thường xuyên để chứng minh ứng dụng còn tiến triển. Với record listener đồng bộ, nếu một lần poll lấy nhiều records và xử lý mỗi record rất lâu, khoảng cách tới poll tiếp theo có thể vượt `max.poll.interval.ms`.

Ví dụ cấu hình riêng cho thí nghiệm:

```yaml
spring:
  kafka:
    consumer:
      max-poll-records: 20
      properties:
        max.poll.interval.ms: 10000

app:
  lab:
    delay-ms: 800
```

Ước lượng:

```text
20 records × 800 ms = 16 seconds
max.poll.interval.ms = 10 seconds
```

Khi gặp poll chứa đủ 20 records và xử lý lần lượt, thời gian có thể vượt giới hạn. Consumer group có thể rebalance/thu hồi partitions; offset commit sau đó có thể thất bại, record được giao lại, khiến duplicate attempts và lag tăng bất thường.

**Quan trọng:** đây là một tình huống fault-injection **chỉ trong môi trường lab**, tách khỏi baseline 5 phút. Không đặt cấu hình này cho ứng dụng production hoặc group đang xử lý dữ liệu quan trọng.

### 13.2. Quan sát

Theo dõi:

- Log Kafka client liên quan rebalance, member leaves group, poll interval exceeded.
- Kafka consumer group state và member count.
- LAG thay đổi chậm hoặc nhảy bất thường.
- Processing counter có tiếp tục tăng nhưng committed offset đứng yên?
- Có duplicate delivery sau khi partitions chuyển assignment không?

Một consumer có thể xử lý record trong business code nhưng commit bị từ chối khi không còn ownership partition. **Processed log không đồng nghĩa offset đã commit.**

### 13.3. Cách sửa đúng

- Đo latency p95/p99 của business method.
- Giới hạn blocking HTTP/DB timeout.
- Giảm `max.poll.records` để mỗi poll cần ít thời gian xử lý hơn.
- Tăng concurrency **trong giới hạn partition và downstream capacity**.
- Với outage dài, dùng retry/backoff phù hợp, pause hoặc xử lý bất đồng bộ qua durable queue.
- Cân nhắc tăng `max.poll.interval.ms` có giới hạn khi workload thực sự cần thời gian dài; phải cân bằng thời gian nhận biết consumer kẹt.
- Thiết kế idempotency vì rebalance/crash có thể gây redelivery.

### 13.4. Không nhầm max.poll.interval.ms với session.timeout.ms

- `max.poll.interval.ms` liên quan tiến triển xử lý ở tầng ứng dụng giữa các poll.
- `session.timeout.ms` liên quan consumer group session/heartbeat; broker xác định member mất kết nối.
- `heartbeat.interval.ms` ảnh hưởng nhịp heartbeat trong group protocol phù hợp.
- `pollTimeout` của Spring Kafka chỉ là thời gian một lần `poll()` đợi dữ liệu.

Các tham số khác nhau. Không sửa một tham số bất kỳ khi chưa xác định triệu chứng.

---

## 14. Phân biệt bốn kiểu backlog bằng số đo

| Quan sát | Khả năng thường gặp | Kiểm chứng tiếp |
|---|---|---|
| Log end tăng, committed cũng tăng nhưng chậm | Consumer thiếu capacity | Rate input/output, latency, partitions |
| Log end tăng, committed đứng yên, group có member | Pause, poison record, retry dài, block | Pause state, logs, consumer threads |
| Log end tăng, group không có active member | Consumer đã stop/crash, deploy sai | Registry/pod health/group state |
| Một partition lag rất cao, partitions khác thấp | Key skew hoặc record nặng | Per-partition lag/assignment/key distribution |
| Lag dao động mạnh, nhiều rebalances | Poll interval, pod churn, network/broker | Rebalance logs, CPU/GC, deployments |
| Lag 0 nhưng DB thiếu records | Ack quá sớm, filter/drop, DLT, business failure bị nuốt | Transaction, dedup, DLT, reconciliation |
| Lag không giảm dù tăng concurrency | Partitions ít, downstream bottleneck | Active members, DB/API throughput |
| Lag tăng sau restart | Reprocessing/uncommitted records | Offset commits, error handler, idempotency |

**Đây là ma trận định hướng**, không phải chẩn đoán tự động. Ví dụ committed offset đứng yên cũng có thể do một transaction Kafka đang chờ commit hoặc listener xử lý batch dài, không chỉ do pause.

---

## 15. Ước lượng thời gian catch-up

### 15.1. Công thức cơ bản

Khi backlog dương, nếu producer rate `λ` và group commit rate `μ` đều ổn định:

```text
Nếu μ > λ:
    catchUpSeconds ≈ L / (μ - λ)

Nếu μ ≤ λ:
    backlog không hội tụ về 0 theo mô hình này
```

Ví dụ backlog 18.000 records:

| Producer rate | Consumer commit rate | Net drain | ETA |
|---:|---:|---:|---:|
| 0/s | 300/s | 300/s | 60 giây |
| 100/s | 300/s | 200/s | 90 giây |
| 200/s | 300/s | 100/s | 180 giây |
| 300/s | 300/s | 0/s | Không giảm |
| 400/s | 300/s | -100/s | Tiếp tục tăng |

Các phép tính minh họa giả định rates giữ ổn định, không có partition skew, retry storm hoặc rebalancing.

### 15.2. Vì sao không được lấy throughput lúc topic rỗng?

Khi không có backlog, consumer dù có khả năng xử lý 10.000 records/s nhưng nếu producer chỉ gửi 10/s, dashboard chỉ quan sát thấy 10/s. Lấy observed consumed rate=10/s để suy capacity sẽ sai.

Nên benchmark khi có backlog kiểm soát, đo stable processing throughput và xác định bottleneck của từng partition. Không dùng benchmark producer perf test để suy throughput business listener khi payload/DB operation khác hoàn toàn.

### 15.3. Committed rate không giống processed counter

App demo có `lag.lab.processed` tăng mỗi khi method hoàn thành, còn Kafka group offset commit có thể đến sau theo policy. Nếu commit lỗi, số method successes có thể tăng nhưng group lag chưa giảm.

Với `AckMode.RECORD`, độ lệch thường nhỏ khi bình thường. Với `AckMode.BATCH`, `MANUAL`, transaction hoặc retry, khác biệt có thể lớn hơn. Khi điều tra, đo **cả processed rate và committed offset rate**.

---

## 16. Giám sát bằng Kafka CLI một cách có hệ thống

### 16.1. Xem offsets

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --offsets
```

`--offsets` là chế độ describe offsets; tùy phiên bản có thể bỏ flag vì nó thường là mặc định.

### 16.2. Xem member assignments

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --members --verbose
```

### 16.3. Xem trạng thái consumer group

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group lag-lab-v1 --state
```

Những trạng thái thường thấy có `Stable`, `PreparingRebalance`, `CompletingRebalance` hoặc `Empty` (phụ thuộc group protocol/phiên bản). Group `Empty` không tự đồng nghĩa xóa committed offsets.

### 16.4. Lấy snapshot theo thời gian

Cần lưu timestamp và kết quả CLI mỗi 5–10 giây. Một thí nghiệm tốt có ít nhất:

- Mốc producer bắt đầu.
- Mốc producer kết thúc.
- Mốc thay delay/concurrency/pause.
- Mốc lag đạt đỉnh.
- Mốc lag giảm về ngưỡng mục tiêu.

Đừng chỉ chụp một lần khi lag cao rồi kết luận “consumer bị kẹt”: **xu hướng** mới cho biết consumer có đang catch up không.

### 16.5. Cẩn thận với group mới

Nếu đổi group ID từ `lag-lab-v1` sang `lag-lab-v2` và `auto.offset.reset=earliest`, group mới có thể đọc toàn bộ dữ liệu còn retention. Lag ban đầu của group v2 có thể rất lớn, dù group v1 không có vấn đề.

Nếu group mới dùng `latest`, nó có thể bỏ qua lịch sử hiện có. Đổi ID để giảm con số lag không phải khắc phục backlog nghiệp vụ.

---

## 17. Quan sát qua Micrometer và Spring Boot Actuator

### 17.1. Metrics của listener demo

Code tạo:

- `lag.lab.processed`: Counter tăng khi listener hoàn tất.
- `lag.lab.processing.duration`: Timer đo thời gian callback.

Với Prometheus registry, tên series thường được chuẩn hóa (ví dụ underscore và hậu tố `_total`, `_seconds_count`, `_seconds_sum`), nên cần xem output thực:

```bash
curl http://127.0.0.1:8080/actuator/prometheus
```

Không giả định mọi Kafka metric hiển thị giống nhau giữa các phiên bản Micrometer/Spring Kafka. Dùng `/actuator/metrics` để xem tên meter đã đăng ký.

### 17.2. Consumer client metrics

Một số Kafka client metrics quan trọng gồm:

- `records-consumed-rate`.
- `records-lag-max`.
- `fetch-rate`/fetch latency.
- `commit-rate`/commit latency nếu có.
- `assigned-partitions`.
- Rebalance-related metrics trong Kafka client/version phù hợp.

Cần phân biệt `records-lag-max` do Kafka client đo ở tầng fetch **không nhất thiết giống** group committed-offset lag từ AdminClient hoặc consumer group exporter. Chúng có cách cập nhật và semantics khác nhau; dùng đúng metric cho từng câu hỏi.

### 17.3. Metrics vận hành cần có

| Metric | Đo ở đâu | Câu hỏi |
|---|---|---|
| Group committed offset lag / partition | Kafka exporter/AdminClient | Group còn bao xa so với end offsets? |
| Lag oldest-event age | Application/exporter/custom | Record lâu nhất đang trễ bao nhiêu? |
| Producer append rate | Broker/producer metrics | Nguồn tạo tải nhanh thế nào? |
| Consumer records consumed/commit rate | Kafka client + group offsets | Có tiến triển thật không? |
| Listener processing p95/p99 | Micrometer | Business code chậm ở đâu? |
| Retry and DLT rate | Spring Kafka error handler/metrics | Có poison message/outage? |
| Rebalance count/duration | Kafka client metrics/logs | Group có ổn định? |
| DB latency and pool wait | Hikari/JDBC metrics | Bottleneck downstream? |
| CPU, heap, GC, throttling | JVM/container | Worker có thiếu tài nguyên? |
| Container pause/stop state | Spring Kafka registry/events | Tạm dừng có chủ đích hay lỗi? |
| Business reconciliation count | DB/side-effect state | Đã thực sự cập nhật đủ dữ liệu? |

Không đưa raw orderId, email hoặc message payload vào metric labels; cardinality cao và có thể lộ thông tin. Tags nên là cluster, topic, group, partition, service, environment và loại lỗi với số lượng giá trị hữu hạn.

### 17.4. Idle không đồng nghĩa lag bằng 0

Spring Kafka có `ListenerContainerIdleEvent`, phát khi không có message được giao trong một khoảng thời gian. Nhưng:

- Topic có thể thực sự không có dữ liệu.
- Container có thể paused.
- Listener khác trong group đang nhận partitions.
- Deserializer hoặc poll loop có thể lỗi.
- Khi broker không kết nối được, một số cơ chế event có behavior khác.

Vì vậy idle event chỉ là tín hiệu phụ. Kết hợp consumer-group lag và end offset để xác định có backlog hay không.

### 17.5. NonResponsiveConsumerEvent

Spring Kafka có `NonResponsiveConsumerEvent` khi poll được phát hiện không phản hồi theo monitor. Khác với listener idle, event này nhắm tới tình huống vòng poll không tiến triển trong thời gian bất thường.

Nếu dùng `ContainerProperties.setMonitorInterval(...)` và `setNoPollThreshold(...)`, phải hiệu chỉnh dựa trên `pollTimeout` và workload. Một event không xác định chính xác root cause; cần thread dump, GC, network và logs.

---

## 18. Phản ứng vận hành khi lag tăng

### 18.1. Cách chọn hành động theo nguyên nhân

| Nguyên nhân | Hành động ưu tiên | Điều không nên làm |
|---|---|---|
| Producer burst theo kế hoạch | Theo dõi ETA và SLA, đợi drain nếu đủ capacity | Khẩn cấp đổi group ID |
| Listener cố ý pause | Kiểm tra lý do, resume khi dependency ready | Resume mù quáng khi DB vẫn lỗi |
| Consumer stop/crash | Khởi động lại đúng version/credential | Reset offsets sang latest |
| DB/API chậm | Tìm p99, pool, timeout và rate limit | Chỉ tăng consumer concurrency |
| Partition skew | Tối ưu hot key/partition strategy | Tăng threads vượt partitions |
| Poison message retry vô hạn | Classify exception, DLT/recovery có kiểm soát | Skip tất cả exceptions |
| Rebalance vì poll quá lâu | Giảm poll batch/latency, điều chỉnh interval | Tăng interval vô hạn |
| Consumer lag 0 nhưng DB thiếu | Reconciliation, idempotency, ack timing | Tin số 0 là success |
| Broker/network issue | Kiểm tra cluster health, leader, request timeouts | Gửi thêm producer burst |
| Retention sắp hết | Ưu tiên bảo toàn/replay dữ liệu đúng quyền | Xóa dữ liệu hoặc reset group bừa bãi |

### 18.2. Kiểm tra năng lực xử lý trước khi scale

Một quyết định scale nên được hỗ trợ bằng:

1. Số partitions đang có.
2. Số active consumer threads.
3. Incoming events/s theo partition.
4. Thời gian xử lý p95/p99 mỗi record.
5. DB/API capacity và connection pool.
6. Retry/DLT rate.
7. CPU/GC/network utilization.
8. ETA catch-up sau khi scale.

Nếu vấn đề là DB chỉ chịu 50 writes/s, nâng từ 2 lên 20 consumers có thể làm timeout, tăng retries và **lag tệ hơn**.

### 18.3. Không bỏ qua data correctness khi giảm lag

Hai hệ thống có thể cùng báo lag=0 nhưng khác chất lượng:

- Hệ A commit offset sau DB transaction thành công.
- Hệ B catch DB exception, log rồi return bình thường.

Hệ B “hết lag” bằng cách bỏ mất business processing. Vì vậy khi làm production incident, phải xem thêm tổng output, dedup count, side-effect success và records đi DLT.

---

## 19. Cảnh báo consumer lag theo SLO

### 19.1. Đặt ngưỡng theo thời gian

Một SLO có thể là “95% đơn hàng được phản ánh trên hệ thống đích trong vòng 2 phút”. Khi đó chỉ alert dựa trên `LAG > 10.000` là yếu: 10.000 records có thể được xử lý trong vài giây ở hệ mạnh hoặc vài giờ ở hệ yếu.

Nên cân nhắc:

- **Backlog age:** tuổi của record lâu nhất chưa được xử lý/commit.
- **Catch-up ETA:** ước lượng khi backlog về ngưỡng bình thường.
- **Rate imbalance:** tốc độ lag tăng liên tục nhiều chu kỳ.
- **No-progress detection:** committed offsets không thay đổi khi có backlog.
- **Error/DLT anomaly:** tỷ lệ lỗi tăng dù lag vẫn giảm.

### 19.2. Alert mẫu

Đây là ngưỡng **minh họa**, cần điều chỉnh theo thực tế:

| Alert | Điều kiện | Ý nghĩa |
|---|---|---|
| Warning | Lag tăng liên tục 10 phút | Group không theo kịp producer |
| Critical | No committed progress 5 phút khi end offset tăng | Có thể pause/block/poison |
| Warning | Catch-up ETA > 30 phút | Nguy cơ vi phạm SLA |
| Critical | Oldest unprocessed age > business deadline | SLA đã bị ảnh hưởng |
| Critical | DLT publish failed | Recovery có nguy cơ mất dữ liệu |
| Warning | Rebalance count tăng bất thường | Membership thiếu ổn định |
| Critical | Consumer group không có active members khi phải chạy | Service down/misconfigured |

Điều kiện `no-progress` cần phân biệt traffic rất thấp, group chưa có offset, topic không có data và planned pause đã được khai báo. Alert phải có link runbook chứ không chỉ một con số.

---

## 20. Offset reset: nội dung nguy hiểm cần hiểu nhưng không dùng để che lag

Kafka CLI có tùy chọn `--reset-offsets`. Đây là thao tác **thay committed position của một consumer group**, không phải một cách làm consumer xử lý nhanh hơn.

### 20.1. Những hậu quả

- Reset sang latest có thể **bỏ qua record chưa xử lý**.
- Reset sang earliest có thể tạo replay lớn và duplicate side effect.
- Reset theo timestamp có thể bỏ sót hoặc xử lý lại nhiều event tùy timestamp/retention.
- Reset khi group đang active thường không được phép; cần dừng consumer theo quy trình.
- Với topic compacted/retention, những offset cũ có thể không còn dữ liệu.

### 20.2. Chỉ preview trong lab

Lệnh **không thực thi thay đổi**:

```bash
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --group lag-lab-v1 --topic lag.lab.orders --reset-offsets --to-earliest --dry-run
```

`--dry-run` chỉ xem các offsets dự kiến. Nếu cần thực sự reset trong một bài tập riêng, dùng consumer group lab đã dừng, snapshot committed offsets trước, hiểu `--execute` làm gì, rồi kiểm tra business replay. Bài thực hành mô phỏng lag **không yêu cầu thực hiện reset thật**.

### 20.3. Không reset offset khi chưa biết outcome

Trong hệ thống thanh toán hoặc order fulfillment, một số records có thể đã cập nhật DB nhưng chưa commit Kafka offset; reset sang earliest có thể gửi lặp, reset sang latest có thể làm mất nghĩa vụ còn pending. Phải có dedup, reconciliation và phê duyệt vận hành trước mọi thao tác.

---

## 21. Error handler, DLT và “lag bị kẹt một offset”

### 21.1. Poison record

Một record không thể deserialize hoặc không đạt validation có thể làm listener fail liên tục. Nếu error handler retry vô hạn, partition đó không tiến. Các partition khác có thể vẫn chạy, nên total lag tăng theo phân phối không đều.

```text
Topic partition 1:
  offset 100: OK
  offset 101: BAD_JSON  ◄─ retry mãi
  offset 102: OK
  offset 103: OK
  ...
```

Một poison record có thể gây **head-of-line blocking**. Nếu tăng concurrency nhưng topic partition 1 vẫn chỉ có một owner, backlog trên partition đó tiếp tục tăng.

### 21.2. Tách lỗi transient và permanent

- Transient: DB timeout, HTTP 503 hoặc rate limit có thể hồi phục → retry hữu hạn + backoff.
- Permanent: JSON/schema sai, vi phạm business rule không thể tự sửa → DLT/quarantine theo hợp đồng.
- Infrastructure: mất broker auth, topic ACL hoặc deserializer configuration → xử lý vận hành, không “skip tất cả”.

### 21.3. DLT không đồng nghĩa business thành công

Khi record được publish vào DLT và source offset được commit theo recovery policy, lag trên main topic có thể giảm, nhưng event lỗi vẫn **chưa xử lý nghiệp vụ**. Cần:

- DLT topic retention và ACL đúng.
- Monitoring số records cần triage/replay.
- Khóa idempotency ổn định khi replay.
- Quy trình xác nhận DLT send success trước khi coi là recovered.
- Alert khi số pending DLT tăng hoặc quá SLA.

Một dashboard chỉ có main-topic lag có thể không phản ánh backlog của workflow phục hồi.

---

## 22. Thử nghiệm redelivery và idempotency

### 22.1. Vì sao consumer lag liên quan duplicate side effect?

Đọc Kafka và commit business database thường không có chung một distributed transaction mặc định:

```text
poll record
    │
    ▼
update DB
    │
    ▼
DB COMMIT thành công
    │
    ▼
consumer crash trước Kafka offset commit
    │
    ▼
consumer restart → redeliver same record
```

Nếu service ghi tăng số dư, gửi email hoặc gọi payment API mà không có idempotency, lần redelivery có thể tạo side effect lần hai.

### 22.2. Business idempotency key

Trong production có thể dùng `eventId` ổn định hoặc business transaction ID. Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_events (
    consumer_group VARCHAR(120) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_group, event_id)
);
```

Trong cùng DB transaction:

```java
@Transactional
public void apply(OrderEvent event) {
    boolean firstTime =
            processedEventRepository.tryInsert(
                    "orders-worker",
                    event.eventId());

    if (!firstTime) {
        return;
    }

    orderRepository.applyBusinessChange(event);
}
```

Hai thao tác phải dùng **cùng transaction DB**. Nếu insert dedup marker commit nhưng business change fail, redelivery có thể bị bỏ sai. Bài lab sleep không có DB side effect, nên quan sát duplicate delivery là an toàn; không suy ra code production sẽ tự an toàn.

### 22.3. Khi nào offset lag có thể khác progress của DB?

- Commit offset trước khi DB thành công.
- DB commit thành công nhưng offset commit fail.
- Listener xử lý async rồi return sớm.
- Batch listener đã poll nhiều records và commit theo batch boundary.
- Consumer transactional producer offset semantics khác non-transactional.
- Một số records đi DLT/recovery mà chưa được business xử lý.

Vì vậy phải reconcile key counts và status, không chỉ `CURRENT-OFFSET`.

---

## 23. Kiểm thử Spring Kafka cho các kịch bản lag

### 23.1. Integration test với EmbeddedKafka

Spring Kafka cung cấp `spring-kafka-test` và `@EmbeddedKafka`. Mục tiêu của test:

- Listener đăng ký đúng group/topic.
- Khi delay tăng, throughput giảm.
- Pause container khiến processed counter ngừng tăng sau khi các in-flight records hoàn tất.
- Resume khiến counter tiếp tục.
- Khi gửi records đủ nhiều, committed offset cuối cùng bắt kịp log end.
- Stop/start không làm group đổi ID ngoài ý muốn.
- Không có dữ liệu bị mất theo fixture.

Skeleton:

```java
@SpringBootTest(
    properties = {
        "spring.profiles.active=lag-lab",
        "app.lab.topic=lag.lab.orders",
        "app.lab.group-id=lag-lab-test",
        "server.port=0"
    })
@EmbeddedKafka(
    partitions = 3,
    topics = "lag.lab.orders",
    bootstrapServersProperty =
            "spring.kafka.bootstrap-servers")
class LagLabIntegrationTest {

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void listenerIsRegistered() {
        var container =
                registry.getListenerContainer(
                        "lag-lab-consumer");

        assertNotNull(container);
    }
}
```

Imports chính:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.context.EmbeddedKafka;
```

Test skeleton chỉ kiểm tra bean/container registration, **chưa chứng minh lag behavior**. Để test offset lag, cần gửi message thật, query committed offsets/log end bằng Kafka AdminClient/consumer group API và chờ asynchronous delivery với timeout rõ ràng.

### 23.2. Awaitility/eventual assertion

Với consumer bất đồng bộ, không nên:

```java
Thread.sleep(100);
assertEquals(100, listener.getProcessed());
```

vì thời gian startup/poll không xác định. Dùng Awaitility hoặc một cơ chế polling đến deadline:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() ->
        assertEquals(100, listener.getProcessed()));
```

Nếu dùng Awaitility, thêm test dependency tương ứng. Khi test nhiều lần trong cùng context, reset/capture baseline counter để tránh số tích lũy từ test khác.

### 23.3. Test pause/resume

Quy trình:

1. Gửi warm-up records và đợi commit.
2. Yêu cầu `pause()`, đợi `isContainerPaused() == true`.
3. Gửi thêm 100 records.
4. Xem committed offset đứng yên trong cửa sổ đo.
5. Gọi `resume()` và đợi tất cả records được xử lý/commit.
6. Xác nhận không có error/rebalance ngoài dự kiến.

**Không assert ngay rằng pause() đồng bộ làm counter đứng yên**, vì các record đã có trong poll hoặc callback in-flight có thể hoàn tất.

### 23.4. Test processing delay và capacity

- Chạy 1 consumer, delay 100 ms, gửi 200 records.
- Đo thời gian xử lý 200 records và committed rate.
- Chạy lại trong môi trường cô lập với concurrency 3, ba partitions, phân phối keys đủ đều.
- So sánh throughput, không mặc định tăng đúng ba lần.
- Đo JVM CPU/GC/network và broker send throughput để loại trừ bottleneck khác.

### 23.5. Test rebalance và failover

- Khởi động hai instances chung group trên topic ba partitions.
- Cho một instance stop/crash có kiểm soát.
- Quan sát assignments chuyển sang instance còn lại.
- Kiểm tra không bị mất record trong lab.
- Nếu thêm DB side effect, xác nhận idempotency trên các records redelivered.
- Đảm bảo group ID và topic subscription không bị thay khi rolling deploy.

### 23.6. Test hot partition

- Gửi hàng trăm records cùng key `hot`.
- Ghi nhận partition thực tế của key qua producer metadata hoặc consumer log.
- Xác nhận lag chủ yếu tăng ở một partition.
- Tăng concurrency vượt partitions và thấy bottleneck của hot partition không biến mất.
- Thử tối ưu processing hoặc thay chiến lược partition theo yêu cầu ordering.

### 23.7. Test lỗi dùng DLT

- Gửi payload không hợp lệ và cấu hình error handler có retry hữu hạn.
- Kiểm tra lag main topic có thể giảm khi record được recover DLT.
- Xác minh DLT có record và workflow replay.
- Giả lập DLT broker/ACL failure để tránh “recover thành công giả”.
- Test không duplicate business side effect qua redelivery.

---

## 24. Runbook vận hành: khi nhận cảnh báo consumer lag

### Bước 1 — Xác định phạm vi và tác động

Ghi lại:

```text
environment:
cluster:
topic:
consumerGroup:
alertTimeUtc:
businessSla:
totalLag:
maxPartitionLag:
oldestEventAge:
activeGroupMembers:
deployVersion:
```

Không chỉ lấy total lag; kiểm tra partition nào bị ảnh hưởng và dữ liệu nghiệp vụ đang bị trễ trong bao lâu.

### Bước 2 — Xác định tốc độ đang diễn ra

Đo hai hoặc ba snapshots cách nhau 30–60 giây:

- Log end có tăng không?
- Current committed offset có tiến không?
- Lag có tăng/giảm/đứng yên?
- Group có member active?
- Processing latency p99 và retries có tăng?
- DLT/backlog recovery có tăng?

Nếu lag giảm với ETA chấp nhận được, có thể chưa cần can thiệp khẩn cấp.

### Bước 3 — Kiểm tra topology

- Consumer group ID đúng chưa?
- Assignment có active như mong đợi?
- Số consumer threads có nhiều hơn partitions không?
- Một partition có hot key không?
- Pod có CPU throttling, OOM, restart hoặc GC pause không?
- Có rebalance thường xuyên không?
- Có người đang intentional pause container không?

### Bước 4 — Tìm bottleneck

Tách ba nhóm:

1. **Upstream:** producer burst hoặc producer đã tăng rate.
2. **Consumer:** deserialization, processor, retry, batch size, offset commit.
3. **Downstream:** DB/API/cache/storage rate limit, lock, network.

Không tăng concurrency trước khi biết downstream chịu được tải thêm.

### Bước 5 — Chọn recovery

- Planned pause: xác nhận dependency khỏe rồi resume.
- Consumer crash: restore service và đảm bảo group membership.
- Slow DB/API: giảm latency, tăng capacity hoặc giới hạn request.
- Producer burst: nếu backlog nằm trong SLA, theo dõi drain.
- Hot partition: điều chỉnh partition key strategy/worker model có kiểm soát.
- Poison message: retry hữu hạn, DLT/quarantine theo policy.
- Long processing: giảm poll size hoặc xử lý theo kiến trúc khác.
- Retention risk: kích hoạt bảo toàn và replay dữ liệu theo quyền, không reset offset bừa bãi.

### Bước 6 — Xác minh phục hồi

Đóng incident chỉ khi:

- Lag giảm về mức mục tiêu và ổn định.
- Oldest-event age nằm trong SLA.
- Consumer members/assignments ổn định.
- Retries, DLT và lỗi DB giảm.
- Dữ liệu nghiệp vụ được đối soát đủ.
- Không còn những records “đã commit offset nhưng chưa thực thi business effect”.

### Bước 7 — Ghi nhận phòng ngừa

Lưu incident timeline: producer rate, commits/s, peak lag, time to catch up, root cause, canary/rollback actions, resource limits và quyết định cải tiến. Thêm load/recovery tests để bảo đảm sự cố không tái diễn.

---

## 25. Bảng chẩn đoán nhanh

| Triệu chứng | Điều cần kiểm tra đầu tiên | Hành động phù hợp |
|---|---|---|
| `CURRENT-OFFSET=-` | Group đã từng commit chưa? | Tạo baseline, kiểm tra reset policy |
| Lag tăng đều | Incoming rate > committed rate? | Đo capacity và bottleneck |
| Lag không đổi dù producer dừng | Consumer paused/blocked/retrying? | Registry, logs, thread dump |
| Lag tập trung một partition | Key skew/hot partition? | Assignment và producer keys |
| Lag tăng sau deploy | Group ID/offset policy/exception thay? | Diff config, rebalance |
| Lag=0 nhưng dữ liệu thiếu | Ack quá sớm, DLT hoặc swallowed exception? | Business reconciliation |
| Consumer “running” nhưng không poll | max.poll.interval, blocking method? | No-poll event, thread dump |
| DLT có nhiều records | Permanent validation/schema/infra? | Triage, fix, replay |
| Mỗi restart replay nhiều | Offset commit quá thưa/crash trước commit | Ack timing, idempotency |
| Tăng concurrency không giảm lag | Partitions/DB capacity? | Active member/partition check |
| Lag tăng khi DB failover | Retry/backoff, connection pool | Cấp lại DB, throttling |
| Producer tool đạt rate thấp | Broker/host giới hạn | Đo actual producer throughput |
| Không thấy topic từ Spring Boot | Kafka advertised.listeners sai | Host/container listener config |
| Describe group không có member | Container stopped/group empty | App status và topic assignment |

---

## 26. Các sai lầm dễ làm kết quả lab sai

### 26.1. Nhầm committed offset với consumer position

Consumer position có thể tiến vì đã fetch/poll records, còn committed offset chưa tiến. `kafka-consumer-groups.sh` cho biết committed progress theo group. Khi đo business throughput, phải xem application-side successful processing bên cạnh offset commits.

### 26.2. Dùng auto-commit trong bài học về reliability

Nếu bật `enable.auto.commit=true`, offset có thể được commit theo timer dù business code chưa hoàn tất. Lag giảm không chứng minh xử lý dữ liệu thành công. Bài đặt `enable.auto.commit=false` và `AckMode.RECORD` để minh họa rõ hơn.

### 26.3. Test trên group chưa từng commit offset

Một group mới có thể báo dấu `-` hoặc không có committed state; kết luận lag=0 là sai. Luôn warm-up để baseline có committed offsets hoặc ghi rõ đây là group mới chưa commit.

### 26.4. Gửi tải vô hạn

Producer burst nên có `--num-records` và `--throughput` rõ, dùng broker local. Không chạy producer loop vô hạn vì có thể làm đầy disk, tăng retention pressure và ảnh hưởng máy học viên.

### 26.5. Dùng payload production

Không dùng thông tin khách hàng, thẻ thanh toán hoặc access token để đo throughput. Kafka log có thể giữ payload nhiều ngày và broker lab không có bảo vệ production.

### 26.6. Đổi group ID để “hết lag”

Group ID mới có offsets riêng. Nếu đặt reset=latest, số lag có thể nhỏ vì đã bỏ qua dữ liệu quá khứ, không phải vì consumer xử lý nhanh hơn.

### 26.7. Tăng concurrency vượt số partitions

Số consumer active không thể vượt số partitions cho một topic trong cùng group. Phần concurrency vượt mức có thể idle nhưng vẫn tiêu thụ resource và gây phức tạp vận hành.

### 26.8. Chỉ nhìn total lag

Total lag 10.000 có thể trải đều trên mười partitions hoặc dồn hết vào một partition. Khả năng scale và catch-up khác nhau hoàn toàn.

### 26.9. Tăng max.poll.interval.ms mà không sửa processing

Cấu hình này có thể giảm rebalances do xử lý lâu nhưng cũng kéo dài thời gian phát hiện consumer thực sự kẹt. Phải kết hợp timeout, batch size, circuit breaker và alerts.

### 26.10. Xem pause và stop như nhau

Pause giữ polling/group theo cơ chế container; stop dừng membership. Hai thao tác tạo profile rebalance/lag khác nhau và phải được test tách biệt.

### 26.11. Chỉ so sánh số log "processed"

Log có thể được ghi trước transaction commit, hoặc mỗi listener invocation bị redeliver nhiều lần. Để đánh giá độ tin cậy, cần committed offset và business state.

### 26.12. Tắt lỗi bằng DLT rồi coi là success

DLT có ích để giữ poison record, nhưng các event đó vẫn cần xử lý sau. Lag topic chính bằng 0 không đồng nghĩa toàn bộ nghĩa vụ nghiệp vụ đã hoàn thành.

---

## 27. Mẫu bảng kết quả thực hành

Khi chạy lab, điền **số thực đo**, không chép các ước lượng lý thuyết.

| Scenario | Input record count | Producer measured r/s | Consumer concurrency | Delay ms | Peak lag | Catch-up time | Rebalance count |
|---|---:|---:|---:|---:|---:|---|---:|
| Baseline | Đo | Đo | 1 | 0 | Đo | Đo | Đo |
| Burst | 6.000 | Đo | 1 | 0 | Đo | Đo | Đo |
| Slow listener | 1.200 | Đo | 1 | 100 | Đo | Đo | Đo |
| Slow + 3 consumers | 1.200 | Đo | 3 | 100 | Đo | Đo | Đo |
| Pause | 2.000 | Đo | 1 | 0 | Đo | Đo | Đo |
| Stop/start | 1.000 | Đo | 1 | 0 | Đo | Đo | Đo |
| Hot key | 1.000 | Đo | 3 | 100 | Đo per partition | Đo | Đo |
| Poll interval fault | Đo | Đo | 1 | 800 | Đo | Đo | Đo |

Đi kèm môi trường:

```text
Kafka version:
Spring Boot version:
Spring Kafka version:
JVM version:
OS/Docker resource limits:
Topic partitions:
Consumer group:
Producer payload size:
Consumer max.poll.records:
Consumer max.poll.interval.ms:
AckMode:
Date/time and timezone:
```

Cần điều này để so sánh các lần thực hành đáng tin cậy. Nếu không ghi payload size, CPU/disk giới hạn hoặc group ID, rất dễ kết luận sai rằng một thay đổi config đã tăng throughput.

---

## 28. Bài tập nâng cao

### Bài 1 — Tính toán lag rate

Producer 800 records/s, group xử lý 500 records/s trong 10 phút. Ước lượng lag tăng và thời gian cần để drain nếu producer dừng và group vẫn xử lý 500/s. Đối chiếu với công thức ở mục 2.

### Bài 2 — ETA dưới tải liên tục

Backlog 120.000 records, producer tiếp tục gửi 200/s, consumer xử lý 500/s. Tính ETA. Khi consumer throughput giảm còn 180/s vì DB bottleneck, giải thích vì sao backlog không hội tụ.

### Bài 3 — Pause và stop

Dùng cùng số record đầu vào, đo lag và số rebalance sau khi pause/resume so với stop/start. Tại sao planned maintenance ngắn có thể ưu tiên pause?

### Bài 4 — Số consumer active

Topic ba partitions, chạy một replica concurrency 1, 2, 3, 6. Ghi số members, assignments và tốc độ tiêu thụ. Giải thích tại sao concurrency 6 không tạo sáu consumer active.

### Bài 5 — Hot partition

Gửi 90% records với cùng key, chạy ba consumers. Lập bảng per-partition lag. Đề xuất giải pháp không phá business ordering.

### Bài 6 — Poll interval

Với `max.poll.records=100`, p99 processing latency 500 ms, retry/backoff có thể mất thêm 90 giây, tính thời gian per-poll bảo thủ. Chọn `max.poll.interval.ms` và phương án giảm rủi ro rebalancing.

### Bài 7 — Lag 0 nhưng side effect thiếu

Sửa một listener test để catch DB exception rồi return bình thường. Theo dõi offset tiến nhưng DB không có record. Sửa listener để propagate exception và thêm idempotency; giải thích khác biệt.

### Bài 8 — Poison pill

Thêm JSON event sai schema và `DefaultErrorHandler` có giới hạn retry + DLT. Chứng minh main-topic lag giảm sau recover nhưng DLT có pending item cần triage.

### Bài 9 — Monitoring

Thiết kế dashboard gồm group lag, max partition lag, lag age, consumed rate, processing p99, retry/DLT, rebalances và DB pool. Xác định alert cho “lag tăng nhưng group vẫn running”.

### Bài 10 — Rolling deploy

Triển khai hai replicas cùng group trong môi trường thử nghiệm, stop lần lượt từng replica. Quan sát assignment, rebalance và duplicate delivery; đưa ra yêu cầu idempotency cho business writer.

### Bài 11 — Capacity planning

Cho một topic 12 partitions, producer rate 1.200/s, p99 xử lý mỗi record 20ms, downstream chịu tối đa 600 requests/s. Tính số consumers lý thuyết cần, xác định bottleneck thật và đề xuất giảm tải hoặc tăng capacity downstream.

### Bài 12 — Runbook

Viết một runbook một trang cho sự cố consumer lag có phân loại: app stop, group ID sai, DB slow, hot partition, poison pill và broker outage. Mỗi nhánh phải nêu metric bằng chứng trước khi hành động.

---

## 29. Dọn môi trường lab

Sau khi kết thúc, dừng Spring Boot consumer (Ctrl+C ở terminal chạy app). Không để background consumer tiếp tục consume khi bạn muốn so sánh backlog lần sau.

Dừng broker cục bộ:

```bash
docker compose down
```

Lệnh trên dừng/xóa các containers/network do Compose tạo; tùy cấu hình storage, dữ liệu Kafka có thể mất khi container bị xóa. **Không dùng `docker compose down -v` nếu volume chứa dữ liệu bạn cần giữ**, và tuyệt đối không chạy những lệnh dọn resource khi bạn chưa chắc terminal đang ở thư mục lab và Compose project đúng.

Nếu muốn chạy lại thí nghiệm với committed offsets sạch, tạo một **group ID lab mới** có chủ đích và ghi lại `auto.offset.reset`. Không dùng group ID production hay reset offsets production.

---

## 30. Tài liệu tham khảo

- [Apache Kafka — Basic Kafka Operations](https://kafka.apache.org/44/operations/basic-kafka-operations/): `kafka-consumer-groups.sh --describe`, `--offsets`, `--members --verbose`, `--state` và offset reset.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.records`, `max.poll.interval.ms`, commit và group settings.
- [Apache Kafka — Consumer Group Protocol](https://kafka.apache.org/documentation/): partition assignment, offset commit và membership.
- [Spring Kafka 3.3 — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/message-listener-container.html): concurrency, ack modes, poll và offset semantics.
- [Spring Kafka — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): `pause()`, `resume()` và giữ polling khi paused.
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): idle, non-responsive, pause và resume events.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): retry, `DefaultErrorHandler` và recovery.
- [Spring Kafka — Dead Letter Publishing](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DeadLetterPublishingRecoverer` và reliability của DLT.
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` và test utilities.
- [Spring Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): observations/metrics cho listener và producer.
- [Spring Boot 3.4 — Kafka Support](https://docs.spring.io/spring-boot/3.4/reference/messaging/kafka.html): cấu hình `spring.kafka.*`.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): meter registry, Prometheus endpoint và instrumentation.
- [Apache Kafka Docker Official Image](https://hub.docker.com/r/apache/kafka): chạy broker Kafka bằng Docker trong môi trường riêng.

## 31. Kết luận

**Mô phỏng consumer lag** là cách trực quan để học những điều khó thấy khi hệ thống bình thường: committed offset khác với record vừa poll, lag tăng khi arrival rate vượt committed processing rate, pause khác stop, concurrency bị giới hạn bởi partitions, và một hot key hoặc poison record có thể khiến group chậm dù có nhiều consumers.

Bài thực hành đã đi từ một Kafka broker cục bộ, Spring Boot listener có delay điều chỉnh được, các lệnh `kafka-consumer-groups.sh`, tới các thí nghiệm burst/slow/pause/stop/skew/rebalance và quy trình khôi phục. Trong production, quan sát **xu hướng lag, tuổi event, ETA, processing latency, retry/DLT, resource saturation và kết quả nghiệp vụ** cùng lúc; không giảm con số lag bằng cách reset offset hoặc nuốt exception.

Một consumer group đáng tin cậy không chỉ “lag về 0”. Nó phải **xử lý đủ record bắt buộc, không nhân đôi side effect khi redelivery, đáp ứng SLA và có runbook rõ ràng khi backlog tăng**.
