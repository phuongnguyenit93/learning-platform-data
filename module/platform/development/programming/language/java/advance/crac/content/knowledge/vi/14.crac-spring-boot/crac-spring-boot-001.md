# Điều kiện tích hợp Spring Framework, Spring Boot và org.crac

Spring Framework và Spring Boot cung cấp cấu trúc ứng dụng, dependency injection, quản lý bean, transaction, web server và nhiều thành phần chạy nền. CRaC (Coordinated Restore at Checkpoint) bổ sung khả năng lưu trạng thái một tiến trình đang chạy rồi khôi phục tiến trình đó từ checkpoint. Để kết hợp hai công nghệ, ứng dụng cần đáp ứng đồng thời điều kiện của JDK/runtime CRaC, thư viện API org.crac, phiên bản Spring đang dùng và vòng đời của các tài nguyên do Spring quản lý.

Việc thêm dependency org.crac vào dự án chỉ giúp mã nguồn tham chiếu API CRaC. Điều đó không tự biến một JDK thông thường thành runtime có khả năng checkpoint/restore, cũng không bảo đảm mọi bean, connection pool, web server hoặc thread pool của ứng dụng Spring đã được chuẩn bị đúng cách. Tương tự, một bản JDK có hỗ trợ CRaC không tự động làm cho mọi thư viện bên thứ ba tương thích với checkpoint.

Tích hợp đúng cần xác định rõ lớp nào cung cấp API, lớp nào thực hiện checkpoint/restore, component nào sở hữu từng tài nguyên và ai điều phối ứng dụng dừng công việc trước checkpoint rồi phục hồi sau restore. Bài học này trình bày các điều kiện cần kiểm tra, cách tổ chức resource trong Spring, ví dụ tích hợp và quy trình xác minh trên runtime thực tế.

## 1. Các lớp cần có để tích hợp hoạt động

Có thể nhìn việc tích hợp theo bốn lớp:

1. **Runtime và nền tảng:** Bản dựng JDK phải hỗ trợ CRaC; hệ điều hành, kernel, container runtime và công cụ checkpoint/restore phải tương thích.
2. **API CRaC:** Ứng dụng cần API như Resource, Context và Core để đăng ký callback quản lý tài nguyên.
3. **Spring integration:** Phiên bản Spring Framework/Spring Boot và các thư viện liên quan cần có cách phối hợp lifecycle phù hợp, thông qua tích hợp chính thức hoặc resource do ứng dụng tự quản lý.
4. **Ứng dụng và dependency:** Các bean, connection, thread, scheduler, cache, file, client và trạng thái phụ thuộc môi trường phải có kế hoạch trước checkpoint và sau restore.

~~~text
Ứng dụng Spring Boot
  |-- Controller / Service / Repository
  |-- Spring ApplicationContext và Bean lifecycle
  |-- DataSource, HTTP client, cache, scheduler, executor
  |
  +---- Spring integration hoặc Resource do ứng dụng đăng ký
                  |
                  v
             CRaC API (org.crac)
                  |
                  v
          JDK runtime có CRaC
                  |
                  v
      Hệ điều hành và cơ chế checkpoint/restore
~~~

Nếu thiếu một lớp, ứng dụng có thể build thành công nhưng không thể checkpoint, restore hoặc phục vụ request đúng cách. Ví dụ, mã nguồn có thể biên dịch vì dependency org.crac đã có trên classpath, nhưng lệnh checkpoint vẫn thất bại nếu JVM đang chạy là JDK không hỗ trợ CRaC. Một trường hợp khác là tiến trình restore được nhưng connection pool vẫn giữ socket cũ và mọi request truy cập database đều lỗi.

## 2. Điều kiện ở cấp JDK và runtime

Điều kiện đầu tiên là runtime Java thực sự chạy ứng dụng phải là bản dựng có hỗ trợ CRaC. Cần phân biệt JDK dùng để biên dịch với JDK dùng để chạy:

- JDK build có thể chỉ cần tương thích với source level và API mà dự án sử dụng.
- JDK runtime phải có tích hợp CRaC để thực hiện checkpoint và restore.
- Môi trường tạo checkpoint và môi trường restore phải đáp ứng ma trận tương thích của nhà cung cấp.
- Các thư viện native, filesystem, network, kernel và container runtime phải phù hợp với cơ chế checkpoint/restore.

Không thể kết luận hỗ trợ CRaC chỉ từ số phiên bản Java. Hai bản JDK cùng ghi Java 21 vẫn có thể khác nhà cung cấp, build, patch và tính năng được tích hợp. Hãy xác minh đúng binary đang chạy bằng java -version, java.home, java.vendor và tài liệu của bản phân phối.

Ví dụ lệnh kiểm tra:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Trong kết quả, cần ghi lại ít nhất:

| Thông tin | Mục đích |
|---|---|
| java.vendor | Xác định nhà cung cấp runtime |
| java.version | Xác định dòng phiên bản Java |
| java.home | Xác định JDK/JRE thực tế đang được dùng |
| java.vm.name và java.vm.version | Nhận diện JVM và bản build |
| os.name và os.arch | Xác định hệ điều hành và kiến trúc |
| Kernel và container runtime | Đối chiếu yêu cầu checkpoint/restore của nền tảng |

