# Tiêm qua setter cho cấu hình có thể tùy chọn trong Spring Core Container

## 1. Mục tiêu: dependency bắt buộc khác cấu hình tùy chọn

**Setter injection** là cách Spring cung cấp một giá trị hoặc cộng tác viên cho bean thông qua **phương thức setter** sau khi đối tượng đã được tạo. Kỹ thuật này đặc biệt hữu ích khi một dependency **không phải điều kiện bắt buộc** để đối tượng thực hiện nhiệm vụ chính, hoặc khi một thông số có **giá trị mặc định hợp lý** nhưng có thể thay đổi qua cấu hình.

Ví dụ: `ReportService` luôn cần `ReportRepository` để lấy dữ liệu báo cáo, nhưng có thể:

- Có hoặc không có `AuditSink` để ghi dấu vết xử lý.
- Dùng tiền tố hiển thị mặc định `REPORT`, hoặc thay bằng giá trị cấu hình như `CUSTOM`.

Thiết kế thích hợp là:

- **Constructor injection** cho `ReportRepository`: không có repository thì service không thể làm việc.
- **Setter injection** cho `AuditSink`: nếu không có audit, chức năng chính vẫn chạy.
- **Setter nhận property** cho tiền tố báo cáo: có giá trị mặc định hợp lệ; cấu hình chỉ ghi đè khi cần.

~~~text
ApplicationContext
     |
     +-- tạo ReportRepository bean
     |
     +-- gọi new ReportService(repository)  [bắt buộc]
     |         |
     |         +-- @Value setter: prefix = REPORT hoặc CUSTOM
     |         |
     |         +-- @Autowired(required=false) setter:
     |                    AuditSink bean có -> gọi setter
     |                    AuditSink bean thiếu -> không gọi setter
     |
     +-- trả ReportService bean đã cấu hình
                      |
                      +-- render(id) -> repository.find(id)
                                      -> audit nếu có
                                      -> chuỗi kết quả
~~~

**Điểm cốt lõi:** “tùy chọn” không có nghĩa là Spring sẽ luôn truyền `null`. Với `@Autowired(required = false)` đặt trên một method, nếu dependency không khả dụng, Spring có thể **không gọi method đó**. Vì vậy trạng thái mặc định đã thiết lập trong object sẽ được giữ nguyên.

## 2. Constructor injection và setter injection khác nhau ở đâu?

| Tiêu chí | Constructor injection | Setter injection |
| --- | --- | --- |
| Thời điểm cung cấp dependency | Khi tạo object | Sau khi object được tạo, trong quá trình cấu hình bean |
| Phù hợp nhất | Dependency bắt buộc, invariant để object hợp lệ | Dependency/tùy chọn cấu hình có default rõ |
| Có thể dùng trường `final`? | Thường có, vì gán trong constructor | Không thể gán lại `final` qua setter bình thường |
| Nếu thiếu dependency | Thường thất bại ở bước tạo bean | Tùy cấu hình: lỗi, bỏ qua hoặc dùng default |
| Mức độ linh hoạt sau khi tạo | Ít đổi reference hơn | Có thể đổi cấu hình nhưng phải kiểm soát lifecycle/thread safety |
| Unit test Java thuần | Truyền dependency vào constructor | Tạo object rồi gọi setter rõ ràng |
| Nguy cơ | Constructor quá nhiều tham số có thể báo hiệu class ôm nhiều trách nhiệm | Bean có thể ở trạng thái chưa cấu hình hoàn chỉnh nếu dùng sai |

Ví dụ Java thuần:

~~~java
public final class ReportService {
    private final ReportRepository repository;  // bắt buộc
    private String prefix = "REPORT";            // giá trị mặc định

    public ReportService(ReportRepository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }

    public void setPrefix(String prefix) {        // tùy chọn
        this.prefix = prefix;
    }
}
~~~

Đây là **đoạn minh họa**, thiếu định nghĩa `ReportRepository` và phần xử lý nên chưa phải file chạy độc lập. Khối trên cho thấy Java đã hỗ trợ setter injection theo nghĩa “người bên ngoài gọi setter để cấu hình”; **Spring không phát minh setter**, mà giúp gọi nó bằng metadata và dependency resolution.

