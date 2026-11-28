# Key material và key metadata

Trong một hệ thống mã hóa, câu hỏi “khóa đang ở đâu?” chỉ mới giải quyết một nửa vấn đề. Hệ thống còn phải biết **đó là khóa nào, dùng cho mục đích gì, phiên bản nào đang có hiệu lực, ai được phép dùng và khi nào phải ngừng dùng**. Phần bí mật hoặc giá trị mật mã thật sự được gọi là **key material**; phần thông tin mô tả và điều khiển việc quản lý khóa được gọi là **key metadata**.

Đây là hai khái niệm nền tảng của **key management**. Hiểu ranh giới giữa chúng giúp thiết kế đúng quy trình tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy khóa; đồng thời liên kết mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Nhận diện key material, kể cả khi vật liệu khóa được mã hóa hoặc chỉ được tham chiếu qua KMS/HSM.
2. Phân loại key metadata và phân biệt metadata của **khóa** với metadata của **một lần mã hóa**.
3. Mô tả cách khóa và metadata phối hợp trong mã hóa dữ liệu, chữ ký số, xoay vòng và thu hồi.
4. Thiết kế cấu trúc lưu trữ và kiểm soát truy cập hạn chế rò rỉ khóa, chọn nhầm phiên bản khóa hoặc bị sửa metadata.

## 2. Key material là gì?

**Key material** là các giá trị mật mã được dùng trực tiếp, hoặc được dùng để tạo ra, một khóa phục vụ phép toán mật mã. Tùy thuật toán, đó có thể là chuỗi byte của khóa đối xứng, thành phần khóa riêng, thành phần khóa công khai, seed sinh khóa hoặc mảnh khóa trong cơ chế chia sẻ bí mật.

Không phải mọi key material đều cần giữ bí mật:

| Loại | Ví dụ | Yêu cầu bảo vệ chính |
|---|---|---|
| **Khóa đối xứng** | Khóa AES-256 mã hóa dữ liệu (DEK); khóa HMAC | Giữ bí mật, chống thay đổi trái phép, hạn chế số nơi tồn tại bản rõ |
| **Khóa riêng bất đối xứng** | Private key RSA, EC hoặc Ed25519 để giải mã/ký | Giữ bí mật, chống dùng trái phép, ưu tiên thao tác trong KMS/HSM |
| **Khóa công khai** | Public key RSA/EC để mã hóa hoặc kiểm tra chữ ký | Không cần giữ bí mật, nhưng phải xác thực **nguồn gốc và tính toàn vẹn** |
| **Vật liệu tạo khóa** | Seed bí mật, khóa gốc của KDF, key share | Bảo vệ theo mức độ nhạy cảm; việc lộ seed có thể làm lộ nhiều khóa dẫn xuất |
| **Khóa đã được bọc** | DEK được mã hóa dưới KEK (wrapped DEK) | Vẫn là **key material ở dạng được bảo vệ**, không phải “chỉ là metadata” |

Ví dụ, một khóa AES-256 có 256 bit (32 byte) giá trị khóa. Chuỗi tên như **customer-data-key** không phải 32 byte này; nó chỉ là tên/định danh dẫn đến khóa. Tương tự, đường dẫn KMS và ID đối tượng HSM là **tham chiếu** đến vật liệu khóa, không phải vật liệu khóa bản rõ.

### 2.1. DEK, KEK và nguyên tắc phân tách nhiệm vụ

- **Data Encryption Key (DEK):** khóa thực hiện mã hóa/giải mã dữ liệu ứng dụng; thường dùng thuật toán đối xứng như AES-GCM.
- **Key Encryption Key (KEK):** khóa dùng để bảo vệ (wrap/unwrap) DEK hoặc các khóa khác. Nhiều thiết kế để KEK trong KMS/HSM và không xuất bản rõ ra ngoài.
- **Signing key:** khóa riêng dùng tạo chữ ký số; thường có mục đích và chính sách khác với khóa mã hóa.

Không nên dùng một khóa cho nhiều chức năng không liên quan chỉ vì độ dài khóa giống nhau. Chính sách “mỗi khóa một mục đích” làm giảm tác động khi một dịch vụ hoặc khóa bị xâm phạm.

### 2.2. Những thứ dễ bị gọi nhầm là key material

