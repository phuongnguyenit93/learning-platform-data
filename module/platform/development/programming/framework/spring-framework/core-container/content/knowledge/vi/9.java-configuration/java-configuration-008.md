# Hành vi gọi trực tiếp giữa các phương thức @Bean trong Spring Core Container

## 1. Mục tiêu và tình huống

Trong Java configuration của Spring, chúng ta có thể thấy một phương thức `@Bean` gọi trực tiếp một phương thức `@Bean` khác:

```java
@Configuration
public class ShopConfig {

    @Bean
    StockRepository stockRepository() {
        return new StockRepository();
    }

    @Bean
    StockService stockService() {
        return new StockService(stockRepository());
    }
}
```

`StockRepository` và `StockService` trong đoạn đầu là hai class nghiệp vụ minh họa, cần định nghĩa và import để biên dịch. Nhìn như Java thuần, `stockRepository()` sẽ chạy mỗi lần được gọi, có thể tạo thêm object. Nhưng với **full `@Configuration`**, Spring thay đổi hành vi lời gọi này bằng cơ chế **CGLIB method interception**, để tham chiếu qua phương thức `@Bean` vẫn đi qua container và tuân theo scope. Khi **tắt interception** hoặc dùng **lite `@Bean`**, cùng cú pháp Java đó có thể thực sự tạo object mới, không phải đối tượng do Spring quản lý.

Đây là một trong những khác biệt quan trọng nhất khi học Java configuration.

Sau bài học, bạn có thể:

1. Giải thích full `@Configuration` và lite `@Bean` khác nhau thế nào khi một factory method gọi factory method khác.
2. Dự đoán identity, số lần tạo object, phạm vi `singleton` và `prototype` trong từng chế độ.
3. Hiểu điều kiện áp dụng interception, những ràng buộc với `final`, `private`, `static` và CGLIB.
4. Phân biệt **container gọi method để tạo bean** với **người dùng gọi method trong Java**.
5. Dùng **tham số của `@Bean` method** thay cho lời gọi chéo để biểu diễn dependency nhất quán với `@Configuration(proxyBeanMethods=false)`.
6. Nhận ra lỗi khó tìm như hai datasource, hai mapper, hai connection pool hoặc callback lifecycle không được áp dụng cho object phụ.
7. Chạy ví dụ Spring Framework 6.2.x, Java 17+ so sánh full configuration, lite configuration và injection qua tham số, có stdout xác định.

**Phạm vi:** cơ chế Spring Core Container đối với các **lời gọi trực tiếp giữa phương thức `@Bean`**. Không nhầm với việc method nghiệp vụ của bean gọi method khác, Spring AOP self-invocation hoặc dependency injection vào một field thông thường.

## 2. @Bean là factory method, nhưng Spring có thể can thiệp lời gọi

Annotation `@Bean` yêu cầu Spring đăng ký một bean definition được tạo bởi phương thức tương ứng:

```java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
```

Đoạn này cần import `org.springframework.context.annotation.Bean` và `java.time.Clock`, đặt trong class cấu hình được Spring nạp. Container biết có bean tên `clock` (nếu không cấu hình tên khác), có return type `Clock` và có thể gọi factory method khi cần tạo instance.

Hai hoạt động khác nhau:

- **Container-managed lookup:** `context.getBean("clock", Clock.class)` yêu cầu bean do Spring quản lý. Singleton thông thường được trả lại từ cache sau lần khởi tạo đầu tiên.
- **Direct Java call:** `clock()` hoặc `config.clock()` trông như gọi method Java bình thường. Nó có được đưa qua container hay không phụ thuộc vào **chế độ xử lý configuration class** và phương thức có được override/intercept hay không.

Vì thế, đừng trả lời đơn giản rằng “cứ gọi một `@Bean` method là luôn tạo object mới” hoặc “cứ gọi `@Bean` method là luôn lấy singleton”. Cả hai đều có thể sai.

## 3. Phân loại lời gọi trực tiếp giữa factory methods

### 3.1. Full `@Configuration`

Với `@Configuration` mặc định (`proxyBeanMethods=true`), Spring tăng cường instance cấu hình bằng CGLIB. Một lời gọi `otherBean()` **đủ điều kiện trên enhanced config** có thể chuyển về `BeanFactory`: singleton được chia sẻ và những scope khác được áp dụng theo quy tắc container.

### 3.2. Lite `@Configuration(proxyBeanMethods=false)`

Bean definitions vẫn được đăng ký và quản lý, nhưng method `otherBean()` được gọi trực tiếp sẽ chạy body như Java thông thường. Nếu body tạo object mới, object đó có thể nằm ngoài managed singleton. Đừng nhầm object này với bean prototype.

### 3.3. `@Bean` trong plain `@Component`

Spring có thể phát hiện factory methods trong class `@Component` đã được scan/đăng ký, nhưng chúng mang semantics **lite** cho inter-bean calls. `@Component` không đồng nghĩa full `@Configuration`.

### 3.4. Bảng đường đi của lời gọi

| Lời gọi | BeanFactory semantics? |
| --- | --- |
| `context.getBean("repository")` | Có, bất kể full/lite |
| `repository()` trên enhanced full config | Có nếu instance method được chặn hợp lệ |
| `repository()` trên lite config / plain `@Component` | Không, chạy body trực tiếp |
| `staticRepository()` trên mọi config | Không chặn lời gọi static |
| `new FullConfig().repository()` ngoài Spring | Không có enhancement |

Chỉ nhìn thấy annotation `@Bean` trên method chưa đủ để kết luận method call sẽ nhận bean từ container; phải xét **receiver và đường đi lời gọi**.

## 4. Vì sao full configuration dùng CGLIB?

