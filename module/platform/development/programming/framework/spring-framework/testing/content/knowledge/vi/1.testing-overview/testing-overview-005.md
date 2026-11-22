# Ranh giới giữa thành phần nghiệp vụ, container và hạ tầng ngoài

Khi kiểm thử một ứng dụng Spring, câu hỏi đầu tiên không nên là “dùng annotation nào?” mà là “đang muốn xác nhận điều gì?”. Một quy tắc nghiệp vụ có thể đúng dù Spring chưa khởi động. Một cấu hình Spring có thể tạo đúng bean nhưng truy vấn cơ sở dữ liệu vẫn sai. Một repository có thể hoạt động với cơ sở dữ liệu thử nghiệm nhưng lại gặp lỗi khi chạy trên hệ quản trị được dùng ở môi trường thật.

Để chọn đúng loại kiểm thử, cần phân biệt ba ranh giới:

1. **Thành phần nghiệp vụ** quyết định ứng dụng phải làm gì.
2. **Spring container** tạo, kết nối và quản lý các thành phần trong ứng dụng.
3. **Hạ tầng ngoài** cung cấp những khả năng nằm ngoài tiến trình ứng dụng, chẳng hạn cơ sở dữ liệu, message broker, Redis hoặc dịch vụ HTTP.

Ba ranh giới này liên quan với nhau khi ứng dụng chạy, nhưng mỗi ranh giới đặt ra một câu hỏi kiểm thử khác nhau.

Trong bài này, từ *container* chỉ **Spring IoC container** — vùng quản lý bean của Spring. Docker container hoặc container của hệ điều hành là khái niệm triển khai hạ tầng khác; chúng có thể được dùng để khởi chạy cơ sở dữ liệu và dịch vụ phục vụ kiểm thử.

## 1. Nhìn ứng dụng qua ba ranh giới

Một luồng xử lý điển hình có thể được hình dung như sau:

~~~mermaid
flowchart LR
    Client["HTTP / Message"] --> Adapter["Controller / Message Adapter"]
    Adapter --> UseCase["Application Service"]
    UseCase --> Domain["Domain Model / Business Rules"]
    UseCase --> Port["Port / Interface"]
    Port --> OutAdapter["Repository / HTTP Client / Broker Adapter"]
    OutAdapter --> Infra["Database / API / Broker"]

    Spring["Spring IoC Container"] -. "tạo và kết nối bean" .-> Adapter
    Spring -. "tạo và kết nối bean" .-> UseCase
    Spring -. "tạo và kết nối bean" .-> OutAdapter
~~~

Sơ đồ thể hiện ba loại trách nhiệm:

- Luồng nghiệp vụ quyết định thứ tự và ý nghĩa của các bước xử lý.
- Spring container cung cấp đối tượng, inject dependency, áp dụng cấu hình và quản lý vòng đời.
- Adapter giao tiếp với hệ thống bên ngoài thông qua giao thức hoặc driver tương ứng.

Một thành phần có thể nằm trong nhiều mối quan hệ. Ví dụ, **OrderService** là thành phần nghiệp vụ ở góc nhìn trách nhiệm, đồng thời có thể là một Spring bean ở góc nhìn cấu hình. Việc nó được Spring quản lý không làm cho quy tắc nghiệp vụ bên trong tự động trở thành trách nhiệm của Spring.

Cũng cần phân biệt **ranh giới logic** và **ranh giới triển khai**. Một repository adapter chạy trong cùng JVM vẫn là adapter hướng tới hạ tầng dữ liệu. Ngược lại, một Docker container có thể chỉ là cách khởi chạy PostgreSQL để kiểm thử; nó không phải Spring IoC container.

## 2. Thành phần nghiệp vụ: kiểm tra ứng dụng đưa ra quyết định đúng

Thành phần nghiệp vụ biểu diễn quy tắc và quyết định của ứng dụng. Tùy kiến trúc, nhóm này có thể gồm:

- Domain model, entity nghiệp vụ, value object và domain service.
- Application service hoặc use case điều phối một nghiệp vụ.
- Policy, validator, calculator và các quy tắc như tính giá, xét điều kiện, phân quyền nghiệp vụ.
- Interface/port mô tả khả năng mà nghiệp vụ cần từ bên ngoài.

