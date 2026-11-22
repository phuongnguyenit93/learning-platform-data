# 2.7 Vòng đời khởi tạo, cập nhật, kết thúc và tái sử dụng đối tượng mật mã

## 1. Vì sao phải hiểu vòng đời?

Trong Java Cryptography Architecture (JCA) và Java Cryptography Extension (JCE), các lớp như `MessageDigest`, `Mac`, `Signature`, `Cipher` và `KeyAgreement` là những **engine object**: ứng dụng gọi API thống nhất, còn cryptographic provider thực hiện thuật toán. Mỗi đối tượng thường giữ **trạng thái có thể thay đổi**: thuật toán/provider, khóa, chế độ, tham số (IV/nonce, padding…), dữ liệu đã đưa vào và bộ đệm nội bộ.

Một lời gọi `getInstance(...)` chỉ chọn yêu cầu về thuật toán/implementation; **không có nghĩa** mọi engine đã sẵn sàng xử lý dữ liệu. Một lời gọi `update(...)` có thể chỉ nạp thêm dữ liệu, chưa tạo ra kết quả hoàn chỉnh. Một lời gọi kết thúc như `digest()`, `doFinal()`, `sign()` hoặc `verify()` hoàn tất **một thao tác mật mã**, nhưng không đồng nghĩa đóng hay hủy đối tượng. Quy tắc đặt lại trạng thái khác nhau theo lớp, thuật toán và trường hợp lỗi.

Sau bài này, cần phân biệt được: (1) tạo engine với khởi tạo khóa/chế độ; (2) `update` với `final`; (3) reset với re-init; (4) tái sử dụng về mặt API với tái sử dụng **an toàn về mật mã**, đặc biệt là AES-GCM.

## 2. Mô hình vòng đời chung

```text
getInstance(algorithm)
        |
        v
[Đối tượng engine được tạo]
        |
        | init(key/mode/parameters) khi API yêu cầu
        v
[Đã khởi tạo cho một loại thao tác]
        |
        | update(data), có thể gọi 0..n lần
        | updateAAD(aad) trước dữ liệu đối với AEAD
        v
[Đang tích lũy/xử lý một thông điệp]
        |
        | digest / doFinal / sign / verify / generateSecret
        v
[Kết thúc thông điệp, nhận kết quả hoặc lỗi]
        |
        +--> engine reset theo hợp đồng API, có thể dùng tiếp
        |
        +--> phải init lại / tạo instance mới cho khóa, IV, mode, phiên mới
        |
        +--> lỗi: không giả định trạng thái còn dùng được; khởi tạo lại
```

Đây là **mô hình khái quát**, không phải một sơ đồ trạng thái chung được Java bảo đảm cho mọi engine. Cụ thể:

- **Tạo:** `MessageDigest.getInstance("SHA-256")` trả về đối tượng ở trạng thái đã khởi tạo. Ngược lại, `Mac` cần `init(key)`; `Signature` cần `initSign(privateKey)` hoặc `initVerify(publicKey)`; `Cipher` cần `init(opmode, key, parameters)`.
- **Khởi tạo:** khóa, hướng thao tác, thuật toán và tham số phải tương thích. `Cipher.ENCRYPT_MODE` khác `Cipher.DECRYPT_MODE`; `Signature` ở chế độ ký khác chế độ xác minh.
- **Cập nhật:** nhiều `update` theo thứ tự tương đương xử lý phép nối các khối dữ liệu *trong cùng một thao tác*, với điều kiện dữ liệu và tham số giống nhau. Dữ liệu đã nạp trước đó vẫn ảnh hưởng tới kết quả đến khi kết thúc/reset.
- **Kết thúc:** phương thức cuối có thể xử lý khối còn đệm, padding, MAC/tag hoặc kiểm tra chữ ký. Vì vậy không được chỉ gọi `update` rồi xem kết quả là đã hoàn tất.
- **Bắt đầu thông điệp mới:** tuân thủ hợp đồng reset của từng API và yêu cầu an toàn về key/nonce. `reset()` không phải là phương thức phổ quát của mọi lớp; `init(...)` lại thiết lập ngữ cảnh mới.
- **Hủy:** các engine này thường không có giao thức `close()` chung như stream. Đối tượng hết tham chiếu không có nghĩa khóa bí mật đã được xóa ngay khỏi bộ nhớ.

