# @OverrideAutoConfiguration và @ImportAutoConfiguration trong Spring Boot Test Slice

## 1. Mục tiêu bài học

Một ứng dụng Spring Boot chạy bình thường cần rất nhiều cơ chế tự cấu hình: MVC, Jackson, datasource, transaction, security, messaging, metrics… Nhưng một bài kiểm thử controller có thể chỉ cần **MVC + MockMvc + controller + mock service**. Nếu nạp toàn bộ auto-configuration và mọi bean của ứng dụng, test có thể chậm hoặc thất bại chỉ vì database/broker không sẵn sàng, dù điều cần kiểm là HTTP request mapping.

Spring Boot giải quyết bài toán đó bằng **test slice**. Hai annotation đứng phía sau thiết kế này là:

- **`@OverrideAutoConfiguration(enabled = false)`**: ghi đè trạng thái của cơ chế `@EnableAutoConfiguration`, thường để **tắt việc nạp cả tập auto-configuration mặc định**.
- **`@ImportAutoConfiguration(...)`**: **nhập có chọn lọc** các auto-configuration class mà một slice hoặc bài test cần; vẫn dùng cơ chế ordering và conditional auto-configuration của Spring Boot.

Hai annotation này thường xuất hiện **gián tiếp** qua `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@WebFluxTest`… Chúng bổ sung cho **component-scan filtering** để một slice có đủ framework beans mà không trở thành full application.

Kết thúc bài, bạn phải làm được những việc sau:

1. Giải thích vì sao `@WebMvcTest` vẫn có `MockMvc`, MVC infrastructure nhưng không tự nạp các service/repository thông thường.
2. Phân biệt **chặn broad auto-configuration**, **nhập selected auto-configuration**, **lọc component scan** và **import user configuration**.
3. Sử dụng `@ImportAutoConfiguration` với `value`/`classes` và `exclude`; hiểu thêm metadata `META-INF/spring/...imports`.
4. Biết khi nào dùng `@Import`, `@MockitoBean`, `@EnableConfigurationProperties` hoặc một phạm vi test khác thay vì lạm dụng `@ImportAutoConfiguration`.
5. Đọc lỗi thiếu bean, dependency bị kéo vào slice, conditional auto-configuration không match và sự khác biệt với `@SpringBootTest`.
6. Thực hiện ví dụ **Java 17+ / Spring Boot 3.5.16 / Maven / JUnit Jupiter**, trong đó test tự chứng minh một auto-configuration chỉ được load khi được phép.

Trong bài này, từ “auto-configuration” chỉ các class Spring Boot hoặc class mở rộng theo chuẩn của Spring Boot (thường mang `@AutoConfiguration` hoặc được dùng như auto-configuration), **không** đồng nghĩa với mọi `@Configuration` thông thường.

## 2. Phải hiểu bốn cơ chế riêng biệt

### 2.1. `@EnableAutoConfiguration`: chế độ bình thường của ứng dụng

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Khi khởi động, Spring Boot khám phá các auto-configuration candidates trên classpath, xét điều kiện (class có mặt, bean đã có, property, web application type…) và cấu hình những bean còn thiếu. Các candidates của Boot hiện đại được công bố qua file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Một file như vậy có thể chứa tên đầy đủ của nhiều class auto-configuration. Việc **candidate được phát hiện** không bảo đảm các `@Bean` bên trong được tạo: `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` và các condition khác có thể khiến class hoặc bean bỏ qua.

### 2.2. `@OverrideAutoConfiguration(enabled = false)`: tắt tập auto-configuration rộng

Annotation nằm ở:

```java
import org.springframework.boot.test.autoconfigure.OverrideAutoConfiguration;
```

Cú pháp:

```java
@OverrideAutoConfiguration(enabled = false)
```

Trong Spring Boot 3.5, annotation này override cơ chế bật/tắt `@EnableAutoConfiguration`. Khi `enabled=false`, Spring Boot **không tải hàng loạt auto-configurations bằng đường khám phá mặc định** của `@EnableAutoConfiguration` trong test context.

Nhưng **không** có nghĩa:

- “Không còn Spring ApplicationContext.”
- “Không còn bean được định nghĩa bằng `@Component`, `@Bean` hoặc `@Import`.”
- “Không một auto-configuration nào có thể được import.”
- “Không còn MVC/JSON/JPA infrastructure.”
- “Bean bị cấm tạo dù tôi import trực tiếp.”

Các class được Spring quản lý vẫn có thể được tạo thông qua configuration, component scan, test imports và các nguồn khác. Đặc biệt, `@ImportAutoConfiguration` **vẫn có thể nhập một tập auto-configuration chọn lọc**.

Thuộc tính `enabled` là **bắt buộc** trong API này, nên cần viết `enabled = false` hoặc `enabled = true`, không suy đoán annotation có default value để có thể viết trống.

### 2.3. `@ImportAutoConfiguration`: chỉ nhập những auto-configuration được chỉ định

Import:

```java
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
```

Ví dụ:

```java
@ImportAutoConfiguration(FeatureAutoConfiguration.class)
```

Cơ chế `@ImportAutoConfiguration` áp dụng các ordering rules liên quan đến auto-configuration, nhưng **giới hạn ở tập class chỉ định** (hoặc lấy từ file `.imports` liên kết với annotation). Nó không thay `@EnableAutoConfiguration` bằng “bật mọi thứ” lần nữa.

Bạn cũng có thể viết:

```java
@ImportAutoConfiguration(
        classes = {FeatureAutoConfiguration.class, ExtraAutoConfiguration.class},
        exclude = ExtraAutoConfiguration.class)
```

Hai thuộc tính `value` và `classes` là alias; chọn **một trong hai**. `exclude` chỉ rõ những auto-configurations không được nhập. Điều kiện bên trong auto-configuration vẫn được đánh giá: chỉ định class là **được xét**, không hứa rằng mọi bean từ class đó tồn tại.

### 2.4. TypeExcludeFilters: slice còn hạn chế component scan

Trong Boot 3.5, `@WebMvcTest` có các meta-annotations tiêu biểu:

```java
@OverrideAutoConfiguration(enabled = false)
@TypeExcludeFilters(WebMvcTypeExcludeFilter.class)
@AutoConfigureCache
@AutoConfigureWebMvc
@AutoConfigureMockMvc
@ImportAutoConfiguration
```

Đây là **trích mô tả các meta-annotation** của `@WebMvcTest`, không phải lớp Java độc lập. Mỗi phần có nhiệm vụ khác nhau:

- `@OverrideAutoConfiguration` ngăn import **toàn bộ** auto-configuration candidates thông thường.
- `@TypeExcludeFilters` giới hạn các component được scan theo luật của web MVC slice.
- Các `@AutoConfigure…` đăng ký cấu hình kiểm thử phù hợp MVC, MockMvc, cache…
- `@ImportAutoConfiguration` và file metadata đi kèm định nghĩa **danh sách auto-configurations chọn lọc**.

Vì vậy, **chỉ thêm `@OverrideAutoConfiguration(false)` vào một test không tạo ra “slice đầy đủ”**: nó không tự có type-exclude filters và bộ test auto-configurations như `@WebMvcTest`. Nếu bạn tạo test slice custom, phải thiết kế cả scan boundary lẫn các infrastructure beans cần thiết.

