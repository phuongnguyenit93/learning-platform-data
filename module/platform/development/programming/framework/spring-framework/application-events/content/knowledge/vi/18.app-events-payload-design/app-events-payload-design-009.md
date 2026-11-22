# Version của event: thiết kế payload có thể tiến hóa trong Spring Application Events

## 1. Vì sao phải version hóa event?

Event thường được tạo ở một thời điểm nhưng có thể được xử lý ở một thời điểm khác, bởi code của một phiên bản khác. Ngay cả với `ApplicationEventPublisher` chạy trong cùng tiến trình, producer và listener vẫn có thể thay đổi theo từng đợt triển khai. Nếu event còn được ghi vào outbox, lưu trữ để replay, hoặc chuyển qua Kafka/RabbitMQ, **payload cũ có thể tồn tại rất lâu sau khi code đã nâng cấp**.

Giả sử lúc đầu ứng dụng phát event `OrderPlaced`:

```json
{
  "orderId": "ORD-101",
  "amountMinorUnits": 1250
}
```

Sau đó hệ thống hỗ trợ nhiều đồng tiền và kênh bán:

```json
{
  "orderId": "ORD-101",
  "amountMinorUnits": 1250,
  "currency": "USD",
  "channel": "web"
}
```

Nếu consumer mới mặc định `currency` luôn có mặt, event cũ có thể gây lỗi. Nếu producer mới gửi thêm field nhưng consumer cũ dùng deserializer chỉ cho phép đúng các field ban đầu, việc nâng cấp producer trước cũng có thể làm consumer cũ lỗi. Và nếu `amountMinorUnits` bị đổi ý nghĩa từ "đơn vị nhỏ nhất" sang "số tiền đã chia 100", đó là **thay đổi ngữ nghĩa**, không thể giải quyết chỉ bằng việc chấp nhận field mới.

**Version của event** là cách xác định hợp đồng dữ liệu và quy tắc diễn giải của một dạng sự kiện trong quá trình phát triển. Mục tiêu không phải tăng số version ở mọi lần chỉnh code, mà là giúp producer và consumer biết một payload có thể đọc đúng bằng hợp đồng nào.

## 2. Phân biệt ba loại version

| Thuộc tính | Ý nghĩa | Có cần luôn giống nhau? |
| --- | --- | --- |
| `schemaVersion` / `eventVersion` | Phiên bản **hợp đồng payload** của một loại event | Không |
| `aggregateVersion` / `revision` | Thứ tự thay đổi trạng thái của một aggregate; thường dùng concurrency control hoặc event sourcing | Không |
| Phiên bản ứng dụng / artifact | Phiên bản triển khai của service hoặc thư viện Java | Không |

Ví dụ event `order.placed` dùng `schemaVersion=2` có thể là thay đổi thứ 17 của aggregate `ORD-101` (`aggregateVersion=17`), do phiên bản ứng dụng 4.8.1 phát ra. Ba con số này trả lời **ba câu hỏi khác nhau**.

- `schemaVersion=2`: payload có định dạng và cách hiểu theo hợp đồng v2.
- `aggregateVersion=17`: aggregate đã trải qua 17 bước cập nhật theo mô hình hệ thống.
- Ứng dụng 4.8.1: bản build triển khai; nhiều bản build có thể cùng phát một schema version.

**Spring Framework không tự cấp hay quản lý `schemaVersion` cho mọi event POJO.** `ApplicationEventPublisher.publishEvent(Object)` chỉ publish một đối tượng; việc gắn version, lưu JSON và kiểm tra tương thích là trách nhiệm của thiết kế ứng dụng hoặc nền tảng messaging/schema mà ứng dụng dùng.

Một record Java tên `OrderPlacedV2` cũng **không tự động** làm các bản ghi JSON trên broker trở thành v2: cần mapping, serializer và hợp đồng dữ liệu rõ ràng.

## 3. Đặt version ở đâu trong payload?

Đối với event lưu bền hoặc gửi qua mạng, cách phổ biến là tách **envelope metadata** và **payload nghiệp vụ**:

```json
{
  "eventId": "8f8e6278-9229-4c93-aeac-38f5590663b3",
  "eventType": "order.placed",
  "schemaVersion": 2,
  "occurredAt": "2026-09-01T10:15:30Z",
  "aggregateId": "ORD-101",
  "payload": {
    "orderId": "ORD-101",
    "amountMinorUnits": 1250,
    "currency": "USD",
    "channel": "web"
  }
}
```

Những trường thường được dùng:

- **`eventId`:** định danh của một lần phát sinh sự kiện; dùng để nhận diện bản sao khi retry/delivery lặp.
- **`eventType`:** tên loại sự kiện ổn định về nghiệp vụ, ví dụ `order.placed`.
- **`schemaVersion`:** phiên bản hợp đồng cho chính `eventType` đó.
- **`occurredAt`:** thời điểm sự kiện xảy ra, dùng timestamp định dạng chuẩn và múi giờ rõ.
- **`aggregateId`:** định danh đối tượng nghiệp vụ liên quan, nếu hợp đồng có aggregate.
- **`payload`:** dữ liệu nghiệp vụ có thể thay đổi từ phiên bản này sang phiên bản khác.

Đây là **mẫu envelope do ứng dụng tự thiết kế**, không phải cấu trúc do Spring Application Events bắt buộc. Một event thuần Java chỉ được truyền trong cùng context có thể không cần serialize và cũng không cần envelope đầy đủ. Nhưng nếu có replay hoặc integration, metadata tách biệt giúp quản lý version và giám sát dễ hơn.

Khi version hóa, hãy định nghĩa quy tắc tăng version **theo từng loại event**, không dùng chung một con số toàn hệ thống. `order.placed/v2` không bắt buộc đồng bộ với `payment.authorized/v2`.

## 4. Quy tắc thay đổi tương thích và không tương thích

### 4.1. Tương thích ngược và tương thích xuôi

Trong thiết kế sự kiện:

- **Backward compatibility:** consumer dùng schema mới đọc được thông điệp được tạo theo schema cũ.
- **Forward compatibility:** consumer dùng schema cũ đọc được thông điệp do producer schema mới tạo.
- **Full compatibility:** đáp ứng cả hai chiều theo chính sách và định dạng serializer/schema đang dùng.

Đừng chỉ dựa vào tên gọi "optional": khả năng tương thích thực tế phụ thuộc **định dạng** (JSON, Avro, Protobuf...), **quy tắc validate**, **deserializer** và **logic ứng dụng**. Chẳng hạn thêm field JSON có thể được consumer cũ bỏ qua hoặc bị từ chối nếu consumer cũ cấu hình không nhận unknown properties.

| Loại thay đổi | Rủi ro | Cách tiếp cận |
| --- | --- | --- |
| Thêm field tùy chọn với default có ý nghĩa | Thường thấp nếu consumer cũ bỏ qua unknown field | Ưu tiên additive evolution; kiểm thử cả hai chiều |
| Thêm field bắt buộc mà event cũ không có | Cao đối với consumer mới đọc lịch sử | Tạo default hợp lệ hoặc phiên bản mới kèm chuyển đổi |
| Đổi tên `orderId` thành `id` | Cao | Duy trì alias/mapping hoặc phát v2 theo hợp đồng mới |
| Đổi kiểu `amountMinorUnits` thành chuỗi tùy ý | Cao | Dùng field mới, adapter hoặc schema version mới |
| Đổi nghĩa trường mà không đổi tên | Rất cao, dễ sai âm thầm | Coi là breaking change; version/new event type |
| Bỏ field đang được consumer sử dụng | Cao | Quan sát usage, deprecate, chuyển đổi consumer rồi mới bỏ |
| Thay enum bằng tập giá trị mới | Phụ thuộc consumer có xử lý giá trị lạ không | Dùng nhánh unknown/fallback hoặc nâng contract |
| Đổi cấu trúc object lồng nhau | Có thể cao | Upcaster và contract test cho dữ liệu lịch sử |

