# Xoay key với write-new read-old

Bài thực hành này hướng dẫn triển khai chiến lược **write-new read-old** khi xoay khóa mã hóa dữ liệu. Sau khi phát hành key version mới, mọi dữ liệu mới được mã hóa bằng version mới; ứng dụng vẫn đọc được ciphertext được tạo bằng version cũ thông qua metadata lưu cùng dữ liệu. Dữ liệu cũ được migrate dần, sau đó version cũ mới được đưa khỏi trạng thái có thể giải mã và cuối cùng được hủy khi không còn dependency.

Chiến lược này giúp rotation không buộc phải mã hóa lại toàn bộ dữ liệu trong cùng một thời điểm. Nó cũng tránh downtime nếu reader đã hỗ trợ nhiều version trước khi writer chuyển sang version mới. Tuy nhiên, việc giữ key cũ để đọc tạo ra một khoảng thời gian mà nhiều key version cùng có thể giải mã dữ liệu; khoảng thời gian đó cần được giới hạn và kiểm toán.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Thực hành tổng hợp**. Bài kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán với vòng đời tạo, cấp phát, lưu trữ, sử dụng, backup, restore, xoay vòng, thu hồi và hủy khóa.

## 1. Mục tiêu thực hành

Sau bài lab, bạn có thể:

- Gắn key ID và version vào metadata của ciphertext.
- Mã hóa dữ liệu mới bằng write key hiện hành.
- Đọc dữ liệu cũ bằng đúng key version được ghi trong metadata.
- Triển khai reader hỗ trợ đồng thời version cũ và mới.
- Chuyển writer sang version mới mà không làm mất khả năng đọc.
- Re-encrypt dữ liệu cũ theo lô và xác minh kết quả.
- Phát hiện ciphertext bị sửa hoặc metadata bị tráo.
- Chỉ retire key cũ sau khi xác minh hết dependency.
- Phân biệt rotation DEK với rewrap khi rotation KEK.

## 2. Kịch bản và giả định

Một ứng dụng lưu dữ liệu đơn hàng được mã hóa bằng AES-GCM. Ban đầu, ứng dụng dùng key logic orders-data-aes version 1. Security team yêu cầu thay key theo cryptoperiod và tạo version 2.

Trạng thái ban đầu:

| Thành phần | Trạng thái |
|---|---|
| Active write key | orders-data-aes, version 1 |
| Readable keys | Version 1 |
| Ciphertext hiện có | Được mã hóa bằng version 1 |
| Metadata | Chưa có version mới |

Trạng thái sau khi cutover:

| Thành phần | Trạng thái |
|---|---|
| Active write key | orders-data-aes, version 2 |
| Readable keys | Version 1 và 2 |
| Ciphertext mới | Version 2 |
| Ciphertext cũ | Vẫn đọc bằng version 1 cho tới khi migrate |

Lab dùng Java 17, AES-256-GCM và key ring trong memory để minh họa. Đây là mô hình học tập; key trong production phải được quản lý bởi KMS/HSM hoặc key store được phê duyệt. Không dùng Map trong JVM làm kho khóa bền vững cho hệ thống thật.

## 3. Quy tắc cốt lõi: write-new, read-old

Reader cần chọn key theo metadata của từng ciphertext. Writer luôn chọn key version active:

- **write:** chỉ dùng version mới đã được kích hoạt.
- **read:** chấp nhận các version cũ còn được phép đọc.
- **migrate:** đọc bằng version ghi trên ciphertext, mã hóa lại bằng active write version.
- **retire:** loại key cũ khỏi khả năng đọc sau khi xác minh hết dependency.

~~~mermaid
flowchart TD
    A["Ciphertext record"] --> B["Đọc keyId + keyVersion"]
    B --> C["Resolve đúng key version"]
    C --> D["Decrypt và xác thực"]
    E["New write request"] --> F["Active write key v2"]
    F --> G["Encrypt dữ liệu mới"]
    G --> H["Lưu ciphertext + metadata v2"]
    D --> I["Legacy plaintext"]
    I --> J["Re-encrypt bằng active v2"]
    J --> K["Ghi record mới có điều kiện"]
    K --> L["Verify và cập nhật inventory"]
~~~

Không thử lần lượt tất cả key cho tới khi decrypt thành công. Cách đó làm mờ lỗi metadata, tăng chi phí, tạo side channel và có thể khiến ciphertext bị xử lý bằng key ngoài dự kiến. Key ID/version là một phần của định dạng dữ liệu và phải được xác thực.

## 4. Vì sao phải lưu key ID và version?

