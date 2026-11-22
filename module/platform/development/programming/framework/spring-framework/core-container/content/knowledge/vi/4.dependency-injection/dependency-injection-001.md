# Phụ thuộc bắt buộc, phụ thuộc tùy chọn và bất biến đối tượng trong Spring

## 1. Phân loại dependency theo hợp đồng của đối tượng

Một class Java có thể cần một hoặc nhiều đối tượng cộng tác (*dependencies*) để thực hiện nhiệm vụ. Trong Spring Core Container, **Dependency Injection (DI)** là quá trình container cung cấp những dependency đã được định nghĩa cho bean, thay vì để bean tự tìm hoặc tự tạo tất cả cộng tác viên.

Câu hỏi quan trọng khi thiết kế một service không phải “đặt annotation nào?”, mà là **dependency đó có bắt buộc để đối tượng hợp lệ không?**

| Loại phụ thuộc | Ý nghĩa | Khi thiếu dependency | Cách thiết kế nên ưu tiên |
| --- | --- | --- | --- |
| **Bắt buộc (required)** | Không thể thực hiện hợp đồng chính của object nếu thiếu | Nên thất bại sớm và rõ nguyên nhân | **Constructor injection**, tham số không được `null`, trường `final` |
| **Tùy chọn (optional)** | Thiếu vẫn có một hành vi hợp lệ đã định nghĩa trước | Dùng mặc định, bỏ qua tính năng hoặc cơ chế thay thế | `Optional<T>`, `ObjectProvider<T>`, default strategy; setter nếu cần tái cấu hình |
| **Cấu hình giá trị (configuration)** | Tham số như timeout, base URL, giới hạn nghiệp vụ | Cần chính sách validation và default rõ ràng | Constructor/configuration factory method, value object bất biến |

Ví dụ một `BillingService` **phải có** `PaymentGateway` để ghi nhận thanh toán, nhưng **có thể không có** `AuditSink` trong một demo/offline mode. Khi thiếu `PaymentGateway`, tạo service sẽ thất bại; khi thiếu `AuditSink`, service vẫn thanh toán được nhưng không phát bản ghi audit.

**Tùy chọn không đồng nghĩa “không quan trọng về bảo mật”.** Nếu audit là yêu cầu bắt buộc vì pháp lý/kiểm toán thì phải thiết kế nó là **required**; không được silently skip một chức năng thiết yếu chỉ vì API `Optional` cho phép.

Mục tiêu học: xác định đúng hợp đồng, phân biệt **container thiếu bean** với **giá trị null do code tự truyền**, làm chủ các lựa chọn optional của Spring và hiểu phạm vi thực sự của `final`/immutability.

## 2. Constructor injection và bất biến trạng thái cấu hình

Với dependency bắt buộc, đối tượng nên từ chối được tạo nếu giá trị cần thiết không tồn tại:

~~~java
// Snippet Java thuần: các type PaymentGateway/AuditSink định nghĩa ở demo đầy đủ.
public final class BillingService {
    private final PaymentGateway gateway;
    private final Optional<AuditSink> audit;

    public BillingService(
            PaymentGateway gateway, Optional<AuditSink> audit) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.audit = Objects.requireNonNull(audit, "audit");
    }
}
~~~

Đây là **mẫu minh họa**, không phải source biên dịch độc lập: cần import `java.util.Objects`, `java.util.Optional` và khai báo các interfaces. Chương trình hoàn chỉnh có ở mục 5.

**Constructor injection** có ba lợi ích trực tiếp:

1. **Thiếu dependency bắt buộc bị phát hiện sớm.** Java caller cố truyền `null` sẽ nhận exception tại constructor thay vì một `NullPointerException` ở giữa xử lý nghiệp vụ.
2. **Object ra khỏi constructor trong trạng thái hợp lệ.** Không cần tạm tồn tại một `BillingService` chưa có gateway rồi mong setter được gọi trước khi dùng.
3. **Dependency references có thể là `final`.** Sau khi constructor chạy xong, class không thể gán lại trường `gateway` hoặc `audit` trong Java thông thường.

