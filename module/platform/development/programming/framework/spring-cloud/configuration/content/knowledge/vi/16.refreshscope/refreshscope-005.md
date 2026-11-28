# Đóng tài nguyên cũ khi bean được tạo lại

Một bean thuộc **@RefreshScope** có thể được tạo lại sau khi cấu hình thay đổi. Nếu bean sở hữu connection pool, HTTP client, file handle, scheduler hoặc tài nguyên có vòng đời riêng, việc tạo target mới cần đi kèm việc giải phóng target cũ. Nếu không đóng tài nguyên, ứng dụng có thể tích lũy connection, thread, socket hoặc file handle qua nhiều lần refresh.

Spring Cloud RefreshScope quản lý cache target và gọi destruction callback đã đăng ký khi target bị loại khỏi scope. Vì vậy, bean cần khai báo rõ cách đóng tài nguyên mà nó sở hữu, chẳng hạn **@PreDestroy**, **DisposableBean.destroy()** hoặc destroy method của bean. RefreshScope không tự đoán cách đóng mọi tài nguyên được tạo bên trong object.

Bài học này giải thích vòng đời của target trong RefreshScope, cách khai báo callback đóng tài nguyên, cách tránh đóng nhầm hoặc đóng hai lần và những giới hạn cần tính đến khi refresh trong lúc ứng dụng đang xử lý request.

Sau bài học, bạn có thể:

- Mô tả điều gì xảy ra với target cũ khi RefreshScope được làm mới.
- Khai báo callback giải phóng tài nguyên bằng **@PreDestroy**, **DisposableBean** hoặc **@Bean(destroyMethod=...)**.
- Thiết kế bean refresh-scoped sở hữu connection pool hoặc HTTP client có thể đóng đúng cách.
- Phân biệt proxy còn tồn tại với target cũ đã bị hủy và target mới được tạo.
- Xử lý an toàn khi có request đang sử dụng tài nguyên trong lúc refresh.
- Kiểm thử số lần tạo, đóng và tái tạo tài nguyên để phát hiện rò rỉ.

## 1. Vòng đời target trong RefreshScope

Bean có **@RefreshScope** được truy cập thông qua scoped proxy. Proxy là đối tượng mà các thành phần khác inject; target thực tế được tạo và lưu trong cache của scope khi cần sử dụng.

Khi Config Client nhận sự kiện refresh, RefreshScope loại target đang được cache khỏi scope. Trong quá trình loại bỏ, scope gọi destruction callback đã đăng ký cho target. Lần gọi tiếp theo qua proxy sẽ tạo một target mới và lưu target mới vào cache.

~~~mermaid
sequenceDiagram
    participant Caller as Bean tiêu thụ
    participant Proxy as Refresh-scope proxy
    participant Scope as RefreshScope
    participant Old as Target cũ
    participant New as Target mới

    Caller->>Proxy: Gọi phương thức
    Proxy->>Scope: Lấy target hiện tại
    Scope-->>Proxy: Target cũ
    Proxy->>Old: Thực thi
    Note over Scope,Old: Target cũ đang nằm trong cache

    Note over Scope,Old: RefreshScope được refresh
    Scope->>Scope: Loại wrapper của target cũ khỏi cache
    Scope->>Old: Gọi destruction callback
    Old->>Old: Đóng tài nguyên đang sở hữu

    Caller->>Proxy: Gọi phương thức lần tiếp theo
    Proxy->>Scope: Lấy target hiện tại
    Scope->>New: Tạo target mới
    New->>New: Khởi tạo tài nguyên mới
    Scope-->>Proxy: Target mới
    Proxy->>New: Thực thi
~~~

Có ba đối tượng cần phân biệt:

- **Scoped proxy:** thường vẫn là cùng một object được các bean khác giữ qua dependency injection.
- **Target cũ:** object đã được tạo trước refresh; khi bị loại khỏi cache, destruction callback của nó được gọi.
- **Target mới:** được tạo khi có lời gọi tiếp theo qua proxy; constructor và quá trình inject cấu hình chạy lại.

