# 11.5 Envelope encryption và tách khóa dữ liệu khỏi khóa bảo vệ khóa

## Mục tiêu

Bài học thuộc **11. Vòng đời khóa** trong Java Advance – security-cryptography. Sau bài này, bạn có thể:

1. Giải thích **envelope encryption (mã hóa phong bì)** và phân biệt **DEK (Data Encryption Key)** với **KEK (Key Encryption Key)** theo vai trò, nơi lưu, quyền truy cập và vòng đời.
2. Mô tả quy trình **sinh DEK → mã hóa dữ liệu → bọc DEK bằng KEK → lưu envelope → mở bọc DEK → giải mã dữ liệu**; hiểu phần nào được phép lưu công khai và phần nào phải được bảo vệ.
3. Hiểu vì sao **rewrap (bọc lại DEK)** khi thay KEK thường không cần giải mã/mã hóa lại toàn bộ dữ liệu, nhưng **khác** với thay DEK hoặc khắc phục sự cố lộ khóa.
4. Dùng **Java 17+ và AES-GCM** để viết mô phỏng độc lập có key separation, AAD, nonce, kiểm chứng tampering và tái bọc DEK.
5. Đưa thiết kế vào KMS/HSM, kiểm soát key ID, multi-tenant, quyền gọi dịch vụ mã hóa, lịch rotation, backup, kiểm thử phục hồi và audit mà không lưu khóa bí mật lộ thiên.

**Giới hạn của ví dụ:** chương trình Java bên dưới dùng hai `SecretKey` được tạo **trong bộ nhớ** để minh họa tầng DEK/KEK. Đây **không phải** một KMS thật, không cung cấp kiểm soát IAM, HSM, audit hay bảo vệ khóa trước tiến trình bị xâm phạm. Trong sản phẩm thực tế, KEK nên được quản lý bằng dịch vụ khóa/KMS hoặc thiết bị bảo mật phù hợp; code ứng dụng chỉ có quyền thực hiện những thao tác cần thiết theo policy.

## 1. Bài toán: vì sao không dùng một khóa AES cho mọi dữ liệu?

Giả sử dịch vụ lưu hàng triệu bản ghi hoặc tệp, mỗi tệp được mã hóa bằng AES-GCM. Cách đơn giản nhất là lấy **một khóa AES toàn hệ thống** và dùng nó mã hóa từng tệp. Nhưng khi làm vậy:

- Mỗi service cần giải mã đều có thể phải truy cập **cùng một khóa dùng cho tất cả dữ liệu**, làm tăng phạm vi thiệt hại nếu khóa bị lộ.
- Đổi khóa mã hóa dữ liệu có thể đòi hỏi đọc và mã hóa lại khối lượng lớn dữ liệu, tốn I/O, CPU và thời gian.
- Phân quyền theo tenant, tài liệu hoặc ứng dụng trở nên khó kiểm soát; một khóa sai phạm vi có thể giải mã nhiều thứ không liên quan.
- Việc theo dõi phiên bản khóa, thu hồi quyền, backup/restore và khôi phục sau sự cố trở nên phức tạp.
- Nếu nonce AES-GCM bị lặp lại dưới cùng khóa, bảo mật bị tổn hại nghiêm trọng. Dùng một khóa cho số lượng phép mã hóa khổng lồ làm tăng gánh nặng vận hành nonce và key lifetime.

**Envelope encryption** khắc phục một phần các vấn đề trên bằng **phân tầng khóa**. Thông thường, dữ liệu được mã hóa bằng **một DEK riêng**; chính DEK lại được **bọc (wrap/encrypt)** dưới một **KEK** có phạm vi bảo vệ/ủy quyền rộng hơn. Nhờ đó, phần dữ liệu lớn có thể được mã hóa cục bộ nhanh chóng, trong khi khóa tầng cao được quản lý tập trung và hạn chế truy cập.

Không có nghĩa mô hình này tự cung cấp mọi bảo đảm. Nếu ứng dụng được phép gọi KMS để mở mọi DEK và bị chiếm quyền, attacker vẫn có thể giải mã dữ liệu trong phạm vi quyền đó. Envelope encryption là một phần của kiến trúc an toàn, không thay thế least privilege, identity, audit, nonce policy và kiểm soát plaintext trong bộ nhớ.

## 2. Hai loại khóa: DEK và KEK

| Tiêu chí | **DEK — Data Encryption Key** | **KEK — Key Encryption Key** |
| --- | --- | --- |
| Mục đích | Mã hóa **nội dung dữ liệu** (file, bản ghi, object, blob) | **Bảo vệ DEK** (wrap/encrypt/unwrap) |
| Phạm vi | Có thể một object, một nhóm object hoặc một phiên, theo chính sách; thường ưu tiên phạm vi hẹp | Có thể bảo vệ nhiều DEK; nên ràng buộc tenant, app, môi trường, vai trò và key policy |
| Ví dụ thuật toán | AES-256-GCM (AEAD), với nonce duy nhất khi dùng cùng DEK | AES key wrap / AES-GCM được cấu hình đúng, hoặc wrap bằng KMS/HSM; có thể dùng cơ chế bất đối xứng phù hợp |
| Sinh khóa | Sinh bằng CSPRNG; thường sinh **DEK mới** khi mã hóa object mới | Sinh/quản lý trong KMS/HSM hoặc secret manager/keystore có kiểm soát |
| Lưu trữ | **Không lưu plaintext DEK cùng ciphertext**; có thể lưu **wrapped DEK** | Giữ KEK ở vùng tin cậy; nếu KMS/HSM giữ key không xuất được, ứng dụng chỉ thấy key ID/handle |
| Quyền sử dụng | Dùng tạm để mã hóa/giải mã nội dung cụ thể | Quyền wrap/unwrap, ràng buộc identity, key policy, audit và quota |
| Rotation | Đổi DEK thường **phải mã hóa lại dữ liệu** được bảo vệ bởi DEK cũ | Đổi KEK có thể **rewrap các DEK** mà không thay ciphertext dữ liệu |
| Khi lộ | Ảnh hưởng dữ liệu mã hóa bằng DEK đó; phạm vi phụ thuộc cách tái sử dụng | Có thể ảnh hưởng nhiều DEK đã được bọc bằng KEK đó, gồm bản sao lưu cũ |

**Thuật ngữ:**

- **Plaintext DEK:** byte khóa gốc, dùng trực tiếp với AES-GCM để mã hóa dữ liệu; là secret.
- **Wrapped/encrypted DEK:** dữ liệu mã hóa chứa DEK và tag/metadata cần thiết; có thể được lưu cùng ciphertext của nội dung, nhưng bản thân nó **không phải khóa có thể dùng trực tiếp**.
- **KEK ID / key version:** định danh để hệ thống **tìm đúng KEK tin cậy** khi unwrap; key ID không phải secret và **không tự cấp quyền**.
- **Master/root key:** tên gọi tùy hệ thống cho khóa ở tầng cao hơn, có thể chính là KEK do KMS bảo vệ. Không mặc định mọi hệ thống đều phải có đúng ba tầng.

