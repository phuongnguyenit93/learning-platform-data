# Phát hiện listener phù hợp trong Spring Framework Application Events

## 1. Mục tiêu của việc phát hiện listener

Khi một bean gọi `ApplicationEventPublisher.publishEvent(event)`, Spring phải xác định **listener nào có thể nhận loại sự kiện đó**, sau đó chuyển sự kiện đến các listener đã chọn. Cùng một `ApplicationContext` có thể chứa nhiều listener dành cho thanh toán, tồn kho, giao vận, auditing hoặc các sự kiện vòng đời của chính Spring. Nếu chuyển mọi sự kiện đến mọi listener, ứng dụng vừa lãng phí công việc vừa dễ xử lý sai kiểu dữ liệu.

Trong Spring, thành phần thực hiện phân phối là `ApplicationEventMulticaster`. Triển khai thông dụng là `SimpleApplicationEventMulticaster`, kế thừa khả năng quản lý và **tìm danh sách listener phù hợp** từ `AbstractApplicationEventMulticaster`.

Ví dụ nghiệp vụ:

- `PaymentReceived`: listener thanh toán cần nhận; listener tồn kho không cần nhận.
- `InventoryLow`: listener tồn kho cần nhận; listener thanh toán không cần nhận.
- Hai sự kiện `PaymentReceived` có cùng kiểu Java nhưng khác kiểu `source`: một listener có thể đăng ký chỉ nhận các sự kiện xuất phát từ `CheckoutSource`.
- Trong những listener đã khớp kiểu, một phương thức `@EventListener(condition = "...")` vẫn có thể bỏ qua sự kiện nếu điều kiện nghiệp vụ không thỏa.

**Cần phân biệt rõ:** "được tìm thấy trong danh sách listener phù hợp" là bước chọn ứng viên theo loại sự kiện và, khi có hỗ trợ, kiểu nguồn. "Phương thức thật sự chạy" còn phụ thuộc điều kiện annotation, pha transaction, cấu hình thực thi và những yếu tố khác.

## 2. Đường đi từ publisher đến listener

Ở mức khái niệm, luồng đồng bộ mặc định là:

```text
Một bean gọi publishEvent(event)
         |
         v
ApplicationContext
         |
         v
ApplicationEventMulticaster.multicastEvent(...)
         |
         v
Lấy các listener đã đăng ký
         |
         v
Đối chiếu event type / source type
         |
         v
Danh sách listener phù hợp
         |
         v
Gọi listener (và kiểm tra condition/phase nếu có)
```

Các vai trò chính:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ApplicationEventPublisher` | API để mã ứng dụng công bố một sự kiện |
| `ApplicationEventMulticaster` | Điều phối việc tìm và gọi các listener |
| `AbstractApplicationEventMulticaster` | Quản lý tập listener, chọn ứng viên và hỗ trợ cache kết quả tra cứu |
| `SimpleApplicationEventMulticaster` | Triển khai multicast phổ biến; mặc định gọi listener đồng bộ nếu không cấu hình executor |
| `ApplicationListener<E>` | Listener theo kiểu sự kiện `E`, trong đó `E extends ApplicationEvent` |
| `GenericApplicationListener` | Listener kiểm tra được `ResolvableType` của event và kiểu `source` |
| `@EventListener` | Khai báo phương thức xử lý; Spring tạo adapter listener để tham gia cơ chế phân phối |

Sơ đồ là mô hình dễ hiểu, không phải cam kết về mọi lớp nội bộ hay thứ tự gọi trong mọi bản phát hành Spring. Đặc biệt, một listener phương thức có thể **được chọn trước** rồi mới đánh giá biểu thức `condition` khi adapter chuẩn bị gọi phương thức đích.

## 3. Listener được đăng ký vào đâu?

Một listener chỉ có thể được tìm nếu Spring đã biết đến nó.

### 3.1. Bean triển khai `ApplicationListener<E>`

```java
@Component
public class PaymentAuditListener
        implements ApplicationListener<PaymentReceived> {

    @Override
    public void onApplicationEvent(PaymentReceived event) {
        // Ghi audit sự kiện thanh toán.
    }
}
```

Đoạn minh họa trên giả định `PaymentReceived extends ApplicationEvent`. Với bean nằm trong component scan của `ApplicationContext`, Spring tự phát hiện và đăng ký listener. Bạn cũng có thể khai báo một bean trả về `ApplicationListener<PaymentReceived>` bằng `@Bean`.

Kiểu generic `PaymentReceived` là một phần quan trọng để Spring xác định event type được hỗ trợ. Tránh triển khai `ApplicationListener` ở dạng **raw type** nếu không có lý do cụ thể, vì việc suy luận loại sự kiện dễ trở nên không rõ ràng.

### 3.2. Phương thức đánh dấu `@EventListener`

```java
@Component
public class PaymentNotifications {

