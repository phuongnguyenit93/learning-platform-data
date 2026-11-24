# Key leakage: phòng ngừa, phát hiện và ứng phó khi API key bị lộ

> **Chương:** API key  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào rò rỉ API key như một sự cố credential: hiểu key đại diện cho ai, phát hiện nơi lộ, thu hồi và xoay vòng an toàn, điều tra việc sử dụng trái phép và giảm khả năng tái diễn.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao API key là credential/bearer secret và việc lộ key có thể cho phép bên khác sử dụng quyền được gắn với key.
2. Nhận diện các bề mặt rò rỉ phổ biến: source code, Git history, frontend bundle, log, CI/CD, artifact, ticket, chat, container image và cấu hình.
3. Phân biệt phát hiện bí mật với xác nhận key đã bị khai thác; đánh giá phạm vi ảnh hưởng theo owner, scope, môi trường và thời hạn.
4. Xây dựng quy trình containment, revoke, rotate, kiểm tra usage và khôi phục dịch vụ.
5. Thiết kế secret scanning, quản lý secret tập trung, least privilege, giới hạn mạng và giám sát bất thường.
6. Xử lý key trong Java/Spring và pipeline CI/CD mà không ghi secret vào repository hoặc log.
7. Kiểm thử quy trình phát hiện và ứng phó rò rỉ mà không phát tán hoặc sử dụng credential thật.

## 2. API key là credential, không phải một chuỗi cấu hình vô hại

**API key** là một giá trị do nhà cung cấp hoặc hệ thống cấp để nhận diện một client, project, service hoặc workload khi gọi API. Tùy thiết kế, key có thể đồng thời mang quyền truy cập, định danh project, quota hoặc một chính sách cụ thể.

Nhiều API key hoạt động như **bearer secret**: ai nắm giữ giá trị hợp lệ có thể trình nó để được hệ thống chấp nhận. Vì vậy, khi key bị lộ, rủi ro không phụ thuộc vào việc người nhận có phải chủ sở hữu ban đầu hay không; điều quan trọng là key còn hiệu lực và quyền gắn với nó.

Một số key chỉ nhận diện project hoặc dùng cho dữ liệu công khai; một số khác có thể đọc dữ liệu riêng, tạo tài nguyên, gửi thông điệp, phát sinh chi phí hoặc quản trị hệ thống. Không nên giả định mọi API key có cùng mức nhạy cảm.

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Owner | Key thuộc user, team, service account, project hay workload nào? |
| Environment | Development, staging hay production? |
| Scope/permission | Key có thể đọc, ghi, xóa, quản trị hay gọi những API nào? |
| Audience/service | Key được phép dùng ở API hoặc tài nguyên nào? |
| Expiration | Có ngày hết hạn hoặc chu kỳ xoay vòng không? |
| Network restrictions | Có giới hạn IP, private network hoặc mTLS không? |
| Quota/billing | Key có thể tiêu thụ quota hoặc tạo chi phí đến mức nào? |
| Revocation path | Ai có quyền thu hồi và việc thu hồi mất bao lâu để có hiệu lực? |

**Key leakage** là việc credential vượt khỏi ranh giới kiểm soát dự kiến: bị đưa vào repository công khai, gửi nhầm cho người không được phép, ghi vào log, đóng gói trong ứng dụng client, lưu trong artifact có quyền truy cập quá rộng hoặc bị lấy qua hệ thống bị xâm nhập.

Rò rỉ không đồng nghĩa chắc chắn đã có truy cập trái phép. Tuy nhiên, nếu không chứng minh được key vẫn nằm trong phạm vi kiểm soát, hãy xử lý theo mức độ credential có thể đã bị lộ.

## 3. Key leakage khác gì các sự cố xác thực khác?

