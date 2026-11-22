
# Thoát ký tự và sử dụng `and`, `or`, `not` trong biểu thức Spring AOP cấu hình XML

## 1. Vấn đề thực tế

Khi định nghĩa pointcut trong `applicationContext.xml`, ta đang viết **biểu thức pointcut của Spring AOP bên trong một thuộc tính XML**. Hai lớp cú pháp được xử lý nối tiếp nhau:

1. XML parser đọc tài liệu, giải mã XML entities trong giá trị thuộc tính (ví dụ `&amp;` thành ký tự `&`).
2. Spring AOP/AspectJ pointcut parser nhận chuỗi biểu thức sau khi XML đã giải mã, rồi xác định những lời gọi method trên Spring bean nào khớp.

Vì vậy một biểu thức hoàn toàn hợp lệ trong Java `@Pointcut` có thể làm XML không hợp lệ nếu chép nguyên ký tự `&&` vào attribute `expression`. Trong cấu hình XML, Spring cho phép dùng **từ khóa `and`, `or`, `not`** tương đương các toán tử `&&`, `||`, `!`. Cách dùng từ khóa thường dễ đọc hơn và tránh phải escape ký tự `&`.

Mục tiêu bài này là viết và kiểm tra các biểu thức **Spring AOP proxy-based** trong namespace `aop`; chỉ giải thích phần ngôn ngữ biểu thức liên quan trực tiếp đến Spring XML.

## 2. Bảng đối chiếu cú pháp toán tử

| Ý nghĩa | Biểu thức trong Java `@Pointcut` | Cách khuyên dùng ở Spring XML | Dạng ký hiệu vẫn dùng được trong XML |
| --- | --- | --- | --- |
| Đồng thời thỏa hai điều kiện (AND) | `A && B` | `A and B` | `A &amp;&amp; B` |
| Thỏa ít nhất một điều kiện (OR) | `A || B` | `A or B` | `A || B` |
| Phủ định một điều kiện (NOT) | `!A` | `not A` | `!A` |
| Nhóm điều kiện | `(A || B) && !C` | `(A or B) and not C` | `(A || B) &amp;&amp; !C` |

Trong bảng, `A`, `B`, `C` là các pointcut sub-expression hợp lệ, chẳng hạn `execution(* demo.OrderService.save(..))`, `within(demo..*)`, `bean(*Service)` hoặc `@annotation(demo.Audited)`.

- `and` kết hợp các điều kiện: một method được advice nếu **mọi** điều kiện đều khớp.
- `or` tạo tập hợp: một method được advice khi **ít nhất một** nhánh khớp.
- `not` loại trừ các join point mà điều kiện được phủ định khớp.
- Ngoặc đơn là cú pháp **pointcut expression**, không phải XML entity; dùng trực tiếp để làm rõ thứ tự tính.
- `&&`, `||`, `!` là toán tử trong biểu thức pointcut, **không phải** phép toán Java được chạy khi method nghiệp vụ thực thi. Spring phân tích chúng để tạo điều kiện chọn join point.

### Ví dụ đơn giản

~~~xml
<!-- Chỉ advice method public trong package demo. -->
<aop:pointcut id="publicInDemo"
    expression="within(demo..*) and execution(public * *(..))"/>
~~~

Điều kiện `within(demo..*)` chọn phạm vi khai báo, còn `execution(public * *(..))` chọn các method execution `public`. Spring AOP chỉ chặn **lời gọi method đi qua Spring proxy**; biểu thức không tự làm cho các đối tượng được tạo bằng `new` trở thành bean.

Với OR:

~~~xml
<!-- Match method send(...) hoặc receive(...), bất kể số lượng argument. -->
<aop:pointcut id="ioOperations"
    expression="execution(* *.send(..)) or execution(* *.receive(..))"/>
~~~

Với NOT:

~~~xml
<!-- Chọn bean tên kết thúc bằng Service nhưng loại bean testService. -->
<aop:pointcut id="nonTestServices"
    expression="bean(*Service) and not bean(testService)"/>
~~~

`bean(idOrNamePattern)` là pointcut designator riêng của **Spring AOP** để xét tên bean. Nó có thể kết hợp các toán tử ở trên; không phải cùng một cơ chế với quét class hoặc chọn package.

## 3. Vì sao `&&` cần `&amp;&amp;` trong XML?

