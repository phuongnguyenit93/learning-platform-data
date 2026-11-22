# Event contract và khả năng tiến hóa trong Spring Framework Application Events

## 1. Event contract là gì và vì sao cần thiết kế để tiến hóa?

Trong Spring Framework, một ứng dụng có thể phát một đối tượng bằng `ApplicationEventPublisher.publishEvent(...)` và các bean đăng ký `@EventListener` sẽ nhận sự kiện tương ứng. Về mặt kỹ thuật, Java chỉ cần xác định kiểu đối tượng. Nhưng về mặt kiến trúc, **event contract** (hợp đồng sự kiện) còn trả lời những câu hỏi lâu dài hơn:

- **Điều gì đã xảy ra?** Ví dụ `OrderPlaced` nghĩa là một đơn hàng đã được tiếp nhận; đây là sự kiện mô tả *sự thật đã xảy ra*, không phải mệnh lệnh “hãy tạo đơn hàng”.
- **Khi nào điều đó đúng?** Sự kiện phát trước hay sau khi giao dịch lưu dữ liệu đã commit? Thời điểm phát event khác thời điểm business fact xảy ra.
- **Consumer có thể dựa vào trường nào?** Tên trường, kiểu, đơn vị đo, khả năng `null`, các giá trị hợp lệ và ý nghĩa nghiệp vụ.
- **Producer có bảo đảm gì?** Sự kiện có thể phát lại, gửi trùng, phát sai thứ tự hoặc bị mất không? Event nội bộ của Spring **không tự có** các bảo đảm của broker.
- **Làm sao thay đổi hợp đồng?** Thêm trường tùy chọn, đổi định dạng, giữ song song V1/V2 hay nâng cấp consumer mà không phá vỡ hệ thống cũ.

Một contract hữu ích phải mô tả đủ **cấu trúc + ngữ nghĩa + quy tắc phát + kỳ vọng xử lý**. Chỉ có Java record hoặc JSON Schema mà không ghi rõ đơn vị tiền, thời điểm hoặc điều kiện phát là chưa đầy đủ.

Ví dụ, contract của sự kiện đặt đơn có thể nói:

> `OrderPlaced` là sự kiện bất biến được tạo một lần cho mỗi lần đặt đơn được hệ thống chấp nhận; `orderId` là mã đơn ổn định; `totalMinorUnits` là tổng tiền tính theo đơn vị nhỏ nhất của `currency`; `eventId` định danh lần phát sinh sự kiện nghiệp vụ. Consumer phải chịu được khả năng một bản tin được xử lý lại trong kiến trúc có cơ chế retry.

Nếu V1 chỉ có `totalMinorUnits` mà không có `currency`, consumer sẽ phải dựa vào một quy tắc đã thỏa thuận (ví dụ hệ thống V1 chỉ nhận VND). Khi xuất hiện thanh toán nhiều loại tiền, contract cần tiến hóa thay vì ngầm đoán rằng con số cũ vẫn mang cùng ý nghĩa.

## 2. Sự kiện nghiệp vụ, thông điệp và payload

Trong thiết kế Spring Application Events, cần phân biệt ba lớp:

| Lớp | Vai trò | Ví dụ |
| --- | --- | --- |
| **Business event** | Sự thật đã xảy ra trong miền nghiệp vụ, có tên và ý nghĩa ổn định. | “Đơn hàng ORD-7 đã được đặt”. |
| **Payload/contract** | Dữ liệu mà producer công bố cho consumer. | `orderId`, `eventId`, `amountMinorUnits`, `currency`. |
| **Envelope/transport metadata** | Thông tin hỗ trợ truyền, theo dõi, phân luồng và giải mã. | `eventType`, `schemaVersion`, `occurredAt`, `correlationId`. |

Trong **Spring Application Events nội bộ**, payload có thể là **bất kỳ đối tượng Java nào**, không cần kế thừa `ApplicationEvent`. Spring bọc nó thành `PayloadApplicationEvent` rồi chuyển đến các listener phù hợp.

~~~java
public record OrderPlaced(String eventId, String orderId) {}

@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Nhận payload OrderPlaced do Spring phát.
}
~~~

*Đoạn code minh họa đặt trong bean Spring và cần các import phù hợp; ví dụ chạy hoàn chỉnh nằm ở phần 6.*

Khi sự kiện đi qua một **message broker** hoặc được lưu thành JSON/Avro/Protobuf, nó còn có một **wire contract**: định dạng, tên topic, schema, chiến lược tương thích serializer/deserializer. Spring `publishEvent(Object)` **không tự cung cấp** JSON schema registry, version negotiation hay serialization cho event nội bộ. Đừng nhầm việc Java biên dịch được với việc mọi consumer đã tương thích.

## 3. Nguyên tắc thiết kế payload dễ tiến hóa

