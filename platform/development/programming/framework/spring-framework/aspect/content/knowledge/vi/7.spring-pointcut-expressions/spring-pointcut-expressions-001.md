# execution để chọn phương thức của bean theo chữ ký trong Spring AOP

## 1. Mục tiêu bài học

Trong **Spring AOP**, pointcut quyết định **method execution nào của Spring-managed bean** có thể kích hoạt advice. Trong các pointcut designator mà Spring hỗ trợ, **execution(...)** là lựa chọn phổ biến nhất khi cần chọn phương thức dựa vào **chữ ký (method signature)**: quyền truy cập, kiểu trả về, lớp/interface khai báo, tên và danh sách kiểu tham số.

Sau khi học, bạn có thể:

1. Đọc và tự viết **execution(...)** theo cấu trúc đầy đủ hoặc rút gọn.
2. Phân biệt ký tự đại diện **\*** với **..** khi dùng trong kiểu, tên method, package và danh sách tham số.
3. Viết pointcut chọn một method cụ thể, một nhóm tên method hoặc toàn bộ service package trong **Spring ApplicationContext**.
4. Giải thích vì sao **execution** dựa vào kiểu khai báo của tham số khác với **args(...)** dựa trên argument tại thời điểm chạy.
5. Sử dụng **@Pointcut** đặt tên biểu thức và tái dùng trong **@Before**.
6. Chạy dự án Java 17+ có ví dụ match và không match, kiểm tra thứ tự log, rồi chẩn đoán các giới hạn do Spring AOP proxy.

**Phạm vi:** Chỉ tập trung vào **Spring Framework @AspectJ-style Spring AOP**, không chuyển sang các khái niệm AspectJ weaving tổng quát. Ngay cả khi dùng cú pháp pointcut của AspectJ, Spring AOP trong bài vẫn hoạt động bằng **proxy** và chỉ xử lý **method execution join points trên Spring beans**.

## 2. execution(...) chọn điều gì?

Hình dung client gọi một Spring bean:

~~~text
Client
  |
  | gọi method trên bean được Spring inject
  v
Spring AOP proxy
  |
  +-- advisor xét biểu thức execution(...)
  |      |
  |      +-- method signature khớp  -> advice có thể chạy
  |      +-- không khớp             -> không chạy advice này
  |
  v
Target method thực thi
~~~

Biểu thức không trực tiếp thay đổi thân method. Nó là **bộ lọc các method executions** mà advice có thể áp dụng. Ví dụ:

~~~java
@Before("execution(* demo.OrderApi.create(..))")
public void beforeCreate() {
    System.out.println("Trước create");
}
~~~

Pointcut này biểu thị những method-execution join points được Spring AOP hỗ trợ và có signature khớp method **create** trên **demo.OrderApi**, bất kể kiểu trả về hoặc số lượng tham số. Nếu một lời gọi đến create đi qua proxy được Spring cấu hình với advisor tương ứng, advice có thể chạy trước target.

Các điều kiện cần phân biệt:

- **Biểu thức parse hợp lệ**: cú pháp execution được AspectJ pointcut parser của Spring hiểu.
- **Signature match**: chữ ký phương thức thỏa biểu thức.
- **Bean eligible**: bean là Spring-managed bean và được Spring AOP xem xét áp dụng advisor.
- **Invocation qua proxy**: caller đi qua đối tượng proxy ở điểm có thể intercept.
- **Advice chạy**: tất cả các điều kiện trên cùng thỏa, cộng với điều kiện runtime khác nếu pointcut được kết hợp với các designator động.

Một expression đúng vẫn có thể không tạo log nếu bean không thuộc ApplicationContext, advice chưa được đăng ký, hoặc method được gọi bằng **this.method()** bên trong target.

## 3. Cú pháp đầy đủ của execution

Dạng khái quát được tài liệu Spring trình bày như sau:

~~~text
execution(
    modifiers-pattern?
    ret-type-pattern
    declaring-type-pattern?name-pattern(param-pattern)
    throws-pattern?
)
~~~

Dấu **?** trong sơ đồ trên chỉ rằng thành phần **có thể bỏ qua**, **không phải ký tự bạn cần gõ** vào mọi pointcut.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **modifiers-pattern?** | Ràng buộc modifier của method, khi cần | public |
| **ret-type-pattern** | Kiểu trả về của method; **bắt buộc** | void, java.lang.String, * |
| **declaring-type-pattern?** | Class/interface hoặc pattern type sở hữu method | demo.OrderApi. |
| **name-pattern** | Tên method, có thể có wildcard | create, get*, * |
| **param-pattern** | Kiểu và số lượng tham số, **bắt buộc** dưới dạng ngoặc | (), (java.lang.String), (*), (..) |
| **throws-pattern?** | Ràng buộc kiểu ngoại lệ được khai báo trong throws clause | Chỉ dùng khi thật sự cần lọc checked-exception signature |

Trong mã thực tế, biểu thức thường được viết trên một dòng:

~~~java
execution(public java.lang.String demo.OrderApi.create(java.lang.String))
~~~

Đọc từ trái sang phải:

1. **public**: method phải công khai.
2. **java.lang.String**: kiểu trả về khai báo phải là String.
3. **demo.OrderApi.**: chọn method được mô tả qua type/interface OrderApi trong package demo.
4. **create**: tên chính xác.
5. **(java.lang.String)**: method có **đúng một tham số được khai báo kiểu String**.

Dấu chấm sau **demo.OrderApi** là dấu nối giữa **declaring type** và **method name**, không phải ký tự bất kỳ. Nếu không cần giới hạn method ở một type cụ thể, bạn có thể bỏ phần declaring type và chỉ dùng tên method.

Các thành phần được thiết kế để chọn method theo **khai báo**. Chúng không so sánh giá trị argument như mã đơn bằng "A-123"; trường hợp lọc theo giá trị runtime phải dùng cơ chế khác với điều kiện cụ thể và hiểu rõ hiệu ứng của proxy.

## 4. Hiểu chính xác dấu * và dấu ..

### 4.1. Dấu * trong kiểu trả về

~~~java
execution(* demo.OrderApi.create(..))
~~~

Dấu **\*** ở vị trí **ret-type-pattern** nghĩa là **bất kỳ kiểu trả về**, kể cả void. Nếu muốn chọn riêng method trả String:

~~~java
execution(java.lang.String demo.OrderApi.create(..))
~~~

Nếu muốn chọn riêng method trả void:

~~~java
execution(void demo.OrderApi.cancel(..))
~~~

Phần kiểu trả về phải phản ánh **return type được khai báo trong method signature**, không phải kiểu của object mà một nhánh code có thể trả về ở runtime. Ví dụ, một method khai báo trả **Object** nhưng return ra String không được chọn chỉ vì expression ghi **java.lang.String**.

### 4.2. Dấu * trong tên method

~~~java
execution(* demo.OrderApi.get*(..))
~~~

Chọn các method trên OrderApi có tên bắt đầu bằng **get**. Có thể dùng wildcard ở giữa/cuối tên để xây một naming pattern, chẳng hạn:

~~~java
execution(* demo.OrderApi.*Status(..))
~~~

Chọn method có tên kết thúc bằng **Status**.

Không nhầm wildcard của pointcut với toán tử nhân trong Java. Biểu thức nằm trong **chuỗi annotation** và được pointcut parser diễn giải.

### 4.3. Dấu .. trong danh sách tham số

Ba dạng phải nhớ:

~~~text
()   -> không có tham số
(*)  -> đúng một tham số, kiểu bất kỳ
(..) -> không, một hoặc nhiều tham số, với các kiểu bất kỳ
~~~

Ví dụ:

~~~java
execution(* demo.OrderApi.status())
execution(* demo.OrderApi.create(*))
execution(* demo.OrderApi.create(..))
~~~

Nếu method thực sự là **String create(String id)**:

- **create()** không match vì không có tham số.
- **create(*)** match vì có đúng một tham số.
- **create(..)** match vì chấp nhận mọi số tham số, bao gồm một.

Nếu muốn đúng một tham số String, dùng:

~~~java
execution(* demo.OrderApi.create(java.lang.String))
~~~

Nếu muốn hai tham số, tham số thứ nhất tùy kiểu, tham số thứ hai String:

~~~java
execution(* demo.OrderApi.someMethod(*,java.lang.String))
~~~

Đây là **mẫu cú pháp**, không khẳng định interface OrderApi của ví dụ ở mục 7 thực sự có method **someMethod**.

### 4.4. Dấu .. trong package/type pattern

~~~java
execution(* demo.service.*.*(..))
~~~

Chọn các method có chữ ký thuộc các type khớp pattern trong package **demo.service** trực tiếp, không tự mở rộng mọi subpackage.

~~~java
execution(* demo.service..*.*(..))
~~~

Cho phép chọn type trong **demo.service** và các subpackage bên dưới. Cần chú ý vị trí của **..**: ở đây nó nằm trong **declaring-type-pattern**, không phải danh sách tham số.

| Pattern | Đang mở rộng cái gì? |
| --- | --- |
| **demo.service.*.*(..)** | Type trực tiếp trong package demo.service và mọi tên method/số tham số |
| **demo.service..*.*(..)** | Type thuộc demo.service hoặc các subpackage và mọi method/số tham số |
| **demo.OrderApi.*(..)** | Mọi tên method trên type OrderApi, số tham số tùy ý |
| **demo.OrderApi.get*(..)** | Những method tên bắt đầu get |
| **demo.OrderApi.create(..)** | Method tên create, mọi số tham số |
| **demo.OrderApi.create()** | Method create **không** có tham số |

Đừng dùng **..** như wildcard toàn bộ string một cách mơ hồ. Trong **parameter pattern**, nó là **bất kỳ số lượng tham số**; trong **type pattern**, nó mô tả các mức package/type theo cú pháp AspectJ.

## 5. Tập hợp các biểu thức thường dùng với Spring beans

