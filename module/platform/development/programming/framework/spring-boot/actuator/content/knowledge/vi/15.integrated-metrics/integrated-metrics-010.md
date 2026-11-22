# Quan sát lời gọi Spring Data repository theo cơ chế được hỗ trợ

## 1. Ta đang quan sát điều gì?

Trong ứng dụng Spring, repository là nơi mã nghiệp vụ gọi các thao tác như lưu, tìm kiếm hoặc đếm dữ liệu. Khi ứng dụng chậm, biết “cơ sở dữ liệu có kết nối” chưa trả lời được câu hỏi: phương thức repository nào được gọi nhiều, phương thức nào mất thời gian và phương thức nào đang lỗi.

Spring Boot Actuator có tích hợp sẵn với Spring Data để ghi nhận những lời gọi này bằng Micrometer. Đối tượng đo là **lời gọi phương thức repository đi qua hạ tầng Spring Data được tích hợp**, chẳng hạn `CustomerRepository.findByName(...)`. Một phép đo gồm thời gian thực hiện và kết quả mà hạ tầng đó ghi nhận. Đây là điểm nhìn ở tầng truy cập dữ liệu của ứng dụng.

Bài này dùng Spring Boot **3.3.x**, Spring Data JPA và lời gọi đồng bộ làm ví dụ chính. Các tên cấu hình, lớp tích hợp và cách nhận biết kết quả phải được đối chiếu lại khi đổi dòng phiên bản. Phần thực hành ghim Boot 3.3.0 để xác định rõ môi trường của ví dụ; không dùng số phiên bản đó để suy luận chính sách hỗ trợ hiện tại.

Sau bài này, bạn cần làm được ba việc: xác định điều kiện để có số liệu, tạo một lời gọi rồi tìm đúng bộ số liệu của nó, và giải thích giới hạn của kết luận rút ra từ số liệu.

## 2. Cơ chế tích hợp và ranh giới đo

Luồng khái niệm của phép đo:

```text
Mã gọi repository bean do Spring Data tạo
    → hạ tầng thực thi phương thức Spring Data
    → RepositoryMethodInvocationListener nhận kết quả và thời lượng
    → MetricsRepositoryMethodInvocationListener ghi Timer
    → MeterRegistry
    → Actuator metrics hoặc bộ xuất số liệu
```

`MetricsRepositoryMethodInvocationListener` triển khai điểm mở rộng `RepositoryMethodInvocationListener` của Spring Data. Nó nhận thông tin lời gọi rồi ghi số liệu; đây không phải yêu cầu bạn tự bọc mỗi phương thức bằng đồng hồ đo. Xem [API của listener trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/data/MetricsRepositoryMethodInvocationListener.html).

Điều kiện thực tế cần có là Spring Data repository đã được Spring quản lý, phần Actuator metrics cùng một `MeterRegistry` hoạt động, và cấu hình tự động liên quan không bị loại bỏ hoặc thay thế sai. Chỉ thêm `@Repository` lên một lớp DAO tự viết không biến lớp đó thành Spring Data repository. Một đối tượng do bạn tự `new` cũng không tự nhận tích hợp này.

**Ranh giới này quyết định cách đọc kết quả.** Một phương thức repository có thể thực hiện nhiều truy vấn; một thao tác có thể sử dụng bộ nhớ đệm; một truy vấn có thể dẫn tới công việc tiếp theo khi tải dữ liệu lười. Vì vậy, một lần ghi nhận repository không đồng nghĩa với một câu SQL. Với giao dịch bao ngoài ở service, kết quả phương thức repository cũng không chứng minh giao dịch cuối cùng đã commit.

Ngoài ra, có một Timer không tự chứng minh đã có một span truy vết. Thu thập chỉ số tổng hợp và truy vết một lần thực thi là các yêu cầu riêng; phải kiểm chứng tích hợp tạo observation/span nếu cần truy vết.

## 3. Tên chỉ số, nhãn và loại phép đo

Tên mặc định là `spring.data.repository.invocations`. Các nhãn mặc định cho phép phân biệt repository, phương thức, trạng thái và ngoại lệ. `@Timed` của Micrometer được hỗ trợ trên interface repository hoặc phương thức của interface. Xem [tích hợp Spring Data Repository Metrics trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-data-repository).

