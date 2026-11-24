# Key generation (Sinh API key)

> **Chương:** API key  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Sinh API key như một credential bí mật có entropy cao, không thể đoán thực tế; gắn khóa với đúng chủ thể và phạm vi sử dụng; bảo vệ bí mật trong lúc tạo, hiển thị, lưu trữ và phân phối để tránh biến API key thành đường truy cập trái phép.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích API key là gì, nó chứng minh điều gì và vì sao thường hoạt động như **bearer credential**.
2. Phân biệt phần định danh/selector của key với phần secret ngẫu nhiên; phân biệt key với user ID, API endpoint, token có claim và quyền truy cập.
3. Chọn nguồn ngẫu nhiên mật mã an toàn (CSPRNG), độ dài entropy và cách mã hóa biểu diễn key phù hợp.
4. Thiết kế định dạng API key dễ nhận diện, tra cứu, phân biệt môi trường và hỗ trợ thu hồi mà không làm lộ secret.
5. Viết ví dụ Java dùng **SecureRandom** để sinh secret; hiểu vì sao **Random**, timestamp, UUID tự chế hoặc chuỗi dễ đoán không phù hợp.
6. Thiết kế cách lưu trữ và xác minh key, bao gồm hash/HMAC, constant-time comparison, hiển thị một lần và quản lý secret.
7. Xác định các yêu cầu về scope, expiry, rotation, revocation, audit, rate limit và kiểm thử cho vòng đời API key.

## 1. API key là gì?

**API key** là một credential mà client trình cho một API để hệ thống nhận diện một ứng dụng, tích hợp, workload hoặc một chủ thể được cấp khóa. Trong nhiều thiết kế, ai nắm được key có thể sử dụng nó trong phạm vi được cấp; vì vậy API key thường là **bearer secret**.

Ví dụ, một dịch vụ báo cáo được cấp key để gọi endpoint đọc dữ liệu báo cáo. Khi request gửi key hợp lệ, API có thể tra ra bản ghi key, xác định chủ thể sở hữu và kiểm tra các quyền tương ứng.

API key thường hữu ích cho:

- Tích hợp server-to-server đơn giản.
- Xác định client ứng dụng hoặc workload trong một API.
- Quản lý hạn mức, quota và audit theo từng tích hợp.
- Cấp/thu hồi credential riêng cho từng môi trường hoặc ứng dụng.
- Tránh dùng chung một mật khẩu quản trị cho nhiều dịch vụ.

API key **không tự chứng minh danh tính con người** đang ngồi trước ứng dụng. Nó cũng không tự xác định người dùng cuối thay mặt request, không tự tạo MFA và không nên mặc nhiên cấp quyền rộng. Nếu API cần xác thực người dùng, có thể cần cơ chế riêng như OAuth/OIDC hoặc một mô hình ủy quyền phù hợp.

### API key khác những giá trị nào?

| Giá trị | Mục đích | Có phải bí mật xác thực không? |
| --- | --- | --- |
| **User ID / client ID** | Tham chiếu tài khoản hoặc client. | Thường không; có thể công khai nếu không trao quyền. |
| **API endpoint** | Địa chỉ gọi dịch vụ. | Không. |
| **API key secret** | Bằng chứng bearer mà client trình để được nhận diện/kiểm tra quyền. | Có; phải bảo vệ như mật khẩu hoặc token bí mật. |
| **Access token** | Credential có thể mang audience, scope, thời hạn và ngữ cảnh ủy quyền. | Có; cần kiểm chứng theo giao thức và chính sách. |
| **Private key của chứng chỉ** | Khóa mật mã dùng ký hoặc chứng minh sở hữu trong giao thức. | Có; không gửi lên server. |
| **Request signature** | Bằng chứng mật mã gắn request với khóa và có thể với thời gian/body. | Là bằng chứng được tạo từ secret/private key; khác với gửi bearer key trực tiếp. |

Một chuỗi có tên **apiKey** trong JSON không tự nhiên trở thành API key an toàn. Hệ thống cần có quy trình sinh, lưu, tra cứu, xác minh, phân quyền, hết hạn và thu hồi.

## 2. Nguyên tắc cốt lõi khi sinh key

Một API key dùng làm secret cần đáp ứng bốn yêu cầu:

1. **Không thể đoán thực tế:** giá trị secret được tạo từ nguồn ngẫu nhiên mật mã với đủ entropy.
2. **Không trùng lặp thực tế:** không sinh key bằng bộ đếm, thời gian, ID tuần tự hoặc dữ liệu có thể dự đoán.
3. **Không tiết lộ trong quá trình tạo và sử dụng:** chỉ hiển thị khi cần, không ghi log, không đưa vào URL hoặc thông báo.
4. **Có thể quản lý vòng đời:** có chủ sở hữu, mục đích, môi trường, scope, thời hạn, trạng thái, lịch sử xoay và khả năng thu hồi.