Spring cần phân biệt **factory invocation để tạo bean** và **lời gọi tham chiếu bean** khi method `@Bean` này gọi method `@Bean` khác. Với full config, CGLIB tạo subclass và override method hợp lệ để chuyển lời gọi tham chiếu sang BeanFactory:

```text
BeanFactory tạo serviceA
    -> enhancedConfig.serviceA()
    -> repository() được intercept
    -> BeanFactory lấy bean 'repository' theo scope
    -> serviceA nhận managed reference
```

Nếu bean là singleton, những consumer dùng cùng bean; nếu là prototype hoặc custom scope, container áp dụng chính scope ấy. Nếu bean được bọc AOP/scoped proxy, reference do container trả có thể là proxy chứ không phải raw object do factory body tạo. Đó là khác biệt có thể thấy bằng identity và lifecycle.

### 4.1. Factory call không phải lúc nào cũng là lookup

Khi BeanFactory đang thật sự tạo bean tương ứng, interceptor phải cho phép chạy factory body; khi enhanced configuration gọi method để **tham chiếu bean khác**, interceptor thực hiện lookup. Nếu không phân biệt hai trường hợp, dễ hiểu sai thành một vòng đệ quy vô hạn hoặc cache Java cho mọi lần gọi. Đây là mô hình khái niệm, không phải source code nội bộ CGLIB.

### 4.2. Giới hạn full configuration

Subclassing/overriding yêu cầu configuration class không `final`, instance `@Bean` methods không `private`/`final`; `static @Bean` không được override. Tạo `new Config()` ngoài Spring không có enhancement. Khi cần cấu hình lite, **truyền dependency bằng tham số `@Bean`** là cách ổn định hơn.

## 5. Cách an toàn: inject dependency qua tham số @Bean

Thay:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service() {
        return new Service(repository()); // Java direct call!
    }
}
```

bằng:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service(Repository repository) {
        return new Service(repository); // Spring resolve dependency.
    }
}
```

`Repository` và `Service` là kiểu minh họa. Trong biến thể thứ hai, Spring giải quyết tham số `Repository` từ bean definitions, dùng scope/qualifier/primary như các injection point khác. Không cần enhancement hoặc gọi chéo phương thức để chia sẻ bean.

**Lợi ích:**

- Hoạt động cùng nguyên tắc ở full mode và lite mode.
- Dependency graph rõ trong method signature.
- Dễ phân định nhiều implementation bằng `@Qualifier`.
- Dễ phát hiện lỗi dependency thiếu hoặc mơ hồ.
- Không vô tình tạo thêm client/connection pool/mapper ngoài container.
- Giảm phụ thuộc vào CGLIB và cách Spring xử lý lời gọi method.
- Cho phép `@Configuration(proxyBeanMethods=false)` mà không thay semantics mong đợi của dependency.

Trong Java configuration hiện đại, đây thường là lựa chọn dễ đọc và ít ngạc nhiên nhất.

## 6. Ví dụ hoàn chỉnh Java 17+: so sánh ba chế độ

Ví dụ thực hành không dùng Spring Boot, JDBC hoặc web server. Nó sử dụng **Spring Framework 6.2.9**, **JDK 17+** và `AnnotationConfigApplicationContext`.

Chúng ta thử ba context **riêng biệt**:

1. **FullConfig:** `@Configuration` mặc định intercept lời gọi chéo `widget()`.
2. **LiteConfig:** `@Configuration(proxyBeanMethods=false)` để lời gọi `widget()` trong `pair()` chạy như Java thuần.
3. **ParamConfig:** cũng tắt interception, nhưng `pair(Widget widget)` nhận tham số từ container nên vẫn dùng singleton đã đăng ký.

`Widget` là một đối tượng đơn giản có id. Mỗi khi factory body thực sự tạo object, counter tăng. `Pair` giữ hai tham chiếu tới Widget. So sánh bằng toán tử `==` để kiểm tra **object identity**, không phụ thuộc `equals()`.

### 6.1. Cấu trúc dự án

```text
interbean-calls-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── InterBeanCallsDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'interbean-calls-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.InterBeanCallsDemo'
}
```

