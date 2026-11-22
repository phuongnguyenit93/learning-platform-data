# Chọn thành phần cần thay thế ở ranh giới bài kiểm thử

Khi viết kiểm thử, một quyết định quan trọng là xác định thành phần nào cần chạy thật và thành phần nào nên được thay bằng mock, stub, spy hoặc fake. Quyết định này ảnh hưởng trực tiếp đến điều mà bài kiểm thử chứng minh được. Nếu thay thế quá nhiều, test có thể chỉ kiểm tra cách các mock được gọi mà không chứng minh hành vi của ứng dụng. Nếu giữ tất cả phụ thuộc bên ngoài, test có thể chậm, khó lặp lại và thất bại vì mạng, thời gian hoặc hệ thống dùng chung.

Không có một quy tắc như “luôn mock repository” hay “không bao giờ mock service”. Cách chọn đúng phụ thuộc vào ranh giới hành vi đang kiểm tra, mức độ tin cậy cần có và loại bằng chứng cần thu được. Một thành phần có thể được giữ thật trong integration test nhưng được thay bằng fake trong unit test của cùng nghiệp vụ.

Bài học này tập trung vào cách đưa ra quyết định đó trong bối cảnh Spring Framework Testing: xác định system under test, phân loại phụ thuộc, chọn loại test double, thiết kế kiểm thử ở từng tầng Spring và tránh những thay thế làm suy yếu bằng chứng.

## 1. Bắt đầu bằng câu hỏi: bài kiểm thử cần chứng minh điều gì?

Trước khi tạo mock hoặc cấu hình Spring context, hãy viết một câu mô tả hành vi cần kiểm chứng. Ví dụ:

> Khi khách hàng đặt một sản phẩm còn hàng và thanh toán được chấp nhận, hệ thống lưu đơn hàng và phát sự kiện OrderPlaced.

Từ yêu cầu này, có thể xác định:

- Đối tượng đang được kiểm thử là dịch vụ ứng dụng xử lý việc đặt hàng.
- Kết quả quan trọng gồm đơn hàng được lưu với dữ liệu đúng và sự kiện được phát.
- Việc thanh toán phụ thuộc vào một hệ thống bên ngoài.
- Dữ liệu sản phẩm và đơn hàng có thể đến từ persistence adapter.
- Thời gian tạo đơn có thể phụ thuộc đồng hồ hệ thống.

Nếu mục tiêu chỉ là kiểm tra quyết định nghiệp vụ của dịch vụ ứng dụng, ta không cần khởi động cơ sở dữ liệu thật hoặc gọi cổng thanh toán thật. Nhưng nếu mục tiêu là xác minh mapping entity, transaction hoặc câu truy vấn, thay repository bằng mock sẽ loại bỏ chính phần cần kiểm tra.

Hãy xác định rõ ba yếu tố:

1. **System under test (SUT):** thành phần mà hành vi của nó là trọng tâm.
2. **Collaborators:** những thành phần SUT cần dùng để hoàn thành hành vi.
3. **Boundary:** điểm mà hành vi đang kiểm tra đi qua để tương tác với hệ thống khác, chẳng hạn database, HTTP service, message broker, file system hoặc clock.

Ranh giới bài kiểm thử không nhất thiết trùng với ranh giới của một class. Một unit test có thể kiểm tra một service cùng một vài đối tượng domain thật. Một integration test có thể kiểm tra controller, service, repository và database cùng hoạt động. Ranh giới phải được chọn theo điều ta muốn chứng minh.

### 1.1. Phân biệt đối tượng được kiểm thử và đối tượng cộng tác

Giả sử một service có các phụ thuộc sau:

~~~java
class OrderApplicationService {
    private final ProductCatalog productCatalog;
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;
    private final OrderEventPublisher eventPublisher;
    private final Clock clock;

    // Constructor và phương thức nghiệp vụ
}
~~~

Khi kiểm tra quy tắc đặt hàng, OrderApplicationService là SUT. Các interface còn lại là collaborator. Tuy nhiên, không phải tất cả collaborator đều phải được thay thế theo cùng một cách:

| Collaborator | Đặc điểm | Lựa chọn có thể phù hợp |
| --- | --- | --- |
| ProductCatalog | Cung cấp dữ liệu sản phẩm | Fake hoặc stub trong unit test; adapter thật trong integration test |
| PaymentGateway | Gọi hệ thống thanh toán bên ngoài | Stub phản hồi và mock tương tác có ý nghĩa; server giả lập ở kiểm thử adapter |
| OrderRepository | Lưu và đọc đơn hàng | Fake cho kiểm thử logic ứng dụng; database thật cho kiểm thử persistence |
| OrderEventPublisher | Phát sự kiện ra ngoài | Recording fake hoặc mock; broker thật trong kiểm thử tích hợp cần thiết |
| Clock | Cung cấp thời gian hiện tại | Fixed Clock để kết quả xác định |

Bảng này không phải cấu hình cố định. Nếu bài kiểm thử nhằm chứng minh repository tạo đúng câu SQL hoặc mapping quan hệ, OrderRepository phải được kiểm tra với persistence implementation thật. Nếu bài kiểm thử nhằm xác nhận cách service phản ứng khi thanh toán bị từ chối, một phản hồi stub từ PaymentGateway là đủ.

### 1.2. Viết tiêu chí kiểm thử trước khi chọn công cụ

Một tiêu chí cụ thể giúp tránh chọn mock chỉ vì công cụ đang có sẵn. Ví dụ:

- Khi thanh toán được chấp nhận, service tạo đơn với đúng khách hàng, sản phẩm và tổng tiền.
- Khi thanh toán bị từ chối, service không lưu đơn ở trạng thái đã thanh toán.
- Sự kiện OrderPlaced chỉ được phát sau khi đơn đã đạt trạng thái mà nghiệp vụ quy định.
- Thời gian tạo đơn lấy từ Clock được cung cấp.

Từ các tiêu chí này, ta biết cần điều khiển kết quả thanh toán, quan sát dữ liệu được lưu, quan sát sự kiện và cố định thời gian. Ta chưa cần quyết định mọi thứ đều là Mockito mock. Một repository in-memory và một publisher ghi nhận sự kiện có thể cung cấp bằng chứng tốt hơn một chuỗi mock phức tạp.

