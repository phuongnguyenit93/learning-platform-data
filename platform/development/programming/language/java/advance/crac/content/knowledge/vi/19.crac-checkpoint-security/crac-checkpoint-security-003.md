# Nạp hoặc làm mới bí mật sau restore và giới hạn của việc xóa dấu vết trong heap

Checkpoint CRaC lưu trạng thái bộ nhớ của tiến trình JVM tại một thời điểm. Nếu ứng dụng đang giữ password, access token, API key, private key đã nạp, session credential hoặc dữ liệu xác thực trong heap, những giá trị đó có thể được ghi vào ảnh checkpoint. Khi ảnh được lưu, sao chép hoặc chuyển sang môi trường khác, bí mật có thể đi theo ảnh và tồn tại lâu hơn vòng đời dự kiến.

Một chiến lược bảo mật quan trọng là chỉ nạp hoặc làm mới bí mật sau khi restore, ngay trước khi thành phần cần chúng được phép hoạt động. Trước checkpoint, ứng dụng nên ngừng sử dụng credential, đóng hoặc giải phóng các đối tượng giữ bí mật khi có thể, và loại bỏ các bản sao tạm thời theo khả năng của API. Tuy nhiên, không thể cam kết xóa sạch mọi dấu vết bí mật khỏi heap Java chỉ bằng cách gán biến thành null hoặc ghi đè một mảng.

JVM có garbage collector, có thể sao chép object trong quá trình compact heap, thư viện có thể tạo bản sao nội bộ và một số API biểu diễn bí mật bằng String bất biến. Dữ liệu cũ cũng có thể còn trong vùng nhớ chưa được tái sử dụng. Vì vậy, zeroization trong Java chỉ là biện pháp giảm rủi ro có giới hạn; nó không thay thế việc tránh đưa bí mật vào checkpoint, bảo vệ ảnh và giới hạn quyền truy cập.

Bài học này tập trung vào ba nguyên tắc:

- **Không đóng gói bí mật dài hạn nếu có thể lấy chúng sau restore.** Ưu tiên workload identity và secret manager để cấp credential ngắn hạn khi instance hoạt động.
- **Làm mới theo đúng thứ tự lifecycle.** Secret phải sẵn sàng trước khi database pool, HTTP client, broker hoặc TLS component cần chúng kết nối lại.
- **Không tuyên bố heap đã được làm sạch tuyệt đối.** Xóa tham chiếu và ghi đè buffer chỉ giảm khả năng lộ; cần kết hợp kiểm soát artifact, mã hóa, rotation và kiểm thử.

## 1. Vì sao bí mật có thể bị lưu trong checkpoint?

Một ứng dụng thường nạp bí mật trong lúc khởi động và giữ chúng trong object graph để dùng nhiều lần. Ví dụ:

- Password database trong cấu hình hoặc connection pool.
- Access token và refresh token trong HTTP client.
- API key trong singleton hoặc static field.
- Private key hoặc secret key trong đối tượng cryptographic provider.
- Credential dùng để kết nối message broker, cache hoặc cloud API.
- Cookie, session ID và authorization header trong request hoặc cache.
- Secret được giải mã từ environment variable, file mount hoặc secret manager.

Khi checkpoint, các object đang được tham chiếu có thể được lưu cùng heap. Nếu ảnh được chuyển đến một môi trường có quyền truy cập khác, người có thể đọc ảnh có thể có cơ hội khôi phục những dữ liệu nhạy cảm đó. Cụ thể dữ liệu nào được ghi còn phụ thuộc trạng thái tiến trình, cơ chế checkpoint, vùng nhớ native và cách thư viện quản lý secret; không nên giả định credential chỉ tồn tại ở một field.

### Một ví dụ dễ gặp

~~~java
public final class DatabaseConfig {
    private final String username;
    private final String password;

    public DatabaseConfig(String username, String password) {
        this.username = username;
        this.password = password;
    }
}
~~~

Nếu object này được tạo trước checkpoint và còn được một bean hoặc pool tham chiếu, password có thể nằm trong heap image. Đặt biến cục bộ chứa password thành null không xóa field trong object khác. Ngay cả khi object không còn được ứng dụng sử dụng, dữ liệu byte cũ có thể còn trong vùng heap chưa được ghi đè.

### Phân biệt bí mật với cấu hình thông thường

Không phải mọi cấu hình đều là secret. Hostname database, tên service, port hoặc feature flag có thể không nhạy cảm, tùy kiến trúc. Password, token, private key và dữ liệu xác thực phải được phân loại riêng.

| Dữ liệu | Ví dụ | Cách xử lý quanh checkpoint |
|---|---|---|
| Cấu hình không bí mật | Service name, port, timeout | Có thể giữ nếu tương thích môi trường restore |
| Secret dài hạn | Password cố định, API key | Tránh lưu trong ảnh; chuyển sang cơ chế cấp phát an toàn |
| Credential ngắn hạn | Access token, DB password tạm thời | Làm mới sau restore và giới hạn TTL |
| Private key | Khóa TLS hoặc ký | Ưu tiên HSM/KMS hoặc provider không xuất khóa; nếu phải nạp vào JVM, giảm thời gian và bản sao |
| Session/request data | Cookie, authorization header | Không để trong cache hoặc buffer có thể checkpoint nếu không cần |
| Secret dùng để bootstrap | Workload identity token hoặc credential truy cập secret manager | Bảo vệ theo cùng mức nhạy cảm; không giả định bootstrap secret không quan trọng |

