# Secret lease

**Secret lease** là cơ chế cấp một secret hoặc credential trong một khoảng thời gian có giới hạn. Khi cấp phát, hệ thống quản lý lease trả về secret cần sử dụng cùng metadata mô tả thời hạn, khả năng gia hạn và định danh lease. Khi lease hết hạn hoặc bị thu hồi, hệ thống quản lý sẽ vô hiệu hóa credential hoặc thực hiện hành động thu hồi tương ứng.

Lease giúp giảm thời gian một credential có thể bị lạm dụng nếu bị lộ. Thay vì tạo một tài khoản cơ sở dữ liệu dùng chung rồi giữ mật khẩu trong cấu hình vô thời hạn, ứng dụng có thể yêu cầu credential động với TTL ngắn, sử dụng trong phạm vi công việc và để hệ thống quản lý thu hồi khi hết hạn.

Lease không phải là bản thân secret, cũng không phải khóa mật mã. Nó là hợp đồng quản lý vòng đời gắn với một secret được cấp phát. Trong hệ thống quản lý khóa, tư duy lease còn giúp giới hạn thời gian sử dụng credential hoặc quyền truy cập thao tác bằng khóa, nhưng không thay thế vòng đời riêng của vật liệu khóa.

## 1. Lease là gì?

Một lease mô tả quyền sử dụng một tài nguyên hoặc secret trong một khoảng thời gian. Khi cấp lease, secret manager hoặc secret engine có thể trả về:

- **Secret data:** giá trị cần dùng, ví dụ username/password cơ sở dữ liệu hoặc credential dịch vụ.
- **Lease ID:** định danh duy nhất để quản lý lease, thường được dùng khi gia hạn hoặc thu hồi.
- **Lease duration (TTL):** khoảng thời gian lease còn hiệu lực kể từ lúc được cấp hoặc gia hạn.
- **Renewable:** cho biết lease có được phép gia hạn hay không.
- **Metadata:** thông tin về role, secret engine, phiên bản hoặc thời điểm cấp phát tùy hệ thống.

Ví dụ, một ứng dụng cần kết nối database. Thay vì đọc một mật khẩu dùng chung được lưu nhiều năm, ứng dụng xác thực với secret manager bằng workload identity rồi yêu cầu một bộ thông tin đăng nhập động. Secret manager tạo tài khoản database theo role đã cấu hình, trả credential cùng lease có thời hạn. Khi ứng dụng không còn cần credential, nó có thể thu hồi lease; nếu không, hệ thống sẽ thu hồi khi lease hết hạn theo cơ chế của backend.

Lease thường được dùng với dynamic secrets, nhưng không phải mọi secret manager đều triển khai cùng một mô hình lease. Một số hệ thống quản lý secret tĩnh bằng version và rotation schedule; một số hệ thống cấp credential ngắn hạn nhưng không hiển thị lease ID riêng. Cần hiểu đúng khả năng của nền tảng đang sử dụng.

## 2. Lease khác secret, token và key thế nào?

Các đối tượng này có quan hệ nhưng không đồng nghĩa:

| Đối tượng | Vai trò | Ví dụ |
|---|---|---|
| **Secret** | Giá trị bí mật được sử dụng để xác thực hoặc thực hiện thao tác | Database password, API credential |
| **Lease** | Quy định thời hạn và vòng đời của secret được cấp | Lease TTL 30 phút |
| **Lease ID** | Định danh lease để gia hạn hoặc thu hồi | ID do secret manager trả về |
| **Access token** | Credential chứng minh quyền gọi một API hoặc dịch vụ | OAuth bearer token |
| **Cryptographic key** | Vật liệu mật mã dùng cho mã hóa, ký, MAC hoặc thỏa thuận khóa | AES key, HMAC key, private key |

