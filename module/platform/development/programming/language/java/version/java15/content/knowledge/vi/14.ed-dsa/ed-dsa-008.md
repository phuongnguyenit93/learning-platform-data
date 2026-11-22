# Ranh giới bảo mật giữa chữ ký hợp lệ và danh tính đáng tin (EdDSA, Java 15+)

> **Chủ đề cha: EdDSA.** Java 15 bổ sung hỗ trợ EdDSA theo JEP 339, gồm Ed25519 và Ed448. Khi `Signature.verify(...)` trả `true`, kết luận mật mã học chỉ là: **chữ ký khớp chính xác với thông điệp và public key đang dùng để kiểm tra** (theo thuật toán và nhà cung cấp đã chọn). Nó **không tự trả lời** public key ấy thuộc về ai, người ký có quyền gì, thông điệp có đúng ngữ cảnh hay còn hiệu lực không. Ranh giới giữa hai việc này là một trong những điểm quan trọng nhất khi thiết kế hệ thống chữ ký số.

Bài học tập trung vào những API và nguyên tắc còn được áp dụng trong Java hiện đại. Các chương trình độc lập phía dưới biên dịch được với `javac --release 17`, sử dụng JCA/JDK tiêu chuẩn, không cần thư viện thứ ba.

## Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **cryptographic validity**, **trusted public-key binding**, **authenticated identity** và **authorization**.
2. Mô tả tại sao một thông điệp ghi `issuer=admin` có chữ ký Ed25519 đúng vẫn có thể do **kẻ tấn công tự ký** bằng private key của họ.
3. Dùng `KeyPairGenerator` và `Signature` để ký/kiểm tra dữ liệu với Ed25519/Ed448, đồng thời không nhầm public key do bên gửi cung cấp với một trusted key.
4. Hiểu cơ chế pin public key, key registry được cấp phát qua kênh đáng tin cậy hoặc kiểm tra chuỗi chứng thư PKIX/X.509; tránh “tự chứng nhận” danh tính.
5. Ràng buộc mục đích, phiên bản protocol, issuer, audience, action, expiry và nonce vào **các byte đã ký**.
6. Chống key substitution, nhầm thuật toán, replay, context confusion, quyền vượt mức và canonicalization ambiguity.
7. Xây kiểm thử phân biệt **chữ ký đúng nhưng không đáng tin**, **chữ ký đúng và người ký đáng tin nhưng không đủ quyền**, **chữ ký hợp lệ nhưng đã hết hạn/bị phát lại**.

## 1. Bốn tầng không được đánh đồng

Hãy xét một dịch vụ deployment nhận yêu cầu:

~~~text
issuer=release-service
audience=deploy-api
action=publish
artifact=build-42
~~~

Người gửi kèm một public key, chữ ký và tuyên bố “Tôi là release-service”. Nếu server làm:

~~~java
// Đoạn minh họa logic thiếu tin cậy, không phải chương trình độc lập.
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKeyFromRequest);
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureFromRequest);
~~~

thì `valid == true` có thể chỉ chứng minh **người gửi sở hữu private key tương ứng với chính public key họ vừa cung cấp**. Kẻ tấn công cũng có thể tự tạo key pair, tự ký thông điệp và tự gửi public key.

Cần phân tách:

| Tầng | Câu hỏi phải trả lời | Có được bảo đảm bởi riêng `Signature.verify`? |
| --- | --- | --- |
| **1. Tính toàn vẹn/chữ ký mật mã** | Đúng message bytes và signature này có khớp public key này không? | **Có**, với thuật toán đúng và phép kiểm tra hoàn tất |
| **2. Nguồn gốc khóa đáng tin** | Public key lấy từ trust store/pin/chuỗi chứng thư đã được xác thực, hay do attacker gửi tùy ý? | **Không** |
| **3. Danh tính gắn với khóa** | Khóa ấy được tổ chức tin cậy ràng buộc với service/user/tenant/hostname nào? | **Không** |
| **4. Chính sách ứng dụng** | Danh tính đó có quyền thực hiện action này, cho audience này, ở thời điểm này, và nonce chưa dùng? | **Không** |

**Công thức tư duy:**

~~~text
Chữ ký đúng với public key K
              ≠
K được ứng dụng tin cậy
              ≠
K được gắn với danh tính X
              ≠
X có quyền thực hiện hành động A

Quyết định chấp nhận =
  chữ ký đúng với khóa đã được tin cậy
  + khóa gắn với danh tính phù hợp
  + ngữ cảnh/nội dung đã ký hợp lệ
  + chính sách, thời hạn, chống replay thỏa mãn
~~~

Chữ ký EdDSA không tự mã hóa dữ liệu: một chữ ký hợp lệ **không bảo đảm confidentiality**. Nó cũng không tự chứng minh một con người cụ thể đã nhìn thấy và đồng ý với nội dung: nếu private key bị đánh cắp, dùng chung hoặc hệ thống ký tự động, thông điệp vẫn có thể có chữ ký hợp lệ.

## 2. API EdDSA hiện hành trong Java

Java cung cấp các thuật toán JCA chuẩn:

| Mục đích | API | Tên thuật toán dùng trong bài |
| --- | --- | --- |
| Sinh key pair | `KeyPairGenerator.getInstance(...)` | `"Ed25519"` hoặc `"Ed448"` |
| Tạo và kiểm tra chữ ký | `Signature.getInstance(...)` | `"Ed25519"` hoặc `"Ed448"` |
| Đọc public key từ SubjectPublicKeyInfo bytes | `KeyFactory.getInstance(...)` | `"Ed25519"` / `"Ed448"` |
| Mô tả public key trong ứng dụng | `PublicKey`, `X509EncodedKeySpec` | `getEncoded()` chứa SPKI encoded bytes |
| Tên họ thuật toán | `"EdDSA"` | Không dùng để tự cho bên gửi lựa chọn tùy tiện |

