# Cơ chế xử lý `@Autowired` trong Spring IoC Container

## 1. `@Autowired` là chỉ dẫn cho container, không phải cú pháp tự động của Java

`@Autowired` là annotation thuộc **Spring Framework** (package `org.springframework.beans.factory.annotation`) được dùng để mô tả những điểm mà Spring nên cung cấp dependency. Nó có thể đặt trên **constructor, instance field, setter hoặc phương thức cấu hình có tham số**. Ở những vị trí được hỗ trợ, Spring IoC Container tìm bean phù hợp và đưa **reference của bean đó** cho đối tượng đang được tạo.

Điểm mấu chốt: **Java compiler/JVM không tự chạy DI chỉ vì nhìn thấy `@Autowired`.** Annotation là metadata; Spring phải đọc và xử lý nó thông qua hạ tầng của container.

~~~java
// Snippet minh họa, không phải file độc lập.
@Autowired
private MessageSource source;
~~~

Trong một **Spring-managed bean**, Spring có thể cấp `MessageSource` thích hợp cho field trên. Nhưng nếu bạn viết `new SomeService()` bên ngoài container, Spring không tự tìm đến object vừa `new` để tiêm field; trường có thể vẫn là `null`. Tương tự, chỉ gắn `@Autowired` không làm class tự đăng ký thành bean.

Bài này trả lời năm câu hỏi:
1. Ai đọc `@Autowired`, vào **giai đoạn nào** của vòng đời bean?
2. Spring chọn **constructor**, **bean candidate** và **điểm tiêm** ra sao?
3. Field injection khác constructor injection và method injection tại thời điểm nào?
4. `required`, `Optional<T>`, `ObjectProvider<T>`, `@Qualifier` tác động thế nào tới dependency resolution?
5. Vì sao một số lỗi xảy ra ngay khi context `refresh()`, còn một số chỉ xảy ra khi lấy bean?

**Phạm vi:** Spring Framework Core Container thuần, **không** cần Spring Boot, HTTP server hay database. Ví dụ chính dùng **Java 17+, Spring Framework 7.0.9, Maven**, không dựa vào random, đồng hồ hoặc log nội bộ để xây expected stdout.

## 2. Những thành phần tham gia xử lý annotation

| Thành phần | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| `BeanDefinition` | Metadata đăng ký cách tạo, scope, factory method và cấu hình cho bean | Bean instance thực |
| `BeanFactory` / `ApplicationContext` | Quản lý definitions, tạo và cấp bean, giải quyết dependency | Java compiler |
| `BeanPostProcessor` | Extension point can thiệp một số giai đoạn xử lý bean do Spring tạo | Một business bean bình thường |
| `AutowiredAnnotationBeanPostProcessor` | Processor chuyên trách `@Autowired` và các annotation liên quan; nhận diện injection points và xử lý field/method injection; tham gia chọn constructor candidate | Lệnh `new` của Java |
| `ConfigurationClassPostProcessor` | Xử lý các nguồn cấu hình như `@Configuration`, `@Bean`, `@ComponentScan` để đăng ký metadata thích hợp | Processor tự tiêm mọi field |
| `DependencyDescriptor` và resolver bên trong bean factory | Mô tả type, qualifier, required/optional, generic và chọn dependency phù hợp | Cơ chế Java reflection đơn thuần |
| `InitializingBean` hoặc init callback | Chạy khi các dependency được cấp và bean đã đến bước initialization | Nơi thích hợp để chọn constructor |

Trong thực tế, `AutowiredAnnotationBeanPostProcessor` có các hợp đồng chuyên biệt như **`SmartInstantiationAwareBeanPostProcessor`** và **`InstantiationAwareBeanPostProcessor`**, cho phép nó tham gia cả **xác định constructor** lẫn **population/injection** của instance.

Với `AnnotationConfigApplicationContext` và Java configuration thông thường, Spring đã **đăng ký sẵn các annotation processors thiết yếu**. Vì vậy ví dụ dùng `@Autowired` không cần tự `new AutowiredAnnotationBeanPostProcessor()`.

Trong XML-based context cấu hình thủ công, những cơ chế như `<context:annotation-config/>` hoặc `<context:component-scan/>` giúp đăng ký processor thích hợp. **Chỉ có XML `<bean>` không bảo đảm mọi annotation injection sẽ tự chạy nếu hạ tầng tương ứng không được bật.**

