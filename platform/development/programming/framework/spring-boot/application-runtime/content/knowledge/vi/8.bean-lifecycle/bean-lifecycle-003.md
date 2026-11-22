# Thứ tự @PostConstruct, InitializingBean và initMethod trong vòng đời bean

Một bean Spring thường được **tạo đối tượng**, **tiêm dependency**, rồi **khởi tạo (initialization)** trước khi được cung cấp cho thành phần khác sử dụng bình thường. Trong giai đoạn khởi tạo, Spring hỗ trợ nhiều cơ chế callback: phương thức đánh dấu `@PostConstruct`, interface `InitializingBean` và phương thức khởi tạo tùy chỉnh được khai báo qua `@Bean(initMethod = "...")` hoặc metadata tương đương.

Khi một bean **đồng thời** có cả ba callback, mỗi callback là một phương thức khác nhau, thứ tự Spring gọi là:

1. **`@PostConstruct`**
2. **`InitializingBean.afterPropertiesSet()`**
3. **Custom `initMethod`**

Thứ tự này được Spring Framework quy định cho **các callback trên cùng một bean**. Nó không có nghĩa mọi `@PostConstruct` của mọi bean trong ứng dụng đều chạy trước tất cả các `afterPropertiesSet()`. Những bean khác nhau có thể được tạo theo quan hệ dependency, cách quét bean, cấu hình lazy và những điều kiện container khác.

Bài học sử dụng Spring Boot 3.3.x và Java 17 trở lên. Spring Boot dựa trên Spring Framework để quản lý vòng đời bean, nên quy tắc cốt lõi thuộc Spring IoC container, không phải một thứ tự riêng do `SpringApplication.run()` tự định nghĩa.

## 1. Callback khởi tạo được gọi khi nào?

Luồng rút gọn của **một bean singleton thông thường**:

~~~text
Spring quyết định cần tạo bean
    |
    v
Gọi constructor hoặc @Bean factory method
    |
    v
Gán property, tiêm dependency và cấu hình cần thiết
    |
    v
BeanPostProcessor trước initialization
  (cơ chế xử lý @PostConstruct nằm trong giai đoạn này)
    |
    v
@PostConstruct
    |
    v
InitializingBean.afterPropertiesSet()
    |
    v
Phương thức được khai báo qua initMethod
    |
    v
BeanPostProcessor sau initialization
  (có thể tạo wrapper/proxy)
    |
    v
Bean sẵn sàng theo hợp đồng của container
~~~

Sơ đồ lược bỏ một số bước nội bộ như `Aware` callback, các loại `BeanPostProcessor` và cơ chế đăng ký bean. Đối với bean dùng `@Autowired` hoặc `@Value`, giá trị được tiêm thường đã sẵn sàng trước khi ba callback khởi tạo chạy.

Điều đặc biệt quan trọng: **“post construct” là sau khi tạo và cấu hình chính bean đó**, không đồng nghĩa “sau khi tất cả bean trong ứng dụng đã được tạo” hoặc “sau khi ứng dụng đã sẵn sàng phục vụ request”.

### Tại sao cần các callback sau constructor?

Constructor thích hợp cho việc nhận dependency bắt buộc và xác lập invariant của đối tượng. Nhưng một số giá trị có thể được Spring gán qua setter, field injection, binding cấu hình hoặc post-processor sau khi constructor kết thúc. Callback khởi tạo là cơ hội để:

- Kiểm tra các property và dependency đã được cấu hình hợp lệ.
- Chuẩn bị cấu trúc dữ liệu nội bộ dựa trên cấu hình cuối cùng của bean.
- Tạo cache nhỏ hoặc tính trước một giá trị thuần bộ nhớ.
- Báo lỗi sớm nếu bean chưa thể hoạt động theo hợp đồng của nó.

Callback khởi tạo **không phù hợp mặc định** cho những tác vụ kéo dài, chờ network lâu, khởi tạo toàn bộ dữ liệu từ xa hoặc điều phối toàn hệ thống. Những việc này có thể chặn startup, giữ lock của việc tạo singleton hoặc tạo vòng phụ thuộc khó gỡ.

## 2. Ba cơ chế hoạt động khác nhau thế nào?

