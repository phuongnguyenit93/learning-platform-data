# Định tuyến đọc-ghi, độ trễ bản sao và nhất quán sau ghi trong Spring Data JPA

## 1. Vì sao ứng dụng cần định tuyến đọc-ghi?

Khi ứng dụng có nhiều truy vấn đọc và một database primary chịu trách nhiệm ghi, có thể bổ sung một hoặc nhiều read replica để phân tải. Ứng dụng gửi thao tác ghi tới primary, còn những truy vấn đọc phù hợp được gửi tới replica.

Kiến trúc này giúp mở rộng năng lực đọc, nhưng làm phát sinh một vấn đề quan trọng: replica thường nhận dữ liệu từ primary theo cơ chế replication bất đồng bộ. Sau khi primary commit một thay đổi, replica có thể chưa replay thay đổi đó. Một truy vấn đọc ngay sau khi ghi có thể thấy dữ liệu cũ.

Trong Spring Data JPA, cần thiết kế đồng thời ba phần:

- **Read/write routing:** chọn DataSource primary hoặc replica theo ý định của transaction.
- **Replica lag management:** đo và xử lý độ trễ đồng bộ của replica.
- **Consistency policy:** quyết định use case nào cần đọc dữ liệu mới nhất, use case nào chấp nhận dữ liệu trễ.

Không phải mọi truy vấn SELECT đều có thể gửi tới replica. Các truy vấn khóa pessimistic, thao tác cần read-your-writes, kiểm tra quyền hoặc trạng thái ngay sau ghi thường cần đọc từ primary.

## 2. Kiến trúc primary và read replica

Một topology phổ biến:

~~~text
                    Spring Boot application
                              |
                    Spring Data JPA / Hibernate
                              |
                    Routing DataSource
                       /           \
                 PRIMARY           REPLICA
                    |                 |
              Write + Read       Read-only traffic
                    |                 ^
                    +---- replication+
                         (async)
~~~

**Primary** là database nhận các transaction ghi. Nó cũng có thể phục vụ truy vấn đọc.

**Read replica** nhận thay đổi từ primary thông qua cơ chế replication của database. Replica thường được cấu hình chỉ đọc ở cấp database hoặc tài khoản kết nối.

**Routing DataSource** là lớp chọn DataSource phù hợp trước khi JDBC connection vật lý được lấy. Spring cung cấp **AbstractRoutingDataSource** để ánh xạ một routing key tới một DataSource đích.

Mỗi DataSource đích thường có connection pool riêng. Ví dụ primary có pool dành cho ghi và đọc nhất quán; replica có pool dành cho các truy vấn đọc có thể chấp nhận eventual consistency.

Routing diễn ra khi connection được lấy. Một JDBC connection đã được cấp từ primary sẽ tiếp tục thuộc primary trong suốt vòng đời connection/transaction đó. Không thể chuyển một transaction đang dùng connection primary sang replica chỉ bằng cách đổi routing key giữa chừng.

## 3. Replication bất đồng bộ và replica lag

Với asynchronous replication, primary có thể xác nhận commit trước khi replica áp dụng thay đổi tương ứng.

Ví dụ:

1. Người dùng cập nhật địa chỉ giao hàng.
2. Transaction commit trên primary thành công.
3. API trả về thành công.
4. Một request đọc tiếp theo được định tuyến sang replica.
5. Replica chưa replay transaction vừa commit nên trả về địa chỉ cũ.
6. Sau một khoảng thời gian, replica nhận và áp dụng thay đổi; truy vấn sau đó trả về địa chỉ mới.

Khoảng chênh giữa trạng thái primary và replica được gọi là **replica lag**.

Lag có thể phát sinh do:

- Mạng giữa primary và replica bị chậm hoặc gián đoạn.
- Replica thiếu CPU, I/O hoặc dung lượng xử lý WAL/binlog.
- Truy vấn dài hoặc transaction lâu trên replica làm trì hoãn replay.
- Một lượng lớn transaction được ghi trên primary.
- Replication bị pause, lỗi cấu hình hoặc replica đang recovery.
- Replica vừa restart hoặc đang thực hiện catch-up.

Lag không phải lúc nào cũng là một số millisecond cố định. Có database báo khoảng cách theo byte/log sequence, có database báo thời gian hoặc vị trí log. Cần dùng metric phù hợp với engine đang chạy.

### Eventual consistency

Khi replication bất đồng bộ hoạt động bình thường, replica cuối cùng sẽ hội tụ với primary nếu hệ thống tiếp tục truyền và replay log thành công. Đây là mô hình eventual consistency.

Một truy vấn đọc từ replica có thể trả về dữ liệu cũ trong một khoảng thời gian. Vì vậy, không được giả định mọi SELECT sau một commit đều nhìn thấy thay đổi vừa ghi.

## 4. Chọn consistency policy trước khi cấu hình routing

Trước khi viết code, hãy phân loại use case:

| Use case | Nguồn đọc phù hợp | Lý do |
|---|---|---|
| Cập nhật hồ sơ rồi trả lại hồ sơ vừa cập nhật | Primary hoặc entity đã cập nhật trong transaction | Cần read-your-writes |
| Kiểm tra số dư ngay sau giao dịch | Primary hoặc nguồn có bảo đảm nhất quán tương đương | Không chấp nhận số dư cũ |
| Đọc trạng thái đơn hàng ngay sau khi tạo | Primary trong thời gian pin phù hợp | Người dùng cần thấy đơn hàng mới |
| Dashboard tổng hợp có thể chậm vài giây | Replica | Chấp nhận eventual consistency |
| Báo cáo phân tích dữ liệu lớn | Replica/reporting database | Giảm tải primary |
| Đọc danh mục ít thay đổi | Replica nếu stale window được chấp nhận | Có thể phân tải |
| Đọc để quyết định cập nhật tiếp theo | Primary | Tránh quyết định dựa trên trạng thái cũ |
| SELECT FOR UPDATE hoặc pessimistic lock | Primary | Replica thường không cho phép ghi/khóa theo semantics cần thiết |

Không định tuyến chỉ dựa trên việc SQL bắt đầu bằng SELECT. Một truy vấn SELECT có thể dùng FOR UPDATE, gọi stored procedure có tác dụng ghi hoặc tham gia vào quy trình cần trạng thái mới nhất.

## 5. Định tuyến dựa trên transaction readOnly của Spring

Spring transaction có thuộc tính **readOnly**. Khi service khai báo:

~~~java
@Transactional(readOnly = true)
public CustomerProfile getProfile(Long customerId) {
    return customerRepository.findProfile(customerId);
}
~~~

Spring đánh dấu transaction hiện tại là read-only. Thuộc tính này là một hint cho transaction manager, JDBC driver và JPA provider để tối ưu xử lý đọc. Nó không tự động chọn replica nếu ứng dụng chưa cấu hình routing.

Một cách thường dùng là để routing DataSource đọc thuộc tính read-only của transaction:

~~~java
public enum DataSourceRoute {
    PRIMARY,
    REPLICA
}
~~~

~~~java
public class ReadWriteRoutingDataSource
        extends AbstractRoutingDataSource {

    @Override
    protected Object determineCurrentLookupKey() {
        boolean readOnly =
            TransactionSynchronizationManager.isCurrentTransactionReadOnly();

        return readOnly
            ? DataSourceRoute.REPLICA
            : DataSourceRoute.PRIMARY;
    }
}
~~~

Ý nghĩa:

- Transaction read-only được định tuyến sang replica.
- Transaction ghi, hoặc không có read-only transaction, được định tuyến sang primary.
- Primary nên là default target để các thao tác không có routing context vẫn an toàn.

Cách này chỉ phù hợp khi ứng dụng đã xác định rõ truy vấn trong read-only transaction có thể chấp nhận độ trễ replica. Nếu một use case cần đọc mới nhất, hãy chủ động dùng primary.

## 6. Cấu hình AbstractRoutingDataSource

Ví dụ cấu hình hai DataSource đích và một routing DataSource:

~~~java
@Configuration
public class DataSourceConfiguration {

    @Bean
    public ReadWriteRoutingDataSource routingDataSource(
            @Qualifier("primaryDataSource") DataSource primary,
            @Qualifier("replicaDataSource") DataSource replica) {

        ReadWriteRoutingDataSource routing =
            new ReadWriteRoutingDataSource();

        Map<Object, Object> targets = new HashMap<>();
        targets.put(DataSourceRoute.PRIMARY, primary);
        targets.put(DataSourceRoute.REPLICA, replica);

        routing.setTargetDataSources(targets);
        routing.setDefaultTargetDataSource(primary);
        return routing;
    }
}
~~~

Trong ví dụ này, hai bean primaryDataSource và replicaDataSource là connection pool riêng, thường dùng HikariCP. Phần cấu hình URL, credentials, pool size, timeout và driver được lược bỏ vì phụ thuộc database và môi trường.

**setTargetDataSources** khai báo routing key và DataSource tương ứng. **setDefaultTargetDataSource** chọn primary khi không có key phù hợp.

Nên cấu hình fallback về primary. Nếu route key bị thiếu hoặc code gọi repository ngoài transaction, thao tác vẫn đi tới database có thể đọc và ghi. Tuy nhiên, fallback không thay thế việc kiểm soát quyền truy cập và consistency policy.

Trong ứng dụng thực tế, cần bảo đảm routing DataSource được dùng thống nhất bởi cả EntityManagerFactory và transaction manager. Không để Hibernate sử dụng primary trực tiếp trong khi transaction manager lại sử dụng một routing DataSource khác.

## 7. Vì sao cần LazyConnectionDataSourceProxy?

Đây là chi tiết rất quan trọng khi routing theo TransactionSynchronizationManager.isCurrentTransactionReadOnly().