## 3. So sánh các annotation để khỏi nhầm

| Annotation / cơ chế | Chức năng chính | Khi nên dùng |
| --- | --- | --- |
| `@SpringBootTest` | Tạo test context từ ứng dụng, bình thường bao gồm auto-configuration rộng | Kiểm wiring/integration nhiều tầng |
| `@WebMvcTest` / `@DataJpaTest` | Test slice tích hợp cơ chế lọc bean và auto-config phù hợp | Kiểm một tầng có ý nghĩa |
| `@OverrideAutoConfiguration(enabled=false)` | Tắt đường auto-config broad của `@EnableAutoConfiguration` | Viết slice/test context tùy chỉnh khi biết rõ muốn disable |
| `@ImportAutoConfiguration` | Nhập auto-configuration classes có chọn lọc, theo luật ordering/conditions | Bổ sung auto-config cho slice |
| `@Import` | Nhập cấu hình Spring thông thường hoặc bean/class do test cần | Import custom `@TestConfiguration`, `@Configuration`, specific component |
| `@MockitoBean` | Thay/đăng ký Mockito mock bean trong test Spring context | Cấp collaborator bị slice cố ý loại bỏ |
| `@EnableConfigurationProperties` | Đăng ký xử lý một/một số `@ConfigurationProperties` types | Slice cần binding config property không được scan |
| `excludeAutoConfiguration` của slice | Loại một số auto-configurations khỏi tập slice | Giảm hạ tầng không liên quan hoặc ngăn auto-config cụ thể |
| `@SpringBootTest(properties=...)` | Bổ sung/override property sources cho test | Điều chỉnh điều kiện config/hành vi |
| `@DirtiesContext` | Làm bẩn cache context, yêu cầu rebuild | Context state đã bị test thay đổi; không sửa thiếu bean |

Chú ý: `@ImportAutoConfiguration` **không** phải cách thích hợp để import một `@Service` thông thường chỉ vì nó bị slice scan loại bỏ. Với service collaborator của MVC controller, thường nên dùng `@MockitoBean`. Nếu mục tiêu là kiểm service thật, chuyển sang `@Import(Service.class)` hoặc chọn full-context test, tùy rủi ro muốn kiểm. Việc nhập service thật có thể kéo theo repository/external dependencies và làm slice mất tính cô lập.

## 4. Luồng cấu hình một @WebMvcTest

Xem một project có:

```text
CatalogController -> CatalogService -> CatalogRepository -> DataSource
```

Một full `@SpringBootTest` có thể tải controller, service, repository, datasource, security, scheduler, messaging và các auto-configurations tương ứng. Một `@WebMvcTest(CatalogController.class)` tập trung vào:

```text
Spring TestContext
  |
  +-- MVC infrastructure (DispatcherServlet, handler mappings, codecs)
  +-- MockMvc
  +-- CatalogController (bean thật)
  +-- các MVC components hợp lệ theo slice filter
  +-- CatalogService? -> KHÔNG được quét như @Service thông thường
  +-- CatalogRepository? -> KHÔNG được quét như @Repository thông thường
  +-- DataSource auto-config? -> không tự nhập theo full-app discovery
```

Cách cung cấp service cho controller:

```java
@WebMvcTest(CatalogController.class)
class CatalogControllerTest {
    @MockitoBean
    CatalogService catalogService;

    @Autowired
    MockMvc mvc;
}
```

`@MockitoBean` thuộc Spring Framework 6.2+ (Spring Boot 3.4/3.5); import là `org.springframework.test.context.bean.override.mockito.MockitoBean`. Tạo mock service **không** đồng nghĩa load toàn bộ persistence stack. Controller và MVC vẫn là bean/infra thật.

**Một số slice cũng tự import security configuration.** Không suy từ “slice” rằng không có filters. Spring Boot `@WebMvcTest` có thể auto-configure Spring Security nếu dependency hiện diện; HTTP 401/403 khi test expect 200 có thể do security, không phải do `@ImportAutoConfiguration`.

## 5. Quan hệ giữa hai annotation: cần cả hai, nhưng theo đúng mục đích

### 5.1. Đường broad của full app

```text
@SpringBootApplication
    |
    +-- @EnableAutoConfiguration
            |
            +-- đọc AutoConfiguration.imports trong classpath
            +-- xét conditions và order
            +-- tạo các bean phù hợp
```

### 5.2. Đường selective của slice

```text
@WebMvcTest
    |
    +-- @OverrideAutoConfiguration(enabled=false)
    |       |
    |       +-- không dùng tập imports rộng của @EnableAutoConfiguration
    |
    +-- @TypeExcludeFilters(WebMvcTypeExcludeFilter)
    |       |
    |       +-- chỉ cho MVC components phù hợp đi qua component scan
    |
    +-- @AutoConfigureWebMvc/@AutoConfigureMockMvc/...
    |
    +-- @ImportAutoConfiguration
            |
            +-- đọc tập imports liên kết với test annotation
            +-- import auto-configurations thuộc slice (và additions)
            +-- xét ordering và @Conditional
```

Hai annotation **không mâu thuẫn**: tắt một nguồn import rộng và giữ nguồn import chọn lọc. Nếu một auto-configuration phụ thuộc bean khác không có trong slice, import nó có thể vẫn bị bỏ qua vì condition fail, hoặc có thể làm context fail vì dependency cần thiết không tồn tại. Đó là lý do mọi import bổ sung phải gắn với một nhu cầu rõ ràng.

### 5.3. “Imported” không đồng nghĩa “Bean chắc chắn được tạo”