    @EventListener
    public void onPayment(PaymentReceived event) {
        // Thông báo khi nhận PaymentReceived.
    }
}
```

Lớp này không cần triển khai `ApplicationListener`. Trong quá trình khởi tạo context, cơ chế xử lý annotation `@EventListener` phát hiện các phương thức phù hợp và đăng ký adapter để multicaster có thể sử dụng. Kiểu tham số phương thức giúp Spring suy ra loại event quan tâm.

Đối với các đối tượng Java không kế thừa `ApplicationEvent`, Spring vẫn hỗ trợ `publishEvent(Object)`: event có thể được bọc thành `PayloadApplicationEvent`. Phương thức `@EventListener` nhận **kiểu payload** vẫn có thể được chọn. Ngược lại, giao diện `ApplicationListener<E>` yêu cầu `E` là một `ApplicationEvent`; nếu muốn nghe payload bằng giao diện này, phải xử lý dạng sự kiện bọc tương ứng.

### 3.3. Đăng ký bằng API multicaster

Một `ApplicationEventMulticaster` cũng có các API như `addApplicationListener(...)` và `addApplicationListenerBean(...)`. Ứng dụng thường để `ApplicationContext` đăng ký tự động thay vì trực tiếp điều khiển multicaster. Đăng ký tay hữu ích trong tích hợp đặc biệt, nhưng cần quản lý vòng đời và loại bỏ listener khi không dùng nữa. Đừng tự đăng ký trùng một listener đang được Spring quản lý.

**Lưu ý về phạm vi:** các listener gắn với `ApplicationContext` tương ứng. Nếu ứng dụng có context cha/con, phải xét nơi phát sự kiện và cách event lan truyền giữa các context; không mặc định mọi listener trên toàn bộ ứng dụng đều nằm trong cùng một danh sách.

## 4. Spring xác định "phù hợp" dựa trên những tiêu chí nào?

### 4.1. Kiểu sự kiện

Ví dụ `ApplicationListener<PaymentReceived>` quan tâm `PaymentReceived`; `ApplicationListener<InventoryLow>` quan tâm `InventoryLow`. Spring sử dụng thông tin kiểu có thể phân giải được, thay vì chờ đến khi mã listener ép kiểu rồi mới biết có phù hợp hay không.

Kiểu kế thừa cũng quan trọng: một listener khai báo kiểu sự kiện cha có thể phù hợp với sự kiện con. Điều này có thể hữu ích cho audit chung, nhưng cũng khiến listener nhận nhiều sự kiện hơn dự định.

Đối với generic event phức tạp, Spring dùng `ResolvableType` để biểu diễn thông tin kiểu chi tiết khi có thể. Tuy nhiên, generic Java bị xóa kiểu lúc chạy; nếu Spring không biết đủ kiểu từ lớp sự kiện hoặc metadata, cần thiết kế event/`ResolvableTypeProvider` phù hợp. Không nên nghĩ `List<OrderPaid>` và `List<OrderCancelled>` luôn phân biệt được tại runtime chỉ vì generic được ghi trong mã nguồn.

### 4.2. Kiểu nguồn (`source type`)

Một `ApplicationEvent` có `getSource()`. Listener có thể phân biệt **lớp Java của đối tượng nguồn** bằng `supportsSourceType(Class<?> sourceType)` nếu triển khai giao diện hỗ trợ như `GenericApplicationListener` hoặc `SmartApplicationListener`.

Ví dụ:

```java
@Override
public boolean supportsSourceType(Class<?> sourceType) {
    return sourceType != null
            && CheckoutSource.class.isAssignableFrom(sourceType);
}
```

Đoạn này chỉ phù hợp khi nguồn là `CheckoutSource` hoặc kiểu con. Đây là **lọc theo kiểu của `source`**, không phải lọc theo thuộc tính như `checkoutId`, `tenantId` hay chuỗi `sourceName`. Nếu muốn xét dữ liệu bên trong source, dùng điều kiện nghiệp vụ ở một lớp xử lý thích hợp.

### 4.3. Điều kiện `@EventListener(condition)`

```java
@EventListener(condition = "#p0.paymentId() == 'P-101'")
public void onSelectedPayment(PaymentReceived event) {
    // Chỉ chạy với paymentId P-101.
}
```

Phương thức này là listener của **kiểu** `PaymentReceived`. Nó có thể xuất hiện trong tập listener được multicaster chọn cho `PaymentReceived`, nhưng adapter chỉ gọi phương thức khi biểu thức SpEL trả về `true`. `#p0` nghĩa là tham số đầu tiên; cách viết này không phụ thuộc việc lưu tên tham số khi biên dịch.

