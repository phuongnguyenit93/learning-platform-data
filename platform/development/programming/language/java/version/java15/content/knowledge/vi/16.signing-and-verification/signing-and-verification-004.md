# Chữ ký byte[] và mã hóa Base64 để truyền trong Java 15+

## 1. Bài toán cần giải quyết

Khi ký một thông điệp bằng API `java.security.Signature`, kết quả của `sign()` là **một mảng byte `byte[]`**, không phải một chuỗi văn bản. Chữ ký số là dữ liệu nhị phân, có thể chứa byte `0x00` hoặc các byte không tạo thành chuỗi UTF-8 hợp lệ. Nếu cần gửi chữ ký qua JSON, HTTP header, URL, hàng đợi thông điệp hay một trường văn bản trong cơ sở dữ liệu, ta thường **mã hóa Base64** để chuyển byte thành chuỗi ký tự ASCII an toàn cho kênh truyền.

Quy trình đầy đủ có hai phía:

~~~text
Bên ký:
  dữ liệu gốc --(quy ước byte cố định, ví dụ UTF-8)--> byte[] thông điệp
  private key + byte[] thông điệp --(Signature.sign)--> byte[] chữ ký
  byte[] thông điệp / byte[] chữ ký --(Base64)--> chuỗi để truyền

Bên xác minh:
  chuỗi nhận --(Base64 decoder)--> byte[] thông điệp, byte[] chữ ký
  public key đã được tin cậy + đúng byte[] thông điệp + byte[] chữ ký
      --(Signature.verify)--> hợp lệ / không hợp lệ
~~~

**Ba giới hạn quan trọng:**

1. **Base64 chỉ mã hóa, không ký và không mã hóa bí mật.** Ai cũng có thể giải mã Base64; việc đổi cách biểu diễn không tạo tính bảo mật.
2. **Chữ ký xác thực các byte đã ký**, không tự hiểu nội dung JSON, dấu tiếng Việt hay cấu trúc đối tượng Java. Chỉ cần một byte khác cũng có thể làm xác minh thất bại.
3. **`Signature.verify` chỉ đáng tin khi khóa công khai nhận từ nguồn xác thực.** Nếu kẻ tấn công được thay cả thông điệp, chữ ký và public key mà bên nhận chấp nhận hết, phép xác minh vẫn có thể trả `true` cho thông điệp giả mạo.

Trong Java 15, **EdDSA/Ed25519** được hỗ trợ chính thức (JEP 339). Bài thực hành dùng `Ed25519` với các API `KeyPairGenerator` và `Signature` còn được hỗ trợ trên JDK hiện đại. Mã minh họa tương thích Java 17+.

## 2. Phân biệt dữ liệu để ký với chuỗi để truyền

### 2.1. Luôn quy định byte[] thông điệp một cách tường minh

Nếu dữ liệu nghiệp vụ đang là `String`, hãy chọn encoding xác định, thông thường là UTF-8:

~~~java
String message = "Chào Việt Nam, đơn 42";
byte[] data = message.getBytes(StandardCharsets.UTF_8);
~~~

Phía xác minh phải nhận hoặc tái tạo **đúng mảng byte `data`** mà bên ký dùng. Dùng `getBytes()` không có charset có thể phụ thuộc vào cấu hình môi trường trong một số bối cảnh và làm hợp đồng dữ liệu kém rõ ràng; viết `StandardCharsets.UTF_8` để thể hiện chính xác chủ đích.

Ví dụ, hai chuỗi nhìn giống nhau nhưng một chuỗi dùng ký tự tiếng Việt ghép sẵn (NFC), chuỗi kia dùng ký tự kết hợp dấu (NFD), có thể tạo **byte UTF-8 khác nhau**. Tương tự, `"\n"` khác `"\r\n"`, JSON thêm khoảng trắng khác JSON không khoảng trắng, và thứ tự thuộc tính JSON khác nhau có thể tạo byte khác nhau. Chữ ký số **không tự chuẩn hóa** các khác biệt này.

Khi nhận thông điệp đã ký từ mạng, cách chắc chắn nhất là **giải mã đúng các byte của payload rồi xác minh trước khi parse/format lại**. Nếu giao thức yêu cầu chuẩn hóa (*canonicalization*), cả hai phía phải sử dụng **cùng một quy tắc được định nghĩa rõ**, không tự ý parse rồi serialize lại bằng mỗi thư viện một kiểu.

