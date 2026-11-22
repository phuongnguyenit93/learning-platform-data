# Chuẩn bị dữ liệu độc lập và dọn trạng thái giữa các ca kiểm thử

## Mục tiêu

Mỗi ca kiểm thử cần tự chuẩn bị dữ liệu mà nó sở hữu, kiểm tra đúng phần dữ liệu đó và kết thúc mà không để lại ảnh hưởng cho ca chạy sau. Một test phải chạy được riêng lẻ, chạy cùng toàn bộ suite và không phụ thuộc thứ tự thực thi.

Điều này đặc biệt quan trọng với Spring Data REST: framework xuất các Spring Data repository thành REST resource qua Spring MVC. Dữ liệu còn sót lại có thể làm thay đổi kết quả collection, search, phân trang, kiểm tra số lượng hoặc gây trùng khóa khi test khác chạy.

## 1. Chọn đúng loại kiểm thử

- **Unit test:** kiểm tra logic thuần; thay repository hoặc dịch vụ bên ngoài bằng mock. Không cần tạo dữ liệu trong database.
- **Repository test:** với JPA, dùng `@DataJpaTest` để tập trung vào entity mapping, query và repository. Spring Boot cấu hình repository và database nhúng nếu có trên classpath; test mặc định chạy trong transaction và rollback sau mỗi method.
- **Spring Data REST integration test:** cần kiểm tra repository được export, URL, HAL/JSON, query method, status code hoặc ghi dữ liệu qua HTTP thì nạp application context thật bằng `@SpringBootTest` và dùng `@AutoConfigureMockMvc`. Cấu hình mặc định là mock web environment, không khởi động server thật.
- **Live-server test:** chỉ dùng `webEnvironment = RANDOM_PORT` khi cần kiểm tra HTTP qua server thật, cổng, filter hoặc hành vi phụ thuộc mạng. Phải có kế hoạch cleanup riêng vì request client và server chạy ở các thread và transaction khác nhau.

`@WebMvcTest` phù hợp khi chỉ kiểm tra MVC controller đã chọn. Nó không tự nạp toàn bộ repository và cấu hình export của Spring Data REST; hãy dùng full application context khi mục tiêu là kiểm tra resource do repository tạo ra.

## 2. Tạo fixture độc lập cho từng test

Một fixture tốt có các đặc điểm sau:

1. Tạo entity mới mỗi lần gọi factory/builder; không dùng lại một entity mutable hoặc collection static giữa nhiều test.
2. Chỉ tạo các bản ghi mà test cần. Không dựa vào dữ liệu được seed bởi test khác hoặc giả định bảng đang rỗng.
3. Dùng khóa nghiệp vụ duy nhất cho từng lần chạy, nhất là email, username, mã đơn hàng hoặc slug. Có thể kết hợp tiền tố dễ nhận biết với UUID.
4. Giữ dữ liệu đủ nhỏ và mô tả đúng điều kiện đang kiểm tra. Khi test một search endpoint, truy vấn theo khóa duy nhất của fixture thay vì khẳng định tổng số bản ghi của cả bảng.
5. Nếu có quan hệ, tạo đầy đủ các bản ghi phụ thuộc và giữ tham chiếu đến ID do repository trả về để cleanup chính xác.

Ví dụ factory tạo fixture mới:

```java
static Customer newCustomerFixture() {
    Customer customer = new Customer();
    customer.setName("Ada");
    customer.setEmail("sdr-" + UUID.randomUUID() + "@example.test");
    return customer;
}
```

Không lưu một `Customer` đã tạo vào biến `static final` rồi dùng chung cho nhiều test. Factory có thể là static, nhưng mỗi lần gọi phải trả về object mới và dữ liệu định danh mới.

