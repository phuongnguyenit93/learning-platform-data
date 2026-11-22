# Quản lý tài nguyên theo vòng đời ứng dụng

Một ứng dụng Spring Boot không chỉ tạo object rồi sử dụng chúng. Trong quá trình chạy, ứng dụng còn mở kết nối database, tạo HTTP client, khởi động thread pool, lên lịch công việc, mở file, đăng ký listener và giữ những tài nguyên cần được giải phóng khi dừng.

Nếu một tài nguyên được tạo mà không được đóng đúng lúc, ứng dụng có thể gặp:

- Connection hoặc file handle bị rò rỉ.
- Thread nền tiếp tục chạy sau khi context đã đóng.
- JVM không thoát vì executor còn thread hoạt động.
- Request mới được nhận trong lúc ứng dụng đang shutdown.
- Dữ liệu chưa được flush hoặc công việc đang xử lý bị bỏ dở.
- Một bean đóng tài nguyên mà bean khác vẫn đang dùng.

Spring quản lý vòng đời của các bean trong ApplicationContext và cung cấp callback để khởi tạo, dừng hoặc giải phóng tài nguyên. Tuy nhiên, **container chỉ quản lý đúng những tài nguyên mà ứng dụng giao quyền sở hữu cho nó**. Một file stream được mở cục bộ trong method vẫn cần try-with-resources; một executor sống suốt thời gian ứng dụng chạy cần lifecycle rõ ràng; một prototype bean có thể không được Spring tự gọi destroy callback.

Bài học tập trung vào nguyên tắc **resource ownership**, các giai đoạn tạo/hủy bean, **@PostConstruct**, **@PreDestroy**, **initMethod**, **destroyMethod**, **AutoCloseable**, singleton/prototype/scoped beans, **Lifecycle/SmartLifecycle**, graceful shutdown và cách kiểm thử việc giải phóng tài nguyên.

## 1. Vòng đời ứng dụng và vòng đời tài nguyên

Một tài nguyên có thể tồn tại trong một phạm vi rất ngắn hoặc gần bằng toàn bộ thời gian sống của process:

| Tài nguyên | Phạm vi thường gặp | Cách quản lý phù hợp |
|---|---|---|
| InputStream đọc một file | Trong một method | try-with-resources |
| JDBC Connection lấy từ pool | Trong một transaction/operation | Để transaction manager hoặc code sở hữu connection đóng đúng lúc |
| DataSource connection pool | Vòng đời ứng dụng | Bean/container lifecycle |
| HTTP client dùng chung | Vòng đời ứng dụng | Bean có close/shutdown callback |
| ScheduledExecutorService | Vòng đời ứng dụng | Bean quản lý start/stop/destroy |
| ThreadPoolTaskExecutor | Vòng đời ứng dụng | Spring bean với shutdown policy |
| File tạm cho một tác vụ | Trong một tác vụ | Tạo và xóa trong phạm vi tác vụ |
| Message consumer | Vòng đời ứng dụng hoặc một subscription | Lifecycle start/stop có thứ tự |
| Cache local | Vòng đời bean/context | Bean lifecycle hoặc thư viện cache tự quản lý |

Điểm quan trọng là xác định **ai tạo tài nguyên, ai dùng và ai có trách nhiệm đóng nó**.

### 1.1. Quy tắc ownership

Một nguyên tắc dễ áp dụng:

> Thành phần tạo và sở hữu một tài nguyên chịu trách nhiệm giải phóng nó, trừ khi ownership đã được chuyển giao rõ ràng.

Ví dụ, một method mở file rồi đọc xong:

~~~java
public String readFile(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8);
    }
}
~~~

Method mở stream và cũng đóng stream. Không cần giữ InputStream trong field của service chỉ để đọc một file.

Ngược lại, nếu một service tạo một HTTP client dùng chung:

~~~java
public class PartnerClient implements AutoCloseable {
    // Client giữ connection pool và tài nguyên nội bộ.
    @Override
    public void close() {
        // Đóng client/pool.
    }
}
~~~

thì client cần được đóng khi owner kết thúc vòng đời. Nếu nó là singleton Spring bean, container có thể thực hiện cleanup callback khi context đóng.

### 1.2. Không đóng tài nguyên mà mình chỉ mượn

Giả sử service nhận một DataSource qua constructor:

~~~java
@Service
public class OrderRepository {

    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }
}
~~~

Repository **sử dụng** DataSource do container quản lý. Nó không sở hữu DataSource nên không được gọi dataSource.close() sau mỗi request.

Tương tự:

- Không đóng shared HTTP client do một bean khác quản lý.
- Không shutdown executor dùng chung nếu service chỉ gửi task vào đó.
- Không đóng ApplicationContext từ một bean nghiệp vụ.
- Không tự giải phóng connection pool do Spring Boot auto-configure.

Đóng tài nguyên dùng chung quá sớm có thể làm các bean khác thất bại dù ứng dụng chưa shutdown.

### 1.3. Resource ownership nên được thể hiện trong API

Một method nhận InputStream cần quy định rõ ai đóng stream:

~~~java
public void importData(InputStream input) {
    // API này chỉ đọc stream hay nhận ownership?
}
~~~

Nếu method đóng stream, caller phải biết stream sẽ không còn dùng được sau khi gọi. Nếu caller vẫn sở hữu stream, method không nên tự đóng.

Có thể diễn đạt ownership bằng tên/hợp đồng method, tài liệu và cách tổ chức try-with-resources. Không nên để người gọi phải đoán.

## 2. Các giai đoạn trong vòng đời một Spring bean

Với một singleton bean thông thường, Spring tạo object, inject dependency, gọi các callback khởi tạo và cuối cùng quản lý cleanup khi context đóng.

~~~text
ApplicationContext refresh
          │
          ▼
Tạo bean instance
          │
          ▼
Inject constructor / properties
          │
          ▼
Aware callbacks (nếu có)
          │
          ▼
BeanPostProcessor trước initialization
          │
          ▼
@PostConstruct
          │
          ▼
InitializingBean.afterPropertiesSet()
          │
          ▼
Custom init method
          │
          ▼
BeanPostProcessor sau initialization
          │
          ▼
Bean sẵn sàng sử dụng
          │
          ▼
ApplicationContext đóng
          │
          ▼
@PreDestroy
          │
          ▼
DisposableBean.destroy()
          │
          ▼
Custom destroy method
~~~

Đây là sơ đồ khái niệm cho bean được Spring quản lý đầy đủ. Những callback cụ thể còn phụ thuộc bean type, scope, proxy và cấu hình container.

### 2.1. Constructor: thiết lập trạng thái cần thiết

Constructor injection phù hợp để nhận dependency bắt buộc:

~~~java
@Component
public class ReportService {

    private final ReportRepository repository;
    private final ReportExporter exporter;

    public ReportService(
            ReportRepository repository,
            ReportExporter exporter) {
        this.repository = repository;
        this.exporter = exporter;
    }
}
~~~

Constructor nên:

- Nhận các dependency cần thiết.
- Gán field.
- Kiểm tra invariant đơn giản.
- Thiết lập state nội bộ an toàn.

Tránh mở socket, gọi remote API, chạy batch dài hoặc tạo side effects khó rollback trong constructor. Nếu việc khởi tạo thất bại giữa chừng, object chưa được đăng ký hoàn chỉnh và việc cleanup tài nguyên vừa mở có thể trở nên khó kiểm soát.

### 2.2. Dependency injection xảy ra trước init callbacks

Khi @PostConstruct được gọi, các dependency đã được inject theo quy trình thông thường. Vì vậy callback này có thể dùng collaborator đã nhận từ constructor để hoàn tất một số bước khởi tạo cục bộ.

Tuy nhiên, không nên mặc định mọi bean khác trong context đều đã hoàn tất initialization chỉ vì một bean đang chạy @PostConstruct. Bean graph có thứ tự khởi tạo theo dependency; các singleton không liên quan có thể chưa được tạo.

Nếu một bước cần toàn bộ context sẵn sàng, hãy xem lifecycle event hoặc runner phù hợp thay vì dựa vào thứ tự ngẫu nhiên của component scan.

### 2.3. Initialization callback không phải nơi chạy mọi công việc startup

Một callback khởi tạo bean nên ngắn và gắn với tính hợp lệ của bean đó, ví dụ:

- Kiểm tra cấu hình cục bộ.
- Chuẩn bị một cấu trúc dữ liệu nội bộ.
- Xác minh một resource đã được mở.
- Tạo handle mà bean sở hữu.

Những công việc như nhập hàng triệu dòng dữ liệu, gọi nhiều dịch vụ ngoài hoặc chờ hệ thống khác sẵn sàng có thể làm context startup kéo dài và gây khó kiểm soát timeout. Hãy chọn ApplicationRunner, lifecycle component hoặc job riêng tùy bản chất công việc.

## 3. @PostConstruct: khởi tạo sau khi dependency được inject

@PostConstruct là annotation chuẩn của Jakarta để đánh dấu method được gọi sau khi dependency injection hoàn tất và trước khi bean được đưa vào sử dụng theo lifecycle thông thường.

Trong Spring Boot 3, import:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Ví dụ:

~~~java
package com.example.reports;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class ReportFormatRegistry {

    private final ReportFormatRepository repository;
    private Map<String, ReportFormat> formats;

    public ReportFormatRegistry(
            ReportFormatRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void initialize() {
        this.formats = Map.copyOf(repository.loadBuiltInFormats());
    }
}
~~~

Ví dụ này giả định loadBuiltInFormats() chỉ đọc dữ liệu cần thiết và có thể chạy an toàn trong giai đoạn khởi tạo. Nếu nó phụ thuộc database/network, cần cân nhắc startup policy và cách xử lý lỗi.

### 3.1. Phương thức @PostConstruct nên có đặc điểm gì?

- Thường là method không tham số.
- Không cần public; method có thể là package-private hoặc protected theo quy tắc hỗ trợ của runtime/framework.
- Không nên trả về giá trị.
- Không nên khai báo static.
- Chỉ nên có một callback phù hợp trong hierarchy theo quy tắc annotation processing.

Ví dụ:

~~~java
@PostConstruct
void warmUpLocalIndex() {
    this.index = buildLocalIndex();
}
~~~

### 3.2. Nếu @PostConstruct ném exception thì sao?

Nếu callback khởi tạo ném exception không được xử lý, việc tạo bean thất bại. Với singleton bắt buộc, quá trình refresh ApplicationContext thường thất bại theo và Spring Boot có thể không khởi động được.

Điều này phù hợp khi bean không thể hoạt động an toàn nếu thiếu resource đó.

Không nên bắt mọi exception rồi bỏ qua:

~~~java
@PostConstruct
void initialize() {
    try {
        connectToRequiredSystem();
    } catch (Exception ex) {
        // Bỏ qua để ứng dụng vẫn khởi động.
    }
}
~~~

Nếu dependency là bắt buộc, im lặng bỏ qua lỗi chỉ khiến ứng dụng chạy trong trạng thái không hợp lệ.

### 3.3. Không dùng @PostConstruct để tự inject dependency

Không nên:

~~~java
@PostConstruct
void initialize() {
    this.repository = applicationContext.getBean(
            ReportRepository.class);
}
~~~

Đây là service locator: dependency bị giấu trong method thay vì constructor. Hãy khai báo ReportRepository trực tiếp trong constructor để thể hiện hợp đồng của bean.

### 3.4. Tránh phụ thuộc vào bean chưa khởi tạo

Một @PostConstruct gọi một service khác có thể kích hoạt thêm quá trình khởi tạo bean đó. Nếu graph phức tạp, dễ phát sinh side effect sớm, circular dependency hoặc startup order khó hiểu.

Hãy giữ callback tập trung vào trạng thái của chính bean. Nếu cần phối hợp nhiều bean sau khi context đã sẵn sàng, xem xét event hoặc runner.

## 4. @PreDestroy: giải phóng tài nguyên trước khi bean bị hủy

@PreDestroy đánh dấu method được gọi khi container chuẩn bị hủy bean trong lifecycle cleanup.

Spring Boot 3:

~~~java
import jakarta.annotation.PreDestroy;
~~~

Ví dụ một bean giữ tài nguyên:

~~~java
package com.example.integration;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class PartnerConnectionManager {

    private final PartnerClient client;

    public PartnerConnectionManager(PartnerClient client) {
        this.client = client;
    }

    @PreDestroy
    void releaseResources() {
        client.close();
    }
}
~~~

Ví dụ này chỉ đúng nếu PartnerConnectionManager thực sự sở hữu PartnerClient. Nếu client là một bean dùng chung được inject từ nơi khác, bean quản lý client mới nên đóng nó.

### 4.1. Cleanup cần an toàn khi chạy lúc shutdown

Một destroy callback nên:

- Có thể gọi khi ứng dụng đang dừng.
- Không giả định request mới vẫn được xử lý.
- Không phụ thuộc vào bean đã bị hủy trước đó.
- Có giới hạn thời gian nếu chờ tác vụ/flush.
- Giữ lại thông tin cần thiết khi cleanup thất bại.

Không nên gọi remote service không giới hạn thời gian trong @PreDestroy. Nếu mạng bị lỗi, shutdown có thể kéo dài hoặc bị process manager kill trước khi cleanup hoàn tất.

### 4.2. Không đóng cùng một tài nguyên ở nhiều owner

Nếu PartnerClient là một @Bean riêng có destroy method close, và PartnerConnectionManager cũng gọi client.close() trong @PreDestroy, tài nguyên có thể bị đóng hai lần.

Một số API cho phép close nhiều lần an toàn, nhưng không nên dựa vào điều đó nếu không có hợp đồng rõ ràng.

Chọn một owner duy nhất:

- Bean factory tạo client và container đóng client.
- Hoặc manager tạo client và manager đóng client.

Không chia ownership mơ hồ giữa các bean.

### 4.3. @PreDestroy không phải hook bảo đảm chạy trong mọi tình huống

Spring có thể gọi destroy callbacks khi context được đóng theo lifecycle bình thường. Nhưng callback không được bảo đảm khi:

- Process bị kill cưỡng bức.
- JVM crash hoặc máy mất điện.
- Container bị terminate trước khi shutdown grace period kết thúc.
- Ứng dụng gọi Runtime.halt() hoặc thoát bất thường.
- Một số bean scope không được container quản lý destruction như mong đợi.

Vì vậy, không dùng @PreDestroy làm cơ chế duy nhất để bảo đảm một giao dịch nghiệp vụ quan trọng được commit. Dữ liệu cần bền vững phải được ghi theo transaction/durable storage phù hợp.

## 5. Vòng đời annotation trong Spring Boot 2 và 3

Sự khác nhau thường gặp là package của annotation:

| Nền tảng | @PostConstruct / @PreDestroy |
|---|---|
| Spring Boot 3 / Spring Framework 6 | jakarta.annotation.PostConstruct, jakarta.annotation.PreDestroy |
| Spring Boot 2 / Spring Framework 5 | Thường dùng javax.annotation.PostConstruct, javax.annotation.PreDestroy nếu dependency tương ứng có mặt |

Ví dụ Boot 3:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

Không import nhầm javax.annotation từ một dependency cũ trong ứng dụng Boot 3. Package Jakarta và Javax là hai namespace khác nhau.

### 5.1. Dependency annotation có cần thêm riêng không?

Trong môi trường Boot 3, Jakarta annotation API có thể được cung cấp qua dependency phù hợp của ứng dụng/framework. Nếu compiler báo không tìm thấy package jakarta.annotation, kiểm tra dependency graph và starter đang dùng; đừng thêm một phiên bản API bất kỳ không tương thích với dependency management.

### 5.2. Annotation chuẩn khác với Spring-specific lifecycle interface

@PostConstruct và @PreDestroy là annotation chuẩn Jakarta. InitializingBean và DisposableBean là interface của Spring. Cả hai có thể được container hỗ trợ, nhưng mức độ gắn kết với Spring khác nhau.

Với code nghiệp vụ thông thường, annotation thường giúp giữ class ít phụ thuộc vào Spring API hơn.

## 6. InitializingBean và DisposableBean

Spring cung cấp hai lifecycle interfaces:

~~~java
org.springframework.beans.factory.InitializingBean
org.springframework.beans.factory.DisposableBean
~~~

Ví dụ:

~~~java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
public class LocalIndex implements InitializingBean, DisposableBean {

    @Override
    public void afterPropertiesSet() {
        // Chuẩn bị index sau khi properties được inject.
    }

    @Override
    public void destroy() {
        // Giải phóng resource do bean sở hữu.
    }
}
~~~

### 6.1. afterPropertiesSet()

afterPropertiesSet() được gọi trong giai đoạn initialization, sau khi các properties/dependencies được set theo lifecycle của Spring.

Nó có mục đích tương tự @PostConstruct:

- Hoàn tất trạng thái nội bộ.
- Kiểm tra điều kiện cấu hình.
- Chuẩn bị resource cục bộ mà bean sở hữu.

### 6.2. destroy()

destroy() là callback cleanup khi bean được container hủy theo lifecycle hỗ trợ.

Có thể đóng client, dừng worker hoặc flush tài nguyên do bean sở hữu.

### 6.3. Ưu và nhược điểm

| Cách | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|
| @PostConstruct / @PreDestroy | Annotation phổ biến, ít phụ thuộc Spring API | Cần Jakarta/Javax namespace phù hợp |
| InitializingBean / DisposableBean | Hợp đồng lifecycle rõ, Spring gọi trực tiếp | Class phụ thuộc Spring Framework |
| initMethod / destroyMethod | Cấu hình lifecycle ở nơi khai báo bean | Method không hiện trong class như annotation |

Nếu class được thiết kế như một component thuần Java hoặc thư viện dùng ngoài Spring, annotation chuẩn hoặc API AutoCloseable có thể phù hợp hơn. Nếu class là adapter đặc thù Spring, lifecycle interface vẫn là lựa chọn hợp lệ.

### 6.4. Không triển khai cả ba cách cho cùng một công việc

Một bean không cần đồng thời:

- @PostConstruct
- InitializingBean.afterPropertiesSet()
- custom init method

chỉ để gọi cùng một hàm chuẩn bị ba lần. Điều đó gây khó đọc thứ tự và tăng nguy cơ side effect lặp.

Chọn một cơ chế chính cho mỗi trách nhiệm lifecycle. Nếu có nhiều bước khởi tạo thực sự khác nhau, đặt tên rõ ràng và hiểu thứ tự callback.

## 7. Khai báo initMethod và destroyMethod trên @Bean

Khi bean được tạo từ một factory method, có thể cấu hình callback tại nơi đăng ký bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(
            initMethod = "start",
            destroyMethod = "stop")
    PartnerClient partnerClient() {
        return new PartnerClient();
    }
}
~~~

Ở đây:

- Spring gọi start() trong giai đoạn khởi tạo bean.
- Spring gọi stop() khi bean được hủy theo lifecycle.

### 7.1. Phù hợp với class bên thứ ba

Bạn không thể thêm @PostConstruct vào class thư viện không thuộc quyền sở hữu. Nhưng nếu class có method initialize()/shutdown(), có thể khai báo:

~~~java
@Bean(
        initMethod = "initialize",
        destroyMethod = "shutdown")
ThirdPartyClient thirdPartyClient() {
    return ThirdPartyClient.builder()
            .endpoint("https://api.example.invalid")
            .build();
}
~~~

Điều này giữ lifecycle management ở cấu hình Spring mà không cần sửa thư viện.

### 7.2. Method phải phù hợp với callback contract

Các method được khai báo làm init/destroy method thường cần có signature mà Spring có thể gọi theo lifecycle, phổ biến là method không tham số.

Không dùng method cần ApplicationContext, Environment hoặc business argument như destroy method nếu không có cơ chế phù hợp.

### 7.3. Bean @Bean có thể tự suy luận close/shutdown

Spring hỗ trợ suy luận destroy method cho một số bean được khai báo qua @Bean, thường dựa trên public close() hoặc shutdown() method phù hợp.

Ví dụ:

~~~java
@Bean
PartnerClient partnerClient() {
    return new PartnerClient();
}
~~~

Nếu PartnerClient là AutoCloseable hoặc có public close method theo quy tắc Spring hỗ trợ, container có thể tự gọi cleanup khi destroy.

Tuy nhiên, với resource quan trọng, khai báo rõ:

~~~java
@Bean(destroyMethod = "close")
PartnerClient partnerClient() {
    return new PartnerClient();
}
~~~

có thể giúp người đọc thấy rõ ownership và ý định cleanup.

### 7.4. Tắt inferred destroy method khi bean không thuộc ownership của container

Nếu bean trả về là một shared object được tạo/quản lý bên ngoài và Spring không được phép đóng nó, có thể cấu hình:

~~~java
@Bean(destroyMethod = "")
ExternalSharedClient externalSharedClient() {
    return externallyManagedClient();
}
~~~

Chỉ làm điều này khi ownership bên ngoài được xác định rõ. Nếu bean thực sự được ứng dụng tạo và sở hữu, tắt destroy method có thể gây resource leak.

### 7.5. Tránh gọi close ngay trong factory method

Không:

~~~java
@Bean
PartnerClient partnerClient() {
    PartnerClient client = new PartnerClient();
    client.close();
    return client;
}
~~~

Bean được trả về đã đóng trước khi bất kỳ consumer nào sử dụng. Hãy để lifecycle callback đảm nhiệm cleanup vào đúng thời điểm.

## 8. AutoCloseable và try-with-resources

Java có interface chuẩn:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Một resource implement AutoCloseable có thể được đóng tự động khi ra khỏi try-with-resources:

~~~java
try (PartnerClient client = new PartnerClient()) {
    client.send(message);
}
~~~

Đây là cách phù hợp khi resource có vòng đời gắn với một block/method và code đang trực tiếp sở hữu nó.

### 8.1. Resource cục bộ: try-with-resources

Ví dụ đọc file:

~~~java
public List<String> readLines(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines().toList();
    }
}
~~~

Khi block kết thúc bình thường hoặc do exception, Java tự gọi close(). Nếu close() cũng ném exception trong khi block đã có exception khác, Java giữ exception chính và ghi nhận exception khi đóng dưới dạng suppressed exception.

### 8.2. Resource sống cùng bean: Spring lifecycle

Nếu một client được dùng qua nhiều request:

~~~java
@Bean(destroyMethod = "close")
PartnerClient partnerClient() {
    return new PartnerClient();
}
~~~

Spring quản lý bean và gọi close khi bean được destroy theo lifecycle.

### 8.3. Không dùng try-with-resources cho bean được inject và chia sẻ

Không:

~~~java
public void sendMessage(String message) throws Exception {
    try (PartnerClient client = injectedClient) {
        client.send(message);
    }
}
~~~

Nếu injectedClient là singleton dùng chung, method này đóng client sau một lần gửi. Request tiếp theo có thể thất bại.

Caller chỉ sở hữu resource khi API đã chuyển quyền sở hữu cho caller. Với bean do container quản lý, hãy để owner bean/container đóng.

### 8.4. Phân biệt close và shutdown

Các thư viện có thể dùng tên method khác nhau:

- close(): đóng resource, stream, client hoặc pool.
- shutdown(): yêu cầu executor/service dừng nhận công việc mới.
- stop(): dừng một component theo lifecycle contract.
- dispose(): giải phóng resource theo API của thư viện.

