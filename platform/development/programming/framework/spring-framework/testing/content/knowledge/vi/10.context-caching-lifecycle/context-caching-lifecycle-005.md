# Giới hạn kích thước cache và loại bỏ context ít dùng

Spring TestContext Framework lưu cache các ApplicationContext đã được tạo để nhiều test có cấu hình tương đương có thể dùng lại cùng context. Việc khởi tạo context thường tốn thời gian vì Spring phải đọc cấu hình, tạo bean, inject phụ thuộc và có thể mở kết nối đến database hoặc dịch vụ hạ tầng. Cache giúp giảm chi phí đó trong một test suite.

Cache không giữ mọi context vô hạn. Spring đặt giới hạn kích thước và dùng chính sách loại bỏ phần tử ít được sử dụng gần đây nhất (Least Recently Used, LRU) khi cache vượt giới hạn. Cơ chế này giữ bộ nhớ ở mức có thể kiểm soát, đồng thời ưu tiên những context vừa được dùng vì chúng có khả năng được yêu cầu lại sớm.

## 1. Vì sao Spring cần cache ApplicationContext?

Trong một ứng dụng Spring, việc tạo ApplicationContext có thể bao gồm nhiều công việc:

- Đọc và xử lý cấu hình Java, XML hoặc cấu hình component scan.
- Tạo bean và giải quyết các phụ thuộc giữa chúng.
- Chạy các bean post-processor và callback khởi tạo.
- Tạo connection pool, cấu hình ORM hoặc khởi tạo thành phần tích hợp.
- Chuẩn bị web infrastructure, message broker client hoặc các thành phần hạ tầng khác nếu cấu hình yêu cầu.

Nếu mỗi test class đều tạo lại một context giống hệt, phần thời gian khởi tạo sẽ bị lặp lại. Spring TestContext Framework giải quyết việc này bằng cách lưu context đã tải vào cache dùng chung trong tiến trình kiểm thử.

Ví dụ, hai test class sử dụng cùng cấu hình:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {
    @Autowired
    private InventoryService inventoryService;

    @Test
    void findsAnItem() {
        inventoryService.find("SKU-01");
    }
}

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryRepositoryTest {
    @Autowired
    private InventoryRepository inventoryRepository;

    @Test
    void loadsRepository() {
        inventoryRepository.findBySku("SKU-01");
    }
}
~~~

Nếu metadata cấu hình của hai test class tương đương, Spring có thể dùng lại cùng ApplicationContext. Test instance của mỗi class vẫn do JUnit tạo theo lifecycle của nó; cache chỉ giữ context và các bean thuộc context đó.

Cache giúp tiết kiệm thời gian nhưng cũng có nghĩa singleton bean có thể tồn tại qua nhiều test class. Vì vậy, bean dùng chung cần quản lý trạng thái cẩn thận để kết quả test không phụ thuộc thứ tự chạy.

## 2. Context cache lưu những gì?

Spring không dùng tên test class đơn thuần làm khóa cache. Nó xây dựng khóa từ metadata mô tả cách tạo context, thường được thể hiện qua MergedContextConfiguration. Các thông tin quan trọng có thể bao gồm:

| Thành phần cấu hình | Ảnh hưởng đến khóa cache |
|---|---|
| Resource locations | Các file XML hoặc resource cấu hình context |
| Configuration classes | Những lớp @Configuration hoặc lớp cấu hình được khai báo |
| Context initializer classes | Các initializer được dùng trước khi context refresh |
| Context customizers | Các tùy chỉnh context, bao gồm nhiều cơ chế test bean override và dynamic property |
| Context loader | Loader chịu trách nhiệm tạo context |
| Parent configuration | Cấu hình context cha trong hierarchy |
| Active profiles | Các profile Spring được bật |
| Test property sources | Descriptor và giá trị property được khai báo cho test |
| Web resource base path | Đường dẫn gốc của web application khi dùng web context |