**Salt** dùng cho hàm dẫn xuất khóa thường không bí mật và không tự nó là khóa. **Nonce/IV** là tham số của lần mã hóa, cũng không phải khóa; với AES-GCM, nonce phải **không trùng dưới cùng một khóa**. **Authentication tag** giúp xác minh bản mã, không phải khóa. **Chứng thư số (certificate)** là cấu trúc chứa khóa công khai và thông tin ràng buộc danh tính được ký bởi bên phát hành; khóa riêng tương ứng không nằm trong chứng thư.

Mật khẩu, API token và access token đều là bí mật có thể cần bảo vệ nghiêm ngặt, nhưng không tự động được coi là khóa mật mã theo định nghĩa trên. Tránh áp dụng nhầm quy trình kỹ thuật chỉ vì mọi thứ đều được gọi chung là “secret”.

## 3. Key metadata là gì?

**Key metadata** là thông tin mô tả, định danh, phân loại và điều khiển cách hệ thống quản lý/sử dụng một khóa. Nó không thay thế phép toán mật mã, nhưng quyết định hệ thống có chọn **đúng khóa** và thực thi **đúng chính sách** hay không.

| Nhóm metadata | Trường minh họa | Ý nghĩa |
|---|---|---|
| Định danh | **keyId**, **keyVersion**, alias | Xác định khóa/phiên bản cụ thể; alias có thể trỏ sang phiên bản khác theo thời gian |
| Thuộc tính mật mã | **algorithm**, **keySize**, key type, purpose | Phân biệt AES, RSA, EC; dùng cho mã hóa, MAC, ký hay wrapping |
| Nguồn gốc và lưu trữ | origin, KMS/HSM reference, provider, region, **exportable** | Khóa được tạo/nhập ở đâu; có được xuất vật liệu khóa không |
| Vòng đời | state, createdAt, activatedAt, retiredAt, destroyAfter | Theo dõi khi nào khóa được phép dùng, ngừng dùng hoặc chờ hủy |
| Quyền và trách nhiệm | owner, tenant, policyId, allowed operations | Gắn khóa với chủ sở hữu, phạm vi dữ liệu và quyền truy cập |
| Quản trị/kiểm toán | rotation policy, audit reference, change reason | Hỗ trợ điều tra, xoay vòng và đáp ứng yêu cầu kiểm soát |

Các tên trường là **mô hình minh họa**, không phải schema bắt buộc của mọi KMS. Chẳng hạn, mỗi nhà cung cấp có mô hình version, alias, trạng thái và khóa do nhà cung cấp quản lý khác nhau. Trường **createdAt** không có nghĩa khóa tự động hết hiệu lực nếu chưa có chính sách quy định.

### 3.1. Metadata của khóa và metadata của một lần mã hóa

Hai loại thường xuất hiện cạnh nhau nhưng có phạm vi khác nhau:

| Thuộc khóa/phiên bản khóa | Thuộc bản mã/lần mã hóa |
|---|---|
| keyId, keyVersion, key purpose, lifecycle state | nonce/IV, authentication tag, AAD/context |
| Thuật toán được phép, chính sách IAM/KMS, nguồn gốc khóa | Thuật toán/chế độ đã dùng cho bản mã, định dạng bản mã |
| Quyền sử dụng khóa, thời điểm kích hoạt/hủy | Định danh khóa và phiên bản **đã thực sự dùng** để mã hóa bản ghi |

Ví dụ: **nonce** không phải thuộc tính cố định của một khóa AES; mỗi lần mã hóa GCM cần nonce riêng. Ngược lại, key ID và version liên kết bản mã với một khóa cụ thể. Lưu key ID trong bản ghi không tự chứng minh bản ghi được tạo bởi khóa đó; tính xác thực phải dựa trên kiểm soát truy cập, xác minh mật mã và cơ chế ràng buộc phù hợp.

### 3.2. Metadata không nhất thiết vô hại

Metadata thường không cần giữ bí mật như private key, nhưng vẫn có thể tiết lộ sơ đồ tổ chức, danh tính tenant, tên dịch vụ, vùng lưu trữ, thời điểm triển khai và lịch sử xoay vòng. Hơn nữa, kẻ tấn công có quyền sửa metadata có thể:

- Đổi tham chiếu key ID/version khiến dữ liệu không giải mã được hoặc trỏ đến khóa sai.
- Sửa trạng thái/chính sách để cố dùng khóa đã bị vô hiệu hóa.
- Đổi thuật toán hoặc context ở nơi ứng dụng thiếu kiểm tra, gây lỗi xác minh hoặc mở đường cho hành vi thay thế khóa.
- Xóa dấu vết owner và lịch sử thay đổi, làm suy giảm khả năng kiểm toán.

Vì vậy, metadata cần **kiểm soát quyền đọc/ghi, kiểm tra tính toàn vẹn, quản lý phiên bản và audit**, dù phần lớn trường không phải bí mật mật mã.

## 4. Quan hệ giữa material, metadata và KMS/HSM

Một thiết kế tốt tách **nơi thực thi các phép toán trên khóa** khỏi **nơi ứng dụng lưu định danh, chính sách và bản mã**:

~~~mermaid
flowchart LR
    A["Ứng dụng"] -->|"Gửi key ID và yêu cầu được cấp quyền"| K["KMS/HSM"]
    K -->|"Thực thi bằng KEK/khóa riêng được bảo vệ"| K
    K -->|"Kết quả được phép: wrapped DEK, chữ ký, plaintext DEK nếu API hỗ trợ"| A
    A -->|"Lưu bản mã + dữ liệu cần thiết để giải mã"| D[("Kho dữ liệu")]
    M[("Metadata/policy/audit")] <-->|"Định danh, vòng đời, quyền, sự kiện"| K
    A -->|"Tham chiếu key ID/version"| M
~~~

**KMS (Key Management Service)** cung cấp API quản lý và sử dụng khóa, kiểm soát truy cập, trạng thái và thường tích hợp audit. **HSM (Hardware Security Module)** là ranh giới phần cứng chuyên dụng bảo vệ khóa và thực thi thao tác mật mã theo thiết kế thiết bị. Một KMS có thể dùng HSM ở tầng dưới; chúng không đồng nghĩa và không có nghĩa mọi API đều cho phép xuất khóa bản rõ.

Ví dụ, với một khóa riêng **non-exportable**, ứng dụng gửi dữ liệu cần ký hoặc digest theo API được hỗ trợ rồi nhận chữ ký. Ứng dụng không thấy private key; nó dùng **key ID/handle** để chỉ định đối tượng và cần quyền thực hiện thao tác **Sign**. Public key được phát hành để kiểm tra chữ ký nhưng phải được liên kết đúng danh tính/nguồn phát hành, tránh bị thay thế.

### 4.1. Envelope encryption: đâu là key material, đâu là metadata?

Envelope encryption thường dùng một **DEK** mã hóa dữ liệu và một **KEK** bảo vệ DEK:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant KMS as KMS/KEK
    participant DB as Kho lưu trữ
    App->>KMS: GenerateDataKey(key reference, context)
    KMS-->>App: plaintext DEK + wrapped DEK
    Note over App: Dùng plaintext DEK tạm thời để AES-GCM
    App->>DB: ciphertext + nonce + tag + wrapped DEK + key reference
    Note over App: Giảm thời gian DEK bản rõ tồn tại trong bộ nhớ
    App->>KMS: Decrypt/Unwrap(wrapped DEK, context) khi cần
    KMS-->>App: plaintext DEK nếu được cấp quyền
    App->>DB: Đọc bản mã để giải mã trong ứng dụng
~~~

Phân loại thành phần lưu trong bản ghi:

| Thành phần | Phân loại | Lưu ý |
|---|---|---|
| **plaintext DEK** | Key material bản rõ, **bí mật** | Chỉ tồn tại tạm thời trong nơi xử lý tin cậy; không ghi log, DB hoặc telemetry |
| **wrapped DEK** | Key material đã mã hóa | Có thể lưu cùng bản mã, nhưng vẫn cần kiểm soát truy cập, integrity và KEK an toàn |
| **KEK** | Key material bí mật | Ưu tiên ở KMS/HSM với quyền wrap/unwrap riêng |
| **keyId/keyVersion** | Metadata tham chiếu | Lưu đủ thông tin để tìm lại đúng khóa hoặc đúng phiên bản khi giải mã |
| **nonce, tag, AAD, format version** | Metadata của lần mã hóa hoặc thành phần xác thực | Nonce không cần bí mật, nhưng GCM đòi hỏi tính duy nhất theo khóa; AAD phải trùng khi giải mã |
| **ciphertext** | Dữ liệu đã mã hóa | Không phải key material; bản mã và tag cần được bảo vệ khỏi thay đổi trái phép |