Cần phân biệt: `@Bean` hoặc `@Component` đưa **định nghĩa bean** vào container, còn `@Autowired` yêu cầu **resolve/cấp cộng tác viên** cho một đối tượng đã thuộc quá trình tạo bean. Có bean definition không đồng nghĩa tất cả các dependency đã được resolve hoặc instance đã tồn tại.

## 3. Toàn bộ pipeline từ metadata đến bean sẵn sàng

Đây là **mô hình khái niệm** của một singleton Spring-managed bean thông dụng; trình tự nội bộ có nhiều nhánh cho factory method, scope, lazy, proxy và các extension points khác.

~~~text
Đăng ký @Configuration / @Bean / @Component / registerBean(...)
                             |
                             v
                BeanDefinitions trong factory
                             |
                        context.refresh()
                             |
                Đăng ký BeanPostProcessors
                             |
                 Cần tạo bean đích hay chưa?
                       /             \
                      /               \
            Lazy/prototype        Eager singleton
              có thể đợi               |
                     \                /
                      v              v
         Xác định bean class, factory method,
           candidate constructors, metadata
                             |
           Resolve required constructor args
                             |
                    Tạo Java instance
                             |
         Xử lý @Autowired trên instance fields
                             |
         Xử lý @Autowired trên config methods
                             |
             Các bước population liên quan
                             |
          Aware / before-init / init callbacks
                             |
       Bean sẵn sàng; có thể qua proxy hậu xử lý
                             |
                 getBean(...) cho client
                             |
          close() -> destroy callbacks phù hợp
~~~

### Trước khi khởi tạo object

Spring dùng metadata và các extension points để xác định **constructor phù hợp** hoặc factory method sẽ tạo object. Nếu constructor có tham số, dependencies của các tham số được resolve **để có đối số cho lời gọi constructor**. Vì thế constructor injection **không phải** thao tác gán field sau construction.

### Sau khi khởi tạo object

Nếu class có `@Autowired` trên field hoặc method, processor tìm các injection points cần thiết và sử dụng dependency resolution của bean factory để cấp các reference. **Field injection xảy ra sau constructor**, và trong luồng xử lý thông thường fields được inject trước các autowired configuration methods.

### Trước khi bàn giao bean

Container hoàn tất các bước property population và initialization tương ứng, có thể chạy **`InitializingBean.afterPropertiesSet()`** hoặc init method. Sau các BeanPostProcessor khác, bean được trả cho client; một số tính năng như AOP có thể tạo proxy nên **object trả về không nhất thiết cùng runtime class với target**.

**Không khẳng định Spring tạo tất cả beans ngay trong `refresh()`:** singleton không lazy thường pre-instantiate khi context refresh, còn bean lazy hoặc prototype có thể tạo sau lúc được yêu cầu. Một lazy bean vẫn có thể bị tạo sớm nếu dependency eager khác bắt buộc cần nó.

## 4. Chọn constructor: trước khi instance xuất hiện

Có thể gắn `@Autowired` trên constructor:

~~~java
// Snippet, giả sử type MessageSource đã khai báo.
final class Consumer {
    private final MessageSource source;

    @Autowired
    Consumer(MessageSource source) {
        this.source = source;
    }
}
~~~

Spring cần tìm một bean phù hợp với `MessageSource` **trước** khi gọi constructor. Do đó field `source` có thể là `final` và object được xây dựng với một dependency rõ ràng.

Quy tắc đáng nhớ của Spring:
- Nếu class bean **chỉ khai báo một constructor**, constructor đó thường được Spring dùng **không cần** `@Autowired`.
- Nếu class có **nhiều constructors**, Spring phải có quy tắc/metadata để chọn. Một constructor được đánh dấu `@Autowired(required = true)` (mặc định) là lựa chọn bắt buộc; không thể đặt nhiều constructor cùng required `true`.
- Với nhiều constructors được đánh dấu non-required (`required=false`), Spring có thể đánh giá candidates theo mức dependency có thể resolve, rồi dùng default/primary constructor khi quy tắc cho phép. Đây **không phải** cam kết rằng mọi overload được thử tùy tiện.
- Constructor riêng tư/không `public` có thể được Spring sử dụng khi khả năng truy cập phản chiếu của môi trường cho phép.
- **Lỗi thiếu dependency bắt buộc** có thể xuất hiện khi bean được khởi tạo, và với eager singleton đó thường là trong `refresh()`.

Nếu class được tạo bằng **`@Bean` factory method**:

~~~java
@Bean
Consumer consumer(MessageSource source) {
    return new Consumer(source);
}
~~~

