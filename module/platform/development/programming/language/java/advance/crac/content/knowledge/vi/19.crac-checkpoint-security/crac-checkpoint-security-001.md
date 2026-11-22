# Nhận diện bí mật và dữ liệu nhạy cảm có thể tồn tại trong ảnh bộ nhớ

CRaC (Coordinated Restore at Checkpoint) tạo ảnh trạng thái của một tiến trình Java để có thể khôi phục tiến trình đó về sau. Ảnh checkpoint có thể chứa heap, stack, trạng thái thread và những vùng bộ nhớ khác mà cơ chế checkpoint của runtime hỗ trợ. Nếu tiến trình đang giữ mật khẩu, access token, khóa mã hóa, dữ liệu cá nhân hoặc nội dung request trong bộ nhớ, những dữ liệu đó có thể xuất hiện trong ảnh.

Vì vậy, checkpoint image cần được xem là một artifact nhạy cảm tương đương với bộ nhớ của tiến trình đang chạy. Việc bảo vệ ứng dụng ở runtime là chưa đủ; cần kiểm soát cả lúc tạo ảnh, lưu trữ, sao chép, truyền tải, restore, backup và xóa ảnh.

## 1. Vì sao checkpoint image có thể chứa bí mật?

Java application thường nạp dữ liệu nhạy cảm vào bộ nhớ để thực hiện công việc. Dữ liệu có thể tồn tại trong nhiều lớp:

- Heap: object, String, mảng byte, cấu hình, cache và session.
- Stack của thread: biến cục bộ, tham số method và tham chiếu đang được sử dụng.
- Buffer: ByteBuffer, direct buffer, buffer của thư viện mạng hoặc JDBC.
- Native memory: dữ liệu do JNI/JNA, TLS provider, driver hoặc thư viện native cấp phát.
- ThreadLocal và static field: token, user context, credential hoặc dữ liệu được cache lâu dài.
- Các vùng memory-mapped: nội dung file được ánh xạ vào address space.
- Trạng thái của thư viện: TLS session, authentication context, connection pool hoặc credential cache.

Nếu checkpoint được tạo khi những dữ liệu này còn nằm trong vùng bộ nhớ được snapshot, ảnh có thể giữ lại bản sao của chúng. Việc một object không còn được ứng dụng sử dụng không đồng nghĩa byte của nó đã bị xóa khỏi bộ nhớ. Garbage Collector có thể thu hồi object về mặt logic, nhưng không bảo đảm ghi đè vùng nhớ cũ ngay lập tức.

Một checkpoint image vì thế có thể chứa nhiều hơn những field mà ứng dụng chủ động xem là dữ liệu cần lưu. Những bản sao tạm thời, dữ liệu trong buffer và trạng thái nội bộ của thư viện cũng cần được xem xét.

### Ví dụ một token trong heap

~~~java
public final class ApiClient {
    private final String accessToken;

    public ApiClient(String accessToken) {
        this.accessToken = accessToken;
    }

    public void callService() {
        // Header Authorization được tạo từ accessToken.
    }
}
~~~

Nếu ApiClient còn sống tại thời điểm checkpoint, accessToken vẫn là một phần của trạng thái object. Ảnh bộ nhớ có thể chứa chuỗi token và các bản sao liên quan do quá trình xử lý request tạo ra.

Nếu token có quyền truy cập vào hệ thống bên ngoài, người có thể đọc và restore image có thể có khả năng sử dụng token đó, tùy thời hạn, scope và chính sách xác thực.

## 2. Những loại dữ liệu nhạy cảm cần nhận diện

Không chỉ password mới được xem là bí mật. Trước khi tạo checkpoint, cần lập danh sách dữ liệu mà nếu bị lộ có thể gây ảnh hưởng đến người dùng, hệ thống hoặc tổ chức.

| Nhóm dữ liệu | Ví dụ | Rủi ro khi lộ |
|---|---|---|
| Mật khẩu và credential | Database password, API key, SMTP password | Truy cập trái phép vào dịch vụ |
| Token | OAuth access/refresh token, JWT, session cookie | Mạo danh người dùng hoặc workload |
| Khóa mật mã | Private key, symmetric key, data encryption key | Giải mã dữ liệu hoặc giả mạo chữ ký |
| Thông tin TLS | Key material, session secret, client certificate private key | Giả mạo hoặc giải mã kết nối tùy ngữ cảnh |
| Dữ liệu cá nhân | Tên, email, số điện thoại, địa chỉ, định danh | Vi phạm quyền riêng tư |
| Dữ liệu xác thực | Session, MFA state, reset token | Chiếm phiên hoặc vượt qua bước xác thực |
| Dữ liệu nghiệp vụ | Hồ sơ khách hàng, giao dịch, nội dung tài liệu | Lộ thông tin kinh doanh hoặc dữ liệu được bảo vệ |
| Nội dung request | Request body, header, query parameter | Lộ thông tin gửi lên API |
| Dữ liệu cache | User profile, authorization decision, query result | Lộ dữ liệu giữa các tenant hoặc người dùng |
| Dữ liệu debug | Stack trace, diagnostic snapshot, request dump | Tiết lộ cấu hình, dữ liệu hoặc credential |

