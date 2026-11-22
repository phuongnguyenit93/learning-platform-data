# Những pointcut designator của AspectJ không được Spring AOP hỗ trợ

## 1. Vấn đề: dùng đúng cú pháp AspectJ chưa chắc chạy trong Spring AOP

Spring Framework hỗ trợ khai báo aspect bằng annotation `@Aspect`, `@Pointcut`, `@Before`, `@Around` và sử dụng cú pháp biểu thức pointcut bắt nguồn từ AspectJ. Tuy nhiên, **Spring AOP không triển khai toàn bộ ngôn ngữ pointcut của AspectJ**. Hạ tầng proxy của Spring chỉ cung cấp các **method execution join point trên Spring-managed beans**, không quan sát mọi kiểu sự kiện như lời gọi method ở mọi vị trí bytecode, truy cập field hay khởi tạo constructor.

Vì vậy biểu thức:

~~~java
@Before("execution(* demo.OrderService.submit(..))")
public void beforeSubmit() {
    // Spring AOP có thể sử dụng.
}
~~~

có thể hợp lệ, trong khi biểu thức:

~~~java
@Before("call(* demo.OrderService.submit(..))")
public void beforeCall() {
    // Spring AOP không hỗ trợ call(...) designator.
}
~~~

**không hợp lệ đối với pointcut parser mà Spring AOP sử dụng**. Khi một pointcut expression chứa designator không được Spring AOP hỗ trợ và framework cố phân tích/chuẩn bị pointcut, nó ném `IllegalArgumentException`. Đây thường là **lỗi cấu hình/chạy khởi tạo application context**, không phải đơn giản là “advice không match nên bị bỏ qua”.

Hai đoạn trên chỉ minh họa method advice bên trong lớp `@Aspect`; chúng không phải hai tệp Java độc lập và không nên cùng đặt trong ứng dụng chạy bình thường. Bài này tập trung vào tập designator hợp lệ và không hợp lệ **trong Spring AOP**, phương án thay thế dùng Spring-managed bean, cách tái hiện lỗi và cách chẩn đoán. Không mở rộng sang hướng dẫn sử dụng toàn bộ AspectJ weaving.

## 2. Vì sao Spring AOP giới hạn method execution?

Spring AOP vận hành theo mô hình **proxy**. Spring bean được auto-proxy creator xét sau khi container tạo bean; nếu có advisor phù hợp, caller nhận một JDK dynamic proxy hoặc class-based proxy. Khi caller gọi một method **qua proxy**, interceptor chain xử lý advice rồi chuyển tiếp tới target.

~~~text
Caller
   |
   | gọi bean do Spring cung cấp
   v
Spring AOP proxy
   |
   | method invocation / advisor matching
   v
@Before / @Around / ... advice
   |
   v
Target bean.method(...)
~~~

Những hoạt động mà lời gọi đi qua proxy *không trực tiếp cung cấp* thành join point gồm:

- Chỉ dẫn tại **vị trí gọi** method trong code của một caller cụ thể, khác với sự kiện method target đang được thực thi.
- Đọc/ghi **field** của object (`get`/`set` theo nghĩa field join point, không phải method có tên `getX`/`setX`).
- Constructor initialization và static initialization.
- Phân tích bao quanh một join point theo control flow của toàn call stack bằng chính designator `cflow`/`cflowbelow`.
- Các designator cần mức thông tin bytecode/lexical context mà proxy Spring AOP không biểu diễn.

Do đó, biểu thức `execution(...)` mới là designator chủ yếu trong Spring AOP. Spring vẫn cho phép ràng buộc kiểu, annotation, argument và bean name **trên method execution đã có thể được proxy**.

Một phân biệt cần ghi nhớ: **`call(...)` và `execution(...)` không cùng nghĩa**. `call` mô tả *nơi code phát ra lời gọi*, còn `execution` mô tả *sự kiện thực thi method*. Trong Spring AOP, lời gọi từ bên ngoài tới một Spring proxy có thể kích hoạt advice trên **execution join point**; Spring không hỗ trợ trực tiếp chọn những call site bằng `call(...)`.

## 3. Danh sách designator Spring AOP hỗ trợ

Theo tài liệu chính thức của Spring Framework 6.2, Spring AOP chấp nhận **chín** AspectJ pointcut designators sau:

| Designator | Ý nghĩa khi sử dụng trong Spring AOP | Ví dụ biểu thức |
| --- | --- | --- |
| `execution` | Chọn method execution theo method signature | `execution(public * demo.OrderService.*(..))` |
| `within` | Thu hẹp phạm vi theo kiểu khai báo method | `within(demo..service..*)` |
| `this` | Kiểm tra **proxy reference** là instance của kiểu được chỉ định | `this(demo.OrderOperations)` |
| `target` | Kiểm tra **target object** sau proxy là instance của kiểu đó | `target(demo.OrderService)` |
| `args` | Chọn theo loại runtime của các argument được truyền | `args(java.lang.String)` |
| `@target` | Kiểm tra annotation trên loại runtime của target object | `@target(demo.AuditedType)` |
| `@args` | Kiểm tra annotation trên loại runtime của argument object | `@args(demo.ValidatedPayload)` |
| `@within` | Thu hẹp method execution trong các kiểu mang annotation | `@within(demo.AuditedType)` |
| `@annotation` | Chọn method có annotation tương ứng | `@annotation(demo.AuditedOperation)` |

Các ví dụ chứa `demo.OrderOperations`, `demo.AuditedType` và `demo.ValidatedPayload` chỉ nhằm minh họa syntax và cần những type/annotation tương ứng trong project khi dùng thật. Cần kiểm tra interface/proxy type với `this`, target implementation với `target`; hai thứ **khác nhau trong Spring AOP** do có object proxy nằm giữa caller và target.

Spring AOP còn bổ sung designator **đặc thù của Spring**:

~~~text
bean(orderService)
bean(*Service)
~~~

`bean(namePattern)` giới hạn theo **tên Spring bean** và có hỗ trợ wildcard `*`. Ví dụ:

~~~java
@Before("execution(* demo.OrderService.submit(..)) && bean(orderService)")
public void beforeOrderService() {
    // Áp dụng khi bean name và method execution đều khớp.
}
~~~

Đây là method advice minh họa trong `@Aspect`. `bean()` là extension của **Spring AOP**, không phải designator chuẩn để dùng trong native AspectJ weaving. Nó có ý nghĩa vì Spring container quản lý **bean name** và tạo proxy cho **instance cụ thể**.

Ký hiệu logic có thể kết hợp:

- `&&`: cả hai điều kiện phải khớp;
- `||`: ít nhất một điều kiện khớp;
- `!`: phủ định;
- dấu ngoặc đơn khi cần nhóm điều kiện.

Chỉ sử dụng operator không làm một PCD **không hỗ trợ** trở thành hợp lệ. Ví dụ `execution(...) && call(...)` vẫn chứa `call` và bị parser Spring AOP từ chối.

## 4. Danh sách 14 designator không được Spring AOP hỗ trợ

Tài liệu Spring Framework nêu **14** designator thuộc ngôn ngữ AspectJ đầy đủ nhưng **không được Spring AOP hỗ trợ** ở lớp pointcut expression:

| Designator | Mục đích trong ngôn ngữ AspectJ đầy đủ | Kết luận với Spring AOP |
| --- | --- | --- |
| `call` | Chọn điểm **gọi** method/constructor | Không được chấp nhận |
| `get` | Chọn join point **đọc field** | Không được chấp nhận |
| `set` | Chọn join point **ghi field** | Không được chấp nhận |
| `preinitialization` | Chọn giai đoạn trước khi constructor initialization | Không được chấp nhận |
| `staticinitialization` | Chọn static initialization của type | Không được chấp nhận |
| `initialization` | Chọn constructor initialization | Không được chấp nhận |
| `handler` | Chọn điểm xử lý exception handler | Không được chấp nhận |
| `adviceexecution` | Chọn khi một advice đang thực thi | Không được chấp nhận |
| `withincode` | Chọn join point theo phạm vi lexical bên trong code của method/constructor | Không được chấp nhận |
| `cflow` | Chọn join point nằm trong control flow của join point khác | Không được chấp nhận |
| `cflowbelow` | Chọn các join point *bên dưới* join point nguồn trong control flow | Không được chấp nhận |
| `if` | Điều kiện động đặc biệt trong biểu thức AspectJ | Không được chấp nhận |
| `@this` | Chọn theo annotation trên `this` trong ngữ nghĩa AspectJ | Không được chấp nhận |
| `@withincode` | Chọn theo annotation của vùng code chứa join point | Không được chấp nhận |

**Đối chiếu chính xác:** `this` được hỗ trợ, nhưng `@this` không; `within` được hỗ trợ, nhưng `withincode` không; `@within` được hỗ trợ, nhưng `@withincode` không. Các cặp này dễ nhầm khi sửa code từ native AspectJ sang Spring AOP.