## 3. Bảng hành vi theo engine

| Engine | Trước khi nạp dữ liệu | Nạp dữ liệu / pha trung gian | Hoàn tất | Trạng thái sau khi hoàn tất thành công |
| --- | --- | --- | --- | --- |
| `MessageDigest` | `getInstance("SHA-256")` là đủ | `update(...)` | `digest()` hoặc `digest(bytes)` | Tự reset về trạng thái digest rỗng; `reset()` có thể bỏ phần đang tích lũy |
| `Mac` | `getInstance("HmacSHA256")` rồi `init(secretKey)` | `update(...)` | `doFinal()` hoặc `doFinal(bytes)` | Reset về trạng thái ngay sau lần `init` gần nhất, giữ khóa; `reset()` cũng làm vậy |
| `Signature` | `initSign(privateKey)` hoặc `initVerify(publicKey)` | `update(...)` | `sign()` hoặc `verify(signature)` | Reset về chế độ ký/xác minh đã khởi tạo và khóa tương ứng |
| `Cipher` | `init(ENCRYPT_MODE/DECRYPT_MODE, key, params)` | `update(...)`; AEAD: `updateAAD(...)` trước dữ liệu | `doFinal(...)` | API mô tả reset về trạng thái sau `init` khi thành công; **vẫn cần IV mới cho mỗi lần mã hóa GCM cùng khóa** |
| `KeyAgreement` | `init(privateKey)` | `doPhase(peerPublicKey, lastPhase)`, có thể nhiều pha theo thuật toán | `generateSecret()` | Reset về trạng thái sau `init`; phiên mới cần các pha mới, và thường nên dùng khóa phiên mới tùy giao thức |
| `SecureRandom` | Tạo/getInstance, seed nội bộ theo provider | `nextBytes(...)`/`generateSeed(...)` | Không có thao tác final cho mỗi thông điệp | Có thể lấy nhiều lần; không có mô hình `update/doFinal` |
| `KeyGenerator` / `KeyPairGenerator` | Chọn thuật toán, nên `init` kích thước/tham số và `SecureRandom` thích hợp | Không có luồng `update` dữ liệu thông điệp | `generateKey()` / `generateKeyPair()` | Có thể tiếp tục sinh khóa; mỗi lần sinh ra vật liệu khóa mới |

**Không suy luận từ tên phương thức rằng mọi lớp đều có quy tắc reset giống nhau.** Ví dụ `Mac.reset()` giữ khóa HMAC hiện tại, còn `Cipher` không có `reset()` công khai tương ứng để tự đổi IV. Cũng không nên dùng `getInstance` để kiểm tra sự sẵn sàng của khóa hay trạng thái runtime.

## 4. Tích lũy dữ liệu: `update` và thao tác kết thúc

Giả sử dữ liệu UTF-8 của thông điệp là `"Hello JCA"` và được chia thành `"Hello "` và `"JCA"`:

```text
update("Hello ") + digest("JCA")
       cùng thông điệp
digest("Hello JCA") sau khi engine đã reset
       tạo ra cùng giá trị SHA-256
```

`MessageDigest.digest(byte[])` **vừa cập nhật dữ liệu cuối vừa kết thúc**. Tương tự, `Mac.doFinal(byte[])` tiêu thụ thêm dữ liệu cuối. Đừng vô tình gọi `update(fullMessage)` rồi `doFinal(fullMessage)`: khi đó thông điệp được xử lý hai lần. Một lệnh `doFinal()` không có dữ liệu mới kết thúc toàn bộ dữ liệu từ các `update` trước đó.

