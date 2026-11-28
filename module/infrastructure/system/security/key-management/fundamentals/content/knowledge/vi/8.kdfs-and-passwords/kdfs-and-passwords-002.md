# KDF từ secret: Dẫn xuất khóa mật mã an toàn từ bí mật gốc

Một ứng dụng cần hai khóa: **AES-256** để mã hóa dữ liệu và **HMAC-SHA-256** để xác thực thông điệp. Hệ thống đang có một bí mật gốc chất lượng cao được tạo bởi KMS/HSM hoặc có một shared secret từ giao thức thỏa thuận khóa. Có nên cắt bí mật gốc thành hai nửa, lấy **SHA256(secret)** làm khóa AES, rồi sử dụng lại chính khóa đó cho HMAC? **Không.** Những thao tác tùy tiện này không có hợp đồng phân tách mục đích, dễ tạo quan hệ khó kiểm chứng giữa các khóa và làm việc xoay vòng, phân quyền trở nên rối rắm.

**Key Derivation Function (KDF)** là một cơ chế dẫn xuất một hoặc nhiều khóa/giá trị mật mã từ **input keying material** cùng các tham số và ngữ cảnh được xác định. Khi đầu vào là một **secret có entropy đủ mạnh**, **HKDF (HMAC-based Extract-and-Expand Key Derivation Function)** là ví dụ điển hình: nó chuyển bí mật đầu vào thành vật liệu khóa có dạng phù hợp và dẫn xuất **các khóa con khác nhau theo mục đích**. HKDF không phải mã hóa, không tạo entropy từ hư không, không tự phân phối khóa và không thay thế việc kiểm soát quyền truy cập.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, KDF từ secret kết nối mật mã đối xứng và bất đối xứng, ECDH, HMAC, AES-GCM, KMS/HSM, envelope encryption và toàn bộ vòng đời khóa: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi, hủy**, có chính sách truy cập và kiểm toán rõ ràng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **KDF từ secret** và phân biệt nó với **password hashing**, encryption, key wrapping và hash thông thường.
2. Mô tả **HKDF-Extract**, **HKDF-Expand**, vai trò của **IKM**, **salt**, **PRK**, **info** và **OKM**.
3. Dẫn xuất khóa AES-GCM và HMAC riêng biệt từ một secret bằng **domain separation** có version.
4. Hiểu vì sao KDF không tăng entropy của secret yếu và vì sao khóa đầu ra không tự có chính sách nonce, quyền hoặc vòng đời.
5. Áp dụng KDF vào **ECDH/X25519**, key hierarchy, các dịch vụ KMS/HSM và thiết kế cần phục hồi dữ liệu cũ.
6. Thực hiện ví dụ Java 17 với **HKDF-HMAC-SHA-256**, đồng thời tránh để lộ root secret và derived keys.

## 2. KDF từ secret thực sự giải quyết điều gì?

Giả sử hệ thống có **root secret** dài 32 byte được tạo ngẫu nhiên bằng CSPRNG. Ứng dụng muốn tạo các khóa dùng cho mục đích riêng:

~~~text
                      Root secret / IKM
                   (giữ kín, entropy cao)
                               |
                     HKDF-Extract(salt)
                               |
                          PRK bí mật
                               |
                 +-------------+-------------+
                 |                           |
         HKDF-Expand(info-A, 32)    HKDF-Expand(info-B, 32)
                 |                           |
            AES-256 key                HMAC-SHA-256 key
          mục đích DATA_ENC          mục đích REQUEST_MAC
~~~

**Cùng secret, salt và info, một KDF xác định sẽ tạo cùng kết quả**. Nếu thay info (chẳng hạn nhãn mục đích hoặc tenant), đầu ra được thiết kế để không thể đoán quan hệ hữu ích với khóa còn lại nếu giả định an ninh của KDF và nguồn secret được đáp ứng.

### 2.1. Phân loại đầu vào và đầu ra

| Thành phần | Ý nghĩa | Bí mật? | Cần lưu ý |
|---|---|---|---|
| **IKM (Input Keying Material)** | Bí mật đầu vào, ví dụ random root secret hoặc ECDH shared secret | **Có** | Nguồn entropy/chất lượng và cách xác thực phải phù hợp |
| **Salt (HKDF)** | Giá trị bổ trợ cho bước Extract | Thường **không** | Khác salt của password verifier về mục đích và yêu cầu vận hành |
| **PRK (Pseudorandom Key)** | Khóa trung gian sinh bởi Extract | **Có** | Không log, không công bố hoặc dùng bừa làm DEK |
| **Info (HKDF)** | Ngữ cảnh cho Expand: protocol, tenant, purpose, version, role | Thường **không** | Phải được mã hóa không nhập nhằng, chuẩn hóa và đáng tin |
| **L** | Độ dài keying material đầu ra cần lấy | Không | Phải phù hợp thuật toán và giới hạn HKDF |
| **OKM (Output Keying Material)** | Byte khóa được dẫn xuất, có thể làm AES/HMAC key | **Có** | Hưởng chính sách bảo mật và vòng đời của key material |

Các tên **IKM**, **PRK**, **OKM** có ý nghĩa riêng trong HKDF, không phải chuẩn đặt tên bắt buộc cho mọi loại KDF. Một secret có thể là nguồn dẫn xuất nhiều khóa, nhưng việc cấp quyền cho từng **derived key** vẫn cần thiết.

### 2.2. Những gì KDF không làm

- **Không tăng entropy có thật** của nguồn đầu vào. Nếu secret chỉ là mã PIN hoặc một mật khẩu phổ biến, dẫn xuất 32 byte không biến nó thành 256 bit bí mật chống đoán.
- **Không phải encryption**: không có “decrypt HKDF” để khôi phục IKM từ OKM; cũng không dùng HKDF để mã hóa file.
- **Không thay thế key wrapping**: muốn lưu hoặc chuyển một DEK cần khôi phục, phải dùng cơ chế lưu trữ/bao bọc khóa thích hợp, không chỉ lưu **hash(DEK)**.
- **Không tự phân phối khóa cho đối tác**: bên cần dẫn xuất cùng OKM phải có đúng vật liệu bí mật đầu vào (hoặc tham gia giao thức tạo cùng bí mật) cùng salt/info.
- **Không xác thực nguồn của secret**: ECDH với public key bị tráo vẫn có thể tạo ra shared secret và HKDF output nhìn hợp lệ.
- **Không tự bảo đảm an toàn khi sử dụng khóa**: một khóa AES-GCM dẫn xuất đúng vẫn thất bại nếu nonce bị tái sử dụng với cùng khóa.

