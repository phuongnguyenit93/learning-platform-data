# Tương thích ngược của payload trong Spring Framework Application Events

**Tương thích ngược (backward compatibility) của event payload** nghĩa là một consumer đã được viết theo hợp đồng cũ vẫn có thể xử lý dữ liệu do producer phiên bản mới tạo ra, trong phạm vi các cam kết tương thích đã công bố. Với Spring Framework Application Events, cần phân biệt rõ:

1. **Event trong cùng JVM:** publisher gửi một đối tượng Java qua `ApplicationEventPublisher`; `@EventListener` lựa chọn phương thức theo **kiểu event**. Tương thích liên quan đến tên class, package, constructor, method/accessor, type parameter và **ý nghĩa nghiệp vụ**.
2. **Event được tuần tự hóa:** payload được ghi vào outbox, audit log, Kafka/RabbitMQ hoặc truyền qua HTTP/JSON/Avro/Protobuf. Lúc này producer và consumer có thể chạy **nhiều phiên bản độc lập**, nên cần thêm hợp đồng **schema, cách đọc trường thiếu/thừa, phiên bản và chính sách migration**.

Một thay đổi có thể tương thích ở tầng Java nhưng không tương thích với JSON, hoặc ngược lại. Không nên gộp hai phạm vi dưới một nhãn “Spring tự tương thích”.

Ví dụ: phiên bản đầu của `OrderPlaced` chỉ có `orderId` và `customerId`. Phiên bản sau muốn thêm `channel` (kênh bán hàng). Nếu listener cũ chỉ đọc hai thuộc tính đầu, có thể thiết kế để listener đó **không cần sửa code**. Nhưng nếu xóa `customerId` hoặc đổi đơn vị của một trường từ đồng sang xu, sự thay đổi có thể phá vỡ logic dù chương trình vẫn biên dịch.

## 1. Mô hình producer, payload và consumer

```text
            Producer                    Spring Event Bus              Consumer
    OrderService / Aggregate       ApplicationEventPublisher       @EventListener
              |                              |                            |
              |-- OrderPlaced(payload) ----->|-- dispatch theo Java type ->|
              |                              |                            |
              |                              |                     đọc các field
              |                              |                     theo hợp đồng
              v                              v                            v
  phiên bản có thể thay đổi        cùng JVM, cùng classpath       listener cũ / mới

Nếu còn có outbox hoặc message broker:
      Object Java -> serialize -> schema/message -> deserialize -> Consumer khác
                       ^              ^                 ^
                    format        version policy     unknown/missing field
```

Trong Spring Framework, `publishEvent(Object)` nhận cả đối tượng thường, không bắt buộc kế thừa `ApplicationEvent`. Khi truyền một POJO/record, Spring đóng gói nó trong `PayloadApplicationEvent` để phân phối; phương thức `@EventListener` vẫn có thể khai báo tham số là **chính kiểu payload**.

```java
public record OrderPlaced(String orderId, String customerId) {}

@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Được gọi khi publisher phát payload OrderPlaced phù hợp.
}
```

Đây là **mã khung**, không phải chương trình độc lập. Việc mở rộng thêm một trường không tạo ra cơ chế chuyển đổi phiên bản tự động: Spring không tự map một `OrderPlacedV2` độc lập thành `OrderPlacedV1`.

### Ba cấp tương thích cần xem riêng

| Cấp | Câu hỏi | Ví dụ phá vỡ |
| --- | --- | --- |
| **Source compatibility** | Source code consumer cũ có còn biên dịch với thư viện event mới? | Xóa accessor `customerId()` mà code cũ gọi |
| **Binary compatibility** | Consumer đã biên dịch trước đó có còn link/chạy với class event mới? | Xóa constructor `OrderPlaced(String, String)` mà bytecode cũ gọi |
| **Semantic compatibility** | Consumer cũ có còn hiểu **đúng nghiệp vụ** dù code chạy được? | Đổi `amount` từ đồng sang xu nhưng giữ tên và kiểu `long` |
| **Wire/schema compatibility** | Consumer độc lập có đọc được JSON/Avro/message từ producer mới? | Đổi `orderId` thành `id` nhưng không hỗ trợ alias/upcast |