RefreshScope không nhất thiết tạo target mới ngay trong lúc nhận refresh event. Việc tạo mới thường diễn ra lazy ở lần truy cập tiếp theo. Vì vậy, lỗi cấu hình hoặc lỗi mở tài nguyên có thể chỉ xuất hiện khi ứng dụng gọi bean sau refresh.

## 2. RefreshScope gọi destruction callback như thế nào?

Spring quản lý vòng đời bean thông qua các callback hủy. Khi bean được tạo bởi Spring và scope loại bean đó khỏi cache, callback đã đăng ký sẽ được thực thi.

Các cách khai báo phổ biến:

| Cơ chế | Cách dùng | Khi phù hợp |
|---|---|---|
| **@PreDestroy** | Đánh dấu phương thức đóng tài nguyên trên bean | Bean cần gom nhiều thao tác dọn dẹp |
| **DisposableBean** | Implement phương thức **destroy()** | Bean cần tham gia rõ ràng vào lifecycle contract của Spring |
| **@Bean(destroyMethod="close")** | Chỉ định phương thức đóng trên object được tạo bởi factory method | Bean trả về resource có phương thức close/shutdown |
| **AutoCloseable / Closeable** | Dùng cùng destroy callback hoặc destroy method được cấu hình | Tài nguyên có API đóng chuẩn của Java |

Spring gọi callback đã đăng ký khi target bị scope hủy. Không cần tự gọi phương thức đóng từ controller hoặc từ bean tiêu thụ.

### Dùng @PreDestroy

Với Spring Boot 3 và Spring Framework 6, dùng **jakarta.annotation.PreDestroy**. Ví dụ bean sở hữu một HTTP client có thể đóng:

~~~java
import java.io.IOException;
import java.net.URI;

import jakarta.annotation.PreDestroy;

import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class PartnerApiClient {

    private final URI baseUri;
    private final CloseableHttpClient httpClient;

    public PartnerApiClient(
            @Value("\${partner.api.base-url}") URI baseUri) {
        this.baseUri = baseUri;
        this.httpClient = HttpClients.createDefault();
    }

    public URI baseUri() {
        return baseUri;
    }

    @PreDestroy
    public void closeResources() {
        try {
            httpClient.close();
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot close partner HTTP client", ex);
        }
    }
}
~~~

Khi target cũ bị loại khỏi RefreshScope, Spring gọi **closeResources()**. Phương thức đóng HTTP client do target sở hữu. Khi target mới được tạo, constructor mở một HTTP client mới với cấu hình hiện tại.

Ví dụ rút gọn này minh họa ownership và lifecycle. Trong ứng dụng thực tế, nên giữ HTTP client ở phạm vi bean, cung cấp các phương thức nghiệp vụ cần thiết và tránh trả resource nội bộ ra ngoài nếu caller có thể giữ lại reference sau refresh.

Với Spring Boot 2.x, dự án cũ có thể dùng **javax.annotation.PreDestroy** tùy phiên bản dependency. Không trộn namespace javax và jakarta trong cùng một ứng dụng; dùng annotation phù hợp với phiên bản Spring Framework.

### Implement DisposableBean

Có thể khai báo callback bằng interface của Spring:

~~~java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class ManagedWorker implements DisposableBean {

    private final WorkerResources resources = WorkerResources.open();

    public void execute() {
        resources.execute();
    }

    @Override
    public void destroy() {
        resources.close();
    }
}
~~~

Spring gọi **destroy()** khi target bị hủy. Cách này rõ ràng nhưng gắn lớp trực tiếp với Spring API. Nếu muốn lớp nghiệp vụ ít phụ thuộc Spring hơn, có thể dùng **@PreDestroy** hoặc khai báo destroy method ở cấu hình bean.

### Dùng @Bean(destroyMethod="close")

Với tài nguyên được tạo trong một phương thức **@Bean**, khai báo destroy method rõ ràng:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReportingDataSourceConfiguration {

    @Bean(destroyMethod = "close")
    @RefreshScope
    public HikariDataSource reportingDataSource(
            @Value("\${reporting.datasource.jdbc-url}") String jdbcUrl,
            @Value("\${reporting.datasource.username}") String username,
            @Value("\${reporting.datasource.password}") String password) {

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(jdbcUrl);
        config.setUsername(username);
        config.setPassword(password);
        return new HikariDataSource(config);
    }
}
~~~