| Yêu cầu chọn method | Biểu thức |
| --- | --- |
| Mọi public method có thể intercept | **execution(public * *(..))** |
| Một method create có đúng một String argument | **execution(* demo.OrderApi.create(java.lang.String))** |
| Mọi overload của create, mọi kiểu trả về | **execution(* demo.OrderApi.create(..))** |
| Một method không có tham số | **execution(* demo.OrderApi.status())** |
| Method trả void, tên cancel, nhận long primitive | **execution(void demo.OrderApi.cancel(long))** |
| Mọi method của interface/type OrderApi | **execution(* demo.OrderApi.*(..))** |
| Method bắt đầu bằng find trên OrderApi | **execution(* demo.OrderApi.find*(..))** |
| Mọi public method của các service trong package cụ thể | **execution(public * demo.service.*.*(..))** |
| Mọi method trong package service và các subpackage | **execution(* demo.service..*.*(..))** |

Tất cả biểu thức trong bảng đều nói về **signature**, không phải việc Spring đã có bean nào. Nếu ứng dụng không đăng ký các service phù hợp, hoặc lời gọi bypass proxy, sẽ không có lời gọi AOP được xử lý.

**Lưu ý về primitive và wrapper**: tham số **long** trong chữ ký không giống tham số **java.lang.Long**. Nếu method định nghĩa **cancel(long id)**, hãy dùng **(long)** thay vì **(java.lang.Long)** khi muốn khớp chính xác declared parameter type. Autoboxing tại vị trí gọi Java không biến chữ ký phương thức thành Long.

## 6. Các ràng buộc riêng của Spring AOP

### 6.1. Chỉ chọn method execution trên Spring-managed beans

Spring AOP không thực hiện AspectJ compiler weaving. Nó không chặn **field access**, **constructor execution**, hoặc tùy ý mọi object tạo bằng **new**. Pointcut như:

~~~java
execution(* demo.OrderApi.*(..))
~~~

không có nghĩa mọi lời gọi Java tới object triển khai OrderApi đều bị aspect kiểm soát. Phải có bean được Spring quản lý và được expose qua proxy khi có advisor phù hợp.

### 6.2. JDK proxy và CGLIB proxy

**JDK dynamic proxy** hoạt động theo interface. Lời gọi public interface method có thể được Spring AOP intercept. Method chỉ có trên implementation nhưng không thuộc interface proxy không được expose qua JDK proxy đó.

**CGLIB class-based proxy** tạo subclass nên có thể intercept public method, và trong những điều kiện thích hợp cả protected hoặc package-visible method có thể override. Nhưng CGLIB không override **private** hay **final** method, cũng không tạo subclass cho final class.

Do đó:

~~~java
execution(public * demo.OrderApi.*(..))
~~~

là lựa chọn dễ kiểm soát cho giao diện service công khai. Nếu một expression bỏ modifier public, nó không tự vượt qua hạn chế kỹ thuật của proxy.

### 6.3. Self-invocation vẫn bỏ qua advice

Nếu **OrderServiceImpl.outer()** gọi **this.create(id)**, lời gọi nội bộ đó không đi qua proxy. Dù create khớp hoàn toàn chữ ký trong execution expression, Spring AOP không tự chạy thêm advice cho lần gọi nội bộ.

Cần phân biệt:

- **Signature match**: create phù hợp với biểu thức.
- **Proxy invocation**: caller gọi create thông qua Spring proxy.
- **Advice execution**: chỉ diễn ra khi có lời gọi phù hợp mà proxy có thể chặn.

### 6.4. Không dùng call(...) để thay thế

Trong **native AspectJ weaving**, có thể phân biệt execution và call join point. Nhưng **Spring AOP chỉ hỗ trợ method execution join points**, không hỗ trợ **call(...)** hoặc các pointcut designator chỉ có trong weaving. Dùng một pointcut designator không được Spring hỗ trợ có thể gây **IllegalArgumentException** khi Spring phân tích cấu hình.

Trong bài này nên tập trung vào **execution(...)**, thay vì tìm cách khắc phục self-invocation bằng một expression call(...).

## 7. Ví dụ Java 17+ chạy được: ba chữ ký match, một lời gọi nội bộ không match

Ví dụ dùng **Spring Framework 6.2.12**, **Java 17+**, **Maven 3.9+** và **aspectjweaver 1.9.24**, không cần Spring Boot. Chúng ta sẽ có một Spring service với bốn method:

- **create(String)** — advice chọn bằng chữ ký chính xác, có public + return String + parameter String.
- **cancel(long)** — advice chọn chính xác **public void** + **long**.
- **find(String)** — advice dùng wildcard **\*** cho kiểu trả về và **(..)** cho tham số.
- **outer(String)** — gọi **this.create(String)** từ bên trong target để đối chiếu giới hạn của proxy.

### 7.1. Cấu trúc dự án

~~~text
spring-aop-execution/
├── pom.xml
└── src/main/java/demo/
    ├── OrderApi.java
    ├── OrderServiceImpl.java
    ├── SignatureAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-execution</artifactId>
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

**spring-context** bao gồm hạ tầng container và kéo theo các module Spring AOP cần thiết. **aspectjweaver** cung cấp các kiểu và parser hỗ trợ AspectJ-style pointcut. Đây vẫn là **proxy-based Spring AOP**, không phải dự án thực hiện AspectJ weaving.

### 7.3. Service interface: chữ ký mà pointcut sẽ chọn

**src/main/java/demo/OrderApi.java**

~~~java
package demo;

