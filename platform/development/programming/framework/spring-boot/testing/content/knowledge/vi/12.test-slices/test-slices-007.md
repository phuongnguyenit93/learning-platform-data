# Include filter, exclude filter và phạm vi quét thành phần

## 1. Bài học giải quyết vấn đề gì?

**Test slice** trong Spring Boot là kiểu kiểm thử chỉ nạp một phần application context và một tập auto-configuration phù hợp với lớp kiến trúc đang cần thử. Ví dụ, `@WebMvcTest` tập trung vào Spring MVC; `@DataJpaTest` tập trung vào Spring Data JPA, entity và repository. Khác với `@SpringBootTest`, slice cố ý **không nạp toàn bộ bean của ứng dụng**.

Nhưng có những lúc phạm vi mặc định quá hẹp hoặc quá rộng cho một test cụ thể:

- MVC slice cần **một** bộ chuyển đổi nghiệp vụ nhẹ là `@Service` để controller chạy, nhưng không muốn nạp tất cả service.
- Một servlet `Filter` tự định nghĩa nằm trong tập thành phần MVC có thể được quét mặc định, nhưng test hiện tại chỉ muốn tập trung vào JSON serialization nên cần loại filter đó khỏi **phần được component scan phát hiện**.
- Một test cần giới hạn controller vào đúng `OrderController` thay vì mọi controller trong module.
- Một slice bất ngờ nạp database, scheduler hoặc cấu hình external client vì ứng dụng khai báo `@ComponentScan` riêng trên class `@SpringBootApplication`.
- Developer thêm `includeFilters` mà bean vẫn không có, do nó không thuộc base package đang quét hoặc được tạo bởi cơ chế khác chứ không phải component scanning.

Các công cụ chính:

- `includeFilters` — mở rộng tập **candidate component** được cho phép qua scan của slice.
- `excludeFilters` — loại một số candidate khỏi scan của slice.
- `useDefaultFilters` — bật/tắt các quy tắc nhận diện thành phần mặc định của slice.
- `controllers` / `value` trên `@WebMvcTest` — giới hạn những controller mà test hướng đến.
- `@Import`, `@TestConfiguration`, `@MockitoBean` — cách bổ sung hoặc thay dependency **không đơn thuần là component-scan filter**.
- `excludeAutoConfiguration` — xử lý lớp auto-configuration, **khác** với exclude bean theo type.

**Kết quả mong đợi:** biết chọn bộ lọc đúng, hiểu cơ chế quét, tránh biến slice thành full context ngoài ý muốn, và kiểm tra phạm vi bean bằng assertion cụ thể thay vì nhìn tên annotation rồi đoán.

Phạm vi bài: Java 17+, Spring Boot 3.x cho ví dụ chạy được; giải thích những điểm khác với Spring Boot 4.x và các rủi ro dùng cùng cú pháp trong loại slice khác.

## 2. Trước hết phải phân biệt bốn cơ chế nạp bean

Một class xuất hiện trong Spring context không nhất thiết do component scan. Nếu không phân biệt nguồn bean, `includeFilters`/`excludeFilters` rất dễ bị dùng sai.

| Nguồn tạo bean | Ví dụ | Có phải candidate từ component scan? |
|---|---|---|
| Quét stereotype | `@Component`, `@Service`, `@Repository`, `@Controller` | Có, khi package và bộ lọc cho phép |
| Định nghĩa từ configuration | `@Bean` trong `@Configuration` đã được nạp | Bản thân method `@Bean` không được lọc trực tiếp như class candidate |
| Import cấu hình/class | `@Import(MyConfig.class)`, test configuration | Không phụ thuộc việc `MyConfig` được tự phát hiện qua scan |
| Auto-configuration / registrar | Bean do Spring Boot auto-config hoặc Spring Data repository registrar tạo | Không được điều khiển trọn vẹn chỉ bằng scan filter |

Ví dụ, một `@Service` ở đúng package có thể bị MVC slice loại khỏi tập candidate dù nó hợp lệ trong production. Bạn dùng `includeFilters` để đưa riêng class đó vào **quá trình quét**. Nhưng nếu một bean `DataSource` được tạo bởi auto-configuration, việc viết `excludeFilters = ...DataSource.class` **không phải** biện pháp đúng để tắt JDBC auto-configuration.

**Nguyên tắc:** trước khi đổi filter, trả lời *bean này đến từ component scan, @Import/@Bean, hay auto-configuration?* và *mục tiêu test có thực sự cần bean đó không?*

## 3. Test slice hoạt động như thế nào?

### 3.1. Full context và slice khác nhau từ bước bootstrap

Với một ứng dụng Spring Boot có controller, service, repository và web dependencies:

```text
@SpringBootTest
    └─ Primary application configuration
       ├─ Controller
       ├─ Service
       ├─ Repository
       ├─ @Configuration/@Bean
       └─ Auto-configuration tương ứng classpath/properties

@WebMvcTest(controllers = OrderController.class)
    └─ Test MVC slice
       ├─ OrderController + MVC infrastructure
       ├─ ControllerAdvice/Converter/Filter... phù hợp scope
       ├─ MockMvc
       ├─ Dependency được import/mock/include có chủ đích
       └─ Không mặc định quét mọi @Service/@Repository

@DataJpaTest
    └─ Test JPA slice
       ├─ Entities và Spring Data repositories theo cơ chế liên quan
       ├─ EntityManager/transaction/JDBC-JPA infrastructure
       └─ Không mặc định quét controller và service ứng dụng
```

Đây là **sơ đồ khái niệm**, không phải danh sách toàn bộ auto-configuration hay lời bảo đảm mọi dự án nạp chính xác những bean đó. Chi tiết phụ thuộc dependency, config, profile và phiên bản Spring Boot.

Tại sao slice thường chạy nhanh hơn? Nó nạp ít bean và ít hạ tầng hơn, nên giảm thời gian startup và điểm thất bại không thuộc lớp đang được thử. Nhưng **ít bean hơn không đồng nghĩa kiểm thử mạnh hơn trong mọi tình huống**: khi cần xác minh toàn bộ dây chuyền MVC → service → repository, full-context integration test có giá trị riêng.

### 3.2. `@WebMvcTest` mặc định nhận những gì?

Theo Javadoc của Spring Boot 3.x/4.x, MVC slice nhận các controller và một số thành phần MVC liên quan. Ngoài `@Controller`/`@ControllerAdvice`, còn có các loại như `@JsonComponent`, `Converter`, `GenericConverter`, `Filter`, `HandlerInterceptor`, `HandlerMethodArgumentResolver`, `HttpMessageConverter`, `SecurityFilterChain`, `WebMvcConfigurer` và những kiểu được tài liệu của phiên bản cụ thể liệt kê.

Vì vậy hai suy nghĩ này đều sai:

- “`@WebMvcTest` chỉ có đúng một controller, không thể có filter hay advice.” Sai; nhiều thành phần hỗ trợ MVC vẫn thuộc phạm vi.
- “Controller phụ thuộc `@Service` thì `@WebMvcTest` tự quét service ấy.” Sai; `@Service` thông thường bị giới hạn khỏi component scan của MVC slice, trừ khi được bổ sung có chủ đích.

