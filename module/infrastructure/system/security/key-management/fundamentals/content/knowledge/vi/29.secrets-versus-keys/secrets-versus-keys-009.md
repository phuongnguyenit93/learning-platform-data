# Dynamic secret trong quản lý bí mật

**Dynamic secret** (bí mật động) là thông tin xác thực hoặc bí mật được cấp phát theo yêu cầu, thường có thời hạn sử dụng giới hạn và được quản lý theo một lease (khoảng thuê). Thay vì dùng một mật khẩu hoặc API key tĩnh cho nhiều ứng dụng trong thời gian dài, hệ thống yêu cầu một credential riêng cho workload, người dùng hoặc phiên làm việc. Khi lease hết hạn hoặc bị thu hồi, hệ thống quản lý bí mật sẽ yêu cầu backend vô hiệu hóa credential theo khả năng của dịch vụ đích.

Ví dụ, một ứng dụng cần truy cập cơ sở dữ liệu có thể yêu cầu một tài khoản riêng chỉ có quyền đọc một schema và chỉ tồn tại trong 30 phút. Một workload khác có thể nhận thông tin xác thực cloud tạm thời, hoặc một dịch vụ có thể yêu cầu chứng thư máy khách với thời hạn ngắn. Mỗi lần cấp phát tạo ra một danh tính hoặc credential có thể truy vết riêng, giúp giới hạn phạm vi ảnh hưởng khi thông tin xác thực bị lộ.

Dynamic secret là một phần của quản lý vòng đời bí mật. Nó giảm nhu cầu phân phối mật khẩu dùng chung và giúp tự động hóa cấp phát, gia hạn, thu hồi. Tuy nhiên, thời hạn ngắn không tự động bảo đảm an toàn: hệ thống vẫn phải xác thực workload, giới hạn quyền, bảo vệ kênh cấp phát, theo dõi lease và xử lý lỗi thu hồi.

## 1. Dynamic secret là gì?

Dynamic secret thường được tạo khi một ứng dụng hoặc người dùng đã xác thực yêu cầu một credential cho một vai trò cụ thể. Secret manager gọi backend hoặc secrets engine để tạo tài khoản, token, chứng thư hay thông tin xác thực tạm thời. Kết quả được trả cho bên yêu cầu cùng metadata về thời hạn và cách quản lý vòng đời.

Một dynamic secret thường có các thuộc tính:

- **Được cấp phát theo yêu cầu:** chỉ tạo khi workload cần dùng, theo một role hoặc policy đã cấu hình.
- **Có phạm vi quyền xác định:** credential chỉ được phép thực hiện các thao tác cần thiết.
- **Có thời hạn:** lease hoặc thời hạn của credential xác định khoảng sử dụng.
- **Có thể gia hạn trong giới hạn:** một số loại lease cho phép renew trước khi hết hạn, nhưng thường bị giới hạn bởi maximum TTL hoặc chính sách backend.
- **Có thể thu hồi:** secret manager yêu cầu backend vô hiệu hóa credential trước hoặc khi hết hạn nếu backend hỗ trợ.
- **Có thể kiểm toán:** hệ thống ghi nhận ai yêu cầu, role nào được dùng, credential được cấp khi nào và đã được gia hạn/thu hồi ra sao.

Dynamic secret không nhất thiết là một chuỗi mật khẩu mới. Nó có thể là cặp username/password cơ sở dữ liệu, access key tạm thời, token, chứng thư số hoặc một tập thông tin xác thực khác. Điểm chung là credential được cấp phát và quản lý theo vòng đời thay vì tồn tại vô thời hạn.

## 2. Phân biệt dynamic secret, static secret và cryptographic key

Ba khái niệm liên quan nhưng không đồng nghĩa:

| Loại | Cách hình thành | Vòng đời thường gặp | Ví dụ |
|---|---|---|---|
| Static secret | Được tạo trước và lưu để nhiều lần sử dụng. | Tồn tại đến khi được rotate, revoke hoặc xóa. | API key dài hạn, mật khẩu dịch vụ dùng chung. |
| Dynamic secret | Được cấp theo yêu cầu từ secret manager hoặc hệ thống cấp phát. | Có lease/TTL, có thể renew hoặc revoke. | Tài khoản DB tạm thời, cloud session credential, chứng thư máy thời hạn ngắn. |
| Cryptographic key | Được sinh bằng CSPRNG, thiết bị mật mã hoặc KMS/HSM. | Theo key policy, cryptoperiod, trạng thái và phiên bản. | AES DEK, RSA private key, KEK trong HSM. |