public interface OrderApi {
    String create(String id);
    void cancel(long id);
    String find(String id);
    void outer(String id);
}
~~~

Toàn bộ method đều public theo quy tắc của Java interface. Đây là hợp đồng mà JDK proxy có thể công bố.

**create(String)**, **cancel(long)** và **find(String)** có chữ ký khác nhau về tên, return type và kiểu argument. Đối chiếu từng method với biểu thức tương ứng để thấy vì sao advice được chọn.

### 7.4. Implementation có một self-invocation

**src/main/java/demo/OrderServiceImpl.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderApi {

    @Override
    public String create(String id) {
        System.out.println("SERVICE create " + id);
        return "created:" + id;
    }

    @Override
    public void cancel(long id) {
        System.out.println("SERVICE cancel " + id);
    }

    @Override
    public String find(String id) {
        System.out.println("SERVICE find " + id);
        return id;
    }

    @Override
    public void outer(String id) {
        System.out.println("SERVICE outer " + id);
        this.create(id);
    }
}
~~~

**@Service** làm bean có thể được **@ComponentScan** đăng ký. Trong **outer**, lời gọi **this.create(id)** chạy trực tiếp trên target; nó không tự qua Spring AOP proxy.

### 7.5. Aspect dùng execution với ba signature pattern

**src/main/java/demo/SignatureAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class SignatureAspect {

    @Pointcut(
        "execution(public java.lang.String " +
        "demo.OrderApi.create(java.lang.String))"
    )
    public void exactCreate() {
    }

    @Before("exactCreate()")
    public void beforeCreate(JoinPoint jp) {
        System.out.println("ADVICE create " + jp.getArgs()[0]);
    }

    @Before("execution(public void demo.OrderApi.cancel(long))")
    public void beforeCancel(JoinPoint jp) {
        System.out.println("ADVICE cancel " + jp.getArgs()[0]);
    }

    @Before("execution(* demo.OrderApi.find(..))")
    public void beforeFind(JoinPoint jp) {
        System.out.println("ADVICE find " + jp.getArgs()[0]);
    }
}
~~~

Giải thích:

1. **exactCreate()** là một **named pointcut**. Tên method giúp advice tái sử dụng biểu thức, còn thân method rỗng không được gọi như logic nghiệp vụ để “kiểm tra”.
2. **@Pointcut** giữ expression theo chữ ký cụ thể: public, String trả về, OrderApi, create và đúng một String parameter.
3. **@Before("exactCreate()")** tham chiếu named pointcut trong cùng aspect.
4. **@Before("execution(public void demo.OrderApi.cancel(long))")** là pointcut viết trực tiếp trong advice, chỉ chọn method cancel được mô tả.
5. **@Before("execution(* demo.OrderApi.find(..))")** dùng wildcard để không ràng buộc kiểu trả về và số lượng tham số, nhưng vẫn giới hạn tên method find.
6. **JoinPoint.getArgs()** giúp in đối số thực tế trong advice. Giá trị đối số dùng để **hiển thị**, không phải điều kiện match của các expression này.

**@Aspect** khai báo aspect, **@Component** đăng ký nó thành Spring bean khi scan. Nếu chỉ giữ @Aspect mà không đăng ký bean, Spring AOP không tự tạo instance aspect để áp dụng advice.

### 7.6. Bật Spring AOP trong ApplicationContext

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

**@ComponentScan** đăng ký **OrderServiceImpl** và **SignatureAspect**. **@EnableAspectJAutoProxy** kích hoạt hạ tầng Spring AOP để tìm advisor và proxy bean phù hợp.

Việc bật auto-proxy không có nghĩa toàn bộ bean trong context đều trở thành proxy. Spring xét khả năng áp dụng advisor cho mỗi bean.

### 7.7. Tạo context và gọi lần lượt các method

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderApi service = context.getBean(OrderApi.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(service));

            String created = service.create("A1");
            System.out.println("RESULT " + created);

            service.cancel(7L);

            String found = service.find("A1");
            System.out.println("FOUND " + found);

            service.outer("B2");
        }
    }
}
~~~

Chạy từ thư mục có **pom.xml**:

~~~bash
mvn -q clean compile exec:java
~~~

Các dòng **stdout logic kỳ vọng** theo thứ tự lời gọi (không tính các thông báo riêng của Maven/logging):

~~~text
IS_PROXY true
ADVICE create A1
SERVICE create A1
RESULT created:A1
ADVICE cancel 7
SERVICE cancel 7
ADVICE find A1
SERVICE find A1
FOUND A1
SERVICE outer B2
SERVICE create B2
~~~

### 7.8. Diễn giải output

- **IS_PROXY true**: Spring trả OrderApi bean dưới dạng một AOP proxy.
- **ADVICE create A1**: exactCreate() match phương thức create(String) được gọi qua proxy.
- **ADVICE cancel 7**: match chính xác return **void** và primitive parameter **long**.
- **ADVICE find A1**: wildcard return type và **(..)** cho phép match phương thức find có một String parameter.
- **SERVICE outer B2** rồi **SERVICE create B2**: outer được gọi qua proxy nhưng không thuộc ba advice; còn create được gọi trực tiếp bằng **this** trong target nên không có **ADVICE create B2**.