Access token có thể có thời hạn riêng, và một lease có thể gắn với token đã cấp phát nó. Tuy nhiên, TTL của token và TTL của lease không mặc nhiên giống nhau. Thu hồi token xác thực có thể ngăn ứng dụng yêu cầu secret mới, nhưng không phải lúc nào cũng tự động thu hồi mọi secret đã được cấp trước đó. Ngược lại, thu hồi lease của một credential không nhất thiết thu hồi token dùng để gọi API khác.

Lease ID cũng không phải mật khẩu hay access token. Nó là định danh thao tác quản lý lease. Dù vậy, cần bảo vệ lease ID khỏi log và người không có nhiệm vụ quản trị vì người có quyền phù hợp có thể dùng nó để gia hạn hoặc thu hồi credential.

Một cryptographic key có thể được cấp qua một lease hoặc policy truy cập có thời hạn, nhưng lease không tự thay đổi thuật toán, độ dài hay vật liệu khóa. Hết lease có thể chặn quyền sử dụng hoặc thu hồi credential liên quan; việc hủy khóa, xử lý bản sao và bảo toàn khả năng giải mã dữ liệu cũ vẫn cần quy trình key management riêng.

## 3. TTL và thời điểm hết hạn

**TTL (time to live)** là khoảng thời gian lease còn hiệu lực. Nếu hệ thống cấp lease với TTL 30 phút, thời điểm hết hạn dự kiến là thời điểm cấp cộng thêm 30 phút. Khi gia hạn thành công, hệ thống trả về thời lượng hiệu lực mới hoặc thông tin lease mới theo giao thức của nó.

Cần phân biệt:

- **TTL:** thời lượng hiệu lực được cấp trong một lần cấp hoặc gia hạn.
- **Expiration time:** thời điểm hết hạn được ứng dụng tính hoặc hệ thống trả về.
- **Maximum TTL:** giới hạn tối đa mà policy hoặc secret engine cho phép lease tồn tại.
- **Credential expiry:** thời hạn riêng do hệ thống đích áp dụng cho credential.

TTL của lease và hạn dùng của credential ở backend cần được đồng bộ. Nếu secret manager cho rằng lease còn hiệu lực nhưng database đã vô hiệu hóa credential, ứng dụng vẫn có thể nhận lỗi kết nối. Nếu backend credential còn hiệu lực sau khi lease đã hết hạn, thời gian lạm dụng thực tế có thể dài hơn dự kiến. Thiết kế phải kiểm tra hành vi thu hồi thực tế của backend.

Không nên chỉ lưu một con số TTL rồi giả định ứng dụng có thể dùng secret chính xác đến giây cuối. Đồng hồ máy chủ có thể lệch, request có thể trễ và hệ thống đích có thể bắt đầu từ chối trước thời điểm mà ứng dụng tính được. Nên đặt thời điểm làm mới sớm hơn thời điểm hết hạn một khoảng an toàn.

## 4. Dynamic secret và static secret

Lease đặc biệt hữu ích khi secret được tạo động cho từng workload hoặc phiên làm việc.

| Đặc điểm | Dynamic secret | Static secret |
|---|---|---|
| Cách cấp | Hệ thống tạo credential mới theo role hoặc yêu cầu | Giá trị đã tồn tại được lưu và phân phối |
| Phạm vi | Có thể riêng cho từng ứng dụng hoặc phiên | Có thể được nhiều consumer dùng chung nếu thiết kế kém |
| Thu hồi | Có thể thu hồi theo lease | Thường cần rotation hoặc revoke tại hệ thống nguồn |
| Thời hạn | Thường có TTL và lease metadata | Có thể không có lease; thời hạn do chính sách riêng |
| Ví dụ | Database user tạm thời, credential cloud ngắn hạn | API key tĩnh, mật khẩu dịch vụ lâu dài |

Với dynamic database credentials, secret engine có thể tạo user riêng theo role, đặt quyền SQL và TTL, sau đó thu hồi user khi lease kết thúc. Cách này giúp giảm việc chia sẻ mật khẩu và tạo khả năng truy vết theo workload.