Đối với `Cipher`, `update` có thể trả về `null` hoặc 0 byte vì provider đang giữ dữ liệu để hoàn thành khối/padding/tag. `doFinal` mới đưa ra phần cuối; mã hóa và giải mã phải ghép các phần theo đúng thứ tự. Với `Cipher.getOutputSize(inputLength)`, tham số là **số byte đầu vào còn dự kiến xử lý ở thời điểm đó**, và kết quả là dung lượng đầu ra ước tính cần cho `update/doFinal`; khi dùng overload ghi vào buffer phải kiểm tra vị trí, độ dài và `ShortBufferException`.

`Signature` không trả chữ ký tại `update`: phương thức này chỉ tích lũy thông điệp cần ký hoặc xác minh. `sign` cần khóa riêng, `verify` cần khóa công khai và trả `boolean` (hoặc ném `SignatureException` khi chữ ký/định dạng/trạng thái không hợp lệ). Không đổi chiều ký/xác minh khi chưa gọi phương thức `initSign`/`initVerify` tương ứng.

### Ví dụ 1 — Hash và HMAC dùng lại đúng cách

Lưu thành **`DigestMacLifecycleDemo.java`**; chạy bằng Java 17+.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class DigestMacLifecycleDemo {
    public static void main(String[] args) throws Exception {
        byte[] a = "Hello ".getBytes(StandardCharsets.UTF_8);
        byte[] b = "JCA".getBytes(StandardCharsets.UTF_8);
        byte[] whole = "Hello JCA".getBytes(StandardCharsets.UTF_8);

        MessageDigest md = MessageDigest.getInstance("SHA-256");
        md.update(a);
        byte[] digest1 = md.digest(b);
        byte[] digest2 = md.digest(whole);
        System.out.println("digestReset=" + Arrays.equals(digest1, digest2));
        System.out.println("sha256Bytes=" + digest1.length);

        byte[] keyBytes = "demo-key-for-hmac".getBytes(StandardCharsets.UTF_8);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(keyBytes, "HmacSHA256"));
        mac.update(a);
        byte[] tag1 = mac.doFinal(b);
        byte[] tag2 = mac.doFinal(whole);
        System.out.println("macReset=" + Arrays.equals(tag1, tag2));
        System.out.println("hmacBytes=" + tag1.length);
    }
}
```

```bash
javac -encoding UTF-8 DigestMacLifecycleDemo.java
java DigestMacLifecycleDemo
```

```text
digestReset=true
sha256Bytes=32
macReset=true
hmacBytes=32
```

Sau `digest(b)`, `MessageDigest` trở lại trạng thái rỗng, nên `digest(whole)` không bị ghép nhầm vào thông điệp trước. Sau `mac.doFinal(b)`, `Mac` trở lại trạng thái đã nạp cùng khóa. `reset()` của `Mac` cũng bỏ dữ liệu tích lũy nhưng **không đổi khóa**; muốn đổi khóa thì `init(newKey)`.

Khóa HMAC viết trực tiếp bằng chuỗi ở đây chỉ phục vụ quan sát vòng đời. Trong hệ thống thật, hãy tạo/lưu khóa có entropy phù hợp, ví dụ dùng `KeyGenerator` hoặc dịch vụ quản lý khóa. SHA-256 là hàm băm **không có khóa**; HMAC-SHA256 kiểm tra tính toàn vẹn/xác thực khi hai phía chia sẻ bí mật. Không dùng riêng hash để thay thế MAC.

## 5. `Cipher` và điểm dễ sai nhất: AES-GCM

`Cipher.getInstance("AES/GCM/NoPadding")` chỉ tạo engine với transformation (thuật toán/chế độ/padding). Để mã hóa, cần `init(ENCRYPT_MODE, key, GCMParameterSpec)`; giải mã cần `init(DECRYPT_MODE, key, GCMParameterSpec)`. Trong `GCMParameterSpec(tagBits, iv)`, `tagBits=128` là độ dài authentication tag theo **bit**, còn `iv` thường dài **12 byte (96 bit)**.

Một phiên mã hóa GCM diễn ra theo thứ tự:

1. Chọn **IV/nonce không lặp với cùng khóa**; có thể tạo IV 12 byte ngẫu nhiên bằng `SecureRandom` nếu quản lý rủi ro trùng nonce phù hợp.
2. `cipher.init(ENCRYPT_MODE, key, new GCMParameterSpec(128, iv))`.
3. Nếu có **AAD** (metadata cần xác thực nhưng không mã hóa), gọi `updateAAD(aad)` **trước** `update/doFinal` xử lý plaintext.
4. Gọi `update` 0..n lần, rồi `doFinal` đúng một lần cho thông điệp đó; kết quả chứa ciphertext và authentication tag (với cách trả mảng byte của Java GCM).
5. Lưu/truyền IV cùng ciphertext+tag và quy ước AAD cho phía giải mã. IV không bắt buộc giữ bí mật, nhưng phải duy nhất trong phạm vi khóa.
6. Với **thông điệp mã hóa tiếp theo dưới cùng khóa, phải init lại bằng IV mới**. Không lấy việc `doFinal` reset nội bộ làm lý do tái dùng key+IV; tái dùng cặp này có thể phá vỡ bảo mật và cho phép giả mạo.

Phía giải mã phải dùng **cùng khóa, IV, AAD** và xử lý ciphertext+tag. `AEADBadTagException` ở `doFinal` nghĩa là xác thực thất bại (có thể do sửa dữ liệu, sai khóa/IV/AAD hoặc dữ liệu bị hỏng). **Loại bỏ toàn bộ plaintext của lần giải mã lỗi**; không xuất hay sử dụng plaintext từng phần trước khi tag được xác nhận.

### Ví dụ 2 — Update, doFinal, GCM tag và re-init khi giải mã

Lưu thành **`AesGcmLifecycleDemo.java`**; chạy bằng Java 17+.

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmLifecycleDemo {
    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        byte[] aad = "doc:123".getBytes(StandardCharsets.UTF_8);
        byte[] plain = "Hello authenticated world!".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        encrypt.updateAAD(aad);
        int middle = plain.length / 2;
        byte[] first = encrypt.update(plain, 0, middle);
        byte[] last = encrypt.doFinal(plain, middle, plain.length - middle);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        if (first != null) {
            buffer.writeBytes(first);
        }
        buffer.writeBytes(last);
        byte[] ciphertextAndTag = buffer.toByteArray();

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        decrypt.updateAAD(aad);
        byte[] recovered = decrypt.doFinal(ciphertextAndTag);
        System.out.println("roundTrip=" + Arrays.equals(plain, recovered));

        byte[] tampered = ciphertextAndTag.clone();
        tampered[tampered.length - 1] ^= 1;
        decrypt.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        decrypt.updateAAD(aad);
        try {
            decrypt.doFinal(tampered);
            System.out.println("tamperRejected=false");
        } catch (AEADBadTagException expected) {
            System.out.println("tamperRejected=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 AesGcmLifecycleDemo.java
java AesGcmLifecycleDemo
```