Một thành phần nghiệp vụ tốt thường nhận dependency qua constructor hoặc interface. Nhờ vậy, quy tắc có thể được gọi trực tiếp trong JVM mà không cần khởi động Spring.

Ví dụ, dịch vụ đặt chỗ cần biết kho còn đủ hàng hay không. Quy tắc đặt chỗ có thể phụ thuộc vào một port:

~~~java
public interface StockPort {
    boolean hasEnough(String sku, int quantity);
}

public final class ReservationService {
    private final StockPort stockPort;

    public ReservationService(StockPort stockPort) {
        this.stockPort = stockPort;
    }

    public boolean canReserve(String sku, int quantity) {
        if (quantity <= 0) {
            return false;
        }
        return stockPort.hasEnough(sku, quantity);
    }
}
~~~

Có thể kiểm tra quy tắc bằng JUnit mà không tạo **ApplicationContext**:

~~~java
class ReservationServiceTest {

    @Test
    void rejectsNonPositiveQuantity() {
        StockPort stock = (sku, quantity) -> true;
        ReservationService service = new ReservationService(stock);

        assertFalse(service.canReserve("BOOK-01", 0));
    }

    @Test
    void acceptsQuantityWhenStockIsEnough() {
        StockPort stock = (sku, quantity) -> quantity <= 5;
        ReservationService service = new ReservationService(stock);

        assertTrue(service.canReserve("BOOK-01", 3));
    }
}
~~~

Ở đây, lambda đóng vai trò một fake đơn giản: nó cung cấp phản hồi có kiểm soát để bài kiểm thử tập trung vào quyết định của **ReservationService**. Nếu cần kiểm tra một tương tác cụ thể, có thể dùng mock; nếu cần mô phỏng trạng thái có thể thay đổi, một fake có bộ nhớ thường dễ đọc hơn.

Mục tiêu của kiểm thử này là xác nhận đầu vào và trạng thái phụ thuộc dẫn đến kết quả nghiệp vụ đúng. Nó không chứng minh rằng Spring đã đăng ký **ReservationService**, rằng repository truy vấn đúng SQL, hoặc rằng cơ sở dữ liệu thật có đủ dữ liệu.

### Khi nào không cần Spring?

Không cần khởi tạo Spring chỉ vì lớp có tên **Service**, hoặc vì trong ứng dụng thật lớp đó được đánh dấu **@Service**. Nếu bài kiểm thử chỉ cần xác nhận phép tính, điều kiện hay quyết định nghiệp vụ, hãy tạo đối tượng trực tiếp và cung cấp dependency phù hợp.

Một annotation Spring có thể phục vụ đăng ký bean hoặc cấu hình runtime. Nó không nhất thiết là một phần của thuật toán nghiệp vụ. Nếu bài kiểm thử phải khởi động cả ứng dụng để kiểm tra một phép tính đơn giản, phạm vi kiểm thử đang rộng hơn câu hỏi cần trả lời.

Ngược lại, nếu hành vi đang xét phụ thuộc vào proxy giao dịch, bảo mật method, cache hoặc một cơ chế do Spring áp dụng, tạo đối tượng bằng **new** sẽ bỏ qua cơ chế đó. Khi ấy cần một kiểm thử đi qua Spring container.

## 3. Spring container: kiểm tra cấu hình và cách các thành phần được kết nối

Spring IoC container quản lý các bean trong **ApplicationContext**. Container chịu trách nhiệm cho những hành vi như:

- Tìm hoặc đăng ký bean từ component scan, **@Configuration** và các cơ chế cấu hình khác.
- Giải quyết dependency và inject bean vào constructor, field hoặc method.
- Tạo bean theo điều kiện, profile và property.
- Quản lý vòng đời, scope và callback khởi tạo/hủy.
- Áp dụng **BeanPostProcessor**, AOP proxy và các cơ chế tích hợp.
- Kết nối các thành phần như transaction manager, security, validation, cache và web infrastructure.

Vì vậy, một kiểm thử ở ranh giới container cần trả lời câu hỏi về **cấu hình runtime**. Ví dụ:

- Với profile hoặc property này, bean nào được tạo?
- Hai dependency có được inject đúng implementation không?
- Cấu hình tự viết có được áp dụng cùng auto-configuration dự kiến không?
- Method có thực sự đi qua transaction proxy hoặc security proxy không?
- Controller có được Spring MVC nhận diện và ánh xạ đúng không?