Cần đánh giá cả dữ liệu được mã hóa và dữ liệu đã giải mã. Ciphertext có thể không nhạy cảm như plaintext nếu khóa được bảo vệ độc lập, nhưng khóa giải mã nằm trong cùng ảnh có thể làm mất lợi ích của việc mã hóa.

### Bí mật tĩnh và bí mật có thời hạn

Có thể phân biệt:

- Bí mật dài hạn: private key, master key, database credential hoặc API key ít thay đổi.
- Bí mật ngắn hạn: access token, session token, signed URL hoặc credential có TTL ngắn.
- Bí mật theo phiên: TLS session state, authentication context hoặc token gắn với một request.
- Dữ liệu nhạy cảm tạm thời: password vừa nhận, request body, dữ liệu đã giải mã hoặc nội dung file đang xử lý.

Bí mật ngắn hạn vẫn có thể nguy hiểm nếu checkpoint image được lưu lâu hơn thời hạn của token, hoặc nếu token có thể refresh bằng một refresh token khác cũng nằm trong ảnh.

## 3. Nguồn bí mật có thể đi vào bộ nhớ Java

Một cuộc kiểm kê hiệu quả cần tìm nguồn dữ liệu, cách nạp và nơi lưu giữ chúng.

### Environment variable

Ứng dụng thường đọc credential từ environment:

~~~java
String password = System.getenv("DB_PASSWORD");
~~~

Environment variable giúp tránh hard-code secret trong source code, nhưng sau khi đọc, giá trị có thể được giữ trong String hoặc object cấu hình. Môi trường của tiến trình cũng có thể được lưu trong trạng thái process tùy cơ chế snapshot.

Không nên kết luận rằng dùng environment variable đồng nghĩa với secret không xuất hiện trong checkpoint image. Hãy kiểm tra cách runtime và môi trường triển khai xử lý process environment, đồng thời giảm quyền truy cập vào image.

### System properties và command-line arguments

Credential có thể được truyền qua:

~~~bash
java -Dapi.token=secret-value -jar app.jar
~~~

Hoặc được truyền qua tham số command line. Các giá trị này có thể xuất hiện trong process metadata, log khởi động, diagnostic output hoặc trạng thái được snapshot.

Không truyền secret trực tiếp trong command line nếu có lựa chọn an toàn hơn. Ưu tiên secret manager, file mount có quyền hạn chế hoặc workload identity, tùy nền tảng.

### File cấu hình và binding object

Spring Boot hoặc framework khác có thể bind giá trị cấu hình vào bean:

~~~java
@ConfigurationProperties(prefix = "remote.api")
public class RemoteApiProperties {
    private String token;

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }
}
~~~

Sau khi bind, token nằm trong object sống cùng ApplicationContext. Nếu bean được giữ trong heap khi checkpoint, giá trị có thể được lưu trong ảnh.

Việc cấu hình file bên ngoài hoặc mount secret không làm giá trị đã nạp biến mất khỏi heap. Cần thiết kế vòng đời của object chứa secret.

### Request, session và cache

Một request có thể đưa dữ liệu nhạy cảm vào:

- Controller parameter và DTO.
- Authentication principal.
- SecurityContext.
- HTTP header và body buffer.
- Session object.
- Cache hoặc retry queue.
- Exception message và diagnostic context.

Một request đã hoàn tất vẫn có thể để lại dữ liệu trong cache, ThreadLocal hoặc object được tham chiếu từ singleton. Nên xóa context theo đúng vòng đời request và tránh giữ dữ liệu cá nhân lâu hơn cần thiết.

### JDBC, HTTP và TLS client

Connection pool, HTTP client và TLS stack có thể giữ credential, token, cookie, session state hoặc buffer. Đóng client trước checkpoint giúp xử lý socket và thread, nhưng không tự bảo đảm mọi bản sao secret trong heap đã được xóa.

Nếu ứng dụng cần kết nối lại sau restore, nên tạo client mới từ credential được cấp lại hoặc xác minh lại sau restore.

### Native library và direct buffer

Thư viện native có thể giữ key material hoặc plaintext trong vùng nhớ ngoài Java heap. DirectByteBuffer cũng có thể chứa dữ liệu nhạy cảm.

Không chỉ kiểm kê field Java. Hãy xác định các thư viện crypto, TLS, compression, database driver, JNI/JNA và SDK có thể giữ dữ liệu trong native memory.

## 4. String, byte[] và giới hạn của việc xóa bí mật

Trong Java, String là immutable. Khi một password được tạo thành String, ứng dụng không thể ghi đè nội dung của chính String đó qua API công khai.

~~~java
String password = obtainPassword();
authenticate(password);
password = null;
~~~

