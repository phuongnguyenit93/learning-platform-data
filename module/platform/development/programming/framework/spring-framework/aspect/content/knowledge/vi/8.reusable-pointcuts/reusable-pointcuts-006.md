# Đặt tên Pointcut theo ý định thay vì chi tiết chuỗi biểu thức trong Spring AOP

## 1. Mục tiêu

Trong Spring AOP, viết trực tiếp biểu thức dài vào `@Before` hoặc `@Around` có thể hoạt động đúng hôm nay, nhưng khó đọc và khó bảo trì. Khi biểu thức đó được sao chép ở nhiều advice, người sửa thường không biết nó đại diện cho **ý định nghiệp vụ nào**: giám sát tất cả thao tác nghiệp vụ, audit phê duyệt thanh toán, hay chỉ chặn method của một bean cụ thể?

Spring Framework cho phép định nghĩa **named pointcut** bằng `@Pointcut` đặt trên một phương thức Java trả về `void`, sau đó tham chiếu bằng tên trong advice hoặc kết hợp những pointcut nhỏ thành một pointcut có ý nghĩa hơn. Mục tiêu quan trọng nhất là để người đọc hiểu **vì sao các method ấy thuộc phạm vi advice**, thay vì phải giải mã chi tiết ký tự của một expression dài mỗi khi review code.

Bài này thuộc phần **Tổ chức Pointcut** của Spring Framework và chỉ tập trung vào Spring Aspect/Spring AOP dạng proxy, bao gồm:

1. Phân biệt **tên mô tả ý định** với **biểu thức hiện thực**.
2. Tổ chức các pointcut nhỏ và pointcut tổng hợp bằng `@Pointcut`.
3. Chia sẻ pointcut giữa các Spring aspect mà vẫn tôn trọng Java visibility.
4. Tránh đặt tên sai khiến code review bỏ sót thay đổi phạm vi áp dụng.
5. Viết ứng dụng Java 17+ chạy được để chứng minh một tên nghiệp vụ match đúng bean/method mong muốn.
6. Xây dựng kiểm thử tích cực và tiêu cực để có thể thay expression mà giữ nguyên hợp đồng của pointcut.

Các khái niệm Aspect chung không được lặp lại; trọng tâm là **Spring đọc named pointcut, tạo advisor và áp dụng lên Spring-managed beans**.

## 2. Tên pointcut trả lời câu hỏi gì?

So sánh hai cách viết một advice:

**Cách 1 — nhúng chi tiết expression trong advice:**

~~~java
@Before(
    "within(example.payment..*)"
    + " && execution(public * approve(..))"
)
public void audit() {
    System.out.println("audit");
}
~~~

**Cách 2 — tham chiếu tên thể hiện mục đích:**

~~~java
@Before("example.aop.PaymentPointcuts.paymentApprovalOperation()")
public void audit() {
    System.out.println("audit");
}
~~~

Ở cách 2, người đọc thấy ngay đó là **thao tác phê duyệt thanh toán**. Expression vẫn tồn tại ở nơi định nghĩa named pointcut nhưng không lặp lại trong mọi advice. Người duy trì có thể đổi cách nhận diện thao tác — theo package, kiểu, annotation hoặc tên bean — mà không phải viết lại nhiều advice.

**Tên pointcut là một hợp đồng ngữ nghĩa trong code**:

- Tên nên biểu đạt **tập method/bean mà advice định can thiệp**.
- Tên không nên mô tả trực tiếp **cú pháp sẽ dễ thay đổi** nếu cú pháp chỉ là một chi tiết triển khai.
- Tên càng công khai và được nhiều aspect tái sử dụng, càng cần ổn định, có tài liệu và kiểm thử phạm vi.
- **Tên không thay đổi kết quả matching.** Chính expression trong `@Pointcut` vẫn xác định các method thật sự được chọn.

