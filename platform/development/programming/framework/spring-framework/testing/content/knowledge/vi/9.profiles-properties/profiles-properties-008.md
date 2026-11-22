# Giới hạn dữ liệu động khi context được dùng chung

Spring TestContext Framework có thể tái sử dụng cùng một ApplicationContext giữa nhiều test class để giảm thời gian khởi tạo. Đây là lợi ích lớn của context cache, nhưng cũng tạo ra một ràng buộc: mọi bean và cấu hình bên trong context được tạo theo các giá trị môi trường tại thời điểm context được khởi tạo.

Khi test dùng dữ liệu động như cổng ngẫu nhiên của Testcontainers, URL của WireMock hoặc endpoint của một dịch vụ giả lập, giá trị đó có thể thay đổi giữa các test class. Nếu các class vẫn dùng chung một context đã cache, bean trong context có thể tiếp tục giữ cấu hình cũ dù nguồn cung cấp property đã trả về giá trị mới.

Vì vậy, khi dùng dữ liệu động, cần đồng bộ vòng đời của tài nguyên với vòng đời của ApplicationContext. Tài nguyên được chia sẻ lâu dài có thể dùng chung context; tài nguyên thay đổi theo từng class cần context riêng hoặc cơ chế làm mới có chủ đích.

## Dữ liệu động trong Spring Test là gì?

Dữ liệu động là giá trị chỉ xác định được khi test chạy hoặc khi tài nguyên test được khởi động. Một số ví dụ thường gặp:

- JDBC URL và cổng ngẫu nhiên do Testcontainers cấp.
- Host/port của WireMock hoặc mock web server.
- Endpoint của dịch vụ giả lập được khởi động trong test.
- Token, queue name hoặc bucket name sinh riêng cho một test run.
- Thông tin kết nối được cấp phát bởi môi trường CI.

Các giá trị này không phù hợp để viết cố định vào file property vì địa chỉ hoặc cổng có thể khác nhau ở mỗi lần chạy. Spring Framework 5.2.5 trở lên cung cấp `@DynamicPropertySource` và `DynamicPropertyRegistry` để đăng ký chúng vào `Environment`.

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("service.base-url", mockServer::getEndpoint);
}
~~~

Phương thức được đánh dấu `@DynamicPropertySource` phải là static và nhận một `DynamicPropertyRegistry`. Mỗi lời gọi `registry.add()` đăng ký một supplier để Spring lấy giá trị khi property được truy vấn. Cách này cho phép test đăng ký endpoint sau khi tài nguyên test đã được khởi tạo.

## @DynamicPropertySource và property supplier

Khác với inline property trong `@TestPropertySource`, dynamic property không cần biết giá trị cuối cùng tại thời điểm biên dịch hoặc khi viết test. Supplier có thể đọc giá trị từ container hoặc server đang chạy.

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Ở ví dụ này, `postgres::getJdbcUrl` là method reference được đăng ký làm supplier. Spring gọi supplier khi cần phân giải property. Có thể đăng ký nhiều property trong cùng một phương thức.

Dynamic property source có độ ưu tiên cao hơn các nguồn cấu hình test thông thường như `@TestPropertySource`, system properties và environment variables. Điều này hữu ích khi endpoint do test cấp phát phải được ưu tiên so với cấu hình mặc định của máy hoặc CI.

Tuy nhiên, supplier không phải cơ chế tự động tái cấu hình mọi bean khi giá trị thay đổi. Ví dụ, `DataSource` được tạo trong lúc ApplicationContext refresh thường đọc JDBC URL và khởi tạo pool một lần. Nếu supplier sau đó trả về URL khác, Spring không tự động tạo lại `DataSource`, đóng pool cũ hoặc bind lại các bean đã được tạo.

Đây là điểm quan trọng khi context được cache: supplier có thể cung cấp giá trị động, nhưng bean trong context vẫn có vòng đời riêng.

## Vì sao context cache có thể giữ cấu hình cũ?

TestContext Framework cache ApplicationContext dựa trên cấu hình đã hợp nhất của test. Cache key bao gồm nhiều yếu tố như cấu hình class/location, initializer, active profile, property source, context customizer và loader.

