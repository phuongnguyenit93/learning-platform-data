# Kiểm thử sai khóa, sai dữ liệu, nonce và chứng chỉ không hợp lệ trong Java

## 1. Mục tiêu của kiểm thử âm tính

Trong mật mã ứng dụng, kiểm thử một lần mã hóa/giải mã hoặc một kết nối TLS hợp lệ chưa đủ. Hệ thống còn phải **từ chối an toàn** khi nhận khóa sai, ciphertext bị sửa, nonce không đúng, metadata bị thay đổi hoặc chứng chỉ không được tin cậy.

Bài này tập trung vào kiểm thử phòng thủ cho Java Cryptography Architecture (JCA/JCE) và TLS:

- **Sai khóa:** khóa không đúng, khóa sai độ dài, key ID không tồn tại hoặc dùng nhầm phiên bản khóa.
- **Sai dữ liệu:** ciphertext, authentication tag, Additional Authenticated Data (AAD), envelope hoặc dữ liệu bị cắt cụt.
- **Nonce:** kiểm tra độ dài, tính duy nhất theo từng khóa, cấp phát đồng thời, restart và tránh tái sử dụng.
- **Chứng chỉ:** hết hạn, chưa có hiệu lực, CA không đáng tin, thiếu intermediate, chữ ký sai, SAN không khớp hostname, Key Usage/EKU không phù hợp.
- **Hành vi khi từ chối:** không trả plaintext chưa xác thực, không ghi dữ liệu một phần, không bỏ qua kiểm tra và không fallback sang cấu hình yếu.

Ví dụ dùng **AES/GCM/NoPadding**, GCMParameterSpec, SecureRandom, PKIX và xác minh hostname HTTPS. Đây là các API hiện hành trong Java; ví dụ tương thích Java 8+ và đã chạy trên JDK 24. Không dùng DES/3DES, ECB, MD5, SHA-1, SSLv3, TLS 1.0/1.1, trust-all manager hoặc tắt kiểm tra hostname.

Một bộ kiểm thử tốt luôn có cả **positive control** (dữ liệu hợp lệ phải được chấp nhận) và **negative case** (dữ liệu lỗi phải bị từ chối). Chỉ kiểm tra “có exception” chưa đủ: còn phải xác minh hệ thống không tiết lộ dữ liệu, không ghi side effect và không chấp nhận kết quả sai.

## 2. Phân loại lỗi cần kiểm tra

| Nhóm | Ví dụ đầu vào sai | Kết quả mong đợi |
| --- | --- | --- |
| Key material | AES key sai độ dài | InvalidKeyException khi khởi tạo cipher |
| Key identity | key ID không có trong KMS/key store | Từ chối; không tự thử mọi khóa |
| Key correctness | Khóa hợp lệ về độ dài nhưng không phải khóa đã mã hóa | AEAD tag không xác thực |
| Ciphertext | Bit ciphertext bị thay đổi | AEADBadTagException |
| Authentication tag | Tag bị sửa hoặc cắt cụt | Từ chối giải mã |
| AAD | Tenant ID/record ID/version khác lúc mã hóa | Tag không hợp lệ |
| Nonce | Nonce giải mã không trùng nonce mã hóa | Tag không hợp lệ |
| Nonce reuse | Hai lần mã hóa cùng khóa dùng cùng nonce | Phát hiện ở tầng quản lý nonce; JCA không tự kiểm tra lịch sử |
| Certificate time | Expired/not-yet-valid | Từ chối |
| Certificate trust | CA không nằm trong trust anchors | PKIX path validation thất bại |
| Certificate signature | Chữ ký chứng chỉ bị thay đổi | PKIX validation thất bại |
| Host identity | SAN không khớp hostname | TLS handshake thất bại |
| Certificate usage | EKU/Key Usage không phù hợp vai trò | Từ chối theo path/algorithm policy |

Phải phân biệt **lỗi API** với **lỗi nghiệp vụ**. InvalidKeyException thường xảy ra khi khóa không phù hợp ngay lúc Cipher.init(). Còn khóa AES có độ dài hợp lệ nhưng sai nội dung có thể chỉ được phát hiện lúc xác thực tag ở doFinal().

Với GCM, sai khóa, ciphertext, tag, nonce hoặc AAD thường dẫn đến cùng một lỗi xác thực. Không nên trả thông tin quá chi tiết cho người gọi không đáng tin, vì việc phân biệt nguyên nhân có thể tạo oracle. Phía ứng dụng có thể ghi metric nội bộ đã được kiểm soát, nhưng tuyệt đối không log khóa, plaintext, token hoặc secret.

## 3. Kiến thức nền: AES-GCM và xác thực dữ liệu

AES-GCM là chế độ **authenticated encryption with associated data (AEAD)**: vừa bảo mật plaintext, vừa xác thực tính toàn vẹn của ciphertext và AAD.

Một lời gọi mã hóa:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
    Cipher.ENCRYPT_MODE,
    secretKey,
    new GCMParameterSpec(128, nonce)
);
cipher.updateAAD(aad);
byte[] ciphertextAndTag = cipher.doFinal(plaintext);
```

Các thành phần:

- **Key:** khóa AES bí mật, thường 128 hoặc 256 bit tùy policy/provider.
- **Nonce/IV:** giá trị duy nhất trong phạm vi một khóa; GCM thường dùng nonce 96 bit (12 byte).
- **Tag:** mã xác thực, ví dụ 128 bit; kết quả doFinal() thường chứa ciphertext nối với tag.
- **AAD:** dữ liệu không mã hóa nhưng được xác thực, chẳng hạn version, tenant ID, record ID hoặc metadata cần gắn với ciphertext.

AAD không bí mật. Nếu AAD bị thay đổi giữa lúc mã hóa và giải mã, xác thực phải thất bại. AAD hữu ích để ngăn ciphertext hợp lệ bị chuyển sang ngữ cảnh khác, ví dụ chuyển ciphertext của tenant A sang record của tenant B.

### 3.1. Không xử lý plaintext trước khi tag được xác thực

Với AEAD, tag được xác minh khi hoàn tất giải mã. Nếu dùng Cipher.update() theo từng phần, **không công bố hoặc xử lý plaintext trung gian như dữ liệu đáng tin** trước khi doFinal() hoàn tất thành công. Với file/stream lớn, ghi dữ liệu vào vùng staging riêng và chỉ publish sau khi xác thực thành công; nếu thất bại, xóa vùng staging theo policy.

Một lỗi nghiêm trọng là gửi dữ liệu giải mã từng phần cho parser hoặc ghi vào database trước khi tag cuối cùng được kiểm tra. Khi tag sai, dữ liệu đã có thể tạo side effect dù toàn bộ thông điệp không hợp lệ.

### 3.2. Tag và replay

Bài dùng GCMParameterSpec(128, nonce) cho tag 128 bit. Không tự giảm tag length để tiết kiệm vài byte nếu không có thiết kế và policy được phê duyệt.

GCM **không tự chống replay**. Một ciphertext hợp lệ có thể được gửi lại nguyên vẹn. Nếu nghiệp vụ yêu cầu chống replay, cần sequence number, timestamp có policy, nonce/message ID đã dùng, idempotency key hoặc trạng thái xử lý phía server. AAD có thể ràng buộc record ID/sequence, nhưng việc từ chối message đã xử lý vẫn cần logic ứng dụng.

## 4. Kiểm thử sai khóa

Có hai kiểu sai khóa thường gặp:

1. **Khóa không hợp lệ về hình thức:** ví dụ AES key chỉ có 15 byte. Cipher.init() có thể ném InvalidKeyException.
2. **Khóa đúng định dạng nhưng sai bí mật:** ví dụ dùng một AES-128 key khác để giải mã ciphertext được tạo bằng key ban đầu. Với GCM, kiểm tra tag sẽ thất bại và thường ném AEADBadTagException.

Không được chỉ kiểm tra độ dài khóa. Hai khóa đều 16 byte vẫn là hai khóa khác nhau.

### 4.1. Key ID và luân chuyển khóa

Envelope mã hóa nên có keyId/version để chọn đúng khóa từ kho quản lý khóa (KMS, HSM hoặc key store). keyId là metadata định danh, **không phải khóa bí mật**.

Khi key ID không tồn tại:
- Từ chối theo policy.
- Không thử lần lượt mọi khóa trong kho để tìm khóa giải được.
- Không fallback sang một khóa mặc định.
- Không ghi khóa/secret ra log.
- Không thay đổi key ID do người dùng gửi nếu chưa xác minh envelope.

Khi xoay khóa, giữ khả năng đọc dữ liệu cũ bằng key version cũ theo retention policy, nhưng mã hóa dữ liệu mới bằng khóa hiện hành. Không tái sử dụng nonce counter đã reset nếu khóa thực tế vẫn là cùng key material.

### 4.2. Ví dụ 1 — AeadNegativeTest.java

Chương trình dùng key cố định **chỉ để test lặp lại được**. Không sao chép key hoặc nonce trong test vào production.

```java
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.security.InvalidKeyException;

