# Phân biệt event gốc và event dẫn xuất trong Spring Framework Application Events

## 1. Vì sao cần phân biệt hai loại event?

Một hành động nghiệp vụ có thể mở đầu cả **chuỗi sự kiện**. Ví dụ, sau khi đơn hàng được chấp nhận, ứng dụng cần yêu cầu giữ tồn kho, gửi email xác nhận và cập nhật một read model. Nếu chỉ quan sát log có nhiều event, rất khó biết:

- Event nào biểu diễn **sự việc nghiệp vụ khởi đầu**?
- Event nào được **tạo ra trong quá trình xử lý** một event trước đó?
- Hai event khác loại có cùng thuộc một yêu cầu/workflow không?
- Khi replay một event cũ, có nên **tạo lại các event dẫn xuất** hay chỉ cập nhật read model?
- Nếu listener nhận trùng, làm sao không gửi email hay trừ tồn kho hai lần?

Ta gọi:

**Event gốc (root/original event)** là sự kiện được chọn làm điểm bắt đầu cho một chuỗi xử lý đang xét, ví dụ `OrderAccepted` do dịch vụ nghiệp vụ phát khi đơn được chấp nhận. Nó ghi lại một sự thật hoặc thay đổi có ý nghĩa độc lập.

**Event dẫn xuất (derived/follow-up event)** là sự kiện được tạo ra **vì một event trước đó được xử lý**, ví dụ `InventoryReservationRequested` phát khi listener nhận `OrderAccepted` và quyết định yêu cầu giữ tồn kho.

Cách phân biệt **không phải hai class có sẵn trong Spring**: Spring không có một nhãn chung “root event” và “derived event” tự động gắn cho tất cả event. Đây là **ngữ nghĩa do ứng dụng thiết kế**. Một event có thể là event dẫn xuất trong một chuỗi lớn nhưng lại là điểm bắt đầu của một nhánh phân tích nhỏ hơn.

> **Ghi nhớ:** “gốc/dẫn xuất” mô tả **quan hệ nhân quả và nguồn gốc nghiệp vụ**, không mô tả ưu tiên chạy, kiểu Java bắt buộc, hay việc event đó là đồng bộ hay bất đồng bộ.

## 2. Ví dụ dễ hình dung: một event gốc, hai nhánh dẫn xuất

Giả sử ứng dụng đã xác nhận đơn hàng `ORD-42`:

```text
OrderAccepted
  eventId = evt-100
  correlationId = flow-7
  causationId = null
         |
         | listener xử lý OrderAccepted
         |
         +----> InventoryReservationRequested
         |        eventId = evt-101
         |        correlationId = flow-7
         |        causationId = evt-100
         |
         +----> ConfirmationEmailRequested
                  eventId = evt-102
                  correlationId = flow-7
                  causationId = evt-100
```

- `OrderAccepted` là **event gốc của chuỗi** đang xét.
- `InventoryReservationRequested` và `ConfirmationEmailRequested` là **hai event dẫn xuất trực tiếp**, có **hai ID riêng**.
- Cả ba cùng `correlationId = flow-7`, vì thuộc cùng một workflow.
- Mỗi event dẫn xuất mang `causationId = evt-100`, chỉ rõ **event trực tiếp gây ra nó**.
- Không có chuyện event dẫn xuất đương nhiên đã thành công: hậu tố `Requested` biểu thị **yêu cầu thực hiện**. Chỉ khi giữ tồn kho hoặc gửi email thành công mới được phát một event sự thật tương ứng như `InventoryReserved` hoặc `ConfirmationEmailSent`.

Nếu xử lý `InventoryReservationRequested` dẫn tới `InventoryReserved`, event mới sẽ có `causationId = evt-101` chứ không phải `evt-100`, vì nguyên nhân trực tiếp của nó là event yêu cầu giữ tồn kho. Trong khi đó `correlationId` vẫn có thể là `flow-7`.

Sơ đồ trên là **một đồ thị quan hệ nhân quả**, có thể phân nhánh, không nhất thiết là một danh sách tuyến tính. Khi nhiều listener xử lý cùng event, có thể có nhiều nhánh dẫn xuất độc lập.

## 3. Ba định danh quan trọng: eventId, correlationId, causationId

| Thuộc tính | Trả lời câu hỏi | Quy tắc thường dùng |
| --- | --- | --- |
| `eventId` | “Đây là **occurrence** sự kiện nào?” | Duy nhất cho một occurrence; giữ nguyên khi retry/replay cùng occurrence |
| `correlationId` | “Những event nào thuộc **cùng request/workflow**?” | Thường được tạo ở ranh giới yêu cầu rồi được **truyền tiếp** |
| `causationId` | “Event nào **trực tiếp gây ra** event hiện tại?” | Bằng `eventId` của event cha; có thể `null` ở event gốc |

Ví dụ:

```text
root.eventId        = "evt-100"
root.correlationId  = "flow-7"
root.causationId    = null

derived.eventId        = "evt-101"
derived.correlationId  = "flow-7"
derived.causationId    = "evt-100"
```

**Không đồng nhất các ID:**

1. Hai event có **cùng correlationId** không có nghĩa là trùng nhau; chúng chỉ có liên hệ trong cùng workflow.
2. Hai event có **cùng causationId** có thể là **anh em**, được tạo từ cùng một event cha.
3. Hai event có **cùng eventId** trong cơ chế replay thường biểu thị **cùng một event được phát/đọc lại**, không phải hai sự việc nghiệp vụ khác nhau.
4. Một event dẫn xuất **phải có eventId riêng** nếu nó mô tả một occurrence mới, ngay cả khi mang dữ liệu giống event gốc.
5. Một hành động nghiệp vụ có thể tạo nhiều event gốc cho những aggregate khác nhau; phạm vi “gốc” phải được xác định theo workflow.
6. Nếu mang thêm `aggregateId`, `aggregateVersion`, `tenantId`, `traceId`, đừng tự biến tất cả thành một loại ID; mỗi trường có ý nghĩa riêng.

