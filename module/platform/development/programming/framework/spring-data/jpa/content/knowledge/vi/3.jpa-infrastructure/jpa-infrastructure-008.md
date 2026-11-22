# Chế độ khởi tạo Repository DEFAULT, LAZY và DEFERRED trong Spring Data JPA

Spring Data JPA tạo repository bean từ các interface như JpaRepository. Quá trình này gồm đăng ký bean, tạo proxy, phân tích repository metadata, chuẩn bị query method và kết nối repository với hạ tầng JPA. Khi ứng dụng có nhiều repository, query method hoặc entity, thời điểm thực hiện các công việc này có thể ảnh hưởng đáng kể đến startup.

Spring Data cung cấp ba chế độ khởi tạo repository: DEFAULT, LAZY và DEFERRED. Chúng quyết định khi nào repository implementation được khởi tạo và kiểm tra trong vòng đời ApplicationContext. Chúng không thay đổi cách Hibernate thực thi SQL, transaction semantics, fetch strategy của entity hay mô hình blocking của JPA/JDBC.

## 1. Repository được khởi tạo gồm những gì?

Ví dụ một repository interface:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

Spring Data tạo implementation proxy cho interface. Những thành phần được xử lý trong quá trình khởi tạo thường gồm:

- Repository proxy và interceptor điều phối lời gọi method.
- Repository metadata: domain type, ID type, interface cha và repository fragment.
- Entity information và mapping metadata.
- Cơ chế phân tích tên method như findByEmail thành query.
- Query lookup strategy để tìm query khai báo, named query hoặc query sinh từ method.
- Thành phần thực thi query thông qua EntityManager.
- Các dependency hạ tầng như EntityManager, EntityManagerFactory và transaction infrastructure.

Không phải mọi query đều được thực thi lúc repository được tạo. Tuy nhiên, Spring Data có thể phân tích method và tạo query object khi khởi tạo repository. Với query khai báo bằng @Query, lỗi cú pháp hoặc tên thuộc tính có thể được phát hiện trong giai đoạn này, tùy loại query, provider và phiên bản.

Vì vậy, repository initialization là một phần của startup cost. Chế độ bootstrap quyết định chi phí đó xuất hiện ở giai đoạn nào.

## 2. So sánh nhanh ba chế độ

| Chế độ | Thời điểm khởi tạo implementation | Thời điểm lỗi bootstrap thường xuất hiện | Mục tiêu |
|---|---|---|---|
| DEFAULT | Eager trong quá trình startup của ApplicationContext | Khi context đang khởi tạo | Fail fast |
| LAZY | Khi repository được sử dụng lần đầu | Khi repository được truy cập lần đầu | Trì hoãn công việc chưa cần |
| DEFERRED | Lazy ban đầu, sau đó kích hoạt khi ContextRefreshedEvent được phát | Sau giai đoạn refresh context | Phối hợp thứ tự khởi tạo nhưng vẫn xác minh repository trong startup |

Cách nhớ ngắn gọn:

- DEFAULT: khởi tạo ngay khi Spring dựng context.
- LAZY: khởi tạo khi có lời gọi đầu tiên vào repository.
- DEFERRED: đăng ký proxy trước, rồi chủ động khởi tạo repository khi context refresh.

## 3. DEFAULT — eager initialization

DEFAULT là chế độ mặc định. Spring Data khởi tạo các repository singleton trong giai đoạn startup, không đợi request nghiệp vụ đầu tiên.

Luồng tổng quát:

1. Spring scan package và phát hiện repository interface.
2. Spring đăng ký bean definition.
3. Khi khởi tạo singleton beans, repository factory tạo repository proxy và cấu hình các thành phần cần thiết.
4. Query method và repository metadata được xử lý theo query lookup strategy.
5. Nếu repository không thể khởi tạo, ApplicationContext thường khởi động thất bại.

Ưu điểm:

- Phát hiện sớm nhiều lỗi khai báo repository, query method và mapping.
- Lần gọi repository đầu tiên sau startup thường không chịu toàn bộ chi phí tạo repository.
- Hành vi đơn giản, dễ dự đoán và dễ kiểm thử.
- Startup thành công là tín hiệu tương đối tốt rằng repository infrastructure đã được tạo.