Một thay đổi "cộng thêm field" chỉ an toàn khi đã rõ cách consumer cũ hoạt động. **Tương thích về cú pháp không đồng nghĩa tương thích về nghiệp vụ**: consumer cũ có thể hiểu sai tổng tiền, trạng thái hoặc đơn vị đo ngay cả khi JSON vẫn deserialize được.

### 4.2. Default phải có cơ sở nghiệp vụ

Giả sử hợp đồng `OrderPlacedV1` ghi rõ tất cả đơn hàng đều thanh toán bằng USD. Khi nâng sang `OrderPlacedV2` có `currency`, giá trị `"USD"` cho event v1 là **default có căn cứ**.

Nếu v1 đã có thể là nhiều đồng tiền nhưng không ghi field, tự đặt `USD` là **bịa thông tin**. Hãy chọn chiến lược chính xác hơn, ví dụ:

- Tra cứu bản ghi giao dịch gốc theo ID có kiểm soát.
- Đánh dấu `currency=UNKNOWN` và yêu cầu consumer xử lý nhánh thiếu thông tin.
- Không cho phép diễn giải dữ liệu cũ bằng schema mới nếu không đủ dữ kiện.
- Thiết kế migration có audit và cách xử lý dữ liệu không xác định.

Đừng lặng lẽ đưa default làm thay đổi kết quả kế toán, thuế, thanh toán hoặc phân quyền.

## 5. Ví dụ v1/v2 rõ ràng: cùng nghiệp vụ, hợp đồng khác nhau

**Hợp đồng giả định cho ví dụ:**

- `OrderPlacedV1` gồm `orderId` và `amountMinorUnits`; trong thời kỳ v1, **tất cả đơn hàng đều là USD**.
- `OrderPlacedV2` bổ sung `currency` và `channel`; `channel` mô tả kênh tạo đơn.
- Consumer muốn chuyển cả hai về mô hình đọc nội bộ thống nhất (*canonical representation*).
- Nếu v1 không có kênh bán, trả `unknown` thay vì tự suy ra `web`.

Ví dụ JSON độc lập với Spring:

```json
{
  "eventType": "order.placed",
  "schemaVersion": 1,
  "payload": {
    "orderId": "ORD-101",
    "amountMinorUnits": 1250
  }
}
```

```json
{
  "eventType": "order.placed",
  "schemaVersion": 2,
  "payload": {
    "orderId": "ORD-102",
    "amountMinorUnits": 9900,
    "currency": "USD",
    "channel": "mobile"
  }
}
```

Đối với hệ thống dùng serialization, router phải đọc cặp `eventType + schemaVersion` rồi chọn decoder/upcaster tương ứng. **Không** deserialze mọi payload bằng class v2 với giả định các field v2 luôn tồn tại; cần khai báo rõ cách chuyển những giá trị không có trong v1.

Trong Java trong cùng JVM, một phương án minh họa là dùng hai kiểu record và hai listener, rồi chuyển vào một service xử lý chung. Đây là chiến lược version **ở mức kiểu Java**; phần routing JSON/broker nếu có phải triển khai riêng.

## 6. Ví dụ Spring Framework Java 17+ có thể chạy được

Ví dụ này dùng **Spring Framework 6.2.13** với `spring-context`, không cần Spring Boot, database hoặc message broker. Mục đích là minh họa cách nhiều phiên bản event được lắng nghe bằng `@EventListener` và chuẩn hóa về một mô hình chung **mà không phát lại event mới gây trùng xử lý**.

### Cấu trúc project

