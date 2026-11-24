# Đối chiếu header theo phần tử trong lô

Kafka consumer có thể nhận nhiều record trong một lần `poll()`. Với chế độ batch của Spring Cloud Stream Kafka binder, các record đó được chuyển tới hàm xử lý dưới dạng một danh sách payload. Khi ứng dụng cần biết từng phần tử đến từ topic, partition, offset hoặc key nào, chỉ nhận `List<T>` là chưa đủ: cần nhận thêm `Message<List<T>>` để truy cập metadata của từng record.

Điểm quan trọng là header của batch không phải một bộ metadata chung áp dụng cho toàn bộ danh sách. Với `Message<List<T>>`, các header dạng metadata theo record được biểu diễn bằng collection có thứ tự tương ứng với thứ tự payload. Phần tử ở vị trí `i` trong danh sách payload phải được đối chiếu với metadata ở vị trí `i` trong collection header. Nếu ghép sai vị trí, log, trace, định tuyến hoặc quyết định nghiệp vụ có thể gắn nhầm metadata của record này sang record khác.

## 1. Batch mode trong Kafka binder

Mặc định, Spring Cloud Stream Kafka binder gọi hàm consumer cho từng record. Khi bật `batch-mode`, tất cả record được lấy trong một lần poll được chuyển thành một batch và đưa tới listener dưới dạng `List<?>`.

Ví dụ cấu hình:

```yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-batch-processor
          content-type: application/json
          consumer:
            batch-mode: true
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 100
```

`batch-mode: true` bật batch consumption cho input binding. `max.poll.records` giới hạn số record tối đa Kafka consumer trả về trong một lần poll. Batch thực tế có thể nhỏ hơn giới hạn này nếu hiện tại chưa có đủ dữ liệu. Các thuộc tính fetch như `fetch.min.bytes` và `fetch.max.wait.ms` cũng ảnh hưởng việc broker gom dữ liệu trước khi trả về.

Batch là tập record mà consumer nhận từ lần poll đó. Nếu consumer subscribe nhiều topic hoặc nhiều partition, một batch có thể chứa record từ nhiều topic và partition khác nhau. Không được giả định mọi phần tử trong batch có cùng topic, partition hoặc key.

## 2. Hai chữ ký hàm được hỗ trợ

Với Spring Cloud Stream Kafka binder batch mode, hai dạng chữ ký chính được hỗ trợ là:

```java
Consumer<List<OrderCreated>>
Consumer<Message<List<OrderCreated>>>
```

Khác biệt nằm ở khả năng truy cập header:

| Chữ ký | Payload | Truy cập message headers |
| --- | --- | --- |
| `Consumer<List<OrderCreated>>` | Danh sách các `OrderCreated` | Không nhận được headers của message batch |
| `Consumer<Message<List<OrderCreated>>>` | Danh sách các `OrderCreated` qua `getPayload()` | Có thể đọc headers; metadata theo record là các collection song song với payload |

Nếu cần đối chiếu metadata từng record, hãy dùng `Message<List<T>>`. Dạng `List<Message<T>>` không được hỗ trợ cho batch consumption của Spring Cloud Stream Kafka binder. Không nhầm mô hình này với một số cách khai báo batch listener trực tiếp bằng `@KafkaListener` trong Spring Kafka.

## 3. Cấu trúc header của Message<List<T>>

Giả sử một batch có ba payload:

```text
payload[0] = OrderCreated("ORD-101")
payload[1] = OrderCreated("ORD-102")
payload[2] = OrderCreated("ORD-103")
```

Các header theo record được biểu diễn bằng collection có cùng thứ tự:

```text
kafka_receivedTopic     = ["orders.created", "orders.created", "orders.priority"]
kafka_receivedPartition = [2, 0, 1]
kafka_offset            = [501, 812, 77]
kafka_receivedMessageKey= ["ORD-101", "ORD-102", "ORD-103"]
```

Vì vậy, metadata của `payload[1]` nằm ở vị trí `1` trong từng collection header tương ứng:

| Index | Payload | Topic | Partition | Offset | Key |
| ---: | --- | --- | ---: | ---: | --- |
| 0 | `ORD-101` | `orders.created` | 2 | 501 | `ORD-101` |
| 1 | `ORD-102` | `orders.created` | 0 | 812 | `ORD-102` |
| 2 | `ORD-103` | `orders.priority` | 1 | 77 | `ORD-103` |

Đây là ví dụ minh họa. Giá trị thực tế phụ thuộc topic subscription, partition assignment, key, header mapper và cấu hình binder. Offset chỉ có ý nghĩa trong phạm vi một topic-partition; không so sánh hai offset thuộc partition khác nhau như thể chúng tạo thành một thứ tự toàn cục.

## 4. Đọc header Kafka theo từng phần tử

Spring Kafka cung cấp các hằng số trong `KafkaHeaders` để truy cập metadata của record. Với batch message, các header tương ứng có thể chứa collection:

- `KafkaHeaders.RECEIVED_TOPIC`: topic của từng record.
- `KafkaHeaders.RECEIVED_PARTITION`: partition của từng record.
- `KafkaHeaders.OFFSET`: offset của từng record.
- `KafkaHeaders.RECEIVED_KEY`: key của từng record, nếu có.
- `KafkaHeaders.RECEIVED_TIMESTAMP`: timestamp của từng record.

Ví dụ hàm consumer nhận `Message<List<OrderCreated>>`:

```java
import java.util.List;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

public record OrderCreated(String orderId, long totalCents) {}

@Configuration
public class OrderBatchConsumers {

    @Bean
    public Consumer<Message<List<OrderCreated>>> processOrders() {
        return batchMessage -> {
            List<OrderCreated> orders = batchMessage.getPayload();

            List<String> topics = headerList(
                    batchMessage, KafkaHeaders.RECEIVED_TOPIC);
            List<Integer> partitions = headerList(
                    batchMessage, KafkaHeaders.RECEIVED_PARTITION);
            List<Long> offsets = headerList(
                    batchMessage, KafkaHeaders.OFFSET);
            List<?> keys = headerList(
                    batchMessage, KafkaHeaders.RECEIVED_KEY);

            if (topics.size() != orders.size()
                    || partitions.size() != orders.size()
                    || offsets.size() != orders.size()) {
                throw new IllegalStateException(
                        "Batch payload and Kafka metadata are not aligned");
            }

            for (int i = 0; i < orders.size(); i++) {
                OrderCreated order = orders.get(i);
                String topic = topics.get(i);
                Integer partition = partitions.get(i);
                Long offset = offsets.get(i);
                Object key = i < keys.size() ? keys.get(i) : null;

                processOne(order, topic, partition, offset, key);
            }
        };
    }

    private static <T> List<T> headerList(
            Message<?> message, String headerName) {
        Object value = message.getHeaders().get(headerName);
        if (value instanceof List<?> values) {
            @SuppressWarnings("unchecked")
            List<T> result = (List<T>) values;
            return result;
        }
        return List.of();
    }

    private static void processOne(
            OrderCreated order,
            String topic,
            Integer partition,
            Long offset,
            Object key) {
        System.out.printf(
                "Order %s from %s-%d@%d, key=%s%n",
                order.orderId(), topic, partition, offset, key);
    }
}
```

Ví dụ dùng helper để kiểm tra kiểu header và giữ logic vòng lặp tập trung vào đối chiếu theo index. Trong code production, hãy xử lý rõ trường hợp header tùy chọn không tồn tại, giá trị null hoặc kiểu dữ liệu khác với kỳ vọng. Không nên ép kiểu mù quáng rồi giả định mọi binder/client đều trả về cùng một kiểu Java.

## 5. Quy tắc đồng bộ index giữa payload và header

Khi xử lý batch, index là mối liên kết giữa payload và metadata. Một vòng lặp an toàn phải lấy payload và tất cả header tại cùng một index:

```java
for (int i = 0; i < orders.size(); i++) {
    OrderCreated order = orders.get(i);
    String topic = topics.get(i);
    Integer partition = partitions.get(i);
    Long offset = offsets.get(i);

    audit(order, topic, partition, offset);
}
```