```text
roundTrip=true
tamperRejected=true
```

`encrypt.update(...)` có thể đưa ra phần ciphertext đầu hoặc chưa trả byte nào; ví dụ xử lý cả `null` rồi ghép cùng `doFinal`. Với cùng khóa và IV, GCM tính tag để phía nhận kiểm tra cả ciphertext lẫn AAD. Chương trình chủ động gọi lại `decrypt.init(...)` trước lần giải mã kiểm tra bị sửa, nhằm bắt đầu thao tác rõ ràng. **Không tái sử dụng IV của ví dụ này cho lần mã hóa khác với cùng `key`**; lần mã hóa tiếp theo phải lấy IV mới và `encrypt.init(...)` lại. Việc mã hóa tạo ciphertext khác nhau mỗi lần nên ví dụ chỉ in ra kết quả kiểm tra ổn định, không in ciphertext.

Trong sản phẩm, nên đóng gói mỗi bản ghi thành các trường có phiên bản/algorithm, IV, ciphertext+tag, cùng quy tắc AAD thống nhất. Kiểm tra độ dài dữ liệu và giới hạn bộ đệm trước khi cấp phát; không đưa dữ liệu chưa xác thực vào parser, database hoặc luồng phản hồi.

## 6. `Signature`: một đối tượng, hai chế độ có chủ đích