**Quan trọng:** binary/source compatibility không đồng nghĩa semantic compatibility. Một thay đổi “chỉ đổi nghĩa” có thể nguy hiểm hơn lỗi biên dịch vì làm hệ thống âm thầm xử lý sai.

## 2. Quy tắc tiến hóa payload an toàn

### 2.1. Ưu tiên bổ sung trường tùy chọn có giá trị mặc định hợp lý

Giả sử `OrderPlaced` v1 có:

```json
{
  "eventType": "order.placed",
  "schemaVersion": 1,
  "eventId": "evt-101",
  "orderId": "ORD-42",
  "customerId": "CUS-7"
}
```

Một thông điệp v2 bổ sung `channel`:

```json
{
  "eventType": "order.placed",
  "schemaVersion": 2,
  "eventId": "evt-102",
  "orderId": "ORD-43",
  "customerId": "CUS-7",
  "channel": "MOBILE"
}
```

Thiết kế có thể hỗ trợ:

- Consumer **mới đọc message cũ**: nếu thiếu `channel`, dùng giá trị mặc định **có ngữ nghĩa rõ** như `UNKNOWN`.
- Consumer **cũ đọc message mới**: có thể tiếp tục xử lý nếu bộ deserializer được cấu hình **bỏ qua trường không biết** và không phụ thuộc vào việc object có đúng một tập trường cố định.
- Producer phải duy trì ý nghĩa của `orderId` và `customerId`; không đổi kiểu hoặc ý nghĩa ngầm.
- Phải kiểm thử **cả hai chiều** nếu hệ thống có rolling deployment hoặc khả năng replay event lịch sử.

**Không được giả định mọi thư viện JSON tự bỏ qua trường lạ.** Ví dụ Jackson thuần có cấu hình xử lý unknown properties và constructor khác với mapper do Spring Boot tùy chỉnh. Với record, một trường thiếu có thể được truyền `null` vào constructor, tùy phiên bản và cấu hình deserializer. Nếu muốn hợp đồng tương thích, cần kiểm thử **mapper thực tế** của ứng dụng.

### 2.2. Không xóa/đổi tên trường còn consumer sử dụng

Các thao tác rủi ro cao:

- Đổi `orderId` thành `id` mà không giữ tên cũ/alias trên wire.
- Đổi `amount` từ `long` sang `String` hoặc đổi đơn vị tiền không có trường `currency`/`unit` rõ ràng.
- Đổi `occurredAt` từ ISO-8601 có timezone sang epoch milliseconds mà giữ nguyên tên field.
- Biến một trường có thể null thành bắt buộc non-null mà dữ liệu lịch sử không có.
- Thay đổi `eventType` hay Java class/package dùng để phân phối event mà không có adapter.
- Thay enum bằng tập giá trị mới mà consumer cũ xử lý bằng `switch` không có fallback.

Nếu thay đổi là **breaking change**, hãy tạo một phiên bản event mới, xây adapter/upcaster hoặc dùng thời gian chuyển tiếp để chuyển consumer. Việc “sửa tại chỗ” một schema cũ đang được lưu/replay thường khiến dữ liệu lịch sử khó đọc.

### 2.3. Đặt default phải phản ánh nghiệp vụ

Không phải trường nào thiếu cũng có thể thay bằng `""`, `0` hoặc `false`. Ví dụ:

- `channel = UNKNOWN` là hợp lý khi consumer chỉ cần phân loại kênh và chấp nhận nhóm không rõ.
- `discountPercent = 0` **không luôn** giống “không có thông tin giảm giá”, vì 0% có nghĩa nghiệp vụ cụ thể.
- `currency = VND` là nguy hiểm nếu trước đây hệ thống có nhiều loại tiền.
- Trường bắt buộc để quyết định thanh toán **không nên default bừa**; phải chuyển sang schema mới hoặc bổ sung bước enrichment/validation.

Một default tốt cần được ghi trong hợp đồng và có test với event lịch sử.

## 3. Java 17+ chạy được: thêm trường mà vẫn hỗ trợ listener cũ

Đây là ví dụ **in-process Spring Application Events**, minh họa trường hợp **giữ nguyên Java type** và **bảo toàn constructor cũ** khi phát triển record.