**`src/main/java/demo/InterBeanCallsDemo.java`**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class InterBeanCallsDemo {
    private static final AtomicInteger FULL_CALLS = new AtomicInteger();
    private static final AtomicInteger LITE_CALLS = new AtomicInteger();
    private static final AtomicInteger PARAM_CALLS = new AtomicInteger();

    // Java 17 record: immutable value giữ mã nhận diện factory invocation.
    record Widget(int id) {}
    record Pair(Widget first, Widget second) {}

    // Full mode: method interception bật theo mặc định.
    @Configuration
    public static class FullConfig {
        @Bean
        public Widget widget() {
            return new Widget(FULL_CALLS.incrementAndGet());
        }

        @Bean
        public Pair pair() {
            return new Pair(widget(), widget());
        }
    }

    // Lite mode: lời gọi chéo là lời gọi Java thông thường.
    @Configuration(proxyBeanMethods = false)
    public static class LiteConfig {
        @Bean
        public Widget widget() {
            return new Widget(LITE_CALLS.incrementAndGet());
        }

        @Bean
        public Pair pair() {
            return new Pair(widget(), widget());
        }
    }

    // Không intercept nhưng dùng method argument injection.
    @Configuration(proxyBeanMethods = false)
    public static class ParamConfig {
        @Bean
        public Widget widget() {
            return new Widget(PARAM_CALLS.incrementAndGet());
        }

        @Bean
        public Pair pair(Widget widget) {
            return new Pair(widget, widget);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(FullConfig.class)) {
            Widget managed = context.getBean(Widget.class);
            Pair pair = context.getBean(Pair.class);

            System.out.println("full.calls=" + FULL_CALLS.get());
            System.out.println("full.pairSame="
                    + (pair.first() == pair.second()));
            System.out.println("full.managedSame="
                    + (pair.first() == managed));
            System.out.println("full.externalCallManaged="
                    + (context.getBean(FullConfig.class).widget() == managed));
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(LiteConfig.class)) {
            Widget managed = context.getBean(Widget.class);
            Pair pair = context.getBean(Pair.class);

            System.out.println("lite.calls=" + LITE_CALLS.get());
            System.out.println("lite.pairSame="
                    + (pair.first() == pair.second()));
            System.out.println("lite.managedSame="
                    + (pair.first() == managed));
            System.out.println("lite.externalCallManaged="
                    + (context.getBean(LiteConfig.class).widget() == managed));
            System.out.println("lite.callsAfterExternal=" + LITE_CALLS.get());
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(ParamConfig.class)) {
            Widget managed = context.getBean(Widget.class);
            Pair pair = context.getBean(Pair.class);

            System.out.println("param.calls=" + PARAM_CALLS.get());
            System.out.println("param.pairSame="
                    + (pair.first() == pair.second()));
            System.out.println("param.managedSame="
                    + (pair.first() == managed));
        }
    }
}
```

Các nested class `FullConfig`, `LiteConfig`, `ParamConfig` được khai báo `public static` nên dùng được làm Java configuration class. Chỉ có `InterBeanCallsDemo` là public top-level class; file trùng tên class, code không cần package khác.

`Widget`/`Pair` là nested records, thích hợp với Java 17. Vì các class configuration không `final` và `@Bean` methods ở full mode là `public`, Spring có thể enhanced `FullConfig`.

### 6.2. Chạy

Trong thư mục gốc `interbean-calls-demo`:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows). Lệnh `javac InterBeanCallsDemo.java` không hoạt động đơn lẻ nếu chưa cung cấp dependency Spring trên classpath; Gradle thực hiện điều này.

**Stdout do chính chương trình in ra:**

```text
full.calls=1
full.pairSame=true
full.managedSame=true
full.externalCallManaged=true
lite.calls=3
lite.pairSame=false
lite.managedSame=false
lite.externalCallManaged=false
lite.callsAfterExternal=4
param.calls=1
param.pairSame=true
param.managedSame=true
```

Nếu Gradle hoặc logging framework tạo log phụ, chúng không thuộc nội dung `System.out.println` trên.

### 6.3. Phân tích FullConfig

`widget` là singleton mặc định. BeanFactory tạo một instance `Widget` qua factory body, khiến `FULL_CALLS` tăng tới 1.

Khi `pair()` được gọi trong enhanced configuration, hai lời gọi `widget()` được intercept để yêu cầu bean `widget` từ container. Vì singleton đã được tạo hoặc sẽ được tạo theo lookup, hai tham chiếu trong `Pair` trỏ về **cùng bean**. Vì vậy:

```text
full.calls=1
full.pairSame=true
full.managedSame=true
```

Khi code ngoài configuration lấy **chính managed FullConfig bean** rồi gọi `widget()`, method cũng được enhanced. Nó trả bean container quản lý:

```text
full.externalCallManaged=true
```

**Ranh giới quan trọng:** nếu bạn tự `new FullConfig()` rồi gọi method, đó là object không qua Spring enhancement, nên không được kỳ vọng có cùng hành vi.

### 6.4. Phân tích LiteConfig

Container vẫn có bean definition `widget` và `pair`, và khi refresh sẽ tạo singleton thường. Nhưng `pair()` gọi trực tiếp `widget()` hai lần trong body, tạo hai object khác nhau. BeanFactory còn tạo một `Widget` riêng cho bean definition `widget`, nên tổng số invocation của factory body sau refresh là **3**:

```text
lite.calls=3
lite.pairSame=false
lite.managedSame=false
```

Ở đây `pair.first()` không phải managed widget singleton, dù class/return type giống hệt. Nó được tạo bởi **direct Java call** trong method factory khác.

Khi lấy managed `LiteConfig` bean rồi gọi `widget()`, do không có interception, lời gọi ấy tạo thêm object, làm counter tăng lên 4:

```text
lite.externalCallManaged=false
lite.callsAfterExternal=4
```

Điều này không có nghĩa Spring “không quản lý `widget`” ở lite mode. Spring **vẫn quản lý instance mà BeanFactory tạo cho bean `widget`**. Vấn đề chỉ nằm ở **những object phụ được tạo bởi direct method call**.

### 6.5. Phân tích ParamConfig

`ParamConfig` cũng ở lite mode nhưng `pair(Widget widget)` yêu cầu dependency qua chữ ký factory method. Spring resolve `Widget` từ context, cung cấp managed singleton vào tham số. Không cần method interception:

```text
param.calls=1
param.pairSame=true
param.managedSame=true
```

Đây là lý do thực tế nên ưu tiên **method parameter injection** thay cho gọi trực tiếp một `@Bean` method khác khi không cần full mode.

### 6.6. Ý nghĩa của bộ đếm

Counter chỉ đếm số lần **factory method body** `widget()` thật sự thực thi trong mỗi cấu hình. Nó không đếm số lần lookup container nếu lookup trả bean đã cache. `==` kiểm tra cùng tham chiếu object. Vì source dùng các `AtomicInteger` khác nhau cho từng cấu hình và mỗi context tạo/đóng tuần tự, kết quả có thể xác định từ code mà không dựa vào thứ tự BeanFactory trả map.

**Không nên suy luận từ ví dụ rằng Spring luôn khởi tạo các singleton theo một thứ tự cố định ngoài hợp đồng.** Dù `widget` hay `pair` được tạo trước trong lite context, vẫn có ba invocation factory body sau refresh: một để tạo managed `widget` và hai direct calls từ `pair()`.

## 7. Scope ảnh hưởng trực tiếp đến kết quả của inter-bean calls

Full mode bảo toàn **scope**, không bảo đảm hai lời gọi `@Bean` luôn trả cùng object. Ví dụ:

```java
@Configuration
class ScopeConfig {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    Widget widget() {
        return new Widget(1);
    }