Vì thế, khi debug, cần hỏi hai câu riêng:

1. Listener đã **được đăng ký và khớp kiểu event/source** chưa?
2. Sau khi chọn, nó có **được phép chạy** theo condition, pha transaction và cách thực thi hiện tại không?

## 5. Ví dụ chạy được: loại event, kiểu source và condition

Ví dụ sử dụng JDK 17+, Spring Framework 6.2.0 và Maven. Nó chứng minh ba kiểu đăng ký listener trong cùng một ứng dụng, gồm `ApplicationListener<T>`, `@EventListener` và `GenericApplicationListener`.

**Cấu trúc thư mục**

```text
listener-selection-demo/
├── pom.xml
└── src/main/java/example/ListenerSelectionDemo.java
```

**Tệp `pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>listener-selection-demo</artifactId>
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
                    <mainClass>example.ListenerSelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/java/example/ListenerSelectionDemo.java`**

```java
package example;

import java.util.Set;
import java.util.TreeSet;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.GenericApplicationListener;
import org.springframework.core.ResolvableType;

public class ListenerSelectionDemo {

    public record CheckoutSource(String name) {}
    public record WarehouseSource(String name) {}

    public static final class PaymentReceived extends ApplicationEvent {
        private final String paymentId;

        public PaymentReceived(Object source, String paymentId) {
            super(source);
            this.paymentId = paymentId;
        }

        public String paymentId() {
            return paymentId;
        }
    }

    public static final class InventoryLow extends ApplicationEvent {
        private final String sku;

        public InventoryLow(Object source, String sku) {
            super(source);
            this.sku = sku;
        }

        public String sku() {
            return sku;
        }
    }

    // Ghi tập kết quả để trình bày theo thứ tự ổn định.
    // Ví dụ cố ý chạy đồng bộ, không sử dụng async.
    public static final class Evidence {
        private final Set<String> lines = new TreeSet<>();

        public void record(String value) {
            lines.add(value);
        }

        public void print() {
            lines.forEach(System.out::println);
        }
    }

    public static final class AnnotatedListeners {
        private final Evidence evidence;

        public AnnotatedListeners(Evidence evidence) {
            this.evidence = evidence;
        }

        @EventListener
        public void onPayment(PaymentReceived event) {
            evidence.record("annotation: " + event.paymentId());
        }

        @EventListener(condition = "#p0.paymentId() == 'P-101'")
        public void onChosenPayment(PaymentReceived event) {
            evidence.record("condition: " + event.paymentId());
        }

        @EventListener
        public void onInventory(InventoryLow event) {
            evidence.record("inventory: " + event.sku());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Evidence evidence() {
            return new Evidence();
        }

        @Bean
        public AnnotatedListeners annotatedListeners(Evidence evidence) {
            return new AnnotatedListeners(evidence);
        }

        @Bean
        public ApplicationListener<PaymentReceived> typedListener(
                Evidence evidence) {
            return event ->
                    evidence.record("typed: " + event.paymentId());
        }

        @Bean
        public GenericApplicationListener sourceFilteredListener(
                Evidence evidence) {
            return new GenericApplicationListener() {
                @Override
                public boolean supportsEventType(ResolvableType eventType) {
                    return PaymentReceived.class.isAssignableFrom(
                            eventType.toClass());
                }

                @Override
                public boolean supportsSourceType(Class<?> sourceType) {
                    return sourceType != null
                            && CheckoutSource.class.isAssignableFrom(
                                    sourceType);
                }

                @Override
                public void onApplicationEvent(ApplicationEvent event) {
                    PaymentReceived payment = (PaymentReceived) event;
                    evidence.record("generic: " + payment.paymentId());
                }
            };
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new PaymentReceived(
                    new CheckoutSource("web"), "P-101"));

            context.publishEvent(new PaymentReceived(
                    new WarehouseSource("batch"), "P-102"));

            context.publishEvent(new InventoryLow(
                    new WarehouseSource("warehouse"), "SKU-7"));

            context.getBean(Evidence.class).print();
        }
    }
}
```

