# Database password

Database password là bí mật xác thực được dùng cùng tên tài khoản hoặc danh tính dịch vụ để chứng minh quyền kết nối tới hệ quản trị cơ sở dữ liệu (DBMS). Ứng dụng thường lấy credential này từ một nguồn bí mật được kiểm soát rồi dùng nó khi tạo kết nối JDBC hoặc cấu hình connection pool.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, database password là ví dụ điển hình của secret cần được tạo, phân phối, lưu trữ, sử dụng, xoay vòng và thu hồi. Nó có thể được mã hóa khi lưu trong secret manager, nhưng bản thân password là credential xác thực, không phải encryption key. Phân biệt đúng hai loại này giúp thiết kế quyền truy cập, vòng đời và cơ chế bảo vệ phù hợp.

## 1. Database password là gì?

Database password là một phần của thông tin xác thực tài khoản cơ sở dữ liệu. Khi ứng dụng mở kết nối, DBMS kiểm tra danh tính và xác thực credential theo cơ chế mà DBMS hoặc authentication plugin cấu hình.

Ví dụ, một dịch vụ đơn hàng có thể kết nối tới database bằng tài khoản orders_app. Ứng dụng cần:

- Địa chỉ và tên database cần kết nối.
- Tên tài khoản hoặc danh tính dịch vụ.
- Password hoặc cơ chế xác thực tương đương.
- Quyền mạng và cấu hình TLS phù hợp.
- Quyền SQL cần thiết trên schema, bảng, view hoặc stored procedure.

Password chỉ chứng minh credential được trình bày phù hợp với tài khoản. Nó không tự cấp quyền truy cập mọi bảng; quyền thực tế còn phụ thuộc role, grant, policy và cấu hình DBMS.

## 2. Phân biệt database password, secret và encryption key

Các khái niệm có liên quan nhưng không đồng nhất:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Database password | Credential để xác thực tài khoản DB | Mật khẩu của orders_app |
| Secret | Thuật ngữ chung cho dữ liệu nhạy cảm cần kiểm soát truy cập | Database password, API token, private key |
| Encryption key | Vật liệu mật mã dùng để mã hóa/giải mã hoặc thực hiện thao tác mật mã | AES data key, KEK, private key ký |
| Password verifier | Giá trị DBMS lưu để kiểm tra password theo cơ chế xác thực | Verifier có salt/thuật toán của DBMS |
| TLS certificate | Chứng chỉ ràng buộc public key với danh tính máy chủ | Chứng chỉ TLS của database endpoint |

Database password thường được giữ bí mật và có thể được lưu trong secret manager. Secret manager có thể dùng một encryption key do KMS/HSM bảo vệ để mã hóa secret khi lưu trữ. Trong kiến trúc đó, password vẫn là dữ liệu xác thực; encryption key bảo vệ dữ liệu secret tại lớp lưu trữ.

Không dùng database password làm AES key chỉ vì nó là chuỗi bí mật. Password do con người chọn thường có entropy thấp và không có độ dài/định dạng phù hợp với khóa mật mã. Nếu cần tạo encryption key từ passphrase, phải dùng KDF chuyên dụng theo thiết kế riêng.

## 3. Database password được sử dụng trong luồng kết nối

Luồng kết nối phổ biến:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant SM as Secret manager
    participant DB as Database
    App->>SM: Xác thực workload identity và yêu cầu secret
    SM-->>App: Database credential
    App->>DB: Mở kết nối qua TLS
    DB->>DB: Xác thực credential và kiểm tra quyền
    DB-->>App: Chấp nhận hoặc từ chối kết nối
    App->>DB: Thực thi câu lệnh trong phạm vi quyền được cấp
~~~

Secret manager nên xác minh danh tính workload trước khi trả secret. Ứng dụng chỉ nhận credential của database mà nó cần. Kết nối DB cần xác minh chứng chỉ máy chủ và hostname qua TLS để tránh gửi credential tới endpoint giả mạo.

Nếu nền tảng hỗ trợ xác thực bằng danh tính workload, IAM hoặc token ngắn hạn, có thể cân nhắc cơ chế đó để giảm việc quản lý password tĩnh. Dù dùng password hay token, thông tin xác thực vẫn cần phân quyền, giám sát, hết hạn và thu hồi.

