# Chi phí, tốc độ phản hồi và độ tin cậy của từng cấp kiểm thử

Trong một ứng dụng Spring, các bài kiểm thử có thể chạy ở nhiều phạm vi: từ một phương thức Java độc lập, qua một nhóm bean do Spring quản lý, đến cơ sở dữ liệu thật và toàn bộ luồng người dùng. Mỗi phạm vi trả lời một loại câu hỏi khác nhau. Phạm vi càng rộng thường càng tốn thời gian thiết lập và chạy, nhưng có thể phát hiện những lỗi mà kiểm thử hẹp không nhìn thấy.

Khi chọn cấp kiểm thử, hãy cân nhắc đồng thời ba yếu tố:

- **Chi phí**: công sức viết và bảo trì, thời gian chạy, tài nguyên hạ tầng, cũng như thời gian tìm nguyên nhân khi kiểm thử thất bại.
- **Tốc độ phản hồi**: khoảng thời gian từ lúc thay đổi mã đến khi nhóm phát triển nhận được kết quả đủ rõ để hành động. Thời gian này gồm cả biên dịch, khởi tạo Spring context, chuẩn bị dữ liệu, xếp hàng trên CI và chạy test.
- **Độ tin cậy**: mức độ kết quả kiểm thử phản ánh hành vi thật của ứng dụng. Một test đáng tin cậy cần kiểm tra đúng ranh giới cần kiểm tra, dùng môi trường đủ đại diện và cho kết quả ổn định khi chạy lặp lại.

Không có cấp kiểm thử nào tối ưu trên cả ba yếu tố. Mục tiêu là đặt mỗi loại kiểm thử ở phạm vi nhỏ nhất nhưng vẫn đủ khả năng phát hiện rủi ro đang quan tâm.

## 1. Hiểu đúng ba yếu tố đánh đổi

### Chi phí không chỉ là thời gian chạy

Một bài test chạy trong 20 mili giây vẫn có thể đắt nếu cần nhiều mock khó bảo trì hoặc thường xuyên phải sửa khi cấu trúc nội bộ thay đổi. Ngược lại, một bài test tích hợp chạy vài giây có thể tiết kiệm thời gian về lâu dài nếu nó phát hiện sớm lỗi cấu hình kết nối cơ sở dữ liệu.

Có thể nhìn chi phí theo bốn phần:

1. **Chi phí xây dựng**: tạo dữ liệu, cấu hình test, chuẩn bị container, mock các phụ thuộc.
2. **Chi phí thực thi**: CPU, bộ nhớ, thời gian khởi động JVM, Spring context và dịch vụ phụ trợ.
3. **Chi phí bảo trì**: cập nhật fixture, xử lý thay đổi schema, sửa test bị phụ thuộc vào chi tiết triển khai.
4. **Chi phí chẩn đoán**: thời gian xác định lỗi nằm ở logic, cấu hình, dữ liệu, môi trường hay chính bài test.

Vì vậy, không nên chỉ so sánh số giây chạy test. Một suite nhanh nhưng thường xuyên báo lỗi giả có thể làm giảm năng suất hơn một suite chậm nhưng ổn định.

### Tốc độ phản hồi quyết định thời điểm phát hiện lỗi

Nếu một unit test báo lỗi ngay sau khi lưu mã, lập trình viên thường còn nhớ rõ thay đổi vừa thực hiện. Nếu lỗi chỉ xuất hiện trong pipeline chạy cuối ngày, việc tìm nguyên nhân sẽ khó hơn và có thể liên quan đến nhiều commit.

Tốc độ phản hồi phụ thuộc vào:

- Số lượng test được chạy ở mỗi vòng.
- Thời gian khởi tạo Spring context và các dịch vụ phụ trợ.
- Khả năng tái sử dụng context giữa các test.
- Việc chạy song song và giới hạn tài nguyên của máy hoặc CI.
- Chất lượng thông báo lỗi và khả năng tái hiện lỗi ở máy cá nhân.

