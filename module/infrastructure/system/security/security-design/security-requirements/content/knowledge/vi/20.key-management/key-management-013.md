# Key encryption key

## 1. KEK là khóa bảo vệ những khóa khác

Key encryption key, viết tắt là KEK, là khóa dùng để bảo vệ key material khác. Trong mô hình phổ biến, data encryption key (DEK) mã hóa nội dung nghiệp vụ, còn KEK wrap DEK để có thể lưu hoặc vận chuyển DEK dưới dạng được bảo vệ.

```text
DEK bảo vệ dữ liệu
KEK bảo vệ DEK
```

NIST sử dụng thuật ngữ key-encryption key trong ngữ cảnh bảo vệ khóa và các cơ chế key wrapping. Tên gọi mô tả vai trò, không tự xác định một thuật toán duy nhất hay vị trí lưu trữ bắt buộc. [NIST: Key-Encryption-Key](https://csrc.nist.gov/glossary/term/key_encryption_key).

Trong module yêu cầu bảo mật, mục tiêu không chỉ là “thêm một lớp mã hóa”. Cần giữ được ranh giới: người đọc database hoặc backup chứa ciphertext và wrapped DEK không tự có quyền unwrap. Đồng thời, ứng dụng hợp lệ phải có cách sử dụng đúng DEK khi đã kiểm tra quyền nghiệp vụ.

Một KEK bị lộ hoặc bị cấp quyền dùng quá rộng có thể ảnh hưởng tới nhiều DEK bên dưới. Vì vậy KEK cần purpose, scope, vòng đời và gate quản trị rõ hơn một hằng số bí mật đặt trong cấu hình ứng dụng.

Bài học dùng tình huống nền tảng học tập mã hóa báo cáo kết quả theo tenant. Các profile, key version và API trong ví dụ là minh họa thiết kế, không phải cấu hình hoặc thao tác đã được thực hiện trên hạ tầng thật.

## 2. Phân biệt KEK, DEK và root key

| Thành phần | Vai trò trong tình huống | Phạm vi ảnh hưởng cần xét |
| --- | --- | --- |
| DEK | Mã hóa một báo cáo hoặc một nhóm dữ liệu theo policy | Nội dung được mã hóa dưới DEK đó |
| KEK | Wrap/unwrap các DEK trong scope đã chốt | Những wrapped DEK có thể được mở bằng KEK |
| Root/master key trong một hierarchy | Bảo vệ key cấp dưới hoặc nằm ở gốc trust của provider | Có thể ảnh hưởng nhiều KEK hoặc toàn một boundary |
| Key ID/version | Chọn resource/material version trong registry | Không phải key material; cần integrity và mapping đúng |
| Alias hiện tại | Chọn đích wrap cho dữ liệu mới theo policy | Không mô tả mọi key version dữ liệu cũ còn phụ thuộc |

KEK không nhất thiết là root key. Một hệ thống có thể có root bảo vệ tenant KEK, rồi tenant KEK bảo vệ nhiều DEK. Một hệ thống đơn giản hơn có thể chỉ cần một lớp KEK do KMS quản lý. Thêm tầng chỉ có giá trị nếu mục tiêu phân tách quyền, recovery hoặc vòng đời cần nó.

Không dùng trực tiếp một key material cho cả mã hóa báo cáo, wrap DEK và ký chứng chỉ chỉ vì cùng có thể biểu diễn thành byte. Vai trò, primitive, quyền sử dụng và lifecycle khác nhau cần được tách theo profile.

### 2.1. Một hierarchy minh họa

```text
Boundary KMS/HSM
└── KEK báo cáo của tenant A, version 7
    ├── wrapped DEK của report A-101
    ├── wrapped DEK của report A-102
    └── wrapped DEK của report A-103

Kho báo cáo
└── Mỗi report giữ ciphertext cùng envelope cần thiết
```

Scope một KEK trên mỗi tenant là một lựa chọn kiến trúc, không phải yêu cầu chung. Nó có thể giảm phạm vi quản trị và compromise, nhưng tăng số resource, quota và nhu cầu vận hành. Dù chọn granularity nào, phải chứng minh identity không unwrap được ngoài scope được cấp.

## 3. KEK giúp giảm rủi ro nào và không giải quyết điều gì?

| Tình huống | Lợi ích mong muốn | Giới hạn cần giữ trong đặc tả |
| --- | --- | --- |
| Đọc được database/backup | Chỉ có ciphertext và wrapped DEK chưa đủ mở dữ liệu | Quyền unwrap và recovery root phải được tách khỏi quyền đọc storage |
| Cần thay khóa quản lý nhiều DEK | Có thể rewrap DEK thay vì xử lý lại mọi byte dữ liệu | Không đồng nghĩa mọi loại compromise đã được khắc phục |
| Nhiều workload dùng cùng kho báo cáo | KMS/policy có thể giới hạn ai được unwrap theo scope | KMS không tự biết actor ứng dụng có quyền trên report nào |
| Process ứng dụng đã được cấp DEK bị chiếm | Có thể giới hạn KEK không xuất và giảm raw root material ở process | Plaintext DEK/dữ liệu mà process hợp lệ dùng vẫn có thể bị lộ |
| Wrapped DEK bị tráo giữa bản ghi | Có thể phát hiện bằng binding/context và data AEAD phù hợp | Không được giả định mọi wrap scheme tự xác thực tenant/report metadata |

Không gọi envelope encryption là bảo vệ tuyệt đối trước application compromise. Nếu một service identity có quyền unwrap tất cả KEK và ứng dụng không kiểm tra tenant/object, hierarchy chỉ di chuyển lỗi quyền sang một API mật mã khác.

Cần phân tích cả data path và control plane: ai đọc wrapped DEK, ai gọi unwrap, ai thay alias/policy, ai có thể tạo thêm bản wrap dưới một KEK khác và ai có quyền hủy recovery dependency.

## 4. Envelope encryption diễn ra như thế nào?

### 4.1. Đường ghi dữ liệu mới

Một flow mẫu:

```text
Actor được xác thực và phân quyền ghi report
→ chọn crypto profile và KEK active trong registry đúng scope
→ tạo DEK theo cơ chế được duyệt
→ mã hóa report bằng data AEAD và context của report
→ wrap DEK bằng KEK/profile đã chọn
→ lưu ciphertext cùng envelope nhất quán
```

Một số provider/API kết hợp tạo DEK với việc trả wrapped DEK. Một số kiến trúc sinh DEK ở ứng dụng rồi wrap trong boundary được duyệt. Cần chốt plaintext DEK xuất hiện ở đâu; việc gọi KMS không tự có nghĩa ứng dụng chưa từng giữ DEK.

Khi một bước thất bại, không ghi report plaintext hoặc DEK raw làm phương án dự phòng. Trạng thái dữ liệu và envelope phải nhất quán; không báo cập nhật thành công với một ciphertext thiếu đường mở hợp lệ.

### 4.2. Đường đọc dữ liệu

```text
Actor được phân quyền đọc đúng report
→ tải envelope có giới hạn và xác định scope kỳ vọng
→ resolve KEK/version trong registry được phép
→ unwrap với đúng profile/context
→ xác thực data AEAD và context của report
→ chỉ trả plaintext sau khi mọi điều kiện đạt
```

Unwrap thành công chưa chứng minh caller được đọc report. Nó cũng chưa chứng minh ciphertext báo cáo không bị sửa; data AEAD là lớp kiểm tra riêng trên dữ liệu nghiệp vụ.

### 4.3. Envelope cần giữ thông tin gì?

| Trường logic | Ý nghĩa |
| --- | --- |
| Format version | Chọn parser/reader thuộc tập được hỗ trợ |
| Data crypto profile | Thuật toán/tham số dữ liệu đã được duyệt |
| Wrap profile | Cách biểu diễn/bảo vệ DEK phù hợp |
| Logical KEK/version hoặc reference | Chọn đúng key trong scope có thẩm quyền |
| Wrapped DEK | Material đã được bảo vệ, không phải raw DEK |
| Nonce/tag hoặc thành phần tương ứng | Tham số của data AEAD theo format |
| Ciphertext và context cần thiết | Nội dung được bảo vệ và cách ràng buộc tài nguyên |

Metadata là dữ liệu bên ngoài ranh giới tin cậy khi đọc từ storage có thể bị sửa. Reader không được cho những trường này tự chọn URL key, algorithm tùy ý hoặc bỏ bước kiểm tra để tìm một cách decrypt được.

## 5. Dùng key wrapping scheme, không tự chế một lớp mã hóa khóa

Key wrapping cần bảo vệ confidentiality và integrity của key material theo scheme được chọn. NIST SP 800-38F mô tả các phương pháp key wrapping, trong đó có AES Key Wrap (KW) và AES Key Wrap with Padding (KWP). [NIST: SP 800-38F](https://csrc.nist.gov/pubs/sp/800/38/f/final).

Không dùng XOR với một secret, hash có khóa ghép tay hoặc một chế độ AES mặc định không được xác định rõ rồi gọi đó là KEK protection. Chọn scheme/library/provider cùng format và giới hạn đầu vào đã được duyệt.

### 5.1. KW và KWP không phải cùng một format tùy ý thay thế

AES-KW có cấu trúc và ràng buộc độ dài key data theo RFC 3394. KWP mở rộng cho các độ dài đầu vào khác với padding theo RFC 5649. Hai bên phải thống nhất format; không tự thử cả hai để chấp nhận mọi input lạ. [RFC 3394: AES Key Wrap](https://www.rfc-editor.org/rfc/rfc3394.html), [RFC 5649: AES Key Wrap with Padding](https://www.rfc-editor.org/rfc/rfc5649.html).

KW/KWP có cách xử lý riêng, không phải một API AES-GCM mà caller tự thêm nonce. Không áp quy tắc nonce của data AEAD sang mọi wrapping scheme chỉ vì tất cả đều dùng AES bên dưới.

Profile cần ghi algorithm, tham số, kích thước key và giới hạn material được wrap. Việc KEK có nhiều bit không bù được một DEK sinh từ entropy yếu hoặc một quy trình để lộ raw key.

### 5.2. Integrity của wrapped key không tự bảo vệ mọi metadata

Một scheme có kiểm tra integrity cho material không tự chứng minh rằng key thuộc tenant/report nào. AES-KW thuần không có một interface AAD tùy ý giống data AEAD. Nếu cần binding metadata, phải dùng thiết kế/protocol đáp ứng rõ điều đó, không đặt một JSON field cạnh blob rồi gọi nó là “đã xác thực”.

Key wrap scheme cũng không thay authorization, freshness hoặc chống rollback. Một wrapped DEK cũ vẫn có thể hợp lệ về mật mã dưới KEK phù hợp.

## 6. Ràng buộc scope ở cả wrap và data layer

Trong tình huống báo cáo, có hai lớp context cần tách:

| Lớp | Context minh họa | Mục tiêu |
| --- | --- | --- |
| Bảo vệ DEK | App/purpose, tenant scope, profile/version theo API hỗ trợ | Không mở wrapped key ngoài context được phép |
| Data AEAD | Tenant ID, report ID, purpose và format/version đã chốt | Không dùng ciphertext như một tài nguyên khác |

Context kỳ vọng phải được dựng hoặc đối chiếu bằng thông tin server có thẩm quyền. Nếu chỉ lấy nguyên `tenantId` từ envelope rồi kiểm tra với chính envelope, việc so sánh chưa tạo một ranh giới tenant độc lập.

AWS KMS là một ví dụ API sử dụng encryption context làm AAD cho symmetric encryption KMS operations; context phải khớp để decrypt, và không được coi là secret vì có thể xuất hiện trong log. Không áp cơ chế đó cho mọi loại key/API mà provider không hỗ trợ. [AWS KMS: encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html).

Không đưa điểm số, mật khẩu, token hoặc thông tin riêng của học viên vào context được log chỉ để “ràng buộc mạnh hơn”. Chọn metadata cần thiết, có biểu diễn ổn định và đúng policy công bố. Dữ liệu cần bí mật vẫn thuộc phần được mã hóa theo thiết kế.

Nếu application dùng một wrap scheme không có context riêng, phải giải thích rõ lớp nào thực thi binding và policy key selection. Không hứa rằng một lời gọi wrap primitive đã giải quyết toàn bộ vấn đề tráo tenant.

## 7. Ví dụ Java: wrap một AES DEK bằng AES-256 KEK

Ví dụ Java 17 sau dùng profile minh họa AES-KW với KEK 256 bit và DEK AES 256 bit. DEK 32 byte được KW wrap thành 40 byte theo format tương ứng. Tên `AESWrap_256` được định nghĩa trong danh mục thuật toán Java; provider triển khai vẫn phải hỗ trợ profile đó. [Oracle: Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html#cipher-algorithms).

```java
import java.security.GeneralSecurityException;
import java.security.InvalidKeyException;
import java.security.Key;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;

public final class Aes256KekExample {
    private static final String WRAP_TRANSFORMATION = "AESWrap_256";
    private static final int WRAPPED_AES_256_BYTES = 40;

    public static byte[] wrap(SecretKey kek, SecretKey dataKey)
            throws GeneralSecurityException {
        Objects.requireNonNull(kek, "KEK required");
        Objects.requireNonNull(dataKey, "DEK required");
        if (!"AES".equalsIgnoreCase(dataKey.getAlgorithm())) {
            throw new InvalidKeyException("Expected an AES data key");
        }

        Cipher wrapper = Cipher.getInstance(WRAP_TRANSFORMATION);
        wrapper.init(Cipher.WRAP_MODE, kek);
        byte[] wrapped = wrapper.wrap(dataKey);
        if (wrapped.length != WRAPPED_AES_256_BYTES) {
            throw new InvalidKeyException("DEK outside example profile");
        }
        return wrapped;
    }

    public static SecretKey unwrap(SecretKey kek, byte[] wrappedDataKey)
            throws GeneralSecurityException {
        Objects.requireNonNull(kek, "KEK required");
        Objects.requireNonNull(wrappedDataKey, "Wrapped DEK required");
        if (wrappedDataKey.length != WRAPPED_AES_256_BYTES) {
            throw new InvalidKeyException("Wrapped DEK outside example profile");
        }
        byte[] exactWrappedKey = wrappedDataKey.clone();

        Cipher wrapper = Cipher.getInstance(WRAP_TRANSFORMATION);
        wrapper.init(Cipher.UNWRAP_MODE, kek);
        Key result = wrapper.unwrap(exactWrappedKey, "AES", Cipher.SECRET_KEY);
        if (!(result instanceof SecretKey secretKey)) {
            throw new InvalidKeyException("Unexpected unwrapped key type");
        }
        return secretKey;
    }

    private Aes256KekExample() {}
}
```

JCE có `WRAP_MODE`, `UNWRAP_MODE` cùng các phương thức wrap/unwrap dành cho thao tác khóa. Không thay chúng bằng `Cipher.getInstance("AES")` với mode/padding không được công bố. [Oracle Java 17: Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html).

Đây là ví dụ primitive, không phải một envelope encryption protocol hoàn chỉnh. Nó không resolve KEK theo tenant, không kiểm tra quyền actor, không có AAD cho wrap và không quản lý vòng đời. Những việc đó phải được thực hiện ở lớp policy/provider phù hợp như các phần khác của bài.

Đối với HSM/KMS, dùng API và provider tương ứng với boundary được duyệt. `SecretKey` trong code không tự bảo đảm material không xuất được; không kéo KEK về heap hoặc ép export DEK trái policy chỉ để dùng helper này.

Mỗi lời gọi tạo một Cipher instance cho thao tác đó. Lỗi unwrap/integrity hoặc profile không hỗ trợ phải được xử lý là thất bại, không thử plaintext, không giảm thuật toán và không trả một key tùy ý để tiếp tục decrypt.

## 8. Quyền wrap/unwrap phải gắn với phạm vi

Một ma trận minh họa cho nền tảng học tập:

| Identity | Quyền cần có | Quyền không tự phát sinh |
| --- | --- | --- |
| Workload ghi báo cáo | Tạo/wrap DEK cho report trong scope và profile được cấp | Unwrap toàn bộ key của mọi tenant |
| Workload đọc báo cáo | Unwrap trong scope sau authorization ứng dụng | Thay alias, đổi key policy hoặc tạo bản wrap ngoài scope |
| Rotation worker | Rewrap nguồn–đích được phê duyệt | Đọc plaintext dữ liệu nghiệp vụ hoặc đổi mọi key provider |
| Backup operator | Tạo/đối soát backup theo policy | Decrypt report hoặc xuất raw KEK |
| Key administrator | Quản lý lifecycle theo thẩm quyền | Tự động có quyền đọc toàn bộ báo cáo |

Chi tiết quyền thực tế phụ thuộc API provider. “Có quyền Encrypt” không tự tương đương “chỉ được wrap những DEK mà ứng dụng cho phép”; một API tổng quát cần policy và đường gọi được thiết kế đúng.

Nếu một identity được cả tạo ciphertext dưới KEK và unwrap tùy ý, nó có thể dùng dịch vụ như một crypto oracle ngoài mục tiêu ban đầu. Phải xét đầu vào, context, resource scope, quota và mục đích của operation, không chỉ tên action IAM.

Một key reference từ body hoặc storage chưa tin cậy không được tự trở thành authority để gọi KMS. Resolve trong namespace được phép, đối chiếu purpose/environment/tenant và từ chối reference ngoài tập trước khi đưa material vào luồng xử lý.

## 9. Rotate KEK, rewrap DEK và rotate DEK là ba việc khác nhau

| Thay đổi | Thành phần thường thay | Điều không tự xảy ra |
| --- | --- | --- |
| Rotate material của một KEK resource theo provider | Material dùng cho các operation mới | Không tự đổi mọi DEK hoặc ciphertext dữ liệu |
| Chuyển wrapped DEK sang KEK khác | Wrapped blob/reference và metadata tương ứng | DEK có thể vẫn giữ nguyên material |
| Rotate DEK | Key dùng mã hóa dữ liệu và ciphertext liên quan | Không chỉ sửa key ID trong envelope |
| Chuyển alias active | Đích chọn cho operation mới theo cấu hình | Không tự migrate dữ liệu cũ |

AWS KMS mô tả rotation material dưới cùng một logical key resource và việc decrypt tiếp tục dùng material phù hợp. Tài liệu cũng nêu rotation đó không rotate data key hoặc mã hóa lại dữ liệu đang được bảo vệ. Phải phân biệt behavior provider này với một batch rewrap do ứng dụng điều phối. [AWS KMS: rotate keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html).

### 9.1. Rewrap có thể giữ nguyên data ciphertext

Nếu DEK vẫn phù hợp và mục tiêu là chuyển lớp bảo vệ DEK từ KEK cũ sang KEK mới, có thể unwrap rồi wrap lại DEK trong boundary được duyệt. Data ciphertext có thể giữ nguyên vì DEK không đổi.

Một số provider có operation chuyển ciphertext/key wrapping hoàn toàn phía dịch vụ. Ví dụ AWS KMS `ReEncrypt` hỗ trợ những ciphertext format phù hợp của KMS, chứ không tự hiểu mọi ciphertext từ SDK hoặc thư viện khác. [AWS KMS: ReEncrypt](https://docs.aws.amazon.com/kms/latest/APIReference/API_ReEncrypt.html).

Worker rewrap cần quyền nguồn và đích đúng scope. Không cho nó biến mọi wrapped DEK thành một bản dưới KEK do người gọi tự chọn; đó có thể là một đường chuyển quyền giải mã ra ngoài boundary mong muốn.

### 9.2. Migration phải cập nhật envelope nhất quán

Một flow có kiểm soát có thể là:

```text
Chốt source/destination KEK và profile được duyệt
→ đọc envelope cùng revision hiện tại
→ xác minh scope/context và rewrap trong boundary thích hợp
→ kiểm tra wrapped result/reference đích
→ ghi envelope mới với điều kiện revision chưa đổi
→ audit và đo coverage migration
```

Không lưu wrapped DEK mới rồi quên đổi reference, hoặc đổi reference trước khi blob mới được ghi đầy đủ. Với cập nhật đồng thời, cần transaction/compare-and-set hoặc cơ chế nhất quán phù hợp để tránh ghi đè một envelope khác vừa được thay.

Retry phải nhận biết bản ghi đã migrate hay chưa. Không đánh giá tiến độ bằng số request đã gửi tới KMS; phải đối soát trạng thái envelope thực tế, những bản thất bại và các bản snapshot/backup còn cần hỗ trợ.

### 9.3. Compromise không được xử lý bằng một nhãn rotation chung

Nếu KEK cũ đã bị lộ cùng các wrapped DEK hoặc đối thủ đã unwrap được DEK, rewrap giữ nguyên DEK không thu hồi được bí mật đã mất. Có thể cần tạo DEK mới và mã hóa lại dữ liệu còn phải bảo vệ, đồng thời đánh giá phạm vi bản sao đã bị lấy.

Ngay cả khi rewrap live database đã hoàn tất, đối thủ có thể giữ backup cũ gồm wrapped DEK dưới KEK đã lộ. Việc đổi alias không làm bản sao đó biến mất hoặc trở nên an toàn lại.

Một sự cố phải phân biệt material bị lộ, quyền KMS bị lạm dụng, context bị thay và metadata bị sửa. Kế hoạch recovery cần dựa vào khả năng thực tế của đối thủ, không chỉ vào việc provider đã báo tạo một key version mới.

## 10. Thu hồi KEK và cache DEK có giới hạn khác nhau

Vô hiệu hóa quyền unwrap có thể ngăn các lần lấy DEK mới qua đường provider. Nhưng nếu process đang giữ plaintext DEK trong cache, nó có thể tiếp tục sử dụng material đó ngoài một lời gọi KMS mới.

Vì vậy yêu cầu “thu hồi quyền giải mã có hiệu lực trong bao lâu” phải xét:

- Cache chứa DEK, key handle hay ciphertext; mỗi loại có semantics khác nhau.
- TTL, số lần dùng, scope tenant/purpose và giới hạn dung lượng cache.
- Cơ chế nhận thay đổi quyền/trạng thái khóa và hành vi khi không đồng bộ được.
- Workload, worker nền và bản sao process nào đang giữ material có thể dùng.
- Timeout và đường mở quyền trở lại theo chính sách.

Không công bố “disable KEK là mọi dữ liệu lập tức không đọc được” nếu kiến trúc còn các bản plaintext/key cache được phép sống. Nếu mục tiêu yêu cầu cửa sổ thu hồi ngắn, cache và workload lifecycle phải được thiết kế đáp ứng cửa sổ đó.

Một metadata key ID không có material có thể vô hại hơn raw key nhưng vẫn cần integrity để không resolve sai scope. Không gom mọi loại cache vào một mô tả chung rồi suy ra hiệu lực thu hồi.

## 11. Bảo vệ KEK và đường bootstrap

KEK có scope ảnh hưởng lớn nên cần boundary và quyền quản trị phù hợp. Có thể sinh/giữ nó trong KMS/HSM và chỉ cho thao tác wrap/unwrap được phép, hoặc dùng một thiết kế khác đáp ứng rõ threat model.

Không đặt raw KEK trong database cạnh wrapped DEK với cùng quyền đọc. Cũng không để backup script chứa một master password cố định làm nguồn mở mọi KEK mà bất kỳ người đọc artifact đều lấy được.

Nếu KEK lại được bảo vệ bằng key cấp trên, phải xác định recovery root và tránh chu trình không có đường mở độc lập. Một hierarchy nhiều tầng vẫn phải có một trust boundary cuối cùng; không thể giải quyết bằng cách mã hóa A bằng B rồi chỉ giữ B dưới A.

Quản lý vòng đời khóa cần bao gồm generation, phân phối/quyền dùng, cryptoperiod, backup, compromise và hủy các bản sao đúng phạm vi. Các hoạt động này phải theo mục đích của key thay vì mặc định mọi key có cùng chính sách. [OWASP: Key Management](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).

### 11.1. Backup KEK phải khớp dữ liệu còn phụ thuộc

Nếu backup dữ liệu còn chứa wrapped DEK dưới KEK v6, việc hệ thống live chỉ còn dùng v7 không tự cho phép hủy v6. Cần inventory các version, retention và cơ chế restore của provider.

Backup/failover cho key không xuất được phải dùng cơ chế boundary được duyệt. Không ép export raw material để tạo một file “DR” rồi coi như đã giữ nguyên thuộc tính non-exportable.

Sau restore, không tự re-enable một KEK đã bị hạn chế hoặc compromise sau thời điểm snapshot. Trạng thái sử dụng phải được đối chiếu với nguồn hiện tại có thẩm quyền và mục tiêu phục hồi.

### 11.2. Hủy KEK có thể làm mất dữ liệu nhiều đối tượng

Trước khi hủy, xác minh các wrapped DEK, bản sao lưu, archive và consumer còn phụ thuộc. Không lấy số request gần đây bằng zero làm bằng chứng không còn dữ liệu cần đọc.

Ngược lại, nếu còn một bản sao KEK hoặc DEK mở được dữ liệu, việc xóa một resource live chưa chứng minh cryptographic erasure đã bao phủ mọi bản sao. Phải giữ đúng phạm vi của kết luận.

## 12. Hành vi lỗi, quota và audit

### 12.1. Lỗi không được làm rơi về raw key

| Lỗi | Hành vi cần giữ |
| --- | --- |
| Wrap service không sẵn có | Không lưu plaintext DEK cạnh ciphertext để xử lý sau ngoài policy |
| Unwrap/integrity thất bại | Không nhận blob như raw DEK hoặc thử mode không bảo vệ |
| Key reference không được phép | Không gọi provider/URL tùy ý và không tự đổi tenant scope |
| Context không khớp | Từ chối; không bỏ context để thử decrypt lại |
| KEK không được dùng theo trạng thái | Không dùng một identity đặc quyền khác để lách gate |
| Migration thất bại một phần | Giữ trạng thái/coverage rõ; không xóa source dependency chưa đủ điều kiện |

Availability cần được thiết kế qua timeout, retry có giới hạn, capacity, circuit breaker và recovery, không bằng một KEK mặc định hard-code. Nếu hệ thống cần một hàng đợi cho tác vụ chưa hoàn tất, dữ liệu trong hàng đợi vẫn phải đáp ứng policy bảo vệ của nó.

Quota/rate limit cần áp dụng cho unwrap và rewrap để tránh lạm dụng và cạn tài nguyên. Chọn granularity KEK/DEK hoặc caching phải dựa vào mục tiêu và rủi ro, không mở quyền decrypt toàn hệ thống chỉ để giảm số lần resolve policy.

### 12.2. Audit tập trung vào quyết định, không chứa material

Một sự kiện mẫu có thể là:

```json
{
  "event": "DEK_REWRAP_COMPLETED",
  "operationRef": "approved-migration-operation",
  "scopeRef": "controlled-tenant-scope",
  "sourceKekRef": "report-kek-v6",
  "destinationKekRef": "report-kek-v7",
  "envelopeRevision": 12,
  "profileRevision": "report-wrap-profile-1"
}
```

Đây là schema quan sát minh họa, không phải một operation đã chạy. Audit không cần raw KEK, plaintext DEK hay toàn bộ báo cáo. Context cũng cần giảm dữ liệu vì có thể được provider ghi log dưới dạng không mã hóa.

Tách được các kết quả: provider wrap/unwrap thành công, authorization từ chối, envelope commit thành công và migration coverage đạt. Một request crypto thành công nhưng DB update thất bại không đồng nghĩa bản ghi đã migrate.

## 13. Bộ yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-KEK-01 | KEK có purpose, owner, môi trường, scope và profile được duyệt; không dùng chung material tùy ý với DEK/signing key | Inventory hierarchy và đường provisioning |
| SR-KEK-02 | KEK được bảo vệ ngoài quyền đọc storage/ciphertext theo threat model | Ma trận quyền storage/KMS và ca chỉ có backup không unwrap được |
| SR-KEK-03 | Wrap/unwrap dùng scheme/provider có confidentiality và integrity phù hợp, format/tham số được chốt | Cấu hình, test vector và ca wrapped blob bị sửa |
| SR-KEK-04 | Key selection giới hạn theo registry và expected tenant/purpose; không lấy metadata làm authority | Ca key reference lạ, sai môi trường và sai tenant |
| SR-KEK-05 | Binding metadata/context và data AEAD bảo vệ đúng tài nguyên theo thiết kế | Ca tráo wrapped DEK/envelope giữa report/tenant |
| SR-KEK-06 | Quyền wrap, unwrap, rewrap, policy và destroy được cấp tối thiểu theo operation | Ma trận IAM và ca worker/actor trái scope |
| SR-KEK-07 | Rotation, rewrap và rotate DEK có gate/kết quả riêng; không công bố một việc như đã hoàn thành việc khác | Hồ sơ thay đổi và đối soát envelope/data thực tế |
| SR-KEK-08 | Migration giữ nhất quán reference/blob/context và kiểm soát đồng thời | Ca partial failure, retry và CAS/transaction |
| SR-KEK-09 | Compromise response đánh giá raw material, quyền dùng và bản sao lịch sử; không coi rewrap là thu hồi mọi DEK đã lộ | Diễn tập sự cố và quyết định re-key phù hợp |
| SR-KEK-10 | Revocation objective xét cả cache DEK, worker và cửa sổ hiệu lực | Ca cache đang có DEK khi quyền KEK thay đổi |
| SR-KEK-11 | Backup/restore và gate hủy KEK đối soát dependency dữ liệu còn tồn tại | Ca restore lịch sử và kiểm tra key còn phụ thuộc |
| SR-KEK-12 | Lỗi provider/context/profile không dẫn tới raw key, downgrade hoặc bỏ xác thực | Fault injection có kiểm soát và đọc lại trạng thái |
| SR-KEK-13 | Telemetry đủ liên kết operation/key version/context đã giảm dữ liệu, không có key material | Kiểm tra log, provider audit và capture middleware |

Các yêu cầu phải gắn với profile thật. Nếu dùng AES-KW primitive không có context, SR-KEK-05 phải nêu rõ lớp binding/authorization còn lại; không để một field `context` trong JSON trở thành bằng chứng có AAD.

Các mục tiêu cryptoperiod, cache TTL, cửa sổ thu hồi và thời hạn migration phải được owner rủi ro/vận hành chốt. Những từ “rotate thường xuyên” hoặc “xóa khóa cũ sớm” chưa tạo tiêu chí đủ an toàn khi dữ liệu lịch sử còn phụ thuộc.

## 14. Thiết kế bằng chứng kiểm chứng

Phần này mô tả cách xác minh một triển khai sản phẩm; không khẳng định các kiểm thử dưới đây đã được chạy trong bài học.

### 14.1. Ma trận ca kiểm thử

| Ca | Tình huống | Kỳ vọng |
| --- | --- | --- |
| E1 | Actor đúng quyền ghi/đọc report | Wrap/unwrap và data AEAD hoạt động đúng, storage không có raw key |
| E2 | Identity chỉ đọc database/backup | Không tự sử dụng KEK hoặc mở plaintext DEK |
| E3 | Sửa byte wrapped DEK hoặc dùng KEK sai | Unwrap/integrity thất bại, không fallback |
| E4 | Tráo envelope tenant A sang tenant B | Bị chặn bởi policy/context/binding tương ứng |
| E5 | Thay key reference thành resource ngoài registry | Không gọi resource tùy ý hoặc mở rộng scope |
| E6 | Bỏ hoặc thay context khi API yêu cầu | Không được unwrap bằng một lần thử không context |
| E7 | Rewrap v6→v7 nhưng giữ DEK theo kế hoạch | Data ciphertext vẫn đọc đúng; metadata và wrapped result khớp đích |
| E8 | Provider thành công nhưng envelope commit lỗi | Không báo bản ghi đã migrate; retry/reconcile đúng |
| E9 | Ghi đồng thời trong lúc migration | Không ghi đè envelope mới bằng kết quả dựa trên revision cũ |
| E10 | Tắt quyền KEK khi process còn cache DEK | Kết quả đúng cửa sổ thu hồi/cache policy, không hứa hiệu lực tức thời sai |
| E11 | Backup cũ còn wrapped DEK dưới KEK lịch sử | Chưa hủy dependency cho tới khi đủ gate hoặc xử lý retention |
| E12 | KMS/provider unavailable hoặc quota deny | Không lưu raw DEK/KEK và không dùng key fallback |

Với ví dụ Java, có thể kiểm tra wrap/unwrap đúng cặp key, wrapped result sai độ dài, byte bị sửa và KEK không phù hợp. Các ca đó kiểm tra primitive/profile của helper, không thay các ca authorization/context của dịch vụ thực tế.

### 14.2. Chứng minh ranh giới quyền, không chỉ round-trip

Một phép wrap rồi unwrap bằng cùng KEK chỉ là happy path. Cần thử identity không có quyền unwrap, key thuộc scope khác và metadata bị tráo để kiểm tra mục tiêu của hierarchy.

Nếu data layer có AAD, phải quan sát đúng nguyên nhân và gate khi tráo report. Không công bố “wrap đã ràng buộc tenant” khi chỉ có data AEAD phát hiện lỗi; có thể hệ thống vẫn đạt mục tiêu tổng thể nhưng bằng chứng phải mô tả đúng lớp bảo vệ.

Tương tự, nếu provider từ chối theo IAM/context thì ghi rõ. Những cơ chế độc lập có thể bổ sung nhau, nhưng một lỗi chung không chứng minh tất cả đều được cấu hình đúng.

### 14.3. Đối soát migration bằng trạng thái lưu trữ

Sau batch rewrap, kiểm tra số envelope còn source version, số đã tới destination, bản thất bại và các data snapshot còn phụ thuộc. Không chỉ đếm số lần gọi API hoặc số message đã xử lý.

Kiểm tra data ciphertext/DEK có thay theo đúng kế hoạch hay không. Với rewrap giữ DEK, không tuyên bố đã khắc phục DEK compromise. Với rotate DEK thực sự, phải chứng minh dữ liệu được mã hóa lại và các thao tác/metadata không bị lệch.

### 14.4. Test lỗi phải kiểm tra không có secret bị rò

Dùng dữ liệu/khóa thử trong môi trường được phép để kiểm tra log, trace, queue tạm và error handling. Không đưa key production ra file hoặc console chỉ để so sánh.

Nếu một API trả plaintext DEK, middleware phải giảm dữ liệu trước khi ghi trace. Khi unwrap lỗi, response ngoài không được trả lại toàn bộ envelope hoặc chi tiết key material để “dễ debug”.

### 14.5. Cache và restore cần diễn tập riêng

Ca thu hồi phải kiểm tra workload đang chạy, không chỉ một instance mới chưa có cache. Ca restore cần đối chiếu trạng thái key hiện tại và kiểm tra historical decrypt-only nếu đó là mục tiêu.

Nếu scheme dữ liệu phụ thuộc nonce/counter có thể rollback, việc phục hồi KEK/DEK không tự chứng minh an toàn để ghi tiếp. Gate new write phải có kế hoạch uniqueness hoặc key/state mới theo profile.

## 15. Những giả định cần loại bỏ

**“KEK là một DEK lớn hơn.”** Vai trò và quyền dùng khác nhau. KEK bảo vệ key material; dữ liệu nghiệp vụ có lớp bảo vệ riêng.

**“Có wrapped DEK trong database là bí mật đã được tách quyền.”** Cần chứng minh bên đọc database không có hoặc không thể tự lấy quyền unwrap/raw KEK.

**“Mọi key wrap tự có AAD cho tenant.”** Phải kiểm tra scheme/API. Metadata đặt cạnh blob không tự được xác thực.

**“Đổi alias nghĩa là dữ liệu cũ dùng khóa mới.”** Alias ảnh hưởng việc chọn key cho những operation tương ứng, không tự migrate mọi envelope.

**“Rewrap khắc phục DEK đã bị lộ.”** Nếu giữ nguyên DEK, material đã bị lấy vẫn là material đó. Cần đánh giá re-key và bản sao dữ liệu liên quan.

**“Disable KEK làm mọi process quên DEK ngay.”** Raw key/cache đã cấp ra có thể còn sử dụng được trong giới hạn của kiến trúc.

**“KMS giữ KEK nên không cần kiểm tra quyền report.”** KMS policy không tự thay authorization actor–tenant–object của ứng dụng.

**“Không thấy traffic KEK cũ thì có thể xóa.”** Archive hoặc backup ít truy cập vẫn có thể cần key version đó trong nhiều năm theo policy dữ liệu.

## 16. Bài tập vận dụng

Một nền tảng dùng KEK chung cho mọi tenant, lưu alias `current` cạnh wrapped DEK và cho migration worker quyền decrypt/reencrypt mọi key. Đội phát triển vừa đổi alias rồi công bố đã rotate toàn bộ khóa dữ liệu. Workload đọc còn cache plaintext DEK trong nhiều giờ.

Hãy đề xuất thiết kế thay thế:

1. Xác định hierarchy và granularity phù hợp cùng phạm vi ảnh hưởng của từng KEK.
2. Chốt envelope, logical version và expected context; chỉ ra nguồn nào có thẩm quyền khi đọc.
3. Tách quyền wrap, unwrap và rewrap nguồn–đích, không cấp worker một crypto oracle tổng quát.
4. Phân biệt đổi alias, rewrap và rotate DEK; viết gate coverage/commit cho kế hoạch được chọn.
5. Đặc tả cửa sổ thu hồi có xét cache và các bản backup cũ.
6. Viết ba ca nghiệm thu chứng minh đúng tenant, không fallback raw key và không xóa KEK còn dependency.

Kết quả cần cho thấy lớp bảo vệ khóa làm giảm rủi ro nào và được thực thi ở đâu. KEK có giá trị khi hierarchy, quyền wrap/unwrap, binding dữ liệu và vòng đời được quản lý như một hợp đồng thống nhất, không chỉ như thêm một key vào cấu hình.