Ban đầu người dùng tạo event bằng constructor `new OrderPlaced(orderId, customerId)`. Bản mới bổ sung `channel`, đồng thời giữ constructor **hai tham số** để mã caller cũ không bị buộc phải đổi ngay. Listener cũ chỉ biết hai accessor `orderId()`/`customerId()`, còn listener mới đọc cả `channel()`.

### 3.1. Cấu trúc dự án

```text
payload-compatibility-demo/
├── pom.xml
└── src/main/java/PayloadCompatibilityDemo.java
```

### 3.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>payload-compatibility-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <configuration>
                    <mainClass>PayloadCompatibilityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.3. `src/main/java/PayloadCompatibilityDemo.java`

```java
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class PayloadCompatibilityDemo {

    // Phiên bản đã tiến hóa: thêm channel nhưng giữ API cũ.
    public record OrderPlaced(
            String orderId,
            String customerId,
            String channel) {

        public OrderPlaced {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(customerId, "customerId");
            channel = (channel == null || channel.isBlank())
                    ? "UNKNOWN" : channel;
        }

        // Caller cũ vẫn gọi được constructor hai tham số.
        public OrderPlaced(String orderId, String customerId) {
            this(orderId, customerId, "UNKNOWN");
        }
    }

    public static class LegacyListener {
        @EventListener
        @Order(10)
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("legacy: order=" + event.orderId()
                    + " customer=" + event.customerId());
        }
    }

    public static class ModernListener {
        @EventListener
        @Order(20)
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("modern: order=" + event.orderId()
                    + " channel=" + event.channel());
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(LegacyListener.class);
            context.registerBean(ModernListener.class);
            context.refresh();

            System.out.println("publish old signature");
            context.publishEvent(new OrderPlaced("ORD-42", "CUS-7"));

            System.out.println("publish new signature");
            context.publishEvent(
                    new OrderPlaced("ORD-43", "CUS-7", "MOBILE"));
        }
    }
}
```

Chạy từ thư mục dự án (cần JDK 17+, Maven và mạng để tải dependency lần đầu):

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in ra, theo thứ tự:

```text
publish old signature
legacy: order=ORD-42 customer=CUS-7
modern: order=ORD-42 channel=UNKNOWN
publish new signature
legacy: order=ORD-43 customer=CUS-7
modern: order=ORD-43 channel=MOBILE
```

**Giải thích:**

1. `OrderPlaced` là Java record mới có ba component, nhưng có một constructor hai tham số chuyển sang constructor chính và gán `channel = "UNKNOWN"`.
2. `LegacyListener` chỉ gọi các accessor cũ, nên vẫn xử lý được cả hai event trong ví dụ. `ModernListener` đọc thêm thuộc tính mới.
3. `@Order(10)` và `@Order(20)` giúp ví dụ có thứ tự hiển thị rõ ràng trong cấu hình listener đồng bộ mặc định; không nên mặc định rằng mọi listener bất đồng bộ luôn hoàn tất theo thứ tự này.
4. `AnnotationConfigApplicationContext` và `@EventListener` cho phép nhận plain object: Spring tự đóng gói payload thích hợp khi `publishEvent(...)` được gọi.

**Giới hạn của ví dụ:** Nó chứng minh **đường gọi API cụ thể** và hành vi listener trong **một JVM chạy cùng phiên bản class mới**; không chứng minh mọi binary cũ, mọi serializer, reflection hay consumer ở môi trường khác đều tương thích. Theo Java Language Specification, **thêm/xóa/đổi thứ tự record components có thể phá binary compatibility**, đặc biệt vì constructor chuẩn, các accessor, `equals()`, `hashCode()` và biểu diễn record có thể thay đổi. Constructor tương thích hai tham số chỉ bảo toàn một phần hợp đồng mà caller dùng.

Nếu cần giữ hợp đồng lâu dài với nhiều thư viện đã được build, cân nhắc event dưới dạng một class bất biến có constructor/factory ổn định, hoặc dùng DTO version tách biệt. Test Java bytecode cũ trong CI nếu binary compatibility là yêu cầu thật.

## 4. Tương thích JSON không tự động suy ra từ tương thích Java

Đối với event chỉ sống trong `ApplicationEventPublisher`, Spring thường dispatch theo Java type, không cần serialize payload. Một khi event được chuyển thành JSON, Avro hoặc Protobuf, cần thỏa thuận rõ:

| Thành phần | Quy tắc gợi ý |
| --- | --- |
| `eventType` | Tên nghiệp vụ ổn định, tách khỏi tên class/package Java |
| `schemaVersion` | Phiên bản schema được công bố rõ; đặc biệt quan trọng với event được lưu/replay |
| `eventId` | ID duy nhất cho một **sự kiện logic**, phục vụ deduplication/idempotency |
| `aggregateId` | Khóa aggregate/đối tượng nghiệp vụ liên quan, hỗ trợ routing và tracing |
| `occurredAt` | Thời điểm xảy ra với format/timezone quy ước |
| Payload fields | Kiểu, đơn vị, ý nghĩa, optionality/default, quy tắc alias |
| Unknown fields | Phải quy định consumer làm gì với trường mới không biết |
| Missing fields | Phải quy định consumer làm gì khi gặp event cũ thiếu trường |
| Enums | Phải có chính sách xử lý giá trị mới hoặc version mới |

Với Jackson, có thể cấu hình DTO consumer cũ bỏ qua trường không nhận biết:

```java
// Mã minh họa; cần dependency Jackson và import annotation tương ứng.
@JsonIgnoreProperties(ignoreUnknown = true)
public record LegacyOrderPlacedDto(
        String orderId,
        String customerId) {}
```

Điều này chỉ giúp **bỏ qua trường không biết**; nó không sửa đổi nghĩa của những trường đã biết, cũng không tự bảo đảm việc deserializing record khi thiếu dữ liệu bắt buộc. Cần kiểm thử `ObjectMapper` thực tế, bao gồm constructor, null-handling, thời gian, enum và chính sách strict validation.

Không gắn tên class Java vào JSON rồi dựa vào `@class` polymorphic metadata nếu không kiểm soát được contract và danh sách type được phép: thay package/class sẽ làm wire format phụ thuộc code, còn polymorphic deserialization trên input không tin cậy có thể tạo rủi ro bảo mật. Ưu tiên `eventType` và schema tường minh cùng ánh xạ có kiểm soát.

### Backward và forward compatibility khác nhau

- **Backward compatibility:** consumer **mới** đọc được message **cũ**; hữu ích cho replay lịch sử sau khi deploy phiên bản mới.
- **Forward compatibility:** consumer **cũ** đọc được message **mới**; quan trọng khi producer deploy trước consumer hoặc khi nhiều phiên bản chạy đồng thời.

Trong ngôn ngữ giao tiếp, đôi khi người ta dùng “backward compatibility” để chỉ mọi dạng consumer cũ không bị hỏng. Khi lập kế hoạch triển khai, nên ghi rõ **hướng đọc cụ thể** thay vì chỉ dùng một nhãn. Nếu đòi hỏi cả hai chiều, producer và consumer cần đáp ứng **full compatibility** theo policy schema áp dụng.

## 5. Khi thay đổi phá vỡ hợp đồng: tạo event V2 và adapter

Một số thay đổi không nên cố “ép” vào cùng class hoặc cùng schema:

- Xóa trường từng là bắt buộc ở consumer.
- Đổi `String customerId` thành một cấu trúc ID khác mà consumer cũ không hiểu.
- Gộp nhiều ý nghĩa nghiệp vụ vào một event cũ hoặc tách một event thành nhiều sự kiện có semantic khác nhau.
- Đổi thứ tự/kiểu tham số public constructor mà thư viện cũ đang dùng.
- Đổi quy tắc “OrderPlaced nghĩa là đơn đặt thành công” thành “đơn mới được tạo nháp”.

Khi đó, mô hình hóa rõ ràng:

```java
public record OrderPlacedV1(String eventId, String orderId) {}

public record OrderPlacedV2(
        String eventId,
        String orderId,
        String customerId,
        String salesChannel) {}
```

Hai record trên là **hai Java type khác nhau**. Listener nhận `OrderPlacedV1` **không tự** nhận `OrderPlacedV2` nếu chúng không có quan hệ kiểu phù hợp. Spring event bus không tự “upcast” các phiên bản.

Một lộ trình chuyển tiếp có thể là:

1. **Inventory** các consumer, nơi lưu event và dữ liệu lịch sử; tìm field nào đang được sử dụng.
2. **Triển khai consumer hiểu V2** hoặc thêm adapter từ V1 sang mô hình domain hiện tại; giữ đọc V1 trong thời gian còn event cũ.
3. **Dual-publish trong giai đoạn chuyển tiếp** nếu thực sự có consumer chỉ hiểu V1, nhưng phải gắn cùng `eventId`/correlation ID để tránh xử lý nghiệp vụ hai lần. Nếu có thể, ưu tiên giữ một message logical và một adapter ở lớp tiêu thụ thay vì dual-publish tràn lan.
4. **Đo lượng tiêu thụ** của V1, xác định thời gian lưu/replay và lịch hủy theo chính sách.
5. **Ngừng phát V1** sau khi các consumer cũ đã được di chuyển; không xóa ngay khả năng đọc V1 nếu còn event lịch sử cần replay.

Ví dụ *minh họa publisher chuyển tiếp*, không phải ứng dụng độc lập:

```java
public void publishDuringMigration(String eventId, String orderId) {
    // Chỉ làm nếu đã thiết kế dedup và cần tương thích hai loại consumer.
    applicationEventPublisher.publishEvent(
            new OrderPlacedV1(eventId, orderId));
    applicationEventPublisher.publishEvent(
            new OrderPlacedV2(eventId, orderId, "CUS-7", "MOBILE"));
}
```

Hai bản phát có thể dẫn tới **hai lần side effect** nếu một consumer đăng ký cả V1 lẫn V2. Một phép kiểm tra `eventId` trong consumer/inbox hoặc luật loại bỏ V1 rõ ràng là bắt buộc khi side effect không idempotent. Trong một Spring application event bus đồng bộ, exception của listener có thể ảnh hưởng luồng publish; dual-publish không phải một transaction bất khả phân tự động.

### Upcaster trong event store hoặc consumer

Với event bền vững, có thể để dữ liệu lịch sử bất biến và áp dụng **upcaster** lúc đọc:

```text
Stored OrderPlaced v1
       |
       v
decode + validate schemaVersion == 1
       |
       v
upcast: thêm channel = UNKNOWN, giữ eventId/orderId
       |
       v
Current internal OrderPlaced representation
       |
       v
Business handler
```

Upcaster cần có test cho dữ liệu thiếu, enum cũ, timestamp và format cũ. Không nên sửa nghĩa lịch sử của event hoặc tạo thông tin giả. Upcaster là lớp chuyển đổi **message/DTO**, không phải một feature tự động của `@EventListener`.

## 6. Cách triển khai thay đổi an toàn trong ứng dụng thật

### Bước 1: Định nghĩa contract trước khi sửa record

Ghi rõ:

- Event type/name và ý nghĩa nghiệp vụ bất biến.
- Field nào bắt buộc, field nào optional, default có nghĩa gì.
- Các consumer phụ thuộc vào field nào, có consumer nào chạy độc lập phiên bản không.
- Event có lưu vào outbox/log để replay hay chỉ được phát trong cùng JVM.
- Ranh giới transaction của publication và side effect.

### Bước 2: Phân loại loại thay đổi

| Thay đổi | Đánh giá mặc định | Hành động |
| --- | --- | --- |
| Thêm field optional có default an toàn | Thường tương thích **nếu consumer chấp nhận unknown field** | Test consumer cũ + mới, cấu hình serializer |
| Giữ field cũ và thêm constructor/factory | Có thể giúp API Java cũ | Kiểm thử source/binary; tránh tuyên bố bảo đảm tuyệt đối với record |
| Xóa/đổi tên field cũ | Breaking với consumer sử dụng field | Alias/upcaster hoặc V2 |
| Đổi kiểu hoặc đơn vị field | Thường breaking cả khi Java vẫn compile | Tạo field mới, deprecate field cũ hoặc V2 |
| Đổi tập giá trị enum | Có thể breaking semantic | Fallback `UNKNOWN`/validation hoặc version mới |
| Đổi class/package của event Java | Breaking với listener/caller cũ | Adapter hoặc migrate đồng bộ |
| Thay đổi thời điểm phát từ trước sang sau commit | Thay đổi semantic quan trọng | Review listener/transaction, test ordering và retry |
| Thay payload Java thành message external | Thêm hợp đồng wire/delivery | Đặt `eventId`, schema policy, outbox, idempotency |

### Bước 3: Triển khai theo hướng consumer-first khi có rolling deployment