Ví dụ: `paymentApprovalOperation()` là một tên có ý nghĩa nghiệp vụ; `executionStarApproveDotDot()` chỉ diễn giải ký tự expression. Tuy vậy, `allPaymentOperations()` **không phải** tên tốt nếu expression chỉ match `approve()`: tên rộng hơn thực tế gây hiểu nhầm.

## 3. Named pointcut trong Spring AOP vận hành như thế nào?

Định nghĩa named pointcut bằng method `void` với body thường rỗng; Spring dùng **expression metadata** làm điều kiện match, còn tên method cho phép advice diễn đạt mục đích rõ ràng:

```java
public class PaymentPointcuts {
    @Pointcut("within(example.payment..*) && execution(public * approve(..))")
    public void paymentApprovalOperation() {}
}
```

Ở một Spring-managed aspect, `@Before("example.aop.PaymentPointcuts.paymentApprovalOperation()")` tham chiếu định nghĩa này nếu class thật đặt trong package `example.aop`. Class chỉ lưu pointcut không cần là Spring bean; aspect có advice phải là bean. Bài **“Khai báo pointcut có tên bằng @Pointcut”** đi sâu vào signature, visibility, binding và cú pháp tham chiếu.

## 4. Đặt tên đúng: nhóm ý định và nhóm kỹ thuật

Không cần cấm mọi tên mô tả kỹ thuật. Điều nên tránh là biến **chi tiết expression** thành API công khai mà advice phụ thuộc vào, trong khi ý định nghiệp vụ thực sự bị ẩn.

| Tên | Đánh giá | Lý do |
| --- | --- | --- |
| `paymentApprovalOperation()` | Tốt nếu chỉ match phê duyệt thanh toán | Biểu đạt ý định của advice và có thể dùng khi refactor expression |
| `businessServiceOperation()` | Tốt nếu scope thật là tầng service nghiệp vụ | Phù hợp khi nhiều aspect dùng chung boundary service |
| `inPaymentModule()` | Tốt cho pointcut nhỏ phục vụ kết hợp | Mô tả một điều kiện scoping rõ ràng |
| `publicMethod()` | Tốt cho primitive pointcut dùng nội bộ | Thật thà về phạm vi kỹ thuật, nên phối hợp với scoping |
| `executionPublicStarStar()` | Nên tránh | Chỉ lặp lại cú pháp, khó hiểu mục đích nghiệp vụ |
| `allServices()` | Sai nếu expression chỉ chọn một class | Tên tạo kỳ vọng rộng hơn behavior |
| `secureOperation()` | Nguy hiểm nếu chỉ có pattern tên method | Hứa hẹn tính an toàn mà expression không chứng minh |
| `paymentOperation()` | Quá mơ hồ nếu chỉ chọn `approve()` | Người đọc dễ tưởng mọi method trong payment đều match |
| `pointcut1()` / `aopCheck()` | Không nên dùng | Không có thông tin phạm vi hay ý định |
| `forLogging()` | Cần xem lại | Nêu **hành động advice** chứ không chỉ rõ nơi advice phải chạy |

Với một tên public được dùng ở nhiều nơi, có thể kèm Javadoc: “chọn những public approve operations thuộc payment module” và mô tả **ngoại lệ** như không chọn preview, report hoặc lời gọi trên đối tượng ngoài Spring.

## 5. Tách pointcut theo tầng và kết hợp theo ý định

Spring Framework hỗ trợ tham chiếu named pointcut bằng tên và kết hợp bằng `&&`, `||`, `!`.

**Mẫu đề xuất:**

~~~text
Nhóm primitive pointcuts:
  inPaymentModule()
  publicApprovalMethod()
  hasAuditMarker()

          \______/  \_______/
                |
Nhóm intent pointcuts:
  paymentApprovalOperation()
  sensitiveBusinessOperation()
                |
             Advice
  @Before("...paymentApprovalOperation()")
  @AfterReturning("...paymentApprovalOperation()")
~~~

