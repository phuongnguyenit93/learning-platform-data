# TypeExcludeFilter, component scan và nguyên nhân bean ngoài phạm vi xuất hiện

Một trong những lợi ích lớn của **test slice** trong Spring Boot là chỉ dựng phần `ApplicationContext` cần thiết cho một loại kiểm thử. Ví dụ, `@WebMvcTest` hướng tới controller và hạ tầng Spring MVC, không phải toàn bộ service, repository, scheduler hay HTTP client của ứng dụng. Thế nhưng đôi khi một test gắn `@WebMvcTest` hoặc `@DataJpaTest` vẫn khởi tạo những bean “lạc phạm vi”: service nghiệp vụ, cấu hình kết nối mạng, background job, datasource không mong muốn. Hệ quả là context khởi động chậm, thiếu dependency, kết nối dịch vụ ngoài, test lỗi do configuration production hoặc mất tính cô lập.

Một nguyên nhân rất dễ bỏ sót là **component scanning đã được tùy biến khiến các bộ lọc slice không còn được áp dụng như dự kiến**. Spring Boot có cơ chế `TypeExcludeFilter` làm cầu nối giữa cấu hình test slice và quá trình quét component. Nhưng bộ lọc này **không phải tường lửa chống mọi cách đăng ký bean**: các nguồn `@Import`, method `@Bean`, auto-configuration, bean override, hoặc một lệnh quét khác vẫn có thể đưa bean vào context.

Bài này giải thích cơ chế, dấu hiệu, cách debug và cách sửa có chủ đích, với ví dụ runnable **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5**. Nếu dùng Boot 4.x, một số package và danh sách thành phần MVC đã thay đổi; hãy tham chiếu tài liệu API của **đúng phiên bản** thay vì sao chép nguyên xi import trong ví dụ.

**Kết quả học tập:** sau bài này bạn có thể chỉ ra bean được đăng ký bằng đường nào, hiểu vai trò của `TypeExcludeFilter`, phân biệt “bean hợp lệ trong slice” với “bean bất thường”, sửa lỗi `@ComponentScan`, chọn `@Import`/`@MockitoBean` đúng mục đích và xác nhận một test slice thực sự cô lập phần không liên quan.

## 1. “Test slice” là gì, và nó không phải là gì?

Spring Boot cung cấp những annotation test chuyên biệt để nạp **một lát cắt** của application context cùng tập auto-configuration thích hợp. Điển hình:

| Annotation | Mục tiêu | Thành phần trọng tâm | Thứ thường không cần có |
|---|---|---|---|
| `@WebMvcTest(Controller.class)` | Kiểm tra mapping HTTP, JSON, validation, MVC/security filter theo cấu hình | Controller được chọn, controller advice, các phần MVC được cho phép, `MockMvc` | Service nghiệp vụ, repository, message consumer, scheduled job |
| `@DataJpaTest` | Kiểm tra entity mapping, repository JPA, query, DB constraint | JPA/repository/data source và hạ tầng persistence cần thiết | REST controller, các service ứng dụng không liên quan |
| `@JsonTest` | Kiểm tra serialize/deserialize JSON | JSON mapper/module/tester liên quan | Full web server, service và database |
| `@RestClientTest` | Kiểm tra adapter REST client | HTTP client, serialization và mock server phù hợp | Full server/API controller, domain workflow không liên quan |
| `@SpringBootTest` | Kiểm thử Spring Boot context rộng/tích hợp | Tùy ứng dụng và `webEnvironment` | **Không phải slice**; có thể nạp nhiều thành phần |

Slice giúp tốc độ và phạm vi kiểm chứng rõ hơn, nhưng không có nghĩa **chỉ đúng một bean** tồn tại. Một `@WebMvcTest` hợp lệ vẫn có thể nạp `@ControllerAdvice`, `Filter`, `WebMvcConfigurer`, `HandlerMethodArgumentResolver` hoặc auto-configuration cho converter/security. Những bean này **có thể thuộc MVC slice**, không phải “rò rỉ”.

Ngược lại, nếu `PaymentReconciliationJob` hoặc `InventorySyncService` bỗng được tạo dù bài test chỉ muốn kiểm JSON controller, cần điều tra cách đăng ký bean.

**Câu hỏi đầu tiên khi debug:** bean đó vốn có quyền xuất hiện trong slice không, hay nó thực sự nằm ngoài boundary mà test định kiểm tra?

## 2. Component scanning trong ứng dụng bình thường

Spring Framework phát hiện nhiều bean từ classpath bằng component scan. Những kiểu stereotype thường được xem xét gồm `@Component`, `@Service`, `@Repository`, `@Controller`, `@Configuration` và annotation tự định nghĩa có meta-annotation tương ứng.

Ví dụ:

```java
package com.example.sliceaudit;

import org.springframework.stereotype.Component;

@Component
public class ExternalBillingClient {
    public String preview(long reportId) {
        return "external:" + reportId;
    }
}
```

Trong full application context có component scan bao trùm package này, `ExternalBillingClient` có thể thành bean. **Dòng code không có network call** ở ví dụ: tên class chỉ đại diện một adapter hạ tầng, để test không vô tình gọi dịch vụ thật.

`@SpringBootApplication` bao gồm ba khả năng chính: `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Nếu đặt application class ở package gốc như `com.example.sliceaudit`, mặc định Spring Boot quét package đó cùng các package con.

Cú pháp thường thấy:

```java
@SpringBootApplication
public class SliceAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceAuditApplication.class, args);
    }
}
```

Đây là **đoạn header minh họa**; file Java runnable ở phần 9 có đầy đủ package và import.

Điểm quan trọng: **component scan** là một **cơ chế đăng ký bean**, không phải cơ chế duy nhất. `@Bean` trong class cấu hình được import, auto-configuration, `ImportBeanDefinitionRegistrar` hoặc Spring TestContext bean override có thể tạo bean mà không cần class implementation được component scan phát hiện.

## 3. `TypeExcludeFilter` là gì?

`org.springframework.boot.context.TypeExcludeFilter` là cơ sở để **loại một số candidate type trong quá trình component scan của Boot**. Trong bối cảnh test slice, những bộ lọc chuyên biệt (ví dụ `WebMvcTypeExcludeFilter`) sử dụng thông tin từ annotation test để quyết định thành phần nào phù hợp.

Hãy xem nó như cơ chế gắn **quy tắc loại kiểu** từ test slice vào quá trình quét component:

```text
JUnit / @WebMvcTest(ReportController.class)
              |
              v
Spring Boot test bootstrapper
              |
              +--> slice metadata + type-exclude filters
              |
              v
