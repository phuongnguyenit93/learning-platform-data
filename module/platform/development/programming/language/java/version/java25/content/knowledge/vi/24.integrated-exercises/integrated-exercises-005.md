# Dẫn xuất khóa theo nhiều mục đích bằng KDF và xác minh bằng vector kiểm thử

## Mục tiêu bài học

Một giao thức bảo mật thường cần nhiều khóa từ cùng một bí mật gốc: khóa mã hóa dữ liệu, khóa xác thực, khóa cho từng chiều truyền, hoặc khóa cho từng phiên. Dùng trực tiếp một secret cho nhiều mục đích làm các thành phần phụ thuộc lẫn nhau và có thể phá vỡ giả định bảo mật của thuật toán. **Key Derivation Function (KDF)** tạo ra các khóa con độc lập theo ngữ cảnh từ input keying material (IKM).

Từ JDK 25, Java cung cấp API KDF ổn định theo **JEP 510 — Key Derivation Function API**. API nằm trong module `java.base`, package `javax.crypto`, và có thể dùng HKDF theo RFC 5869 thông qua các thuật toán chuẩn `HKDF-SHA256`, `HKDF-SHA384` và `HKDF-SHA512`.

Bài **Dẫn xuất khóa theo nhiều mục đích bằng KDF và xác minh bằng vector kiểm thử** thuộc chương **Thực hành tổng hợp** của module **JAVA_VERSION_JAVA25**. Bài xây dựng một luồng thực hành hoàn chỉnh: nhận shared secret từ một key agreement đã xác thực, dẫn xuất các khóa con theo từng mục đích bằng nhãn `info`, rồi kiểm tra implementation bằng test vectors công khai của RFC 5869.

Sau bài này, bạn có thể:

1. Phân biệt KDF, hash, MAC, encryption và password-based KDF.
2. Giải thích hai giai đoạn HKDF-Extract và HKDF-Expand.
3. Dùng `KDF` và `HKDFParameterSpec` trong JDK 25 mà không bật preview.
4. Dẫn xuất nhiều khóa từ cùng IKM với các nhãn `info` khác nhau để tách biệt mục đích.
5. Chọn output algorithm và độ dài phù hợp với AES hoặc HMAC.
6. Phân biệt vai trò của salt, IKM, PRK và info.
7. Xác minh PRK/OKM bằng test vectors RFC 5869.
8. Xử lý provider, khóa không extractable và giới hạn thread-safety.
9. Tránh dùng HKDF trực tiếp trên mật khẩu có entropy thấp.
10. Thiết kế test, kiểm tra lỗi và quy trình bảo vệ key material.

> **Trạng thái hiện hành:** JDK 24 giới thiệu KDF API dưới dạng preview theo JEP 478. Trong JDK 25, JEP 510 đưa API thành tính năng ổn định. Ví dụ trong bài dùng JDK 25 trở lên và không cần `--enable-preview`. Không lấy cú pháp preview của JDK 24 làm cấu hình cho dự án mới.

## 1. Bài toán: một bí mật gốc, nhiều mục đích

Giả sử hai peer đã hoàn tất một key agreement như ECDH và thu được cùng một shared secret. Giao thức cần:

- Khóa AES-256-GCM cho dữ liệu client gửi tới server.
- Khóa AES-256-GCM khác cho dữ liệu server gửi tới client.
- Khóa HMAC-SHA-256 riêng cho một luồng audit được giao thức quy định.
- Có thể dẫn xuất lại đúng các khóa khi hai bên có cùng shared secret, salt và context.

Không nên dùng nguyên shared secret làm khóa AES, khóa HMAC và khóa cho cả hai chiều. Thay vào đó, dùng KDF để tạo các khóa con với ngữ cảnh riêng:

~~~mermaid
flowchart TD
    A["Shared secret từ key agreement"] --> B["HKDF-Extract<br/>salt + IKM"]
    B --> C["PRK"]
    C --> D["HKDF-Expand<br/>info: AES-GCM / client-to-server"]
    C --> E["HKDF-Expand<br/>info: AES-GCM / server-to-client"]
    C --> F["HKDF-Expand<br/>info: HMAC / audit"]
    D --> G["Kc2s"]
    E --> H["Ks2c"]
    F --> I["Kaudit"]
~~~

Các khóa con có nguồn gốc từ cùng một IKM nhưng được ràng buộc với những mục đích khác nhau. Một thay đổi ở `info` tạo ra đầu ra dẫn xuất khác theo thiết kế HKDF.

**Tách biệt theo mục đích (domain separation)** là nguyên tắc cốt lõi. Nhãn `info` phải mô tả đầy đủ giao thức, phiên bản, thuật toán, vai trò và chiều truyền khi các thuộc tính đó ảnh hưởng tới cách dùng khóa.

## 2. KDF làm gì và không làm gì?

KDF nhận key material cùng tham số bổ sung để tạo key material mới có cấu trúc và độ dài phù hợp.

| Thành phần | Vai trò |
|---|---|
| IKM | Bí mật đầu vào, ví dụ shared secret từ key agreement |
| Salt | Giá trị bổ sung cho bước Extract; thường không cần giữ bí mật |
| PRK | Pseudorandom key được tạo ở bước Extract |
| Info | Context công khai, đặc thù ứng dụng/mục đích cho bước Expand |
| OKM | Output keying material được tạo ở bước Expand |

