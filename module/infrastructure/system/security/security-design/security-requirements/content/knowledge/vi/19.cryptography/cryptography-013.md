# Không dùng thuật toán lỗi thời

## 1. Yêu cầu không dừng ở việc xóa một tên thuật toán

Một hệ thống có thể đã dùng thuật toán hiện đại ở chức năng chính nhưng vẫn tạo dữ liệu mới bằng một profile cũ trong job nền, chấp nhận một cipher suite yếu ở host phụ hoặc fallback khi đối tác không tương thích. Vì vậy, “không dùng thuật toán lỗi thời” phải là yêu cầu về **hành vi có hiệu lực**, không chỉ là kết quả tìm kiếm trong source.

Yêu cầu cần trả lời:

- Thuật toán, cấu hình hoặc giao thức nào không còn được phép cho mục đích đang xét?
- Cấm tạo bảo vệ mới hay cấm cả đọc và xác minh dữ liệu lịch sử?
- Áp dụng tại ứng dụng, TLS, key manager, công cụ quản trị và backup nào?
- Có ngoại lệ được kiểm soát không, ai phê duyệt và hết hạn khi nào?
- Khi không còn lựa chọn phù hợp, hệ thống phải thất bại thế nào?
- Dữ liệu cũ được chuyển đổi và kiểm chứng ra sao trước khi ngừng khả năng đọc?

Một yêu cầu chưa đủ rõ:

> Không được dùng DES, MD5 và SHA-1.

Một cách diễn đạt có thể triển khai hơn:

> Mọi thao tác tạo ciphertext, MAC, chữ ký hoặc password verifier mới phải sử dụng profile được phê duyệt cho đúng mục đích. Profile đã ngừng tạo mới không được lựa chọn từ cấu hình, metadata đầu vào hoặc đường fallback. Việc đọc dữ liệu lịch sử, nếu còn cần, phải đi qua phạm vi và thời hạn chuyển đổi đã được phê duyệt.

