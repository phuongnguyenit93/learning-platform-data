# Vì sao prototype tiêm trực tiếp vào singleton không đổi mỗi lần gọi?

## 1. Vấn đề cần hiểu

Trong Spring Framework Core Container, `singleton` là scope mặc định: đối với một bean definition, container giữ một bean instance để tái sử dụng. `prototype` có nghĩa là **mỗi lần Spring được yêu cầu cung cấp bean prototype**, container tạo một instance mới.

Nghe có vẻ mâu thuẫn khi ta khai báo một bean `prototype`, inject nó qua constructor vào singleton, rồi gọi phương thức singleton nhiều lần mà vẫn nhận cùng instance. Hành vi này **đúng với quy tắc scope**.

> **Câu trả lời cốt lõi:** Spring giải quyết dependency khi nó **tạo và lắp ráp singleton**. Một instance prototype được tạo tại thời điểm đó và được lưu trong field/constructor parameter của singleton. Các lần gọi phương thức của singleton sau này chỉ đọc lại tham chiếu Java đã lưu; chúng không tự trở thành yêu cầu lấy bean mới từ Spring.

Nếu muốn có prototype mới **mỗi lần thực hiện một nghiệp vụ**, phải yêu cầu Spring lấy bean **tại thời điểm nghiệp vụ chạy**, chẳng hạn bằng `ObjectProvider<T>.getObject()` hoặc lookup method.

### Mục tiêu học tập

Sau bài này bạn có thể:

- Phân biệt **mỗi lần container được yêu cầu tạo bean** với **mỗi lần gọi method Java**.
- Giải thích thời điểm dependency được resolve trong constructor injection, field injection và setter injection.
- Quan sát chính xác singleton giữ nguyên một prototype và cách lấy prototype mới theo nhu cầu.
- Chọn giữa direct injection, `ObjectProvider`, `@Lookup` và scoped proxy dựa trên vòng đời cần thiết.
- Tránh lỗi giữ mutable state giữa các lời gọi và hiểu trách nhiệm dọn dẹp prototype.

## 2. Hai scope hoạt động độc lập

Hãy xem hai bean definition:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class CalculationState {
}

@Service
class CalculationService {
    private final CalculationState state;

    CalculationService(CalculationState state) {
        this.state = state;
    }

    CalculationState currentState() {
        return state;
    }
}
~~~

Đây là **mã minh họa**: cần các import Spring, component scan và application context để chạy. `CalculationState` được khai báo `prototype`; `CalculationService` không có `@Scope` nên mặc định `singleton`.

| Sự kiện | Spring có được yêu cầu cung cấp `CalculationState` mới không? | Kết quả |
| --- | --- | --- |
| Container tạo `CalculationService` và resolve constructor argument | Có | Tạo prototype P1 và inject vào service |
| Gọi `service.currentState()` lần 1 | Không | Trả field đang trỏ P1 |
| Gọi `service.currentState()` lần 2 | Không | Vẫn là P1 |
| Gọi `context.getBean(CalculationState.class)` | Có | Tạo prototype P2 |
| Gọi lại `context.getBean(CalculationState.class)` | Có | Tạo prototype P3 |

Một instance P1 có thể được sử dụng mãi bên trong singleton mà vẫn **không biến bean definition prototype thành singleton**. Nếu nơi khác yêu cầu `CalculationState` từ container, mỗi lần yêu cầu vẫn nhận một prototype mới.

**Scope mô tả cách container trả bean khi được hỏi, không mô tả tần suất gọi method của object đang giữ bean đó.**

## 3. Diễn tiến từ lúc tạo singleton đến khi chạy nghiệp vụ

Với constructor injection, ta có thể biểu diễn thứ tự như sau:

~~~text
ApplicationContext khởi động
        |
        v
Spring đọc bean definition
        |
        v
Spring chuẩn bị tạo CalculationService (singleton)
        |
        +----> Resolve dependency CalculationState
        |                  |
        |                  v
        |          Prototype P1 được tạo
        |                  |
        +<-----------------+
        |
        v
new CalculationService(P1)
        |
        v
Container cache singleton CalculationService
        |
        +---- service.currentState() ---> P1
        +---- service.currentState() ---> P1
        +---- service.currentState() ---> P1
        |
        +---- context.getBean(CalculationState) ---> P2
        +---- context.getBean(CalculationState) ---> P3