Có thể dùng Spring TestContext Framework để tạo một context nhỏ cho cấu hình cần kiểm tra:

~~~java
@SpringJUnitConfig(ReservationConfiguration.class)
class ReservationWiringTest {

    @Autowired
    private ReservationService reservationService;

    @Test
    void createsReservationServiceBean() {
        assertNotNull(reservationService);
    }
}
~~~

Ví dụ này kiểm tra khả năng tạo và inject bean từ cấu hình đã chỉ định. Nó chưa chứng minh nghiệp vụ đặt chỗ đúng trong mọi tình huống; phần đó thuộc kiểm thử thành phần nghiệp vụ. Nó cũng chưa chứng minh adapter có thể kết nối với cơ sở dữ liệu thật.

Nếu cần kiểm tra cấu hình tự động có điều kiện của Spring Boot, **ApplicationContextRunner** có thể giúp dựng context theo từng bộ cấu hình/property nhỏ và quan sát bean được tạo. Cách này hữu ích khi muốn xác nhận điều kiện bật/tắt một cấu hình mà không phải khởi động toàn bộ ứng dụng.

### Chọn phạm vi context phù hợp

Spring Boot cung cấp nhiều cách tạo context. Mỗi cách có phạm vi và mục đích khác nhau:

| Cách kiểm thử | Phạm vi chính | Câu hỏi phù hợp |
|---|---|---|
| **@SpringJUnitConfig** / **@ContextConfiguration** | Context Spring được chỉ định | Cấu hình bean và dependency có hoạt động không? |
| **ApplicationContextRunner** | Context nhỏ, khởi tạo theo từng lần chạy | Auto-configuration có tạo bean đúng điều kiện không? |
| **@WebMvcTest** | Phần Spring MVC được chọn | Mapping, binding, validation và xử lý HTTP có đúng không? |
| **@DataJpaTest** | Các thành phần JPA liên quan | Mapping entity, repository và truy vấn có hoạt động không? |
| **@JsonTest** | Cấu hình JSON | Serialization và deserialization có đúng không? |
| **@SpringBootTest** | Context ứng dụng Spring Boot rộng hơn | Các cấu hình và thành phần chính có phối hợp được không? |

Tên annotation không tự quyết định mức độ chứng minh. Ví dụ, một bài **@SpringBootTest** thay repository bằng mock vẫn chưa kiểm tra truy vấn trên cơ sở dữ liệu thật. Một bài **@DataJpaTest** chạy trên H2 có thể xác nhận một số hành vi JPA nhưng chưa chắc tái hiện đầy đủ dialect, kiểu dữ liệu hoặc locking của PostgreSQL.

Hãy chọn context nhỏ nhất có thể kiểm tra hành vi đang quan tâm. Context nhỏ thường khởi động nhanh hơn, dễ hiểu hơn và giúp lỗi chỉ ra đúng vùng cấu hình. Chỉ dùng context rộng khi chính sự phối hợp giữa nhiều cấu hình là đối tượng cần kiểm tra.

### Những hành vi chỉ xuất hiện khi đi qua container

Một số cơ chế không thể được kiểm tra đầy đủ bằng cách gọi trực tiếp đối tượng:

- **Transaction proxy:** gọi method qua bean do Spring quản lý có thể mở hoặc tham gia transaction; gọi trực tiếp một object tự tạo không đi qua proxy đó.
- **AOP và method security:** lời gọi phải đi qua proxy hoặc cơ chế interceptor tương ứng mới thể hiện hành vi được áp dụng.
- **Dependency injection:** chỉ context mới chứng minh được các bean được chọn và kết nối đúng theo cấu hình.
- **Conditional configuration:** kết quả phụ thuộc vào classpath, property, profile hoặc điều kiện cấu hình tại thời điểm tạo context.
- **Lifecycle:** callback khởi tạo, hủy hoặc xử lý sau khi tạo bean thuộc vòng đời do container quản lý.

Khi kiểm tra những hành vi này, cần gọi đối tượng từ context theo cách tương tự ứng dụng thật. Việc chỉ kiểm tra **new ReservationService(...)** không thể chứng minh transaction proxy hoặc cấu hình Spring đang hoạt động.

