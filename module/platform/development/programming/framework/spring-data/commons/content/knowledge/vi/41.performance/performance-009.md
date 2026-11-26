# Đo thời gian khởi tạo repository, parser và metadata

## Mục tiêu và phạm vi

Thời gian khởi động một ứng dụng Spring Data không chỉ là thời gian tạo repository proxy. Nó còn có thể bao gồm class loading, quét cấu hình, khởi tạo mapping, tạo hạ tầng store, kết nối backend và kiểm tra các phương thức truy vấn.

Khi thấy ứng dụng khởi động chậm, câu hỏi “repository mất bao lâu?” cần được chuyển thành các phạm vi đo cụ thể.

Sau bài học này, bạn có thể:

- Phân biệt startup toàn ứng dụng, khởi tạo repository và lần gọi đầu tiên.
- Nhận diện vai trò của parser derived query và các loại metadata.
- Chọn công cụ quan sát phù hợp với từng phạm vi.
- Thiết kế microbenchmark cho PartTree và RepositoryMetadata.
- Tránh nhầm cache nóng, JIT hoặc thời gian truy cập store với chi phí parser.
- Đề xuất thay đổi dựa trên số đo thay vì suy luận từ số lượng repository.

Bài thuộc phạm vi Spring Data Commons. Các ví dụ JPA hoặc Spring Boot chỉ minh họa phần tích hợp; thời điểm tạo query và mapping cụ thể phụ thuộc module, phiên bản và cấu hình thực tế.

## 1. Tách các phạm vi trước khi bấm đồng hồ

| Phạm vi | Câu hỏi đo | Những việc có thể nằm trong phạm vi |
|---|---|---|
| Tiến trình khởi động | Từ lúc hệ điều hành khởi chạy tới mốc đã chọn mất bao lâu? | Khởi động JVM, class loading, framework, hạ tầng store |
| Application context | Context refresh mất bao lâu? | Tạo bean, dependency, callback và công việc trong vòng đời context |
| Khởi tạo repository | Một nhóm repository sẵn sàng theo cấu hình khi nào? | Factory, metadata, proxy, fragment và query lookup |
| Lần dùng đầu | Request đầu dùng repository mất bao lâu? | Công việc bị trì hoãn, query đầu, kết nối và I/O |
| Parser riêng | Tạo mô hình derived query cho một method name mất bao lâu? | PartTree, phân tích property path và cấu trúc điều kiện |
| Metadata riêng | Phân tích interface hoặc mô hình domain mất bao lâu? | Generic type, thông tin repository hoặc mapping tùy loại metadata |
| Trạng thái ổn định | Các lần dùng sau có chi phí như thế nào? | Cache, mã đã JIT, connection pool đã hoạt động |

Một số phạm vi lồng nhau hoặc có thể chạy song song. Không cộng các thời gian con một cách máy móc rồi coi đó là tổng startup.

Ví dụ:

```text
startup chậm
    |
    +-- EntityManagerFactory khởi tạo lâu
    |
    +-- repository phụ thuộc vào EntityManagerFactory
```

Một span tạo repository có thể bao gồm thời gian chờ dependency. Điều đó chưa chứng minh parser của repository đang tiêu tốn CPU trong toàn bộ khoảng đó.

## 2. Hiểu đường đi khởi tạo ở mức khái niệm

Một đường đi thường gặp:

```text
Đọc cấu hình và tìm repository interface
    |
Xác định module store và domain type
    |
Khởi tạo hạ tầng store cần thiết
    |
Tạo repository factory, metadata và các thành phần liên quan
    |
Ghép implementation cơ sở, fragment và proxy
    |
Tra cứu hoặc chuẩn bị query method theo chiến lược của module
    |
Repository được sử dụng
```

Đây là mô hình để đặt câu hỏi, không phải thứ tự bắt buộc của mọi implementation.

Một số bước có thể:

- Được thực hiện sớm khi tạo context.
- Chỉ xảy ra khi bean được yêu cầu.
- Được trì hoãn tới lần gọi phương thức.
- Sử dụng kết quả đã cache.
- Chạy sau khi hạ tầng store được tạo bất đồng bộ.

