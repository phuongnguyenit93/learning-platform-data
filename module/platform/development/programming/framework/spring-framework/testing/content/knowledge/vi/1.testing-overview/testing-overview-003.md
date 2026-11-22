# Vai trò của Spring Test bên cạnh JUnit và thư viện assertion

Khi kiểm thử một ứng dụng Spring, có ba câu hỏi khác nhau cần được trả lời:

1. Ai phát hiện và chạy từng test, quản lý vòng đời của test?
2. Ai chuẩn bị môi trường Spring mà đoạn code cần để hoạt động, chẳng hạn ApplicationContext, dependency injection, transaction hoặc hạ tầng web?
3. Ai kiểm tra kết quả thực tế có đúng với mong đợi hay không?

JUnit, Spring Test và thư viện assertion đảm nhiệm ba nhóm trách nhiệm đó. Chúng phối hợp với nhau trong cùng một test, nhưng không thay thế nhau. Hiểu ranh giới này giúp chọn đúng loại test, tránh khởi động toàn bộ ứng dụng khi chỉ cần kiểm tra một class, đồng thời vẫn kiểm chứng được những hành vi phụ thuộc vào container Spring.

## Ba thành phần, ba trách nhiệm

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| JUnit | Tổ chức và thực thi test: nhận diện test, gọi lifecycle, chạy test case, hỗ trợ parameterized test và extension | `@Test`, `@BeforeEach`, `@AfterEach`, `@ParameterizedTest` |
| Spring Test | Kết nối test với cơ chế của Spring: tạo và quản lý ApplicationContext, inject bean vào test, thiết lập profile/property, transaction và tiện ích kiểm thử web | `@SpringJUnitConfig`, `@ContextConfiguration`, `@ActiveProfiles`, `MockMvc` |
| Assertion library | Diễn đạt điều kiện mong đợi và so sánh kết quả thực tế với điều kiện đó | JUnit Assertions, AssertJ, Hamcrest |

JUnit trả lời câu hỏi “test nào cần chạy và chạy theo thứ tự/lifecycle nào?”. Spring Test trả lời “test cần một môi trường Spring như thế nào?”. Assertion library trả lời “kết quả này có đúng không?”.

Một test có thể sử dụng cả ba: JUnit gọi phương thức test; Spring Test chuẩn bị bean và môi trường; phương thức test gọi đối tượng cần kiểm tra rồi dùng AssertJ để xác nhận kết quả.

~~~mermaid
flowchart TD
    A["JUnit Jupiter phát hiện và chạy test"] --> B["SpringExtension tích hợp với JUnit"]
    B --> C["Spring Test chuẩn bị TestContext và ApplicationContext"]
    C --> D["Inject bean / cấu hình môi trường test"]
    D --> E["Test gọi hành vi cần kiểm tra"]
    E --> F["Assertion kiểm tra kết quả"]
~~~

### JUnit: khung thực thi test

JUnit là nền tảng kiểm thử Java. Với JUnit Jupiter, lập trình viên đánh dấu phương thức bằng `@Test`, chuẩn bị dữ liệu bằng `@BeforeEach`, dọn dẹp bằng `@AfterEach`, nhóm test bằng nested test hoặc chạy nhiều bộ dữ liệu bằng parameterized test.

JUnit không tự hiểu cách tạo một Spring ApplicationContext chỉ vì test đang kiểm tra một service có `@Service`. Nếu test cần dependency injection hoặc cần cấu hình Spring, một integration point phải kết nối JUnit với Spring. Spring Test cung cấp integration point đó.

JUnit cũng có assertion cơ bản như `assertEquals`, `assertTrue` và `assertThrows`. Vì vậy, một test JUnit hoàn toàn có thể chạy mà không cần AssertJ hay Hamcrest.

### Spring Test: môi trường và tích hợp Spring

Spring Test là phần hỗ trợ kiểm thử của Spring Framework. Nó giúp test sử dụng các khả năng mà ứng dụng thật dựa vào, ví dụ:

- Nạp cấu hình và tạo ApplicationContext để các bean được khởi tạo theo quy tắc của Spring.
- Inject bean vào chính class test.
- Kích hoạt profile và property dành riêng cho môi trường test.
- Quản lý transaction cho test, thường cho phép rollback dữ liệu sau khi test kết thúc.
- Cung cấp công cụ kiểm thử tầng web như MockMvc và WebTestClient.
- Kết nối các bước chuẩn bị, thực thi và dọn dẹp test thông qua TestContext Framework và các test execution listener.

Spring Test không quyết định test có đúng hay sai. Nó chuẩn bị điều kiện để test có thể thực hiện hành vi cần kiểm chứng.

### Assertion library: diễn đạt kỳ vọng

Assertion library làm cho điều kiện kiểm tra rõ ràng và dễ đọc. Ví dụ, JUnit có thể viết:

~~~java
assertEquals(new BigDecimal("110.00"), actual);
~~~

Với AssertJ, có thể viết:

~~~java
assertThat(actual).isEqualByComparingTo("110.00");
~~~

Hamcrest thường diễn đạt kỳ vọng bằng matcher:

~~~java
assertThat(actual, is(equalTo(expected)));
~~~

Các thư viện này tập trung vào việc diễn đạt và kiểm tra kết quả. Chúng không tự khởi động Spring, không tự inject bean và không tự tạo transaction. Một dự án có thể dùng assertion của JUnit, AssertJ, Hamcrest hoặc kết hợp tùy nhu cầu.

## Spring Test tích hợp với JUnit như thế nào?

Spring Test có thể kết nối với JUnit Jupiter thông qua `SpringExtension`. Extension này tham gia vào lifecycle của JUnit và ủy quyền các công việc liên quan đến Spring cho TestContext Framework. Nhờ vậy, test có thể nhận bean từ ApplicationContext giống như một thành phần được Spring quản lý.

Cách khai báo trực tiếp thường gồm `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`. Spring cũng cung cấp annotation kết hợp `@SpringJUnitConfig`, giúp khai báo ngắn gọn hơn.

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(InvoiceTest.TestConfig.class)
class InvoiceTest {

    @Autowired
    private InvoiceService invoiceService;

    @Test
    void calculatesTotalWithTax() {
        var total = invoiceService.total(new BigDecimal("100.00"));

        assertThat(total).isEqualByComparingTo("110.00");
    }

    @Configuration
    static class TestConfig {
        @Bean
        TaxPolicy taxPolicy() {
            return new TaxPolicy(new BigDecimal("0.10"));
        }

        @Bean
        InvoiceService invoiceService(TaxPolicy taxPolicy) {
            return new InvoiceService(taxPolicy);
        }
    }
}
~~~

Trong ví dụ này:

- `@Test` thuộc JUnit Jupiter và đánh dấu phương thức cần chạy.
- `@SpringJUnitConfig` thuộc Spring Test. Nó kết nối Spring với JUnit và chỉ định cấu hình để tạo ApplicationContext.
- `@Autowired` yêu cầu Spring inject bean vào test.
- `@Bean` khai báo các đối tượng sẽ được quản lý trong ApplicationContext.
- `assertThat` thuộc AssertJ và kiểm tra kết quả nghiệp vụ.

Ví dụ giả định `InvoiceService` và `TaxPolicy` là các class nghiệp vụ có constructor tương ứng. Điểm cần quan sát là test nhận `InvoiceService` từ container; nó không tự tạo service bằng `new`. Nhờ đó, test có thể kiểm chứng cả việc Spring lắp ghép dependency.

Nếu bỏ Spring Test, JUnit vẫn có thể gọi một phương thức test, nhưng không còn cơ chế tạo ApplicationContext và inject `InvoiceService` như ví dụ. Nếu bỏ AssertJ, test vẫn có thể chạy và dùng assertion của JUnit. Nếu bỏ JUnit, cần một test runner khác để phát hiện và thực thi test.