Trong Java/JCA, kết quả **AES/GCM/NoPadding** của **doFinal** thường chứa ciphertext nối với authentication tag. Nếu dùng định dạng này, không lưu thêm một tag giả hoặc giả định tag đã tự được tách thành field.

Ví dụ định dạng lưu trữ mang tính minh họa (các giá trị mã hóa dưới đây là placeholder, **không phải khóa thật**):

~~~json
{
  "formatVersion": 1,
  "keyId": "kms-key/customer-pii",
  "keyVersion": "v3",
  "wrappedDek": "<base64-encrypted-DEK>",
  "algorithm": "AES-256-GCM",
  "nonce": "<base64-of-12-byte-nonce>",
  "ciphertextWithTag": "<base64-ciphertext-and-16-byte-tag>",
  "aadContext": {
    "tenantId": "tenant-42",
    "dataType": "customer-pii"
  }
}
~~~

Ở bản ghi này, **wrappedDek** không được chuyển thành “metadata thường” chỉ vì nó được lưu dưới dạng chuỗi Base64. Base64 chỉ là mã hóa biểu diễn, không phải biện pháp bảo mật. **aadContext** chứa các dữ liệu được xác thực nhưng không mã hóa bởi AEAD; chỉ đặt thông tin không bí mật vào AAD. Cần xác định cách mã hóa byte AAD **nhất quán, không nhập nhằng** giữa lúc encrypt và decrypt, tránh phụ thuộc thứ tự key tùy ý trong JSON.

## 5. Ví dụ Java: vật liệu khóa nằm trong bộ nhớ, metadata đi cùng bản mã

Đoạn mã dùng Java 17+ và thư viện chuẩn để **minh họa ranh giới dữ liệu**, chưa phải trình quản lý khóa cho production. **SecretKey** là key material được truyền vào hàm. **EncryptedPayload** chỉ chứa định danh, phiên bản và các giá trị cần thiết để đọc bản mã.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyMaterialExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_BYTES = 12; // 96-bit nonce
    private static final int TAG_BITS = 128;

    public record EncryptedPayload(
            String keyId,
            String keyVersion,
            String algorithm,
            String nonceBase64,
            String ciphertextWithTagBase64
    ) {}

    public static EncryptedPayload encrypt(
            SecretKey dek, String keyId, String keyVersion,
            byte[] plaintext, String tenantId
    ) throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, dek, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(tenantId.getBytes(StandardCharsets.UTF_8));
        byte[] ciphertextWithTag = cipher.doFinal(plaintext);

        return new EncryptedPayload(
                keyId, keyVersion, "AES-256-GCM",
                Base64.getEncoder().encodeToString(nonce),
                Base64.getEncoder().encodeToString(ciphertextWithTag)
        );
    }

    public static byte[] decrypt(
            SecretKey correctDek, EncryptedPayload payload, String tenantId
    ) throws GeneralSecurityException {
        if (!"AES-256-GCM".equals(payload.algorithm())) {
            throw new GeneralSecurityException("Unsupported algorithm");
        }
        byte[] nonce = Base64.getDecoder().decode(payload.nonceBase64());
        if (nonce.length != NONCE_BYTES) {
            throw new GeneralSecurityException("Invalid nonce length");
        }
        byte[] ciphertextWithTag = Base64.getDecoder()
                .decode(payload.ciphertextWithTagBase64());

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, correctDek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(tenantId.getBytes(StandardCharsets.UTF_8));
        return cipher.doFinal(ciphertextWithTag); // Sai tag/AAD => thất bại
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey exampleDek = generator.generateKey();

        EncryptedPayload stored = encrypt(
                exampleDek, "local-demo-key", "v1",
                "Thông tin cần bảo vệ".getBytes(StandardCharsets.UTF_8),
                "tenant-42");

        byte[] restored = decrypt(exampleDek, stored, "tenant-42");
        System.out.println(new String(restored, StandardCharsets.UTF_8));
        // Không in exampleDek.getEncoded() hay plaintext DEK ra log.
    }
}
~~~

