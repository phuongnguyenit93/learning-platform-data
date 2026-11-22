# Không biến annotation thành nơi chứa quy tắc nghiệp vụ khó theo dõi trong Spring AOP

Khi viết custom annotation cho **Spring AOP**, một sai lầm dễ gặp là gom các quyết định nghiệp vụ vào annotation rồi để aspect âm thầm thực thi. Cú pháp trông ngắn gọn, nhưng người đọc method không thấy điều kiện nào quyết định kết quả; việc kiểm thử, thay đổi chính sách và tìm lỗi cũng trở nên khó khăn. Annotation nên thể hiện **ý định gắn một mối quan tâm cắt ngang** (cross-cutting concern), còn quy tắc quyết định nghiệp vụ nên xuất hiện rõ trong service hoặc lớp policy chuyên trách.

Phạm vi bài này là cách thiết kế **custom annotation kết hợp Spring AOP proxy và advice**. Các khái niệm AOP tổng quát không cần học lại ở đây.

## 1. Ranh giới trách nhiệm trong ứng dụng Spring

| Thành phần | Trách nhiệm nên có | Điều nên tránh |
| --- | --- | --- |
| Custom annotation, ví dụ `@AuditAction("create-order")` | Đánh dấu điểm cần áp dụng audit; mang metadata nhỏ, ổn định, dễ hiểu | Mã hóa bảng giá, phân hạng khách hàng, nhiều điều kiện quyết định duyệt đơn |
| Spring `@Aspect` và advice | Xử lý logging/audit/tracing/metric theo cùng một cách tại các method được đánh dấu | Quyết định đơn hàng hợp lệ, tính phí, đổi kết quả trả về vì chính sách kinh doanh |
| `OrderService` | Điều phối ca sử dụng, gọi policy một cách **tường minh** | Trông cậy vào aspect để gọi hộ kiểm tra nghiệp vụ |
| `OrderPolicy` (hoặc domain service) | Đặt quy tắc ở một nơi có tên rõ ràng, kiểm thử độc lập với Spring proxy | Dồn quy tắc vào chuỗi tên annotation hay xử lý vòng quanh method một cách khó thấy |

Spring AOP thường áp dụng advice khi lời gọi method **đi qua Spring proxy**. Vì vậy nếu bảo vệ một bất biến nghiệp vụ chỉ bằng aspect, lời gọi không đi qua proxy có thể bỏ qua kiểm tra. Một service có lời gọi trực tiếp tới policy thì vẫn thể hiện quy tắc ngay trong luồng nghiệp vụ.

## 2. Phản ví dụ: annotation mang cả chính sách kinh doanh

Giả sử ứng dụng cần kiểm tra đơn hàng trên 200 đơn vị tiền tệ chỉ được tạo bởi khách premium. Thiết kế sau là **minh họa điều cần tránh**, không phải chương trình chạy độc lập:

```java
// API gây hiểu nhầm: chính sách được đẩy vào metadata trên method.
@AcceptOrder(maxAmountForBasicMember = 200, requirePremiumAboveLimit = true)
public String createOrder(int amount, boolean premium) {
    return "APPROVED";
}
```

Nếu một `@Around` advice đọc các tham số này rồi âm thầm chặn đơn hàng, thân `createOrder` có vẻ luôn chấp nhận. Vấn đề thực tế:

- **Luồng điều khiển bị giấu:** từ method không thể thấy việc kiểm tra hạng khách hàng, nơi phát sinh exception hoặc quy tắc ưu tiên giữa các điều kiện.
- **Chính sách khó thay đổi:** thêm khuyến mãi, hạn mức theo khu vực hoặc theo thời điểm buộc mở rộng annotation và aspect, tạo ra một bộ máy nghiệp vụ ngoài service.
- **Kiểm thử dễ sai tầng:** test gọi trực tiếp đối tượng service bằng `new` sẽ không chạy Spring advice; kết quả có thể khác khi bean đi qua proxy.
- **Tái sử dụng khó:** API khác cần cùng quy tắc nhưng không sử dụng cùng annotation hoặc proxy sẽ phải lặp logic.
- **Khó truy vết:** người bảo trì cần lần theo pointcut và advice mới biết vì sao thao tác bị từ chối.

