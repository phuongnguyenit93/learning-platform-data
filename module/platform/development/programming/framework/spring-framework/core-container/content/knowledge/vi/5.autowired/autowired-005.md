# Ý nghĩa `required` và thời điểm phụ thuộc được giải quyết trong `@Autowired`

## 1. Câu hỏi trung tâm

Khi Spring Core Container tạo một bean, nó có thể phải tìm các bean khác để tiêm vào constructor, field hoặc phương thức cấu hình. Hai điều cần phân biệt là:

1. **Dependency có bắt buộc không?** Thuộc tính `required` của `@Autowired` ảnh hưởng đến việc Spring có chấp nhận một injection point không có dependency phù hợp hay không.
2. **Spring giải quyết dependency ở thời điểm nào?** Thời điểm này phụ thuộc vào quá trình **tạo bean**, scope, lazy initialization, loại injection point và các cơ chế trì hoãn được khai báo — không đồng nghĩa với mỗi lần business method được gọi.

Quy tắc chung:

~~~java
@Autowired
public void configure(Repository repository) {
    this.repository = repository;
}
~~~

`@Autowired` mặc định tương đương `@Autowired(required = true)`. Spring tìm bean `Repository` thỏa dependency rồi gọi method trong quá trình cấu hình bean. Nếu dependency bắt buộc không thể giải quyết, quá trình tạo bean **thường thất bại**.

Còn:

~~~java
@Autowired(required = false)
public void setAuditSink(AuditSink auditSink) {
    this.auditSink = auditSink;
}
~~~

cho phép Spring **bỏ qua lời gọi setter** nếu không có bean phù hợp, để trạng thái mặc định của đối tượng tiếp tục có hiệu lực. Đây là ví dụ **minh họa**; toàn bộ kiểu Java và cấu hình chạy được nằm ở mục 6.

~~~text
Đăng ký BeanDefinition
        |
ApplicationContext.refresh()
        |
        +-- các singleton non-lazy: thường tạo ở startup
        |        |
        |        +-- chọn constructor / giải quyết constructor args
        |        +-- gọi constructor hoặc factory method
        |        +-- resolve @Autowired fields/methods
        |        +-- chạy init callbacks thích hợp
        |
        +-- lazy singleton: trì hoãn nếu không bị bean eager khác yêu cầu
        |
        +-- prototype: thường tạo/tiêm khi container được yêu cầu cấp instance
        |
getBean(...) -> lấy managed bean, hoặc kích hoạt tạo nếu chưa có
        |
gọi method nghiệp vụ -> dùng dependency đã tiêm
~~~

Bài này tập trung vào Spring Framework 6.x / Java 17+, giúp bạn giải thích chính xác lỗi thiếu bean, không nhầm `required=false` với việc đưa `null` tùy tiện, và không hiểu sai thời điểm injection.

## 2. `required=true`: dependency tại injection point là điều kiện bắt buộc

### 2.1. Giá trị mặc định

Annotation khai báo:

~~~java
@Autowired
private PaymentGateway gateway;
~~~

nghĩa là Spring phải tìm cách giải quyết field `PaymentGateway` khi cấu hình managed bean. Nếu không tìm được ứng viên phù hợp, lỗi thiếu dependency có thể xuất hiện ở thời điểm bean được tạo, ví dụ `UnsatisfiedDependencyException` với nguyên nhân thiếu bean.

Viết:

~~~java
@Autowired(required = true)
private PaymentGateway gateway;
~~~

về mặt yêu cầu bắt buộc tương đương với cách viết không chỉ định thuộc tính. Hai khối chỉ minh họa; `PaymentGateway` và class chứa field cần được định nghĩa thêm để biên dịch riêng.

**Bắt buộc** ở đây không có nghĩa “Spring chắc chắn tìm được một bean” mà là “nếu không đáp ứng điều kiện injection, bean đang tạo không thể hoàn tất bình thường”. Cần cả đăng ký bean và khả năng lựa chọn một ứng viên thích hợp.

### 2.2. Có bean nhưng không phân giải được vẫn lỗi

Spring giải quyết một dependency đơn theo type, sau đó có thể xét `@Qualifier`, `@Primary`, tên tham số và những quy tắc lựa chọn khác khi thích hợp. Các tình huống thường gặp:

| Tình huống | Hành vi thường gặp |
| --- | --- |
| Có đúng một bean phù hợp | Inject bean đó |
| Không có bean phù hợp, injection bắt buộc | Bean creation thất bại |
| Hai bean cùng type, không phân giải duy nhất | Có thể gặp `NoUniqueBeanDefinitionException` |
| Bean cần inject tồn tại nhưng constructor/factory ném lỗi | Bean creation thất bại theo lỗi gốc |
| Có bean, nhưng không tương thích qualifier cần thiết | Không có ứng viên phù hợp với injection point |
| Có vòng phụ thuộc constructor không giải quyết được | Bean graph không được tạo hoàn chỉnh |

`@Autowired(required=true)` không tự khắc phục tình huống có nhiều ứng viên hoặc vòng phụ thuộc. Đây là vấn đề **bean graph và metadata lựa chọn**, không phải vấn đề annotation bị viết thiếu chữ.

