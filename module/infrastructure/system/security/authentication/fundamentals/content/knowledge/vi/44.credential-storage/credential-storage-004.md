# Database access (Truy cập cơ sở dữ liệu bằng credential an toàn)

> **Chương:** Lưu trữ credential  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Thiết kế cách ứng dụng và workload xác thực với database; cấp phát, lưu trữ, truy xuất, sử dụng, xoay vòng và thu hồi DB credential; ưu tiên workload identity hoặc credential ngắn hạn khi nền tảng hỗ trợ; giới hạn quyền theo vai trò; bảo vệ kết nối bằng TLS; vận hành an toàn với secret manager, JDBC, connection pool, migration, backup và quy trình ứng phó khi secret bị lộ.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt credential truy cập database với password của người dùng cuối được lưu trong ứng dụng.
2. Xác định các loại principal cần kết nối database: runtime application, migration, reporting, backup, DBA và workload.
3. Mô hình hóa trust boundary giữa workload, secret manager, database, network, CI/CD và operator.
4. Chọn phương thức xác thực phù hợp: managed identity, IAM database authentication, certificate, Kerberos hoặc password credential.
5. Lưu trữ và phân phối DB secret qua secret manager hoặc cơ chế bảo vệ tương đương, không hardcode vào source/image.
6. Thiết kế database role theo least privilege, tách runtime khỏi migration và administrative access.
7. Bảo vệ kết nối bằng TLS và xác minh server identity; hiểu khác biệt giữa mã hóa transport và client authentication.
8. Triển khai lấy credential lúc runtime trong Java/Spring/JDBC mà không ghi secret vào log.
9. Xử lý rotation, dynamic credential, connection pool, token expiry và revocation.
10. Kiểm thử credential lifecycle, quyền database, backup/restore, audit và incident response.

## 1. Database access là gì?

**Database access** là quá trình một ứng dụng, service, worker hoặc operator chứng minh danh tính với hệ quản trị cơ sở dữ liệu (DBMS) để mở kết nối và thực hiện thao tác được cấp quyền.

Ví dụ:

- Learning API kết nối PostgreSQL để đọc và cập nhật hồ sơ học tập.
- Enrollment Service ghi nhận đăng ký khóa học.
- Reporting Worker đọc dữ liệu để tạo báo cáo.
- Migration Job thay đổi schema khi phát hành phiên bản.
- Backup Agent tạo bản sao lưu theo lịch.
- DBA thực hiện bảo trì có kiểm soát.

Mỗi thành phần có mục đích và mức quyền khác nhau. Nếu mọi workload đều dùng chung một tài khoản database có quyền owner hoặc administrator, một lỗi ở bất kỳ service nào cũng có thể dẫn tới ảnh hưởng toàn bộ dữ liệu.

### Credential truy cập DB là gì?

Credential có thể là:

- Username và password của database role.
- Certificate và private key dùng cho client certificate authentication.
- Kerberos ticket hoặc service principal.
- Token ngắn hạn do cloud IAM hoặc database authentication service cấp.
- Managed workload identity được DB provider xác minh.
- Secret/key theo cơ chế riêng của DBMS.

Credential chứng minh caller có quyền sử dụng một database principal. Sau khi xác thực, DBMS vẫn cần kiểm tra role, schema, table, view, procedure và quyền thực hiện câu lệnh.

### Xác thực khác authorization

- **Authentication:** DBMS xác minh principal nào đang kết nối.
- **Authorization:** DBMS quyết định principal được phép thực hiện thao tác nào.
- **Network control:** giới hạn nguồn nào có thể kết nối tới DB endpoint.
- **Transport security:** bảo vệ dữ liệu trên đường truyền và xác minh server.
- **Application authorization:** kiểm tra user, tenant và nghiệp vụ trước khi ứng dụng gửi câu lệnh.

Không được coi việc request đến từ subnet nội bộ là bằng chứng danh tính database.

## 2. Phân biệt DB credential với password người dùng cuối

Hai loại credential này thường cùng xuất hiện trong một ứng dụng nhưng có cách lưu trữ khác nhau.

| Loại dữ liệu | Dùng để làm gì? | Cách lưu trữ |
| --- | --- | --- |
| **DB access credential** | Cho application/workload kết nối DB. | Secret manager, managed identity, certificate store hoặc cơ chế cấp credential ngắn hạn. |
| **End-user password** | Cho người dùng đăng nhập ứng dụng. | Password hashing chuyên dụng, salt riêng; không lưu plaintext hoặc reversible encryption. |
| **API access token** | Cho client truy cập resource API. | Token ngắn hạn, audience/scope giới hạn; bảo vệ khi lưu/cache. |
| **DB encryption key** | Mã hóa dữ liệu hoặc backup. | KMS/HSM hoặc key management service, tách khỏi DB credential. |
| **DB signing/TLS private key** | Xác thực server hoặc client theo PKI. | Key store/HSM/secret provider, giới hạn quyền truy cập. |

Password của học viên không phải DB password. Không dùng một giá trị cho cả hai mục đích, không lưu password người dùng bằng cách mã hóa có thể giải ngược chỉ vì ứng dụng cần kiểm tra đăng nhập.

### Ví dụ

Khi học viên đăng nhập Learning Platform:

1. Ứng dụng xác thực password của học viên bằng password hash đã lưu.
2. Application process kết nối PostgreSQL bằng DB identity riêng của Learning API.
3. Query đọc hồ sơ của học viên theo subject và tenant đã xác minh.
4. Database role của Learning API không cần quyền quản trị user hoặc tạo database role.