Tránh các cách làm sau:

- Dùng một header ở index `0` cho mọi payload trong batch.
- Sắp xếp riêng danh sách payload mà không sắp xếp các collection header tương ứng.
- Lọc hoặc loại bỏ một payload nhưng giữ nguyên danh sách header rồi tiếp tục dùng index cũ.
- Ghép payload với header bằng thứ tự của một `Map` hoặc bằng giả định mọi record cùng partition.
- Dùng offset đơn lẻ như metadata chung cho cả batch.

Nếu cần lọc hoặc sắp xếp batch, hãy tạo một cấu trúc trung gian chứa payload và metadata của cùng record trước khi biến đổi:

```java
public record OrderEnvelope(
        OrderCreated payload,
        String topic,
        int partition,
        long offset,
        Object key
) {}
```

Sau đó chuyển từng index thành một `OrderEnvelope`. Mọi thao tác lọc, sắp xếp hoặc phân nhóm sẽ giữ metadata gắn liền với payload, tránh làm lệch các danh sách song song.

## 6. Header ứng dụng riêng của từng record

Ngoài metadata Kafka như topic, partition, offset và key, producer có thể gửi các header ứng dụng như `correlationId`, `eventType` hoặc `tenantId`. Khi batch converter ánh xạ các header này, Spring Kafka có thể cung cấp header đặc biệt `KafkaHeaders.BATCH_CONVERTED_HEADERS`.

Header này có dạng danh sách các map; map ở vị trí `i` chứa các header đã chuyển đổi của record tương ứng với payload ở vị trí `i`.

Ví dụ:

```java
import java.util.List;
import java.util.Map;

import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

List<?> convertedHeaders = (List<?>) batchMessage.getHeaders()
        .get(KafkaHeaders.BATCH_CONVERTED_HEADERS);

for (int i = 0; i < orders.size(); i++) {
    Map<?, ?> recordHeaders = (Map<?, ?>) convertedHeaders.get(i);
    Object correlationId = recordHeaders.get("correlationId");
    Object eventType = recordHeaders.get("eventType");

    System.out.printf("%s: correlation=%s, type=%s%n",
            orders.get(i).orderId(), correlationId, eventType);
}
```

Trước khi truy cập, hãy kiểm tra header tồn tại, có đúng kiểu danh sách và có số phần tử bằng payload. `BATCH_CONVERTED_HEADERS` phụ thuộc header mapper; nếu không có mapper phù hợp, dữ liệu header native có thể được cung cấp theo dạng khác. Cần kiểm tra cấu hình mapper và phiên bản Spring Kafka của dự án.

`BATCH_CONVERTED_HEADERS` cũng có thể chứa tracing headers cho từng record. Batch có thể gồm record từ nhiều producer với trace context khác nhau, vì vậy không thể coi toàn batch có một `traceId` chung. Nếu muốn tạo observation hoặc span riêng, ứng dụng cần đọc map tương ứng của từng phần tử và thiết lập context cho đúng record.

## 7. Native headers và header đã chuyển đổi

Kafka record lưu header dưới dạng byte array. Spring Kafka dùng header mapper để chuyển chúng thành Spring Messaging headers có kiểu Java phù hợp. Trong batch, có thể gặp hai dạng dữ liệu:

| Dạng | Nội dung | Cách dùng |
| --- | --- | --- |
| Header đã chuyển đổi | Các giá trị header Java được ánh xạ; metadata theo record được biểu diễn bằng collection hoặc map theo từng phần tử | Phù hợp khi ứng dụng cần đọc header nghiệp vụ như chuỗi hoặc số |
| Native Kafka headers | Header gốc từ Kafka client, giữ tên và byte value theo API Kafka | Dùng khi cần tự giải mã hoặc cần truy cập header mà mapper không chuyển đổi |

Nếu dùng native headers, cần đối chiếu thứ tự phần tử với payload và tự giải mã byte value theo encoding mà producer đã thống nhất. Không giả định một header dạng byte có thể ép trực tiếp sang `String` mà không chỉ rõ charset.