Nên phân tầng thời điểm chạy: test nhanh chạy thường xuyên trong lúc phát triển; test tốn kém hơn chạy trước khi hợp nhất hoặc theo lịch phù hợp.

### Độ tin cậy gồm tính đại diện và tính ổn định

Hai khía cạnh này cần được phân biệt:

- **Tính đại diện**: test có dùng đúng thành phần và giao thức có khả năng gây lỗi trong môi trường thật không? Ví dụ, mock repository không chứng minh được câu SQL hoạt động trên PostgreSQL.
- **Tính ổn định**: cùng một phiên bản mã và dữ liệu, test có cho cùng kết quả không? Test phụ thuộc thời gian thực, thứ tự chạy, cổng mạng ngẫu nhiên hoặc dữ liệu dùng chung thường dễ chập chờn.

Một test có thể rất ổn định nhưng ít đại diện vì mock gần như mọi thứ. Một test dùng hạ tầng thật có thể đại diện tốt nhưng thiếu ổn định nếu dữ liệu hoặc môi trường không được cô lập. Bộ test tốt cần cân bằng cả hai.

## 2. Unit test: chi phí thấp, phản hồi nhanh

Unit test kiểm tra một đơn vị logic nhỏ, thường là một phương thức hoặc một lớp. Các phụ thuộc bên ngoài như repository, HTTP client, message publisher hoặc clock có thể được thay bằng mock hoặc fake để test tập trung vào hành vi của đơn vị đang xét.

Trong dự án Spring, nhiều lớp nghiệp vụ không cần khởi động Spring container để kiểm thử. JUnit Jupiter cùng Mockito thường đủ dùng.

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private PaymentGateway paymentGateway;

    @InjectMocks
    private OrderService orderService;

    @Test
    void rejectsOrderWhenPaymentIsDeclined() {
        var order = new Order("order-17", 120_000);

        when(paymentGateway.charge(order))
                .thenReturn(PaymentResult.declined());

        var result = orderService.place(order);

        assertEquals(OrderStatus.REJECTED, result.status());
        verify(orderRepository, never()).save(any());
    }
}
~~~

Ví dụ trên kiểm tra quyết định nghiệp vụ khi thanh toán bị từ chối. Test không cần tạo ApplicationContext, không cần cơ sở dữ liệu và không cần gọi dịch vụ thanh toán thật.

**Chi phí và tốc độ**

- Thường có chi phí khởi tạo thấp và thời gian chạy rất ngắn.
- Có thể chạy liên tục trong IDE sau mỗi thay đổi.
- Dễ chạy song song vì mỗi test có thể tự quản lý dữ liệu và mock.
- Chi phí bảo trì tăng nếu test mock quá nhiều chi tiết nội bộ hoặc sao chép thuật toán của mã sản phẩm.

**Độ tin cậy**

Unit test đáng tin cậy khi điều kiện đầu vào, đầu ra và tương tác cần thiết được xác định rõ. Nó rất phù hợp để kiểm tra quy tắc tính toán, phân nhánh, kiểm tra dữ liệu, chuyển trạng thái và xử lý lỗi.

Tuy nhiên, mock repository chỉ xác nhận cách lớp dịch vụ tương tác với hợp đồng đã giả lập. Nó không chứng minh truy vấn thực thi đúng, transaction hoạt động đúng hoặc Spring đã inject đúng bean. Nếu mock mọi phụ thuộc, test có thể vẫn xanh dù cấu hình tích hợp của ứng dụng đã hỏng.

Hãy tránh kiểm tra quá sâu thứ tự gọi nội bộ nếu thứ tự đó không phải một phần hợp đồng. Một unit test nên ưu tiên xác nhận kết quả hoặc hành vi quan sát được, để có thể tái cấu trúc mã mà không phải sửa hàng loạt test.

## 3. Kiểm thử thành phần và kiểm thử lát cắt Spring

Ở cấp này, test đưa một phần Spring vào hoạt động để xác nhận cách các thành phần được kết nối và xử lý request hoặc dữ liệu. Phạm vi rộng hơn unit test nhưng nhỏ hơn việc khởi động toàn bộ ứng dụng.

