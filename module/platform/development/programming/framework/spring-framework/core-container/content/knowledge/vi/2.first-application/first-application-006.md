# Quan sát đối tượng được tạo và phụ thuộc được cung cấp trong Spring Core Container

## 1. Mục tiêu: nhìn thấy quá trình IoC/DI, không chỉ học annotation

Khi một ứng dụng Java sử dụng **Spring IoC Container**, các đối tượng do container quản lý được gọi là **beans**. Container đọc cấu hình, tạo các đối tượng khi cần, tìm các dependency phù hợp và cung cấp chúng cho đối tượng phụ thuộc. **Dependency Injection (DI)** là cách đối tượng nhận dependency từ bên ngoài thay vì tự khởi tạo tất cả trong logic nghiệp vụ.

Bài này tập trung vào **bằng chứng thực nghiệm**: dùng bộ đếm constructor, danh sách sự kiện, phép so sánh cùng reference (`==`) và đầu ra CLI để trả lời:

- Bean `Repository` được tạo **khi nào** và mấy lần?
- Bean `GreetingService` nhận **đúng đối tượng Repository nào**?
- Gọi `getBean` hai lần đối với singleton có tạo thêm service không?
- Bean `prototype` có sinh instance mới mỗi lần tra cứu không?
- Bean được đánh dấu `@Lazy` đã có **định nghĩa** nhưng **chưa có instance** khi context refresh hay chưa?
- Đóng context thực hiện callback hủy ở thời điểm nào?

Không nhầm ba cấp độ: **class Java** là kiểu, **bean definition** là cấu hình container dùng để tạo/quản lý bean, còn **bean instance** là object thực đã được tạo. Có definition **không đồng nghĩa** đã có instance. Một bean definition `prototype` có thể cấp nhiều instances; bean `singleton` mặc định được chia sẻ **theo definition, trong một container**, không phải một object toàn JVM.

**Phạm vi:** Spring Framework Core Container thuần, không dùng Spring Boot, HTTP server hay database. Ví dụ dùng Java 17+, Maven, `spring-context` và `AnnotationConfigApplicationContext`. Các kết quả chính được kiểm tra bằng stdout do chính chương trình in; log nền của build tool hoặc thư viện không nằm trong expected stdout.

## 2. Đọc sơ đồ quan hệ trước khi nhìn log

Ví dụ có bốn bean:

~~~text
                  AnnotationConfigApplicationContext
                              |
                    AppConfig (@Configuration)
                              |
              +---------------+---------------+
              |               |               |
        repository        greetingService     report
        singleton         singleton          prototype
              |               |                 |
              +---inject----->|            mỗi getBean
                              |            tạo object mới
                              |
                          greet("An")
                              |
                         "data:An"

                      audit (singleton @Lazy)
                          |
              chưa cần lúc refresh;
              tạo ở lần getBean đầu
~~~

Các factory methods `@Bean` sẽ khai báo `repository`, `greetingService`, `report` và `audit`. Factory method của `greetingService` nhận một **tham số `Repository`**. Spring resolve một bean phù hợp rồi đưa **reference thật** vào lời gọi factory method, từ đó vào constructor của service.

Để quan sát đủ các góc nhìn, demo sẽ:
1. Tạo context **rỗng** rồi `register(AppConfig.class)`.
2. In các bộ đếm **trước `refresh()`**.
3. Gọi `refresh()` để bootstrap context, tạo các singleton **không lazy**.
4. In bộ đếm, creation trace và tình trạng đã đăng ký bean `audit`.
5. Lấy `GreetingService` và `Repository`; so sánh reference được inject.
6. Lấy `Report` hai lần, sau đó yêu cầu bean lazy `Audit`.
7. Đóng context bằng `try-with-resources` và quan sát destroy callback.

Chúng ta **không phụ thuộc thứ tự toàn bộ bean nội bộ của Spring** hoặc số lượng bean definitions của framework. Bộ đếm chỉ đặt trong constructor của **các lớp demo**, vì vậy không bị nhiễu bởi hạ tầng container.