### 3.1. Đặt tên theo sự thật nghiệp vụ

Ưu tiên những tên mô tả trạng thái đã xảy ra:

- `OrderPlaced`, `PaymentCaptured`, `InventoryReserved`.
- Tránh dùng `HandleOrder`, `SendEmail` hoặc `UpdateCache` nếu đây thực chất là **command** chứ không phải sự kiện.
- Không dùng một tên quá chung như `DataChangedEvent` rồi yêu cầu consumer phân tích một bản đồ tùy ý để biết hành động thật sự.

Tên phải có **ranh giới ngữ nghĩa**: `OrderPlaced` khác `OrderPaid` và khác `OrderShipped`. Nếu điều kiện tạo sự kiện thay đổi từ “đã đặt đơn” sang “đã thanh toán”, đó là thay đổi ý nghĩa phá vỡ contract dù tên lớp và tất cả các trường vẫn giữ nguyên.

### 3.2. Công bố dữ liệu cần thiết, không công bố toàn bộ entity

Không nên đặt trực tiếp `@Entity OrderEntity`, `EntityManager` hoặc các đối tượng lazy proxy trong event công bố cho nhiều listener:

~~~java
// Không khuyến nghị cho contract ổn định:
public record OrderPlaced(OrderEntity entity) {}
~~~

*Đoạn trên chỉ minh họa anti-pattern; `OrderEntity` là kiểu JPA giả định.*

Những rủi ro gồm thay đổi JPA model làm thay đổi hợp đồng ngầm, đối tượng bị sửa sau khi event phát, `LazyInitializationException` trong xử lý async và vô tình lộ dữ liệu nhạy cảm. Payload có thể sử dụng các giá trị bất biến như ID, số tiền, currency, trạng thái cần thiết; khi cần dữ liệu mới nhất, consumer tự truy vấn theo ID trong transaction phù hợp.

**Chọn snapshot hay reference theo nhu cầu:**

- **Reference event:** chứa `orderId`, consumer tải trạng thái hiện tại từ database. Phù hợp khi consumer cần bản mới nhất, nhưng có race condition hoặc không còn thấy trạng thái lịch sử của thời điểm event.
- **Snapshot event:** chứa các giá trị nghiệp vụ tại thời điểm phát. Phù hợp cho tính toán hoặc audit cần dữ liệu lịch sử, nhưng payload lớn và yêu cầu version contract chặt chẽ hơn.
- Có thể kết hợp ID + một số trường snapshot quan trọng. Tránh “đổ” toàn bộ entity graph nếu không có nhu cầu rõ.

### 3.3. Ưu tiên bất biến, có ràng buộc rõ ràng

Java 17 `record` là lựa chọn thuận tiện cho **payload dữ liệu nông và ít thay đổi**:

~~~java
public record PaymentCaptured(
        String eventId,
        String paymentId,
        long amountMinorUnits,
        String currency) {}
~~~

Record có các trường `final`, nhưng **không bảo đảm bất biến sâu** nếu trường là danh sách, map hoặc đối tượng có thể sửa. Khi chứa collection, cần sao chép phòng vệ và ưu tiên dữ liệu bất biến:

~~~java
public record OrderLines(List<String> skuIds) {
    public OrderLines {
        skuIds = List.copyOf(skuIds);
    }
}
~~~

*Đoạn minh họa cần import `java.util.List`.*

Đối với contract quan trọng, ràng buộc nên được ghi rõ và kiểm tra:

- ID không trống và ổn định trong phạm vi hệ thống.
- `amountMinorUnits` là số nguyên chính xác, không dùng `double` cho tiền.
- `currency` theo mã chuẩn như ISO 4217; đơn vị minor phải được thống nhất cho từng loại tiền.
- Thời điểm `occurredAt` dùng `Instant`/UTC khi có thể, không dựa vào múi giờ mặc định của máy.
- Giá trị mới có thể là `null`/vắng mặt chỉ khi schema và consumer chấp nhận; phân biệt “chưa biết” và “không áp dụng”.
- Trường dữ liệu cá nhân phải tuân thủ nguyên tắc tối thiểu hóa, che/mã hóa theo yêu cầu.

**Không nên đổi ý nghĩa trường mà không đổi tên hoặc version.** Chẳng hạn `amount` từ đơn vị đồng sang xu, hoặc `createdAt` từ giờ UTC sang giờ địa phương, là thay đổi phá vỡ contract ngay cả khi cả hai vẫn mang kiểu `long`/`String`.

## 4. Hợp đồng sự kiện nên ghi lại những gì?

Một tài liệu contract thực tế tối thiểu nên có:

| Phần contract | Câu hỏi cần trả lời |
| --- | --- |
| Tên và định danh | Event là gì, namespace nào sở hữu, ai là producer? |
| Định nghĩa nghiệp vụ | Sự kiện khẳng định điều gì đã hoàn tất? Điều kiện phát chính xác là gì? |
| Schema | Trường nào bắt buộc, tùy chọn, kiểu dữ liệu, giới hạn, default và ví dụ hợp lệ? |
| Version | Phiên bản hiện tại, thay đổi so với phiên bản trước, chính sách hết hỗ trợ? |
| Thời gian | `occurredAt`, `publishedAt` nếu có khác nhau thế nào? |
| Định danh | `eventId` cho lần phát sinh nghiệp vụ; `aggregateId`/`orderId` cho thực thể. |
| Trình tự/độ trễ | Có bảo đảm thứ tự theo aggregate? Consumer có thể nhận lại không? |
| Giao dịch | Phát trong hay sau commit; khi rollback thì có được nhận không? |
| Bảo mật | Trường nhạy cảm nào bị cấm, thời gian lưu và quyền truy cập ra sao? |
| Kiểm thử/vận hành | Ai xác minh tương thích, rollout theo thứ tự nào, metric nào theo dõi lỗi? |

**Ví dụ bảng contract V2** cho event `OrderPlaced`:

| Trường | Kiểu | Bắt buộc? | Ý nghĩa |
| --- | --- | --- | --- |
| `eventId` | String | Có | ID ổn định của occurrence; dùng hỗ trợ idempotency. |
| `orderId` | String | Có | ID của đơn được đặt, không phải ID của event. |
| `amountMinorUnits` | long | Có | Tổng tiền theo đơn vị nhỏ nhất của currency tương ứng. |
| `currency` | String | Có ở V2 | Mã tiền tệ; V1 không có nên áp dụng quy ước legacy **chỉ khi đã xác thực**. |

Một bản tin cùng `orderId` có thể đại diện các sự kiện khác nhau (`OrderPlaced`, `OrderPaid`, `OrderCancelled`). Vì vậy **không dùng `orderId` thay hoàn toàn `eventId` để khử trùng**; nếu nghiệp vụ có nhiều occurrence cùng loại trên một aggregate, cần khóa dedup phù hợp.

## 5. Compatibility: thay đổi nào an toàn, thay đổi nào cần version mới?

“Backward-compatible” và “forward-compatible” luôn phụ thuộc vào **bên đọc**, **schema format** và **quy tắc parser/serializer**:

- **Backward compatibility:** consumer *mới* có thể đọc event được producer *cũ* phát.
- **Forward compatibility:** consumer *cũ* có thể đọc event do producer *mới* phát.
- **Full compatibility:** thỏa cả hai chiều, trong phạm vi các chính sách đã cam kết.

Một thay đổi được coi là “bổ sung” chưa chắc tương thích trong mọi hệ thống. Ví dụ JSON parser có thể bỏ qua trường lạ, nhưng một deserializer strict sẽ từ chối; thêm field có default vào Java record thay đổi constructor Java, nên các call site cũ có thể không biên dịch.

| Thay đổi | Đánh giá thường gặp | Cách giảm rủi ro |
| --- | --- | --- |
| Thêm trường **tùy chọn**, consumer cũ chấp nhận trường lạ | Thường tương thích với wire schema cho phép unknown fields. | Chỉ thêm khi đã kiểm tra parser, default và nullable behavior. |
| Thêm trường **bắt buộc** mà event cũ không có | Dễ phá vỡ backward compatibility. | Dùng default đáng tin hoặc version mới; không đoán dữ liệu lịch sử. |
| Xóa trường consumer cũ cần | Phá vỡ forward compatibility. | Giữ trường trong giai đoạn chuyển tiếp; có thời hạn deprecate rõ. |
| Đổi tên trường | Thường phá vỡ nếu consumer đọc theo tên. | Cho phép alias/mapping hoặc duy trì V1 song song V2. |
| Đổi `long` sang `String` hoặc đổi cấu trúc nested | Có thể phá vỡ parser/code/semantic. | Version mới và bộ chuyển đổi có kiểm thử. |
| Thêm giá trị enum | Có thể phá vỡ consumer dùng `switch` exhaustive. | Consumer có nhánh unknown/fallback khi nghiệp vụ cho phép. |
| Đổi đơn vị tiền hoặc ý nghĩa một trạng thái | Phá vỡ **ngữ nghĩa** dù schema không đổi. | Contract/version mới, migration rõ ràng. |
| Đổi thứ tự trường trong positional format | Có thể phá vỡ consumer đọc theo vị trí. | Dùng field IDs/tên hoặc công cụ schema evolution phù hợp. |
| Nới/tăng giới hạn số hoặc kích thước chuỗi | Có thể làm consumer cũ tràn/không hợp lệ. | Kiểm thử giới hạn và cập nhật hợp đồng. |