Khi đưa một PCD không hỗ trợ vào biểu thức Spring AOP, Spring ném `IllegalArgumentException` trong quá trình pointcut được phân tích hoặc khởi tạo. **Không cần có bean hay method thực sự khớp** mới chứng minh được PCD đó không hợp lệ; lỗi đến từ bộ phân tích designator. Thời điểm lỗi được quan sát có thể khác nhau tùy cách khởi tạo pointcut và application context.

Danh sách ở đây dựa vào **Spring Framework 6.2**; khi nâng phiên bản, luôn đọc tài liệu của phiên bản đang chạy thay vì giả định tập designator cố định vĩnh viễn.

## 5. Các nhầm lẫn đặc biệt hay gặp

### 5.1. `call` khác `execution`

Hai pointcut:

~~~text
call(* demo.OrderService.submit(..))
execution(* demo.OrderService.submit(..))
~~~

không thể thay thế nhau tùy tiện về **ngữ nghĩa**. Ví dụ sau chọn method execution trên Spring bean, trong khi designator `call` thuộc nhóm không hỗ trợ. Nếu mục tiêu chỉ là log trước khi một Spring service method chạy, giải pháp Spring AOP tự nhiên là `execution(...)` (có thể kết hợp `within`, `@annotation` hoặc `bean()`).

Nếu mục tiêu thực sự là “chỉ advice khi method được gọi **từ một call site cụ thể**”, `execution` sẽ **không bảo đảm cùng phạm vi**. Spring AOP proxy không quan sát call site lexical ở mức `call`. Hãy thiết kế lại ranh giới service/adapter hoặc đánh giá kỹ cơ chế weaving riêng khi yêu cầu thật sự cần call-site join points.

### 5.2. `get`/`set` không tương đương Java getters/setters

Với Java class:

~~~java
public class AccountService {
    private int balance;

    public int getBalance() {
        return balance;
    }

    public void setBalance(int amount) {
        this.balance = amount;
    }
}
~~~

Điểm cần phân biệt:

- `get(int demo.AccountService.balance)` và `set(int demo.AccountService.balance)` là **field access** designators của AspectJ; không hoạt động trong Spring AOP.
- `execution(* demo.AccountService.getBalance())` hoặc `execution(* demo.AccountService.setBalance(..))` là **method execution** pointcut, Spring AOP có thể áp dụng nếu method được gọi qua Spring proxy.
- Thao tác trực tiếp `balance = amount` hoặc `int value = balance` bên trong target vẫn là field read/write. Spring AOP proxy không chặn field access chỉ vì các method khác của class đã được proxy.

Đoạn Java minh họa class có thể biên dịch độc lập, nhưng chỉ trở thành target của Spring AOP nếu được đăng ký như Spring bean và có advisor phù hợp.

### 5.3. Constructor/static initialization không phải method execution

~~~text
preinitialization(demo.OrderService.new(..))
initialization(demo.OrderService.new(..))
staticinitialization(demo.OrderService)
~~~

Ba biểu thức minh họa designator không hỗ trợ. Spring tạo bean qua constructor/factory và có thể post-process để trả proxy **sau giai đoạn tạo đối tượng**; proxy thông thường không chặn constructor execution hoặc static initializer thành join point advice.

Nếu cần hành vi khi Spring tạo bean, dùng cơ chế **lifecycle/extension point của container** đúng nhiệm vụ như `@PostConstruct`, init callback, `BeanPostProcessor` hoặc event ứng dụng; đừng ép một biểu thức `initialization(...)` vào `@Before` rồi mong Spring AOP hiểu.

Một điều quan trọng: `@PostConstruct` là lifecycle callback, **không phải** cách làm cho Spring AOP bắt mọi lần khởi tạo object. Khi một method được gọi ngay từ constructor/init của target, lời gọi thường cũng **chưa đi qua Spring proxy cuối cùng**.

### 5.4. `handler` không phải lời khuyên để advice exception

`handler(...)` dùng để chọn exception handler join point trong ngôn ngữ AspectJ đầy đủ; Spring AOP không hỗ trợ. Nếu mục tiêu là quan sát **exception được ném từ method execution của Spring bean**, dùng advice `@AfterThrowing`:

~~~java
@AfterThrowing(
    pointcut = "execution(* demo.OrderService.submit(..))",
    throwing = "ex"
)
public void whenSubmitFails(IllegalStateException ex) {
    System.out.println("EXCEPTION: " + ex.getMessage());
}
~~~

