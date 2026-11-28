# Secret là gì

Trong hệ thống công nghệ thông tin, **secret** là thông tin cần được giữ bí mật vì người biết hoặc sử dụng được nó có thể truy cập tài nguyên, mạo danh một chủ thể, thực hiện thao tác được bảo vệ hoặc làm suy yếu một cơ chế an toàn. Secret có thể là mật khẩu, token truy cập, thông tin xác thực cơ sở dữ liệu, khóa API, khóa ký, khóa mã hóa hoặc bí mật dùng để xác minh webhook.

Secret là một khái niệm rộng hơn **cryptographic key**. Khóa mật mã là một loại secret khi nó cần giữ bí mật, nhưng không phải secret nào cũng là khóa mật mã. Mật khẩu và access token có thể cấp quyền truy cập mà không trực tiếp tham gia phép toán mã hóa. Ngược lại, một public key hoặc chứng chỉ số thường được công khai và không phải secret, dù chúng vẫn cần được xác thực để tránh bị thay thế.

Quản lý secret vì vậy bao gồm việc nhận diện, phân loại, tạo hoặc cấp phát, lưu trữ, phân phối, sử dụng, xoay vòng, thu hồi và hủy. Mục tiêu là chỉ cho đúng thành phần sử dụng đúng secret trong đúng phạm vi và khoảng thời gian cần thiết.

## 1. Secret trong hệ thống là gì?

Một giá trị được xem là secret khi việc tiết lộ nó có thể làm mất một ranh giới bảo mật. Câu hỏi thực tế để nhận diện là: **Nếu người không được phép biết giá trị này, họ có thể làm gì?**

Ví dụ:

- Biết mật khẩu cơ sở dữ liệu có thể cho phép đăng nhập trực tiếp vào database.
- Biết bearer access token có thể cho phép gọi API dưới danh tính của người hoặc dịch vụ được cấp token.
- Biết private key ký số có thể cho phép tạo chữ ký giả mạo chủ thể sở hữu khóa.
- Biết khóa AES có thể cho phép giải mã dữ liệu đã được bảo vệ bằng khóa đó.
- Biết webhook signing secret có thể cho phép tạo thông điệp giả mạo từ hệ thống gửi webhook.
- Biết refresh token có thể cho phép lấy access token mới trong thời gian token còn hiệu lực.

Secret có thể nằm trong tệp cấu hình, biến môi trường, cơ sở dữ liệu, pipeline CI/CD, container image, log, bản sao lưu hoặc bộ nhớ tiến trình. Vị trí lưu không làm thay đổi bản chất của secret; một giá trị vẫn nhạy cảm dù nó xuất hiện trong file YAML, manifest triển khai hay một biến trong mã nguồn.

Không phải mọi dữ liệu nhạy cảm đều là secret. Thông tin cá nhân, dữ liệu tài chính hoặc hồ sơ khách hàng cần được bảo vệ theo chính sách dữ liệu, nhưng việc biết một trường dữ liệu không nhất thiết cấp quyền truy cập hay khả năng giả mạo. Secret là nhóm thông tin có vai trò trực tiếp trong việc duy trì quyền truy cập hoặc một thuộc tính bảo mật.

## 2. Các nhóm secret thường gặp

| Nhóm | Ví dụ | Rủi ro khi bị lộ |
|---|---|---|
| Mật khẩu | Mật khẩu database, tài khoản quản trị, mật khẩu dịch vụ | Đăng nhập trái phép |
| Token | OAuth access token, refresh token, bearer token | Gọi API dưới quyền của chủ thể được cấp token |
| API credential | API key có quyền truy cập, client secret | Mạo danh ứng dụng hoặc vượt giới hạn dịch vụ |
| Khóa mật mã bí mật | AES key, HMAC key, private key | Giải mã, giả mạo chữ ký hoặc tạo MAC hợp lệ |
| Bí mật giao thức | Webhook signing secret, shared secret | Giả mạo thông điệp hoặc bên gửi |
| Thông tin xác thực kết nối | Username/password, connection credential, private key SSH | Truy cập database, máy chủ hoặc dịch vụ khác |
| Bí mật nền tảng | Cloud access key, deployment token, CI/CD credential | Chiếm quyền tài nguyên hoặc pipeline |

