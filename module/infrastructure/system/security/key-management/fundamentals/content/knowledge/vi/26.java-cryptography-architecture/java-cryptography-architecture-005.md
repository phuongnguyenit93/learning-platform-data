# Signature

Trong Java Cryptography Architecture (JCA), lớp **java.security.Signature** cung cấp API để tạo và xác minh chữ ký số. Một bên dùng private key để ký dữ liệu; bên nhận dùng public key tương ứng để xác minh chữ ký. Nếu dữ liệu bị thay đổi, chữ ký không hợp lệ hoặc public key không đúng cặp, phép xác minh sẽ thất bại.

Chữ ký số thường được dùng để xác thực nguồn gốc thông điệp ở cấp khóa, phát hiện thay đổi dữ liệu và hỗ trợ kiểm toán. Chữ ký không mã hóa nội dung, không tự chứng minh người ký là ai, không tự ngăn phát lại một thông điệp hợp lệ và không thay thế việc kiểm tra danh tính hoặc quyền truy cập ở tầng ứng dụng.

Bài học đặt API Signature trong kiến trúc JCA, giải thích cách chọn thuật toán, quản lý trạng thái sign/verify, chuẩn bị dữ liệu đầu vào, xử lý định dạng chữ ký, tích hợp keystore/HSM và kiểm thử an toàn. Các ví dụ dùng Java 17.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Giải thích vai trò của chữ ký số và sự khác nhau giữa Signature, MessageDigest và MAC.
- Mô tả cách JCA định tuyến lời gọi Signature tới provider thông qua SPI.
- Sử dụng đúng chu trình getInstance, initSign, update, sign, initVerify và verify.
- Chọn RSA-PSS, ECDSA hoặc Ed25519 theo yêu cầu bảo mật và tương thích.
- Tạo dữ liệu đầu vào có cấu trúc ổn định, tránh lỗi canonicalization và nhập nhằng trường dữ liệu.
- Xác minh chữ ký cùng danh tính và trạng thái tin cậy của public key.
- Giữ private key trong KeyStore, HSM hoặc dịch vụ quản lý khóa.
- Xử lý chữ ký detached, dữ liệu lớn, lỗi xác minh, replay và định dạng liên thông.
- Thiết kế test cho dữ liệu bị sửa, sai khóa, sai tham số và sai ngữ cảnh.

Phạm vi chính là chữ ký bất đối xứng trong JCA. Bài không thay thế kiến thức về thiết kế giao thức, PKI, certificate path validation, quản lý vòng đời khóa hay chính sách authorization. Những phần này quyết định public key nào được tin cậy và chữ ký nào được phép chấp nhận.

## 2. Chữ ký số giải quyết vấn đề gì?

Một chữ ký số được tạo từ dữ liệu và private key. Bên xác minh dùng public key tương ứng để kiểm tra chữ ký có phù hợp với dữ liệu hay không.

Ba thuộc tính thường được kỳ vọng:

- **Integrity:** thay đổi dữ liệu sau khi ký làm phép xác minh thất bại.
- **Authentication at key level:** chữ ký hợp lệ cho thấy phép ký được tạo bởi bên nắm giữ private key tương ứng, với giả định thuật toán và khóa an toàn.
- **Evidence:** chữ ký và dữ liệu có thể được lưu lại để kiểm tra sau này, nếu hệ thống giữ đủ thông tin về public key, thuật toán, thời điểm và chính sách tin cậy.

Không được suy diễn các thuộc tính này thành kết luận rộng hơn. Chữ ký hợp lệ không tự chứng minh private key chỉ do một cá nhân kiểm soát, không chứng minh người đó đã đọc nội dung, không chứng minh thời điểm ký là chính xác và không bảo đảm nội dung chưa bị phát lại.

### Ví dụ

Một dịch vụ phát hành hóa đơn ký nội dung hóa đơn bằng private key của tổ chức. Hệ thống nhận hóa đơn có thể dùng public key đã được xác thực để kiểm tra chữ ký. Nếu một trường như tổng tiền hoặc mã khách hàng bị thay đổi, chữ ký sẽ không còn hợp lệ.

Để kết luận hóa đơn thực sự do tổ chức phát hành, bên nhận còn phải biết public key đó thuộc về tổ chức nào, có được cấp cho mục đích ký hóa đơn không, chứng thư có hợp lệ không và khóa có bị thu hồi tại thời điểm liên quan không.

## 3. Signature, MessageDigest và MAC

Ba cơ chế thường xuất hiện cùng nhau nhưng giải quyết các vấn đề khác nhau.

| Cơ chế | Đầu vào | Bí mật cần có | Ai xác minh được? | Mục đích |
|---|---|---|---|---|
| MessageDigest | Dữ liệu | Không | Bất kỳ ai tính lại digest | Dấu vân tay dữ liệu, kiểm tra thay đổi khi digest được bảo vệ độc lập |
| MAC, ví dụ HmacSHA256 | Dữ liệu và secret key dùng chung | Secret key | Bên có secret key | Xác thực thông điệp giữa các bên cùng giữ bí mật |
| Signature | Dữ liệu và private key | Private key để ký | Bên có public key tương ứng | Xác thực chữ ký bằng cơ chế khóa bất đối xứng |

Digest đơn thuần không xác thực nguồn gốc. Kẻ tấn công sửa dữ liệu cũng có thể tính lại digest nếu digest không được bảo vệ.

MAC phù hợp khi các bên cùng tin cậy và cùng giữ một secret. Vì tất cả bên giữ khóa MAC đều có thể tạo MAC, MAC không cung cấp khả năng xác minh công khai.

Chữ ký số cho phép bên ký giữ private key và phân phối public key cho nhiều bên xác minh. Đây là lý do chữ ký được dùng cho tài liệu, phần mềm, chứng thư, token và thông điệp cần xác minh độc lập.

Trong Java:

- **MessageDigest** cung cấp digest như SHA-256.
- **Mac** cung cấp MAC như HmacSHA256.
- **Signature** cung cấp các thuật toán chữ ký như SHA256withRSA, SHA256withECDSA, RSASSA-PSS và Ed25519.

Không dùng Signature để thay thế encryption. Mã hóa bảo vệ tính bí mật; chữ ký bảo vệ tính toàn vẹn và xác thực ở cấp khóa. Một giao thức có thể cần cả hai, nhưng phải thiết kế thứ tự và ràng buộc dữ liệu rõ ràng.

