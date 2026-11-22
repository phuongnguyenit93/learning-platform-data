# Mẫu tên, kiểu con, overload và danh sách tham số trong Spring AOP pointcut

## 1. Mục tiêu bài học

Trong Spring Framework, một `@Aspect` có thể sử dụng biểu thức `execution(...)` để chọn những **method execution** cụ thể trên các **Spring-managed beans**. Khi một service chứa nhiều phương thức có tên tương tự, có overload, được triển khai qua interface/class hierarchy và có danh sách tham số khác nhau, việc viết biểu thức chính xác quan trọng hơn việc chỉ dùng một wildcard thật rộng.

Bài học tập trung vào bốn kỹ thuật chọn phương thức:

1. **Mẫu tên**: tên chính xác, tiền tố, hậu tố hoặc wildcard `*` trong tên method.
2. **Kiểu con**: ký hiệu `+` sau **type pattern** để tính cả type đó và các subtype/implementation phù hợp.
3. **Overload**: phân biệt các method **cùng tên** dựa trên **số lượng và kiểu tham số được khai báo**.
4. **Danh sách tham số**: phân biệt `()`, `(*)`, `(..)`, và các danh sách hỗn hợp như `(java.lang.String,int)`, `(java.lang.String,..)`.

Sau bài này, bạn có thể tự dự đoán một `@Before` advice có chạy hay không, thay vì sửa pointcut bằng cách đoán. Bạn cũng sẽ biết tại sao **giá trị argument ở runtime**, **phép overload resolution lúc biên dịch Java** và **Spring AOP proxy invocation** là ba phần khác nhau.

**Giới hạn nội dung:** Chỉ học cách viết và kiểm chứng các pointcut trong **Spring AOP dựa trên proxy**, dùng annotation style `@Aspect`, không học các kiểu AspectJ weaving ngoài Spring. Ví dụ dùng **Java 17+**, **Spring Framework 6.2.x** và Maven.

## 2. Điều kiện để pointcut thực sự kích hoạt advice

`execution(...)` đối chiếu **chữ ký method**; lời gọi chỉ được advice khi bean và aspect đã được Spring đăng ký, hạ tầng AOP hoạt động và caller đi qua **Spring proxy**. Một chữ ký khớp vẫn không tạo advice nếu gọi trực tiếp đối tượng tạo bằng `new`, gọi `this.method()` nội bộ, hoặc proxy không thể chặn method đó (như `private`/`final` trong class-based proxy). JDK proxy chỉ expose những method trên interface của proxy.

Khi thử các mẫu tên/kiểu con/overload bên dưới, luôn đối chiếu **ba câu hỏi riêng**: Java đã chọn chữ ký nào, expression có khớp chữ ký ấy không, và invocation có đi qua proxy không? Spring AOP giới hạn ở method execution của Spring-managed beans.

## 3. Nhắc nhanh cú pháp `execution(...)`

Dạng rút gọn: `execution(modifiers? return-type declaring-type?.method-name(parameter-pattern))`; đây là ký hiệu mô tả, **dấu `?` không phải ký tự nhập vào biểu thức**. Ví dụ:

~~~java
@Before("execution(public java.lang.String demo.TaskApi.lookup(java.lang.String))")
public void beforeLookup() {
    // Khớp method public lookup(String) trả về String trên TaskApi.
}
~~~

Đoạn trên nằm trong một `@Aspect` được đăng ký. `*` ở vị trí tên/kiểu và `..` trong phần package/tham số có ý nghĩa khác nhau; các ví dụ tiếp theo lần lượt khai triển từng vị trí. Chú ý `TaskApi+` ở phần **type pattern** để diễn tả cả subtype, còn `(*)` và `(..)` trong **parameter pattern** có ranh giới số tham số khác nhau.

## 4. Mẫu tên phương thức: exact, prefix, suffix và wildcard

### 4.1. Tên chính xác

~~~text
execution(* demo.TaskApi.lookup(..))
~~~

Chọn những method execution tên **lookup** phù hợp với TaskApi; dấu `(..)` cho phép mọi số lượng và kiểu tham số. Nếu TaskApi có ba overload lookup, cả ba có thể được chọn.

### 4.2. Tiền tố

~~~text
execution(* demo.TaskApi.list*(..))
~~~

Tên bắt đầu bằng **list**, ví dụ `listAll` và `listByOwner`. Method `lookup` hoặc `inspect` không khớp chỉ vì nằm cùng bean.

### 4.3. Hậu tố

~~~text
execution(* demo.TaskApi.*Status(..))
~~~

Tên kết thúc bằng **Status**, ví dụ `getStatus`, `updateStatus`. Không chọn `statusCode` vì hậu tố không đúng.

### 4.4. Có ký tự bất kỳ ở giữa

~~~text
execution(* demo.TaskApi.find*By*(..))
~~~

Chọn tên có phần đầu **find**, tiếp theo một đoạn bất kỳ, rồi **By**, tiếp theo một đoạn bất kỳ. Chẳng hạn `findOrderById` phù hợp, nhưng `findAll` thì không.

### 4.5. Mọi tên method

~~~text
execution(* demo.TaskApi.*(..))
~~~

Phần `*` tại **name-pattern** bỏ ràng buộc tên. Điều này dễ dùng để debug nhưng có thể khiến rất nhiều method bị advice khi đem vào ứng dụng thật.

**Cách đọc an toàn:** viết type và method name tách biệt: `demo.TaskApi.list*(..)` là một type cụ thể kết hợp prefix method, không có nghĩa Spring quét toàn bộ package `demo` theo tên bean.

## 5. Phạm vi package và các cấp thư mục package

Điểm hay gây nhầm nhất là phân biệt `.` và `..` trong phần type.