Spring cũng khuyến nghị constructor injection cho các thành phần bắt buộc vì nó cho phép thiết kế bất biến và tránh đối tượng được trả về trong trạng thái chưa hoàn tất. Với một Spring-managed component chỉ có **một constructor**, Spring thường có thể chọn constructor đó mà không cần viết `@Autowired`; với `@Bean` factory method, ta có thể inject qua **tham số factory method**. Quy tắc nhiều constructors phức tạp hơn, không suy ra rằng Spring sẽ đoán đúng mọi constructor overload.

### `final` không đồng nghĩa deep immutability

~~~java
private final List<String> events = new ArrayList<>();
~~~

Reference `events` không thể được gán sang list khác sau khởi tạo, nhưng **nội dung list vẫn có thể thay đổi**. Tương tự, `private final PaymentGateway gateway` chỉ giữ cố định *reference*; nếu implementation `PaymentGateway` có trạng thái mutable, cả object graph không tự trở nên bất biến hoặc thread-safe.

**Bất biến đối tượng có nhiều mức:**
- **Stable dependency wiring:** reference tới dependency không bị đổi sau construction (`final`).
- **Immutable state:** các giá trị mà object chứa không thay đổi sau construction; khi dùng mutable inputs nên tạo defensive copies.
- **Deep immutability:** cả object con reachable từ object cũng phải có hợp đồng phù hợp.
- **Thread safety:** cần xem xét cả concurrency và state thực tế; Spring singleton **không tự bảo đảm thread safety**.

Một service có thể có final dependencies mà vẫn thao tác với database, ghi log hoặc gọi mutable client. **Immutability của cấu hình và side effects của phương thức là hai khái niệm khác nhau.**

## 3. Spring hiểu “required” ở điểm inject như thế nào?

Trong Spring, dependency thông thường được coi là **bắt buộc** khi resolve một tham số constructor hoặc factory method theo type. Nếu container không có bean phù hợp và không có một quy tắc đặc biệt cho điểm inject, quá trình tạo bean thất bại.

~~~java
// Snippet configuration, có đầy đủ type/import trong demo mục 5.
@Bean
BillingService billingService(
        PaymentGateway gateway, Optional<AuditSink> audit) {
    return new BillingService(gateway, audit);
}
~~~

`PaymentGateway gateway` là **required**. Spring phải tìm bean tương thích để gọi factory method. `Optional<AuditSink>` là điểm inject **optional** theo khả năng resolve của Spring: nếu không có bean `AuditSink` thích hợp, nó có thể truyền `Optional.empty()`; khi có đúng một candidate phù hợp, nó truyền `Optional.of(bean)`.

Nếu có **hai beans cùng type** mà không có qualifier/primary hoặc cơ chế phân giải rõ ràng, Spring có thể báo ambiguity. `Optional<T>` không có nghĩa “lấy tùy một bean đầu tiên” khi có nhiều candidates.

### Khi Spring resolve thiếu bean bắt buộc

~~~text
@Bean billingService(PaymentGateway gateway, Optional<AuditSink> audit)
                         |
                         v
           Tìm PaymentGateway trong context
                     /                 \
             Có 1 phù hợp           Không có
                  |                     |
                  v                     v
         Inject reference       Thất bại tạo bean
                  |
                  v
         Resolve optional AuditSink
                  |
            Có / không có
                  |
                  v
       Tạo BillingService hợp lệ
~~~

Khi một singleton không lazy được pre-instantiate ở `ApplicationContext.refresh()`, thiếu required bean có thể khiến **cả context khởi động thất bại** trước khi ứng dụng gọi `getBean`. Với lazy/prototype, lỗi có thể xuất hiện muộn hơn vào lúc tạo bean. Không đồng nhất lỗi tạo bean với lỗi Maven chưa tải đủ JAR.

**Khác biệt giữa hai tầng validation:**

- **Container validation:** Có bean nào có type/qualifier đáp ứng injection point?
- **Object invariant validation:** Tham số có hợp lệ về null, domain, phạm vi giá trị hay quan hệ business không?

Spring có thể đã resolve đúng bean theo type nhưng bean ấy vẫn có một cấu hình nghiệp vụ không hợp lệ. Dùng validation tại constructor/factory để giữ invariant, thay vì kỳ vọng DI tự kiểm tra mọi quy tắc domain.

## 4. Các cách diễn đạt phụ thuộc tùy chọn

Spring hỗ trợ nhiều cách, với ý nghĩa và lifecycle không hoàn toàn giống nhau.