Nếu hai test class có cùng các thành phần cấu hình tương ứng, chúng có thể dùng chung một cache entry. Nếu một thuộc tính trong khóa khác nhau, Spring có thể xem đó là một cấu hình context khác và tải context riêng.

Ví dụ, các test cùng dùng InventoryTestConfig và cùng active profile có thể chia sẻ context. Nhưng nếu một test thêm @ActiveProfiles("integration"), một test khác dùng @TestPropertySource với giá trị riêng, hoặc mỗi test khai báo một tập bean override khác nhau, khóa có thể khác và cache cần thêm entry mới.

Điều này giải thích vì sao một dự án có nhiều test class nhưng vẫn có thể dùng ít context, hoặc ngược lại có nhiều context dù số test class không quá lớn. Số lượng test class không phải số lượng cache entry; số lượng cấu hình context phân biệt mới là yếu tố quyết định.

## 3. Giới hạn kích thước cache mặc định

Spring TestContext Framework đặt giới hạn mặc định là 32 ApplicationContext. Giá trị này là giới hạn số context được giữ trong cache tại một thời điểm, không phải số lượng test class, số bean hay số test method.

Thuộc tính điều khiển giới hạn là:

~~~text
spring.test.context.cache.maxSize
~~~

Có thể thay đổi bằng system property của JVM hoặc cơ chế SpringProperties. Ví dụ đặt giới hạn thành 64:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

Giá trị cần được thiết lập trước khi TestContext Framework khởi tạo cache. Thay đổi system property giữa lúc test suite đang chạy không phải cách đáng tin cậy để điều chỉnh cache đã được tạo.

### Cấu hình với Gradle

Với Gradle Groovy DSL, truyền system property vào tiến trình test:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty "spring.test.context.cache.maxSize", "64"
}
~~~

Với Gradle Kotlin DSL:

~~~kotlin
tasks.withType<Test>().configureEach {
    systemProperty("spring.test.context.cache.maxSize", "64")
}
~~~

Điểm cần chú ý là property phải được truyền vào JVM chạy test. Đặt property trong Gradle daemon nhưng không chuyển nó sang test worker có thể khiến test process vẫn dùng giá trị mặc định.

### Cấu hình với Maven Surefire

Có thể đặt system property trong cấu hình Maven Surefire:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <spring.test.context.cache.maxSize>64</spring.test.context.cache.maxSize>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Nếu dự án dùng Maven Failsafe cho integration test, hãy cấu hình property trong đúng plugin đang chạy các test đó. Surefire và Failsafe có thể chạy ở những giai đoạn hoặc tiến trình khác nhau, nên cần bảo đảm cả nhóm test cần dùng cache đều nhận cùng cấu hình mong muốn.

Không có một giá trị tối ưu cho mọi dự án. Giữ mặc định 32 là điểm khởi đầu hợp lý. Chỉ tăng hoặc giảm sau khi quan sát số lượng context, tỷ lệ cache hit, thời gian tải lại và mức sử dụng bộ nhớ của tiến trình test.

## 4. Chính sách LRU hoạt động như thế nào?

LRU là viết tắt của Least Recently Used, nghĩa là phần tử có lần sử dụng gần nhất xa nhất sẽ được chọn loại bỏ trước. Khi cache đầy và một context mới cần được thêm vào, Spring loại bỏ cache entry ít được truy cập gần đây nhất để giữ kích thước không vượt giới hạn.

Giả sử cache có maxSize bằng 3 và đang giữ ba context A, B, C. Trình tự sử dụng như sau:

1. Test dùng A, sau đó B, rồi C.
2. Một test khác dùng lại A, khiến A trở thành context vừa được truy cập gần nhất.
3. Test tiếp theo yêu cầu context D.
4. Cache đã đầy nên Spring loại bỏ B vì B là context ít được sử dụng gần đây nhất.
5. Cache giữ A, C và D.

Trạng thái có thể hình dung như sau:

| Thao tác | Các context trong cache theo thứ tự ít dùng gần đây đến vừa dùng | Kết quả |
|---|---|---|
| Tải A, B, C | A, B, C | Cache đầy |
| Truy cập A | B, C, A | A được đánh dấu vừa dùng |
| Tải D | C, A, D | B bị loại bỏ |
| Truy cập B | A, D, B | B phải được tải lại; context ít dùng gần đây tiếp theo bị loại bỏ nếu cần chỗ |

Thứ tự trong bảng mô tả ý tưởng LRU. Việc truy cập cache entry cập nhật mức độ gần đây của entry đó. Một context được tạo từ lâu nhưng vẫn được dùng thường xuyên có thể tiếp tục nằm trong cache; tuổi đời tạo context không phải tiêu chí duy nhất.

### Điều gì xảy ra với context bị loại bỏ?

Khi một entry bị loại khỏi cache, Spring đóng ApplicationContext tương ứng theo cơ chế quản lý vòng đời. Các bean có callback hủy hoặc tài nguyên được quản lý đúng cách có thể được giải phóng, chẳng hạn connection pool hoặc thành phần thực hiện DisposableBean.

Nếu một test sau đó cần lại cùng cấu hình đã bị loại bỏ, Spring phải tạo context mới. Test vẫn có thể chạy bình thường; chi phí chỉ tăng vì việc khởi tạo được thực hiện lại.

LRU eviction không có nghĩa test bị đánh dấu thất bại hoặc context bị hỏng. Đây là cơ chế quản lý dung lượng cache. Nó chỉ ảnh hưởng đến hiệu năng và số lần khởi tạo context.

## 5. Phân biệt LRU eviction với @DirtiesContext

Hai cơ chế đều có thể khiến một context không còn nằm trong cache, nhưng lý do khác nhau:

| Cơ chế | Vì sao context bị loại bỏ? | Khi nào xảy ra? |
|---|---|---|
| LRU eviction | Cache cần giải phóng chỗ vì số context vượt maxSize | Tự động khi cache vượt giới hạn |
| @DirtiesContext | Test tuyên bố context đã bị thay đổi và không còn phù hợp để tái sử dụng | Ở chế độ BEFORE hoặc AFTER đã khai báo |

LRU eviction dựa trên mức độ sử dụng gần đây. @DirtiesContext là yêu cầu loại bỏ tường minh gắn với test class hoặc method.

Ví dụ dùng @DirtiesContext sau một test method:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class ContextStateMutationTest {
    @Test
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void changesContextState() {
        // Test thay đổi trạng thái context theo cách không thể reset an toàn.
    }
}
~~~

Khi method hoàn tất, Spring loại context khỏi cache theo chế độ đã khai báo. Việc này có thể xảy ra ngay cả khi cache còn nhiều chỗ. Ngược lại, một context có thể bị LRU eviction dù test không đánh dấu @DirtiesContext, chỉ vì cache cần chỗ cho cấu hình khác.

Không nên dùng @DirtiesContext chỉ để xử lý dữ liệu database còn sót lại. Nếu dữ liệu nằm trong transaction, hãy cân nhắc rollback. Nếu dữ liệu được tạo bởi SQL script, hãy dùng script cleanup. Nếu trạng thái nằm trong fake hoặc bean có thể reset, hãy cung cấp phương thức reset rõ ràng. Tạo lại context có chi phí cao hơn việc dọn đúng trạng thái cần dọn.

## 6. Context hierarchy và việc loại bỏ context

Một số ứng dụng kiểm thử dùng context hierarchy, trong đó context con kế thừa bean hoặc cấu hình từ context cha. Ví dụ, web integration test có thể dùng một parent context chứa service và repository, còn child context chứa web-specific bean.

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfig.class),
    @ContextConfiguration(classes = WebTestConfig.class)
})
class WebApplicationContextTest {
    // Test dùng context hierarchy gồm parent và child.
}
~~~

Cache có thể giữ các context trong hierarchy và theo dõi quan hệ cha-con. Việc loại bỏ context trong hierarchy cần tôn trọng quan hệ này để không tái sử dụng một child context dựa trên parent đã bị đóng hoặc bị loại khỏi cache.