Đoạn trên là **method advice minh họa**, cần nằm trong Spring bean `@Aspect` với import `org.aspectj.lang.annotation.AfterThrowing`. Nó chạy khi method execution được advice ném ngoại lệ phù hợp và lời gọi qua proxy. Nó **không** tương đương bắt đầu execution của mọi `catch` block, cũng không quan sát exception đã được target tự catch/nuốt bên trong.

### 5.5. `cflow`/`cflowbelow`: phân biệt PCD với Spring Pointcut API

~~~text
cflow(execution(* demo.Controller.handle(..)))
cflowbelow(execution(* demo.Controller.handle(..)))
~~~

Các chuỗi trên không phải Spring AOP expressions hợp lệ. Spring AOP không nhận AspectJ PCD `cflow` hoặc `cflowbelow`.

**Ngoại lệ dễ bị hiểu sai:** Spring còn cung cấp `org.springframework.aop.support.ControlFlowPointcut` trong **Pointcut API programmatic**. Nó là một Spring API có thể chọn method execution theo thông tin call stack (kém mạnh hơn semantics của `cflow` AspectJ). Việc tồn tại **class `ControlFlowPointcut` không làm designator `cflow(...)` được phép dùng trong `@Pointcut`**. Đây là hai giao diện/cơ chế khác nhau.

Nếu mục tiêu là lấy một request-scoped context hoặc correlation ID khi method Spring service được gọi, cân nhắc truyền context rõ ràng hoặc dùng tầng phù hợp như filter/interceptor/request context, thay vì cố chuyển toàn bộ AspectJ call flow expression vào Spring AOP.

### 5.6. `withincode` và `within` không giống nhau

- `within(demo..service..*)` **được hỗ trợ**: giới hạn method execution theo **type scope**.
- `withincode(* demo.Controller.handle(..))` **không được hỗ trợ**: cần match join point theo phần code lexical nằm **bên trong** method.
- `@within(demo.AuditedType)` **được hỗ trợ**: type mang annotation tương ứng.
- `@withincode(demo.AuditedAction)` **không được hỗ trợ**: annotation trên code chứa join point.

Khi cần giới hạn pointcut theo **service layer**, dùng `execution(* demo..service..*.*(..))` hoặc `within(...)` kết hợp `execution(...)`. Nếu chỉ muốn khi một caller cụ thể gọi, cách khớp theo type/method execution không cung cấp đúng mô hình call-site của `withincode`.

### 5.7. `this`/`@this` và `target`/`@target`

Với Spring AOP proxy, `this(Type)` xét **proxy object**, còn `target(Type)` xét **target object**. Ngữ nghĩa này đặc biệt quan trọng khi JDK dynamic proxy chỉ implements interface, không phải subclass của implementation.

~~~text
this(demo.OrderOperations)      // Spring AOP hỗ trợ
target(demo.OrderService)       // Spring AOP hỗ trợ
@target(demo.AuditedType)       // Spring AOP hỗ trợ
@this(demo.AuditedType)         // Spring AOP không hỗ trợ
~~~

Dấu `@` tạo ra designator khác; đừng sửa `@this` thành `this` nếu mục tiêu ban đầu của bạn là match theo **annotation**. Hãy quyết định cần kiểm tra type hay annotation của target, rồi chọn `target` hoặc `@target` phù hợp.

## 6. Project Java 17+ minh họa pointcut hợp lệ và lỗi không hỗ trợ

Ví dụ sử dụng **Spring Framework 6.2.0**, **AspectJ Weaver 1.9.22**, Maven và JDK 17+. Ta tạo service Spring bean có một advice hợp lệ, rồi **tự kiểm tra một pointcut `call` không hợp lệ bằng API Spring** mà không làm application context thất bại lúc startup.

Cấu trúc:

~~~text
spring-aop-pcd-check/
├── pom.xml
└── src/main/java/demo/
    ├── Demo.java
    ├── OrderService.java
    └── TraceAspect.java
~~~

### 6.1. Cấu hình Maven

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-pcd-check</artifactId>
    <version>1.0-SNAPSHOT</version>

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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
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
                    <mainClass>demo.Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp Java configuration và container, `spring-aop` chứa proxy/pointcut API, `aspectjweaver` giúp Spring phân tích cú pháp kiểu `@AspectJ`. Dependency này **không tự kích hoạt AspectJ bytecode weaving**.

### 6.2. Business service

Tạo `src/main/java/demo/OrderService.java`:

~~~java
package demo;

