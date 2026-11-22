# Tại sao TestContext giữ lại ApplicationContext để dùng chung

Khởi động một ứng dụng Spring trong mỗi bài kiểm thử có thể tốn nhiều thời gian. Spring phải đọc cấu hình, quét component, đánh giá điều kiện tạo bean, khởi tạo singleton, thiết lập proxy, cấu hình các tích hợp và đôi khi kết nối database hoặc dịch vụ khác. Nếu hàng chục test class cùng cần một cấu hình ứng dụng giống nhau mà lần nào cũng tạo lại toàn bộ context, thời gian chạy suite sẽ tăng đáng kể.

Spring TestContext Framework giải quyết vấn đề đó bằng **ApplicationContext cache**. Khi một test cần context, framework tìm trong cache một context đã được tạo với cấu hình tương đương. Nếu tìm thấy, test dùng lại context đó. Nếu chưa có, Spring tải context mới rồi lưu vào cache để các test tiếp theo có thể sử dụng.

Vì vậy, nhiều test class có thể dùng chung một ApplicationContext trong cùng một tiến trình JVM. Cơ chế này giảm thời gian khởi động và tránh lặp lại việc tạo bean, nhưng cũng có hệ quả: các bean singleton và trạng thái gắn với context được chia sẻ giữa những test dùng cùng cache entry. Muốn tận dụng cache an toàn, cần hiểu điều kiện nhận diện context, phạm vi tồn tại, các nguyên nhân tạo context mới và cách cô lập trạng thái kiểm thử.

## 1. Chi phí tạo ApplicationContext

ApplicationContext là container quản lý bean và cấu hình của ứng dụng Spring. Việc tạo context có thể bao gồm nhiều công việc:

1. Đọc class cấu hình, XML, component scan và import.
2. Xử lý bean definition và điều kiện cấu hình.
3. Đăng ký BeanFactoryPostProcessor và BeanPostProcessor.
4. Tạo các singleton eager-init.
5. Inject dependency và thực hiện initialization callback.
6. Tạo proxy cho transaction, security, caching hoặc aspect.
7. Thiết lập web infrastructure, message listener, client và các tích hợp khác.
8. Khởi tạo connection pool, ORM metadata hoặc những thành phần có chi phí khởi động đáng kể.

Không phải mọi context đều thực hiện tất cả các bước trên. Một unit test thuần Java không tạo Spring context. Một slice test như @WebMvcTest thường chỉ nạp một phần bean. Một @SpringBootTest có thể nạp phần lớn ứng dụng và thường có chi phí lớn hơn.

Giả sử một suite có 40 test class cùng cần một cấu hình web giống nhau. Nếu mỗi class tự tạo context mới, Spring có thể phải lặp lại quá trình cấu hình và khởi tạo 40 lần. Khi cache hoạt động, context được tạo ở lần đầu và các test sau có thể dùng lại context đó.

<text>
  <escape>40 test class với cùng cấu hình:</escape>
</text>

~~~text
Không dùng lại context:
Test 1  -> tạo context A -> chạy test -> đóng
Test 2  -> tạo context B -> chạy test -> đóng
Test 3  -> tạo context C -> chạy test -> đóng
...
Test 40 -> tạo context N -> chạy test -> đóng

Dùng TestContext cache:
Test 1  -> tạo context A -> lưu cache -> chạy test
Test 2  -> lấy context A từ cache -> chạy test
Test 3  -> lấy context A từ cache -> chạy test
...
Test 40 -> lấy context A từ cache -> chạy test
~~~

Sơ đồ trên minh họa trường hợp các test có cùng cache key và context chưa bị loại khỏi cache. Trên thực tế, một suite có thể cần nhiều context khác nhau do sử dụng profile, property, cấu hình web, bean override hoặc cấu hình slice khác nhau.

## 2. TestContext cache hoạt động như thế nào?

Spring TestContext Framework cung cấp một cơ chế chung để nạp và quản lý context cho các test framework được tích hợp. Trong JUnit Jupiter, SpringExtension phối hợp với TestContextManager. Khi test cần ApplicationContext, TestContext yêu cầu bộ nạp context lấy context từ cache hoặc tạo mới nếu chưa có.

Luồng khái quát:

~~~text
Test class bắt đầu
       |
       v
SpringExtension / TestContextManager
       |
       v
Tạo hoặc nhận diện MergedContextConfiguration
       |
       v
Tính cache key từ cấu hình đã hợp nhất
       |
       v