### 2.3. Lỗi có thể đến trước `getBean`

Một `ApplicationContext` mặc định thường **pre-instantiate singleton beans không lazy** trong `refresh()`. Nếu bean A có field `@Autowired` bắt buộc nhưng thiếu dependency B, context có thể fail **ngay khi khởi động**, trước khi bạn gọi `context.getBean(A.class)`.

Do đó câu “Spring chỉ tìm dependency khi gọi `getBean`” là **không chính xác** đối với tất cả trường hợp. Nó có thể đúng với một bean lazy chưa bị bean khác yêu cầu, hoặc prototype được yêu cầu sau này, nhưng không phải quy tắc chung.

## 3. `required=false` trên field và method có nghĩa khác gì?

### 3.1. Field optional

~~~java
private AuditSink audit = AuditSink.NO_OP;

@Autowired(required = false)
private AuditSink injectedAudit;
~~~

Đây chỉ là **minh họa**: `AuditSink.NO_OP` chưa định nghĩa. Field `injectedAudit` được phép không được inject khi không có candidate. Nếu không có bean phù hợp, Spring thường để field **nguyên trạng mặc định**; nó không nhất thiết “gọi setter với null”, vì trường hợp này không có setter.

Nếu code dùng `injectedAudit.record(...)` vô điều kiện trong khi field vẫn null, bạn vẫn có thể gặp `NullPointerException`. Đánh dấu optional là một **quyết định thiết kế**, phải có hành vi khi dependency vắng mặt.

Nếu muốn default an toàn, có thể tạo Null Object:

~~~java
private AuditSink audit = id -> { /* Không làm gì */ };

@Autowired(required = false)
public void setAudit(AuditSink audit) {
    this.audit = java.util.Objects.requireNonNull(audit);
}
~~~

Khi Spring không tìm được `AuditSink` thì setter không chạy và field `audit` tiếp tục giữ no-op implementation. Khi có bean, setter thay implementation mặc định. Trong project thực tế, cần tự định nghĩa `AuditSink` là functional interface phù hợp.

### 3.2. Phương thức optional: bỏ qua **toàn bộ** lời gọi

Giả sử:

~~~java
@Autowired(required = false)
public void configureMonitoring(AuditSink audit,
                                MetricSink metrics) {
    this.audit = audit;
    this.metrics = metrics;
    this.monitoringEnabled = true;
}
~~~

Đây là trích đoạn minh họa; file chương trình chính ở mục 6 dùng một setter có một tham số để dễ quan sát. Với một method nhận **hai** tham số như đoạn trên, `required=false` áp dụng cho **cả injection point**:

- Có đủ hai dependency thích hợp: Spring có thể gọi method với cả hai.
- Thiếu một dependency: Spring **bỏ qua cả method**, chứ không tự gọi “nửa method” hoặc truyền `null` vào parameter thiếu.
- Field `monitoringEnabled` tiếp tục giữ default ban đầu nếu method bị bỏ qua.

Đây là một lý do không nên gom các option **độc lập** vào cùng một method `required=false`. Nếu audit và metrics có thể được bật độc lập, dùng hai setter optional riêng hoặc tham số `Optional<T>` phù hợp.

### 3.3. Optional **không** có nghĩa nuốt mọi lỗi

`required=false` không phải bộ xử lý exception:

- Nếu một bean candidate có tồn tại nhưng quá trình khởi tạo bean ấy ném exception, lỗi có thể khiến context không tạo được bean.
- Nếu method optional được gọi và body method ném `IllegalArgumentException`, lỗi đó không bị Spring bỏ qua đơn giản vì annotation là non-required.
- Nếu có nhiều candidates và không thể chọn duy nhất, đó là lỗi lựa chọn ứng viên, không phải tình huống “không cần bean nào cả”.
- Một dependency khác ngoài injection point optional có thể vẫn là bắt buộc.

Vì thế không nên sửa mọi `UnsatisfiedDependencyException` bằng `required=false`. Cần xác định dependency thật sự có thể vắng mặt mà object vẫn hoạt động đúng hay không.

## 4. `required` trên constructor: cần hiểu quy tắc lựa chọn

### 4.1. Chỉ một constructor: không cần `@Autowired`

Từ Spring Framework 4.3 trở đi, một managed bean class chỉ có **một constructor** thường không cần ghi `@Autowired` trên constructor đó:

~~~java
public final class ReportService {
    private final Repository repository;

    public ReportService(Repository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }
}
~~~

Đây là đoạn minh họa; bean `Repository` phải có sẵn. Nếu Spring trực tiếp khởi tạo `ReportService` từ bean definition, nó có thể chọn constructor duy nhất rồi resolve `Repository`. **Không gắn annotation không có nghĩa dependency trở thành tùy chọn.**

### 4.2. Nhiều constructor

Với một class có nhiều constructor, `@Autowired` giúp Spring xác định candidates. Không thể tùy tiện gắn `@Autowired(required=true)` lên nhiều constructor khác nhau và kỳ vọng Spring tự chọn:

- Mặc định, **chỉ một constructor** trong class có thể được đánh dấu `@Autowired(required=true)`.
- Với nhiều constructor được đánh dấu `@Autowired(required=false)`, Spring có thể xét các candidates theo khả năng thỏa argument và chọn constructor phù hợp nhất theo quy tắc.
- Nếu không constructor có annotation nào được thỏa và có constructor không tham số, constructor mặc định có thể làm fallback trong những điều kiện được Spring hỗ trợ.
- Có những quy tắc suy luận constructor đặc biệt cho bean definitions và Java records; đừng coi “Spring luôn chọn constructor dài nhất” là định luật áp dụng mọi class.

**Quan trọng:** `@Autowired(required=false)` đặt trên constructor không có nghĩa Spring tự truyền null vào bất cứ argument thiếu nào. Nó ảnh hưởng **cách đánh giá constructor candidates**, khác với setter method non-required bị bỏ qua khi thiếu dependency.

### 4.3. Dependency bắt buộc nên hiện rõ

Nếu service cần repository để hoạt động, hãy dùng constructor nhận repository và không tạo một constructor no-arg chỉ để tránh lỗi startup. Object không có dependency bắt buộc sẽ tồn tại nhưng có thể ném lỗi khi business method chạy — thường còn khó debug hơn.

Nếu dependency thật sự tùy chọn, cân nhắc `Optional<T>`, `@Nullable` phù hợp, provider hoặc setter optional thay vì làm class hợp lệ trong trạng thái thiếu invariant.

## 5. Tùy chọn theo **tham số** thay vì cả method

### 5.1. `Optional<T>`

Ví dụ:

~~~java
@Autowired
public void configure(Repository repository,
                      java.util.Optional<AuditSink> audit) {
    this.repository = repository;
    this.audit = audit.orElse(null);
}
~~~

Đây là snippet cần field/type tương ứng nếu muốn biên dịch. Khi repository có sẵn mà `AuditSink` không có, Spring có thể truyền `Optional.empty()` cho tham số audit và **vẫn gọi method**, khác với `@Autowired(required=false)` áp dụng lên toàn method nhiều tham số.

| Cấu hình injection | Thiếu audit | Có audit |
| --- | --- | --- |
| `@Autowired(required=false) setAudit(AuditSink)` | Không gọi setter | Gọi setter |
| `@Autowired(required=false) configure(Repository, AuditSink)` | Bỏ qua toàn method | Gọi nếu mọi tham số thỏa |
| `@Autowired configure(Repository, Optional<AuditSink>)` | Gọi với `Optional.empty()` nếu repo có | Gọi với `Optional.of(bean)` |
| Constructor `Service(Repository, Optional<AuditSink>)` | Constructor vẫn có thể được gọi, audit rỗng | Constructor nhận audit hiện có |

`Optional<T>` mô tả điều kiện **theo từng tham số**, trong khi `required` là thuộc tính **của annotation injection point**.

### 5.2. `@Nullable`

Khi annotation nullability được Spring nhận biết ở phiên bản và package phù hợp, một dependency parameter có thể được phép nhận null. **Không phải mọi annotation có chữ Nullable từ bất kỳ thư viện nào đều mặc nhiên tương đương**; dự án cần dùng đúng annotation mà Spring 6.x hỗ trợ. Đối với người mới học, `Optional<T>` thường giúp ý nghĩa rõ hơn so với dựa vào null.

### 5.3. `ObjectProvider<T>`

Nếu collaborator cần được giải quyết **lúc xử lý**, có thể inject Spring `ObjectProvider<T>` rồi gọi `getObject()` hoặc `getIfAvailable()` trong những tình huống thích hợp:

~~~java
public final class ExportService {
    private final org.springframework.beans.factory.ObjectProvider<Exporter>
            exporters;

    public ExportService(
            org.springframework.beans.factory.ObjectProvider<Exporter>
                    exporters) {
        this.exporters = exporters;
    }

    public void export() {
        Exporter exporter = exporters.getIfAvailable();
        if (exporter != null) {
            exporter.run();
        }
    }
}
~~~

Đây là **minh họa** chưa định nghĩa `Exporter`. `ObjectProvider` cho phép trì hoãn **lần lookup cụ thể**, nhưng không miễn trừ mọi lỗi do nhiều ứng viên mơ hồ hoặc factory candidate gặp lỗi. Với scope prototype, lookup từ provider có thể tạo instance mới theo mỗi yêu cầu.

Nếu nghiệp vụ cần hoàn toàn độc lập với Spring, một interface `ExporterFactory` hoặc `Supplier<Exporter>` được injected thường giữ ranh giới dependency sạch hơn.

## 6. Ví dụ Spring Framework 6.2 / Java 17: quan sát required và timing

Chương trình console hoàn chỉnh dùng hai context độc lập:

- **Context thứ nhất** có `TicketStore` nhưng **không có `AuditSink`**. Service có constructor `TicketStore` bắt buộc và setter `@Autowired(required=false)` cho audit; setter bị bỏ qua. Một singleton `@Lazy` chưa được tạo sau refresh; khi gọi `getBean(LazySummary.class)` thì Spring tạo nó.
- **Context thứ hai** có cả `TicketStore` và `AuditSink`. Setter audit được gọi trong quá trình tạo service, và method nghiệp vụ ghi audit trước khi trả kết quả.