~~~text
execution(* demo.service.*.*(..))
~~~

Mô tả method trên các type **trực tiếp thuộc package** `demo.service`.

~~~text
execution(* demo.service..*.*(..))
~~~

Mở rộng xuống **demo.service và các subpackage** như `demo.service.internal`, `demo.service.payment` khi các type/method thực sự phù hợp.

| Type thực tế | `demo.service.*` | `demo.service..*` |
| --- | --- | --- |
| `demo.service.OrderService` | Khớp phạm vi type | Khớp phạm vi type |
| `demo.service.billing.BillingService` | Không | Khớp phạm vi type |
| `demo.repository.OrderRepository` | Không | Không |
| `demo.service_internal.LegacyService` | Không | Không |

Bảng chỉ đối chiếu **type-pattern**, chưa nói tới việc bean tương ứng có proxy/advisor hay không.

Đừng nhầm với biểu thức bean name. Ví dụ `bean(*Service)` là **pointcut designator riêng của Spring** xét **tên bean**, không phải một phần của `execution` và không suy ra package class.

## 6. Kiểu con: vai trò của dấu + sau type pattern

Trong type pattern kiểu AspectJ mà Spring AOP sử dụng, hậu tố **`+`** biểu thị **type được ghi trong biểu thức hoặc bất kỳ subtype phù hợp của nó**, bao gồm subclass và implementation của interface.

Ví dụ:

~~~text
demo.TaskApi+
~~~

Được đọc là `TaskApi` **và các subtype/implementation** của TaskApi, trong phạm vi ngữ nghĩa pointcut. Ký hiệu này khác hoàn toàn dấu `+` để nối String của Java: trong annotation, nó chỉ là ký tự bên trong biểu thức Spring AOP.

Khi kết hợp với execution:

~~~text
execution(* demo.TaskApi+.lookup(..))
~~~

ý định là chọn những execution phù hợp của method **lookup** trên TaskApi hoặc type con tương ứng. Cách này hữu ích khi:

- nhiều implementation của cùng một interface được đăng ký thành các bean khác nhau;
- một interface con khai báo thêm method;
- một base class được mở rộng bởi nhiều service class;
- muốn đặt một quy ước pointcut ở mức hợp đồng thay vì liệt kê từng implementation.

**Không phải mọi điểm matching đều tự động chứng minh có proxy.** Nếu Spring dùng JDK dynamic proxy, những method muốn được gọi qua proxy cần được công bố trong interface được proxy triển khai. Nếu dùng CGLIB, method vẫn phải overridable và được gọi qua proxy.

### 6.1. Phân biệt hai pattern

~~~text
execution(* demo.TaskApi.lookup(..))
execution(* demo.TaskApi+.lookup(..))
~~~

Dòng đầu tập trung vào type được đặt tên `TaskApi`. Dòng thứ hai thể hiện rõ chủ đích bao gồm type con. Trong Spring AOP, một execution biểu diễn bởi interface cũng có thể áp dụng cho method được triển khai trong concrete class; do đó **không nên khẳng định hai expression lúc nào cũng cho kết quả khác nhau** chỉ dựa vào dấu `+`. Với các hierarchy phức tạp, kiểm chứng thực tế qua Spring-managed proxy và các method mong muốn là cần thiết.

### 6.2. Dùng + ở pattern của tham số

Giả sử:

~~~java
package demo;

public class Payload {
}

public class UrgentPayload extends Payload {
}
~~~

Đây là **hai class minh họa đặt trong hai file riêng**, vì Java chỉ cho một public top-level class tương ứng mỗi file. Nếu service có hai overload:

~~~java
void update(Payload payload);
void update(UrgentPayload payload);
~~~

thì:

~~~text
execution(* demo.TaskApi.update(demo.Payload+))
~~~

có thể chọn các chữ ký với một tham số có kiểu là **Payload hoặc subtype của Payload**. `Payload+` là **type pattern cho declared parameter type**, không phải “chỉ match khi argument runtime là một subtype”.

### 6.3. So sánh với target(...) và this(...)

Các pointcut designator khác có thể chọn theo đối tượng hiện diện tại invocation:

~~~text
target(demo.TaskApi)
this(demo.TaskApi)
~~~

Trong Spring AOP, **target(...)** xét target object, **this(...)** xét proxy object. Đây không phải cú pháp chọn một overloaded method theo chữ ký; thường kết hợp chúng với execution khi có yêu cầu cụ thể.

**Không thay `Payload+` bằng `args(Payload)` một cách tùy tiện**: `args` quan tâm **kiểu argument tại runtime**, trong khi **execution** quan tâm chữ ký method. Hai phương thức với cùng argument runtime có thể match pointcut execution khác nhau do overload được chọn từ trước.

## 7. Danh sách tham số: (), (*), (..) và hỗn hợp

Đây là nhóm quy tắc cần nhớ chính xác:

| Parameter pattern | Ý nghĩa |
| --- | --- |
| `()` | **Không có** tham số |
| `(*)` | **Đúng một** tham số, kiểu bất kỳ |
| `(..)` | **0 hoặc nhiều** tham số, kiểu bất kỳ |
| `(java.lang.String)` | Đúng một tham số, declared type String |
| `(long)` | Đúng một tham số primitive long |
| `(java.lang.String,int)` | Đúng hai tham số, đúng thứ tự String rồi primitive int |
| `(*,java.lang.String)` | Đúng hai tham số, đầu tùy kiểu, thứ hai String |
| `(java.lang.String,..)` | Tham số đầu String; phía sau có thể 0 hoặc nhiều tham số |
| `(..,int)` | Tham số cuối int; trước đó có thể 0 hoặc nhiều tham số |

Ví dụ **TaskApi** có:

~~~java
String lookup(String code);
String lookup(long id);
String lookup(String code, int version);
~~~

Đối chiếu:

| Pattern | lookup(String) | lookup(long) | lookup(String,int) |
| --- | --- | --- | --- |
| `lookup()` | Không | Không | Không |
| `lookup(*)` | Có | Có | Không |
| `lookup(..)` | Có | Có | Có |
| `lookup(java.lang.String)` | Có | Không | Không |
| `lookup(long)` | Không | Có | Không |
| `lookup(java.lang.String,int)` | Không | Không | Có |
| `lookup(java.lang.String,..)` | Có | Không | Có |
| `lookup(*,int)` | Không | Không | Có |
| `lookup(..,int)` | Không | Không | Có |

**Thứ tự parameter là quan trọng.** `(String,int)` khác `(int,String)`. Nếu method được khai báo `lookup(String,int)`, biểu thức đảo thứ tự sẽ không khớp method ấy.

**Primitive khác wrapper.** `lookup(long)` không có declared parameter type `java.lang.Long`, dù Java tự động boxing/unboxing ở điểm gọi khác nhau. Muốn match chính xác theo chữ ký, dùng kiểu được khai báo.

### 7.1. Dấu hai chấm? Không, dấu hai chấm không có ý nghĩa wildcard

Đôi khi người học viết `lookup(...)` giống ký hiệu varargs của Java. Trong AspectJ pointcut:

~~~text
lookup(..)
~~~

mới là mẫu cho **bất kỳ số lượng tham số**. Không thêm dấu chấm thứ ba để chọn mọi tham số.

### 7.2. Dùng (*) không giống dùng (..)

Nếu service có `void refresh()`, pattern `refresh(*)` **không** match, còn `refresh(..)` có. Tương tự, với `refresh(String,int)`, `refresh(*)` không match vì có hai tham số.

Một lời khuyên thực hành: nếu muốn áp dụng advice cho **mọi overload** cùng tên, bắt đầu bằng `(..)`; nếu cần phân biệt overload, ghi từng kiểu hoặc đúng số lượng.

### 7.3. Varargs

Method Java:

~~~java
public void publish(String... events) {
    // ...
}
~~~

thực chất có kiểu tham số array `String[]` trong method signature. Pattern `publish(..)` có thể bao quát method này; nhưng đừng diễn giải nó là “chỉ varargs”. Nếu cần chọn đúng kiểu array, nghiên cứu và thử type pattern `java.lang.String[]` tương ứng.

Các fragment trong mục này **chỉ minh họa chữ ký**, không thay thế source files của dự án runnable bên dưới.

## 8. Overload: Spring AOP không lựa chọn overload thay Java

**Overloading** là nhiều method cùng tên, khác danh sách parameter. Ví dụ:

~~~java
void update(Payload payload);
void update(UrgentPayload payload);
~~~

Khi Java biên dịch:

~~~java
Payload value = new UrgentPayload();
service.update(value);
~~~

Overload **update(Payload)** được chọn bởi **kiểu compile-time của biến `value`** (giả sử những overload trên), dù runtime object là **UrgentPayload**. Spring AOP không thay Java overload resolution.

Ngược lại:

~~~java
service.update(new UrgentPayload());
~~~

biểu thức argument có compile-time type **UrgentPayload**, nên Java chọn overload **update(UrgentPayload)**.

Điểm quan trọng:

- **execution(...update(demo.Payload))** chú ý **declared parameter type** của method `update(Payload)`.
- **execution(...update(demo.UrgentPayload))** chú ý **declared parameter type** của `update(UrgentPayload)`.
- **execution(...update(demo.Payload+))** bao gồm cả các declared type là Payload và subtype tương ứng.
- **args(demo.UrgentPayload)** là điều kiện kiểu **argument runtime** trong Spring AOP; không đồng nghĩa việc Java đã chọn overload `update(UrgentPayload)`.

Một instance UrgentPayload có thể được truyền tới method `update(Payload)`. Do đó, một pointcut dùng **args** có thể quan sát type runtime UrgentPayload trong invocation tới signature `update(Payload)`, trong khi expression execution ràng buộc riêng signature vẫn nhận diện nó là `update(Payload)`.

Đây là nguyên nhân nhiều lỗi “pointcut không chọn đúng overload” thực ra đến từ việc hiểu nhầm kiểu biến Java khi gọi.

## 9. Ví dụ Maven chạy được: mẫu tên, kiểu con, overload và tham số

Ta tạo một ứng dụng Spring Framework thuần có một service triển khai **interface con** và hai overload **update** với kiểu cha/con. Aspect định nghĩa nhiều `@Before` pointcut **không chồng nhau** trên cùng một lời gọi trong kịch bản chính, để stdout có thứ tự dễ kiểm tra.

Yêu cầu môi trường:

- **JDK 17+**
- **Maven 3.9+**
- **Spring Framework 6.2.12**
- **AspectJ Weaver 1.9.24** trên classpath để Spring phân tích các annotation/pointcut.

Cấu trúc thư mục:

~~~text
spring-aop-signature-patterns/
├── pom.xml
└── src/main/java/demo/
    ├── TaskApi.java
    ├── ExtendedTaskApi.java
    ├── Payload.java
    ├── UrgentPayload.java
    ├── TaskService.java
    ├── PatternAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-signature-patterns</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp ApplicationContext và kéo theo Spring AOP. `aspectjweaver` là dependency cần thiết cho cú pháp `@AspectJ` trong Spring AOP; project **không kích hoạt AspectJ weaving**.

### 9.2. Interface cha và interface con

**src/main/java/demo/TaskApi.java**

~~~java
package demo;

public interface TaskApi {
    void listAll();
    void listByOwner(String owner);