Ví dụ một auto-configuration:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.OptionalEngine")
class OptionalEngineAutoConfiguration {
    @Bean
    EngineSupport engineSupport() {
        return new EngineSupport();
    }
}
```

Đây là **minh họa khái niệm**, không phải file chạy độc lập. Khi class `OptionalEngine` không có trong classpath, condition không match nên `EngineSupport` không được tạo, ngay cả khi annotation đã được nhập qua `@ImportAutoConfiguration`.

Các condition khác cũng phải được kiểm: web application type, property flags, existing/missing beans, resource availability và thứ tự đăng ký bean definition. Bởi vậy, đừng xử lý `NoSuchBeanDefinitionException` chỉ bằng cách thêm import tràn lan: cần xem condition evaluation report.

## 6. Dự án chạy được: chứng minh broad auto-configuration bị tắt còn selected import vẫn hoạt động

Mục này sử dụng **một custom auto-configuration được phát hiện từ metadata** và **hai custom auto-configurations không được đăng ký vào metadata broad** để có phép kiểm rõ ràng:

- **`DiscoveryAutoConfiguration`** xuất hiện trong `AutoConfiguration.imports` của test classpath: full test context dùng `@EnableAutoConfiguration` sẽ thấy bean `discoveryTag`.
- **`FeatureAutoConfiguration`** chỉ được nạp khi bạn ghi `@ImportAutoConfiguration(FeatureAutoConfiguration.class)`.
- **`ExtraAutoConfiguration`** được dùng để thực nghiệm `exclude`.
- Tất cả class cấu hình bổ sung nằm ở **package ngoài component scan của application**, để không bị scan thành `@Configuration` thông thường. Đây là điều kiện quan trọng giúp demo thật sự chứng minh đường auto-import.

### 6.1. Cây file

```text
slice-autoconfig-lab/
├── pom.xml
├── src/main/java/com/example/slicelab/
│   ├── SliceLabApplication.java
│   ├── CatalogService.java
│   └── CatalogController.java
├── src/test/java/
│   ├── com/example/testsupport/
│   │   ├── DiscoveryTag.java
│   │   ├── FeatureTag.java
│   │   ├── ExtraTag.java
│   │   ├── DiscoveryAutoConfiguration.java
│   │   ├── FeatureAutoConfiguration.java
│   │   └── ExtraAutoConfiguration.java
│   └── com/example/slicelab/
│       ├── FullDiscoveryTest.java
│       ├── WebMvcSliceTest.java
│       ├── WebMvcImportTest.java
│       ├── LeanSelectiveContextTest.java
│       └── ImportExclusionTest.java
└── src/test/resources/META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**Package boundary quan trọng:** app ở `com.example.slicelab`; test-support auto-configurations ở `com.example.testsupport`, là package **anh em**, không nằm trong subtree `com.example.slicelab`. `@SpringBootApplication` scan theo package gốc `com.example.slicelab` nên không tự scan các class test-support.

### 6.2. Maven POM

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>slice-autoconfig-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
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
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

Dùng `spring-boot-starter-web` để có MVC và `MockMvc` trong test. Test dependencies gồm Spring Boot Test Autoconfigure, JUnit Jupiter, Mockito, AssertJ. Việc đăng ký `AutoConfiguration.imports` ở `src/test/resources` chỉ ảnh hưởng test classpath và **không tự được đóng gói như main production resource**.

### 6.3. Main application

`src/main/java/com/example/slicelab/SliceLabApplication.java`:

```java
package com.example.slicelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceLabApplication.class, args);
    }
}
```

### 6.4. Service thật

`src/main/java/com/example/slicelab/CatalogService.java`:

```java
package com.example.slicelab;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    public String label(long id) {
        return "real-" + id;
    }
}
```

### 6.5. Controller thật

`src/main/java/com/example/slicelab/CatalogController.java`:

```java
package com.example.slicelab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class CatalogController {
    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/{id}")
    public ItemResponse item(@PathVariable long id) {
        return new ItemResponse(catalogService.label(id));
    }

    public record ItemResponse(String label) {}
}
```

Khi chạy app không mock và gọi `GET /catalog/7`, body JSON chứa `label="real-7"`. Service ở đây cố ý đơn giản; mục đích là cho thấy slice loại service khỏi component scan và phải cấp collaborator.

### 6.6. Ba value records trong test support

`src/test/java/com/example/testsupport/DiscoveryTag.java`:

```java
package com.example.testsupport;

public record DiscoveryTag(String value) {}
```

`src/test/java/com/example/testsupport/FeatureTag.java`:

```java
package com.example.testsupport;

public record FeatureTag(String value) {}
```

`src/test/java/com/example/testsupport/ExtraTag.java`:

```java
package com.example.testsupport;

public record ExtraTag(String value) {}
```

Records ở test source set chỉ nhằm đánh dấu bean đến từ auto-configuration nào; không là thành phần domain production.

### 6.7. Auto-configuration #1: chỉ được khám phá qua file metadata

`src/test/java/com/example/testsupport/DiscoveryAutoConfiguration.java`:

```java
package com.example.testsupport;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class DiscoveryAutoConfiguration {
    @Bean
    DiscoveryTag discoveryTag() {
        return new DiscoveryTag("broad-import");
    }
}
```

**Cần có file metadata** tại đúng đường dẫn:

`src/test/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung **một dòng, không thêm backticks hoặc dấu `#`:**

```text
com.example.testsupport.DiscoveryAutoConfiguration
```

Cơ chế `@EnableAutoConfiguration` sẽ nhìn thấy class này khi load test classpath. Nó **không** được import tường minh bởi các slice tests.

### 6.8. Auto-configuration #2: chỉ được nhập khi yêu cầu

`src/test/java/com/example/testsupport/FeatureAutoConfiguration.java`:

```java
package com.example.testsupport;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FeatureAutoConfiguration {
    @Bean
    FeatureTag featureTag() {
        return new FeatureTag("selective-import");
    }
}
```

**Không** thêm `FeatureAutoConfiguration` vào file `AutoConfiguration.imports` trên. Vì class nằm ngoài component scan và không có broad metadata registration, nó chỉ được chọn khi test ghi `@ImportAutoConfiguration(FeatureAutoConfiguration.class)` hoặc một cơ chế import tương đương.

### 6.9. Auto-configuration #3: dùng để kiểm `exclude`

`src/test/java/com/example/testsupport/ExtraAutoConfiguration.java`:

```java
package com.example.testsupport;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ExtraAutoConfiguration {
    @Bean
    ExtraTag extraTag() {
        return new ExtraTag("should-be-excluded");
    }
}
```

Cũng **không** đăng ký class này trong broad metadata file. Nó phục vụ test lựa chọn/exclusion ở phần dưới.

### 6.10. Test #1 — Full context khám phá auto-configuration mặc định

`src/test/java/com/example/slicelab/FullDiscoveryTest.java`:

```java
package com.example.slicelab;

import com.example.testsupport.DiscoveryTag;
import com.example.testsupport.FeatureTag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullDiscoveryTest {
    @Autowired ApplicationContext context;

    @Test
    void broadDiscoveryImportsOnlyRegisteredCandidate() {
        assertThat(context.getBean(DiscoveryTag.class).value())
                .isEqualTo("broad-import");
        assertThat(context.getBeansOfType(FeatureTag.class)).isEmpty();
    }
}
```

`@SpringBootTest` dùng cấu hình chính của app, với `@EnableAutoConfiguration` được bật bình thường. File `AutoConfiguration.imports` trong test classpath giới thiệu `DiscoveryAutoConfiguration`, nên có `DiscoveryTag`. `FeatureAutoConfiguration` không được đăng ký broad nên chưa được load.

`webEnvironment=NONE` chỉ có nghĩa **không khởi động web application context/server**; nó **không** tự tắt toàn bộ auto-configuration. Vì thế test này vẫn chứng minh đường broad import hoạt động.

### 6.11. Test #2 — MVC slice loại auto-configuration broad

`src/test/java/com/example/slicelab/WebMvcSliceTest.java`:

```java
package com.example.slicelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = CatalogController.class)
class WebMvcSliceTest {
    @Autowired ApplicationContext context;
    @Autowired MockMvc mvc;

    @MockitoBean CatalogService catalogService;

    @Test
    void sliceHasMvcButNotBroadDiscoveredTag() throws Exception {
        assertThat(context.containsBean("discoveryTag")).isFalse();
        assertThat(context.containsBean("featureTag")).isFalse();

        when(catalogService.label(7L)).thenReturn("mock-7");

        mvc.perform(get("/catalog/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.label").value("mock-7"));
    }
}
```

