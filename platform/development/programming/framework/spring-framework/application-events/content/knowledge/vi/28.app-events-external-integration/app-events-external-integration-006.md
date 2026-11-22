# Schema Registry và versioning khi tích hợp Spring Application Events ra ngoài ứng dụng

## 1. Tại sao event cần schema registry?

Trong một ứng dụng Spring, `ApplicationEventPublisher.publishEvent(...)` thường truyền một đối tượng Java giữa các thành phần cùng tiến trình. Producer và listener có thể cùng được build/deploy, nên compiler hỗ trợ phát hiện nhiều lỗi thay đổi kiểu ngay lúc biên dịch.

Khi một sự kiện cần đến các service độc lập qua Kafka, RabbitMQ hoặc hạ tầng messaging khác, ranh giới thay đổi:

- Producer và consumer có thể dùng **phiên bản ứng dụng khác nhau** trong giai đoạn rolling deployment.
- Consumer có thể đọc một message lưu từ nhiều tháng trước, bằng code mới.
- Một event có thể được đọc bởi Java, Go, Python hoặc một hệ thống analytics.
- Không còn bảo đảm mọi phía cùng biết một class Java, enum hoặc tên package.
- Broker lưu/định tuyến message, nhưng không tự hiểu ý nghĩa của tất cả field nghiệp vụ.

**Schema** là bản mô tả kiểu/cấu trúc dữ liệu trên đường truyền: các field, kiểu dữ liệu, giá trị mặc định và một số quy tắc diễn giải. **Schema Registry** là dịch vụ lưu, đánh phiên bản và tra cứu schema, thường kèm chính sách kiểm tra tương thích trước khi chấp nhận một phiên bản mới.

Ví dụ một service phát `order.placed` phiên bản cũ chỉ có mã đơn và số tiền. Phiên bản mới muốn thêm đồng tiền:

```json
{
  "orderId": "ORD-101",
  "amountMinorUnits": 12500,
  "currency": "USD"
}
```

Nếu consumer cũ không hiểu field mới, hoặc consumer mới đọc lịch sử mà không có `currency`, deployment có thể gây lỗi hay — nguy hiểm hơn — diễn giải dữ liệu sai. Schema registry giúp kiểm tra **một phần hợp đồng dữ liệu**, nhưng **không thay thế contract test về ngữ nghĩa nghiệp vụ**.

**Phạm vi:** Bài trình bày Schema Registry với Avro và Kafka/Confluent làm ví dụ cụ thể; các nguyên tắc versioning cũng dùng được với Protobuf, JSON Schema và broker khác, nhưng quy tắc tương thích và wire format của từng công nghệ **không giống nhau**.

## 2. Phân biệt bốn lớp của một hệ thống event

```text
[Domain/Application Layer]
      OrderPlaced (record/POJO Java)
           |
           | ApplicationEventPublisher.publishEvent(...)
           v
      @EventListener (bridge/adapter)
           |
           | map sang integration event
           v
[Integration Contract Layer]
      eventType=order.placed
      schema Avro v1 / v2 ...
           |
           | serializer tra cứu/đăng ký schema
           v
[Transport Layer]
      Kafka topic / message broker
      bytes + headers + key
           |
           | consumer lấy schema của payload
           v
[Consumer Layer]
      deserializer -> dữ liệu đã decode
      validation -> business handler -> ACK/offset
```

Cần trả lời rõ **schema registry quản lý cái gì**:

- Quản lý một tập **schema theo subject**.
- Ghi nhận **version** của từng schema trong subject.
- Cấp hoặc tra cứu **schema ID** để deserializer biết dùng định nghĩa nào.
- Có thể **từ chối đăng ký schema mới** nếu không đạt compatibility policy.
- Cung cấp REST API/client để producer, consumer và CI kiểm tra hợp đồng.

Và nó **không quản lý**:

- Việc Spring có đăng ký bean `@EventListener` hay không.
- Thời điểm commit/rollback của database.
- Broker có thực sự lưu và phân phối được message hay không.
- Consumer đã gọi API bên ngoài thành công hay chưa.
- Idempotency, retry, DLQ hoặc exactly-once business effect.
- Ý nghĩa nghiệp vụ của một giá trị như `amountMinorUnits` là cent hay đồng.

**Schema Registry không phải message broker.** Producer vẫn cần Kafka/RabbitMQ và các cơ chế gửi, nhận, retry, theo dõi riêng.

## 3. Schema, subject, version và schema ID là bốn khái niệm khác nhau

Với Confluent Schema Registry, hãy phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Schema | Định nghĩa cấu trúc/kiểu trên đường truyền | Avro record `OrderPlaced` |
| Subject | Không gian tên/nhóm version nơi kiểm tra compatibility | `order.placed-value` |
| Subject version | Thứ tự phiên bản đăng ký trong **một subject** | v1, v2 |
| Schema ID | Định danh do registry cấp cho schema để client tra cứu | Một số nguyên do server trả về |
| Event type | Tên sự thật nghiệp vụ | `order.placed` |
| Payload/event version | Phiên bản hợp đồng nghiệp vụ nếu tổ chức còn dùng metadata riêng | `schemaVersion=2` |
| Aggregate version | Thứ tự thay đổi trạng thái của một aggregate | `aggregateVersion=17` |
| Application release | Version build/deploy service | `orders-service 4.2.0` |

**Schema ID không phải subject version.** Một schema có thể được đăng ký dưới nhiều subject; ID có thể được dùng lại trong phạm vi registry còn version của mỗi subject phát triển riêng. Không viết code giả định `schema ID=2` luôn là `version 2`.

### Subject naming trong Kafka

Với cách đặt tên subject theo topic phổ biến (`TopicNameStrategy`):

- Topic `order.placed` có subject cho value là `order.placed-value`.
- Nếu key cũng có schema riêng, subject key có thể là `order.placed-key`.
- Thường một chuỗi version value schema trong subject được quản lý tương thích theo cấu hình.

Ngoài ra có các chiến lược như `RecordNameStrategy` và `TopicRecordNameStrategy`. Chúng cho phép nhóm schema theo tên record hoặc kết hợp topic/record, phù hợp khi nhiều loại record chia sẻ topic. Chọn chiến lược trước khi producer chạy rộng rãi; **đổi subject naming không tự di chuyển lịch sử schemas** và có thể khiến consumer tìm sai schema.

### Vì sao cần version ngay cả khi class không đổi tên?