Với static secret như API key do nhà cung cấp phát hành, việc đặt secret vào vault không tự làm nó hết hạn. Secret manager có thể lưu version và nhắc rotation, nhưng hệ thống nguồn vẫn phải phát hành key mới và vô hiệu hóa key cũ. Nếu nền tảng có tính năng lease cho static secret, cần kiểm tra nó chỉ giới hạn việc phân phối hay thực sự thu hồi credential ở hệ thống đích.

## 5. Vòng đời của một lease

Một lease thường trải qua các trạng thái:

1. **Issue:** workload xác thực với secret manager và yêu cầu secret theo role hoặc policy.
2. **Active:** secret được trả về, lease có ID và TTL. Ứng dụng dùng credential trong phạm vi quyền được cấp.
3. **Renew:** nếu lease được phép gia hạn, workload yêu cầu kéo dài thời gian sử dụng trước khi hết hạn.
4. **Revoke:** ứng dụng hoặc quản trị viên chủ động yêu cầu thu hồi lease khi không còn cần secret hoặc khi có dấu hiệu bị lộ.
5. **Expire:** nếu không gia hạn, lease hết hạn và secret engine thực hiện hành động thu hồi theo cấu hình.
6. **Cleanup:** ứng dụng xóa secret khỏi bộ nhớ và đóng kết nối hoặc tài nguyên liên quan; backend xác nhận credential đã được vô hiệu hóa theo khả năng của nó.

Không phải lease nào cũng có thể gia hạn. Trường renewable hoặc metadata tương đương cho biết khả năng này. Lease không thể gia hạn cần được dùng trong giới hạn thời gian và yêu cầu lease mới nếu công việc vẫn cần tiếp tục.

Một số hệ thống cho phép gia hạn nhiều lần nhưng vẫn có **maximum TTL**. Khi chạm giới hạn, lease không thể kéo dài thêm; ứng dụng phải xin credential mới và chuyển sang credential mới trước khi lease cũ hết hạn.

## 6. Issue: cấp secret kèm lease

Khi yêu cầu secret, workload cần được xác thực bằng identity có quyền truy cập đúng role. Không nên để ứng dụng có quyền đọc toàn bộ secret store chỉ vì nó cần một database credential.

Một response lease có thể có cấu trúc khái niệm như sau:

~~~json
{
  "lease_id": "database/creds/orders/7f31...",
  "lease_duration": 1800,
  "renewable": true,
  "data": {
    "username": "v-orders-ephemeral",
    "password": "<secret-value>"
  }
}
~~~

Ví dụ trên minh họa metadata thường gặp trong API cấp dynamic secret; tên field và định dạng thực tế phụ thuộc nền tảng. Giá trị password là bí mật. Lease ID là metadata nhạy cảm về vận hành và không nên ghi vào log công khai.

Khi nhận response, ứng dụng cần:

- Xác minh request được gửi tới đúng secret manager qua TLS và danh tính workload được xác thực.
- Kiểm tra role, phạm vi quyền và thời hạn có phù hợp với công việc không.
- Lưu lease ID, TTL/expiration và renewable trong thành phần quản lý vòng đời.
- Đưa secret vào đúng consumer, tránh ghi ra log, metric label, trace hoặc exception.
- Chỉ giữ secret trong bộ nhớ trong thời gian cần thiết.

Với database credential, nên tạo role chỉ có quyền truy cập schema, bảng hoặc thao tác mà ứng dụng cần. TTL ngắn không thể bù cho quyền quá rộng.

## 7. Renew: gia hạn lease

Renew là yêu cầu kéo dài thời gian hiệu lực của một lease còn hoạt động. Ứng dụng chỉ nên gia hạn khi:

- Lease được đánh dấu renewable.
- Workload vẫn cần secret cho công việc đang chạy.
- Danh tính và policy vẫn cho phép gia hạn.
- Lease chưa hết hạn và chưa bị thu hồi.
- Thời gian gia hạn không vượt giới hạn của secret engine hoặc maximum TTL.