Spring resolve tham số **factory method** rồi gọi đoạn `new Consumer(source)` do bạn viết. Đây cũng là một dạng DI do container thực hiện, nhưng **đừng mô tả nhầm rằng Spring đang tự chọn constructor của `Consumer` trong factory method**: chính factory method đã chọn constructor trong source Java.

## 5. Inject vào field và method: sau constructor

### Field injection

~~~java
@Autowired
private Audit audit;
~~~

Processor xác định field cần gán rồi resolve `Audit` phù hợp. Nếu bean không có candidate và injection point là required, bean creation có thể thất bại. Field không cần `public`, nhưng phải thuộc đối tượng Spring-managed và environment cho phép reflection thích hợp.

Không thiết kế required fields để chỉ được gán sau construction rồi truy cập ngay trong constructor. `private final Audit audit` thường phù hợp **constructor injection**, không phải field injection.

### Setter hoặc arbitrary configuration method

~~~java
@Autowired
void configure(Audit audit) {
    this.audit = audit;
}
~~~

Tên method **không bắt buộc** theo mẫu `setX`. Spring cũng có thể resolve **nhiều tham số** của một config method nếu các dependency tương ứng tồn tại. Với method injection, các tham số được resolve trước khi Spring gọi method; lỗi thiếu bean ở một tham số có thể làm toàn method injection không hoàn thành.

Ví dụ thứ tự quan sát được trong demo của bài:
1. Constructor in rằng field chưa được gán.
2. Field `audit` được Spring tiêm.
3. Method `configureAudit(Audit)` được gọi, thấy field đã có reference.
4. `afterPropertiesSet()` quan sát trạng thái bean đã được cung cấp các dependency.

Đây là mô hình kiểm chứng **lifecycle injection** của một bean bình thường; không cần hardcode danh sách tất cả các processors hay thứ tự bean definitions nội bộ.

### Những vị trí không nên dùng

`@Autowired` không phải cơ chế DI **vào static field/method** thông thường. Đừng cố dùng `@Autowired static Repo repo` để có dependency toàn JVM. Tương tự, một instance tạo qua `new` nằm ngoài container sẽ không nhận field/method injection tự động.

Trong Java module path, reflection đối với field/method không-public có thể cần thiết lập `opens` phù hợp. Dự án demo dùng **classpath** nên không đưa những giới hạn JPMS vào bước chạy cơ bản.

## 6. Spring tìm bean phù hợp như thế nào?

Dependency resolution dựa trước hết vào **kiểu** và metadata của injection point. Spring có thể xét type (kể cả generic type), các qualifiers, tập bean candidates, primary/fallback, tên injection point và những luật ưu tiên tương ứng.

| Tình huống | Kết quả hoặc cách xử lý |
| --- | --- |
| Một bean có type phù hợp, injection required | Bean được chọn và reference được cấp |
| Không có bean phù hợp, required | Thông thường **bean creation thất bại** |
| Nhiều beans cùng type, không có cách phân giải | Có thể gặp `NoUniqueBeanDefinitionException` |
| Có bean được đánh dấu `@Primary` trong tập phù hợp | Bean primary có thể được ưu tiên khi resolve single-valued dependency |
| Injection point có `@Qualifier("name")` | Thu hẹp candidates theo qualifier/name phù hợp, **không tạo bean mới** |
| Generic types khác nhau | Spring có thể dùng generic type như một dạng qualifier |
| `List<T>`, `T[]`, `Map<String,T>` | Có thể inject tập beans phù hợp; `Map` dùng bean names làm keys |
| Nhiều context cha/con | Resolution có thể liên quan hierarchy, visibility và local overrides theo quy tắc container |

**Không nên viết “Spring luôn tìm theo tên rồi mới theo type”.** Autowiring được thiết kế theo type và những điều kiện chọn candidate; bean name/parameter name có thể tham gia khi loại/qualifier và các ưu tiên cho phép, nhưng không phải một luật đơn giản dùng cho mọi trường hợp.

Ví dụ minh họa (không phải project độc lập):

~~~java
@Autowired
@Qualifier("fastGateway")
private Gateway gateway;
~~~

Spring cần một bean `Gateway` phù hợp với qualifier. `fastGateway` trong annotation là thông tin **chọn dependency**, không phải hướng dẫn tạo một `Gateway` mới. Khi class có nhiều implementation, hãy đặt qualifiers rõ và tránh phụ thuộc vào tên tham số không được giữ lại khi biên dịch.