## 4. Hạ tầng ngoài: kiểm tra khả năng giao tiếp với hệ thống thật

Hạ tầng ngoài là những hệ thống hoặc tài nguyên có vòng đời, giao thức, trạng thái hay cách vận hành độc lập với logic nghiệp vụ trong ứng dụng. Các ví dụ phổ biến:

- Cơ sở dữ liệu quan hệ như PostgreSQL, MySQL.
- Redis hoặc hệ thống lưu trữ khác.
- Kafka, RabbitMQ và message broker.
- Dịch vụ HTTP bên thứ ba hoặc một service nội bộ khác.
- File system, object storage, SMTP server và các dịch vụ mạng.

Ở ranh giới này, câu hỏi không chỉ là “bean đã được tạo chưa?” mà là “adapter có giao tiếp đúng với hệ thống mà nó đại diện không?”.

Ví dụ với persistence, các hành vi cần kiểm tra có thể gồm:

- Câu truy vấn thực tế có trả về đúng dữ liệu không?
- Mapping giữa entity và schema có chính xác không?
- Constraint, index, kiểu dữ liệu và migration có tương thích không?
- Transaction, isolation, locking và rollback có đáp ứng yêu cầu không?
- Ứng dụng có xử lý được lỗi kết nối hoặc lỗi từ hệ thống dữ liệu không?

Với HTTP client hoặc message adapter, các câu hỏi có thể là:

- Request có đúng method, path, header, payload và encoding không?
- Response thành công, lỗi hoặc không đúng định dạng được xử lý thế nào?
- Timeout, retry và lỗi mạng có được xử lý theo chính sách đã định không?
- Message có đúng schema, key, header và cơ chế acknowledgement không?

### Dùng hệ thống thật hay mô phỏng?

Không phải bài kiểm thử nào cũng cần kết nối một dịch vụ dùng chung. Có thể chọn nhiều mức độ thay thế hạ tầng:

| Cách cung cấp dependency | Đặc điểm | Phù hợp khi |
|---|---|---|
| Stub | Trả về phản hồi đã định trước | Cần kiểm tra một nhánh xử lý cụ thể |
| Mock | Ghi nhận và xác nhận tương tác | Cần xác nhận một lời gọi hoặc tham số quan trọng |
| Fake | Có triển khai đơn giản, giữ trạng thái trong bộ nhớ | Cần mô phỏng hành vi trong nhiều bước |
| In-memory implementation | Chạy cục bộ nhưng có ngữ nghĩa riêng | Chấp nhận được khác biệt so với hệ thống thật |
| Service giả lập giao thức | Mô phỏng HTTP, SMTP hoặc broker ở mức giao thức | Cần kiểm tra request/response và xử lý lỗi |
| Hạ tầng thật chạy tạm thời | Khởi chạy database, broker hoặc dịch vụ thực trong môi trường cô lập | Cần kiểm tra tương thích với công nghệ thật |

Stub, mock và fake hữu ích để kiểm soát tình huống. Chúng không chứng minh rằng driver, giao thức, schema hay cấu hình kết nối với hạ tầng thật hoạt động đúng.

Với cơ sở dữ liệu, H2 hoặc một in-memory database có thể giúp kiểm thử nhanh, nhưng không thể mặc định tương đương PostgreSQL hay MySQL. Khác biệt có thể xuất hiện ở SQL dialect, kiểu dữ liệu, collation, constraint, sequence, locking và hành vi transaction. Nếu ứng dụng phụ thuộc vào các đặc điểm đó, nên kiểm thử với đúng hệ quản trị hoặc một phiên bản tương thích được khởi chạy tạm thời.

**Testcontainers** thường được dùng để chạy các dịch vụ như PostgreSQL, Kafka hoặc Redis trong môi trường kiểm thử cô lập. Test có thể khởi tạo dịch vụ, cấu hình ứng dụng kết nối tới địa chỉ được cấp và dọn dẹp tài nguyên sau khi chạy. Nhờ đó, kiểm thử có thể xác nhận hành vi của adapter với công nghệ thực mà không cần dùng một máy chủ dùng chung lâu dài.