Đừng dùng khẩu quyết “thêm trường luôn an toàn” hay “record mới là tự backward-compatible”. Trong **Java trong cùng codebase**, thay đổi chữ ký constructor, getter hoặc kiểu lớp có thể làm mã khác ngừng biên dịch. Trong **hệ thống truyền JSON**, hiệu quả phụ thuộc phiên bản schema và cấu hình deserialization. Trong **Avro/Protobuf**, phải tuân thủ quy tắc field default/field number/reserved field tương ứng, không áp dụng máy móc quy tắc của Java.

## 6. Ví dụ Java 17+ chạy được: giữ V1, giới thiệu V2 và chuẩn hóa tại consumer

Chúng ta có một ứng dụng Spring Framework 6.2.9 dùng event nội bộ:

- V1 chỉ mang `eventId`, `orderId`, `amountMinorUnits`. **Theo hợp đồng legacy giả định, toàn bộ V1 được ghi bằng VND**.
- V2 bổ sung `currency`, làm rõ ý nghĩa giá trị tiền.
- Một consumer duy nhất nhận cả hai version bằng **hai listener typed riêng**, rồi chuyển về một **mô hình xử lý nội bộ** thống nhất. Không cần phát thêm bản tin V2 mỗi khi nhận V1; tránh việc cùng nghiệp vụ chạy hai lần.

### 6.1. Cấu trúc dự án