Nhược điểm:

- Startup phải chờ khởi tạo repository.
- Ứng dụng có nhiều repository hoặc query method có thể mất thêm thời gian khởi động.
- Nếu EntityManagerFactory tốn thời gian bootstrap, repository có thể chờ hạ tầng JPA sẵn sàng.

DEFAULT thường là lựa chọn phù hợp nhất khi startup time chấp nhận được và hệ thống ưu tiên fail fast.

## 4. LAZY — khởi tạo khi sử dụng lần đầu

Với LAZY, Spring Data đăng ký lazy proxy cho repository. Repository implementation thật được khởi tạo khi có thao tác đầu tiên cần sử dụng nó.

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Optional<Customer> findByEmail(String email) {
        return repository.findByEmail(email);
    }
}
```

Trong chế độ LAZY, constructor của CustomerService có thể nhận proxy mà chưa cần khởi tạo repository implementation đầy đủ. Khi findByEmail được gọi lần đầu, proxy kích hoạt quá trình khởi tạo và chuyển lời gọi tới repository thật.

Ưu điểm:

- Có thể giảm startup time nếu có repository chưa được sử dụng.
- Hữu ích với module tùy chọn hoặc chức năng hiếm khi chạy.
- Trì hoãn chi phí khởi tạo cho tới khi chức năng thực sự cần.

Nhược điểm:

- Lần truy cập đầu tiên chịu thêm độ trễ khởi tạo.
- Lỗi query, mapping hoặc repository configuration có thể chỉ xuất hiện lúc runtime.
- Lỗi có thể xuất hiện trong một request production hiếm gặp.
- Nếu bean startup gọi repository trong constructor, lifecycle callback hoặc runner, repository vẫn bị khởi tạo sớm.

LAZY không bảo đảm startup nhanh hơn. Nếu ứng dụng gọi hầu hết repository trong giai đoạn startup, chi phí chỉ được chuyển sang thời điểm gọi đó.

## 5. DEFERRED — khởi tạo sau ContextRefreshedEvent

DEFERRED đăng ký repository proxy theo cách lazy ban đầu, nhưng khác LAZY ở cơ chế kích hoạt. Spring Data đăng ký listener để kích hoạt repository initialization khi ApplicationContext phát sự kiện ContextRefreshedEvent.

Trình tự tổng quát:

1. Spring scan repository và đăng ký lazy proxy.
2. Các bean khác trong ApplicationContext được tạo.
3. Context tiến tới trạng thái refreshed và phát ContextRefreshedEvent.
4. Spring Data kích hoạt khởi tạo các repository deferred.
5. Repository được xác minh trong giai đoạn startup thông thường, thay vì chờ request nghiệp vụ đầu tiên.

Ưu điểm:

- Tách repository initialization khỏi giai đoạn đăng ký và dựng bean ban đầu.
- Phối hợp tốt hơn với các hạ tầng được bootstrap bất đồng bộ.
- Vẫn có cơ hội phát hiện lỗi repository trong startup.
- Hữu ích khi EntityManagerFactory được tạo trên background executor.

Nhược điểm:

- Startup vẫn phải chờ bước deferred initialization.
- Không giúp nhiều nếu EntityManagerFactory và repository vốn khởi tạo rất nhanh.
- Không bỏ qua validation; lỗi repository vẫn có thể làm startup thất bại.
- Nếu bean khác gọi repository trước ContextRefreshedEvent, repository có thể bị khởi tạo sớm.

DEFERRED thường được cân nhắc khi cần trì hoãn giai đoạn khởi tạo ban đầu nhưng vẫn muốn kiểm tra repository trước khi ứng dụng hoàn tất startup.

## 6. Cấu hình trong Spring Boot

Với Spring Boot sử dụng Spring Data JPA auto-configuration, chọn chế độ bằng property:

```properties
# Mặc định: eager initialization
spring.data.jpa.repositories.bootstrap-mode=default

# Khởi tạo khi repository được dùng lần đầu
spring.data.jpa.repositories.bootstrap-mode=lazy

