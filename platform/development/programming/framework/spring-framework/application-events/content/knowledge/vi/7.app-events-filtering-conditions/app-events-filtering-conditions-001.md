# Điều kiện condition trong @EventListener của Spring Framework

## Mục tiêu

`@EventListener` cho phép một bean nhận application event thông qua method. Thuộc tính `condition` bổ sung một bước lọc bằng Spring Expression Language (SpEL): Spring chỉ gọi method listener khi biểu thức đánh giá thành `true`.

Điều kiện được áp dụng riêng cho từng method listener đã khớp kiểu event. Vì vậy, nhiều listener có thể nhận cùng một loại event nhưng chỉ xử lý những trường hợp phù hợp với tiêu chí của từng listener.

Bài học tập trung vào cách viết biểu thức, truy cập đối số event, lọc payload POJO và custom `ApplicationEvent`, cách kết hợp nhiều listener, và các giới hạn cần hiểu khi dùng điều kiện trong ứng dụng thực tế.

Sau bài học, bạn có thể:

- Viết `@EventListener(condition = "...")` bằng SpEL.
- Truy cập đối số listener ổn định bằng `#a0` hoặc `#p0`.
- Dùng điều kiện với POJO payload và class kế thừa `ApplicationEvent`.
- Phân biệt bước khớp kiểu event với bước đánh giá condition.
- Kết hợp nhiều listener, `@Order`, biểu thức null-safe và thuộc tính lồng nhau.
- Kiểm thử trường hợp được nhận, bị lọc và lỗi biểu thức.

## 1. Condition là bộ lọc ở phía listener

Khi một object được publish, Spring trước hết xác định các listener phù hợp với kiểu event và chữ ký method. Với method có `@EventListener`, nếu có khai báo `condition`, Spring đánh giá biểu thức SpEL trước khi gọi method.

Luồng xử lý khái quát:

1. Publisher gọi `publishEvent(event)`.
2. Spring tìm các listener có kiểu event tương thích với event thực tế.
3. Với từng method `@EventListener` phù hợp, Spring chuẩn bị các đối số method.
4. Spring đánh giá `condition` trong evaluation context của listener.
5. Nếu biểu thức trả về `true`, method được gọi. Nếu trả về `false`, method đó được bỏ qua.
6. Các listener khác tiếp tục được xét độc lập theo cấu hình dispatch.

Ví dụ, một `PriceQuote` có thể được gửi đến ba listener: listener dành cho báo giá giá trị cao, listener dành cho khu vực Việt Nam và listener ghi nhận mọi báo giá. Condition của hai listener đầu có thể khác nhau; listener ghi nhận mọi báo giá không cần condition.

**Condition không lọc event tại publisher và không chặn các listener khác.** Nó chỉ quyết định một method listener cụ thể có được gọi hay không. Nếu cần từ chối một hành động nghiệp vụ hoặc kiểm tra quyền truy cập, hãy thực hiện quy tắc đó trong application/domain service; không dùng condition làm ranh giới bảo mật.

## 2. Cú pháp cơ bản

Thuộc tính `condition` nhận một chuỗi biểu thức SpEL:

```java
@EventListener(condition = "#a0.amount >= 100")
void onHighValueQuote(PriceQuote quote) {
    // Chỉ xử lý báo giá có amount thỏa điều kiện.
}
```

Biểu thức cần trả về boolean. Giá trị `true` cho phép Spring gọi method; `false` khiến method bị bỏ qua.

Một số toán tử thường dùng:

| Nhóm | Toán tử / cú pháp | Ý nghĩa |
|---|---|---|
| So sánh | `==`, `!=`, `>`, `>=`, `<`, `<=` | So sánh giá trị |
| Logic | `and`, `or`, `not`, `&&`, `||`, `!` | Kết hợp hoặc phủ định điều kiện |
| Null | `== null`, `!= null` | Kiểm tra giá trị null |
| Chuỗi | `#a0.region == 'VN'` | So sánh chuỗi |
| Kiểu tĩnh | `T(java.math.BigDecimal)` | Tham chiếu class Java |
| Gọi method | `#a0.amount.compareTo(...)` | Gọi method trên đối tượng |