Spring transaction manager có thể lấy JDBC connection trong lúc bắt đầu transaction. Trạng thái transaction synchronization, bao gồm read-only flag, được công bố trong quá trình thiết lập transaction. Nếu routing DataSource quyết định primary/replica quá sớm, nó có thể chưa nhìn thấy read-only flag và luôn chọn primary.

**LazyConnectionDataSourceProxy** trì hoãn việc lấy connection vật lý cho tới khi ứng dụng thực sự cần thực thi JDBC statement. Khi câu SQL đầu tiên chạy, transaction đã được thiết lập và read-only state có thể được đọc đúng.

Cấu hình thường dùng:

~~~java
@Bean
@Primary
public DataSource dataSource(
        @Qualifier("routingDataSource") DataSource routingDataSource) {

    return new LazyConnectionDataSourceProxy(routingDataSource);
}
~~~

Trong kiến trúc này:

1. Transaction manager lấy một lazy connection proxy.
2. Spring thiết lập transaction attributes và read-only state.
3. Hibernate/JDBC thực thi statement đầu tiên.
4. Lazy proxy yêu cầu connection thật từ routing DataSource.
5. Routing DataSource đọc transaction read-only flag và chọn primary hoặc replica.

Nếu bỏ lớp lazy proxy trong cấu hình routing dựa trên transaction metadata, hãy xác minh thứ tự lấy connection của transaction manager/provider cụ thể. Đừng giả định routing key luôn sẵn sàng tại thời điểm DataSource nhận getConnection().

LazyConnectionDataSourceProxy cũng có khả năng cấu hình riêng một read-only DataSource trong các phiên bản Spring Framework hỗ trợ API đó. Có thể dùng cơ chế này thay cho custom routing khi policy đơn giản là chọn target theo trạng thái JDBC connection read-only. Hãy kiểm tra phiên bản Spring Framework của ứng dụng trước khi dùng API phiên bản mới.

## 8. Kết nối với Spring Boot, JPA và transaction manager

Trong Spring Boot, routing DataSource thường là DataSource chính mà JPA và transaction manager nhìn thấy.

Các nguyên tắc cấu hình:

- Đặt routing/lazy wrapper làm bean **@Primary** nếu ứng dụng có nhiều DataSource.
- Primary pool và replica pool là các bean riêng, có qualifier rõ ràng.
- EntityManagerFactory dùng DataSource wrapper.
- JpaTransactionManager dùng cùng EntityManagerFactory.
- Không inject trực tiếp primary hoặc replica pool vào repository/service thông thường.
- Chỉ thành phần health check hoặc migration được truy cập DataSource riêng khi có lý do rõ ràng.
- Cấu hình connection pool, timeout và monitoring riêng cho primary và từng replica.

Nếu tự khai báo nhiều DataSource, Spring Boot có thể không còn tự suy luận được một DataSource duy nhất để auto-configure. Hãy cấu hình rõ các bean JPA, transaction manager và migration tool theo topology thực tế.

## 9. Dùng @Transactional đúng ranh giới

Ví dụ service phân biệt thao tác đọc và ghi:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Customer getCustomer(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException(
                "Customer not found"
            ));
    }

    @Transactional
    public Customer changeEmail(Long id, String email) {
        Customer customer = repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException(
                "Customer not found"
            ));

        customer.changeEmail(email);
        return customer;
    }
}
~~~

Method đọc có read-only transaction nên có thể được định tuyến tới replica. Method ghi dùng transaction mặc định read-write và được định tuyến tới primary.

Trong method ghi, lệnh findById() cũng phải đọc từ primary vì nó tham gia transaction ghi. Đây là điều mong muốn: ứng dụng kiểm tra và thay đổi dựa trên cùng nguồn dữ liệu nhất quán.

Với Spring Data JPA, các method CRUD kế thừa có transaction configuration mặc định. Các declared query method thường cần transaction được xác định ở service hoặc cấu hình repository phù hợp. Khai báo transaction ở service giúp toàn bộ use case dùng cùng một nguồn dữ liệu và cùng transaction boundary.

## 10. Transaction propagation và routing key

Routing được quyết định theo transaction thực sự đang hoạt động, không chỉ theo annotation nằm trên method được gọi gần nhất.

Với propagation mặc định **REQUIRED**:

- Nếu chưa có transaction, Spring tạo transaction mới theo attributes của method.
- Nếu đã có transaction, method tham gia transaction hiện tại.
- Một method read-only gọi bên trong write transaction không biến transaction đó thành read-only.
- Một method ghi gọi bên trong read-only transaction hiện tại cũng không tự nâng transaction đó thành write transaction.

Ví dụ:

~~~java
@Transactional(readOnly = true)
public CustomerProfile loadProfile(Long id) {
    return customerRepository.findProfile(id);
}