Đây là điểm phân biệt quan trọng: **create(String) khớp pointcut trong cả hai tình huống**, nhưng chỉ lần gọi từ bên ngoài qua proxy mới có advice.

## 8. Bảng match cụ thể từ dự án

| Expression | create(String) | cancel(long) | find(String) | outer(String) |
| --- | --- | --- | --- | --- |
| **execution(public java.lang.String demo.OrderApi.create(java.lang.String))** | Có | Không | Không | Không |
| **execution(public void demo.OrderApi.cancel(long))** | Không | Có | Không | Không |
| **execution(* demo.OrderApi.find(..))** | Không | Không | Có | Không |
| **execution(* demo.OrderApi.*(..))** | Có | Có | Có | Có |
| **execution(* demo.OrderApi.create())** | Không | Không | Không | Không |
| **execution(* demo.OrderApi.create(*))** | Có | Không | Không | Không |
| **execution(public * demo.OrderApi.*(..))** | Có | Có | Có | Có |
| **execution(void demo.OrderApi.*(..))** | Không | Có | Không | Có |

**Bảng mô tả signature match của các method**, không phải bảng số lần advice sẽ chạy. Khi **outer()** tự gọi **this.create()**, chữ ký create vẫn match expression nhưng invocation đó **không đi qua proxy**.

Những biểu thức rộng như **execution(* demo.OrderApi.*(..))** có thể chọn nhiều method không mong muốn nếu sử dụng cho logging quan trọng, phân quyền hoặc thay đổi kết quả nghiệp vụ. Nên giới hạn tên, layer, modifier hoặc signature phù hợp với mục tiêu thật sự.

## 9. Phân biệt execution với args ở Spring AOP

Một nguồn nhầm lẫn là **declared parameter type** và **runtime argument type**.

Với method Java:

~~~java
public void process(java.io.Serializable value) {
    // ...
}
~~~

Và caller truyền một String:

~~~java
process("hello");
~~~

**String** thực thi interface **Serializable**, nhưng **chữ ký khai báo** của method vẫn nhận **Serializable**, không phải String.

Hai pointcut có ý nghĩa khác nhau:

~~~java
execution(* *.process(java.io.Serializable))
~~~

Biểu thức trên mô tả method có **declared parameter type Serializable**.

~~~java
args(java.lang.String)
~~~

Biểu thức thứ hai là một designator khác do Spring AOP hỗ trợ, xét **kiểu argument tại invocation**. Nếu caller truyền **String**, có thể khớp điều kiện kiểu runtime này; nếu caller truyền một implementation Serializable khác không phải String, điều kiện đó có thể không khớp.

Các đoạn trên là **minh họa cú pháp**, chưa phải file Java chạy độc lập. Một số chi tiết type-matching có thể phụ thuộc type hierarchy và ngữ nghĩa pattern; điểm cần nhớ là **execution dựa vào chữ ký phương thức**, còn **args tham chiếu đối số được truyền lúc chạy**. Không thay execution bằng args khi đề bài thực sự yêu cầu lọc theo tên method hoặc return type.

### 9.1. Vì sao dùng (long) thay vì (java.lang.Long)?

Trong dự án, **cancel(long)** nhận primitive long. Mặc dù Java có boxing/unboxing giữa long và Long khi gọi, chữ ký vẫn mang kiểu **long**. Expression **execution(* demo.OrderApi.cancel(java.lang.Long))** không phải cách viết tương đương cho signature cancel(long).

### 9.2. Overload và chữ ký

Giả sử interface có:

~~~java
void submit(String id);
void submit(String id, int quantity);
void submit(long id);
~~~

Các biểu thức:

~~~text
execution(* *.submit(java.lang.String))
execution(* *.submit(java.lang.String,int))
execution(* *.submit(..))
~~~

Lần lượt chọn overload một String, overload String + int, và mọi overload tên submit. Đây chỉ là **fragment minh họa**; muốn compile cần đặt các method trong interface hoặc class hợp lệ.

Đặc biệt, **execution(* *.submit(*))** chọn các overload có một parameter bất kỳ, không chọn overload có hai parameter.

### 9.3. Varargs và array trong Java

Method:

~~~java
public void send(String... messages) {
    // ...
}
~~~

sử dụng varargs nhưng trong Java bytecode parameter được biểu diễn bằng **String[]**. Vì vậy pointcut cần được đối chiếu với signature được Spring/AspectJ parser hiểu đối với array type, thay vì giả định **(..)** là wildcard chuyên biệt cho varargs.

Nếu chỉ muốn bao quát mọi số lượng tham số của send, **execution(* *.send(..))** là cách diễn đạt dễ đọc. Nếu muốn match đúng array parameter, kiểm tra pattern và kết quả trong project thực tế.

### 9.4. Generics và type erasure

Trong Java, generic type arguments thường không có đầy đủ trong runtime method signature theo cách các lời gọi generic source được viết. Khi lựa chọn pointcut cho generic service interfaces hoặc bridge methods, kết quả matching cần được kiểm tra với type thực tế và Spring proxy.