Hai service có thể cùng tên class `OrderPlaced` nhưng classpath của phiên bản mới thêm field. Mặt khác, class nội bộ có thể refactor mà hợp đồng Avro không đổi. **Schema version thuộc hợp đồng dữ liệu**, không nên tăng theo mọi lần release, cũng không phụ thuộc tên package của entity nội bộ.

## 4. Cách Avro encode và schema được tra cứu

Avro là một định dạng schema-based. Dữ liệu nhị phân chỉ giải mã đúng khi deserializer biết **writer schema**; khi cần ánh xạ thành hợp đồng mới, nó có thể sử dụng thêm **reader schema** và thực hiện schema resolution.

Trong **Confluent Avro wire format mặc định/legacy**, phần message value thường có:

```text
+-----------+--------------------+-----------------------+
| magic byte| schema ID (4 bytes)| Avro binary payload   |
+-----------+--------------------+-----------------------+
|     0     |       ID           | giá trị đã serialize |
+-----------+--------------------+-----------------------+
```

Wire format cụ thể phụ thuộc serializer và cấu hình; đây là mô hình thường dùng của Confluent serializers chứ **không phải Avro specification bắt buộc mọi ứng dụng tuân theo**.

Luồng decode điển hình:

1. Consumer nhận bytes từ broker.
2. Deserializer đọc schema ID trong framing.
3. Client tra cứu schema tương ứng qua registry; client có thể cache kết quả.
4. Dùng writer schema để hiểu dữ liệu nhị phân.
5. Nếu ứng dụng sử dụng một reader schema mới, áp dụng quy tắc resolution/default thích hợp.
6. Chuyển dữ liệu sang model xử lý nghiệp vụ.

Registry có thể giúp giải mã dữ liệu cũ, nhưng **không tự biến event v1 thành domain object v2 đúng về nghiệp vụ**. Phần mapping, default hoặc upcasting cần có hợp đồng rõ.

## 5. Compatibility modes: đọc đúng chiều

Khi đăng ký schema mới, registry có thể đánh giá nó so với schema cũ. Các thuật ngữ phổ biến:

| Chế độ | Điều cần bảo đảm |
| --- | --- |
| `BACKWARD` | Reader theo schema **mới** đọc được dữ liệu viết bằng schema **liền trước** |
| `BACKWARD_TRANSITIVE` | Reader mới đọc được dữ liệu viết bằng **mọi schema trước đó** |
| `FORWARD` | Reader schema cũ đọc được dữ liệu do schema mới viết, so với phiên bản liền trước |
| `FORWARD_TRANSITIVE` | Reader của mọi phiên bản cũ đọc được dữ liệu viết bởi schema mới |
| `FULL` | Cả backward và forward với phiên bản liền trước |
| `FULL_TRANSITIVE` | Cả hai chiều với toàn bộ các phiên bản trước |
| `NONE` | Tắt compatibility checks của registry |

**Mặc định Confluent Schema Registry là `BACKWARD`, không phải `BACKWARD_TRANSITIVE`.** Điều này quan trọng khi hệ thống cần đọc/replay dữ liệu rất cũ. Với `BACKWARD` không transitive, một chuỗi thay đổi v1→v2 và v2→v3 có thể được chấp nhận nhưng v3 chưa chắc đọc được mọi dữ liệu từ v1.

### Hướng nâng cấp producer/consumer

- Với **backward compatibility**, thường nâng consumer để đọc được dữ liệu cũ/mới **trước** khi producer bắt đầu ghi schema mới. Như vậy consumer triển khai sau cùng không bị bất ngờ với dữ liệu mới.
- Với **forward compatibility**, cần đánh giá khả năng consumer cũ hiểu dữ liệu mới và thứ tự triển khai theo hợp đồng cụ thể; không suy diễn quy tắc duy nhất cho mọi schema format.
- Với **full compatibility**, có linh hoạt hơn về thứ tự nâng cấp nhưng vẫn cần contract test cho logic nghiệp vụ, kiểu enum, null và version cũ.
- Với **NONE**, mọi thay đổi đều có thể được đăng ký nếu schema hợp lệ; tổ chức phải tự kiểm soát rủi ro breaking changes.

Chọn policy **theo từng subject** nếu nhu cầu khác nhau. Đừng đặt `NONE` toàn registry để “đẩy nhanh deploy” mà không có phương án chuyển đổi hoặc tạo subject/topic mới.

## 6. Ví dụ schema evolution: v1, v2 và bản breaking

Giả định nghiệp vụ được ghi rõ: **mọi đơn trong thời kỳ v1 sử dụng USD**. Do đó, khi nâng sang v2, `currency="USD"` là default đúng cho dữ liệu lịch sử.

### v1 — hai field ban đầu

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.contract",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinorUnits", "type": "long"}
  ]
}
```

### v2 — thêm currency có default

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.contract",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinorUnits", "type": "long"},
    {"name": "currency", "type": "string", "default": "USD"}
  ]
}
```

Với Avro, schema v2 có thể đọc dữ liệu do v1 ghi: khi không thấy field `currency` trong writer schema v1, Avro reader v2 có thể dùng `default` của **reader schema** là USD.

**Điểm dễ nhầm:** Default của Avro phục vụ **schema resolution khi đọc dữ liệu thiếu field**, không phải lời hứa rằng serializer sẽ tự điền default vào mọi record producer v2. Nếu writer theo schema v2, ứng dụng thường vẫn cần cung cấp field hợp lệ cho record đó.

Trong ví dụ này, schema v1 đọc dữ liệu do v2 ghi cũng có thể bỏ qua field mới `currency`. Với sự thay đổi cụ thể này, hai chiều có thể tương thích về cấu trúc, nhưng logic v1 có thể **không hỗ trợ giao dịch không phải USD**. Đây chính là ví dụ cho việc *schema compatibility không đảm bảo semantic compatibility*.