## 3. HKDF: Extract rồi Expand

**HKDF** được mô tả trong **RFC 5869** và xây dựng từ **HMAC**, thường với SHA-256 hoặc một hàm băm mật mã phù hợp. Nó có hai giai đoạn tách biệt:

~~~mermaid
flowchart TD
    I["IKM: secret từ CSPRNG hoặc ECDH"] --> E["HKDF-Extract"]
    S["Salt"] --> E
    E --> P["PRK bí mật"]
    P --> X1["HKDF-Expand(info = tenant-42 / AES-GCM / v1, L=32)"]
    P --> X2["HKDF-Expand(info = tenant-42 / HMAC / v1, L=32)"]
    P --> X3["HKDF-Expand(info = tenant-43 / AES-GCM / v1, L=32)"]
    X1 --> K1["AES-256 key tenant-42"]
    X2 --> K2["HMAC key tenant-42"]
    X3 --> K3["AES-256 key tenant-43"]
~~~

### 3.1. Bước Extract: đưa secret về dạng phù hợp

Với một hàm băm mật mã và HMAC tương ứng:

\[
\text{PRK} = \operatorname{HKDF\text{-}Extract}(\text{salt}, \text{IKM})
            = \operatorname{HMAC}_{\text{salt}}(\text{IKM}).
\]

IKM có thể có cấu trúc hoặc phân phối chưa thuận tiện để dùng trực tiếp làm khóa cho nhiều thuật toán. Extract giúp tạo một **PRK** có đặc tính phù hợp để mở rộng theo mô hình an ninh của HKDF, với điều kiện IKM chứa **đủ entropy và không bị đối thủ biết**.

**Salt của HKDF** thường có thể công khai và đôi khi được tạo ngẫu nhiên. RFC 5869 cho phép salt là tùy chọn; khi không cung cấp, trong HKDF-Extract sử dụng chuỗi byte 0 có độ dài bằng HashLen theo quy định. Tuy vậy, **nếu có thể dùng salt độc lập, phù hợp, hãy sử dụng nó và quản lý cách tái tạo**. Không được tự cho rằng thêm một salt công khai sẽ cứu được IKM có entropy thấp.

Nếu salt được tạo mới ngẫu nhiên mà cả hai phía hoặc bản ghi lưu trữ cần dẫn xuất lại cùng khóa, **phải lưu/chuyển đúng salt** như metadata được bảo vệ tính toàn vẹn/ngữ cảnh. Mất salt tương ứng có thể khiến không thể tái tạo được OKM.

### 3.2. Bước Expand: tạo khóa con theo info

Với PRK và một chuỗi byte **info** đã xác định:

\[
\begin{aligned}
T(0)&=\epsilon,\\
T(i)&=\operatorname{HMAC}_{\text{PRK}}\left(T(i-1)\parallel\text{info}\parallel i\right),\\
\text{OKM}&=\operatorname{first}_L\left(T(1)\parallel T(2)\parallel\cdots\right).
\end{aligned}
\]

Ở đây **i** được mã hóa bằng **một byte duy nhất**, bắt đầu từ 1; **\(\parallel\)** là nối byte; **\(\epsilon\)** là chuỗi rỗng.

Đối với **HKDF-HMAC-SHA-256**, **HashLen = 32 byte**, và HKDF-Expand giới hạn:

\[
0 \le L \le 255\times32=8160\text{ byte}.
\]

Ứng dụng thực tế thường yêu cầu ít hơn nhiều, chẳng hạn **L=32** cho AES-256 key hoặc HMAC key dài 256 bit. Không dùng KDF để tạo một luồng byte không giới hạn bằng cách bỏ qua bộ đếm/giới hạn tiêu chuẩn.

### 3.3. HKDF có tính xác định

| IKM | Salt | Info | L | Kết quả |
|---|---|---|---|---|
| Secret A | Salt S | **AES-GCM / v1** | 32 | Khóa AES K1 |
| Secret A | Salt S | **AES-GCM / v1** | 32 | **Đúng cùng K1** |
| Secret A | Salt S | **HMAC / v1** | 32 | Khóa K2 khác K1 với xác suất áp đảo |
| Secret A | Salt S | **AES-GCM / v2** | 32 | Khóa K3 khác theo ngữ cảnh |
| Secret B | Salt S | **AES-GCM / v1** | 32 | Khóa K4 phụ thuộc Secret B |
| Secret A | Salt S2 | **AES-GCM / v1** | 32 | Khóa K5 phụ thuộc salt mới |

Nếu chỉ đổi **label** từ v1 sang v2 mà vẫn giữ root secret, hai đầu phải thống nhất version để tái tạo đúng keying material. Nếu cần dữ liệu cũ, phải giữ khả năng dẫn xuất phiên bản v1 theo policy hoặc chuyển đổi dữ liệu trước khi ngừng hỗ trợ.

## 4. Domain separation: Vì sao phải có info?

**Domain separation** nghĩa là mỗi nhóm khóa, mỗi giao thức và mỗi mục đích sử dụng có một ngữ cảnh dẫn xuất riêng, giúp giảm nguy cơ dùng nhầm material cho những thao tác không liên quan.

Thay vì:

~~~text
aesKey  = HKDF(secret, salt, info = "", L = 32)
hmacKey = HKDF(secret, salt, info = "", L = 32)
~~~

**Hai phép gọi này sẽ cho cùng 32 byte** nếu cùng một KDF. Dùng chúng cho cả AES-GCM lẫn HMAC không phải là phân tách khóa.

Nên thiết kế:

~~~text
aesKey  = HKDF(
    secret, salt,
    info = Encode("app-v1", "tenant-42", "DATA_ENCRYPTION", "AES-256-GCM"),
    L = 32)

hmacKey = HKDF(
    secret, salt,
    info = Encode("app-v1", "tenant-42", "REQUEST_AUTHENTICATION", "HMAC-SHA-256"),
    L = 32)
~~~

**Encode** ở đây phải là một hàm mã hóa **byte không nhập nhằng**. Không tùy tiện nối **tenant + "|" + purpose** khi dữ liệu có thể chứa dấu phân cách. Nên dùng quy tắc **prefix độ dài từng trường**, field cố định, byte UTF-8 rõ ràng và version.

### 4.1. Info nên chứa gì?