Một test MVC slice thường dùng `@MockitoBean`/mock service hoặc `@Import` cấu hình nhỏ. `includeFilters` là lựa chọn khi bạn **chủ động muốn đưa một class từ scan vào context**, không phải mặc định phải dùng cho mọi dependency.

### 3.3. `@DataJpaTest` có cùng cơ chế scan không?

`@DataJpaTest` cũng có `includeFilters`, `excludeFilters` và `useDefaultFilters`, nhưng **tập mặc định khác hoàn toàn**. Nó tập trung vào thực thể JPA, Spring Data repositories và auto-configuration JPA/transaction/database. Entities/repositories được tìm bởi các cơ chế chuyên biệt như entity scanning và Spring Data repository registration.

Do đó không được suy luận:

> “Nếu include một `@Service` trong `@DataJpaTest`, JPA slice sẽ biến thành `@SpringBootTest`.”

Nó chỉ bổ sung candidate theo cơ chế filter; không tự nạp mọi collaborator, không bật mọi auto-configuration khác và không giải quyết kết nối database nếu hạ tầng JPA thiếu. Trong nhiều tình huống, một `@Import` rõ ràng cho service thuần Java sẽ dễ hiểu hơn.

## 4. Cú pháp filter trên test-slice annotation

### 4.1. Cấu trúc `ComponentScan.Filter`

Spring Boot cho phép dùng đối tượng annotation `@ComponentScan.Filter` trong thuộc tính của nhiều test slice:

```java
@WebMvcTest(
    controllers = OrderController.class,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = OrderFormatter.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = RequestAuditFilter.class
    )
)
class OrderControllerWebSliceTest {
}
```

**Đây là minh họa cú pháp**, giả định các class đã tồn tại; chưa phải một test chạy độc lập. Ý nghĩa của ba phần:

1. `controllers = OrderController.class` giới hạn controller được chọn.
2. `includeFilters` chủ động mở đường cho `OrderFormatter` (khi nó là component được scan ở package hợp lệ).
3. `excludeFilters` loại `RequestAuditFilter` khỏi quá trình component scan tương ứng, kể cả khi nó thuộc tập MVC component được phép mặc định.

Để dùng cú pháp trên, imports thường gồm:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
```

Package `WebMvcTest` nêu ở đây dành cho **Spring Boot 3.x**. Mục 11 sẽ nói tới Boot 4.

### 4.2. Các `FilterType` phổ biến

| `FilterType` | Tiêu chí khớp | Khi nên dùng |
|---|---|---|
| `ASSIGNABLE_TYPE` | Một class/interface cụ thể hoặc class con/implementation phù hợp | Muốn include/exclude kiểu cụ thể hoặc nhóm implementation |
| `ANNOTATION` | Một annotation hiện diện trực tiếp hoặc qua meta-annotation theo quy tắc Spring | Nhóm thành phần đánh dấu bởi annotation riêng |
| `REGEX` | Biểu thức chính quy khớp tên lớp đầy đủ | Chọn nhóm type theo tên/package, nên dùng thận trọng |
| `ASPECTJ` | Biểu thức type pattern AspectJ | Hệ thống có quy tắc phân loại theo type pattern |
| `CUSTOM` | Class triển khai `TypeFilter` tùy biến | Quy tắc metadata phức tạp, không giải quyết được bằng loại trước |

Mặc định của `@ComponentScan.Filter` thường là `FilterType.ANNOTATION`; nếu truyền `classes = SomeClass.class` mà quên `type = ASSIGNABLE_TYPE`, bạn có thể gặp cấu hình sai vì class đó không phải annotation.

**Ưu tiên type-safe:** `ASSIGNABLE_TYPE` với `classes = X.class` dễ refactor và dễ đọc hơn một biểu thức regex chứa tên package bằng string. Regex vẫn hữu ích khi cần nhiều class theo tên nhưng dễ vô tình bắt nhầm class khác.

### 4.3. Filter theo annotation

Giả sử dự án có annotation `@SliceHelper` áp lên một số class hỗ trợ web:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface SliceHelper {
}
```

Với imports `java.lang.annotation.ElementType`, `Retention`, `RetentionPolicy` và `Target`; đây chỉ là **định nghĩa annotation minh họa**, không phải source file riêng của ví dụ runnable ở phần 7.

Test có thể include các class phù hợp:

```java
includeFilters = @ComponentScan.Filter(
    type = FilterType.ANNOTATION,
    classes = SliceHelper.class
)
```

Đây là **thuộc tính annotation**, không phải câu lệnh Java độc lập. Một class mang `@SliceHelper` vẫn phải ở vùng quét thích hợp và là candidate có thể đăng ký; annotation marker tự nó không biến mọi POJO bên ngoài scope thành Spring bean.

### 4.4. Filter theo regex

```java
excludeFilters = @ComponentScan.Filter(
    type = FilterType.REGEX,
    pattern = "com\\.example\\.api\\.internal\\..*"
)
```

**Đoạn minh họa** cho một cấu trúc package giả định. Matcher regex xét **tên class**, không phải bean name hay request path. Nếu đổi package, regex có thể sai; nếu dùng pattern quá rộng, bạn có thể loại luôn component cần test.

Đừng dùng regex để “loại mọi service trong package” nếu slice vốn đã loại chúng; điều đó làm test khó đọc mà không tăng độ rõ ràng.

### 4.5. Include, exclude và mặc định có thể tương tác

Cần hiểu ba tập:

- **Default includes của slice**: những loại bean mà slice vốn cho phép.
- **Custom includes**: những candidate muốn cho phép thêm.
- **Custom excludes**: những candidate phải loại khỏi quá trình quét áp dụng filter.

Một rule exclude cụ thể có thể loại một candidate dù candidate đó thuộc tập mặc định hoặc custom include. Tuy nhiên, đây là cách hình dung **ở tầng component scan**; bean được đăng ký qua `@Import`, `@Bean` hoặc auto-configuration có thể vẫn hiện diện.

## 5. `controllers` và `useDefaultFilters`: kiểm soát phạm vi mặc định

### 5.1. `controllers` chọn controller, không biến cả context thành một class

```java
@WebMvcTest(controllers = ProductController.class)
class ProductControllerWebTest {
}
```

Khi các class và dependency hợp lệ, MVC slice nhắm tới controller được chỉ định, chứ không quét tất cả controller như khi để trống `controllers`. Nhưng context vẫn có thể chứa `ControllerAdvice`, converters, filters, MVC config, validation và security infrastructure được slice cho phép.

Vì thế một test có thể nhận HTTP 403 dù chỉ chọn một controller, bởi Spring Security filter chain vẫn thuộc phạm vi test. Không nên kết luận filter “bị quét nhầm” chỉ dựa trên 403: đó có thể là cấu hình đúng mà test chưa cung cấp authenticated user/CSRF token.

### 5.2. `useDefaultFilters = true` là mặc định