**Điểm dễ nhầm:** một bean tên giống field không bảo đảm luôn được chọn nếu bean type không tương thích hoặc bị loại bởi qualifier/candidate filters. Một `@Primary` không làm thay đổi Java type hay tạo alias.

## 7. Required, optional và provider được xử lý khác nhau

Theo mặc định, field/method `@Autowired` là **required**. Khi thiếu bean, container thường fail tại thời điểm tạo bean. Tuy nhiên Spring hỗ trợ những cách biểu đạt dependency thực sự **tùy chọn**.

### `@Autowired(required = false)`

~~~java
@Autowired(required = false)
void configureMissing(MissingNotifier missing) {
    // Spring có thể bỏ qua lời gọi method nếu không có candidate.
}
~~~

Với **non-required config method**, khi thiếu một dependency không thể thỏa, Spring có thể **không gọi cả method**. Đối với non-required field, trường có thể giữ giá trị ban đầu. Không đồng nhất hành vi với việc Spring tự truyền `null` cho mọi tham số.

### `Optional<T>`

~~~java
@Autowired
private Optional<Metrics> metrics;
~~~

Spring có thể cung cấp `Optional.empty()` khi không có bean `Metrics` phù hợp, thay vì từ chối bean chứa field. Khi có candidate, `Optional` có thể giữ reference tới bean. Mã business phải thực sự xử lý nhánh empty.

**Không gọi `metrics.get()` vô điều kiện** khi dependency optional. Đừng dùng optional cho chức năng bắt buộc về mặt nghiệp vụ chỉ để làm context “khởi động được”.

### `ObjectProvider<T>`

~~~java
@Autowired
private ObjectProvider<MissingNotifier> notifierProvider;
~~~

Container inject một **provider**, không nhất thiết tạo bean đích ngay khi inject. `notifierProvider.getIfAvailable()` có thể trả `null` nếu không có bean; `getObject()` đòi bean thực và có thể ném exception nếu thiếu. Provider có ích khi cần **lấy dependency theo nhu cầu**, đặc biệt với prototype hoặc lazy behavior.

### `@Nullable`

Spring có thể hiểu **nullability annotation được hỗ trợ** (như JSpecify `org.jspecify.annotations.Nullable` ở các Spring lines hiện đại) trên injection point để biểu thị được phép vắng mặt. Hãy dùng đúng annotation và dependency tương ứng cho version đang chạy; đây **không phải** một cơ chế Java compiler tự thêm bean.

**Đối với arrays/collections/maps:** tài liệu Spring mô tả default required semantics có thể cần ít nhất một candidate cho những injection points bắt buộc. Có các ngoại lệ theo loại điểm inject và phiên bản (chẳng hạn tham số của một constructor duy nhất có thể nhận empty collection), nên không suy luận rằng mọi `List<T>` required đều luôn empty khi thiếu.

## 8. Dự án Maven Java 17 chạy được: quan sát từng giai đoạn

Ví dụ tạo một bean `Consumer` có **constructor `@Autowired`**, **field `@Autowired`**, **method `@Autowired`**, `Optional<Metrics>`, `ObjectProvider<MissingNotifier>`, một optional method bị bỏ qua và callback `InitializingBean.afterPropertiesSet()`.

Để loại bỏ nhầm lẫn về component scan, `Consumer` được **đăng ký tường minh bằng `registerBean(Consumer.class)`**. `AppConfig` khai báo `MessageSource` và `Audit`. Context tự kích hoạt annotation processors thích hợp.

### 8.1. Cấu trúc

~~~text
autowired-pipeline-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AutowiredPipelineDemo.java
~~~

Yêu cầu **JDK 17+**, **Maven 3.9+** và khả năng tải Maven dependencies ở lần chạy đầu.

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>autowired-pipeline-demo</artifactId>
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
                    <mainClass>demo.AutowiredPipelineDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp các Spring API trong bài và tự kéo Spring artifacts nền tương ứng qua Maven dependency resolution. Không cần Spring Boot, annotation processing plugin của Java compiler hay web starter. Maven Compiler Plugin biên dịch với `--release 17`.

### 8.3. `src/main/java/demo/AutowiredPipelineDemo.java`

~~~java
package demo;