KDF không phải:

- **Hash:** hash thông thường không có key và không thay thế quy trình dẫn xuất khóa.
- **MAC:** MAC xác thực dữ liệu bằng khóa; KDF tạo khóa.
- **Encryption:** KDF không mã hóa hoặc giải mã payload.
- **Random generator:** KDF không tự tạo entropy mới; chất lượng đầu ra phụ thuộc vào IKM và giả định của thuật toán.
- **Password hashing/KDF chậm:** HKDF không được thiết kế để chống brute-force mật khẩu yếu.

Nếu IKM có entropy thấp, HKDF không biến nó thành một secret mạnh. Không lấy mật khẩu người dùng rồi đưa trực tiếp vào HKDF để tạo khóa AES.

## 3. HKDF theo RFC 5869

HKDF là HMAC-based Extract-and-Expand Key Derivation Function. Nó chia quá trình thành hai bước.

### 3.1. Extract

\[
PRK = \operatorname{HMAC}(salt, IKM)
\]

Extract gom entropy của IKM thành một pseudorandom key có độ dài bằng hash output:

- HKDF-SHA256 tạo PRK 32 byte.
- HKDF-SHA384 tạo PRK 48 byte.
- HKDF-SHA512 tạo PRK 64 byte.

Salt thường là dữ liệu ngẫu nhiên hoặc pseudorandom, có thể công khai. Nếu giao thức không cung cấp salt, RFC 5869 quy định dùng chuỗi byte 0 có độ dài bằng HashLen.

Salt không thay thế IKM và không phải mật khẩu. Biết salt không đủ để tái tạo khóa nếu không có IKM.

### 3.2. Expand

Expand dùng PRK, context `info` và độ dài mong muốn để tạo OKM:

\[
OKM = HKDF\text{-}Expand(PRK, info, L)
\]

`info` có thể chứa:

- Tên giao thức và phiên bản.
- Mục đích của khóa.
- Thuật toán đích và độ dài khóa.
- Vai trò client/server.
- Chiều truyền client-to-server hoặc server-to-client.
- Session identifier hoặc transcript hash.
- Context đã được encode theo định dạng không nhập nhằng.

Với cùng PRK nhưng `info` khác nhau, đầu ra được tách biệt theo ngữ cảnh. Không dùng cùng một nhãn cho hai mục đích khác nhau.

### 3.3. Giới hạn độ dài đầu ra

RFC 5869 giới hạn:

\[
L \le 255 \times HashLen
\]

Với HKDF-SHA256:

\[
L_{max} = 255 \times 32 = 8160\ bytes
\]

Đây là giới hạn giao thức của HKDF, không phải gợi ý rằng ứng dụng nên tạo khóa dài hàng kilobyte. Khóa AES-128 thường cần 16 byte; AES-256 cần 32 byte; HMAC-SHA-256 thường dùng key material 32 byte trong ví dụ này.

## 4. Tách biệt mục đích bằng info

Nếu dẫn xuất ba khóa từ cùng IKM, mỗi khóa phải có một nhãn khác nhau.

Ví dụ:

| Khóa | Nhãn info minh họa | Output |
|---|---|---|
| Client gửi tới server | `orders/v1/aes-256-gcm/client-to-server` | AES 32 byte |
| Server gửi tới client | `orders/v1/aes-256-gcm/server-to-client` | AES 32 byte |
| Audit MAC | `orders/v1/hmac-sha-256/audit` | HmacSHA256 32 byte |

Các nhãn này chỉ là ví dụ cho một giao thức do ứng dụng tự thiết kế. Nếu dùng TLS, HPKE hoặc một giao thức chuẩn khác, phải dùng đúng label construction do đặc tả giao thức quy định; không tự thay thế bằng nhãn tùy ý.

### 4.1. Context phải được mã hóa không nhập nhằng

Không ghép các trường tùy ý mà không có ranh giới:

~~~text
protocol + version + role + session
~~~

Nếu các trường không có độ dài cố định hoặc delimiter được quy định, hai bộ giá trị khác nhau có thể tạo cùng chuỗi byte sau khi nối.

Một cách minh họa là encode mỗi trường bằng length-prefix:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

static byte[] encodeInfo(String purpose, byte[] context) {
    byte[] label = purpose.getBytes(StandardCharsets.UTF_8);

    return ByteBuffer.allocate(
                    Integer.BYTES + label.length
                    + Integer.BYTES + context.length)
            .putInt(label.length)
            .put(label)
            .putInt(context.length)
            .put(context)
            .array();
}
~~~

Định dạng này dùng số nguyên 32-bit big-endian cho độ dài, theo mặc định của `ByteBuffer`. Hai bên phải thống nhất chính xác encoding. Trong production, giới hạn kích thước các trường và dùng encoding do protocol định nghĩa.

### 4.2. Không đặt secret vào info

`info` thường là context công khai, không phải nơi chứa bí mật. Không cần giấu nhãn. Mục đích của `info` là gắn kết đầu ra với một context cụ thể để tránh dùng nhầm khóa.