@Transactional
public void updateCustomer(Long id, String email) {
    customerProfileService.loadProfile(id);
    customerRepository.updateEmail(id, email);
}
~~~

Nếu loadProfile() tham gia transaction ghi bên ngoài theo REQUIRED, cả hai thao tác vẫn sử dụng transaction hiện tại và route primary. Annotation read-only bên trong không làm chuyển connection đã lấy sang replica.

Không thiết kế một use case vừa cần read-only replica vừa cần ghi trong cùng một transaction rồi mong routing tự chuyển DataSource. Nếu cần một transaction độc lập, có thể cân nhắc propagation khác như **REQUIRES_NEW**, nhưng cần hiểu việc suspend transaction ngoài, lấy connection mới và tác động tới atomicity.

Không thay routing key sau khi transaction đã lấy connection. Hãy xác định consistency policy trước khi bắt đầu transaction.

## 11. Read-your-writes consistency

**Read-your-writes** là bảo đảm người dùng đọc lại được thay đổi do chính họ vừa ghi.

Ví dụ người dùng đổi tên hiển thị từ "An" sang "Bình". Sau khi API cập nhật trả thành công, request tiếp theo lấy hồ sơ cần thấy "Bình".

Nếu request tiếp theo được route tới replica chưa replay thay đổi, người dùng có thể thấy "An". Đây là vi phạm read-your-writes ở cấp ứng dụng dù replication vẫn đang hoạt động đúng theo mô hình eventual consistency.

Các chiến lược phổ biến:

### 11.1. Đọc từ primary sau khi ghi

Cách đơn giản và mạnh nhất là định tuyến các truy vấn cần đọc ngay sau ghi tới primary. Có thể giữ use case đọc và ghi trong cùng một write transaction hoặc gọi một service method được đánh dấu read-write.

### 11.2. Pin người dùng/session về primary trong một khoảng thời gian

Sau một write thành công, ứng dụng đánh dấu user/session/request context cần đọc từ primary trong một khoảng ngắn. Những request tiếp theo của cùng user được route tới primary cho tới khi hết thời gian pin hoặc replica đã theo kịp.

Cần thiết kế TTL, storage và phạm vi pin rõ ràng. Không dùng ThreadLocal cho trạng thái cần tồn tại qua nhiều HTTP request; ThreadLocal chỉ tồn tại trên thread hiện tại và không tự truyền qua request khác.

### 11.3. Dùng replication watermark hoặc consistency token

Một số database cung cấp vị trí log/commit như LSN, GTID hoặc token tương đương. Sau khi ghi, ứng dụng có thể giữ token và chỉ đọc replica khi replica đã replay tới vị trí ít nhất bằng token đó.

Đây là cách triển khai đặc thù database. Cần hiểu token đại diện cho commit nào, cách lấy vị trí sau commit, cách so sánh trên replica và timeout khi replica không theo kịp. Không dùng một phép so sánh LSN/GTID chung cho mọi database.

### 11.4. Dùng synchronous replication khi yêu cầu phù hợp

Một số database có thể cấu hình synchronous replication hoặc đợi replica xác nhận replay trước khi commit được xác nhận. Cách này có thể tăng consistency nhưng làm tăng latency ghi và phụ thuộc topology/failure policy.

Cần phân biệt replica đã nhận log, đã flush log và đã replay log. Một acknowledgement chỉ xác nhận nhận/flush chưa chắc bảo đảm truy vấn đọc trên replica nhìn thấy dữ liệu ngay. Hãy kiểm tra semantics cụ thể của database.

## 12. Eventual consistency có thể chấp nhận ở đâu?

Không phải màn hình nào cũng cần dữ liệu mới nhất từng millisecond.

Replica thường phù hợp với:

- Dashboard số liệu tổng hợp.
- Báo cáo hoạt động.
- Danh sách lịch sử không cần phản ánh commit vừa xảy ra ngay tức thì.
- Catalog hoặc nội dung ít thay đổi.
- Tìm kiếm, lọc dữ liệu có thể chấp nhận stale window ngắn.
- Các tác vụ phân tích không ảnh hưởng quyết định ghi ngay sau đó.

Không nên mặc định route replica cho:

- Số dư, hạn mức hoặc trạng thái thanh toán ngay sau giao dịch.
- Quyết định tồn kho, đặt chỗ hoặc cấp phát tài nguyên.
- Kiểm tra quyền truy cập vừa thay đổi.
- Kiểm tra idempotency hoặc trạng thái xử lý trong quy trình ghi.
- Truy vấn khóa bằng PESSIMISTIC_WRITE hoặc SELECT FOR UPDATE.
- Use case cần read-your-writes hoặc monotonic reads nghiêm ngặt.

Đưa consistency requirement vào thiết kế API/use case thay vì để developer tự đoán từ tên method.

## 13. Độ trễ replica và cách giám sát

Không nên chỉ đo replica lag bằng một con số trong dashboard. Hãy theo dõi cả replication health và tác động tới ứng dụng.