Một cryptographic key có thể là bí mật, nhưng không phải mọi dynamic secret đều là khóa mật mã. Ví dụ, username/password DB động là credential để xác thực với database; nó không phải khóa AES dùng mã hóa dữ liệu. Ngược lại, một khóa ký hoặc khóa mã hóa có thể được tạo động, nhưng vẫn cần tuân theo key policy về thuật toán, mục đích, quyền sử dụng, khả năng export, backup và hủy.

Dynamic secret cũng khác với việc tự động rotate một static secret. Với static rotation, hệ thống thường thay giá trị của một credential đã tồn tại. Với dynamic provisioning, hệ thống tạo credential mới theo yêu cầu, cấp lease và quản lý việc vô hiệu hóa credential đó. Một nền tảng có thể hỗ trợ cả hai cách.

## 3. Lease, TTL, renew và revoke

Trong nhiều secret manager, dynamic secret được gắn với một **lease**. Lease là bản ghi quản lý vòng đời của credential được cấp; nó thường có lease ID, thời hạn, thông tin gia hạn và metadata cần thiết để thu hồi. Lease ID không phải password hay key material, nhưng vẫn nên được bảo vệ vì có thể được dùng để thao tác với lease.

| Thuật ngữ | Ý nghĩa |
|---|---|
| TTL (Time To Live) | Khoảng thời gian credential hoặc lease còn hiệu lực theo chính sách. |
| Lease ID | Định danh lease để gia hạn hoặc thu hồi credential tương ứng. |
| Renew | Yêu cầu kéo dài lease trước khi hết hạn, nếu loại secret và policy cho phép. |
| Maximum TTL | Giới hạn tối đa mà lease hoặc credential có thể tồn tại, kể cả khi được renew. |
| Revoke | Yêu cầu backend vô hiệu hóa credential hoặc kết thúc lease. |
| Expiry | Thời điểm hết hạn; secret manager có thể kích hoạt thu hồi hoặc backend tự hết hiệu lực. |

Một luồng cơ bản:

~~~text
Workload xác thực với Secret Manager
              |
              v
Yêu cầu credential theo role
              |
              v
Secret Engine tạo credential tại backend
              |
              v
Trả credential + lease metadata
              |
              v
Workload sử dụng trong phạm vi TTL
              |
        +-----+------+
        |            |
        v            v
      Renew        Revoke
        |            |
        v            v
  TTL được kéo dài  Backend vô hiệu hóa
  trong giới hạn     credential
~~~

Không phải mọi backend đều có hành vi giống nhau. Có backend tạo tài khoản và xóa tài khoản khi revoke; có dịch vụ cấp credential tự hết hạn; có dịch vụ cần thêm thao tác policy hoặc session invalidation. Vì vậy, cần kiểm tra chính xác ý nghĩa của TTL, renew và revoke trong loại secrets engine đang dùng.

TTL ngắn làm giảm thời gian credential có thể bị lạm dụng sau khi bị lộ, nhưng TTL quá ngắn có thể gây gián đoạn nếu ứng dụng không kịp cấp mới hoặc kết nối chưa được làm mới. Hãy chọn TTL dựa trên thời gian xử lý, độ trễ cấp phát, khả năng renew, tải backend và mức độ rủi ro.

## 4. Dynamic secret cho cơ sở dữ liệu

Một trường hợp phổ biến là tạo tài khoản database riêng cho từng ứng dụng hoặc workload. Secret manager kết nối database bằng tài khoản quản trị được giới hạn quyền tạo và thu hồi user. Khi ứng dụng yêu cầu credential cho role **orders-readonly**, engine tạo username/password mới và cấp quyền đọc phù hợp.

Ví dụ về quy trình:

1. Ứng dụng xác thực với secret manager bằng workload identity.
2. Ứng dụng yêu cầu credential theo role **orders-readonly**.
3. Database secrets engine tạo tài khoản ngẫu nhiên, gán quyền chỉ đọc schema cần thiết và thiết lập TTL.
4. Secret manager trả username, password, lease ID và thời hạn.
5. Ứng dụng dùng credential để tạo kết nối database.
6. Trước khi lease hết hạn, ứng dụng renew hoặc lấy credential mới theo chính sách.
7. Khi không còn cần, ứng dụng đóng pool kết nối và revoke lease; nếu không, backend xử lý theo cơ chế hết hạn đã cấu hình.

Ví dụ quyền:

| Role | Quyền DB | TTL định hướng |
|---|---|---|
| orders-readonly | SELECT trên schema đơn hàng. | 30 phút |
| reporting-reader | SELECT trên các view báo cáo. | 1 giờ |
| migration-writer | DDL/DML cần thiết cho tác vụ migration. | 10 phút, cấp theo đợt triển khai |

Các TTL trong bảng chỉ minh họa cách phân loại; thời hạn thực tế phải dựa trên thời gian tác vụ và chính sách của tổ chức. Không cấp quyền quản trị toàn database chỉ vì secret được dùng trong thời gian ngắn.

### Những điểm phải kiểm soát ở backend database

- Tài khoản mà secret engine dùng để tạo user chỉ có các quyền quản trị tối thiểu cần thiết.
- Template tạo user không được cấp quyền rộng hơn role đã phê duyệt.
- Tên user phải duy nhất để việc revoke không ảnh hưởng credential khác.
- Có xử lý khi tạo user thành công nhưng secret manager không nhận được phản hồi hoặc không lưu lease.
- Có kiểm tra tài khoản mồ côi nếu thao tác revoke thất bại.
- Cần hiểu backend có xóa user ngay khi revoke hay chỉ thu hồi quyền, đổi mật khẩu hoặc chờ kết thúc session.

Một số database không cho phép xóa user đang có session hoặc có thể giữ kết nối hiện hữu sau khi credential hết hạn. Vì vậy, ứng dụng cần đóng hoặc drain connection pool trước thời điểm hết hạn, và quản trị viên cần có quy trình phát hiện, xử lý user còn tồn tại ngoài dự kiến.

## 5. Dynamic secret cho cloud và API

Cloud provider có thể cấp thông tin xác thực tạm thời gắn với một role hoặc session. Workload yêu cầu quyền theo danh tính đã xác thực; hệ thống cấp credential có thời hạn, phạm vi policy và thông tin session. Khi hết hạn, credential không còn được chấp nhận theo cơ chế của dịch vụ.

Ví dụ, một worker xử lý báo cáo chỉ cần đọc object trong một bucket. Thay vì lưu access key dài hạn trong cấu hình, worker nhận session credential có quyền đọc đúng bucket và tồn tại trong thời gian chạy tác vụ.

Các thuộc tính cần xem xét:

- **Role/session policy:** giới hạn tài nguyên và hành động được phép.
- **Session duration:** thời hạn credential, có thể chịu giới hạn của role hoặc dịch vụ.
- **Session identity:** gắn credential với workload, người gọi hoặc mục đích cụ thể.
- **Revocation behavior:** một số credential chỉ tự hết hạn; một số nền tảng có cơ chế vô hiệu hóa phiên hoặc chặn session thông qua policy.
- **Audit trail:** ghi nhận principal, role, session name, thời gian và thao tác thực hiện.

Không được cho rằng mọi cloud credential đều có thể revoke tức thì chỉ bằng cách xóa lease trong secret manager. Cần xác minh hành vi của provider và dịch vụ đích. Khi backend chỉ bảo đảm hết hạn theo TTL, ứng dụng phải coi thời điểm đó là ranh giới cuối cùng và không tiếp tục dùng credential sau khi hết hạn.

## 6. Dynamic secret cho chứng thư và PKI

Một PKI engine có thể cấp chứng thư theo yêu cầu với thời hạn ngắn. Ví dụ, một service yêu cầu chứng thư TLS client cho danh tính **billing-worker**, dùng để xác thực mTLS với dịch vụ nội bộ.

Quy trình thường gồm:

1. Workload xác thực với CA hoặc secret manager.
2. Workload yêu cầu chứng thư theo role có giới hạn Subject, SAN, key usage và TTL.
3. CA phát hành chứng thư và trả certificate cùng metadata cần thiết.
4. Workload nạp chứng thư vào TLS client/server theo cấu hình.
5. Trước khi hết hạn, workload xin chứng thư mới và chuyển kết nối sang chứng thư mới.
6. Chứng thư cũ hết hạn hoặc được thu hồi theo cơ chế PKI.

Chứng thư công khai không phải bí mật; private key tương ứng mới là key material nhạy cảm. Tùy thiết kế, private key có thể được sinh ngay trong workload và chỉ gửi CSR tới CA, nhờ đó private key không phải rời khỏi workload. Nếu CA hoặc secret manager sinh và trả cả private key, cần đánh giá rủi ro xuất khóa, kênh truyền và cách lưu trữ.

TTL của chứng thư là thời hạn hiệu lực được ghi trong certificate. Việc revoke chứng thư có thể dựa trên CRL, OCSP hoặc cơ chế kiểm tra trạng thái riêng của hệ thống. Không nên giả định mọi TLS client đều kiểm tra thu hồi theo thời gian thực; phải cấu hình và thử nghiệm hành vi của từng thành phần.

## 7. Xác thực workload trước khi cấp dynamic secret

Secret manager phải xác minh danh tính bên yêu cầu trước khi phát credential. Nếu bất kỳ workload nào cũng có thể yêu cầu secret cho mọi role, dynamic secret chỉ chuyển rủi ro từ mật khẩu tĩnh sang API cấp phát.

Các cơ chế xác thực workload thường gặp:

- Workload identity do nền tảng điều phối cấp, ví dụ danh tính service account trong Kubernetes.
- Cloud identity hoặc instance identity được xác minh bởi nhà cung cấp.
- Chứng thư máy khách dùng mTLS.
- AppRole hoặc cơ chế tương tự cho workload không có danh tính nền tảng phù hợp.
- Token ngắn hạn được cấp bởi một hệ thống xác thực tin cậy.

Sau xác thực, policy cần giới hạn:

- Workload được gọi path hoặc secrets engine nào.
- Workload được yêu cầu role nào.
- Credential được cấp có quyền gì ở backend.
- Có được renew, revoke hoặc tạo nhiều lease đồng thời hay không.
- Credential có được đọc lại sau lần cấp đầu hay chỉ được trả một lần.

Ưu tiên danh tính workload thay cho token tĩnh nhúng trong image hoặc source code. Nếu buộc phải bootstrap bằng một bí mật ban đầu, bí mật đó cũng cần TTL, quyền tối thiểu, quy trình xoay vòng và giám sát riêng.

## 8. Tích hợp dynamic secret trong ứng dụng Java

Ứng dụng Java nên lấy credential ngay trước khi cần, dùng trong phạm vi lease và quản lý kết nối theo thời hạn. Không nên ghi credential vào file cấu hình lâu dài, commit vào source code hoặc đưa vào log.

Một hợp đồng adapter có thể trừu tượng hóa secret manager:

~~~java
import java.time.Instant;
import java.time.Duration;

public interface DynamicCredentialProvider {
    CredentialLease issue(String role) throws Exception;
}

public interface CredentialLease extends AutoCloseable {
    String username();
    char[] password();
    Instant expiresAt();
    void renew(Duration extension) throws Exception;
    void revoke() throws Exception;
    @Override
    void close() throws Exception;
}
~~~

Đây là giao diện minh họa do ứng dụng định nghĩa, không phải API chuẩn của JDK. Adapter cụ thể sẽ gọi Vault, cloud secrets service hoặc nền tảng cấp phát tương ứng. Trong hợp đồng minh họa này, **revoke()** yêu cầu backend thu hồi credential, còn **close()** giải phóng tài nguyên và buffer cục bộ của đối tượng lease. Đối tượng lease cần che giấu credential khỏi log và chỉ cung cấp dữ liệu cho thành phần cần thiết.

Ví dụ luồng dùng credential với một tác vụ ngắn:

~~~java
CredentialLease lease = provider.issue("orders-readonly");
char[] password = null;

