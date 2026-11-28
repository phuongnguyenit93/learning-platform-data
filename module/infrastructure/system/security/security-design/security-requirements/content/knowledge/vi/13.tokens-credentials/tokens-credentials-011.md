# API key lifecycle

## 1. Vòng đời API key là một hợp đồng bảo mật

Một API key bị lộ vẫn có thể được sử dụng sau khi lập trình viên đã đổi biến môi trường, nếu gateway còn chấp nhận key cũ. Ngược lại, xóa key cũ trước khi mọi tiến trình sử dụng key mới có thể làm dừng một tích hợp đang phục vụ khách hàng. Vì vậy, yêu cầu “hệ thống hỗ trợ API key” chưa mô tả đủ hành vi bảo mật cần có.

**API key lifecycle** là tập hợp quy tắc quản lý một API key từ lúc yêu cầu cấp, tạo và bàn giao, qua sử dụng, giám sát và xoay vòng, đến hết hạn, đình chỉ, thu hồi và xử lý dữ liệu còn lại. Mỗi bước cần xác định chủ thể thực hiện, điều kiện chuyển trạng thái, thời hạn có hiệu lực và bằng chứng có thể kiểm chứng.

Trong thiết kế yêu cầu bảo mật, mục tiêu của vòng đời này là biến những rủi ro như đánh cắp credential, quyền tồn đọng và gián đoạn tích hợp thành các điều kiện rõ ràng:

- Một key được cấp cho đúng danh tính máy, đúng môi trường và đúng tập quyền.
- Bên sử dụng nhận được bí mật qua kênh được kiểm soát.
- Mọi request được xét theo trạng thái và quyền hiện hành của key.
- Có thể thay key với thời gian chuyển tiếp hữu hạn.
- Có thể chấm dứt quyền sử dụng trong thời gian đã cam kết.
- Có đủ dấu vết để điều tra mà không làm lộ thêm credential.

