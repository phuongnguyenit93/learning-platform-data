# Một listener trả về nhiều event trong Spring Framework Application Events

## 1. Ý tưởng: một event đầu vào tạo ra nhiều event tiếp theo

Trong Spring Framework, một phương thức có `@EventListener` **không bắt buộc trả về `void`**. Nếu phương thức trả về một giá trị khác `null`, Spring có thể **phát tiếp giá trị đó như một application event mới**. Đặc biệt, **nếu kết quả là một `Collection` hoặc mảng, từng phần tử được phát thành một event riêng**.

Đây là cách ngắn gọn để biểu diễn một chuỗi xử lý event (event chaining) hoặc phân nhánh (fan-out):

~~~text
ApplicationEventPublisher.publishEvent(OrderPlaced)
          |
          v
@EventListener
List<Object> classifyAndDecide(OrderPlaced)
          |
          +-- trả về OrderSizeClassified
          |          |
          |          +--> @EventListener onSizeClassified(...)
          |
          +-- trả về ReviewDecisionCalculated
                     |
                     +--> @EventListener onReviewDecision(...)
                                  |
                                  +-- trả về ReviewPathSelected
                                             |
                                             +--> @EventListener onReviewPath(...)
~~~

Mỗi phần tử trả về là **một thông điệp sự kiện độc lập**, có thể được Spring chuyển đến những listener khác nhau theo kiểu đối tượng. Điều này khác với việc trả về `List<Order>` trong một phương thức nghiệp vụ thông thường: khi một listener trả `Collection`, Spring **không coi toàn bộ danh sách là đúng một event payload** theo cơ chế return-value publication của `@EventListener`.

**Phạm vi của bài:** cơ chế trả về nhiều event của `@EventListener` trong cùng `ApplicationContext`, cách tạo chuỗi event, kiểm soát lỗi/vòng lặp, tương tác transaction và giới hạn của việc phát lại (replay). Đây không phải cơ chế message broker, không tự cung cấp lưu trữ bền vững hay phát lại lịch sử.

## 2. Quy tắc chính thức của @EventListener

Spring xử lý kết quả của một phương thức listener như sau:

| Kiểu giá trị trả về | Hành vi điển hình |
| --- | --- |
| `void` | Không phát thêm event qua return value. |
| Một đối tượng khác `null`, ví dụ `OrderChecked` | Phát đối tượng đó thành **một event mới**. |
| `List<?>`, `Set<?>` hoặc `Collection<?>` | Phát **từng phần tử** thành các event riêng. |
| Mảng, ví dụ `Object[]` hoặc `OrderChecked[]` | Phát **từng phần tử** thành các event riêng. |
| `null` | Không có kết quả để phát thêm. |
| Collection/mảng rỗng | Không có phần tử, nên không có event phát thêm từ kết quả. |
| Listener dùng `@Async` | **Không được sử dụng return value để phát tiếp event**; phải gọi `ApplicationEventPublisher` trực tiếp nếu muốn phát tiếp. |

Ví dụ ngắn với một kết quả duy nhất:

~~~java
@EventListener
public OrderChecked check(OrderPlaced event) {
    return new OrderChecked(event.orderId());
}
~~~

Ví dụ trả về **hai event khác kiểu**:

~~~java
@EventListener
public List<Object> route(OrderPlaced event) {
    return List.of(
        new OrderIndexed(event.orderId()),
        new OrderAuditPrepared(event.orderId()));
}
~~~

Ví dụ trả về mảng:

~~~java
@EventListener
public Object[] routeAsArray(OrderPlaced event) {
    return new Object[] {
        new OrderIndexed(event.orderId()),
        new OrderAuditPrepared(event.orderId())
    };
}
~~~

*Các ví dụ ở phần này là các đoạn tích hợp minh họa: `OrderPlaced`, `OrderChecked`, `OrderIndexed` và `OrderAuditPrepared` là các kiểu nghiệp vụ giả định; cần khai báo kiểu, import `@EventListener`, `java.util.List` và đặt phương thức trong Spring bean. Ví dụ Maven/Java 17+ chạy hoàn chỉnh nằm ở phần 4.*

Một số điều cần nhớ:

- Spring dựa vào **giá trị trả về thực tế** để phát event kế tiếp, không dựa vào tên phương thức hay tên biến `result`.
- Sự kiện trả về có thể là một `ApplicationEvent` tùy biến hoặc **payload object** thông thường như Java record; với payload object, Spring sử dụng cơ chế `PayloadApplicationEvent`.
- `List<Object>` hữu ích khi cần trả các **kiểu event khác nhau**. `List<OrderChecked>` hợp lý khi mọi event cùng kiểu.
- Không dùng danh sách có phần tử `null` để diễn đạt “bỏ qua một event”; hãy chỉ thêm các phần tử hợp lệ. `List.of(...)` vốn không cho phần tử `null`.
- Nếu thứ tự phát trong fan-out có ý nghĩa, dùng một cấu trúc có thứ tự rõ như `List.of(...)` hoặc mảng, **không dựa vào thứ tự duyệt của `HashSet`**.