## 2. Test double là gì?

Test double là một đối tượng thay thế collaborator thật trong một bài kiểm thử. Nó giữ vai trò tương tự diễn viên đóng thế: cung cấp một phần hành vi cần thiết để kiểm thử tập trung vào mục tiêu đã chọn.

Các loại thường gặp gồm:

- **Dummy:** đối tượng được truyền vào để đáp ứng chữ ký phương thức nhưng không được sử dụng trong tình huống đó.
- **Stub:** trả về dữ liệu hoặc kết quả đã được chuẩn bị trước.
- **Mock:** ghi nhận tương tác và cho phép kiểm tra những lời gọi được kỳ vọng.
- **Spy:** quan sát hoặc bọc một đối tượng thật, đôi khi thay thế một phần hành vi của nó.
- **Fake:** triển khai một phiên bản đơn giản nhưng có thể hoạt động của một collaborator, ví dụ repository lưu dữ liệu trong bộ nhớ.

Trong thực tế, một thư viện như Mockito có thể tạo stub, mock và spy. Tên annotation hoặc API không tự quyết định mục đích kiểm thử. Điều quan trọng là test đang dùng đối tượng đó để cung cấp kết quả, xác minh tương tác hay quan sát hành vi.

### 2.1. Stub: điều khiển câu trả lời của collaborator

Stub phù hợp khi SUT cần nhận một kết quả cụ thể để đi qua một nhánh nghiệp vụ. Ví dụ, PaymentGateway có thể trả về thanh toán được chấp nhận hoặc bị từ chối.

~~~java
when(paymentGateway.charge(any(PaymentRequest.class)))
    .thenReturn(PaymentResult.approved("PAY-100"));
~~~

Trong tình huống này, điều quan trọng là SUT phản ứng đúng với kết quả được cung cấp. Nếu test không cần xác nhận chính xác collaborator được gọi bao nhiêu lần, việc thêm verify có thể không mang lại giá trị.

Có thể tạo stub cho:

- Phản hồi thành công hoặc lỗi của dịch vụ bên ngoài.
- Kết quả truy vấn cần thiết cho một nhánh nghiệp vụ.
- Thời gian cố định hoặc dữ liệu được chuẩn bị trước.
- Tình huống hiếm khó tái hiện bằng hệ thống thật.

Stub không nên chứa lại chính thuật toán của SUT. Nếu stub tính toán cùng công thức với production code, test có nguy cơ xác nhận một kết quả sai theo cùng một cách.

### 2.2. Mock: kiểm tra tương tác có ý nghĩa

Mock phù hợp khi một lời gọi ra ngoài là một phần của hành vi cần bảo vệ. Ví dụ, khi yêu cầu quy định rằng hệ thống phải gửi một lệnh thanh toán với đúng số tiền và khóa idempotency, ta có thể xác minh command gửi tới PaymentGateway.

~~~java
ArgumentCaptor<PaymentRequest> requestCaptor =
    ArgumentCaptor.forClass(PaymentRequest.class);

verify(paymentGateway).charge(requestCaptor.capture());

assertThat(requestCaptor.getValue().amount())
    .isEqualByComparingTo(expectedTotal);
~~~

Mock thường cũng được cấu hình để trả dữ liệu, vì vậy một mock có thể đồng thời đóng vai trò stub. Tuy nhiên, nên tách hai ý định khi đọc test:

- Setup: cung cấp phản hồi để SUT xử lý.
- Verification: xác nhận một tương tác quan trọng đã xảy ra hoặc không xảy ra.

Không phải mọi lời gọi đều cần verify. Nếu test xác nhận đơn hàng cuối cùng có đúng dữ liệu và không có hợp đồng nào yêu cầu một thứ tự gọi cụ thể, việc verify mọi getter, mapper hoặc repository method sẽ làm test phụ thuộc vào cách triển khai.

### 2.3. Spy: quan sát một đối tượng thật

Spy bọc một đối tượng thật để có thể quan sát lời gọi hoặc thay thế một phương thức cụ thể. Nó hữu ích trong một số tình huống chuyển tiếp hoặc khi cần quan sát một collaborator thật mà không thể dễ dàng đưa điểm quan sát khác vào.

~~~java
List<String> names = new ArrayList<>();
List<String> namesSpy = spy(names);

namesSpy.add("Spring");

verify(namesSpy).add("Spring");
assertThat(namesSpy).containsExactly("Spring");
~~~

Spy có thể khiến test khó hiểu nếu nó vừa chạy logic thật vừa thay thế một vài phương thức. Với Mockito, cách viết when(spy.method()) có thể gọi phương thức thật ngay trong lúc setup. Khi cần tránh việc gọi đó, API doReturn(...).when(spy)... có thể phù hợp hơn.

Spy cũng tạo rủi ro khi dùng với class có trạng thái phức tạp, phương thức final, lời gọi nội bộ hoặc side effect. Nếu cần thay một collaborator, hãy cân nhắc tạo interface/port rõ ràng hoặc dùng fake. Nếu cần kiểm tra một class, ưu tiên gọi API công khai của nó và quan sát kết quả.

### 2.4. Fake: một phiên bản đơn giản nhưng có hành vi

Fake hữu ích khi cần một collaborator hoạt động được nhưng không muốn phụ thuộc vào hạ tầng thật. Ví dụ, InMemoryOrderRepository có thể lưu đơn trong Map:

~~~java
class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    int count() {
        return orders.size();
    }
}
~~~

Fake có thể giúp kiểm thử service nhanh và dễ đọc. Nhưng nó chỉ chứng minh hành vi của service khi làm việc với hợp đồng OrderRepository mà fake triển khai. Nó không chứng minh JPA mapping, SQL, transaction, constraint hoặc locking của database thật.

Một fake tốt cần đơn giản, rõ giới hạn và không tự biến thành một implementation thứ hai của production. Nếu fake ngày càng phải mô phỏng transaction, concurrency, query language và mọi quy tắc của database, đã đến lúc dùng database kiểm thử thật.

### 2.5. Dummy: chỉ để lấp chỗ trống

Dummy là đối tượng không được dùng trong tình huống kiểm thử. Có thể dùng một hằng số null hoặc một implementation rỗng nếu chữ ký cho phép, nhưng nên tránh để dummy tạo lỗi khó hiểu nếu SUT vô tình gọi vào nó.

