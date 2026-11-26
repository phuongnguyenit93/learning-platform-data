# Thực hành đọc lại stream hoặc client AMQP 1.0 khi phiên bản phù hợp

## 1. Mục tiêu của bài thực hành tổng hợp

Trong module **SPRING_AMQP**, chúng ta đã dùng `RabbitTemplate` để publish message, `@RabbitListener` để consume, exchange/queue/binding để route và kết hợp ack, retry, dead-letter, transaction, quan sát hệ thống để xử lý bất đồng bộ đáng tin cậy. Tuy nhiên, hai yêu cầu nâng cao có thể xuất hiện:

- **Đọc lại sự kiện đã xử lý:** dựng lại projection, kiểm toán, chạy thuật toán phân tích mới hoặc cho một consumer mới đọc từ lịch sử thay vì chỉ nhận message tương lai.
- **Dùng client AMQP 1.0:** giao tiếp với RabbitMQ 4.x bằng giao thức mới hơn, phân biệt publish outcome và consumer settlement, hoặc khai thác khả năng interoperable của các client AMQP 1.0.

Đây là **hai bài lab liên quan nhưng không giống nhau**. *Replay* là khả năng của **stream (append-only log)** và điểm đọc **offset**; **AMQP 1.0 là một giao thức**. Một AMQP 1.0 client đọc **classic/quorum queue** thông thường không tự biến queue đó thành kho lịch sử có thể replay. AMQP 1.0 có thể consume **stream queue** với chỉ định offset trên phiên bản RabbitMQ thích hợp.

Trong bài này:

1. Chọn đúng đường thực hành theo **RabbitMQ version, client và queue type**.
2. Tạo một stream thật; publish message **đợi broker confirm**; đọc lại từ `first`, `offset(n)` và `next`.
3. Dùng named consumer + server-side offset tracking để resume; phân biệt **resume** với **chủ động replay toàn bộ**.
4. Kiểm tra retention, metadata offset, tính đúng nghiệp vụ và chống xử lý lặp.
5. Thực hành tùy chọn **AMQP 1.0 Java Client trên RabbitMQ 4.x**, bao gồm publish accepted/released và consumer accept/requeue/discard.
6. Ghép với Spring AMQP qua `spring-rabbit-stream` khi version phù hợp; xác định giới hạn của `@RabbitListener` dùng stream container.

**Phạm vi an toàn:** toàn bộ ví dụ chạy trên broker/container local hoặc staging cô lập. Không thử reset offset, xóa stream hoặc replay vào production DB nếu chưa có kế hoạch bù trừ và quyền phê duyệt.

## 2. Chọn đúng công nghệ theo phiên bản

| Câu hỏi | RabbitMQ Streams protocol | AMQP 1.0 native client | Spring AMQP AMQP 0-9-1 |
| --- | --- | --- | --- |
| Broker phù hợp | RabbitMQ **3.9+** có stream feature, bật `rabbitmq_stream`. | RabbitMQ **4.0+** native, không cần plugin AMQP 1.0. | RabbitMQ 3.x/4.x hỗ trợ AMQP 0-9-1. |
| Cổng mặc định | **5552** (stream protocol). | **5672** hoặc TLS 5671, dùng header AMQP 1.0. | **5672** hoặc TLS 5671, header AMQP 0-9-1. |
| Java client | `com.rabbitmq:stream-client`. | `com.rabbitmq.client:amqp-client`. | `com.rabbitmq:amqp-client`, thường qua Spring. |
| Kiểu dữ liệu | Stream: log append-only, offset, retention. | Classic/quorum/stream tùy target. | Exchange, queue, routing key và ack. |
| Replay | `first`, `offset(n)`, timestamp, `next`; named offset tracking. | Với **stream queue**, có offset stream consumer options. | Với **stream queue**, có AMQP 0-9-1 stream offset arguments; queue thường không replay. |
| Spring integration | `spring-rabbit-stream`: `RabbitStreamTemplate`, `StreamListenerContainer`. | Client **riêng**; không sử dụng `RabbitTemplate` để tự chuyển sang AMQP 1.0. | `RabbitTemplate`, `@RabbitListener` + Simple/Direct container. |
| Xác nhận thành công | Publish confirm, consumer offset tracking theo thiết kế. | Publish disposition `ACCEPTED/RELEASED/REJECTED`; consumer `accept/requeue/discard`. | Publisher confirms/returns; consumer `basicAck`/`basicNack`. |

**Quan trọng với RabbitMQ 3.x:** các bản cũ từng có `rabbitmq_amqp1_0` plugin, nhưng mô hình và feature support không giống **native AMQP 1.0 từ 4.0**. Lab AMQP 1.0 dưới đây **chỉ hướng tới RabbitMQ 4.x**; không giả định có thể chạy nguyên trên 3.x.

**Chọn bài lab:**

- Cần dựng lại projection từ message lịch sử → làm **Lab A: RabbitMQ Streams**.
- Muốn học AMQP 1.0 client nhưng chỉ cần work queue → làm **Lab B: AMQP 1.0**, đừng gọi đó là replay.
- Muốn replay stream bằng AMQP 1.0 → làm **Lab A** trước để có stream, rồi sử dụng consumer AMQP 1.0 với stream offset ở Lab B mở rộng.

## 3. Ba khái niệm dễ nhầm: ack, offset và retention

```mermaid
flowchart LR
    P["Publisher"] -->|"append"| S[("orders.audit.stream<br/>append-only log")]
    S -->|"offset 0..n"| C1["Projection consumer<br/>named offset"]
    S -->|"offset first"| C2["Replay consumer<br/>independent"]
    S -->|"offset next"| C3["Live-only consumer"]
    S -.->|"retention theo age/bytes"| R["Dữ liệu cũ có thể bị xóa<br/>theo segment"]
```

### 3.1. Work queue thông thường

Với classic/quorum queue, consumer ack đồng nghĩa broker có thể loại delivery khỏi queue. Sau khi ack và message đã bị loại, **không thể yêu cầu broker cho đọc lại toàn bộ lịch sử** chỉ bằng cách thay `@RabbitListener`. Cần nguồn log/outbox/archive khác nếu muốn replay.

### 3.2. Stream

Stream là **append-only log bền vững**. Consumer đọc từ một vị trí offset; đọc xong **không xóa message khỏi log**. Một consumer khác có thể đọc lại cùng nội dung cho tới khi message bị loại bởi retention. Offset là **vị trí kỹ thuật trong stream**, không phải số thứ tự business event nhất định liên tiếp; log có thể có record phục vụ housekeeping.

### 3.3. Resume khác replay

- **Resume:** tiếp tục từ offset đã lưu bởi một named consumer, tránh đọc quá nhiều dữ liệu cũ sau restart.
- **Replay:** chủ động đọc lại từ `first`, một offset chỉ định hoặc một mốc thời gian, thường cho projection mới hoặc điều tra.
- **Retention:** giới hạn nội dung **còn tồn tại** theo tuổi hoặc byte; không phải TTL riêng từng message của work queue. Một offset đã bị retention loại sẽ **không thể hồi phục chỉ bằng cách đặt lại con trỏ**.

Lưu ý: Khi named consumer có server-side offset tracking, **offset đã lưu có thể được ưu tiên hơn `OffsetSpecification.first()`**. Muốn replay toàn bộ, dùng **consumer name mới**, hoặc consumer không lưu tracking, và không sửa checkpoint production.

## 4. Chuẩn bị RabbitMQ local

### 4.1. Yêu cầu

- Java **17+** và Maven/Maven Wrapper.
- Docker daemon/container runtime hoạt động.
- Cổng host **5552** (stream), **5672** (AMQP 0-9-1/1.0), **15672** (Management) còn trống.
- Broker RabbitMQ 4.x cho **cả hai lab**; Streams có thể chạy trên broker cũ hơn nếu đúng feature/plugin.

Ví dụ shell Bash/WSL/macOS/Linux (PowerShell cần điều chỉnh cú pháp xuống dòng):