Một số tên gọi dễ gây nhầm lẫn. API key có thể chỉ là định danh công khai trong một số thiết kế, nhưng nếu hệ thống dùng nó như bearer credential để cấp quyền thì phải bảo vệ như secret. Client ID thường là định danh và có thể công khai; client secret mới là thông tin xác thực cần giữ bí mật. Cần đánh giá quyền thực tế mà giá trị mang lại thay vì chỉ dựa vào tên trường.

## 3. Secret và cryptographic key khác nhau thế nào?

**Secret** mô tả yêu cầu bảo mật của một giá trị: nó phải được giữ bí mật. **Cryptographic key** mô tả vai trò toán học của vật liệu được thuật toán mật mã sử dụng.

| Tiêu chí | Secret nói chung | Cryptographic key |
|---|---|---|
| Bản chất | Thông tin bí mật có thể cấp quyền hoặc khả năng xác thực | Vật liệu khóa có cấu trúc và mục đích theo thuật toán |
| Ví dụ | Password, API token, database credential, webhook secret | AES key, HMAC key, RSA private key, EC private key |
| Cách sử dụng | Xác thực, cấp quyền, kết nối, ký yêu cầu hoặc cấu hình dịch vụ | Mã hóa, giải mã, ký, xác minh, MAC hoặc thỏa thuận khóa |
| Sinh giá trị | Có thể do hệ thống cấp, người dùng đặt hoặc dịch vụ phát hành | Nên sinh bằng bộ sinh khóa mật mã hoặc KMS/HSM |
| Lưu trữ | Secret manager, vault, kho cấu hình được bảo vệ | KeyStore, KMS, HSM hoặc provider quản lý khóa |
| Vòng đời | Cấp phát, phân phối, xoay vòng, thu hồi, hủy | Tương tự, nhưng còn gắn với thuật toán, key usage, tham số và dữ liệu phụ thuộc |

Một cryptographic key bí mật thường đồng thời là secret. Tuy nhiên, public key không cần giữ bí mật. Chứng chỉ X.509 thường chứa public key và thông tin danh tính; bản thân chứng chỉ có thể được công bố. Private key tương ứng mới là vật liệu phải bảo vệ. IV, nonce và salt cũng thường được lưu công khai, dù phải tuân thủ quy tắc tạo và sử dụng riêng của từng thuật toán.

Vì vậy, không nên gom tất cả dữ liệu nhạy cảm vào một khái niệm “key”. Mỗi loại cần cơ chế phù hợp: mật khẩu cần password hashing, token cần kiểm soát thời hạn và quyền, private key cần kiểm soát thao tác mật mã, còn chứng chỉ cần xác minh chuỗi tin cậy và trạng thái.

## 4. Secret, credential và định danh

Ba khái niệm thường xuất hiện cùng nhau nhưng không đồng nghĩa:

- **Identity:** chủ thể được nhận diện, ví dụ một người dùng, service account, workload hoặc ứng dụng.
- **Credential:** bằng chứng được dùng để chứng minh hoặc thiết lập danh tính, ví dụ password, certificate, token hoặc khóa riêng.
- **Secret:** phần thông tin cần được giữ bí mật để credential hoặc một thao tác được bảo vệ hoạt động an toàn.

Ví dụ, một dịch vụ có thể có identity là orders-service. Nó dùng client ID để nhận diện ứng dụng và client secret để chứng minh quyền sở hữu credential khi lấy token. Sau khi xác thực, dịch vụ nhận access token có phạm vi quyền và thời hạn cụ thể. Client secret và access token đều là secret, nhưng có vòng đời và quyền khác nhau.