Ký tự `&` có vai trò mở đầu entity reference của XML, vì vậy không thể xuất hiện trần trong giá trị attribute.

**Sai: XML không hợp lệ**

~~~xml
<aop:pointcut id="bad"
    expression="within(demo..*) && execution(public * *(..))"/>
~~~

Bộ phân tích XML gặp `&` đầu tiên và mong đợi một entity hợp lệ; việc phân tích dừng trước khi Spring kịp hiểu pointcut. Lỗi thường biểu hiện như `SAXParseException` hoặc thông báo liên quan entity/name, không phải lỗi logic của `execution(...)`.

**Đúng: dùng chữ `and`**

~~~xml
<aop:pointcut id="correctWords"
    expression="within(demo..*) and execution(public * *(..))"/>
~~~

**Cũng đúng: escape từng ký tự `&`**

~~~xml
<aop:pointcut id="correctEntities"
    expression="within(demo..*) &amp;&amp; execution(public * *(..))"/>
~~~

Sau XML parsing, ví dụ thứ ba đưa đến Spring AOP một chuỗi chứa `&&`. Hai biểu thức đúng trong mục này có cùng ý nghĩa match; chúng không khác nhau về thời điểm advice chạy hay khả năng tạo proxy.

Cần phân biệt:

- **Nội dung XML source**: `&amp;&amp;` có tổng cộng hai entity `&amp;` liên tiếp.
- **Chuỗi đã parse**: `&&`.
- **Pointcut expression**: toán tử AND nối hai điều kiện.

Không viết `&amp;amp;&amp;amp;` do escape hai lần: khi XML parser giải mã một lượt, Spring có thể nhận literal `&amp;&amp;` và pointcut parser không nhận được toán tử mong muốn.

## 4. Các XML entity cần nhớ khi pointcut nằm trong attribute

| Ký tự muốn đưa vào giá trị attribute | Cách viết XML source | Khi nào liên quan |
| --- | --- | --- |
| `&` | `&amp;` | Bắt buộc nếu dùng ký hiệu `&&` |
| `<` | `&lt;` | Bắt buộc trong XML attribute nếu thực sự cần dấu nhỏ hơn |
| `>` | `&gt;` | Có thể dùng để rõ ràng, dù ký tự `>` thường được phép trong attribute |
| `"` | `&quot;` | Cần khi attribute được bọc bằng dấu nháy kép và muốn chứa nháy kép bên trong |
| `'` | `&apos;` | Cần khi attribute được bọc bằng dấu nháy đơn và muốn chứa dấu nháy đơn bên trong |

Không phải tất cả entity trong bảng đều thường xuyên dùng ở pointcut; phổ biến nhất là `&amp;`. Các toán tử `||` và `!` không chứa ký tự XML bắt buộc escape, vì vậy phiên bản ký hiệu của OR và NOT có thể đặt thẳng trong attribute.

XML entity và cú pháp pointcut là **hai cơ chế độc lập**. Viết `&amp;` chỉ làm tài liệu XML hợp lệ; nó không thay đổi ý nghĩa chọn method. Các ký tự `*`, `..`, `(..)`, `@` trong biểu thức Spring AOP thường được viết nguyên vẹn.

**Lưu ý đặc biệt:** Không áp dụng cách escape cho code Java `@Aspect` một cách máy móc:

~~~java
@Pointcut("within(demo..*) && execution(public * *(..))")
public void publicOperationsInDemo() {}
~~~

Trong Java string literal ở trên, `&&` không nằm trong XML attribute nên không phải viết `&amp;&amp;`.

## 5. Chọn đúng thứ tự bằng ngoặc đơn

Khi phối hợp `and`, `or`, `not`, dùng ngoặc để diễn đạt rõ **nhóm tích cực** và **nhóm loại trừ**. Cách này tránh nhầm ý nghĩa giữa người đọc và kết quả parser khi biểu thức phức tạp.

Xét quy tắc nghiệp vụ:

> Chỉ theo dõi bean service, trên hai method `send` hoặc `receive`, nhưng không áp dụng cho bean thử nghiệm `testService`.

Viết:

~~~text
bean(*Service)
and (execution(* demo.DefaultMessageService.send(..))
     or execution(* demo.DefaultMessageService.receive(..)))
and not bean(testService)
~~~