```bash
docker run -d --rm --name rabbitmq-stream-lab \
  -p 5552:5552 -p 5672:5672 -p 15672:15672 \
  -e RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS='-rabbitmq_stream advertised_host localhost' \
  rabbitmq:4.1-management

# Bật stream protocol và tích hợp Stream Management UI.
docker exec rabbitmq-stream-lab rabbitmq-plugins enable \
  rabbitmq_stream rabbitmq_stream_management

# Kiểm tra listeners và phiên bản.
docker exec rabbitmq-stream-lab rabbitmq-diagnostics listeners
docker exec rabbitmq-stream-lab rabbitmq-diagnostics status
```

Giải thích:

- Image `4.1-management` là **ví dụ version để lab**, không tự đại diện bản production. Có thể pin digest của image đã được kiểm thử theo tiêu chuẩn của tổ chức.
- `guest/guest` mặc định thường chỉ cho phép kết nối localhost, thích hợp lab khi có port mapping local. Production cần user/vhost/ACL riêng, TLS và bí mật qua secret manager.
- Stream Java Client dùng port **5552**; AMQP 1.0 dùng port **5672** trên cùng broker 4.x.
- `advertised_host localhost` chỉ tiện khi một Docker container được map vào localhost. Khi chạy cluster, Kubernetes hoặc container-to-container, advertised host/port phải là địa chỉ client **thật sự truy cập được**, nếu không metadata discovery có thể trả host không kết nối được.

Management UI: `http://localhost:15672`. Không mở các port mặc định này ra mạng công cộng.

### 4.2. Kiểm tra plugin và queue type

```bash
docker exec rabbitmq-stream-lab rabbitmq-plugins list -e

docker exec rabbitmq-stream-lab rabbitmqctl list_queues -p / \
  name type durable messages consumers
```

Chưa có stream `orders.audit.stream` cũng bình thường; Java chương trình sau sẽ tạo. Với môi trường dùng admin/IaC riêng, thay thao tác tự tạo bằng provisioner đã phê duyệt.

## 5. Tạo project Maven cho hai lab

Để tập trung vào cách dùng client, sử dụng Java program độc lập ngoài Spring Boot nhưng vẫn cùng hệ sinh thái RabbitMQ. Sau đó mục 12 sẽ đưa stream vào Spring AMQP.

```text
rabbit-replay-lab/
  pom.xml
  src/main/java/lab/StreamReplayLab.java
  src/main/java/lab/Amqp10Lab.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab</groupId>
  <artifactId>rabbit-replay-lab</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <!-- RabbitMQ native stream protocol, ví dụ release có tài liệu. -->
    <dependency>
      <groupId>com.rabbitmq</groupId>
      <artifactId>stream-client</artifactId>
      <version>1.11.0</version>
    </dependency>
    <!-- RabbitMQ AMQP 1.0 Java client; KHÁC tọa độ classic Java client. -->
    <dependency>
      <groupId>com.rabbitmq.client</groupId>
      <artifactId>amqp-client</artifactId>
      <version>1.7.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
```

**Chú ý:** Hai artifact `amqp-client` khác groupId hoàn toàn:

- `com.rabbitmq:amqp-client` là Java client **AMQP 0-9-1**, thường được Spring AMQP dùng gián tiếp.
- `com.rabbitmq.client:amqp-client` là Java client **AMQP 1.0**, với package `com.rabbitmq.client.amqp`.

Chúng không tự đổi protocol cho nhau. Khi tích hợp Spring Boot, dùng dependency management phù hợp, kiểm tra transitive dependencies và pin phiên bản đã test; **không chép version ví dụ vào production mà không kiểm tra BOM/compatibility**.

## 6. Lab A — Publish và xác nhận đã append vào stream

Tạo `src/main/java/lab/StreamReplayLab.java`. Chương trình cung cấp các command:

| Command | Ý nghĩa |
| --- | --- |
| `send` | Publish 5 event, đợi confirm từng event. |
| `first` | Đọc 5 message đầu tiên còn được retention giữ lại. |
| `offset-2` | Đọc 3 message từ offset 2 trở đi (trong lần chạy sạch). |
| `next` | Bắt đầu ở đuôi, đợi 5 message mới; cần terminal khác chạy `send`. |
| `track` | Named consumer đọc 5 message và lưu offset sau xử lý. |

```java
package lab;

import com.rabbitmq.stream.ByteCapacity;
import com.rabbitmq.stream.Consumer;
import com.rabbitmq.stream.Environment;
import com.rabbitmq.stream.OffsetSpecification;
import com.rabbitmq.stream.Producer;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class StreamReplayLab {
    private static final String STREAM = "orders.audit.stream";
    private static final int BATCH = 5;

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: send | first | offset-2 | next | track");
            System.exit(2);
        }

        // localhost:5552, guest/guest và vhost / là mặc định trong lab.
        try (Environment env = Environment.builder().build()) {
            env.streamCreator()
                    .stream(STREAM)
                    .maxLengthBytes(ByteCapacity.GB(1))
                    .create();

            switch (args[0]) {
                case "send" -> sendBatch(env);
                case "first" ->
                        read(env, OffsetSpecification.first(), BATCH);
                case "offset-2" ->
                        read(env, OffsetSpecification.offset(2), 3);
                case "next" ->
                        read(env, OffsetSpecification.next(), BATCH);
                case "track" -> readWithStoredOffset(env);
                default -> throw new IllegalArgumentException(args[0]);
            }
        }
    }

    private static void sendBatch(Environment env) throws Exception {
        CountDownLatch confirms = new CountDownLatch(BATCH);
        AtomicInteger failed = new AtomicInteger();

        try (Producer producer = env.producerBuilder()
                .stream(STREAM)
                .build()) {
            for (int i = 1; i <= BATCH; i++) {
                String event = "event-" + i;
                producer.send(producer.messageBuilder()
                                .addData(event.getBytes(StandardCharsets.UTF_8))
                                .build(),
                        context -> {
                            if (!context.isConfirmed()) {
                                failed.incrementAndGet();
                            }
                            confirms.countDown();
                        });
            }

            if (!confirms.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timeout: publish outcomes chưa đủ");
            }
            if (failed.get() != 0) {
                throw new IllegalStateException(
                        "Broker không confirm " + failed.get() + " events");
            }
            System.out.println("Confirmed " + BATCH + " events");
        }
    }

    private static void read(
            Environment env, OffsetSpecification from, int expected)
            throws Exception {
        CountDownLatch received = new CountDownLatch(expected);
        AtomicInteger seen = new AtomicInteger();

        // Không đặt consumer name: mỗi lần chạy có thể chọn offset mới.
        Consumer consumer = env.consumerBuilder()
                .stream(STREAM)
                .offset(from)
                .messageHandler((context, message) -> {
                    int n = seen.incrementAndGet();
                    if (n <= expected) {
                        String body = new String(
                                message.getBodyAsBinary(),
                                StandardCharsets.UTF_8);
                        System.out.printf(
                                "offset=%d body=%s%n",
                                context.offset(), body);
                        received.countDown();
                    }
                })
                .build();
        try {
            if (!received.await(25, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Không đủ message; kiểm tra offset/retention " +
                        "hoặc chạy send ở terminal khác");
            }
        } finally {
            consumer.close();
        }
    }

    private static void readWithStoredOffset(Environment env)
            throws Exception {
        CountDownLatch processed = new CountDownLatch(BATCH);
        AtomicInteger seen = new AtomicInteger();

        Consumer consumer = env.consumerBuilder()
                .stream(STREAM)
                .name("orders-projection-lab")
                .offset(OffsetSpecification.first())
                .manualTrackingStrategy().builder()
                .messageHandler((context, message) -> {
                    // DEMO: xem như đã xử lý sau khi ghi log.
                    // Production: commit DB idempotently TRƯỚC khi storeOffset.
                    String body = new String(
                            message.getBodyAsBinary(),
                            StandardCharsets.UTF_8);
                    System.out.printf("tracked offset=%d %s%n",
                            context.offset(), body);
                    context.storeOffset();
                    seen.incrementAndGet();
                    processed.countDown();
                })
                .build();
        try {
            if (!processed.await(25, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Named consumer chưa đọc đủ 5 message");
            }
        } finally {
            consumer.close();
        }
        System.out.println("Stored progress for orders-projection-lab");
    }
}
```

