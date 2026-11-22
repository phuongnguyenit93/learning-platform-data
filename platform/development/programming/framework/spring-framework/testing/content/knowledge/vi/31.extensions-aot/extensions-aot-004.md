# TestContextBootstrapper khi cần thay cơ chế khởi tạo

## 1. TestContextBootstrapper là gì?

Spring TestContext Framework quản lý cách một test được kết nối với `ApplicationContext`, cách context được tải và cách các callback kiểm thử được thực thi. `TestContextBootstrapper` là điểm mở rộng ở tầng khởi động của cơ chế này.

Bootstrapper chịu trách nhiệm cung cấp `TestContext` và danh sách `TestExecutionListener` cho `TestContextManager`. Nó cũng tham gia xây dựng `MergedContextConfiguration`, tức cấu hình đã hợp nhất từ các annotation kiểm thử và cấu hình kế thừa trên test class.

Thông tin được hợp nhất có thể bao gồm:

- Class cấu hình hoặc resource location được khai báo bằng `@ContextConfiguration`.
- `ContextLoader` dùng để tạo `ApplicationContext`.
- Active profiles.
- Property source dành cho test.
- Context initializer và context customizer.
- Cấu hình web application context và quan hệ context cha-con.

Trong phần lớn test, các annotation có sẵn như `@SpringJUnitConfig`, `@ContextConfiguration`, `@WebAppConfiguration`, `@ActiveProfiles`, `@TestPropertySource` hoặc `@DynamicPropertySource` đã đủ để mô tả context cần tạo. Chỉ nên thay bootstrapper khi cần thay đổi chính sách khởi tạo ở cấp framework cho một nhóm test hoặc toàn bộ test suite.

## 2. Vị trí của bootstrapper trong vòng đời test

Khi JUnit chạy một test có tích hợp Spring, `SpringExtension` hoặc runner tương ứng tạo `TestContextManager`. Manager này xác định bootstrapper, nhận `TestContext` và các listener từ bootstrapper, rồi gọi listener tại các điểm thích hợp của vòng đời test.

Luồng tổng quát:

```text
JUnit Jupiter / SpringExtension
             |
             v
      TestContextManager
             |
             v
      Chọn TestContextBootstrapper
       - @BootstrapWith nếu được khai báo
       - bootstrapper mặc định phù hợp
             |
             v
      Bootstrapper xây dựng TestContext
      và danh sách TestExecutionListener
             |
             v
      MergedContextConfiguration
      - classes / locations
      - profiles / properties
      - loader / initializers
      - context customizers / parent
             |
             v
      ContextLoader tải ApplicationContext
             |
             v
      TestContextManager gọi listener
      quanh test class / instance / method
             |
             v
          Test method
```

`TestContextBootstrapper` quyết định cách TestContext được thiết lập. `ContextLoader` chịu trách nhiệm tải `ApplicationContext` từ cấu hình đã hợp nhất. `TestExecutionListener` nhận callback trong vòng đời test. Ba thành phần này có vai trò riêng, vì vậy không nên dùng bootstrapper để giải quyết một yêu cầu vốn chỉ cần thay `ContextLoader` hoặc thêm listener.

## 3. Bootstrapper mặc định và bootstrapper của Spring Boot

Nếu test không khai báo `@BootstrapWith`, Spring chọn bootstrapper mặc định dựa trên loại test context. Những bootstrapper thường gặp gồm:

| Bootstrapper | Phạm vi sử dụng |
|---|---|
| `DefaultTestContextBootstrapper` | Bootstrapper mặc định cho test context thông thường. |
| `WebTestContextBootstrapper` | Dùng cho test có `@WebAppConfiguration`, cần web application context trên Servlet stack. |
| `SpringBootTestContextBootstrapper` | Do Spring Boot sử dụng cho `@SpringBootTest`, bổ sung cách khởi tạo đặc thù của Boot. |
| Bootstrapper của test slice | Các annotation như `@WebMvcTest` có thể dùng bootstrapper riêng để áp dụng auto-configuration và bộ lọc slice tương ứng. |

Spring Boot cung cấp bootstrapper riêng vì quá trình khởi tạo test Boot có thêm các khái niệm như `@SpringBootConfiguration`, `@SpringBootTest`, `@AutoConfigure...`, `ContextCustomizerFactory` và cấu hình môi trường Boot. Nếu test dùng `@SpringBootTest` hoặc test slice, không nên thay bootstrapper Boot bằng `DefaultTestContextBootstrapper` một cách tùy tiện; việc đó có thể làm mất các hành vi mà annotation Boot mong đợi.