## 3. Chuẩn bị dự án Maven độc lập

Cần **JDK 17+**, **Maven 3.9+**, internet lần đầu tải dependency (hoặc một mirror Maven sẵn có). Kiểm tra môi trường:

~~~bash
java -version
javac -version
mvn -version
~~~

Các lệnh kiểm tra môi trường không có stdout cố định. Nếu `mvn -version` hiển thị Java khác với `java -version`, kiểm tra `JAVA_HOME`, `PATH` và thiết lập toolchain.

Tạo cây thư mục:

~~~text
bean-observation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanObservationDemo.java
~~~

Tệp `pom.xml` đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-observation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                    <mainClass>demo.BeanObservationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp `AnnotationConfigApplicationContext`, `@Configuration`, `@Bean` và kéo các module cần thiết theo dependency graph. Không cần thêm `spring-boot-starter`; Maven/Gradle tự resolve classpath. `maven.compiler.release=17` giúp biên dịch theo API Java 17.

Mốc **Spring Framework 7.0.9** cố định để ví dụ tái hiện được; nó hỗ trợ Java 17. Đối với sản phẩm thực tế, sử dụng bản vá được hỗ trợ và đồng bộ các Spring modules theo BOM/dependency management phù hợp.

## 4. Mã Java 17: ghi dấu thời điểm tạo object

Tạo đúng file `src/main/java/demo/BeanObservationDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

public final class BeanObservationDemo {
    private BeanObservationDemo() {
    }

    // Bộ đếm và trace chỉ dùng cho chương trình demo chạy một luồng.
    private static final List<String> TRACE = new ArrayList<>();
    private static int repositoryCreated;
    private static int serviceCreated;
    private static int reportCreated;
    private static int auditCreated;

    public static final class Repository {
        private final int id;

        public Repository() {
            id = ++repositoryCreated;
            TRACE.add("repository#" + id);
        }

        public int id() {
            return id;
        }

        public String load() {
            return "data";
        }

        public void shutdown() {
            System.out.println("destroy.repository#" + id);
        }
    }

    public static final class GreetingService {
        private final Repository repository;
        private final int id;

        public GreetingService(Repository repository) {
            this.repository = repository;
            id = ++serviceCreated;
            TRACE.add("service#" + id + "(repository#" + repository.id() + ")");
        }

        public Repository repository() {
            return repository;
        }

        public String greet(String name) {
            return repository.load() + ":" + name;
        }
    }

    public static final class Report {
        private final int id;

        public Report() {
            id = ++reportCreated;
        }

        public int id() {
            return id;
        }
    }

    public static final class Audit {
        public Audit() {
            auditCreated++;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean(destroyMethod = "shutdown")
        public Repository repository() {
            return new Repository();
        }

        // Spring cung cấp Repository qua tham số factory method.
        @Bean
        public GreetingService greetingService(Repository repository) {
            return new GreetingService(repository);
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public Report report() {
            return new Report();
        }

        @Bean
        @Lazy
        public Audit audit() {
            return new Audit();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(AppConfig.class);

            System.out.println("beforeRefresh.repository=" + repositoryCreated);
            System.out.println("beforeRefresh.service=" + serviceCreated);

            context.refresh();

            System.out.println("afterRefresh.repository=" + repositoryCreated);
            System.out.println("afterRefresh.service=" + serviceCreated);
            System.out.println("afterRefresh.report=" + reportCreated);
            System.out.println("afterRefresh.audit=" + auditCreated);
            System.out.println("creation.trace=" + String.join(" > ", TRACE));
            System.out.println("definition.audit="
                    + context.containsBeanDefinition("audit"));

            Repository repository = context.getBean(Repository.class);
            GreetingService first = context.getBean(GreetingService.class);
            GreetingService second = context.getBean(GreetingService.class);

            System.out.println("sameService=" + (first == second));
            System.out.println("sameInjectedRepository="
                    + (first.repository() == repository));
            System.out.println("greeting=" + first.greet("An"));

            Report reportA = context.getBean(Report.class);
            Report reportB = context.getBean(Report.class);

            System.out.println("report.ids="
                    + reportA.id() + "," + reportB.id());
            System.out.println("sameReport=" + (reportA == reportB));

            Audit audit = context.getBean(Audit.class);
            System.out.println("afterLookup.audit=" + auditCreated);
            System.out.println("sameAuditSingleton="
                    + (audit == context.getBean(Audit.class)));
        }

        System.out.println("context.closed=true");
    }
}
~~~

### Tại sao cách ghi dấu này đáng tin?

- Chỉ **constructor của `Repository`** tăng `repositoryCreated` và thêm `repository#1` vào trace.
- Constructor của **`GreetingService`** nhận đúng `Repository` được truyền vào, tăng `serviceCreated` và ghi ID dependency đã nhận. Do đó trace phản ánh **thứ tự quan sát tạo hai bean nghiệp vụ**, không cần đoán thời điểm Spring tạo bean nội bộ.
- Hai bean trên là singleton **không lazy**; lúc `refresh()` hoàn thành, chúng thông thường đã được tạo. `Report` là prototype và `Audit` là lazy singleton, nên chúng chưa được tạo trong trường hợp cụ thể này.
- Lần gọi `getBean(Report.class)` nào cũng yêu cầu tạo thêm một `Report`; mỗi instance có ID tăng dần. Không dùng `System.identityHashCode`, vì giá trị đó không cố định giữa những lần chạy.
- Bean `audit` đã có **definition**, nhưng chỉ tạo instance lúc ứng dụng gọi `getBean(Audit.class)`. Nếu sau này một bean singleton eager phụ thuộc vào `Audit`, dependency đó có thể làm Audit được tạo ngay từ `refresh()`.
- `@Bean(destroyMethod="shutdown")` yêu cầu Spring gọi `Repository.shutdown()` trong quá trình đóng context. Trace này phân biệt shutdown callback với Java garbage collection.