**Điểm cần hiểu khi chuyển sang production:**

1. **keyId** và **keyVersion** trong ví dụ chỉ là nhãn. Hàm **decrypt** nhận sẵn **correctDek**; bản thân chuỗi nhãn **không xác minh** đó là khóa đúng. Trong hệ thống thực, tầng KMS/repository phải ánh xạ và xác thực ID/version theo chính sách.
2. Khóa sinh bằng **KeyGenerator** phù hợp để minh họa Java/JCA. Với envelope encryption thực tế, DEK có thể được KMS sinh và cung cấp cùng **wrapped DEK**, hoặc được tạo trong một thiết kế được kiểm soát tương đương. Không duy trì plaintext DEK vĩnh viễn trong cấu hình ứng dụng.
3. Nonce ngẫu nhiên 96 bit cần **duy nhất trên mỗi lần mã hóa với cùng một DEK**. Khi khối lượng mã hóa lớn, cần phân tích xác suất trùng nonce, giới hạn lượng dữ liệu/operation theo khóa và cân nhắc cơ chế cấp nonce tránh trùng; không dùng bộ đếm tự reset khi nhiều instance dùng chung khóa.
4. **AES-GCM** xác minh tag khi giải mã. Sai khóa, nonce, ciphertext, tag hoặc AAD thường khiến xác minh thất bại; không tự động “thử mọi khóa” hoặc bỏ qua xác minh để lấy plaintext.
5. Ví dụ sử dụng **tenantId** làm AAD để ràng buộc bản mã với tenant. Với nhiều trường AAD, hãy dùng định dạng tuần tự hóa chuẩn hóa và có version, xác định rõ mọi thành phần nào được bảo vệ. Chính sách truy cập tenant vẫn phải được kiểm tra độc lập.

## 6. Metadata giúp điều khiển vòng đời khóa như thế nào?

Một khóa có thể đi qua các trạng thái khái niệm sau; tên và tính hợp lệ của chuyển trạng thái phụ thuộc KMS:

~~~mermaid
stateDiagram-v2
    [*] --> Created: Tạo/nhập vật liệu khóa
    Created --> Active: Kích hoạt theo policy
    Active --> Disabled: Vô hiệu hóa
    Disabled --> Active: Kích hoạt lại nếu được phép
    Active --> Retired: Ngừng dùng cho dữ liệu mới
    Retired --> Disabled: Chặn toàn bộ thao tác
    Disabled --> PendingDeletion: Lên lịch hủy
    PendingDeletion --> Destroyed: Hoàn tất thời gian chờ
    Destroyed --> [*]
~~~

Đây là sơ đồ **khái niệm**, không phải cam kết API của nhà cung cấp. Một số nền tảng không có trạng thái **Retired** riêng; hệ thống có thể thực hiện bằng alias/policy và giữ phiên bản cũ ở quyền **decrypt-only**.

| Sự kiện | Material có thay đổi không? | Metadata/chính sách cần làm gì? |
|---|---|---|
| Tạo khóa | Có, phát sinh material mới | Ghi key ID, thuật toán, mục đích, owner, nơi lưu, trạng thái khởi tạo |
| Kích hoạt | Thường không | Cho phép đúng thao tác và principal, đánh dấu thời điểm hiệu lực |
| Sử dụng | Không nhất thiết | Kiểm tra quyền, trạng thái và mục đích; ghi audit tương ứng |
| Xoay DEK | **Có**, tạo DEK mới | Bản mã mới tham chiếu DEK mới; dữ liệu cũ cần re-encrypt nếu muốn thay khóa thực sự |
| Xoay KEK | **Có**, tạo KEK/version mới | Có thể re-wrap DEK mà không mã hóa lại toàn bộ payload, tùy thiết kế |
| Thu hồi/vô hiệu hóa | Có thể **không** | Chặn các thao tác tương ứng; xem xét tác động đến dữ liệu cũ và bản sao lưu |
| Hủy khóa | Có, material bị hủy/không thể sử dụng | Ghi nhận hủy, bằng chứng audit; dữ liệu cần khóa đó có thể không giải mã lại được |