| Trường ví dụ | Vai trò |
|---|---|
| **protocol/application identifier** | Tách khóa của hai ứng dụng/giao thức khác nhau |
| **purpose** | Tách AES encryption khỏi HMAC, wrapping, hoặc các chức năng khác |
| **tenantId / ownerId** | Tách miền logic giữa tenant nếu threat model cần |
| **direction / role** | Tách khóa client-to-server khỏi server-to-client khi giao thức có hai chiều |
| **algorithm identifier** | Tách khóa cho AES-256-GCM và thuật toán khác |
| **schema/key version** | Diễn đạt phiên bản của cây khóa, định dạng và policy |
| **session/document context** | Dẫn xuất khóa theo phiên hoặc đối tượng khi giao thức quy định |

**Info thường không bí mật**. Nhưng mọi giá trị có ý nghĩa an ninh phải được lấy từ **nguồn đã xác thực**, được xác minh và đóng gói nhất quán. Nếu client được quyền tự khai **tenantId=other-tenant** và có quyền yêu cầu root key của hệ thống dẫn xuất tương ứng, domain separation không cứu được lỗi phân quyền.

### 4.2. Salt, info và nonce không phải một thứ

- **Salt của HKDF:** tác động bước Extract, giúp tạo PRK theo ngữ cảnh salt; có thể công khai, thường cần ghi nhận để tái tạo.
- **Info của HKDF:** nhãn/ngữ cảnh của từng derived key, phục vụ domain separation.
- **Nonce của AES-GCM:** giá trị dùng cho **mỗi lần mã hóa**, phải **không trùng với cùng khóa AES**. Nonce không được tạo bằng cách lấy một **info cố định** rồi dùng mãi cho mọi bản ghi.
- **Salt của password hashing:** thường ngẫu nhiên riêng mỗi mật khẩu và lưu cùng password verifier để chống precomputation/cross-user correlation; không có nghĩa giống hệt mọi chính sách salt của HKDF.

KDF cung cấp một khóa AES hợp lệ không có nghĩa AES-GCM tự cấp nonce an toàn. Nếu tất cả instance cùng dẫn xuất **một DEK cho tenant-42**, chúng vẫn phải phối hợp chiến lược nonce trên **tổng số lần mã hóa bằng DEK ấy**.

## 5. Ví dụ Java 17: HKDF-HMAC-SHA-256 từ secret ngẫu nhiên

Ví dụ dùng thư viện mật mã chuẩn **javax.crypto.Mac** của Java 17, tự thể hiện các bước HKDF theo RFC 5869 để làm rõ thuật toán. Trong production, nên ưu tiên **implementation KDF đã được kiểm chứng của thư viện/provider** và kiểm tra interoperability/test vectors thay vì duy trì một bản tự viết. Đoạn mã này là **mẫu học tập**, không bao gồm phân quyền KMS/HSM, lưu trữ, backup hay điều phối multi-instance.

Ví dụ tạo một **IKM 32 byte ngẫu nhiên** (mô phỏng secret được cấp phát an toàn), dùng salt 32 byte, sau đó dẫn xuất **một khóa AES** và **một khóa HMAC khác nhau** cho cùng tenant. Nó còn chứng minh AES-GCM mã hóa/giải mã và HMAC tạo tag bằng hai derived keys riêng.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class HkdfFromSecretDemo {
    private static final String HMAC_ALG = "HmacSHA256";
    private static final int HASH_LEN = 32;  // SHA-256
    private static final SecureRandom RANDOM = new SecureRandom();

    // RFC 5869: PRK = HMAC(salt, IKM).
    private static byte[] extract(byte[] salt, byte[] ikm)
            throws GeneralSecurityException {
        if (ikm == null || ikm.length == 0) {
            throw new IllegalArgumentException("IKM is required");
        }
        byte[] effectiveSalt = (salt == null || salt.length == 0)
                ? new byte[HASH_LEN] : salt;
        Mac hmac = Mac.getInstance(HMAC_ALG);
        hmac.init(new SecretKeySpec(effectiveSalt, HMAC_ALG));
        return hmac.doFinal(ikm);
    }

    // RFC 5869: T(i) = HMAC(PRK, T(i-1) || info || counter).
    private static byte[] expand(byte[] prk, byte[] info, int length)
            throws GeneralSecurityException {
        if (prk == null || prk.length < HASH_LEN) {
            throw new IllegalArgumentException("Invalid PRK");
        }
        if (info == null) {
            throw new IllegalArgumentException("Explicit info required");
        }
        if (length <= 0 || length > 255 * HASH_LEN) {
            throw new IllegalArgumentException("HKDF output size invalid");
        }
        Mac hmac = Mac.getInstance(HMAC_ALG);
        hmac.init(new SecretKeySpec(prk, HMAC_ALG));
        byte[] okm = new byte[length];
        byte[] previous = new byte[0];
        int offset = 0;
        int counter = 1;
        while (offset < length) {
            hmac.update(previous);
            hmac.update(info);
            hmac.update((byte) counter);
            byte[] block = hmac.doFinal();
            int copy = Math.min(block.length, length - offset);
            System.arraycopy(block, 0, okm, offset, copy);
            Arrays.fill(previous, (byte) 0); // best-effort cleanup
            previous = block;
            offset += copy;
            counter++;
        }
        Arrays.fill(previous, (byte) 0);
        return okm;
    }

    // Biểu diễn nhãn có cấu trúc: UTF-8 và prefix độ dài mỗi trường.
    private static byte[] context(String tenant, String purpose, String alg)
            throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            for (String value : new String[] {
                    "SECURITY_KEY_MANAGEMENT_FUNDAMENTALS",
                    "derivation-schema-v1", tenant, purpose, alg }) {
                byte[] field = value.getBytes(StandardCharsets.UTF_8);
                out.writeInt(field.length);
                out.write(field);
            }
        }
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        byte[] rootSecret = new byte[32];
        byte[] salt = new byte[32];
        RANDOM.nextBytes(rootSecret);
        RANDOM.nextBytes(salt);

        byte[] prk = extract(salt, rootSecret);
        byte[] aesMaterial = expand(
                prk, context("tenant-42", "DATA_ENCRYPTION", "AES-256-GCM"),
                32);
        byte[] macMaterial = expand(
                prk, context("tenant-42", "REQUEST_MAC", "HMAC-SHA-256"),
                32);

        System.out.println("AES key length: " + aesMaterial.length);
        System.out.println("MAC key length: " + macMaterial.length);
        System.out.println("Same key material: "
                + MessageDigest.isEqual(aesMaterial, macMaterial));

        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce); // Chỉ một lần mã hóa trong demo
        byte[] aad = context("tenant-42", "RECORD", "record-123");

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(aesMaterial, "AES"),
                new GCMParameterSpec(128, nonce));
        encryptor.updateAAD(aad);
        byte[] ciphertextWithTag = encryptor.doFinal(
                "Dữ liệu minh họa".getBytes(StandardCharsets.UTF_8));

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE,
                new SecretKeySpec(aesMaterial, "AES"),
                new GCMParameterSpec(128, nonce));
        decryptor.updateAAD(aad);
        byte[] restored = decryptor.doFinal(ciphertextWithTag);
        System.out.println("Restored: "
                + new String(restored, StandardCharsets.UTF_8));

        Mac requestMac = Mac.getInstance(HMAC_ALG);
        requestMac.init(new SecretKeySpec(macMaterial, HMAC_ALG));
        byte[] tag = requestMac.doFinal(
                "event=created".getBytes(StandardCharsets.UTF_8));
        System.out.println("MAC tag length: " + tag.length);

        Arrays.fill(rootSecret, (byte) 0);
        Arrays.fill(prk, (byte) 0);
        Arrays.fill(aesMaterial, (byte) 0);
        Arrays.fill(macMaterial, (byte) 0);
        // Byte-array cleanup chỉ là best effort; Java/provider có thể
        // giữ những bản sao khác của secret trong bộ nhớ.
    }
}
~~~