Trong nhiều slice annotation, `useDefaultFilters` mặc định là `true`, nhưng **“default” là tập phù hợp từng slice**, không phải toàn bộ `@Component` trong ứng dụng.

- Trên `@WebMvcTest`, mặc định cho phép các loại thành phần MVC.
- Trên `@DataJpaTest`, component scan thông thường bị giới hạn mạnh; entities/repositories theo cơ chế chuyên biệt của JPA.
- Hai annotation có cùng tên attribute nhưng **không đồng nghĩa cùng tập bean mặc định**.

### 5.3. `useDefaultFilters = false` chỉ dành cho trường hợp kiểm soát chặt

Ví dụ minh họa ý định:

```java
@WebMvcTest(
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductController.class
    )
)
class NarrowWebTest {
}
```

Đây là **snippet cấu hình**, không phải bài test chạy độc lập. Nó chủ động tắt cách chọn candidate mặc định rồi include component cụ thể; kết quả còn phụ thuộc bootstrapper, auto-configuration và các dependency của controller. Một số cấu hình MVC mà bạn cần có thể không còn được quét, vì vậy cần kiểm tra context thực tế.

**Chọn đúng công cụ:** nếu chỉ muốn test một controller, `controllers = ProductController.class` thường rõ ràng hơn; không phải tắt hết defaults rồi thêm chúng lại. Tắt default filters là trường hợp đặc biệt khi cần kiểm soát chi tiết một tập scan ít gặp.

### 5.4. Một controller với dependency bắt buộc

Giả sử `OrderController` cần `OrderService` ở constructor. `@WebMvcTest(OrderController.class)` không mặc định quét service thông thường, nên test có thể báo `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException`.

Có ba lựa chọn khác nhau:

1. **Mock dependency:** `@MockitoBean OrderService service` (trên Spring Framework 6.2+/Boot phù hợp) — phù hợp khi chỉ test HTTP contract/controller.
2. **Import bean/cấu hình:** `@Import(OrderService.class)` khi muốn chạy logic thật của một class có ít phụ thuộc.
3. **Include qua component scan:** `includeFilters = @Filter(type = ASSIGNABLE_TYPE, classes = OrderService.class)` khi class ấy thuộc vùng scan và bạn cố ý muốn kiểm chứng scan.

Cách thứ ba là trọng tâm bài học. Nhưng nếu mục tiêu là kiểm tra kết nối controller → service → repository thật với nhiều bean, có thể cân nhắc `@SpringBootTest + @AutoConfigureMockMvc` thay vì tiếp tục mở rộng slice đến gần full context.

## 6. Thí nghiệm thiết kế: một service được include, một filter bị exclude

Ta xây ứng dụng Spring MVC rất nhỏ với các component:

- `EchoController` nhận GET `/api/echo/{word}` và gọi `FormatterService`.
- `FormatterService` được đánh dấu `@Service`; trong MVC slice bình thường không có, nhưng **sẽ xuất hiện nhờ include filter**.
- `AuditHeaderFilter` được đánh dấu `@Component` và implement servlet `Filter`; về loại thành phần nó được MVC slice xét, nhưng **bị exclude filter loại**.
- `AdminController` là một controller khác, cố tình **không nằm trong `controllers`** của test.
- `BillingService` là một service khác, không có custom include, nên **không được scan**.

Mục tiêu của test không chỉ là context load thành công. Ta sẽ chứng minh:

1. `FormatterService` thực sự nằm trong context và logic thật chạy.
2. `AuditHeaderFilter` không phải bean trong slice này.
3. `AdminController` và `BillingService` không bị kéo vào slice.
4. Request tới EchoController trả JSON đúng và không có header do filter bị loại.
5. Request tới endpoint của AdminController không được map trong slice.

**Điều kiện:** ví dụ được thiết kế cho **Spring Boot 3.x, Java 17+ và JUnit Jupiter**. Tất cả Java production classes nằm trong một package để tránh vấn đề scan location. Không có Spring Security, JPA, database, Testcontainers hoặc external services trong ví dụ cơ bản.

## 7. Ví dụ Java 17+ chạy được với Spring Boot 3.x

### 7.1. Dependencies

Trong dự án Gradle Groovy DSL đã cấu hình Spring Boot plugin/BOM, repositories và Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Nếu dùng Maven với Spring Boot parent/BOM và plugin test phù hợp, dependencies tương ứng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **đoạn trích từ build file**, không phải file build hoàn chỉnh. Spring MVC và JSON converter đến từ web starter; JUnit Jupiter, AssertJ và Spring Test/MockMvc đến từ starter test. Không thêm Security vào mẫu này, vì security filters sẽ thay đổi HTTP status nếu không thiết lập test user/CSRF.

### 7.2. Cây file

```text
src/
├── main/java/com/example/slicefilters/
│   ├── SliceFiltersApplication.java
│   ├── EchoController.java
│   ├── FormatterService.java
│   ├── AuditHeaderFilter.java
│   ├── AdminController.java
│   └── BillingService.java
└── test/java/com/example/slicefilters/
    └── EchoWebMvcSliceTest.java
```

Đặt đúng package `com.example.slicefilters` ở đầu các class. Class `@SpringBootApplication` đặt trong package đó nên component scan mặc định bao trùm các class còn lại.

### 7.3. Application class

**File `src/main/java/com/example/slicefilters/SliceFiltersApplication.java`:**

```java
package com.example.slicefilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceFiltersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceFiltersApplication.class, args);
    }
}
```

**Cố tình không thêm `@ComponentScan` trực tiếp** vào class này. Spring Boot cung cấp default scan cùng cơ chế `TypeExcludeFilter` để test slicing vẫn hoạt động.

### 7.4. Service cần include vào MVC slice

**File `src/main/java/com/example/slicefilters/FormatterService.java`:**

```java
package com.example.slicefilters;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class FormatterService {
    public String normalize(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }
}
```

Dù có `@Service` và được scan trong application thật, trong `@WebMvcTest` mặc định service không thuộc tập MVC component được chọn. Vì vậy test sẽ chỉ định `includeFilters` theo kiểu `ASSIGNABLE_TYPE` để đưa riêng class này vào.

### 7.5. Controller đang được thử

**File `src/main/java/com/example/slicefilters/EchoController.java`:**

```java
package com.example.slicefilters;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {
    private final FormatterService formatter;

    public EchoController(FormatterService formatter) {
        this.formatter = formatter;
    }

    @GetMapping("/api/echo/{word}")
    public Map<String, String> echo(@PathVariable String word) {
        return Map.of("value", formatter.normalize(word));
    }
}
```

Controller cần service qua constructor. Điều này tạo ra một test có ý nghĩa: nếu include filter không làm việc, context sẽ khó khởi tạo vì thiếu `FormatterService`. Khi filter hoạt động, một request GET sẽ kiểm tra logic normalize thật và JSON serialization.

### 7.6. Servlet Filter muốn loại khỏi slice

**File `src/main/java/com/example/slicefilters/AuditHeaderFilter.java`:**

```java
package com.example.slicefilters;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class AuditHeaderFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        response.setHeader("X-Audit", "enabled");
        filterChain.doFilter(request, response);
    }
}
```