Trong một XML attribute, xuống dòng có thể bị chuẩn hóa thành dấu cách. Với bài học hoặc cấu hình cần dễ diff, viết gọn trên cùng dòng hoặc tách pointcut một cách có chủ đích.

~~~xml
<aop:pointcut id="auditedCalls"
    expression="bean(*Service) and (execution(* demo.DefaultMessageService.send(..)) or execution(* demo.DefaultMessageService.receive(..))) and not bean(testService)"/>
~~~

Quy tắc trên thực hiện ba bước logic:

1. `bean(*Service)`: chọn những Spring beans mà tên khớp wildcard.
2. `(send or receive)`: chỉ giữ lại hai nhóm method, không giới hạn vào một nhóm duy nhất.
3. `and not bean(testService)`: trừ các invocation trên bean thử nghiệm.

Nếu viết thành `bean(*Service) and send or receive and not bean(testService)` mà không có ngoặc, cấu trúc đã khác về cách liên kết toán tử và dễ khiến `receive` vượt qua một phần điều kiện mong muốn. Luôn đưa `or` vào nhóm rõ ràng khi hai nhánh phải dùng chung điều kiện bao ngoài.

**Một tình huống nhầm phủ định:**

~~~text
not (A or B)   =   (not A) and (not B)
not (A and B)  =   (not A) or (not B)
~~~

Ví dụ `not (send or receive)` chọn các method **không thuộc cả hai nhóm send/receive**; còn `not send or receive` có ngữ nghĩa khác. Trong Spring AOP, các điểm match vẫn phải là method invocation qua proxy, dù biểu thức Boolean về mặt hình thức cho kết quả true.

## 6. Ví dụ hoàn chỉnh Spring XML AOP dùng cả `and`, `or`, `not`

Ví dụ sử dụng Java 17, Maven và Spring Framework 6.1.15. Hai bean `messageService` và `testService` dùng cùng implementation `DefaultMessageService`. Chỉ bean `messageService` được advice trên `send` và `receive`; method `health` không nằm trong biểu thức, còn bean thử nghiệm bị loại bằng `not bean(testService)`.

Cấu trúc:

~~~text
spring-xml-pointcut-operators/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── Application.java
    │   ├── MessageService.java
    │   ├── DefaultMessageService.java
    │   └── LoggingAspect.java
    └── resources/applicationContext.xml
~~~

### 6.1. Maven

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-xml-pointcut-operators</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.1.15</version>
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
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration><mainClass>demo.Application</mainClass></configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp ApplicationContext, `spring-aop` cung cấp Spring proxy/advisor runtime, còn `aspectjweaver` chứa công cụ hỗ trợ phân tích/match AspectJ pointcut được Spring dùng. Đây vẫn là **Spring AOP**, không chạy compile-time hay load-time weaving.

### 6.2. Interface dùng để gọi qua Spring proxy

**src/main/java/demo/MessageService.java**

~~~java
package demo;

public interface MessageService {
    String send(String id);
    String receive(String id);
    String health();
}
~~~

**src/main/java/demo/DefaultMessageService.java**

~~~java
package demo;

public class DefaultMessageService implements MessageService {
    @Override
    public String send(String id) {
        System.out.println("target: send " + id);
        return "sent " + id;
    }

    @Override
    public String receive(String id) {
        System.out.println("target: receive " + id);
        return "received " + id;
    }

    @Override
    public String health() {
        System.out.println("target: health");
        return "UP";
    }
}
~~~

Hai bean cùng Java class có thể cho ra kết quả advice khác nhau vì pointcut `bean(...)` xét Spring bean name. Không cần gắn annotation trên class để ví dụ XML-based này hoạt động.

### 6.3. Bean chứa advice

**src/main/java/demo/LoggingAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;

public class LoggingAspect {
    public void before(JoinPoint joinPoint) {
        System.out.println("advice: " + joinPoint.getSignature().getName());
    }
}
~~~

`LoggingAspect` là Java class đơn giản. Nó sẽ được đăng ký bằng `<bean>` và liên kết tới `<aop:before method="before">`. Không cần `@Aspect` hoặc `@Before` trong lớp khi dùng schema-based AOP.

### 6.4. Định nghĩa pointcut trong XML