# Khởi tạo khi ApplicationContext được refresh
spring.data.jpa.repositories.bootstrap-mode=deferred
```

Nếu không khai báo property, chế độ mặc định là DEFAULT. Hãy bắt đầu bằng mặc định và chỉ thay đổi khi có số liệu startup hoặc yêu cầu bootstrap cụ thể.

Có thể đặt property trong application.properties hoặc theo profile. Ví dụ:

```properties
# application.properties
spring.data.jpa.repositories.bootstrap-mode=default
```

```properties
# application-prod.properties
spring.data.jpa.repositories.bootstrap-mode=deferred
```

Ví dụ này chỉ minh họa cấu hình theo môi trường; không có quy tắc production bắt buộc phải dùng DEFERRED.

Property của Boot áp dụng cho repository infrastructure do auto-configuration quản lý. Nếu dự án tự khai báo repository scanning bằng @EnableJpaRepositories, nên đặt bootstrapMode trực tiếp tại annotation để cấu hình được thể hiện rõ ở nơi bật repository.

## 7. Cấu hình bằng @EnableJpaRepositories

Có thể chọn chế độ trên annotation:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.config.BootstrapMode;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.customer.repository",
    bootstrapMode = BootstrapMode.DEFERRED
)
public class JpaRepositoryConfig {
}
```

Đổi giá trị thành BootstrapMode.DEFAULT hoặc BootstrapMode.LAZY để chọn hai chế độ còn lại.

Ví dụ LAZY:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.customer.repository",
    bootstrapMode = BootstrapMode.LAZY
)
public class LazyRepositoryConfig {
}
```

Lưu ý:

- BootstrapMode nằm trong package org.springframework.data.repository.config.
- @EnableJpaRepositories thường được dùng khi cần tùy chỉnh package scan, factory bean, EntityManagerFactory hoặc transaction manager.
- Nếu Spring Boot đã auto-configure repository, không nên thêm cấu hình annotation trùng lặp chỉ để đổi một property.
- Với nhiều persistence unit, mỗi nhóm repository phải gắn đúng EntityManagerFactory và transaction manager.
- Tránh cấu hình đồng thời property Boot và nhiều cấu hình repository thủ công mà không xác định rõ cấu hình nào có hiệu lực.

## 8. Vì sao DEFERRED hữu ích với EntityManagerFactory bootstrap bất đồng bộ?

EntityManagerFactory có chi phí khởi tạo đáng kể. Provider như Hibernate cần xử lý entity metadata, mapping, dialect, connection metadata và các thành phần persistence liên quan.

Spring Framework cho phép bootstrap EntityManagerFactory bất đồng bộ thông qua LocalContainerEntityManagerFactoryBean và AsyncTaskExecutor. Khi đó, việc tạo factory có thể diễn ra trên background executor.

Nếu repository eager initialization cần EntityManagerFactory quá sớm, startup thread có thể phải chờ factory sẵn sàng. Cách phối hợp thường được cân nhắc:

- EntityManagerFactory được bootstrap trên executor.
- Repository dùng LAZY hoặc DEFERRED để không buộc khởi tạo đầy đủ quá sớm.
- Với DEFERRED, ContextRefreshedEvent kích hoạt repository initialization sau giai đoạn bean registration ban đầu.
- Repository vẫn được xác minh trong startup thay vì đợi request đầu tiên.

Ví dụ phần cấu hình EMF:

```java
@Configuration
public class JpaBootstrapConfiguration {

    @Bean
    public AsyncTaskExecutor jpaBootstrapExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setThreadNamePrefix("jpa-bootstrap-");
        executor.initialize();
        return executor;
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean entityManagerFactory(
            DataSource dataSource,
            JpaVendorAdapter vendorAdapter,
            AsyncTaskExecutor jpaBootstrapExecutor) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.customer.domain");
        factory.setJpaVendorAdapter(vendorAdapter);
        factory.setBootstrapExecutor(jpaBootstrapExecutor);