Với dữ liệu đơn giản, tạo fixture trong `@BeforeEach` hoặc ngay trong test method. Dùng `@BeforeEach` khi nhiều test trong cùng lớp cần cùng cấu trúc dữ liệu ban đầu; dùng helper riêng khi mỗi test cần một trạng thái khác nhau. Tránh `@BeforeAll` để tạo dữ liệu mutable dùng chung cho toàn lớp.

## 3. Ưu tiên rollback cho test chạy trong cùng transaction

Spring TestContext hỗ trợ test-managed transaction khi application context có `PlatformTransactionManager` và test được đánh dấu `@Transactional`. Transaction test được rollback mặc định sau khi test kết thúc. Các thao tác của Spring-managed transaction thường tham gia transaction này khi dùng propagation phù hợp, chẳng hạn `REQUIRED`.

Với JPA repository test, `@DataJpaTest` đã bật transaction và rollback mặc định. Không cần thêm `repository.deleteAll()` ở `@AfterEach` chỉ để dọn các bản ghi nằm trong transaction đó: lệnh delete cũng nằm trong transaction và sẽ rollback cùng test.

Với endpoint Spring Data REST chạy qua MockMvc, có thể dùng cấu hình sau cho backend hỗ trợ transaction (ví dụ JPA):

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class CustomerRestIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    CustomerRepository customers;

    @Test
    void searchReturnsThisTestsCustomer() throws Exception {
        Customer customer = newCustomerFixture();
        customers.save(customer);

        mvc.perform(get("/customers/search/findByEmail")
                .param("email", customer.getEmail())
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.email").value(customer.getEmail()));
    }
}
```

Ví dụ giả định repository được Spring Data REST export, có query method `findByEmail(String email)`, entity có trường `email`, và collection resource là `/customers`. Tên resource mặc định được suy ra từ tên entity; `@RepositoryRestResource`, base path hoặc cấu hình khác có thể thay đổi URL. Search resource chỉ xuất hiện khi repository công khai query method tương ứng.

Trong test trên, fixture được lưu qua repository và endpoint được gọi trong mock web environment. Với xử lý MVC đồng bộ và transaction propagation thông thường, các thao tác database cùng tham gia transaction test; dữ liệu được rollback sau method. Không áp dụng kết luận này cho tác vụ async, thread khác, transaction `REQUIRES_NEW`, hoặc backend không hỗ trợ transaction theo cách đó.

## 4. Dùng `@Sql` khi cần fixture hoặc cleanup rõ ràng

Với relational database, `@Sql` cho phép chạy script trước hoặc sau một test method. Mặc định script chạy trước test. Đặt `executionPhase = AFTER_TEST_METHOD` để chạy script cleanup sau test.

Ví dụ sau dành cho tình huống dữ liệu phải được commit để server thật hoặc tiến trình khác nhìn thấy:

```java
import static org.springframework.test.context.jdbc.Sql.ExecutionPhase.AFTER_TEST_METHOD;
import static org.springframework.test.context.jdbc.Sql.TransactionMode.ISOLATED;