Một pointcut nghiệp vụ nên đặt ở lớp **gần module sở hữu hợp đồng**. Khi dùng chung trong hệ thống lớn, một lớp chuyên biệt như `CommonPointcuts` có thể cung cấp những boundary ổn định (tầng service/data access); một lớp `PaymentPointcuts` chuyên biệt có thể đặt các tên nghiệp vụ payment. Tránh tạo một tập “global utility pointcuts” quá lớn không có chủ sở hữu.

### 5.1. Quy tắc kết hợp cần review

| Biểu thức | Ý nghĩa | Tác động phạm vi |
| --- | --- | --- |
| `inPaymentModule() && publicApprovalMethod()` | Public approve method **trong** payment | Giao hai tập, thường hẹp hơn |
| `inPaymentModule() || publicApprovalMethod()` | Method thuộc payment **hoặc** public approve ở bất kỳ đâu | Rộng hơn, dễ audit nhầm |
| `inPaymentModule() && !publicApprovalMethod()` | Những method thuộc payment trừ approve | Có thể ngược ý định hoàn toàn |
| `inPaymentModule() && hasAuditMarker()` | Những method được đánh dấu trong module payment | Tốt khi chủ động chọn opt-in |
| `paymentApprovalOperation() && bean(primaryPaymentService)` | Thao tác approve của một Spring bean đúng tên | Hẹp hơn nhưng gắn với bean naming |

Khi muốn đổi từ method-name pattern sang annotation opt-in, chỉ đổi phần triển khai pointcut **sau khi** xác nhận rằng việc đổi tập match là có chủ đích hoặc các test chứng minh tập mong muốn không thay đổi. Không được coi tên pointcut là một lời cam kết được runtime tự kiểm tra.

### 5.2. Chọn đủ scoping để không match ngoài ý muốn

Biểu thức `execution(public * approve(..))` đứng riêng có thể match `approve()` của report, inventory hoặc user administration. Biểu thức `within(example.payment..*)` đứng riêng có thể match mọi method trong module thanh toán. Ghép bằng `&&` diễn đạt intent “phê duyệt thuộc payment”.

Spring AOP hỗ trợ **method execution trên Spring beans**, không hỗ trợ tất cả AspectJ designators. Đối với Spring proxy-based AOP, các lựa chọn thường gặp là `execution`, `within`, `this`, `target`, `args`, `@annotation` và `bean`. Đặc biệt `bean(...)` là phần mở rộng **riêng của Spring AOP**; không nên chuyển expression đó nguyên dạng sang AspectJ native weaving.

## 6. Ví dụ Java 17+ chạy được: một tên pointcut, hai loại advice

Ví dụ sử dụng:

- **Spring Framework 6.2.19**, Java **17+**, **AspectJ Weaver 1.9.25.1**.
- Một lớp khai báo named pointcuts **không phải Spring bean**.
- Một aspect được đăng ký **bằng `@Bean`**, có cả `@Before` và `@AfterReturning` cùng tham chiếu **một tên nghiệp vụ**.
- Hai Spring service beans và ba lời gọi để kiểm tra phạm vi positive/negative.
- `@EnableAspectJAutoProxy` với class-based proxy để dễ lấy concrete type trong chương trình minh họa.

### 6.1. Cấu trúc dự án

~~~text
spring-intent-pointcut-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── Main.java
    ├── aop/
    │   ├── PaymentPointcuts.java
    │   └── PaymentAuditAspect.java
    ├── payment/
    │   └── PaymentService.java
    └── report/
        └── ReportService.java
~~~

### 6.2. Maven: `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-intent-pointcut-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
~~~

Spring Framework BOM quản lý các module `spring-*` để không lệch phiên bản. AspectJ Weaver là dependency cho xử lý pointcut biểu thức trong Spring AOP `@AspectJ`; sự hiện diện của artifact không tự bật bytecode weaving.

### 6.3. Named pointcuts: `PaymentPointcuts.java`

~~~java
package example.aop;

import org.aspectj.lang.annotation.Pointcut;