| Sự cố | Bản chất | Ví dụ |
|---|---|---|
| **Key leakage** | Giá trị credential bị tiết lộ hoặc sao chép ngoài phạm vi tin cậy | API key xuất hiện trong commit công khai |
| Credential stuffing | Dùng cặp credential bị lộ ở dịch vụ khác để thử đăng nhập | Tên đăng nhập/mật khẩu bị tái sử dụng |
| Token theft | Lấy access token, refresh token hoặc session token đang có hiệu lực | Token bị ghi vào log request |
| Key misuse | Key còn được giữ kín nhưng bị dùng sai mục đích/quyền | Service dùng key production cho tác vụ thử nghiệm |
| Key compromise | Bên trái phép có khả năng kiểm soát key hoặc môi trường quản lý key | Secret manager hoặc máy build bị xâm nhập |
| Key expiration | Key hết hạn theo vòng đời bình thường | Credential cũ bị từ chối |

Các tình huống có thể chồng lấp. Một API key bị lộ có thể được sử dụng để tạo token khác, truy cập dữ liệu hoặc phát sinh chi phí; điều tra cần xem cả key gốc lẫn credential downstream được cấp từ nó.

## 4. Những nơi API key thường bị lộ

### 4.1. Source code và Git

- Key được hardcode trong Java, JavaScript, YAML, JSON, shell script hoặc file cấu hình môi trường.
- Commit nhầm cấu hình thật, kể cả repository private.
- Key bị xóa ở commit mới nhưng vẫn còn trong Git history, tag, fork, pull request hoặc clone.
- Secret xuất hiện trong test fixture, sample config, notebook hoặc script migration.
- Key được dán vào issue, pull request, code review hoặc tài liệu hướng dẫn.

Xóa dòng chứa key khỏi file hiện tại **không thu hồi credential** và không xóa các bản sao trong lịch sử, fork, cache hay clone của người khác. Nếu key có khả năng đã bị lộ, phải revoke/rotate trước; việc xử lý lịch sử Git là công việc vệ sinh bổ sung.

### 4.2. Frontend và ứng dụng phân phối tới người dùng

Một secret đặt trong JavaScript bundle, source map, mobile binary, desktop package hoặc file cấu hình tải xuống có thể được người dùng trích xuất. Minify, obfuscate, Base64 hoặc đổi tên biến không biến key thành bí mật.

Nếu một dịch vụ yêu cầu key bí mật, hãy gọi dịch vụ đó từ backend. Với API key công khai được nhà cung cấp thiết kế để dùng trong browser, cần cấu hình giới hạn origin/referrer, API được phép, quota và quyền phù hợp; không dùng public key như thể nó là credential server-side.

### 4.3. Log, tracing và telemetry

- Authorization header hoặc query string chứa key được ghi vào access log.
- Exception in toàn bộ request/response hoặc cấu hình.
- Distributed tracing, APM, crash report, analytics ghi lại header.
- Debug log hoặc lệnh in biến môi trường.
- Audit event lưu nguyên payload có credential.

Không truyền API key qua URL query nếu nhà cung cấp hỗ trợ header, vì URL dễ xuất hiện trong browser history, proxy log, analytics và referrer. Dùng header được tài liệu API quy định và redaction ở mọi lớp log.

### 4.4. CI/CD, build artifact và container

- Secret được khai báo trong command line rồi bị lưu vào process log.
- Build script in toàn bộ environment hoặc bật shell tracing.
- Artifact, test report, package cache hoặc Docker layer chứa file cấu hình có key.
- Pull request từ fork chạy workflow có quyền đọc secret production.
- Runner dùng chung không được cô lập, workspace còn dữ liệu sau job.

CI secret cần được cấp theo job/repository/environment tối thiểu; không để pull request không tin cậy có quyền đọc secret production. Ưu tiên workload identity/OIDC federation để runner lấy credential ngắn hạn thay cho key tĩnh khi nền tảng hỗ trợ.

### 4.5. Con người và hệ thống hỗ trợ

Key có thể bị gửi vào email, chat, ticket, ảnh chụp màn hình, pastebin, tài liệu chia sẻ công khai hoặc công cụ không được phép nhận bí mật. Cần hướng dẫn rõ cách chia sẻ thông tin cấu hình bằng secret manager và cách báo cáo khi gửi nhầm.