Ví dụ dữ liệu dài 10 MiB được mã hóa bằng AES-256-GCM dưới DEK 32 byte. KEK chỉ cần bọc **32 byte DEK** (cộng overhead của scheme wrap), không phải nhận cả 10 MiB. Đây là điểm đem lại lợi ích hiệu năng và tách nhiệm vụ.

## 3. Envelope trông như thế nào?

Một thiết kế lưu trữ hợp lý phải ghi đủ metadata để giải mã **đúng** trong tương lai; ví dụ minh họa:

```text
Encrypted Object Envelope
+-------------------------------------------------------+
| envelopeVersion = 1                                   |
| tenantId / objectId / purpose (theo protocol)         |
| dataAlgorithm = AES-256-GCM                           |
| dataNonce (12 bytes)                                  |
| dataCiphertext || dataTag (GCM tag 16 bytes)           |
|                                                       |
| wrappingAlgorithm = KMS-based-wrap / AES-GCM-wrap     |
| kekId = "tenant-A/kek-v3"                              |
| wrapNonce (nếu wrap scheme yêu cầu)                    |
| wrappedDEK || wrapTag (nếu là AEAD-GCM wrap)           |
+-------------------------------------------------------+
```

Trong đó:

- **dataCiphertext** là bản mã của dữ liệu dài, được tạo bằng DEK.
- **wrappedDEK** là DEK sau khi được bảo vệ bằng KEK; không thể thay thế cho DEK để giải mã dữ liệu nếu chưa unwrap.
- **dataNonce** và **wrapNonce** là hai nonce của **hai phép mã hóa riêng**. Nếu dùng GCM, nonce cần duy nhất **theo từng khóa được sử dụng**. Việc thấy nonce trong envelope không tiết lộ khóa (nonce không phải secret).
- **dataTag / wrapTag** cung cấp xác thực AEAD tương ứng cho *mỗi tầng* khi dùng GCM. Tag không được cắt/bỏ tùy tiện.
- **kekId** cho biết dùng KEK nào **đã được đăng ký và cho phép**. Không dùng một URL/key do payload tự khai để thay thế trusted key registry.
- **tenantId**, **objectId** và **purpose** giúp gắn record với đúng ranh giới dữ liệu; các trường ảnh hưởng cách hiểu nội dung phải được **xác thực** qua AAD hoặc cơ chế tương đương.

Sơ đồ hai tầng:

```text
                  DATA PLANE                                KEY PLANE
plaintext data ----------> AES-GCM(plaintext DEK) --> dataCiphertext + dataTag
                                 ^                           |
                                 |                           v
CSPRNG --> plaintext DEK --------+                  lưu dataNonce + ciphertext
            |                    |
            v                    |
  wrap/encrypt under KEK         |
            |                    |
            v                    |
    wrapped DEK + metadata ------+------> lưu cùng encrypted object
            ^
            |
      KEK do KMS/HSM quản lý
       (không nằm trong object)
```

Sơ đồ minh họa chức năng, không phải phân chia máy chủ bắt buộc. Cả ciphertext dữ liệu, wrapped DEK, nonce và metadata có thể cùng nằm trong storage; **chính KEK và plaintext DEK phải được bảo vệ**.

**Cẩn thận với “encrypted DEK” versus “DEK”:** gọi `getEncoded()` của secret key AES có thể đưa **khóa thật** ra mảng byte. Không lưu mảng này vào envelope. Đối tượng envelope chỉ chứa **giá trị đã bọc**; plaintext DEK được xóa/hạn chế lưu giữ sau khi thao tác hoàn tất trong khả năng của runtime.

## 4. Luồng mã hóa: tạo DEK và bọc bằng KEK

Quy trình khi tạo một object:

1. **Xác định chính sách từ phía đáng tin:** tenant, object ID, mục đích, KEK được phép, phiên bản envelope và thuật toán. Không để client tùy ý áp đặt key ID bên ngoài allowlist.
2. **Sinh DEK mới** từ nguồn ngẫu nhiên mật mã, ví dụ 32 byte cho AES-256. Không suy DEK từ object ID, timestamp, mật khẩu yếu hay hash nội dung.
3. **Mã hóa dữ liệu với DEK**, thông thường bằng `AES/GCM/NoPadding` với nonce 12 byte duy nhất dưới DEK, tag 128 bit và AAD gắn context ổn định.
4. **Bọc DEK bằng KEK**: tốt nhất nhờ KMS/HSM hoặc một wrap primitive được chuẩn hóa. Nếu dùng AES-GCM làm thao tác bọc, phải sinh **nonce mới và duy nhất dưới chính KEK** và đưa vào AAD các thuộc tính ràng buộc cần thiết.
5. **Gắn metadata**: key ID phiên bản, thuật toán, nonce/tag, schema version, thông tin context. Lưu kết quả nhất quán với object và kiểm tra giới hạn kích thước trước/ sau mã hóa.
6. **Chỉ commit record hoàn chỉnh** (ciphertext data và wrapped DEK đi cùng nhau). Không công bố một object chưa có đủ tag hoặc key metadata; nếu lưu nhiều dịch vụ, cần giao thức commit/rollback tránh trạng thái không nhất quán.
7. **Giảm tồn tại plaintext DEK** trong bộ nhớ, log, crash dump, trace. Việc ghi zero vào `byte[]` trong Java là best effort; JIT, garbage collector và provider có thể giữ bản sao mà ứng dụng không điều khiển hoàn toàn.

### Cùng một KEK có thể bọc nhiều DEK

Đây là chức năng của KEK, nhưng **KEK là điểm tập trung quyền**. Mỗi lần wrap phải dùng scheme an toàn và tuân thủ nonce/usage limit. Nếu bảo vệ nhiều tenant, tốt nhất phân vùng key policy hoặc KEK theo tenant/rủi ro. Việc tách key theo tenant/object không thay thế xác thực quyền truy cập dữ liệu trước khi gọi unwrap.

### Data AAD và Wrap AAD phải có mục đích rõ

Có thể dùng hai AAD độc lập:

```text
dataAAD = Encode("DATA-v1", tenantId, objectId, dataSchemaVersion)
wrapAAD = Encode("WRAP-v1", tenantId, objectId, kekId, wrappingVersion)
```

`Encode` phải là serialization **không mơ hồ** (length prefix, schema canonical, các trường có kiểu và thứ tự cố định). Không nối tùy ý `("ab" || "c")` và `("a" || "bc")` để hai nhóm metadata có cùng bytes. AAD **không được mã hóa**, nên đừng đưa secret vào AAD với kỳ vọng nó sẽ được che giấu. Nhưng thay đổi AAD khiến tag xác thực GCM thất bại.

Một chi tiết quan trọng cho rotation: nếu chỉ đổi KEK, **dataAAD không nên phụ thuộc trực tiếp vào kekId** trong một mô hình mà bạn mong giữ nguyên data ciphertext/tag. Khi thay KEK, giữ nguyên context dữ liệu để **dataNonce + dataCiphertextAndTag** không đổi; chỉ tạo **wrapped DEK mới** với `wrapAAD` chứa key ID mới. Nếu chính sách của bạn muốn thay cả dataAAD, sẽ phải giải mã và mã hóa lại dữ liệu/tag (hoặc dùng cơ chế protocol khác có xác thực tương đương).

## 5. Luồng giải mã: xác thực hai lớp

Khi đọc object:

1. Kiểm tra **version, format, giới hạn kích thước** và mandatory fields. Xác định tenant/object ID mong đợi từ request được xác thực hoặc trusted storage path; không lấy mọi thông tin xác thực chỉ từ payload do attacker kiểm soát.
2. Tra cứu `kekId` trong **trusted registry/KMS** của tenant/mục đích đã xác định. Kiểm tra quyền gọi unwrap; key ID không phải secret/password.
3. Dùng KEK phù hợp **unwrap wrapped DEK**, kiểm tra tag/wrapping integrity và wrap AAD. **Không dùng DEK** nếu bước unwrap chưa xác thực thành công.
4. Kiểm tra byte DEK đã unwrap có **loại/độ dài đúng**; tạo tạm `SecretKeySpec` (nếu key bytes nằm trong process) hoặc dùng handle phù hợp của provider.
5. Giải mã `dataCiphertextAndTag` bằng DEK, nonce, tag và data AAD tương ứng. Chỉ xem plaintext là hợp lệ **sau khi `Cipher.doFinal` thành công và tag được xác nhận**.
6. Kiểm tra authorization ở mức **object/resource/action** và các ràng buộc nghiệp vụ; không trả plaintext nhạy cảm chỉ vì ai đó có thể lấy wrapped DEK.
7. Không log DEK, KEK, plaintext hoặc thông tin vượt quá yêu cầu vận hành; cố gắng xóa secret tạm trong mức khả thi.

Nếu wrapped DEK bị tráo từ một object khác, wrap AAD gắn `tenantId/objectId/purpose` giúp chặn khi không khớp. Nếu attacker có quyền thay cả metadata chưa xác thực và hệ thống tin ngay vào metadata đó, AAD có thể bị dùng sai ngữ cảnh; vì vậy cần **nguồn expected context đáng tin** ở phía server, không chỉ “dữ liệu tự mô tả” do client gửi.

**Hai tag bảo vệ hai thứ khác nhau** khi dùng GCM ở cả tầng: wrap tag xác thực DEK/metadata của wrap; data tag xác thực ciphertext/metadata của data. Chỉ verify một tag rồi bỏ tag còn lại là sai.

## 6. Java 17 — chương trình hoàn chỉnh: mã hóa envelope và rewrap KEK

Mã dưới đây cố tình không dùng SDK KMS ngoài JDK. Nó sinh **ba KEK trong bộ nhớ** (cũ, mới, sai) bằng `KeyGenerator`, tạo **một DEK 32 byte** qua `SecureRandom`, mã hóa nội dung bằng AES-GCM với DEK, rồi **mã hóa/bọc DEK bằng một KEK khác** cũng qua AES-GCM. Cách dùng GCM để bảo vệ DEK trong ví dụ là **key encryption với authentication**; các KMS/HSM hoặc giao thức thật có thể dùng **AES Key Wrap** hoặc wrapping primitive khác với API/metadata khác.

Mỗi phép `seal` sinh nonce ngẫu nhiên 12 byte mới và sử dụng tag 128 bit. Với KEK tồn tại lâu và số lượng thao tác lớn, không chỉ dựa vào “random thường là không trùng”: phải có **quy tắc không tái sử dụng nonce dưới cùng KEK** và giới hạn usage theo chính sách/thiết kế GCM. Mã demo có hai vùng AAD độc lập `DATA-v1` và `WRAP-v1`, cùng `objectId`; metadata được mã hóa theo length-prefix để tránh ranh giới mơ hồ.

Chương trình chủ ý chứa các test:

- Mở đúng envelope với KEK cũ: **đạt**.
- Dùng **KEK sai**, đổi object ID, sửa data ciphertext/tag, sửa wrapped DEK/tag, làm thiếu số byte tag của wrapped DEK: **từ chối**.
- **Rewrap DEK** sang KEK mới: data nonce và data ciphertext/tag **giữ nguyên**; KEK mới giải mã được, KEK cũ không còn được chấp nhận cho envelope mới.

Tạo đúng tệp **`EnvelopeEncryptionDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class EnvelopeEncryptionDemo {
    private static final int DEK_BYTES = 32;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final SecureRandom RANDOM = new SecureRandom();

    private record Sealed(byte[] nonce, byte[] ciphertextAndTag) {
        Sealed {
            nonce = nonce.clone();
            ciphertextAndTag = ciphertextAndTag.clone();
        }
        @Override public byte[] nonce() { return nonce.clone(); }
        @Override public byte[] ciphertextAndTag() {
            return ciphertextAndTag.clone();
        }
    }

    private record Envelope(String keyId, Sealed wrappedDek, Sealed data) {}

    public static void main(String[] args) throws Exception {
        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256);
        SecretKey oldKek = keyGenerator.generateKey();
        SecretKey newKek = keyGenerator.generateKey();
        SecretKey wrongKek = keyGenerator.generateKey();

        String objectId = "invoice-42";
        String oldId = "kek-v1";
        String newId = "kek-v2";
        byte[] plaintext = "amount=250;currency=USD"
                .getBytes(StandardCharsets.UTF_8);

        Envelope before = encryptEnvelope(oldKek, oldId, objectId, plaintext);
        System.out.println("Original round-trip: " + Arrays.equals(
                plaintext, decryptEnvelope(before, oldKek, oldId, objectId)));
        System.out.println("Wrong KEK rejected: " + rejects(
                () -> decryptEnvelope(before, wrongKek, oldId, objectId)));
        System.out.println("Wrong object ID rejected: " + rejects(
                () -> decryptEnvelope(before, oldKek, oldId, "invoice-43")));

        byte[] changedData = before.data().ciphertextAndTag();
        changedData[0] ^= 1;
        Envelope forgedData = new Envelope(oldId, before.wrappedDek(),
                new Sealed(before.data().nonce(), changedData));
        System.out.println("Changed data rejected: " + rejects(
                () -> decryptEnvelope(forgedData, oldKek, oldId, objectId)));

        byte[] changedWrap = before.wrappedDek().ciphertextAndTag();
        changedWrap[changedWrap.length - 1] ^= 1;
        Envelope forgedWrap = new Envelope(oldId,
                new Sealed(before.wrappedDek().nonce(), changedWrap),
                before.data());
        System.out.println("Changed DEK wrap rejected: " + rejects(
                () -> decryptEnvelope(forgedWrap, oldKek, oldId, objectId)));

        Envelope tooShort = new Envelope(oldId,
                new Sealed(before.wrappedDek().nonce(), new byte[TAG_BYTES - 1]),
                before.data());
        System.out.println("Short wrapped DEK rejected: " + rejects(
                () -> decryptEnvelope(tooShort, oldKek, oldId, objectId)));

        Envelope after = rewrap(before, oldKek, oldId, newKek, newId, objectId);
        System.out.println("Rewrap keeps data bytes: "
                + Arrays.equals(before.data().nonce(), after.data().nonce())
                + " / " + Arrays.equals(before.data().ciphertextAndTag(),
                        after.data().ciphertextAndTag()));
        System.out.println("New KEK decrypts: " + Arrays.equals(
                plaintext, decryptEnvelope(after, newKek, newId, objectId)));
        System.out.println("Old KEK rejected after rewrap: " + rejects(
                () -> decryptEnvelope(after, oldKek, newId, objectId)));
    }

    private static Envelope encryptEnvelope(
            SecretKey kek, String kekId, String objectId, byte[] plaintext)
            throws GeneralSecurityException {
        byte[] dek = new byte[DEK_BYTES];
        RANDOM.nextBytes(dek);
        try {
            Sealed data = seal(new SecretKeySpec(dek, "AES"), plaintext,
                    associatedData("DATA-v1", objectId, ""));
            Sealed wrapped = seal(kek, dek,
                    associatedData("WRAP-v1", objectId, kekId));
            return new Envelope(kekId, wrapped, data);
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    private static byte[] decryptEnvelope(
            Envelope envelope, SecretKey kek, String expectedKekId,
            String objectId) throws GeneralSecurityException {
        if (!envelope.keyId().equals(expectedKekId)) {
            throw new IllegalArgumentException("Unexpected KEK identifier");
        }
        byte[] dek = open(kek, envelope.wrappedDek(),
                associatedData("WRAP-v1", objectId, expectedKekId));
        try {
            if (dek.length != DEK_BYTES) {
                throw new GeneralSecurityException("Unexpected DEK length");
            }
            return open(new SecretKeySpec(dek, "AES"), envelope.data(),
                    associatedData("DATA-v1", objectId, ""));
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    private static Envelope rewrap(
            Envelope original, SecretKey oldKek, String oldId,
            SecretKey newKek, String newId, String objectId)
            throws GeneralSecurityException {
        if (!original.keyId().equals(oldId)) {
            throw new IllegalArgumentException("Unexpected old KEK identifier");
        }
        byte[] dek = open(oldKek, original.wrappedDek(),
                associatedData("WRAP-v1", objectId, oldId));
        try {
            if (dek.length != DEK_BYTES) {
                throw new GeneralSecurityException("Unexpected DEK length");
            }
            Sealed wrapped = seal(newKek, dek,
                    associatedData("WRAP-v1", objectId, newId));
            return new Envelope(newId, wrapped, original.data());
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    private static Sealed seal(SecretKey key, byte[] input, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return new Sealed(nonce, cipher.doFinal(input));
    }

    private static byte[] open(SecretKey key, Sealed sealed, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = sealed.nonce();
        byte[] ciphertextAndTag = sealed.ciphertextAndTag();
        if (nonce.length != NONCE_BYTES || ciphertextAndTag.length < TAG_BYTES) {
            throw new IllegalArgumentException("Invalid sealed field");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    private static byte[] associatedData(
            String domain, String objectId, String kekId) {
        byte[] d = domain.getBytes(StandardCharsets.UTF_8);
        byte[] o = objectId.getBytes(StandardCharsets.UTF_8);
        byte[] k = kekId.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(12 + d.length + o.length + k.length)
                .putInt(d.length).put(d)
                .putInt(o.length).put(o)
                .putInt(k.length).put(k)
                .array();
    }

    @FunctionalInterface
    private interface Operation { void run() throws GeneralSecurityException; }

    private static boolean rejects(Operation operation) {
        try {
            operation.run();
            return false;
        } catch (GeneralSecurityException | IllegalArgumentException e) {
            return true;
        }
    }
}
```