~~~text
event-contract-demo/
├── pom.xml
└── src/main/java/EventContractDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-contract-demo</artifactId>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/EventContractDemo.java`:

~~~java
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventContractDemo {

    // Contract cũ: toàn bộ amountMinorUnits trong V1 là VND.
    public record OrderPlacedV1(
            String eventId,
            String orderId,
            long amountMinorUnits) {
    }

    // Contract mới: thêm đơn vị tiền tệ rõ ràng.
    public record OrderPlacedV2(
            String eventId,
            String orderId,
            long amountMinorUnits,
            String currency) {
    }

    // Mô hình riêng của consumer, không phải public event contract.
    public record CanonicalOrderPlaced(
            String eventId,
            String orderId,
            long amountMinorUnits,
            String currency) {

        public CanonicalOrderPlaced {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(orderId);
            Objects.requireNonNull(currency);
            if (eventId.isBlank() || orderId.isBlank()
                    || currency.isBlank() || amountMinorUnits < 0) {
                throw new IllegalArgumentException("Invalid order payload");
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Projection projection() {
            return new Projection();
        }
    }

    public static class Projection {

        @EventListener
        public void receiveV1(OrderPlacedV1 event) {
            // Quy tắc VND chỉ đúng vì contract V1 đã quy định như vậy.
            accept(new CanonicalOrderPlaced(
                    event.eventId(),
                    event.orderId(),
                    event.amountMinorUnits(),
                    "VND"));
        }

        @EventListener
        public void receiveV2(OrderPlacedV2 event) {
            accept(new CanonicalOrderPlaced(
                    event.eventId(),
                    event.orderId(),
                    event.amountMinorUnits(),
                    event.currency()));
        }

        private void accept(CanonicalOrderPlaced event) {
            System.out.println("Projection: " + event.eventId()
                    + " | " + event.orderId()
                    + " | " + event.amountMinorUnits()
                    + " " + event.currency());
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                Config.class)) {

            context.publishEvent(new OrderPlacedV1(
                    "evt-1", "ORD-7", 120_000));

            context.publishEvent(new OrderPlacedV2(
                    "evt-2", "ORD-8", 4_500, "USD"));
        }
    }
}
~~~

Từ thư mục có `pom.xml`, chạy với Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventContractDemo
~~~

Stdout do chương trình in ra, không kể log của Maven:

~~~text
Projection: evt-1 | ORD-7 | 120000 VND
Projection: evt-2 | ORD-8 | 4500 USD
~~~

### 6.2. Vì sao ví dụ chạy như vậy?

1. `AnnotationConfigApplicationContext` đăng ký bean `Projection` từ `Config`; phương thức có `@EventListener` được Spring phát hiện.
2. Khi `context.publishEvent(new OrderPlacedV1(...))` chạy, Spring bọc đối tượng record thành `PayloadApplicationEvent`. Chỉ listener phù hợp với kiểu payload V1 được gọi.
3. `receiveV1` dùng **quy tắc V1 đã xác định** để chuẩn hóa tiền tệ thành `VND`. Nếu dữ liệu legacy thực tế có nhiều loại tiền, quy tắc này **không hợp lệ**; phải tra cứu nguồn dữ liệu hoặc thiết kế migration khác.
4. V2 đã mang `currency`, nên `receiveV2` chuyển thẳng trường đó vào mô hình chuẩn hóa.
5. `accept(...)` xử lý cùng một cấu trúc cho cả hai version và in hai dòng. Mỗi occurrence trong ví dụ chỉ được phát **một version**, tránh xử lý trùng.
6. Spring mặc định dispatch event đồng bộ trên thread phát (nếu không cấu hình executor/`@Async`), nên hai dòng xuất hiện đúng thứ tự đã publish.

**Điểm cần nhớ:** tạo một bản record V2 khác lớp V1 **không tự động làm mọi listener V1 nhận V2**. Nếu một listener chỉ khai báo `onEvent(OrderPlacedV1)`, nó không tự nhận `OrderPlacedV2`. Cần adapter, listener hỗ trợ nhiều version hoặc cơ chế tương thích khác được thiết kế rõ ràng.

Ví dụ minh họa **cách thích nghi event type**, không phải giải pháp serialization đa hệ thống. Khi consumer nhận event từ broker, việc giải mã V1/V2 phải được xác định bởi `eventType`/`schemaVersion`, schema registry hoặc quy ước tương đương trước khi gọi logic chuẩn hóa.

## 7. Chiến lược tiến hóa contract: in-place, versioned event, upcaster

### 7.1. In-place additive evolution

Nếu thay đổi chỉ thêm dữ liệu tùy chọn với default có ý nghĩa, producer và consumer cùng kiểm soát được và serializer tương thích, có thể mở rộng schema đang tồn tại. Với JSON, ví dụ producer mới thêm trường `displayCurrency`, consumer cũ bỏ qua trường lạ **nếu được cấu hình như vậy**. Consumer mới phải chấp nhận event lịch sử không có trường đó.

Với Java record truyền trong cùng JVM, thay đổi khai báo record vẫn thay đổi kiểu/chữ ký constructor; cần kiểm tra lại mọi producer và consumer. **Tương thích wire schema không đồng nghĩa tương thích Java API**.

### 7.2. Tạo event V2 riêng

Khi thay đổi phá vỡ contract, ví dụ từ một giá tiền không có currency sang cơ chế đa tiền tệ, nên dùng type/version rõ ràng như `OrderPlacedV2`, hoặc sự kiện cùng tên nhưng envelope `schemaVersion=2` nếu hệ thống ngoài JVM dùng schema/version routing.

Ưu điểm: consumer cũ có thể tiếp tục nhận V1 trong giai đoạn chuyển tiếp; consumer mới triển khai V2. Nhược điểm: cần có chính sách thời hạn hỗ trợ, mapping, migration và xử lý version khi replay.

### 7.3. Upcaster / normalizer ở ranh giới

Một **upcaster** chuyển dữ liệu event cũ sang dạng mà consumer mới hiểu. Ví dụ:

~~~text
Persisted event V1
  |
  | decode / verify schema V1
  | upcast: legacy amount -> {amountMinorUnits, currency=VND}
  v
Canonical event model
  |
  +--> projection / reporting / application handler

Persisted event V2
  |
  | decode / verify schema V2
  v
Canonical event model
  |
  +--> projection / reporting / application handler
~~~

Bộ chuyển đổi phải **đúng ngữ nghĩa**, không được tự bịa giá trị. Nếu currency không thể suy ra từ contract V1, một upcaster gán mặc định `VND` sẽ gây sai lệch dữ liệu. Trong trường hợp đó cần enrichment từ nguồn đáng tin, xử lý thủ công, hoặc để consumer biểu diễn trạng thái `currency=UNKNOWN` khi nghiệp vụ cho phép.

Khi dữ liệu event được lưu bền vững, **mỗi version cần có cách decode và upcast rõ ràng**. Tránh giả định thay đổi tên class Java sẽ tự nâng cấp được các bản tin lưu trước đó.

## 8. Rollout V1 → V2 mà không làm vỡ consumer

Một lộ trình **expand → migrate → contract** thường an toàn hơn đổi producer và consumer cùng lúc:

1. **Khảo sát consumer đang chạy:** liệt kê ai nghe V1, ai lưu event, ai phụ thuộc tên trường hay giá trị enum. Ghi cả consumer ít hoạt động và job replay.
2. **Định nghĩa V2:** mô tả business fact, schema, ví dụ và quy tắc chuyển V1→V2; chốt tiêu chuẩn ID và thời gian.
3. **Mở rộng phía consumer:** triển khai consumer có thể đọc V1 + V2 hoặc adapter tập trung, nhưng chưa yêu cầu producer ngừng V1.
4. **Thêm contract tests:** kiểm tra consumer mới đọc được mẫu V1 đã lưu và mẫu V2; các trường bắt buộc/đơn vị tiền không đổi ngầm.
5. **Chuyển producer theo kế hoạch:** có thể chọn phát V2 cho consumer đã sẵn sàng. Với nhiều service độc lập, cân nhắc dual-publish trong thời gian ngắn **chỉ khi có quy tắc khử trùng**.
6. **Quan sát vận hành:** theo dõi số event/consumer theo version, lỗi decode, sự kiện trùng và tỷ lệ xử lý thất bại. Có khả năng rollback về V1 nếu cả hai vẫn được hỗ trợ.
7. **Ngừng V1 sau khi đã xác nhận:** mọi consumer/replay path đáp ứng V2, thời gian retention hết hoặc có upcaster cho lịch sử; sau đó mới loại bỏ mã hỗ trợ V1.

**Dual-publish nguy hiểm nếu cùng occurrence được phát thành V1 và V2 mà hai listener đều chạy nghiệp vụ.** Nếu bắt buộc phát hai bản cho cùng một sự thật, giữ cùng một `eventId` cho **cùng occurrence**, dùng cơ chế route/version-aware, và deduplicate ở nơi thực hiện side effect. Nếu `eventId` mới được tạo cho mỗi bản V1/V2, dedupe bằng ID đơn thuần sẽ không nhận ra chúng thuộc cùng một occurrence.

Ngược lại, **không tái sử dụng một eventId** cho hai sự kiện nghiệp vụ thực sự khác nhau; chẳng hạn đặt đơn và thanh toán đơn phải có định danh event riêng.

## 9. Event ID, idempotency, ordering và giao dịch

Khả năng tiến hóa chỉ an toàn khi xác định rõ **định danh và cách xử lý lặp**:

- **`eventId`:** ID cho occurrence; nếu một message được retry/replay, nên giữ cùng ID của occurrence gốc để dedup có ý nghĩa.
- **`aggregateId`/`orderId`:** nhóm nhiều sự kiện của cùng thực thể. Nó không đồng nghĩa event ID.
- **`occurredAt`:** thời điểm business fact xảy ra; có thể khác thời điểm message được publish/consume. Không dùng timestamp làm khóa dedup duy nhất.
- **`correlationId`:** kết nối nhiều thao tác của cùng luồng nghiệp vụ.
- **`causationId`:** chỉ ra event/command đã gây ra event mới khi hệ thống thực sự theo dõi causal chain.
- **`aggregateVersion`/sequence`:** có thể hữu ích khi phải kiểm tra thứ tự theo aggregate, nhưng chỉ chính xác nếu producer có quy tắc cấp số nhất quán.