Cần kiểm tra cả môi trường chạy trong IDE, môi trường chạy bằng Gradle/Maven, container image và production. Một máy có nhiều JDK có thể dùng một bản để build nhưng lệnh java trong container lại trỏ đến bản khác.

Ngoài binary, hãy kiểm tra yêu cầu của nhà cung cấp về hệ điều hành, kernel, CRIU hoặc công cụ tương ứng, quyền container, mount, namespace và cách lưu checkpoint. Một checkpoint không phải file JAR độc lập có thể chuyển tùy ý giữa mọi máy. Nó gắn với trạng thái runtime và môi trường tạo ra nó.

## 3. Điều kiện về dependency org.crac

org.crac cung cấp API để ứng dụng đăng ký và triển khai vòng đời resource. Những kiểu thường gặp gồm:

- Resource: giao diện mô tả tài nguyên cần chuẩn bị trước checkpoint và phục hồi sau restore.
- Context: ngữ cảnh được truyền vào callback.
- Core: điểm truy cập đến CRaC context, thường dùng để đăng ký resource vào global context.

Ví dụ dependency Gradle minh họa:

~~~groovy
dependencies {
    implementation("org.crac:crac:<compatible-version>")
}
~~~

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
    <version><crac-version></version>
</dependency>
~~~

Phiên bản minh họa phải được thay bằng phiên bản tương thích với JDK CRaC, Spring integration và dependency thực tế. Không nên chọn version chỉ vì nó mới nhất hoặc sao chép từ một dự án dùng bản JDK khác.

Một số điều cần kiểm tra:

- Dependency có được đưa vào compile classpath để mã có thể import org.crac không?
- API version có tương thích với bản JDK CRaC được triển khai không?
- Runtime có cung cấp hoặc yêu cầu API theo cách đóng gói riêng không?
- Có nhiều phiên bản org.crac cùng xuất hiện do dependency transitive không?
- Dependency có vô tình bị khai báo compileOnly hoặc provided trong khi runtime cần nó không?
- Framework integration có kéo theo phiên bản API khác không?

Không nên thêm nhiều bản API vào classpath để thử ngẫu nhiên. Hãy xem dependency tree và tài liệu của nhà cung cấp. Nếu JDK distribution đã quy định cách sử dụng API riêng, tuân theo hướng dẫn đó để tránh class conflict hoặc hành vi không nhất quán.

## 4. API org.crac và khả năng của JVM là hai việc khác nhau

org.crac là hợp đồng API ở phía ứng dụng. JVM CRaC là runtime thực hiện vòng đời checkpoint/restore. Hai phần liên quan nhưng không thay thế nhau.

Ví dụ, mã sau có thể biên dịch khi dependency API có mặt:

~~~java
import org.crac.Context;
import org.crac.Resource;

public final class ExampleResource implements Resource {
    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Chuẩn bị tài nguyên.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Phục hồi tài nguyên.
    }
}
~~~

Nhưng việc biên dịch thành công không chứng minh JVM có thể checkpoint tiến trình hoặc sẽ gọi callback. Cần chạy ứng dụng bằng runtime được hỗ trợ và thực hiện phép thử checkpoint/restore thật.

Tương tự, một ứng dụng có thể chạy bình thường trên JDK không hỗ trợ CRaC nếu thư viện và cách tích hợp cho phép chế độ chạy đó. Tuy nhiên, thao tác yêu cầu checkpoint sẽ không hoạt động nếu runtime không cung cấp khả năng cần thiết. Cách xử lý khi chạy không có CRaC phụ thuộc API, framework và phiên bản; cần kiểm tra tài liệu thay vì giả định callback luôn là no-op.

## 5. Điều kiện về phiên bản Spring Framework và Spring Boot

Spring Framework quản lý ApplicationContext, bean lifecycle, dependency injection, event, transaction abstraction và nhiều tài nguyên khác. Spring Boot bổ sung auto-configuration, embedded web server, startup runner, actuator và cấu hình triển khai. Khi dùng CRaC, cần xác định phiên bản đang sử dụng có hỗ trợ tích hợp CRaC chính thức hay cần ứng dụng tự đăng ký Resource.

Không nên chỉ nhìn tên Spring Boot 3 hoặc Spring Framework 6 rồi kết luận rằng mọi thành phần đã hỗ trợ CRaC. Hãy kiểm tra tài liệu của đúng phiên bản và đúng artifact:

- Spring Boot version và Spring Framework version thực tế trong dependency tree.
- Có module hoặc integration CRaC chính thức nào được cung cấp cho phiên bản đó không.
- Cách bật integration và các property cần thiết.
- Những loại bean/tài nguyên mà integration tự quản lý.
- Những thư viện ngoài Spring mà integration không bao phủ.
- Quy tắc callback, thứ tự lifecycle và hành vi khi callback lỗi.
- Những giới hạn theo JDK, hệ điều hành và container runtime.

Nếu Spring Boot cung cấp integration CRaC cho phiên bản đang dùng, ưu tiên theo đúng tài liệu của integration đó. Tránh đăng ký thêm một Resource tự quản lý cùng tài nguyên mà integration đã quản lý, vì hai callback có thể cùng đóng hoặc mở một client và tạo race condition.