**Rotation không giống revocation và destruction.** Xoay vòng đưa vật liệu khóa hoặc phiên bản khóa mới vào sử dụng; thu hồi/vô hiệu hóa chặn quyền sử dụng; hủy làm mất khả năng sử dụng material, thường không thể đảo ngược. Chỉ đổi tên alias từ **v2** sang **v3** không tự mã hóa lại dữ liệu đã tạo bằng **v2**.

Ngoài ra, thời gian mã hóa dữ liệu mới bằng khóa cũ có thể ngừng trước thời điểm vô hiệu hóa khả năng giải mã. Đây là lý do metadata cần biểu diễn **quyền sử dụng theo mục đích và trạng thái**, chứ không chỉ một cờ **active=true/false**.

## 7. Hai tình huống cần đặc biệt phân biệt

### 7.1. Ký số: public key cũng là material

Giả sử dịch vụ hóa đơn có signing key phiên bản **sign-7**. Private key ở HSM; dịch vụ ký thông qua API. Public key được công bố để bên nhận kiểm tra chữ ký.

- **Material:** private key, public key.
- **Metadata khóa:** key ID, version, thuật toán ký, mục đích **sign**, trạng thái hiệu lực, owner, tham chiếu HSM.
- **Metadata chữ ký/tài liệu:** key ID dùng để kiểm tra, thuật toán theo định dạng được chấp thuận, chữ ký và thông tin chứng thư nếu có.

Người xác minh phải lấy public key từ nguồn **đáng tin cậy** và kiểm tra sự ràng buộc giữa khóa, tổ chức ký và chính sách; chỉ tin vào một giá trị **kid** lấy từ header không đáng tin cậy có thể dẫn đến **key substitution**. Khi chuyển sang signing key mới, hệ thống thường vẫn cần phương án xác minh chữ ký lịch sử bằng khóa công khai cũ, theo chính sách lưu trữ và thời hạn xác thực.

### 7.2. Multi-tenant: ID, AAD và quyền truy cập phải nhất quán

Giả sử hai tenant dùng hai KEK khác nhau. Hệ thống phải đảm bảo:

- Tenant A chỉ có quyền gọi **GenerateDataKey/Decrypt** đối với tài nguyên khóa được phép cho A.
- Bản mã của A lưu **đúng tham chiếu khóa/phiên bản và wrapped DEK**; không cho request từ B tự do chọn tham chiếu của A.
- Tenant identity và các thông tin nghiệp vụ cần ràng buộc được đưa vào **AAD/encryption context** theo API, sau đó được kiểm tra lại lúc giải mã.
- Quản trị viên chỉ được sửa các field vòng đời/owner/policy theo quyền rõ ràng; thay đổi được audit.

**AAD không thay IAM**, và IAM không thay việc xác thực bản mã. Một kiểm soát bảo vệ quyền gọi dịch vụ; kiểm soát còn lại bảo vệ sự ràng buộc mật mã của dữ liệu.

## 8. Nguy cơ thường gặp và cách phòng vệ

| Lỗi thiết kế | Hậu quả | Kiểm soát ưu tiên |
|---|---|---|
| Lưu raw AES key/private key trong Git, biến môi trường bị lộ, log hoặc DB thông thường | Lộ material, giải mã/ký giả mạo | Sử dụng KMS/HSM/secret store phù hợp; hạn chế export; tuyệt đối không log material |
| Nghĩ rằng Base64 hoặc wrapped DEK là “không cần bảo vệ” | Rò rỉ bản mã khóa và thông tin hỗ trợ tấn công | Phân loại wrapped key là dữ liệu nhạy cảm; bảo vệ KEK, quyền đọc và tính toàn vẹn |
| Chỉ lưu alias hiện tại, không lưu thông tin đủ để tìm lại khóa đã dùng | Không giải mã được bản ghi cũ sau rotation | Lưu tham chiếu phiên bản/định danh đúng theo hợp đồng KMS và wrapped DEK |
| Tái sử dụng nonce AES-GCM với cùng khóa | Phá vỡ bảo đảm bảo mật và xác thực của GCM | Thiết kế nonce duy nhất theo khóa; phân bổ an toàn qua nhiều instance |
| Cho phép thay keyId, algorithm hoặc AAD tùy ý | Lỗi giải mã, chọn nhầm khóa hoặc tấn công thay thế khóa | Validate thuật toán, kiểm soát tham chiếu, ràng buộc AAD và kiểm tra quyền |
| Dùng chung key cho encryption và signing hoặc nhiều tenant không tách quyền | Tăng phạm vi ảnh hưởng khi lộ khóa | Tách khóa theo mục đích/tenant/độ nhạy; nguyên tắc least privilege |
| Hủy KEK trước khi xử lý dữ liệu cũ | Mất khả năng unwrap DEK, gây mất dữ liệu | Lập kế hoạch re-wrap/khôi phục, kiểm thử dữ liệu và backup trước khi hủy |
| Không audit thao tác sử dụng và thay đổi policy | Khó phát hiện sử dụng trái phép, khó truy vết | Log actor, action, resource ID/version, thời gian, kết quả; loại bỏ secret và plaintext |