## 4. Tạo database password có entropy cao

Với tài khoản dịch vụ, password nên được tạo ngẫu nhiên bằng bộ sinh số ngẫu nhiên mật mã, thay vì chọn theo tên ứng dụng, môi trường, ngày tháng hoặc mẫu dễ đoán. Password dịch vụ thường không cần con người ghi nhớ, vì vậy có thể dài và duy nhất.

Thực hành tốt:

- Sinh password bằng nguồn ngẫu nhiên mật mã của secret manager hoặc nền tảng tin cậy.
- Tạo credential riêng cho từng ứng dụng, môi trường và mục đích.
- Không tái sử dụng password giữa development, staging và production.
- Dùng độ dài và tập ký tự được DBMS, driver và quy trình triển khai hỗ trợ.
- Xác nhận DBMS không cắt ngắn hoặc chuẩn hóa password theo cách không tương thích.
- Lưu password ngay vào secret manager sau khi tạo; chỉ phân phối cho workload được phép.

Không đưa password vào tên tài khoản, hostname, JDBC URL được ghi log hoặc thông tin cấu hình có thể công khai. Không dùng một password mặc định chung cho mọi cài đặt.

## 5. Lưu trữ và phân phối password bằng secret manager

Database password cần được quản lý tập trung hoặc qua cơ chế bí mật phù hợp với nền tảng. Secret manager thường cung cấp:

- Mã hóa secret khi lưu trữ, thường dựa trên KMS/HSM hoặc khóa bảo vệ của nền tảng.
- Xác thực workload và phân quyền theo secret cụ thể.
- Phiên bản secret, lịch sử thay đổi và khả năng thu hồi.
- Audit log cho thao tác đọc, tạo, cập nhật và xóa.
- Cơ chế cấp phát hoặc làm mới secret cho ứng dụng.

Các kiểm soát quan trọng:

1. Cấp quyền đọc secret theo danh tính workload, không theo một credential dùng chung cho cả nhóm.
2. Giới hạn phạm vi secret theo môi trường và ứng dụng.
3. Không cấp quyền quản trị secret manager cho tiến trình chỉ cần đọc password DB.
4. Không ghi password vào log, exception message, metric label, trace hoặc crash report.
5. Hạn chế lưu secret trong file cấu hình, source code, image/container layer và hệ thống quản lý phiên bản.
6. Bảo vệ audit log để người có quyền đọc secret không thể âm thầm xóa dấu vết.

Mã hóa secret khi lưu trữ là cần thiết nhưng chưa đủ. Nếu một workload bị xâm nhập và có quyền đọc password, kẻ tấn công có thể dùng chính quyền đó để lấy credential. Vì vậy, quyền đọc secret phải được giới hạn và giám sát.

## 6. Sử dụng database password trong Java JDBC

Không hardcode password trong source code hoặc commit file cấu hình chứa credential. Ứng dụng nên lấy password từ một abstraction kết nối với secret manager hoặc cơ chế workload identity của môi trường.

Ví dụ dưới đây minh họa việc nạp password qua một interface và truyền credential cho JDBC bằng Properties:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public final class DatabaseConnections {
    public interface SecretProvider {
        String readSecret(String secretId);
    }

    private DatabaseConnections() {
    }

    public static Connection open(
            String jdbcUrl,
            String username,
            SecretProvider secretProvider) throws SQLException {

        Properties credentials = new Properties();
        credentials.setProperty("user", username);
        credentials.setProperty(
                "password",
                secretProvider.readSecret("prod/orders/database-password"));

        try {
            return DriverManager.getConnection(jdbcUrl, credentials);
        } finally {
            credentials.remove("password");
        }
    }
}
~~~

SecretProvider là abstraction do ứng dụng triển khai bằng SDK secret manager hoặc cơ chế cấp credential của nền tảng. Ví dụ không chứa endpoint hay token quản trị của secret manager. JDBC driver thường nhận password dưới dạng String; xóa thuộc tính khỏi Properties giúp bỏ tham chiếu trong object này nhưng không bảo đảm mọi bản sao trong JVM hoặc driver đã được xóa khỏi bộ nhớ.