public class OrderService {
    public void submit(String orderId) {
        System.out.println("SERVICE: submit " + orderId);
    }
}
~~~

Class này không `final`, method `submit` là `public`; Spring có thể bọc bằng class-based proxy để can thiệp vào method execution.

### 6.3. Aspect có expression được hỗ trợ

Tạo `src/main/java/demo/TraceAspect.java`:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(* demo.OrderService.submit(..))"
          + " && within(demo.OrderService)")
    public void beforeSubmit() {
        System.out.println("ADVICE: before submit");
    }
}
~~~

Cả `execution` và `within` đều nằm trong tập Spring AOP hỗ trợ. Điều kiện `within(demo.OrderService)` còn minh họa cách ràng buộc type scope hợp lệ. Hai điều kiện khớp cùng method trong ví dụ; method không bị chặn hai lần chỉ vì biểu thức có hai designators.

### 6.4. Kiểm tra proxy rồi bắt lỗi parser đối với call(...)

Tạo `src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Demo {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Demo.class)) {
            OrderService service = context.getBean(OrderService.class);
            boolean proxied = AopUtils.isAopProxy(service);

            System.out.println("PROXY: " + proxied);
            service.submit("A-01");

            AspectJExpressionPointcut unsupported =
                    new AspectJExpressionPointcut();
            unsupported.setExpression(
                    "call(* demo.OrderService.submit(..))");

            boolean rejected = false;
            try {
                unsupported.getClassFilter().matches(OrderService.class);
            } catch (IllegalArgumentException ex) {
                rejected = true;
                System.out.println("UNSUPPORTED_CALL: rejected");
            }

            if (!proxied || !rejected) {
                throw new IllegalStateException(
                        "Spring AOP pointcut check failed");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Cơ chế trong đoạn này:

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` cho phép Spring tạo class proxy cho bean `OrderService`. `@Bean traceAspect()` đăng ký aspect với advisor hợp lệ. Chỉ `@Aspect` mà không đăng ký làm bean sẽ không đủ.
2. `service.submit("A-01")` đi qua proxy nên `@Before` chạy trước target method.
3. `new AspectJExpressionPointcut()` là API Spring AOP để diễn giải một AspectJ pointcut expression. Ta **cố tình** đặt biểu thức chứa `call(...)` không hỗ trợ. Object pointcut này **không được đăng ký làm advisor trong context**, để không gây lỗi khởi động Spring application.
4. `getClassFilter().matches(OrderService.class)` buộc pointcut thực hiện bước phân tích/đánh giá điều kiện type; parser Spring AOP từ chối `call` và ném `IllegalArgumentException`.
5. `catch` chỉ in một marker ổn định, không in exception message vốn có thể thay đổi theo phiên bản parser. Biến `rejected` buộc ứng dụng phải chứng minh đã nhận lỗi mới in `CHECK: PASS`.

### 6.5. Lệnh chạy và output

Trong thư mục `spring-aop-pcd-check`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do mã ví dụ chủ động in ra:

~~~text
PROXY: true
ADVICE: before submit
SERVICE: submit A-01
UNSUPPORTED_CALL: rejected
CHECK: PASS
~~~

Thông báo từ Maven/framework có thể xuất hiện ngoài năm dòng trên. Hai kết quả cần phân biệt:

- `PROXY: true` và `ADVICE: before submit` xác nhận biểu thức `execution && within` **được Spring AOP chấp nhận và advice chạy qua proxy**.
- `UNSUPPORTED_CALL: rejected` chứng minh `call(...)` bị Spring AOP pointcut parser từ chối; không phải do `OrderService` thiếu method hoặc do advisor không khớp.

Đây là ví dụ tái hiện có kiểm soát và kiểm tra điểm cốt lõi của bài học: **pointcut syntax hợp lệ đối với native AspectJ chưa chắc hợp lệ đối với Spring AOP**.

## 7. Nếu viết sai designator trực tiếp trong @Aspect thì sao?

Nếu bạn sửa advice của `TraceAspect` thành:

~~~java
@Aspect
public class TraceAspect {
    @Before("call(* demo.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("ADVICE: before submit");
    }
}
~~~

đây là **đoạn thay thế minh họa cho class aspect**, không phải phương án chạy bình thường. Khi Spring chuẩn bị advisor/pointcut cho aspect và nhận thấy designator `call` không hỗ trợ, việc tạo bean/context hoặc khởi tạo AOP advisor sẽ thất bại với `IllegalArgumentException` trong chuỗi nguyên nhân (đôi khi được bọc trong exception tạo bean của Spring). Không có chuyện Spring âm thầm đổi `call` thành `execution`.

