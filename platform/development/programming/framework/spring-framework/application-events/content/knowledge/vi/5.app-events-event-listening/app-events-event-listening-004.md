# Listener nhận ApplicationEvent trong Spring Framework

## Mục tiêu

Trong Spring Framework, `ApplicationEvent` là lớp nền cho các sự kiện được phát và phân phối trong một `ApplicationContext`. Khi một class nghiệp vụ kế thừa `ApplicationEvent`, nó có thể mang dữ liệu về điều đã xảy ra, đồng thời giữ lại `source` — đối tượng khởi phát sự kiện. Một listener triển khai `ApplicationListener<E>` có thể khai báo rõ kiểu event mà nó nhận.

Bài học này tập trung vào listener nhận custom event kế thừa `ApplicationEvent`, cách generic type `E` được Spring dùng để chọn listener, ý nghĩa của `source`, và sự khác nhau giữa event class tùy chỉnh với POJO được Spring bọc thành `PayloadApplicationEvent`. Cuối bài có ví dụ Java 17 và Spring Framework 6.2 chạy được bằng Maven.

Sau bài học, bạn có thể:

- Tạo custom event class kế thừa `ApplicationEvent` và cung cấp source hợp lệ.
- Triển khai `ApplicationListener<CustomEvent>` để xử lý đúng kiểu event.
- Giải thích event type matching theo kiểu lớp và generic type.
- Phân biệt custom `ApplicationEvent` với POJO payload và wrapper `PayloadApplicationEvent`.
- Chọn giữa `ApplicationListener<E>` và method listener dùng `@EventListener`.
- Hiểu giới hạn của application event trong phạm vi một tiến trình Spring.

## 1. ApplicationEvent là gì?

`ApplicationEvent` là abstract class của Spring, kế thừa `java.util.EventObject`. Vì vậy, một event class kế thừa nó phải gọi constructor của lớp cha với một `source` khác `null`.

`source` là đối tượng mà event mô tả là nơi khởi phát sự kiện. Ví dụ, khi một `CatalogService` thay đổi giá sản phẩm, event có thể nhận chính instance service đó làm source. Listener truy cập source bằng `getSource()`.

Một custom event thường chứa:

- **Source:** đối tượng khởi phát hoặc sở hữu hành động tạo ra event.
- **Event data:** các giá trị cần thiết để listener hiểu sự việc đã xảy ra.
- **Timestamp:** `ApplicationEvent` lưu thời điểm tạo event và cung cấp qua `getTimestamp()`.

Event nên mô tả sự việc đã xảy ra, chẳng hạn `ProductPriceChangedEvent`, `OrderApprovedEvent` hoặc `CustomerRegisteredEvent`. Tránh đưa cả entity đang được quản lý bởi ORM vào event nếu listener chỉ cần một vài giá trị. ID, giá trị trước/sau hoặc dữ liệu bất biến thường là payload dễ kiểm soát hơn.

### Tạo custom event class

```java
import java.math.BigDecimal;

import org.springframework.context.ApplicationEvent;

public class ProductPriceChangedEvent extends ApplicationEvent {

    private final long productId;
    private final BigDecimal oldPrice;
    private final BigDecimal newPrice;

    public ProductPriceChangedEvent(
            Object source,
            long productId,
            BigDecimal oldPrice,
            BigDecimal newPrice) {
        super(source);
        this.productId = productId;
        this.oldPrice = oldPrice;
        this.newPrice = newPrice;
    }

    public long getProductId() {
        return productId;
    }

    public BigDecimal getOldPrice() {
        return oldPrice;
    }

    public BigDecimal getNewPrice() {
        return newPrice;
    }
}
```

Constructor nhận `Object source` vì nguồn có thể là service, aggregate, component hoặc một đối tượng khác có ý nghĩa với ứng dụng. `super(source)` chuyển source cho `EventObject`; nếu truyền `null`, constructor sẽ ném `IllegalArgumentException`.