| Cách diễn đạt | Khi không có bean | Khi nên cân nhắc |
| --- | --- | --- |
| **`Optional<T>`** tại injection point | Thường nhận `Optional.empty()` | Biết ngay tại construction xem tính năng có sẵn không; dependency optional thật sự |
| **`ObjectProvider<T>`** | Nhận provider; có thể kiểm tra `getIfAvailable()` sau | Muốn **lookup theo nhu cầu**, trì hoãn việc lấy bean hoặc phối hợp scope |
| **`@Nullable T`** trên tham số | Cho phép nhận `null` theo quy tắc injection | Tích hợp API vốn dùng null; phải code null-safe và chọn đúng annotation |
| **`@Autowired(required = false)`** trên setter/field | Setter không được gọi hoặc field không được set nếu thiếu candidate | Optional mutable/configuration legacy; cần default hợp lệ |
| **No-op/default implementation** | Luôn inject một implementation đáp ứng hợp đồng | Khi tính năng luôn cần một strategy nhưng có implementation mặc định không thực hiện side effect |

**Khuyến nghị cho code mới:** `Optional<T>` rõ nghĩa cho một dependency có thể vắng mặt ngay lúc tạo object; `ObjectProvider<T>` hữu ích nếu dependency cần lấy động tại thời điểm gọi method. Không dùng optional cho thứ mà service không thể hoạt động nếu thiếu.

### `Optional<T>` ngay trong constructor

~~~java
public BillingService(
        PaymentGateway gateway, Optional<AuditSink> audit) {
    this.gateway = Objects.requireNonNull(gateway);
    this.audit = Objects.requireNonNull(audit);
}
~~~

`audit` **không được là null**; vắng audit được biểu diễn bằng `Optional.empty()`. Điều này tránh kết hợp hai cơ chế “vắng”: vừa `null`, vừa empty. Ở caller Java thuần, bạn phải tự tạo `Optional.empty()` hoặc `Optional.of(sink)`; Spring chỉ giúp resolve `Optional` khi thực sự tạo/tiêm bean.

### `ObjectProvider<T>`: lấy khi cần

~~~java
// Snippet trong một bean Spring, giả sử provider đã được inject.
private final ObjectProvider<AuditSink> sinkProvider;

public void maybeRecord(String message) {
    AuditSink sink = sinkProvider.getIfAvailable();
    if (sink != null) {
        sink.record(message);
    }
}
~~~

Đoạn trên cần import `org.springframework.beans.factory.ObjectProvider` và các type phù hợp. **Provider không tự biến một bean bị thiếu thành một implementation**, chỉ cho phép hỏi và xử lý sự vắng mặt. `getObject()` thông thường **yêu cầu có bean**, không giống `getIfAvailable()`; với nhiều candidates, cần xử lý ambiguity/qualifiers.

Provider có thể hữu ích khi một singleton cần tạo/lấy prototype theo từng lượt. Inject prototype trực tiếp vào constructor singleton **không** tự làm mới dependency ở mỗi lần gọi method.

### `@Autowired(required=false)` và `@Nullable`

~~~java
// Snippet minh họa (không phải một file Java độc lập):
private AuditSink audit = message -> { }; // Mặc định no-op.

@Autowired(required = false)
public void setAudit(AuditSink sink) {
    this.audit = sink;
}
~~~

Nếu Spring không có dependency phù hợp, non-required setter có thể **không được gọi**, nên field giữ giá trị no-op ban đầu. Cách này hợp lý khi object **cho phép thay strategy sau construction**; nhưng state giờ mutable, cần cân nhắc concurrency và thời điểm object được dùng.

`@Nullable` được Spring hỗ trợ trên điểm inject (chẳng hạn `org.jspecify.annotations.Nullable` trong hệ Spring hiện đại) để biểu diễn việc vắng dependency bằng `null`. API này cần đúng dependency/import và phải được xử lý null-safe. **Không nhầm `@Nullable` với `@Autowired(required=false)` trên mọi vị trí**; chúng có semantics khác nhau, đặc biệt ở method nhiều tham số.

## 5. Dự án Spring Framework 7 + Java 17: ba tình huống required/optional

Ví dụ dùng **một business service** và ba cách cấu hình container:

1. Có `PaymentGateway`, **không có `AuditSink`** → service tạo được, `Optional.empty()`.
2. Có `PaymentGateway` và **có một `AuditSink`** → service tạo được, audit nhận thông điệp.
3. **Không có `PaymentGateway`** → container từ chối tạo `BillingService` bắt buộc, thay vì cung cấp null âm thầm.

Ba lần khởi tạo context độc lập, không dùng Spring Boot hay web server.

### 5.1. Cấu trúc Maven

~~~text
required-optional-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── RequiredOptionalDemo.java
~~~

Yêu cầu: **JDK 17+**, Maven **3.9+**, tải thư viện từ repository ở lần chạy đầu.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>required-optional-demo</artifactId>
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
                    <mainClass>demo.RequiredOptionalDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` có các API container và kéo các Spring artifacts nền cần thiết theo Maven transitive dependencies; không phải khai báo Spring Boot starter. Spring Framework 7.0 có baseline Java 17; dùng BOM/quản lý phiên bản phù hợp khi bổ sung các Spring modules khác vào ứng dụng thật.

### 5.2. Mã `src/main/java/demo/RequiredOptionalDemo.java`

~~~java
package demo;

import java.util.Objects;
import java.util.Optional;

import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class RequiredOptionalDemo {

    private RequiredOptionalDemo() {
    }

    interface PaymentGateway {
        String charge(String invoice, long amount);
    }

    interface AuditSink {
        void record(String message);
    }

    static final class FixedGateway implements PaymentGateway {
        @Override
        public String charge(String invoice, long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("amount must be >= 0");
            }
            return "OK:" + invoice + ":" + amount;
        }
    }

    static final class ConsoleAuditSink implements AuditSink {
        @Override
        public void record(String message) {
            System.out.println("AUDIT:" + message);
        }
    }

    // Business service: không phụ thuộc API Spring.
    public static final class BillingService {
        private final PaymentGateway gateway;
        private final Optional<AuditSink> audit;

        public BillingService(
                PaymentGateway gateway, Optional<AuditSink> audit) {
            this.gateway = Objects.requireNonNull(gateway, "gateway");
            this.audit = Objects.requireNonNull(audit, "audit");
        }

        public boolean hasAudit() {
            return audit.isPresent();
        }

        public String bill(String invoice, long amount) {
            String receipt = gateway.charge(invoice, amount);
            audit.ifPresent(sink -> sink.record(receipt));
            return receipt;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BaseConfig {
        @Bean
        public PaymentGateway paymentGateway() {
            return new FixedGateway();
        }

        @Bean
        public BillingService billingService(
                PaymentGateway gateway, Optional<AuditSink> audit) {
            return new BillingService(gateway, audit);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AuditConfig {
        @Bean
        public AuditSink auditSink() {
            return new ConsoleAuditSink();
        }
    }

    // Cố tình KHÔNG khai báo PaymentGateway.
    @Configuration(proxyBeanMethods = false)
    public static class MissingGatewayConfig {
        @Bean
        public BillingService billingService(
                PaymentGateway gateway, Optional<AuditSink> audit) {
            return new BillingService(gateway, audit);
        }
    }

    public static void main(String[] args) {
        // Có required PaymentGateway, thiếu optional AuditSink.
        try (var context =
                new AnnotationConfigApplicationContext(BaseConfig.class)) {
            BillingService service = context.getBean(BillingService.class);
            System.out.println("without.audit=" + service.hasAudit());
            System.out.println("without.result="
                    + service.bill("INV-1", 120));
            System.out.println("without.singleton="
                    + (service == context.getBean(BillingService.class)));
        }

        // Đăng ký thêm một bean AuditSink.
        try (var context = new AnnotationConfigApplicationContext(
                BaseConfig.class, AuditConfig.class)) {
            BillingService service = context.getBean(BillingService.class);
            System.out.println("with.audit=" + service.hasAudit());
            // Lệnh dưới gọi AuditSink.record(), in dòng AUDIT trước.
            String receipt = service.bill("INV-2", 200);
            System.out.println("with.result=" + receipt);
        }

        // Không có bean required: lỗi khi startup context.
        try (var context = new AnnotationConfigApplicationContext(
                MissingGatewayConfig.class)) {
            System.out.println("unreachable");
        } catch (BeansException expected) {
            System.out.println("missingRequired.rejected=true");
        }
    }
}
~~~

**Vì sao có thể biên dịch và chạy độc lập:** Tất cả classes/interfaces của demo nằm trong cùng source, chỉ cần dependency `spring-context`. `BaseConfig` khai báo gateway và service; `AuditConfig` độc lập chỉ khai báo audit. Spring resolve tham số `PaymentGateway` bắt buộc và tham số `Optional<AuditSink>` tùy chọn cho factory method.

`BillingService` giữ hai field `final`, không có setters, và tự từ chối tham số `null` qua `Objects.requireNonNull`. Đây là **thiết kế không đổi reference**; không suy luận rằng mọi implementation `PaymentGateway`/`AuditSink` sẽ bất biến hoặc thread-safe.

`MissingGatewayConfig` chỉ có `BillingService` cần gateway. Ở cấu hình mặc định (singleton không lazy), context không thể hoàn thành refresh; exception thuộc họ `BeansException`. Chương trình chỉ in một dòng boolean xác nhận thất bại, **không dựa vào toàn bộ class/message/stack trace** vốn phụ thuộc version và logger.

**Chú ý `@Bean` factory-method injection:** Với `proxyBeanMethods=false`, factory methods trong ví dụ **không tự gọi nhau**. Spring cấp dependency cho `billingService(...)` qua tham số; không gọi `paymentGateway()` bằng tay ở bên trong để giả định đó là singleton.

## 6. Chạy Maven và đối chiếu stdout

Tại thư mục `required-optional-demo` có `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Các lệnh kiểm tra Java/Maven in thông tin phụ thuộc môi trường. Lệnh cuối dùng compiler qua Maven để biên dịch target Java 17 rồi chạy class `demo.RequiredOptionalDemo`.