Vì vậy, cần quan sát vòng đời thực tế của ứng dụng đang đo. Không suy rằng mọi derived query luôn được parse lại ở mỗi request, hoặc mọi metadata chỉ được tạo đúng một lần trên toàn tiến trình.

## 3. Parser đang làm gì và không làm gì?

Với derived query:

```java
findByEmail
findByAddress_CityAndActiveTrueOrderByIdDesc
findTop20ByActiveTrueOrderByIdDesc
```

Commons có các abstraction hỗ trợ phân tích tên phương thức, trong đó PartTree biểu diễn cấu trúc như:

- Chủ thể của truy vấn.
- Các phần điều kiện và toán tử.
- Đường dẫn property.
- Thông tin giới hạn hoặc distinct khi cú pháp hỗ trợ.
- Sort tĩnh trong tên phương thức.

Kết quả parser chưa phải toàn bộ công việc thực thi query.

Module store còn phải chuyển ý nghĩa đó thành truy vấn phù hợp với backend, mapping tham số và kiểu kết quả.

```text
Tên phương thức
    -> mô hình PartTree
    -> query của module store
    -> driver/backend thực thi
    -> mapping kết quả
```

Đo `new PartTree(...)` không đo:

- Khởi tạo Spring context.
- Tạo một repository proxy hoàn chỉnh.
- Khởi tạo connection pool.
- Tạo SQL hoặc truy vấn backend của mọi module.
- Thực thi truy vấn.
- Projection, serialization hoặc I/O đầu ra.

Nếu một method dùng query khai báo, named query hoặc fragment tùy biến, đường chuẩn bị query có thể khác derived query. Không gộp mọi chi phí query lookup thành chi phí PartTree.

## 4. Metadata không phải một loại dữ liệu duy nhất

| Loại thông tin | Ví dụ câu hỏi |
|---|---|
| RepositoryMetadata | Domain type là gì? ID type là gì? Interface repository nào đang được mô tả? |
| RepositoryInformation | Những method nào thuộc repository và liên quan tới implementation như thế nào? |
| Query method metadata | Kiểu trả về, tham số đặc biệt, projection hoặc annotation của method là gì? |
| Persistent entity/property metadata | Domain có những property nào? ID, version, auditing và mapping được xác định ra sao? |
| Store-specific metadata | Entity gắn với bảng, collection hoặc cơ chế lưu trữ nào? |

Các lớp thông tin có liên hệ nhưng không thể thay thế nhau.

Chẳng hạn, lấy RepositoryMetadata để biết `Customer` và `Long` không đồng nghĩa đã xây xong toàn bộ mapping JPA của Customer.

Tương tự, xác định property auditing trong mapping không có nghĩa ứng dụng đã gọi auditor, ghi thời điểm hoặc thực hiện một lần lưu.

Khi báo số đo, hãy dùng tên đủ cụ thể:

```text
Thời gian tạo RepositoryMetadata cho một interface
```

chính xác hơn:

```text
Thời gian khởi tạo toàn bộ metadata Spring Data
```

## 5. Đo một mốc startup trong ứng dụng

Có thể bắt đầu bằng một mốc rõ ràng trong Spring Boot:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

public class Application {

