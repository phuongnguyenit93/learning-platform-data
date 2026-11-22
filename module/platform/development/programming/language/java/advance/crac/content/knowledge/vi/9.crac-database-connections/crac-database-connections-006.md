# Thông tin xác thực cơ sở dữ liệu hết hạn hoặc được xoay vòng

Trong chu kỳ CRaC, một ứng dụng Java có thể được checkpoint trong khi vẫn giữ cấu hình database, đối tượng `DataSource`, connection pool và thông tin xác thực trong heap. Trong thời gian tiến trình ở trạng thái checkpoint, mật khẩu database có thể được đổi, token xác thực có thể hết hạn, credential có thể bị thu hồi hoặc chứng chỉ client có thể được thay thế.

Khi restore, JVM tiếp tục từ trạng thái đã lưu. Các field và object cấu hình trong memory không tự cập nhật theo secret store. Nếu ứng dụng tiếp tục dùng credential cũ để tạo kết nối mới, database có thể từ chối xác thực. Nếu connection pool tái sử dụng một session cũ, hành vi còn phụ thuộc database và chính sách rotation: một số hệ thống chỉ ảnh hưởng các lần đăng nhập mới, trong khi hệ thống khác có thể thu hồi hoặc chấm dứt session đang tồn tại.

Ứng dụng CRaC vì vậy cần xem credential là dữ liệu có thời hạn và có thể thay đổi. Trước checkpoint, ứng dụng đưa connection pool về trạng thái an toàn. Sau restore, ứng dụng đọc credential hiện hành từ nguồn quản lý bí mật, tạo pool/client mới, kiểm tra kết nối rồi mới cho phép nhận traffic.

## 1. Vì sao credential có thể không còn hợp lệ sau restore?

Thông tin xác thực thường được nạp lúc ứng dụng khởi động và được giữ trong nhiều thành phần:

- `DataSource` hoặc connection pool giữ username/password dùng khi mở connection mới.
- JDBC driver hoặc thư viện database giữ cấu hình xác thực và trạng thái session.
- Ứng dụng giữ password, access token, refresh token hoặc credential object trong field/cache.
- Secret SDK có thể cache secret theo version hoặc thời gian sống riêng.
- Client certificate và private key có thể được nạp vào keystore hoặc TLS context.

Checkpoint lưu trạng thái tiến trình tại một thời điểm. Giả sử ứng dụng được checkpoint lúc 09:00 với password version `v12`. Đến 09:20, hệ thống bảo mật xoay vòng sang `v13` và thu hồi `v12`. Khi restore lúc 09:30, object trong heap vẫn có thể chứa password `v12`, dù secret store đã trả về `v13` cho các workload mới.

```text
09:00  JVM đang chạy
       Credential v12 được nạp vào DataSource/pool
             |
             v
       Tạo checkpoint
             |
             v
09:20  Database/secret store xoay vòng sang v13
       v12 có thể bị thu hồi
             |
             v
09:30  Restore từ ảnh cũ
       Heap vẫn chứa trạng thái v12
             |
             v
       Ứng dụng phải đọc v13 và tạo pool mới
```

Thời gian checkpoint càng dài thì khả năng credential thay đổi càng cao. Ngay cả khi thời gian checkpoint ngắn, token có TTL vài phút vẫn có thể hết hạn trong lúc tiến trình tạm dừng.

## 2. Các loại credential và vòng đời của chúng

Không phải mọi thông tin xác thực đều là mật khẩu tĩnh. Cần nhận diện loại credential để chọn cách refresh phù hợp.