Nếu một collaborator không liên quan đến hành vi, constructor injection giúp tạo một test fixture đơn giản. Khi dependency bắt buộc phải có, một dummy tường minh với tên như unusedAuditPort có thể làm rõ ý định hơn một mock được tạo nhưng không bao giờ dùng.

## 3. Cách chọn thành phần cần thay thế

Hãy đi lần lượt qua các câu hỏi sau. Mỗi câu hỏi thu hẹp phạm vi và giúp chọn loại test double phù hợp.

### 3.1. Hành vi của collaborator có nằm trong điều cần chứng minh không?

Nếu có, giữ collaborator thật ở mức phù hợp. Ví dụ:

- Kiểm tra truy vấn repository: dùng repository thật và database kiểm thử.
- Kiểm tra binding JSON, validation hoặc exception mapping: giữ MVC infrastructure thật.
- Kiểm tra transaction rollback: cần chạy qua transaction manager và persistence thật.
- Kiểm tra thuật toán domain: dùng đối tượng domain thật.

Nếu không, có thể thay collaborator để test tập trung vào hành vi của SUT. Ví dụ, khi kiểm tra service phản ứng với payment declined, không cần gọi cổng thanh toán thật.

### 3.2. Collaborator có nằm ngoài ranh giới kiểm soát của ứng dụng không?

Những thành phần như HTTP service của bên thứ ba, email provider, broker dùng chung, clock hệ thống hoặc filesystem thường cần được kiểm soát trong test. Chúng có thể chậm, không ổn định, tốn phí hoặc khó tạo lỗi theo ý muốn.

Với các thành phần này, hãy thay thế ở adapter hoặc port mà ứng dụng sở hữu. Giữ logic chuyển đổi request/response của adapter thật trong một bài kiểm thử riêng, dùng HTTP stub server hoặc container để điều khiển hệ thống đối tác.

### 3.3. Cần điều khiển dữ liệu hay cần xác minh hành động?

Nếu chỉ cần SUT nhận một câu trả lời cụ thể, dùng stub.

Nếu cần xác nhận một command quan trọng đã được gửi, dùng mock hoặc recording fake.

Nếu cần thao tác với dữ liệu qua một API đơn giản, fake có thể phù hợp.

Nếu cần chứng minh tương tác giữa nhiều adapter và hạ tầng, giữ các thành phần liên quan thật trong integration test.

### 3.4. Thay thế có làm mất bằng chứng quan trọng không?

Đây là câu hỏi cần ưu tiên nhất. Mock repository trong một test nhằm xác nhận SQL query sẽ loại bỏ bằng chứng. Mock validator trong một test nhằm xác nhận Bean Validation sẽ làm cho test không còn kiểm tra validator thật. Mock Security filter chain trong một test nhằm xác nhận quyền truy cập sẽ bỏ qua chính lớp bảo vệ cần kiểm tra.

Ngược lại, nếu một service chỉ cần biết cổng thanh toán trả về approved hay declined, thay gateway thật bằng stub giúp kiểm soát nhánh nghiệp vụ mà không làm mất bằng chứng của service.

### 3.5. Chi phí và độ tin cậy của phương án thật là bao nhiêu?

Một phụ thuộc thật có thể phù hợp nếu nó nhẹ, chạy cục bộ và là một phần của mục tiêu. Một database Testcontainers có thể đáng dùng trong integration test. Một hệ thống thanh toán production thì không phù hợp để gọi trong test tự động thông thường.

Hãy cân nhắc:

- Thời gian khởi động và thời gian chạy.
- Khả năng chạy offline và chạy song song.
- Mức độ lặp lại của dữ liệu và kết quả.
- Khả năng mô phỏng lỗi và timeout.
- Độ giống với môi trường production.
- Chi phí duy trì fake hoặc mock.

Không tối ưu tốc độ bằng cách thay thế một thành phần mà bài kiểm thử cần xác minh. Cũng không cần dựng toàn bộ hạ tầng production cho mọi unit test.

## 4. Ma trận quyết định theo loại collaborator

Ma trận sau là điểm khởi đầu để lựa chọn, không phải quy tắc tuyệt đối:

| Collaborator | Unit test SUT | Kiểm thử adapter hoặc tích hợp |
| --- | --- | --- |
| Value object, domain entity | Giữ thật | Giữ thật |
| Domain service thuần | Giữ thật nếu không có side effect | Giữ thật |
| Repository | Fake hoặc stub nếu chỉ cần dữ liệu; tránh mock query chi tiết | Repository và database thật |
| HTTP client tới dịch vụ ngoài | Stub/mock port để điều khiển kết quả | Adapter thật + HTTP stub server |
| Message publisher | Recording fake hoặc mock để kiểm tra event | Broker/container thật nếu cần xác minh giao thức và cấu hình |
| Clock | Fixed Clock | Fixed Clock hoặc nguồn thời gian kiểm thử |
| File storage | Fake filesystem hoặc adapter giả lập | Filesystem thật trong thư mục tạm nếu cần kiểm tra semantics |
| Email/SMS provider | Mock/recording fake | Adapter thật với server giả lập hoặc sandbox |
| Security filter chain | Không liên quan trong unit test service thuần | Giữ filter chain thật khi kiểm tra quyền ở web layer |
| Random/id generator | Generator cố định có thể thay thế | Kiểm thử adapter nếu cần xác minh tích hợp |

### 4.1. Khi nào nên giữ repository thật?

Giữ repository và database thật khi mục tiêu liên quan đến:

- Tên bảng, cột, kiểu dữ liệu và quan hệ entity.
- JPQL, Criteria, native SQL hoặc query derivation.
- Lazy/eager loading và cascade.
- Unique constraint, foreign key và optimistic locking.
- Transaction, rollback và isolation.
- Pagination, sorting hoặc truy vấn phụ thuộc database dialect.

Một mock repository có thể trả đúng entity cho service, nhưng không chứng minh các truy vấn đó chạy được. Với những mục tiêu này, hãy dùng @DataJpaTest hoặc @SpringBootTest cùng database kiểm thử. Nếu production dùng PostgreSQL, MySQL hoặc một database cụ thể, Testcontainers giúp kiểm tra gần với hệ quản trị đó hơn database nhúng.