try {
    password = lease.password();
    ManagedDataSource dataSource = dataSourceFactory.create(
            lease.username(), password);
    try {
        runReadOnlyQuery(dataSource);
    } finally {
        dataSource.close();
    }
} finally {
    if (password != null) {
        java.util.Arrays.fill(password, '\0');
    }
    try {
        lease.revoke();
    } finally {
        lease.close();
    }
}
~~~

Đây là mã minh họa: **ManagedDataSource**, **dataSourceFactory** và **runReadOnlyQuery** là thành phần do ứng dụng định nghĩa. Ví dụ giả định tác vụ hoàn tất trước khi lease hết hạn và DataSource có thể đóng ngay. Cấu trúc finally lồng nhau bảo đảm tài nguyên cục bộ vẫn được đóng nếu thao tác revoke thất bại. Trong ứng dụng dùng connection pool lâu dài, không revoke ngay sau khi lấy credential: cần giữ lease manager, renew trước thời điểm hết hạn hoặc cấp credential mới, chuyển pool sang credential mới, drain pool cũ rồi revoke lease cũ.

### Quản lý connection pool

Credential hết hạn có thể khiến kết nối mới thất bại, trong khi kết nối đã xác thực có thể vẫn tồn tại tùy database và cấu hình. Không dựa vào giả định rằng TTL tự đóng mọi session. Một chiến lược an toàn cho pool:

1. Theo dõi thời điểm hết hạn do server trả về và thời điểm renew sớm hơn một khoảng dự phòng.
2. Nếu renew được phép, cập nhật lease expiry theo phản hồi backend.
3. Nếu không renew được hoặc gần maximum TTL, yêu cầu credential mới.
4. Tạo pool mới và kiểm tra kết nối với credential mới.
5. Chuyển request mới sang pool mới.
6. Drain và đóng pool cũ trước khi revoke credential cũ.
7. Nếu cấp credential mới thất bại, áp dụng retry có giới hạn và cảnh báo; không tiếp tục dùng credential đã hết hạn.

Không để nhiều instance đồng thời tạo credential mới không kiểm soát. Dùng cơ chế phối hợp hoặc cache theo workload/role phù hợp để tránh tạo quá nhiều tài khoản tạm thời và gây tải lên database.

## 9. Bảo vệ credential sau khi được cấp

Dynamic secret thường được trả rõ trong phản hồi cấp phát và không nên dựa vào khả năng đọc lại sau đó. Nếu bị log hoặc ghi vào nơi lưu trữ lâu dài, lợi ích của TTL giảm đáng kể. Cần áp dụng các kiểm soát:

- Chỉ giữ credential trong bộ nhớ của tiến trình cần sử dụng.
- Không ghi username/password, token, private key hoặc response đầy đủ vào log, trace, metric label hay exception.
- Không truyền secret qua query string hoặc URL có thể bị ghi lại.
- Bảo vệ TLS và xác minh danh tính server của secret manager.
- Hạn chế quyền đọc bộ nhớ, dump JVM, heap dump và diagnostic artifact.
- Tránh đặt secret trong biến môi trường tồn tại lâu nếu có lựa chọn cấp phát trực tiếp hoặc file tạm trong vùng nhớ được bảo vệ.
- Giới hạn quyền truy cập file nếu phải dùng file, và xóa file sau khi ứng dụng không còn cần.
- Không chia sẻ một dynamic credential giữa các workload độc lập nếu có thể cấp riêng.

Metadata như lease ID, role, TTL và key version thường không phải key material, nhưng có thể nhạy cảm về vận hành. Không đưa metadata có thể dùng để thu hồi hoặc truy vấn secret vào log công khai.

## 10. Gia hạn, cấp mới và thu hồi an toàn

Ứng dụng cần coi lease là tài nguyên có vòng đời. Việc lấy secret thành công chỉ là bước đầu; ứng dụng phải biết credential còn hiệu lực bao lâu và điều gì xảy ra khi không thể renew.

### Lập lịch renew