@SpringBootApplication component scanning
              |
              +--> TypeExcludeFilter  ---> evaluate scan candidates
              |                             |
              |                       MVC-allowed type?
              |                         /       \
              |                       yes       no
              |                        |         |
              |                     register   exclude
              |
              v
ApplicationContext được dựng cùng auto-configuration của slice
```

Sơ đồ trên là mô hình **khái niệm**, không phải trình tự callback/stack trace chính xác cho mọi phiên bản. Bộ lọc còn dựa vào annotation, include/exclude filter và bootstrap data.

Các phân biệt bắt buộc:

- `TypeExcludeFilter` là **lọc ở tầng candidate component scanning**; nó không tự động xóa bean đã đăng ký từ mọi nguồn khác.
- `WebMvcTypeExcludeFilter` là một filter cụ thể cho `@WebMvcTest` trong Spring Boot 3.5, liên quan tập MVC component được phép.
- `@DataJpaTest` có filter phù hợp với data slice; không sử dụng một danh sách MVC để xác định entity/repository.
- `@WebMvcTest` còn **giới hạn auto-configuration** được áp dụng; đó là một trục khác với component scanning.
- Test slice không đạt được isolation chỉ bằng `TypeExcludeFilter`; nó cần **đúng bootstrapper, đúng scan và đúng auto-configuration**.

Trong Spring Boot 3.5, JavaDoc `WebMvcTypeExcludeFilter` mô tả nó là filter cho `@WebMvcTest`. Mặc dù nó làm việc trong quá trình quét, không nên tạo instance filter thủ công trong một test business thông thường.

## 4. Vì sao `@SpringBootApplication` có thể bảo toàn slice filtering?

`@SpringBootApplication` không chỉ là viết tắt cho một `@ComponentScan` trống. Spring Boot thiết lập những exclude filter dùng cho cơ chế Boot, trong đó có `TypeExcludeFilter`; nhiều nhánh phiên bản còn có `AutoConfigurationExcludeFilter` để tránh các auto-configuration class bị component scan nhầm.

Có thể hình dung ý tưởng:

```java
// Minh họa phần ý tưởng annotation, KHÔNG phải định nghĩa thật của Boot.
@ComponentScan(excludeFilters = {
    @ComponentScan.Filter(
        type = FilterType.CUSTOM,
        classes = TypeExcludeFilter.class),
    @ComponentScan.Filter(
        type = FilterType.CUSTOM,
        classes = AutoConfigurationExcludeFilter.class)
})
```

**Không cần sao chép đoạn annotation này** vào ứng dụng khi bạn chỉ dùng `@SpringBootApplication` bình thường. Các loại filter và chi tiết source code cần đối chiếu với Spring Boot version đang cài; đoạn trên là cách biểu diễn cơ chế trong các nhánh 3.x.

Chính nhờ default scan có exclude filter phù hợp, khi `@WebMvcTest` bootstrap context, bộ lọc slice có thể hạn chế các bean `@Service`, `@Repository` hoặc `@Component` không thuộc MVC. Dù application class vẫn được tìm thấy để cung cấp cấu hình gốc, context của test không nhất thiết nạp hết bean production.

## 5. Bẫy lớn nhất: khai báo `@ComponentScan` trực tiếp trên application class

Một thay đổi tưởng vô hại:

```java
// PHẢN VÍ DỤ: đừng thay root class của dự án demo bằng code này.
@SpringBootApplication
@ComponentScan("com.example.sliceaudit")
public class SliceAuditApplication {
}
```

Người viết muốn chỉ rõ base package, nhưng `@ComponentScan` **được khai báo trực tiếp** trên class có thể có ưu tiên với meta-annotation scan của `@SpringBootApplication`, khiến default exclude filters của Boot **không được dùng cho lệnh scan trực tiếp này**. Spring Boot reference cảnh báo rõ: test slices có thể bắt đầu scan các component hoặc configuration production ngoài phạm vi.

Hệ quả thường gặp:

1. Test `@WebMvcTest(ReportController.class)` nhận cả `ReportService`, `ExternalBillingClient` hoặc những component ngoài MVC.
2. Test `@DataJpaTest` gặp service/scheduler hoặc configuration không thuộc JPA.
3. Bean ngoài scope có constructor hoặc `@Bean` yêu cầu property production, queue hoặc network client, nên context fail trước khi bất kỳ test method nào chạy.
4. Suite bỗng chạy chậm, nhiều cache entries và side effects khó giải thích.

**Vấn đề không phải tên package tự thân.** Vấn đề là lệnh scan mới **không mang đầy đủ cơ chế loại trừ** mà Boot đặt trên default scan. Việc base package trùng hệt package gốc cũng không bảo đảm nó tương đương cấu hình mặc định.

### 5.1. Cách sửa ưu tiên: bỏ scan trực tiếp không cần thiết

Nếu package ứng dụng đã nằm ở gốc của các package con, chỉ dùng:

```java
@SpringBootApplication
public class SliceAuditApplication {
}
```

Đây là snippet minh họa; xem code đầy đủ ở phần 9. Cách này giữ nguyên cấu hình quét mặc định, đơn giản và dễ review nhất.

### 5.2. Nếu chỉ muốn đổi base package, dùng alias của Boot

```java
@SpringBootApplication(scanBasePackages = "com.example.sliceaudit")
public class SliceAuditApplication {
}
```

`scanBasePackages` là alias của thuộc tính component scan trên `@SpringBootApplication`, nên giữ được những filter đã được Boot cấu hình trên annotation tổng hợp. Nếu cần type-safe, dùng `scanBasePackageClasses`. Lưu ý: các alias này **không tự mở rộng `@EntityScan` hoặc Spring Data repository scanning**; đó là cơ chế khác.

### 5.3. Nếu bắt buộc dùng `@ComponentScan` trực tiếp

Khi thật sự cần advanced include/exclude filters, có thể cấu hình lại filter của Boot cho lệnh scan tùy chỉnh:

```java
// Mẫu hướng dẫn cho Spring Boot 3.x: chỉ dùng khi có lý do.
@SpringBootApplication
@ComponentScan(
    basePackages = "com.example.sliceaudit",
    excludeFilters = {
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = TypeExcludeFilter.class),
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = AutoConfigurationExcludeFilter.class)
    })
