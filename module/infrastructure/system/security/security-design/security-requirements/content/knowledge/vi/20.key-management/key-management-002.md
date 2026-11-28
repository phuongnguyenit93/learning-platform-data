# Key generation

## 1. Sinh khóa là thiết lập một gốc tin cậy

Key generation là quá trình tạo key material đáp ứng yêu cầu của thuật toán, mục đích sử dụng và ranh giới bảo vệ. Nó không chỉ là lấy một chuỗi có đủ độ dài rồi đặt tên là khóa.

Nếu một khóa AES có 256 bit nhưng được tạo từ timestamp hoặc một seed có thể đoán, độ dài biểu diễn không làm nó khó đoán tương ứng. Nếu private key được tạo đúng nhưng xuất hiện trong log provisioning, quy trình sinh khóa cũng chưa đạt mục tiêu bảo mật. Nếu khóa sinh trong môi trường dev được dùng lại ở production, ranh giới môi trường đã bị mất ngay từ đầu.

Trong module yêu cầu bảo mật, một yêu cầu sinh khóa cần trả lời: khóa phục vụ việc gì, ai được yêu cầu tạo, profile nào được phép, nguồn ngẫu nhiên nào được dùng, key material xuất hiện ở đâu và điều kiện nào cho phép chuyển sang sử dụng.