Tìm context trong ApplicationContext cache
       |
       +---- Có context phù hợp ----> Dùng lại context
       |
       +---- Không có ----------------> Nạp context mới
                                         |
                                         v
                                  Lưu vào cache
                                         |
                                         v
                                  Dùng cho test
~~~

Test class không cần tự quản lý Map chứa context. Framework thực hiện việc nhận diện, lưu, lấy lại và quản lý vòng đời cache.

### 2.1. Cache key là gì?

Spring không chỉ dựa vào tên test class để quyết định có thể dùng lại context hay không. Framework xây dựng một cấu hình đã hợp nhất, thường được biểu diễn bằng MergedContextConfiguration, rồi dùng cấu hình đó làm cơ sở tạo cache key.

Hai test class có thể dùng chung context khi cấu hình cần thiết của chúng tương đương và tạo ra cùng cache key. Nếu cấu hình khác nhau ở một yếu tố có ý nghĩa, Spring có thể tạo context riêng.

Các thành phần quan trọng tham gia nhận diện cache key gồm:

| Thành phần | Ví dụ hoặc ý nghĩa |
| --- | --- |
| locations | Các resource XML dùng để nạp context |
| classes | Các class cấu hình Spring |
| contextInitializerClasses | Các ApplicationContextInitializer |
| contextCustomizers | Các tùy chỉnh context, gồm nhiều cơ chế như @DynamicPropertySource và bean override |
| contextLoader | Bộ nạp context được sử dụng |
| parent | Context cha trong cấu hình hierarchy |
| activeProfiles | Các profile đang kích hoạt |
| propertySourceDescriptors | Mô tả nguồn property được khai báo cho test |
| propertySourceProperties | Các property inline trong annotation |
| resourceBasePath | Gốc web resource khi dùng @WebAppConfiguration |

Danh sách chi tiết có thể phát triển theo phiên bản Spring và các extension đang dùng. Điểm cần nhớ là cache key phản ánh cấu hình context đã hợp nhất, không phải chỉ tên class hoặc một annotation riêng lẻ.

### 2.2. Hai test class có thể dùng chung context

Ví dụ:

~~~java
@SpringBootTest
class OrderServiceTest {
    // Kiểm thử service
}

@SpringBootTest
class CustomerServiceTest {
    // Kiểm thử service khác
}
~~~

Nếu hai test class cùng dùng cấu hình ứng dụng, profile, property và các context customizer tương đương, Spring có thể tái sử dụng cùng ApplicationContext. Việc test class có tên khác nhau không tự động buộc Spring tạo context mới.

Tương tự, nhiều test method trong cùng một class thường dùng chung context của class đó. Mặc định, JUnit Jupiter tạo test instance mới cho mỗi test method, nhưng ApplicationContext do Spring quản lý được cache riêng và có thể được inject lại từ cùng context.

### 2.3. Khác biệt cấu hình tạo context riêng

Ví dụ hai test cùng dùng @SpringBootTest nhưng một test kích hoạt profile test, test còn lại kích hoạt profile integration:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTest {
}

@SpringBootTest
@ActiveProfiles("integration")
class OrderIntegrationTest {
}
~~~

Hai cấu hình profile khác nhau có thể tạo cache key khác nhau, vì vậy Spring nạp hai ApplicationContext riêng. Điều này là cần thiết nếu profile làm thay đổi bean hoặc property mà test sử dụng.

Tương tự, các khác biệt sau có thể dẫn đến context riêng:

- Danh sách class cấu hình khác nhau.
- locations XML khác nhau.
- @TestPropertySource có property hoặc resource khác nhau.
- Active profiles khác nhau.
- Initializer khác nhau.
- Context hierarchy khác nhau.
- Web resource path khác nhau.
- Bean override hoặc context customizer khác nhau.

Không nên cố ép các test dùng chung context nếu cấu hình của chúng thực sự khác nhau. Mục tiêu của cache là tái sử dụng context tương đương, không phải dùng một context bất kỳ cho mọi test.

## 3. Cache tồn tại trong phạm vi nào?

ApplicationContext cache là cache trong bộ nhớ gắn với tiến trình JVM. Nó thường được chia sẻ giữa các test class chạy trong cùng một JVM và cùng sử dụng Spring TestContext Framework.

Điều đó có một số hệ quả:

- Context không được lưu thành file để dùng lại ở lần chạy Gradle hoặc Maven tiếp theo.
- Context không tự chia sẻ giữa hai JVM độc lập.
- Nếu build tool chạy test trong nhiều fork hoặc worker process, mỗi tiến trình có cache riêng.
- Khi JVM kết thúc, cache trong tiến trình đó không còn tồn tại.
- Nếu một context bị loại khỏi cache hoặc bị đánh dấu dirty, Spring có thể phải tạo lại khi test sau cần cùng cấu hình.