Header mapper có thể lọc tên header, bỏ qua một số header nội bộ hoặc không chuyển đổi được giá trị tùy cấu hình. Vì vậy, nếu header nghiệp vụ bắt buộc phải có, hãy kiểm thử producer và consumer qua binder thật thay vì chỉ kiểm tra object `Message` được tạo trong unit test.

## 8. Batch header không phải metadata chung của cả lô

Một số header mô tả cả lần nhận hoặc container, nhưng nhiều header mô tả từng record. Cần phân biệt hai nhóm này trước khi viết logic:

| Loại thông tin | Ví dụ | Cách diễn giải |
| --- | --- | --- |
| Theo record | Topic, partition, offset, key, timestamp và converted headers | Giá trị ở index `i` thuộc payload ở index `i` |
| Theo batch/container | Thông tin consumer hoặc acknowledgment liên quan tới lần poll | Áp dụng cho lần nhận/batch, không gán cho từng payload như thể đó là metadata riêng |

Một batch có thể chứa nhiều partition. Nếu ứng dụng log một `partition` duy nhất cho toàn batch, log đó có thể gây hiểu nhầm hoặc sai hoàn toàn. Khi cần audit từng record, hãy ghi topic-partition-offset cùng event ID của chính payload đó.

Offset cũng không tạo ra thứ tự tổng thể giữa partition. Ví dụ offset 900 của partition 0 không nhất thiết xảy ra sau offset 120 của partition 3 theo thời gian nghiệp vụ. Nếu cần thứ tự theo aggregate, producer cần dùng key phù hợp để các sự kiện liên quan đi vào cùng partition và consumer cần xử lý tuần tự trong phạm vi đó.

## 9. Kiểm tra kích thước và tính toàn vẹn của metadata

Trước khi xử lý, có thể kiểm tra số lượng payload và collection header bắt buộc:

```java
private static void validateBatch(
        List<?> payloads,
        List<?> topics,
        List<?> partitions,
        List<?> offsets) {

    int size = payloads.size();
    if (topics.size() != size
            || partitions.size() != size
            || offsets.size() != size) {
        throw new IllegalArgumentException(
                "Payload and per-record metadata sizes differ");
    }
}
```

Không phải mọi header đều bắt buộc. Kafka key có thể null; header ứng dụng có thể vắng mặt; một mapper có thể không đưa header tùy chọn vào message. Chỉ kiểm tra kích thước với metadata mà logic thực sự cần. Với header tùy chọn, xử lý null hoặc thiếu giá trị một cách tường minh.

Nếu metadata bắt buộc bị thiếu, không nên âm thầm gắn giá trị của record khác vào payload. Hãy dừng xử lý batch hoặc xử lý lỗi theo chính sách đã định, ghi lại vị trí và event ID để có thể điều tra.

## 10. Xử lý lỗi chuyển đổi của từng phần tử

Trong batch conversion, một record có thể không chuyển đổi được dù các record khác trong cùng batch hợp lệ. Spring Kafka batch converter có thể biểu diễn payload lỗi dưới dạng `null` tại vị trí tương ứng và cung cấp thông tin lỗi chuyển đổi trong header `KafkaHeaders.CONVERSION_FAILURES` khi dùng cơ chế converter hỗ trợ.

Vì vậy, không được giả định mọi phần tử trong `List<T>` đều khác null. Nếu ứng dụng cần phân biệt lỗi chuyển đổi với payload nghiệp vụ null hợp lệ, hãy đọc conversion failure metadata theo index và xử lý rõ ràng.

Ví dụ kiểm tra phần tử trước khi gọi nghiệp vụ:

```java
for (int i = 0; i < orders.size(); i++) {
    OrderCreated order = orders.get(i);
    if (order == null) {
        // Đối chiếu KafkaHeaders.CONVERSION_FAILURES tại cùng index,
        // ghi nhận lỗi và áp dụng chính sách batch/error handling.
        continue;
    }

    processOne(order);
}
```