**Lệnh chạy:** từ thư mục chứa `pom.xml`, sử dụng JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Các dòng do chương trình in** (không tính log của công cụ chạy nếu có):

```text
annotation: P-101
annotation: P-102
condition: P-101
generic: P-101
inventory: SKU-7
typed: P-101
typed: P-102
```

`TreeSet` chỉ dùng trong ví dụ để sắp xếp và in kết quả ổn định; **không đại diện cho trình tự thật của các listener**, không phù hợp để đếm các lần giao trùng, và không phải cấu trúc an toàn cho mọi trường hợp bất đồng bộ.

Giải thích từng nhóm kết quả:

- `typedListener` là `ApplicationListener<PaymentReceived>`: nhận cả `P-101` và `P-102`, không nhận `InventoryLow`.
- `onPayment` dùng `@EventListener` với tham số `PaymentReceived`: nhận cả hai thanh toán.
- `onChosenPayment` khớp cùng kiểu sự kiện, nhưng SpEL chỉ cho chạy với `P-101`.
- `sourceFilteredListener` dùng `GenericApplicationListener`: chỉ nhận `PaymentReceived` có source thuộc `CheckoutSource`. Vì thế `P-102` từ `WarehouseSource` không tạo dòng "generic".
- `onInventory` chỉ nhận `InventoryLow` và in `SKU-7`.
- Context tự phát một số sự kiện vòng đời (như lúc refresh hoặc close); những listener được khai báo ở đây không in cho chúng vì không khớp kiểu.

**Tại sao kiểm tra source ở `GenericApplicationListener` là an toàn trong ví dụ?** Phương thức `onApplicationEvent` ép sang `PaymentReceived` chỉ sau khi `supportsEventType` đã kiểm tra kiểu. Nếu sau này mở rộng bộ lọc cho các kiểu sự kiện khác, cần cập nhật cách xử lý/cast tương ứng.

## 6. Từng loại listener được Spring phát hiện như thế nào?

### 6.1. `ApplicationListener<PaymentReceived>`

Từ generic type của bean, Spring biết listener quan tâm loại `PaymentReceived`. Với ví dụ trên, multicaster không cần gọi `onApplicationEvent` cho `InventoryLow` rồi mới để listener tự bỏ qua.

### 6.2. `@EventListener`

Spring tìm các phương thức có annotation trên Spring bean và dùng adapter để đăng ký chúng với hệ thống event. Một phương thức có một tham số event thường dùng kiểu tham số làm loại event quan tâm. Annotation cũng cho phép chỉ định loại event tường minh khi cần:

```java
// Ví dụ minh họa đặt bên trong một Spring bean:
@EventListener(classes = {PaymentReceived.class, InventoryLow.class})
public void onEitherType() {
    // Không nhận đối tượng event trong tham số;
    // chỉ biết một trong hai loại được phát.
}
```

Đây là đoạn minh họa bổ sung, không nằm trong ví dụ chạy mục 5. Khi chỉ định nhiều loại event nhưng không có tham số, phương thức không có dữ liệu để phân biệt loại nào vừa đến, trừ khi ứng dụng có cơ chế riêng. Thông thường, nên dùng các listener có tham số kiểu cụ thể.

### 6.3. `GenericApplicationListener` và `SmartApplicationListener`

`GenericApplicationListener` phù hợp khi điều kiện chọn listener cần hiểu `ResolvableType` hoặc kiểu `source`. Ví dụ `supportsSourceType` là **bộ lọc nguồn** ở giai đoạn tìm listener, không phải SpEL. `SmartApplicationListener` cũng hỗ trợ kiểm tra kiểu event và source, nhưng dùng API theo `Class<? extends ApplicationEvent>` cho loại sự kiện.

Nếu cần một điều kiện phức tạp theo nội dung payload, hãy cân nhắc `@EventListener(condition)` hoặc xử lý điều kiện trong mã Java. `supportsSourceType` chỉ nhận lớp của nguồn, không nhận object event đầy đủ.

## 7. Cache khi tìm listener: lợi ích và giới hạn