## 2. Thiết kế để bí mật được nạp sau restore

Thay vì đưa password hoặc token vào image, ứng dụng có thể giữ một provider biết cách lấy secret từ nguồn đáng tin cậy khi cần. Nguồn này có thể là secret manager, KMS, workload identity, service account hoặc cơ chế cấp credential của nền tảng.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Ứng dụng đang ACTIVE] --> B[Đóng admission và drain request]
    B --> C[Đóng client phụ thuộc secret]
    C --> D[Giải phóng secret trong phạm vi có thể]
    D --> E[Checkpoint]
    E --> F[Restore JVM]
    F --> G[afterRestore]
    G --> H[Xác thực workload identity hiện tại]
    H --> I[Lấy secret hoặc token mới]
    I --> J[Khởi tạo lại database, HTTP và broker client]
    J --> K[Kiểm tra dependency]
    K --> L[Mở readiness]
~~~

Điểm quan trọng là secret provider và các client sử dụng secret cũng có lifecycle. Nếu secret manager client giữ socket cũ hoặc credential bootstrap hết hạn, việc gọi provider ngay sau restore có thể thất bại. Phải phục hồi identity/bootstrap path trước, sau đó mới lấy application secret.

### Workload identity thay cho credential đóng gói

Nếu nền tảng hỗ trợ workload identity, ứng dụng có thể chứng minh danh tính bằng thông tin do runtime hoặc orchestrator cấp, rồi nhận token ngắn hạn. Token này có thể được giới hạn:

- Theo service hoặc workload.
- Theo audience và scope.
- Theo thời hạn ngắn.
- Theo môi trường hoặc namespace.
- Theo quyền truy cập secret cụ thể.

Không dùng một token dài hạn chung cho mọi replica nếu nền tảng có thể cấp danh tính riêng. Nếu token được lưu trong heap tại thời điểm checkpoint, token đó vẫn có thể bị khôi phục từ ảnh; do đó cần lấy token mới sau restore và thu hồi token cũ theo chính sách của hệ thống identity.

### Secret manager và KMS

Secret manager có thể cấp password database hoặc API token sau khi workload được xác thực. KMS/HSM có thể giữ private key bên ngoài JVM và chỉ cho phép thực hiện thao tác ký/giải mã mà không xuất key material.

Ưu tiên giữ secret ở hệ thống quản lý chuyên dụng khi thư viện hỗ trợ. Nếu ứng dụng bắt buộc phải nạp byte của secret vào JVM, hãy giới hạn phạm vi sử dụng, thời gian lưu, số bản sao và quyền truy cập heap dump/checkpoint artifact.

## 3. Phân biệt khởi động mới và restore

Ứng dụng cần có đường khởi tạo secret cho cả hai trường hợp:

1. **Khởi động JVM mới**: lấy workload identity, xác thực với secret manager, lấy secret hiện hành và tạo client ban đầu.
2. **Restore từ checkpoint**: object graph được phục hồi; sau đó callback phục hồi identity, lấy credential mới và thay thế các client đã đóng hoặc hết hiệu lực.

Không đặt logic lấy secret chỉ trong constructor hoặc startup callback rồi giả định constructor sẽ chạy lại sau restore. Object đã tồn tại trong heap được khôi phục; constructor của object đó không tự chạy lại.

Ngược lại, không đặt mọi logic khởi tạo chỉ trong `afterRestore()`, vì lần chạy JVM mới thông thường không đi qua callback restore.

Một thiết kế phù hợp là dùng một service điều phối có các thao tác tách biệt:

- `initializeForFreshStart()` cho JVM mới.
- `prepareForCheckpoint()` để ngừng sử dụng và giải phóng credential.
- `refreshAfterRestore()` để lấy secret mới.
- `isReady()` để cho biết credential và client bắt buộc đã sẵn sàng.

Các method trên là API do ứng dụng định nghĩa, không phải API CRaC.

## 4. Đăng ký resource và thứ tự phục hồi

CRaC cung cấp `org.crac.Resource` với callback `beforeCheckpoint(...)` và `afterRestore(...)`. Có thể dùng một resource điều phối việc làm mới secret hoặc chia trách nhiệm giữa identity provider, secret provider và client resource.

Thứ tự phụ thuộc phải rõ ràng:

1. Phục hồi workload identity hoặc bootstrap credential.
2. Kết nối secret manager/KMS và lấy secret mới.
3. Tạo database pool, HTTP client, broker client và TLS context cần thiết.
4. Kiểm tra các dependency.
5. Mở readiness/admission.

Không dựa vào thứ tự tình cờ của component scan hoặc thứ tự đăng ký Resource nếu API/runtime không cam kết điều đó. Có thể dùng một coordinator duy nhất để điều phối chuỗi phụ thuộc, hoặc dùng cơ chế ordering/context được tài liệu CRaC và framework hỗ trợ.

### Ví dụ coordinator