Với `@Pointcut` đặt tên cũng tương tự:

~~~java
@Pointcut("cflow(execution(* demo.OrderService.submit(..)))")
public void underSubmitFlow() {
}
~~~

Spring AOP không hỗ trợ `cflow` trong biểu thức pointcut, kể cả khi expression bên trong `execution(...)` được hỗ trợ. `@Pointcut` chỉ đặt tên/ghép biểu thức, không thêm khả năng nhận diện join point mới vào Spring proxy. Đây là snippet minh họa đặt trong `@Aspect`, không thêm vào project chuẩn ở phần 6.

Nếu muốn kiểm tra các designators không hỗ trợ khác bằng API `AspectJExpressionPointcut`, chỉ thay `setExpression(...)` trong demo rồi giữ cơ chế bắt `IllegalArgumentException`. Một số expression có thêm vấn đề cú pháp/kiểu tham số; hãy dùng ví dụ theo tài liệu và xem root cause thật khi debug. Đừng coi mọi parser error đều có cùng thông điệp.

## 8. Chuyển thiết kế pointcut sang khả năng Spring AOP

Không phải mọi nhu cầu có từ khóa AspectJ đều chuyển nguyên xi bằng cách thay tên designator. Bảng dưới đây phân biệt **mục đích của người viết** và **giải pháp Spring**:

| Nhu cầu ban đầu | Designator không hỗ trợ | Cách tiếp cận trong Spring AOP |
| --- | --- | --- |
| Log trước khi service method chạy | `call` | Advice `execution(...)` trên Spring bean, có thể kết hợp `bean(name)`/`within(...)` |
| Ghi log các lần setter method được gọi | `set` nếu đang nói về field assignment | `execution(* set*(..))` chọn **setter method**, không bắt các lần gán field trực tiếp |
| Quan sát getter method qua proxy | `get` nếu đang nói về field read | `execution(* get*(..))` chọn **getter method**, không bắt field read |
| Làm gì đó ngay khi Spring bean hoàn thành init | `initialization`, `preinitialization` | Lifecycle callback Spring hoặc `BeanPostProcessor`, không gọi đó là AspectJ join point |
| Cấu hình khi class được load/static initialize | `staticinitialization` | Đặt cấu hình khởi tạo ở application startup/lifecycle phù hợp; không mong AOP proxy intercept static initializer |
| Ghi nhận exception method trả ra | `handler` | `@AfterThrowing` trên Spring method execution; không bắt mọi catch handler |
| Chọn method theo layer | `withincode` | `execution(...)`/`within(...)` hoặc `bean(...)` để giới hạn target layer; không khớp theo source call site |
| Dựa trên call stack của caller | `cflow`, `cflowbelow` | Xem nhu cầu context propagation/adapter rõ ràng; nếu dùng Spring Pointcut API, `ControlFlowPointcut` là cơ chế khác và có hạn chế riêng |
| Chọn method theo annotation trên proxy this | `@this` | Xem `@target`, `@within`, `@annotation` theo đúng mục tiêu; không coi chúng là thay thế tương đương từng byte |
| Chọn vùng code mang annotation | `@withincode` | Đánh dấu method được advice bằng `@annotation` hoặc class bằng `@within`/`@target` rồi chặn qua proxy |
| Điều kiện runtime tùy biến trong pointcut | `if` | Chuyển điều kiện sang code advice `@Around`/`@Before` hoặc cơ chế chọn method phù hợp của Spring; không giả định cùng semantics |
| Chọn execution của advice khác | `adviceexecution` | Xem instrumentation/observability hạ tầng phù hợp thay vì advice lên chính AOP internals |

**Lưu ý:** bảng là gợi ý **thiết kế lại** theo Spring AOP, không khẳng định `execution(get*(..))` tương đương field `get`, hay `@AfterThrowing` tương đương exception `handler`. Nếu yêu cầu đích thực cần call-site, field-access, constructor hay lexical join points thì giới hạn proxy của Spring AOP không đủ; cần **đánh giá một cơ chế khác có chi phí/đặc tính riêng**. Nội dung bài không triển khai cơ chế ngoài Spring AOP.

## 9. Tình huống điển hình trong ứng dụng Spring

### 9.1. Chỉ log các method có @Audited

Thay vì mong `@withincode` kiểm tra annotation ở nơi gọi, hãy đánh dấu đúng **method cần advice**:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Audited {
}
~~~