```text
event-version-demo/
├── pom.xml
└── src/main/java/example/events/EventVersionDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-version-demo</artifactId>
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

### EventVersionDemo.java

```java
package example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventVersionDemo {

    // Hợp đồng v1: ở thời kỳ này hệ thống CHỈ hỗ trợ USD.
    public record OrderPlacedV1(String orderId, long amountMinorUnits) {
    }

    // Hợp đồng v2: currency và channel có mặt trong payload.
    public record OrderPlacedV2(
            String orderId,
            long amountMinorUnits,
            String currency,
            String channel) {
    }

    // Mô hình nội bộ nhất quán để phần xử lý không phải phân nhánh v1/v2.
    public record CanonicalOrderPlaced(
            String orderId,
            long amountMinorUnits,
            String currency,
            String channel) {
    }

    public static class OrderEventConsumer {

        @EventListener
        public void onV1(OrderPlacedV1 event) {
            CanonicalOrderPlaced converted = new CanonicalOrderPlaced(
                    event.orderId(),
                    event.amountMinorUnits(),
                    "USD",         // Mặc định hợp lệ theo hợp đồng v1.
                    "unknown");    // V1 không lưu kênh bán.

            process(converted, 1);
        }

        @EventListener
        public void onV2(OrderPlacedV2 event) {
            CanonicalOrderPlaced converted = new CanonicalOrderPlaced(
                    event.orderId(),
                    event.amountMinorUnits(),
                    event.currency(),
                    event.channel());

            process(converted, 2);
        }

        private void process(
                CanonicalOrderPlaced event, int sourceVersion) {

            System.out.printf(
                    "CONSUMED v%d id=%s amount=%d currency=%s channel=%s%n",
                    sourceVersion,
                    event.orderId(),
                    event.amountMinorUnits(),
                    event.currency(),
                    event.channel());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        OrderEventConsumer orderEventConsumer() {
            return new OrderEventConsumer();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(AppConfig.class);
            context.refresh();

            context.publishEvent(new OrderPlacedV1("ORD-101", 1250L));

            context.publishEvent(new OrderPlacedV2(
                    "ORD-102", 9900L, "USD", "mobile"));
        }
    }
}
```

### Biên dịch và chạy

Yêu cầu Java 17+, Maven 3.9+ và kết nối tải dependency Maven lần đầu:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.events.EventVersionDemo
```

Các dòng do chính code in ra, theo đúng thứ tự:

```text
CONSUMED v1 id=ORD-101 amount=1250 currency=USD channel=unknown
CONSUMED v2 id=ORD-102 amount=9900 currency=USD channel=mobile
```

**Giải thích:**

1. `AnnotationConfigApplicationContext` được tạo và `refresh()` trước khi phát event; Spring đăng ký bean `OrderEventConsumer` cùng hai phương thức `@EventListener`.
2. Khi publish `OrderPlacedV1`, chỉ listener `onV1(...)` có kiểu phù hợp. Nó chuyển v1 thành `CanonicalOrderPlaced` với USD dựa vào **hợp đồng giả định được ghi rõ**, còn channel là `unknown`.
3. Khi publish `OrderPlacedV2`, chỉ `onV2(...)` phù hợp và giữ nguyên các giá trị có trong v2.
4. `process(...)` xử lý cùng một dạng dữ liệu chuẩn; nó không cần biết cấu trúc v1/v2 ngoài tham số nguồn dùng để quan sát.
5. Mặc định `ApplicationEventPublisher` với `SimpleApplicationEventMulticaster` của context này gọi listener **đồng bộ**, nên hai dòng xuất hiện theo thứ tự hai lần `publishEvent(...)`.

**Giới hạn ví dụ:** Nó không truyền JSON, không dùng serialization, không có queue/retry/broker. Khác nhau giữa `OrderPlacedV1` và `OrderPlacedV2` được Spring chọn theo **kiểu class tại runtime**, không phải bằng cách Spring tự đọc `schemaVersion` từ metadata. Nếu dùng outbox, message broker hoặc event store, phải bổ sung serializer, deserializer và version router/upcaster có kiểm thử.

## 7. Chọn chiến lược evolution cho payload

Có ba hướng phổ biến. Không phải hệ thống nào cũng cần nhiều class event:

### Hướng A — Phát triển cùng một schema theo quy tắc tương thích

Duy trì một event type `order.placed`, bổ sung field tùy chọn, default và cơ chế bỏ qua field lạ nếu quy tắc serializer cho phép. Consumer mới có thể đọc payload cũ; producer có thể được triển khai tuần tự mà không bắt buộc mọi consumer thay đổi cùng một lúc.

Ưu điểm: ít version class và ít nhánh chuyển đổi. Điều kiện: các thay đổi thật sự tương thích cả về dữ liệu lẫn nghiệp vụ. Cần schema/contract test, không suy luận chỉ từ tên field.

### Hướng B — Phiên bản payload riêng

Khi thay đổi phá hợp đồng, có thể phát `order.placed` với `schemaVersion=2` hoặc định danh rõ là `order.placed.v2`. Consumer có router lựa chọn decoder theo version, rồi chuyển lên canonical model. Giữ đường đọc v1 chừng nào còn event lịch sử hoặc producer cũ.

Ưu điểm: rõ ràng, có thể replay dữ liệu cũ. Đổi lại tăng logic chuyển đổi, tài liệu và thử nghiệm. Nên phân định khi nào một version không còn được đọc hoặc được phép xóa.

### Hướng C — Tạo một event nghiệp vụ mới

Nếu đổi **ý nghĩa sự thật**, chỉ tăng schemaVersion có thể không đủ. Ví dụ `OrderPlaced` là lúc khách xác nhận đặt hàng, nhưng sự kiện mới cần thông báo lúc hệ thống chấp nhận rủi ro và quyết định xử lý; đó có thể là `OrderAccepted`, một event **khác về nghiệp vụ**.

Tên event nên phản ánh điều đã xảy ra. Không để `OrderPlaced/v2` âm thầm đổi thời điểm phát từ "đã gửi yêu cầu" thành "đã thanh toán" vì consumer cũ sẽ có thể hiểu sai mà không phát sinh lỗi cú pháp.

## 8. Upcasting: đọc dữ liệu cũ theo mô hình hiện tại

Với event store hoặc outbox giữ payload nhiều năm, có thể xây một **upcaster** để chuyển event v1 → v2 rồi v2 → v3 trước khi đưa cho domain/application handler:

```text
Persisted event (type + version + payload)
                |
                v
Version router / deserializer
                |
        +-------+-------+
        |               |
        v               v
       v1              v2
        |               |
        v               |
  upcast v1->v2         |
        +-------+-------+
                |
                v
       Canonical handler
```

Mảnh pseudocode dưới đây minh họa một converter cho **mô hình đã deserialize**, không phải chương trình độc lập:

```java
CanonicalOrderPlaced upgrade(OrderPlacedV1 oldEvent) {
    return new CanonicalOrderPlaced(
            oldEvent.orderId(),
            oldEvent.amountMinorUnits(),
            "USD",      // Chỉ hợp lệ nếu contract v1 bảo đảm.
            "unknown"); // Không thể suy ra kênh bán.
}
```

Các quy tắc thiết kế upcaster:

- **Thuần và xác định:** cùng một event cũ cho cùng kết quả; tránh đọc dữ liệu mutable hoặc gọi dịch vụ ngoài để đoán giá trị.
- **Không làm mất sự thật:** giữ định danh, thời điểm xảy ra, giá trị gốc và ngữ nghĩa; không đổi `amountMinorUnits` thành dữ liệu khác.
- **Không tái phát domain event ngoài ý muốn:** chuyển đổi dạng đọc chỉ chuẩn bị dữ liệu, không phải một hành động nghiệp vụ mới.
- **Version không được hỗ trợ phải báo rõ:** không được deserialize nhầm v99 thành v2 rồi bỏ qua field bắt buộc.
- **Có fixture lịch sử:** lưu các mẫu dữ liệu thật đã được khử nhạy cảm, kiểm thử việc replay khi code thay đổi.

Upcasting thường phù hợp **lúc đọc** thay vì âm thầm sửa toàn bộ event lịch sử. Nếu yêu cầu migration lưu trữ, phải có kế hoạch sao lưu, audit, kiểm thử tương thích và cơ chế khôi phục riêng.

### Event sourcing khác event notification

Trong **event sourcing**, event history có thể là nguồn sự thật để dựng lại trạng thái aggregate. Khi đó compatibility của dữ liệu cũ ảnh hưởng trực tiếp khả năng replay. Với **event notification** thông thường của Spring Application Events, event có thể chỉ tồn tại trong bộ nhớ; không có cơ chế replay lịch sử mặc định. Không áp đặt toàn bộ kiến trúc event sourcing chỉ vì ứng dụng gọi `publishEvent(...)`.

## 9. Tương thích khi nâng cấp nhiều producer và consumer

Một kế hoạch triển khai version mới nên xem xét cả producer lẫn consumer và khả năng chạy song song các phiên bản trong môi trường thực.

**Ví dụ nâng cấp v1 → v2:**

1. Công bố hợp đồng v2: định nghĩa field, kiểu, đơn vị đo, mandatory/optional, default và ví dụ dữ liệu.
2. Nâng consumer trước nếu bắt buộc consumer mới phải hiểu cả v1 và v2. Tạo adapter/upcaster và contract test.
3. Kiểm thử consumer mới xử lý event v1 thật, kể cả thiếu field mới và có trạng thái hiếm.
4. Nâng producer để phát v2 khi các consumer liên quan đã hỗ trợ.
5. Quan sát số lượng event theo `eventType/schemaVersion`, lỗi deserialize, lỗi xử lý và độ trễ.
6. Ngừng phát v1 khi mọi producer đã nâng cấp; **chỉ** ngừng hỗ trợ đọc v1 khi đã xử lý retention, replay và consumer còn dùng phiên bản cũ.

Trong trường hợp không kiểm soát được tất cả consumer, có thể cần giai đoạn chuyển tiếp, kênh/stream version hóa hoặc adapter ở biên. **Dual-publish** v1 và v2 là lựa chọn có rủi ro: consumer đăng ký cả hai có thể thực hiện nghiệp vụ hai lần. Nếu dùng, phải có correlation hoặc business-event ID chung và deduplication, kèm quy tắc định tuyến rõ.

**Không chọn deployment order mù quáng:** tương thích ngược/xuôi và định dạng schema thực tế quyết định producer hay consumer có thể nâng trước. Một số registry hỗ trợ `BACKWARD`, `FORWARD`, `FULL`, các biến thể `TRANSITIVE`, nhưng các chế độ này không áp dụng tự động cho một record Java được publish trong Spring context.

## 10. Version, eventId, thứ tự và xử lý trùng

Version không thay thế những metadata vận hành khác:

- **`eventId`:** xác định một lần xảy ra duy nhất, hỗ trợ dedup khi retry hoặc broker giao lại.
- **`aggregateId`:** nhóm các event cùng đối tượng nghiệp vụ.
- **`aggregateVersion` hoặc sequence:** có thể hỗ trợ phát hiện event thiếu/thứ tự và optimistic locking, tùy thiết kế storage.
- **`schemaVersion`:** diễn giải payload; không dùng để sắp thứ tự event nghiệp vụ.
- **`occurredAt`:** timestamp thông tin; không tự bảo đảm thứ tự tuyệt đối giữa nhiều máy.

Ví dụ, hai event của cùng aggregate đều có `schemaVersion=2` nhưng `aggregateVersion=17` và `aggregateVersion=18`. Hai bản sao của **cùng một event** có thể được giao hai lần với **cùng `eventId`**, không phải hai lần chuyển trạng thái.

Nếu khi migration bạn phát đồng thời hai biểu diễn v1/v2 của **cùng một sự thật**, chúng nên có liên hệ qua business occurrence ID/correlation để người nhận biết đó không phải hai đơn hàng được đặt khác nhau. Cách dùng `eventId` chung hay ID khác nhau tùy hợp đồng; phải định nghĩa trước, không thay đổi ngầm khi chuyển đổi.

## 11. Kiểm thử contract và replay

Kiểm thử unit class Java chỉ đủ khi event thuần in-memory. Đối với payload serialize, cần kiểm thử **bytes/JSON/Avro/Protobuf thực** mà consumer nhận.

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Consumer v2 nhận payload v1 | Đọc thành công hoặc bị từ chối có chủ đích với lỗi rõ; không sai nghiệp vụ âm thầm |
| Consumer v1 nhận payload v2 | Chỉ thành công nếu quy tắc forward compatibility cho phép |
| Event v1 không có `currency` | Dùng default USD **chỉ khi v1 bảo đảm USD** |
| Event v2 thiếu trường bắt buộc | Fail validation hoặc đưa vào luồng lỗi rõ, không bỏ qua lặng lẽ |
| Payload chứa field không biết | Hành vi đúng theo hợp đồng (ignore hoặc reject) |
| Producer thay tên/kiểu của field | Contract test phát hiện breaking change |
| Một event cũ được replay nhiều lần | Upcaster deterministic, side effect idempotent |
| Một eventId được giao lặp | Consumer chống tạo tác dụng phụ hai lần theo quy tắc |
| Gửi event có `schemaVersion` chưa hỗ trợ | Không xử lý như version khác; log/metric/quarantine phù hợp |
| Phát cả v1 và v2 trong giai đoạn chuyển tiếp | Không tự động xử lý cùng nghiệp vụ hai lần |

### Dữ liệu fixture

Lưu các payload phiên bản trước thành file fixture trong bộ test của ứng dụng, chẳng hạn:

```text
src/test/resources/events/order-placed-v1.json
src/test/resources/events/order-placed-v2.json
```

Mỗi fixture cần kiểm tra ít nhất: cú pháp hợp lệ, field bắt buộc, enum/đơn vị tiền, default, event type, schema version, và việc chuyển sang canonical model. Không chỉ tạo JSON test bằng serializer hiện tại: làm vậy dễ bỏ lỡ trường hợp dữ liệu **thực tế từ phiên bản cũ** khác dự đoán.

Nếu dùng schema registry, cấu hình policy tương thích theo từng subject/type và bổ sung test schema evolution trong CI. Registry có thể bắt lỗi kiểu/cấu trúc theo quy tắc, nhưng **không kiểm chứng được tất cả thay đổi ngữ nghĩa nghiệp vụ**; vẫn cần contract test và review.

## 12. Vấn đề riêng trong Spring Application Events

Spring Application Events thường dispatch một **đối tượng Java** trong cùng process. Khi thiết kế version cho loại event này:

1. `@EventListener` chọn listener chủ yếu theo **kiểu tham số event**. Nó không đọc một field tên `schemaVersion` để tự đổi class.
2. Một listener chỉ nhận `OrderPlacedV2` sẽ không tự nhận `OrderPlacedV1` nếu hai record không có quan hệ kiểu phù hợp. Cần một listener riêng hoặc một router cho các phiên bản.
3. `ApplicationEventPublisher.publishEvent(Object)` không cung cấp persistence, replay, schema registry hoặc transaction boundary theo mặc định.
4. Với `@Async`, consumer có thể chạy sau khi producer trả về; không giả định publication = processing thành công. Queue in-memory không thay thế outbox.
5. Khi sử dụng `@TransactionalEventListener`, phase transaction quyết định khi nào xử lý event, nhưng **không tự giải quyết versioning hoặc bảo đảm delivery sau crash**.
6. Nếu event type chỉ là một class Java nội bộ và không bao giờ được lưu/truyền xa, bạn có thể không cần field `schemaVersion`. Tuy nhiên, vẫn nên giữ định nghĩa payload rõ và tránh đổi ý nghĩa trường âm thầm.

**Thiết kế thường phù hợp:** Event domain nội bộ giữ đối tượng giàu ý nghĩa nhưng độc lập với chi tiết vận chuyển; adapter tại ranh giới integration chuyển nó thành envelope versioned, lưu outbox và gửi qua broker nếu cần. Điều này tránh trộn field hạ tầng vào mọi domain object.

## 13. Các lỗi phổ biến cần tránh

**Lỗi 1 — Tăng schemaVersion theo mỗi release.** Chỉ tăng khi hợp đồng dữ liệu cần phân biệt phiên bản; một release có thể không thay schema, nhiều release có thể cùng đọc các version cũ.

**Lỗi 2 — Cho rằng field mới luôn tương thích.** Một consumer có thể reject unknown fields; phải thử dữ liệu thật và chính sách parser.

**Lỗi 3 — Thay đổi đơn vị hoặc ý nghĩa field mà không đổi version.** Ví dụ `total=1000` từ "cent" thành "USD"; dữ liệu vẫn là number nhưng giá trị nghiệp vụ sai nghiêm trọng.

**Lỗi 4 — Đặt default bằng cách đoán.** Currency, tax và trạng thái xử lý phải dựa trên dữ liệu/hợp đồng lịch sử; nếu thiếu thông tin, phải công khai giới hạn.

**Lỗi 5 — Xóa decoder v1 ngay khi producer phát v2.** Outbox, broker retention, retry, dead-letter và replay có thể vẫn chứa event v1.

**Lỗi 6 — Sửa bản ghi event lịch sử tại chỗ mà không audit.** Việc sửa lại dữ liệu có thể phá tính bất biến và replay. Ưu tiên upcasting khi đọc hoặc migration có quy trình và kiểm chứng.

**Lỗi 7 — Coi tên class Java là wire contract.** Refactor package/class có thể là thay đổi code nội bộ; schema lưu trữ cần một `eventType` ổn định và mapping được kiểm soát.

**Lỗi 8 — Dual-publish mà không dedup.** Một nghiệp vụ có thể được xử lý hai lần. Dùng correlation/event ID và xác định consumer nào đang nghe kênh nào.

**Lỗi 9 — Dùng schemaVersion để sắp thứ tự event.** Sắp thứ tự theo aggregate sequence/offset và quy tắc của broker/storage khi cần, không theo version schema.

**Lỗi 10 — Bỏ qua bảo mật của schema cũ.** Payload có thể chứa dữ liệu nhạy cảm hoặc field đã bị loại bỏ vì chính sách riêng tư. Có retention, masking, migration và quyền truy cập phù hợp cho dữ liệu lưu bền.

## 14. Checklist thiết kế payload versioned

Trước khi công bố event mới hoặc thay đổi payload, xác nhận:

1. Tên event mô tả **một sự thật nghiệp vụ** nhất quán qua các phiên bản không?
2. Có phân biệt `eventType`, `schemaVersion`, `eventId` và `aggregateVersion` không?
3. Field và kiểu có hợp đồng rõ: ý nghĩa, đơn vị, required/optional, giá trị null, default?
4. Consumer mới có đọc được event cũ cần replay không?
5. Consumer cũ có hành vi được kiểm chứng khi nhận payload mới không?
6. Những thay đổi breaking có router/upcaster hoặc event type mới không?
7. Producer/consumer có kế hoạch triển khai, giám sát và rollback không?
8. Dual-publish/retry có nguy cơ xử lý trùng không, và đã có dedup chưa?
9. Đã kiểm thử fixture lịch sử thay vì chỉ serialize/deserialze bằng cùng một version chưa?
10. Nếu có lưu bền, đã xác định retention, schema registry, replay và chính sách bảo vệ dữ liệu cũ chưa?

**Ghi nhớ:** Version hóa event là quản lý **hợp đồng dữ liệu và ngữ nghĩa** giữa producer, consumer và các thông điệp quá khứ. Spring Application Events chỉ giúp phát/nhận đối tượng trong ứng dụng; hệ thống phải tự thiết kế khả năng tương thích, chuyển đổi phiên bản và bảo đảm xử lý khi dữ liệu đi ra ngoài tiến trình.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): cách publish event và dùng `@EventListener`.
- [Spring Framework — EventListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html): đăng ký listener theo kiểu event.
- [Confluent — Schema Compatibility](https://developer.confluent.io/patterns/event-stream/schema-compatibility/): khái niệm tương thích ngược và xuôi của schema.
- [Confluent — Schema Evolution](https://developer.confluent.io/patterns/event-stream/schema-evolution/): lựa chọn tiến hóa cùng schema hoặc dùng stream/version riêng.
- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): các mode compatibility; chi tiết phụ thuộc Avro/Protobuf/JSON Schema và chính sách registry.