**Idempotency** là consumer xử lý một occurrence lặp lại mà không tạo thêm tác dụng phụ không mong muốn. Ví dụ consumer ghi log xử lý theo khóa `(consumerName, eventId)` vào DB có unique constraint; khi đã xử lý, nó không tạo lại dòng audit hoặc gửi thêm tác vụ. Thực thi thật cần xét transaction và ranh giới side effect: kiểm tra “đã xử lý?” rồi mới ghi, nếu không đồng bộ, vẫn có race condition giữa nhiều worker.

### Spring Application Events không phải message broker

Mặc định Spring `ApplicationEventPublisher` chỉ bàn giao event cho multicaster trong **cùng application context/JVM**. Listener có thể chạy đồng bộ; có thể chuyển async nếu cấu hình. Không có sẵn:

- Persistence bền vững cho event.
- Acknowledgement/retry trên broker.
- Consumer offset, dead-letter queue, hoặc replay tự động.
- Đảm bảo once-only delivery giữa các service.
- Transaction atomic giữa commit DB và gửi một message ra mạng.

Nếu yêu cầu “đơn đã commit thì phải gửi message, không được mất”, hãy dùng mẫu phù hợp như **transactional outbox**: ghi bản ghi outbox **trong cùng transaction** với thay đổi nghiệp vụ, rồi một tiến trình riêng chuyển ra broker và retry. Event contract của bản ghi outbox có thể lưu `eventType`/`schemaVersion` để consumer decode và upcast khi cần.

### Publish trước/sau commit