**Quy tắc thiết kế:** đừng chuyển mọi tham số constructor sang setter chỉ để giảm số tham số. Một class mà không có các dependency quan trọng vẫn bị coi là “khởi tạo thành công” có thể ném `NullPointerException` rất muộn khi xử lý nghiệp vụ. Đối với các dependency bắt buộc, constructor injection thường minh bạch và an toàn hơn.

## 3. Setter là một điểm cấu hình, không bắt buộc có Spring

Một setter truyền thống có chữ ký:

~~~java
public void setAuditSink(AuditSink sink) {
    this.auditSink = sink;
}
~~~

Nếu mã khởi động tự làm:

~~~java
ReportService service = new ReportService(repository);
service.setAuditSink(new ConsoleAuditSink());
~~~

thì đó là **setter injection thủ công**. Các kiểu trong hai khối này được giả định đã định nghĩa; chương trình đầy đủ nằm ở mục 6.

Cấu hình Spring có thể chọn gọi setter theo ba cách phổ biến:

1. **Explicit setter call trong `@Bean` factory method**: khi tạo bean, cấu hình Java tự gọi `set...`.
2. **Annotation `@Autowired` trên setter**: Spring cố gắng tìm bean phù hợp và gọi setter qua `AutowiredAnnotationBeanPostProcessor`.
3. **Property injection từ XML**: `<property name="auditSink" ref="auditSink"/>` khiến Spring áp dụng JavaBeans property setter.

Đối với giá trị scalar từ environment, một method nhận `@Value("${app.report.prefix:REPORT}")` có thể nhận chuỗi property đã được Spring resolve rồi lưu vào trường. Cú pháp `${key:default}` có phần sau dấu `:` làm giá trị mặc định nếu không có key thích hợp.

Không nên coi mọi cơ chế này là giống hệt nhau. `@Bean` gọi setter trực tiếp do **mã cấu hình** quyết định; `@Autowired` có semantics về bean candidate và `required`; `@Value` phụ thuộc property resolution, còn XML `<property>` là metadata của bean definition.

## 4. `@Autowired(required = false)`: setter có thể được bỏ qua

### 4.1. Cú pháp và semantics

~~~java
private AuditSink auditSink;  // mặc định null: không có audit

@Autowired(required = false)
public void setAuditSink(AuditSink auditSink) {
    this.auditSink = auditSink;
}
~~~

Đây là trích đoạn từ chương trình chạy mục 6. Trong một `ApplicationContext` có annotation processing:

- Nếu có một bean `AuditSink` phù hợp, Spring gọi setter và đặt reference.
- Nếu **không có** bean phù hợp, **không gọi setter**, trường giữ giá trị mặc định đã khai báo.
- Với một method có **nhiều tham số**, `required = false` áp dụng cho cả method: chỉ cần một dependency không khả dụng, method có thể bị bỏ qua hoàn toàn.
- Nếu có **nhiều bean `AuditSink` cùng phù hợp nhưng không chọn được một**, `required = false` không phải cơ chế để giải quyết mơ hồ: cần `@Qualifier`, `@Primary` hoặc cấu hình hợp lý.
- Nếu có bean nhưng quá trình tạo dependency thất bại, đừng coi `required = false` là cơ chế nuốt mọi exception của constructor/factory hay lỗi cấu hình.
- Nếu setter được gọi mà **body setter tự ném exception**, bean creation vẫn có thể thất bại.

Nói cách khác, thuộc tính `required = false` có nghĩa **điểm injection không bắt buộc phải được đáp ứng**, chứ không phải “bất kể có lỗi gì cũng bỏ qua”.

### 4.2. Thiết kế hành vi khi không có dependency

Nếu audit thật sự là tùy chọn, mã dùng phải xử lý trường hợp vắng mặt rõ ràng:

~~~java
if (auditSink != null) {
    auditSink.record(reportId);
}
~~~

Một cách khác là **Null Object pattern**: khởi tạo reference bằng một implementation không làm gì, rồi cho setter ghi đè khi có bean thật:

~~~java
private AuditSink auditSink = reportId -> { };