public class PaymentPointcuts {

    @Pointcut("within(example.payment..*)")
    public void inPaymentModule() {}

    @Pointcut("execution(public * approve(..))")
    public void publicApprovalMethod() {}

    /**
     * Phê duyệt thanh toán: public approve method trên type
     * thuộc package example.payment hoặc các package con.
     */
    @Pointcut("inPaymentModule() && publicApprovalMethod()")
    public void paymentApprovalOperation() {}
}
~~~

Ba named pointcuts ở trên là **khai báo metadata**; không có lời gọi Java thông thường đến những method rỗng này. Tên tổng hợp `paymentApprovalOperation` sẽ được dùng trong advice. Nếu thay đổi cách biểu diễn module hay phương thức, nơi sửa nằm ở `PaymentPointcuts`, không rải trong mỗi aspect.

Vì các signature trên là `public`, chúng có thể được tham chiếu bằng **fully qualified name** từ lớp `@Aspect` khác. Không cần đánh dấu `PaymentPointcuts` bằng `@Component` hoặc đăng ký nó làm Spring bean chỉ để tham chiếu những pointcut definitions đã khai báo.

### 6.4. Aspect: `PaymentAuditAspect.java`

~~~java
package example.aop;

import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class PaymentAuditAspect {

    @Before("example.aop.PaymentPointcuts.paymentApprovalOperation()")
    public void beforePaymentApproval() {
        System.out.println("audit: before payment approval");
    }

    @AfterReturning("example.aop.PaymentPointcuts.paymentApprovalOperation()")
    public void afterPaymentApproval() {
        System.out.println("audit: after payment approval");
    }
}
~~~

Hai advice có cách thức thực thi khác nhau nhưng chia sẻ **một ý định chọn method**. Nếu bạn đổi expression tại `PaymentPointcuts.paymentApprovalOperation()`, cả hai advice đều cùng nhận phạm vi mới.

Chỉ `@Aspect` trên class này chưa đủ để Spring scan thành bean; ví dụ đăng ký `PaymentAuditAspect` bằng method `@Bean` trong `AppConfig`.

### 6.5. Service payment: `PaymentService.java`

~~~java
package example.payment;

public class PaymentService {

    public void preview() {
        System.out.println("payment: preview");
    }

    public void approve() {
        System.out.println("payment: approve");
    }
}
~~~

Method `approve()` nằm trong payment module và là public method, còn `preview()` không có tên approve. Cả hai đều được gọi qua cùng một bean, nhưng chỉ một method nên nhận audit.

### 6.6. Service report: `ReportService.java`

~~~java
package example.report;

public class ReportService {

    public void approve() {
        System.out.println("report: approve");
    }
}
~~~

ReportService cũng có method `approve()`, nhưng nằm ngoài package `example.payment` nên **không đáp ứng** `inPaymentModule()`. Đây là negative case giúp chứng minh tên pointcut không chỉ là cách đặt tên đẹp, mà phải đi kèm **biểu thức hẹp đúng ý định**.

### 6.7. Spring configuration: `AppConfig.java`

~~~java
package example;

import example.aop.PaymentAuditAspect;
import example.payment.PaymentService;
import example.report.ReportService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService();
    }

    @Bean
    public PaymentAuditAspect paymentAuditAspect() {
        return new PaymentAuditAspect();
    }
}
~~~

Nhờ `@Bean`, Spring container có một aspect bean. Spring AOP nhận diện pointcut/advice của bean ấy, tìm target class/method phù hợp và tạo proxy khi cần. `proxyTargetClass=true` giúp chương trình lấy bean qua class cụ thể; đặt CGLIB **không làm thay đổi ý nghĩa của named pointcut**.

### 6.8. Chạy chương trình: `Main.java`

~~~java
package example;