### 4.2. Khi nào nên thay repository?

Trong unit test của application service, nếu mục tiêu là quyết định nghiệp vụ và repository chỉ là cổng lưu trữ, một fake in-memory thường đủ. Fake cho phép test xác nhận trạng thái cuối qua API đọc dữ liệu.

Mock repository cũng có thể phù hợp khi service cần phản ứng với một lỗi lưu cụ thể hoặc khi cần kiểm tra một command lưu dữ liệu có ý nghĩa. Tuy nhiên, tránh verify quá chi tiết chuỗi find/save chỉ để khẳng định implementation gọi đúng các phương thức nội bộ.

### 4.3. Khi nào nên giữ HTTP adapter thật?

Nếu mục tiêu là kiểm tra service xử lý phản hồi của đối tác, thay port của đối tác bằng stub giúp tập trung vào nghiệp vụ. Nếu mục tiêu là kiểm tra adapter HTTP, hãy giữ HTTP client, serialization, headers, authentication mapping và error mapping thật, rồi dùng HTTP stub server để điều khiển phản hồi.

Ví dụ, một test của PaymentHttpAdapter có thể khởi động WireMock hoặc MockWebServer, cấu hình URL local và kiểm tra:

- HTTP method và path được gửi.
- Header xác thực hoặc idempotency được đặt đúng.
- Request body chứa đúng số tiền và currency.
- Response thành công được chuyển thành PaymentResult.
- HTTP 4xx/5xx, timeout hoặc response sai định dạng được ánh xạ theo hợp đồng.

Trong test service, không cần lặp lại toàn bộ các kiểm tra HTTP này. Hãy để adapter test chịu trách nhiệm cho giao thức và service test chịu trách nhiệm cho quy tắc ứng dụng.

## 5. Ví dụ xuyên suốt: kiểm thử dịch vụ đặt hàng

Giả sử OrderApplicationService nhận yêu cầu đặt hàng, kiểm tra sản phẩm, yêu cầu thanh toán, lưu đơn và phát sự kiện. Các interface được định nghĩa ở ranh giới ứng dụng:

~~~java
interface ProductCatalog {
    Optional<Product> findById(long productId);
}

interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

interface OrderRepository {
    Order save(Order order);
    Optional<Order> findById(String orderId);
}

interface OrderEventPublisher {
    void publish(OrderPlaced event);
}
~~~

Trong unit test của service, ta có thể lựa chọn:

- ProductCatalog: fake để cung cấp sản phẩm và giá xác định.
- PaymentGateway: mock để stub kết quả thanh toán và xác minh command charge quan trọng.
- OrderRepository: fake để lưu đơn trong bộ nhớ và đọc trạng thái sau hành động.
- OrderEventPublisher: recording fake để ghi lại sự kiện đã phát.
- Clock: Clock.fixed để thời gian tạo đơn luôn xác định.

Mỗi lựa chọn có lý do. Fake repository cho phép kiểm tra trạng thái đơn hàng, recording publisher cho phép kiểm tra event, còn mock payment gateway phù hợp vì lệnh thanh toán là tác động ra hệ thống bên ngoài.

### 5.1. Chuẩn bị fake và recording fake

~~~java
class InMemoryProductCatalog implements ProductCatalog {
    private final Map<Long, Product> products = new HashMap<>();

    void add(Product product) {
        products.put(product.id(), product);
    }

    @Override
    public Optional<Product> findById(long productId) {
        return Optional.ofNullable(products.get(productId));
    }
}

class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(String orderId) {
        return Optional.ofNullable(orders.get(orderId));
    }
}

class RecordingOrderEventPublisher implements OrderEventPublisher {
    private final List<OrderPlaced> published = new ArrayList<>();

    @Override
    public void publish(OrderPlaced event) {
        published.add(event);
    }

    List<OrderPlaced> publishedEvents() {
        return List.copyOf(published);
    }
}
~~~

Những fake này chỉ chứa hành vi tối thiểu cần cho test. Chúng không cố mô phỏng JPA hoặc message broker. Khi một bài kiểm thử cần chứng minh những đặc tính đó, hãy dùng adapter thật trong một test khác.

### 5.2. Unit test cho nhánh thanh toán thành công

Ví dụ sau thể hiện cách kết hợp fake, mock và Clock cố định. Tên constructor, factory và kiểu dữ liệu domain là minh họa; điều quan trọng là ranh giới và bằng chứng của bài test.

~~~java
@ExtendWith(MockitoExtension.class)
class OrderApplicationServiceTest {

    @Mock
    PaymentGateway paymentGateway;

    InMemoryProductCatalog productCatalog;
    InMemoryOrderRepository orderRepository;
    RecordingOrderEventPublisher eventPublisher;
    OrderApplicationService service;

    @BeforeEach
    void setUp() {
        productCatalog = new InMemoryProductCatalog();
        orderRepository = new InMemoryOrderRepository();
        eventPublisher = new RecordingOrderEventPublisher();

        Clock clock = Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC
        );

        productCatalog.add(ProductFixtures.product(7L, "BOOK", "120.00"));

        service = new OrderApplicationService(
            productCatalog,
            paymentGateway,
            orderRepository,
            eventPublisher,
            clock
        );
    }

    @Test
    void saves_order_and_publishes_event_when_payment_is_approved() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved("PAY-100"));

        PlaceOrderResult result = service.placeOrder(
            new PlaceOrderCommand("CUSTOMER-1", 7L, 2)
        );

        assertThat(result.isSuccessful()).isTrue();
        Order saved = orderRepository.findById(result.orderId())
            .orElseThrow();
        assertThat(saved.paymentReference()).isEqualTo("PAY-100");
        assertThat(saved.createdAt())
            .isEqualTo(Instant.parse("2026-01-15T10:00:00Z"));
        assertThat(eventPublisher.publishedEvents())
            .extracting(OrderPlaced::orderId)
            .containsExactly(saved.id());

        ArgumentCaptor<PaymentRequest> requestCaptor =
            ArgumentCaptor.forClass(PaymentRequest.class);
        verify(paymentGateway).charge(requestCaptor.capture());
        assertThat(requestCaptor.getValue().amount())
            .isEqualByComparingTo("240.00");
    }
}
~~~