| Nhãn | Cách hiểu |
| --- | --- |
| `repository` | Tên đơn giản của interface repository, ví dụ `CustomerRepository` |
| `method` | Tên phương thức, ví dụ `findByName` |
| `state` | Trạng thái Spring Data báo cho lời gọi; các giá trị gồm `SUCCESS`, `ERROR`, `CANCELED`, `RUNNING` |
| `exception` | Tên đơn giản của ngoại lệ được báo; ở mặc định Boot 3.3.0, không có lỗi được biểu diễn bằng `None` |

Chữ hoa/chữ thường có ý nghĩa khi lọc nhãn. Đừng tự đổi `None` thành `none`, hoặc suy ra tên ngoại lệ từ thông báo trả cho người dùng. Ngoại lệ có thể được bọc/chuyển đổi ở tầng khác; hãy xem giá trị thực tế của meter.

Một `Timer` ghi số sự kiện và tổng thời gian; tùy registry và cấu hình, còn có thống kê như thời gian lớn nhất hoặc phân bố. Không cần tạo thêm `Counter` chỉ để đếm lại chính các lần đã được Timer ghi nhận. Xem [Timer](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) và [Counter](https://docs.micrometer.io/micrometer/reference/concepts/counters.html) của Micrometer.

`RUNNING` xuất hiện trong mô hình trạng thái không có nghĩa Timer thông thường là đồng hồ đếm số tác vụ đang chạy. Bài này đọc các lời gọi đồng bộ đã kết thúc; không dùng `COUNT` để suy ra số tác vụ còn hoạt động.

## 4. Ví dụ độc lập: gọi repository rồi đọc MeterRegistry

Ví dụ dùng JDK 21, Gradle 8.5 và H2 trong bộ nhớ. Cần Gradle đã cài; nếu dự án của bạn đã có wrapper thì có thể dùng wrapper tương thích thay lệnh `gradle`. Lần phân giải dependency đầu cần truy cập Maven Central.

Đây là một dự án thực hành riêng. Các tệp Java bên dưới cùng package `demo`; thư mục chứa cấu hình và lớp ứng dụng như sau:

```text
repository-metrics-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── Customer.java
    │   ├── CustomerRepository.java
    │   └── DemoApplication.java
    └── resources/application.properties
```

**`settings.gradle`**

```groovy
rootProject.name = 'repository-metrics-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}
repositories {
    mavenCentral()
}
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
application {
    mainClass = 'demo.DemoApplication'
}
```

BOM của Boot quản lý các phiên bản thư viện. Plugin `application` cung cấp tác vụ `run`; ví dụ không phụ thuộc vào một tác vụ `bootRun` chưa được khai báo.

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:repo_demo;DB_CLOSE_DELAY=-1
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
management.endpoints.web.exposure.include=health,metrics
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
```

Phần exposure cho phép truy cập `metrics` qua HTTP khi chạy chế độ web. Nó không phải công tắc bật phép đo repository. Ví dụ không thêm Spring Security; ứng dụng thật cần giữ cơ chế xác thực và quyền truy cập endpoint phù hợp. Các dòng tắt log chỉ giúp nhìn rõ kết quả thực hành; khi chẩn đoán lỗi khởi động, hãy bỏ `logging.level.root=OFF`.

**`src/main/java/demo/Customer.java`**

```java
package demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }
}
```

**`src/main/java/demo/CustomerRepository.java`**

```java
package demo;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByName(String name);
}
```

**`src/main/java/demo/DemoApplication.java`**

```java
package demo;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner experiment(CustomerRepository repository, MeterRegistry registry) {
        return args -> {
            repository.save(new Customer("Lan"));
            boolean found = repository.findByName("Lan").isPresent();
            boolean missing = repository.findByName("Nobody").isEmpty();

            try {
                repository.findById(null);
                throw new IllegalStateException("Expected invalid id to fail");
            } catch (IllegalArgumentException
                    | org.springframework.dao.InvalidDataAccessApiUsageException expected) {
                // Continue so that the error metric can be inspected.
            }

            System.out.println("FOUND=" + found);
            System.out.println("MISSING=" + missing);
            System.out.println("findByName.SUCCESS="
                    + count(registry, "findByName", "SUCCESS"));
            System.out.println("findById.ERROR="
                    + count(registry, "findById", "ERROR"));
        };
    }

    private static long count(MeterRegistry registry, String method, String state) {
        return registry.find("spring.data.repository.invocations")
                .tags("repository", "CustomerRepository",
                        "method", method, "state", state)
                .timers().stream().mapToLong(Timer::count).sum();
    }
}
```

`save` tạo một khách hàng. Hai lần `findByName` kiểm tra có dữ liệu và không có dữ liệu. `findById(null)` cố ý cung cấp ID không hợp lệ để tạo một lỗi đầu vào, sau đó bắt ngoại lệ để vẫn đọc được meter. Trong mã nghiệp vụ thật, không bắt rồi bỏ qua lỗi theo cách này.

Chạy từ thư mục dự án, với `JAVA_HOME` trỏ tới JDK 21:

```shell
gradle --console=plain run --args="--spring.main.web-application-type=none"
```

Với một lần khởi động mới, cấu hình mặc định của ví dụ và không có lời gọi bổ sung, bốn dòng do chương trình in ra được kỳ vọng là:

```text
FOUND=true
MISSING=true
findByName.SUCCESS=2
findById.ERROR=1
```

Đây là các dòng của ứng dụng, không phải toàn bộ stdout của Gradle. Ví dụ chạy cùng framework và dependency nên không thể chỉ gọi `javac Customer.java` rồi mong có đủ classpath.

Cách giải thích kết quả:

- Hai lần tìm theo tên đều kết thúc bình thường, nên nhóm `findByName/SUCCESS` có số đếm 2. Không tìm thấy bản ghi, thể hiện bằng `Optional.empty()`, không tự trở thành lỗi kỹ thuật.
- Lời gọi với ID null đi vào nhánh lỗi nên nhóm `findById/ERROR` có số đếm 1. Lỗi đầu vào này không chứng minh cơ sở dữ liệu đã nhận một truy vấn hay bị gián đoạn.
- `save` cũng có phép đo riêng, nhưng hàm `count` chỉ chọn các phương thức và trạng thái được truyền vào, nên không cộng `save` vào hai dòng đếm.
- `registry.find(...)` tra cứu meter đã có. Dùng `registry.timer(...)` để “kiểm tra có meter chưa” có thể tự tạo một Timer trống, làm sai mục đích chẩn đoán.

Không ấn định một thời gian chạy chính xác cho ví dụ. JIT, khởi tạo ORM, bộ nhớ đệm và tải máy đều có thể ảnh hưởng thời lượng. Cần so sánh những phép đo trong cùng điều kiện trước khi đánh giá tối ưu hóa.

## 5. Đọc cùng phép đo qua Actuator

Chạy lại ở chế độ web để ứng dụng giữ cổng HTTP mở:

```shell
gradle --console=plain run
```

Ở một terminal khác, đọc danh sách rồi đọc tên meter:

```shell
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/spring.data.repository.invocations
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` đang là alias của một lệnh khác. Để tránh ký tự `&` bị shell xử lý, có thể lọc bằng các tham số được mã hóa riêng:

```shell
curl --get http://localhost:8080/actuator/metrics/spring.data.repository.invocations --data-urlencode "tag=repository:CustomerRepository" --data-urlencode "tag=method:findByName" --data-urlencode "tag=state:SUCCESS"
```

Đọc `measurements` để tìm thống kê `COUNT`; ở phiên chạy sạch của ví dụ, bộ lọc trên cho số đếm 2. Xem `availableTags` trên phản hồi ít bộ lọc hơn để biết các giá trị thực tế, rồi thêm nhãn khi cần phân biệt nhóm ngoại lệ.

Không đọc một phản hồi tổng hợp của mọi repository rồi gán kết quả cho một phương thức. Khi chưa lọc đủ nhãn, nhiều meter có thể cùng khớp. Cũng không dùng tên đã được bộ xuất đổi sang quy ước của Prometheus để gọi endpoint này: ở đây dùng tên gốc có dấu chấm.

Endpoint `metrics` thích hợp cho chẩn đoán tức thời. Để lưu lịch sử, tính tốc độ và dựng cảnh báo, dùng registry/bộ xuất cùng hệ thống giám sát phù hợp; không biến endpoint chẩn đoán này thành kho số liệu lịch sử. Xem [REST API của metrics endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

## 6. Chỉ đo những phương thức cần thiết bằng @Timed

Nếu tự động đo toàn bộ repository không phù hợp, tắt cơ chế tự đo và chọn phương thức bằng annotation. Cấu hình của Boot 3.3 có `management.metrics.data.repository.autotime.enabled`, mặc định là `true`; `management.metrics.data.repository.metric-name` xác định tên mặc định khi tự đo. Xem [bảng thuộc tính Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Trong một lần thực hành riêng, thêm vào `application.properties`:

```properties
management.metrics.data.repository.autotime.enabled=false
```

Thay interface repository bằng bản sau:

```java
package demo;