Khi dùng @DirtiesContext với hierarchy, thuộc tính hierarchyMode cho phép xác định phạm vi loại bỏ theo các mức của hierarchy. Chế độ mặc định EXHAUSTIVE có thể loại cả những context con liên quan; CURRENT_LEVEL giới hạn việc loại bỏ ở cấp hiện tại theo quy tắc của TestContext Framework.

Với LRU eviction, không nên giả định rằng các context cha và con sẽ tồn tại độc lập mãi mãi. Hãy để Spring quản lý quan hệ trong cache và tránh giữ tham chiếu thủ công đến ApplicationContext đã bị loại bỏ. Nếu test dùng hierarchy và gặp việc tải lại context nhiều lần, cần quan sát log cache cùng cấu hình parent/child để hiểu entry nào đang được tạo hoặc loại bỏ.

## 7. Những yếu tố làm tăng số lượng context cache

Một test suite có thể vô tình tạo nhiều context khác nhau khi các lớp test khai báo cấu hình hơi khác nhau. Một số nguồn phổ biến:

### Khác active profile

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
@ActiveProfiles("test")
class InventoryServiceTest {
}

@SpringJUnitConfig(InventoryTestConfig.class)
@ActiveProfiles("integration")
class InventoryRepositoryIntegrationTest {
}
~~~

Hai test class có active profile khác nhau cần cấu hình context khác nhau. Spring không thể dùng chung một cache entry nếu profile là một phần khác biệt của khóa.

### Khác test property source

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
@TestPropertySource(properties = "inventory.mode=fast")
class FastInventoryTest {
}

@SpringJUnitConfig(InventoryTestConfig.class)
@TestPropertySource(properties = "inventory.mode=accurate")
class AccurateInventoryTest {
}
~~~

Hai tập property khác nhau có thể tạo hai context. Nếu một giá trị chỉ khác để đáp ứng một test đơn lẻ, hãy cân nhắc liệu có thể kiểm tra giá trị đó bằng constructor hoặc cấu hình fixture ở phạm vi nhỏ hơn không.

### Khác bean override hoặc context customizer

Các annotation thay thế bean như @MockitoBean hoặc những cơ chế mock bean tương ứng có thể góp phần tạo context customizer. Hai test class khai báo tập mock bean khác nhau có thể dẫn đến khóa context khác nhau.

Ví dụ, một test thay InventoryRepository bằng mock, test khác thay PaymentGateway bằng mock. Dù cùng dùng một lớp cấu hình gốc, tập bean override khác nhau có thể khiến Spring cần hai context.

### Khác cấu hình web hoặc context hierarchy

Web resource base path, parent context, initializer hoặc context loader khác nhau cũng có thể làm cache key khác nhau. Khi nhiều module hoặc nhiều nhóm test sử dụng cấu hình riêng, số context có thể tăng nhanh.

## 8. Cách giảm context cache fragmentation

Context fragmentation xảy ra khi nhiều test class tạo ra nhiều cache key gần giống nhau nhưng không trùng khớp. Điều này làm cache nhanh đầy và tăng số lần tải lại context.

Một số cách tổ chức có thể giúp:

- Dùng chung các lớp cấu hình test khi các test thực sự cần cùng môi trường.
- Chuẩn hóa active profile và các test property dùng chung.
- Tập trung các cấu hình bean override được chia sẻ khi phù hợp với cùng một nhóm test.
- Tránh khai báo các property ngẫu nhiên hoặc duy nhất cho từng test class nếu không cần một context khác.
- Không dùng @DirtiesContext như thao tác dọn dẹp mặc định.
- Tách unit test thuần Java khỏi các test cần Spring context, giảm số test phải tạo context.
- Dùng slice test cho các nhóm chức năng như MVC hoặc JPA khi chỉ cần kiểm tra một phần cấu hình.

Ví dụ, nếu nhiều test class cần cùng profile và cấu hình repository, có thể tạo một cấu hình test dùng chung:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ActiveProfiles;