Test này xác nhận service tạo đơn đúng với phản hồi thanh toán, dùng thời gian xác định và phát sự kiện tương ứng. PaymentGateway được stub để điều khiển kết quả, đồng thời verify để xác nhận số tiền gửi đi. Repository và event publisher là fake có thể quan sát trạng thái cuối.

Nếu hợp đồng không yêu cầu chính xác một lời gọi charge, có thể bỏ verify số lần gọi. Nếu tính idempotency hoặc tránh thanh toán trùng là yêu cầu, số lần và khóa idempotency trở thành bằng chứng quan trọng và cần được kiểm tra riêng.

### 5.3. Unit test cho thanh toán bị từ chối

Một tình huống thất bại cần xác nhận hệ thống không tạo tác động tiếp theo trái với quy tắc:

~~~java
@Test
void does_not_save_order_or_publish_event_when_payment_is_declined() {
    when(paymentGateway.charge(any(PaymentRequest.class)))
        .thenReturn(PaymentResult.declined("INSUFFICIENT_FUNDS"));

    PlaceOrderResult result = service.placeOrder(
        new PlaceOrderCommand("CUSTOMER-1", 7L, 2)
    );

    assertThat(result.isSuccessful()).isFalse();
    assertThat(orderRepository.count()).isZero();
    assertThat(eventPublisher.publishedEvents()).isEmpty();
}
~~~

Ví dụ trên giả định hợp đồng nghiệp vụ quy định không lưu đơn và không phát OrderPlaced khi thanh toán bị từ chối. Nếu hệ thống thực tế có trạng thái PENDING_PAYMENT hoặc cần lưu một lần thử thanh toán thất bại, assertion phải phản ánh hợp đồng đó. Test không được tự áp đặt một chính sách chưa được xác nhận.

### 5.4. Vì sao không mock mọi collaborator?

Nếu thay ProductCatalog, OrderRepository và OrderEventPublisher bằng mock, bài test sẽ phải stub nhiều lời gọi rồi verify nhiều tương tác:

- findById trả về sản phẩm.
- save được gọi với đơn nào.
- publish được gọi với event nào.
- PaymentGateway charge được gọi ra sao.

Một test như vậy có thể hữu ích trong một số trường hợp, nhưng thường khó đọc hơn và dễ gắn chặt vào thứ tự gọi nội bộ. Fake repository và recording publisher cho phép kiểm tra trạng thái kết quả trực tiếp. Chỉ PaymentGateway được mock vì nó là ranh giới bên ngoài mà test cần điều khiển và xác minh.

## 6. Chọn ranh giới theo từng tầng Spring

Một ứng dụng Spring có thể được kiểm tra ở nhiều tầng. Cùng một dependency có thể thật trong test này và được thay thế trong test khác.

### 6.1. Unit test không khởi động Spring context

Với logic domain hoặc application service thuần, hãy khởi tạo SUT trực tiếp qua constructor. Cách này:

- Làm rõ dependencies thật sự cần thiết.
- Tránh thời gian khởi động ApplicationContext.
- Giúp test điều khiển từng collaborator.
- Không bị ảnh hưởng bởi cấu hình bean hoặc component scanning.

MockitoExtension có thể tạo mock và quản lý strict stubbing. Tuy nhiên, không bắt buộc dùng annotation. Tạo mock bằng Mockito.mock hoặc dùng fake bằng Java thuần đều hợp lệ.

Ưu tiên constructor injection trong production code. Nó giúp test cung cấp đủ dependency và phát hiện sớm khi class có quá nhiều trách nhiệm hoặc phụ thuộc khó thay thế.

### 6.2. Web slice với @WebMvcTest

Trong test controller, mục tiêu thường là HTTP mapping, request binding, validation, response serialization và security behavior thuộc web layer.

Giữ Spring MVC infrastructure thật. Thay application service ở ranh giới controller bằng mock hoặc stub nếu test chỉ tập trung vào web contract:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderApplicationService orderService;

    @Test
    void returns_created_response_when_service_accepts_order()
            throws Exception {
        when(orderService.placeOrder(any(PlaceOrderCommand.class)))
            .thenReturn(PlaceOrderResult.success("ORDER-10"));

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId": 7, "quantity": 2}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.orderId").value("ORDER-10"));
    }
}
~~~

Ở đây, mock service là ranh giới có chủ đích: controller test không chứng minh nghiệp vụ đặt hàng. Nó chứng minh HTTP request được chuyển thành lời gọi ứng dụng và kết quả được chuyển thành response đúng.

Nếu cần xác minh service thật xử lý yêu cầu, hãy viết test service riêng hoặc integration test. Đừng suy luận rằng controller test đã chứng minh toàn bộ luồng chỉ vì nó trả status 201.

### 6.3. Data slice với @DataJpaTest

Trong repository test, giữ entity mapping, repository implementation và database test thật. Không thay repository bằng mock vì đó là đối tượng đang được kiểm tra.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void finds_orders_by_customer_id() {
        orderRepository.save(OrderFixtures.forCustomer("CUSTOMER-1"));
        orderRepository.save(OrderFixtures.forCustomer("CUSTOMER-2"));

        List<Order> result =
            orderRepository.findAllByCustomerId("CUSTOMER-1");

        assertThat(result)
            .extracting(Order::customerId)
            .containsExactly("CUSTOMER-1");
    }
}
~~~

Ví dụ này minh họa ranh giới persistence. Nếu test thay OrderRepository bằng mock, câu truy vấn findAllByCustomerId sẽ không được thực thi và test không còn chứng minh điều đang cần kiểm tra.

### 6.4. Application integration với @SpringBootTest

Khi cần xác minh nhiều bean thật phối hợp, hãy dùng @SpringBootTest. Thay thế những phụ thuộc nằm ngoài phạm vi cần kiểm tra, chẳng hạn cổng thanh toán hoặc dịch vụ gửi email.

Trong Spring Boot 3.3, @MockBean thường được dùng để thay bean trong ApplicationContext. Với các phiên bản Spring Framework mới hơn có hỗ trợ bean override, @MockitoBean là lựa chọn tương ứng. Hãy dùng annotation phù hợp với phiên bản dự án.