Nếu context chứa transcript hash hoặc session ID, giá trị đó cần được tạo và xác thực theo giao thức. KDF không tự xác minh tính xác thực của context.

## 5. KDF API ổn định trong JDK 25

JDK 25 cung cấp:

- `javax.crypto.KDF`: tạo instance KDF và dẫn xuất key/data.
- `javax.crypto.KDFParameters`: nhóm tham số khởi tạo cho KDF.
- `javax.crypto.spec.HKDFParameterSpec`: mô tả Extract, Expand hoặc Extract-then-Expand cho HKDF.

Các tên thuật toán HKDF chuẩn:

| Tên | Hash | HashLen |
|---|---|---:|
| `HKDF-SHA256` | HMAC-SHA-256 | 32 byte |
| `HKDF-SHA384` | HMAC-SHA-384 | 48 byte |
| `HKDF-SHA512` | HMAC-SHA-512 | 64 byte |

Oracle JDK 25 cung cấp các implementation này trong SunJCE. Provider khác có thể hỗ trợ tập thuật toán khác; kiểm tra provider thực tế của deployment.

### 5.1. Khởi tạo KDF

~~~java
import javax.crypto.KDF;

KDF hkdf = KDF.getInstance("HKDF-SHA256");
~~~

`getInstance` chọn implementation thông qua JCA provider. Nếu không có provider hỗ trợ thuật toán, sẽ nhận `NoSuchAlgorithmException`.

### 5.2. Khai báo Extract-then-Expand

~~~java
import javax.crypto.spec.HKDFParameterSpec;

var parameters = HKDFParameterSpec.ofExtract()
        .addIKM(sharedSecret)
        .addSalt(salt)
        .thenExpand(info, 32);
~~~

Builder cho phép thêm nhiều phần IKM hoặc salt. Khi dùng HKDF, các phần được xử lý theo thứ tự thêm vào như một chuỗi được ghép. Builder không thread-safe; tạo builder mới cho mỗi phép dẫn xuất.

### 5.3. deriveKey và deriveData

`deriveKey` trả về `SecretKey` với thuật toán đích:

~~~java
SecretKey aesKey = hkdf.deriveKey("AES", parameters);
~~~

`deriveData` trả về raw byte array:

~~~java
byte[] outputKeyMaterial = hkdf.deriveData(parameters);
~~~

Trong ứng dụng thật, ưu tiên `deriveKey` để giữ key ở dạng `SecretKey` và truyền trực tiếp cho `Cipher` hoặc `Mac`. Dùng `deriveData` khi cần raw bytes theo contract, ví dụ kiểm tra RFC test vector hoặc khi protocol yêu cầu key material dạng byte array.

Nếu key được giữ trong hardware và không extractable, `deriveData` có thể ném `UnsupportedOperationException`. Dùng `deriveKey` khi provider có thể trả về key object phù hợp.

## 6. Dẫn xuất nhiều khóa từ cùng shared secret

Ví dụ sau minh họa cách tạo khóa AES cho hai chiều truyền và một khóa HMAC cho một mục đích riêng. Nó giả định `sharedSecret` đã được tạo từ một key agreement có xác thực; phần key agreement không nằm trong ví dụ.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

public final class SessionKeys {

    private static byte[] encodeInfo(
            String purpose,
            byte[] sessionContext) {

        byte[] label = purpose.getBytes(StandardCharsets.UTF_8);

        return ByteBuffer.allocate(
                        Integer.BYTES + label.length
                        + Integer.BYTES + sessionContext.length)
                .putInt(label.length)
                .put(label)
                .putInt(sessionContext.length)
                .put(sessionContext)
                .array();
    }

    private static SecretKey derive(
            byte[] sharedSecret,
            byte[] salt,
            byte[] sessionContext,
            String purpose,
            String keyAlgorithm,
            int keyLength) throws GeneralSecurityException {

        byte[] info = encodeInfo(purpose, sessionContext);

        var spec = HKDFParameterSpec.ofExtract()
                .addIKM(sharedSecret)
                .addSalt(salt)
                .thenExpand(info, keyLength);

        // Tạo KDF riêng cho phép dẫn xuất này.
        KDF hkdf = KDF.getInstance("HKDF-SHA256");

        return hkdf.deriveKey(keyAlgorithm, spec);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        byte[] sharedSecret = obtainSharedSecretFromKeyAgreement();
        byte[] salt = obtainPublicHandshakeSalt();
        byte[] transcriptHash = obtainAuthenticatedTranscriptHash();

        SecretKey clientToServer = derive(
                sharedSecret,
                salt,
                transcriptHash,
                "orders/v1/aes-256-gcm/client-to-server",
                "AES",
                32
        );

        SecretKey serverToClient = derive(
                sharedSecret,
                salt,
                transcriptHash,
                "orders/v1/aes-256-gcm/server-to-client",
                "AES",
                32
        );

        SecretKey auditMac = derive(
                sharedSecret,
                salt,
                transcriptHash,
                "orders/v1/hmac-sha-256/audit",
                "HmacSHA256",
                32
        );

        // Truyền SecretKey trực tiếp cho Cipher/Mac.
        // Không in key hoặc gọi getEncoded() trong luồng production.
    }