Class này là một `@Component` thuộc nhóm Servlet `Filter`. Trong test không exclude nó, filter có thể được đưa vào MockMvc và thêm `X-Audit: enabled`. Nhưng bài học có yêu cầu cụ thể **loại một component đang thuộc tập MVC scan**, nên test áp dụng `excludeFilters` cho class này.

Đừng xem filter là “xấu” trong production. Nó chỉ nằm **ngoài phạm vi** của test riêng này. Nếu hệ thống có yêu cầu audit/security thật, cần test bổ sung nơi filter được bật, không loại nó khỏi mọi bài test.

### 7.7. Hai component không thuộc phạm vi test

**File `src/main/java/com/example/slicefilters/AdminController.java`:**

```java
package com.example.slicefilters;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminController {

    @GetMapping("/api/admin/ping")
    public Map<String, String> ping() {
        return Map.of("status", "UP");
    }
}
```

**File `src/main/java/com/example/slicefilters/BillingService.java`:**

```java
package com.example.slicefilters;

import org.springframework.stereotype.Service;

@Service
public class BillingService {
    public int calculateFee() {
        return 100;
    }
}
```

`AdminController` không được chọn trong `controllers = EchoController.class`. `BillingService` không được đưa vào `includeFilters`, và `@Service` là loại bị MVC slice giới hạn mặc định. Cả hai phục vụ **assertion về phạm vi**, không phải dependency mà EchoController cần.

### 7.8. Lớp test có include và exclude filter

**File `src/test/java/com/example/slicefilters/EchoWebMvcSliceTest.java`:**

```java
package com.example.slicefilters;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(
    controllers = EchoController.class,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = FormatterService.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = AuditHeaderFilter.class
    )
)
@AutoConfigureMockMvc(addFilters = true)
class EchoWebMvcSliceTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    FormatterService formatter;

    @Autowired
    MockMvc mvc;

    @Test
    void includesTheSelectedServiceFromComponentScan() {
        assertThat(context.getBeanNamesForType(FormatterService.class))
                .hasSize(1);
        assertThat(context.getBeanNamesForType(EchoController.class))
                .hasSize(1);
        assertThat(formatter.normalize("  book  "))
                .isEqualTo("BOOK");
    }

    @Test
    void excludesServletFilterFromComponentScan() {
        assertThat(context.getBeanNamesForType(AuditHeaderFilter.class))
                .isEmpty();
    }

    @Test
    void doesNotScanUnselectedControllerOrService() {
        assertThat(context.getBeanNamesForType(AdminController.class))
                .isEmpty();
        assertThat(context.getBeanNamesForType(BillingService.class))
                .isEmpty();
    }

    @Test
    void mvcRequestUsesIncludedServiceWithoutExcludedFilter()
            throws Exception {
        mvc.perform(get("/api/echo/hello")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.value").value("HELLO"))
                .andExpect(header().doesNotExist("X-Audit"));
    }

    @Test
    void unselectedAdminEndpointIsNotMapped()
            throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isNotFound());
    }
}
```

**Kỳ vọng:** **5 phương thức `@Test`** chạy thành công trên một project Spring Boot 3.x sạch với dependencies trên, Java 17+ và JUnit Jupiter. Test không tự in stdout; Gradle/Maven/IDE hiển thị summary theo phiên bản và cấu hình của chúng. `@AutoConfigureMockMvc(addFilters = true)` ở đây **cố ý giữ default filter registration** — bằng cách ấy, test không “giấu” AuditHeaderFilter nhờ tắt tất cả filters; thay vào đó ta chứng minh filter cụ thể thật sự đã bị loại khỏi component scan.

### 7.9. Cách chạy

Linux/macOS:

```bash
# Nếu dự án dùng Gradle Wrapper:
./gradlew test --tests "com.example.slicefilters.EchoWebMvcSliceTest"

# Nếu dự án dùng Maven Wrapper/Surefire:
./mvnw -Dtest=EchoWebMvcSliceTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.slicefilters.EchoWebMvcSliceTest"

# Hoặc Maven:
.\mvnw.cmd "-Dtest=EchoWebMvcSliceTest" test
```

Chọn lệnh tương ứng build tool; không mặc định dự án có cả hai wrapper. Khi chạy multi-module, cần chỉ rõ module chứa test. Không cần `java -jar` hoặc HTTP server để chạy `MockMvc`: test gửi request trong JVM.

### 7.10. Đọc kết quả thực nghiệm

| Phép kiểm tra | Quan sát cần có | Chứng minh |
|---|---|---|
| Lấy `FormatterService` từ context | Có đúng một bean | Custom include filter đã đưa bean vào slice |
| `formatter.normalize("  book  ")` | `BOOK` | Đây là logic service thật, không phải Mockito stub |
| Tìm `AuditHeaderFilter` | Không có bean | Custom exclude filter đã loại component |
| Tìm `AdminController` | Không có bean | `controllers = EchoController.class` giới hạn controller |
| Tìm `BillingService` | Không có bean | MVC slice không tự nạp mọi service |
| GET `/api/echo/hello` | 200, JSON có `"value":"HELLO"`, không có `X-Audit` | Request đi qua controller và service đã include, filter đã exclude |
| GET `/api/admin/ping` | 404 | Controller không thuộc slice, endpoint không được map |

**Hãy suy luận từ assertion, không chỉ từ số test pass.** Nếu xóa `includeFilters`, test có thể fail ngay từ bootstrap vì thiếu service; nếu xóa `excludeFilters`, AuditHeaderFilter có thể xuất hiện và thêm header. Đó là kiểm chứng ý nghĩa thực tế của hai filter, không phải chỉ kiểm tra cú pháp.

## 8. Khi nào nên dùng filter, khi nào nên dùng cách khác?

### 8.1. `includeFilters` phù hợp khi nào?

Dùng nó khi:

- Component cần thêm đang là class có stereotype/interface phù hợp, nằm trong vùng component scan của test.
- Bạn muốn kiểm thử **chính cấu hình quét** và bean thật của class.
- Component nhỏ, ít collaborator; thêm nó không kéo cả graph phụ thuộc vào slice.
- Có annotation marker hoặc interface chung đại diện cho nhóm component bổ trợ web.

Không dùng như “cơ chế sửa mọi missing bean” nếu dependency thật là database client, Kafka consumer, scheduler hoặc service tích hợp phức tạp. Khi đó cấu trúc test cần được xác định lại.

### 8.2. `@Import` thích hợp hơn khi nào?

Giả sử controller cần một formatter thuần Java, không muốn phụ thuộc package scanning:

```java
@WebMvcTest(controllers = EchoController.class)
@Import(FormatterService.class)
class EchoWithImportedServiceTest {
}
```

**Đây là cấu hình test minh họa**, không phải test runnable riêng. `@Import` đăng ký class/cấu hình được nêu rõ, **không đòi component phải được phát hiện qua include filter**. Đây thường là cách gọn khi bạn chỉ cần một bean thật trong MVC slice mà không cần kiểm tra cơ chế scan.