### 2.2. Chữ ký là byte[], không phải String

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(data);
byte[] signatureBytes = signer.sign();
~~~

Đây là **đoạn minh họa** giả sử đã có `privateKey` và `data`. Kết quả `signatureBytes` có dạng nhị phân theo thuật toán `Ed25519`, độ dài chữ ký chuẩn là **64 byte**. Không dùng:

~~~java
// SAI: mảng byte chữ ký không bắt buộc là văn bản UTF-8 hợp lệ.
String broken = new String(signatureBytes, StandardCharsets.UTF_8);
byte[] restored = broken.getBytes(StandardCharsets.UTF_8);
~~~

Chuyển nhị phân tùy ý sang `String` bằng UTF-8 có thể tạo ký tự thay thế cho chuỗi byte không hợp lệ; chuyển ngược không bảo đảm `Arrays.equals(signatureBytes, restored)`. Hãy dùng **Base64 encoder** để chuyển byte thành văn bản theo cách có thể đảo ngược chính xác.

### 2.3. Mã hóa chữ ký bằng Base64

~~~java
String encodedSignature = Base64.getEncoder().encodeToString(signatureBytes);
byte[] decodedSignature = Base64.getDecoder().decode(encodedSignature);
~~~

Lúc này `decodedSignature` trùng từng byte với `signatureBytes`. Cách mã hóa và giải mã phải **khớp cùng một biến thể Base64**. Đừng tự cắt, thay hoặc thay đổi ký tự trong chuỗi Base64 mà không có đặc tả giao thức.

## 3. Base64 thường, Base64URL và MIME khác nhau ra sao?

`java.util.Base64` cung cấp ba bộ mã hóa/giải mã chính thức:

| Biến thể | Encoder / decoder | Đặc điểm | Dùng khi |
| --- | --- | --- | --- |
| **Basic** theo RFC 4648 | `Base64.getEncoder()` / `Base64.getDecoder()` | Bảng chữ cái gồm chữ, số, `+` và `/`; thường có dấu đệm `=` cuối chuỗi; không tự xuống dòng. | JSON, file text hoặc giao thức chấp nhận các ký tự này. |
| **URL-safe (Base64URL)** | `Base64.getUrlEncoder()` / `Base64.getUrlDecoder()` | Thay `+` bằng `-`, thay `/` bằng `_`; có thể bỏ đệm bằng `withoutPadding()`. | URL path, query token hoặc giao thức quy định Base64URL. |
| **MIME** | `Base64.getMimeEncoder()` / `Base64.getMimeDecoder()` | Có quy tắc xuống dòng và decoder cho phép bỏ qua một số ký tự ngoài bảng mã. | Nội dung MIME/email khi giao thức yêu cầu. |

Ví dụ Base64URL không đệm:

~~~java
Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
Base64.Decoder decoder = Base64.getUrlDecoder();

String wireSignature = encoder.encodeToString(signatureBytes);
byte[] receivedSignature = decoder.decode(wireSignature);
~~~

`withoutPadding()` chỉ thay đổi **cách ghi văn bản Base64**, không sửa bytes nguồn và không tăng độ bảo mật. `getUrlDecoder()` có thể giải mã đầu vào Base64URL không có dấu `=` cuối theo quy tắc Javadoc; nếu giao thức yêu cầu một biểu diễn văn bản nhất quán, cả hai phía nên thống nhất rõ **có/không padding**.

**Không dùng nhầm decoder:** Basic và URL-safe có bảng chữ cái khác nhau. Một chuỗi không chứa `+`, `/`, `-` hoặc `_` có thể tình cờ được cả hai giải mã, nhưng điều đó **không có nghĩa hai format tương đương**. Với đầu vào từ mạng, nên dùng đúng decoder mà giao thức cho phép; không tự động thử mọi biến thể để “đoán”.

`Base64.Decoder.decode(...)` ném `IllegalArgumentException` với dữ liệu không đúng bảng chữ cái/cú pháp hợp lệ. Bộ giải mã MIME có đặc điểm bỏ qua ký tự khác, nên **không nên chọn MIME decoder làm bộ kiểm tra strict** cho một trường mà giao thức yêu cầu Base64URL.