và bên trong một bean aspect:

~~~java
@Before("@annotation(demo.Audited)")
public void beforeAudited() {
    System.out.println("AUDIT");
}
~~~

Đây là hai snippet minh họa; cần import `java.lang.annotation.Retention`, `RetentionPolicy`, `Target`, `ElementType` cho annotation, và `@Aspect`/`@Before`/đăng ký bean cho advice. Chúng không phải project chạy độc lập. `@annotation` chỉ chọn **method mang annotation** khi method execution đi qua Spring proxy.

### 9.2. Phạm vi theo tên bean

Nếu các service có tên `orderService`, `paymentService`, dùng:

~~~java
@Before("execution(public * demo..service..*.*(..)) && bean(*Service)")
public void beforeBusinessCall() {
    // ...
}
~~~

Biểu thức này chỉ mang tính ví dụ: cú pháp package trong `execution` phải trùng package thực của project và bean name phải match suffix `Service`. `bean(*Service)` là extension đặc thù Spring, thích hợp khi Spring-managed bean name là một phần của convention. Nó không áp dụng cho object được tạo ngoài container.

### 9.3. Giới hạn theo loại proxy

Với JDK dynamic proxy, `this(demo.OrderOperations)` có thể match proxy theo interface; `target(demo.OrderService)` match target implementation. Với CGLIB proxy, proxy cũng có thể là subclass của target. Tránh nhầm `@this` (không hỗ trợ) với `this` (hỗ trợ) và tránh cast JDK proxy thành implementation class.

### 9.4. Lời gọi nội bộ không được chặn

~~~java
public class OrderService {
    public void batch() {
        this.submit("A-02");
    }

    public void submit(String orderId) {
        System.out.println("SERVICE: submit " + orderId);
    }
}
~~~

Cho dù `execution(* demo.OrderService.submit(..))` là pointcut hợp lệ, lời gọi `this.submit()` trong target **không quay lại qua Spring AOP proxy**. Đây không phải vì designator `execution` không được hỗ trợ, mà là vì cách caller đi qua ranh giới proxy. Cách sửa nên ở kiến trúc gọi qua một Spring-managed collaborator khác, không thêm `call` vào pointcut.

## 10. Phân biệt lỗi parser với lỗi pointcut không match

Khi startup hoặc lời gọi method không đúng mong đợi, có ba lớp lỗi khác nhau:

### A. Designator không hỗ trợ

Dấu hiệu:

- Pointcut có `call`, `set`, `get`, `cflow` hoặc một trong 14 PCD không hỗ trợ;
- `IllegalArgumentException` xuất hiện trong quá trình Spring chuẩn bị/phân tích expression;
- Ứng dụng có thể không khởi tạo được aspect/auto-proxy creator hoặc context.

Cách xử lý: tìm **root cause**, xác định designator không hỗ trợ và chuyển về một thiết kế phù hợp Spring AOP; đừng chỉ nới wildcard hoặc sửa method name.

### B. Designator được hỗ trợ nhưng biểu thức sai hoặc method không match

Dấu hiệu:

- Có `execution(...)`/`@annotation(...)`/`within(...)` hợp lệ, nhưng package/class/method/annotation không khớp, hoặc expression sai cú pháp;
- Nếu sai syntax vẫn có thể ném exception từ parser; nếu cú pháp đúng nhưng không match, Spring có thể không tạo proxy cho bean đó;
- Không có dòng advice vì advisor không áp dụng.

Cách xử lý: kiểm tra package đầy đủ, interface/implementation, runtime annotation, type/bean name, cú pháp tham số `(..)` và nơi Spring đăng ký aspect.

### C. Advisor match nhưng lời gọi không đi qua proxy

Dấu hiệu:

- Bean có advisor/proxy, nhưng code gọi `this.submit()`, gọi raw target, method `final`/`private` hay object `new` ngoài Spring;
- Logic method vẫn chạy nhưng advice không chạy, không nhất thiết có parser exception;
- Proxy strategy JDK/CGLIB và scope Spring bean ảnh hưởng những method có thể intercept.

Cách xử lý: đo `AopUtils.isAopProxy(bean)` và gọi method **qua reference do Spring container cung cấp**; tránh kết luận từ việc pointcut trông đúng.

### Checklist chẩn đoán