Tài liệu của Spring nêu rõ: listener trả về một event sẽ kích hoạt publication của event đó; nếu cần nhiều event, hãy trả về một `Collection` hoặc array. Cơ chế này **không hỗ trợ return-value publication đối với asynchronous listener**.

## 3. Điều gì xảy ra sau khi return?

Trong luồng mặc định đồng bộ của Spring:

1. Một component gọi `applicationEventPublisher.publishEvent(originalEvent)`.
2. `ApplicationEventMulticaster` chuyển event tới listener phù hợp.
3. `@EventListener` được thực thi; code bên trong có thể xác minh điều kiện, đọc dữ liệu và tạo kết quả.
4. Nếu method trả về một `Collection`/mảng, hạ tầng listener duyệt các phần tử và phát mỗi phần tử như event mới.
5. Mỗi event mới được multicaster phân phối tới các listener khớp kiểu tương ứng. Một listener khác lại có thể trả về event, tạo thành một chuỗi nhiều tầng.
6. Khi toàn bộ chuỗi đồng bộ hoàn tất, lời gọi `publishEvent(...)` ban đầu mới kết thúc bình thường.

Sơ đồ thời điểm khi **không dùng `@Async` hoặc executor cho multicaster**:

~~~text
Caller                       Spring event infrastructure
  |                                      |
  | publishEvent(OrderPlaced)            |
  |------------------------------------->|
  |                       invoke handler(OrderPlaced)
  |                       handler returns List[A, B]
  |                       publish A
  |                         invoke listener(A)
  |                       publish B
  |                         invoke listener(B)
  |                         listener(B) returns C
  |                         publish C
  |                           invoke listener(C)
  |<-------------------------------------|
  | publishEvent(...) returned           |
~~~

Từ “phát tiếp” ở đây là **publication trong cùng hệ thống sự kiện**, không phải hành động tự ghi event vào một database hay hàng đợi. Nếu một listener nhận lại đúng kiểu event mà nó luôn phát tiếp, chương trình có thể đệ quy vô hạn. Nếu một listener ném exception chưa được xử lý, toàn bộ chuỗi đồng bộ có thể bị ngắt trước khi phát hết các phần tử còn lại.

**Không nên suy diễn thứ tự toàn cục từ sơ đồ này.** Trong ví dụ đồng bộ, một `List` được duyệt theo thứ tự phần tử và lời gọi con có thể chạy lồng nhau. Nhưng khi nhiều listener cùng đăng ký một kiểu, có `@Order`, multicaster tùy biến hoặc xử lý async, thứ tự giữa các listener và thời gian kết thúc có thể khác. Nếu hệ thống phải bảo đảm thứ tự nghiệp vụ, hãy thiết kế điều phối rõ ràng thay vì chỉ dựa vào side effect của event fan-out.

## 4. Ví dụ hoàn chỉnh: Java 17+ và Spring Framework 6.2

Ví dụ này dùng một `@EventListener` nhận `OrderPlaced` rồi trả về **hai event khác kiểu** trong `List<Object>`:

- `OrderSizeClassified`: kết quả phân loại kích thước đơn hàng dựa trên số lượng mặt hàng.
- `ReviewDecisionCalculated`: kết quả xác định cần kiểm tra thủ công hay không.

Listener của `ReviewDecisionCalculated` còn trả về `ReviewPathSelected`, thể hiện **chuỗi event hai tầng**. Mỗi event được xử lý bởi đúng một listener nhận kiểu tương ứng, làm cho các dòng stdout có thể kiểm chứng.

Không dùng Spring Boot, database, broker hay executor để tránh làm mờ cơ chế cốt lõi.

### 4.1. Cấu trúc dự án

~~~text
event-fan-out-demo/
├── pom.xml
└── src/main/java/EventFanOutDemo.java
~~~

Yêu cầu: JDK 17+, Maven 3.8+ và quyền tải thư viện Maven lần đầu.

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-fan-out-demo</artifactId>
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

### 4.2. Mã nguồn đầy đủ

`src/main/java/EventFanOutDemo.java`:

~~~java
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventFanOutDemo {

    public record OrderPlaced(String orderId, int itemCount) {}

    public record OrderSizeClassified(
            String orderId, String size) {}

    public record ReviewDecisionCalculated(
            String orderId, boolean required) {}

    public record ReviewPathSelected(
            String orderId, String path) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public EventHandlers eventHandlers() {
            return new EventHandlers();
        }
    }

    public static class EventHandlers {

        @EventListener
        public List<Object> classifyAndDecide(OrderPlaced event) {
            System.out.println("A: OrderPlaced " + event.orderId());

            String size = event.itemCount() >= 3
                    ? "LARGE" : "SMALL";
            boolean manualReview = event.itemCount() >= 3;

            // Một listener sinh HAI event có kiểu khác nhau.
            return List.of(
                new OrderSizeClassified(event.orderId(), size),
                new ReviewDecisionCalculated(
                    event.orderId(), manualReview));
        }

        @EventListener
        public void onSize(OrderSizeClassified event) {
            System.out.println("B: Size " + event.size());
        }

        @EventListener
        public ReviewPathSelected onDecision(
                ReviewDecisionCalculated event) {
            System.out.println(
                "C: Review required=" + event.required());

            String path = event.required()
                    ? "MANUAL" : "AUTO";
            return new ReviewPathSelected(
                    event.orderId(), path);
        }

        @EventListener
        public void onPath(ReviewPathSelected event) {
            System.out.println("D: Path " + event.path());
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("BEGIN");
            context.publishEvent(new OrderPlaced("ORD-7", 4));
            System.out.println("END");
        }
    }
}
~~~

Mặc dù phương thức `classifyAndDecide(...)` trả `List<Object>`, các phần tử vẫn giữ kiểu runtime riêng. Spring phát `OrderSizeClassified` và `ReviewDecisionCalculated` thành hai event độc lập, vì thế hai listener typed `onSize(...)` và `onDecision(...)` được gọi. `onDecision(...)` trả về tiếp một `ReviewPathSelected`, được chuyển tới `onPath(...)`.

### 4.3. Biên dịch và chạy

