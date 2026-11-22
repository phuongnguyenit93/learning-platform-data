# Những nơi Spring dùng SpEL trong hệ sinh thái

Spring Expression Language (SpEL) là ngôn ngữ biểu thức mà nhiều thành phần của Spring dùng để đọc thuộc tính, truy cập tham số, gọi phương thức, tính toán giá trị hoặc quyết định một hành vi tại một điểm cụ thể trong vòng đời ứng dụng. Vì vậy, khi nhìn toàn bộ hệ sinh thái Spring, SpEL xuất hiện ở nhiều nơi: cấu hình bean, điều kiện xử lý event, cache, phân quyền, truy vấn dữ liệu, batch job và luồng message.

Điểm quan trọng là **mỗi integration point cung cấp một evaluation context riêng**. Cùng một biểu thức có thể hợp lệ trong một annotation nhưng không có cùng biến hoặc đối tượng gốc ở annotation khác. Hãy xem SpEL như một phần của API mà từng module công bố, thay vì giả định rằng mọi chuỗi cấu hình của Spring đều được diễn giải bằng SpEL.

## 1. Nhận diện cú pháp và ngữ cảnh

Một số thành phần nhận biểu thức SpEL trong dấu **#{...}**. Một số annotation nhận trực tiếp phần biểu thức, chẳng hạn **@Cacheable(key = "#isbn")** hoặc **@PreAuthorize("hasRole('ADMIN')")**. Cú pháp cụ thể phụ thuộc vào nơi tích hợp.

Các thành phần thường gặp trong biểu thức:

| Cú pháp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **#name** | Biến hoặc tham số có tên trong evaluation context | **#isbn**, **#root** |
| **@beanName** | Tham chiếu Spring bean theo tên | **@permissionService.canRead(#order)** |
| **T(Type)** | Tham chiếu kiểu Java để gọi thành viên static hoặc tạo giá trị theo cú pháp được hỗ trợ | **T(java.lang.Math).max(3, 7)** |
| **.property** | Đọc thuộc tính/getter | **payload.total** |
| **[key]** | Truy cập phần tử map hoặc collection | **headers['tenantId']** |
| **method(...)** | Gọi phương thức được phép trong evaluation context | **#name.toUpperCase()** |

Cần phân biệt hai dạng thường xuất hiện cạnh nhau:

- **${app.currency}** là **property placeholder**: lấy giá trị cấu hình từ **Environment** hoặc nguồn thuộc tính.
- **#{...}** là **SpEL expression**: đánh giá một biểu thức trong context do thành phần Spring cung cấp.

Ví dụ:

~~~java
@Value("${app.currency:VND}")
private String currency;             // placeholder

@Value("#{systemProperties['user.country']}")
private String country;              // SpEL
~~~

Không nên suy ra rằng mọi giá trị trong **application.properties** hoặc **application.yml** đều tự động chạy qua SpEL. Chỉ những điểm tích hợp có hỗ trợ expression mới đánh giá biểu thức. Một số annotation cho phép kết hợp placeholder với SpEL; cần kiểm tra tài liệu của đúng annotation và phiên bản đang dùng.

## 2. Các điểm tích hợp phổ biến

### 2.1. Spring Framework Core Container — inject giá trị và tham chiếu bean

**@Value** cho phép inject giá trị từ property placeholder hoặc từ biểu thức SpEL. SpEL hữu ích khi giá trị cần lấy từ system property, thuộc tính của bean khác hoặc một phép tính đơn giản.

~~~java
@Component
class RuntimeSettings {

    @Value("#{systemProperties['user.country']}")
    private String country;

    @Value("#{pricingRules.defaultTaxRate}")
    private BigDecimal taxRate;
}
~~~

Trong ví dụ, **systemProperties** là dữ liệu có sẵn trong context; **pricingRules** là bean được tham chiếu theo tên. Với giá trị cấu hình thông thường, ưu tiên placeholder như **${app.tax-rate}** vì ý định rõ ràng và dễ quản lý theo môi trường. Dùng SpEL khi thật sự cần đánh giá biểu thức.

### 2.2. Spring Application Events — lọc event bằng điều kiện

**@EventListener** có thuộc tính **condition** nhận SpEL. Listener chỉ được gọi khi biểu thức trả về **true**.

~~~java
@Component
class OrderEventListener {

    @EventListener(condition = "#root.args[0].total >= 1000000")
    public void handleLargeOrder(OrderCreatedEvent event) {
        // xử lý đơn hàng có tổng tiền từ 1.000.000 trở lên
    }
}
~~~

Context của event listener cung cấp event và các đối số của phương thức. Có thể truy cập đối số qua **#root.args**, hoặc dùng tên tham số khi tên đó được Spring phát hiện. Cách dùng **#root.args[0]** làm rõ rằng biểu thức đang đọc đối số đầu tiên.

Phù hợp với điều kiện lọc ngắn, gắn trực tiếp với event. Nếu quy tắc cần truy vấn dữ liệu, nhiều nhánh hoặc có logic nghiệp vụ phức tạp, hãy chuyển phần quyết định vào một bean/service và gọi nó từ biểu thức.

### 2.3. Spring Cache — tạo cache key và quyết định cache

Các annotation **@Cacheable**, **@CachePut** và **@CacheEvict** hỗ trợ SpEL cho các thuộc tính như **key**, **condition** và **unless**.

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#isbn.rawNumber",
    condition = "#isbn != null",
    unless = "#result == null"
)
public Book findBook(ISBN isbn) {
    // đọc dữ liệu
}
~~~