~~~

Những điểm quyết định:

1. **Dependency resolution diễn ra tại thời điểm tạo singleton.** Với non-lazy singleton, thời điểm đó thường là trong quá trình khởi tạo Spring context; với lazy singleton, là lúc singleton lần đầu được tạo.
2. Constructor chỉ chạy **một lần cho instance singleton đó**. Nó nhận P1, rồi lưu tham chiếu vào field `state`.
3. `currentState()` là method Java thông thường. Không có `BeanFactory.getBean(...)`, provider, lookup hay proxy nào trong đường gọi này để Spring tạo P2.
4. `@Scope("prototype")` vẫn có hiệu lực khi Spring nhận **yêu cầu mới** cho bean prototype từ provider, BeanFactory hoặc injection point khác.
5. Trong Spring, một singleton là một bean instance **trong một container trên mỗi bean definition**, không nhất thiết là một đối tượng duy nhất trong toàn JVM.

### Constructor, field và setter injection có khác nhau không?

Ba hình thức injection thông dụng đều xảy ra trong quá trình container tạo/cấu hình object:

~~~java
// Constructor injection: prototype được resolve cho constructor.
public WorkerService(WorkState workState) {
    this.workState = workState;
}

// Field injection: prototype được resolve khi Spring populate field.
@Autowired
private WorkState workState;

// Setter injection: prototype được resolve khi Spring gọi setter.
@Autowired
void setWorkState(WorkState workState) {
    this.workState = workState;
}
~~~

Ba đoạn trên minh họa **ba lựa chọn thay thế trong một class**, không ghép nguyên xi cùng một lúc. Cả ba đều không làm Spring inject lại một prototype mới **sau mỗi lần** gọi method nghiệp vụ. Tự gọi một setter với object mới là một hành động Java riêng, không phải đặc tính tự động của prototype.

## 4. Ví dụ chạy được bằng Java 17 và Spring Context 6.1

Đây là ứng dụng Java thuần sử dụng `AnnotationConfigApplicationContext`. Không cần Spring Boot hoặc máy chủ HTTP. Ví dụ chứng minh cả **direct injection giữ một prototype** và **`ObjectProvider` lấy prototype mới** bằng phép so sánh object identity và output xác định.

### 4.1. Cấu trúc thư mục

~~~text
prototype-singleton-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── demo/
                        └── PrototypeSingletonDemo.java
~~~

### 4.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>prototype-singleton-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.demo.PrototypeSingletonDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.3. `PrototypeSingletonDemo.java`

~~~java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class PrototypeSingletonDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            FixedConsumer fixed = context.getBean(FixedConsumer.class);
            ProviderConsumer dynamic = context.getBean(ProviderConsumer.class);

            JobState fixedFirst = fixed.current();
            JobState fixedSecond = fixed.current();

            JobState dynamicFirst = dynamic.newJob();
            JobState dynamicSecond = dynamic.newJob();

            System.out.println(
                    "Same singleton service: " +
                    (fixed == context.getBean(FixedConsumer.class)));

            System.out.println(
                    "Directly injected prototype reused: " +
                    (fixedFirst == fixedSecond));

            System.out.println(
                    "Direct state counter: " +
                    fixed.process() + ", " + fixed.process());

            System.out.println(
                    "ObjectProvider gives new prototypes: " +
                    (dynamicFirst != dynamicSecond));

            System.out.println(
                    "Two getBean calls give new prototypes: " +
                    (context.getBean(JobState.class) !=
                     context.getBean(JobState.class)));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public JobState jobState() {
            return new JobState();
        }

        @Bean
        public FixedConsumer fixedConsumer(JobState jobState) {
            return new FixedConsumer(jobState);
        }

        @Bean
        public ProviderConsumer providerConsumer(
                ObjectProvider<JobState> jobStates) {
            return new ProviderConsumer(jobStates);
        }
    }

    public static class JobState {
        private final AtomicInteger steps = new AtomicInteger();

        public int nextStep() {
            return steps.incrementAndGet();
        }
    }

    public static class FixedConsumer {
        private final JobState state;

        public FixedConsumer(JobState state) {
            this.state = state;
        }

        public JobState current() {
            return state;
        }

        public int process() {
            return state.nextStep();
        }
    }

    public static class ProviderConsumer {
        private final ObjectProvider<JobState> jobStates;

        public ProviderConsumer(ObjectProvider<JobState> jobStates) {
            this.jobStates = jobStates;
        }

        public JobState newJob() {
            return jobStates.getObject();
        }
    }
}
~~~