Một chu trình renew thường gồm việc gửi lease ID và thông tin gia hạn theo API, nhận thời hạn mới rồi cập nhật expiration trong bộ quản lý lease. Không được giả định yêu cầu renew thành công chỉ vì request đã được gửi; ứng dụng phải kiểm tra response và trạng thái mới.

Nên gia hạn trước khi hết hạn, có khoảng đệm cho độ trễ mạng, thời gian xử lý và clock skew. Với nhiều instance, thêm jitter để tránh tất cả workload đồng thời gửi yêu cầu renew. Khi lỗi tạm thời, retry có backoff và giới hạn; không retry vô hạn hoặc tiếp tục dùng credential sau khi đã hết hạn.

Không nên renew liên tục chỉ để giữ credential vô thời hạn. Việc gia hạn cần gắn với nhu cầu công việc, thời hạn tối đa và policy. Nếu một tác vụ kết thúc, hãy revoke lease thay vì đợi TTL.

## 8. Revoke và expire

**Revoke** là hành động chủ động thu hồi lease trước khi hết TTL. Có thể thực hiện khi:

- Ứng dụng kết thúc công việc sớm.
- Một workload bị xâm phạm hoặc mất quyền.
- Secret bị lộ hoặc nghi ngờ bị lộ.
- Credential cần được thay thế khẩn cấp.
- Quản trị viên cần chấm dứt quyền truy cập của một consumer.

**Expire** xảy ra khi TTL kết thúc mà lease không được gia hạn. Secret engine hoặc hệ thống quản lý sẽ thực hiện hành động hết hạn theo cấu hình, ví dụ xóa database user được tạo động hoặc thu hồi credential đã phát hành.

Thu hồi lease không phải lúc nào cũng đồng nghĩa mọi kết nối đang mở bị ngắt ngay lập tức. Ví dụ, xóa database user có thể ngăn đăng nhập mới nhưng hành vi với session hiện hữu phụ thuộc database và cơ chế revoke của backend. Ứng dụng cần đóng connection pool và xử lý session theo chính sách của hệ thống đích.

Đối với lease của dynamic credentials, backend cần hỗ trợ thao tác thu hồi. Nếu secret engine không thể liên hệ hệ thống đích, credential có thể chưa bị vô hiệu hóa đúng thời điểm. Hãy giám sát lỗi revoke, có quy trình xử lý thủ công và đánh giá thời gian credential thực sự còn dùng được.

## 9. Quản lý lease trong ứng dụng Java

Ứng dụng nên đóng gói secret cùng lease metadata trong một abstraction. Consumer cần biết secret, lease ID, expiration và khả năng renew mà không phải tự triển khai giao thức secret manager ở nhiều nơi.

Ví dụ sau mô tả một interface tổng quát. Phần triển khai SecretLeaseClient sẽ gọi API của secret manager cụ thể:

~~~java
import java.time.Instant;
import java.util.Arrays;

public final class LeaseContracts {
    private LeaseContracts() {
    }

    public interface SecretLease<T> extends AutoCloseable {
        T value();

        String leaseId();

        Instant expiresAt();

        boolean renewable();

        @Override
        void close() throws Exception;
    }

    public interface SecretLeaseClient {
        SecretLease<DatabaseCredentials> issueDatabaseCredentials(String role);

        LeaseMetadata renew(String leaseId);

        void revoke(String leaseId) throws Exception;
    }

    public static final class LeaseMetadata {
        private final Instant expiresAt;
        private final boolean renewable;

        public LeaseMetadata(Instant expiresAt, boolean renewable) {
            this.expiresAt = expiresAt;
            this.renewable = renewable;
        }

        public Instant expiresAt() {
            return expiresAt;
        }

        public boolean renewable() {
            return renewable;
        }
    }

    public static final class DatabaseCredentials {
        private final String username;
        private final char[] password;

        public DatabaseCredentials(String username, char[] password) {
            this.username = username;
            this.password = password.clone();
        }

        public String username() {
            return username;
        }

        public char[] passwordCopy() {
            return password.clone();
        }