        return factory;
    }
}
```

Đây là ví dụ phần cấu hình EMF, không phải toàn bộ cấu hình Boot. Ứng dụng phải cung cấp DataSource, JpaVendorAdapter, transaction manager và repository configuration phù hợp. Khi tự định nghĩa EMF, cần hiểu các auto-configuration nào của Boot đã back off.

Có thể kết hợp với:

```properties
spring.data.jpa.repositories.bootstrap-mode=deferred
```

Async bootstrap chỉ thay đổi cách EntityManagerFactory được tạo trong startup. JPA/JDBC sau đó vẫn là mô hình blocking. Nó không biến repository method thành Mono hoặc Flux, không làm SQL non-blocking và không thay thế R2DBC.

Không nên bật async bootstrap chỉ để tăng tốc khi chưa đo startup. Cấu hình này làm trình tự khởi tạo phức tạp hơn và cần xác minh tương thích với provider, datasource, executor và repository infrastructure.

## 9. Khác biệt giữa repository LAZY và các loại LAZY khác

Từ lazy xuất hiện ở nhiều tầng khác nhau:

| Khái niệm | Điều khiển điều gì? | Ví dụ |
|---|---|---|
| Repository BootstrapMode.LAZY | Thời điểm Spring Data khởi tạo repository implementation | Repository proxy được tạo, implementation tạo ở lần gọi đầu |
| Spring @Lazy | Thời điểm Spring khởi tạo một bean dependency | Một bean được tạo khi dependency được yêu cầu |
| JPA FetchType.LAZY | Thời điểm tải association hoặc thuộc tính entity | Truy cập order.getItems() có thể kích hoạt query |
| Hibernate lazy proxy/collection | Cách provider đại diện dữ liệu association chưa tải | Proxy entity hoặc persistent collection |

Ba điểm quan trọng:

1. BootstrapMode.LAZY không thay đổi FetchType của entity.
2. FetchType.LAZY không quyết định repository bean được tạo khi nào.
3. @Lazy của Spring là cơ chế bean chung; BootstrapMode là lựa chọn của Spring Data repository infrastructure.

Một repository được khởi tạo eager vẫn có thể trả về entity có association FetchType.LAZY. Ngược lại, repository bootstrap LAZY vẫn có thể thực thi query tải eager association khi được gọi.

## 10. Dependency injection và bean startup

Repository thường được inject vào service qua constructor:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }
}
```

Với LAZY hoặc DEFERRED, dependency injection có thể nhận proxy repository trước khi implementation thật được khởi tạo. Tuy nhiên, nếu constructor hoặc lifecycle callback gọi repository, lazy proxy sẽ bị kích hoạt ngay:

```java
@Service
public class StartupInitializer {

    public StartupInitializer(OrderRepository repository) {
        // Lời gọi này kích hoạt repository initialization.
        long count = repository.count();
    }
}
```

Trong ví dụ này, LAZY không còn trì hoãn repository tới request đầu tiên. Repository được khởi tạo trong lúc bean initializer được tạo. Tránh truy vấn database trong constructor.

Nếu cần chuẩn bị dữ liệu khi startup, có thể dùng ApplicationRunner hoặc CommandLineRunner, nhưng phải xác định rõ transaction, lỗi và readiness behavior. Runner gọi repository cũng sẽ kích hoạt repository LAZY.

DEFERRED giúp tách giai đoạn tạo bean khỏi giai đoạn khởi tạo repository, nhưng bean khác gọi repository sớm vẫn có thể kích hoạt nó trước ContextRefreshedEvent.

## 11. Tác động tới startup time và request đầu tiên

Không thể kết luận chế độ nào nhanh nhất nếu chưa đo toàn ứng dụng:

- DEFAULT đặt chi phí repository vào startup. Request đầu tiên thường không chịu toàn bộ chi phí tạo repository.
- LAZY có thể giảm startup nếu còn repository chưa dùng, nhưng request đầu tiên vào mỗi repository chưa khởi tạo sẽ chịu thêm độ trễ.
- DEFERRED trì hoãn một phần công việc khỏi giai đoạn bean registration, nhưng vẫn khởi tạo repository trước khi startup hoàn tất. Lợi ích phụ thuộc khả năng overlap với các tác vụ bootstrap khác.