- **key**: xác định khóa cache từ tham số hoặc metadata của lời gọi.
- **condition**: được đánh giá trước khi phương thức được thực thi; **false** nghĩa là bỏ qua cache cho lời gọi đó.
- **unless**: được đánh giá sau khi có kết quả; **true** ngăn kết quả được đưa vào cache.
- **#result**: tham chiếu kết quả trả về trong những biểu thức hỗ trợ kết quả.

Cache expression còn có root object chứa metadata của phương thức, chẳng hạn method, target và arguments. Dùng **key** để tạo khóa ổn định, có ý nghĩa; tránh đưa các đối tượng lớn hoặc giá trị thay đổi liên tục vào khóa nếu điều đó làm giảm hiệu quả cache.

### 2.4. Spring Security — phân quyền ở mức phương thức

Method Security dùng SpEL để biểu đạt quyền truy cập dựa trên authority, principal, authentication, tham số phương thức hoặc đối tượng trả về. Cần bật method security, ví dụ bằng **@EnableMethodSecurity**.

~~~java
@Service
class InvoiceService {

    @PreAuthorize(
        "hasAuthority('invoice:read') and " +
        "#tenantId == authentication.principal.tenantId"
    )
    public Invoice findInvoice(String tenantId, long invoiceId) {
        // ...
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Invoice readOwnedInvoice(long invoiceId) {
        // ...
    }
}
~~~

- **@PreAuthorize**: kiểm tra trước khi gọi phương thức; thường dùng cho điều kiện truy cập dựa trên quyền và tham số.
- **@PostAuthorize**: kiểm tra sau khi có kết quả; có thể dùng để xác nhận người dùng sở hữu đối tượng được trả về.
- **authentication**, **principal**, **hasAuthority(...)**, **hasRole(...)** là các thành phần được Spring Security đưa vào security expression context.

Tên tham số như **#tenantId** phải được Spring phát hiện đúng. Tùy cách biên dịch và cấu hình, có thể cần bật lưu tên tham số bằng **-parameters** hoặc dùng annotation hỗ trợ như **@P**.

Không nên đặt kiểm tra hậu điều kiện **@PostAuthorize** lên phương thức ghi dữ liệu nếu việc ghi đã xảy ra trước khi quyền được kiểm tra. Với logic phân quyền phức tạp, hãy đặt chính sách trong bean riêng và gọi bean đó từ expression. Giữ biểu thức ngắn để dễ đọc, kiểm thử và rà soát bảo mật.

### 2.5. Spring Data JPA — biểu thức trong @Query

Spring Data JPA hỗ trợ một tập biểu thức giới hạn trong query được khai báo bằng **@Query**. Một trường hợp hữu ích là **#{#entityName}**, đại diện tên entity gắn với repository domain type.

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Query("""
        select u
        from #{#entityName} u
        where u.lastname = ?1
        """)
    List<User> findByLastname(String lastname);
}
~~~

Cách này hữu ích khi viết repository generic hoặc khi muốn query theo tên entity được khai báo trong mapping. Nếu tên entity thay đổi, query không cần hard-code lại tên cũ.

