# Phạm vi Spring Framework Testing so với công cụ Spring Boot

Khi kiểm thử một ứng dụng Spring, ta thường gặp hai nhóm API có tên gọi gần nhau: phần hỗ trợ kiểm thử do **Spring Framework** cung cấp và các tiện ích kiểm thử do **Spring Boot** bổ sung. Chúng phối hợp với nhau, nhưng giải quyết những vấn đề khác nhau.

Spring Framework cung cấp nền tảng để dựng và quản lý môi trường kiểm thử cho các thành phần Spring: nạp `ApplicationContext`, tiêm dependency vào test, quản lý transaction, chuẩn bị môi trường web giả lập và cung cấp các đối tượng hỗ trợ như `MockMvc`. Spring Boot xây dựng trên nền tảng đó để khởi động ứng dụng theo cách gần với cấu hình thực tế, tự động cấu hình các thành phần kiểm thử và cung cấp những bài kiểm thử theo lát cắt (test slice) như MVC hoặc JPA.

Có thể hình dung ranh giới như sau:

```text
JUnit / test engine / assertion / mocking libraries
                    │
                    ▼
Spring Framework Test
  - TestContext Framework
  - SpringExtension và tích hợp với JUnit
  - transaction, profile, property, SQL cho test
  - MockMvc, WebTestClient, MockRestServiceServer
                    │
                    ▼
Spring Boot Test
  - khởi động ứng dụng bằng SpringApplication
  - @SpringBootTest và test slice
  - tự động cấu hình môi trường kiểm thử
  - tiện ích riêng cho ứng dụng Boot
```

Đây là quan hệ theo tầng, không phải hai bộ công cụ cạnh tranh. Một bài kiểm thử Spring Boot thường sử dụng cơ chế của Spring Framework ở bên dưới.

## 1. Spring Framework Testing chịu trách nhiệm phần nào?

Spring Framework Testing tập trung vào việc **kiểm thử các thành phần có sử dụng Spring** và cung cấp hạ tầng để một test có thể làm việc với container Spring một cách có kiểm soát. Phần lớn API nằm trong module `spring-test`, với các package quen thuộc như `org.springframework.test.context`, `org.springframework.test.context.junit.jupiter`, `org.springframework.test.web.servlet` và `org.springframework.test.web.reactive.server`.

### 1.1. TestContext Framework

TestContext Framework là nền tảng quan trọng nhất. Nó tạo cầu nối giữa test framework (chẳng hạn JUnit Jupiter) và `ApplicationContext` của Spring. Nhờ đó, test có thể yêu cầu Spring nạp cấu hình, tiêm bean vào test instance, áp dụng profile hoặc property riêng, và tái sử dụng context giữa các test khi cấu hình tương thích.

Một số annotation thường gặp:

| Annotation | Vai trò trong kiểm thử |
|---|---|
| `@ExtendWith(SpringExtension.class)` | Kết nối JUnit Jupiter với Spring TestContext Framework. |
| `@ContextConfiguration` | Chỉ định class cấu hình hoặc resource dùng để tạo test `ApplicationContext`. |
| `@SpringJUnitConfig` | Annotation kết hợp tiện lợi giữa `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`. |
| `@ActiveProfiles` | Chọn profile được kích hoạt khi tạo context cho test. |
| `@TestPropertySource` | Bổ sung property source dành riêng cho test. |
| `@DynamicPropertySource` | Đăng ký property động, thường dùng khi giá trị chỉ có sau khi khởi động tài nguyên phục vụ test. |
| `@DirtiesContext` | Đánh dấu context đã bị test làm thay đổi trạng thái và cần loại khỏi cache. |

Ví dụ một test dùng Spring Framework mà không cần Spring Boot:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsAnOrder() {
        Order order = orderService.createOrder(new CreateOrderCommand("SKU-1", 2));

        assertThat(order.getItems()).hasSize(1);
    }
}
```

Ở ví dụ này, test chỉ định cấu hình Spring cần nạp. Spring Test tạo context theo cấu hình đó và tiêm `OrderService` vào test. Không có bước khởi động một ứng dụng Spring Boot hoàn chỉnh.

TestContext Framework còn quản lý vòng đời của context và một số listener thực thi trước/sau test. Cache context giúp tránh khởi tạo lại cùng một cấu hình cho từng phương thức test. Vì vậy, test chạy nhanh hơn khi nhiều test có thể dùng chung context. Đổi lại, test cần tránh để lại trạng thái dùng chung ngoài ý muốn; chỉ dùng `@DirtiesContext` khi test thực sự làm hỏng trạng thái context và cần tạo lại context ở lần sử dụng sau.

### 1.2. Transaction và dữ liệu kiểm thử

Spring Framework cung cấp hỗ trợ kiểm thử transaction thông qua TestContext Framework. Khi một test được đánh dấu `@Transactional`, Spring có thể chạy test trong transaction do test quản lý và rollback sau test theo mặc định.

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void savesAnAccount() {
        accountRepository.save(new Account("ACC-100"));

        assertThat(accountRepository.findByCode("ACC-100")).isPresent();
    }
}
```