public class SliceAuditApplication {
}
```

Đoạn này **không phải file runnable độc lập**: cần imports từ `org.springframework.boot.autoconfigure`, `org.springframework.boot.context` và `org.springframework.context.annotation`, plus method `main`. Tên/filter thực tế phải đối chiếu version; lựa chọn **an toàn và ít rủi ro nhất là tránh tạo lệnh scan tùy chỉnh nếu không cần**.

Hơn nữa, đặt filter ở **một `@ComponentScan`** không tự sửa **những `@ComponentScan` khác** đến từ cấu hình nhập sau đó. Khi nhiều nguồn scan tồn tại, phải xem từng nguồn.

## 6. Phân biệt “scan làm lọt bean” với “bean được đăng ký trực tiếp”

Đây là bước chẩn đoán quan trọng nhất. Một bean ngoài phạm vi có thể xuất hiện mà **không hề được component scan chọn**.

| Đường vào context | Có phải candidate của component scan? | Vì sao slice filter chưa chắc chặn? |
|---|---|---|
| `@Service`/`@Component` được quét bởi default scan | Có | Filter slice thường có cơ hội loại nếu scan đã đăng ký filter đúng |
| `@Service` được quét bởi một `@ComponentScan` riêng | Có, nhưng từ lệnh scan khác | Lệnh scan đó có thể không mang `TypeExcludeFilter` |
| `@Import(SomeService.class)` | Đăng ký tường minh | Không phải kết quả tự nhiên của bộ lọc trên component scan |
| `@Import(WholeConfig.class)` | Class cấu hình được import trực tiếp | Những `@Bean` bên trong có thể được tạo dù bean không thuộc slice |
| `@Bean` trong configuration đã nạp | Bean được tạo theo factory method | Filter của component scan không kiểm từng sản phẩm `@Bean` như candidate component |
| Auto-configuration được Boot chọn | Cơ chế auto-configuration | Slice giới hạn auto-configuration riêng; không phải chỉ bằng `TypeExcludeFilter` |
| `@MockitoBean` trong test (Spring 6.2+) | Bean override hoặc tạo mock | Mock có thể tồn tại do test yêu cầu, không phải do scan |
| `@TestConfiguration` được import | Test-specific config | Bean cố ý được thêm; cần review phạm vi nhập |
| `@Enable...` hoặc registrar | Đăng ký bằng cơ chế framework | Có thể đăng ký bean ngoài scan thông thường |

Vì vậy **“context có bean X” không đủ chứng minh `TypeExcludeFilter` hỏng**. Cần xác định **đường đăng ký**.

Ví dụ: với `@WebMvcTest`, một field:

```java
@MockitoBean
ReportService reportService;
```

có thể tạo mock `ReportService` trong context vì controller cần dependency đó. Đây là kết quả **cố ý** của test. Nó **không có nghĩa `@Service` thật đã lọt qua component scan**. Muốn kiểm tra, hãy xem `Mockito.mockingDetails(reportService).isMock()` và xác định những bean không được cấu hình bởi mock/import.

## 7. Bean nào hợp lệ trong một `@WebMvcTest`?

Theo Spring Boot 3.5, `@WebMvcTest` tự cấu hình Spring MVC và giới hạn các bean quét được về một tập phục vụ MVC, có thể bao gồm:

- `@Controller`, `@ControllerAdvice`;
- `@JsonComponent` và JSON-related components được version đó hỗ trợ;
- `Converter`, `GenericConverter`;
- Servlet `Filter`;
- `HandlerInterceptor`, `WebMvcConfigurer`, `WebMvcRegistrations`;
- `HandlerMethodArgumentResolver`;
- Các thành phần bổ sung được đưa vào bởi test configuration và auto-configuration phù hợp.

Nếu Spring Security nằm trên classpath, security filter chain và các bean security liên quan có thể xuất hiện theo test setup. **Đừng xóa/tắt security chỉ để làm slice “ít bean hơn”** nếu API cần được bảo vệ. Hãy dùng test security setup/`@WithMockUser` hoặc CSRF fixture theo version/dependency và contract.

Điểm tinh tế: một bean có class tên `PaymentAuthFilter` nhưng implement servlet `Filter` có thể được xem là **MVC infrastructure** và được include đúng quy tắc. Tên “Payment” không tự làm nó bất hợp lệ. Nếu nó có dependency đắt hoặc side effect, đó có thể là vấn đề thiết kế filter/scan: nên tách logic ngoài MVC sang collaborator và mock/đưa fixture đúng boundary.

### 7.1. `@WebMvcTest(ReportController.class)` vẫn cần dependency controller

Dù controller được chọn, service của nó **thường không được tự scan**, nên context có thể báo `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` nếu controller constructor yêu cầu service.

Giải pháp thông thường:

```java
@WebMvcTest(ReportController.class)
class ReportControllerWebTest {
    @MockitoBean
    ReportService reportService;
}
```

Đây là **snippet**; test đầy đủ nằm ở phần 10. Trong Boot 3.3 và một số nhánh cũ dùng `@MockBean`; trong Boot 3.4+/Spring Framework 6.2+, `@MockitoBean` là cơ chế khuyến nghị. Không dùng `@SpringBootTest` chỉ để “sửa” dependency thiếu nếu thật ra bạn muốn một MVC slice.

## 8. Tại sao `@DataJpaTest` có thể thấy service và scheduler?

`@DataJpaTest` có mục tiêu kiểm thử persistence. Nó thường sử dụng JPA-related auto-configuration, repository, entity mapping và database test thích hợp; nhiều bài test có transaction rollback mặc định.

Nếu một service/job production xuất hiện, có thể do:

1. `@ComponentScan` trực tiếp trên application root vô hiệu hóa filter mặc định của slice.
2. Một `@Configuration` ngoài phạm vi được import, kéo theo `@ComponentScan` hoặc `@Bean` khác.
3. `@EnableJpaRepositories`, `@EntityScan`, một auto-configuration được bổ sung hoặc framework registrar đưa thêm thành phần theo cơ chế riêng.
4. Test tự nhập service/config hoặc đặt cấu hình kiểm thử quá rộng.
5. Test thực ra dùng `@SpringBootTest` hoặc một composed annotation đã thêm full bootstrap.

**Entity và Spring Data repository không phải chỉ là các class `@Component` bình thường.** JPA entities, repository interface, entity scanning và repository registration có cơ chế riêng. Đừng nghĩ sửa `TypeExcludeFilter` sẽ tự khắc phục mọi vấn đề entity/repository package.

Ví dụ một cấu hình không nên import chỉ để thử một JPA repository:

```java
// PHẢN VÍ DỤ CHO SLICE HẸP: nạp cả cấu hình ứng dụng.
@DataJpaTest
@Import(EntireApplicationInfrastructureConfiguration.class)
class OrderRepositoryTest {
}
```

Đây là snippet không độc lập. Cấu hình được import có thể tạo HTTP client, queue consumer hoặc scheduler; những bean ấy xuất hiện **vì được import**, không nhất thiết do default component scan sai.

## 9. Ví dụ runnable: project Spring Boot 3.5.x, Java 17+

Ta tạo một ứng dụng rất nhỏ để quan sát ba trạng thái:

1. **Full context** có service và adapter thông thường.
2. **MVC slice đúng** có controller thật, service dưới dạng **Mockito mock do test yêu cầu**, và **không có adapter ngoài MVC**.
3. **MVC slice nhập thêm configuration** có một bean ngoài MVC được thêm **cố ý** — chứng minh `TypeExcludeFilter` không chặn mọi hình thức đăng ký.

Ví dụ dùng class/package tên `com.example.sliceaudit`. Nếu sao chép vào project khác, đổi toàn bộ package nhất quán.

### 9.1. Cây thư mục

```text
src/main/java/com/example/sliceaudit/
    SliceAuditApplication.java
    ExternalBillingClient.java
    ReportService.java
    ReportController.java