Đừng giả định một expression chỉ vì ghi kiểu parameterized đầy đủ sẽ tự lọc chính xác **List<String>** khác **List<Integer>** ở runtime. Khi bài toán cần phân biệt loại dữ liệu sâu bên trong generic collection, điều kiện kiểm tra giá trị cần được thực hiện trong logic rõ ràng hoặc bằng metadata thích hợp.

## 10. Named @Pointcut: một tên tái sử dụng biểu thức

Trong ví dụ, chúng ta đã dùng:

~~~java
@Pointcut(
    "execution(public java.lang.String " +
    "demo.OrderApi.create(java.lang.String))"
)
public void exactCreate() {
}
~~~

Và:

~~~java
@Before("exactCreate()")
public void beforeCreate(JoinPoint jp) {
    // ...
}
~~~

Ở đây có **hai chữ ký khác nhau**:

- **Method signature trong execution(...)**: mô tả **method nghiệp vụ** muốn chọn (OrderApi.create(String)).
- **Method signature của exactCreate()**: là **tên pointcut** để tham chiếu trong aspect. Nó phải trả void và thân không chứa nghiệp vụ; **không phải phương thức service được advice**.

Bạn có thể nhóm những biểu thức thành các named pointcut dễ bảo trì hơn:

~~~java
@Pointcut("execution(public * demo.OrderApi.*(..))")
public void publicApiMethod() {
}

@Pointcut("execution(* demo.OrderApi.create(..))")
public void anyCreateOverload() {
}

@Pointcut("publicApiMethod() && anyCreateOverload()")
public void publicCreate() {
}
~~~

Đây là **đoạn minh họa thêm bên trong một class aspect**, không cần chép nguyên cụm vào project runnable nếu không muốn bổ sung advice. Trong Java annotation value, **&&** ở đây là toán tử kết hợp pointcut; không phải vòng lặp Java.

Tính **private/protected/public** của **method định nghĩa @Pointcut** quyết định quy tắc Java visibility khi các aspect khác tham chiếu pointcut đó; nó **không** tự biến expression thành chỉ chọn method nghiệp vụ có modifier tương ứng. Nếu muốn public-only, hãy ghi **public** trong **execution**.

Spring cũng cho phép tham chiếu named pointcut định nghĩa trong type khác bằng tên đầy đủ khi method accessible. Cách này hữu ích khi nhiều aspect của cùng module chia sẻ một quy ước lựa chọn service methods.

## 11. Kết hợp execution với phạm vi bean rõ ràng

Một expression quá rộng:

~~~java
@Before("execution(* *(..))")
public void aroundEverything() {
    // ...
}
~~~

là **mẫu minh họa không nên dùng tùy tiện**. Nó có thể áp dụng cho quá nhiều method phù hợp, tăng nhiễu log, chi phí tạo proxy hoặc gây side effects khó hiểu.

Thường nên thu hẹp theo **package**, **service interface**, hoặc **type**:

~~~java
execution(public * demo.order.service..*.*(..))
~~~

Cách này giới hạn signature vào **demo.order.service** và subpackages, với các public methods mà Spring proxy có thể intercept.

Hoặc chọn một interface contract ổn định:

~~~java
execution(* demo.OrderApi.*(..))
~~~

Có thể kết hợp với designator khác được Spring AOP hỗ trợ, ví dụ:

~~~java
execution(public * demo.OrderApi.*(..)) && bean(orderServiceImpl)
~~~

**bean(...)** là Spring-specific pointcut designator, so theo **bean name**; nó không phải một phần của cú pháp execution. Trong ví dụ có **@Service OrderServiceImpl** và default component naming, tên bean thường là **orderServiceImpl**.

Việc chọn theo **bean name** có thể hữu ích khi nhiều bean cùng interface nhưng bạn chỉ muốn một bean nhất định. Nó có rủi ro phụ thuộc vào tên bean và cách cấu hình context, nên cần cố ý dùng và test.

Các Spring pointcut designator khác như **within**, **@annotation**, **target** cũng có thể được kết hợp để bổ sung điều kiện. Tuy nhiên, nếu nhiệm vụ đơn thuần là chọn method theo signature, ưu tiên **execution** đủ cụ thể và dễ đọc.