Các annotation hỗ trợ khác gồm `@Commit`, `@Rollback`, `@BeforeTransaction`, `@AfterTransaction`, `@Sql` và `@SqlConfig`. Chúng giúp kiểm soát dữ liệu trước, trong và sau test. Ví dụ, `@Sql` có thể chạy script chuẩn bị dữ liệu; `@Commit` yêu cầu commit thay vì rollback cho trường hợp cần xác nhận dữ liệu tồn tại sau transaction.

Điểm cần hiểu rõ: rollback chỉ áp dụng cho transaction mà test đang quản lý. Nếu test gửi HTTP request đến một server đang chạy ở cổng thật, transaction xử lý request thường thuộc thread và ranh giới transaction phía server. Transaction của test không tự động bao trùm transaction đó. Vì thế, không nên kết luận rằng mọi dữ liệu được tạo bởi test có server thật đều tự rollback chỉ vì phương thức test có `@Transactional`.

### 1.3. Công cụ kiểm thử web và HTTP

Spring Framework Test cung cấp các công cụ để kiểm tra tầng web hoặc HTTP mà không nhất thiết phải khởi chạy một server thật:

| Công cụ | Phạm vi sử dụng |
|---|---|
| `MockMvc` | Gửi request đến Spring MVC `DispatcherServlet` trong môi trường kiểm thử, kiểm tra status, header, model và nội dung response. |
| `WebTestClient` | API fluent để gửi request và kiểm tra response; có thể dùng với WebFlux và các cấu hình kiểm thử MVC tương ứng. |
| `MockMvcWebTestClient` | Cầu nối để dùng API `WebTestClient` khi kiểm thử ứng dụng Spring MVC thông qua MockMvc. |
| `MockRestServiceServer` | Giả lập phản hồi của HTTP service bên ngoài khi kiểm thử code dùng `RestTemplate`. |

Ví dụ dùng `MockMvc`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebTestConfiguration.class)
class OrderControllerTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test
    void returnsOrderList() throws Exception {
        mockMvc.perform(get("/orders"))
                .andExpect(status().isOk());
    }
}
```

`MockMvc` thuộc Spring Framework Test. Nó không phải tính năng riêng của Spring Boot. Boot có thể tự cấu hình `MockMvc` cho test bằng annotation của Boot, nhưng đối tượng và cơ chế gửi request vẫn đến từ hệ sinh thái Spring Test.

## 2. Spring Boot bổ sung điều gì cho kiểm thử?

Spring Boot Testing tập trung vào trải nghiệm kiểm thử một **ứng dụng Spring Boot**. Thay vì yêu cầu mỗi test tự chọn từng cấu hình Spring, Boot tận dụng cơ chế auto-configuration, cách tìm cấu hình ứng dụng và `SpringApplication` để dựng môi trường phù hợp với mục đích của test.

Các API thường nằm trong những module như `spring-boot-test` và `spring-boot-test-autoconfigure`. Khi phát triển ứng dụng Boot, dependency `spring-boot-starter-test` thường được dùng để đưa các thư viện kiểm thử phổ biến vào test classpath theo phiên bản được Boot quản lý.

### 2.1. `@SpringBootTest`: khởi động ứng dụng theo cấu hình Boot

`@SpringBootTest` yêu cầu Spring Boot tạo test context thông qua cơ chế khởi động ứng dụng. Boot tìm cấu hình ứng dụng phù hợp, áp dụng auto-configuration và nạp các bean mà ứng dụng khai báo. Đây là lựa chọn khi mục tiêu là kiểm tra sự phối hợp của nhiều thành phần trong ứng dụng.

```java
@SpringBootTest
class OrderApplicationIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsAnOrderUsingApplicationConfiguration() {
        Order order = orderService.createOrder(new CreateOrderCommand("SKU-1", 2));