Tên lớp bootstrapper mặc định và cách lựa chọn có thể thay đổi theo phiên bản Spring Framework hoặc Spring Boot. Khi cần kiểm soát chính xác, hãy xem annotation `@BootstrapWith` trên annotation test đang sử dụng và Javadoc của phiên bản dự án.

## 4. Chỉ định bootstrapper bằng @BootstrapWith

`@BootstrapWith` cho phép chỉ định implementation của `TestContextBootstrapper` cho test class. Annotation này cũng có thể được dùng như meta-annotation để tạo annotation kiểm thử dùng chung trong dự án.

Ví dụ, tạo bootstrapper riêng kế thừa `DefaultTestContextBootstrapper`:

```java
import org.springframework.test.context.support.DefaultTestContextBootstrapper;

public class ProjectTestContextBootstrapper
        extends DefaultTestContextBootstrapper {

    // Đặt các tùy chỉnh bootstrap dùng chung cho nhóm test của dự án tại đây.
}
```

Đăng ký bootstrapper trên test class:

```java
import org.springframework.test.context.BootstrapWith;
import org.springframework.test.context.ContextConfiguration;

@BootstrapWith(ProjectTestContextBootstrapper.class)
@ContextConfiguration(classes = TestApplicationConfiguration.class)
class CatalogRepositoryTests {
}
```

Ví dụ này minh họa cách thay bootstrapper mặc định bằng một implementation của dự án. Vì lớp chưa override hành vi nào, nó vẫn giữ cách làm việc của `DefaultTestContextBootstrapper`. Một bootstrapper thực tế chỉ nên override các hook cần thay đổi; không nên sao chép toàn bộ logic của Spring vào dự án.

### Tạo composed annotation cho nhóm test

Nếu nhiều test cần cùng một bootstrapper và cùng quy ước cấu hình, có thể gói `@BootstrapWith` vào annotation riêng:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.test.context.BootstrapWith;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@BootstrapWith(ProjectTestContextBootstrapper.class)
public @interface ProjectIntegrationTest {
}
```

Sử dụng annotation:

```java
@ProjectIntegrationTest
@ContextConfiguration(classes = IntegrationTestConfiguration.class)
class InventoryIntegrationTests {
}
```

Composed annotation giúp nhóm test dùng cùng chính sách bootstrap mà không lặp lại `@BootstrapWith`. Nếu annotation được dùng cùng một annotation cấp cao hơn như `@SpringBootTest`, cần bảo đảm bootstrapper được chọn vẫn tương thích với cơ chế của annotation đó.

## 5. Tùy chỉnh ContextLoader mặc định

Một lý do có thể cần bootstrapper riêng là dự án muốn chọn `ContextLoader` mặc định theo một quy ước riêng. `AbstractTestContextBootstrapper` cung cấp hook `getDefaultContextLoaderClass(Class<?>)` để xác định loader dự phòng khi `@ContextConfiguration` không chỉ định loader rõ ràng.

Ví dụ dự án có một nhóm test XML legacy và muốn dùng `GenericXmlContextLoader` làm loader mặc định:

```java
import org.springframework.test.context.ContextLoader;
import org.springframework.test.context.support.DefaultTestContextBootstrapper;
import org.springframework.test.context.support.GenericXmlContextLoader;

public class LegacyXmlTestContextBootstrapper
        extends DefaultTestContextBootstrapper {

    @Override
    protected Class<? extends ContextLoader> getDefaultContextLoaderClass(
            Class<?> testClass) {
        return GenericXmlContextLoader.class;
    }
}
```

Đăng ký bootstrapper và khai báo resource XML:

```java
import org.springframework.test.context.BootstrapWith;
import org.springframework.test.context.ContextConfiguration;