`@Configuration(proxyBeanMethods = false)` phù hợp vì các `@Bean` methods **không gọi trực tiếp nhau**; dependency `Repository` được container cung cấp qua tham số. Nếu tự gọi `repository()` trong `greetingService()` ở chế độ này, lời gọi Java thông thường có thể tạo object khác, đi ngược điều ta muốn chứng minh.

## 5. Biên dịch, chạy và expected stdout

Mở terminal tại thư mục **`bean-observation-demo`** chứa `pom.xml`. Trên Windows PowerShell, CMD, Linux hoặc macOS, lệnh Maven sau dùng chung:

~~~bash
mvn -q clean compile exec:java
~~~

Maven Compiler Plugin sử dụng `javac` cho Java 17 và Exec Maven Plugin chạy `demo.BeanObservationDemo` với các JAR Spring/dependency transitive trên classpath. Dùng `javac BeanObservationDemo.java` trần **không đủ** nếu chưa khai báo classpath Spring.

**Stdout xác định do các lệnh `System.out.println` trong source ở mục 4 tạo ra**, không tính banner/log/diagnostics mà Maven hoặc logging backend có thể in ra:

~~~text
beforeRefresh.repository=0
beforeRefresh.service=0
afterRefresh.repository=1
afterRefresh.service=1
afterRefresh.report=0
afterRefresh.audit=0
creation.trace=repository#1 > service#1(repository#1)
definition.audit=true
sameService=true
sameInjectedRepository=true
greeting=data:An
report.ids=1,2
sameReport=false
afterLookup.audit=1
sameAuditSingleton=true
destroy.repository#1
context.closed=true
~~~

Bộ đếm `static` bắt đầu lại từ 0 khi chạy trong **JVM mới**. Nếu bạn chạy lại `main` nhiều lần trong **cùng một JVM** hoặc biến chương trình thành ứng dụng đa luồng, bộ đếm có thể khác: đây là dụng cụ quan sát cho demo một luồng, không phải một API định danh đối tượng của Spring.