    public static void main(String[] args) {
        long startedAt = System.nanoTime();

        SpringApplication application =
                new SpringApplication(ApplicationConfiguration.class);

        application.addListeners(
                (ApplicationListener<ApplicationReadyEvent>) event -> {
                    long elapsed = System.nanoTime() - startedAt;

                    System.out.printf(
                            "startup.ready.ms=%.3f%n",
                            elapsed / 1_000_000.0);
                });

        application.run(args);
    }
}
```

Đoạn mã giả định `ApplicationConfiguration` là cấu hình ứng dụng đã có.

Phép đo này có ý nghĩa:

> Thời gian từ mốc trong main tới lúc listener nhận ApplicationReadyEvent.

Nó không bao gồm toàn bộ thời gian khởi chạy JVM trước khi vào main. Nó cũng không tự chứng minh mọi repository lazy hoặc mọi đường query đã được dùng.

Nếu chạy ứng dụng có nhiều context hoặc event, cần bảo đảm listener chỉ ghi mốc thuộc ứng dụng đang đo.

Dùng `System.nanoTime()` để đo khoảng thời gian trong cùng tiến trình. Không lấy chênh lệch các timestamp từ nhiều máy rồi mặc định đó là thời gian xử lý chính xác.

### Khi cần mốc bên ngoài tiến trình

Có thể dùng công cụ chạy thử để đo từ lúc tạo process tới khi readiness theo hợp đồng được đáp ứng. Khi đó cần ghi rõ:

- Readiness được xác định bằng gì.
- Có chờ backend hoặc dữ liệu chuẩn bị không.
- Có tính thời gian khởi động container và tải image không.
- Có request kiểm tra nào vô tình làm nóng repository trước khi ghi nhận readiness không.

Mốc bên ngoài tiến trình và mốc ApplicationReadyEvent trả lời hai câu hỏi khác nhau.

## 6. Quan sát startup bằng ApplicationStartup

Spring Framework có cơ chế ghi nhận các bước startup. Trong Spring Boot, một lựa chọn để thu thập timeline là BufferingApplicationStartup.

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ApplicationConfiguration.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(4096));

        application.run(args);
    }
}
```

Số 4096 là dung lượng buffer minh họa. Cần chọn phù hợp số lượng bước của ứng dụng và kiểm tra dữ liệu có bị thiếu do giới hạn buffer hay không.

Nếu ứng dụng có Spring Boot Actuator, có thể dùng khả năng startup endpoint khi được cấu hình và truy cập theo cơ chế quản trị của dự án. Chỉ đặt ApplicationStartup không có nghĩa mọi endpoint quan sát đã tự được bật.

Khi đọc timeline, cần phân biệt:

- Bước tạo bean repository.
- Bước tạo dependency của repository.
- Thời gian chờ.
- Thời gian của bước cha và bước con.
- Các bước chồng lấp vì thực thi song song.

Tên step và mức chi tiết phụ thuộc phiên bản cùng các thành phần có instrumentation. Không mặc định timeline luôn có một step riêng cho từng lần PartTree được tạo.

Một bước dài chỉ là điểm bắt đầu để điều tra. Muốn kết luận CPU đang ở parser, cần thêm bằng chứng như profile stack hoặc benchmark có phạm vi phù hợp.

## 7. Dùng JFR để hiểu CPU, allocation và thời gian chờ

Java Flight Recorder có thể giúp phân biệt:

- CPU thực sự dùng để phân tích metadata.
- Class loading và initialization.
- Allocation và garbage collection.
- Lock hoặc thời gian thread chờ.
- Hoạt động I/O có được recording thu thập.
- Tương tác với startup step khi dùng tích hợp phù hợp.

Spring có FlightRecorderApplicationStartup cho cách ghi nhận startup qua JFR. Đây là một lựa chọn cấu hình ApplicationStartup khác với ví dụ buffer; cần chọn và cấu hình theo mục tiêu đo.

Một lệnh minh họa khi môi trường đã có JDK hỗ trợ:

```text
java -XX:StartFlightRecording=filename=repository-startup.jfr,settings=profile,dumponexit=true -jar application.jar
```

Lệnh này chỉ minh họa cách chạy một phiên đo; bài không cung cấp kết quả recording đã thực hiện.

Cần bảo đảm recording bắt đầu đủ sớm và kết thúc sau các mốc muốn quan sát. Một profile chỉ bắt đầu sau khi ứng dụng đã sẵn sàng sẽ không phản ánh startup trước đó.

### Đọc profile theo giả thuyết

Nếu repository bean mất nhiều thời gian nhưng stack cho thấy phần lớn đang chờ kết nối hoặc khởi tạo provider, tối ưu tên derived query khó giải quyết vấn đề chính.