| Loại credential | Đặc điểm | Việc cần làm sau restore |
| --- | --- | --- |
| Username/password | Có thể được quản trị viên hoặc secret manager xoay vòng | Đọc phiên bản hiện hành và cấu hình lại pool trước khi mở kết nối mới. |
| Database access token | Có thể hết hạn theo thời gian ngắn, đôi khi gắn với audience hoặc scope | Xin token mới; kiểm tra `expiresAt` và không tái sử dụng token cũ chỉ vì object vẫn còn trong heap. |
| Cloud/IAM authentication token | Có thể được ký hoặc cấp theo từng lần kết nối, có TTL ngắn | Tạo token mới khi pool mở connection; tránh cache token vượt quá thời hạn. |
| Client certificate/private key | Certificate có ngày hết hạn, có thể được thay thế hoặc thu hồi | Nạp certificate/key mới và dựng lại TLS context hoặc client nếu thư viện không hỗ trợ reload an toàn. |
| Trust store/CA bundle | CA có thể được thêm, thay thế hoặc loại bỏ | Đọc trust material mới và tạo lại TLS context để xác thực server theo chính sách hiện tại. |
| Credential do secret file cung cấp | Nội dung file có thể được cập nhật bởi hệ thống triển khai | Đọc lại file sau restore; không dùng bản đã parse vào object từ trước checkpoint. |

Ứng dụng cần biết credential đến từ đâu, có version nào, hết hạn lúc nào và cơ chế refresh nào được hỗ trợ. Không nên giả định mọi credential có thể được làm mới bằng cách thay một chuỗi password trong object `DataSource` đang tồn tại.

## 3. Phân biệt credential trong heap với credential tại nguồn

Secret manager hoặc hệ thống cấp token là nguồn sự thật. Object trong heap chỉ là bản sao đã được đọc tại một thời điểm.

Ví dụ, một bean có thể giữ password khi khởi động:

```java
public final class DatabaseSettings {
    private final String username;
    private final String password;

    public DatabaseSettings(String username, String password) {
        this.username = username;
        this.password = password;
    }
}
```

Nếu bean này được khôi phục từ checkpoint, các field không tự thay đổi khi password bên ngoài đã được xoay vòng. Tương tự, đọc environment variable sau restore thường vẫn trả về giá trị môi trường mà process nhận lúc khởi chạy; restore không khởi tạo process mới để nhận environment mới.

Nếu triển khai cập nhật secret qua mounted file, cần đọc lại nội dung file sau restore và hiểu cách volume/mount cập nhật dữ liệu. Không nên giữ nội dung đã parse vào một singleton rồi cho rằng file được thay đổi sẽ tự cập nhật object.

Một thiết kế rõ ràng nên tách ba lớp:

- **Secret provider:** lấy credential hiện hành từ secret manager, IAM provider hoặc file được quản lý.
- **Credential snapshot:** chứa giá trị, version và thời hạn của credential được lấy tại một thời điểm.
- **Database client/pool:** sử dụng snapshot để mở connection. Khi credential thay đổi, client/pool được thay mới theo khả năng của thư viện.

Không lưu IP hoặc endpoint tạm thời cùng credential nếu chúng có vòng đời độc lập. Endpoint database có thể thay đổi riêng; cần refresh theo chính sách mạng và service discovery tương ứng.

## 4. Xử lý connection pool trước checkpoint

Connection pool có thể giữ nhiều connection đã xác thực bằng credential cũ. Sau một khoảng thời gian checkpoint, các connection này có thể bị database đóng, firewall timeout hoặc session bị thu hồi. Pool cũng có thể giữ password cũ để mở thêm connection khi cần.

Một quy trình chuẩn bị thường gồm:

1. Chuyển ứng dụng hoặc database client sang trạng thái `QUIESCING`, ngăn công việc mới sử dụng pool.
2. Chờ các transaction/request đang chạy hoàn tất trong một deadline hữu hạn.
3. Xử lý các connection đang mượn theo chính sách của pool và ứng dụng.
4. Đóng pool hoặc giải phóng các socket theo API được thư viện hỗ trợ trước checkpoint.
5. Giữ lại factory/provider và cấu hình logic cần thiết để tạo pool mới sau restore.