Các chỉ số nên có:

- Replication lag theo thời gian hoặc vị trí log.
- Khoảng cách byte/log giữa primary và replica.
- Thời gian kể từ lần replay cuối.
- Trạng thái streaming/recovery hoặc replication thread.
- Tốc độ nhận log và tốc độ replay.
- Query latency và error rate riêng theo từng DataSource.
- Pool active/idle/pending và connection acquisition time.
- Số request bị pin về primary vì consistency requirement.
- Số lần fallback do replica lỗi hoặc vượt lag threshold.

Tên metric và cách tính phụ thuộc database. Ví dụ PostgreSQL cung cấp thông tin replication sender/receiver và replay LSN; MySQL có trạng thái replication source/replica và GTID/worker metrics. Hãy dùng metric native của engine làm nguồn sự thật cho lag.

### Ngưỡng lag

Đặt ngưỡng theo yêu cầu nghiệp vụ:

- Dashboard chấp nhận trễ 10 giây có thể tiếp tục dùng replica khi lag dưới ngưỡng đó.
- Trang xác nhận thanh toán có thể yêu cầu primary ngay lập tức.
- Báo cáo lớn có thể dùng replica chuyên biệt với lịch refresh riêng.

Không dùng một ngưỡng lag duy nhất cho mọi endpoint. Nếu replica vượt ngưỡng, có thể tạm route các truy vấn nhạy cảm về primary hoặc trả lỗi/đánh dấu dữ liệu đang cập nhật tùy hợp đồng API.

## 14. Health check và failover

Một replica có thể kết nối được nhưng không replay log hoặc đã tụt quá xa. TCP health check đơn thuần không đủ để kết luận replica đủ an toàn cho mọi truy vấn.

Nên kiểm tra:

- Kết nối và authentication.
- Trạng thái replication.
- Read-only mode của replica.
- Replication lag và thời điểm replay gần nhất.
- Khả năng thực thi một query health check nhẹ.
- Connection pool và timeout.
- Replica có đang recovery hoặc bị pause hay không.

Khi replica lỗi, có hai policy phổ biến:

1. **Fallback về primary:** tăng tính sẵn sàng đọc nhưng có thể làm primary quá tải.
2. **Fail closed cho workload replica:** từ chối hoặc tạm dừng một số truy vấn đọc, giữ primary cho workload quan trọng.

Không tự động fallback toàn bộ traffic về primary mà không giới hạn tải. Khi nhiều replica cùng lỗi, primary có thể trở thành điểm nghẽn và làm cả hệ thống ngừng hoạt động.

Việc chuyển primary khi failover là quy trình khác với việc route đọc. Cần xác định primary mới, cập nhật endpoint/service discovery, fencing node cũ để tránh split-brain và xác minh replication topology trước khi nhận ghi.

## 15. Persistence context và cache có thể tạo dữ liệu cũ

Replica lag không phải nguyên nhân duy nhất khiến ứng dụng đọc thấy dữ liệu cũ.

### First-level cache

Persistence context của JPA giữ entity đã managed. Nếu entity đã được tải trước đó, gọi find() lại trong cùng EntityManager thường trả về object đang được quản lý mà không nhất thiết truy vấn database.

Vì vậy, ngay cả khi route primary, entity managed có thể vẫn giữ trạng thái cũ nếu đã có thay đổi ngoài persistence context.

Trong một write transaction, sau khi thay đổi entity managed, hãy dùng chính object đó hoặc flush theo nhu cầu. Nếu có native/bulk update, cần hiểu persistence context không tự đồng bộ; cân nhắc refresh/clear đúng phạm vi.

### Second-level cache và query cache

Hibernate second-level cache và query cache có thể giữ dữ liệu qua nhiều Session. Nếu cache invalidation hoặc cache coordination giữa node không đúng, ứng dụng có thể đọc trạng thái cũ dù truy vấn được gửi tới primary.

Hãy quan sát cache hit/miss, eviction, invalidation và cấu hình cache concurrency strategy. Đừng quy mọi kết quả cũ cho replica.

### Application cache

Redis, Caffeine hoặc cache trong service có thể còn giá trị cũ sau khi database commit. Cần có cache invalidation/update policy tương ứng với consistency requirement.

Read-your-writes phải xét toàn bộ đường đọc: primary/replica, persistence context, Hibernate cache và application cache.

## 16. Query khóa và truy vấn có tác dụng ghi

Không định tuyến truy vấn chỉ dựa trên SQL SELECT.

Ví dụ Spring Data JPA:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select o from Order o where o.id = :id")
Optional<Order> findForUpdate(@Param("id") Long id);
~~~

Query này cần database hỗ trợ lock phù hợp và phải chạy trên primary trong transaction ghi. Replica thường không cho phép lock theo cách phục vụ cập nhật nghiệp vụ.