        public void destroy() {
            Arrays.fill(password, (char) 0);
        }
    }
}
~~~

Ví dụ sử dụng lease trong một tác vụ ngắn:

~~~java
public final class DatabaseJob {
    private DatabaseJob() {
    }

    public static void run(LeaseContracts.SecretLeaseClient leaseClient)
            throws Exception {
        try (LeaseContracts.SecretLease<LeaseContracts.DatabaseCredentials> lease =
                 leaseClient.issueDatabaseCredentials("orders-readonly")) {

            LeaseContracts.DatabaseCredentials credentials = lease.value();
            char[] password = credentials.passwordCopy();

            try {
                connectAndRunQuery(credentials.username(), password);
            } finally {
                java.util.Arrays.fill(password, (char) 0);
                credentials.destroy();
            }
        }
    }

    private static void connectAndRunQuery(String username, char[] password) {
        // Tích hợp với JDBC hoặc connection pool của ứng dụng.
    }
}
~~~

Các interface trên là hợp đồng thiết kế, không phải implementation cho một nhà cung cấp cụ thể. Implementation close() cần có hành vi revoke được tài liệu hóa, xử lý lỗi rõ ràng và không làm mất thông tin lease nếu revoke thất bại. Trong hệ thống chạy dài, không nên giữ một try-with-resources mở vô hạn; hãy có một lease manager riêng để theo dõi expiration, renew và revoke khi workload dừng.

Khi renew, ứng dụng cần thay trạng thái lease bằng response mới và chuyển consumer sang credential mới nếu backend cấp lại giá trị. Không tiếp tục dùng bản credential cũ chỉ vì lease ID vẫn giống nhau. Hành vi sau renew phụ thuộc secret engine và cần được kiểm tra trong adapter.

Một lease manager có thể áp dụng logic sau:

~~~java
if (!activeLease.renewable()) {
    throw new IllegalStateException("Lease không cho phép gia hạn");
}

LeaseContracts.LeaseMetadata metadata =
    leaseClient.renew(activeLease.leaseId());

if (!metadata.expiresAt().isAfter(clock.instant())) {
    throw new IllegalStateException("Lease đã hết hạn sau khi renew");
}

activeLeaseMetadata = metadata;
~~~

Đoạn mã chỉ minh họa cập nhật metadata sau khi renew; trong thực tế cần kiểm tra renewable, xử lý lỗi mạng, giới hạn gia hạn, thay credential nếu backend trả giá trị mới và đồng bộ trạng thái giữa các instance.

## 10. Lease manager và phối hợp với connection pool

Ứng dụng có thể có nhiều request đồng thời nhưng dùng chung một bộ credential có lease. Khi đó, thành phần quản lý lease cần phối hợp vòng đời credential với connection pool.

Một số nguyên tắc:

- Lưu expiration và bắt đầu renew trước thời điểm hết hạn theo một khoảng đệm cấu hình.
- Chỉ một luồng hoặc một instance chịu trách nhiệm renew cho cùng lease, tránh renew đồng thời không cần thiết.
- Sau khi nhận credential mới, cập nhật pool theo cách an toàn; không đóng connection đang phục vụ request nếu chính sách cho phép drain.
- Ngừng tạo kết nối mới bằng credential cũ khi credential gần hết hạn hoặc đã bị thu hồi.
- Khi lease bị revoke, đóng hoặc loại bỏ kết nối và cache phụ thuộc vào credential đó.
- Khi ứng dụng shutdown, cố gắng revoke lease và xóa secret trong bộ nhớ; nếu revoke không thành công, ghi nhận sự kiện an toàn để hệ thống quản trị xử lý.

Trong môi trường nhiều replica, mỗi replica có thể nhận lease riêng hoặc một nhóm replica chia sẻ lease. Lease riêng giúp cô lập quyền và truy vết tốt hơn, nhưng tăng số lượng credential và tải secret manager. Lease dùng chung giảm số lượng nhưng làm tăng blast radius và phức tạp khi một replica bị xâm phạm. Chọn theo yêu cầu cô lập và khả năng backend.