src/test/java/com/example/sliceaudit/
    ReportControllerWebTest.java
    FullContextControlTest.java
    ExtraSliceConfig.java
    ImportedExtraBeanWebTest.java
```

Các file này phù hợp với Spring Boot 3.5.x + `spring-boot-starter-web` + `spring-boot-starter-test`, không cần datasource hoặc external network.

### 9.2. Application root giữ scan mặc định

**`src/main/java/com/example/sliceaudit/SliceAuditApplication.java`**

```java
package com.example.sliceaudit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceAuditApplication.class, args);
    }
}
```

**Không khai báo `@ComponentScan` trực tiếp** trên application class. Với package root đã đúng, đây là cấu hình tối thiểu, dễ tương thích test slices.

### 9.3. Adapter ngoài MVC: không có network call trong demo

**`src/main/java/com/example/sliceaudit/ExternalBillingClient.java`**

```java
package com.example.sliceaudit;

import org.springframework.stereotype.Component;

@Component
public class ExternalBillingClient {

    public String preview(long id) {
        return "external:" + id;
    }
}
```

Dù tên là client, implementation demo chỉ trả chuỗi, không mở kết nối. Trong ứng dụng thật, adapter có thể dùng HTTP/SDK; test slice nên tránh tạo những collaborator không liên quan.

### 9.4. Service nghiệp vụ phụ thuộc adapter

**`src/main/java/com/example/sliceaudit/ReportService.java`**

```java
package com.example.sliceaudit;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ExternalBillingClient billingClient;

    public ReportService(ExternalBillingClient billingClient) {
        this.billingClient = billingClient;
    }

    public String describe(long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        return billingClient.preview(id).toUpperCase(Locale.ROOT);
    }
}
```

Nếu service được tạo trong **full context**, nó cần `ExternalBillingClient` thật. Trong MVC slice, service này **không phải thành phần cần scan**; ta chỉ cần mock collaborator tại boundary của controller.

### 9.5. REST controller và response record

**`src/main/java/com/example/sliceaudit/ReportController.java`**

```java
package com.example.sliceaudit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/{id}")
    public ReportView get(@PathVariable long id) {
        return new ReportView(id, reportService.describe(id));
    }

    public record ReportView(long id, String description) {
    }
}
```

`ReportController` được lựa chọn bởi `@WebMvcTest`; JSON serialization của `record` được Jackson hỗ trợ trong Spring Boot 3.5 với starter-web. Trong full context, controller gọi service thật.

## 10. Test MVC slice chuẩn: kiểm HTTP và chứng minh adapter không được scan

**`src/test/java/com/example/sliceaudit/ReportControllerWebTest.java`**

```java
package com.example.sliceaudit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReportController.class)
class ReportControllerWebTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @MockitoBean
    ReportService reportService;

    @Test
    void keepsMvcBoundaryAndExcludesUnrelatedAdapter()
            throws Exception {
        when(reportService.describe(7L)).thenReturn("fixture-7");

        mvc.perform(get("/api/reports/7"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.id").value(7),
                        jsonPath("$.description").value("fixture-7"));

        verify(reportService).describe(7L);

        assertEquals(0, context.getBeanNamesForType(
                ExternalBillingClient.class).length);
        assertTrue(mockingDetails(
                context.getBean(ReportService.class)).isMock());
    }
}
```

**Ba điều được chứng minh tách biệt:**

- Controller/MVC thật mapping `GET /api/reports/7` và serialize JSON có `id=7`, `description="fixture-7"`.
- `ExternalBillingClient` **không được tạo thành bean** trong MVC slice này; không có lý do để thử adapter ngoài MVC trong bài test HTTP mapping.
- `ReportService` **có bean trong context**, nhưng đó là **Mockito mock do `@MockitoBean` thêm**, không phải `@Service` thật được component scan chọn. `mockingDetails(...).isMock()` giúp tránh kết luận sai khi rà soát bean list.

`@WebMvcTest` thường auto-configure `MockMvc`; không cần mở HTTP server thật. Test không kiểm logic `ReportService.describe` — điều đó thuộc unit/integration test của service.

**Nếu project bật Spring Security**, request có thể cần principal/authorization tùy chính sách. Ví dụ runnable giả định dependencies như ở mục 16, không thêm `spring-boot-starter-security`. Đừng tắt security trong bài test sản phẩm thật nếu quyền truy cập là một phần contract.

## 11. Đối chiếu: full context có service và adapter thật

**`src/test/java/com/example/sliceaudit/FullContextControlTest.java`**

```java
package com.example.sliceaudit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = SliceAuditApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullContextControlTest {

    @Autowired
    ReportService service;

    @Autowired
    ExternalBillingClient billingClient;

    @Test
    void createsRegularComponentsInFullContext() {
        assertEquals("external:7", billingClient.preview(7));
        assertEquals("EXTERNAL:7", service.describe(7));
    }
}
```

Test này không phải MVC slice. Nó xác nhận full application context đăng ký service và adapter theo scan mặc định.

**Điểm học tập:** cùng bộ class production, `@WebMvcTest` và `@SpringBootTest` cho **hai context khác nhau một cách có chủ ý**. Việc service không có trong slice dưới dạng implementation thật **không phải lỗi**, và việc service có trong full context cũng không phải “lọt phạm vi”.

Nếu test đang có lỗi do application context rất nặng, nên lựa chọn loại test theo điều muốn kiểm tra thay vì bắt tất cả dùng `@SpringBootTest`.

## 12. Đối chiếu thứ hai: `@Import` tạo bean ngoài scan hợp lệ

Ta cố ý đăng ký một bean không thuộc MVC bằng `@Import`. Nó không phải `@Component`, và bản thân nó không nằm trong tập MVC component scan.

**`src/test/java/com/example/sliceaudit/ExtraSliceConfig.java`**

```java
package com.example.sliceaudit;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class ExtraSliceConfig {

    @Bean
    ExtraBackgroundJob extraBackgroundJob() {
        return new ExtraBackgroundJob();
    }
}