Ví dụ sau minh họa lifecycle. Các interface là abstraction của ứng dụng; triển khai thực tế phải dùng workload identity và secret manager của môi trường.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class SecretLifecycleResource implements Resource {

    public interface WorkloadIdentity {
        void refresh() throws Exception;
    }

    public interface SecretProvider {
        void refreshSecrets() throws Exception;
        void clearCachedSecrets();
    }

    public interface DependentClients {
        void closeForCheckpoint() throws Exception;
        void recreateAndVerify() throws Exception;
    }

    public interface ReadinessGate {
        void close();
        void open();
    }

    private final WorkloadIdentity identity;
    private final SecretProvider secrets;
    private final DependentClients clients;
    private final ReadinessGate readiness;

    public SecretLifecycleResource(
            WorkloadIdentity identity,
            SecretProvider secrets,
            DependentClients clients,
            ReadinessGate readiness) {
        this.identity = identity;
        this.secrets = secrets;
        this.clients = clients;
        this.readiness = readiness;
        Core.getGlobalContext().register(this);
    }

    public void initializeForFreshStart() throws Exception {
        readiness.close();
        identity.refresh();
        secrets.refreshSecrets();
        clients.recreateAndVerify();
        readiness.open();
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.close();
        clients.closeForCheckpoint();
        secrets.clearCachedSecrets();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        readiness.close();
        identity.refresh();
        secrets.refreshSecrets();
        clients.recreateAndVerify();
        readiness.open();
    }
}
~~~

Đây là skeleton minh họa thứ tự, không phải triển khai hoàn chỉnh cho mọi secret manager. Các thao tác phải có timeout, logging không chứa secret, cleanup khi lỗi và chính sách retry có giới hạn. Nếu một bước thất bại, readiness phải tiếp tục đóng; không được mở cổng phục vụ chỉ vì callback đã chạy đến cuối một nhánh xử lý.

Trong ứng dụng thật, cần xác định hành vi khi checkpoint bị hủy sau khi client đã đóng và cache secret đã xóa. Nếu rollback về trạng thái ACTIVE, ứng dụng phải lấy lại credential và tạo client trước khi mở admission. Không giả định có callback afterCheckpoint tự động để khôi phục mọi thứ.

## 5. Giới hạn của việc xóa dấu vết trong Java heap

Trong Java, gán một biến thành null chỉ xóa một tham chiếu. Nó không ghi đè nội dung object mà tham chiếu đó từng trỏ tới. Garbage collector có thể thu hồi object khi không còn tham chiếu sống, nhưng thời điểm và cách vùng nhớ được tái sử dụng không được ứng dụng kiểm soát chính xác.

Ví dụ:

~~~java
String password = loadPassword();
usePassword(password);
password = null;
~~~

Sau dòng cuối, biến cục bộ không còn giữ tham chiếu đến String. Nhưng điều đó không chứng minh nội dung String đã bị xóa khỏi heap. Một object khác, log buffer, exception, cache hoặc thư viện có thể vẫn giữ bản sao. Ngay cả khi object trở thành unreachable, vùng nhớ cũ có thể vẫn chứa bytes cho đến khi bị ghi đè.

### String là bất biến

`String` là immutable. Ứng dụng không thể sửa trực tiếp nội dung của một String sau khi tạo. Các thao tác như `replace()` hoặc `toCharArray()` tạo object/buffer mới; chúng không xóa String ban đầu.

Ví dụ:

~~~java
import java.util.Arrays;

String secret = readSecret();
char[] chars = secret.toCharArray();
Arrays.fill(chars, '\0');
~~~

Đoạn mã trên chỉ ghi đè mảng char mới được tạo. String `secret` vẫn chứa nội dung cũ cho đến khi vùng nhớ được tái sử dụng. Nếu API secret manager trả về String hoặc thư viện yêu cầu password dạng String, khả năng zeroization bị giới hạn ngay từ đầu.

Với dữ liệu bí mật, ưu tiên API cho phép nhận `char[]` hoặc `byte[]` có thể ghi đè, hoặc API thực hiện thao tác bằng key handle mà không xuất key material. Tuy vậy, buffer mutable cũng không bảo đảm toàn bộ bản sao đã bị xóa.

### Ghi đè mảng chỉ là best effort

Ví dụ:

~~~java
char[] password = secretProvider.loadPassword();
try {
    authenticate(password);
} finally {
    Arrays.fill(password, '\0');
}
~~~

Mảng được ghi đè trong khối finally kể cả khi thao tác thất bại. Đây là thực hành tốt hơn giữ credential trong String lâu dài, nhưng vẫn có giới hạn:

- Thư viện nhận mảng có thể đã sao chép nội dung sang buffer khác.
- JDBC driver hoặc native library có thể giữ bản sao ở vùng native.
- Một API wrapper có thể chuyển mảng thành String.
- Compiler/JIT và runtime có thể tạo bản sao tạm trong quá trình xử lý.
- Garbage collector có thể di chuyển object hoặc giữ bản sao trong vùng heap khác.
- Buffer có thể đã được serialize, log hoặc ghi vào diagnostic artifact.

Vì vậy, không tuyên bố `Arrays.fill()` đã xóa mọi dấu vết. Nó chỉ giảm thời gian tồn tại của bản sao cụ thể mà ứng dụng sở hữu và có thể ghi đè.

### Nhiều bản sao của cùng một bí mật

Một secret có thể xuất hiện ở nhiều nơi:

| Vị trí | Vì sao có thể còn bản sao |
|---|---|
| String cấu hình | Immutable, không thể ghi đè nội dung |
| char[]/byte[] gốc | Có thể ghi đè nếu ứng dụng còn tham chiếu |
| Buffer do thư viện tạo | Ứng dụng không trực tiếp kiểm soát |
| JDBC/HTTP client | Có thể giữ credential hoặc header nội bộ |
| Exception | Message hoặc cause có thể chứa dữ liệu nhạy cảm |
| Log/trace | Có thể ghi header, URL hoặc payload |
| Heap dump/checkpoint | Có thể chứa object và vùng nhớ liên quan |
| Native memory | Có thể giữ bản sao ngoài heap |
| Direct ByteBuffer | Có lifecycle và cơ chế giải phóng riêng |

Thiết kế tốt cần giảm số bản sao ngay từ đầu. Tránh đưa secret qua nhiều lớp config, DTO, String concatenation, exception message và log. Chỉ chuyển secret tới thành phần thực sự cần nó.

## 6. Direct buffer, native memory và private key

Không phải mọi dữ liệu nhạy cảm đều nằm trong Java heap. Thư viện mã hóa, TLS provider, JDBC driver hoặc native SDK có thể lưu key material trong native memory, direct buffer hoặc cấu trúc nội bộ.

### Direct ByteBuffer

`ByteBuffer.allocateDirect()` cấp vùng nhớ ngoài heap. `clear()` hoặc đặt position về 0 chỉ thay đổi trạng thái buffer; chúng không ghi đè nội dung.

Nếu ứng dụng sở hữu buffer và API cho phép ghi, có thể ghi đè vùng dữ liệu đã sử dụng trước khi giải phóng:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(secretLength);
try {
    buffer.put(secretBytes);
    buffer.flip();
    useSecretBuffer(buffer);
} finally {
    buffer.clear();
    while (buffer.hasRemaining()) {
        buffer.put((byte) 0);
    }
}
~~~

Đoạn mã này chỉ minh họa ghi đè buffer do ứng dụng sở hữu. Nó không bảo đảm thư viện đã không sao chép dữ liệu sang buffer khác, và không phải mọi direct buffer đều có thể được giải phóng đồng bộ bằng API công khai. Tránh dùng internal JDK API để ép giải phóng nếu không có hỗ trợ chính thức.

### Cryptographic key handle

Với private key, ưu tiên HSM, KMS hoặc cryptographic provider giữ key material bên ngoài heap và chỉ cung cấp thao tác ký/giải mã. Khi key không thể export, checkpoint JVM không cần chứa bytes của private key.

Nếu key được nạp vào JVM:

- Xác định provider có giữ bản sao native hay không.
- Dùng API destroy nếu implementation hỗ trợ.
- Không gọi `getEncoded()` trừ khi thật sự cần key bytes.
- Không log key, certificate bundle có private key hoặc encoded form.
- Tạo lại hoặc lấy handle mới sau restore nếu provider yêu cầu.

Interface `javax.security.auth.Destroyable` có thể cung cấp `destroy()` và `isDestroyed()` cho một số đối tượng. Khả năng thực hiện zeroization phụ thuộc implementation; việc method trả về thành công không tự chứng minh mọi bản sao ở heap/native memory đã biến mất.

~~~java
import javax.security.auth.Destroyable;

if (credential instanceof Destroyable destroyable) {
    destroyable.destroy();
}
~~~

Hãy đọc tài liệu của provider cụ thể để biết object nào hỗ trợ destroy, thao tác đó có tác dụng gì và liệu object có thể dùng lại sau đó không.

## 7. Làm mới credential và thay thế client

Khi secret thay đổi sau checkpoint, client phụ thuộc secret cũ phải được thay thế hoặc cập nhật theo API chính thức. Chỉ cập nhật một field chứa password không có nghĩa connection pool hoặc client đã dùng credential mới.

Ví dụ:

- Database pool có thể giữ connection đã xác thực bằng password cũ.
- HTTP client có thể giữ Authorization header trong interceptor.
- Broker client có thể giữ SASL session hoặc connection đã xác thực.
- TLS context có thể giữ certificate/key đã nạp.
- Cloud SDK có thể cache token và credential provider.

Quy trình phục hồi nên:

1. Đóng admission và bảo đảm không còn request dùng client cũ.
2. Thu hồi hoặc loại bỏ client cũ theo API hỗ trợ.
3. Làm mới workload identity.
4. Lấy secret/token mới từ nguồn tin cậy.
5. Tạo client hoặc pool mới bằng credential mới.
6. Thực hiện health check và xác minh quyền.
7. Chỉ công bố client mới sau khi kiểm tra thành công.
8. Mở readiness.

Nếu thư viện hỗ trợ credential provider động hoặc token callback, ưu tiên cơ chế đó. Tuy nhiên, vẫn phải xác minh client có refresh đúng sau restore hay không; một provider object còn trong heap không bảo đảm token cache hoặc socket đã được làm mới.

### Rotation và revoke

Secret manager có thể rotate secret trong thời gian ứng dụng tạm dừng. Sau restore, ứng dụng cần dùng phiên bản hiện hành và có thể cần revoke token cũ. Thời điểm revoke phải phối hợp với các replica còn đang chạy và quá trình rollout; thu hồi quá sớm có thể làm gián đoạn instance chưa được cập nhật.

Đối với token ngắn hạn, dùng TTL ngắn và refresh trước khi hết hạn. Sau restore, không tin vào expiration timestamp trong heap nếu thời gian hoặc clock source có thể khác; xác minh token với issuer hoặc lấy token mới.