## 5. Phân loại mức độ nghiêm trọng

Không phải mọi phát hiện đều có cùng tác động. Đánh giá tối thiểu:

| Tiêu chí | Rủi ro cao hơn khi |
|---|---|
| Phạm vi quyền | Có quyền ghi/xóa/quản trị, đọc dữ liệu nhạy cảm hoặc cấp credential khác |
| Môi trường | Production hoặc môi trường chứa dữ liệu thật |
| Khả năng tiếp cận | Repository công khai, artifact tải công khai, log chia sẻ rộng |
| Thời gian lộ | Không rõ thời điểm, đã tồn tại lâu hoặc không có thời hạn |
| Khả năng sử dụng | Key còn hiệu lực, không có IP/scope restriction, quota lớn |
| Dấu hiệu khai thác | Request lạ, địa chỉ nguồn mới, usage spike, resource/charge bất thường |
| Phạm vi downstream | Key có thể cấp token, tạo webhook, tài khoản hoặc key khác |
| Khả năng thu hồi | Không rõ owner hoặc không có quy trình revoke nhanh |

Một key chỉ có quyền đọc dữ liệu công khai vẫn cần được xử lý theo chính sách nhà cung cấp, nhưng có thể có mức ảnh hưởng thấp hơn key production có quyền quản trị. Đừng dựa vào tên biến PUBLIC_API_KEY để kết luận an toàn; phải kiểm tra quyền thực tế và nơi sử dụng.

## 6. Phát hiện key leakage

Phát hiện hiệu quả cần nhiều lớp:

1. **Secret scanning khi commit:** quét thay đổi mới trước khi được merge.
2. **Repository history scanning:** quét lịch sử, tag và nhánh; secret có thể nằm trong commit cũ.
3. **Organization-wide scanning:** quét repository, snippet, wiki và nơi lưu code được quản lý.
4. **CI/CD scanning:** kiểm tra source, artifact, image và file cấu hình được đóng gói.
5. **Runtime monitoring:** phát hiện key được dùng từ IP/ASN, quốc gia, thời gian hoặc user agent bất thường.
6. **Provider alerts:** tiếp nhận cảnh báo key xuất hiện trong nguồn công khai hoặc có usage bất thường nếu nhà cung cấp hỗ trợ.
7. **Human reporting:** tạo kênh báo cáo một lần dán nhầm key, không yêu cầu người báo gửi lại nguyên secret.

### Secret scanner hoạt động như thế nào?

Scanner có thể tìm theo:

- Pattern/prefix của nhà cung cấp.
- Entropy hoặc hình dạng chuỗi.
- Tên biến nhạy cảm như API_KEY, TOKEN, SECRET.
- Context xung quanh chuỗi, file path và loại file.
- Kiểm tra xác thực với nhà cung cấp trong môi trường được phép, nếu tính năng này an toàn và được cấu hình rõ.

Scanner có thể tạo false positive (chuỗi mẫu, fixture giả) và false negative (key bị biến đổi, mã hóa, chia nhỏ hoặc định dạng mới). Vì vậy cần quy trình triage và không xem “scan sạch” là chứng minh không có key bị lộ.

### Khi phát hiện

- Không copy secret vào ticket/chat để nhờ người khác kiểm tra.
- Ghi nhận fingerprint hoặc định danh an toàn, provider, owner, repository/path, commit/URL và thời điểm phát hiện.
- Chỉ hiển thị giá trị đã che một phần, ví dụ prefix/suffix tối thiểu cần phân biệt.
- Xác minh key còn hiệu lực qua console/secret inventory có quyền truy cập; không thử gọi API bằng key nghi lộ từ máy cá nhân.
- Mở incident theo quy trình nội bộ và thông báo đúng owner/security team.

## 7. Ứng phó khi key bị lộ