Các class `JobState`, `FixedConsumer` và `ProviderConsumer` được khai báo ở dạng `public static` nested class để gom trọn ví dụ trong một file; các bean thực sự được đăng ký bằng `@Bean` trong `AppConfig`. Để quan sát cùng đối tượng Java, dùng `==`, không dùng `equals()` vì `equals()` có thể được override theo giá trị nghiệp vụ.

`@Configuration(proxyBeanMethods = false)` vẫn hợp lệ ở đây: từng dependency được Spring truyền vào **tham số factory method**, không có lời gọi trực tiếp từ một `@Bean` method sang một `@Bean` method khác.

### 4.4. Lệnh chạy

Cài JDK 17+ và Maven 3.9+, mở terminal tại thư mục chứa `pom.xml` rồi chạy:

~~~bash
mvn -q compile exec:java
~~~

Output chính xác từ các câu lệnh `System.out.println`:

~~~text
Same singleton service: true
Directly injected prototype reused: true
Direct state counter: 1, 2
ObjectProvider gives new prototypes: true
Two getBean calls give new prototypes: true
~~~

Maven có thể ghi thêm thông báo ra stderr tùy môi trường. Năm dòng trên là stdout chủ động của chương trình, có thể đối chiếu trực tiếp.

### 4.5. Giải thích từng kết quả

- **`Same singleton service: true`:** hai lần gọi `context.getBean(FixedConsumer.class)` trả về cùng singleton trong context.
- **`Directly injected prototype reused: true`:** `FixedConsumer` đã lưu một `JobState` trong field. Gọi `current()` hai lần chỉ trả cùng tham chiếu đó.
- **`Direct state counter: 1, 2`:** do cùng target được giữ, số bước tích lũy qua hai lần gọi `process()`. Nếu công việc cần một trạng thái trống mỗi lần, đây có thể là bug nghiệp vụ.
- **`ObjectProvider gives new prototypes: true`:** mỗi lần `getObject()` là một yêu cầu mới đối với prototype, nên hai object khác nhau.
- **`Two getBean calls give new prototypes: true`:** truy xuất bean prototype trực tiếp từ Spring context cũng tạo instance mới mỗi lần.

Việc `FixedConsumer` giữ một prototype không ảnh hưởng đến các lần lấy `JobState` ở nơi khác. Các instance do provider hoặc `context.getBean(...)` tạo không làm thay đổi field `state` đã inject.

## 5. Tình huống thực tế: state của từng lần xử lý bị giữ qua nhiều request

Giả sử có một singleton service quản lý hoạt động xuất báo cáo và một prototype chứa danh sách lỗi của một lần xuất:

~~~java
@Component
@Scope("prototype")
class ExportState {
    private final List<String> errors = new ArrayList<>();

    void addError(String error) {
        errors.add(error);
    }

    int errorCount() {
        return errors.size();
    }
}

@Service
class ExportService {
    private final ExportState state;

    ExportService(ExportState state) {
        this.state = state;
    }

    int export(boolean invalidInput) {
        if (invalidInput) {
            state.addError("Invalid input");
        }
        return state.errorCount();
    }
}
~~~

Đoạn này là **mã minh họa cần import `@Component`, `@Service`, `@Scope` và `java.util`** trong một ứng dụng đã bật component scan. Nếu gọi:

~~~java
service.export(true);
service.export(false);
~~~

Lời gọi thứ hai vẫn có thể trả về `1`, mặc dù input lần hai hợp lệ, vì cùng object `ExportState` được tái sử dụng. Trong ứng dụng web, nhiều request có thể dùng chung singleton service, khiến dữ liệu các request chảy vào cùng object prototype đã bị singleton giữ lâu dài.

Đổi annotation `@Scope("prototype")` sang chuỗi khác hoặc thêm nhiều method xử lý trong service không làm Spring tự inject lại dependency. Cần thay đổi **thời điểm lấy instance**.

## 6. Cách khuyến nghị: inject `ObjectProvider<Prototype>`