Kiểm thử khẳng định **MVC hoạt động** mà `DiscoveryAutoConfiguration` (chỉ có trong broad metadata) không xuất hiện. Việc có `MockMvc` dù broad auto-configuration bị tắt là nhờ bộ selective test auto-configurations của slice.

`@MockitoBean` cấp `CatalogService` để constructor của controller được inject. Không có annotation này, slice bình thường không scan service, nên có thể `Failed to load ApplicationContext` vì thiếu collaborator.

### 6.12. Test #3 — Bổ sung auto-configuration có chọn lọc vào slice

`src/test/java/com/example/slicelab/WebMvcImportTest.java`:

```java
package com.example.slicelab;

import com.example.testsupport.FeatureAutoConfiguration;
import com.example.testsupport.FeatureTag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;

@WebMvcTest(controllers = CatalogController.class)
@ImportAutoConfiguration(FeatureAutoConfiguration.class)
class WebMvcImportTest {
    @Autowired ApplicationContext context;
    @MockitoBean CatalogService catalogService;

    @Test
    void selectiveImportWorksAlthoughBroadDiscoveryDisabled() {
        assertThat(context.getBean(FeatureTag.class).value())
                .isEqualTo("selective-import");
        assertThat(context.containsBean("discoveryTag")).isFalse();
    }
}
```

Bài test vẫn mang `@WebMvcTest`, nên broad imports từ `@EnableAutoConfiguration` không chạy, nhưng `FeatureAutoConfiguration` được **nhập tường minh** và tạo bean `FeatureTag`. Đây là phép kiểm cốt lõi để hiểu hai annotation làm việc cùng nhau, không xung đột.

### 6.13. Test #4 — Tự dùng @OverrideAutoConfiguration với SpringBootTest

`src/test/java/com/example/slicelab/LeanSelectiveContextTest.java`:

```java
package com.example.slicelab;

import com.example.testsupport.DiscoveryTag;
import com.example.testsupport.FeatureAutoConfiguration;
import com.example.testsupport.FeatureTag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.OverrideAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@OverrideAutoConfiguration(enabled = false)
@ImportAutoConfiguration(FeatureAutoConfiguration.class)
class LeanSelectiveContextTest {
    @Autowired ApplicationContext context;

    @Test
    void disableBroadButKeepSelectedImportAndUserBeans() {
        assertThat(context.getBeansOfType(DiscoveryTag.class)).isEmpty();
        assertThat(context.getBean(FeatureTag.class).value())
                .isEqualTo("selective-import");

        // Tắt broad auto-configuration KHÔNG tắt component scan:
        assertThat(context.getBean(CatalogService.class)).isNotNull();
    }
}
```

**Bài học:** thêm `@OverrideAutoConfiguration(enabled=false)` ở test full context ngăn broad `DiscoveryAutoConfiguration`; `@ImportAutoConfiguration` vẫn nhập `FeatureAutoConfiguration`. Trong khi đó `CatalogService` vẫn do `@ComponentScan` của app tạo. Vì vậy test này **không đồng nghĩa** với một slice filter chuẩn: nó vẫn quét user components trong package ứng dụng.

Hãy dùng kiểu annotation thủ công này khi có lý do rõ, chẳng hạn muốn khảo sát behavior của một tập auto-configuration giới hạn. Trong phần lớn dự án, ưu tiên slice có sẵn vì meta-annotation của chúng đã được Spring Boot kiểm thử và duy trì.

### 6.14. Test #5 — Nhập hai auto-configurations nhưng loại một

`src/test/java/com/example/slicelab/ImportExclusionTest.java`:

```java
package com.example.slicelab;

import com.example.testsupport.ExtraAutoConfiguration;
import com.example.testsupport.ExtraTag;
import com.example.testsupport.FeatureAutoConfiguration;
import com.example.testsupport.FeatureTag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.OverrideAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@OverrideAutoConfiguration(enabled = false)
@ImportAutoConfiguration(
        classes = {FeatureAutoConfiguration.class, ExtraAutoConfiguration.class},
        exclude = ExtraAutoConfiguration.class)
class ImportExclusionTest {
    @Autowired ApplicationContext context;

    @Test
    void explicitExcludeWinsForListedAutoConfiguration() {
        assertThat(context.getBean(FeatureTag.class).value())
                .isEqualTo("selective-import");
        assertThat(context.getBeansOfType(ExtraTag.class)).isEmpty();
        assertThat(context.containsBean("discoveryTag")).isFalse();
    }
}
```

`classes` và `value` chỉ là hai tên cho danh sách import, **không dùng cả hai với hai danh sách khác nhau**. Trong test này, `ExtraAutoConfiguration` được liệt kê nhưng lại bị loại qua `exclude`, nên không có `ExtraTag`. Điều này cho thấy `exclude` tác động tới việc import auto-configuration chứ không phải xóa một bean đã được định nghĩa tùy ý ở nơi khác.

### 6.15. Chạy lệnh và đối chiếu kết quả

Trong thư mục `slice-autoconfig-lab` có JDK 17+ và Maven:

```bash
mvn -q clean test

mvn -q -Dtest=FullDiscoveryTest test
mvn -q -Dtest=WebMvcSliceTest test
mvn -q -Dtest=WebMvcImportTest test
mvn -q -Dtest=LeanSelectiveContextTest test
mvn -q -Dtest=ImportExclusionTest test
```

Các test trên được thiết kế PASS với cấu trúc file và dependency như mô tả. Khi `mvn test` thành công, Maven exit code **0**; log thời gian khởi động, context cache, số dòng output và warning có thể khác giữa môi trường. Không khẳng định output console cố định; những giá trị trong bảng dưới đây là **assertions được code kiểm**.

| Test | Broad-discovered `DiscoveryTag` | Selected `FeatureTag` | `ExtraTag` | MVC request |
| --- | --- | --- | --- | --- |
| `FullDiscoveryTest` | Có | Không | Không | Không test |
| `WebMvcSliceTest` | Không | Không | Không | HTTP mock 200, label `mock-7` |
| `WebMvcImportTest` | Không | Có | Không | Không gọi request |
| `LeanSelectiveContextTest` | Không | Có | Không | Web env NONE |
| `ImportExclusionTest` | Không | Có | Không | Web env NONE |

Có thể chạy ứng dụng thật bằng:

```bash
mvn spring-boot:run
```

Và tại terminal khác:

```bash
curl "http://localhost:8080/catalog/7"
```

Body chứa `{"label":"real-7"}`. Lưu ý hai records `DiscoveryTag`/`FeatureTag` chỉ có trong test source set nên **không tự xuất hiện** khi chạy executable application artifact từ main code. Phần minh họa broad discovery ở trên phụ thuộc test classpath và file metadata trong `src/test/resources`.

## 7. Cách import đúng khi mở rộng slice

### 7.1. Bổ sung auto-configuration: @ImportAutoConfiguration

Tài liệu Spring Boot khuyến nghị:

```java
@JdbcTest
@ImportAutoConfiguration(IntegrationAutoConfiguration.class)
class MyJdbcTests {
    // ...
}
```