## 4. Signature nằm ở đâu trong JCA?

JCA cung cấp một lớp API thống nhất cho các dịch vụ mật mã. Ứng dụng gọi lớp facade như Signature, KeyPairGenerator, KeyStore hoặc Cipher. Provider cung cấp phần triển khai thuật toán thông qua các SPI tương ứng.

~~~~mermaid
flowchart TB
    APP[Ứng dụng Java]
    API[java.security.Signature]
    SPI[SignatureSpi]
    P1[Provider phần mềm]
    P2[Provider HSM hoặc PKCS 11]
    KEY[Private key / Public key]
    APP --> API
    API --> SPI
    SPI --> P1
    SPI --> P2
    P1 --> KEY
    P2 --> KEY
~~~~

Ứng dụng không cần tự triển khai RSA, ECDSA hay Ed25519. Nó yêu cầu một tên thuật toán từ Signature.getInstance; JCA tìm provider có hỗ trợ dịch vụ đó theo thứ tự provider đã cấu hình hoặc theo provider được chỉ định.

Provider có thể thực hiện phép ký trong phần mềm, trong thiết bị HSM, smart card hoặc một dịch vụ mật mã. Với private key không thể export, provider có thể nhận một đối tượng PrivateKey đại diện cho khóa nằm trong thiết bị và chuyển yêu cầu ký tới thiết bị đó.

### Các khái niệm chính

| Thành phần | Vai trò |
|---|---|
| Signature | API facade mà ứng dụng sử dụng |
| SignatureSpi | Hợp đồng triển khai dịch vụ Signature của provider |
| Provider | Đăng ký thuật toán và lớp triển khai |
| PrivateKey | Khóa dùng để tạo chữ ký |
| PublicKey | Khóa dùng để xác minh chữ ký |
| KeyPairGenerator | Tạo cặp khóa mới |
| KeyStore | Lưu hoặc tham chiếu khóa và chứng thư theo loại keystore/provider |
| SecureRandom | Cung cấp ngẫu nhiên mật mã khi thuật toán hoặc provider cần |

### Tìm provider

~~~~java
import java.security.Provider;
import java.security.Security;
public class SignatureProviders {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println(provider.getName()
                    + " " + provider.getVersionStr());

            for (Provider.Service service : provider.getServices()) {
                if ("Signature".equalsIgnoreCase(service.getType())) {
                    System.out.println("  " + service.getAlgorithm());
                }
            }
        }
    }
}
~~~~

Danh sách provider và thuật toán thay đổi theo JDK, hệ điều hành, cấu hình bảo mật và thư viện bổ sung. Có thuật toán trong tên chuẩn không có nghĩa mọi provider đều hỗ trợ thuật toán đó.

Trong production, cần xác nhận provider thực tế, phiên bản, chính sách triển khai, chế độ FIPS nếu có và khả năng tương thích của HSM. Không chọn provider chỉ dựa trên tên hoặc giả định rằng mọi môi trường Java đều có cùng danh sách.

## 5. Vòng đời của đối tượng Signature

Signature là một đối tượng có trạng thái. Một chu trình ký hoặc xác minh điển hình gồm các bước:

~~~~mermaid
stateDiagram-v2
    [*] --> Uninitialized
    Uninitialized --> Signing: initSign(privateKey)
    Signing --> Signing: update(data)
    Signing --> Signing: sign()
    Uninitialized --> Verifying: initVerify(publicKey)
    Verifying --> Verifying: update(data)
    Verifying --> Verifying: verify(signature)
    Signing --> Signing: initSign(newKey)
    Verifying --> Verifying: initVerify(newKey)
~~~~

Các phương thức thường dùng:

| Phương thức | Chức năng |
|---|---|
| Signature.getInstance(algorithm) | Lấy implementation cho thuật toán |
| initSign(privateKey) | Chuẩn bị đối tượng để ký |
| initSign(privateKey, random) | Khởi tạo ký với nguồn ngẫu nhiên được cung cấp |
| update(data) | Đưa bytes vào phép ký hoặc xác minh |
| sign() | Kết thúc phép ký và trả về bytes chữ ký |
| initVerify(publicKey) | Chuẩn bị đối tượng để xác minh |
| verify(signatureBytes) | Kiểm tra chữ ký với dữ liệu đã update |
| setParameter(params) | Cấu hình tham số thuật toán khi thuật toán hỗ trợ |

Một đối tượng Signature tại một thời điểm chỉ ở chế độ ký hoặc xác minh. Không gọi update trước khi khởi tạo phù hợp. Dữ liệu đưa vào update khi ký và xác minh phải giống nhau từng byte, cùng thứ tự.

Dù một số implementation có thể đưa đối tượng về trạng thái có thể dùng tiếp sau sign hoặc verify, ứng dụng nên gọi initSign hoặc initVerify cho mỗi thao tác mới. Cách này làm ranh giới giữa các thông điệp rõ ràng và tránh phụ thuộc vào chi tiết trạng thái của provider.

Không chia sẻ một instance Signature cho nhiều thread cùng lúc. Đối tượng giữ trạng thái dữ liệu đang xử lý và không phải API thread-safe. Tạo instance riêng cho mỗi thao tác hoặc dùng cơ chế quản lý instance an toàn theo thread.

## 6. Chu trình ký và xác minh tối thiểu

Ví dụ dưới đây dùng Ed25519. Thuật toán này được hỗ trợ trong các JDK hiện đại, bao gồm Java 17 với provider phù hợp. Ed25519 tự thực hiện quy trình băm nội bộ; ứng dụng không truyền digest đã tính trước vào Signature.

~~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.Base64;

public class Ed25519Basics {
    public static void main(String[] args) throws GeneralSecurityException {
        byte[] message = "invoice:INV-2026-0042;amount:125000"
                .getBytes(StandardCharsets.UTF_8);

        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keyPair = generator.generateKeyPair();

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keyPair.getPrivate());
        signer.update(message);
        byte[] signatureBytes = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(keyPair.getPublic());
        verifier.update(message);
        boolean valid = verifier.verify(signatureBytes);

        System.out.println("Signature: "
                + Base64.getEncoder().encodeToString(signatureBytes));
        System.out.println("Valid: " + valid);

        if (!valid) {
            throw new SecurityException("Signature verification failed");
        }
    }
}
~~~~