Tham số annotation không tự động trở thành xấu: tên sự kiện audit, tag metric hay tên thao tác là metadata hợp lý. Điểm quyết định là **nó có điều khiển kết quả nghiệp vụ hay không**.

## 3. Thiết kế khuyến nghị: policy rõ ràng, annotation phục vụ audit

Ví dụ dưới đây dùng **Java 17+**, một ứng dụng **Spring Boot 3.x** có `spring-boot-starter-aop`. Cấu trúc:

```text
src/main/java/com/example/aopaudit/
├── DemoApplication.java
├── AuditAction.java
├── AuditAspect.java
├── OrderPolicy.java
└── OrderService.java
```

Trong dự án Spring Boot dùng Maven, thêm dependency này nếu chưa có (phiên bản được quản lý bởi Spring Boot parent/BOM):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Với Gradle, dependency tương đương là `implementation 'org.springframework.boot:spring-boot-starter-aop'`. Dự án cũng cần Spring Boot starter để chạy ứng dụng. Với cấu hình Boot thông dụng, starter AOP cung cấp các annotation `@Aspect` và support cần thiết cho Spring proxy.

**Tệp `AuditAction.java` — annotation chỉ là dấu hiệu audit:**

```java
package com.example.aopaudit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditAction {
    String value();
}
```

`@Target(METHOD)` giới hạn annotation vào method. `@Retention(RUNTIME)` cho phép Spring/AspectJ nhận diện nó trong quá trình thực thi. `value` là tên hành động phục vụ quan sát, **không phải hạn mức hay điều kiện duyệt đơn**.

**Tệp `OrderPolicy.java` — nơi thực thi quyết định nghiệp vụ:**

```java
package com.example.aopaudit;

import org.springframework.stereotype.Component;

@Component
public class OrderPolicy {
    public void check(int amount, boolean premium) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (amount > 200 && !premium) {
            throw new IllegalArgumentException(
                "Premium required for amount over 200"
            );
        }
    }
}
```

Đây là ví dụ chính sách đơn giản có chủ ý: amount phải dương; nếu amount lớn hơn 200, khách phải premium. Trong hệ thống thật, quy tắc có thể sử dụng một domain model và các lớp policy chuyên biệt. Dù chính sách phức tạp hơn, cách gọi vẫn minh bạch.

**Tệp `OrderService.java` — gọi policy ngay trong method:**

```java
package com.example.aopaudit;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderPolicy policy;

    public OrderService(OrderPolicy policy) {
        this.policy = policy;
    }

    @AuditAction("create-order")
    public String createOrder(int amount, boolean premium) {
        policy.check(amount, premium);
        return "APPROVED";
    }
}
```

Ngay cả khi bạn đọc riêng `OrderService`, bạn vẫn thấy `policy.check(...)` được gọi trước khi chấp nhận. Annotation chỉ yêu cầu bổ sung audit; bỏ annotation không làm thay đổi quy tắc duyệt đơn.

**Tệp `AuditAspect.java` — advice chỉ quan sát kết quả:**

```java
package com.example.aopaudit;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Around("@annotation(auditAction)")
    public Object audit(ProceedingJoinPoint joinPoint, AuditAction auditAction)
            throws Throwable {
        String action = auditAction.value();
        System.out.println("AUDIT start " + action);
        try {
            Object result = joinPoint.proceed();
            System.out.println("AUDIT success " + action);
            return result;
        } catch (Throwable failure) {
            System.out.println(
                "AUDIT failure " + action + ": " +
                    failure.getClass().getSimpleName()
            );
            throw failure;
        }
    }
}
```