## 4. Ký và xác minh byte[] bằng java.security.Signature

API `Signature` có ba bước rõ ràng ở hai vai trò:

| Bên ký | Bên xác minh |
| --- | --- |
| `Signature.getInstance("Ed25519")` | `Signature.getInstance("Ed25519")` |
| `initSign(privateKey)` | `initVerify(trustedPublicKey)` |
| `update(originalBytes)` | `update(receivedOriginalBytes)` |
| `byte[] sig = sign()` | `boolean valid = verify(receivedSigBytes)` |

`sign()` trả **bytes chữ ký**; `verify(byte[])` nhận **bytes chữ ký** đã giải mã Base64. Nó không nhận trực tiếp chuỗi Base64 và **không tự thực hiện Base64 decoding**. Trên receiver, phải chuyển văn bản về `byte[]` trước.

### Xác minh thất bại không nhất thiết chỉ trả false

Javadoc `Signature.verify(byte[])` quy định:

- Trả về **`true`** nếu chữ ký khớp với **đúng thông điệp, thuật toán và public key**.
- Trả về **`false`** nếu chữ ký đã xử lý hợp lệ về mặt định dạng nhưng không xác minh được.
- Có thể ném **`SignatureException`** nếu chữ ký có mã hóa không hợp lệ, sai kiểu, hoặc provider không xử lý được đầu vào.

Với `Ed25519`, việc thay ngẫu nhiên byte trong phần biểu diễn điểm elliptic của chữ ký có thể gây `SignatureException` (ví dụ điểm không giải mã được), **không chỉ trả `false`**. Vì vậy hệ thống cần xem **cả hai tình huống là kết quả từ chối**, nhưng vẫn có thể ghi lại loại lỗi để chẩn đoán.

Trong ví dụ chạy độc lập, hàm `verify` chỉ bắt `SignatureException` ở bước xác minh chữ ký và trả `false` cho chữ ký sai định dạng. Nó **không** bắt chung mọi `Exception` rồi coi hệ thống mã hóa hoạt động bình thường: lỗi khởi tạo thuật toán, key không hợp lệ hoặc provider có vấn đề cần được báo theo chính sách hệ thống.

## 5. Ví dụ đầy đủ: ký, Base64URL, truyền, giải mã và xác minh

Lưu file **`SignatureBase64Demo.java`** dưới UTF-8. Đây là chương trình Java SE độc lập, không cần thư viện thứ ba. Chương trình sinh key pair **chỉ để minh họa**, không in private key hay chữ ký ngẫu nhiên ra stdout, vì chúng không ổn định giữa các lần chạy.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.security.SignatureException;
import java.util.Arrays;
import java.util.Base64;