Kết quả không dựa vào thời gian thực, random, địa chỉ bộ nhớ hay thứ tự các bean nội bộ của Spring. Vì `GreetingService` cần một `Repository` và trace chỉ ghi hai constructor nghiệp vụ đó, `repository#1` phải được tạo trước khi `service#1(repository#1)` hoàn tất.

## 6. Phân tích từng bằng chứng trong output

| Dòng/nhóm kết quả | Nó chứng minh điều gì? | Không nên suy diễn |
| --- | --- | --- |
| `beforeRefresh.*=0` | Mới đăng ký nguồn cấu hình, chưa khởi tạo hai bean nghiệp vụ | Không có nghĩa container chưa có bean definitions nội bộ |
| `afterRefresh.repository=1` và `service=1` | Hai singleton không lazy đã được tạo | Không có nghĩa mọi bean đều eager |
| `afterRefresh.report=0` | Chưa yêu cầu instance prototype nào | Không có nghĩa thiếu bean definition `report` |
| `afterRefresh.audit=0`, `definition.audit=true` | Metadata lazy bean đã được đăng ký, instance chưa tạo | Không có nghĩa lazy luôn thắng mọi dependency eager |
| `creation.trace=repository#1 > service#1(...)` | Trước khi constructor service hoàn thành, Spring đã cung cấp repository | Không chứng minh một thứ tự tuyệt đối giữa mọi singleton độc lập |
| `sameService=true` | Hai lookup trong cùng context trả một singleton instance | Không phải singleton toàn JVM/mọi context |
| `sameInjectedRepository=true` | Reference service giữ đúng là bean Repository được lấy từ context | Không chứng minh mọi dependency có cùng scope |
| `report.ids=1,2` và `sameReport=false` | Hai request tới prototype tạo hai đối tượng | Không tự chứng minh container sẽ hủy chúng |
| `afterLookup.audit=1` và `sameAuditSingleton=true` | Lazy singleton được tạo một lần khi yêu cầu và dùng lại | Không đồng nghĩa scope của nó là prototype |
| `destroy.repository#1` | Shutdown callback đã chạy khi đóng context | Không có nghĩa object bị GC ngay |
| `context.closed=true` | Dòng này chạy sau khi khối try-with-resources hoàn tất | Không phải phép đo số tài nguyên đã giải phóng |

### Điều được quan sát là *reference*, không chỉ giá trị

Hai object khác nhau có thể có cùng trường, cùng `toString()` hoặc `equals()` trả `true`; điều đó không có nghĩa chúng là **cùng instance**. Trong chương trình, `first == second`, `first.repository() == repository`, `reportA == reportB` kiểm tra **reference identity**.

Đừng dùng `==` để so sánh **giá trị nội dung** của `String` hay nhiều value objects thông thường; ở đây `==` được chọn có chủ đích để chứng minh bean instance nào được chia sẻ.

## 7. Phân biệt tạo bean, inject dependency và sử dụng nghiệp vụ

Quan sát ba bước liên quan nhưng không đồng nhất:

1. **Tạo object**: constructor `new Repository()` được gọi bởi factory method `@Bean repository()`. Spring tiếp nhận object mà factory method trả về làm bean theo registration.
2. **Cung cấp dependency**: container resolve bean `Repository` và đưa reference vào tham số `greetingService(Repository repository)`. Factory method truyền tiếp reference đó cho constructor của `GreetingService`.
3. **Sử dụng**: code ứng dụng lấy service bằng `getBean`, rồi gọi `first.greet("An")`. Bước gọi nghiệp vụ là Java bình thường; Spring không cần “tiêm lại” Repository mỗi lần `greet` chạy.

Một thiết kế đối lập:

~~~java
// Mã minh họa Java thuần, giả sử các type đã có trong lớp bài.
GreetingService wrong = new GreetingService(new Repository());
~~~

Dòng trên **tự tạo hai object**, không cần container resolve hay quản lý chúng. Nó có thể hợp lý trong một ứng dụng Java nhỏ, nhưng **không** chứng minh Spring đã inject một bean. Trong demo, dòng này còn làm thay đổi bộ đếm, nên đừng chèn vào chương trình gốc nếu vẫn muốn so stdout chuẩn.