Tương tự, các query có @Modifying, native stored procedure, SELECT FOR UPDATE, hoặc query kiểm tra trạng thái để ra quyết định ghi cần được định tuyến theo write intent.

Nếu route theo readOnly=true, hãy bảo đảm các use case này không được khai báo read-only. Không dùng parser SQL tự viết để đoán ý định từ chuỗi query; hãy xác định policy ở service/transaction boundary.

## 17. Trạng thái routing thủ công bằng ThreadLocal

Một số ứng dụng cần override route theo use case thay vì chỉ dựa trên read-only flag. Có thể dùng routing context riêng, nhưng phải quản lý vòng đời cẩn thận.

Ví dụ khung context:

~~~java
public final class DataSourceContext {

    private static final ThreadLocal<DataSourceRoute> ROUTE =
        new ThreadLocal<>();

    private DataSourceContext() {
    }

    public static void usePrimary() {
        ROUTE.set(DataSourceRoute.PRIMARY);
    }

    public static void useReplica() {
        ROUTE.set(DataSourceRoute.REPLICA);
    }

    public static DataSourceRoute current() {
        return ROUTE.get();
    }

    public static void clear() {
        ROUTE.remove();
    }
}
~~~

Routing DataSource có thể ưu tiên explicit route nếu có, rồi mới xét transaction read-only:

~~~java
@Override
protected Object determineCurrentLookupKey() {
    DataSourceRoute explicit = DataSourceContext.current();

    if (explicit != null) {
        return explicit;
    }

    return TransactionSynchronizationManager.isCurrentTransactionReadOnly()
        ? DataSourceRoute.REPLICA
        : DataSourceRoute.PRIMARY;
}
~~~

Phải đặt explicit route trước khi transaction lấy connection và dọn context trong finally:

~~~java
public Customer loadFromPrimary(Long id) {
    DataSourceContext.usePrimary();
    try {
        return transactionalCustomerReader.load(id);
    } finally {
        DataSourceContext.clear();
    }
}
~~~

Ví dụ này giả định transactionalCustomerReader là một bean khác được gọi qua Spring proxy và connection vật lý được lấy sau khi context đã được đặt. Không tự gọi method transactional bằng self-invocation rồi mong proxy mở transaction.

ThreadLocal có thể gây rò route sang request khác nếu quên remove(). Nó cũng không tự truyền qua executor, async task hoặc reactive pipeline. Trong reactive application, dùng Reactor Context và reactive transaction routing phù hợp thay vì ThreadLocal.

Nếu có thể diễn đạt consistency bằng transaction read-only/write và service boundary, hãy ưu tiên cách đó vì ít trạng thái ẩn hơn.

## 18. Không chuyển route giữa chừng trong một transaction

Một transaction JPA thường gắn với một EntityManager và một JDBC connection. Routing key được đọc lúc lấy connection vật lý.

Ví dụ không an toàn:

~~~java
@Transactional
public void processOrder(Long id) {
    DataSourceContext.useReplica();
    Order order = repository.findById(id).orElseThrow();

    DataSourceContext.usePrimary();
    order.confirm();
    repository.save(order);
}
~~~

Dù context thay đổi, connection đã lấy từ replica vẫn không tự chuyển sang primary. Câu lệnh ghi có thể thất bại vì replica read-only hoặc vi phạm transaction semantics.

Hãy xác định nguồn dữ liệu trước khi bắt đầu transaction. Nếu use case cần đọc rồi ghi, route toàn transaction tới primary.

## 19. Phân trang và nhiều query cần cùng consistency

Một endpoint Page có thể chạy query lấy nội dung và count query. Nếu hai câu được route tới các replica khác nhau hoặc replica ở thời điểm replay khác nhau, nội dung trang và total count có thể không khớp.

Khi cần tính nhất quán trong một response:

- Chạy content query và count query trong cùng transaction/read snapshot khi phù hợp.
- Dùng cùng routing policy và cùng replica/connection cho các câu lệnh của use case.
- Route primary nếu tổng số và nội dung cần phản ánh commit mới nhất.
- Cân nhắc Slice hoặc keyset pagination nếu không cần total count.
- Không chọn replica ngẫu nhiên cho từng statement trong cùng transaction.

Định tuyến nên diễn ra ở cấp transaction/connection, không phải chọn replica ngẫu nhiên ở mỗi câu SQL.

## 20. Migration và schema trên primary/replica

Flyway hoặc Liquibase thường thực hiện migration trên primary. Replication sau đó chuyển DDL/DML tương ứng sang replica theo khả năng của database và cấu hình replication.

Không chạy cùng một migration độc lập trên cả primary và replica nếu replica được quản lý bằng replication từ primary. Làm vậy có thể gây schema mismatch hoặc replication error.

Quy trình thường là:

1. Chọn một migration authority.
2. Chạy migration trên primary hoặc database migration endpoint được chỉ định.
3. Xác nhận migration hoàn tất và schema version đúng.
4. Theo dõi replica replay DDL/data change.
5. Chỉ đưa replica trở lại read pool khi schema và replication state đã tương thích với ứng dụng.
6. Triển khai code theo chiến lược tương thích ngược nếu ứng dụng cũ và mới chạy song song.