    String lookup(String code);
    String lookup(long id);
    String lookup(String code, int version);

    void update(Payload payload);
    void update(UrgentPayload payload);

    void inspect();
}
~~~

**src/main/java/demo/ExtendedTaskApi.java**

~~~java
package demo;

public interface ExtendedTaskApi extends TaskApi {
    void extra();
}
~~~

**TaskApi** định nghĩa ba overload `lookup`, hai overload `update` và hai method bắt đầu bằng **list**. **ExtendedTaskApi** là subtype của TaskApi và bổ sung `extra()`.

Nhờ `ExtendedTaskApi extends TaskApi`, type pattern `demo.TaskApi+` mô tả cả hợp đồng TaskApi và những subtype phù hợp. Không nên nhầm **inheritance của interface** với **component scanning**: Spring vẫn cần bean implementation.

### 9.3. Kiểu tham số cha/con

**src/main/java/demo/Payload.java**

~~~java
package demo;

public class Payload {

    private final String code;

    public Payload(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

**src/main/java/demo/UrgentPayload.java**

~~~java
package demo;

public class UrgentPayload extends Payload {

    public UrgentPayload(String code) {
        super(code);
    }
}
~~~

`UrgentPayload` kế thừa `Payload`, không override code(). Đây là hierarchy đơn giản để kiểm tra pointcut **Payload+** ở vị trí tham số. Không cần dùng annotation tùy chỉnh hoặc framework đặc biệt để tạo quan hệ subtype.

### 9.4. Service implementation

**src/main/java/demo/TaskService.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class TaskService implements ExtendedTaskApi {

    @Override
    public void listAll() {
        System.out.println("TARGET listAll");
    }

    @Override
    public void listByOwner(String owner) {
        System.out.println("TARGET listByOwner " + owner);
    }

    @Override
    public String lookup(String code) {
        System.out.println("TARGET lookup(String) " + code);
        return code;
    }

    @Override
    public String lookup(long id) {
        System.out.println("TARGET lookup(long) " + id);
        return Long.toString(id);
    }

    @Override
    public String lookup(String code, int version) {
        System.out.println("TARGET lookup(String,int) " + code + "/" + version);
        return code + ":" + version;
    }

    @Override
    public void update(Payload payload) {
        System.out.println("TARGET update(Payload) " + payload.code());
    }

    @Override
    public void update(UrgentPayload payload) {
        System.out.println("TARGET update(UrgentPayload) " + payload.code());
    }

    @Override
    public void extra() {
        System.out.println("TARGET extra");
    }

    @Override
    public void inspect() {
        System.out.println("TARGET inspect");
        this.listAll();
    }
}
~~~

Khai báo `@Service` khiến bean được phát hiện qua `@ComponentScan`. Method `inspect()` cố ý gọi `this.listAll()` để chỉ ra **self-invocation**: tuy tên listAll khớp expression `list*`, lời gọi nội bộ không đi qua proxy nên không có advice thứ hai.

### 9.5. Aspect chỉ dùng những signature pattern cần học

**src/main/java/demo/PatternAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class PatternAspect {

    @Before("execution(* demo.TaskApi+.list*(..))")
    public void beforeList(JoinPoint jp) {
        System.out.println("AOP name " + jp.getSignature().getName());
    }

    @Before("execution(* demo.TaskApi+.lookup(java.lang.String))")
    public void beforeLookupString() {
        System.out.println("AOP lookup(String)");
    }

    @Before("execution(* demo.TaskApi+.lookup(long))")
    public void beforeLookupLong() {
        System.out.println("AOP lookup(long)");
    }

    @Before("execution(* demo.TaskApi+.lookup(java.lang.String,int))")
    public void beforeLookupTwo() {
        System.out.println("AOP lookup(String,int)");
    }

    @Before("execution(* demo.TaskApi+.update(demo.Payload+))")
    public void beforeUpdate() {
        System.out.println("AOP update(Payload+)");
    }

    @Before("execution(* demo.TaskApi+.extra(..))")
    public void beforeExtra() {
        System.out.println("AOP extra");
    }
}
~~~

Các expression thể hiện bốn yêu cầu:

- **Tên:** `list*` chọn `listAll()`, `listByOwner(String)`.
- **Kiểu con ở declaring type:** `TaskApi+` bao gồm các subtype phù hợp; `extra()` tồn tại trong `ExtendedTaskApi` và triển khai ở TaskService.
- **Overload:** ba expression `lookup` có danh sách parameter **String**, **long**, **String,int** khác nhau.
- **Kiểu con ở parameter:** `update(demo.Payload+)` bao quát overload khai báo `Payload` và overload khai báo `UrgentPayload`.

Các pointcut trong ví dụ được chọn để **mỗi lời gọi bên ngoài tương ứng một advice duy nhất**, tránh cần suy đoán thứ tự khi có nhiều advice của cùng aspect cùng match.

**@Aspect** khai báo advice, **@Component** cho Spring đăng ký aspect thành bean. Không được hiểu rằng `@Aspect` tự làm một object bất kỳ ngoài Spring thành advisor.

### 9.6. Bật AOP và component scan

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

Trong ví dụ Spring Framework thuần:

- **@Configuration**: nguồn cấu hình Java.
- **@ComponentScan**: đăng ký TaskService và PatternAspect.
- **@EnableAspectJAutoProxy**: bật hạ tầng dùng các `@AspectJ` advice và Spring AOP proxy.

Nếu Spring AOP tự động dùng **JDK dynamic proxy** vì target triển khai interface, client nên lấy theo `TaskApi` hoặc `ExtendedTaskApi`, không cast sang TaskService.

### 9.7. Main để kiểm tra chữ ký và hành vi

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ExtendedTaskApi api = context.getBean(ExtendedTaskApi.class);
            System.out.println("IS_PROXY " + AopUtils.isAopProxy(api));

            api.listAll();
            api.listByOwner("team");

            System.out.println("RESULT " + api.lookup("A-1"));
            System.out.println("RESULT " + api.lookup(7L));
            System.out.println("RESULT " + api.lookup("A-2", 3));

            api.update(new Payload("B-1"));
            api.update(new UrgentPayload("U-1"));

            Payload declaredParent = new UrgentPayload("U-2");
            api.update(declaredParent);

            api.extra();
            api.inspect();
        }
    }
}
~~~