Một integration test đặt hàng có thể giữ thật controller, service, repository và database Testcontainers, trong khi thay PaymentGateway bằng mock hoặc một server giả lập. Cách chọn phụ thuộc mục tiêu:

- Nếu cần kiểm tra service phản ứng với approved/declined: mock port thanh toán là đủ.
- Nếu cần kiểm tra PaymentHttpAdapter tạo request đúng: dùng adapter thật và HTTP stub server.
- Nếu cần kiểm tra toàn bộ luồng qua giao thức thanh toán: dùng sandbox hoặc môi trường hợp đồng được kiểm soát, với chính sách dữ liệu riêng.

Không nên thay tất cả bean chỉ để ApplicationContext khởi động được. Nếu một bean quan trọng không được tạo do cấu hình sai, việc mock bean đó có thể che giấu lỗi wiring.

### 6.5. Security và authentication

Nếu test cần chứng minh endpoint cho phép hoặc từ chối người dùng theo role, hãy giữ Security filter chain thật. Có thể dùng test principal như @WithMockUser để kiểm soát danh tính mà không gọi identity provider bên ngoài.

Nếu mục tiêu là kiểm tra OAuth2 login, token decoding hoặc mapping claim, cần một test ở đúng adapter/security boundary với token hoặc issuer giả lập. Không mock toàn bộ security layer trong bài test đang muốn chứng minh authorization.

### 6.6. Reactive web với WebFlux

Với WebFlux, giữ WebFlux infrastructure thật trong @WebFluxTest và dùng WebTestClient. Thay application service nếu mục tiêu là web contract. Khi kiểm tra service reactive, có thể cung cấp publisher giả định hoặc mock port, rồi kiểm tra signal, error và completion theo yêu cầu.

Nếu mục tiêu là backpressure, cancellation hoặc tương tác với broker reactive, test double đơn giản có thể không đủ. Hãy chọn công cụ có thể tạo và quan sát các signal cần thiết, hoặc chạy integration test với adapter thật.

## 7. Thay thế ở đúng phía của adapter

Một nguyên tắc hữu ích là thay dependency ở ranh giới do ứng dụng kiểm soát, thường là interface/port mà application layer gọi tới. Điều này giữ cho nghiệp vụ không phụ thuộc trực tiếp vào thư viện HTTP, database hoặc vendor SDK.

Ví dụ:

~~~text
OrderApplicationService
    |
    +-- ProductCatalog
    |       |
    |       +-- JpaProductCatalogAdapter
    |
    +-- PaymentGateway
    |       |
    |       +-- PaymentHttpAdapter
    |
    +-- OrderRepository
    |       |
    |       +-- JpaOrderRepositoryAdapter
    |
    +-- OrderEventPublisher
            |
            +-- KafkaOrderEventPublisher
~~~

Unit test của OrderApplicationService thay các port. Test của PaymentHttpAdapter giữ adapter và HTTP client thật nhưng điều khiển server bên kia. Test của JpaOrderRepositoryAdapter giữ JPA và database thật. Test của KafkaOrderEventPublisher có thể dùng broker container hoặc một adapter test phù hợp.

Như vậy, mỗi test tập trung vào một ranh giới và có bằng chứng riêng. Một fake ở application layer không thay thế test adapter; test adapter cũng không cần lặp lại toàn bộ quy tắc nghiệp vụ.

### 7.1. Đừng mock thư viện thay cho ứng dụng

Mock trực tiếp một lớp của framework hoặc vendor SDK có thể khiến test phụ thuộc vào chi tiết của thư viện. Ví dụ, mock EntityManager trong service test thường tạo ra nhiều setup không phản ánh hợp đồng nghiệp vụ.

Hãy bọc khả năng bên ngoài bằng interface có ý nghĩa với ứng dụng, chẳng hạn PaymentGateway hoặc DocumentStorage. Adapter triển khai interface đó bằng thư viện cụ thể. Khi đó:

- Unit test thay port.
- Adapter test kiểm tra mapping tới thư viện/protocol.
- Integration test kiểm tra cấu hình và tương tác thực tế cần thiết.

Không cần tạo interface cho mọi class. Chỉ nên tạo abstraction khi nó thể hiện một ranh giới, một chính sách thay thế hoặc một hợp đồng có ý nghĩa.

## 8. Những dấu hiệu cho thấy đang thay thế sai

### 8.1. Test xanh nhưng hệ thống thật không chạy

Nếu mọi repository, HTTP client, event publisher và security component đều là mock, test có thể xanh dù query sai, URL sai, bean không được cấu hình hoặc transaction không hoạt động.

Hãy xem lại mục tiêu của test. Nếu cần chứng minh một adapter hoặc cấu hình Spring, giữ phần đó thật và thay phần nằm ngoài phạm vi.

### 8.2. Setup mock dài hơn logic đang kiểm tra

Một test cần hàng chục when và verify thường có thể đang kiểm tra quá sâu một đồ thị triển khai. Có thể chuyển một số collaborator thành fake, dùng fixture có ý nghĩa hoặc chia test theo ranh giới.

Không phải mọi setup dài đều sai: một protocol phức tạp có thể cần nhiều bước. Nhưng nếu test chỉ để chứng minh một quy tắc đơn giản mà phải cấu hình nhiều chi tiết nội bộ, hãy đánh giá lại thiết kế.

### 8.3. Verify thứ tự gọi không thuộc hợp đồng

Một service có thể đổi thứ tự gọi hai phương thức nội bộ mà vẫn tạo cùng kết quả đúng. VerifyInOrder hoặc verifyNoMoreInteractions có thể làm test dễ vỡ nếu thứ tự đó không phải một cam kết nghiệp vụ.

Chỉ kiểm tra thứ tự khi nó có ý nghĩa, ví dụ phải xác thực quyền trước khi thực hiện hành động nhạy cảm, phải reserve hàng trước khi xác nhận đơn, hoặc chỉ phát sự kiện sau khi commit theo hợp đồng đã chọn.

### 8.4. Spy che giấu một thiết kế khó kiểm thử

Nếu cần spy một service để chặn một private helper hoặc bỏ qua nửa phương thức, có thể class đang gộp nhiều trách nhiệm. Hãy xem xét tách collaborator có ý nghĩa hoặc kiểm thử qua API công khai.