Với thay đổi schema phá vỡ tương thích, dùng expand-and-contract: thêm cấu trúc mới, deploy code tương thích, backfill dữ liệu, chuyển reads/writes, rồi mới xóa cấu trúc cũ.

## 21. Bảo vệ read replica ở cấp database

Routing trong ứng dụng là một lớp bảo vệ, nhưng không nên là lớp duy nhất.

Nên cấu hình replica với:

- Tài khoản database chỉ có quyền đọc cần thiết.
- Read-only mode ở cấp database nếu engine hỗ trợ.
- Không cấp quyền DDL hoặc DML cho user ứng dụng trên replica.
- Network policy chỉ cho phép ứng dụng và công cụ giám sát phù hợp.
- Credential riêng với primary.
- Monitoring cho các câu lệnh ghi bị từ chối và trạng thái replication.

**@Transactional(readOnly = true)** chỉ là metadata/hint trong Spring. Nó không phải cơ chế authorization hoặc bảo đảm database từ chối mọi thao tác ghi. Database privilege mới là lớp kiểm soát quyền thực tế.

## 22. Kiểm thử read/write routing

Cần integration test chứng minh route thực sự chọn đúng database, không chỉ kiểm tra annotation.

Nên có topology test với hai database hoặc hai schema có thể phân biệt:

- Ghi một bản ghi và xác minh nó xuất hiện ở primary.
- Gọi service read-only và xác minh query đi tới replica.
- Gọi service ghi và xác minh cả SELECT trong write transaction cũng đi primary.
- Kiểm tra method read-only tham gia outer write transaction vẫn dùng primary.
- Kiểm tra explicit primary override và cleanup ThreadLocal.
- Kiểm tra không có route context thì default là primary.
- Kiểm tra replica unavailable và fallback policy.
- Kiểm tra read-after-write trong thời gian replica lag.
- Kiểm tra query có pessimistic lock đi primary.
- Kiểm tra migration chỉ chạy trên primary.

Có thể dùng Testcontainers để dựng database engine mục tiêu. Nếu cần kiểm tra replication thực sự, phải tạo topology primary/replica tương ứng hoặc dùng môi trường integration riêng; hai container database độc lập không mô phỏng replication lag.

Một cách kiểm tra route đơn giản là mỗi database trả về một marker khác nhau từ query test hoặc expose hostname/server identity. Không dựa riêng vào log của determineCurrentLookupKey() vì connection pool có thể che khuất DataSource thực sự đã được dùng.

## 23. Observability và vận hành

Theo dõi riêng primary và từng replica:

| Metric | Mục đích |
|---|---|
| Query count theo route | Biết tải đọc/ghi phân bố thế nào |
| Query latency p50/p95/p99 | So sánh hiệu năng primary và replica |
| Connection pool active/idle/pending | Phát hiện pool cạn hoặc quá tải |
| Connection acquisition time | Phát hiện chờ connection |
| Replica lag/time since replay | Phát hiện dữ liệu replica quá cũ |
| Replication errors/reconnects | Phát hiện topology không ổn định |
| Primary CPU, I/O, lock waits | Đánh giá tải ghi và đọc còn lại |
| Read fallback/pinning count | Biết consistency policy đang dùng primary nhiều tới đâu |
| Stale-read incidents | Đo tác động thực tế tới người dùng |

Dùng metric tag có cardinality thấp như datasource, route, operation hoặc query name. Không đưa customer ID, order ID hoặc raw SQL có parameter vào metric label.

Log/trace nên có route name và trace ID để xác định request đã đi primary hay replica. Che dữ liệu nhạy cảm trong SQL bind logs.

## 24. Lỗi thường gặp

### 24.1. Nghĩ readOnly tự động route sang replica

**@Transactional(readOnly = true)** chỉ cung cấp transaction metadata/hint. Phải cấu hình routing DataSource hoặc read-only target mới có routing thực tế.

### 24.2. Routing chọn primary vì connection lấy quá sớm

Khi dùng TransactionSynchronizationManager để đọc read-only flag, connection vật lý lấy trước lúc transaction metadata sẵn sàng có thể làm route sai. Dùng LazyConnectionDataSourceProxy và kiểm thử đúng transaction manager/provider.

### 24.3. Dùng replica cho read-after-write

Replica bất đồng bộ có thể chưa replay commit mới nhất. Pin về primary hoặc dùng consistency token/watermark nếu cần bảo đảm.

### 24.4. Đổi ThreadLocal sau khi transaction đã bắt đầu

Connection đã được chọn thì không chuyển DataSource giữa transaction. Xác định route trước khi connection được lấy.

### 24.5. Cho rằng read-only transaction cấm ghi