@Autowired(required = false)
public void setAuditSink(AuditSink auditSink) {
    this.auditSink = java.util.Objects.requireNonNull(auditSink);
}
~~~

Nếu không có bean, setter bị bỏ qua và audit implementation mặc định im lặng. Cách này tránh `null` check ở từng lời gọi, nhưng phải đặt tên/semantics rõ ràng để không vô tình che lỗi thiếu audit khi audit là yêu cầu bắt buộc.

Trong bài chạy ở mục 6, ta dùng `null` + kiểm tra rõ ràng để dễ quan sát `AUDIT_ENABLED false/true`.

### 4.3. `Optional<T>` và `ObjectProvider<T>` là những lựa chọn khác

Khi dependency chỉ để thể hiện “có hoặc không”, bạn cũng có thể dùng:

~~~java
public ReportService(ReportRepository repository,
                     java.util.Optional<AuditSink> optionalAudit) {
    this.repository = repository;
    this.auditSink = optionalAudit.orElse(null);
}
~~~

Đây là đoạn **minh họa constructor** cần các field/interface tương ứng. Spring hỗ trợ xử lý injection của `Optional<T>`; cách này cho phép dependency tùy chọn được biểu lộ ngay ở constructor, không bắt buộc phải dùng setter.

Nếu collaborator phải được lấy **theo nhu cầu ở thời điểm chạy**, có thể cân nhắc `ObjectProvider<AuditSink>`, chẳng hạn `getIfAvailable()`. Tuy nhiên:

- Đừng dùng provider chỉ để thay cho một tham chiếu optional đơn giản.
- Đọc contract của `getIfAvailable()`, bao gồm tình huống nhiều candidate gây mơ hồ.
- Đừng trộn tùy chọn cấu hình với lựa chọn implementation thay đổi theo từng request.

Với configuration property scalar, `@Value` có default hoặc bean `@ConfigurationProperties` của Spring Boot (nếu dùng Boot) thường phù hợp hơn một `Optional<Bean>` chỉ để chứa chuỗi.

## 5. `@Value` trên setter: default và cấu hình bên ngoài

### 5.1. Giá trị mặc định bằng placeholder

~~~java
private String prefix = "REPORT";

@Value("${app.report.prefix:REPORT}")
public void setPrefix(String prefix) {
    this.prefix = prefix;
}
~~~

Trong trường hợp property `app.report.prefix` không tồn tại, Spring dùng default `REPORT`. Nếu property có giá trị `CUSTOM`, setter nhận `CUSTOM`.

Phân biệt:

- **Java default field:** `private String prefix = "REPORT";` có sẵn khi constructor kết thúc.
- **Property placeholder default:** `${app.report.prefix:REPORT}` là quy tắc resolve của Spring khi key chưa được cung cấp.
- **Setter body validation:** nếu cần, method phải kiểm tra prefix không null/blank để tránh nhận cấu hình vô nghĩa.
- **@Value không đồng nghĩa @Autowired(required=false):** `@Value` cung cấp giá trị đã resolve; optional bean injection có semantics riêng.
- **Một property rỗng hoặc chứa toàn dấu cách** có thể vẫn được resolve thành chuỗi rỗng/trắng, không nhất thiết kích hoạt giá trị mặc định. Vì vậy nên validate nếu dữ liệu cấu hình cần không rỗng.

Trong demo, Spring cung cấp `MapPropertySource` cho context thứ hai, tạo một key cấu hình rõ ràng mà không cần file `application.properties` hay phụ thuộc Spring Boot.

### 5.2. Có thể dùng factory method thay `@Value`

Một hướng khác là truyền `Environment` vào `@Bean` method rồi **gọi setter có chủ đích**:

~~~java
@Bean
ReportService reportService(ReportRepository repository,
                            Environment env) {
    ReportService service = new ReportService(repository);
    service.setPrefix(env.getProperty("app.report.prefix", "REPORT"));
    return service;
}
~~~

Đây là **đoạn minh họa alternative**, không phải một factory method bổ sung trong chương trình chính. Nếu dùng trong project thật, cần import `org.springframework.core.env.Environment` và các class liên quan.