        assertThat(order.getItems()).hasSize(1);
    }
}
```

`@SpringBootTest` có thể chạy với nhiều chế độ web:

| `webEnvironment` | Ý nghĩa |
|---|---|
| `MOCK` | Tạo web application context giả lập; không khởi động server HTTP thật. Đây là chế độ mặc định. |
| `RANDOM_PORT` | Khởi động server trên cổng ngẫu nhiên để test gửi request qua HTTP thật. |
| `DEFINED_PORT` | Khởi động server trên cổng được cấu hình. |
| `NONE` | Tạo application context không có web environment. |

Ví dụ kiểm thử qua cổng ngẫu nhiên:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void exposesTheOrderEndpoint() {
        // Gửi HTTP request tới localhost và port được cấp cho test.
    }
}
```

Chế độ `RANDOM_PORT` hữu ích khi cần xác nhận luồng HTTP qua server thực, bao gồm cấu hình server và các thành phần chạy trong request. Nó tốn tài nguyên và thời gian hơn kiểm thử bằng MockMvc. Đồng thời, cần nhớ rằng request chạy ở phía server có ranh giới transaction riêng, không tự động nằm trong transaction của phương thức test.

### 2.2. Test slice: chỉ nạp phần ứng dụng cần kiểm tra

Không phải test nào cũng cần toàn bộ application context. Spring Boot cung cấp các annotation test slice để giới hạn cấu hình được nạp theo một khu vực chức năng. Điều này làm test tập trung hơn và thường khởi động nhanh hơn `@SpringBootTest`.

| Annotation | Phần ứng dụng được tập trung kiểm thử |
|---|---|
| `@WebMvcTest` | Tầng Spring MVC, thường tập trung vào controller, binding, validation, exception handling và cấu hình MVC liên quan. |
| `@DataJpaTest` | Thành phần JPA, entity, repository và cấu hình persistence liên quan. |
| `@JdbcTest` | Tầng JDBC và truy vấn dữ liệu dựa trên JDBC. |
| `@JsonTest` | Serialization và deserialization JSON. |
| `@RestClientTest` | Thành phần gọi REST service bên ngoài và cấu hình client liên quan. |

Ví dụ test controller:

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsBadRequestWhenInputIsInvalid() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest());
    }
}
```

`@WebMvcTest` là tiện ích của Spring Boot. Nó giới hạn context vào cấu hình MVC và những thành phần được chọn. `MockMvc` được tiêm vào test nhờ cấu hình tự động của Boot, nhưng `MockMvc` và API kiểm tra request/response vẫn là phần hỗ trợ của Spring Framework Test. Các dependency nghiệp vụ của controller thường cần được thay bằng mock hoặc được import rõ ràng vì slice không nạp toàn bộ service và repository như ứng dụng đầy đủ.

Tương tự, `@DataJpaTest` tập trung vào persistence. Cấu hình slice này thường chạy test trong transaction và rollback sau test. Khi cần kiểm tra hành vi xuyên qua nhiều tầng, chẳng hạn HTTP request đi qua controller, service và database, một test slice riêng lẻ có thể không đủ; khi đó hãy cân nhắc `@SpringBootTest` hoặc một bài integration test có phạm vi được xác định rõ.

### 2.3. Auto-configuration và tiện ích kiểm thử của Boot

Boot còn cung cấp annotation và helper để cấu hình môi trường test nhanh hơn, ví dụ:

- `@AutoConfigureMockMvc` cấu hình MockMvc trong test context Boot, thường kết hợp với `@SpringBootTest` khi muốn dùng application context rộng hơn nhưng vẫn gửi request mà không mở cổng HTTP thật.
- `@TestConfiguration` khai báo cấu hình bổ sung dành cho test. Cấu hình này có thể bổ sung bean phục vụ test mà không biến nó thành cấu hình ứng dụng thông thường.
- `@MockBean` và các tiện ích mock bean của Boot cho phép thay thế bean trong application context bằng mock khi kiểm thử. Cần dùng đúng API theo phiên bản Spring Boot của dự án.
- `TestRestTemplate` hỗ trợ gửi HTTP request trong các bài kiểm thử ứng dụng Boot có server đang chạy.
- Các extension và helper như `OutputCaptureExtension` hỗ trợ kiểm tra output trong những trường hợp phù hợp.

Một ví dụ kết hợp context Boot và MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApplicationWebTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void respondsWithNotFoundForUnknownOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", 99999))
                .andExpect(status().isNotFound());
    }
}
```

Trong ví dụ này, `@SpringBootTest` quyết định cách tạo context ứng dụng; `@AutoConfigureMockMvc` là tiện ích Boot yêu cầu cấu hình MockMvc; còn `MockMvc` thực hiện request và assertion theo API của Spring Test.