    private static byte[] obtainSharedSecretFromKeyAgreement() {
        throw new UnsupportedOperationException("Thay bằng key agreement của giao thức");
    }

    private static byte[] obtainPublicHandshakeSalt() {
        throw new UnsupportedOperationException("Thay bằng salt của giao thức");
    }

    private static byte[] obtainAuthenticatedTranscriptHash() {
        throw new UnsupportedOperationException("Thay bằng context của giao thức");
    }
}
~~~

Các method `obtain...` là placeholder, không phải API JDK. Thay chúng bằng dữ liệu từ handshake đã xác thực. Không dùng giá trị cố định trong ví dụ làm secret production.

### 6.1. Dùng khóa AES-GCM

~~~java
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
        Cipher.ENCRYPT_MODE,
        clientToServer,
        new GCMParameterSpec(128, nonce)
);

byte[] ciphertextAndTag = cipher.doFinal(plaintext);
~~~

Nonce GCM phải tuân thủ quy tắc của giao thức và không được lặp lại với cùng một key. KDF không tự quản lý nonce và việc dẫn xuất một key mới không thay thế cơ chế nonce an toàn.

### 6.2. Dùng khóa HMAC

~~~java
import javax.crypto.Mac;

Mac mac = Mac.getInstance("HmacSHA256");
mac.init(auditMac);

byte[] tag = mac.doFinal(auditRecord);
~~~

Ví dụ HMAC là một mục đích riêng của hệ thống audit. Nếu payload đã dùng AES-GCM, không tự thêm HMAC cho cùng payload trừ khi protocol có yêu cầu được thiết kế và phân tích rõ ràng. AEAD thường đã cung cấp confidentiality và integrity.

### 6.3. Vì sao không cắt một khóa dài thành nhiều đoạn?

Không nên tự dẫn xuất một chuỗi dài rồi chia thủ công thành các đoạn mà không có thiết kế protocol. Dùng HKDF Expand với `info` riêng cho từng mục đích giúp thể hiện domain separation rõ ràng và làm cho test vector/label có thể review độc lập.

Nếu một protocol chuẩn định nghĩa một cách expand cụ thể, phải theo chính xác đặc tả đó. Không thay đổi label, thứ tự trường hoặc độ dài vì sự tiện lợi của ứng dụng.

## 7. Salt, info và IKM: cách chọn đúng

| Tham số | Có cần bí mật? | Cách chọn |
|---|---|---|
| IKM | Có | Shared secret có entropy cao từ key agreement hoặc nguồn key material được bảo vệ |
| Salt | Thường không | Giá trị ngẫu nhiên/pseudorandom phù hợp với giao thức; dùng cùng giá trị ở cả hai peer |
| Info | Không | Context công khai, có cấu trúc, duy nhất theo mục đích và phiên bản |
| Output length | Không | Đúng độ dài mà thuật toán đích yêu cầu |

### 7.1. IKM phải có chất lượng mật mã

Ví dụ phù hợp:

- Shared secret từ ECDH/DH đã được xác thực.
- Secret key ngẫu nhiên có đủ entropy.
- Key material được cung cấp bởi HSM hoặc provider hỗ trợ key không extractable.

Không dùng:

- User ID.
- Session ID đơn thuần.
- Timestamp.
- UUID công khai.
- Mật khẩu người dùng chưa qua password KDF.
- Hash của dữ liệu công khai.

Những dữ liệu này có thể nằm trong context, nhưng không thay thế IKM bí mật có entropy.

### 7.2. Salt không phải mật khẩu hay encryption key

Salt có thể được truyền công khai cùng handshake hoặc lưu cùng metadata. Vai trò của nó là làm tham số cho Extract, không phải để mã hóa IKM.

Nếu giao thức yêu cầu salt ngẫu nhiên, tạo bằng `SecureRandom` và truyền nó tới cả hai peer. Không tạo salt riêng biệt ở hai bên nếu họ cần dẫn xuất cùng khóa.

### 7.3. Info phải tách biệt rõ

Dùng nhãn có version và purpose. Ví dụ:

- `product-x/v1/aes-256-gcm/c2s`
- `product-x/v1/aes-256-gcm/s2c`
- `product-x/v1/hmac-sha-256/audit`

Không dùng nhãn chung chung như `key`, `secret` hoặc `session` cho mọi output. Khi đổi protocol version hoặc thuật toán, dùng label/version mới theo thiết kế.

## 8. Tách Extract và Expand thành hai giai đoạn

Thông thường, `thenExpand` thực hiện cả Extract và Expand trong một lần. Khi cần giữ PRK hoặc tách giai đoạn theo protocol, API cũng hỗ trợ Extract-only và Expand-only.

### 8.1. Extract-only

~~~java
var extractSpec = HKDFParameterSpec.ofExtract()
        .addIKM(sharedSecret)
        .addSalt(salt)
        .extractOnly();

SecretKey prk = KDF.getInstance("HKDF-SHA256")
        .deriveKey("HmacSHA256", extractSpec);
~~~

PRK là key material trung gian. Không dùng PRK trực tiếp cho encryption/MAC của ứng dụng nếu protocol yêu cầu Expand. Thông thường, PRK chỉ làm đầu vào cho các lần Expand.