Ứng dụng không dùng Spring Boot, HTTP server, database hoặc AOP. Nó minh họa **các thời điểm mà bạn có thể quan sát được**, không hứa mọi singleton không liên quan khởi tạo theo thứ tự trong source code.

### 6.1. Yêu cầu và cấu trúc thư mục

Cần **JDK 17+**, Apache Maven. Maven có thể tải dependencies khi chạy lần đầu.

~~~text
required-timing-demo/
├── pom.xml
└── src/main/java/demo/RequiredTimingDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>required-timing-demo</artifactId>
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
                    <mainClass>demo.RequiredTimingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. File Java đầy đủ

Tạo `src/main/java/demo/RequiredTimingDemo.java`:

~~~java
package demo;

import java.util.Objects;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Lazy;

public final class RequiredTimingDemo {
    private RequiredTimingDemo() {}

    public interface TicketStore {
        String find(String id);
    }

    public static final class MemoryTicketStore implements TicketStore {
        @Override
        public String find(String id) {
            return "TICKET(" + id + ")";
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

    public static final class TicketService {
        private final TicketStore store;  // Bắt buộc
        private AuditSink audit;          // Tùy chọn
        private boolean auditSetterCalled;

        public TicketService(TicketStore store) {
            this.store = Objects.requireNonNull(store, "store");
        }

        @Autowired(required = false)
        public void setAudit(AuditSink audit) {
            this.audit = Objects.requireNonNull(audit, "audit");
            this.auditSetterCalled = true;
        }

        public boolean auditConfigured() {
            return auditSetterCalled;
        }

        public String process(String id) {
            String ticket = store.find(id);
            if (audit != null) {
                audit.record(id);
            }
            return "DONE " + ticket;
        }
    }

    public static final class LazySummary {
        private final TicketStore store;

        public LazySummary(TicketStore store) {
            this.store = Objects.requireNonNull(store);
        }

        public String summarize(String id) {
            return "SUMMARY " + store.find(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CoreConfig {
        @Bean
        public TicketStore ticketStore() {
            return new MemoryTicketStore();
        }

        @Bean
        public TicketService ticketService(TicketStore store) {
            return new TicketService(store);
        }

        @Bean
        @Lazy
        public LazySummary lazySummary(TicketStore store) {
            System.out.println("CREATE lazy-summary");
            return new LazySummary(store);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CoreConfig.class)
    public static class WithAuditConfig {
        @Bean
        public AuditSink auditSink() {
            return new ConsoleAuditSink();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            System.out.println("-- without audit --");
            System.out.println("LAZY_READY "
                    + context.getBeanFactory()
                             .containsSingleton("lazySummary"));

            TicketService service = context.getBean(TicketService.class);
            System.out.println("AUDIT_SET " + service.auditConfigured());
            System.out.println("RESULT " + service.process("A1"));

            LazySummary lazy = context.getBean(LazySummary.class);
            System.out.println(lazy.summarize("A1"));
            System.out.println("LAZY_READY "
                    + context.getBeanFactory()
                             .containsSingleton("lazySummary"));
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             WithAuditConfig.class)) {
            System.out.println("-- with audit --");
            TicketService service = context.getBean(TicketService.class);
            System.out.println("AUDIT_SET " + service.auditConfigured());
            System.out.println("RESULT " + service.process("B2"));
        }
    }
}
~~~

Không có `@Autowired` trên constructor của `TicketService` vì nó chỉ có một constructor, nhưng chương trình còn sử dụng **`@Bean ticketService(TicketStore)`**: chính Spring inject tham số vào factory method; body factory gọi Java constructor. Điều đó vẫn cho dependency bắt buộc, nhưng không nên nhầm với Spring trực tiếp suy luận constructor của service class.

### 6.3. Biên dịch, chạy và stdout

Mở terminal tại thư mục `required-timing-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Các dòng do chương trình in qua `System.out.println` theo đúng thứ tự:**

~~~text
-- without audit --
LAZY_READY false
AUDIT_SET false
RESULT DONE TICKET(A1)
CREATE lazy-summary
SUMMARY TICKET(A1)
LAZY_READY true
-- with audit --
AUDIT_SET true
AUDIT B2
RESULT DONE TICKET(B2)
~~~

`mvn -version` in phiên bản Maven/JDK; Maven và Spring cũng có thể có log khác tùy môi trường. Khối trên chỉ ghi các dòng **do Java code chủ động in**, không khẳng định toàn bộ terminal chỉ gồm từng ấy dòng.

### 6.4. Truy vết thời điểm Spring giải quyết dependency

**Context không có audit:**

1. `AnnotationConfigApplicationContext(CoreConfig.class)` đăng ký config và **refresh** context. Những singleton non-lazy, trong đó có `TicketStore` và `TicketService`, thường đã được tạo trước khi constructor này trả về.
2. Khi tạo `ticketService`, Spring phải resolve tham số `TicketStore` của `@Bean` factory method. Đây là dependency **bắt buộc**; nếu thiếu, startup không thể hoàn tất như demo.
3. Bean `TicketService` được tạo, sau đó Spring xử lý setter `@Autowired(required=false)`. Không có bean `AuditSink`, nên setter **không được gọi**, cờ `auditSetterCalled` giữ `false`.
4. Bean `LazySummary` khai báo `@Lazy` và không bị một bean eager khác yêu cầu; sau refresh, `containsSingleton("lazySummary")` là `false`.
5. `getBean(TicketService.class)` trả service đã cấu hình. `process("A1")` chỉ dùng dependency đã được tiêm và không làm Spring chạy lại setter. Nó in `RESULT DONE TICKET(A1)`.
6. Khi `getBean(LazySummary.class)`, Spring phải tạo lazy bean. Factory method in `CREATE lazy-summary`, rồi Spring trả object. Lệnh `summarize("A1")` trả `SUMMARY TICKET(A1)`.
7. Từ đây singleton `lazySummary` đã tồn tại, nên `containsSingleton("lazySummary")` trả `true`.

**Context có audit:**

1. `WithAuditConfig` import `CoreConfig` và đăng ký thêm bean `AuditSink`. Spring có thể resolve cả repository và audit khi cấu hình `TicketService`.
2. Setter `setAudit(AuditSink)` được gọi trong bean creation; `auditSetterCalled` trở thành `true` **trước khi** `main` gọi `getBean(TicketService.class)`.
3. `process("B2")` gọi `audit.record("B2")`, in `AUDIT B2`, rồi trả `DONE TICKET(B2)` cho `main` in.
4. Mỗi context có bộ singleton riêng. Không suy từ hai lần chạy rằng Spring giữ một global singleton cho toàn JVM.

**Không có stdout về thời điểm tạo ticketStore/ticketService**, vì constructor/factory chúng không in gì. Như vậy output có ý nghĩa ổn định, không dựa vào thứ tự Spring tạo các singleton không liên quan.

## 7. Eager, lazy, prototype: “lúc nào” phải phụ thuộc loại bean

| Kiểu bean | Thời điểm Spring thường tạo và resolve dependency |
| --- | --- |
| Singleton non-lazy | Khi ApplicationContext refresh/pre-instantiation (nếu không có điều kiện khác làm trì hoãn) |
| Singleton `@Lazy` | Lần được yêu cầu đầu tiên, trừ khi dependency eager khác buộc phải tạo sớm |
| Prototype | Mỗi lần container được yêu cầu cấp prototype instance, theo cơ chế scope |
| Request/session scoped | Khi scope web hợp lệ có yêu cầu tương ứng; cần web-aware context |
| Bean được tạo bằng `new` ngoài Spring | Spring không tự xử lý `@Autowired` của instance đó |
| `ObjectProvider<T>` injection | Provider có thể được cấp trước; dependency đích được lookup khi provider được dùng |
| Proxy do `@Lazy` tại injection point | Proxy có thể được inject trước; target được tìm khi proxy cần giải quyết target |

### 7.1. `@Lazy` trên bean definition có thể bị dependency eager đánh thức

Ví dụ:

~~~java
@Bean
@Lazy
ExternalClient externalClient() {
    return new ExternalClient();
}

@Bean
EagerService eagerService(ExternalClient client) {
    return new EagerService(client);
}
~~~

Đây là **minh họa**, `ExternalClient` và `EagerService` cần định nghĩa. Nếu Spring cần tạo `eagerService` trong startup, nó phải resolve tham số client. Kết quả: **`externalClient` có thể được tạo trong startup dù có `@Lazy`**.

Vì vậy câu “mọi bean đánh dấu lazy chỉ được tạo khi lần đầu `getBean` đúng tên bean đó” là sai.

### 7.2. `@Lazy` tại injection point có thể tạo proxy

Trong những tình huống Spring hỗ trợ, đặt `@Lazy` tại tham số/field injection có thể tạo **proxy trì hoãn resolution**:

~~~java
public EagerService(@Lazy ExternalClient client) {
    this.client = client;
}
~~~

Đây là snippet minh họa. Object được inject có thể là proxy, còn việc xác định và tạo target thật có thể dời tới lần dùng đầu. Tuy nhiên:

- Không phải mọi class/method có thể được proxy như nhau (nhất là `final` class/method và lựa chọn proxy).
- Lỗi missing bean có thể dời sang runtime use của proxy.
- Không nhầm “constructor đã nhận một proxy” với “constructor thật sự không nhận dependency nào”.
- Đừng tùy tiện đánh dấu toàn bộ injection points là lazy để che vòng dependency.

### 7.3. Prototype được inject vào singleton

Nếu một bean prototype được inject **trực tiếp** vào singleton qua constructor, việc lấy prototype thường diễn ra **khi singleton được tạo**. Singleton giữ reference ấy; nó **không tự nhận prototype mới mỗi lần method nghiệp vụ chạy**.

Muốn một instance prototype cho mỗi tác vụ, sử dụng `ObjectProvider<T>`, scoped proxy thích hợp hoặc một injected factory với hợp đồng rõ ràng. Prototype cũng có vòng đời dọn dẹp khác singleton: Spring không tự chạy mọi destruction callback khi context đóng cho từng prototype đã cấp.

### 7.4. Khi nào “dependency đã được giải quyết” thực sự xảy ra?

Có thể tách bốn thời điểm:

1. **Đăng ký bean definitions**: Spring biết có bean nào và metadata nào. Chưa đồng nghĩa object đã tồn tại.
2. **Tạo instance**: chọn constructor/factory, resolve những dependency cần ngay để gọi constructor/factory.
3. **Populate/inject properties**: xử lý `@Autowired` field và method, property values cùng các bước lifecycle liên quan.
4. **Business method execution**: người dùng gọi hành vi trên object đã sẵn sàng. Dependency cố định thường chỉ được **sử dụng**, không được tự động lookup lại.

Những thứ như proxy, provider, prototype factory có thể thay đổi hoặc trì hoãn một phần resolution, nhưng nên được coi là **cấu hình riêng**, không làm mất quy tắc mặc định.

## 8. Một ví dụ Java 17 thuần để phân biệt injection với lookup động

Không cần Spring để hiểu rằng một dependency đã được cấp qua constructor sẽ được giữ lại ở field.

Tạo file `PlainRequiredDemo.java` tại thư mục làm việc độc lập:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class PlainRequiredDemo {
    interface Formatter {
        String format(String value);
    }

    static class Service {
        private final Formatter formatter;

        Service(Formatter formatter) {
            this.formatter = Objects.requireNonNull(formatter);
        }

        String run(String value) {
            return formatter.format(value);
        }
    }

    static class DynamicService {
        private final Supplier<Formatter> provider;

        DynamicService(Supplier<Formatter> provider) {
            this.provider = Objects.requireNonNull(provider);
        }

        String run(String value) {
            return provider.get().format(value);
        }
    }

    public static void main(String[] args) {
        Formatter fixed = value -> "FIXED:" + value;
        Service service = new Service(fixed);
        System.out.println(service.run("A"));
        System.out.println(service.run("B"));

        int[] calls = {0};
        DynamicService dynamic = new DynamicService(() -> {
            calls[0]++;
            return value -> "DYNAMIC:" + value;
        });
        System.out.println(dynamic.run("C"));
        System.out.println(dynamic.run("D"));
        System.out.println("LOOKUPS " + calls[0]);
    }
}
~~~

Biên dịch và chạy với **JDK 17+** (không cần Spring):

~~~bash
javac --release 17 -encoding UTF-8 PlainRequiredDemo.java
java PlainRequiredDemo
~~~

Stdout chính xác:

~~~text
FIXED:A
FIXED:B
DYNAMIC:C
DYNAMIC:D
LOOKUPS 2
~~~

Trong `Service`, dependency `fixed` đã được truyền vào constructor một lần. Hai lời gọi `run` **không gọi lại nơi cung cấp formatter**. Ngược lại, `DynamicService` gọi `provider.get()` mỗi lần run, vì code của chúng ta **thiết kế rõ** như vậy.

Đây là analog thuần Java giúp hiểu `ObjectProvider` hoặc factory abstraction trong Spring: lookup theo nhu cầu là một lựa chọn API, **không phải mặc định của mọi lần gọi method trên một managed bean**.

## 9. Xử lý thiếu bean đúng cách, không che vấn đề

### 9.1. Dependency thật sự bắt buộc

Giả sử `TicketService` không thể làm việc khi thiếu `TicketStore`. Nên để constructor hoặc `@Bean` factory method yêu cầu bean ấy. Nếu không có, startup thất bại sớm đối với eager singleton là tín hiệu cấu hình sai cần sửa.

Không chuyển sang:

~~~java
@Autowired(required = false)
public void setStore(TicketStore store) {
    this.store = store;
}
~~~

rồi dùng `store.find(...)` vô điều kiện nếu setter không chạy. Điều này chỉ **dời lỗi** tới thời điểm nghiệp vụ, không giải quyết dependency bắt buộc.

### 9.2. Dependency thật sự tùy chọn

Audit, telemetry, tracing hoặc một tối ưu cache phụ trợ có thể không ảnh hưởng chức năng chính. Có thể dùng setter optional, `Optional<T>` hoặc Null Object default, với điều kiện:

- Có test cho trường hợp dependency tồn tại.
- Có test cho trường hợp dependency vắng mặt.
- Hành vi fallback được ghi rõ.
- Không bỏ qua yêu cầu pháp lý/bảo mật thực ra đòi audit bắt buộc.

Ví dụ `TicketService` trong demo minh họa hành vi tiếp tục xử lý khi không có `AuditSink`, không có `NullPointerException`.

### 9.3. Hai beans cùng type không phải “optional”

Nếu đã đăng ký hai `AuditSink` bean với cùng interface và không có quy tắc chọn duy nhất, kết quả không trở thành “không có audit”. Cần lựa chọn có chủ đích: `@Primary`, `@Qualifier`, injection collection hoặc strategy/router theo runtime data.

### 9.4. Lỗi lazy xảy ra muộn cũng vẫn là lỗi cấu hình

Một bean đánh dấu `@Lazy` có thể làm startup hoàn tất nhưng lỗi thiếu dependency chỉ xuất hiện ở `getBean` đầu tiên. Điều đó không có nghĩa `required=true` bị vô hiệu; **điều kiện bắt buộc chỉ được kiểm tra khi bean thật sự được tạo**.

Hãy có integration tests hoặc startup checks thích hợp nếu muốn biết sớm tính đầy đủ của object graph quan trọng.

## 10. Quan hệ với `@Bean` factory method và XML

### 10.1. Factory method parameters được Spring resolve

~~~java
@Bean
TicketService ticketService(TicketStore store) {
    return new TicketService(store);
}
~~~

Đây là đoạn trích từ chương trình chạy. Spring xác định `@Bean` method là một bean factory method và tự giải quyết `TicketStore` parameter. Không cần đặt `@Autowired` lên chính `@Bean` method chỉ để nó nhận các tham số.

Đối với class `TicketService` do method trả về, setter `@Autowired(required=false)` vẫn được bean post-processor xem xét vì nó là Spring-managed bean.

**Cần tách:** resolution của factory parameters xảy ra **trước** khi gọi factory; injection của setters/fields trên sản phẩm xảy ra **sau** khi sản phẩm được tạo và trước khi bean được sử dụng bình thường.

### 10.2. XML bean dependencies

Một cấu hình XML có thể khai báo constructor dependency:

~~~xml
<bean id="ticketStore" class="demo.MemoryTicketStore"/>

<bean id="ticketService" class="demo.TicketService">
    <constructor-arg ref="ticketStore"/>
</bean>
~~~

Đây là **minh họa**; class Java trong chương trình Maven là nested classes bên trong `demo.RequiredTimingDemo` nên không dùng được tên `demo.MemoryTicketStore` của snippet này một cách trực tiếp. Trong project thật, sử dụng fully qualified class names đúng hoặc tách thành top-level classes.

`<constructor-arg ref="ticketStore"/>` là reference bắt buộc theo metadata: nếu tên bean tham chiếu không tồn tại, tạo bean sẽ lỗi. Không có thuộc tính `required=false` trên mọi `<constructor-arg>` có cùng semantics với `@Autowired(required=false)`; không nên cố dịch một-một.

## 11. Các hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “Không ghi `required` thì dependency optional.” | Mặc định `@Autowired(required=true)`. |
| “`required=false` sẽ gọi setter với `null`.” | Với method non-required thiếu dependency, Spring có thể **không gọi method**. |
| “`required=false` xử lý cả bean ứng viên bị lỗi khi tạo.” | Không: lỗi factory/constructor vẫn có thể phá bean creation. |
| “Mọi field optional đều có giá trị hợp lệ nếu không inject.” | Nó giữ default, có thể là null; object cần fallback an toàn. |
| “Constructor `required=false` giống setter `required=false`.” | Constructor resolution và method injection có quy tắc khác nhau. |
| “Một constructor không ghi `@Autowired` nghĩa là không DI.” | Managed bean có một constructor vẫn có thể được inject tự động. |
| “Spring resolve dependency ở mọi lần gọi business method.” | Thường resolution/injection xảy ra lúc bean được tạo; method chỉ sử dụng dependency đã có. |
| “Dependency chỉ được tìm lúc `getBean`.” | Eager singleton thường được tạo khi context refresh. |
| “`@Lazy` tuyệt đối ngăn bean tạo lúc startup.” | Eager dependency có thể buộc bean lazy khởi tạo sớm. |
| “`@Lazy` trên field giống `@Lazy` trên bean definition.” | Vị trí đặt có thể tạo lazy proxy và thời điểm resolution khác. |
| “Inject prototype vào singleton giúp có prototype mới mỗi request.” | Singleton thường giữ một instance đã được inject. |
| “`@Autowired` trên class tự `new` sẽ được JVM thực thi.” | Không, nó cần Spring-managed lifecycle/processor. |
| “`@Primary` giải quyết thiếu bean.” | Primary giúp ưu tiên khi nhiều bean, không tạo bean còn thiếu. |
| “Mọi bean singleton được tạo theo thứ tự khai báo trong source.” | Không dựa vào thứ tự source; chỉ dựa vào dependency/lifecycle semantics. |
| “Context refresh thành công chứng minh mọi lazy bean hợp lệ.” | Lazy bean có thể chỉ được tạo/kiểm tra khi được yêu cầu. |
| “`ObjectProvider` luôn trả một bean hay null, không thể lỗi.” | Nó còn có quy tắc thiếu/đa ứng viên và lỗi tạo bean. |

## 12. Bài tập kèm đáp án

**Bài 1.** `@Autowired` không ghi `required` là true hay false?

**Đáp án:** Mặc định **true**. Dependency tại injection point cần được đáp ứng nếu không có một hình thức optionality khác được hỗ trợ.

**Bài 2.** Method `@Autowired(required=false) void configure(Audit a, Metrics m)` có audit nhưng thiếu metrics. Nó có được gọi với metrics null không?

**Đáp án:** Không trong semantics của method non-required: Spring có thể bỏ qua **toàn bộ method**. Nếu audit và metrics cần tùy chọn riêng, tách điểm tiêm hoặc dùng `Optional<T>`.

**Bài 3.** Bean singleton eager thiếu `TicketStore` bắt buộc. Lỗi xảy ra khi `getBean(TicketService.class)` lần đầu?

**Đáp án:** Có thể xảy ra **ngay khi `ApplicationContext.refresh()`** tạo singleton non-lazy, trước lời gọi getBean của ứng dụng.

**Bài 4.** Một bean `@Lazy` không bị dependency eager nào yêu cầu. Khi nào dependency của nó được giải quyết?

**Đáp án:** Thường khi bean được yêu cầu tạo lần đầu. Nếu bean ấy được inject vào một eager singleton theo cách cần tạo target, thời điểm có thể sớm hơn.

**Bài 5.** Một singleton được inject prototype trực tiếp. Lần gọi method thứ hai trên singleton tự có prototype thứ hai?

**Đáp án:** Không mặc định. Singleton giữ prototype reference được inject lúc tạo. Muốn instance mới, dùng provider/factory hoặc cách scope phù hợp.

**Bài 6.** Có hai `AuditSink` candidates, method setter `required=false` tự chọn một hay bỏ qua?

**Đáp án:** Không được giả định như vậy. Đây là vấn đề ambiguity resolution; cần qualifier/primary hoặc một thiết kế injection nhiều beans hợp lý.

**Bài 7.** Trong chương trình, vì sao có `LAZY_READY false` rồi `CREATE lazy-summary` và `LAZY_READY true`?

**Đáp án:** `LazySummary` là singleton `@Lazy` không bị yêu cầu lúc refresh. `getBean(LazySummary.class)` kích hoạt factory method tạo instance; sau đó instance tồn tại trong singleton registry.

**Bài 8.** Vì sao `AUDIT B2` xuất hiện trước `RESULT DONE TICKET(B2)`?

**Đáp án:** Method `TicketService.process` gọi `audit.record` trước khi trả chuỗi; `main` in kết quả sau khi lời gọi hoàn tất.

**Bài 9.** Có nên dùng `required=false` cho repository mà service không thể thiếu?

**Đáp án:** Không. Điều đó che dependency bắt buộc, có thể biến lỗi startup dễ nhận biết thành lỗi runtime khó theo dõi.

**Bài 10.** `@Bean TicketService ticketService(TicketStore store)` cần `@Autowired` trên method để Spring tiêm store?

**Đáp án:** Không. Spring nhận biết và resolve factory method parameters từ `@Bean` metadata.

## 13. Checklist triển khai và kiểm tra

- [ ] Biết `@Autowired` mặc định là `required=true`.
- [ ] Phân loại collaborator: bắt buộc hay thực sự optional, không chọn theo mong muốn “đừng fail startup”.
- [ ] Dùng constructor/factory method parameters cho dependencies bắt buộc.
- [ ] Khi dùng `@Autowired(required=false)` trên method, thiết kế rõ hành vi nếu method bị bỏ qua.
- [ ] Không nhầm optional injection với việc Spring luôn truyền `null`.
- [ ] Với method nhiều arguments, nhớ tính nguyên khối của method resolution.
- [ ] Dùng `Optional<T>` hoặc provider khi cần optional theo tham số/lúc sử dụng.
- [ ] Với nhiều bean cùng type, có quy tắc chọn đúng: qualifier, primary hoặc aggregate injection.
- [ ] Đừng áp dụng semantics method `required=false` nguyên xi cho constructor selection.
- [ ] Xác định bean được tạo trong startup (non-lazy singleton) hay sau đó (lazy/prototype).
- [ ] Kiểm tra lazy bean bị dependency eager khác yêu cầu.
- [ ] Không kỳ vọng Spring chạy lại setter mỗi lần business method được gọi.
- [ ] Không kỳ vọng field `@Autowired` tự chạy trên đối tượng tạo tay bằng `new`.
- [ ] Với prototype trực tiếp trong singleton, xác định có cần provider/factory cho instance mới hay không.
- [ ] Kiểm thử ngữ cảnh thiếu bean, có bean và nhiều beans khi cấu hình quan trọng.
- [ ] Đọc nguyên nhân gốc của `BeanCreationException`/`UnsatisfiedDependencyException`.
- [ ] Đóng context khi không còn dùng và không gọi managed resources sau khi đóng.
- [ ] Đảm bảo build Java 17 và phân biệt dòng stdout chương trình với log Maven.

### Tham khảo tài liệu Spring chính thức

- [`@Autowired` — constructor, fields, methods, required semantics](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Lazy-initialized beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Bean scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [`@Bean` factory methods](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)

**Kết luận:** `required` trả lời câu hỏi “injection point này có thể vắng dependency không?”, còn **thời điểm resolution** phụ thuộc vào cách và lúc Spring tạo bean. Với singleton eager, lỗi dependency bắt buộc có thể xảy ra ngay khi refresh; với bean lazy/prototype, lỗi có thể xuất hiện muộn hơn; với proxy/provider, lookup đích có thể tiếp tục được trì hoãn. Hiểu hai trục này giúp thiết kế dependency đúng, dự đoán lỗi chính xác và không lạm dụng `required=false` để che cấu hình thiếu.