**Giới hạn của ví dụ:** `readWithStoredOffset` lưu offset mỗi event để dễ quan sát, điều này làm tăng I/O. Ứng dụng thật thường batch checkpoint theo số message hoặc interval đã đánh giá. `ctx.storeOffset()` không phải consumer ack xóa message; nó lưu vị trí xử lý. Để chắc chắn một checkpoint đã bền vững trước restart, cần đánh giá cơ chế xác nhận/lưu offset của client và test restart/fault injection, không chỉ dựa vào log “Stored progress”.

### 6.1. Chạy publish

```bash
mvn -q compile exec:java -Dexec.mainClass=lab.StreamReplayLab -Dexec.args=send
```

Ví dụ output:

```text
Confirmed 5 events
```

Gọi `producer.send(...)` là bất đồng bộ. Chương trình dùng `CountDownLatch` chờ tất cả publisher confirms và fail nếu có outcome không xác nhận hoặc timeout. Trường hợp timeout là **unknown outcome**: không có bằng chứng chắc chắn broker chưa append. Trong ứng dụng production, giữ event ID và outbox/idempotency.

## 7. Lab A — Đọc lại từ first, offset và next

### 7.1. Đọc từ đầu

```bash
mvn -q compile exec:java -Dexec.mainClass=lab.StreamReplayLab -Dexec.args=first
```

Trong stream mới chỉ có năm message:

```text
offset=0 body=event-1
offset=1 body=event-2
offset=2 body=event-3
offset=3 body=event-4
offset=4 body=event-5
```

Chạy lại lệnh `first`: bạn nhận **cùng các event** dù đã đọc một lần. Đó là replay. Nếu stream trước đó đã chứa dữ liệu, offset và batch đầu không nhất thiết giống ví dụ; dùng tên stream lab mới nếu cần kết quả chính xác.

### 7.2. Đọc từ offset cụ thể

```bash
mvn -q compile exec:java -Dexec.mainClass=lab.StreamReplayLab -Dexec.args=offset-2
```

Kỳ vọng khi log còn đủ và stream sạch:

```text
offset=2 body=event-3
offset=3 body=event-4
offset=4 body=event-5
```

`OffsetSpecification.offset(2)` chọn vị trí trong log. Đừng diễn giải `2` là “thử lại lần thứ hai” hay mã business ID. Offset là vị trí stream, và một số vị trí có thể được dành cho dữ liệu nội bộ. Khi số được yêu cầu đã bị retention loại, broker có thể đưa consumer tới vị trí khả dụng gần nhất.

### 7.3. Chỉ nhận message mới bằng next

Mở **terminal A**:

```bash
mvn -q compile exec:java -Dexec.mainClass=lab.StreamReplayLab -Dexec.args=next
```

Chương trình sẽ chờ, không in các event đã publish trước đó. Trong **terminal B**, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=lab.StreamReplayLab -Dexec.args=send
```

Terminal A nhận năm event mới. Vì payload cố ý tái sử dụng `event-1 ... event-5`, chúng trông giống message cũ nhưng **offset khác**; đây là các lần append mới, không phải replay các record cũ.

**Phân biệt `last()` và `next()`:** `last()` có thể bắt đầu từ *chunk cuối* và nhận nhiều message đã có; `next()` đợi record mới được append. Không thay `last()` cho `next()` nếu contract là “chỉ dữ liệu phát sinh sau khi consumer attach”.

## 8. Lab A — Named consumer, lưu offset và resume

### 8.1. Chạy named consumer lần đầu

```bash
mvn -q compile exec:java -Dexec.mainClass=lab.StreamReplayLab -Dexec.args=track
```

Chương trình dùng:

```java
.name("orders-projection-lab")
.offset(OffsetSpecification.first())
.manualTrackingStrategy().builder()
...
context.storeOffset();
```

`name` xác định **logical consumer** đối với server-side offset tracking. Sau khi message được xử lý, `storeOffset()` yêu cầu client lưu tiến độ vào stream. Với code production, hãy **commit side effect nghiệp vụ rồi mới store offset**; không checkpoint trước rồi mới ghi DB, vì process có thể chết giữa hai bước và bỏ qua event chưa xử lý.

### 8.2. Chạy lần hai và quan sát

Trong điều kiện checkpoint trước đó đã được lưu, `track` tiếp theo có thể **không in năm event cũ**. Vì consumer đã có stored offset, trạng thái đó được ưu tiên hơn yêu cầu ban đầu `first()`, nên nó sẽ chờ message mới. Mở terminal thứ hai gọi `send`, consumer mới nhận batch tiếp theo.

Nếu lab báo timeout:

- Kiểm tra đã chạy `send` **sau** khi `track` restart chưa.
- Kiểm tra retention và offset tracking lưu thành công.
- Kiểm tra từng lần chạy trước đó có thực sự xử lý đủ 5 message và có đủ thời gian flush/stored offset hay không.
- Đừng tự xóa stream production hay đổi named consumer đang dùng để cố lấy lại offset 0.

### 8.3. Tại sao chỉ dùng cùng consumer name không đảm bảo “một instance duy nhất”?

Tên consumer dùng để định danh checkpoint nhưng **không tự bảo đảm mutual exclusion**. Hai client khác nhau có thể dùng cùng name và tiến độ checkpoint chồng lên nhau. Nếu cần một active consumer cho stream hoặc super stream, đánh giá **single active consumer**/consumer group tương ứng của client; nếu dùng nhiều partition, mỗi partition có offset riêng. Đừng chỉ đặt cùng `name` ở hai JVM rồi kỳ vọng broker tự phân phối chính xác một lần.

### 8.4. Thực hành replay độc lập với consumer production

Giả sử `orders-projection-prod` đã ghi offset 10.000. Để rebuild projection:

1. Tạo **projection DB/schema/table mới** hoặc target tách biệt (không ghi đè dữ liệu production đang phục vụ).
2. Khởi tạo replay consumer **không có name** hoặc dùng name mới như `orders-projection-rebuild-2026`.
3. Chọn `OffsetSpecification.first()` hoặc một offset/timestamp đã duyệt.
4. Đọc đến một **watermark/cutoff offset** ghi nhận tại thời điểm bắt đầu; sau đó chuyển sang bắt kịp live tail nếu cần.
5. Đối soát theo `eventId`/aggregate version trước khi promote projection mới.
6. Giữ consumer checkpoint production nguyên vẹn cho tới khi cutover được duyệt.

Việc đọc lại không phải rollback thời gian của các tác động ngoại vi: nếu event đã gây thanh toán hoặc gửi email, consumer replay **không được thực hiện lại** những side effect đó.

## 9. Offset theo timestamp, chunk và retention

RabbitMQ Stream Java Client hỗ trợ nhiều kiểu:

| Offset specification | Cách dùng | Giới hạn |
| --- | --- | --- |
| `OffsetSpecification.first()` | Đầu log **còn được giữ lại**. | Không thể đọc segment đã bị retention xóa. |
| `OffsetSpecification.offset(n)` | Offset kỹ thuật chỉ định. | Có thể không liên tiếp; bị clamp nếu ngoài phạm vi. |
| `OffsetSpecification.last()` | Chunk cuối đã có. | Không chỉ lấy “một message cuối”. |
| `OffsetSpecification.next()` | Bắt đầu từ record chưa được ghi. | Không thấy message cũ; có thể chờ mãi nếu không có producer. |
| `OffsetSpecification.timestamp(instant)` | Vị trí gần thời điểm broker append. | Chunk có timestamp chung, có thể đọc record trước mốc. |

### 9.1. Replay từ timestamp

Đoạn thay thế tại chỗ `read(...)`:

```java
import java.time.Instant;

OffsetSpecification from =
        OffsetSpecification.timestamp(
                Instant.parse("2026-11-26T08:00:00Z"));