| Cơ chế | Cách khai báo | Đặc điểm |
|---|---|---|
| `@PostConstruct` | Đánh dấu một phương thức không nhận tham số trên bean. | Dễ đọc, phổ biến, dùng annotation chuẩn Jakarta trong Spring Boot 3. |
| `InitializingBean` | Bean implement `org.springframework.beans.factory.InitializingBean` và override `afterPropertiesSet()`. | Spring-specific; nhận callback sau khi container gán các property cần thiết. |
| `initMethod` | Ví dụ `@Bean(initMethod = "customInit")` trong lớp cấu hình. | Giữ class nghiệp vụ độc lập với annotation/interface của Spring; tên callback nằm trong bean definition. |

Cả ba đều là **callback khởi tạo của bean**, không phải ba giai đoạn riêng của `SpringApplication` và cũng không phải ba dấu mốc của toàn ứng dụng.

### `@PostConstruct`

Trong Spring Boot 3.x, import annotation:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Ví dụ:

~~~java
@PostConstruct
public void validate() {
    System.out.println("Bean da duoc inject dependency");
}
~~~

Phương thức callback thông thường có kiểu trả về `void`, không nhận tham số và là instance method. Nó chỉ được Spring gọi khi **đối tượng là bean do container quản lý**, và bộ xử lý annotation tương ứng được bật. Gọi `new MyService()` trong Java thuần **không tự kích hoạt** `@PostConstruct`.

Spring Boot 3 dùng namespace `jakarta.annotation`. Code cũ sử dụng `javax.annotation.PostConstruct` từ các phiên bản Java/Spring trước có thể cần chuyển import và dependency khi nâng cấp. Không suy đoán JDK hiện đại tự chứa sẵn API Jakarta; dependency của dự án cần cung cấp annotation này.

### `InitializingBean.afterPropertiesSet()`

Khi một bean implement interface:

~~~java
import org.springframework.beans.factory.InitializingBean;

public class SettingsVerifier implements InitializingBean {

    @Override
    public void afterPropertiesSet() throws Exception {
        System.out.println("Properties da san sang");
    }
}
~~~

Spring gọi `afterPropertiesSet()` sau khi gán các bean properties cần thiết và xử lý các callback `Aware` liên quan. Vì interface đến từ Spring, class có sự phụ thuộc trực tiếp vào Spring Framework; thư viện hoặc domain class muốn giữ độc lập thường ưu tiên `@PostConstruct` hoặc custom init method.

Tên `afterPropertiesSet` **không** có nghĩa mọi công việc của hệ thống đã hoàn tất. Chỉ phần khởi tạo thuộc bean này và các dependency được yêu cầu của nó đạt đến giai đoạn phù hợp.

### Custom `initMethod`

Với Java configuration:

~~~java
@Bean(initMethod = "validateConfiguration")
SettingsVerifier settingsVerifier() {
    return new SettingsVerifier();
}
~~~

Spring tìm và gọi `validateConfiguration()` trên **bean được trả về** bởi factory method, không phải gọi phương thức đó trên class cấu hình. Đoạn này chỉ là ví dụ minh họa: muốn chạy thực tế cần thêm phương thức `validateConfiguration()` không nhận tham số vào `SettingsVerifier` và khai báo bean ở trong một `@Configuration` class.

Nếu định nghĩa bằng XML cổ điển, khái niệm tương đương là thuộc tính `init-method="validateConfiguration"` trên `<bean>`. Trong mã Java dùng Spring Boot, `@Bean(initMethod = "...")` thường dễ theo dõi hơn.

Không có annotation `@InitMethod` mặc định của Spring dành cho trường hợp này. `initMethod` là **thuộc tính của `@Bean`** (hoặc thuộc bean definition), và chuỗi tên phương thức phải khớp với callback thực sự tồn tại.

## 3. Ví dụ hoàn chỉnh: quan sát thứ tự chính xác

Tạo dự án **Spring Boot 3.3.x**, Java 17 trở lên, có dependency `spring-boot-starter`. Đặt mã sau trong tệp:

`src/main/java/com/example/lifecycle/InitOrderApplication.java`

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class InitOrderApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(InitOrderApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println(
                    "4. main: context active = " + context.isActive());
        }
    }

    @Bean(initMethod = "customInit")
    InitProbe initProbe() {
        return new InitProbe("billing");
    }

    public static final class InitProbe implements InitializingBean {

        private final String name;

        public InitProbe(String name) {
            this.name = name;
            System.out.println("0. constructor: " + name);
        }

        @PostConstruct
        public void postConstruct() {
            System.out.println("1. @PostConstruct: " + name);
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println(
                    "2. InitializingBean.afterPropertiesSet: " + name);
        }

        public void customInit() {
            System.out.println("3. @Bean(initMethod): " + name);
        }
    }
}
~~~