Đây là **minh họa theo Spring Boot 3.5**; không thuộc project MVC ở mục 6. Khi một test slice cần thêm auto-configurations, dùng `@ImportAutoConfiguration` thay vì `@Import` cho chính auto-configuration class. Spring Boot áp dụng chính sách ordering/condition phù hợp hơn khi xử lý auto-config classes.

**Không kéo cả một bộ auto-configurations không liên quan** vào slice. Ví dụ nếu test chỉ kiểm JSON của controller, import messaging broker, batch, JDBC, JPA, scheduler và HTTP clients sẽ đánh mất ý nghĩa cô lập.

### 7.2. Bổ sung cấu hình Spring thường: @Import

Nếu controller test cần một custom `WebMvcConfigurer`, Jackson module, argument resolver hoặc `@TestConfiguration` do dự án viết, dùng:

```java
@WebMvcTest(CatalogController.class)
@Import(CustomMvcTestConfiguration.class)
class CatalogMvcTest {
    // ...
}
```

`CustomMvcTestConfiguration` là **tên minh họa**, không phải lớp nằm trong project mục 6. Đây là cách nhập **user configuration**, không phải auto-config candidate cần xử lý ordering.

Đừng dùng `@ImportAutoConfiguration` cho một class `@Service` vì nó không trở thành “auto-configuration” chỉ nhờ cách import. Dùng `@Import`/`@MockitoBean` hoặc thay đổi phạm vi test.

### 7.3. Bổ sung collaborator: @MockitoBean

`@WebMvcTest` không scan mọi service của app. Khi controller phụ thuộc `CatalogService`, cách hợp lý nhất để kiểm MVC contract là:

```java
@MockitoBean
CatalogService catalogService;
```

Field này tạo mock bean ngay trong test ApplicationContext. Đừng dùng Mockito `@Mock` thuần Java rồi mong Spring inject nó vào controller. Nếu muốn kiểm thực service cùng controller, cân nhắc `@Import(CatalogService.class)` hoặc `@SpringBootTest + @AutoConfigureMockMvc`, nhưng chú ý các dependencies của service.

### 7.4. Bổ sung @ConfigurationProperties

Với slice cần một properties holder do app định nghĩa:

```java
@WebMvcTest(CatalogController.class)
@EnableConfigurationProperties(CatalogProperties.class)
class CatalogPropertiesTest {
    // ...
}
```

Đây là ví dụ cú pháp; `CatalogProperties` phải được project định nghĩa và có binding annotations hợp lệ. Test slice thường không tự scan mọi `@ConfigurationProperties` beans trong ứng dụng. Cần đăng ký nó tường minh để binding thực sự diễn ra.

### 7.5. Điều chỉnh điều kiện thay vì import tùy tiện

Nếu một auto-configuration có `@ConditionalOnProperty(name="feature.enabled", havingValue="true")`, test chỉ định class mà thiếu property vẫn có thể không tạo bean. Để bật điều kiện:

```java
@WebMvcTest(
    controllers = CatalogController.class,
    properties = "feature.enabled=true")
@ImportAutoConfiguration(FeatureAutoConfiguration.class)
class FeatureEnabledMvcTest {
    // ...
}
```

Mẫu này minh họa nguyên tắc (class `FeatureAutoConfiguration` trong project mục 6 không có condition property). Kết quả với auto-configuration thật còn phụ thuộc tất cả conditions, không chỉ một property.

## 8. File metadata .imports và custom composed annotations

Một số `@AutoConfigure…` annotations trong Spring Boot dùng:

```java
@ImportAutoConfiguration
```

mà không ghi class trong annotation. Khi `classes` rỗng, Spring Boot có thể đọc các tên class từ file tương ứng:

```text
META-INF/spring/<fully-qualified-name-of-annotated-class>.imports
```

Ví dụ class annotation `com.example.testtools.AutoConfigureDemoFeature` có thể gắn:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ImportAutoConfiguration
public @interface AutoConfigureDemoFeature {}
```

Đây là **mẫu cú pháp**, không phải file chạy độc lập: cần import Java `ElementType`, `RetentionPolicy`, các annotations liên quan và đặt file resource như dưới đây để có tác dụng.

Tên file metadata:

```text
src/test/resources/META-INF/spring/com.example.testtools.AutoConfigureDemoFeature.imports
```

Nội dung có thể là:

```text
com.example.testtools.FeatureAutoConfiguration
# Comment được hỗ trợ
```

Nếu muốn khai báo một class **có thể không nằm trên classpath**, Spring Boot hỗ trợ tiền tố `optional:` trong file `@ImportAutoConfiguration` metadata imports. Hãy đối chiếu Javadoc phiên bản dùng và đừng lạm dụng optional để che thiếu dependency bắt buộc.

Cần phân biệt **hai tên file**:

| Tên file | Ai sử dụng? | Ý nghĩa |
| --- | --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | `@EnableAutoConfiguration` | Danh sách candidates rộng của app |
| `META-INF/spring/com.example.testtools.AutoConfigureDemoFeature.imports` | `@ImportAutoConfiguration` gắn trên annotation tương ứng | Danh sách được chọn cho annotation test/feature |

Nhầm hai file có thể khiến auto-configuration chỉ định bị load mọi nơi, hoặc **không load ở bất kỳ test nào**.

## 9. exclude: loại auto-configuration ở đúng tầng

Các cách thường thấy:

### 9.1. Exclude tại @ImportAutoConfiguration

```java
@ImportAutoConfiguration(
    classes = {FeatureAutoConfiguration.class, ExtraAutoConfiguration.class},
    exclude = ExtraAutoConfiguration.class)
```

Đây là phép loại trực tiếp của selective import. Không cần sửa production app.

### 9.2. Exclude qua thuộc tính của slice

Nhiều test slice hỗ trợ `excludeAutoConfiguration`. Ví dụ:

```java
@WebMvcTest(
    controllers = CatalogController.class,
    excludeAutoConfiguration = SomeAutoConfiguration.class)