// Trong ví dụ chính: read(env, from, expectedCount).
```

Timestamp dựa theo **thời gian message đến stream ở broker**, không phải `createdAt` do ứng dụng gửi trong payload. Vì broker xử lý theo **chunk**, một consumer có thể nhận message hơi sớm hơn mốc yêu cầu. Nếu cần tập dữ liệu business chính xác theo giờ, lọc tiếp theo `eventTime`/`eventId` trong payload sau khi attach và đảm bảo tính đúng của clock/event schema.

### 9.2. Retention không tương đương TTL work queue

```text
Stream append-only
  segment A (cũ) | segment B | segment C (mới)
        ^
        x-max-age / x-max-length-bytes có thể xóa cả segment
```

Trong code lab, `maxLengthBytes(ByteCapacity.GB(1))` giới hạn stream khoảng 1 GiB theo cơ chế **segment retention**, không đảm bảo đạt đúng byte tuyệt đối trước mỗi lần loại segment. RabbitMQ còn có `x-max-age`/policy `max-age`. Retention xử lý theo segment, thường giữ ít nhất một segment, nên không đảm bảo mỗi message biến mất chính xác ngay khi quá tuổi.

**Điểm an toàn:** Retention có thể xóa message mà consumer chậm chưa đọc. Nếu yêu cầu replay 30 ngày, đặt retention và disk capacity theo tốc độ thực tế, thêm giám sát **oldest available offset / consumer progress / lag**; đừng chỉ set max age mà không đo disk.

### 9.3. Kiểm tra stream từ broker

```bash
docker exec rabbitmq-stream-lab rabbitmqctl list_queues -p / \
  name type messages consumers arguments

# Một số bản có công cụ dành riêng cho stream; kiểm tra help.
docker exec rabbitmq-stream-lab rabbitmq-streams help
```

Số `messages` ở Management UI của stream có thể khác số record business vì offset tracking records/metadata cũng được lưu. **Không** đối soát số event theo UI message count như một sổ cái. Đối soát theo `eventId` và business DB.

## 10. Idempotency khi đọc lại: tại sao quan trọng hơn tốc độ

Một stream cho phép replay **cùng sự kiện nhiều lần**. Đối với consumer dựng projection, đó là tính năng; đối với consumer tạo side effect trực tiếp, có thể là lỗi nghiêm trọng.

Ví dụ bảng PostgreSQL:

```sql
CREATE TABLE processed_events (
    consumer_group VARCHAR(80) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_group, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(80) PRIMARY KEY,
    total_amount BIGINT NOT NULL,
    event_version BIGINT NOT NULL
);
```

Ví dụ service theo hướng transaction (giả định dùng `JdbcTemplate`):

```java
@Transactional
public void apply(Event event) {
    int inserted = jdbc.update("""
        INSERT INTO processed_events(consumer_group, event_id)
        VALUES (?, ?)
        ON CONFLICT (consumer_group, event_id) DO NOTHING
        """, "orders-projection-rebuild", event.eventId());

    if (inserted == 0) {
        return; // Event đã được nhóm projection này áp dụng.
    }

    jdbc.update("""
        INSERT INTO order_projection(order_id, total_amount, event_version)
        VALUES (?, ?, ?)
        ON CONFLICT (order_id) DO UPDATE
        SET total_amount = EXCLUDED.total_amount,
            event_version = EXCLUDED.event_version
        WHERE order_projection.event_version < EXCLUDED.event_version
        """, event.orderId(), event.amount(), event.version());
}
```

`Event` và `JdbcTemplate` là các thành phần ứng dụng phải định nghĩa/inject. Ví dụ tập trung vào **transaction + unique event ID + kiểm soát aggregate version**; chỉ phù hợp khi mỗi event mang một **snapshot toàn phần** của số tiền và version tăng. Nếu event chứa `delta`, không thể tùy ý `UPSERT total_amount` như snapshot; phải thiết kế event handler theo semantics thực tế và đảm bảo thứ tự.

### 10.1. Ranh giới transaction và checkpoint

```text
Stream deliver event offset N
  -> validate schema
  -> Spring @Transactional service.apply(event)
  -> DB COMMIT
  -> context.storeOffset() hoặc external checkpoint
```

**DB commit và broker offset checkpoint không phải một transaction chung.** Nếu chết **sau commit trước checkpoint**, event sẽ được đọc lại; unique marker chặn side effect thứ hai. Nếu checkpoint **trước commit**, có thể bỏ qua một event không được xử lý — thứ tự nguy hiểm.

Nếu cần đồng bộ offset với business state chính xác hơn, lưu **offset vào cùng DB transaction** với projection và dùng external checkpoint store + `subscriptionListener` để đọc lại từ `lastCommittedOffset + 1`. Vẫn phải tính đến stream partition và version, và làm rõ policy khi offset đã bị retention xóa.

### 10.2. Không dùng replay để gọi API thanh toán/email lần nữa

Phân biệt:

- **Rebuild projection:** đọc lại và ghi vào bảng mới, side effect giới hạn trong projection.
- **Reprocess business workflow:** cần event ID, idempotency key với downstream và approval.
- **Audit/analytics:** có thể chỉ đọc/đếm/ghi ở kho dữ liệu phân tích, không thay đổi business state chính.

Replay là *công cụ để đọc lại dữ liệu*, không phải cơ chế tự động undo/redo toàn bộ giao dịch kinh doanh.

## 11. Lab B — Dùng AMQP 1.0 Java client khi RabbitMQ 4.x hỗ trợ

**Đây là nhánh tùy chọn.** AMQP 1.0 được RabbitMQ hỗ trợ **native từ 4.0**, trên cùng port 5672 với AMQP 0-9-1; client thương lượng bằng protocol header và SASL. Không cần bật plugin `rabbitmq_amqp1_0` trên RabbitMQ 4.x.

Với Maven mục 5, package `com.rabbitmq.client.amqp` thuộc library **`com.rabbitmq.client:amqp-client`**. Nó **không phải** `com.rabbitmq.client.Channel` AMQP 0-9-1 và không sử dụng `basicAck`/`basicNack`; thay vào đó dùng **publisher outcomes** và **consumer dispositions**.

### 11.1. Tạo class Java và queue quorum

Tạo `src/main/java/lab/Amqp10Lab.java`:

```java
package lab;