OWASP mô tả các giai đoạn tạo, xoay vòng, thu hồi và hết hạn trong vòng đời secret. Đây là nền tảng để đặt câu hỏi thiết kế; trạng thái chi tiết và các ngưỡng trong bài dưới đây là mô hình minh họa, không phải thời hạn bắt buộc do OWASP quy định. [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html#27-secret-lifecycle)

## 2. Xác định API key đại diện cho ai

Trong bài này, API key là một credential bí mật dạng opaque, được server phát hành cho một ứng dụng hoặc service account. Client đưa credential vào request; server tra cứu metadata để quyết định có chấp nhận hay không.

Cần phân biệt ba thành phần:

| Thành phần | Vai trò | Có được dùng như bí mật không? |
|---|---|---|
| `key_id` | Định danh bản ghi credential, phục vụ tra cứu, quản trị và audit | Không; biết ID không được đủ để truy cập |
| Secret ngẫu nhiên | Chứng minh client đang giữ credential | Có; người lấy được secret có thể giả danh client theo mô hình bearer |
| Principal | Danh tính ứng dụng/service account mà key thuộc về | Là đối tượng được cấp quyền, không phải chuỗi key |

Một API key không mặc nhiên xác định người dùng cuối đứng sau request. Nếu ứng dụng đối tác gọi API thay cho nhiều người, hệ thống cần cơ chế nhận diện và phân quyền người dùng riêng khi nghiệp vụ yêu cầu. Không được suy luận “đã xác thực key của ứng dụng” thành “được thao tác mọi dữ liệu của người dùng”.

API key cũng không phải public key trong mật mã bất đối xứng. Tên gọi “key” không nói lên việc credential có được công khai hay không. Một số nhà cung cấp có loại key dành cho ứng dụng công khai với giới hạn riêng; không nên áp dụng giả định của loại key đó cho một secret dùng để truy cập backend.

OWASP lưu ý không dựa riêng vào API key để bảo vệ tài nguyên nhạy cảm hoặc có giá trị cao. Với nghiệp vụ như phê duyệt thanh toán, thiết kế có thể cần danh tính workload mạnh hơn, mTLS, token ngắn hạn hoặc bước xác thực/phê duyệt bổ sung phù hợp. [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#api-keys)

## 3. Tình huống xuyên suốt: tích hợp đọc hóa đơn

Giả sử một nền tảng cung cấp API hóa đơn cho hệ thống ERP của khách hàng. Ứng dụng ERP chỉ cần đọc hóa đơn của tenant đã đăng ký; không được sửa hóa đơn, xem tenant khác hoặc quản lý credential.

Các vai trò được tách như sau:

- **Integration owner:** chịu trách nhiệm nghiệp vụ, liên hệ vận hành và quyết định tích hợp còn cần thiết hay không.
- **Credential administrator:** cấp, giới hạn quyền và thu hồi key trong tenant được phép quản trị.
- **ERP runtime:** sử dụng key để gọi API, không có quyền tự mở rộng scope hoặc cấp key quản trị.
- **Security operator:** xử lý sự cố theo quyền ứng cứu đã được kiểm soát.
- **Gateway và resource service:** thực thi xác thực, giới hạn truy cập và kiểm tra quyền trên tài nguyên.

Principal `erp-invoice-reader` thuộc tenant `tenant-a`, môi trường `production`, với scope `invoice:read`. Đó là phạm vi cần bảo vệ, không phải một chuỗi ký tự do client tự khai để server tin tưởng.

Các giá trị sau được chọn riêng cho ví dụ nhằm làm cho yêu cầu đo được:

| Tham số | Giá trị minh họa | Ý nghĩa cần thống nhất |
|---|---|---|
| Tuổi thọ tối đa | 90 ngày | Thời điểm cấp quyết định `expires_at`; xoay key tạo credential mới |
| Nhắc gia hạn | Trước hạn 7 ngày | Gửi đến owner và kênh vận hành được đăng ký |
| Chuyển tiếp khi xoay bình thường | Tối đa 15 phút | Hai phiên bản có thể cùng hợp lệ trong khoảng này |
| Hiệu lực thu hồi | Trong 15 giây sau khi commit thu hồi | Áp dụng cho quyết định xác thực mới ở mọi gateway phục vụ API |
| Giới hạn lease chấp nhận từ cache | Tối đa 10 giây | Là một phần ngân sách thu hồi, không phải cơ chế duy nhất |
| Số key dùng đồng thời cho một tích hợp | Tối đa 2 | Cho phép chuyển tiếp nhưng ngăn tích lũy key không kiểm soát |

Những số này cần được điều chỉnh theo tác động nghiệp vụ, kiến trúc phân tán và năng lực vận hành. Chọn “90 ngày” mà không có owner, cơ chế triển khai key mới hoặc cảnh báo trước hạn thường chỉ chuyển rủi ro bảo mật thành rủi ro gián đoạn.

## 4. Từ mối đe dọa đến yêu cầu

Trước khi chọn thư viện hoặc gateway, cần ghi rõ điều gì có thể sai và hệ thống phải ngăn hoặc phát hiện bằng cách nào.

| Mối đe dọa | Hậu quả trong tình huống ERP | Yêu cầu cần có |
|---|---|---|
| Key bị commit vào repository | Người ngoài đọc được hóa đơn | Secret không nằm trong mã nguồn; có phát hiện lộ và quy trình thu hồi |
| Một key dùng chung cho mọi khách hàng | Một sự cố ảnh hưởng nhiều tenant | Key gắn một tenant và một principal xác định |
| Tích hợp đã ngừng nhưng key còn sống | Quyền truy cập tồn đọng | Đóng tích hợp kích hoạt thu hồi mọi key liên quan |
| Xoay key tạo thêm quyền | Client đọc được dữ liệu ngoài mục đích ban đầu | Quyền key mới không tự rộng hơn key cũ và quyền hiện hành của principal |
| Gateway giữ cache cũ | Key đã thu hồi tiếp tục được chấp nhận | Có giới hạn độ cũ và thời hạn thực thi thu hồi trên mọi điểm kiểm tra |
| Log ghi toàn bộ credential | Hệ thống quan sát trở thành nguồn phát tán secret | Redact credential ở ứng dụng, proxy, trace và công cụ hỗ trợ |
| Khôi phục snapshot cũ | Key từng bị thu hồi sống lại | Đối chiếu trạng thái thu hồi mới hơn trước khi mở lại lưu lượng |
| Xoay đồng thời từ hai tiến trình | Vượt giới hạn số key hoặc mất thông tin key kế nhiệm | Kiểm soát phiên bản và giao dịch trên cùng tích hợp |

Một yêu cầu tốt không dừng ở “có hỗ trợ thu hồi”. Nó cần chỉ ra ai được thu hồi, mốc thời gian bắt đầu đo, điểm thực thi nào nằm trong phạm vi và bằng chứng nào chứng minh kết quả.

## 5. Mô hình trạng thái của credential

Không cần dùng cùng một state machine cho mọi sản phẩm. Tuy nhiên, phải thống nhất ý nghĩa của từng trạng thái trước khi viết code hoặc kịch bản nghiệm thu.

Mô hình minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Cấp thành công
    ACTIVE --> DRAINING: Có key kế nhiệm, bắt đầu chuyển tiếp
    ACTIVE --> SUSPENDED: Đình chỉ để điều tra
    SUSPENDED --> ACTIVE: Được phê duyệt khôi phục, chưa hết hạn
    ACTIVE --> REVOKED: Thu hồi
    DRAINING --> REVOKED: Kết thúc chuyển tiếp hoặc thu hồi khẩn
    SUSPENDED --> REVOKED: Xác nhận cần chấm dứt credential
    ACTIVE --> EXPIRED: Đến expires_at
    DRAINING --> EXPIRED: Đến expires_at
    SUSPENDED --> EXPIRED: Đến expires_at
~~~

| Trạng thái | Có chấp nhận request không? | Quy tắc chính |
|---|---|---|
| `ACTIVE` | Có, nếu mọi điều kiện xác thực/phân quyền khác đạt | Không đồng nghĩa với toàn quyền |
| `DRAINING` | Có, trước cả `retire_at` và `expires_at` | Chỉ dùng trong chuyển tiếp có giới hạn |
| `SUSPENDED` | Không | Có thể phục hồi theo quy trình nếu chưa bị thu hồi/hết hạn |
| `REVOKED` | Không | Trạng thái kết thúc; không bật lại cùng credential |
| `EXPIRED` | Không | Tạo key mới thay vì kéo dài ngầm key cũ |

Đề nghị cấp key và phê duyệt có thể được lưu trong đối tượng yêu cầu cấp riêng. Không cần tạo một credential hoạt động trước khi hoàn thành các bước đó.

Một key bị nghi đã lộ không nên được đưa vào nhánh “tạm đình chỉ rồi tự bật lại khi cảnh báo biến mất”. Hệ thống phải có chính sách xử lý mức độ nghi ngờ; nếu quyết định thu hồi thì credential cũ kết thúc vĩnh viễn. Việc phục hồi tích hợp dùng credential mới.

Xóa metadata sau thời gian lưu giữ là một bước quản lý dữ liệu, không phải trạng thái giúp key được chấp nhận trở lại.

## 6. Metadata tối thiểu để quản lý vòng đời

Một bảng chỉ có `api_key` và `enabled` thường không đủ để quản lý quyền, xoay key và điều tra sự cố. Metadata nên cho phép trả lời: ai sở hữu key, key được cấp để làm gì, khi nào còn hiệu lực, ai đã thay đổi trạng thái và phiên bản nào là mới nhất.

Ví dụ bản ghi phía phát hành, không chứa secret gốc:

~~~yaml
key_id: key_7f0a
principal_id: erp-invoice-reader
tenant_id: tenant-a
environment: production
display_name: ERP invoice reader
scope:
  - invoice:read
status: ACTIVE
created_at: "2027-01-10T08:00:00Z"
not_before: "2027-01-10T08:00:00Z"
expires_at: "2027-04-10T08:00:00Z"
retire_at: null
created_by: admin-42
owner_contact_id: integration-owner-19
verifier_algorithm: SHA-256
verifier: "<digest dạng binary trong kho dữ liệu; không phải secret>"
credential_version: 1
replaced_by_key_id: null
revoked_at: null
revoked_by: null
revocation_reason: null
~~~

Các ngày và ID trên chỉ là dữ liệu ví dụ.

`tenant_id` và `principal_id` phải được server xác lập từ ngữ cảnh quản trị đáng tin cậy. Một request ghi `tenant_id=tenant-b` không được làm admin của tenant A cấp key cho tenant B.

`last_used_at` có ích cho rà soát nhưng thường được cập nhật bất đồng bộ. Nó không phải bằng chứng tuyệt đối rằng một key không còn được sử dụng. Không đưa việc cập nhật trường này vào đường đi bắt buộc khiến mọi request phụ thuộc một lần ghi cơ sở dữ liệu.

Mọi thay đổi trạng thái, scope hoặc giới hạn phải có phiên bản tăng đơn điệu. Phiên bản giúp consumer xử lý sự kiện trễ và sự kiện đến sai thứ tự mà không áp dụng ngược trạng thái cũ.

## 7. Tạo key và lưu bằng chứng xác thực

### 7.1. Định dạng có thể quản trị

Một định dạng có thể là:

~~~text
ak_live_<key-id>.<random-secret>
~~~

Prefix giúp nhận diện loại credential và hỗ trợ công cụ phát hiện secret. `key-id` giúp tra bản ghi mà không quét toàn bộ kho credential. Phần bí mật phải được sinh từ nguồn ngẫu nhiên mật mã; prefix và ID không được tính thay cho entropy của secret.

Trong thiết kế minh họa, secret gồm 32 byte ngẫu nhiên, tức 256 bit đầu vào ngẫu nhiên. Base64 URL-safe không padding của 32 byte có 43 ký tự; việc mã hóa không làm tăng entropy.

Các yêu cầu cần ghi rõ:

- Key không được tạo từ timestamp, email, ID tăng dần hoặc hàm băm của dữ liệu có thể đoán.
- Secret không do người dùng tự chọn theo quy tắc mật khẩu thông thường.
- ID có ràng buộc duy nhất; nếu xảy ra trùng ID phải sinh lại an toàn.
- Có giới hạn định dạng và độ dài trước khi xử lý credential từ request.
- Prefix môi trường chỉ hỗ trợ nhận diện; server vẫn kiểm tra binding môi trường trong metadata.

### 7.2. Phân biệt nơi xác minh và nơi sử dụng secret

Bên phát hành API thường chỉ cần **xác minh** credential. Với secret ngẫu nhiên đủ mạnh, có thể lưu verifier một chiều thay vì lưu secret ở dạng khôi phục được.

Bên ERP lại cần **sử dụng** secret để gửi request. Bên này phải lưu credential trong secret manager hoặc kho được bảo vệ phù hợp với quyền của workload. Không thể chỉ lưu hash rồi dùng hash thay cho credential gốc, trừ khi giao thức được thiết kế riêng như vậy; làm thế tùy tiện chỉ biến hash thành bearer secret mới.

Nếu hệ thống chọn HMAC làm verifier, khóa HMAC cần được quản lý tách biệt với dữ liệu verifier và có kế hoạch thay phiên bản. Thay khóa HMAC không tự động tương đương với xoay API key của client. Cũng không được giả định có thể tính lại mọi HMAC cũ khi đã không còn secret gốc.

Không áp dụng máy móc cơ chế hash mật khẩu chậm cho mọi request API. Mật khẩu do con người chọn và secret ngẫu nhiên entropy cao có mô hình đoán khác nhau. Quyết định lưu verifier vẫn cần đánh giá rủi ro thực tế và khả năng bảo vệ kho dữ liệu.

### 7.3. Ví dụ Java cho phần sinh và đối chiếu

Đoạn code sau chỉ minh họa cơ chế sinh secret ngẫu nhiên và tạo verifier SHA-256. Phần quản trị, giao dịch, trạng thái và phân quyền được mô tả riêng trong bài; gọi `matches` không đủ để cho phép một request.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

public final class ApiKeyMaterial {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private ApiKeyMaterial() {
    }

    public static String generateRawKey() {
        byte[] idBytes = new byte[16];
        byte[] secretBytes = new byte[32];

        try {
            RANDOM.nextBytes(idBytes);
            RANDOM.nextBytes(secretBytes);

            String keyId = ENCODER.encodeToString(idBytes);
            String secret = ENCODER.encodeToString(secretBytes);
            return "ak_live_" + keyId + "." + secret;
        } finally {
            Arrays.fill(idBytes, (byte) 0);
            Arrays.fill(secretBytes, (byte) 0);
        }
    }

    public static byte[] verifier(String rawKey) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(rawKey.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                    "Required digest unavailable", exception);
        }
    }

    public static boolean matches(String presentedKey, byte[] storedVerifier) {
        byte[] candidate = verifier(presentedKey);
        try {
            return MessageDigest.isEqual(storedVerifier, candidate);
        } finally {
            Arrays.fill(candidate, (byte) 0);
        }
    }
}
~~~