### Định danh và secret nên tách biệt

Một key có thể được biểu diễn bằng hai phần:

- **Selector / public identifier:** giúp hệ thống tìm bản ghi key. Phần này không trao quyền nếu đứng riêng.
- **Secret:** chuỗi ngẫu nhiên mà client phải bảo vệ và trình khi gọi API.

Ví dụ về cấu trúc hiển thị:

~~~text
ak_live_<selector>_<secret>
~~~

Trong đó:

- **ak** cho biết loại credential.
- **live** gợi ý môi trường sản xuất.
- **selector** giúp tìm bản ghi hoặc phiên bản key.
- **secret** là phần bí mật ngẫu nhiên.

Đây là định dạng minh họa, không phải chuẩn chung. Prefix giúp phát hiện key trong log hoặc repository và hỗ trợ phân biệt môi trường; prefix **không phải** cơ chế bảo mật và không thay thế kiểm tra secret.

Nếu key chỉ là một chuỗi ngẫu nhiên duy nhất, server vẫn có thể tra bằng hash, nhưng tách selector và secret thường giúp tra cứu nhanh hơn và tránh lưu secret rõ. Selector nên đủ duy nhất trong phạm vi hệ thống, không chứa thông tin cá nhân hoặc quyền nhạy cảm.

## 3. Entropy và độ dài secret

**Entropy** biểu thị mức không thể đoán của secret. Nếu secret có \(n\) bit entropy và được sinh đều, không có cấu trúc dễ đoán, thì không gian có \(2^n\) khả năng.

Ví dụ:

| Entropy | Số giá trị có thể | Nhận xét |
| --- | ---: | --- |
| 32 bit | \(2^{32}\) | Quá nhỏ cho bearer credential có giá trị. |
| 64 bit | \(2^{64}\) | Không nên dùng làm mục tiêu cho API key có quyền truy cập quan trọng. |
| 128 bit | \(2^{128}\) | Không gian rất lớn nếu sinh đúng bằng CSPRNG. |
| 256 bit | \(2^{256}\) | Lựa chọn phổ biến, dư dả cho secret API key mới. |

Một thiết kế thực tế có thể dùng **32 byte ngẫu nhiên = 256 bit** cho phần secret. Khi mã hóa Base64 URL-safe không padding, 32 byte tạo chuỗi khoảng 43 ký tự. Nếu dùng hex, 32 byte sẽ thành 64 ký tự. Chọn cách biểu diễn sao cho dễ truyền và ít lỗi cắt/escape.

**Độ dài ký tự không đồng nghĩa entropy.** Một chuỗi 40 ký tự ghép từ timestamp, tên ứng dụng và số thứ tự có thể dễ đoán hơn một chuỗi ngắn hơn được sinh đều từ CSPRNG.

### Xác suất trùng lặp

Khi sinh ngẫu nhiên độc lập trong không gian \(N=2^n\), xác suất có ít nhất một va chạm sau \(k\) lần sinh gần đúng theo birthday bound:

\[
P(\text{collision}) \approx \frac{k(k-1)}{2N}
\]

Với secret 256 bit, số lần sinh key thực tế rất nhỏ so với không gian, nên xác suất va chạm cực thấp. Dù vậy, cơ sở dữ liệu vẫn nên có ràng buộc duy nhất cho selector hoặc fingerprint phù hợp để xử lý lỗi, cấu hình sai hoặc tình huống bất thường.

## 4. Phải dùng CSPRNG

**Cryptographically Secure Pseudo-Random Number Generator (CSPRNG)** là bộ sinh số giả ngẫu nhiên được thiết kế để đầu ra khó dự đoán ngay cả khi attacker biết một phần đầu ra hoặc trạng thái liên quan trong các giới hạn của mô hình bảo mật.

Khi sinh API key, dùng CSPRNG của hệ điều hành hoặc runtime được tin cậy:

- Java: **java.security.SecureRandom**.
- Các runtime khác: API crypto ngẫu nhiên được nền tảng khuyến nghị.
- Dịch vụ sinh secret chuyên dụng hoặc HSM có thể phù hợp với yêu cầu quản trị đặc biệt.

Không dùng:

- **java.util.Random** hoặc **ThreadLocalRandom**.
- Timestamp, số thứ tự, tên người dùng, email hoặc hash từ dữ liệu công khai.
- UUID tự chế bằng cách ghép chuỗi, cắt timestamp hoặc lấy ID tuần tự.
- Hash của một chuỗi dễ đoán để giả làm secret.
- Bộ sinh tự viết hoặc thuật toán mã hóa không rõ nguồn.

