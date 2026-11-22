# Rủi ro cần kiểm chứng trong ứng dụng dùng Spring

Spring giúp ứng dụng được lắp ghép từ các bean, cấu hình, bộ chuyển đổi HTTP, tầng dữ liệu và nhiều cơ chế chạy nền. Những cơ chế này làm ứng dụng dễ mở rộng, nhưng cũng tạo ra các rủi ro khó thấy nếu chỉ kiểm thử từng hàm Java riêng lẻ. Một service có thể chạy đúng khi được tạo bằng `new`, nhưng hoạt động khác khi Spring quản lý nó; một repository có thể qua được kiểm thử với cơ sở dữ liệu giả lập nhưng lỗi khi chạy trên hệ quản trị thật; một endpoint có thể trả về đúng dữ liệu trong trường hợp thông thường nhưng bỏ sót quyền truy cập hoặc xử lý sai khi đầu vào không hợp lệ.

Vì vậy, kiểm thử ứng dụng Spring cần trả lời hai câu hỏi song song: **logic nghiệp vụ có đúng không, và các thành phần do Spring kết nối có phối hợp đúng trong môi trường chạy thực tế không?** Bài học này tập trung vào những rủi ro cần nhận diện, cách chọn mức kiểm thử phù hợp và bằng chứng nên thu thập để phát hiện lỗi trước khi phát hành.

## 1. Cấu hình và khởi tạo ApplicationContext

`ApplicationContext` là nơi Spring tìm, tạo và kết nối các bean. Lỗi ở bước này có thể khiến ứng dụng không khởi động, hoặc khởi động được nhưng sử dụng nhầm cấu hình.

Các rủi ro thường gặp gồm:

- Một bean không được quét vì nằm ngoài phạm vi component scan hoặc thiếu cấu hình import.
- Có nhiều bean cùng kiểu nhưng không có `@Primary` hoặc `@Qualifier` phù hợp, dẫn đến lỗi inject hoặc chọn sai implementation.
- Một bean chỉ được tạo trong profile hay điều kiện cấu hình khác với môi trường triển khai.
- Giá trị property thiếu, sai kiểu, sai tên hoặc bị ghi đè bởi nguồn cấu hình có độ ưu tiên cao hơn.
- Cấu hình khởi tạo tạo vòng phụ thuộc, hoặc một bean khởi tạo quá sớm khi dependency chưa sẵn sàng.

Không nên chỉ kiểm tra rằng một class có annotation `@Component` hay `@Service`. Điều cần xác nhận là **context thực sự tạo được bean cần thiết và dùng đúng cấu hình trong profile mục tiêu**.

Ví dụ kiểm tra một nhóm bean quan trọng trong context:

```java
@SpringBootTest
@ActiveProfiles("test")
class ApplicationContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsTheRequiredApplicationBeans() {
        assertNotNull(context.getBean(OrderService.class));
        assertNotNull(context.getBean(OrderRepository.class));
        assertNotNull(context.getBean(PaymentGateway.class));
    }
}
```

Đây là ví dụ cho ứng dụng Spring Boot; với ứng dụng Spring Framework thuần, có thể khởi tạo context từ cấu hình Java hoặc XML tương ứng. Không cần viết một bài kiểm thử liệt kê mọi bean. Hãy tập trung vào các bean quyết định luồng nghiệp vụ, bảo mật, lưu trữ và tích hợp.

Với cấu hình có nhiều profile, hãy kiểm tra ít nhất profile dùng trong kiểm thử và các khác biệt quan trọng của profile triển khai. Đặc biệt chú ý các property bắt buộc như URL dịch vụ, thời gian chờ, giới hạn kết nối và thông tin định danh. Không đưa secret thật vào mã kiểm thử; dùng giá trị giả hoặc secret được cấp riêng cho môi trường kiểm thử.

## 2. Dependency Injection và hành vi của proxy