Lưu thành **HkdfFromSecretDemo.java**, sau đó chạy với **JDK 17+**:

~~~bash
javac HkdfFromSecretDemo.java
java HkdfFromSecretDemo
~~~

Kết quả dự kiến:

~~~text
AES key length: 32
MAC key length: 32
Same key material: false
Restored: Dữ liệu minh họa
MAC tag length: 32
~~~

Giá trị cụ thể của các khóa thay đổi giữa các lần chạy vì chương trình sinh **rootSecret** và **salt** mới. Hai derived keys khác nhau nhờ **info khác nhau**, với xác suất xảy ra trùng ngẫu nhiên không đáng kể khi cơ chế được dùng đúng.

### 5.1. Giới hạn của ví dụ Java

1. **Secret đang nằm trong JVM.** Với hệ thống dùng KMS/HSM, việc đọc raw root key ra ứng dụng có thể bị cấm; dịch vụ chỉ được dùng API **DeriveKey** nếu được hỗ trợ, hoặc một thiết kế dẫn xuất ở trong ranh giới tin cậy.
2. **Cần lưu thông tin để tái tạo.** Demo không lưu root secret, salt hoặc metadata nên sau khi chương trình kết thúc **không thể dẫn xuất lại chính các khóa ấy**. Muốn đọc dữ liệu lưu lâu dài, cần kế hoạch lưu trữ, wrapping, version và recovery riêng.
3. **Không tự triển khai lại HKDF khi có thư viện chuẩn phù hợp.** Code nhằm minh họa RFC 5869; production nên có test vectors, kiểm thử liên vận và xem xét provider hỗ trợ.
4. **Không in key material.** Chỉ in độ dài, kết quả giải mã dữ liệu giả và độ dài tag. Không in IKM, PRK, OKM, private key, raw DEK hoặc nội dung khách hàng vào log.
5. **Chưa có IAM và audit.** Một service được gọi KDF với root secret của nhiều tenant vẫn có thể dẫn xuất tất cả khóa tenant, dù info có chứa tenant ID.
6. **Nonce AES-GCM cần quản lý riêng.** Code chỉ mã hóa một lần với một nonce ngẫu nhiên 96 bit. Khi dùng cùng derived DEK cho nhiều dữ liệu, phải ngăn nonce trùng trên toàn bộ instance sử dụng DEK đó và giới hạn số lần mã hóa.
7. **Không dùng HKDF như password hashing.** Root secret trong demo là 32 byte từ CSPRNG; nếu thay bằng mật khẩu do người dùng chọn, mô hình an ninh hoàn toàn khác.
8. **Xóa byte[] không bảo đảm zeroization toàn bộ.** Provider/JVM có thể sao chép secret vào object, bộ nhớ native hoặc heap không kiểm soát được; cần giảm phạm vi và thời gian sống của secret theo khả năng nền tảng.

## 6. KDF từ secret khác password hashing như thế nào?

Trong chương **KDF và mật khẩu**, hai loại đầu vào cần được tách bạch:

| Tiêu chí | KDF từ secret entropy cao | Password-based KDF / password hashing |
|---|---|---|
| Nguồn đầu vào | Random keying material từ CSPRNG/KMS hoặc shared secret từ giao thức | Mật khẩu do con người chọn, thường entropy thấp |
| Ví dụ | **HKDF**, KDF theo NIST SP 800-108 khi phù hợp | **Argon2id**, scrypt, PBKDF2 theo chính sách |
| Mục tiêu chính | Rút trích và dẫn xuất nhiều khóa con có domain separation | Làm tốn chi phí cho từng lần thử đoán mật khẩu, tạo password verifier hoặc khóa từ mật khẩu |
| Salt | Tùy mô hình HKDF, thường công khai và cần khôi phục đúng | Thường ngẫu nhiên riêng cho mỗi mật khẩu/verifier |
| Chi phí tính toán | Có chủ đích tương đối nhẹ | Có chủ đích tốn CPU, bộ nhớ hoặc iteration |
| Nếu bí mật đầu vào yếu | **Vẫn yếu**, HKDF không làm chậm đáng kể offline guesses | Chi phí thử đoán tăng, nhưng không thể biến mật khẩu yếu thành bất khả đoán |

Nếu ứng dụng lưu mật khẩu tài khoản, không làm như sau:

~~~text
stored = HKDF(passwordUtf8, salt, info="user-login", L=32)
~~~

Rồi kết luận an toàn vì đầu ra 256 bit. HKDF được thiết kế cho vật liệu khóa có entropy thích hợp, không phải cơ chế làm chậm các cuộc tấn công dò mật khẩu. Để lưu password verifier, cần **password hashing chuyên dụng**, salt riêng từng người dùng, tham số được định kỳ xem xét và kiểm soát đăng nhập/rate limiting.

### 6.1. Khi nào dùng PBKDF2?

**PBKDF2** có thể dẫn xuất một khóa từ mật khẩu theo công thức có iteration và salt; nó cũng có thể làm nền cho password verifier trong bối cảnh/chính sách nhất định. Nhưng PBKDF2 không mặc nhiên thay được **HKDF cho shared secret từ ECDH**, và HKDF không thay PBKDF2/Argon2id cho mật khẩu. Chọn KDF phải dựa trên **nguồn entropy, mô hình tấn công và giao thức**, không chỉ tên “KDF”.