@Test
@Sql(
    scripts = "/sql/customer-fixture.sql",
    config = @SqlConfig(transactionMode = ISOLATED)
)
@Sql(
    scripts = "/sql/customer-cleanup.sql",
    config = @SqlConfig(transactionMode = ISOLATED),
    executionPhase = AFTER_TEST_METHOD
)
void liveEndpointReadsCommittedFixture() {
    // Gọi endpoint và kiểm tra dữ liệu đã được commit.
}
```

- Đặt script trong test classpath, ví dụ `src/test/resources/sql/`.
- Script fixture nên tạo dữ liệu có marker riêng cho test; script cleanup chỉ xóa các hàng mang marker đó.
- Dùng `ISOLATED` khi cần transaction riêng được commit độc lập với transaction test. Script cleanup cũng cần transaction độc lập nếu dữ liệu đã được commit ở nơi khác.
- Xóa bản ghi con trước bản ghi cha khi có khóa ngoại, trừ khi schema đã cấu hình cascade phù hợp.
- `@Sql` khai báo ở method mặc định override khai báo ở class. Kiểm tra quy tắc này nếu script dùng chung ở class và có fixture riêng ở method.

Nếu test và script đều tham gia cùng test-managed transaction, rollback mặc định thường đã đủ và không cần script xóa riêng. Chỉ thêm cleanup độc lập khi dữ liệu thực sự thoát khỏi transaction rollback của test.

## 5. Dọn trạng thái ngoài database

Rollback database không tự reset mọi trạng thái. Hãy xác định test có thể thay đổi những tài nguyên nào và cleanup đúng tài nguyên đó:

- **Cache hoặc singleton bean:** reset các entry/key do test tạo; không dùng cache dùng chung với dữ liệu thật.
- **Message broker hoặc event:** dùng queue/topic riêng cho test, kiểm tra và xóa message do test phát ra; chờ consumer hoàn tất trước khi khẳng định trạng thái.
- **File hoặc thư mục tạm:** dùng thư mục riêng cho test và xóa trong `@AfterEach` hoặc `@TempDir`.
- **Mock và spy:** tạo/reset theo vòng đời test; không giữ invocation hoặc mutable mock state dùng chung ngoài ý muốn.
- **Tài nguyên mở:** đóng stream, client, socket và executor do test tạo.

JUnit Jupiter mặc định tạo một test instance mới cho mỗi test method (`PER_METHOD`). Điều này cô lập field của object test, nhưng không tự xóa database, static field, singleton bean hay dịch vụ bên ngoài. Nếu bật `@TestInstance(PER_CLASS)`, cùng một test instance được dùng cho cả lớp; phải reset mutable field trong `@BeforeEach` hoặc `@AfterEach`.

`@DirtiesContext` đánh dấu Spring `ApplicationContext` bị thay đổi hoặc hỏng để framework đóng context và tạo lại context khi cần. Dùng annotation này khi test làm thay đổi trạng thái context, chẳng hạn singleton bean không thể reset an toàn. Đây không phải cơ chế cleanup mặc định cho từng hàng dữ liệu trong database bên ngoài; vẫn phải dọn dữ liệu ở database, broker hoặc filesystem theo cách tương ứng. Việc reload context cũng tốn thời gian và có thể ảnh hưởng test chạy song song.

## 6. Tránh xung đột khi chạy song song

Nếu nhiều test cùng truy cập một database, broker hoặc filesystem, cleanup toàn cục có thể xóa dữ liệu của test đang chạy. Để giảm xung đột:

- Dùng UUID hoặc namespace riêng cho mỗi test invocation.
- Xóa theo ID hoặc marker thuộc test đó; tránh `deleteAll()` trên repository dùng chung.
- Dùng database/schema/container riêng cho nhóm test cần trạng thái độc lập mạnh.
- Không phụ thuộc vào thứ tự test hoặc dữ liệu do test khác tạo.
- Nếu không thể cô lập một tài nguyên dùng chung, không chạy song song nhóm test đó.
- Không dùng `@DirtiesContext` như cách chữa lỗi race condition; xử lý shared state hoặc tách test khỏi chạy song song.

Spring TestContext cảnh báo rằng test thay đổi trạng thái hệ thống dùng chung như database, message broker hoặc filesystem có thể thất bại ngẫu nhiên khi chạy song song. Hãy thiết kế fixture và cleanup trước khi bật parallel execution.

## 7. Quy trình thực hiện cho một test Spring Data REST

1. Xác định repository được export, collection path, query method và base path thực tế.
2. Chọn loại test: repository slice, MockMvc với full context, hoặc live server.
3. Tạo fixture riêng với khóa duy nhất và chỉ các quan hệ cần thiết.
4. Chạy hành vi qua repository hoặc REST endpoint; kiểm tra status, representation, dữ liệu và quan hệ cần thiết.
5. Chọn đúng cơ chế kết thúc: rollback transaction; hoặc cleanup bằng `@Sql`/repository theo marker; đồng thời reset trạng thái ngoài database.
6. Xác nhận dữ liệu của test không còn tồn tại sau khi cleanup nếu test dùng commit hoặc live server.
7. Chạy test riêng lẻ rồi chạy toàn bộ test suite. Nếu có bật parallel execution, chạy lại nhóm liên quan để phát hiện xung đột.

Lệnh chạy một lớp test (đổi tên lớp và dùng wrapper có trong dự án):

```bash
./mvnw -Dtest=CustomerRestIntegrationTest test
./gradlew test --tests '*CustomerRestIntegrationTest'
```

Trên Windows có thể dùng `mvnw.cmd -Dtest=CustomerRestIntegrationTest test` hoặc `gradlew.bat test --tests '*CustomerRestIntegrationTest'`.

## 8. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test chạy riêng thành công nhưng chạy cả suite thì fail | Dữ liệu cũ, static state, singleton bean hoặc phụ thuộc thứ tự | Tạo fixture mới cho từng method; tìm dữ liệu theo marker; reset shared state |
| Lỗi unique constraint | Nhiều test dùng chung email, username hoặc mã nghiệp vụ | Sinh khóa duy nhất; cleanup đúng bản ghi đã tạo |
| REST collection trả về nhiều hàng hơn dự kiến | Test kiểm tra toàn bộ collection trong database dùng chung | Query theo ID/marker duy nhất; chỉ assert phần dữ liệu test sở hữu |
| POST qua RANDOM_PORT tạo dữ liệu còn sót dù test có `@Transactional` | Request được xử lý ở server thread và transaction riêng | Cleanup sau test bằng `@Sql` với `ISOLATED`/ `AFTER_TEST_METHOD`, hoặc dùng fixture ID và xóa rõ ràng |
| Cleanup lỗi khóa ngoại | Xóa parent trước child | Xóa theo thứ tự phụ thuộc hoặc dùng cascade đã được thiết kế |
| Script cleanup không chạy | `@Sql` mặc định chạy trước test hoặc method annotation override class annotation | Kiểm tra `executionPhase`, đường dẫn classpath và quy tắc merge/override |
| Dữ liệu không rollback | Không có transaction manager phù hợp, test không có `@Transactional`, dùng `REQUIRES_NEW`, async/thread khác, hoặc test được cấu hình commit | Kiểm tra transaction manager/propagation; dùng cleanup độc lập cho phần đã commit |
| Test song song lúc pass lúc fail | Các test cùng sửa database, queue, cache hoặc file | Tách namespace/tài nguyên hoặc tắt parallel cho nhóm không thể cô lập |

Khi cần chẩn đoán, ghi log ID/marker fixture và truy vấn đúng các bản ghi đó. Tránh chạy lệnh xóa toàn bảng trên database được chia sẻ.

## Tài liệu chính thức

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): cách repository được export, collection/item/search resource và HTTP method.
- [Spring Data REST — Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): cấu hình Spring Data REST trong Spring Boot.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, mock web environment, `@AutoConfigureMockMvc`, live server và transaction boundary.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/): các test slice, gồm `@DataJpaTest`.
- [Spring Framework — Transaction management in TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction, rollback và lifecycle hooks.
- [Spring Framework — Executing SQL scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): `@Sql`, execution phase và transaction mode.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử Spring MVC bằng request/response giả lập.
- [Spring Framework — Context caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): tái sử dụng ApplicationContext và khi cần reload context.
- [Spring Framework — Parallel test execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): giới hạn và rủi ro khi chạy test song song.
- [JUnit Jupiter User Guide — Test instance lifecycle](https://docs.junit.org/current/user-guide/#writing-tests-test-instance-lifecycle): vòng đời `PER_METHOD` và `PER_CLASS`.