Ví dụ v1 -> v2 thêm `channel`:

1. Consumer v2 biết đọc cả thông điệp thiếu `channel`.
2. CI kiểm tra consumer v1 (hoặc một binary/fixture tương đương) đọc v2 đúng **nếu yêu cầu chạy song song**.
3. Producer mới bắt đầu phát payload có `channel`.
4. Sau thời gian chuyển đổi, mới cân nhắc đặt `channel` thành required, nếu không còn dữ liệu lịch sử và consumer v1.

Nếu không thể bảo đảm bước 2, không phát schema v2 chưa tương thích cho consumer v1. Hãy dùng schema version riêng, endpoint/topic riêng hoặc adapter tách biệt theo kiến trúc.

### Bước 4: Không quên yếu tố Spring transaction

`ApplicationEventPublisher.publishEvent(...)` với multicaster mặc định thường đồng bộ trong thread publisher. Nếu publisher đang nằm trong transaction, listener `@EventListener` có thể chạy **trước khi commit**. Khi cần xử lý chỉ sau commit thành công, dùng:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderPlaced event) {
    // Phản ứng sau commit, với điều kiện event được publish trong transaction.
}
```

Đây là **đoạn minh họa tích hợp**, cần đúng Spring bean và import transaction annotation. Listener dạng này mặc định **không chạy nếu event được phát ngoài transaction** (`fallbackExecution = false`). Lỗi sau commit không rollback transaction đã hoàn tất.

**Tương thích payload không giải quyết độ tin cậy giao nhận.** Nếu event phải được đưa sang hệ thống khác một cách bền vững, cân nhắc ghi **Transactional Outbox** cùng transaction của aggregate, rồi gửi/retry độc lập sau commit. Thiết kế consumer idempotent theo `eventId`. Mô hình event bus trong JVM tự nó không phải message broker có lưu trữ và replay.

## 7. Kiểm thử hợp đồng tương thích

Không nên chỉ viết một test cho producer mới. Tập test nên bao gồm các tổ hợp phiên bản:

| Producer / dữ liệu | Consumer | Kỳ vọng |
| --- | --- | --- |
| V1 Java constructor (2 tham số) | Listener hiện tại chỉ dùng field cũ | Không lỗi, ý nghĩa dữ liệu giữ nguyên |
| V2 Java constructor (3 tham số) | Listener cũ | Vẫn đọc `orderId`/`customerId` đúng |
| V2 Java constructor | Listener mới | Đọc đúng `channel` |
| JSON V1 thiếu `channel` | Consumer V2 | Áp dụng default được thỏa thuận hoặc báo lỗi hợp đồng rõ |
| JSON V2 thừa `channel` | Consumer V1 | Bỏ qua trường lạ **nếu** policy cho phép |
| Dữ liệu lịch sử có enum/timestamp khác | Consumer V2/upcaster | Chuyển đổi đúng, không tự bịa dữ liệu |
| Consumer binary cũ đã biên dịch | Artifact event mới | Link thành công hoặc xác định breaking change sớm |
| Event sau commit + lỗi listener | Consumer/transaction | Dữ liệu transaction nguồn đã commit không bị đảo ngược |

Một phương án test thực tế:

- **Golden JSON fixtures**: lưu mẫu v1/v2 và chạy deserialize với `ObjectMapper` đúng cấu hình production.
- **Consumer-driven contract tests**: consumer công bố các kỳ vọng cần giữ; pipeline của producer kiểm tra trước khi đổi schema.
- **Binary compatibility checks**: chạy test với JAR consumer **đã build từ phiên bản cũ**, không chỉ compile lại toàn bộ source; xem xét công cụ so sánh public API nếu thư viện event được phân phối rộng.
- **Semantic checks**: kiểm tra đơn vị, timezone, nullability, enum fallback và quan hệ giữa các field.
- **Replay/upcaster tests**: phát lại mẫu event lịch sử và kiểm tra kết quả handler, đặc biệt các trường không còn có thể tái tạo.
- **Delivery/idempotency checks**: nếu dual-publish, retry hoặc outbox, bảo đảm cùng logical `eventId` không gây side effect trùng.

Một test chỉ chứng minh chương trình vẫn compile **không đủ** kết luận tương thích ngược. Mục tiêu là bảo toàn **hành vi của consumer cũ trong các tình huống thực tế**.

## 8. Các lỗi phổ biến và cách sửa

**Lỗi 1: Thêm component vào Java record rồi tuyên bố tương thích tuyệt đối.**  
Record thay đổi canonical constructor, metadata components, `equals/hashCode` và có thể tác động đến binary, reflection, JSON mapping. Giữ constructor cũ chỉ bảo vệ những call site cụ thể; kiểm thử chính xác contract đã công bố.

**Lỗi 2: Dùng tên class làm event type trên wire.**  
Đổi package Java có thể vô tình làm vỡ dữ liệu cũ. Định nghĩa một `eventType` nghiệp vụ ổn định và mapping có kiểm soát.

**Lỗi 3: Thêm field bắt buộc mà không có default cho event lịch sử.**  
Replay V1 sẽ thất bại. Hãy khai báo field optional/unknown hoặc áp dụng upcaster có logic xác định.

**Lỗi 4: Bỏ qua unknown fields mà không kiểm tra ý nghĩa.**  
Deserializer có thể đọc được message nhưng consumer vẫn xử lý sai nếu một enum/đơn vị tiền đã đổi. Phải test semantic compatibility, không chỉ parsing.

**Lỗi 5: Dual-publish V1 và V2 rồi consumer xử lý hai lần.**  
Cần `eventId` cho cùng logical event, cơ chế dedup/idempotency và lịch chuyển đổi có thời hạn.

**Lỗi 6: Cho rằng Spring tự chuyển V1 sang V2.**  
`@EventListener` dispatch theo type, không phải schema migration engine. Dùng adapter/upcaster rõ ràng khi breaking.

**Lỗi 7: Trộn lẫn “event đã publish” với “transaction đã commit”.**  
Listener đồng bộ có thể chạy trước commit; với side effect chỉ sau commit dùng `@TransactionalEventListener` hoặc outbox phù hợp.

**Lỗi 8: Bật Jackson ignore-unknown rồi xem như mọi thay đổi đều an toàn.**  
Cờ này không sửa field bị xóa, đổi loại, thay nghĩa hoặc dữ liệu bị null. Cần schema policy và contract tests.

## 9. Câu hỏi tự đánh giá

**1. Một listener cũ nhận `OrderPlaced(orderId, customerId)`; producer mới cần thêm `channel`. Hướng ưu tiên là gì?**  
Giữ các field và ý nghĩa cũ, thêm `channel` với default/optional rõ ràng, duy trì API cần thiết cho caller cũ, rồi kiểm tra cả listener Java và serializer nếu event được tuần tự hóa.

**2. Vì sao thêm field vào Java record không luôn binary-compatible?**  
Vì có thể thay đổi canonical constructor, các thành phần/metadata và những API mà bytecode/serialization cũ dựa vào. Cần kiểm thử binary cũ, không chỉ source mới.

**3. Spring có tự chuyển một `OrderPlacedV2` độc lập thành `OrderPlacedV1` để listener cũ nhận không?**  
Không. Nếu hai class không có quan hệ kiểu phù hợp, phải có lớp adapter/dual-publish được thiết kế rõ.

**4. Consumer V1 có đọc được JSON V2 thêm field không?**  
Chỉ khi deserializer/schema policy cho phép unknown fields và phần semantic mà consumer cần vẫn được giữ. Không được giả định.

**5. Tại sao eventId quan trọng trong thời kỳ dual-publish?**  
Vì một logical event có thể đi tới cùng side effect qua hai phiên bản hoặc retry. Stable eventId giúp consumer/inbox loại bỏ xử lý trùng.

**6. Nếu transaction rollback sau khi `@EventListener` đã chạy, payload có tự bị thu hồi không?**  
Không. Event bus không đảo ngược side effect. Chọn transaction-bound listener hoặc outbox tùy yêu cầu nhất quán.

## 10. Tài liệu tham khảo

- [Spring Framework 6.2 — Standard and Custom Events, `ApplicationEventPublisher` và `@EventListener`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2.9 Javadoc — `ApplicationEventPublisher`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2.9 Javadoc — `EventListener`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html)
- [Java Language Specification — Binary Compatibility, Evolution of Record Classes (`13.4.27)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html#jls-13.4.27)

