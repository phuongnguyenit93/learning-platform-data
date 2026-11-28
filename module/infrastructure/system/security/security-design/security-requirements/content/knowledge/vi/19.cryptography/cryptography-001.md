# Yêu cầu dùng cryptography

## 1. Yêu cầu mật mã bắt đầu từ tài sản và rủi ro

Cryptography cung cấp những cơ chế như mã hóa, xác thực thông điệp, chữ ký số, hàm băm và sinh giá trị ngẫu nhiên. Trong thiết kế yêu cầu bảo mật, nhiệm vụ đầu tiên không phải chọn một tên thuật toán, mà là xác định dữ liệu cần bảo vệ, đối thủ có khả năng gì và thuộc tính nào phải được giữ.

Một yêu cầu như “hệ thống phải dùng AES-256” chưa trả lời dữ liệu nào được mã hóa, khóa nằm ở đâu, ai được giải mã, dữ liệu bị sửa thì xử lý thế nào hoặc khi mất khóa có phục hồi được không. Có thể đáp ứng câu chữ đó bằng cách mã hóa một file bằng khóa hard-code ngay cạnh file, nhưng không đạt mục tiêu giảm rủi ro mong muốn.

Ngược lại, một yêu cầu có ý nghĩa có thể bắt đầu như sau:

> Bản xuất kết quả học tập phải giữ bí mật khi bản sao lưu cơ sở dữ liệu bị đọc trái phép, trong giả định bên đọc không có quyền sử dụng dịch vụ khóa của ứng dụng.

Từ mục tiêu này mới xác định lớp mã hóa, phân tách quyền khóa, định dạng lưu trữ và bằng chứng nghiệm thu. Nếu đối thủ đã chiếm được process được cấp quyền giải mã, cùng cơ chế đó không tự bảo vệ được plaintext mà process hợp lệ có thể đọc.