Ví dụ sinh key pair trong bộ nhớ để minh họa API. Ứng dụng thực tế phải nạp public key từ nguồn đã được xác thực và lấy private key từ keystore, HSM hoặc dịch vụ ký được kiểm soát. Không tạo một cặp khóa mới mỗi lần xác minh một thông điệp production.

### Thứ tự thao tác

1. Xác định chính xác bytes cần ký.
2. Chọn thuật toán theo policy đã được phê duyệt.
3. Lấy private key phù hợp với mục đích ký.
4. Tạo Signature và gọi initSign.
5. Gọi update với toàn bộ bytes theo đúng thứ tự.
6. Gọi sign để lấy signature bytes.
7. Lưu chữ ký cùng metadata cần thiết.
8. Bên xác minh lấy public key đã được xác thực.
9. Khởi tạo Signature bằng initVerify.
10. Đưa đúng bytes đã ký vào update và gọi verify.

Chữ ký được tạo trên bytes, không phải trên khái niệm “đối tượng Java”. Nếu hai bên serialize cùng một object theo thứ tự field, encoding hoặc format khác nhau, chúng có thể tạo bytes khác nhau và chữ ký không xác minh được.

## 7. Chuẩn bị dữ liệu trước khi ký

Đây là một trong những phần dễ gây lỗi nhất khi tích hợp chữ ký. Signature không biết ý nghĩa của dữ liệu. Nó chỉ xử lý chuỗi bytes được truyền vào update.

### Dùng encoding xác định

Không dựa vào charset mặc định của máy:

~~~~java
byte[] data = text.getBytes(StandardCharsets.UTF_8);
~~~~

Nếu bên ký dùng UTF-8 nhưng bên xác minh dùng charset mặc định của hệ điều hành, cùng một chuỗi hiển thị có thể tạo bytes khác nhau.

### Canonicalization cho dữ liệu có cấu trúc

JSON, XML và các định dạng tài liệu có thể có nhiều cách biểu diễn cùng nội dung logic. Ví dụ, hai object JSON có thể có thứ tự field khác nhau nhưng cùng ý nghĩa. Nếu ký raw JSON, thứ tự field, khoảng trắng, escaping và cách biểu diễn số có thể làm chữ ký khác nhau.

Có hai lựa chọn:

- Ký đúng byte sequence đã được lưu và truyền, rồi xác minh trên đúng byte sequence đó.
- Chuẩn hóa dữ liệu bằng một canonicalization scheme được thống nhất trước khi ký và xác minh.

Không tự viết quy tắc canonicalization sơ sài. Với JSON có thể nghiên cứu JSON Canonicalization Scheme (RFC 8785); với XML cần dùng XML Signature và canonicalization phù hợp, chú ý namespace và transform. Không parse rồi serialize lại tùy tiện trước khi xác minh.

### Tránh nhập nhằng khi ghép trường

Giả sử ứng dụng ký hai trường tenant và payload bằng cách nối chuỗi:

- tenant = ab, payload = c
- tenant = a, payload = bc

Cả hai đều có thể tạo chuỗi abc. Chữ ký không phân biệt được ranh giới trường nếu đầu vào không mã hóa ranh giới.

Dùng encoding có length-prefix, định dạng nhị phân có schema hoặc canonical serialization. Đồng thời đưa ngữ cảnh nghiệp vụ vào dữ liệu ký: purpose, tenant, audience, phiên bản format và định danh thông điệp.

### Domain separation

Một hệ thống có thể dùng cùng một key để ký nhiều loại dữ liệu. Nếu dữ liệu của hai protocol có cùng byte representation, một chữ ký từ protocol này có thể bị sử dụng nhầm ở protocol khác. Đưa một domain tag cố định vào đầu dữ liệu ký giúp phân biệt mục đích.

Ví dụ:

~~~~text
MYBUSINESS-SHOP|SIGNATURE|PAYMENT-AUTHORIZATION|V1
~~~~

Domain tag phải được định nghĩa trong protocol và giữ ổn định. Không để người gửi tùy ý chọn domain tag hoặc purpose rồi bên nhận tin theo giá trị đó mà không kiểm tra policy.

## 8. Ví dụ Java 17: ký có ngữ cảnh và phát hiện thay đổi

Ví dụ sau dùng Ed25519 và length-prefix cho các trường. Dữ liệu ký gắn với domain, purpose và tenant. Khi payload hoặc tenant thay đổi, phép xác minh bằng chữ ký cũ phải thất bại.

~~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public final class ContextBoundSignatureDemo {
    private static final byte[] DOMAIN =
            "MYBUSINESS-SHOP-SIGNATURE-V1"
                    .getBytes(StandardCharsets.UTF_8);

    private static byte[] field(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    private static void writeField(
            DataOutputStream output,
            byte[] value
    ) throws IOException {
        output.writeInt(value.length);
        output.write(value);
    }

    private static byte[] signingInput(
            String purpose,
            String tenantId,
            String payload
    ) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream output = new DataOutputStream(buffer)) {
            writeField(output, DOMAIN);
            writeField(output, field(purpose));
            writeField(output, field(tenantId));
            writeField(output, field(payload));
        }

        return buffer.toByteArray();
    }

    private static boolean verify(
            java.security.PublicKey publicKey,
            byte[] input,
            byte[] signatureBytes
    ) throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(publicKey);
        verifier.update(input);
        return verifier.verify(signatureBytes);
    }

    public static void main(String[] args)
            throws GeneralSecurityException, IOException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keyPair = generator.generateKeyPair();

        byte[] originalInput = signingInput(
                "payment-authorization",
                "tenant-42",
                "paymentId=PAY-1007;amount=125000;currency=VND"
        );

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keyPair.getPrivate());
        signer.update(originalInput);
        byte[] signatureBytes = signer.sign();

        boolean originalValid = verify(
                keyPair.getPublic(),
                originalInput,
                signatureBytes
        );

        byte[] changedAmount = signingInput(
                "payment-authorization",
                "tenant-42",
                "paymentId=PAY-1007;amount=925000;currency=VND"
        );

        boolean changedAmountValid = verify(
                keyPair.getPublic(),
                changedAmount,
                signatureBytes
        );

        byte[] wrongTenant = signingInput(
                "payment-authorization",
                "tenant-99",
                "paymentId=PAY-1007;amount=125000;currency=VND"
        );

        boolean wrongTenantValid = verify(
                keyPair.getPublic(),
                wrongTenant,
                signatureBytes
        );

        System.out.println("Original valid: " + originalValid);
        System.out.println("Changed amount valid: " + changedAmountValid);
        System.out.println("Wrong tenant valid: " + wrongTenantValid);

        if (!originalValid || changedAmountValid || wrongTenantValid) {
            throw new SecurityException("Unexpected signature result");
        }
    }
}
~~~~