Không nên chỉ gọi `Connection.close()` trên một connection đang được pool quản lý nếu điều đó chỉ trả connection về pool. Cần dùng API đóng pool/client đúng cách. Cũng không nên giả định một pool đã `close()` có thể `start()` lại; nhiều implementation yêu cầu tạo instance mới.

Việc đóng pool trước checkpoint không làm cho mọi bản sao password biến mất khỏi heap. Credential có thể vẫn nằm trong object cấu hình, chuỗi immutable, log hoặc cache khác. Cần hạn chế số nơi giữ secret và bảo vệ checkpoint như dữ liệu nhạy cảm.

## 5. Đọc credential hiện hành sau restore

Trong `afterRestore`, Resource hoặc lifecycle coordinator có thể thực hiện các bước:

1. Kết nối tới secret manager hoặc đọc nguồn secret hiện tại.
2. Lấy credential version mới nhất theo identity của ứng dụng.
3. Kiểm tra credential chưa hết hạn và còn đủ thời gian sống cho thao tác mở pool.
4. Tạo pool/client mới từ credential vừa lấy.
5. Mở thử connection và thực hiện health check phù hợp.
6. Chỉ công bố pool mới và mở nhận traffic sau khi validation thành công.

Không nên gọi secret manager trong khi đang giữ application lock. Việc đọc secret có thể cần DNS, TLS handshake hoặc network I/O. Hãy dùng timeout và retry/backoff có giới hạn, đồng thời bảo đảm callback có deadline tổng.

Nếu secret provider cần một HTTP client hoặc network Resource khác để kết nối, không nên dựa vào thứ tự callback ngầm giữa các `Resource`. Hãy để secret provider tự phục hồi kết nối cần thiết, hoặc điều phối việc refresh và tạo pool trong một lifecycle coordinator có thứ tự rõ ràng.

## 6. Ví dụ quản lý DataSource bằng Resource

Ví dụ dưới đây dùng các abstraction `SecretProvider`, `DatabasePoolFactory` và `ManagedDatabasePool` do ứng dụng định nghĩa. Cách làm này tránh giả định rằng mọi thư viện pool đều có cùng API để thay credential hoặc khởi động lại sau khi đóng.

```java
import org.crac.Context;
import org.crac.Resource;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public final class DatabaseResource implements Resource {
    private final SecretProvider secretProvider;
    private final DatabasePoolFactory poolFactory;
    private final AtomicReference<ManagedDatabasePool> currentPool =
            new AtomicReference<>();

    public DatabaseResource(
            SecretProvider secretProvider,
            DatabasePoolFactory poolFactory) {
        this.secretProvider = secretProvider;
        this.poolFactory = poolFactory;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        stopAcceptingDatabaseWork();
        drainTransactionsWithTimeout();

        ManagedDatabasePool oldPool = currentPool.getAndSet(null);
        if (oldPool != null) {
            oldPool.close();
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        DatabaseCredentials credentials = secretProvider.fetchCurrent();

        if (!credentials.expiresAt().isAfter(Instant.now().plusSeconds(30))) {
            throw new IllegalStateException("Database credential expires too soon");
        }

        ManagedDatabasePool candidate = poolFactory.create(credentials);
        try {
            candidate.validateConnection();
            currentPool.set(candidate);
            resumeAcceptingDatabaseWork();
        } catch (Exception e) {
            currentPool.compareAndSet(candidate, null);
            candidate.close();
            throw e;
        }
    }

    private void stopAcceptingDatabaseWork() { /* application-specific */ }
    private void drainTransactionsWithTimeout() { /* bounded wait */ }
    private void resumeAcceptingDatabaseWork() { /* application-specific */ }
}
```

Các interface được minh họa ở mức khái niệm:

```java
import java.time.Instant;

public interface SecretProvider {
    DatabaseCredentials fetchCurrent() throws Exception;
}

public interface DatabasePoolFactory {
    ManagedDatabasePool create(DatabaseCredentials credentials) throws Exception;
}

public interface ManagedDatabasePool extends AutoCloseable {
    void validateConnection() throws Exception;
    @Override
    void close();
}

public record DatabaseCredentials(
        String username,
        char[] password,
        String version,
        Instant expiresAt) {}
```