Gán null chỉ bỏ tham chiếu từ biến password. Nó không xóa byte của String khỏi heap ngay lập tức. Garbage Collector có thể thu hồi object sau này, nhưng không có bảo đảm về thời điểm hoặc việc ghi đè vùng nhớ.

Ngoài ra, một secret có thể đã được sao chép khi:

- Chuyển từ byte[] sang String.
- Nối chuỗi để tạo header hoặc URL.
- Ghi vào log hoặc exception.
- Bind vào nhiều object cấu hình.
- Đưa vào buffer hoặc thư viện native.
- Chuyển qua API yêu cầu String.

### Dùng mảng mutable khi API hỗ trợ

Nếu API cho phép, có thể giữ secret trong char[] hoặc byte[] và ghi đè sau khi sử dụng:

~~~java
char[] password = secretProvider.readPassword();

try {
    authenticate(password);
} finally {
    Arrays.fill(password, '\0');
}
~~~

Với byte[]:

~~~java
byte[] keyBytes = secretProvider.readKey();

try {
    useKey(keyBytes);
} finally {
    Arrays.fill(keyBytes, (byte) 0);
}
~~~

Đây là biện pháp giảm thời gian tồn tại của dữ liệu, không phải bảo đảm xóa tuyệt đối. JVM, JIT compiler, thư viện và API được gọi có thể tạo bản sao khác. Nếu dữ liệu đã được chuyển thành String, việc xóa mảng gốc không xóa bản sao String.

Không gọi clear() trên ByteBuffer rồi cho rằng dữ liệu đã bị xóa. clear() chỉ đặt lại vị trí và giới hạn của buffer; nội dung byte vẫn có thể còn. Muốn ghi đè buffer có thể dùng vòng lặp put hoặc thao tác tương đương, nhưng direct buffer và bản sao native vẫn cần được đánh giá riêng.

### Tránh biến secret thành chuỗi ghép

Không nên tạo chuỗi chứa credential để tiện log hoặc cấu hình:

~~~java
String authorization = "Bearer " + token;
logger.debug("Authorization: {}", authorization);
~~~

Header Authorization nên được truyền trực tiếp đến HTTP client và phải được loại khỏi log. Không đưa token vào URL query parameter vì URL thường bị ghi trong access log, proxy log hoặc tracing.

### Không tự triển khai zeroization mật mã

Nếu cần bảo vệ key material, ưu tiên API crypto hoặc provider có cơ chế quản lý key phù hợp. Không viết một tiện ích tự chế rồi khẳng định nó bảo đảm xóa mọi bản sao trong JVM.

Đối với khóa không thể export, HSM hoặc KMS có thể giữ khóa bên ngoài process. Ứng dụng chỉ giữ handle hoặc quyền gọi thao tác ký/giải mã. Đây thường là cách giảm lượng key material nhạy cảm trong checkpoint image.

## 5. Mức độ nhạy cảm của checkpoint image

Hãy giả định một người có quyền đọc ảnh bộ nhớ có thể tìm thấy một phần dữ liệu mà tiến trình đã truy cập gần thời điểm checkpoint. Mức độ thực tế phụ thuộc runtime, vùng nhớ được snapshot, cơ chế bảo vệ và cách secret được quản lý.

Checkpoint image nên được phân loại và bảo vệ ít nhất theo mức nhạy cảm cao nhất của dữ liệu có thể tồn tại trong process memory.

Ví dụ:

~~~text
Ứng dụng đang chạy
   |
   +-- Database credential
   +-- OAuth token
   +-- TLS key material
   +-- Customer data
   +-- Request/session state
   |
   v
Checkpoint image
   |
   +-- Có thể chứa các vùng memory ở trên
   |
   v
Lưu trữ / sao chép / truyền tải / restore
~~~

Nếu image được coi là artifact triển khai thông thường, nó có thể bị sao chép sang registry, object storage, backup hoặc môi trường CI/CD với quyền rộng hơn mức cần thiết. Điều này tạo thêm đường rò rỉ.

### Các vị trí cần bảo vệ

Kiểm kê toàn bộ vòng đời artifact:

- Thư mục tạm nơi runtime tạo checkpoint.
- Thư mục checkpoint chính.
- Bản sao được dùng cho restore.
- Backup và snapshot của volume chứa checkpoint.
- Object storage hoặc artifact registry.
- Đường truyền giữa node tạo và node restore.
- Cache của hệ thống triển khai.
- Log, diagnostic bundle và file hỗ trợ điều tra.
- Bản sao trong môi trường thử nghiệm hoặc staging.

Không chỉ bảo vệ thư mục gốc. Một bản sao được tải xuống máy cá nhân hoặc đính kèm vào ticket vẫn là một bản sao của dữ liệu nhạy cảm.

## 6. Mã hóa và quản lý khóa cho checkpoint image

Nếu checkpoint image được lưu trên disk hoặc truyền qua network, cần mã hóa theo chính sách bảo mật của hệ thống.

Các nguyên tắc quan trọng:

1. Mã hóa dữ liệu khi lưu trữ bằng cơ chế được nền tảng hỗ trợ hoặc một lớp mã hóa artifact phù hợp.
2. Dùng TLS hoặc kênh truyền an toàn khi chuyển image.
3. Giới hạn quyền đọc, ghi, restore và xóa theo role.
4. Tách quyền quản lý image khỏi quyền sử dụng khóa giải mã.
5. Lưu khóa mã hóa trong KMS/HSM hoặc secret manager độc lập với image.
6. Theo dõi audit log cho việc tải xuống, sao chép và restore.
7. Có chính sách hết hạn và xóa an toàn cho image cùng các bản backup.

Không giả định mọi bản phân phối CRaC đều tự mã hóa checkpoint image. Phải xác minh tính năng thực tế của runtime, filesystem và storage provider. Nếu nền tảng không cung cấp mã hóa phù hợp, cần thêm lớp bảo vệ artifact trước khi lưu hoặc phân phối.

### Không đặt khóa giải mã trong chính image

Nếu image được mã hóa nhưng khóa giải mã cũng nằm trong heap hoặc file được đóng gói cùng image, người có image có thể lấy được cả hai thành phần.

Khóa giải mã cần được cung cấp từ một nguồn độc lập sau khi workload được xác thực. Có thể dùng KMS, HSM, workload identity hoặc cơ chế key release theo policy.

### Kiểm soát quyền truy cập

Áp dụng least privilege:

- Chỉ service account cần thiết mới được đọc image.
- Chỉ node hoặc workload được phép mới được restore.
- Developer không mặc định có quyền tải image production.
- Không dùng bucket hoặc registry public.
- Tách quyền tạo image, phê duyệt, phân phối và xóa.
- Ghi nhận ai đã truy cập image và vào thời điểm nào.

Nếu image chứa credential production, không restore nó vào môi trường kém tin cậy hơn chỉ để debug. Việc restore có thể đưa các secret đó vào process memory của môi trường mới.

## 7. Giảm dữ liệu nhạy cảm trước checkpoint

Cách giảm rủi ro tốt nhất là không để dữ liệu không cần thiết tồn tại trong bộ nhớ tại thời điểm tạo ảnh.

Một quy trình chuẩn bị có thể gồm:

1. Ngừng nhận request và công việc mới.
2. Drain request đang chạy và hoàn tất transaction.
3. Xóa request context, security context và ThreadLocal không cần thiết.
4. Loại bỏ dữ liệu cá nhân khỏi cache nếu cache có thể tái tạo.
5. Dừng retry queue hoặc buffer có chứa payload nhạy cảm.
6. Đóng client giữ session hoặc token cũ.
7. Ghi đè mảng byte/char có thể xóa an toàn.
8. Đưa secret cần dùng sau restore ra khỏi heap và chuẩn bị cơ chế cấp lại.
9. Kiểm tra log, diagnostic buffer và các object tạm.
10. Chỉ tạo checkpoint khi ứng dụng ở trạng thái đã chuẩn bị.

Không xóa dữ liệu nghiệp vụ đang cần để khôi phục tính đúng đắn. Phải phân biệt state cần thiết để tiếp tục công việc với credential hoặc payload tạm thời có thể nạp lại.

### Không checkpoint giữa một thao tác nhạy cảm

Ví dụ, nếu ứng dụng đang xử lý một yêu cầu đổi mật khẩu, reset token hoặc thanh toán, heap có thể chứa cả dữ liệu đầu vào và trạng thái transaction. Nên hoàn tất hoặc hủy thao tác theo quy tắc nghiệp vụ trước checkpoint.

Đối với request không thể hoàn tất nhanh, có thể chuyển nó sang hàng đợi bền vững hoặc lưu một trạng thái công việc tối thiểu, không lưu raw credential hoặc payload nhạy cảm nếu không cần thiết.

### Làm sạch ThreadLocal

ThreadLocal có thể giữ user context hoặc credential trên thread pool lâu hơn thời gian request:

~~~java
try {
    currentUser.set(userContext);
    processRequest();
} finally {
    currentUser.remove();
}
~~~

Luôn remove() trong finally. Nếu không, thread được tái sử dụng có thể giữ dữ liệu của request trước, và dữ liệu đó có thể xuất hiện trong checkpoint image.

## 8. Tái lấy secret sau restore

Đối với credential cần thiết để tiếp tục kết nối, thường nên lấy lại sau restore thay vì dựa vào giá trị cũ được lưu trong heap.

Một luồng khái quát:

~~~text
Restore process
      |
      v
Giữ request gate đóng
      |
      v
Xác thực workload identity
      |
      v
Lấy secret/token mới từ provider
      |
      v
Tạo lại client / connection pool
      |
      v
Kiểm tra dependency và quyền
      |
      v
Xóa buffer secret tạm
      |
      v
Mở worker và request listener
~~~

Cách này giúp xử lý credential đã hết hạn hoặc bị rotate trong thời gian image nằm chờ restore.

### Dùng SecretProvider abstraction

