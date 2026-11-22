# ByteArraySerializer cho payload nhị phân

## 1. Payload nhị phân trong Kafka là gì?

Kafka lưu key và value của mỗi record dưới dạng byte. Producer chuyển kiểu dữ liệu của ứng dụng thành mảng byte trước khi gửi; consumer nhận byte rồi chuyển chúng về dạng mà nghiệp vụ có thể sử dụng. Quá trình chuyển đổi hai chiều này gọi là serialization và deserialization.

Với dữ liệu văn bản hoặc object, ứng dụng thường dùng serializer như `StringSerializer` hoặc `JsonSerializer`. Với payload đã ở dạng byte, Kafka cung cấp `ByteArraySerializer`. Serializer này chuyển trực tiếp `byte[]` thành value của record mà không mã hóa JSON, chuyển thành chuỗi hay thêm cấu trúc dữ liệu riêng.

Các loại payload nhị phân thường gặp:

- Nội dung PDF, ảnh, âm thanh hoặc tệp đính kèm.
- Dữ liệu đã được mã hóa hoặc nén ở tầng ứng dụng.
- Một thông điệp đã được encode bằng định dạng nhị phân như Protobuf hoặc một định dạng nội bộ.
- Khối dữ liệu do một hệ thống khác cung cấp dưới dạng `byte[]`.

Trong Spring Kafka, `ByteArraySerializer` phù hợp khi ứng dụng đã có sẵn byte cần gửi và muốn Kafka vận chuyển nguyên dạng. Nó không tự hiểu cấu trúc PDF, ảnh, Protobuf hay định dạng nghiệp vụ nào khác.

## 2. Luồng serialization và deserialization

Producer gửi `byte[]` qua `KafkaTemplate`, Kafka producer dùng `ByteArraySerializer` để tạo value byte của record. Ở phía nhận, consumer dùng `ByteArrayDeserializer` để lấy lại mảng byte.

~~~mermaid
flowchart LR
    A["Ứng dụng tạo payload byte[]"] --> B["KafkaTemplate<String, byte[]>"]
    B --> C["ByteArraySerializer"]
    C --> D["Kafka record: key + value bytes + headers"]
    D --> E["Kafka topic"]
    E --> F["ByteArrayDeserializer"]
    F --> G["@KafkaListener nhận byte[]"]
    G --> H["Ứng dụng giải mã / xử lý nội dung"]
~~~

Cần dùng serializer và deserializer tương thích:

| Phía gửi | Phía nhận | Kiểu value ở ứng dụng |
|---|---|---|
| `ByteArraySerializer` | `ByteArrayDeserializer` | `byte[]` |
| `StringSerializer` | `StringDeserializer` | `String` |
| `JsonSerializer` | `JsonDeserializer` tương ứng | Object Java theo cấu hình type và trusted packages |

Nếu producer gửi byte nhưng consumer lại cấu hình `StringDeserializer` hoặc `JsonDeserializer`, consumer có thể lỗi khi đọc hoặc diễn giải payload sai. Ngược lại, nếu producer dùng `JsonSerializer` nhưng consumer nhận `byte[]`, byte nhận được là biểu diễn JSON đã serialize chứ không phải object Java ban đầu.

`ByteArraySerializer` không thêm schema, tên class hay thông tin kiểu vào payload. Producer và consumer phải thống nhất hợp đồng dữ liệu bằng cách khác, chẳng hạn header, phiên bản định dạng hoặc metadata đã được quy định trong payload.

## 3. Cấu hình ByteArraySerializer trong Spring Boot

Có thể cấu hình producer và consumer trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.ByteArraySerializer
      acks: all
      properties:
        enable.idempotence: true

    consumer:
      group-id: document-processor
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.ByteArrayDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest

    listener:
      type: single
      ack-mode: record
~~~

Ý nghĩa các thuộc tính chính:

- `key-serializer` dùng `StringSerializer` để chuyển key kiểu `String` thành byte.
- `value-serializer` dùng `ByteArraySerializer` để gửi trực tiếp mảng byte.
- `key-deserializer` và `value-deserializer` phải khớp với kiểu key/value mà producer ghi.
- `acks: all` yêu cầu xác nhận theo quy tắc ISR của Kafka; độ bền dữ liệu còn phụ thuộc replication factor và `min.insync.replicas`.
- `enable-auto-commit: false` để Spring Kafka listener container quản lý offset theo ack mode.
- `auto-offset-reset: earliest` chỉ quyết định vị trí bắt đầu khi group chưa có offset hợp lệ.

Khi dùng Spring Boot với cấu hình trên, auto-configuration thường tạo `ProducerFactory`, `ConsumerFactory` và `KafkaTemplate` tương ứng. Có thể inject `KafkaTemplate<String, byte[]>` vào publisher. Nếu ứng dụng có nhiều kiểu payload hoặc nhiều cụm Kafka, hãy khai báo factory và template riêng để kiểu generic, serializer và cấu hình không bị trộn lẫn.

## 4. Gửi payload byte[] bằng KafkaTemplate

Giả sử dịch vụ tài liệu nhận nội dung tệp từ một thành phần khác dưới dạng `byte[]`. Publisher có thể gửi byte trực tiếp, đồng thời dùng document ID làm key để các sự kiện của cùng tài liệu được định tuyến nhất quán:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class DocumentPublisher {

    private final KafkaTemplate<String, byte[]> kafkaTemplate;

    public DocumentPublisher(KafkaTemplate<String, byte[]> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, byte[]>> publish(
            String documentId,
            String contentType,
            byte[] content) {

        ProducerRecord<String, byte[]> record =
            new ProducerRecord<>("documents", documentId, content);

        record.headers().add(
            "content-type",
            contentType.getBytes(StandardCharsets.UTF_8)
        );

        record.headers().add(
            "payload-format-version",
            new byte[] { 1 }
        );

        return kafkaTemplate.send(record);
    }
}
~~~

Trong ví dụ:

- Topic là `documents`.
- Key là `documentId`.
- Value là nguyên mảng `content`.
- Header `content-type` mô tả định dạng nội dung, ví dụ `application/pdf` hoặc `image/png`.
- Header `payload-format-version` là metadata phiên bản của hợp đồng payload do ứng dụng quy ước.

`ProducerRecord` cho phép kiểm soát topic, partition tùy chọn, timestamp, key, value và headers. Nếu chỉ cần gửi topic, key và byte array, có thể gọi overload ngắn hơn:

~~~java
kafkaTemplate.send("documents", documentId, content);
~~~

Gửi bất đồng bộ không có nghĩa record đã được broker xác nhận ngay khi phương thức trả về. Với luồng cần theo dõi kết quả, hãy quan sát future:

~~~java
documentPublisher.publish(documentId, "application/pdf", content)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error("Không gửi được tài liệu documentId={}", documentId, error);
            return;
        }

        var metadata = result.getRecordMetadata();
        log.info(
            "Đã gửi documentId={} topic={} partition={} offset={}",
            documentId,
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
~~~

Future hoàn tất thành công khi producer nhận xác nhận theo cấu hình `acks`. Điều đó xác nhận việc ghi record theo chính sách producer, không xác nhận consumer đã tải hoặc xử lý nội dung tệp.

## 5. Tạo byte[] từ nguồn dữ liệu

Nếu nguồn dữ liệu vốn đã là byte array, không cần chuyển đổi qua `String` hoặc Base64. Ví dụ đọc một tệp nhỏ:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

byte[] content = Files.readAllBytes(Path.of("sample.pdf"));

documentPublisher.publish(
    "DOC-1001",
    "application/pdf",
    content
);
~~~

`Files.readAllBytes` đọc toàn bộ tệp vào bộ nhớ. Cách này phù hợp với payload nhỏ có kích thước được kiểm soát. Với tệp lớn, không nên mặc định đọc toàn bộ vào heap rồi gửi trong một record. Hãy cân nhắc lưu nội dung ở object storage hoặc hệ thống tệp phân tán, sau đó chỉ gửi metadata và tham chiếu như object key, URI, checksum và kích thước qua Kafka.

Nếu dữ liệu đến từ một API hoặc một thành phần tạo nội dung, hãy giữ nó dưới dạng `byte[]` xuyên suốt đường gửi. Chuyển byte sang chuỗi UTF-8 chỉ phù hợp khi dữ liệu thực sự là văn bản UTF-8. Với PDF, ảnh, âm thanh hoặc dữ liệu nén, thao tác chuyển đổi chuỗi có thể làm hỏng byte.

Không dùng Base64 chỉ để gửi dữ liệu nhị phân trong Kafka nếu cả producer và consumer đều có thể trao đổi `byte[]`. Base64 làm payload lớn hơn khoảng một phần ba và tạo thêm chi phí encode/decode. Chỉ dùng Base64 khi hợp đồng tích hợp bắt buộc truyền nội dung nhị phân bên trong một định dạng văn bản.

## 6. Nhận payload byte[] ở consumer

Consumer cần cấu hình `ByteArrayDeserializer`. Listener có thể nhận trực tiếp `byte[]` nếu chỉ cần nội dung:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class DocumentListener {

    private final DocumentService documentService;

    public DocumentListener(DocumentService documentService) {
        this.documentService = documentService;
    }

    @KafkaListener(
        topics = "documents",
        groupId = "document-processor"
    )
    public void handle(byte[] content) {
        documentService.process(content);
    }
}
~~~

Nếu cần key và header, nhận `ConsumerRecord<String, byte[]>`:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class DocumentMetadataListener {

    private final DocumentService documentService;

    public DocumentMetadataListener(DocumentService documentService) {
        this.documentService = documentService;
    }

    @KafkaListener(
        topics = "documents",
        groupId = "document-metadata-processor"
    )
    public void handle(ConsumerRecord<String, byte[]> record) {
        byte[] content = record.value();

        Header contentTypeHeader =
            record.headers().lastHeader("content-type");

        String contentType = contentTypeHeader == null
            ? "application/octet-stream"
            : new String(
                contentTypeHeader.value(),
                StandardCharsets.UTF_8
            );

        documentService.process(
            record.key(),
            contentType,
            content
        );
    }
}
~~~

`ConsumerRecord` hữu ích khi consumer cần:

- Key để liên kết nội dung với tài liệu hoặc thực thể nghiệp vụ.
- Header để biết content type, phiên bản payload hoặc correlation ID.
- Topic, partition và offset để log, tracing và điều tra lỗi.
- Timestamp để phục vụ nghiệp vụ hoặc quan sát độ trễ.

Nếu listener chỉ cần byte array, chữ ký `handle(byte[] content)` ngắn và dễ kiểm thử hơn. Không đưa metadata Kafka vào domain model nếu nghiệp vụ không cần biết chi tiết vận chuyển.

## 7. Header và hợp đồng của payload nhị phân

Vì `ByteArraySerializer` không mang theo thông tin kiểu, producer và consumer cần thống nhất cách diễn giải byte. Header Kafka là nơi phù hợp để truyền metadata vận chuyển như:

| Header gợi ý | Ví dụ | Mục đích |
|---|---|---|
| `content-type` | `application/pdf` | Cho biết loại nội dung |
| `payload-format-version` | `1` | Chọn bộ giải mã hoặc quy tắc đọc tương ứng |
| `event-id` | `evt-9a81` | Nhận diện sự kiện qua retry và xử lý trùng |
| `correlation-id` | `req-123` | Liên kết log giữa các dịch vụ |
| `content-encoding` | `gzip` | Cho biết payload đã được nén ở tầng ứng dụng |
| `content-length` | `20480` | Kích thước byte gốc theo hợp đồng ứng dụng |

Header Kafka cũng là byte array. Khi ghi chuỗi vào header, hãy chọn encoding rõ ràng, thường là UTF-8; khi đọc phải dùng cùng encoding. Không giả định mọi header đều là chuỗi.

Với payload có cấu trúc nhị phân, hợp đồng nên mô tả:

1. Cấu trúc byte và thứ tự trường.
2. Phiên bản định dạng.
3. Quy tắc mã hóa số, chuỗi và thời gian.
4. Cách xử lý trường thiếu hoặc trường mới.
5. Quy tắc tương thích giữa producer và consumer.
6. Giới hạn kích thước và cách kiểm tra dữ liệu lỗi.

Có thể đặt một byte magic/version ở đầu payload nếu định dạng cần tự mô tả, hoặc dùng header phiên bản nếu toàn bộ hệ thống bảo đảm header luôn đi cùng value. Dù chọn cách nào, consumer phải kiểm tra phiên bản trước khi giải mã.

Nếu dùng Protobuf, Avro hoặc một định dạng có schema registry, hãy cân nhắc serializer/deserializer chuyên dụng của định dạng đó. `ByteArraySerializer` chỉ vận chuyển kết quả byte đã encode; nó không đăng ký schema, không quản lý schema evolution và không tự giải mã object.

## 8. Phân biệt null và mảng byte rỗng

Một giá trị `byte[]` có thể là `null`, hoặc là một mảng hợp lệ có độ dài bằng 0:

~~~java
byte[] noValue = null;
byte[] emptyPayload = new byte[0];
~~~

Hai trường hợp này không giống nhau:

- `null` value được Kafka sử dụng làm tombstone trong compacted topic. Tombstone biểu thị việc xóa key tương ứng theo ngữ nghĩa log compaction.
- `new byte[0]` là một value tồn tại nhưng có độ dài bằng 0.

Consumer nên xử lý rõ trường hợp `record.value() == null`, đặc biệt khi topic bật log compaction. Không nên mặc định mọi null đều là tệp rỗng hoặc payload bị hỏng.

~~~java
if (record.value() == null) {
    // Xử lý tombstone hoặc null value theo hợp đồng topic.
    return;
}

if (record.value().length == 0) {
    // Payload tồn tại nhưng rỗng; quyết định theo quy tắc nghiệp vụ.
    throw new IllegalArgumentException("Payload tài liệu rỗng");
}
~~~

Với topic tài liệu thông thường không dùng compact theo key, hãy quy định rõ null có được phép hay không. Kiểm tra null trước khi xử lý byte giúp tránh `NullPointerException` và tránh nhầm tombstone với nội dung rỗng.

## 9. Kích thước record, bộ nhớ và compression

Payload nhị phân có thể lớn hơn nhiều so với sự kiện JSON thông thường. Kafka có các giới hạn kích thước ở producer, broker, topic và consumer. Nếu chỉ tăng một phía, producer có thể gửi được nhưng broker hoặc consumer vẫn từ chối hay không fetch được record.

Các cấu hình cần xem xét:

| Thành phần | Thuộc tính | Vai trò |
|---|---|---|
| Producer | `max.request.size` | Giới hạn kích thước request gửi; ảnh hưởng khả năng gửi record batch lớn |
| Broker | `message.max.bytes` | Giới hạn kích thước record batch broker chấp nhận |
| Topic | `max.message.bytes` | Có thể ghi đè giới hạn batch ở cấp topic |
| Consumer | `max.partition.fetch.bytes` | Giới hạn lượng dữ liệu fetch cho một partition |
| Consumer | `fetch.max.bytes` | Giới hạn tổng dữ liệu fetch cho một request |
| Broker replica | `replica.fetch.max.bytes` | Giới hạn dữ liệu replica fetch từ leader |

Giới hạn thực tế phụ thuộc phiên bản Kafka và cách triển khai cluster. Khi tăng kích thước, cần kiểm tra cả producer, broker/topic, replica fetch và consumer fetch. Một số cấu hình fetch có thể cho phép trả về batch đầu tiên lớn hơn giới hạn để consumer tiếp tục tiến triển, nhưng không nên dựa vào ngoại lệ đó như chính sách thiết kế.

Ví dụ cấu hình producer:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        max.request.size: 2097152
~~~

Con số trên chỉ là ví dụ giới hạn request 2 MiB; cần chọn theo kích thước payload và giới hạn cluster thực tế. Không đặt giới hạn quá lớn nếu không có nhu cầu vì record lớn làm tăng heap usage, thời gian truyền, độ trễ, áp lực replication và thời gian xử lý consumer.

### Compression không thuộc trách nhiệm của ByteArraySerializer

`ByteArraySerializer` chỉ chuyển `byte[]` thành value của record. Nén Kafka là cơ chế riêng của producer và record batch. Có thể cấu hình `compression.type` với codec mà phiên bản Kafka client và broker hỗ trợ, ví dụ `gzip`, `snappy`, `lz4` hoặc `zstd`.

~~~yaml
spring:
  kafka:
    producer:
      properties:
        compression.type: zstd
~~~

Kafka giải nén ở phía consumer trước khi deserializer trả value cho ứng dụng. Vì vậy, ứng dụng vẫn nhận byte payload ban đầu. Nếu payload đã được nén ở tầng ứng dụng, cần dùng header như `content-encoding` và tự giải nén trong consumer; không nhầm nén nội dung với compression của Kafka.

Một số loại dữ liệu như PDF hoặc JPEG vốn đã nén, nên nén thêm có thể không giảm kích thước đáng kể. Hãy đo dữ liệu thực tế trước khi chọn codec và cấu hình.

## 10. Bảo mật và tính toàn vẹn của payload

Payload nhị phân có thể chứa tài liệu, hình ảnh hoặc dữ liệu nhạy cảm. Không ghi toàn bộ byte ra log và không đưa payload nguyên vẹn vào exception message. Hãy log metadata cần thiết như event ID, document ID, kích thước, content type, topic, partition và offset.

Nếu cần mã hóa đầu cuối ở tầng ứng dụng, producer có thể mã hóa byte trước khi gọi `send`; consumer giải mã sau khi nhận. Khi đó, cần quản lý khóa, nonce/IV, thuật toán, phiên bản mã hóa và quy trình xoay khóa theo một hợp đồng rõ ràng. TLS cho kết nối Kafka bảo vệ dữ liệu trên đường truyền giữa client và broker, nhưng không thay thế mã hóa payload nếu broker hoặc các hệ thống trung gian không được phép đọc nội dung.

Có thể tính checksum như SHA-256 để phát hiện nội dung thay đổi hoặc xác minh dữ liệu sau khi lưu trữ:

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public String sha256(byte[] content) throws NoSuchAlgorithmException {
    byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(content);

    return HexFormat.of().formatHex(digest);
}
~~~

Checksum hỗ trợ kiểm tra tính toàn vẹn, nhưng không phải chữ ký số và không chứng minh nguồn gửi đáng tin cậy. Nếu cần xác thực nguồn phát, dùng chữ ký số hoặc cơ chế xác thực phù hợp với mô hình bảo mật.

## 11. Kiểm thử ByteArraySerializer

Kiểm thử nên xác minh byte gửi đi được nhận lại nguyên vẹn, không chỉ xác minh listener đã được gọi.

Với unit test cho publisher, có thể mock `KafkaTemplate` để kiểm tra topic, key, value và headers. Với integration test dùng Embedded Kafka hoặc Testcontainers, gửi byte thực qua broker rồi đọc lại bằng consumer cấu hình `ByteArrayDeserializer`.

Ví dụ kiểm tra nội dung:

~~~java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;

byte[] original = new byte[] {
    0x00, 0x01, 0x02, (byte) 0x80, (byte) 0xFF
};

kafkaTemplate.send("binary-documents", "DOC-1", original)
    .get(10, TimeUnit.SECONDS);

// Helper của test poll consumer cho đến khi nhận record hoặc hết timeout.
ConsumerRecord<String, byte[]> received = pollForRecord();

assertThat(received.key()).isEqualTo("DOC-1");
assertThat(received.value()).containsExactly(original);
~~~

Các trường hợp nên kiểm thử:

- Byte array có byte `0x00`, byte âm theo kiểu Java và byte ngoài ASCII.
- Payload rỗng và null theo chính sách topic.
- Header content type và payload version được giữ nguyên.
- Payload ở kích thước gần giới hạn được chấp nhận.
- Consumer cấu hình nhầm deserializer phải phát hiện qua integration test.
- Payload không đúng định dạng hoặc phiên bản không hỗ trợ được xử lý như lỗi dữ liệu.

Đừng dùng `new String(bytes)` để so sánh payload nhị phân. Chuyển đổi đó dùng charset mặc định và có thể làm thay đổi byte. Hãy so sánh bằng `Arrays.equals`, AssertJ `containsExactly` hoặc checksum.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| Producer báo lỗi serialization | Value không phải `byte[]` nhưng dùng `ByteArraySerializer` | Kiểm tra kiểu generic và kiểu value truyền vào |
| Consumer lỗi khi deserialize | Consumer dùng `StringDeserializer` hoặc `JsonDeserializer` | Cấu hình `ByteArrayDeserializer` |
| Payload bị hỏng sau khi nhận | Byte bị chuyển sang String/Base64 không đúng hợp đồng | Giữ nguyên byte hoặc dùng encoding được thống nhất |
| Consumer không biết cách đọc payload | Thiếu content type hoặc version | Quy định header/format version và validate trước khi decode |
| Gửi payload lớn thất bại | Giới hạn producer, broker/topic hoặc fetch không tương thích | Đối chiếu các giới hạn kích thước trên toàn đường truyền |
| Heap tăng cao | Đọc nhiều tệp lớn vào `byte[]`, giữ nhiều bản sao trong bộ nhớ | Giới hạn payload/concurrency hoặc chuyển nội dung lớn sang object storage |
| Nội dung bị xử lý như tombstone | Producer gửi null value | Phân biệt null với mảng byte rỗng và quy định rõ semantics |

Khi gặp lỗi, kiểm tra theo thứ tự: kiểu dữ liệu thực tế ở publisher, serializer của producer, topic và giới hạn kích thước, deserializer của consumer, rồi mới đến bộ giải mã nghiệp vụ.

## 13. Khi nào nên dùng ByteArraySerializer?

Dùng `ByteArraySerializer` khi ứng dụng đã có dữ liệu ở dạng byte và muốn vận chuyển chính xác byte đó qua Kafka. Đây là lựa chọn phù hợp cho tệp nhỏ, payload nhị phân, dữ liệu đã encode hoặc định dạng mà producer/consumer đã thống nhất.

Cân nhắc một giải pháp khác khi:

- Payload là object nghiệp vụ cần schema và hỗ trợ thay đổi phiên bản: cân nhắc JSON, Avro hoặc Protobuf.
- Tệp quá lớn hoặc cần tải theo luồng: lưu nội dung ở object storage, gửi metadata và tham chiếu qua Kafka.
- Hệ thống cần schema registry hoặc serializer có khả năng quản lý schema: dùng serializer chuyên biệt thay vì chỉ chuyển dữ liệu thành byte thủ công.
- Nội dung là văn bản thuần: `StringSerializer` thường dễ đọc và dễ vận hành hơn.

Checklist trước khi triển khai:

- [ ] Producer dùng `ByteArraySerializer` cho value `byte[]`.
- [ ] Consumer dùng `ByteArrayDeserializer` cho value `byte[]`.
- [ ] Key serializer/deserializer khớp với kiểu key.
- [ ] Hợp đồng payload quy định content type, version và encoding.
- [ ] Null value được phân biệt với byte array rỗng.
- [ ] Kích thước record phù hợp giới hạn producer, broker/topic và consumer.
- [ ] Compression được cấu hình riêng nếu cần.
- [ ] Payload nhạy cảm không bị ghi nguyên vẹn vào log.
- [ ] Kiểm thử xác minh byte nhận được giống byte gửi đi.

`ByteArraySerializer` giúp Spring Kafka gửi payload nhị phân mà không chuyển đổi nội dung. Để vận hành đáng tin cậy, producer và consumer cần thống nhất deserializer, metadata và phiên bản định dạng; đồng thời kiểm soát kích thước, bộ nhớ, bảo mật và cách xử lý payload lỗi.