Biên dịch và chạy với JDK 17+ có AES-256-GCM:

```bash
javac --release 17 EnvelopeEncryptionDemo.java
java EnvelopeEncryptionDemo
```

**Stdout** (đã biên dịch/chạy kiểm thử bằng Java 17):

```text
Original round-trip: true
Wrong KEK rejected: true
Wrong object ID rejected: true
Changed data rejected: true
Changed DEK wrap rejected: true
Short wrapped DEK rejected: true
Rewrap keeps data bytes: true / true
New KEK decrypts: true
Old KEK rejected after rewrap: true
```

Chương trình dùng các khóa và nonce ngẫu nhiên, **không in ra key material**, nên chuỗi ciphertext thay đổi mỗi lần chạy nhưng 9 dòng boolean trên phản ánh kết quả mong đợi. Nếu Java/provider không hỗ trợ transformation hoặc key size theo chính sách hiện hành, các bước `getInstance`/`init` có thể báo lỗi; đừng lặng lẽ hạ key length/mode để “cho chạy”.

### Tại sao demo này thể hiện đúng nguyên lý?

- `encryptEnvelope` sinh **DEK riêng** và dùng nó mã hóa **plaintext data**; `kek` chỉ bọc **DEK**, không tham gia trực tiếp mã hóa nội dung.
- `Sealed` lưu nonce và `ciphertextAndTag`; mảng byte được clone khi tạo/trả về record để các phép thử thay đổi đầu vào **không âm thầm sửa envelope ban đầu**.
- `associatedData` mã hóa domain, object ID và key ID bằng UTF-8 với **ba độ dài int big-endian**. Mỗi bộ trường có ranh giới xác định; đây là minh họa encoding nội bộ, không tự nhận là chuẩn interoperable công khai.
- `DATA-v1` và `WRAP-v1` là domain separation: dùng cùng tên biến “context” không có nghĩa các byte AAD của hai tầng phải giống nhau. `kekId` chỉ ràng buộc vào wrap AAD nên rewrap không thay data ciphertext.
- `decryptEnvelope` từ chối nếu key ID envelope không bằng **expectedKekId** mà caller đã quyết định. Trong production, expected ID phải được chọn **qua trusted tenant/key registry**, không được “trust” chỉ bằng việc sao chép `envelope.keyId()` vào biến expected.
- Khi `Cipher.doFinal` kiểm tra GCM tag thất bại, Java thường ném `AEADBadTagException` (kế thừa `BadPaddingException`). Hàm test `rejects` gộp các lỗi chỉ để hiển thị; API thực phải phân loại nội bộ và trả lỗi public không tạo oracle.
- `rewrap` cần giải mã **DEK**, nhưng **không bao giờ gọi `open` trên data ciphertext**. Kết quả data nonce và data ciphertext/tag giữ nguyên, kiểm tra bằng `Arrays.equals`.
- `Arrays.fill(dek, (byte) 0)` cố gắng xóa bản byte[] tạm, **không bảo đảm** xóa mọi bản sao trong JVM/hardware; trong production, ưu tiên KMS/HSM với tính năng không xuất KEK và quản lý heap/secret lifecycle chặt.

### Giới hạn của ví dụ cần nhận diện

Mã chạy độc lập chỉ xử lý **một object và một lần chuyển KEK**. Nó không lưu envelope ra file/database, không kiểm tra IAM, không cung cấp transaction/rotation lock, không serialize toàn bộ cấu trúc để chống lỗi parse từ dữ liệu không đáng tin, và không thực hiện key discovery hay gọi KMS. `Operation`/`rejects` giúp trình bày trường hợp từ chối, không nên dùng trực tiếp làm API contract.

Đặc biệt, `Sealed` trong demo dùng AES-GCM cho **cả data lẫn wrap**. Với KMS/HSM thực, có thể sử dụng cơ chế wrapping chuyên dụng, chẳng hạn AES Key Wrap hay thao tác KMS `Encrypt`/`Decrypt`/`GenerateDataKey`/`ReEncrypt` tùy nhà cung cấp. **Không** tự chuyển đổi dữ liệu GCM-wrapped thành output AESWrap: thuật toán, IV, tag và format **khác nhau**.