**7 dòng stdout xác định của chương trình** (không tính log/exception diagnostic do Maven hoặc Spring backend sinh ngoài các lệnh `System.out.println`):

~~~text
without.audit=false
without.result=OK:INV-1:120
without.singleton=true
with.audit=true
AUDIT:OK:INV-2:200
with.result=OK:INV-2:200
missingRequired.rejected=true
~~~

| Dòng output | Bằng chứng | Giới hạn suy luận |
| --- | --- | --- |
| `without.audit=false` | `Optional.empty()` được dùng khi không có bean AuditSink | Không có nghĩa API `AuditSink` bị lỗi |
| `without.result=...` | Required gateway tồn tại, nghiệp vụ vẫn chạy | Không chứng minh mọi cấu hình optional đều an toàn |
| `without.singleton=true` | Bean BillingService mặc định singleton trong một context | Không phải một instance toàn JVM |
| `with.audit=true` | Có đúng một AuditSink phù hợp ở context thứ hai | Không có nghĩa audit bắt buộc trong context thứ nhất |
| `AUDIT:...` | Optional dependency được dùng khi hiện diện | Một side effect có thể xảy ra mà kết quả bill vẫn trả đúng |
| `with.result=...` | Business receipt không đổi khi thêm audit | Không tự bảo đảm audit delivery thật sự bền vững |
| `missingRequired.rejected=true` | Tạo singleton thiếu required dependency bị từ chối | Không có nghĩa thiếu mọi optional dependency cũng fail |

Khi một context startup thất bại, Spring có thể log warning/exception trước khi exception được chương trình catch. Expected output ở đây là **các dòng từ chính source**, không phải toàn bộ nội dung terminal.

Nếu ứng dụng dùng một `PaymentGateway` thật có I/O, không cố định expected output theo các lệnh gọi network; demo dùng `FixedGateway` có kết quả xác định và không có side effects bên ngoài.

## 7. Java thuần Java 17: required/optional không cần Spring

Tính **bắt buộc/tùy chọn** là vấn đề hợp đồng của object, không chỉ là tính năng Spring. Để tự kiểm chứng, tạo file **`RequiredOptionalPureJava.java`** tách biệt:

~~~java
import java.util.Objects;
import java.util.Optional;

public class RequiredOptionalPureJava {
    interface Store {
        String id();
    }

    static final class Reader {
        private final Store store;
        private final Optional<String> label;

        Reader(Store store, Optional<String> label) {
            this.store = Objects.requireNonNull(store, "store");
            this.label = Objects.requireNonNull(label, "label");
        }

        String describe() {
            return store.id() + ":" + label.orElse("default");
        }
    }