Cách này rõ đường cấu hình trong một nơi, dễ kiểm soát giá trị mặc định và validation. Nó cũng cho phép giữ class nghiệp vụ **không import Spring annotation**. Đổi lại, configuration cần biết setter và cung cấp giá trị.

Khi một class có nhiều property, hãy tránh hàng chục setter rời rạc nếu có thể gom thành một **immutable configuration object** được validate và inject qua constructor.

## 6. Chương trình Java 17 / Spring Framework 6.2 chạy đầy đủ

Ví dụ cố ý tạo hai context độc lập:

- **Context mặc định:** có `ReportRepository` và `ReportService` nhưng **không có `AuditSink`** và không cung cấp property `app.report.prefix`. Service vẫn chạy, setter audit không được gọi; prefix mặc định là `REPORT`.
- **Context tùy chỉnh:** đăng ký thêm `AuditSink` và thiết lập property `app.report.prefix=CUSTOM` **trước `refresh()`**. Setter audit được Spring gọi; setter prefix nhận `CUSTOM`.

Không có HTTP, database hoặc network I/O. Audit chỉ in dòng console. Ví dụ dùng `spring-context`, JDK 17 và Maven; không cần Spring Boot.

### 6.1. Cấu trúc và Maven

~~~text
optional-setter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── OptionalSetterDemo.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>optional-setter-demo</artifactId>
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
                    <mainClass>demo.OptionalSetterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. File Java hoàn chỉnh

Lưu `src/main/java/demo/OptionalSetterDemo.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.MapPropertySource;

public final class OptionalSetterDemo {
    private OptionalSetterDemo() {}

    public interface ReportRepository {
        String find(String id);
    }

    public static final class DemoRepository implements ReportRepository {
        @Override
        public String find(String id) {
            return "ITEM(" + id + ")";
        }
    }

    public interface AuditSink {
        void record(String id);
    }

    public static final class ConsoleAuditSink implements AuditSink {
        @Override
        public void record(String id) {
            System.out.println("AUDIT " + id);
        }
    }

    public static final class ReportService {
        private final ReportRepository repository;
        private AuditSink auditSink;       // tùy chọn, mặc định vắng mặt
        private String prefix = "REPORT";  // mặc định luôn hợp lệ

        public ReportService(ReportRepository repository) {
            this.repository = Objects.requireNonNull(
                    repository, "repository");
        }

        @Autowired(required = false)
        public void setAuditSink(AuditSink auditSink) {
            this.auditSink = Objects.requireNonNull(
                    auditSink, "auditSink");
        }

        @Value("${app.report.prefix:REPORT}")
        public void setPrefix(String prefix) {
            if (prefix == null || prefix.isBlank()) {
                throw new IllegalArgumentException(
                        "report prefix must not be blank");
            }
            this.prefix = prefix;
        }

        public String render(String id) {
            String value = repository.find(id);
            if (auditSink != null) {
                auditSink.record(id);
            }
            return prefix + ":" + value;
        }

        public boolean hasAuditSink() {
            return auditSink != null;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BaseConfig {
        @Bean
        public ReportRepository reportRepository() {
            return new DemoRepository();
        }

        @Bean
        public ReportService reportService(ReportRepository repository) {
            return new ReportService(repository);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(BaseConfig.class)
    public static class WithAuditConfig {
        @Bean
        public AuditSink auditSink() {
            return new ConsoleAuditSink();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(BaseConfig.class)) {
            ReportService service = context.getBean(ReportService.class);
            System.out.println("-- default --");
            System.out.println("TEXT " + service.render("A1"));
            System.out.println("AUDIT_ENABLED " + service.hasAuditSink());
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo",
                            Map.of("app.report.prefix", "CUSTOM")));

            context.register(WithAuditConfig.class);
            context.refresh();

            ReportService service = context.getBean(ReportService.class);
            System.out.println("-- customized --");
            System.out.println("TEXT " + service.render("B2"));
            System.out.println("AUDIT_ENABLED " + service.hasAuditSink());
        }
    }
}
~~~

Dấu `@Autowired(required = false)` nằm **trên method setter**, không phải constructor. `@Value` được xử lý trên một setter khác. Cả hai bean `ReportService` đều được tạo bởi `@Bean` factory method, nên Spring vẫn áp dụng bean post-processors để xử lý các annotation của bean được quản lý.

### 6.3. Lệnh và stdout

Từ thư mục `optional-setter-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Nếu là lần đầu dùng Maven, các dependency có thể cần tải từ repository. **Những dòng do chương trình in ra stdout theo đúng thứ tự:**