Một certificate có thể là credential nhưng không phải toàn bộ certificate đều bí mật. Chứng chỉ thường được gửi cho đối tác; private key dùng để chứng minh quyền sở hữu chứng chỉ mới phải được bảo vệ. Khi đánh giá một credential, hãy xác định phần nào công khai, phần nào bí mật, ai có thể sử dụng và quyền mà nó cấp.

## 5. Phân loại theo quyền và mức độ ảnh hưởng

Không phải secret nào cũng có mức rủi ro như nhau. Có thể phân loại theo quyền mà secret cấp và phạm vi hệ thống bị ảnh hưởng nếu secret bị lộ.

| Mức ảnh hưởng | Ví dụ | Kiểm soát phù hợp |
|---|---|---|
| Thấp, phạm vi hẹp | Token chỉ đọc một tài nguyên thử nghiệm | Thời hạn ngắn, quyền tối thiểu, giới hạn môi trường |
| Trung bình | Credential của một dịch vụ nội bộ | Secret manager, giới hạn workload, audit và rotation |
| Cao | Cloud credential có quyền triển khai hoặc quản trị | Quyền hẹp, cấp phát ngắn hạn, MFA/approval theo chính sách, giám sát |
| Rất cao | Root key, private signing key cấp tổ chức, khóa mã hóa dữ liệu trọng yếu | HSM/KMS, kiểm soát nhiều lớp, phân tách nhiệm vụ, audit chuyên biệt và quy trình khôi phục |

Phân loại phải xét cả quyền trực tiếp và khả năng leo thang. Một token chỉ đọc có thể vẫn nguy hiểm nếu dữ liệu nó đọc chứa credential khác. Một secret có thời hạn dài hoặc được dùng ở nhiều môi trường cũng có thể có blast radius lớn hơn giá trị quyền ghi trên tài liệu.

Mỗi secret nên có chủ sở hữu, mục đích, hệ thống sử dụng, mức ảnh hưởng, thời hạn hoặc điều kiện xoay vòng và quy trình xử lý khi bị lộ.

## 6. Secret management và key management

**Secret management** quản lý nhiều loại bí mật của ứng dụng và hạ tầng, ví dụ password, token, API credential, certificate material và một số khóa. **Key management** tập trung vào vòng đời vật liệu khóa mật mã, gồm sinh khóa, thuật toán, mục đích sử dụng, lưu trữ, phân phối, xoay vòng, thu hồi, sao lưu và hủy.

Hai lĩnh vực giao nhau ở chỗ private key hoặc symmetric key thường cũng là secret. Tuy vậy, key management có thêm các yêu cầu riêng như:

- Thuật toán và độ dài khóa được phép.
- Key usage và giới hạn mục đích.
- Sinh khóa bằng nguồn ngẫu nhiên mật mã.
- Không xuất khóa khi có thể giữ khóa trong HSM.
- Quan hệ giữa khóa và dữ liệu đã mã hóa hoặc chữ ký đã tạo.
- Khả năng khôi phục, chuyển đổi và hủy khóa mà không làm mất dữ liệu cần thiết.

Một secret manager có thể lưu chuỗi credential và cung cấp cơ chế truy cập có kiểm soát. KMS thường cung cấp quản lý khóa và thao tác mật mã qua API. HSM là ranh giới phần cứng bảo vệ khóa và thực hiện thao tác mật mã bên trong thiết bị. Một nền tảng có thể tích hợp cả ba, nhưng chức năng và bảo đảm của chúng không giống nhau.

## 7. Vòng đời quản lý secret

Một quy trình quản lý secret thường gồm các giai đoạn sau:

1. **Khám phá và phân loại:** tìm secret trong ứng dụng, cấu hình, pipeline, kho mã nguồn và môi trường chạy. Gắn chủ sở hữu, mục đích, phạm vi và mức ảnh hưởng.
2. **Tạo hoặc cấp phát:** sinh secret bằng nguồn phù hợp hoặc nhận credential từ nhà cung cấp. Ưu tiên credential ngẫu nhiên và có thể thu hồi; tránh giá trị cố định dùng chung.
3. **Lưu trữ:** đặt secret trong secret manager, vault hoặc vùng lưu trữ được bảo vệ. Không commit vào Git, đóng gói vào image hoặc ghi vào log.
4. **Phân phối:** cấp secret cho đúng workload thông qua cơ chế xác thực đáng tin cậy. Hạn chế việc truyền qua file tạm, command line hoặc kênh không bảo vệ.
5. **Sử dụng:** chỉ đọc khi cần, giới hạn phạm vi và thời gian tồn tại trong bộ nhớ. Không hiển thị secret trong exception, trace hoặc telemetry.
6. **Xoay vòng:** tạo hoặc yêu cầu credential mới, chuyển consumer sang giá trị mới, xác minh hoạt động rồi vô hiệu hóa giá trị cũ.
7. **Thu hồi:** chặn ngay quyền sử dụng khi secret bị lộ, không còn cần thiết hoặc chủ thể không còn được phép truy cập.
8. **Hủy:** xóa secret khỏi kho hoạt động và xử lý bản sao, cache, snapshot, backup hoặc hệ thống phụ thuộc theo chính sách lưu giữ.

Xoay vòng không chỉ là thay giá trị trong secret manager. Consumer có thể cache secret, giữ kết nối cũ hoặc chạy trên nhiều instance. Cần một kế hoạch chuyển đổi có thể quan sát được: phát hành giá trị mới, cho phép giai đoạn chuyển tiếp nếu phù hợp, xác nhận consumer đã cập nhật rồi thu hồi giá trị cũ.

## 8. Lưu trữ secret an toàn

Secret cần được lưu trong hệ thống có kiểm soát truy cập, mã hóa khi lưu và khi truyền, audit và khả năng xoay vòng. Một số lựa chọn phổ biến:

- **Secret manager hoặc vault:** lưu credential, token, chuỗi kết nối và secret cấu hình; thường hỗ trợ policy, version, audit và tích hợp workload identity.
- **KeyStore:** lưu khóa và chứng chỉ theo API Java; hỗ trợ các loại entry khác nhau tùy provider.
- **KMS:** quản lý khóa và thực hiện thao tác mã hóa, giải mã, ký hoặc MAC theo dịch vụ được cung cấp.
- **HSM:** bảo vệ khóa trong phần cứng, hỗ trợ kiểm soát thao tác và hạn chế xuất vật liệu khóa.
- **Secret injection của nền tảng:** đưa secret vào workload khi chạy, với quyền truy cập và vòng đời do nền tảng quản lý.

Các lựa chọn này không thay thế hoàn toàn nhau. Secret manager phù hợp với nhiều loại secret dạng dữ liệu; KMS cung cấp thao tác và quản lý khóa mật mã; HSM tăng cường bảo vệ khóa bằng ranh giới phần cứng. Khi thiết kế, hãy xác định liệu ứng dụng cần đọc giá trị secret hay chỉ cần yêu cầu dịch vụ thực hiện thao tác bằng khóa mà không nhận khóa thô.

Không lưu secret trong mã nguồn, Docker image, file cấu hình được commit hoặc tham số dòng lệnh dễ bị ghi lại. Biến môi trường có thể hữu ích cho một số môi trường triển khai nhưng không phải kho bí mật hoàn hảo: giá trị có thể xuất hiện trong dump tiến trình, công cụ chẩn đoán hoặc cấu hình vận hành. Cần đánh giá đường truyền secret tới tiến trình và quyền của người có thể quan sát môi trường.

## 9. Sử dụng secret trong ứng dụng Java

Ứng dụng Java nên lấy secret từ một abstraction hoặc integration đã được cấu hình với secret manager của nền tảng. Không đặt credential thật trong source code hoặc tệp properties được quản lý cùng mã nguồn.

Ví dụ sau minh họa một giao diện trừu tượng để lấy mật khẩu dưới dạng mảng ký tự. Phần triển khai SecretProvider sẽ kết nối với secret manager hoặc cơ chế cấp phát của môi trường:

~~~java
import java.util.Arrays;

public final class DatabaseCredentialUse {
    public interface SecretProvider {
        char[] readSecret(String secretId);
    }