Các kiểu trên là abstraction ứng dụng, không phải class có sẵn trong CRaC. Trong triển khai thực tế, `ManagedDatabasePool` có thể bọc HikariCP hoặc pool khác; `SecretProvider` có thể gọi Vault, cloud secret manager hoặc đọc file secret.

Đoạn code tập trung vào lifecycle. Một implementation production cần thêm timeout cho `drainTransactionsWithTimeout`, deadline tổng cho secret retrieval và connection validation, đồng bộ việc công bố pool, xử lý credential cleanup và trạng thái readiness. Không mở traffic chỉ vì `poolFactory.create()` trả về; cần xác nhận connection thật sự hoạt động.

Nếu callback đã đóng pool nhưng một Resource khác hoặc bước dump sau đó làm checkpoint attempt bị hủy, ứng dụng vẫn cần một đường phục hồi cho process ban đầu nếu nó tiếp tục chạy. Không dựa vào `afterRestore` như callback rollback cho checkpoint bị abort; hãy điều phối việc chuẩn bị và rollback trong lifecycle coordinator của ứng dụng, hoặc bảo đảm deployment không mở traffic lại cho tới khi pool được tạo lại và kiểm tra thành công.

## 7. Thay pool an toàn và tránh dùng credential cũ

Khi pool mới đã được tạo và kiểm tra, ứng dụng cần chuyển traffic sang pool mới một cách nhất quán. Không để một số request tiếp tục dùng pool cũ trong khi pool mới đã được công bố, trừ khi thiết kế hỗ trợ rõ ràng giai đoạn overlap.

Một chiến lược thay thế an toàn:

1. Chặn request mới dùng database và drain request đang chạy.
2. Tạo pool mới từ credential mới.
3. Kiểm tra kết nối và một truy vấn health check không gây side effect.
4. Thay reference hiện hành sang pool mới trong một thao tác đồng bộ ngắn.
5. Đóng pool cũ sau khi không còn request nào sử dụng nó.
6. Mở lại traffic.

Nếu ứng dụng giữ pool qua `AtomicReference`, việc swap reference có thể thực hiện nguyên tử, nhưng vẫn cần cơ chế ngăn request lấy pool cũ đúng lúc đang đóng. Có thể dùng quiesce/drain hoặc một provider có cơ chế lease/reference count. Atomic swap một mình không giải quyết lifecycle của request đang sử dụng pool cũ.

Nếu pool mới không kết nối được, không công bố nó và không đánh dấu ứng dụng sẵn sàng. Giữ trạng thái `NOT_READY`, đóng candidate pool và thử lại theo deadline/retry policy. Không âm thầm fallback sang credential đã biết là hết hạn hoặc đã bị thu hồi.

## 8. Chiến lược rotation ở phía database và secret manager

Ứng dụng không thể kiểm soát toàn bộ cách database áp dụng rotation. Cần phối hợp quy trình cấp credential với thời điểm triển khai và khả năng của database.

### Rotation có khoảng thời gian chồng lấn

Nếu database hỗ trợ nhiều credential hoặc hai user có quyền tương đương trong giai đoạn chuyển đổi, có thể:

1. Tạo credential mới.
2. Cập nhật secret store với version mới.
3. Cho ứng dụng refresh và xác nhận kết nối bằng credential mới.
4. Chờ các instance chuyển sang version mới.
5. Thu hồi credential cũ sau khi xác nhận không còn workload dùng nó.

Khoảng thời gian overlap giúp giảm nguy cơ downtime, nhưng cần giới hạn thời gian và quyền của credential cũ. Không giữ hai credential hoạt động vô thời hạn.

### Rotation tức thời