Khi cần mã hóa dữ liệu dựa trên mật khẩu người dùng, hệ thống có thể dùng password-based KDF để tạo keying material rồi mã hóa bằng AEAD. Phải xét riêng khả năng dò mật khẩu offline khi attacker lấy được ciphertext/salt, rủi ro quên mật khẩu và kế hoạch khôi phục. Nếu muốn quản lý khóa dữ liệu chuyên nghiệp, có thể dùng mô hình **DEK + KEK** thay vì để mật khẩu người dùng trực tiếp quyết định toàn bộ khả năng giải mã.

## 7. Dẫn xuất khóa từ ECDH/X25519 shared secret

Trong một giao thức **key agreement**, hai bên có thể tính ra một shared secret bằng ECDH hoặc X25519 mà **không gửi chính shared secret qua mạng**. Sau đó KDF biến shared secret thành một hoặc nhiều khóa phiên thích hợp.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Server B
    A->>A: Tạo private_A / public_A tạm thời
    B->>B: Tạo private_B / public_B tạm thời
    A->>B: public_A cùng thông tin giao thức
    B->>A: public_B cùng thông tin xác thực
    A->>A: X25519(private_A, public_B) -> sharedSecret
    B->>B: X25519(private_B, public_A) -> sharedSecret
    Note over A,B: Xác thực peer, transcript và đầu vào theo giao thức
    A->>A: HKDF(sharedSecret, salt, info) -> session keys
    B->>B: HKDF(sharedSecret, salt, info) -> session keys
    Note over A,B: Hai bên có cùng session keys nếu ngữ cảnh giống nhau
~~~

Để giao thức an toàn:

1. **Xác thực đúng peer/public key.** ECDH/X25519 thuần túy không chứng minh danh tính đối tác và có thể bị tấn công man-in-the-middle nếu public key bị tráo.
2. **Kiểm tra input và kết quả theo chuẩn.** X25519 có quy tắc xử lý đầu vào và một số giá trị shared secret đặc biệt; giao thức/thư viện phải có kiểm tra phù hợp, bao gồm trường hợp shared secret all-zero khi cần.
3. **Ràng buộc transcript và vai trò.** Info/salt hoặc key schedule theo giao thức cần gắn phiên, thuật toán, public key liên quan và chiều gửi/nhận để tránh nhầm khóa giữa ngữ cảnh.
4. **Tách khóa theo direction.** Client-to-server và server-to-client nên có label khác nhau nếu dùng khóa phiên riêng; không tự dùng một khóa/nonce space cho cả hai chiều.
5. **Xóa ephemeral secret khi hết mục đích.** Forward secrecy đòi hỏi một giao thức được thiết kế và vận hành đúng; HKDF đơn lẻ không tạo forward secrecy.

Ví dụ:

~~~text
sharedSecret = X25519(privateA, trustedPublicB)
prk = HKDF-Extract(transcriptSalt, sharedSecret)

clientWriteKey = HKDF-Expand(prk, "proto-v1/client-write/AES-GCM", 32)
serverWriteKey = HKDF-Expand(prk, "proto-v1/server-write/AES-GCM", 32)
~~~

Đây là **pseudocode giảng giải**, không phải thông số hoàn chỉnh của TLS hay HPKE. Với những giao thức đã chuẩn hóa như **TLS 1.3** hoặc **HPKE**, phải dùng **key schedule, label, transcript binding và encoding của chính chuẩn đó** thay vì thay bằng chuỗi tự đặt trong ví dụ.

## 8. KDF trong cây khóa: Root key, tenant key, session key

KDF có thể hỗ trợ **key hierarchy**, nhưng chỉ khi ranh giới tin cậy và chính sách quyền được thiết kế rõ ràng.

~~~mermaid
flowchart TD
    R["Root secret được bảo vệ"] --> P["HKDF-Extract / root PRK"]
    P --> T1["HKDF-Expand(info tenant-42 / v1)"]
    P --> T2["HKDF-Expand(info tenant-43 / v1)"]
    T1 --> A["Key DATA_ENC tenant-42"]
    T1 --> B["Key REQUEST_MAC tenant-42"]
    T2 --> C["Key DATA_ENC tenant-43"]
    T2 --> D["Key REQUEST_MAC tenant-43"]
~~~

**Hình trên là sơ đồ mục tiêu tách domain**, không phải quyền truy cập tự động. Một dịch vụ được biết **root secret** có thể tự tính cả khóa tenant-42 lẫn tenant-43 nếu biết label, bất kể tên tenant có mặt trong info. Nếu muốn **cô lập quyền tenant**, có thể:

- Để root secret trong KMS/HSM/derivation service và chỉ cho workload gọi **DeriveKey cho tenant đã được xác thực**, theo policy.
- Phân tách root key theo tenant/môi trường nếu yêu cầu cô lập mạnh hơn, thay vì dùng một root key toàn cục.
- Cấp **derived key** hoặc handle cho workload đúng mục đích, không cấp root secret hoặc quyền derivation tùy ý.
- Ghi audit **actor, tenant, root key version, derivation purpose, result** mà không ghi secret.

### 8.1. NIST SP 800-108 và các KDF khác

Ngoài HKDF, có những KDF dựa trên pseudorandom function (PRF), như **counter-mode KDF** theo **NIST SP 800-108**, trong đó **key**, **label**, **context**, **counter** và **L** được kết hợp theo cấu trúc của chuẩn. Một số KMS/HSM sử dụng biến thể derivation riêng hoặc KDF theo tiêu chuẩn/khả năng phần cứng.

**Không thể thay thế tùy ý HKDF bằng NIST SP 800-108 hoặc ngược lại**: cùng root key và nhãn mà khác KDF sẽ cho output khác; mỗi scheme có công thức, yêu cầu và encoding riêng. Thiết kế phải lưu đủ **KDF identifier, parameters, label encoding, version** và kiểm thử liên vận trước khi chuyển đổi.

### 8.2. KMS/HSM có luôn hỗ trợ HKDF không?

**Không thể giả định.** Một hệ thống KMS có thể chỉ cung cấp **GenerateDataKey, Encrypt, Decrypt, Sign, Verify, HMAC, Wrap/Unwrap** mà không cho **DeriveKey**; một HSM khác có thể hỗ trợ các cơ chế dẫn xuất nhưng yêu cầu key attributes riêng. Tính khả dụng còn phụ thuộc thuật toán, key type, policy và nhà cung cấp.