Caller chỉ lưu verifier và metadata, rồi chuyển raw key vào luồng bàn giao một lần được bảo vệ. Không thêm `System.out.println(rawKey)` để chạy thử trên môi trường thật.

`SecureRandom` cung cấp bộ sinh ngẫu nhiên phù hợp mục đích mật mã; không seed thủ công bằng thời gian hiện tại. `MessageDigest` cung cấp SHA-256 và phương thức đối chiếu digest. [Java SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html), [Java MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)

Việc xóa các mảng byte trong ví dụ chỉ giảm một số bản sao tạm. Các chuỗi Java và bản sao do thư viện tạo không được đảm bảo xóa khỏi bộ nhớ ngay lập tức. Yêu cầu bảo vệ secret không nên hứa “xóa sạch bộ nhớ” chỉ dựa vào `Arrays.fill`.

## 8. Cấp và bàn giao key một lần

Luồng cấp bình thường có thể gồm các bước:

1. Người quản trị đăng nhập bằng cơ chế quản trị thích hợp và chọn đúng tích hợp.
2. Server xác minh quyền cấp credential, tenant, môi trường, scope và giới hạn số key.
3. Server sinh credential, lưu verifier và metadata trong giao dịch.
4. Sau khi giao dịch thành công, server trả raw key một lần qua kênh TLS.
5. Client chuyển raw key vào kho secret được cấp cho workload cần sử dụng.
6. Các lần đọc thông tin sau chỉ trả ID, trạng thái, scope và thông tin quản trị được phép.