Nếu allocation tập trung ở phân tích type hoặc property path, mới cần khoanh vùng metadata, cache hoặc số lượng cấu trúc được tạo.

Sampling profile có giới hạn độ phân giải. Một thao tác rất ngắn có thể khó quan sát riêng lẻ; microbenchmark phù hợp hơn cho câu hỏi hẹp đó.

## 8. Đo bean lookup và lần gọi đầu tiên riêng nhau

Trong một môi trường đo đã cấu hình context và store, có thể tách hai mốc:

```java
long lookupStarted = System.nanoTime();

ApplicationCustomerRepository repository =
        context.getBean(ApplicationCustomerRepository.class);

long lookupNanos = System.nanoTime() - lookupStarted;

long firstCallStarted = System.nanoTime();

repository.findByEmail("benchmark@example.invalid");

long firstCallNanos = System.nanoTime() - firstCallStarted;
```

Đoạn mã giả định:

- `context` là context đã tạo theo cấu hình cần đo.
- Repository có query method tương ứng.
- Backend kiểm thử và dữ liệu được kiểm soát.
- Kết quả và lỗi được kiểm tra, không bỏ qua lỗi để coi là thành công.

Hai phép đo không có cùng phạm vi:

| Mốc | Có thể bao gồm |
|---|---|
| getBean | Lookup bean, tạo bean nếu chưa có hoặc trả một proxy |
| Lần query đầu | Khởi tạo bị trì hoãn, chuẩn bị query, lấy connection, truy vấn và mapping |

Với lazy proxy, getBean có thể trả nhanh nhưng chưa kích hoạt toàn bộ phần đích. Vì vậy, không dùng thời gian getBean làm bằng chứng repository đã hoàn toàn sẵn sàng.

Lần gọi đầu cũng không phải phép đo parser riêng, vì nó có I/O và nhiều lớp khác.

Sau đó có thể đo các lần gọi cùng query trên trạng thái đã hoạt động để thấy mức chi phí chuyển từ startup sang request đầu. Không lấy “lần đầu trừ lần sau” rồi gọi toàn bộ chênh lệch là parser; chênh lệch còn có thể do JIT, cache, kết nối và backend.

## 9. Microbenchmark PartTree và RepositoryMetadata bằng JMH

Đối với thao tác ngắn trong JVM, JMH giúp quản lý warmup, iteration, fork và việc tiêu thụ kết quả.

Ví dụ sau cần thư viện JMH và annotation processing được cấu hình trong môi trường benchmark. Đây là mã minh họa, không phải cấu hình build hay kết quả benchmark đã chạy.

```java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

import org.springframework.data.repository.Repository;
import org.springframework.data.repository.core.RepositoryMetadata;
import org.springframework.data.repository.core.support.AbstractRepositoryMetadata;
import org.springframework.data.repository.query.parser.PartTree;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class RepositoryPlanningBenchmark {

    @State(Scope.Thread)
    public static class ParserInput {

        @Param({
                "findByEmail",
                "findByAddress_CityAndActiveTrueOrderByIdDesc",
                "findTop20ByActiveTrueOrderByIdDesc"
        })
        public String methodName;
    }

    @Benchmark
    public PartTree buildPartTree(ParserInput input) {
        return new PartTree(input.methodName, Customer.class);
    }

    @Benchmark
    public RepositoryMetadata inspectRepositoryInterface() {
        return AbstractRepositoryMetadata.getMetadata(
                CustomerRepository.class);
    }

    public interface CustomerRepository
            extends Repository<Customer, Long> {

        Optional<Customer> findByEmail(String email);

        List<Customer>
                findByAddress_CityAndActiveTrueOrderByIdDesc(
                        String city);
    }

    public static class Customer {

        private Long id;
        private String email;
        private boolean active;
        private Address address;

        public Long getId() {
            return id;
        }

        public String getEmail() {
            return email;
        }

        public boolean isActive() {
            return active;
        }

        public Address getAddress() {
            return address;
        }
    }

    public static class Address {

        private String city;

        public String getCity() {
            return city;
        }
    }
}
```