Không tự chọn tên theo cảm tính. Hãy đọc contract của thư viện và bảo đảm destroy callback gọi đúng phương thức.

## 9. Singleton bean và prototype bean có cleanup khác nhau

Spring hỗ trợ nhiều bean scopes. Scope quyết định số lượng instance và phạm vi tồn tại của bean.

### 9.1. Singleton

Singleton là scope mặc định. Spring tạo một instance cho mỗi bean definition trong một ApplicationContext và quản lý lifecycle của instance đó.

~~~java
@Component
public class SharedPartnerClient {
    // Một instance dùng chung trong context.
}
~~~

Với singleton được quản lý đầy đủ, Spring gọi destroy callbacks khi context đóng.

### 9.2. Prototype

Prototype tạo instance mới mỗi lần container được yêu cầu resolve bean theo scope đó.

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class CsvImportSession implements AutoCloseable {

    @Override
    public void close() {
        // Đóng file/session do instance sở hữu.
    }
}
~~~

**Spring quản lý việc tạo, inject và initialization của prototype bean, nhưng không theo dõi đầy đủ destruction của từng instance sau khi giao nó cho caller.**

Vì vậy, container không tự bảo đảm gọi @PreDestroy hoặc destroy method cho prototype bean khi caller dùng xong.

### 9.3. Caller chịu trách nhiệm cleanup prototype

Nếu lấy prototype qua ObjectProvider:

~~~java
@Service
public class ImportCoordinator {

    private final ObjectProvider<CsvImportSession> sessions;

    public ImportCoordinator(
            ObjectProvider<CsvImportSession> sessions) {
        this.sessions = sessions;
    }

    public void importOne(Path file) {
        CsvImportSession session = sessions.getObject();
        try {
            session.importFile(file);
        } finally {
            session.close();
        }
    }
}
~~~

Caller tạo instance và phải đóng nó sau khi hoàn thành. Có thể dùng try-with-resources nếu type implement AutoCloseable:

~~~java
try (CsvImportSession session = sessions.getObject()) {
    session.importFile(file);
}
~~~

Điều này yêu cầu API của class và ownership được thiết kế phù hợp. Đừng trông đợi Spring tự gọi destroy callback cho mọi prototype object.

### 9.4. Inject prototype trực tiếp vào singleton không tạo instance mới mỗi lần dùng

Ví dụ:

~~~java
@Service
public class ImportCoordinator {

    private final CsvImportSession session;

    public ImportCoordinator(CsvImportSession session) {
        this.session = session;
    }
}
~~~

Nếu singleton ImportCoordinator được tạo một lần, prototype dependency thường được resolve tại thời điểm tạo singleton. Singleton giữ đúng instance đó; gọi nhiều method không tự tạo prototype mới.

Nếu cần instance mới theo từng lần sử dụng, dùng ObjectProvider, Provider hoặc scoped proxy phù hợp.

### 9.5. Request/session scope

Trong web application, Spring có các scope như request và session. Bean scoped được tạo theo phạm vi request/session và container quản lý lifecycle tương ứng khi scope kết thúc.

Ví dụ:

~~~java
@Component
@RequestScope
public class RequestContextData {
    // Dữ liệu gắn với một HTTP request.
}
~~~

Đối với scoped bean, destruction callback được xử lý khi scope tương ứng kết thúc theo cơ chế web context. Không nên giữ reference tới request-scoped resource trong singleton rồi sử dụng ngoài request.

### 9.6. Bảng so sánh scope và destruction

| Scope | Vòng đời | Ai quản lý cleanup? |
|---|---|---|
| singleton | Theo ApplicationContext | Spring gọi destroy callbacks khi context đóng |
| prototype | Mỗi lần resolve tạo instance mới | Caller chịu trách nhiệm cleanup sau khi nhận instance |
| request | Trong một HTTP request | Web scope/container khi request kết thúc |
| session | Theo HTTP session | Web scope/container khi session kết thúc theo lifecycle |
| application | Theo ServletContext trong web app | Web application context |
| custom scope | Theo contract của scope | Scope implementation phải quản lý callbacks đúng cách |

## 10. Lifecycle của ứng dụng khác lifecycle của một bean

Một bean có thể được tạo và hủy trong khi ApplicationContext vẫn sống, ví dụ request-scoped bean. Ngược lại, một ứng dụng có thể cần điều phối một chuỗi component cùng start/stop.

Phân biệt:

- **Bean initialization/destruction:** callback gắn với một bean.
- **Application startup/readiness:** thời điểm ứng dụng hoàn tất khởi động.
- **Application lifecycle:** quản lý component bắt đầu hoạt động, dừng nhận việc và giải phóng.
- **Process lifecycle:** JVM/container bắt đầu và kết thúc.

Không dùng @PostConstruct cho mọi thứ chỉ vì muốn chạy code “khi app start”.

### 10.1. ApplicationRunner và CommandLineRunner

Nếu cần thực hiện một bước sau khi ApplicationContext đã refresh và trước khi SpringApplication báo sẵn sàng, có thể dùng:

~~~java
@Component
public class StartupDataCheck implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Kiểm tra hoặc chuẩn bị dữ liệu sau context refresh.
    }
}
~~~

ApplicationRunner và CommandLineRunner chạy trong startup flow sau khi context được refresh. Chúng thích hợp cho công việc startup cần các bean đã sẵn sàng hơn so với @PostConstruct của một bean đơn lẻ.

Tuy nhiên, nếu runner ném exception, ứng dụng vẫn có thể thất bại trong startup. Không nên dùng runner để chạy một job không giới hạn thời gian khiến deployment không bao giờ đạt trạng thái ready.

### 10.2. ApplicationReadyEvent

Spring Boot phát ApplicationReadyEvent khi ứng dụng đã sẵn sàng theo startup lifecycle:

~~~java
@Component
public class ReadyListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Thực hiện hành động sau khi app đã ready.
    }
}
~~~

Đây là tín hiệu phù hợp khi một hành động cần chờ toàn bộ startup flow hoàn tất. Nhưng listener vẫn chạy trong process; nếu mở một resource dài hạn ở đây, cần có owner và cleanup tương ứng.

### 10.3. ContextClosedEvent

Spring phát ContextClosedEvent khi ApplicationContext bắt đầu đóng:

~~~java
@Component
public class ShutdownObserver {

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        // Ghi nhận sự kiện hoặc phát tín hiệu nội bộ.
    }
}
~~~

Event hữu ích để quan sát hoặc điều phối một số hành động khi context đóng. Với resource thuộc sở hữu của bean, destroy callback như @PreDestroy hoặc destroyMethod thường thể hiện ownership trực tiếp và dễ kiểm soát hơn.

Không dùng event listener làm nơi đóng tất cả resources toàn cục mà không xác định owner.

### 10.4. ApplicationReadyEvent không thay thế @PostConstruct

@PostConstruct chạy trong lifecycle của bean. ApplicationReadyEvent xảy ra muộn hơn, sau startup flow của ứng dụng.

Chọn theo mục đích:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Hoàn tất state riêng của một bean | @PostConstruct hoặc init callback |
| Kiểm tra/cấu hình phụ thuộc nhiều bean sau refresh | ApplicationRunner |
| Thực hiện hành động khi app đã ready | ApplicationReadyEvent |
| Giải phóng resource của bean | @PreDestroy/destroyMethod |
| Điều phối start/stop component | Lifecycle/SmartLifecycle |

## 11. Lifecycle và SmartLifecycle

Spring có interface:

~~~java
org.springframework.context.Lifecycle
org.springframework.context.SmartLifecycle
~~~

Lifecycle mô tả component có thể start/stop:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

SmartLifecycle bổ sung khả năng tự khởi động, phase và callback khi stop bất đồng bộ.

### 11.1. Khi nào dùng Lifecycle?

Phù hợp với component có trạng thái hoạt động rõ:

- Message listener container.
- Consumer subscription.
- Background polling worker.
- Component nhận sự kiện từ hệ thống ngoài.
- Một service cần ngừng nhận việc trước khi các dependency bị đóng.

Không cần implement Lifecycle cho mọi service chỉ có method nghiệp vụ. Một class stateless dùng để tính giá không cần start/stop.

### 11.2. Ví dụ một consumer có lifecycle

~~~java
package com.example.messaging;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class OrderEventConsumer implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        // Mở subscription hoặc bắt đầu nhận message.
        running = true;
    }

    @Override
    public void stop() {
        // Ngừng nhận message và đóng subscription.
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Đây là ví dụ khung. Một consumer thật cần giữ handle subscription, dừng nhận message mới, xử lý message đang chạy theo policy và đóng client do nó sở hữu.

### 11.3. stop(Runnable callback) phải gọi callback khi dừng xong

Với SmartLifecycle, callback cho phép component báo cho container biết quá trình dừng đã hoàn tất, đặc biệt nếu stop diễn ra bất đồng bộ.

Ví dụ:

~~~java
@Override
public void stop(Runnable callback) {
    subscription.stopAsync()
            .whenComplete((ignored, error) -> {
                running = false;
                callback.run();
            });
}
~~~

Đây là minh họa cho API trả về CompletionStage; kiểu thực tế tùy thư viện. Nếu quá trình stop thất bại, cần ghi nhận lỗi phù hợp và vẫn bảo đảm callback được hoàn tất theo contract, tránh làm LifecycleProcessor chờ vô hạn.

### 11.4. Phase điều khiển thứ tự start/stop

SmartLifecycle có phase:

- Phase thấp thường được start trước.
- Phase cao thường được start sau.
- Khi stop, thứ tự được đảo lại: phase cao dừng trước, phase thấp dừng sau.

Điều này hữu ích khi một component phụ thuộc vào một component khác:

~~~text
Startup:
Message transport (phase thấp)
          │
          ▼
Message consumer (phase cao)

Shutdown:
Message consumer dừng trước
          │
          ▼
Message transport dừng sau
~~~

Ví dụ: consumer nên ngừng nhận message trước khi transport/client dùng để nhận message bị đóng.

Không chọn phase tùy tiện. Hãy dựa vào dependency thực tế và viết integration test cho thứ tự nếu nó quan trọng.

### 11.5. isAutoStartup()

SmartLifecycle có thể khai báo component có tự start khi context refresh hay không. Với isAutoStartup() trả true, Spring tự start theo lifecycle. Nếu trả false, ứng dụng cần điều khiển start theo cách riêng.

Không nên tự start cùng component ở cả @PostConstruct và SmartLifecycle.start(), vì có thể mở subscription hoặc thread hai lần.

### 11.6. LifecycleProcessor điều phối component

Spring sử dụng LifecycleProcessor để điều phối start/stop các bean có lifecycle contract trong quá trình refresh và close context.

Bạn không cần tự gọi start/stop của từng bean từ ApplicationContext nếu chỉ muốn Spring quản lý lifecycle chuẩn.

## 12. Graceful shutdown: dừng nhận việc trước khi giải phóng tài nguyên

Khi ứng dụng dừng, không phải mọi request/task đều kết thúc ngay lập tức. Một server có thể đang xử lý request, một consumer đang xử lý message, hoặc một executor còn task trong queue.

**Graceful shutdown** là quy trình cho ứng dụng một khoảng thời gian có giới hạn để ngừng nhận công việc mới và hoàn tất công việc đang chạy trước khi giải phóng resources.

~~~text
Nhận tín hiệu shutdown
          │
          ▼
Ngừng nhận công việc mới
          │
          ▼
Chờ request / task / message đang chạy
          │
          ▼
Flush hoặc commit trạng thái cần thiết
          │
          ▼
Đóng consumer / executor / client
          │
          ▼
Đóng ApplicationContext
          │
          ▼
Process kết thúc
~~~

Thứ tự thực tế phụ thuộc server, lifecycle phases, bean dependencies và cấu hình timeout.

### 12.1. Graceful shutdown của web server trong Spring Boot

Spring Boot hỗ trợ cấu hình shutdown mode:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Với server implementation được hỗ trợ, graceful shutdown giúp ngừng nhận request mới và cho các request đang xử lý cơ hội hoàn tất trong khoảng thời gian được cấp.

Nếu thời gian chờ hết, ứng dụng vẫn cần kết thúc theo shutdown policy; không có bảo đảm request nào cũng hoàn thành nếu nó chạy lâu hơn timeout.

### 12.2. Timeout phải phù hợp với deployment

Ví dụ Kubernetes có termination grace period ngắn hơn tổng thời gian Spring cần để dừng các phase. Khi đó container runtime có thể kill process trước khi cleanup hoàn tất.

Hãy đồng bộ:

- Spring lifecycle timeout.
- Web server graceful shutdown timeout.
- Executor/consumer shutdown timeout.
- Kubernetes terminationGracePeriodSeconds hoặc service manager timeout.
- Thời gian tối đa mà load balancer ngừng gửi traffic tới instance.

Không đặt timeout vô hạn. Một shutdown bị treo cũng có thể làm rollout hoặc scale-down không hoàn tất.

### 12.3. Ngừng nhận request khác với đóng mọi connection ngay lập tức

Nếu đóng DataSource hoặc HTTP client trước khi các request đang xử lý hoàn tất, những request đó có thể mất khả năng dùng dependency.

Vì vậy, thứ tự dừng cần tính tới:

1. Ngừng nhận traffic mới.
2. Chờ request đang chạy kết thúc trong giới hạn.
3. Dừng background consumers.
4. Hoàn tất hoặc hủy các tasks theo policy.
5. Đóng clients, pools và resource cấp thấp.

Lifecycle phase và shutdown coordination giúp thể hiện thứ tự này khi các component có dependency rõ ràng.

## 13. Quản lý thread pool và executor

Thread pool là tài nguyên dài hạn. Nếu tạo bằng Executors.newFixedThreadPool() trong một service rồi không shutdown, các thread có thể tiếp tục sống sau khi context đóng.

Không nên:

~~~java
@Service
public class ExportService {

    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);
}
~~~