Nếu root key được đánh dấu **non-exportable**, đừng tìm cách đọc raw root key để chạy HKDF trong JVM trái với policy. Hãy dùng KDF được hỗ trợ trong ranh giới tin cậy, một derivation service chuyên dụng được cấp quyền hoặc điều chỉnh kiến trúc. **Non-exportable** bảo vệ byte key material, nhưng API DeriveKey có quyền quá rộng vẫn có thể tiết lộ các derived keys hoặc cho phép lạm dụng key schedule.

## 9. Derivation khác wrapping và envelope encryption

Hai thiết kế sau có mục đích khác nhau:

| Mô hình | Cách nhận DEK | Đặc tính phục hồi |
|---|---|---|
| **Derive DEK** | Tính **DEK = KDF(rootSecret, salt, info)** | Muốn lấy lại đúng DEK cần **rootSecret, salt, info, version/KDF** giống ban đầu |
| **Wrap DEK** | Sinh DEK ngẫu nhiên, dùng KEK **Wrap(DEK)** rồi lưu wrapped DEK | Muốn lấy lại DEK cần wrapped DEK và quyền dùng KEK đúng |
| **Hybrid key transport** | Bọc DEK bằng public key người nhận hoặc KEM/KDF theo protocol | Cần private key/decapsulation và protocol tương ứng |

**KDF không tạo ciphertext của DEK có thể đảo ngược.** Nếu hệ thống chỉ lưu **HKDF(root, context)** (một derived key) rồi xóa cả root và derived key, không có phép “unwrap” để khôi phục root. Ngược lại, wrapped DEK được thiết kế để khôi phục DEK bằng khóa bảo vệ được cấp quyền.

### 9.1. Derived DEK với AES-GCM

Một derived key dài 32 byte có thể được dùng như AES-256 key khi source secret và KDF phù hợp. Sau khi có key:

1. Tạo nonce/IV theo chiến lược bảo đảm không trùng **trong phạm vi chính derived DEK đó**.
2. Mã hóa plaintext bằng **AES-GCM**, cung cấp AAD ràng buộc record/tenant/version theo nghiệp vụ.
3. Lưu **nonce + ciphertext + tag + metadata tham chiếu root key/KDF/salt/info** đủ để khôi phục đúng DEK, mà không lưu raw root secret.
4. Khi giải mã, xác thực IAM, resolve đúng root version hoặc key handle, dẫn xuất DEK cùng ngữ cảnh rồi xác minh GCM tag.
5. Giới hạn tổng số lần mã hóa trên **mỗi derived DEK**, kể cả nhiều instance và khôi phục sau sự cố.

**Derived DEK mới không tự đổi ciphertext cũ.** Nếu thay root key version, cần dẫn xuất đúng derived DEK cũ cho dữ liệu cũ, hoặc giải mã và mã hóa lại dưới khóa mới có kiểm soát.

### 9.2. Rủi ro khi dùng một root key cho mọi đối tượng

Root key chung là **điểm ảnh hưởng tập trung**: nếu bị lộ, đối thủ có thể tái tạo các derived keys mà họ biết ngữ cảnh, salt và version. Domain separation giúp tách các mục đích về mật mã nhưng **không vô hiệu hóa root-secret compromise**.

Tương tự, nếu chỉ “xóa derived key của record-123” nhưng vẫn giữ root secret và biết context dẫn xuất, hệ thống có thể **dẫn xuất lại đúng khóa đã xóa**. Vì vậy **crypto-erasure từng bản ghi không được bảo đảm chỉ bằng việc xóa derived key**. Cần mô hình key hierarchy hoặc key material riêng có thể hủy thực sự, chẳng hạn per-object random DEK được wrap bởi KEK, khi bài toán yêu cầu hủy độc lập.

## 10. Vòng đời secret gốc và các khóa dẫn xuất

~~~mermaid
flowchart TD
    A["Tạo/nhận IKM từ nguồn an toàn"] --> B["Gắn owner, rootKeyId, version, policy"]
    B --> C["Giữ kín root; xác lập salt và derivation schema"]
    C --> D["Dẫn xuất khóa theo purpose/tenant/session"]
    D --> E["Cấp quyền sử dụng derived key và audit"]
    E --> F["Giới hạn sử dụng, giám sát sự cố và thời hạn"]
    F --> G["Rotate root/key version hoặc dẫn xuất version mới"]
    G --> H["Dữ liệu mới dùng key schedule mới"]
    H --> I["Xử lý decrypt/verify dữ liệu cũ hoặc chuyển đổi"]
    I --> J["Disable, thu hồi và hủy khi không còn phụ thuộc"]
~~~

| Giai đoạn | Câu hỏi thiết kế | Lưu ý |
|---|---|---|
| **Generation** | Root secret được sinh bằng CSPRNG, ECDH hay nhập từ nguồn nào? | Xác thực nguồn, entropy và key purpose |
| **Provisioning** | Ai giữ root, ai chỉ có quyền DeriveKey, ai chỉ dùng derived key? | Least privilege, tách tenant/môi trường |
| **Storage** | Có cần lưu root để phục hồi? Salt/info/version được lưu ra sao? | Tránh mất khả năng decrypt dữ liệu dài hạn |
| **Use** | KDF nào, Hash/PRF nào, info format, L và algorithm nào? | Domain separation, registry tin cậy, không cho caller tự chọn tùy ý |
| **Audit** | Có ghi actor, keyId/version, purpose, kết quả, thời điểm? | Không log IKM/PRK/OKM |
| **Rotation** | Đổi root key, salt hay info version? | Đổi bất kỳ đầu vào nào có thể làm derived key thay đổi |
| **Revocation** | Làm sao chặn việc dẫn xuất và sử dụng key cũ? | Disable root/API, thu hồi quyền workload và xử lý cached derived keys |
| **Destruction** | Có dữ liệu hoặc backup nào còn phụ thuộc root/version cũ? | Hủy quá sớm mất khả năng phục hồi; hủy derived key đơn lẻ có thể không đủ |

### 10.1. Root rotation không giống DEK rewrap

Với KDF, khi đổi **root-v1 → root-v2**, cùng **salt/info** sẽ tạo các khóa con khác nhau. Dữ liệu cũ được AES-GCM mã hóa bằng derived DEK từ v1 **không tự giải mã bằng derived DEK v2**. Cần giữ quyền dẫn xuất v1 theo thời hạn được chấp nhận, hoặc thực hiện **decrypt/re-encrypt** dữ liệu cũ.