import example.payment.PaymentService;
import example.report.ReportService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            PaymentService payment = context.getBean(PaymentService.class);
            ReportService report = context.getBean(ReportService.class);

            System.out.println("payment proxy: " + AopUtils.isAopProxy(payment));
            System.out.println("report proxy: " + AopUtils.isAopProxy(report));

            System.out.println("-- payment preview --");
            payment.preview();

            System.out.println("-- report approval --");
            report.approve();

            System.out.println("-- payment approval --");
            payment.approve();
        }
    }
}
~~~

Từ thư mục có `pom.xml` chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

**Các dòng do chương trình in ra theo đúng thứ tự:**

~~~text
payment proxy: true
report proxy: false
-- payment preview --
payment: preview
-- report approval --
report: approve
-- payment approval --
audit: before payment approval
payment: approve
audit: after payment approval
~~~

### 6.9. Đọc kết quả như một phép kiểm chứng hợp đồng tên

- **`payment proxy: true`:** Spring tìm thấy advisor có thể áp dụng cho ít nhất một method của `PaymentService`.
- **`report proxy: false`:** Không có advisor nào trong cấu hình tối giản này match `ReportService`; Spring không cần proxy nó cho mục đích AOP ấy.
- **`payment.preview()`:** Caller gọi trên AOP proxy, nhưng method `preview` không khớp named pointcut tổng hợp, nên không có audit advice.
- **`report.approve()`:** Tên method đúng nhưng package không nằm trong payment module, nên không có audit advice.
- **`payment.approve()`:** Cả `inPaymentModule` và `publicApprovalMethod` đều khớp. `@Before` chạy trước business method; `@AfterReturning` chạy sau khi method hoàn tất bình thường.

Nếu một advisor khác được thêm vào app (caching, transaction, security, custom aspect), `report` có thể nhận proxy vì nguyên nhân khác. Vì vậy `isAopProxy == false` được dự đoán dựa trên **đúng cấu hình ví dụ**, không phải quy luật của mọi app.

## 7. Chia sẻ named pointcut giữa nhiều Spring aspects

Một tên ý định như `paymentApprovalOperation()` có thể được **nhiều aspects** dùng chung: audit `@Before`, metrics `@AfterReturning` hoặc tracing `@Around`. Các aspect vẫn có trách nhiệm riêng, nên dùng chung tập match không tự biến nhiều policies thành một policy hoặc xác định thứ tự advice.

Nếu chỉ một aspect cần điều kiện riêng, nó có thể kết hợp `PaymentPointcuts.paymentApprovalOperation() && bean(primaryPaymentService)` mà không sửa ý định chung cho các consumers khác. Cần kiểm tra bean name thật và lưu ý `bean(...)` là designator Spring AOP riêng, không portable sang native AspectJ weaving.

## 8. Khi nào nên đặt named pointcut vào lớp riêng?

Tạo class `PaymentPointcuts` hoặc `CommonPointcuts` khi nhiều advice/aspects thực sự cùng phụ thuộc **một tập lời gọi có ý nghĩa ổn định**. Giữ pointcut nội bộ `private` nếu chỉ một aspect cần, công bố `public` khi có consumers bên ngoài; không cần tách mỗi biểu thức một dòng thành public catalog.

Đặt catalog gần domain/module sở hữu chính sách để code review thấy ai chịu trách nhiệm khi đổi expression. Một thư viện chung quá lớn dễ làm những modules không liên quan phụ thuộc lẫn nhau.

## 9. Refactor an toàn: đổi biểu thức mà không đổi ý định

Giả sử hệ thống ban đầu định nghĩa:

~~~java
@Pointcut("within(example.payment..*) && execution(public * approve(..))")
public void paymentApprovalOperation() {}
~~~

Sau refactor, thay vì dựa vào tên method và package, nhóm phát triển muốn đánh dấu các operation bằng `@PaymentApproval`. Ý định có thể vẫn là “những thao tác phê duyệt thanh toán”, nhưng **tập method được match có thể thay đổi**.

Một phương án có chủ đích:

~~~java
@Pointcut(
    "within(example.payment..*)"
    + " && @annotation(example.aop.PaymentApproval)"
)
public void paymentApprovalOperation() {}
~~~

Ở đây `@PaymentApproval` là **annotation tự định nghĩa**. Mẫu annotation cần có `@Target(ElementType.METHOD)` và `@Retention(RetentionPolicy.RUNTIME)`; đặt nó đúng trên các method thực sự cần audit. Các snippet chỉ minh họa hướng refactor, **không thuộc project độc lập** ở mục 6.

Nếu một method chưa được gắn annotation, nó sẽ không còn được advice. Nếu một method không có tên `approve` được gắn annotation thì nó có thể bắt đầu được advice. **Không được coi hai biểu thức là tương đương chỉ vì tên method `paymentApprovalOperation` không đổi**.

### 9.1. Quy trình refactor khuyến nghị

1. Ghi một danh sách **positive matches** theo hợp đồng nghiệp vụ, ví dụ PaymentService.approve.
2. Ghi **negative matches**, ví dụ PaymentService.preview, ReportService.approve.
3. Kiểm tra trong context với bean registration và proxy strategy thật.
4. Chỉ thay expression ở định nghĩa named pointcut sau khi hiểu tập match mong muốn.
5. Chạy integration tests để xác minh cả advice behavior và **không can thiệp nhầm** bean ngoài scope.
6. Cập nhật Javadoc/contract nếu ý định nghiệp vụ đã thay đổi.
7. Review thứ tự advisor nếu nhiều aspect sử dụng cùng named pointcut.

Kết quả kỳ vọng: code ở các advice vẫn đọc được theo intent và không đòi sửa hàng loạt khi cần đổi chi tiết nhận diện.

## 10. Đừng nhầm tên named pointcut với bảo đảm bảo mật

Tên như `secureOperation()`, `authorizedPayment()` hoặc `trustedMethod()` có thể khiến người đọc tưởng một chính sách **đã được thực thi**, trong khi `@Pointcut` chỉ định nghĩa **nơi advice có khả năng chạy**.

Ví dụ:

~~~java
@Pointcut("execution(public * example.payment.PaymentService.approve(..))")
public void authorizedPayment() {}
~~~

Method trên không tự kiểm tra authorization, không biết ai gọi, không từ chối quyền truy cập. Trừ khi advice phù hợp thực sự thực thi security rules đúng cách, một pointcut tên `authorizedPayment` không chứng minh thao tác đã được bảo vệ.

Nên dùng tên mô tả **tập lời gọi** như `paymentApprovalOperation()`; để advice mang trách nhiệm riêng về audit, authorization, metrics hoặc transaction và kiểm thử hành vi từng lớp độc lập.

Với security và transaction quan trọng, không nên chỉ dựa vào naming convention hoặc phạm vi pointcut chưa được kiểm chứng; phải test hệ thống thực tế và cả trường hợp gọi nội bộ/self-invocation.

## 11. Những lỗi thường gặp

Các lỗi đặt tên cần bắt lúc review: tên `allPaymentOperations()` nhưng chỉ match `approve()`; `secureOperation()` khiến người đọc tưởng authorization đã được thực thi; tên ký tự expression không cho biết mục đích; hoặc đổi tên pointcut nhưng quên các chuỗi tham chiếu fully-qualified trong advice/XML.

Sau khi đổi implementation từ package/method pattern sang `@annotation(PaymentApproval)`, **giữ cùng tên không bảo đảm giữ cùng tập match**. Dùng positive cases (`PaymentService.approve`) và negative cases (`PaymentService.preview`, `ReportService.approve`) để kiểm chứng ý định, đồng thời xem lại bean registration và proxy boundary.

## 12. Đặt tên có thể giúp review thay đổi AOP

Khi review một pull request Spring Aspect, người đọc nên thấy ngay:

~~~java
@Before("example.aop.PaymentPointcuts.paymentApprovalOperation()")
public void auditPaymentApproval() {
    // ...
}
~~~