Ciphertext không tự cho biết key nào đã mã hóa nó. Nếu chỉ lưu nonce và ciphertext, ứng dụng có thể không xác định được key cần dùng sau nhiều lần rotation.

Một envelope nên có metadata tối thiểu:

| Field | Mục đích |
|---|---|
| formatVersion | Phiên bản định dạng dữ liệu |
| keyId | Định danh logic của key |
| keyVersion | Phiên bản key đã mã hóa dữ liệu |
| algorithm | Thuật toán/profile cần dùng; phải khớp allowlist của format |
| nonce | Nonce/IV của operation AEAD |
| ciphertext | Ciphertext kèm authentication tag |
| createdAt | Thời điểm tạo để phục vụ lifecycle/audit |

Trong lab, keyId, keyVersion, formatVersion và algorithm được đưa vào Additional Authenticated Data (AAD). Khi metadata bị sửa, tag xác thực không còn hợp lệ. createdAt là metadata phục vụ inventory/audit; nếu cần chống sửa đổi, hãy đưa giá trị đó vào AAD hoặc bảo vệ bằng integrity mechanism riêng.

Không đưa key bytes, password, PIN hoặc token vào metadata. Metadata không bí mật nhưng cần bảo vệ tính toàn vẹn và liên kết với đúng record/tenant.

## 5. Chuẩn bị project Java

Tạo project Java 17 hoặc mới hơn. Lab không cần thư viện ngoài:

~~~text
key-rotation-lab/
  src/
    KeyRotationLab.java
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -d out src/KeyRotationLab.java
java -cp out KeyRotationLab
~~~

Nếu dùng IDE, tạo class KeyRotationLab và dán chương trình hoàn chỉnh ở mục 12. Không đưa key hoặc password thật vào source code.

## 6. Tạo key version 1

Bước đầu, tạo một AES key và đăng ký nó dưới định danh logic cùng version:

~~~java
KeyRef v1 = new KeyRef("orders-data-aes", 1);
ring.add(v1, generateAesKey());
ring.activateForWrite(v1);
~~~

KeyRef là cặp (keyId, version). Không dùng alias đơn lẻ làm định danh vĩnh viễn nếu alias có thể được trỏ sang version khác. Một version đã được dùng để mã hóa dữ liệu phải được giữ nguyên identity trong inventory.

## 7. Mã hóa dữ liệu và lưu metadata

Writer lấy active key từ key ring, tạo nonce mới cho AES-GCM, ràng buộc record ID và tenant ID vào AAD rồi lưu envelope:

~~~java
Envelope envelope = encrypt(
        ring,
        "order-1001",
        "tenant-a",
        "order total=125000"
                .getBytes(StandardCharsets.UTF_8));
~~~

Trong production, recordId và tenantId phải lấy từ context đã xác thực, không tin giá trị tùy ý do caller gửi. Dùng AAD để chống việc chuyển ciphertext từ record hoặc tenant này sang record khác.

## 8. Reader chọn đúng key version

Reader lấy keyId và keyVersion từ envelope rồi resolve chính xác key tương ứng:

~~~java
byte[] plaintext = decrypt(
        ring,
        "order-1001",
        "tenant-a",
        envelope);
~~~

Nếu key version không tồn tại, reader phải trả lỗi rõ ràng và fail closed. Không được thử active key thay thế hoặc bỏ qua xác thực GCM. Nếu ciphertext bị sửa, Cipher.doFinal sẽ phát hiện tag không hợp lệ và không được trả plaintext cho nghiệp vụ.

## 9. Tạo version 2 và chuyển writer

Tạo key mới, phân phối tới các reader và chỉ sau đó mới kích hoạt làm write key:

~~~java
KeyRef v2 = new KeyRef("orders-data-aes", 2);
ring.add(v2, generateAesKey());
ring.activateForWrite(v2);
~~~

Từ thời điểm cutover, mọi lần gọi encrypt sẽ ghi keyVersion=2. Reader vẫn giữ version 1 để đọc dữ liệu cũ. Việc đổi active write key không tự động migrate ciphertext đã lưu.

Trong triển khai nhiều instance, không switch writer trước khi tất cả reader hỗ trợ version mới và đã nhận key v2. Nếu instance cũ không biết version 2, nó có thể không đọc được dữ liệu mới do instance khác tạo ra.

## 10. Migrate dữ liệu cũ

Migration đọc từng record bằng key version ghi trong envelope, mã hóa lại bằng active write key rồi cập nhật record. Không tạo plaintext file trung gian.

Quy trình:

1. Lấy một batch có giới hạn.
2. Đọc record và version hiện tại.
3. Decrypt bằng key version cũ được metadata chỉ định.
4. Encrypt plaintext bằng active write key.
5. Ghi envelope mới bằng conditional update/CAS.
6. Xác minh version và khả năng decrypt.
7. Ghi metric/audit cho thành công, bỏ qua hoặc lỗi.
8. Tiếp tục batch tiếp theo theo giới hạn tải.

Nếu record đã được ứng dụng cập nhật đồng thời, migration phải phát hiện conflict và đọc lại record mới nhất. Không ghi đè một bản ghi mới bằng plaintext cũ vừa đọc.

## 11. Kiểm soát đồng thời và idempotency

Giả sử worker migration đọc record version 1. Trong lúc worker đang decrypt, request người dùng cập nhật record và writer đã mã hóa version 2. Nếu worker ghi kết quả cũ mà không kiểm tra, dữ liệu mới có thể bị ghi đè.

Một cách xử lý là optimistic concurrency:

~~~sql
UPDATE encrypted_records
SET key_version = :new_key_version,
    nonce = :new_nonce,
    ciphertext = :new_ciphertext,
    record_revision = record_revision + 1
WHERE record_id = :record_id
  AND record_revision = :revision_read;
~~~

Nếu số dòng được cập nhật bằng 0, record đã thay đổi; worker bỏ kết quả vừa tạo, đọc lại và quyết định migrate lại. Ghi nhận trạng thái migration theo record/version để job có thể chạy lại an toàn.

Migration phải idempotent: chạy lại không làm hỏng record đã migrate và không tạo plaintext artifact. Dùng checkpoint, batch ID và retry có giới hạn.

## 12. Chương trình Java hoàn chỉnh