    @Bean
    Pair pair() {
        return new Pair(widget(), widget());
    }
}
```

Đây là ví dụ cấu trúc dùng các record `Widget`/`Pair` của chương trình đầy đủ; cần import `Scope` và `ConfigurableBeanFactory`, hoặc đặt trong cùng package với chúng nếu tách ra kiểu public. Với `widget` là prototype, **mỗi lookup do hai lời gọi `widget()` đã intercept yêu cầu bean prototype mới**. Vì vậy `pair.first() != pair.second()` có thể đúng, ngay trong full mode.

Bảng tổng quát:

| Bean được gọi chéo | Full mode, gọi qua enhanced config | Lite mode, direct call | Factory method parameter |
| --- | --- | --- | --- |
| `singleton` | Lookup tới singleton Spring quản lý, thường cùng instance | Chạy method body, có thể tạo instance mới ngoài container | Spring inject cùng singleton theo type/qualifier |
| `prototype` | Mỗi lookup yêu cầu prototype theo BeanFactory | Chạy method body, có thể tạo instance mới nhưng **không theo lifecycle đầy đủ của prototype bean** | Spring resolve một prototype khi tạo bean nhận tham số |
| `request`/`session` | Lookup tuân theo scope đang hoạt động | Method body trực tiếp có thể bỏ qua semantics scope | Spring resolve dependency tại lúc tạo bean nhận tham số; có thể cần scoped proxy/provider |
| Bean `@Lazy` singleton | Lookup có thể kích hoạt tạo bean khi cần | Chạy body bất kể `@Lazy` trên definition | Spring resolve theo dependency; eager consumer có thể khiến lazy target được tạo sớm |

**Đặc biệt với prototype và singleton consumer:** nếu một singleton `Pair` nhận tham số prototype `Widget` ở lúc khởi tạo, nó giữ **một instance prototype đã được giải quyết tại thời điểm đó**. Để có prototype mới theo mỗi lời gọi nghiệp vụ, dùng `ObjectProvider<Widget>`, `Provider<Widget>` hoặc cơ chế lookup phù hợp. Đừng gọi method `@Bean` trong business service để thử giải quyết scope.

### 7.1. Vì sao direct call tới prototype cũng là vấn đề?

Một người có thể lập luận: “Prototype vốn phải mới mỗi lần, nên lite direct call `widget()` vẫn tạo object mới, có gì sai?”. Sai lệch nằm ở chỗ **tạo object mới không đồng nghĩa nhận một bean prototype do Spring quản lý**.

Object do direct call tạo có thể bỏ qua:

- Autowiring lên instance trả về;
- `BeanPostProcessor` và lifecycle initialization;
- Bean-specific proxying/AOP;
- Scope resolution hoặc các dependency đặc biệt;
- Những quy tắc container khác gắn với bean definition.

Cho dù số instance tình cờ giống nhau, **semantics không tương đương**.

## 8. Interception và lifecycle của object ngoài container

Một example quen thuộc là `DataSource`:

```java
@Bean
DataSource dataSource() {
    return buildPooledDataSource();
}

@Bean
JdbcTemplate jdbcTemplate() {
    return new JdbcTemplate(dataSource());
}
```

Đây là ví dụ cấu trúc, cần dependency `spring-jdbc`, interface `javax.sql.DataSource` và factory `buildPooledDataSource()` do ứng dụng cung cấp. Nếu dùng full config, lời gọi `dataSource()` trong `jdbcTemplate()` có thể được intercept và dùng managed datasource singleton.

Nếu chuyển class sang `@Configuration(proxyBeanMethods=false)` nhưng giữ nguyên lời gọi, Spring có thể tạo:

1. Một connection pool cho bean `dataSource` quản lý bởi container.
2. Một connection pool khác từ lời gọi Java trực tiếp bên trong `jdbcTemplate()`.

Pool thứ hai không được đăng ký theo bean definition `dataSource`; quản lý tài nguyên trở nên nguy hiểm: credentials, properties, connection metrics, shutdown callback có thể không thống nhất.

**Cách đáng tin cậy:**

```java
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
```

Lúc này Spring resolve managed datasource cho tham số. Đoạn code này yêu cầu bean `DataSource` được đăng ký hợp lệ; nếu nhiều bean `DataSource`, dùng `@Qualifier` hoặc quy tắc lựa chọn ứng viên tương ứng.

### 8.1. Lifecycle callback không tự áp vào object direct call

Giả sử factory method:

```java
@Bean(initMethod = "start", destroyMethod = "stop")
VendorClient vendorClient() {
    return new VendorClient();
}
```

`VendorClient` là class giả định có `start()`/`stop()`. Spring có thể gọi init/destroy callback cho **instance được BeanFactory tạo và quản lý**. Nếu code lite mode gọi `vendorClient()` thủ công, method body có thể trả một `VendorClient` mới nhưng **container không tự ghi nhận object phụ đó là bean có callback tương ứng**. Kết quả là tài nguyên có thể không được start đúng quy trình hoặc không được stop khi context đóng.

Với SDK bên ngoài, đặc biệt connection pool/thread client, dùng parameter injection và xác định rõ quyền sở hữu tài nguyên.

### 8.2. Proxy và AOP có thể bị bypass

Khi bean đích được wrap bởi Spring proxy, lookup qua context thường trả về proxy. Lời gọi trực tiếp factory method trong lite mode tạo raw object không được đưa qua auto-proxy creator theo đường bean đã đăng ký. Gọi method nghiệp vụ trên raw object này có thể bỏ qua transaction/caching/metrics tùy cấu hình.

Đây là vấn đề **khác nhưng có liên hệ** với Spring AOP self-invocation:

- **Inter-bean call**: method `@Bean` gọi một factory method `@Bean` khác; full configuration CGLIB có cơ chế can thiệp riêng.
- **AOP self-invocation**: method nghiệp vụ `this.inner()` gọi method khác cùng service; trong proxy mode thông dụng nó có thể bỏ qua AOP advice.

Hai cơ chế đều nhắc tới proxy, nhưng **không được đánh đồng** hoặc dùng quy tắc của cái này để thay thế cái kia.

## 9. Khi nào @Configuration(proxyBeanMethods=false) là lựa chọn tốt?

Đây không phải một tùy chọn “bật lên sẽ phá Spring”. Nó là lựa chọn thiết kế hợp lệ khi các factory methods độc lập và **không cần inter-bean Java calls**.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    GreetingService greetingService(Clock clock) {
        return new GreetingService(clock);
    }

    @Bean
    AuditService auditService(GreetingService greetingService) {
        return new AuditService(greetingService);
    }
}
```