Response chứa raw key cần có chính sách không lưu cache phù hợp, chẳng hạn `Cache-Control: no-store`, đồng thời cấu hình để gateway, APM và hệ thống ghi response không ghi payload này. Không đưa secret vào email, ticket hỗ trợ, ảnh chụp màn hình dùng chung hoặc kết quả CI.

“Hiển thị một lần” cũng phải áp dụng cho API quản trị, không chỉ giao diện. Nếu giao diện che key nhưng endpoint `GET /keys/{id}` vẫn trả toàn bộ secret thì yêu cầu chưa đạt.

### Khi response bị mất

Có một khoảng lỗi quan trọng: server đã lưu key nhưng client không nhận được response. Nếu hệ thống chỉ lưu verifier, server không thể hiển thị lại raw key cũ.

Contract cần chọn cách xử lý, ví dụ:

- Retry với cùng idempotency key không tạo thêm credential không giới hạn.
- Server trả thông tin rằng thao tác cấp đã được ghi nhận, nhưng không trả lại secret đã mất.
- Người có quyền thu hồi credential chưa sử dụng được rồi cấp credential mới.
- Kịch bản cấp lại vẫn chịu giới hạn số key và được ghi audit.

Nếu sản phẩm cần phát lại secret trong một khoảng ngắn, phải thiết kế riêng kho payload mã hóa, kiểm soát truy cập, TTL và cơ chế xóa. Không được âm thầm lưu raw key trong bảng thông thường chỉ để làm retry dễ hơn.

Hai request cấp đồng thời phải kiểm tra giới hạn trong giao dịch hoặc cơ chế tương đương. Kiểm tra “đang có một key” ở ứng dụng rồi cùng chèn thêm hai key có thể phá vỡ chính sách tối đa hai key.

## 9. Xác thực và phân quyền trong lúc sử dụng

Một request chỉ được phép tiếp tục khi mọi điều kiện liên quan cùng đúng:

~~~text
allow =
    credential_format_valid
    AND verifier_matches
    AND status_allows_use
    AND now >= not_before
    AND now < expires_at
    AND (retire_at is absent OR now < retire_at)
    AND principal_is_enabled
    AND tenant_binding_matches
    AND environment_binding_matches
    AND scope_allows_operation
    AND resource_belongs_to_authorized_tenant
    AND contextual_restrictions_pass
~~~

Đây là mô hình logic, không bắt buộc mọi kiểm tra đều ở cùng một tiến trình. Kiến trúc phải chỉ rõ gateway kiểm tra gì, resource service kiểm tra gì và cách truyền danh tính nội bộ mà client không thể giả mạo.

Ví dụ minh họa sử dụng header:

~~~http
GET /v1/invoices/invoice-172 HTTP/1.1
Host: api.example.invalid
X-API-Key: <credential được lấy từ secret manager>
~~~

`X-API-Key` ở đây là tên header do API ví dụ quy định. Không mặc định mọi nhà cung cấp dùng cùng tên hoặc cùng cơ chế.