class ExtraBackgroundJob {
    String mode() {
        return "intentionally-imported";
    }
}
```

`ExtraBackgroundJob` là một class package-private chỉ để học; method `mode()` không có side effect. `@TestConfiguration` nằm ở test sources và **không cần scan** để được dùng khi có `@Import`.

**`src/test/java/com/example/sliceaudit/ImportedExtraBeanWebTest.java`**

```java
package com.example.sliceaudit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;

@WebMvcTest(ReportController.class)
@Import(ExtraSliceConfig.class)
class ImportedExtraBeanWebTest {

    @MockitoBean
    ReportService reportService;

    @Autowired
    ApplicationContext context;

    @Test
    void explicitImportRegistersBeanOutsideMvcComponentScan() {
        assertEquals("intentionally-imported",
                context.getBean(ExtraBackgroundJob.class).mode());
    }
}
```

**Kết quả kỳ vọng:** test xanh, dù `ExtraBackgroundJob` không thuộc component scan MVC. Đây là kết quả **đúng theo `@Import`**, không phải chứng minh filter sai.

Điều đáng lo trong dự án thật là `@Import(EntireInfrastructureConfig.class)` có thể kéo theo nhiều `@Bean`: datasource, background executor, client gọi network, scheduler. Vì vậy **chỉ import những bean/config cần thiết**, tránh “nhập cả package” hoặc import toàn bộ application configuration để chữa một dependency thiếu của slice.

## 13. Khi `@Import` hoặc `@Bean` làm nhiều bean xuất hiện

Một ví dụ thường gặp: cấu hình được import vào test slice để lấy một `WebMvcConfigurer`, nhưng class đó cũng cung cấp datasource và HTTP client:

```java
// PHẢN VÍ DỤ MANG TÍNH MINH HỌA, không phải file chạy.
@Configuration
class MixedInfrastructureConfig {
    @Bean WebMvcConfigurer mvcConfigurer() { /* ... */ }
    @Bean DataSource dataSource() { /* ... */ }
    @Bean RemoteGateway remoteGateway() { /* ... */ }
}

@WebMvcTest(MyController.class)
@Import(MixedInfrastructureConfig.class)
class MyControllerTest {
}
```

Đây **không phải code độc lập**: class `MyController`, `RemoteGateway`, `DataSource`, method body và imports chưa được định nghĩa. Nó minh họa rủi ro cấu hình chứa quá nhiều trách nhiệm.

**Cách sửa phù hợp:** tách `MvcOnlyConfiguration` với `@Bean WebMvcConfigurer` và `DatabaseConfiguration` với datasource/DB. `@Import(MvcOnlyConfiguration.class)` trong MVC slice sẽ rõ ràng hơn và không kéo theo DB.

Phân biệt:

- `includeFilters` của `@WebMvcTest` cho phép thêm một số candidate scan phù hợp khi muốn mở rộng có chủ đích.
- `@Import` trực tiếp thêm class cấu hình/bean và có thể kéo theo dependencies.
- `@ImportAutoConfiguration` được dùng khi cần thêm auto-configuration theo cơ chế Boot, **không nên thay nó bằng `@Import` bừa bãi** đối với auto-configuration class.
- `@MockitoBean` thêm/thay mock bean để cung cấp một collaborator cần cho controller; nó không kiểm tra logic của bean thật.

Điểm chung: **mọi mở rộng slice phải có lý do gắn với contract đang được kiểm tra**.

## 14. `includeFilters`, `excludeFilters` và `useDefaultFilters`

`@WebMvcTest` (Boot 3.5) có các thuộc tính điều khiển việc chọn component được quét, như `controllers`, `includeFilters`, `excludeFilters` và `useDefaultFilters`.

Ví dụ cú pháp:

```java
// Minh họa việc cố ý thêm một component trong slice.
@WebMvcTest(
    controllers = ReportController.class,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = SpecialMvcAdapter.class))