Ví dụ kết hợp:

```java
@EventListener(
    condition = "#a0.region == 'VN' and #a0.amount >= 100"
)
void onVietnamHighValueQuote(PriceQuote quote) {
    // Chỉ xử lý báo giá từ VN có giá trị từ 100 trở lên.
}
```

Khi so sánh tiền tệ bằng `BigDecimal`, nên dùng `compareTo` thay cho toán tử so sánh số trực tiếp để tránh nhầm lẫn giữa so sánh số học và biểu diễn thập phân:

```java
@EventListener(
    condition = "#a0.amount.compareTo(T(java.math.BigDecimal).valueOf(100)) >= 0"
)
void onHighValueQuote(PriceQuote quote) {
}
```

`compareTo` trả về số âm, 0 hoặc số dương. Biểu thức trên chọn các báo giá có amount lớn hơn hoặc bằng 100.

## 3. Truy cập event và tham số method trong SpEL

Spring cung cấp các biến tham chiếu cho biểu thức của `@EventListener`:

| Biến | Nội dung |
|---|---|
| `#root.event` | Application event đang được xử lý |
| `#root.args` | Mảng đối số đã phân giải cho method listener |
| `#a0` | Đối số thứ nhất của method |
| `#a1` | Đối số thứ hai, nếu method có đối số thứ hai |
| `#p0` | Bí danh vị trí thứ nhất, tương tự `#a0` |
| `#p1` | Bí danh vị trí thứ hai, tương tự `#a1` |

Với listener có một tham số, `#a0` và `#p0` là cách tham chiếu ngắn, ổn định theo vị trí. Có thể dùng tên tham số như `#quote` khi Spring khám phá được tên tham số từ metadata biên dịch; nếu muốn biểu thức không phụ thuộc cấu hình compiler, ưu tiên `#a0` hoặc `#p0`.

Ví dụ:

```java
@EventListener(condition = "#a0.region == 'VN'")
void onVietnamQuote(PriceQuote quote) {
}

@EventListener(condition = "#root.args[0].amount >= 100")
void onLargeQuote(PriceQuote quote) {
}
```

Với một custom event kế thừa `ApplicationEvent`, method có thể nhận chính event class và condition truy cập thuộc tính của event:

```java
@EventListener(condition = "#a0.quantity < 0")
void onNegativeInventory(InventoryAdjustedEvent event) {
    // Chỉ gọi khi số lượng điều chỉnh âm.
}
```

Nếu cần kiểm tra metadata của event gốc, `#root.event` là application event được Spring dispatch. Với custom `ApplicationEvent`, có thể truy cập source qua thuộc tính `source` hoặc gọi `getSource()` theo cú pháp SpEL phù hợp. Với POJO được publish, root event là wrapper `PayloadApplicationEvent`, còn `#a0` trong method nhận payload là chính payload đã được phân giải.

## 4. Property access và kiểm tra null

SpEL truy cập property Java thông qua accessor. Với JavaBean, property `amount` thường ánh xạ tới getter `getAmount()`; property `region` ánh xạ tới `getRegion()`.

```java
public class PriceQuote {
    private final BigDecimal amount;
    private final String region;

    public PriceQuote(BigDecimal amount, String region) {
        this.amount = amount;
        this.region = region;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getRegion() {
        return region;
    }
}
```

Một biểu thức có thể kết hợp nhiều property:

```java
@EventListener(
    condition = "#a0.customer != null and #a0.customer.active == true"
)
void onActiveCustomerQuote(PriceQuote quote) {
}
```

Nên kiểm tra null trước khi truy cập property lồng nhau. SpEL dùng toán tử logic short-circuit, vì vậy vế phải của `and` không cần được đánh giá khi vế trái đã là false.

Có thể viết ngắn hơn:

```java
@EventListener(
    condition = "#a0.customer?.active == true"
)
void onActiveCustomerQuote(PriceQuote quote) {
}
```