## 7. Rewrap, re-encrypt và rotate: ba việc khác nhau

Từ “xoay khóa” dễ gây hiểu nhầm vì có nhiều tầng:

### 7.1 Rewrap (đổi KEK, giữ DEK)

```text
TRƯỚC:
plaintext data -- encrypt(DEK1) --> ciphertextData1
DEK1           -- wrap(KEK-A) --> wrappedDEK-A

SAU REWRAP:
ciphertextData1             [KHÔNG ĐỔI]
DEK1           -- wrap(KEK-B) --> wrappedDEK-B
keyId: KEK-A -> KEK-B
```

Quá trình cần quyền **unwrap với KEK-A** và **wrap với KEK-B**. Tùy dịch vụ KMS, thao tác có thể được thực hiện trong ranh giới dịch vụ khóa mà không xuất DEK ra ứng dụng, hoặc cần mở DEK trong một vùng tin cậy để rewrap.

**Ưu điểm:** không đọc/mã hóa lại data file 10 GiB; chỉ xử lý một DEK ngắn và metadata. Chi phí phụ thuộc số object/DEK phải chuyển, số lời gọi KMS và storage metadata. Nếu có 1 triệu object, vẫn phải rewrap khoảng 1 triệu wrapped DEK nếu mỗi object có DEK riêng: **không phải thao tác O(1) cho cả kho**.

**Yêu cầu vận hành:** ghi wrapped DEK mới + key ID + metadata liên quan **nguyên tử** hoặc bằng quy trình có thể recover. Không xóa KEK-A trước khi tất cả object/backup cần thiết đã chuyển và quy trình khôi phục xác nhận có thể dùng KEK-B.

### 7.2 Rotate DEK (đổi khóa mã hóa dữ liệu)

Nếu chính DEK bị lộ hoặc vượt giới hạn sử dụng, tạo **DEK2 mới**, giải mã data bằng DEK1 rồi **mã hóa lại** bằng DEK2 với nonce/AAD phù hợp và lưu ciphertext/tag mới. Sau đó bọc DEK2 bằng KEK đã được phê duyệt.

```text
dataCiphertext1 -- decrypt(DEK1) --> plaintext
plaintext       -- encrypt(DEK2) --> dataCiphertext2
DEK2            -- wrap(KEK-B)  --> wrappedDEK2
```

Công việc này tác động toàn bộ dữ liệu và phải xử lý cẩn thận **plaintext tạm**, storage, timeout, tính nhất quán, checksum/integrity và rollback.

**Không đánh đồng rewrap với DEK rotation.** Nếu DEK1 đã bị lộ, chỉ rewrap dưới KEK mới **không làm DEK1 trở lại bí mật**.

### 7.3 KMS-managed rotation (thay key material bên trong dịch vụ)

Một số KMS cung cấp **automatic rotation** cho khóa được quản lý, có thể giữ các phiên bản key material cũ để giải mã ciphertext lịch sử và tự áp dụng phiên bản mới cho mã hóa mới. Tùy provider/key type, **automatic rotation không có nghĩa mọi wrapped DEK cũ được rewrap ngay** và cũng không có nghĩa key ID của từng object thay đổi.

Phải đọc đúng semantics của nhà cung cấp: alias thay đổi, phiên bản key, ciphertext chứa metadata key nào, quyền decrypt bản cũ, thời gian chờ, cách backup/migration và giới hạn API. **Không tự suy** rằng bật một nút “rotation” sẽ xóa tác động của dữ liệu khóa từng bị lộ.

### 7.4 Sự cố lộ khóa và bản sao cũ

| Sự kiện | Hành động thường cần | Vì sao chỉ rewrap không đủ trong một số trường hợp |
| --- | --- | --- |
| Chuyển quản lý từ KEK-A sang KEK-B, chưa có dấu hiệu lộ | Rewrap DEK + chuyển policy, kiểm thử backup/restore | Đây là đúng use case hiệu quả của rewrap |
| Quyền một service bị thu hồi | Giảm quyền KMS + credential rotation + audit + đánh giá cache plaintext/DEK | Service có thể đã trích xuất DEK hoặc dữ liệu khi còn quyền |
| **KEK-A bị lộ** | Incident response, ngăn dùng KEK-A, đánh giá ciphertext/wrapped DEK cũ và backup, rewrap và có thể re-encrypt dữ liệu | Ai đã lưu bản sao **wrappedDEK-A + ciphertextData** và KEK-A có thể vẫn giải mã bản sao cũ; rewrap bản hiện tại **không thu hồi được snapshot** |
| **DEK bị lộ** | Re-encrypt dữ liệu liên quan bằng DEK mới, bọc lại, thu hồi bản cũ theo quy trình | KEK mới không làm thay đổi việc attacker biết DEK cũ |
| Xóa dữ liệu (“crypto-erasure”) | Quy trình hủy key liên quan, backup/cache/snapshot, kiểm soát retention | Xóa một wrapped DEK không bảo đảm không còn bản sao hoặc plaintext ở nơi khác |

**Tính bảo mật lịch sử không thể được tạo ngược bởi rotation.** Khi một khóa từng bị lộ, phải đánh giá dữ liệu attacker **đã lấy được**, backup, snapshot, log, các bản DEK/KEK được cache, chứ không chỉ nhìn vào khóa hiện hành.

## 8. KMS/HSM trong mô hình envelope encryption

### 8.1 Dịch vụ khóa thường làm gì?

Một API kiểu `GenerateDataKey` có thể trả:

- **Plaintext DEK** để ứng dụng mã hóa dữ liệu ngay tại chỗ (nếu API/policy cho phép).
- **Encrypted/wrapped DEK** để lưu cùng encrypted object.
- Metadata cần thiết như KMS key ID và encryption context, tùy dịch vụ.

Sau khi mã hóa dữ liệu, ứng dụng không lưu plaintext DEK. Lần giải mã về sau gửi **wrapped DEK** cùng **encryption context**/metadata thích hợp tới KMS theo quyền được cấp; KMS kiểm tra policy và trả về DEK plaintext hoặc thực hiện unwrap trong ranh giới bảo vệ tương ứng. Tên API, thành phần response và semantics phụ thuộc nhà cung cấp.

Một số HSM/KMS có thể giữ KEK **non-exportable**, giới hạn chỉ wrap/unwrap/reencrypt. Tuy vậy nếu API trả plaintext DEK, ứng dụng vẫn phải bảo vệ DEK khi nó đi qua process memory. **“KEK không xuất được” không đồng nghĩa plaintext DEK chưa từng ở trong JVM**.

### 8.2 Policy và audit quan trọng ngang thuật toán

- Chỉ service có quyền, tại đúng tenant/project và context, được phép gọi **wrap/unwrap**.
- Tách role **encrypt-only** (có thể chỉ wrap tạo bản mới) với **decrypt-capable** nếu use case cho phép.
- Bảo vệ key policy, alias/registry, IAM, service identities, network boundary, quota, key deletion schedule.
- Audit **key ID, caller identity, mục đích, object/tenant reference hợp lệ, thời gian và kết quả**. Không ghi DEK plaintext, KEK, plaintext data, request secret.
- Các API encryption context thường coi context là **AAD không bí mật**: đừng đặt mật khẩu/token hoặc PII nhạy cảm vào đó nếu KMS logging/API có thể hiển thị context.
- Kiểm thử permission denial và lỗi provider trước rollout. Không fallback sang khóa hardcoded/local yếu để “tiếp tục chạy”.