Không nên bỏ qua phần tử null mà không ghi nhận lý do. Nếu message không thể chuyển đổi do schema sai, cần có DLQ hoặc quy trình điều tra để dữ liệu không bị mất dấu.

## 11. Retry, DLQ và acknowledgment trong batch mode

Batch mode thay đổi phạm vi xử lý lỗi so với record mode:

- Retry nội bộ của Spring Cloud Stream binder không được hỗ trợ theo cách thông thường trong batch mode; `maxAttempts` bị ghi đè thành `1`.
- Có thể cấu hình `DefaultErrorHandler` qua `ListenerContainerCustomizer` để xây dựng hành vi retry phù hợp ở tầng listener container.
- Từ Spring Cloud Stream 4.0.2, Kafka binder hỗ trợ DLQ cho batch consumption. Khi dùng DLQ, toàn bộ record nhận từ lần poll trước có thể được gửi tới DLQ topic, không chỉ phần tử gây lỗi.
- Với manual acknowledgment, có thể dùng `Acknowledgment.nack(index, sleep)` để xác nhận phần trước index và yêu cầu các record còn lại được giao lại theo semantics của container.

Do đó, lựa chọn batch size có ảnh hưởng tới phạm vi redelivery và DLQ. Batch quá lớn có thể khiến nhiều record hợp lệ bị gửi lại hoặc chuyển DLQ cùng một record lỗi. Hãy thiết kế consumer idempotent và kiểm thử chính xác hành vi lỗi trên phiên bản binder thực tế.

## 12. Observability và tracing theo từng record

Batch listener không có một trace context chung tự nhiên cho mọi phần tử. Một batch có thể gom record từ nhiều partition, topic hoặc producer; mỗi record có thể có `traceparent` riêng hoặc không có tracing header.

Spring Cloud Stream Kafka binder không tự động truyền observation/tracing context cho batch theo cách record listener làm được. Khi nhận `Message<List<T>>`, ứng dụng có thể đọc `KafkaHeaders.BATCH_CONVERTED_HEADERS`, lấy tracing headers ở map tương ứng từng payload và tự tạo observation/span cho từng record nếu cần.

Khi log batch, nên ghi:

- Số lượng record trong batch.
- Event ID hoặc business key của từng record.
- Topic, partition, offset theo từng record khi cần truy vết.
- Correlation/trace ID theo từng record, không gộp thành một giá trị cho cả batch.
- Kết quả xử lý và lỗi theo index/event ID.

Không ghi payload nhạy cảm hoặc toàn bộ headers vào log một cách mặc định. Chọn metadata tối thiểu phục vụ truy vết và bảo vệ thông tin xác thực.

## 13. Ví dụ hoàn chỉnh: xử lý batch và audit metadata

Ví dụ dưới đây gom payload và metadata thành một cấu trúc trước khi xử lý:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

public record OrderRecordContext(
        OrderCreated order,
        String topic,
        Integer partition,
        Long offset,
        Object key,
        Object correlationId
) {}

public class OrderBatchHandler {

    public Consumer<Message<List<OrderCreated>>> processBatch() {
        return message -> {
            List<OrderCreated> payloads = message.getPayload();
            List<String> topics = requiredHeaderList(
                    message, KafkaHeaders.RECEIVED_TOPIC);
            List<Integer> partitions = requiredHeaderList(
                    message, KafkaHeaders.RECEIVED_PARTITION);
            List<Long> offsets = requiredHeaderList(
                    message, KafkaHeaders.OFFSET);
            List<?> keys = optionalHeaderList(
                    message, KafkaHeaders.RECEIVED_KEY);

            validateBatch(payloads, topics, partitions, offsets);

            List<?> converted = optionalHeaderList(
                    message, KafkaHeaders.BATCH_CONVERTED_HEADERS);

            List<OrderRecordContext> records = new ArrayList<>();
            for (int i = 0; i < payloads.size(); i++) {
                OrderCreated order = payloads.get(i);
                if (order == null) {
                    throw new IllegalStateException(
                            "Null payload at batch index " + i);
                }

                Object correlationId = null;
                if (i < converted.size()
                        && converted.get(i) instanceof Map<?, ?> headers) {
                    correlationId = headers.get("correlationId");
                }

                records.add(new OrderRecordContext(
                        order,
                        topics.get(i),
                        partitions.get(i),
                        offsets.get(i),
                        i < keys.size() ? keys.get(i) : null,
                        correlationId));
            }

            records.forEach(this::processOne);
        };
    }