### Event gốc không nhất thiết có causationId null trên toàn hệ thống

Một event `OrderAccepted` có thể bắt nguồn từ một HTTP request, một message bên ngoài hoặc một event khác. Khi phân tích **chuỗi Spring Application Events nội bộ**, ta có thể coi nó là root và đặt `causationId = null`. Nhưng trong hệ thống event liên dịch vụ, có thể giữ `causationId` từ hệ thống upstream. Do vậy “root” là **quan hệ trong phạm vi quan sát**, không phải một tính chất tuyệt đối của class.

### Vì sao không tạo UUID mới khi replay?

Giả sử sự kiện `evt-100` được đọc lại từ event store. Nếu replay bản ghi đó mà tự tạo `eventId = evt-999`, consumer dựa trên eventId có thể xem nó như occurrence mới và chạy tác dụng phụ lần thứ hai. Khi replay **cùng sự kiện**, phải giữ eventId và thông tin nguồn gốc ổn định. Nếu replay nhằm **tạo một công việc nghiệp vụ mới**, hãy mô hình hóa nó như hành động/command mới với ID mới, không gọi đó là phát lại nguyên văn event gốc.

Với event dẫn xuất được tái tạo từ replay, chính sách ID cần rõ: tái dùng ID dẫn xuất đã lưu, hoặc dùng khóa nghiệp vụ/causation ổn định để khử trùng. Không mặc định các UUID ngẫu nhiên được sinh lại sẽ giúp chống duplicate.

## 4. Phân biệt ngữ nghĩa với Spring API

Spring Framework Application Events hỗ trợ phát:

```java
publisher.publishEvent(someObject);
```

Với object không extends `ApplicationEvent`, Spring có thể bọc thành `PayloadApplicationEvent<T>` để phân phối qua hạ tầng event. Phương thức `@EventListener` vẫn có thể nhận thẳng kiểu payload:

```java
@EventListener
public void onOrderAccepted(OrderAccepted event) {
    // Đọc một record do ứng dụng tự định nghĩa.
}
```

Spring **không tự suy ra** từ method name rằng event này là gốc hay dẫn xuất. Nếu listener tạo và phát một event mới, ý nghĩa nhân quả xuất phát từ **logic nghiệp vụ và metadata** của event đó.

Cần đặc biệt phân biệt:

| Khái niệm | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| `ApplicationEventPublisher.publishEvent(Object)` | Công bố một đối tượng sự kiện | Persist event vào event store |
| `PayloadApplicationEvent` | Wrapper Spring cho một payload POJO | Định danh “event dẫn xuất” |
| `ApplicationEvent.getSource()` | Source object của sự kiện kiểu `ApplicationEvent` | `causationId` nghiệp vụ |
| `@EventListener` | Đăng ký phương thức nhận event theo kiểu/điều kiện | Sơ đồ nhân quả tự động |
| `@Order` | Điều chỉnh thứ tự gọi các listener cùng đợt phân phối | Đảm bảo hoàn tất nghiệp vụ theo thứ tự khi async |
| `@Async` | Chuyển phần xử lý sang executor | Một event mới hoặc chế độ replay |
| `@TransactionalEventListener` | Ràng buộc callback với pha transaction | Chống trùng hay lưu sự kiện bền vững |

**Một cạm bẫy:** `getSource()` của `ApplicationEvent` nói tới object được Spring sử dụng như source, không có hợp đồng rằng nó là **event cha trực tiếp**. Với `PayloadApplicationEvent`, source có thể là context/publisher. Muốn lưu quan hệ nhân quả ổn định qua process và replay, hãy dùng **metadata riêng** như `causationId`, không phụ thuộc `getSource()`.

## 5. Tạo event dẫn xuất từ listener đồng bộ

Spring hỗ trợ một tiện ích của `@EventListener`: phương thức listener **đồng bộ** có thể **trả về** một event mới; adapter sẽ công bố giá trị trả về như event tiếp theo.

```java
@EventListener
public InventoryReservationRequested derive(OrderAccepted event) {
    return new InventoryReservationRequested(
            /* metadata của event dẫn xuất */,
            event.orderId());
}
```

Đoạn này chỉ minh họa ý tưởng và cần các kiểu record cùng metadata cụ thể. Trong ví dụ hoàn chỉnh ở mục 7, mọi giá trị sẽ được cung cấp thật, không có chỗ trống.

Nếu muốn phát nhiều event dẫn xuất, `@EventListener` đồng bộ còn hỗ trợ trả về **mảng hoặc Collection**; Spring lần lượt phát từng phần tử:

```java
@EventListener
public List<Object> deriveActions(OrderAccepted event) {
    InventoryReservationRequested inventory = /* tạo từ event */;
    ConfirmationEmailRequested email = /* tạo từ event */;
    return List.of(inventory, email);
}
```

Đây là đoạn sơ đồ thiết kế, không phải mã độc lập. Chính việc **Spring công bố từng giá trị trả về** làm cho các listener của hai loại event tiếp tục được kích hoạt.

### Khi nào nên dùng return?

Đây là giải pháp ngắn gọn khi:

- Listener là **đồng bộ** trong cấu hình đang dùng.
- Các event dẫn xuất là kết quả trực tiếp, đơn giản từ event đầu vào.
- Không cần điều phối phức tạp cho lỗi/retry, transaction hay công bố có điều kiện ở nhiều thời điểm.
- Người đọc chấp nhận rằng các event tiếp theo được phát bởi adapter của `@EventListener`, không có lệnh `publishEvent(...)` hiển thị trong method.

Khi workflow dài hoặc cần quản lý rõ điểm phát event, một lời gọi `ApplicationEventPublisher.publishEvent(...)` **tường minh** thường dễ kiểm soát và quan sát hơn.

## 6. Với @Async: không dùng return để sinh event dẫn xuất

Spring có một giới hạn được tài liệu chính thức nêu rõ: **listener bất đồng bộ không thể phát event tiếp theo bằng cách trả về giá trị**.

Mẫu nên dùng:

```java
@Async("workflowExecutor")
@EventListener
public void onAccepted(OrderAccepted original) {
    InventoryReservationRequested derived = deriveRequest(original);
    publisher.publishEvent(derived);
}
```

Đây là đoạn tích hợp, cần inject `ApplicationEventPublisher publisher`, khai báo `deriveRequest(...)`, bật `@EnableAsync` và tạo executor bean có tên `workflowExecutor`. Phương thức listener trả về `void`; event mới xuất hiện từ **lệnh publish tường minh**, không phải từ return value.

**Không nên giả định** `@Async public InventoryReservationRequested onAccepted(...)` sẽ chạy như listener đồng bộ và Spring tự publish kết quả. Trong mô hình `@Async` qua proxy, một kiểu trả về nghiệp vụ như vậy còn không phù hợp hợp đồng trả về `void`/`Future` được hỗ trợ.

Với một listener async, các event dẫn xuất có thể được phát **sau** khi `publishEvent(original)` đã trả về. Khi đó, thứ tự hoàn thành phụ thuộc executor và các listener, không còn là thứ tự đệ quy đơn giản của một chuỗi đồng bộ.

## 7. Ví dụ Java 17 + Spring 6.2 chạy được: root phát hai event dẫn xuất

Chương trình console dưới đây dùng:

- Ba `record` làm payload bất biến: `OrderAccepted` (gốc), `InventoryReservationRequested` và `ConfirmationEmailRequested` (dẫn xuất).
- Một record `EventMetadata` chứa `eventId`, `correlationId`, `causationId` và `occurredAt`.
- Một listener của `OrderAccepted` **trả về `List<Object>`** gồm hai event dẫn xuất.
- Hai listener khác nhận từng loại event dẫn xuất để ghi trace.
- `AnnotationConfigApplicationContext` với event multicaster mặc định **đồng bộ**.
- Các ID cố định **chỉ để kết quả kiểm chứng dễ đọc**; production phải cấp phát và lưu metadata theo chính sách thực tế.

### 7.1. Cấu trúc dự án

```text
event-lineage-demo/
├── pom.xml
└── src/main/java/example/EventLineageDemo.java
```

### 7.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-lineage-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.EventLineageDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Tệp src/main/java/example/EventLineageDemo.java

```java
package example;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventLineageDemo {

    // "causationId" null được chấp nhận cho root trong demo.
    public record EventMetadata(
            String eventId,
            String correlationId,
            String causationId,
            Instant occurredAt) {

        public EventMetadata {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(correlationId, "correlationId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            if (eventId.isBlank() || correlationId.isBlank()) {
                throw new IllegalArgumentException(
                        "Event identifiers cannot be blank");
            }
        }
    }

    // Một sự thật: đơn hàng đã được chấp nhận.
    public record OrderAccepted(
            EventMetadata metadata,
            String orderId) {}

    // Hai yêu cầu được sinh từ việc xử lý OrderAccepted.
    public record InventoryReservationRequested(
            EventMetadata metadata,
            String orderId) {}

    public record ConfirmationEmailRequested(
            EventMetadata metadata,
            String orderId) {}

    public static final class Trace {
        private final List<String> lines = new ArrayList<>();

        public void add(String line) {
            lines.add(line);
        }

        public int size() {
            return lines.size();
        }

        public void printAll() {
            lines.forEach(System.out::println);
        }
    }

    public static class FlowListeners {
        private final Trace trace;

        public FlowListeners(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        public List<Object> deriveFromRoot(OrderAccepted root) {
            EventMetadata parent = root.metadata();

            trace.add("root OrderAccepted"
                    + " id=" + parent.eventId()
                    + " corr=" + parent.correlationId()
                    + " cause=-");

            EventMetadata inventoryMeta = new EventMetadata(
                    "evt-101",
                    parent.correlationId(),
                    parent.eventId(),
                    Instant.now());

            EventMetadata emailMeta = new EventMetadata(
                    "evt-102",
                    parent.correlationId(),
                    parent.eventId(),
                    Instant.now());

            return List.of(
                    new InventoryReservationRequested(
                            inventoryMeta, root.orderId()),
                    new ConfirmationEmailRequested(
                            emailMeta, root.orderId())
            );
        }

        @EventListener
        public void onInventory(InventoryReservationRequested event) {
            EventMetadata meta = event.metadata();
            trace.add("derived InventoryReservationRequested"
                    + " id=" + meta.eventId()
                    + " corr=" + meta.correlationId()
                    + " cause=" + meta.causationId());
        }

        @EventListener
        public void onEmail(ConfirmationEmailRequested event) {
            EventMetadata meta = event.metadata();
            trace.add("derived ConfirmationEmailRequested"
                    + " id=" + meta.eventId()
                    + " corr=" + meta.correlationId()
                    + " cause=" + meta.causationId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public FlowListeners flowListeners(Trace trace) {
            return new FlowListeners(trace);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            OrderAccepted root = new OrderAccepted(
                    new EventMetadata(
                            "evt-100",
                            "flow-7",
                            null,
                            Instant.parse("2026-11-01T08:00:00Z")),
                    "ORD-42");

            context.publishEvent(root);

            Trace trace = context.getBean(Trace.class);
            trace.printAll();
            System.out.println("Total observations: " + trace.size());
        }
    }
}
```