Không dùng spy để gọi private method chỉ nhằm đạt coverage. Mục tiêu là kiểm tra hành vi công khai, không phải mở mọi chi tiết nội bộ cho test.

### 8.5. Fake không giống production ở phần quan trọng

In-memory repository có thể không phân biệt hoa thường giống database, không có constraint, không có transaction và không có concurrency. Nếu nghiệp vụ phụ thuộc những đặc tính đó, fake không đủ fidelity.

Hãy ghi rõ fake đảm bảo điều gì và không đảm bảo điều gì. Bổ sung integration test bằng hạ tầng phù hợp cho những thuộc tính mà fake không mô phỏng.

### 8.6. Mock một collaborator mà không biết vì sao

Một mock không nên xuất hiện chỉ vì class có dependency. Trước mỗi mock, hãy trả lời được:

- Nó giúp điều khiển dữ liệu nào?
- Nó giúp quan sát tác động nào?
- Vì sao không dùng collaborator thật hoặc fake?
- Việc thay nó có làm mất phần hành vi cần kiểm chứng không?

Nếu không có câu trả lời rõ ràng, có thể chưa cần mock.

## 9. Quản lý trạng thái và side effect trong test

Chọn test double đúng vẫn chưa đủ nếu trạng thái bị chia sẻ giữa các test hoặc side effect không được kiểm soát.

### 9.1. Tạo mới test double cho mỗi test

Fake có trạng thái như in-memory repository hoặc recording publisher nên được tạo mới trong setup của từng test. Không chia sẻ một fake mutable giữa các test chạy song song, trừ khi có chủ đích và đồng bộ phù hợp.

Với Mockito, mỗi test nên có mock lifecycle rõ ràng. MockitoExtension giúp khởi tạo và kiểm tra stubbing. Tránh giữ static mock hoặc dữ liệu test có thể thay đổi giữa các lượt chạy.

### 9.2. Cố định thời gian

Nếu service đọc thời gian hiện tại, hãy inject java.time.Clock thay vì gọi trực tiếp Instant.now() ở nhiều nơi. Trong test, dùng Clock.fixed:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Điều này giúp test xác nhận hạn dùng, thời điểm tạo bản ghi hoặc quy tắc ngày giờ mà không phụ thuộc thời điểm máy chạy.

### 9.3. Kiểm soát random và ID

Nếu ID ngẫu nhiên là một phần của kết quả, có thể inject ID generator để tạo giá trị xác định. Tuy nhiên, không nên thay một thuật toán sinh ID trong mọi test nếu thuật toán đó không phải mục tiêu. Có thể kiểm tra định dạng hoặc tính duy nhất ở một test riêng.

### 9.4. Side effect cần có ranh giới

Gửi email, gọi thanh toán hoặc publish event là tác động có thể ra khỏi tiến trình. Trong unit test, recording fake có thể giữ lại nội dung đã gửi để kiểm tra. Trong adapter test, server hoặc broker giả lập xác nhận giao thức. Trong integration test, container hoặc sandbox có thể chứng minh wiring và serialization.

Nếu yêu cầu đòi hỏi chỉ phát event sau khi transaction commit, một recording fake được gọi trực tiếp trong cùng transaction chưa đủ chứng minh semantics sau commit. Cần test đúng transaction event mechanism hoặc adapter/broker thực tế có liên quan.

## 10. Thiết kế test double dễ bảo trì

Test double cũng là code và cần có chất lượng.

### 10.1. Ưu tiên tên thể hiện vai trò

Tên như InMemoryOrderRepository, FixedClock, RecordingEventPublisher hoặc DecliningPaymentGateway cho người đọc biết đối tượng làm gì. Tên generic như MockHelper hoặc TestUtil thường che giấu mục đích.

### 10.2. Giữ fake nhỏ và đúng hợp đồng

Fake nên triển khai phần hợp đồng cần cho nhóm test. Nếu một interface quá rộng khiến fake phải triển khai nhiều phương thức không liên quan, có thể interface đang gộp nhiều trách nhiệm.

Không nên thêm logic nghiệp vụ vào fake để test pass. Fake repository có thể lưu và tìm entity; nó không nên tự tính phí giao hàng hoặc quyết định quyền đặt hàng thay cho SUT.

### 10.3. Dùng fixture cho dữ liệu domain

Fixture hoặc Object Mother có thể tạo đối tượng hợp lệ với mặc định rõ ràng:

~~~java
Product product = ProductFixtures.availableProduct()
    .withId(7L)
    .withPrice(new BigDecimal("120.00"));
~~~

Factory phải giúp test đọc dễ hơn. Nếu fixture ẩn những thuộc tính quyết định kết quả, hãy truyền chúng trực tiếp tại test hoặc dùng builder có giá trị mặc định dễ nhận ra.

### 10.4. Tránh stubbing không được dùng

Stubbing một phương thức nhưng SUT không gọi tới có thể cho thấy setup thừa hoặc đường đi của test không như dự kiến. MockitoExtension với strict stubbing thường giúp phát hiện các stub không dùng. Khi cần lenient, chỉ áp dụng cho stub cụ thể và có lý do.

Không dùng lenient cho cả test suite chỉ để dập cảnh báo. Cảnh báo có thể đang chỉ ra fixture quá rộng hoặc test không còn kiểm tra nhánh dự định.

## 11. Một số lựa chọn công cụ trong hệ sinh thái Spring

Các công cụ sau giúp hiện thực hóa ranh giới đã chọn:

| Nhu cầu | Công cụ thường dùng | Vai trò |
| --- | --- | --- |
| Mock/stub/spy đối tượng Java | Mockito | Điều khiển phản hồi và quan sát tương tác |
| Kiểm tra MVC controller | @WebMvcTest, MockMvc | Giữ MVC infrastructure thật, thay service khi phù hợp |
| Kiểm tra WebFlux | @WebFluxTest, WebTestClient | Giữ reactive web stack thật |
| Kiểm tra JPA | @DataJpaTest | Giữ mapping và repository thật |
| Kiểm tra nhiều bean | @SpringBootTest | Dựng ApplicationContext và chọn dependency thật/giả theo mục tiêu |
| Thay bean trong context | @MockBean ở Spring Boot 3.3; @MockitoBean ở các phiên bản Spring mới hỗ trợ | Thay một bean bằng Mockito mock |
| Cấu hình fake bean | @TestConfiguration, @Import | Đăng ký adapter/fake dành riêng cho test |
| Database thật trong container | Testcontainers | Kiểm tra database engine và cấu hình thực tế |
| HTTP service giả lập | WireMock, MockWebServer hoặc công cụ tương đương | Điều khiển phản hồi và xác minh HTTP request |
| Kiểm tra MVC không server | MockMvc | Gửi request qua Spring MVC trong test |
| Kiểm tra HTTP server đang chạy | @SpringBootTest với RANDOM_PORT và client phù hợp | Kiểm tra qua ranh giới HTTP thực |