class SpecializedMvcTest {
}
```

Đây **không phải file biên dịch độc lập**; `SpecialMvcAdapter` chưa khai báo, và cần import annotation/enum. Cách này có thể đưa thêm bean vào slice (tùy phạm vi scan). Vì vậy, khi thấy bean lạ, hãy xem **các includeFilters được đặt ngay trên test annotation**.

Ngược lại, `excludeFilters` có thể loại component không muốn. Nhưng **đừng bắt đầu debug bằng cách thêm excludeFilter ngẫu nhiên để giấu bean**. Nếu root cause là một `@ComponentScan` riêng làm mất bộ lọc mặc định, cần sửa gốc scan; nếu bean được đưa vào qua `@Bean`/`@Import`, component-scan exclude không phải giải pháp đủ.

`useDefaultFilters=false` làm thay đổi cách nhận các candidate mặc định trong test slice. Nó không biến context thành “không có bean nào”, vì infrastructure/auto-configuration/import vẫn có thể tạo bean. Chỉ dùng khi hiểu chính xác bộ type cần giữ.

**Lưu ý version:** danh sách default includes và loại bean được hỗ trợ có thể đổi qua các bản Boot. Khi một test sau nâng cấp có bean khác trước, kiểm tra API của `@WebMvcTest` trong đúng phiên bản trước khi gọi là regression.

## 15. Tìm root configuration và cấu hình lồng nhau

Nếu test chỉ ghi:

```java
@WebMvcTest(ReportController.class)
class ReportControllerWebTest {
}
```

Spring Boot thường tìm application configuration bằng cách duyệt package của test lên package cha để tìm `@SpringBootApplication` hoặc `@SpringBootConfiguration`. **Application class tìm thấy có thể mang các annotation cấu hình khác** như `@Import`, `@EnableScheduling` hoặc một `@ComponentScan` tùy chỉnh. Điều đó ảnh hưởng context slice dù bạn không viết các annotation ấy trên test class.

Những nguồn cần xem khi debug:

1. Lớp application root được Boot tìm thấy.
2. `@ComponentScan` trực tiếp và các meta-annotation trên root.
3. `@Import`, `@ImportAutoConfiguration`, `@Enable...` trên root.
4. `@Configuration` lồng nhau hoặc class cấu hình được import.
5. Annotation test riêng (`@WebMvcTest` include/exclude), `@TestConfiguration` và bean override.

**Một trường hợp tinh tế:** nested `@Configuration` trong một Spring Boot test có thể được dùng làm cấu hình chính của test theo quy tắc bootstrap, còn nested `@TestConfiguration` thường thêm vào cấu hình chính. Đừng dùng annotation cấu hình lồng nhau theo cảm tính rồi suy ra Boot vẫn đang tìm và dùng đúng root như trước.

Khi muốn chủ động chỉ định root, dùng `classes` ở những annotation hỗ trợ hoặc cấu hình test rõ ràng, **nhưng không biến một slice test thành full context** chỉ vì chọn nguồn cấu hình quá rộng.

## 16. Gradle và lệnh chạy ví dụ

Dự án ví dụ ở mục 9–12 dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5, Mockito**. Trong một Gradle project đã cấu hình Spring Boot plugin/BOM và repositories, cần phần dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn bổ sung**, không phải `build.gradle` hoàn chỉnh (phần plugins/versions/repositories cần theo project). Nếu đã có các starter trên, không khai báo lặp.

Chạy từ project có Gradle wrapper:

```bash
./gradlew test --tests com.example.sliceaudit.ReportControllerWebTest --tests com.example.sliceaudit.FullContextControlTest --tests com.example.sliceaudit.ImportedExtraBeanWebTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.sliceaudit.ReportControllerWebTest --tests com.example.sliceaudit.FullContextControlTest --tests com.example.sliceaudit.ImportedExtraBeanWebTest
```

Ở Gradle multi-project, thay `test` bằng task test của module thực tế. Với code và configuration đúng như đã mô tả, **ba test method dự kiến pass**, Gradle thông báo `BUILD SUCCESSFUL`. Đây là **kết quả kỳ vọng khi đọc mã**, không phải tuyên bố đã chạy chúng trên một repository được cung cấp. Các snippet gắn nhãn PHẢN VÍ DỤ hoặc minh họa không độc lập **không được tạo thành file trong project runnable**.

Kỳ vọng cụ thể:

- `ReportControllerWebTest`: HTTP 200, JSON `id=7` và `description=fixture-7`; `ExternalBillingClient` không có bean; `ReportService` trong context là Mockito mock.
- `FullContextControlTest`: full context có `ExternalBillingClient`, service trả `EXTERNAL:7`.
- `ImportedExtraBeanWebTest`: `ExtraBackgroundJob` có trong MVC slice **do `@Import`** và trả `intentionally-imported`.

JUnit test không in stdout nghiệp vụ cố định. Thông báo Gradle và log context có thể khác theo cấu hình. Báo cáo thường ở `build/reports/tests/test/index.html`, dữ liệu XML ở `build/test-results/test/` của module.

## 17. Mô phỏng bug `@ComponentScan` để thấy test mất isolation

Bạn có thể học bằng cách **đọc** hai cấu hình sau; không nên sửa application chính trong dự án production để thử tùy tiện.

**Cấu hình bình thường:**

```java
@SpringBootApplication
class DemoApplication { }
```

**Cấu hình đáng nghi:**

```java
@SpringBootApplication
@ComponentScan("com.example.sliceaudit")
class DemoApplication { }
```

Nếu app root dùng cấu hình đáng nghi, những bài `@WebMvcTest` hoặc `@DataJpaTest` có thể quét thêm component ngoài phạm vi do lệnh scan trực tiếp không giữ default exclude filters.

**Dấu hiệu test có thể xảy ra khi thay cấu hình:**

- Test controller trước kia chỉ cần `@MockitoBean ReportService`, nhưng giờ `ExternalBillingClient` thật xuất hiện.
- Test đụng dependency/properties của component ngoài MVC.
- Startup time cao lên; test cần nhiều mock hơn chỉ để dựng context.
- Component test-specific hoặc configuration không mong đợi bị quét.

Không phải mọi bản cấu hình đều biểu hiện giống nhau. Khi có cả bean thật và mock cùng type, framework có thể xử lý bean override hoặc ném lỗi mơ hồ, tùy cấu hình test. **Không đưa ra kết luận chỉ từ một exception cuối; cần xem bean definition và cơ chế đăng ký.**

**Cách sửa:** gỡ lệnh scan dư thừa; nếu cần đổi base package, dùng `@SpringBootApplication(scanBasePackages = ...)`; với scans bổ sung bắt buộc, cấu hình filters có chủ đích và viết test chứng minh isolation.

## 18. Chẩn đoán: bean vào context từ đâu?

Có ba mức quan sát:

### 18.1. Mức an toàn: nhìn loại bean và hành vi

Trong test, có thể inject `ApplicationContext` và hỏi:

```java
// Đoạn code đặt trong @Test; context là ApplicationContext.
String[] names = context.getBeanNamesForType(
        ExternalBillingClient.class);
assertEquals(0, names.length);
```

Điều này chứng minh bean **không được đăng ký theo type** trong context như đang xét. Nó không chứng minh bộ lọc nào đã loại bean hay lý do ban đầu.

Nếu muốn phân biệt mock:

```java
boolean isMockitoMock =
        Mockito.mockingDetails(context.getBean(ReportService.class))
                .isMock();
assertTrue(isMockitoMock);
```

Cần import `org.mockito.Mockito`, `assertTrue` và dùng trong test class có `context` đã inject. Đây là **đoạn minh họa**, không phải Java class độc lập.

### 18.2. Mức chi tiết: bean definition và nguồn đăng ký

Với `ConfigurableApplicationContext`/`BeanFactory` phù hợp, có thể tìm `BeanDefinition` theo bean name và xem metadata như `getResourceDescription()`, `getFactoryBeanName()`, `getFactoryMethodName()` hoặc source nếu có:

```java
// Đoạn minh họa để debug, không phải file độc lập.
ConfigurableListableBeanFactory factory =
        configurableContext.getBeanFactory();

BeanDefinition definition =
        factory.getBeanDefinition("externalBillingClient");