Kết quả mong đợi:

~~~~text
Original valid: true
Changed amount valid: false
Wrong tenant valid: false
~~~~

Đây là minh họa về cách tạo signing input có cấu trúc. Trong hệ thống thật, payload cần dùng một schema và encoding được định nghĩa đầy đủ; các trường như amount phải có biểu diễn số chuẩn, currency có tập giá trị hợp lệ, tenant phải được ràng buộc với danh tính đã xác thực và paymentId phải có quy tắc duy nhất.

Domain separation và chữ ký không tự kiểm tra trạng thái giao dịch. Server vẫn phải kiểm tra quyền, trạng thái payment, thời hạn và việc thông điệp đã được xử lý hay chưa.

## 9. Lựa chọn thuật toán chữ ký

Thuật toán phải được chọn theo yêu cầu bảo mật, tuổi thọ hệ thống, nền tảng, provider và giao thức liên thông.

| Thuật toán JCA | Họ mật mã | Đặc điểm | Khi sử dụng |
|---|---|---|---|
| RSASSA-PSS | RSA | Padding xác suất, có tham số digest, MGF và salt length | Lựa chọn phù hợp cho thiết kế RSA mới khi các bên hỗ trợ |
| SHA256withRSA | RSA PKCS#1 v1.5 | Tương thích rộng, định dạng phổ biến | Hệ thống legacy hoặc giao thức yêu cầu rõ ràng |
| SHA256withECDSA | ECDSA | Chữ ký tương đối nhỏ, dựa trên elliptic curve | Hệ thống cần chữ ký gọn và provider hỗ trợ curve được chọn |
| Ed25519 | Edwards-curve signature | Chữ ký gọn, API đơn giản, không yêu cầu chọn digest riêng | Hệ thống mới khi nền tảng và policy cho phép |

Không dùng MD5 hoặc SHA-1 cho thiết kế chữ ký mới. Tránh DSA và các thuật toán cũ không còn phù hợp với policy hiện tại. Không dùng raw RSA hoặc thuật toán do ứng dụng tự ghép từ các primitive mật mã.

### RSA-PSS

RSA-PSS được khuyến nghị cho chữ ký RSA mới. PSS sử dụng tham số gồm:

- Digest dùng cho thông điệp, ví dụ SHA-256.
- Mask Generation Function, thường là MGF1.
- Digest của MGF1.
- Salt length.
- Trailer field.

Hai phía phải thống nhất chính xác các tham số. Không chỉ ghi “RSA-PSS” rồi để mỗi phía tự chọn tham số khác nhau.

### ECDSA

ECDSA yêu cầu curve được thống nhất và có mức bảo mật phù hợp. Các lựa chọn phổ biến gồm NIST P-256 và P-384. Trong Java có thể tạo khóa bằng KeyPairGenerator với ECGenParameterSpec.

Chữ ký ECDSA phụ thuộc vào nonce mật mã dùng trong quá trình ký. Việc tái sử dụng hoặc tạo nonce yếu có thể làm lộ private key. Hãy để provider đã được kiểm định xử lý nonce; không tự triển khai phép ký ECDSA.

### Ed25519

Ed25519 có API đơn giản: dùng tên thuật toán Ed25519 cho cả ký và xác minh. Ứng dụng không ghép SHA-256 vào tên thuật toán và không tự băm dữ liệu trước khi gọi update.

Ed25519 không phải lựa chọn được mọi hệ thống tuân thủ hoặc HSM hỗ trợ. Kiểm tra yêu cầu FIPS, provider, giao thức đối tác và khả năng lưu trữ khóa trước khi quyết định.

### RSA PKCS#1 v1.5

SHA256withRSA dùng RSA với PKCS#1 v1.5 signature padding. Đây là thuật toán có độ tương thích cao nhưng với giao thức mới nên ưu tiên RSA-PSS nếu mọi bên có thể hỗ trợ và policy cho phép. Không nhầm RSA PKCS#1 v1.5 signature với RSA encryption padding.

## 10. Cấu hình RSA-PSS tường minh trong Java

PSS cần cấu hình thống nhất trước khi ký và xác minh. Ví dụ sau chọn SHA-256, MGF1 với SHA-256, salt length 32 byte và trailer field 1.

~~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public class RsaPssSignatureDemo {
    private static PSSParameterSpec pssParameters() {
        return new PSSParameterSpec(
                "SHA-256",
                "MGF1",
                MGF1ParameterSpec.SHA256,
                32,
                1
        );
    }

    private static Signature newPssSignature()
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("RSASSA-PSS");
        signature.setParameter(pssParameters());
        return signature;
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair keyPair = generator.generateKeyPair();

        byte[] message = "contract-version=7"
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);

        Signature signer = newPssSignature();
        signer.initSign(keyPair.getPrivate());
        signer.update(message);
        byte[] signatureBytes = signer.sign();

        Signature verifier = newPssSignature();
        verifier.initVerify(keyPair.getPublic());
        verifier.update(message);

        if (!verifier.verify(signatureBytes)) {
            throw new SecurityException("RSA-PSS signature is invalid");
        }

        System.out.println("RSA-PSS verification succeeded");
    }
}
~~~~

Provider có thể có giới hạn về tham số hoặc thứ tự cấu hình. Nếu một provider yêu cầu đặt tham số ở thời điểm khác, cần tuân theo tài liệu của provider và kiểm thử trên đúng JDK/provider production. Không bỏ tham số để làm cho lỗi tương thích biến mất.

## 11. Tạo key pair cho ECDSA

Ví dụ tạo key pair EC dùng named curve P-256:

~~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.spec.ECGenParameterSpec;

public class EcdsaKeyGeneration {
    public static KeyPair generate() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        return generator.generateKeyPair();
    }
}
~~~~

Tên curve phải được hỗ trợ bởi provider và thống nhất với bên xác minh. Không tự tạo tham số curve tùy ý cho hệ thống production. Lưu metadata thuật toán và curve cùng key inventory để việc xác minh, xoay vòng và migration có thể kiểm soát.

## 12. Không băm hai lần