## 8. Không để secret lọt vào log và diagnostic artifact

Một lỗi phổ biến là xóa secret khỏi config nhưng vô tình ghi nó vào log:

~~~java
logger.debug("Connecting with password {}", password);
logger.error("Authentication failed for URL {}", jdbcUrl, exception);
~~~

JDBC URL hoặc exception có thể chứa username/password hoặc query parameter nhạy cảm. Authorization header, cookie, signed URL và request body cũng có thể chứa credential.

Các nguyên tắc:

- Không log password, token, private key hoặc secret bytes.
- Redact header/cookie và query parameter nhạy cảm.
- Không đưa secret vào exception message hoặc assertion output.
- Không bật wire/debug logging ở production nếu chưa có redaction.
- Kiểm tra APM, tracing, metrics label và crash reporter.
- Hạn chế quyền truy cập log, heap dump, JFR và core dump.
- Đặt retention phù hợp và xóa artifact theo chính sách.

Heap dump và core dump có thể chứa nhiều dữ liệu nhạy cảm hơn log thông thường. Bật tính năng dump cần có kiểm soát quyền, nơi lưu, mã hóa, retention và quy trình truy cập điều tra.

## 9. Giới hạn của việc xóa dấu vết trước checkpoint

Một số ứng dụng cố xóa secret trước checkpoint bằng cách:

- Gán field chứa secret thành null.
- Ghi đè char[] hoặc byte[].
- Gọi destroy trên credential object.
- Đóng client và pool.
- Xóa cache hoặc session.

Những bước này hữu ích nhưng không tạo ra bảo đảm rằng ảnh checkpoint không còn dấu vết bí mật.

### Vì sao không thể bảo đảm xóa sạch?

**Object immutable:** String không thể ghi đè trực tiếp. Nếu thư viện đã tạo String, ứng dụng không có API chuẩn để sửa nội dung.

**Bản sao ngoài tầm kiểm soát:** Driver, framework, provider hoặc native code có thể đã copy secret sang cấu trúc khác.

**Garbage collection:** GC quản lý vòng đời object nhưng không cam kết zeroize ngay khi object unreachable. Compaction có thể di chuyển dữ liệu và để lại bản sao cũ trong vùng nhớ.

**JIT và runtime:** Runtime có thể giữ giá trị tạm hoặc tạo representation nội bộ mà ứng dụng không thể quan sát đầy đủ.

**Native/direct memory:** Dữ liệu ngoài heap có lifecycle riêng và có thể không được xóa bằng thao tác trên Java object.

**Artifact đã tạo:** Nếu secret đã được ghi vào checkpoint, heap dump, log hoặc file tạm, việc xóa field trong tiến trình sau đó không sửa được artifact đã tạo.

### Xóa tham chiếu không phải xóa dữ liệu

~~~java
credential = null;
~~~

Lệnh trên chỉ loại bỏ một tham chiếu. Nó không:

- Ghi đè bytes của object.
- Xóa các tham chiếu khác.
- Buộc GC chạy ngay.
- Xóa bản sao native hoặc direct buffer.
- Xóa secret khỏi checkpoint đã được tạo.

Không dùng `System.gc()` như một cơ chế xóa secret. GC có thể không chạy ngay, không cam kết ghi đè vùng nhớ và có thể gây pause. Đây không phải API zeroization.

### Xóa sau checkpoint cũng không sửa được ảnh

Nếu ứng dụng tạo checkpoint khi secret còn trong heap rồi mới xóa biến ở lần chạy tiếp tục, ảnh checkpoint đã lưu vẫn có thể chứa secret. Phải chuẩn bị trước khi gọi checkpoint và xác minh artifact được tạo theo quy trình phù hợp.

Không mở ảnh checkpoint như một file bình thường để tìm chuỗi password rồi sửa bytes. Việc chỉnh sửa nội dung ảnh có thể làm hỏng cấu trúc hoặc tính toàn vẹn của checkpoint và không phải phương pháp xóa secret an toàn.

## 10. Cách giảm lượng secret có thể đi vào heap image

Zeroization không thể bảo đảm tuyệt đối, nên ưu tiên giảm secret có mặt tại thời điểm checkpoint.

### Nạp muộn

Chỉ lấy secret ngay trước khi client cần sử dụng. Không nạp tất cả credential khi ứng dụng khởi động nếu một số chỉ dùng cho tác vụ hiếm hoặc chỉ dùng trong một request.

### Dùng credential ngắn hạn

Ưu tiên token có TTL ngắn, scope nhỏ và có thể revoke. Tránh credential dài hạn có quyền rộng được giữ trong singleton suốt vòng đời JVM.

### Giữ key ở bên ngoài JVM

Dùng KMS/HSM hoặc provider hỗ trợ thao tác bằng key handle để private key không phải xuất ra heap.

### Giảm số bản sao

- Ưu tiên char[]/byte[] nếu API cho phép.
- Tránh chuyển qua String, DTO hoặc concatenation.
- Không copy buffer nếu không cần.
- Không giữ credential trong cache hoặc static field.
- Giải phóng buffer do ứng dụng sở hữu ngay sau khi dùng.
- Đóng client cũ theo API chính thức trước checkpoint.

### Tách secret khỏi cấu hình checkpoint

Không nhúng secret vào:

- JVM command line hoặc system property nếu tránh được.
- File cấu hình được đóng gói cùng image.
- Environment variable của container nếu có cơ chế identity tốt hơn.
- Log, trace, metrics hoặc exception.
- Checkpoint metadata/manifest.

Environment variable không tự động an toàn hơn file; giá trị có thể xuất hiện trong process environment, diagnostic output hoặc heap sau khi ứng dụng đọc nó. Hãy chọn kênh cấp secret dựa trên threat model và khả năng của nền tảng.

## 11. Ví dụ quản lý byte[] với thời gian sống ngắn

Nếu API secret manager trả về byte[] và client có thể sử dụng trực tiếp trong một phạm vi đồng bộ, có thể giới hạn thời gian sống bằng try/finally.

~~~java
import java.util.Arrays;

public final class SecretUse {

    @FunctionalInterface
    public interface SecretOperation<T> {
        T execute(byte[] secret) throws Exception;
    }

    private SecretUse() {
    }

    public static <T> T withSecret(
            SecretLoader loader,
            SecretOperation<T> operation) throws Exception {
        byte[] secret = loader.load();
        try {
            return operation.execute(secret);
        } finally {
            Arrays.fill(secret, (byte) 0);
        }
    }

    public interface SecretLoader {
        byte[] load() throws Exception;
    }
}
~~~

Đoạn mã giúp ghi đè buffer mà loader trả về sau khi operation hoàn tất. Điều kiện quan trọng là loader trả quyền sở hữu buffer cho caller và operation không giữ lại tham chiếu hoặc bản sao lâu dài. Nếu thư viện client sao chép secret, bản sao đó phải được quản lý theo API của thư viện.

Không gọi async operation rồi ghi đè buffer ngay khi method trả về nếu tác vụ nền còn sử dụng mảng. Với xử lý bất đồng bộ, cần một lifecycle rõ ràng để biết khi nào mọi consumer đã hoàn tất.

### API nhận String

Nếu một thư viện chỉ nhận String, hãy hiểu rằng tạo String sẽ tạo một bản sao bất biến mà ứng dụng không thể zeroize trực tiếp. Không tạo thêm String chỉ để format hoặc log credential. Nếu đây là thành phần quan trọng, xem xét API khác hỗ trợ mutable buffer hoặc credential provider.

## 12. Xử lý lỗi khi secret manager chưa sẵn sàng

Sau restore, secret manager hoặc identity endpoint có thể chưa sẵn sàng. Ứng dụng phải giữ readiness false và retry theo ngân sách thời gian có giới hạn.

Phân loại lỗi:

| Lỗi | Cách xử lý |
|---|---|
| Identity endpoint tạm thời không truy cập được | Retry có backoff và jitter |
| Secret manager timeout | Retry có deadline, ghi mã lỗi không chứa secret |
| Workload identity bị từ chối | Không mở readiness; báo lỗi xác thực |
| Secret đã rotate | Lấy version hiện hành và tạo client mới |
| Secret bị revoke | Dừng dùng credential cũ, yêu cầu cấp lại |
| Scope không đủ | Fail rõ ràng và cập nhật policy |
| KMS/HSM không sẵn sàng | Giữ chức năng phụ thuộc key ở trạng thái chưa ready |

Không retry vô hạn trong callback nếu điều đó khiến restore treo không có kết quả. Có thể chờ có giới hạn trong `afterRestore()` hoặc khởi động recovery worker và giữ readiness false. Chiến lược phải phù hợp với cách orchestrator xử lý instance chưa ready.

Không log request đầy đủ hoặc token để chẩn đoán lỗi xác thực. Dùng correlation ID, issuer, audience, secret version ID và mã lỗi đã được phép ghi.

## 13. Ví dụ Resource nạp lại secret sau restore

Ví dụ dưới đây minh họa một resource sở hữu một buffer bí mật dạng byte[]. Mọi thao tác sử dụng secret đi qua method đồng bộ để resource có thể chờ thao tác đang dùng hoàn tất trước khi ghi đè buffer.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.util.Arrays;

public final class SecretMaterialResource implements Resource {

    @FunctionalInterface
    public interface SecretSource {
        byte[] loadCurrentSecret() throws Exception;
    }

    @FunctionalInterface
    public interface SecretOperation<T> {
        T apply(byte[] secret) throws Exception;
    }

    private final SecretSource source;
    private byte[] secret;
    private boolean ready;

    public SecretMaterialResource(SecretSource source) throws Exception {
        this.source = source;
        this.secret = source.loadCurrentSecret();
        if (secret == null || secret.length == 0) {
            throw new IllegalStateException("Secret source returned no secret");
        }
        this.ready = true;
        Core.getGlobalContext().register(this);
    }

    public synchronized <T> T withSecret(SecretOperation<T> operation)
            throws Exception {
        if (!ready || secret == null) {
            throw new IllegalStateException("Secret is not ready");
        }
        return operation.apply(secret);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        ready = false;
        clearSecret();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        byte[] candidate = source.loadCurrentSecret();
        if (candidate == null || candidate.length == 0) {
            if (candidate != null) {
                Arrays.fill(candidate, (byte) 0);
            }
            throw new IllegalStateException("Secret source returned no secret");
        }
        secret = candidate;
        ready = true;
    }