Vì vậy, một suite chạy trong một JVM có thể tận dụng cache tốt hơn suite bị chia nhỏ thành nhiều tiến trình ngắn. Chạy song song bằng nhiều JVM có thể tăng throughput nhưng cũng làm mỗi tiến trình phải khởi tạo những context riêng của nó.

### 3.1. Cache không phải singleton toàn hệ thống

Context cache không phải một registry dùng chung giữa mọi ứng dụng Spring đang chạy trên máy. Nó thuộc tiến trình test và Spring TestContext Framework trong tiến trình đó.

Nếu một ứng dụng production đang chạy trong một JVM khác, test process không lấy ApplicationContext từ ứng dụng đó. Mỗi tiến trình có vòng đời container riêng.

### 3.2. Context được đóng khi nào?

Context có thể bị đóng khi:

- Cache loại context ra do giới hạn dung lượng và chính sách eviction.
- Test đánh dấu context dirty bằng @DirtiesContext.
- Cache hoặc tiến trình được kết thúc và shutdown hook của Spring Test đóng các context còn được quản lý.

Việc test method kết thúc không đồng nghĩa context phải đóng ngay. Đây chính là điểm tạo ra lợi ích tái sử dụng.

## 4. Giới hạn kích thước và chính sách eviction

Spring TestContext Framework giới hạn số context được giữ trong cache để tránh giữ quá nhiều tài nguyên. Mặc định, cache có kích thước tối đa **32 context**. Khi vượt giới hạn, cache sử dụng chính sách LRU (Least Recently Used): context ít được sử dụng gần đây nhất có thể bị loại trước.

Khi một context bị eviction, Spring đóng context đó để giải phóng bean và tài nguyên do context quản lý. Nếu một test sau đó cần lại cấu hình tương ứng, context phải được nạp lại.

Có thể thay đổi giới hạn bằng system property:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

Giá trị trên chỉ là ví dụ tăng giới hạn lên 64 context. Chỉ nên điều chỉnh khi đã quan sát cache statistics và hiểu mức tiêu thụ bộ nhớ, connection pool, thread hoặc tài nguyên khác. Tăng cache size quá cao có thể làm JVM giữ nhiều context nặng cùng lúc và gây áp lực bộ nhớ.

### 4.1. Vì sao LRU hợp lý?

Một suite có thể dùng một số cấu hình context thường xuyên và một số cấu hình hiếm gặp. Giữ context được sử dụng gần đây giúp những test tiếp theo có khả năng tái sử dụng cao hơn.

Ví dụ:

~~~text
Cache tối đa 3 context:

Lần lượt dùng A, B, C:
Cache = [A, B, C]

Test tiếp tục dùng A:
Cache vẫn có A, B, C; A trở thành context được dùng gần đây nhất.

Test cần D:
Context ít được dùng gần đây nhất bị loại.
Cache sau đó chứa các context còn lại và D.
~~~

Đây là mô tả khái niệm. Thứ tự cụ thể phụ thuộc lịch sử truy cập của cache trong suite.

### 4.2. Nhiều context không nhất thiết là lỗi

Một suite có nhiều context có thể là thiết kế hợp lý nếu nó kiểm tra các profile, database, security configuration hoặc web slice khác nhau. Vấn đề xuất hiện khi các context gần như giống nhau nhưng bị phân tách bởi những khác biệt cấu hình không cần thiết.

Ví dụ, khai báo property inline khác nhau ở nhiều test class chỉ vì mỗi test muốn một giá trị đơn giản có thể làm tăng số cache key. Hãy xem xét dùng fixture, property chung hoặc cấu hình test thống nhất nếu các khác biệt đó không đại diện cho môi trường thực sự khác nhau.

## 5. Những lợi ích của việc dùng lại ApplicationContext

### 5.1. Giảm thời gian chạy test suite

Chi phí tạo context chỉ phải trả khi cần một cache key chưa có trong cache hoặc khi context trước đó đã bị loại. Các test dùng cùng cấu hình có thể bắt đầu nhanh hơn vì không phải lặp lại quá trình khởi tạo.

Đối với một ứng dụng Spring Boot có nhiều auto-configuration, database pool, security và web infrastructure, thời gian tiết kiệm có thể đáng kể.

### 5.2. Giảm công việc khởi tạo bean

Bean singleton được tạo một lần trong context và được dùng lại khi test khác lấy cùng context. Các bước khởi tạo tốn kém như tạo client, đọc metadata hoặc thiết lập infrastructure không cần lặp lại cho từng test class.