Ở ví dụ này, Spring không tự biết phải đóng executor do constructor/field tự tạo bên trong bean nếu không có destroy callback.

### 13.1. Dùng ThreadPoolTaskExecutor như Spring bean

~~~java
@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {

    @Bean
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("report-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
~~~

Spring quản lý ThreadPoolTaskExecutor như một bean lifecycle-aware. Nó có initialization và shutdown support; các thiết lập ở ví dụ yêu cầu chờ các task đang chạy/đang chờ trong giới hạn đã đặt khi context shutdown.

### 13.2. waitForTasksToCompleteOnShutdown

Khi đặt true, executor cố gắng để các task đã submit hoàn tất trong shutdown thay vì lập tức hủy queue theo hành vi mặc định tương ứng.

Điều này không có nghĩa mọi task chắc chắn hoàn thành:

- Task có thể chạy quá thời gian chờ.
- Task có thể bị interrupt/hủy khi timeout.
- Task có thể bị lỗi do dependency đã bắt đầu shutdown.
- Task không nên phụ thuộc vào một tài nguyên đã bị đóng trước khi nó hoàn tất.

### 13.3. awaitTerminationSeconds

Đặt giới hạn chờ executor dừng:

~~~java
executor.setAwaitTerminationSeconds(20);
~~~

Giá trị phải phù hợp với thời gian shutdown tổng thể. Nếu executor chờ 60 giây nhưng process manager chỉ cho 30 giây, process vẫn có thể bị kết thúc trước.

### 13.4. Service sử dụng executor không được tự shutdown nó

~~~java
@Service
public class ReportService {

    private final ThreadPoolTaskExecutor executor;

    public ReportService(ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public void submit(Report report) {
        executor.execute(() -> generate(report));
    }
}
~~~

ReportService chỉ sử dụng executor. Bean AsyncConfiguration sở hữu và Spring đóng executor khi context kết thúc.

Không gọi executor.shutdown() sau mỗi submit hoặc sau mỗi request.

### 13.5. Nếu tự quản lý ExecutorService

Nếu dùng Java ExecutorService trực tiếp, cần có owner và destroy callback:

~~~java
public final class ManagedExecutor implements AutoCloseable {

    private final ExecutorService delegate =
            Executors.newFixedThreadPool(4);

    public void execute(Runnable task) {
        delegate.execute(task);
    }

    @Override
    public void close() {
        delegate.shutdown();
        try {
            if (!delegate.awaitTermination(
                    20, TimeUnit.SECONDS)) {
                delegate.shutdownNow();
            }
        } catch (InterruptedException ex) {
            delegate.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Đăng ký:

~~~java
@Bean(destroyMethod = "close")
ManagedExecutor managedExecutor() {
    return new ManagedExecutor();
}
~~~

Ví dụ này minh họa một owner tự quản lý executor. Trong code thực tế, cần quyết định cách xử lý task bị hủy, exception của task và logging; không dùng chung một executor mà không có policy queue/rejection phù hợp.

### 13.6. Đừng tạo thread thủ công trong @PostConstruct mà quên dừng

~~~java
@PostConstruct
void startWorker() {
    worker = new Thread(this::pollForever);
    worker.start();
}
~~~

Nếu chọn cách này, bean phải có cơ chế stop, interrupt, join với timeout và xử lý trạng thái. Thông thường một TaskExecutor, ScheduledExecutorService hoặc SmartLifecycle component thể hiện ownership/lifecycle rõ hơn.

Không dùng vòng lặp vô hạn không có stop signal hoặc sleep không thể interrupt.

## 14. Quản lý ScheduledExecutorService và scheduled tasks

Một scheduler có thể tiếp tục gọi task theo chu kỳ sau khi service không còn được sử dụng. Cần dừng scheduler đúng lúc.

Ví dụ dùng Spring TaskScheduler:

~~~java
@Configuration(proxyBeanMethods = false)
public class SchedulerConfiguration {

    @Bean
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(15);
        return scheduler;
    }
}
~~~

Spring quản lý lifecycle của scheduler bean. Nếu dùng @Scheduled, Spring scheduling infrastructure quản lý các scheduled tasks theo scheduler được cấu hình.

### 14.1. @Scheduled không phải thread pool riêng của từng method

~~~java
@Component
public class CleanupJob {

    @Scheduled(fixedDelay = 60_000)
    public void cleanExpiredRecords() {
        // Công việc định kỳ.
    }
}
~~~

Method được gọi bởi scheduling infrastructure. Không nên tự tạo một ScheduledExecutorService mới bên trong mỗi lần method chạy.

### 14.2. Dừng scheduling trước khi đóng dependency

Nếu job dùng DataSource hoặc HTTP client, shutdown cần ngăn lịch chạy mới và để task đang chạy kết thúc/hủy theo policy trước khi đóng dependency mà task cần.

Không để scheduler tiếp tục submit task vào executor đã shutdown hoặc gọi client đã đóng.

### 14.3. Task chạy quá lâu

Nếu scheduled task có thể kéo dài hơn chu kỳ:

- Chọn fixedDelay/fixedRate theo semantics mong muốn.
- Xác định có cho phép overlap hay không.
- Dùng lock/guard nếu không được chạy đồng thời.
- Có timeout và cancellation policy.
- Đảm bảo shutdown có thể dừng hoặc chờ task.

Resource lifecycle và task concurrency liên quan trực tiếp: một task đang chạy có thể còn giữ connection/file trong lúc context bắt đầu shutdown.

## 15. DataSource và JDBC resources

Spring Boot có thể auto-configure DataSource dựa trên dependency và cấu hình. Connection pool thường được quản lý như bean trong ApplicationContext.

Service sử dụng DataSource:

~~~java
@Repository
public class CustomerRepository {

    private final JdbcTemplate jdbcTemplate;

    public CustomerRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
~~~

Repository không sở hữu connection pool và không đóng DataSource khi một query kết thúc.

### 15.1. Để transaction manager quản lý connection

Với Spring JDBC/JPA, transaction manager quản lý việc lấy, gắn với transaction và giải phóng connection theo lifecycle transaction.

Ví dụ:

~~~java
@Transactional
public void transfer(AccountId from, AccountId to, Money amount) {
    // Thực hiện các thao tác repository trong transaction.
}
~~~

Không tự đóng connection do framework bind vào transaction nếu API transaction management đang sở hữu nó.

### 15.2. Khi tự lấy JDBC Connection

Nếu code trực tiếp gọi DataSource.getConnection(), code đó cần đóng Connection:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "select id from customer where active = ?")) {

    statement.setBoolean(1, true);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Đọc kết quả.
        }
    }
}
~~~

Đóng connection trả nó về pool nếu DataSource dùng connection pool; không nhất thiết đóng physical socket ngay lập tức.

### 15.3. Không đóng pool từ repository

Connection là resource theo operation/transaction. DataSource pool là resource cấp ứng dụng. Hai vòng đời khác nhau.

Container đóng pool khi DataSource bean bị destroy. Repository chỉ đóng connection mà chính operation của nó lấy ra theo đúng JDBC contract.

## 16. HTTP client và connection pool

HTTP client có thể giữ connection pool, event loop, selector thread hoặc tài nguyên native. Nếu client được tái sử dụng, cần một owner cấp ứng dụng.

Ví dụ cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
public class PartnerHttpConfiguration {

    @Bean(destroyMethod = "close")
    PartnerHttpClient partnerHttpClient() {
        return PartnerHttpClient.create();
    }
}
~~~

Tên class ở đây minh họa một client có close(). Với client thực tế như Apache HttpClient, Reactor Netty hoặc SDK vendor, hãy dùng đúng API shutdown/dispose theo phiên bản thư viện.

### 16.1. Inject client vào service

~~~java
@Service
public class PartnerGateway {

    private final PartnerHttpClient client;

    public PartnerGateway(PartnerHttpClient client) {
        this.client = client;
    }
}
~~~

Gateway sử dụng client; bean factory sở hữu client và container thực hiện cleanup. Không đóng client sau mỗi HTTP call nếu thư viện thiết kế client để dùng chung.

### 16.2. Async HTTP client cần dừng event loop

Một số client có event loop hoặc connection provider riêng. Đóng wrapper nhưng không dispose event loop/pool có thể để lại thread.

Hãy kiểm tra API lifecycle của thư viện:

- close() có đóng connection pool không?
- Có cần dispose() một provider riêng không?
- Có callback async khi shutdown hoàn tất không?
- Có timeout chờ active requests không?

Một destroy method đúng phải giải phóng toàn bộ tài nguyên mà bean factory đã tạo và sở hữu.

### 16.3. Không tạo client cho từng request nếu không cần

Tạo client liên tục có thể gây:

- Tốn chi phí khởi tạo TLS/DNS/connection pool.
- Tăng số lượng socket.
- Khó quản lý cleanup.
- Không tận dụng connection reuse.

Nếu client thread-safe và được thiết kế dùng chung, singleton bean thường là lựa chọn hợp lý. Nếu thư viện yêu cầu client riêng theo scope, hãy theo đúng contract của thư viện.

## 17. File, stream và temporary resources

File stream thường có vòng đời ngắn và nên được đóng ngay tại nơi mở.

~~~java
public void copy(Path source, Path target) throws IOException {
    try (InputStream in = Files.newInputStream(source);
         OutputStream out = Files.newOutputStream(target)) {
        in.transferTo(out);
    }
}
~~~

Không giữ stream mở trong singleton field chỉ để chia sẻ giữa nhiều request trừ khi thiết kế thực sự cần một handle lâu dài và có synchronization/lifecycle rõ.

### 17.1. Tạo file tạm và xóa khi hoàn tất

~~~java
Path temp = Files.createTempFile("import-", ".csv");
try {
    process(temp);
} finally {
    Files.deleteIfExists(temp);
}
~~~

Nếu cần giữ file khi xử lý thất bại để điều tra, hãy có policy retention rõ ràng thay vì bỏ qua cleanup vô thời hạn.

### 17.2. File lớn hoặc tác vụ async

Nếu method submit một tác vụ async để xử lý file:

- Không đóng stream trước khi worker đọc xong.
- Không giữ MultipartFile request-scoped sau khi request kết thúc nếu backing temp file có thể bị dọn.
- Nên chuyển dữ liệu sang storage có lifecycle phù hợp trước khi submit.
- Đảm bảo cleanup sau khi task hoàn tất hoặc thất bại.

### 17.3. Memory buffer cũng là resource theo phạm vi

ByteArrayOutputStream không cần close để giải phóng OS handle, nhưng buffer lớn vẫn chiếm heap. Resource lifecycle không chỉ là close socket/file; còn bao gồm giải phóng tham chiếu, giới hạn kích thước và tránh giữ dữ liệu lâu hơn cần thiết.

Không lưu request body hoặc file upload lớn trong singleton field sau khi xử lý xong.

## 18. Shutdown hook và đóng ApplicationContext

Spring container chỉ có thể gọi destroy callbacks khi context thực sự được đóng.

Với một context có thể đóng thủ công:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(OrderApiApplication.class, args);

// Khi cần dừng ứng dụng theo điều khiển của chương trình:
context.close();
~~~

Trong ứng dụng Spring Boot chạy bình thường, SpringApplication đăng ký cơ chế shutdown hook để đóng ApplicationContext khi JVM shutdown theo luồng thông thường.

### 18.1. Shutdown hook là gì?

JVM cho phép đăng ký hook được chạy khi JVM bắt đầu quá trình shutdown bình thường:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            // Cleanup ở mức JVM nếu thật sự cần.
        }));