import com.rabbitmq.client.amqp.Connection;
import com.rabbitmq.client.amqp.Consumer;
import com.rabbitmq.client.amqp.ConsumerBuilder;
import com.rabbitmq.client.amqp.Environment;
import com.rabbitmq.client.amqp.Publisher;
import com.rabbitmq.client.amqp.impl.AmqpEnvironmentBuilder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class Amqp10Lab {
    private static final String QUEUE = "lab.amqp10.work";
    private static final String STREAM = "orders.audit.stream";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: send | receive | replay-stream");
            System.exit(2);
        }
        Environment env = new AmqpEnvironmentBuilder()
                .connectionSettings()
                .uri("amqp://guest:guest@localhost:5672/%2f")
                .environmentBuilder()
                .build();

        try {
            Connection connection = env.connectionBuilder().build();
            try {
                // Chỉ cho lab: management API phía client khai báo queue.
                connection.management()
                        .queue(QUEUE).quorum().queue().declare();

                switch (args[0]) {
                    case "send" -> send(connection);
                    case "receive" -> receive(connection);
                    case "replay-stream" -> replayStream(connection);
                    default ->
                            throw new IllegalArgumentException(args[0]);
                }
            } finally {
                connection.close();
            }
        } finally {
            env.close();
        }
    }

    private static void send(Connection connection) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Publisher.Status> outcome =
                new AtomicReference<>();

        try (Publisher publisher = connection.publisherBuilder()
                .queue(QUEUE).build()) {
            publisher.publish(
                    publisher.message(
                            "hello-amqp10".getBytes(StandardCharsets.UTF_8)),
                    context -> {
                        outcome.set(context.status());
                        done.countDown();
                    });

            if (!done.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Unknown publish outcome");
            }
            if (outcome.get() != Publisher.Status.ACCEPTED) {
                throw new IllegalStateException(
                        "Publish status: " + outcome.get());
            }
            System.out.println("AMQP 1.0 ACCEPTED");
        }
    }

    private static void receive(Connection connection) throws Exception {
        CountDownLatch done = new CountDownLatch(1);

        Consumer consumer = connection.consumerBuilder()
                .queue(QUEUE)
                .messageHandler((context, message) -> {
                    try {
                        String body = new String(
                                message.body(), StandardCharsets.UTF_8);
                        System.out.println("Received: " + body);
                        // Thực tế: commit nghiệp vụ trước khi accept.
                        context.accept();
                        done.countDown();
                    } catch (RuntimeException error) {
                        context.requeue();
                    }
                })
                .build();

        try {
            if (!done.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timeout waiting for AMQP 1.0 delivery");
            }
        } finally {
            consumer.close();
        }
    }

    private static void replayStream(Connection connection)
            throws Exception {
        CountDownLatch done = new CountDownLatch(5);
        Consumer consumer = connection.consumerBuilder()
                .queue(STREAM)
                .stream()
                    .offset(ConsumerBuilder.StreamOffsetSpecification.FIRST)
                .builder()
                .messageHandler((context, message) -> {
                    System.out.println("AMQP 1.0 stream read: " +
                            new String(message.body(),
                                    StandardCharsets.UTF_8));
                    // Trên stream, settle delivery không xóa log.
                    context.accept();
                    done.countDown();
                })
                .build();
        try {
            if (!done.await(25, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Stream chưa có đủ 5 message hoặc retention đã xóa");
            }
        } finally {
            consumer.close();
        }
    }
}
```

**Lưu ý:** Trong bài lab, chạy `replay-stream` **sau Lab A đã tạo và gửi message vào stream**. Consumer AMQP 1.0 có thêm `.stream().offset(FIRST)` và sẽ đọc lại log; consumer AMQP 1.0 của **quorum queue thường** dùng `.queue(QUEUE)` không có replay offset, `accept()` loại delivery như work queue bình thường.

### 11.2. Gửi và nhận bằng AMQP 1.0

```bash
mvn -q compile exec:java -Dexec.mainClass=lab.Amqp10Lab -Dexec.args=send
mvn -q compile exec:java -Dexec.mainClass=lab.Amqp10Lab -Dexec.args=receive
```

Kết quả mẫu:

```text
AMQP 1.0 ACCEPTED
Received: hello-amqp10
```

`Publisher.Status.ACCEPTED` là một publish outcome thành công, không có nghĩa DB consumer đã commit. Các trạng thái khác:

| Publisher outcome | Diễn giải |
| --- | --- |
| `ACCEPTED` | Broker chấp nhận publish theo protocol. |
| `RELEASED` | Publish không route vào queue phù hợp, ví dụ binding sai. |
| `REJECTED` | Broker/target từ chối message; cần kiểm tra lý do. |
| Không có disposition trước timeout | **Unknown**, có thể broker đã nhận nhưng response chưa tới. |

Với AMQP 1.0, `Consumer.Context` có:

- `accept()`: xử lý thành công; queue thông thường loại delivery.
- `requeue()`: chưa xử lý, cho broker có thể giao lại, **không có delay/backoff tự động**.
- `discard()`: từ chối; có thể drop hoặc dead-letter nếu topology/policy hỗ trợ.

**Không map mù** `accept/requeue/discard` sang các lệnh Java Channel `basicAck/basicNack/basicReject`. Chúng thuộc protocol APIs khác; ngữ nghĩa giao nhận tương tự ở cấp khái niệm nhưng tính năng, headers/annotations, security và transaction cần kiểm thử theo client/version cụ thể.

### 11.3. Đọc lại stream bằng AMQP 1.0

```bash
mvn -q compile exec:java -Dexec.mainClass=lab.Amqp10Lab -Dexec.args=replay-stream
```

Kỳ vọng nhận năm message đầu còn tồn tại. Chạy lại lệnh: **đọc lại được**. Tính năng này đến từ **queue type stream + offset consumer option**, không phải vì AMQP 1.0 nói chung tạo lịch sử cho classic/quorum queue.

AMQP 1.0 có address v2 dành riêng cho RabbitMQ như `/queues/<queue-name>` và `/exchanges/<exchange>/<routing-key>`. Client Java ở đây dùng builder `.queue(name)` để tránh tự ghép chuỗi địa chỉ sai hoặc quên percent-encoding. Khi dùng raw AMQP 1.0 client không có builder, phải làm đúng quy tắc RabbitMQ v2 addresses và virtual host.

### 11.4. Khi nào không dùng Lab B?

- Broker chưa đạt RabbitMQ 4.0 native AMQP 1.0, chưa có kế hoạch nâng cấp.
- Ứng dụng production đang dùng `RabbitTemplate`/`@RabbitListener` AMQP 0-9-1 và không có yêu cầu chuyển protocol; **không cần đổi chỉ vì lab hỗ trợ**.
- Phụ thuộc `tx.select/tx.commit`, channel interceptors hoặc tính năng AMQP 0-9-1 hiện chưa có ở native AMQP 1.0 theo version đang dùng.
- Không có kiểm thử tương thích message properties/header khi producer và consumer dùng **hai protocol khác nhau**.

AMQP 1.0 và AMQP 0-9-1 **có thể tương tác qua RabbitMQ**, nhưng complex headers và body mapping có giới hạn chuyển đổi. Kiểm tra schema với payload JSON/Avro/Protobuf và content type rõ ràng, thay vì coi mọi field table sẽ được bảo toàn một-một.

## 12. Đưa stream vào Spring AMQP khi stack tương thích

Nếu hệ thống đã sử dụng Spring AMQP, **không nhất thiết phải chạy Java Stream Client trực tiếp trong mỗi service**. Từ Spring AMQP **2.4**, module `spring-rabbit-stream` cung cấp:

- `RabbitStreamTemplate`: publish qua Stream protocol; **khác `RabbitTemplate`** AMQP 0-9-1.
- `StreamListenerContainer`: consume stream thông qua Java Stream Client.
- `StreamRabbitListenerContainerFactory`: dùng `@RabbitListener` với stream listener container.
- `StreamAdmin`: tạo stream bằng Stream protocol, hữu ích khi ứng dụng chỉ dùng stream components và không mở AMQP 0-9-1 connection để kích hoạt `RabbitAdmin`.

**Version guard:** tên class và API dưới đây theo Spring AMQP 2.4+/các phiên bản 3.x/4.x có tính năng tương ứng. Kiểm tra compatibility với Spring Boot BOM, JDK và Stream Java Client. Ví dụ sử dụng Java 17; không pin đồng thời các version Spring bị xung đột với dependency management của dự án.

### 12.1. Dependency Spring

```xml
<dependency>
    <groupId>org.springframework.amqp</groupId>
    <artifactId>spring-rabbit-stream</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Với Spring Boot có BOM phù hợp, chọn version `spring-rabbit-stream` theo release train; nếu không có BOM quản lý, chỉ định version tương thích **có kiểm chứng**. Module kéo các dependency cần thiết theo setup của nó; đừng trộn các stream-client version xung đột khi ghép vào dự án lớn.

### 12.2. Khai báo `Environment` và `StreamAdmin`

Ví dụ rút gọn (trên broker local của lab):

```java
import com.rabbitmq.stream.Environment;
import org.springframework.rabbit.stream.support.StreamAdmin;
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Duration;

@Configuration
class AuditStreamConfiguration {

    @Bean(destroyMethod = "close")
    Environment streamEnvironment() {
        return Environment.builder().build();
    }

    @Bean
    StreamAdmin streamAdmin(Environment env) {
        return new StreamAdmin(env, creator -> {
            creator.stream("orders.audit.stream")
                    .maxAge(Duration.ofHours(2))
                    .create();
        });
    }

    @Bean
    RabbitStreamTemplate auditStreamTemplate(Environment env) {
        return new RabbitStreamTemplate(env, "orders.audit.stream");
    }
}
```