Tên cho biết **nơi advice có ý định chạy**; tên advice cho biết **hành vi chạy tại đó**. Chúng giải quyết hai phần khác nhau.

Một review tốt cần xét:

- Ý định nghiệp vụ của `paymentApprovalOperation()` có còn đúng không?
- Expression hiện tại có thật sự chọn **chỉ** những operation ấy?
- Việc thêm module hoặc method mới có vô tình làm mở rộng tập match không?
- Có method phải được advice nhưng không nằm trong phạm vi package/bean/annotation đã chọn không?
- Nhiều aspect sử dụng shared pointcut có bị ảnh hưởng nếu người khác sửa expression không?
- Cấu hình proxy của Spring Boot/Spring Framework có thay đổi từ JDK sang CGLIB và ảnh hưởng method visibility không?
- Có những lời gọi tự gọi nội bộ qua `this` hoặc object được tạo bằng `new` khiến advice không chạy?
- Positive **và** negative tests có đủ để bảo vệ hợp đồng không?

Đặt tên theo ý định giúp việc review **đặt đúng câu hỏi**, nhưng tests và kiểm tra proxy/runtime mới xác nhận hành vi thực tế.

## 13. Tình huống luyện tập

**Tình huống A.** Hai advice đều chứa nguyên chuỗi `within(example.payment..*) && execution(public * approve(..))`. Làm thế nào giảm lặp mà vẫn đọc được rõ ý định?

**Đáp án:** Tạo `@Pointcut` tên `paymentApprovalOperation()`, đặt biểu thức ở một nơi, rồi dùng tên trong cả hai advice.

**Tình huống B.** Pointcut `paymentApprovalOperation()` chỉ chứa `execution(public * approve(..))`. Nó có đúng tên không?

**Đáp án:** Chưa đủ bảo đảm. Nó còn chọn method public tên approve trong nhiều package khác. Bổ sung scoping/payment condition hoặc đổi tên để phản ánh phạm vi thực tế.

**Tình huống C.** Một `PaymentPointcuts` class chứa `@Pointcut` public nhưng không có `@Component`. Named pointcut có dùng từ một Spring-managed `@Aspect` khác được không?

**Đáp án:** Có, Spring @AspectJ support cho phép tham chiếu named pointcuts được công bố trong class khác; lớp chỉ chứa signatures không cần thành bean để được tham chiếu. Điều cần đăng ký là aspect bean có advice.

**Tình huống D.** `@Pointcut` method là `private` trong class A, class B muốn tham chiếu nó bằng tên đầy đủ. Có nên làm thế không?

**Đáp án:** Không. Java visibility áp dụng cho named pointcut references. Nếu cần chia sẻ ngoài class, dùng method public và định nghĩa hợp đồng rõ ràng.

**Tình huống E.** Sau khi đổi implementation sang `@annotation(PaymentApproval)`, tên `paymentApprovalOperation()` không thay đổi. Có thể bỏ kiểm thử phạm vi không?

**Đáp án:** Không. Tập method match có thể khác rất nhiều, dù tên pointcut giữ nguyên.

**Tình huống F.** Một method `payment.preview()` trên bean có proxy không nhận advice. Có phải vì named pointcut không được nạp?

**Đáp án:** Không nhất thiết. Nếu expression chỉ chọn `approve()`, đây là hành vi đúng: một bean có proxy không có nghĩa mọi method đều match cùng advisor.

## 14. Nguồn tài liệu chính thức

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): chữ ký phương thức `@Pointcut`, tham chiếu tên, tổ hợp biểu thức, visibility, dedicated CommonPointcuts và cách viết good pointcuts.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Before`, `@AfterReturning`, cách tham chiếu named pointcut trong annotation advice.
- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `ClassFilter`, `MethodMatcher` và tái sử dụng/composition của Spring pointcut.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): điều kiện đăng ký aspect bean và bật Spring AOP.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): ranh giới JDK/CGLIB proxies và giới hạn self-invocation.