Read-only thường là hint; mức enforcement phụ thuộc provider, driver và database. Dùng database user/privilege riêng để ngăn ghi trên replica.

### 24.6. Gọi transactional method bằng self-invocation

Lời gọi nội bộ trong cùng object thường không đi qua Spring proxy, nên transaction attributes có thể không được áp dụng. Tách bean hoặc gọi qua proxy đúng cách.

### 24.7. Không xử lý propagation

Method read-only lồng trong write transaction vẫn tham gia transaction ghi với REQUIRED. Method ghi lồng trong read-only transaction cũng không tự nâng cấp transaction đó.

### 24.8. Mọi replica lỗi đều fallback về primary

Fallback toàn bộ tải đọc có thể làm primary quá tải. Cần giới hạn traffic, circuit breaker, health policy và khả năng từ chối một số workload.

### 24.9. Chỉ kiểm tra replica có kết nối được

Replica có thể kết nối nhưng đang lag hoặc không replay. Theo dõi replication state và replay position.

### 24.10. Bỏ qua cache khi điều tra dữ liệu cũ

First-level, second-level, query cache và application cache đều có thể trả trạng thái cũ. Xác định chính xác tầng nào đã cung cấp dữ liệu.

## 25. Thiết kế khuyến nghị

Một thiết kế thực tế cho ứng dụng Spring Data JPA có primary và replica:

1. Dùng một primary pool và một hoặc nhiều replica pool.
2. Đặt AbstractRoutingDataSource trước các pool đích.
3. Dùng LazyConnectionDataSourceProxy để routing theo transaction read-only diễn ra đúng thời điểm.
4. Đặt primary làm default target.
5. Dùng @Transactional(readOnly = true) cho use case đọc chấp nhận eventual consistency.
6. Dùng transaction read-write cho use case ghi và mọi lần đọc phụ thuộc vào thay đổi mới nhất.
7. Xác định read-your-writes policy: primary pin, session stickiness hoặc replication watermark.
8. Không route query lock, query ghi hoặc quyết định nghiệp vụ nhạy cảm sang replica.
9. Theo dõi lag, route, latency và pool riêng cho từng DataSource.
10. Kiểm thử topology và failure mode trên database gần production.
11. Chạy migration trên primary và đợi replica replay schema change.
12. Bảo vệ replica bằng read-only database credentials và privileges.

Không cần route mọi truy vấn đọc sang replica ngay từ đầu. Hãy đo tải primary, xác định use case chấp nhận stale data, rồi mở rộng routing theo policy rõ ràng.

## 26. Ghi nhớ

- Primary nhận transaction ghi; read replica phục vụ các truy vấn đọc phù hợp.
- Replication bất đồng bộ tạo replica lag; truy vấn ngay sau commit có thể thấy dữ liệu cũ.
- Eventual consistency phù hợp với dashboard/báo cáo, nhưng không phù hợp với mọi quyết định nghiệp vụ.
- @Transactional(readOnly = true) là transaction hint, không tự chọn replica và không phải cơ chế phân quyền.
- AbstractRoutingDataSource chọn DataSource theo routing key; primary nên là default.
- LazyConnectionDataSourceProxy trì hoãn lấy connection vật lý để read-only transaction metadata sẵn sàng trước khi routing.
- Routing được quyết định khi lấy connection; không thể chuyển DataSource giữa chừng trong cùng transaction.
- REQUIRED tham gia transaction hiện có; annotation read-only lồng nhau không thay đổi route của transaction ngoài.
- Read-your-writes có thể bảo đảm bằng primary routing, pin user/session hoặc đợi replica đạt replication watermark.
- LSN/GTID/watermark là database-specific; phải hiểu chính xác semantics của log received, flushed và replayed.
- Query có lock, stored procedure ghi hoặc quyết định nghiệp vụ cần nguồn dữ liệu phù hợp, thường là primary.
- First-level, second-level, query cache và application cache cũng có thể làm dữ liệu cũ.
- Migration thường chạy trên primary; replica nhận thay đổi qua replication.
- Giám sát replica lag, query latency, pool usage, fallback và stale-read incidents.
- Test routing, transaction propagation, failover và read-after-write bằng topology gần production.

Định tuyến đọc-ghi chỉ có ích khi gắn với một consistency policy rõ ràng. Primary/replica giúp phân tải, còn transaction boundary, replica lag, cache và read-your-writes quyết định người dùng nhìn thấy dữ liệu nào sau mỗi thao tác.

## Tài liệu tham khảo

- [Spring Framework — AbstractRoutingDataSource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/lookup/AbstractRoutingDataSource.html)
- [Spring Framework — LazyConnectionDataSourceProxy](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/LazyConnectionDataSourceProxy.html)
- [Spring Framework — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [PostgreSQL — Monitoring Database Activity and Replication](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — Warm Standby and Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [MySQL — Replication Status](https://dev.mysql.com/doc/refman/8.4/en/replication-administration-status.html)