Database không cần biết password đăng nhập của học viên. Ứng dụng cũng không nên dùng DB administrator credential để thực hiện truy vấn thường ngày.

## 3. Các principal cần tách riêng

Một hệ thống production thường có nhiều loại database principal:

| Principal | Mục đích | Quyền gợi ý |
| --- | --- | --- |
| Application runtime | Phục vụ request của ứng dụng. | Chỉ quyền CRUD/procedure cần thiết trên schema cụ thể. |
| Background worker | Xử lý job hoặc event. | Quyền theo bảng/queue nghiệp vụ mà worker cần. |
| Migration principal | Tạo/đổi schema. | DDL trong thời gian triển khai; chỉ cấp khi migration chạy. |
| Reporting principal | Truy vấn phân tích. | Read-only trên view/schema được phép. |
| Backup principal | Đọc dữ liệu để backup. | Quyền backup chuyên biệt, không dùng account runtime. |
| Monitoring principal | Lấy metrics/health. | Quyền quan sát giới hạn, không đọc dữ liệu nghiệp vụ. |
| DBA/operator | Bảo trì và xử lý sự cố. | Tài khoản cá nhân, MFA/privileged access workflow, audit đầy đủ. |

### Vì sao không dùng chung một account?

- Khó xác định service nào thực hiện query khi có sự cố.
- Không thể thu hồi riêng một workload bị compromise.
- Quyền của account phải đủ cho workload có quyền cao nhất.
- Rotation làm gián đoạn nhiều service cùng lúc.
- Audit không phân biệt được runtime, migration và operator.
- Một lỗi SQL injection trong service có thể khai thác quyền rộng hơn mức cần thiết.

Tách principal giúp giảm blast radius và hỗ trợ điều tra.

## 4. Threat model cho database credential

DB credential có giá trị cao vì nó có thể mở đường trực tiếp tới dữ liệu, schema và đôi khi cả quyền quản trị.

### Tài sản và điểm có thể bị lộ

- Secret manager và policy cấp quyền đọc secret.
- Source code, Git history, CI/CD variables và build logs.
- Container image, VM image và file cấu hình.
- Environment variables, process arguments và crash dump.
- Application logs, tracing, metrics và error report.
- JDBC URL, connection pool và heap dump.
- Backup, snapshot và exported configuration.
- Laptop/operator session hoặc automation runner.
- DB network endpoint và authentication configuration.

### Các threat thường gặp

| Threat | Hậu quả | Kiểm soát trọng tâm |
| --- | --- | --- |
| Hardcoded credential | Secret tồn tại trong source/image và bản sao. | Secret manager, scan repository, rotate khi lộ. |
| Shared DB account | Một workload bị compromise ảnh hưởng nhiều service. | Principal riêng theo service và environment. |
| Overprivileged role | Đọc/xóa/sửa dữ liệu ngoài nhiệm vụ. | Least privilege, schema/table grants. |
| Secret manager overreach | Workload có thể đọc secret của service khác. | Workload identity và secret-level ACL. |
| Network interception | Credential/data bị lộ trên đường truyền. | TLS, server verification và network segmentation. |
| Stale credential | Secret cũ tiếp tục hoạt động sau rotation. | Disable/revoke, overlap có thời hạn và audit. |
| Backup leakage | Secret hoặc dữ liệu DB lộ qua bản sao. | Encryption, access control và retention. |
| SQL injection | Query chạy bằng quyền DB của application. | Parameterized query, validation và DB role hẹp. |
| Runtime memory exposure | Secret bị lộ qua dump/debugging. | Hạn chế dump, process access và secret lifetime. |

### Phân tích theo trust boundary

~~~mermaid
flowchart LR
    W["Application workload"] -->|"Workload identity"| SM["Secret manager / IAM"]
    SM -->|"Short-lived credential"| W
    W -->|"TLS + DB authentication"| DB["Database"]
    CI["CI/CD migration job"] -->|"Deployment identity"| SM
    CI -->|"Migration principal"| DB
    OP["DBA / operator"] -->|"Privileged access workflow"| DB
    DB --> AU["Audit / monitoring"]
    SM --> SA["Secret access audit"]
~~~

Mỗi mũi tên là một ranh giới cần kiểm soát. Đặc biệt, workload chỉ nên đọc secret mà nó cần; CI/CD không nên tự động có quyền truy xuất mọi DB password trong production.

## 5. Chọn phương thức xác thực database

Không có một phương thức phù hợp cho mọi DBMS và môi trường. Ưu tiên cơ chế có danh tính workload và credential ngắn hạn nếu nền tảng hỗ trợ.

| Phương thức | Bằng chứng | Ưu điểm | Điều cần quản lý |
| --- | --- | --- | --- |
| Username/password | Secret gắn với DB role. | Hỗ trợ rộng, dễ tích hợp. | Secret storage, rotation, password policy và leak response. |
| Managed identity / cloud IAM | Danh tính workload do cloud/platform xác minh. | Có thể tránh password tĩnh và cấp token ngắn hạn. | Trust policy, role mapping, token expiry và provider configuration. |
| IAM database authentication | Token tạm thời hoặc signed request theo provider. | Credential có TTL ngắn, gắn với IAM principal. | Clock, token refresh, DB grants và connection lifetime. |
| Client certificate | Certificate và proof of private key. | Có thể gắn workload identity với PKI. | CA, SAN, EKU, key protection, rotation và revocation. |
| Kerberos/GSSAPI | Ticket từ KDC/identity domain. | Tích hợp directory và mutual authentication theo cấu hình. | SPN, realm, keytab hoặc credential cache, clock và ticket lifecycle. |
| Dynamic database secret | Secret riêng được cấp theo lease. | Giảm shared/long-lived credential, hỗ trợ revoke theo lease. | Secret broker, lease renewal, role template và cleanup. |