## 11. Xử lý lỗi và tình huống biên

| Tình huống | Rủi ro | Cách xử lý |
|---|---|---|
| Secret manager không phản hồi khi issue | Ứng dụng không có credential mới | Không fallback sang credential nhúng trong image; trả lỗi hoặc dùng cơ chế dự phòng đã được phê duyệt |
| Renew thất bại tạm thời | Lease có thể hết hạn trước khi phục hồi | Retry có backoff trong cửa sổ an toàn, cảnh báo khi gần hết hạn |
| Lease không renewable | Ứng dụng mất quyền khi TTL kết thúc | Yêu cầu lease mới và chuyển consumer trước khi lease cũ hết hạn |
| Lease đã hết hạn | Credential có thể bị backend từ chối | Xin lease mới; không tiếp tục dùng credential cũ |
| Revoke thất bại | Credential có thể còn hiệu lực ở backend | Ghi nhận lease, retry có kiểm soát và cảnh báo để xử lý |
| Workload crash trước khi revoke | Lease tồn tại đến khi TTL hết hạn | Dùng TTL hợp lý, theo dõi lease mồ côi và dựa vào cleanup của backend |
| Credential được renew nhưng pool vẫn giữ credential cũ | Kết nối mới có thể thất bại | Cập nhật pool và drain connection theo chính sách |
| Đồng hồ workload lệch | Renew quá muộn hoặc quá sớm | Dùng thời gian từ response, đồng bộ clock và đặt safety margin |

Không nên dùng một credential tĩnh dự phòng khi secret manager gặp sự cố nếu credential đó có quyền rộng và không được quản lý. Cơ chế fallback phải được thiết kế trước, có quyền tối thiểu, thời hạn và audit riêng. Với các hệ thống nhạy cảm, fail closed có thể phù hợp hơn việc tiếp tục bằng một bí mật không còn được kiểm soát.

## 12. Lease trong hệ thống quản lý khóa

Lease thường được nhắc đến khi cấp dynamic secrets, nhưng ý tưởng giới hạn thời gian cũng hữu ích trong key management:

- Cấp quyền sử dụng một khóa trong một khoảng thời gian hoặc phiên làm việc.
- Cấp credential ngắn hạn để workload gọi KMS.
- Cấp certificate hoặc credential tạm thời cho một workload.
- Giới hạn thời gian một ứng dụng có thể truy cập private key hoặc thực hiện thao tác ký.

Tuy nhiên, cần phân biệt **lease của quyền truy cập** với **vòng đời của khóa**. Khi lease truy cập hết hạn, ứng dụng có thể mất quyền gọi KMS nhưng khóa gốc vẫn tồn tại để workload được cấp quyền khác sử dụng. Khi lease của dynamic database credential hết hạn, credential có thể bị thu hồi, nhưng không liên quan tới việc hủy một AES key đang bảo vệ dữ liệu.

Đối với khóa mã hóa, việc thu hồi hoặc hủy cần xét dữ liệu phụ thuộc. Xóa khóa quá sớm có thể khiến bản sao lưu hoặc dữ liệu lưu trữ không thể giải mã. Đối với private signing key, ngừng quyền ký không đồng nghĩa phải xóa public key đã công bố; public key cũ có thể cần được giữ để xác minh chữ ký trước đó.

## 13. Theo dõi và kiểm toán lease

Một hệ thống lease cần quan sát được vòng đời từ issue đến revoke/expire. Nên ghi nhận metadata đủ để điều tra:

- Lease ID hoặc định danh đã được che/mã hóa theo chính sách.
- Workload identity và role yêu cầu.
- Secret engine hoặc hệ thống nguồn.
- Thời điểm cấp, TTL, thời điểm renew và thời điểm hết hạn.
- Kết quả renew, revoke và cleanup.
- Lý do thu hồi hoặc lỗi backend.
- Consumer hoặc connection pool đã chuyển sang credential mới hay chưa.