import java.util.Optional;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class AutowiredPipelineDemo {
    private AutowiredPipelineDemo() {
    }

    @FunctionalInterface
    interface MessageSource {
        String message(String name);
    }

    interface Metrics {
    }

    interface MissingNotifier {
        void notifyEvent(String event);
    }

    record Audit(String label) {
    }

    static final class Consumer implements InitializingBean {
        private final MessageSource source;

        @Autowired
        private Audit audit;

        @Autowired
        private Optional<Metrics> metrics;

        @Autowired
        private ObjectProvider<MissingNotifier> notifierProvider;

        private Audit auditFromMethod;
        private boolean optionalMethodCalled;

        @Autowired
        Consumer(MessageSource source) {
            this.source = source;
            System.out.println("constructor.fieldNull=" + (audit == null));
        }

        @Autowired
        void configureAudit(Audit selectedAudit) {
            this.auditFromMethod = selectedAudit;
            System.out.println("method.fieldReady=" + (audit != null));
        }

        @Autowired(required = false)
        void configureMissing(MissingNotifier notifier) {
            optionalMethodCalled = true;
        }

        @Override
        public void afterPropertiesSet() {
            boolean ready = source != null
                    && audit != null
                    && auditFromMethod != null
                    && metrics != null
                    && notifierProvider != null;
            System.out.println("init.ready=" + ready);
            System.out.println("init.metricsAbsent=" + metrics.isEmpty());
        }

        String message(String name) {
            return source.message(name);
        }

        boolean sameAudit() {
            return audit == auditFromMethod;
        }

        boolean optionalMethodSkipped() {
            return !optionalMethodCalled;
        }

        boolean providerMissing() {
            return notifierProvider.getIfAvailable() == null;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public MessageSource messageSource() {
            return name -> "Hello, " + name + "!";
        }

        @Bean
        public Audit audit() {
            return new Audit("trace");
        }
    }

    public static void main(String[] args) {
        // Context rỗng: đăng ký config và Consumer, sau đó refresh.
        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(AppConfig.class);
            context.registerBean(Consumer.class);
            context.refresh();

            Consumer consumer = context.getBean(Consumer.class);
            System.out.println("lookup.message=" + consumer.message("Lan"));
            System.out.println("lookup.sameAudit=" + consumer.sameAudit());
            System.out.println("optional.setterSkipped="
                    + consumer.optionalMethodSkipped());
            System.out.println("optional.providerMissing="
                    + consumer.providerMissing());
            System.out.println("scope.singleton="
                    + (consumer == context.getBean(Consumer.class)));
        }

        // Thiếu dependency bắt buộc: exception khi context.refresh().
        try (var missing = new AnnotationConfigApplicationContext()) {
            missing.registerBean(Consumer.class);
            missing.refresh();
        } catch (BeansException expected) {
            System.out.println("missingRequired.failed=true");
        }
    }
}
~~~

**Giải thích các điểm kiểm chứng:**

1. `register(AppConfig.class)` và `registerBean(Consumer.class)` làm xuất hiện các bean definitions. Constructor `Consumer(MessageSource)` được xử lý như injection point; Spring phải resolve `MessageSource` để tạo object.
2. Constructor quan sát `audit == null` → `true`, vì **field injection chưa xảy ra** ở giai đoạn đang chạy constructor.
3. Khi `configureAudit(Audit)` chạy, field `audit` đã có reference; đó là bằng chứng field injection đến **trước autowired method injection** trong demo này.
4. `afterPropertiesSet()` được gọi khi các injection points đã được xử lý. `init.ready=true` không phải phép đo mọi tác vụ initialization/proxy trong Spring; nó chỉ xác nhận các dependency cần quan sát ở demo đều có sẵn.
5. Không có bean `Metrics`, nên Spring tiêm `Optional.empty()` và `init.metricsAbsent=true`.
6. Không có bean `MissingNotifier`: non-required method `configureMissing` không được gọi; `ObjectProvider` vẫn được inject, và `getIfAvailable()` không tìm thấy bean.
7. `Consumer` mặc định singleton. Lấy hai lần từ cùng context cho cùng reference.
8. Context thứ hai chỉ đăng ký `Consumer`, cố ý thiếu `MessageSource` bắt buộc. Tạo Consumer không thành công; chương trình catch `BeansException` và in một dòng, không phụ thuộc chính xác class/message/stack trace.

**Điểm quan trọng về lambda:** `MessageSource` là interface có một abstract method nên biểu thức `name -> "Hello, " + name + "!"` hợp lệ trong Java 17. `Audit` là Java `record`, cũng là cú pháp được hỗ trợ trong Java 17.

**Không kết luận `@Autowired` xử lý `Consumer` vì class có `@Component`:** class ở đây **không có** `@Component`; nó được `registerBean` trực tiếp. Điều cần thiết là nó thuộc container và có annotation processor thích hợp.

## 9. Build, chạy và expected stdout