- Bắt đầu renew trước expiry với khoảng dự phòng đủ cho độ trễ mạng và tải backend.
- Dùng thời gian hết hạn do server trả về, không tự suy ra từ TTL mặc định.
- Tôn trọng maximum TTL và giới hạn renew của role.
- Tránh renew quá sát thời điểm hết hạn hoặc lặp liên tục khi backend đang lỗi.
- Dùng exponential backoff có giới hạn và jitter cho lỗi tạm thời.
- Nếu renew bị từ chối vì lease đã hết hạn, lấy credential mới nếu workload vẫn được phép.

### Revoke khi kết thúc

Khi tác vụ hoặc workload kết thúc, ứng dụng nên đóng tài nguyên phụ thuộc rồi revoke lease nếu quy trình yêu cầu. Revoke có thể thất bại do backend không khả dụng; khi đó cần ghi nhận sự kiện, retry theo chính sách và dựa vào TTL như giới hạn tồn tại cuối cùng nếu backend hỗ trợ expiry. Không được coi lời gọi revoke thất bại là đã thu hồi thành công.

### Xử lý credential bị lộ

Nếu credential động bị lộ:

1. Xác định lease, role, backend và tài nguyên mà credential có thể truy cập.
2. Revoke lease hoặc vô hiệu hóa credential trực tiếp ở backend nếu cần khẩn cấp.
3. Xác minh backend đã áp dụng thay đổi; kiểm tra session hoặc connection còn tồn tại.
4. Cấp credential mới cho workload hợp lệ và rà soát quyền của role.
5. Điều tra log truy cập, phạm vi dữ liệu và khả năng credential đã bị dùng trái phép.
6. Kiểm tra secret manager có tạo credential mồ côi hoặc lease không còn được theo dõi hay không.

## 11. Rủi ro và cách kiểm soát

| Rủi ro | Tác động | Kiểm soát |
|---|---|---|
| Workload xác thực quá rộng | Ứng dụng có thể xin credential cho role không thuộc phạm vi. | Ràng buộc identity với role/path cụ thể; least privilege và kiểm thử policy. |
| Credential có quyền backend quá lớn | Credential ngắn hạn vẫn có thể gây thiệt hại lớn trong TTL. | Giới hạn quyền DB/cloud/PKI theo nhiệm vụ; không cấp quyền quản trị mặc định. |
| Lease không được renew kịp | Request hoặc kết nối mới thất bại. | Renew sớm, theo dõi expiry, cấp mới và chuyển pool có kiểm soát. |
| Revoke thất bại | Credential có thể còn hiệu lực đến khi backend tự hết hạn hoặc được xử lý. | Cảnh báo, retry, kiểm tra trạng thái backend và quy trình thu hồi khẩn cấp. |
| Tạo credential thành công nhưng mất phản hồi | Có thể xuất hiện user/token mồ côi mà ứng dụng không biết lease ID. | Dùng backend cleanup, idempotency nếu hỗ trợ, kiểm tra tài khoản mồ côi và giới hạn số lượng. |
| Lộ secret qua log hoặc heap dump | Kẻ tấn công có thể dùng credential trong thời gian còn hiệu lực. | Redaction, kiểm soát dump, quyền đọc log, TLS và giảm thời gian lưu trong bộ nhớ. |
| TTL quá ngắn | Tăng số lần cấp phát và nguy cơ gián đoạn. | Đo thời gian tác vụ, latency backend và chọn TTL có dự phòng. |
| TTL quá dài | Tăng cửa sổ lạm dụng khi secret bị lộ. | Phân loại role, đặt TTL phù hợp và giới hạn maximum TTL. |
| Credential dùng chung giữa nhiều ứng dụng | Khó truy vết và thu hồi riêng từng workload. | Cấp credential riêng theo workload hoặc phiên khi khả thi. |
| Backend không hỗ trợ revoke tức thì | Xóa lease không chắc đã chặn credential ngay. | Hiểu semantics backend, dùng TTL ngắn và kiểm tra session/policy riêng. |

## 12. Giám sát và kiểm toán

Một hệ thống dynamic secret cần theo dõi cả hoạt động cấp phát lẫn vòng đời:

- Số lượng credential được cấp theo role, workload và backend.
- Tỷ lệ cấp phát thành công/thất bại và độ trễ.
- Lease sắp hết hạn, renew thất bại và số lần retry.
- Revoke thành công/thất bại và thời gian backend hoàn tất.
- Số credential tồn tại vượt quá dự kiến hoặc tài khoản mồ côi.
- Số lượng credential đang hoạt động theo role và mức sử dụng so với quota.
- Thay đổi policy, role, TTL, maximum TTL và quyền của secrets engine.