**src/main/resources/applicationContext.xml**

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

    <bean id="messageService" class="demo.DefaultMessageService"/>
    <bean id="testService" class="demo.DefaultMessageService"/>
    <bean id="loggingAspect" class="demo.LoggingAspect"/>

    <aop:config proxy-target-class="false">
        <aop:pointcut id="auditedCalls"
            expression="bean(*Service) and (execution(* demo.DefaultMessageService.send(..)) or execution(* demo.DefaultMessageService.receive(..))) and not bean(testService)"/>

        <aop:aspect ref="loggingAspect">
            <aop:before pointcut-ref="auditedCalls" method="before"/>
        </aop:aspect>
    </aop:config>
</beans>
~~~

Các thành phần có vai trò rõ ràng:

- `xmlns:aop` và `spring-aop.xsd` khai báo cú pháp namespace cho tài liệu XML.
- Ba `<bean>` tạo target bean (hai tên), và aspect bean chứa method advice.
- `<aop:pointcut id="auditedCalls">` lưu một biểu thức hoàn chỉnh; `pointcut-ref="auditedCalls"` tham chiếu **ID cấu hình pointcut**.
- `<aop:aspect ref="loggingAspect">` trỏ đến Spring bean chứa method `before`.
- `proxy-target-class="false"` phù hợp với `MessageService` interface của hai target. Lời gọi bên ngoài nên lấy bean qua interface.
- Khi advice chạy, `LoggingAspect.before` chỉ ghi log trước khi method target thực thi, không thay đổi return value.

`not bean(testService)` không xóa bean `testService` khỏi context; nó chỉ làm cho **pointcut cụ thể này** không match method invocation trên bean đó.

### 6.5. Gọi Spring beans

**src/main/java/demo/Application.java**

~~~java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Application {
    public static void main(String[] args) {
        try (var context =
                new ClassPathXmlApplicationContext("applicationContext.xml")) {

            MessageService production =
                    context.getBean("messageService", MessageService.class);
            MessageService testing =
                    context.getBean("testService", MessageService.class);

            System.out.println("result: " + production.send("M-1"));
            System.out.println("result: " + production.receive("M-2"));
            System.out.println("result: " + production.health());
            System.out.println("result: " + testing.send("T-1"));
        }
    }
}
~~~

Ở thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chương trình in (bỏ qua log Maven/Spring phụ thuộc môi trường) theo thứ tự:

~~~text
advice: send
target: send M-1
result: sent M-1
advice: receive
target: receive M-2
result: received M-2
target: health
result: UP
target: send T-1
result: sent T-1
~~~

Giải thích kết quả:

1. `production.send`: bean tên `messageService` match `bean(*Service)`, nhánh `send` match, điều kiện `not bean(testService)` cũng true ⇒ advice chạy.
2. `production.receive`: khớp nhánh `receive` của OR ⇒ advice chạy.
3. `production.health`: không khớp cả hai nhánh method-name bên trong ngoặc ⇒ không chạy advice.
4. `testing.send`: khớp tên method nhưng bean tên `testService` bị phủ định ⇒ không chạy advice.

Cần lấy service từ `ApplicationContext` để có Spring-managed proxy. Tạo `new DefaultMessageService()` rồi gọi `send` sẽ không đi qua Spring AOP. Self-invocation như `this.send(...)` bên trong chính target cũng thường bỏ qua proxy.

## 7. Biểu thức dùng dấu toán tử có ý nghĩa tương đương

Ta có thể thay **chỉ thuộc tính expression** trong pointcut ví dụ bằng:

~~~xml
<aop:pointcut id="auditedCalls"
    expression="bean(*Service) &amp;&amp; (execution(* demo.DefaultMessageService.send(..)) || execution(* demo.DefaultMessageService.receive(..))) &amp;&amp; !bean(testService)"/>
~~~

Bản này tương đương bản dùng `and`, `or`, `not`. XML parser giải mã hai cặp `&amp;&amp;` thành `&&`; Spring pointcut parser hiểu các toán tử và điều kiện như cũ. Dấu `||`, `!`, dấu ngoặc và wildcard dùng nguyên văn. **Không đặt cả hai `<aop:pointcut id="auditedCalls">` trùng ID trong cùng cấu hình**; đây là một bản thay thế để so sánh.

Sơ đồ quan sát cú pháp:

~~~text
applicationContext.xml
  expression="A &amp;&amp; (B || C) &amp;&amp; !D"
            |
            | XML parser
            v
  pointcut string: A && (B || C) && !D
            |
            | Spring AOP/AspectJ expression parser
            v
  match: A and (B or C) and not D
            |
            | Spring advisor / proxy
            v
  Chỉ lời gọi bean method thỏa điều kiện mới chạy advice