## 3. So sánh ranh giới trách nhiệm

| Khía cạnh | Spring Framework Testing | Spring Boot Testing |
|---|---|---|
| Mục tiêu chính | Cung cấp hạ tầng kiểm thử cho Spring Framework và các thành phần Spring. | Làm cho việc kiểm thử ứng dụng Spring Boot thuận tiện và gần với cách ứng dụng được khởi động. |
| Tạo context | Chỉ định cấu hình Spring bằng TestContext, chẳng hạn `@ContextConfiguration`. | Khởi động theo cấu hình ứng dụng bằng `@SpringBootTest` và `SpringApplication`. |
| Tích hợp JUnit | `SpringExtension`, `@SpringJUnitConfig` và TestContext Framework. | Các annotation Boot tích hợp với Spring Test; thông thường không cần tự khai báo `SpringExtension` thêm khi đã dùng `@SpringBootTest`. |
| Web test | Cung cấp `MockMvc`, `WebTestClient`, `MockRestServiceServer` và API liên quan. | Tự động cấu hình các công cụ đó theo application context hoặc test slice. |
| Transaction test | Cung cấp hỗ trợ `@Transactional`, rollback/commit và SQL script cho test. | Dùng lại nền tảng transaction của Spring, đồng thời cung cấp cấu hình slice phù hợp cho các loại test dữ liệu. |
| Phạm vi context | Do test chỉ định, linh hoạt từ cấu hình nhỏ đến web context. | Có thể dùng toàn bộ ứng dụng hoặc một lát cắt do Boot định nghĩa. |
| Phụ thuộc | Thường cần `spring-test` cùng test engine và thư viện assertion/mock phù hợp. | Thường dùng `spring-boot-starter-test`, được Boot quản lý phiên bản dependency. |

Một cách phân biệt nhanh là nhìn vào câu hỏi mà annotation giải quyết:

- “Nạp một Spring `ApplicationContext` từ cấu hình nào?” là mối quan tâm của Spring Framework TestContext (`@ContextConfiguration`).
- “Khởi động ứng dụng Boot theo cấu hình chính và auto-configuration như thế nào?” là mối quan tâm của Spring Boot (`@SpringBootTest`).
- “Gửi request và kiểm tra status/body mà không mở server thật bằng cách nào?” có thể dùng `MockMvc` hoặc `WebTestClient` từ Spring Framework Test.
- “Làm sao để Boot tự cấu hình MVC context và MockMvc cho controller test?” là mối quan tâm của test slice và auto-configuration trong Spring Boot (`@WebMvcTest`, `@AutoConfigureMockMvc`).

## 4. Chọn lớp công cụ theo mục tiêu kiểm thử

Không nên mặc định rằng mọi test đều phải dùng `@SpringBootTest`. Hãy bắt đầu từ hành vi cần xác nhận và chỉ nạp phạm vi lớn hơn khi test thực sự cần nó.