`AbstractApplicationEventMulticaster` có thể lưu kết quả tra cứu listener để không phải lọc lại toàn bộ danh sách cho mọi event có cùng đặc điểm tra cứu. Một khóa tra cứu quan trọng được xây dựng từ **loại sự kiện** và **kiểu nguồn**. Ví dụ, nhiều `PaymentReceived` cùng đến từ `CheckoutSource` thường có thể tái sử dụng kết quả chọn ứng viên.

Cần hiểu ba giới hạn:

1. **Cache chọn ứng viên không phải cache kết quả xử lý.** Mỗi lần `publishEvent` vẫn có thể gọi listener tương ứng; không có nghĩa sự kiện chỉ được xử lý một lần.
2. **Không nên nhét dữ liệu biến đổi từng event vào bộ lọc kiểu.** Ví dụ `paymentId == 'P-101'` phải được đánh giá theo từng sự kiện; không thể kết luận mọi `PaymentReceived` từ `CheckoutSource` đều là `P-101` chỉ dựa trên cache.
3. **Kết quả cache là chi tiết triển khai có điều kiện.** Tính cacheable phụ thuộc vào khả năng phân giải kiểu và class loader, và khi đăng ký hay gỡ listener, Spring phải bảo đảm không dùng mãi tập ứng viên cũ.

Bởi vậy, tối ưu đầu tiên là khai báo đúng loại event và source, thay vì tự xây cache cho logic nghiệp vụ trong listener.

## 8. Khi nào listener được chọn nhưng không chạy?

Đây là các trường hợp đặc biệt dễ gây nhầm lẫn:

| Biểu hiện | Khả năng giải thích | Cách kiểm tra |
| --- | --- | --- |
| Phương thức `@EventListener` không chạy | Bean không được đăng ký; sai kiểu tham số; condition trả về false | Kiểm tra component scan/`@Bean`, event type, biểu thức SpEL |
| `GenericApplicationListener` không chạy | `supportsEventType` hoặc `supportsSourceType` trả về false | Ghi nhận loại event và lớp `event.getSource()` khi thử nghiệm |
| `@TransactionalEventListener` không chạy | Không có transaction; `fallbackExecution` mặc định là false; phase không phù hợp | Kiểm thử trong transaction thật ở commit và rollback |
| Đăng ký `ApplicationListener<ParentEvent>` nhận nhiều event | Event con cũng thuộc kiểu cha | Dùng kiểu cụ thể hơn hoặc điều kiện bổ sung |
| Một listener được gọi nhiều lần | Có nhiều lần publish; đăng ký trùng; hệ thống retry | Kiểm tra nơi publish và phạm vi đăng ký |
| Listener bất đồng bộ chưa hoàn thành khi publisher trả về | Executor hoặc `@Async` được cấu hình | Đợi/tích hợp đồng bộ đúng cách trong test, theo dõi lỗi async |
| Phát một POJO nhưng listener theo `ApplicationEvent` không xử lý payload như mong đợi | POJO được bọc thành `PayloadApplicationEvent` | Dùng `@EventListener` tham số payload hoặc listener nhận wrapper thích hợp |

**Lọc kiểu không phải lọc nghiệp vụ.** Ví dụ trong mục 5, `P-102` được chọn cho `onChosenPayment` theo loại `PaymentReceived` nhưng bị bỏ qua ở bước đánh giá condition. Nếu chỉ nhìn số lần phương thức chạy, rất dễ kết luận sai rằng adapter không được đăng ký.

## 9. Thứ tự, đồng bộ và ngoại lệ

Mặc định `SimpleApplicationEventMulticaster` gọi listener ngay trên luồng phát nếu không được cấu hình `TaskExecutor`. Điều đó giúp quy trình dễ quan sát, nhưng **không nên phụ thuộc vào thứ tự mặc định giữa các listener** để bảo đảm bước A đã chạy trước B.

Spring hỗ trợ cơ chế sắp thứ tự như `@Order` và `Ordered` trong các hoàn cảnh phù hợp. Dù vậy, event vẫn là cách thông báo về một việc đã xảy ra. Nếu nghiệp vụ đòi hỏi A thành công rồi mới được chạy B, hãy diễn đạt trình tự đó trong một service/workflow rõ ràng; đừng biến nhiều listener độc lập thành chuỗi xử lý bắt buộc theo thứ tự ngầm định.

Khi cấu hình executor hoặc dùng `@Async`:

- Thời điểm thực thi thay đổi; không mặc định `publishEvent` chờ tất cả callback hoàn tất.
- Một số listener, đặc biệt listener ràng buộc giao dịch, không hỗ trợ thực thi async qua multicaster như listener thông thường.
- Cách truyền lỗi về publisher khác với gọi đồng bộ. Cần cấu hình error handling/quan sát thất bại phù hợp.
- Dữ liệu sự kiện nên bất biến; không dùng entity mutable được cập nhật tiếp như snapshot tin cậy.

Ở chế độ đồng bộ, exception chưa được xử lý trong listener có thể lan về lời gọi publish và làm ngắt quá trình phân phối. Với cơ chế bất đồng bộ, lỗi cần được theo dõi ở luồng thực thi tương ứng; đừng dựa vào `try/catch` quanh publisher để bắt mọi exception của callback.

## 10. Kiểm thử khả năng phát hiện listener

Một bộ kiểm thử nên thể hiện rõ **bộ lọc loại event**, **bộ lọc kiểu source** và **condition theo nội dung**. Từ ví dụ mục 5, ma trận mong đợi:

| Event và source | Typed Payment | Annotation Payment | SpEL `P-101` | Generic Checkout | Inventory |
| --- | --- | --- | --- | --- | --- |
| `PaymentReceived(P-101)` từ `CheckoutSource` | Có | Có | Có | Có | Không |
| `PaymentReceived(P-102)` từ `WarehouseSource` | Có | Có | Không | Không | Không |
| `InventoryLow(SKU-7)` từ `WarehouseSource` | Không | Không | Không | Không | Có |

Kiểm thử nên xác nhận **đúng listener được gọi và listener không phù hợp không được gọi**. Ngoài dữ liệu chính, nên thử một subclass của loại event nếu ứng dụng cần kế thừa, và một source có kiểu khác nhưng cùng giá trị chuỗi hiển thị để phát hiện lỗi dùng nhầm tên nguồn thay cho lớp nguồn.

Đối với `@EventListener(condition)`, cần kiểm thử false case và sự thay đổi thuộc tính event. Nếu test cần đếm lời gọi, dùng counter/spies thay cho `TreeSet` của bản demo (vì tập hợp loại bỏ phần tử trùng). Với listener async, dùng công cụ chờ có giới hạn và cơ chế đồng bộ của test; không khẳng định "không nhận" chỉ vì callback chưa chạy kịp.

Nếu dùng `@TransactionalEventListener`, kiểm thử thêm trường hợp transaction commit, rollback và phát ngoài transaction. Những cơ chế này ảnh hưởng **thời điểm gọi**, ngay cả khi listener đã phù hợp theo event type.

## 11. Checklist khi một listener không nhận sự kiện

1. **Đúng context chưa?** Event được publish vào `ApplicationContext` nào, listener bean nằm trong context nào?
2. **Đúng đăng ký chưa?** Bean có được tạo bởi Spring? Với `@EventListener`, phương thức thuộc Spring bean và có chữ ký thích hợp?
3. **Đúng loại event chưa?** Đang phát subclass của `ApplicationEvent` hay một POJO payload được Spring bọc? Generic type có đủ thông tin để phân giải?
4. **Đúng source type chưa?** `getSource()` là object của lớp nào? `supportsSourceType` có lọc bỏ nó không?
5. **Đúng điều kiện chưa?** SpEL có trả về true đối với event cụ thể này? Có truy cập sai thuộc tính hoặc phụ thuộc tên tham số không?
6. **Đúng transaction phase chưa?** Với listener giao dịch, transaction có thật sự hoạt động và commit/rollback đúng phase mong đợi không?
7. **Đúng thời điểm quan sát chưa?** Nếu callback bất đồng bộ, test/log đã đợi đúng cách và kiểm tra lỗi thực thi chưa?

## 12. Ghi nhớ

Trong Spring Application Events, việc phát hiện listener diễn ra dựa trên **đăng ký listener trong context**, **loại sự kiện**, và **kiểu nguồn** khi listener hỗ trợ điều kiện đó. `ApplicationListener<E>` cung cấp kiểu generic, `@EventListener` được chuyển thành adapter, còn `GenericApplicationListener` cho phép chọn ứng viên theo `ResolvableType` và `source type`. Điều kiện `@EventListener(condition)` được đánh giá cho **từng sự kiện** tại bước xử lý, vì vậy không đồng nhất "listener phù hợp về kiểu" với "phương thức đã thực thi".

**Tài liệu Spring để đối chiếu:**

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Javadoc — ApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [Javadoc — AbstractApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html)
- [Javadoc — GenericApplicationListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/GenericApplicationListener.html)