Trong ví dụ này:

- `@SpringBootApplication` đưa lớp gốc vào cấu hình Boot và cho phép `@Bean` được xử lý.
- `@Bean(initMethod = "customInit")` tạo bean `initProbe`. `new InitProbe("billing")` in dòng constructor trước khi các callback lifecycle được gọi.
- `InitProbe` có **ba phương thức callback khác tên**; chúng minh họa ba cơ chế cùng tồn tại trên **một instance**.
- `WebApplicationType.NONE` loại bỏ phần khởi tạo web server, để dễ quan sát vòng đời bean.
- `try-with-resources` gọi `close()` lên context khi hết khối try; điều này giúp chương trình console kết thúc gọn gàng.

### Cách chạy

Dùng Gradle wrapper của một dự án Spring Boot đã cấu hình main class:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Hoặc với dự án Maven có Spring Boot Maven plugin:

~~~bash
./mvnw spring-boot:run
~~~

Nếu dự án có nhiều main class, hãy chỉ định `com.example.lifecycle.InitOrderApplication` làm main class cho `bootRun`/plugin tương ứng. Đây là mã cần Spring Boot/Spring Framework trên classpath, nên **không thể chạy độc lập chỉ bằng `javac InitOrderApplication.java`**.

Bỏ qua banner và những dòng log của Spring Boot, các dòng do chính chương trình trên in ra theo thứ tự:

~~~text
0. constructor: billing
1. @PostConstruct: billing
2. InitializingBean.afterPropertiesSet: billing
3. @Bean(initMethod): billing
4. main: context active = true
~~~

**Vì sao đây là thứ tự xác định?**

1. Factory method `initProbe()` tạo `InitProbe` nên constructor in `0`.
2. Sau khi Spring xử lý cấu hình và dependency cho bean, phương thức `@PostConstruct` được gọi, in `1`.
3. Container phát hiện instance implement `InitializingBean`, gọi `afterPropertiesSet()`, in `2`.
4. Bean definition chỉ định `customInit` làm init method, nên Spring gọi nó sau callback interface, in `3`.
5. Khi quá trình startup và startup runners (nếu có) hoàn tất bình thường, `app.run(args)` trả về context còn active; `main` in `4`.

Chú ý dòng **4** không phải một callback khởi tạo bean. Nó là dòng Java thông thường ở `main` sau khi Boot đã chạy xong quá trình startup. Log hệ thống có thể xen giữa các dòng tự in nhưng không thay đổi quan hệ thứ tự 0–4 trong ví dụ.

## 4. Sự khác biệt quan trọng giữa ba thời điểm

Để dễ phân biệt những điều có thể làm ở mỗi callback, xem xét một bean dùng cấu hình sau:

~~~java
public class ConnectionSettings implements InitializingBean {

    private String endpoint;

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    @PostConstruct
    public void verifyEndpoint() {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalStateException("endpoint is required");
        }
    }

    @Override
    public void afterPropertiesSet() {
        // Có thể kiểm tra thêm invariant sau khi properties đã được gán.
    }

    public void prepare() {
        // Chuẩn bị dữ liệu nội bộ từ endpoint đã hợp lệ.
    }
}
~~~

Đây là class minh họa, cần import `jakarta.annotation.PostConstruct` và `InitializingBean`. Để callback chạy, object phải được Spring đăng ký thành bean và phương thức `prepare()` phải được khai báo làm custom init method nếu muốn Spring gọi nó tự động.

**Không có phép màu nào ở đây:**

- Cả `verifyEndpoint()`, `afterPropertiesSet()` và `prepare()` đều thấy `endpoint` đã được container gán, nếu bean được cấu hình đúng.
- `@PostConstruct` chạy đầu tiên **trong ba callback trên**. Nó không nhất thiết có ít dependency hơn callback khác; những dependency được inject vào chính bean thường đã có.
- `afterPropertiesSet()` không đợi ApplicationContext refresh xong toàn bộ mới chạy.
- `prepare()` chạy sau hai callback trước nếu bạn cấu hình `initMethod = "prepare"`, nhưng không tự chạy chỉ vì phương thức mang tên `prepare`.

