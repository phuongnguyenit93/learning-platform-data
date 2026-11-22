# 9.2 Chu trình `Signature.initSign`, `update`, `sign` và `initVerify`, `verify`

## Mục tiêu học tập

`java.security.Signature` là **engine API của Java Security Architecture (JCA)** để tạo và kiểm tra **chữ ký số**. Một đối tượng `Signature` vận hành theo chu trình có trạng thái: phải chọn thuật toán, khởi tạo đúng **khóa** và **chiều thao tác**, cung cấp đầy đủ các byte thông điệp, rồi gọi `sign()` hoặc `verify()`.

Kết thúc bài, bạn có thể:

- Phân biệt hai chu trình **ký bằng private key** và **xác minh bằng public key**.
- Hiểu từng lệnh `getInstance`, `initSign`, `initVerify`, `update`, `sign` và `verify`, thứ tự hợp lệ và việc **reset trạng thái** sau thao tác.
- Đưa một thông điệp vào `update()` theo **nhiều chunk** mà vẫn đảm bảo tất cả byte được ký và xác minh đúng thứ tự.
- Thiết lập tham số của thuật toán chữ ký như `RSASSA-PSS` rõ ràng và thực hành trên **Java 17+**.
- Phân biệt kết quả `verify() == false` với **exception**, và tránh các lỗi liên quan đến encoding, nhầm key, nội dung thiếu, provider hoặc xử lý dữ liệu chưa xác thực.

> **Phạm vi:** Bài này hướng dẫn API `Signature` và chu trình thao tác chữ ký trong Java. Chữ ký số **không mã hóa dữ liệu**: người khác vẫn đọc được thông điệp nếu ứng dụng không mã hóa riêng. Việc xác thực chữ ký với một public key chỉ trở thành xác thực *danh tính người ký* khi public key được gắn đáng tin với danh tính ấy.

## 1. Bức tranh tổng thể: ai ký, ai xác minh?

Giả sử Alice gửi thông điệp cho Bob:

```text
ALICE (người ký)                            BOB (người kiểm tra)
-----------------                          --------------------
Message M (bytes)                          Nhận Message M + Signature S
      |                                                |
Private key của Alice                         Public key của Alice đã xác thực
      |                                                |
Signature.initSign(private)                    Signature.initVerify(public)
      |                                                |
Signature.update(M)                            Signature.update(M)
      |                                                |
Signature.sign()  -> chữ ký S                   Signature.verify(S) -> true/false
      |                                                |
Gửi M và S -------------------------------------------->|
```

- `initSign(privateKey)` yêu cầu **private key** có quyền ký, phù hợp với thuật toán đã chọn.
- `initVerify(publicKey)` yêu cầu **public key** tương ứng với khóa mà người ký đã dùng; bên xác minh cần **tin cậy cách public key được cung cấp**.
- `update(...)` cung cấp **message bytes** theo đúng thứ tự. Hai bên phải tạo ra **cùng chuỗi byte**: thay nội dung, thứ tự chunk, encoding hoặc metadata đã ký làm thay đổi đối tượng được xác minh.
- `sign()` trả `byte[]` chứa chữ ký, **không** trả ciphertext của thông điệp.
- `verify(signatureBytes)` thường trả `true` hoặc `false` nếu chữ ký được phân tích hợp lệ; ngoại lệ có thể xảy ra nếu trạng thái hoặc định dạng chữ ký không hợp lệ.

Đối với một tài liệu thực tế, bạn thường gửi/lưu **(message, signature, key identifier, algorithm ID / parameters)** trong một định dạng có phiên bản. Không truyền private key cùng chữ ký.

## 2. Signature là một state machine có ba giai đoạn

Theo Java SE 17 API, đối tượng `Signature` có ba trạng thái khái niệm:

| Trạng thái | Được tạo khi nào? | Thao tác hợp lệ chính |
| --- | --- | --- |
| **UNINITIALIZED** | Vừa `Signature.getInstance(...)`, chưa chỉ định key/operation | `initSign(...)` hoặc `initVerify(...)`; chưa được `update`, `sign`, `verify`. |
| **SIGN** | Sau `initSign(privateKey)` | `update(...)` một hoặc nhiều lần rồi `sign()`. |
| **VERIFY** | Sau `initVerify(publicKey)` / `initVerify(certificate)` | `update(...)` một hoặc nhiều lần rồi `verify(signature)`. |

```text
                       Signature.getInstance("RSASSA-PSS")
                                      |
                                      v
                               UNINITIALIZED
                                 /         \
                 initSign(private)      initVerify(public)
                             |               |
                             v               v
                           SIGN             VERIFY
                             |               |
                       update(...)       update(...)
                             |               |
                             v               v
                          sign()          verify(S)
                             |               |
                      sinh byte[] S       true / false
                             |               |
             Reset về trạng thái SIGN    Reset về VERIFY
                 (cùng key đã init)        (cùng key đã init)
```