public class AeadNegativeTest {
    static byte[] crypt(
        int mode, byte[] key, byte[] nonce,
        byte[] aad, byte[] input
    ) throws Exception {
        Cipher cipher =
            Cipher.getInstance("AES/GCM/NoPadding");

        cipher.init(
            mode,
            new SecretKeySpec(key, "AES"),
            new GCMParameterSpec(128, nonce)
        );

        cipher.updateAAD(aad);
        return cipher.doFinal(input);
    }

    static boolean rejected(
        byte[] key, byte[] nonce,
        byte[] aad, byte[] ciphertext
    ) throws Exception {
        try {
            crypt(
                Cipher.DECRYPT_MODE,
                key, nonce, aad, ciphertext
            );
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    static byte[] changed(byte[] input, int index) {
        byte[] copy = input.clone();
        copy[index] ^= 1;
        return copy;
    }

    public static void main(String[] args)
            throws Exception {
        byte[] key = new byte[16];
        byte[] wrongKey = new byte[16];
        Arrays.fill(key, (byte) 0x11);
        Arrays.fill(wrongKey, (byte) 0x22);

        byte[] nonce = new byte[12];
        nonce[11] = 1;

        byte[] aad =
            "v1|record=42".getBytes("UTF-8");
        byte[] plaintext =
            "approved payment".getBytes("UTF-8");

        byte[] ciphertext = crypt(
            Cipher.ENCRYPT_MODE,
            key, nonce, aad, plaintext
        );

        byte[] recovered = crypt(
            Cipher.DECRYPT_MODE,
            key, nonce, aad, ciphertext
        );

        System.out.println(
            "roundTrip=" +
            Arrays.equals(plaintext, recovered)
        );
        System.out.println(
            "wrongKeyRejected=" +
            rejected(wrongKey, nonce, aad, ciphertext)
        );
        System.out.println(
            "tamperedCiphertextRejected=" +
            rejected(key, nonce, aad,
                     changed(ciphertext, 0))
        );
        System.out.println(
            "tamperedTagRejected=" +
            rejected(key, nonce, aad,
                     changed(ciphertext, ciphertext.length - 1))
        );
        System.out.println(
            "wrongAadRejected=" +
            rejected(
                key, nonce,
                "v1|record=43".getBytes("UTF-8"),
                ciphertext
            )
        );

        byte[] wrongNonce = nonce.clone();
        wrongNonce[0] = 1;

        System.out.println(
            "wrongNonceRejected=" +
            rejected(key, wrongNonce, aad, ciphertext)
        );
        System.out.println(
            "truncatedTagRejected=" +
            rejected(
                key, nonce, aad,
                Arrays.copyOf(ciphertext, ciphertext.length - 1)
            )
        );

        try {
            Cipher cipher =
                Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                Cipher.ENCRYPT_MODE,
                new SecretKeySpec(new byte[15], "AES"),
                new GCMParameterSpec(128, nonce)
            );
            System.out.println(
                "invalidKeyLengthRejected=false"
            );
        } catch (InvalidKeyException expected) {
            System.out.println(
                "invalidKeyLengthRejected=true"
            );
        }
    }
}
```

Chạy:

```bash
javac AeadNegativeTest.java
java AeadNegativeTest
```

Stdout đã kiểm thử:

```text
roundTrip=true
wrongKeyRejected=true
tamperedCiphertextRejected=true
tamperedTagRejected=true
wrongAadRejected=true
wrongNonceRejected=true
truncatedTagRejected=true
invalidKeyLengthRejected=true
```

Dữ liệu đúng round-trip thành công; mọi biến thể sai đều bị từ chối. Key 15 byte bị từ chối ngay tại khâu khởi tạo, trong khi khóa sai nhưng đủ 16 byte bị phát hiện khi xác thực ciphertext/tag.

## 5. Kiểm thử dữ liệu bị sửa, AAD và envelope

Ngoài ciphertext, cần kiểm tra metadata điều khiển cách ứng dụng diễn giải dữ liệu:

- Version của định dạng mã hóa và thuật toán được allowlist.
- keyId và trạng thái khóa.
- Nonce có đúng 12 byte theo format đang dùng không.
- Ciphertext có đủ tag và không vượt giới hạn payload không.
- AAD có được dựng từ cùng một canonical encoding ở cả hai phía không.
- Tenant ID, object ID, schema version có bị tráo giữa hai record không.

Không parse envelope không giới hạn kích thước trước khi áp dụng giới hạn input; điều này có thể tạo rủi ro tiêu thụ bộ nhớ. Hãy kiểm tra cấu trúc trước khi lấy khóa hoặc cấp phát buffer lớn.

### 5.1. Ví dụ 2 — EnvelopeValidationDemo.java

Đây là lớp kiểm tra cấu trúc đầu vào. Nó không thay thế kiểm tra tag mật mã.

```java
import java.util.HashMap;
import java.util.Map;

public class EnvelopeValidationDemo {
    static final int VERSION = 1;
    static final int NONCE_BYTES = 12;
    static final int TAG_BYTES = 16;
    static final int MAX_BYTES = 1024 * 1024;

    static final class Envelope {
        final int version;
        final String keyId;
        final byte[] nonce;
        final byte[] ciphertext;

        Envelope(
            int version, String keyId,
            byte[] nonce, byte[] ciphertext
        ) {
            this.version = version;
            this.keyId = keyId;
            this.nonce = nonce;
            this.ciphertext = ciphertext;
        }
    }

    static void validate(Envelope e) {
        if (e == null)
            throw new IllegalArgumentException("missing envelope");
        if (e.version != VERSION)
            throw new IllegalArgumentException("version");
        if (e.keyId == null || e.keyId.trim().isEmpty())
            throw new IllegalArgumentException("key id");
        if (e.nonce == null || e.nonce.length != NONCE_BYTES)
            throw new IllegalArgumentException("nonce length");
        if (e.ciphertext == null ||
                e.ciphertext.length < TAG_BYTES)
            throw new IllegalArgumentException("ciphertext/tag length");
        if (e.ciphertext.length > MAX_BYTES)
            throw new IllegalArgumentException("ciphertext too large");
    }

    static boolean accepted(Envelope e) {
        try {
            validate(e);
            return true;
        } catch (IllegalArgumentException expected) {
            return false;
        }
    }