Không đưa key vào URL hoặc query string vì URL thường đi qua nhiều lớp ghi nhận. Google cũng hướng dẫn tránh truyền API key qua query parameter, tách key theo ứng dụng và xóa key không còn cần thiết; các hướng dẫn này hỗ trợ việc thiết kế kênh truyền và giới hạn phạm vi credential. [Google Cloud: Best practices for managing API keys](https://docs.cloud.google.com/docs/authentication/api-keys-best-practices)

Các chi tiết dễ bị bỏ sót:

- Quy định cách xử lý header lặp; không để proxy và backend chọn hai giá trị khác nhau.
- Chỉ tin danh tính do gateway truyền khi request đến từ kênh nội bộ được xác thực và header từ phía client đã được xử lý.
- Không cho phép key đọc hóa đơn của tenant A truy cập hóa đơn tenant B chỉ vì cùng có scope `invoice:read`.
- Hạn chế IP chỉ có ý nghĩa khi nguồn IP được xác định từ proxy đáng tin cậy; không tin trực tiếp `X-Forwarded-For` do client gửi.
- Đổi hoặc khóa principal phải ảnh hưởng các key liên quan theo thời hạn đã quy định.
- Rate limit cần gắn cả principal/tenant khi cần; xoay sang key mới không được dùng để vượt quota tích hợp.

API key hợp lệ chứng minh một điều kiện của quyền truy cập. Nó không thay thế kiểm tra quyền trên từng tài nguyên.

## 10. Hết hạn phải được thực thi trên đường request

Job chạy mỗi đêm để đổi trạng thái hết hạn có ích cho báo cáo, nhưng không đủ để thực thi `expires_at`. Nếu job chạy chậm, credential đã quá hạn vẫn phải bị từ chối.

Trong mô hình này:

- Khoảng hợp lệ có cận trên mở: khi `now == expires_at`, key không còn hợp lệ.
- `DRAINING` cũng không vượt qua `expires_at`.
- `retire_at` có thể kết thúc hiệu lực sớm hơn thời điểm hết hạn.
- Gia hạn tích hợp không tự sửa thời hạn key hiện có; quy trình bình thường cấp key kế nhiệm.
- Hệ thống đồng bộ thời gian và đưa sai lệch đồng hồ vào ngân sách thực thi.

Nếu lựa chọn cho phép độ lệch thời gian, phải ghi rõ độ lệch cho `not_before` và `expires_at`. Tự thêm vài phút “để tránh lỗi giờ” có thể kéo dài thời gian khai thác ngoài hợp đồng bảo mật.

Đến hạn mà ERP chưa triển khai key mới là một tình huống vận hành cần cảnh báo và xử lý. Không nên giải quyết bằng việc âm thầm bật key hết hạn trở lại.

## 11. Xoay vòng bình thường: thay credential mà giữ đúng quyền

Xoay vòng là cấp credential mới và kết thúc credential cũ theo một quy trình xác định. Chỉ đổi tên hiển thị hoặc cập nhật ngày hết hạn của cùng secret không đạt mục tiêu thay vật liệu bí mật.

Luồng chuyển tiếp cho ví dụ ERP:

1. Xác minh owner và quyền hiện hành của tích hợp.
2. Tạo key B với secret mới; scope không tự rộng hơn key A.
3. Gắn quan hệ A được thay bởi B; đánh dấu A là `DRAINING` với `retire_at` hữu hạn.
4. Bàn giao B qua kênh được bảo vệ và cập nhật ERP.
5. Kiểm tra các nhóm tiến trình đã dùng B, gồm worker nền, tác vụ lịch và instance ít lưu lượng.
6. Kết thúc chấp nhận A không muộn hơn `retire_at` hoặc `expires_at`, tùy mốc đến trước.
7. Ghi nhận kết quả và đóng tác vụ xoay vòng.

Có thể dùng thời gian như sau:

~~~text
T0              T0 + 5 phút                 T0 + 15 phút
| Cấp B         | ERP đã chuyển phần lớn    | A kết thúc hiệu lực
| A: DRAINING   | Kiểm tra instance còn sót | Chỉ B được chấp nhận
| B: ACTIVE     | Không tự kéo dài A        | A: REVOKED hoặc EXPIRED
~~~

Điểm cần kiểm soát là **thời hạn kết thúc A**, không chỉ thời điểm tạo B. Không được để A và B cùng hoạt động vô thời hạn vì “chưa thấy lỗi”.

Nếu A sắp hết hạn trong ba phút, cửa sổ chuyển tiếp không biến thành mười lăm phút sau hạn. Khi đó cần triển khai sớm hơn hoặc có quyết định xử lý vận hành riêng; không tự thay đổi nghĩa `expires_at`.

### Kiểm soát rollback và xoay đồng thời

Rollback cấu hình ERP có thể dùng lại A chỉ khi A vẫn còn trong cửa sổ hợp lệ và chưa bị thu hồi. Khi A đã `REVOKED`, rollback phải dùng một credential mới phù hợp; không phục hồi cùng secret cũ.

Nếu hai quản trị viên cùng yêu cầu xoay, server phải điều phối bằng khóa, kiểm tra version hoặc giao dịch có ràng buộc tương đương. Chỉ một kế hoạch chuyển tiếp hợp lệ được áp dụng cho cùng phiên bản hiện hành. Retry có idempotency không được sinh thêm cặp key ngoài chính sách.

Một key cũ được tạo từ principal hiện có nhưng principal vừa bị giảm quyền cũng không được trở thành nguồn để key mới giữ quyền đã bị loại bỏ. Quyền được cấp cho key mới phải nằm trong cả phạm vi đề nghị hợp lệ và quyền hiện hành được chính sách cho phép.

## 12. Thu hồi: thời điểm ghi dữ liệu khác thời điểm chặn truy cập

Thu hồi là yêu cầu chấm dứt khả năng sử dụng credential trước hạn hoặc kết thúc credential không còn cần thiết. Các tác nhân thường gồm owner yêu cầu, đóng tích hợp, vi phạm chính sách hoặc phản ứng sự cố.

Cần phân biệt:

- **Mốc commit thu hồi:** trạng thái `REVOKED` được ghi bền vững ở nguồn có thẩm quyền.
- **Mốc hiệu lực ở điểm kiểm tra:** gateway/resource service quyết định từ chối key.
- **Mốc xác nhận thu hồi:** hệ thống có bằng chứng các điểm phục vụ đáp ứng cam kết.

Một response thành công từ API quản trị không tự chứng minh rằng tất cả cache đã được vô hiệu hóa.

### 12.1. Contract thời gian có thể kiểm chứng

Yêu cầu minh họa:

> Với key K bị thu hồi và commit tại thời điểm T, mọi quyết định xác thực mới tại gateway phục vụ API từ T + 15 giây trở đi phải từ chối K, kể cả khi một sự kiện vô hiệu hóa cache bị mất.

Tiêu chí này đo quyết định xác thực mới. Một request đã được cho phép trước thời điểm đó có thể đang xử lý. Nghiệp vụ cần dừng cả tác vụ đang chạy hoặc tránh commit một giao dịch nhạy cảm sau thu hồi phải có yêu cầu kiểm tra lại ở ranh giới nghiệp vụ tương ứng.

Không nên hứa “thu hồi ngay lập tức” nếu hệ thống thực tế cho phép cache chấp nhận key thêm năm phút.

### 12.2. Thiết kế hỗ trợ contract

Một phương án cho ví dụ:

- Trạng thái credential ở nguồn có thẩm quyền là dữ liệu quyết định.
- Sự kiện thay đổi trạng thái được phát bền vững, chẳng hạn qua transactional outbox.
- Gateway vô hiệu hóa cache theo `key_id` và chỉ áp dụng phiên bản mới hơn.
- Bản ghi cache cho phép chấp nhận có lease tối đa 10 giây.
- Gia hạn lease phải dựa vào dữ liệu đủ mới từ nguồn có thẩm quyền; không làm mới thời gian sống bằng cách đọc lại một snapshot cũ tùy ý.
- Khi không xác minh được độ mới sau khi lease hết, gateway không tiếp tục chấp nhận key bằng cache cũ.

Mười giây lease chỉ là một phần thiết kế. Độ trễ replica, sai lệch đồng hồ, thời gian xử lý và các điểm xác thực ngoài gateway vẫn phải nằm trong ngân sách mười lăm giây đã chọn.

Chỉ có TTL mà không giới hạn độ cũ của nguồn nạp cache vẫn có thể thất bại: gateway hết TTL, đọc lại replica chưa cập nhật rồi tiếp tục chấp nhận key.

Một denylist có thể là thành phần bổ sung nhưng cũng cần kiểm soát độ mới và tính sẵn sàng. Đặt tên cơ chế là “denylist” không làm mất bài toán phân phối trạng thái.

### 12.3. Thu hồi khẩn khác xoay bình thường

Khi xác nhận key A bị lộ, không mặc định dành cửa sổ chuyển tiếp mười lăm phút cho A. Quy trình sự cố thu hồi A theo cam kết khẩn cấp, sau đó khôi phục tích hợp bằng credential mới được cấp và bàn giao qua kênh còn đáng tin cậy.

Nếu secret manager của ERP cũng bị xâm nhập, chỉ đưa B vào cùng kho chưa được xử lý có thể làm lộ tiếp B. Quy trình cần xác định lại vùng tin cậy trước khi cấp credential thay thế.

## 13. API quản trị và audit

Một giao diện quản trị có thể cung cấp các thao tác dưới đây. Đây là contract minh họa, không phải tên route bắt buộc.

| Thao tác | Hành vi cần quy định |
|---|---|
| `POST /integrations/{id}/keys` | Kiểm tra quyền, quota và scope; trả raw key chỉ ở response cấp thành công |
| `GET /integrations/{id}/keys` | Trả metadata được phép; không trả secret hoặc verifier |
| `POST /keys/{id}/rotate` | Tạo key kế nhiệm theo cùng giới hạn; kiểm soát retry và cạnh tranh |
| `POST /keys/{id}/suspend` | Đình chỉ theo quyền và lý do; không tự phục hồi khi hết một bộ đếm tùy ý |
| `POST /keys/{id}/revoke` | Thu hồi có audit; gọi lại không bật key và không tạo hiệu ứng cấp mới |

Admin của tenant A không được quản trị key tenant B qua việc thay ID trên URL. Cần thống nhất chính sách response để tránh tiết lộ thông tin credential của tenant khác.

Một audit event có thể chứa:

~~~json
{
  "event_type": "api_key.revoked",
  "key_id": "key_7f0a",
  "principal_id": "erp-invoice-reader",
  "tenant_id": "tenant-a",
  "actor_id": "security-operator-12",
  "reason_code": "CONFIRMED_EXPOSURE",
  "credential_version": 4,
  "occurred_at": "2027-02-02T09:10:00Z",
  "request_id": "req-9021",
  "outcome": "SUCCESS"
}
~~~

Không ghi raw key, header chứa key, verifier hoặc response cấp secret vào event. Nhận diện credential bằng ID nội bộ được kiểm soát đủ để nối sự kiện mà không sao chép bí mật vào hệ thống log.

Yêu cầu audit cần bao gồm tạo, thay quyền, xoay, đình chỉ, phục hồi được phép, thu hồi và những hành vi quản trị bị từ chối. Ai được đọc audit và thời gian lưu cũng cần được xác định.

Các chỉ số hữu ích gồm số key gần hết hạn, key không có owner, thời gian lan truyền thu hồi, tỷ lệ gọi bằng key hết hạn và tỷ lệ lưu lượng còn dùng key cũ trong chuyển tiếp. Tránh đưa credential hoặc ID có số lượng quá lớn vào nhãn metric không được kiểm soát.

## 14. Backup, phục hồi và kết thúc lưu giữ

Khôi phục kho credential từ bản backup cũ có thể khôi phục cả trạng thái `ACTIVE` của một key đã bị thu hồi. Đây là lỗi bảo mật dù quy trình phục hồi dữ liệu chạy thành công.

Yêu cầu phục hồi cần nêu rõ:

1. Backup chứa verifier và metadata được bảo vệ tương xứng.
2. Bản ghi thu hồi/sự kiện vòng đời được lưu bền vững theo cơ chế đáp ứng mục tiêu phục hồi.
3. Trước khi mở API sau restore, hệ thống đối chiếu thay đổi mới hơn snapshot, đặc biệt các credential bị thu hồi.
4. Cache cũ không được coi là nguồn chuẩn để tái tạo trạng thái.
5. Nếu chưa xác định được trạng thái hiện hành, key không được tự động chấp nhận.

Nếu không thể phục hồi đầy đủ lịch sử thu hồi, có thể cần một cơ chế khẩn cấp như vô hiệu hóa toàn bộ tập key bị ảnh hưởng và cấp lại. Quyết định này phải nằm trong kế hoạch phục hồi, kèm tác động tới tích hợp.

Về lưu giữ, hệ thống có thể xóa verifier sau khi credential kết thúc và hết thời hạn cần thiết, trong khi giữ audit/tombstone tối thiểu theo chính sách. Cần tránh tái sử dụng ID khiến credential cũ bị nhầm là credential mới.

“Xóa key” ở hệ thống đang chạy không có nghĩa là mọi bản sao trong backup đã biến mất ngay. Chính sách phải nói rõ chu kỳ hết hạn backup và cơ chế kiểm soát truy cập trong thời gian còn lưu.

## 15. Bộ yêu cầu mẫu có thể đưa vào đặc tả

Các yêu cầu dưới đây dùng cho tình huống ERP và các ngưỡng đã chọn. Chúng là ví dụ cách diễn đạt, cần được xét lại theo phân loại dữ liệu và kiến trúc thật.

| ID | Yêu cầu | Bằng chứng nghiệm thu dự kiến |
|---|---|---|
| AK-LC-01 | Mỗi key gắn với một principal, tenant và môi trường do server xác lập | Thử cấp/call bằng binding ngoài phạm vi và xác nhận bị từ chối |
| AK-LC-02 | Secret được tạo từ 32 byte ngẫu nhiên mật mã; ID công khai không được dùng thay secret | Đối chiếu cơ chế sinh và thử chỉ gửi ID |
| AK-LC-03 | Kho xác minh không lưu raw key; API đọc metadata không trả secret/verifier | Kiểm tra dữ liệu lưu và response của API quản trị |
| AK-LC-04 | Raw key chỉ được bàn giao ở thao tác cấp thành công qua kênh được bảo vệ | Kiểm tra response, cache policy và đường ghi log/trace |
| AK-LC-05 | Mọi quyết định truy cập kiểm tra trạng thái, thời hạn và quyền trên tài nguyên | Các ca revoked, expired, sai scope và sai tenant đều bị từ chối |
| AK-LC-06 | Xoay bình thường giới hạn chuyển tiếp tối đa 15 phút và không vượt hạn key cũ | Gọi cả key ở trước/sau các ranh giới thời gian |
| AK-LC-07 | Thu hồi có hiệu lực trên quyết định xác thực mới trong 15 giây sau commit | Đo từng gateway, gồm tình huống mất sự kiện và cache cũ |
| AK-LC-08 | Không chấp nhận key qua cache khi không còn bằng chứng đủ mới theo lease | Ngắt kết nối nguồn trạng thái và đo hành vi sau lease |
| AK-LC-09 | Tối đa hai key sử dụng đồng thời cho một tích hợp, kể cả cấp/xoay cạnh tranh | Gửi các yêu cầu đồng thời và kiểm tra kết quả giao dịch |
| AK-LC-10 | Key mới không tự nhận quyền vượt chính sách hiện hành của principal | Giảm quyền principal rồi thực hiện xoay |
| AK-LC-11 | Thu hồi và thay đổi vòng đời có audit không chứa credential | Kiểm tra event theo actor, key ID, version và reason |
| AK-LC-12 | Restore không tái kích hoạt credential đã bị thu hồi sau thời điểm snapshot | Phục hồi bản backup cũ trong môi trường kiểm chứng |

Đối với yêu cầu có thời gian, cần ghi rõ nguồn mốc thời gian và cách đo. Ví dụ AK-LC-07 không nên chỉ dựa trên timestamp do client không đồng bộ tự gửi lên.

Các “bằng chứng nghiệm thu dự kiến” là phần của thiết kế yêu cầu. Chúng chưa phải kết luận hệ thống hay nội dung bài đã được kiểm thử.

## 16. Những kịch bản ranh giới cần đặc tả

### 16.1. Đến đúng thời điểm hết hạn

**Given:** key A còn trạng thái lưu là `ACTIVE`, nhưng `expires_at` đã đến.

**When:** gateway nhận request và thực hiện quyết định xác thực tại đúng thời điểm hết hạn.

**Then:** key A bị từ chối, dù job cập nhật trạng thái nền chưa chạy.

Kịch bản này phân biệt thời gian hiệu lực với nhãn trạng thái phục vụ quản trị.

### 16.2. Chuyển tiếp bình thường

**Given:** A đang `DRAINING` và B đang `ACTIVE`, cả hai cùng thuộc một principal.

**When:** ERP triển khai B, sau đó một instance cũ tiếp tục gửi A qua `retire_at`.

**Then:** B vẫn hoạt động trong phạm vi quyền cho phép; A bị từ chối. Instance cũ tạo tín hiệu vận hành để owner xử lý, không kéo dài A tự động.

### 16.3. Sự kiện thu hồi bị mất

**Given:** gateway G đang cache A hợp lệ và chưa nhận được event thu hồi.

**When:** A bị thu hồi ở nguồn có thẩm quyền và G không thể cập nhật trạng thái.

**Then:** G chỉ chấp nhận trong giới hạn lease còn được phép; sau đó từ chối vì không thể chứng minh trạng thái đủ mới. Các quyết định từ T + 15 giây phải đáp ứng yêu cầu thu hồi.

### 16.4. Quyền principal thay đổi

**Given:** key A từng có `invoice:read` và `invoice:export`, nhưng principal đã bị bỏ quyền export.

**When:** admin yêu cầu xoay A.

**Then:** key B không được tự thừa hưởng quyền export đã bị loại bỏ. Key A cũng phải chịu hiệu lực giảm quyền theo contract của hệ thống.

### 16.5. Cấp thành công nhưng mất response

**Given:** server đã commit key B, client mất kết nối trước khi nhận secret.

**When:** client retry cùng yêu cầu cấp.

**Then:** không tạo thêm key ngoài chính sách và không hiển thị lại secret trái với contract một lần. Luồng thu hồi/cấp lại được thực hiện bởi chủ thể có quyền.

### 16.6. Khôi phục backup trước sự cố

**Given:** snapshot ghi A là `ACTIVE`; sau snapshot, A bị thu hồi vì lộ.

**When:** hệ thống phục hồi từ snapshot đó.

**Then:** API chưa mở lại cho A trước khi đối chiếu trạng thái mới hơn. A vẫn bị chặn sau phục hồi.

### 16.7. Principal hoặc tenant bị vô hiệu hóa

**Given:** key còn secret đúng và chưa tới hạn.

**When:** principal hoặc tenant liên quan bị khóa theo chính sách.

**Then:** key không tiếp tục được chấp nhận chỉ vì verifier vẫn khớp. Thời gian hiệu lực khóa cần được đặc tả giống các thay đổi quyền khác.

## 17. Ví dụ xử lý một sự cố

Một tác vụ CI vô tình đưa key A của ERP vào artifact có người ngoài truy cập được. Nhóm vận hành phát hiện và cần vừa giới hạn thiệt hại vừa khôi phục tích hợp.

Quy trình theo thiết kế:

1. Ghi nhận ID credential và phạm vi ảnh hưởng mà không sao chép raw key sang ticket.
2. Thu hồi A qua kênh quản trị/ứng cứu được xác thực; lưu actor, lý do và mốc commit.
3. Xác nhận các điểm xác thực đáp ứng thời hạn thu hồi; theo dõi request tiếp tục dùng A.
4. Bảo vệ hoặc thay thế đường bàn giao secret và cấu hình CI gây lộ.
5. Cấp B cho đúng principal/tenant với quyền tối thiểu hiện hành.
6. Triển khai B vào kho secret của ERP; kiểm tra các tiến trình nền và tác vụ lịch liên quan.
7. Điều tra hoạt động bằng A trong khoảng phơi lộ, xử lý tác động dữ liệu và thông báo theo quy trình của tổ chức.
8. Đóng sự cố khi credential cũ đã bị chặn, credential mới sử dụng ổn định và nguyên nhân lộ được xử lý.

Cấp B ở bước đầu nhưng để A còn hoạt động vì sợ gián đoạn không phải là thu hồi. Đồng thời, xóa artifact hay sửa commit không chứng minh rằng A chưa từng bị sao chép.

## 18. Những cách viết yêu cầu dễ gây hiểu sai

| Cách viết thiếu rõ ràng | Vấn đề | Cách làm rõ |
|---|---|---|
| “API key được lưu an toàn” | Không biết ai giữ secret và ai chỉ cần verifier | Chỉ rõ dữ liệu lưu, kho lưu, chủ thể truy cập và đường bàn giao |
| “Có nút revoke” | Không nói thời gian thực thi ở gateway | Định nghĩa mốc commit, thời hạn và phạm vi quyết định bị chặn |
| “Key rotate mỗi 90 ngày” | Không có cửa sổ triển khai hoặc kết thúc key cũ | Thêm owner, cảnh báo, key kế nhiệm và `retire_at` |
| “Key thuộc tenant hiện tại” | Client có thể tự khai tenant | Server xác lập binding và kiểm tra quyền trên tài nguyên |
| “Đã hash thì không cần bảo vệ database” | Verifier, metadata và quyền ghi vẫn có giá trị bảo mật | Bảo vệ kho dữ liệu và ngăn sửa trái phép trạng thái/quyền |
| “Hết TTL sẽ tự an toàn” | Cache có thể nạp lại từ nguồn cũ | Giới hạn cả lease và độ mới của nguồn trạng thái |
| “Đã xóa key khỏi production” | Backup có thể làm key sống lại | Thêm yêu cầu phục hồi và duy trì bằng chứng thu hồi |
| “Rollback về key cũ nếu lỗi” | Có thể bật lại credential đã bị thu hồi | Chỉ rollback khi key cũ vẫn hợp lệ; trường hợp khác cấp credential mới |

## 19. Bài tập áp dụng

Hãy đặc tả vòng đời key cho một dịch vụ đối tác chỉ được tạo vận đơn, không được hủy vận đơn và không được quản lý credential.

Tài liệu cần trả lời được:

1. Principal nào đứng sau key, tenant nào sở hữu và ai là owner?
2. Secret được tạo, bàn giao và lưu ở từng bên như thế nào?
3. Những trạng thái nào chấp nhận request, trong khoảng thời gian nào?
4. Xoay bình thường và thu hồi do lộ credential khác nhau ở điểm nào?
5. Khi gateway mất kết nối nguồn trạng thái, hệ thống chấp nhận rủi ro ra sao?
6. Nếu restore snapshot trước một lần thu hồi, điều gì ngăn key cũ hoạt động lại?
7. Từng yêu cầu sẽ được chứng minh bằng trường hợp và bằng chứng nào?

Một đặc tả hoàn chỉnh cho phép người xây dựng API, người vận hành và người nghiệm thu cùng xác định được thời điểm một credential được phép sử dụng và thời điểm nó phải bị từ chối. Đó là giá trị cốt lõi của việc thiết kế API key lifecycle trong yêu cầu bảo mật.