### 8.3 So sánh các cách bảo vệ DEK

| Cách bọc DEK | Mô hình | Lưu ý |
| --- | --- | --- |
| **AES-GCM với KEK** | Mã hóa DEK thành ciphertext + tag, cần nonce duy nhất dưới cùng KEK | Có thể làm theo JCA; phải serialize nonce/tag và ràng buộc AAD; demo dùng cách này |
| **AES Key Wrap (RFC 3394)** | Primitive dành riêng cho đóng gói key material | Có kiểm tra tính toàn vẹn theo scheme; format/độ dài đầu vào khác GCM; tên và hỗ trợ `Cipher` tùy provider |
| **AES Key Wrap with Padding (RFC 5649)** | Biến thể wrap hỗ trợ độ dài key material tổng quát hơn | Không nhầm với PKCS5Padding/GCM; hỗ trợ provider phải kiểm tra |
| **KMS/HSM wrap/unwrap** | KEK do dịch vụ/hardware quản lý, ứng dụng gọi API đã cấp phép | KMS key ID, encryption context, IAM, logging, latency và quota; không giả định thuật toán nội bộ của mọi nhà cung cấp giống nhau |
| **RSA-OAEP bảo vệ DEK** | Public key encrypt DEK ngắn; private key decrypt | Dùng khi kiến trúc bất đối xứng cần thiết, đúng OAEP params/key custody; không dùng raw RSA hoặc RSA PKCS#1 v1.5 cũ khi thiết kế mới |
| **Encrypt data trực tiếp bằng KMS** | Một số dịch vụ cho mã hóa đầu vào nhỏ trực tiếp | Dữ liệu lớn nên dùng DEK cục bộ và KMS chỉ xử lý key; kiểm tra giới hạn kích thước input cụ thể |

**Không** dùng `AES/ECB/NoPadding` thô để “mã hóa DEK”, không dùng phép XOR với một chuỗi cố định, không băm DEK thành “wrapped key”, và không coi Base64/hex là mã hóa. Một primitive mã hóa key phải có tính bảo mật và integrity đúng scheme.

## 9. Nguyên tắc về nonce, AAD và thuật toán

### 9.1 Dữ liệu mã hóa và DEK được bọc đều cần integrity

Nếu thuật toán wrap chỉ cung cấp confidentiality mà thiếu integrity, một DEK bị sửa có thể đi đến giải mã hoặc dẫn tới failure khó phân tích. Dùng AEAD hoặc key-wrap scheme có kiểm tra integrity để không chấp nhận key material bị thay đổi.

Với `AES/GCM/NoPadding`:

- GCM tag thường dài **128 bit**, Java nhận `GCMParameterSpec(128, nonce)` với **độ dài tính theo bit**.
- Nonce **12 byte** là cấu hình điển hình; phải duy nhất **dưới cùng key**. Data encryption dùng **DEK**, wrap encryption dùng **KEK**, nên có hai yêu cầu quản lý nonce riêng.
- `Cipher.updateAAD(...)` phải thực hiện trước `update/doFinal` đối với dữ liệu trong Java GCM; phía decrypt phải dùng **cùng bytes AAD**.
- `Cipher.doFinal(...)` chỉ xuất plaintext hợp lệ khi xác minh tag thành công. Không publish output tạm trước authentication.
- Nếu tag/nonce/AAD/key bị sửa, quá trình giải mã GCM thất bại (`AEADBadTagException` thường gặp). **Không thể biết chắc loại lỗi vật lý chỉ từ tên exception**.

Khi dùng 96-bit random nonce và KEK sống lâu, số lượng lần wrap phải được hạn chế sao cho xác suất va chạm nonce vẫn trong mức rủi ro cho phép, hoặc dùng cơ chế quản lý nonce duy nhất bảo đảm theo policy. **Không reuse nonce trong cùng KEK** chỉ vì hai DEK khác nhau.

### 9.2 Ràng buộc tenant/object/role

Một lỗi nguy hiểm là lấy wrapped DEK của tenant A gắn vào ciphertext tenant B rồi **trông đợi tag data tự giải quyết tất cả**. Tag data có thể fail khi key khác, nhưng chỉ riêng điều đó không tạo được mô hình ủy quyền đúng.

Các lớp bảo vệ nên đồng thời bao gồm:

1. **Access control:** chỉ được lấy object và gọi unwrap cho đúng tenant.
2. **Trusted key ID mapping:** `tenantId + purpose + kekId` ánh xạ tới KEK đã cấp quyền.
3. **Wrap AAD:** ràng buộc DEK được bọc với object/tenant/purpose và phiên bản thích hợp.
4. **Data AAD:** ràng buộc ciphertext với object/tenant/purpose, format/version thích hợp.
5. **Authenticated data format:** đảm bảo cả bên tạo và bên đọc thống nhất representation của metadata trước khi tính tag.

AAD không giữ bí mật metadata; cần thêm encryption nếu chính các trường metadata cũng phải được giấu. Nhưng không được bỏ AAD chỉ vì “đã có ciphertext tag”.

### 9.3 Đừng đưa `kekId` vào data AAD nếu cần giữ nguyên data khi rewrap

Hàm `associatedData("DATA-v1", objectId, "")` trong demo không chứa `kekId`; `associatedData("WRAP-v1", objectId, kekId)` có chứa. Nhờ vậy sau rewrap:

```text
dataNonce:              giữ nguyên
dataCiphertextAndTag:   giữ nguyên
wrappedDEK:             thay đổi
wrapNonce:              thay đổi
kekId:                  thay đổi
```

Đây không phải “bỏ xác thực key ID”: `kekId` vẫn **được kiểm tra ở trusted key mapping** và **được wrap AAD xác thực**. Việc phân tách đúng metadata theo mục đích giúp cả integrity và rotation hoạt động nhất quán.

## 10. Lưu trữ và giao dịch nhất quán khi rewrap hàng triệu object

Một hệ thống quản lý object có thể cần migrate từ KEK version 1 sang 2, trong khi vẫn phục vụ traffic bình thường. Những trường hợp khó thường nằm ở **tính nhất quán**, không phải ở `Cipher`:

1. **Đọc snapshot/version của object:** lấy data ciphertext/tag, wrapped DEK, key ID, context và version metadata trong một phiên bản nhất quán.
2. **Authorize old unwrap và new wrap:** không chuyển tất cả object sang key mới nếu thiếu quyền/điều kiện ở một tenant. Đặt giới hạn throughput/KMS quota.
3. **Rewrap và xác minh:** dùng provider/KMS đúng key IDs; ít nhất kiểm thử decrypt một tập mẫu với new KEK theo policy. Đối với mỗi object, nếu unwrap/authentication thất bại, **không ghi đè wrapped DEK cũ**.
4. **Atomic compare-and-swap:** chỉ cập nhật `(keyId, wrappedDEK, wrapMetadata, envelopeVersion)` nếu object chưa bị ghi đồng thời hoặc có cùng ETag/version. Nếu có concurrent update, re-read record và áp dụng retry có giới hạn thay vì ghi đè dữ liệu mới.
5. **Đảm bảo khả năng khôi phục:** có state máy migrate, retry idempotent, kiểm tra checksum/record counts, ghi log không chứa key, đủ dữ liệu khôi phục nếu job bị dừng nửa chừng.
6. **Hỗ trợ đọc cả hai KEK tạm thời:** trong thời gian rollout, service phải dùng đúng key ID để giải mã object phiên bản cũ/mới; khi không còn dependency, mới thu hồi old unwrap theo kế hoạch.
7. **Backup và restore:** snapshot có key IDs/wrapped DEKs đúng version; nếu đã hủy KEK cũ, những bản backup cũ cần được xem xét để tránh mất khả năng phục hồi. Không assume object hiện tại rewrap xong là mọi replica/backups cũng xong.
8. **Xác nhận điều kiện dừng:** đối chiếu inventory và audit log, đo tỷ lệ lỗi đọc, exception theo key version; áp dụng cutover/disable old key có kế hoạch.

**Ví dụ sai:** ghi `kekId="v2"` trước, nhưng vẫn giữ `wrappedDEK` của v1; khi đọc, service chọn KEK-v2 và unwrap thất bại. Ví dụ sai khác: bọc DEK bằng v2 xong nhưng lưu object thiếu tag hoặc wrap nonce. **Nhóm trường liên quan phải cập nhật cùng nhau**.

## 11. Xử lý ngoại lệ và phân loại lỗi

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý đúng |
| --- | --- | --- |
| `AEADBadTagException` khi unwrap DEK bằng AES-GCM | Sai KEK, wrap AAD khác, nonce/tag/ciphertext wrap bị sửa hoặc cắt | Từ chối DEK; không thử sửa tag hoặc đoán key; kiểm tra metadata và source bytes nội bộ |
| `AEADBadTagException` khi giải mã data | Sai DEK, data AAD/nonce không khớp, data ciphertext/tag hỏng | Không xuất plaintext; kiểm tra object consistency, context và storage transport |
| `IllegalArgumentException` vì nonce/tag quá ngắn | Format không đủ minimum, metadata không hợp lệ | Chặn ở parser trước khi cấp phát lớn/gọi provider |
| `InvalidKeyException` khi `Cipher.init` | Key không hợp lệ, sai loại, provider/key policy không chấp nhận | Kiểm tra key type/size và policy; không fallback yếu |
| KMS báo access denied | IAM/key policy không cho phép unwrap | Từ chối và audit; **không log DEK** hay dùng một KEK local mặc định |
| KMS rate limit/timeout | Quota hoặc sự cố mạng; không liên quan trực tiếp ciphertext integrity | Retry với backoff/jitter, deadline và giới hạn; tránh giải mã sai hay leak secret |
| `kekId` không có trong registry | Metadata lỗi, key đã bị thu hồi hoặc sender không được dùng key đó | Không tải key ngoài allowlist; trả lỗi được chuẩn hóa |
| Rewrap thành công nhưng đọc lại bằng new KEK fail | Mismatch wrap AAD, key ID, format/serialization hoặc update không atomic | Chặn rollout, kiểm tra theo record version, rollback có kiểm soát |
| Decrypt thành công nhưng object không đúng tenant | Thiếu authorization/context binding; lỗi thiết kế logic | Kiểm tra quyền dữ liệu, tenant ID trong AAD và trusted resource mapping |
| Chỉ xóa KEK cũ, sau đó không restore được backup | Các bản sao cũ vẫn phụ thuộc KEK đã xóa | Diễn tập restore trước key deletion; quản lý retention theo phiên bản |

**Lỗi từ tầng bọc và lỗi từ tầng dữ liệu không nên bị trộn trong monitoring nội bộ**, nhưng phản hồi public không được tiết lộ chi tiết về key material hoặc trạng thái xác thực làm tăng lợi thế của đối thủ. Không giải mã một phần data khi tag chưa được xác nhận; không thử hoán đổi key ID/nonce/tag theo danh sách cho đến khi “giải được”.

## 12. Những câu hỏi thiết kế thường gặp

### 12.1 Có bắt buộc mỗi record một DEK không?

Không tuyệt đối. Một DEK có thể phục vụ nhiều record nếu giao thức có nonce management, usage limits và threat model đầy đủ. Tuy nhiên **DEK riêng theo object/nhóm nhỏ** thường giúp thu hẹp phạm vi khi lộ DEK, dễ phân quyền vòng đời, xóa object và re-encrypt. Đổi lại, chi phí là số lượng wrapped DEK, metadata và KMS calls tăng. Chọn độ hạt phù hợp với dung lượng, số lượng object, tốc độ truy cập và khả năng quản lý.

### 12.2 Có nên cache plaintext DEK để giảm độ trễ không?

Caching làm giảm số lời gọi KMS nhưng **kéo dài thời gian tồn tại và phạm vi lộ DEK**. Nếu cần, phải có TTL, giới hạn entry, tenant separation, quyền process, lifecycle eviction, giới hạn debug/heap dump, audit và đánh giá nguy cơ replay/stale key policy. **Cache encrypted DEK** không có nguy cơ tương tự như cache plaintext DEK; dù vậy cache metadata cũng cần xử lý nhất quán với rotation.

### 12.3 Có thể lấy một khẩu lệnh chung làm KEK không?

Không nên coi một chuỗi cấu hình dễ đoán như `"master-password-123"` là KEK. KEK phải có entropy, key management và policy thích hợp. Nếu mô hình thực sự buộc bắt đầu từ **mật khẩu người dùng**, cần password-based KDF (như Argon2id/scrypt/PBKDF2 theo kiến trúc và môi trường), salt, chi phí chống đoán và thiết kế phù hợp; không đơn giản gọi `password.getBytes()` làm AES key. Mô hình này khác với KMS-backed KEK có entropy ngẫu nhiên.

### 12.4 KEK và DEK có thể đều là AES-256 không?

**Có**, cùng loại thuật toán AES nhưng là **hai khóa độc lập với vai trò khác nhau**. Cụm “tách khóa” không chỉ là thay tên biến: phải sinh key material độc lập, giới hạn truy cập và chức năng, bảo vệ KEK bằng biện pháp mạnh hơn, quản lý version và tránh dùng lại cùng một key cho data và wrap. Nếu cả hai là một mảng 32 byte giống hệt thì bạn chưa đạt được key separation.

### 12.5 Bọc DEK với public key của người nhận được không?

Có, nếu thiết kế dùng **RSA-OAEP** hoặc KEM/HPKE được chuẩn hóa, bạn có thể mã hóa/bọc DEK ngắn cho public key người nhận; chỉ bên có private key mới unwrap được. Khi này “KEK” có thể là khái niệm **key-encryption mechanism** bất đối xứng thay vì một khóa AES đối xứng. Nhưng vẫn cần authentic public key của người nhận, đúng scheme, tham số OAEP/KEM và chính sách bảo vệ private key; **đừng dùng RSA raw hoặc tự chế hybrid protocol**.

### 12.6 Có thể dùng “wrapped DEK” làm token cấp quyền không?