Một `Signature` hoạt động theo một trong hai luồng riêng:

- **Ký:** `getInstance(algorithm) → initSign(privateKey) → update(message) → sign()`. Sau `sign` thành công, trạng thái quay về như sau `initSign`; có thể `update`/`sign` thông điệp mới với cùng khóa.
- **Xác minh:** `getInstance(algorithm) → initVerify(publicKey) → update(message) → verify(signatureBytes)`. Sau `verify`, trạng thái quay về như sau `initVerify`. Kết quả `false` nghĩa là chữ ký không khớp; byte chữ ký sai định dạng hoặc lỗi provider có thể gây `SignatureException`.
- Chuyển từ ký sang xác minh, đổi người ký hoặc đổi khóa: phải gọi `initVerify`/`initSign` thích hợp, không chỉ `update`. Thuật toán tạo chữ ký và xác minh phải tương thích, bao gồm cả tham số thuật toán nếu có (ví dụ RSA-PSS).

### Ví dụ 3 — Ký, xác minh rồi tái sử dụng

Lưu thành **`SignatureLifecycleDemo.java`**; chạy bằng Java 17+.

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class SignatureLifecycleDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();
        byte[] a = "record:".getBytes(StandardCharsets.UTF_8);
        byte[] b = "42".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(a);
        signer.update(b);
        byte[] signature1 = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(a);
        verifier.update(b);
        System.out.println("firstValid=" + verifier.verify(signature1));

        signer.update(a);
        signer.update(b);
        byte[] signature2 = signer.sign();
        verifier.update(a);
        verifier.update(b);
        System.out.println("reuseSignVerify=" + verifier.verify(signature2));

        verifier.update("record:".getBytes(StandardCharsets.UTF_8));
        verifier.update("43".getBytes(StandardCharsets.UTF_8));
        System.out.println("modifiedValid=" + verifier.verify(signature1));
    }
}
```

```bash
javac -encoding UTF-8 SignatureLifecycleDemo.java
java SignatureLifecycleDemo
```

```text
firstValid=true
reuseSignVerify=true
modifiedValid=false
```

Sau mỗi `sign()` và `verify(...)` thành công, cùng instance xử lý thông điệp mới được. Nếu quên gọi `update` cho thông điệp mới, API sẽ ký/kiểm tra **thông điệp rỗng**; nếu chỉ cập nhật một phần, nội dung đã ký không còn khớp nội dung mong muốn. Khóa RSA được sinh khi chương trình chạy nên bytes chữ ký không được in thành một giá trị cố định. `SHA256withRSA` ở đây là ví dụ vòng đời; lựa chọn thuật toán/chính sách ký trong sản phẩm phải đáp ứng yêu cầu bảo mật riêng.

## 7. Reset, re-init, clone và đối tượng mới: chọn đúng hành vi

| Nhu cầu | Cách xử lý đúng | Điều cần tránh |
| --- | --- | --- |
| Bỏ dữ liệu hash đang dở | `MessageDigest.reset()`; hoặc dùng `digest()` để hoàn tất rồi tự reset | Nghĩ rằng dữ liệu cũ vẫn được giữ sau `digest()` |
| HMAC thông điệp khác, **cùng key** | Sau `doFinal()`, `update`/`doFinal` thông điệp tiếp; hoặc `mac.reset()` trước khi bắt đầu | Gọi `reset()` rồi mặc định key đã thay |
| HMAC với **key khác** | `mac.init(newKey)` | Dùng cùng instance chỉ với `reset()` |
| Signature thông điệp khác, **cùng chế độ/key** | Sau `sign/verify`, gọi `update` thông điệp mới | Nhầm `verify(false)` thành chưa kết thúc và trộn dữ liệu |
| Đổi khóa/người ký/chế độ Signature | `initSign(...)` hoặc `initVerify(...)` | Dùng object đang ở chế độ đối lập |
| AES-GCM mã hóa thông điệp mới | IV/nonce duy nhất với key, rồi `cipher.init(ENCRYPT_MODE, key, new GCMParameterSpec(...))` | Gọi lại `doFinal` với cùng key+IV |
| Sau lỗi Cipher/Signature/KeyAgreement | Bỏ kết quả chưa xác thực; `init` lại hoặc tạo instance mới trước thao tác khác | Dựa vào trạng thái nội bộ chưa biết sau exception |
| Sao chép trạng thái một digest | `clone()` chỉ khi provider hỗ trợ `Cloneable` và có mục đích rõ | Giả định mọi provider hoặc engine đều clone được |

`reset` thường có nghĩa **loại bỏ trạng thái của thông điệp hiện tại**, chứ không xóa an toàn khóa khỏi bộ nhớ. `init` là ranh giới để thay đổi khóa, hướng hoặc tham số thao tác. Tạo **instance mới cho mỗi yêu cầu** thường dễ hiểu, dễ kiểm tra và tránh rò rỉ trạng thái hơn một pool instance tái sử dụng phức tạp; chi phí khởi tạo cần đo thực tế nếu muốn tối ưu.

`KeyAgreement` cũng có sự phân biệt này: `generateSecret()` kết thúc một chuỗi `doPhase` và reset về trạng thái đã `init`, nhưng **không tự tạo private key mới**. Giao thức yêu cầu ephemeral keys/forward secrecy cần quản lý vật liệu khóa phiên riêng, không suy luận an toàn từ reset API.

## 8. Sai thứ tự và xử lý lỗi

| Triệu chứng / exception | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalStateException` ở `Mac.update`, `Cipher.update/doFinal` hoặc `KeyAgreement.doPhase` | Chưa `init`; sai mode; engine không còn trạng thái hợp lệ | Xác định pha dự kiến, init đúng trước khi thao tác |
| `InvalidKeyException` / `InvalidAlgorithmParameterException` | Khóa, IV, tham số không tương thích thuật toán/mode | Kiểm tra loại khóa, kích thước, `AlgorithmParameterSpec`; không ghi log khóa |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | Transformation hoặc provider không hỗ trợ | Dùng tên thuật toán chuẩn và cấu hình provider rõ ràng |
| `ShortBufferException` | Mảng đầu ra không đủ chỗ ở overload có output buffer | Tính dung lượng bằng `getOutputSize` khi phù hợp, giữ đúng offset |
| `IllegalBlockSizeException` / `BadPaddingException` | Kích thước/padding sai, key sai hoặc ciphertext hỏng trong các mode tương ứng | Từ chối dữ liệu, không thử dùng plaintext nghi ngờ; xử lý lỗi thống nhất |
| `AEADBadTagException` | Tag GCM sai do ciphertext, AAD, IV hoặc khóa không khớp | Hủy kết quả, không xử lý plaintext; coi đây là lỗi xác thực |
| `SignatureException` hoặc `verify(...) == false` | Sai trạng thái/định dạng, hoặc chữ ký không hợp lệ | Phân biệt exception kỹ thuật với kết quả xác minh thất bại |