1. Đọc **toàn bộ biểu thức pointcut** trong `@Pointcut`, `@Before`, XML hoặc API `AspectJExpressionPointcut`.
2. Đối chiếu designator với tập Spring AOP hỗ trợ: chín PCD chuẩn cộng `bean()` extension.
3. Nếu là một trong 14 PCD không hỗ trợ, sửa **thiết kế**; không sửa kiểu Java import để cố làm parser nhận.
4. Xem exception ở **root cause**, đặc biệt `IllegalArgumentException` từ pointcut parser.
5. Kiểm tra Spring bean, `@EnableAspectJAutoProxy` và việc `@Aspect` đã được đăng ký như Spring bean.
6. Kiểm tra loại proxy `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`; đối chiếu method có khả năng được intercept.
7. Gọi một method qua proxy rồi dùng marker hoặc counter trong advice để xác minh thực thi.
8. Với case cần call-site/field-access/constructor, ghi rõ giới hạn Spring AOP và chọn cơ chế phù hợp thay vì giả vờ có PCD tương đương.
9. Nếu ứng dụng còn Spring Boot AOP auto-configuration, transaction, cache hoặc nhiều context, đối chiếu **ApplicationContext và cấu hình runtime thực tế**.
10. Sau sửa, chạy integration test thực hiện external caller → Spring proxy → method; đừng chỉ dựa trên syntax highlight trong IDE.

## 11. Các câu hỏi tự kiểm tra

**1. Spring AOP có hỗ trợ `call(...)` vì dùng cú pháp @AspectJ không?**  
Không. Spring AOP hiểu **một tập con** PCD và chỉ chặn method execution trên Spring beans qua proxy.

**2. `execution(* set*(..))` có thay thế được `set(* ..*)` không?**  
Không tương đương. `execution(set*(..))` chỉ match **setter method execution**; `set(...)` của AspectJ chọn field write.

**3. Nếu dùng `execution(...) && cflow(...)`, Spring chỉ bỏ qua cflow rồi chạy execution chứ?**  
Không. `cflow` nằm trong nhóm PCD không hỗ trợ; biểu thức bị parser từ chối, không phải điều kiện bị bỏ qua.

**4. `within(...)` được hỗ trợ còn `withincode(...)` thì sao?**  
`within` được hỗ trợ để thu hẹp scope kiểu; `withincode` không được Spring AOP parser chấp nhận.

**5. `this(...)` và `@this(...)` có giống nhau không?**  
Không. Trong Spring AOP, `this` kiểm tra proxy type; `@this` là PCD không được hỗ trợ.

**6. Vì sao Spring hỗ trợ `bean(name)` nhưng native AspectJ weaving không?**  
Spring AOP có khái niệm **Spring bean name**/instance trong container; `bean` là extension của Spring, không phải PCD chuẩn của native AspectJ.

**7. Có `ControlFlowPointcut` thì `cflow(...)` trong @Pointcut đã hợp lệ chưa?**  
Chưa. `ControlFlowPointcut` thuộc Spring Pointcut API programmatic, không làm AspectJ designator `cflow` trở thành hợp lệ trong parser Spring AOP.

**8. Lỗi `IllegalArgumentException` do PCD không hỗ trợ có nghĩa Spring AOP không chạy trên project?**  
Không. Nó nói một biểu thức không nằm trong phần ngôn ngữ Spring AOP hỗ trợ. Ví dụ `execution && within` vẫn có thể chạy bình thường, như project ở phần 6.

**9. Khi một method có pointcut hợp lệ nhưng advice không chạy, nguyên nhân duy nhất có phải unsupported designator không?**  
Không. Kiểm tra cả advisor có match, bean có thuộc Spring context và lời gọi có đi qua proxy hay không.

**10. Nếu cần intercept việc đọc field của mọi object, chỉ đổi JDK proxy sang CGLIB là đủ?**  
Không. Cả hai vẫn là **proxy Spring AOP cho method execution**. Chuyển loại proxy không biến field read thành join point.

## 12. Tài liệu Spring Framework chính thức

- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): danh sách 9 PCD chuẩn được hỗ trợ, 14 PCD không được hỗ trợ, `bean` extension và lưu ý Spring AOP method execution.
- [Spring Framework 6.2 — @AspectJ support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring dùng syntax AspectJ nhưng runtime AOP vẫn dựa trên Spring proxy.
- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `@Before`/`@AfterThrowing`/`@Around` trên các execution join point hợp lệ.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxy, self-invocation, method restrictions.
- [Spring Framework 6.2 — Pointcut API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pointcuts.html): `AspectJExpressionPointcut` và Spring API `ControlFlowPointcut` (khác `cflow` PCD).