~~~text
-- default --
TEXT REPORT:ITEM(A1)
AUDIT_ENABLED false
-- customized --
AUDIT B2
TEXT CUSTOM:ITEM(B2)
AUDIT_ENABLED true
~~~

`mvn -version` cùng Maven/plugin có thể in phiên bản và log riêng. Khối stdout mô tả **dòng được in từ logic `OptionalSetterDemo`**, không khẳng định terminal luôn chỉ có bảy dòng này.

### 6.4. Theo dõi cơ chế thật

1. `AnnotationConfigApplicationContext(BaseConfig.class)` tạo và refresh context đầu. Spring tạo `DemoRepository` và `ReportService`.
2. Constructor `ReportService(ReportRepository)` nhận repository bắt buộc, không tự tìm bean.
3. Không có bean `AuditSink` trong context đầu, nên injection method `@Autowired(required=false)` **bị bỏ qua**, trường `auditSink` vẫn `null`.
4. Không có key `app.report.prefix`, nên `@Value("${app.report.prefix:REPORT}")` dùng default `REPORT`; setter prefix được gọi.
5. `render("A1")` lấy `ITEM(A1)` từ repository, không gọi audit và trả `REPORT:ITEM(A1)`.
6. Context thứ hai thêm `MapPropertySource` với giá trị `CUSTOM` **trước** khi register/refresh. `@Import(BaseConfig.class)` đưa định nghĩa repository và service vào cùng context với bean `AuditSink`.
7. Spring có một bean `AuditSink` phù hợp, nên gọi `setAuditSink(ConsoleAuditSink)` khi cấu hình `ReportService`. Setter prefix nhận `CUSTOM`.
8. `render("B2")` gọi `auditSink.record("B2")`, in `AUDIT B2` **trước** khi `main` in `TEXT CUSTOM:ITEM(B2)`. Cuối cùng `hasAuditSink()` trả `true`.
9. Hai context độc lập: singleton `ReportService` của context này không được chia sẻ mặc định với context kia. `try-with-resources` đóng từng context.

**Điều đáng học:** cả hai lần, logic `render` không cần đổi. Thành phần tùy chọn và prefix được quyết định ở cách Spring lắp ráp/cấu hình bean.

## 7. XML property injection: một cách cấu hình setter khác

Một cấu hình XML có thể đưa giá trị vào setter JavaBeans:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="repository" class="demo.DemoRepository"/>

    <bean id="reportService" class="demo.ReportService">
        <constructor-arg ref="repository"/>
        <property name="prefix" value="REPORT"/>
    </bean>
</beans>
~~~

Đây là **XML minh họa**, không phải tệp XML chạy cùng ví dụ Java có nested classes ở mục 6. Khi dùng thực tế, thay `demo.DemoRepository` và `demo.ReportService` bằng tên class đầy đủ tồn tại trong project, hoặc tách class ra file riêng như thiết kế thông thường.

`<property name="prefix">` ánh xạ tới JavaBeans method `setPrefix(String)`. Nếu thêm:

~~~xml
<property name="auditSink" ref="auditSink"/>
~~~

thì cần đăng ký bean `auditSink` tương ứng để Spring truyền qua setter. Nếu property XML tham chiếu một bean không tồn tại, đó **không tự động là optional injection**: context có thể fail khi tạo bean. Vì thế cú pháp explicit `<property ref>` và `@Autowired(required=false)` khác nhau.

Với legacy XML, cũng có `autowire="byName"` hoặc `autowire="byType"` để tự nối một số property phù hợp. Các mode này có quy tắc riêng và có thể bị mơ hồ, nên không nên chọn chỉ để tránh viết cấu hình rõ ràng khi dependency quan trọng.

## 8. Vì sao không nên dùng setter cho mọi dependency?

### 8.1. Trạng thái chưa hoàn chỉnh

Nếu object nghiệp vụ yêu cầu repository nhưng chỉ khai báo:

~~~java
class BadReportService {
    private ReportRepository repository;

    public void setRepository(ReportRepository repository) {
        this.repository = repository;
    }

    public String render(String id) {
        return repository.find(id);
    }
}
~~~

Đây là đoạn minh họa với `ReportRepository` đã giả định có sẵn. `new BadReportService().render("A1")` sẽ ném `NullPointerException` vì repository chưa được set. Nếu dùng constructor có `Objects.requireNonNull`, thiếu dependency được phát hiện **ngay khi tạo service**, không bị dời sang lúc chạy nghiệp vụ.

Một setter “tùy chọn” phải thật sự có hành vi khi không được gọi; nếu không, đó thực chất là dependency bắt buộc đặt sai nơi.

### 8.2. Thay đổi runtime và concurrency

Bean singleton được nhiều caller dùng chung. Dù có setter public, **không nên tùy ý gọi setter sau khi bean đã phục vụ request** nếu nó thay đổi state không đồng bộ. Ví dụ một thread đang `render` mà thread khác `setPrefix` có thể quan sát cấu hình khác nhau; setter không tự tạo synchronization hay transaction.

Trong ứng dụng thường gặp, setter injection là **bước cấu hình ban đầu của container**, không phải lời mời thay cấu hình runtime không kiểm soát. Nếu cần hot reload, hãy dùng cơ chế quản lý state an toàn, rõ ràng hoặc immutable snapshot.

### 8.3. Không khắc phục vòng phụ thuộc bằng mọi giá

Setter injection trong một số tình huống có thể khiến container giải quyết một số chu kỳ dependency mà constructor injection không thể, nhưng **vòng phụ thuộc thường là dấu hiệu thiết kế cần xem xét**. Không nên cố thay constructor bằng setter chỉ để giấu một graph A↔B; cần tách trách nhiệm, áp dụng mediator/event hoặc thiết kế lại nơi sở hữu hành vi nếu phù hợp.

Spring cũng có nhiều quy tắc riêng về proxy, singleton đang tạo, circular references và Boot defaults. Không suy từ một ví dụ cũ rằng Spring hiện tại luôn giải quyết mọi vòng setter injection.

## 9. Hướng xử lý các tình huống tùy chọn khó hơn

| Tình huống | Lựa chọn phù hợp | Lưu ý |
| --- | --- | --- |
| Dependency không bắt buộc, có thì sử dụng | `@Autowired(required=false)` setter | Method bị bỏ qua khi không thỏa dependency |
| Muốn thể hiện option rõ trong constructor | `Optional<T>` | Không cần biến mọi dependency thành setter |
| Cần lấy dependency muộn hoặc theo nhu cầu | `ObjectProvider<T>` | Xác định semantics nếu thiếu/nhiều bean |
| Tham số cấu hình có default | `@Value("${key:default}")` hoặc `Environment.getProperty(key, default)` | Validate giá trị rỗng/không hợp lệ |
| Cấu hình nhiều trường liên quan | Bean config có validation, constructor injection | Giảm mutable setters rời rạc |
| Có nhiều bean cùng interface | `@Qualifier` hoặc `@Primary` | `required=false` không giải quyết mơ hồ |
| Cần một hành vi mặc định khi không có collaborator | Null Object hoặc điều kiện rõ | Không âm thầm che thiếu dependency bắt buộc |
| Chọn implementation tùy từng request | Strategy/router theo business data | Không dùng bean injection để thay quyết định runtime |
| Đổi cấu hình lúc đang phục vụ nhiều thread | Thiết kế snapshot/thread-safety rõ | Setter thông thường không giải quyết concurrency |

### Multi-argument optional method

~~~java
@Autowired(required = false)
public void configure(AuditSink audit, MetricsSink metrics) {
    this.audit = audit;
    this.metrics = metrics;
}
~~~

Đây là **minh họa**, `MetricsSink` và các field chưa được định nghĩa. Nếu thiếu một trong hai dependency, method non-required có thể **không được gọi hoàn toàn**. Nếu hai thứ có tính tùy chọn **độc lập**, nên chia thành hai injection point hoặc dùng `Optional<T>`/provider phù hợp, thay vì đặt vào cùng một setter rồi vô tình buộc chúng cùng xuất hiện.