### v3-bad — thêm field bắt buộc không có default

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.contract",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinorUnits", "type": "long"},
    {"name": "currency", "type": "string", "default": "USD"},
    {"name": "salesChannel", "type": "string"}
  ]
}
```

Nếu đọc event v2 bằng reader schema v3-bad, Avro không biết giá trị của `salesChannel` vì writer cũ không chứa field này, còn reader mới không định nghĩa default. Do đó v3-bad **không backward compatible** với v2.

Một v3 hợp lý có thể khai báo `salesChannel` nullable có default `null` nếu nghiệp vụ cho phép “không xác định”:

```json
{"name": "salesChannel", "type": ["null", "string"], "default": null}
```

Trong Avro, thứ tự các nhánh union và kiểu của default phải hợp lệ; mô hình `["null","string"]` kèm `default:null` là cách thường dùng.

**Không dùng default tùy tiện.** Nếu v1 thực tế đã chứa đơn nhiều đồng tiền nhưng không ghi `currency`, mặc định USD sẽ là dữ liệu sai. Khi thiếu dữ kiện, cần chiến lược migration/upcaster có audit, trường unknown hợp lệ hoặc giữ dữ liệu cũ không được diễn giải thành giá trị đã biết.

## 7. Những thay đổi cần thận trọng ngoài việc thêm field

| Thay đổi | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Thêm field có default hợp lệ | Thường backward compatible trong Avro | Viết reader/writer tests |
| Thêm field bắt buộc không có default | New reader không đọc dữ liệu cũ | Default, union nullable hoặc version riêng |
| Bỏ field bắt buộc | Old reader có thể không đọc new writer | Đánh giá compatibility hai chiều |
| Đổi `long` sang `string` | Thường phá contract | Tạo field/schema/topic mới hoặc adapter |
| Đổi tên field `orderId` thành `id` | Cần Avro aliases/migration phù hợp | Đánh giá schema resolution, contract test |
| Đổi nghĩa `amountMinorUnits` | Nguy cơ sai âm thầm | Event type/version mới, kiểm tra nghiệp vụ |
| Thêm enum symbol | Reader cũ có thể không xử lý symbol lạ | Fallback/unknown, kiểm tra theo format |
| Chuyển nullability | Tác động writer/reader khác nhau | Kiểm tra union/default và mọi consumer |
| Thay nested record/union | Có thể ảnh hưởng nhiều type | Thử fixture lịch sử và policy phù hợp |
| Xóa schema quá sớm | Dữ liệu cũ có thể không giải mã được | Retention/migration/replay có kiểm soát |

Với **Protobuf**, field numbers là một phần hợp đồng trên wire; tránh tái sử dụng field number đã xóa, dùng `reserved` theo quy tắc. Với **JSON Schema**, hành vi tương thích còn phụ thuộc việc mô hình cho phép field ngoài schema (open/closed content model), quy tắc required và policy của registry. Không copy nguyên quy tắc Avro sang hai định dạng này.

## 8. Ví dụ Java 17+ chạy được: Spring event + Avro evolution

Bài thực hành dưới đây **không cần Kafka, Schema Registry server hay database**. Nó chứng minh hai phần cơ sở:

1. Java/Avro xác định schema mới có đọc được dữ liệu viết theo schema cũ hay không.
2. Một Spring `@EventListener` có thể chuyển event Java nội bộ sang record theo **integration schema**.

Sau đó, ở mục 9, ta dùng REST với **Schema Registry thật** để lưu subject/version và kiểm tra compatibility phía server. Hai bài thực hành có mục đích riêng: kiểm tra Avro tại JVM không thay cho việc đăng ký schema hay gửi message ra broker.

### 8.1. Cấu trúc thư mục

```text
spring-avro-schema-demo/
├── pom.xml
├── compose.yaml
└── src/
    ├── main/java/example/events/SchemaEvolutionDemo.java
    └── test/java/example/events/SchemaEvolutionDemoTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-avro-schema-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>
        <dependency>
            <groupId>org.apache.avro</groupId>
            <artifactId>avro</artifactId>
            <version>1.12.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

### 8.3. SchemaEvolutionDemo.java

```java
package example.events;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

import org.apache.avro.Schema;
import org.apache.avro.SchemaCompatibility;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericDatumReader;
import org.apache.avro.generic.GenericDatumWriter;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.io.BinaryDecoder;
import org.apache.avro.io.BinaryEncoder;
import org.apache.avro.io.DecoderFactory;
import org.apache.avro.io.EncoderFactory;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SchemaEvolutionDemo {

    private static final String V1_JSON = """
            {
              "type": "record",
              "name": "OrderPlaced",
              "namespace": "example.contract",
              "fields": [
                {"name":"orderId","type":"string"},
                {"name":"amountMinorUnits","type":"long"}
              ]
            }
            """;

    private static final String V2_JSON = """
            {
              "type": "record",
              "name": "OrderPlaced",
              "namespace": "example.contract",
              "fields": [
                {"name":"orderId","type":"string"},
                {"name":"amountMinorUnits","type":"long"},
                {"name":"currency","type":"string","default":"USD"}
              ]
            }
            """;

    private static final String V3_BAD_JSON = """
            {
              "type": "record",
              "name": "OrderPlaced",
              "namespace": "example.contract",
              "fields": [
                {"name":"orderId","type":"string"},
                {"name":"amountMinorUnits","type":"long"},
                {"name":"currency","type":"string","default":"USD"},
                {"name":"salesChannel","type":"string"}
              ]
            }
            """;

    private static final Schema V1 =
            new Schema.Parser().parse(V1_JSON);
    private static final Schema V2 =
            new Schema.Parser().parse(V2_JSON);
    private static final Schema V3_BAD =
            new Schema.Parser().parse(V3_BAD_JSON);

    // Event nội bộ: chưa phải Avro/Kafka message.
    public record OrderPlaced(
            String eventId,
            String orderId,
            long amountMinorUnits,
            String currency) {
    }

    public static Schema schemaV1() {
        return V1;
    }

    public static Schema schemaV2() {
        return V2;
    }

    public static Schema schemaV3Bad() {
        return V3_BAD;
    }

    // Chiều tương thích: newReader đọc oldWriter.
    public static boolean canRead(Schema reader, Schema writer) {
        return SchemaCompatibility.checkReaderWriterCompatibility(
                reader, writer).getType()
                == SchemaCompatibility.SchemaCompatibilityType.COMPATIBLE;
    }

    // Demo: tự tạo record theo schema V1 hoặc V2.
    public static byte[] write(
            Schema writerSchema,
            String orderId,
            long amountMinorUnits,
            String currency) throws IOException {

        GenericRecord record = new GenericData.Record(writerSchema);
        record.put("orderId", orderId);
        record.put("amountMinorUnits", amountMinorUnits);

        if (writerSchema.getField("currency") != null) {
            record.put("currency", currency);
        }

        try (ByteArrayOutputStream output =
                     new ByteArrayOutputStream()) {
            GenericDatumWriter<GenericRecord> writer =
                    new GenericDatumWriter<>(writerSchema);

            BinaryEncoder encoder =
                    EncoderFactory.get().binaryEncoder(output, null);

            writer.write(record, encoder);
            encoder.flush();
            return output.toByteArray();
        }
    }

    // Avro schema resolution với writer và reader schema rõ ràng.
    public static GenericRecord read(
            byte[] bytes,
            Schema writerSchema,
            Schema readerSchema) throws IOException {

        GenericDatumReader<GenericRecord> reader =
                new GenericDatumReader<>(writerSchema, readerSchema);

        BinaryDecoder decoder =
                DecoderFactory.get().binaryDecoder(bytes, null);

        return reader.read(null, decoder);
    }

    public static class Bridge {
        private GenericRecord lastRead;

        @EventListener
        public void on(OrderPlaced domainEvent) {
            try {
                byte[] payload = write(
                        V2,
                        domainEvent.orderId(),
                        domainEvent.amountMinorUnits(),
                        domainEvent.currency());

                // Đây là round-trip mô phỏng đường wire;
                // chưa gửi đến message broker.
                lastRead = read(payload, V2, V2);

                System.out.printf(
                        "BRIDGE id=%s order=%s currency=%s%n",
                        domainEvent.eventId(),
                        lastRead.get("orderId"),
                        lastRead.get("currency"));
            } catch (IOException ex) {
                throw new IllegalStateException(
                        "Cannot encode integration event", ex);
            }
        }

        public GenericRecord lastRead() {
            return lastRead;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        Bridge bridge() {
            return new Bridge();
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("BACKWARD v2<-v1="
                + canRead(V2, V1));
        System.out.println("BACKWARD v3<-v2="
                + canRead(V3_BAD, V2));

        byte[] oldBytes =
                write(V1, "ORD-101", 12500L, null);
        GenericRecord upgraded = read(oldBytes, V1, V2);

        System.out.printf(
                "REPLAY order=%s currency=%s%n",
                upgraded.get("orderId"),
                upgraded.get("currency"));

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             DemoConfig.class)) {

            context.publishEvent(
                    new OrderPlaced(
                            "evt-102", "ORD-102", 2500L, "VND"));
        }
    }
}
```

