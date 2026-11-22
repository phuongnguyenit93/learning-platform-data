# MockMvcConfigurer cho tích hợp có phạm vi

`MockMvcConfigurer` là điểm mở rộng của Spring MVC Test để gắn một nhóm cấu hình dùng chung vào một `MockMvc` được tạo từ builder. Nó hữu ích khi nhiều request trong cùng một bộ test cần chung filter, request context hoặc hành vi mặc định, nhưng cấu hình đó chỉ nên áp dụng cho những `MockMvc` được chọn.

Điểm quan trọng là phạm vi của configurer gắn với builder mà ta gọi `.apply(...)`. Một configurer không tự đăng ký vào mọi `ApplicationContext`, không tự biến thành filter toàn ứng dụng và cũng không ảnh hưởng đến request thật đi qua servlet container. Nó tùy chỉnh quá trình dựng `MockMvc` và những request được thực hiện qua instance đó.

## 1. Vị trí của `MockMvcConfigurer` trong quá trình dựng MockMvc

Spring MVC Test cung cấp hai cách dựng `MockMvc` thường gặp:

| Cách dựng | Nguồn cấu hình | Phù hợp khi |
|---|---|---|
| `MockMvcBuilders.webAppContextSetup(context)` | Một `WebApplicationContext` đã được nạp | Cần kiểm tra tích hợp với MVC configuration, controller, converter, advice, interceptor và các bean trong context |
| `MockMvcBuilders.standaloneSetup(controllers...)` | Các controller và thành phần được khai báo trực tiếp cho builder | Cần một lát cắt nhỏ, chủ động cấu hình những thành phần tham gia test |

Cả hai đều trả về builder có thể nhận configurer bằng `.apply(...)`:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(myConfigurer)
        .build();
```

Builder quyết định những thành phần nào tham gia vào `MockMvc`. `MockMvcConfigurer` bổ sung hoặc điều chỉnh cấu hình tại đúng builder đó. Vì vậy, hai test có thể dùng cùng một `ApplicationContext` nhưng tạo hai `MockMvc` với các tích hợp khác nhau.

## 2. Hai hook trong vòng đời của configurer

`MockMvcConfigurer` có hai phương thức:

```java
public interface MockMvcConfigurer {

    void afterConfigurerAdded(ConfigurableMockMvcBuilder<?> builder);

    RequestPostProcessor beforeMockMvcCreated(
            ConfigurableMockMvcBuilder<?> builder,
            WebApplicationContext context);
}
```

Mỗi hook có một thời điểm và mục đích riêng.

### `afterConfigurerAdded`

Spring gọi phương thức này khi configurer được gắn vào builder bằng `.apply(...)`. Configurer có thể dùng builder để thêm filter hoặc cấu hình chung cho `MockMvc`.

Ví dụ, một bộ test cần bảo đảm request đi qua một filter mã hóa ký tự:

```java
import org.springframework.test.web.servlet.setup.ConfigurableMockMvcBuilder;
import org.springframework.test.web.servlet.setup.MockMvcConfigurer;
import org.springframework.web.filter.CharacterEncodingFilter;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.web.context.WebApplicationContext;

final class Utf8MockMvcConfigurer implements MockMvcConfigurer {

    @Override
    public void afterConfigurerAdded(ConfigurableMockMvcBuilder<?> builder) {
        builder.addFilters(new CharacterEncodingFilter("UTF-8", true));
    }

    @Override
    public RequestPostProcessor beforeMockMvcCreated(
            ConfigurableMockMvcBuilder<?> builder,
            WebApplicationContext context) {
        return null;
    }
}
```

Khi áp dụng configurer này, filter được thêm vào chuỗi filter do `MockMvc` sử dụng. Nó không vì thế mà được đăng ký vào servlet container đang chạy ngoài test. Nếu filter đã được builder hoặc cấu hình test thêm vào, không nên thêm lần thứ hai vì filter trùng lặp có thể khiến hành vi khó hiểu.

### `beforeMockMvcCreated`

Spring gọi phương thức này ngay trước khi tạo `MockMvc`. Phương thức nhận builder và `WebApplicationContext`, sau đó có thể trả về một `RequestPostProcessor`.

`RequestPostProcessor` được áp dụng cho các request thực hiện qua `MockMvc` tương ứng. Đây là vị trí phù hợp để thêm thông tin mặc định vào request như tenant id, locale hoặc một request attribute dùng trong môi trường test.

Ví dụ, một nhóm test cần gửi cùng tenant header:

```java
import java.util.Objects;