**Hash không tạo thêm entropy.** Nếu đầu vào là thời gian hiện tại, SHA-256(timestamp) vẫn có thể bị dò bằng cách thử các thời điểm hợp lý.

### Ví dụ Java: sinh 32 byte secret

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class ApiKeyGenerator {
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    private ApiKeyGenerator() {
    }

    public static String generateSecret() {
        byte[] secretBytes = new byte[32]; // 256 bits
        SECURE_RANDOM.nextBytes(secretBytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secretBytes);
    }

    public static void main(String[] args) {
        String secret = generateSecret();
        System.out.println(secret);
    }
}
~~~

Đây là ví dụ minh họa việc sinh và mã hóa secret. Trong ứng dụng thực tế:

- Không in secret ra console hoặc log như ví dụ demo nếu môi trường có thu thập log.
- Chỉ đưa secret tới kênh trả kết quả đã được bảo vệ để người quản trị lưu lại.
- Không tái sử dụng cùng một secret cho nhiều client hoặc môi trường.
- Không tự seed **SecureRandom** bằng timestamp hay dữ liệu người dùng; để runtime khởi tạo và quản lý nguồn entropy.
- Không giữ bản sao secret không cần thiết trong bộ nhớ lâu hơn yêu cầu.

### Ví dụ tạo định dạng đầy đủ

~~~java
String selector = createRandomSelector();
String secret = ApiKeyGenerator.generateSecret();

String presentedKey = "ak_live_" + selector + "_" + secret;

// Chỉ selector và fingerprint/hash được lưu trong bản ghi.
// presentedKey chỉ được trả cho người tạo một lần.
~~~

**createRandomSelector()** cũng nên dùng nguồn ngẫu nhiên phù hợp hoặc ID ngẫu nhiên có không gian đủ lớn. Không sử dụng selector tuần tự nếu nó làm lộ quy mô, thứ tự cấp key hoặc thông tin nội bộ; nếu dùng ID tuần tự để tra cứu, phải bảo đảm ID không tự trao quyền và secret độc lập vẫn có entropy cao.

## 5. Mã hóa biểu diễn secret

CSPRNG sinh byte. Ứng dụng cần chuyển byte thành dạng có thể hiển thị và truyền qua giao thức.

| Biểu diễn | Đặc điểm | Lưu ý |
| --- | --- | --- |
| **Base64 URL-safe** | Gọn hơn hex, tránh các ký tự cộng và gạch chéo khi dùng alphabet URL-safe. | Cần thống nhất padding/no-padding và xử lý chính xác khi parse. |
| **Hex** | Dễ đọc và debug, chỉ dùng 0-9 và a-f. | Dài gấp đôi số byte. |
| **Base32** | Có thể thuận tiện cho một số kênh nhập tay. | Dài hơn; cần xử lý chữ hoa/thường và ký tự dễ nhầm. |
| **Chuỗi custom** | Có thể tối ưu cho trải nghiệm người dùng. | Không tự tạo entropy; phải mã hóa byte ngẫu nhiên và tránh làm giảm không gian. |

Không dùng mã hóa để thay thế bảo vệ secret. Base64, hex và Base32 chỉ là **encoding**, không phải encryption. Ai nhìn thấy chuỗi đã mã hóa vẫn có thể sử dụng nó nếu chuỗi đó là bearer key.

### Cắt ngắn secret để hiển thị có được không?

Có thể hiển thị một phần đã che như **ak_live_ab12••••••••** trong giao diện quản lý sau khi tạo. Tuy nhiên, phần bị che không phải giá trị dùng để xác thực. Server cần lưu selector/fingerprint để tìm bản ghi, và chỉ hiển thị toàn bộ secret một lần khi cấp key. Không thể khôi phục secret đầy đủ từ vài ký tự cuối.

## 6. Lưu trữ an toàn: không lưu secret rõ

Nếu server lưu API key ở dạng rõ, bất kỳ ai đọc được database backup, replica, log hoặc bảng quản trị có thể lấy key và sử dụng nó. Với secret được sinh ngẫu nhiên có entropy cao, server thường không cần giữ bản rõ sau khi cấp.

### Mô hình lưu trữ

Một bản ghi có thể gồm:

| Trường | Mục đích |
| --- | --- |
| **keyId / selector** | Tra cứu bản ghi key. |
| **secretHash hoặc secretHmac** | Giá trị xác minh thay cho secret rõ. |
| **ownerSubjectId** | Chủ thể hoặc tài khoản sở hữu key. |
| **environment** | test, staging, production hoặc môi trường được định nghĩa. |
| **scopes** | Quyền/hành động mà key được phép thực hiện. |
| **createdAt, expiresAt** | Thời điểm cấp và hết hạn nếu có. |
| **lastUsedAt** | Theo dõi hoạt động, nếu cần và có kiểm soát quyền riêng tư. |
| **status** | Active, revoked, expired, suspended. |
| **description** | Mục đích do người tạo ghi, không chứa secret. |