Trong dự án dùng JUnit 4, Spring từng tích hợp qua `SpringRunner`/`SpringJUnit4ClassRunner` với `@RunWith`. Với JUnit Jupiter, cách tích hợp hiện đại là `SpringExtension`; không nên trộn annotation của hai thế hệ JUnit trong cùng một test class.

## Spring Test cung cấp những khả năng nào?

### 1. Tạo và tái sử dụng ApplicationContext

Nhiều hành vi chỉ xuất hiện khi object được tạo qua Spring: constructor injection, field injection, AOP proxy, bean scope, event listener, transaction proxy hoặc cấu hình từ các class `@Configuration`. Tự gọi constructor của service trong một unit test không kiểm chứng được những hành vi container này.

TestContext Framework quản lý ApplicationContext cho các test cần Spring. Nó có thể tái sử dụng context giữa các test có cùng cấu hình, giúp giảm chi phí khởi tạo. Cấu hình test càng khác nhau nhiều thì càng có khả năng tạo thêm context và làm suite chạy lâu hơn.

Một số annotation thường gặp:

| Annotation | Ý nghĩa |
|---|---|
| `@ContextConfiguration` | Chỉ định class cấu hình hoặc resource dùng để nạp ApplicationContext |
| `@SpringJUnitConfig` | Kết hợp tích hợp Spring với JUnit Jupiter và cấu hình context |
| `@SpringJUnitWebConfig` | Biến thể dành cho cấu hình web context |
| `@ActiveProfiles` | Kích hoạt profile khi tạo context test |
| `@TestPropertySource` | Khai báo property bổ sung hoặc ghi đè cho test |
| `@DynamicPropertySource` | Đăng ký property động, thường hữu ích khi địa chỉ hoặc cổng của dịch vụ test chỉ biết lúc chạy |
| `@DirtiesContext` | Đánh dấu context đã bị thay đổi và cần loại khỏi cache để được tạo lại |

Ví dụ, một test cần profile `test` có thể khai báo:

~~~java
@SpringJUnitConfig(AppTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "feature.invoice.enabled=true"
})
class InvoiceFeatureTest {
    // Các test sử dụng bean được tạo với profile và property ở trên.
}
~~~

`@DirtiesContext` nên được dùng khi test thực sự làm thay đổi trạng thái cấu hình hoặc bean trong context đến mức không thể khôi phục an toàn. Dùng annotation này tràn lan làm mất lợi ích cache và khiến các test sau phải khởi tạo context lại.

### 2. Quản lý transaction cho test

Khi kiểm tra repository hoặc luồng nghiệp vụ ghi dữ liệu, test thường cần transaction để cô lập dữ liệu. Spring Test hỗ trợ transaction test thông qua `@Transactional` và transaction manager trong context.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void savesAndFindsAccount() {
        accountRepository.save(new Account("A-100", "Lan"));

        var account = accountRepository.findByCode("A-100");

        assertThat(account).isPresent();
        assertThat(account.get().getName()).isEqualTo("Lan");
    }
}
~~~

Với transaction do Spring Test quản lý, hành vi mặc định thường là rollback khi test kết thúc. Điều này giúp dữ liệu được tạo trong một test không tồn tại như dữ liệu đã commit sau test đó. Có thể điều chỉnh hành vi bằng `@Commit` hoặc `@Rollback(false)` khi trường hợp kiểm thử yêu cầu.

Cần hiểu đúng phạm vi của rollback: nó chỉ áp dụng cho transaction được test quản lý. Một lời gọi HTTP sang hệ thống khác, thao tác ghi file, gửi message ra broker hoặc công việc chạy trên thread khác không tự động bị rollback cùng transaction của test. Nếu ứng dụng mở transaction độc lập hoặc tự commit, test cũng không thể mặc định giả định rằng mọi thay đổi đều được hoàn tác.

Spring Test còn hỗ trợ chạy SQL script cho test bằng `@Sql`, hữu ích khi cần chuẩn bị dữ liệu hoặc kiểm tra trạng thái database theo một kịch bản cụ thể.