Nếu một service gọi `publishEvent(...)` trong transaction thông thường, listener `@EventListener` đồng bộ có thể chạy **trước khi transaction commit**. Nếu business fact chỉ có hiệu lực sau commit, cân nhắc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` khi dùng transaction do Spring quản lý. Nhưng callback `AFTER_COMMIT` cũng **không tự bảo đảm phát lại** khi tiến trình chết sau commit và trước khi xử lý xong.

Không thay đổi định nghĩa contract `OrderPlaced` từ “đã gửi event” thành “đã commit” mà không xem lại cả producer lẫn consumer. Sự bảo đảm về pha giao dịch là **một phần của ngữ nghĩa event**.

## 10. Thiết kế envelope cho hệ thống ngoài JVM

Nếu event truyền qua API/broker, nên tách payload nghiệp vụ với metadata phục vụ giao tiếp. Ví dụ JSON minh họa một schema V2:

~~~json
{
  "eventId": "evt-2",
  "eventType": "sales.order.placed",
  "schemaVersion": 2,
  "aggregateId": "ORD-8",
  "occurredAt": "2026-01-15T08:12:00Z",
  "correlationId": "corr-25",
  "payload": {
    "orderId": "ORD-8",
    "amountMinorUnits": 4500,
    "currency": "USD"
  }
}
~~~

Những trường ở đây chỉ là **đề xuất thiết kế contract**, không phải định dạng Spring buộc mọi `ApplicationEvent` phải tuân thủ. `schemaVersion=2` có thể là số nguyên trong envelope, nhưng hệ thống cũng có thể dùng một event type riêng theo version như `sales.order.placed.v2`. Quan trọng là cách định tuyến và định nghĩa contract nhất quán, có thể kiểm thử.

### Version đặt ở đâu?

- **Tên event/class:** `OrderPlacedV1` và `OrderPlacedV2` trong JVM giúp compiler/lint phát hiện sự khác nhau về type.
- **Envelope `schemaVersion`:** phù hợp với message broker, event store, hoặc contract cần parse theo schema.
- **Schema registry:** có thể làm nơi quản lý compatibility policy và ID schema khi sử dụng Avro, JSON Schema hoặc Protobuf; không tự động giải quyết mọi thay đổi ý nghĩa nghiệp vụ.

Tránh mang cả version trong tên event và trong envelope mà không quy định chúng tương ứng thế nào. Nếu xảy ra `OrderPlacedV2` nhưng metadata `schemaVersion=1`, consumer có thể diễn giải sai.

## 11. Contract tests và quy trình kiểm thử tiến hóa

Chỉ thử “publish rồi listener được gọi” là chưa đủ cho event contract. Nên có nhiều lớp kiểm thử.

### 11.1. Kiểm thử nội dung và invariant

- V1 hợp lệ có ID, đơn hàng, amount theo đơn vị VND như hợp đồng.
- V2 hợp lệ có `currency` và amount đồng bộ.
- Amount âm, ID rỗng hoặc currency không hợp lệ bị từ chối theo quy tắc đã chốt.
- Những trường tùy chọn vắng mặt không làm consumer mới lỗi ngoài dự kiến.
- Trường nhạy cảm không vô tình xuất hiện trong payload.

### 11.2. Kiểm thử tương thích giữa các version

Ví dụ dữ liệu kiểm thử:

~~~json
{
  "eventId": "evt-old",
  "orderId": "ORD-1",
  "amountMinorUnits": 90000
}
~~~

Một consumer V2 phải có cách đọc/mapping V1 **nếu đó là cam kết backward compatibility**. Đồng thời có thể thử event V2 với một consumer cũ để chứng minh khả năng forward compatibility hoặc ghi rõ nó không được hỗ trợ.

Nếu có event store, nên giữ **fixture lịch sử** của V1, V2 trong test để phát hiện thay đổi parser/schema khiến replay thất bại. Nếu có consumer độc lập, xem xét consumer-driven contract tests hoặc kiểm thử compatibility theo schema registry.

### 11.3. Kiểm thử runtime trong Spring

Ví dụ ở phần 6 chứng minh hai overload listener V1/V2 được gọi theo kiểu payload. Với bài toán thật, cần test thêm:

- Đúng event type thì listener phù hợp được gọi; type khác không kích hoạt nhầm.
- Exception trong listener đồng bộ có thể ảnh hưởng đến publisher, trong khi `@Async` không tự truyền exception trở lại như một lời gọi thường.
- `@TransactionalEventListener(AFTER_COMMIT)` chỉ phản ứng khi transaction commit thành công theo hợp đồng đã định.
- Nếu dual-publish, consumer không thực hiện side effect hai lần cho cùng occurrence.
- Nếu có thêm event version mới, đường decode/upcast không làm mất các trường quan trọng.

Khi có async listener hoặc broker, **không assert thứ tự ngẫu nhiên của thread**; dùng test hook, await có timeout và điều kiện nghiệp vụ thay vì `Thread.sleep(...)` cố định.

## 12. Những lỗi thường gặp

1. **Đổi schema mà không đổi ngữ nghĩa/tài liệu contract.** Consumer cũ vẫn chạy nhưng tính sai. Ví dụ đổi `amountMinorUnits` thành đơn vị tiền nguyên rồi giữ nguyên tên.
2. **Công bố entity trực tiếp.** Thay đổi ORM model thành thay đổi contract ngầm, có thể mang theo dữ liệu nhạy cảm/lazy proxy.
3. **Cho rằng thêm field luôn backward-compatible.** Record constructor, strict JSON parser, validation và default có thể phá vỡ consumer.
4. **Dùng `null` làm default tùy tiện.** Consumer không rõ thiếu dữ liệu, chưa biết hay không áp dụng; cần định nghĩa cụ thể.
5. **Thay enum mà không có chiến lược unknown.** Consumer cũ có thể throw hoặc chạy sai nhánh.
6. **Nhân đôi version mà không có idempotency.** Cùng một occurrence được xử lý hai lần, dẫn đến duplicate email/audit hoặc thay đổi dữ liệu hai lần.
7. **Đặt toàn bộ business logic vào upcaster.** Upcaster nên chuyển đổi định dạng có quy tắc rõ; không bịa trạng thái hiện tại hay tạo side effect.
8. **Không hỗ trợ replay dữ liệu cũ.** Producer mới vẫn chạy nhưng job tái dựng projection không thể đọc sự kiện lịch sử.
9. **Lạm dụng generic “Event<T>”.** Một event có type parameter chưa chắc giữ được type khi chạy do Java type erasure; cần concrete subtype hoặc `ResolvableTypeProvider` theo cơ chế Spring nếu routing theo generic type.
10. **Không có owner và lịch ngừng version.** V1 sống mãi, consumer mới không biết có được bỏ adapter hay không.
11. **Nhầm event trong JVM với contract wire.** `ApplicationEventPublisher` không tự lưu JSON schema hoặc gửi qua broker.
12. **Tin rằng event phát sau commit là không mất được.** Callback nội bộ không có durable delivery; dùng transactional outbox và retry nếu nghiệp vụ bắt buộc.

## 13. Tự kiểm tra

**Câu 1.** Vì sao thay đổi tên trường `orderId` thành `id` có thể phá vỡ hợp đồng dù cả hai cùng mang String?

**Đáp án:** Consumer có thể phụ thuộc vào tên trường trong JSON, getter, constructor hoặc schema. Đổi tên mà không có alias/migration sẽ khiến consumer không đọc được dữ liệu hoặc diễn giải sai.

**Câu 2.** Một producer mới thêm `currency` vào record V1 và đổi constructor từ ba tham số thành bốn tham số. Đây có tự động là thay đổi tương thích không?

**Đáp án:** Không. Các Java call site cũ có thể không biên dịch. Nếu truyền qua broker, tính tương thích còn phụ thuộc schema và cấu hình parser; cần kiểm thử hoặc tạo V2 riêng.

**Câu 3.** Vì sao ví dụ dùng hai listener `receiveV1` và `receiveV2` thay vì ép mọi listener V1 tự nhận V2?

**Đáp án:** Hai lớp event là hai type Java khác nhau. Spring phân phát event dựa vào kiểu listener đã khai báo. Adapter rõ ràng giúp chuẩn hóa cả hai version mà không âm thầm giả định tương thích.

**Câu 4.** Khi nào việc đặt `currency="VND"` cho V1 là hợp lệ?

**Đáp án:** Chỉ khi business contract V1 bảo đảm tất cả amount đều là VND. Nếu không có bảo đảm đó, default này có thể làm sai dữ liệu và phải được thay bằng quy trình migration khác.

**Câu 5.** Nếu phát cả V1 và V2 cho cùng một lần đặt đơn, vì sao consumer có thể gặp sự cố?

**Đáp án:** Cùng occurrence xuất hiện dưới hai bản biểu diễn. Nếu cả hai đường đều thực hiện side effect mà không dedup/route đúng, sẽ xử lý lặp. Cần cơ chế phát song song và idempotency rõ.

**Câu 6.** Vì sao `eventId` không nên thay bằng mỗi `orderId`?

**Đáp án:** Một đơn có nhiều occurrence/event khác nhau. `orderId` định danh aggregate, còn `eventId` định danh một lần phát sinh sự kiện để hỗ trợ truy vết và dedup.

**Câu 7.** Spring `publishEvent(...)` có bảo đảm durable replay sau khi JVM tắt không?

**Đáp án:** Không. Đây là cơ chế phát event trong ứng dụng; bảo đảm lưu bền vững, broker delivery và replay phải do thiết kế bổ sung cung cấp.

## Tài liệu tham khảo

- [Spring Framework Reference — ApplicationContext: Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`, payload objects, generic events và cơ chế multicaster.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): `publishEvent(Object)`, `PayloadApplicationEvent` và giới hạn việc bàn giao event.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): cách gắn listener vào các pha giao dịch với `@TransactionalEventListener`.
- [Spring Framework Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html): listener theo type, điều kiện lọc và khả năng nhận nhiều event type.
- [Martin Fowler — Event-Driven Architecture](https://martinfowler.com/articles/201701-event-driven.html): phân biệt các phong cách sử dụng sự kiện và những hệ quả về liên kết giữa hệ thống.