Audit event nên ghi principal yêu cầu, role/path, lease ID hoặc định danh đã che phù hợp, thời điểm, hành động, backend và kết quả. Không ghi giá trị secret. Log phải được bảo vệ khỏi sửa đổi và chỉ cấp cho người có nhiệm vụ điều tra.

Đặt cảnh báo cho các tình huống như một workload yêu cầu nhiều lease bất thường, role nhạy cảm được gọi từ danh tính lạ, renew liên tục thất bại, revoke không hoàn tất hoặc credential tồn tại lâu hơn maximum TTL mong đợi.

## 13. Quy trình triển khai dynamic secret

Một lộ trình triển khai có kiểm soát có thể thực hiện theo các bước:

1. **Chọn use case:** xác định credential nào cần cấp động, chẳng hạn tài khoản DB đọc dữ liệu hoặc cloud session chỉ đọc.
2. **Xác định danh tính workload:** chọn cơ chế xác thực không cần bí mật bootstrap dài hạn nếu nền tảng hỗ trợ.
3. **Thiết kế role:** xác định quyền backend nhỏ nhất, TTL, maximum TTL và khả năng renew/revoke.
4. **Cấu hình backend:** cấp quyền cho secrets engine đủ để tạo và thu hồi credential; bảo vệ tài khoản quản trị của engine.
5. **Tích hợp ứng dụng:** lấy secret theo yêu cầu, giữ trong bộ nhớ, theo dõi lease và xử lý pool/kết nối.
6. **Kiểm thử vòng đời:** kiểm tra issue, renew, expiry, revoke, backend outage, mất phản hồi và credential mồ côi.
7. **Triển khai có giám sát:** bắt đầu với workload giới hạn, theo dõi latency, lỗi, quota và hành vi backend.
8. **Rà soát định kỳ:** giảm quyền, điều chỉnh TTL, loại role không dùng và kiểm tra audit trail.

Không nên chuyển tất cả credential sang dynamic secret cùng lúc nếu ứng dụng chưa có khả năng xử lý renew, hết hạn và cấp mới. Hãy bắt đầu từ một use case có ranh giới rõ, chứng minh được revoke và recovery, rồi mở rộng theo mức độ sẵn sàng.

## 14. Checklist vận hành

- [ ] Mỗi workload xác thực bằng danh tính riêng và chỉ được gọi role cần thiết.
- [ ] Credential được tạo theo yêu cầu, có quyền tối thiểu và có TTL rõ ràng.
- [ ] Maximum TTL và chính sách renew được cấu hình.
- [ ] Backend có cơ chế expiry/revoke đã được kiểm chứng.
- [ ] Ứng dụng theo dõi lease và xử lý cấp mới trước khi credential hết hạn.
- [ ] Connection pool hoặc session phụ thuộc được drain khi thay credential.
- [ ] Credential và metadata nhạy cảm không xuất hiện trong log, trace hoặc dump không được bảo vệ.
- [ ] Có retry, cảnh báo và quy trình xử lý revoke thất bại.
- [ ] Có kiểm tra tài khoản/token mồ côi và quota backend.
- [ ] Có audit trail cho issue, renew, revoke, policy change và truy cập backend.
- [ ] Có quy trình xử lý sự cố khi credential bị lộ.
- [ ] Đã kiểm thử backend outage, expiry, rotation và khôi phục trên môi trường tương đương sản xuất.

Dynamic secret giúp giảm việc dùng credential dài hạn và tạo khả năng cấp phát theo đúng nhu cầu của từng workload. Hiệu quả bảo mật đến từ sự kết hợp giữa danh tính workload đáng tin cậy, quyền backend tối thiểu, lease được quản lý đúng, thu hồi có kiểm chứng và giám sát liên tục. Khi tích hợp vào vòng đời quản lý khóa, cần giữ rõ ranh giới giữa credential động và cryptographic key để mỗi loại tài sản được bảo vệ bằng chính sách phù hợp.