Có thể tách việc lấy secret khỏi service sử dụng nó:

~~~java
public interface SecretProvider {
    char[] readSecret(String secretName) throws Exception;
}
~~~

Service nhận provider và yêu cầu secret khi cần:

~~~java
public final class RemoteClientFactory {
    private final SecretProvider secrets;

    public RemoteClientFactory(SecretProvider secrets) {
        this.secrets = secrets;
    }

    public RemoteClient create() throws Exception {
        char[] token = secrets.readSecret("remote-api-token");

        try {
            return RemoteClient.connect(token);
        } finally {
            Arrays.fill(token, '\0');
        }
    }
}
~~~

RemoteClient.connect() là API minh họa. Trong thực tế, cần kiểm tra thư viện có sao chép token thành String hoặc giữ token trong object nội bộ hay không. Xóa mảng đầu vào không tự xóa bản sao mà client đã tạo.

### Không cache secret lâu hơn cần thiết

Nếu client bắt buộc giữ token để refresh hoặc xác thực request, xác định rõ vòng đời và khả năng rotate. Có thể dùng provider có khả năng thay credential, wrapper client hoặc factory tạo client mới khi secret thay đổi.

Không để nhiều singleton cùng giữ một bản sao credential chỉ vì việc inject String tiện lợi. Hãy giảm số nơi lưu secret và tránh truyền secret qua các tầng không cần biết nó.

## 9. CRaC Resource cho dữ liệu nhạy cảm

CRaC cung cấp interface Resource với hai callback chính:

- beforeCheckpoint(): chuẩn bị tài nguyên trước khi tạo checkpoint.
- afterRestore(): tạo lại hoặc xác minh tài nguyên sau khi restore.

Một resource quản lý client có thể đóng client cũ và xóa buffer secret tạm trước checkpoint, rồi lấy secret mới và tạo client sau restore.

~~~java
import java.util.Arrays;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ProtectedClientResource implements Resource {
    private final SecretProvider secretProvider;
    private RemoteClient client;
    private char[] temporarySecret;

    public ProtectedClientResource(
            SecretProvider secretProvider) throws Exception {
        this.secretProvider = secretProvider;
        this.client = createClient();
        Core.getGlobalContext().register(this);
    }

    private RemoteClient createClient() throws Exception {
        char[] secret = secretProvider.readSecret("remote-api-token");

        try {
            return RemoteClient.connect(secret);
        } finally {
            Arrays.fill(secret, '\0');
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.close();
            client = null;
        }

        clearTemporarySecret();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = createClient();
    }

    public synchronized void recoverAfterAbortedCheckpoint()
            throws Exception {
        if (client == null) {
            client = createClient();
        }
    }

    private void clearTemporarySecret() {
        if (temporarySecret != null) {
            Arrays.fill(temporarySecret, '\0');
            temporarySecret = null;
        }
    }
}
~~~

ProtectedClientResource là ví dụ khái niệm. RemoteClient, SecretProvider và cách tạo client cần thay bằng implementation thật. Nếu client giữ token nội bộ, cần xác minh API close() có xóa hoặc giải phóng trạng thái nhạy cảm hay không; không mặc định close() đồng nghĩa với zeroization.

Trong ví dụ, credential được đọc trong factory và mảng đầu vào được ghi đè sau khi gọi connect(). Nếu thư viện tạo bản sao String hoặc native buffer, ứng dụng cần đánh giá riêng. Đối với khóa mật mã, ưu tiên provider giữ khóa bên ngoài process nếu có thể.

### Phân biệt restore với checkpoint bị hủy

Nếu checkpoint thành công và tiến trình được restore, afterRestore() chạy để lấy credential mới và tạo client mới.

Nếu checkpoint bị hủy, tiến trình ban đầu tiếp tục. afterRestore() không phải callback rollback. Nếu beforeCheckpoint() đã đóng client, ứng dụng cần tạo lại client trong nhánh phục hồi.

Khi ứng dụng gọi Core.checkpointRestore(), có thể bắt CheckpointException:

~~~java
try {
    Core.checkpointRestore();
    // Tiếp tục trong tiến trình đã restore.
} catch (CheckpointException checkpointFailure) {
    try {
        protectedClient.recoverAfterAbortedCheckpoint();
    } catch (Exception recoveryFailure) {
        checkpointFailure.addSuppressed(recoveryFailure);
        markApplicationNotReady();
    }

    throw checkpointFailure;
} catch (RestoreException restoreFailure) {
    // Đây là lỗi ở tiến trình đã restore.
    markApplicationNotReady();
    throw restoreFailure;
}
~~~

Nếu checkpoint được yêu cầu bằng jcmd từ bên ngoài, luồng gọi API trong ứng dụng không có khối catch này. Do đó, không xóa credential duy nhất hoặc đóng resource theo cách khiến tiến trình gốc không thể phục hồi, trừ khi có một cơ chế recovery độc lập được thiết kế và kiểm thử.