### 7.4. Chạy chương trình

Dùng JDK 17+ và Maven từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Bốn dòng do mã ứng dụng in** với multicaster đồng bộ mặc định:

```text
root OrderAccepted id=evt-100 corr=flow-7 cause=-
derived InventoryReservationRequested id=evt-101 corr=flow-7 cause=evt-100
derived ConfirmationEmailRequested id=evt-102 corr=flow-7 cause=evt-100
Total observations: 3
```

**Tại sao thứ tự này hợp lý?**

1. `context.publishEvent(root)` công bố record `OrderAccepted`.
2. Spring gọi phương thức `deriveFromRoot` nhận đúng kiểu payload; phương thức ghi dòng root rồi trả về `List.of(inventory, email)`.
3. Adapter `@EventListener` của Spring phát **lần lượt từng phần tử** của danh sách trả về.
4. Khi event inventory được phát, listener `onInventory` ghi dòng thứ hai; khi event email được phát, `onEmail` ghi dòng thứ ba.
5. `context.publishEvent(root)` trả về sau khi xử lý chuỗi đồng bộ. `main` in toàn bộ trace và số dòng.

`Trace` dùng `ArrayList` vì ví dụ **không kích hoạt xử lý bất đồng bộ**. Với multicaster tùy chỉnh hoặc `@Async`, cần cấu trúc an toàn luồng và cơ chế đợi kết quả; lúc đó không được giữ kỳ vọng cứng về thứ tự các callback.

**Phân biệt ý nghĩa:** `InventoryReservationRequested` là **yêu cầu giữ tồn kho**, không chứng minh kho đã được giữ. `ConfirmationEmailRequested` là **yêu cầu gửi email**, không chứng minh email đã gửi. Ứng dụng phải thực thi nhiệm vụ và chỉ phát `InventoryReserved` / `ConfirmationEmailSent` khi có kết quả đáng tin cậy.

**Điểm giới hạn của demo:** các ID `evt-101` và `evt-102` được viết cố định để giải thích và in kết quả ổn định. Nếu chạy nhiều đơn, hệ thống thật phải sinh/tra cứu định danh riêng, gắn với dữ liệu bền vững và chính sách replay; tuyệt đối không dùng hằng số này cho mọi đơn. Mã ví dụ không ghi database và không gửi HTTP/email thật.

## 8. Tạo event dẫn xuất bằng ApplicationEventPublisher tường minh

Không bắt buộc dùng return. Một listener có thể inject `ApplicationEventPublisher` rồi phát event mới:

```java
@Component
public class DerivationHandler {
    private final ApplicationEventPublisher publisher;

    public DerivationHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    public void onAccepted(OrderAccepted original) {
        EventMetadata parent = original.metadata();
        EventMetadata childMeta = new EventMetadata(
                UUID.randomUUID().toString(),
                parent.correlationId(),
                parent.eventId(),
                Instant.now());

        publisher.publishEvent(
                new InventoryReservationRequested(
                        childMeta, original.orderId()));
    }
}
```

Đây là **đoạn tích hợp**, không phải chương trình chạy độc lập: cần import `@Component`, `ApplicationEventPublisher`, `@EventListener`, `UUID`, `Instant` và dùng các record đã định nghĩa ở mục 7. Ở production, một UUID mới cho **lần tạo event dẫn xuất thật sự** là hợp lý, nhưng **không nên tạo UUID khác khi replay cùng occurrence** nếu việc tái tạo đó phải được nhận là duplicate.

Ưu điểm của publish tường minh là điểm phát hiện rõ trong mã, dễ điều kiện hóa theo kết quả xử lý, kiểm soát log và xử lý lỗi. Đây cũng là lựa chọn cần dùng khi listener bất đồng bộ cần phát event tiếp theo.

### Mẫu sinh nhiều nhánh

Khi một event gốc có thể dẫn tới nhiều event, không nhất thiết phải sinh tất cả trong cùng một listener. Có thể đăng ký hai listener độc lập cho `OrderAccepted`:

- Một listener liên quan kho tạo `InventoryReservationRequested`.
- Một listener liên quan thông báo tạo `ConfirmationEmailRequested`.

Cách chia giúp tách chức năng nhưng cần hiểu sự khác biệt về **thứ tự**, **transaction** và **xử lý lỗi**. Trong multicaster đồng bộ, nếu listener đầu tiên ném exception không được bắt, quá trình phân phối có thể dừng trước khi listener khác chạy. Với multicaster bất đồng bộ, thứ tự hoàn thành các nhánh càng không được bảo đảm.

Nếu yêu cầu “chỉ gửi email sau khi đã giữ tồn kho”, đừng tạo hai event anh em và hy vọng listener nào đó chạy trước. Hãy mô hình hóa nhân quả:

```text
OrderAccepted
    -> InventoryReservationRequested
        -> InventoryReserved
            -> ConfirmationEmailRequested
```

Ở chuỗi này, `ConfirmationEmailRequested.causationId` nên trỏ tới `InventoryReserved.eventId`, vì email được yêu cầu **sau khi kho xác nhận giữ thành công**.

## 9. Phân biệt “event dẫn xuất” với command và phản ứng phụ

Tên “event” đôi khi bị dùng cho mọi thông báo trong ứng dụng. Tuy nhiên, hai kiểu thông điệp khác nhau về ngữ nghĩa:

- **Fact/domain event:** “Điều gì đã xảy ra?” Ví dụ `OrderAccepted`, `InventoryReserved`, `PaymentCaptured`.
- **Command/request:** “Hãy làm điều gì?” Ví dụ `ReserveInventory`, `SendConfirmationEmail`, hoặc payload mang tên `InventoryReservationRequested`.

Spring Application Events có thể chuyển **cả hai loại payload** do ứng dụng định nghĩa. Framework không ép phải là domain event hay command. Nhưng trong thiết kế hệ thống, việc đặt tên đúng ý nghĩa giúp tránh lỗi:

| Payload | Ý nghĩa thực tế | Không nên suy ra |
| --- | --- | --- |
| `OrderAccepted` | Đơn đã được chấp nhận | Thanh toán đã hoàn tất |
| `InventoryReservationRequested` | Đã yêu cầu giữ tồn kho | Tồn kho chắc chắn đã giữ |
| `InventoryReserved` | Kho đã xác nhận giữ thành công | Email đã được gửi |
| `ConfirmationEmailRequested` | Đã yêu cầu gửi email | Email đã được nhà cung cấp tiếp nhận |
| `ConfirmationEmailSent` | Một lần gửi đã thành công theo hợp đồng định nghĩa | Người nhận đã mở hoặc đọc email |

Đối với event dẫn xuất, **phải chọn tên theo bước thực sự đã đạt**. Nếu chỉ scheduling một task, gọi nó là “sent/completed” sẽ gây hiểu nhầm trong log, test và báo cáo nghiệp vụ.

### Event dẫn xuất có nên chứa toàn bộ payload gốc?

Thường không. Event mới nên mang **dữ liệu cần thiết cho trách nhiệm của nó**, cộng định danh để truy vết:

```java
public record ConfirmationEmailRequested(
        EventMetadata metadata,
        String orderId,
        String templateCode
) {}
```

Đoạn này là một biến thể schema minh họa, không thay đổi chương trình ở mục 7. Không cần sao chép toàn bộ entity đơn hàng, thông tin thẻ, object HTTP request hay các resource đang sống trong transaction. Event nên là snapshot bất biến, an toàn khi xử lý chậm hoặc trên thread khác.

## 10. Replay: phân biệt phát lại event gốc và tái tạo event dẫn xuất

**Replay** là việc ứng dụng đọc lại và xử lý một event đã tồn tại (thường từ event store, outbox, broker hoặc một nguồn bền vững). **Spring ApplicationEventPublisher tự nó không cung cấp event store hoặc chức năng replay bền vững**. Việc lưu, chọn phạm vi replay, xử lý checkpoint và bảo đảm delivery phải do kiến trúc hệ thống giải quyết.

Hai chiến lược cần phân biệt:

### 10.1. Replay toàn bộ event đã lưu để rebuild read model

Giả sử lịch sử chứa:

```text
evt-100 OrderAccepted
evt-101 InventoryReservationRequested
evt-103 InventoryReserved
evt-104 ConfirmationEmailRequested
```

Khi rebuild read model, ứng dụng có thể **phát lại chính các bản ghi đã lưu** cho projector đọc dữ liệu. Nếu đồng thời cho một listener của `OrderAccepted` tự sinh `InventoryReservationRequested` mới, sẽ xuất hiện hai đường cùng tạo ra thao tác derived: bản ghi `evt-101` đã lưu và bản mới tái sinh. Điều này dễ làm trùng event/tác dụng phụ.

**Chính sách thích hợp:** một replay phục vụ projection thường **không sinh lại external side effect** và không mặc định tạo thêm event mới; projector xử lý các bản ghi lịch sử như input đã có.

### 10.2. Replay event gốc để chạy lại workflow

Đôi khi cần thực sự **thực thi lại** một bước nghiệp vụ do lỗi trước đó, ví dụ yêu cầu gửi email chưa được thực hiện. Khi đó phải xác định:

- Có đang xử lý lại **cùng occurrence** hay muốn tạo một ý định nghiệp vụ mới?
- Event dẫn xuất đã được lưu chưa?
- Khóa idempotency nào nhận ra tác vụ đã chạy?
- Bên ngoài có hỗ trợ idempotency key không?
- Khi retry, có giữ được `correlationId` và `causationId` để không phá chuỗi truy vết?
- Có cần phát event thất bại/bù trừ thay vì chạy lại toàn bộ chuỗi?

Một replay an toàn không đơn thuần là:

```java
for (StoredEvent event : history) {
    publisher.publishEvent(event.payload());
}
```

Đây là mã giả cho cơ chế đọc lịch sử; nó không giải quyết duplicate, transaction hoặc external side effect. Phải chọn consumer nào được tham gia replay và hành vi của chúng khi gặp event cũ.

### Bảng so sánh

| Mục đích | Input | Có nên sinh event dẫn xuất mới? | Tác dụng phụ ngoài? |
| --- | --- | --- | --- |
| Rebuild read model | Các event lịch sử đã lưu | Thường **không** | Không |
| Retry một handler bị lỗi | Cùng event occurrence | Chỉ khi bước cần làm chưa hoàn thành và có idempotency | Có điều kiện, phải chống trùng |
| Bắt đầu workflow nghiệp vụ mới | Command/request mới | Có, với event ID mới | Theo nghiệp vụ |
| Reprocess để kiểm tra logic trong môi trường thử | Event lịch sử | Có thể mô phỏng nhưng không commit/publish thật | Không hoặc sandbox |
| Đồng bộ lại consumer sau downtime | Các event còn tồn trong broker/outbox | Không tự nhân bản event đã lưu | Chỉ qua handler đã thiết kế idempotent |

