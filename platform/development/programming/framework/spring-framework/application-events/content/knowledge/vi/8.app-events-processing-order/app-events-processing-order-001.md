# @Order trên event listener

## 1. Vai trò của @Order trong xử lý event

Một event trong Spring có thể được nhiều listener cùng nhận. Khi các listener cần được gọi theo thứ tự xác định, Spring cung cấp cơ chế sắp xếp bằng `@Order` và contract `Ordered`.

Ví dụ, sau khi nhận `OrderPlaced`, ứng dụng có thể cần chạy lần lượt các bước kiểm tra dữ liệu, giữ hàng tồn kho, ghi audit và gửi thông báo. Nếu các bước này là những listener đồng bộ cùng nhận một event, có thể gán mức ưu tiên cho từng listener để Spring gọi chúng theo thứ tự.

`@Order` mô tả thứ tự ưu tiên khi một cơ chế Spring có hỗ trợ ordering. Với event listener, nó ảnh hưởng đến thứ tự dispatch các listener phù hợp cho cùng một lần phát event. Nó không tạo workflow, không tự bảo đảm transaction nguyên tử giữa nhiều listener và không điều khiển thứ tự khởi tạo bean.

## 2. Quy tắc sắp xếp

Spring sử dụng quy tắc của interface `Ordered`:

- Số order càng nhỏ thì độ ưu tiên càng cao và listener được gọi trước.
- Số order lớn hơn được gọi sau.
- Nếu không khai báo order, listener dùng `Ordered.LOWEST_PRECEDENCE`, tương đương mức ưu tiên thấp nhất.
- Có thể dùng `Ordered.HIGHEST_PRECEDENCE` hoặc `Ordered.LOWEST_PRECEDENCE` để biểu đạt hai đầu của dải ưu tiên.
- Nếu hai listener có cùng order, không nên dựa vào thứ tự khai báo method hoặc thứ tự component scan để quyết định listener nào chạy trước.

Ví dụ:

| Listener | Order | Thứ tự dispatch |
|---|---:|---|
| ValidateOrder | 10 | Đầu tiên |
| ReserveInventory | 20 | Thứ hai |
| WriteAudit | 30 | Thứ ba |
| NotifyCustomer | Mặc định | Sau các listener có order cụ thể trong ví dụ |

Order không phải thời gian. `@Order(10)` không có nghĩa listener chờ 10 mili giây, chạy 10 lần hoặc có thời gian thực thi 10 đơn vị.

Nên chọn các giá trị có khoảng cách như 10, 20, 30 để dễ chèn bước mới. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy gán giá trị khác nhau cho các listener liên quan.

## 3. Đặt @Order trên method @EventListener

Với listener khai báo bằng annotation, đặt `@Order` trực tiếp trên method có `@EventListener`:

```java
@Component
public class OrderListeners {

    @EventListener
    @Order(10)
    public void validate(OrderPlaced event) {
        System.out.println("10 validate");
    }

    @EventListener
    @Order(20)
    public void reserveInventory(OrderPlaced event) {
        System.out.println("20 reserve");
    }

    @EventListener
    @Order(30)
    public void writeAudit(OrderPlaced event) {
        System.out.println("30 audit");
    }
}
```

Trong quá trình refresh ApplicationContext, Spring phát hiện các method listener, tạo adapter tương ứng và đăng ký chúng với application event multicaster. Khi một `OrderPlaced` được publish, multicaster chọn các listener phù hợp và sắp xếp chúng theo order trước khi dispatch.

Order chỉ so sánh các listener tham gia cùng lần dispatch. Một listener nhận `PaymentCaptured` không được đặt trước hoặc sau listener nhận `OrderPlaced` chỉ vì hai method có các giá trị order khác nhau; hai event được phân phối trong hai lần riêng biệt.

## 4. Listener không khai báo order

Nếu một method `@EventListener` không có `@Order` và listener không cung cấp một order khác qua contract tương ứng, nó được xem là có mức ưu tiên mặc định `Ordered.LOWEST_PRECEDENCE`.

Ví dụ:

```java
@Component
public class OrderListeners {

    @EventListener
    @Order(10)
    public void validate(OrderPlaced event) {
        System.out.println("validate");
    }

    @EventListener
    public void notifyCustomer(OrderPlaced event) {
        System.out.println("notify");
    }
}
```

Listener `validate` có mức ưu tiên cao hơn listener không khai báo order. Tuy nhiên, khi nhiều listener cùng dùng mức mặc định hoặc cùng một giá trị, thứ tự tương đối giữa chúng không phải hợp đồng nên dựa vào cho logic nghiệp vụ.

## 5. Dùng ApplicationListener và Ordered

Nếu muốn biểu diễn listener bằng một class triển khai `ApplicationListener<E>`, có thể đặt `@Order` trên class:

```java
@Component
@Order(10)
public class AuditListener
        implements ApplicationListener<OrderPlaced> {

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        System.out.println("audit: " + event.orderId());
    }
}
```

Hoặc triển khai interface `Ordered`:

```java
@Component
public class InventoryListener
        implements ApplicationListener<OrderPlaced>, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        System.out.println("reserve: " + event.orderId());
    }
}
```

Với `@EventListener`, khai báo order trên method là cách trực tiếp. Với `ApplicationListener`, order có thể được cung cấp ở cấp class hoặc bằng `getOrder()`. Nên chọn một nguồn cấu hình rõ ràng để người bảo trì dễ xác định mức ưu tiên thực tế.

## 6. @Order không quyết định thứ tự khởi tạo bean

Không nên dùng `@Order` để yêu cầu Spring khởi tạo bean A trước bean B. Hai vấn đề này thuộc các cơ chế khác nhau:

| Cơ chế | Mục đích |
|---|---|
| `@Order` trên method `@EventListener` | Sắp xếp listener khi phân phối event. |
| `@Order` trên class hoặc `Ordered` | Cung cấp thứ tự cho các cơ chế Spring có hỗ trợ ordering. |
| Constructor injection | Khai báo dependency giữa các bean. |
| `@DependsOn` | Khai báo bean cần được khởi tạo trước bean phụ thuộc. |
| `SmartLifecycle#getPhase()` | Sắp xếp thứ tự start và stop của lifecycle component. |

Nếu một bean cần bean khác, hãy thể hiện dependency qua constructor injection hoặc cơ chế lifecycle phù hợp. Việc đặt `@Order(1)` trên component không thay thế dependency graph của Spring.

## 7. Thứ tự với listener đồng bộ

Mặc định, `SimpleApplicationEventMulticaster` gọi listener đồng bộ trong thread phát event khi không cấu hình executor. Trong trường hợp này, các listener được dispatch theo order; lời gọi listener trước hoàn tất trước khi multicaster chuyển sang listener tiếp theo.

Điều đó có thể hữu ích khi các bước cần chạy tuần tự trong cùng thread. Tuy nhiên, `@Order` không biến nhiều listener thành một transaction chung. Nếu listener thứ hai thất bại, các side effect mà listener đầu đã thực hiện bên ngoài transaction vẫn có thể tồn tại.

Với multicaster mặc định không có `ErrorHandler`, exception từ listener đồng bộ có thể thoát khỏi quá trình dispatch và ngăn các listener tiếp theo được gọi. Nếu cấu hình `ErrorHandler`, việc dispatch có tiếp tục hay không phụ thuộc cách handler xử lý exception. Hãy xác định rõ listener nào là bắt buộc và chính sách lỗi của từng bước.

## 8. Thứ tự với listener bất đồng bộ

Có hai cách phổ biến để listener chạy bất đồng bộ:

- Đặt `@Async` trên method listener để async proxy gửi phần thực thi sang executor.
- Cấu hình `TaskExecutor` cho `SimpleApplicationEventMulticaster` để multicaster gửi các listener hỗ trợ async sang executor.

Order có thể quyết định thứ tự các adapter được xét và task được submit. Nó không bảo đảm thứ tự task bắt đầu hoặc hoàn tất khi có nhiều thread.

Ví dụ:

```java
@Async
@EventListener
@Order(10)
public void sendEmail(OrderPlaced event) {
    // Xử lý trên executor.
}
```