Không ghi secret value, password, access token hoặc private key vào audit log. Lease ID cũng không nên xuất hiện trong log công khai hoặc metric label có thể truy cập rộng. Có thể dùng một định danh đã che hoặc correlation ID riêng để nối sự kiện.

Các chỉ số hữu ích gồm số lease đang hoạt động, số lease sắp hết hạn, renew thất bại, revoke thất bại, lease tồn tại quá TTL dự kiến và số credential động chưa được cleanup. Cảnh báo cần hướng tới người vận hành có trách nhiệm xử lý.

## 14. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Coi lease ID là secret value hoặc access token | Dùng sai API và ranh giới quyền | Phân biệt lease ID, secret data và token xác thực |
| Bỏ qua TTL | Workload dùng credential đã hết hạn | Theo dõi expiration và làm mới trước thời hạn |
| Renew mọi lease vô hạn | Credential tồn tại lâu hơn nhu cầu | Gắn renew với nhu cầu công việc và maximum TTL |
| Không kiểm tra renewable | Gửi renew cho lease không thể gia hạn | Kiểm tra metadata trước khi renew |
| Chỉ xóa secret khỏi bộ nhớ mà không revoke | Credential vẫn có thể còn hiệu lực ở backend | Revoke lease và xác minh cleanup |
| Revoke nhưng giữ connection pool cũ | Kết nối hoặc request có thể tiếp tục dùng credential cũ | Drain/close pool theo chính sách backend |
| Chia sẻ một lease cho quá nhiều workload | Khó truy vết và tăng blast radius | Cấp lease theo workload hoặc nhóm có ranh giới rõ |
| Không xử lý lỗi revoke | Lease mồ côi tồn tại đến hết TTL hoặc lâu hơn nếu backend lỗi | Retry có kiểm soát, cảnh báo và quy trình cleanup |
| Coi mọi secret manager đều có lease | Thiết kế phụ thuộc tính năng không tồn tại | Xác minh semantics của nhà cung cấp và secret engine |
| Nhầm lease truy cập với hủy khóa | Có thể xóa khóa quá sớm hoặc tưởng khóa đã bị hủy | Quản lý quyền truy cập và vòng đời key riêng biệt |

## 15. Nguyên tắc triển khai an toàn

- Ưu tiên dynamic credentials có TTL ngắn và quyền tối thiểu cho workload khi backend hỗ trợ.
- Xác thực workload trước khi issue; chỉ cho phép yêu cầu role và secret đúng phạm vi.
- Lưu lease ID, TTL, expiration và renewable trong lease manager; bảo vệ metadata quản lý.
- Renew trước expiration với safety margin, backoff và jitter; tuân thủ maximum TTL.
- Revoke ngay khi công việc kết thúc hoặc secret có dấu hiệu bị lộ; không chỉ xóa giá trị khỏi bộ nhớ.
- Phối hợp lease với connection pool, cache, session và các consumer đang sử dụng credential.
- Giám sát renew, revoke, expire và cleanup; có quy trình xử lý khi backend không thu hồi được credential.
- Không dùng credential fallback tĩnh có quyền rộng nếu chưa có policy và kiểm soát riêng.
- Tách lease của credential hoặc quyền truy cập khỏi vòng đời của cryptographic key.
- Kiểm thử tình huống workload crash, secret manager mất kết nối, lease hết hạn và rotation trong môi trường nhiều replica.

Secret lease giúp giới hạn thời gian một credential được phép tồn tại và tạo cơ chế quản lý có thể gia hạn hoặc thu hồi. Giá trị của lease phụ thuộc vào việc secret engine thực sự thu hồi credential ở hệ thống đích, ứng dụng theo dõi đúng TTL và consumer chuyển đổi an toàn. Khi kết hợp lease với workload identity, least privilege, audit và quy trình key management, hệ thống giảm thời gian phơi lộ secret và giới hạn ảnh hưởng khi credential bị xâm phạm.