### 8.2. Expand-only

~~~java
var expandSpec = HKDFParameterSpec.expandOnly(
        prk,
        info,
        32
);

SecretKey aesKey = KDF.getInstance("HKDF-SHA256")
        .deriveKey("AES", expandSpec);
~~~

Expand-only phù hợp khi PRK đã được tạo ở giai đoạn trước hoặc được cung cấp theo một giao thức có định nghĩa rõ. Phải bảo vệ PRK như một secret có khả năng tạo ra các khóa con.

### 8.3. Không lưu PRK nếu không cần

Nếu ứng dụng chỉ cần các khóa con trong cùng một phiên, dùng Extract-then-Expand và không lưu PRK lâu hơn cần thiết. Nếu protocol cần tái sử dụng PRK, quản lý vòng đời, quyền truy cập, persistence và rotation theo threat model.

## 9. Xác minh bằng RFC 5869 Test Case 1

Không nên xác nhận KDF chỉ bằng cách chạy hai lần rồi thấy kết quả giống nhau. Một implementation sai nhưng deterministic vẫn có thể cho cùng kết quả mỗi lần. Dùng test vector công khai với đầu vào và đầu ra đã biết.

RFC 5869 Appendix A.1 quy định vector HKDF-SHA256:

| Thành phần | Giá trị |
|---|---|
| Hash | SHA-256 |
| IKM | Byte `0x0b` lặp 22 lần |
| Salt | `000102030405060708090a0b0c` |
| Info | `f0f1f2f3f4f5f6f7f8f9` |
| L | 42 byte |
| PRK | `077709362c2e32df0ddc3f0dc47bba63 90b6c73bb50f9c3122ec844ad7c2b3e5` |
| OKM | `3cb25f25faacd57a90434f64d0362f2a 2d2d0a90cf1a5a4c5db02d56ecc4c5bf 34007208d5b887185865` |

### 9.1. Code kiểm tra PRK và OKM

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.KDF;
import javax.crypto.spec.HKDFParameterSpec;

public final class HkdfRfc5869Vector1 {

    private static final HexFormat HEX = HexFormat.of();

    private static void assertHex(
            String expectedHex,
            byte[] actual,
            String name) {

        byte[] expected = HEX.parseHex(expectedHex);

        if (!MessageDigest.isEqual(expected, actual)) {
            throw new AssertionError(name + " does not match RFC 5869");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] ikm = HEX.parseHex("0b".repeat(22));
        byte[] salt = HEX.parseHex(
                "000102030405060708090a0b0c");
        byte[] info = HEX.parseHex(
                "f0f1f2f3f4f5f6f7f8f9");

        KDF hkdf = KDF.getInstance("HKDF-SHA256");

        byte[] actualPrk = hkdf.deriveData(
                HKDFParameterSpec.ofExtract()
                        .addIKM(ikm)
                        .addSalt(salt)
                        .extractOnly()
        );

        assertHex(
                "077709362c2e32df0ddc3f0dc47bba63"
              + "90b6c73bb50f9c3122ec844ad7c2b3e5",
                actualPrk,
                "PRK"
        );

        byte[] actualOkm = hkdf.deriveData(
                HKDFParameterSpec.ofExtract()
                        .addIKM(ikm)
                        .addSalt(salt)
                        .thenExpand(info, 42)
        );

        assertHex(
                "3cb25f25faacd57a90434f64d0362f2a"
              + "2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
              + "34007208d5b887185865",
                actualOkm,
                "OKM"
        );

        System.out.println("RFC 5869 test case 1: PASS");
    }
}
~~~

Test này xác minh riêng Extract output và Extract-then-Expand output. `MessageDigest.isEqual` được dùng để so sánh byte array; không in IKM, PRK hoặc OKM ra log.

### 9.2. Vì sao test cả PRK và OKM?

Nếu chỉ test OKM, lỗi ở Extract hoặc Expand đều có thể khiến kết quả sai nhưng khó xác định giai đoạn. Kiểm tra riêng PRK giúp khoanh vùng:

- PRK sai: xem IKM, salt, thuật toán hash hoặc Extract.
- PRK đúng nhưng OKM sai: xem info, output length hoặc Expand.
- Cả hai đúng: implementation phù hợp với vector đã kiểm tra.

## 10. Xác minh trường hợp salt và info rỗng

RFC 5869 Appendix A.3 cung cấp vector SHA-256 với salt và info có độ dài 0:

| Thành phần | Giá trị |
|---|---|
| Hash | SHA-256 |
| IKM | Byte `0x0b` lặp 22 lần |
| Salt | Không cung cấp; dùng HashLen byte 0 |
| Info | Chuỗi rỗng |
| L | 42 byte |
| PRK | `19ef24a32c717b167f33a91d6f648bdf 96596776afdb6377ac434c1c293ccb04` |
| OKM | `8da4e775a563c18f715f802a063c5a31 b8a11f5c5ee1879ec3454e5f3c738d2d 9d201395faa4b61a96c8` |

Ví dụ code:

~~~java
byte[] ikm = HexFormat.of().parseHex("0b".repeat(22));

KDF hkdf = KDF.getInstance("HKDF-SHA256");