Task của listener order 10 có thể được submit trước task order 20, nhưng task 20 vẫn có thể hoàn tất trước nếu task 10 chậm hơn. Không dùng `@Order` để tạo phụ thuộc kiểu “bước B chỉ chạy sau khi bước A thành công” trong xử lý async.

Khi cần điều phối tuần tự, hãy gọi một service điều phối rõ ràng hoặc kết hợp Future/CompletableFuture để bước sau phụ thuộc vào kết quả bước trước. Với listener async trả về `void`, lỗi không tự truyền về publisher; cấu hình `AsyncUncaughtExceptionHandler` nếu cần xử lý tập trung.

## 9. Kết hợp với @TransactionalEventListener

`@TransactionalEventListener` cũng là một loại event listener và có thể dùng ordering để sắp xếp các callback cùng được kích hoạt. Tuy nhiên, `TransactionPhase` quyết định thời điểm callback được gọi so với transaction; `@Order` chỉ quyết định thứ tự ưu tiên trong nhóm callback phù hợp.

Ví dụ:

```java
@Component
public class OrderTransactionListeners {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Order(10)
    public void updateSearchIndex(OrderPlaced event) {
        // Callback sau commit.
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Order(20)
    public void publishNotification(OrderPlaced event) {
        // Callback sau commit, có order thấp hơn về ưu tiên.
    }
}
```

Listener `AFTER_COMMIT` không được gọi trước commit chỉ vì nó có `@Order(1)`. Nếu hai listener thuộc hai phase khác nhau, phase của transaction quyết định thời điểm thực thi; order không thay thế phase.

## 10. Listener trả về một event khác

Một method `@EventListener` có thể trả về một object event thay vì `void`. Spring sẽ publish giá trị trả về như một event mới; nếu method trả về array hoặc collection, các phần tử được publish thành các event riêng.

```java
@EventListener
@Order(10)
public InventoryCheckRequested onOrderPlaced(OrderPlaced event) {
    return new InventoryCheckRequested(event.orderId());
}
```

Order ở đây sắp xếp listener nhận `OrderPlaced`. Các listener nhận `InventoryCheckRequested` được sắp xếp trong lần dispatch mới theo order của chính chúng.

Với method listener được đánh dấu `@Async`, không thể dùng giá trị trả về của method để publish event tiếp theo theo cơ chế return-value của `@EventListener`. Nếu cần publish từ async method, inject `ApplicationEventPublisher` và gọi `publishEvent` rõ ràng.

## 11. Ví dụ Java 17 + Spring Context chạy được

Ví dụ này tạo một event payload dạng record và ba method listener trong cùng một bean. Các method được gán order 10, 20 và 30 để thể hiện thứ tự dispatch.

Cấu trúc project:

```text
event-order-demo/
├── pom.xml
└── src/main/java/com/example/events/
    ├── Application.java
    ├── OrderPlaced.java
    └── OrderListeners.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>event-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.0</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
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
                    <mainClass>com.example.events.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**OrderPlaced.java**

```java
package com.example.events;