Đây là ví dụ cấu trúc với `GreetingService` và `AuditService` do ứng dụng định nghĩa. Mọi dependency đều đi qua factory method parameters. Nó có những lợi ích:

- Tránh dynamic subclass CGLIB cho configuration chỉ làm nhiệm vụ factory.
- Cho phép thiết kế configuration class có thể là `final` trong các trường hợp phù hợp.
- Tối giản semantics: direct method call luôn là direct method call; bean lookup luôn qua container.
- Dễ đọc dependency graph qua signatures.
- Giảm nguy cơ hidden behavior do một method trong class gọi method khác.

Nhưng `false` không tự động tốt hơn `true` cho mọi mã. Một cấu hình cũ dựa vào inter-bean calls sẽ phải refactor trước khi đổi; nếu không, có thể tạo object phụ ngoài container.

### 9.1. Không được đổi flag theo kiểu “tối ưu mù”

Trước khi thay:

```java
@Configuration
class OldConfig { ... }
```

bằng:

```java
@Configuration(proxyBeanMethods = false)
class OldConfig { ... }
```

hãy đọc toàn bộ factory methods trong class đó để tìm các direct calls tới `@Bean` methods khác, các calls từ nơi ngoài class vào configuration bean, hoặc các assumptions về scope/lifecycle.

Nếu có, sửa thành method parameter injection trước và bổ sung test **identity/lifecycle/proxy**. Sau đó mới cân nhắc tắt interception.

## 10. Ranh giới: direct calls ở đâu được intercept?

### 10.1. Trong chính full @Configuration class

Trường hợp phổ biến được Spring bảo đảm: method instance `@Bean` gọi một instance `@Bean` method khác trên **enhanced configuration bean**. Spring hướng tham chiếu tới managed bean theo scope.

### 10.2. Từ bên ngoài, qua configuration bean của Spring

```java
FullConfig config = context.getBean(FullConfig.class);
Widget widget = config.widget();
```

Đây là snippet dựa trên ví dụ chạy ở mục 6. `config` là instance Spring-managed và đã được enhanced; vì thế method `widget()` có thể được intercept như ví dụ `full.externalCallManaged=true`.

Tuy nhiên, việc gọi configuration `@Bean` methods từ code nghiệp vụ vẫn làm kiến trúc gắn với factory; constructor injection của `Widget` vào consumer là cách nên dùng hơn.

### 10.3. Từ một object tự new bên ngoài Spring

```java
FullConfig config = new FullConfig();
Widget widget = config.widget();
```

Đây là Java direct call trên object không được enhanced, nên method body chạy thường. Đừng nhầm “class có annotation `@Configuration`” với “mọi instance của class ấy đều được Spring proxy”.

### 10.4. Static @Bean method

```java
@Configuration
class SettingsConfig {
    @Bean
    static Settings settings() {
        return new Settings();
    }

    @Bean
    Client client() {
        return new Client(settings());
    }
}
```

`Settings` và `Client` là kiểu minh họa. Static method không override được bằng CGLIB, nên `settings()` trong `client()` là lời gọi Java thường, ngay cả khi configuration class ở full mode.

Nên sửa thành `Client client(Settings settings)` để Spring cấp bean đã đăng ký.

### 10.5. Các class @Configuration khác

Nếu một config class khác lấy **managed enhanced bean** của full configuration và gọi method đủ điều kiện, interception vẫn có thể áp dụng. Nhưng **gọi `new OtherConfig().beanMethod()`** không có hạ tầng đó.

Thực tế, ghép dependency qua factory method parameter, `@Import` và bean injection rõ ràng tốt hơn truyền configuration class qua lại chỉ để gọi factory.

### 10.6. @Bean method trên plain @Component

Các `@Bean` methods của plain `@Component` class (lite mode) không có CGLIB interception inter-bean calls theo semantics full `@Configuration`, ngay cả khi instance component được Spring quản lý. Vì thế **managed component** và **enhanced configuration** không phải cùng một điều.

## 11. Bean name, @Qualifier và @Primary khi chuyển sang parameter injection

Nếu cấu hình có hai bean cùng type:

```java
@Bean("primaryClock")
Clock primaryClock() {
    return Clock.systemUTC();
}

@Bean("testClock")
Clock testClock() {
    return Clock.fixed(
            java.time.Instant.parse("2024-01-01T00:00:00Z"),
            java.time.ZoneOffset.UTC
    );
}
```

Đây là snippet đặt trong một class configuration, cần import `java.time.Clock`. Lời gọi direct `primaryClock()` trong một factory method khác có thể bị intercept ở full mode, nhưng trong lite mode chạy thân method như Java. Phương án nhất quán:

```java
@Bean
TimeReporter timeReporter(
        @Qualifier("primaryClock") Clock clock) {
    return new TimeReporter(clock);
}
```

`TimeReporter` là kiểu nghiệp vụ giả định; cần import `org.springframework.beans.factory.annotation.Qualifier`. Spring sẽ resolve ứng viên thích hợp theo qualifier và scope. Nếu ứng dụng thật có một bean mặc định, `@Primary` có thể giúp phân định dependency theo type, nhưng qualifier vẫn rõ khi nghiệp vụ cần tên cụ thể.

Không dùng việc gọi một `@Bean` method theo tên như một chiến lược ngầm để chọn bean khi codebase đã chọn lite mode. **Đặt điều kiện chọn ngay tại injection point**.

## 12. Circular dependency và inter-bean calls

Có lúc người học dùng inter-bean calls để lắp một vòng phụ thuộc:

```java
@Bean
A a() {
    return new A(b());
}

@Bean
B b() {
    return new B(a());
}
```

`A` và `B` là kiểu nghiệp vụ giả định. Đây là một vòng constructor dependency. Full mode interception **không tự phá vòng**: BeanFactory có thể phát hiện việc bean đang được tạo lại khi chưa hoàn tất, và ném lỗi vòng phụ thuộc/bean currently in creation.

Lite mode càng có nguy cơ gọi Java đệ quy vô hạn giữa `a()` và `b()`, không qua BeanFactory kiểm soát vòng phụ thuộc theo cách mong đợi.

Phải thiết kế lại dependency: tách trách nhiệm, tách interface giao tiếp, xử lý sau khởi tạo khi hợp lệ, dùng sự kiện hoặc provider/lazy lookup có chủ đích. Không dùng direct `@Bean` method calls như cách né kiểm tra vòng phụ thuộc của container.

### 12.1. Gọi cùng method trong body của nó

Nếu một factory method tự gọi chính nó:

```java
@Bean
A a() {
    return a();
}
```

Đây là ví dụ không hợp lệ về mặt thiết kế: trong full mode, Spring có thể gặp tình huống yêu cầu bean đang được tạo; trong lite mode có thể đệ quy không dừng. Tránh hoàn toàn mô hình tự gọi factory method để khai báo dependency.

## 13. Inter-bean calls và thời điểm khởi tạo

`@Bean` methods được Spring phân tích thành bean definitions trước khi phần lớn singleton thông thường được tạo. Khi full config intercept `b()` từ `a()`, nó có thể **kích hoạt bean `b` được tạo sớm hơn** nếu nó chưa tồn tại.

Điều này không có nghĩa Spring tạo bean đúng theo thứ tự source code mọi lúc. Spring phải xử lý dependency, `@Lazy`, scope, post-processors và nhiều yếu tố lifecycle.

### 13.1. @Lazy và lookup

```java
@Bean
@Lazy
ExpensiveClient expensiveClient() {
    return new ExpensiveClient();
}

@Bean
Service service() {
    return new Service(expensiveClient());
}
```

`ExpensiveClient`/`Service` là kiểu minh họa; import `Lazy`. Với full mode, nếu `service` được khởi tạo eager và gọi `expensiveClient()`, lookup có thể buộc Spring tạo `expensiveClient` **ngay khi cần để lắp service**, dù bean ấy khai báo lazy.

Trong lite mode, method body `expensiveClient()` được gọi trực tiếp từ `service()`, không thông qua bean definition lazy và có thể tạo object khác ngoài container. Không coi `@Lazy` trên factory method là rào chắn đối với các Java calls thủ công.

### 13.2. Post-processors và early instantiation

Các bean đặc biệt như `BeanFactoryPostProcessor`/`BeanPostProcessor` có thể phải được tạo rất sớm. Với static `@Bean` dành cho các processor này, Spring thường khuyến nghị factory method static để tránh tạo configuration instance sớm.

Điều này bổ sung cho chủ đề hiện tại: static `@Bean` methods **không intercept direct calls**, nên đừng gọi static processor factory chỉ để lấy processor trong code nghiệp vụ. Spring cần được tự phát hiện chúng theo return type và đăng ký đúng giai đoạn.

## 14. Ví dụ so sánh số object và lifecycle khi dùng SDK bên ngoài

Giả sử một cấu hình:

```java
@Configuration(proxyBeanMethods = false)
class VendorConfig {
    @Bean
    VendorClient vendorClient() {
        return VendorClient.create();
    }

    @Bean
    VendorService vendorService() {
        return new VendorService(vendorClient());
    }
}
```

`VendorClient`/`VendorService` và `VendorClient.create()` là SDK giả định. Có thể tạo **hai client**: một theo bean `vendorClient`, một do call trong `vendorService`. Nếu mỗi client khởi tạo connection pool hoặc background threads, dự án có thể tốn gấp tài nguyên và không đóng object phụ.

Chuyển sang:

```java
@Configuration(proxyBeanMethods = false)
class VendorConfig {
    @Bean
    VendorClient vendorClient() {
        return VendorClient.create();
    }

    @Bean
    VendorService vendorService(VendorClient vendorClient) {
        return new VendorService(vendorClient);
    }
}
```

Khi đó Spring thực hiện dependency resolution trên managed `VendorClient`. Nếu SDK client cần `close()`, dùng `@Bean(destroyMethod="close")` khi đúng hợp đồng và xác định ownership để container đóng tài nguyên được quản lý. Không giả định mọi loại SDK client có cùng method/lifecycle.

**Phép test thiết thực:** tiêm `VendorClient` vào một test bean và kiểm tra reference bên trong `VendorService` chính là managed bean, hoặc dùng spy/counter/factory test double để assert chỉ một pool được tạo.

## 15. Những lỗi hiểu sai phổ biến

### Lỗi 1: “@Bean gọi @Bean khác thì luôn singleton”