Nếu phiên bản chưa có integration phù hợp, ứng dụng có thể triển khai Resource riêng cho các tài nguyên mà mình sở hữu. Cần giữ ranh giới rõ ràng giữa tài nguyên do Spring/container quản lý, tài nguyên do thư viện quản lý và tài nguyên do ứng dụng tự tạo.

## 6. Spring bean không tự động trở thành CRaC Resource

Một bean được Spring quản lý có lifecycle riêng như khởi tạo, dependency injection, callback khởi tạo, start/stop và destroy. CRaC Resource có hai callback chuyên biệt:

- beforeCheckpoint(...): chuẩn bị tài nguyên trước khi lưu trạng thái tiến trình.
- afterRestore(...): tạo lại hoặc xác minh tài nguyên sau khi khôi phục.

Việc một bean có @PreDestroy, DisposableBean, SmartLifecycle hoặc phương thức close() không tự chứng minh rằng phương thức đó sẽ được gọi đúng thời điểm checkpoint. Shutdown lifecycle và checkpoint lifecycle là hai sự kiện khác nhau.

Có ba cách tổ chức phổ biến:

1. Dùng integration chính thức của Spring/Boot nếu phiên bản hỗ trợ và tài nguyên nằm trong phạm vi tích hợp.
2. Tạo một Spring bean triển khai org.crac.Resource cho tài nguyên do ứng dụng sở hữu.
3. Tạo một coordinator Resource điều phối nhiều owner, trong khi từng component vẫn chịu trách nhiệm đóng/mở tài nguyên của mình.

Không nên đóng toàn bộ ApplicationContext một cách tùy tiện trong beforeCheckpoint(). Việc đóng context có thể hủy bean, dừng server và khiến tiến trình không thể tiếp tục theo lifecycle mà nền tảng mong đợi. Cần làm theo cách tích hợp được hỗ trợ; nếu cần dừng một thành phần, hãy gọi lifecycle API cụ thể của thành phần đó.

## 7. Đăng ký Resource như một Spring bean

Với ứng dụng tự quản lý resource, một cách tổ chức dễ theo dõi là tạo singleton bean triển khai Resource và đăng ký sau khi bean đã được khởi tạo.

Ví dụ:

~~~java
import jakarta.annotation.PostConstruct;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class CacheClientCracResource implements Resource {
    private final CacheClientLifecycle cacheClient;

    public CacheClientCracResource(CacheClientLifecycle cacheClient) {
        this.cacheClient = cacheClient;
    }

    @PostConstruct
    public void registerWithCrac() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        cacheClient.stopNewOperations();
        cacheClient.awaitOperationsToFinish();
        cacheClient.closeConnections();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        cacheClient.reconnect();
        cacheClient.verifyConnection();
    }
}
~~~

CacheClientLifecycle là abstraction do ứng dụng định nghĩa, không phải API Spring hoặc CRaC. Nó đại diện cho owner thực sự của cache client.

Cách làm này có một số điều kiện:

- Bean phải được tạo đúng một lần trong mỗi tiến trình.
- Resource chỉ được đăng ký một lần, tránh đăng ký trùng khi context khởi tạo lặp.
- Dependency được inject phải sẵn sàng khi callback được gọi.
- Component phải có khả năng dừng thao tác đang chạy trước khi đóng kết nối.
- afterRestore chỉ hoàn tất khi client mới hoạt động và đã được xác minh.
- Nếu callback thất bại, ứng dụng phải báo lỗi và không nhận traffic phụ thuộc vào client đó.

Nếu dùng Spring phiên bản cũ hơn Jakarta namespace, annotation khởi tạo có thể thuộc javax.annotation thay vì jakarta.annotation. Hãy dùng namespace phù hợp với phiên bản Spring và JDK của dự án. Cũng có thể dùng lifecycle callback khác của Spring nếu nó phù hợp hơn với cấu trúc ứng dụng.

Không nên đăng ký Resource trong constructor nếu constructor còn chạy trước khi dependency hoặc trạng thái cần thiết được khởi tạo. Đăng ký sau khi bean sẵn sàng giúp giảm rủi ro callback được gọi trên một object chưa hoàn tất cấu hình.

## 8. Tổ chức coordinator cho nhiều bean

Một ứng dụng Spring Boot thường có nhiều nhóm tài nguyên: HTTP server, DataSource, Redis, HTTP client, Kafka consumer, scheduler và executor. Nếu mỗi bean tự dừng theo một thứ tự không rõ ràng, một component có thể đóng dependency trong khi component khác vẫn đang dùng nó.

Có thể tổ chức một coordinator để thực hiện trình tự tổng thể:

1. Ngừng nhận công việc mới.
2. Chờ request, message handler và scheduled job đang chạy hoàn tất.
3. Dừng producer/consumer hoặc worker theo chính sách.
4. Yêu cầu owner từng tài nguyên flush, đóng hoặc chuẩn bị.
5. Xác nhận các thành phần đã ở trạng thái an toàn.
6. Cho phép checkpoint.

Sau restore, thứ tự thường đi theo chiều dependency:

1. Nạp lại identity và cấu hình theo instance.
2. Tạo kết nối, client và pool.
3. Xác minh database, cache, broker và dịch vụ ngoài.
4. Khởi động worker/scheduler.
5. Mở lại ingress và báo readiness.

Ví dụ coordinator:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class ApplicationCheckpointCoordinator implements Resource {
    private final IngressLifecycle ingress;
    private final BackgroundWorkLifecycle backgroundWork;
    private final DataAccessLifecycle dataAccess;
    private final ExternalClientLifecycle externalClients;

    public ApplicationCheckpointCoordinator(
            IngressLifecycle ingress,
            BackgroundWorkLifecycle backgroundWork,
            DataAccessLifecycle dataAccess,
            ExternalClientLifecycle externalClients) {
        this.ingress = ingress;
        this.backgroundWork = backgroundWork;
        this.dataAccess = dataAccess;
        this.externalClients = externalClients;
    }

    @PostConstruct
    public void register() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        ingress.stopAcceptingNewWork();
        backgroundWork.stopSchedulingNewWork();
        ingress.awaitRequestsToFinish();
        backgroundWork.awaitInFlightWorkToFinish();
        dataAccess.prepareForCheckpoint();
        externalClients.prepareForCheckpoint();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        externalClients.restoreAndValidate();
        dataAccess.restoreAndValidate();
        backgroundWork.restoreInPausedState();
        ingress.verifyReady();
        backgroundWork.allowNewWork();
        ingress.allowNewWork();
    }

    public interface IngressLifecycle {
        void stopAcceptingNewWork() throws Exception;
        void awaitRequestsToFinish() throws Exception;
        void verifyReady() throws Exception;
        void allowNewWork() throws Exception;
    }

    public interface BackgroundWorkLifecycle {
        void stopSchedulingNewWork() throws Exception;
        void awaitInFlightWorkToFinish() throws Exception;
        void restoreInPausedState() throws Exception;
        void allowNewWork() throws Exception;
    }

    public interface DataAccessLifecycle {
        void prepareForCheckpoint() throws Exception;
        void restoreAndValidate() throws Exception;
    }

    public interface ExternalClientLifecycle {
        void prepareForCheckpoint() throws Exception;
        void restoreAndValidate() throws Exception;
    }
}
~~~

Đây là mẫu kiến trúc. Các interface lifecycle là hợp đồng do ứng dụng tự định nghĩa. Không phải mọi ứng dụng cần một coordinator trung tâm; có thể dùng integration của framework hoặc nhiều Resource độc lập. Nếu dùng coordinator, phải bảo đảm không có Resource khác mở lại ingress trước khi coordinator xác nhận toàn bộ dependency đã sẵn sàng.

Không nên dựa vào thứ tự đăng ký Resource nếu API hoặc bản JDK không cam kết thứ tự callback. Khi thứ tự quan trọng, hãy điều phối tường minh bằng một component có trách nhiệm tổng thể và kiểm thử thứ tự đó trên runtime thực tế.

## 9. Tích hợp với DataSource và connection pool

Spring Boot thường tạo DataSource thông qua auto-configuration hoặc cấu hình riêng. JPA provider, JdbcTemplate và repository có thể dùng chung DataSource đó. Connection pool thường giữ socket đến database và có thread quản lý riêng.

Trước checkpoint, cần:

- Ngừng nhận request và job mới có thể truy cập database.
- Chờ transaction đang chạy hoàn tất hoặc rollback theo chính sách.
- Không để EntityManager/Session, JDBC Connection, Statement hoặc ResultSet đang hoạt động dở dang.
- Dùng CRaC integration của connection pool nếu có.
- Nếu cần đóng pool, thực hiện tại owner quản lý DataSource.
- Không để nhiều bean cùng đóng một pool.

Sau restore, cần:

- Tạo lại hoặc xác minh pool theo integration của thư viện.
- Kiểm tra kết nối đến database.
- Làm mới secret, DNS hoặc endpoint nếu chúng có thể thay đổi.
- Chỉ mở request cần database sau khi pool hoạt động.

Không phải mọi DataSource đều cần đóng và tạo lại theo cùng một cách. Một số pool hoặc driver có tích hợp CRaC; một số cần adapter; một số có thể giữ cấu trúc pool nhưng phải loại bỏ connection vật lý cũ. Hãy kiểm tra tài liệu của đúng phiên bản pool và driver.

## 10. Tích hợp với web server và request lifecycle

Spring Boot có thể chạy embedded web server. Server sở hữu listening socket, event loop, worker thread và các buffer nội bộ. Ứng dụng cần xác định integration CRaC của web server và Spring Boot version đang dùng.

Trước checkpoint, hệ thống cần ngừng nhận request mới và drain request đang chạy. Điều này giúp:

- Hoàn tất transaction và response.
- Chạy finally block và cleanup của request context.
- Đóng stream hoặc file đang mở theo request.
- Tránh checkpoint khi thread đang giữ lock hoặc xử lý dở.
- Đưa readiness về trạng thái không nhận traffic nếu cơ chế triển khai yêu cầu.

Sau restore, server phải ở trạng thái có thể nhận kết nối. Nếu listening socket cần được tạo lại, việc này phải do integration hoặc owner của server thực hiện. Không tự đóng socket nội bộ bằng reflection hoặc truy cập field private của server.