Các yếu tố ảnh hưởng:

- Số repository interface và query method.
- Số entity, mapping, converter và repository fragment.
- Thời gian bootstrap EntityManagerFactory.
- DataSource có cần kết nối database để đọc metadata không.
- Provider và phiên bản Spring Data JPA/Hibernate.
- Bean startup có gọi repository hay không.
- Cách ứng dụng triển khai readiness và health check.

Khi đo, ghi nhận:

1. Thời gian process start tới ApplicationContext refreshed.
2. Thời gian context refresh tới ApplicationReady.
3. Thời gian khởi tạo EntityManagerFactory.
4. Thời gian repository initialization.
5. Độ trễ request đầu tiên vào từng repository.
6. Lỗi startup và lỗi first-use trong log.

Không chỉ đo tổng startup rồi kết luận LAZY tốt hơn. Nếu startup giảm nhưng request đầu tiên tăng mạnh, cần cân nhắc mục tiêu latency thực tế.

## 12. Chọn chế độ theo tình huống

### Chọn DEFAULT khi

- Ứng dụng có số lượng repository vừa phải.
- Muốn lỗi repository xuất hiện ngay khi khởi động.
- Startup time không phải vấn đề đáng kể.
- Không sử dụng async EntityManagerFactory bootstrap.
- Ưu tiên hành vi đơn giản và dễ kiểm thử.

Đây là lựa chọn mặc định phù hợp với phần lớn ứng dụng.

### Chọn LAZY khi

- Có repository thuộc module tùy chọn hoặc chỉ dùng trong luồng hiếm.
- Có số liệu cho thấy repository initialization ảnh hưởng đáng kể đến startup.
- Chấp nhận độ trễ ở lần truy cập đầu.
- Có cách kiểm tra repository quan trọng trước khi nhận traffic, hoặc chấp nhận lỗi xuất hiện khi dùng.
- Có monitoring để phát hiện lỗi first-use.

Không chọn LAZY chỉ vì tên gọi nghe có vẻ tối ưu. Nếu hầu hết repository được dùng ngay khi ứng dụng chạy, lợi ích có thể rất nhỏ.

### Chọn DEFERRED khi

- EntityManagerFactory được bootstrap bất đồng bộ.
- Cần trì hoãn repository initialization khỏi giai đoạn bean registration.
- Vẫn muốn repository được khởi tạo và kiểm tra trong startup.
- Muốn xác minh repository trước khi ứng dụng hoàn tất startup thông thường.

DEFERRED thường hợp lý hơn LAZY khi mục tiêu là phối hợp thứ tự khởi tạo và vẫn muốn fail fast trước khi ứng dụng nhận traffic.

## 13. Kiểm thử và xác minh

Có thể đặt bootstrap mode trong Spring Boot test:

```java
@SpringBootTest(properties = {
    "spring.data.jpa.repositories.bootstrap-mode=deferred"
})
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void canFindCustomerByEmail() {
        // Seed dữ liệu theo cấu hình test trước khi truy vấn.
        assertThat(repository.findByEmail("a@example.com"))
                .isPresent();
    }
}
```

Ví dụ cần có test database, dữ liệu seed và assertion library phù hợp. Đoạn code minh họa cách đặt property; phần setup phụ thuộc dự án.

Các hướng kiểm thử:

- DEFAULT: khởi tạo context và xác nhận repository được tạo; lỗi bootstrap được phát hiện sẽ làm context startup thất bại.
- LAZY: khởi tạo context không gọi repository, sau đó gọi repository và quan sát thời điểm initialization; kiểm tra lỗi first-use.
- DEFERRED: xác nhận repository được kích hoạt sau ContextRefreshedEvent; lỗi xuất hiện trong giai đoạn deferred initialization.
- Integration test: chạy query quan trọng trên database tương ứng để phát hiện lỗi chỉ xảy ra khi SQL thực thi.
- Startup test: đo cùng profile, database, JVM và dataset để so sánh công bằng.