### Tương tác với `@Bean` và annotation processing

`@Autowired`/`@Value` được áp dụng bởi `BeanPostProcessor`. `AnnotationConfigApplicationContext` đăng ký các annotation processors cần thiết trong cấu hình thông thường, bao gồm xử lý bean được tạo từ `@Bean` methods.

Tuy nhiên, nếu bạn **tự `new ReportService(repo)` ngoài Spring context**, những annotation setter **không tự chạy**. Cần tự gọi setter, hoặc đưa đối tượng vào quy trình quản lý/cấu hình bean một cách rõ ràng. `@Autowired` không phải một cú pháp được JVM tự thực thi khi gọi constructor.

Trong những bean thuộc loại `BeanFactoryPostProcessor` hoặc `BeanPostProcessor` của chính bạn, không nên mặc định có thể áp dụng injection annotation như trên các bean nghiệp vụ thông thường: các đối tượng tham gia xử lý post-processing được dựng ở giai đoạn đặc biệt và có những hạn chế cần cấu hình rõ.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân / hướng xử lý |
| --- | --- |
| Setter `@Autowired` không chạy | Thiếu bean phù hợp; `required=false` khiến Spring bỏ qua method |
| Setter chạy nhưng code vẫn dùng null | Kiểm tra field thực sự được gán, null guard và lifecycle của bean |
| Thiếu bean nhưng context vẫn khởi động | Đây có thể là hành vi đúng nếu dependency thật sự optional |
| Dependency bắt buộc không có mà service vẫn được tạo | Thiết kế sai ranh giới; chuyển dependency sang constructor |
| Có 2 bean cùng kiểu optional và context lỗi | Phân giải mơ hồ bằng qualifier/primary; optional không đồng nghĩa chọn bừa |
| `@Value` không lấy default như mong đợi | Key có thể tồn tại nhưng rỗng; kiểm tra property sources và validation |
| Property vừa được thêm nhưng đã refresh context | Thêm/cấu hình nguồn property trước bước bean creation nếu muốn ảnh hưởng setter |
| Setter `@Value` không chạy trên object tự tạo bằng `new` | Annotation được Spring xử lý với bean managed, không phải bởi Java trực tiếp |
| XML có `<property ref>` nhưng thiếu bean tham chiếu | Explicit ref bắt buộc bean name hợp lệ; không tương đương setter optional |
| `@Autowired(required=false)` trên method nhiều tham số bỏ qua tất cả | Một tham số không giải quyết được có thể khiến method không được gọi |
| Bean singleton thay cấu hình giữa runtime bị race | Cần thiết kế concurrency/hot-reload riêng |
| Gắn setter injection để chữa mọi vòng phụ thuộc | Đánh giá lại kiến trúc dependency graph |
| Kỳ vọng Spring tạo HTTP/transaction từ setter annotation | DI không tự bổ sung web server hoặc transaction manager |

**Quy trình debug:** xác nhận class thực sự là Spring-managed bean → annotation processor được đăng ký → đúng setter signature → bean candidate/property key có tồn tại → có nhiều candidate không → kiểm tra default khi injection bị bỏ qua → xác minh lỗi gốc trong stack trace.

## 11. Bài tập tự luyện có đáp án

**Bài 1.** `ReportRepository` là bắt buộc, `AuditSink` chỉ để ghi trace. Nên inject chúng bằng cách nào?

**Đáp án:** Repository qua constructor injection; audit có thể qua setter `@Autowired(required=false)` với hành vi an toàn khi vắng mặt. Nếu audit thực ra bắt buộc về tuân thủ, không nên đánh dấu optional.

**Bài 2.** Vì sao context không có `AuditSink` vẫn render được?

**Đáp án:** Spring bỏ qua setter `@Autowired(required=false)`, `auditSink` giữ giá trị `null`; `render` kiểm tra trước khi gọi audit. Constructor vẫn nhận repository đầy đủ.

**Bài 3.** Context thứ hai in `AUDIT B2` trước `TEXT CUSTOM:ITEM(B2)` vì sao?