~~~

Spring Boot thường quản lý việc đóng context qua shutdown hook của nó. Vì vậy, không cần tự đăng ký một hook khác chỉ để gọi @PreDestroy hoặc context.close().

### 18.2. Không dùng System.exit() trong business code

Gọi System.exit() từ một service hoặc controller có thể kết thúc cả JVM và ảnh hưởng mọi request đang chạy.

Nếu một thao tác cần dừng ứng dụng, hãy chuyển yêu cầu tới cơ chế quản lý process/deployment hoặc một orchestration component có quyền rõ ràng. Không để logic nghiệp vụ tùy tiện kết thúc toàn bộ process.

### 18.3. SIGTERM và SIGKILL khác nhau

Trên môi trường Unix/container:

- SIGTERM thường cho process cơ hội shutdown bình thường; JVM có thể chạy shutdown hooks.
- SIGINT cũng thường khởi động quá trình shutdown JVM.
- SIGKILL kết thúc process ngay lập tức; shutdown hooks không được chạy.

Do đó, container cần termination grace period đủ dài và ứng dụng cần shutdown nhanh, có giới hạn.

Không dựa vào @PreDestroy để bảo đảm công việc quan trọng được hoàn thành khi process có thể bị kill cưỡng bức.

### 18.4. Không đăng ký nhiều shutdown hooks cho cùng resource

Nếu Spring đã quản lý client bean và một hook riêng cũng đóng client đó, có thể xảy ra cleanup lặp hoặc sai thứ tự.

Chọn một owner duy nhất và để lifecycle container gọi đúng callback.

## 19. Thứ tự cleanup giữa các bean

Một bean có thể phụ thuộc vào bean khác trong quá trình hoạt động và cả khi shutdown.

Ví dụ:

~~~text
OrderEventConsumer
       │ sử dụng
       ▼
MessageTransport
       │ sử dụng
       ▼
NetworkConnectionPool
~~~

Khi dừng, consumer nên ngừng nhận message trước, transport dừng sau và connection pool được đóng khi không còn component nào sử dụng.

### 19.1. Dependency graph giúp Spring xác định thứ tự

Khi bean A có constructor dependency tới bean B, Spring biết A phụ thuộc B. Trong cleanup singleton, dependent bean thường được hủy trước dependency mà nó cần, để A có thể giải phóng tài nguyên khi B vẫn còn khả dụng.

Đây là một lý do nữa để khai báo dependency bằng constructor thay vì tìm bean thủ công qua ApplicationContext.

### 19.2. @DependsOn cho dependency lifecycle không thể hiện qua injection

Nếu có một quan hệ thứ tự khởi tạo/hủy mà không thể hiện qua constructor dependency, có thể dùng @DependsOn:

~~~java
@Bean
ResourceRegistry resourceRegistry() {
    return new ResourceRegistry();
}

@Bean
@DependsOn("resourceRegistry")
WorkerService workerService() {
    return new WorkerService();
}
~~~

WorkerService được tạo sau ResourceRegistry; khi singleton beans bị destroy, bean phụ thuộc thường được hủy trước bean mà nó phụ thuộc.

Không dùng @DependsOn để thay constructor injection nếu WorkerService thật sự cần ResourceRegistry. Hãy inject dependency trực tiếp; @DependsOn chỉ phù hợp cho quan hệ ordering đặc biệt không được thể hiện bằng dependency reference.

### 19.3. SmartLifecycle stop diễn ra trước destroy callbacks

Trong shutdown flow của ApplicationContext, lifecycle components được yêu cầu stop trước khi singleton beans được destroy. Điều này giúp consumer dừng hoạt động trước khi các tài nguyên cấp thấp bị đóng.

Một thiết kế điển hình:

1. SmartLifecycle consumer ngừng nhận message và chờ xử lý đang chạy.
2. Các worker/executors được dừng theo policy.
3. @PreDestroy hoặc destroyMethod đóng client/pool.

Thứ tự cụ thể phụ thuộc phase và dependency graph. Hãy thiết kế phase phù hợp, không dựa vào tên bean hoặc thứ tự file.

### 19.4. Tránh cleanup phụ thuộc một bean đã bị destroy

Nếu @PreDestroy của A cần gọi B, hãy bảo đảm lifecycle/dependency graph khiến B vẫn còn sẵn sàng khi A cleanup. Nếu không thể biểu đạt rõ, hãy chuyển resource ownership về một bean duy nhất hoặc tạo một coordinator có lifecycle được xác định.

Đừng để hai destroy methods gọi lẫn nhau mà không có thứ tự ổn định.

## 20. Xử lý lỗi trong quá trình cleanup

Cleanup cũng có thể thất bại:

- Client close ném IOException.
- Executor không kết thúc trong timeout.
- Message consumer không thể ack/commit message.
- File flush thất bại vì disk đầy.
- Remote resource không phản hồi.

### 20.1. Không che mất lỗi cleanup

Không:

~~~java
@PreDestroy
void close() {
    try {
        client.close();
    } catch (Exception ignored) {
        // Bỏ qua hoàn toàn.
    }
}
~~~

Nếu lỗi cleanup có ý nghĩa vận hành, hãy ghi nhận bằng logger phù hợp:

~~~java
@PreDestroy
void close() {
    try {
        client.close();
    } catch (Exception ex) {
        log.warn("Could not close partner client cleanly", ex);
    }
}
~~~

Thông báo không nên chứa secret hoặc thông tin nhạy cảm. Cần cân nhắc rằng logging backend cũng có thể đang shutdown; tránh phụ thuộc vào một remote appender có thể đã dừng.

### 20.2. Cleanup nên có giới hạn thời gian

Một callback chờ vô hạn có thể làm process không kết thúc. Với executor/client/consumer, đặt timeout cụ thể và xác định hành vi khi hết thời gian:

- Tiếp tục chờ trong một giới hạn khác?
- Hủy/interrupt task?
- Đóng kết nối ngay?
- Ghi nhận số tác vụ chưa hoàn thành?

Chính sách phụ thuộc nghiệp vụ. Không có một lựa chọn chung cho mọi hệ thống.

### 20.3. Đừng ném exception cleanup để giả vờ startup thành công

Nếu init callback thất bại, không thể dùng destroy callback để che lỗi và làm context tiếp tục hoạt động. Cleanup chỉ giải phóng tài nguyên đã được tạo; nó không sửa điều kiện startup ban đầu.

### 20.4. Cleanup có thể cần idempotent

Một phương thức close/stop có thể được gọi từ nhiều đường lifecycle trong một số thiết kế hoặc do code chủ động retry. Nếu contract yêu cầu gọi lặp an toàn, hãy bảo đảm:

- Không đóng tài nguyên đã đóng theo cách gây lỗi.
- Không submit task sau khi đã stop.
- Không flush/commit dữ liệu hai lần gây side effect.
- Trạng thái running/closed được cập nhật an toàn giữa các thread.

Đừng tự giả định thư viện bên thứ ba có close idempotent; kiểm tra API của nó.

## 21. Tách initialization khỏi readiness và health

Một resource có thể mở thành công trong @PostConstruct nhưng dịch vụ bên ngoài mất kết nối sau đó. Ngược lại, một hệ thống bên ngoài có thể tạm thời chưa sẵn sàng lúc startup.

Hãy quyết định chính sách:

- **Fail-fast:** ứng dụng không thể phục vụ an toàn nếu resource không sẵn sàng.
- **Retry có giới hạn:** startup chờ trong một khoảng xác định.
- **Degraded mode:** ứng dụng vẫn phục vụ một số chức năng, còn chức năng phụ bị vô hiệu hóa.
- **Lazy connect:** chỉ mở kết nối khi thực sự cần.

### 21.1. Không dùng @PostConstruct để ping mọi dependency vô hạn

Ví dụ:

~~~java
@PostConstruct
void waitUntilPartnerIsReady() {
    while (!partnerClient.isHealthy()) {
        // Chờ vô hạn.
    }
}
~~~

Điều này có thể khiến context không bao giờ refresh và deployment không thể đánh giá startup state.

Nếu cần chờ dependency, hãy có timeout, backoff, logging và quyết định rõ startup fail hay degraded mode.

### 21.2. Health indicator phục vụ trạng thái runtime

Spring Boot Actuator có thể cung cấp health endpoints để quan sát thành phần phụ thuộc sau khi ứng dụng đã chạy.

Health indicator không tự giải phóng tài nguyên và không thay lifecycle callback. Nó giúp người vận hành biết trạng thái; lifecycle chịu trách nhiệm start/stop/cleanup.

### 21.3. Readiness khác liveness

- Readiness cho biết instance có nên nhận traffic hay chưa.
- Liveness cho biết process/container có cần restart do trạng thái không thể phục hồi hay không.

Không đánh dấu một ứng dụng unhealthy chỉ vì một tính năng phụ tùy chọn tạm thời không khả dụng, nếu hệ thống được thiết kế để hoạt động ở degraded mode.

## 22. Quản lý listener và message consumer

Message consumer thường giữ socket, subscription, thread hoặc connection tới broker. Nó cần start/stop có thứ tự.

Một lifecycle phù hợp:

~~~text
Context refresh
      │
      ▼
Mở connection / đăng ký subscription
      │
      ▼
Nhận message
      │
      ▼
Shutdown bắt đầu
      │
      ▼
Ngừng nhận message mới
      │
      ▼
Chờ message đang xử lý / ack / commit
      │
      ▼
Đóng subscription
      │
      ▼
Đóng broker client/pool
~~~

### 22.1. Phân biệt stop consumer và close client

Consumer có thể chỉ quản lý subscription; client/connection pool được chia sẻ bởi nhiều consumers.

Trong trường hợp đó:

- Consumer stop: dừng subscription của nó.
- Client owner close: đóng kết nối khi tất cả consumers đã dừng.

Không để một consumer đóng shared broker client khi các consumer khác vẫn đang dùng.