**Reset sau khi hoàn thành:** Đặc tả API cho biết `sign()` đưa object về trạng thái như sau `initSign` thành công trước đó, còn `verify()` đưa object về trạng thái như sau `initVerify` thành công trước đó. Vì thế có thể gọi `update()` và `sign()`/`verify()` cho **thông điệp mới** mà không khởi tạo lại cùng key, miễn provider/algorithm cho phép theo API contract. Ví dụ ở phần 6 sẽ kiểm chứng điều này.

**Reset không có nghĩa xóa key, không có nghĩa tự chuyển qua chiều còn lại.** Nếu cần đổi key, đổi từ ký sang xác minh, hoặc thay bộ tham số, phải thực hiện khởi tạo/cấu hình phù hợp. Trong server, cách dễ quản lý là **mỗi operation dùng một đối tượng riêng** và không chia sẻ mutable `Signature` giữa nhiều thread/request.

Không nên gọi `sign()` khi object đang ở `VERIFY`, hay `verify()` khi object đang ở `SIGN`. `SignatureException` thường báo trạng thái không phù hợp.

## 3. Pha ký: `getInstance` → `initSign` → `update` → `sign`

### 3.1 `Signature.getInstance(algorithm)` chọn scheme chữ ký

```java
// Minh họa đặt trong phương thức có xử lý GeneralSecurityException:
Signature signer = Signature.getInstance("SHA256withRSA");
```

- `getInstance` chọn **scheme chữ ký** qua JCA provider registry, **chưa ký hoặc xác minh**. `Signature` **không có thuật toán mặc định**; tên phải được chỉ rõ.
- `SHA256withRSA` là scheme chữ ký RSA với SHA-256 theo standard algorithm name (thường gắn với RSASSA-PKCS1-v1_5).
- `RSASSA-PSS` là scheme chữ ký RSA-PSS có tham số digest/MGF1/salt length; `Ed25519` là scheme EdDSA có thuật toán khác. Không thay qua lại tên chỉ vì đều dùng public/private keys.
- Java SE 17 **yêu cầu** các implementation có `SHA256withRSA` trong tập `Signature` tối thiểu; tên `RSASSA-PSS` hoặc `Ed25519` cần kiểm tra hỗ trợ JDK/provider đích theo yêu cầu triển khai.

Nếu cố định provider bằng `Signature.getInstance(name, "ProviderName")`, mã nguồn phụ thuộc vào provider đó được đăng ký và hỗ trợ scheme; chỉ định provider có chủ đích khi HSM/chính sách bắt buộc.

### 3.2 `initSign(privateKey)` chọn chiều ký và khóa

```java
signer.initSign(privateKey);
```

`privateKey` phải thuộc thuật toán/scheme phù hợp; khóa RSA private không tự động dùng được để ký Ed25519. `initSign` có overload `initSign(privateKey, secureRandom)` nếu scheme cần randomness do ứng dụng cung cấp. Hầu hết ứng dụng nên dùng nguồn ngẫu nhiên mật mã an toàn từ provider/JDK; không truyền `java.util.Random`.

**Không dùng public key để `initSign`.** Nếu khai báo nhầm khóa, code thường không biên dịch vì kiểu yêu cầu là `PrivateKey`; nếu khóa private sai loại/kích thước/quyền sử dụng, có thể nhận `InvalidKeyException`.

Khóa có thể được sinh bởi `KeyPairGenerator`, đọc từ keystore, KMS/HSM qua provider, hoặc được cung cấp theo cơ chế đáng tin. Trong ví dụ, tạo khóa RSA-2048 **mới trong bộ nhớ** để thao tác có thể chạy độc lập.

### 3.3 `update(...)` nạp byte thông điệp

```java
signer.update(headerBytes);
signer.update(payloadBytes, 0, payloadBytes.length);
byte[] signature = signer.sign();
```

Mỗi lần `update` đóng góp byte vào **cùng một thông điệp logic**, theo **thứ tự các lệnh gọi**. Về mặt nội dung ký, các lệnh trên tương đương một lần `update()` với `headerBytes || payloadBytes`.

Các overload:

| API | Ý nghĩa |
| --- | --- |
| `update(byte value)` | Cấp một byte. |
| `update(byte[] data)` | Cấp toàn bộ mảng. |
| `update(byte[] data, int off, int len)` | Cấp đúng `len` byte bắt đầu từ offset `off`; `len` là **số byte**, không phải chỉ số kết thúc. |
| `update(ByteBuffer data)` | Cấp các byte trong vùng `remaining()`, từ `position()` tới `limit()`; khi trả về, `position` đến `limit`. |