**Đáp án:** `render` gọi `auditSink.record` trong khi tính kết quả, sau đó trả chuỗi cho `main` in. Các dòng không phải do Spring tự in log.

**Bài 4.** Nếu có hai bean `AuditSink` cùng type, `required=false` có tự chọn một không?

**Đáp án:** Không. Cần quy tắc chọn rõ bằng `@Primary`/`@Qualifier` hoặc thiết kế injection nhiều bean có chủ đích.

**Bài 5.** `@Value("${app.report.prefix:REPORT}")` có tương đương “đọc property hoặc dùng REPORT nếu giá trị là khoảng trắng” không?

**Đáp án:** Không. Default chủ yếu dùng khi property không tìm thấy; một giá trị đã cung cấp nhưng blank có thể cần tự từ chối hoặc chuẩn hóa. Setter ở demo ném lỗi nếu blank.

**Bài 6.** Nếu khai báo method optional có hai tham số và chỉ có một bean tương ứng, method sẽ nhận null cho tham số còn lại?

**Đáp án:** Không nên giả định như vậy. Với method `@Autowired(required=false)`, nếu một parameter không có dependency, method có thể bị bỏ qua toàn bộ. Có thể dùng `Optional<T>` ở từng tham số để thể hiện độc lập.

**Bài 7.** Unit test `ReportService` không cần context được không?

**Đáp án:** Có. Dựng một fake `ReportRepository`, gọi constructor; nếu cần thì gọi `setAuditSink` và `setPrefix` thủ công, sau đó assert `render` và các lời gọi fake. Annotation không bắt buộc để Java method setter chạy.

**Bài 8.** Vì sao không nên thay `ReportRepository` bằng một setter optional để “linh hoạt hơn”?

**Đáp án:** Vì service không thể render khi thiếu repository. Constructor biến dependency bắt buộc thành điều kiện tạo object hợp lệ, phát hiện lỗi sớm hơn.

## 12. Checklist áp dụng thực tế

- [ ] Mỗi dependency được phân loại rõ: **bắt buộc** hay **tùy chọn**.
- [ ] Dependency bắt buộc được inject qua constructor, không để service vào trạng thái thiếu điều kiện hoạt động.
- [ ] Setter optional có default hoặc nhánh xử lý vắng mặt rõ ràng.
- [ ] `@Autowired(required=false)` được đặt đúng trên setter và hiểu rằng method có thể bị bỏ qua.
- [ ] Với method nhiều tham số, kiểm tra semantics `required=false` áp dụng cho toàn method.
- [ ] Không dùng `required=false` để giải quyết lỗi nhiều bean cùng type hoặc lỗi tạo bean.
- [ ] `@Value` placeholder có default đúng cú pháp và giá trị được validate khi cần.
- [ ] Đặt property sources trước `refresh()` hoặc trước khi bean cần được khởi tạo.
- [ ] Hiểu difference giữa setter được gọi trong `@Bean`, annotation autowiring và XML property.
- [ ] Không trộn một setter cấu hình nhiều nguồn (XML, annotation, manual) nếu thứ tự ưu tiên không rõ.
- [ ] Unit test service với/không có optional collaborator; integration test cả hai profile/configurations.
- [ ] Khi service singleton chạy đa luồng, tránh chỉnh mutable settings tùy tiện giữa runtime.
- [ ] Đừng biến mọi dependency thành optional chỉ để context không fail.
- [ ] Xác nhận output của chương trình và phân biệt với log Maven.
- [ ] Đóng `ApplicationContext` đúng vòng đời và không trông chờ injection trên object ngoài container.

### Đọc thêm trong tài liệu Spring

- [Setter-based Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Using @Autowired và required=false](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)

**Kết luận:** Setter injection có giá trị khi cấu hình hoặc collaborator **thực sự tùy chọn** và object vẫn hoạt động đúng khi setter không được gọi. `@Autowired(required=false)` biểu đạt khả năng bỏ qua injection, `@Value` giúp áp dụng property có default, trong khi constructor injection giữ các dependency bắt buộc rõ ràng. Sự tách bạch đó khiến bean hợp lệ ngay từ lúc tạo nhưng vẫn linh hoạt ở những điểm cấu hình hợp lý.