### 3. Kiểm thử tầng web

Một controller Spring MVC không chỉ là một phương thức Java. Khi xử lý request, nó còn liên quan đến mapping URL, binding tham số, validation, converter, exception handler, interceptor và định dạng response. Gọi trực tiếp phương thức controller chỉ kiểm tra logic của phương thức; nó bỏ qua phần lớn pipeline HTTP của Spring MVC.

MockMvc cho phép gửi request giả lập qua hạ tầng Spring MVC và kiểm tra response mà không cần mở cổng HTTP hoặc khởi động một server thật.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@RestController
class GreetingController {
    @GetMapping("/greeting")
    String greeting(@RequestParam(defaultValue = "world") String name) {
        return "Hello, " + name;
    }
}

class GreetingControllerTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new GreetingController())
            .build();
    }

    @Test
    void returnsGreeting() throws Exception {
        mockMvc.perform(get("/greeting").param("name", "Lan"))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, Lan"));
    }
}
~~~

Ở đây JUnit quản lý lifecycle của test; MockMvc thuộc hệ sinh thái Spring Test và mô phỏng request/response theo pipeline Spring MVC; các `ResultMatcher` xác nhận HTTP status và body. Có thể kết hợp thêm AssertJ nếu cần kiểm tra dữ liệu đã trích xuất từ response.

Ví dụ dùng `standaloneSetup` tạo controller trực tiếp, phù hợp khi muốn tập trung vào mapping và hành vi của controller. Nó không chứng minh toàn bộ cấu hình ứng dụng, dependency injection hay các thành phần MVC được khai báo trong ApplicationContext đang hoạt động đúng. Khi cần kiểm tra các cấu hình đó, hãy dựng MockMvc từ WebApplicationContext hoặc dùng cấu hình kiểm thử phù hợp của Spring Boot.

Với ứng dụng reactive, WebTestClient cung cấp API kiểm thử request/response theo phong cách client. Nó có thể làm việc với môi trường mock hoặc server thật tùy cách cấu hình. Việc chọn MockMvc hay WebTestClient phụ thuộc vào stack web và mục tiêu kiểm thử, không phụ thuộc vào thư viện assertion đang dùng.

## Spring Framework Test và Spring Boot Test có quan hệ gì?

Spring Framework cung cấp Spring Test như một nền tảng kiểm thử tích hợp với container và các module của Framework. Spring Boot xây dựng thêm các tiện ích để kiểm thử ứng dụng Boot đã được auto-configuration.

Một số annotation thường gặp thuộc Spring Boot Test, không phải annotation cốt lõi của Spring Framework Test:

- `@SpringBootTest` khởi tạo ứng dụng theo cấu hình Spring Boot để thực hiện integration test.
- `@WebMvcTest` giới hạn context vào một lát cắt MVC.
- `@DataJpaTest` tập trung vào các thành phần persistence/JPA.
- `@AutoConfigureMockMvc` cấu hình MockMvc trong ngữ cảnh Spring Boot.

Spring Boot Test sử dụng Spring Test bên dưới, nhưng hai tên gọi không đồng nghĩa. Khi đọc dependency hoặc annotation trong dự án, cần xác định tính năng đến từ Spring Framework hay phần bổ sung của Spring Boot. Chẳng hạn, `@SpringJUnitConfig` là của Spring Test; `@SpringBootTest` là của Spring Boot Test.

## Chọn JUnit thuần hay thêm Spring Test?

Không phải mọi test trong một dự án Spring đều cần khởi động Spring. Quyết định nên dựa vào điều mà test cần chứng minh.