Đoạn config thể hiện **stream protocol** trên port 5552. Nếu bạn chỉ có stream components, bean `QueueBuilder.stream()` qua `RabbitAdmin` có thể chưa được declare vì RabbitAdmin thường đợi AMQP connection; `StreamAdmin` giải quyết việc khai báo qua Stream protocol. Khi topology do IaC quản lý, chuyển ownership sang provisioner, không cho runtime declare ngẫu nhiên.

Lưu ý `maxAge(Duration.ofHours(2))` chỉ dành cho lab; production cần retention theo storage capacity, replay window và recovery SLO. Nếu stream đã tồn tại với cấu hình khác, cần đọc effective retention và rules của stream creator/policy thay vì tin rằng gọi `create()` tự cập nhật mọi setting.

### 12.3. Publish với `RabbitStreamTemplate`

```java
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;

@Service
class AuditPublisher {
    private final RabbitStreamTemplate template;

    AuditPublisher(RabbitStreamTemplate template) {
        this.template = template;
    }

    CompletableFuture<Boolean> publish(String eventId) {
        return template.convertAndSend(eventId);
    }
}
```

Kết quả là một `CompletableFuture<Boolean>` — cần quan sát hoàn tất, false/exception, timeout và unknown outcome. **Không gọi `convertAndSend()` rồi coi đã append chắc chắn nếu chưa xử lý future.** Có thể dùng outbox, correlation ID, producer deduplication theo Stream Client khi phù hợp.

### 12.4. Consume bằng `@RabbitListener` qua stream container

Ví dụ stream listener riêng, **không** dùng `SimpleRabbitListenerContainerFactory`:

```java
import com.rabbitmq.stream.Environment;
import com.rabbitmq.stream.OffsetSpecification;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.rabbit.stream.config.StreamRabbitListenerContainerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Configuration
class AuditReplayListenerConfiguration {
    @Bean("replayStreamFactory")
    StreamRabbitListenerContainerFactory replayStreamFactory(
            Environment env) {
        StreamRabbitListenerContainerFactory factory =
                new StreamRabbitListenerContainerFactory(env);
        factory.setNativeListener(true);
        factory.setConsumerCustomizer((id, builder) -> {
            builder.offset(OffsetSpecification.first())
                    .noTrackingStrategy();
        });
        return factory;
    }
}

@Component
class AuditReplayListener {
    @RabbitListener(
            id = "audit-replay-lab",
            queues = "orders.audit.stream",
            containerFactory = "replayStreamFactory",
            autoStartup = "false")
    public void onStreamMessage(
            com.rabbitmq.stream.Message message,
            com.rabbitmq.stream.MessageHandler.Context context) {
        System.out.println(
                new String(message.getBodyAsBinary()));
        // Replay ở lab: đọc để quan sát. Không ghi business state khi chưa có
        // cơ chế idempotent processing và vị trí offset rõ ràng.
    }
}
```

Để mở container theo yêu cầu, dùng `RabbitListenerEndpointRegistry` tìm listener ID `audit-replay-lab` rồi start khi user/admin đã chọn đúng replay scope. `autoStartup=false` ngăn việc replay toàn bộ stream mỗi lần ứng dụng production boot.

**Giới hạn `@RabbitListener` khi dùng stream factory:** các thuộc tính như `concurrency`, `exclusive`, `priority` của listener AMQP 0-9-1 không nhất thiết có ý nghĩa. Theo tài liệu Spring AMQP, chỉ một số thuộc tính như `id`, `queues` (một stream), `autoStartup` và `containerFactory` được stream container hỗ trợ; với super stream/concurrency, dùng API của Stream Listener Container tương ứng.

**Không đưa `StreamAdmin` và listener tự replay vào một ứng dụng production mà không có feature flag và phân quyền.** Replay vào bảng cũ có thể gây side effect lặp hoặc làm tắc broker nếu chạy mỗi lần deploy.

## 13. So sánh cùng một event qua ba đường tiêu thụ

Giả sử event `OrderCreated(eventId=evt-101)` đã được publish:

```text
               RabbitMQ broker
                 |
                 +-- classic/quorum work queue
                 |      -- @RabbitListener AUTO ack -->
                 |         Message được ack; không replay bằng consumer offset
                 |
                 +-- orders.audit.stream
                        -- Stream Client offset first --> đọc evt-101
                        -- Stream Client offset first --> đọc lại evt-101
                        -- AMQP 1.0 stream offset FIRST --> đọc lại evt-101
                        -- named consumer checkpoint --> resume từ tiến độ
```

### Vì sao không thay mọi queue bằng stream?

| Yêu cầu | Work queue classic/quorum | Stream |
| --- | --- | --- |
| Một worker hoàn thành công việc rồi message rời queue | Phù hợp. | Message vẫn ở log đến khi retention loại. |
| Đọc lại toàn bộ lịch sử đã lưu | Không đáp ứng nếu đã ack/xóa. | Phù hợp. |
| DLX/TTL per-message/poison message theo queue | Có cơ chế quen thuộc. | Stream có retention/offset, **không có DLX/TTL per-message tương đương**. |
| Nhiều consumer đọc độc lập cùng event | Cần nhiều queue/binding/group. | Nhiều consumer dùng offset riêng. |
| Tính đúng một lần của side effect DB | Cần idempotency/transaction. | **Vẫn cần idempotency/transaction**. |
| Source của backfill/rebuild | Cần archive/outbox khác. | Có thể dùng stream nếu retention đủ. |

**Không dùng stream retention để thay thế dead-letter queue trong bài toán retry poison message** mà chưa thiết kế lại error handling. Stream không có kiểu “nack requeue để message được worker khác nhận” giống queue truyền thống.

## 14. Kiểm thử tự động và tiêu chí PASS/FAIL

Phần này mô tả test integration với RabbitMQ thật. Unit test Mockito có thể kiểm tra handler nhưng không chứng minh stream còn giữ message, offset resume hay publish disposition của AMQP 1.0.

### 14.1. Mô hình test Testcontainers

Với Testcontainers RabbitMQ:

```java
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class ReplayIntegrationTest {
    @Container
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse("rabbitmq:4.1-management"))
                    .withExposedPorts(5552);

    // Setup cần bật rabbitmq_stream và advertised host/port
    // phù hợp với network namespace mà Java Stream Client truy cập.
    // Test thực sẽ tạo stream và gửi event có unique eventId.
}
```

**Chú ý cấu hình network:** Stream protocol trả thông tin metadata node; Testcontainers có mapped port ngẫu nhiên, trong khi broker có thể advertise `rabbitmq@container` hoặc port `5552` không truy cập được từ host. Vì vậy skeleton trên **chưa phải test chạy được ngay**; cần bật plugin, expose/mapping đúng stream listener, cấu hình `stream.advertised_host`/`advertised_port` hoặc networking alias phù hợp, và chỉ xây `Environment` sau khi container sẵn sàng. Không hardcode port 5552 từ host rồi coi Testcontainers đã map đúng.

Nếu chỉ kiểm thử AMQP 1.0 queue send/receive, có thể dùng mapped AMQP port của `RabbitMQContainer`; không cần stream plugin. Với test replay Stream, tốt nhất diễn tập trên Docker Compose/staging có network metadata đã được cấu hình đúng, rồi thêm Testcontainers integration khi network config đã ổn.

### 14.2. Ma trận kiểm thử

| Test | Input/thao tác | Expected |
| --- | --- | --- |
| Publish confirmed | Append 5 event IDs vào stream. | Mọi publish có confirmation, không timeout. |
| Read first | Consume từ `first`. | Lấy được mọi event còn trong retention. |
| Replay first | Tạo consumer mới từ `first`. | Cùng event IDs được đọc lại, stream không mất record. |
| Offset replay | Start `offset(2)`. | Bắt đầu từ offset cụ thể, không nhất thiết từ business sequence #2. |
| Tail live | Start `next` rồi mới publish 5 event. | Chỉ nhận event mới sau attach. |
| Named consumer | Commit DB, store offset, restart với cùng name. | Resume từ checkpoint có thể bị trễ nhẹ, không tạo duplicate side effect. |
| Retention | Cấu hình ngưỡng rất thấp trong **stream test mới** rồi append nhiều segment. | Dữ liệu đã expired không replay được, có cảnh báo cho consumer lag. |
| AMQP 1.0 publish | Publish vào quorum queue, đợi disposition. | `ACCEPTED`; message tới queue. |
| AMQP 1.0 consume | Consumer nhận, gọi `accept()`. | Message được settle; queue thông thường không giữ message đã accept. |
| AMQP 1.0 stream read | `.stream().offset(FIRST)` trên stream. | Đọc lại lịch sử theo phạm vi retention. |
| Consumer crash | DB commit nhưng chưa lưu checkpoint hoặc chưa settle. | Event có thể đọc/giao lại, idempotency chặn side effect lặp. |
| Cross-protocol | AMQP 0-9-1 publish, AMQP 1.0 consume (hoặc ngược lại). | Body/headers cần thiết được chuyển đổi đúng; không giả định complex field table. |