import java.util.Optional;
import io.micrometer.core.annotation.Timed;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Timed("demo.customer.lookup")
    Optional<Customer> findByName(String name);
}
```

Khởi động một tiến trình mới và gọi như ví dụ trước. Tra cứu meter `demo.customer.lookup`, không tiếp tục tìm phương thức này dưới tên mặc định:

```shell
curl http://localhost:8080/actuator/metrics/demo.customer.lookup
```

Với hai lời gọi tìm tên, số đếm của Timer được chọn là 2. Các phương thức không được chọn bằng `@Timed` không được cơ chế autotime đã tắt tự đo nữa. Vì hàm `count` trong ví dụ gốc đang tra cứu tên `spring.data.repository.invocations`, hai dòng đếm của hàm đó sẽ là 0 trong kịch bản lựa chọn này. Muốn in phép đo mới, đổi tên tra cứu trong hàm sang `demo.customer.lookup`; nhóm `findByName/SUCCESS` sẽ phản ánh hai lần gọi.

Đặt annotation ở nơi tích hợp repository hỗ trợ, như interface/phương thức ở trên. Không suy luận rằng mọi annotation có chữ “Timed” đều tương đương: import ở đây là `io.micrometer.core.annotation.Timed`.

Không cần bổ sung một `TimedAspect` tổng quát chỉ để làm cho ví dụ repository này được đo. Nếu đồng thời dùng một cơ chế AOP đo cùng phương thức, cần kiểm tra có hai phép ghi nhận cho một lần thực thi không. Việc instrument service tùy biến là một phạm vi khác và không được dùng để kết luận rằng tích hợp repository bị thiếu.

Một thay đổi khác, độc lập với kịch bản annotation, là đổi tên tự đo:

```properties
management.metrics.data.repository.metric-name=demo.repository.invocations
```

Khi dùng thay đổi này cùng autotime mặc định, phải đổi tên tra cứu tương ứng. Thuộc tính đổi tên mặc định không phải cam kết đổi tên được chỉ định tường minh trong `@Timed("demo.customer.lookup")`. Đừng bật nhiều biến thể cùng lúc trong lần kiểm tra đầu; hãy xác định cấu hình nào đang có hiệu lực.

## 7. Đọc số liệu để trả lời câu hỏi thực tế

### Số lần gọi tăng có đồng nghĩa nhiều yêu cầu người dùng hơn?

Không nhất thiết. Một yêu cầu có thể gọi repository nhiều lần; tác vụ nền cũng có thể gọi. Nếu một API xử lý 100 yêu cầu nhưng gọi repository 500 lần, hãy kiểm tra vòng lặp, phân trang hoặc các truy vấn phụ trước khi kết luận lưu lượng bên ngoài tăng gấp năm.

Số đếm cộng dồn còn phụ thuộc thời gian sống của tiến trình. So sánh hai instance khởi động ở hai thời điểm khác nhau bằng số đếm tuyệt đối có thể gây hiểu nhầm; để xem tải trong một khoảng, cần tốc độ thay đổi hoặc độ chênh trong cùng cửa sổ thời gian. Khi tiến trình khởi động lại, hệ thống giám sát cần xử lý việc bộ đếm bắt đầu lại.

### Thời gian trung bình được tính thế nào?

Với đúng cùng tập meter, cùng đơn vị và khoảng thu thập có ý nghĩa:

```text
thời gian trung bình = tổng thời gian / số lần được ghi nhận