Với mô hình **DEK ngẫu nhiên được wrap bởi KEK**, chỉ đổi KEK và rewrap cùng DEK thường **không đòi hỏi mã hóa lại dữ liệu**. Đây là khác biệt kiến trúc lớn. Không gọi việc thay root của KDF là “rewrap” trừ khi có bước wrap/unwrap key material thực tế.

### 10.2. Thu hồi và cache

Một KMS có thể **disable root key** và ngăn lệnh DeriveKey mới, nhưng derived key bản rõ đã được đưa vào nhiều JVM vẫn có thể còn tồn tại và tiếp tục được dùng cho đến khi ứng dụng xóa hoặc kết thúc phiên. Thiết kế thu hồi cần có chính sách **TTL của derived key, cache invalidation, khả năng dừng workload, rotation, thu hồi token/credential và audit**.

Nếu root hoặc PRK nghi bị lộ, không chỉ thay label **v1 → v2** và tiếp tục dùng cùng bí mật đã lộ. Kẻ tấn công sở hữu root/PRK có thể tính các nhãn mới khi biết context. Cần **thay thế secret gốc**, xem xét toàn bộ derived keys và dữ liệu liên quan, đồng thời đánh giá khả năng re-encrypt hoặc thu hồi quyền theo kế hoạch.

### 10.3. Crypto agility và phiên bản hóa

Một bản ghi có thể lưu metadata:

~~~json
{
  "formatVersion": 1,
  "kdf": "HKDF-HMAC-SHA256",
  "rootKeyRef": "tenant-42-root",
  "rootKeyVersion": "v3",
  "salt": "<BASE64_PUBLIC_SALT>",
  "derivationSchema": "app-key-derivation-v1",
  "purpose": "DATA_ENCRYPTION",
  "derivedKeyAlgorithm": "AES-256-GCM",
  "nonce": "<BASE64_12_BYTE_NONCE>",
  "ciphertextWithTag": "<BASE64_CIPHERTEXT_PLUS_TAG>"
}
~~~

Đây chỉ là **schema minh họa**, không phải định dạng chuẩn. Cần định nghĩa chính xác **info được tái dựng từ những trường nào, thứ tự/encoding thế nào, root được resolve và cấp quyền ra sao**. Metadata an ninh phải được xác thực và đối chiếu với ngữ cảnh nghiệp vụ; nếu không, đối thủ có thể sửa key reference/purpose hoặc khiến ứng dụng dùng sai domain.

Nếu cần đổi **HKDF-HMAC-SHA256** sang một KDF hoặc policy khác, phải có **version và lộ trình đọc dữ liệu cũ**. Không thể đổi một nhãn thuật toán trong metadata rồi hy vọng ciphertext cũ vẫn giải mã.

## 11. Threat model: Những lỗi thường gặp khi dẫn xuất khóa

| Lỗi | Hậu quả | Biện pháp |
|---|---|---|
| Dùng **HKDF(password)** để lưu mật khẩu | Dễ thử đoán offline; 32 byte đầu ra không tạo thêm entropy | Argon2id/scrypt/PBKDF2 theo policy, salt và work factor phù hợp |
| Lấy **SHA256(root)** rồi dùng cho mọi mục đích | Không có domain separation; dùng chung key material | HKDF hoặc KDF chuẩn với label/context riêng cho từng purpose |
| Để info rỗng cho hai khóa AES và HMAC | Hai lần dẫn xuất có thể cho **cùng OKM** | Info chứa purpose, algorithm, tenant, version |
| Nối các trường info mơ hồ | Hai bộ context khác nhau có thể tạo cùng bytes info | Encoding có version, prefix độ dài hoặc chuẩn chính tắc |
| Tin tenantId do client tự khai khi DeriveKey | Vượt ranh giới dữ liệu tenant khác | Workload identity, IAM, kiểm tra tenant từ nguồn tin cậy |
| Public key ECDH bị tráo nhưng vẫn chạy HKDF | Shared secret với kẻ tấn công | Xác thực peer, transcript binding, kiểm tra giao thức |
| Tái dùng cùng nonce AES-GCM với một derived DEK | Phá tính bí mật/toàn vẹn | Nonce duy nhất theo key, toàn hệ thống và sau restore |
| Cho mọi service đọc root secret | Lộ một service có thể ảnh hưởng mọi derived key | Root trong KMS/HSM/derivation service, quyền tối thiểu |
| Cho quyền DeriveKey theo context bất kỳ | Lạm dụng key schedule dù root non-exportable | Allowlist purpose/tenant, caller policy, audit |
| Không lưu salt/info/version | Không tái tạo được DEK để đọc bản mã cũ | Metadata được version hóa, integrity, backup và kiểm tra restore |
| Rotate root rồi chỉ cập nhật alias | Dữ liệu cũ vẫn gắn với derived key cũ | Giữ decrypt-only hoặc migrate/re-encrypt có kiểm soát |
| Xóa một derived key nhưng vẫn giữ root | Có thể rederive khóa tưởng đã hủy | Thiết kế crypto-erasure theo key granularity thực sự |
| Root bị lộ nhưng chỉ đổi info label | Kẻ tấn công vẫn dẫn xuất khóa mới | Tạo root mới, đánh giá toàn bộ nhánh và dữ liệu |
| Log IKM/PRK/OKM hoặc salt lẫn secret | Rò rỉ key material qua telemetry | Redaction, không log bí mật và bảo vệ audit logs |

## 12. Tình huống kiến trúc: Cấp khóa theo tenant từ derivation service

Giả sử một hệ thống Java có **Billing Service**, **Analytics Service** và **Derivation Service** được bảo vệ bởi KMS/HSM. Mục tiêu là tách keying material cho từng tenant và purpose mà không phát root secret cho các ứng dụng.

**Thiết kế đề xuất:**

1. **Provision root:** Security team tạo root key đủ entropy, gắn key reference, phiên bản, owner và state; quyền quản trị được phân tách với quyền thực thi derivation.
2. **Xác thực request:** Derivation Service nhận workload identity, suy ra tenant được phép, kiểm tra **purpose** và key scope. Không lấy tenant từ trường request chưa xác thực làm nguồn sự thật.
3. **Chọn KDF và info:** Service tạo info chuẩn hóa từ **app/domain/version/tenant/purpose/algorithm**; salt theo chính sách, được lưu/khôi phục khi cần.
4. **Dẫn xuất trong ranh giới tin cậy:** KMS/HSM thực hiện DeriveKey nếu hỗ trợ. Nếu không, kiến trúc phải có vùng xử lý secret được chấp thuận; không export root trái policy.
5. **Cấp quyền sử dụng:** Billing chỉ nhận hoặc dùng key/handle cho **DATA_ENCRYPTION** của tenant được cấp; Analytics không tự có quyền dùng **REQUEST_MAC** hoặc root.
6. **Mã hóa:** Workload dùng AES-GCM với nonce được quản lý riêng, AAD ràng buộc tenant và record. Lưu metadata đủ để tái tạo khóa và kiểm tra phiên bản khi decrypt.
7. **Audit:** Ghi principal, tenant, purpose, root version, derivation schema, outcome, thời điểm và correlation ID; không ghi raw key bytes.
8. **Rotation:** Khi root-v4 thay root-v3, dữ liệu mới sử dụng v4. Hệ thống duy trì luồng khôi phục dữ liệu cũ theo v3 hoặc chuyển đổi từng phần trước khi disable/hủy v3.