byte[] prk = hkdf.deriveData(
        HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .extractOnly()
);

byte[] okm = hkdf.deriveData(
        HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .thenExpand(new byte[0], 42)
);
~~~

Khi không gọi `addSalt`, implementation HKDF áp dụng quy tắc salt mặc định của RFC. `new byte[0]` biểu diễn info rỗng trong ví dụ này.

## 11. Kiểm thử domain separation

Sau khi xác minh implementation bằng RFC vector, cần test quy tắc thiết kế của ứng dụng.

~~~java
byte[] infoC2S = encodeInfo(
        "orders/v1/aes-256-gcm/client-to-server",
        transcriptHash
);

byte[] infoS2C = encodeInfo(
        "orders/v1/aes-256-gcm/server-to-client",
        transcriptHash
);

var c2sSpec = HKDFParameterSpec.ofExtract()
        .addIKM(sharedSecret)
        .addSalt(salt)
        .thenExpand(infoC2S, 32);

var s2cSpec = HKDFParameterSpec.ofExtract()
        .addIKM(sharedSecret)
        .addSalt(salt)
        .thenExpand(infoS2C, 32);
~~~

Với cùng IKM và salt, hai nhãn khác nhau tạo ra hai key output khác nhau. Test nên xác nhận:

- Hai peer dùng cùng protocol label sẽ dẫn xuất được cùng key.
- Đổi chiều truyền sẽ tạo key khác.
- Đổi protocol version sẽ tạo key khác.
- Đổi session context sẽ tạo key khác.
- Hai purpose khác nhau không dùng chung info.

Không coi phép so sánh “hai key không bằng nhau” là bằng chứng duy nhất về bảo mật. Điều quan trọng là protocol định nghĩa label/context đúng, hai peer mã hóa giống nhau và các test vector kiểm tra thuật toán.

## 12. Chọn provider và làm việc với key không extractable

JCA cho phép nhiều provider cung cấp KDF. Trong Oracle JDK 25, SunJCE hỗ trợ:

- `HKDF-SHA256`
- `HKDF-SHA384`
- `HKDF-SHA512`

SunPKCS11 cũng hỗ trợ HKDF-SHA256/384/512 trong JDK 25 khi PKCS#11 token và provider có implementation tương ứng. Khả năng thực tế phụ thuộc HSM/token, cấu hình và provider.

### 12.1. Chỉ định provider

~~~java
Provider provider = Security.getProvider("SunJCE");

KDF hkdf = KDF.getInstance("HKDF-SHA256", provider);
~~~

Trong production, chọn provider theo chính sách triển khai. Không hard-code `SunJCE` nếu hệ thống bắt buộc dùng HSM/FIPS provider. Kiểm tra thuật toán và tham số được provider hỗ trợ.

### 12.2. Delayed provider selection

Nếu không chỉ định provider, JDK có thể trì hoãn việc chọn provider cho đến khi `deriveKey` hoặc `deriveData` được gọi. Điều này hữu ích khi key material nằm trong phần cứng và chỉ một provider nhất định có thể sử dụng.

Nếu gọi `getProviderName()` hoặc `getParameters()` trước khi dẫn xuất, provider có thể được chọn sớm theo thuật toán/tham số nhưng chưa chắc xử lý được key material thực tế. Với non-extractable key, hãy để provider selection diễn ra cùng lúc với phép dẫn xuất hoặc chỉ định provider đã xác minh.

### 12.3. Truyền SecretKey thay vì export bytes

Builder hỗ trợ:

~~~java
HKDFParameterSpec.ofExtract()
        .addIKM(secretKeyFromHsm)
        .addSalt(salt)
        .thenExpand(info, 32);
~~~

Điều này cho phép đưa key không extractable vào KDF nếu provider hỗ trợ. Không gọi `getEncoded()` để lấy bytes của key HSM chỉ nhằm đưa vào một API khác nếu provider có thể xử lý key trực tiếp.

## 13. Thread-safety và vòng đời đối tượng

Java SE 25 API ghi rõ `KDF` không thread-safe nếu implementation không công bố điều khác. `HKDFParameterSpec.Builder` cũng không thread-safe.

Thực hành an toàn:

- Tạo KDF instance riêng cho mỗi luồng hoặc mỗi phép dẫn xuất.
- Không chia sẻ một builder giữa nhiều thread.
- Không sửa đổi input byte arrays trong lúc đang dẫn xuất.
- Dùng `SecretKey` thay vì raw bytes khi có thể.
- Không lưu PRK/IKM trong static field hoặc log.
- Giữ key object trong phạm vi vòng đời của phiên/giao thức.
- Xóa byte arrays do ứng dụng sở hữu khi có thể; hiểu rằng Java không bảo đảm xóa mọi bản sao trong heap/provider.

Không tạo một singleton `KDF` dùng đồng thời từ nhiều request mà không có đồng bộ hóa.

## 14. Giới hạn và lỗi cần xử lý