### Constructor injection trong component scan

Cùng ý tưởng DI có thể được viết bằng class Spring-managed:

~~~java
// Đoạn minh họa; các class phải được đăng ký/scan và có bean Repository.
@Component
class GreetingHandler {
    private final Repository repository;

    GreetingHandler(Repository repository) {
        this.repository = repository;
    }
}
~~~

Trong một component chỉ có **một constructor**, Spring có thể chọn constructor ấy mà không cần `@Autowired` tường minh. Tuy nhiên, `@Component` **không tự** khiến class thành bean: context phải scan hoặc đăng ký class. Đoạn trên **không độc lập**; code hoàn chỉnh chạy được nằm ở mục 4.

DI giúp `GreetingService` dễ test bằng một implementation giả hoặc một dependency được truyền thủ công, nhưng không tự bảo đảm code thread-safe hay business logic đúng.

## 8. Thử thay đổi có kiểm soát để hiểu sâu hơn

Giữ bản gốc và làm từng thay đổi riêng, khôi phục code trước khi so output chuẩn.

### Thử nghiệm A — tạo bean lúc refresh hay lúc lookup?

Đổi bean `repository()` sang `@Lazy`:

~~~java
@Bean
@Lazy
public Repository repository() {
    return new Repository();
}
~~~

Dù `Repository` có `@Lazy`, bean `GreetingService` vẫn **singleton eager** và bắt buộc cần `Repository`. Do đó repository có thể vẫn được tạo trong `refresh()`: lazy singleton **không trì hoãn dependency bắt buộc của singleton eager**. Đây là tình huống phản ví dụ quan trọng; không nên dự đoán `afterRefresh.repository=0` chỉ dựa trên annotation mới.

Nếu đồng thời đánh dấu **`GreetingService` là `@Lazy`** và không có bean eager nào phụ thuộc hai bean này, cả hai có thể chưa được tạo lúc refresh. Lần đầu lấy service sẽ khiến Spring resolve và tạo repository rồi service.

### Thử nghiệm B — singleton và prototype

Đổi `@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)` trên `report()` thành singleton mặc định. Nếu không có bean eager nào dùng report, context thông thường sẽ pre-instantiate singleton này trong refresh, nên `afterRefresh.report` có thể thành `1`, `report.ids` thành `1,1` và `sameReport=true`.

Nếu giữ report prototype mà inject nó **một lần vào constructor của một singleton**, singleton thường giữ **cùng instance prototype đã inject** suốt đời của nó; Spring không tự làm mới dependency mỗi lần bạn gọi phương thức singleton. Muốn tạo mới theo nhu cầu, có thể xem `ObjectProvider<Report>` hoặc lookup-method injection — đó là chủ đề nâng cao, không phải chức năng mặc định của field injection.

### Thử nghiệm C — đổi thứ tự registration có làm DI hỏng?

Thử đổi vị trí phương thức `repository()` và `greetingService()` trong `AppConfig`. Bean graph vẫn có thông tin dependency kiểu `Repository`; Spring không dựa vào người viết source đặt factory method ở đầu file để quyết định service nhận dependency nào. **Đừng đặt yêu cầu về thứ tự tuyệt đối của các singleton độc lập** dựa vào thứ tự code trong file.

### Thử nghiệm D — giả lập thiếu dependency

Tạm xóa hoặc comment `@Bean repository()` trên bản sao rồi chạy lại. `GreetingService` còn yêu cầu `Repository`, nên context có thể thất bại khi bootstrap với exception dạng `UnsatisfiedDependencyException`/`NoSuchBeanDefinitionException` lồng nhau. Thông điệp chi tiết và thứ tự cause có thể thay đổi theo phiên bản; hãy quan sát **nguyên nhân gốc** thay vì chép một stack trace cố định.

### Thử nghiệm E — dùng hai container