Lợi ích của thiết kế là tách purpose và giảm nhu cầu nhân bản root key. Giới hạn chính là nếu root vẫn là một điểm tin cậy toàn hệ thống, **root compromise có phạm vi ảnh hưởng lớn**. Khi yêu cầu cô lập từng tenant hoặc hủy từng đối tượng độc lập rất cao, nên đánh giá phương án **per-tenant root**, **random DEK per object** và **KEK wrapping** thay vì ép một cây HKDF toàn cục giải quyết mọi mục tiêu.

## 13. Checklist trước khi dùng KDF từ secret

1. **Nguồn IKM:** secret có entropy đủ mạnh không? Được tạo bằng CSPRNG/KMS hay đến từ giao thức key agreement đã xác thực?
2. **Đúng loại KDF:** HKDF hoặc KDF chuẩn phù hợp với **secret entropy cao**; không dùng thay password hashing khi IKM là mật khẩu yếu.
3. **Tham số rõ ràng:** Hash/PRF, salt, info, L và format version được mô tả/kiểm thử chính xác?
4. **Domain separation:** mỗi purpose, tenant, role/direction, algorithm và version cần thiết có label khác nhau và encoding không nhập nhằng?
5. **Trust boundary:** ai được biết root/PRK; ai được DeriveKey; ai chỉ được dùng derived key? Chính sách có chặn tenant khác?
6. **Tái tạo được khi cần:** lưu metadata **rootKeyRef/version, salt, derivationSchema, info context** đúng và được xác thực?
7. **Nonce và AEAD:** derived AES key có chiến lược nonce duy nhất, giới hạn invocation, AAD và tag verification đầy đủ?
8. **Vòng đời:** thay root, info hay thuật toán ảnh hưởng đến dữ liệu cũ thế nào? Có kế hoạch decrypt/re-encrypt, backup và restore?
9. **Thu hồi/hủy:** disable root có chặn các derived key đã cache không? Xóa derived key có thực sự đạt crypto-erasure mong muốn?
10. **Kiểm toán:** log principal, key ID/version, purpose, outcome mà không lộ IKM/PRK/OKM?
11. **Interoperability:** code/library/provider đã được kiểm thử theo test vectors và hợp đồng encoding/KDF suite?
12. **Ứng phó sự cố:** khi root bị lộ, có khả năng đổi secret gốc và xử lý toàn bộ nhánh khóa chịu ảnh hưởng?

### Câu hỏi tự kiểm tra

**Câu 1.** HKDF-HMAC-SHA-256 nhận mật khẩu **123456** và trả ra 32 byte. Có phải đầu ra tương đương một secret 256 bit chống đoán?

**Trả lời:** **Không.** HKDF không tăng entropy của mật khẩu. Đối thủ có thể thử các ứng viên mật khẩu rồi tính HKDF; cần password KDF/hashing chuyên dụng và mật khẩu đủ mạnh.

**Câu 2.** Từ cùng root secret và salt, nếu dùng cùng info để dẫn xuất 32 byte cho AES và HMAC, hai khóa có khác nhau không?

**Trả lời:** **Không.** HKDF là hàm xác định; cùng IKM, salt, info và L cho **đúng cùng OKM**. Phải dùng **domain separation** theo purpose.

**Câu 3.** Salt và info của HKDF có phải được giữ kín như root secret không?

**Trả lời:** **Thường không.** Chúng thường là metadata công khai, nhưng phải được bảo toàn và ràng buộc đúng với ngữ cảnh/phiên bản. Root/PRK/OKM mới là key material bí mật.

**Câu 4.** Một derived AES key được tạo đúng bằng HKDF. Có thể dùng nonce AES-GCM cố định cho tất cả record không?

**Trả lời:** **Không.** Khi mã hóa nhiều lần bằng **cùng derived key**, nonce phải không trùng. HKDF không thay thế nonce management.

**Câu 5.** Root secret vẫn còn trong KMS nhưng derived key của một record đã bị xóa khỏi database. Record đã được crypto-erasure chắc chắn chưa?

**Trả lời:** **Chưa.** Nếu root và salt/info/version vẫn tồn tại và người dùng được phép dẫn xuất, cùng derived key có thể được tạo lại. Cần mô hình hủy khóa thực sự đáp ứng granularity yêu cầu.

**Câu 6.** ECDH shared secret được đưa vào HKDF có tự xác thực peer không?

**Trả lời:** **Không.** Phải xác thực public key/peer và ràng buộc transcript theo giao thức; nếu không có thể chia sẻ bí mật với kẻ tấn công.

**Câu 7.** Sau khi đổi root key từ v2 sang v3, ciphertext mã hóa bằng derived DEK v2 có tự giải mã bằng derived DEK v3 không?

**Trả lời:** **Không.** Phải duy trì đúng cách tái tạo v2 theo chính sách hoặc giải mã/mã hóa lại dữ liệu trong quá trình migration.

**Câu 8.** Root key không export được từ HSM. Vậy quyền DeriveKey vô hạn cho mọi workload có an toàn không?

**Trả lời:** **Không.** Workload vẫn có thể dùng API để lấy hoặc sử dụng derived keys trái phép. Phải phân quyền **DeriveKey theo principal, tenant, purpose và version**, kèm audit.

**Điểm cốt lõi:** **KDF từ secret** giúp chuyển nguồn keying material đủ mạnh thành những **khóa con có purpose và ngữ cảnh riêng**, đặc biệt với mô hình **HKDF-Extract/Expand**. Nó không tạo entropy từ mật khẩu yếu, không mã hóa dữ liệu và không thay thế key wrapping. Muốn an toàn ở production, cần phối hợp **nguồn secret đáng tin, domain separation, KMS/HSM, IAM, nonce management, audit, rotation và recovery** cho từng khóa được dẫn xuất.