**Ưu tiên containment và revoke.** Xóa key khỏi source không làm key cũ mất hiệu lực; đừng chờ hoàn tất Git cleanup mới thu hồi.

~~~mermaid
flowchart TD
    A["Phát hiện key có thể bị lộ"] --> B["Ghi nhận vị trí, owner, provider và thời điểm"]
    B --> C["Đánh giá scope, môi trường và quyền"]
    C --> D["Containment: revoke/disable key nghi lộ"]
    D --> E["Tạo key mới an toàn nếu dịch vụ cần tiếp tục"]
    E --> F["Cập nhật secret manager và workload"]
    F --> G["Kiểm tra hoạt động, quota và lỗi"]
    G --> H["Điều tra usage và credential downstream"]
    H --> I["Làm sạch source, history, log và artifact"]
    I --> J["Tăng giám sát, ghi nhận bài học và đóng incident"]
~~~

### Trình tự xử lý thực tế

1. **Triage:** xác định provider, key owner, scope, environment, ngày phát hiện, vị trí lộ và mức độ công khai. Nếu không rõ key có bị sử dụng hay không, coi là có khả năng bị compromise.
2. **Contain:** thu hồi/disable key ở provider hoặc secret manager; nếu có thể, giới hạn quyền/nguồn sử dụng ngay trong khi chuẩn bị revoke. Với key có quyền rất cao, ưu tiên hành động khẩn cấp theo quy trình incident.
3. **Rotate:** tạo credential mới qua kênh quản trị tin cậy, với scope tối thiểu, thời hạn và restriction phù hợp. Không tạo key mới trong cùng file/commit công khai.
4. **Migrate:** cập nhật secret manager hoặc workload identity; triển khai theo cách tránh đưa giá trị mới vào log, artifact hay command history.
5. **Verify:** xác nhận ứng dụng dùng key mới, request hợp lệ hoạt động, key cũ bị từ chối và không còn workload nào phụ thuộc key cũ.
6. **Investigate:** xem usage trước/sau thời điểm lộ, IP/ASN, user agent, endpoint, quota, tài nguyên được tạo/sửa/xóa, billing và token/credential downstream.
7. **Clean up:** xử lý source hiện tại, Git history, artifact, cache, log, ticket và bản sao theo chính sách. Thu hồi vẫn là bước quyết định bảo mật.
8. **Monitor:** theo dõi key mới và tài khoản/project liên quan để phát hiện tiếp tục lạm dụng hoặc persistence.
9. **Learn:** tìm nguyên nhân gốc, cập nhật secret scanning, quyền CI, hướng dẫn developer và thời hạn xoay vòng.

Không xóa log phục vụ điều tra trước khi bảo toàn bằng chứng theo quy trình. Không chia sẻ key nghi lộ rộng hơn để chứng minh sự cố.

## 8. Xoay vòng key không gây gián đoạn dịch vụ

Nếu hệ thống hỗ trợ nhiều key đồng thời, có thể dùng quy trình chuyển đổi:

1. Tạo key mới với scope và restriction tương đương hoặc nhỏ hơn.
2. Lưu key mới vào secret manager, phân quyền workload cần sử dụng.
3. Triển khai workload đọc key mới; nếu có thể, kiểm tra health và request thực tế.
4. Xác nhận toàn bộ instance/job đã dùng key mới.
5. Thu hồi key cũ và kiểm tra provider từ chối key cũ.
6. Theo dõi lỗi xác thực và usage bất thường sau cutover.

Trong sự cố key đang bị khai thác, không kéo dài thời gian overlap chỉ để thuận tiện triển khai. Revoke key cũ ngay theo mức khẩn cấp; nếu cần giảm gián đoạn, có thể tạm hạn chế scope/network hoặc dùng cơ chế chuyển đổi đã được chuẩn bị trước.

### Hai key active có lợi và có rủi ro