Toán tử safe navigation `?.` trả về null nếu đối tượng bên trái là null, giúp tránh lỗi truy cập property trên null. Hãy chọn cách viết rõ ràng và thống nhất trong codebase.

Không nên viết condition quá dài với nhiều phép gọi method và nhánh lồng nhau. Nếu quy tắc cần nhiều bước hoặc có ý nghĩa nghiệp vụ quan trọng, hãy đưa logic vào một policy/service có thể kiểm thử riêng; condition chỉ nên biểu đạt bộ lọc ngắn.

## 5. Lọc POJO payload và custom ApplicationEvent

Spring hỗ trợ hai dạng event thường gặp.

### POJO được bọc trong PayloadApplicationEvent

Từ Spring Framework 4.2, publisher có thể gửi một object Java không kế thừa `ApplicationEvent`:

```java
context.publishEvent(new PriceQuote(101L, new BigDecimal("150.00"), "VN"));
```

Spring bọc POJO trong `PayloadApplicationEvent<PriceQuote>`. Method `@EventListener` có tham số `PriceQuote` có thể nhận trực tiếp payload, và condition truy cập payload qua `#a0`:

```java
@EventListener(condition = "#a0.region == 'VN'")
void onVietnamQuote(PriceQuote quote) {
}

@EventListener(
    condition = "#a0.amount.compareTo(T(java.math.BigDecimal).valueOf(100)) >= 0"
)
void onHighValueQuote(PriceQuote quote) {
}
```

Nếu listener cần đọc cả wrapper, ví dụ `getSource()` của `PayloadApplicationEvent`, có thể khai báo tham số phù hợp với wrapper. Trong trường hợp đó, hãy xác định rõ kiểu method argument mà condition sẽ nhận.

### Custom event kế thừa ApplicationEvent

Một custom event có thể chứa các property nghiệp vụ và source:

```java
public class InventoryAdjustedEvent extends ApplicationEvent {
    private final String warehouse;
    private final int quantityDelta;

    public InventoryAdjustedEvent(
            Object source,
            String warehouse,
            int quantityDelta) {
        super(source);
        this.warehouse = warehouse;
        this.quantityDelta = quantityDelta;
    }

    public String getWarehouse() {
        return warehouse;
    }

    public int getQuantityDelta() {
        return quantityDelta;
    }
}
```

Condition có thể lọc trực tiếp trên event:

```java
@EventListener(
    condition = "#a0.warehouse == 'HCM' and #a0.quantityDelta < 0"
)
void onHcmStockReduction(InventoryAdjustedEvent event) {
}
```

Ở đây `#a0` là custom event object. Nó không phải payload wrapper vì event đã kế thừa `ApplicationEvent`.

| Đặc điểm | Custom ApplicationEvent | POJO payload |
|---|---|---|
| Class gốc | Kế thừa `ApplicationEvent` | Object Java thông thường |
| Object được dispatch | Chính custom event | `PayloadApplicationEvent<T>` |
| `@EventListener` có thể nhận | Custom event class | Payload type |
| Condition trên `#a0` | Property của custom event | Property của payload nếu method nhận payload |
| Source | Được truyền vào `super(source)` | Source của wrapper do Spring tạo khi publish qua context |
| Listener interface | `ApplicationListener<CustomEvent>` | `ApplicationListener<PayloadApplicationEvent<T>>` nếu muốn nhận wrapper |

Không thể khai báo `ApplicationListener<PriceQuote>` khi `PriceQuote` chỉ là POJO vì generic `E` phải extends `ApplicationEvent`. Với POJO, dùng `@EventListener` nhận payload hoặc `ApplicationListener<PayloadApplicationEvent<PriceQuote>>` nhận wrapper.

## 6. Condition được đánh giá sau event type matching

Condition không thay thế việc xác định kiểu event. Trước tiên Spring cần biết method listener có thể nhận event đó hay không; sau đó condition mới quyết định method có được gọi hay không.

Ví dụ có hai method cùng nhận `PriceQuote`:

```java
@EventListener(condition = "#a0.amount >= 100")
void onLargeQuote(PriceQuote quote) {
}

@EventListener(condition = "#a0.region == 'VN'")
void onVietnamQuote(PriceQuote quote) {
}
```

Với một quote có amount 150 và region VN, cả hai condition đều true và cả hai method đều có thể được gọi. Với amount 50 và region VN, chỉ method thứ hai được gọi. Với amount 150 và region US, chỉ method thứ nhất được gọi.

Condition của một method không làm thay đổi condition của method khác. Nó cũng không ngăn event tiếp tục tới các listener khác.

Có thể dùng `@Order` để sắp xếp thứ tự listener method khi nhiều method cùng xử lý event. Thứ tự này có ích khi các listener đồng bộ có phụ thuộc thứ tự rõ ràng, nhưng không nên dùng nó để tạo một chuỗi nghiệp vụ phức tạp hoặc phụ thuộc thứ tự hoàn tất của tác vụ bất đồng bộ.

## 7. Ví dụ chạy được với Java 17 và Spring Framework 6.2

Ví dụ sau dùng POJO `PriceQuote` và hai listener method. Listener thứ nhất chỉ nhận báo giá có amount từ 100 trở lên; listener thứ hai chỉ nhận báo giá thuộc khu vực VN. Dùng `#a0` để condition không phụ thuộc tên tham số compiler.

Cấu trúc:

```text
event-listener-condition-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── EventListenerConditionDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-listener-condition-demo</artifactId>
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
                    <mainClass>demo.EventListenerConditionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/demo/EventListenerConditionDemo.java**

```java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventListenerConditionDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            QuotePublisher publisher = context.getBean(QuotePublisher.class);

            publisher.publish(new PriceQuote(
                    101L, new BigDecimal("150.00"), "VN"));
            publisher.publish(new PriceQuote(
                    102L, new BigDecimal("50.00"), "VN"));
            publisher.publish(new PriceQuote(
                    103L, new BigDecimal("200.00"), "US"));
            publisher.publish(new PriceQuote(
                    104L, new BigDecimal("80.00"), "US"));
        }
    }

    @Configuration
    static class AppConfig {

        @Bean
        QuotePublisher quotePublisher(ApplicationEventPublisher publisher) {
            return new QuotePublisher(publisher);
        }

        @Bean
        QuoteListeners quoteListeners() {
            return new QuoteListeners();
        }
    }

    static class QuotePublisher {
        private final ApplicationEventPublisher publisher;

        QuotePublisher(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void publish(PriceQuote quote) {
            publisher.publishEvent(quote);
        }
    }

    public static class PriceQuote {
        private final long quoteId;
        private final BigDecimal amount;
        private final String region;

        public PriceQuote(long quoteId, BigDecimal amount, String region) {
            this.quoteId = quoteId;
            this.amount = amount;
            this.region = region;
        }

        public long getQuoteId() {
            return quoteId;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getRegion() {
            return region;
        }
    }

    static class QuoteListeners {

        @EventListener(
            condition = "#a0.amount.compareTo(T(java.math.BigDecimal).valueOf(100)) >= 0"
        )
        @Order(1)
        void onHighValueQuote(PriceQuote quote) {
            System.out.printf(
                    "HIGH: quote=%d amount=%s%n",
                    quote.getQuoteId(),
                    quote.getAmount().toPlainString()
            );
        }

        @EventListener(condition = "#a0.region == 'VN'")
        @Order(2)
        void onVietnamQuote(PriceQuote quote) {
            System.out.printf(
                    "VN: quote=%d region=%s%n",
                    quote.getQuoteId(),
                    quote.getRegion()
            );
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Stdout chính xác:

```text
HIGH: quote=101 amount=150.00
VN: quote=101 region=VN
VN: quote=102 region=VN
HIGH: quote=103 amount=200.00
```

Diễn giải kết quả:

| Quote | Amount | Region | Listener được gọi |
|---|---:|---|---|
| 101 | 150.00 | VN | HIGH và VN |
| 102 | 50.00 | VN | VN |
| 103 | 200.00 | US | HIGH |
| 104 | 80.00 | US | Không listener nào |

Quote 104 vẫn được publish bình thường. Chỉ là cả hai condition đều false nên không method listener nào trong class được gọi cho quote đó.

## 8. Kết hợp condition với custom ApplicationEvent

Nếu ứng dụng đã có custom event class kế thừa `ApplicationEvent`, condition có thể lọc trên property của chính event. Ví dụ:

```java
public class InventoryAdjustedEvent extends ApplicationEvent {
    private final String warehouse;
    private final int quantityDelta;

    public InventoryAdjustedEvent(
            Object source,
            String warehouse,
            int quantityDelta) {
        super(source);
        this.warehouse = warehouse;
        this.quantityDelta = quantityDelta;
    }

    public String getWarehouse() {
        return warehouse;
    }

    public int getQuantityDelta() {
        return quantityDelta;
    }
}
```

Listener:

```java
@Component
class InventoryListeners {

    @EventListener(
        condition = "#a0.warehouse == 'HCM' and #a0.quantityDelta < 0"
    )
    void onHcmStockReduction(InventoryAdjustedEvent event) {
        // Phản ứng khi kho HCM giảm tồn.
    }
}
```

Publisher:

```java
eventPublisher.publishEvent(
        new InventoryAdjustedEvent(this, "HCM", -3)
);
```

Ở đây `#a0` là instance `InventoryAdjustedEvent`. Spring đã chọn method dựa trên kiểu event; condition tiếp tục lọc theo warehouse và quantityDelta. Event có warehouse khác hoặc delta không âm sẽ không gọi method này.

Khi condition cần xét source, có thể truy cập event object qua `#a0.source` hoặc `#a0.getSource()` đối với custom event. Chỉ dùng source trong điều kiện nếu source thực sự là một phần ổn định của quy tắc lọc; tránh dựa vào class cụ thể của service phát event vì điều đó tạo coupling giữa listener và implementation.

## 9. Condition, @Order và bất đồng bộ

### @Order

Khi nhiều listener cùng nhận một event, `@Order` có thể xác định thứ tự gọi. Giá trị nhỏ hơn có độ ưu tiên cao hơn:

```java
@EventListener(condition = "#a0.region == 'VN'")
@Order(1)
void notifyVietnam(PriceQuote quote) {
}

@EventListener(condition = "#a0.amount >= 100")
@Order(2)
void auditLargeQuote(PriceQuote quote) {
}
```

Condition vẫn được đánh giá riêng cho từng method. `@Order` không làm một condition phụ thuộc condition trước và không thay đổi việc publish event.

### @Async

Có thể kết hợp `@Async` với `@EventListener` khi listener phù hợp chạy bất đồng bộ và ứng dụng đã bật `@EnableAsync`:

```java
@Async
@EventListener(condition = "#a0.region == 'VN'")
void processVietnamQuote(PriceQuote quote) {
    // Xử lý phụ có thể chạy trên executor.
}
```

Condition quyết định method có được chọn để chạy hay không; `@Async` quyết định việc thực thi method được chuyển sang executor. Publisher không chờ listener async hoàn tất. Cần cấu hình executor, theo dõi exception và tránh phụ thuộc thứ tự hoàn tất. Async không làm event bền vững: công việc còn trong bộ nhớ vẫn có thể mất khi process dừng.

## 10. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Method luôn chạy dù tưởng condition false | Biểu thức luôn trả true hoặc tham chiếu sai đối số | Kiểm tra giá trị thực tế của `#a0` và viết điều kiện boolean rõ ràng |
| Method không chạy | Event type không khớp hoặc condition false | Kiểm tra riêng kiểu tham số và biểu thức |
| Lỗi SpEL khi publish | Sai tên property, method hoặc kiểu dữ liệu | Dùng getter hợp lệ, kiểm tra null và chạy test cho biểu thức |
| Dùng `#quote` nhưng không resolve | Metadata tên tham số không có sẵn | Dùng `#a0` hoặc `#p0` |
| So sánh BigDecimal bằng double | Sai số biểu diễn hoặc phép so sánh không rõ ràng | Dùng `compareTo` với ngưỡng BigDecimal |
| Truy cập property lồng nhau khi null | Vế trái không tồn tại | Kiểm tra null trước hoặc dùng `?.` |
| Nghĩ condition chặn event toàn ứng dụng | Condition chỉ áp dụng một listener method | Đặt validation nghiệp vụ ở service/domain |
| Condition gọi logic nặng | Biểu thức chạy mỗi khi listener phù hợp nhận event | Chỉ lọc thuộc tính đơn giản; chuyển policy phức tạp sang component riêng |
| Condition có side effect | SpEL được dùng như một nơi thực thi nghiệp vụ | Giữ biểu thức thuần, không thay đổi trạng thái |
| Listener async bị mất công việc khi tắt ứng dụng | Executor không phải kho lưu bền vững | Dùng outbox hoặc message broker khi cần giao nhận tin cậy |

Nếu condition sai cú pháp hoặc truy cập property không hợp lệ, việc đánh giá có thể ném exception. Với dispatch đồng bộ mặc định, exception có thể truyền về luồng publish và ảnh hưởng các listener tiếp theo. Hãy kiểm thử biểu thức với dữ liệu đại diện, bao gồm null, giá trị biên và trường hợp không khớp.

## 11. Chiến lược kiểm thử condition

Một condition tốt cần kiểm thử cả hai nhánh true/false. Với ví dụ báo giá, nên xác nhận:

- Báo giá 150.00 ở VN gọi cả hai listener.
- Báo giá 50.00 ở VN chỉ gọi listener VN.
- Báo giá 200.00 ở US chỉ gọi listener HIGH.
- Báo giá 80.00 ở US không gọi hai listener có điều kiện.

Có thể kiểm thử qua context Spring thật để xác nhận annotation được phát hiện và SpEL được đánh giá. Dùng listener test hoặc spy để đếm số lần gọi, thay vì chỉ kiểm tra log. Với listener async, dùng latch hoặc cơ chế đồng bộ hóa có timeout để tránh test phụ thuộc thời gian ngủ cố định.

Nên có test riêng cho:

1. Điều kiện biên, ví dụ amount đúng bằng 100.
2. Property null và nested property null.
3. Region hoặc trạng thái không được hỗ trợ.
4. Condition sai cú pháp hoặc truy cập property không tồn tại.
5. Nhiều listener cùng nhận một event và thứ tự `@Order` mong muốn.

## 12. Nguyên tắc thiết kế

- Condition nên ngắn, dễ đọc và trả về boolean rõ ràng.
- Dùng `#a0`/`#p0` khi muốn tham chiếu đối số ổn định theo vị trí.
- Không đưa quy tắc phân quyền hoặc invariant nghiệp vụ vào SpEL condition.
- Không gọi API bên ngoài, truy vấn database hoặc thực hiện side effect trong condition.
- Nếu biểu thức trở nên phức tạp, tạo các event type rõ hơn hoặc tách policy thành thành phần nghiệp vụ có thể kiểm thử.
- Nhớ rằng condition được áp dụng riêng cho method listener, không phải bộ lọc chung của publisher.
- Khi cần giao tiếp bền vững giữa các process, dùng integration event và cơ chế vận chuyển phù hợp; `@EventListener` chỉ xử lý event trong ứng dụng Spring.

## Kết luận

`@EventListener(condition = "...")` kết hợp cơ chế chọn listener theo event type với một biểu thức SpEL để quyết định method có được gọi hay không. `#a0` và `#p0` giúp truy cập đối số ổn định; `#root.event` cho phép quan sát application event gốc. Với POJO được publish, method có thể nhận payload trong khi event nội bộ được bọc bởi `PayloadApplicationEvent`; với custom `ApplicationEvent`, method nhận event class và lọc trực tiếp trên property của nó. Giữ condition thuần, ngắn và được kiểm thử ở cả hai nhánh để việc lọc listener dễ dự đoán.