    private DatabaseCredentialUse() {
    }

    public static void connect(SecretProvider secrets) {
        char[] password = secrets.readSecret("prod/orders/database-password");

        try {
            // Truyền credential tới thành phần kết nối được kiểm soát.
            openDatabaseConnection(password);
        } finally {
            Arrays.fill(password, (char) 0);
        }
    }

    private static void openDatabaseConnection(char[] password) {
        // Phần tích hợp JDBC/connection pool phụ thuộc thư viện triển khai.
        // Không ghi password vào log hoặc exception.
    }
}
~~~

Đây là ví dụ về ranh giới tích hợp, không phải một triển khai secret manager cụ thể. Nếu thư viện JDBC hoặc connection pool chỉ nhận password dưới dạng String, việc chuyển char[] thành String tạo ra một đối tượng bất biến mà ứng dụng không thể chủ động xóa nội dung. Khi đó, hãy giới hạn phạm vi và thời gian sống của String, không log cấu hình kết nối và dùng cơ chế credential provider của nền tảng nếu có.

Với khóa mật mã, nên nhận đối tượng Key hoặc tham chiếu khóa do provider cung cấp thay vì lấy byte khóa thô. Ví dụ, một SecretKey có thể được lấy từ KeyStore bằng SecretKeyEntry rồi truyền trực tiếp cho Mac hoặc Cipher. Với HSM/KMS, ứng dụng có thể yêu cầu thao tác bằng key ID mà không cần xuất khóa.

## 10. Quyền truy cập và nguyên tắc least privilege

Secret chỉ nên được cấp cho workload hoặc người dùng thực sự cần nó. Các nguyên tắc chính:

- **Least privilege:** chỉ cấp quyền tối thiểu, ví dụ chỉ đọc một secret cụ thể thay vì quyền đọc toàn bộ vault.
- **Workload identity:** ưu tiên xác thực workload bằng danh tính nền tảng hoặc cơ chế ngắn hạn thay vì credential tĩnh dùng chung.
- **Tách môi trường:** không dùng chung secret giữa development, staging và production.
- **Tách nhiệm vụ:** người phát hành secret, người phê duyệt quyền và workload sử dụng secret có thể là các vai trò khác nhau.
- **Giới hạn thời gian:** dùng credential ngắn hạn hoặc dynamic secret khi hệ thống hỗ trợ.
- **Audit:** ghi lại ai hoặc workload nào đã truy cập secret, thời điểm, mục đích và kết quả; không ghi giá trị secret.

Không nên cấp quyền dựa trên việc một thành phần biết tên secret hoặc alias. Tên chỉ là định danh; quyền truy cập phải được quyết định bởi policy, danh tính và ngữ cảnh.

## 11. Phát hiện rò rỉ và xử lý sự cố

Secret có thể bị lộ qua commit Git, log, ticket, ảnh chụp màn hình, artifact CI/CD, crash dump, bản sao lưu hoặc máy cá nhân của nhà phát triển. Quy trình xử lý cần có khả năng phản ứng nhanh:

1. Xác định secret nào bị lộ, chủ sở hữu, quyền, thời gian hiệu lực và các hệ thống phụ thuộc.
2. Thu hồi hoặc vô hiệu hóa secret bị lộ. Nếu không thể thu hồi ngay, giảm quyền hoặc chặn đường truy cập.
3. Phát hành secret mới và cập nhật các consumer.
4. Kiểm tra log truy cập, hành vi bất thường và tài nguyên có thể đã bị truy cập.
5. Xử lý bản sao bị lộ trong Git history, artifact, log hoặc backup theo quy trình; xóa file ở nhánh hiện tại không làm secret cũ mất hiệu lực.
6. Đánh giá nguyên nhân và bổ sung secret scanning, policy hoặc kiểm soát phát hành để ngăn tái diễn.