Lưu ý: “non-exportable” là một đặc tính giúp thu hẹp bề mặt rò rỉ **material**, nhưng không ngăn người được cấp quyền **Sign/Decrypt** lạm dụng khóa. Vì vậy cần kiểm soát quyền sử dụng, hạn mức, phân tách vai trò và theo dõi bất thường, bên cạnh việc giữ khóa trong HSM.

## 9. Checklist khi thiết kế một key registry

Trước khi đưa một kho quản lý khóa vào sử dụng, hãy kiểm tra:

1. **Định nghĩa rõ loại khóa:** symmetric/asymmetric, DEK/KEK/signing, kích thước, thuật toán và mục đích được phép.
2. **Không nhầm tham chiếu với material:** key ID, alias, handle không phải khóa bản rõ; wrapped key vẫn là material đã mã hóa.
3. **Định danh ổn định:** lưu đủ key ID, phiên bản và thông tin wrapping để giải mã/kiểm tra chữ ký lịch sử; xác định ngữ nghĩa alias khi rotation.
4. **Chính sách vòng đời rõ ràng:** ai được tạo, kích hoạt, xoay, vô hiệu hóa, lên lịch hủy; lúc nào khóa cũ còn được decrypt/verify.
5. **Quyền tối thiểu:** tách quản trị chính sách với quyền sử dụng khóa; tách wrap, unwrap, sign, verify nếu dịch vụ cho phép.
6. **Ràng buộc dữ liệu:** bảo đảm nonce duy nhất khi dùng GCM, xác thực AAD/encryption context và kiểm tra key reference ở lớp ứng dụng.
7. **Audit có thể điều tra:** ghi ID tài nguyên, hành động, principal, timestamp, trạng thái thành công/thất bại; không ghi material, plaintext hay secret-bearing context.
8. **Khôi phục và hủy:** nắm rõ backup, thời gian chờ xóa, phạm vi ảnh hưởng của việc hủy KEK và khả năng giải mã dữ liệu tồn lưu.

## 10. Tự kiểm tra bằng một tình huống

Một dịch vụ lưu **ciphertext**, **nonce**, **wrapped DEK**, **keyId** và **keyVersion** trong bảng dữ liệu. Sau sáu tháng, quản trị viên đổi alias KEK sang phiên bản mới; dịch vụ vẫn phải đọc được dữ liệu cũ.

**Phân tích:** ciphertext là dữ liệu đã mã hóa; nonce là tham số lần mã hóa; wrapped DEK là **vật liệu khóa ở dạng được bảo vệ**; keyId và keyVersion là **metadata tham chiếu**. Đổi alias không có nghĩa wrapped DEK cũ được tự động bọc lại. Dịch vụ cần giữ khả năng unwrap bằng đúng KEK cũ hoặc thực hiện **re-wrap** có kiểm soát rồi cập nhật tham chiếu/phiên bản tương ứng. Chỉ sau khi xác minh dữ liệu và đường khôi phục mới nên lên lịch vô hiệu hóa/hủy khóa cũ.

**Điều cần ghi nhớ:** Bảo vệ key material giữ bí mật và năng lực mật mã; quản lý key metadata giúp hệ thống chọn đúng khóa, áp đúng quyền, theo dõi vòng đời và khôi phục dữ liệu. Cả hai đều là thành phần an ninh của hệ thống.