Không có callback afterRestore() nào tự động chạy chỉ vì checkpoint bị hủy. Đây là điều quan trọng khi quyết định có nên xóa secret hoặc đóng client trong beforeCheckpoint() hay không.

## 10. Secret manager, workload identity và KMS

Một thiết kế tốt không cần lưu tất cả credential dài hạn trong image. Thay vào đó, workload có thể xác thực với hệ thống cấp secret sau restore.

Các lựa chọn phổ biến:

- Secret manager: cấp database password, API token hoặc secret theo policy.
- Workload identity: xác thực workload dựa trên service account hoặc danh tính runtime thay vì lưu key tĩnh.
- KMS: thực hiện thao tác mã hóa/giải mã bằng khóa được quản lý bên ngoài.
- HSM: giữ private key trong phần cứng hoặc dịch vụ bảo vệ key.
- Short-lived credential: token có TTL ngắn và scope tối thiểu.
- Certificate rotation: cấp certificate mới khi instance được tạo hoặc khi certificate sắp hết hạn.

### Workload identity

Thay vì đóng gói một access key dài hạn trong image, workload có thể dùng identity do nền tảng cấp. Sau restore, nó xác thực lại và lấy credential ngắn hạn.

Cần bảo đảm identity token hoặc service account credential dùng để bootstrap không bị lộ trong image. Nếu bootstrap credential cũng nằm trong heap, rủi ro chỉ được chuyển từ token chính sang token bootstrap.

### KMS/HSM

Nếu private key không cần xuất khỏi KMS/HSM, ứng dụng chỉ giữ key reference và gọi dịch vụ để ký hoặc giải mã. Checkpoint image khi đó không cần chứa raw private key.

Vẫn cần bảo vệ access token hoặc workload identity cho phép gọi KMS. Giới hạn quyền theo key, operation, workload identity và môi trường.

## 11. Credential có thể hết hạn hoặc bị rotate trong thời gian checkpoint

Một image có thể được lưu nhiều giờ hoặc nhiều ngày. Trong khoảng đó:

- Password database có thể bị rotate.
- OAuth access token có thể hết hạn.
- Refresh token có thể bị thu hồi.
- TLS certificate có thể hết hạn hoặc bị thay thế.
- API key có thể bị disable sau sự cố.
- User session có thể bị logout hoặc revoke.
- Quyền của workload có thể thay đổi.

Nếu restore sử dụng credential cũ, kết nối có thể thất bại hoặc tệ hơn là tiếp tục dùng một credential đã bị thu hồi theo policy chưa được áp dụng đúng.

Nên lưu metadata không nhạy cảm như secret version, key ID, certificate serial hoặc thời điểm credential được cấp. Sau restore, lấy credential hiện hành và kiểm tra version/policy trước khi mở traffic.

Không lưu raw secret trong manifest checkpoint. Manifest chỉ nên có tên secret, version reference hoặc identifier cần thiết để lấy lại dữ liệu.

### Rotation và thu hồi

Khi một checkpoint image bị lộ hoặc không còn được tin cậy:

1. Xác định các secret có thể đã nằm trong image.
2. Thu hồi hoặc rotate credential tương ứng.
3. Vô hiệu hóa token/session có thể bị sử dụng lại.
4. Xác định tất cả bản sao image và backup.
5. Chặn restore từ image không còn tin cậy.
6. Tạo checkpoint image mới sau khi credential được cấp lại.
7. Ghi audit event và kiểm tra truy cập bất thường.

Xóa image không thay thế việc rotate secret nếu đã có khả năng image bị sao chép.

## 12. Log, tracing và diagnostic data

Secret có thể bị sao chép ra khỏi heap qua logging và observability.

Các vị trí cần kiểm tra:

- Authorization header.
- Cookie và Set-Cookie.
- Query parameter có token.
- Request/response body.
- JDBC URL chứa credential.
- Exception message từ driver hoặc SDK.
- HTTP client wire log.
- Distributed trace baggage hoặc span attribute.
- Debug dump và heap dump.
- Metrics label có giá trị định danh nhạy cảm.

Không log raw request hoặc toàn bộ object cấu hình. Dùng allowlist cho field được phép ghi và redact header/field nhạy cảm trước khi gửi log hoặc trace.

Nếu checkpoint image được tạo sau khi bật debug logging, các buffer hoặc diagnostic object có thể giữ dữ liệu nhạy cảm lâu hơn. Tắt chế độ dump request/body trong production trừ khi có nhu cầu được phê duyệt và kiểm soát.

## 13. Phát hiện bí mật trong image và kiểm tra trước phân phối

Việc kiểm tra image có thể hỗ trợ phát hiện dữ liệu nhạy cảm ngoài dự kiến, nhưng phải thực hiện trong môi trường được kiểm soát.

Các biện pháp có thể áp dụng:

- Duy trì secret inventory cho ứng dụng và thư viện.
- Quét artifact hoặc vùng nhớ bằng công cụ được phê duyệt.
- Dùng canary secret trong môi trường thử nghiệm để xác nhận dữ liệu có bị lưu trong image không.
- Kiểm tra log và diagnostic bundle để phát hiện credential bị ghi ra.
- Kiểm tra quyền truy cập và mã hóa của thư mục image.
- Đánh giá thư viện native hoặc SDK có giữ key material trong memory hay không.

Không chạy công cụ quét tùy tiện trên image production nếu công cụ có thể tạo bản sao tạm, dump plaintext hoặc ghi secret vào output. Scanner cũng cần được bảo vệ như một công cụ xử lý dữ liệu nhạy cảm.

Khi dùng canary secret, chỉ dùng giá trị giả trong môi trường thử nghiệm. Không đưa credential production vào bài kiểm tra hoặc ví dụ.

### Không đưa secret vào báo cáo

Khi phát hiện chuỗi giống token hoặc password, báo cáo nên chỉ chứa:

- Loại dữ liệu.
- Vị trí hoặc thành phần liên quan.
- Secret identifier hoặc hash đã được xử lý an toàn.
- Mức độ nghiêm trọng.
- Hướng khắc phục.

Không chép giá trị secret nguyên văn vào ticket, log hoặc báo cáo kiểm tra.

## 14. Bảo vệ backup và vòng đời checkpoint image

Checkpoint image thường được xem là artifact có thể tái sử dụng. Vì vậy, cần quản lý vòng đời rõ ràng:

~~~text
Tạo checkpoint
      |
      v
Mã hóa và ghi vào vùng lưu trữ được bảo vệ
      |
      v
Ghi metadata / audit
      |
      v
Phân phối qua kênh an toàn
      |
      v
Xác thực image và quyền restore
      |
      v
Restore trong workload được phép
      |
      v
Giữ image theo retention policy
      |
      v
Xóa image, bản sao và backup hết hạn
~~~

Các kiểm soát nên có:

- Mã hóa at-rest và in-transit.
- Quyền truy cập theo role và workload identity.
- Audit log cho read, copy, download, restore và delete.
- Integrity check hoặc chữ ký artifact nếu nền tảng hỗ trợ.
- Retention policy rõ ràng.
- Xóa bản sao trong cache và staging.
- Backup được bảo vệ với cùng mức phân loại.
- Cấm chia sẻ qua kênh không được quản lý.

Nếu image được sao lưu tự động bởi volume snapshot hoặc backup agent, cần tính cả các bản sao đó trong thời gian lưu giữ. Xóa file gốc không nhất thiết xóa snapshot hoặc bản backup.

## 15. Kiểm soát môi trường restore

Không restore checkpoint production vào một môi trường không đáng tin cậy chỉ để kiểm tra nhanh. Khi restore, dữ liệu nhạy cảm có thể xuất hiện trở lại trong memory của tiến trình mới.

Trước khi restore, cần xác minh:

- Workload identity đúng.
- Node và namespace thuộc môi trường được phép.
- Secret manager/KMS policy cho phép workload này truy cập.
- Checkpoint image được xác thực và không bị thay đổi.
- Network policy giới hạn kết nối ra ngoài.
- Log, tracing và diagnostic endpoint được bảo vệ.
- Debugger, heap dump và process inspection chỉ dành cho người được cấp quyền.
- Readiness gate giữ traffic đóng cho đến khi kiểm tra hoàn tất.

Nếu image bị sao chép sang staging, hãy cân nhắc dùng dữ liệu giả và credential staging. Một image production có thể mang theo production secret dù cấu hình bên ngoài của môi trường mới là staging.

## 16. Các lỗi thường gặp

### Nghĩ rằng secret nằm trong environment variable nên không vào image

Sau khi đọc environment, ứng dụng có thể giữ secret trong String, configuration bean hoặc client. Process environment cũng cần được xem xét trong mô hình snapshot.

Cách xử lý: kiểm kê cả nguồn nạp và object đang giữ giá trị; bảo vệ image như dữ liệu nhạy cảm.

### Gán null rồi cho rằng secret đã bị xóa

Gán null chỉ bỏ tham chiếu. Nó không ghi đè nội dung String hoặc mọi bản sao.

Cách xử lý: giảm số bản sao, dùng mutable buffer khi API hỗ trợ, xóa best-effort và tránh giữ secret lâu dài. Không tuyên bố zeroization tuyệt đối nếu không có bảo đảm từ provider/runtime.

### Đóng HTTP client nhưng token vẫn còn trong heap

close() giải phóng tài nguyên client theo implementation, nhưng token có thể còn trong object cấu hình, header cache hoặc String khác.

Cách xử lý: xác định nơi giữ token, giới hạn vòng đời, xóa dữ liệu tạm và lấy credential mới sau restore.

### Credential hết hạn khi image nằm chờ

Restore có thể dùng token đã hết hạn hoặc password đã rotate.

Cách xử lý: tái lấy secret sau restore, kiểm tra version/expiry và chỉ mở traffic khi xác thực thành công.