Nếu dùng reverse proxy hoặc load balancer, hãy phối hợp drain traffic ở tầng điều phối. Một instance không nên báo ready trước khi web server và dependency thiết yếu sẵn sàng.

## 11. Tích hợp với scheduler và executor

Các bean như TaskScheduler, ScheduledExecutorService, ThreadPoolTaskExecutor hoặc executor tự tạo có thể tiếp tục giữ thread và task queue. Một task có thể đang chạy, đang chờ hoặc đã được schedule trong tương lai.

Trước checkpoint:

- Ngừng schedule task mới.
- Chờ task đang chạy hoàn tất hoặc dừng tại batch boundary.
- Lưu progress bền vững nếu task xử lý dữ liệu.
- Xử lý lease và distributed lock nếu task có quyền sở hữu độc quyền.
- Không để task giữ transaction, lock hoặc resource dở dang.

Sau restore:

- Tạo lại executor nếu lifecycle của thư viện yêu cầu.
- Tính lại lịch dựa trên thời gian hiện tại.
- Tránh chạy bù tác vụ đã hết hạn nhiều lần ngoài ý muốn.
- Acquire lease mới trước khi chạy công việc độc quyền.
- Mở scheduler sau khi dependency và readiness đã hoàn tất.

Không phải cứ thấy một executor trong Spring context là phải shutdown nó trong callback. Nếu executor do container hoặc integration quản lý, hãy theo đúng lifecycle được hỗ trợ. Đóng executor sai thời điểm có thể khiến ứng dụng không thể tiếp tục sau checkpoint.

## 12. Tích hợp với HTTP client, Redis, messaging và thư viện ngoài

Các thư viện client thường giữ socket, connection pool, thread nền, timer, DNS cache, TLS session và buffer. Một Spring bean chỉ inject client không có nghĩa nó là owner của toàn bộ tài nguyên nội bộ.

Với từng dependency, cần kiểm tra:

- Phiên bản đang dùng có hỗ trợ CRaC chính thức không.
- Cách thư viện yêu cầu pause, close, reconnect hoặc reinitialize.
- Callback nào được đăng ký tự động.
- Có cần tạo lại client sau restore không.
- Những trạng thái nào cần làm mới: token, DNS, TLS, endpoint, consumer ID hoặc subscription.
- Có resource nào được cả framework và ứng dụng cùng quản lý không.

Ví dụ:

| Thành phần | Trước checkpoint | Sau restore |
|---|---|---|
| HTTP client | Hoàn tất/hủy request đang chạy, đóng connection nếu integration yêu cầu | Tạo hoặc kiểm tra connection mới |
| Redis client | Dừng thao tác mới, chờ lệnh đang chạy, xử lý connection | Kết nối lại, xác minh cluster và auth |
| Kafka/message consumer | Pause, xử lý message dở dang, commit theo chính sách, đóng client nếu cần | Tạo consumer mới, tham gia group và xác minh assignment |
| Scheduler | Dừng trigger mới và drain job | Tính lại lịch, lấy lease mới nếu cần |
| Secret provider | Không giữ giả định token còn hiệu lực | Làm mới secret/token khi cần |
| Cache | Xác định dữ liệu có thể giữ và dữ liệu cần invalidate | Reconnect hoặc làm mới dữ liệu hết hạn |

Không viết một Resource tổng quát gọi close() trên mọi bean có phương thức close. Một số bean là proxy, một số có shared lifecycle, một số đã được thư viện tự đăng ký. Quản lý theo owner và hợp đồng của từng thư viện.

## 13. Cấu hình Spring Boot và dữ liệu phụ thuộc môi trường

Một ứng dụng có thể đọc cấu hình khi ApplicationContext khởi tạo và giữ kết quả trong bean hoặc static field. Sau khi checkpoint được tạo, môi trường restore có thể khác về hostname, IP, port, secret, credential hoặc endpoint.

Các giá trị cần phân loại:

- **Cấu hình nền:** Quy tắc nghiệp vụ, mapping, metadata bất biến và cấu hình có thể chia sẻ an toàn.
- **Cấu hình theo instance:** Instance ID, hostname, IP, port, pod name và node identity.
- **Thông tin có thời hạn:** Token, certificate, secret, signed URL, lease và credential ngắn hạn.
- **Thông tin có thể thay đổi:** DNS, endpoint dịch vụ, feature flag và cấu hình tập trung.

Không nên đưa identity riêng của tiến trình tạo checkpoint vào ảnh dùng chung cho nhiều replica. Sau restore, lấy thông tin instance từ môi trường hiện tại hoặc hệ thống điều phối. Nếu giá trị đã được cache trong bean, cần có cách cập nhật hoặc tạo lại bean/client phụ thuộc giá trị đó.

Các hook như ApplicationRunner hoặc CommandLineRunner thường chạy trong quá trình khởi động ứng dụng. Chúng có thể phù hợp để chuẩn bị hoặc warm-up trước khi checkpoint, nhưng không nên giả định chúng tự chạy lại sau mỗi restore. Hành vi restore tiếp tục từ trạng thái tiến trình đã lưu, và callback CRaC là điểm phối hợp riêng. Hãy đặt công việc cần thực hiện sau restore vào lifecycle phù hợp thay vì dựa vào việc khởi động Spring Boot từ đầu.