@BootstrapWith(LegacyXmlTestContextBootstrapper.class)
@ContextConfiguration(locations = "classpath:/legacy-test-context.xml")
class LegacyBillingTests {
}
```

Trong ví dụ, test không khai báo `loader = ...`, nên bootstrapper cung cấp loader mặc định. Nếu `@ContextConfiguration` đã chỉ định một `ContextLoader` tường minh, lựa chọn đó được ưu tiên theo cấu hình annotation. Hook này chỉ thay loader dự phòng; nó không thay thế nội dung trong file XML hoặc tự thêm bean vào context.

Nếu chỉ có một test cần XML loader, khai báo `@ContextConfiguration(loader = GenericXmlContextLoader.class)` thường đơn giản hơn. Bootstrapper riêng có ý nghĩa khi quy tắc đó cần được áp dụng nhất quán cho cả một họ test.

## 6. Chọn đúng extension point thay vì thay bootstrapper

`TestContextBootstrapper` là điểm mở rộng ở tầng cao. Trước khi tạo implementation riêng, hãy xác định thay đổi thực sự thuộc phần nào:

| Nhu cầu | Extension point phù hợp hơn |
|---|---|
| Chỉ đổi class cấu hình hoặc resource location | `@ContextConfiguration` |
| Chỉ đổi loader cho một test | Thuộc tính `loader` của `@ContextConfiguration` |
| Cần thêm bean hoặc thay cấu hình context | `@TestConfiguration`, `@Import`, `ApplicationContextInitializer` hoặc cấu hình test riêng |
| Cần thay đổi context theo điều kiện hoặc đăng ký bean động | `ContextCustomizer` / `ContextCustomizerFactory` |
| Cần thêm listener cho vòng đời test | `@TestExecutionListeners` với merge mode phù hợp |
| Cần bật profile | `@ActiveProfiles` hoặc `ActiveProfilesResolver` |
| Cần thêm property tĩnh cho test | `@TestPropertySource` hoặc thuộc tính `properties` của annotation Boot |
| Cần property phụ thuộc port/container được tạo lúc chạy | `@DynamicPropertySource` |
| Cần cấu trúc nhiều context cha-con | `@ContextHierarchy` |
| Cần thay đổi chính sách bootstrap chung, cách hợp nhất cấu hình hoặc listener mặc định cho một họ test | `TestContextBootstrapper` tùy chỉnh |

Đặc biệt, `ContextCustomizerFactory` thường là lựa chọn phù hợp nếu mục tiêu là bổ sung một customizer vào context mà vẫn giữ nguyên phần còn lại của quy trình bootstrap. Bootstrapper riêng chỉ nên được chọn khi cần thay đổi chính sách tổng thể mà các extension point cấp thấp hơn không đáp ứng.

## 7. Khi nào cần kế thừa bootstrapper của Spring Boot?

Với test Spring Boot, bootstrapper được chọn có thể cung cấp logic quan trọng để phát hiện cấu hình Boot, xử lý `@SpringBootTest`, áp dụng test slice và thêm các context customizer của Boot.

Nếu cần tùy chỉnh một test Boot, hãy cân nhắc theo thứ tự:

1. Dùng `@TestConfiguration`, `@Import`, `@DynamicPropertySource` hoặc `@ActiveProfiles` nếu chỉ cần thay bean, property hay profile.
2. Dùng `ContextCustomizerFactory` nếu cần can thiệp vào context theo một quy tắc có thể đóng gói.
3. Chỉ khi thật sự cần thay chính sách bootstrap, kế thừa bootstrapper Boot tương ứng với annotation đang dùng và giữ lại hành vi của nó.

Ví dụ về nguyên tắc kế thừa:

```java
import org.springframework.boot.test.context.SpringBootTestContextBootstrapper;