Nếu mục tiêu của bạn đơn giản là kiểm tra `endpoint` rồi tạo một cấu trúc dữ liệu nội bộ, **chỉ chọn một callback** thường dễ bảo trì hơn việc rải cùng một công việc vào cả ba.

## 5. Spring đảm bảo thứ tự trong phạm vi nào?

Quy tắc **`@PostConstruct` → `afterPropertiesSet()` → `initMethod`** áp dụng khi:

1. Một instance được tạo và quản lý như Spring bean.
2. Các callback tương ứng được khai báo hợp lệ và cơ chế xử lý annotation hoạt động.
3. Ba cơ chế trỏ đến **các phương thức riêng biệt** của bean.

Spring Framework cũng quy định: nếu nhiều cơ chế chỉ về **cùng một tên phương thức khởi tạo**, thì không gọi phương thức đó nhiều lần chỉ vì nó được đăng ký lặp qua các cơ chế. Tuy nhiên, tốt nhất vẫn tránh khai báo trùng một callback ở nhiều nơi vì code trở nên khó đọc.

Ví dụ gây nhầm lẫn:

~~~java
public class DuplicateInitExample {

    @PostConstruct
    public void initialize() {
        System.out.println("initialize");
    }
}
~~~

Nếu bean này lại được khai báo bằng `@Bean(initMethod = "initialize")`, bạn **không nên dựa vào suy luận “hai annotation = hai lần chạy”**. Spring có cơ chế tránh gọi trùng cùng phương thức khởi tạo theo hợp đồng lifecycle. Quan trọng hơn, một phương thức không nên gánh trách nhiệm lặp chỉ do người viết config đăng ký hai lần.

### Không có thứ tự callback toàn cục giữa các bean

Giả sử bean A và bean B đều có `@PostConstruct`, `afterPropertiesSet()` và `initMethod`. Spring không đưa ra cam kết kiểu:

~~~text
@PostConstruct(A)
@PostConstruct(B)
afterPropertiesSet(A)
afterPropertiesSet(B)
initMethod(A)
initMethod(B)
~~~

Thay vào đó, Spring thường tạo và khởi tạo **trọn vẹn bean đang được tạo**, sau đó mới tiếp tục các bean khác theo nhu cầu và quan hệ dependency. Một dependency B có thể được khởi tạo xong trước khi bean A hoàn tất injection.

Nếu bạn muốn A chỉ được tạo sau B, hãy biểu diễn quan hệ **dependency thực sự** qua constructor/factory method injection. Khi cần quan hệ thứ tự khởi tạo mà không có injection trực tiếp, có thể dùng `@DependsOn("beanB")` có chủ đích. `@DependsOn` điều khiển quan hệ giữa **các bean**, không đảo thứ tự ba callback trên cùng một bean.

Annotation `@Order` hoặc interface `Ordered` cũng **không thay** thứ tự `@PostConstruct`, `afterPropertiesSet()` và `initMethod` của một bean.

## 6. Một cái bẫy: `@PostConstruct` không phải thời điểm mọi thứ đã ready

Tên `@PostConstruct` dễ khiến người mới học nghĩ rằng callback chạy sau khi Spring Boot đã hoàn tất khởi động. Thực tế, nó xảy ra trong **quá trình tạo bean**, thường **trước khi refresh context hoàn tất**.

So sánh những mốc khác nhau:

| Mốc | Phạm vi và mục đích |
|---|---|
| Constructor | Khởi tạo đối tượng Java, nhận dependency qua constructor. |
| `@PostConstruct` | Kiểm tra và chuẩn bị chính bean sau injection. |
| `InitializingBean.afterPropertiesSet()` | Callback Spring-specific sau khi cấu hình bean đã được gán. |
| `@Bean(initMethod = "...")` | Callback tùy chỉnh trên bean theo bean definition. |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Chạy sau giai đoạn pre-instantiation của những singleton non-lazy thông thường. |
| `ContextRefreshedEvent` | Phát khi context hoàn tất một lần refresh. |
| `ApplicationRunner` / `CommandLineRunner` | Logic startup của Spring Boot sau khi context refresh. |
| `ApplicationReadyEvent` | Boot báo hiệu startup bình thường đã đi qua các runner. |