~~~

Đặc biệt, escape đúng không làm thay đổi logic lọc `bean(*Service)`: tên `messageService` và `testService` vẫn như trước.

## 8. Phân biệt lỗi XML parsing và lỗi pointcut parsing

**Lỗi ở lớp XML parsing:** XML chưa được parse thành document hợp lệ.

~~~xml
<!-- Sai XML: dấu & chưa escape. -->
<aop:pointcut id="brokenXml"
    expression="execution(* demo..*.*(..)) && bean(*Service)"/>
~~~

Hệ quả: Spring có thể báo lỗi khi đọc XML trước khi tạo ApplicationContext. Cách sửa: thay `&&` bằng `and`, hoặc `&amp;&amp;`; kiểm tra thêm namespace và `schemaLocation`.

**Lỗi ở lớp pointcut parsing:** XML hợp lệ nhưng biểu thức đưa vào Spring không hợp lệ hoặc dùng designator không được Spring AOP hỗ trợ.

~~~xml
<!-- XML hợp lệ; biểu thức sai vì thiếu vế bên phải của and. -->
<aop:pointcut id="brokenPointcut"
    expression="execution(* demo..*.*(..)) and"/>
~~~

Hệ quả: XML parser hoàn thành; Spring/AspectJ pointcut parser báo lỗi expression/advisor khi khởi tạo hạ tầng. Cách sửa: viết đầy đủ vế phải và đảm bảo kiểu pointcut designator được Spring AOP hỗ trợ (`execution`, `within`, `this`, `target`, `args`, `bean`, các designator annotation tương ứng...). Spring AOP không hỗ trợ mọi loại join point của AspectJ (ví dụ field `get`, `set` hoặc `call`).

**Không chạy advice dù XML và pointcut hợp lệ:** biểu thức match tập phương thức rỗng, bean không đi qua proxy hoặc có self-invocation. Đây là vấn đề runtime/proxy boundary, không có nghĩa phải thêm XML escaping.

## 9. Cẩn trọng với named pointcut trong XML

Một `<aop:pointcut id="allServiceMethods" expression="..."/>` đặt tên cho **một biểu thức hoàn chỉnh**. Advice dùng `pointcut-ref="allServiceMethods"`, còn `expression="allServiceMethods and not bean(testService)"` **không hợp lệ** vì ID XML không phải named pointcut method có thể gọi trong expression.

Nếu cần phủ định bean, khai báo scope cuối cùng ngay trong expression:

~~~xml
<aop:pointcut id="productionServices"
    expression="execution(* demo..*Service.*(..)) and not bean(testService)"/>
~~~

Khi các advice dùng cùng tập method, chúng tham chiếu ID `productionServices`. Bài **“Pointcut có tên và pointcut-ref trong XML”** phân tích đầy đủ khả năng dùng lại của ID tại cấp config/aspect, cùng test thay đổi phạm vi.

## 10. Kết hợp pointcut `@annotation`, `within` và `bean`

Ví dụ để log mọi method trong package `demo` **có annotation** `@Audited`, ngoại trừ bean nội bộ `internalService`:

~~~xml
<aop:pointcut id="annotatedBusinessMethods"
    expression="within(demo..*) and @annotation(demo.Audited) and not bean(internalService)"/>
~~~

Điều kiện trên có ý nghĩa:

- `within(demo..*)` giới hạn method execution trong namespace class/type tương ứng.
- `@annotation(demo.Audited)` lọc theo annotation trên method.
- `not bean(internalService)` loại bean nội bộ theo ID/name.

Đây là ví dụ **độc lập**; class `demo.Audited` cần được định nghĩa với runtime retention và đặt trên method thực tế nếu muốn chạy. Không nhầm `@annotation` là XML annotation namespace; ký tự `@` ở đây thuộc pointcut syntax.

Trong project lớn, kết hợp phạm vi kiểu/package với điều kiện mục tiêu giúp expression dễ kiểm tra hơn. Không dùng `or` vô ý để đưa vào các method ngoài vùng cần thiết:

~~~xml
<!-- Dễ chọn nhầm: nhánh thứ hai không chịu giới hạn within(demo..*). -->
<aop:pointcut id="tooBroad"
    expression="within(demo..*) and execution(* *.save(..)) or execution(* *.delete(..))"/>