import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.test.web.servlet.setup.ConfigurableMockMvcBuilder;
import org.springframework.test.web.servlet.setup.MockMvcConfigurer;
import org.springframework.web.context.WebApplicationContext;

final class TenantHeaderConfigurer implements MockMvcConfigurer {

    private final String tenantId;

    TenantHeaderConfigurer(String tenantId) {
        this.tenantId = Objects.requireNonNull(tenantId);
    }

    @Override
    public void afterConfigurerAdded(ConfigurableMockMvcBuilder<?> builder) {
        // Không cần thay đổi builder ở hook này.
    }

    @Override
    public RequestPostProcessor beforeMockMvcCreated(
            ConfigurableMockMvcBuilder<?> builder,
            WebApplicationContext context) {

        return request -> {
            request.addHeader("X-Tenant-Id", this.tenantId);
            return request;
        };
    }
}
```

Đối tượng `RequestPostProcessor` nhận `MockHttpServletRequest`, thay đổi request rồi trả lại chính request đó. Configurer không phải tự tạo request và cũng không cần thay đổi từng lời gọi `mockMvc.perform(...)`.

## 3. Áp dụng configurer cho một MockMvc cụ thể

Giả sử controller đọc tenant id từ header:

```java
@RestController
class OrderController {

    @GetMapping("/orders/{id}")
    OrderView findOrder(
            @PathVariable long id,
            @RequestHeader("X-Tenant-Id") String tenantId) {
        return new OrderView(id, tenantId);
    }
}

record OrderView(long id, String tenantId) {
}
```

Test có thể tạo `MockMvc` với tenant mặc định cho toàn bộ request:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringJUnitWebConfig(WebConfig.class)
class OrderControllerTests {

    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = webAppContextSetup(context)
                .apply(new TenantHeaderConfigurer("tenant-test"))
                .build();
    }

    @Test
    void usesTheConfiguredTenant() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.tenantId").value("tenant-test"));
    }
}
```

`WebConfig` ở đây là cấu hình MVC của ứng dụng hoặc cấu hình test có đăng ký `OrderController`. Ví dụ tập trung vào điểm tích hợp: configurer được áp dụng khi tạo builder, vì thế request đi qua `mockMvc` sẽ nhận tenant header mà không phải lặp lại header trong từng test.

Nếu một nhóm test khác cần tenant khác, nhóm đó có thể tạo `MockMvc` riêng:

```java
MockMvc anotherTenantMvc = webAppContextSetup(context)
        .apply(new TenantHeaderConfigurer("tenant-another"))
        .build();
```

Hai instance dùng cùng context nhưng có request configuration riêng. Việc áp dụng configurer cho builder thứ hai không thay đổi cấu hình của `MockMvc` đã được dựng trước đó.

## 4. Dùng configurer có sẵn từ thư viện

Không phải mọi configurer đều cần tự viết. Các thư viện có thể cung cấp `MockMvcConfigurer` để tích hợp với `MockMvc` theo đúng cơ chế builder này.

Một ví dụ phổ biến là Spring Security Test. Khi dựng `MockMvc` thủ công với `WebApplicationContext`, có thể áp dụng `springSecurity()`:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

Configurer của Spring Security tích hợp chuỗi filter bảo mật với `MockMvc` và cung cấp các tiện ích request post-processor của thư viện. Sau đó test có thể mô phỏng người dùng hoặc thông tin xác thực trên từng request, ví dụ:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/profile").with(user("alice")))
        .andExpect(status().isOk());