### 22.2. Xử lý message đang chạy

Khi shutdown:

- Message đang xử lý có được phép hoàn tất không?
- Có cần ack/commit trước timeout không?
- Nếu timeout, message được redeliver hay bị bỏ?
- Handler có idempotent để xử lý redelivery không?

Đây là contract của messaging system và nghiệp vụ, không thể giải quyết chỉ bằng @PreDestroy.

### 22.3. Không ack message chỉ vì shutdown

Không nên đánh dấu message đã xử lý thành công nếu business operation chưa hoàn tất. Nếu cần dừng, hãy dùng semantics của broker để release/requeue hoặc để message được redeliver theo policy.

Shutdown đúng phải bảo toàn tính đúng đắn của xử lý message, không chỉ làm thread biến mất.

## 23. Cache và tài nguyên có vòng đời riêng

Một cache local có thể cần:

- Đóng scheduler cleanup.
- Dừng refresh thread.
- Flush persistence nếu cache hỗ trợ write-behind.
- Giải phóng native memory hoặc resource ngoài heap.

Nếu cache là bean do Spring quản lý, xác định API close/stop của thư viện và khai báo destroy method phù hợp.

### 23.1. Cache không đồng nghĩa với dữ liệu bền vững

Không dựa vào cache destroy callback để ghi toàn bộ business data quan trọng. Process có thể bị kill trước cleanup; cache có thể có write-behind queue chưa flush.

Dữ liệu cần bền vững nên được commit qua storage/transaction phù hợp trong lúc xử lý nghiệp vụ.

### 23.2. Scheduled refresh cần dừng trước khi đóng cache

Nếu một scheduler định kỳ refresh cache, shutdown nên dừng scheduler trước, sau đó mới đóng cache hoặc client mà refresh task dùng.

Có thể dùng SmartLifecycle phases hoặc để một bean owner duy nhất quản lý cả scheduler và cache nếu chúng có cùng vòng đời.

## 24. Quản lý resource ở nhiều ApplicationContext

Một số ứng dụng có parent/child ApplicationContext. Resource được tạo trong parent có thể được dùng bởi beans ở child.

Ví dụ:

~~~text
Parent ApplicationContext
  └── SharedDataSource
  └── SharedHttpClient

Child ApplicationContext
  └── WebController
  └── RequestService
~~~

Khi child đóng, parent có thể vẫn sống. Do đó:

- Child không nên đóng SharedDataSource của parent.
- Parent chỉ đóng shared resources khi chính parent kết thúc.
- Bean không nên giả định context chứa nó là context cuối cùng của toàn process.

### 24.1. Scope ownership theo context

Resource nên được tạo trong context có vòng đời phù hợp với consumer. Nếu resource dùng chung cho nhiều child contexts, tạo ở parent có thể hợp lý.

Nếu mỗi child cần client riêng, đăng ký ở child để lifecycle của child sở hữu client đó.

### 24.2. Tránh đóng parent context từ child bean

Một bean trong child không nên gọi parent.close() chỉ vì nó đã kết thúc nhiệm vụ. Điều đó có thể làm những child contexts khác và shared resources ngừng hoạt động.

Để component quản lý context hoặc deployment điều phối vòng đời toàn bộ application.

## 25. Thứ tự callback khởi tạo và hủy

Với một bean được quản lý theo lifecycle chuẩn, thứ tự callback thường gặp:

| Giai đoạn khởi tạo | Callback |
|---|---|
| Sau dependency injection | @PostConstruct |
| Sau đó | InitializingBean.afterPropertiesSet() |
| Cuối cùng trong custom initialization callbacks | initMethod được khai báo |

Trong quá trình destroy:

| Giai đoạn hủy | Callback |
|---|---|
| Đầu tiên | @PreDestroy |
| Sau đó | DisposableBean.destroy() |
| Cuối cùng trong custom destroy callbacks | destroyMethod được khai báo |

Đây là thứ tự giữa những cơ chế callback của một bean trong lifecycle hỗ trợ. BeanPostProcessor còn có thể bao quanh initialization và tạo proxy; các lifecycle-aware components có thể có bước stop riêng trước khi destroy callbacks.

### 25.1. Không phụ thuộc vào thứ tự callback nếu không cần

Nếu @PreDestroy và destroyMethod đều đóng cùng một client, cleanup có thể bị lặp. Hãy chọn một nơi thực hiện hành động đóng chính.

Nếu có nhiều bước:

~~~java
@PreDestroy
void shutdown() {
    stopAcceptingWork();
    flushPendingState();
    closeClient();
}
~~~

Một method có thứ tự rõ ràng có thể dễ hiểu hơn nhiều callbacks rời rạc, miễn các bước thuộc cùng một owner và có policy xử lý lỗi phù hợp.

### 25.2. Bean khởi tạo thất bại giữa chừng cần tự cleanup phần đã mở

Một trường hợp dễ bỏ sót:

~~~java
@PostConstruct
void initialize() {
    resource = resourceFactory.open();
    resource.configure(); // Có thể ném exception.
}
~~~

Nếu configure() thất bại, bean chưa hoàn tất initialization. Không nên dựa vào destroy callback của bean để chắc chắn resource vừa mở sẽ được đóng.

Hãy xử lý cleanup ngay trong initialization:

~~~java
@PostConstruct
void initialize() {
    ResourceHandle candidate = resourceFactory.open();

    try {
        candidate.configure();
        this.resource = candidate;
    } catch (RuntimeException ex) {
        try {
            candidate.close();
        } catch (Exception closeError) {
            ex.addSuppressed(closeError);
        }
        throw ex;
    }
}
~~~

Ví dụ này giả định close() có thể ném checked exception và configure() ném RuntimeException. Điều quan trọng là resource chỉ được gán vào field sau khi khởi tạo thành công; nếu thất bại, candidate được đóng trước khi lỗi được ném lại.

### 25.3. Factory method cũng phải cleanup nếu tạo bean thất bại

Nếu @Bean method mở một resource rồi ném exception trước khi trả object cho Spring, container chưa nhận được bean instance để quản lý destroy callback.

Hãy bảo đảm factory method đóng resource nếu quá trình tạo/configure thất bại:

~~~java
@Bean(destroyMethod = "close")
PartnerClient partnerClient() {
    PartnerClient client = new PartnerClient();
    try {
        client.initialize();
        return client;
    } catch (RuntimeException ex) {
        try {
            client.close();
        } catch (Exception closeError) {
            ex.addSuppressed(closeError);
        }
        throw ex;
    }
}
~~~

Khi factory method trả về thành công, Spring nhận ownership theo cấu hình bean và có thể gọi destroy method khi context đóng.

## 26. Kiểm thử @PostConstruct và @PreDestroy

Một lifecycle test nên chứng minh callback được gọi đúng khi context refresh và close.

Ví dụ JUnit 5:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ResourceLifecycleTests {

    @Test
    void callsInitializationAndDestroyCallbacks() {
        AtomicInteger initialized = new AtomicInteger();
        AtomicInteger destroyed = new AtomicInteger();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(
                    LifecycleProbe.class,
                    () -> new LifecycleProbe(initialized, destroyed));

            context.refresh();

            assertThat(initialized.get()).isEqualTo(1);
            assertThat(destroyed.get()).isZero();
        }

        assertThat(destroyed.get()).isEqualTo(1);
    }

    static class LifecycleProbe {

        private final AtomicInteger initialized;
        private final AtomicInteger destroyed;

        LifecycleProbe(
                AtomicInteger initialized,
                AtomicInteger destroyed) {
            this.initialized = initialized;
            this.destroyed = destroyed;
        }

        @PostConstruct
        void initialize() {
            initialized.incrementAndGet();
        }

        @PreDestroy
        void close() {
            destroyed.incrementAndGet();
        }
    }
}
~~~

Test này tạo một context thật, refresh để chạy initialization và đóng context bằng try-with-resources. Sau khi block kết thúc, destroy callback phải được gọi.

### 26.1. Test destroyMethod của @Bean

~~~java
@Test
void invokesConfiguredDestroyMethod() {
    AtomicBoolean closed = new AtomicBoolean();

    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

        context.registerBean(
                ClientConfigurationForTest.class,
                () -> new ClientConfigurationForTest(closed));
        context.refresh();

        assertThat(closed).isFalse();
    }

    assertThat(closed).isTrue();
}

static class ClientConfigurationForTest {

    private final AtomicBoolean closed;

    ClientConfigurationForTest(AtomicBoolean closed) {
        this.closed = closed;
    }

    @Bean(destroyMethod = "close")
    TestClient testClient() {
        return new TestClient(closed);
    }
}

static class TestClient {

    private final AtomicBoolean closed;

    TestClient(AtomicBoolean closed) {
        this.closed = closed;
    }

    public void close() {
        closed.set(true);
    }
}
~~~

Đây là ví dụ minh họa ý tưởng test callback; khi viết test thật, configuration class cần được đăng ký như một configuration class được Spring xử lý, ví dụ dùng @Configuration hoặc register/import bean definitions phù hợp.

### 26.2. Dùng ApplicationContextRunner

ApplicationContextRunner tự đóng context sau callback. Có thể kiểm tra:

~~~java
AtomicBoolean destroyed = new AtomicBoolean();

new ApplicationContextRunner()
        .withBean(
                LifecycleProbe.class,
                () -> new LifecycleProbe(destroyed))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(destroyed).isFalse();
        });

assertThat(destroyed).isTrue();
~~~

Test kiểm tra trạng thái sau khi run() hoàn tất, lúc runner đã đóng context.

### 26.3. Kiểm thử shutdown bất đồng bộ

Với SmartLifecycle, cần xác nhận:

- start được gọi khi context refresh nếu autoStartup=true.
- isRunning phản ánh trạng thái.
- stop được gọi khi context đóng.
- Callback trong stop(Runnable) được gọi sau khi công việc dừng.
- Shutdown không treo quá timeout.

Nếu test dùng asynchronous completion, dùng latch/future có timeout hữu hạn; không chờ vô hạn làm test suite bị treo.

## 27. Theo dõi resource leak trong runtime

Một ứng dụng có thể chạy nhiều giờ trước khi resource leak trở nên rõ ràng. Một số dấu hiệu:

- Số lượng thread tăng dần.
- Connection pool thường xuyên cạn.
- File descriptor/socket count tăng.
- Heap giữ nhiều buffer/session không còn dùng.
- Scheduled tasks tiếp tục chạy sau khi feature đã tắt.
- JVM không kết thúc sau khi context đóng.

### 27.1. Thread dump

Thread dump giúp xem:

- Thread nào đang chạy.
- Thread thuộc executor/client nào.
- Có thread đang chờ vô hạn hoặc deadlock không.
- Executor có worker còn sống sau shutdown không.

Nếu process không thoát, đừng chỉ tăng thời gian termination. Hãy xác định thread/resource nào còn giữ JVM sống.

### 27.2. Metrics

Theo dõi những chỉ số phù hợp:

- Active/idle/pending connections của pool.
- Active threads, queue size, rejected tasks.
- HTTP connection pool utilization.
- Scheduled task duration/failure.
- File system usage.
- Message consumer lag và inflight messages.

Metrics giúp nhận diện xu hướng leak trước khi process gặp sự cố.

### 27.3. Actuator và Micrometer

Spring Boot Actuator/Micrometer có thể expose nhiều metrics cho datasource, JVM, executor hoặc web server tùy dependencies và instrumentation.

Không phải mọi resource custom tự động có metrics. Với custom pool/client, có thể cần instrumentation riêng hoặc adapter metrics.

### 27.4. Quan sát startup/shutdown logs

Một lifecycle component có thể log mốc start/stop:

~~~java
log.info("Starting order event consumer");
log.info("Stopping order event consumer");
log.info("Order event consumer stopped");
~~~