public class ProjectBootTestContextBootstrapper
        extends SpringBootTestContextBootstrapper {

    // Chỉ override hook mà dự án thực sự cần thay đổi.
}
```

Lớp trên giữ nền tảng bootstrap của `@SpringBootTest`. Khi áp dụng, cần đăng ký bootstrapper tùy chỉnh qua annotation phù hợp và kiểm tra tương thích với phiên bản Boot. Với test slice như `@WebMvcTest`, bootstrapper có thể là implementation riêng của slice; kế thừa `SpringBootTestContextBootstrapper` không nhất thiết giữ lại hành vi slice đó.

Không thay bootstrapper Boot bằng `DefaultTestContextBootstrapper` chỉ để giải quyết một vấn đề property hoặc bean. Việc đó có thể khiến test khởi tạo một context khác với context mà Spring Boot dự kiến.

## 8. MergedContextConfiguration và context cache

`MergedContextConfiguration` là mô hình dữ liệu mô tả cấu hình đã hợp nhất để tải `ApplicationContext`. Nó chứa các thông tin như test class, locations, classes, context initializer, active profiles, property source descriptors, context customizers, parent configuration và loader.

Spring TestContext Framework dùng cấu hình đã hợp nhất này để quản lý context cache. Các test có cấu hình tương đương có thể dùng lại context nhằm giảm thời gian chạy.

Khi tùy chỉnh bootstrapper, cần bảo đảm dữ liệu cấu hình được hợp nhất phản ánh đầy đủ các yếu tố ảnh hưởng đến context. Nếu một bootstrapper tạo ra context khác nhau nhưng không thể hiện khác biệt đó trong cấu hình hoặc customizer phù hợp, cache có thể tái sử dụng context không đúng với test hiện tại.

Không nên sửa `MergedContextConfiguration` theo cách bỏ qua thông tin về profiles, properties, loader hoặc context customizers. Nếu cần thay đổi cấu hình, hãy dùng hook được Spring cung cấp và bảo đảm các thành phần tham gia vào quá trình so sánh/cache key đúng cách.

## 9. Bootstrapper, ContextLoader và ContextCustomizer phối hợp thế nào?

Ba extension point này thường bị nhầm lẫn vì đều tác động đến quá trình tạo `ApplicationContext`:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `TestContextBootstrapper` | Xác định cách xây dựng TestContext và cấu hình đã hợp nhất; cung cấp listener mặc định. | `DefaultTestContextBootstrapper`, bootstrapper Boot hoặc bootstrapper của dự án. |
| `ContextLoader` | Tạo và tải `ApplicationContext` từ `MergedContextConfiguration`. | `AnnotationConfigContextLoader`, `GenericXmlContextLoader`, `DelegatingSmartContextLoader`. |
| `ContextCustomizer` | Áp dụng một thay đổi cụ thể vào context trong quá trình chuẩn bị trước khi context được refresh. | Đăng ký bean hoặc điều chỉnh cấu hình dựa trên metadata test. |

Ví dụ, nếu chỉ cần đăng ký một bean giả cho integration test, `@TestConfiguration` hoặc `ContextCustomizer` phù hợp hơn việc thay bootstrapper. Nếu cần loader riêng để đọc một định dạng cấu hình, hãy xem xét `ContextLoader`. Nếu cần toàn bộ nhóm test dùng quy tắc hợp nhất cấu hình hoặc listener khác nhau, bootstrapper mới là tầng cần xem xét.

## 10. Tác động đến AOT và tính xác định của bootstrap

Spring Framework hỗ trợ xử lý AOT cho test context ở các phiên bản hiện đại. Trong giai đoạn AOT, cấu hình test context được phân tích và tạo ra initializer hoặc mã hỗ trợ để dùng khi chạy test trong chế độ AOT.

Một bootstrapper tùy chỉnh cần có hành vi xác định giữa giai đoạn tạo AOT và giai đoạn chạy test. Nếu bootstrapper chọn cấu hình dựa trên biến môi trường thay đổi, trạng thái hệ thống bên ngoài hoặc giá trị ngẫu nhiên, context được phân tích khi build có thể khác context lúc chạy.

Khi dự án sử dụng AOT cho test:

- Giữ cấu hình bootstrap ổn định và có thể xác định từ annotation/configuration đã khai báo.
- Không phụ thuộc vào dịch vụ production hoặc Internet để quyết định context cần tạo.
- Kiểm tra custom `ContextLoader`, initializer và context customizer có tương thích với quy trình AOT đang dùng.
- Nếu custom bootstrapper thay đổi cách tạo context, chạy cả test ở chế độ thông thường và pipeline AOT để phát hiện khác biệt.
- Cung cấp runtime hints hoặc AOT contribution khi extension tùy chỉnh dùng reflection, resource hoặc proxy cần được nhận diện trước.

Bootstrapper không tự động làm cho test context tương thích AOT. AOT compatibility phụ thuộc vào cách toàn bộ context và các extension point được xây dựng. Nếu chỉ cần thêm property hoặc bean có thể xác định, dùng annotation hoặc customizer tiêu chuẩn thường giúp Spring phân tích cấu hình dễ dàng hơn.

## 11. Kiểm thử bootstrapper tùy chỉnh

Khi đã có bootstrapper riêng, nên kiểm thử nó bằng một test context nhỏ và xác nhận hành vi mà bootstrapper chịu trách nhiệm. Không cần kiểm tra lại toàn bộ Spring TestContext Framework.

Ví dụ dưới đây minh họa việc xác nhận profile và bean được nạp trong context của test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.BootstrapWith;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestApplicationConfiguration.class)
@BootstrapWith(ProjectTestContextBootstrapper.class)
@ActiveProfiles("bootstrap-test")
class ProjectBootstrapperTests {

    @Autowired
    ApplicationContext context;

    @Test
    void loadsTheExpectedTestContext() {
        assertThat(context.getEnvironment().getActiveProfiles())
                .contains("bootstrap-test");
        assertThat(context.containsBean("testMarker")).isTrue();
    }
}
```