    static String resolveKey(
        String keyId, Map<String, String> keyReferences
    ) {
        String keyReference = keyReferences.get(keyId);
        if (keyReference == null)
            throw new SecurityException("unknown key id");
        return keyReference;
    }

    public static void main(String[] args) {
        byte[] nonce = new byte[12];
        byte[] ciphertextAndTag = new byte[32];

        Envelope valid =
            new Envelope(1, "key-v1", nonce, ciphertextAndTag);

        System.out.println("validAccepted=" + accepted(valid));
        System.out.println(
            "unknownVersionRejected=" +
            !accepted(new Envelope(2, "key-v1", nonce, ciphertextAndTag))
        );
        System.out.println(
            "wrongNonceLengthRejected=" +
            !accepted(new Envelope(1, "key-v1", new byte[11],
                                   ciphertextAndTag))
        );
        System.out.println(
            "truncatedTagRejected=" +
            !accepted(new Envelope(1, "key-v1", nonce, new byte[15]))
        );
        System.out.println(
            "emptyKeyIdRejected=" +
            !accepted(new Envelope(1, " ", nonce, ciphertextAndTag))
        );

        Map<String, String> keyReferences = new HashMap<>();
        keyReferences.put("key-v1", "test-key-reference");

        try {
            resolveKey("unknown", keyReferences);
            System.out.println("unknownKeyIdRejected=false");
        } catch (SecurityException expected) {
            System.out.println("unknownKeyIdRejected=true");
        }
    }
}
```

```bash
javac EnvelopeValidationDemo.java
java EnvelopeValidationDemo
```

Stdout:

```text
validAccepted=true
unknownVersionRejected=true
wrongNonceLengthRejected=true
truncatedTagRejected=true
emptyKeyIdRejected=true
unknownKeyIdRejected=true
```

Map trong ví dụ chỉ giữ một **tham chiếu khóa giả lập**, không lưu secret thật. Trong production, resolve keyId qua KMS/HSM hoặc key store với quyền truy cập tối thiểu.

### 5.2. AAD nên gắn với ngữ cảnh nào?

Ví dụ AAD có thể là cấu trúc canonical gồm:

```text
formatVersion | tenantId | recordId | fieldName | schemaVersion
```

Nếu ciphertext của recordId=42 bị sao chép sang recordId=43, giải mã với AAD mới phải thất bại. Nếu dựng AAD bằng JSON, cần quy định canonical serialization: thứ tự field, charset, escaping, null, số và version. Hai phía phải tạo ra **đúng cùng byte sequence**, không chỉ cùng nội dung nhìn bằng mắt.

Không đưa secret vào AAD vì AAD không được mã hóa. Có thể đưa ID hoặc metadata không bí mật nhưng cần xác thực.

## 6. Nonce trong AES-GCM: tính duy nhất theo từng khóa

Nonce (IV) của GCM phải **không lặp lại với cùng một khóa**. Oracle Cipher docs cảnh báo việc lặp IV dưới cùng khóa có thể dẫn tới tấn công giả mạo; NIST SP 800-38D khuyến nghị triển khai ưu tiên IV 96 bit để tăng khả năng tương thích, hiệu quả và đơn giản.

Ba điều cần phân biệt:

1. **Nonce sai khi giải mã:** nonce khác với nonce đã dùng lúc mã hóa sẽ làm tag xác thực thất bại.
2. **Nonce bị tái sử dụng khi mã hóa:** đây là lỗi thiết kế nghiêm trọng; GCM không tự phát hiện lịch sử nonce.
3. **Replay ciphertext:** gửi lại nguyên ciphertext hợp lệ không giống nonce reuse; cần chống replay ở tầng ứng dụng.

Cipher.init() không duy trì registry tất cả nonce từng dùng. Trách nhiệm đảm bảo uniqueness thuộc về hệ thống cấp phát nonce và quản lý vòng đời khóa.

### 6.1. Hai chiến lược cấp phát phổ biến

**Random nonce:** Dùng SecureRandom tạo 12 byte. Cách này có tính ngẫu nhiên mật mã, nhưng uniqueness chỉ là xác suất; phải giới hạn số lần dùng một key và đánh giá collision probability theo chuẩn/policy. Không tự viết PRNG hoặc seed từ timestamp, counter nhỏ hay ID dễ đoán.

**Counter/sequence nonce:** Dùng cấu trúc như prefix 32 bit + counter 64 bit. Nó có thể đảm bảo không trùng trong phạm vi một khóa nếu:
- Prefix được cấp duy nhất cho từng writer/instance dùng cùng key.
- Counter được tăng nguyên tử và không quay vòng.
- Trạng thái được lưu bền vững, cấp phát đồng bộ qua nhiều instance.
- Restart, restore backup, rollback VM và scale-out không làm counter quay lại.
- Khi counter hết miền, dừng cấp nonce và xoay sang key material mới theo quy trình.

Một AtomicLong trong một JVM chỉ giải quyết cạnh tranh giữa thread trong process đó; nó **không** đảm bảo uniqueness qua restart, nhiều máy, nhiều container hoặc bản backup được phục hồi. Nếu dùng counter, cần thiết kế lưu trữ/lease/range allocation bền vững và được kiểm thử.

### 6.2. Ví dụ 3 — kiểm tra uniqueness khi nhiều thread cấp nonce

Chương trình dùng prefix 4 byte và counter 8 byte để tạo nonce 12 byte. Đây là **mô hình minh họa cho một process**, không phải allocator production dùng trực tiếp.

```java
import java.nio.ByteBuffer;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.IntStream;

public class NonceUniquenessDemo {
    static final class Sequence {
        final byte[] prefix;
        final AtomicLong next = new AtomicLong();

        Sequence(byte[] prefix) {
            if (prefix.length != 4)
                throw new IllegalArgumentException();
            this.prefix = prefix.clone();
        }

        byte[] next() {
            long value = next.getAndUpdate(
                v -> Math.addExact(v, 1L)
            );
            return ByteBuffer.allocate(12)
                .put(prefix)
                .putLong(value)
                .array();
        }

        long count() {
            return next.get();
        }
    }

    static final class Registry {
        final ConcurrentHashMap<String, Set<String>> seen =
            new ConcurrentHashMap<>();

        boolean register(String keyId, byte[] nonce) {
            return seen.computeIfAbsent(
                keyId,
                ignored -> ConcurrentHashMap.newKeySet()
            ).add(hex(nonce));
        }
    }