Giữ message ngắn và có component identity. Không log payload hoặc credential. Khi nhiều replica, thêm instance/service identity an toàn để phân biệt.

## 28. Các lỗi thường gặp khi quản lý tài nguyên

### 28.1. Mở file nhưng không đóng

**Dấu hiệu:** số file handle tăng, file có thể bị lock hoặc process dùng hết descriptor.

**Nguyên nhân:** mở InputStream/OutputStream mà không đóng trong mọi nhánh.

**Cách xử lý:** dùng try-with-resources cho resource cục bộ.

### 28.2. Đóng injected singleton sau mỗi request

**Dấu hiệu:** request đầu thành công, request sau lỗi client đã đóng.

**Nguyên nhân:** consumer đóng tài nguyên mà nó chỉ mượn.

**Cách xử lý:** xác định owner bean; chỉ owner/container đóng shared resource.

### 28.3. Prototype bean không được cleanup

**Dấu hiệu:** nhiều instance prototype mở resource nhưng không có destroy callback tương ứng.

**Nguyên nhân:** Spring không tự quản lý đầy đủ destruction cho prototype instance sau khi giao cho caller.

**Cách xử lý:** caller đóng instance, thường qua AutoCloseable/try-with-resources.

### 28.4. Inject prototype trực tiếp vào singleton

**Dấu hiệu:** mong đợi mỗi lần gọi method có instance mới nhưng thực tế dùng cùng instance.

**Nguyên nhân:** prototype được resolve khi singleton tạo.

**Cách xử lý:** dùng ObjectProvider hoặc Provider để resolve instance theo lần cần.

### 28.5. Executor làm JVM không thoát

**Dấu hiệu:** log shutdown đã xuất hiện nhưng process vẫn còn.

**Nguyên nhân:** executor hoặc thread tự tạo chưa shutdown/interrupt.

**Cách xử lý:** quản lý executor như bean và đặt shutdown policy; không tạo thread không có stop signal.

### 28.6. @PreDestroy không được gọi khi kill -9

**Dấu hiệu:** cleanup không xảy ra khi process bị terminate cưỡng bức.

**Nguyên nhân:** JVM không có cơ hội chạy shutdown hooks.

**Cách xử lý:** dùng graceful termination, timeout phù hợp và thiết kế dữ liệu bền vững không phụ thuộc cleanup hook.

### 28.7. Cleanup chạy hai lần

**Dấu hiệu:** close client bị gọi nhiều lần, lỗi hoặc log trùng.

**Nguyên nhân:** cả consumer và bean owner cùng đóng resource; hoặc annotation và destroyMethod cùng gọi một hành động.

**Cách xử lý:** xác định một owner duy nhất, một đường cleanup chính; bảo đảm idempotent nếu contract cho phép.

### 28.8. @PostConstruct mở resource rồi lỗi giữa chừng

**Dấu hiệu:** context startup thất bại nhưng socket/file handle vừa mở còn tồn tại.

**Nguyên nhân:** bean chưa hoàn tất initialization nên destroy callback không phải cơ chế cleanup đáng tin cậy cho resource cục bộ vừa mở.

**Cách xử lý:** cleanup ngay trong catch trước khi ném lại exception; chỉ chuyển resource sang field khi initialization thành công.

### 28.9. Runner startup chạy vô hạn

**Dấu hiệu:** app không bao giờ đạt ready.

**Nguyên nhân:** ApplicationRunner chờ external system hoặc chạy job không giới hạn.

**Cách xử lý:** đặt timeout/retry policy, tách job dài sang background worker hoặc job runner riêng.

### 28.10. @PostConstruct gọi bean khác quá sớm

**Dấu hiệu:** lỗi circular dependency, initialization order khó đoán hoặc side effects chạy trước khi context sẵn sàng.

**Nguyên nhân:** callback của một bean kích hoạt nhiều bean khác.

**Cách xử lý:** giữ callback đơn giản; dùng ApplicationRunner/event nếu cần phối hợp sau context refresh.

### 28.11. Scheduler tiếp tục gọi client đã đóng

**Dấu hiệu:** exception xuất hiện trong lúc shutdown hoặc sau khi context đóng.

**Nguyên nhân:** scheduled tasks chưa dừng trước khi dependency bị destroy.

**Cách xử lý:** dừng scheduling/consumer trước; đặt lifecycle phase và shutdown policy rõ.

### 28.12. DataSource bị đóng từ repository

**Dấu hiệu:** các repository khác lỗi connection pool đã shutdown.

**Nguyên nhân:** bean consumer đóng shared DataSource.

**Cách xử lý:** đóng JDBC Connection theo transaction/operation; để DataSource owner/container đóng pool.

### 28.13. Graceful shutdown timeout quá ngắn

**Dấu hiệu:** request/task đang chạy bị terminate khi deploy.

**Nguyên nhân:** timeout Spring hoặc deployment thấp hơn thời gian xử lý thực tế.

**Cách xử lý:** đo thời gian shutdown, đặt timeout hợp lý và bảo đảm process manager cấp đủ termination grace period.

### 28.14. Graceful shutdown timeout quá dài

**Dấu hiệu:** rollout/scale-down chậm, instance giữ tài nguyên lâu.

**Nguyên nhân:** chờ vô hạn hoặc timeout lớn hơn mức vận hành cho phép.

**Cách xử lý:** giới hạn thời gian, có cancellation/fallback và đo số tác vụ còn lại.

### 28.15. Context đóng nhưng client thread vẫn sống

**Dấu hiệu:** JVM không kết thúc hoặc thread dump còn event loop/client worker.

**Nguyên nhân:** destroy method không gọi đúng API close/dispose của thư viện.

**Cách xử lý:** kiểm tra lifecycle contract của client và xác nhận thread/pool đã kết thúc sau context close.

### 28.16. Dùng ContextClosedEvent để thay mọi destroy callbacks

**Dấu hiệu:** nhiều listener đóng cùng một resource hoặc thứ tự cleanup không rõ.

**Nguyên nhân:** ownership bị dồn vào event handler toàn cục.

**Cách xử lý:** dùng destroy callback ở bean owner; chỉ dùng event để điều phối khi có yêu cầu thực sự.

### 28.17. Đóng parent resource từ child context

**Dấu hiệu:** một web context đóng làm context khác mất datasource/client.

**Nguyên nhân:** child đóng resource được parent sở hữu.

**Cách xử lý:** phân định ownership theo context và chỉ owner context đóng resource.

### 28.18. Dựa vào @PreDestroy để commit dữ liệu quan trọng

**Dấu hiệu:** dữ liệu chưa được ghi nếu process bị kill hoặc shutdown timeout.

**Nguyên nhân:** cleanup hook không phải cơ chế durability.

**Cách xử lý:** commit dữ liệu trong transaction nghiệp vụ hoặc durable outbox/storage; destroy callback chỉ flush phần resource có thể flush an toàn.

## 29. Một ví dụ tổng hợp: quản lý message consumer và client

Giả sử ứng dụng cần nhận order events từ một message broker:

- Broker client có connection pool và phải được đóng khi ứng dụng dừng.
- Consumer đăng ký subscription khi ứng dụng sẵn sàng.
- Khi shutdown, consumer phải ngừng nhận message và chờ xử lý đang chạy.
- Client chỉ được đóng sau khi consumer dừng.

Có thể tách ownership thành hai bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class MessagingResourceConfiguration {

    @Bean(destroyMethod = "close")
    MessageTransport messageTransport() {
        return MessageTransport.create();
    }
}
~~~

MessageTransport là class minh họa có public close method.

Consumer:

~~~java
@Component
public class OrderEventConsumer implements SmartLifecycle {

    private final MessageTransport transport;
    private volatile boolean running;

    public OrderEventConsumer(MessageTransport transport) {
        this.transport = transport;
    }

    @Override
    public void start() {
        transport.subscribe("order-events");
        running = true;
    }