Các tên như SHA256withRSA và SHA256withECDSA đã bao gồm bước băm dữ liệu bằng SHA-256 trong thuật toán chữ ký. Khi gọi Signature.update, truyền dữ liệu gốc theo protocol.

Luồng đúng:

~~~~text
message bytes
    -> SHA-256 bên trong thuật toán chữ ký
    -> RSA/ECDSA signature operation
    -> signature bytes
~~~~

Một lỗi phổ biến là tính SHA-256 trước rồi truyền digest vào SHA256withRSA. Khi đó thuật toán tiếp tục băm digest một lần nữa. Bên xác minh có thể tái hiện cùng thao tác nhưng chữ ký không còn mang ý nghĩa protocol mong muốn và không tương thích với các hệ thống ký dữ liệu gốc.

Nếu protocol yêu cầu ký một digest đã được tính trước, phải dùng API/thuật toán được thiết kế rõ cho trường hợp đó, thống nhất định dạng DigestInfo hoặc prehash variant, và kiểm soát chặt chẽ đầu vào. Không tự đổi tên thuật toán để giả lập.

Với Ed25519, không truyền SHA-256 digest thay cho thông điệp trừ khi protocol chỉ định một biến thể prehash riêng được hỗ trợ rõ ràng. Ed25519 và Ed25519ph là hai cách dùng khác nhau.

## 13. Chữ ký detached và metadata

Chữ ký có thể được lưu tách khỏi payload. Đây là mô hình detached signature thường gặp trong artifact signing, tài liệu và API.

Một envelope có thể chứa:

~~~~json
{
  "format": "signature-envelope-v1",
  "algorithm": "Ed25519",
  "keyId": "payments-signing-2026-01",
  "purpose": "payment-authorization",
  "contentType": "application/vnd.example.payment+json",
  "signature": "BASE64_SIGNATURE_BYTES"
}
~~~~

Payload được lưu hoặc truyền riêng. Bên nhận dùng keyId để tra public key trong registry tin cậy, kiểm tra thuật toán có nằm trong allowlist cho purpose đó không, tái tạo signing input và xác minh signature.

Các metadata như format version, algorithm, keyId, purpose, content type, tenant và audience cần được ràng buộc với dữ liệu ký hoặc được bảo vệ bằng một policy tin cậy độc lập. Nếu metadata có thể bị thay đổi mà không bị phát hiện, hệ thống có nguy cơ chọn sai key, sai thuật toán hoặc sai ngữ cảnh.

Không cho dữ liệu không tin cậy tự quyết định tùy ý thuật toán cần dùng. Bên xác minh phải áp dụng allowlist theo policy, kiểm tra keyId trong registry được quản trị và từ chối thuật toán đã bị loại bỏ. Tránh thử lần lượt nhiều thuật toán hoặc nhiều key cho đến khi một phép xác minh thành công.

## 14. Xác minh chữ ký không đồng nghĩa tin cậy public key

Phép verify trả về true chỉ cho biết chữ ký hợp lệ đối với dữ liệu và public key đã đưa vào. Nó không xác nhận public key đó thuộc về đúng tổ chức hoặc người gửi.

Một quy trình xác minh đầy đủ thường gồm:

1. Xác định danh tính signer mong đợi từ cấu hình hoặc protocol đã xác thực.
2. Tra public key theo keyId trong một registry tin cậy.
3. Nếu public key lấy từ certificate, kiểm tra certificate path tới trust anchor.
4. Kiểm tra thời hạn, key usage, extended key usage, policy và trạng thái thu hồi theo yêu cầu.
5. Kiểm tra key được phép ký đúng loại nội dung và đúng tenant/purpose.
6. Xác minh chữ ký trên đúng bytes.
7. Kiểm tra freshness, expiry, nonce hoặc trạng thái replay.
8. Ghi audit evidence cần thiết.

Với X.509 certificate, KeyUsage thường cần có bit digitalSignature cho mục đích ký. ExtendedKeyUsage và certificate policy có thể giới hạn thêm mục đích. Không suy ra mọi public key trong certificate đều được phép ký mọi loại dữ liệu.

Nếu public key được pin trực tiếp, quy trình enrollment, thay thế, thu hồi và phân phối pin cần được quản lý. Một file public key không có nguồn gốc tin cậy không đủ để xác thực danh tính signer.

## 15. Chống replay và ràng buộc ngữ cảnh

Chữ ký hợp lệ có thể bị gửi lại. Ví dụ, một lệnh thanh toán đã ký có thể bị kẻ tấn công phát lại nhiều lần nếu server không kiểm tra trạng thái.

Để giảm replay, protocol cần ký các trường liên quan như:

- Purpose hoặc loại hành động.
- Tenant hoặc account scope.
- Audience hoặc service đích.
- Message ID duy nhất.
- Issued-at và expiry.
- Nonce hoặc sequence number.
- Phiên bản schema/protocol.

Bên nhận phải kiểm tra các trường này theo policy và lưu trạng thái đã xử lý nếu cần bảo đảm một lần. Chỉ đưa timestamp vào payload chưa đủ: server phải kiểm tra cửa sổ thời gian và đồng hồ; chỉ đưa nonce vào payload cũng chưa đủ nếu server không lưu hoặc không kiểm tra nonce đã dùng.

Chữ ký số không tự tạo trusted timestamp. Nếu cần chứng minh thời điểm tồn tại của chữ ký, cần cơ chế timestamp tin cậy hoặc audit log có bảo vệ thích hợp.

## 16. Xử lý dữ liệu lớn bằng update theo luồng

Signature hỗ trợ update nhiều lần. Không cần nạp toàn bộ file vào bộ nhớ trước khi ký hoặc xác minh.

~~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.Signature;

public class StreamingFileSigner {
    public static byte[] signFile(
            Path file,
            PrivateKey privateKey
    ) throws IOException, GeneralSecurityException {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);

        byte[] buffer = new byte[8192];

        try (InputStream input = Files.newInputStream(file)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                signer.update(buffer, 0, count);
            }
        }

        return signer.sign();
    }
}
~~~~

Phía xác minh đọc đúng cùng một file byte sequence và gọi update theo thứ tự tương tự. Nếu file có thể thay đổi trong lúc đọc hoặc giữa lúc ký và lưu chữ ký, cần snapshot hoặc cơ chế bảo đảm nội dung bất biến trong toàn bộ thao tác.