Ví dụ:

~~~text
ApiKeyRecord
  keyId: "key_7f2a..."
  secretHash: <hash-or-HMAC>
  ownerSubjectId: "service-reporting"
  environment: "production"
  scopes: ["reports:read"]
  createdAt: ...
  expiresAt: ...
  status: "active"
~~~

### Hash hay HMAC?

Với mật khẩu do người dùng chọn, cần thuật toán băm chậm chuyên dụng vì mật khẩu thường có entropy thấp. API key được sinh ngẫu nhiên đủ entropy khác ở điểm này:

- Có thể dùng **SHA-256** để lưu fingerprint/hash của phần secret vì secret có không gian tìm kiếm rất lớn nếu CSPRNG và độ dài được chọn đúng.
- Có thể dùng **HMAC-SHA-256 với server-side pepper/key** được lưu trong secret manager hoặc HSM để tăng bảo vệ khi database bị lộ riêng lẻ.
- Không dùng hash nhanh cho mật khẩu yếu; không đánh đồng yêu cầu lưu password hash với hash của random API key.

Nếu dùng HMAC, cần quản lý phiên bản khóa HMAC, kế hoạch xoay khóa và khả năng xác minh các key cũ trong thời gian chuyển đổi. Không đặt pepper cạnh bảng database chứa fingerprint.

### Xác minh key

Một luồng kiểm tra có thể là:

1. Parse prefix/selector và secret theo định dạng được hỗ trợ.
2. Tra bản ghi bằng selector; nếu không tồn tại, từ chối an toàn.
3. Kiểm tra trạng thái, môi trường, thời hạn và các ràng buộc.
4. Tính hash/HMAC của secret nhận được bằng cấu hình đúng.
5. So sánh bằng hàm **constant-time comparison** phù hợp, tránh tự viết so sánh dừng ở byte đầu tiên khác nhau.
6. Nếu secret đúng, xác định chủ thể sở hữu key và kiểm tra scope/quyền trên request.
7. Ghi sự kiện cần thiết nhưng không log key hoặc secret.

Không nên trả response khác biệt quá rõ để tiết lộ selector hợp lệ hay trạng thái key cho người không được phép. Nếu API cần thông tin chẩn đoán, cung cấp mã lỗi tổng quát và audit nội bộ.

## 7. Hiển thị và phân phối key an toàn

Một API key mới thường chỉ nên hiển thị đầy đủ **một lần** ngay sau khi tạo.

Quy trình gợi ý:

1. Người có quyền quản lý tích hợp yêu cầu tạo key cho đúng owner và môi trường.
2. Server kiểm tra quyền tạo credential, scope được phép và giới hạn số key.
3. Server sinh secret bằng CSPRNG, tạo selector, lưu hash/HMAC cùng metadata.
4. Server trả key đầy đủ qua response bảo vệ, chỉ trong luồng tạo key.
5. Giao diện cảnh báo người dùng lưu key vào secret manager hoặc kho bí mật được chấp nhận.
6. Khi quay lại trang quản lý, chỉ hiển thị prefix, selector và một phần che; không cung cấp lại secret đầy đủ.
7. Nếu mất key, người quản trị tạo key mới và thu hồi key cũ sau khi chuyển đổi.

Không gửi key qua email, chat, issue tracker, ticket, ảnh chụp màn hình hoặc tài liệu công khai. Nếu phải truyền giữa người quản trị và workload, sử dụng kênh phân phối secret được kiểm soát và giới hạn quyền đọc.

**“Chỉ hiển thị một lần” không có nghĩa key chỉ dùng một lần.** Nó có nghĩa server không lưu secret rõ để hiển thị lại; key vẫn có thể hoạt động cho tới khi hết hạn hoặc bị thu hồi theo chính sách.

## 8. Gắn key với chủ thể, môi trường và quyền

Sinh một secret ngẫu nhiên chỉ giải quyết câu hỏi **key khó đoán không**. Nó chưa trả lời:

- Ai sở hữu key?
- Key được dùng ở môi trường nào?
- Key được phép gọi API nào?
- Key có thể thực hiện thao tác đọc hay ghi?
- Key có được dùng thay mặt người dùng cuối không?

Các thông tin này cần được quản lý bằng metadata và chính sách ở server.

### Phân tách theo môi trường

Không dùng cùng một key cho development, staging và production. Nếu secret ở môi trường thử nghiệm bị lộ, attacker không nên có đường dùng nó truy cập dữ liệu production.

### Scope tối thiểu