| Tình huống | Hành vi/ngoại lệ cần kiểm tra |
|---|---|
| Tên KDF không tồn tại | `NoSuchAlgorithmException` |
| Provider không có HKDF tương ứng | `NoSuchAlgorithmException` |
| Tham số không hợp lệ | `InvalidAlgorithmParameterException` |
| Output length bằng 0 | `IllegalArgumentException` khi tạo HKDF parameter spec |
| Output vượt 255 × HashLen | Provider HKDF từ chối |
| PRK quá ngắn cho Expand | Provider HKDF từ chối |
| deriveData với output không extractable | Có thể ném `UnsupportedOperationException` |
| Provider không hỗ trợ key material | Không thể thực hiện dẫn xuất với key đó |
| KDF instance được chia sẻ đồng thời | Không có bảo đảm thread-safety |
| Builder được chia sẻ đồng thời | Không thread-safe |

Không bắt `Exception` chung rồi bỏ qua lỗi. Lỗi dẫn xuất khóa phải làm thao tác bảo mật thất bại theo hướng an toàn; không tiếp tục bằng một khóa mặc định hoặc khóa rỗng.

## 15. HKDF không phải password KDF

HKDF phù hợp với IKM đã có entropy đủ mạnh, ví dụ shared secret từ một key agreement. Mật khẩu con người có entropy thấp và dễ bị thử offline.

Nếu đầu vào là password, dùng password-based KDF với salt và work factor phù hợp:

- `PBKDF2WithHmacSHA256` thông qua `SecretKeyFactory` là lựa chọn chuẩn có sẵn trong JDK.
- Nếu chính sách yêu cầu memory-hard password hashing, dùng Argon2id/scrypt từ thư viện/provider đã được đánh giá và duy trì.
- Không tự thiết kế vòng lặp hash hoặc lặp HKDF để thay thế password KDF.

HKDF có thể được dùng **sau** password KDF nếu protocol cần tách purpose từ key material đã được password KDF tạo ra, nhưng không thay thế bước làm chậm đoán mật khẩu.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Dùng cùng một key cho AES và HMAC | Phá vỡ key separation | Dẫn xuất riêng bằng info khác nhau |
| Dùng cùng info cho hai chiều truyền | Hai phía có thể dùng chung key ngoài ý muốn | Thêm role/direction vào label |
| Dùng user ID làm IKM | Không đủ entropy | Dùng shared secret/key material mật mã |
| Dùng HKDF trực tiếp với password | Dễ bị brute-force offline | Dùng PBKDF2/Argon2id/scrypt phù hợp |
| Không có protocol version trong info | Khó tách khóa giữa phiên bản | Gắn version và suite vào context |
| Nối context không có cấu trúc | Có nguy cơ encoding nhập nhằng | Dùng encoding chuẩn/length-prefix |
| Không xác minh RFC test vectors | Có thể triển khai sai Extract/Expand | Test PRK và OKM bằng vector chuẩn |
| Chỉ test tính deterministic | Implementation sai vẫn có thể lặp lại kết quả | So sánh với output chuẩn đã công bố |
| Dùng deriveData cho key HSM không extractable | Không lấy được output raw bytes | Dùng deriveKey và provider phù hợp |
| Chia sẻ KDF/builder giữa các thread | Race condition hoặc hành vi không xác định | Tạo instance/builder riêng |
| Ghi key hoặc PRK ra log | Lộ bí mật | Không log key material |
| Tái sử dụng nonce AES-GCM với cùng key | Mất bảo mật AEAD nghiêm trọng | Dùng nonce unique theo protocol |

## 17. Ma trận kiểm thử nghiệm thu

| Mã | Kịch bản | Kết quả mong đợi |
|---|---|---|
| K1 | RFC 5869 A.1 — kiểm tra PRK SHA-256 | Khớp 32 byte PRK công bố |
| K2 | RFC 5869 A.1 — kiểm tra OKM | Khớp 42 byte output công bố |
| K3 | RFC 5869 A.3 — salt/info rỗng | Khớp PRK và OKM công bố |
| K4 | Cùng IKM, salt, info, length | Dẫn xuất lặp lại cho cùng output |
| K5 | Đổi salt | Output thay đổi |
| K6 | Đổi info | Output thay đổi |
| K7 | Đổi purpose label | Không dùng lại cùng key |
| K8 | Đổi chiều client-to-server/server-to-client | Dẫn xuất hai key khác nhau |
| K9 | AES output length 32 byte | Thu được SecretKey AES phù hợp |
| K10 | HMAC-SHA256 output length 32 byte | Thu được SecretKey HmacSHA256 |
| K11 | Output length bằng 0 | Bị từ chối |
| K12 | Output length vượt 255 × HashLen | Bị từ chối |
| K13 | PRK ngắn hơn HashLen trong Expand-only | Bị provider từ chối |
| K14 | Provider không hỗ trợ HKDF-SHA256 | Nhận lỗi thuật toán/provider |
| K15 | IKM là SecretKey non-extractable | Provider tương thích có thể xử lý trực tiếp |
| K16 | deriveData trên output non-extractable | Xử lý UnsupportedOperationException |
| K17 | Sử dụng key với Cipher AES/GCM | Cipher khởi tạo đúng với key/nonce hợp lệ |
| K18 | Sử dụng key với Mac HmacSHA256 | Tạo và xác minh tag đúng |
| K19 | KDF instance riêng từng thread | Không chia sẻ state không thread-safe |
| K20 | HKDF nhận password trực tiếp | Thiết kế bị từ chối trong review bảo mật |