Một test chỉ khởi tạo ApplicationContext chưa chắc kiểm tra được mọi câu SQL. Query có thể hợp lệ về JPA nhưng database thiếu cột, thiếu quyền hoặc khác dialect. Hãy có integration test trên hệ quản trị dữ liệu tương ứng production khi khác biệt schema/dialect quan trọng.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Startup nhanh nhưng request đầu tiên lỗi repository | LAZY trì hoãn lỗi tới lúc repository được kích hoạt | Chuyển DEFAULT/DEFERRED hoặc bổ sung startup validation |
| Startup vẫn chậm dù chọn LAZY | Bean initializer, runner hoặc health check đã gọi repository | Tìm lời gọi trong constructor, @PostConstruct, listener và runner |
| Chọn DEFERRED nhưng startup vẫn chờ repository | Deferred initialization diễn ra ở ContextRefreshedEvent | Đây là hành vi dự kiến; đo lại tổng startup time |
| Lỗi query xuất hiện sau ContextRefreshedEvent | Repository được khởi tạo ở giai đoạn deferred | Kiểm tra query method, entity property và declared query |
| Lỗi chỉ xuất hiện khi chạy SQL | Schema, quyền, dialect hoặc dữ liệu không phù hợp | Chạy integration test và kiểm tra SQL thực tế |
| Property không có tác dụng | Repository được cấu hình thủ công hoặc auto-configuration bị override | Kiểm tra @EnableJpaRepositories và cấu hình scanning |
| Repository bị khởi tạo sớm hơn dự kiến | Bean khác gọi method qua lazy proxy | Tìm call site trong constructor, init callback, listener và runner |
| Có nhiều repository factory hoặc EMF | Nhiều cấu hình repository scan chồng lấn | Phân tách package và chỉ rõ factory/transaction manager |

Không phải mọi lỗi database đều được phát hiện lúc khởi tạo repository. Ví dụ cột bị thiếu hoặc quyền SELECT bị từ chối có thể chỉ xuất hiện khi query thực thi.

## 15. Checklist trước khi đổi bootstrap mode

- [ ] Đã đo startup time bằng cùng môi trường và cấu hình.
- [ ] Đã xác định chi phí nằm ở EntityManagerFactory hay repository initialization.
- [ ] Đã kiểm tra số lượng repository và query method.
- [ ] Đã tìm constructor, @PostConstruct, listener, runner hoặc health check gọi repository.
- [ ] Đã xác định có async EntityManagerFactory bootstrap không.
- [ ] Đã hiểu lỗi xuất hiện tại startup, context refresh hay first use.
- [ ] Đã cân nhắc first-use latency nếu chọn LAZY.
- [ ] Đã xác định cấu hình đang có hiệu lực là property Boot hay @EnableJpaRepositories.
- [ ] Đã kiểm thử repository quan trọng trên database tương ứng.
- [ ] Đã xác nhận readiness chỉ báo ứng dụng sẵn sàng sau khi hạ tầng bắt buộc được khởi tạo.

## 16. Kết luận

DEFAULT khởi tạo repository eager trong startup, giúp phát hiện lỗi sớm và là lựa chọn an toàn cho phần lớn ứng dụng. LAZY dùng proxy và chỉ khởi tạo repository khi được gọi lần đầu, có thể giảm startup nhưng chuyển chi phí và một số lỗi sang runtime. DEFERRED trì hoãn khởi tạo ban đầu rồi kích hoạt repository khi ApplicationContext phát ContextRefreshedEvent, phù hợp khi cần phối hợp repository với async EntityManagerFactory bootstrap mà vẫn muốn kiểm tra repository trong startup.

Hãy chọn theo mục tiêu vận hành:

- Dùng DEFAULT khi ưu tiên đơn giản và fail fast.
- Dùng LAZY khi cần on-demand initialization và chấp nhận first-use latency.
- Dùng DEFERRED khi cần trì hoãn giai đoạn khởi tạo ban đầu nhưng vẫn xác minh repository trước khi ứng dụng hoàn tất startup.

Ba chế độ chỉ thay đổi lifecycle khởi tạo repository. Chúng không thay đổi transaction semantics, SQL execution model, entity fetch strategy hoặc khả năng non-blocking của JPA.