Nhưng đừng import nguyên `@Configuration` của một subsystem khi nó kéo theo DB, scheduler, network hoặc nhiều auto-config gián tiếp; như vậy bạn có thể biến một MVC slice nhỏ thành test startup phức tạp không cần thiết.

### 8.3. `@TestConfiguration` thích hợp hơn khi nào?

Khi dependency cần **fake nhỏ trong test**, có thể khai báo class `@TestConfiguration` lồng trong test:

```java
@TestConfiguration(proxyBeanMethods = false)
static class SliceOnlyConfig {

    @Bean
    ExternalQuoteGateway externalQuoteGateway() {
        return sku -> 123L;
    }
}
```

**Snippet minh họa**: `ExternalQuoteGateway` là interface giả định có một abstract method nhận sku và trả long/Long; để chạy cần định nghĩa interface và imports Spring. Test configuration thêm bean có kiểm soát, không cần quét production external client. Nó phục vụ test behavior nhưng **không có nghĩa class `ExternalQuoteGateway` được phát hiện bằng `includeFilters`**.

Điểm quan trọng: nested `@TestConfiguration` thường **bổ sung** vào primary configuration được test bootstrap tìm; nested `@Configuration` thông thường có thể **thay thế** primary configuration trong một số test bootstrap cases. Chọn annotation có chủ đích.

### 8.4. Mock service: ít code và đúng phạm vi

Nếu chỉ kiểm tra HTTP mapping, JSON và validation của controller, mock dependency thường hợp lý:

```java
@WebMvcTest(EchoController.class)
class EchoContractTest {

    @MockitoBean
    FormatterService formatter;
}
```

**Snippet dùng trên Spring Framework 6.2+ với test bean override support**, chẳng hạn nhiều dự án Spring Boot 3.4+/4.x; cần import `org.springframework.test.context.bean.override.mockito.MockitoBean`. Boot 3.3 trở xuống thường dùng `@MockBean` của Spring Boot (những nhánh mới đã deprecate annotation cũ). Không dán `@MockitoBean` vào Boot 3.2 và trông đợi import có sẵn.

Nếu muốn xác nhận cả `FormatterService.normalize(...)` thật được dùng, đừng mock nó. Bài runnable phần 7 cố ý dùng `includeFilters` để kiểm thử đúng mục tiêu quét thành phần.

### 8.5. Khi nên chuyển sang full context?

Nếu test cần cả controller + service + repository + transaction + nhiều config, thay vì include hàng chục class và tự chữa từng `NoSuchBeanDefinitionException`, dùng:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class FullContextApiTest {
}
```

**Snippet minh họa**, không phải một test class đầy đủ. Khác với MVC slice, full application context có thể nạp database hoặc các external integrations; phải có test profile/fixtures và isolation phù hợp. Đó là **đổi phạm vi kiểm thử có chủ đích**, không phải thao tác “fix filter”.

## 9. Phân biệt `excludeFilters` với những dạng exclude khác

Cùng từ “exclude” trong Spring Boot có nhiều tầng ý nghĩa.

| Công cụ | Đối tượng bị loại | Không tự làm được gì |
|---|---|---|
| `excludeFilters` trên slice | Component candidate được scan theo rule | Không chắc loại bean được `@Import` hoặc auto-config register |
| `excludeAutoConfiguration` trên slice | Auto-configuration classes được slice import/apply | Không phải generic filter cho `@Service` |
| `@SpringBootApplication(exclude=...)` | Auto-configuration classes của ứng dụng | Không loại arbitrary controller/service |
| `@ComponentScan(excludeFilters=...)` | Component candidates theo scan đó | Không xóa bean tạo bởi direct `@Bean` registration |
| `@AutoConfigureMockMvc(addFilters=false)` | Không đăng ký các servlet filters từ context vào MockMvc theo cơ chế tương ứng | **Không xóa** bean Filter khỏi application context |
| `@MockitoBean` | Tạo/override bean bằng Mockito mock theo quy tắc test framework | Không phải quy tắc package scan |

Đây là điểm hay bị nhầm nhất với tên **Filter**:

- **Component-scan `excludeFilters`** quyết định **class có được phát hiện/đăng ký thành Spring bean qua scan không**.
- **Servlet `Filter`** là object thực thi trước controller.
- **`@AutoConfigureMockMvc(addFilters=false)`** có thể giữ bean `AuditHeaderFilter` trong context, nhưng bỏ nó khỏi MockMvc filter chain.

Vì vậy nếu test chỉ assert “không có header X-Audit”, chưa đủ chứng minh bean filter bị exclude khỏi scan. Ví dụ phần 7 còn assert `context.getBeanNamesForType(AuditHeaderFilter.class)` rỗng để kiểm tra **đúng ý nghĩa component-scan filter**.

### 9.1. `@ImportAutoConfiguration` khác `@Import`

Spring Boot test slices giới hạn auto-configuration theo tập riêng. Nếu muốn bổ sung một auto-configuration vào slice, Spring Boot hướng dẫn dùng `@ImportAutoConfiguration` hoặc cơ chế tùy biến của slice, không tùy tiện dùng `@Import` như một công cụ tương đương với mọi auto-configuration.

Ngược lại, khi chỉ cần một bean/config thông thường, `@Import` có thể là lựa chọn sáng rõ. Tự động áp một auto-config nhiều dependency vào MVC slice chỉ vì “thiếu bean” có thể vô tình khởi tạo hạ tầng ngoài phạm vi.

## 10. Một bẫy lớn: `@ComponentScan` tường minh làm hỏng slicing

### 10.1. Tại sao một dự án có `@WebMvcTest` nhưng vẫn load mọi service?

Spring Boot mặc định đặt component scan phù hợp trong `@SpringBootApplication` và gắn cơ chế **`TypeExcludeFilter`** để test slice loại các component không thuộc phạm vi.

Nếu bạn thêm trực tiếp một `@ComponentScan` riêng lên main application class:

```java
@SpringBootApplication
@ComponentScan({
    "com.example.application",
    "com.example.shared"
})
public class Application {
}
```

thì bạn có thể **vượt qua cơ chế exclude mặc định được khai báo qua meta-annotation** của `@SpringBootApplication`, khiến scan vẫn kéo vào những thành phần mà slice đang muốn loại. Kết quả thường gặp:

- `@DataJpaTest` đột nhiên nạp service, web config hoặc scheduler.
- `@WebMvcTest` bị kéo vào service/repository graph ngoài dự kiến.
- Test fail ở datasource, remote client hoặc bean không có thuộc phạm vi.
- Thời gian load context tăng mạnh, không còn đặc tính nhẹ của slice.

Spring Boot docs cảnh báo trực tiếp trường hợp này. Đây **không phải** lỗi `includeFilters` quá rộng trong chính test; nguồn vấn đề là **custom scan directive ở ứng dụng chính**.

### 10.2. Cách ưu tiên sửa

Nếu chỉ muốn mở rộng package quét cho **components**, có thể cân nhắc thuộc tính của `@SpringBootApplication`:

```java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.application",
        "com.example.shared"
    }
)
public class Application {
}
```

**Snippet minh họa**, không phải class đầy đủ. Cách dùng alias `scanBasePackages` tránh phải thay bằng một annotation `@ComponentScan` riêng và giữ cơ chế meta-annotation có filter phù hợp với Boot.

Cũng có thể dùng `scanBasePackageClasses = {MarkerInApp.class, MarkerInShared.class}` để lựa chọn package theo kiểu type-safe, tránh lỗi khi refactor tên package. Các marker phải tồn tại.

**Quan trọng:** `scanBasePackages` chỉ điều chỉnh component scanning của application; nó **không tự mở rộng JPA entity scanning hay Spring Data repository scanning**. Nếu cần các cơ chế đó ở package ngoài, xem `@EntityScan`/`@EnableJpaRepositories` và cấu hình theo ứng dụng, không lấy component-scan attribute làm giải pháp chung.

### 10.3. Nếu bắt buộc giữ `@ComponentScan` riêng?

Đặt scan tùy biến vào một `@Configuration` tách riêng, được đưa vào ứng dụng ở vị trí phù hợp, thường tránh làm mất filter mặc định ở main class. Nếu vẫn phải dùng `@ComponentScan` trực tiếp và kỳ vọng slices hoạt động, cần **đăng ký lại `TypeExcludeFilter` đúng cách** theo tài liệu Boot.

Spring Boot có TypeFilter tên `org.springframework.boot.context.TypeExcludeFilter`, dùng trong loại `FilterType.CUSTOM` của `@ComponentScan`. Đừng chép cứng thêm/bỏ class khác từ một ví dụ phiên bản cũ; kiểm tra Javadoc của nhánh Boot đang dùng và test lại phạm vi.

Nếu muốn test độc lập với một main application config phức tạp, cũng có thể chỉ rõ test bootstrap source bằng một class `@SpringBootConfiguration` dành riêng cho ngữ cảnh test phù hợp, thay vì để framework dò ra main class có quá nhiều annotation tích hợp.

### 10.4. `@SpringBootApplication` root package cũng ảnh hưởng scope

Spring Boot tìm primary configuration bằng cách đi ngược từ package của test đến package chứa `@SpringBootApplication` hoặc `@SpringBootConfiguration`. Nếu test đặt ngoài package hierarchy, bạn có thể thấy lỗi không tìm được configuration.

Ngoài ra, một component không nằm trong **base package** có thể **không được xét** ngay cả khi filter theo type đúng. Ví dụ `includeFilters = classes=RemoteFormatter.class` không tự scan package `com.some.other.module` nếu package đó chưa nằm trong vùng component scan của ứng dụng/test.

Giải pháp trong trường hợp này thường là `@Import(RemoteFormatter.class)`, đưa cấu hình scan hợp lệ vào nơi thích hợp hoặc chỉnh root package theo thiết kế. Đừng làm regex phức tạp hơn để giải quyết một vấn đề phạm vi package.

## 11. Khác biệt Spring Boot 3.x và 4.x

Những annotation có thể giữ ý nghĩa gần nhau nhưng **package và starter thay đổi theo major version**.

### 11.1. Boot 3.x

Imports thường gặp:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
```