public record OrderPlaced(String orderId) {
}
```

**OrderListeners.java**

```java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class OrderListeners {

    @EventListener
    @Order(10)
    public void validate(OrderPlaced event) {
        System.out.println("10 validate: " + event.orderId());
    }

    @EventListener
    @Order(20)
    public void reserveInventory(OrderPlaced event) {
        System.out.println("20 reserve: " + event.orderId());
    }

    @EventListener
    @Order(30)
    public void writeAudit(OrderPlaced event) {
        System.out.println("30 audit: " + event.orderId());
    }
}
```

**Application.java**

```java
package com.example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Application {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderListeners.class)) {
            context.publishEvent(new OrderPlaced("ORD-42"));
        }
    }
}
```

Chạy bằng Java 17 và Maven:

```bash
mvn -q compile exec:java
```

Stdout:

```text
10 validate: ORD-42
20 reserve: ORD-42
30 audit: ORD-42
```

Kết quả cho thấy listener order 10 được gọi trước order 20, rồi đến order 30. Vì cả ba method chạy đồng bộ trong ví dụ, output phản ánh đúng thứ tự hoàn tất từng lời gọi.

## 12. Kiểm thử thứ tự listener

Nên kiểm thử qua ApplicationContext thật để xác nhận Spring đã phát hiện annotation, đăng ký listener adapter và phân phối event đúng cách:

1. Đăng ký các bean listener cùng nhận một event type.
2. Gán order khác nhau cho những listener cần thứ tự ổn định.
3. Publish một event qua ApplicationContext.
4. Ghi lại ID hoặc tên bước trong một collection dùng chung của test.
5. So sánh danh sách thực tế với thứ tự mong đợi.
6. Kiểm thử riêng exception của listener đồng bộ và listener async.

Ví dụ assertion cho phần kiểm thử:

```java
assertEquals(List.of("validate", "reserve", "audit"), calls);
```

Đây là assertion minh họa; test đầy đủ cần khởi tạo context, đăng ký listener và publish event. Với listener async, hãy đợi task hoàn tất bằng latch hoặc Future trước khi kiểm tra collection. Không dùng `Thread.sleep` cố định để suy đoán task đã chạy xong.

Không viết test yêu cầu một thứ tự cụ thể giữa hai listener có cùng order. Nếu thứ tự đó quan trọng, hãy gán hai giá trị khác nhau.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Order 20 chạy trước order 10 | Hiểu ngược quy tắc ưu tiên | Số nhỏ hơn được gọi trước. |
| Listener mặc định chạy không ổn định tương đối với listener khác | Nhiều listener cùng mức `LOWEST_PRECEDENCE` | Gán order riêng cho các bước cần thứ tự. |
| Thứ tự method trong source quyết định kết quả | Dựa vào thứ tự khai báo method | Đặt `@Order` trên từng method listener. |
| Bean khởi tạo không theo order | Dùng `@Order` để điều khiển dependency | Dùng constructor injection, `@DependsOn` hoặc lifecycle phase. |
| Async task hoàn tất sai thứ tự | Nhầm thứ tự submit với thứ tự hoàn tất | Dùng service điều phối hoặc compose Future. |
| Listener sau không chạy khi listener trước lỗi | Exception đồng bộ thoát khỏi multicaster | Xác định chính sách ErrorHandler và xử lý lỗi. |
| Hai listener cùng order nhưng test lúc pass lúc fail | Test dựa vào thứ tự không được cam kết | Gán order khác nhau. |
| Listener ở event khác bị xếp chung một chuỗi | Nhầm các lần dispatch riêng biệt | Dùng workflow/service nếu cần điều phối liên event. |

## 14. Checklist triển khai

1. Xác định các listener cùng nhận một event và cần thứ tự gọi.
2. Đặt `@Order` trực tiếp trên method `@EventListener`.
3. Dùng số nhỏ hơn cho listener cần được gọi trước.
4. Dùng các giá trị khác nhau khi thứ tự tương đối có ý nghĩa.
5. Hiểu listener không khai báo order dùng `Ordered.LOWEST_PRECEDENCE`.
6. Với `ApplicationListener`, dùng class-level `@Order` hoặc `Ordered#getOrder()`.
7. Không dùng `@Order` để điều khiển khởi tạo bean hoặc thay thế dependency injection.
8. Với async listener, phân biệt thứ tự dispatch, submit, bắt đầu và hoàn tất task.
9. Xác định hành vi khi listener đồng bộ ném exception.
10. Dùng workflow/service điều phối khi bước sau phụ thuộc kết quả bước trước.
11. Kiểm thử bằng ApplicationContext thật và tránh phụ thuộc thứ tự giữa listener có cùng order.

## 15. Tài liệu tham khảo

- [Spring Framework Reference — Ordering Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — @Order Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/annotation/Order.html)
- [Spring Framework 6.2 — @EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — Ordered Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/Ordered.html)

`@Order` giúp khai báo ưu tiên rõ ràng cho listener cùng xử lý một event. Dùng số nhỏ cho listener cần được gọi trước, giữ giá trị khác nhau khi thứ tự có ý nghĩa, và dùng cơ chế điều phối riêng cho công việc async hoặc các bước phụ thuộc kết quả.