## 12. Những lỗi viết execution phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa/kiểm tra |
| --- | --- | --- |
| Advice không chạy | Bean không phải Spring-managed proxy hoặc gọi **this.method()** | Lấy bean từ context, kiểm tra đường gọi |
| Method có tên đúng nhưng không match | Sai kiểu trả về, modifier, declared parameter type hoặc package/type | So chữ ký thật với từng phần của expression |
| Muốn match mọi số tham số nhưng dùng **(*)** | **(*)** chỉ một tham số, không phải mọi số | Dùng **(..)** khi cần mọi số lượng |
| Muốn method không tham số nhưng dùng **(..)** | **(..)** match cả 0, 1, nhiều args | Dùng **()** để chọn đúng 0 |
| Muốn tất cả subpackage nhưng pattern chỉ có **.*** | Wildcard type trực tiếp không tự xuống subpackage | Dùng đúng **..*** ở phần package/type |
| Expression trả String không match method trả Object | Return pattern xét declared return type | Dùng declared type thực tế hoặc **\*** nếu phù hợp |
| cancel(long) không match cancel(Long) | long và Long là hai kiểu declared khác nhau | Viết đúng chữ ký |
| Method chỉ tồn tại trên implementation nhưng bean dùng JDK proxy | JDK proxy công bố interface methods | Đưa method vào interface phù hợp hoặc xét CGLIB |
| Method private/final không được chặn bằng CGLIB | Không thể override theo cơ chế subclass proxy | Tạo public entry point hoặc thay thiết kế |
| Mở rộng pointcut quá nhiều bean | Pattern chọn cả layer không mong muốn | Thu hẹp package, type hoặc bean name |
| Named pointcut không resolve | Sai tên hoặc Java visibility không cho tham chiếu | Kiểm tra method @Pointcut, tên và class |
| Sử dụng **call(...)** như trong AspectJ weaving | Spring proxy-based AOP không hỗ trợ designator đó | Dùng execution và hiểu giới hạn proxy |
| Có **@Aspect** mà chưa có aspect bean | @Aspect không tự đăng ký trong component scanner nếu thiếu @Component hoặc @Bean | Đăng ký aspect rõ ràng |
| Không bật Spring AOP trong context phù hợp | Thiếu @EnableAspectJAutoProxy hoặc cấu hình tương đương | Bật AOP trong context chứa service/aspect |
| In sai số lần advice khi có overloaded methods | Expression broad **(..)** chọn nhiều overload | Giới hạn parameter pattern và viết test |
| Chỉ kiểm tra **AopUtils.isAopProxy == true** | Proxy có thể do advisor khác tạo | Kiểm tra log của advice cụ thể và pointcut thật |

Đọc bảng theo hướng **kiểm tra điều kiện hẹp trước**, không đổi hàng loạt annotation hoặc proxy type mà chưa biết mismatch nằm ở đâu.

## 13. Quy trình debug một execution pointcut

### Bước 1 — Ghi lại method signature thật

Ví dụ:

~~~java
public String create(String id)
~~~

Tách rõ:

- Modifier: **public**.
- Return type: **java.lang.String**.
- Declaring contract: **demo.OrderApi** (hoặc implementation thực tế).
- Name: **create**.
- Parameter count: **1**.
- Declared parameter type: **java.lang.String**.

### Bước 2 — Viết expression từ hẹp đến rộng

Bắt đầu bằng:

~~~java
execution(public java.lang.String demo.OrderApi.create(java.lang.String))
~~~

Nếu không match, có thể tạm bỏ ràng buộc return/argument để điều tra:

~~~java
execution(* demo.OrderApi.create(..))
~~~

Đây là **cách debug tạm thời**, không tự động nên giữ expression rộng khi đưa vào production.

### Bước 3 — Xác minh service là Spring AOP proxy

Trong ví dụ ở mục 7:

~~~java
System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(service)
);
~~~

Nếu giá trị là false, kiểm tra bean được đăng ký và advisor có được Spring áp dụng cho bean không. Nếu là true nhưng advice không chạy, xác minh biểu thức và caller path. **True không chứng minh mọi method đều được advice**.

### Bước 4 — Kiểm tra self-invocation

Thử gọi **service.create("A1")** trực tiếp từ App và gọi **service.outer("B2")**. Nếu trước create từ App có advice nhưng trước this.create bên trong target không có, đó là giới hạn proxy, không phải chữ ký create sai.

### Bước 5 — Phân biệt syntax parse error và no match

- **Parse error**: Spring có thể fail khi tạo advisor/context; kiểm tra dấu ngoặc, full type name, vị trí wildcard, designator được hỗ trợ.
- **No match**: context vẫn chạy nhưng advice không xuất hiện; kiểm tra chữ ký, type, package và đường gọi.
- **Match nhưng advice không như mong đợi**: kiểm tra số lượng aspect beans, thứ tự advice, pointcut kết hợp, exception và logic trong advice.

Nếu dùng overload hoặc subclass/generic interface, viết integration test đủ đại diện thay vì chỉ nhìn một lượt log.

## 14. Bài tập thực hành

**Bài 1 — Chọn mọi method của OrderApi.**

Trong một bản thử riêng, đổi một advice thành:

~~~java
@Before("execution(* demo.OrderApi.*(..))")
public void allMethods(JoinPoint jp) {
    System.out.println("ALL " + jp.getSignature().getName());
}
~~~

Dự đoán log mới khi gọi **create**, **cancel**, **find** và **outer** từ App. Các lời gọi ngoài qua proxy có thể kích hoạt advice ALL; lời gọi **this.create()** trong outer vẫn không tạo invocation proxy riêng.

Lưu ý: đây là **đoạn minh họa để thay thế một advice**, không nên thêm bên cạnh toàn bộ advice cũ rồi so output với mục 7 mà không tính advice mới.

**Bài 2 — Chọn chỉ void methods.**

Dùng:

~~~java
execution(void demo.OrderApi.*(..))
~~~

Đối chiếu **cancel(long)** và **outer(String)**: return type của cả hai là void. Dự đoán vì sao **create(String)** và **find(String)** không khớp.

**Bài 3 — Chọn đúng một parameter bất kể type.**

Dùng:

~~~java
execution(* demo.OrderApi.*(*))
~~~