### Lựa chọn theo môi trường

- Managed cloud database: xem xét IAM/managed identity nếu provider và driver hỗ trợ.
- Kubernetes: workload identity federation hoặc secret agent/CSI có thể cấp credential ngắn hạn.
- On-premises: PKI, Kerberos hoặc secret manager nội bộ có thể phù hợp.
- Legacy database: có thể phải dùng password, nhưng cần account riêng, quyền hẹp, rotation và monitoring.

Không tự giả định một driver hỗ trợ mọi authentication mode. Kiểm tra đúng DBMS version, JDBC driver, cloud provider và runtime.

## 6. Lưu trữ DB secret an toàn

### Secret manager

Secret manager là nơi quản lý secret tập trung với access policy, encryption, versioning, audit và rotation workflow.

Các khả năng cần xem xét:

- Encryption at rest bằng KMS/HSM hoặc key management tương đương.
- TLS khi workload truy xuất secret.
- IAM/ACL theo workload identity và secret path.
- Versioning và rotation.
- Audit ai/ứng dụng nào đọc secret, lúc nào và từ đâu.
- Secret expiry, lease và revoke.
- Replication/availability và disaster recovery.
- Tách quyền quản trị secret khỏi quyền sử dụng secret.

Không phải mọi secret manager đều có cùng guarantee. Cần hiểu backup, recovery, cache, audit retention và behavior khi service không khả dụng.

### Không lưu secret trong source hoặc artifact

Không đặt DB password trong:

- Source code hoặc Git commit.
- Dockerfile hoặc container image layer.
- Helm chart values commit vào repository.
- File cấu hình production được chia sẻ.
- JDBC URL có password.
- Command-line argument.
- Log, exception, trace hoặc metric label.
- Tài liệu onboarding hoặc ticket hỗ trợ.

Nếu secret từng xuất hiện trong Git, xóa dòng trong commit mới không làm mất bản cũ khỏi history/fork/cache. Cần coi secret đã lộ, revoke/rotate và xử lý repository history theo quy trình của tổ chức.

### Environment variable có phải secret manager không?

Environment variable tiện cho injection nhưng không phải kho bí mật hoàn chỉnh. Giá trị có thể lộ qua process inspection, crash dump, diagnostic bundle hoặc công cụ vận hành có quyền cao. Nếu dùng env var:

- Chỉ inject vào process cần thiết.
- Không in toàn bộ environment ra log.
- Giới hạn quyền đọc process và host.
- Tránh truyền qua command line.
- Dùng secret file mount hoặc direct secret-provider integration nếu phù hợp.
- Có rotation/reload strategy rõ.

## 7. Truy xuất secret lúc runtime

Workload cần xác thực với secret manager trước khi đọc DB credential. Không nên để một secret bootstrap có quyền đọc toàn bộ vault nằm trong image.

### Quy trình tham khảo

1. Workload khởi động bằng workload identity do platform cấp.
2. Secret manager xác minh identity, namespace, service account hoặc attestation.
3. Policy cho phép workload đọc đúng secret/lease.
4. Secret manager trả credential và version/expiry.
5. Application tạo DataSource hoặc cập nhật pool.
6. Application không ghi secret vào log hoặc telemetry.
7. Khi secret sắp hết hạn/rotate, workload lấy phiên bản mới và chuyển kết nối.
8. Secret cũ được revoke sau khi overlap hoàn tất.

### Direct retrieval và agent

- **Direct SDK:** ứng dụng gọi secret provider trực tiếp; dễ tích hợp nhưng app chịu trách nhiệm cache, retry và rotation.
- **Sidecar/agent:** agent lấy và làm mới secret rồi cung cấp qua file/socket; cần bảo vệ local channel và quyền file.
- **CSI/secret volume:** nền tảng mount secret; cần kiểm tra file refresh có được ứng dụng nạp lại không.
- **Environment injection:** đơn giản nhưng thường chỉ cập nhật khi restart pod/process.

Chọn một mô hình mà runtime có thể thực sự reload hoặc restart an toàn khi credential đổi.

## 8. Least privilege trong database

Secret được bảo vệ tốt nhưng gắn với role quyền quá rộng vẫn tạo rủi ro lớn. Role runtime chỉ nên có quyền cần cho hoạt động bình thường.

### Ví dụ phân tách quyền

~~~sql
CREATE ROLE learning_api_runtime LOGIN;
GRANT CONNECT ON DATABASE learning TO learning_api_runtime;
GRANT USAGE ON SCHEMA app TO learning_api_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE app.enrollments TO learning_api_runtime;
GRANT SELECT ON TABLE app.courses TO learning_api_runtime;

CREATE ROLE learning_reporting LOGIN;
GRANT CONNECT ON DATABASE learning TO learning_reporting;
GRANT USAGE ON SCHEMA reporting TO learning_reporting;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO learning_reporting;
~~~

Ví dụ mang tính minh họa cho PostgreSQL; cú pháp, quyền sequence, default privileges và schema thực tế cần được điều chỉnh. Không cấp quyền CREATE DATABASE, SUPERUSER hoặc ownership cho application runtime nếu không có yêu cầu được phê duyệt.

### Phân quyền cần xem xét

- CONNECT vào đúng database.
- USAGE trên schema cần thiết.
- SELECT/INSERT/UPDATE/DELETE theo bảng.
- EXECUTE trên stored procedure cụ thể.
- Sequence usage nếu insert cần sequence.
- Quyền view/materialized view.
- Quyền tạm thời cho migration.
- Quyền quản trị tách biệt và có kiểm soát.