### 5.3. Tạo nền tảng chung cho nhiều test

Các test class có thể cùng dùng một cấu hình ứng dụng chuẩn. Điều này giúp suite thể hiện nhất quán cách ứng dụng được lắp ráp và tránh mỗi class tự tạo một phiên bản cấu hình riêng.

### 5.4. Giữ đúng mô hình singleton của Spring

Trong ứng dụng thực tế, singleton bean thường tồn tại trong suốt vòng đời ApplicationContext. Dùng chung context giúp test có thể quan sát mô hình đó, bao gồm việc các bean được quản lý và liên kết trong cùng một container.

Tuy nhiên, việc dùng chung cũng yêu cầu bean phải an toàn với trạng thái và thứ tự test. Cache không tự làm singleton bean trở nên stateless hoặc thread-safe.

## 6. Hệ quả: test dùng chung bean và trạng thái

Khi nhiều test dùng cùng context, singleton bean trong context cũng được chia sẻ. Nếu một test sửa trạng thái mutable của singleton và không khôi phục, test khác có thể nhận trạng thái đã bị thay đổi.

Ví dụ bean không an toàn:

~~~java
@Component
class SearchCounter {
    private int count;

    void increment() {
        count++;
    }

    int count() {
        return count;
    }

    void reset() {
        count = 0;
    }
}
~~~

Nếu test A gọi increment và test B kỳ vọng count bằng 0, kết quả của test B phụ thuộc vào thứ tự chạy nếu không có bước reset hoặc context mới.

Cache không phải nguyên nhân làm test sai. Vấn đề là test đã thay đổi trạng thái dùng chung mà không có chiến lược cô lập.

### 6.1. Phân biệt test instance và Spring bean

JUnit Jupiter mặc định tạo một test class instance mới cho mỗi test method. Nhưng điều đó không có nghĩa ApplicationContext và các singleton bean cũng được tạo mới theo từng method.

Ví dụ:

~~~java
@SpringBootTest
class SharedContextTest {

    @Autowired
    SearchCounter searchCounter;

    @Test
    void first_test() {
        searchCounter.increment();
    }

    @Test
    void second_test() {
        // Có thể thấy trạng thái đã thay đổi nếu test trước không reset.
    }
}
~~~

Hai test method có thể có hai test instance khác nhau nhưng cùng nhận một SearchCounter singleton từ cùng ApplicationContext.

### 6.2. Trạng thái database không tự được cache hoặc rollback

ApplicationContext cache chỉ quản lý context và các bean do context quản lý. Nó không tự động xóa dữ liệu trong database sau mỗi test.

Database state cần chiến lược riêng:

- Dùng transaction test và rollback khi phù hợp.
- Tạo dữ liệu riêng cho từng test.
- Dùng cleanup rõ ràng.
- Dùng schema/database riêng cho nhóm test khi cần.
- Dùng Testcontainers hoặc database test có vòng đời phù hợp.

Một test dùng cùng ApplicationContext nhưng thay đổi database có thể ảnh hưởng test tiếp theo nếu không cô lập dữ liệu.

### 6.3. Trạng thái bên ngoài cũng cần được quản lý

Các tác động như gửi message, ghi file, gọi API ngoài, tạo dữ liệu trong hệ thống khác hoặc thay đổi cache phân tán không tự động được hoàn tác chỉ vì test method kết thúc.

Hãy dùng test double, namespace dữ liệu riêng, container có vòng đời kiểm soát hoặc cleanup phù hợp với từng phụ thuộc. Đừng nhầm việc Spring tái sử dụng ApplicationContext với việc mọi trạng thái ứng dụng đều được khôi phục.

### 6.4. Test chạy song song

Khi bật parallel execution, nhiều test có thể truy cập cùng bean singleton trong cùng context cùng lúc. Nếu bean chứa mutable state hoặc collaborator không thread-safe, test có thể gây race condition.

Để kiểm thử song song an toàn:

- Ưu tiên singleton bean stateless.
- Không lưu dữ liệu riêng của test trong field mutable của singleton.
- Mỗi test dùng dữ liệu định danh riêng.
- Đồng bộ hoặc cô lập tài nguyên dùng chung khi nghiệp vụ thực sự cần.
- Không dựa vào thứ tự test.

Không nên tắt parallel execution chỉ để che giấu một thiết kế test phụ thuộc trạng thái dùng chung. Trước tiên hãy xác định state nào đang bị chia sẻ và cách cô lập phù hợp.