Không cần sử dụng tất cả công cụ trong một dự án. Chọn công cụ dựa trên ranh giới đã xác định và phiên bản Spring thực tế.

### 11.1. Dùng @TestConfiguration cho fake

Khi một integration test cần giữ phần lớn ApplicationContext thật nhưng thay một adapter, có thể khai báo cấu hình test:

~~~java
@TestConfiguration
class FakePaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}
~~~

Sau đó import cấu hình này vào test phù hợp. Cách làm này có thể dễ đọc hơn việc thay bean bằng mock nếu fake có hành vi ổn định và cần được tái sử dụng. Hãy đảm bảo test configuration không vô tình được component scan vào ứng dụng production.

### 11.2. Dùng @MockBean hoặc @MockitoBean có chủ đích

Khi cần kiểm tra một bean khác trong Spring context và muốn thay một collaborator bằng Mockito mock, bean override là lựa chọn thuận tiện. Nhưng mỗi lần thay bean, hãy xác định rõ test đang bỏ qua phần nào.

Ví dụ, thay PaymentGateway trong test của OrderApplicationService giúp điều khiển phản hồi thanh toán. Thay OrderRepository trong test của OrderRepository lại làm mất chính implementation cần kiểm tra. Không dùng annotation chỉ vì nó làm context khởi động thành công.

## 12. Quy trình quyết định trước khi viết test

Có thể áp dụng quy trình sau cho mỗi test case:

**Bước 1 – Viết hành vi cần chứng minh.** Nêu điều kiện ban đầu, hành động và kết quả mong đợi bằng ngôn ngữ nghiệp vụ.

**Bước 2 – Xác định SUT.** Chỉ rõ class, adapter hoặc luồng ứng dụng nào đang được kiểm tra.

**Bước 3 – Liệt kê collaborator.** Ghi rõ dependency nào tham gia và phần nào của hợp đồng có ý nghĩa với test.

**Bước 4 – Đánh dấu ranh giới cần giữ thật.** Thành phần có hành vi cần chứng minh phải chạy thật ở mức phù hợp.

**Bước 5 – Chọn loại thay thế cho từng dependency.** Dùng stub để điều khiển kết quả, mock để kiểm tra tương tác có ý nghĩa, fake để cung cấp hành vi đơn giản, spy khi thực sự cần quan sát đối tượng thật, dummy cho tham số không được sử dụng.

**Bước 6 – Kiểm tra fidelity.** Xem test double có bỏ qua transaction, query, serialization, security, concurrency hoặc semantics quan trọng nào không.

**Bước 7 – Viết assertion theo kết quả.** Kiểm tra state và output trước; kiểm tra interaction khi nó là một phần của hợp đồng.

**Bước 8 – Chọn tầng Spring phù hợp.** Unit test, web slice, data slice hay application integration.

**Bước 9 – Bổ sung test adapter khi cần.** Đảm bảo các adapter bị thay trong unit test vẫn có test riêng với hạ tầng phù hợp.

**Bước 10 – Chạy độc lập và trong suite.** Xác nhận test không phụ thuộc thứ tự, dữ liệu dùng chung hoặc trạng thái rò rỉ.

## 13. Bảng tự rà soát quyết định thay thế

Trước khi hoàn tất một test, hãy tự trả lời:

| Câu hỏi | Nếu câu trả lời là Có |
| --- | --- |
| Thành phần này chính là thứ test cần xác minh? | Giữ implementation thật ở tầng kiểm thử phù hợp |
| Đây là hệ thống ngoài khó kiểm soát? | Thay ở port hoặc dùng server/container giả lập |
| Chỉ cần một kết quả cụ thể để đi qua nhánh? | Dùng stub |
| Cần chứng minh command hoặc side effect quan trọng? | Dùng mock hoặc recording fake |
| Cần một collaborator hoạt động đơn giản với trạng thái? | Cân nhắc fake |
| Cần kiểm tra giao thức, mapping hoặc cấu hình adapter? | Giữ adapter thật, giả lập phía đối tác |
| Fake không mô phỏng được đặc tính đang xét? | Dùng hạ tầng thật trong integration test |
| Setup mock đang mô tả quá nhiều chi tiết nội bộ? | Xem lại ranh giới, fake hoặc cấu trúc collaborator |

Một test có thể kết hợp nhiều cách. Ví dụ, application service test có thể dùng domain object thật, fake repository, stub payment gateway, recording event publisher và fixed clock. Đó là lựa chọn tốt nếu mỗi test double phục vụ một mục đích rõ ràng và test vẫn chứng minh đầy đủ hành vi của SUT.

## 14. Kết luận

Chọn thành phần cần thay thế bắt đầu từ việc xác định điều bài kiểm thử cần chứng minh. Giữ thật những thành phần mang hành vi thuộc phạm vi kiểm tra; thay thế các dependency bên ngoài hoặc những cộng tác viên mà test chỉ cần điều khiển. Stub cung cấp câu trả lời, mock kiểm tra tương tác, spy quan sát đối tượng thật và fake cung cấp một implementation đơn giản có thể hoạt động.

Trong Spring, ranh giới này được thể hiện qua unit test, web slice, data slice và integration test. @WebMvcTest nên giữ MVC infrastructure thật, @DataJpaTest nên giữ persistence thật, còn @SpringBootTest cho phép kết hợp bean thật với test double tại các ranh giới đã chọn. Một bộ test đáng tin không đo bằng số mock ít hay nhiều; nó được đánh giá bằng việc mỗi test tạo ra đúng bằng chứng cho hành vi mà nó tuyên bố kiểm tra.