**Ed25519 và Ed448 là các thuật toán ký khác nhau**, không phải tên thay thế cho nhau; chữ ký và key tương ứng phải được dùng với biến thể phù hợp. Chỉ nhận thuật toán đã cấu hình trong **chính sách tin cậy** của ứng dụng.

### 2.1. Quy trình ký và xác minh

~~~text
Bên ký (được cấp khóa theo chính sách):
  (private key, message bytes)
          |
  Signature("Ed25519").initSign(privateKey)
  update(messageBytes)
  sign()
          |
       signature

Bên xác minh:
  authoritative key registry/trusted certificate
          |
       trusted public key K
          |
  Signature("Ed25519").initVerify(K)
  update(EXACT same message bytes)
  verify(signature)
          |
       true / false
          |
  Chỉ khi true và kiểm tra trust/identity/policy đều PASS:
       chấp nhận request
~~~

`Signature.verify()` có thể trả về `false` với chữ ký không khớp hoặc ném ngoại lệ khi dữ liệu khóa/chữ ký/engine không hợp lệ. **Fail closed**: đừng biến exception thành `true`, đừng bỏ qua lỗi để thử tiếp thuật toán do request chỉ định.

### 2.2. Đừng thay đổi dữ liệu trước/sau khi xác minh

Chữ ký trên **dãy byte** chứ không trên ý nghĩa trừu tượng của JSON, XML hay một object. Những phép biến đổi như đổi encoding, thay newline, sắp xếp lại trường JSON, normalize Unicode hoặc bỏ khoảng trắng có thể thay byte và khiến xác minh thất bại.

Nếu protocol muốn ký nội dung có cấu trúc, phải xác định rõ:
- Encoding, thường là UTF-8.
- Representation/canonical serialization (hoặc ký raw payload bytes).
- Độ dài, thứ tự, kiểu trường và giới hạn kích thước.
- Có trường nào nằm ngoài chữ ký không? Đặc biệt chú ý `issuer`, `kid`, `audience`, `action`, `expires`, `nonce`.
- Version và purpose/domain của loại thông điệp.

Không dùng `Map.toString()`, thứ tự một `HashMap` hoặc cách nối giá trị không có escape/length prefix làm canonical serialization.

## 3. Ví dụ 1: chữ ký thật nhưng danh tính giả

Chúng ta tạo **hai cặp khóa Ed25519**:
- `trusted`: private/public key của dịch vụ `release-service`, giả định public key đã được provision từ **nguồn tin cậy ngoài request**.
- `attacker`: key pair hoàn toàn khác mà kẻ tấn công tự sinh.

Cả hai đều có thể ký cùng một message ghi `issuer=release-service`. Phép xác minh dưới key của attacker vẫn đúng về mật mã, nhưng không tạo ra quyền sử dụng danh tính `release-service`.

### 3.1. Mã chạy độc lập — `Ed25519IdentityBoundaryDemo.java`

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;