Ví dụ, nếu bạn cần **kiểm tra property của một bean**, `@PostConstruct` là phù hợp. Nếu bạn cần **thực hiện một bước khởi động ứng dụng sau khi toàn bộ context đã refresh**, một runner hoặc listener sự kiện có thể phù hợp hơn.

Điểm cần cân nhắc: `SmartInitializingSingleton` chỉ nói đến vòng đời những singleton đã được eagerly khởi tạo trong vòng pre-instantiation. Nó không có nghĩa toàn bộ bean lazy/prototype đều được tạo, cũng không tự bảo đảm hệ thống bên ngoài đã sẵn sàng.

### Tại sao không nên truy cập nhiều bean khác từ `@PostConstruct`?

Những callback khởi tạo có thể chạy trong lúc Spring vẫn giữ cơ chế đồng bộ/lock liên quan việc tạo singleton. Nếu callback khởi động luồng khác rồi **đợi** luồng đó lấy bean từ cùng container, bạn có thể tự tạo deadlock. Nếu callback kéo dài do database/network không phản hồi, toàn bộ startup có thể bị kéo dài hoặc thất bại.

Hãy để callback này xử lý việc ngắn, đồng bộ, gần với trạng thái nội bộ của bean. Với công việc cần nhiều bean đã sẵn sàng, xem xét `SmartInitializingSingleton` hoặc `ContextRefreshedEvent`; với startup nghiệp vụ của Spring Boot, xem xét `ApplicationRunner`/`CommandLineRunner`. Lựa chọn cuối cùng phụ thuộc việc công việc cần chạy **mỗi bean**, **mỗi context refresh** hay **mỗi lần Boot startup**.

## 7. Hậu quả khi callback ném exception

Một callback lifecycle có thể chủ động từ chối khởi tạo bean nếu cấu hình không hợp lệ.

Ví dụ:

~~~java
@PostConstruct
public void validate() {
    if (connectionTimeoutMillis <= 0) {
        throw new IllegalStateException(
                "connectionTimeoutMillis must be positive");
    }
}
~~~

Đây là đoạn code trong bean đã có field `connectionTimeoutMillis` và import `PostConstruct`. Khi bean singleton non-lazy được tạo trong startup, exception có thể bị Spring bọc thành `BeanCreationException` và khiến quá trình refresh/context startup thất bại. Các thông báo cấp cao có thể khác nhau tùy vị trí ném lỗi; khi gỡ lỗi phải tìm **root cause**.

So sánh:

- Lỗi trong `@PostConstruct`: Spring không tiếp tục gọi `afterPropertiesSet()` và `initMethod` cho cùng bean như thể initialization đã thành công.
- Lỗi trong `afterPropertiesSet()`: `@PostConstruct` có thể đã chạy, nhưng custom `initMethod` chưa chạy.
- Lỗi trong custom `initMethod`: hai callback trước có thể đã chạy, nhưng bean vẫn chưa được khởi tạo thành công theo container.
- Với bean `@Lazy`, exception có thể chỉ xuất hiện ở lần bean được truy xuất và cần tạo, **sau khi lần startup ban đầu đã kết thúc**.

Đừng bắt rồi nuốt hết exception chỉ để “ứng dụng khởi động được”, nếu bean đó thực tế không thể phục vụ nghiệp vụ. Nếu cần cơ chế fallback, hãy biểu diễn trạng thái degraded một cách có chủ đích và để downstream code biết khi nào dependency không sẵn sàng.

## 8. Ảnh hưởng của scope và lazy initialization

**Singleton non-lazy (thông thường):** Spring tạo và chạy các callback trong quá trình refresh nếu bean nằm trong tập singleton cần được pre-instantiate. Mỗi lần một singleton được tạo thành công trong một context, các callback đó chạy một lần cho instance ấy.

**Lazy singleton:** Một bean đánh dấu `@Lazy` có thể chưa được tạo trong startup. Các callback chỉ chạy khi Spring thật sự tạo bean, chẳng hạn ở lần `getBean()` đầu tiên. Nếu một singleton non-lazy phụ thuộc bắt buộc vào bean lazy, dependency đó vẫn có thể phải được tạo sớm.

**Prototype:** Mỗi lần Spring tạo một prototype instance, nó thực hiện injection và initialization callback cho instance mới. Tuy nhiên, Spring không tự theo dõi toàn bộ vòng đời destroy của prototype sau khi bàn giao bean cho caller. Không nhầm initialize mỗi lần với tự đóng tài nguyên mỗi lần.