`@Around("@annotation(auditAction)")` chọn các method có `@AuditAction` và bind annotation vào tham số advice. Gọi `joinPoint.proceed()` đúng một lần; trả về giá trị gốc và ném lại lỗi gốc. Aspect **không thay đổi** điều kiện premium, không trả về trạng thái giả và không nuốt exception. `System.out` chỉ để minh họa đầu ra dễ quan sát; ứng dụng thực tế nên dùng logger/audit sink phù hợp, tránh ghi dữ liệu cá nhân hoặc bí mật.

**Tệp `DemoApplication.java` — chạy hai tình huống:**

```java
package com.example.aopaudit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService orderService) {
        return args -> {
            System.out.println(
                "RESULT " + orderService.createOrder(150, false)
            );

            try {
                orderService.createOrder(500, false);
            } catch (IllegalArgumentException failure) {
                System.out.println("REJECTED " + failure.getMessage());
            }
        };
    }
}
```

Chạy trong dự án Boot đã cấu hình dependency:

```bash
./mvnw spring-boot:run
# Hoặc với dự án Gradle:
./gradlew bootRun
```

Trên Windows dùng `mvnw.cmd spring-boot:run` hoặc `gradlew.bat bootRun`. Ngoài log khởi động của Spring, phần output do ví dụ tạo ra theo thứ tự:

```text
AUDIT start create-order
AUDIT success create-order
RESULT APPROVED
AUDIT start create-order
AUDIT failure create-order: IllegalArgumentException
REJECTED Premium required for amount over 200
```

Ở lần gọi đầu, policy cho phép 150 với khách thường. Ở lần hai, `OrderPolicy.check` ném lỗi; aspect ghi nhận thất bại rồi ném lại lỗi để caller xử lý. Không có quyết định nghiệp vụ nào được tạo trong aspect.

> Giả định khi chạy ví dụ: dùng dependency quản lý bởi Spring Boot 3.x và build có thông tin tên tham số để bind `auditAction` (cấu hình chuẩn của Spring Boot build thông thường). Nếu dùng build tùy biến và gặp lỗi không xác định tên tham số advice, bật compiler flag `-parameters` hoặc khai báo `argNames` theo hướng dẫn Spring AOP.

## 4. Refactor khi đã có annotation chứa nghiệp vụ

Nếu code hiện tại dùng annotation kiểu `@AcceptOrder(...)`, nên chuyển từng trách nhiệm về đúng chỗ:

1. **Liệt kê hành vi thật sự:** xác định điều kiện nào chấp nhận/từ chối đơn, exception nào được ném, phụ thuộc vào dữ liệu nào, và logging/audit đang làm gì.
2. **Trích xuất chính sách thành API có tên nghiệp vụ:** ví dụ `OrderPolicy.check(amount, premium)` hoặc `EligibilityPolicy.evaluate(customer, order)`, với input/output minh bạch.
3. **Gọi policy trực tiếp từ use case/service:** tất cả entry point tạo đơn cần đi qua nghiệp vụ này; viết test cho các trường hợp biên.
4. **Giữ annotation cho concern kỹ thuật:** nếu vẫn cần audit, đổi thành metadata kiểu `@AuditAction("create-order")`; aspect chỉ log thành công/thất bại.
5. **Xóa logic nghiệp vụ khỏi advice sau khi đã đối chiếu hành vi:** không để kiểm tra tồn tại hai nơi với hai chính sách khác nhau.

Ví dụ khác: `@ApplyDiscount(level = "VIP", percentage = 15)` khiến aspect tự sửa giá là dấu hiệu quy tắc giá bị che giấu. Service nên gọi `pricingPolicy.calculatePrice(...)`; một `@TrackOperation("price-quote")` có thể đánh dấu thời điểm cần metric mà không quyết định giá.

## 5. Đặc thù Spring AOP cần nhớ