OWASP khuyến nghị bắt đầu từ threat model và chọn lớp mã hóa phù hợp; mã hóa ở phần cứng, filesystem, database hay ứng dụng bảo vệ những ranh giới khác nhau. [OWASP: Cryptographic Storage](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html#architectural-design).

Bài học tập trung vào cách đặc tả và kiểm chứng việc sử dụng mật mã trong hệ thống. Các tên thuật toán và giới hạn minh họa cần được đưa vào profile đã duyệt của dự án trước khi dùng thật, không phải cấu hình production sẵn có của module học tập.

## 2. Lập ma trận tài sản, đối thủ và thuộc tính cần giữ

Với một nền tảng học tập, có thể phân tích các trường hợp sau:

| Tài sản hoặc luồng | Khả năng của đối thủ trong tình huống | Thuộc tính cần giữ |
| --- | --- | --- |
| Thông tin đăng nhập qua mạng | Quan sát hoặc can thiệp đường truyền | Bí mật, toàn vẹn, xác thực đầu bên kia theo giao thức |
| Bản xuất kết quả học tập trong backup | Đọc được bản sao lưu nhưng không được dùng khóa | Bí mật của nội dung |
| Báo cáo đã mã hóa trong storage | Sửa byte hoặc tráo blob giữa các bản ghi | Phát hiện sửa đổi và sai ngữ cảnh |
| Mật khẩu tài khoản | Đọc được kho verifier | Tăng chi phí đoán offline; không lưu mật khẩu có thể khôi phục |
| Chứng chỉ khóa học phát cho bên ngoài | Có thể sửa nội dung file | Xác minh chữ ký và mối liên hệ tới bên phát hành được tin |
| Reset token | Có thể đoán hoặc thử nhiều token | Tính khó đoán, giới hạn thời gian và chống dùng lại theo nghiệp vụ |
| Kết nối giữa service và KMS | Có thể gọi từ workload không được cấp quyền | Xác thực workload và giới hạn thao tác khóa |

Mỗi hàng cần ghi cả giả định. Ví dụ “storage bị đọc” khác “ứng dụng bị chiếm quyền”, và “file có chữ ký hợp lệ” khác “người giữ private key chưa từng bị xâm nhập”. Không dùng một cơ chế để công bố những bảo đảm nằm ngoài ranh giới của nó.

Trước khi bảo vệ bằng mật mã, nên hỏi dữ liệu có cần lưu hay không, có thể giảm độ chi tiết hoặc thời hạn tồn tại không. Không lưu một bí mật không cần thiết thường giảm rủi ro và chi phí quản lý khóa tốt hơn việc giữ nó rồi bổ sung một lớp mã hóa.

## 3. Chọn cơ chế theo mục tiêu, không dùng một công cụ cho mọi việc

| Cơ chế | Mục tiêu phù hợp | Điều nó không tự cung cấp |
| --- | --- | --- |
| TLS | Bảo vệ kênh truyền giữa các đầu cuối được xác thực theo cấu hình | Không tự mã hóa dữ liệu trong database hoặc phân quyền nghiệp vụ |
| Mã hóa có xác thực, như một AEAD profile được duyệt | Bí mật và phát hiện sửa đổi của dữ liệu, cùng associated data nếu có | Không tự ngăn replay hay cấp quyền giải mã cho actor |
| Hàm băm mật mã | Digest và các cấu trúc cần thuộc tính hash phù hợp | Một digest không được bảo vệ không chứng minh ai tạo thông điệp |
| Password hashing/KDF chuyên dụng | Lưu verifier mật khẩu với salt và chi phí đoán phù hợp | Không thay rate limit, MFA hoặc chất lượng mật khẩu |
| MAC/HMAC | Toàn vẹn và xác thực thông điệp giữa các bên giữ khóa chung | Không giữ bí mật nội dung và không phân biệt được bên nào trong nhóm giữ khóa đã tạo MAC |
| Chữ ký số | Xác minh thông điệp bằng public key với mô hình tin cậy đã chốt | Không tự che nội dung hay chứng minh quyền nghiệp vụ hiện tại |
| Bộ sinh ngẫu nhiên mật mã | Khóa, token hoặc nonce theo yêu cầu của giao thức | Giá trị ngẫu nhiên không tự có TTL, scope hoặc quyền sử dụng |
| Base64, hex, encoding dữ liệu | Chuyển cách biểu diễn byte | Không phải mã hóa bảo mật và không giữ bí mật |

### 3.1. Hash thông thường không thay MAC

Nếu kẻ sửa dữ liệu cũng sửa được digest lưu cạnh dữ liệu, việc so sánh hash mới với hash đó không tạo bằng chứng xác thực nguồn. MAC dùng khóa bí mật chung cho một mục tiêu khác. Không tự chế MAC bằng cách ghép khóa vào dữ liệu rồi gọi hash; dùng cơ chế chuẩn với profile được duyệt. [RFC 2104: HMAC](https://www.rfc-editor.org/rfc/rfc2104.html).

Tương tự, một email hoặc mã định danh có miền giá trị nhỏ có thể bị đoán bằng cách tính hash hàng loạt. Hash một giá trị không mặc định làm nó trở thành bí mật khó khôi phục.

### 3.2. Mật khẩu cần cơ chế chuyên dụng

Đối với đăng nhập bằng mật khẩu, mục tiêu thông thường là xác minh mà không cần khôi phục mật khẩu gốc. OWASP khuyến nghị password hashing thích ứng như Argon2id, với phương án phù hợp khi có ràng buộc triển khai khác. Không dùng hash nhanh đơn thuần như một cơ chế lưu mật khẩu. [OWASP: Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Yêu cầu phải chốt cách chọn tham số theo tài nguyên, chính sách hiện hành, tải đăng nhập và kế hoạch nâng cấp verifier. Không ghi “có salt” rồi bỏ qua chi phí tính toán hoặc hành vi rehash khi profile thay đổi.

### 3.3. Chữ ký không đồng nghĩa nội dung được giấu

Một tài liệu hoặc token chỉ được ký vẫn có thể đọc được nội dung nếu không có lớp mã hóa riêng. Chữ ký hợp lệ cũng cần được kiểm tra với đúng public key, bên phát hành, ngữ cảnh và hiệu lực mà ứng dụng tin cậy.

Không mô tả chữ ký như bằng chứng tuyệt đối rằng một cá nhân đã hiểu hoặc chấp thuận giao dịch. Quản lý private key, nhận diện chủ thể, flow xác nhận và bằng chứng vận hành đều ảnh hưởng cách hệ thống diễn giải kết quả xác minh.

## 4. Xác định ranh giới bảo vệ: khi truyền, khi lưu và khi sử dụng

### 4.1. Khi truyền

Yêu cầu TLS cần mô tả từng chặng: browser tới edge, edge tới service, service tới database, object storage hoặc KMS. Việc edge dùng HTTPS không tự chứng minh chặng phía sau có bảo vệ phù hợp.

Profile TLS cần quy định giao thức/cipher suite được phép, kiểm tra certificate và hostname, quản lý trust store, gia hạn và hành vi khi xác minh thất bại. Không tắt certificate verification để khắc phục một lỗi tích hợp. Hướng dẫn OWASP hiện khuyến nghị TLS 1.3 và chỉ duy trì TLS 1.2 khi cần tương thích với cấu hình phù hợp. [OWASP: Transport Layer Security](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

Với thao tác có tác dụng phụ, các đặc tính như replay của early data cần được xét theo giao thức và hành vi endpoint. Đừng suy rằng “đã qua TLS” có nghĩa mọi request đều chỉ được xử lý một lần.

### 4.2. Khi lưu

Mã hóa ổ đĩa có thể phù hợp với rủi ro mất thiết bị. Database encryption có thể bảo vệ file dữ liệu hoặc backup theo mô hình triển khai. Application-level encryption có thể giữ ciphertext trong database và tách quyền dùng khóa khỏi quyền đọc database.

Lựa chọn lớp mã hóa phải khớp đối thủ trong ma trận tài sản. Nếu database được giải mã minh bạch cho một tài khoản query, lớp đó không tự ngăn tài khoản query đọc nội dung. Nếu ứng dụng được quyền giải mã mọi tenant, một process ứng dụng bị chiếm vẫn là ranh giới rủi ro lớn.

### 4.3. Khi sử dụng

Để xử lý một báo cáo, process hợp lệ thường cần plaintext trong bộ nhớ. Yêu cầu cần giới hạn nơi plaintext xuất hiện, thời gian lưu tạm và các bản sao qua log, trace, crash dump, cache hoặc file tạm.

Không công bố bảo đảm xóa sạch mọi bản sao trong bộ nhớ chỉ vì đã gán một biến thành null. Đặc điểm runtime, thư viện và hạ tầng phải được xét nếu mô hình đe dọa yêu cầu bảo vệ dữ liệu đang sử dụng ở mức sâu hơn.

## 5. Một yêu cầu mật mã đầy đủ cần những thành phần nào?

Một mẫu đặc tả có thể gồm:

```text
Mục tiêu: thuộc tính bảo mật và rủi ro cần giảm
Tài sản/phạm vi: dữ liệu, luồng và môi trường áp dụng
Giả định: đối thủ có và không có quyền gì
Crypto profile: giao thức/thuật toán, mode, tham số và thư viện được duyệt
Khóa: nguồn sinh, owner, quyền dùng, vòng đời, backup và xử lý compromise
Định dạng/ngữ cảnh: version, metadata, AAD hoặc nội dung được xác minh
Lỗi: hành vi khi xác thực thất bại, khóa không sẵn có hoặc format lạ
Vận hành: giới hạn sử dụng, rotation, migration và khả năng phục hồi
Bằng chứng: cấu hình, kiểm thử, quyền thực tế và diễn tập
```

Ví dụ yêu cầu cho báo cáo học tập:

> Bản báo cáo thuộc nhóm dữ liệu đã phân loại phải được bảo vệ bằng authenticated encryption theo profile được duyệt trước khi lưu vào kho báo cáo. Quyền đọc database đơn thuần không được cấp quyền dùng khóa. Khi dữ liệu hoặc ngữ cảnh xác thực không hợp lệ, hệ thống không trả plaintext và không ghi bản thay thế chưa mã hóa.

Yêu cầu này cần được bổ sung profile cụ thể, phạm vi kho dữ liệu, quyền KMS và tiêu chí lỗi. Nó tốt hơn một khẩu hiệu về thuật toán vì liên kết được mục tiêu với ranh giới thực thi và bằng chứng cần thu thập.

Các điều khoản vận hành như thời hạn xử lý sự cố, RTO/RPO hoặc cryptoperiod cần được dự án chốt theo rủi ro và khả năng hệ thống. Không dùng một con số chung cho mọi khóa chỉ để hoàn thành biểu mẫu.

## 6. Với AEAD, phải đặc tả cả nonce, associated data và lỗi

AEAD kết hợp mã hóa với xác thực dữ liệu và có thể xác thực thêm associated data không bị mã hóa. Khi xác thực thất bại, phía sử dụng không được nhận plaintext như một kết quả hợp lệ. [RFC 5116: Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116.html).

Một profile mẫu có thể dùng AES-GCM với khóa 256 bit, nonce 96 bit và tag 128 bit. Đây là lựa chọn minh họa cần được xác nhận trong crypto standard của dự án, không phải kết luận rằng mọi hệ thống đều buộc dùng đúng bộ tham số đó. NIST SP 800-38D mô tả GCM như một cơ chế authenticated encryption với associated data. [NIST: SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final).

### 6.1. Nonce không chỉ là một trường có đủ độ dài

Với GCM, tính duy nhất của nonce theo cùng khóa là điều kiện quan trọng. Yêu cầu phải nêu chiến lược sinh và giới hạn sử dụng profile, bao gồm nhiều process, nhiều node, retry và phục hồi từ snapshot. Không tái dùng một cặp key–nonce để mã hóa lại chỉ vì bản ghi hoặc plaintext giống nhau.

Nếu dùng nonce ngẫu nhiên, phải xét giới hạn số lần dùng khóa và xác suất trùng theo thiết kế được duyệt. Nếu dùng bộ đếm, phải giữ tính duy nhất qua đồng thời, restart và restore. Một bài test sinh vài nghìn giá trị không trùng không tự chứng minh invariant cho cả hệ thống.

### 6.2. Ràng buộc ciphertext với đúng tài nguyên

Giả sử cùng một dịch vụ mã hóa báo cáo của nhiều tenant. Nếu chỉ xác thực nội dung blob mà không ràng buộc ngữ cảnh, một ciphertext hợp lệ có thể bị chép sang vị trí khác rồi được giải mã dưới một ý nghĩa không dự định.

AAD của tình huống có thể gồm tenant ID, report ID, mục đích `learning-report` và format version. Những giá trị này phải được lấy hoặc đối chiếu với ngữ cảnh server có thẩm quyền, không chỉ tin metadata đi cùng blob. Cách serialize AAD phải ổn định và không mơ hồ; không ghép chuỗi bằng dấu phân cách tùy ý rồi bỏ qua collision về biểu diễn.

AAD được xác thực nhưng không được AEAD giữ bí mật. Nếu metadata tự nó nhạy cảm, cần chọn cách đặt hoặc bảo vệ metadata theo một quyết định riêng.

### 6.3. Toàn vẹn mật mã chưa phải chống rollback nghiệp vụ

Một ciphertext cũ hợp lệ vẫn có thể vượt qua xác thực nếu được đưa lại đúng ngữ cảnh. Nếu cần phát hiện quay về một báo cáo cũ, hệ thống phải có version, thời hạn hoặc trạng thái chống replay/rollback có thẩm quyền.

Chỉ đặt version bên trong blob không đủ nếu đối thủ có thể quay lại cả blob lẫn version mà hệ thống dùng làm nguồn chuẩn. Mô hình đe dọa phải chỉ ra trạng thái nào được tin và cách xác minh tính mới của dữ liệu.

## 7. Ví dụ Java: tách quyền nghiệp vụ khỏi dịch vụ mật mã

Ví dụ Java 17 sau mô tả ranh giới sử dụng cryptography, không tự triển khai thuật toán. Interface `ReportCrypto` phải được hiện thực bằng thư viện/dịch vụ đã được duyệt và đáp ứng hợp đồng được ghi trong comment.

```java
import java.util.Objects;
import java.util.UUID;

public final class ProtectedReports {
    public record Actor(UUID subjectId, UUID tenantId) {
        public Actor {
            Objects.requireNonNull(subjectId);
            Objects.requireNonNull(tenantId);
        }
    }

    public record Context(
            UUID tenantId,
            UUID reportId,
            String purpose,
            int formatVersion
    ) {}

    public record Envelope(
            int formatVersion,
            String suiteId,
            String keyRef,
            byte[] payload
    ) {
        public Envelope {
            Objects.requireNonNull(suiteId);
            Objects.requireNonNull(keyRef);
            payload = Objects.requireNonNull(payload).clone();
        }

        @Override
        public byte[] payload() {
            return payload.clone();
        }
    }

    public interface AccessPolicy {
        void requireRead(Actor actor, UUID reportId);
        void requireWrite(Actor actor, UUID reportId);
    }

    public interface ReportCrypto {
        // Chỉ dùng profile/key được phép; ràng buộc Context vào AAD.
        // Thất bại thì báo lỗi, không trả payload plaintext thay thế.
        Envelope seal(Context context, byte[] plaintext);

        // Giới hạn format/suite/keyRef theo registry tin cậy.
        // Chỉ trả plaintext sau khi xác thực toàn bộ thành công.
        byte[] open(Context expectedContext, Envelope envelope);
    }

    public interface Repository {
        void save(UUID tenantId, UUID reportId, Envelope envelope);
        Envelope load(UUID tenantId, UUID reportId);
    }

    private final AccessPolicy access;
    private final ReportCrypto crypto;
    private final Repository repository;

    public ProtectedReports(
            AccessPolicy access,
            ReportCrypto crypto,
            Repository repository
    ) {
        this.access = Objects.requireNonNull(access);
        this.crypto = Objects.requireNonNull(crypto);
        this.repository = Objects.requireNonNull(repository);
    }

    public void write(Actor actor, UUID reportId, byte[] plaintext) {
        access.requireWrite(actor, reportId);
        Objects.requireNonNull(plaintext);
        if (plaintext.length > 1_048_576) {
            throw new IllegalArgumentException("Report exceeds example limit");
        }
        Context context = context(actor, reportId);
        Envelope envelope = Objects.requireNonNull(crypto.seal(context, plaintext));
        repository.save(actor.tenantId(), reportId, envelope);
    }

    public byte[] read(Actor actor, UUID reportId) {
        access.requireRead(actor, reportId);
        Envelope envelope = repository.load(actor.tenantId(), reportId);
        return crypto.open(context(actor, reportId), envelope);
    }

    private static Context context(Actor actor, UUID reportId) {
        return new Context(actor.tenantId(), reportId, "learning-report", 1);
    }
}
```

Actor phải xuất phát từ ngữ cảnh xác thực server, không được deserialize tùy ý từ request. `AccessPolicy` vẫn chịu trách nhiệm kiểm tra object, tenant và thao tác; possession của một ciphertext hoặc key reference không cấp quyền đọc báo cáo.

Giới hạn một MiB là policy minh họa cho báo cáo nhỏ, không phải hạn mức bảo mật phổ quát. `Repository` phải thực thi tenant scoping và những điều kiện đồng thời/giao dịch cần thiết. Code trên không thay các điều kiện domain đó.

`Envelope.payload` là biểu diễn do crypto provider định nghĩa, chứa các thành phần cần thiết như ciphertext/nonce/tag theo format được duyệt. Metadata trong envelope không được phép tự chọn một thuật toán lạ, tải khóa từ URL tùy ý hoặc bật một fallback không xác thực.

Các interface giúp bài kiểm tra xác định rõ: actor trái quyền không được gọi đường giải mã; lỗi seal không được dẫn tới lưu plaintext; lỗi xác thực không được trả một phần báo cáo. Chúng không tự chứng minh implementation mật mã đã đúng — phần đó cần cấu hình, review và bằng chứng riêng của provider.

## 8. Quản lý khóa là một phần của yêu cầu, không phải chi tiết triển khai phụ

Khóa cần có owner, mục đích và vòng đời từ lúc sinh tới khi ngừng sử dụng hoặc hủy. OWASP nhấn mạnh cả bảo vệ key material, mối liên hệ giữa khóa với mục đích sử dụng và kế hoạch khi khóa bị compromise. [OWASP: Key Management](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).

### 8.1. Phân biệt các giá trị thường bị gọi chung là secret

| Giá trị | Vai trò | Yêu cầu cần chốt |
| --- | --- | --- |
| Khóa đối xứng/private key | Thực hiện thao tác mật mã có quyền | Bí mật, entropy, scope sử dụng và vòng đời |
| Public key | Xác minh hoặc tham gia giao thức theo loại khóa | Tính xác thực của liên kết key–chủ thể/mục đích |
| Salt của password verifier | Phân biệt việc xử lý các mật khẩu | Quy tắc sinh/lưu theo password hashing scheme; thường không cần giữ bí mật |
| Nonce/IV | Tham số của mode hoặc giao thức | Tính duy nhất, khó đoán hoặc điều kiện khác theo đúng cơ chế |
| Authentication tag/MAC | Bằng chứng kiểm tra toàn vẹn theo khóa | Kiểm tra đúng trước khi chấp nhận dữ liệu |
| Key reference/version | Chọn khóa trong registry được phép | Không cho metadata tự mở rộng quyền dùng khóa |

Không thay nonce bằng salt chỉ vì cả hai có byte ngẫu nhiên. Không dùng mật khẩu người dùng trực tiếp như khóa AES. Nếu một thiết kế thực sự cần tạo khóa từ mật khẩu, phải có KDF và profile riêng cho mục tiêu đó, không tự tái sử dụng một đoạn hash từ flow đăng nhập.

### 8.2. Quyền dùng khóa và quyền đọc storage phải được phân tách

Trong tình huống backup báo cáo, quyền tải backup không được kéo theo quyền unwrap hoặc decrypt. Tách service identity, policy KMS, môi trường và mục đích sử dụng để một quyền vận hành đơn lẻ không tự có toàn bộ khả năng đọc plaintext.

Không lưu khóa plaintext cùng ciphertext, trong source code hoặc trong artifact có cùng quyền đọc với kho dữ liệu. Một biến môi trường cũng có thể bị lộ qua cấu hình, dump hay công cụ vận hành; nó không mặc định tương đương một KMS/HSM với quyền sử dụng và audit được kiểm soát.

KMS/HSM không tự cấp đúng quyền nghiệp vụ cho mọi request. Một workload được phép giải mã quá rộng vẫn có thể trở thành đường đọc dữ liệu của nhiều tenant. Cần giới hạn identity, key scope, mục đích, context và quyền của caller tại lớp ứng dụng.

### 8.3. Vòng đời registry mẫu

Một registry ứng dụng có thể biểu diễn trạng thái sử dụng như sau:

| Trạng thái trong thiết kế mẫu | Hành vi được phép |
| --- | --- |
| Chuẩn bị | Sinh, kiểm tra và cấu hình quyền; chưa dùng cho dữ liệu mới |
| Active for write/read | Được dùng bảo vệ dữ liệu mới và mở dữ liệu hợp lệ theo policy |
| Read-only historical | Không mã hóa mới, chỉ giải mã dữ liệu cũ cần được giữ |
| Suspended/restricted | Ngừng hoặc giới hạn thao tác để điều tra theo policy |
| Compromised | Xử lý theo kế hoạch sự cố; không tiếp tục coi như khóa active bình thường |
| Destroyed | Không còn key material để thực hiện thao tác theo phạm vi hủy đã xác minh |

Đây là mô hình hành vi của registry minh họa, không phải một danh sách thay thế mọi trạng thái của tiêu chuẩn quản lý khóa. Mỗi triển khai phải ánh xạ đúng trạng thái của nhà cung cấp và policy tổ chức.

Cryptoperiod và giới hạn dùng khóa cần phụ thuộc mức nhạy cảm, profile, khối lượng dữ liệu, rủi ro compromise và khả năng vận hành. Không chờ một ngày rotation theo lịch nếu đã tới giới hạn dùng của mode hoặc đã có dấu hiệu khóa bị lộ.

## 9. Envelope encryption và khả năng phục hồi

Một kiến trúc thường dùng là tách data encryption key (DEK) khỏi key encryption key (KEK):

```text
Plaintext báo cáo
  └── AEAD bằng DEK + context
      └── ciphertext và tham số xác thực

DEK
  └── bảo vệ bằng cơ chế key wrapping được duyệt dưới KEK
      └── wrapped DEK

Kho dữ liệu giữ ciphertext, tham số, wrapped DEK và key reference.
KEK/key material có thẩm quyền được quản lý ngoài quyền đọc kho dữ liệu.
```

Sơ đồ là mô hình khái niệm. Cách KMS sinh, unwrap hoặc sử dụng DEK cụ thể phụ thuộc API và profile đã chọn. Không dùng việc có hai tên khóa để suy rằng dữ liệu đã được bảo vệ nếu quyền unwrap vẫn mở cho bất kỳ người đọc database nào.

### 9.1. Rotation không phải lúc nào cũng là cùng một tác vụ

Đổi KEK có thể cho phép rewrap DEK mà không mã hóa lại toàn bộ nội dung, tùy kiến trúc/provider. Đổi DEK hoặc đổi cipher profile thường đòi hỏi xử lý lại ciphertext theo kế hoạch migration tương ứng.

Yêu cầu cần ghi rõ dữ liệu mới dùng key version nào, dữ liệu cũ còn được mở bằng version nào, tiến độ migration đo ra sao và khi nào có thể ngừng quyền với khóa cũ. “Rotation thành công” không đủ nếu vẫn chưa biết bao nhiêu blob phụ thuộc key version sắp bị hủy.

Một batch migration phải bảo toàn context, quyền tenant và tính toàn vẹn. Ghi ciphertext mới cùng metadata theo cơ chế nhất quán; khi lỗi không được để một bản ghi trỏ đến key version mới trong khi payload vẫn thuộc format cũ.

### 9.2. Backup khóa phải khớp nhu cầu khôi phục dữ liệu

Backup dữ liệu đã mã hóa nhưng mất đường phục hồi khóa có thể dẫn đến mất khả năng đọc dữ liệu hợp lệ. Ngược lại, một bản sao khóa không được bảo vệ có thể vô hiệu hóa mục tiêu bảo mật của backup.

Cần diễn tập restore trong môi trường được phép với quyền tách biệt: nạp đúng data snapshot, khôi phục registry/key reference cần thiết, xác thực một số dữ liệu kiểm soát và chứng minh bên chỉ có backup không tự có quyền decrypt.

Nếu nonce dựa trên trạng thái có thể rollback khi restore, kế hoạch phục hồi phải ngăn lặp cặp key–nonce sau đó. Phục hồi được plaintext cũ chưa đủ để chứng minh hệ thống có thể tiếp tục mã hóa dữ liệu mới an toàn.

### 9.3. Hủy khóa không tự xóa mọi dấu vết của dữ liệu

Cryptographic erasure cần mô tả những bản sao khóa, DEK đã cache/wrap, replica và backup nào nằm trong phạm vi. Plaintext đã export, log hoặc gửi cho người nhận không biến mất chỉ vì một khóa ở KMS bị xóa.

Không hủy key version còn cần cho dữ liệu phải giữ khi chưa hoàn tất kiểm tra phụ thuộc và thẩm quyền xử lý. Việc hủy dữ liệu, retention và legal hold của một dự án cần quy trình riêng; một tác vụ crypto migration không tự có quyền quyết định các nghĩa vụ đó.

## 10. Lỗi mật mã không được chuyển thành plaintext hoặc bỏ xác minh

Các lỗi cần có hành vi xác định gồm: tag không hợp lệ, AAD không khớp, key reference không được phép, format không hỗ trợ, KMS timeout, certificate sai và khóa ở trạng thái không được dùng.

| Lỗi | Hành vi cần giữ trong tình huống |
| --- | --- |
| Xác thực ciphertext thất bại | Không trả plaintext hoặc một phần plaintext; lỗi ngoài không lộ chi tiết nhạy cảm |
| Key reference ngoài registry | Không tự tải key/URL ngoài policy và không thử khóa tùy ý |
| Crypto provider không sẵn có | Không lưu plaintext thay thế, không báo thành công giả |
| Certificate/hostname không hợp lệ | Không tắt verify hoặc chuyển sang kênh không bảo vệ |
| Format hoặc suite lạ | Từ chối theo contract; không suy đoán một mode yếu hơn |
| Khóa bị hạn chế/thu hồi | Tuân policy trạng thái, kể cả các cache hoặc worker nền liên quan |

Fail-closed không có nghĩa bỏ qua yêu cầu availability. Cần chốt timeout, retry có giới hạn, circuit breaker, RTO/RPO và cơ chế phục hồi phù hợp. Một hàng đợi tạm giữ plaintext ngoài policy không phải giải pháp availability chấp nhận được chỉ vì KMS đang lỗi.

Nếu có cache key/DEK, phải quy định scope, thời gian tồn tại, giới hạn kích thước, bảo vệ bộ nhớ phù hợp và hành vi khi quyền khóa thay đổi. Không hứa “thu hồi có hiệu lực ngay” nếu đường cache vẫn tiếp tục dùng key material theo một TTL chưa được xét.

Các thông báo bên ngoài có thể được gom theo error contract để giảm lộ trạng thái nhạy cảm; audit nội bộ vẫn cần đủ reason code để điều tra. Không đưa key bytes, password, plaintext báo cáo hoặc toàn bộ payload nhạy cảm vào log để chẩn đoán lỗi.

## 11. Crypto agility cần có kiểm soát

Thuật toán, giao thức, provider hoặc ràng buộc vận hành có thể thay đổi. Hệ thống cần biết dữ liệu đang dùng profile nào, ở đâu và còn phụ thuộc key version nào để có thể thay đổi có kế hoạch.

Một envelope có version và suite ID giúp lựa chọn implementation đã duyệt. Nhưng nó không phải quyền cho client cung cấp tùy ý tên thuật toán, tag length hoặc key URL. Reader cần allowlist format/profile và kế hoạch ngừng đọc format cũ, không tự fallback sau lỗi xác thực.

Khi chuyển profile, phân biệt “không viết mới bằng profile cũ” với “không còn đọc dữ liệu cũ”. Có thể cần giai đoạn đọc có giới hạn để migrate, nhưng phải biết thời hạn, owner và rủi ro; không giữ parser cũ vô thời hạn chỉ vì còn một metadata version.

Với dữ liệu cần giữ bí mật lâu hoặc chữ ký cần được xác minh nhiều năm, thời hạn bảo vệ là đầu vào để chuyên gia và owner chọn lộ trình công nghệ phù hợp, kể cả đánh giá thay đổi tiêu chuẩn. Không tự sáng tác thuật toán hoặc tự kết hợp các primitive để giải quyết một yêu cầu tương lai chưa được phân tích.

Profile đã duyệt nên ghi revision, cơ sở lựa chọn, provider, tham số, giới hạn dùng và thời điểm rà soát. Một yêu cầu dài hạn tham chiếu profile theo cơ chế quản trị rõ ràng thường dễ duy trì hơn việc rải hằng số thuật toán không có owner trong nhiều service.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-CR-01 | Mỗi use case mật mã có tài sản, mục tiêu, đối thủ và giả định trust boundary được ghi rõ | Ma trận threat model và liên kết kiến trúc |
| SR-CR-02 | Dữ liệu phải bảo vệ khi lưu được xử lý ở lớp đáp ứng đúng đối thủ đã xác định | Kiểm tra data flow, storage/backup và quyền thực tế |
| SR-CR-03 | Giao thức, thuật toán, tham số và thư viện tuân crypto profile đã duyệt; không dùng lựa chọn từ client ngoài registry | Readback cấu hình/provider và ca metadata lạ |
| SR-CR-04 | Khóa và token cần tính khó đoán được tạo bằng CSPRNG theo scheme; không hard-code key material | Kiểm tra nguồn sinh và đường provisioning |
| SR-CR-05 | Khóa không nằm trong cùng quyền đọc với ciphertext; identity chỉ có thao tác key cần thiết | Ma trận quyền storage/KMS và thử workload bị từ chối |
| SR-CR-06 | AEAD xác thực ciphertext và context trước khi trả plaintext; lỗi không có fallback không bảo vệ | Ca sửa payload, tag, nonce hoặc AAD và kiểm tra hiệu ứng |
| SR-CR-07 | Invariant nonce theo key được giữ qua đồng thời, retry, restart và restore | Thiết kế nguồn nonce, giới hạn dùng và kiểm tra lifecycle |
| SR-CR-08 | Mật khẩu dùng password hashing profile thích hợp, có salt/tham số và đường nâng cấp verifier | Cấu hình cùng kiểm tra verifier/rehash theo policy |
| SR-CR-09 | Lỗi KMS/provider/TLS không dẫn tới plaintext storage hoặc bỏ xác minh | Fault injection có kiểm soát và đọc lại trạng thái |
| SR-CR-10 | Khóa có owner, mục đích, trạng thái, cryptoperiod, giới hạn dùng và kế hoạch compromise | Registry cùng quy trình/diễn tập tương ứng |
| SR-CR-11 | Backup/restore giữ được quyền đọc hợp lệ mà không phá điều kiện mật mã sau phục hồi | Diễn tập restore dữ liệu, key dependency và tiếp tục ghi |
| SR-CR-12 | Rotation/migration có version, tiến độ và gate trước khi ngừng/hủy khóa cũ | Đối soát envelope/key version và kết quả migration |
| SR-CR-13 | Plaintext, password và key material không đi vào log/trace/file tạm ngoài policy | Kiểm tra các kênh quan sát bằng dữ liệu canary |
| SR-CR-14 | Authorization, replay/rollback và business invariants được xử lý riêng khỏi xác thực mật mã | Ca actor trái quyền, tráo ngữ cảnh và phát lại dữ liệu hợp lệ |

Các yêu cầu phải gắn với phạm vi thật. Nếu một endpoint không dùng mật khẩu, SR-CR-08 không tự buộc thêm password flow. Nếu một use case chỉ cần chữ ký chứ không cần bí mật, phải đặc tả đúng quyền ký/xác minh thay vì thêm encryption không có mục tiêu.

Một yêu cầu như “mọi dữ liệu đều được mã hóa” cần được chia theo nơi xuất hiện: database, object storage, cache, export, backup và telemetry. Mỗi vị trí có quyền và lifecycle riêng; một cấu hình mã hóa database không tự bao phủ tất cả.

## 13. Thiết kế bằng chứng kiểm chứng

Phần này mô tả cách xác minh một triển khai sản phẩm; không khẳng định các kiểm thử dưới đây đã được chạy trong bài học.

### 13.1. Chứng minh mục tiêu và giới hạn

Với báo cáo mẫu, có thể đặt một nội dung canary không nhạy cảm vào dữ liệu thử, rồi quan sát representation trong những kho thuộc phạm vi. Canary giúp tìm plaintext bị lưu hoặc log ngoài ý muốn, nhưng “không tìm thấy canary” không thay review quyền khóa và độ đúng của profile.

Một phép thử encrypt rồi decrypt thành công chỉ chứng minh đường happy path khôi phục dữ liệu đó. Nó chưa chứng minh hệ thống phát hiện sửa đổi, ràng buộc tenant hoặc giữ key material ngoài quyền đọc storage.

### 13.2. Ma trận ca kiểm thử

| Ca | Điều kiện/thao tác | Kỳ vọng |
| --- | --- | --- |
| K1 | Actor đúng quyền ghi và đọc báo cáo | Dữ liệu khôi phục đúng; storage giữ biểu diễn được bảo vệ |
| K2 | Actor khác tenant yêu cầu đọc | Bị chặn theo quyền, không được plaintext chỉ vì có report ID |
| K3 | Thay một phần ciphertext hoặc tag | Xác thực thất bại; không trả dữ liệu một phần |
| K4 | Đổi nonce hoặc context kỳ vọng | Không chấp nhận như báo cáo hợp lệ |
| K5 | Chép envelope tenant A sang vị trí tenant B | Không giải mã thành dữ liệu hợp lệ dưới context B |
| K6 | Trả keyRef hoặc suiteId không được phép | Từ chối, không truy cập endpoint/key tùy ý |
| K7 | KMS timeout hoặc deny thao tác | Không lưu plaintext, không báo cập nhật thành công giả |
| K8 | Nhiều node/retry/restart cùng tạo dữ liệu | Invariant nonce theo key được giữ theo chiến lược thiết kế |
| K9 | Restore snapshot rồi ghi dữ liệu mới | Không rollback nguồn nonce vào một trạng thái gây tái dùng |
| K10 | Rotate profile/key theo kế hoạch | Dữ liệu mới dùng version mới; dữ liệu cũ đọc/migrate đúng policy |
| K11 | Khóa không được dùng hoặc bị thu hồi | Các đường trực tiếp/cache/worker hành xử theo gate đã chốt |
| K12 | Đưa lại envelope cũ nhưng hợp lệ | Kết quả theo policy replay/rollback, không suy từ tag hợp lệ |

Với K3–K6, phân biệt lỗi format, lỗi integrity và lỗi quyền ở telemetry nội bộ mà vẫn giữ error contract bên ngoài. Không đưa raw payload hay key bytes vào test report có thể được lưu rộng rãi.

### 13.3. Kiểm tra quyền có thẩm quyền

Cần thử bằng các identity đại diện: bên chỉ đọc backup, service có quyền crypto đúng scope, workload sai môi trường và actor ứng dụng không có quyền đọc đối tượng. Kiểm tra một file config có ghi “least privilege” không thay việc service thật sự bị KMS từ chối khi gọi ngoài scope.

Nếu hệ thống quản lý khóa theo tenant hoặc purpose, ca quyền phải kiểm tra cả mapping key/context, không chỉ quyền gọi một API KMS chung. Một identity có quyền dùng tất cả key vẫn là một phạm vi rủi ro cần được ghi nhận và giải thích.

### 13.4. Giới hạn của bằng chứng ngẫu nhiên và thuật toán

Không trùng nonce trong một sample chỉ là tín hiệu của sample đó. Bằng chứng chính còn là chiến lược tạo nonce, phân phối trạng thái, giới hạn dùng key và cách phục hồi. Tương tự, kiểm tra ciphertext trông “khó đọc” không cho biết nó dùng AEAD hay đã xác minh tag đúng.

Không tự xây bộ test để chứng minh một thuật toán tự chế an toàn. Chọn primitive/giao thức chuẩn, dùng implementation đã được quản lý và kiểm tra cách ứng dụng cấu hình/sử dụng chúng. Nếu có yêu cầu certification hoặc môi trường đặc thù, bằng chứng phải đúng module/provider và chế độ hoạt động liên quan.

## 14. Các giả định cần loại bỏ khi viết yêu cầu

**“Thuật toán mạnh thì hệ thống tự mạnh.”** Khóa hard-code, nonce lặp, bỏ tag hoặc cấp quyền giải mã rộng có thể làm mất mục tiêu dù primitive được chọn đúng.

**“Đã mã hóa nên người có quyền database không đọc được.”** Điều đó phụ thuộc lớp mã hóa và đường sử dụng khóa. Mã hóa minh bạch cho chính tài khoản query không tự chặn tài khoản đó đọc dữ liệu.

**“MAC/chữ ký hợp lệ nghĩa là không cần authorization.”** Kết quả mật mã chỉ có ý nghĩa trong context và mô hình khóa đã chốt; quyền trên đối tượng và thao tác vẫn phải được kiểm tra.

**“Rotation khắc phục được mọi dữ liệu đã lộ.”** Khóa mới có thể bảo vệ dữ liệu về sau, nhưng không lấy lại plaintext hoặc ciphertext/key đã bị sao chép. Cần xác định phạm vi sự cố và hành động phục hồi tương ứng.

**“Hash hoặc Base64 là anonymization/mã hóa.”** Base64 chỉ đổi biểu diễn; hash của dữ liệu dễ đoán có thể được thử hàng loạt. Quyết định giảm khả năng nhận diện cần phân tích riêng theo dữ liệu và đối thủ.

**“Không có KMS thì lưu tạm plaintext cho khỏi mất request.”** Hành vi lỗi không được phá mục tiêu bảo mật. Availability cần phương án có kiểm soát và giới hạn, không phải fallback bỏ bảo vệ.

**“Hủy một key là xóa hết dữ liệu.”** Phải xét mọi bản sao key, wrapped key, cache, backup và plaintext đã ra ngoài phạm vi mã hóa.

## 15. Bài tập vận dụng

Một nền tảng học tập cần lưu bản xuất điểm, xác minh mật khẩu, phát chứng chỉ có thể kiểm tra bên ngoài và bảo vệ kết nối tới nhà cung cấp email. Đội phát triển đề xuất dùng cùng một khóa bí mật hard-code cho mọi nhu cầu để đơn giản vận hành.

Hãy thiết kế bộ yêu cầu thay thế:

1. Lập ma trận tài sản–đối thủ–thuộc tính cần giữ cho bốn nhu cầu, chỉ rõ mỗi cơ chế thích hợp.
2. Chọn ranh giới bảo vệ của bản xuất điểm, bao gồm storage, backup, context và quyền dùng khóa.
3. Đặc tả vòng đời khóa cho dữ liệu và khóa ký chứng chỉ, không mặc định hai mục đích có cùng policy.
4. Viết yêu cầu lỗi cho KMS không sẵn có, tag sai và certificate không hợp lệ.
5. Đề xuất ba ca nghiệm thu chứng minh quyền, integrity và khả năng restore, thay vì chỉ encrypt/decrypt round-trip.
6. Chỉ rõ những rủi ro còn lại khi một process hợp lệ đã được quyền xem plaintext bị chiếm quyền.

Kết quả cần liên kết được mục tiêu rủi ro, cơ chế, quyền khóa và bằng chứng kiểm chứng. Một yêu cầu dùng cryptography đầy đủ mô tả cả điều được bảo vệ, các điều kiện để bảo vệ có hiệu lực và cách hệ thống hành xử khi những điều kiện đó không còn đúng.