**Không.** Wrapped DEK là ciphertext của key material, không phải capability token tự chứng thực quyền người gọi. Hệ thống vẫn phải xác thực người dùng/service, authorize object, giới hạn KMS unwrap và ràng buộc tenant/context. Ai được đọc envelope thường có thể thấy wrapped DEK; điều này **không đồng nghĩa** họ có quyền KMS để mở nó.

### 12.7 Crypto-erasure có đủ để xóa dữ liệu không?

Ý tưởng **crypto-erasure** là xóa vĩnh viễn material cần để giải mã; nếu mỗi object có DEK riêng và không còn bản sao DEK/wrapped DEK có thể unwrap, dữ liệu có thể trở nên không thể khôi phục về mặt mật mã. Nhưng không thể khẳng định hoàn tất chỉ vì xóa một row: cần đánh giá DEK cache, KEK version còn sống, snapshots, backups, bản sao plaintext, log và các máy chủ đã giải mã trước đó. Hủy KEK dùng chung để xóa một object có thể **vô tình xóa khả năng giải mã của toàn bộ object khác**.

### 12.8 Envelope encryption có tự làm dữ liệu “end-to-end encrypted” không?

Không. Nếu server xử lý plaintext DEK và plaintext data, server nằm trong vùng tin cậy của hệ thống. End-to-end encryption có mô hình key custody và endpoint khác; envelope encryption có thể là một thành phần nhưng không tự tạo E2EE. Cần chỉ rõ **ai có thể unwrap, ai nhìn thấy plaintext, ở đâu key được giải mã**, chứ không chỉ đếm số lớp encryption.

## 13. Checklist production và kiểm thử

### Bảo mật khóa

- [ ] DEK và KEK khác nhau cả về **key material, role, quyền sử dụng và vòng đời**.
- [ ] Plaintext DEK chỉ tồn tại tạm thời trong ranh giới được kiểm soát; KEK nằm trong KMS/HSM/keystore theo policy.
- [ ] CSPRNG đúng, nonce GCM **không tái sử dụng dưới cùng khóa** và có quản lý usage limits.
- [ ] Có trusted key ID registry; tenant, object, purpose/role được bind vào context xác thực.
- [ ] Không ghi DEK/KEK/plaintext vào log, trace, metrics, exception hoặc metadata envelope.
- [ ] Giao thức không dùng ECB/raw RSA/hash làm primitive bọc khóa.

### Envelope và integrity

- [ ] Format có version, algorithm allowlist, key ID, nonce/tag và canonical byte representation.
- [ ] Data AAD ổn định theo object/tenant/purpose; wrap AAD ràng buộc key ID/context, cho phép rewrap độc lập khi đó là mục tiêu thiết kế.
- [ ] Parser chặn thiếu header/tag và giới hạn độ dài trước khi cấp phát/gọi `Cipher`.
- [ ] Đọc/ghi object và wrapped DEK nhất quán; không expose plaintext trước khi xác minh tag cả tầng unwrap lẫn tầng data.
- [ ] Có test đổi 1 bit ciphertext/tag/nonce, dùng KEK sai, sai object ID/tenant/AAD, thiếu tag, thay key ID, sai version.
- [ ] Đối với KMS, kiểm thử key permission, status, quota/timeout, key rotation và policy revocation.

### Rotation và vận hành

- [ ] Phân biệt **KEK rewrap** và **DEK re-encryption**, có runbook riêng.
- [ ] Rewrap cập nhật atomic `wrappedDEK + keyId + wrap metadata` và có ETag/concurrency guard.
- [ ] Tạm hỗ trợ đúng key versions cần đọc; xóa khóa cũ **chỉ sau** khi xác minh các object, backup và restore path.
- [ ] Có migration metrics, audit trail, batch size, retry idempotent và rollback.
- [ ] Có kế hoạch incident response nếu KEK/DEK bị lộ, gồm bản sao lịch sử và backup.

## 14. Bài tập thực hành

1. Vẽ sơ đồ envelope cho hệ thống lưu hóa đơn của ba tenant. Chọn một DEK mỗi invoice hay mỗi tenant? KEK ở cấp nào? Giải thích trade-off về KMS calls và phạm vi lộ khóa.
2. Chạy `EnvelopeEncryptionDemo.java`. Chỉ ra chỗ DEK được sinh, dùng mã hóa dữ liệu, bọc, unwrap và xóa tạm. KEK có bao giờ trực tiếp mã hóa `plaintext` ban đầu không?
3. Tại sao test `Wrong object ID rejected` thành công dù `objectId` không nằm trong plaintext? Nếu lấy object ID tùy ý từ payload rồi dùng làm AAD, rủi ro identity binding còn gì?
4. Thêm `tenantId` vào `associatedData` bằng length prefix. Tạo test tráo wrapped DEK giữa hai tenant khác nhau rồi chứng minh không thể giải mã sai context.
5. Phân biệt `Rewrap keeps data bytes: true / true` với DEK rotation. Vì sao rewrap **không thay data ciphertext/tag** nhưng đổi DEK thường phải thay chúng?
6. Giả sử công ty làm lộ KEK-v1 và attacker từng lưu snapshot của `wrappedDEK-v1`. Rewrap record hiện tại sang v2 có làm snapshot cũ mất giá trị không? Hãy viết kế hoạch xử lý sự cố.
7. Xây dựng mô hình database với `object_version`, `kek_id`, `wrapped_dek`, `wrap_nonce`, `data_nonce` và `data_ciphertext_and_tag`. Phác thảo câu lệnh cập nhật compare-and-swap cho rewrap khi có writer đồng thời.
8. Thiết kế thử nghiệm KMS: unwrap permission denied, key rotation, key disabled, old backup restore, KMS unavailable. Chỉ rõ tình huống nào nên retry, tình huống nào phải fail closed.
9. Giải thích vì sao cùng một mã `AES/GCM/NoPadding` được demo dùng cho hai vai trò khác nhau vẫn là **key separation** và vì sao không nên reuse nonce dưới cùng KEK.
10. Nếu DEK của một object cần xóa vĩnh viễn, những bản sao plaintext key/encrypted key, backup/cache/snapshot nào phải xét trước khi tuyên bố crypto-erasure đã hoàn tất?

## Tài liệu tham khảo

- [NIST SP 800-38D — GCM/GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): yêu cầu về authenticated encryption, IV/nonce và tag.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): thuật ngữ, key management, lifecycle và cryptoperiod.
- [RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm](https://www.rfc-editor.org/rfc/rfc3394): phương pháp bọc khóa AES.
- [RFC 5649 — AES Key Wrap with Padding Algorithm](https://www.rfc-editor.org/rfc/rfc5649): biến thể có padding phục vụ key material độ dài tổng quát hơn.
- [Java SE 17 — `Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `AES/GCM/NoPadding`, `updateAAD`, `doFinal`, authentication failure và `WRAP_MODE`.
- [Java SE 17 — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tag length tính bằng bit và IV/nonce.
- [Java SE 17 — `KeyGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): sinh khóa AES bằng provider.
- [Java SE 17 — `SecretKeySpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html): khóa byte được đưa vào JCE; chỉ là wrapper trong bộ nhớ, không thay thế KMS.
- [Java SE 17 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): providers, key generation, Cipher/JCE và kiến trúc dịch vụ.