    static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte b : bytes) {
            out.append(String.format("%02x", b & 0xff));
        }
        return out.toString();
    }

    public static void main(String[] args) {
        Sequence sequence = new Sequence(
            new byte[] { 1, 2, 3, 4 }
        );

        Set<String> generated =
            ConcurrentHashMap.newKeySet();
        AtomicInteger duplicates = new AtomicInteger();

        IntStream.range(0, 4000).parallel().forEach(i -> {
            if (!generated.add(hex(sequence.next()))) {
                duplicates.incrementAndGet();
            }
        });

        Registry registry = new Registry();
        byte[] sample = new byte[12];
        sample[11] = 7;

        boolean first =
            registry.register("key-v1", sample);
        boolean duplicate =
            registry.register("key-v1", sample);
        boolean otherKey =
            registry.register("key-v2", sample);

        System.out.println("generated=" + sequence.count());
        System.out.println("unique=" + generated.size());
        System.out.println(
            "duplicateGenerated=" + duplicates.get()
        );
        System.out.println(
            "nonceLength=" + sequence.next().length
        );
        System.out.println("firstUseAccepted=" + first);
        System.out.println(
            "duplicateSameKeyRejected=" + !duplicate
        );
        System.out.println(
            "sameNonceOtherKeyAccepted=" + otherKey
        );
    }
}
```

```bash
javac NonceUniquenessDemo.java
java NonceUniquenessDemo
```

Stdout đã kiểm thử:

```text
generated=4000
unique=4000
duplicateGenerated=0
nonceLength=12
firstUseAccepted=true
duplicateSameKeyRejected=true
sameNonceOtherKeyAccepted=true
```

Cùng nonce được chấp nhận ở key-v2 trong registry vì uniqueness của GCM được xét **theo từng key**. Điều này chỉ đúng nếu key-v1 và key-v2 thực sự là hai key material khác nhau; không được tạo hai alias cho cùng một khóa rồi coi đó là hai namespace độc lập.

**Không dùng Registry trong RAM làm giải pháp production.** Nó mất dữ liệu khi restart và không chia sẻ giữa các node. Ví dụ chỉ chứng minh cấu trúc test có thể phát hiện duplicate trong một process.

### 6.3. Test nonce phải bao phủ nhiều tình huống hơn một vòng lặp

- Nhiều thread gọi đồng thời.
- Nhiều instance cùng dùng một key.
- Restart giữa chừng và restore từ backup.
- Snapshot/rollback máy ảo hoặc container.
- Key rotation, key alias và key material trùng.
- Counter gần giới hạn và hành vi khi hết counter.
- Một nonce bị ghi lại rồi được gửi lại.
- Lỗi ghi trạng thái nonce nhưng encryption đã thành công (hoặc ngược lại).

Nếu phát hiện GCM nonce reuse, không chỉ xóa nonce trùng khỏi registry rồi tiếp tục. Cần dừng dùng khóa bị ảnh hưởng, đánh giá phạm vi dữ liệu đã mã hóa và xoay key theo incident procedure. Nonce reuse trước đó không thể được “hoàn tác” bằng cách sửa registry.

## 7. Tạo key và nonce an toàn trong ứng dụng

Ví dụ tạo AES key bằng JCA:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

// Đoạn minh họa:
SecureRandom random = new SecureRandom();

KeyGenerator generator =
    KeyGenerator.getInstance("AES");

generator.init(128, random);

SecretKey key = generator.generateKey();

byte[] nonce = new byte[12];
random.nextBytes(nonce);
```

Không tạo key bằng new byte[16] trong production. Mảng zero hoặc key cố định trong test chỉ để kiểm thử lặp lại được. Không tự đặt seed dễ đoán cho SecureRandom.

Random 96-bit nonce là một chiến lược phổ biến nếu số lần mã hóa mỗi key được giới hạn theo thiết kế và phân tích collision phù hợp. Với hệ thống throughput cao hoặc cần uniqueness được kiểm soát chặt, hãy dùng bộ cấp phát nonce có trạng thái bền vững/độc lập giữa các instance. Không tự suy rằng SecureRandom biến một nonce ngẫu nhiên thành bảo đảm toán học tuyệt đối không lặp.

## 8. Kiểm thử chứng chỉ X.509: bốn lớp xác minh riêng

Một chứng chỉ có thể có ngày hợp lệ nhưng vẫn không đáng tin; một chain được tin cậy nhưng hostname không khớp. Cần tách:

1. **Validity period:** notBefore và notAfter — chứng chỉ đã có hiệu lực và chưa hết hạn chưa?
2. **Path/trust:** chữ ký, chuỗi intermediate, trust anchor và quy tắc PKIX có hợp lệ không?
3. **Purpose/constraints:** Key Usage, Extended Key Usage, Basic Constraints, Name Constraints và algorithm/key-size policy có phù hợp vai trò không?
4. **Endpoint identity:** SAN trong chứng chỉ có khớp hostname/IP mà client định kết nối không?

X509Certificate.checkValidity() chỉ kiểm tra thời hạn. Nó **không** chứng minh certificate chain đáng tin, chữ ký hợp lệ hay SAN khớp hostname.

### 8.1. Hết hạn và chưa có hiệu lực

Kiểm thử cả hai biên:
- CertificateExpiredException: thời điểm kiểm tra sau notAfter.
- CertificateNotYetValidException: thời điểm kiểm tra trước notBefore.
- Thời điểm hiện tại trong khoảng hiệu lực phải được chấp nhận nếu các bước trust/purpose khác cũng đạt.

Để kiểm thử deterministic, dùng checkValidity(Date) với một ngày cố định nằm ngoài khoảng hiệu lực của fixture. Không cần chờ nhiều tuần cho chứng chỉ test thật sự hết hạn.

### 8.2. PKIX path và trust anchors

CertPathValidator.getInstance("PKIX") xác thực đường dẫn chứng chỉ theo PKIXParameters, bao gồm một hoặc nhiều TrustAnchor. Một CA không được tin cậy phải làm validation thất bại.

Một chain thường có dạng:

```text
Server/Client leaf certificate
       |
       v
Intermediate CA (có thể nhiều tầng)
       |
       v
Root CA (trust anchor trong trust store)
```

Root CA thường được cấu hình là trust anchor; các intermediate phải có mặt hoặc được tìm thấy theo chính sách path building. Thiếu intermediate có thể làm không dựng được chain dù root cuối cùng nằm trong trust store.

Đừng biến một chứng chỉ leaf tự ký thành trust anchor chỉ để test pass. Nếu ứng dụng có private PKI, chỉ cài CA test/CA nội bộ vào trust store đúng phạm vi, và kiểm tra chain theo mô hình tin cậy đã thiết kế.

### 8.3. SAN và hostname verification

Đối với HTTPS, certificate phải đại diện đúng hostname mà client đang kết nối. Kiểm tra hostname độc lập với việc chain có trusted hay không. Hiện đại hóa certificate test theo **Subject Alternative Name (SAN)**; không dựa vào CN-only như một fallback để bỏ qua SAN mismatch.

Với SSLSocket/SSLEngine, có thể yêu cầu endpoint identification bằng:

```java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
```

Đối với HttpsURLConnection hoặc HTTP client chuẩn, giữ xác minh hostname mặc định. Không cài HostnameVerifier luôn trả true, không cài TrustManager chấp nhận mọi certificate, không tắt kiểm tra chain/hostname để “sửa” test.

### 8.4. Chữ ký, EKU và Key Usage

Một chứng chỉ có thể parse được nhưng chữ ký không hợp lệ. Ngoài ra:
- CA certificate cần Basic Constraints/Key Usage thích hợp để ký chứng chỉ con.
- Server TLS certificate cần mục đích phù hợp, ví dụ serverAuth.
- Client certificate cần mục đích clientAuth nếu policy yêu cầu.
- Key size, signature algorithm, name constraints và algorithm constraints phải phù hợp policy hiện hành.

Không chỉ kiểm tra subject hoặc issuer text; tên hiển thị giống CA không chứng minh chữ ký/chain đúng.

### 8.5. Revocation: OCSP/CRL

Nếu ứng dụng cần kiểm tra chứng chỉ bị thu hồi, xác định rõ chính sách OCSP/CRL và cách xử lý khi dịch vụ kiểm tra không truy cập được. Test certificate bị revoke, response hết hạn/không hợp lệ, responder không truy cập được và policy fail-closed/soft-fail. Không suy rằng chỉ gọi checkValidity() đã kiểm tra revocation; cũng không đổi sang soft-fail chỉ để test pass.

## 9. Ví dụ 4 — tạo fixture chứng chỉ test bằng keytool