@Configuration
class SharedInventoryTestConfig {
    @Bean
    InventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }
}

@SpringJUnitConfig(SharedInventoryTestConfig.class)
@ActiveProfiles("test")
class SharedInventoryServiceTest {
    // Các test dùng chung profile và cấu hình này có thể chia sẻ context.
}
~~~

Sau đó, các test class cùng sử dụng cấu hình này khi chúng thực sự cần cùng một context. Không nên gom các test có nhu cầu hạ tầng khác nhau vào một context chỉ để giảm số cache key; cấu hình phải phản ánh đúng môi trường mà test cần xác nhận.

## 9. Quan sát cache hit, miss và eviction

Khi test suite chậm, cần biết Spring có tái sử dụng context hay liên tục tạo mới. TestContext Framework ghi log thống kê cache qua logger category:

~~~text
org.springframework.test.context.cache
~~~

Đặt mức log DEBUG để quan sát kích thước cache, maxSize, số lần hit, miss và thông tin liên quan đến context cache.

Với Spring Boot, có thể đặt trong application-test.properties hoặc cấu hình logging test:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Nếu dự án không dùng Spring Boot logging configuration, hãy cấu hình logger trong logback-test.xml hoặc logging backend mà test suite đang sử dụng. Ví dụ với Logback:

~~~xml
<configuration>
    <logger name="org.springframework.test.context.cache" level="DEBUG"/>
</configuration>
~~~

Log thống kê có thể thể hiện các trường như:

| Trường | Ý nghĩa |
|---|---|
| size | Số context hiện đang được giữ trong cache |
| maxSize | Giới hạn cache đang áp dụng |
| parentContextCount | Số context cha được theo dõi trong hierarchy |
| hitCount | Số lần yêu cầu lấy context tìm thấy cache entry |
| missCount | Số lần yêu cầu không tìm thấy entry và cần tải context |

Tỷ lệ hit có thể được tính theo công thức:

\[
\text{Hit ratio} =
\frac{\text{hitCount}}{\text{hitCount}+\text{missCount}}
\]

Ví dụ, nếu cache có 900 hit và 100 miss, hit ratio là 90%. Đây chỉ là một chỉ số quan sát. Một tỷ lệ cao chưa chắc test suite nhanh nếu mỗi lần tải context rất tốn thời gian; tỷ lệ thấp cũng có thể chấp nhận được nếu mỗi context nhỏ và tải nhanh.

### Đọc dấu hiệu trong log

- size thường xuyên chạm maxSize và xuất hiện eviction: cache đang chịu áp lực về số lượng context.
- missCount tăng nhanh: nhiều context mới được yêu cầu hoặc context trước đó đã bị loại bỏ.
- hitCount tăng đều và missCount ít sau giai đoạn khởi động: test suite đang tái sử dụng cấu hình hiệu quả.
- Cùng một test class liên tục tải context mới: xem lại cấu hình có thay đổi giữa các lần chạy, fork process hoặc @DirtiesContext.

Hãy kết hợp log với thời gian tải context và thời gian chạy test. Đừng tăng maxSize chỉ vì thấy cache thường đầy; cần xác định eviction có thực sự làm tổng thời gian test tăng hay không.

## 10. Ảnh hưởng của forked JVM và chạy song song

Context cache là cache tĩnh trong tiến trình JVM. Các test chạy trong cùng một JVM có thể chia sẻ cache. Nếu build tool tạo nhiều forked JVM, mỗi tiến trình có cache riêng và phải tự tải các context cần thiết.

Ví dụ, Maven Surefire có thể chạy test trong nhiều fork. Gradle cũng có thể dùng nhiều test worker process. Khi đó, maxSize được áp dụng cho từng tiến trình, không phải một cache duy nhất dùng chung toàn bộ máy.

Điều này có vài hệ quả:

- Tăng số fork có thể cải thiện thời gian wall-clock nhờ chạy song song, nhưng mỗi fork có thể phải khởi tạo lại context.
- Tổng bộ nhớ có thể tăng vì mỗi JVM giữ cache riêng.
- Thống kê cache trong một tiến trình không phản ánh toàn bộ cache của các tiến trình khác.
- Cùng một context configuration có thể được tải nhiều lần ở các fork khác nhau.

Chạy test song song trong cùng JVM cũng cần chú ý trạng thái bean singleton và tài nguyên dùng chung. Cache có thể được truy cập bởi nhiều test đồng thời; thiết kế bean phải an toàn với cách chạy đó. Tránh để một test thay đổi trạng thái toàn cục mà test khác đang sử dụng.

## 11. Chọn maxSize theo đặc điểm dự án

Tăng maxSize giúp giữ được nhiều context hơn, giảm khả năng phải tải lại các cấu hình đã dùng. Đổi lại, nhiều bean graph, connection pool, web server giả hoặc tài nguyên tích hợp có thể cùng tồn tại trong bộ nhớ lâu hơn.

Giảm maxSize giúp giới hạn số context được giữ và có thể giảm áp lực bộ nhớ. Đổi lại, cache dễ loại bỏ context cần dùng lại, khiến Spring tạo lại context và chạy các callback khởi tạo một lần nữa.

| Dấu hiệu | Hướng điều chỉnh có thể cân nhắc |
|---|---|
| Cache thường đầy, nhiều eviction và tải lại context đắt | Đo mức sử dụng bộ nhớ; nếu còn dư, thử tăng maxSize |
| Test process gặp áp lực bộ nhớ khi giữ nhiều context | Xem xét giảm maxSize hoặc giảm số cấu hình context phân biệt |
| Nhiều miss do mỗi test có cấu hình khác nhau | Chuẩn hóa cấu hình dùng chung trước khi tăng cache |
| Nhiều test chỉ kiểm tra logic nhưng vẫn tải Spring context | Chuyển những test đó thành unit test thuần Java |
| Mỗi fork tải lại cùng cấu hình | Đánh giá số fork và trade-off giữa song song với việc nhân bản cache |

Không nên chọn một giá trị lớn chỉ để tránh mọi eviction. Một context có thể giữ connection pool hoặc tài nguyên đáng kể; số context được giữ càng nhiều thì mức tiêu thụ bộ nhớ và tài nguyên có thể càng lớn. Ngược lại, đặt maxSize quá thấp khiến test suite phải tạo lại context liên tục.

Một quy trình điều chỉnh có thể gồm:

1. Chạy test suite với cấu hình hiện tại và bật DEBUG log cho cache.
2. Ghi nhận maxSize, size, hitCount, missCount và thời gian chạy.
3. Xác định các context key khác nhau và nguyên nhân tạo ra chúng.
4. Giảm những khác biệt cấu hình không cần thiết nếu các test thực sự có thể chia sẻ context.
5. Nếu eviction vẫn gây tải lại đáng kể và bộ nhớ còn đủ, thử tăng maxSize một mức có kiểm soát.
6. Chạy lại trên cùng môi trường và so sánh thời gian, số lần tải context và bộ nhớ.

## 12. Một ví dụ cấu hình và quan sát cache

Giả sử dự án dùng Gradle và có nhiều integration test. Có thể cấu hình cache size và bật log trong test profile:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty "spring.test.context.cache.maxSize", "48"
    testLogging {
        events "failed"
    }
}
~~~

Trong file logback-test.xml:

~~~xml
<configuration>
    <logger name="org.springframework.test.context.cache" level="DEBUG"/>
    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Phần root appender trong ví dụ cần tham chiếu appender đã được khai báo trong cấu hình thực tế của dự án. Nếu đã có cấu hình logging, chỉ cần thêm logger category tương ứng thay vì tạo một cấu hình hoàn chỉnh mới.

Khi chạy test, quan sát log để xem cache có chạm 48 hay không và missCount tăng ở thời điểm nào. Nếu test suite chỉ sử dụng 12 context khác nhau, tăng maxSize từ 32 lên 48 có thể không tạo lợi ích. Nếu có 70 context key và các context cũ thường được yêu cầu lại, cache có thể eviction thường xuyên; lúc đó cần xem cả memory headroom và khả năng giảm fragmentation.