    private static <T> List<T> requiredHeaderList(
            Message<?> message, String name) {
        List<T> values = optionalHeaderList(message, name);
        if (values.isEmpty()) {
            throw new IllegalStateException("Missing batch header: " + name);
        }
        return values;
    }

    private static <T> List<T> optionalHeaderList(
            Message<?> message, String name) {
        Object value = message.getHeaders().get(name);
        if (value instanceof List<?> list) {
            @SuppressWarnings("unchecked")
            List<T> typed = (List<T>) list;
            return typed;
        }
        return List.of();
    }

    private static void validateBatch(
            List<?> payloads,
            List<?> topics,
            List<?> partitions,
            List<?> offsets) {
        int size = payloads.size();
        if (topics.size() != size
                || partitions.size() != size
                || offsets.size() != size) {
            throw new IllegalStateException(
                    "Payload and metadata collections are misaligned");
        }
    }

    private void processOne(OrderRecordContext context) {
        System.out.printf("Processing %s at %s-%d@%d, correlation=%s%n",
                context.order().orderId(),
                context.topic(),
                context.partition(),
                context.offset(),
                context.correlationId());
    }
}
```

Đây là ví dụ minh họa cách tổ chức code; cần bổ sung constructor, bean registration, model và chính sách lỗi phù hợp dự án. Trong ứng dụng thực tế, có thể tách helper đọc header và bước ánh xạ thành một component riêng để dễ kiểm thử.

## 14. Kiểm thử đối chiếu payload và header

Unit test nên xác minh metadata tại cùng index được gắn với đúng payload. Có thể tạo `Message<List<OrderCreated>>` bằng `MessageBuilder` với các header dạng list:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class BatchHeaderMappingTest {

    @Test
    void alignsHeadersWithPayloadIndex() {
        List<OrderCreated> orders = List.of(
                new OrderCreated("ORD-1", 1000),
                new OrderCreated("ORD-2", 2000));

        Message<List<OrderCreated>> message = MessageBuilder
                .withPayload(orders)
                .setHeader(KafkaHeaders.RECEIVED_TOPIC,
                        List.of("orders.created", "orders.priority"))
                .setHeader(KafkaHeaders.RECEIVED_PARTITION,
                        List.of(1, 0))
                .setHeader(KafkaHeaders.OFFSET,
                        List.of(10L, 25L))
                .build();

        List<?> topics = (List<?>) message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC);
        List<?> offsets = (List<?>) message.getHeaders()
                .get(KafkaHeaders.OFFSET);

        assertEquals("orders.created", topics.get(0));
        assertEquals(10L, offsets.get(0));
        assertEquals("orders.priority", topics.get(1));
        assertEquals(25L, offsets.get(1));
    }
}
```

Kiểm thử này xác minh hợp đồng index của code ứng dụng, nhưng không chứng minh Kafka binder thực tế tạo đúng batch headers. Cần thêm integration test với Kafka để xác nhận metadata được ánh xạ đúng qua poll, batch converter và header mapper.

## 15. Các tình huống integration test cần có

Với batch consumer, nên kiểm tra tối thiểu:

1. Một batch chỉ có một record.
2. Một batch có nhiều record từ cùng partition.
3. Một batch có record từ nhiều partition.
4. Một batch nhận dữ liệu từ nhiều topic nếu binding subscribe nhiều topic.
5. Record có key null hoặc thiếu application header.
6. Header tùy chỉnh được ánh xạ vào `BATCH_CONVERTED_HEADERS` đúng index.
7. Một payload không chuyển đổi được và conversion failure được nhận diện tại đúng index.
8. Batch có phần tử lỗi và hành vi retry/DLQ/acknowledgment đúng cấu hình.
9. Consumer restart hoặc rebalance khi đang xử lý batch.
10. Batch size thay đổi theo `max.poll.records` và lượng dữ liệu sẵn có.