Không. Full mode trả bean theo scope: singleton cùng instance, prototype có thể khác instance mỗi lookup, và scoped proxies hoạt động theo scope. Lite mode direct call không tuân theo semantics lookup container.

### Lỗi 2: “proxyBeanMethods=false khiến Spring bỏ qua @Bean”

Không. Các factory methods vẫn được xử lý để đăng ký/tạo bean. Chỉ **interception của Java calls** không còn.

### Lỗi 3: “Cứ đặt @Configuration thì phương thức static cũng được CGLIB chặn”

Không. Static methods không override được; lời gọi trực tiếp tới static factory vẫn chạy body bình thường.

### Lỗi 4: “@Component chứa @Bean giống full @Configuration”

Không. `@Bean` trên plain `@Component` ở lite mode. Nếu method A gọi method B, đó là Java direct call, không phải container lookup.

### Lỗi 5: “Nếu object direct call có cùng class thì cũng là Spring bean”

Không. Spring bean được xác định qua **bean definition và quá trình quản lý của container**. Một object có cùng class nhưng tạo bên ngoài có thể không nhận DI, post-processing, init/destroy callback hoặc proxy.

### Lỗi 6: “Đổi true thành false để tối ưu sẽ an toàn tuyệt đối”

Không. Trước khi đổi, phải tìm mọi direct calls giữa `@Bean` methods và từ bên ngoài vào config bean, rồi chuyển sang parameter injection hoặc lookup container phù hợp.

### Lỗi 7: “Nhận prototype mới nhờ direct call cũng giống lấy bean prototype”

Không. Mặc dù có instance mới, direct call có thể bỏ qua lifecycle/proxy/dependency resolution theo bean definition; chỉ container lookup mới thực sự tuân scope.

### Lỗi 8: “Gọi new FullConfig() thì CGLIB vẫn hoạt động”

Không. Enhancement nằm trên Spring-managed config bean; object tự `new` không được Spring thay bằng enhanced subclass.

### Lỗi 9: “Có full interception nên vòng phụ thuộc constructor được giải quyết”

Không. Circular dependency vẫn là vấn đề cần thiết kế, không biến mất nhờ CGLIB method interception.

### Lỗi 10: “Gọi @Bean method trong business code là cách DI phù hợp”

Thông thường không. Consumer nên nhận dependency qua constructor; factory method và configuration class thuộc layer wiring/composition, không phải service locator cho code nghiệp vụ.

### Lỗi 11: “Spring chắc chắn tạo bean theo thứ tự các methods trong source”

Không nên dựa vào thứ tự source làm hợp đồng. Dependency graph, `@Lazy`, bean scope, post-processor và bean definition ordering có thể tác động tới timing; use case phải đúng độc lập với thứ tự không được bảo đảm.

### Lỗi 12: “Method parameter injection chỉ dùng được nếu proxyBeanMethods=true”

Không. Parameter injection là dependency resolution bình thường của Spring, hoạt động tốt ở cả full và lite mode, và chính là cách nên dùng khi tắt interception.

## 16. Checklist kiểm thử trước khi chuyển sang lite mode

Trước khi đặt `@Configuration(proxyBeanMethods=false)` trong project thật:

1. **Xác định nơi cấu hình:** class thực sự được Spring đăng ký hay chỉ là Java object thủ công?
2. **Liệt kê các factory methods:** method nào mang `@Bean`, method nào trực tiếp gọi method khác?
3. **Nhận diện direct inter-bean calls:** `beanB()` trong `beanA()`, gọi từ method helper, gọi từ configuration class khác hoặc gọi qua managed config bean.
4. **Sửa dependency expression:** chuyển call thành factory method parameters, dùng qualifier khi cần.
5. **Kiểm tra scope:** singleton, prototype, request/session và lazy behavior có còn đúng không?
6. **Kiểm tra identity:** object trong consumer có cùng managed singleton được container trả về không?
7. **Kiểm tra lifecycle:** init/destroy callbacks, proxying, autowiring và resource cleanup có được áp dụng đúng instance không?
8. **Kiểm tra tài nguyên đắt tiền:** chỉ tạo một connection pool/HTTP client/mapper theo policy đặt ra.
9. **Kiểm tra static methods:** không trông chờ interception cho static `@Bean`.
10. **Kiểm tra code test:** tests dựng configuration bằng `new` không mô phỏng full Spring context.
11. **Chạy integration test:** dùng `AnnotationConfigApplicationContext` hoặc context thực tế tương ứng để assert bean graph.
12. **Quan sát warning:** nếu có bean creation/processor warning sau refactor, đừng bỏ qua vì “chỉ thay flag”.

## 17. Cách kiểm thử nhanh và điều tra một bean bị tạo thừa

### 17.1. Đếm lần tạo factory body

Trong test fixture, dùng `AtomicInteger` tăng tại lúc factory method thực sự trả object:

```java
private final AtomicInteger created = new AtomicInteger();

@Bean
Widget widget() {
    return new Widget(created.incrementAndGet());
}
```

Đây là snippet dựa trên kiểu `Widget` từ demo; muốn chạy độc lập cần class chứa bean definition và imports tương ứng. So sánh counter khi tạo context full và lite giúp quan sát việc direct call có chạy body hay không.

### 17.2. Kiểm tra identity

```java
Widget managed = context.getBean(Widget.class);
Pair pair = context.getBean(Pair.class);

System.out.println(pair.first() == managed);
System.out.println(pair.first() == pair.second());
```

Đây là snippet trong scope context của ví dụ. Khi singleton được resolve đúng, các reference có thể trùng nhau. Với lite mode và direct calls trong factory body, chúng có thể khác nhau.

### 17.3. Xem bean definition

```java
var factory = context.getBeanFactory();
var def = factory.getBeanDefinition("widget");

System.out.println(def.getFactoryMethodName());
System.out.println(factory.containsSingleton("widget"));
```