Trong ứng dụng thực tế, nên dùng DataSource và connection pool được cấu hình từ secret manager. Connection pool có thể giữ credential để tạo kết nối mới; khi password thay đổi, cần cập nhật cấu hình pool và tái tạo hoặc làm mới kết nối theo cơ chế của thư viện. Không ghi Properties, JDBC URL có credential hoặc object cấu hình pool vào log.

## 7. Cấu hình JDBC URL và TLS an toàn

JDBC URL nên chứa thông tin định tuyến và tùy chọn kết nối không bí mật. Đưa username/password trực tiếp vào URL có thể khiến credential xuất hiện trong log, metric, exception, thread dump hoặc trang quản trị.

Ưu tiên truyền credential qua API riêng của driver hoặc DataSource:

~~~java
String jdbcUrl = "jdbc:postgresql://db.internal.example:5432/orders";
Properties properties = new Properties();
properties.setProperty("user", databaseUsername);
properties.setProperty("password", databasePassword);
~~~

Các tùy chọn TLS phụ thuộc DBMS và JDBC driver. Cần cấu hình TLS để mã hóa đường truyền, xác minh chứng chỉ máy chủ và kiểm tra hostname. Chỉ bật mã hóa mà bỏ qua xác minh danh tính máy chủ có thể khiến ứng dụng kết nối tới endpoint giả mạo.

Không tắt certificate validation hoặc hostname verification để khắc phục lỗi kết nối. Hãy cài trust anchor đúng, kiểm tra chain, SAN, thời hạn và cấu hình driver theo tài liệu của DBMS.

## 8. Quyền database gắn với tài khoản dịch vụ

Password mạnh không bù được việc tài khoản có quyền quá rộng. Mỗi ứng dụng nên có danh tính riêng và chỉ nhận quyền SQL cần thiết cho chức năng của nó.

Ví dụ phân tách:

| Tài khoản/role | Quyền điển hình | Mục đích |
|---|---|---|
| orders_app | Đọc/ghi các bảng đơn hàng cần thiết | Runtime của dịch vụ đơn hàng |
| orders_readonly | Chỉ đọc view hoặc bảng được cho phép | Báo cáo hoặc truy vấn phân tích |
| orders_migrator | Quyền DDL cần thiết trong thời gian triển khai | Migration schema có kiểm soát |
| db_admin | Quyền quản trị rộng | Chỉ dành cho DBA hoặc quy trình break-glass |

Không dùng tài khoản root, sa, postgres hoặc tài khoản quản trị tương đương trong cấu hình runtime thông thường. Tài khoản migration nên được tách khỏi tài khoản ứng dụng và chỉ được cấp quyền khi chạy migration.

Nếu nhiều dịch vụ dùng chung một database, tránh dùng chung một username/password. Tách tài khoản giúp thu hồi một dịch vụ mà không làm gián đoạn các dịch vụ khác, đồng thời giúp audit xác định nguồn truy cập.

## 9. Database lưu password như thế nào?

Ứng dụng hoặc JDBC driver cần password gốc để thực hiện cơ chế xác thực với DBMS. Tùy giao thức, password có thể được gửi qua kênh đã bảo vệ hoặc được dùng để tính phản hồi challenge; không nên giả định mọi DBMS đều truyền password theo cùng một cách. DBMS không nên lưu password người dùng ở dạng plaintext. Tùy engine và authentication mechanism, DBMS lưu password verifier hoặc dùng cơ chế challenge-response phù hợp.

Một password verifier có thể được tạo từ password bằng thuật toán có salt và chi phí tính toán, hoặc theo giao thức xác thực riêng của DBMS. Khi người dùng kết nối, DBMS kiểm tra bằng verifier hoặc challenge mà không cần lưu bản plaintext để đọc lại.

Không tự băm password trước khi gửi cho DBMS trừ khi giao thức xác thực của DBMS quy định chính xác thao tác đó. Nếu ứng dụng gửi một hash tĩnh thay cho password, hash đó có thể trở thành password-equivalent: ai lấy được nó có thể dùng lại để xác thực nếu giao thức chấp nhận.