Dependency Injection giúp Spring cấp dependency cho đối tượng. Rủi ro xuất hiện khi ứng dụng có nhiều implementation, dùng qualifier không nhất quán, hoặc tự tạo đối tượng thay vì để container quản lý.

Ví dụ, `OrderService` có thể cần `PaymentGateway` cho thanh toán trực tuyến và `TestPaymentGateway` trong môi trường kiểm thử. Nếu profile hoặc qualifier cấu hình sai, ứng dụng có thể gọi nhầm cổng thanh toán. Kiểm thử cần xác nhận implementation được inject ở đúng cấu hình, đồng thời kiểm tra hành vi thông qua bean do Spring quản lý.

Một điểm dễ bị bỏ sót là các annotation như `@Transactional`, `@Async`, `@Cacheable` và một số annotation AOP hoạt động thông qua proxy. Khi một phương thức được gọi từ bên ngoài bean, lời gọi có thể đi qua proxy để áp dụng transaction, chạy bất đồng bộ hoặc truy cập cache. Nhưng nếu một phương thức trong cùng class gọi trực tiếp phương thức có annotation, lời gọi nội bộ thường không đi qua proxy. Khi đó annotation có thể không tạo ra hiệu ứng mà lập trình viên mong đợi.

Ví dụ về lời gọi nội bộ:

```java
@Service
class OrderService {

    public void placeOrder() {
        saveOrder();
    }

    @Transactional
    public void saveOrder() {
        // Ghi dữ liệu đơn hàng
    }
}
```

Nếu `placeOrder()` gọi `saveOrder()` trực tiếp trên cùng đối tượng, transaction được khai báo trên `saveOrder()` có thể không được kích hoạt như mong muốn. Cách kiểm chứng đúng là gọi bean qua Spring context và quan sát kết quả transaction, thay vì tự khởi tạo `new OrderService()` rồi chỉ kiểm tra kết quả của hàm.

Khi kiểm thử các tính năng dựa trên proxy, hãy xác nhận:

- Đối tượng được lấy từ Spring container.
- Lời gọi đi qua ranh giới proxy theo thiết kế.
- Cấu hình proxy phù hợp với kiểu bean và phương thức đang dùng.
- Hành vi quan sát được đúng với hợp đồng: transaction được mở, cache được dùng, tác vụ được gửi sang executor hoặc phương thức được validate.

## 3. Ranh giới HTTP: routing, dữ liệu và lỗi

Với ứng dụng Spring MVC hoặc Spring WebFlux, controller là ranh giới giữa HTTP và logic ứng dụng. Kiểm thử chỉ gọi trực tiếp phương thức controller sẽ bỏ qua một phần quan trọng của quá trình xử lý request.

Các rủi ro cần kiểm chứng gồm:

- URL, HTTP method, path variable, query parameter hoặc header được ánh xạ sai.
- JSON không được deserialize đúng, hoặc response có tên trường, kiểu dữ liệu hay định dạng ngày giờ không đúng hợp đồng API.
- Validation không chạy, thiếu ràng buộc, hoặc lỗi validation bị chuyển thành response không nhất quán.
- Exception bị xử lý sai, làm lộ stack trace hoặc biến lỗi nghiệp vụ thành HTTP 500 không cần thiết.
- Content type, encoding, phân trang hoặc sắp xếp không được xử lý đúng.
- Request bị chấp nhận dù thiếu dữ liệu bắt buộc, hoặc bị từ chối dù hợp lệ.