Trong thư mục `event-fan-out-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventFanOutDemo
~~~

Kết quả do chương trình tự in ra, với multicaster mặc định đồng bộ và không tính log của Maven:

~~~text
BEGIN
A: OrderPlaced ORD-7
B: Size LARGE
C: Review required=true
D: Path MANUAL
END
~~~

### 4.4. Vì sao thứ tự trên xác định trong ví dụ này?

- `BEGIN` được in trước khi gọi `context.publishEvent(...)`.
- `A` do duy nhất listener `classifyAndDecide` nhận `OrderPlaced` in ra.
- Listener trả `List.of(sizeEvent, decisionEvent)`: Spring phát phần tử đầu tiên, nên `onSize` in `B`.
- Spring tiếp tục phát phần tử thứ hai. `onDecision` in `C` rồi trả về `ReviewPathSelected`; Spring phát event cấp hai đó, khiến `onPath` in `D`.
- Sau khi các listener đồng bộ kết thúc, `publishEvent(...)` trả về và mã `main` in `END`.

**Giới hạn của ví dụ:** không có giao dịch database, không dùng `@Async`, không có listener cạnh tranh cùng loại, không đăng ký custom multicaster. Nếu thêm async hoặc thay cơ chế dispatch, không được coi chính thứ tự stdout này là bảo đảm toàn cục cho ứng dụng.

## 5. Collection và array: giống nhau ở publication, khác nhau ở cách biểu diễn

Để trả về nhiều event, hai dạng được Spring hỗ trợ trực tiếp là `Collection` và mảng. Chọn dựa vào khả năng diễn đạt:

### 5.1. Trả về List

~~~java
@EventListener
public List<Object> handle(PaymentConfirmed event) {
    return List.of(
        new ReceiptReady(event.paymentId()),
        new LoyaltyPointsReady(event.paymentId()));
}
~~~

*Đoạn minh họa trong Spring bean; `PaymentConfirmed`, `ReceiptReady`, `LoyaltyPointsReady` là kiểu giả định, cần được định nghĩa trước khi dùng.*

`List` giữ thứ tự các phần tử theo vị trí, dễ sinh động số lượng event bằng `ArrayList` và dễ kiểm thử. Một method có thể trả `List<ReceiptReady>` nếu chỉ sinh event cùng type; `List<Object>` có thể chứa nhiều type.

### 5.2. Trả về mảng

~~~java
@EventListener
public Object[] handleBatch(BatchAccepted event) {
    return new Object[] {
        new BatchIndexed(event.batchId()),
        new BatchAuditCreated(event.batchId())
    };
}
~~~

*Đoạn tích hợp minh họa; `BatchAccepted` và các event tạo ra là các lớp/record nghiệp vụ do ứng dụng định nghĩa.*

Array cũng giữ thứ tự chỉ số, có số phần tử cố định tại thời điểm trả. Nếu các phần tử có nhiều type, dùng `Object[]`; nếu cùng type, có thể dùng `EventType[]`.

### 5.3. Trả về không có event nào

~~~java
@EventListener
public List<Object> onOrderPlaced(OrderPlaced event) {
    if (event.itemCount() == 0) {
        return List.of();
    }
    return List.of(new OrderSizeClassified(
        event.orderId(), "NON_EMPTY"));
}
~~~

*Đoạn trên minh họa, không thay thế method trong ví dụ chạy ở phần 4. Trường hợp đơn 0 sản phẩm nên được coi không hợp lệ ở tầng nghiệp vụ nếu đó là ràng buộc của hệ thống.*

Một danh sách rỗng nghĩa là không có event tiếp theo. Có thể trả `null` để không phát event nhưng thường nên dùng một kết quả dễ hiểu và thiết kế rõ ràng khi code làm việc với collection. Đừng dùng `List.of(null)` vì nó ném `NullPointerException`.

### 5.4. Không nhầm Collection payload với Collection return value

~~~java
// Case A: Trả về collection từ listener => nhiều event.
@EventListener
public List<ReportReady> onBatch(BatchCreated event) {
    return List.of(
        new ReportReady("R-1"),
        new ReportReady("R-2"));
}
~~~

*Các lớp trong đoạn trên là kiểu minh họa.*

Với Case A, Spring phát **hai `ReportReady` event**. Nếu yêu cầu một event duy nhất chứa danh sách báo cáo, hãy thiết kế **wrapper event**:

~~~java
public record ReportsReady(List<String> reportIds) {
    public ReportsReady {
        reportIds = List.copyOf(reportIds);
    }
}

@EventListener
public ReportsReady onBatch(BatchCreated event) {
    return new ReportsReady(List.of("R-1", "R-2"));
}
~~~

Đây là **một event `ReportsReady`** có một thuộc tính collection, thay vì hai event riêng. Sự phân biệt này ảnh hưởng trực tiếp đến số lần listener downstream được gọi.

## 6. Event chaining, fan-out và vấn đề thứ tự

### Fan-out

**Một event đầu vào → nhiều event đầu ra**. Ví dụ `OrderPlaced` tạo hai thông tin phát sinh độc lập: phân loại đơn và quyết định có cần review. Điều này cho phép tách các consumer theo trách nhiệm:

~~~text
OrderPlaced
   |
   v
Producer listener
   |---> OrderSizeClassified ---> MetricsListener
   |
   +---> ReviewDecisionCalculated ---> ReviewListener
~~~

### Chaining

**Một event đầu ra → một listener khác → thêm event mới**. Ví dụ `ReviewDecisionCalculated` dẫn tới `ReviewPathSelected`. Có thể tạo thành pipeline sự kiện nhiều tầng:

~~~text
OrderPlaced
  -> ReviewDecisionCalculated
       -> ReviewPathSelected
            -> ReviewQueueEntryCreated
~~~

Tên `ReviewQueueEntryCreated` trong ví dụ chỉ hợp lệ nếu có bước thật sự tạo queue entry thành công trước khi phát event; **không dùng tên sự thật đã xảy ra khi mới chỉ có ý định thực hiện**.

### Sự khác nhau với xử lý tuần tự imperative

Lời gọi `eventPublisher.publishEvent(...)` tạo **liên kết ẩn** giữa các bean: người phát không gọi trực tiếp một method nghiệp vụ cụ thể. Lợi ích là mở rộng dễ, nhưng chi phí là khó lần theo đường thực thi, xử lý lỗi và kiểm thử nếu có quá nhiều tầng.

Nếu nghiệp vụ **bắt buộc** phải chạy các bước theo thứ tự, kết quả của bước trước quyết định bước sau, và có rollback/compensation phức tạp, một application service điều phối trực tiếp (hoặc workflow engine khi cần) có thể rõ ràng hơn một chuỗi listener đệ quy.

**`@Order` chỉ giúp sắp xếp những listener cùng nhận một event** theo contract của Spring; nó không có nghĩa một chuỗi fan-out phức tạp trở thành một giao dịch tuần tự bền vững. Với executor hoặc xử lý async, bảo đảm thứ tự còn phải được thiết kế ở hệ thống xử lý.

## 7. Cạm bẫy vòng lặp: phát lại chính kiểu event đầu vào

Một lỗi nguy hiểm:

~~~java
@EventListener
public OrderPlaced onOrderPlaced(OrderPlaced event) {
    return event; // Phát lại chính event kiểu OrderPlaced.
}
~~~

*Đoạn code này minh họa anti-pattern, không phải ví dụ nên chạy.*

Với cơ chế event synchronous mặc định, khi nhận `OrderPlaced`, listener trả về `OrderPlaced`, Spring lại phát `OrderPlaced` và gọi **cùng listener**; vòng lặp này có thể tiếp tục cho đến khi bị lỗi đệ quy/stack overflow hoặc chạm cơ chế bảo vệ do ứng dụng tự xây dựng.

Tương tự, chuỗi hai event có thể tạo vòng:

~~~text
A --> listener(A) returns B
B --> listener(B) returns A
A --> ...
~~~

Cách phòng tránh:

1. Xây dựng đồ thị event type có hướng, phân biệt event gốc và event dẫn xuất.
2. Không để event đầu ra của một listener kích hoạt chính listener đó, trừ khi có điều kiện dừng được kiểm tra và bảo đảm.
3. Nếu cần nhiều vòng xử lý, dùng explicit state machine/workflow có trạng thái chuyển tiếp và giới hạn số lần.
4. Đưa `eventId`, correlation/causation và trạng thái xử lý phù hợp để theo dõi chuỗi.
5. Với hệ thống broker hoặc công việc có retry, áp dụng idempotency, dead-letter queue, giới hạn retry và quan sát vòng lặp.

**Không cố “giải quyết” vòng lặp bằng cách chuyển sang `@Async`.** Khi đó chỉ biến thành vòng lặp ở nhiều task/thread thay vì xử lý tận gốc điều kiện lặp.

## 8. Giới hạn đặc biệt của @Async

Tài liệu `@EventListener` quy định **asynchronous listener method không thể phát tiếp event chỉ bằng return value**. Nếu listener có `@Async` và cần tạo event tiếp theo, phải tiêm `ApplicationEventPublisher` và gọi `publishEvent(...)` rõ ràng.

Mẫu phù hợp:

~~~java
@Component
class AsyncOrderListener {

    private final ApplicationEventPublisher publisher;

    AsyncOrderListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Async
    @EventListener
    public void afterOrderPlaced(OrderPlaced event) {
        OrderSizeClassified size = new OrderSizeClassified(
                event.orderId(), "LARGE");
        publisher.publishEvent(size);
    }
}
~~~

*Đây là đoạn minh họa Spring bean: cần import `@Component`, `@Async`, `@EventListener` và `ApplicationEventPublisher`; `OrderPlaced`/`OrderSizeClassified` phải được định nghĩa, và ứng dụng cần bật `@EnableAsync` cùng executor phù hợp. Đây không phải mã độc lập để chạy.*

Không nên mong rằng:

~~~java
@Async
@EventListener
public List<Object> afterOrderPlaced(OrderPlaced event) {
    return List.of(new OrderSizeClassified(event.orderId(), "LARGE"));
}
~~~

sẽ tự phát lại `OrderSizeClassified`. Cấu hình async thay đổi cách gọi phương thức và xử lý kết quả. Spring tài liệu hóa rõ **return-value publication không được hỗ trợ đối với asynchronous listener**. Mẫu có `return List` ở trên chỉ để giải thích điều **không nên dựa vào**, không phải thiết kế đề xuất.

Các khác biệt liên quan đến async:

| Khía cạnh | Listener đồng bộ mặc định | `@Async` listener |
| --- | --- | --- |
| Ngữ cảnh chạy | Thường trong thread phát event. | Trong thread của executor. |
| Trả về event / collection để publish | **Được hỗ trợ**. | **Không được hỗ trợ**. |
| Cách phát event kế tiếp | Trả về kết quả hoặc gọi publisher. | Gọi `ApplicationEventPublisher.publishEvent(...)` trực tiếp. |
| Ngoại lệ | Có thể truyền ngược tới publisher nếu chưa được bắt. | Không tự quay lại thread gọi; phải cấu hình quản lý exception. |
| ThreadLocal transaction / logging | Có thể nhìn thấy ngữ cảnh thread hiện tại trong xử lý đồng bộ. | Không tự chuyển đầy đủ sang thread khác. |
| Thứ tự kết thúc | Theo stack đồng bộ trong ví dụ đơn giản. | Không nên kỳ vọng thứ tự hoàn thành nếu không điều phối. |

Chỉ riêng việc multicaster được cấu hình với executor cũng có thể làm thay đổi thời điểm dispatch. Vì vậy ví dụ xác định stdout ở phần 4 áp dụng cho multicaster mặc định, không phải mọi cấu hình listener trong hệ thống production.

## 9. Liên hệ với transaction: nhiều event không bằng nhiều commit

Giả sử một `@Transactional` service phát `OrderPlaced` và listener đồng bộ trả lại hai event `A` và `B`. Nếu tất cả chạy **trong cùng thread và cùng transaction hiện hành**, các listener downstream có thể tham gia transaction đó theo cấu hình transaction manager.

~~~text
@Transactional service
   |
   | thay đổi DB (chưa commit)
   | publishEvent(OrderPlaced)
   |    -> fanOut returns [A, B]
   |       -> listener(A) (có thể đang trong transaction hiện hành)
   |       -> listener(B) (có thể đang trong transaction hiện hành)
   |
   | service kết thúc
   v
Transaction manager commit hoặc rollback
~~~

Nhưng “return ra hai event” **không tự mở hai transaction mới**, không tự commit sau mỗi event và không bảo đảm rằng những listener có side effect sẽ rollback đồng nhất trong mọi cấu hình (ví dụ hệ thống bên ngoài, async, hoặc propagation khác).

### BEFORE_COMMIT và AFTER_COMMIT

Nếu yêu cầu phát event **chỉ sau khi transaction gốc đã commit thành công**, có thể dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` cho logic phản ứng. Tuy nhiên:

- Lúc `AFTER_COMMIT`, commit gốc đã xong. Các thao tác ghi database bổ sung cần transaction mới rõ ràng, thường `REQUIRES_NEW` trong mô hình imperative khi phù hợp.
- Hãy tách việc **chọn thời điểm** xử lý với việc **phát ra nhiều event**. Không coi một chuỗi event sau commit là phần còn lại của commit cũ.
- Không sử dụng `@Async` để giả lập transaction boundary; async đổi thread và không tự kế thừa transaction từ publisher.
- `@TransactionalEventListener` mặc định chỉ thực thi khi có transaction phù hợp, trừ khi dùng `fallbackExecution = true`.

Cần kiểm thử các đường commit/rollback trên hệ thống thật nếu dùng `@TransactionalEventListener` kết hợp fan-out; không suy ra cam kết bền vững chỉ từ tên annotation.

## 10. “Phát lại” (re-publish) khác “replay” lịch sử

Trong chủ đề “Phát lại và chuỗi event”, hai khái niệm rất dễ bị dùng lẫn nhau:

**Re-publish / publish derived event:** listener trả về một hoặc nhiều đối tượng để Spring **phát các event mới ngay trong thời gian ứng dụng đang chạy**. Ví dụ `OrderPlaced` → `OrderSizeClassified` + `ReviewDecisionCalculated`. Đó là cơ chế đang học.