| Scope ví dụ | Hành động |
| --- | --- |
| reports:read | Đọc báo cáo. |
| reports:export | Xuất dữ liệu báo cáo. |
| billing:read | Xem thông tin thanh toán được phép. |
| billing:write | Thay đổi nghiệp vụ thanh toán theo quyền. |
| users:admin | Quản trị người dùng; cần kiểm soát đặc biệt. |

Không cấp **admin:\*** chỉ vì tích hợp cần gọi một endpoint. Kiểm tra scope phải được thực hiện ở resource server/API, kết hợp owner, resource, action và context.

### API key và người dùng cuối

Nếu một backend dùng API key để gọi API thay mặt người dùng, key xác định **backend/client**. Hệ thống vẫn cần một cơ chế riêng để mang danh tính và quyền của người dùng cuối, chẳng hạn access token có audience/scope phù hợp hoặc thông tin ủy quyền được ký và kiểm chứng. Không nhúng **userId** do client tự khai vào request rồi coi đó là danh tính đã xác thực.

## 9. Truyền key trong request

Một cách phổ biến là gửi API key trong header chuyên dụng:

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.test
X-API-Key: ak_live_<selector>_<secret>
Accept: application/json
~~~

Đây là ví dụ minh họa định dạng header; tên header thực tế phụ thuộc API contract.

Các nguyên tắc:

- Chỉ truyền qua HTTPS/TLS.
- Tránh đưa key vào URL query string vì URL có thể xuất hiện trong access log, browser history, proxy log, analytics và referrer.
- Không đặt key trong cookie trừ khi kiến trúc đã xem xét rõ các rủi ro cookie/CSRF và có lý do cụ thể.
- Không đưa key vào mã nguồn frontend/mobile công khai nếu không thể giữ bí mật; bất kỳ secret nhúng trong client phân phối cho người dùng đều có thể bị trích xuất.
- Không gửi key tới domain không được phép hoặc redirect tùy ý.
- Loại key khỏi log, trace, error report, crash dump và telemetry.
- Hạn chế scope, TTL, audience, quota và tốc độ request theo key.

Nếu một ứng dụng chạy trong browser cần gọi API, không nên nhúng server API key có quyền vào JavaScript. Thay vào đó, dùng backend trung gian/BFF hoặc cơ chế cấp quyền client phù hợp; coi mọi bí mật được phân phối trong ứng dụng công khai là có thể bị người dùng lấy ra.

## 10. Vòng đời API key: tạo, xoay và thu hồi

Một key an toàn cần được quản lý từ lúc cấp đến khi hết hiệu lực.

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Active: Kiểm tra quyền và sinh key
    Active --> RotationPending: Chuẩn bị key thay thế
    RotationPending --> ActiveNew: Client chuyển sang key mới
    ActiveNew --> RevokedOld: Thu hồi key cũ
    Active --> Suspended: Phát hiện rủi ro / tạm dừng
    Suspended --> Active: Xác minh và khôi phục theo policy
    Suspended --> Revoked: Xác nhận bị lộ
    Active --> Expired: Hết hạn
    Active --> Revoked: Thu hồi chủ động
    Expired --> [*]
    Revoked --> [*]
~~~

### 10.1 Rotation không gây gián đoạn

Một cách xoay key có kiểm soát:

1. Tạo key mới cho cùng workload/owner với scope được rà soát.
2. Phân phối key mới qua secret manager hoặc kênh được phê duyệt.
3. Cập nhật workload và xác nhận request mới dùng key mới.
4. Theo dõi việc sử dụng key cũ trong khoảng chuyển đổi có giới hạn.
5. Thu hồi key cũ sau khi client đã chuyển.
6. Kiểm tra log và xác nhận không còn request hợp lệ dùng key cũ.

Không nên duy trì vô thời hạn nhiều key cũ “phòng khi cần”. Mỗi key còn hiệu lực là một đường truy cập cần bảo vệ.

### 10.2 Revocation

Khi key bị lộ hoặc không còn cần thiết:

- Đánh dấu key revoked ở nguồn có thẩm quyền.
- Đảm bảo API/gateway kiểm tra trạng thái đủ kịp thời theo yêu cầu rủi ro.
- Xem xét các request đang chạy, cache xác thực và replica.
- Thu hồi hoặc thay credential ở secret manager/workload liên quan.
- Tìm kiếm log để xác định thời điểm, nguồn và phạm vi sử dụng đáng ngờ.
- Nếu key có quyền rộng, kiểm tra dữ liệu và hành động mà nó có thể đã truy cập.

Nếu hệ thống cache kết quả xác minh lâu, trạng thái revoked có thể không có hiệu lực ngay. TTL cache, cơ chế invalidation hoặc introspection cần phù hợp với thời gian phản ứng mong muốn.

## 11. Ví dụ Java: tạo, fingerprint và xác minh