## 7. @DirtiesContext: khi nào cần loại context khỏi cache?

@DirtiesContext đánh dấu ApplicationContext đã bị thay đổi đến mức không nên tái sử dụng cho các test tiếp theo. Spring TestContext Framework sẽ loại context khỏi cache và đóng nó theo lifecycle tương ứng. Khi một test khác cần cấu hình đó, Spring sẽ tạo context mới.

Ví dụ:

~~~java
@SpringBootTest
@DirtiesContext
class ChangesApplicationContextTest {
    // Test thay đổi trạng thái cấu hình/context không thể khôi phục.
}
~~~

Có thể dùng @DirtiesContext ở cấp method hoặc class, với các mode quy định thời điểm đánh dấu dirty, chẳng hạn trước hoặc sau method/class. Mặc định thường là sau phạm vi được đánh dấu.

### 7.1. Khi nào @DirtiesContext phù hợp?

Chỉ nên dùng khi test thực sự làm thay đổi ApplicationContext theo cách không thể khôi phục an toàn, ví dụ:

- Thay đổi bean definition hoặc cấu trúc context trong lúc test.
- Thay đổi trạng thái singleton dùng chung mà không có cách reset phù hợp và việc thay đổi đó là mục tiêu test.
- Kiểm thử một thành phần có hành vi làm hỏng context hoặc thay đổi trạng thái quản lý của container.
- Một số trường hợp test tích hợp legacy có cấu hình context không thể cô lập bằng fixture.

Nếu chỉ thay đổi dữ liệu database, file, message hoặc trạng thái mock, thường có cách reset hoặc cleanup trực tiếp phù hợp hơn.

### 7.2. Các mode thường gặp

| Mode | Ý nghĩa khái quát |
| --- | --- |
| BEFORE_METHOD | Đóng context trước test method được chạy |
| AFTER_METHOD | Đóng context sau test method |
| BEFORE_CLASS | Đóng context trước các test method của class |
| AFTER_CLASS | Đóng context sau các test method của class |
| BEFORE_EACH_TEST_METHOD | Mode cấp class, loại context trước mỗi test method |
| AFTER_EACH_TEST_METHOD | Mode cấp class, loại context sau mỗi test method |

Tên mode và phạm vi áp dụng phụ thuộc annotation attribute tương ứng trong phiên bản Spring. Hãy xem Javadoc của @DirtiesContext đang dùng khi cấu hình một lifecycle cụ thể.

### 7.3. @DirtiesContext không phải lệnh dọn mọi dữ liệu

Loại context khỏi cache sẽ đóng bean và tài nguyên mà context quản lý. Điều đó không bảo đảm xóa dữ liệu trong một database bên ngoài vẫn đang chạy, xóa message trong broker dùng chung hoặc hoàn tác request đã gửi đến hệ thống khác.

Nếu test ghi vào database dùng chung, hãy dùng transaction, schema riêng hoặc cleanup. Nếu test gửi message, hãy dùng topic/queue riêng hoặc xóa message theo cơ chế của môi trường test. @DirtiesContext không thay thế những chiến lược này.

### 7.4. Lạm dụng @DirtiesContext làm suite chậm

Mỗi lần context bị đánh dấu dirty, lợi ích cache cho context đó mất đi. Test tiếp theo có thể phải khởi động lại context, tạo lại pool, bean và infrastructure.

Nếu nhiều test class đều dùng @DirtiesContext, suite có thể gần như tạo context liên tục. Hãy kiểm tra xem có thể:

- Reset trạng thái bean qua API test rõ ràng.
- Tạo mới fake hoặc mock cho mỗi test.
- Dùng transaction rollback cho dữ liệu persistence.
- Dùng fixture riêng thay vì sửa singleton.
- Tách test thay đổi context thành một nhóm riêng.

Chỉ giữ @DirtiesContext khi context thực sự không còn an toàn để tái sử dụng.

## 8. Context cache và @DynamicPropertySource

Testcontainers và các dịch vụ giả lập thường cung cấp port hoặc URL động. @DynamicPropertySource cho phép đăng ký property vào Environment của test context:

~~~java
@SpringBootTest
class DatabaseIntegrationTest {

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
~~~

Các method @DynamicPropertySource được phản ánh thông qua context customizer trong cấu hình cache. Khi test dùng cùng cấu hình tương ứng, Spring có thể tái sử dụng context.

Điều này cần chú ý nếu resource cung cấp property có vòng đời ngắn:

- Context đã được tạo với URL hoặc port của container hiện tại.
- Container bị dừng rồi khởi động lại với port khác.
- Test tiếp theo lấy context cũ từ cache.
- Bean trong context vẫn giữ cấu hình đã được dùng khi context khởi tạo.

Giá trị dynamic property không nên được hiểu là tự động đọc lại và tái cấu hình mọi bean mỗi lần cache hit. Property thường được tiêu thụ khi bean hoặc infrastructure được tạo. Nếu resource thay đổi vòng đời, hãy bảo đảm resource tồn tại ổn định trong suốt thời gian context được tái sử dụng, hoặc đánh dấu context dirty khi cần.

Một cách phổ biến là chia sẻ container theo vòng đời phù hợp với nhóm test dùng cùng context. Nếu mỗi class tự khởi động và dừng một container nhưng context lại được cache giữa các class, có thể xuất hiện kết nối đến endpoint đã hết hiệu lực.

## 9. Cách nhận biết cache đang hoạt động

Spring TestContext Framework có thể ghi log thống kê cache. Bật log DEBUG cho logger:

~~~text
org.springframework.test.context.cache
~~~

Ví dụ cấu hình logging trong test:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Log cache có thể cung cấp thông tin về:

- Số lần lấy context từ cache (hit).
- Số lần phải tải context mới (miss).
- Số context đang được giữ.
- Số lần context bị eviction hoặc các thống kê liên quan tùy phiên bản.

Nếu suite tạo rất nhiều context, thống kê giúp tìm nguyên nhân. Hãy xem cache hit/miss cùng cấu hình của các test class để xác định khác biệt nào đang tạo cache key mới.

### 9.1. Dấu hiệu cache hit thấp

Một số nguyên nhân thường gặp:

- Nhiều test class khai báo classes hoặc locations khác nhau dù cấu hình gần như giống nhau.
- Active profiles không thống nhất.
- Property inline khác nhau không cần thiết.
- Các @TestConfiguration hoặc @Import khác nhau.
- Danh sách bean override khác nhau.
- Các context customizer khác nhau.
- Web resource path hoặc context hierarchy khác nhau.
- Suite chia test sang nhiều JVM process.

Không phải mọi miss đều cần sửa. Nếu test thực sự cần cấu hình khác, miss là điều bình thường.

### 9.2. Dùng thống kê để điều tra, không để chạy đua theo hit rate

Hit rate cao không tự chứng minh test suite tốt. Nếu ép các test dùng chung một context dù chúng cần cấu hình khác nhau, test có thể không còn đại diện cho môi trường cần kiểm tra.

Mục tiêu là tránh tạo context trùng lặp không cần thiết, đồng thời giữ mỗi test chạy trong cấu hình đúng. Hãy tối ưu dựa trên thời gian, số context, bộ nhớ và độ ổn định của test.

## 10. Cách tổ chức test để tận dụng cache

### 10.1. Tái sử dụng cấu hình chung

Nếu nhiều test class cần cùng cấu hình, có thể dùng chung một class cấu hình hoặc một lớp cấu hình nền phù hợp. Hãy tránh tạo các configuration class chỉ khác tên nhưng khai báo bean giống hệt nhau nếu chúng không đại diện cho môi trường khác.

Ví dụ:

~~~java
@SpringBootTest
@ActiveProfiles("test")
abstract class BaseApplicationTest {
}

class OrderServiceTest extends BaseApplicationTest {
}

class CustomerServiceTest extends BaseApplicationTest {
}
~~~

Các class con có thể dùng chung context nếu không thêm cấu hình làm thay đổi cache key. Tuy nhiên, không nên tạo base class chỉ để ép mọi test vào cùng một cấu hình. Base test nên chứa những thiết lập thực sự chung và dễ hiểu.

### 10.2. Nhóm test theo slice và mục tiêu

Một @WebMvcTest, @DataJpaTest và @SpringBootTest thường cần các context khác nhau vì phạm vi bean khác nhau. Điều đó là bình thường.

Hãy nhóm test theo mục tiêu:

- Web contract test dùng cùng một MVC slice nếu cấu hình tương đương.
- Repository test dùng cùng một data slice và database configuration.
- Integration test dùng application context đầy đủ cho những luồng cần phối hợp nhiều bean.
- Unit test thuần không tạo context nếu không cần Spring.

Không chuyển mọi test thành @SpringBootTest chỉ để dùng một context chung. Context lớn có thể làm test chậm hơn và khiến lỗi khó khoanh vùng.

### 10.3. Tránh thay property tùy tiện giữa các class

Nếu mỗi test chỉ cần một dữ liệu đầu vào khác nhau, hãy truyền dữ liệu vào test method hoặc fixture thay vì thay application property. Property nên đại diện cho cấu hình môi trường, không phải một cách truyền dữ liệu test tùy tiện.

Nếu thật sự cần kiểm tra hai cấu hình ứng dụng khác nhau, hãy giữ hai context riêng và ghi rõ mục tiêu của chúng.

### 10.4. Dùng @DirtiesContext đúng mức

Trước khi thêm @DirtiesContext, hãy hỏi:

- Test có thay đổi ApplicationContext hay chỉ thay đổi dữ liệu?
- Bean có API reset an toàn không?
- Có thể dùng fake/mock mới theo từng test không?
- Database có thể rollback hoặc cleanup không?
- Tài nguyên ngoài có thể được tạo riêng và đóng đúng vòng đời không?

Nếu vấn đề chỉ là dữ liệu, không nên đóng toàn bộ context để giải quyết.

## 11. Cache và các loại trạng thái khác nhau

Để tránh nhầm lẫn, hãy phân biệt những thứ sau:

| Loại trạng thái | Được ApplicationContext cache quản lý? | Cách cô lập thường dùng |
| --- | --- | --- |
| Bean definition và singleton bean | Có, trong context được cache | Thiết kế bean stateless hoặc reset state có kiểm soát |
| Test instance JUnit | Không | JUnit test lifecycle |
| Dữ liệu database | Không trực tiếp | Transaction, fixture, cleanup, schema riêng |
| Mockito mock trong context | Mock bean thuộc context được dùng lại; việc reset phụ thuộc integration/lifecycle cấu hình | Reset mock hoặc dùng cấu hình mock phù hợp |
| Message trong broker | Không | Queue/topic riêng, purge hoặc broker container |
| File trên filesystem | Không | Temporary directory và cleanup |
| Cache phân tán bên ngoài | Không | Namespace riêng, reset hoặc container |
| Container Testcontainers | Không trực tiếp | Quản lý vòng đời container tương thích với context |
| Static field trong JVM | Không thuộc context cache | Tránh state dùng chung hoặc reset tường minh |

ApplicationContext có thể giữ reference tới connection pool, client hoặc adapter. Khi context bị đóng, các bean được quản lý có thể giải phóng tài nguyên theo lifecycle. Nhưng dữ liệu mà các tài nguyên đó đã ghi vào hệ thống ngoài không tự động biến mất.

## 12. Những hiểu lầm thường gặp

### Mỗi test method có một ApplicationContext riêng

Không đúng trong trường hợp thông thường. JUnit có thể tạo test instance mới theo method, nhưng Spring TestContext cache context dựa trên cấu hình. Nhiều method và nhiều class có thể dùng cùng context.

### Mỗi test class luôn tạo một context

Không đúng. Nếu cache key tương đương và context còn trong cache, class khác có thể dùng lại context đã tạo.

### Hai class cùng @SpringBootTest chắc chắn dùng chung context

Không chắc chắn. Profile, property, configuration class, context customizer, bean override và các thành phần khác có thể làm cache key khác nhau.

### Context cache được lưu giữa các lần chạy build

Không. Đây là cache trong bộ nhớ của một JVM test process. Khi tiến trình kết thúc, cache không được giữ để lần chạy sau sử dụng.

### Dùng @DirtiesContext sẽ xóa database

Không. Annotation này loại context khỏi cache và đóng context. Database bên ngoài cần chiến lược cleanup riêng.

### @Transactional luôn hoàn tác mọi thay đổi của test

Không. Transaction chỉ bao trùm những thao tác tham gia vào transaction đó. HTTP request chạy trên server thread, message bất đồng bộ và side effect bên ngoài có thể nằm ngoài transaction của test.

### Cache hit cao đồng nghĩa test chạy đúng

Không. Cache hit chỉ cho biết context đã được tái sử dụng. Nó không chứng minh test độc lập, dữ liệu được dọn đúng hoặc bean singleton không rò rỉ state.

### Đóng context là cách reset an toàn cho mọi thứ

Không. Đóng context giải phóng tài nguyên của bean, nhưng không hoàn tác side effect đã xảy ra ở hệ thống bên ngoài.

## 13. Ví dụ minh họa nhiều test class dùng chung context

Giả sử ứng dụng có cấu hình:

~~~java
@SpringBootApplication
class SampleApplication {
}
~~~

Hai test class:

~~~java
@SpringBootTest(classes = SampleApplication.class)
@ActiveProfiles("test")
class ProductServiceTest {