| Mục tiêu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Kiểm tra thuật toán hoặc logic thuần Java | JUnit và assertion/mock library, không nạp Spring context | Nhanh, ít phụ thuộc vào cấu hình ứng dụng. |
| Kiểm tra bean và wiring của một cấu hình Spring cụ thể | Spring TestContext với `@ContextConfiguration` hoặc `@SpringJUnitConfig` | Kiểm soát chính xác cấu hình cần nạp, không cần bootstrap Boot. |
| Kiểm tra controller Spring MVC | `@WebMvcTest` và `MockMvc` | Tập trung vào MVC, tránh nạp các tầng không liên quan. |
| Kiểm tra repository/JPA | `@DataJpaTest` | Tập trung vào persistence và cấu hình dữ liệu của Boot. |
| Kiểm tra tích hợp nhiều bean và auto-configuration | `@SpringBootTest` | Cần xác nhận các thành phần phối hợp trong context ứng dụng. |
| Kiểm tra giao tiếp HTTP qua server đang chạy | `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Bao gồm server thật và luồng request qua mạng nội bộ của test. |

Quy tắc thực hành: dùng phạm vi nhỏ nhất có thể chứng minh hành vi đang cần kiểm tra. Khi một test slice không nạp đủ thành phần, mở rộng cấu hình một cách có chủ đích hoặc chuyển sang integration test rộng hơn. Không mở rộng toàn bộ context chỉ để giải quyết một dependency đơn lẻ nếu có thể cấu hình test rõ ràng hơn.

## 5. Dependency và phiên bản

Trong một ứng dụng Spring Boot, cách phổ biến là khai báo `spring-boot-starter-test` ở test scope. Starter này tập hợp Spring Test và các thư viện kiểm thử thông dụng như JUnit Jupiter, AssertJ, Mockito và một số thư viện hỗ trợ assertion dữ liệu. Thành phần cụ thể phụ thuộc phiên bản Boot và cấu hình dependency của dự án; có thể kiểm tra dependency tree của build khi cần biết chính xác thư viện nào đang được đưa vào.

Nếu ứng dụng dùng Spring Framework mà không dùng Spring Boot, có thể khai báo `spring-test` cùng JUnit Jupiter và các thư viện test mà dự án chọn. Khi tự quản lý dependency, cần giữ các module Spring tương thích cùng một dòng phiên bản. Trong ứng dụng Boot, nên để dependency management của Boot quản lý phiên bản thay vì tự ghim `spring-test` sang một phiên bản khác.

Ví dụ Gradle ở mức khái niệm:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Với ứng dụng không dùng Boot, dependency test có thể bắt đầu từ `org.springframework:spring-test` và các thư viện JUnit/assertion cần thiết. `spring-boot-starter-test` không phải là điều kiện bắt buộc để dùng Spring TestContext, `MockMvc` hay hỗ trợ transaction của Spring Framework.

## 6. Những nhầm lẫn thường gặp

### Nhầm `MockMvc` là công cụ riêng của Spring Boot

`MockMvc` được cung cấp bởi Spring Framework Test. Spring Boot giúp cấu hình và tiêm nó thuận tiện hơn qua `@WebMvcTest` hoặc `@AutoConfigureMockMvc`. Vì vậy, có thể dùng MockMvc trong một ứng dụng Spring MVC không dùng Boot nếu tự dựng web application context phù hợp.

### Cho rằng `@SpringBootTest` và `@ContextConfiguration` có cùng phạm vi

`@ContextConfiguration` cho Spring Test biết cấu hình nào cần nạp. `@SpringBootTest` yêu cầu Boot bootstrap ứng dụng, thường kéo theo auto-configuration và các cấu hình ứng dụng. Hai annotation có thể cùng dẫn tới một Spring context, nhưng con đường khởi tạo và phạm vi cấu hình khác nhau.

### Dùng full context cho mọi test

Full context có ích khi cần xác nhận tích hợp toàn ứng dụng. Với một controller hoặc repository đơn lẻ, test slice thường tập trung hơn và khởi động nhanh hơn. Dùng full context tràn lan làm tăng thời gian chạy và khiến lỗi cấu hình ở một khu vực có thể ảnh hưởng đến những test vốn chỉ muốn kiểm tra khu vực khác.

### Nghĩ rằng test có `@Transactional` luôn rollback mọi thao tác

Transaction test của Spring quản lý transaction gắn với test. Request gửi qua server thật thường được xử lý trong transaction riêng của request. Cần chọn chiến lược dọn dữ liệu phù hợp với kiểu test, đặc biệt khi dùng `RANDOM_PORT` hoặc `DEFINED_PORT`.

### Nhầm starter với một framework kiểm thử độc lập

`spring-boot-starter-test` chủ yếu là dependency starter giúp đưa các thư viện cần thiết vào test classpath theo phiên bản Boot quản lý. Các test engine, assertion library, mock library và Spring Test vẫn là những thành phần có trách nhiệm riêng.

### Dùng annotation theo ví dụ nhưng không kiểm tra phiên bản

Annotation và tiện ích kiểm thử có thể thay đổi theo phiên bản Spring Framework/Spring Boot. Khi sao chép ví dụ, hãy đối chiếu phiên bản dependency đang dùng và package import thực tế. Tránh trộn module `spring-test` của một dòng phiên bản với Spring Boot được quản lý theo dòng khác.

## 7. Kết luận về phạm vi

Spring Framework Testing cung cấp nền tảng kiểm thử: tích hợp test framework với Spring, quản lý test context, transaction và các công cụ web/HTTP như MockMvc. Spring Boot Testing bổ sung cách bootstrap ứng dụng Boot, auto-configuration dành cho test, test slice và các helper đặc thù của Boot.

Khi đọc một bài test, hãy nhận diện riêng ba lớp: thư viện kiểm thử nền như JUnit/Mockito, hạ tầng Spring Framework Test và tiện ích Spring Boot Test. Phân biệt được ba lớp này giúp chọn đúng dependency, hiểu vì sao context được tạo theo cách hiện tại và quyết định phạm vi test vừa đủ cho hành vi cần xác nhận.