Kiểm thử slice với `@WebMvcTest` giúp dựng phần MVC cần thiết mà không phải khởi tạo toàn bộ ứng dụng. Có thể thay thế service bằng mock để tập trung vào mapping, validation và định dạng response. Ví dụ dưới đây dùng `@MockitoBean` của Spring Framework 6.2 trở lên; ở các phiên bản Spring Boot cũ hơn, dự án có thể đang dùng `@MockBean`.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void rejectsAnInvalidCreateRequest() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":"", "items":[]}
                    """))
            .andExpect(status().isBadRequest());
    }
}
```

Một bài kiểm thử endpoint nên xác nhận cả status code và phần body có ý nghĩa. Với lỗi validation, hãy kiểm tra cấu trúc lỗi mà client dựa vào; với lỗi nghiệp vụ, hãy kiểm tra mã lỗi ổn định thay vì phụ thuộc vào thông báo nội bộ có thể thay đổi.

Nếu ứng dụng dùng WebFlux, hãy kiểm tra đúng stack reactive. Không nên suy luận rằng một kiểm thử MVC chứng minh được hành vi của WebFlux, vì pipeline, kiểu trả về và cách xử lý backpressure khác nhau.

## 4. Xác thực và phân quyền

Một request có thể đúng về dữ liệu nhưng vẫn nguy hiểm nếu người gọi không có quyền thực hiện thao tác. Rủi ro bảo mật thường nằm ở chỗ cấu hình filter chain, quyền theo role, quyền theo tài nguyên hoặc method security không được áp dụng đồng nhất.

Hãy kiểm chứng riêng các tình huống:

- Người chưa đăng nhập truy cập tài nguyên cần xác thực.
- Người đã đăng nhập nhưng thiếu quyền gọi endpoint hoặc method.
- Người có quyền trên tài nguyên của mình nhưng không được truy cập tài nguyên của người khác.
- Token hết hạn, sai chữ ký, sai issuer hoặc thiếu claim bắt buộc.
- CSRF, CORS và chính sách session được cấu hình đúng với loại client.
- Quyền ở tầng method (`@PreAuthorize`, chẳng hạn) vẫn được áp dụng khi method được gọi qua đường đi thực tế.

Với Spring Security Test, có thể tạo request mang danh tính giả để kiểm tra chính sách mà không cần gọi hệ thống xác thực thật:

```java
mockMvc.perform(get("/admin/reports")
        .with(user("linh").roles("USER")))
    .andExpect(status().isForbidden());
```

Đừng chỉ kiểm tra một trường hợp được phép. Bộ kiểm thử phân quyền cần có cả trường hợp bị từ chối, đặc biệt là truy cập chéo dữ liệu giữa hai người dùng hoặc hai tenant. Một lỗi phân quyền thường nghiêm trọng hơn lỗi định dạng response, nên cần ưu tiên kiểm thử ở cả endpoint và tầng nghiệp vụ có ranh giới quyền.

## 5. Persistence, mapping và transaction

Repository có thể trả về kết quả đúng với dữ liệu đơn giản nhưng thất bại khi gặp quan hệ entity, constraint, kiểu dữ liệu hoặc hành vi transaction thực tế.

Những rủi ro phổ biến:

- Mapping entity sai tên cột, kiểu dữ liệu, khóa chính hoặc quan hệ.
- Cascade và orphan removal xóa hoặc giữ dữ liệu ngoài dự kiến.
- Lazy loading gây lỗi khi session đã đóng, hoặc tạo truy vấn N+1.
- Query hoạt động trên H2 nhưng khác hành vi trên PostgreSQL, MySQL hay hệ quản trị dùng ở production.
- Unique constraint, foreign key, nullability hoặc index không phản ánh đúng quy tắc nghiệp vụ.
- Transaction bị commit quá sớm, rollback không đúng, hoặc nhiều thao tác chỉ được ghi một phần.
- Isolation level không đáp ứng yêu cầu khi nhiều request cập nhật cùng dữ liệu.

`@DataJpaTest` phù hợp để kiểm tra mapping và repository. Khi kiểm tra việc lưu và đọc lại entity, nên gọi `flush()` rồi `clear()` trước khi truy vấn lại. Việc này buộc persistence context đẩy thay đổi xuống database và tránh đọc lại cùng đối tượng đang nằm trong bộ nhớ.

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @PersistenceContext
    EntityManager entityManager;

    @Test
    void persistsAndReloadsAnOrder() {
        Order saved = orderRepository.save(new Order("customer-42"));

        entityManager.flush();
        entityManager.clear();

        Order reloaded = orderRepository.findById(saved.getId())
            .orElseThrow();

        assertEquals("customer-42", reloaded.getCustomerId());
    }
}
```

Đoạn mã minh họa ý tưởng; constructor và getter cần khớp với entity của dự án. Nếu production dùng một hệ quản trị cụ thể, hãy bổ sung kiểm thử tích hợp bằng database cùng loại, thường có thể khởi chạy qua Testcontainers. Database thay thế trong bộ kiểm thử nhanh vẫn hữu ích, nhưng không chứng minh được mọi khác biệt về dialect, locking, JSON column, sequence, collation hay constraint.

Transaction cần được kiểm tra ở mức service khi một nghiệp vụ gồm nhiều thao tác. Ví dụ đặt hàng có thể tạo đơn, trừ tồn kho và ghi lịch sử. Nếu bước cuối lỗi, trạng thái trước đó phải được rollback theo yêu cầu. Cần kiểm tra cả đường thành công lẫn đường thất bại giữa chừng.

Lưu ý rằng nhiều test slice tự chạy trong transaction và rollback khi kết thúc. Điều này thuận tiện để cô lập dữ liệu, nhưng có thể che khuất hành vi commit thực tế, sự kiện `afterCommit`, hoặc transaction được mở ở một thread khác. Với các trường hợp đó, hãy thiết kế bài kiểm thử tích hợp có ranh giới transaction rõ ràng và xác nhận trạng thái từ một transaction hoặc kết nối mới.

## 6. Tích hợp với dịch vụ bên ngoài

Ứng dụng Spring thường gọi API thanh toán, dịch vụ định danh, hệ thống gửi email, kho file, message broker hoặc dịch vụ nội bộ khác. Rủi ro không chỉ là phản hồi thành công hay thất bại, mà còn là timeout, phản hồi sai định dạng, lỗi tạm thời, giới hạn tốc độ và trạng thái không chắc chắn sau khi kết nối bị ngắt.

Đối với mỗi tích hợp, hãy xác định và kiểm thử:

- Timeout kết nối và timeout đọc có giới hạn hợp lý.
- Lỗi 4xx, 5xx, timeout và lỗi mạng được phân loại đúng.
- Retry chỉ áp dụng cho lỗi có thể thử lại; không lặp thao tác không idempotent một cách mù quáng.
- Client xử lý được response thiếu trường, trường null hoặc định dạng không hợp lệ.
- Secret, token và header xác thực được truyền đúng nhưng không xuất hiện trong log.
- Khi dịch vụ ngoài ngừng hoạt động, ứng dụng trả về trạng thái có kiểm soát và không giữ tài nguyên vô hạn.

Với client HTTP, có thể dùng mock server để điều khiển response và xác nhận request được gửi đi. Với Spring Boot, `@RestClientTest` hỗ trợ kiểm thử một số cấu hình client; `MockRestServiceServer`, WireMock hoặc MockWebServer là lựa chọn tùy loại client. Với message broker hoặc database thật, Testcontainers giúp kiểm tra giao thức và cấu hình gần môi trường chạy hơn.

Mock giúp tạo nhanh các tình huống hiếm như timeout hoặc response lỗi. Tuy nhiên, ít nhất một lớp kiểm thử tích hợp nên xác nhận endpoint, serialization, authentication và cấu hình kết nối thực sự tương thích với hệ thống đích hoặc môi trường mô phỏng đáng tin cậy.

## 7. Tác vụ bất đồng bộ, scheduler và event

Các annotation như `@Async`, `@Scheduled` và cơ chế application event thay đổi thời điểm thực thi. Một lời gọi trả về thành công có thể chỉ có nghĩa tác vụ đã được xếp hàng, không có nghĩa công việc đã hoàn tất.

Rủi ro cần kiểm chứng:

- Tác vụ không được gửi tới executor, hoặc executor bị bão hòa.
- Exception trong thread nền không được quan sát và xử lý.
- Test kết thúc trước khi tác vụ hoàn thành, tạo kết quả chập chờn.
- Scheduler chạy trùng, chạy sai múi giờ hoặc kích hoạt lại khi ứng dụng có nhiều instance.
- Event được phát trước khi transaction commit, khiến listener đọc dữ liệu chưa sẵn sàng.
- Một message hoặc event được xử lý nhiều lần nhưng handler không idempotent.

Không nên dùng `Thread.sleep()` với thời gian tùy ý để chờ tác vụ. Hãy chờ qua `Future`/`CompletableFuture`, latch hoặc thư viện chờ điều kiện như Awaitility, với timeout rõ ràng. Đối với scheduler, tách phần xử lý nghiệp vụ thành service có thể gọi trực tiếp trong unit test; sau đó kiểm tra cấu hình trigger và việc đăng ký scheduler ở lớp tích hợp.

Nếu một listener cần chạy sau khi transaction commit, hãy kiểm tra đúng thời điểm đó bằng dữ liệu được đọc từ transaction độc lập. Với consumer message, cần kiểm tra ack/nack, retry, dead-letter và khả năng xử lý lặp theo chính sách của hệ thống.

## 8. Cache và trạng thái dùng chung

Cache có thể làm giảm tải, nhưng dễ gây lỗi dữ liệu cũ hoặc rò rỉ dữ liệu giữa người dùng nếu key không chứa đủ ngữ cảnh. Kiểm thử nên xác nhận:

- Cache key phân biệt đúng tenant, người dùng hoặc tham số ảnh hưởng kết quả.
- Dữ liệu được evict hoặc cập nhật sau thao tác ghi.
- TTL và chính sách hết hạn phù hợp.
- Cache miss, cache lỗi hoặc cache không khả dụng không làm hỏng luồng nghiệp vụ ngoài dự kiến.
- Nhiều request đồng thời không tạo trạng thái sai do cập nhật đua.

Đối với `@Cacheable` và `@CacheEvict`, hãy gọi bean qua Spring context để proxy được áp dụng. Kiểm tra cả kết quả trả về lẫn số lần service hoặc repository thực sự được gọi. Nếu dùng cache phân tán trong production, một kiểm thử với cache in-memory không đủ chứng minh cấu hình serialization, key hoặc eviction trên hệ thống phân tán.

## 9. Hiệu năng và khả năng chịu lỗi

Một bài kiểm thử chức năng có thể chạy nhanh với vài bản ghi nhưng chậm nghiêm trọng khi dữ liệu tăng. Các nguyên nhân thường gặp là N+1 query, thiếu index, truy vấn không giới hạn, giữ transaction quá lâu, pool kết nối cạn hoặc retry đồng loạt làm tăng tải khi dịch vụ ngoài gặp sự cố.

Nên xác định trước các ngưỡng có ý nghĩa với sản phẩm: thời gian phản hồi, thông lượng, số kết nối, kích thước batch, độ trễ xử lý message và tỷ lệ lỗi. Dùng dữ liệu gần với phân bố thực tế để kiểm tra các luồng có rủi ro cao. Với database, xem SQL và query plan; với HTTP client, quan sát timeout và số lần retry; với executor, kiểm tra hàng đợi và số thread.

Kiểm thử tải và kiểm thử sức bền phù hợp cho các mục tiêu này. Chúng bổ sung cho unit test và integration test, chứ không thay thế việc kiểm tra logic. Khi có retry, circuit breaker hoặc giới hạn đồng thời, hãy kiểm tra cả trạng thái bình thường lẫn lúc dependency chậm hoặc ngừng phản hồi.

## 10. Quan sát lỗi và bảo vệ thông tin

Khi có lỗi trong production, log, metric và trace giúp xác định nguyên nhân. Nhưng việc ghi log quá nhiều hoặc đưa dữ liệu nhạy cảm vào log lại tạo ra rủi ro riêng.

Kiểm chứng rằng:

- Lỗi quan trọng được ghi nhận với correlation ID hoặc trace ID phù hợp.
- Log có đủ ngữ cảnh để điều tra nhưng không chứa password, token, secret hay dữ liệu cá nhân không cần thiết.
- Metric phân biệt được lỗi nghiệp vụ và lỗi hạ tầng, đồng thời tránh nhãn có cardinality quá cao.
- Exception được chuyển thành response đúng hợp đồng và không để lộ thông tin nội bộ.
- Health check phản ánh đúng trạng thái dependency cần thiết; không đánh dấu ứng dụng khỏe khi thành phần bắt buộc đã mất kết nối.

Không nhất thiết kiểm tra từng câu chữ của log. Hãy kiểm tra các thuộc tính có ý nghĩa vận hành, chẳng hạn có mã tương quan, có loại lỗi, không có token và không làm lộ stack trace ra response công khai.

## 11. Môi trường chạy, migration và vòng đời ứng dụng

Một ứng dụng có thể chạy tốt trong IDE nhưng thất bại khi đóng gói hoặc triển khai. Sự khác biệt thường đến từ biến môi trường, timezone, locale, quyền truy cập file, migration database, thứ tự khởi động hoặc cách tắt ứng dụng.

Các tình huống cần xem xét:

- Property bắt buộc không được cấp trong môi trường triển khai.
- Migration thất bại khi chạy trên schema có dữ liệu cũ hoặc khi nhiều instance khởi động gần nhau.
- Ứng dụng nhận thời gian theo timezone khác với kỳ vọng nghiệp vụ.
- Graceful shutdown không chờ request hoặc message đang xử lý theo chính sách.
- Health/readiness check cho phép nhận traffic trước khi ứng dụng sẵn sàng.
- Khác biệt phiên bản JDK, thư viện hoặc cấu hình logging làm thay đổi hành vi.

Các rủi ro này cần được kiểm tra ở pipeline đóng gói, môi trường staging hoặc môi trường triển khai gần production. Kiểm thử trong một context đơn lẻ không thể chứng minh toàn bộ hành vi khi rollout, restart hoặc nâng cấp schema.

## 12. Chọn đúng lớp kiểm thử

Không phải rủi ro nào cũng cần `@SpringBootTest`. Chọn lớp kiểm thử dựa trên cơ chế có thể gây lỗi và bằng chứng cần thu thập.

| Lớp kiểm thử | Phù hợp để xác nhận | Ví dụ công cụ/cách làm |
| --- | --- | --- |
| Unit test | Quy tắc nghiệp vụ thuần, nhánh điều kiện, tính toán và xử lý lỗi | JUnit 5, Mockito; tạo đối tượng trực tiếp khi không cần Spring |
| Spring context test | Bean wiring, profile, property và cấu hình ứng dụng | `@SpringBootTest`, context từ Java/XML config |
| Slice test | Một ranh giới Spring cụ thể | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest` trong Spring Boot |
| Integration test | Nhiều thành phần phối hợp với database, broker hoặc dịch vụ mô phỏng | Testcontainers, WireMock, mock server |
| Contract test | Hai hệ thống thống nhất request, response và schema | Consumer/provider contract hoặc schema validation |
| End-to-end test | Luồng người dùng xuyên qua các ranh giới chính | Môi trường staging hoặc môi trường kiểm thử tích hợp |
| Load/resilience test | Độ trễ, thông lượng và hành vi khi dependency suy giảm | Công cụ tạo tải, metric, trace và fault injection |

Unit test nên chiếm phần lớn vì nhanh và dễ định vị lỗi. Tuy nhiên, các rủi ro do Spring tạo ra như proxy, filter chain, mapping, transaction và cấu hình context cần có kiểm thử chạy qua chính cơ chế Spring tương ứng.

`@SpringBootTest` hữu ích khi cần khởi tạo gần toàn bộ ứng dụng, nhưng nếu dùng cho mọi trường hợp, bộ kiểm thử sẽ chậm và lỗi khó định vị. Slice test giúp giới hạn phạm vi; integration test với hạ tầng thật giúp phát hiện khác biệt mà mock không thể mô phỏng.

## 13. Ma trận rủi ro và bằng chứng cần có

Bảng sau gợi ý cách chuyển một rủi ro thành một phép kiểm chứng có thể quan sát. Mức ưu tiên cuối cùng phụ thuộc vào tác động nghiệp vụ, xác suất xảy ra và khả năng phát hiện sau triển khai.

| Rủi ro | Hậu quả có thể xảy ra | Bằng chứng kiểm thử nên thu thập |
| --- | --- | --- |
| Bean hoặc profile cấu hình sai | Ứng dụng không khởi động hoặc dùng nhầm implementation | Context khởi tạo được; bean và property quan trọng đúng ở profile mục tiêu |
| Proxy không được áp dụng | Transaction, cache hoặc async không hoạt động | Gọi bean qua context và quan sát hiệu ứng thực tế |
| API mapping/validation sai | Client nhận response sai hoặc dữ liệu không hợp lệ lọt vào | Request HTTP thực qua MockMvc/WebTestClient; kiểm tra status và body |
| Phân quyền thiếu | Người dùng đọc hoặc sửa dữ liệu trái phép | Các trường hợp unauthenticated, forbidden và truy cập chéo tài nguyên |
| Mapping/query database sai | Mất dữ liệu, lỗi truy vấn hoặc hiệu năng kém | Flush/clear/readback; constraint và truy vấn trên database tương thích production |
| Transaction không nguyên tử | Nghiệp vụ chỉ ghi được một phần | Gây lỗi giữa luồng và xác nhận rollback/commit đúng |
| Dịch vụ ngoài chậm hoặc lỗi | Request treo, retry quá mức hoặc trạng thái không chắc chắn | Timeout, lỗi mạng, 4xx/5xx và retry được điều khiển trong mock server |
| Tác vụ nền/event chạy sai thời điểm | Mất, lặp hoặc xử lý dữ liệu chưa commit | Chờ hoàn tất có timeout; xác nhận idempotency và thời điểm phát event |
| Cache sai key hoặc không evict | Trả dữ liệu cũ hoặc lẫn dữ liệu người dùng | Kiểm tra key, số lần gọi và hành vi sau cập nhật |
| Quá tải hoặc thiếu tài nguyên | Độ trễ tăng, lỗi dây chuyền | Load test, metric pool/executor và kiểm thử dependency suy giảm |
| Log/response lộ thông tin | Rò rỉ secret hoặc dữ liệu cá nhân | Kiểm tra response và log không chứa trường nhạy cảm |
| Migration/khởi động triển khai lỗi | Không thể rollout hoặc restart an toàn | Chạy migration trên schema có dữ liệu; kiểm tra readiness và shutdown |

## 14. Xây dựng chiến lược kiểm thử theo luồng nghiệp vụ

Hãy bắt đầu từ một luồng có giá trị cao, chẳng hạn tạo đơn hàng. Liệt kê các ranh giới mà luồng đi qua: controller, xác thực, service, transaction, repository, cổng thanh toán và event phát sau khi lưu thành công. Với từng ranh giới, xác định điều gì có thể sai và chọn phép kiểm chứng tương ứng.

Ví dụ cho luồng tạo đơn:

1. **Unit test service:** kiểm tra quy tắc tính tổng tiền, trạng thái đơn hàng và điều kiện từ chối đơn không hợp lệ.
2. **MVC/security slice:** gửi request HTTP hợp lệ và không hợp lệ; kiểm tra validation, xác thực và quyền sở hữu dữ liệu.
3. **Repository integration:** lưu rồi đọc lại đơn hàng; xác nhận quan hệ, constraint và truy vấn trên database tương thích.
4. **Transaction integration:** làm cho bước thanh toán hoặc ghi dữ liệu thất bại; xác nhận trạng thái được rollback hoặc chuyển sang trạng thái bù trừ đúng thiết kế.
5. **External client test:** mô phỏng thanh toán timeout, từ chối và thành công; xác nhận timeout, retry và idempotency.
6. **Event test:** xác nhận event chỉ được phát ở thời điểm phù hợp và consumer xử lý lặp an toàn.
7. **End-to-end test:** chạy một luồng thành công qua môi trường tích hợp để kiểm tra cấu hình và wiring tổng thể.

Không nhất thiết đưa mọi tổ hợp vào end-to-end test. Những nhánh nghiệp vụ nên được kiểm tra ở unit hoặc slice test; end-to-end chỉ nên giữ các luồng đại diện đủ giá trị để xác nhận các thành phần đã được kết nối đúng.

## 15. Những cách kiểm thử dễ tạo cảm giác an toàn giả

Một bộ kiểm thử có nhiều test vẫn có thể bỏ sót rủi ro nếu tất cả cùng kiểm tra một lớp hành vi. Hãy chú ý các tình huống sau:

- **Mock toàn bộ dependency:** test chứng minh logic của class nhưng không chứng minh Spring inject đúng bean, proxy hoạt động hay query chạy được.
- **Chỉ kiểm tra đường thành công:** lỗi timeout, quyền bị từ chối, rollback và dữ liệu biên thường là nơi rủi ro tập trung.
- **Chỉ dùng database thay thế:** test nhanh có ích, nhưng khác biệt dialect và constraint có thể chỉ xuất hiện trên database production.
- **Tạo đối tượng bằng `new` cho mọi test:** phù hợp với unit test thuần, nhưng bỏ qua các hành vi dựa trên container và proxy.
- **Dùng `@SpringBootTest` cho mọi bài:** làm test chậm và khiến lỗi ở một cấu hình nhỏ khó được khoanh vùng.
- **Chờ tác vụ bằng `Thread.sleep()` cố định:** dễ tạo test chập chờn theo tải máy và thời gian thực thi.
- **Dùng dữ liệu dùng chung hoặc phụ thuộc thứ tự chạy:** khiến kết quả thay đổi theo thứ tự, chạy song song hoặc trạng thái môi trường.
- **Chỉ kiểm tra status code:** response có thể là 200 nhưng chứa dữ liệu sai, hoặc lỗi có status đúng nhưng sai mã lỗi mà client cần.

Một phép kiểm thử tốt phải có điều kiện đầu vào rõ ràng, hành động cụ thể và kết quả quan sát được. Với rủi ro quan trọng, nên kiểm tra cả điều kiện bình thường và ít nhất một tình huống lỗi có khả năng xảy ra.

## 16. Câu hỏi định hướng khi thiết kế test

Trước khi viết test cho một tính năng Spring, hãy tự hỏi:

- Thành phần nào do Spring tạo hoặc cấu hình, và cấu hình sai sẽ gây hậu quả gì?
- Hành vi nào phụ thuộc proxy, transaction, security filter, serializer hoặc lifecycle?
- Có ranh giới nào gọi ra hệ thống bên ngoài, và điều gì xảy ra khi hệ thống đó chậm hoặc không phản hồi?
- Dữ liệu nào có thể bị ghi một phần, đọc sai, cache cũ hoặc truy cập trái quyền?
- Kiểm thử hiện tại có đi qua đúng cơ chế cần xác nhận không?
- Kết quả nào chứng minh rủi ro đã được kiểm soát, và kết quả nào chỉ chứng minh một mock đã được gọi?
- Có cần database, broker hoặc môi trường gần production để kiểm tra khác biệt cấu hình không?

Khi trả lời được các câu hỏi này, nhóm phát triển có thể chọn một bộ kiểm thử cân bằng: unit test bảo vệ quy tắc nghiệp vụ, slice test kiểm tra ranh giới Spring, integration test xác nhận hạ tầng và cấu hình, còn end-to-end cùng load/resilience test kiểm chứng những luồng có tác động lớn. Mục tiêu là tạo bằng chứng phù hợp với rủi ro thực tế của ứng dụng, để lỗi được phát hiện ở nơi dễ hiểu và dễ sửa nhất.