`update()` ở trạng thái chưa init sẽ ném `SignatureException`. Nó **không** trả chữ ký, không lấy message từ `String` tự động. Vì vậy phải chọn charset/encoding một cách tường minh, ví dụ `message.getBytes(StandardCharsets.UTF_8)`.

Với các scheme như `SHA256withRSA` hoặc RSA-PSS cấu hình SHA-256, engine thường thực hiện băm nội bộ. **Không tự băm message bằng `MessageDigest` rồi đưa digest thay message vào `Signature.update()`**, trừ khi giao thức/thuật toán được chọn yêu cầu đúng kiểu đó. Làm vậy thường dẫn đến ký trên **digest như một message mới**, gây sai phạm vi dữ liệu hoặc “double hashing”.

### 3.4 `sign()` kết thúc và trả chữ ký

```java
byte[] result = signer.sign();
```

- Kết quả là **chữ ký nhị phân**, có thể mã hóa Base64 khi cần vận chuyển qua JSON/text nhưng Base64 **không cung cấp bảo mật**.
- Độ dài/encoding phụ thuộc scheme và khóa. Với RSA modulus 2048 bit, chữ ký RSA-PSS dài **256 byte**, không phụ thuộc message ngắn/dài; nhiều scheme khác có định dạng/kích thước khác.
- Một số scheme có randomness (như PSS) nên **ký lại cùng message/key có thể tạo chữ ký khác**, dù cả hai xác minh đúng. Không dùng so sánh raw signature bytes như bằng chứng hai message tương đương.
- Sau khi `sign()`, engine trở về **SIGN initialized state**, dữ liệu vừa `update()` không tự trở thành message tiếp theo. Muốn ký message mới phải cấp lại byte của message đó.
- Gọi `sign()` mà không `update()` có thể ký **thông điệp rỗng**, không phải bản sao message trước đó. Đây là lỗi logic khó phát hiện nếu ứng dụng mong “dùng lại dữ liệu cũ”.

Overload `sign(outbuf, offset, len)` ghi vào một vùng của mảng output và trả số byte thực ghi; kiểm tra buffer size và phạm vi chính xác. Với đa số ví dụ, `byte[] sign()` rõ ràng hơn.

## 4. Pha xác minh: `getInstance` → `initVerify` → `update` → `verify`

```java
// Minh họa trong phương thức có xử lý GeneralSecurityException:
Signature verifier = Signature.getInstance("SHA256withRSA");
verifier.initVerify(trustedPublicKey);
verifier.update(receivedMessageBytes);
boolean valid = verifier.verify(receivedSignatureBytes);
```

### 4.1 `initVerify(publicKey)` khởi tạo bằng khóa công khai

Dùng **public key tương ứng người ký**, đã được xác thực qua hệ thống tin cậy của ứng dụng. Nếu bên gửi dùng `private_A`, bên nhận dùng `public_A`; `public_B` thuộc người khác sẽ không xác minh chữ ký A (với cặp khóa và scheme an toàn).

Có overload `initVerify(Certificate certificate)` đọc public key từ chứng chỉ. **Đừng hiểu rằng chỉ gọi `initVerify(certificate)` là đã xác thực chuỗi chứng chỉ, hostname, trạng thái thu hồi hoặc danh tính ứng dụng.** Việc xác minh độ tin cậy/path validation của X.509, subject identity và mục đích key usage phải được xử lý theo quy tắc của hệ thống; `Signature.verify` chỉ kiểm tra chữ ký dưới khóa cung cấp. `initVerify(certificate)` còn có thể từ chối khóa/chứng chỉ không phù hợp với mục đích ký.

### 4.2 `update` ở bên nhận cũng nạp *toàn bộ* message

`verifier.update(...)` phải có **chính xác chuỗi byte đã được ký**, dù bên ký và bên nhận chia chunk khác nhau:

```text
Bên ký:      update([A B]) ; update([C D E])    => A B C D E
Bên kiểm tra: update([A]) ; update([B C D E])    => A B C D E
                                              (tương đương)

Bên kiểm tra: update([C D E]) ; update([A B])    => C D E A B
                                              (khác message)
```

Không cần cùng kích thước chunk; **cần cùng thứ tự và cùng byte**. Đừng chỉ ký phần body rồi tin header chưa được ký: dữ liệu quan trọng như version, message type, algorithm/key ID, tenant, user, amount, recipient, expiry hoặc context phải được đưa vào dữ liệu ký với encoding không mơ hồ.

### 4.3 `verify(signature)` trả boolean, không trả dữ liệu