- Có thể hỗ trợ rotation không downtime nếu thời gian overlap ngắn và có giám sát.
- Cũng mở rộng số credential hợp lệ; key cũ bị lộ vẫn dùng được trong thời gian overlap.
- Cần owner, ngày hết hạn và trạng thái rõ cho từng key.
- Không dùng key mới như bản sao vô thời hạn của key cũ; xóa/thu hồi credential đã hết mục đích.

## 9. Ngăn key xuất hiện trong Git và code review

### Quy tắc phát triển

- Không hardcode key thật trong source, test, sample, README hoặc script.
- Dùng placeholder không thể sử dụng, ví dụ REPLACE_WITH_TEST_KEY, trong tài liệu.
- Thêm secret scanner vào pre-commit hoặc pre-receive hook và CI; hook phía client chỉ là lớp tiện ích vì có thể bị bỏ qua.
- Bảo vệ nhánh chính và yêu cầu scanner chạy trước merge.
- Không đưa secret vào commit để “tạm thử”; dùng secret manager hoặc local secret file đã được ignore và cấp quyền phù hợp.
- Nếu cần lịch sử để audit, không chỉnh sửa commit cũ theo cách làm mất bằng chứng incident; xử lý theo quy trình repository.

### Git history

Xóa key khỏi file ở commit mới không xóa blob chứa key ở commit cũ. Nếu cần loại khỏi history:

- Trước hết revoke key.
- Xác định repository, branch, tag, fork, mirror, clone và cache liên quan.
- Phối hợp owner repository để rewrite history theo chính sách, thông báo người dùng cần re-clone/rebase và tránh merge lại lịch sử cũ.
- Làm sạch pull request, artifact hoặc bản mirror mà tổ chức kiểm soát; với bản sao bên ngoài, đánh giá và liên hệ chủ quản theo quy trình.

History rewrite là biện pháp giảm tiếp tục phát tán; **không thay thế revoke**.

## 10. Secret trong CI/CD, container và cloud workload

### CI/CD

- Cấp secret ở cấp environment/job, không truyền cho workflow từ fork hoặc branch không tin cậy.
- Tắt shell tracing quanh lệnh có secret; không in environment hoặc command chứa credential.
- Dùng secret masking của CI nhưng không dựa hoàn toàn vào masking: encoded/substring/biến đổi có thể không được che.
- Xóa secret khỏi artifact, test report, cache và workspace sau job theo khả năng runner.
- Giới hạn runner, quyền truy cập secret, thời gian sống credential và khả năng network egress.
- Ưu tiên OIDC workload identity hoặc federation để cấp token ngắn hạn theo job thay cho key dài hạn nếu nhà cung cấp hỗ trợ.

### Container và cloud

- Không dùng ENV hoặc ARG để đóng secret vào image; layer lịch sử có thể còn giá trị.
- Không copy file .env thật vào image hoặc build context.
- Mount secret lúc runtime từ secret manager/volume với quyền file tối thiểu.
- Dùng workload identity/managed identity khi có thể để workload lấy credential theo danh tính máy.
- Tránh lưu secret trong Terraform state, plan output, cloud-init, startup log hoặc metadata công khai; bảo vệ state như dữ liệu nhạy cảm.

## 11. Bảo vệ log, tracing và error handling

API key không nên xuất hiện trong URL, log hoặc exception. Nếu provider bắt buộc một cách truyền đặc biệt, cần redaction tương ứng ở proxy, application, APM và tracing.

| Vị trí | Rủi ro | Kiểm soát |
|---|---|---|
| HTTP Authorization header | Access log hoặc debug middleware ghi header | Redact header nhạy cảm ở ingress và app |
| Query string | URL xuất hiện trong history, referrer, proxy log | Dùng header theo tài liệu provider |
| Exception | In request config hoặc object chứa key | Exception message không chứa secret; structured logging |
| APM/tracing | Span attribute ghi header/body | Mask field, tắt capture payload nhạy cảm |
| Audit | Lưu nguyên credential thay vì metadata | Lưu key ID/fingerprint, owner, action và kết quả |
| Support ticket | Người dùng dán key thật để nhờ hỗ trợ | Hướng dẫn che key và báo cáo bằng metadata |