**Nhiều ApplicationContext:** Một lớp bean được khai báo giống nhau trong hai context độc lập có thể tạo hai singleton instance và chạy callback trên từng instance. Quy tắc ba callback vẫn tính theo **từng bean instance**, không theo toàn JVM.

Ví dụ minh họa lazy bean:

~~~java
@Bean(initMethod = "customInit")
@Lazy
InitProbe initProbe() {
    return new InitProbe("billing");
}
~~~

Đây là đoạn thay thế phương thức `@Bean` của ví dụ chính và cần import `org.springframework.context.annotation.Lazy`. Nếu không có bean nào yêu cầu `InitProbe` trong startup, các dòng 0–3 không xuất hiện ngay khi `app.run(args)`, mà có thể xuất hiện khi code gọi `context.getBean(InitProbe.class)` lần đầu.

## 9. Callback khởi tạo và proxy/AOP/transaction

Một bean có thể được Spring bọc bằng proxy để hỗ trợ AOP như `@Transactional` hoặc `@Async`. Nhưng initialization callback thường chạy **trên bean đang được tạo**, trước khi proxy cuối cùng được đưa cho các thành phần khác.

Vì thế:

- Không nên kỳ vọng `@Transactional` trên `@PostConstruct` hoặc phương thức `initMethod` sẽ có transaction giống khi một caller từ ngoài gọi qua proxy.
- Không nên kỳ vọng `@Async` trên phương thức callback sẽ biến callback thành tác vụ async đúng như một lời gọi qua proxy sau startup.
- Lời gọi từ một phương thức trong bean sang phương thức khác của **chính bean đó** có thể bỏ qua Spring proxy (self-invocation), ngay cả ở thời điểm ứng dụng hoạt động bình thường.
- Callback nhận dependency đã được Spring inject nhưng bean chưa chắc đã sẵn sàng sử dụng mọi tiện ích liên quan đến các bean khác hoặc tầng giao tiếp bên ngoài.

Nếu một thao tác cần transaction quản lý đầy đủ, cân nhắc gọi một service khác qua proxy đúng thời điểm từ runner/listener; giữ callback khởi tạo phục vụ validation và chuẩn bị trạng thái nội bộ.

## 10. Bên cạnh init còn có destroy, nhưng đó là giai đoạn khác

Ba callback trong đề bài đều thuộc **initialization**. Khi context đóng, Spring hỗ trợ những callback hủy tương ứng, chẳng hạn:

| Khởi tạo | Hủy/dọn dẹp |
|---|---|
| `@PostConstruct` | `@PreDestroy` |
| `InitializingBean.afterPropertiesSet()` | `DisposableBean.destroy()` |
| `@Bean(initMethod = "...")` | `@Bean(destroyMethod = "...")` |

Nếu có nhiều cơ chế destroy khác nhau cho cùng một bean, Spring cũng có quy tắc về thứ tự callback hủy. Đừng hiểu callback khởi tạo là nơi đóng tài nguyên. Ví dụ một bean tạo cache ở init thì nên dọn cache hoặc đóng kết nối trong destroy callback tương ứng nếu có tài nguyên cần thu hồi.

Một số loại tài nguyên như connection pool, executor hoặc client có phương thức `close()`/`shutdown()` có thể được Spring hỗ trợ suy luận destroy method trong bean definition. Tuy nhiên việc cleanup phụ thuộc cách bean được khai báo và scope; một object do bạn tự `new` bên ngoài Spring không tự được container quản lý.

## 11. Những lỗi thường gặp

**Lỗi 1 — “`@PostConstruct` chạy ngay sau constructor”.**

Chưa chính xác. Spring còn phải thiết lập các dependency/property và xử lý cơ chế trước initialization. Callback chỉ chạy khi bean đi đến pha phù hợp trong container. Nếu tự gọi `new`, annotation không có cơ chế tự chạy.

**Lỗi 2 — “`afterPropertiesSet()` chạy sau khi context refresh hoàn tất”.**

Sai. Nó là callback **trên từng bean**, trong quá trình bean được khởi tạo. Có thể còn rất nhiều bean và bước refresh khác chưa hoàn tất.

**Lỗi 3 — “Chỉ cần viết một method tên `init` thì Spring tự gọi”.**