Tạo context thứ hai với cùng `AppConfig`. Singleton được chia sẻ **trong từng context**, không mặc nhiên qua hai contexts. Nếu giữ bộ đếm `static` của demo, IDs tiếp tục tăng trong cùng JVM; đó là **bộ đếm do ta viết**, không phải Spring tự gán ID global cho bean.

## 9. Cách quan sát thực tế: logger, debugger và kiểm thử

Bộ đếm và `System.out.println` có giá trị khi học, nhưng dự án thực tế nên quan sát ít xâm lấn và kiểm thử có mục tiêu:

- **Debugger**: đặt breakpoint ở constructor `Repository`, `GreetingService`, `report()` hoặc `audit()`. Xem call stack, đối số `repository`, reference identity và nhánh dẫn tới việc tạo bean.
- **Logger**: ghi sự kiện lifecycle có cấu trúc khi thực sự cần; không log secret hoặc dữ liệu nhạy cảm. Tránh phụ thuộc thứ tự startup logger framework cho test logic.
- **Test identity**: dùng assertions để kiểm chứng `assertSame` / `assertNotSame` tương đương với mục đích tham chiếu. Nếu dùng JUnit, hãy thêm dependency và cấu hình build tương ứng; demo hiện tại **không yêu cầu JUnit**.
- **`getBeanDefinitionNames()`**: dùng để điều tra metadata đang đăng ký, nhưng con số và thứ tự liệt kê có thể gồm bean nội bộ và không ổn định. Không dùng “bean count toàn context” làm expected output của bài.
- **`BeanPostProcessor`**: có thể quan sát/gắn xử lý trước–sau initialization ở cấp bean. Đó là extension point nâng cao, **khác** với `BeanFactoryPostProcessor` vốn tập trung vào metadata.
- **Actuator**: dành cho ứng dụng Spring Boot khi đã thêm dependency/cấu hình cần thiết. Demo Framework thuần không có Actuator mặc định.

**Không đo tốc độ khởi động bằng số dòng constructor log.** Một ứng dụng có lazy beans, proxy hoặc nhiều scopes vẫn có thể khởi tạo đúng theo thiết kế. “Bean đã đăng ký”, “bean instance đã tạo”, “dependency đã inject” và “đã chạy logic nghiệp vụ” là bốn quan sát riêng.

## 10. Lỗi thường gặp khi đọc kết quả

| Nhận định/lỗi | Sự thật hoặc cách kiểm tra |
| --- | --- |
| “Gọi `getBean` thì Spring mới tạo mọi singleton” | Singleton không lazy thường được tạo trong `ApplicationContext.refresh()` |
| “Có `BeanDefinition` thì constructor chắc chắn đã chạy” | Metadata có thể tồn tại trước instance, đặc biệt lazy/prototype |
| “`@Lazy` luôn ngăn bean tạo lúc startup” | Eager singleton cần nó vẫn có thể kích hoạt việc tạo |
| “Một class Java chỉ có một object trong Spring” | Nhiều definitions/contexts/scopes có thể có nhiều instances cùng type |
| “Prototype được inject vào singleton thì tự tạo mới ở mỗi method call” | Inject thường xảy ra một lần lúc tạo singleton |
| “Hai bean có giá trị bằng nhau là cùng reference” | Muốn kiểm tra identity phải xét reference/quan hệ `==` đúng ngữ cảnh |
| “Một object do code `new` là Spring bean” | Chỉ thành bean nếu đi qua cơ chế container quản lý/đăng ký thích hợp |
| “`@Bean` factory method là một instance” | Method là nguồn khai báo cách tạo; object trả về mới là bean instance |
| “`close()` khiến object mất khỏi heap ngay” | Context gọi destruction callbacks phù hợp; JVM GC độc lập |
| “Nhìn log tạo service là DI thành công hoàn toàn” | Cần xác nhận dependency đúng reference/type và service hoạt động |
| “Mọi bean luôn tạo theo thứ tự khai báo trong file” | Dependency graph, scope, lazy và processing quyết định; đừng dựa vào thứ tự source |
| “Lỗi `NoSuchBeanDefinitionException` do Maven thiếu Spring JAR” | Thường là thiếu bean phù hợp trong context; phân biệt với compile/classpath error |