Với định dạng container như ZIP, PDF hoặc package phần mềm, phải định nghĩa chính xác ký toàn bộ file bytes hay ký một representation logic đã chuẩn hóa. Nếu ký file sau khi nén, thay đổi metadata hoặc thứ tự entry có thể làm chữ ký khác; nếu ký nội dung đã giải nén, protocol phải định nghĩa rõ cách xử lý tên file, đường dẫn, quyền và metadata.

## 17. Định dạng chữ ký: DER và IEEE P1363

Signature trả về một mảng byte. Cách mã hóa bytes phụ thuộc thuật toán và provider.

| Thuật toán | Định dạng thường gặp |
|---|---|
| RSA | Chuỗi byte có độ dài theo kích thước modulus |
| Ed25519 | Chữ ký 64 byte |
| ECDSA trong JCA phổ biến | ASN.1 DER encoding của cặp số nguyên r và s |

Một số giao thức cần ECDSA theo IEEE P1363, tức hai giá trị r và s được nối bằng độ dài cố định. Ví dụ, JOSE ES256 yêu cầu dạng P1363 cho P-256, trong khi Signature với SHA256withECDSA thường trả về DER encoding.

Đây là lỗi liên thông phổ biến: chữ ký đúng về toán học nhưng bên nhận từ chối vì format khác. Hãy dùng thư viện giao thức có hỗ trợ chuyển đổi đã được kiểm thử. Không tự cắt byte DER theo vị trí cố định; DER INTEGER có thể có byte 0 ở đầu để biểu diễn số dương và độ dài thay đổi.

Không giả định mọi chữ ký đều có cùng độ dài. Kiểm tra format theo thuật toán và protocol, đồng thời giới hạn kích thước đầu vào trước khi parse chữ ký từ bên ngoài.

## 18. Lưu trữ và bảo vệ private key

Private key là tài sản nhạy cảm nhất trong quy trình ký. Nếu kẻ tấn công lấy được private key, họ có thể tạo chữ ký mới có vẻ hợp lệ cho đến khi key bị thu hồi hoặc bị thay thế và hệ thống xác minh cập nhật policy.

Các lựa chọn lưu trữ:

- **PKCS12 KeyStore:** phù hợp cho một số ứng dụng Java cần lưu private key và certificate chain được bảo vệ bằng password.
- **HSM hoặc smart card:** private key có thể không export được; provider thực hiện ký bên trong thiết bị.
- **Remote signing service:** ứng dụng gửi yêu cầu ký có xác thực tới dịch vụ quản lý khóa; service áp dụng policy và audit.
- **Cloud KMS:** cần kiểm tra dịch vụ có hỗ trợ asymmetric signing, thuật toán, định dạng đầu ra và provider/API tương ứng hay không.

Không ghi private key, password, PIN hoặc token truy cập vào log. Không đưa private key vào source code, file cấu hình, image container hay biến môi trường dài hạn nếu có phương án quản lý khóa phù hợp hơn.

### Đọc private key từ PKCS12 KeyStore

Ví dụ dưới đây minh họa cách lấy private key và certificate từ một keystore đã được cấp quyền truy cập. Password được lấy từ secret provider ở runtime; trong ví dụ chỉ thể hiện bằng tham số.

~~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;

public class LoadSigningKey {
    public static PrivateKey load(
            Path path,
            char[] storePassword,
            char[] keyPassword,
            String alias
    ) throws Exception {
        KeyStore keyStore = KeyStore.getInstance("PKCS12");

        try (InputStream input = Files.newInputStream(path)) {
            keyStore.load(input, storePassword);
        }

        Key key = keyStore.getKey(alias, keyPassword);
        if (!(key instanceof PrivateKey privateKey)) {
            throw new SecurityException("Alias does not contain a private key");
        }

        Certificate certificate = keyStore.getCertificate(alias);
        if (certificate == null) {
            throw new SecurityException("Signing certificate is missing");
        }

        return privateKey;
    }
}
~~~~

Đoạn code chưa xác minh certificate path hoặc mục đích sử dụng. Ứng dụng phải thực hiện các kiểm tra trust và policy trước khi sử dụng certificate/public key. Sau khi dùng password dạng char array, cần xóa bản sao do ứng dụng sở hữu khi có thể; việc xóa không bảo đảm mọi bản sao trong runtime đã biến mất.

Đối với HSM, thao tác lấy key có thể trả về một đối tượng khóa đại diện thay vì raw key bytes. Không ép export hoặc chuyển đối tượng đó sang provider khác nếu provider không hỗ trợ.

## 19. Ký bằng HSM hoặc provider ngoài

JCA cho phép ứng dụng sử dụng Signature mà không cần biết chi tiết phần cứng. Provider có thể kết nối HSM qua PKCS#11 hoặc cơ chế riêng.

Luồng khái quát:

~~~~mermaid
sequenceDiagram
    participant A as Java application
    participant J as JCA Signature
    participant P as HSM provider
    participant H as HSM
    A->>J: getInstance + initSign(key handle)
    J->>P: SignatureSpi operation
    P->>H: Ký dữ liệu hoặc digest theo policy
    H-->>P: Signature bytes
    P-->>J: Signature bytes
    J-->>A: sign() result
~~~~

Một số provider yêu cầu cài đặt provider, cấu hình slot/token, đăng nhập session và lấy private key theo alias. Chi tiết cụ thể phụ thuộc nhà cung cấp và không thể thay bằng một cấu hình chung cho mọi HSM.

Các kiểm soát cần có:

- Private key được tạo hoặc import theo policy và không export nếu yêu cầu.
- Chỉ service account được phép ký đúng key và đúng purpose.
- Có cơ chế phân quyền, dual control hoặc approval cho key nhạy cảm.
- Audit ghi nhận key identifier, operation, caller, thời điểm và kết quả theo policy.
- Giới hạn tốc độ, concurrency và timeout để tránh làm cạn session HSM.
- Theo dõi lỗi provider, thiết bị, network và quota.
- Có kế hoạch dự phòng, phục hồi và xoay vòng key.
- Không fallback âm thầm sang một private key phần mềm khác khi HSM lỗi.

Nếu dùng provider ngoài, hãy xác nhận provider được đăng ký đúng cách và Signature.getInstance thực sự chọn provider đó. Không chỉ dựa vào việc ứng dụng đã load thư viện PKCS#11.