    public synchronized void resumeAfterAbortedCheckpoint()
            throws Exception {
        if (secret == null) {
            secret = source.loadCurrentSecret();
        }
        ready = secret != null && secret.length > 0;
        if (!ready) {
            if (secret != null) {
                Arrays.fill(secret, (byte) 0);
                secret = null;
            }
            throw new IllegalStateException("Cannot reload secret");
        }
    }

    private void clearSecret() {
        if (secret != null) {
            Arrays.fill(secret, (byte) 0);
            secret = null;
        }
    }
}
~~~

Mẫu này thể hiện một số điểm:

- JVM mới lấy secret trong constructor; đường khởi động mới không phụ thuộc callback restore.
- Trước checkpoint, resource ngừng cho phép sử dụng secret và ghi đè buffer mà nó sở hữu.
- Sau restore, resource lấy secret hiện hành từ nguồn tin cậy.
- Nếu nguồn không cấp được secret, callback báo lỗi và ứng dụng không được mở readiness.
- Có method riêng để minh họa rollback nếu checkpoint bị hủy và ứng dụng tiếp tục chạy.

Đây vẫn chỉ là zeroization best effort. SecretOperation nhận tham chiếu đến mảng nội bộ; hợp đồng của caller phải quy định không giữ lại tham chiếu, không sửa mảng và không tạo bản sao không cần thiết. Trong hệ thống thực tế, cần đóng admission và drain request trước khi callback chạy. Việc đồng bộ trên resource không thay thế drain toàn bộ ứng dụng hoặc quản lý transaction.

Nếu API thư viện buộc phải tạo String hoặc giữ bản sao credential, resource không thể xóa các bản sao đó. Cần dùng API credential provider/secret handle được thư viện hỗ trợ, hoặc đóng và tạo lại client để giảm thời gian giữ credential cũ.

## 14. Bảo vệ checkpoint artifact như dữ liệu bí mật

Ngay cả khi ứng dụng làm mới secret sau restore, ảnh checkpoint cũ vẫn có thể chứa credential đã được nạp trước đó. Vì vậy, phải bảo vệ artifact theo mức nhạy cảm của dữ liệu trong heap.

### Quyền truy cập và lưu trữ

- Giới hạn quyền đọc ảnh cho service và operator thực sự cần thiết.
- Không đặt ảnh trong thư mục public, artifact repository công khai hoặc bucket mở.
- Mã hóa khi lưu và khi truyền qua mạng.
- Bảo vệ checksum, manifest và bản sao lưu; chữ ký xác minh nguồn gốc không thay thế mã hóa.
- Dùng retention ngắn phù hợp và xóa artifact theo quy trình được quản lý.
- Hạn chế quyền truy cập vào heap dump, core dump và JFR recording.
- Không đưa checkpoint vào Git, log archive hoặc Docker build context.

### Quản lý khóa mã hóa

Nếu mã hóa ảnh, khóa giải mã phải được quản lý tách biệt khỏi artifact. Không đặt key giải mã trong cùng archive hoặc manifest. Ưu tiên KMS/HSM hoặc hệ thống key management có audit, rotation và access policy.

Mã hóa at rest bảo vệ dữ liệu khi lưu trên storage, nhưng không bảo vệ ảnh khỏi một tiến trình hoặc operator đã có quyền giải mã. Kiểm soát IAM, quyền truy cập artifact và audit vẫn cần thiết.

### Secret cũ trong ảnh

Nếu phát hiện checkpoint chứa secret đã bị lộ hoặc không còn được phép lưu:

1. Thu hồi hoặc rotate credential ở issuer/secret manager.
2. Xác định mọi bản sao ảnh, archive, cache và backup.
3. Ngăn các bản ảnh cũ tiếp tục được restore.
4. Xóa hoặc cô lập artifact theo quy trình retention và incident response.
5. Tạo checkpoint mới sau khi ứng dụng đã chuyển sang credential hiện hành.
6. Kiểm tra log, heap dump và diagnostic artifact có chứa cùng secret hay không.

Không chỉ xóa file checkpoint chính nếu archive hoặc bản sao lưu vẫn tồn tại.

## 15. Kiểm thử secret lifecycle quanh checkpoint

Kiểm thử cần xác minh cả hai điều: secret mới thực sự được sử dụng sau restore và secret cũ không còn được dùng bởi các client hoạt động.

### Kịch bản cơ bản

1. Khởi động ứng dụng mới và xác nhận workload identity lấy được secret.
2. Xác nhận database, HTTP hoặc broker client được tạo bằng credential hiện hành.
3. Ghi nhận secret version ID hoặc key ID không nhạy cảm; không ghi giá trị secret.
4. Đóng admission và drain các request đang dùng credential.
5. Chạy callback chuẩn bị checkpoint và xác nhận buffer do ứng dụng sở hữu được xử lý.
6. Tạo checkpoint.
7. Rotate secret ở secret manager hoặc làm hết hạn credential trong môi trường thử nghiệm.
8. Restore ảnh.
9. Xác nhận callback lấy credential mới và tạo lại client.
10. Xác nhận health check và request thực tế thành công.
11. Xác nhận readiness chỉ mở sau khi mọi dependency bắt buộc sẵn sàng.
12. Xác nhận không có log hoặc telemetry chứa secret.

### Các tình huống cần thử