    public static void main(String[] args) {
        Store store = () -> "store";
        System.out.println("noLabel="
                + new Reader(store, Optional.empty()).describe());
        System.out.println("withLabel="
                + new Reader(store, Optional.of("vip")).describe());

        try {
            new Reader(null, Optional.empty());
        } catch (NullPointerException expected) {
            System.out.println("requiredRejected=true");
        }
    }
}
~~~

Chạy từ thư mục chứa file, **không cần Maven hay JAR Spring**:

~~~bash
javac RequiredOptionalPureJava.java
java RequiredOptionalPureJava
~~~

Expected stdout:

~~~text
noLabel=store:default
withLabel=store:vip
requiredRejected=true
~~~

Hai ví dụ dùng cùng nguyên tắc: **required không null**, **optional biểu diễn vắng mặt rõ ràng**, và **reference được giữ final**. Spring chỉ tổ chức việc resolve/dependency wiring; Java thuần vẫn phải bảo vệ invariants khi caller chủ động dùng `new`.

Một lưu ý thiết kế: `Optional` thường phù hợp với return value và một số dependency injection points; không nên cố đưa `Optional` vào mọi field hoặc mọi DTO để thay thế việc định nghĩa contract và serialisation rõ ràng. Ở ví dụ, field `Optional<AuditSink>` có chủ đích để làm nổi bật optional dependency.

## 8. Setter injection khi cấu hình không thiết yếu có giá trị mặc định

Trong ví dụ `BillingService`, `PaymentGateway` là dependency bắt buộc còn `AuditSink` được biểu diễn là `Optional<AuditSink>` ngay trong constructor. Với một **thiết lập có mặc định hợp lệ** và cho phép điều chỉnh, setter là một lựa chọn khác:

~~~java
// Mẫu Java thuần để minh họa setter, chưa có main().
public final class ReportService {
    private boolean verbose; // Mặc định false, object vẫn hợp lệ.

    public void setVerbose(boolean verbose) {
        this.verbose = verbose;
    }

    public void report() {
        if (verbose) {
            System.out.println("report:verbose");
        }
    }
}
~~~

Không gọi `setVerbose(...)` vẫn để `ReportService` có hành vi xác định. Với setter `@Autowired(required = false)` nhận **bean tùy chọn**, Spring có thể bỏ qua lời gọi setter nếu không tìm được dependency phù hợp; vì vậy trạng thái mặc định phải an toàn. Đừng biến một dependency thật sự bắt buộc như `PaymentGateway` thành setter tùy chọn chỉ để context khởi động được.

**Giới hạn:** setter giữ state có thể thay đổi, nên nếu sửa cấu hình khi một singleton đang phục vụ nhiều luồng phải có chính sách đồng bộ và tính nhất quán rõ ràng. Quy tắc chọn nhiều constructor và cách chẩn đoán constructor quá nhiều dependency là hai chủ đề riêng; chúng không làm thay đổi định nghĩa required/optional của bài này.

## 9. Immutability thực tế: dữ liệu, defensive copy và concurrency

Một class có `final` fields vẫn có thể bị thay đổi gián tiếp nếu field trỏ đến collection do caller quản lý. Ví dụ:

~~~java
// Snippet Java 17: giữ bản sao bất biến của các tags.
public final class BillingPolicy {
    private final List<String> allowedTags;

    public BillingPolicy(List<String> tags) {
        this.allowedTags = List.copyOf(
                Objects.requireNonNull(tags, "tags"));
    }

    public List<String> allowedTags() {
        return allowedTags;
    }
}
~~~

`List.copyOf` tạo hoặc tái sử dụng một **unmodifiable list** với hợp đồng phù hợp và từ chối phần tử `null`; caller không thể sửa các phần tử của list qua reference được trả về. Tuy nhiên nếu phần tử là mutable object, **bản thân object con** vẫn có thể thay đổi. Đoạn trên cần import `java.util.List`, `java.util.Objects` và đặt trong file có class public cùng tên.

Các nguyên tắc nâng mức bất biến:

1. Khai báo field `private final` cho state nên giữ cố định; constructor thực thi validation.
2. Tránh công khai setters thay state thiết yếu sau construction.
3. Dùng value objects immutable (ví dụ `record` Java 17 khi phù hợp), defensive copies cho collections/arrays và không rò reference mutable.
4. Xác định rõ ownership của resource và side effects. Một `PaymentGateway` final vẫn có thể thực hiện giao dịch bên ngoài.
5. Khi Spring tạo singleton, **đảm bảo code của bean thread-safe theo nhu cầu**: Spring scope không tự bảo vệ mutable caches hoặc counters.
6. Tránh circular constructor dependencies. Nếu A cần B để constructor hoàn tất và B đồng thời cần A, container có thể báo lỗi khi tạo graph; xem lại thiết kế thay vì chuyển mọi dependency sang setter để che vòng lặp.

**Không biến mọi dependency thành Optional để né lỗi startup.** Nếu một ứng dụng bắt buộc phải thanh toán, thiếu PaymentGateway nên là failure rõ ràng — khởi động “thành công” với một payment gateway null/no-op có thể nguy hiểm hơn fail-fast.

## 10. Lỗi thường gặp và cách tự chẩn đoán

| Triệu chứng/nhận định | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho PaymentGateway | Không có bean phù hợp trong context | Đăng ký một `@Bean`/component scan đúng, xem cấu hình active |
| `UnsatisfiedDependencyException` lúc refresh | Bean cần dependency bắt buộc chưa resolve | Đọc exception `Caused by`; xác minh type, bean name, qualifier |
| `NoUniqueBeanDefinitionException` | Nhiều candidates cùng type mà không có cách chọn | Dùng `@Qualifier`, `@Primary` hoặc phân tách interface |
| `Optional<AuditSink>` luôn empty | Bean AuditSink không được đăng ký trong context hiện tại | Kiểm tra config class/scan, không ép code `get()` |
| Gọi `audit.get()` khi Optional.empty | `NoSuchElementException` trong business code | Dùng `ifPresent`, `orElse`, `orElseGet` theo policy |
| `@Autowired(required=false)` setter không chạy | Không có candidate hợp lệ cho injection point | Đảm bảo default object state hợp lệ trước setter |
| `ObjectProvider.getObject()` bị lỗi | API này yêu cầu bean, không cho fallback tự động | Chọn `getIfAvailable()` hoặc xử lý exception |
| `Objects.requireNonNull` vẫn ném NPE | Code tự gọi `new Service(null,...)` hoặc factory tự truyền null | Sửa caller/factory; container injection không thay validation |
| Có `final` fields nhưng state vẫn thay đổi | Dependency hoặc collection được tham chiếu vẫn mutable | Defensive copy, immutable implementations, đồng bộ state thích hợp |
| Singleton bị race khi nhiều request | Có mutable state không an toàn được chia sẻ | Thiết kế stateless/immutable hoặc cơ chế concurrency đúng |
| Context tạo được nhưng nghiệp vụ sai | DI chỉ giải quyết wiring, không chứng minh domain rule đúng | Unit/integration tests, input validation và contract checks |
| Java import Spring không compile | Thiếu `spring-context` trên compile classpath | Dùng Maven dependency đúng version và reload project |

### Phân biệt lỗi hạ tầng với lỗi hợp đồng

- Nếu Maven không tìm thấy artifact, đó là vấn đề **dependency resolution/repository**.
- Nếu code Java không import được `org.springframework.context.annotation`, đó là vấn đề **compile classpath**.
- Nếu context không tìm được bean, đó là vấn đề **DI configuration**.
- Nếu constructor tự ném `IllegalArgumentException`/`NullPointerException`, đó là vấn đề **invariant/argument validation** hoặc factory đang truyền giá trị không hợp lệ.
- Nếu `bill()` xử lý sai `amount`, đó là vấn đề **business logic**, không được Spring tự phát hiện.

Đọc **nguyên nhân gốc trong exception chain**, thay vì chép nguyên message cố định của Spring theo một patch version; các type và thông báo lồng nhau có thể thay đổi theo cách context được dựng.

## 11. Thử nghiệm có kiểm chứng

Thực hiện từng thay đổi độc lập trên một bản sao, khôi phục code gốc để đối chiếu stdout ở mục 6:

1. **Không có optional:** chạy BaseConfig, giải thích vì sao `without.audit=false` nhưng vẫn có `without.result`.
2. **Có optional:** thêm AuditConfig, chỉ ra thời điểm `ConsoleAuditSink.record()` chạy và lý do dòng `AUDIT` xuất hiện trước `with.result`.
3. **Không có required:** chạy MissingGatewayConfig riêng và xác định loại lỗi startup. Vì sao thiếu gateway phải fail thay vì `Optional.empty()`?
4. **Gây ambiguity:** khai báo hai beans `PaymentGateway` khác nhau, rồi thêm `@Qualifier`/`@Primary` để giải quyết. Không dùng Optional để che lỗi.
5. **Constructor guard:** tự tạo `new BillingService(null, Optional.empty())` bên ngoài Spring, xác định exception là do Java constructor validation, không phải container.
6. **Đổi optional sang required:** thay tham số `Optional<AuditSink>` bằng `AuditSink`; dự đoán trường hợp BaseConfig không còn khởi động bình thường.
7. **Dùng Provider:** inject `ObjectProvider<AuditSink>`, so sánh `getIfAvailable()` với `getObject()` khi thiếu bean.
8. **Thêm no-op fallback:** tạo `NoOpAuditSink` và inject như một bean mặc định có điều kiện/hợp đồng rõ; so sánh với việc bỏ hẳn audit.
9. **Setter optional:** chuyển audit thành setter với `@Autowired(required=false)`, cho default no-op, so sánh vì sao wiring giờ mutable hơn.
10. **Thử concurrency:** giải thích vì sao `final PaymentGateway` không bảo đảm implementation của gateway thread-safe khi gọi đồng thời.
11. **Defensive copy:** thử sửa list được trả về từ `BillingPolicy.allowedTags()`, dự đoán exception và phân biệt shallow/deep immutability.
12. **Unit test thuần Java:** truyền fake gateway và `Optional.empty()` để kiểm thử `BillingService` mà không khởi tạo context; phân biệt test business với test wiring.

### Checklist đạt bài

- [ ] Phân biệt required, optional và default dependency theo **hợp đồng nghiệp vụ**.
- [ ] Dùng constructor injection và `Objects.requireNonNull` cho required dependency.
- [ ] Dự đoán đúng hành vi `Optional<AuditSink>` không/có bean.
- [ ] Không nhầm `ObjectProvider.getObject()` với `getIfAvailable()`.
- [ ] Giải thích đúng `@Autowired(required=false)` trên setter và điểm khác với constructor.
- [ ] Phân biệt `final` reference, immutable state, deep immutability và thread safety.
- [ ] Biết vì sao thiếu PaymentGateway làm context fail-fast.
- [ ] Chạy Maven demo Java17 ra đúng 7 dòng stdout chính và Java thuần ra đúng 3 dòng.
- [ ] Biết kiểm tra dependency ambiguity và không dùng optional để che lỗi cấu hình.

## 12. Tóm tắt và tài liệu chính thức

**Điểm cần ghi nhớ:**

- **Required dependency:** object không thể hợp lệ khi thiếu; hãy bảo vệ bằng constructor injection, non-null contract và validation. Spring mặc định đòi resolve nó.
- **Optional dependency:** vắng vẫn có hành vi hợp lệ; diễn đạt bằng `Optional<T>`, `ObjectProvider<T>` hoặc một default strategy phù hợp. Đừng gắn optional cho nghiệp vụ vốn bắt buộc.
- **Bất biến:** `final` cố định reference nhưng **không tự cố định trạng thái của dependency**; sử dụng defensive copy và value objects khi cần.
- **Thiết kế DI tốt:** nghiệp vụ nhận dependency rõ ràng và có thể kiểm thử bằng Java thuần; Spring là công cụ wiring/lifecycle, không phải nguồn gốc của quy tắc bất biến.

Tài liệu tra cứu:
- [Spring Framework – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework – Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework – Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework – Dependency Resolution with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Java 17 – `java.util.Optional`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html)
- [Java 17 – `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html)

**Kết luận:** Trong Spring Core Container, “phụ thuộc bắt buộc” và “phụ thuộc tùy chọn” là **quyết định thiết kế đối tượng**, còn `Optional`, provider và autowiring là những công cụ để thực hiện quyết định ấy. Một service với constructor rõ ràng, required dependencies được kiểm tra và references `final` sẽ dễ lý giải, kiểm thử và vận hành hơn mà không ngộ nhận rằng Spring tự làm mọi object bất biến.