## 20. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| verify trả về false | Payload khác bytes lúc ký hoặc sai public key | So sánh hash phục vụ chẩn đoán, encoding, serialization và keyId |
| InvalidKeyException | Sai loại key hoặc key không hỗ trợ thuật toán | Kiểm tra key algorithm, curve, modulus và provider |
| NoSuchAlgorithmException | Provider không hỗ trợ tên thuật toán | Kiểm tra provider và thuật toán được cài |
| InvalidAlgorithmParameterException | PSS/EC parameters không hợp lệ hoặc không được hỗ trợ | So khớp tham số ở hai phía và tài liệu provider |
| SignatureException | Dữ liệu, trạng thái hoặc chữ ký không hợp lệ | Kiểm tra thứ tự init/update/sign/verify và định dạng đầu vào |
| ECDSA verify lỗi với hệ thống khác | DER và P1363 không thống nhất | Xác nhận protocol encoding và dùng converter chuẩn |
| RSA-PSS verify lỗi | Digest, MGF digest, salt length hoặc trailer khác nhau | Cấu hình tường minh cùng PSSParameterSpec |
| HSM ký thất bại | Slot, token, session, quyền hoặc quota | Kiểm tra provider log, HSM audit và key usage policy |
| Chữ ký hợp lệ nhưng signer sai | Public key không được xác thực hoặc keyId bị tráo | Kiểm tra certificate chain, pinning và key registry |
| Thông điệp hợp lệ được xử lý nhiều lần | Thiếu replay control | Kiểm tra nonce, message ID, expiry và idempotency store |

Không chuyển mọi lỗi thành “signature invalid” rồi bỏ qua thông tin vận hành. Phân biệt chữ ký không hợp lệ với lỗi provider, lỗi truy cập khóa, lỗi tham số và lỗi định dạng. Đồng thời không trả chi tiết nhạy cảm của hệ thống khóa ra API công khai nếu điều đó giúp dò tìm key hoặc cấu hình.

## 21. Kiểm thử chữ ký

Bộ kiểm thử phải bao gồm cả đường đi hợp lệ và các trường hợp bị từ chối.

| Ca kiểm thử | Thay đổi | Kết quả mong đợi |
|---|---|---|
| Chữ ký hợp lệ | Đúng bytes, đúng public key | verify thành công |
| Sửa payload | Thay một byte sau khi ký | verify thất bại |
| Sai public key | Dùng key pair khác | verify thất bại |
| Sai tenant | Thay tenant trong signing input | verify thất bại |
| Sai purpose | Thay domain/purpose | verify thất bại |
| Sai thuật toán | Chọn thuật toán ngoài allowlist | Từ chối trước khi verify |
| Sai PSS salt length | Tham số khác policy | Từ chối hoặc verify thất bại |
| Sai MGF digest | MGF1 dùng digest khác | Verify thất bại |
| Chữ ký bị cắt | Signature bytes thiếu | Verify thất bại hoặc báo lỗi định dạng |
| Chữ ký quá lớn | Đầu vào vượt giới hạn | Từ chối trước khi xử lý |
| DER sai cấu trúc | ASN.1 encoding không hợp lệ | Từ chối |
| ECDSA DER/P1363 mismatch | Dùng nhầm representation | Từ chối hoặc chuyển đổi theo protocol |
| Replay | Gửi lại message ID/nonce đã xử lý | Từ chối theo policy |
| Hết hạn | issued-at/expiry ngoài cửa sổ cho phép | Từ chối |
| Public key bị thu hồi | Certificate/key status không còn hợp lệ | Từ chối theo trust policy |
| Provider unavailable | HSM/provider không sẵn sàng | Báo lỗi vận hành; không fallback yếu hơn |

### Test property và interoperability

- Ký rồi xác minh bằng cùng provider.
- Ký bằng provider A và xác minh bằng provider B nếu production cần liên thông.
- Test nhiều kích thước payload, kể cả payload lớn.
- Test bytes có Unicode, newline, ký tự null và dữ liệu nhị phân.
- Test canonicalization qua nhiều implementation.
- Test certificate chain, key usage và key rotation.
- Test khi provider timeout hoặc HSM hết session.
- Test concurrency để bảo đảm không chia sẻ Signature instance sai cách.

Không dùng private key production trong unit test. Tạo key test riêng và đánh dấu rõ ràng; test fixture không được đưa vào môi trường production.

## 22. Các tình huống sử dụng

### Ký artifact phần mềm

Pipeline build ký hash hoặc nội dung artifact bằng private key được quản lý tập trung. Hệ thống triển khai xác minh chữ ký, kiểm tra signer, key usage, phiên bản và policy trước khi cài đặt. Chữ ký không thay thế kiểm tra nguồn build, provenance hoặc vulnerability scan.

### Webhook

Nhà cung cấp ký request body hoặc signing input gồm timestamp, method, path và body digest. Bên nhận xác minh chữ ký bằng public key đã được xác thực, kiểm tra timestamp trong cửa sổ cho phép và chống xử lý lặp bằng event ID. Chỉ ký body mà không ràng buộc endpoint hoặc timestamp có thể để request hợp lệ bị dùng lại trong ngữ cảnh khác.

### Tài liệu điện tử

Hệ thống ký representation được xác định của tài liệu và lưu detached signature cùng chứng thư hoặc key reference. Để xác minh dài hạn, cần lưu bằng chứng về certificate chain, trạng thái thu hồi, timestamp và policy áp dụng tại thời điểm ký.

### Dịch vụ nội bộ

Một service ký message event bằng private key trong HSM. Consumer lấy public key từ registry tin cậy và xác minh purpose, tenant, event ID và schema version. Authorization của service gửi vẫn phải được kiểm tra riêng.

## 23. Vòng đời khóa ký và xử lý compromise

Khóa ký cần được quản lý theo mục đích sử dụng, thời gian hoạt động và phạm vi ảnh hưởng.

Một quy trình quản lý cơ bản:

1. Xác định owner, purpose, thuật toán, phạm vi signer và thời hạn sử dụng.
2. Tạo key pair trong HSM hoặc môi trường được kiểm soát.
3. Đăng ký public key, certificate, keyId và policy vào registry.
4. Phân phối public key hoặc certificate qua kênh tin cậy.
5. Chỉ cấp quyền ký cho workload hoặc người có trách nhiệm.
6. Theo dõi operation, lỗi, tần suất và bất thường.
7. Xoay vòng khóa theo cryptoperiod hoặc khi policy yêu cầu.
8. Giữ public key cũ để xác minh chữ ký lịch sử khi cần và khi policy cho phép.
9. Khi nghi ngờ compromise, cô lập quyền ký, đánh giá phạm vi và thu hồi/chuyển key theo incident plan.
10. Lưu audit evidence và cập nhật registry để verifier áp dụng trạng thái mới.