Một số **phản ví dụ** (minh họa sai, không phải chương trình độc lập):

```java
Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
// c.update(input); // SAI: chưa init khóa, mode, IV.

Mac m = Mac.getInstance("HmacSHA256");
// m.doFinal(message); // SAI: chưa init key.

// Sau khi AES-GCM mã hóa xong:
// c.doFinal(nextMessage); // SAI về bảo mật nếu tái sử dụng key+IV.
```

Sau exception, API có thể không bảo đảm bộ đệm/trạng thái còn đủ tin cậy; hãy loại bỏ thao tác hiện tại và **khởi tạo lại** trước khi thử lần khác. Đặc biệt, lỗi giải mã không nên trả ra thông báo chi tiết về padding, tag, khóa hay dữ liệu đầu vào cho client: thông báo khác nhau có thể trở thành kênh rò rỉ thông tin.

## 9. Thiết kế sử dụng trong ứng dụng thực

**Ranh giới thông điệp.** Mỗi request/file/chunk được xử lý như một thao tác rõ ràng: xác định algorithm + key + mode + IV/AAD → khởi tạo → truyền dữ liệu đúng thứ tự → final → kiểm tra kết quả. Chỉ công bố plaintext sau khi xác thực thành công nếu dùng AEAD. Với streaming file lớn, không được phát tán plaintext từ `update` giải mã GCM trước khi xác minh tag cuối.