Dependencies thường dùng: `spring-boot-starter-web`, `spring-boot-starter-test`; thêm `spring-boot-starter-data-jpa` và database khi test JPA.

### 11.2. Boot 4.x

Theo Javadoc Boot 4, package MVC slice được tổ chức lại:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
```

Các starter test được tách chuyên biệt trong hệ thống module, ví dụ `spring-boot-starter-webmvc-test` và `spring-boot-starter-data-jpa-test` trong hệ sinh thái Boot 4. Dự án phải chọn dependency thực sự tương thích BOM/version.

Các attribute `controllers`, `includeFilters`, `excludeFilters`, `useDefaultFilters` vẫn xuất hiện trong Javadoc Boot 4, nhưng tập MVC components/auto-configuration có thể thay đổi; đừng sao chép nguyên danh sách default includes của một major version rồi coi là hợp đồng mãi mãi.

### 11.3. Chú ý JUnit, Java và security

- Boot 3 có Java 17 là baseline phù hợp cho bài; Boot 4 yêu cầu JVM phù hợp theo release notes phiên bản.
- `@WebMvcTest` tích hợp Spring Test/JUnit Jupiter khi dùng dependency đúng; không cần tự thêm `@ExtendWith(SpringExtension.class)` trong ví dụ.
- Nếu Spring Security xuất hiện trên classpath, MVC slice có thể nạp security filters. Một test không authenticated có thể gặp 401/403 trước controller.
- Đừng chữa bằng cách tắt mọi filter nếu test có mục tiêu kiểm tra bảo mật. Dùng test security support, mock user và CSRF theo chính sách của endpoint.

## 12. Lưu ý với những slice khác ngoài MVC

### 12.1. `@DataJpaTest`

Trong JPA slice, Spring Boot hạn chế auto-configuration và nạp các thành phần JPA liên quan. Có thể tùy biến `includeFilters/excludeFilters`, nhưng **entity và repository không phải chỉ do component scan annotation xử lý**.

Ví dụ cấu hình minh họa:

```java
@DataJpaTest(
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = PricingPolicy.class
    )
)
class PricingRepositoryTest {
}
```

Đây là **snippet**, giả định `PricingPolicy` là component trong vùng scan và test đã có JPA dependencies, entity/repository/database hợp lệ. Nó không tự biên dịch nếu thiếu các class. Service `PricingPolicy` được thêm không có nghĩa có toàn bộ REST application context.

Trong JPA test, tập trung vào query/transaction/constraint/persistence behavior. Nếu cần một service có logic nghiệp vụ và một repository thật, `@Import(PricingPolicy.class)` hoặc một integration test phù hợp có thể rõ ràng hơn nhiều filter.

### 12.2. `@JsonTest`

Slice này hướng đến JSON serializer/deserializer và những thành phần JSON được hỗ trợ. Không mặc định quét controller hay service thông thường. Khi muốn thêm custom Jackson module hoặc serializer, thường có thể `@Import` config cụ thể hoặc dùng cơ chế tương ứng version. Một include filter chỉ tác động tới candidate scan, không tự khởi động MVC HTTP pipeline.

### 12.3. `@RestClientTest` / client slice

Các HTTP client test slice thường có phạm vi auto-configuration và scanning riêng, không phải MVC server slice. Filter theo class có thể hữu ích cho một collaborator nhỏ, nhưng đừng biến client test thành web-server integration test bằng cách import bừa. Với một `RestClient` hoặc `RestTemplate`, cần dùng mock server/test utilities đúng dòng phiên bản.

### 12.4. Không chồng nhiều `@...Test` slice lên cùng class

Spring Boot không hỗ trợ coi việc thêm nhiều `@WebMvcTest` + `@DataJpaTest` là cách “hợp nhất” hai slice. Bootstrapper, context type, auto-config và TypeExcludeFilters có thể xung đột.

Nếu cần hai lớp hạ tầng, hãy chọn một slice chủ đạo và thêm hạ tầng cần thiết **có chủ đích** theo hướng dẫn Spring Boot, hoặc dùng `@SpringBootTest`. “Thêm hai annotation” không tự tạo ra một slice hợp lệ.

## 13. Cách kiểm chứng phạm vi quét thay vì đoán

### 13.1. Assert tên/kiểu bean tại context

Trong test đã có Spring `ApplicationContext context`:

```java
assertThat(context.getBeanNamesForType(FormatterService.class))
        .hasSize(1);