class MvcWithoutOneAutoConfigTest {
    // ...
}
```

`SomeAutoConfiguration` là class minh họa cần tồn tại trong dự án thực tế; không phải file chạy độc lập. Ở Spring Boot 3.5, `WebMvcTest.excludeAutoConfiguration` là alias tới `@ImportAutoConfiguration.exclude` của slice.

### 9.3. Exclude broad auto-configuration

`@SpringBootApplication(exclude=...)` và property `spring.autoconfigure.exclude` tác động tới đường auto-configuration thông thường của ứng dụng; `@EnableAutoConfiguration` hỗ trợ exclusion. **Không xem các hình thức này là cơ chế thay thế hoàn toàn cho `@ImportAutoConfiguration.exclude` khi đang tùy chỉnh một test slice**. Chúng thuộc những entry points và scope khác nhau.

### 9.4. Exclude không phải “xóa bean”

Nếu một user configuration khác đã tạo `FeatureTag` bean (ví dụ `@Bean` trong `@TestConfiguration`), việc exclude `FeatureAutoConfiguration` không tự gỡ bean đó. Điều tương tự đúng với component scan: exclude auto-configuration class không tự chặn một `@Component` vô tình bị scan. Để debug, xác định **nguồn định nghĩa bean** trước khi lựa chọn exclude.

## 10. Conditional auto-configuration và thứ tự

### 10.1. `@AutoConfiguration` vẫn là configuration có conditions

Một auto-configuration thường khai báo:

```java
@AutoConfiguration(after = {DependencyAutoConfiguration.class})
@ConditionalOnClass(FeatureEngine.class)
class FeatureAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean
    FeatureFacade featureFacade() {
        return new FeatureFacade();
    }
}
```

Đây là **mẫu minh họa**, không phải chương trình hoàn chỉnh: `DependencyAutoConfiguration`, `FeatureEngine`, `FeatureFacade` là các kiểu do dự án cung cấp.

Các điểm chính:
- `@AutoConfiguration(after=...)` định nghĩa ordering **giữa các auto-configuration classes**, không phải thứ tự chắc chắn khi method business chạy.
- `@ConditionalOnClass` chỉ match khi class cần có mặt.
- `@ConditionalOnMissingBean` có thể back off nếu một bean phù hợp đã đăng ký.
- Dù `@ImportAutoConfiguration` chọn class, condition vẫn được xử lý bình thường.
- Nếu import một class mà dependency/condition cần thiết vắng mặt, một số bean không xuất hiện; đó không nhất thiết là bug framework.

### 10.2. Vì sao không dùng @Import cho auto-configurations?

Spring Boot test reference nói rõ: muốn bổ sung **auto-configurations** cho slice, sử dụng `@ImportAutoConfiguration`, **không dùng `@Import` thông thường** để import các class auto-configuration. Lý do: ordering, exclusions, candidate selection và conditional auto-configuration cần được xử lý theo đúng đường import của Boot.

Ngược lại, `@Import` phù hợp cho user config và specific Spring beans. Chọn đúng công cụ để không vô tình thay thứ tự đăng ký bean hoặc bỏ qua exclusions mong muốn.

### 10.3. Tại sao đôi khi import rồi vẫn thiếu bean?

Ví dụ một `@ConditionalOnMissingBean` bị ràng buộc bởi existing bean hoặc `@ConditionalOnClass` không match do thiếu dependency. Kiểm bằng Spring Boot condition evaluation report:

```text
Condition evaluation report
  Positive matches: ...
  Negative matches: ...
  Unconditional classes: ...
```

Khối trên là **mô tả dạng report**, không phải stdout chính xác. Bật `debug=true` trong cấu hình test hoặc logging phù hợp, rồi tìm **tên auto-configuration** và reason của match/no match. Đừng chỉ tra `context.getBean(...)` và đoán framework không xử lý annotation.

## 11. Chọn đúng slice trong ứng dụng thực tế

| Rủi ro cần kiểm | Test annotation | Auto-configurations thường cần | Có nên tự thêm @ImportAutoConfiguration? |
| --- | --- | --- | --- |
| HTTP routing, JSON, validation MVC | `@WebMvcTest` | MVC, MockMvc, JSON/security phù hợp | Chỉ khi cần thêm auto-config rất cụ thể |
| WebFlux controller/filters | `@WebFluxTest` | Reactive web pipeline, WebTestClient phù hợp | Có thể, nếu slice thiếu một auto-config cần kiểm |
| JPA mapping/repository | `@DataJpaTest` | JPA, transactions, embedded/test DB theo điều kiện | Có thể, khi cần thêm integration auto-config hợp lệ |
| JDBC/repository helper | `@JdbcTest` | JDBC, datasource, transaction | Có thể, theo ví dụ Spring Boot `IntegrationAutoConfiguration` |
| JSON serialization | `@JsonTest` | JSON mapper/testers | Thường không cần nếu chỉ kiểm mapping |
| Full context với external services | `@SpringBootTest` | Auto-config của app | Không thêm tùy tiện; chỉ khi custom specific needs |
| Custom framework test slice | Composed test annotation + filter + selective auto-config | Chính xác bộ infra đã thiết kế | Là thành phần quan trọng của custom slice |

Không đặt đồng thời hai test slice annotations như `@WebMvcTest` và `@DataJpaTest` lên một class để “cộng hai bộ slice”. Spring Boot không hỗ trợ cách kết hợp trực tiếp này. Hãy chọn một slice và bổ sung `@AutoConfigure…`/import cụ thể của tầng kia, hoặc dùng `@SpringBootTest` nếu cần tích hợp hai tầng thật.

### 11.1. Web MVC slice

`@WebMvcTest` chỉ quan tâm controller/MVC; nếu controller cần repository trực tiếp (thiết kế không lý tưởng), bạn có thể mock repository collaborator nhưng không chứng minh database behavior. Hãy sửa kiến trúc ranh giới controller/service khi có thể; unit test service và JPA slice test riêng.

### 11.2. JPA slice

`@DataJpaTest` tải repositories, entities, EntityManager và transactional test support theo cấu hình; việc vô tình import web/HTTP/broker auto-config vào JPA slice vừa tăng chi phí vừa che lỗi kiến trúc. Nếu cần DB production-like, dùng Testcontainers hoặc real test database theo cách phù hợp, chứ không “import thêm tất cả auto-config”.

### 11.3. JSON slice

`@JsonTest` dùng JSON mapper và testers phù hợp để xác nhận serialization. Không giả định vì một DTO serialize đúng trong JSON slice nên controller status, security hoặc full HTTP contract cũng đúng. Dùng `@WebMvcTest`/integration test cho ranh giới HTTP.

## 12. Những lỗi thường gặp và cách chẩn đoán

### 12.1. `NoSuchBeanDefinitionException` sau khi dùng @OverrideAutoConfiguration(false)

**Triệu chứng:** trước đây có datasource/codec/client, sau khi disable broad auto-configuration thì bean biến mất.

**Nguyên nhân:** bạn đã tắt đường `@EnableAutoConfiguration` rộng nhưng chưa import lại các auto-configurations cần thiết; hoặc bạn đã dùng custom context mà không có type-exclude filters/infrastructure đầy đủ.

**Cách xử lý:** xác định bean nào thật sự thuộc scope test. Với slice có sẵn, dùng đúng annotation; với custom test, import chính xác auto-configuration cần thiết cùng dependencies/conditions. Không đặt `@OverrideAutoConfiguration(enabled=true)` chỉ để mọi thứ tự động xuất hiện nếu mục tiêu vốn là cô lập slice.

### 12.2. @ImportAutoConfiguration được khai báo nhưng bean không xuất hiện

**Khả năng:**
- `@ConditionalOnClass` không match vì dependency vắng mặt.
- `@ConditionalOnProperty` đang false hoặc thiếu key.
- `@ConditionalOnMissingBean` back off vì có bean khác.
- `@ImportAutoConfiguration.exclude`/slice `excludeAutoConfiguration` loại class.
- Tên class import sai, source set chứa class không được biên dịch.
- File `.imports` liên kết sai fully qualified annotation name.
- User-defined config đã tạo bean/candidate khác.

**Sửa:** đọc condition report; kiểm classpath, property sources, exclusions, package boundaries. Nếu context fail, đọc `Caused by` gốc, không chỉ wrapper `Failed to load ApplicationContext`.

### 12.3. @WebMvcTest thiếu service

`@WebMvcTest` không scan `@Service` thông thường. Controller có constructor dependency làm context fail. Sửa bằng `@MockitoBean Service` nếu muốn kiểm MVC độc lập, hoặc `@Import(Service.class)` khi muốn service thật. `@ImportAutoConfiguration(Service.class)` không phải công cụ phù hợp để import service business.

### 12.4. Test slice vẫn load bean ngoài ý muốn

**Nguyên nhân:** App root class dùng explicit `@ComponentScan` mà không giữ type-exclude filter như mặc định; hoặc user `@Configuration`/`@Import` ép thêm bean; hoặc một component là MVC-related type được phép trong slice.

**Sửa:** kiểm app root scan configuration, test `@Import`, `@TestConfiguration`, packages và filters. Theo Spring Boot reference, nếu dùng explicit `@ComponentScan` trên application class, slice filters mặc định có thể bị bỏ qua; cần đăng ký lại `TypeExcludeFilter` phù hợp.

### 12.5. Test slice có security dù bạn muốn HTTP 200

`@WebMvcTest` hỗ trợ auto-configure Spring Security khi dependency tồn tại. Nhận 401/403 là tín hiệu request cần setup authentication/CSRF theo policy; không khẳng định “slice vô hiệu hóa security”. Dùng Spring Security Test `@WithMockUser` hoặc request post processors phù hợp. Chỉ tắt security/filter nếu yêu cầu của test thực sự loại trừ chúng, và bổ sung test riêng kiểm policy.

### 12.6. “Tôi đặt @Import thay @ImportAutoConfiguration nhưng vẫn chạy”

`@Import` có thể import một class configuration, nhưng làm vậy với auto-configuration không phải con đường được Boot khuyến nghị cho slice. Test có thể PASS tình cờ trong phiên bản và context cụ thể nhưng mất các bảo đảm liên quan auto-configuration ordering/exclusion. Hãy chuyển sang `@ImportAutoConfiguration` nếu đó thực sự là auto-config class. Với user config thông thường, tiếp tục dùng `@Import`.

### 12.7. “Disable auto-configuration” nhưng CatalogService vẫn có

`@OverrideAutoConfiguration(enabled=false)` **không tắt component scan**. `CatalogService` được `@Service` và app scan tạo nên vẫn còn trong `LeanSelectiveContextTest`. Muốn loại user components, cần type exclude filters hoặc cấu hình test có phạm vi scan phù hợp, như `@WebMvcTest`. Điều này khác cơ chế import auto-config candidates.

### 12.8. Import một auto-config kéo thêm cả chuỗi phụ thuộc

Tùy auto-configuration, condition có thể yêu cầu bean phụ thuộc; import một class được chọn có thể tạo thêm nhiều bean trong class đó, gây kết nối DB/broker hoặc thiếu secret. Giải pháp không phải luôn là import thêm dependency tiếp theo. Xác định mục tiêu test; nếu chỉ muốn một fake collaborator, `@MockitoBean`/`@TestConfiguration` thường hẹp hơn.

### 12.9. Context cache trở nên chậm khi mỗi test có import khác nhau

Spring TestContext cache key xét cấu hình, profiles, properties, context customizers, imports và bean overrides. Hai test dùng tập `@ImportAutoConfiguration` khác nhau có thể có contexts riêng; điều này đúng vì graph của chúng khác. Giữ các slice cùng mục tiêu có cấu hình nhất quán, ưu tiên unit tests cho logic không cần Spring và tránh lạm dụng `@DirtiesContext`.

### 12.10. Test pass trên máy dev, fail trên CI

Các khác biệt phổ biến:
- Classpath khác do dependency/profile/plugin.
- Test resource `META-INF/spring/...imports` không được copy.
- Thiếu environment variables khiến condition không match.
- Spring Boot version thay đổi danh sách slice auto-configurations hoặc package imports.
- JDK/DB/network và thứ tự chạy test.
- Một test toàn bộ context lưu lại state làm ô nhiễm test khác.

**Cách chẩn đoán:** chạy Maven/Gradle sạch, so `target/test-classes`, `dependency:tree`, condition report và lần context load đầu tiên fail. Không sửa bằng cách bật tất cả auto-configurations nếu test ban đầu có phạm vi rõ.

## 13. Hướng debug có thể lặp lại

### 13.1. Quan sát bean thật trong context

Trong test:

```java
@Autowired ApplicationContext context;

