# Checkpoint tự động tại onRefresh bằng spring.context.checkpoint

Spring Boot có thể phối hợp với CRaC để tạo checkpoint ở một mốc trong quá trình khởi động ứng dụng. Với cấu hình spring.context.checkpoint=onRefresh, Spring Boot yêu cầu CRaC thực hiện checkpoint khi ApplicationContext đã hoàn tất giai đoạn refresh. Nhờ vậy, ảnh checkpoint có thể chứa trạng thái đã được tạo trong quá trình khởi tạo bean, nạp cấu hình và chạy các callback khởi tạo của Spring.

Checkpoint tại onRefresh hữu ích khi phần khởi tạo tốn thời gian chủ yếu diễn ra trong quá trình tạo ApplicationContext. Ứng dụng có thể khôi phục từ ảnh để giảm thời gian khởi động cho những lần chạy tiếp theo. Tuy nhiên, mốc onRefresh không đồng nghĩa ứng dụng đã hoàn tất toàn bộ startup. Các bước như ApplicationRunner, CommandLineRunner hoặc công việc warm-up được thực hiện sau refresh có thể chưa chạy tại thời điểm ảnh được tạo.

Để dùng cơ chế này, ứng dụng cần phiên bản Spring Boot có hỗ trợ CRaC, dependency org.crac tương thích và JDK/runtime CRaC được cấu hình đúng. Property chỉ xác định thời điểm Spring Boot yêu cầu checkpoint; nó không tự làm cho mọi kết nối, thread, session hoặc tài nguyên bên ngoài trở nên an toàn. Các resource cần được chuẩn bị trước checkpoint và khôi phục sau restore theo lifecycle phù hợp.

## 1. CRaC và checkpoint trong vòng đời Spring Boot

CRaC (Coordinated Restore at Checkpoint) cho phép lưu trạng thái của một tiến trình đang chạy rồi khôi phục tiến trình từ trạng thái đó. Với Java, checkpoint có thể giữ lại trạng thái JVM như lớp đã nạp, đối tượng trong heap và một phần trạng thái tiến trình/tài nguyên được runtime hỗ trợ.

Spring Boot tạo ApplicationContext để quản lý bean, cấu hình, dependency injection, event listener và lifecycle của ứng dụng. Quá trình khởi động thường gồm các bước lớn:

1. Tạo SpringApplication và chuẩn bị Environment.
2. Tạo ApplicationContext.
3. Nạp bean definitions và xử lý cấu hình.
4. Khởi tạo singleton bean và các dependency cần thiết.
5. Hoàn tất refresh của ApplicationContext.
6. Chạy các bước tiếp theo của SpringApplication, bao gồm ApplicationRunner và CommandLineRunner.
7. Phát sự kiện ứng dụng đã sẵn sàng và bắt đầu phục vụ theo cấu hình.

Property spring.context.checkpoint điều khiển mốc checkpoint gắn với vòng đời context. Khi đặt giá trị onRefresh, Spring Boot yêu cầu checkpoint sau khi ApplicationContext refresh hoàn tất.

~~~mermaid
flowchart TD
    A[SpringApplication bắt đầu] --> B[Tạo Environment và ApplicationContext]
    B --> C[Đọc cấu hình và tạo bean]
    C --> D[Khởi tạo singleton và dependency]
    D --> E[ApplicationContext refresh hoàn tất]
    E --> F{spring.context.checkpoint}
    F -->|onRefresh| G[CRaC checkpoint]
    F -->|never| H[Tiếp tục startup]
    G --> I[CRaC restore và callback phục hồi]
    I --> J[Tiếp tục startup]
    H --> J
    J --> K[ApplicationRunner và CommandLineRunner]
    K --> L[Ứng dụng sẵn sàng]
~~~

Sơ đồ thể hiện vị trí khái quát của checkpoint trong startup pipeline. Chi tiết event và callback có thể khác theo phiên bản Spring Boot, Spring Framework và CRaC runtime; hãy đối chiếu phiên bản thực tế khi phụ thuộc vào một thứ tự cụ thể.

## 2. Property spring.context.checkpoint=onRefresh

Giá trị onRefresh yêu cầu Spring Boot thực hiện checkpoint tại thời điểm ApplicationContext đã refresh. Giá trị mặc định thường là never, nghĩa là Spring Boot không tự kích hoạt checkpoint ở mốc refresh.

Trong file application.properties:

~~~properties
spring.context.checkpoint=onRefresh
~~~

Hoặc trong application.yml:

~~~yaml
spring:
  context:
    checkpoint: onRefresh
~~~

Khi cấu hình được nạp, Spring Boot sử dụng chế độ checkpoint đã chọn trong quá trình startup.

### 2.1. Ý nghĩa của onRefresh

onRefresh gắn việc yêu cầu checkpoint với sự kiện ApplicationContext đã hoàn tất refresh. Tại thời điểm này, nhiều công việc khởi tạo Spring đã diễn ra:

- Bean definitions đã được đăng ký và xử lý.
- Các singleton bean cần khởi tạo eagerly đã được tạo.
- Dependency injection và các callback khởi tạo bean đã được thực hiện.
- Các thành phần Spring lifecycle được khởi động theo cơ chế refresh tương ứng.
- Các listener của ApplicationContext đã được đăng ký và context đã hoàn tất refresh.

Vì vậy, nếu chi phí khởi động nằm trong constructor, factory method, BeanPostProcessor, InitializingBean, @PostConstruct hoặc quá trình tạo singleton, trạng thái hoàn tất của những bước này có thể nằm trong checkpoint.

Tuy nhiên, onRefresh không phải tín hiệu rằng mọi tác vụ ứng dụng đã hoàn tất. Công việc được thực hiện sau giai đoạn refresh, ví dụ trong ApplicationRunner hoặc CommandLineRunner, có thể chưa chạy khi checkpoint được tạo. Những tác vụ được khởi chạy bất đồng bộ trong lúc khởi tạo cũng có thể chưa hoàn tất.

### 2.2. Giá trị mặc định và khi nào nên bật

Nếu không cấu hình property, ứng dụng không nên giả định Spring Boot sẽ tự tạo checkpoint. Hãy bật onRefresh khi:

- Ứng dụng chạy trên runtime hỗ trợ CRaC.
- Có quy trình tạo và lưu checkpoint trong môi trường triển khai.
- Phần khởi tạo cần tái sử dụng chủ yếu hoàn tất trước hoặc trong refresh.
- Các resource bên ngoài có callback chuẩn bị và phục hồi rõ ràng.
- Ứng dụng đã được kiểm thử với đúng JDK, container, filesystem và thư viện đang dùng.

Không nên bật property trong một môi trường không hỗ trợ CRaC rồi kỳ vọng dependency Maven tự bổ sung khả năng checkpoint. Artifact org.crac cung cấp API; khả năng checkpoint/restore còn phụ thuộc JDK/runtime, hệ điều hành và môi trường triển khai.

### 2.3. Không nhầm với checkpoint định kỳ

onRefresh không phải một lịch checkpoint định kỳ và cũng không có nghĩa mỗi lần bean thay đổi thì ứng dụng tạo ảnh mới. Đây là một điểm kích hoạt gắn với quá trình refresh ApplicationContext. Nếu ứng dụng có nhiều context hoặc refresh context nhiều lần, cần kiểm tra hành vi của phiên bản và cấu trúc ứng dụng thay vì giả định chỉ có một lần gọi trong mọi trường hợp.

Nếu cần checkpoint sau một bước warm-up riêng hoặc tại một thời điểm vận hành khác, hãy thiết kế trigger có chủ đích theo API và phiên bản đang dùng. Không giả định onRefresh sẽ chờ mọi tác vụ nền hoặc mọi runner hoàn tất.

## 3. Chuẩn bị dependency và runtime

Spring Boot cần có API CRaC trên classpath và phải chạy bằng JDK/runtime hỗ trợ checkpoint/restore.

### 3.1. Dependency Maven

Nếu dự án dùng Spring Boot dependency management và phiên bản BOM quản lý dependency CRaC tương ứng, có thể khai báo:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
</dependency>
~~~

Nếu BOM không quản lý phiên bản hoặc dự án dùng cách quản lý dependency riêng, hãy khai báo phiên bản org.crac tương thích với phiên bản Spring Boot và runtime CRaC đang sử dụng. Không chọn một phiên bản ngẫu nhiên chỉ để làm cho compile thành công.

### 3.2. Dependency Gradle

Với Gradle:

~~~kotlin
dependencies {
    implementation("org.crac:crac")
}
~~~

Tương tự Maven, nếu dependency management không cung cấp version, hãy chỉ định phiên bản đã được xác nhận tương thích.

### 3.3. Phiên bản Spring Boot

Spring Boot cung cấp tích hợp CRaC trong các phiên bản có hỗ trợ tính năng này, bắt đầu từ dòng Spring Boot 3.2. Khi triển khai, cần xác nhận:

- Phiên bản Spring Boot thực tế.
- Phiên bản Spring Framework đi kèm.
- Phiên bản org.crac API.
- Bản phân phối JDK có CRaC support.
- Hệ điều hành, kernel và container runtime tương thích.
- Các thư viện native, agent, profiler hoặc client bên thứ ba có hỗ trợ checkpoint/restore.

Không nên chỉ kiểm tra file build để kết luận runtime đã hỗ trợ CRaC. Hãy chạy thử checkpoint/restore trên chính image và môi trường đích.

### 3.4. Runtime và nơi lưu checkpoint

JDK thông thường có thể không cung cấp khả năng checkpoint/restore CRaC. Cần sử dụng bản JDK/runtime được xây dựng với CRaC support và cấu hình checkpoint destination theo hướng dẫn của bản phân phối.

Một số runtime CRaC dùng tùy chọn JVM tương tự:

~~~text
-XX:CRaCCheckpointTo=/opt/checkpoints/orders
~~~

Đường dẫn trên chỉ là ví dụ. Tùy JDK và môi trường, cần cấu hình quyền ghi, dung lượng, mount volume, ownership và chính sách bảo vệ ảnh. Không đặt checkpoint vào một thư mục tạm sẽ bị xóa trước khi quy trình restore sử dụng ảnh.

Tạo checkpoint có thể cần quyền hệ điều hành, cấu hình kernel hoặc khả năng của container runtime. Hãy tuân thủ tài liệu của JDK CRaC và nền tảng đang triển khai; property Spring Boot không thể thay thế các yêu cầu này.

## 4. Điều gì được khởi tạo trước mốc onRefresh?

Điểm checkpoint nằm sau giai đoạn refresh nên những trạng thái đã được tạo trong quá trình refresh có thể được lưu vào ảnh. Ví dụ:

- Bean singleton và dependency đã được khởi tạo.
- Cấu hình đã bind vào đối tượng.
- Metadata hoặc schema đã được nạp.
- Các cache được khởi tạo đồng bộ trong quá trình tạo bean.
- Các parser, serializer hoặc cấu trúc dữ liệu dùng chung đã được tạo.
- Các callback khởi tạo bean đã chạy.

Điều này có thể giảm đáng kể công việc lặp lại khi ứng dụng được restore.

### 4.1. Constructor và @PostConstruct

Ví dụ một bean chuẩn bị dữ liệu bất biến khi khởi tạo:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public final class ReferenceData {
    private Map<String, String> values;

    @PostConstruct
    void load() {
        values = Map.of(
                "VN", "Vietnam",
                "SG", "Singapore",
                "JP", "Japan"
        );
    }

    public String find(String code) {
        return values.get(code);
    }
}
~~~

Nếu bean được khởi tạo trong quá trình refresh, dữ liệu trong values đã có thể nằm trong heap tại checkpoint onRefresh. Sau restore, ứng dụng có thể sử dụng đối tượng đã được tạo mà không phải thực hiện lại cùng công việc khởi tạo.

Ví dụ này chỉ phù hợp với dữ liệu ổn định và có thể dùng chung. Nếu dữ liệu thay đổi theo thời gian, quyền truy cập hoặc replica, cần xác minh freshness sau restore hoặc nạp lại từ nguồn có thẩm quyền.

### 4.2. Cache được làm nóng trong quá trình refresh

Một cache có thể được khởi tạo trước checkpoint nếu quá trình warm-up hoàn tất đồng bộ trong callback khởi tạo bean. Nhưng cần cân nhắc:

- Cache có dữ liệu thay đổi trong lúc JVM dừng hay không?
- Cache có chứa token, session hoặc dữ liệu riêng người dùng không?
- Cache có thể được chia sẻ giữa nhiều replica hay cần namespace riêng?
- Có thể làm mới cache sau restore theo từng phần không?
- Việc restore đồng thời nhiều replica có tạo tải đột biến lên nguồn dữ liệu không?

Không đưa dữ liệu có thời hạn ngắn vào ảnh chỉ để tránh một lần đọc nếu sau restore dữ liệu có thể đã cũ. Hãy phân biệt cache khởi tạo tĩnh với cache nghiệp vụ cần refresh.

### 4.3. Những công việc có thể chưa chạy

Trong startup pipeline thông thường, các bước sau diễn ra sau khi ApplicationContext refresh hoàn tất:

- ApplicationRunner.
- CommandLineRunner.
- Một số listener của SpringApplication như ApplicationReadyEvent.
- Công việc warm-up được lên lịch bất đồng bộ.
- Tác vụ bắt đầu sau khi server nhận request đầu tiên.

Vì vậy, nếu ứng dụng nạp model lớn hoặc làm warm-up trong CommandLineRunner, checkpoint tại onRefresh có thể được tạo trước khi công việc đó chạy. Sau restore, runner tiếp tục được thực hiện trong luồng startup; công việc warm-up đó không được tính là đã hoàn tất trong ảnh.

Nếu cần đưa kết quả warm-up vào checkpoint, hãy cân nhắc chuyển phần khởi tạo phù hợp sang giai đoạn trước refresh hoàn tất, hoặc dùng một quy trình checkpoint khác sau warm-up đã hoàn tất. Việc thay đổi vị trí warm-up phải giữ đúng lifecycle của Spring và không làm kéo dài thời gian refresh ngoài khả năng vận hành.

## 5. onRefresh không tự quản lý mọi tài nguyên

Checkpoint tại onRefresh lưu trạng thái tiến trình ở thời điểm đó. Nó không tự bảo đảm mọi tài nguyên bên ngoài có thể tiếp tục hoạt động sau restore.

Các tài nguyên cần xem xét:

| Tài nguyên | Rủi ro nếu giữ trạng thái cũ | Việc cần chuẩn bị |
|---|---|---|
| JDBC connection pool | Database hoặc network đã đóng connection | Drain transaction, đóng pool và tạo pool mới |
| HTTP client | Socket, DNS cache hoặc TLS session đã lỗi thời | Đóng client và tạo lại theo API của thư viện |
| Message consumer | Heartbeat ngừng, member session hết hạn | Dừng consumer, xử lý acknowledgment và tham gia group lại |
| Scheduler | Deadline đã trôi qua khi JVM dừng | Dừng scheduler và tính lại lịch sau restore |
| File writer | File descriptor vẫn trỏ tới file đã rotate | Flush/close trước checkpoint, mở lại path sau restore |
| Token/session | Credential đã hết hạn hoặc bị thu hồi | Lấy token mới hoặc xác thực lại |
| Lease/distributed lock | Lease có thể đã hết hạn và được cấp cho replica khác | Acquire lại và xác minh quyền sở hữu |
| Native resource | Thư viện có thể không hỗ trợ restore | Kiểm tra hỗ trợ, đóng hoặc tạo lại |

Spring Boot property chọn mốc checkpoint. Phần xử lý từng tài nguyên cần dùng CRaC Resource, Spring lifecycle hoặc cơ chế chính thức của thư viện.

## 6. Đăng ký Resource để chuẩn bị trước checkpoint

Với tài nguyên cần xử lý riêng, ứng dụng có thể triển khai org.crac.Resource và đăng ký với global context. Callback beforeCheckpoint() chuẩn bị tài nguyên trước khi ảnh được tạo; afterRestore() khôi phục tài nguyên sau khi tiến trình được restore.