Spring Data còn hỗ trợ value expression cho tham số truy vấn, ví dụ **:#{#filter.status}** khi phương thức nhận một tham số **filter**. Hãy dùng đúng biến và cú pháp mà module Spring Data cụ thể hỗ trợ; không giả định evaluation context của JPA giống context của Spring Security hay Spring Integration.

### 2.6. Spring Batch — late binding cho Job và Step

Batch job thường nhận tham số tại thời điểm chạy, chẳng hạn tên file đầu vào, ngày xử lý hoặc giá trị trong **ExecutionContext**. Spring Batch dùng SpEL để late-bind các giá trị này vào bean có scope **step** hoặc **job**.

~~~java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            // cấu hình mapping và các thuộc tính còn lại
            .build();
}
~~~

Các nguồn dữ liệu thường dùng:

- **jobParameters**: tham số được truyền khi khởi chạy job.
- **jobExecutionContext**: dữ liệu trong execution context của job.
- **stepExecutionContext**: dữ liệu trong execution context của step.

Late binding chỉ hoạt động đúng khi bean được khai báo với scope phù hợp, thường là **@StepScope** hoặc **@JobScope**. Bean cần đọc tham số của step không nên được khởi tạo như singleton thông thường trước khi step bắt đầu, vì lúc đó dữ liệu runtime chưa sẵn sàng.

### 2.7. Spring Integration — thao tác trên Message

Spring Integration dùng SpEL rộng rãi để cấu hình router, filter, transformer, service activator và nhiều endpoint khác. Trong phần lớn trường hợp, root object là **Message**; biểu thức có thể đọc **payload**, **headers** và gọi bean trong application context.

Ví dụ một filter chỉ cho message có tổng tiền lớn hơn 1.000 đi tiếp:

~~~xml
<int:filter
    input-channel="orders"
    expression="payload.total > 1000" />
~~~

Có thể đọc header hoặc gọi bean:

~~~text
headers['tenantId']
@orderPolicy.canProcess(payload)
~~~

**payload** là nội dung chính của message; **headers** là metadata dạng key/value. Một số endpoint bổ sung biến riêng, chẳng hạn tham số request hoặc path variable. Vì vậy, hãy kiểm tra context mà endpoint cụ thể cung cấp trước khi sử dụng một biến.

### 2.8. Spring AMQP — cấu hình listener và định tuyến reply

Spring AMQP cho phép dùng placeholder và SpEL trong thuộc tính của **@RabbitListener**, ví dụ danh sách queue được lấy từ cấu hình:

~~~java
@RabbitListener(
    queues = "#{'${app.orders.queues}'.split(',')}"
)
public void processOrder(Order order) {
    // ...
}
~~~

Với **@SendTo**, Spring AMQP hỗ trợ hai thời điểm đánh giá khác nhau:

- **#{...}**: biểu thức được đánh giá một lần khi khởi tạo listener.
- **!{...}**: biểu thức được đánh giá tại runtime cho từng message; context có **request**, **source** và **result**.

Ví dụ định tuyến reply theo kết quả xử lý:

~~~java
@RabbitListener(queues = "orders")
@SendTo("!{'reply.' + result.region}")
public OrderReply process(Order order) {
    return handle(order);
}
~~~

Cần phân biệt hai dạng delimiter này khi cấu hình reply động. **#{...}** dùng context lúc khởi tạo, còn **!{...}** dùng dữ liệu request/reply của lần xử lý hiện tại.

### 2.9. Spring Retry — quyết định retry theo exception

Spring Retry cung cấp các thuộc tính nhận expression, chẳng hạn **maxAttemptsExpression** và **exceptionExpression**. **exceptionExpression** được đánh giá sau khi chính sách retry cho phép thử lại và có thể dùng exception cuối cùng làm root object.

~~~java
@Retryable(
    exceptionExpression = "@retryPolicy.shouldRetry(#root)"
)
public void sendNotification() {
    // gửi thông báo
}
~~~

Trong ví dụ, **#root** là exception đang được xét và **retryPolicy** là bean chứa quyết định retry. Cách này hữu ích khi chính sách phụ thuộc loại lỗi hoặc nội dung exception. Giữ chính sách tập trung trong bean để dễ kiểm thử và tránh nhồi logic vào annotation.