    @Override
    public void stop() {
        if (running) {
            transport.stopSubscription("order-events");
            running = false;
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Đây là code minh họa ownership và thứ tự. Trong triển khai thật, cần bảo đảm stopSubscription có semantics dừng nhận message mới và chờ inflight messages theo timeout. Nếu stop là async, callback chỉ được gọi khi việc dừng hoàn tất.

### 29.1. Thứ tự mong muốn

~~~text
Startup:
MessageTransport được tạo
          │
          ▼
OrderEventConsumer.start()
          │
          ▼
Subscription nhận message

Shutdown:
OrderEventConsumer.stop()
          │
          ▼
Subscription dừng / inflight xử lý xong
          │
          ▼
MessageTransport.close()
~~~

Consumer giữ reference tới transport, nên dependency graph và lifecycle phase giúp transport còn tồn tại trong lúc consumer dừng.

### 29.2. Ai đóng transport?

Trong ví dụ, bean factory tạo MessageTransport và khai báo destroyMethod close. Consumer chỉ sử dụng transport để subscribe/stop subscription; nó không đóng toàn bộ client.

Nếu có nhiều consumer cùng dùng transport, càng cần một owner duy nhất cho client.

### 29.3. Nếu consumer không dừng đúng hạn?

Đặt shutdown timeout theo khả năng xử lý message và policy của broker. Khi hết thời gian:

- Ghi nhận số message chưa hoàn tất.
- Để broker redeliver nếu contract hỗ trợ.
- Không ack message chưa xử lý thành công.
- Tiếp tục cleanup client theo giới hạn shutdown.

Không chờ vô hạn và cũng không âm thầm đánh dấu message thành công chỉ để process thoát.

## 30. Thiết kế lifecycle theo loại tài nguyên

Một bảng quyết định nhanh:

| Tài nguyên | Tạo ở đâu | Dừng/đóng ở đâu |
|---|---|---|
| File stream trong một method | Trong method | try-with-resources |
| JDBC Connection thủ công | Trong operation/transaction | try-with-resources hoặc transaction manager |
| DataSource pool | Bean configuration/auto-configuration | Container destroy callback |
| HTTP client dùng chung | @Bean factory | destroyMethod/close/dispose |
| ThreadPoolTaskExecutor | @Bean configuration | Spring executor lifecycle |
| ExecutorService tự tạo | Owner bean/factory | close/destroy callback với timeout |
| Scheduled task | Scheduling infrastructure | Scheduler lifecycle/shutdown |
| Message subscription | SmartLifecycle.start() | SmartLifecycle.stop() |
| Prototype resource session | ObjectProvider.getObject() | Caller đóng instance |
| Request-scoped state | Request scope | Scope cleanup khi request kết thúc |
| File tạm | Trong task | finally/delete sau khi hoàn tất |
| Durable business event | Transaction/outbox | Không dựa vào shutdown hook |

Đừng chọn lifecycle mechanism theo thói quen. Chọn theo **vòng đời thật của resource** và **ownership**.

## 31. Những hiểu nhầm thường gặp

**“Spring tự đóng mọi object mà nó tạo.”**  
Không. Singleton beans được quản lý đầy đủ có destroy callbacks; prototype beans không được container tự quản lý destruction sau khi giao cho caller.

**“@PostConstruct là nơi phù hợp để chạy mọi công việc lúc startup.”**  
Không. Nó thuộc lifecycle của một bean. Công việc cần nhiều bean đã sẵn sàng có thể phù hợp với ApplicationRunner hoặc ApplicationReadyEvent hơn.

**“@PreDestroy luôn chạy khi process kết thúc.”**  
Không. Process bị kill cưỡng bức hoặc JVM crash có thể không chạy shutdown hooks.

**“Một bean inject client thì có quyền đóng client.”**  
Không. Sử dụng resource không đồng nghĩa sở hữu resource.

**“try-with-resources phù hợp cho mọi injected dependency.”**  
Không. Chỉ dùng khi method/caller thực sự sở hữu resource trong phạm vi block.

**“@Bean destroyMethod luôn phải khai báo thủ công.”**  
Không. Spring có thể suy luận một số public close/shutdown methods; có thể khai báo tường minh khi muốn làm rõ contract.

**“@PostConstruct và InitializingBean là hai cách phải dùng cùng lúc.”**  
Không. Chọn một callback chính cho một trách nhiệm.

**“Đóng một bean ở @PreDestroy và destroyMethod không thể trùng.”**  
Không. Nếu cùng thực hiện close, có thể cleanup lặp. Xác định một đường cleanup.

**“Prototype scope nghĩa Spring tự đóng từng instance.”**  
Không. Caller thường chịu trách nhiệm cleanup prototype instance sau khi nhận.

**“Inject prototype vào singleton sẽ tạo prototype mới mỗi lần gọi method.”**  
Không. Dependency thường được resolve khi singleton tạo; dùng ObjectProvider/Provider nếu cần instance mới theo lần gọi.

**“Thread pool tự dừng khi ApplicationContext đóng.”**  
Không nếu nó được tạo ngoài lifecycle management hoặc không có shutdown policy. Hãy quản lý executor như bean và cấu hình timeout.

**“SmartLifecycle chỉ là một cách khác để viết @PostConstruct.”**  
Không. SmartLifecycle quản lý start/stop của component, phase và asynchronous stop.

**“Phase cao được start trước.”**  
Không. Phase thấp thường start trước; khi stop, thứ tự được đảo lại.

**“Graceful shutdown bảo đảm mọi request/task hoàn tất.”**  
Không. Nó chỉ cho một khoảng thời gian hữu hạn; timeout vẫn có thể kết thúc tác vụ.

**“ContextClosedEvent thay thế destroy callback.”**  
Không. Event dùng để quan sát/điều phối; destroy callback thể hiện resource ownership trực tiếp hơn.

**“Một callback cleanup có thể chờ vô hạn.”**  
Không nên. Shutdown cần timeout để process không bị treo.

**“Có thể dùng @PreDestroy để commit transaction quan trọng.”**  
Không nên. Dữ liệu bền vững phải được commit trong transaction nghiệp vụ hoặc durable mechanism.

**“Nếu @PostConstruct thất bại, @PreDestroy chắc chắn đóng được resource đã mở.”**  
Không nên dựa vào điều đó. Initialization thất bại giữa chừng cần tự cleanup resource cục bộ trước khi ném exception.

**“Một resource dùng chung có thể được nhiều bean cùng đóng.”**  
Không nên. Một owner rõ ràng tránh đóng sớm hoặc cleanup lặp.

**“Actuator health tự quản lý resource.”**  
Không. Health chỉ quan sát trạng thái; lifecycle callbacks/owner chịu trách nhiệm start/stop/close.

## 32. Quy trình thiết kế và kiểm tra resource lifecycle

Khi một bean cần mở hoặc giữ tài nguyên, có thể đi theo trình tự:

### Bước 1 — Xác định loại tài nguyên

Là file/stream cục bộ, database connection, connection pool, executor, scheduler, HTTP client, message subscription hay cache?

Đọc API để biết resource có close(), shutdown(), dispose() hay lifecycle contract riêng.

### Bước 2 — Xác định ownership

Ai tạo? Ai dùng? Ai đóng? Có được chia sẻ giữa nhiều bean không?

Chỉ định một owner chịu trách nhiệm cleanup.

### Bước 3 — Chọn phạm vi vòng đời

- Method/task → try-with-resources hoặc finally.
- Bean/application → Spring bean lifecycle.
- Prototype instance → caller cleanup.
- Request/session → scope lifecycle.
- Component cần start/stop → Lifecycle/SmartLifecycle.

### Bước 4 — Chọn callback phù hợp

- Initialization đơn giản → @PostConstruct hoặc initMethod.
- Cleanup singleton → @PreDestroy, destroyMethod hoặc DisposableBean.
- Component có hoạt động nền → SmartLifecycle.
- Startup action cần context refresh → ApplicationRunner.

### Bước 5 — Thiết kế thứ tự

Consumer dừng trước transport; worker dừng trước client; scheduler dừng trước resource mà task sử dụng.

Dùng dependency graph, phase hoặc @DependsOn chỉ khi cần thiết và có contract rõ.

### Bước 6 — Đặt timeout

Chọn timeout cho:

- Chờ task hoàn tất.
- Dừng consumer.
- Đóng client.
- Web server graceful shutdown.
- Toàn bộ process termination grace period.

Không để một resource giữ process sống vô hạn.

### Bước 7 — Xử lý lỗi giữa initialization

Nếu resource đã mở nhưng callback/factory method còn có thể thất bại, tự đóng resource trước khi ném exception. Chỉ chuyển ownership sang bean sau khi khởi tạo thành công.

### Bước 8 — Kiểm thử

Test init callback, destroy callback, close method, lifecycle start/stop và trường hợp startup failure. Dùng timeout hữu hạn cho asynchronous cleanup.

### Bước 9 — Quan sát runtime

Theo dõi thread count, pool usage, queue size, open connections và shutdown logs. Kiểm tra thread dump nếu JVM không thoát.

### Bước 10 — Kiểm tra deployment

Đảm bảo systemd/container/Kubernetes cấp đủ thời gian graceful shutdown và không kill process trước khi lifecycle hoàn tất.

### Sơ đồ quyết định

~~~text
Ứng dụng cần một resource
          │
          ▼
Resource chỉ dùng trong một operation?
          │
      ┌───┴────┐
      │        │
     Có       Không
      │        │
      ▼        ▼
try-with-   Resource sống theo bean/
resources   component scope?
                │
            ┌───┴────┐
            │        │
           Có       Không
            │        │
            ▼        ▼
      Spring bean   Caller/scope/
      lifecycle     external owner
            │
            ▼
      Cần start/stop
      bất đồng bộ?
            │
        ┌───┴────┐
        │        │
       Có       Không
        │        │
        ▼        ▼
 SmartLifecycle  init/destroy callback
~~~

## 33. Bài tập tự luyện

### Bài tập 1 — Chọn owner cho HTTP client

Một singleton PartnerGateway inject một HTTP client dùng chung. Mỗi method send() đều được gọi từ nhiều request.

**Câu hỏi:** PartnerGateway có nên đóng client sau mỗi lần send không?

**Đáp án định hướng:** Không. Gateway chỉ sử dụng client. Bean factory hoặc bean owner chịu trách nhiệm close client khi context shutdown.

### Bài tập 2 — Prototype resource

Một CsvImportSession prototype mở một file handle. ImportCoordinator là singleton và cần session mới cho mỗi file.

**Câu hỏi:** Inject CsvImportSession trực tiếp có tạo instance mới cho từng file không? Ai đóng session?

**Đáp án:** Không. Prototype được resolve khi singleton tạo nếu inject trực tiếp. Dùng ObjectProvider để lấy instance mới cho từng file; caller đóng instance sau khi import, ví dụ try-with-resources nếu nó implement AutoCloseable.

### Bài tập 3 — Chọn callback

Một bean cần xây index nội bộ sau khi repository đã inject.

**Câu hỏi:** Dùng callback nào?

**Đáp án định hướng:** @PostConstruct hoặc InitializingBean/custom init method. Giữ initialization ngắn và không phụ thuộc vào mọi bean trong context đã sẵn sàng.

### Bài tập 4 — Chạy công việc sau startup

Một bước kiểm tra cần dùng nhiều bean và chỉ chạy sau khi context refresh.

**Câu hỏi:** @PostConstruct của một bean bất kỳ có phải lựa chọn tốt nhất?

**Đáp án:** Không nhất thiết. ApplicationRunner phù hợp hơn nếu cần chạy sau context refresh; ApplicationReadyEvent nếu cần chờ startup flow hoàn tất và ứng dụng đã ready.

### Bài tập 5 — Executor không dừng

Ứng dụng đã log ContextClosedEvent nhưng JVM vẫn sống do thread worker.

**Câu hỏi:** Cần kiểm tra gì?

**Đáp án định hướng:** Executor có được đăng ký làm bean không, destroy callback có shutdown không, task có bị chặn vô hạn không, thread có thể interrupt không, và await termination có timeout không.

### Bài tập 6 — @PreDestroy không chạy sau khi pod bị kill

Pod bị kill cưỡng bức và cleanup không xuất hiện.

**Câu hỏi:** Đây có phải lỗi Spring lifecycle?

**Đáp án:** Không nhất thiết. SIGKILL/JVM crash không chạy shutdown hooks. Cần termination grace period phù hợp và thiết kế durability không phụ thuộc cleanup hook.

### Bài tập 7 — Message consumer và transport

Consumer và transport dùng chung broker connection.

**Câu hỏi:** Thành phần nào nên dừng trước?

**Đáp án định hướng:** Consumer ngừng nhận message và xử lý inflight trước; sau đó owner đóng transport/connection pool.

### Bài tập 8 — Resource mở rồi init thất bại

@PostConstruct mở socket rồi configure() ném exception.

**Câu hỏi:** Có nên chờ @PreDestroy đóng socket không?

**Đáp án:** Không nên dựa vào đó vì bean chưa hoàn tất initialization. Hãy đóng socket ngay trong catch và ném lại exception gốc, thêm close failure dưới dạng suppressed nếu cần.

### Bài tập 9 — Context có parent và child

Parent sở hữu DataSource dùng chung. Child context đóng.

**Câu hỏi:** Child bean có nên đóng DataSource không?

**Đáp án:** Không. Parent là owner; child chỉ sử dụng. DataSource chỉ được đóng khi parent context kết thúc.

### Bài tập 10 — Chọn cơ chế shutdown

Một component nhận message liên tục và cần dừng bất đồng bộ, có phase phụ thuộc transport.

**Câu hỏi:** @PreDestroy có đủ không?

**Đáp án định hướng:** Có thể chưa đủ. SmartLifecycle phù hợp hơn để quản lý start/stop, phase và callback hoàn tất dừng bất đồng bộ; resource cấp thấp vẫn được đóng qua destroy callback của owner.

## Ghi nhớ cốt lõi

**Quản lý tài nguyên bắt đầu từ ownership.** Thành phần tạo và sở hữu resource chịu trách nhiệm đóng nó; bean chỉ inject để sử dụng không được tự ý đóng shared resource. Resource ngắn hạn nên được giới hạn bằng try-with-resources; resource sống cùng ứng dụng nên có owner bean và destroy callback rõ ràng.

Spring cung cấp **@PostConstruct/@PreDestroy**, **InitializingBean/DisposableBean** và **@Bean initMethod/destroyMethod** để hoàn tất initialization và cleanup. **Singleton** được container quản lý destruction khi context đóng; **prototype** được tạo nhưng caller phải chịu trách nhiệm cleanup sau khi nhận instance. **Lifecycle/SmartLifecycle** phù hợp với component cần start/stop, thứ tự phase hoặc shutdown bất đồng bộ.

Một shutdown an toàn cần ngừng nhận việc mới, chờ request/task/message đang chạy trong thời gian hữu hạn, rồi đóng executor, consumer, client và connection pool theo đúng dependency order. Graceful shutdown và @PreDestroy không bảo đảm chạy khi process bị kill cưỡng bức; dữ liệu quan trọng phải được bảo vệ bằng transaction/durable storage trong quá trình nghiệp vụ.

Khi thiết kế bean, hãy xác định resource thuộc phạm vi method, bean, scope hay toàn ứng dụng; chọn callback phù hợp; cleanup ngay nếu initialization thất bại giữa chừng; đặt timeout; và kiểm thử cả lúc tạo lẫn lúc đóng context. Nhờ đó, ứng dụng Spring Boot có thể giải phóng tài nguyên có trật tự, tránh leak và dừng ổn định khi triển khai hoặc nâng cấp.