~~~

Phiên bản nêu rõ cùng một phạm vi:

~~~xml
<aop:pointcut id="scoped"
    expression="within(demo..*) and (execution(* *.save(..)) or execution(* *.delete(..)))"/>
~~~

Các ví dụ này chỉ minh họa điều kiện; không cần tạo thêm advice nếu mục tiêu hiện tại chỉ là phân tích cú pháp.

## 11. Kết hợp với `aop:aspectj-autoproxy` và `@Aspect`

Với aspect dùng annotation Java, cú pháp logic nằm **trong Java string** nên không cần XML entity:

~~~java
@Aspect
public class TraceAspect {
    @Before("within(demo..*) && (execution(* *.send(..)) || execution(* *.receive(..))) && !bean(testService)")
    public void before() {}
}
~~~

Đây là fragment, cần imports và phải đăng ký `TraceAspect` thành Spring bean. XML chỉ cần đăng ký bean ấy rồi bật `<aop:aspectj-autoproxy/>`; annotation method có thể dùng `&&` bình thường. Nếu dùng schema-style `<aop:config>` để định nghĩa advice, không cần thêm auto-detection @AspectJ cho chính advice ấy.

## 12. Thứ tự sửa lỗi khi pointcut XML không hoạt động

1. **Kiểm tra XML hợp lệ:** `xmlns:aop`, `spring-aop.xsd`, đúng cặp namespace–schema trong `xsi:schemaLocation`, không chứa ký tự `&` chưa escape; tránh `&&` thô trong attribute.
2. **Kiểm tra expression hợp lệ:** mỗi toán tử có đủ toán hạng, các ngoặc cân bằng, `and`/`or`/`not` không viết sai chính tả, designator nằm trong tập Spring AOP hỗ trợ.
3. **Kiểm tra ý nghĩa Boolean:** dùng ngoặc cho nhóm OR rồi AND với điều kiện chung; `not` được áp dụng vào đúng sub-expression; tránh lọc nhiều hơn hoặc rộng hơn mong muốn.
4. **Kiểm tra bean thực tế:** tên bean có thật và match `bean(...)`, target thuộc ApplicationContext, advice/aspect bean đã đăng ký, `pointcut-ref` khớp ID.
5. **Kiểm tra proxy invocation:** gọi qua bean Spring (interface khi dùng JDK proxy), không dùng `new` target hoặc trông đợi self-invocation tự được chặn.
6. **Kiểm tra output bằng nhiều trường hợp:** một method phải match AND, một method thỏa một nhánh OR, một method bị NOT loại, một method không thuộc nhóm; so sánh thứ tự log advice/target.

### Ma trận test cho ví dụ mục 6

| Bean | Method | `bean(*Service)` | `send or receive` | `not bean(testService)` | Advice? |
| --- | --- | --- | --- | --- | --- |
| `messageService` | `send` | Đúng | Đúng | Đúng | Có |
| `messageService` | `receive` | Đúng | Đúng | Đúng | Có |
| `messageService` | `health` | Đúng | Sai | Đúng | Không |
| `testService` | `send` | Đúng | Đúng | Sai | Không |
| `testService` | `receive` | Đúng | Đúng | Sai | Không |

Nếu môi trường thực tế có nhiều auto-proxy configurations hoặc kiểu proxy khác nhau, kiểm tra bằng integration test lấy bean trực tiếp từ cùng `ApplicationContext`. Không suy đoán rằng một biểu thức pointcut đúng là đủ để advice chạy mọi lúc: Spring AOP phụ thuộc khả năng intercept qua proxy.

## 13. Những lỗi dễ lặp lại

Các lỗi nổi bật: (1) `&&` thô làm XML parser từ chối tài liệu; (2) escape hai lần khiến parser pointcut nhận literal sai; (3) thiếu ngoặc quanh OR mở rộng tập match; (4) nhầm `pointcut-ref` là biểu thức; (5) `not bean(testService)` bị bỏ và chặn nhầm bean thử nghiệm.

Khi sửa, kiểm tra **hai tầng parser** theo thứ tự XML entity → pointcut expression rồi thử ma trận: hai method cần match, method ngoài nhóm OR, bean phải loại trừ, method trên object không qua proxy. Chỉ có proxy chưa chứng minh advice cụ thể đã chạy.