**Replay:** đọc lại các event **đã lưu từ trước** (event store, log, outbox hoặc broker) rồi áp dụng lại cho consumer để tái dựng projection/khôi phục trạng thái. Spring Application Events mặc định **không tự lưu lịch sử event, không có offset, không có API phát lại toàn bộ event cũ**.

Hai hành vi có thể tương tác: khi một hệ thống ngoài Spring lấy `OrderPlaced` lịch sử và gọi `publisher.publishEvent(...)`, listener fan-out sẽ tạo lại các event dẫn xuất, trừ khi thiết kế logic khác cho chế độ replay. Điều đó có thể:

- Tạo lại side effect cũ như gửi email, cộng điểm thưởng, gọi API thanh toán.
- Tạo trùng bản ghi khi database/repository không có khóa idempotency.
- Tạo event mới với ID/timestamp khác, khiến audit trail khó phân biệt nguyên nhân phát.
- Gây chênh lệch nếu thuật toán fan-out đã thay đổi giữa phiên bản lịch sử và hiện tại.

**Không phát lại một event mà mặc định tất cả listener đều “an toàn để chạy lại”.** Với event store hoặc broker cần định nghĩa rõ replay policy, idempotency key, việc có chạy external side effect không, và phiên bản contract/algorithm dùng để tái dựng dữ liệu.

### Ví dụ quy tắc idempotency

Nếu handler `PaymentCaptured` lưu dòng audit tương ứng với `eventId`, có thể đặt unique constraint trên `(consumerName, eventId)` và xử lý duplicate cùng transaction thích hợp. Nếu cùng một event được giao lại, consumer kiểm tra/ghi nhận xử lý để không tạo tác dụng phụ hai lần.

Tuy nhiên, “kiểm tra đã tồn tại, rồi mới insert” không có ràng buộc/transaction thích hợp vẫn có race condition. Với side effect bên ngoài như gửi email, thường cần outbox/inbox, khóa idempotency ở đối tác hoặc cơ chế phân phối đã được thiết kế để chịu retry.

## 11. Ngoại lệ và tính “partial fan-out”

Giả sử listener trả về hai event `A` và `B`, mỗi event có handler riêng.

Trong multicaster mặc định đồng bộ, nếu handler của `A` ném exception chưa được xử lý:

~~~text
OriginalEvent
    |
    +--> returns [A, B]
                |
                +--> publish A
                         |
                         +--> handler(A) throws exception
                |
                +--> publish B  [có thể KHÔNG diễn ra]
~~~

Vì việc phát danh sách theo thứ tự nằm trong đường gọi đồng bộ, exception có thể làm quá trình xử lý dừng trước khi Spring phát `B`. Điều này tạo **partial fan-out**: một event đã được phát/được xử lý, event còn lại chưa.

Cách xử lý phụ thuộc yêu cầu:

- Nếu cả hai bước phải thành công hoặc cùng rollback, cân nhắc xử lý trong một application service/transaction phù hợp, thay vì coi event fan-out là giao dịch phân tán.
- Nếu mỗi bước độc lập và cần retry, cân nhắc giao qua hàng đợi/outbox bền vững và consumer idempotent.
- Nếu muốn tiếp tục dù một listener lỗi, cần cấu hình `ErrorHandler` của multicaster có chủ đích và giám sát lỗi; đừng chỉ nuốt exception im lặng.
- Nếu sau đó replay input event, phải bảo đảm những bước đã chạy không tạo side effect trùng.

**Không có bảo đảm atomic publication** cho nhiều phần tử return trong Spring Application Events mặc định: trả về một `List` không biến nó thành một transaction message batch.