Chưa đủ. Phương thức phải được cấu hình làm custom init method, được nhận diện bởi cơ chế lifecycle thích hợp, hoặc được gọi tường minh bởi code của bạn. `@Bean(initMethod = "init")` là một cách khai báo rõ ràng.

**Lỗi 4 — “Khai báo ba cơ chế sẽ chạy theo thứ tự ngẫu nhiên”.**

Không đúng với ba callback **khác tên trên cùng bean**: Spring quy định rõ `@PostConstruct`, rồi `afterPropertiesSet()`, cuối cùng custom `initMethod`.

**Lỗi 5 — “Có thể dùng `@Order` để đổi thứ tự ba callback”.**

Không. `@Order` không đảo hợp đồng initialization callback. Nếu muốn đổi trình tự công việc của chính bean, hãy gom logic vào một callback và tự gọi các bước theo thứ tự rõ ràng.

**Lỗi 6 — “`@PostConstruct` là chỗ tốt để chạy migration dữ liệu nặng”.**

Thường không. Callback có thể chạy trong quá trình tạo singleton và làm chậm, gây deadlock hoặc chặn startup. Dùng cơ chế startup thích hợp cho công việc toàn ứng dụng và thiết kế timeout/retry riêng.

**Lỗi 7 — “Trong Spring Boot 3 vẫn dùng `javax.annotation.PostConstruct` như cũ”.**

Boot 3 sử dụng các API Jakarta tương ứng; import thông thường là `jakarta.annotation.PostConstruct`. Hãy kiểm tra dependency thay vì đoán annotation có sẵn trong JDK.

**Lỗi 8 — “Tôi thấy bean in ra kết quả một lần, nghĩa là callback chạy đúng một lần trong toàn chương trình”.**

Không luôn đúng. Có thể có hai context, bean prototype, hoặc nhiều lần refresh/tạo bean. Phạm vi của callback là instance được container tạo, không phải một lần cố định cho toàn JVM.

## 12. Bài thực hành kiểm chứng

Dùng ví dụ `InitOrderApplication` ở mục 3 và thử:

1. **Bỏ `@PostConstruct`** khỏi `postConstruct()`: dòng `1` không còn do Spring tự gọi, nhưng dòng `2` và `3` vẫn chạy.
2. **Bỏ `implements InitializingBean`** và phương thức `afterPropertiesSet()`: dòng `2` biến mất. Hai cơ chế còn lại vẫn hoạt động.
3. **Bỏ `initMethod = "customInit"`** khỏi `@Bean`: dòng `3` biến mất. Chỉ việc có method tên `customInit` không khiến Spring gọi nó.
4. **Đổi `initMethod` sang tên không tồn tại**: quan sát lỗi tạo bean lúc startup. Truy root cause thay vì chỉ đọc thông báo chung “Application failed to start”.
5. **Thêm `@Lazy` vào `@Bean`**, rồi gọi `context.getBean(InitProbe.class)` trong `main` sau `run`: quan sát các callback dời tới thời điểm bean thật sự được tạo.
6. **Tạo trực tiếp `new InitProbe("manual")`** bên ngoài container: constructor chạy, nhưng các callback không được Spring gọi tự động.

Mỗi thử nghiệm nên thay **một điều kiện** rồi chạy lại để nhìn mối quan hệ nhân quả. Với experiment `@Lazy`, nhớ rằng việc có dependency non-lazy khác yêu cầu bean vẫn có thể buộc nó khởi tạo sớm.

### Tài liệu tham khảo

- Spring Framework – Customizing the Nature of a Bean, phần *Combining Lifecycle Mechanisms*: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Framework 6.1 – `InitializingBean` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/InitializingBean.html
- Spring Boot 3.3 – Features, SpringApplication: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Ghi nhớ:** Khi **cùng một Spring bean** khai báo ba callback **khác phương thức**, Spring khởi tạo theo thứ tự **`@PostConstruct` → `InitializingBean.afterPropertiesSet()` → `@Bean(initMethod = "...")`**. Chúng diễn ra **sau khi bean được cấu hình và trước khi bean hoàn tất initialization**, không phải các mốc startup của toàn ứng dụng. Chọn một cơ chế phù hợp cho công việc của bean thường rõ ràng và dễ bảo trì hơn dùng cả ba chỉ để làm cùng một việc.