Các trường dữ liệu được khai báo `final` để event không bị thay đổi sau khi publish. Điều này giúp nhiều listener có thể đọc cùng một snapshot mà không phải lo một listener sửa dữ liệu trước listener khác.

## 2. ApplicationListener<E> nhận event theo kiểu

`ApplicationListener<E>` là interface listener cốt lõi của Spring:

```java
public interface ApplicationListener<E extends ApplicationEvent> {
    void onApplicationEvent(E event);
}
```

Tham số generic `E` phải là một kiểu kế thừa `ApplicationEvent`. Khi triển khai `ApplicationListener<ProductPriceChangedEvent>`, class đã khai báo rõ rằng nó xử lý event thuộc kiểu `ProductPriceChangedEvent`.

Ví dụ:

```java
import org.springframework.context.ApplicationListener;

public class ProductPriceChangedListener
        implements ApplicationListener<ProductPriceChangedEvent> {

    @Override
    public void onApplicationEvent(ProductPriceChangedEvent event) {
        System.out.printf(
                "Product %d changed from %s to %s; source=%s%n",
                event.getProductId(),
                event.getOldPrice().toPlainString(),
                event.getNewPrice().toPlainString(),
                event.getSource().getClass().getSimpleName()
        );
    }
}
```

Spring đăng ký listener bean với `ApplicationEventMulticaster` của context. Khi event được publish, multicaster chọn listener có kiểu phù hợp rồi gọi `onApplicationEvent`.

Có thể đăng ký listener bằng cấu hình Java:

```java
@Configuration
class EventConfiguration {

    @Bean
    ProductPriceChangedListener productPriceChangedListener() {
        return new ProductPriceChangedListener();
    }
}
```

Cũng có thể dùng component scanning nếu class được đánh dấu `@Component`. Điều kiện quan trọng là listener phải được Spring quản lý hoặc được đăng ký trực tiếp với context; chỉ tạo object bằng `new ProductPriceChangedListener()` ở ngoài container không khiến nó tự động nhận event.

## 3. Source của event và source của publisher

Cần phân biệt hai khái niệm:

- **Publisher:** nơi gọi `publishEvent(...)`, tức context hoặc một bean được inject `ApplicationEventPublisher`.
- **Event source:** giá trị truyền vào constructor `ApplicationEvent` khi tạo event.

Hai đối tượng này có thể giống nhau nhưng không bắt buộc. Trong một luồng nghiệp vụ, context có thể là publisher trong khi `CatalogService` là source:

```java
CatalogService catalogService = context.getBean(CatalogService.class);

context.publishEvent(
        new ProductPriceChangedEvent(
                catalogService,
                42L,
                new BigDecimal("100.00"),
                new BigDecimal("125.00")
        )
);
```

Trong ví dụ này:

- `context` thực hiện việc phát event và phân phối event.
- `catalogService` được lưu vào `event.getSource()`.
- Listener có thể dùng source để ghi log hoặc truy vết nguồn phát sinh thay đổi.

Không nên dùng source như một cách truyền toàn bộ dependency sang listener. Listener nên phụ thuộc vào hợp đồng event và các dependency riêng của chính nó. Nếu source chỉ dùng để nhận diện nơi phát, hãy cân nhắc truyền một mã nguồn hoặc dữ liệu định danh rõ ràng thay vì một object lớn.

## 4. Event type matching hoạt động ra sao?

Spring không gọi mọi listener cho mọi event. Khi dispatch, Spring xem xét kiểu event thực tế và kiểu event mà listener đã khai báo.

Với listener generic, Spring cố gắng xác định kiểu `E` từ generic declaration của class hoặc bean definition. Kiểu đã phân giải được dùng để quyết định listener có hỗ trợ event hay không.

Ví dụ:

```java
class DomainEvent extends ApplicationEvent {
    DomainEvent(Object source) {
        super(source);
    }
}

class ProductPriceChangedEvent extends DomainEvent {
    ProductPriceChangedEvent(Object source) {
        super(source);
    }
}

class DomainEventListener
        implements ApplicationListener<DomainEvent> {
    @Override
    public void onApplicationEvent(DomainEvent event) {
        // Nhận DomainEvent và các subclass tương thích.
    }
}

class ProductPriceListener
        implements ApplicationListener<ProductPriceChangedEvent> {
    @Override
    public void onApplicationEvent(ProductPriceChangedEvent event) {
        // Chỉ nhận event thuộc nhánh ProductPriceChangedEvent.
    }
}
```

Khi publish một `ProductPriceChangedEvent`:

- `ApplicationListener<ProductPriceChangedEvent>` khớp trực tiếp.
- `ApplicationListener<DomainEvent>` cũng khớp vì event thực tế là subclass của `DomainEvent`.
- Một listener cho một nhánh không liên quan, ví dụ `ApplicationListener<CustomerRegisteredEvent>`, không khớp.

Có thể hiểu quy tắc kiểu lớp là: kiểu event mà listener khai báo phải có khả năng nhận instance của kiểu event thực tế. Nói cách khác, listener khai báo superclass có thể nhận event subclass; listener khai báo subclass không nhận một event chỉ có kiểu superclass.

Spring dùng thông tin kiểu đã phân giải (trong nội bộ có hỗ trợ `ResolvableType`) để xử lý cả các trường hợp generic. Điều này hữu ích khi nhiều listener cùng nghe một nhóm event nhưng mỗi listener cần một kiểu cụ thể. Nếu event class có tham số generic bị mất thông tin do type erasure và cần phân biệt chính xác tham số kiểu lúc chạy, event có thể triển khai `ResolvableTypeProvider` để cung cấp kiểu runtime phù hợp.

Không nên dựa vào tên class hoặc tên bean để định tuyến event. Hãy khai báo generic type rõ ràng và giữ quan hệ kế thừa event đơn giản, có ý nghĩa.

## 5. POJO event và PayloadApplicationEvent khác custom ApplicationEvent thế nào?

Từ Spring Framework 4.2, `publishEvent` nhận được cả object không kế thừa `ApplicationEvent`. Khi một POJO được publish, Spring bọc nó trong `PayloadApplicationEvent<T>` để đưa vào cơ chế event vốn nhận `ApplicationEvent`.

Giả sử có một record:

```java
public record PriceQuote(long productId, BigDecimal amount) {
}
```

Khi gọi:

```java
context.publishEvent(new PriceQuote(43L, new BigDecimal("19.99")));
```

event được dispatch thực tế là `PayloadApplicationEvent<PriceQuote>`, với:

- `getPayload()` trả về record `PriceQuote`.
- `getSource()` là publisher context đã bọc payload trong trường hợp publish POJO qua `ApplicationContext`.

Sự khác biệt quan trọng nằm ở kiểu object mà listener nhận:

| Cách publish | Object event được dispatch | Listener phù hợp |
|---|---|---|
| `publishEvent(new ProductPriceChangedEvent(...))` | Chính `ProductPriceChangedEvent` | `ApplicationListener<ProductPriceChangedEvent>` |
| `publishEvent(new PriceQuote(...))` | `PayloadApplicationEvent<PriceQuote>` | `ApplicationListener<PayloadApplicationEvent<PriceQuote>>` |
| Publish POJO và dùng annotation | Payload được adapter giải quyết | `@EventListener void onQuote(PriceQuote quote)` |

Do `ApplicationListener<E>` có ràng buộc `E extends ApplicationEvent`, không thể viết `ApplicationListener<PriceQuote>` nếu `PriceQuote` chỉ là record POJO. Có thể nghe wrapper bằng `ApplicationListener<PayloadApplicationEvent<PriceQuote>>`, hoặc dùng `@EventListener` để nhận trực tiếp payload.

Ví dụ listener nhận wrapper:

```java
class PriceQuoteWrapperListener
        implements ApplicationListener<PayloadApplicationEvent<PriceQuote>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<PriceQuote> event) {
        PriceQuote quote = event.getPayload();
        Object source = event.getSource();

        System.out.printf(
                "Payload from %s: product=%d, amount=%s%n",
                source.getClass().getSimpleName(),
                quote.productId(),
                quote.amount().toPlainString()
        );
    }
}
```

Ví dụ annotation nhận payload đã được giải quyết:

```java
class PriceQuoteAnnotationListener {

    @EventListener
    void onPriceQuote(PriceQuote quote) {
        System.out.printf(
                "Quote payload: product=%d, amount=%s%n",
                quote.productId(),
                quote.amount().toPlainString()
        );
    }
}
```

Trong trường hợp cần đọc metadata của wrapper, như `source` của `PayloadApplicationEvent`, hãy nhận wrapper bằng listener phù hợp. Nếu chỉ cần nội dung payload, method `@EventListener` với tham số POJO thường gọn hơn.

## 6. So sánh ApplicationListener<E> và @EventListener

Cả hai đều tham gia cơ chế dispatch của Spring, nhưng cách khai báo và kiểu event nhận có khác biệt.

| Tiêu chí | `ApplicationListener<E>` | `@EventListener` |
|---|---|---|
| Cách khai báo | Triển khai interface | Đánh dấu method của bean |
| Kiểu nhận | `E extends ApplicationEvent` | Có thể nhận ApplicationEvent hoặc payload POJO |
| Mức độ tường minh | Generic type nằm trên class | Kiểu tham số method thể hiện event |
| Phù hợp | Listener class chuyên trách, cần type contract rõ | Handler gọn, nhiều event method trong bean |
| Truy cập wrapper/source | Nhận event object trực tiếp | Có thể khai báo tham số event phù hợp; method nhận POJO thường nhận payload |
| Điều kiện | Có thể triển khai logic lọc trong listener chuyên biệt | Hỗ trợ thuộc tính `condition` với SpEL |

Dùng `ApplicationListener<E>` khi bạn muốn class thể hiện trực tiếp hợp đồng event, xử lý event ở mức object `ApplicationEvent`, hoặc cần truy cập `getSource()` và metadata của event.

Dùng `@EventListener` khi handler chỉ cần xử lý một kiểu payload, muốn đặt nhiều method listener trong một bean hoặc cần điều kiện SpEL:

```java
@EventListener(condition = "#quote.amount().doubleValue() > 100")
void onExpensiveQuote(PriceQuote quote) {
    // Chỉ xử lý quote có amount lớn hơn 100.
}
```

Trong SpEL, tên biến mặc định phụ thuộc vào tên tham số có thể được khám phá; để tránh mơ hồ, có thể dùng `#a0` hoặc `#p0` làm tham chiếu tham số đầu tiên khi cần. Điều kiện phải phù hợp với payload và không nên chứa logic nghiệp vụ phức tạp.

Không cần đăng ký cùng một phản ứng bằng cả hai cách nếu điều đó khiến một event bị xử lý trùng. Chọn một cơ chế phù hợp cho từng handler và kiểm thử số lần xử lý.

## 7. Ví dụ hoàn chỉnh với Java 17 và Spring Framework 6.2

Ví dụ này phát hai loại event để quan sát rõ khác biệt:

1. `ProductPriceChangedEvent` kế thừa `ApplicationEvent`, source là bean `CatalogService`, được nhận bởi `ApplicationListener<ProductPriceChangedEvent>`.
2. `PriceQuote` là POJO record. Spring bọc nó thành `PayloadApplicationEvent<PriceQuote>`; một listener nhận wrapper và một method `@EventListener` nhận trực tiếp payload.

Cấu trúc:

```text
application-event-listener-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventListenerDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>application-event-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ApplicationEventListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/demo/ApplicationEventListenerDemo.java**

```java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class ApplicationEventListenerDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            CatalogService source = context.getBean(CatalogService.class);

            context.publishEvent(
                    new ProductPriceChangedEvent(
                            source,
                            42L,
                            new BigDecimal("10.00"),
                            new BigDecimal("12.50")
                    )
            );

            context.publishEvent(
                    new PriceQuote(43L, new BigDecimal("19.99"))
            );
        }
    }

    @Configuration
    static class AppConfig {

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }

        @Bean
        ProductPriceChangedListener productPriceChangedListener() {
            return new ProductPriceChangedListener();
        }

        @Bean
        PriceQuoteWrapperListener priceQuoteWrapperListener() {
            return new PriceQuoteWrapperListener();
        }

        @Bean
        PriceQuoteAnnotationListener priceQuoteAnnotationListener() {
            return new PriceQuoteAnnotationListener();
        }
    }

    static class CatalogService {
    }

    static class ProductPriceChangedEvent extends ApplicationEvent {
        private final long productId;
        private final BigDecimal oldPrice;
        private final BigDecimal newPrice;

        ProductPriceChangedEvent(
                Object source,
                long productId,
                BigDecimal oldPrice,
                BigDecimal newPrice) {
            super(source);
            this.productId = productId;
            this.oldPrice = oldPrice;
            this.newPrice = newPrice;
        }

        long getProductId() {
            return productId;
        }

        BigDecimal getOldPrice() {
            return oldPrice;
        }

        BigDecimal getNewPrice() {
            return newPrice;
        }
    }

    record PriceQuote(long productId, BigDecimal amount) {
    }

    static class ProductPriceChangedListener
            implements ApplicationListener<ProductPriceChangedEvent> {

        @Override
        public void onApplicationEvent(ProductPriceChangedEvent event) {
            System.out.printf(
                    "Custom ApplicationEvent: product=%d, source=%s, %s -> %s%n",
                    event.getProductId(),
                    event.getSource().getClass().getSimpleName(),
                    event.getOldPrice().toPlainString(),
                    event.getNewPrice().toPlainString()
            );
        }
    }

    @Order(1)
    static class PriceQuoteWrapperListener
            implements ApplicationListener<PayloadApplicationEvent<PriceQuote>> {

        @Override
        public void onApplicationEvent(
                PayloadApplicationEvent<PriceQuote> event) {
            PriceQuote quote = event.getPayload();

            System.out.printf(
                    "PayloadApplicationEvent: source=%s, payload=%s%n",
                    event.getSource().getClass().getSimpleName(),
                    quote
            );
        }
    }

    static class PriceQuoteAnnotationListener {

        @EventListener
        @Order(2)
        void onPriceQuote(PriceQuote quote) {
            System.out.printf(
                    "@EventListener payload: product=%d, amount=%s%n",
                    quote.productId(),
                    quote.amount().toPlainString()
            );
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Stdout dự kiến:

```text
Custom ApplicationEvent: product=42, source=CatalogService, 10.00 -> 12.50
PayloadApplicationEvent: source=AnnotationConfigApplicationContext, payload=PriceQuote[productId=43, amount=19.99]
@EventListener payload: product=43, amount=19.99
```

Giải thích:

- Event custom được publish trực tiếp vì nó đã là một `ApplicationEvent`. Spring không bọc thêm `PayloadApplicationEvent`.
- Listener generic `ApplicationListener<ProductPriceChangedEvent>` được chọn theo kiểu event.
- Source của custom event là bean `CatalogService`, vì object đó được truyền vào `super(source)`.
- `PriceQuote` không kế thừa `ApplicationEvent`; context bọc nó trong `PayloadApplicationEvent`.
- `ApplicationListener<PayloadApplicationEvent<PriceQuote>>` nhận wrapper nên đọc được cả `getPayload()` và `getSource()`.
- `@EventListener` với tham số `PriceQuote` nhận payload đã được Spring giải quyết, nên method không cần tự mở wrapper.
- `@Order` xác định thứ tự hai listener xử lý cùng payload trong ví dụ.

## 8. Những lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Truyền `null` vào source | `EventObject` yêu cầu source khác null | Truyền bean hoặc object nguồn có ý nghĩa |
| Dùng `ApplicationListener<PriceQuote>` cho POJO | Generic `E` bị ràng buộc phải extends `ApplicationEvent` | Dùng `ApplicationListener<PayloadApplicationEvent<PriceQuote>>` hoặc `@EventListener` |
| Nghĩ listener custom nhận cả POJO cùng dữ liệu | POJO được bọc thành wrapper khác kiểu | Khai báo listener cho wrapper hoặc method nhận payload |
| Listener không được gọi | Bean chưa được đăng ký hoặc kiểu event không khớp | Kiểm tra generic type và cấu hình bean |
| Listener superclass không nhận subclass | Kiểu generic được khai báo quá hẹp hoặc type metadata không đúng | Khai báo kiểu cha phù hợp và kiểm tra generic runtime |
| Dùng source làm service locator | Listener bị phụ thuộc vào object phát event | Đưa dữ liệu cần thiết vào event và inject dependency riêng |
| Một event bị xử lý hai lần | Cùng phản ứng được đăng ký qua nhiều listener | Chọn một handler hoặc kiểm soát rõ các side effect |
| Gửi ApplicationEvent sang service khác | Application event chỉ thuộc context/process hiện tại | Dùng integration event và broker/API phù hợp |

## 9. Lưu ý về transaction và độ tin cậy

Application event mặc định được dispatch đồng bộ. Nếu publish event bên trong transaction, listener thông thường có thể chạy trước commit. Nếu transaction rollback sau đó, side effect mà listener đã thực hiện không tự rollback theo database.

Với listener cần chạy sau khi transaction commit, có thể dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. Tuy nhiên, listener sau commit vẫn không tạo bảo đảm lưu bền vững: process có thể dừng sau commit trước khi listener hoàn tất. Với thông điệp tích hợp quan trọng không được bỏ sót, hãy ghi outbox trong cùng transaction rồi chuyển tiếp qua relay/broker. Thiết kế consumer idempotent vì message có thể được giao lại.

Cũng cần nhớ rằng ApplicationEvent không phải message broker. Nó không tự cung cấp durable storage, acknowledgement, retry, replay hay giao nhận giữa nhiều process. Phạm vi của nó là cơ chế event nội bộ trong Spring application.

## 10. Checklist triển khai

- [ ] Custom event kế thừa `ApplicationEvent` khi cần event class rõ ràng.
- [ ] Constructor gọi `super(source)` với source khác null.
- [ ] Event chứa dữ liệu cần thiết, ưu tiên trạng thái bất biến.
- [ ] Listener khai báo đúng `ApplicationListener<E>` và E là ApplicationEvent phù hợp.
- [ ] Listener được đăng ký thành bean hoặc được thêm trực tiếp vào context.
- [ ] Hiểu event type matching giữa superclass và subclass.
- [ ] Không nhầm POJO payload với custom ApplicationEvent.
- [ ] Dùng `PayloadApplicationEvent<T>` khi cần nhận wrapper và source của POJO.
- [ ] Dùng `@EventListener` khi cần nhận payload trực tiếp hoặc handler gọn.
- [ ] Không đăng ký cùng side effect qua nhiều cơ chế khiến event bị xử lý trùng.
- [ ] Xác định transaction, đồng bộ/bất đồng bộ và chính sách lỗi phù hợp.
- [ ] Dùng integration mechanism khi cần giao tiếp giữa các tiến trình.

## Kết luận

`ApplicationListener<E>` nhận event theo kiểu generic được khai báo, trong đó `E` phải kế thừa `ApplicationEvent`. Custom event class cho phép định nghĩa rõ dữ liệu và source; Spring dùng kiểu event đã phân giải để chọn listener tương thích. Khi publish POJO, Spring bọc payload thành `PayloadApplicationEvent<T>`, vì vậy listener interface nhận wrapper còn `@EventListener` có thể nhận trực tiếp payload. Nắm vững khác biệt này giúp chọn đúng hợp đồng listener, truy vết source chính xác và tránh bỏ lỡ event do sai kiểu.