Mỗi method của ví dụ ở mục 7 đều có đúng một parameter, nên đều khớp ở mức signature. Thêm một method **status()** không có argument rồi kiểm tra nó bị loại.

**Bài 4 — Thêm overload.**

Mở rộng **OrderApi** bằng **create(String,int)**, cài đặt trong service, sau đó so:

~~~java
execution(* demo.OrderApi.create(..))
execution(* demo.OrderApi.create(java.lang.String))
execution(* demo.OrderApi.create(java.lang.String,int))
~~~

Biểu thức đầu chọn cả hai overload; hai biểu thức sau chọn overload riêng. Cần cập nhật source code hợp lệ và chạy lại Maven để tự xác minh.

**Bài 5 — Chọn public trong một package.**

Tách service class sang **demo.service** và sửa pointcut thành:

~~~java
execution(public * demo.service.*.*(..))
~~~

Nếu tạo thêm **demo.service.internal**, hãy so với:

~~~java
execution(public * demo.service..*.*(..))
~~~

để thấy khác biệt giữa package trực tiếp và subpackages. Thử đi qua Spring proxy từ một caller thật.

## 15. Checklist trước khi đưa execution pointcut vào ứng dụng

1. **Đúng phạm vi Spring AOP**: Spring-managed bean, method execution và không đòi intercept field/constructor.
2. **Đúng chữ ký**: return type, modifier, declaring type, method name, count và declared parameter types.
3. **Đúng wildcard**: **\*** là wildcard type/name theo ngữ cảnh; **(..)** là mọi số tham số; **..** trong package pattern có chức năng khác.
4. **Đúng loại proxy**: JDK theo interface hoặc CGLIB theo class; không kỳ vọng private/final method của CGLIB được override.
5. **Đúng đường gọi**: invocation đi từ caller qua proxy, không phải self-invocation trên target.
6. **Aspect đã là bean**: dùng @Component + component scan hoặc @Bean và bật @EnableAspectJAutoProxy trong context phù hợp.
7. **Pointcut đủ hẹp**: không chọn vô tình cả module/layer không liên quan.
8. **Test match và no-match**: có ít nhất một method phải được advice và một method tương tự nhưng không đủ chữ ký.
9. **Kiểm tra quá tải/overload**: không nhầm **(*)** với **(..)**, hoặc primitive với wrapper.
10. **Test hành vi thực tế**: chỉ có proxy không đủ, phải kiểm tra advice cụ thể đã chạy đúng phương thức.

## 16. Câu hỏi tự đánh giá

**1. Vì sao execution(* demo.OrderApi.create(..)) không quan tâm return type?**

Vì **\*** ở vị trí return type match mọi kiểu trả về. Biểu thức vẫn ràng buộc type OrderApi và method create.

**2. execution(* demo.OrderApi.create(*)) khác execution(* demo.OrderApi.create(..)) thế nào?**

Dạng đầu yêu cầu **đúng một parameter** bất kỳ; dạng sau chấp nhận **0 đến nhiều parameter**.

**3. Khi nào nên viết execution(public * *(..))?**

Khi thật sự muốn chọn mọi public method có thể intercept trong vùng AOP xem xét. Trong ứng dụng thực tế nên cân nhắc thêm phạm vi package/type để tránh match quá rộng.

**4. execution chọn theo declared parameter hay đối số runtime?**

Chủ yếu theo chữ ký method và declared type; designator **args(...)** dùng khi muốn quan tâm runtime argument type.

**5. Method trả Object nhưng return ra String ở runtime, execution(java.lang.String ... ) có match không?**

Không chỉ vì giá trị runtime là String; phải xem declared return type và ngữ nghĩa type pattern.

**6. Vì sao create(String) được advice khi App gọi nhưng không được advice khi outer gọi this.create?**

Vì gọi từ App đi qua Spring AOP proxy, trong khi this.create là lời gọi nội bộ trực tiếp trên target.

**7. Một biểu thức chọn private method có đủ để Spring AOP advice private method không?**

Không. Spring proxy không override private method; pointcut không thay đổi cơ chế intercept.

**8. Một named @Pointcut có private method thì có nghĩa chỉ chọn private business methods không?**

Không. Visibility của method định nghĩa named pointcut chỉ điều khiển khả năng tham chiếu Java. Muốn chọn method theo modifier, phải ghi modifier trong **execution**.

**9. Có nên dùng call(...) thay execution(...) để chặn self-invocation trong Spring AOP không?**

Không. Spring proxy-based AOP không hỗ trợ pointcut designator call theo kiểu AspectJ weaving.

**10. Vì sao cần so method signature từ interface khi dùng JDK proxy?**

Vì JDK proxy công bố các public interface methods; một implementation-only method không tự thành API của JDK proxy.

## 17. Tài liệu Spring chính thức

- Spring Framework 6.2 — **Declaring a Pointcut / execution syntax**: https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — **Declaring Advice**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Kết luận:** **execution(...)** là công cụ chính của Spring AOP để lựa chọn **method execution theo chữ ký**. Muốn expression đúng cần xác định chính xác modifier, return type, declaring type, tên method và parameter pattern. Muốn **advice thật sự chạy**, method ấy còn phải thuộc Spring-managed bean và được gọi qua một Spring AOP proxy phù hợp.