`ObjectProvider<T>` thuộc `org.springframework.beans.factory`. Container inject một provider, còn singleton yêu cầu target mới khi logic cần. Cách này giữ constructor injection và dễ kiểm thử.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    private final ObjectProvider<ExportState> states;

    public ExportService(ObjectProvider<ExportState> states) {
        this.states = states;
    }

    public int export(boolean invalidInput) {
        ExportState state = states.getObject(); // Lấy 1 prototype mới cho lần export.
        if (invalidInput) {
            state.addError("Invalid input");
        }
        return state.errorCount();
    }
}
~~~

Đây là **class minh họa thay thế** cho `ExportService` ở mục 5; không đặt hai định nghĩa cùng tên trong một source file. Khi sử dụng, `ExportState` vẫn phải được Spring đăng ký với `@Scope("prototype")`.

Nếu chạy tuần tự:

~~~java
System.out.println(service.export(true));
System.out.println(service.export(false));
~~~

Kết quả sẽ là:

~~~text
1
0
~~~

Vì mỗi lần `export(...)` bắt đầu bằng một instance `ExportState` mới và chỉ dùng một instance đó trong suốt lần xử lý. Quy tắc thiết kế quan trọng là:

> **Lấy một prototype cho mỗi đơn vị công việc, lưu biến cục bộ và tái sử dụng biến đó trong chính công việc ấy.**

Không gọi `states.getObject()` lặp lại cho từng thao tác đọc/ghi trên cùng trạng thái nếu các thao tác cần làm việc với **cùng một object**:

~~~java
// Sai nếu state cần được chia sẻ giữa hai bước:
states.getObject().addError("E1");
int count = states.getObject().errorCount(); // Object thứ hai: 0

// Đúng: lấy một lần, dùng xuyên suốt một nghiệp vụ:
ExportState state = states.getObject();
state.addError("E1");
int count = state.errorCount(); // 1
~~~

**Lưu ý:** `ObjectProvider.getObject()` không đảm bảo object mới nếu bean target là singleton: chính **scope của target** quy định trả một instance hay nhiều instance. Provider chỉ trì hoãn hành động lookup đến thời điểm gọi.

## 7. Cách khác: `@Lookup` method injection

Spring có thể tự ghi đè một method trong bean do container tạo, để mỗi lần gọi method đó container truy xuất bean theo tên hoặc kiểu trả về. Annotation là `org.springframework.beans.factory.annotation.Lookup`.

~~~java
import org.springframework.beans.factory.annotation.Lookup;
import org.springframework.stereotype.Component;

@Component
public class LookupExportService {

    public int export(boolean invalidInput) {
        ExportState state = createState();
        if (invalidInput) {
            state.addError("Invalid input");
        }
        return state.errorCount();
    }

    @Lookup("exportState")
    protected ExportState createState() {
        // Khi được Spring tạo và xử lý đúng, phương thức này
        // được override bằng lookup do container thực hiện.
        throw new IllegalStateException("Spring lookup was not applied");
    }
}
~~~

Đây là **đoạn minh họa đặt trong ứng dụng có `ExportState` prototype được đăng ký với tên `exportState`** (mặc định khi class `ExportState` được component scan); class phải được Spring tạo qua component scan hoặc cơ chế tạo bean hỗ trợ method injection. Không trực tiếp `new LookupExportService()` rồi kỳ vọng method được Spring thay thế.

Cơ chế:

1. Spring tạo một subclass tại runtime bằng CGLIB.
2. Subclass override `createState()`.
3. Mỗi lần `export(...)` gọi `createState()`, method override lấy `ExportState` từ container.
4. Với bean definition `prototype`, lookup mới trả instance mới.

Các giới hạn cần nhớ:

- Class chứa lookup method và chính method đó không thể là `final`, vì subclass cần override.
- Lookup method **không làm việc trên một instance được trả ra từ `@Bean` factory method**. Spring không tự tạo subclass của object đã được factory method tạo sẵn.
- Method injection phụ thuộc Spring container và làm luồng cấp dependency ít tường minh hơn constructor-injected `ObjectProvider`.
- Đối tượng mà method trả về vẫn tuân theo scope đã khai báo. Nếu `exportState` là singleton, `@Lookup` mỗi lần vẫn có thể trả cùng bean.

Với ứng dụng cần code rõ ràng, dễ unit test, `ObjectProvider<T>` thường dễ hiểu và dễ kiểm soát hơn.