Hướng dẫn chuyển đổi thuật toán và độ dài khóa là một cơ sở để xây dựng chính sách. Ví dụ, [NIST SP 800-131A Rev. 2](https://csrc.nist.gov/pubs/sp/800/131/a/r2/final) đề cập việc chuyển sang thuật toán và khóa mạnh hơn. Khi áp dụng thực tế, phải kiểm tra bản sửa đổi, trạng thái và thông báo cập nhật phù hợp thời điểm quyết định, thay vì coi một danh sách trong tài liệu cũ là chính sách bất biến.

## 2. Phân loại đúng vấn đề trước khi thay đổi

### 2.1. Thuật toán yếu, cấu hình sai và implementation có lỗi không giống nhau

| Loại vấn đề | Ví dụ | Hướng xử lý chính |
| --- | --- | --- |
| Thuật toán không còn phù hợp mục tiêu | Hash có vấn đề chống va chạm dùng để ký mới | Chuyển profile và quản lý dữ liệu/chữ ký liên quan |
| Độ dài khóa không đủ theo policy | Khóa bất đối xứng dưới mức đã phê duyệt | Tạo khóa phù hợp và chuyển đổi các phụ thuộc |
| Mode hoặc construction không phù hợp | Mã hóa bản ghi bằng ECB hoặc thiếu xác thực | Sửa construction và định dạng dữ liệu |
| Tham số dùng sai | Nonce lặp dưới cùng key AEAD | Sửa cơ chế cấp phát, key và đánh giá dữ liệu ảnh hưởng |
| Giao thức hoặc bộ cấu hình lỗi thời | Kết nối còn chấp nhận phiên bản TLS đã ngừng | Sửa chính sách giao thức trên mọi đường kết nối |
| Implementation hoặc phiên bản không còn được duy trì | Provider có lỗ hổng hoặc hết hỗ trợ | Nâng/thay implementation, kiểm chứng cấu hình và tương thích |

Không gộp tất cả thành “thuật toán đã bị phá”. Một primitive chuẩn có thể bị dùng sai; một thuật toán chưa bị phá về toán học vẫn có thể không đáp ứng policy, mức an toàn hoặc thời hạn bảo vệ của hệ thống.

Ngược lại, nâng thư viện không tự chuyển đổi mọi ciphertext cũ hoặc thay một key yếu đã được tạo trước đó. Phải xác định lớp nào thay đổi và tài sản nào vẫn còn phụ thuộc cơ chế cũ.

### 2.2. Tên mới hoặc số bit lớn không bảo đảm đúng

Một khóa lớn hơn không bù cho mode sai, nonce lặp, thiếu xác thực hoặc bí mật bị hard-code. Đổi `SHA-1` thành `SHA-256` cũng không tự biến hash một vòng thành cơ chế lưu mật khẩu phù hợp.

AES không bị coi là lỗi thời chỉ vì một cấu hình AES-ECB không đáp ứng yêu cầu bảo vệ bản ghi. CBC không tự cung cấp tính chất AEAD; nếu dùng một construction có CBC trong một giao thức được phê duyệt, cần đánh giá đầy đủ construction chứ không suy từ một từ khóa.

Do đó, đơn vị policy nên là profile theo purpose, gồm thuật toán, mode, tham số, key, implementation và giới hạn sử dụng. Một denylist tên thuật toán chỉ hỗ trợ một phần kiểm soát.

## 3. Các trường hợp điển hình và phạm vi kết luận

### 3.1. MD5 và SHA-1 trong các mục đích phụ thuộc chống va chạm

Nếu một chữ ký hoặc cơ chế bảo vệ toàn vẹn cần tính chống va chạm, việc dùng một hash có va chạm thực tế là vấn đề quan trọng. [RFC 6151](https://www.rfc-editor.org/rfc/rfc6151.html) giải thích MD5 không còn phù hợp ở nơi cần collision resistance và phân biệt các bối cảnh sử dụng, gồm HMAC-MD5.

Không đồng nhất tấn công collision với việc tìm lại mọi mật khẩu hoặc mọi thông điệp ban đầu. Với password verifier dùng MD5 nhanh, rủi ro đoán offline còn đến từ chi phí tính rất thấp và cách dùng không phù hợp mục đích, không cần dựa vào một collision attack để có vấn đề.

NIST cũng đã công bố khuyến nghị chuyển khỏi SHA-1 cho bảo vệ an ninh; xem [NIST Retires SHA-1 Cryptographic Algorithm](https://www.nist.gov/news-events/news/2022/12/nist-retires-sha-1-cryptographic-algorithm). Hồ sơ chuyển đổi phải đối chiếu mục đích và chính sách hiện hành, không suy rằng mọi tham chiếu SHA-1 ở mọi tầng có cùng mức rủi ro hoặc cùng semantics.

Một tổ chức có thể cấm tạo mới mọi profile chứa SHA-1 trong phạm vi sản phẩm theo policy của mình. Quyết định đó cần được ghi đúng là policy có phạm vi; không trình bày nó như bằng chứng rằng mọi construction dùng SHA-1 bị phá theo cùng một cách.

### 3.2. DES và TDEA/3DES

Không chọn DES hoặc TDEA làm phương án tạo bảo vệ mới cho ứng dụng hiện đại chỉ vì thiết bị cũ còn hỗ trợ. Một ví dụ phân biệt rõ thao tác là [thông báo NIST về việc rút SP 800-67 Rev. 2](https://csrc.nist.gov/news/2023/nist-to-withdraw-sp-800-67-rev-2): theo lộ trình được nêu, TDEA không được dùng để áp dụng bảo vệ mới sau ngày 31/12/2023, trong khi các thao tác xử lý dữ liệu đã được bảo vệ trước đó được phân biệt riêng.

Đây không phải lý do để mở giải mã TDEA tùy ý cho mọi API. Nhu cầu lịch sử phải có nguồn dữ liệu, quyền truy cập, thời hạn và biện pháp kiểm soát. Cũng không nên hủy ngay khóa cũ trước khi đã xử lý dữ liệu còn phải lưu và các bản backup thuộc phạm vi.

### 3.3. RC4 và phiên bản TLS cũ

[RFC 7465](https://www.rfc-editor.org/rfc/rfc7465.html) cấm đàm phán RC4 cipher suite trong TLS. [RFC 8996](https://www.rfc-editor.org/rfc/rfc8996.html) chính thức deprecate TLS 1.0 và TLS 1.1. Đây là các quyết định ở lớp giao thức, cần được thực thi tại client và server liên quan, không chỉ trong hàm mã hóa dữ liệu của ứng dụng.

Một endpoint HTTPS có chứng chỉ hợp lệ chưa chứng minh nó chỉ chấp nhận profile giao thức và cipher phù hợp. Cần kiểm tra cấu hình có hiệu lực và kết nối thực tế trên đúng host, port, listener và đường phân phối.

Các ví dụ trên không phải danh sách đầy đủ mọi cơ chế lỗi thời. Danh mục áp dụng cho hệ thống phải có owner, nguồn tham chiếu, version và quy trình cập nhật khi có thay đổi.

## 4. Tách tạo mới, đọc lịch sử và ngừng hoàn toàn

Một trạng thái “allowed” duy nhất thường không đủ. Cần xác định quyền theo loại thao tác:

| Trạng thái profile minh họa | Tạo bảo vệ mới | Đọc/giải mã/xác minh lịch sử | Điều kiện |
| --- | --- | --- | --- |
| Current | Cho phép đúng scope | Cho phép đúng scope | Đủ key, tham số và implementation |
| Legacy read only | Không | Có giới hạn | Nguồn dữ liệu, quyền và kế hoạch chuyển đổi rõ |
| Retirement scheduled | Không dùng mới theo mốc đã chốt | Chỉ tới điều kiện ngừng | Có owner và theo dõi lượng dữ liệu còn lại |
| Retired | Không | Không qua đường vận hành thông thường | Phục hồi đặc biệt, nếu có, theo quy trình riêng |
| Unknown/unapproved | Không | Không tự thử một mặc định | Ghi nhận lỗi và xử lý theo policy |

Tên trạng thái có thể khác ở từng tổ chức. Điều quan trọng là ứng dụng không coi “còn giải mã được” thành “được phép mã hóa mới”. Việc giữ một adapter đọc lịch sử không được tự mở một encoder legacy trong cùng API.

Một yêu cầu minh họa:

> Sau mốc T0, profile report-envelope-v1 không được tạo ciphertext mới. Profile này chỉ được đọc trong tác vụ migration được cấp quyền với tập dữ liệu đủ điều kiện. Mọi ghi mới và dữ liệu đã chuyển đổi phải dùng report-aead-v2. Lỗi ở v2 không được gây fallback sang v1.

Mốc T0 phải trở thành thời điểm cụ thể có múi giờ trong kế hoạch thật. Không dùng một giá trị `createdAt` do client tự khai để quyết định dữ liệu đủ điều kiện đọc legacy; điều kiện phải dựa trên metadata và nguồn dữ liệu đáng tin theo thiết kế.

## 5. Kiểm kê nơi cơ chế cũ có thể còn tồn tại

### 5.1. Phạm vi rộng hơn repository chính

| Khu vực | Ví dụ cần kiểm kê |
| --- | --- |
| Ứng dụng | Cipher, signature, MAC, hash, password encoder và định dạng token |
| Cấu hình runtime | Provider, transformation alias, policy động và biến môi trường |
| Kênh kết nối | Public TLS, outbound HTTP, database, broker, email và quản trị |
| Công việc nền | Batch, export, import, retry, replay và job migrate cũ |
| Key infrastructure | KMS/HSM policy, key type, key size, purpose và version |
| Dữ liệu | Profile envelope, verifier mật khẩu, chứng thư và chữ ký lưu trữ |
| Backup và DR | Snapshot, khóa phục hồi, image cũ và công cụ restore |
| Bên thứ ba | Đối tác chỉ hỗ trợ profile cũ hoặc thư viện bắc cầu |

Một host phụ hoặc outbound client có thể giữ cấu hình yếu hơn host chính. Một artifact triển khai cũ cũng có thể còn hoạt động dù nhánh source hiện tại đã được sửa.

Inventory nên liên kết cơ chế với purpose, service, owner, môi trường, release, key và tập dữ liệu. Không cần lưu raw key hoặc plaintext để có được liên kết này.

### 5.2. Tìm chuỗi là điểm bắt đầu, không phải kết luận

Tìm `MD5`, `SHA1`, `DESede` hoặc `RC4` trong source có thể phát hiện một số điểm đáng chú ý. Nhưng một chuỗi có thể thuộc test từ chối, adapter đọc lịch sử hoặc dữ liệu không dùng cho mục đích an ninh. Cần phân loại theo đường thực thi.

Ngược lại, không tìm thấy chuỗi không chứng minh sạch: tên thuật toán có thể được lấy từ cấu hình, chọn qua alias hoặc mặc định provider, nằm trong dependency hoặc được thực hiện bởi hạ tầng ngoài process.

Yêu cầu hoàn thành cần liên kết bằng chứng source/config với môi trường đã deploy và dữ liệu thực tế. Không thay đánh giá phạm vi bằng một báo cáo quét từ khóa không có ngữ cảnh.

### 5.3. Biết điều chưa biết

Nếu chưa xác định được profile của một tập ciphertext, ghi nhận đó là khoảng trống và tìm nguồn metadata, owner hoặc công cụ tạo dữ liệu. Không mặc định nó dùng cơ chế hiện đại chỉ vì trường tên là `encrypted_value`.

Cũng không tự thử hàng loạt thuật toán trên ciphertext production để đoán định dạng qua lỗi. Cần phương án khảo sát có phạm vi, quyền và giới hạn tài nguyên phù hợp, nhất là khi các adapter cũ có đường xử lý lỗi khác nhau.

## 6. Chặn dùng mới bằng allowlist có hiệu lực

### 6.1. Đầu vào chọn profile phải được kiểm soát

Một envelope có thể chứa `profileId` và `keyId` để hỗ trợ đọc dữ liệu. Những trường đó không phải quyền cho người gửi chọn bất kỳ transformation hoặc key nào.

Thiết kế nên ánh xạ ID tới một registry do server quản lý, kiểm tra purpose, thao tác và trạng thái hiện hành. Không truyền trực tiếp chuỗi từ request vào API như `Cipher.getInstance()` hoặc `Signature.getInstance()`.

Ví dụ policy minh họa:

```yaml
purpose: report_note_storage
newProtectionProfiles:
  - report-aead-v2
historicalReadProfiles:
  - profileId: report-envelope-v1
    accessPath: authorized_migration_worker
    sourceScope: approved_legacy_dataset
    retirementPlanRef: report-crypto-migration-plan-A
onUnknownProfile: reject
onCurrentProfileFailure: fail_without_downgrade
```

Đây là nội dung mô tả chính sách, không phải cấu hình thực thi của module. Các tham chiếu về dataset, quyền worker và retirement phải được giải quyết trong thiết kế thật.

### 6.2. Không fallback vì lỗi cấu hình hoặc lỗi xác thực

Các đường cần ngăn:

```text
Không có provider hiện tại -> thử một cipher cũ.
Tag AEAD không khớp       -> thử đọc như định dạng legacy.
Đối tác không hỗ trợ TLS  -> gửi qua HTTP.
Password profile lỗi     -> thử hash nhanh không salt.
Không lấy được key mới   -> dùng key hard-code dự phòng.
```

Mỗi đường trên thay đổi giả định bảo mật để đổi lấy một kết quả có vẻ thành công. Yêu cầu nên ghi rõ lỗi nào dẫn tới dừng thao tác, lỗi nào được retry trong cùng profile và điều kiện nào cần can thiệp có quyền.

Nếu hỗ trợ nhiều profile tương đương cho một purpose, tập lựa chọn và cách chọn phải được phê duyệt trước. “Không fallback yếu hơn” không có nghĩa hệ thống không được có khả năng dự phòng hợp lệ; nó cấm việc tự mở rộng xuống cơ chế ngoài policy.

### 6.3. Tách quyền đọc cũ khỏi quyền ghi cũ

Một service account migration có thể cần giải mã lịch sử nhưng không cần quyền tạo dữ liệu legacy mới. Key manager, API của adapter và policy ứng dụng nên phản ánh sự tách biệt đó khi nền tảng hỗ trợ.

Không dựa vào comment “chỉ dùng để migrate” nếu code vẫn cung cấp một phương thức encrypt cũ có thể được gọi bởi luồng nghiệp vụ bình thường. Phạm vi truy cập, call graph và test phải thể hiện hạn chế.

## 7. Ví dụ Java: không dựa vào mặc định hoặc khả năng sẵn có

### 7.1. Implementation có mặt không có nghĩa được phép dùng

Một JDK hoặc provider có thể hỗ trợ cơ chế cũ để tương thích. `getInstance()` thành công chỉ cho biết có implementation, không thay quyết định phê duyệt của sản phẩm.

Ngoài ra, một lời gọi chỉ ghi tên thuật toán có thể dựa vào mode/padding mặc định của provider. Hợp đồng này được mô tả trong [Java SE 21 Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html).

Không dùng:

```java
// Không biểu đạt đủ profile mã hóa bản ghi đã phê duyệt.
Cipher cipher = Cipher.getInstance("AES");
```

Một trích đoạn thể hiện cách chọn rõ profile hiện tại:

```java
import java.security.GeneralSecurityException;
import java.security.Provider;
import java.util.Objects;
import javax.crypto.Cipher;

public final class CurrentEncryptionFactory {
    private static final String CURRENT_PROFILE = "report-aead-v2";

    private CurrentEncryptionFactory() {
    }

    public static Cipher create(String profileId, Provider approvedProvider)
            throws GeneralSecurityException {
        Objects.requireNonNull(approvedProvider, "approvedProvider");
        if (!CURRENT_PROFILE.equals(profileId)) {
            throw new GeneralSecurityException(
                    "Profile is not allowed for new encryption");
        }
        return Cipher.getInstance(
                "AES/GCM/NoPadding", approvedProvider);
    }
}
```

Ví dụ chỉ minh họa lựa chọn transformation cho một purpose. Nó chưa khởi tạo key, nonce hoặc AAD và chưa hoàn thành một phép mã hóa. Provider, key size, quyền dùng key, nonce duy nhất, tag và usage budget phải được bảo đảm bởi profile cùng hạ tầng liên quan.

Lỗi từ `getInstance()` được truyền theo đường lỗi, không được bắt để đổi sang DES, CBC hoặc plaintext ngoài policy. Adapter đọc lịch sử không nằm trong factory tạo mã hóa mới này.

### 7.2. Security property có phạm vi riêng

Java có các cơ chế giới hạn thuật toán cho TLS và xử lý chứng thư, nhưng không được coi một security property là allowlist chung cho mọi lời gọi mật mã trong ứng dụng.

Ví dụ, `jdk.tls.disabledAlgorithms` áp dụng cho thương lượng TLS/DTLS của JSSE theo phạm vi được tài liệu mô tả. Nó không tự chứng minh mọi hàm lưu trữ dữ liệu, password encoder hoặc chữ ký tự gọi ở lớp nghiệp vụ đã bị chặn theo cùng danh sách. Xem [Oracle JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html).

Không sửa cấu hình runtime để bật lại một giao thức hoặc cipher bị chặn chỉ nhằm làm một tích hợp cũ hết báo lỗi, trừ khi có quyết định ngoại lệ và phạm vi được phê duyệt. Đồng thời, không dựa vào một giá trị mặc định được nhớ từ phiên bản JDK khác; cần đọc cấu hình có hiệu lực của môi trường thật.

## 8. Chuyển đổi dữ liệu mã hóa: bảo toàn dữ liệu và tính toàn vẹn

### 8.1. Chuẩn bị trước khi chuyển đổi

Đối với tập bản ghi dùng profile cũ, kế hoạch cần xác định nguồn đủ điều kiện, quyền đọc, khóa cũ, profile mục tiêu, schema envelope và cách xử lý lỗi. Phải có thống kê dữ liệu, bản backup phù hợp và khả năng khôi phục trước khi thay đổi hàng loạt.

Một luồng khái niệm:

```text
Chọn record legacy thuộc dataset được phê duyệt
    -> kiểm tra version và metadata theo profile đọc cũ
    -> giải mã bằng adapter có quyền
    -> kiểm chứng dữ liệu theo khả năng của nguồn cũ
    -> mã hóa bằng profile mới, key và nonce phù hợp
    -> ghi envelope mới nguyên tử nếu record version chưa đổi
    -> ghi nhận tiến độ, không ghi plaintext
```

Không cập nhật riêng `profileId` thành v2 mà giữ ciphertext v1. Metadata và dữ liệu phải tương ứng cùng một lần chuyển đổi.

### 8.2. Dữ liệu cũ thiếu xác thực không được “nâng niềm tin” ngược thời gian

Nếu cơ chế cũ không xác thực ciphertext, giải mã thành công không tự chứng minh dữ liệu chưa bị sửa. Re-encrypt bằng AEAD bảo vệ bản được nhập từ thời điểm chuyển đổi, không chứng minh lịch sử trước đó.

Cần đánh giá nguồn tin cậy bổ sung, backup, chữ ký hoặc kiểm tra nghiệp vụ phù hợp. Dữ liệu nghi ngờ có thể cần được cách ly để xử lý, thay vì tự đưa vào profile mới rồi gắn nhãn đã được xác thực đầy đủ từ trước.

### 8.3. Chống ghi đè và hỗ trợ tiếp tục sau lỗi

Tác vụ migration nên dùng điều kiện version hoặc cơ chế tương ứng để không ghi đè chỉnh sửa mới của người dùng. Nếu record đã đổi, phải đọc lại hoặc xử lý theo policy; không cưỡng ép bản cũ lên bản mới.

Tiến độ phải cho biết record nào đã chuyển và record nào cần thử lại, nhưng không chứa plaintext hoặc raw key. Một lần chạy lại không được làm hỏng envelope đã chuyển hoặc tạo lại bảo vệ legacy.

Giới hạn tốc độ và concurrency của migration cần tính cả KMS, database và ngân sách dùng key. Hàng triệu phép mã hóa mới vẫn phải tuân theo yêu cầu nonce và usage budget; không miễn trừ vì đó là job nội bộ.

### 8.4. Rewrap key khác re-encrypt dữ liệu

Trong envelope encryption, đổi KEK rồi bọc lại DEK có thể thay lớp bảo vệ key mà không thay thuật toán/mode đang mã hóa payload. Nếu mục tiêu là loại profile payload lỗi thời, chỉ rewrap key có thể chưa đáp ứng.

Ngược lại, re-encrypt payload không tự sửa mọi vấn đề về quyền truy cập KMS hoặc khóa bị lộ. Hồ sơ phải chỉ ra lớp nào cần thay và bằng chứng nào chứng minh lớp đó đã được chuyển đổi.

## 9. Password verifier và chữ ký cần chiến lược riêng

### 9.1. Không “đổi thuật toán” của hash mật khẩu chỉ bằng metadata

Với verifier legacy, không thể lấy một hash cũ, đổi nhãn algorithm hoặc thêm salt rồi coi như đã có verifier mới trực tiếp từ mật khẩu. Khi người dùng cung cấp mật khẩu và được xác minh đúng theo luồng legacy được phép, hệ thống có thể tạo verifier mới bằng password hashing profile hiện tại với salt mới.

Tài khoản không quay lại cần chính sách hết hạn hoặc reset phù hợp nếu phải ngừng đường xác minh cũ. Không giữ một verifier yếu vô hạn chỉ để chỉ số chuyển đổi không có tài khoản bị gián đoạn.

Các chiến lược nâng cấp verifier được trình bày trong [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#upgrading-legacy-hashes). Cách chuyển đổi phải giữ đúng algorithm, salt, cost và credential version, đồng thời chống race với đổi/reset mật khẩu.

### 9.2. Chữ ký cũ không trở thành chữ ký mới bằng thay OID hoặc tên hash

Chữ ký ràng buộc với byte thông điệp, thuật toán và khóa đã dùng. Không thể thay nhãn SHA-1 thành SHA-256 rồi kỳ vọng chữ ký lịch sử vẫn có ý nghĩa như một chữ ký được tạo mới đúng profile.

Nhu cầu xác minh tài liệu lịch sử cần đánh giá thời điểm, nguồn tin cậy, chứng thư và bằng chứng lưu trữ liên quan theo policy. Việc chữ ký toán học khớp chưa tự giải quyết mọi rủi ro do thuật toán hoặc khóa đã không còn đáng tin.

Nếu tạo lại một chữ ký hiện tại hoặc một bản chứng thực mới cho dữ liệu cũ, phải ghi rõ đó là sự kiện mới với chủ thể và provenance tương ứng. Không làm mất bản gốc hoặc trình bày nó như bằng chứng rằng chữ ký cũ luôn an toàn.

## 10. Loại bỏ cơ chế cũ khỏi kết nối thực tế

### 10.1. Kiểm tra cả inbound và outbound

Một nền tảng có thể chặn TLS cũ ở public gateway nhưng vẫn dùng kết nối yếu tới database, broker hoặc đối tác. Cần inventory các hop và nơi kết thúc TLS để không hiểu nhầm một phép đo tại biên là bảo đảm end-to-end.

Profile phải xác định protocol version, cipher, nhóm trao đổi khóa, thuật toán chữ ký hoặc các thành phần liên quan theo giao thức đang dùng. Không chỉ kiểm tra tên protocol mà bỏ qua các ràng buộc khác của cấu hình.

Khi một đối tác không tương thích, xử lý bằng nâng cấp, thay đổi kiến trúc tích hợp hoặc ngoại lệ có phạm vi. Không mở lại profile yếu cho mọi host và client của nền tảng để phục vụ một trường hợp.

### 10.2. Kiểm chứng đàm phán, không chỉ file cấu hình

Một dòng cấu hình có thể bị override, không áp dụng vào listener cần kiểm tra hoặc chưa được reload. Bằng chứng cần bao gồm kết nối thực tế với tập lựa chọn được phép và thử từ chối cơ chế bị cấm.

Một ca handshake thất bại chưa đủ chứng minh profile yếu bị chặn: DNS, trust, firewall hoặc server ngừng cũng có thể gây thất bại. Cần ca dương phù hợp, thông tin endpoint và lý do quan sát để đánh giá đúng.

Không kiểm tra trên hệ thống ngoài phạm vi được phép. Các phép thử cần được thiết kế để không mở đường dữ liệu hoặc làm thay đổi cấu hình chỉ nhằm phục vụ công cụ đo.

## 11. Chuyển đổi theo mốc và điều kiện hoàn thành

Một kế hoạch minh họa có thể gồm:

| Mốc | Kết quả phải đạt |
| --- | --- |
| T0: chốt policy | Owner, profile thay thế và scope đã được phê duyệt |
| T1: dừng tạo mới | Mọi đường ghi/ký mới không dùng profile cũ; có telemetry phát hiện vi phạm |
| T2: chuyển dữ liệu | Dataset được migrate, lỗi được xử lý và dữ liệu mới được kiểm chứng |
| T3: kiểm chứng phục hồi | Restore và các công cụ phục hồi không tạo lại phụ thuộc yếu ngoài policy |
| T4: ngừng đọc thường lệ | Adapter, quyền key và đường tích hợp cũ được ngừng theo điều kiện đã chốt |

Đây là thứ tự minh họa, không phải thời hạn chuẩn chung. Khi có rủi ro khẩn cấp, một số luồng có thể phải dừng ngay; khi dữ liệu cần giữ lâu, đường đọc lịch sử có thể cần một môi trường cách ly được phê duyệt trong thời hạn nhất định.

### 11.1. Rollback không được âm thầm tạo lại dữ liệu yếu

Một bản code cũ được rollback có thể không hiểu envelope mới hoặc tiếp tục ghi v1. Kế hoạch cần xác định version ứng dụng tối thiểu, capability check và điều kiện chỉ đọc hoặc chặn ghi nếu runtime không đáp ứng policy.

Không gọi migration hoàn tất nếu chỉ runtime mới tuân thủ nhưng công cụ DR vẫn khôi phục image cũ với quyền ghi profile đã ngừng. Khôi phục là một đường vận hành thật cần nằm trong scope.

### 11.2. Khóa cũ chỉ được hủy sau khi đủ điều kiện

Trước khi hủy hoặc mất khả năng dùng key, phải biết những dữ liệu và bản backup nào còn phụ thuộc. Cần đối chiếu chính sách lưu giữ, khả năng phục hồi và quyền đọc lịch sử đã chốt.

Không giữ quyền dùng key rộng hơn cần thiết trong suốt thời gian chờ, nhưng cũng không coi xóa key ngay là cách đơn giản để loại thuật toán. Việc làm dữ liệu không thể đọc là một thay đổi khác, cần được quản lý đúng mục tiêu.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

| Mã | Yêu cầu minh họa | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| OLD-CRYPTO-01 | Mọi use case mật mã phải có purpose, profile, owner và trạng thái theo policy | Inventory liên kết source, config, hạ tầng và dữ liệu |
| OLD-CRYPTO-02 | Sau mốc ngừng tạo mới, profile cũ không được tạo ciphertext/MAC/chữ ký/verifier mới | Ca ghi mới qua API, batch, retry và công cụ nội bộ |
| OLD-CRYPTO-03 | Profile đầu vào không biết hoặc không được phép phải bị từ chối | Envelope/request chọn cơ chế ngoài danh mục |
| OLD-CRYPTO-04 | Lỗi profile hiện tại không được gây hạ cấp ngoài policy | Thiếu provider, lỗi key, lỗi tag và lỗi tương thích |
| OLD-CRYPTO-05 | Đọc lịch sử chỉ được thực hiện đúng scope, quyền và thời hạn | Người dùng thường, worker migration và dataset ngoài scope |
| OLD-CRYPTO-06 | Migration phải giữ metadata/body nhất quán và không ghi đè version mới | Lỗi giữa chừng, chạy lại và cạnh tranh cập nhật |
| OLD-CRYPTO-07 | Các kết nối trong scope phải không đàm phán profile bị cấm | Ca dương và ca từ chối tại endpoint thực tế |
| OLD-CRYPTO-08 | Backup/restore không tái mở quyền ghi bằng cơ chế cũ | Diễn tập restore và kiểm tra runtime phục hồi |
| OLD-CRYPTO-09 | Retirement key/adapter phải có bằng chứng dữ liệu và phục hồi phù hợp | Đối chiếu dataset, backup và phê duyệt ngừng |
| OLD-CRYPTO-10 | Ngoại lệ phải có owner, scope, hạn và biện pháp bù | Kiểm tra cấu hình hiệu lực và trạng thái hết hạn |

Yêu cầu tổng hợp có thể là:

> Dịch vụ chỉ tạo bảo vệ mới bằng profile hiện hành cho đúng purpose. Profile lỗi thời không được lựa chọn qua request, cấu hình tùy ý hoặc fallback. Khả năng đọc dữ liệu lịch sử phải được tách quyền, giới hạn nguồn và gắn kế hoạch retirement; mọi chuyển đổi phải bảo toàn dữ liệu và được kiểm chứng qua đường phục hồi.

## 13. Kế hoạch nghiệm thu và bằng chứng cần quan sát

Các ca sau là kế hoạch kiểm chứng cho một hệ thống giả định, không phải báo cáo đã chạy trên dự án cụ thể.

| Ca | Điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| Ghi mới đúng | Profile hiện hành, key và tham số đúng | Tạo dữ liệu đúng profile và envelope nhất quán |
| Yêu cầu ghi bằng profile cũ | Client/config chọn profile chỉ đọc lịch sử | Từ chối, không tạo dữ liệu cũ mới |
| Profile không biết | Metadata chọn một tên tùy ý | Không dùng mặc định hoặc thử tuần tự nhiều thuật toán |
| Provider thiếu | Không có implementation được phê duyệt | Lỗi có kiểm soát, không fallback |
| Xác thực ciphertext lỗi | Tag hoặc context bị sửa | Không thử như legacy và không phát plaintext |
| Đọc cũ đúng scope | Worker được cấp quyền, record đủ điều kiện | Đọc theo policy và chuyển sang profile mới |
| Đọc cũ sai scope | User thường hoặc dataset không đủ điều kiện | Không biến adapter thành dịch vụ giải mã tùy ý |
| Migration bị ngắt | Lỗi trước hoặc trong cập nhật record | Không có envelope nửa cũ nửa mới |
| Chạy lại migration | Record đã được chuyển hoặc từng lỗi | Không làm hỏng dữ liệu, tiến độ đáng tin |
| Ghi đồng thời | User sửa record trong lúc migrate | Không ghi đè version mới bằng bản cũ |
| Chỉ rewrap key | KEK đổi nhưng payload vẫn profile cũ | Phát hiện chưa đáp ứng mục tiêu thay profile payload |
| TLS yếu | Client chỉ đề nghị cơ chế bị cấm | Không đàm phán; có bằng chứng lý do và ca dương đối chứng |
| Host/đường phụ | Endpoint beta, nội bộ hoặc outbound trong scope | Policy nhất quán theo phạm vi đã phê duyệt |
| Restore | Khôi phục backup và image theo quy trình | Đọc được dữ liệu cần giữ; không ghi profile đã ngừng |
| Ngoại lệ hết hạn | Đến mốc hoặc thiếu phê duyệt hợp lệ | Không tiếp tục cho phép vô hạn |
| Hủy key/adapter | Điều kiện retirement đã chốt | Không làm mất khả năng phục hồi còn bắt buộc |

### 13.1. Không chỉ kiểm tra mã lỗi

Một request trả lỗi sau khi đã ghi dữ liệu bằng profile cũ vẫn vi phạm. Cần kiểm tra storage, envelope, queue và tác dụng phụ liên quan để chứng minh thao tác bị cấm không xảy ra.

Tương tự, một job migrate báo thành công cần có số lượng theo profile, đối chiếu dữ liệu và tình trạng lỗi; không chỉ một log “done”. Kết quả quét không được coi là bằng chứng dữ liệu đã chuyển nếu nó chỉ kiểm tra nhãn profile.

### 13.2. Round-trip không chứng minh an toàn

Một thuật toán yếu hoặc mode sai vẫn có thể vượt ca `decrypt(encrypt(P)) == P`. Cần kiểm tra từ chối cơ chế ngoài policy, tính toàn vẹn, binding ngữ cảnh và các điều kiện key/nonce của profile mục tiêu.

Đối với dữ liệu legacy, ca đọc được không tự chứng minh nội dung có provenance đáng tin. Bằng chứng migration phải ghi rõ giới hạn niềm tin của nguồn cũ và các kiểm tra bổ sung đã được thực hiện.

### 13.3. Nghiệm thu theo môi trường và release

Một bản test tại máy phát triển không chứng minh provider, policy file, image và listener production giống nhau. Hồ sơ cần gắn kết quả với release, môi trường, endpoint và phạm vi dữ liệu.

Nếu có yêu cầu xác nhận module, phải kiểm tra đúng module/version và chế độ sử dụng; một thuật toán hiện đại không tự làm runtime đạt yêu cầu đó. Nếu không có yêu cầu này, cũng không nên tự gắn nhãn chứng nhận từ một kết quả kiểm thử chức năng.

## 14. Quan sát sau chuyển đổi mà không lộ dữ liệu

Telemetry có thể ghi profile ID, purpose, loại thao tác, quyết định cho phép/từ chối và release. Không ghi plaintext, raw key, password hoặc verifier chỉ để biết một đường legacy còn được gọi.

Các chỉ số có ích:

- Số thao tác tạo mới bằng profile đã ngừng, kỳ vọng bằng không trong scope.
- Số bản ghi theo profile và số bản ghi chưa xác định định dạng.
- Số lần đọc legacy theo worker hoặc đường được phép.
- Số trường hợp fallback bị chặn và lý do cấu hình.
- Số kết nối bị từ chối do profile ngoài policy.
- Số ngoại lệ chưa hết hạn, quá hạn hoặc chưa có owner.

Mẫu số và độ bao phủ phải rõ. “Không quan sát thấy v1 trong một ngày” không chứng minh không còn job tháng, backup hoặc host phụ sử dụng nó. Cần liên kết telemetry với inventory và cửa sổ quan sát.

Không đưa key ID, tenant tùy ý hoặc ciphertext vào nhãn metric không có giới hạn vì có thể làm tăng cardinality và lộ metadata không cần thiết. Bằng chứng chi tiết nên được giữ ở nơi có quyền truy cập thích hợp.

## 15. Ngoại lệ phải có đường thoát

Một tích hợp chưa thể nâng cấp ngay có thể cần quyết định ngoại lệ có thẩm quyền. Hồ sơ tối thiểu nên có:

| Thành phần | Nội dung cần chốt |
| --- | --- |
| Lý do | Phụ thuộc nào đang cản trở thay đổi? |
| Phạm vi | Service, endpoint, đối tác, dataset và thao tác nào? |
| Rủi ro | Tài sản nào chịu ảnh hưởng và giả định bảo vệ nào giảm? |
| Biện pháp bù | Cách ly mạng, giới hạn dữ liệu/quyền hoặc môi trường chuyển đổi riêng |
| Owner | Ai chịu trách nhiệm và ai chấp nhận rủi ro? |
| Thời hạn | Mốc xem xét, hết hạn và hành vi khi hết hạn |
| Kế hoạch thoát | Bước nâng cấp, thay thế hoặc ngừng tích hợp |

Ngoại lệ không được biến thành bật lại cơ chế cũ toàn cục. Một gateway chuyển đổi có thể giới hạn phạm vi tương thích nhưng không làm hop legacy tự trở nên mạnh; phải đánh giá và bảo vệ ranh giới còn yếu đó một cách trung thực.

Khi có dấu hiệu khai thác hoặc mất khóa, ưu tiên ứng phó theo tài sản và phạm vi ảnh hưởng. Đổi thuật toán không khôi phục bí mật của dữ liệu có thể đã bị đọc, và đổi key không sửa mode hoặc nonce nếu nguyên nhân vẫn còn.

## 16. Một hồ sơ yêu cầu gọn cho retirement mật mã

```text
Tài sản: dữ liệu được bảo vệ, credential và kết nối trong scope.
Đe dọa: tiếp tục dùng profile không còn phù hợp; downgrade;
        giữ phụ thuộc legacy không được quản lý hoặc mất dữ liệu khi migrate.

Chính sách:
  - Mọi purpose dùng profile hiện hành đã phê duyệt.
  - Trạng thái tạo mới và đọc lịch sử được tách rõ.
  - Metadata không cho client chọn thuật toán/key tùy ý.
  - Không hạ cấp ngoài policy khi lỗi hoặc không tương thích.

Chuyển đổi:
  - Có inventory source/config/runtime/dữ liệu/backup.
  - Migration có quyền, nguồn dữ liệu, version và giới hạn tài nguyên.
  - Không chỉ đổi nhãn hoặc rewrap key khi payload cần re-encrypt.
  - Restore và rollback không tái tạo ghi yếu ngoài policy.

Hoàn thành:
  - Không còn tạo bảo vệ mới bằng profile đã ngừng trong scope.
  - Dữ liệu và khả năng phục hồi được kiểm chứng theo policy.
  - Adapter/key/ngoại lệ cũ được xử lý theo điều kiện retirement.
  - Có bằng chứng runtime và owner duy trì danh mục.
```

Không dùng thuật toán lỗi thời là một quá trình kiểm soát cách tạo bảo vệ mới, xử lý lịch sử và loại bỏ phụ thuộc cũ có bằng chứng. Khi yêu cầu gắn với purpose, trạng thái sử dụng và điều kiện phục hồi, hệ thống có thể nâng mức bảo vệ mà không chỉ che một từ khóa hoặc vô tình làm mất dữ liệu cần giữ.