Chương trình sau minh họa key ring hai version, AES-GCM, AAD, write-new/read-old, migration và kiểm tra tampering. Key được giữ trong memory để dễ quan sát; chương trình không tạo file keystore hay gọi KMS.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyRotationLab {
    private static final int FORMAT_VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final SecureRandom RANDOM = new SecureRandom();

    record KeyRef(String keyId, int version) {
        KeyRef {
            Objects.requireNonNull(keyId);
            if (keyId.isBlank() || version < 1) {
                throw new IllegalArgumentException("Invalid key reference");
            }
        }
    }

    record Envelope(
            int formatVersion,
            String keyId,
            int keyVersion,
            String algorithm,
            byte[] nonce,
            byte[] ciphertext) {
        Envelope {
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(algorithm);
            nonce = nonce.clone();
            ciphertext = ciphertext.clone();
        }

        @Override
        public byte[] nonce() {
            return nonce.clone();
        }

        @Override
        public byte[] ciphertext() {
            return ciphertext.clone();
        }
    }

    static final class KeyRing {
        private final Map<KeyRef, SecretKey> keys = new HashMap<>();
        private KeyRef activeWriteKey;

        synchronized void add(KeyRef ref, SecretKey key) {
            Objects.requireNonNull(ref);
            Objects.requireNonNull(key);
            if (keys.putIfAbsent(ref, key) != null) {
                throw new IllegalStateException("Key version already exists");
            }
        }

        synchronized void activateForWrite(KeyRef ref)
                throws GeneralSecurityException {
            if (!keys.containsKey(ref)) {
                throw new GeneralSecurityException("Write key is unavailable");
            }
            activeWriteKey = ref;
        }

        synchronized KeyRef activeWriteKey() throws GeneralSecurityException {
            if (activeWriteKey == null) {
                throw new GeneralSecurityException("No active write key");
            }
            return activeWriteKey;
        }

        synchronized SecretKey require(KeyRef ref)
                throws GeneralSecurityException {
            SecretKey key = keys.get(ref);
            if (key == null) {
                throw new GeneralSecurityException(
                        "Key version unavailable: " + ref.keyId()
                                + " v" + ref.version());
            }
            return key;
        }

        synchronized void retire(KeyRef ref)
                throws GeneralSecurityException {
            if (ref.equals(activeWriteKey)) {
                throw new GeneralSecurityException(
                        "Cannot retire the active write key");
            }
            if (keys.remove(ref) == null) {
                throw new GeneralSecurityException("Key version not found");
            }
        }
    }

    static SecretKey generateAesKey() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    static byte[] aad(
            int formatVersion,
            String recordId,
            String tenantId,
            String keyId,
            String algorithm,
            int keyVersion) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(formatVersion);
        writeField(out, recordId);
        writeField(out, tenantId);
        writeField(out, keyId);
        writeField(out, algorithm);
        out.writeInt(keyVersion);
        out.flush();
        return bytes.toByteArray();
    }

    private static void writeField(DataOutputStream out, String value)
            throws IOException {
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(encoded.length);
        out.write(encoded);
    }

    static Envelope encrypt(
            KeyRing ring,
            String recordId,
            String tenantId,
            byte[] plaintext) throws GeneralSecurityException, IOException {
        KeyRef ref = ring.activeWriteKey();
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(
                Cipher.ENCRYPT_MODE,
                ring.require(ref),
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(
                FORMAT_VERSION, recordId, tenantId,
                ref.keyId(), TRANSFORMATION, ref.version()));

        byte[] ciphertext = cipher.doFinal(plaintext);
        return new Envelope(
                FORMAT_VERSION, ref.keyId(), ref.version(),
                TRANSFORMATION, nonce, ciphertext);
    }

    static byte[] decrypt(
            KeyRing ring,
            String recordId,
            String tenantId,
            Envelope envelope) throws GeneralSecurityException, IOException {
        if (envelope.formatVersion() != FORMAT_VERSION
                || !TRANSFORMATION.equals(envelope.algorithm())
                || envelope.nonce().length != NONCE_BYTES
                || envelope.ciphertext().length < TAG_BITS / 8) {
            throw new GeneralSecurityException("Invalid envelope format");
        }

        KeyRef ref = new KeyRef(envelope.keyId(), envelope.keyVersion());
        Cipher cipher = Cipher.getInstance(envelope.algorithm());
        cipher.init(
                Cipher.DECRYPT_MODE,
                ring.require(ref),
                new GCMParameterSpec(TAG_BITS, envelope.nonce()));
        cipher.updateAAD(aad(
                envelope.formatVersion(), recordId, tenantId,
                envelope.keyId(), envelope.algorithm(), envelope.keyVersion()));
        return cipher.doFinal(envelope.ciphertext());
    }

    static Envelope reencrypt(
            KeyRing ring,
            String recordId,
            String tenantId,
            Envelope oldEnvelope)
            throws GeneralSecurityException, IOException {
        byte[] plaintext = decrypt(ring, recordId, tenantId, oldEnvelope);
        try {
            return encrypt(ring, recordId, tenantId, plaintext);
        } finally {
            Arrays.fill(plaintext, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyRing ring = new KeyRing();
        KeyRef v1 = new KeyRef("orders-data-aes", 1);
        ring.add(v1, generateAesKey());
        ring.activateForWrite(v1);

        Map<String, Envelope> store = new LinkedHashMap<>();
        store.put("order-1001", encrypt(
                ring, "order-1001", "tenant-a",
                "total=125000".getBytes(StandardCharsets.UTF_8)));
        store.put("order-1002", encrypt(
                ring, "order-1002", "tenant-a",
                "total=250000".getBytes(StandardCharsets.UTF_8)));

        // Giữ snapshot để kiểm tra behavior sau retirement trong lab.
        Envelope oldSnapshot = store.get("order-1001");

        KeyRef v2 = new KeyRef("orders-data-aes", 2);
        ring.add(v2, generateAesKey());
        ring.activateForWrite(v2);

        // Reader vẫn đọc ciphertext cũ bằng version 1.
        byte[] oldPlaintext = decrypt(
                ring, "order-1001", "tenant-a", oldSnapshot);
        if (!Arrays.equals(
                oldPlaintext, "total=125000".getBytes(StandardCharsets.UTF_8))) {
            throw new IllegalStateException("Legacy read failed");
        }
        Arrays.fill(oldPlaintext, (byte) 0);

        // Mọi write mới kể từ cutover đều dùng version 2.
        store.put("order-1003", encrypt(
                ring, "order-1003", "tenant-a",
                "total=99000".getBytes(StandardCharsets.UTF_8)));

        // Migrate các record còn dùng version cũ.
        for (String recordId : new ArrayList<>(store.keySet())) {
            Envelope current = store.get(recordId);
            if (current.keyVersion() != v2.version()) {
                Envelope migrated = reencrypt(
                        ring, recordId, "tenant-a", current);
                store.put(recordId, migrated);
            }
        }

        // Xác minh mọi record đang dùng version 2 và đọc được.
        for (Map.Entry<String, Envelope> entry : store.entrySet()) {
            if (entry.getValue().keyVersion() != v2.version()) {
                throw new IllegalStateException("Old version remains");
            }
            byte[] value = decrypt(
                    ring, entry.getKey(), "tenant-a", entry.getValue());
            Arrays.fill(value, (byte) 0);
        }

        // Tampering phải làm AES-GCM authentication thất bại.
        Envelope sample = store.get("order-1003");
        byte[] damaged = sample.ciphertext();
        damaged[0] ^= 0x01;
        Envelope tampered = new Envelope(
                sample.formatVersion(), sample.keyId(), sample.keyVersion(),
                sample.algorithm(), sample.nonce(), damaged);
        try {
            decrypt(ring, "order-1003", "tenant-a", tampered);
            throw new IllegalStateException("Tampering was not detected");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampering rejected");
        }

        // Chỉ retire v1 sau khi lab đã migrate mọi record và xác minh xong.
        ring.retire(v1);
        try {
            decrypt(ring, "order-1001", "tenant-a", oldSnapshot);
            throw new IllegalStateException("Retired key was still usable");
        } catch (GeneralSecurityException expected) {
            System.out.println("Retired version rejected");
        }

        System.out.println("Active write version: " + ring.activeWriteKey().version());
        System.out.println("Stored records: " + store.size());
        System.out.println("All current records use version 2");
    }
}
~~~

Kết quả mong đợi:

~~~text
Tampering rejected
Retired version rejected
Active write version: 2
Stored records: 3
All current records use version 2
~~~

KeyRing trong ví dụ giữ SecretKey trong heap và retire loại entry khỏi map. Đây chỉ là mô phỏng. Phương thức retire trong lab không tự kiểm tra database, backup, archive hoặc consumer; main chỉ gọi nó sau khi các record mẫu đã migrate. Production phải có retirement gate độc lập dựa trên inventory/dependency scan, retention và approval. Thay key ring bằng adapter KMS/HSM; không export key material về ứng dụng chỉ để tạo key ring trong memory.

Ví dụ dùng nonce ngẫu nhiên 96 bit để đơn giản hóa lab. AES-GCM yêu cầu nonce không lặp với cùng key. Production cần thiết kế nonce allocation và giới hạn số lần encrypt trên mỗi key; không coi nonce ngẫu nhiên là nguồn vô hạn cho workload có volume lớn. Phải tham khảo giới hạn và hướng dẫn của cryptographic provider/KMS đang dùng.

## 13. Tại sao phải đưa metadata vào AAD?

AES-GCM xác thực cả ciphertext và AAD. AAD không được mã hóa nhưng được bảo vệ tính toàn vẹn. Trong lab, AAD chứa:

- Format version.
- Record ID.
- Tenant ID.
- Key ID.
- Algorithm/profile.
- Key version.

Nếu attacker thay keyVersion=1 thành 2, hoặc copy envelope từ tenant A sang tenant B, AAD tính lại sẽ khác và GCM tag không hợp lệ. Cần dùng encoding có cấu trúc, ví dụ field length-prefix như DataOutputStream trong lab; tránh ghép chuỗi bằng delimiter có thể xuất hiện trong dữ liệu.

Metadata vẫn cần được kiểm soát ở tầng storage và API. AAD bảo vệ việc giải mã phát hiện thay đổi, nhưng không ngăn attacker xóa record, replay một record hợp lệ hoặc sửa các field không được đưa vào AAD.

## 14. Quy trình rollout nhiều instance

Không triển khai rotation bằng cách đổi config writer trên tất cả instance cùng lúc mà không kiểm soát reader compatibility. Trình tự an toàn:

1. **Expand reader:** phát hành phiên bản ứng dụng có thể đọc version 1 và version 2; writer vẫn dùng version 1.
2. **Provision v2:** tạo key version 2 trong KMS/HSM và cấp quyền đọc cần thiết cho các workload.
3. **Verify readiness:** xác nhận mọi instance cần thiết đã nhận metadata/key reference v2 và đọc thử ciphertext test.
4. **Switch writer:** đổi active write version sang v2 bằng một control plane có audit.
5. **Observe:** kiểm tra mọi write mới mang version 2; phát hiện instance cũ còn ghi version 1.
6. **Migrate:** re-encrypt dữ liệu cũ theo batch và conditional update.
7. **Verify dependencies:** kiểm tra database, cache, queue, archive, replica, backup và offline export.
8. **Restrict old key:** chuyển v1 sang decrypt-only hoặc policy tương đương khi không còn writer hợp lệ.
9. **Retire:** chỉ loại v1 khỏi read path sau khi retention và recovery dependency đã hết.
10. **Destroy:** thực hiện destruction theo quy trình riêng, có approval và audit.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Ring as KMS/Key service
    participant DB as Data store
    App->>Ring: Provision v1
    App->>DB: Write ciphertext v1
    App->>Ring: Provision v2
    Note over App: Deploy dual-read support
    App->>Ring: Set active write v2
    App->>DB: Write new ciphertext v2
    App->>DB: Read legacy ciphertext v1
    App->>Ring: Resolve v1 for decrypt
    App->>DB: Re-encrypt legacy record as v2
    Note over App,DB: Verify no v1 references remain
    App->>Ring: Restrict/retire v1 after approval
~~~

## 15. Migration lazy và migration batch

Có hai cách migrate:

| Cách | Cách làm | Ưu điểm | Rủi ro/cần kiểm soát |
|---|---|---|---|
| Lazy migration | Khi đọc record cũ, re-encrypt và ghi version mới | Phân bổ tải theo traffic tự nhiên | Record ít truy cập có thể giữ key cũ rất lâu |
| Batch migration | Worker quét toàn bộ record theo batch | Có tiến độ và coverage đo được | Tạo tải lớn, cần concurrency control và checkpoint |

Có thể kết hợp: lazy migration cho record thường truy cập và batch migration cho phần còn lại. Cần có deadline rõ cho việc loại bỏ version cũ; nếu không, read-old có thể tồn tại vô hạn.

## 16. Theo dõi tiến độ migration

Các metric hữu ích:

- Tổng số record theo key version.
- Số record đã migrate, còn lại, lỗi và conflict.
- Tỷ lệ write mới dùng active version.
- Số instance còn cấu hình writer cũ.
- Batch duration, throughput và retry count.
- Decrypt failure, authentication failure và missing-key error.
- Số backup/archive còn tham chiếu version cũ.
- Tuổi của ciphertext cũ nhất.

Ví dụ báo cáo:

| Key version | Record count | Trạng thái |
|---|---:|---|
| v1 | 1,200 | Đang migrate |
| v2 | 98,800 | Active write/read |
| Unknown | 0 | Không được phép |

Không suy ra đã migrate hết chỉ từ số record trong database chính. Cần tính cả replica, object storage, event queue, export, backup và bản sao offline thuộc phạm vi retention.

## 17. Xử lý lỗi trong migration

Phân loại lỗi để quyết định retry:

| Lỗi | Cách xử lý |
|---|---|
| KMS timeout/5xx | Retry bounded với backoff và jitter |
| Throttling | Giảm concurrency, tôn trọng retry-after nếu có |
| AccessDenied | Dừng batch liên quan, sửa quyền qua change process |
| Key version missing | Không thể migrate; điều tra inventory/recovery |
| GCM tag invalid | Cách ly record, điều tra corruption/tampering |
| CAS conflict | Đọc lại record mới và đánh giá lại |
| Storage unavailable | Giữ nguyên bản cũ, retry khi phục hồi |
| Invalid metadata | Quarantine, không đoán key version |

Không xóa ciphertext cũ trước khi ciphertext mới được ghi bền vững và xác minh. Nếu migrate thất bại giữa chừng, record cũ vẫn phải đọc được.

## 18. Rollback và cutover

Trước khi migrate dữ liệu, có thể rollback writer về v1 nếu v1 vẫn được phép encrypt và chưa có incident compromise. Sau khi đã ghi v2, reader dual-read vẫn có thể đọc cả hai version.

Rollback plan cần trả lời:

- Có thể bật lại writer v1 trong bao lâu?
- Version v1 có còn được phép encrypt theo policy không?
- Reader hiện tại có đọc được cả v1 và v2 không?
- Record đã migrate v2 có cần chuyển ngược không? Thường không cần nếu reader vẫn hỗ trợ v2.
- Có change log và audit cho active write key không?

Nếu rotation được kích hoạt do nghi ngờ v1 bị compromise, không rollback writer về v1 chỉ để khôi phục availability. Khi đó, cần incident response và giữ v1 chỉ trong phạm vi cần thiết để xử lý dữ liệu lịch sử theo policy.

## 19. Retire, revoke và destroy key cũ

Ba hành động có ý nghĩa khác nhau:

- **Retire from write:** không còn mã hóa dữ liệu mới bằng version cũ.
- **Decrypt-only/restricted:** giữ khả năng giải mã dữ liệu lịch sử nhưng chặn operation không cần thiết.
- **Revoke/disable:** ngăn một số hoặc toàn bộ operation theo policy và backend.
- **Destroy:** hủy vật liệu khóa theo quy trình; có thể không khôi phục được.

Trước khi destroy v1, xác nhận:

- Không còn record hiện hành tham chiếu v1.
- Không còn backup, archive hoặc snapshot cần v1 để restore.
- Không còn replica, queue hoặc consumer offline chứa ciphertext v1.
- Recovery test với v2 đã đạt.
- Retention/legal hold đã được đáp ứng.
- Owner và approver chấp thuận destruction.
- Audit evidence và inventory được cập nhật.

Không đồng nhất “không thấy record trong database chính” với “key không còn cần thiết”. Key destruction là quyết định lifecycle riêng và có thể ảnh hưởng không thể đảo ngược tới khả năng đọc dữ liệu.

## 20. Phân biệt rotation DEK và rotation KEK

Write-new/read-old trong lab áp dụng trực tiếp cho key mã hóa dữ liệu (DEK hoặc data-encryption key). Nếu xoay key-encryption key (KEK) trong envelope encryption, quy trình thường khác:

| Rotation | Dữ liệu cần thay đổi | Công việc |
|---|---|---|
| DEK rotation | Ciphertext dữ liệu | Decrypt bằng DEK cũ, encrypt bằng DEK mới |
| KEK rotation | Wrapped DEK | Unwrap DEK bằng KEK cũ, wrap DEK bằng KEK mới |
| Signing key rotation | Key tạo chữ ký | Ký mới bằng private key mới; giữ public key/certificate cũ để verify chữ ký lịch sử theo policy |
| TLS key/certificate rotation | Identity trình trong handshake | Phát hành và rollout certificate/key mới; giữ overlap trust có kiểm soát |

Khi chỉ rotate KEK, ciphertext dữ liệu có thể giữ nguyên nếu DEK không thay đổi và wrapped DEK được cập nhật an toàn. Cần cập nhật key ID/version của KEK trong metadata và xác thực metadata đó bằng AAD hoặc cơ chế integrity phù hợp.

## 21. Backup và restore trong thời gian rotation

Backup có thể chứa ciphertext cũ cùng wrapped DEK hoặc key reference cũ. Vì vậy:

- Ghi nhận key version mà mỗi backup phụ thuộc.
- Giữ key cũ ít nhất đến khi backup hết retention hoặc đã rewrap/migrate.
- Test restore từ backup được tạo trước rotation.
- Test restore từ backup được tạo trong giai đoạn dual-read.
- Test restore từ backup sau cutover.
- Không xóa KEK/DEK cũ khi bản backup hợp lệ còn cần.
- Lưu audit của restore và key version được sử dụng.

Một backup không thể giải mã sau khi key cũ bị destroy là một dạng mất dữ liệu, dù file backup vẫn tồn tại.

## 22. Kiểm thử bảo mật và tính đúng đắn

Thực hiện các test sau trong môi trường lab:

| Test | Kết quả mong đợi |
|---|---|
| Encrypt khi active v1 | Envelope ghi v1 |
| Activate v2 rồi encrypt | Envelope mới ghi v2 |
| Decrypt envelope v1 sau cutover | Đọc thành công bằng v1 |
| Decrypt envelope v2 | Đọc thành công bằng v2 |
| Sửa keyVersion trong metadata | GCM authentication fail |
| Copy envelope sang tenant khác | AAD mismatch, decrypt fail |
| Sửa ciphertext/nonce | Authentication fail |
| Key version không tồn tại | Fail closed, không thử key khác |
| Migrate record v1 | Record mới dùng v2, plaintext không đổi |
| Chạy migration lần hai | Không làm hỏng record đã migrate |
| Concurrent update trong migration | CAS conflict, không ghi đè dữ liệu mới |
| Retire v1 khi còn record v1 | Gate/policy phải chặn retirement |
| Restore backup cũ | Đọc được bằng key version còn được giữ |

Kiểm tra cả dữ liệu plaintext sau khi decrypt, metadata, audit event và trạng thái record. Không chỉ kiểm tra keyVersion == 2.

## 23. Bài tập thực hành

Hãy hoàn thành theo thứ tự:

1. Chạy chương trình Java hoàn chỉnh và xác nhận output.
2. Thêm record order-1004 khi active write key là v1.
3. Tạo v2, kích hoạt v2 và ghi thêm order-1005.
4. Chứng minh reader đọc được cả record v1 và v2.
5. Viết hàm batch migration có checkpoint cho tất cả record v1.
6. Thêm kiểm tra CAS hoặc revision để tránh ghi đè update đồng thời.
7. Thử sửa keyVersion, tenantId và ciphertext; xác nhận decrypt bị từ chối.
8. Thử retire v1 khi còn record v1 và thiết kế gate ngăn hành động.
9. Mô phỏng backup còn tham chiếu v1; chứng minh retirement bị trì hoãn.
10. Sau khi tất cả dependency được xử lý, retire v1 và kiểm tra reader fail closed với envelope cũ.

## 24. Câu hỏi tự đánh giá

1. Vì sao phải triển khai dual-read trước khi switch writer?
2. Tại sao không thử tất cả key version nếu decrypt bằng key được metadata chỉ định thất bại?
3. AAD bảo vệ những metadata nào và không bảo vệ điều gì?
4. Điều gì xảy ra nếu worker migration ghi đè một record được cập nhật đồng thời?
5. Khi nào có thể retire key cũ nhưng vẫn giữ nó cho decrypt?
6. Vì sao backup cũ có thể ngăn việc destroy key?
7. Khi rotate KEK, tại sao thường chỉ cần rewrap DEK?
8. Nếu v1 bị compromise, điều gì thay đổi trong rollback plan?

## 25. Checklist hoàn thành rotation

Trước khi đóng change:

- [ ] Reader hỗ trợ version cũ và mới đã được triển khai.
- [ ] Key version mới đã được tạo trong backend được phê duyệt.
- [ ] Key ID/version và policy đã được ghi vào inventory.
- [ ] Mọi writer đã chuyển sang version mới.
- [ ] Không còn writer cũ ghi version cũ.
- [ ] Ciphertext mới có metadata và AAD đúng.
- [ ] Migration có checkpoint, retry bounded và concurrency control.
- [ ] Record migrate được xác minh bằng decrypt.
- [ ] Không có plaintext key/data trung gian bị ghi ra disk hoặc log.
- [ ] Backup, archive, replica và consumer offline đã được kiểm kê.
- [ ] Restore test cho dữ liệu trước và sau rotation đã đạt.
- [ ] Key cũ được chuyển sang trạng thái phù hợp và có owner.
- [ ] Destruction chỉ diễn ra sau approval và hết dependency.
- [ ] Audit ghi active version change, migration, retire và destroy.
- [ ] Có rollback/incident plan nếu rotation gây lỗi.

## 26. Các lỗi thiết kế thường gặp

- Switch writer trước khi reader mới được triển khai đầy đủ.
- Chỉ lưu alias mà không lưu version bất biến.
- Thử decrypt lần lượt mọi key khi metadata sai.
- Dùng một nonce GCM lặp lại với cùng key.
- Không đưa record/tenant/key version vào AAD.
- Migrate không có CAS và làm mất update mới.
- Xóa key cũ ngay sau cutover dù backup còn phụ thuộc.
- Đánh dấu migration hoàn tất chỉ dựa trên số batch đã chạy.
- Giữ read-old vô thời hạn và không có deadline retire.
- Dùng plaintext key trong ứng dụng production thay cho KMS/HSM.
- Không kiểm tra audit và inventory sau rotation.
- Rollback về key đã bị nghi compromise.

## 27. Kết nối với KMS/HSM trong production

Khi chuyển từ lab sang production:

- KeyRing.add tương ứng với tạo/import key version hoặc đăng ký key reference trong KMS/HSM.
- activateForWrite tương ứng với cập nhật active key version trong control plane/configuration có audit.
- require tương ứng với resolve key ID/version và kiểm tra quyền operation.
- encrypt/decrypt gọi KMS data plane hoặc dùng DEK được KMS cấp trong envelope encryption.
- retire tương ứng với policy chuyển key cũ sang decrypt-only/disabled theo lifecycle.
- destroy là workflow riêng, có approval, retention check và audit.

Không lưu key bytes vào Java map trong production. Nếu dùng envelope encryption, ứng dụng có thể nhận plaintext DEK tạm thời từ KMS để mã hóa dữ liệu; DEK phải được giữ trong memory trong thời gian cần thiết, được xóa best effort và không ghi vào log/disk.

## 28. Báo cáo kết quả lab

Một báo cáo hoàn thành nên ghi:

| Hạng mục | Bằng chứng |
|---|---|
| Active write version | Metadata của record mới sau cutover |
| Dual-read | Decrypt thành công record v1 và v2 |
| Migration coverage | Số record theo version trước/sau |
| Integrity | Test tampering và AAD mismatch bị từ chối |
| Concurrency | CAS conflict không ghi đè dữ liệu mới |
| Backup dependency | Danh sách backup/version còn cần key cũ |
| Retirement gate | Bằng chứng không còn dependency trước retire |
| Audit | Event tạo v2, switch writer, migration và retire |
| Recovery | Restore test cho dữ liệu cũ và mới |

Write-new/read-old là một chiến lược chuyển đổi theo version, không phải chỉ thay một alias trong cấu hình. Reader phải hiểu version cũ và mới trước khi writer chuyển sang version mới; dữ liệu cũ cần được migrate có kiểm soát; metadata phải được xác thực; và key cũ chỉ được retire/destroy sau khi mọi record, backup và consumer đã được xử lý. Khi thực hiện đúng thứ tự, hệ thống duy trì khả năng đọc trong lúc rotation diễn ra mà vẫn có lộ trình rõ ràng để loại bỏ key version cũ.