Log nên ghi **key identifier** hoặc fingerprint không thể dùng để xác thực, owner, scope, source, thời gian và kết quả. Không log toàn bộ secret để điều tra; provider console và audit trail là nguồn ưu tiên.

## 12. Giới hạn quyền và giảm tác động khi key lộ

Không thể bảo đảm mọi key sẽ không bao giờ bị lộ. Thiết kế nên giả định credential có thể bị sao chép và giới hạn thiệt hại:

- **Least privilege:** chỉ cấp endpoint/action cần thiết; tách read/write/admin.
- **Environment separation:** key dev/staging không dùng được ở production; không chia sẻ một key cho nhiều môi trường.
- **Per-service key:** mỗi workload có credential riêng để có thể revoke một thành phần mà không ảnh hưởng tất cả.
- **Short lifetime:** ưu tiên token ngắn hạn hoặc workload identity khi hỗ trợ; giảm thời gian hữu ích của credential bị lấy.
- **Scope/audience restriction:** giới hạn API, project, tenant và tài nguyên.
- **Network restrictions:** IP allowlist/private endpoint/mTLS khi phù hợp; đây là lớp bổ sung, không thay authentication.
- **Quota and budget:** đặt giới hạn usage, cảnh báo chi phí và tốc độ tạo tài nguyên.
- **Rotation and inventory:** có owner, purpose, createdAt, expiresAt, lastUsedAt và trạng thái.
- **Revocation drill:** diễn tập thu hồi và chuyển đổi key để biết thời gian phản ứng thực tế.

Nếu key được dùng trong hệ thống không hỗ trợ scope hoặc expiration, cân nhắc proxy backend làm lớp kiểm soát, giảm quyền của key upstream và không phát key trực tiếp cho client.

## 13. Java/Spring: đọc secret từ môi trường quản lý

Ứng dụng Java không nên chứa API key trong source hoặc cấu hình được commit. Ví dụ dưới đây minh họa lấy key từ cấu hình runtime do secret manager cấp:

~~~java
@ConfigurationProperties(prefix = "vendor.api")
record VendorApiProperties(URI baseUri, String key) {}

@Configuration
class ExternalApiConfiguration {

    @Bean
    ExternalApiClient externalApiClient(VendorApiProperties properties) {
        String apiKey = properties.key();
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException(
                "Vendor API credential is not configured"
            );
        }

        return ExternalApiClient.builder()
            .baseUri(properties.baseUri())
            .apiKey(apiKey)
            .build();
    }
}
~~~

Đây là ví dụ khung; ExternalApiClient là client do ứng dụng hoặc SDK định nghĩa. Cần đăng ký cấu hình properties và cấp giá trị ở runtime từ secret manager/secret volume hoặc workload identity theo nền tảng. Không log giá trị apiKey, không đưa nó vào exception, actuator endpoint, debug representation hoặc metrics label. Quyền đọc secret cần tối thiểu và có cơ chế rotation.

### Không đưa key vào frontend

~~~javascript
// Không an toàn: giá trị sẽ xuất hiện trong bundle hoặc runtime của browser.
const apiKey = "REAL_SERVER_SIDE_API_KEY";
~~~

Browser nên gọi backend của chính ứng dụng. Backend xác thực user, kiểm tra authorization, sau đó gọi API bên ngoài bằng key được giữ ở server. Nếu nhà cung cấp có public browser key, chỉ dùng đúng loại key được thiết kế công khai và cấu hình origin/API/quota restrictions.

### Tránh log request chứa secret

~~~java
// Không log Authorization header hoặc API key.
log.info("Calling vendor API: endpoint={}, requestId={}",
    endpointPath, requestId);
~~~

Không log toàn bộ URL nếu key có thể nằm trong query string; log path đã chuẩn hóa và request ID.

## 14. Điều tra dấu hiệu sử dụng key trái phép

Sau khi revoke hoặc trong lúc containment, xem xét:

- Key được dùng lần cuối khi nào, trước/sau thời điểm phát hiện?
- Có nguồn IP/ASN, vùng mạng, user agent hoặc thời gian bất thường không?
- Endpoint nào được gọi? Có request liệt kê, export, delete hoặc tạo tài nguyên mới không?
- Usage/quota/billing có tăng đột biến không?
- Có credential khác được tạo ra, token được cấp hoặc webhook bị thay đổi không?
- Có thay đổi permission, allowlist, project settings hoặc billing account không?
- Key có được dùng ở nhiều service/host không đúng inventory không?
- Secret có xuất hiện ở nhiều nơi khác nhau, dẫn đến nhiều bên có thể đã sao chép không?

Phân biệt **dấu hiệu xác thực** với **dấu hiệu sử dụng**: log có request thành công chứng minh key đã được chấp nhận, nhưng không luôn cho biết ai là người dùng thật; IP có thể là proxy/NAT và user agent có thể giả. Ghép provider audit, application audit, cloud audit, billing và incident timeline.

Nếu key có quyền tạo credential mới, hãy rà soát các key/token/service account downstream. Revoke key gốc chưa chắc thu hồi những credential đã được tạo trước đó.

## 15. Ma trận kiểm thử key leakage

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Commit chứa chuỗi khớp pattern API key giả lập | Secret scanner chặn hoặc tạo finding đúng |
| Secret chỉ bị xóa ở commit mới nhưng còn trong Git history | History scan vẫn phát hiện |
| Pull request từ fork không tin cậy | Workflow không được đọc secret production |
| Frontend bundle chứa server-side key giả lập | CI/build scan phát hiện; build bị chặn |
| Debug log nhận request có Authorization header | Header bị redaction; log không chứa secret |
| Exception do SDK trả về có request config | Error handler không in key |
| Docker image có file cấu hình secret | Image scan/build policy phát hiện |
| Artifact/test report chứa env dump | Scan phát hiện và artifact không được publish |
| Key bị đánh dấu compromised | Quy trình revoke/rotate có thể thực hiện và được audit |
| Key mới được triển khai trong rotation | Workload hoạt động với key mới, không lộ trong log |
| Key cũ sau revoke | Provider từ chối key cũ |
| Usage bất thường từ nguồn mới | Alert tạo đúng owner/security triage |
| Key read-only bị lộ | Phạm vi dữ liệu đọc được được xác định và key vẫn được revoke theo policy |
| Secret scanner có false positive | Có cơ chế triage/suppress có lý do, không tắt scanner toàn bộ |
| Key downstream được tạo từ key gốc | Incident review phát hiện và đánh giá thu hồi credential liên quan |

Chỉ sử dụng key giả lập hoặc môi trường sandbox để thử scanner, revoke và rotation. Không đưa credential production thật vào test case hoặc repository thử nghiệm.

## 16. Tình huống phân tích

### Tình huống A: key xuất hiện trong repository công khai

Developer commit nhầm API key production vào file cấu hình. Một scanner bên ngoài phát hiện sau vài phút; commit mới đã xóa dòng chứa key.

**Phân tích:** key vẫn có thể nằm trong Git history và đã bị sao chép. Cần revoke/disable key ngay theo quy trình, tạo key mới với scope tối thiểu, cập nhật secret manager/workload, điều tra provider usage và downstream credential. Sau đó mới làm sạch history, fork, artifact và cache trong phạm vi kiểm soát.

### Tình huống B: key xuất hiện trong log CI

Một job bật shell tracing và in command chứa biến môi trường API key. Log chỉ chia sẻ trong nhóm phát triển nhưng có retention dài.

**Phân tích:** coi log là một nơi credential đã vượt khỏi phạm vi cần thiết. Xác định ai có quyền đọc log, thời gian lưu, bản export/cache; revoke/rotate nếu có khả năng người không được phép truy cập. Tắt tracing quanh secret, bật redaction và chuyển sang workload identity nếu hỗ trợ.