- **Self-invocation:** gọi `this.createOrder(...)` từ method khác trong cùng bean thường không đi qua Spring proxy, vì thế `@AuditAction` có thể không kích hoạt advice. Bất biến nghiệp vụ vẫn phải dựa vào lời gọi `policy.check(...)` trong service. Đừng dùng AOP proxy như hàng rào duy nhất cho chính sách.
- **Method visibility và proxy:** Spring AOP advice chỉ hoạt động trên method có thể được proxy intercept; ví dụ ưu tiên public method trên bean do Spring quản lý. Các lời gọi qua `new OrderService(...)` không có audit advice, nhưng logic policy vẫn chạy.
- **Không dùng annotation để giả vờ bảo mật:** kiểm tra quyền truy cập có thể dùng cơ chế Spring Security như `@PreAuthorize` được cấu hình đúng, nhưng quy tắc miền như hạn mức chi tiêu hoặc khả năng đặt hàng cần có vị trí rõ ràng trong mô hình nghiệp vụ; đừng tự viết custom aspect mơ hồ để thay cơ chế bảo mật.
- **Thứ tự advice và transaction:** nếu audit cần lưu chắc chắn sau khi transaction commit, một `@Around` log “success” khi method trả về chưa chắc đồng nghĩa dữ liệu đã commit. Cân nhắc application event sau commit hoặc `@TransactionalEventListener(phase = AFTER_COMMIT)` theo nhu cầu thực tế.
- **Giữ metadata nhỏ và ổn định:** tên sự kiện, loại audit, tag observability có thể là attribute annotation; quy tắc thường xuyên thay đổi theo khách hàng, thị trường hoặc dữ liệu nên đặt trong service/policy.
- **Minh bạch lỗi:** advice quan sát thất bại, giữ nguyên exception và kết quả; chỉ biến đổi kết quả khi đó là hành vi cross-cutting được thiết kế, đặt tên và kiểm thử rõ ràng.

## 6. Kiểm thử để bảo đảm annotation không nắm quyền nghiệp vụ

Phần quyết định nên test **không cần Spring context**, nhờ đó kết quả không phụ thuộc cách gọi qua proxy. Ví dụ JUnit 5 cho `OrderService`, có sẵn nếu thêm `spring-boot-starter-test` vào scope test:

```java
package com.example.aopaudit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    private final OrderService service =
        new OrderService(new OrderPolicy());

    @Test
    void regularCustomerCanPlaceSmallOrder() {
        assertEquals("APPROVED", service.createOrder(150, false));
    }

    @Test
    void regularCustomerCannotPlaceLargeOrder() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.createOrder(500, false)
        );
    }

    @Test
    void amountMustBePositive() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.createOrder(0, true)
        );
    }
}
```

Test này cố ý khởi tạo trực tiếp `OrderService`: không có proxy hay aspect, nhưng policy vẫn hoạt động. Test riêng dạng Spring integration, ví dụ `@SpringBootTest` cùng bean thật, để xác nhận advice bắt được annotation khi đi qua proxy và không làm đổi kết quả/exception. Đừng để audit log là bằng chứng duy nhất rằng đơn hàng đã được duyệt đúng.

## 7. Checklist rà soát thiết kế

- Khi đọc method service, có thấy lời gọi đến lớp quyết định nghiệp vụ, điều kiện và lỗi quan trọng không?
- Xóa hoặc tắt annotation audit có làm khác kết quả nghiệp vụ không? **Không nên.**
- Gọi service trực tiếp không qua Spring proxy có bỏ qua chính sách miền không? **Không được.**
- Aspect có chỉ thực thi concern đã được nêu rõ, và có trả kết quả/ném lỗi chính xác từ `proceed()` không?
- Attribute annotation có chỉ là metadata kỹ thuật, thay vì công thức/điều kiện dùng để tính giá, duyệt đơn hoặc thay đổi trạng thái không?
- Có unit test cho policy độc lập và integration test riêng cho Spring AOP interception không?

**Nguyên tắc áp dụng:** Với custom annotation trong Spring AOP, hãy để annotation trả lời *“method này cần áp dụng concern nào?”*, aspect trả lời *“concern đó được xử lý ra sao?”*, còn service/policy trả lời *“nghiệp vụ có cho phép và phải làm gì?”*. Nhờ vậy code thể hiện đúng luồng xử lý, test được cả khi không chạy Spring và ít phát sinh luật ngầm.