`verify()` kiểm tra chữ ký với message đã `update` và public key đã `initVerify`:

- **`true`:** chữ ký hợp lệ **đối với chính message bytes, scheme, params và public key đang sử dụng**.
- **`false`:** chữ ký đã phân tích được nhưng không khớp với message/key/params; phải từ chối.
- **`SignatureException`:** object chưa init đúng, chữ ký có format/loại không hợp lệ, hoặc provider không thể xử lý; cũng **phải từ chối**. Không nên giả định mọi input chữ ký sai đều trả `false`.
- **Sau `verify()`:** engine reset về trạng thái **VERIFY đã init**; lần tiếp theo muốn kiểm tra message mới thì `update()` lại message mới và `verify()` trên chữ ký mới.

`verify()` **không giải mã** dữ liệu và **không tự đánh giá danh tính người ký**. Nếu public key do request tự cung cấp thì attacker có thể tự tạo key pair, ký message và đưa public key của mình để `verify == true`. Hệ thống cần ràng buộc public key với identity/quyền sử dụng trước khi xem chữ ký là bằng chứng từ một chủ thể cụ thể.

## 5. Chu trình và lỗi trạng thái cần ghi nhớ

| Tình huống | Kết quả hoặc rủi ro | Cách dùng đúng |
| --- | --- | --- |
| `Signature.getInstance(...)` rồi `update(...)` ngay | Chưa init; thường `SignatureException` | Gọi `initSign(private)` hoặc `initVerify(public)` trước. |
| `initSign(private)` rồi `verify(signature)` | Sai chiều thao tác | Gọi `sign()` ở chiều SIGN; hoặc `initVerify(public)` rồi nạp message và `verify()`. |
| `initVerify(public)` rồi `sign()` | Sai chiều thao tác | Dùng chiều VERIFY. |
| `initSign(private)` → `update(A)` → `sign()` → `update(B)` → `sign()` | Hai chữ ký cho **A** và **B**; message không cộng dồn qua lần `sign` | Đây là reset được tài liệu hóa; có thể `initSign` lại để tách operations rõ hơn. |
| `initVerify(public)` → `update(A)` → `verify(SA)` → `update(B)` → `verify(SB)` | Hai lượt verify liên tiếp; object reset về VERIFY sau mỗi lượt | Dùng object riêng cho mỗi request nếu có concurrency. |
| Bên ký update `A\|\|B`, bên nhận update `B\|\|A` | Chữ ký không hợp lệ vì byte khác | Chuẩn hóa layout, thứ tự, encoding. |
| Bên nhận chỉ update body, bỏ header đã được ký | Verify sai; hoặc thiếu kiểm tra tính xác thực metadata nếu header vốn không được ký | Ký/xác minh **đủ byte của envelope đã định nghĩa**. |
| Thay đổi params PSS giữa ký và verify | Có thể verify thất bại hoặc lỗi tham số | Quy định digest, MGF1, salt length và trailer field giống nhau. |
| Dùng thuật toán ký không phù hợp public/private key | `InvalidKeyException` hoặc lỗi provider | Kiểm tra key algorithm, purpose, provider và scheme. |
| Chia sẻ cùng instance `Signature` giữa các request/thread | Mutable state trộn bytes và khóa | Tạo object riêng theo operation; không cho nhiều thread `update` đồng thời. |

## 6. Ví dụ Java 17+ hoàn chỉnh: RSA-PSS, nhiều `update` và tái sử dụng đúng chu trình

Chương trình **`SignatureLifecycleDemo.java`** dưới đây:

1. Sinh key pair RSA-2048; tạo engine `RSASSA-PSS` với tham số **SHA-256**, **MGF1(SHA-256)**, **salt dài 32 byte** và **trailer 1**.
2. Ký `header || body` bằng hai lần `update`.
3. Dùng public key cùng cặp và cùng parameters để `verify()`.
4. Thử đổi body và đảo thứ tự chunk: đều không còn hợp lệ.
5. Ký/xác minh thông điệp thứ hai trên cùng objects sau khi phương thức đầu đã reset state.
6. Kiểm tra `update` khi object chưa init bị từ chối.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public final class SignatureLifecycleDemo {
    private static final PSSParameterSpec PSS =
            new PSSParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    32, 1);

    private static Signature createPss() throws GeneralSecurityException {
        Signature engine = Signature.getInstance("RSASSA-PSS");
        engine.setParameter(PSS);
        return engine;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] header = "order=42;".getBytes(StandardCharsets.UTF_8);
        byte[] body = "amount=100".getBytes(StandardCharsets.UTF_8);

        Signature signer = createPss();
        signer.initSign(pair.getPrivate());
        signer.update(header);
        signer.update(body);
        byte[] signature = signer.sign();

        Signature verifier = createPss();
        verifier.initVerify(pair.getPublic());
        verifier.update(header);
        verifier.update(body);
        System.out.println("First verification: " + verifier.verify(signature));

        verifier.update(header);
        verifier.update("amount=101".getBytes(StandardCharsets.UTF_8));
        System.out.println("Modified content accepted: " + verifier.verify(signature));

        verifier.update(body);
        verifier.update(header);
        System.out.println("Reordered chunks accepted: " + verifier.verify(signature));

        byte[] secondMessage = "second document".getBytes(StandardCharsets.UTF_8);
        signer.update(secondMessage);
        byte[] secondSignature = signer.sign();
        verifier.update(secondMessage);
        System.out.println("Second verification: " + verifier.verify(secondSignature));

        System.out.println("Signature bytes: " + signature.length);

        Signature uninitialized = createPss();
        boolean rejected = false;
        try {
            uninitialized.update(header);
        } catch (SignatureException expected) {
            rejected = true;
        }
        System.out.println("Uninitialized update rejected: " + rejected);
    }
}
```

Biên dịch và chạy với JDK 17+ có provider hỗ trợ **RSA-PSS**:

```bash
javac --release 17 SignatureLifecycleDemo.java
java SignatureLifecycleDemo
```

Kết quả kỳ vọng khi chạy chương trình (chữ ký nhị phân bên trong là ngẫu nhiên nhưng stdout sau ổn định):

```text
First verification: true
Modified content accepted: false
Reordered chunks accepted: false
Second verification: true
Signature bytes: 256
Uninitialized update rejected: true
```

**Giải thích kết quả:**

- Hai lần `signer.update(header)` và `signer.update(body)` tạo message đúng bằng hai mảng byte nối theo thứ tự đó. `verifier.update` cấp cùng dữ liệu nên dòng đầu `true`.
- `amount=101` khác `amount=100`, dù chỉ khác một byte; chữ ký cũ không khớp nên dòng thứ hai `false`.
- Đảo thứ tự hai mảng byte làm thay message thành `body || header`; chữ ký cũ không hợp lệ.
- `signer.sign()` **reset về trạng thái SIGN** và `verifier.verify()` **reset về VERIFY**, vì vậy ở thông điệp thứ hai có thể gọi `update` và kết thúc mà không init lại. **Không dùng lại cùng instance cho các request chạy đồng thời.**
- Với RSA-2048, modulus dài 256 byte, chữ ký RSA-PSS cũng dài 256 byte; đó không phải bằng chứng “độ dài message = 256”.
- `Signature` chưa init không thể nhận `update`; lỗi `SignatureException` được bắt và in `true` cho kiểm tra cuối.
- RSA-PSS dùng salt nên byte signature có thể khác giữa các lần ký cùng message; cách đánh giá đúng là gọi `verify`, **không so sánh byte giữa hai chữ ký mới**.
- Bài dùng `setParameter(PSS)` **trước init** và bộ tham số giống hệt hai phía. Các provider/HSM khác nhau có thể có yêu cầu về thời điểm set parameters hoặc khả năng PSS; cần đọc tài liệu provider đích và kiểm thử `getInstance → setParameter → initSign/initVerify → sign/verify`. Nếu không hỗ trợ, báo lỗi cấu hình; không tự hạ cấp scheme một cách âm thầm.

**Giới hạn demo:** private key chỉ sống trong RAM; chạy lại chương trình sẽ sinh key pair mới nên chữ ký cũ không tự xác minh được bằng public key mới. Môi trường thực phải có private key được bảo vệ, public key/chứng chỉ đáng tin, key ID/version, policy kiểm tra và định dạng thông điệp nhất quán.

## 7. Ký/xác minh dữ liệu lớn theo luồng với `update`

Với file nhiều megabyte, không cần `Files.readAllBytes()` chỉ để gọi `Signature.update()`. Có thể đưa byte từ stream theo chunk:

```java
// Đoạn minh họa trong phương thức có throws IOException, GeneralSecurityException;
// signer đã được initSign(privateKey), path là Path đã chọn.
try (java.io.InputStream input = java.nio.file.Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        if (count > 0) {
            signer.update(buffer, 0, count);
        }
    }
}
byte[] signature = signer.sign();
```

Bên verify thực hiện cùng logic đọc **cùng byte file**, nhưng engine phải `initVerify(trustedPublicKey)` và kết thúc bằng `verify(signature)`:

```java
// verifier đã initVerify(trustedPublicKey).
try (java.io.InputStream input = java.nio.file.Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        if (count > 0) {
            verifier.update(buffer, 0, count);
        }
    }
}
boolean accepted = verifier.verify(signatureBytes);
```

Hai đoạn này là **mảnh code tích hợp**, không phải chương trình standalone: `path`, các engine, key và chữ ký phải được cung cấp từ logic ứng dụng. `update(data, off, len)` phải dùng **số byte thực đọc `count`**, không dùng toàn bộ `buffer.length` cho chunk cuối, vì phần cuối buffer có thể chứa dữ liệu cũ.

**Chi phí bộ nhớ:** cung cấp dữ liệu theo chunk giúp không phải giữ toàn bộ file trong `byte[]` ở lớp ứng dụng; không được khẳng định mọi provider đều xử lý nội bộ theo streaming với mức bộ nhớ tuyệt đối cố định. Nếu đọc dữ liệu từ file có thể thay đổi đồng thời, phải chốt một snapshot/nguồn bất biến hoặc kiểm tra dữ liệu cuối trước khi công nhận kết quả để tránh TOCTOU.

Đối với `update(ByteBuffer)`, phương thức xử lý toàn bộ `remaining()` và dịch `position()` tới `limit()`. Nếu muốn dùng lại buffer cho mục đích khác, phải quản lý `flip`/`rewind`/`duplicate` đúng; không gọi `update(buffer)` hai lần với buffer đã hết `remaining()` rồi tưởng đã đưa cùng message hai lần.

## 8. Chính xác *byte nào* được ký? Encoding và phạm vi tin cậy

Một chữ ký hợp lệ chỉ bảo đảm tính toàn vẹn của **chuỗi byte thực đã nạp**. Không bảo đảm nội dung hiển thị là “giống nhau” nếu encoding/normalization khác. Những lỗi dễ gặp:

- Bên ký gọi `text.getBytes()` theo charset mặc định; bên verify dùng UTF-8: cùng ký tự có thể ra byte khác. Dùng `StandardCharsets.UTF_8` hoặc giao thức đã định.
- Bên ký tạo JSON với một thứ tự field, bên nhận parse rồi serialize lại thứ tự khác: byte đã thay đổi dù object có nội dung giống nhau. Cần canonical serialization được quy định hoặc xác minh trên **raw signed bytes**.
- Bên ký nối nhiều chuỗi không có length-prefix: `"ab" || "c"` trùng byte với `"a" || "bc"`. Nếu ý nghĩa field quan trọng, cần schema có version, tag/length, thứ tự cố định và context.
- Bên ký chỉ đưa payload vào `update()` nhưng ứng dụng xác nhận cả `amount`, `recipient`, `tenant`, `expiry` nằm ở header chưa ký: attacker có thể đổi header mà verify vẫn đúng với payload cũ. **Ký đầy đủ dữ liệu tác động tới quyết định nghiệp vụ.**
- Bên ký thực hiện normalization Unicode còn bên nhận thì không (hoặc ngược lại): khác byte. Chuẩn hóa và ký theo encoding được ghi trong protocol.
- Nếu ký nội dung chứa `algorithmId`, `keyId` hoặc type/version, cần tránh trường chưa xác thực điều khiển lựa chọn thuật toán yếu; parser phải dùng allowlist và chính sách chữ ký phù hợp.

Một cấu trúc message có thể được định nghĩa như:

```text
signed_input = domain_separator
            || format_version
            || type_length || message_type
            || payload_length || payload
            || context_length || context