### 8.4. Lệnh chạy và output dự kiến

Yêu cầu JDK 17+ và Maven, tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.events.SchemaEvolutionDemo
```

Các dòng do **mã demo** in ra (không tính log thư viện):

```text
BACKWARD v2<-v1=true
BACKWARD v3<-v2=false
REPLAY order=ORD-101 currency=USD
BRIDGE id=evt-102 order=ORD-102 currency=VND
```

Giải thích:

1. `canRead(V2,V1)` trả `true` vì reader schema v2 có default cho field `currency` mới.
2. `canRead(V3_BAD,V2)` trả `false` vì v3 thêm `salesChannel` không có default.
3. Bytes Avro được viết bằng **v1**, sau đó được đọc bằng **v2**. Avro reader dùng default USD, nên `REPLAY` in `currency=USD`.
4. Spring dispatch record Java `OrderPlaced` tới method `@EventListener`. Bridge mapping sang record **v2**, encode/decode rồi in VND.
5. Ví dụ không cần network, database, registry hay Kafka. Nó minh họa **khả năng đọc schema cũ và ranh giới internal → integration event**, không chứng minh broker đã nhận message.

Đừng sửa `canRead` để đảo vị trí hai đối số: API `checkReaderWriterCompatibility(reader, writer)` định nghĩa **reader trước, writer sau**. Đảo chiều khiến kiểm tra `BACKWARD` thành kiểm tra khác.

### 8.5. Unit/integration test JUnit 5

File `src/test/java/example/events/SchemaEvolutionDemoTest.java`:

```java
package example.events;

import org.apache.avro.generic.GenericRecord;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchemaEvolutionDemoTest {

    @Test
    void newReaderCanReadOldAvroData() throws Exception {
        byte[] writtenByV1 =
                SchemaEvolutionDemo.write(
                        SchemaEvolutionDemo.schemaV1(),
                        "ORD-1", 100L, null);

        GenericRecord readByV2 =
                SchemaEvolutionDemo.read(
                        writtenByV1,
                        SchemaEvolutionDemo.schemaV1(),
                        SchemaEvolutionDemo.schemaV2());

        assertEquals("ORD-1",
                readByV2.get("orderId").toString());
        assertEquals(100L,
                readByV2.get("amountMinorUnits"));
        assertEquals("USD",
                readByV2.get("currency").toString());
    }

    @Test
    void requiredNewFieldBreaksBackwardCompatibility() {
        assertTrue(SchemaEvolutionDemo.canRead(
                SchemaEvolutionDemo.schemaV2(),
                SchemaEvolutionDemo.schemaV1()));

        assertFalse(SchemaEvolutionDemo.canRead(
                SchemaEvolutionDemo.schemaV3Bad(),
                SchemaEvolutionDemo.schemaV2()));
    }

    @Test
    void springDispatchesInternalEventToSchemaBridge() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SchemaEvolutionDemo.DemoConfig.class)) {

            context.publishEvent(
                    new SchemaEvolutionDemo.OrderPlaced(
                            "evt-1", "ORD-2", 200L, "EUR"));

            var bridge = context.getBean(
                    SchemaEvolutionDemo.Bridge.class);

            assertNotNull(bridge.lastRead());
            assertEquals("ORD-2",
                    bridge.lastRead().get("orderId").toString());
            assertEquals("EUR",
                    bridge.lastRead().get("currency").toString());
        }
    }
}
```

Chạy:

```bash
mvn test
```

Dự án định nghĩa **3 test methods**. Khi tất cả assertion đúng, Surefire báo thành công; thời lượng và log phụ thuộc máy. Các test này không kết nối registry/broker — điều đó là **phạm vi cố ý** của bài kiểm thử unit và Spring context.

## 9. Thực hành Schema Registry thật qua REST API

Schema Registry là một dịch vụ riêng, thường dùng Kafka làm nơi lưu metadata nội bộ. Để chạy local, có thể sử dụng Docker Compose với Kafka và Schema Registry. Phần này minh họa API thực sự dùng để tạo **subject, version, compatibility**.

### 9.1. compose.yaml (local lab)

```yaml
services:
  kafka:
    image: confluentinc/cp-kafka:7.8.2
    hostname: kafka
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: "broker,controller"
      KAFKA_CONTROLLER_QUORUM_VOTERS: "1@kafka:29093"
      KAFKA_LISTENERS: "PLAINTEXT://kafka:29092,CONTROLLER://kafka:29093,PLAINTEXT_HOST://0.0.0.0:9092"
      KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092"
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT,CONTROLLER:PLAINTEXT"
      KAFKA_INTER_BROKER_LISTENER_NAME: "PLAINTEXT"
      KAFKA_CONTROLLER_LISTENER_NAMES: "CONTROLLER"
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      CLUSTER_ID: "MkU3OEVBNTcwNTJENDM2Qk"

  registry:
    image: confluentinc/cp-schema-registry:7.8.2
    hostname: registry
    depends_on:
      - kafka
    ports:
      - "8081:8081"
    environment:
      SCHEMA_REGISTRY_HOST_NAME: "registry"
      SCHEMA_REGISTRY_LISTENERS: "http://0.0.0.0:8081"
      SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: "PLAINTEXT://kafka:29092"