| Tình huống | Kết quả mong đợi |
|---|---|
| Secret manager sẵn sàng | Secret mới được lấy và client hoạt động |
| Secret manager tạm thời không truy cập được | Retry có giới hạn hoặc recovery worker; readiness false |
| Credential bị rotate trước restore | Client mới dùng version hiện hành |
| Credential cũ bị revoke | Client cũ không được dùng lại |
| Workload identity hết hạn | Identity được làm mới hoặc restore không mở readiness |
| Client tạo thất bại sau khi lấy secret | Candidate được cleanup, readiness false |
| Checkpoint bị hủy | Rollback lấy lại secret và client trước khi mở admission |
| Thư viện giữ bản sao secret | Được ghi nhận trong threat model; dùng API thay thế nếu có |
| Secret nằm trong String | Không tuyên bố zeroization; giảm phạm vi và thời gian tồn tại |
| Nhiều instance restore đồng thời | Secret manager không bị quá tải; retry có jitter |
| Heap dump/diagnostic được tạo | Artifact được bảo vệ và không phát tán ngoài quyền cho phép |

### Kiểm tra giá trị mà không in secret

Test nên kiểm tra:

- Secret version ID hoặc credential generation.
- Client kết nối được với dependency.
- Credential cũ bị từ chối sau rotation nếu policy yêu cầu.
- Buffer do ứng dụng sở hữu đã được ghi đè trong test harness.
- Không có secret trong log đã thu thập.

Không in secret để “xác nhận” test. Nếu cần kiểm tra buffer đã ghi đè, dùng assertion nội bộ trên bản sao test không nhạy cảm hoặc kiểm tra buffer do fixture tạo ra; không tạo log chứa giá trị thật.

## 16. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Gán String thành null là xóa password. | Chỉ bỏ một tham chiếu; String và các bản sao có thể còn trong heap. |
| Gọi System.gc() sẽ xóa secret. | GC không cam kết zeroization hoặc thời điểm thu hồi. |
| Arrays.fill() xóa mọi bản sao. | Chỉ ghi đè mảng cụ thể mà ứng dụng sở hữu. |
| Secret đã được xóa sau checkpoint nên ảnh an toàn. | Ảnh đã tạo có thể vẫn chứa secret cũ. |
| Restore sẽ chạy lại constructor. | Object graph được khôi phục; dùng afterRestore để làm mới trạng thái cần thiết. |
| Secret manager client còn trong heap là có thể dùng. | Socket, identity token và cache có thể đã hết hiệu lực. |
| Token còn hạn theo timestamp là chắc chắn hợp lệ. | Issuer có thể revoke; cần xác minh hoặc lấy token mới. |
| Environment variable luôn an toàn hơn secret file. | Cả hai có thể bị đọc hoặc được sao chép vào heap/diagnostic data. |
| HSM/KMS loại bỏ mọi rủi ro secret. | Key handle giảm việc xuất key material, nhưng identity, policy và thao tác ký vẫn cần bảo vệ. |
| Mã hóa artifact là đủ. | Cần quản lý khóa, IAM, audit, retention và bảo vệ bản giải mã. |

## 17. Checklist triển khai

### Trước checkpoint

- [ ] Đóng admission và drain mọi request/job đang dùng credential.
- [ ] Đóng client, pool hoặc session theo lifecycle được thư viện hỗ trợ.
- [ ] Xóa cache secret và ghi đè buffer do ứng dụng sở hữu khi phù hợp.
- [ ] Không giả định String, native memory hoặc bản sao thư viện đã được zeroize.
- [ ] Không để token, password hoặc private key trong log/exception.
- [ ] Xác định rollback nếu checkpoint bị hủy sau khi secret đã được giải phóng.

### Sau restore

- [ ] Làm mới workload identity hoặc bootstrap credential.
- [ ] Kết nối secret manager/KMS bằng identity hiện hành.
- [ ] Lấy secret/token hiện hành với scope và TTL phù hợp.
- [ ] Tạo lại client/pool/TLS context phụ thuộc secret.
- [ ] Kiểm tra thao tác thực tế và quyền truy cập.
- [ ] Giữ readiness false khi identity hoặc secret chưa sẵn sàng.
- [ ] Không công bố client chưa được xác minh.

### Bảo vệ artifact và kiểm thử

- [ ] Xem checkpoint như dữ liệu nhạy cảm có thể chứa secret.
- [ ] Mã hóa ảnh khi lưu/truyền và quản lý khóa tách biệt.
- [ ] Hạn chế quyền đọc, backup, heap dump và diagnostic artifact.
- [ ] Có quy trình rotate/revoke khi ảnh cũ chứa credential không còn hợp lệ.
- [ ] Đã kiểm thử restore sau khi secret được rotate hoặc revoke.
- [ ] Đã kiểm tra log/trace/metric không làm lộ secret.
- [ ] Ghi rõ giới hạn zeroization của từng thư viện/provider.

Nạp hoặc làm mới bí mật sau restore giúp giảm nguy cơ credential cũ bị đóng gói và tiếp tục được sử dụng từ heap image. Tuy nhiên, Java không cung cấp cách portable để xóa chắc chắn mọi bản sao secret khỏi heap, native memory và artifact đã tạo. Hãy giảm lượng secret có mặt tại thời điểm checkpoint, dùng workload identity và credential ngắn hạn, làm mới client theo thứ tự lifecycle, ghi đè buffer do ứng dụng sở hữu như một biện pháp best effort, và bảo vệ checkpoint artifact như dữ liệu nhạy cảm.