### 14.3. Mô hình assertion theo event IDs

Không assert duy nhất số message ở Management UI. Ví dụ:

```text
Published IDs = {E1, E2, E3, E4, E5}
First read    = {E1, E2, E3, E4, E5}
Replay read   = {E1, E2, E3, E4, E5}
New projection: mỗi E1..E5 được áp dụng đúng 1 lần
Stream log: dữ liệu vẫn tồn tại trong retention window
```

Với consumer gặp lỗi giữa DB commit và offset checkpoint, số lần đọc event có thể **lớn hơn 1**, nhưng số side effect đúng phải **bằng 1** cho từng event ID.

## 15. Troubleshooting: tại sao stream hoặc AMQP 1.0 không chạy?

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Client Stream không kết nối port 5552 | Plugin chưa bật, firewall, sai listener hoặc port mapping. | `rabbitmq-plugins list -e`, `rabbitmq-diagnostics listeners`, container logs. |
| Stream Client kết nối bước đầu rồi thất bại | `advertised_host/port` trả địa chỉ node không truy cập được. | Kiểm tra metadata discovery và địa chỉ trong Docker/K8s/cluster. |
| `PRECONDITION_FAILED` khi tạo stream | Queue cùng tên đã tồn tại loại classic/quorum hoặc args khác. | Kiểm tra `type`/arguments; không delete/purge production. |
| Consumer stream không in gì | Default offset là `next`, stream chưa có event mới. | Dùng `first()` cho replay; chạy producer hoặc kiểm tra stored offset. |
| Đặt `first` nhưng vẫn resume ở đuôi | Named consumer đã lưu offset trước đó. | Dùng replay consumer không tracking hoặc name riêng, không reset checkpoint production. |
| Chỉ nhận một phần lịch sử | Retention đã xóa segment cũ hoặc chọn timestamp/offset quá xa. | Kiểm tra max-age, max-length-bytes, oldest offset, backup/archive. |
| Offset không tăng đều | Offset tracking records và nội bộ stream làm offset không liên tiếp. | Đo event ID/sequence nghiệp vụ, không giả định offset n = message thứ n. |
| Broker lưu nhiều disk | Retention chưa thiết lập hoặc stream/segment size lớn. | Cấu hình policy age/bytes, capacity và cảnh báo disk. |
| AMQP 1.0 client gặp protocol header error | RabbitMQ 3.x/plugin cũ, sai endpoint, proxy không cho AMQP 1.0. | Dùng RabbitMQ 4.x native, đúng port và SASL. |
| AMQP 1.0 không auth được | Vhost/user/password sai, client SASL chưa tương thích. | Check URI, `%2F` cho vhost `/`, auth backend/TLS. |
| AMQP 1.0 publish không được ACCEPTED | Unroutable, target không tồn tại, quyền write hoặc tài nguyên. | Xem `RELEASED/REJECTED`, target v2 address/permissions. |
| AMQP 1.0 consumer treo sau một thời gian | Message chưa settle, credit cạn. | Gọi `accept/requeue/discard` sau xử lý phù hợp. |
| Dùng `RabbitTemplate` mà không thấy AMQP 1.0 | Spring `RabbitTemplate` là AMQP 0-9-1. | Dùng Java AMQP 1.0 client riêng hoặc Stream module cho stream protocol. |
| `@RabbitListener` stream không áp dụng concurrency | Stream factory có subset thuộc tính annotation. | Dùng Stream container API và super stream nếu cần partitioning. |
| Replay sinh double payment/email | Handler phát lại side effect không idempotent. | Dùng projection isolation, unique event ID, không replay side effect chưa kiểm soát. |

### 15.1. Lệnh chẩn đoán nhanh

```bash
docker logs --tail 100 rabbitmq-stream-lab

docker exec rabbitmq-stream-lab rabbitmq-diagnostics listeners
docker exec rabbitmq-stream-lab rabbitmq-plugins list -e
docker exec rabbitmq-stream-lab rabbitmqctl list_queues -p / \
  name type durable messages consumers arguments
```

Khi triển khai production, đừng lặp CLI dày đặc để thay thế metrics. Thu thập Prometheus từ RabbitMQ và metrics/observations của app với labels có cardinality thấp; tránh dùng `eventId` làm metric label. Với AMQP 1.0, chú ý Management UI message rates có giới hạn hiển thị so với AMQP 0-9-1 ở một số phiên bản; đối chiếu broker/client metrics phù hợp.

## 16. Checklist vận hành trước khi đưa replay vào production

1. Xác nhận **broker version**, stream plugin/port hoặc native AMQP 1.0, client dependency và interoperability matrix.
2. Xác nhận stream **type=stream**, không nhầm queue type classic/quorum cùng tên và không đổi type in-place.
3. Đặt retention theo **cửa sổ replay yêu cầu**; dự toán disk/segment, monitoring lag và alert khi consumer sắp vượt retention.
4. Dùng event ID/aggregate version; dựng projection trong phạm vi riêng, không phát side effect ngoài ý muốn.
5. Nếu dùng offset tracking, chọn chiến lược manual/automatic và đảm bảo **DB commit trước store offset**.
6. Nếu dùng publisher AMQP 1.0, xử lý đủ các outcome và **UNKNOWN timeout**, không đánh đồng accepted với consumer success.
7. Kiểm tra cross-protocol conversion của payload/headers và schema version.
8. Đặt kill switch, rate limit và phạm vi offset/time window khi thực hiện backfill.
9. Có rollback: projection cũ không bị xóa trước khi đối soát; checkpoint consumer production không bị reset.
10. Test fault injection: mất kết nối, restart client, retention expiration và poison event, quan sát idempotency.

### Mẫu phiếu thực hành

```text
LAB ID: SPRING-AMQP-STREAM-REPLAY
RabbitMQ version: ...
Stream plugin: enabled / not enabled
Stream name: ...
Client versions:
  com.rabbitmq:stream-client = ...
  com.rabbitmq.client:amqp-client (AMQP 1.0) = ...

Published event IDs: ...
Confirm outcomes: ...
Replay first IDs: ...
Replay offset N IDs: ...
Replay next IDs: ...
Named consumer stored checkpoint: ...
Restart and resume first offset: ...
Retention and oldest available data: ...
AMQP 1.0 ACCEPTED/RELEASED/REJECTED: ...
Business duplicate side effects: ...
Troubleshooting evidence: ...
PASS / FAIL / NEXT ACTION: ...
```

## 17. Bài tập mở rộng

### Bài 1 — Replay đúng một phiên bản projection

Publish 20 event `OrderChanged` với `eventId` và `orderVersion` riêng; tạo projection v2 từ `first`. Sau đó replay lần hai vào cùng DB và chứng minh unique event marker khiến mỗi event được áp dụng đúng một lần.

### Bài 2 — Resume qua failure window

Consumer xử lý 12 message rồi crash sau DB commit nhưng trước `storeOffset` lần cuối. Khởi động lại cùng consumer name; ghi nhận những event bị đọc lại và kiểm chứng idempotency. Giải thích vì sao checkpoint cuối không tự đồng bộ atomic với transaction DB.

### Bài 3 — Retention nhỏ hơn thời gian gián đoạn