public class SignatureBase64Demo {
    private static boolean verify(byte[] message, byte[] signature, PublicKey key)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(message);
        try {
            return verifier.verify(signature);
        } catch (SignatureException malformedSignature) {
            return false;
        }
    }

    private static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println(label + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        String message = "Chao Viet Nam: đơn 42, Nguyễn";
        byte[] data = message.getBytes(StandardCharsets.UTF_8);

        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = generator.generateKeyPair();
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        Base64.Encoder wireEncoder = Base64.getUrlEncoder().withoutPadding();
        Base64.Decoder wireDecoder = Base64.getUrlDecoder();

        String dataOnWire = wireEncoder.encodeToString(data);
        String signatureOnWire = wireEncoder.encodeToString(signature);
        byte[] receivedData = wireDecoder.decode(dataOnWire);
        byte[] receivedSignature = wireDecoder.decode(signatureOnWire);

        check("utf8RoundTrip",
                message.equals(new String(receivedData, StandardCharsets.UTF_8)));
        check("bytesRoundTrip", Arrays.equals(data, receivedData));
        check("signatureRoundTrip", Arrays.equals(signature, receivedSignature));
        check("signatureLength64", signature.length == 64);
        check("verifyOriginal", verify(receivedData, receivedSignature, pair.getPublic()));

        byte[] changedData = "Chao Viet Nam: đơn 43, Nguyễn".getBytes(StandardCharsets.UTF_8);
        check("rejectChangedMessage",
                !verify(changedData, receivedSignature, pair.getPublic()));

        byte[] changedSignature = receivedSignature.clone();
        changedSignature[0] ^= 1;
        check("rejectChangedSignature",
                !verify(receivedData, changedSignature, pair.getPublic()));

        PublicKey unrelatedKey = generator.generateKeyPair().getPublic();
        check("rejectWrongKey", !verify(receivedData, receivedSignature, unrelatedKey));

        String basicText = Base64.getEncoder().encodeToString(signature);
        byte[] basicDecoded = Base64.getDecoder().decode(basicText);
        check("basicBase64", Arrays.equals(signature, basicDecoded));

        try {
            wireDecoder.decode("bad*base64");
            throw new AssertionError("invalidBase64 accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidBase64=REJECTED");
        }

        System.out.println("ALL_CHECKS_PASS");
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 SignatureBase64Demo.java
java SignatureBase64Demo
~~~

**Stdout chính xác** (đã biên dịch với `--release 17` và chạy kiểm tra trên JDK 24):

~~~text
utf8RoundTrip=PASS
bytesRoundTrip=PASS
signatureRoundTrip=PASS
signatureLength64=PASS
verifyOriginal=PASS
rejectChangedMessage=PASS
rejectChangedSignature=PASS
rejectWrongKey=PASS
basicBase64=PASS
invalidBase64=REJECTED
ALL_CHECKS_PASS
~~~

Các kiểm tra có tác dụng:

1. `utf8RoundTrip` kiểm tra dấu tiếng Việt được phục hồi đúng khi mã hóa/giải mã payload bằng UTF-8.
2. `bytesRoundTrip` xác minh toàn bộ **byte[] thông điệp** được chuyển qua Base64URL không mất byte nào.
3. `signatureRoundTrip` xác minh **byte[] chữ ký** sau giải mã trùng tuyệt đối với chữ ký gốc.
4. `signatureLength64` khẳng định kích thước chữ ký Ed25519 trong ví dụ là **64 byte**.
5. `verifyOriginal` chỉ cho phép kết quả hợp lệ khi ký đúng message và dùng public key cùng key pair.
6. `rejectChangedMessage` thay dữ liệu `42` bằng `43` nhưng giữ chữ ký; phép xác minh phải từ chối.
7. `rejectChangedSignature` sửa một bit của chữ ký; hàm xác minh từ chối nếu `verify` trả `false` **hoặc** ném `SignatureException` do cấu trúc chữ ký sai.
8. `rejectWrongKey` chứng minh một public key không tương ứng với signer không xác minh được chữ ký.
9. `basicBase64` kiểm tra cả biến thể Base64 thông thường cũng khôi phục bytes chính xác khi dùng đúng cặp encoder/decoder.
10. `invalidBase64` chứng minh decoder từ chối chuỗi chứa ký tự `*` không hợp lệ trong bảng mã Base64URL.

Hàm `check` ném `AssertionError` nếu một điều kiện không đúng, nên chương trình không chỉ in một dãy boolean rồi bỏ qua các lỗi. Nó cũng không phụ thuộc cờ `-ea` như từ khóa `assert`.

**Đừng gửi private key qua mạng.** Ở ứng dụng thật, bên ký giữ private key trong hạ tầng quản lý khóa (ví dụ `KeyStore` hoặc dịch vụ quản lý khóa thích hợp), còn bên xác minh lấy public key đã được xác thực thông qua cơ chế phân phối khóa đáng tin cậy.

## 6. Thiết kế payload gửi qua JSON/HTTP

Một giao thức truyền có thể dùng cấu trúc JSON dạng minh họa sau:

~~~json
{
  "algorithm": "Ed25519",
  "keyId": "signing-key-2026",
  "payloadBase64Url": "<chuỗi Base64URL của byte[] thông điệp>",
  "signatureBase64Url": "<chuỗi Base64URL của byte[] chữ ký>"
}
~~~

Đây là **mô hình envelope**, không phải giá trị JSON hợp lệ sẵn có để chạy xác minh. Những đoạn trong dấu `<...>` là vị trí thay dữ liệu thật theo giao thức. Trên receiver:

1. Giới hạn kích thước request/payload trước khi giải mã; không phân bổ bộ nhớ không giới hạn cho chuỗi Base64 không tin cậy.
2. Đọc đúng hai trường `payloadBase64Url` và `signatureBase64Url` theo định dạng đã thống nhất.
3. Kiểm tra thuật toán qua **allowlist cấu hình phía verifier**; không chọn thuật toán yếu hoặc không mong muốn chỉ vì input đề nghị.
4. Dùng `Base64.getUrlDecoder()` cho từng trường để phục hồi **byte[]`.
5. Ánh xạ `keyId` tới một **public key đã được tin cậy trước**. `keyId` chỉ là mã định danh gợi ý lựa chọn khóa, không tự chứng minh khóa ấy đáng tin.
6. Dùng `Signature.getInstance("Ed25519")`, `initVerify(trustedPublicKey)`, `update(payloadBytes)` và `verify(signatureBytes)`.
7. **Chỉ sau xác minh thành công** mới xử lý payload theo chính sách tin cậy của ứng dụng. Nếu thông điệp cần chống phát lại, kiểm tra thêm nonce, timestamp, expiry hoặc message ID theo giao thức.

**Cần xác định chính xác những gì được ký.** Trong chương trình `SignatureBase64Demo`, chữ ký chỉ bao phủ `data` (byte[] thông điệp), không tự bao phủ trường `keyId` hay metadata bên ngoài. Nếu giao thức cần xác thực `timestamp`, `keyId`, đối tượng nhận, phiên bản giao thức hoặc thông tin khác, hãy đưa chúng vào **dữ liệu được ký** theo một cách đóng gói/canonicalization rõ ràng, thay vì nghĩ rằng chỉ đặt cạnh chữ ký trong JSON là chúng đã được bảo vệ.

Trong giao thức có cấu trúc, nên dùng định dạng xác định byte để ký (ví dụ một **canonical byte representation** được tài liệu giao thức quy định). Không ký một biểu diễn rồi cố xác minh một JSON được serialize lại theo thứ tự trường, độ trắng hoặc quy tắc Unicode khác.

## 7. Các lỗi phổ biến và chẩn đoán

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| `Signature.verify` trả `false` dù “nội dung nhìn như nhau” | Byte payload khác do UTF-8/encoding, NFC/NFD, xuống dòng, khoảng trắng, thứ tự JSON hoặc bytes sau khi xử lý lại | Kiểm tra hex/byte length hoặc hash của byte[] thực tế ở hai phía; quy định canonical representation. |
| Chữ ký sau truyền không còn trùng byte[] gốc | Dùng `new String(signatureBytes, UTF_8)` rồi `getBytes(UTF_8)` | Encode bằng Base64, decode ngược đúng biến thể. |
| Base64 decoder ném `IllegalArgumentException` | Chuỗi không đúng bảng chữ cái, padding hoặc cấu trúc hợp lệ | Dùng `getDecoder` hay `getUrlDecoder` đúng giao thức, kiểm tra input và không tự bỏ ký tự. |
| Xác minh chữ ký bị `SignatureException` | Chữ ký sai encoding/loại hoặc provider không xử lý được; Ed25519 có thể gặp điểm mã hóa không hợp lệ | Từ chối chữ ký; phân biệt với `false` (chữ ký có định dạng hợp lệ nhưng không khớp). |
| Xác minh thất bại với public key khác | Không cùng cặp khóa ký/xác minh, hoặc khóa đã xoay/nhận sai `keyId` | Phân phối khóa công khai đã xác thực, quản lý phiên bản/rotation. |
| Bên ký dùng Ed25519, bên nhận chọn thuật toán khác | Mismatch thuật toán/kiểu khóa | Thống nhất thuật toán và khóa phù hợp; đặt allowlist, không tự đoán bằng input không tin cậy. |
| Base64 chạy được nhưng dấu tiếng Việt mất | Payload bytes đã bị chuyển mã sai trước/sau Base64 | Quy định `StandardCharsets.UTF_8` và thử vòng truyền, giữ byte[] nguyên bản khi xác minh. |
| Dữ liệu đã ký hợp lệ nhưng bị phát lại | Chữ ký chứng thực bytes chứ không tự chứng thực tính mới của yêu cầu | Thêm nonce, timestamp, expiry, ID và kiểm soát replay theo nghiệp vụ. |
| Cho rằng Base64 làm dữ liệu không đọc được | Base64 chỉ là biểu diễn text | Dùng HTTPS/TLS hoặc mã hóa phù hợp nếu cần bí mật nội dung. |

### Phân biệt mã hóa, hàm băm, MAC và chữ ký số

- **Base64:** biểu diễn `byte[]` thành ký tự; không có khóa, không chứng minh tính toàn vẹn.
- **Hash:** tạo dấu vân tay dữ liệu; bản thân hash công khai **không xác thực ai đã gửi**.
- **HMAC/MAC:** xác thực bằng khóa bí mật chung; phù hợp khi hai bên chia sẻ khóa và dùng `javax.crypto.Mac` theo giao thức.
- **Digital signature:** bên ký dùng **private key**, bên xác minh dùng **public key** đáng tin cậy. Trong Java dùng `java.security.Signature`.

Không dùng `Base64` thay thế chữ ký số; cũng không so sánh trực tiếp hai chuỗi Base64 khác biến thể để kết luận chữ ký có giống nhau hay không nếu điều cần so sánh là bytes nhị phân.

## 8. Checklist kiểm thử hồi quy trước khi tích hợp

1. **Round-trip:** Base64 encode/decode cho payload và chữ ký phải tái lập đúng `byte[]` nguồn; dùng `Arrays.equals`.
2. **UTF-8:** nội dung có dấu tiếng Việt/emoji phải trở về cùng văn bản khi ý định là chuyển đổi `String` ⇄ UTF-8.
3. **Đúng khóa:** chữ ký hợp lệ xác minh bằng public key cùng cặp phải thành công.
4. **Sai thông điệp:** chỉ đổi một byte payload nhưng giữ chữ ký phải bị từ chối.
5. **Sai chữ ký:** sửa byte chữ ký phải bị từ chối; kiểm thử chấp nhận cả đường trả `false` hoặc `SignatureException` do chữ ký không hợp lệ.
6. **Sai public key:** chữ ký không xác minh được bằng khóa không liên quan.
7. **Sai Base64:** chuỗi có ký tự không hợp lệ bị từ chối trước khi tiến hành xác minh.
8. **Khác encoder:** kiểm tra đúng Basic hoặc URL-safe theo giao thức; không dựa vào việc hai biến thể tình cờ cùng giải mã được một chuỗi cụ thể.
9. **Không log vật liệu bí mật:** không in private key; hạn chế ghi dữ liệu nhạy cảm/chữ ký vào log theo chính sách bảo mật.
10. **Các giới hạn giao thức:** xác thực thuật toán, khóa, kích thước payload, phiên bản, thời hạn hiệu lực và chống phát lại nếu cần.

## 9. Tài liệu chính thức còn hiệu lực

- [Java SE 26 — java.security.Signature](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): `initSign`, `update`, `sign` trả byte[], `initVerify`, `verify` và `SignatureException`.
- [Java SE 26 — java.util.Base64](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html): Basic, URL-safe và MIME encoder/decoder.
- [Java SE 26 — Base64.Encoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.Encoder.html): `encodeToString` và `withoutPadding`.
- [Java SE 26 — Base64.Decoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.Decoder.html): `decode`, padding và `IllegalArgumentException`.
- [Java SE 26 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên thuật toán `Ed25519` của `KeyPairGenerator` và `Signature`.
- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): hỗ trợ EdDSA/Ed25519 chính thức từ Java 15.
- [RFC 4648 — Base64 and Base64URL](https://www.rfc-editor.org/rfc/rfc4648): bảng chữ cái và quy tắc biểu diễn Base64.

**Kết luận:** ký **đúng mảng byte** bằng private key, chuyển **byte[] chữ ký** thành text bằng **Base64 đúng biến thể**, rồi giải mã lại thành **byte[] nguyên vẹn** trước khi `Signature.verify` bằng **public key đáng tin cậy**. Base64 là lớp biểu diễn cho vận chuyển, còn chữ ký số mới là cơ chế xác thực nội dung.