Domain trong benchmark chỉ cần phục vụ type/property inspection của Commons. Nó không được cấu hình như một entity của một store.

### Phép đo này trả lời gì?

`buildPartTree` đo việc tạo PartTree lặp lại cho một tên method và domain type trong điều kiện benchmark.

`inspectRepositoryInterface` đo việc lấy RepositoryMetadata qua API được gọi trong benchmark. Nó không tạo repository implementation hoặc proxy đầy đủ.

Kết quả được trả ra để harness JMH tiêu thụ. Không bỏ kết quả vào một biến không dùng rồi tự chạy vòng lặp lớn bằng đồng hồ thủ công.

### Vì sao dùng state riêng cho parser?

Danh sách method name chỉ ảnh hưởng benchmark parser. Benchmark metadata không bị lặp thành nhiều tổ hợp tham số không liên quan, giúp kết quả dễ diễn giải hơn.

Các query name đều trỏ tới property có thật. Một lỗi đánh máy gây exception không nên bị lẫn vào phép đo đường parse thành công.

## 10. Benchmark đã warm không phải startup lạnh

Trong ví dụ JMH:

- Các class đã được tham chiếu trong quá trình chạy.
- JIT có thời gian tối ưu.
- Cache liên quan đến type hoặc property có thể đã được làm nóng.
- Cùng một nhóm method name được dùng nhiều lần.

Do đó, kết quả không đại diện cho toàn bộ chi phí gặp một domain type lần đầu trong một JVM mới.

Có thể phân biệt:

| Thí nghiệm | Mục tiêu |
|---|---|
| Lặp tạo PartTree cho cùng type | Chi phí lặp ở trạng thái đã hoạt động |
| Lấy lại metadata từ hạ tầng có cache | Chi phí lookup trong phạm vi cache đó |
| Mỗi lần chạy ứng dụng bằng process mới | Startup của JVM và ứng dụng theo mốc đã chọn |
| Lần gọi repository đầu sau readiness | Chi phí mà client đầu tiên có thể phải chịu |
| Nhiều domain/method khác nhau | Ảnh hưởng của kích thước và độ đa dạng mô hình |

Một process mới tạo điều kiện tốt hơn để khảo sát trạng thái JVM mới, nhưng cache hệ điều hành, file và backend vẫn có thể nóng.

Tạo classloader mới cũng không tự xóa mọi cache của JVM hay backend. Nó còn bổ sung chi phí và vấn đề vòng đời classloader, nên không được coi là cách mô phỏng startup lạnh một cách tự động.

Nếu dùng chế độ single-shot hoặc thay đổi warmup của JMH, hãy ghi rõ phạm vi còn được harness chuẩn bị trước phép đo. Không đổi tên kết quả thành “cold startup” chỉ vì bỏ warmup.

## 11. Đo mapping metadata trong đúng context của store

RepositoryMetadata không thay thế persistent entity metadata.

Để khảo sát mapping, cần dùng mapping context thực sự của module đang đo và xác định:

1. Domain đã được đăng ký hoặc khởi tạo trước đó chưa?
2. Lần lấy entity metadata là lần tạo mới hay lookup lại?
3. Mapping context đã khởi tạo toàn bộ domain từ trước chưa?
4. Có callback hoặc store infrastructure nào chạy cùng thời điểm không?
5. Có dependency nào đang bị trì hoãn và bị kích hoạt bởi phép đo không?

Ví dụ về hai phạm vi khác nhau:

```text
A. Context refresh đã khởi tạo mapping.
   Sau đó đo getPersistentEntity.
   -> chủ yếu quan sát đường lấy thông tin đã có.

B. Đo giai đoạn mapping context lần đầu nhận domain.
   -> có thể gồm introspection và xây mô hình property.
```

Không báo A như thể đã đo B.

Với JPA, việc tạo metamodel của provider còn nằm trong hạ tầng JPA. Không mặc định thời gian tạo EntityManagerFactory bằng thời gian metadata của Commons.