Khi target DataSource cũ bị hủy, Spring gọi **close()** trên HikariDataSource để đóng pool. Target mới được tạo ở lần truy cập tiếp theo và mở pool mới với thông tin cấu hình mới.

Chỉ dùng một cơ chế destroy phù hợp cho mỗi resource. Nếu vừa tự đóng trong **@PreDestroy**, vừa cấu hình destroy method gọi cùng thao tác, cần bảo đảm không phát sinh đóng lặp hoặc thiết kế phương thức đóng có tính idempotent.

## 3. Bean phải sở hữu tài nguyên mà nó đóng

Nguyên tắc quan trọng là đóng đúng tài nguyên do target sở hữu. Không đóng một resource chỉ vì bean có reference đến nó.

Ví dụ:

- Bean tự tạo HTTP client trong constructor thì bean có trách nhiệm đóng client đó.
- Bean nhận một client dùng chung từ một singleton khác thì thường không được tự đóng client dùng chung.
- Bean nhận một pool được quản lý bởi container hoặc một bean khác thì cần xác định rõ owner trước khi khai báo destroy callback.
- Resource tạo bằng **new** bên ngoài Spring và không được đăng ký lifecycle sẽ không tự nhận callback của RefreshScope.

Nếu nhiều bean cùng giữ một resource, cần có một owner duy nhất hoặc một cơ chế chia sẻ có quản lý vòng đời. Nếu mỗi bean tự gọi close trên cùng object, một lần refresh có thể làm hỏng tài nguyên mà bean khác vẫn đang sử dụng.

Một cách phân định ownership:

| Resource | Owner phù hợp | Hành động khi target bị hủy |
|---|---|---|
| HTTP client được tạo trong target | Target đó | Đóng client |
| Hikari connection pool do target tạo | Target đó | Đóng pool |
| Executor service do target tạo | Target đó | Dừng nhận task mới và shutdown theo chính sách |
| File handle do target mở | Target đó | Flush dữ liệu cần thiết rồi đóng file |
| Shared Redis connection do singleton quản lý | Singleton sở hữu connection | Target tiêu thụ không tự đóng |
| Client được inject từ bean khác | Bean tạo và quản lý client | Chỉ giải phóng nếu hợp đồng ownership quy định rõ |

Không dùng garbage collection làm cơ chế giải phóng connection, socket, file hoặc thread. Garbage collection không thay thế callback đóng tài nguyên và thời điểm chạy không được bảo đảm.

## 4. Hủy target cũ và tạo target mới

Với một target refresh-scoped, trình tự thường là:

1. Client nhận refresh event.
2. RefreshScope tìm target đang cache.
3. Scope loại wrapper của target cũ khỏi cache.
4. Scope gọi destruction callback của target cũ.
5. Target cũ giải phóng tài nguyên.
6. Khi proxy được gọi tiếp, scope tạo target mới.
7. Constructor và dependency injection của target mới chạy với Environment hiện tại.
8. Target mới mở tài nguyên mới và được lưu trong cache.

Điều này có nghĩa refresh không phải thao tác thay đổi field bên trong object cũ. Target cũ được hủy theo lifecycle; lần truy cập tiếp theo qua proxy sẽ tạo target mới. Trong luồng tuần tự, callback đóng target cũ được thực hiện trong lúc scope hủy target. Nếu có request đồng thời, không nên giả định việc đóng resource cũ và khởi tạo resource mới luôn tách biệt hoàn toàn về thời gian; hãy thiết kế và kiểm thử chính sách drain/synchronization theo loại tài nguyên.

Nếu constructor của target mới thất bại, ví dụ URL sai, credentials không hợp lệ hoặc pool không kết nối được, lỗi xuất hiện khi target mới được yêu cầu. Không nên giả định refresh endpoint đã trả thành công đồng nghĩa tài nguyên mới đã mở thành công. Hãy có health check hoặc kiểm tra chủ động sau refresh để xác nhận target mới hoạt động.