## 12. Khi nào nên return Collection, khi nào nên publishEvent thủ công?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Một listener đồng bộ tạo ra vài event dẫn xuất ngắn gọn | Trả về `List<?>` hoặc mảng từ `@EventListener`. |
| Một listener trả về đúng một event dẫn xuất | Trả về một đối tượng event. |
| Không có event khi điều kiện không phù hợp | Trả `List.of()`/mảng rỗng hoặc `null` khi return type cho phép và quy ước rõ. |
| Nhiều event cùng type | `List<SomeEvent>` hoặc `SomeEvent[]`. |
| Nhiều event khác type | `List<Object>` hoặc `Object[]`. |
| Xử lý listener bằng `@Async` | Tiêm `ApplicationEventPublisher` và phát từng event bằng lời gọi rõ ràng. |
| Cần phát event ở các thời điểm khác nhau trong cùng method | Dùng `publishEvent(...)` tường minh đúng vị trí, không thể đạt được bằng một return value cuối method. |
| Cần điều phối nghiệp vụ nghiêm ngặt hoặc atomic state changes | Application service/transaction/workflow; event chỉ là tín hiệu phụ trợ. |
| Cần bảo đảm giao message qua tiến trình hoặc replay lịch sử | Broker/outbox/event store kèm contract, retry và idempotency. |

### So sánh hai phong cách

**Trả về collection:**

~~~java
@EventListener
public List<Object> onSource(SourceEvent e) {
    return List.of(new EventA(e.id()), new EventB(e.id()));
}
~~~

**Phát tường minh:**

~~~java
@EventListener
public void onSource(SourceEvent e) {
    publisher.publishEvent(new EventA(e.id()));
    publisher.publishEvent(new EventB(e.id()));
}
~~~

*Hai đoạn là minh họa; các kiểu event và bean `publisher` phải được định nghĩa. Trong phong cách thứ hai, tiêm `ApplicationEventPublisher` vào Spring bean.*

Hai phong cách có thể cho kết quả tương tự trong một ứng dụng đơn giản với listener đồng bộ, nhưng **thời điểm publish khác nhau**: return-value publication chỉ xảy ra sau khi method listener trả về; lời gọi publish thủ công xảy ra ngay tại vị trí tương ứng trong method. Điều này ảnh hưởng tới xử lý lỗi, transaction, thay đổi state và thứ tự quan sát được.

Đừng coi callback return-value như một API phản hồi kết quả cho publisher. `publishEvent(...)` trả `void`; event mới được Spring phát qua multicaster chứ không trở thành return value của caller gốc.

## 13. Kiểm thử chuỗi event và chẩn đoán trong thực tế

Một bộ kiểm thử hợp lý cho listener trả nhiều event nên xác minh:

1. Đầu vào đúng kiểu chỉ gọi listener tương ứng.
2. Một `List` hai phần tử dẫn tới **hai lần phát** theo đúng kiểu event, không phải một event có payload list.
3. Một phần tử event downstream có thể tạo một event cấp tiếp theo khi cần.
4. `List.of()` không phát thêm event.
5. Điều kiện nghiệp vụ cho từng loại event đúng với payload đầu vào.
6. Không có chuỗi A → B → A vô hạn.
7. Nếu có transaction, đường rollback và commit đúng theo semantics dự kiến.
8. Nếu dùng async, test hoàn tất qua synchronization/await, không assert thứ tự thread ngẫu nhiên.
9. Nếu có retry/replay, consumer không tạo side effect trùng cho cùng `eventId`.
10. Lỗi ở handler đầu tiên không làm hệ thống ghi nhận nhầm rằng tất cả derived events đã hoàn tất.

Có thể viết kiểm thử Spring tích hợp tạo `AnnotationConfigApplicationContext` như phần 4 và thay các `System.out.println(...)` bằng một collector/test probe (ví dụ `List` được đồng bộ hóa hoặc `BlockingQueue` nếu cần async). Sau khi gọi `publishEvent(...)` trong cấu hình **đồng bộ**, assert số lượng/kiểu event nhận được và các trạng thái đã cập nhật. Nếu muốn kiểm thử khả năng chạy lại, phát cùng input hai lần rồi assert logic xử lý duplicate theo quy ước nghiệp vụ.

### Logging và tracing

Để hiểu event chain dài, nên ghi tối thiểu:

- `eventType` và `eventId` của từng occurrence, tránh lẫn với aggregate ID.
- `correlationId` để nối các event có chung nghiệp vụ.
- `causationId` của event cha nếu có chuỗi dẫn xuất.
- `handler`, phase giao dịch (nếu có), thời điểm bắt đầu/kết thúc và outcome.
- Cảnh báo khi một chuỗi có độ sâu hoặc số lượng event bất thường.

Không log toàn bộ payload chứa dữ liệu nhạy cảm. Với việc gọi external service, thêm timeout, metric và retry/idempotency tường minh thay vì trông chờ event nội bộ tự quản lý lỗi.