Với dịch vụ HTTP bên ngoài, có thể dùng WireMock hoặc MockWebServer để nhận request và trả response theo kịch bản. Đây là cách kiểm tra HTTP adapter ở ranh giới giao thức. Nó xác nhận ứng dụng tạo request và xử lý response như dự kiến, nhưng không xác nhận trạng thái hay logic nội bộ của nhà cung cấp dịch vụ thật.

### Cô lập và lặp lại được

Kiểm thử hạ tầng cần quản lý trạng thái rõ ràng:

- Mỗi test hoặc nhóm test phải có dữ liệu đầu vào xác định.
- Dữ liệu tạo ra cần được dọn dẹp hoặc đặt trong namespace/schema riêng.
- Không phụ thuộc vào thứ tự chạy test hay dữ liệu còn sót từ lần chạy trước.
- Port, credential và endpoint nên được cấp từ môi trường test thay vì ghi cố định.
- Timeout và retry phải đủ thực tế nhưng không khiến test treo kéo dài.
- Khi test chạy song song, cần tránh chia sẻ tài nguyên có trạng thái theo cách gây tranh chấp.

Nếu bài kiểm thử thất bại vì một database dùng chung đang bận hoặc một dịch vụ bên thứ ba mất kết nối, kết quả sẽ khó lặp lại. Môi trường tạm thời và dữ liệu cô lập giúp lỗi có thể được tái hiện và chẩn đoán.

## 5. Một nghiệp vụ, ba câu hỏi kiểm thử

Giả sử ứng dụng có use case đặt chỗ. Use case nhận yêu cầu, kiểm tra số lượng, lưu đơn đặt chỗ và gửi thông báo.

Có thể tách mục tiêu kiểm thử thành ba nhóm:

| Ranh giới | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Thành phần nghiệp vụ | Quyết định đặt chỗ có đúng không? | Số lượng không hợp lệ bị từ chối; đủ hàng thì chấp nhận |
| Spring container | Các thành phần được lắp ghép đúng không? | Bean của **ReservationService**, repository và publisher được inject theo cấu hình |
| Hạ tầng ngoài | Adapter giao tiếp đúng với công nghệ thật không? | Repository lưu/đọc trên PostgreSQL; publisher gửi message theo giao thức broker |

Một bộ kiểm thử có thể triển khai theo hướng sau:

**Ở mức nghiệp vụ**, tạo **ReservationService** trực tiếp và dùng **StockPort** fake để kiểm tra các trường hợp đủ hàng, thiếu hàng và số lượng không hợp lệ. Các bài này chạy nhanh và không cần Spring.

**Ở mức container**, dựng context với cấu hình ứng dụng hoặc một lát cắt phù hợp. Kiểm tra các bean được đăng ký, dependency được inject, profile/property chọn đúng implementation, và các proxy cần thiết có hiệu lực.

**Ở mức hạ tầng**, chạy repository adapter với database phù hợp, hoặc chạy publisher adapter với broker tạm thời. Kiểm tra dữ liệu và message ở phía hệ thống nhận để xác nhận adapter thực hiện đúng giao thức và ngữ nghĩa cần thiết.

Ba nhóm không thay thế nhau. Một bài kiểm thử nghiệp vụ tốt không chứng minh SQL đúng. Một bài kiểm thử context khởi động thành công không chứng minh database chấp nhận câu truy vấn. Một bài kiểm thử repository với database thật không tự chứng minh mọi quy tắc đặt chỗ đều đúng.

## 6. Những nhầm lẫn thường làm kiểm thử mất ý nghĩa

### Dùng **@SpringBootTest** cho mọi bài kiểm thử

Khi mọi test đều khởi động toàn bộ ứng dụng, thời gian chạy tăng và lỗi cấu hình có thể che khuất lỗi nghiệp vụ. Một phép tính đơn giản không cần database, web server hay component scan.

Hãy để bài kiểm thử nghiệp vụ chạy độc lập. Dành context Spring cho hành vi phụ thuộc vào container và dành môi trường hạ tầng cho hành vi phụ thuộc vào hệ thống ngoài.

### Thay repository bằng mock rồi kết luận database hoạt động

Mock repository chỉ xác nhận thành phần gọi repository theo tương tác đã định. Nó không chạy SQL, không kiểm tra mapping và không thực thi transaction trên database.