```

Chỉ là sơ đồ khái niệm: phải quy định cụ thể từng trường (bao nhiêu byte, unsigned/signed, endianness, byte encoding, max length). **Domain separator** như `invoice-signature-v1` giúp ngăn chữ ký có hiệu lực ở protocol này bị dùng sai sang protocol khác nếu cùng key và cùng byte payload.

Chữ ký không tự chống **replay**. Một thông điệp đã ký hợp lệ vẫn có thể bị phát lại nhiều lần. Nếu use case cần “chỉ dùng một lần”, phải kiểm tra transaction ID, nonce, sequence, expiration, recipient và duy trì trạng thái đã sử dụng; dữ liệu này cần nằm trong phần đã ký.

## 9. Thuật toán, provider và tham số trong chu trình `Signature`

| Scheme Java | Thuộc tính đáng lưu ý | Vai trò của `Signature` |
| --- | --- | --- |
| `SHA256withRSA` | Dùng SHA-256 cùng scheme chữ ký RSA kiểu PKCS#1 v1.5; thuộc mức yêu cầu tối thiểu của `Signature` trên Java SE 17 | `initSign(RSA private)`, `update(message)`, `sign()` và `initVerify(RSA public)`, `update(message)`, `verify(sig)`. |
| `RSASSA-PSS` | RSA-PSS sử dụng salt, digest, MGF và trailer parameters; cần thống nhất cả phía ký và verify | Cùng lifecycle; đặt `PSSParameterSpec` rõ. |
| `SHA256withECDSA` | ECDSA; chữ ký thường có định dạng ASN.1 DER trong Java khi dùng tên chuẩn, tùy scheme/biến thể | Lifecycle vẫn vậy nhưng loại key là EC, không phải RSA. |
| `Ed25519` | EdDSA; không dùng PSS params; key và signature scheme khác RSA | `Signature.getInstance("Ed25519")` với private/public key Ed25519 khi provider hỗ trợ. |

Không tự đổi `SHA256withRSA` sang `RSASSA-PSS` chỉ bằng tên phía verify mà bỏ qua encoding/params; chữ ký v1.5 không phải chữ ký PSS. Phải có **algorithm/suite ID được phép**, parameters, key ID và version trong hệ thống lưu trữ/giao tiếp.

`Signature.getInstance()` chọn provider thực thi, nhưng **không phải giấy chứng nhận** rằng key, scheme, params và môi trường chạy đã an toàn. Có thể lỗi ở `initSign`, `setParameter`, `update`, `sign`, `initVerify` hoặc `verify`. Phải kiểm thử cả chu trình trên provider dự kiến, nhất là khi dùng khóa từ HSM/KMS hoặc runtime không phải JDK đã dùng phát triển.

`Signature` dùng API `java.security` để ký/xác minh; các engine khác có mục tiêu khác:

- `MessageDigest` chỉ băm dữ liệu, không có private key: không xác thực chủ thể.
- `Mac` dùng khóa bí mật đối xứng chung: các bên nắm khóa cùng tạo/kiểm tra MAC, không tương đương public-key signature.
- `Cipher` mã hóa/giải mã: bí mật không đồng nghĩa nguồn gốc được chứng thực.
- `KeyAgreement` thỏa thuận shared secret: không tự tạo một chữ ký số.

## 10. Ngoại lệ và cách xử lý an toàn

| Loại vấn đề | Khi nào xảy ra | Hướng xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `Signature.getInstance("RSASSA-PSS")` khi runtime/provider không có scheme | Kiểm tra version/provider/thuật toán được yêu cầu; không tự fallback sang scheme khác không được giao thức phê duyệt. |
| `InvalidKeyException` | `initSign(private)`/`initVerify(public)` dùng khóa sai loại, sai quyền hoặc không hợp lệ | Kiểm tra key algorithm, size, key usage, key storage/HSM và policy. |
| `InvalidAlgorithmParameterException` | `setParameter(PSS)` không được provider chấp nhận | Kiểm tra digest/MGF1/salt/trailer, khả năng triển khai và cấu hình hai bên. |
| `SignatureException` ở `update` | Chưa gọi init phù hợp, object sai state hoặc provider không xử lý được | Khởi tạo đúng chiều, tạo engine mới cho operation khi cần. |
| `SignatureException` ở `sign`/`verify` | Trạng thái sai, signature encoding không phù hợp hoặc lỗi provider | Từ chối operation; bảo đảm lỗi được log an toàn và phân loại theo kiểm soát. |
| `verify(...) == false` | Chữ ký không khớp thông điệp/public key/params được cung cấp | Từ chối; không tự “sửa” message hoặc bỏ qua metadata để thử lại. |
| `verify(...) == true` nhưng sai danh tính | Public key chưa được xác thực hoặc bị attacker thay thế | Xác minh nguồn, chuỗi tin cậy, identity và key usage trước khi gán người ký. |
| `verify(...) == true` nhưng thao tác bị phát lại | Chữ ký không chống replay tự động | Có expiry/id/sequence trong dữ liệu đã ký và policy/state kiểm tra replay. |

Không nên xử lý ngoại lệ bằng cách cho phép dữ liệu đi qua. Luồng an toàn là **fail closed**: nếu bước xác minh không thành công, không thực hiện giao dịch hoặc chấp nhận dữ liệu như đã xác thực.

## 11. Kiểm thử chu trình và checklist review

Bài kiểm thử nên bao gồm:

1. **Happy path:** cùng message bytes, đúng public key, cùng scheme/params → `verify == true`.
2. **Dữ liệu bị sửa:** đổi một byte trong message đã ký → `verify == false`.
3. **Sai thứ tự hoặc thiếu chunk:** ký `A||B`, verify `B||A` hay chỉ `A` → fail.
4. **Sai public key:** dùng public key của cặp khác → không xác minh hợp lệ.
5. **Tham số scheme sai:** PSS digest/MGF1/salt khác → fail hoặc lỗi params.
6. **Không init:** `update`/`sign`/`verify` trước init → `SignatureException` thích hợp.
7. **Sau `sign`/`verify`:** thử message mới với `update` lại, không dựa vào dữ liệu message trước.
8. **Encoding và canonicalization:** ký và verify trên nhiều runtime/language bằng cùng test vectors, UTF-8, layout và key/params được đặc tả.
9. **Metadata:** sửa `tenant`, `role`, `amount`, `expiry`, `audience` trong phần đã ký → fail; sửa metadata không nằm trong phần ký là điểm cần cải thiện protocol.
10. **Replay và trust:** chữ ký hợp lệ nhưng đã hết hạn/ID đã dùng/public key chưa được phê duyệt → nghiệp vụ phải từ chối.

Checklist khi review code:

- [ ] `getInstance` dùng **tên thuật toán chữ ký rõ ràng**, không lấy tùy ý từ dữ liệu chưa được xác thực.
- [ ] `initSign` nhận **private key** đúng người ký/mục đích; `initVerify` dùng **public key đáng tin** đúng người ký.
- [ ] Mọi byte quan trọng đều được `update` đúng thứ tự, đúng charset/schema; khi streaming, `len` là số byte thực đọc.
- [ ] `sign()` và `verify()` chỉ chạy sau init/update hợp lệ; biết engine reset sau operation, không chia sẻ giữa các thread.
- [ ] PSS và các params khác được chỉ định/tương thích; key length và provider đáp ứng chính sách.
- [ ] Kết quả `verify` **phải được kiểm tra**; `false` và mọi exception liên quan đều dẫn tới từ chối.
- [ ] Chứng chỉ, định danh và key usage được xác thực **ngoài** chữ ký; thông điệp ký không được mặc định là confidential hay chống replay.
- [ ] Có test signature altered, content altered, wrong key, stale/replayed message, wrong params và cross-provider khi cần.

## 12. Tự kiểm tra kiến thức

**Câu 1:** `Signature.getInstance("SHA256withRSA")` rồi `update` được ngay không?  
**Không.** Phải gọi `initSign(privateKey)` hoặc `initVerify(publicKey)` trước.

**Câu 2:** Bên ký `update(A)` và `update(B)`, bên verify `update(A||B)` có được không?  
**Có**, nếu byte nối chính xác cùng thứ tự và cùng scheme/params. Kích thước chunk không làm thay đổi message.

**Câu 3:** `Signature.sign()` trả ciphertext hay signature?  
**Signature bytes.** Message không được mã hóa bởi `Signature`.

**Câu 4:** Vì sao thay `amount=100` thành `amount=101` làm `verify` thất bại?  
Vì chữ ký đã ràng buộc với **byte message đã nạp**. Nội dung mới không còn khớp chữ ký cũ.

**Câu 5:** Sau `verify()` có được nạp message khác không?  
**Có** theo contract: đối tượng reset về initialized VERIFY state với key cũ; phải `update` lại message mới. Trong code concurrency nên dùng engine riêng cho mỗi operation.

**Câu 6:** `verify() == true` đã đủ khẳng định “Alice ký” chưa?  
**Chưa.** Cần xác thực public key thật sự thuộc Alice và được phép dùng ký; cần thêm kiểm tra expiry, replay và context theo ứng dụng.

**Câu 7:** RSA-PSS ký lại cùng message bằng cùng private key có bắt buộc ra đúng cùng byte chữ ký không?  
**Không.** PSS dùng randomness (salt); kiểm chứng bằng `Signature.verify`, không dựa vào byte equality.

## Tài liệu gốc và đọc thêm

- [Java SE 17 — `java.security.Signature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): tài liệu chính cho **ba giai đoạn**, state `UNINITIALIZED`/`SIGN`/`VERIFY`, `update`, `sign`, `verify` và reset sau khi hoàn thành.
- [Java SE 17 — `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html): SHA-256, MGF1, salt length, trailer.
- [Java SE 17 — `MGF1ParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html): digest sử dụng bên trong MGF1.
- [Java SE 17 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): Signature engine, provider, service architecture và ví dụ sử dụng.
- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên chuẩn và nhóm thuật toán `Signature` bắt buộc/khả dụng.
- [RFC 8017 — PKCS #1 v2.2](https://www.rfc-editor.org/rfc/rfc8017): RSASSA-PSS, encoding, salt và mô hình xác minh.

**Ghi nhớ:** `initSign(private) → update(message bytes) → sign()` tạo chữ ký; `initVerify(trustedPublic) → update(same message bytes) → verify(signature)` kiểm tra. Hai phía phải thống nhất **byte, thuật toán, tham số và danh tính khóa**. `Signature` quản lý tính toàn vẹn và chứng thực theo khóa, không cung cấp bảo mật bí mật hay chống replay một cách tự động.