// Bên trong một @Test method:
assertThat(context.containsBean("featureTag")).isTrue();
assertThat(context.containsBean("discoveryTag")).isFalse();
```

Đây là đoạn **minh họa**; import AssertJ và ApplicationContext như các file chạy ở mục 6. Khi tên bean được tạo từ `@Bean` method, bạn cũng có thể kiểm `context.getBean(FeatureTag.class)`. Với nhiều bean cùng type, dùng `context.getBeansOfType(...)` hoặc chọn theo name.

### 13.2. Kiểm output resources và dependency

```bash
mvn -q clean test
mvn dependency:tree
```

Trong ví dụ, file `AutoConfiguration.imports` phải được copy vào:

```text
target/test-classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung file phải đúng FQCN `com.example.testsupport.DiscoveryAutoConfiguration`. File không nằm dưới `target/classes` vì đây là **test resource**, và đó là chủ ý để tránh tác động production.

### 13.3. Bật condition evaluation report khi cần

Có thể thêm property `debug=true` vào test Spring Boot hoặc sử dụng logging phù hợp để xem positive/negative matches của auto-configurations. Việc một bean không có mặt có thể là do **không được nhập** hoặc **được nhập nhưng condition false**; đây là hai nguyên nhân khác nhau.

Lọc log theo tên auto-configuration class và điều kiện thay vì đọc toàn bộ startup log không có cấu trúc.

### 13.4. Kết quả Maven Surefire

`mvn test` báo TEST FAILURE vì assertion mismatch và ERROR khi test context fail; đây chỉ là phân loại của test runner. Context fail có thể xảy ra trước body test. Lần fail tiếp theo với cùng context cache key có thể bị Spring TestContext failure threshold chặn; hãy đọc **lần đầu cùng context**. Đừng coi việc tăng threshold là cách chữa thiếu bean.

### 13.5. Cách viết phép kiểm bảo vệ boundary

Nên có ít nhất hai loại assertions:
- **Tính năng cần test**: ví dụ MVC request tới `/catalog/7` trả 200 và JSON label đúng.
- **Boundary của slice**: bean auto-config không liên quan không xuất hiện, trong khi bean cần thiết có mặt.

Một test chỉ assert `MockMvc` được autowire vẫn có thể bỏ sót việc vô tình import cả DB stack. Một test chỉ assert bean được import nhưng không gọi SUT vẫn có thể bỏ sót bug trong controller. Kết hợp kiểm tính năng và kiểm ranh giới ở những slice quan trọng.

## 14. Các tình huống không nên dùng hai annotation này