Muốn xác nhận persistence, cần có bài kiểm thử đi qua adapter và database phù hợp.

### Dùng in-memory database rồi mặc định production database cũng đúng

In-memory database có thể rất hữu ích, nhưng khác biệt về dialect và ngữ nghĩa có thể khiến một truy vấn chạy được trong test nhưng thất bại khi triển khai. Hãy chọn hệ quản trị theo các đặc điểm mà ứng dụng thực sự phụ thuộc.

### Tự tạo object nhưng kỳ vọng hành vi proxy của Spring

Một object được tạo bằng **new** không tự nhận transaction, AOP hoặc method security chỉ vì class có annotation. Các cơ chế đó cần được áp dụng qua container/proxy tương ứng.

Nếu mục tiêu là kiểm tra proxy, hãy lấy bean từ **ApplicationContext** và gọi method qua bean đó.

### Kiểm tra bean tồn tại rồi kết luận toàn bộ luồng đã đúng

Bean tồn tại chỉ chứng minh một phần cấu hình. Nó không chứng minh logic nghiệp vụ, truy vấn dữ liệu, request HTTP hay message đều đúng. Mỗi kết luận phải gắn với bằng chứng mà bài kiểm thử thực sự quan sát được.

### Dùng transaction rollback để giả định mọi side effect đều được hoàn tác

Rollback của database không tự thu hồi email đã gửi, message đã publish, file đã ghi hoặc lời gọi HTTP đã hoàn tất. Với test có side effect ngoài transaction, cần thiết kế dữ liệu và cleanup riêng, hoặc dùng adapter giả lập phù hợp.

## 7. Chọn ranh giới từ câu hỏi cần trả lời

Trước khi viết test, hãy diễn đạt mục tiêu thành một câu hỏi cụ thể:

1. **“Quy tắc này có đưa ra quyết định đúng không?”**  
   Kiểm thử trực tiếp thành phần nghiệp vụ bằng JUnit; cung cấp dependency bằng fake, stub hoặc mock khi cần.

2. **“Spring có tạo và kết nối đúng các thành phần không?”**  
   Dùng Spring TestContext, **ApplicationContextRunner** hoặc một Spring Boot test slice phù hợp. Kiểm tra bean, điều kiện cấu hình, proxy và vòng đời liên quan.

3. **“Adapter có làm việc đúng với hệ thống mà nó tích hợp không?”**  
   Kiểm thử adapter với service giả lập giao thức hoặc hạ tầng thật chạy tạm thời. Chọn đúng công nghệ khi ngữ nghĩa của công nghệ đó ảnh hưởng đến kết quả.

4. **“Các phần chính có phối hợp thành một luồng ứng dụng không?”**  
   Dùng kiểm thử tích hợp ở phạm vi rộng hơn, có thể là **@SpringBootTest**, rồi quyết định rõ dependency nào là thật và dependency nào được thay thế.

Khi một test thất bại, ranh giới được xác định rõ giúp khoanh vùng nguyên nhân. Lỗi kết quả tính toán thường nằm ở logic hoặc dữ liệu đầu vào. Lỗi không tìm thấy bean thường thuộc cấu hình container. Lỗi SQL, timeout hoặc không kết nối được broker thường thuộc adapter, cấu hình kết nối hoặc hạ tầng.

## 8. Kết luận về phạm vi chứng minh

Mỗi loại kiểm thử chỉ chứng minh những gì nó thực sự đi qua và quan sát được:

- Test thành phần nghiệp vụ chứng minh quy tắc được thực thi đúng trong điều kiện đã cung cấp.
- Test Spring container chứng minh cấu hình và cơ chế quản lý bean hoạt động trong context được dựng.
- Test hạ tầng chứng minh adapter giao tiếp đúng với hệ thống hoặc giao thức được sử dụng trong test.
- Test tích hợp rộng chứng minh các thành phần được chọn phối hợp với nhau trong một cấu hình cụ thể.

Khi thiết kế bộ kiểm thử Spring Framework, hãy giữ rõ ba ranh giới này. Một bộ test hiệu quả không phụ thuộc vào việc dùng nhiều annotation hay khởi động nhiều thành phần; nó phụ thuộc vào việc mỗi test tạo ra bằng chứng đúng cho câu hỏi mà nó đặt ra.