Ví dụ dưới đây minh họa cách sinh 32 byte secret, tạo chuỗi Base64 URL-safe và tính SHA-256 fingerprint để lưu. Trong hệ thống thật, cần thêm quản lý selector, metadata, quyền, lỗi, transaction và secret management.

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class ApiKeySupport {
    private static final SecureRandom RANDOM = new SecureRandom();

    private ApiKeySupport() {
    }

    public static byte[] newSecretBytes() {
        byte[] secret = new byte[32]; // 256 bits
        RANDOM.nextBytes(secret);
        return secret;
    }

    public static String encodeSecret(byte[] secret) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);
    }

    public static byte[] fingerprint(byte[] secret) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return digest.digest(secret);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    public static boolean matches(byte[] presented, byte[] storedFingerprint) {
        byte[] candidate = fingerprint(presented);
        return MessageDigest.isEqual(candidate, storedFingerprint);
    }
}
~~~

Một số điểm cần hiểu:

- **SecureRandom** tạo byte secret; không dùng **Random**.
- 32 byte tương ứng 256 bit trước khi encoding.
- Base64 URL-safe chỉ biểu diễn byte, không mã hóa bí mật.
- SHA-256 fingerprint phù hợp với random secret có entropy cao; nếu dùng HMAC, khóa HMAC phải được quản lý riêng.
- **MessageDigest.isEqual** được dùng để so sánh byte array theo cách giảm rò rỉ thời gian so sánh; cần dùng API phù hợp của runtime và không tự viết vòng lặp dừng sớm.
- **byte[]** chứa secret vẫn có thể tồn tại trong bộ nhớ; Java không bảo đảm xóa tuyệt đối mọi bản sao. Giảm thời gian tồn tại, tránh log và giới hạn việc sao chép.
- Ví dụ không thay thế việc bảo vệ database, backup, secret manager, TLS, scope và revocation.

### Lưu ý khi lưu secret theo dạng chuỗi

Nếu server nhận key ở dạng chuỗi, cần parse/validate định dạng nhất quán, giải mã đúng alphabet và padding policy, giới hạn độ dài trước khi cấp tài nguyên, rồi tính fingerprint trên **byte secret chuẩn hóa**. Tránh nhiều cách biểu diễn tương đương dẫn tới một key có nhiều fingerprint hoặc kiểm tra không nhất quán.

## 12. Những lỗi sinh key thường gặp

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Sinh key từ timestamp hoặc ID tăng dần | Attacker có thể đoán khoảng giá trị. | Dùng CSPRNG cho secret. |
| Dùng **java.util.Random** | Không được thiết kế cho secret mật mã. | Dùng **SecureRandom**. |
| Hash dữ liệu công khai để tạo key | Hash không bổ sung entropy cho đầu vào dễ đoán. | Sinh byte ngẫu nhiên trực tiếp. |
| Secret quá ngắn | Không gian đoán nhỏ, brute force có thể khả thi hơn. | Chọn độ dài/entropy cao, ví dụ 32 byte ngẫu nhiên. |
| Lưu key rõ trong database | Database leak làm lộ credential dùng được ngay. | Lưu hash/HMAC và metadata. |
| Log request header chứa key | Log trở thành kho bearer secret. | Redact header, filter trace và error reporting. |
| Nhúng key trong frontend | Người dùng có thể trích xuất từ bundle hoặc runtime. | Đưa secret về backend; dùng cơ chế client phù hợp. |
| Dùng chung một key cho mọi môi trường | Sự cố test có thể mở đường vào production. | Key riêng theo môi trường và workload. |
| Cấp scope quá rộng | Key bị lộ có phạm vi thiệt hại lớn. | Least privilege và quyền theo endpoint/action. |
| Không có expiry/rotation/revocation | Key cũ tồn tại lâu và khó kiểm soát. | Quản lý vòng đời, rà soát và thu hồi. |
| Hiển thị lại secret sau khi tạo | Buộc hệ thống lưu secret rõ hoặc có thể làm lộ qua UI. | Chỉ hiển thị một lần; tạo key mới nếu mất. |
| Dùng API key để đại diện người dùng cuối | Không phân biệt client và người dùng, dễ nhầm quyền. | Dùng mô hình ủy quyền/identity riêng. |

## 13. Kiểm thử chất lượng bộ sinh và hệ thống key

Không nên chỉ kiểm tra “chuỗi có đủ 43 ký tự”. Một bộ sinh đúng cần kiểm tra cả thuộc tính ngẫu nhiên và quy trình lưu trữ/vận hành.

### 13.1 Kiểm tra thiết kế