Ví dụ minh họa:
COUNT = 4
TOTAL_TIME = 0.080 giây
Trung bình = 0.020 giây = 20 ms
```

Đây là phép tính minh họa, không phải thời lượng cam kết của chương trình. Không chia khi số đếm bằng 0. Khi tổng hợp nhiều instance, cộng tổng thời gian và cộng số lần rồi mới chia; trung bình cộng các giá trị trung bình sẽ sai nếu số lời gọi mỗi instance khác nhau. Đồng thời, trung bình không mô tả được các lời gọi chậm hiếm gặp; cần phân bố/histogram phù hợp nếu câu hỏi liên quan đuôi độ trễ.

### SUCCESS có chứng minh toàn bộ nghiệp vụ thành công?

Không. Trong ví dụ, không tìm thấy người dùng vẫn là lần gọi repository kết thúc bình thường. Ứng dụng có thể quyết định “không tìm thấy” là một kết quả nghiệp vụ không đạt yêu cầu, nhưng đó là một phép phân loại khác.

Tương tự, service có thể gọi repository thành công rồi ném ngoại lệ hoặc rollback giao dịch ở bước sau. Nếu muốn đo kết quả của cả nghiệp vụ, phải xác định ranh giới nghiệp vụ đó và instrument riêng; không đổi ý nghĩa nhãn repository theo mong muốn của dashboard.

### ERROR có phải lỗi SQL không?

Không. Lỗi ID null trong ví dụ đã đủ tạo một nhánh lỗi mà không cần kết luận có SQL thất bại. Cần kết hợp nhãn ngoại lệ, log có tương quan, truy vết khi có và dữ liệu từ driver/cơ sở dữ liệu để tìm nguyên nhân. Không đưa thông báo ngoại lệ đầy đủ vào tag để thay cho việc xem log.

## 8. Những giới hạn cần giữ đúng

| Số liệu đang có | Điều có thể kết luận | Điều cần thêm bằng chứng |
| --- | --- | --- |
| Timer của một phương thức repository | Tần suất và thời gian được ghi ở ranh giới repository | Thời gian từng SQL, kế hoạch thực thi, số bản ghi quét |
| Nhãn `state=SUCCESS` | Phần thực thi repository được báo kết thúc bình thường | Toàn bộ service thành công hay giao dịch đã commit |
| Meter `jdbc.connections.*` hoặc `hikaricp.*` | Thông tin tương ứng về kết nối/pool | Phương thức repository nào là nguyên nhân gốc |
| Một chuỗi số liệu tổng hợp | Xu hướng của nhóm lời gọi khớp nhãn | Diễn biến chi tiết của một yêu cầu cụ thể |

Với repository trả `Stream`, kiểu bất đồng bộ hoặc kiểu phản ứng, không mặc định rằng thời điểm trả về đối tượng kết quả là thời điểm mọi công việc đã hoàn tất. Với mô hình phản ứng, còn phải xem đăng ký thực thi, kết thúc, lỗi hoặc hủy. Khi chuyển ví dụ sang một Spring Data store khác, cần kiểm chứng ranh giới listener của đúng phiên bản/store; không áp kết quả đếm của chương trình JPA đồng bộ này sang mọi kiểu trả về.

Những hàm tiện ích mặc định trên interface, lời gọi nội bộ hoặc phần triển khai tùy biến cũng cần được thử ở đúng đường thực thi trước khi cam kết độ bao phủ. Đừng tự đếm số dòng gọi Java trong mã nguồn rồi cho rằng nó chắc chắn bằng `COUNT` của một timer cụ thể.

## 9. Tùy biến nhãn có kiểm soát

Boot cung cấp điểm mở rộng `RepositoryTagsProvider`. Nếu định nghĩa bean thay thế, bạn chịu trách nhiệm trả bộ nhãn phù hợp; nếu còn muốn dùng các nhãn mặc định thì cần chủ động giữ chúng. Xem [API RepositoryTagsProvider](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/data/RepositoryTagsProvider.html).

Một thiết kế dễ quản lý có thể bổ sung một nhãn hữu hạn như miền chức năng với vài giá trị đã biết. Ngược lại, ID khách hàng, email, tên tìm kiếm, chuỗi SQL chứa tham số và thông báo lỗi tự do tạo quá nhiều giá trị tag. Mỗi tổ hợp tag có thể trở thành một chuỗi số liệu riêng, làm tăng chi phí lưu trữ và tài nguyên của hệ thống giám sát. Dữ liệu từng yêu cầu nên được xử lý trong log/tracing theo chính sách dữ liệu tương ứng. Xem [quy tắc đặt tên và giá trị tag của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

`method` mặc định chỉ là tên phương thức, không phải chữ ký đầy đủ. Hai overload cùng tên có thể không được tách chỉ bằng nhãn này; hai repository trùng tên đơn giản ở hai package cũng cần được xem xét khi thiết kế nhãn. Đừng dùng nhãn có độ phân biệt không đủ rồi suy ra số liệu chỉ thuộc một chữ ký/lớp duy nhất.

## 10. Khi không thấy số liệu hoặc số liệu lệch kỳ vọng

Kiểm tra theo thứ tự để phân biệt không có phép đo, không được truy cập endpoint và lọc sai phép đo:

1. **Ứng dụng có khởi động thành công không?** Kiểm tra cấu hình datasource, dependency và log trước khi suy đoán lỗi Actuator.
2. **Đã thật sự gọi repository bean chưa?** Việc chỉ khai báo interface chưa chứng minh đã có một mẫu đo. Tạo một lời gọi có kiểm soát rồi đọc lại.
3. **Đúng Spring Data repository và registry chưa?** Kiểm tra bean thực tế, auto-configuration liên quan và registry mà bạn đang đọc; không đo một đối tượng tự tạo bên ngoài hạ tầng.
4. **Autotime hoặc meter filter có chặn không?** Khi autotime bị tắt, kiểm tra annotation được hỗ trợ và tên metric đã chọn; nếu có `MeterFilter` tùy chỉnh, kiểm tra quy tắc từ chối/đổi tên.
5. **HTTP endpoint đã được expose và truy cập đúng quyền chưa?** Lỗi 401/403 là vấn đề quyền truy cập; không đủ để kết luận timer không tồn tại. Cổng, context path và management base path có thể khác ví dụ.
6. **Tên và nhãn có đúng không?** Xem tên gốc và `availableTags`; kiểm tra `SUCCESS`, `ERROR`, tên repository, tên phương thức và ngoại lệ thực tế. Lọc sai tập nhãn có thể cho kết quả trống.
7. **Có lời gọi ngoài dự kiến không?** Runner, seed dữ liệu, kiểm tra khởi động, tác vụ lịch hoặc kiểm thử khác đều có thể gọi repository. So sánh độ chênh trước/sau trên cùng tập nhãn thay vì chỉ nhìn một tổng số.
8. **Có đo chồng không?** Kiểm tra timer thủ công, aspect tùy biến và annotation bổ sung trước khi kết luận Spring Data tự đếm hai lần.

Không sửa lỗi bằng cách expose toàn bộ endpoint, tạo thêm timer có cùng ý nghĩa hoặc bỏ mọi nhãn để che kết quả khác kỳ vọng. Trước hết xác định phép đo nào đang được ghi và đường gọi nào tạo ra nó.

## 11. Thực hành tự kiểm chứng

Thực hiện từng tình huống trên một tiến trình mới hoặc ghi số liệu trước/sau để tránh trộn kết quả:

| Tình huống | Thao tác | Kỳ vọng cần kiểm chứng |
| --- | --- | --- |
| Mặc định | Giữ nguyên ví dụ, không có annotation | Hai lời gọi tìm tên thuộc nhóm SUCCESS; lỗi ID null thuộc nhóm ERROR |
| Không có bản ghi | Tìm một tên không tồn tại | `Optional.empty()` nhưng lời gọi hoàn tất bình thường |
| Chỉ đo được chọn | Tắt autotime, thêm `@Timed("demo.customer.lookup")` | Có timer được chọn; không trông chờ các lời gọi không được chọn ở tên mặc định |
| Đổi tên tự đo | Dùng cấu hình metric-name, không dùng biến thể annotation | Tra cứu tên mới thay vì tên mặc định |
| Không expose metrics | Bỏ metrics khỏi exposure nhưng vẫn gọi repository | Phân biệt được phép đo trong registry với khả năng truy cập nó qua HTTP |

Khi trình bày kết quả, ghi rõ phiên bản, cấu hình, tên meter, bộ nhãn và số lời gọi thực sự tạo ra. Một kết luận tốt phải trả lời được: “số liệu này đại diện cho đoạn thực thi nào, và bằng chứng nào còn thiếu để khẳng định nguyên nhân chậm hoặc lỗi?”.
