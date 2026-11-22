# Ràng buộc tham số, `returning` và `throwing` trong Spring AOP XML

## 1. Mục tiêu

Khi cấu hình aspect qua XML, Spring AOP cho phép advice nhận trực tiếp dữ liệu từ method được chặn mà không phải tự lấy và ép kiểu mọi giá trị từ `JoinPoint.getArgs()`. Ba cơ chế trọng tâm là:

- **Ràng buộc tham số đầu vào** từ pointcut, ví dụ `args(orderId, ..)`, vào tham số cùng tên của advice.
- **`returning`** trên `<aop:after-returning>`: đưa giá trị method trả về khi hoàn tất bình thường vào advice.
- **`throwing`** trên `<aop:after-throwing>`: đưa ngoại lệ được method ném ra khỏi join point vào advice.

Ngoài ra, **`arg-names`** trong XML khai báo rõ thứ tự tên tham số mà Spring dùng khi kết nối pointcut và phương thức advice; điều này đặc biệt hữu ích khi mã Java không giữ tên tham số ở runtime.

Bài học tập trung vào **Spring AOP dạng schema XML** (`<aop:config>`, `<aop:aspect>`, các phần tử advice). Không cần dùng annotation `@Aspect` hoặc weaving AspectJ để chạy ví dụ.

## 2. Phân biệt các thành phần rất dễ nhầm

| Thành phần XML | Vai trò | Ví dụ |
| --- | --- | --- |
| `<aop:pointcut expression="..."/>` | Chọn method execution và có thể khai báo biến binding | `args(orderId, ..)` |
| `method` | Tên phương thức Java trên bean được tham chiếu bởi `<aop:aspect ref="...">` | `method="beforeProcess"` |
| `arg-names` | Danh sách tên binding ứng với tham số của advice theo thứ tự | `arg-names="orderId,receipt"` |
| `returning` | Tên biến nhận giá trị trả về, dành cho after-returning advice | `returning="receipt"` |
| `throwing` | Tên biến nhận ngoại lệ, dành cho after-throwing advice | `throwing="failure"` |

Ba quy tắc kết nối cần nhớ:

1. Trong `args(orderId, ..)`, **`orderId` là tên binding**; phương thức advice nhận tham số tương ứng với tên này. Nó không bắt buộc trùng tên parameter của method nghiệp vụ, nhưng kiểu và vị trí phải phù hợp.
2. `returning="receipt"` yêu cầu advice có tham số nhận giá trị trả về tương ứng tên `receipt`. `throwing="failure"` yêu cầu tham số nhận ngoại lệ tương ứng tên `failure`.
3. `arg-names` chứa tên **các tham số phải bind** theo thứ tự khai báo trong method advice. Nếu method có `JoinPoint` là tham số đầu tiên, Spring có thể suy ra tham số này theo kiểu nên có thể bỏ tên nó ra khỏi danh sách; vẫn cần chỉ rõ các binding còn lại để cấu hình dễ kiểm tra.

**Không nhầm `returning` hoặc `throwing` với phương thức Java trả về/ném ngoại lệ.** Chúng là thuộc tính của phần tử **advice XML** quy định giá trị mà Spring chuyển đến advice sau khi method được chặn kết thúc.

## 3. Luồng Spring AOP khi một method được gọi

Giả sử caller gọi `invoiceService.process("INV-1", false)` qua Spring proxy:

~~~text
Caller
  |
  v
Spring proxy: pointcut khớp process(..), args(invoiceId, ..)
  |
  +-- <aop:before> nhận invoiceId = "INV-1"
  |
  v
Target InvoiceService.process(...)
  |
  +-- trả về String "paid:INV-1"
  |      |
  |      +-- <aop:after-returning returning="receipt">
  |               invoiceId = "INV-1"
  |               receipt = "paid:INV-1"
  |      |
  |      +-- trả giá trị ban đầu về caller
  |
  +-- hoặc ném IllegalStateException
         |
         +-- <aop:after-throwing throwing="failure">
                  invoiceId được bind từ input
                  failure là ngoại lệ thực tế
         |
         +-- ngoại lệ tiếp tục truyền về caller
~~~