`@DynamicPropertySource` được tích hợp vào cơ chế này thông qua context customizer. Khi một phương thức dynamic property source được kế thừa từ cùng một lớp cha, các test class con có thể có cấu hình customizer tương đương. Nếu các yếu tố cấu hình còn lại cũng tương đương, Spring có thể lấy lại ApplicationContext đã cache.

Hãy xét tình huống:

1. Test class A khởi động container PostgreSQL và nhận cổng `49152`.
2. `@DynamicPropertySource` đăng ký JDBC URL trỏ tới cổng đó.
3. Spring tạo ApplicationContext và khởi tạo `DataSource` với URL của class A.
4. Test class A kết thúc, container dừng.
5. Test class B kế thừa cùng phương thức `@DynamicPropertySource`, khởi động container mới với cổng `49180`.
6. Nếu context cache tái sử dụng context của A, `DataSource` trong context vẫn có thể trỏ tới cổng `49152`.

Dù supplier có thể đọc endpoint mới khi được truy vấn, `DataSource` đã được khởi tạo trước đó không tự động đổi URL. Test class B có thể gặp lỗi kết nối tới container cũ hoặc một tài nguyên không còn tồn tại.

~~~mermaid
sequenceDiagram
    participant A as Test class A
    participant C1 as Container A
    participant S as Spring Context Cache
    participant B as Test class B
    participant C2 as Container B

    A->>C1: Khởi động, nhận port 49152
    A->>S: Dynamic property đăng ký URL A
    S->>S: Tạo context và DataSource trỏ URL A
    A->>C1: Kết thúc class, container dừng
    B->>C2: Khởi động, nhận port 49180
    B->>S: Cần context với cùng cấu hình cache
    S-->>B: Có thể trả lại context cũ
    Note over B,S: DataSource vẫn giữ URL A
    B->>S: Thực hiện truy vấn
    S-->>B: Kết nối có thể thất bại
~~~

Đây là vấn đề về vòng đời và cache, không nhất thiết là lỗi của `@DynamicPropertySource` hoặc database driver. Nguồn dữ liệu động và context được tái sử dụng đang có vòng đời không tương thích.

## Ví dụ với Testcontainers và lớp test cha

Một mẫu thường gặp là đặt container và phương thức đăng ký property trên lớp test cha:

~~~java
abstract class AbstractPostgresIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void registerDatabaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Hai test class kế thừa lớp cha:

~~~java
@Testcontainers
class CustomerRepositoryIT extends AbstractPostgresIntegrationTest {
    // Kiểm tra repository khách hàng.
}

@Testcontainers
class OrderRepositoryIT extends AbstractPostgresIntegrationTest {
    // Kiểm tra repository đơn hàng.
}
~~~

Trong cách tổ chức này, extension của Testcontainers quản lý static container theo vòng đời test class. Các class con có thể khởi động và dừng container ở những thời điểm khác nhau, vì vậy endpoint được cấp phát có thể thay đổi.

Phương thức `registerDatabaseProperties()` được kế thừa từ cùng lớp cha. Nếu hai test class có cấu hình TestContext tương đương, cache có thể coi chúng là cùng một cấu hình và tái sử dụng ApplicationContext. Khi đó `DataSource` của class sau có thể vẫn trỏ tới container của class trước.

## Cách 1: đánh dấu context dirty sau mỗi test class

Khi mỗi test class cần một container hoặc endpoint riêng, có thể yêu cầu Spring loại ApplicationContext khỏi cache sau khi class hoàn tất bằng `@DirtiesContext`.

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CustomerRepositoryIT extends AbstractPostgresIntegrationTest {
    // Kiểm tra repository khách hàng.
}

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderRepositoryIT extends AbstractPostgresIntegrationTest {
    // Kiểm tra repository đơn hàng.
}
~~~

Sau khi `CustomerRepositoryIT` kết thúc, Spring đóng context và loại entry tương ứng khỏi cache. Khi `OrderRepositoryIT` chạy, framework cần tạo context mới và supplier có thể cung cấp endpoint của container mới.

Cách này phù hợp khi:

- Mỗi class có một container hoặc mock server riêng.
- Endpoint, credential hoặc dữ liệu kết nối thay đổi giữa các class.
- Bean trong context giữ cấu hình đã bind từ lần khởi tạo trước.
- Muốn mỗi class có một vòng đời ApplicationContext riêng.

`@DirtiesContext` có chi phí: context phải được tạo lại, các bean phải khởi tạo lại và các bước bootstrap có thể làm suite chậm hơn. Chỉ dùng nó ở những test class có lý do về vòng đời tài nguyên.

Nếu nhiều class có cùng cache key và chạy song song, việc một class đóng context trong khi class khác đang sử dụng context đó có thể gây lỗi khó tái hiện. Với nhóm test cần context riêng theo từng class, hãy tránh chia sẻ cùng cache entry trong lúc chạy song song; có thể tuần tự hóa nhóm test hoặc thiết kế context key/tài nguyên riêng rõ ràng.

## Cách 2: chia sẻ một tài nguyên động có vòng đời dài

Nếu nhiều test class có thể dùng cùng một database hoặc mock server, cách đơn giản hơn là chia sẻ chính tài nguyên đó trong toàn bộ vòng đời của test suite. Khi endpoint không đổi, việc tái sử dụng context là an toàn và tiết kiệm thời gian.

Ví dụ singleton container của Testcontainers:

~~~java
abstract class AbstractPostgresIntegrationTest {

    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    static {
        postgres.start();
    }

    @DynamicPropertySource
    static void registerDatabaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Container được khởi động một lần trong JVM và tiếp tục tồn tại khi các test class dùng chung context. Các test class có thể tái sử dụng cùng endpoint, nên `DataSource` trong ApplicationContext không bị trỏ tới container đã dừng giữa chừng.

Đây là singleton container pattern. Cần quản lý rõ vòng đời container và để Testcontainers/Ryuk dọn tài nguyên khi JVM kết thúc. Không kết hợp mẫu khởi động thủ công này với `@Container` theo cách khiến extension dừng container sau từng class; hai chiến lược lifecycle cần được lựa chọn nhất quán.

Chia sẻ container không có nghĩa chia sẻ dữ liệu test một cách tùy tiện. Các test vẫn cần dữ liệu riêng, transaction hoặc cleanup phù hợp. Tài nguyên kết nối có thể dùng chung trong khi mỗi test vẫn tạo bản ghi riêng hoặc schema riêng.

## Cách 3: tạo cấu hình context khác nhau khi endpoint khác nhau

Một lựa chọn khác là bảo đảm mỗi test class có context key khác nhau. Khi cấu hình đã hợp nhất khác nhau, Spring không lấy nhầm context của class khác.

Có thể khai báo phương thức `@DynamicPropertySource` riêng trên từng class nếu mỗi class thực sự có nguồn property khác nhau, hoặc tạo cấu hình/customizer có danh tính phản ánh endpoint hay tài nguyên riêng. Tuy nhiên, không nên thêm property giả chỉ để ép cache miss. Cấu hình phải thể hiện khác biệt thật về môi trường kiểm thử.

Trong nhiều trường hợp, `@DirtiesContext` rõ ràng và dễ hiểu hơn một custom context customizer chỉ nhằm tạo cache key riêng. Nếu cần một framework test phức tạp với nhiều resource động, hãy cân nhắc xây dựng cơ chế bootstrap/context customizer có quy tắc `equals()` và `hashCode()` phản ánh đúng danh tính tài nguyên.

## Dữ liệu động không thay thế profile

Profile và dynamic property giải quyết hai bài toán khác nhau:

| Cơ chế | Dùng để | Ví dụ |
|---|---|---|
| `@ActiveProfiles` | Chọn nhóm bean/cấu hình theo môi trường hoặc kịch bản | `integration`, `test`, `local` |
| `@TestPropertySource` | Khai báo property cố định dành cho test | `feature.payment.enabled=false` |
| `@DynamicPropertySource` | Cung cấp property chỉ biết khi tài nguyên test chạy | JDBC URL, random port, mock server endpoint |

Không nên tạo một profile mới cho mỗi cổng ngẫu nhiên hoặc mỗi container instance. Profile biểu diễn lựa chọn cấu hình, còn endpoint động là giá trị của một property. Nếu dùng profile để ép tạo context riêng cho từng endpoint, cấu hình sẽ trở nên khó hiểu và không phản ánh đúng ý nghĩa của profile.

Active profiles là một phần của context cache key. Chúng có thể tạo context khác khi test thực sự dùng các nhóm bean/cấu hình khác nhau. Nhưng thay đổi profile không phải giải pháp thay thế cho việc quản lý vòng đời tài nguyên động.

## Supplier lazy không đồng nghĩa bean tự cập nhật

Một hiểu nhầm phổ biến là vì `DynamicPropertyRegistry` nhận supplier nên mọi bean luôn nhận được giá trị mới mỗi lần endpoint thay đổi.

Supplier được gọi khi property source cần phân giải property. Nhưng nhiều bean chỉ đọc property tại thời điểm khởi tạo:

~~~java
@Configuration
class ClientConfiguration {