## 18. Bài thực hành tổng hợp

Xây dựng module `SessionKeyDerivation` cho một giao thức truyền dữ liệu nội bộ. Hai peer đã có shared secret từ key agreement và cùng biết salt cùng transcript hash của handshake.

Thực hiện:

1. Tạo helper encode `info` theo cấu trúc length-prefix.
2. Dẫn xuất khóa AES-256-GCM cho chiều client-to-server.
3. Dẫn xuất khóa AES-256-GCM khác cho chiều server-to-client.
4. Dẫn xuất khóa HmacSHA256 cho mục đích audit riêng được protocol quy định.
5. Giữ output ở dạng `SecretKey`; không in hoặc serialize key.
6. Dùng key AES với `Cipher.getInstance("AES/GCM/NoPadding")` và nonce unique.
7. Dùng key HMAC với `Mac.getInstance("HmacSHA256")`.
8. Xác minh RFC 5869 A.1 cho PRK và OKM.
9. Xác minh RFC 5869 A.3 cho trường hợp không cung cấp salt và info rỗng.
10. Kiểm tra domain separation bằng cách đổi purpose, direction và protocol version.
11. Kiểm tra output length, provider failure và non-extractable key behavior nếu môi trường có HSM.
12. Chạy ma trận K1–K20 và ghi lại provider/JDK build.
13. Review threat model: entropy của IKM, salt, context, nonce, key lifetime và rotation.
14. Viết runbook xử lý khi hai peer dẫn xuất key không khớp.

**Sản phẩm nghiệm thu:** mã nguồn dẫn xuất nhiều khóa, test RFC vector, test domain separation, bảng K1–K20, tài liệu encoding context, kết quả kiểm thử provider và checklist bảo vệ key material.

## 19. Biên dịch và chạy trên JDK 25

KDF API là API ổn định trong JDK 25; không cần bật preview.

~~~bash
javac --release 25 -d out HkdfRfc5869Vector1.java
java -cp out HkdfRfc5869Vector1
~~~

Kết quả mong đợi:

~~~text
RFC 5869 test case 1: PASS
~~~

Các lớp KDF và HKDFParameterSpec thuộc module `java.base`; ứng dụng classpath thông thường không cần thêm module hoặc dependency bên ngoài.

Nếu build bằng Maven/Gradle, đặt compiler release là 25 hoặc cao hơn và chạy test trên JDK tương ứng. Không thêm `--enable-preview` cho KDF API trong JDK 25.

## 20. Checklist bảo mật trước khi đưa vào production

- IKM đến từ nguồn bí mật có entropy đủ mạnh.
- HKDF chỉ được dùng cho key material phù hợp, không dùng trực tiếp trên password.
- Salt được tạo và chia sẻ đúng theo protocol.
- Info có cấu trúc, version, purpose, algorithm và direction rõ ràng.
- Không dùng chung label cho nhiều mục đích.
- Dùng `deriveKey` để giữ key ở dạng `SecretKey` khi có thể.
- Chỉ dùng `deriveData` khi cần raw bytes và đã đánh giá khả năng extract.
- Kiểm tra provider và thuật toán được hỗ trợ trên đúng JDK/runtime.
- Không chia sẻ KDF instance hoặc Builder giữa các thread đồng thời.
- Không ghi IKM, PRK, OKM hoặc key ra log.
- Quản lý nonce AES-GCM riêng biệt và không tái sử dụng với cùng key.
- Thực hiện rotation và giới hạn vòng đời khóa theo protocol.
- Xác minh RFC vectors trước khi review domain separation của ứng dụng.
- Không tự thay label construction của một giao thức chuẩn.
- Có test âm cho provider, length và tham số không hợp lệ.
- Review threat model và interoperability giữa các peer.

## Tài liệu tham khảo chính thức

- [JEP 510 — Key Derivation Function API](https://openjdk.org/jeps/510): đưa KDF API thành tính năng ổn định trong JDK 25.
- [JEP 478 — Key Derivation Function API (Preview)](https://openjdk.org/jeps/478): lịch sử preview ban đầu trong JDK 24.
- [Oracle Java SE 25 — KDF](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html): `getInstance`, `deriveKey`, `deriveData`, provider selection và thread-safety.
- [Oracle Java SE 25 — HKDFParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html): Extract, Expand và Extract-then-Expand parameters.
- [Oracle Java SE 25 — HKDFParameterSpec.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.Builder.html): `addIKM`, `addSalt`, `extractOnly`, `thenExpand` và giới hạn builder.
- [Oracle Java SE 25 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên chuẩn HKDF-SHA256, HKDF-SHA384 và HKDF-SHA512.
- [Oracle Java SE 25 — JDK Providers](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html): thuật toán KDF được SunJCE và provider liên quan hỗ trợ.
- [Oracle Java SE 25 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html): cách khởi tạo KDF, HKDF Extract/Expand và dẫn xuất SecretKey.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869): đặc tả HKDF, salt/info semantics, giới hạn output và test vectors Appendix A.
- [Oracle Java SE 25 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/25/security/security-developer-guide.pdf): ví dụ HKDF, provider, KDF và hướng dẫn sử dụng trong Java.