`<aop:after-returning>` **chỉ chạy khi method hoàn thành bình thường**. `<aop:after-throwing>` **chỉ chạy khi join point kết thúc bằng ném ngoại lệ**. Nếu method tự bắt một ngoại lệ rồi trả kết quả bình thường, đó là nhánh `after-returning`, không phải nhánh `after-throwing`.

Mọi điều trên giả định lời gọi đi qua Spring AOP proxy. Self-invocation kiểu `this.process(...)` trong chính target bean không đi qua proxy và sẽ không kích hoạt advice ở lời gọi nội bộ đó.

## 4. Ví dụ độc lập: XML + Java 17 + Spring Framework 6

Ví dụ dùng **Java 17**, Spring AOP được cung cấp bởi **Spring Boot starter AOP 3.3.0** (dependency management đưa Spring Framework 6.1.x phù hợp), nhưng khởi tạo trực tiếp Spring `ClassPathXmlApplicationContext`. Vì vậy toàn bộ **khai báo aspect nằm trong XML**, không có `@Aspect`, `@EnableAspectJAutoProxy`, hoặc chương trình Spring Boot khởi chạy bằng `SpringApplication.run`.

### 4.1. Cấu trúc dự án

~~~text
pom.xml
src/main/java/com/example/xmlaop/
    InvoiceService.java
    InvoiceAdvice.java
    Demo.java
src/main/resources/
    applicationContext.xml
~~~

### 4.2. Maven

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-aop-xml-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Starter AOP có dependency Spring AOP và AspectJ weaver phục vụ việc phân tích pointcut. Ở đây nó chỉ cung cấp thư viện qua Maven; **chính XML** sẽ tạo auto-proxy.

### 4.3. Target service

Tệp `src/main/java/com/example/xmlaop/InvoiceService.java`:

~~~java
package com.example.xmlaop;

public class InvoiceService {

    public String process(String invoiceId, boolean reject) {
        System.out.println("service:" + invoiceId);

        if (reject) {
            throw new IllegalStateException("declined:" + invoiceId);
        }

        return "paid:" + invoiceId;
    }
}
~~~

Hai nhánh được cố ý viết đơn giản:

- `reject = false`: phương thức **trả String**.
- `reject = true`: phương thức **ném IllegalStateException** và không trả một String nào.

Spring AOP sẽ nhận cùng một tham số `invoiceId` tại before advice, rồi chọn **một trong hai** advice sau thực thi tùy cách method kết thúc.

### 4.4. Java advice bean bình thường

Tệp `src/main/java/com/example/xmlaop/InvoiceAdvice.java`:

~~~java
package com.example.xmlaop;

public class InvoiceAdvice {

    public void beforeProcess(String invoiceId) {
        System.out.println("before:" + invoiceId);
    }

    public void afterSuccess(String invoiceId, String receipt) {
        System.out.println("returned:" + invoiceId + "->" + receipt);
    }

    public void afterFailure(String invoiceId, IllegalStateException failure) {
        System.out.println(
                "thrown:" + invoiceId + "->" + failure.getMessage());
    }
}
~~~

Đây là POJO, không cần `@Aspect`. Các method advice có tên và kiểu tham số rõ ràng; mapping được khai báo bằng XML.

**Sự khác biệt về kiểu:** `String receipt` nghĩa là after-returning advice nhận những kết quả tương thích với `String`; `IllegalStateException failure` nghĩa là after-throwing advice chỉ nhận ngoại lệ thuộc kiểu `IllegalStateException` hoặc kiểu con của nó. Dùng `Object receipt` để nhận các kết quả tham chiếu thuộc nhiều kiểu, và `Throwable failure` nếu muốn theo dõi nhiều loại lỗi (bao gồm `Error`). Không gán kiểu cụ thể quá hẹp so với method định theo dõi.

### 4.5. Cấu hình XML chứa pointcut và binding