Ba lần `lookup(...)` giúp xác nhận overload; ba lần `update(...)` chứng minh việc Java chọn overload theo **compile-time type**, không chỉ theo runtime object.

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java
~~~

### 9.8. Stdout logic kỳ vọng

~~~text
IS_PROXY true
AOP name listAll
TARGET listAll
AOP name listByOwner
TARGET listByOwner team
AOP lookup(String)
TARGET lookup(String) A-1
RESULT A-1
AOP lookup(long)
TARGET lookup(long) 7
RESULT 7
AOP lookup(String,int)
TARGET lookup(String,int) A-2/3
RESULT A-2:3
AOP update(Payload+)
TARGET update(Payload) B-1
AOP update(Payload+)
TARGET update(UrgentPayload) U-1
AOP update(Payload+)
TARGET update(Payload) U-2
AOP extra
TARGET extra
TARGET inspect
TARGET listAll
~~~

Đây là **đầu ra logic mong đợi** của mã ví dụ, bỏ qua logging riêng của Maven và Spring. Khi chạy thực tế, hãy so cả thứ tự **AOP** trước **TARGET** cho các method match, và xác minh **không có AOP name listAll** ở lời gọi `this.listAll()` bên trong inspect.

### 9.9. Phân tích các lần gọi tiêu biểu

**listAll và listByOwner.** Hai method cùng bắt đầu bằng `list` nên match `list*(..)`. Các method `lookup` không match prefix `list`.

**lookup("A-1").** Biểu thức argument có compile-time type String; Java chọn overload `lookup(String)`. Advice `beforeLookupString` chạy.

**lookup(7L).** Literal 7L là long primitive, nên overload `lookup(long)` được chọn và advice tương ứng chạy.

**lookup("A-2", 3).** Có hai parameter String và int, nên chỉ expression `lookup(java.lang.String,int)` match trong ba advice lookup.

**update(new UrgentPayload("U-1")).** Java chọn overload `update(UrgentPayload)`, `Payload+` match kiểu declared subtype.

**Payload declaredParent = new UrgentPayload("U-2"); api.update(declaredParent).** Dù object runtime là UrgentPayload, Java chọn `update(Payload)` theo type của biến. `Payload+` vẫn match vì bao gồm type Payload. Log chứng minh method thực sự được chọn là `update(Payload)`.

**api.extra().** Interface con `ExtendedTaskApi` công bố method extra; `TaskApi+` cho phép biểu thức theo interface cha tính đến subtype phù hợp.

**api.inspect().** Không có advice chọn tên inspect. Bên trong target `this.listAll()` vẫn in TARGET listAll nhưng không qua Spring proxy để chạy advice cho listAll một lần nữa.

## 10. Bảng dự đoán match từ chương trình

Bảng xét **method signature**, không tự thay thế điều kiện bean/proxy.

| Pattern | listAll() | lookup(String) | lookup(long) | lookup(String,int) | update(Payload) | update(UrgentPayload) |
| --- | --- | --- | --- | --- | --- | --- |
| `execution(* demo.TaskApi+.list*(..))` | Có | Không | Không | Không | Không | Không |
| `execution(* demo.TaskApi+.lookup(..))` | Không | Có | Có | Có | Không | Không |
| `execution(* demo.TaskApi+.lookup(*))` | Không | Có | Có | Không | Không | Không |
| `execution(* demo.TaskApi+.lookup(java.lang.String))` | Không | Có | Không | Không | Không | Không |
| `execution(* demo.TaskApi+.lookup(java.lang.String,int))` | Không | Không | Không | Có | Không | Không |
| `execution(* demo.TaskApi+.update(demo.Payload))` | Không | Không | Không | Không | Có | Không |
| `execution(* demo.TaskApi+.update(demo.UrgentPayload))` | Không | Không | Không | Không | Không | Có |
| `execution(* demo.TaskApi+.update(demo.Payload+))` | Không | Không | Không | Không | Có | Có |
| `execution(* demo.TaskApi+.*(..))` | Có | Có | Có | Có | Có | Có |

Khi muốn debug một expression, hãy dùng bảng riêng cho từng phương thức và từng type pattern. Nếu đọc khó, tách pointcut rộng thành các named pointcuts.

## 11. Named @Pointcut để tránh lặp lại điều kiện

Một aspect lớn có thể tái sử dụng những điều kiện nhiều lần:

~~~java
@Pointcut("execution(* demo.TaskApi+.list*(..))")
public void listing() {
}

@Pointcut("execution(* demo.TaskApi+.lookup(..))")
public void lookups() {
}

@Pointcut("listing() || lookups()")
public void reads() {
}
~~~

Đây là **các method mẫu để đặt bên trong một class @Aspect** có import `org.aspectj.lang.annotation.Pointcut`, không phải file Java độc lập. Trong một aspect đầy đủ, advice có thể tham chiếu:

~~~java
@Before("reads()")
public void beforeRead(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
~~~

Nếu bổ sung advice này vào `PatternAspect` đang chạy ở mục 9, một số method sẽ có **nhiều advice cùng match**, nên stdout không còn đúng với bản gốc. Hãy thay advice cũ bằng advice named pointcut hoặc dùng một context test riêng.

Cũng đừng nhầm **visibility của method @Pointcut** với **modifier của method nghiệp vụ**. Một named pointcut `private void reads()` vẫn có thể chọn các public service methods; ngược lại, expression có `execution(public ...)` mới giới hạn modifier của method được chọn.

## 12. Cách kết hợp các nhóm điều kiện

### 12.1. Chọn public lookup trên subtype

~~~text
execution(public * demo.TaskApi+.lookup(..))
~~~

Expression thể hiện:

- method public;
- return type tùy ý;
- declaring type trong họ TaskApi phù hợp;
- tên chính xác lookup;
- số tham số và type tùy ý.

Nhờ `(..)`, overload mới thêm sau này cũng có thể được match mà không phải cập nhật expression.

### 12.2. Chọn tên list với đúng một tham số

~~~text
execution(* demo.TaskApi+.list*(*))
~~~

Trong ví dụ, `listByOwner(String)` match còn `listAll()` không match. Nếu chọn `list*(..)`, cả hai match.

### 12.3. Chọn tên update và parameter là Payload hoặc subtype

~~~text
execution(* demo.TaskApi+.update(demo.Payload+))
~~~

Đây là dạng tiêu biểu cho **kiểu con trong parameter signature**. Nó không có nghĩa có thể advise một Java method không tồn tại chỉ vì argument object thuộc kiểu Payload.

### 12.4. Giới hạn theo Spring bean name

Giả sử có nhiều bean triển khai TaskApi, chỉ muốn bean tên `taskService`:

~~~text
execution(* demo.TaskApi+.lookup(..)) && bean(taskService)
~~~

`bean(...)` là designator **riêng Spring AOP** để match bean name. Nó không phải tên Java method và không phải quy tắc subtype. Với `@Service TaskService` và component scanning thông thường, bean name mặc định là `taskService`; nếu bean được đăng ký với tên khác, điều kiện này có thể không match.

### 12.5. Điều kiện runtime argument

~~~text
execution(* demo.TaskApi+.update(..))
&& args(demo.UrgentPayload)
~~~

Kết hợp trên nói: method tên update của type phù hợp, và **argument runtime** là UrgentPayload. Điều này có thể match một lời gọi `update(Payload)` được truyền instance UrgentPayload. Không đồng nhất nó với expression chỉ chọn overload khai báo `update(UrgentPayload)`.

Khi viết `@Before`, có thể nối hai dòng thành một chuỗi Java duy nhất; ví dụ:

~~~java
@Before(
    "execution(* demo.TaskApi+.update(..)) && " +
    "args(demo.UrgentPayload)"
)
public void beforeUrgent() {
    // ...
}
~~~

Đây là **fragment minh họa**; nếu đặt cạnh advice update có sẵn, một invocation phù hợp sẽ có thêm advice khác nên log thay đổi.

## 13. Java inheritance và giới hạn chọn subtype

### 13.1. Interface extends interface

~~~java
interface BaseApi {
    void run();
}

interface ExtendedApi extends BaseApi {
    void extra();
}
~~~

Pattern có hậu tố `BaseApi+` biểu thị BaseApi hoặc type con. Tuy nhiên, nếu service bean chỉ được expose bằng một JDK proxy không công bố `ExtendedApi`, client không thể tùy ý gọi `extra()` trên interface `BaseApi`. Trong ví dụ chính, bean thực sự triển khai **ExtendedTaskApi** và client lấy theo **ExtendedTaskApi.class**.

### 13.2. Class extends class

~~~java
class BaseProcessor {
    public void process() {
    }
}

class SpecialProcessor extends BaseProcessor {
    public void extra() {
    }
}
~~~

Type pattern có hậu tố `BaseProcessor+` bao hàm những subclass phù hợp. Nhưng để **Spring AOP** can thiệp method trên class-based proxy, target class/method vẫn phải cho phép subclass/override và caller phải đi qua proxy. Không dùng inheritance pattern để kỳ vọng chặn `final`, `private` hoặc constructor.

### 13.3. Khác package và method không visible

Nếu subclass nằm ở package khác, một method package-private của superclass có thể không visible cho subclass; CGLIB không thể override nó theo cách thông thường. Biểu thức subtype `+` **không xóa Java visibility constraints**.

### 13.4. Hierarchy không đồng nghĩa mọi overload được khai báo ở một nơi

Một interface con có thể bổ sung method cùng tên với interface cha nhưng parameter khác. Từ góc nhìn Java, đây vẫn là những overload khác nhau. Muốn chọn tất cả, dùng `name(..)` kết hợp phạm vi type phù hợp; muốn một overload cụ thể, ghi rõ parameter types.

## 14. Những góc cạnh thường gặp

### 14.1. Generic types và bridge methods

Nếu interface có:

~~~java
interface Repository<T> {
    T save(T value);
}
~~~

Và class triển khai `Repository<String>`, compiler có thể tạo **bridge method** để giữ tương thích sau type erasure. Đừng đoán rằng một pointcut ghi type argument tổng quát có thể phân biệt mọi `List<String>` và `List<Integer>` ở runtime. Khi dùng generic interface phức tạp, cần integration test thực tế trên proxy và signature được Spring resolve.

### 14.2. Varargs là array ở method signature

~~~java
void publish(String... items);
~~~

Tại cấp JVM, parameter type của phương thức là `String[]`. `publish(..)` match được danh sách tham số tùy ý, nhưng không có ý nghĩa “method varargs”. Muốn chọn riêng một phương thức varargs/array, kiểm tra array type pattern được hỗ trợ và signature thật.

### 14.3. Kiểu trả về không tham gia overload resolution của Java

Java **không cho phép** định nghĩa hai overload cùng tên và cùng parameter list mà **chỉ khác return type**:

~~~text
String read(String id)
int read(String id)
~~~

Đây là mô tả **không hợp lệ nếu đặt cả hai trong một class/interface**. Trong execution pattern bạn có thể lọc theo return type, nhưng đó không phải cách Java phân biệt hai overload ở source.

### 14.4. Dùng this() và target() đúng ngữ nghĩa Spring AOP

Trong Spring AOP, `this(demo.SomeType)` xét **proxy object**, còn `target(demo.SomeType)` xét **target object**. Với JDK dynamic proxy, proxy có thể không là instance của class implementation dù target là instance của class đó.

Nếu điều kiện của bạn liên quan đến **kiểu implementation tại runtime** thay vì signature, hãy cân nhắc `target`, nhưng không dùng nó thay một expression overload cụ thể khi yêu cầu dựa vào declared parameter types.

### 14.5. Spring Boot khác Spring Framework thuần ở auto-configuration

Trong ví dụ Maven Spring Framework thuần, `@EnableAspectJAutoProxy` được khai báo trực tiếp. Spring Boot có thể bật auto-proxy thông qua starter/auto-configuration phù hợp và có cấu hình loại proxy riêng. Vì vậy khi chép expression sang một ứng dụng Boot, hãy xác minh bean, proxy type và AOP config thực tế, không suy luận mọi context giống nhau.

## 15. Lỗi phổ biến và cách sửa

| Triệu chứng | Lý do thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Cả `lookup(String)` và `lookup(long)` bị advice dù chỉ muốn một overload | Dùng `lookup(..)` hoặc `lookup(*)` quá rộng | Dùng declared parameter type `java.lang.String` hoặc `long` |
| Overload có hai tham số không được advice | Dùng `(*)` | Dùng `(..)` hoặc `(java.lang.String,int)` |
| Biểu thức `lookup(java.lang.Long)` không match `lookup(long)` | Khác primitive/wrapper | Sửa về `long` |
| Aspect không thấy method ở interface con | Type pattern quá hẹp hoặc method không nằm trong proxy interface | Kiểm tra subtype `+`, concrete bean và interfaces được proxy |
| Method có argument UrgentPayload nhưng log overload Payload | Overload chọn theo compile-time type của biến | Đọc method thực sự được Java chọn; phân biệt execution và args |
| Biểu thức theo package không bao phủ subpackage | Nhầm `.*` với `..*` | Sửa declaring type pattern đúng |
| Advice áp dụng quá nhiều method | Pattern tên `*` hoặc `(..)` quá rộng | Thu hẹp method name, type hoặc danh sách parameter |
| `@Aspect` có rồi nhưng không thấy log | Aspect chưa là Spring bean hoặc AOP chưa bật | @Component/@Bean, component scan, @EnableAspectJAutoProxy |
| Advice không chạy khi `this.listAll()` | Self-invocation bỏ qua proxy | Tách lời gọi sang Spring bean khác hoặc gọi qua dependency |
| CGLIB không chặn private/final | Không thể override | Thiết kế entry method interceptable |
| Bean là proxy nhưng advice mong muốn không chạy | Proxy có thể do advisor khác, pointcut không match | Xem signature và quan sát advice cụ thể |
| Advice xuất hiện hai lần | Hai advisor cùng match hoặc gọi method qua proxy hai lần | Kiểm tra các pointcut giao nhau và đường gọi thực tế |
| Dùng `call(...)` và lỗi parse | Spring AOP không hỗ trợ call join point | Dùng execution, hiểu proxy boundary |
| Chọn overloaded method theo tên variable trong Java | Variable name không thuộc method parameter type signature | Lọc theo type/số lượng, không theo tên biến |

## 16. Quy trình debug theo ba lớp: chữ ký, proxy, invocation

**Bước 1 — Viết chữ ký thật ra giấy.** Ví dụ method `String lookup(String,int)` có return String, name lookup, hai tham số lần lượt String và int. Một expression như `lookup(*)` chắc chắn không match vì chỉ đúng một tham số.

**Bước 2 — Phân biệt class/interface và subtype.** Xem bean thực sự triển khai interface nào, liệu method chỉ xuất hiện trên interface con hay có mặt ở interface cha, và có cần `+` để thể hiện phạm vi intended hierarchy không.

**Bước 3 — Kiểm tra bean lấy từ Spring context.** Dùng `AopUtils.isAopProxy(bean)` trong một integration test, đồng thời nhớ rằng kết quả true không chứng minh một advice cụ thể đã match.

**Bước 4 — Gọi từng overload riêng từ bên ngoài proxy.** In log signature trong advice và target. Với code ở mục 9, từng overload lookup có advice riêng, giúp xác định match trực tiếp.

**Bước 5 — Thử cả compile-time parent reference.** Gán `Payload declaredParent = new UrgentPayload(...)`, gọi `update(declaredParent)`; kiểm tra overload thật là `update(Payload)`.

**Bước 6 — Thử một method không thuộc pointcut.** Ví dụ `inspect()` không có advice, dù nó gọi `this.listAll()`. Điều này cho thấy điều kiện match và đường đi invocation là hai chuyện.

**Bước 7 — Khi có nhiều advice, xem thứ tự và sự giao nhau.** Không phụ thuộc thứ tự khai báo các method @Before trong cùng class để suy ra thứ tự log. Nếu cần thứ tự xác định, thiết kế và cấu hình advisor/aspect order rõ ràng.

## 17. Bài tập tự thực hành

**Bài 1 — Thay tên list bằng wildcard hậu tố.** Thêm method `getStatus()` và `updateStatus()` vào interface/service rồi thử:

~~~text
execution(* demo.TaskApi+.*Status(..))
~~~

Dự đoán hai method trên match, còn `listAll()` không match.

**Bài 2 — Giới hạn đúng một parameter cho list.** Thay expression `list*(..)` bằng:

~~~text
execution(* demo.TaskApi+.list*(*))
~~~

Chạy lại: `listByOwner(String)` được advice; `listAll()` không được advice.

**Bài 3 — Dùng lookup(..) để bao phủ overload.** Thay ba advice lookup bằng một advice:

~~~java
@Before("execution(* demo.TaskApi+.lookup(..))")
public void beforeAnyLookup(JoinPoint jp) {
    System.out.println("AOP lookup " + jp.getSignature().toShortString());
}
~~~

Đây là **fragment thay thế**, không thêm cạnh ba advice lookup cũ nếu muốn giữ số log của bài. Mọi overload lookup đều có thể được chọn.

**Bài 4 — Chỉ chọn update(UrgentPayload).** Thay `update(demo.Payload+)` bằng:

~~~text
execution(* demo.TaskApi+.update(demo.UrgentPayload))
~~~

Dự đoán chỉ invocation tới overload `update(UrgentPayload)` được advice. Việc đưa một UrgentPayload object vào biến có declared type Payload **không** tự khiến Java đổi overload.

**Bài 5 — Thêm argument runtime.** Dùng điều kiện `args(demo.UrgentPayload)` cùng execution update, rồi gọi overload `update(Payload)` bằng runtime UrgentPayload. Xem sự khác biệt giữa type được truyền và chữ ký được chọn.

**Bài 6 — Tạo thêm Spring bean khác implement TaskApi.** So sánh pointcut theo type `TaskApi+` với điều kiện `bean(taskService)`. Nếu có nhiều bean cùng interface, phải chọn bean rõ ràng khi injection; tránh để `NoUniqueBeanDefinitionException` gây nhiễu thí nghiệm pointcut.

## 18. Checklist thiết kế pointcut theo signature

- Đã xác định chính xác mục tiêu là **tên**, **hierarchy**, **overload**, hay **runtime argument**?
- Pattern type có cần ký hiệu subtype **`+`** không?
- Pattern method name có đang quá rộng (`*`) hoặc quá hẹp không?
- Dùng `()`, `(*)` và `(..)` đúng số lượng tham số chưa?
- Declared parameter types có đúng **primitive/wrapper** và đúng thứ tự không?
- Với overload, đã phân biệt **compile-time overload resolution** với runtime object type chưa?
- Java interface/class của bean có được proxy expose đúng các methods cần thiết không?
- Service và aspect có nằm trong **Spring ApplicationContext** được cấu hình AOP không?
- Lời gọi test có đi qua proxy thay vì `this.method()` hoặc object tạo bằng `new` không?
- Có test ít nhất một method **match**, một method **không match** và một overloaded method chưa?
- Nếu nhiều advisor giao nhau, có kiểm tra hành vi advice và thứ tự thực tế không?

## 19. Câu hỏi tự đánh giá

**1. `list*(..)` khác `list*()` ra sao?**

Biểu thức đầu bao gồm những method tên bắt đầu list với mọi số lượng tham số; biểu thức sau chỉ chọn những method bắt đầu list có **không tham số**.

**2. Dấu `+` trong `TaskApi+` nghĩa là cộng thêm một method phải không?**

Không. Nó thuộc type pattern, nghĩa là type được chỉ định cùng các subtype/implementation phù hợp.

**3. `lookup(*)` có chọn được `lookup(String,int)` không?**

Không. `(*)` yêu cầu đúng một parameter, trong khi `lookup(String,int)` có hai.

**4. `lookup(String,..)` có chọn `lookup(String)` và `lookup(String,int)` không?**

Có, vì yêu cầu một String ở đầu và phần còn lại có thể có 0 hoặc nhiều parameter.

**5. Hai overload `update(Payload)` và `update(UrgentPayload)` có đều khớp `Payload+` không?**

Có, nếu Payload là superclass của UrgentPayload và expression chỉ định type pattern đó ở parameter position.

**6. Nếu `Payload p = new UrgentPayload()`, Java chọn overload nào khi gọi update(p)?**

Overload `update(Payload)` dựa vào compile-time type của biến p, dù object runtime là UrgentPayload.

**7. `args(UrgentPayload)` có đồng nghĩa overload `update(UrgentPayload)` không?**

Không. `args` xét runtime argument type, còn `execution` xét declared method signature.

**8. Vì sao Spring AOP không chặn `this.listAll()` dù method match wildcard?**

Lời gọi nội bộ `this` bỏ qua AOP proxy; signature match không đủ để advice chạy.

**9. Type pattern `demo.service.*` khác `demo.service..*` thế nào?**

Dạng đầu nói tới type trong package trực tiếp; dạng hai mở rộng cả các subpackage.

**10. Nên chọn kiểu nào nếu mục tiêu là mọi overload có tên lookup?**

Dùng `execution(* demo.TaskApi+.lookup(..))` cùng các điều kiện type/bean cần thiết.

## 20. Tài liệu chính thức

- Spring Framework — **Declaring a Pointcut**: https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — **Declaring Advice**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Eclipse AspectJ — **Pointcut Semantics, Type/Subtype Patterns** (tham chiếu cú pháp được Spring sử dụng): https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html

**Kết luận:** Khi chọn method bằng Spring AOP, phải đọc **tên method**, **type hierarchy** (bao gồm `+` nếu cần), **overload** và **parameter pattern** như những ràng buộc riêng biệt. Một pointcut đúng về signature vẫn chỉ kích hoạt advice khi Spring quản lý bean, tạo proxy thích hợp và lời gọi thực sự đi qua proxy.