`TestApplicationConfiguration` cần khai báo bean có tên `testMarker`. Ví dụ này xác nhận test context được nạp và profile được áp dụng; nếu bootstrapper có hành vi riêng như chọn loader, hãy viết assertion trực tiếp cho kết quả đó, chẳng hạn kiểm tra bean hoặc context type đặc thù. Để tránh test chỉ xác nhận Spring mặc định, hãy chọn một hành vi cụ thể mà bootstrapper thực sự thay đổi.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Test Boot mất auto-configuration sau khi thêm `@BootstrapWith` | Bootstrapper Boot bị thay bằng bootstrapper Framework chung. | Kế thừa bootstrapper Boot tương ứng hoặc dùng extension point cấp thấp hơn. |
| `@ContextConfiguration` không dùng loader mong đợi | Loader được chỉ định tường minh hoặc hook mặc định không được gọi. | Kiểm tra thuộc tính `loader` và `getDefaultContextLoaderClass(...)`. |
| Test class không nhận listener mong đợi | Bootstrapper tùy chỉnh thay đổi danh sách listener mặc định. | Giữ listener cần thiết hoặc dùng cơ chế merge phù hợp; kiểm tra listener do bootstrapper cung cấp. |
| Context cache trả context không phù hợp | Cấu hình động hoặc customizer không thể hiện đầy đủ khác biệt giữa các test. | Đưa khác biệt vào merged configuration/customizer và quản lý cache key đúng cách. |
| Custom bootstrapper không được chọn | `@BootstrapWith` không được đặt trên test hoặc meta-annotation được áp dụng như dự kiến. | Kiểm tra annotation trực tiếp, composed annotation và kế thừa annotation. |
| Test hoạt động thường nhưng lỗi ở AOT | Bootstrapper hoặc extension phụ thuộc vào thông tin chỉ có ở runtime. | Giữ cấu hình xác định và kiểm tra hỗ trợ AOT của loader/customizer/initializer. |
| Bootstrapper quá phức tạp | Đang dùng SPI cấp cao để giải quyết thay đổi nhỏ về property hoặc bean. | Chuyển sang `@TestPropertySource`, `@DynamicPropertySource`, `@TestConfiguration` hoặc `ContextCustomizerFactory`. |

## 13. Quy trình quyết định có cần bootstrapper riêng không

Trước khi tạo bootstrapper mới, hãy trả lời lần lượt:

1. Vấn đề có thể giải quyết bằng annotation cấu hình test hiện có không?
2. Nếu cần thay cách tải context, `ContextLoader` có đủ không?
3. Nếu cần thêm thay đổi trước khi context refresh, `ApplicationContextInitializer` hoặc `ContextCustomizer` có đáp ứng không?
4. Nếu chỉ cần thêm callback vòng đời, `@TestExecutionListeners` có phù hợp không?
5. Nếu cần thay cách hợp nhất cấu hình, chọn loader mặc định hoặc chính sách listener cho cả nhóm test, `TestContextBootstrapper` có phải tầng phù hợp không?
6. Nếu dùng Spring Boot, bootstrapper mới có giữ lại hành vi của bootstrapper Boot hoặc test slice không?
7. Nếu dùng AOT, bootstrapper và các extension liên quan có hành vi xác định trong cả giai đoạn build và runtime không?

Khi câu trả lời cho các bước đầu cho thấy extension point đơn giản hơn đã đủ, hãy dùng extension point đó. Bootstrapper tùy chỉnh nên được dành cho chính sách bootstrap có phạm vi rõ ràng và được nhiều test thực sự dùng chung.

## 14. Kết luận

`TestContextBootstrapper` là SPI điều khiển cách Spring TestContext Framework xây dựng `TestContext`, hợp nhất cấu hình và cung cấp listener cho vòng đời test. `@BootstrapWith` chọn bootstrapper cho test class hoặc nhóm test. Khi cần thay loader mặc định hay chính sách bootstrap chung, có thể kế thừa `DefaultTestContextBootstrapper` hoặc bootstrapper tương ứng của Spring Boot và override đúng hook. Với thay đổi nhỏ về bean, profile, property, loader riêng lẻ hoặc listener, hãy ưu tiên annotation và extension point chuyên biệt. Cách chọn đúng tầng giúp giữ hành vi mặc định của Spring, giảm rủi ro với context cache và làm cho test context dễ tương thích với AOT hơn.

## Tài liệu tham khảo

- [Spring Framework Reference — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Spring Framework Javadoc — `TestContextBootstrapper`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestContextBootstrapper.html)
- [Spring Framework Javadoc — `@BootstrapWith`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/BootstrapWith.html)
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