## 5. Xử lý request đang dùng target cũ

RefreshScope quản lý việc loại target khỏi cache và gọi destruction callback. Nó không thay thế một giao thức drain request chung cho mọi loại tài nguyên.

Nếu một request đang sử dụng HTTP client, connection hoặc stream trong lúc target bị hủy, việc đóng resource có thể làm thao tác đó thất bại. Mức độ ảnh hưởng phụ thuộc resource, thư viện và cách ứng dụng đồng bộ việc sử dụng.

Với tác vụ ngắn, có thể chấp nhận một cửa sổ gián đoạn nhỏ nếu hệ thống có retry an toàn. Với tác vụ dài, transaction hoặc stream, cần thiết kế thêm:

- Ngừng nhận tác vụ mới trước khi đóng resource nếu nghiệp vụ yêu cầu.
- Chờ các tác vụ đang chạy hoàn tất bằng cơ chế drain hoặc giới hạn thời gian.
- Dùng timeout cho quá trình shutdown để tránh treo vô hạn.
- Đảm bảo close có thể gọi lặp mà không làm hỏng trạng thái.
- Phân biệt lỗi do refresh với lỗi nghiệp vụ và chỉ retry thao tác có tính an toàn.
- Kiểm thử refresh đồng thời với request thật, transaction và tải cao.

Không giữ lock toàn cục quanh mọi request chỉ để tránh refresh. Hãy chọn cơ chế đồng bộ phù hợp với resource và yêu cầu độ sẵn sàng. Nếu thư viện connection pool đã hỗ trợ đóng mềm hoặc chờ connection đang dùng, hãy dùng đúng tính năng và kiểm tra timeout của nó.

## 6. Thiết kế phương thức close an toàn

Phương thức đóng tài nguyên nên có các đặc điểm:

1. **Có thể gọi lặp an toàn:** nếu callback hoặc quá trình shutdown được kích hoạt nhiều lần, lần gọi sau không làm hỏng ứng dụng.
2. **Có giới hạn thời gian:** không để shutdown chờ vô hạn khi resource không phản hồi.
3. **Đóng theo thứ tự phụ thuộc:** đóng các thành phần sử dụng resource trước, rồi đóng resource nền tảng.
4. **Giữ lại lỗi cần thiết:** ghi nhận lỗi đóng để vận hành điều tra, nhưng không ghi credentials hoặc payload nhạy cảm.
5. **Không tạo tài nguyên mới:** destruction callback chỉ dọn dẹp resource cũ, không khởi tạo lại target.
6. **Không đóng resource không thuộc ownership:** tránh đóng shared dependency do bean khác quản lý.

Ví dụ với một bean quản lý nhiều tài nguyên:

~~~java
import jakarta.annotation.PreDestroy;

import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class ReportEngine {

    private final ReportExecutor executor;
    private final ReportFileStore fileStore;

    public ReportEngine() {
        this.fileStore = ReportFileStore.open();
        this.executor = ReportExecutor.create(fileStore);
    }

    public void generate() {
        executor.generate();
    }

    // Getter này chỉ phục vụ ví dụ truy cập resource không an toàn bên dưới.
    public ReportFileStore fileStore() {
        return fileStore;
    }

    @PreDestroy
    public void close() {
        try {
            executor.shutdownAndAwait();
        } finally {
            fileStore.close();
        }
    }
}
~~~

Ví dụ giả định **ReportExecutor** sử dụng **ReportFileStore**, vì vậy executor được dừng trước rồi file store mới được đóng. Trong mã thực tế, cần xử lý exception riêng cho từng bước để lỗi ở bước đầu không ngăn bước sau được dọn dẹp. Nếu executor có thể không dừng trong thời gian giới hạn, cần có chính sách timeout và báo lỗi phù hợp.

## 7. Tránh giữ resource cũ bên ngoài proxy

Một bean singleton có thể inject scoped proxy và gọi nó mỗi lần cần resource. Nhưng nếu nó lấy resource nội bộ từ target rồi lưu vào field, reference đó có thể trỏ đến resource đã bị đóng sau refresh.