Nếu credential cũ bị thu hồi ngay, mọi kết nối mới dùng credential đó có thể thất bại. Tùy database, các session đã xác thực có thể tiếp tục hoặc cũng bị ngắt. Hãy đọc chính sách của database và kiểm thử trước khi áp dụng. Sau restore, luôn tạo pool mới từ secret hiện hành thay vì dựa vào trạng thái session trong ảnh checkpoint.

### Token ngắn hạn hoặc IAM authentication

Với token ngắn hạn, nên tạo token khi cần mở connection hoặc refresh trước khi token hết hạn. Tránh checkpoint một token rồi dùng lại sau restore mà không kiểm tra `expiresAt`. Nếu token được ký theo thời gian, cần tính đến clock skew và dành một safety margin.

### Certificate rotation

Nếu database dùng mutual TLS, sau restore cần nạp certificate/private key hiện hành và dựng lại TLS context hoặc client theo API của thư viện. Nếu CA/trust store thay đổi, client cũng cần reload trust material. Không tắt xác thực certificate để khắc phục lỗi rotation.

## 9. Credential hết hạn trong khi ứng dụng vẫn chạy

Credential refresh không chỉ cần cho CRaC. Một ứng dụng chạy liên tục cũng có thể giữ pool lâu hơn TTL của token hoặc password version. Nên có một cơ chế refresh định kỳ hoặc theo sự kiện rotation:

- Theo dõi `expiresAt` hoặc secret version.
- Bắt đầu refresh trước thời điểm hết hạn với safety margin.
- Tạo và validate pool/client mới trước khi thay pool hiện tại nếu chính sách cho phép overlap.
- Xử lý lỗi refresh theo trạng thái readiness và retry policy.
- Theo dõi số connection đang dùng credential cũ nếu database/driver cung cấp telemetry.

Không nên chỉ đợi lần đăng nhập tiếp theo thất bại mới biết credential đã hết hạn. Tuy nhiên, lỗi authentication vẫn cần được xử lý như một tín hiệu để refresh một lần có kiểm soát; tránh retry vô hạn với cùng secret cũ.

## 10. Timeout, retry và lỗi khi lấy secret

Secret manager có thể tạm thời không truy cập được ngay sau restore do DNS, network, IAM endpoint hoặc dịch vụ đang khởi động. Việc refresh cần có deadline tổng, timeout kết nối/đọc và retry/backoff có giới hạn.

Phân loại lỗi trước khi retry:

| Lỗi | Hành động phù hợp |
| --- | --- |
| Timeout hoặc lỗi mạng tạm thời khi gọi secret manager | Retry có backoff và jitter trong deadline; kiểm tra lại network và resolver. |
| Unauthorized/forbidden khi đọc secret | Kiểm tra workload identity, IAM role, policy và quyền truy cập; không lặp vô hạn. |
| Secret version không tồn tại hoặc bị thu hồi | Refresh metadata/version và xử lý theo quy trình rotation; không dùng secret cũ làm fallback nếu đã bị thu hồi. |
| Credential hết hạn | Yêu cầu token/credential mới từ nguồn cấp; không retry database với cùng token đã hết hạn. |
| Database từ chối xác thực | Refresh credential một lần theo chính sách, sau đó thử lại có giới hạn và ghi nhận version đã dùng. |
| Database không reachable | Kiểm tra DNS, route, firewall và health; phân biệt lỗi mạng với lỗi authentication. |

Nếu không thể lấy credential hợp lệ trong deadline, callback nên báo lỗi và ứng dụng không được mở readiness. Để instance chạy với pool chưa xác thực có thể làm request lỗi hàng loạt hoặc tạo ra trạng thái khó kiểm soát.

## 11. Bảo vệ credential trong checkpoint image

Checkpoint có thể chứa heap và trạng thái bộ nhớ của ứng dụng. Nếu password, access token, private key hoặc credential object đang nằm trong heap, ảnh checkpoint có thể chứa dữ liệu đó ngay cả khi ứng dụng đóng connection pool trước khi tạo ảnh.

Vì vậy:

- Lưu checkpoint trên storage có kiểm soát quyền truy cập và mã hóa phù hợp.
- Giới hạn người và service được phép đọc, sao chép hoặc tải checkpoint.
- Đặt retention policy và xóa ảnh cũ theo quy trình có kiểm soát.
- Không đưa checkpoint vào artifact công khai, image container hoặc log.
- Hạn chế số nơi giữ credential trong heap và tránh sao chép secret không cần thiết.
- Không ghi password, token, private key hoặc nội dung secret vào log/exception.
- Xem xét thu hồi credential cũ sau rotation để ảnh checkpoint cũ không thể dùng secret đã bị thu hồi.
- Không coi việc dùng `char[]` thay cho `String` là bảo đảm bí mật được xóa hoàn toàn; thư viện và driver có thể tạo bản sao nội bộ.

Nếu cần hỗ trợ restore từ checkpoint cũ, thiết kế phải bảo đảm ứng dụng lấy credential mới từ nguồn có thẩm quyền thay vì phụ thuộc secret snapshot nằm trong ảnh.

## 12. Các lỗi thường gặp sau restore

| Hiện tượng | Nguyên nhân có thể gặp | Hướng điều tra |
| --- | --- | --- |
| `password authentication failed` khi mở connection mới | Pool hoặc DataSource dùng password cũ | Kiểm tra secret version, thời điểm rotation và cấu hình pool được tạo sau restore. |
| Token bị expired ngay sau restore | Token được checkpoint khi gần hết TTL | Đọc lại token từ issuer và kiểm tra safety margin theo `expiresAt`. |
| Pool có object nhưng không lấy được connection | Pool giữ session/socket cũ hoặc đã đóng trước checkpoint | Tạo pool mới và kiểm tra trạng thái lifecycle của pool. |
| Một số request thành công, một số request thất bại | Request dùng lẫn pool/credential cũ và mới | Kiểm tra swap pool, request đang giữ lease và việc đóng pool cũ. |
| Secret manager trả về secret cũ | Cache của SDK/provider hoặc version pin cố định | Kiểm tra TTL cache, version selector và cơ chế invalidate/refresh của provider. |
| Restore không truy cập được secret manager | DNS/network/IAM chưa sẵn sàng hoặc identity không hợp lệ | Kiểm tra network, workload identity, quyền và retry có giới hạn. |
| TLS handshake thất bại | Certificate, private key hoặc trust store đã được xoay vòng | Nạp lại TLS material và dựng client/context mới; kiểm tra hostname và trust chain. |
| Credential mới hợp lệ nhưng database vẫn từ chối | Sai username/database/role, quyền chưa được cấp hoặc rotation chưa đồng bộ | Kiểm tra account, database, role grants, secret version và trạng thái rotation. |

## 13. Kiểm thử credential rotation giữa checkpoint và restore

Một kiểm thử tích hợp nên mô phỏng đúng việc secret thay đổi trong khi ứng dụng không chạy:

1. Tạo database user/credential version `v1` trong môi trường thử nghiệm.
2. Khởi động ứng dụng và xác nhận connection pool mở được connection bằng `v1`.
3. Tạo checkpoint sau khi ứng dụng đã hoàn tất startup và xử lý công việc cần thiết.
4. Trong khi ứng dụng ở trạng thái checkpoint, tạo hoặc kích hoạt credential `v2` và cập nhật secret store.
5. Thu hồi `v1` theo chính sách thử nghiệm, nếu kịch bản cần kiểm tra tình huống rotation tức thời.
6. Restore ứng dụng trong môi trường tương thích.
7. Xác nhận `afterRestore` đọc `v2`, tạo pool mới và validate connection.
8. Gửi request database và xác nhận request dùng pool mới.
9. Xác nhận không có log chứa secret và không còn request sử dụng pool cũ.

Nên có thêm các kịch bản:

- Token hết hạn trước khi restore.
- Secret manager tạm thời không truy cập được.
- Secret version bị thu hồi hoặc quyền IAM bị thay đổi.
- Pool mới tạo được nhưng health query thất bại.
- Database rotation có overlap và rotation tức thời.
- Restore từ checkpoint cũ sau khi secret đã đổi nhiều version.
- Credential được cấp lại thành công nhưng TLS certificate hoặc CA cũng đã thay đổi.
- Checkpoint bị abort sau khi callback đã đóng pool; xác nhận ứng dụng có đường phục hồi an toàn trước khi nhận traffic lại.

Kiểm thử nên xác nhận cả hành vi thành công lẫn fail-closed: nếu không lấy được credential hợp lệ, ứng dụng giữ trạng thái `NOT_READY` và không phục vụ request cần database.

## 14. Quan sát và truy vết rotation

Để phân tích sự cố, ghi nhận metadata thay vì ghi secret:

- Secret identifier và version, không ghi giá trị secret.
- Thời điểm credential được lấy và thời điểm hết hạn.
- Checkpoint attempt id và restore attempt id.
- Thời gian lấy secret, tạo pool, mở connection và health check.
- Số lần retry, loại lỗi và thời gian backoff.
- Pool/client generation đang phục vụ request.
- Số request/connection còn sử dụng pool generation cũ trong thời gian swap.
- Trạng thái readiness trước và sau restore.

Các metric hữu ích gồm số lần refresh thành công/thất bại, số lỗi authentication, số token sắp hết hạn, thời gian reconnect và số request bị từ chối khi ứng dụng chưa sẵn sàng. Tránh đưa username nhạy cảm hoặc identifier có thể tiết lộ cấu trúc nội bộ vào metric label có cardinality cao.

## 15. Checklist vận hành

- [ ] Biết credential được cấp từ đâu và cơ chế rotation/expiry của nó.
- [ ] Không coi password/token trong heap là nguồn sự thật sau restore.
- [ ] Không phụ thuộc environment variable đã nạp lúc process start nếu secret có thể thay đổi.
- [ ] Có thể đọc lại secret version hiện hành sau restore.
- [ ] Trước checkpoint, dừng nhận việc mới, drain transaction và đóng pool theo API phù hợp.
- [ ] Sau restore, lấy credential mới và kiểm tra `expiresAt`/version.
- [ ] Tạo pool/client mới thay vì giả định pool cũ có thể đổi credential an toàn.
- [ ] Validate connection trước khi công bố pool mới và mở traffic.
- [ ] Có timeout, deadline tổng, retry/backoff và xử lý lỗi authentication rõ ràng.
- [ ] Không fallback sang credential đã hết hạn hoặc bị thu hồi.
- [ ] Có chiến lược rotation overlap hoặc phối hợp thu hồi theo khả năng của database.
- [ ] Bảo vệ checkpoint image vì nó có thể chứa secret trong heap.
- [ ] Không ghi password, token, private key hoặc secret vào log.
- [ ] Kiểm thử rotation xảy ra giữa checkpoint và restore.
- [ ] Khi refresh thất bại, giữ instance `NOT_READY` cho tới khi có credential và connection hợp lệ.

## 16. Kết luận

Credential có thể hết hạn hoặc bị xoay vòng trong khi ứng dụng đang ở trạng thái checkpoint. Restore khôi phục object và cấu hình trong heap tại thời điểm tạo ảnh; nó không tự cập nhật password, token, certificate hoặc secret cache theo nguồn bên ngoài. Connection pool cũ cũng có thể giữ session và credential không còn hợp lệ.

Hãy quản lý connection pool qua lifecycle CRaC: dừng và drain công việc trước checkpoint, đóng pool theo API phù hợp, đọc credential hiện hành sau restore, tạo pool mới và xác thực kết nối trước khi mở traffic. Kết hợp timeout, retry có giới hạn, rotation có overlap khi khả thi và bảo vệ checkpoint image để ứng dụng tiếp tục kết nối database an toàn khi credential thay đổi.