### Khi output thực tế lệch

1. **Kiểm tra code đã sửa chưa**: `@Lazy`, `@Scope`, factory method, lần gọi `getBean` có khác bản gốc không?
2. **Kiểm tra chạy trong JVM mới hay cùng JVM**: bộ đếm `static` có thể giữ state nếu chạy lại `main` trong cùng JVM.
3. **Tách log khỏi stdout ứng dụng**: Maven, Spring, logging backend có thể tạo thêm diagnostic.
4. **Đọc exception chain**: nếu thiếu dependency hoặc có nhiều bean cùng type, context có thể thất bại ngay ở `refresh()` trước khi in phần after-refresh.
5. **Kiểm tra Java và dependencies**: `mvn -version`, `mvn dependency:tree` để phát hiện runtime/JDK/version conflict.
6. **Đối chiếu bằng identity**: nếu `sameInjectedRepository=false`, kiểm tra có tạo thêm object bằng `new`, cấu hình nhiều definitions, proxy hoặc scope ngoài dự kiến hay không.

## 11. Bài tập tự kiểm tra và tài liệu chính thức

Làm từng bài trên một bản sao sạch, giải thích dự đoán trước khi chạy:

1. Chỉ ra hai dòng chứng minh **Repository được tạo trước Service** và một dòng chứng minh Service nhận cùng bean Repository từ context.
2. Giải thích vì sao `reportCreated=0` sau refresh nhưng `getBean(Report.class)` hai lần vẫn tạo ID `1,2`.
3. Dự đoán `auditCreated` nếu không gọi `getBean(Audit.class)` ở bất kỳ nơi nào.
4. Đổi `Report` sang singleton; ghi nhận chính xác những dòng expected stdout thay đổi.
5. Gắn `@Lazy` cho Repository rồi giải thích vì sao vẫn có thể được tạo lúc refresh do Service.
6. Thêm một bean `GreetingService` khác có type giống nhau; dự đoán hành vi lookup bằng type và cách sửa bằng `@Primary`/`@Qualifier`.
7. Thử `new Repository()` thủ công và quan sát counter tăng nhưng bean `repository` trong Spring **không bị thay thế**.
8. Giữ một reference tới Repository sau `context.close()`. Giải thích shutdown callback khác garbage collection ra sao.
9. Bỏ definition Repository trên bản sao, tìm nguyên nhân exception ở bước refresh; không coi exception message chi tiết là API ổn định.
10. Chạy test identity mà **không cần Spring**, tự truyền Repository vào constructor GreetingService; chỉ ra điểm giống và khác với DI do container tự resolve.

**Checklist đạt bài:**

- [ ] Phân biệt thời điểm `register`, `refresh`, tạo singleton, lấy prototype, lấy lazy bean và `close()`.
- [ ] Biết **factory-method parameter injection** truyền bean instance nào cho service.
- [ ] Hiểu `sameService=true` và `sameInjectedRepository=true` kiểm tra hai quan hệ khác nhau.
- [ ] Nêu rõ tại sao **bean definition** không đồng nghĩa **đã tạo object**.
- [ ] Không nhầm singleton theo container với singleton toàn JVM.
- [ ] Tự biên dịch/chạy Maven Java 17 và dự đoán chính xác 17 dòng stdout gốc.
- [ ] Phân biệt logging quan sát và side effects quan sát do demo tự thêm.

**Tài liệu chính thức:**

- [Spring Framework – IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring – Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Spring – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring – Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Kết luận:** Muốn biết Spring đã làm gì, hãy quan sát **đúng ranh giới**: metadata được đăng ký, constructor chạy, dependency reference được inject, bean được lấy và callback đóng được gọi. Trong demo, các bộ đếm, nhật ký tạo và phép so reference cho bằng chứng cụ thể mà không phải dựa vào cảm giác “Spring đã tự tạo tất cả”.