## 11. Tránh vòng lặp, fan-out không kiểm soát và chuỗi quá sâu

Nếu listener nhận `A` rồi phát `B`, còn listener nhận `B` lại phát `A` không có điều kiện dừng, sẽ có vòng lặp:

```text
EventA -> EventB -> EventA -> EventB -> ...
```

Trong multicaster đồng bộ, việc publish event bên trong listener có thể tạo lời gọi lồng nhau trên cùng thread và làm tăng độ sâu stack. Nếu chuyển sang async, vấn đề không biến mất: event có thể tạo fan-out không giới hạn, tăng queue và cạn tài nguyên.

Một số biện pháp:

1. **Định nghĩa state machine/workflow rõ ràng:** chỉ chuyển trạng thái theo những bước hợp lệ.
2. **Phân biệt fact và request:** không tạo request lặp khi đã có kết quả hoàn tất.
3. **Idempotency key** cho từng handler và tác dụng phụ quan trọng.
4. **Theo dõi causation graph** để phát hiện chu trình và số lần tạo event bất thường.
5. **Giới hạn retry/fan-out/depth** theo yêu cầu nghiệp vụ.
6. **Tách orchestration** khi có nhiều nhánh phụ thuộc nhau, thay vì để các listener tự phát lẫn nhau vô hạn.
7. **Quan sát queue và lỗi** khi chạy bất đồng bộ hoặc đưa qua broker.

Một `correlationId` ổn định giúp gom log nhưng không tự ngăn vòng lặp; bộ phận xử lý phải sử dụng state và idempotency đúng cách.

## 12. Transaction: event gốc và dẫn xuất có thể xảy ra trước commit

Trong multicaster đồng bộ mặc định, listener chạy trong thread gọi `publishEvent`. Nếu publisher đang ở trong một transaction, các listener đồng bộ thường thấy transaction context đó.

Ví dụ minh họa tích hợp:

```java
@Transactional
public void acceptOrder(String orderId) {
    // repository.save(...) cập nhật trạng thái.
    publisher.publishEvent(
            new OrderAccepted(metadata, orderId));
}
```

Đoạn này cần transaction manager, repository, `publisher` và `metadata`. Khi event gốc được phát **trước commit**, một listener đồng bộ có thể ngay lập tức tạo và phát event dẫn xuất **cũng trước commit**. Nếu transaction sau đó rollback, email/request ngoài đã được thực hiện từ listener có thể vẫn xảy ra, tạo sai lệch nghiệp vụ.

### Nếu event dẫn xuất chỉ được phát sau commit

Có thể dùng `@TransactionalEventListener` ở bước xử lý root:

```java
@Component
public class CommittedOrderListener {
    private final ApplicationEventPublisher publisher;

    public CommittedOrderListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCommitted(OrderAccepted original) {
        EventMetadata child = createChildMetadata(original);
        publisher.publishEvent(
                new InventoryReservationRequested(
                        child, original.orderId()));
    }
}
```

Đây là đoạn minh họa tích hợp cần định nghĩa `createChildMetadata(...)` và import `@Component`, `TransactionalEventListener`, `TransactionPhase`. Không phải chương trình standalone ở mục 7.

**Quan trọng:**

- `@TransactionalEventListener` mặc định dùng `AFTER_COMMIT`; `fallbackExecution` mặc định là `false`, nên không có transaction nguồn thì listener thường không chạy.
- Callback được kích hoạt sau commit, nhưng **không tự lưu event dẫn xuất vào event store**; crash có thể làm mất công việc trước khi publish hoặc trước khi listener xử lý xong.
- Sau commit, một số resource transaction cũ có thể còn gắn với thread. Nếu callback cần ghi database mới, dùng transaction mới thích hợp (ví dụ `REQUIRES_NEW` qua Spring proxy hoặc `TransactionTemplate`).
- Một event được publish trên thread khác thường không mang transaction gốc. Một listener `@TransactionalEventListener` cho event dẫn xuất có thể không chạy nếu không có transaction hoạt động và `fallbackExecution = false`.
- Với nghiệp vụ **không được phép mất event**, outbox record nên được ghi **trong transaction nghiệp vụ ban đầu**, sau đó có worker đọc, retry và phát, thay vì chỉ dựa vào callback sau commit nằm trong RAM.

**Không ngộ nhận:** `@TransactionalEventListener` kiểm soát **thời điểm**, không tự giải quyết duplicate, idempotency, durability hay thứ tự qua nhiều process.

## 13. Khử trùng event và tác dụng phụ theo từng handler

Khi event gốc `evt-100` bị replay, listener có thể tạo thêm event dẫn xuất; hoặc khi event dẫn xuất được nhận lại từ broker, consumer có thể thực hiện tác dụng phụ hai lần. Bảo vệ ở nhiều tầng:

### 13.1. Duy nhất theo consumer và event

Một bảng marker điển hình:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

`(consumer_name, event_id)` cho phép hai handler độc lập xử lý cùng một event nhưng ngăn **một handler** xử lý trùng occurrence đó. Một unique constraint ở database quan trọng hơn việc `SELECT` trước rồi `INSERT`, vì hai worker có thể cùng thấy “chưa có”.

### 13.2. Duy nhất theo nghiệp vụ/quan hệ nhân quả

Ví dụ với `ConfirmationEmailRequested` có thể cần ràng buộc “một email xác nhận cho mỗi `orderId` và template version” hoặc “một yêu cầu gửi cho mỗi causation event”. Khi đó một `eventId` mới không được phép làm mất bảo vệ nghiệp vụ.