## 14. Warm-up và thời điểm tạo checkpoint

Một mục tiêu phổ biến là tạo checkpoint sau khi Spring ApplicationContext đã khởi tạo và ứng dụng đã warm-up. Điều này có thể giữ lại metadata, cấu trúc cache và trạng thái JVM đã được chuẩn bị.

Quy trình chuẩn bị thường gồm:

1. Khởi chạy bằng JDK CRaC tương thích.
2. Để Spring tạo ApplicationContext và hoàn tất khởi tạo bean.
3. Chờ các dependency nền sẵn sàng.
4. Chạy workload warm-up đại diện, tránh side effect nghiệp vụ.
5. Xác nhận cache hoặc metadata nền đã được nạp.
6. Ngừng ingress và background work.
7. Chuẩn bị tài nguyên theo Resource lifecycle.
8. Tạo checkpoint.

Không nên checkpoint khi warm-up còn thực hiện giao dịch thật, gửi email, tạo đơn hàng hoặc phát message nghiệp vụ. Dùng dữ liệu thử và thao tác an toàn, có thể lặp lại.

Nếu một bean khởi tạo lười, warm-up cần kích hoạt đúng đường đi nghiệp vụ quan trọng. Một lần gọi health endpoint không bảo đảm toàn bộ application path đã được làm nóng.

## 15. Quản lý transaction và persistence context

Spring transaction management có thể gắn transaction với thread hiện tại và quản lý EntityManager/JDBC connection theo phạm vi transaction. Khi checkpoint, không nên để transaction active hoặc persistence context dở dang.

Cần bảo đảm:

- Ingress và scheduler đã ngừng tạo công việc mới.
- Request đang chạy được drain.
- Transaction đã commit hoặc rollback.
- EntityManager/Session application-managed đã được đóng.
- Cursor, ResultSet và stream query đã được kết thúc.
- Connection pool được xử lý theo integration của driver/pool.
- Sau restore, request mới tạo transaction và persistence context mới.

Không gọi flush() rồi cho rằng transaction đã commit. Flush chỉ đồng bộ thay đổi của persistence context xuống database; transaction vẫn có thể rollback. Hãy để transaction manager hoàn tất transaction theo ranh giới nghiệp vụ.

## 16. Xử lý lỗi callback và readiness

Callback CRaC có thể thất bại. Ví dụ, database không thể kết nối lại, secret provider timeout, Redis cluster chưa sẵn sàng hoặc file không còn tồn tại.

Một ứng dụng tốt cần định nghĩa hành vi khi callback lỗi:

- Không nuốt exception rồi báo restore thành công.
- Ghi log có resource ID, operation và nguyên nhân; tránh ghi secret.
- Dùng timeout có giới hạn và retry theo chính sách.
- Phân biệt lỗi có thể retry với lỗi cấu hình hoặc không tương thích.
- Không mở ingress nếu dependency thiết yếu chưa sẵn sàng.
- Cho phép orchestrator giữ instance ở trạng thái chưa ready hoặc thay thế instance lỗi.
- Tránh tạo side effect nghiệp vụ trong callback phục hồi.

Readiness cần phản ánh trạng thái phục vụ thực tế. Tiến trình có thể tồn tại nhưng chưa có database connection, consumer chưa tham gia group hoặc HTTP server chưa bind xong. Liveness và readiness có mục đích khác nhau; không nên đánh đồng hai tín hiệu.

## 17. Điều kiện khi dùng Spring Boot integration chính thức

Nếu phiên bản Spring Boot cung cấp module hoặc integration CRaC chính thức, cần xác minh các nội dung sau trong tài liệu của đúng phiên bản:

1. Artifact nào phải thêm vào build.
2. Có cần thêm riêng org.crac API hay integration đã khai báo dependency transitive.
3. Cách cấu hình SpringApplication hoặc ApplicationContext tham gia checkpoint/restore.
4. Những bean hoặc loại resource nào được tích hợp tự động.
5. Những resource nào ứng dụng vẫn phải tự đăng ký.
6. Cách integration phối hợp web server, lifecycle, shutdown và restore.
7. Cách xử lý callback lỗi và readiness.
8. Giới hạn về JDK distribution, OS và container.

Không đoán tên artifact hoặc property dựa trên phiên bản khác. Kiểm tra dependency metadata và reference documentation của đúng Spring Boot release đang dùng.

Nếu integration tự động quản lý một thành phần, không tạo thêm Resource để đóng/mở cùng tài nguyên. Nếu integration chỉ quản lý một phần, viết adapter cho phần còn lại và ghi rõ ranh giới ownership.

## 18. Điều kiện khi tự tích hợp bằng org.crac

Nếu dự án không có integration Spring/Boot phù hợp, có thể triển khai Resource riêng. Trước khi làm, cần có inventory:

| Nhóm | Câu hỏi cần trả lời |
|---|---|
| Web server | Ai dừng nhận request và drain request? |
| Transaction | Ai xác nhận không còn transaction active? |
| DataSource | Ai quản lý pool và connection vật lý? |
| HTTP/Redis/Messaging | Thư viện có CRaC support không, ai tạo lại client? |
| Executor | Ai dừng task và khởi động lại worker? |
| Scheduler | Làm sao tránh chạy trùng và lấy lại lease? |
| File/native | Handle nào cần đóng, flush hoặc mở lại? |
| Configuration | Giá trị nào phải đọc lại sau restore? |
| Cache | Cache nào có thể giữ, cache nào cần invalidate? |

Sau đó:

- Tạo một Resource cho mỗi owner hoặc một coordinator có trách nhiệm điều phối.
- Đăng ký Resource đúng một lần trong mỗi tiến trình.
- Dùng callback để thực hiện lifecycle tường minh.
- Không dùng reflection vào nội bộ Spring hoặc thư viện để đóng tài nguyên.
- Kiểm thử checkpoint/restore với đúng JDK và dependency.
- Kiểm tra readiness sau restore trước khi nhận traffic.

## 19. Kiểm tra dependency tree và classpath

Ứng dụng Spring Boot thường có nhiều dependency transitive. Một thư viện có thể kéo theo phiên bản org.crac API hoặc Spring integration không giống với phiên bản nhóm nghĩ đang dùng.

Với Gradle, có thể xem dependency tree bằng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency crac --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
~~~

Hãy kiểm tra:

- Spring Boot plugin/BOM và Spring Framework version có đồng bộ không.
- Có nhiều phiên bản org.crac hoặc CRaC integration không.
- Driver, pool, cache provider và messaging client có phiên bản tương thích không.
- Dependency cần ở runtime có bị loại khỏi runtime classpath không.
- Container image có dùng đúng JDK runtime mà build/deploy đã chọn không.

Dependency tree chỉ cho biết thư viện nào có trong classpath. Nó không chứng minh runtime có hỗ trợ checkpoint hoặc thư viện đã xử lý tài nguyên đúng cách. Vẫn cần thử trên runtime CRaC thực tế.

## 20. Quy trình xác minh từ build đến restore

Một quy trình kiểm chứng có thể chia thành các lớp:

### Bước 1: Xác minh runtime

Ghi nhận vendor, version, build, java.home, OS, architecture, kernel và công cụ checkpoint/restore. Đối chiếu với tài liệu nhà cung cấp.

### Bước 2: Xác minh API

Kiểm tra org.crac có mặt ở compile và runtime classpath theo cách đóng gói được hỗ trợ. Xác nhận code có thể import Resource, Context và Core.

### Bước 3: Xác minh Spring integration

Xác định Spring Boot/Spring Framework version thực tế. Kiểm tra có integration CRaC chính thức hay không, artifact và property nào cần dùng, resource nào được quản lý tự động.

### Bước 4: Kiểm tra resource registration

Chạy ứng dụng và xác nhận Resource được đăng ký đúng một lần. Dùng log an toàn để xác nhận callback được gọi. Không chỉ dựa vào việc bean tồn tại trong ApplicationContext.

### Bước 5: Kiểm tra trước checkpoint

Gửi request và task đại diện, sau đó yêu cầu quiesce. Xác nhận request đã drain, transaction kết thúc, worker dừng, buffer được xử lý và resource owner báo sẵn sàng.

### Bước 6: Tạo checkpoint và restore

Thực hiện bằng cơ chế được JDK/platform chỉ định. Quan sát log, callback và trạng thái tài nguyên sau restore.

### Bước 7: Kiểm tra ứng dụng

Gửi request mới, thực hiện query database, gọi service ngoài, kiểm tra cache, message consumer và scheduler. Chỉ đánh dấu readiness khi các chức năng thiết yếu hoạt động.

### Bước 8: Kiểm tra lỗi

Thử database chưa sẵn sàng, token hết hạn, callback timeout, endpoint thay đổi và restore trên môi trường không tương thích. Xác nhận ứng dụng không báo ready sai và không tạo side effect trùng.

## 21. Ví dụ cấu trúc dự án

Một cấu trúc có thể tách integration CRaC khỏi nghiệp vụ:

~~~text
src/main/java/com/example/app/
  Application.java
  config/
    CracConfiguration.java
    DataSourceConfiguration.java
  crac/
    ApplicationCheckpointCoordinator.java
    DatabaseCracResource.java
    ExternalClientCracResource.java
  lifecycle/
    IngressLifecycle.java
    WorkerLifecycle.java
    DataAccessLifecycle.java
  service/
    OrderService.java
  repository/
    OrderRepository.java
~~~

Trong đó:

- Application.java khởi chạy Spring Boot.
- CracConfiguration.java tạo và cấu hình các bean lifecycle.
- ApplicationCheckpointCoordinator điều phối quiesce và restore.
- DatabaseCracResource quản lý phần database mà ứng dụng thực sự sở hữu.
- ExternalClientCracResource quản lý client ngoài nếu thư viện chưa có integration.
- Các interface lifecycle giúp tách phần điều phối khỏi chi tiết của driver hoặc framework.

Không bắt buộc phải tạo đúng các lớp này. Với ứng dụng nhỏ, một Resource có thể đủ. Với ứng dụng lớn, tách theo owner giúp tránh một callback khổng lồ biết quá nhiều chi tiết nội bộ.