### Không dùng quyền để thay thế authorization nghiệp vụ

Database role có thể cho phép SELECT trên bảng enrollments, nhưng ứng dụng vẫn cần lọc theo tenant và subject. Có thể bổ sung row-level security (RLS) nếu DBMS hỗ trợ và kiến trúc phù hợp; cần bảo đảm session context dùng cho RLS không thể bị caller giả mạo.

## 9. Tách runtime, migration và DBA

Một anti-pattern phổ biến là ứng dụng chạy bằng database owner để có thể tự tạo bảng khi khởi động. Điều này làm tăng quyền của mọi request chạy trong process.

### Runtime principal

- Không có DDL nếu không cần.
- Không có quyền tạo role hoặc user.
- Không có quyền đọc secret của service khác.
- Chỉ truy cập schema và thao tác nghiệp vụ cần thiết.
- Quyền được kiểm tra định kỳ.

### Migration principal

- Chỉ dùng trong deployment job hoặc migration window.
- Có quyền DDL cần cho thay đổi schema.
- Không được đưa credential vào runtime application.
- Có approval, audit và rollback plan.
- Sau migration, credential có thể bị revoke hoặc lease kết thúc.

### DBA/operator

- Tài khoản cá nhân, không chia sẻ.
- Privileged access management, MFA và just-in-time elevation khi có.
- Không dùng account DBA trong application configuration.
- Ghi audit thao tác quản trị.
- Break-glass account được kiểm soát, giám sát và rà soát sau sử dụng.

### Ví dụ

Learning API runtime chỉ có SELECT/INSERT/UPDATE trên schema app. Release pipeline lấy migration credential trong thời gian ngắn để chạy DDL. DBA sử dụng tài khoản cá nhân qua privileged access workflow. Ba principal không dùng chung password và không được lưu trong cùng một file cấu hình.

## 10. Bảo vệ kết nối bằng TLS

TLS bảo vệ dữ liệu trên đường truyền và giúp client xác minh database server. Nếu không xác minh server certificate, client có thể mã hóa kết nối tới nhầm endpoint hoặc attacker đứng giữa.

### Các yêu cầu

- Bắt buộc TLS theo policy.
- Xác minh chain tới CA tin cậy.
- Xác minh hostname/SAN của DB endpoint.
- Không dùng trust-all certificate manager.
- Không tắt hostname verification để chữa lỗi cấu hình.
- Dùng protocol/cipher phù hợp với policy hiện hành.
- Cập nhật trust bundle trước khi CA cũ hết hạn.
- Cân nhắc client certificate authentication nếu DBMS hỗ trợ và có PKI lifecycle.

### PostgreSQL JDBC minh họa

~~~text
jdbc:postgresql://db.internal.example:5432/learning?sslmode=verify-full
~~~

Tên host phải khớp certificate; CA certificate phải được cấu hình trong trust material phù hợp với driver/runtime. Không dùng chế độ chỉ mã hóa nhưng bỏ qua xác minh server khi production policy yêu cầu xác thực endpoint.

### TLS không đồng nghĩa mTLS

TLS server authentication xác minh database server với client. Nếu DBMS được cấu hình yêu cầu client certificate và xác minh nó, kết nối có thể dùng mutual TLS/client certificate authentication. Tuy nhiên, TLS có client certificate chưa chắc tự tạo DB role hoặc quyền; DBMS cần mapping certificate identity sang principal và authorization policy.

## 11. JDBC và Java: không hardcode credential

Ứng dụng Java thường tạo DataSource hoặc connection pool để quản lý kết nối. Credential phải đến từ runtime secret provider hoặc workload identity, không nằm trong source.

### Ví dụ với secret provider

~~~java
import javax.sql.DataSource;
import java.util.Arrays;

public final class DatabaseDataSourceFactory {

    private DatabaseDataSourceFactory() {
    }