Tệp `src/main/resources/applicationContext.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="invoiceService"
          class="com.example.xmlaop.InvoiceService"/>

    <bean id="invoiceAdvice"
          class="com.example.xmlaop.InvoiceAdvice"/>

    <aop:config proxy-target-class="true">
        <aop:aspect id="invoiceAspect" ref="invoiceAdvice">

            <aop:pointcut
                    id="invoiceProcess"
                    expression="execution(public * com.example.xmlaop.InvoiceService.process(..))
                                and args(invoiceId, ..)"/>

            <aop:before
                    pointcut-ref="invoiceProcess"
                    method="beforeProcess"
                    arg-names="invoiceId"/>

            <aop:after-returning
                    pointcut-ref="invoiceProcess"
                    method="afterSuccess"
                    returning="receipt"
                    arg-names="invoiceId,receipt"/>

            <aop:after-throwing
                    pointcut-ref="invoiceProcess"
                    method="afterFailure"
                    throwing="failure"
                    arg-names="invoiceId,failure"/>

        </aop:aspect>
    </aop:config>
</beans>
~~~

Đọc theo thứ tự:

1. `<bean id="invoiceService" .../>` tạo **target bean**. `<bean id="invoiceAdvice" .../>` tạo **POJO advice**.
2. `<aop:config>` kích hoạt cơ chế Spring AOP proxy cho khai báo XML trong ApplicationContext. `proxy-target-class="true"` dùng class-based proxy; phương thức `process` là public và không final nên có thể intercept.
3. `<aop:aspect ref="invoiceAdvice">` nối khái niệm aspect trong XML với Java bean `InvoiceAdvice`.
4. `execution(public * ...InvoiceService.process(..))` thu hẹp phạm vi đúng method `process`, với mọi kiểu trả về và số lượng argument. Phần `args(invoiceId, ..)` yêu cầu argument đầu có thể bind với `String invoiceId` của advice.
5. `arg-names="invoiceId"` của before advice tạo mapping giữa biến trong pointcut và `beforeProcess(String invoiceId)`.
6. `returning="receipt"` và `arg-names="invoiceId,receipt"` đưa **giá trị trả về** vào tham số thứ hai của `afterSuccess(String invoiceId, String receipt)`.
7. `throwing="failure"` và `arg-names="invoiceId,failure"` đưa **ngoại lệ** vào tham số thứ hai của `afterFailure(String invoiceId, IllegalStateException failure)`.

**Tại sao trong expression dùng `and`?** Thuộc tính XML không thể chứa ký tự `&` thô trong `&&`; Spring AspectJ pointcut expression cho phép dạng từ khóa `and`, `or`, `not`. Nếu thực sự viết `&&`, phải escape thành `&amp;&amp;`. Ví dụ chọn `and` để XML dễ đọc.

**Tại sao `arg-names` lại chứa `receipt`/`failure` dù pointcut không khai báo chúng?** Vì đây là các binding bổ sung do **thuộc tính `returning`/`throwing` trên advice** cung cấp. Chúng cần tên để ghép với tham số Java, mặc dù không xuất hiện ở `args(...)`.

### 4.6. Main chạy hai trường hợp

Tệp `src/main/java/com/example/xmlaop/Demo.java`:

~~~java
package com.example.xmlaop;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Demo {

    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext(
                             "applicationContext.xml")) {

            InvoiceService service =
                    context.getBean("invoiceService", InvoiceService.class);

            System.out.println("== success ==");
            String receipt = service.process("INV-1", false);
            System.out.println("caller:" + receipt);

            System.out.println("== failure ==");
            try {
                service.process("INV-2", true);
            } catch (IllegalStateException failure) {
                System.out.println(
                        "caller caught:" + failure.getMessage());
            }
        }
    }
}
~~~

Tại thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.xmlaop.Demo
~~~

Bỏ qua log môi trường/Maven, dòng do chương trình in ra có **thứ tự và nội dung xác định**:

~~~text
== success ==
before:INV-1
service:INV-1
returned:INV-1->paid:INV-1
caller:paid:INV-1
== failure ==
before:INV-2
service:INV-2
thrown:INV-2->declined:INV-2
caller caught:declined:INV-2
~~~

Phân tích:

- Nhánh thành công: `beforeProcess` chạy trước target; target trả `paid:INV-1`; `afterSuccess` nhận đồng thời `invoiceId` ban đầu và kết quả; caller vẫn nhận **chính giá trị trả về gốc**.
- Nhánh lỗi: `beforeProcess` vẫn chạy; target ném `IllegalStateException`; `afterFailure` nhận ngoại lệ; caller vẫn bắt được **ngoại lệ gốc**.
- `afterSuccess` không được gọi trong nhánh lỗi; `afterFailure` không được gọi trong nhánh thành công.
- Cấu hình XML không sử dụng `@Aspect` và chương trình không tự khởi tạo `InvoiceService` bằng `new` ở caller, vì làm vậy sẽ đi vòng qua proxy.

## 5. Tìm hiểu kỹ `args(...)` và kiểu binding

Với biểu thức `args(invoiceId, ..)`:

- `invoiceId` là **biến pointcut** cần bind. Kiểu `String` được suy ra từ tham số advice `beforeProcess(String invoiceId)`, `afterSuccess(String invoiceId, ...)`, v.v.
- `..` biểu diễn các đối số còn lại có số lượng bất kỳ. Do đó `process(String, boolean)` khớp và lấy giá trị String đầu tiên.
- Đây là **runtime argument matching**; nó không đơn giản là “phương thức có biến Java nguồn tên `invoiceId`”. Tên tham số ở source của target method không quyết định tên binding trong pointcut.
- Nếu muốn match chính xác signature, thêm ràng buộc `execution(public String com.example.xmlaop.InvoiceService.process(String,boolean))`, nhưng vẫn có thể dùng `args(invoiceId, ..)` để lấy giá trị cụ thể.

Một ví dụ XML ngắn khác khi cần bind hai tham số:

~~~xml
<aop:before
        pointcut="execution(* com.example.xmlaop.InvoiceService.process(..))
                  and args(invoiceId,reject)"
        method="auditInput"
        arg-names="invoiceId,reject"/>
~~~

Method trên advice tương ứng phải có chữ ký phù hợp, chẳng hạn:

~~~java
public void auditInput(String invoiceId, boolean reject) {
    System.out.println("request=" + invoiceId + ", reject=" + reject);
}
~~~

Hai đoạn vừa nêu **chỉ minh họa biến thể**, chưa có `auditInput` trong class `InvoiceAdvice` của chương trình chạy ở mục 4. Nếu thay XML và thêm method như trên, Spring sẽ truyền cả hai đối số theo đúng thứ tự. Không nên chèn riêng XML này vào bản chính nếu chưa bổ sung method.

Khi muốn đọc toàn bộ args mà không thiết lập binding tường minh, before advice có thể nhận `JoinPoint`:

~~~java
public void inspect(org.aspectj.lang.JoinPoint joinPoint) {
    Object[] arguments = joinPoint.getArgs();
    System.out.println("argumentCount=" + arguments.length);
}
~~~

Đây cũng là **biến thể minh họa**. Cách `JoinPoint.getArgs()` linh hoạt hơn nhưng bạn phải tự đọc và ép kiểu. Với một vài biến rõ ràng, binding qua `args` và `arg-names` thường dễ bảo trì hơn.

## 6. `returning`: nhận kết quả nhưng không thay giá trị trả về

`<aop:after-returning>` chỉ kích hoạt khi matched method **hoàn thành bình thường**. Khi có `returning="receipt"`, Spring truyền kết quả vào tham số advice có tên binding tương ứng.

Ví dụ `afterSuccess(String invoiceId, String receipt)` chỉ định `String`: đó là một **ràng buộc kiểu**. Trong pointcut rộng chặn nhiều method trả nhiều kiểu khác nhau, advice nhận `String receipt` chỉ áp dụng cho các lời gọi có giá trị trả về phù hợp kiểu `String`. Nếu dùng `Object receipt`, phạm vi nhận kết quả tham chiếu rộng hơn. Trong method khai báo trả `void`, không có giá trị kết quả để bind vào `String` như ví dụ.

After-returning advice **không thể dùng return của chính advice để thay kết quả** mà caller nhận. Chẳng hạn:

~~~java
// Biến thể minh họa, không phải method trong ví dụ chính:
public String afterSuccess(String invoiceId, String receipt) {
    return "overridden"; // không biến thành return của InvoiceService.process()
}
~~~

Nếu yêu cầu nghiệp vụ là đổi hoặc thay thế kết quả, phải dùng `<aop:around>` với `ProceedingJoinPoint` và chủ động trả về kết quả muốn chuyển cho caller. Việc around advice đổi kết quả cần cân nhắc contract và type của method.

**Lưu ý về object mutable:** advice nhận một tham chiếu tới object kết quả có thể sửa **trạng thái bên trong object đó**, nếu object mutable. Điều này khác với việc thay hẳn reference trả về. Tránh thay đổi ngầm data ở advice đo đạc/audit vì làm kết quả phụ thuộc thứ tự interceptor.

## 7. `throwing`: nhận ngoại lệ được phát ra, không tự xử lý phục hồi

Khai báo:

~~~xml
<aop:after-throwing
        pointcut-ref="invoiceProcess"
        method="afterFailure"
        throwing="failure"
        arg-names="invoiceId,failure"/>
~~~

Spring truyền ngoại lệ ném ra khỏi matched method đến tham số `failure` của advice. `IllegalStateException failure` chỉ khớp ngoại lệ cùng kiểu hoặc kiểu con; nếu method ném `IOException`, advice với kiểu `IllegalStateException` sẽ không xử lý nó.

**After-throwing khác `catch`**:

- Advice `afterFailure` trong ví dụ chỉ ghi nhận thông tin.
- Nó không tự nuốt ngoại lệ để chuyển execution thành thành công.
- `return` bên trong after-throwing advice (nếu method có return type) không thay thế ngoại lệ của target.
- Caller vẫn có thể xử lý bằng `try/catch`.
- Nếu target bắt lỗi nội bộ rồi trả kết quả bình thường, Spring không có ngoại lệ thoát khỏi join point để chạy after-throwing advice.

Nếu muốn fallback khi target ném ngoại lệ, dùng `<aop:around>` và xử lý exception quanh `proceed()` theo một **chính sách nghiệp vụ được xác định rõ**. Đừng nhầm `after-throwing` với `@ControllerAdvice`/exception resolver của Spring MVC: đây là hai cơ chế xử lý ở các boundary khác nhau.

## 8. `arg-names`: cách Spring khớp tên biến với chữ ký advice

Ràng buộc biến trong Spring AOP không thể dựa chắc chắn vào **tên parameter của Java source** nếu bytecode không giữ tên. Spring có các chiến lược khám phá tên, nhưng với XML bạn có thể chủ động cấu hình `arg-names` để tránh sự mơ hồ.

Giả sử:

~~~java
public void afterSuccess(String order, String result) {
    // ...
}
~~~

Nếu pointcut dùng biến `invoiceId` và `returning="receipt"`, vẫn có thể khai báo:

~~~xml
<aop:after-returning
        pointcut-ref="invoiceProcess"
        method="afterSuccess"
        returning="receipt"
        arg-names="invoiceId,receipt"/>
~~~

Ở đây **thứ tự** trong `arg-names` tương ứng tham số Java thứ nhất và thứ hai; tên source `order`/`result` không quyết định mapping khi Spring dùng danh sách `arg-names` tường minh. Dù vậy, nên đặt cùng tên trong Java và XML để tài liệu và implementation dễ theo dõi.

### Nếu advice nhận `JoinPoint`

Ví dụ before advice nhận join point trước rồi nhận argument được bind:

~~~java
public void beforeProcess(
        org.aspectj.lang.JoinPoint joinPoint,
        String invoiceId) {
    System.out.println(joinPoint.getSignature().getName() + ":" + invoiceId);
}
~~~

Khai báo XML có thể là:

~~~xml
<aop:before
        pointcut-ref="invoiceProcess"
        method="beforeProcess"
        arg-names="invoiceId"/>
~~~

Spring có thể tự nhận biết tham số đầu `JoinPoint` theo kiểu, vì vậy không cần đưa tham số `joinPoint` vào `arg-names`. Đây là **biến thể minh họa**: nếu dùng chữ ký này thì phải thay method `beforeProcess` trong ví dụ chính cho phù hợp.

Với `<aop:around>`, tham số đầu tiên của method advice phải là `ProceedingJoinPoint` để gọi `proceed()`. Binding cho các tham số còn lại tuân theo cùng nguyên tắc, còn around advice quyết định có chạy target hay không.

### Lỗi cấu hình tên thường gặp

- XML ghi `returning="retVal"` nhưng `arg-names="invoiceId,result"`: tên `retVal` không có chỗ bind; có thể phát sinh lỗi tạo aspect/advisor hoặc ràng buộc không hợp lệ.
- XML ghi `throwing="failure"` còn method advice chỉ có tham số `String failure`: kiểu không tương thích với exception object.
- `arg-names="receipt,invoiceId"` nhưng method khai báo tham số theo thứ tự `(String invoiceId, String receipt)`: hai giá trị đều là String nên lỗi **khó phát hiện qua type checking**, khiến log hoặc logic bị hoán đổi.
- Pointcut ghi `args(invoiceId, ..)` nhưng advice cần bind cả `tenantId` mà expression không đưa vào: variable thiếu nguồn giá trị.
- Quên `arg-names` rồi kỳ vọng Spring luôn lấy được tên Java parameter khi biên dịch không bật cơ chế giữ tên phù hợp: binding có thể phụ thuộc tên đã khám phá hoặc bị lỗi.

Đặc biệt với các binding cùng kiểu như String/String, **test so sánh giá trị thực tế** mới chứng minh mapping đúng; Java compiler không thể phát hiện mọi trường hợp đảo thứ tự về mặt nghiệp vụ.

## 9. Phối hợp nhiều biến: inputs + returning/throwing

Một advice có thể nhận cả input từ `args(...)` và output/exception. Ví dụ chính đã dùng:

| Lời gọi | Pointcut `args(invoiceId, ..)` | Dữ liệu thêm từ XML | Advice nhận |
| --- | --- | --- | --- |
| `process("INV-1", false)` | `invoiceId="INV-1"` | `receipt="paid:INV-1"` | `afterSuccess(String, String)` |
| `process("INV-2", true)` | `invoiceId="INV-2"` | `failure=IllegalStateException("declined:INV-2")` | `afterFailure(String, IllegalStateException)` |

Dù hai after-advice dùng cùng `pointcut-ref`, việc method kết thúc thành công hay lỗi sẽ quyết định loại advice nào được gọi; `returning` và `throwing` **không đồng thời bind cho cùng một lần hoàn tất**.

Khi điểm chặn cần phân biệt nhiều overload hoặc các kiểu argument khác nhau, hãy thu hẹp `execution` theo signature và dùng `args` cho các giá trị cụ thể muốn nhận. Đừng dùng biểu thức quá rộng bao hết mọi bean/method nếu chỉ cần audit một operation, vì các binding type có thể gây matching không như dự kiến hoặc tạo overhead không cần thiết.

## 10. Điều kiện hoạt động và lỗi thường gặp với XML AOP

### 10.1. Advice không được gọi dù XML đọc thành công

Kiểm tra lần lượt:

1. Có khai báo namespace `aop`, `spring-aop.xsd`, `<aop:config>` và `<aop:aspect ref="...">` đúng hay không?
2. Bean aspect được tham chiếu bởi `ref` có tồn tại không, và `method` có đúng tên method trên bean đó không?
3. Bean target có được **Spring quản lý** và caller có lấy **proxy** từ context không?
4. Pointcut `execution(...)` có khớp class, method và kiểu tham số thực tế không?
5. Có self-invocation `this.process(...)` hoặc method private/final làm lời gọi không được proxy intercept không?
6. Có lỗi khai báo `arg-names`, `returning`, `throwing` hoặc kiểu tham số của advice không?

Ví dụ dùng class-based proxy nên `InvoiceService` không cần interface. Nếu đổi sang JDK proxy, target phải có interface được proxy và caller nên inject/lấy bean bằng **kiểu interface**, không ép proxy thành concrete class.

### 10.2. XML bị parser từ chối do dấu ampersand

Sai:

~~~xml
<!-- Sai cú pháp XML: không thể đặt & thô trong attribute -->
<aop:pointcut
        id="x"
        expression="execution(* com.example..*(..)) && args(name,..)"/>
~~~

Đúng (dùng từ khóa):

~~~xml
<aop:pointcut
        id="x"
        expression="execution(* com.example..*(..)) and args(name,..)"/>
~~~

Hoặc dùng entity XML:

~~~xml
<aop:pointcut
        id="x"
        expression="execution(* com.example..*(..)) &amp;&amp; args(name,..)"/>
~~~

Các XML trên chỉ minh họa cú pháp escape/pointcut; chúng không thay thế cấu hình demo vốn có kiểu binding tường minh.

### 10.3. Lỗi binding không chắc sẽ xuất hiện ở compile-time

Cấu hình XML được Spring xử lý khi khởi tạo ApplicationContext. Nếu advice tham chiếu tên không tồn tại, số lượng biến không khớp hoặc không thể resolve method, lỗi có thể xuất hiện **khi startup** chứ không phải lúc biên dịch Java. Với logic security/audit/transaction quan trọng, viết integration test khởi tạo context và gọi method qua bean proxy ở cả hai nhánh success/failure.

### 10.4. `returning` không phải lúc nào cũng là kết quả “nghiệp vụ đã hoàn tất”

Nếu method trả `CompletableFuture`, after-returning advice thường thấy **đối tượng future được trả**, chưa chắc thấy kết quả xử lý cuối cùng. Nếu method trả `Mono`/`Flux`, advice thấy publisher được trả, không tự đo việc subscription hoàn thành. Khi cần audit kết quả cuối của công việc bất đồng bộ, phải theo dõi completion/subscription bằng cơ chế thích hợp, thay vì suy luận từ lúc method return.

### 10.5. Thứ tự nhiều advice và xử lý ngoại lệ

Khi phối hợp advice từ các aspect/advisor khác nhau, thứ tự interceptor ảnh hưởng dữ liệu nhìn thấy và thời điểm ghi log. Nếu một around advice ngoài cùng bắt exception và trả fallback, advice after-throwing nằm **bên ngoài** around advice đó có thể không còn nhìn thấy ngoại lệ. Nếu after-throwing nằm **bên trong** và nhìn thấy exception trước lúc bị bắt, nó có thể được kích hoạt. Xác định ranh giới đo và thứ tự theo hành vi cần bảo đảm; khi phải kiểm soát, dùng cơ chế order phù hợp và kiểm thử thay vì suy đoán thứ tự.

### 10.6. Nơi đặt cấu hình

Schema-based AOP nằm trong Spring ApplicationContext thực sự tải XML. Một XML riêng có khai báo `<aop:config>` sẽ không có tác dụng nếu ứng dụng chưa import/tải file đó. Nếu ứng dụng Spring Boot chủ yếu dùng Java config, có thể dùng `@ImportResource("classpath:applicationContext.xml")` trên một configuration class để tải XML; đây là **cách tích hợp bổ sung**, không phải yêu cầu của demo sử dụng `ClassPathXmlApplicationContext`.

## 11. Checklist kiểm chứng

Trước khi xem binding XML AOP là đúng, cần xác nhận:

- Spring khởi động được ApplicationContext với schema `aop` và đủ dependency.
- Pointcut chỉ chọn các method cần thiết, không chặn nhầm các operation khác.
- `args` bind đúng **giá trị input**, kể cả khi tên Java source khác biến trong pointcut.
- `arg-names` có thứ tự tương ứng với danh sách tham số Java của advice.
- `returning` bind đúng kết quả trong success; after-returning không chạy ở nhánh lỗi.
- `throwing` bind đúng exception type trong failure; after-throwing không chạy ở nhánh thành công.
- Caller vẫn nhận return value hoặc ngoại lệ gốc, trừ khi có around advice chủ ý thay đổi chúng.
- Test gọi **thông qua Spring proxy**, không gọi trực tiếp `new Target()` hoặc self-invocation.
- Khi dùng async/reactive, đã xác định rõ lời gọi method kết thúc hay tác vụ thực tế kết thúc mới là mốc quan sát.

## 12. Ghi nhớ

Spring AOP XML tách biệt **phạm vi cần chặn** (pointcut) và **dữ liệu đưa vào advice** (binding). `args(...)` gắn giá trị đầu vào với tên biến; `arg-names` ghép tên đó với chữ ký Java advice; `returning` và `throwing` bổ sung binding cho kết quả bình thường hoặc ngoại lệ. Dù cấu hình nằm trong XML, cơ chế Spring AOP vẫn là **proxy-based**, có giới hạn self-invocation và thứ tự advisor như những cách khai báo Spring AOP khác.

Tài liệu chính thức:

- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html)
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