public class Ed25519IdentityBoundaryDemo {
    static byte[] sign(PrivateKey privateKey, byte[] data) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(data);
        return signer.sign();
    }

    static boolean verify(PublicKey key, byte[] data, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPair trusted = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        KeyPair attacker = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();

        byte[] claim = ("domain=release-approval/v1\n"
                + "issuer=release-service\n"
                + "audience=deploy-api\n"
                + "action=publish\n").getBytes(StandardCharsets.UTF_8);

        byte[] attackerSignature = sign(attacker.getPrivate(), claim);
        byte[] trustedSignature = sign(trusted.getPrivate(), claim);

        System.out.println("attackerKeyVerifies=" +
                verify(attacker.getPublic(), claim, attackerSignature));
        System.out.println("trustedKeyRejectsAttackerSignature=" +
                !verify(trusted.getPublic(), claim, attackerSignature));
        System.out.println("trustedSignatureVerifies=" +
                verify(trusted.getPublic(), claim, trustedSignature));

        byte[] changed = claim.clone();
        changed[changed.length - 2] = (byte) 'X';
        System.out.println("changedBytesRejected=" +
                !verify(trusted.getPublic(), changed, trustedSignature));

        byte[] transportedSpki = attacker.getPublic().getEncoded();
        PublicKey decoded = KeyFactory.getInstance("Ed25519")
                .generatePublic(new X509EncodedKeySpec(transportedSpki));

        System.out.println("decodedUntrustedKeyStillVerifies=" +
                verify(decoded, claim, attackerSignature));
        System.out.println("decodedKeyEqualsPinned=" +
                Arrays.equals(decoded.getEncoded(),
                        trusted.getPublic().getEncoded()));
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 Ed25519IdentityBoundaryDemo.java
java Ed25519IdentityBoundaryDemo
~~~

**Stdout chính xác** (đã kiểm tra bằng JDK 24):

~~~text
attackerKeyVerifies=true
trustedKeyRejectsAttackerSignature=true
trustedSignatureVerifies=true
changedBytesRejected=true
decodedUntrustedKeyStillVerifies=true
decodedKeyEqualsPinned=false
~~~

### 3.2. Đọc kết quả cho đúng

**`attackerKeyVerifies=true`:** Attacker biết private key của mình và tạo chữ ký hợp lệ. Điều này không có gì đáng ngạc nhiên: bất kỳ ai cũng có thể tự sinh Ed25519 key pair và ký dữ liệu họ muốn.

**`trustedKeyRejectsAttackerSignature=true`:** Khi cùng message và chữ ký của attacker được xác minh bằng **public key đã pin của release-service**, phép kiểm tra không chấp nhận. Đây chính là ranh giới trust.

**`trustedSignatureVerifies=true`:** Chữ ký do private key tương ứng với public key đã pin tạo ra xác minh đúng. Nhưng bước **authorization** vẫn cần kiểm tra riêng; chưa nên cấp quyền chỉ nhờ dòng `true` này.

**`changedBytesRejected=true`:** Thay một byte của payload khiến chữ ký cũ không hợp lệ. Chữ ký bảo vệ **byte representation được ký**; nếu nội dung business được parse/biến đổi, ứng dụng phải có quy tắc đồng nhất.

**`decodedUntrustedKeyStillVerifies=true`:** Một public key attacker gửi dưới dạng SubjectPublicKeyInfo bytes có thể được `KeyFactory` parse thành `PublicKey` và vẫn xác minh chữ ký attacker. **Parse/deserialize key không biến nó thành trusted key.**

**`decodedKeyEqualsPinned=false`:** SPKI bytes của attacker khác khóa đã được pin. Trong demo, `Arrays.equals` đủ để minh họa khác biệt của hai key; trong ứng dụng bảo mật, cần so key material/identifier qua bản tin cậy, và nếu so secret thì dùng so sánh phù hợp chống timing leakage. Chống key substitution chủ yếu là **nguồn cấp khóa đáng tin**, không phải bản thân hàm so sánh.

> Trong demo, `trusted` và `attacker` được sinh mới mỗi lần chạy chỉ để minh họa. Trong hệ thống thật, khóa tin cậy của release-service phải được **cấp phát và phân phối qua quy trình tin cậy**, không thể tự tạo một key “trusted” mới cho mỗi request.

## 4. Vì sao việc kèm public key hoặc chứng thư chưa đủ chứng minh danh tính?

### 4.1. Public key do request tự đưa vào: chỉ là input không tin cậy

Đây là thiết kế dễ bị key substitution:

~~~text
Request:
  claimed_issuer = "release-service"
  public_key = <attacker's Ed25519 public key>
  payload = <attacker-chosen bytes>
  signature = Sign(attacker_private, payload)

Server:
  Verify(public_key FROM REQUEST, payload, signature) == true
  => (SAI) authenticated_issuer = "release-service"
~~~

Server chỉ chứng minh attacker có private key của public key attacker đã gửi. **Không có mối liên hệ đáng tin giữa public key đó và release-service.**

**Thiết kế đúng:** Server lấy public key từ **trusted registry**, được provision ngoài request hoặc được ràng buộc với một chuỗi chứng thư đã validate tới trust anchor tin cậy. Payload có thể chứa `kid` làm **gợi ý chọn key** trong registry nhưng `kid` không tự làm key đáng tin.

### 4.2. Key pinning / registry theo service hoặc tenant

Một hệ thống nội bộ có thể lưu:

~~~text
trusted signer registry (được cấu hình/provision an toàn):
  kid: "prod-key-1"
  algorithm: Ed25519
  principal: "release-service"
  permitted_actions: ["publish"]
  audiences: ["deploy-api"]
  status: active
  public_key: <known Ed25519 public key/SPKI>
  rotation_policy: <managed out-of-band>
~~~

Đường tin cậy:

~~~text
Untrusted request --kid--> tra trong trusted registry
                               |
                   không thấy: REJECT
                               |
                          trusted public key
                               |
                 verify(signature, exact signed bytes)
                               |
                  map key -> trusted principal
                               |
        validate audience / action / expiration / nonce
                               |
                       ALLOW or REJECT
~~~

**Không được** lấy `kid` rồi tự tạo mục trust mới từ `public_key` của request. Nếu `kid` dùng để gọi URL/đọc file, cần giới hạn lookup theo danh sách/namespace được phép, không nối tùy ý vào đường dẫn hay truy cập mạng.

Các mục registry cần được cấp quyền cập nhật; key rotation, thu hồi/disable và tenant isolation phải được thực hiện qua một control plane đáng tin. Việc ai **có quyền ghi registry** quan trọng không kém thuật toán chữ ký.

### 4.3. X.509/PKIX: xác minh chuỗi và mục đích, không chỉ parse certificate

Trong mô hình PKI:
1. Bên gửi có thể kèm **end-entity certificate** và các intermediate certificates.
2. Verifier xây/kiểm tra đường chứng thư với `CertPathValidator.getInstance("PKIX")`, trust anchors **do verifier tự tin cậy**.
3. Kiểm tra tính hợp lệ theo thời gian, các ràng buộc CA/path, key usage/extended key usage theo ứng dụng, revocation policy theo yêu cầu, và **định danh được chứng nhận** (DNS name, URI, service identity hoặc subject claim theo profile).
4. Chỉ sau đó mới gắn public key trong end-entity cert với một principal cụ thể, và kiểm tra chữ ký EdDSA trên payload với khóa ấy.
5. Cuối cùng áp dụng **authorization** và các kiểm tra ngữ cảnh.

Một certificate **được parse thành công** bằng `CertificateFactory` không có nghĩa đã validate. Một certificate **tự ký** có chữ ký đúng dưới public key của chính nó cũng không tự trở thành tin cậy; trust anchor phải được chỉ định độc lập. Ngay cả một path PKIX hợp lệ cũng **không đủ** nếu certificate chứng nhận danh tính/usage **khác** danh tính/usage ứng dụng đang cần.

**Cần phân biệt hai “X.509” thường thấy:**

- `X509EncodedKeySpec` đọc public key từ **SubjectPublicKeyInfo** encoded bytes; đây **không phải** X.509 certificate và không bao gồm một PKIX path đáng tin cậy.
- `X509Certificate` là một chứng thư có issuer/subject/validity/extensions/signature. Nó vẫn cần trust path và identity policy.

Đừng nhầm `certificate.verify(certificate.getPublicKey())` với “đã được CA đáng tin xác nhận”: với certificate tự ký, lệnh đó chỉ chứng minh chữ ký tự ký khớp public key bên trong certificate.

## 5. Ràng buộc dữ liệu đã ký với đúng mục đích và ngữ cảnh

Một chữ ký Ed25519 không tự hiểu từ `"publish"` là “lệnh triển khai trong hệ thống A”, hay từ `"admin"` là một principal đáng tin. Hãy đưa đầy đủ **security-relevant fields** vào phần bytes được ký.

| Trường | Tại sao nên nằm trong signed bytes? | Kiểm tra thêm ngoài crypto |
| --- | --- | --- |
| Protocol/domain/version | Chống một chữ ký bị tái sử dụng sang protocol khác | Chỉ chấp nhận version/purpose đã cấu hình |
| `kid` | Chống thay thế key routing metadata mà không thay chữ ký | Chỉ chọn key từ trusted allowlist |
| `issuer` / tenant | Gắn claim với ngữ cảnh signer | So claim với identity ánh xạ từ trusted key |
| `audience` / recipient | Chặn mang token từ dịch vụ A sang B | So với audience hiện tại, không tin claim tùy ý |
| `action` / scope | Ngăn đổi hành động trên đường truyền | Kiểm tra quyền của principal từ policy |
| `resource` | Ngăn dùng chữ ký cho tài nguyên khác | Kiểm tra quyền trên đúng tài nguyên |
| `expiresAt` và, nếu cần, `notBefore` | Giới hạn thời gian hiệu lực | Dùng clock và chính sách lệch giờ có kiểm soát |
| `nonce` / request ID / sequence | Giảm nguy cơ phát lại | Lưu trạng thái đã dùng, check atomically |
| Payload/body/hash theo chuẩn | Bảo vệ đúng dữ liệu được phê duyệt | Validate schema, size, semantics |

**Chỉ ký những trường này chưa phải đủ.** Nếu signer đã được cấp key nhưng không có quyền `delete`, nó vẫn có thể **ký một message chứa `action=delete`** với chữ ký đúng. Server phải kiểm tra allowed actions từ policy do verifier tin cậy, không tự tin vào role/scope được bên ký tự khai báo.

### 5.1. Domain separation ở tầng ứng dụng

`Signature.getInstance("Ed25519")` ký trên những bytes mà ứng dụng truyền cho `update(...)`. Trong ví dụ, chúng ta thêm chuỗi `release-approval/protocol-v1` vào dữ liệu đã ký, tránh dùng chữ ký của một thông điệp ở ngữ cảnh khác như một lệnh deployment.

Không nhầm application-level domain separation này với chế độ Ed25519ctx/Ed25519ph của RFC 8032. Các biến thể đó có semantics riêng; **ký một SHA-256 digest bằng Ed25519 thường không tự biến thành Ed25519ph**. Nếu tích hợp một protocol cụ thể, triển khai đúng thuật toán/parameter của protocol đã tiêu chuẩn hóa.

### 5.2. Canonical encoding và ambiguity

Nếu ghép không rõ ràng:

~~~text
tenant = "ab"  action = "c"  -> "abc"
tenant = "a"   action = "bc" -> "abc"
~~~

thì hai bộ field khác nhau có thể cho cùng bytes. Dùng representation **không mơ hồ**: length prefix/typed encoding hoặc một canonical serialization được quy định bởi protocol. Phải đồng ý về UTF-8, thứ tự field, endian của integer, null/empty, normalization, thời gian, cách mã hóa số, và cách xử lý field lạ.

Nếu ký JSON, có hai hướng phổ biến:
- Ký **raw bytes chính xác** của một payload được coi là opaque và không tự serialize lại giữa ký–verify; nhưng phải bảo đảm consumer đọc đúng các bytes đó và không có semantic ambiguity.
- Ký **canonical JSON/CBOR** theo định dạng/protocol được các bên thống nhất; không tự phát minh cách sắp xếp và strip whitespace chỉ vì “trông giống nhau”.

Đừng để signer kiểm tra một dạng còn phần authorization parse một dạng khác (parser differential), vì khi đó chữ ký có thể hợp lệ cho bytes nhưng policy diễn giải không giống điều được phê duyệt.

## 6. Ví dụ 2: chữ ký hợp lệ phải đi qua trust, authorization và replay checks

Chương trình tạo một registry **do verifier giữ**: `prod-key-1` là public key của `release-service`, chỉ được `publish` cho `deploy-api`. Yêu cầu mang các field được ký bằng Ed25519. Để tránh phụ thuộc canonical JSON trong một bài về identity trust, demo dùng format nhị phân **có trường độ dài rõ ràng** qua `DataOutputStream`:

~~~text
field(domain = "release-approval/protocol-v1")
field(kid)
field(issuer)
field(audience)
field(action)
int64(expiresAt)       // big-endian
field(nonce)

field(s) = int32(byteLengthOfUtf8(s)) || UTF8(s)
~~~

Tất cả các field quan trọng đều nằm trong chữ ký. Phần mã là **mô hình học tập**, không phải giao thức mạng tiêu chuẩn. Ứng dụng thật cần schema versioning, giới hạn tổng kích thước, parser có kiểm tra độ dài và chính sách exception/fail closed.

### 6.1. Mã chạy độc lập — `TrustedEd25519EnvelopeDemo.java`

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class TrustedEd25519EnvelopeDemo {
    record Envelope(String kid, String issuer, String audience,
                    String action, long expiresAt, String nonce) {}
    record TrustedKey(PublicKey key, String issuer, Set<String> allowedActions) {}

    static void field(DataOutputStream out, String value) throws IOException {
        if (value == null || value.length() > 128) {
            throw new IllegalArgumentException("Invalid field");
        }
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    static byte[] canonical(Envelope e) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            field(out, "release-approval/protocol-v1");
            field(out, e.kid());
            field(out, e.issuer());
            field(out, e.audience());
            field(out, e.action());
            out.writeLong(e.expiresAt());
            field(out, e.nonce());
        }
        return bytes.toByteArray();
    }

    static byte[] sign(PrivateKey key, Envelope e) throws Exception {
        Signature s = Signature.getInstance("Ed25519");
        s.initSign(key);
        s.update(canonical(e));
        return s.sign();
    }

    static boolean verify(PublicKey key, Envelope e, byte[] sig)
            throws Exception {
        Signature s = Signature.getInstance("Ed25519");
        s.initVerify(key);
        s.update(canonical(e));
        return s.verify(sig);
    }

    static boolean accept(Envelope e, byte[] sig, Map<String, TrustedKey> keys,
                          String requiredAudience, long now, Set<String> seen)
            throws Exception {
        TrustedKey trusted = keys.get(e.kid());
        if (trusted == null) return false;
        if (!trusted.issuer().equals(e.issuer())) return false;
        if (!requiredAudience.equals(e.audience())) return false;
        if (!trusted.allowedActions().contains(e.action())) return false;
        if (e.nonce() == null || e.nonce().isBlank()) return false;
        if (e.expiresAt() <= now || e.expiresAt() > now + 300) return false;
        if (!verify(trusted.key(), e, sig)) return false;

        // Atomic only in this single-threaded example.
        return seen.add(e.kid() + ":" + e.nonce());
    }

    public static void main(String[] args) throws Exception {
        KeyPair service = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        KeyPair attacker = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        Map<String, TrustedKey> trusted = Map.of(
                "prod-key-1", new TrustedKey(
                        service.getPublic(), "release-service",
                        Set.of("publish")));
        long now = 1_800_000_000L;
        Set<String> seen = new HashSet<>();

        Envelope good = new Envelope(
                "prod-key-1", "release-service", "deploy-api",
                "publish", now + 60, "nonce-001");
        byte[] validSig = sign(service.getPrivate(), good);
        System.out.println("acceptedFirst=" +
                accept(good, validSig, trusted, "deploy-api", now, seen));
        System.out.println("replayRejected=" +
                !accept(good, validSig, trusted, "deploy-api", now, seen));

        Envelope wrongAudience = new Envelope(
                "prod-key-1", "release-service", "other-api",
                "publish", now + 60, "nonce-002");
        System.out.println("wrongAudienceRejected=" +
                !accept(wrongAudience, sign(service.getPrivate(), wrongAudience),
                        trusted, "deploy-api", now, seen));

        Envelope unauthorized = new Envelope(
                "prod-key-1", "release-service", "deploy-api",
                "delete", now + 60, "nonce-003");
        System.out.println("validButUnauthorizedSignature=" +
                verify(service.getPublic(), unauthorized,
                        sign(service.getPrivate(), unauthorized)));
        System.out.println("unauthorizedRejected=" +
                !accept(unauthorized, sign(service.getPrivate(), unauthorized),
                        trusted, "deploy-api", now, seen));

        Envelope wrongIssuer = new Envelope(
                "prod-key-1", "finance-admin", "deploy-api",
                "publish", now + 60, "nonce-004");
        System.out.println("issuerMismatchRejected=" +
                !accept(wrongIssuer, sign(service.getPrivate(), wrongIssuer),
                        trusted, "deploy-api", now, seen));

        Envelope expired = new Envelope(
                "prod-key-1", "release-service", "deploy-api",
                "publish", now - 1, "nonce-005");
        System.out.println("expiredRejected=" +
                !accept(expired, sign(service.getPrivate(), expired),
                        trusted, "deploy-api", now, seen));

        Envelope forged = new Envelope(
                "attacker-key", "release-service", "deploy-api",
                "publish", now + 60, "nonce-006");
        byte[] forgedSig = sign(attacker.getPrivate(), forged);
        System.out.println("forgedSignatureIsValidUnderAttackerKey=" +
                verify(attacker.getPublic(), forged, forgedSig));
        System.out.println("untrustedKidRejected=" +
                !accept(forged, forgedSig, trusted, "deploy-api", now, seen));

        Envelope edited = new Envelope(
                "prod-key-1", "release-service", "deploy-api",
                "delete", now + 60, "nonce-001");
        System.out.println("editedPayloadFailsCrypto=" +
                !verify(service.getPublic(), edited, validSig));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 TrustedEd25519EnvelopeDemo.java
java TrustedEd25519EnvelopeDemo
~~~

**Stdout chính xác** (đã đối chiếu trên JDK 24):

~~~text
acceptedFirst=true
replayRejected=true
wrongAudienceRejected=true
validButUnauthorizedSignature=true
unauthorizedRejected=true
issuerMismatchRejected=true
expiredRejected=true
forgedSignatureIsValidUnderAttackerKey=true
untrustedKidRejected=true
editedPayloadFailsCrypto=true
~~~

### 6.2. Điều gì được chứng minh?

- `acceptedFirst=true`: đúng key trong registry, đúng principal, đúng audience, đúng action, chưa hết hạn và nonce chưa từng chấp nhận.
- `replayRejected=true`: cùng một message + chữ ký đã **vẫn verify cryptographically**, nhưng không được chấp nhận lần thứ hai.
- `wrongAudienceRejected=true`: dù service thật đã ký, request dành cho `other-api` không được dùng tại `deploy-api`.
- `validButUnauthorizedSignature=true` cùng `unauthorizedRejected=true`: signer **đáng tin** vẫn có thể ký một lệnh `delete` mà chính sách không cho phép. Đây là ranh giới **authentication → authorization**.
- `issuerMismatchRejected=true`: key pin cho `release-service` không được biến thành `finance-admin` chỉ vì trường `issuer` có nội dung ấy.
- `expiredRejected=true`: chữ ký không tự có hạn; expiry là một ràng buộc **do protocol và verifier cùng thi hành**.
- `forgedSignatureIsValidUnderAttackerKey=true` nhưng `untrustedKidRejected=true`: attacker có thể ký bằng key riêng; registry **không có key ấy**, nên không chấp nhận.
- `editedPayloadFailsCrypto=true`: thay action sau khi ký khiến cùng chữ ký xác minh thất bại với message bytes mới.

**Không có “giải mã” để nhận danh tính từ signature bytes.** Danh tính tin cậy chỉ đến từ ánh xạ `trustedKey → principal` mà verifier kiểm soát.

### 6.3. Giới hạn của ví dụ để không dùng sai trong production

- `Map.of(...)` giả lập trusted registry, được khởi tạo ở chương trình để test. Hệ thống thật phải **provision khóa từ nguồn đáng tin** (ví dụ cấu hình ký số/hệ thống cấp khóa/certificate policy), có rotation và thu hồi.
- `now = 1_800_000_000L` là clock **cố định chỉ phục vụ test**. Ở production dùng clock tin cậy của verifier như `Instant.now()`/`Clock`, có quy tắc thời gian rõ ràng. Không để client quyết định “bây giờ là mấy giờ”.
- `now + 300` diễn tả thời hạn tối đa đơn giản. Mã production phải xử lý overflow, clock skew, giới hạn `notBefore`/`issuedAt` và chính sách expiresAt phù hợp.
- `HashSet` trong demo chạy một luồng. Với nhiều request, `nonce`/request ID phải được **check-and-insert atomically**, có TTL phù hợp và trạng thái chia sẻ giữa các node nếu ứng dụng phân tán; không dùng `contains` rồi `add` tách rời trong môi trường cạnh tranh.
- Key `kid` + nonce là khóa replay cache minh họa. Trong hệ thống thật, chọn scope (principal, tenant, audience, key rotation) cho phù hợp; bảo đảm nonce không thể dùng lại sau khi chính sách hết hạn/khởi động lại khi vẫn còn hiệu lực.
- Bản encoding có một field-length cap nhưng không phải complete parser, không có transport schema/hardening đầy đủ. Production nên dùng một protocol/serialization có đặc tả rõ ràng và giới hạn message size.
- Các hàm demo dùng `throws Exception` để nhìn rõ API. Dịch vụ thật phải phân loại malformed input, unsupported algorithms, invalid keys, exception, key revocation rồi **reject**, không bỏ qua.
- Việc `accept(...)` check một số policy trước khi verify chỉ là **nhánh từ chối không có side effect cấp quyền**. Bất kỳ hành động cấp quyền/chấp nhận request đều phải xảy ra **sau** khi toàn bộ chữ ký, trust và policy thành công.
- `Signature` có trạng thái qua `initSign/initVerify/update/sign/verify`; trong code minh họa tạo engine mới mỗi lần. Đừng chia sẻ một instance `Signature` giữa các threads mà không có thiết kế đồng bộ phù hợp.

## 7. Ed448 cũng chịu đúng ranh giới trust

Ed448 là biến thể EdDSA khác, hỗ trợ qua `KeyPairGenerator.getInstance("Ed448")` và `Signature.getInstance("Ed448")` khi JCA provider của JDK có thuật toán đó. Cơ chế xác minh chữ ký **không tự xác định danh tính** với Ed448 cũng y như Ed25519.

### 7.1. Chương trình Ed448 độc lập

**Tệp `Ed448SmokeTest.java`:**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class Ed448SmokeTest {
    public static void main(String[] args) throws Exception {
        KeyPair keys = KeyPairGenerator.getInstance("Ed448").generateKeyPair();
        byte[] message = "Ed448 signature verification demo"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed448");
        signer.initSign(keys.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed448");
        verifier.initVerify(keys.getPublic());
        verifier.update(message);
        System.out.println("ed448Valid=" + verifier.verify(signature));
        System.out.println("signatureBytes=" + signature.length);

        Signature altered = Signature.getInstance("Ed448");
        altered.initVerify(keys.getPublic());
        altered.update("a different message".getBytes(StandardCharsets.UTF_8));
        System.out.println("changedMessageRejected=" +
                !altered.verify(signature));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 Ed448SmokeTest.java
java Ed448SmokeTest
~~~

Kết quả trong môi trường JDK 24:

~~~text
ed448Valid=true
signatureBytes=114
changedMessageRejected=true
~~~

Ed448 trong RFC 8032 có chữ ký **114 bytes**; Ed25519 có chữ ký **64 bytes**. Kích thước chữ ký là thuộc tính định dạng, **không phải bằng chứng một key thuộc về danh tính nào**. Cũng không thay thế việc kiểm tra provenance của key, certificate chain, issuer, audience hay quyền.

## 8. Các tình huống tấn công và phản ứng đúng

### 8.1. Key substitution

**Tấn công:** API cho phép request kèm `public_key` rồi dùng ngay để verify, sau đó gán danh tính từ trường `issuer`.

**Kết quả:** Attacker tạo key, tự ký, tự nhận danh tính khác; `verify==true`.

**Phòng chống:** Lấy public key từ trusted mapping hoặc PKIX path/identity validation đúng chính sách; không tin public key do request tự phát làm anchor.

### 8.2. Self-signed certificate masquerading

**Tấn công:** Request kèm certificate tự ký, code chỉ kiểm tra chữ ký của certificate bằng chính public key trong certificate và tin subject name.

**Kết quả:** Attacker tự tạo certificate có `CN=release-service` và tự ký; việc ký certificate tự nó không làm CA trở thành trusted.

**Phòng chống:** Chỉ tin trust anchors provision ngoài request; validate PKIX path và identity/usage; không tự động “trust on first use” nếu protocol không thiết kế và chấp nhận rõ ràng chính sách TOFU đó.

### 8.3. Algorithm confusion / untrusted `alg`

**Tấn công:** Payload đưa `alg=none` hoặc tên thuật toán khác, ứng dụng tự chọn verifier theo giá trị do attacker điều khiển mà không có policy chặt.

**Phòng chống:** Ràng buộc thuật toán với key đã provision và protocol allowlist; không chấp nhận thuật toán yếu/không được phép, không tự fallback khi verify sai. `kid` chỉ chọn **một trusted record**, không áp đặt trust.

### 8.4. Cross-protocol / cross-service replay

**Tấn công:** Một chữ ký hợp lệ cho `service-A` được chuyển sang `service-B`; hai nơi tình cờ parse cùng bytes và dùng cùng key.

**Phòng chống:** Đưa domain/purpose/version và audience của từng protocol vào phần đã ký; mỗi verifier so với giá trị **cục bộ đang mong đợi**.

### 8.5. Valid signer, unauthorized action

**Tấn công:** Một service có Ed25519 key hợp lệ nhưng chỉ được phép `publish` ký payload `action=delete`. Nếu server tin trường action đã ký nghĩa là được cấp quyền, nó có thể nâng quyền ngoài ý muốn.

**Phòng chống:** `Signature.verify` xác nhận key đã ký **đúng những bytes đó**, không xác nhận quyền. Kiểm tra ACL/RBAC/ABAC/tenant/resource policy độc lập từ trusted principal.

### 8.6. Replay dù chữ ký vẫn đúng

**Tấn công:** Attacker copy một request đã ký hợp lệ rồi gửi lại nhiều lần.

**Phòng chống:** Nonce/idempotency key/monotonic sequence được ký, thời hạn sống ngắn, replay cache/check-and-insert atomically. `Signature.verify` sẽ tiếp tục đúng với cùng signature và cùng bytes — đây là đặc tính của chữ ký, không phải bug.

### 8.7. Key compromise và trạng thái thu hồi

**Tình huống:** Private key thật bị lộ. Attacker ký đúng bằng key từng được hệ thống pin.

**Kết quả:** Crypto vẫn `true`, key mapping vẫn nói `release-service` nếu registry chưa được cập nhật. Chữ ký không tự phát hiện khóa bị lộ.

**Phòng chống:** Bảo vệ private keys bằng quản lý khóa/HSM/KMS theo khả năng, kiểm soát quyền ký, giám sát, quy trình revoke/rotate, cập nhật trust registry và xử lý chứng thư revoked theo chính sách. Định nghĩa cách xử lý các chữ ký lịch sử, timestamp và effective time rõ ràng.

### 8.8. Canonicalization và parser disagreement

**Tình huống:** Một hệ thống verify chữ ký trên raw JSON, hệ thống sau đó parse JSON với quy tắc khác (duplicate keys, number representation, Unicode). Nếu các thành phần diễn giải khác nhau, quyết định authorization có thể sai dù chữ ký đúng với bytes.

**Phòng chống:** Kiểm tra canonical encoding/duplicate keys/schema nhất quán; chỉ một cấu trúc được diễn giải theo một policy; dùng serialization/protocol được tiêu chuẩn hóa khi cần tính tương tác.

## 9. Triển khai trong hệ thống thực tế

### 9.1. Một checklist xác minh cho server

- [ ] **Trust source:** Public key được provision an toàn hoặc lấy qua PKIX path đã validate tới trust anchor tin cậy.
- [ ] **Principal binding:** Key được map tới issuer/tenant/service/subject identity theo chính sách, không suy ra từ claim tự xưng.
- [ ] **Algorithm binding:** Ed25519/Ed448 được ấn định bởi trusted key record/protocol; reject key/algorithm mismatch, không downgrade.
- [ ] **Exact signed bytes:** Kiểm tra signature trên chính bytes mà business logic sử dụng, có canonicalization không mơ hồ.
- [ ] **Context binding:** Domain/purpose/version, key ID, issuer, audience, action/resource, expiry/nonce nằm trong phần có chữ ký khi áp dụng.
- [ ] **Validation:** Field types, max size, allowed values, protocol version và dữ liệu đầu vào được kiểm tra; malformed input bị reject.
- [ ] **Authorization:** Trusted principal có quyền hành động trên tài nguyên/tenant này; chữ ký không thay kiểm tra quyền.
- [ ] **Freshness:** Kiểm tra clock, expiry, nonce/replay cache/sequence; xử lý đua tranh khi có nhiều node.
- [ ] **Key lifecycle:** Rotate/disable/revoke, không sử dụng key đã bị thu hồi; cấu hình đồng bộ đến mọi verifier.
- [ ] **Errors and observability:** Lỗi signature/trust/policy không làm request được chấp nhận; log nguyên nhân vừa đủ, không log private key hoặc bí mật.
- [ ] **Negative tests:** Thử attacker key, sửa bytes, đổi audience/issuer, replay, hết hạn, key chưa provision và valid signer thiếu quyền.

### 9.2. Những kiểm thử tự động nên có

| Test case | Crypto verify | Trusted identity/policy | Kết quả cuối |
| --- | --- | --- | --- |
| Key service đã pin, đúng message và policy | `true` | Hợp lệ | **ALLOW** |
| Attacker tự ký, gửi public key của attacker | `true` **nếu dùng key attacker** | Key không nằm trong trust registry | **REJECT** |
| Attacker ký, verifier dùng key service đã pin | `false` | Không xét cấp quyền | **REJECT** |
| Service thật ký `action=delete` nhưng chỉ có quyền `publish` | `true` | Không đủ quyền | **REJECT** |
| Service thật ký cho audience khác | `true` | Audience mismatch | **REJECT** |
| Một request hợp lệ gửi lần thứ hai | `true` | Replay nonce/sequence | **REJECT** |
| Request đúng chữ ký nhưng hết hạn | `true` | Freshness fail | **REJECT** |
| Message đổi một byte sau ký | `false` | Không xét cấp quyền | **REJECT** |
| `kid` không tồn tại/đã revoke | Có thể không chạy crypto | Không trusted key | **REJECT** |
| Certificate tự ký chưa được trust | Có thể chứng minh self-signature | Không có trusted path | **REJECT** |

### 9.3. Quy tắc kiểm tra certificate/path khi dùng PKIX

Bài này không tự dựng CA/certificate chain giả để tránh đưa ra một quy trình PKI thiếu bước. Trong ứng dụng có X.509, tham khảo Java PKI Programmer's Guide và API:
- `CertificateFactory.getInstance("X.509")` để parse chứng thư/đường chứng thư.
- `CertPathBuilder.getInstance("PKIX")` nếu cần dựng path.
- `CertPathValidator.getInstance("PKIX")` để validate path theo `PKIXParameters`/`TrustAnchor` được cung cấp từ **trust store độc lập**.
- Kiểm tra identity/subjectAltName/ExtendedKeyUsage/KeyUsage theo loại chứng thư và protocol đang dùng, validity, revocation policy phù hợp và các ràng buộc riêng.
- `endEntityCert.getPublicKey()` chỉ là một public key để dùng cho xác minh **sau khi** trust/identity được thiết lập; nó không mang trust đến chỉ vì phương thức này trả về không null.

Không lấy public key trong chứng thư do attacker gửi rồi dùng chính nó làm `TrustAnchor`. Làm như vậy xóa bỏ ranh giới trust.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Attacker sinh một Ed25519 key pair, ký message `issuer=admin`, rồi server verify bằng public key attacker gửi. `verify==true` chứng minh điều gì?

**Đáp án:** Chứng minh chữ ký khớp message và public key attacker đưa vào, không chứng minh attacker là `admin` hoặc có quyền admin.

**Câu 2.** Một Ed25519 key nằm trong trust registry của `report-service`, nhưng message được ký ghi `issuer=payment-service`. Có nên chấp nhận?

**Đáp án:** Không. Cần đối chiếu issuer được ký với principal được registry ràng buộc theo key đã được tin cậy; chữ ký đúng không làm thay đổi danh tính.

**Câu 3.** Một service có khóa hợp lệ chỉ được `publish`, nhưng nó ký yêu cầu `delete` và verify thành công. Có được thi hành `delete`?

**Đáp án:** Không. Authentication/chữ ký đúng không thay thế authorization trên action/resource.

**Câu 4.** Chữ ký của một request đã được chấp nhận lần thứ nhất có thể verify đúng lần thứ hai không?

**Đáp án:** Có. Đó là lý do cần cơ chế replay protection độc lập như nonce/sequence và expiry được ký.

**Câu 5.** `new X509EncodedKeySpec(bytes)` và `KeyFactory.generatePublic(...)` thành công có chứng minh key belongs to `release-service`?

**Đáp án:** Không. Đó là decode public key ở định dạng SPKI; không phải xác minh chứng thư/chuỗi trust hoặc ràng buộc danh tính.

**Câu 6.** Một certificate tự ký có `CN=release-service` và `cert.verify(cert.getPublicKey())` đúng. Có được dùng làm trust anchor mặc định không?

**Đáp án:** Không. Certificate có thể do bất kỳ ai tự ký. Trust anchor phải đến từ nguồn được verifier cấu hình tin cậy độc lập; sau đó cần kiểm tra path/identity/usage.

**Câu 7.** Nếu sign trên JSON rồi bên nhận tự sắp xếp trường khác thứ tự, chuyện gì xảy ra?

**Đáp án:** Byte representation có thể khác và chữ ký sẽ không verify, hoặc các parser có thể hiểu khác nhau. Cần quy ước ký raw bytes hoặc canonical serialization thống nhất và kiểm tra schema.

**Câu 8.** Đưa `purpose=release-approval/v1` vào signed bytes giúp gì?

**Đáp án:** Ràng buộc chữ ký với mục đích và version cụ thể, hạn chế lấy chữ ký hợp lệ của một protocol khác dùng sai ngữ cảnh. Verifier vẫn phải so purpose với protocol đang mong đợi.

**Câu 9.** Nếu private key đã bị lộ, `verify==true` có bảo đảm người chủ khóa ban đầu ký không?

**Đáp án:** Không. Chữ ký chỉ chứng minh người tạo có khả năng dùng private key tương ứng. Cần key security, revocation/rotation, chính sách sự cố và giám sát.

## Ghi nhớ

- **`Signature.verify()==true` không bằng “danh tính đáng tin”.** Nó chỉ chứng minh sự phù hợp mật mã giữa signature, message bytes và public key.
- **Public key phải có provenance đáng tin:** pin/registry hoặc chứng thư có PKIX path và identity validation. Public key do request tự đính kèm không tạo trust.
- **Danh tính không đồng nghĩa quyền:** key được cấp cho một principal không tự cho principal ấy thực thi mọi action.
- **Cần ràng buộc context và freshness:** domain/version, issuer, audience, action, resource, expiry, nonce được ký rồi kiểm tra bằng policy của verifier.
- **Chống replay và key compromise là lớp bảo vệ riêng:** chữ ký hợp lệ có thể bị phát lại hoặc được tạo từ khóa bị lộ.
- **Dùng JCA Ed25519/Ed448 theo đúng protocol:** tạo `Signature` với thuật toán đáng tin cậy được cấu hình, verify đúng bytes, reject khi sai và không cho phép attacker tự chọn trust anchor.
- **Luôn có negative tests:** attacker key hợp lệ, trusted signer thiếu quyền, wrong audience, replay, expired, modified payload, unknown/revoked kid, chứng thư chưa trusted.

## Tài liệu tham khảo hiện hành

- [OpenJDK — JEP 339: Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339)
- [Oracle Java SE 25 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html)
- [Oracle Java SE 25 — `Signature` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html)
- [Oracle Java SE 25 — `KeyPairGenerator` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyPairGenerator.html)
- [Oracle Java SE 25 — `X509EncodedKeySpec` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html)
- [Oracle Java SE 25 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/25/security/java-pki-programmers-guide.html)
- [Oracle Java SE 25 — `CertPathValidator` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032)
- [RFC 5280 — X.509 PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