    public static DataSource create(
            SecretProvider secrets,
            DataSourceBuilder builder
    ) {
        String username = secrets.readString("learning-api/db/username");
        char[] password = secrets.readSecret("learning-api/db/password");

        try {
            return builder
                    .url("jdbc:postgresql://db.internal.example:5432/learning?sslmode=verify-full")
                    .username(username)
                    .password(new String(password))
                    .build();
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Các interface SecretProvider và DataSourceBuilder trong ví dụ là abstraction minh họa, không phải class có sẵn trong JDK. Nhiều JDBC driver và pool cần password dạng String hoặc giữ bản sao nội bộ; xóa mảng char không bảo đảm mọi bản sao đã biến mất. Ưu tiên credential ngắn hạn, giảm thời gian sống trong memory, hạn chế heap dump và bảo vệ process.

### Không log DataSource properties

Không in toàn bộ DataSource configuration, JDBC URL có query chứa secret hoặc exception object có thể chứa credential. Log nên ghi DB host/service alias, principal identifier không nhạy cảm, connection result và correlation ID; không ghi password/token.

### Spring Boot

Cấu hình Spring có thể lấy giá trị từ environment hoặc secret provider integration. Các tên như DB_USERNAME và DB_PASSWORD chỉ là nguồn cấu hình; hệ thống deploy phải inject chúng từ secret manager hoặc workload identity flow, không lưu giá trị thực trong YAML commit.

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal.example:5432/learning?sslmode=verify-full
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      connection-timeout: 3000
      max-lifetime: 1500000
~~~

Đây là cấu hình minh họa cho cách tổ chức tham số. Trong triển khai thực tế, phải cấu hình property source/secret integration để username/password được resolve từ secret provider; không để chuỗi tên biến trở thành credential literal. Điều chỉnh pool size, timeout và lifetime theo DB capacity, latency và rotation policy.

## 12. Connection pool và vòng đời credential

Connection pool giữ sẵn các kết nối đã xác thực để giảm chi phí mở kết nối. Điều này tạo một điểm quan trọng: thay DB password không tự động thay credential của những connection đã mở.

### Hệ quả

- Kết nối cũ có thể tiếp tục hoạt động dù password cũ đã bị disable, tùy DBMS.
- Connection mới có thể thất bại nếu pool vẫn giữ credential cũ.
- Secret manager đã cập nhật nhưng application không reload DataSource.
- Connection pool có thể giữ session/transaction context cũ.
- Rotation thiếu overlap có thể làm gián đoạn request.

### Rotation an toàn

1. Cấp credential hoặc role mới.
2. Cho phép credential mới hoạt động trong thời gian overlap.
3. Cập nhật secret provider/runtime.
4. Tạo pool hoặc connection mới dùng credential mới.
5. Health check xác minh kết nối và quyền.
6. Drain pool cũ, đóng connection cũ và session liên quan theo policy.
7. Revoke credential cũ.
8. Theo dõi lỗi authentication và connection churn.

Nếu DBMS chỉ cho một password active trên mỗi role, có thể cần hai role thay phiên hoặc cơ chế managed auth/token thay vì đổi password tại chỗ rồi hy vọng mọi instance reload cùng lúc.

### HikariCP và lifetime

Pool lifetime phải tương thích với credential TTL và DB/network timeout. Với IAM token ngắn hạn, driver/credential provider cần hỗ trợ lấy token khi tạo connection mới; token hết hạn không nhất thiết làm connection đã xác thực mất hiệu lực ngay. Kiểm tra behavior của DBMS và driver, không giả định token có thể refresh trên connection đang mở.

## 13. Dynamic database credentials và lease

Dynamic credential là credential được cấp riêng theo yêu cầu, thường gắn với lease hoặc TTL. Secret broker có thể tạo database role/password, trả cho workload và thu hồi khi lease hết hạn.

### Lợi ích

- Giảm credential dùng chung giữa nhiều workload.
- Mỗi lease có thể truy vết và revoke riêng.
- Credential có thời hạn, giảm thời gian tồn tại sau khi bị lộ.
- Có thể gắn role template với service identity.
- Hỗ trợ audit ai đã yêu cầu credential.

### Luồng tham khảo

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload
    participant SM as Secret manager
    participant DB as Database
    W->>SM: Authenticate workload identity
    W->>SM: Request credential for role template
    SM->>DB: Create scoped DB principal
    DB-->>SM: Principal created
    SM-->>W: Credential + lease expiry
    W->>DB: TLS connection + DB authentication
    DB-->>W: Session with scoped privileges
    SM->>DB: Revoke principal when lease ends
~~~

### Điều cần quản lý

- Role template chỉ cấp quyền cần thiết.
- Lease TTL đủ cho công việc nhưng không quá dài.
- Renewal và expiry được xử lý trước khi connection mới cần tạo.
- Revoke role phải xử lý session đang mở theo policy.
- Cleanup thất bại phải có retry và reconciliation.
- Không tạo vô hạn role nếu secret broker lỗi.
- Giới hạn số lease đồng thời và audit issuance.

Dynamic credential không thay thế authorization. Nếu role template quá rộng, credential ngắn hạn vẫn có thể gây thiệt hại lớn trong thời gian hiệu lực.

## 14. Rotation và revocation khi dùng password tĩnh

Nếu phải dùng username/password lâu dài, cần quy trình quản lý chặt.

### Rotation

- Có owner cho từng secret.
- Đặt expiry/rotation interval theo risk và khả năng vận hành.
- Hỗ trợ overlap khi có thể.
- Cập nhật secret manager trước hoặc đồng bộ với rollout.
- Xác minh mọi replica đã nạp credential mới.
- Đóng connection cũ nếu cần.
- Thu hồi password cũ sau khi chuyển đổi.
- Theo dõi authentication failure sau rotation.

Không xoay password định kỳ một cách máy móc nếu quy trình tạo downtime hoặc khiến team lưu password trong tài liệu tạm. Ưu tiên credential ngắn hạn và automation có thể kiểm chứng.

### Revocation

Khi secret bị lộ:

- Disable role hoặc rotate password.
- Revoke sessions/connections nếu DBMS hỗ trợ.
- Kiểm tra active connection và transaction.
- Tìm workload/host đã dùng credential.
- Kiểm tra query/audit log trong khoảng thời gian ảnh hưởng.
- Cập nhật secret provider và cache.
- Xác minh credential cũ không thể mở connection mới.
- Kiểm tra backup, image và repository có bản sao secret không.

Xóa secret khỏi một nơi không thu hồi được credential đã bị sao chép.

## 15. Migration, CI/CD và môi trường build

Pipeline triển khai thường cần truy cập database để migration. Đây là ranh giới đặc biệt vì CI runner có thể có quyền rộng và tồn tại ngoài production runtime.

### Kiểm soát

- CI/CD dùng workload identity hoặc short-lived deployment credential.
- Secret chỉ được cấp cho job và environment cụ thể.
- Không đưa production DB password vào build step không cần DB.
- Tách build artifact khỏi deploy/migration credential.
- Approval cho migration có destructive change.
- Migration account riêng với runtime account.
- Không lưu secret trong artifact, test report hoặc pipeline log.
- Hạn chế runner network access tới production DB.
- Thu hồi credential khi job hoàn tất nếu dùng dynamic lease.

### Migration test

Kiểm tra pipeline fail trước khi lấy secret, fail sau khi credential được cấp, timeout khi migration đang chạy và cleanup lease. Có thể cần lock migration để hai deployment không chạy DDL đồng thời.

## 16. Backup, restore và replication

Backup có thể chứa toàn bộ dữ liệu và một số metadata nhạy cảm. Credential dùng cho backup cần được tách khỏi runtime application.

### Backup identity

- Role chuyên dụng chỉ có quyền cần cho backup.
- Credential ngắn hạn hoặc managed identity nếu có.
- Không dùng DBA superuser trừ khi DBMS bắt buộc và đã có kiểm soát.
- Backup encryption key quản lý riêng với DB login credential.
- Destination storage có access policy riêng.
- Audit backup creation, export, restore và download.

### Restore

Restore thường cần quyền cao hơn backup. Hãy dùng job identity riêng, approval và môi trường cô lập. Không cấp credential restore thường trực cho mọi application.

### Replication

Replication account chỉ được phép thực hiện protocol/operation cần thiết. Giới hạn network source, TLS, slot/replication role và monitoring. Nếu credential replication bị lộ, attacker có thể đọc stream dữ liệu rộng hơn một ứng dụng thông thường.

## 17. Network, TLS và database endpoint

DB credential tốt vẫn có thể bị lạm dụng nếu DB endpoint mở rộng hoặc kết nối không được bảo vệ.

### Network controls

- Chỉ mở DB port cho workload/segment cần thiết.
- Private endpoint/VPC/private network nếu phù hợp.
- Security group/network policy theo service identity hoặc subnet quản lý.
- Không expose database trực tiếp ra Internet nếu không có yêu cầu và bảo vệ được phê duyệt.
- Quản lý DNS và endpoint để client xác minh đúng server.
- Hạn chế port-forward/tunnel và ghi audit cho truy cập đặc quyền.

### Network không thay thế authentication

IP allowlist giúp giảm bề mặt kết nối nhưng không chứng minh process nào đang gọi. Workload bị compromise bên trong subnet vẫn có thể tiếp cận DB. Cần kết hợp network segmentation, DB authentication, least privilege và monitoring.

## 18. Monitoring, audit và phát hiện lạm dụng

Database audit cần đủ thông tin để xác định principal và hành động nhưng không làm lộ secret.

### Event hữu ích

- Authentication success/failure.
- Principal, database, source host/address và application name.
- Privilege/role/ownership change.
- DDL và thao tác nhạy cảm.
- Query anomaly, export lớn hoặc access ngoài baseline.
- Connection count và session lifetime.
- Secret retrieval, lease issue/renew/revoke.
- Rotation và deprovision event.
- Backup/restore và replication activity.

### Không ghi

- DB password hoặc IAM token.
- JDBC URL có credential.
- Private key/certificate key material.
- Full connection string nếu chứa secret.
- Sensitive parameter values không cần thiết.
- Heap dump hoặc environment dump không được bảo vệ.

### Alert gợi ý

- Runtime principal thực hiện DDL ngoài lịch.
- Reporting account ghi dữ liệu.
- Một service truy cập schema ngoài allowlist.
- Authentication failure tăng đột biến.
- Một credential được dùng từ workload/host mới.
- Connection count vượt baseline.
- Credential cũ vẫn được dùng sau rotation.
- DBA account đăng nhập ngoài privileged access workflow.
- Secret manager read event bất thường.
- Backup/export lớn ngoài lịch.

## 19. Incident response khi DB credential bị lộ

Phải xử lý cả secret, session đang mở, dữ liệu bị truy cập và các bản sao credential.

### Quy trình

1. **Triage:** xác định DB principal, credential version, secret path, workload, environment và thời gian nghi lộ.
2. **Contain:** disable/revoke credential hoặc role theo mức độ; giới hạn network source nếu cần.
3. **Session control:** tìm connection đang mở và terminate theo policy; xem xét transaction đang chạy.
4. **Rotate:** cấp credential mới qua nguồn provisioning tin cậy.
5. **Deploy:** cập nhật workload, pool và secret cache; xác minh mọi replica đã chuyển.
6. **Audit:** rà soát query, DDL, export, role changes và access theo tenant.
7. **Scope:** kiểm tra secret có nằm trong Git, image, CI log, dump, backup hoặc ticket không.
8. **Recover:** khôi phục dữ liệu/permission nếu bị thay đổi; kiểm tra integrity.
9. **Prevent:** thu hẹp role, sửa secret policy và bổ sung alert/test.
10. **Close:** lưu incident record và xác minh credential cũ không còn được chấp nhận.

Không chỉ đổi password rồi đóng incident. Credential có thể đã được dùng để tạo user khác, grant quyền hoặc exfiltrate dữ liệu.

## 20. Những lỗi triển khai thường gặp

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| DB password trong Git | Lịch sử commit và fork có thể giữ secret. | Revoke/rotate, scan history và dùng secret manager. |
| Một account cho mọi service | Mất attribution, blast radius lớn. | Principal riêng theo workload và môi trường. |
| Runtime là DB owner | SQL injection hoặc lỗi app có quyền DDL/admin. | Runtime role tối thiểu; migration principal riêng. |
| Secret trong JDBC URL | Dễ lộ qua log, process list hoặc exception. | Tách credential khỏi URL và redact cấu hình. |
| Trust-all TLS | Client có thể kết nối nhầm/attacker endpoint. | Verify chain và hostname. |
| Chỉ dùng IP allowlist | Workload nội bộ bị compromise vẫn dùng được DB. | DB authentication và authorization độc lập. |
| Env dump trong log | Secret injection bị lộ. | Redact và hạn chế diagnostics. |
| Rotation không drain pool | Connection cũ tiếp tục hoạt động hoặc pool lỗi. | Reload DataSource, drain và verify. |
| Dynamic secret role không cleanup | Principal mồ côi tích tụ. | Lease, revoke retry và reconciliation. |
| Migration dùng runtime role | Runtime phải giữ quyền DDL. | Migration identity riêng và ngắn hạn. |
| Backup dùng DBA account | Credential backup có quyền quá rộng. | Backup role chuyên dụng. |
| Shared admin password | Không quy trách nhiệm được. | Named accounts và privileged access management. |
| Log query chứa secret | Secret trong SQL literal hoặc connection data bị ghi. | Parameterization, redaction và audit policy. |
| Fail-open khi secret manager lỗi | App có thể dùng credential cũ hoặc bỏ qua kiểm soát. | Define availability policy, TTL và safe startup behavior. |

## 21. Ví dụ thực tế: Learning Platform

Learning Platform có PostgreSQL phục vụ Learning API, Enrollment Service, Reporting Worker và migration pipeline.

### Thiết kế principal

- **learning_api_runtime:** đọc/ghi dữ liệu hồ sơ và enrollment theo schema app.
- **enrollment_runtime:** chỉ có quyền cập nhật enrollment và đọc catalog cần thiết.
- **reporting_readonly:** chỉ đọc reporting views.
- **schema_migrator:** quyền DDL trong deployment job.
- **backup_agent:** quyền backup chuyên dụng.
- **dba_personal:** tài khoản cá nhân qua privileged access workflow.

Mỗi principal có secret/identity riêng và được cấp theo environment. Không có password production chung cho tất cả service.

### Runtime flow

1. Learning API nhận workload identity từ platform.
2. Workload xác thực với secret manager hoặc database IAM provider.
3. Provider cấp credential ngắn hạn hoặc trả secret đúng path.
4. Application tạo DataSource với TLS server verification.
5. PostgreSQL xác thực principal và role.
6. Application kiểm tra subject/tenant rồi thực hiện query parameterized.
7. Connection pool tái sử dụng kết nối trong giới hạn lifetime.
8. Audit ghi principal, database, application name và action cần theo dõi.

### Rotation

Khi credential của Learning API sắp hết hạn:

1. Secret manager cấp version mới.
2. Workload nạp credential và tạo connection mới.
3. Health check xác minh query read-only và quyền cập nhật cần thiết.
4. Pool cũ được drain.
5. Credential cũ bị revoke.
6. Monitoring xác nhận không còn connection mới dùng principal/version cũ.

### Sự cố

Nếu secret của Reporting Worker xuất hiện trong CI log:

- Revoke credential ngay theo incident policy.
- Tạo credential mới với role read-only.
- Kiểm tra CI log, artifact, build cache và access history.
- Rà soát query/export trong thời gian bị ảnh hưởng.
- Xác minh Reporting Worker không có quyền ghi hoặc đọc schema ngoài reporting.
- Bổ sung secret masking và regression test pipeline.

## 22. Kiểm thử database credential lifecycle

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Credential hợp lệ | Kết nối bằng runtime principal đúng. | Kết nối thành công và role đúng. |
| Password sai | Dùng password test không hợp lệ. | DB từ chối; không ghi secret vào log. |
| Principal bị disable | Disable role rồi thử kết nối mới. | Kết nối mới bị từ chối. |
| Secret manager access denied | Workload khác đọc secret của Learning API. | Provider từ chối. |
| Secret manager outage | Ngắt provider trong staging. | Behavior startup/refresh theo policy; không bỏ qua xác thực. |
| Hardcoded secret scan | Scan source, image metadata và config. | Không có production secret. |
| TLS hostname mismatch | Dùng endpoint không khớp certificate. | Client từ chối handshake. |
| CA không tin cậy | Dùng certificate từ CA ngoài trust bundle. | Client từ chối. |
| Plaintext DB connection | Cố kết nối không TLS ở môi trường yêu cầu TLS. | DB/network policy từ chối. |
| Least privilege | Runtime thử CREATE ROLE hoặc DROP TABLE ngoài quyền. | DB từ chối. |
| Reporting read-only | Reporting principal thử INSERT/UPDATE. | DB từ chối. |
| Migration separation | Runtime principal thử DDL. | DB từ chối; migration principal được phép trong job. |
| Cross-schema access | Runtime đọc schema không được cấp. | DB từ chối. |
| SQL injection impact | Dùng test fixture để xác minh quyền sau injection simulation. | Parameterization ngăn injection; DB role giới hạn blast radius. |
| Credential rotation | Chuyển sang secret version mới. | Kết nối mới thành công; pool cũ drain. |
| Old credential revoked | Thử mở connection mới bằng credential cũ. | DB từ chối. |
| Existing session after revoke | Kiểm tra connection đang mở sau revoke. | Hành vi terminate/continue đúng policy đã định nghĩa. |
| Dynamic lease expiry | Để lease hết hạn trong lab. | Credential mới bị từ chối; cleanup được thực hiện. |
| Pool reload | Refresh secret khi ứng dụng đang chạy. | DataSource/pool chuyển đổi không dùng nhầm credential. |
| Concurrent rotation | Nhiều instance cùng rotate. | Không có trạng thái split hoặc downtime ngoài SLA. |
| Migration failure | Job fail giữa chừng. | Credential được cleanup/revoke; schema state được điều tra. |
| Backup identity | Backup role thử query nghiệp vụ không cần thiết. | Quyền bị giới hạn; backup vẫn chạy. |
| Restore identity | User runtime thử restore database. | DB từ chối. |
| DBA audit | Operator dùng named account. | Audit xác định được cá nhân và phiên thao tác. |
| Secret log review | Quét application, proxy, CI và DB logs. | Không có password/token/private key. |
| Credential source attribution | Kết nối từ workload ngoài allowlist. | Network/IAM/DB policy từ chối hoặc cảnh báo. |
| Decommission | Xóa workload và thu hồi principal. | Credential/role không còn dùng được. |

## 23. Checklist triển khai

- [ ] Đã phân biệt DB access credential với end-user password và encryption key.
- [ ] Có principal riêng cho runtime, worker, migration, reporting, backup và DBA.
- [ ] Workload chỉ đọc secret cần thiết từ secret manager.
- [ ] Ưu tiên managed identity hoặc dynamic/short-lived credential nếu hỗ trợ.
- [ ] Không hardcode secret trong source, image, URL, CI artifact hoặc log.
- [ ] Environment variable và secret file có access control, masking và lifecycle rõ.
- [ ] Database role áp dụng least privilege theo schema/table/action.
- [ ] Runtime không dùng DB owner/superuser hoặc migration credential.
- [ ] TLS được bật và client xác minh CA chain cùng hostname.
- [ ] Không có trust-all certificate manager hoặc plaintext fallback.
- [ ] JDBC/DataSource không log password hoặc connection secret.
- [ ] Connection pool có strategy cho credential expiry, reload, drain và rotation.
- [ ] Dynamic lease có TTL, renewal, revoke và cleanup.
- [ ] Migration/CI job có identity riêng, approval và cleanup.
- [ ] Backup/restore/replication có principal và key management riêng.
- [ ] Secret rotation được xác minh trên mọi replica và connection pool.
- [ ] Revocation xử lý credential mới và session/connection đang mở theo policy.
- [ ] Audit theo dõi authentication, role change, secret retrieval và query nhạy cảm.
- [ ] Có incident runbook khi DB credential hoặc secret manager bị compromise.
- [ ] Có kiểm thử least privilege, TLS, rotation, revocation, outage, pool và backup.

## 24. Tự kiểm tra

**Câu 1.** DB access credential khác password của người dùng cuối như thế nào?

**Đáp án:** DB credential xác thực workload hoặc operator với DBMS; end-user password xác thực người dùng với ứng dụng và phải được lưu bằng password hashing chuyên dụng. Hai loại không được dùng chung.

**Câu 2.** Vì sao mỗi service nên có DB principal riêng?

**Đáp án:** Để giới hạn quyền, thu hồi riêng, audit chính xác và giảm blast radius khi một workload bị compromise.

**Câu 3.** Secret manager giải quyết vấn đề gì?

**Đáp án:** Quản lý tập trung secret, encryption, access policy, version, audit, rotation và cấp phát cho workload đã được xác minh.

**Câu 4.** Environment variable có tự động an toàn hơn hardcode không?

**Đáp án:** Không. Nó giảm secret trong source nhưng vẫn có thể lộ qua process inspection, dump hoặc diagnostics. Cần access control và lifecycle; có thể dùng secret agent/file hoặc managed identity.

**Câu 5.** Vì sao runtime role không nên là database owner?

**Đáp án:** Vì mọi lỗi hoặc SQL injection trong ứng dụng có thể thừa hưởng quyền DDL/admin. Runtime chỉ cần quyền nghiệp vụ tối thiểu; migration dùng principal riêng.

**Câu 6.** TLS server verification khác mTLS thế nào?

**Đáp án:** TLS server verification giúp client xác minh database server. mTLS/client certificate authentication còn yêu cầu DB xác minh client certificate theo cấu hình; cả hai vẫn cần DB authorization.

**Câu 7.** Đổi password DB có tự động đóng mọi connection đang mở không?

**Đáp án:** Không nhất thiết. Connection đã xác thực có thể tiếp tục hoạt động tùy DBMS. Cần drain pool, terminate session theo policy và xác minh credential cũ không mở được connection mới.

**Câu 8.** Dynamic credential có loại bỏ nhu cầu least privilege không?

**Đáp án:** Không. Credential ngắn hạn nhưng role template quá rộng vẫn có thể gây thiệt hại lớn trong thời gian lease còn hiệu lực.

**Câu 9.** Có nên dùng cùng credential cho migration và runtime không?

**Đáp án:** Không. Migration cần quyền DDL rộng hơn và chỉ nên được cấp trong deployment job; runtime không nên giữ quyền đó thường trực.

**Câu 10.** Khi DB credential bị lộ, chỉ xóa secret khỏi repository đã đủ chưa?

**Đáp án:** Không. Cần revoke/rotate credential, xử lý session đang mở, kiểm tra Git history, image, CI logs, backup và audit DB để xác định phạm vi ảnh hưởng.

## Ghi nhớ

**Database access** cần một danh tính riêng cho từng workload và mục đích sử dụng. DB credential phải được cấp phát, lưu trữ và truy xuất qua secret manager, managed identity hoặc cơ chế bảo vệ tương đương; database role cần least privilege. Tách runtime khỏi migration, reporting, backup và DBA để giảm blast radius và hỗ trợ audit.

Bảo vệ transport bằng TLS với xác minh server certificate; không hardcode secret hoặc ghi credential vào log. Rotation phải phối hợp secret provider, mọi application replica và connection pool; revoke cần xem xét cả connection đang mở. Dynamic credential giảm thời gian tồn tại của secret nhưng không thay thế authorization. **Một DB connection chỉ nên được mở bằng identity đúng mục đích, trên kênh được xác minh và với quyền tối thiểu cần cho công việc.**