```

Đây là **local lab**, không phải cấu hình production: một broker, không TLS/auth, không persistent volume, không replication/HA. Một số phiên bản image có thể thay đổi yêu cầu cấu hình; giữ cùng nhóm phiên bản và kiểm tra log nếu container lỗi khởi động. `depends_on` chỉ sắp thứ tự start container, **không đảm bảo Kafka đã sẵn sàng** trước khi registry thử kết nối.

Khởi động:

```bash
docker compose up -d
docker compose ps
```

Đợi REST API sẵn sàng bằng cách thử:

```bash
curl -fsS http://localhost:8081/subjects
```

Khi registry mới chưa có subject, thường trả `[]`. Nếu lỗi kết nối, xem `docker compose logs registry kafka` và thử lại **sau khi service đã khởi động**, không bỏ qua lỗi. Các lệnh `curl` dưới đây dùng quoting kiểu shell POSIX; PowerShell có quy tắc quote riêng.

### 9.2. Đặt compatibility cho một subject

Dùng subject gắn với topic `order.placed` theo `TopicNameStrategy`:

```bash
curl -fsS -X PUT \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"compatibility":"BACKWARD_TRANSITIVE"}' \
  http://localhost:8081/config/order.placed-value
```

Một phản hồi thành công có trường `compatibility` nhận giá trị `BACKWARD_TRANSITIVE`. Việc đặt policy tại **subject** giúp tránh ảnh hưởng ngoài ý muốn đến các subject khác.

Kiểm tra:

```bash
curl -fsS http://localhost:8081/config/order.placed-value
```

### 9.3. Đăng ký schema v1

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"schemaType":"AVRO","schema":"{\"type\":\"record\",\"name\":\"OrderPlaced\",\"namespace\":\"example.contract\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amountMinorUnits\",\"type\":\"long\"}]}"}' \
  http://localhost:8081/subjects/order.placed-value/versions
```

Phản hồi có schema ID do server cấp, chẳng hạn theo dạng:

```json
{"id": 123}
```

Số `123` chỉ là **ví dụ minh họa**, không dự đoán ID thực tế. Kiểm tra version sau đăng ký:

```bash
curl -fsS http://localhost:8081/subjects/order.placed-value/versions
```

Nếu subject mới, kết quả có thể là `[1]`.

### 9.4. Kiểm tra v2 trước khi đăng ký

Dùng endpoint `/compatibility/subjects/{subject}/versions` để kiểm tra theo policy của subject, kể cả chế độ transitive. Đây là bước phù hợp cho CI kiểm tra thay đổi schema:

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"schemaType":"AVRO","schema":"{\"type\":\"record\",\"name\":\"OrderPlaced\",\"namespace\":\"example.contract\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amountMinorUnits\",\"type\":\"long\"},{\"name\":\"currency\",\"type\":\"string\",\"default\":\"USD\"}]}"}' \
  http://localhost:8081/compatibility/subjects/order.placed-value/versions
```

Với policy `BACKWARD_TRANSITIVE` và v1 ở trên, kết quả dự kiến:

```json
{"is_compatible": true}
```

Đây mới là **kiểm tra**, chưa tạo version mới. Registry kiểm tra cấu trúc Avro và policy, không xác nhận default USD đúng về nghiệp vụ.

### 9.5. Đăng ký v2 và đọc metadata

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"schemaType":"AVRO","schema":"{\"type\":\"record\",\"name\":\"OrderPlaced\",\"namespace\":\"example.contract\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amountMinorUnits\",\"type\":\"long\"},{\"name\":\"currency\",\"type\":\"string\",\"default\":\"USD\"}]}"}' \
  http://localhost:8081/subjects/order.placed-value/versions

curl -fsS \
  http://localhost:8081/subjects/order.placed-value/versions/latest
```

Phản hồi `latest` cung cấp subject/version/schema ID/schema string và có thể thêm metadata tùy server/client. Với subject mới và hai schema khác nhau được đăng ký tuần tự, latest thường là **version 2**. Schema ID là giá trị riêng do server cấp, **không bắt buộc bằng 2**.

### 9.6. Thử bản breaking nhưng không đăng ký

Đề nghị thêm `salesChannel` bắt buộc không có default:

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"schemaType":"AVRO","schema":"{\"type\":\"record\",\"name\":\"OrderPlaced\",\"namespace\":\"example.contract\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amountMinorUnits\",\"type\":\"long\"},{\"name\":\"currency\",\"type\":\"string\",\"default\":\"USD\"},{\"name\":\"salesChannel\",\"type\":\"string\"}]}"}' \
  'http://localhost:8081/compatibility/subjects/order.placed-value/versions?verbose=true'
```

Với v1/v2 và policy `BACKWARD_TRANSITIVE` ở trên, `is_compatible` phải là `false`. Khi bật `verbose=true`, response có thể kèm thông điệp giải thích. Đừng hardcode nguyên văn các message lỗi của registry vào test vì phiên bản server có thể thay đổi.

Nếu thử **đăng ký** bản breaking qua `POST /subjects/.../versions`, registry sẽ từ chối theo compatibility policy (thường HTTP 409). Không nên đưa thao tác đăng ký phá hợp đồng vào pipeline deploy thật chỉ để “xem có lỗi không”; dùng endpoint kiểm tra trước.

### 9.7. Kết thúc lab

```bash
docker compose down
```

Nếu muốn xóa toàn bộ dữ liệu trong các volumes có quản lý, phải làm việc đó có chủ đích trên lab; không chạy lệnh xóa volume trong môi trường chứa Kafka/SR dữ liệu thật.

## 10. Tích hợp Schema Registry vào Spring Kafka

Bài tập ở mục 8 kiểm tra Avro trong JVM; mục 9 đăng ký schema qua REST. Để **message Kafka thực sự sử dụng Schema Registry**, producer/consumer cần serializer/deserializer phù hợp.

Mẫu cấu hình trong một **ứng dụng Spring Boot có Spring Kafka và Confluent Avro SerDes** (không nằm trong project demo chỉ dùng `spring-context`):

```properties
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=io.confluent.kafka.serializers.KafkaAvroSerializer

spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=io.confluent.kafka.serializers.KafkaAvroDeserializer

spring.kafka.properties.schema.registry.url=http://localhost:8081
spring.kafka.consumer.properties.specific.avro.reader=false
```

Các class `KafkaAvroSerializer` / `KafkaAvroDeserializer` đến từ dependency **`io.confluent:kafka-avro-serializer`** có phiên bản tương thích với stack Kafka/Confluent đang dùng; Maven có thể cần repository Confluent. `spring-kafka` là dependency framework Kafka của Spring, còn `spring-context` **không** tự mang các serializer này vào classpath.

Với `specific.avro.reader=false`, consumer thường nhận `GenericRecord`. Nếu muốn class `SpecificRecord` sinh từ schema Avro, phải thiết lập generation/reader phù hợp và quản lý version của những class đó.

Ví dụ send với Spring Kafka, **chỉ là mảnh code minh họa**:

```java
GenericRecord record = new GenericData.Record(orderPlacedSchemaV2);
record.put("orderId", "ORD-101");
record.put("amountMinorUnits", 12500L);
record.put("currency", "USD");

kafkaTemplate.send("order.placed", "ORD-101", record)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Ghi nhận lỗi và chuyển sang retry/outbox theo hợp đồng.
            } else {
                // Kafka producer send đã thành công theo ACK config.
                // Chưa có nghĩa consumer hoàn tất nghiệp vụ.
            }
        });