Nếu private key ký số bị lộ, có thể cần thu hồi chứng chỉ và đánh giá các chữ ký được tạo trong khoảng thời gian rủi ro. Nếu khóa mã hóa bị lộ, cần đánh giá dữ liệu đã được bảo vệ bằng khóa đó, khả năng giải mã bản sao lưu và nhu cầu mã hóa lại. Nếu token bị lộ, thu hồi token và các refresh token hoặc session liên quan theo chính sách nhà cung cấp.

Không nên chỉ xóa secret khỏi nơi phát hiện rồi tiếp tục sử dụng. Khi giá trị đã bị tiết lộ, cần coi nó là không còn đáng tin cậy và thực hiện rotation hoặc revocation phù hợp.

## 12. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Coi mọi secret là cryptographic key | Dùng sai cơ chế lưu trữ hoặc API | Phân loại theo bản chất và cách sử dụng |
| Coi public key hoặc certificate là secret | Tạo quy trình phân phối không cần thiết hoặc hiểu sai rủi ro | Phân biệt dữ liệu công khai với private key và trust validation |
| Commit credential vào Git | Secret có thể tồn tại lâu dài trong history và clone | Secret scanning, loại khỏi source và rotation ngay khi lộ |
| Đưa secret vào image hoặc artifact | Mọi nơi lấy artifact đều có thể nhận được secret | Inject secret lúc runtime |
| Dùng một credential ở nhiều môi trường | Rò rỉ một môi trường ảnh hưởng các môi trường khác | Tách secret theo môi trường và workload |
| Cấp quyền đọc toàn bộ vault | Một workload bị chiếm có thể lấy nhiều secret khác | Policy theo secret, identity và mục đích |
| Không xoay vòng hoặc thu hồi | Secret cũ tiếp tục có hiệu lực sau khi không còn an toàn | Lịch rotation, thời hạn và quy trình incident |
| Ghi secret vào log hoặc exception | Hệ thống quan sát trở thành nơi rò rỉ | Redaction và kiểm soát telemetry |
| Xem xóa file là thu hồi secret | Giá trị đã lộ vẫn có thể được sử dụng | Revoke/rotate ở hệ thống phát hành |
| Dùng biến môi trường như kho bí mật tuyệt đối | Secret có thể lộ qua dump hoặc công cụ chẩn đoán | Đánh giá kênh injection và quyền quan sát tiến trình |

## 13. Nguyên tắc triển khai an toàn

- Lập danh mục secret có chủ sở hữu, mục đích, mức ảnh hưởng, consumer và thời hạn.
- Dùng secret manager hoặc dịch vụ nền tảng để lưu và phân phối credential; dùng KMS/HSM khi cần quản lý thao tác bằng khóa mật mã.
- Tạo secret bằng nguồn ngẫu nhiên phù hợp hoặc yêu cầu nhà cung cấp cấp credential có thể thu hồi.
- Ưu tiên workload identity và credential ngắn hạn thay cho secret tĩnh dùng chung.
- Cấp quyền tối thiểu theo từng secret, dịch vụ và môi trường.
- Không đưa secret vào source code, image, log, command line hoặc tài liệu chia sẻ.
- Thiết kế rotation và revocation cùng với consumer, cache, bản sao lưu và dependency.
- Dùng secret scanning, audit log, cảnh báo truy cập bất thường và quy trình ứng phó khi rò rỉ.
- Phân biệt secret, credential, public key, certificate và cryptographic key để áp dụng đúng cơ chế bảo vệ.
- Kiểm thử khôi phục và thay thế secret để bảo đảm rotation không làm gián đoạn dịch vụ.

Secret là thông tin mà việc tiết lộ có thể làm mất quyền kiểm soát hoặc một bảo đảm an toàn của hệ thống. Cryptographic key là một loại vật liệu có vai trò chuyên biệt trong thuật toán mật mã; một số khóa phải giữ bí mật, trong khi public key có thể công khai. Khi phân loại đúng và quản lý secret theo danh tính, quyền, phạm vi cùng vòng đời, hệ thống giảm được nguy cơ lộ credential và hạn chế ảnh hưởng khi một secret bị xâm phạm.