Khóa nên phản ánh **hiệu ứng cần chống trùng**, không lấy toàn bộ payload hoặc correlationId làm khóa một cách tùy ý. `correlationId` quá rộng: một workflow có nhiều event hợp lệ cùng correlation.

### 13.3. Tác dụng phụ bên ngoài

Nếu đánh dấu marker rồi gọi email và process chết trước khi gửi, lần retry có thể bị chặn dù email chưa đi. Nếu gửi email trước khi đánh dấu, crash hoặc timeout có thể khiến retry gửi trùng.

Với yêu cầu giao nhận đáng tin, dùng **transactional outbox** để ghi nhận công việc trong cùng transaction với thay đổi dữ liệu, worker claim/ retry và khóa idempotency phía hệ thống ngoài khi có thể. Không tuyên bố “exactly once end-to-end” chỉ vì một event được publish đúng một lần trong Spring context.

## 14. Event gốc và event dẫn xuất khi tracing

Để hiểu một chuỗi thực thi, log nên hiển thị ít nhất:

```text
eventType
eventId
correlationId
causationId
aggregateId / orderId
occurredAt
handlerName
processingAttempt
processingStatus
```

Ví dụ:

```text
type=OrderAccepted id=evt-100 corr=flow-7 cause=- order=ORD-42
type=InventoryReservationRequested id=evt-101 corr=flow-7 cause=evt-100 order=ORD-42
type=ConfirmationEmailRequested id=evt-102 corr=flow-7 cause=evt-100 order=ORD-42
```

Từ đó có thể:

- Dùng `correlationId` để gom các event thuộc một workflow.
- Dùng `causationId` để dựng **cạnh cha → con** trên đồ thị.
- Dùng `eventId` để nhận biết occurrence và replay/duplicate.
- Dùng `orderId` để liên hệ aggregate nghiệp vụ.
- Dùng trạng thái xử lý và số lần thử để biết listener đã thành công hay chỉ được gọi.

Cần phân biệt `traceId` từ OpenTelemetry/Micrometer với `correlationId` nghiệp vụ. Hai ID có thể liên quan nhưng **không nhất thiết cùng giá trị hoặc vòng đời**. Một workflow dài ngày có thể trải qua nhiều distributed traces mà vẫn giữ cùng correlation ID; ngược lại một trace HTTP có thể chạm nhiều event riêng biệt.

Với listener `@Async`, `ThreadLocal`/MDC và transaction context không mặc định truyền sang luồng worker. Cách an toàn là mang metadata có ý nghĩa lâu dài trong **payload bất biến**, đồng thời thiết kế context propagation có chủ đích cho tracing kỹ thuật.

## 15. Thiết kế payload bất biến cho chuỗi event

Java 17 `record` giúp mô tả event gọn và minh bạch:

```java
public record EventMetadata(
        String eventId,
        String correlationId,
        String causationId,
        Instant occurredAt) {}

public record OrderAccepted(
        EventMetadata metadata,
        String orderId) {}

public record InventoryReservationRequested(
        EventMetadata metadata,
        String orderId) {}
```

Đây là ví dụ kiểu dữ liệu; chương trình mục 7 có phần kiểm tra bất biến metadata đầy đủ. Các trường `String` và `Instant` là immutable; record cũng không có setter cho các component.

Tuy vậy **record chỉ đảm bảo bất biến nông**. Nếu event chứa `List<OrderLine>` và `OrderLine` mutable, cần tạo snapshot của list và nested elements. `List.copyOf(...)` chỉ cố định cấu trúc list, không deep-copy phần tử mutable.

Với event dẫn xuất, đừng truyền nguyên entity JPA mutable từ event gốc rồi tin rằng nó là snapshot. Nên map sang ID hoặc value immutable; record giúp làm hợp đồng rõ hơn nhưng không tự xử lý lazy loading, concurrency hoặc durability.

### Thời gian của event dẫn xuất

`occurredAt` của event gốc mô tả thời điểm sự việc gốc xảy ra. `occurredAt` của event dẫn xuất nên phản ánh **thời điểm event dẫn xuất thực sự được tạo**, không sao chép timestamp gốc chỉ để cho giống nhau.

Một số hệ thống cần cả `triggeredAt` hoặc `originalOccurredAt` để so sánh độ trễ xử lý. Khi replay, phải quyết định có giữ timestamp gốc của occurrence và ghi thêm `replayedAt` trong metadata xử lý thay vì âm thầm thay đổi `occurredAt` của bản ghi lịch sử.

## 16. Kiểm thử quan hệ gốc – dẫn xuất

Một phép thử tốt không chỉ khẳng định số lượng event, mà còn khẳng định **quan hệ nhân quả đúng**:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Root được publish một lần | Listener root nhận đúng `OrderAccepted` |
| Hai event dẫn xuất được tạo | Có `InventoryReservationRequested` và `ConfirmationEmailRequested` |
| Mỗi event dẫn xuất có eventId riêng | `evt-101` khác `evt-102` và khác `evt-100` |
| Giữ correlation | Cả ba có `correlationId=flow-7` |
| Giữ causation đúng | Hai event dẫn xuất trực tiếp có `causationId=evt-100` |
| Không có recursion vô tận | Listener derived không tự phát lại root bừa bãi |
| Async handler | Đợi bằng latch/future, không đoán thứ tự log |
| Transaction rollback | Không phát tác dụng phụ trái ngữ nghĩa commit |
| Replay event gốc | Không tạo tác dụng phụ trùng khi consumer đã xử lý |
| Replay lịch sử | Không nhân đôi event dẫn xuất đã lưu nếu đang rebuild projection |

### 16.1. Kiểm thử thứ tự trong cấu hình đồng bộ

