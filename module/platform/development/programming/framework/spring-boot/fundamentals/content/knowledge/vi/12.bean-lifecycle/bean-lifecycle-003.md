# @PostConstruct và namespace jakarta.annotation theo dòng phiên bản

Trong vòng đời của một Spring bean, có những công việc chỉ nên thực hiện sau khi Spring đã tạo object và tiêm các dependency cần thiết. Ví dụ, bean cần kiểm tra cấu hình đã được bind, xây dựng một cấu trúc dữ liệu nội bộ hoặc chuẩn bị trạng thái ban đầu trước khi được sử dụng. Annotation `@PostConstruct` cung cấp một callback cho giai đoạn này.

Khi làm việc với Spring Boot, cần chú ý **namespace của annotation thay đổi theo thế hệ Spring Framework**:

- Spring Boot 2.x (Spring Framework 5.x) sử dụng `javax.annotation.PostConstruct`.
- Spring Boot 3.x (Spring Framework 6.x) sử dụng `jakarta.annotation.PostConstruct`.

Đây là thay đổi quan trọng khi nâng cấp ứng dụng. Hai annotation có tên và mục đích tương tự, nhưng thuộc **hai package khác nhau**, nên code import sai namespace có thể không biên dịch hoặc callback không được Spring xử lý như mong đợi.

## 1. @PostConstruct dùng để làm gì?

`@PostConstruct` đánh dấu một phương thức cần được gọi sau khi dependency injection và các bước thiết lập bean ban đầu hoàn tất, trước khi bean được đưa vào sử dụng bình thường.

Ví dụ với Spring Boot 3:

~~~java
package com.example.catalog.service;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class CatalogCache {

    private final ProductRepository productRepository;

    private java.util.Map<Long, String> productNames;

    public CatalogCache(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @PostConstruct
    void initialize() {
        this.productNames = productRepository.findAllNames();
    }

    public String findName(long productId) {
        return productNames.get(productId);
    }
}
~~~

Khi Spring tạo `CatalogCache`:

1. Tạo instance của class.
2. Tiêm `ProductRepository` qua constructor.
3. Xử lý các bước thiết lập dependency và callback liên quan.
4. Gọi phương thức `initialize()` có `@PostConstruct`.
5. Hoàn thành giai đoạn khởi tạo bean và đưa bean vào sử dụng.

Khi `initialize()` chạy, trường `productRepository` đã được gán. Đây là lý do callback này thích hợp cho công việc cần sử dụng dependency đã được inject.

Ví dụ trên giả định `ProductRepository.findAllNames()` là API do ứng dụng định nghĩa. Việc tải toàn bộ dữ liệu vào bộ nhớ chỉ phù hợp khi kích thước dữ liệu và chính sách làm mới cache được kiểm soát; không nên xem `@PostConstruct` là nơi mặc định để tải dữ liệu lớn hoặc gọi dịch vụ ngoài không giới hạn.

**Spring Framework thực thi lifecycle callback này.** Spring Boot cung cấp môi trường khởi động và cấu hình ứng dụng; bản thân `@PostConstruct` thuộc Jakarta/Java Common Annotations API (hoặc namespace Java EE cũ), không phải annotation riêng của Spring Boot.

## 2. Namespace javax và jakarta khác nhau như thế nào?

Trong các phiên bản cũ, annotation được khai báo trong package `javax.annotation`:

~~~java
import javax.annotation.PostConstruct;
~~~

Từ thế hệ Jakarta EE, các API Java EE được chuyển sang namespace `jakarta.*`:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Tên class ngắn vẫn là `PostConstruct`, nhưng tên đầy đủ khác nhau:

| Thế hệ | Fully qualified class name |
|---|---|
| Java EE / javax | `javax.annotation.PostConstruct` |
| Jakarta EE / jakarta | `jakarta.annotation.PostConstruct` |

Trong JVM, hai tên đầy đủ này là **hai kiểu khác nhau**. Một annotation được biên dịch với `javax.annotation.PostConstruct` không phải là annotation `jakarta.annotation.PostConstruct`. Việc chỉ đổi tên dependency hoặc chỉ đổi phiên bản JDK không làm cho hai kiểu tự tương thích.

## 3. Chọn import theo dòng Spring Boot

Quy tắc thực hành quan trọng:

| Spring Boot | Spring Framework nền tảng | Namespace dùng cho @PostConstruct |
|---|---|---|
| Boot 2.x | Spring Framework 5.x | `javax.annotation.PostConstruct` |
| Boot 3.x | Spring Framework 6.x | `jakarta.annotation.PostConstruct` |

Boot 3 là mốc chuyển đổi lớn sang Jakarta EE APIs. Nếu một dự án được nâng từ Boot 2 lên Boot 3, cần chuyển các import Java EE liên quan sang Jakarta tương ứng, trong đó có `PostConstruct` và `PreDestroy`.

Đối với các dòng Boot mới hơn tiếp tục dựa trên Spring Framework 6+ và Jakarta APIs, vẫn dùng namespace `jakarta.annotation`. Không nên xác định namespace dựa vào tên JDK đang chạy hoặc tên annotation đơn lẻ; hãy xem **phiên bản Spring Framework mà dòng Spring Boot đang quản lý**.

### 3.1. Ví dụ với Spring Boot 2.x

~~~java
package com.example.catalog;

import javax.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class StartupRegistry {

    @PostConstruct
    public void initialize() {
        // Chuẩn bị trạng thái sau khi dependency đã được inject.
    }
}
~~~

Đây là import phù hợp cho ứng dụng dựa trên Spring Framework 5.x, thường gặp trong Spring Boot 2.x.

### 3.2. Ví dụ với Spring Boot 3.x

~~~java
package com.example.catalog;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class StartupRegistry {

    @PostConstruct
    public void initialize() {
        // Chuẩn bị trạng thái sau khi dependency đã được inject.
    }
}
~~~

Phần thân class không đổi; khác biệt thể hiện ở package import. Với Spring Framework 6, callback được phát hiện theo annotation Jakarta.

## 4. Vì sao Java 11+ có thể cần khai báo dependency annotation API?

Một nhầm lẫn phổ biến là cho rằng `javax.annotation.PostConstruct` luôn có sẵn trong JDK vì từng thấy code chạy trên Java 8 mà không cần thêm thư viện.

Các API Java EE liên quan từng có mặt trong môi trường Java SE cũ thông qua các module Java EE/CORBA đã bị loại bỏ khỏi JDK. Từ **JDK 11**, `javax.annotation` không còn được cung cấp sẵn theo cách trước đây. Tương tự, `jakarta.annotation` cũng là API bên ngoài JDK, không phải package được Java SE tích hợp mặc định.

Vì vậy, ứng dụng phải có annotation API phù hợp trên compile/runtime classpath.

### 4.1. Spring Boot 2.x trên JDK hiện đại

Với dự án Boot 2.x dùng JDK 11 trở lên, nếu dependency tree chưa có API cũ, có thể khai báo:

~~~groovy
dependencies {
    implementation 'javax.annotation:javax.annotation-api'
}
~~~

Nếu dự án dùng Spring Boot dependency management/BOM, phiên bản tương thích có thể được quản lý tập trung. Nếu không dùng BOM, cần khai báo phiên bản API phù hợp thay vì để dependency không có version.

### 4.2. Spring Boot 3.x

Với dự án Boot 3.x, khai báo API Jakarta nếu chưa có trên classpath:

~~~groovy
dependencies {
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

Spring Boot dependency management quản lý phiên bản phù hợp khi dự án dùng BOM hoặc plugin quản lý dependency tương ứng. Không nên tự chọn một phiên bản Jakarta API tùy ý khi Spring Boot đã cung cấp version alignment.

### 4.3. Ví dụ Maven

Nếu dùng Maven với Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>jakarta.annotation</groupId>
    <artifactId>jakarta.annotation-api</artifactId>
</dependency>
~~~

Đối với Boot 2.x, tọa độ artifact tương ứng là:

~~~xml
<dependency>
    <groupId>javax.annotation</groupId>
    <artifactId>javax.annotation-api</artifactId>
</dependency>
~~~

Chỉ thêm dependency thuộc namespace tương ứng với dòng Spring Framework của ứng dụng. Nếu starter hoặc một dependency khác đã đưa API phù hợp vào classpath, không cần khai báo lặp lại.

## 5. Spring phát hiện và gọi @PostConstruct như thế nào?

Trong application context dựa trên annotation configuration, Spring đăng ký một `BeanPostProcessor` có trách nhiệm xử lý các annotation lifecycle như `@PostConstruct` và `@PreDestroy`. Cơ chế này thường được thực hiện bởi `CommonAnnotationBeanPostProcessor`, dựa trên hạ tầng `InitDestroyAnnotationBeanPostProcessor`.

Luồng khởi tạo khái quát:

~~~text
Spring cần tạo bean
       |
       v
Instantiate object
       |
       v
Constructor injection / populate properties
       |
       v
Aware callbacks (nếu có)
       |
       v
BeanPostProcessor before initialization
       |
       v
@PostConstruct callback
       |
       v
InitializingBean.afterPropertiesSet()
       |
       v
Custom init method (nếu có)
       |
       v
BeanPostProcessor after initialization
       |
       v
Bean sẵn sàng cho các bean khác sử dụng
~~~

Đây là thứ tự lifecycle phổ biến của Spring bean. Các bước cụ thể còn phụ thuộc loại bean, processor và cấu hình ứng dụng.

### Thứ tự giữa các callback khởi tạo

Nếu một bean đồng thời dùng nhiều cơ chế init, thứ tự thông thường là:

1. Phương thức `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Phương thức init tùy chỉnh khai báo bằng `@Bean(initMethod = "...")` hoặc cấu hình tương ứng.

Ví dụ:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.InitializingBean;

public class SearchIndex implements InitializingBean {

    @PostConstruct
    void postConstruct() {
        System.out.println("1. PostConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("2. afterPropertiesSet");
    }

    public void initializeIndex() {
        System.out.println("3. custom init method");
    }
}
~~~

Để chạy cả ba callback trong ví dụ, phải khai báo custom init method cho bean, ví dụ:

~~~java
@Bean(initMethod = "initializeIndex")
SearchIndex searchIndex() {
    return new SearchIndex();
}
~~~

Không nên đồng thời đăng ký `SearchIndex` bằng component scanning và một phương thức `@Bean` khác nếu không có chủ đích, vì có thể tạo hai bean definition riêng. Ví dụ hai đoạn trên minh họa cùng một bean definition được cấu hình để có cả callback, không phải hai cách đăng ký độc lập cần ghép tùy tiện.

## 6. Quy tắc viết phương thức @PostConstruct

Để callback dễ đọc và tương thích với hợp đồng lifecycle annotation, nên tuân theo các quy tắc:

- Phương thức không nhận tham số.
- Phương thức không phải `static`.
- Phương thức trả về `void`.
- Phương thức thường được đặt tên rõ ràng như `initialize()`, `loadMetadata()` hoặc `prepareCache()`.
- Giữ một callback chính cho mỗi class để thứ tự và trách nhiệm khởi tạo dễ dự đoán.
- Không gọi trực tiếp constructor hoặc tự khởi tạo object bằng `new` nếu kỳ vọng Spring sẽ gọi callback cho object đó.

Ví dụ phù hợp:

~~~java
@PostConstruct
void initialize() {
    // Khởi tạo trạng thái nội bộ.
}
~~~

Spring cho phép mức truy cập method phù hợp với quy tắc xử lý annotation của framework; không bắt buộc callback phải là `public`. Tuy nhiên, nên dùng `public` hoặc package-private/protected nhất quán với style của dự án và tránh làm method phức tạp.

Không viết:

~~~java
@PostConstruct
static void initialize() {
}
~~~

~~~java
@PostConstruct
void initialize(String mode) {
}
~~~

Các dạng trên không phù hợp với lifecycle callback thông thường vì method static hoặc có tham số không đáp ứng hợp đồng gọi callback.

## 7. @PostConstruct có được gọi với mọi scope không?

`@PostConstruct` gắn với **giai đoạn khởi tạo instance do Spring quản lý**, không chỉ riêng singleton.

| Scope | Thời điểm callback |
|---|---|
| Singleton | Khi singleton instance được tạo và khởi tạo |
| Prototype | Mỗi lần container tạo prototype instance |
| Request | Khi request-scoped instance được tạo trong request context |
| Session | Khi session-scoped instance được tạo |

Với singleton không lazy, callback thường chạy trong quá trình khởi động context. Với singleton lazy hoặc prototype, callback có thể chỉ chạy khi bean thực sự được yêu cầu.

Ví dụ prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class TemporaryReport {

    @PostConstruct
    void prepare() {
        System.out.println("Prepare a new report instance");
    }
}
~~~

Mỗi lần Spring phân giải `TemporaryReport` và tạo instance mới, callback được gọi cho instance đó. Nếu một singleton inject trực tiếp prototype, prototype chỉ được tạo trong lần singleton được khởi tạo; callback không tự chạy lại mỗi lần gọi phương thức trên singleton.

## 8. Điều gì xảy ra nếu @PostConstruct ném exception?

Callback là một phần của quá trình khởi tạo bean. Nếu nó ném exception không được xử lý, Spring xem quá trình khởi tạo bean thất bại. Với một singleton eager được tạo trong lúc khởi động, lỗi đó thường làm quá trình tạo application context thất bại và ứng dụng không thể khởi động hoàn chỉnh.

Ví dụ:

~~~java
@Component
class RequiredConfiguration {

    @PostConstruct
    void validate() {
        if (!configurationIsValid()) {
            throw new IllegalStateException(
                    "Required configuration is invalid");
        }
    }

    private boolean configurationIsValid() {
        return false;
    }
}
~~~

Đây là cách hữu ích để fail-fast khi một bất biến bắt buộc không được đáp ứng. Tuy nhiên, cần phân biệt lỗi cấu hình thật với lỗi dịch vụ ngoài tạm thời.

Một số lưu ý:

- Nếu callback thực hiện kết nối mạng, phụ thuộc DNS hoặc dịch vụ bên ngoài, ứng dụng có thể không khởi động khi hệ thống đó tạm thời unavailable.
- Nếu callback nạp lượng dữ liệu rất lớn, thời gian khởi động có thể tăng đáng kể.
- Nếu callback chạy trên prototype, exception làm lần tạo instance đó thất bại; không có nghĩa mọi bean prototype khác đều không thể tạo.
- Không nên nuốt exception rồi để bean ở trạng thái nửa khởi tạo nếu những phương thức sau đó giả định dữ liệu đã sẵn sàng.

## 9. @PostConstruct và Spring AOP/proxy

Một điểm tinh tế: callback `@PostConstruct` thường được gọi trong giai đoạn BeanPostProcessor **trước khi bean được bọc bởi proxy ở giai đoạn sau khởi tạo**. Vì vậy, không nên gọi một method của chính bean trong `@PostConstruct` và kỳ vọng các interceptor AOP như `@Transactional` hoặc `@Async` đã hoạt động như khi gọi qua proxy.

Ví dụ không nên dựa vào:

~~~java
@Service
class AccountService {

    @PostConstruct
    void initialize() {
        refreshAccounts();
    }

    @Transactional
    public void refreshAccounts() {
        // Cập nhật dữ liệu.
    }
}
~~~

Lời gọi `refreshAccounts()` ở đây là self-invocation trên instance đang khởi tạo; nó không đi qua proxy Spring theo cách một lời gọi từ bean khác đi qua proxy. Vì vậy, transaction annotation trên method không được kích hoạt chỉ nhờ lời gọi này.

Nếu cần thao tác có transaction hoặc AOP, có thể chuyển logic sang một bean khác và gọi bean đó sau khi context sẵn sàng, hoặc dùng một lifecycle event/runner phù hợp:

~~~java
@Component
class StartupTask {
    private final AccountInitializer initializer;

    StartupTask(AccountInitializer initializer) {
        this.initializer = initializer;
    }

    @EventListener(ApplicationReadyEvent.class)
    void afterApplicationReady() {
        initializer.refresh();
    }
}
~~~

~~~java
@Service
class AccountInitializer {
    @Transactional
    public void refresh() {
        // Giao dịch được gọi qua bean proxy khi cấu hình AOP phù hợp.
    }
}
~~~

Đoạn minh họa dùng `ApplicationReadyEvent` để thể hiện một thao tác ở giai đoạn ứng dụng đã sẵn sàng, không phải thay thế bắt buộc cho `@PostConstruct`. Việc gọi qua bean khác giúp lời gọi transaction đi qua proxy của `AccountInitializer`.

## 10. Không dùng @PostConstruct cho mọi công việc lúc khởi động

`@PostConstruct` thích hợp cho **khởi tạo nội bộ của một bean** sau khi dependency được inject. Một số công việc khác nên dùng callback/event chuyên biệt:

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Kiểm tra trạng thái nội bộ sau dependency injection | `@PostConstruct` |
| Cài đặt bước init có tên trên bean factory method | `@Bean(initMethod = "...")` |
| Tham gia lifecycle interface của Spring | `InitializingBean` |
| Chạy logic sau khi context đã refresh | `ContextRefreshedEvent` |
| Chạy logic sau khi ứng dụng Boot sẵn sàng | `ApplicationReadyEvent` |
| Chạy tác vụ khởi động có thứ tự/argument theo Boot | `ApplicationRunner` hoặc `CommandLineRunner` |

Không phải tất cả callback/event có cùng thời điểm. Ví dụ, `@PostConstruct` chạy khi **từng bean** khởi tạo; `ApplicationReadyEvent` được phát ra sau khi ứng dụng Boot hoàn thành trình tự khởi động và sẵn sàng phục vụ. Chọn đúng điểm lifecycle để tránh phụ thuộc vào những bean khác chưa sẵn sàng.

### Phân biệt @PostConstruct với ApplicationRunner

~~~java
@Component
class ReferenceDataInitializer implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Công việc khởi động ở mức ứng dụng.
    }
}
~~~

`ApplicationRunner` phù hợp với logic cần thực hiện khi ứng dụng Boot đã xây dựng context. Nó không thay cho việc thiết lập trạng thái đơn giản của một bean. Ngược lại, nếu bean cần dữ liệu nội bộ trước khi được các bean khác sử dụng, `@PostConstruct` có thể là lựa chọn tự nhiên hơn.

## 11. Chuyển namespace khi nâng cấp Spring Boot 2 lên 3

Spring Boot 3 chuyển nền tảng sang Spring Framework 6 và Jakarta EE APIs. Khi nâng cấp, không chỉ `PostConstruct` mà nhiều package Java EE/Jakarta khác cũng thay đổi:

| API thường gặp | Spring Boot 2 / Spring 5 | Spring Boot 3 / Spring 6 |
|---|---|---|
| Post construct | `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` |
| Pre destroy | `javax.annotation.PreDestroy` | `jakarta.annotation.PreDestroy` |
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Persistence | `javax.persistence.*` | `jakarta.persistence.*` |
| Validation | `javax.validation.*` | `jakarta.validation.*` |

Không phải mọi package bắt đầu bằng `javax` đều đổi thành `jakarta`. Ví dụ `javax.sql`, `javax.crypto` và `javax.net` là các API Java SE vẫn tồn tại trong JDK. Chỉ chuyển những API thuộc hệ Java EE/Jakarta tương ứng theo hướng dẫn migration của framework và thư viện.

### 11.1. Thay import trong source code

Boot 2:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
~~~

Boot 3:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

Đổi import là bước cần thiết nhưng chưa đủ nếu dự án còn dependency cũ hoặc thư viện bên thứ ba vẫn sử dụng API Java EE cũ.

### 11.2. Cập nhật dependency

Loại bỏ dependency API cũ nếu không còn thư viện nào cần nó; thêm API Jakarta phù hợp khi classpath chưa có. Kiểm tra cả dependency trực tiếp và transitive để tránh giữ đồng thời hai namespace chỉ vì một module cũ chưa được nâng cấp.

### 11.3. Nâng cấp thư viện tích hợp

Một thư viện compiled against `javax.annotation.PostConstruct` không tự trở nên tương thích với Spring Framework 6 chỉ vì ứng dụng thêm `jakarta.annotation-api`. Thư viện đó cần phiên bản hỗ trợ Jakarta hoặc cần được thay thế/nâng cấp. Hai annotation là hai kiểu khác nhau.

### 11.4. Kiểm tra runtime

Sau migration:

- Kiểm tra import và dependency tree.
- Khởi động context để chắc chắn lifecycle processor tìm thấy annotation.
- Kiểm tra callback có chạy đúng một lần cho singleton instance dự kiến.
- Kiểm tra callback trên prototype nếu dự án dùng prototype.
- Xem log khởi động và lỗi class loading, đặc biệt `ClassNotFoundException` hoặc `NoClassDefFoundError` liên quan namespace.

## 12. Kiểm thử callback @PostConstruct

Có thể kiểm tra callback bằng một bean có trạng thái được khởi tạo:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
class StartupState {
    private boolean initialized;

    @PostConstruct
    void initialize() {
        initialized = true;
    }

    boolean isInitialized() {
        return initialized;
    }
}
~~~

Một Spring context test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class StartupStateTest {

    @Autowired
    StartupState startupState;

    @Test
    void postConstructRunsBeforeBeanIsUsed() {
        assertThat(startupState.isInitialized()).isTrue();
    }
}
~~~

Test này giả định dự án Boot 3 có Jakarta Annotation API trên classpath. Nếu chạy với Boot 2, đổi import thành `javax.annotation.PostConstruct` và dùng dependency API tương ứng khi cần.

Đối với kiểm thử unit thuần không khởi tạo Spring context, annotation không tự chạy:

~~~java
StartupState state = new StartupState();
~~~

Lệnh `new StartupState()` chỉ gọi constructor Java. Nó không đi qua Spring BeanPostProcessor, nên `@PostConstruct` không được thực thi. Nếu cần kiểm thử callback, hãy khởi tạo bean qua Spring context hoặc gọi logic khởi tạo qua một API tách biệt có thể kiểm thử trực tiếp.

## 13. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `package jakarta.annotation does not exist` | Chưa có Jakarta Annotation API trên compile classpath | Kiểm tra dependency `jakarta.annotation-api` và dependency management |
| `package javax.annotation does not exist` | Dự án Boot 2 trên JDK không còn cung cấp API cũ, hoặc thiếu dependency | Kiểm tra `javax.annotation-api` trong runtime/compile classpath |
| Import biên dịch được nhưng callback không chạy | Dùng sai namespace so với Spring Framework, object không do Spring quản lý, hoặc annotation processor không được đăng ký | Kiểm tra Boot/Spring version, bean registration và context configuration |
| Callback chạy nhưng dependency là null | Object được tạo bằng `new`, field injection chưa diễn ra, hoặc dependency không được inject đúng | Đảm bảo object được tạo qua container và dùng constructor injection |
| Context không khởi động | Callback ném exception hoặc thao tác init thất bại | Đọc nguyên nhân gốc trong log và kiểm tra điều kiện khởi tạo |
| Transaction không có hiệu lực trong callback | Gọi method transactional trên cùng object trước khi AOP proxy sẵn sàng | Chuyển thao tác sang bean khác hoặc lifecycle phù hợp |
| `ClassNotFoundException` với javax/jakarta | Thư viện và ứng dụng đang dùng namespace không tương thích | Đồng bộ phiên bản framework, API và thư viện tích hợp |

Một lỗi thường gặp khi nâng cấp là đổi dependency sang Jakarta nhưng quên đổi import, hoặc đổi import nhưng vẫn kéo một thư viện cũ phụ thuộc namespace `javax`. Hãy xem classpath thực tế thay vì chỉ nhìn file build.

## 14. Nguyên tắc sử dụng @PostConstruct trong ứng dụng Spring Boot

1. Dùng callback cho việc **chuẩn bị trạng thái của chính bean** sau khi dependency đã được inject.
2. Chọn import theo nền tảng: `javax.annotation.PostConstruct` cho Boot 2/Spring 5; `jakarta.annotation.PostConstruct` cho Boot 3/Spring 6.
3. Với JDK 11 trở lên, không giả định API annotation cũ còn nằm trong JDK; kiểm tra và khai báo dependency phù hợp.
4. Giữ method callback đơn giản, không tham số, không static và trả về void.
5. Tránh gọi method của cùng bean cần AOP như `@Transactional` từ callback trước khi proxy sẵn sàng.
6. Không thực hiện công việc khởi động quá nặng hoặc phụ thuộc không kiểm soát vào dịch vụ ngoài; chọn event/runner nếu logic thuộc giai đoạn ứng dụng sẵn sàng.
7. Kiểm thử bằng Spring context nếu muốn xác nhận lifecycle processor thực sự gọi callback.

`@PostConstruct` là một điểm móc nhỏ nhưng quan trọng trong vòng đời bean: nó chạy sau khi Spring thiết lập dependency và trước khi bean được sử dụng bình thường. Khi nâng cấp giữa Spring Boot 2 và 3, hãy đặc biệt chú ý việc chuyển namespace từ `javax.annotation` sang `jakarta.annotation`, vì hai annotation cùng tên không phải cùng một kiểu. Chọn đúng API, dependency và thời điểm lifecycle giúp callback hoạt động dự đoán được trên từng dòng phiên bản.