Ví dụ dưới đây quản lý một client giả định:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class ExternalClientResource implements Resource {
    private final ExternalClientFactory factory;
    private volatile ExternalClient client;

    public ExternalClientResource(ExternalClientFactory factory)
            throws Exception {
        this.factory = factory;
        this.client = factory.create();

        if (Core.isCheckpointSupported()) {
            Core.getGlobalContext().register(this);
        }
    }

    public ExternalClient client() {
        ExternalClient current = client;
        if (current == null) {
            throw new IllegalStateException(
                    "External client is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        ExternalClient current = client;
        client = null;
        if (current != null) {
            current.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = factory.create();
    }
}
~~~

ExternalClient và ExternalClientFactory là kiểu do ứng dụng định nghĩa, không phải API của Spring Boot hoặc CRaC. Ví dụ minh họa cách một bean sở hữu client đăng ký resource và đóng/mở lại client. Trong ứng dụng thực tế, factory cần đọc cấu hình hiện hành, tạo kết nối mới, xác thực và xử lý timeout.

Nếu thư viện client đã có tích hợp CRaC hoặc Spring Boot tự quản lý lifecycle của thành phần đó, hãy dùng cơ chế được hỗ trợ. Tránh đóng trực tiếp socket nội bộ khi client vẫn còn tham chiếu tới socket. Việc đóng phải đi qua API lifecycle của thư viện.

### 6.1. Khi nào đăng ký resource?

Resource phải được đăng ký trước khi checkpoint tại onRefresh diễn ra. Đăng ký trong constructor hoặc callback khởi tạo bean thường có thể đáp ứng điều kiện này vì các singleton được tạo trước khi refresh hoàn tất. Tuy nhiên, hãy kiểm tra cách bean được khởi tạo:

- Bean lazy có thể chưa được tạo tại thời điểm refresh.
- Bean prototype có vòng đời khác singleton.
- Bean được tạo bất đồng bộ có thể chưa đăng ký xong.
- Resource được tạo muộn sau refresh sẽ không tham gia checkpoint đã xảy ra trước đó.

Với resource lazy hoặc tạo muộn, cần thiết kế một cơ chế đăng ký rõ ràng và bảo đảm nó hoàn tất trước lần checkpoint tương ứng. Không trì hoãn việc đăng ký tới một callback chỉ chạy sau khi checkpoint đã bắt đầu.

### 6.2. Thứ tự resource

Nếu resource phụ thuộc nhau, thứ tự đăng ký cần phản ánh thứ tự đóng và phục hồi. Ví dụ, một consumer dùng database pool:

- Trước checkpoint, dừng consumer trước rồi mới đóng database pool.
- Sau restore, tạo database pool trước rồi mới khởi động consumer.

Hãy xem quy tắc thứ tự callback của CRaC Context trong phiên bản đang dùng và đăng ký các resource theo thứ tự phù hợp. Không để hai resource cùng quản lý việc đóng một client hoặc connection pool.

## 7. Spring lifecycle và các tác vụ nền

Spring có các abstraction lifecycle như Lifecycle và SmartLifecycle. Những thành phần này cho phép Spring quản lý start/stop theo giai đoạn của ApplicationContext. Khi tích hợp CRaC, hãy xác định rõ thành phần nào được Spring quản lý và thành phần nào cần Resource riêng.

Một số câu hỏi cần trả lời:

- Worker có cần chạy trong lúc checkpoint chuẩn bị hay phải tạm dừng?
- Scheduler có cần hủy lịch và tính lại deadline sau restore không?
- Consumer có cần dừng nhận message và tham gia group lại không?
- Thread pool có thể tiếp tục dùng sau restore hay phải tạo mới?
- Thành phần có hỗ trợ Spring lifecycle hoặc CRaC integration chính thức không?

Không nên mặc định mọi thread do ứng dụng tạo đều tự động dừng và khởi động lại đúng cách. Hãy cấu hình SmartLifecycle hoặc resource callback phù hợp và kiểm thử trên phiên bản Spring Boot đang dùng.

Ví dụ khái niệm một lifecycle component:

~~~java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class BackgroundWorkerLifecycle
        implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        if (running) {
            return;
        }
        running = true;
        // Tạo hoặc khởi động worker theo chính sách ứng dụng.
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }
        running = false;
        // Ngừng nhận task, drain và dừng worker.
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

Đây là ví dụ rút gọn về Spring lifecycle. Một worker thực tế cần có cơ chế dừng, chờ hoàn tất, xử lý interrupt và tạo lại executor nếu executor cũ đã shutdown. Không dùng biến running đơn thuần để chứng minh worker đã dừng hoàn toàn.

## 8. Cấu hình môi trường và thứ tự ưu tiên property

spring.context.checkpoint là một property Spring Boot, vì vậy có thể được cung cấp qua application.properties, application.yml, biến môi trường hoặc tham số dòng lệnh theo quy tắc externalized configuration của Spring Boot.

Ví dụ biến môi trường:

~~~text
SPRING_CONTEXT_CHECKPOINT=onRefresh
~~~

Ví dụ tham số ứng dụng:

~~~text
--spring.context.checkpoint=onRefresh
~~~

Trong triển khai, nên quản lý cấu hình checkpoint theo profile hoặc môi trường:

~~~yaml
spring:
  config:
    activate:
      on-profile: crac
  context:
    checkpoint: onRefresh
~~~

Ví dụ này minh họa một cấu hình theo profile. Cần đặt nó trong đúng file cấu hình profile và bảo đảm profile crac được kích hoạt ở môi trường muốn tạo checkpoint.

Không nên bật checkpoint tự động trong mọi môi trường một cách vô tình. Môi trường phát triển, kiểm thử tích hợp và production có thể có runtime hoặc quyền hệ điều hành khác nhau. Hãy kiểm soát profile, tham số JVM và nơi lưu ảnh để tránh tạo checkpoint ngoài ý muốn.

## 9. Quy trình tạo checkpoint và restore

Một luồng vận hành tổng quát:

### Khi khởi động để tạo checkpoint

1. Khởi chạy ứng dụng trên JDK/runtime hỗ trợ CRaC.
2. Cung cấp dependency org.crac tương thích.
3. Bật spring.context.checkpoint=onRefresh trong môi trường cần tạo ảnh.
4. Cấu hình checkpoint destination và quyền truy cập.
5. Spring Boot tạo ApplicationContext và khởi tạo các bean.
6. Khi refresh hoàn tất, Spring Boot kích hoạt checkpoint theo cấu hình.
7. CRaC gọi callback chuẩn bị resource, tạo ảnh và thực hiện restore theo cơ chế runtime.
8. Ứng dụng tiếp tục startup sau khi restore; các bước sau refresh được thực hiện theo lifecycle.

### Khi sử dụng ảnh đã tạo

1. Cung cấp checkpoint image cho môi trường restore.
2. Sử dụng đúng runtime, thư viện native và điều kiện tương thích với ảnh.
3. Cấu hình restore source theo hướng dẫn của JDK/runtime.
4. Restore tiến trình.
5. CRaC gọi callback phục hồi resource.
6. Ứng dụng xác minh cấu hình, credential, kết nối và readiness.
7. Đưa instance vào nhận lưu lượng khi các dependency bắt buộc sẵn sàng.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Build Spring Boot application] --> B[Thêm org.crac dependency]
    B --> C[Chạy trên CRaC-enabled JDK]
    C --> D[Bật spring.context.checkpoint=onRefresh]
    D --> E[Spring tạo ApplicationContext]
    E --> F[Khởi tạo bean và dependency]
    F --> G[Context refresh hoàn tất]
    G --> H[CRaC checkpoint]
    H --> I[Checkpoint image]
    I --> J[Triển khai image vào môi trường restore]
    J --> K[CRaC restore]
    K --> L[afterRestore và bootstrap dependency]
    L --> M[Readiness]
    M --> N[Phục vụ request]
~~~

Checkpoint image thường gắn với môi trường runtime cụ thể. Không giả định có thể tạo ảnh trên một hệ điều hành rồi restore ở bất kỳ hệ điều hành hoặc kernel nào. Hãy xác nhận giới hạn tương thích của JDK CRaC, container runtime và công cụ checkpoint.

## 10. Những trường hợp onRefresh phù hợp

onRefresh phù hợp khi phần lớn chi phí khởi tạo nằm trong quá trình refresh và trạng thái đó có thể tái sử dụng:

- Nạp metadata hoặc cấu hình ít thay đổi.
- Khởi tạo parser, serializer và cấu trúc dữ liệu.
- Tạo các singleton bean tốn thời gian.
- Nạp model hoặc dữ liệu tham chiếu nếu việc nạp hoàn tất trước refresh.
- Chuẩn bị cache bất biến hoặc có quy trình xác minh freshness sau restore.
- Khởi tạo framework và các thành phần nội bộ không giữ tài nguyên bên ngoài không thể khôi phục.

Ví dụ, một ứng dụng xử lý tài liệu có thể nạp schema và tạo parser trong bean initialization. Nếu những đối tượng này không phụ thuộc vào identity của replica hoặc trạng thái bên ngoài có thời hạn, checkpoint sau refresh có thể giữ lại kết quả khởi tạo.

## 11. Những trường hợp cần cân nhắc mốc khác

onRefresh có thể quá sớm nếu ứng dụng cần một số bước sau refresh mới đạt trạng thái mong muốn:

- ApplicationRunner tải dữ liệu nghiệp vụ.
- CommandLineRunner làm warm-up model.
- Một tác vụ bất đồng bộ nạp cache.
- Kết nối tới dịch vụ bên ngoài chỉ được thiết lập sau khi server sẵn sàng.
- Một bước bootstrap phụ thuộc metadata của replica được cấp sau khi container bắt đầu phục vụ.

Trong trường hợp đó, cần quyết định dữ liệu nào nên có trong ảnh và dữ liệu nào nên tạo lại sau restore. Không chuyển mọi tác vụ vào refresh chỉ để đưa chúng vào checkpoint; làm như vậy có thể kéo dài thời gian refresh và gây lỗi timeout của hệ thống triển khai.

Nếu muốn checkpoint sau warm-up, cần trigger tại thời điểm warm-up thực sự hoàn tất, theo API CRaC hoặc tích hợp Spring Boot tương thích. Tránh gọi checkpoint ở nhiều nơi mà không kiểm soát số lần, vì có thể tạo nhiều ảnh hoặc làm startup flow khó dự đoán.

## 12. Lỗi thường gặp khi bật checkpoint tự động

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có checkpoint image | Runtime không hỗ trợ CRaC hoặc checkpoint destination chưa cấu hình | Kiểm tra JDK, runtime option, log và quyền ghi |
| Lỗi khi refresh context | Resource callback thất bại hoặc checkpoint không thể thực hiện | Xem lỗi gốc, kiểm tra tài nguyên và tính tương thích |
| Ứng dụng không tiếp tục startup | Restore hoặc callback phục hồi bị lỗi | Kiểm tra log CRaC, dependency và thứ tự resource |
| Kết nối database lỗi sau restore | Pool giữ connection cũ hoặc credential đã rotate | Đóng pool trước checkpoint và tạo pool mới |
| Consumer không nhận message | Member session hết hạn hoặc chưa join group lại | Tạo consumer mới và đăng ký subscription |
| Cache chứa dữ liệu cũ | Cache được snapshot trước khi nguồn dữ liệu thay đổi | Làm mới hoặc kiểm tra TTL/version |
| Warm-up không có trong ảnh | Warm-up chạy trong Runner hoặc sau refresh | Chọn mốc checkpoint sau warm-up hoặc chấp nhận warm-up sau restore |
| Appender ghi vào file cũ | File rotation diễn ra khi JVM dừng | Đóng file trước checkpoint và mở lại active path |
| Nhiều replica có cùng identity | Identity được tạo trước checkpoint và bị nhân bản | Tạo identity riêng sau restore |
| Restore không tương thích môi trường | JDK, kernel, thư viện native hoặc container khác | Dùng môi trường tương thích với checkpoint image |
| Checkpoint mất quá nhiều thời gian | Callback chờ task hoặc I/O vô hạn | Drain có deadline, timeout và chính sách hủy checkpoint |
| Startup bị kích hoạt checkpoint ngoài ý muốn | Property được bật trong profile không phù hợp | Quản lý property theo profile và cấu hình triển khai |

## 13. Quan sát và chẩn đoán

Để hiểu checkpoint tự động có diễn ra đúng thời điểm hay không, hãy ghi nhận các mốc startup và lifecycle:

- Thời điểm bắt đầu SpringApplication.
- Thời điểm bắt đầu và hoàn tất ApplicationContext refresh.
- Giá trị cấu hình spring.context.checkpoint đang được sử dụng.
- Thời điểm bắt đầu callback beforeCheckpoint và hoàn tất từng resource.
- Thời điểm runtime tạo checkpoint và vị trí artifact.
- Thời điểm restore bắt đầu và kết thúc.
- Thời điểm callback afterRestore chạy.
- Thời điểm ApplicationRunner/CommandLineRunner bắt đầu và hoàn tất.
- Thời điểm readiness chuyển sang trạng thái sẵn sàng.

Log cần có correlation ID cho một lần khởi động/restore, nhưng không ghi token, mật khẩu, private key hoặc nội dung nhạy cảm vào checkpoint log. Với nhiều replica, hãy ghi instance ID được tạo sau restore để phân biệt các bản sao.

Đừng dùng riêng ApplicationReadyEvent làm bằng chứng rằng checkpoint đã được tạo. Sự kiện này thể hiện giai đoạn ứng dụng sẵn sàng theo lifecycle Spring Boot; trạng thái checkpoint cần được xác nhận bằng log và artifact của CRaC runtime.

## 14. Kiểm thử checkpoint tại onRefresh

Kiểm thử cần chạy trên runtime CRaC thật và môi trường gần với production. Một lần khởi động thành công trên JDK thông thường không chứng minh cơ chế checkpoint hoạt động.

### 14.1. Kiểm thử cơ bản

1. Bật spring.context.checkpoint=onRefresh.
2. Chạy ứng dụng trên JDK hỗ trợ CRaC và cấu hình checkpoint destination.
3. Xác nhận Spring tạo ApplicationContext và hoàn tất refresh.
4. Xác nhận runtime nhận yêu cầu checkpoint ở mốc onRefresh.
5. Xác nhận ảnh checkpoint được tạo tại vị trí dự kiến.
6. Xác nhận tiến trình tiếp tục startup sau restore.
7. Xác nhận Runner và sự kiện ready xảy ra theo thứ tự mong muốn.
8. Khởi chạy từ ảnh checkpoint và xác nhận ứng dụng có thể phục vụ request.

### 14.2. Kiểm thử tài nguyên

- Database được restart trong lúc JVM dừng.
- Broker đóng consumer session trước khi restore.
- Token hoặc chứng chỉ hết hạn trong thời gian tạm dừng.
- Log rotation xảy ra sau khi writer được đóng.
- Scheduler bỏ lỡ một hoặc nhiều lần chạy.
- Một resource callback thất bại khi beforeCheckpoint.
- Một dependency chưa sẵn sàng trong afterRestore.
- Cùng ảnh được dùng để tạo nhiều replica và mỗi replica cần identity riêng.

### 14.3. Kiểm thử thời điểm warm-up

Tạo một bean ghi nhận thời điểm khởi tạo trong @PostConstruct và một Runner ghi nhận thời điểm warm-up. So sánh log với mốc checkpoint để xác nhận công việc nào nằm trước refresh và công việc nào chạy sau restore.

Nếu warm-up cần được lưu trong ảnh, hãy chuyển phần có thể tái sử dụng sang một giai đoạn trước refresh hoàn tất hoặc thiết kế trigger sau warm-up. Sau đó kiểm tra rằng dữ liệu warm-up thực sự có trong ảnh và vẫn hợp lệ khi restore.

### 14.4. Kiểm thử nhiều replica

Tạo nhiều replica từ cùng checkpoint image. Xác nhận:

- Bean bất biến có thể được tái sử dụng.
- Replica identity được tạo mới hoặc truy vấn từ metadata hiện tại.
- Connection pool và consumer được tạo riêng.
- Lease và quyền leader được xin lại.
- Token hoặc chứng chỉ được cấp theo chính sách.
- Readiness chỉ mở sau khi bootstrap riêng hoàn tất.

## 15. Quy trình cấu hình đề xuất

Một quy trình triển khai có thể chia thành các bước:

1. Chọn phiên bản Spring Boot có hỗ trợ CRaC.
2. Thêm dependency org.crac tương thích.
3. Dùng JDK/runtime CRaC được hỗ trợ bởi nền tảng triển khai.
4. Bật spring.context.checkpoint=onRefresh trong profile tạo checkpoint.
5. Cấu hình checkpoint destination, volume, permission và bảo vệ artifact.
6. Xác định bean nào có thể giữ trạng thái qua checkpoint.
7. Đăng ký Resource cho kết nối, worker và tài nguyên cần đóng/mở lại.
8. Đảm bảo resource được đăng ký trước mốc refresh.
9. Kiểm thử thứ tự callback và thứ tự startup.
10. Tạo checkpoint image và kiểm tra restore trên môi trường tương thích.
11. Xác minh Runner, readiness, identity và dependency sau restore.
12. Đưa image vào pipeline triển khai và theo dõi thời gian khởi động thực tế.

## 16. Những nguyên tắc cần nhớ

- spring.context.checkpoint=onRefresh yêu cầu Spring Boot checkpoint sau khi ApplicationContext refresh hoàn tất.
- Property này chọn mốc checkpoint trong startup; nó không phải lịch checkpoint định kỳ.
- ApplicationRunner và CommandLineRunner thường chạy sau refresh, nên không mặc định kết quả warm-up của chúng đã nằm trong ảnh.
- Dependency org.crac chỉ cung cấp API; runtime/JDK và môi trường phải thực sự hỗ trợ CRaC.
- Bean được tạo trước refresh có thể được snapshot, nhưng cache và dữ liệu có thời hạn vẫn cần xác minh sau restore.
- Connection pool, socket, consumer, scheduler, file writer và credential cần lifecycle riêng.
- Resource phải được đăng ký trước checkpoint và callback phải hoàn tất trong thời hạn có kiểm soát.
- Không gọi thêm checkpoint ở nhiều nơi nếu chưa có chính sách trigger rõ ràng.
- Quản lý property theo profile để tránh bật checkpoint ngoài môi trường mong muốn.
- Xác nhận checkpoint image và restore bằng runtime thực tế; log startup đơn thuần không chứng minh artifact đã được tạo.

Checkpoint tự động tại onRefresh giúp Spring Boot lưu trạng thái sau giai đoạn khởi tạo ApplicationContext. Đây là lựa chọn phù hợp khi phần lớn công việc chuẩn bị có thể hoàn tất trong quá trình refresh. Để sử dụng an toàn, cần hiểu chính xác mốc này trong startup pipeline, phân biệt nó với các bước Runner/ready, chuẩn bị resource bằng callback CRaC và kiểm thử restore trên môi trường triển khai thật.