Ví dụ Java ở mục 7 dùng đúng một listener để nhận root và trả về một `List.of(...)` hai phần tử. Vì vậy trace do ứng dụng ghi có thứ tự xác định trong trường hợp **multicaster đồng bộ mặc định**. Không áp dụng kỳ vọng cứng đó nếu các listener được chuyển sang async.

Khi cần test async, dùng `CountDownLatch`, `CompletableFuture` hoặc công cụ đồng bộ có timeout và kiểm tra **tập event thu được** cùng metadata thay vì assert thứ tự completion.

### 16.2. Kiểm thử idempotency thật

Nếu muốn chứng minh retry không nhân đôi email, đừng chỉ mock `publishEvent` và đếm nó chạy một lần. Hãy kiểm thử marker DB với unique constraint, trạng thái outbox, và hai worker/connection cạnh tranh cùng khóa. Bản thân một event record bất biến không bảo vệ chống trùng.

### 16.3. Kiểm thử khi một listener thất bại

Trong multicaster đồng bộ mặc định, exception chưa xử lý của listener có thể lan lên publisher và làm chuỗi event dừng trước khi các nhánh khác hoàn tất. Trong async, exception của listener `void` có thể được báo qua async error handler mà không truyền lại tới caller; các nhánh khác vẫn có thể chạy.

Thử lỗi ở từng bước để thấy chính xác event nào đã được publish, bước nào đã có tác dụng phụ và có khả năng retry từ đâu. Không mặc định “publishEvent đã trả về” đồng nghĩa mọi nhiệm vụ ngoài hệ thống đã thành công.

## 17. Các sai lầm thường gặp

1. **Gọi mọi event do handler tạo ra là event gốc.** Khi muốn truy vết, phải ghi lại quan hệ trực tiếp tới event cha.
2. **Dùng `correlationId` làm khóa duy nhất của event.** Một workflow chứa nhiều event khác nhau cùng correlation.
3. **Giữ nguyên `eventId` cho event dẫn xuất mới.** Làm lẫn occurrence và gây lỗi idempotency.
4. **Sinh eventId mới cho replay của cùng occurrence.** Consumer không thể nhận diện bản ghi lặp chỉ bằng eventId.
5. **Dùng `ApplicationEvent.getSource()` thay `causationId`.** Source của framework không phải hợp đồng parent event.
6. **Nhầm request với kết quả đã hoàn thành.** `InventoryReservationRequested` không phải `InventoryReserved`.
7. **Giả định sự kiện gốc và dẫn xuất luôn chạy trên một thread.** Khi dùng `@Async` hoặc multicaster tùy chỉnh, thread có thể khác.
8. **Dùng return value của `@Async @EventListener` để phát event dẫn xuất.** Spring không hỗ trợ; phải publish tường minh.
9. **Tin rằng `@Order` bảo đảm hoàn tất các công việc async theo thứ tự.** Nó chỉ liên quan thứ tự dispatch theo điều kiện phù hợp, không đảm bảo completion.
10. **Replay toàn bộ lịch sử nhưng đồng thời tự tái sinh các derived event đã lưu.** Dễ nhân đôi xử lý.
11. **Không giới hạn vòng lặp/fan-out.** Listener có thể phát event đệ quy vô hạn hoặc làm đầy queue.
12. **Phát tác dụng phụ trước commit rồi giả định rollback sẽ thu hồi nó.** HTTP/email không tự rollback với database.
13. **Dựa vào Spring event in-process như event store bền vững.** `publishEvent` không tự persist hoặc replay.
14. **Đưa nguyên JPA entity mutable trong payload.** Dễ thay đổi dữ liệu trong khi listener xử lý và gây vấn đề lazy loading.
15. **Thiếu idempotency ở consumer cuối.** Dù event gốc không bị phát trùng, một derived event có thể được retry từ outbox/broker.
16. **Giữ timestamp root cho mọi derived event.** Làm sai thời điểm phát sinh từng bước và sai số đo latency.

## 18. Checklist thiết kế hệ thống event

- [ ] Đã xác định **root** trong phạm vi workflow cần quan sát.
- [ ] Mỗi occurrence có `eventId` ổn định; event dẫn xuất mới có ID mới.
- [ ] Event dẫn xuất giữ `correlationId` và trỏ `causationId` tới **event cha trực tiếp**.
- [ ] Tên event phân biệt sự thật đã xảy ra với yêu cầu mới được tạo.
- [ ] Payload là snapshot bất biến, không chứa resource hoặc entity mutable không kiểm soát.
- [ ] Với `@EventListener` đồng bộ, biết rõ khi nào dùng return event hoặc Collection.
- [ ] Với listener `@Async`, dùng `ApplicationEventPublisher.publishEvent(...)` tường minh.
- [ ] Đã xác định thời điểm transaction: trước commit, sau commit hoặc outbox.
- [ ] Replay phục vụ projection không tự phát lại các side effect quan trọng.
- [ ] Có chiến lược idempotency cho từng handler và các hệ thống ngoài.
- [ ] Có giám sát quan hệ `eventId` / `causationId` / `correlationId`, retry và kết quả.
- [ ] Có test duplicate, rollback, replay, đa luồng và chuỗi có nhiều nhánh.

**Ghi nhớ:** event gốc ghi nhận điểm khởi đầu của chuỗi; event dẫn xuất là event **mới có nguyên nhân trực tiếp** là một event trước đó. Sử dụng `eventId` để định danh từng occurrence, `correlationId` để nhóm workflow, `causationId` để dựng quan hệ cha–con. Spring giúp công bố và phân phối các event, nhưng việc quản lý nhân quả, replay, durability và idempotency là trách nhiệm thiết kế của ứng dụng.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events và return event từ @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — @EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