Ví dụ không an toàn dưới đây cố ý expose resource nội bộ để cho thấy caller có thể giữ reference đã bị đóng. Không thiết kế getter này trong API production:

~~~java
@Component
public class ReportService {

    private final ReportFileStore fileStore;

    public ReportService(ReportEngine engine) {
        this.fileStore = engine.fileStore();
    }

    public void generate() {
        fileStore.writeReport();
    }
}
~~~

Nếu **ReportEngine** là refresh-scoped và **fileStore** là resource do target tạo, **ReportService** đã giữ trực tiếp resource của target cũ. Khi scope hủy target, file store bị đóng nhưng ReportService vẫn giữ reference cũ.

Thiết kế tốt hơn là giữ proxy và gọi phương thức nghiệp vụ qua proxy:

~~~java
@Component
public class ReportService {

    private final ReportEngine engine;

    public ReportService(ReportEngine engine) {
        this.engine = engine;
    }

    public void generate() {
        engine.generate();
    }
}
~~~

Như vậy, mỗi lần gọi đi qua proxy để lấy target hiện tại. Không expose resource nội bộ nếu caller không cần quyền sở hữu hoặc quyền đóng resource đó.

## 8. Refresh qua Actuator và Spring Cloud Bus

Khi endpoint **POST /actuator/refresh** được gọi trên Config Client, client nạp lại cấu hình và làm mới các bean thuộc RefreshScope. Destruction callback của từng target bị loại khỏi scope được gọi trên instance đó.

Với nhiều instance, Spring Cloud Bus có thể phân phối refresh event đến các client. Mỗi instance nhận event sẽ làm mới scope cục bộ và đóng các target cũ mà nó đang quản lý. Vì event có thể đến các instance ở thời điểm khác nhau, quá trình đóng tài nguyên cũng diễn ra phân tán, không phải một thao tác nguyên tử trên toàn cụm.

Trình tự vận hành nên có:

1. Xác nhận Config Server đã trả revision cấu hình mới.
2. Phát refresh event đến client hoặc qua Bus.
3. Theo dõi từng instance đã nhận event và hoàn tất callback đóng.
4. Gửi request kiểm tra để buộc target mới được tạo nếu cần.
5. Xác nhận target mới mở resource thành công và health check đạt.
6. Theo dõi số connection, thread, file handle và lỗi request sau refresh.

Endpoint refresh và bus refresh cần được expose có chọn lọc, xác thực và phân quyền. Không mở endpoint quản trị công khai.

## 9. Kiểm thử việc đóng và tạo lại tài nguyên

Không chỉ kiểm tra giá trị cấu hình sau refresh. Cần chứng minh resource cũ đã được đóng và resource mới đã được tạo.

Có thể dùng một resource giả trong unit hoặc integration test để đếm số lần mở và đóng:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class TrackedResource implements AutoCloseable {

    private final AtomicInteger closeCount;
    private final AtomicBoolean closed = new AtomicBoolean();

    public TrackedResource(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    public boolean isOpen() {
        return !closed.get();
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            closeCount.incrementAndGet();
        }
    }
}
~~~

Trong test, tạo bean refresh-scoped sở hữu **TrackedResource** và đăng ký callback đóng. Kịch bản kiểm tra:

| Bước | Điều cần xác minh |
|---|---|
| Lần gọi đầu tiên qua proxy | Target thứ nhất được tạo, resource thứ nhất mở |
| Gọi refresh scope | Callback target thứ nhất chạy, resource thứ nhất đóng đúng một lần |
| Gọi proxy lần tiếp theo | Target thứ hai được tạo, resource thứ hai mở |
| Refresh lần nữa | Resource thứ hai đóng đúng một lần |
| Đóng ApplicationContext | Target đang tồn tại được cleanup khi context shutdown |

Đảm bảo test phân biệt số lần target được tạo và số lần resource được đóng. Nếu test chỉ kiểm tra constructor chạy lại mà không kiểm tra close, nó không phát hiện được resource leak.