Cấu hình retention ngắn trên **stream test mới**, để consumer ngừng đủ lâu cho segment cũ bị loại. Sau khi resume, xác minh có gap dữ liệu. Đề xuất giải pháp: tăng retention/dung lượng, archive hoặc backfill từ nguồn authoritative.

### Bài 4 — AMQP 1.0 và AMQP 0-9-1 cùng một broker

Dùng `RabbitTemplate` publish JSON với event ID vào exchange/binding tới quorum queue; dùng Java AMQP 1.0 consumer đọc qua `.queue(name)`, `accept()` sau xử lý. Sau đó đảo chiều: AMQP 1.0 publisher tới exchange, `@RabbitListener` AMQP 0-9-1 consume. Kiểm tra headers/content type thực sự truyền được thay vì giả định mọi kiểu AMQP table được bảo toàn.

### Bài 5 — Một stream, hai nhóm độc lập

Chạy hai consumers với name riêng và offset tracking riêng. Cho nhóm A bắt đầu từ `first`, nhóm B từ `next` rồi append 10 message. So sánh số message mỗi nhóm nhận; chứng minh việc nhóm A đọc không xóa log của nhóm B.

## 18. Câu hỏi tự đánh giá

1. Tại sao `RabbitTemplate` và `@RabbitListener` của Spring AMQP không tự dùng AMQP 1.0 khi broker được nâng lên RabbitMQ 4.x?
2. RabbitMQ Streams yêu cầu broker tối thiểu phiên bản nào, plugin nào và cổng mặc định nào?
3. RabbitMQ native AMQP 1.0 xuất hiện từ phiên bản nào và mặc định dùng cổng nào?
4. Hai Maven artifacts có tên `amqp-client` nhưng khác `groupId` tương ứng hai giao thức nào?
5. Vì sao đọc `first` hai lần vẫn thấy cùng dữ liệu trong stream?
6. `last()` và `next()` khác nhau thế nào?
7. Vì sao `OffsetSpecification.offset(42)` không nên được hiểu là message business thứ 43?
8. Khi named consumer đã lưu offset, việc cấu hình `first` trong lần chạy sau có bắt buộc replay toàn bộ không?
9. `storeOffset()` có xóa message khỏi stream giống `basicAck` ở quorum queue không?
10. Vì sao cần DB commit trước khi lưu offset?
11. Nếu mất connection sau DB commit nhưng trước offset checkpoint, làm sao tránh side effect lặp?
12. Vì sao một timestamp offset có thể trả message sớm hơn timestamp được yêu cầu?
13. Retention có cho phép lấy lại message đã bị segment deletion không?
14. `Publisher.Status.ACCEPTED` trong AMQP 1.0 có nghĩa consumer đã xử lý xong không?
15. Những settlement methods nào được AMQP 1.0 client Java dùng thay cho `basicAck`, `basicNack` và `basicReject`?
16. Consumer AMQP 1.0 đọc quorum queue bình thường có replay message đã accept không? Trường hợp nào có thể replay với AMQP 1.0?
17. Vì sao stream protocol metadata discovery có thể fail khi chạy Docker port mapping dù TCP 5552 truy cập được?
18. Trong Spring `StreamRabbitListenerContainerFactory`, thuộc tính `concurrency` của `@RabbitListener` có ý nghĩa giống Simple container không?
19. Khi nào nên tạo projection DB riêng thay vì replay trực tiếp vào bảng đang phục vụ?
20. Tại sao không được dùng Management UI message count làm đối soát số event chính xác của stream?

**Gợi ý đáp án:** (1) Spring `RabbitTemplate` vẫn dùng AMQP 0-9-1; (2) RabbitMQ 3.9+, `rabbitmq_stream`, 5552; (3) RabbitMQ 4.0+, 5672; (4) `com.rabbitmq:amqp-client` là 0-9-1, `com.rabbitmq.client:amqp-client` là 1.0; (5) stream append-only giữ record theo retention; (6) `last` từ chunk cuối, `next` chỉ record mới; (7) offset có gaps/housekeeping; (8) không, stored offset có thể ưu tiên; (9) không; (10) checkpoint trước commit có thể làm mất tiến độ nghiệp vụ; (11) unique event ID/idempotency; (12) timestamp theo chunk; (13) không, cần nguồn dữ liệu khác; (14) không; (15) `accept/requeue/discard`; (16) không trên work queue, có trên stream với offset option; (17) broker advertise hostname/port không reach được; (18) không; (19) để tránh overwrite/double side effects và có rollback; (20) tracking records có thể ảnh hưởng số liệu UI, không đại diện mỗi business event.

## 19. Tổng kết

Trong **thực hành tổng hợp SPRING_AMQP**, hãy phân biệt rõ ba tầng:

1. **RabbitMQ Streams** là cấu trúc **append-only log** cho phép consumer đọc lại từ offset hoặc timestamp trong giới hạn retention. Đây là lựa chọn đúng khi cần rebuild projection, audit hay xử lý sự kiện lịch sử.
2. **RabbitMQ Stream Java Client** dùng protocol riêng (port 5552, plugin `rabbitmq_stream`), có producer confirms, offset specifications và server-side offset tracking. **Replay** từ `first`/`offset(n)` không làm mất message khỏi stream.
3. **AMQP 1.0 Java Client** là một giao thức/client khác, native trên RabbitMQ **4.0+** qua port 5672. Nó có publish outcomes, consumer settlements và có thể đọc **stream queue** với offset option, nhưng không khiến một classic/quorum work queue tự có replay.

Khi tích hợp với Spring, `spring-rabbit-stream` cung cấp `RabbitStreamTemplate`, `StreamAdmin` và `StreamRabbitListenerContainerFactory`; `RabbitTemplate` truyền thống vẫn phục vụ AMQP 0-9-1. Dù ở giao thức nào, **publisher confirm không đồng nghĩa consumer business success**, và offset checkpoint không atomically commit cùng DB transaction. Idempotency, retention sizing, kiểm thử phiên bản và đối soát event ID mới làm cho replay thực sự an toàn.

## Tài liệu tham khảo

- [RabbitMQ — Streams and Super Streams](https://www.rabbitmq.com/docs/streams): stream queue, offset, replay, retention, limit so với classic/quorum.
- [RabbitMQ — Stream Plugin](https://www.rabbitmq.com/docs/stream): bật `rabbitmq_stream`, port 5552, advertised host/port, metadata discovery.
- [RabbitMQ — Java Stream Tutorial 1](https://www.rabbitmq.com/tutorials/tutorial-one-java-stream): Environment, StreamCreator, Producer, Consumer từ first.
- [RabbitMQ — Java Stream Tutorial 2: Offset Tracking](https://www.rabbitmq.com/tutorials/tutorial-two-java-stream): `first`/`offset`/`next`, named consumers, manual tracking và resume.
- [RabbitMQ — Stream Java Client Reference](https://rabbitmq.github.io/rabbitmq-stream-java-client/stable/htmlsingle/): API stream publisher/consumer, offset tracking, retention và recovery.
- [RabbitMQ — AMQP 1.0](https://www.rabbitmq.com/docs/amqp): native từ 4.0, address v2, SASL, inter-protocol conversion và giới hạn.
- [RabbitMQ — AMQP 1.0 Client Libraries](https://www.rabbitmq.com/client-libraries/amqp-client-libraries): `Publisher.Status`, consumer `accept/requeue/discard`, stream offset options.
- [RabbitMQ — AMQP 1.0 Java Client Reference](https://rabbitmq.github.io/rabbitmq-amqp-java-client/stable/htmlsingle/): `AmqpEnvironmentBuilder`, connections, producers, consumers.
- [RabbitMQ — Java AMQP 1.0 Hello World](https://www.rabbitmq.com/tutorials/tutorial-one-java-amqp10): Java client native setup, publish outcome và consumer settlement.
- [Spring AMQP — Using the RabbitMQ Stream Plugin](https://docs.spring.io/spring-amqp/reference/stream.html): `spring-rabbit-stream`, `RabbitStreamTemplate`, `StreamAdmin`, `StreamListenerContainer`.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): phân biệt publisher confirms và consumer acknowledgement.