Không nên dùng số liệu từ một lần chạy duy nhất làm quyết định cuối cùng nếu môi trường CI, số fork hoặc mức song song khác với máy phát triển. Hãy so sánh trong điều kiện chạy tương đương.

## 13. Những hiểu lầm thường gặp

### Cache size là số test class

Cache lưu ApplicationContext theo cấu hình, không lưu test class. Nhiều class có thể chia sẻ một context; một class cũng có thể dùng các cấu hình khác nhau ở các bộ test riêng.

### Context bị LRU eviction thì test sẽ thất bại

Eviction chỉ loại context khỏi cache và đóng nó. Khi cần lại, Spring có thể tạo context mới. Test vẫn chạy nếu cấu hình hợp lệ và tài nguyên cần thiết sẵn sàng.

### Context cũ nhất luôn bị loại bỏ

LRU xét lần truy cập gần đây, không chỉ thời điểm tạo. Context được tạo từ lâu nhưng vẫn được truy cập có thể được giữ lại.

### Tăng maxSize luôn làm test nhanh hơn

Giữ nhiều context hơn có thể giảm khởi tạo lặp lại nhưng làm tăng bộ nhớ và tài nguyên sống đồng thời. Nếu nhiều context key khác nhau do cấu hình không cần thiết, giải quyết fragmentation có thể hiệu quả hơn.

### @DirtiesContext và LRU là một cơ chế

@DirtiesContext yêu cầu loại bỏ context vì test đã làm nó không còn phù hợp. LRU tự động loại entry ít được sử dụng gần đây khi cache vượt giới hạn.

### Context cache dùng chung giữa mọi tiến trình

Cache tĩnh chỉ dùng chung trong một JVM. Các fork hoặc test worker process có cache độc lập.

### Cache lưu test instance và kết quả test

Cache chỉ lưu ApplicationContext. JUnit vẫn quản lý test instance theo lifecycle, và kết quả test không được cache bởi TestContext context cache.

## 14. Nguyên tắc quản lý context cache

- Hiểu rằng cache mặc định giữ tối đa 32 ApplicationContext trong mỗi JVM.
- Dùng spring.test.context.cache.maxSize để điều chỉnh giới hạn trước khi test bắt đầu.
- Nhớ LRU loại context ít được truy cập gần đây nhất khi cache cần chỗ.
- Nhận biết context bị loại sẽ được đóng; lần yêu cầu sau cần tải lại.
- Phân biệt eviction tự động với việc loại bỏ tường minh bằng @DirtiesContext.
- Xem xét các thành phần trong context cache key như cấu hình, profile, property, initializer, customizer và hierarchy.
- Dùng log DEBUG của org.springframework.test.context.cache để theo dõi size, maxSize, hit và miss.
- Đánh giá cả thời gian khởi tạo lẫn bộ nhớ trước khi tăng hoặc giảm maxSize.
- Giảm context fragmentation bằng cách chia sẻ cấu hình khi các test thật sự cần cùng môi trường.
- Nhớ cache độc lập giữa các forked JVM và chú ý singleton bean khi chạy test song song.
- Chỉ dùng @DirtiesContext khi trạng thái context thực sự cần được loại bỏ; dọn dữ liệu bằng transaction hoặc SQL cleanup khi phù hợp hơn.

Giới hạn cache và chính sách LRU cho phép Spring TestContext tái sử dụng những ApplicationContext được dùng thường xuyên trong khi vẫn kiểm soát số context được giữ. Khi test suite có nhiều cấu hình, việc hiểu cache key, theo dõi hit/miss và nhận diện eviction giúp tìm đúng nguyên nhân tải context lặp lại. Điều chỉnh maxSize dựa trên số liệu về thời gian và bộ nhớ sẽ giúp cân bằng hiệu năng với tài nguyên của tiến trình kiểm thử.