- **Logic thuần Java:** dùng JUnit + Mockito, tạo SUT bằng constructor, không tải Spring context.
- **Một service cần config nhỏ:** dùng `@TestConfiguration` và `@Import`, không cần viết custom auto-configuration nếu không có lợi ích.
- **Integration cần mọi bean thật:** `@SpringBootTest` với profile/test infrastructure phù hợp; tự disable broad auto-config có thể làm bài test không đại diện app.
- **Bài test chỉ cần một collaborator giả:** dùng `@MockitoBean`; không xây auto-config chỉ để tạo một mock.
- **Kiểm database mapping:** dùng `@DataJpaTest` có sẵn và DB test phù hợp; không viết lại từ đầu full `@OverrideAutoConfiguration` trừ khi đang phát triển một custom test slice framework.
- **Tắt một auto-config cụ thể trong slice:** dùng `excludeAutoConfiguration` hoặc `@ImportAutoConfiguration(exclude=...)`, thay vì tắt toàn bộ rồi tự khôi phục nhiều class.
- **Tối ưu hiệu năng qua “ít bean hơn” một cách mù quáng:** trước tiên xác định test boundary, hạ tầng setup, context reuse và bean graph thật.

## 15. Câu hỏi ôn tập có đáp án

1. **Vì sao `@WebMvcTest` có MockMvc dù broad auto-configuration bị tắt?** Vì annotation tích hợp các `@AutoConfigure…` và `@ImportAutoConfiguration` cho MVC/test infra, song song với type-exclude filters.
2. **`@OverrideAutoConfiguration(enabled=false)` có xóa `@Service` khỏi component scan không?** Không. Nó điều chỉnh đường `@EnableAutoConfiguration`, không tự đổi component scanning.
3. **Vì sao `@ImportAutoConfiguration(FeatureAutoConfiguration.class)` có thể tạo bean khi broad auto-config tắt?** Vì đây là **đường import chọn lọc độc lập**; class được xử lý theo rules và conditions của auto-configuration.
4. **Một auto-configuration đã được import có chắc sinh bean không?** Không. Condition không match hoặc một bean đã có có thể khiến nó back off.
5. **Dùng `@Import` hay `@ImportAutoConfiguration` để bổ sung `IntegrationAutoConfiguration` vào `@JdbcTest`?** Dùng `@ImportAutoConfiguration` theo tài liệu Spring Boot.
6. **Dùng gì để đưa custom `WebMvcConfigurer` configuration vào MVC slice?** Thường `@Import` một class `@Configuration`/`@TestConfiguration` phù hợp, không nhầm với auto-config candidate.
7. **Dùng gì để cấp `CatalogService` cho `CatalogController` trong `@WebMvcTest`?** Thường `@MockitoBean`; dùng `@Import` nếu thực sự cần service thật.
8. **Vì sao `FullDiscoveryTest` thấy `DiscoveryTag` còn `WebMvcSliceTest` không?** Full test dùng broad `@EnableAutoConfiguration` và file `AutoConfiguration.imports`; MVC slice tắt broad path.
9. **Tại sao `WebMvcImportTest` vẫn thấy `FeatureTag`?** Vì nhập riêng `FeatureAutoConfiguration` bằng `@ImportAutoConfiguration`.
10. **`exclude` của `@ImportAutoConfiguration` có gỡ user-created bean cùng type không?** Không; nó loại một auto-configuration khỏi import, không xóa các bean definitions khác.
11. **Có thể dùng `@WebMvcTest` và `@DataJpaTest` cùng lớp để cộng hai slices?** Không được Spring Boot hỗ trợ; chọn một slice và thêm cấu hình phù hợp hoặc dùng full-context.
12. **Khi file custom metadata imports không chạy, kiểm gì?** Đường dẫn, FQCN, output `target/test-classes`, annotation gắn trên class, classpath và conditions.
13. **Vì sao direct `@ComponentScan` trên app root có thể làm slice load quá nhiều?** Vì nó có thể vô hiệu hóa các exclude filters mà `@SpringBootApplication` được thiết kế để cung cấp cho slicing.
14. **Khi nào nên dùng `@OverrideAutoConfiguration` trực tiếp?** Khi thiết kế test context/slice rất cụ thể và hiểu cần import/configure lại gì; thường các slice có sẵn đã làm việc đó.
15. **Phải kiểm cái gì sau khi thêm custom auto-config cho slice?** Bean mục tiêu có mặt, bean không liên quan vẫn vắng mặt, và behavior của SUT chạy đúng.

## 16. Checklist trước khi merge một test slice

- [ ] Đã chọn đúng loại slice (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`…) thay vì tự viết cấu hình từ đầu?
- [ ] Phân biệt rõ auto-config broad với selective import và user bean scan?
- [ ] Biết `@OverrideAutoConfiguration(enabled=false)` **không** tắt component scan?
- [ ] Biết `@ImportAutoConfiguration` vẫn xét conditions và ordering?
- [ ] Chỉ nhập auto-configurations thật sự cần, không kéo cả hệ thống vào test?
- [ ] Khi cần mock service/controller collaborator, đã dùng `@MockitoBean` đúng bean?
- [ ] Khi cần import user `@Configuration`, đã dùng `@Import` đúng mục đích?
- [ ] Nếu cần properties, đã cấu hình `@EnableConfigurationProperties`/property sources phù hợp?
- [ ] Nếu có exclusion, đã xác định đúng auto-config class thay vì cố xóa một bean không cùng nguồn?
- [ ] Nếu metadata `.imports` được dùng, path/FQCN có đúng và nằm trong output resources không?
- [ ] Đã kiểm slice có/không có các bean phù hợp bằng `ApplicationContext` hoặc condition report?
- [ ] Có test behavior thực (HTTP/JSON/query) thay vì chỉ assert “context loads”?
- [ ] Security, transaction và hạ tầng ngoài đã được test trong đúng boundary?
- [ ] Test có chạy trong Maven/Gradle sạch, không chỉ IDE?
- [ ] Không đặt hai slice annotations lên cùng một class?
- [ ] Sau khi chỉnh cấu hình, đã so tốc độ/context cache và chạy lại suite liên quan?

**Kết luận:** `@OverrideAutoConfiguration(enabled=false)` đóng cửa **auto-configuration discovery diện rộng**, còn `@ImportAutoConfiguration` mở lại **những auto-configurations được lựa chọn**. Một test slice tốt cần thêm **component-scan boundary** và **test infrastructure phù hợp**, để bài test kiểm đúng một phần ứng dụng mà không vô tình kéo theo các subsystem ngoài phạm vi.

## 17. Tài liệu chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications, mục Auto-configured Tests / Additional Auto-configuration and Slicing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 Javadoc — `@OverrideAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/OverrideAutoConfiguration.html
- Spring Boot 3.5 Javadoc — `@ImportAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html
- Spring Boot 3.5 Javadoc — `@WebMvcTest` (bao gồm meta-annotations và `excludeAutoConfiguration`): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html
- Spring Boot 3.5 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Javadoc — `@EnableAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- Spring Framework — TestContext Framework context caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- JUnit Jupiter User Guide: https://docs.junit.org/5.11.4/user-guide/