assertThat(context.getBeanNamesForType(AuditHeaderFilter.class))
        .isEmpty();
```

Đây là các assertion **trích từ test hoàn chỉnh**; chúng chứng minh bean type có hoặc không có trong context.

Dùng `getBeanNamesForType(Type.class)` thuận tiện hơn so sánh tất cả bean name nếu Spring có proxy/bean naming convention. Nếu có factory bean hoặc lazy bean, semantics có thể khác với các case thông thường; quan sát đúng mục tiêu.

### 13.2. Assert hành vi HTTP, không chỉ bean existence

Một bean `FormatterService` có mặt chưa chứng minh controller đã dùng nó. Request MockMvc:

```java
mvc.perform(get("/api/echo/hello"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.value").value("HELLO"));
```

là minh chứng từ request → controller → real service → JSON response. Kết hợp hai lớp assertion (bean scope và behavior) giúp bảo đảm include filter có ý nghĩa học tập thực sự.

### 13.3. Debug với report về thành phần và auto-configuration

Nếu context load fail, đừng thay filter mù quáng. Xác nhận:

1. Class cần thêm có stereotype thích hợp/implements loại tương ứng không?
2. Package có nằm trong scan roots không?
3. `useDefaultFilters` và `controllers` đang đặt gì?
4. Class có bị custom exclude ưu tiên loại không?
5. Bean được tạo qua scan hay qua `@Import`/`@Bean`/auto-configuration?
6. Main class có explicit `@ComponentScan` phá loại trừ của slice không?
7. Profile/`@ConditionalOnProperty`/`@ConditionalOnClass` có chặn bean không?
8. Dependency của bean include có đang thiếu không?
9. Spring Security filters có chặn request làm bạn tưởng thiếu controller không?
10. JUnit/test starter và Boot major version có khớp import không?

Có thể xem condition evaluation report của Spring Boot khi cần điều tra **auto-configuration**, và kiểm tra bean definitions tại context để điều tra **component scanning**. Hai nguồn chẩn đoán trả lời hai câu hỏi khác nhau.

## 14. Các lỗi phổ biến và cách khắc phục

| Triệu chứng | Vì sao có thể xảy ra | Cách xử lý |
|---|---|---|
| `NoSuchBeanDefinitionException` cho `@Service` trong `@WebMvcTest` | MVC slice cố ý không quét service thông thường | Mock hoặc import service; dùng include filter khi thật sự muốn scan |
| Include filter có class đúng nhưng bean vẫn vắng | Package ngoài scan root, bean conditional, hoặc không là scan candidate | Xác nhận package/annotation/condition; cân nhắc `@Import` |
| Exclude filter không loại bean như mong đợi | Bean được tạo qua `@Bean`/`@Import`/auto-config, không phải scan candidate | Sửa đúng nguồn bean; không lạm dụng `excludeFilters` |
| Servlet filter vẫn trong context khi dùng `addFilters=false` | Đây chỉ là tùy chọn MockMvc filter registration | Dùng `excludeFilters` nếu mục tiêu là không scan/đăng ký bean |
| Controller khác vẫn được nạp | `controllers` để trống hoặc cấu hình scan custom phá slice | Chỉ rõ `controllers`; kiểm tra explicit `@ComponentScan` |
| Security trả 401/403 | Filter chain hoặc CSRF, không nhất thiết do controller thiếu | Thiết lập auth/CSRF đúng policy |
| `useDefaultFilters=false` làm test thiếu advice/converter | Tắt cả nhóm candidate mặc định | Bật default hoặc include/import những thành phần thực sự cần |
| `excludeAutoConfiguration` không bỏ service | Chỉ ảnh hưởng auto-configuration classes | Dùng cơ chế phù hợp cho component-scanned bean |
| `@DataJpaTest` tự nhiên scan web/service | Main app dùng explicit `@ComponentScan`, làm mất TypeExcludeFilter | Đưa scan vào config phù hợp, dùng alias scanBasePackages hoặc đăng ký TypeExcludeFilter |
| Bean `WebMvcConfigurer` nằm trong `@Configuration` không được nạp | Slice loại configuration class khỏi scan, dù `@Bean` tạo kiểu WebMvcConfigurer | Dùng `@Import(MyWebConfig.class)` khi thực sự cần |
| Khi chuyển Boot 3 → 4 import `WebMvcTest` lỗi | Package/module MVC testing thay đổi | Chọn đúng import và starter Boot 4 |
| MVC slice đòi database | Import/include quá nhiều service/config hoặc scan bị phá | Thu hẹp phạm vi, mock dependency, tách test phù hợp |
| `@Mock` có nhưng controller không nhận | Mockito mock field chưa override Spring bean | Dùng annotation bean override được framework hỗ trợ |
| Test pass riêng lẻ nhưng suite fail | Context cache/global state/fixture hoặc unexpected shared configuration | Reset state và cô lập context theo nhu cầu; hạn chế `@DirtiesContext` |
| Test bị lọc hết, không chạy | Gradle/Maven test selection, Surefire, JUnit engine sai | Kiểm tra test task/report và tên class |

### 14.1. Phân biệt hai tình huống “không có bean”

- **Bean cố ý không được scan:** ví dụ `BillingService` trong MVC slice; đây là hành vi mong muốn.
- **Bean bị thiếu làm context không khởi động:** ví dụ controller cần `FormatterService` mà bạn chưa include/import/mock.

Tình huống thứ hai cần giải quyết dependency theo mục tiêu test, không nên mở rộng scan cả ứng dụng để xóa lỗi nhanh chóng. Test xanh sau khi include tất cả service chưa chắc còn được gọi là MVC slice hữu ích.

### 14.2. Đừng dùng `useDefaultFilters=false` để giải quyết vấn đề sai tầng

Nếu lỗi là do `@ComponentScan` trên main application class, tắt default filters ở test có thể tạo thêm dependency failures mà chưa khắc phục nguồn scan. Nếu lỗi là auto-configuration, thao tác `excludeFilters` trên component scanning cũng không giải quyết. Phải xác định **tầng gây lỗi**.

### 14.3. Nếu test không còn nhỏ, hãy đánh giá lại

Một MVC test cần include 12 services, 4 repositories, 3 integration clients và Redis configuration đã không còn cô lập web layer. Sắp xếp lại test:

- Một nhóm `@WebMvcTest` kiểm tra JSON, validation, routes, error handling với mock collaborator.
- Một nhóm unit tests kiểm tra business logic.
- Một vài `@SpringBootTest` integration tests kiểm tra wiring xuyên các lớp.
- Thêm real HTTP tests khi cần kiểm chứng network/server behavior.

Đây không phải làm giảm mức độ kiểm thử; đây là **phân phối hợp đồng kiểm chứng đúng tầng**.

## 15. Bài tập luyện tập

### Bài tập A — Include đúng một service

Cho `ProductController` phụ thuộc `ProductFormatter`, được khai báo `@Service` trong package application. Bạn muốn chạy logic formatter thật trong MVC slice. Cấu hình nào phù hợp?

```java
@WebMvcTest(
    controllers = ProductController.class,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductFormatter.class
    )
)
class ProductSliceTest {
}
```

**Đáp án:** cấu hình trên là một cách (snippet, cần class hiện hữu), nếu formatter có đúng dependency và nằm trong scan scope. `@Import(ProductFormatter.class)` cũng có thể là lựa chọn gọn nếu không cần kiểm tra scan. Nếu formatter phụ thuộc hệ thống I/O, thường không cần gọi thật trong MVC slice.

### Bài tập B — Exclude filter hay tắt filter chain?

Bạn có `@Component AuditHeaderFilter` và muốn chứng minh **bean không xuất hiện trong MVC slice**. Bạn chọn:

1. `@AutoConfigureMockMvc(addFilters=false)`; hay
2. `excludeFilters = @ComponentScan.Filter(type=FilterType.ASSIGNABLE_TYPE, classes=AuditHeaderFilter.class)`?

**Đáp án:** chọn **(2)** và assert bean absence bằng `getBeanNamesForType(...)`. Cách (1) chỉ tác động việc đăng ký filter vào MockMvc theo cơ chế tương ứng, không chứng minh class không được scan.

### Bài tập C — “Service vẫn xuất hiện” dù MVC slice

Main class có:

```java
@SpringBootApplication
@ComponentScan({"com.example.api", "com.example.business"})
class Application {
}
```

Vì sao `@WebMvcTest` có thể nạp service ngoài ý muốn?

**Đáp án:** explicit `@ComponentScan` có thể vô hiệu hóa filter mặc định mà meta-annotation `@SpringBootApplication` cung cấp cho slicing. Hãy đưa cấu hình scan riêng ra một nơi phù hợp, dùng alias `scanBasePackages`/`scanBasePackageClasses` nếu mục tiêu là component base package, hoặc đảm bảo `TypeExcludeFilter` được đăng ký đúng khi buộc phải dùng scan riêng.

### Bài tập D — Bean không được tạo qua scan

Test `@WebMvcTest` có `@Import(MyWebConfiguration.class)`, trong đó `@Bean CacheClient cacheClient()`. Bạn viết exclude filter theo `CacheClient.class` nhưng bean vẫn có mặt. Vì sao?

**Đáp án:** bean được tạo bởi `@Bean` từ cấu hình **đã được import**, không phải được phát hiện như candidate qua component scan. Cần sửa cấu hình import, tách config hoặc dùng test bean override phù hợp; không mong exclude filter xóa một bean từ nguồn khác.

### Bài tập E — Chọn vùng test đúng

Cần kiểm tra repository SQL query với Hibernate và database thực; nên mở rộng `@WebMvcTest` bằng include filter cho repository không?

**Đáp án:** không. Cần `@DataJpaTest` với dữ liệu/hạ tầng DB phù hợp hoặc integration test JPA. `@WebMvcTest` không phải cách chạy repository integration logic chỉ bằng một include filter.

### Checklist review

- [ ] Xác định đúng slice annotation và default included component types của phiên bản đang dùng.
- [ ] Phân biệt `controllers`, `useDefaultFilters`, `includeFilters` và `excludeFilters`.
- [ ] Mỗi custom filter có `FilterType` đúng; `classes`/`pattern` phù hợp.
- [ ] Package/quét thành phần thực sự bao trùm class muốn include.
- [ ] Đã hiểu bean đến từ scan, `@Bean`, `@Import` hay auto-configuration.
- [ ] Không dùng `excludeFilters` để tắt arbitrary auto-configuration.
- [ ] Không dùng `@AutoConfigureMockMvc(addFilters=false)` như phép thay thế cho component-scan exclude.
- [ ] Với MVC test, service dependency được mock/import/include theo mục tiêu.
- [ ] Với JPA test, hiểu entity/repository registration và hạ tầng JPA không phải component scan thông thường.
- [ ] Main `@SpringBootApplication` không có explicit scan làm phá slice filters, hoặc đã xử lý đúng.
- [ ] Một test slice vẫn nhỏ và có mục tiêu rõ, không kéo DB/remote config ngoài phạm vi.
- [ ] Kiểm chứng bean có/không trong context và hành vi HTTP phù hợp.
- [ ] Version Boot 3/4, dependency starter và imports đồng bộ.
- [ ] Spring Security/CSRF được xử lý đúng khi nằm trong scope.
- [ ] Chạy đúng JUnit class bằng Gradle/Maven Wrapper; kiểm tra số test thật sự chạy.
- [ ] Không cho test phụ thuộc thứ tự, global mutable state hoặc môi trường bên ngoài không kiểm soát.

## 16. Kết luận

**`includeFilters` và `excludeFilters` là công cụ tinh chỉnh component scanning của một test slice, không phải công tắc tổng quát bật/tắt mọi bean.** `@WebMvcTest` có tập MVC components riêng; `@DataJpaTest` dùng cơ chế JPA riêng; `@Import`, `@Bean` và auto-configuration có đường đăng ký bean khác.

Một MVC slice tốt thường chỉ cần chọn controller, thêm một số dependency có chủ đích và xác minh HTTP contract. Khi phải đưa logic thật từ service vào, một `includeFilters` chính xác có thể hữu ích. Khi một `Filter` không nằm trong hợp đồng test, `excludeFilters` có thể loại nó khỏi component scan. Nhưng hãy giữ sự khác biệt giữa **loại bean khỏi context** và **bỏ filter khỏi MockMvc chain**.

Cuối cùng, điều tra `@ComponentScan` tường minh trên main application class nếu test slice bất ngờ quét cả ứng dụng. Nắm vững **phạm vi package, default includes, custom filters và nguồn đăng ký bean** giúp test nhỏ, rõ, ổn định và dễ debug.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): slice annotations, MVC/JPA scope, user configuration, `@ComponentScan` và `TypeExcludeFilter`.
- [Spring Boot 3.5 — WebMvcTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html): `controllers`, `includeFilters`, `excludeFilters`, `useDefaultFilters`.
- [Spring Boot 3.5 — DataJpaTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): giới hạn JPA slice và filter options.
- [Spring Boot 4.0 — WebMvcTest Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/test/autoconfigure/WebMvcTest.html): package MVC test mới và phạm vi thành phần.
- [Spring Boot 4.0 — DataJpaTest Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/jpa/test/autoconfigure/DataJpaTest.html): package JPA test mới và filter options.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): `ComponentScan`, các `FilterType` và nguyên tắc candidate discovery.
- [Spring Boot — TypeExcludeFilter Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/TypeExcludeFilter.html): vai trò giữ phạm vi slice khi component scanning.