## 3. So sánh evaluation context theo module

| Điểm tích hợp | Dữ liệu thường truy cập | Mục đích chính |
| --- | --- | --- |
| **@Value / Core Container** | system properties, bean, thuộc tính và giá trị cấu hình | inject giá trị |
| **@EventListener** | event, **#root.args**, tham số listener | lọc event |
| **Spring Cache** | tham số, metadata phương thức, **#result** | tạo key và điều kiện cache |
| **Spring Security** | **authentication**, **principal**, authority, tham số, **returnObject** | phân quyền |
| **Spring Data JPA** | **#entityName**, tham số query | tạo query có thể tái sử dụng |
| **Spring Batch** | **jobParameters**, **jobExecutionContext**, **stepExecutionContext** | late binding |
| **Spring Integration** | **payload**, **headers**, bean | định tuyến và biến đổi message |
| **Spring AMQP** | context khởi tạo hoặc **request** / **source** / **result** | cấu hình listener và reply |
| **Spring Retry** | exception và bean chính sách | quyết định retry |

Bảng này là bản đồ định hướng, không phải một evaluation context dùng chung. Một biến như **#result** có ý nghĩa trong cache hoặc AMQP reply context theo quy tắc riêng của module; không thể mang nguyên xi sang **@EventListener**.

## 4. Cách chọn nơi dùng SpEL

1. **Dùng placeholder cho cấu hình đơn giản.** Nếu chỉ cần lấy **app.timeout** hoặc **app.region**, **${...}** dễ hiểu và phù hợp với cấu hình theo môi trường.
2. **Dùng SpEL tại điểm tích hợp được tài liệu hóa.** Chỉ viết expression trong thuộc tính mà module xác nhận hỗ trợ SpEL.
3. **Xác định dữ liệu context trước khi viết.** Kiểm tra root object, biến có sẵn, cách truy cập tham số và thời điểm expression được đánh giá.
4. **Giữ expression ngắn.** Một điều kiện, khóa cache hoặc phép truy cập thuộc tính đơn giản thường dễ bảo trì hơn một chuỗi nhiều nhánh.
5. **Đưa nghiệp vụ phức tạp vào bean.** Có thể gọi **@policyService.isAllowed(...)** từ SpEL, rồi kiểm thử service như logic Java thông thường.
6. **Tránh side effect.** Expression dùng để đọc và quyết định; không nên dựa vào nó để thay đổi trạng thái hệ thống.
7. **Không đánh giá expression không tin cậy bằng context có quyền rộng.** SpEL có thể truy cập thuộc tính và gọi phương thức tùy evaluation context; giới hạn quyền truy cập khi xây dựng tính năng cho phép người dùng nhập biểu thức.
8. **Kiểm thử tại integration point.** Kiểm thử parser đơn lẻ không chứng minh rằng module đã cung cấp đúng biến, đúng root object hoặc đúng thời điểm đánh giá.

## 5. Ghi nhớ nhanh

- **@Value**: inject giá trị; phân biệt **${...}** với **#{...}**.
- **@EventListener(condition = ...)**: lọc event trước khi gọi listener.
- **@Cacheable**: **key**, **condition**, **unless** phục vụ các quyết định cache ở những thời điểm khác nhau.
- **@PreAuthorize** / **@PostAuthorize**: phân quyền trước lời gọi hoặc sau khi có kết quả.
- Spring Data JPA: **#{#entityName}** giúp query dùng lại theo domain type.
- Spring Batch: **jobParameters** và execution context được late-bind trong bean có scope thích hợp.
- Spring Integration: thường bắt đầu từ **payload** và **headers**.
- Spring AMQP: phân biệt **#{...}** lúc khởi tạo với **!{...}** lúc xử lý message.
- Mỗi module có context và quy tắc riêng; luôn tra tài liệu theo phiên bản dependency đang chạy.

## 6. Tài liệu tham khảo chính thức

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — @Value Annotation](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Data JPA — Query Methods and Expressions](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Batch — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html)
- [Spring Integration — SpEL](https://docs.spring.io/spring-integration/reference/spel.html)
- [Spring AMQP — Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html)
- [Spring AMQP — Reply Management](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/reply.html)
- [Spring Retry — @Retryable API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html)