- [ ] Secret được sinh từ CSPRNG do runtime/hệ điều hành cung cấp.
- [ ] Độ dài byte và entropy được xác định rõ; encoding không làm mất entropy.
- [ ] Không dùng timestamp, ID tuần tự, dữ liệu cá nhân hoặc PRNG không mật mã.
- [ ] Selector và secret được tách rõ; selector không trao quyền khi đứng riêng.
- [ ] Format có thể nhận diện loại key và môi trường nhưng không tiết lộ thông tin nhạy cảm.
- [ ] Key mới không trùng key đã cấp trong phạm vi hệ thống; có ràng buộc uniqueness phù hợp.
- [ ] Server lưu fingerprint/hash/HMAC thay vì secret rõ sau khi cấp.
- [ ] Secret chỉ hiển thị một lần và không xuất hiện trong log/trace/URL.
- [ ] Owner, environment, scope, expiry, status và metadata được lưu.
- [ ] Có rotation, revocation, audit và cách xử lý cache.
- [ ] API kiểm tra key hợp lệ trước khi kiểm tra quyền và thực thi hành động.
- [ ] Frontend công khai không chứa server secret.

### 13.2 Kịch bản kiểm thử

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Sinh số lượng key thử nghiệm lớn | Không có duplicate trong tập thử; không dùng kết quả thống kê đơn lẻ để chứng minh CSPRNG an toàn. |
| Secret ngẫu nhiên được mã hóa Base64 URL-safe | Decode trả đúng số byte dự kiến; không lỗi do padding/alphabet. |
| Selector hợp lệ nhưng secret sai | Request bị từ chối. |
| Secret đúng nhưng key revoked/expired | Request bị từ chối theo trạng thái hiện tại. |
| Key thuộc staging được dùng ở production | Từ chối do môi trường/owner policy không khớp. |
| Key hợp lệ nhưng scope không đủ | Từ chối quyền, không chỉ xác minh key rồi cho qua. |
| Key bị thu hồi trong lúc cache còn dữ liệu cũ | Hành vi thu hồi phù hợp SLA và chính sách cache đã công bố. |
| Key xuất hiện trong log thử nghiệm | Kiểm tra redaction; không có secret rõ. |
| Người dùng quay lại trang quản lý sau khi tạo | Chỉ thấy metadata/prefix đã che, không lấy lại secret đầy đủ. |
| Mất key đã cấp | Có thể tạo key mới, chuyển workload và thu hồi key cũ. |
| Client frontend cố dùng server key | Kiến trúc không phân phối secret có quyền vào bundle công khai. |
| Payload tự khai owner hoặc role khác | Server bỏ qua dữ liệu không đáng tin và lấy owner/scope từ bản ghi key. |

Các test thống kê có thể giúp phát hiện lỗi triển khai hiển nhiên như key rỗng hoặc trùng lặp, nhưng **không chứng minh** một CSPRNG đạt chuẩn mật mã. Chất lượng nguồn ngẫu nhiên cần dựa trên API runtime/nền tảng được tin cậy và review cách sử dụng.

## 14. Threat model ngắn cho việc sinh API key

### Tài sản

- Secret key đang hoạt động.
- Bản ghi selector/fingerprint và metadata owner/scope.
- Quyền truy cập API được key đại diện.
- Secret manager, database, backup, log và pipeline triển khai.

### Tác nhân và mối đe dọa

| Tác nhân | Đường tấn công | Biện pháp |
| --- | --- | --- |
| Người ngoài | Đoán/brute force secret, dò selector, khai thác endpoint cấp key. | Entropy cao, rate limit, response an toàn, authorization cho create/revoke. |
| Kẻ đọc được log | Lấy key từ header, trace hoặc error report. | Redaction, không log secret, kiểm soát quyền và thời gian lưu log. |
| Người có quyền database chỉ đọc | Trích key nếu lưu plaintext. | Lưu hash/HMAC; tách pepper khỏi database. |
| Nội bộ có quyền tạo key | Cấp key scope rộng hoặc cho sai owner. | Least privilege, phê duyệt, audit, policy scope. |
| Kẻ chiếm workload | Đọc secret từ biến môi trường/file/config. | Secret manager, quyền workload tối thiểu, rotation và phát hiện truy cập. |
| Kẻ chiếm pipeline | Chèn key vào artifact hoặc log build. | Secret scanning, CI/CD permissions, masked variables và kiểm soát release. |

### Sơ đồ điểm bảo vệ

~~~mermaid
flowchart TD
    A["Quản trị viên / API cấp key"] --> B["Kiểm tra quyền và policy"]
    B --> C["CSPRNG sinh secret"]
    C --> D["Tạo selector + fingerprint"]
    D --> E[("Lưu hash/HMAC + metadata")]
    C --> F["Trả secret một lần qua kênh bảo vệ"]
    F --> G["Secret manager của workload"]
    G --> H["Client gửi key qua TLS"]
    H --> I["API tra selector và xác minh secret"]
    I --> J["Kiểm tra trạng thái, environment, scope"]
    J --> K["Cho phép hành động đúng quyền"]
    E --> I