    @Autowired
    ProductService productService;

    @Test
    void finds_product() {
        // Chuẩn bị dữ liệu riêng rồi kiểm tra hành vi.
    }
}

@SpringBootTest(classes = SampleApplication.class)
@ActiveProfiles("test")
class CategoryServiceTest {

    @Autowired
    CategoryService categoryService;

    @Test
    void finds_category() {
        // Chuẩn bị dữ liệu riêng rồi kiểm tra hành vi.
    }
}
~~~

Nếu hai test class có cấu hình context đã hợp nhất tương đương, Spring có thể tái sử dụng ApplicationContext. ProductService và CategoryService là các bean trong cùng context đó.

Điều này không có nghĩa test phải dùng chung dữ liệu nghiệp vụ. ProductServiceTest vẫn cần tự chuẩn bị sản phẩm của nó, CategoryServiceTest tự chuẩn bị category của nó, và cả hai phải dọn dữ liệu hoặc dùng transaction phù hợp.

Nếu một class thêm @TestPropertySource với property khác, hoặc thêm bean override khác, context có thể trở thành cache entry riêng. Đây là hệ quả của việc cấu hình đã thay đổi.

## 14. Quy trình điều tra khi suite khởi động context quá nhiều lần

Khi thấy test suite chậm do khởi động Spring nhiều lần, có thể làm theo trình tự:

**Bước 1 – Bật thống kê cache.** Bật DEBUG cho org.springframework.test.context.cache và ghi nhận hit, miss cùng số context đang giữ.

**Bước 2 – Nhóm các test class theo cấu hình.** So sánh classes, locations, profiles, properties, initializers, context customizers và resource path.

**Bước 3 – Xác định khác biệt có chủ đích.** Phân biệt context riêng cần thiết với khác biệt phát sinh do khai báo cấu hình trùng lặp hoặc không thống nhất.

**Bước 4 – Kiểm tra @DirtiesContext.** Tìm test đang loại context khỏi cache và xác định có thể reset state hoặc cleanup trực tiếp hay không.

**Bước 5 – Kiểm tra fork/process.** Xác định build tool có chạy test qua nhiều JVM hay không. Mỗi JVM có cache riêng.

**Bước 6 – Xem kích thước cache.** Nếu số context hợp lệ vượt giới hạn mặc định, cân nhắc điều chỉnh maxSize sau khi đánh giá bộ nhớ và tài nguyên.

**Bước 7 – Chạy lại suite và so sánh.** Đo thời gian tổng thể, số lần tạo context, bộ nhớ và độ ổn định; không chỉ nhìn một chỉ số hit rate.

## 15. Nguyên tắc sử dụng cache an toàn

- Coi singleton bean trong context được cache là trạng thái dùng chung giữa các test tương ứng.
- Ưu tiên bean stateless hoặc có API reset rõ ràng cho trạng thái test.
- Mỗi test tự chuẩn bị dữ liệu cần thiết.
- Không phụ thuộc thứ tự chạy hoặc trạng thái do test trước để lại.
- Phân biệt ApplicationContext lifecycle với database, broker, filesystem và service lifecycle.
- Dùng @DirtiesContext khi context thực sự không thể tái sử dụng an toàn.
- Giữ cấu hình test nhất quán khi các test cần cùng môi trường.
- Chấp nhận context riêng khi profile, property hoặc bean configuration thực sự khác nhau.
- Theo dõi cache statistics trước khi tăng giới hạn cache.
- Bảo đảm tài nguyên động như Testcontainers tồn tại tương thích với thời gian context được cache.

## Kết luận

TestContext giữ lại ApplicationContext để dùng chung vì việc khởi tạo một Spring container có thể tốn nhiều công việc và tài nguyên. Cache cho phép các test có cùng cấu hình tái sử dụng context trong cùng JVM, giảm số lần quét cấu hình, tạo bean và thiết lập infrastructure. Cache key được hình thành từ cấu hình context đã hợp nhất, nên các khác biệt về class cấu hình, profile, property, initializer, customizer hoặc web resource có thể tạo context riêng.

Tái sử dụng context cũng có nghĩa singleton bean được chia sẻ giữa các test dùng cùng cache entry. Vì vậy, test phải quản lý trạng thái bean, dữ liệu database và side effect bên ngoài bằng những cơ chế cô lập phù hợp. @DirtiesContext chỉ nên dùng khi context thực sự không thể tái sử dụng; dùng quá thường xuyên sẽ làm mất lợi ích cache. Khi hiểu đúng phạm vi JVM, cache key, eviction và lifecycle, ta có thể tổ chức Spring test suite nhanh hơn mà vẫn giữ được tính độc lập và độ tin cậy.