Để kiểm tra PKIX và TLS thật, tạo một CA **chỉ dành cho môi trường test**, một leaf certificate có SAN localhost, và một CA khác không liên quan. Các lệnh sau tạo keystore PKCS12, khóa RSA 2048 bit và chữ ký SHA-256. Mật khẩu changeit ở đây chỉ là mật khẩu fixture cục bộ, không dùng cho secret production.

Tạo root test:

```bash
keytool -genkeypair -alias test-root -keystore root.p12 -storetype PKCS12 -storepass changeit -keypass changeit -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=STEP4 Test Root CA" -validity 3650 -ext BC=ca:true -ext KU=keyCertSign,cRLSign

keytool -exportcert -rfc -alias test-root -keystore root.p12 -storetype PKCS12 -storepass changeit -file root.pem
```

Tạo leaf có SAN DNS localhost và CSR:

```bash
keytool -genkeypair -alias localhost -keystore leaf.p12 -storetype PKCS12 -storepass changeit -keypass changeit -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost" -validity 30 -ext BC=ca:false -ext KU=digitalSignature,keyEncipherment -ext EKU=serverAuth -ext SAN=dns:localhost

keytool -certreq -alias localhost -keystore leaf.p12 -storetype PKCS12 -storepass changeit -file leaf.csr -ext SAN=dns:localhost -ext EKU=serverAuth
```

Ký CSR bằng CA test, import CA và leaf chain:

```bash
keytool -gencert -alias test-root -keystore root.p12 -storetype PKCS12 -storepass changeit -infile leaf.csr -outfile leaf.pem -rfc -validity 30 -startdate "-1d" -ext BC=ca:false -ext KU=digitalSignature,keyEncipherment -ext EKU=serverAuth -ext SAN=dns:localhost

keytool -importcert -noprompt -alias test-root-cert -keystore leaf.p12 -storetype PKCS12 -storepass changeit -file root.pem

keytool -importcert -noprompt -alias localhost -keystore leaf.p12 -storetype PKCS12 -storepass changeit -file leaf.pem
```

Tạo CA khác để test untrusted root:

```bash
keytool -genkeypair -alias other-root -keystore other.p12 -storetype PKCS12 -storepass changeit -keypass changeit -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Unrelated Test Root CA" -validity 3650 -ext BC=ca:true -ext KU=keyCertSign,cRLSign

keytool -exportcert -rfc -alias other-root -keystore other.p12 -storetype PKCS12 -storepass changeit -file other.pem
```

Các fixture này chỉ dành cho test. Không cài root.pem vào trust store hệ điều hành/browser thật, không dùng changeit làm password production và không dùng private key test để bảo vệ dữ liệu thực.

## 10. Ví dụ 5 — PKIX path, hết hạn và chưa có hiệu lực

Chương trình nhận ba file: leaf.pem, root.pem, other.pem. setRevocationEnabled(false) chỉ để kiểm thử offline deterministic; production phải cấu hình revocation theo policy của hệ thống.

**CertificatePathDemo.java**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.cert.*;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Collections;
import java.util.Date;

public class CertificatePathDemo {
    static X509Certificate load(String path)
            throws Exception {
        CertificateFactory factory =
            CertificateFactory.getInstance("X.509");

        try (InputStream in =
                 Files.newInputStream(Paths.get(path))) {
            return (X509Certificate)
                factory.generateCertificate(in);
        }
    }

    static boolean validates(
        X509Certificate leaf,
        X509Certificate root
    ) throws Exception {
        CertificateFactory factory =
            CertificateFactory.getInstance("X.509");

        CertPath path = factory.generateCertPath(
            Collections.singletonList(leaf)
        );

        PKIXParameters parameters =
            new PKIXParameters(
                Collections.singleton(
                    new TrustAnchor(root, null)
                )
            );

        // Offline test fixture only.
        parameters.setRevocationEnabled(false);

        try {
            CertPathValidator.getInstance("PKIX")
                .validate(path, parameters);
            return true;
        } catch (CertPathValidatorException expected) {
            return false;
        }
    }

    public static void main(String[] args)
            throws Exception {
        X509Certificate leaf = load(args[0]);
        X509Certificate root = load(args[1]);
        X509Certificate other = load(args[2]);

        leaf.checkValidity();
        System.out.println("currentValidity=ACCEPTED");

        try {
            leaf.checkValidity(Date.from(
                Instant.now().minus(400, ChronoUnit.DAYS)
            ));
            System.out.println("notYetValidRejected=false");
        } catch (CertificateNotYetValidException expected) {
            System.out.println("notYetValidRejected=true");
        }

        try {
            leaf.checkValidity(Date.from(
                Instant.now().plus(400, ChronoUnit.DAYS)
            ));
            System.out.println("expiredRejected=false");
        } catch (CertificateExpiredException expected) {
            System.out.println("expiredRejected=true");
        }

        System.out.println(
            "trustedPathAccepted=" + validates(leaf, root)
        );
        System.out.println(
            "untrustedRootRejected=" +
            !validates(leaf, other)
        );
        System.out.println(
            "sanPresent=" +
            leaf.getSubjectAlternativeNames()
                .toString().contains("localhost")
        );
    }
}
```

Chạy:

```bash
javac CertificatePathDemo.java
java CertificatePathDemo leaf.pem root.pem other.pem
```

Stdout đã kiểm thử:

```text
currentValidity=ACCEPTED
notYetValidRejected=true
expiredRejected=true
trustedPathAccepted=true
untrustedRootRejected=true
sanPresent=true
```

checkValidity(Date) kiểm tra mốc thời gian giả định; CertPathValidator kiểm tra chain theo trust anchor. Hai phép kiểm tra có mục tiêu khác nhau. Dòng sanPresent chỉ xác nhận fixture có SAN localhost; **hostname verification thực sự** được kiểm thử bằng TLS handshake ở ví dụ tiếp theo.

## 11. Ví dụ 6 — chữ ký certificate bị sửa phải bị từ chối

Chứng chỉ X.509 có thể parse được nhưng chữ ký không còn đúng với nội dung. Để kiểm thử, thay đổi một bit trong byte cuối của certificate DER rồi yêu cầu PKIX validator xác thực với CA ban đầu.

**TamperedCertificateDemo.java**:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.cert.*;
import java.util.Collections;

public class TamperedCertificateDemo {
    static X509Certificate load(String path)
            throws Exception {
        CertificateFactory factory =
            CertificateFactory.getInstance("X.509");

        try (InputStream in =
                 Files.newInputStream(Paths.get(path))) {
            return (X509Certificate)
                factory.generateCertificate(in);
        }
    }

    static boolean valid(
        X509Certificate leaf,
        X509Certificate root
    ) throws Exception {
        CertificateFactory factory =
            CertificateFactory.getInstance("X.509");

        CertPath path = factory.generateCertPath(
            Collections.singletonList(leaf)
        );

        PKIXParameters parameters =
            new PKIXParameters(
                Collections.singleton(
                    new TrustAnchor(root, null)
                )
            );
        parameters.setRevocationEnabled(false);

        try {
            CertPathValidator.getInstance("PKIX")
                .validate(path, parameters);
            return true;
        } catch (CertPathValidatorException expected) {
            return false;
        }
    }

    public static void main(String[] args)
            throws Exception {
        X509Certificate leaf = load(args[0]);
        X509Certificate root = load(args[1]);

        byte[] der = leaf.getEncoded();
        der[der.length - 1] ^= 1;

        X509Certificate altered =
            (X509Certificate)
                CertificateFactory.getInstance("X.509")
                    .generateCertificate(
                        new ByteArrayInputStream(der)
                    );

        System.out.println(
            "originalSignatureAccepted=" +
            valid(leaf, root)
        );
        System.out.println(
            "tamperedSignatureRejected=" +
            !valid(altered, root)
        );
    }
}
```