Không xóa public key cũ ngay khi private key bị thay thế nếu hệ thống cần xác minh chữ ký lịch sử. Tuy nhiên, nếu key bị compromise, chữ ký được tạo trong giai đoạn bị ảnh hưởng cần được đánh giá theo timestamp tin cậy, audit và chính sách nghiệp vụ. Một chữ ký toán học hợp lệ không chứng minh nó được tạo trước khi key bị lộ.

## 24. Các nguyên tắc an toàn cần giữ

- Chỉ dùng thuật toán và tham số nằm trong allowlist của hệ thống.
- Không tự triển khai primitive hoặc thuật toán chữ ký.
- Không dùng SHA-1/MD5 cho chữ ký mới.
- Ưu tiên RSA-PSS khi cần RSA cho giao thức mới.
- Dùng curve chuẩn đã được provider hỗ trợ cho ECDSA.
- Dùng Ed25519 khi policy, provider và đối tác hỗ trợ.
- Ký bytes có encoding và canonicalization được định nghĩa.
- Ràng buộc purpose, tenant, audience, version và message identity vào signing input.
- Xác thực public key độc lập với phép verify.
- Chống replay bằng nonce, expiry, message ID và trạng thái phía nhận.
- Bảo vệ private key bằng keystore/HSM/remote signing service.
- Không chia sẻ Signature instance giữa các thread.
- Không fallback sang thuật toán yếu hoặc key khác khi provider lỗi.
- Giới hạn kích thước signature và payload trước khi parse hoặc xử lý.
- Lưu audit có kiểm soát, tránh ghi private key hoặc dữ liệu nhạy cảm.

## 25. Câu hỏi tự kiểm tra

**1. Signature trong JCA dùng để làm gì?**

Tạo và xác minh chữ ký số trên dữ liệu bằng cặp private key/public key.

**2. Signature khác MessageDigest như thế nào?**

MessageDigest tạo digest không dùng khóa. Signature tạo chữ ký bằng private key và xác minh bằng public key.

**3. Signature khác MAC như thế nào?**

MAC dùng secret key chung; chữ ký dùng private key để ký và public key để xác minh.

**4. Phương thức nào khởi tạo chế độ ký?**

initSign(privateKey).

**5. update() nhận loại dữ liệu nào?**

Bytes của dữ liệu cần ký hoặc xác minh. Hai phía phải đưa vào cùng byte sequence và thứ tự.

**6. verify() trả về false có nghĩa gì?**

Chữ ký không hợp lệ với dữ liệu và public key đã cung cấp. Lỗi vận hành hoặc định dạng cũng có thể phát sinh exception.

**7. Chữ ký số có mã hóa payload không?**

Không. Chữ ký không cung cấp tính bí mật.

**8. Vì sao không nên băm SHA-256 trước rồi dùng SHA256withRSA?**

Vì thuật toán SHA256withRSA đã băm dữ liệu nội bộ; làm vậy sẽ tạo thao tác băm hai lần ngoài ý muốn của protocol.

**9. Vì sao cần xác thực public key?**

Vì verify thành công chỉ chứng minh chữ ký phù hợp với key đã dùng; nó không chứng minh key thuộc signer mong đợi.

**10. RSA-PSS cần thống nhất tham số nào?**

Digest, MGF, digest của MGF, salt length và trailer field.

**11. Ed25519 có cần chọn SHA-256 trong tên Signature không?**

Không. Dùng thuật toán Ed25519; không tự băm trước dữ liệu.

**12. Vì sao JSON có thể xác minh thất bại dù hai object có cùng ý nghĩa?**

Vì thứ tự field, whitespace, escaping hoặc biểu diễn số có thể tạo bytes khác nhau.

**13. Vì sao phải dùng length-prefix hoặc canonical serialization?**

Để xác định ranh giới trường và tạo signing input duy nhất, tránh nhập nhằng khi ghép chuỗi.

**14. Chữ ký hợp lệ có chống replay không?**

Không. Protocol cần nonce, message ID, expiry, sequence hoặc trạng thái xử lý lặp.

**15. ECDSA trong JCA có thể không tương thích với giao thức nào?**

Giao thức yêu cầu IEEE P1363 trong khi provider trả về ASN.1 DER, hoặc ngược lại.

**16. Có nên chia sẻ một Signature instance cho nhiều thread?**

Không. Instance giữ trạng thái và không thread-safe.

**17. HSM giúp bảo vệ điều gì?**

HSM có thể giữ private key không export và thực hiện ký bên trong thiết bị, đồng thời áp dụng quyền và audit theo cấu hình.

**18. verify() thành công có chứng minh người ký là một cá nhân cụ thể không?**

Không. Cần quy trình enrollment, bảo vệ khóa, identity binding và audit để gắn key với danh tính.

**19. Khi xoay vòng key ký, có nên giữ public key cũ không?**

Có thể cần giữ để xác minh chữ ký lịch sử theo retention và trust policy; trạng thái compromise/revocation phải được xét riêng.

**20. Nếu HSM không sẵn sàng, ứng dụng có nên tự chuyển sang key phần mềm yếu hơn không?**

Không. Cần báo lỗi và xử lý theo kế hoạch availability đã được phê duyệt, không âm thầm hạ cấp bảo mật.

## 26. Tài liệu tham khảo

- Java SE 17 API — java.security.Signature: API ký, xác minh, cập nhật dữ liệu và cấu hình tham số.
- Java Security Standard Algorithm Names: tên chuẩn của Signature, KeyPairGenerator và các thuật toán.
- Java Cryptography Architecture (JCA) Reference Guide: provider, SPI và kiến trúc dịch vụ mật mã.
- RFC 8017 — PKCS #1: RSA Cryptography Specifications, gồm RSASSA-PSS.
- RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA), gồm Ed25519.
- RFC 8785 — JSON Canonicalization Scheme (JCS).
- RFC 9421 — HTTP Message Signatures.
- Tài liệu provider/HSM cụ thể đang triển khai, bao gồm thuật toán được hỗ trợ, định dạng chữ ký, session, policy và giới hạn vận hành.