Từ thư mục `autowired-pipeline-demo` có `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Các lệnh phiên bản môi trường không có một stdout chung cố định. Lệnh cuối dùng Maven gọi compiler và chạy main class với classpath Spring tương ứng.

**10 dòng stdout của code demo** (không tính log framework hoặc Maven diagnostics):

~~~text
constructor.fieldNull=true
method.fieldReady=true
init.ready=true
init.metricsAbsent=true
lookup.message=Hello, Lan!
lookup.sameAudit=true
optional.setterSkipped=true
optional.providerMissing=true
scope.singleton=true
missingRequired.failed=true
~~~

**Vì sao thứ tự này hợp lý?**
- Ba dòng đầu cùng dòng `init.metricsAbsent` được in khi context thứ nhất tạo singleton Consumer trong `refresh()`, trước khi `getBean` trả bean cho đoạn code ở `main`.
- Nhóm `lookup.*`, `optional.*`, `scope.*` do code `main` in khi context đã active.
- Dòng cuối xảy ra khi context thứ hai cố tạo Consumer thiếu dependency required, rồi bị catch; lỗi đó có thể được Spring logging ghi thêm diagnostic không nằm trong các dòng `System.out.println` chuẩn.

Bạn có thể kiểm tra biến thể với `@Lazy` trên Consumer: nếu không có bean eager khác cần nó, các dòng constructor/method/init có thể được trì hoãn tới lần `getBean(Consumer.class)` thay vì lúc refresh. **Autowiring vẫn là cùng cơ chế**, chỉ thay đổi thời điểm yêu cầu tạo bean.

## 10. Java 17 thuần: tại sao annotation không tự chạy?

Để tách hành vi Java khỏi Spring, tạo tệp riêng `PureJavaInjection.java` và chạy hoàn toàn không cần Maven/JAR Spring:

~~~java
public class PureJavaInjection {
    interface Greeter {
        String greet(String name);
    }

    static final class Service {
        private Greeter field;

        Service() {
            System.out.println("constructor.fieldNull="
                    + (field == null));
        }

        void setGreeter(Greeter value) {
            field = value;
        }

        String greet(String name) {
            return field.greet(name);
        }
    }

    public static void main(String[] args) {
        Service service = new Service();
        System.out.println("beforeManualInjection="
                + (service.field == null));
        service.setGreeter(name -> "Fake:" + name);
        System.out.println("afterManualInjection="
                + service.greet("Lan"));
    }
}
~~~

Lệnh chạy từ thư mục chứa file:

~~~bash
javac PureJavaInjection.java
java PureJavaInjection
~~~

Stdout:

~~~text
constructor.fieldNull=true
beforeManualInjection=true
afterManualInjection=Fake:Lan
~~~

Đây **không** phải ví dụ `@Autowired` trực tiếp; nó cố ý chỉ minh họa cơ chế object được tạo trước rồi được cấp dependency sau. Spring tự động hóa phần tìm/cấp bean khi bean thuộc container. Java thuần không tự thực thi annotation của một framework nếu không có hạ tầng xử lý.

Mặt khác, **constructor injection** vẫn có thể làm hoàn toàn bằng Java: `new Service(greeter)` với constructor nhận `Greeter` là một cách DI thủ công hợp lệ. Container giúp tổ chức resolution và lifecycle, không thay thế ngôn ngữ Java.

## 11. Những lỗi thường gặp khi `@Autowired` không hoạt động

| Triệu chứng | Tầng gây lỗi | Hướng điều tra |
| --- | --- | --- |
| Field `@Autowired` còn null trong object tự `new` | Object **ngoài container** | Đăng ký bean hoặc chuyển sang constructor injection để test Java thuần |
| Class có `@Autowired` nhưng context không biết class | **Không có bean definition** | Dùng `@Component` + scan đúng package, `@Bean` hoặc `registerBean` |
| XML bean có annotation nhưng không được inject | **Thiếu annotation post-processors** | Bật `<context:annotation-config/>` / component scan hoặc processor tương ứng |
| Không có bean cùng type | **Required dependency resolution** | Đăng ký đúng type/qualifier, xem chain `Caused by` |
| Nhiều beans cùng type | **Ambiguous candidates** | `@Primary`, `@Qualifier` hoặc cấu hình lựa chọn minh bạch |
| Field được dùng ngay trong constructor | **Sai thứ tự lifecycle** | Chuyển required dependency sang constructor |
| `@Autowired(required=false)` method không chạy | Optional injection point **không thỏa** | Giữ default state hợp lệ; không coi đó là lỗi nếu dependency thực sự optional |
| `ObjectProvider.getObject()` ném exception | Chọn API **required lookup** | Cân nhắc `getIfAvailable()` và fallback có chủ đích |
| `Optional<T>` rỗng dù muốn có bean | Bean không đăng ký, sai type/qualifier hoặc config ngoài dự kiến | Xác định đúng context/bean registrations; đừng gọi `get()` mù quáng |
| `@Autowired` lên static field không có hiệu lực | **Static member không hỗ trợ kiểu injection này** | Thiết kế instance service; tránh global mutable state |
| Sai `@Qualifier` | Không có candidate đúng qualifier | Đối chiếu bean name/qualifier metadata và injection point |
| Java source import Spring không compile | **Classpath/build**, không phải autowiring | Kiểm `spring-context`, build tool, dependency versions |
| Bean không được post-process đầy đủ | Bean được tạo quá sớm, custom BPP/FactoryPostProcessor hay manual lifecycle | Xem giai đoạn registration và bean creation |
| Circular constructor dependencies | Đồ thị **không có thứ tự dựng object hợp lệ** | Tách trách nhiệm, đổi hướng phụ thuộc; tránh biến required thành optional để che lỗi |

**Một giới hạn quan trọng:** Các chính `BeanPostProcessor` và `BeanFactoryPostProcessor` có vòng đời **đặc biệt** và được đăng ký/khởi tạo sớm. Tài liệu Spring cảnh báo không trông chờ `@Autowired`/`@Inject`/`@Value`/`@Resource` xử lý đầy đủ **bên trong những processor do bạn tự viết**; nên cấu hình dependencies của chúng rõ ràng bằng factory methods hoặc XML theo hướng dẫn framework.

Ngoài ra, nếu một custom `BeanPostProcessor` được đăng ký quá muộn thì một số beans đã tạo trước đó **không được xử lý lại**. Vì thế việc “đã thấy annotation” không đủ để đảm bảo DI đúng; phải xem hạ tầng processor đã tham gia vào **lifecycle của bean đích** hay chưa.

## 12. Kiểm chứng độc lập, debug và lựa chọn thiết kế

### Khi cần quan sát pipeline

- Đặt breakpoint tại constructor của bean, method `@Autowired`, `afterPropertiesSet()` để thấy các giai đoạn.
- Trong Spring source/debugger, xem `AutowiredAnnotationBeanPostProcessor` và cơ chế `DefaultListableBeanFactory.resolveDependency`. Đây là **cơ chế nội bộ để học**, không phải API nên gọi từ business code.
- Dùng `getBeanDefinitionNames()`, `getBeanNamesForType` để điều tra registrations; **không hardcode số bean definitions** vì các processors và infrastructure beans cũng được đăng ký.
- Đọc exception `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException` theo **cause chain**. Chuỗi message chính xác không phải một contract ổn định qua mọi patch.
- Test bean wiring bằng context nhỏ khi cần; dùng fake và constructor injection cho các unit tests chỉ kiểm tra logic.

### Khi nào dùng field, setter hay constructor?

- **Required dependency:** ưu tiên **constructor injection** + field `final` và invariant validation; một constructor duy nhất thường không cần `@Autowired`.
- **Truly optional/configurable dependency:** có thể dùng `Optional<T>`, `ObjectProvider<T>` hoặc setter có default hợp lệ, tùy thời điểm cần resolve.
- **Method injection nhiều đối số:** hữu ích khi cần cấu hình object trong một bước, nhưng cần hiểu required semantics và việc gọi sau construction.
- **Không dùng `@Autowired` để giấu đồ thị quá lớn:** constructor có rất nhiều dependencies có thể báo hiệu class đang ôm nhiều trách nhiệm, cần phân chia thiết kế thay vì chuyển toàn bộ sang private fields để trông ngắn hơn.
- **Không dùng `ApplicationContext.getBean` rải khắp nghiệp vụ:** thường nên nhận dependency qua constructor thay vì phụ thuộc service locator.
- **Không cho rằng `@Autowired` tự tạo bean class chưa được đăng ký:** annotation giải quyết wiring cho bean đang tạo, không thay thế registration/composition root.

## 13. Bài tập và checklist tự đánh giá

Làm từng thử nghiệm **trên một bản sao** và khôi phục code gốc trước khi so stdout mục 9.

1. **Chuyển `Consumer` sang một constructor duy nhất không có `@Autowired`:** dự đoán khả năng Spring tự dùng constructor ấy.
2. **Bỏ bean `MessageSource`:** context đầu tiên có thể fail khi constructor của Consumer cần `MessageSource`. Vì sao `Optional<Metrics>` vẫn không giải quyết được?
3. **Bỏ bean `Audit`:** constructor có thể vẫn chạy và in field null, nhưng required field/method injection sẽ fail sau đó. Tách lỗi constructor resolution với property population.
4. **Thêm bean `Metrics`:** dự đoán `init.metricsAbsent=false` và giải thích `Optional.of(bean)`.
5. **Thêm bean `MissingNotifier`:** dự đoán optional method `configureMissing` được gọi, provider lấy được bean và hai dòng `optional.*` đổi giá trị.
6. **Thêm hai implementations `MessageSource`:** dự đoán khả năng ambiguity; giải quyết bằng `@Primary` hoặc `@Qualifier`.
7. **Đổi thứ tự khai báo `@Bean` methods:** có thay đổi bản chất dependency resolution không? Tránh suy luận tuyệt đối từ source ordering.
8. **Đặt `@Lazy` lên `Consumer`:** dự đoán constructor/method/init log xuất hiện lúc `getBean` thay vì refresh khi không có eager consumer.
9. **Gọi `new Consumer(fake)` ngoài Spring:** constructor vẫn chạy, nhưng các field/method `@Autowired` không được xử lý; nếu dùng `afterPropertiesSet` thủ công, tại sao gọi nó không tự inject?
10. **Đổi `@Autowired(required=false)` sang required method:** context đầu tiên có còn khởi động bình thường nếu thiếu `MissingNotifier`?
11. **So constructor vs factory method:** chuyển Consumer sang `@Bean Consumer consumer(MessageSource source)`, giải thích vì sao Spring resolve method parameter nhưng code Java chọn constructor.
12. **Viết unit test:** truyền fake `MessageSource` vào một class chỉ dùng constructor injection để kiểm tra behavior mà không mở context. Viết integration test chỉ khi muốn kiểm tra processor/registration.
13. **Kiểm tra scope:** đổi Consumer thành prototype và lấy hai lần; quan sát mỗi instance được post-process và có dependency riêng theo quy tắc scope.

**Checklist:**
- [ ] Phân biệt annotation **metadata** với DI do container thực thi.
- [ ] Biết vai trò `AutowiredAnnotationBeanPostProcessor` và các hạ tầng bean factory liên quan.
- [ ] Trình bày đúng thứ tự constructor selection → construction → field/method population → initialization.
- [ ] Phân biệt `@Autowired` constructor với Spring injection của tham số `@Bean` factory method.
- [ ] Biết bean cần được **đăng ký và processor cần tồn tại**.
- [ ] Giải thích được type/qualifier/primary và ambiguity.
- [ ] Biết `Optional<T>`, `ObjectProvider<T>`, non-required method có hành vi khác nhau.
- [ ] Chạy được Maven demo Java 17 ra đúng **10 dòng stdout** và Java thuần ra **3 dòng**.
- [ ] Biết vì sao static fields, tự `new` objects và processor quá sớm không phải đường injection thông thường.
- [ ] Không coi `@Autowired` là lời bảo đảm business logic hoặc concurrency đúng.

## 14. Tóm tắt và nguồn tham khảo chính thức

**Tóm tắt cơ chế:**

1. Đăng ký nguồn cấu hình → Spring có **bean definitions**.
2. Khi cần tạo bean, container xem metadata và **chọn constructor/factory method**; resolve những required args tương ứng.
3. Container tạo object; `AutowiredAnnotationBeanPostProcessor` thực hiện **field/method injection** ở các injection points được hỗ trợ.
4. Container xử lý initialization/lifecycle và có thể áp dụng các processors khác/proxies trước khi đưa bean cho client.
5. Scope, lazy, optional/required và bean candidates quyết định **khi nào** và **bean nào** được cấp.

Tài liệu chính thức:
- [Spring Framework – Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework – Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring API – AutowiredAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html)
- [Spring Framework – Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework – Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)

**Ghi nhớ:** `@Autowired` **không tự tạo bean và không chạy chỉ vì annotation tồn tại**. Nó là metadata được Spring đọc **khi tạo một bean thuộc container**, từ đó chọn/cấp dependency theo type và các quy tắc candidate, required/optional, rồi hoàn tất vòng đời bean. Nắm pipeline ấy giúp giải thích những lỗi autowiring mà việc chỉ đổi một annotation không thể sửa được.