### Xóa secret trong beforeCheckpoint nhưng checkpoint bị hủy

Tiến trình gốc có thể tiếp tục nhưng credential đã bị xóa. afterRestore() không chạy trong nhánh này.

Cách xử lý: khi gọi Core.checkpointRestore(), bắt CheckpointException và khôi phục secret/client; nếu dùng jcmd bên ngoài, phải có recovery độc lập hoặc không thực hiện bước cleanup không thể đảo ngược.

### Mã hóa image nhưng để khóa trong image

Người đọc image có thể lấy cả dữ liệu lẫn khóa giải mã.

Cách xử lý: giữ khóa ngoài image trong KMS/HSM hoặc secret manager độc lập.

### Debug hoặc heap dump làm lộ secret

Diagnostic artifact có thể chứa cùng dữ liệu nhạy cảm như checkpoint image.

Cách xử lý: giới hạn quyền, redact log, bảo vệ dump và áp dụng retention/xóa tương tự image.

## 17. Quy trình triển khai

### Trước checkpoint

1. Lập inventory secret, PII và dữ liệu nhạy cảm từ heap, stack, buffer và native memory.
2. Xác định object, cache, ThreadLocal và client đang giữ credential.
3. Ngừng nhận request mới và drain công việc đang xử lý.
4. Xóa request context, session tạm và buffer không cần thiết.
5. Đóng client hoặc connection giữ session cũ theo lifecycle đã thiết kế.
6. Ghi đè mutable buffer có thể xóa an toàn.
7. Đảm bảo credential cần dùng sau restore có thể được cấp lại từ nguồn độc lập.
8. Không thực hiện cleanup không thể đảo ngược nếu không có đường phục hồi khi checkpoint bị hủy.
9. Tạo image trong vùng lưu trữ được bảo vệ.

### Bảo vệ image

1. Phân loại image theo mức nhạy cảm cao nhất của dữ liệu process memory.
2. Mã hóa khi lưu và truyền theo khả năng nền tảng.
3. Giữ khóa mã hóa ngoài image.
4. Giới hạn quyền đọc, copy, download và restore.
5. Audit mọi lần truy cập và thao tác.
6. Bảo vệ backup, cache, staging và bản sao tạm.
7. Áp dụng retention policy và xóa các bản sao hết hạn.

### Sau restore

1. Giữ request gate và worker ở trạng thái chưa nhận việc.
2. Xác thực workload identity.
3. Lấy credential/token mới từ secret manager hoặc KMS.
4. Tạo lại HTTP client, JDBC pool và TLS session cần thiết.
5. Kiểm tra expiry, version và quyền truy cập.
6. Xóa buffer secret tạm sau khi tạo client.
7. Xác minh readiness rồi mới mở traffic.

### Khi checkpoint bị hủy

Nếu ứng dụng gọi Core.checkpointRestore(), bắt CheckpointException và khôi phục các client hoặc credential đã được giải phóng trong beforeCheckpoint(). Nếu recovery thất bại, giữ ứng dụng not-ready.

Nếu checkpoint được yêu cầu bằng jcmd từ bên ngoài, luồng ứng dụng không bắt được exception qua API. Thiết kế callback và quy trình vận hành phải bảo đảm tiến trình gốc có thể phục hồi; không giả định afterRestore() sẽ chạy khi checkpoint bị hủy.

## 18. Nguyên tắc cần ghi nhớ

- Checkpoint image có thể chứa dữ liệu trong heap, stack, buffer và native memory.
- Environment variable hoặc secret file không ngăn giá trị đã nạp xuất hiện trong bộ nhớ.
- Inventory password, token, key material, session, PII, request payload và cache.
- String là immutable; gán null không xóa nội dung.
- Ghi đè char[] hoặc byte[] là biện pháp best-effort, không bảo đảm xóa mọi bản sao.
- Không ghi secret vào log, trace, URL, command line hoặc diagnostic output.
- Đóng client không đồng nghĩa mọi credential trong heap đã được zeroize.
- Tái lấy credential sau restore từ secret manager, workload identity, KMS hoặc HSM khi có thể.
- Cấp quyền truy cập image theo least privilege và mã hóa cả bản sao, backup, staging.
- Giữ khóa mã hóa ngoài checkpoint image.
- Rotate hoặc revoke credential nếu image có khả năng bị lộ.
- Không restore image production vào môi trường kém tin cậy.
- Phân biệt checkpoint bị hủy với restore thành công; afterRestore() không phải callback rollback.
- Chỉ mở traffic khi credential và dependency đã được xác thực lại.

Checkpoint image là bản ghi trạng thái tiến trình và có thể mang theo bí mật mà ứng dụng từng nạp vào bộ nhớ. Khi kiểm kê nguồn secret, giảm dữ liệu tồn tại tại thời điểm checkpoint, bảo vệ mọi bản sao image và cấp lại credential sau restore, hệ thống có thể giữ được lợi ích khởi động nhanh mà vẫn kiểm soát được rủi ro lộ thông tin nhạy cảm.