```bash
javac TamperedCertificateDemo.java
java TamperedCertificateDemo leaf.pem root.pem
```

Stdout:

```text
originalSignatureAccepted=true
tamperedSignatureRejected=true
```

Đây là test fixture có chủ đích, không phải cách sửa chứng chỉ ngoài đời. Trong hệ thống thật, certificate phải được xác thực bằng trust chain và policy; không tự kiểm tra một trường signature bằng cách so byte theo cách riêng.

## 12. Ví dụ 7 — TLS hostname verification bằng SAN thật

Để kiểm tra SAN, dùng server TLS cục bộ có leaf certificate localhost, và client trust **chỉ CA test**. Client yêu cầu endpoint identification HTTPS:

- Kết nối bằng localhost: SAN khớp, handshake thành công.
- Kết nối bằng 127.0.0.1: certificate fixture không có IP SAN, handshake thất bại dù chain vẫn được tin cậy.

**HttpsEndpointTest.java**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.concurrent.atomic.AtomicReference;
import javax.net.ssl.*;

public class HttpsEndpointTest {
    static SSLContext serverContext(String path)
            throws Exception {
        KeyStore keys = KeyStore.getInstance("PKCS12");

        try (InputStream in =
                 Files.newInputStream(Paths.get(path))) {
            keys.load(in, "changeit".toCharArray());
        }

        KeyManagerFactory kmf =
            KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
            );