| Mục tiêu kiểm thử | Công cụ phù hợp | Lý do |
|---|---|---|
| Hàm tính toán, quy tắc nghiệp vụ thuần Java, không cần bean | JUnit + assertion library | Chạy nhanh, ít phụ thuộc, dễ cô lập |
| Service cần kiểm chứng dependency injection hoặc cấu hình bean | JUnit + Spring Test | Cần ApplicationContext thật |
| Repository cần kiểm tra mapping và truy vấn với database test | JUnit + Spring Test và database test phù hợp | Cần persistence infrastructure và transaction |
| Controller cần kiểm tra mapping, binding, status và response của Spring MVC | JUnit + MockMvc | Cần pipeline MVC nhưng thường không cần server thật |
| Luồng ứng dụng cần kiểm chứng nhiều bean và cấu hình Boot cùng hoạt động | JUnit + Spring Test/Spring Boot Test | Cần context có phạm vi rộng hơn |

Một chiến lược cân bằng thường có nhiều unit test nhỏ chạy nhanh, một số slice test kiểm tra từng tầng, và một số integration test xác nhận các thành phần phối hợp với nhau. Không cần biến mọi test thành integration test chỉ vì ứng dụng sử dụng Spring.

## Những nhầm lẫn thường gặp

**Cho rằng có JUnit là đã kiểm thử được Spring.** JUnit thực thi test, nhưng không tự tạo ApplicationContext hay xử lý injection. Test có `@Autowired` cần integration với Spring Test.

**Cho rằng Spring Test thay thế JUnit.** Spring Test bổ sung môi trường và tiện ích kiểm thử. JUnit vẫn thường là framework điều khiển test trong dự án dùng JUnit Jupiter.

**Cho rằng AssertJ hoặc Hamcrest có thể khởi động Spring.** Assertion library chỉ kiểm tra kết quả. Nó không quản lý bean, profile, transaction hay web context.

**Khởi động toàn bộ context cho một phép tính đơn giản.** Nếu class có thể kiểm tra bằng cách truyền dependency trực tiếp qua constructor, một unit test thuần JUnit thường nhanh và rõ ràng hơn. Chỉ dùng Spring Test khi chính hành vi tích hợp với Spring nằm trong phạm vi cần kiểm chứng.

**Cho rằng rollback bao phủ mọi tác động phụ.** Rollback transaction không thu hồi request đã gửi, message đã phát, file đã ghi hoặc thao tác bên ngoài transaction. Các tác động này cần cơ chế cô lập và dọn dẹp riêng.

**Lạm dụng `@DirtiesContext`.** Annotation này có thể làm giảm hiệu quả cache context. Trước khi dùng, hãy xác định test đã làm thay đổi trạng thái nào và liệu có thể khôi phục trạng thái đó trực tiếp hay không.

**Dùng MockMvc nhưng kết luận rằng server thật đã hoạt động đúng.** MockMvc kiểm tra pipeline Spring MVC trong môi trường mock. Nó không kiểm tra việc bind cổng, cấu hình mạng, TLS hoặc toàn bộ hành vi của một server đang chạy. Nếu các yếu tố đó thuộc phạm vi yêu cầu, cần một integration test với server thật.

## Cách ghi nhớ khi thiết kế test

Hãy bắt đầu bằng việc xác định hành vi cần chứng minh:

- Nếu chỉ cần gọi một đối tượng Java và so sánh kết quả, dùng JUnit cùng assertion library là đủ.
- Nếu cần Spring tạo bean, inject dependency, nạp profile/property hoặc quản lý transaction, bổ sung Spring Test.
- Nếu cần kiểm tra request đi qua Spring MVC, dùng MockMvc; nếu kiểm tra ứng dụng reactive, cân nhắc WebTestClient.
- Nếu cần kiểm tra auto-configuration và cách Spring Boot khởi tạo ứng dụng, dùng tiện ích của Spring Boot Test với phạm vi context phù hợp.
- Chọn assertion library theo độ rõ ràng của điều kiện kiểm tra; thay đổi assertion library không làm thay đổi cách Spring context được khởi tạo.

JUnit điều khiển test, Spring Test chuẩn bị và tích hợp môi trường Spring, còn assertion library xác nhận kết quả. Khi phân định đúng ba trách nhiệm này, test sẽ thể hiện chính xác điều nó đang kiểm chứng và tránh phải trả chi phí khởi tạo hạ tầng không cần thiết.