```

Ở đây có hai phạm vi cấu hình:

- `.apply(springSecurity())` tích hợp Spring Security vào `MockMvc` được dựng từ builder đó.
- `.with(user("alice"))` cung cấp danh tính cho một request cụ thể.

Phân biệt hai phạm vi này giúp test rõ ràng: cấu hình bảo mật được tích hợp một lần cho instance; danh tính hoặc dữ liệu riêng của từng tình huống được chỉ định trên request tương ứng.

## 5. Phạm vi của configurer và cách tái sử dụng

Phạm vi của `MockMvcConfigurer` được quyết định bởi nơi áp dụng nó:

| Nơi áp dụng | Phạm vi tác động |
|---|---|
| `.apply(configurer)` trên một builder | `MockMvc` được tạo từ builder đó |
| Áp dụng cùng configurer cho nhiều builder | Mỗi `MockMvc` được tạo từ builder đã áp dụng |
| Dùng configurer trong một helper dựng MockMvc | Các instance được helper đó tạo ra |
| Chỉ khai báo configurer như một bean trong context | Không tự động áp dụng vào mọi `MockMvc` builder |

Một configurer bất biến, chỉ chứa giá trị cấu hình như tenant id hoặc filter được tạo sẵn, thường có thể tái sử dụng cho nhiều builder. Nếu configurer giữ trạng thái thay đổi trong lúc request chạy, hãy cân nhắc tạo instance riêng cho từng `MockMvc`, đặc biệt khi test chạy song song. Không lưu dữ liệu của request hiện tại vào field dùng chung của configurer vì nhiều request có thể chạy đồng thời.

Có thể tạo factory để tránh lặp cấu hình:

```java
final class TestMockMvcFactory {

    private TestMockMvcFactory() {
    }