        kmf.init(keys, "changeit".toCharArray());

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            kmf.getKeyManagers(),
            null,
            new SecureRandom()
        );
        return context;
    }

    static SSLContext clientContext(String rootPath)
            throws Exception {
        CertificateFactory factory =
            CertificateFactory.getInstance("X.509");

        X509Certificate root;
        try (InputStream in =
                 Files.newInputStream(Paths.get(rootPath))) {
            root = (X509Certificate)
                factory.generateCertificate(in);
        }

        KeyStore trust =
            KeyStore.getInstance(KeyStore.getDefaultType());
        trust.load(null, null);
        trust.setCertificateEntry("test-root", root);

        TrustManagerFactory tmf =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            null,
            tmf.getTrustManagers(),
            new SecureRandom()
        );
        return context;
    }

    static boolean handshake(
        SSLContext serverContext,
        SSLContext clientContext,
        String host
    ) throws Exception {
        SSLServerSocket server =
            (SSLServerSocket)
                serverContext.getServerSocketFactory()
                    .createServerSocket(0);

        AtomicReference<Exception> serverFailure =
            new AtomicReference<>();

        Thread acceptor = new Thread(() -> {
            try (SSLSocket socket =
                     (SSLSocket) server.accept()) {
                socket.setSoTimeout(5000);
                socket.startHandshake();
            } catch (Exception ex) {
                serverFailure.set(ex);
            }
        });

        acceptor.start();
        boolean accepted;

        try (SSLSocket client =
                 (SSLSocket)
                    clientContext.getSocketFactory()
                        .createSocket(host, server.getLocalPort())) {

            SSLParameters parameters =
                client.getSSLParameters();

            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            client.setSSLParameters(parameters);
            client.startHandshake();
            accepted = true;

        } catch (SSLHandshakeException expected) {
            accepted = false;
        } finally {
            server.close();
        }

        acceptor.join(5000);
        if (acceptor.isAlive())
            throw new IllegalStateException("server timeout");

        if (accepted && serverFailure.get() != null) {
            throw new IllegalStateException(
                "server handshake failed",
                serverFailure.get()
            );
        }

        return accepted;
    }

    public static void main(String[] args)
            throws Exception {
        SSLContext server = serverContext(args[0]);
        SSLContext client = clientContext(args[1]);

        System.out.println(
            "matchingSanAccepted=" +
            handshake(server, client, "localhost")
        );

        System.out.println(
            "mismatchedSanRejected=" +
            !handshake(server, client, "127.0.0.1")
        );
    }
}
```

Chạy:

```bash
javac HttpsEndpointTest.java
java HttpsEndpointTest leaf.p12 root.pem
```

Stdout đã kiểm thử:

```text
matchingSanAccepted=true
mismatchedSanRejected=true
```

Client dùng TrustManagerFactory với trust store chứa CA test và bật SSLParameters.setEndpointIdentificationAlgorithm("HTTPS"). Không có trust-all manager và không tắt xác minh hostname.

Nếu chứng chỉ có SAN IP:127.0.0.1, kết quả cho địa chỉ IP có thể khác; test phải khớp chính xác SAN mà ứng dụng dự định hỗ trợ. Trong production, ưu tiên HTTP client/TLS stack chuẩn và giữ mặc định xác thực chain + hostname.

## 13. Bộ test âm tính cho chứng chỉ

| Ca test | Cách tạo fixture | Assertion |
| --- | --- | --- |
| Certificate hợp lệ | CA test tin cậy, leaf hiện hành, SAN đúng | Handshake/PKIX chấp nhận |
| Hết hạn | Fixture notAfter trong quá khứ | CertificateExpiredException hoặc TLS reject |
| Chưa có hiệu lực | Fixture notBefore ở tương lai | CertificateNotYetValidException hoặc TLS reject |
| CA không tin cậy | Trust store không có root ký leaf | PKIX reject |
| Thiếu intermediate | Không gửi/không cung cấp intermediate cần thiết | Path building/handshake reject |
| Chữ ký bị sửa | Thay đổi chữ ký DER | PKIX reject |
| Hostname sai | SAN không có hostname đang kết nối | HTTPS endpoint identification reject |
| SAN thiếu | Không có SAN cần thiết theo policy | Reject |
| EKU sai | Server certificate chỉ có clientAuth hoặc ngược lại | Reject theo path/algorithm policy |
| Key Usage sai | Cờ usage không phù hợp thao tác | Reject theo policy/handshake |
| Key yếu/thuật toán không được phép | Fixture dùng key/algorithm ngoài policy | Algorithm constraints reject |
| Certificate bị revoke | CA test phát hành CRL/OCSP revoke | Reject theo revocation policy |
| Revocation service lỗi | OCSP/CRL không truy cập được | Đúng fail-open/soft-fail hoặc fail-closed policy |

Một test certificate “đã hết hạn” không thay thế test “chữ ký sai”; hai lỗi nằm ở hai lớp kiểm tra khác nhau. Tương tự, certificate có trusted chain không chứng minh SAN khớp.

## 14. Chống kiểm thử giả: fail closed và không để lọt side effect

Khi một phép xác thực thất bại, ứng dụng nên:

1. Không trả plaintext hoặc object đã giải mã.
2. Không cập nhật DB, phát message hoặc thực hiện nghiệp vụ.
3. Không tự đổi sang thuật toán yếu/không xác thực.
4. Không bỏ qua certificate validation khi handshake lỗi.
5. Không thử các khóa ngẫu nhiên khác đến khi một khóa nào đó giải được.
6. Không lộ cho caller biết “sai key”, “sai tag” hay “sai AAD” nếu chi tiết đó tạo oracle.
7. Ghi nhận sự kiện bảo mật nội bộ với thông tin tối thiểu cần thiết, không ghi secret.
8. Giữ metric phân biệt lỗi cấu trúc, lỗi key lookup, AEAD authentication và TLS trust để vận hành, nhưng không đưa chi tiết nhạy cảm vào response công khai.

Với các test có side effect, dùng fake repository/transaction hoặc DB test riêng để xác minh trạng thái **không đổi** sau lỗi. Ví dụ nếu tag sai thì số bản ghi, số tiền, số message queue và trạng thái đơn hàng phải giữ nguyên.

### 14.1. Không nuốt exception

Các pattern nguy hiểm:

```java
// Sai: coi giải mã thất bại là dữ liệu rỗng.
try {
    return decrypt(ciphertext);
} catch (Exception ignored) {
    return new byte[0];
}
```

```java
// Sai: bỏ qua certificate error.
try {
    socket.startHandshake();
} catch (SSLException ignored) {
    // Vẫn gửi dữ liệu nhạy cảm.
}
```

Hãy trả lỗi xác thực chung theo hợp đồng ứng dụng, đóng connection/transaction thích hợp và không tiếp tục dùng dữ liệu chưa xác minh.

### 14.2. Không fallback sang mode không có authentication

Nếu AES-GCM tag sai, không thử AES-CBC, ECB hoặc giải mã không kiểm tra tag để “cứu dữ liệu”. Fallback làm mất tính xác thực và có thể mở ra downgrade attack. Format version/algorithm ID phải được kiểm tra theo allowlist và ràng buộc trong metadata/AAD.

## 15. Test key management và vòng đời

Bên cạnh test thuật toán, cần kiểm thử:
- Key ID hợp lệ và không tồn tại.
- Khóa bị disable/revoked trong KMS.
- Key rotation: dữ liệu cũ đọc bằng key version cũ, dữ liệu mới dùng version mới.
- Key version bị đổi trong metadata.
- Key store/KMS không truy cập được.
- Quyền ứng dụng không đủ để đọc private/secret key.
- Backup/restore và disaster recovery không làm nonce counter quay lại.
- Xóa/retire key: dữ liệu cần giữ có chiến lược re-encrypt/retention.
- Không log key bytes, password, private key hoặc raw decrypted payload.
- Key dùng cho GCM không bị dùng đồng thời cho mục đích khác không có key separation.

Không dùng cùng một khóa cho nhiều thuật toán/protocol chỉ vì cùng kích thước. Hãy dùng key management và domain separation theo thiết kế đã phê duyệt.

## 16. Test TLS theo môi trường triển khai

Một unit test local không thay thế test cấu hình TLS ở môi trường thật. Ma trận kiểm thử nên có:
- TLS version được cho phép theo policy (thường TLS 1.2/1.3 theo môi trường hiện hành).
- Certificate chain đầy đủ, root/intermediate phù hợp.
- Hostname/SAN cho mọi hostname và endpoint IP được công bố.
- Certificate renewal/rotation và overlap giữa hai leaf certificate.
- Mutual TLS: certificate client đúng/sai, EKU clientAuth, trust anchor phía server.
- Revocation nếu policy yêu cầu.
- SNI và nhiều virtual host.
- Proxy/load balancer kết thúc TLS và certificate thực sự mà client nhận.
- Algorithm constraints, key size, signature algorithm và cipher suite.
- Đồng hồ hệ thống sai lệch gây lỗi validity.
- Certificate chain bị thiếu intermediate sau triển khai.
- Không tắt xác minh hostname ở HTTP client hoặc test profile dùng chung production.

Không dùng self-signed certificate tùy tiện cho endpoint production. Với private PKI, cài đúng CA gốc/intermediate trong trust store được quản lý; với public endpoint, dùng trust anchors theo hệ điều hành/JDK policy.

## 17. Các lỗi thường gặp

1. **Chỉ test encrypt/decrypt đúng:** Không phát hiện lỗi từ chối dữ liệu sai. Thêm negative cases.
2. **Dùng key cố định trong production:** Key fixture chỉ dành cho test. Dùng KeyGenerator/KMS/HSM.
3. **Nghĩ key đủ 16 byte thì đúng:** Độ dài hợp lệ không chứng minh key identity đúng.
4. **Nuốt AEADBadTagException:** Có thể biến ciphertext lỗi thành dữ liệu hợp lệ giả.
5. **Trả plaintext từ update trước khi xác thực tag:** Chỉ publish sau doFinal() thành công.
6. **Không xác thực AAD:** Metadata có thể bị tráo giữa tenant/record.
7. **Tự so tag bằng Arrays.equals:** Dùng AEAD của JCA/provider, không tự xây xác thực.
8. **Dùng nonce cố định cho mọi message:** GCM yêu cầu nonce duy nhất theo key.
9. **Tin Cipher tự phát hiện nonce reuse:** JCA không quản lý lịch sử nonce.
10. **Chỉ dùng AtomicLong trong một JVM:** Restart/multi-node có thể trùng nonce.
11. **Reset counter sau restore backup:** Có thể lặp nonce với cùng key.
12. **Đổi key ID nhưng giữ nguyên key material:** Không tạo namespace nonce mới nếu thực chất vẫn cùng key.
13. **Nhầm nonce mismatch với replay:** GCM tag kiểm tra tính xác thực; replay cần state/sequence riêng.
14. **Đưa key/nonce/ciphertext bí mật vào log:** Tăng rủi ro lộ dữ liệu.
15. **Chỉ checkValidity chứng chỉ:** Chưa xác minh chain/trust/hostname.
16. **Tin CN thay SAN:** Test SAN theo hostname/IP thực tế.
17. **Dùng trust-all TrustManager:** Làm mất kiểm tra CA và mở MITM.
18. **Tắt hostname verification để test pass:** Che lỗi SAN mismatch.
19. **Tin certificate parse được là trusted:** Cần PKIX path validation.
20. **Bỏ intermediate khỏi server chain:** Client có thể không dựng được trust path.
21. **Bỏ qua EKU/Key Usage:** Chứng chỉ đúng CA nhưng sai mục đích.
22. **Không kiểm thử thời gian hệ thống:** Clock skew có thể làm certificate chưa/đã hết hạn.
23. **Mặc định revocation đã được kiểm tra:** Xác nhận rõ cấu hình OCSP/CRL theo runtime.
24. **Dùng cert test trong trust store production:** Trust anchor test chỉ nằm trong fixture riêng.
25. **Fallback sang cipher không xác thực:** Có thể tạo downgrade/integrity failure.
26. **Thử mọi khóa khi key ID sai:** Tăng bề mặt tấn công và che lỗi định danh.
27. **Chỉ assert exception:** Còn phải assert không plaintext/side effect.
28. **Dùng test dữ liệu ngẫu nhiên nhưng so stdout cố định:** Dùng vector deterministic cho test, randomness smoke test riêng.
29. **Dùng test CA có private key chung trong repo:** Private key fixture chỉ dành cho test, không phải secret production.
30. **Chỉ test một provider:** Ghi rõ JDK/provider/version triển khai và test thực tế.

## 18. Checklist code review

1. Có dùng AEAD như AES-GCM/ChaCha20-Poly1305 theo policy không?
2. Key được tạo/quản lý bởi nguồn an toàn không?
3. Key ID/version được kiểm tra trước khi dùng không?
4. Sai key length có bị từ chối không?
5. Sai key material có bị phát hiện ở bước authentication không?
6. Nonce có đúng kích thước và được cấp duy nhất theo từng key không?
7. Nonce allocator có an toàn qua thread, restart và nhiều node không?
8. Counter có kiểm tra overflow và trạng thái persistence không?
9. Có test duplicate nonce và key rotation không?
10. AAD có ràng buộc tenant/record/version theo canonical encoding không?
11. Có test ciphertext/tag/AAD/nonce bị sửa không?
12. Có test ciphertext/tag bị cắt cụt và envelope sai version không?
13. Không có plaintext nào được publish trước khi xác thực tag thành công?
14. Có giới hạn kích thước payload trước khi cấp phát bộ nhớ không?
15. Lỗi xác thực có fail closed và không tạo side effect không?
16. Có tránh log key, plaintext, secret và raw token không?
17. Certificate có thời hạn hợp lệ không?
18. Certificate chain có PKIX path tới đúng trust anchor không?
19. Intermediate certificate có đầy đủ không?
20. SAN có khớp hostname/IP đang kết nối không?
21. TLS endpoint identification có được bật không?
22. EKU/Key Usage/Basic Constraints có phù hợp vai trò không?
23. Có kiểm tra thuật toán và key size theo policy hiện hành không?
24. Revocation OCSP/CRL có được cấu hình/test theo yêu cầu không?
25. Không có trust-all manager, permissive hostname verifier hay downgrade fallback?
26. Negative test có xác minh dữ liệu/transaction không đổi sau lỗi không?
27. Fixture test có CA/key riêng và không được trust trong production không?
28. Có ghi rõ JDK/provider/version và test integration trên môi trường gần production không?

## 19. Ma trận test nên chạy trong CI và staging

| Nhóm | Positive case | Negative case |
| --- | --- | --- |
| AES-GCM | Key/nonce/AAD đúng | Sai key, sai nonce, sai AAD |
| Ciphertext | Ciphertext không đổi | Bit flip, tag flip, truncated tag |
| Envelope | Version/key ID/length hợp lệ | Version lạ, key ID rỗng, nonce sai length |
| Nonce | Nhiều thread tạo nonce duy nhất | Duplicate cùng key, counter rollback |
| Key lifecycle | Key version hiện hành | Key ID không tồn tại/đã retire |
| Certificate date | Trong validity period | Expired, not-yet-valid |
| PKIX | Chain tới trusted CA | Untrusted root, missing intermediate, bad signature |
| TLS identity | SAN khớp hostname | Hostname/IP mismatch |
| Certificate purpose | EKU/Key Usage đúng | EKU/Key Usage không phù hợp |
| Revocation | Status hợp lệ | Revoked, response lỗi/hết hạn |
| Application behavior | Dữ liệu hợp lệ được xử lý | Không plaintext/DB update/queue publish khi lỗi |

CI nên chạy test deterministic với fixture cố định. Staging nên có integration test với provider, trust store, KMS, database, proxy/load balancer và cấu hình TLS thực tế. Không đưa CA/private key test vào môi trường production.

## 20. Câu hỏi ôn tập

**1.** AES-GCM bảo vệ những gì?

**Đáp án:** Tính bí mật plaintext và tính toàn vẹn/xác thực của plaintext cùng AAD.

**2.** AEADBadTagException có thể do nguyên nhân nào?

**Đáp án:** Sai key, ciphertext, tag, nonce hoặc AAD; không nhất thiết phân biệt được nguyên nhân.

**3.** AES key 15 byte có thể bị từ chối ở đâu?

**Đáp án:** Cipher.init() với InvalidKeyException.

**4.** AES key 16 byte nhưng sai nội dung có thể lỗi ở đâu?

**Đáp án:** Khi doFinal() xác thực tag.

**5.** Nonce GCM có được lặp với cùng key không?

**Đáp án:** Không; uniqueness theo từng key là yêu cầu quan trọng.

**6.** GCM có tự phát hiện nonce reuse không?

**Đáp án:** Không; ứng dụng phải quản lý nonce.

**7.** Độ dài nonce GCM thường được khuyến nghị là bao nhiêu?

**Đáp án:** 96 bit (12 byte).

**8.** AAD có được mã hóa không?

**Đáp án:** Không; nó được xác thực nhưng giữ dạng rõ.

**9.** Vì sao cần đưa tenant ID/record ID vào AAD?

**Đáp án:** Để ràng buộc ciphertext với đúng ngữ cảnh, ngăn tráo dữ liệu giữa record/tenant.

**10.** Ciphertext hợp lệ có thể bị replay không?

**Đáp án:** Có; chống replay cần sequence/idempotency/state ở tầng ứng dụng.

**11.** AtomicLong trong một process đã đủ quản lý nonce production chưa?

**Đáp án:** Chưa; cần uniqueness qua restart và các node cùng key.

**12.** Nếu nonce trùng được phát hiện thì có thể xóa registry entry rồi tiếp tục không?

**Đáp án:** Không; phải đánh giá ảnh hưởng và xử lý key/incident theo policy.

**13.** X509Certificate.checkValidity() kiểm tra điều gì?

**Đáp án:** Thời hạn notBefore/notAfter, không xác minh trust chain hay hostname.

**14.** API nào kiểm tra PKIX certificate path?

**Đáp án:** CertPathValidator với thuật toán PKIX và trust anchors.

**15.** Root CA không có trong trust store thì sao?

**Đáp án:** Chain không được tin cậy và validation phải thất bại.

**16.** Vì sao cần kiểm tra SAN?

**Đáp án:** Đảm bảo danh tính certificate khớp hostname/IP đang kết nối.

**17.** SSLParameters.setEndpointIdentificationAlgorithm("HTTPS") làm gì?

**Đáp án:** Yêu cầu xác minh endpoint identity trong TLS handshake.

**18.** Chứng chỉ có thời hạn hợp lệ có thể vẫn bị từ chối không?

**Đáp án:** Có; chain, chữ ký, SAN, EKU, Key Usage hoặc algorithm policy có thể sai.

**19.** Vì sao không dùng trust-all TrustManager?

**Đáp án:** Nó bỏ qua xác minh trust chain và mở nguy cơ MITM.

**20.** PKIX validation có tự đảm bảo revocation policy của ứng dụng không?

**Đáp án:** Không nên giả định; phải xác nhận và cấu hình OCSP/CRL theo policy.

**21.** Nếu GCM tag sai, có được trả plaintext đã nhận từ một bước update trước đó không?

**Đáp án:** Không; chỉ publish sau khi xác thực cuối cùng thành công.

**22.** Negative test nên assert thêm điều gì ngoài exception?

**Đáp án:** Không có plaintext, database update, queue publish hoặc side effect ngoài ý muốn.

## 21. Tài liệu chính thức và hướng dẫn hiện hành

- [Oracle Java SE 21 — Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): AES-GCM, AAD, tag verification, AEADBadTagException và yêu cầu nonce/IV không lặp theo key.
- [Oracle Java SE 21 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): cấu hình độ dài tag và IV cho GCM.
- [Oracle Java SE 21 — KeyGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyGenerator.html): tạo secret key bằng provider và nguồn randomness.
- [Oracle Java SE 21 — SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): nguồn số ngẫu nhiên mật mã.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): authenticated encryption, uniqueness của IV và khuyến nghị 96-bit IV.
- [Oracle Java SE 21 — X509Certificate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Certificate.html): checkValidity, ngày hiệu lực và hết hạn.
- [Oracle Java SE 21 — CertPathValidator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html): xác thực certification path, PKIX và revocation checker.
- [Oracle Java SE 21 — PKIXParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors và tham số PKIX.
- [Oracle Java SE 21 — SSLParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification trong TLS handshake.
- [Oracle Java SE 21 — X509ExtendedTrustManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): xác thực certificate chain và endpoint identity.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS hiện hành, certificate trust, SAN, hostname và thuật toán mạnh.

**Ghi nhớ:** Một hệ thống mật mã tốt phải chấp nhận dữ liệu đúng và từ chối dữ liệu sai một cách nhất quán. Với AES-GCM, test sai key, ciphertext, tag, nonce và AAD; quản lý nonce duy nhất theo từng key qua cả concurrency/restart; với X.509, tách kiểm tra thời hạn, PKIX trust chain, mục đích sử dụng và SAN/hostname. Không dùng trust-all, không bỏ qua lỗi xác thực, và luôn xác minh rằng thất bại không làm lộ plaintext hay tạo side effect.