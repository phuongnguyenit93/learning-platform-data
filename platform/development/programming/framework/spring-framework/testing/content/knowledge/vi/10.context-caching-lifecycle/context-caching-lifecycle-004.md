# Phạm vi cache trong cùng JVM và ảnh hưởng của fork process

Spring TestContext Framework lưu các ApplicationContext đã khởi tạo trong một cache tĩnh của JVM để những test có cấu hình tương đương có thể dùng lại. Cơ chế này giúp giảm thời gian chạy test vì việc tạo Spring context thường tốn nhiều tài nguyên: đọc cấu hình, quét bean, tạo object, khởi tạo connection pool và áp dụng auto-configuration.

Phạm vi của cache là **một tiến trình JVM**. Các test chạy trong cùng JVM có thể dùng chung cache nếu cấu hình context tương đương. Khi build tool tạo một fork process khác, tiến trình mới có bộ nhớ và static state riêng, nên nó có cache ApplicationContext độc lập. Hai tiến trình không chia sẻ context đã khởi tạo, kể cả khi chúng chạy cùng một bộ test và dùng cùng cấu hình.

Hiểu rõ ranh giới này giúp giải thích vì sao test suite có thể chạy nhanh khi gom test vào một worker nhưng chậm hơn khi tăng số fork, vì sao một context được tạo nhiều lần trong CI, và cách chọn cấu hình Gradle hoặc Maven phù hợp với thời gian chạy, mức song song và tài nguyên máy.

## 1. ApplicationContext cache hoạt động như thế nào?

Mỗi khi Spring Test cần một ApplicationContext, TestContext Framework xây dựng cấu hình đã hợp nhất cho test class. Cấu hình đó được dùng để tìm một context tương ứng trong cache.

- Nếu cache đã có context phù hợp, Spring trả lại context đó.
- Nếu chưa có, Spring tạo context, áp dụng các bước bootstrap và lưu context mới vào cache.
- Các test class có cấu hình tương đương có thể dùng lại cùng context.
- Khi một context bị đánh dấu không còn hợp lệ hoặc bị loại khỏi cache, Spring phải tạo lại nếu một test sau đó cần cấu hình tương ứng.

Cache mặc định được quản lý trong bộ nhớ tĩnh của TestContext Framework. Vì static field thuộc class được nạp trong một JVM, cache có phạm vi theo tiến trình chạy test.

~~~mermaid
flowchart TD
    A["Test class A"] --> K["MergedContextConfiguration"]
    B["Test class B"] --> K
    C["Test class C"] --> K
    K --> Q{"Context tương ứng trong cache?"}
    Q -->|"Có"| R["Tái sử dụng ApplicationContext"]
    Q -->|"Không"| N["Tạo ApplicationContext mới"]
    N --> S["Lưu vào cache của JVM"]
    S --> R
~~~

Sơ đồ mô tả các test class có cấu hình tương đương. Nếu cấu hình khác nhau, chúng có thể cần những cache entry và ApplicationContext khác nhau.

### Vì sao tái sử dụng context có lợi?

Tạo Spring context có thể bao gồm nhiều công việc:

- Đọc và hợp nhất cấu hình.
- Quét component hoặc đăng ký bean definition.
- Tạo bean và giải quyết dependency.
- Khởi tạo DataSource, connection pool hoặc client.
- Áp dụng transaction manager, security, AOP và các post-processor.
- Khởi động web infrastructure nếu context có cấu hình web.
- Thực hiện các callback khởi tạo của bean.

Nếu 20 test class cùng dùng một cấu hình tương đương, Spring có thể chỉ cần tạo context một lần trong JVM rồi dùng lại cho các class tiếp theo. Nếu mỗi class chạy trong một JVM mới, lợi ích này bị mất vì mỗi process bắt đầu với cache rỗng.

## 2. Cache key quyết định test nào có thể dùng chung context

Spring không chia sẻ context chỉ vì hai test class có cùng tên hoặc cùng package. TestContext Framework so sánh cấu hình đã hợp nhất, thường được biểu diễn bởi MergedContextConfiguration.

Các yếu tố quan trọng có thể tham gia xác định cache key gồm:

- Resource locations và configuration classes.
- Context initializer classes.
- Context loader.
- Active profiles.
- Property source locations và inline properties.
- Context customizers.
- Parent context nếu dùng context hierarchy.

Ví dụ, hai test class cùng khai báo:

~~~java
@SpringJUnitConfig(ApplicationTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.search.enabled=true")
class SearchServiceTest {
}
~~~

~~~java
@SpringJUnitConfig(ApplicationTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.search.enabled=true")
class SearchControllerCollaboratorTest {
}
~~~

Nếu các phần cấu hình đã hợp nhất tương đương và không có yếu tố khác làm thay đổi cache key, hai class có thể dùng chung context. Việc tên class khác nhau không tự động buộc Spring tạo context mới.

Ngược lại, nếu một test dùng profile test còn test khác dùng profile integration, hoặc property khác nhau làm cấu hình context thay đổi, Spring có thể tạo hai context riêng.

### Ví dụ về các cấu hình khác nhau

| Test class | Cấu hình chính | Khả năng tái sử dụng |
|---|---|---|
| OrderServiceTest | Config A, profile test, property X | Có thể chia sẻ với test cùng cấu hình |
| OrderControllerTest | Config A, profile test, property X | Có thể chia sẻ nếu toàn bộ cache key tương đương |
| OrderRepositoryTest | Config B, profile test, property X | Thường cần context khác |
| OrderServiceIntegrationTest | Config A, profile integration, property X | Cần context khác khi profile làm thay đổi cấu hình |
| OrderServiceFeatureTest | Config A, profile test, property Y | Cần context khác nếu property làm thay đổi cấu hình |

Một thay đổi nhỏ trong annotation có thể làm cache key khác nhau. Vì vậy, nếu một dự án có rất nhiều biến thể @SpringBootTest, @ActiveProfiles, @TestPropertySource hoặc ContextCustomizer, số context cần tạo có thể tăng đáng kể.

### ContextCustomizer cũng ảnh hưởng đến cache key

ContextCustomizer là một phần của MergedContextConfiguration. Nếu customizer chứa dữ liệu cấu hình, equals() và hashCode() của nó phải phản ánh đầy đủ dữ liệu làm thay đổi context.

Ví dụ, customizer chọn tenant hoặc region cần tính giá trị tenant/region vào equality. Hai test dùng cùng giá trị có thể chia sẻ context nếu các yếu tố còn lại tương đương. Hai test dùng giá trị khác nhau cần context riêng.

Nếu equality bỏ qua một giá trị làm thay đổi bean hoặc Environment, Spring có thể xem hai cấu hình khác nhau là tương đương và tái sử dụng nhầm context. Nếu equality dựa vào object identity, các customizer có cùng cấu hình nhưng được tạo thành instance khác nhau có thể làm giảm khả năng tái sử dụng.

## 3. Cache có phạm vi trong cùng một JVM

Hãy phân biệt ba tình huống:

1. Nhiều test class chạy tuần tự trong cùng một JVM.
2. Nhiều test class chạy song song bằng các thread trong cùng một JVM.
3. Test được phân phối vào nhiều JVM process riêng biệt.

Hai tình huống đầu có thể truy cập cùng cache tĩnh của TestContext Framework. Tình huống thứ ba có cache riêng ở từng process.

~~~mermaid
flowchart TB
    subgraph P1["JVM process 1"]
        T1["Test class A"]
        T2["Test class B"]
        C1[("Context cache 1")]
        T1 --> C1
        T2 --> C1
    end
    subgraph P2["JVM process 2"]
        T3["Test class C"]
        T4["Test class D"]
        C2[("Context cache 2")]
        T3 --> C2
        T4 --> C2
    end
    C1 -. "Không chia sẻ heap/static state" .- C2
~~~

Ví dụ:

- OrderServiceTest chạy trong JVM process 1 và tạo context A.
- OrderControllerTest cũng chạy trong process 1 với cấu hình tương đương, nên có thể dùng lại context A.
- OrderRepositoryTest chạy trong process 2 với cùng cấu hình tương đương, nhưng process 2 chưa có context A. Nó phải tạo context riêng trong cache của process 2.

Hai context có thể được tạo từ cùng file cấu hình và cho kết quả tương đương, nhưng chúng là hai object graph độc lập trong hai heap khác nhau.

### Cache không nằm trong Gradle daemon hay Maven process điều phối

Build tool thường điều phối test bằng các worker JVM. ApplicationContext được tạo trong tiến trình thực thi test, không phải một object có thể được Gradle daemon hoặc Maven launcher chia sẻ cho mọi worker.

Vì vậy:

- Hai Gradle test worker là hai process độc lập và có cache riêng.
- Hai lần chạy test task trong hai process riêng không dùng chung cache.
- Hai Maven Surefire fork là hai process độc lập và có cache riêng.
- Một test chạy lại ở lần build tiếp theo sẽ không kế thừa static cache của JVM đã kết thúc ở lần build trước.

Giữ Gradle daemon sống không có nghĩa ApplicationContext cache của test worker vẫn còn. Cache thuộc JVM chạy test và chỉ tồn tại trong vòng đời process đó.

## 4. Fork process khác gì với chạy song song bằng thread?

Tăng mức song song có thể được thực hiện ở nhiều tầng. Cần phân biệt song song trong một JVM và song song bằng nhiều process.

| Cách chạy | Số JVM | Phạm vi cache | Tác động chính |
|---|---:|---|---|
| Test tuần tự trong một worker | 1 | Một cache | Khả năng tái sử dụng context cao |
| JUnit parallel execution trong một worker | 1 | Các thread dùng chung cache | Có thể chạy test đồng thời với cùng context |
| Nhiều Gradle test worker | Nhiều | Mỗi worker có cache riêng | Context có thể bị tạo lặp giữa các worker |
| Nhiều Maven Surefire fork | Nhiều | Mỗi fork có cache riêng | Context không chia sẻ giữa các fork |
| Mỗi test class chạy trong process mới | Nhiều process theo class | Cache thường mất sau mỗi class | Chi phí khởi tạo context tăng mạnh |

### Song song trong cùng JVM

Nếu JUnit Jupiter chạy nhiều test bằng các thread trong cùng worker process, các thread vẫn thuộc cùng một JVM và có thể truy cập cache ApplicationContext chung.

Điều đó giúp tránh phải tạo một context cho từng thread. Tuy nhiên, nó không đảm bảo mọi bean trong context đều an toàn khi truy cập đồng thời.

Ví dụ, một singleton service giữ mutable state dùng chung có thể gặp race condition khi hai test gọi cùng lúc. Repository, connection pool và các bean có trạng thái cần được sử dụng theo hợp đồng thread-safety của chúng.

Cũng cần chú ý các test thay đổi hoặc loại context khỏi cache bằng @DirtiesContext. Nếu một context đang được nhiều test dùng đồng thời, việc đóng hoặc loại context có thể gây ảnh hưởng đến test khác. Các test có tác động tới lifecycle context cần được tổ chức để tránh chạy đồng thời với test đang sử dụng cùng context.

### Song song bằng nhiều JVM

Khi build tool tạo nhiều worker process, mỗi worker có heap riêng. Các worker có thể chạy test cùng lúc, nhưng không thể dùng chung ApplicationContext object trong bộ nhớ.

Điều này đem lại khả năng cô lập process và tận dụng nhiều core CPU. Đổi lại, nếu các worker cần cùng một cấu hình context, mỗi worker vẫn có thể phải tạo context riêng.

Ví dụ, 4 worker cùng chạy các test cần cấu hình ApplicationTestConfiguration có thể tạo tối đa 4 context tương đương, một context trong mỗi cache. Số thực tế phụ thuộc cách test được phân phối và số process thực sự chạy các test đó.

## 5. Giới hạn kích thước cache và cơ chế LRU

Spring TestContext Framework có giới hạn kích thước cache mặc định là **32 context** trong cấu hình mặc định phổ biến. Có thể điều chỉnh giới hạn bằng thuộc tính:

~~~properties
spring.test.context.cache.maxSize=64
~~~

Hoặc truyền system property cho JVM chạy test:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

Khi cache vượt giới hạn, Spring sử dụng chiến lược LRU (Least Recently Used): context ít được sử dụng gần đây nhất sẽ bị loại khỏi cache để nhường chỗ cho context mới.

Việc loại context khỏi cache có nghĩa Spring không thể tiếp tục tái sử dụng entry đó. Khi test sau cần cấu hình tương ứng, context phải được tạo lại. Việc eviction cũng kéo theo lifecycle đóng context theo cơ chế của cache.

### Vì sao cache có thể bị churn?

Giả sử một test suite có 50 cấu hình context khác nhau nhưng cache chỉ giữ tối đa 32 entry. Khi test liên tục chuyển qua các cấu hình khác nhau, những entry cũ có thể bị loại trước khi test cần dùng lại chúng.

Kết quả là:

- Context được tạo lại nhiều lần.
- Startup cost lặp lại.
- Database pool hoặc web infrastructure có thể được khởi tạo nhiều lần.
- Thời gian tổng thể tăng dù số test không thay đổi.

Tăng cache maxSize có thể giúp giữ nhiều context hơn, nhưng mỗi context có thể giữ nhiều bean, cache nội bộ, connection pool hoặc tài nguyên. Cache quá lớn làm tăng mức sử dụng heap và có thể gây áp lực bộ nhớ.

Không nên tăng giới hạn chỉ vì thấy cache miss. Trước tiên hãy xác định số cấu hình context thực tế và xem có nhiều test đang tạo các biến thể không cần thiết hay không.

### Cấu hình giới hạn trong test JVM

Với Gradle, có thể truyền property vào Test task:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty 'spring.test.context.cache.maxSize', '64'
}
~~~

Với Maven Surefire:

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

Tên property phải được truyền tới JVM thực thi test. Đặt nó ở môi trường chạy Maven/Gradle nhưng không truyền vào worker JVM có thể khiến test process không nhận giá trị dự kiến.

## 6. Fork process ảnh hưởng thế nào đến Gradle?

Gradle thực thi test bằng các test worker process. Các thuộc tính quan trọng để điều khiển cách worker được tạo gồm:

- maxParallelForks: số worker process có thể chạy song song cho một Test task.
- forkEvery: số test class tối đa được thực thi trong một worker process trước khi Gradle dừng worker đó và tạo process mới.
- systemProperty: truyền system property vào JVM test worker.

### maxParallelForks

Ví dụ:

~~~groovy
tasks.test {
    maxParallelForks = 1
}
~~~

Một worker process được dùng tại một thời điểm cho Test task này. Những test class được chạy trong cùng worker có thể tái sử dụng cache nếu cấu hình context tương đương.

Nếu tăng lên:

~~~groovy
tasks.test {
    maxParallelForks = 4
}
~~~

Gradle có thể chạy tối đa bốn worker process đồng thời. Mỗi worker có cache Spring riêng. Tăng số worker có thể rút ngắn thời gian chạy khi test độc lập và máy có đủ CPU/RAM, nhưng cũng có thể tăng số lần tạo context và mức sử dụng bộ nhớ.

Đặt maxParallelForks = 1 không có nghĩa mọi Test task trong toàn bộ build dùng chung một JVM. Mỗi task có thể có worker process riêng, và các task chạy song song cũng có thể tạo nhiều process.

### forkEvery

forkEvery quyết định khi nào Gradle thay worker process sau một số lượng test class. Giá trị mặc định là 0, nghĩa là không giới hạn số class trước khi worker được tái sử dụng trong vòng đời task.

Ví dụ:

~~~groovy
tasks.test {
    forkEvery = 0
}
~~~

Worker có thể chạy toàn bộ test class được phân phối cho nó, nên cache có cơ hội tồn tại lâu hơn.

Nếu đặt:

~~~groovy
tasks.test {
    forkEvery = 1
}
~~~

Worker process bị thay mới sau mỗi test class. Cache Spring của process cũ không thể được chuyển sang process mới. Nếu nhiều class dùng cùng context, chúng có thể phải khởi tạo lại context ở từng lần fork.

Một cấu hình như vậy có thể hữu ích để cô lập test bị rò rỉ trạng thái hoặc gặp lỗi do static state tích lũy. Tuy nhiên, chi phí khởi động JVM và ApplicationContext có thể tăng đáng kể.

### Ví dụ cấu hình Gradle có kiểm soát

~~~groovy
tasks.withType(Test).configureEach {
    maxParallelForks = 1
    forkEvery = 0

    systemProperty 'spring.test.context.cache.maxSize', '64'
}
~~~

Cấu hình minh họa này ưu tiên tái sử dụng cache trong từng Test task. Với dự án lớn, có thể tăng maxParallelForks sau khi đo thời gian và mức sử dụng tài nguyên. Cần nhớ rằng các worker vẫn có cache riêng khi số fork lớn hơn một.

## 7. Fork process ảnh hưởng thế nào đến Maven Surefire?

Maven Surefire Plugin điều khiển process chạy unit test. Hai thuộc tính quan trọng là:

- forkCount: số JVM fork tối đa chạy test song song.
- reuseForks: quyết định một fork process có được tái sử dụng cho nhiều test class hay không.

### Một fork được tái sử dụng

Ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
~~~

Với một fork và reuseForks bật, process có thể chạy nhiều test class. Cache Spring tồn tại trong process đó và có thể được tái sử dụng giữa các class tương thích.

Đây là cấu hình phổ biến khi muốn giữ cache hiệu quả. Giá trị mặc định cụ thể có thể thay đổi theo phiên bản plugin hoặc cấu hình dự án, nên hãy kiểm tra cấu hình thực tế của build.

### Nhiều fork process

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>4</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
~~~

Surefire có thể phân phối test vào tối đa bốn JVM. Mỗi JVM có cache riêng. Context tương đương có thể được tạo lại trong nhiều fork nếu các test cần nó được phân phối sang các process khác nhau.

### Không tái sử dụng fork

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>false</reuseForks>
    </configuration>
</plugin>
~~~

Khi reuseForks tắt, Surefire tạo process mới cho từng test class theo cơ chế fork của plugin. Mỗi process bắt đầu với cache rỗng và kết thúc sau phần test được giao.

Đây là lựa chọn có tính cô lập cao hơn, nhưng thường làm Spring test suite chậm hơn vì context khó được tái sử dụng giữa các class.

### So sánh nhanh

| Cấu hình | Process | Khả năng giữ cache giữa test class |
|---|---|---|
| forkCount = 1, reuseForks = true | Một fork được tái sử dụng | Cao trong nhóm test chạy cùng fork |
| forkCount > 1, reuseForks = true | Nhiều fork được tái sử dụng | Có trong từng fork, không chia sẻ giữa fork |
| reuseForks = false | Process mới theo test class | Hầu như không tái sử dụng giữa class |

Các thuộc tính trên cần được đọc cùng cấu hình song song, provider và phiên bản Surefire. Không nên suy luận số context chỉ từ một thuộc tính đơn lẻ.

## 8. Vì sao test suite có thể chậm khi bật nhiều fork?

Giả sử có 30 test class và tất cả đều cần cùng một Spring Boot context. Nếu chạy tuần tự trong một JVM và không có eviction hoặc @DirtiesContext, context có thể chỉ cần tạo một lần.

Nếu chia đều cho ba fork process, mỗi process có thể cần tạo context riêng. Tổng cộng có thể xuất hiện ba lần khởi tạo context thay vì một.

Chi phí không chỉ là tạo bean. Context có thể mở:

- Connection pool tới database.
- HTTP client connection pool.
- Embedded server.
- Message listener container.
- Scheduler hoặc executor.
- Cache và resource manager.
- Các bean giữ bộ nhớ đáng kể.

Khi nhiều fork khởi tạo đồng thời, hệ thống ngoài như database có thể nhận nhiều connection pool hơn. Máy chạy CI cũng cần nhiều RAM hơn vì mỗi JVM giữ một bộ object riêng.

~~~mermaid
flowchart LR
    A["30 test classes"] --> B["1 JVM"]
    B --> C["1 cache"]
    C --> D["1 context nếu cấu hình giống nhau"]
    A --> E["3 JVM forks"]
    E --> F["Cache 1"]
    E --> G["Cache 2"]
    E --> H["Cache 3"]
    F --> I["Context 1"]
    G --> J["Context 2"]
    H --> K["Context 3"]
~~~

Sơ đồ là ví dụ minh họa khi test được chia cho các fork và mỗi fork đều chạy ít nhất một class cần cùng cấu hình. Phân phối thực tế do build tool quyết định.

### Khi nhiều fork vẫn có lợi

Nhiều fork có thể giảm thời gian tổng thể khi:

- Test có nhiều phần độc lập và thời gian thực thi nghiệp vụ dài.
- Test không phải khởi động lại một context nặng ở mỗi class.
- Máy CI có nhiều CPU và đủ RAM.
- Database hoặc broker test chịu được số kết nối đồng thời.
- Test không chia sẻ file hoặc dữ liệu gây tranh chấp.

Do đó, không có một con số fork tối ưu cho mọi dự án. Cần đo cả thời gian tổng, thời gian khởi tạo context, mức sử dụng RAM/CPU và tải lên hạ tầng test.

## 9. Đọc thống kê để biết cache đang được dùng ra sao

Spring TestContext Framework có thể ghi log thống kê cache. Bật mức DEBUG cho logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Tùy logging backend và cấu hình test, có thể đặt trong logback-test.xml, application-test.properties hoặc cấu hình logging được test sử dụng.

Các thống kê thường giúp quan sát:

- Kích thước cache hiện tại.
- Giới hạn kích thước cache.
- Số lần cache hit.
- Số lần cache miss.
- Thông tin về context hierarchy nếu có.

Cache hit nghĩa là Spring tìm thấy context tương ứng và tái sử dụng. Cache miss nghĩa là chưa có entry phù hợp, nên cần tải context mới.

Ví dụ minh họa:

~~~text
Spring test ApplicationContext cache statistics:
size = 4, maxSize = 32, parentContextCount = 0,
hitCount = 120, missCount = 4
~~~

Nếu hitCount tăng nhanh trong khi missCount thấp, cache đang tái sử dụng context hiệu quả. Nếu missCount tăng liên tục, có thể test đang tạo nhiều cấu hình khác nhau, context bị eviction hoặc process mới liên tục được tạo.

Cần đọc thống kê trong từng JVM. Mỗi fork có cache và số liệu riêng. Log từ nhiều process có thể xen kẽ, vì vậy nên xem PID hoặc thông tin process của log khi phân tích CI.

### Phân tích cache miss

Khi thấy nhiều cache miss, hãy kiểm tra:

1. Test class có dùng cấu hình classes/locations khác nhau không?
2. @ActiveProfiles có tạo nhiều tổ hợp profile không?
3. @TestPropertySource có khai báo các giá trị khác nhau không?
4. ContextCustomizer có equality/hashCode ổn định không?
5. Có nhiều @DirtiesContext làm context bị loại khỏi cache không?
6. Cache maxSize có quá nhỏ so với số cấu hình thực tế không?
7. Build tool có đang tạo nhiều fork hoặc thay worker thường xuyên không?

Không phải cache miss nào cũng là lỗi. Nếu hai test cần cấu hình thực sự khác nhau, context riêng là đúng. Mục tiêu là loại bỏ những khác biệt không cần thiết làm giảm khả năng dùng chung.

## 10. @DirtiesContext và tác động tới cache

@DirtiesContext đánh dấu ApplicationContext đã bị thay đổi hoặc không còn an toàn để tái sử dụng. Spring Test sẽ loại context tương ứng khỏi cache và đóng context theo lifecycle của framework.

Ví dụ:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ChangesGlobalConfigurationTest {
    // Test thay đổi trạng thái context
}
~~~

Sau khi class hoàn tất, context có thể bị loại khỏi cache. Một test class sau đó cần cấu hình tương đương sẽ phải tạo context mới.

Nếu sử dụng @DirtiesContext thường xuyên, cache hit giảm và thời gian khởi tạo tăng. Hãy chỉ dùng khi test thực sự làm thay đổi cấu hình hoặc trạng thái context đến mức không thể tiếp tục tái sử dụng.

### Fork và @DirtiesContext giải quyết vấn đề khác nhau

Fork process tạo ranh giới bộ nhớ và static state mới. @DirtiesContext vô hiệu hóa một context trong cache hiện tại của JVM.

- Dùng fork khi cần cô lập process hoặc reset static state ở mức JVM.
- Dùng @DirtiesContext khi một test làm context không còn an toàn để dùng lại.
- Dùng @BeforeEach/@AfterEach hoặc fixture khi chỉ cần reset trạng thái của test method.
- Dùng transaction rollback khi dữ liệu database thuộc transaction test và rollback đáp ứng yêu cầu.

Không nên dùng forkEvery = 1 hoặc reuseForks = false chỉ để che một test làm thay đổi singleton. Hãy xác định trạng thái nào bị rò rỉ và chọn cơ chế cô lập phù hợp.

## 11. Context cache và tài nguyên bên ngoài

Một ApplicationContext có thể chứa bean giữ tài nguyên như connection pool, embedded server, scheduler hoặc message listener. Việc tái sử dụng context cũng đồng nghĩa những bean đó có thể tồn tại qua nhiều test class trong cùng JVM.

Điều này có thể giảm chi phí khởi động, nhưng test cần tuân thủ lifecycle của tài nguyên.

### Database connection pool

Nếu mỗi fork tạo một context với HikariCP, mỗi process có thể tạo một pool riêng. Với bốn fork, database có thể nhận bốn pool thay vì một pool. Nếu mỗi pool cho phép tối đa 10 connection, giới hạn kết nối tiềm năng tăng đáng kể.

Cần tính số process đồng thời và cấu hình pool tương ứng với khả năng của database test. Một test suite có thể chạy tốt với một worker nhưng làm database quá tải khi chạy nhiều fork.

### Testcontainers

Testcontainers có thể được quản lý theo lifecycle của test class, suite hoặc context tùy cách khai báo. Nếu context cache được tái sử dụng lâu hơn vòng đời container, các bean có thể giữ endpoint của tài nguyên đã bị dừng.

Hãy bảo đảm vòng đời container phù hợp với context sử dụng nó. @DynamicPropertySource thường đăng ký địa chỉ tài nguyên vào context; nếu context được cache, giá trị cấu hình đó thuộc context đã tạo. Không nên dừng container trong khi context còn được tái sử dụng.

### HTTP server và message broker

Một context có embedded server hoặc message listener có thể chiếm port, thread và connection trong suốt thời gian được cache. Nhiều fork có thể khởi chạy nhiều instance tương ứng.

Nếu port được cố định, các process có thể xung đột. Dùng port động khi phù hợp và bảo đảm mỗi process có tài nguyên độc lập. Với broker hoặc database dùng chung, namespace và dữ liệu test cần được cô lập để tránh va chạm.

### Shutdown và cleanup

Khi context bị đóng do eviction hoặc @DirtiesContext, bean có callback destroy có thể giải phóng tài nguyên. Khi worker process kết thúc, process và tài nguyên hệ điều hành của nó cũng kết thúc. Dù vậy, không nên dựa vào việc process bị dừng để thay thế cleanup rõ ràng cho dữ liệu hoặc tài nguyên bên ngoài.

## 12. Một ví dụ đo tác động của fork

Giả sử một suite có 24 test class:

- 18 class dùng chung context A.
- 4 class dùng context B.
- 2 class dùng context C.

Nếu cả 24 class chạy trong một JVM và không có eviction hoặc context bị dirty, số lần tạo context có thể gần bằng ba.

Nếu test được phân phối đều cho ba JVM, mỗi JVM có thể cần tạo context A. Context B và C cũng có thể được tạo ở nhiều JVM tùy cách phân phối. Tổng số lần tạo có thể lớn hơn ba.

| Cách chạy giả định | Số process | Số lần tạo context có thể xảy ra |
|---|---:|---|
| Một process, cache đủ lớn | 1 | Khoảng 3 |
| Ba process, mỗi process cần context A | 3 | Ít nhất 3 cho A, cộng B/C theo phân phối |
| Một process mới cho mỗi class | 24 | Có thể gần 24 nếu mỗi class cần context |
| Hai process tái sử dụng lâu dài | 2 | Tối đa hai bản của mỗi cấu hình được dùng ở cả hai process, tùy phân phối |

Đây là mô hình để hiểu xu hướng, không phải dự báo thời gian chính xác. Thời gian còn phụ thuộc số bean, startup hook, database, Docker, CPU, heap và việc các test có thực sự dùng chung cache key hay không.

### Đo bằng log thay vì chỉ nhìn thời gian tổng

Để so sánh hai cấu hình fork:

1. Chạy cùng một bộ test và bật log cache ở DEBUG.
2. Ghi lại số process thực tế, hit/miss và thời gian khởi tạo context.
3. Chạy lại với số fork khác.
4. So sánh tổng thời gian, số lần tạo context và mức sử dụng RAM/CPU.
5. Kiểm tra database/broker có bị tăng tải hoặc lỗi do kết nối đồng thời không.

Nếu thời gian giảm nhưng số context tăng mạnh, cấu hình mới có thể đang đổi chi phí khởi tạo lấy song song. Cần đánh giá xem máy CI và hạ tầng test có đủ tài nguyên cho cách chạy đó hay không.

## 13. Các lỗi thường gặp khi hiểu sai phạm vi cache

### Nghĩ rằng Gradle daemon giữ cache Spring

Gradle daemon điều phối build. Test worker JVM thực thi test và giữ ApplicationContext cache. Khi worker kết thúc, static cache của worker cũng kết thúc.

Giữ daemon không giúp context được dùng lại trong một test worker mới.

### Nghĩ rằng nhiều fork dùng chung một context

Mỗi fork là một process có heap riêng. Một ApplicationContext object không thể được chia sẻ trực tiếp giữa các process. Các process có thể tạo context tương đương, nhưng mỗi process sở hữu instance riêng.

### Tăng maxParallelForks nhưng mong startup chỉ xảy ra một lần

Tăng fork tạo nhiều cache độc lập. Nếu mọi worker đều chạy test cần cùng context, mỗi worker có thể phải tạo context đó. Đo số lần khởi tạo và chi phí thực tế trước khi tăng fork.

### Đặt forkEvery quá thấp

Nếu worker bị thay mới sau mỗi class hoặc một số class rất ít, cache không có đủ thời gian tận dụng. JVM startup và Spring context startup lặp lại có thể khiến suite chậm hơn.

### Tăng cache maxSize quá cao

Cache lớn giữ nhiều context và bean trong heap. Nếu các context chứa pool hoặc server, tài nguyên tích lũy có thể gây áp lực bộ nhớ và hệ thống ngoài. Chọn maxSize dựa trên số cấu hình thực tế và khả năng tài nguyên.

### Dùng @DirtiesContext để xử lý mọi lỗi trạng thái

@DirtiesContext làm mất cache entry và tạo lại context, nhưng chi phí có thể cao. Nếu lỗi chỉ do dữ liệu test hoặc một mock cần reset, dùng cleanup hoặc lifecycle method phù hợp.

### Giả định test song song trong cùng JVM luôn an toàn

Cache có thể dùng chung context, nhưng singleton bean và dữ liệu dùng chung vẫn có thể bị truy cập đồng thời. Kiểm tra thread-safety, cô lập dữ liệu và tránh đóng context khi test khác đang dùng.

### Quên rằng các task/module có worker riêng

Một multi-module build có thể chạy nhiều Test task. Mỗi task có thể khởi tạo worker JVM riêng. Context không tự chia sẻ giữa các task hoặc module chỉ vì chúng chạy trong cùng một Gradle/Maven build.

## 14. Chọn chiến lược fork và cache phù hợp

Không có cấu hình duy nhất phù hợp cho mọi dự án. Hãy quyết định theo loại test và tài nguyên sẵn có.

| Tình huống | Hướng cấu hình nên cân nhắc |
|---|---|
| Nhiều test class dùng cùng Spring context | Giữ worker process sống lâu hơn để tận dụng cache |
| Context startup rất nặng, CI có RAM hạn chế | Giảm số fork đồng thời |
| Test độc lập, thời gian xử lý dài, máy nhiều CPU/RAM | Thử tăng số fork và đo kết quả |
| Test bị rò rỉ static state giữa class | Sửa nguồn state; dùng fork riêng khi cần cô lập process |
| Nhiều context khác nhau và cache miss do eviction | Đánh giá số cấu hình và điều chỉnh maxSize |
| Test cần context riêng do thay đổi cấu hình | Giữ cache key khác nhau và chấp nhận context riêng |
| Test dùng @DirtiesContext thường xuyên | Xem lại lý do context bị thay đổi và khả năng reset trạng thái nhỏ hơn |

Một cấu hình khởi đầu thường hợp lý là giữ worker được tái sử dụng, không fork lại quá thường xuyên và dùng số worker vừa với tài nguyên CI. Sau đó đo bằng log cache và thời gian thực tế để điều chỉnh.

Với Gradle, xem xét maxParallelForks và forkEvery. Với Maven Surefire, xem xét forkCount và reuseForks. Nếu dùng cả Surefire và Failsafe, mỗi plugin/task có process và vòng đời riêng; không giả định cache được chia sẻ giữa hai giai đoạn.

## 15. Quy trình điều tra khi context bị tạo quá nhiều lần

Khi startup context chiếm phần lớn thời gian test, có thể đi theo trình tự sau:

1. Bật DEBUG cho org.springframework.test.context.cache.
2. Xác định số JVM worker đang chạy.
3. So sánh cache hit/miss trong từng process.
4. Nhóm test theo cấu hình context đã hợp nhất.
5. Kiểm tra các khác biệt về profile, property, initializer, customizer và loader.
6. Kiểm tra context có bị loại bởi @DirtiesContext hoặc LRU eviction không.
7. Kiểm tra forkEvery/reuseForks có làm worker kết thúc quá sớm không.
8. Đo lại sau khi điều chỉnh để xác nhận số lần tạo context giảm.

Nếu cache miss cao trong từng process, tập trung vào cấu hình và cache key. Nếu mỗi process có hit tốt nhưng tổng số context vẫn cao, nguyên nhân có thể nằm ở số fork hoặc cách build tool phân phối test.

Nếu một context bị tạo lại sau mỗi test class dù cùng cấu hình, hãy xem log và cấu hình thực tế trước khi kết luận cache không hoạt động. Có thể test đang dùng @DirtiesContext, customizer không có equality phù hợp, hoặc mỗi class nhận property/profile khác nhau.

## 16. Nguyên tắc thiết kế để tận dụng cache an toàn

Để ApplicationContext cache đem lại lợi ích mà không làm test phụ thuộc lẫn nhau:

- Dùng cấu hình context nhất quán cho những test thực sự cần cùng môi trường.
- Tránh tạo biến thể profile/property không cần thiết.
- Thiết kế ContextCustomizer bất biến và triển khai equals/hashCode theo cấu hình.
- Không đặt trạng thái theo từng test method vào customizer.
- Reset trạng thái mutable của bean hoặc dùng fixture phù hợp.
- Chỉ dùng @DirtiesContext khi context thực sự không thể tái sử dụng.
- Chọn maxSize theo số context và dung lượng bộ nhớ.
- Đo số fork cùng số lần khởi tạo context, không chỉ đo thời gian tổng.
- Bảo đảm tài nguyên như database pool, container, server và broker có lifecycle tương thích với context.
- Khi chạy test song song, kiểm tra thread-safety của bean và tính độc lập của dữ liệu.

Cache ApplicationContext là cache trong bộ nhớ của JVM thực thi test. Các test class trong cùng process có thể tái sử dụng context khi MergedContextConfiguration tương đương. Thread chạy song song trong cùng process vẫn có thể dùng cache đó, nhưng cần quan tâm đến trạng thái bean và lifecycle. Fork process tạo một vùng nhớ và cache mới, nên tăng số fork hoặc thay worker thường xuyên có thể làm tăng số lần khởi tạo Spring context.

Khi cấu hình Gradle hoặc Maven, hãy cân bằng mức song song với chi phí startup và tài nguyên của từng context. Theo dõi hit/miss, cache eviction, số worker và thời gian tạo context sẽ giúp xác định phần chi phí đến từ cấu hình test hay từ cách build tool phân phối test.