    static MockMvc forTenant(WebApplicationContext context, String tenantId) {
        return MockMvcBuilders.webAppContextSetup(context)
                .apply(new TenantHeaderConfigurer(tenantId))
                .build();
    }
}
```

Factory này làm cho phạm vi áp dụng dễ nhìn thấy tại nơi gọi:

```java
MockMvc mockMvc = TestMockMvcFactory.forTenant(context, "tenant-test");
```

Chỉ nên tạo factory khi nhiều test thực sự cần cùng quy ước dựng `MockMvc`. Với một test đơn lẻ, gọi `.apply(...)` trực tiếp thường dễ đọc hơn.

## 6. Khi nào dùng `MockMvcConfigurer`, khi nào dùng cơ chế khác

Không phải mọi cấu hình MockMvc đều cần một configurer riêng. Hãy chọn điểm mở rộng theo phạm vi của hành vi:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Thêm filter hoặc cấu hình builder cho một nhóm MockMvc | `MockMvcConfigurer` và `.apply(...)` |
| Thêm header, principal hoặc dữ liệu vào một request cụ thể | `RequestPostProcessor` qua `.with(...)` |
| Kiểm tra response của một request cụ thể | `ResultMatcher` qua `.andExpect(...)` |
| Thực hiện hành động sau một request cụ thể | `ResultHandler` qua `.andDo(...)` |
| Cấu hình mặc định trên builder trong một bộ test | `defaultRequest(...)` hoặc một configurer phù hợp |
| Cấu hình MockMvc do Spring Boot tự tạo | Cơ chế tùy biến builder của Spring Boot, chẳng hạn `MockMvcBuilderCustomizer` |

### `MockMvcConfigurer` và `RequestPostProcessor`

Hai API này liên quan nhưng không thay thế nhau:

- `MockMvcConfigurer` tham gia giai đoạn dựng `MockMvc`; nó có thể điều chỉnh builder và cung cấp một request post-processor dùng chung.
- `RequestPostProcessor` trực tiếp sửa một request. Test có thể gắn nó bằng `.with(...)` mà không cần định nghĩa configurer.

Nếu chỉ một test cần thêm header hoặc user, dùng `.with(...)` trực tiếp thường đơn giản hơn. Nếu tất cả request qua một `MockMvc` cần cùng một thiết lập, configurer có thể gom quy tắc đó vào một chỗ.

### `MockMvcConfigurer` và Spring Boot auto-configuration

Trong test dùng `@SpringBootTest` cùng `@AutoConfigureMockMvc`, Spring Boot tự tạo `MockMvc` và quản lý builder. Khai báo một bean có kiểu `MockMvcConfigurer` không có nghĩa bean đó tự động được `.apply(...)` vào builder.

Nếu cần tùy biến builder do Spring Boot quản lý, dùng điểm mở rộng của Boot như `MockMvcBuilderCustomizer`. Nếu chủ động gọi `MockMvcBuilders.webAppContextSetup(...)` hoặc `standaloneSetup(...)`, có thể áp dụng `MockMvcConfigurer` trực tiếp. Chọn một nơi sở hữu cấu hình để tránh thêm cùng filter hoặc request processor hai lần.

## 7. Các lỗi thường gặp

### Mong configurer ảnh hưởng đến mọi MockMvc

Một configurer chỉ có tác dụng khi được áp dụng vào builder. Việc tạo một class triển khai `MockMvcConfigurer` hoặc đăng ký class đó thành bean không tự làm cho mọi test sử dụng nó. Hãy kiểm tra nơi builder được tạo và bảo đảm `.apply(...)` được gọi ở đúng điểm.

### Nhầm request post-processor với filter

`RequestPostProcessor` sửa request giả lập trước khi request được xử lý. Filter tham gia chuỗi xử lý servlet. Nếu cần kiểm tra hành vi của filter, hãy thêm filter vào builder hoặc tích hợp filter thông qua configurer thích hợp; sửa request bằng post-processor không chứng minh filter đã chạy.

### Thêm filter nhiều lần

Một filter có thể đã được thêm bởi cấu hình ứng dụng, cấu hình test hoặc configurer khác. Thêm lại filter có thể làm logic chạy lặp hoặc thay đổi thứ tự xử lý. Hãy xác định nơi đăng ký filter trước khi thêm nó vào builder.

### Dùng configurer có trạng thái dùng chung trong test song song

Không giữ `currentTenant`, `currentUser` hoặc dữ liệu request có thể thay đổi trong field chung rồi cập nhật field đó trước mỗi request. Hai request song song có thể ghi đè trạng thái của nhau. Hãy dùng configurer bất biến để cung cấp mặc định, hoặc đặt dữ liệu riêng trong request bằng `.with(...)`.

### Đưa quá nhiều hành vi vào một configurer

Một configurer gom bảo mật, tenant, locale, mock clock và nhiều filter không liên quan sẽ làm test khó biết cấu hình nào gây ra hành vi. Tách theo trách nhiệm có ý nghĩa và chỉ áp dụng những phần cần thiết cho từng `MockMvc`.

### Coi `MockMvc` là một server thật

`MockMvc` mô phỏng luồng xử lý Spring MVC trong môi trường test. Filter được thêm qua builder thuộc chuỗi filter của MockMvc đó; nó không chứng minh cấu hình triển khai trên servlet container hoặc reverse proxy ngoài môi trường thật là chính xác. Những thuộc tính phụ thuộc container cần được kiểm thử ở cấp tích hợp phù hợp.

## 8. Quy trình thiết kế một configurer có phạm vi

Khi cần dùng chung một tích hợp cho một nhóm test, có thể thực hiện theo trình tự sau:

1. Xác định hành vi cần dùng chung: filter, request metadata, security integration hay cấu hình builder khác.
2. Xác định chính xác những test hoặc `MockMvc` nào cần hành vi đó.
3. Chọn hook phù hợp: `afterConfigurerAdded` để thay đổi builder; `beforeMockMvcCreated` để cung cấp request post-processor có thể dùng context.
4. Viết configurer với cấu hình bất biến và trách nhiệm hẹp.
5. Gắn nó vào builder bằng `.apply(...)` tại nơi tạo `MockMvc`.
6. Kiểm tra một request đại diện để xác nhận tích hợp thực sự có hiệu lực.
7. Nếu test khác cần cấu hình khác, tạo builder hoặc `MockMvc` riêng thay vì thay đổi trạng thái configurer đang được dùng chung.
8. Kiểm tra các filter và customizer đã có để tránh đăng ký trùng.

## 9. Tài liệu tham khảo

- [Spring Framework Reference — Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html): cách dựng `MockMvc` bằng `webAppContextSetup` và `standaloneSetup`.
- [Spring Framework Javadoc — `MockMvcConfigurer`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/setup/MockMvcConfigurer.html): hợp đồng và hai hook của configurer.
- [Spring Framework Javadoc — `ConfigurableMockMvcBuilder`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/setup/ConfigurableMockMvcBuilder.html): các phương thức cấu hình builder.
- [Spring Security Reference — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): cách tích hợp Spring Security bằng `springSecurity()`.
- [Spring Boot API — `MockMvcBuilderCustomizer`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/autoconfigure/web/servlet/MockMvcBuilderCustomizer.html): điểm mở rộng builder trong Spring Boot test auto-configuration.

`MockMvcConfigurer` giúp đóng gói một tích hợp có thể tái sử dụng và gắn nó vào đúng `MockMvc` cần thiết. Hãy dùng hook của builder cho cấu hình chung, dùng request post-processor cho dữ liệu request, và đặt lời gọi `.apply(...)` tại nơi tạo instance để phạm vi tác động luôn rõ ràng.