## 22. Những lỗi tích hợp thường gặp

**Chỉ thêm org.crac dependency rồi chạy trên JDK thông thường.** Mã có thể biên dịch nhưng runtime không có khả năng checkpoint/restore. Hãy xác minh binary thực tế.

**Nhầm Spring bean lifecycle với CRaC lifecycle.** @PreDestroy hoặc close() không tự động là callback trước checkpoint. Dùng integration hoặc Resource được đăng ký rõ ràng.

**Cho rằng Spring Boot tự quản lý mọi dependency.** Framework không thể tự biết mọi socket, native handle và trạng thái tùy chỉnh trong thư viện ngoài. Kiểm tra phạm vi integration và inventory.

**Đăng ký Resource trùng.** Spring integration và ứng dụng cùng đóng một client. Chỉ định một owner lifecycle và tránh callback chồng lặp.

**Đóng ApplicationContext trong beforeCheckpoint.** Có thể phá hủy bean và khiến tiến trình không thể tiếp tục. Chỉ thực hiện theo lifecycle được hỗ trợ.

**Checkpoint khi request hoặc transaction còn chạy.** Trạng thái nghiệp vụ có thể dở dang và connection không còn hợp lệ. Drain request và hoàn tất transaction.

**Dùng callback restore để chạy nghiệp vụ thật.** Restore có thể xảy ra nhiều lần; side effect như tạo đơn hoặc gửi email có thể lặp. Callback nên tập trung phục hồi tài nguyên và trạng thái runtime.

**Mở readiness quá sớm.** Process tồn tại không có nghĩa database, broker hoặc web server đã sẵn sàng. Readiness phải chờ dependency thiết yếu.

**Không refresh cấu hình theo instance.** Checkpoint có thể giữ hostname, token hoặc endpoint cũ. Đọc lại dữ liệu phụ thuộc môi trường sau restore.

**Dựa vào thứ tự callback không được bảo đảm.** Nếu database phải sẵn sàng trước worker, điều phối thứ tự tường minh và kiểm thử thay vì giả định thứ tự đăng ký.

**Không kiểm tra runtimeClasspath.** API hoặc integration có thể chỉ xuất hiện lúc compile, hoặc có nhiều phiên bản xung đột. Kiểm tra dependency tree và container image.

## 23. Checklist tích hợp Spring, Spring Boot và org.crac

- [ ] Đã xác định đúng JDK binary chạy ứng dụng và xác nhận bản dựng hỗ trợ CRaC chưa?
- [ ] JDK, kernel, OS, container runtime và công cụ checkpoint/restore có tương thích không?
- [ ] org.crac API có đúng phiên bản và có mặt ở runtime classpath không?
- [ ] Đã kiểm tra dependency tree để tránh nhiều phiên bản API/integration chưa?
- [ ] Đã xác định chính xác Spring Boot và Spring Framework version chưa?
- [ ] Tài liệu của đúng release có xác nhận integration CRaC và cách cấu hình chưa?
- [ ] Đã biết integration tự động quản lý resource nào và bỏ qua resource nào chưa?
- [ ] Mỗi tài nguyên có owner và cách phối hợp trước checkpoint/sau restore chưa?
- [ ] Resource bean được đăng ký đúng một lần chưa?
- [ ] Không có callback trùng quản lý cùng một pool hoặc client chưa?
- [ ] Ingress, transaction, scheduler và executor được drain trước checkpoint chưa?
- [ ] Database, HTTP client, cache và messaging được phục hồi theo đúng thư viện chưa?
- [ ] Identity, token, DNS và cấu hình phụ thuộc instance được làm mới khi cần chưa?
- [ ] Callback lỗi có ngăn ứng dụng báo ready hoặc nhận traffic không?
- [ ] Đã thử checkpoint và restore bằng đúng runtime và image triển khai chưa?
- [ ] Đã kiểm thử request, transaction, background task và side effect sau restore chưa?

## Kết luận

Để tích hợp Spring Framework, Spring Boot và org.crac, cần đồng thời đáp ứng điều kiện của runtime CRaC, API, phiên bản Spring và các dependency mà ứng dụng sử dụng. Dependency org.crac chỉ cung cấp hợp đồng API; JDK có hỗ trợ CRaC mới cung cấp khả năng checkpoint/restore ở cấp runtime. Spring integration có thể hỗ trợ phối hợp lifecycle, nhưng phạm vi tài nguyên được quản lý phụ thuộc phiên bản và cấu hình.

Hãy xác định owner của từng tài nguyên, dùng integration chính thức khi có, và đăng ký Resource riêng cho phần ứng dụng thực sự sở hữu. Trước checkpoint, ngừng ingress, drain request và transaction, rồi đưa client, pool, worker và scheduler về trạng thái an toàn. Sau restore, làm mới cấu hình phụ thuộc instance, phục hồi dependency, xác minh chức năng và chỉ mở readiness khi ứng dụng có thể phục vụ. Cuối cùng, kiểm thử bằng đúng JDK, Spring release, container image và nền tảng triển khai sẽ giúp phân biệt lỗi dependency, lỗi runtime và lỗi lifecycle của ứng dụng.