~~~

Mỗi mũi tên có rủi ro riêng. Secret có thể lộ ở response tạo key, clipboard, secret manager, biến môi trường, process dump, request header, proxy hoặc log. Vì vậy review không nên dừng ở hàm **SecureRandom**.

## 15. Tự kiểm tra

**Câu 1.** Vì sao API key cần được sinh bằng **SecureRandom** thay vì **java.util.Random**?

**Đáp án:** API key là secret trao quyền truy cập. SecureRandom được thiết kế cho mục đích mật mã và tạo đầu ra khó dự đoán; Random không có bảo đảm đó, nên có thể bị suy đoán khi attacker biết trạng thái hoặc đầu ra liên quan.

**Câu 2.** Một chuỗi có 50 ký tự được ghép từ tên ứng dụng, ngày tạo và số thứ tự. Nó có chắc an toàn hơn key 43 ký tự Base64 ngẫu nhiên không?

**Đáp án:** Không. Độ dài ký tự không bằng entropy. Chuỗi 43 ký tự Base64 từ 32 byte CSPRNG có 256 bit entropy; chuỗi dài có cấu trúc dễ đoán có thể có entropy thấp hơn nhiều.

**Câu 3.** Vì sao nên tách selector và secret?

**Đáp án:** Selector giúp tìm bản ghi mà không cần lưu secret rõ. Secret vẫn là phần bí mật cần kiểm chứng. Nếu selector bị lộ riêng, nó không được trao quyền truy cập.

**Câu 4.** Có thể lưu SHA-256 của API key thay vì secret rõ không?

**Đáp án:** Có thể khi secret được sinh ngẫu nhiên với entropy cao, vì không gian brute force rất lớn. Có thể dùng HMAC với khóa server-side được quản lý riêng để tăng bảo vệ database; đây khác với password hash cho mật khẩu người dùng có entropy thấp.

**Câu 5.** Vì sao Base64 không bảo vệ bí mật?

**Đáp án:** Base64 là encoding, có thể decode trực tiếp về byte gốc. Ai có chuỗi Base64 vẫn có secret và có thể dùng key.

**Câu 6.** Một API key hợp lệ có scope reports:read gửi request ghi dữ liệu. API nên xử lý thế nào?

**Đáp án:** Xác minh key thành công nhưng từ chối request vì scope không đủ. Xác thực client và phân quyền hành động là hai bước riêng.

**Câu 7.** Tại sao không nên gửi API key trong query string?

**Đáp án:** URL có thể bị ghi vào access log, lịch sử trình duyệt, proxy, analytics và referrer; key dễ bị sao chép ngoài ý muốn. Dùng header qua TLS và redaction phù hợp.

**Câu 8.** Khi người dùng làm mất key đã hiển thị một lần, hệ thống có nên lấy lại secret từ database không?

**Đáp án:** Không. Hệ thống nên cấp key mới, phân phối qua kênh bảo vệ, chuyển client và thu hồi key cũ. Việc không lưu secret rõ giúp giảm tác động khi database bị đọc.

**Câu 9.** Nếu một key production bị lộ, đổi key trong database có đủ không?

**Đáp án:** Cần xem cache, workload, secret manager, replica và các request đang chạy; thu hồi key cũ ở nơi có thẩm quyền, cấp key mới, cập nhật client, rà soát log và kiểm tra hành động đã thực hiện.

**Câu 10.** Một backend dùng API key để gọi dịch vụ thay mặt người dùng cuối. API key chứng minh danh tính nào?

**Đáp án:** Thông thường nó chứng minh client/workload được cấp key. Muốn xác định người dùng cuối cần ngữ cảnh xác thực/ủy quyền riêng, không lấy userId do client tự khai.

## Ghi nhớ

**Key generation** là bước tạo ra một bearer credential có secret đủ khó đoán để không thể tìm bằng brute force trong thực tế. Dùng CSPRNG của nền tảng, chọn entropy rõ ràng (ví dụ 32 byte/256 bit), mã hóa byte bằng Base64 URL-safe hoặc hex, tách selector khỏi secret và không tạo secret từ timestamp, ID hay dữ liệu công khai.

Một API key an toàn còn cần được gắn với đúng owner, environment và scope; server chỉ lưu fingerprint/hash hoặc HMAC phù hợp, hiển thị secret một lần, truyền qua TLS, không log và có expiry, rotation, revocation, audit cùng rate limit. **Sinh một chuỗi ngẫu nhiên tốt là điều kiện cần; quản lý và kiểm chứng key trong toàn bộ vòng đời mới quyết định nó có được dùng an toàn hay không.**
