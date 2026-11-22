# Vai trò của Spring AOP đối với hành vi dùng chung trên các bean

## 1. Spring AOP giải quyết vấn đề gì trong ứng dụng Spring?

Trong ứng dụng Spring, nhiều bean nghiệp vụ có thể cần cùng một hành vi kỹ thuật: ghi nhật ký gọi phương thức, đo thời gian, kiểm tra chính sách truy cập, thu thập metric hoặc áp dụng một quy tắc vận hành xuyên suốt nhiều service. Nếu mỗi service tự lặp lại phần mã này, logic nghiệp vụ bị trộn với logic hạ tầng; mỗi thay đổi phải sửa ở nhiều nơi và dễ thiếu nhất quán.

**Spring AOP (Aspect-Oriented Programming)** cho phép đặt hành vi dùng chung ở một **aspect được Spring quản lý**, rồi áp dụng nó lên những lần thực thi phương thức bean phù hợp. Service tập trung vào việc nghiệp vụ của mình; aspect giữ trách nhiệm chung và Spring nối hai phần thông qua **proxy**.

Ví dụ: `OrderService.placeOrder()` và `InvoiceService.issueInvoice()` đều cần ghi dấu trước khi xử lý. Spring AOP cho phép viết một advice ghi dấu dùng chung, thay vì chép lệnh log vào cả hai service.

Phạm vi bài này là **cơ chế và cách dùng Spring AOP trên Spring beans**. Các lý thuyết AOP tổng quát hoặc AspectJ weaving độc lập với Spring nằm ngoài trọng tâm.

## 2. Spring ghép hành vi chung vào bean như thế nào?

Trong cấu hình Spring AOP dựa trên proxy, một lời gọi phù hợp có đường đi khái quát:

```text
Bean gọi (controller, service khác, command runner...)
        |
        v
Spring AOP proxy của bean đích
        |
        +--> Xét pointcut: lời gọi phương thức này có khớp không?
                 |
                 +--> Có: chạy advice tương ứng
                 |           |
                 |           v
                 |       Phương thức của bean đích
                 |           |
                 |           v
                 |       Advice sau lời gọi (nếu có)
                 |
                 +--> Không: chuyển thẳng đến bean đích
        |
        v
Trả kết quả hoặc ném ngoại lệ về bên gọi
```

Những thành phần cần nhận diện khi đọc code Spring AOP:

| Thành phần Spring AOP | Vai trò cụ thể trong ứng dụng |
| --- | --- |
| **Target bean** | Bean chứa phương thức nghiệp vụ, ví dụ `OrderService`. |
| **Proxy** | Đối tượng đại diện do Spring tạo, chặn lời gọi đến phương thức phù hợp và điều phối advice. |
| **Aspect** | Bean mang `@Aspect`, tổ chức các quy tắc can thiệp dùng chung. |
| **Pointcut** | Biểu thức chọn phương thức/lần thực thi sẽ được áp dụng, ví dụ các phương thức public của lớp `*Service`. |
| **Advice** | Mã chạy trước, sau hoặc bao quanh phương thức đích. |
| **Join point** | Trong **Spring AOP**, join point được hỗ trợ là **lần thực thi phương thức** của Spring bean. |

Hệ quả quan trọng: Spring AOP thường **không sửa trực tiếp mã nguồn hay bytecode của class nghiệp vụ**. Tương tác phải đi qua proxy thì advice mới có cơ hội chạy; đây là cơ sở để hiểu giới hạn trong phần 6.

## 3. Ví dụ chạy được: một aspect cho hai service bean

Ví dụ dùng **Java 17+, Spring Framework 6.1.14 và Maven**. Ứng dụng khởi động Spring container nhỏ bằng `AnnotationConfigApplicationContext`, không cần Spring Boot hoặc máy chủ web.

Cấu trúc:

```text
spring-aop-beans/
├── pom.xml
└── src/main/java/com/example/demo/
    ├── DemoApp.java
    ├── OrderService.java
    ├── InvoiceService.java
    └── SharedAuditAspect.java
```

**`pom.xml`** — `spring-context` cung cấp container và tích hợp Spring AOP; `aspectjweaver` cung cấp các kiểu và bộ phân tích biểu thức AspectJ mà Spring AOP sử dụng cho cú pháp `@Aspect`.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-beans</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/demo/OrderService.java`**

```java
package com.example.demo;

public class OrderService {
    public void placeOrder(String orderId) {
        System.out.println("[ORDER] created " + orderId);
    }
}
```

**`src/main/java/com/example/demo/InvoiceService.java`**

```java
package com.example.demo;