System.out.println(definition.getResourceDescription());
System.out.println(definition.getFactoryMethodName());
```

Cần imports cho `ConfigurableApplicationContext`, `ConfigurableListableBeanFactory` và `BeanDefinition`; biến `configurableContext` phải có đúng kiểu. Metadata **có thể null hoặc không đủ để kết luận chính xác mọi đường đăng ký**, nên cần kết hợp log và code cấu hình.

Đừng để debug code này ở production hoặc tự động dump mọi bean/properties lên log CI: có thể gây noise hoặc lộ dữ liệu cấu hình nhạy cảm.

### 18.3. Mức framework: logging có chọn lọc

Có thể tăng log cho Spring configuration/classpath scanning khi debug:

```properties
logging.level.org.springframework.context.annotation=DEBUG
logging.level.org.springframework.boot.test.autoconfigure=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
```

Đây là **gợi ý cấu hình tạm**; log chính xác tùy phiên bản và logger. Không đảm bảo một logger sẽ in lý do của từng candidate. Quan trọng nhất là tìm **scan nào**, **root configuration nào**, **import nào**, và **bean definition nào** đã đưa bean vào context.

Khi test fail với `Failed to load ApplicationContext`, tìm **root cause** trong các `Caused by` liên quan đến bean creation, không chỉ dừng ở exception ngoài cùng.

## 19. Quy trình tìm lỗi không làm mất giá trị test

Nếu một test slice bỗng có service ngoài phạm vi:

1. **Xác nhận annotation thực sự dùng.** `@WebMvcTest` hay `@SpringBootTest`? Có composed annotation nào thêm full context không?
2. **Xem loại bean.** Nó là `@ControllerAdvice`/`Filter` hợp lệ hay `@Service`/job/hạ tầng ngoài MVC?
3. **Tìm Spring root config.** Boot đang tìm `@SpringBootApplication` nào? Có scan/import đặc biệt không?
4. **Rà từng lệnh `@ComponentScan`.** Lệnh trực tiếp trên root, trong config được import, trong meta-annotation riêng? Có `TypeExcludeFilter` trong excludeFilters khi cần không?
5. **Rà những đường khác.** `@Import`, `@Bean`, `@ImportAutoConfiguration`, `@Enable...`, test `@MockitoBean` hoặc factory đăng ký bean.
6. **Xem phạm vi scan.** `basePackages`/`basePackageClasses` có quét nhiều module hoặc test sources không?
7. **Sửa tại nguồn nhỏ nhất.** Bỏ scan thừa, tách config hỗn hợp, import đúng bean hoặc dùng alias của Boot.
8. **Thêm assertion về isolation nếu có giá trị.** Ví dụ kiểm tra adapter mạng không hiện diện trong MVC slice quan trọng.
9. **Chạy test slice và một vài integration tests.** Bảo đảm sửa scan không vô tình làm production thiếu bean.
10. **Quan sát runtime/context cache.** Test nhanh trở lại chỉ là một dấu hiệu; vẫn phải assert contract chức năng.

Một checklist ngắn cho code review:

- [ ] Root `@SpringBootApplication` có `@ComponentScan` trực tiếp không cần thiết không?
- [ ] Có `@Import` một class cấu hình quá rộng trong test slice không?
- [ ] Có test-only mock/bean khiến bean lạ hiện diện **có chủ đích** không?
- [ ] Một class `Filter`/`ControllerAdvice` được phép xuất hiện hay thực sự là dependency sai?
- [ ] Mỗi dependency thiếu được giải quyết bằng double/import đúng boundary, không bằng full app scan?
- [ ] Cần test adapter riêng cho HTTP/DB thay vì ép nó vào MVC slice?
- [ ] Các assertion cuối cùng vẫn bảo vệ hành vi HTTP/persistence chứ không chỉ `contextLoads`?

## 20. Những hiểu lầm thường gặp

**“`@WebMvcTest` chỉ chứa controller.”** Sai. Nó cần MVC infrastructure và một số loại bean liên quan, cộng những bean được test import/mock/auto-configure phù hợp.

**“Có bean `@Service` trong `@WebMvcTest` nghĩa là filter hỏng.”** Chưa chắc. Bean có thể là Mockito mock từ `@MockitoBean` hoặc được import trực tiếp.

**“`TypeExcludeFilter` loại mọi bean ngoài slice.”** Sai. Nó chủ yếu tham gia **component scanning**. `@Bean`, `@Import`, auto-configuration và registrar không nhất thiết đi qua cùng bước candidate scanning.

**“Cứ thêm `@ComponentScan` lên root cho rõ package.”** Dễ phá cơ chế mặc định của Boot nếu không giữ các filters. Thường chỉ cần đặt application class ở đúng root hoặc dùng `scanBasePackages`.

**“Thêm `excludeFilters` vào test chắc chắn sửa được.”** Chưa chắc. Nếu bean được import hoặc được tạo qua `@Bean`, một filter scan không phải công cụ thích hợp.

**“Để test pass, chuyển `@WebMvcTest` thành `@SpringBootTest`.”** Có thể làm context nạp nhiều bean hơn, tốn thời gian hơn, che mất ranh giới thiết kế. Chỉ chuyển khi mục tiêu thật sự cần full integration.

**“Fake/mock service bằng `@MockitoBean` luôn là sai.”** Không. Trong MVC slice test, mock service để kiểm controller contract là hợp lý; không được dùng kết quả ấy để kết luận service business logic đã đúng.

**“Test slice chứng minh toàn bộ ứng dụng chạy đúng.”** Không. Phải có unit, adapter, integration và contract tests phù hợp để bảo vệ những phần ngoài slice.

**“Một profile test bảo đảm không có kết nối ra ngoài.”** Không. Một bean lạc phạm vi do scan/import vẫn có thể khởi tạo hoặc gọi network. Cần thiết kế adapter và môi trường test an toàn.

## 21. Bài tập thực hành

### Bài A — nhận diện root cause

Một dự án có:

```java
@SpringBootApplication
@ComponentScan({"com.example.app", "com.example.shared"})
class App {
}
```

Bài `@DataJpaTest` bỗng tạo `NotificationScheduler` và đòi API key. Hãy trả lời:

1. Scan nào đáng nghi nhất?
2. Vì sao test slice có thể mất khả năng loại bean?
3. Hai cách sửa nào không làm bạn phải đưa scheduler vào test?

**Đáp án định hướng:** `@ComponentScan` trực tiếp trên app root đáng nghi vì có thể thay thế scan mặc định chứa exclude filters. Ưu tiên bỏ direct scan hoặc dùng `@SpringBootApplication(scanBasePackages=...)`; nếu cần scan tùy chỉnh nâng cao, đảm bảo filters thích hợp và xét mọi scan khác.

### Bài B — mock service không có nghĩa service thật được quét

Trong `@WebMvcTest` có:

```java
@MockitoBean
ReportService service;
```

Đồng thời `ApplicationContext.getBean(ReportService.class)` trả một object. Có thể kết luận `@Service` thật đã lọt qua scan không? Nên kiểm chứng điều gì?

**Đáp án:** Không. `@MockitoBean` có thể tạo/thay mock. Kiểm tra `Mockito.mockingDetails(bean).isMock()` và nguồn bean definition/scan nếu thực sự cần phân biệt.

### Bài C — `@Import` làm bean lạ xuất hiện

Vì sao `ExtraBackgroundJob` của phần 12 có trong MVC slice dù nó không có `@Controller`, `@Filter` hoặc `WebMvcConfigurer`?

**Đáp án:** Do `@Import(ExtraSliceConfig.class)` đăng ký configuration có method `@Bean`. Bean này không cần được chọn bởi MVC component scan.

### Bài D — sửa cấu hình lẫn trách nhiệm

Một `AllInfrastructureConfig` chứa `@Bean` cho `WebMvcConfigurer`, datasource, email sender, Kafka client. Team import cả class vào `@WebMvcTest` chỉ để lấy một converter. Hãy tách cấu hình thành những class nhỏ hơn và xác định class nào nên được import. Giải thích tại sao `excludeFilters` trên scan không giải quyết triệt để bean do `@Bean` tạo.

### Bài E — đâu là bean hợp lệ?

Một MVC slice có `GlobalExceptionAdvice`, `RequestIdFilter`, `WebMvcConfigurer` và `OrderReconciliationJob`. Ba bean đầu có thể hợp lệ tùy cấu hình và mục tiêu test; bean job thường đáng điều tra. Hãy nêu cách kiểm tra mỗi bean được đăng ký qua scan, import hay auto-configuration.

### Bài F — viết regression test cho isolation

Dựa trên `ReportControllerWebTest`, bổ sung một class `@Component PaymentWebhookPoller` không liên quan MVC và assertion `context.getBeanNamesForType(PaymentWebhookPoller.class).length == 0`. Sau đó phân tích điều gì có thể xảy ra nếu ai đó thêm direct `@ComponentScan` trên root app.

## 22. Lựa chọn thiết kế cho dự án Spring Boot nhiều module

Trong monolith hoặc modular monolith, việc “quét mọi package” bằng một `@ComponentScan` rộng có thể kéo cả những module không liên quan vào một slice. Càng nhiều module, hậu quả càng khó nhận biết.

Gợi ý kiến trúc:

- Đặt `@SpringBootApplication` ở package gốc hợp lý của phạm vi ứng dụng.
- Nếu mở rộng scan, ưu tiên alias `scanBasePackageClasses` của `@SpringBootApplication` để giữ Boot defaults và tránh chuỗi package dễ sai.
- Không đặt cùng một configuration class mọi bean cho MVC, database, messaging, scheduling và security.
- Với module chỉ có một adapter, định nghĩa configuration riêng để import có chủ đích khi cần.
- Chia unit test cho service/domain, slice test cho controller/repository và integration test cho wiring/transaction thật.
- Duy trì test đảm bảo các **external adapters** không được khởi tạo trong những test slice có tính cô lập quan trọng.
- Tránh các test override/import khác nhau tùy tiện khiến context cache phân mảnh và CI chậm.
- Khi nâng Spring Boot, review lại annotation type/package và danh sách MVC types được phép, không chỉ thay version dependency.

Sự cô lập của slice là một **công cụ thiết kế và hiệu năng**, không phải một cuộc thi giảm số bean xuống thấp nhất. Mục tiêu là nạp **đúng thành phần cần kiểm chứng**, cùng infrastructure tối thiểu phù hợp, rồi giữ test nhanh và đáng tin.

## 23. Tổng kết và checklist cuối cùng

Hãy nhớ mô hình ba câu hỏi:

**1. Bean này có nên có trong slice không?** Với `@WebMvcTest`, controller/advice/filter/converter có thể hợp lệ; service nghiệp vụ và scheduled job thường không thuộc mục tiêu.

**2. Bean này được đăng ký bằng đường nào?** Default component scan, custom component scan, `@Import`, `@Bean`, auto-configuration, bean override, hay registrar? `TypeExcludeFilter` không kiểm soát tất cả những đường ấy.

**3. Cách sửa nào giữ đúng boundary?** Bỏ `@ComponentScan` dư thừa, dùng alias của `@SpringBootApplication`, chia nhỏ config, import đúng phần, hoặc dùng `@MockitoBean` cho collaborator MVC. Chỉ chuyển sang full integration test khi mục tiêu cần.

Checklist xác nhận:

- [ ] Test có annotation slice phù hợp, không vô tình dùng full `@SpringBootTest`.
- [ ] Root application configuration được tìm đúng package.
- [ ] Component scan không vô tình thay bộ lọc mặc định của Boot.
- [ ] Nếu có nhiều `@ComponentScan`, tôi đã xem **từng nguồn scan**.
- [ ] Tôi phân biệt filter candidate type với auto-configuration, import và bean factory.
- [ ] Tôi không gọi bean hợp lệ của MVC là “lọt phạm vi” chỉ vì tên class.
- [ ] Tôi phân biệt mock bean do test tạo với implementation thật được scan.
- [ ] Tôi không import một cấu hình hạ tầng quá rộng chỉ để lấy một bean nhỏ.
- [ ] Tôi không dùng scan exclude để chữa một bean được tạo trực tiếp từ `@Bean`.
- [ ] Test còn kiểm tra mapping/JSON/data contract, không chỉ `contextLoads`.
- [ ] Không mở kết nối thật hay làm side effect ngoài phạm vi khi khởi tạo slice.
- [ ] Unit/integration/adapter test khác bảo vệ những logic mà slice cố tình không chạy.
- [ ] Khi thất bại, tôi tìm root cause, source của bean definition và các annotation cấu hình, thay vì mock thêm mọi dependency để test xanh.

**Thông điệp cốt lõi:** `TypeExcludeFilter` giúp Spring Boot **giữ ranh giới component scanning** cho test slices; một `@ComponentScan` trực tiếp hoặc một nguồn đăng ký bean khác có thể làm context chứa những thành phần không mong đợi. Cần xác định **đường vào của bean** trước khi sửa. Một slice tốt không chỉ nhanh: nó nói rõ mình đang kiểm tra phần nào và cố tình không kiểm tra phần nào.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications, *Auto-configured Tests* và *User Configuration and Slicing*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 API — `SpringBootApplication`, `scanBasePackages` và `scanBasePackageClasses`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html
- Spring Boot 3.5 API — `WebMvcTypeExcludeFilter`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTypeExcludeFilter.html
- Spring Boot 3.5 — How-to Testing, import configuration có chủ đích: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- Spring Framework 6.2 — Classpath Scanning and Managed Components: https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html