## 14. Những lỗi phổ biến cần tránh

1. **Tưởng `List<Event>` là một event duy nhất.** Return `Collection` trong `@EventListener` làm Spring phát từng phần tử. Nếu cần một event chứa list, đặt list vào wrapper payload.
2. **Đặt `@Async` và vẫn mong Spring tự publish return value.** Không được hỗ trợ; gọi publisher thủ công.
3. **Tạo vòng lặp event types.** Một listener trả chính type đầu vào hoặc tạo A → B → A mà không có điều kiện dừng.
4. **Không phân biệt event mới và event replay.** Return-value publication không mang lại lịch sử event hay cơ chế retry.
5. **Phụ thuộc vào thứ tự nhiều listener trong cấu hình async.** Cần thiết kế điều phối/ordering riêng.
6. **Đưa entity JPA mutable làm payload cho nhiều listener.** Các handler có thể thấy dữ liệu bị sửa ngoài dự kiến hoặc gặp vấn đề khi transaction/session hết hạn.
7. **Tin rằng phát thành công đồng nghĩa nghiệp vụ đã commit.** Event sync có thể xảy ra trước transaction commit; async còn có transaction context khác.
8. **Bỏ qua exception của listener con.** Nếu listener downstream ném lỗi, publish phần tử tiếp theo có thể bị ngắt; phải có policy lỗi.
9. **Trả `HashSet` rồi đòi thứ tự publication cố định.** Dùng `List` hoặc mảng nếu thứ tự phần tử quan trọng.
10. **Giả định mọi derived event đều được giao bền vững.** Event multicast trong JVM không phải durable broker; cần outbox/queue khi nghiệp vụ không được phép mất.
11. **Để nhiều listener lén sửa cùng trạng thái.** Fan-out là công cụ tách quan tâm, không thay thế transaction coordination nếu cần invariant chặt.
12. **Nhầm return của `@EventListener` với return của `ApplicationEventPublisher.publishEvent(...)`.** Publisher không trả kết quả event chain cho caller; việc trả về được framework dùng để tạo event mới.

## 15. Bài tập tự kiểm tra

**Câu 1.** Một `@EventListener` trả về `List.of(new A(), new B())`. Spring phát bao nhiêu event?

**Đáp án:** Hai event riêng, một cho đối tượng `A` và một cho đối tượng `B`. Các listener đăng ký với từng loại được gọi nếu cấu hình phù hợp.

**Câu 2.** Nếu muốn phát đúng **một event** mang danh sách 10 ID, nên return `List<String>` trực tiếp từ listener không?

**Đáp án:** Không. Với return-value publication, các phần tử của collection được phát riêng. Nên định nghĩa một wrapper như `IdsReady(List<String> ids)` rồi trả về một đối tượng `IdsReady`.

**Câu 3.** Tại sao ví dụ chạy ở phần 4 in `D: Path MANUAL` trước `END`?

**Đáp án:** Listener đồng bộ `onDecision(...)` trả tiếp `ReviewPathSelected`; framework phát event đó và chạy `onPath(...)` trước khi toàn bộ `publishEvent(OrderPlaced)` ban đầu trả về.

**Câu 4.** Một listener `@Async @EventListener` có thể trả `List<Object>` để Spring tự phát các event trong danh sách không?

**Đáp án:** Không. Tài liệu Spring quy định không hỗ trợ phát tiếp event bằng return value của asynchronous listener. Phải dùng `ApplicationEventPublisher` rõ ràng.

**Câu 5.** Nếu listener của event `A` ném exception trước khi publisher phát `B`, có bảo đảm `B` vẫn được phát không?

**Đáp án:** Không. Trong cơ chế synchronous mặc định, exception chưa xử lý có thể ngắt việc phát các phần tử còn lại. Cần xây dựng xử lý lỗi phù hợp.

**Câu 6.** Việc listener trả một collection có nghĩa Spring đã lưu cả collection vào event store để replay sau khi JVM khởi động lại không?

**Đáp án:** Không. Nó chỉ phát các event dẫn xuất cho multicaster hiện tại; nếu cần replay bền vững, hệ thống phải lưu, phân phối và quản lý ID/version riêng.

**Câu 7.** Với `List.of(new A(), new B())`, làm sao để listener nhận `B` tạo thêm `C`?

**Đáp án:** Một bean có `@EventListener` nhận `B` và trả về đối tượng `C`; Spring sẽ tiếp tục phát `C` tới các listener phù hợp, tạo event chain nhiều tầng.

## Tài liệu tham khảo

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `@EventListener`, trả về event, hỗ trợ collection/array, thứ tự và giới hạn async.
- [Spring Framework Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html): quy tắc xử lý return value và ngoại lệ của asynchronous listener.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): `publishEvent(Object)` và cơ chế event payload.
- [Spring Framework Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): phân phối sync mặc định và cấu hình executor/error handling.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và các phase commit/rollback.