## 8. Cách khác: `ObjectFactory`, `Provider` và `BeanFactory`

Các cơ chế sau cũng thực hiện lookup tại thời điểm cần dùng:

| Cách | Cú pháp ý tưởng | Đặc điểm |
| --- | --- | --- |
| `ObjectProvider<T>` | `provider.getObject()` | API Spring, hỗ trợ lazy/optional access, linh hoạt khi inject |
| `ObjectFactory<T>` | `factory.getObject()` | API Spring tối giản; có thể inject để nhận bean theo nhu cầu |
| `jakarta.inject.Provider<T>` | `provider.get()` | API chuẩn Jakarta Inject, cần dependency `jakarta.inject-api` phù hợp trên classpath |
| `BeanFactory` | `beanFactory.getBean(ExportState.class)` | Hoạt động nhưng service phụ thuộc rõ vào container/service locator |
| `ApplicationContext` | `context.getBean(ExportState.class)` | Truy xuất được nhưng kéo trách nhiệm container vào service |

Ví dụ với `ObjectFactory`:

~~~java
@Service
class FactoryExportService {
    private final ObjectFactory<ExportState> factory;

    FactoryExportService(ObjectFactory<ExportState> factory) {
        this.factory = factory;
    }

    ExportState createState() {
        return factory.getObject();
    }
}
~~~

Đoạn minh họa cần import `ObjectFactory` từ `org.springframework.beans.factory` và các annotation Spring tương ứng. Bean `ExportState` vẫn phải có scope prototype. Cũng như `ObjectProvider`, mỗi lần gọi factory là một yêu cầu mới, nên kết quả phụ thuộc scope được cấu hình.

Không nên giải quyết vấn đề bằng cách gọi `new ExportState()` ngay trong service nếu `ExportState` cần Spring injection, lifecycle callbacks, AOP hoặc các tiện ích của container. `new` tạo đối tượng Java thuần và bỏ qua quản lý bean của Spring.

## 9. Scoped proxy với prototype: dùng được nhưng phải hiểu phạm vi của lời gọi

Một lựa chọn là đăng ký prototype với scoped proxy:

~~~java
@Component
@Scope(
    value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class OperationState {
    private String value;

    public void setValue(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Đoạn này là class minh họa; cần import `Component`, `Scope`, `ScopedProxyMode` và `ConfigurableBeanFactory`.

Khi inject `OperationState` vào singleton, dependency được giữ thường là **proxy**, không phải một target prototype duy nhất. Proxy sẽ truy xuất target theo scope khi chuyển tiếp lời gọi method. Với prototype, mỗi lần lookup target có thể tạo một object khác; vì vậy:

~~~java
// Mã mô tả tình huống thường gặp với prototype scoped proxy.
operationState.setValue("READY");
String result = operationState.getValue();
~~~

**Không được mặc định `result` là `"READY"`**. Lời gọi `setValue` và `getValue` có thể được chuyển tiếp tới hai target prototype khác nhau. Đây là điểm rất khác so với `@RequestScope` hoặc `@SessionScope`: trong cùng request/session, scope tương ứng thường giữ cùng target cho các lời gọi, còn prototype không có khái niệm cache theo một nghiệp vụ.

Nếu một lần xử lý cần **một state riêng nhưng ổn định qua nhiều method calls**, hãy lấy đúng một object từ `ObjectProvider` và lưu vào biến cục bộ. Prototype scoped proxy phù hợp hơn khi từng lời gọi method cần một target độc lập, không phụ thuộc state đã lưu từ lời gọi trước.

Proxy dựa trên class có giới hạn với class/method `final`; proxy theo interface đòi hỏi điểm inject thích hợp. Việc thêm proxy không làm mutable target tự động thread-safe.

## 10. Còn `@Lazy` thì sao?

`@Lazy` thường điều khiển **thời điểm khởi tạo**, không định nghĩa lại scope từ `prototype` thành một scope khác. Ví dụ:

~~~java
@Component
@Lazy
class ExpensiveService {
    // ...
}
~~~

Đoạn này trì hoãn việc khởi tạo bean (tùy hoàn cảnh đăng ký/lấy bean); không thể suy ra rằng mọi lời gọi phương thức trên bean đó tạo object mới.

`@Lazy` đặt trên injection point có thể tạo một proxy giải quyết dependency khi sử dụng, nhưng đó là **cơ chế lazy-resolution proxy riêng** và hành vi cần xét theo bean target. Dùng `ObjectProvider` khi ý định của bạn là **yêu cầu một prototype mới có chủ đích tại từng lần xử lý**, vì code nêu rõ chỗ lookup và số lần tạo.

Không nhầm ba câu hỏi:

- **Khi nào tạo?** — lazy/eager initialization.
- **Mỗi lần container lookup thì lấy bao nhiêu instance?** — bean scope.
- **Khi nào chương trình thực hiện lookup mới?** — direct injection, provider, lookup method hoặc proxy.

## 11. Đánh đổi về vòng đời và hiệu năng

### 11.1. Prototype không được Spring tự hủy toàn bộ sau khi giao cho client

Spring quản lý quá trình tạo, dependency injection và initialization callback cho prototype, nhưng **không tự chạy destruction callback của từng prototype đã giao cho client** như với singleton lúc đóng context.

~~~java
@Component
@Scope("prototype")
class FileProcessingSession implements AutoCloseable {
    // Giả định class nắm một tài nguyên cần giải phóng.

    @Override
    public void close() {
        // Đóng resource thật tại đây.
    }
}
~~~

Trong code sử dụng, bên nhận phải quản lý tài nguyên sau khi xong công việc, ví dụ `try-with-resources` nếu bean implement `AutoCloseable`:

~~~java
try (FileProcessingSession session = sessions.getObject()) {
    // xử lý bằng session
}
~~~

Đoạn này là minh họa cần có `ObjectProvider<FileProcessingSession> sessions` và một bean prototype đã đăng ký; logic đóng tài nguyên cụ thể tùy nghiệp vụ. Không dựa vào `@PreDestroy` của prototype để tự chạy sau mỗi lời gọi `getObject()`.

### 11.2. Mỗi lần lookup có chi phí

Mỗi prototype mới có thể phải thực hiện constructor, dependency injection, bean post-processing và initialization. Nếu object chỉ là một POJO nhỏ, không có dependency nào của Spring, cân nhắc tạo một **đối tượng Java thông thường** ngay tại tầng nghiệp vụ thay vì tạo Spring bean prototype. Trái lại, nếu cần container quản lý dependency/AOP, dùng factory/provider phù hợp.

### 11.3. Không tự động thread-safe

Một singleton có thể được nhiều request/thread dùng đồng thời. Nếu singleton giữ trực tiếp một prototype có mutable state, trạng thái ấy vẫn bị **chia sẻ giữa các lời gọi trên cùng singleton**, và rất dễ race condition. `prototype` không tự bảo đảm thread-safety.

`ObjectProvider.getObject()` có thể giúp mỗi lần xử lý nhận một state độc lập, nhưng nếu bạn lưu state mới đó vào một field chung của singleton thì vẫn có nguy cơ race. Phạm vi biến cục bộ và cách truyền đối tượng giữa các thread vẫn quyết định độ an toàn.

## 12. Chọn cách nào?

| Yêu cầu thực tế | Phương án phù hợp | Vì sao |
| --- | --- | --- |
| Dependency dùng chung, không mang trạng thái theo lần xử lý | Inject trực tiếp một singleton | Đơn giản, tránh tạo object thừa |
| Tạo một dependency prototype **một lần khi singleton được khởi tạo** rồi giữ lâu | Inject prototype trực tiếp | Đúng nếu chủ đích là giữ instance đó |
| Mỗi lần gọi nghiệp vụ cần một prototype mới, dùng xuyên suốt nhiều bước | Inject `ObjectProvider<T>` và lấy một lần vào biến cục bộ | Rõ thời điểm tạo và phạm vi sử dụng |
| Cần lookup ở một method trên bean do Spring tạo | `@Lookup` | Spring override method để cấp bean lúc gọi |
| Có sẵn abstraction kiểu factory tối giản | `ObjectFactory<T>` hoặc `Provider<T>` | Chỉ yêu cầu bean khi cần |
| Từng lời gọi method phải resolve target theo scope | Scoped proxy | Thích hợp khi semantics của scope khớp nhu cầu |
| Object chỉ là dữ liệu/tính toán thuần Java | Tạo bằng constructor/factory Java thông thường | Tránh phụ thuộc container không cần thiết |

Hãy đặc biệt thận trọng với `@Scope("prototype", proxyMode = ScopedProxyMode.TARGET_CLASS)` nếu công việc gồm nhiều thao tác ghi/đọc liên tiếp trên một state. Đối tượng đích có thể thay đổi giữa các phương thức.

## 13. Checklist chẩn đoán khi prototype “không đổi”

Khi một bean được đánh dấu prototype nhưng thấy nhiều lời gọi cùng sử dụng object, kiểm tra theo thứ tự:

1. **Ai thực hiện lần lookup mới?** Method Java đang gọi có thật sự gọi `ObjectProvider.getObject()`, `@Lookup` hay `BeanFactory.getBean(...)`, hay chỉ đọc một field?
2. **Target scope có thực sự là prototype?** `@Scope` phải áp dụng cho bean definition đang inject, không chỉ một class chưa được container đăng ký.
3. **Singleton được khởi tạo khi nào?** Constructor/field/setter injection thông thường giải quyết dependency tại lúc tạo singleton.
4. **Có bao nhiêu instance được lấy?** Không đánh đồng gọi method nghiệp vụ nhiều lần với gọi container nhiều lần.
5. **Có proxy không?** Phải phân biệt identity của proxy và identity của target; một proxy ổn định không nói rằng mọi method đều chạy trên cùng target.
6. **Có giữ target trong singleton field sau lookup không?** Dù provider lấy target mới một lần, lưu lâu trong singleton lại tạo chia sẻ.
7. **Có nhầm scope với Java equality không?** Kiểm tra bằng `==` hoặc identity phù hợp, không dựa duy nhất vào `equals()` hay một field dữ liệu tình cờ giống nhau.
8. **Có bỏ qua quản lý bean không?** Object tạo bằng `new` bên ngoài container sẽ không nhận scope/injection của Spring.

Một cách kiểm tra ngắn trong Java:

~~~java
JobState fromProvider1 = provider.getObject();
JobState fromProvider2 = provider.getObject();

System.out.println(fromProvider1 == fromProvider2); // false nếu prototype.
~~~

Đoạn minh họa cần `provider` là một `ObjectProvider<JobState>` do Spring cung cấp và `JobState` được đăng ký là prototype. Nếu nhận `true`, kiểm tra bean definition, cách khởi tạo provider và code thực sự đang chạy.

## 14. Câu hỏi tự kiểm tra

**Câu 1:** `@Scope("prototype")` đặt trên `ExportState`, singleton `ExportService` inject `ExportState` qua constructor. Gọi `export()` 100 lần tạo bao nhiêu state cho field constructor đó?

**Đáp án:** Một instance `ExportState` cho lần tạo singleton `ExportService` đó; các lần gọi `export()` thông thường không làm Spring inject lại dependency.

**Câu 2:** Đổi sang inject `ObjectProvider<ExportState>`. Nếu gọi `getObject()` 3 lần trong một method thì có mấy object?

**Đáp án:** Ba instance khác nhau khi bean `ExportState` là prototype và không có proxy/cơ chế trả instance khác; nếu muốn chỉ một instance cho cả method, gọi provider một lần rồi dùng biến cục bộ.

**Câu 3:** `@Lookup` trên một method `final` hoặc method của instance tạo bởi `@Bean` factory có giải quyết được không?

**Đáp án:** Không theo cơ chế lookup-method injection chuẩn: method/class cần cho phép Spring tạo subclass và override; với instance trả từ factory method `@Bean`, Spring không chủ động tạo subclass của instance đó.

**Câu 4:** Tại sao `@Scope("prototype")` không ngăn singleton service vô tình chia sẻ state giữa nhiều thread?

**Đáp án:** Scope chỉ quy định hành vi tạo object lúc lookup. Singleton có thể giữ và chia sẻ cùng một tham chiếu prototype trong field, nên mọi thread truy cập field đó vẫn có thể cùng đọc/ghi một object.

## 15. Tài liệu Spring chính thức

- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): `singleton`, `prototype` và tương tác giữa singleton với prototype dependency.
- [Spring Framework Reference — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html): lookup method injection, `@Lookup`, CGLIB và giới hạn với `@Bean` factory methods.
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): thời điểm lắp ráp dependency do container quản lý.
- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): cách đăng ký bean bằng annotation và semantics liên quan đến `@Bean`.