public class InvoiceService {
    public void issueInvoice(String orderId) {
        System.out.println("[INVOICE] created for " + orderId);
    }
}
```

**`src/main/java/com/example/demo/SharedAuditAspect.java`**

```java
package com.example.demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class SharedAuditAspect {
    @Before("execution(public * com.example.demo.*Service.*(..))")
    public void recordCall(JoinPoint joinPoint) {
        System.out.println("[AUDIT] " + joinPoint.getSignature().getName());
    }
}
```

Biểu thức `execution(public * com.example.demo.*Service.*(..))` chọn các lần thực thi phương thức `public` có kiểu trả về bất kỳ (`*`), thuộc các class có tên kết thúc bằng `Service` trong đúng package `com.example.demo`; tên phương thức và danh sách tham số đều có thể khác nhau. Đây là **quy tắc dùng chung cho nhiều bean**, không gắn cứng vào một phương thức. Trong ứng dụng thực, nên giới hạn pointcut sát trách nhiệm cần áp dụng để tránh chặn quá nhiều lời gọi.

**`src/main/java/com/example/demo/DemoApp.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class DemoApp {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public InvoiceService invoiceService() {
        return new InvoiceService();
    }

    @Bean
    public SharedAuditAspect sharedAuditAspect() {
        return new SharedAuditAspect();
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(DemoApp.class)) {
            OrderService orderService = context.getBean(OrderService.class);
            InvoiceService invoiceService = context.getBean(InvoiceService.class);

            orderService.placeOrder("O-42");
            invoiceService.issueInvoice("O-42");
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml` (cần JDK 17+ và Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.demo.DemoApp
```

Các dòng do chương trình in ra, theo đúng thứ tự:

```text
[AUDIT] placeOrder
[ORDER] created O-42
[AUDIT] issueInvoice
[INVOICE] created for O-42
```

**Giải thích kết quả:** hai service hoàn toàn không gọi `SharedAuditAspect`. Container đăng ký ba bean, `@EnableAspectJAutoProxy` kích hoạt hạ tầng tự tạo proxy, Spring phát hiện bean `@Aspect` và lựa chọn advice cho từng phương thức phù hợp. `context.getBean(...)` trả về tham chiếu bean đã được Spring xử lý; lời gọi từ ngoài đi qua proxy nên có dòng `[AUDIT]` trước mỗi dòng nghiệp vụ. Việc dùng `proxyTargetClass = true` chọn proxy dựa trên lớp cho ví dụ có service không khai báo interface.

Nếu bỏ đăng ký aspect hoặc vô hiệu hóa hạ tầng AOP, hai phương thức nghiệp vụ vẫn có thể thực thi, nhưng các dòng `[AUDIT]` do advice tạo sẽ không xuất hiện.

## 4. Các kiểu advice phục vụ hành vi dùng chung

| Advice | Thời điểm và ứng dụng phù hợp |
| --- | --- |
| `@Before` | Trước khi phương thức đích chạy; ghi dấu lời gọi, kiểm tra tiền điều kiện đơn giản. |
| `@AfterReturning` | Khi phương thức trả về bình thường; theo dõi thành công hoặc kết quả. |
| `@AfterThrowing` | Khi phương thức ném ngoại lệ; ghi nhận lỗi theo chính sách. |
| `@After` | Khi lần thực thi kết thúc dù thành công hay lỗi; dọn dẹp/ghi dấu kết thúc, tương tự tinh thần `finally`. |
| `@Around` | Bao quanh lời gọi, có thể quyết định khi nào gọi `proceed()`, đo thời gian, xử lý kết quả/ngoại lệ. |

Ví dụ minh họa `@Around` khi thật sự cần điều khiển cả trước và sau:

```java
@Around("execution(public * com.example.demo.*Service.*(..))")
public Object timeCall(org.aspectj.lang.ProceedingJoinPoint pjp)
        throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed(); // Phải gọi để nghiệp vụ thực sự chạy.
    } finally {
        long elapsedNanos = System.nanoTime() - started;
        // Gửi elapsedNanos tới hệ thống metric phù hợp.
    }
}
```

Đây là **đoạn phương thức minh họa**, đặt bên trong một bean `@Aspect` cùng với import `org.aspectj.lang.annotation.Around`; nó không phải chương trình độc lập và **không được thêm nguyên xi cạnh advice `@Before` của ví dụ mà mong stdout giữ nguyên**. `try/finally` đảm bảo khâu đo kết thúc được thực hiện cả khi phương thức ném lỗi; `proceed()` truyền tiếp thực thi xuống bean đích. Nếu cần advice đơn giản, ưu tiên `@Before`/`@AfterReturning` thay vì `@Around` để bớt kiểm soát luồng không cần thiết.

Trong cùng một lời gọi, thứ tự khi có nhiều aspect/advice còn tùy loại advice, mức ưu tiên (`@Order`/`Ordered`) và cấu hình. Khi thứ tự có ý nghĩa nghiệp vụ, phải xác định thứ tự tường minh và kiểm thử; không suy ra thứ tự chỉ từ thứ tự khai báo các phương thức.

## 5. Giá trị thực tế và ranh giới trách nhiệm

Spring AOP mang lại giá trị khi **một quy tắc áp dụng nhất quán cho nhiều bean hoặc nhiều phương thức**:

- **Quan sát vận hành:** ghi tên thao tác, thời gian thực thi, số lần gọi, tình trạng thành công/thất bại; dùng metadata phù hợp thay vì in mọi tham số nhạy cảm.
- **Quy tắc kỹ thuật tại ranh giới service:** kiểm tra một điều kiện chung, gắn metadata hoặc chuẩn hóa cách theo dõi lời gọi.
- **Tích hợp chính sách do Spring cung cấp:** các tính năng như giao dịch khai báo `@Transactional` có thể dùng interception/proxy tương tự; cần ưu tiên dùng cơ chế Spring chính thức thay vì tự viết aspect thay thế transaction manager, security interceptor hay cache abstraction.

Service phải vẫn thể hiện rõ tác vụ của nó: xác thực dữ liệu nghiệp vụ, tính toán, cập nhật trạng thái và quản lý invariant thuộc domain. Nếu logic chỉ áp dụng cho một use case, viết trực tiếp trong service hoặc component được gọi tường minh thường dễ hiểu hơn. AOP cũng không biến thao tác bất kỳ thành giao dịch, đồng bộ thread hay bảo đảm phân tán; advice chỉ cung cấp một điểm can thiệp vào phương thức đúng phạm vi.

Đặt pointcut quá rộng, ví dụ bắt mọi phương thức của toàn ứng dụng, có thể tạo chi phí không cần thiết, phụ thuộc ẩn và log ồn. Nên chọn package, interface, annotation hoặc tên phương thức dựa trên trách nhiệm thật sự cần chia sẻ, kèm kiểm thử cho các bean được chọn và không được chọn.

## 6. Những giới hạn cần nhận diện khi dùng chung advice

Spring AOP áp dụng advice tại **lời gọi phương thức đi qua proxy của Spring bean**, không thay đổi mọi đường thực thi Java. Trong ví dụ trên, hai lời gọi lấy từ `ApplicationContext` nhận được hành vi audit; bản thân hai lớp service không gọi aspect.

- **Gọi nội bộ:** nếu `ReportService.export()` gọi `this.validate()`, advice chỉ dành cho `validate()` sẽ không nhận được lời gọi nội bộ này. Muốn chặn `validate()` từ service khác, hãy gọi qua một bean được inject.
- **Đối tượng ngoài container:** `new OrderService().placeOrder("O-99")` chỉ chạy logic của đối tượng tự tạo, không tự nhận Spring AOP advice; ngược lại instance được **đăng ký bằng `@Bean`** vẫn có thể được proxy dù factory method dùng `new`.
- **Khả năng proxy:** JDK proxy công bố phương thức qua interface; CGLIB dùng subclass và không override được `final`/`private`. Constructor, field access và static method không thuộc các method-execution join point Spring AOP hỗ trợ.
- **Bất đồng bộ và lỗi:** `@AfterReturning` của method trả về `CompletableFuture` không chứng minh future đã hoàn tất thành công. Advice quan sát nên giữ nguyên giá trị trả về và exception, đồng thời dùng cơ chế phù hợp để đo thời điểm completion thật.

Các ranh giới trên giúp quyết định có nên tách hành vi sang bean khác hoặc dùng cơ chế Spring chuyên dụng. Phần cơ chế proxy, điều kiện quản lý bean và so sánh với AspectJ weaving được phân tích riêng ở các bài tương ứng.

## 7. Cách thiết kế và kiểm thử hành vi dùng chung

Một quy trình áp dụng Spring AOP an toàn:

1. **Xác định hành vi lặp thật sự:** ví dụ ghi audit ở các entry point service, phân biệt rõ dữ liệu nghiệp vụ với metadata kỹ thuật.
2. **Khoanh điểm áp dụng:** chọn đúng bean và method qua pointcut; nếu cần lựa chọn tường minh, tạo annotation riêng cho nhóm phương thức cần theo dõi.
3. **Chọn advice tối giản:** `@Before` cho dấu bắt đầu, `@AfterReturning`/`@AfterThrowing` cho kết quả, `@Around` khi phải quản lý toàn bộ vòng thực thi.
4. **Đảm bảo đường gọi qua container:** inject các service, gọi proxy từ bean khác, tránh `new` hoặc self-invocation đối với phương thức cần interception.
5. **Kiểm thử cả chiều có và không áp dụng:** gọi hai service khớp pointcut và một bean/method không khớp; kiểm tra số lần advice, thứ tự liên quan và nghiệp vụ trả đúng kết quả. Có thêm trường hợp lỗi để xác nhận advice không đổi ngoại lệ ngoài ý muốn.
6. **Quan sát khi vận hành:** tránh log thông tin nhạy cảm và dữ liệu có kích thước lớn; đo overhead nếu advice chạy trên đường nóng; ghi nhận khi một refactor đổi class/method khiến pointcut không còn khớp.

Ví dụ này cho thấy một thay đổi ở `SharedAuditAspect.recordCall()` có thể cập nhật hành vi audit của **cả `OrderService` và `InvoiceService`** mà không sửa code nghiệp vụ. Đó là vai trò cốt lõi của Spring AOP đối với hành vi dùng chung trên các bean: **tập trung quy tắc kỹ thuật, áp dụng nhất quán ở các phương thức Spring quản lý và giữ ranh giới nghiệp vụ rõ ràng**, đồng thời luôn tôn trọng giới hạn của proxy.