Snippet cần context `AnnotationConfigApplicationContext`. `getFactoryMethodName()` thông thường là `widget` trong ví dụ; `containsSingleton("widget")` chỉ nói cache singleton có instance hay chưa. Nó **không thể phát hiện những object phụ** do direct Java call tạo bên ngoài container. Kết hợp kiểm tra bean definition với factory-body counter và identity để chẩn đoán.

### 17.4. Cách test bằng mock/spy

Nếu thư viện trả một object giữ socket/thread mà test không tiện so identity trực tiếp, hãy bọc việc tạo object trong factory dễ spy, hoặc dùng một provider/test counter độc lập. Test các invariant:

- Số lần factory được gọi theo policy.
- Bean consumer nhận đúng managed dependency.
- Context shutdown đóng tài nguyên do Spring sở hữu và **không** đóng object thuộc ownership khác.
- Không có hai connection pools/clients bị tạo bất ngờ.

Không cần mock trực tiếp CGLIB interceptor nội bộ của Spring; test behavior quan sát được sẽ ổn định và hữu ích hơn.

## 18. Bài tập và đáp án

**Câu 1.** Trong full `@Configuration`, `@Bean A a()` gọi `b()` hai lần; `b` là singleton. Hai kết quả có luôn là hai object khác nhau không?

**Đáp:** Không. Với lời gọi đủ điều kiện được intercept qua enhanced configuration, cả hai lookup thường trả cùng managed singleton `b`.

**Câu 2.** Thay full config bằng `@Configuration(proxyBeanMethods=false)` mà giữ lời gọi `b()` trong `a()`, điều gì thay đổi?

**Đáp:** `b()` trở thành lời gọi Java bình thường, có thể thực thi factory body mỗi lần và tạo object ngoài bean `b` mà Spring đã/sẽ quản lý.

**Câu 3.** Làm sao viết lại `a()` để dùng singleton đúng trong lite mode?

**Đáp:** `@Bean A a(B b) { return new A(b); }`. Spring giải quyết dependency parameter theo bean definition/scope.

**Câu 4.** Nếu bean `b` là prototype ở full mode, hai lời gọi chéo qua enhanced configuration có phải cùng instance không?

**Đáp:** Không. Mỗi container lookup tới prototype thông thường tạo một instance mới theo scope, nên hai kết quả có thể khác nhau.

**Câu 5.** Vì sao static `@Bean` không được intercept, kể cả trong full configuration?

**Đáp:** CGLIB dùng subclass và override method; static Java methods không được override.

**Câu 6.** Nếu Spring đã đăng ký bean `clock` thì lời gọi `new MyConfig().clock()` có lấy singleton ấy không?

**Đáp:** Không. Object configuration tự tạo ngoài container không được enhanced; method call chỉ là Java thường.

**Câu 7.** Vì sao cùng một lời gọi `new VendorClient()` trong lite config có thể gây leak tài nguyên?

**Đáp:** Nếu nó được gọi từ một factory method khác, object phụ có thể không được đăng ký làm bean và không nhận destroy callback của managed `VendorClient`. Cần inject client từ container.

**Câu 8.** `@Bean` methods trong plain `@Component` có full inter-bean interception không?

**Đáp:** Không. Đó là lite mode, nên lời gọi chéo không được chuyển sang Spring-managed lookup.

**Câu 9.** Có nên dùng `@Primary` thay cho tham số `@Bean` khi muốn chuyển sang lite mode không?

**Đáp:** `@Primary` giải quyết việc lựa chọn ứng viên theo type; nó không làm một direct Java call được intercept. Vẫn cần parameter injection, có qualifier nếu cần chọn một bean cụ thể.

**Câu 10.** Vì sao test với `new FullConfig()` có thể cho kết quả khác với test tạo `AnnotationConfigApplicationContext(FullConfig.class)`?

**Đáp:** Chỉ context thực sự tạo/enhance configuration bean và can thiệp bean lookup. Object tự new không có CGLIB enhancement.

**Câu 11.** Một service singleton cần prototype mới mỗi request nghiệp vụ. Có nên gọi trực tiếp factory method `prototypeBean()` từ service?

**Đáp:** Không nên. Hãy inject `ObjectProvider<PrototypeType>` hoặc cơ chế lookup tương đương, rồi yêu cầu bean mới từ container đúng thời điểm.

**Câu 12.** Có nên đổi mọi class `@Configuration` thành `proxyBeanMethods=false` mà không cần test không?

**Đáp:** Không. Chỉ an toàn khi không còn phụ thuộc vào inter-bean interception và đã kiểm tra scope/identity/lifecycle/proxy behavior.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): full `@Configuration` và lite `@Bean`, cảnh báo về cross-method calls khi không proxy.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): inter-bean dependencies, CGLIB subclassing, quy tắc scope và hạn chế final methods.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory methods, return type, lifecycle và scope.
- [Spring Framework 6.2 API — Configuration](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/Configuration.html): `proxyBeanMethods` và full/lite semantics.
- [Spring Framework 6.2 API — Bean](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/Bean.html): inter-bean references, static `@Bean` methods, scope và vòng đời.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype và các scope khác.

**Ghi nhớ cốt lõi:** Trong full `@Configuration(proxyBeanMethods=true)`, lời gọi **instance `@Bean` method** trên Spring-enhanced configuration được đưa qua BeanFactory để tuân theo bean scope/lifecycle. Trong lite mode (`proxyBeanMethods=false` hoặc `@Bean` trên plain `@Component`), cùng lời gọi là Java thông thường. **Tham số của phương thức `@Bean` là cách biểu diễn dependency rõ ràng, an toàn và ít phụ thuộc chế độ cấu hình nhất.**