Với connection pool hoặc HTTP client thật, nên có integration test kiểm tra metric connection, thread và khả năng request tiếp tục hoạt động sau refresh. Kiểm thử thêm trường hợp target mới không khởi tạo được và trường hợp refresh xảy ra khi request đang chạy.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Số connection hoặc thread tăng sau nhiều lần refresh | Target cũ không có destruction callback đóng resource | Thêm **@PreDestroy**, **destroy()** hoặc destroy method |
| Callback không được gọi | Resource không thuộc bean do Spring quản lý hoặc target không được tạo trong scope | Kiểm tra bean definition và cách tạo resource |
| Resource bị đóng hai lần | Nhiều callback cùng gọi close trên một resource | Chọn một cơ chế destroy hoặc làm close idempotent |
| Request đang chạy lỗi ngay khi refresh | Target cũ bị đóng trong lúc request còn sử dụng resource | Thiết kế drain, timeout và retry an toàn |
| Target mới tạo nhưng request lỗi | Constructor hoặc mở resource thất bại | Kiểm tra cấu hình mới, credentials, endpoint và health |
| Singleton vẫn dùng resource cũ | Caller giữ trực tiếp resource thay vì gọi qua scoped proxy | Giữ proxy và không copy resource nội bộ ra ngoài |
| Đóng resource dùng chung làm bean khác lỗi | Ownership không rõ ràng | Chỉ owner đóng resource; thống nhất lifecycle contract |
| Refresh endpoint thành công nhưng resource mới chưa mở | Target được tạo lazy ở lần truy cập sau | Thực hiện smoke test qua proxy sau refresh |

## 11. Checklist trước khi đưa RefreshScope vào production

- Xác định resource nào do target sở hữu và resource nào được chia sẻ.
- Mỗi resource do target tạo có một đường đóng rõ ràng.
- Callback đóng được gọi khi target bị loại khỏi RefreshScope.
- Phương thức close có thể gọi lặp và có timeout phù hợp.
- Không để bean khác giữ reference trực tiếp đến resource của target cũ.
- Có chính sách cho request, transaction hoặc stream đang chạy trong lúc refresh.
- Kiểm tra target mới tạo và mở resource thành công sau refresh.
- Theo dõi số connection, thread, socket và file handle qua nhiều lần refresh.
- Thử rollback khi cấu hình mới khiến target mới không khởi tạo được.
- Bảo vệ endpoint refresh và refresh qua Bus.

## 12. Tự kiểm tra

1. Khi RefreshScope loại một target khỏi cache, điều gì xảy ra với destruction callback của target đó?
2. **@PreDestroy** khác gì với **DisposableBean.destroy()** và **@Bean(destroyMethod="close")**?
3. Vì sao RefreshScope không tự biết cách đóng mọi connection, socket hoặc executor được tạo trong bean?
4. Vì sao bean tiêu thụ nên giữ scoped proxy thay vì giữ trực tiếp resource nội bộ của target?
5. Điều gì có thể xảy ra nếu refresh đóng connection pool trong lúc request đang sử dụng connection?
6. Vì sao close nên có tính idempotent và timeout?
7. Làm thế nào kiểm thử chứng minh mỗi resource cũ đã được đóng đúng một lần?
8. Vì sao refresh event qua Bus không làm quá trình đóng resource trên toàn cụm trở thành nguyên tử?

Hãy tạo một bean **@RefreshScope** sở hữu một resource có phương thức close. Ghi nhận số lần tạo và đóng resource. Khởi động client, gọi bean để tạo target, sau đó refresh cấu hình và gọi proxy lần nữa. Xác minh callback của target cũ đã chạy trước khi resource của target mới được sử dụng. Lặp lại nhiều lần và theo dõi số resource còn mở. Cuối cùng, mô phỏng một request kéo dài trong lúc refresh để kiểm tra chính sách drain hoặc retry của ứng dụng.

## Tài liệu tham khảo

- [Spring Cloud Commons — Refresh Scope and Refreshing the Configuration](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Framework — Bean Lifecycle and Destruction Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Using @Bean and Destroy Methods](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)