Không tự quản lý bảng password riêng để thay thế cơ chế xác thực được DBMS hỗ trợ. Dùng authentication plugin/mechanism hiện đại được DBMS duy trì, cấu hình chính sách password và cập nhật phiên bản theo hướng dẫn nhà cung cấp.

## 10. Xoay vòng database password

Rotation là thay credential cũ bằng credential mới theo lịch hoặc khi có sự kiện bảo mật. Với database password, rotation phải phối hợp giữa DBMS, secret manager và mọi ứng dụng đang dùng tài khoản.

Một quy trình an toàn thường gồm:

1. Xác định tài khoản, secret ID, ứng dụng và connection pool phụ thuộc.
2. Tạo password mới ngẫu nhiên và lưu thành phiên bản mới trong secret manager.
3. Cập nhật DBMS để chấp nhận credential mới. Nếu DBMS không hỗ trợ đồng thời hai password cho cùng tài khoản, có thể dùng tài khoản thay thế với quyền tương đương trong giai đoạn chuyển đổi.
4. Cập nhật ứng dụng hoặc connection pool để lấy secret mới.
5. Tạo kết nối mới và kiểm tra truy vấn theo đúng quyền.
6. Drain hoặc đóng dần các kết nối cũ theo kế hoạch; lưu ý phiên đang mở có thể tiếp tục tồn tại sau khi password bị đổi.
7. Thu hồi hoặc vô hiệu hóa credential cũ sau khi xác nhận không còn client phụ thuộc.
8. Kiểm tra log xác thực và ghi lại kết quả rotation.

Không có một thứ tự cập nhật duy nhất phù hợp với mọi DBMS. Cần biết engine có hỗ trợ nhiều credential đồng thời, cách connection pool làm mới kết nối và hành vi của các phiên đã xác thực. Thử nghiệm quy trình trên môi trường staging trước khi áp dụng production.

### Rotation định kỳ và rotation theo sự kiện

Rotation định kỳ giảm thời gian tồn tại của credential, nhưng không thay thế phân quyền tối thiểu hoặc giám sát. Rotation khẩn cấp cần thực hiện khi password bị lộ, nhân sự hoặc workload không còn được phép truy cập, hoặc có dấu hiệu sử dụng bất thường.

Nếu dùng tài khoản DB có password tĩnh trong nhiều ứng dụng, việc rotation có thể phức tạp. Tách credential theo dịch vụ và dùng secret manager giúp thu hẹp phạm vi cập nhật.

## 11. Thu hồi và ứng phó khi password bị lộ

Khi nghi ngờ database password bị lộ:

- Xác định tài khoản, DB instance, secret version và ứng dụng có thể bị ảnh hưởng.
- Vô hiệu hóa hoặc đổi credential theo mức độ khẩn cấp; nếu cần, tạm dừng workload hoặc giới hạn network access.
- Thu hồi phiên hoặc kết nối đang hoạt động theo khả năng DBMS; đổi password không nhất thiết tự ngắt mọi session đã xác thực.
- Rà soát audit log, lịch sử đăng nhập, nguồn IP, câu lệnh và dữ liệu đã truy cập.
- Kiểm tra secret manager, CI/CD, log, dump, ticket và repository để tìm bản sao credential.
- Tạo credential mới, cập nhật ứng dụng và xác minh quyền ở mức tối thiểu.
- Nếu có dấu hiệu truy cập trái phép, đánh giá dữ liệu bị đọc/sửa/xóa và kích hoạt quy trình ứng phó sự cố tương ứng.

Xóa password khỏi secret manager hoặc file cấu hình không làm mất các bản sao đã bị lấy trước đó. Credential bị lộ phải được đổi hoặc thu hồi ở DBMS. Việc đổi database password cũng không tự động mã hóa lại dữ liệu đang lưu trong database; đó là hai bài toán riêng.

## 12. Database password và các cơ chế xác thực thay thế

Password tĩnh không phải lựa chọn duy nhất. Tùy DBMS và nền tảng, có thể dùng:

- **IAM/workload identity authentication:** workload chứng minh danh tính với nền tảng, sau đó nhận quyền kết nối hoặc token ngắn hạn.
- **Kerberos hoặc cơ chế xác thực tập trung:** phù hợp với môi trường doanh nghiệp đã có hạ tầng danh tính.
- **Client certificate/mTLS:** chứng minh danh tính client bằng chứng chỉ và private key được quản lý.
- **Short-lived token:** credential có thời hạn ngắn và được cấp tự động.

Các cơ chế này giảm nhu cầu phân phối password tĩnh nhưng vẫn cần bảo vệ private key, token hoặc danh tính workload. Cần đánh giá khả năng hỗ trợ của DBMS, driver, connection pool và môi trường vận hành trước khi chuyển đổi.

Nếu dùng client certificate, private key là key material và cần quy trình quản lý khóa riêng; chứng chỉ và password vẫn là loại credential khác nhau. Không coi việc chuyển từ password sang certificate là loại bỏ nhu cầu quản lý bí mật.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Hardcode password trong source code | Credential có thể bị lộ qua repository, fork hoặc artifact | Lấy từ secret manager/workload identity và loại bỏ secret khỏi lịch sử mã nguồn theo quy trình |
| Dùng tài khoản DB admin trong ứng dụng | Ứng dụng bị xâm nhập có quyền phá hoại rộng | Tạo role riêng với quyền tối thiểu |
| Dùng chung password giữa nhiều dịch vụ | Khó khoanh vùng và thu hồi khi có sự cố | Credential riêng theo ứng dụng và môi trường |
| Đưa password vào JDBC URL | Có thể lộ qua log, telemetry hoặc exception | Truyền qua API credential riêng và lọc log |
| Tắt TLS hoặc xác minh chứng chỉ | Credential có thể bị nghe lén hoặc gửi tới endpoint giả | Bật TLS và xác minh chain/hostname |
| Lưu password plaintext trong DB hoặc file cấu hình | Người đọc file có thể dùng ngay credential | Dùng secret manager; DBMS lưu verifier theo cơ chế xác thực |
| Chỉ đổi secret manager mà quên DBMS | Secret mới không đăng nhập được hoặc app tiếp tục dùng credential cũ | Đồng bộ cập nhật DBMS, secret và connection pool |
| Chỉ đổi password mà không xử lý session cũ | Phiên đã xác thực có thể tiếp tục hoạt động | Kiểm tra và thu hồi session theo chính sách |
| Không theo dõi secret access | Khó phát hiện đọc hoặc sử dụng bất thường | Bật audit log và cảnh báo theo danh tính/nguồn |
| Dùng password làm encryption key | Khóa yếu hoặc sai định dạng, trộn lẫn hai mục đích | Dùng khóa ngẫu nhiên hoặc KDF phù hợp cho mã hóa |

## 14. Checklist vận hành database password

- [ ] Mỗi ứng dụng và môi trường có credential riêng.
- [ ] Password dịch vụ được sinh ngẫu nhiên, đủ dài và không tái sử dụng.
- [ ] Secret được lưu trong secret manager hoặc cơ chế tương đương có phân quyền và audit.
- [ ] Workload chỉ có quyền đọc đúng secret cần thiết.
- [ ] Không hardcode, commit, log hoặc đưa password vào JDBC URL.
- [ ] Dùng TLS và xác minh chứng chỉ/hostname của database endpoint.
- [ ] Tài khoản runtime chỉ có quyền SQL tối thiểu; tách quyền migration và admin.
- [ ] Connection pool có quy trình nạp lại credential và drain kết nối khi rotation.
- [ ] Có quy trình đổi password định kỳ và khẩn cấp đã được kiểm thử.
- [ ] Có khả năng vô hiệu hóa credential và xử lý session khi bị lộ.
- [ ] Theo dõi truy cập secret, đăng nhập DB và hoạt động SQL bất thường.
- [ ] Đánh giá IAM, workload identity hoặc token ngắn hạn khi DBMS hỗ trợ.

Database password là credential có thể mở đường tới dữ liệu quan trọng, nên phải được quản lý như một secret có quyền truy cập rõ ràng và vòng đời đầy đủ. Bảo vệ tốt đòi hỏi kết hợp password có entropy cao, secret manager, TLS, tài khoản riêng với quyền tối thiểu, rotation có kiểm soát và khả năng thu hồi nhanh khi có sự cố.