Test binder hữu ích để kiểm tra hàm và binding, nhưng không thay thế integration test với Kafka khi cần xác minh offset, partition, header mapping, batch conversion và DLQ.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không đọc được header trong hàm | Hàm nhận `List<T>` thay vì `Message<List<T>>` | Đổi chữ ký sang `Message<List<T>>` nếu cần metadata. |
| Mỗi payload nhận cùng một partition/offset | Code lấy header ở index 0 rồi dùng cho toàn batch | Lấy collection header và truy cập theo cùng index với payload. |
| `ClassCastException` khi đọc header | Ép kiểu sai hoặc header mapper trả kiểu khác | Kiểm tra kiểu runtime và cấu hình mapper trước khi ép kiểu. |
| Header collection ngắn hơn payload | Header tùy chọn bị thiếu, mapping không đồng nhất hoặc giả định sai | Kiểm tra header bắt buộc, dừng xử lý khi dữ liệu không nhất quán. |
| `List<Message<T>>` không được bind | Chữ ký không thuộc dạng batch được Kafka binder hỗ trợ | Dùng `List<T>` hoặc `Message<List<T>>`. |
| Tracing chỉ có một context cho cả batch | Coi batch là một message nghiệp vụ duy nhất | Đọc `BATCH_CONVERTED_HEADERS` và xử lý tracing theo từng record. |
| Nhiều record bị chuyển DLQ khi một record lỗi | Batch DLQ áp dụng cho toàn bộ poll batch theo cấu hình binder | Đánh giá batch size, retry, manual nack và tính idempotent. |
| Record null bị bỏ qua âm thầm | Conversion failure hoặc KafkaNull không được xử lý | Kiểm tra null và conversion failure metadata theo index. |

## 17. Quy trình xử lý batch an toàn

Khi xây dựng một batch consumer cần đối chiếu header, hãy thực hiện theo trình tự:

1. Bật `consumer.batch-mode` cho đúng input binding.
2. Chọn chữ ký `Message<List<T>>` nếu cần metadata.
3. Xác định header nào là metadata theo record và header nào là metadata cấp batch.
4. Lấy collection header bằng hằng số `KafkaHeaders` thay vì hard-code tên nếu có thể.
5. Kiểm tra kiểu, sự tồn tại và số phần tử của các header bắt buộc.
6. Ghép payload và metadata bằng cùng một index.
7. Chuyển thành record context/envelope nếu cần lọc, sắp xếp hoặc xử lý song song.
8. Xử lý null payload và conversion failure rõ ràng.
9. Thiết kế retry, DLQ và acknowledgment theo phạm vi batch.
10. Kiểm thử với batch nhiều partition và quan sát theo event ID/topic-partition-offset.

## Tài liệu tham khảo

- [Spring Cloud Stream Kafka Binder — Consuming Batches](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/consume-batches.html)
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring for Apache Kafka — Batch Listener Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)

Hãy đối chiếu tài liệu của phiên bản Spring Cloud Stream Kafka binder và Spring Kafka đang dùng, đặc biệt về batch header mapping, conversion failure, tracing và acknowledgment.

## Kết luận

Trong Kafka batch mode của Spring Cloud Stream, `List<T>` chỉ cung cấp payload; muốn đọc metadata cần dùng `Message<List<T>>`. Các header theo record được biểu diễn bằng collection có thứ tự tương ứng với payload, vì vậy phải truy cập cùng index. `KafkaHeaders.BATCH_CONVERTED_HEADERS` cung cấp map header đã chuyển đổi cho từng phần tử khi mapper hỗ trợ. Kiểm tra kiểu và kích thước header, giữ payload cùng metadata trong một cấu trúc, và kiểm thử batch nhiều partition giúp tránh gắn nhầm topic, partition, offset, key hoặc correlation ID cho sự kiện.