Với auditing, projection hoặc custom conversion, metadata có thể phát sinh thêm nhu cầu xử lý. Cần so sánh mô hình thực tế thay vì chỉ benchmark một POJO rất nhỏ rồi suy rộng cho mọi domain.

## 12. Bootstrap mode có thể chuyển chi phí sang mốc khác

Một số module cung cấp cách điều khiển thời điểm khởi tạo repository. Trong Spring Data JPA, có thể gặp các chế độ DEFAULT, LAZY và DEFERRED.

Ví dụ cấu hình JPA minh họa:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.config.BootstrapMode;

@Configuration
@EnableJpaRepositories(
        basePackages = "example.customer.persistence",
        bootstrapMode = BootstrapMode.DEFERRED)
public class CustomerRepositoryConfiguration {
}
```

Cần đặt cấu hình này trong hạ tầng JPA phù hợp, không thêm một nhóm scan trùng với cấu hình đang tồn tại.

Ý nghĩa cần xem xét:

| Chế độ hoặc cách khởi tạo | Điều cần quan sát |
|---|---|
| Khởi tạo sớm theo cấu hình thông thường | Bao nhiêu công việc được làm trước mốc startup đã chọn? |
| Lazy | Công việc nào bị dời tới lần sử dụng đầu? |
| Deferred của JPA | Việc khởi tạo được phối hợp với vòng đời context/hạ tầng JPA như thế nào? |

DEFERRED của JPA không đơn giản là bỏ qua mọi kiểm tra tới một request bất kỳ; nó gắn việc khởi tạo repository với giai đoạn vòng đời phù hợp để hoàn tất việc khởi tạo/kiểm tra trong quá trình startup.

Chi tiết và tương tác với cấu hình khác cần được xác minh trong module và phiên bản của dự án.

Khi so sánh, hãy đo ít nhất:

- Mốc startup.
- Mốc repository đã thực sự được khởi tạo.
- Lần dùng đầu.
- Thời điểm lỗi cấu hình được phát hiện.

Startup ngắn hơn nhưng request đầu chậm hơn có thể là chuyển chi phí, không phải loại bỏ chi phí.

Global lazy initialization của ứng dụng và bootstrap mode của repository cũng không phải cùng một cơ chế.

## 13. Thiết kế thí nghiệm để tìm nguyên nhân

Thay đổi một yếu tố mỗi lần giúp kết quả có thể giải thích.

| Yếu tố | Cách so sánh có chủ đích |
|---|---|
| Số repository | Cùng kiểu domain/query, tăng số interface thật sự cần tạo |
| Số query method | Giữ hạ tầng store ổn định, thay số method cần chuẩn bị |
| Cấu trúc method name | Property đơn, property lồng, nhiều điều kiện, sort tĩnh |
| Mô hình domain | Domain nhỏ so với mô hình nhiều property và quan hệ |
| Fragment | Có hoặc không có implementation tùy biến tương ứng |
| Query lookup | Derived query và query khai báo trong cùng phạm vi phù hợp |
| Cache | Lần đầu và lần lấy lại trong cùng context |
| Bootstrap | Cùng cấu hình dữ liệu, đổi thời điểm khởi tạo |
| Môi trường | Giữ JDK, tài nguyên và backend nhất quán giữa các mẫu |

Tên method dài hơn không tự chứng minh thời gian tăng tuyến tính theo số ký tự. Đường dẫn property, kiểu domain, lookup và cache cũng ảnh hưởng.

Dùng query khai báo không tự bảo đảm startup nhanh hơn derived query. Module hoặc provider có thể kiểm tra query khai báo và làm những công việc khác.

Nếu tạo nhiều interface hoặc class tổng hợp cho thí nghiệm, cần nêu rõ chúng là mô hình thử, không phải workload production đã được đo.

## 14. Kiểm soát môi trường và nhiễu phép đo

Các thông tin tối thiểu nên được giữ hoặc ghi lại:

- JDK và chế độ JVM.
- Phiên bản Spring Data, Spring Framework và module store.
- Số repository, domain và query method.
- Cấu hình scan.
- Bootstrap hoặc lazy configuration.
- Backend cùng trạng thái dữ liệu.
- Giới hạn CPU, bộ nhớ và hoạt động cạnh tranh.
- Cơ chế quan sát được bật.
- Mốc bắt đầu và kết thúc của từng phép đo.

Các nguồn nhiễu thường gặp:

| Nguồn nhiễu | Có thể làm sai diễn giải |
|---|---|
| Tải dependency hoặc image trong lần chạy đầu | Bị tính nhầm vào thời gian ứng dụng |
| DNS, TLS và connection pool | Bị tính nhầm thành parser hoặc metadata |
| Tạo schema/migration | Bị quy cho repository vì xảy ra trước khi repository sẵn sàng |
| JIT và class loading | Làm lần đầu khác nhiều lần sau |
| Cache backend và hệ điều hành | Làm “process mới” vẫn chưa phải mọi tầng đều lạnh |
| Debugger hoặc log rất chi tiết | Tăng thời gian và thay đổi phân bố |
| Profiling hoặc instrumentation | Có overhead cần hiểu khi so sánh |
| Context kiểm thử được tái sử dụng | Che mất chi phí khởi tạo mà test tưởng đang đo |

Không dùng một vòng lặp lấy cùng bean từ cùng context để kết luận thời gian tạo repository mới. Sau lần tạo đầu, thao tác đó có thể chỉ là lookup bean đã có.

## 15. Đọc số đo và báo cáo đúng giới hạn

Không chỉ báo một số nhỏ nhất từ một lần chạy.

Với startup process, nên có nhiều lần chạy độc lập và trình bày phân bố hoặc các mốc thống kê phù hợp. Với JMH, giữ kết quả theo fork, sai số và đơn vị của phép đo.

Một mẫu báo cáo có thể gồm:

| Trường | Nội dung cần ghi |
|---|---|
| Mục tiêu | Startup toàn ứng dụng hay thao tác Commons cụ thể |
| Phạm vi | Mốc bắt đầu/kết thúc hoặc API được benchmark |
| Điều kiện | Phiên bản, cấu hình và workload |
| Trạng thái | Process mới, context mới hay cache đã nóng |
| Kết quả | Số đo, đơn vị, số mẫu và biến thiên |
| Phân tích | Bằng chứng cho phần chi phí chi phối |
| Giới hạn | Những gì chưa được phép đo xác minh |

Ví dụ cách diễn đạt đúng:

> Benchmark này đo tạo PartTree lặp lại trên ba method name với cùng domain type sau warmup. Nó không đo thời gian tạo repository proxy hoặc khởi động ứng dụng.

Không dùng một microbenchmark rất ngắn để nhân với số method rồi khẳng định đó là tổng startup. Trong ứng dụng thật, cache, dependency dùng chung, class loading và hoạt động song song khiến phép nhân đó có thể sai.

Tương tự, một thay đổi vài phần trăm nhưng nằm trong biến thiên giữa các lần chạy chưa đủ để kết luận đã cải thiện.

## 16. Tối ưu sau khi đã xác định phần chi phí chi phối

Một số hướng xem xét theo bằng chứng:

| Kết quả quan sát | Hướng cần đánh giá |
|---|---|
| Scan quá rộng hoặc tạo repository không dùng | Giới hạn phạm vi cấu hình và loại bỏ đăng ký không cần |
| Hạ tầng store hoặc migration chi phối | Điều tra phần đó thay vì chỉ sửa parser |
| Khởi tạo repository sớm chi phối nhưng không phải đường cần ngay | Đánh giá bootstrap/lazy cùng request đầu và thời điểm phát hiện lỗi |
| Mapping mô hình lớn chi phối | Kiểm tra số domain, metadata mở rộng và phạm vi thực sự cần |
| Property/type inspection bị thực hiện lặp ngoài dự kiến | Xem vòng đời object và cách dùng hạ tầng hiện có |
| Công việc bị lặp do nhiều context | Xác định context nào thật sự cần cùng nhóm repository |

Một generic base repository không phải repository độc lập có thể cần được đánh dấu hoặc tổ chức đúng theo cơ chế framework, chẳng hạn dùng NoRepositoryBean khi phù hợp. Không gắn annotation đó lên repository thật chỉ để làm số startup giảm rồi vô tình mất bean cần thiết.

Không tự thêm một static cache giữ Class hoặc metadata vô hạn để cải thiện microbenchmark. Cách làm đó có thể gây vấn đề classloader, vòng đời, bộ nhớ và tính đúng của cấu hình.

AOT hoặc native image cũng có thể chuyển một phần công việc sang thời điểm build. Khi so sánh, cần nêu rõ mô hình thực thi và mốc đo; không coi mọi chi phí đã biến mất chỉ vì không còn xuất hiện tại cùng một thời điểm runtime.

## 17. Các kết luận dễ sai

| Kết luận | Vì sao chưa đủ cơ sở? |
|---|---|
| Repository bean mất lâu nên PartTree chậm | Thời gian có thể nằm ở dependency hoặc chờ I/O |
| getBean rất nhanh nên repository đã khởi tạo đầy đủ | Có thể chỉ trả lazy proxy |
| Lần query đầu chậm hơn nên chênh lệch là parser | Còn JIT, connection, backend và mapping |
| Tạo RepositoryMetadata bằng tạo toàn bộ mapping | Hai phạm vi metadata khác nhau |
| JMH sau warmup bằng startup lạnh | Điều kiện cache và JVM khác nhau |
| Đổi sang lazy đã loại bỏ chi phí | Có thể chuyển chi phí sang request đầu |
| Cộng mọi startup step là tổng startup | Step có thể lồng nhau hoặc chồng lấp |
| Một lần chạy nhanh hơn là đã tối ưu | Chưa xét biến thiên và điều kiện môi trường |
| Query khai báo luôn khởi tạo nhanh hơn derived query | Query lookup và validation của store có chi phí riêng |
| Đo parser là đã đo được hiệu năng truy vấn | Parser không thực thi backend |

Một kết luận tốt cần khớp với phạm vi phép đo và có bằng chứng từ đúng lớp xử lý.

## 18. Bài thực hành

Với một ứng dụng Spring Data có cấu hình kiểm thử riêng:

1. Định nghĩa mốc startup muốn đo và ghi rõ có tính JVM startup hay không.
2. Thu thập timeline tạo context và các dependency quan trọng của repository.
3. Đo lookup bean và query đầu như hai phạm vi khác nhau.
4. Chạy một microbenchmark PartTree với property đơn và property lồng.
5. Đo RepositoryMetadata riêng, không gộp với mapping của store.
6. So sánh lần truy cập metadata đầu và lần lấy lại trong cùng vòng đời.
7. Nếu module có bootstrap mode, đo cả readiness và first use khi thay đổi chế độ.
8. Kiểm tra profile để phân biệt CPU, allocation và thời gian chờ.
9. Ghi lại số mẫu, biến thiên và điều kiện cache.
10. Đưa ra một đề xuất chỉ nhắm vào phần chi phí đã có bằng chứng.

Các đoạn mã và công cụ trong bài phục vụ thiết kế phép đo. Bài không khẳng định đã chạy benchmark hoặc cung cấp con số hiệu năng thực tế cho một dự án cụ thể.

## 19. Những điều cần nắm vững

Đo startup repository cần bắt đầu từ phạm vi rõ ràng. Tạo context, tạo proxy, parse derived query, xây metadata và gọi backend lần đầu là những công việc khác nhau.

Timeline và JFR giúp khoanh vùng chi phí trong ứng dụng thật. JMH phù hợp cho một thao tác JVM hẹp như tạo PartTree hoặc lấy RepositoryMetadata trong điều kiện được kiểm soát.

Hãy báo đúng điều đã đo, phân biệt trạng thái mới với trạng thái đã nóng và kiểm tra nơi chi phí được chuyển đến khi thay đổi bootstrap. Tối ưu có ý nghĩa khi cải thiện mốc mà ứng dụng và người dùng thực sự cần.