**Ranh giới luồng.** Tránh cho nhiều thread cùng gọi `update/doFinal` trên một `Cipher`, `Mac`, `MessageDigest` hay `Signature` đang hoạt động. Các engine giữ trạng thái thông điệp; chia sẻ đồng thời có thể làm lẫn dữ liệu và sinh lỗi không tái hiện. Tạo object theo tác vụ/thread hoặc đồng bộ toàn bộ chuỗi thao tác nếu có lý do đặc biệt. Đừng chỉ đồng bộ riêng `doFinal`.

**Ranh giới khóa và nonce.** Khóa là bí mật: không log, không hardcode trong sản phẩm, không gửi kèm ciphertext. IV GCM có thể công khai nhưng cặp **key+IV không được lặp ở phía mã hóa**. Khi xoay khóa, đổi phiên, đổi người dùng hoặc đổi vai trò ký/xác minh, tạo ngữ cảnh engine thích hợp. Với HMAC kiểm tra giá trị nhận được, dùng so sánh byte phù hợp như `MessageDigest.isEqual(expected, received)` thay cho việc so từng byte rồi dừng ngay khi khác.

**Ranh giới provider.** `getInstance("...")` chọn implementation từ các provider có sẵn; hỗ trợ thuật toán, kiểm tra tham số, buffering và chi phí khởi tạo có thể khác nhau. Dựa vào hợp đồng public API, kiểm thử provider/JDK chạy thật và không suy luận rằng kết quả `update` luôn có độ dài cố định. Khi yêu cầu thuật toán/hardware provider cụ thể, xác định `getProvider()` và cấu hình rõ ràng.

**Ranh giới tài nguyên.** Không cần và không thể dựa vào `close()` chung để làm sạch mọi engine. Giới hạn vòng đời tham chiếu tới key và buffer nhạy cảm; xóa mảng byte có thể xóa khi không còn sử dụng bằng `Arrays.fill` là biện pháp bổ sung nhưng không bảo đảm xóa mọi bản sao bên trong JVM/provider. Không giữ đối tượng mật mã trong singleton dùng chung nếu chưa có thiết kế vòng đời chặt chẽ.

## 10. Tự kiểm tra hiểu bài

1. Sau `MessageDigest.digest()`, `digest(bytes)` tiếp theo có tính tiếp thông điệp trước không? **Không**; `digest` hoàn tất và reset state.
2. Sau `Mac.doFinal()`, muốn dùng HMAC key cũ cho thông điệp mới cần `init` lại không? **Không bắt buộc**; `Mac` đã reset về state sau `init`. Nếu đổi key, **cần** `init(newKey)`.
3. Sau `Cipher.doFinal()` với AES-GCM, có nên mã hóa thông điệp khác bằng key+IV cũ không? **Tuyệt đối không**. Hãy tạo IV mới và init lại.
4. `Cipher.update` trả `null` có đồng nghĩa không xử lý dữ liệu? **Không**; provider có thể đệm và trả kết quả ở lần sau hoặc `doFinal`.
5. Có được dùng plaintext nhận từ `update` giải mã GCM trước `doFinal` không? **Không**; tính xác thực chưa được xác nhận.
6. Sau `Signature.verify(signature)` trả `false`, thông điệp mới cần gì? **Nạp lại toàn bộ thông điệp mới** (và init lại nếu muốn đổi key/mode); trạng thái xác minh của message trước đã kết thúc.
7. Có thể gọi `update`/`doFinal` đồng thời từ nhiều request trên một engine không? **Không nên**; mỗi thông điệp cần một chuỗi thao tác tuần tự và state độc lập.

## Tài liệu API chính thức (Java SE 21)

- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html)
- [MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)
- [Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html)
- [Cipher và lưu ý về GCM/IV](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [KeyAgreement](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyAgreement.html)