NIST SP 800-133 Rev. 2 cung cấp khuyến nghị về cryptographic key generation. Việc chọn cơ chế cần nằm trong thiết kế mật mã và quản lý khóa của hệ thống, thay vì một helper tạo chuỗi tùy ý. [NIST: Recommendation for Cryptographic Key Generation](https://csrc.nist.gov/pubs/sp/800/133/r2/final).

Bài học dùng tình huống nền tảng học tập có dữ liệu báo cáo cần mã hóa và chứng chỉ cần ký. Các profile, metadata và giới hạn trong ví dụ là lựa chọn minh họa, không phải bằng chứng hệ thống thực tế đã tạo hoặc kích hoạt khóa.

## 2. Phân biệt vật liệu khóa với định danh và tham số

| Thành phần | Ví dụ vai trò | Điều không được nhầm |
| --- | --- | --- |
| Secret key đối xứng | Mã hóa dữ liệu hoặc tạo MAC theo profile | Không dùng một khóa cho mọi mục đích chỉ vì cùng số byte |
| Private key | Ký hoặc thực hiện thao tác của scheme bất đối xứng | Không phải một chuỗi tùy ý có thể thay bằng hash của password |
| Public key | Xác minh hoặc tham gia scheme tương ứng | Cần liên kết đáng tin với owner/purpose, không cần giữ bí mật như private key |
| Key ID/reference | Tìm key trong registry/provider | Không phải key material và không cấp quyền dùng key |
| Alias | Trỏ tới một key version theo policy | Đổi alias không đồng nghĩa đã sinh lại hoặc rotate dữ liệu |
| Nonce/IV | Tham số cho một phép mã hóa/giao thức | Có điều kiện riêng theo scheme; không thay key |
| Salt | Tham số cho một cơ chế dẫn xuất/password hashing | Không tự thêm entropy bí mật cho một password dễ đoán |

Một UUID có thể phù hợp làm request ID hoặc key ID, nhưng không vì vậy trở thành cách sinh khóa AES-256. Hash một định danh để được 32 byte cũng không biến nó thành key material có nguồn entropy phù hợp.

Đối với bất đối xứng, public key và private key có quan hệ toán học theo thuật toán. Dùng bộ sinh cặp khóa của scheme đã được duyệt; không tự tạo hai mảng byte rồi coi đó là một key pair.

## 3. Độ dài khóa không đồng nghĩa entropy

Entropy liên quan đến mức khó đoán của nguồn tạo giá trị. Với key generation, điều quan trọng là đối thủ không thể thu hẹp khóa về một tập ứng viên nhỏ do seed, quy trình hoặc trạng thái hệ thống bị đoán được.

Giả sử một quy trình chỉ chọn từ một tập seed nhỏ rồi băm seed thành chuỗi dài 256 bit. Kẻ biết quy trình có thể thử tập seed ban đầu; số bit output không tạo thêm lượng bí mật độc lập tương ứng. Đây là lý do không tạo khóa bằng các cách như:

```text
SHA-256(thời gian hiện tại)
SHA-256(tenantId + tên service)
password.getBytes() rồi cắt hoặc đệm thành 32 byte
Random với seed cố định hoặc dự đoán được
```

Các dòng trên là mẫu thiết kế cần tránh, không phải phương án dự phòng khi hệ thống thiếu entropy.

Độ mạnh thực tế còn phụ thuộc thuật toán, tham số, provider, việc giữ bí mật và giới hạn sử dụng. Không so độ an toàn của mọi loại khóa chỉ bằng độ dài byte: một key pair đường cong và một khóa RSA không có cùng thang đo kích thước.

Yêu cầu phải chốt profile theo loại khóa, thay vì một quy tắc chung “mọi khóa ít nhất N ký tự”. Ký tự Base64, số byte raw và mức security strength là các khái niệm khác nhau.

## 4. CSPRNG và nguồn entropy phải thuộc nền tảng được kiểm soát

CSPRNG là bộ sinh số giả ngẫu nhiên phù hợp mục tiêu mật mã. Một implementation có thể sử dụng thuật toán xác định bên trong nhưng được khởi tạo và quản lý với nguồn entropy phù hợp để output không thể dự đoán trong mô hình đe dọa.

Một luồng khái niệm:

```text
Nguồn entropy và cơ chế của hệ điều hành/provider
→ khởi tạo/reseed bộ sinh theo thiết kế
→ primitive tạo khóa theo thuật toán và tham số
→ key material trong ranh giới đã chọn
```

NIST SP 800-90A mô tả các DRBG; SP 800-90C mô tả các cấu trúc RBG kết hợp những thành phần liên quan. Không đồng nhất việc gọi một hàm PRNG bất kỳ với một hệ thống sinh bit cho mật mã đã được quản lý. [NIST SP 800-90A Rev. 1](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final), [NIST SP 800-90C](https://csrc.nist.gov/pubs/sp/800/90/c/final).

### 4.1. Trong Java, dùng API đúng mục đích

`SecureRandom` là API Java dành cho random mật mã; provider cụ thể có cơ chế khởi tạo và nguồn entropy tương ứng. Các seed do ứng dụng cung cấp phải không thể dự đoán theo yêu cầu của API. Không tự dùng thời gian, PID, tenant ID hoặc request ID làm nguồn seed bí mật. [Oracle Java 17: SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html).

`Random`, `ThreadLocalRandom`, `SplittableRandom` hoặc một RNG dùng để mô phỏng/tối ưu tải không trở thành CSPRNG chỉ vì cho output trông phân bố tốt.

Không thêm một lời gọi `setSeed` với timestamp rồi cho rằng đã tăng bảo mật. Semantics bổ sung seed và khởi tạo phụ thuộc API/provider; điều đúng cần giữ là ứng dụng không thay quá trình lấy entropy thích hợp bằng một giá trị dự đoán được.

### 4.2. Không dùng một tiêu chí hiệu năng thay cho profile an toàn

Một số nguồn entropy hoặc thao tác provider có thể chờ trong những điều kiện nhất định. Cần kiểm tra startup, tải đồng thời và hành vi lỗi trên môi trường thật, thay vì chuyển sang RNG yếu để giảm latency.

`getInstanceStrong()` không phải một phép chứng minh độc lập rằng mọi yêu cầu sinh khóa đã đạt, và cũng không tự đáp ứng mọi latency target. Dự án phải chọn provider/profile được hỗ trợ, hiểu hành vi của nó và có kế hoạch khi nguồn cần thiết không sẵn có.

### 4.3. Xét clone, snapshot, fork và phục hồi

Nếu môi trường sao chép trạng thái bộ sinh, có thể xuất hiện các điều kiện khiến hai instance bắt đầu từ trạng thái liên quan. Khả năng cụ thể phụ thuộc runtime, OS, provider và cơ chế reseed; không nên mặc định mọi nền tảng đều đã xử lý giống nhau.

Inventory môi trường cần bao gồm container, VM snapshot, restore, process fork hoặc image có trạng thái đã được khởi tạo nếu kiến trúc sử dụng chúng. Không đóng gói key material hoặc trạng thái bí mật của RNG vào golden image để mọi node dùng chung.

Một kiểm tra nhiều khóa không trùng chỉ là tín hiệu trong sample. Bằng chứng chính vẫn là nguồn entropy, construction/provider, cách vận hành và những điều kiện sao chép trạng thái thực tế.

## 5. Profile sinh khóa phải gắn với mục đích

Trong tình huống nền tảng học tập, có thể chọn các profile minh họa sau:

| Profile | Mục đích | Tham số và ranh giới cần chốt |
| --- | --- | --- |
| Report data key | Bảo vệ nội dung báo cáo | Ví dụ AES-256; DEK có thể tồn tại trong process theo policy envelope encryption |
| Report wrapping key | Bảo vệ DEK | KEK được sinh/quản lý trong KMS/HSM theo ranh giới đã duyệt |
| Certificate signing key | Ký chứng chỉ khóa học | Ví dụ Ed25519 trong môi trường/provider đáp ứng yêu cầu; private key có policy không xuất nếu cần |
| Integration MAC key | Xác thực thông điệp của một tích hợp | Ví dụ HMAC-SHA-256 với secret key 256 bit, scope tích hợp riêng |

Đây không phải bảng lựa chọn bắt buộc cho mọi dự án. Nếu môi trường có profile giao thức, provider hoặc điều kiện chứng nhận riêng, cần sử dụng đúng lựa chọn đã được duyệt. Việc thuật toán có tên chuẩn không tự chứng minh mọi module/provider đang dùng đáp ứng yêu cầu đó.

### 5.1. Tách mục đích và môi trường từ thời điểm tạo

Không sinh một master secret rồi chép cùng byte đó cho encryption, signing, MAC, dev và production. Các mục đích có quyền, cơ chế và vòng đời khác nhau.

Một key có owner, môi trường và purpose rõ giúp giới hạn hậu quả khi bị lộ. Nếu dùng một chiến lược dẫn xuất từ root key thay vì sinh độc lập từng key, phải có KDF, domain separation và policy riêng; không dùng lại trực tiếp root material cho mọi thao tác.

### 5.2. Không để request tự chọn crypto profile tùy ý

Một API provisioning nên nhận ý định được cấp như “tạo signing key cho bên phát hành này”, rồi server ánh xạ sang profile cho phép. Không nhận một object mở chứa tùy ý algorithm, curve, key length, provider, export flag và key URL để truyền thẳng xuống hạ tầng.

Những tham số thực sự cần cho người quản trị lựa chọn phải có allowlist và quyền tương ứng. Không cho một workload chỉ được cấp DEK tạo thêm signing key production hoặc yêu cầu xuất private key.

## 6. Ví dụ Java: sinh khóa bằng primitive của thuật toán

Ví dụ Java 17 sau minh họa software key generation. Nó không lưu key, không xuất byte ra console/file và không thay một dịch vụ KMS/HSM nếu yêu cầu đặt key material trong ranh giới đó.

```java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.NamedParameterSpec;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class KeyGenerationExamples {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static SecretKey newReportDataKey() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    public static SecretKey newIntegrationMacKey()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    public static KeyPair newCertificateSigningPair()
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        generator.initialize(NamedParameterSpec.ED25519, RANDOM);
        return generator.generateKeyPair();
    }

    private KeyGenerationExamples() {}
}
```

`KeyGenerator` tạo secret key của thuật toán; việc initialize rõ kích thước và nguồn random tránh phụ thuộc không chủ đích vào default của provider. `KeyPairGenerator` tạo cặp public/private key với tham số tương ứng. [Oracle: KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html), [Oracle: KeyPairGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html), [Oracle: NamedParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/NamedParameterSpec.html).

Các tên và tham số ở ví dụ là profile cố định của ứng dụng. Nếu runtime/provider không hỗ trợ profile, lớp tích hợp phải báo lỗi provisioning theo contract; không tự đổi thuật toán hoặc giảm kích thước để vẫn trả thành công.

Public method trả một `SecretKey` hay `KeyPair` không tự bảo đảm non-exportable. Trong software provider, key material có thể hiện diện trong heap. Chỉ dùng mô hình này khi ranh giới đó đáp ứng mục tiêu của use case.

Ví dụ không có quyền gọi từ mọi request. Một service thực tế phải kiểm tra actor/workload, tenant/purpose và quy trình provisioning trước khi gọi đường sinh khóa, rồi bảo vệ kết quả trước khi kích hoạt.

Không dùng `getEncoded()`, serialization object hoặc `toString()` như một bước log “để kiểm tra khóa sinh được”. Nếu một format xuất khóa thực sự cần thiết, nó là một thao tác có policy xuất và kênh bảo vệ riêng.

## 7. Chọn đúng ranh giới sinh khóa: JVM, KMS hay HSM

Hai yêu cầu sau khác nhau:

```text
A. Khóa được tạo bằng CSPRNG phù hợp trong process ứng dụng,
   sau đó được wrap và lưu theo policy.

B. Private key được tạo bên trong boundary phần cứng/dịch vụ,
   không được xuất plaintext và ứng dụng chỉ nhận key handle/public key.
```

Nếu mục tiêu là B, việc sinh key trong JVM rồi import vào HSM không làm cho quá trình sinh ban đầu trở thành “key material chưa từng ra ngoài HSM”. Key origin và lịch sử xuất/import phải được mô tả đúng.

### 7.1. Không phải mọi API KMS đều giữ key ngoài process

Một số API tạo data key chủ động trả plaintext DEK để ứng dụng mã hóa dữ liệu, đồng thời trả bản wrapped của DEK. Chẳng hạn tài liệu AWS KMS mô tả `GenerateDataKey` theo mô hình đó. Đây là khác biệt về ranh giới API, không phải khẳng định API nào có tên KMS cũng trả một handle không xuất. [AWS KMS: Generate data keys](https://docs.aws.amazon.com/kms/latest/developerguide/data-keys.html).

Nếu dùng plaintext DEK, phải giới hạn thời gian tồn tại, bản sao, log, cache và crash dump theo policy. Wrapped DEK có thể lưu cùng ciphertext theo thiết kế envelope encryption; KEK và quyền unwrap phải nằm ngoài quyền đọc storage đơn thuần.

### 7.2. Không nhầm quyền tạo key với quyền dùng hoặc xuất key

Một identity được phép provisioning có thể không cần decrypt/sign dữ liệu nghiệp vụ. Một workload được phép dùng key hiện có có thể không cần quyền tạo, import, đổi policy hoặc xóa key.

Ma trận quyền phải tách các thao tác này theo hệ thống cụ thể. Gọi được API tạo key không chứng minh key tạo ra đã có policy đúng, đúng tenant hoặc đã sẵn sàng sử dụng.

## 8. Generation, derivation, agreement và import là các nguồn khác nhau

| Nguồn key material | Ý nghĩa | Yêu cầu riêng |
| --- | --- | --- |
| Generation mới | Tạo material bằng cơ chế đã duyệt | Entropy, thuật toán, boundary và ownership |
| Derivation | Tạo key từ secret đầu vào bằng KDF | Chất lượng root, salt/context, domain separation và scope |
| Key agreement | Hai bên thiết lập secret qua giao thức | Xác thực bên kia, tham số, KDF và transcript/context theo giao thức |
| Import | Đưa material có từ trước vào provider | Nguồn gốc, kênh vận chuyển, kiểm tra và policy export/import |
| Restore | Phục hồi material/key state từ backup | Tính toàn vẹn, quyền khôi phục và tác động tới trạng thái sử dụng |

HKDF là một KDF extract-and-expand cho những thiết kế thích hợp; nó không tạo thêm entropy độc lập chỉ nhờ output dài hơn và không thay password hashing khi đầu vào là password dễ đoán. Context của KDF giúp tách mục đích khi được đặc tả và sử dụng đúng. [RFC 5869: HKDF](https://www.rfc-editor.org/rfc/rfc5869.html).

Không cần tạo một thuật toán dẫn xuất riêng chỉ để mỗi tenant có một chuỗi khác nhau. Nếu chọn derived keys, thiết kế phải chốt root scope, label/context không mơ hồ, crypto profile, rotation và hậu quả khi root bị lộ.

Key agreement trong TLS hoặc giao thức khác nên do implementation giao thức đảm nhiệm. Việc ứng dụng tự generate một key pair không tự tạo được một kênh xác thực an toàn giữa hai bên.

## 9. Tạo thành công chưa có nghĩa được phép kích hoạt

Một quy trình cho managed key dài hạn có thể tách các trạng thái:

```text
Yêu cầu được cấp quyền
→ sinh material trong boundary đúng
→ gắn metadata và policy
→ kiểm tra capability/consistency
→ ghi nhận bằng chứng provisioning
→ kích hoạt cho mục đích đã chốt
```

Nếu provider đã tạo key nhưng bước gắn policy hoặc registry thất bại, key không được mặc định xuất hiện như một key active của ứng dụng. Cần trạng thái pending/failed rõ và tác vụ đối soát thuộc control plane được phân quyền.

### 9.1. Metadata phải mô tả đúng nguồn gốc

Đối với managed signing key của tình huống, registry có thể ghi:

| Metadata | Ý nghĩa cần giữ |
| --- | --- |
| `keyId` và version | Định danh ổn định trong namespace đã được kiểm soát |
| `purpose` | Chỉ dùng cho cấp chứng chỉ của bên phát hành được chỉ định |
| `environment`/owner | Môi trường và đơn vị chịu trách nhiệm |
| `profileRevision` | Algorithm/parameter/provider policy nào đã được duyệt |
| `origin` | Generated trong boundary, imported, derived hoặc restored |
| `providerReference` | Handle được tạo/đối soát từ provider tin cậy |
| `exportPolicy` | Yêu cầu xuất hoặc không xuất và capability đã kiểm tra |
| `state` | Pending, active hoặc trạng thái điều khiển tương ứng |
| `generationOperation` | Liên kết yêu cầu tạo, actor/workload và bằng chứng |

Metadata ghi `NON_EXPORTABLE` không tự thực thi thuộc tính đó. Nếu yêu cầu cần provider ngăn xuất, phải kiểm tra capability/policy thật; một nhãn ở database không ngăn process đã giữ raw key bytes sao chép chúng.

Registry phải giữ integrity cho mối liên hệ key–owner–purpose. Không cho một request thay provider reference của tenant A thành key tenant B rồi chỉ dựa vào việc handle đó tồn tại.

### 9.2. Validation không phải tự viết lại toán học mật mã

Kiểm tra profile thực tế, algorithm/parameter và khả năng dùng key theo API provider. Với key pair, có thể có kiểm tra consistency hoặc self-test phù hợp để xác nhận cặp key thực hiện đúng thao tác; dùng cơ chế được hỗ trợ thay vì tự kiểm tra số học theo một thuật toán mới.

Một phép ký rồi verify thành công chứng minh cặp key khớp cho phép thử đó, không chứng minh entropy tốt hoặc private key chưa từng bị lộ. Bằng chứng phải kết hợp nguồn tạo, boundary, policy quyền và kết quả kiểm tra capability.

Với key không xuất được, không yêu cầu export plaintext chỉ để đo số byte trong bài test. Dùng thông tin provider/attestation/capability được chấp nhận trong profile cùng các thao tác kiểm tra thích hợp.

### 9.3. Kích hoạt và public-key distribution phải khớp nhau

Signing key mới có thể cần public key và metadata được phân phối cho verifier trước hoặc cùng gate kích hoạt theo kế hoạch. Không phát chứng chỉ bằng key mà consumer được hỗ trợ chưa có cách tin cậy để nhận biết.

Với data key/KEK, cần bảo đảm reference và quyền dùng khớp luồng dữ liệu trước khi chuyển write alias. Một key mới được sinh không có nghĩa dữ liệu cũ đã được rotate hoặc mọi reader đã hiểu version mới.

Những gate này áp dụng theo loại khóa. Không bắt mỗi ephemeral key của một phiên TLS phải có quy trình phê duyệt thủ công và registry như một root signing key dài hạn; thư viện giao thức và policy vận hành quản lý lifecycle phù hợp cho ephemeral material.

## 10. Retry, đồng thời và idempotency của provisioning

### 10.1. Timeout có thể xảy ra sau khi provider đã tạo key

Client control plane gửi yêu cầu tạo key, provider thực hiện xong nhưng response bị mất. Một retry mù có thể tạo thêm key khác, để lại orphan hoặc làm alias trỏ tới một kết quả không được dự kiến.

Cần một operation ID và cơ chế idempotency/đối soát được thiết kế theo API provider. Nếu provider không hỗ trợ đúng semantics cần thiết, control plane phải có journal/registry và quy tắc reconcile phù hợp. Không giả định mọi create API đều tự idempotent.

Idempotency ở đây là một yêu cầu logic được giải quyết thành một tài nguyên theo contract. Nó không có nghĩa dùng operation ID làm seed để tái tạo cùng raw key bytes. Biến một request ID công khai thành nguồn sinh khóa làm mất mục tiêu entropy.

### 10.2. Không kích hoạt bằng thứ tự response ngẫu nhiên

Khi hai yêu cầu rotation/provisioning chạy đồng thời, không để response về sau tự trở thành active key chỉ vì nó đến sau. Cần quyền chuyển trạng thái, version/compare-and-set hoặc cơ chế điều phối tương ứng với registry.

Nếu bước sinh thất bại, không đổi alias active sang null hoặc sang một key fallback chưa được duyệt. Khóa active cũ chỉ được tiếp tục dùng nếu còn đáp ứng policy và giới hạn; việc đó phải là trạng thái được ghi nhận, không phải báo “rotation thành công”.

### 10.3. Xử lý orphan theo thẩm quyền

Một key được tạo nhưng chưa gắn đủ registry phải được phát hiện và xử lý theo quy trình. Có thể cần giữ pending để điều tra hoặc dọn theo retention/control plane, nhưng không cho một worker ứng dụng tự xóa key production chỉ vì không nhận được response trước đó.

Trước khi hủy một key có nghi vấn orphan, phải xác minh nguồn gốc, reference và phụ thuộc thật. Việc không thấy trong một bảng cục bộ không chứng minh chưa có dữ liệu hoặc consumer nào sử dụng nó.

## 11. Hành vi lỗi và bootstrap

Một hệ thống cần tạo key phải có cách xác thực workload/control plane trước khi thao tác. Đây là phần bootstrap trust, không được giải quyết bằng việc hard-code một master secret trong artifact rồi dùng nó để bảo vệ mọi secret mới.

Workload identity, quyền provisioning và policy provider cần được quản lý ngoài input nghiệp vụ. Nếu dùng HSM/KMS, cả kết nối, trust và quyền API phải đáp ứng ranh giới đã chốt; không tắt xác minh kênh để “lấy được key trước”.

| Điều kiện lỗi | Hành vi cần giữ |
| --- | --- |
| RNG/provider chưa đáp ứng điều kiện | Chờ hoặc thất bại theo timeout/readiness policy; không chuyển sang random yếu |
| Algorithm/parameter không hỗ trợ | Từ chối provisioning; không hạ độ dài hoặc đổi scheme ngầm |
| Không có quyền tạo trong scope yêu cầu | Từ chối; không thử identity đặc quyền khác ngoài policy |
| Timeout sau create | Đối soát operation trước khi retry/kích hoạt |
| Gắn policy/metadata thất bại | Không công bố key active chưa đủ điều kiện |
| Kiểm tra capability/consistency thất bại | Không sử dụng key như kết quả hợp lệ |
| Audit cần thiết cho gate không ghi được | Giữ trạng thái theo policy provisioning đã chốt, không báo thành công giả |

Availability cần được thiết kế bằng timeout, quota, điều phối và phục hồi, không bằng một khóa mặc định hard-code dùng chung khi create thất bại.

Đối với data key được sinh thường xuyên, cần capacity và giới hạn tốc độ phù hợp. Đối với root/signing key quan trọng, có thể cần quy trình phê duyệt và tách nhiệm vụ chặt hơn. Không áp cùng một ceremony thủ công cho mọi DEK hoặc bỏ ceremony của root chỉ vì workload tạo DEK phải nhanh.

## 12. Audit và bằng chứng mà không xuất vật liệu khóa

Một sự kiện provisioning thành công có thể ghi những trường sau:

```json
{
  "event": "MANAGED_KEY_CREATED",
  "operationRef": "controlled-operation-reference",
  "keyRef": "provider-key-reference",
  "profileRevision": "certificate-signing-profile-1",
  "purpose": "learning-certificate-signing",
  "environment": "production",
  "state": "PENDING_ACTIVATION",
  "actorRef": "authorized-control-plane-identity"
}
```

Đây là ví dụ schema audit, không phải sự kiện được tạo thật trong bài học. Nó không chứa raw key, seed, private parameters hoặc plaintext DEK.

Không log key object, encoded key hay response provider trọn vẹn. Một API trả cả plaintext data key lẫn wrapped key có thể làm lộ material nếu middleware tự capture body để debug.

Nếu cần fingerprint cho public key để đối soát, dùng cách biểu diễn/profile đã chốt cho public material đó. Không tự lấy hash của secret key rồi phát rộng như một định danh tiện lợi; key ID/provider reference thường đủ cho nhu cầu vận hành mà không tạo thêm dữ liệu dẫn xuất từ secret.

Audit còn phải có quyền ghi/đọc, integrity, retention và cách đối soát với registry/provider. Một sự kiện `created` không chứng minh key đã active; các chuyển trạng thái nên được phân biệt rõ để không báo cáo sai tiến độ provisioning.

## 13. Bộ yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-KG-01 | Mỗi loại key có purpose, owner, môi trường, profile và boundary sinh đã được duyệt | Ma trận key use case và profile revision |
| SR-KG-02 | Material mới dùng cơ chế CSPRNG/key generator phù hợp; không lấy seed từ thời gian, ID hoặc cấu hình dự đoán được | Review nguồn RNG, generator và cấu hình runtime |
| SR-KG-03 | Algorithm, parameter và provider do server chọn từ tập cho phép; không có downgrade ngầm | Ca input/profile lạ và provider không hỗ trợ |
| SR-KG-04 | Phân tách key theo mục đích/môi trường hoặc dùng KDF chuẩn với scope đã đặc tả | Kiểm tra registry, derivation context và đường dùng key |
| SR-KG-05 | Nếu yêu cầu non-exportable, material được sinh trong boundary đáp ứng và capability xuất bị kiểm soát | Bằng chứng provider/origin/policy và ca export trái quyền |
| SR-KG-06 | Plaintext key chỉ xuất hiện tại nơi/thời gian policy cho phép, không đi vào log/artifact/image | Kiểm tra provisioning, observability và image/backup |
| SR-KG-07 | Quyền create, use, import, export, activate và destroy được tách theo vai trò | Ma trận IAM và ca actor/workload sai scope |
| SR-KG-08 | Key chỉ được active sau khi metadata, policy và kiểm tra cần thiết hoàn tất | Ca lỗi từng bước và đọc lại registry/provider |
| SR-KG-09 | Retry/timeout tạo key có idempotency hoặc reconcile rõ, không dùng request ID làm seed | Ca mất response, retry và orphan handling |
| SR-KG-10 | Đồng thời và restore không làm mất invariant sinh key của nền tảng | Ca nhiều instance, snapshot/restore theo kiến trúc |
| SR-KG-11 | Key origin và binding key–owner–purpose được ghi đúng, không nhầm imported/restored thành fresh generation | Đối soát metadata và đường provisioning thực tế |
| SR-KG-12 | Lỗi RNG/provider/profile không dẫn tới key fallback yếu hoặc báo thành công giả | Fault injection có kiểm soát và kiểm tra active reference |
| SR-KG-13 | Audit đủ liên kết operation/key/profile/state nhưng không chứa key material/seed | Kiểm tra sự kiện và capture của middleware |
| SR-KG-14 | Signing/public-key distribution hoặc data-key storage được hoàn tất theo gate trước khi dùng | Ca consumer/reader nhận version mới theo kế hoạch |

Với ephemeral key do implementation giao thức quản lý, yêu cầu inventory/audit cần áp dụng ở mức đúng: profile, module và policy giao thức. Không yêu cầu ghi từng session key vào registry dài hạn hay xuất material để chứng minh đã tạo.

Một yêu cầu chỉ ghi “sử dụng SecureRandom” chưa đủ để chốt SR-KG-01, 05 hoặc 08. Cùng API có thể được dùng trong boundary sai, khóa bị xuất sau tạo hoặc activation trước khi policy được gắn.

## 14. Thiết kế bằng chứng kiểm chứng

Phần này mô tả cách xác minh một triển khai sản phẩm; không khẳng định các kiểm thử dưới đây đã được thực thi trong bài học.

### 14.1. Ma trận ca kiểm thử

| Ca | Điều kiện/hành động | Kỳ vọng |
| --- | --- | --- |
| G1 | Actor đúng scope tạo key theo profile được duyệt | Nhận reference/kết quả đúng boundary và state |
| G2 | Actor sai tenant/môi trường/purpose | Bị từ chối trước khi có quyền tạo hoặc kích hoạt tương ứng |
| G3 | Yêu cầu algorithm, curve, độ dài hoặc export flag ngoài tập | Từ chối; không truyền tùy ý xuống provider |
| G4 | Runtime không hỗ trợ profile | Lỗi rõ, không đổi scheme hoặc giảm độ dài |
| G5 | Tạo key pair và kiểm tra capability phù hợp | Đúng loại/parameter; consistency đạt nhưng không suy thành chứng minh entropy |
| G6 | Yêu cầu export private key trái policy | Provider/boundary thực thi từ chối theo contract |
| G7 | Provider tạo xong nhưng response bị mất | Retry/reconcile không kích hoạt nhầm key hoặc báo hai operation thành một |
| G8 | Lỗi gắn policy hoặc metadata sau create | Key không bị công bố active thiếu điều kiện |
| G9 | Hai provisioning/rotation operation đồng thời | Active reference theo luật điều phối, không theo thứ tự response ngẫu nhiên |
| G10 | Nhiều process/node và các chế độ restore hỗ trợ | Không dùng cùng material hoặc trạng thái nguy hiểm do image/seed cố định |
| G11 | RNG/provider unavailable hoặc bị từ chối quyền | Không có default key hoặc RNG yếu được dùng thay |
| G12 | Middleware/trace capture response của data-key API | Không lộ plaintext key hay seed trong kênh quan sát |

Kỳ vọng G10 cần dựa vào cơ chế thực tế của OS/provider, không phải giả định tất cả runtime sẽ clone cùng trạng thái hoặc tất cả đều tự reseed an toàn. Nếu môi trường không hỗ trợ một cách snapshot/fork nhất định, deployment policy phải ngăn hoặc ghi rõ phạm vi đó.

### 14.2. Chứng minh đúng boundary mà không kéo key ra ngoài

Với key non-exportable, kiểm tra key origin, capability và quyền bằng API/attestation/thông tin provider được profile chấp nhận. Một ca export bị từ chối có giá trị nhưng vẫn cần đối chiếu rằng key đã được sinh ở boundary đúng, không phải được import sau khi đã tồn tại plaintext ở nơi khác.

Với software-generated DEK được wrap, kiểm tra dữ liệu raw chỉ đi qua đường được phép và không lưu nhầm cùng wrapped DEK. Không thêm một thao tác ghi key ra file chỉ để “dễ nhìn” trong test report.

### 14.3. Randomness test không thay đánh giá nguồn tạo

Một PRNG có seed cố định vẫn có thể cho output trông ngẫu nhiên và vượt nhiều kiểm tra thống kê đơn giản. Vì vậy không chốt PASS chỉ bằng histogram, tỷ lệ bit hoặc không trùng trong vài nghìn mẫu.

Bằng chứng cần kết hợp implementation/provider được dùng, nguồn entropy, tham số, cấu hình runtime và các điều kiện lifecycle. Test vector hoặc self-test của primitive hỗ trợ kiểm tra tính đúng, nhưng không tự chứng minh key material được giữ bí mật trong toàn bộ quy trình.

### 14.4. Phải kiểm tra trạng thái sau lỗi

Sau một timeout hoặc lỗi activation, đọc lại registry và provider bằng quyền kiểm thử được phép. Xác định key nào đã tồn tại, state nào đang có, alias nào active và operation nào còn pending. Một HTTP error không chứng minh provider chưa tạo gì.

Tương tự, một response thành công từ create không chứng minh key đã có đúng owner và quyền sử dụng. Gate cuối cần đối soát các thuộc tính đã cam kết trước khi cho workload dùng.

## 15. Những giả định cần loại bỏ

**“Đủ 32 byte là khóa AES-256 tốt.”** Phải có nguồn entropy và generator phù hợp; padding hoặc hash một giá trị dễ đoán không tạo thêm bí mật tương ứng.

**“Mỗi tenant một UUID nên đã có mỗi tenant một secret.”** Key ID không thay key material và không phải KDF. Giữ chức năng định danh tách khỏi chức năng sinh khóa.

**“Gọi KMS thì key không bao giờ vào heap.”** Phải nhìn đúng operation. Data-key API có thể trả plaintext material theo mục tiêu của nó.

**“Imported vào HSM rồi có thể ghi origin là generated inside.”** Lịch sử tạo và xuất key không được thay bằng nơi key đang được lưu.

**“Retry bằng cùng seed sẽ giải quyết idempotency.”** Idempotency điều phối tài nguyên/operation, không được biến ID công khai thành nguồn dự đoán key.

**“Không tìm thấy key trong bảng ứng dụng thì cứ xóa ở provider.”** Có thể là operation chưa reconcile hoặc consumer khác đang dùng. Xử lý orphan phải theo thẩm quyền và kiểm tra phụ thuộc.

**“Kiểm tra sign/verify thành công chứng minh key mạnh.”** Nó kiểm tra một quan hệ chức năng của cặp key, không chứng minh entropy hoặc việc giữ bí mật.

**“Provider lỗi thì dùng khóa dự phòng hard-code cho khỏi gián đoạn.”** Availability không được đạt bằng cách bỏ mục tiêu bảo mật của provisioning.

## 16. Bài tập vận dụng

Một nền tảng đang tạo khóa báo cáo bằng hash của `tenantId + currentTimeMillis`, tạo signing key trong JVM rồi import vào HSM, và tự retry create khi mất response. Đội vận hành log toàn bộ response của provider để đối soát.

Hãy thiết kế quy trình thay thế:

1. Chốt profile và boundary cho DEK báo cáo, KEK và signing key; chỉ rõ trường hợp nào được phép có plaintext trong process.
2. Thay nguồn sinh bằng primitive/provider phù hợp và mô tả các giả định về container/snapshot/restore.
3. Tách quyền create, use, export và activate; định nghĩa metadata nguồn gốc đúng cho từng loại key.
4. Thiết kế retry/idempotency và reconcile mà không tái tạo key từ request ID.
5. Viết gate activation cùng hành vi khi gắn policy, kiểm tra capability hoặc audit thất bại.
6. Đề xuất ba ca nghiệm thu chứng minh đúng boundary, không lộ material và không kích hoạt nhầm key sau timeout.

Kết quả cần cho thấy khóa được tạo đúng cách, đúng nơi và cho đúng mục đích trước khi được dùng. Key generation an toàn là một quy trình có kiểm soát từ nguồn entropy đến quyền kích hoạt, không chỉ một lời gọi trả về chuỗi byte mới.