```

Đoạn này giả định có `KafkaTemplate<String, GenericRecord> kafkaTemplate`, schema V2, imports và một bean producer/serializer được cấu hình. Nó **không phải chương trình biên dịch độc lập**. Spring Kafka dùng kiểu `CompletableFuture` cho `KafkaTemplate.send(...)` trong dòng framework hiện đại; xử lý completion/error chứ không bỏ mặc kết quả.

**Không đăng ký schema mới từ mọi event theo ý muốn.** Có serializer cho phép `auto.register.schemas=true`, nhưng production thường cần kiểm soát đăng ký trong CI/CD hoặc governance pipeline, dùng schema đã được duyệt. Nếu tắt auto-registration, phải bảo đảm schema/subject đã tồn tại, và cấu hình lookup/schema ID phù hợp với serializer đang dùng.

### Schema Registry với RabbitMQ có được không?

Có thể dùng registry như **dịch vụ hợp đồng độc lập** và serialize Avro/Protobuf trước khi gửi RabbitMQ, nhưng RabbitMQ không mặc định hiểu Confluent Schema Registry framing/subject. Ứng dụng phải tự thống nhất cách gửi schema ID/headers, serializer/deserializer, lookup, compatibility và cache. Không copy cấu hình `spring.kafka.*` sang `RabbitTemplate` rồi kỳ vọng hoạt động.

## 11. Versioning không chỉ nằm ở schema registry

Một integration event ngoài schema còn cần các thông tin:

```json
{
  "eventId": "d1e173a5-486a-4c78-b90e-abc25004f604",
  "eventType": "order.placed",
  "occurredAt": "2026-11-11T06:15:00Z",
  "aggregateId": "ORD-101",
  "aggregateVersion": 7,
  "payload": {
    "orderId": "ORD-101",
    "amountMinorUnits": 12500,
    "currency": "USD"
  }
}
```

Đây là **một envelope minh họa**; Confluent Avro message không bắt buộc dùng đúng JSON envelope này. Một số metadata có thể đặt trong Kafka headers hoặc được định nghĩa trong Avro record.

Phân biệt:

- `eventId` giúp nhận diện một lần xảy ra, thường là khóa chống trùng.
- `aggregateVersion` phục vụ thứ tự biến đổi của một aggregate, nếu ứng dụng có sequence.
- `occurredAt` giúp tra cứu/audit thời điểm sự kiện xảy ra.
- `schemaVersion` là version hợp đồng nếu hệ thống còn công bố trường này; nó **không thay thế** schema ID do registry cấp.
- `eventType` là sự thật nghiệp vụ, không nhất thiết giống tên subject hay tên class Java.

Schema registry thường **không kiểm tra ý nghĩa** của event type, aggregate sequence hay idempotency. Hệ thống vẫn cần hợp đồng nghiệp vụ, unique constraints, versioning policy và test.

## 12. Rolling deployment và xử lý dữ liệu cũ

Trong một hệ thống có nhiều producer/consumer, thay schema cần có kế hoạch triển khai:

1. **Xác nhận contract v1:** ghi lại tất cả field, đơn vị, nullability, default, enum và data examples thật.
2. **Đề xuất v2:** thêm field hoặc thay đổi type có giải thích rõ tác động.
3. **Chạy compatibility check:** tại CI với subject/schema policy đang áp dụng.
4. **Chạy consumer contract tests:** đọc fixture v1 và v2 bằng implementation dự kiến deploy.
5. **Nâng các consumer cần đọc version mới trước khi producer ghi version mới** theo backward compatibility plan.
6. **Đăng ký v2 có kiểm soát:** pipeline ghi nhận subject/version/ID.
7. **Triển khai producer:** giám sát lỗi serializer/registry lookup và consumer decode.
8. **Quan sát cả hai phiên bản:** ghi metric theo event type/schema family, không xóa support v1 khi còn retention, DLQ hoặc replay.
9. **Kết thúc migration có điều kiện:** chỉ loại bỏ reader/upcaster v1 khi retention và consumer contract cho phép.

Nếu producer mới tạo payload v2 hợp lệ về schema nhưng currency mang giá trị chưa được consumer cũ hỗ trợ, cần **business-level compatibility plan**. Registry không thể biết `"JPY"` có làm hỏng báo cáo tài chính của consumer hay không.

### Upcasting khi đọc lịch sử

Có hai cách khác nhau:

- **Schema resolution:** Avro dùng reader/writer schema để giải mã, bổ sung default, bỏ field không cần theo quy tắc.
- **Upcasting/domain migration:** application chuyển event cũ sang mô hình hiện tại và xử lý thay đổi ngữ nghĩa một cách có chủ đích.

Không giả định schema resolution tự thực hiện nghiệp vụ upcasting. Ví dụ v1 chưa ghi thuế, chuyển sang v2 đòi tính thuế thì cần quy tắc hoặc dữ liệu lịch sử, không thể đặt một default tùy ý.

Khi replay, consumer có thể đọc nhiều schema ID trong cùng topic. Vì thế cần giữ schema lịch sử khả dụng hoặc có chiến lược migration/archival đã được kiểm chứng; xóa subject/schema chỉ để “dọn registry” có thể phá dữ liệu còn nằm ở broker/outbox.

## 13. Kiểm thử hợp đồng trong CI/CD

Một pipeline tốt không chỉ compile producer mới. Nó kiểm tra producer, schema registry và consumer.

### 13.1. Những test nên có

| Test | Xác minh |
| --- | --- |
| Parse schema | Avro/Protobuf/JSON Schema hợp lệ về cú pháp |
| Reader/writer compatibility | New reader đọc được data cũ theo policy |
| Registry compatibility endpoint | Schema được subject policy chấp nhận |
| Historical fixture decode | Consumer đọc được binary/JSON thực từ v1/v2 |
| Serialization round-trip | Dữ liệu encode/decode giữ giá trị/ngữ nghĩa |
| Semantic contract test | Đơn vị tiền, enum, default, timestamp, null đúng nghiệp vụ |
| Producer integration | Serializer tìm/đăng ký schema đúng subject |
| Consumer integration | Deserializer lookup schema ID và xử lý đúng |
| Negative compatibility test | Breaking change bị chặn trước deploy |
| Replay test | Consumer mới xử lý được dữ liệu cũ còn trong retention |
| Cross-service contract | Consumer khác ngôn ngữ/codebase hiểu cùng hợp đồng |
| Security test | Registry ACL/auth không cho producer sửa schema trái quyền |

Unit test mục 8 chứng minh một phần parse/compatibility/reader-writer; phần **REST integration** mục 9 mới chứng minh server policy. Khi chạy CI, không sử dụng một shared production registry làm nơi thử schema hỏng; nên dùng registry kiểm thử hoặc endpoint compatibility read-only với quyền phù hợp.

### 13.2. Golden fixtures

Lưu những message từ phiên bản đã phát hành, đã loại bỏ dữ liệu nhạy cảm, trong test resources:

```text
src/test/resources/contracts/order-placed-v1.avsc
src/test/resources/contracts/order-placed-v2.avsc
src/test/resources/events/order-placed-v1.bin
src/test/resources/events/order-placed-v2.bin
```

Đây là **cấu trúc test gợi ý**, không phải file bắt buộc của demo mục 8. Nếu tạo fixture bằng serializer mới nhất cho mọi phiên bản, test có thể bỏ sót khác biệt thực tế từ producer cũ. Đưa payload cũ đã kiểm chứng vào test để phát hiện thay đổi mapping.

### 13.3. Khi schema evolution đòi breaking change

Nếu thay đổi field/type/ý nghĩa không thể tiến hóa tương thích, lựa chọn:

- Công bố **event type mới** nếu sự thật nghiệp vụ thực sự khác.
- Tạo **topic/subject mới** và migration plan rõ, không ghi payload phá hợp đồng vào cùng nơi mà consumer cũ chưa xử lý được.
- Duy trì hai biểu diễn trong giai đoạn chuyển tiếp, nhưng tránh xử lý cùng business event hai lần; có correlation ID/dedup.
- Dùng adapter/upcaster ở ranh giới cho consumer chưa nâng cấp.
- Có thời điểm deprecate và thời điểm ngừng đọc version cũ dựa trên retention/replay.

**Không tắt `compatibility=NONE` rồi coi việc registry chấp nhận schema là dấu hiệu migration thành công.**

## 14. Failure modes: khi nào registry không giải quyết được sự cố?

### 14.1. Registry tạm thời mất kết nối

Khi producer serializer cần tra cứu/đăng ký schema ID chưa cache, việc publish có thể thất bại nếu registry không truy cập được. Consumer đọc schema ID chưa cache cũng có thể lỗi decode nếu không tra cứu được schema. Khả năng tiếp tục hoạt động phụ thuộc cache, serializer, client retry và cấu hình.

Cách xử lý: metrics registry latency/error, retry/backoff theo giới hạn, cache và schema pre-registration. Nếu event quan trọng, producer dùng outbox để giữ ý định gửi khi registry/broker tạm lỗi.

### 14.2. Producer gửi schema chưa đăng ký

Nếu tắt auto-registration mà schema chưa được đăng ký đúng subject, serializer có thể báo lỗi lookup. Hãy kiểm tra subject naming strategy, URL, auth, schema canonical form, compatibility policy và version. Đừng chỉ đổi serializer thành `StringSerializer` để bỏ qua hợp đồng.

### 14.3. Consumer không hiểu schema mới

Các nguyên nhân có thể là schema incompatibility, reader class cũ, enum symbol lạ, field semantic mới hoặc một service chưa deploy. Registry chấp nhận schema theo một policy không đồng nghĩa **mọi consumer** đều có bản build xử lý được v2. Phân biệt lỗi deserialize với lỗi business mapping.

### 14.4. Schema ID không tồn tại hoặc bị xóa

Một message còn trong topic có thể tham chiếu schema ID không còn tra cứu được. Không xóa schema lịch sử tùy tiện khi còn dữ liệu phải replay hoặc khi consumer có thể nhận message chậm từ DLQ.

### 14.5. Schema compatible nhưng event nghĩa khác

Thay `amountMinorUnits` từ cent sang đơn vị chính mà vẫn giữ `long` có thể qua schema check nhưng sai kết quả x100. Đây là **breaking semantic contract** cần event type hoặc version riêng và review nghiệp vụ.

### 14.6. Dùng schema registry để kỳ vọng exactly-once

Registry chỉ cung cấp metadata/schema validation. Nó không tạo transaction nguyên tử giữa DB và Kafka, không xác nhận consumer side effect, và không tự chống duplicate. Với event quan trọng cần cân nhắc **transactional outbox + at-least-once publication + idempotent consumer**, kèm broker ACK/offset management.

## 15. Bảo mật và quản trị schema

Một registry phục vụ nhiều team cần governance:

- **Quyền đăng ký schema:** giới hạn writer theo subject và môi trường, không cho mọi app tự thay contract.
- **Auth/TLS:** mã hóa đường truyền, bảo vệ schema metadata, credential và API endpoints.
- **Naming convention:** thống nhất topic, subject strategy, namespace, event type và ownership.
- **Compatibility policy:** đặt chủ đích theo subject; thay policy là một thay đổi có rủi ro.
- **Schema review:** chủ sở hữu event và consumer quan trọng cùng review breaking changes.
- **Deprecation/retention:** biết version cũ nào còn được broker/outbox/DLQ hoặc service đọc.
- **CI enforcement:** check schema và test semantic fixtures trước merge/release.
- **Monitoring:** tỷ lệ lỗi đăng ký schema, serializer failures, cache misses, deserialization errors.
- **Data classification:** không tự động đưa password, token, PII vào event chỉ vì schema cho phép.
- **Audit:** ghi nhận ai, khi nào và vì sao một schema/compatibility policy thay đổi.

Lưu ý: bản thân schema có thể chứa field names, mô tả dữ liệu nhạy cảm hoặc namespace nội bộ. Không coi REST API registry là dịch vụ công khai chỉ vì nó không lưu mọi giá trị payload.

## 16. Sai lầm thường gặp

**Lỗi 1 — Nhầm subject version với schema ID.** Version tăng theo subject; schema ID do server cấp, có thể khác và được dùng lại khi cùng schema.

**Lỗi 2 — Dùng schemaVersion để sắp thứ tự event.** Schema version giải thích payload; thứ tự nghiệp vụ thuộc aggregate sequence/offset theo thiết kế.

**Lỗi 3 — Nghĩ Spring ApplicationEventPublisher tự tích hợp registry.** Nó chỉ publish object tới Spring listeners. Cần adapter, serializer và broker client khi vượt process boundary.

**Lỗi 4 — Coi BACKWARD là kiểm tra toàn lịch sử.** Default không transitive. Dùng `BACKWARD_TRANSITIVE` nếu yêu cầu hỗ trợ mọi version cũ.

**Lỗi 5 — Đặt default không đúng nghiệp vụ.** Avro có thể giải mã thành công nhưng tạo dữ liệu sai. Default phải được chứng minh bằng contract lịch sử.

**Lỗi 6 — Dùng generic schema compatibility thay cho consumer contract tests.** Registry kiểm tra cấu trúc, không biết mọi validation/billing rule của consumer.

**Lỗi 7 — Thay đổi field semantics nhưng không đổi contract.** Hai schema giống hệt nhau vẫn có thể bị ứng dụng hiểu sai nếu đơn vị hoặc thời điểm event thay đổi.

**Lỗi 8 — Xóa schema vì đã deploy v2.** Dữ liệu v1 còn trong retention, DLQ hoặc event store có thể không decode được.

**Lỗi 9 — Gắn `@Async` để biến event nội bộ thành integration event.** Async listener vẫn chạy trong tiến trình, không có schema registry, durable publish hay replay tự động.

**Lỗi 10 — Tắt compatibility trên production để vượt CI.** Thao tác này chuyển rủi ro sang consumer và gây lỗi muộn hơn.

**Lỗi 11 — Tưởng forward/backward giống nhau.** Phải luôn hỏi “reader là version nào, writer là version nào?”.

**Lỗi 12 — Cấu hình KafkaAvroSerializer nhưng quên subject naming strategy.** Schema có thể đăng ký vào subject không như mong đợi, gây lỗi lookup/compatibility.

**Lỗi 13 — Thử v2 bằng dữ liệu giả do serializer v2 sinh ra.** Không chứng minh đọc được bytes đã phát từ v1. Giữ golden fixtures lịch sử.

**Lỗi 14 — Coi broker ACK là xử lý nghiệp vụ thành công.** Broker ACK chỉ liên quan đến đường publish; consumer outcome là bước khác.

**Lỗi 15 — Không có idempotency.** Retry producer/outbox relay và broker redelivery có thể khiến cùng event đến nhiều lần, dù schema hoàn toàn hợp lệ.

## 17. Checklist triển khai schema versioning

1. Event type mô tả **cùng một sự thật nghiệp vụ** qua các version?
2. Đã thống nhất Avro/Protobuf/JSON Schema và serialization format chưa?
3. Subject naming strategy có rõ và nhất quán giữa producer/consumer?
4. Đã phân biệt schema ID, subject version, event type, schemaVersion và aggregateVersion?
5. Đã chọn compatibility policy phù hợp với retention và rolling deployment?
6. Nếu cần replay mọi version cũ, policy có thực sự transitive hoặc có adapter migration?
7. Mỗi field có định nghĩa kiểu, đơn vị, null, default và ngữ nghĩa?
8. Default được chứng minh từ nghiệp vụ thời kỳ cũ, không phỏng đoán?
9. Đã thử v2 reader với v1 writer và ngược lại khi yêu cầu full compatibility?
10. Đã kiểm thử với historical binary fixtures và consumer code thật?
11. CI có check registry compatibility trước khi đăng ký/deploy?
12. Đã kiểm soát auto-registration, quyền thay đổi schema và audit?
13. Khi phá compatibility, có event/topic/subject mới hoặc kế hoạch migration?
14. Producer/consumer có xử lý registry outage, serializer failure và cache behavior?
15. Khi cần không mất event, có outbox/relay/retry/broker confirm phù hợp?
16. Consumer có idempotency để chịu retry/redelivery và replay?
17. Có metric/log/tracing cho schema ID/subject/type, nhưng tránh log dữ liệu nhạy cảm?
18. Có lịch deprecate/readers cũ gắn với retention và yêu cầu lịch sử?

**Kết luận:** Schema Registry là một phần của **quản trị hợp đồng dữ liệu xuyên service**. Nó giúp producer/consumer tra cứu schema và chặn nhiều thay đổi cấu trúc không tương thích. Để tích hợp Spring Application Events ra broker an toàn, vẫn cần adapter internal→integration event, serialization có version, chiến lược nâng cấp, contract tests, xử lý transaction/độ bền và consumer idempotent. **Schema compatible là điều kiện quan trọng, nhưng chưa đủ để khẳng định hệ thống đúng về nghiệp vụ.**

## Tài liệu tham khảo

- [Confluent — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): các mode compatibility, transitive và thứ tự triển khai.
- [Confluent — Schema Registry REST API](https://docs.confluent.io/platform/current/schema-registry/develop/api.html): đăng ký schema, tra cứu subject/version và kiểm tra compatibility.
- [Confluent — Schema Registry REST Usage Examples](https://docs.confluent.io/platform/current/schema-registry/develop/using.html): các ví dụ `curl` và cấu hình compatibility.
- [Apache Avro — Specification](https://avro.apache.org/docs/current/specification/): record, default values và schema resolution.
- [Apache Avro Java — SchemaCompatibility API](https://avro.apache.org/docs/current/api/java/org/apache/avro/SchemaCompatibility.html): kiểm tra reader schema với writer schema.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher` và `@EventListener`.
- [Spring Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate` và handling của send future.
- [Spring Kafka — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html): `@KafkaListener`.
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): giảm rủi ro dual-write và duplicate publication.