### Tình huống C: key trong ứng dụng mobile

Ứng dụng mobile gọi trực tiếp một API server-side bằng key nhúng trong binary. Key được trích xuất từ package và dùng từ nhiều thiết bị.

**Phân tích:** obfuscation không bảo vệ secret trong client. Revoke key, chuyển lời gọi nhạy cảm qua backend, xác thực user và giới hạn quyền ở backend. Nếu API có public key dành cho mobile, chỉ sử dụng loại key công khai được thiết kế như vậy và giới hạn API/quota; không dùng nó để bảo vệ thao tác đặc quyền.

### Tình huống D: key bị dùng sau khi đã xóa khỏi source

Nhóm phát triển xóa key khỏi repository nhưng provider audit tiếp tục ghi nhận request từ IP lạ.

**Phân tích:** việc xóa source không thu hồi key. Revoke key tại provider, kiểm tra token/credential được cấp từ key đó, xác minh workload hợp lệ đã chuyển sang key mới và tiếp tục giám sát.

## 17. Quy trình thiết kế và vận hành

Trước khi phát hành một API key, hãy xác định:

1. Key thuộc owner/service nào, dùng ở môi trường nào và có mục đích gì?
2. Key có scope, audience, quota, network restriction và expiration nhỏ nhất cần thiết chưa?
3. Có thể dùng workload identity hoặc token ngắn hạn thay key tĩnh không?
4. Secret được lưu trong secret manager, runtime hoặc HSM phù hợp chưa?
5. Key có xuất hiện trong source, frontend, log, trace, artifact hoặc build context không?
6. Secret scanner được chạy ở commit, CI, repository history và image/artifact chưa?
7. Ai được đọc secret, ai có quyền revoke, và các quyền này có audit không?
8. Rotation có thể thực hiện mà không gây downtime hoặc kéo dài overlap nguy hiểm không?
9. Có cảnh báo usage, billing, IP/ASN, endpoint và hành vi bất thường không?
10. Khi key lộ, incident owner và quy trình revoke/rotate/downstream review có rõ không?
11. Sau incident, có xử lý Git history, cache, artifact, log và bản sao không?
12. Có diễn tập revoke/rotation bằng key giả lập định kỳ không?

## 18. Ghi nhớ trọng tâm

- **API key là credential.** Nếu key có thể được dùng như bearer secret, người nắm giữ giá trị có thể sử dụng quyền gắn với key cho đến khi key bị giới hạn hoặc thu hồi.
- **Rò rỉ có thể xảy ra ở bất kỳ nơi nào secret đi qua:** Git, frontend, log, CI/CD, container, artifact, ticket và chat.
- **Xóa key khỏi source không làm key cũ mất hiệu lực.** Containment/revoke là ưu tiên; Git cleanup và artifact cleanup là các bước bổ sung.
- **Secret scanning cần nhiều lớp và triage.** Scanner có false positive/negative; cần repository history scan, CI scan và runtime/provider monitoring.
- **Rotation phải có owner, kế hoạch chuyển đổi và xác minh revoke.** Giới hạn scope, môi trường, audience, thời hạn và quota để giảm thiệt hại.
- **Không đặt server-side key trong browser/mobile hoặc log.** Dùng backend, secret manager và workload identity khi phù hợp.
- **Điều tra cả credential downstream.** Key gốc có thể đã tạo token, webhook hoặc key khác trước khi bị thu hồi.
- **Diễn tập ứng phó bằng credential giả lập.** Biết rõ ai revoke, cập nhật workload, kiểm tra key cũ và theo dõi usage trước khi sự cố thật xảy ra.

Quản lý API key an toàn không dừng ở việc cất một chuỗi vào secret manager. Cần kiểm soát toàn bộ vòng đời credential: cấp đúng quyền, giới hạn nơi sử dụng, phát hiện khi vượt ranh giới, thu hồi nhanh, điều tra tác động và ngăn secret xuất hiện trở lại.