    @Bean
    PaymentClient paymentClient(Environment environment) {
        String baseUrl = environment.getRequiredProperty("service.base-url");
        return new PaymentClient(baseUrl);
    }
}
~~~

Trong một cấu hình thực tế, property được bind vào constructor hoặc `@ConfigurationProperties` khi bean được tạo. Sau khi context đã refresh, Spring không tự động dựng lại bean chỉ vì supplier trả về một giá trị khác.

Ngay cả khi một lần truy vấn `Environment` sau đó nhìn thấy giá trị mới, client hoặc connection pool đã được khởi tạo trước đó có thể vẫn dùng giá trị cũ. Vì vậy, phải đồng bộ thời gian sống của bean với thời gian sống của endpoint.

Nếu ứng dụng thật sự cần thay đổi endpoint khi đang chạy, đó là một yêu cầu runtime reconfiguration riêng. Cần một abstraction có khả năng cập nhật client/pool an toàn, quản lý kết nối cũ và đồng bộ truy cập. `@DynamicPropertySource` chủ yếu phục vụ việc cung cấp cấu hình khi chuẩn bị test context.

## Giới hạn khi chạy test song song

Chia sẻ context và dữ liệu động giữa các test class có thể nguy hiểm khi chạy song song:

- Class A có thể đóng container trong khi class B vẫn dùng connection pool của context chung.
- Một class có thể đánh dấu context dirty trong lúc class khác đang thực thi trên context đó.
- Hai test có thể ghi cùng một database hoặc queue dù endpoint giống nhau.
- Một static field chứa endpoint có thể bị cập nhật trong khi class khác đang đọc nó.
- Một mock server có thể bị reset hoặc dừng khi request từ class khác vẫn đang chạy.

Nếu tài nguyên là singleton dùng chung, hãy giữ nó sống cho tới khi mọi test sử dụng đã hoàn tất và cô lập dữ liệu giữa các test. Nếu tài nguyên có vòng đời theo class, hãy tạo context riêng cho class đó và tránh chạy đồng thời những class có cùng cache key nhưng endpoint khác nhau.

Khi test song song, không chỉ cần một endpoint duy nhất mà còn cần quyền sở hữu rõ ràng đối với dữ liệu và tài nguyên. Dùng schema, tenant, queue hoặc namespace riêng có thể ngăn test đọc/xóa dữ liệu của nhau.

## Chọn chiến lược theo vòng đời tài nguyên

| Đặc điểm tài nguyên | Chiến lược context phù hợp | Lưu ý |
|---|---|---|
| Một container dùng xuyên suốt test suite | Chia sẻ context và container | Endpoint ổn định trong suốt vòng đời context |
| Container mới cho từng test class | Context riêng hoặc `@DirtiesContext(AFTER_CLASS)` | Đảm bảo context cũ bị đóng trước khi tái sử dụng cùng cache key |
| Mock server có endpoint cố định, chỉ reset dữ liệu | Có thể chia sẻ context | Reset không được làm mất trạng thái cần cho test khác |
| Endpoint thay đổi sau khi context đã refresh | Tạo context mới hoặc cơ chế runtime reconfiguration riêng | Supplier không tự bind lại bean |
| Mỗi class có database/schema riêng | Context và cấu hình riêng theo class | Dùng namespace riêng, cleanup đúng phạm vi |
| Nhiều class chạy song song trên tài nguyên singleton | Chia sẻ endpoint nhưng cô lập dữ liệu | Không dừng hoặc reset tài nguyên khi class khác đang dùng |

Quyết định quan trọng là: tài nguyên động sống bao lâu, context sống bao lâu và bean nào giữ giá trị được bind từ tài nguyên đó. Nếu context sống lâu hơn tài nguyên mà bean phụ thuộc, test có nguy cơ dùng cấu hình lỗi thời.

## Quy trình điều tra lỗi endpoint cũ

Khi một test class kết nối tới cổng hoặc URL của lần chạy trước, hãy lần theo các bước:

1. Xác định nguồn property: `@DynamicPropertySource`, `@TestPropertySource`, profile hay environment variable.
2. Ghi nhận endpoint thực tế của tài nguyên trong từng test class.
3. Xác định phương thức dynamic property source có được kế thừa từ cùng superclass hay không.
4. Xác định TestContext Framework có tái sử dụng cùng ApplicationContext hay tạo context mới.
5. Kiểm tra bean như `DataSource`, HTTP client hoặc message connection factory được khởi tạo vào thời điểm nào.
6. Kiểm tra tài nguyên cũ đã dừng trước khi bean trong context cũ bị đóng hay chưa.
7. Chọn chia sẻ tài nguyên lâu dài hoặc làm mới context theo class.
8. Nếu chạy song song, kiểm tra class khác có đang dùng cùng context hoặc resource không.

Có thể bật log của Spring TestContext để quan sát cache hit, cache miss, context creation và context eviction. Log này giúp xác nhận Spring có tái sử dụng context hay không, thay vì suy đoán từ việc property supplier được gọi.

## Những nhầm lẫn thường gặp

**Cho rằng `@DynamicPropertySource` luôn làm context mới.** Annotation đăng ký property động nhưng không buộc Spring tạo context mới nếu cache có context phù hợp.

**Cho rằng supplier đổi giá trị thì bean tự cập nhật.** Supplier được phân giải khi property được truy cập; bean đã khởi tạo thường giữ giá trị được bind trước đó.

**Dùng cùng một container lifecycle theo class với context cache dùng chung.** Container có thể dừng trong khi context vẫn còn được cache. Phải đồng bộ hai vòng đời hoặc loại context khỏi cache.

**Dùng `@DirtiesContext` cho mọi test.** Điều đó làm giảm tái sử dụng context và tăng thời gian suite. Chỉ đánh dấu dirty khi tài nguyên hoặc trạng thái context thực sự thay đổi theo cách không thể tái sử dụng.

**Cho rằng `@ActiveProfiles` giải quyết endpoint động.** Profile chọn nhóm cấu hình; nó không quản lý vòng đời container hoặc tự cập nhật datasource.

**Chạy song song các class cùng cache key nhưng endpoint khác nhau.** Việc một class đóng context hoặc dừng resource có thể ảnh hưởng class còn lại. Hãy cô lập context và tài nguyên trước khi bật parallel execution.

## Nguyên tắc thiết kế

Hãy xem ApplicationContext và tài nguyên động mà bean sử dụng như hai đối tượng có vòng đời liên kết. Nếu nhiều test class dùng cùng một context, endpoint và dịch vụ mà context tham chiếu phải ổn định trong suốt thời gian context được cache. Nếu endpoint thay đổi theo class, cần context riêng hoặc làm mới context trước khi class tiếp theo sử dụng.

`@DynamicPropertySource` giúp đăng ký giá trị chỉ biết khi test chạy. TestContext cache giúp tiết kiệm thời gian bằng cách tái sử dụng context. Hai cơ chế phối hợp tốt khi vòng đời của resource và context được thiết kế đồng bộ; nếu không, bean có thể giữ endpoint cũ và tạo ra lỗi kết nối khó tái hiện.