Có hai cách thường gặp:

- Dùng Spring TestContext để nạp một cấu hình có chọn lọc, chẳng hạn với **@SpringJUnitConfig** hoặc **@ContextConfiguration**.
- Trong Spring Boot, dùng các annotation kiểm thử lát cắt như **@WebMvcTest** và **@DataJpaTest** để nạp nhóm bean phù hợp với mục tiêu.

Cần phân biệt phần nào thuộc Spring Framework và phần nào do Spring Boot cung cấp: Spring TestContext, SpringExtension, MockMvc và các annotation cấu hình context thuộc hệ sinh thái Spring; các annotation lát cắt tiện dụng như **@WebMvcTest** và **@DataJpaTest** là hỗ trợ của Spring Boot.

### Ví dụ kiểm thử lớp web

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsOrderDetails() throws Exception {
        when(orderService.findById("order-17"))
                .thenReturn(new OrderView("order-17", "PAID"));

        mockMvc.perform(get("/orders/order-17"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("order-17"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

Test này kiểm tra việc ánh xạ route, binding tham số, xử lý request, chuyển kết quả thành HTTP response và một phần cấu hình MVC. OrderService được thay bằng mock nên test không xác minh logic nghiệp vụ hay cơ sở dữ liệu.

**Chi phí và tốc độ**

- Tốn thời gian hơn unit test vì Spring phải tạo một phần ApplicationContext.
- Có thể nhanh hơn đáng kể so với khởi động toàn bộ ứng dụng.
- Những test dùng cùng cấu hình context có thể hưởng lợi từ cơ chế cache của Spring TestContext.
- Nếu mỗi test thay đổi cấu hình, dùng nhiều mock bean khác nhau hoặc đánh dấu context cần khởi tạo lại, lợi ích cache giảm xuống.

**Độ tin cậy**

Kiểm thử lát cắt có độ tin cậy cao đối với phạm vi nó nạp. Ví dụ, **@WebMvcTest** giúp phát hiện lỗi cấu hình MVC, validation, converter, controller advice hoặc ánh xạ endpoint. Nhưng vì nhiều phụ thuộc được thay bằng mock, test không chứng minh toàn bộ luồng từ HTTP đến database hoạt động.

Với tầng persistence, **@DataJpaTest** phù hợp để kiểm tra mapping entity, repository query và hành vi persistence. Nếu dùng cơ sở dữ liệu trong bộ nhớ, hãy nhớ rằng khác biệt SQL, kiểu dữ liệu, collation, sequence hoặc hành vi transaction có thể khiến kết quả khác với hệ quản trị dùng ở production. Với truy vấn phụ thuộc đặc tính riêng của PostgreSQL, MySQL hoặc hệ quản trị khác, nên có test chạy trên đúng loại cơ sở dữ liệu đó.

### Khi nào nên chọn cấp này?

Dùng kiểm thử lát cắt khi câu hỏi tập trung vào một ranh giới của Spring:

- Controller có nhận request và trả response đúng không?
- Validation và exception handler có tạo đúng HTTP status không?
- Repository có tạo đúng truy vấn và ánh xạ entity không?
- Serialization, converter hoặc cấu hình bảo mật ở lớp web có hoạt động không?

Nếu chỉ kiểm tra một phép tính trong service, unit test thường rẻ và rõ hơn. Nếu cần chứng minh nhiều bean và hạ tầng phối hợp với nhau, hãy dùng integration test.

## 4. Integration test: xác minh các thành phần phối hợp

Integration test kiểm tra nhiều thành phần hoạt động cùng nhau. Phạm vi có thể gồm service, repository, transaction manager, cấu hình Spring, database, message broker hoặc HTTP client.

Với Spring Framework, **@SpringJUnitConfig** kết hợp SpringExtension và ContextConfiguration để chạy test trong Spring TestContext. Trong ứng dụng Spring Boot, **@SpringBootTest** thường được dùng khi cần nạp cấu hình ứng dụng rộng hơn.

~~~java
@SpringBootTest
@Transactional
class OrderPersistenceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void savesOrderAndMakesItAvailableThroughRepository() {
        var created = orderService.create(new CreateOrderCommand("customer-8"));

        var loaded = orderRepository.findById(created.id());

        assertTrue(loaded.isPresent());
        assertEquals("customer-8", loaded.get().customerId());
    }
}
~~~

Test trên kiểm tra một luồng qua Spring bean và repository. Với cấu hình transaction test phù hợp, thay đổi dữ liệu thường được rollback sau mỗi phương thức test. Tuy nhiên, không nên mặc định rằng mọi tác động đều được rollback: thao tác chạy ở thread khác, gửi message ra broker, gọi HTTP sang dịch vụ khác hoặc commit transaction độc lập có thể tồn tại sau khi test kết thúc.

### Dùng hạ tầng thật khi hạ tầng là một phần của rủi ro

Nếu ứng dụng phụ thuộc vào hành vi riêng của một database hoặc broker, test bằng hạ tầng thật thường có giá trị cao hơn mock. Testcontainers có thể khởi chạy dịch vụ trong container để test dùng phiên bản gần với môi trường triển khai.

~~~java
@Testcontainers
@SpringBootTest
class OrderDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void persistsOrderInPostgres() {
        var saved = orderRepository.save(new OrderEntity("order-29"));

        assertTrue(orderRepository.findById(saved.getId()).isPresent());
    }
}
~~~

Đây là ví dụ minh họa cho một test dùng PostgreSQL trong container. Cấu hình thực tế có thể cần thêm driver, migration, schema hoặc thuộc tính kết nối theo dự án. Có thể dùng **@ServiceConnection** trong những phiên bản Spring Boot hỗ trợ phù hợp để giảm cấu hình kết nối; **@DynamicPropertySource** là cách tổng quát hơn để đăng ký thuộc tính động.

**Chi phí và tốc độ**

- Cao hơn unit và slice test vì phải khởi tạo nhiều bean, schema và dịch vụ phụ trợ.
- Lần chạy đầu có thể chậm do tải image, tạo container hoặc chạy migration.
- Chạy lại có thể nhanh hơn nếu container và Spring context được tái sử dụng an toàn.
- Cần tài nguyên bộ nhớ, CPU, Docker hoặc môi trường tương đương; CI phải được cấu hình phù hợp.
- Test có thể tốn thời gian bảo trì nếu phụ thuộc vào dữ liệu dùng chung hoặc môi trường bên ngoài không ổn định.

**Độ tin cậy**

Integration test phát hiện các lỗi mà mock khó thấy: wiring sai, cấu hình thiếu, transaction không như dự kiến, query không tương thích, serialization giữa các thành phần hoặc cấu hình client sai.

Tuy vậy, độ tin cậy không tự động cao chỉ vì test khởi động toàn bộ ứng dụng. Nếu dữ liệu không được cô lập, test có thể phụ thuộc thứ tự chạy. Nếu test gọi dịch vụ dùng chung, kết quả có thể thay đổi theo trạng thái môi trường. Nếu test chỉ kiểm tra một kết quả quá chung chung, nó vẫn có thể bỏ sót lỗi nghiệp vụ.

Một số nguyên tắc giúp integration test ổn định:

- Mỗi test tự tạo dữ liệu cần thiết và dùng khóa định danh riêng.
- Xóa hoặc rollback dữ liệu đúng cách; chú ý tác động bất đồng bộ và side effect bên ngoài transaction.
- Tránh phụ thuộc vào thứ tự chạy hoặc trạng thái còn sót từ test trước.
- Không dùng lệnh sleep cố định để chờ hệ thống; hãy chờ điều kiện cụ thể với timeout hợp lý.
- Dùng clock có thể kiểm soát khi nghiệp vụ phụ thuộc thời gian.
- Giới hạn **@DirtiesContext** cho trường hợp thật sự làm thay đổi trạng thái context, vì annotation này có thể khiến Spring phải tạo context mới.
- Ghi log đủ thông tin để xác định container, request hoặc dữ liệu gây lỗi.

## 5. System test và end-to-end test: kiểm tra luồng hoàn chỉnh

System test kiểm tra ứng dụng như một hệ thống đã tích hợp. End-to-end (E2E) test đi qua một luồng gần với cách người dùng hoặc hệ thống bên ngoài sử dụng sản phẩm, chẳng hạn từ trình duyệt qua HTTP API đến database và dịch vụ liên quan.

Một E2E test cho quy trình đặt hàng có thể thực hiện các bước:

1. Đăng nhập bằng một tài khoản kiểm thử.
2. Tạo đơn hàng qua giao diện hoặc API công khai.
3. Thực hiện thanh toán giả lập ở môi trường kiểm thử.
4. Xác nhận đơn hàng chuyển sang trạng thái đã thanh toán.
5. Kiểm tra thông tin hiển thị hoặc thông báo được phát ra.

**Chi phí và tốc độ**

- Thường là cấp tốn kém nhất: cần môi trường triển khai, dữ liệu, tài khoản, trình duyệt hoặc client và nhiều dịch vụ phối hợp.
- Thời gian chạy có thể từ vài giây đến vài phút cho một luồng.
- Lỗi thường khó chẩn đoán vì có nhiều thành phần tham gia.
- Bảo trì tăng khi UI, selector, luồng nghiệp vụ hoặc môi trường thay đổi.

**Độ tin cậy**

E2E test có giá trị lớn khi xác minh một hành trình quan trọng thực sự hoạt động qua các ranh giới. Nhưng nó không nên là cách duy nhất để kiểm tra mọi quy tắc nghiệp vụ. Một test E2E thất bại có thể do dữ liệu, mạng, browser, dịch vụ phụ trợ hoặc logic ứng dụng; phạm vi rộng làm cho việc tìm nguyên nhân khó hơn.

Hãy giữ số lượng E2E test ở mức tập trung vào các hành trình có giá trị cao: đăng nhập, thanh toán, tạo đơn, hoàn tiền hoặc những luồng có nhiều tích hợp. Các nhánh logic chi tiết nên được kiểm tra ở unit hoặc integration test gần với nơi phát sinh lỗi.

## 6. So sánh các cấp kiểm thử

Bảng sau thể hiện xu hướng thường gặp, không phải thời gian cố định cho mọi dự án. Một unit test được thiết kế kém vẫn có thể chậm; một integration test dùng context cache và container tái sử dụng có thể nhanh hơn dự đoán.

| Cấp kiểm thử | Phạm vi điển hình | Chi phí tương đối | Phản hồi thường gặp | Độ tin cậy mạnh nhất ở đâu? |
|---|---|---:|---|---|
| Unit | Một lớp hoặc đơn vị logic, phụ thuộc được giả lập | Thấp | Rất nhanh | Quy tắc và nhánh logic độc lập |
| Component / slice | Một lát cắt Spring như MVC hoặc JPA | Thấp đến trung bình | Nhanh đến vừa | Wiring và hành vi của lát cắt được nạp |
| Integration | Nhiều bean và một hoặc nhiều hạ tầng thật | Trung bình đến cao | Vừa đến chậm | Tương tác giữa thành phần, transaction, truy vấn và cấu hình |
| System / E2E | Hành trình xuyên suốt hệ thống | Cao | Chậm | Luồng quan trọng qua các ranh giới thực tế |

Có thể hình dung xu hướng như sau:

~~~text
Phạm vi và mức độ đại diện tăng dần
Unit  ->  Slice / Component  ->  Integration  ->  System / E2E

Chi phí thiết lập, thời gian chạy và độ khó chẩn đoán thường tăng dần
Thời gian phản hồi thường tăng dần
Khả năng quan sát riêng từng đơn vị thường giảm dần
~~~

Độ tin cậy không tăng tuyến tính theo phạm vi. E2E có thể chứng minh một luồng quan trọng hoạt động, nhưng không thay thế hàng trăm unit test xác nhận các nhánh logic. Unit test có thể kiểm tra rất nhiều trường hợp biên, nhưng không chứng minh cấu hình production kết nối đúng database. Các cấp bổ sung bằng chứng cho nhau.

## 7. Phân bổ test theo rủi ro thay vì chạy mọi thứ ở mọi nơi

Một cách thực tế là chọn cấp test dựa trên loại lỗi cần ngăn chặn:

| Rủi ro cần kiểm tra | Cấp phù hợp | Ví dụ |
|---|---|---|
| Quy tắc tính phí, phân quyền hoặc chuyển trạng thái | Unit | Số tiền âm bị từ chối; trạng thái không hợp lệ không được chuyển |
| HTTP mapping, validation, exception handler | Web slice | Request thiếu trường bắt buộc trả về 400 |
| Entity mapping, query, constraint | Persistence slice hoặc integration | Unique constraint được database thực thi |
| Transaction, nhiều bean phối hợp | Integration | Tạo đơn và ghi lịch sử nằm trong cùng transaction |
| Tương thích với database hoặc broker cụ thể | Integration với hạ tầng thật | Migration và truy vấn chạy trên PostgreSQL |
| Hành trình kinh doanh quan trọng | E2E | Người dùng hoàn tất thanh toán và nhìn thấy trạng thái mới |

Một quy trình CI có thể chia thành các vòng:

- **Trong lúc lập trình**: chạy unit test và nhóm slice test liên quan đến phần vừa sửa.
- **Trước khi hợp nhất**: chạy toàn bộ unit, slice và integration test có thời gian phù hợp.
- **Sau khi triển khai lên môi trường kiểm thử hoặc theo lịch**: chạy smoke test và một số E2E test quan trọng.

Đây chỉ là cách phân bổ phổ biến. Nếu một nhóm integration test nhỏ chạy nhanh và ổn định, có thể đưa chúng vào vòng CI sớm. Nếu một test E2E rất quan trọng cho an toàn dữ liệu hoặc thanh toán, nó cần được chạy ở thời điểm đủ sớm để ngăn phát hành lỗi.

Không nên đặt mục tiêu một tỷ lệ cố định giữa unit, integration và E2E cho mọi hệ thống. Hãy xem kiến trúc, loại rủi ro, thời gian CI và lịch sử sự cố để quyết định. Một hệ thống nhiều truy vấn SQL phức tạp cần kiểm thử database thực chất hơn một thư viện tính toán thuần Java.

## 8. Giảm chi phí mà vẫn giữ tín hiệu đáng tin cậy

### Tận dụng Spring TestContext cache

Spring TestContext có thể tái sử dụng ApplicationContext giữa các test có cấu hình tương thích. Việc dùng các cấu hình context nhất quán giúp giảm số lần khởi động.

Ngược lại, quá nhiều biến thể cấu hình, thay đổi bean theo từng lớp test hoặc đóng context không cần thiết sẽ làm cache kém hiệu quả. Chỉ dùng **@DirtiesContext** khi test thực sự làm bẩn trạng thái context và không thể cô lập bằng cách khác.

### Chỉ khởi động phần cần thiết

Nếu đang kiểm tra controller, một web slice thường phù hợp hơn việc khởi động toàn bộ hệ thống. Nếu đang kiểm tra logic service thuần, không cần nạp Spring context. Nếu cần xác minh transaction và repository cùng hoạt động, hãy nạp đúng phạm vi tích hợp cần thiết.

### Dùng dữ liệu kiểm thử có thể tái tạo

Fixture nên thể hiện rõ điều kiện đầu vào và không phụ thuộc vào dữ liệu còn lại từ lần chạy trước. Với database dùng chung, hãy tạo dữ liệu có định danh riêng và dọn dẹp có kiểm soát. Với container dùng riêng cho test, vẫn cần quản lý dữ liệu và trạng thái giữa các phương thức test.

### Kiểm soát các yếu tố không xác định

Các nguồn gây test chập chờn thường gặp gồm thời gian hệ thống, múi giờ, thứ tự test, dữ liệu dùng chung, random, cổng mạng, timeout và dịch vụ bên ngoài. Hãy thay clock bằng nguồn thời gian có thể kiểm soát, đặt timeout có chủ đích, chờ điều kiện thay vì sleep và cô lập trạng thái giữa các test.

### Chạy song song có kiểm soát

Chạy song song có thể giảm thời gian tổng, nhưng cũng có thể làm lộ lỗi chia sẻ dữ liệu, tranh chấp cổng, giới hạn connection pool hoặc thiếu tài nguyên container. Trước khi tăng mức song song, bảo đảm mỗi test độc lập và hạ tầng có đủ năng lực.

## 9. Đo hiệu quả của bộ kiểm thử

Để biết chiến lược test có phù hợp hay không, hãy theo dõi một số chỉ số:

- **Thời gian phản hồi p50 và p95**: thời gian điển hình và thời gian ở các lượt chạy chậm.
- **Thời gian khởi tạo context**: xác định phần chậm đến từ Spring hay từ logic test.
- **Tỷ lệ test chập chờn**: số lần cùng một commit cho kết quả không nhất quán.
- **Thời gian chẩn đoán**: từ lúc test đỏ đến khi xác định được nguyên nhân.
- **Lỗi lọt qua từng cấp**: sự cố nào unit, slice, integration hoặc E2E đã có khả năng phát hiện nhưng chưa phát hiện.
- **Chi phí hạ tầng CI**: thời gian runner, bộ nhớ, container và dịch vụ phụ trợ.

Không nên tối ưu chỉ số thời gian bằng cách xóa test có giá trị hoặc mock toàn bộ phụ thuộc. Khi một test chậm, hãy tìm phần gây chậm: khởi động context, migration, tạo container, gọi mạng hay chuẩn bị fixture. Sau đó giảm phạm vi hoặc tái sử dụng tài nguyên nếu vẫn giữ được điều test cần chứng minh.

Khi test thất bại, báo cáo nên giúp trả lời nhanh: test nào thất bại, điều kiện đầu vào là gì, kỳ vọng và thực tế khác nhau ở đâu, log hoặc request liên quan nằm ở đâu. Thông báo rõ ràng làm giảm chi phí chẩn đoán và giúp test có giá trị hơn trong CI.

## 10. Checklist chọn cấp kiểm thử

Trước khi viết test, hãy tự trả lời:

1. Hành vi cần xác minh nằm trong một lớp, một lát cắt Spring hay nhiều thành phần?
2. Phụ thuộc nào có thể giả lập an toàn, và phụ thuộc nào cần chạy thật để phát hiện lỗi?
3. Test cần chứng minh logic nghiệp vụ, wiring Spring, truy vấn database hay một hành trình người dùng?
4. Môi trường có thể tái tạo và cô lập dữ liệu giữa các lần chạy không?
5. Test sẽ chạy ở vòng nào: IDE, pull request, CI sau hợp nhất hay môi trường kiểm thử?
6. Khi test thất bại, thông tin có đủ để tìm đúng nguyên nhân không?

Một chiến lược cân bằng thường có nhiều unit test để phản hồi nhanh về logic, một lượng phù hợp component hoặc slice test để kiểm tra tích hợp với Spring, các integration test tập trung vào ranh giới hạ tầng có rủi ro, và một nhóm nhỏ system/E2E test bảo vệ những hành trình quan trọng.

Khi một lỗi đã xảy ra, hãy bổ sung test ở cấp thấp nhất có thể tái hiện lỗi một cách đáng tin cậy. Nếu lỗi chỉ xuất hiện do database thực thi constraint, integration test với database phù hợp là bằng chứng cần thiết. Nếu lỗi là một nhánh tính toán, unit test thường cho phản hồi nhanh và dễ chẩn đoán hơn. Nhờ vậy, bộ kiểm thử vừa kiểm soát được chi phí và tốc độ, vừa tạo ra tín hiệu đủ tin cậy để nhóm phát triển đưa ra quyết định.

