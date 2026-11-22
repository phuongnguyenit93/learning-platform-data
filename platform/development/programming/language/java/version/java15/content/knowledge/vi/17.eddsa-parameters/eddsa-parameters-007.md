# Phân biệt prehash theo giao thức với tự băm thông điệp trong EdDSA (Java 15+)

## 1. Mục tiêu: hai việc nghe giống nhau nhưng **khác thuật toán**

Với chữ ký số EdDSA, câu “băm dữ liệu rồi ký” rất dễ gây hiểu nhầm. **Ed25519ph** và **Ed448ph** là những **chế độ được định nghĩa hoàn chỉnh bởi RFC 8032**, bao gồm cách tiền băm (*prehash*) **và** cách phân tách miền (*domain separation*) trong thuật toán chữ ký. Chúng **không tương đương** với việc lập trình viên tự gọi `MessageDigest` rồi đưa digest cho chế độ **Ed25519/Ed448 thông thường**.

Đây là sự khác biệt cần ghi nhớ:

```text
Đúng với Ed25519ph:
    Ed25519ph_sign(privateKey, message M, context C)

Không tương đương với Ed25519ph:
    Ed25519_sign(privateKey, SHA-512(M))
```

Cả hai trường hợp đều sử dụng hàm băm ở đâu đó, nhưng cách băm, **cờ mode**, **context** và các đầu vào của quá trình tạo nonce/challenge không giống nhau. Nếu bên gửi ký theo một cách mà bên nhận xác minh theo cách kia, chữ ký thường **không xác minh thành công** dù dùng cùng key và cùng thông điệp ban đầu.

**Mục tiêu bài học:**

1. Hiểu **PureEdDSA** (`Ed25519`, `Ed448`) và **HashEdDSA/prehash** (`Ed25519ph`, `Ed448ph`) theo RFC 8032.
2. Phân biệt **`PH(M)` của thuật toán** với **digest tự tính trước khi gọi `Signature.update`**.
3. Dùng `java.security.spec.EdDSAParameterSpec` (`prehash` và `context`) trong Java 15+.
4. Viết đoạn Java chạy được, chứng minh `Ed25519ph(M)` **không xác minh như** `Ed25519(SHA-512(M))`.
5. Hiểu Ed25519ctx, các context bytes, mode mismatch, key/curve, kích thước signature và tính tương tác đa nền tảng.
6. Chọn chế độ theo **hợp đồng giao thức**, không bật prehash vì nghĩ tự động nhanh hơn hoặc an toàn hơn.

`EdDSAParameterSpec` và `Signature.setParameter(AlgorithmParameterSpec)` là API Java SE chính thức, còn hỗ trợ trong Java hiện đại. Không cần API preview hay giải pháp nội bộ đã bị thay thế.

## 2. Giải thích bằng các đối tượng M, PH(M), H và chữ ký

Ký hiệu:

- `M`: **toàn bộ byte thông điệp** được giao thức định nghĩa để ký. Ví dụ bytes UTF-8 của chuỗi, hoặc serialized payload được chuẩn hóa theo quy tắc.
- `PH(M)`: hàm **tiền băm ở mức biến thể EdDSA**. Với biến thể pure, `PH(M) = M`; với biến thể prehash, `PH` là hàm băm mà RFC chỉ định.
- `H`: hàm băm được **chính cơ chế tạo chữ ký EdDSA** sử dụng khi tính nonce/challenge, cùng các thông số domain separation. Nó không phải thao tác mà ứng dụng tự chèn tùy ý.
- `C`: **context bytes** (nếu mode cho phép); chúng là một phần của lựa chọn biến thể và phải khớp giữa ký và xác minh.
- `F`: cờ **prehash mode**, ví dụ `0` với biến thể không prehash, `1` với biến thể prehash theo RFC 8032.

### 2.1. PureEdDSA không có nghĩa “không dùng hash”

Trong chế độ **Ed25519 thuần**, thư viện vẫn sử dụng **SHA-512 nội bộ** trong quy trình sinh chữ ký. “Pure” chỉ có nghĩa là **không có bước `PH(M)` riêng biệt ở đầu vào**: toán tử `PH` là phép đồng nhất, tức `PH(M) = M`.

Với **Ed448 thuần**, thuật toán dùng SHAKE256 bên trong các bước tạo chữ ký, nhưng cũng không có bước `PH(M)` riêng dành cho message.

Vì vậy những cách diễn đạt sau là **sai**:

- “Ed25519 thuần không băm thông điệp.”
- “Muốn Ed25519 an toàn thì phải tự SHA-512 trước khi ký.”
- “Ed25519ph chỉ là Ed25519 được gọi với một thông điệp có độ dài 64 byte.”
- “Cứ băm trước là tương thích Ed25519ph.”

Điều đúng là **cùng một họ thuật toán nhưng mỗi mode có quy tắc chính xác riêng**.

### 2.2. Pure vs prehash ở cấp giao thức

| Biến thể theo RFC 8032 | Curve | `PH(M)` | Domain separation | Dữ liệu ứng dụng nên đưa vào Java `Signature.update` |
| --- | --- | --- | --- | --- |
| **Ed25519** | edwards25519 | `M` | Không có `dom2` trong biến thể thuần, không có context | **M gốc** |
| **Ed25519ctx** | edwards25519 | `M` | `dom2`, có context mode | **M gốc**, đặt context qua spec |
| **Ed25519ph** | edwards25519 | `SHA-512(M)` (64 byte) | `dom2` với `phflag = 1` và context | **M gốc**, đặt `prehash = true` |
| **Ed448** | edwards448 | `M` | `dom4`, hỗ trợ context | **M gốc**, mode `prehash = false` |
| **Ed448ph** | edwards448 | `SHAKE256(M, 64)` (64 byte) | `dom4` với `phflag = 1` và context | **M gốc**, đặt `prehash = true` |

**Điểm đặc biệt của Ed448ph:** hàm prehash là **SHAKE256 với đầu ra đúng 64 byte**, **không phải SHA-512**. Không dùng `MessageDigest.getInstance("SHA-512")` thay thế. Cũng đừng suy đoán một provider có hay không có tên `SHAKE256` trong `MessageDigest` chỉ từ việc provider ấy hỗ trợ `Signature("Ed448")`: đó là những dịch vụ khác nhau.

Chế độ prehash có thể giúp một số giao thức/chữ ký xử lý thông điệp theo cách nhất định, nhưng nó **không làm thay đổi** độ dài chữ ký theo đường cong: Ed25519/Ed25519ph đều 64 byte, Ed448/Ed448ph đều 114 byte. **Không thể xác định mode chỉ bằng độ dài chữ ký.**

## 3. Vì sao `Ed25519ph(M)` khác `Ed25519(SHA-512(M))`?

Phân biệt hai đường đi:

```text
                        MESSAGE M
                            |
           +----------------+----------------+
           |                                 |
     ĐÚNG: Ed25519ph                    KHÁC: tự hash
           |                                 |
     RFC 8032 chọn                      ứng dụng tính
     PH(M) = SHA-512(M)                D = SHA-512(M)
           |                                 |
     RFC 8032 dùng                      Ed25519 thuần
     phflag=1, dom2                    ký chính D
     và context tương ứng                   |
           |                                 |
      chữ ký S_ph                        chữ ký S_plainD
           |                                 |
     Verify Ed25519ph(M)              Verify Ed25519(D)
```

Dấu `dom2` là phép domain separation của RFC 8032 cho Ed25519ctx/Ed25519ph. Nó đưa **mode** và **context** vào những bước hash nội bộ liên quan tới tính nonce/challenge. Ed25519 thuần **không** thay đổi thành Ed25519ph chỉ vì bytes của input bây giờ dài 64.

Có thể hiểu đơn giản về **cấu trúc**, không phải mã triển khai đầy đủ:

```text
Ed25519ph:
    D = SHA-512(M)
    r = SHA-512(dom2(1, C) || secretPrefix || D)
    R = r * B
    k = SHA-512(dom2(1, C) || R || publicKey || D)
    S = (r + k * secretScalar) mod groupOrder
    signature = Encode(R) || Encode(S)

Ed25519 thuần được cho digest làm "message":
    D = SHA-512(M)
    r2 = SHA-512(secretPrefix || D)
    R2 = r2 * B
    k2 = SHA-512(R2 || publicKey || D)
    S2 = (r2 + k2 * secretScalar) mod groupOrder
    signature2 = Encode(R2) || Encode(S2)
```

Các công thức **khái niệm** nhằm chỉ ra **`dom2(1, C)` xuất hiện ở prehash mode nhưng không ở Ed25519 thuần**; RFC 8032 là nguồn chuẩn cho thứ tự byte, encoding và mọi kiểm tra. Không tự viết hiện thực mật mã từ sơ đồ này: các chi tiết scalar, point validation, endianness, constant-time và edge cases phải do provider đáng tin xử lý.

Với cùng private key và M, chữ ký `Ed25519ph(M)` và `Ed25519(SHA-512(M))` có định nghĩa khác nhau; trong ví dụ Java ở phần 7, hai kết quả thực tế **khác nhau**, và việc xác minh chéo **thất bại**.

### 3.1. Khi nào “tự hash rồi ký” lại là đúng?

Có những **giao thức khác** quy định rõ rằng đối tượng được ký là **digest D**, ví dụ `D = SHA-256(serialize(document))`, sau đó ký bằng một thuật toán cụ thể trên **bytes D**. Khi đó ứng dụng thực sự đang ký **D như thông điệp** theo chính giao thức ấy.

Điều đó có thể đúng với một giao thức đã được thiết kế cẩn thận, nhưng **đừng đặt tên nó là Ed25519ph/Ed448ph** nếu nó không tuân theo quy tắc của các biến thể RFC 8032. Bên verify phải biết **exactly what is signed**: là M, D, prefix || D hay một cấu trúc có version, domain, algorithm ID và key ID.

Nếu dự án không có hợp đồng yêu cầu ký digest, **đừng tự thêm một bước `MessageDigest`** trước `Signature.update(...)`.

## 4. EdDSAParameterSpec trong Java 15+: API đúng cho mode và context

Class `java.security.spec.EdDSAParameterSpec` có từ **Java 15**:

```java
new EdDSAParameterSpec(false);              // pure mode
new EdDSAParameterSpec(true);               // prehash mode
new EdDSAParameterSpec(false, contextBytes); // context mode
new EdDSAParameterSpec(true, contextBytes);  // prehash + context
```

Đây là các **biểu thức minh họa**, dòng `contextBytes` yêu cầu một mảng bytes hợp lệ. Mọi giá trị boolean **không** liên quan việc “đã tự băm trước” ở client; nó **ra lệnh cho engine sử dụng biến thể** tương ứng.

Theo Javadoc, các chế độ được quyết định bởi tổ hợp:

1. `prehash = true` → `Ed25519ph` hoặc `Ed448ph` (tùy curve/khóa), với context nếu được cung cấp.
2. `prehash = false`, **có context** → `Ed25519ctx` hoặc `Ed448` với context.
3. `prehash = false`, **không cung cấp context** → `Ed25519` hoặc `Ed448` mặc định.

`EdDSAParameterSpec(boolean prehash)` biểu diễn **context không được chỉ định**. `EdDSAParameterSpec(boolean prehash, byte[] context)` biểu diễn **context được cung cấp**, kể cả một mảng rỗng. Javadoc cảnh báo **context rỗng nhưng có mặt có thể không tương đương context không có mặt**. Đặc biệt đối với Ed25519, context mode là biến thể khác so với Ed25519 thuần.

### 4.1. Độ dài và encoding context

Context được cung cấp dưới dạng **`byte[]`**, không phải số ký tự trong Java String:

- **Độ dài tối đa 255 byte**, không phải 255 Unicode code points.
- Constructor hai tham số **copy** dữ liệu context vào spec; `getContext()` trả `Optional<byte[]>` chứa bản sao khi có context.
- Truyền `null` vào constructor context sẽ gây `NullPointerException`; dài hơn 255 byte sẽ gây `InvalidParameterException`.
- Nếu muốn biểu diễn context bằng text, chọn encoding ổn định (ví dụ `StandardCharsets.UTF_8`), version rõ ràng và thống nhất các bên về **byte sequence**. Một ký tự có dấu có thể chiếm nhiều byte UTF-8; không được tự chuẩn hóa Unicode khác nhau giữa hai bên.
- Không coi context là password hay secret. Mục đích chính của nó là **domain separation**, phân tách những lớp thông điệp/ứng dụng khác nhau dùng chung hệ thống chữ ký.
- Một context được đặt sai một byte có thể làm chữ ký verify thất bại; không “sửa” bằng cách thử vô số context đoán mò trong production.

Ví dụ context:

```java
byte[] context = "invoice-v1"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

EdDSAParameterSpec spec = new EdDSAParameterSpec(true, context);
```

Đây là đoạn code để đặt trong phương thức. Bên ký và bên verify phải dùng **cùng curve, mode, context bytes, message bytes và public key tương ứng**.

### 4.2. Cách gọi `Signature` đúng

Với thông điệp M muốn ký theo **Ed25519ph**:

```java
Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(new EdDSAParameterSpec(true));
signer.initSign(privateKey);
signer.update(messageBytes); // Đưa M GỐC, không đưa SHA-512(M)
byte[] signature = signer.sign();
```

Đây là **đoạn minh họa** cần có `privateKey` và `messageBytes` hợp lệ, import `java.security.*` và `java.security.spec.EdDSAParameterSpec`. Trong ví dụ hoàn chỉnh bên dưới, `setParameter(...)` được gọi **trước `initSign` hoặc `initVerify`**, sau đó mới gọi `update` và `sign/verify`.

Xác minh tương ứng:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.setParameter(new EdDSAParameterSpec(true));
verifier.initVerify(publicKey);
verifier.update(messageBytes); // Vẫn là M GỐC
boolean valid = verifier.verify(signature);
```

**Không** làm thế này nếu mục tiêu là Ed25519ph:

```java
// SAI với giao thức Ed25519ph:
byte[] digest = MessageDigest.getInstance("SHA-512")
        .digest(messageBytes);
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(digest);
byte[] notAnEd25519phSignature = signer.sign();
```

Đây là ví dụ **phản minh họa**. Nó có thể tạo một chữ ký hợp lệ cho thông điệp **D = SHA-512(M)** theo **Ed25519 thuần**, nhưng nó **không** tạo chữ ký Ed25519ph của M.

### 4.3. Chọn tên thuật toán chuẩn, không tự tạo tên `"Ed25519ph"`

Trong **Java Security Standard Algorithm Names** hiện đại, `Signature` có các tên chuẩn:

- `"Ed25519"`
- `"Ed448"`
- `"EdDSA"`

Để chọn **prehash mode** trên Java SE, dùng `setParameter(new EdDSAParameterSpec(true))`; không giả định `Signature.getInstance("Ed25519ph")` hoặc `"Ed448ph"` được mọi provider hỗ trợ như **tên chuẩn JCA**.

Nếu giao thức cố định Ed25519, ưu tiên tên curve cụ thể `"Ed25519"`. Với `"EdDSA"` tổng quát, engine có thể xử lý các curve khác nhau tùy khóa/param; phải bảo đảm curve thực tế được xác định bởi hợp đồng. **Tên thuật toán, mode và curve là các chiều thông tin khác nhau**.

Một **standard name** không bảo đảm mọi provider hỗ trợ đầy đủ các tham số. Khi provider thiếu hoặc từ chối prehash/context, `setParameter` có thể ném `InvalidAlgorithmParameterException`. Không được âm thầm fallback sang pure mode: đó là **thay đổi giao thức và kết quả chữ ký**.

## 5. Ed25519, Ed25519ctx, Ed25519ph: phân biệt ba chế độ

Ba chế độ cùng sử dụng curve edwards25519 và cùng có chữ ký 64 byte, nhưng quy tắc khác nhau:

| Điều kiện | Ed25519 | Ed25519ctx | Ed25519ph |
| --- | --- | --- | --- |
| Curve | edwards25519 | edwards25519 | edwards25519 |
| `PH(M)` | M | M | SHA-512(M), 64 byte |
| `phflag` | Không dùng `dom2` | 0 | 1 |
| Context | Không có context mode | Có context, RFC khuyên không rỗng | Context theo RFC, có thể rỗng |
| Java `EdDSAParameterSpec` | `new EdDSAParameterSpec(false)` | `new EdDSAParameterSpec(false, C)` | `new EdDSAParameterSpec(true)` hoặc `(true, C)` |
| Kích thước chữ ký | 64 byte | 64 byte | 64 byte |
| Verify chéo một mode khác | Không nên/không hợp lệ theo định nghĩa | Không | Không |

Điểm thường bị nhầm: **`Ed25519ctx` không có prehash**, nhưng vẫn dùng **`dom2`** để tách domain. **`Ed25519ph` có cả prehash lẫn domain separation**. Không thể biến một chế độ thành chế độ khác bằng cách đơn thuần gắn thêm hoặc bỏ byte context sau khi ký.

### Vì sao context hữu ích?

Ví dụ một dịch vụ có thể ký cả “phiếu đặt hàng” và “biên nhận”. Nếu giao thức quy định riêng:

```text
Context A: orders-v1
Context B: receipts-v1
```

thì một chữ ký được tạo trong context A sẽ **không xác minh như một chữ ký context B** trên cùng M và cùng key. Đây là domain separation ở cấp chữ ký, giúp giảm nhầm lẫn khi những kiểu thông điệp khác nhau sử dụng cùng một cơ chế ký.

**Context không thay cho authorization.** Nếu attacker có quyền sử dụng private key và tùy ý chọn context, họ vẫn có thể ký dữ liệu trái phép. Quyền ký theo loại thông điệp phải được kiểm soát bằng thiết kế hệ thống.

## 6. Ed448 và Ed448ph: prehash **không** phải SHA-512

Với curve edwards448:

- **Ed448 thuần**: `PH(M) = M`; theo RFC 8032, thuật toán sử dụng `dom4` ngay cả trong chế độ không prehash.
- **Ed448ph**: `PH(M) = SHAKE256(M, 64)`; tức **SHAKE256 có độ dài đầu ra 64 byte**, với `phflag = 1` và `dom4` tương ứng.
- Cả hai có chữ ký **114 byte**, không thể phân biệt chỉ bằng kích thước.
- `Ed448` có thể dùng context. Bên gửi và nhận cần thống nhất **byte context** và cách xử lý absent-vs-empty nếu framework/API phân biệt.
- Trong Java, dùng `Signature.getInstance("Ed448")` và `EdDSAParameterSpec(true)` cho **Ed448ph**; vẫn cung cấp **M gốc** vào `update`.

```java
Signature signer = Signature.getInstance("Ed448");
signer.setParameter(new EdDSAParameterSpec(true));
signer.initSign(privateKeyEd448);
signer.update(messageBytes); // M GỐC
byte[] signature = signer.sign();
```

Đây là **đoạn minh họa**, chỉ hợp lệ khi `privateKeyEd448` thuộc đúng curve và provider hỗ trợ mode. Không thay thế SHAKE256 bằng SHA-512 hoặc đoán rằng `MessageDigest` của runtime có sẵn SHAKE256 chỉ vì Ed448ph được triển khai trong `Signature`.

**Lưu ý interoperability:** một thư viện ngoài Java có thể cung cấp hàm tên `sign_prehashed(...)` và yêu cầu caller đưa sẵn digest 64 byte, còn Java `Signature` với `EdDSAParameterSpec(true)` nhận **M gốc** rồi thực hiện prehash bên trong. Hai interface có thể cùng hiện thực Ed25519ph/Ed448ph nhưng có **hợp đồng đầu vào khác nhau**. Phải đọc tài liệu của API phía kia, không suy diễn từ chữ “prehash”.

## 7. Ví dụ Java 15+ hoàn chỉnh: ký/verify đúng, và chứng minh hai cách không tương đương

Ví dụ dưới đây **thực sự biên dịch/chạy**, sử dụng `KeyPairGenerator`, `Signature`, `EdDSAParameterSpec` và `MessageDigest` của Java SE. Nó kiểm tra:

1. `Ed25519(M)` (thuần) xác minh với **pure mode**.
2. `Ed25519ph(M)` xác minh với **prehash mode**.
3. Chữ ký `Ed25519(SHA-512(M))` **khác** chữ ký `Ed25519ph(M)`, xác minh chéo thất bại.
4. Chữ ký Ed25519ph không hợp lệ nếu thay **message M**.
5. Ed25519ctx cần **context bytes khớp**.
6. Ed448ph hoạt động với **114-byte signature**; Ed448 thuần không xác minh được chữ ký Ed448ph.

### 7.1. File `EdDsaPrehashDemo.java`

Tạo file đúng tên:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;

public class EdDsaPrehashDemo {
    static byte[] sign(PrivateKey key, String algorithm,
            EdDSAParameterSpec spec, byte[] message)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance(algorithm);
        signer.setParameter(spec);
        signer.initSign(key);
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(PublicKey key, String algorithm,
            EdDSAParameterSpec spec, byte[] message, byte[] sig)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.setParameter(spec);
        verifier.initVerify(key);
        verifier.update(message);
        return verifier.verify(sig);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        byte[] message = "Signed message 42".getBytes(StandardCharsets.UTF_8);
        byte[] other = "Signed message 43".getBytes(StandardCharsets.UTF_8);
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        EdDSAParameterSpec pure = new EdDSAParameterSpec(false);
        EdDSAParameterSpec ph = new EdDSAParameterSpec(true);

        byte[] pureSig = sign(pair.getPrivate(), "Ed25519", pure, message);
        byte[] phSig = sign(pair.getPrivate(), "Ed25519", ph, message);
        byte[] digest = MessageDigest.getInstance("SHA-512").digest(message);
        byte[] manualSig = sign(pair.getPrivate(), "Ed25519", pure, digest);

        System.out.println("Ed25519 pure verifies="
                + verify(pair.getPublic(), "Ed25519", pure, message, pureSig));
        System.out.println("Ed25519ph verifies="
                + verify(pair.getPublic(), "Ed25519", ph, message, phSig));
        System.out.println("ph equals pure(SHA-512(M))="
                + Arrays.equals(phSig, manualSig));
        System.out.println("ph verifies manual signature="
                + verify(pair.getPublic(), "Ed25519", ph, message, manualSig));
        System.out.println("pure verifies ph signature="
                + verify(pair.getPublic(), "Ed25519", pure, message, phSig));
        System.out.println("ph verifies other message="
                + verify(pair.getPublic(), "Ed25519", ph, other, phSig));

        byte[] context = "orders-v1".getBytes(StandardCharsets.UTF_8);
        byte[] wrongContext = "orders-v2".getBytes(StandardCharsets.UTF_8);
        EdDSAParameterSpec ctx = new EdDSAParameterSpec(false, context);
        byte[] ctxSig = sign(pair.getPrivate(), "Ed25519", ctx, message);
        System.out.println("Ed25519ctx verifies="
                + verify(pair.getPublic(), "Ed25519", ctx, message, ctxSig));
        System.out.println("context mismatch verifies="
                + verify(pair.getPublic(), "Ed25519",
                    new EdDSAParameterSpec(false, wrongContext), message, ctxSig));

        KeyPair pair448 = KeyPairGenerator.getInstance("Ed448")
                .generateKeyPair();
        byte[] ph448 = sign(pair448.getPrivate(), "Ed448", ph, message);
        System.out.println("Ed448ph length=" + ph448.length);
        System.out.println("Ed448ph verifies="
                + verify(pair448.getPublic(), "Ed448", ph, message, ph448));
        System.out.println("Ed448 pure verifies ph="
                + verify(pair448.getPublic(), "Ed448", pure, message, ph448));
    }
}
```

### 7.2. Biên dịch/chạy

Dùng JDK hiện đại còn được nhà cung cấp hỗ trợ, có `javac` nhận mức `--release 15` (ví dụ JDK 21). Chạy tại thư mục chứa file:

```bash
javac --release 15 -encoding UTF-8 EdDsaPrehashDemo.java
java EdDsaPrehashDemo
```

Ví dụ đã được **biên dịch bằng `javac --release 15` và chạy thành công với một JDK hiện đại (JDK 24)**, kiểm tra cả Ed25519, Ed25519ph, Ed25519ctx và Ed448ph. Chỉ cần các JCA providers trong runtime hỗ trợ các tên thuật toán và mode tương ứng (SunEC của JDK thông thường hỗ trợ). Một JRE/provider tùy biến không được bảo đảm có đầy đủ chức năng.

**Stdout chính xác của ví dụ khi các dịch vụ được hỗ trợ:**

```text
Ed25519 pure verifies=true
Ed25519ph verifies=true
ph equals pure(SHA-512(M))=false
ph verifies manual signature=false
pure verifies ph signature=false
ph verifies other message=false
Ed25519ctx verifies=true
context mismatch verifies=false
Ed448ph length=114
Ed448ph verifies=true
Ed448 pure verifies ph=false
```

Các cặp khóa sinh ngẫu nhiên nên **không** thể hard-code bytes của private key, public key hoặc chữ ký làm kết quả đầu ra. Ngược lại, output dựa trên `boolean`, mode tương ứng và độ dài chữ ký **ổn định** theo định nghĩa của EdDSA/RFC 8032, nên phù hợp để học và kiểm thử.

### 7.3. Giải thích các điểm quan trọng trong code

- Hai phương thức `sign`/`verify` nhận **`EdDSAParameterSpec`** như một phần **hợp đồng của chữ ký**, không chỉ nhận tên curve. `setParameter` đặt mode trước khi init key.
- `pure` được tạo bằng `new EdDSAParameterSpec(false)`, còn `ph` bằng `new EdDSAParameterSpec(true)`. Cả hai dùng **cùng** cặp khóa Ed25519 và **cùng** M gốc trong `sign`.
- `pureSig` xác minh đúng khi bên nhận dùng `pure`; `phSig` xác minh đúng khi bên nhận dùng `ph`.
- `digest` được tự tính từ M bằng `MessageDigest("SHA-512")` **chỉ để minh họa phản ví dụ**. `manualSig` ký digest D bằng **Ed25519 thuần**, không phải Ed25519ph(M).
- `Arrays.equals(phSig, manualSig)` trả `false`. Trong hệ thống bảo mật, **không dùng phép so sánh bytes này thay cho `Signature.verify`**; nó chỉ giúp nhìn thấy khác biệt trong demo.
- `verify(... ph, message, manualSig)` trả `false`: signature của pure(D) **không** xác minh như ph(M).
- `verify(... pure, message, phSig)` trả `false`: signature của ph(M) **không** xác minh như pure(M).
- `verify(... ph, other, phSig)` trả `false`: thay đổi message M làm chữ ký cũ không còn khớp.
- `ctx` mang context bytes `"orders-v1"`, vì vậy Ed25519ctx ký/xác minh đúng với context đó; `"orders-v2"` gây `false` dù key và M giữ nguyên.
- `pair448` là cặp khóa **khác thuộc Ed448**; nó ký `ph448` bằng `EdDSAParameterSpec(true)`. Chữ ký dài **114 byte**, verify với Ed448ph thành công, nhưng verify bằng Ed448 pure không thành công.
- Chương trình dùng `StandardCharsets.UTF_8` để cố định byte encoding. Hai chuỗi nhìn giống nhau nhưng khác encoding/Unicode normalization sẽ là **hai message khác nhau** đối với chữ ký số.

**Đừng chuyển ví dụ `manualSig` thành code production chỉ vì nó vẫn tạo chữ ký hợp lệ.** Nếu giao thức yêu cầu Ed25519ph, hãy xóa bước tự `SHA-512` và bật `EdDSAParameterSpec(true)` như phần còn lại.

## 8. Khi giao thức bên ngoài yêu cầu prehash: cách đọc cho đúng

Một mô tả kỹ thuật có thể dùng một trong các cách nói:

| Câu trong đặc tả | Ý nghĩa có thể có | Câu hỏi bắt buộc cần làm rõ |
| --- | --- | --- |
| “Sign with Ed25519” | Ed25519 thuần theo RFC 8032 | Có context hay mode riêng không? Byte serialization là gì? |
| “Sign with Ed25519ph” | Biến thể prehash **được RFC 8032 định nghĩa** | Bên ký/verify có hỗ trợ `phflag=1`, domain separation, context không? |
| “Sign with Ed448ph” | SHAKE256(M,64) theo RFC và `dom4` | Curve Ed448, context bytes và phiên bản giao thức đã thống nhất? |
| “Hash the data and sign” | **Mơ hồ**: có thể là Ed25519ph, hoặc ký digest dưới Ed25519 thuần | Hash nào, ai thực hiện, mode nào, bytes nào được đưa vào API ký, trường nào được verify? |
| “Sign SHA-256(payload) using Ed25519” | Có thể là một **giao thức tùy biến** ký digest `SHA-256(payload)` bằng Ed25519 thuần | Có đặc tả test vector và canonicalization rõ ràng không? Không tự gọi đây là Ed25519ph |
| “The signing API accepts a precomputed digest” | Bên nhận digest có thể thực hiện phần còn lại của prehash mode, **hoặc** ký digest như message | API mô tả `Ed25519ph` hay `Ed25519`? Digest đã tính theo chuẩn nào? |

### 8.1. Hai tầng xử lý phải được xác định riêng

**Tầng giao thức ứng dụng** quyết định bytes nào là message M cần ký: chẳng hạn JSON canonical, một cấu trúc versioned binary hoặc bytes của file. Trong khi đó **tầng mật mã** quyết định Ed25519 vs Ed25519ph vs Ed448ph và cách `PH` được tính.

Ví dụ một hệ thống định nghĩa:

```text
M = UTF8("invoice-v1") || lengthPrefix || canonicalInvoiceBytes
signature = Ed25519ph(privateKey, M, context="orders-v1")
```

Đây là **ký hiệu giao thức minh họa**, không phải source Java. Trong Java, hãy dựng **M đầy đủ** theo giao thức rồi gọi `Signature.update(M)` với `EdDSAParameterSpec(true, contextBytes)`. Không tự SHA-512(M) trước khi gọi `update`.

Nếu giao thức **thực sự** quy định:

```text
D = SHA-256(canonicalInvoiceBytes)
signature = Ed25519(privateKey, D)
```

thì đây là **Ed25519 thuần trên D**, không phải Ed25519ph. Bên verify phải dựng lại **cùng D** và dùng pure mode. Tốt nhất giao thức phải có version, algorithm ID, domain separation cho tầng application và test vectors để giảm nguy cơ ký nhầm cấu trúc.

### 8.2. Ký và verify phải thống nhất toàn bộ metadata

Một payload có chữ ký nên được định nghĩa đủ các thuộc tính:

- **Curve**: Ed25519 hay Ed448.
- **Signature mode**: pure, ctx hay prehash.
- **Context**: absent/present, byte length và exact bytes.
- **Key ID/public key**: phiên bản, nguồn tin cậy và cách ánh xạ tới người/service ký.
- **Message serialization**: encoding, canonicalization, thứ tự field, line ending, normalization, byte order, dấu phân cách và prefix/length rules.
- **Signature encoding**: raw RFC 8032 bytes hay lớp bao bọc riêng; đảm bảo phía nhận biết rõ.
- **Version/protocol ID**: tránh diễn giải cùng một byte array bằng những quy tắc khác nhau.
- **Dữ liệu được ký**: fields nào nằm trong M, fields nào không; không tin vào những metadata không có xác thực khi chúng có thể thay đổi ý nghĩa chữ ký.

**Không suy mode từ độ dài chữ ký**: Ed25519ph và Ed25519 thuần đều 64 byte; Ed448ph và Ed448 thuần đều 114 byte. **Không thử lần lượt mọi mode cho tới khi verify true** như một cơ chế mặc định: việc chấp nhận chế độ khác hợp đồng có thể mở cửa cho thuật toán-confusion/downgrade.

## 9. Khi nào nên chọn prehash?

RFC 8032 phân biệt PureEdDSA với HashEdDSA và lưu ý rằng prehash modes **không nên được dùng mặc định** chỉ để tăng độ an toàn; chúng chủ yếu hữu ích trong một số trường hợp tích hợp giao thức/API. Lý do: tính chống va chạm và các giả định bảo mật của lựa chọn prehash cần được xem xét, chứ không phải “thêm một hàm băm nên chắc chắn mạnh hơn”.

### Khuyến nghị thực hành

1. **Khi không có yêu cầu đặc biệt**, chọn chế độ **Ed25519 thuần** (hoặc Ed448 thuần theo chính sách) được các bên hỗ trợ.
2. **Khi chuẩn giao thức yêu cầu chính xác Ed25519ph hoặc Ed448ph**, hãy dùng `EdDSAParameterSpec(true)`/context thích hợp và test vector chuẩn — **không** tự hash rồi dùng pure mode.
3. **Khi API bên ngoài chỉ cho nhập digest**, đọc kỹ hợp đồng: nó có thể đã nhận **PH(M)** để hoàn thiện Ed25519ph, hoặc đơn giản ký digest như message. Hai cách là khác nhau.
4. **Khi cân nhắc vì thông điệp rất lớn**, đừng giả định bật prehash tự giải quyết mọi vấn đề bộ nhớ/streaming. Hành vi buffering và độ lớn dữ liệu của `Signature` phụ thuộc provider; test thực tế. Có thể đưa message theo từng khối qua `update(byte[], off, len)` hoặc `update(ByteBuffer)`, nhưng chế độ **vẫn do `EdDSAParameterSpec` quyết định**.
5. **Khi cần chia quyền theo ngữ cảnh**, dùng context theo RFC và bảo đảm cả signer/verifier thỏa cùng quy tắc. Context không phải thay thế authorization hoặc thiết kế key separation khi cần.
6. **Khi cần interoperability**, ưu tiên một bộ test vector từ chính giao thức, bao gồm negative tests (mismatched mode/context/message) thay vì chỉ có một ví dụ `verify=true`.

### 9.1. Streaming qua `update` không đồng nghĩa tự prehash

`Signature` cho phép nhiều lời gọi `update`:

```java
Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(new EdDSAParameterSpec(true));
signer.initSign(privateKey);
signer.update(part1);
signer.update(part2);
byte[] signature = signer.sign();
```

Đây là đoạn minh họa với `privateKey`, `part1` và `part2` có sẵn. Nó ký **M = part1 || part2** trong **prehash mode**. Hệ thống có thể truyền những phần của một message theo luồng, không cần tự tính `SHA-512(part1 || part2)`.

Điểm này **không bảo đảm** provider sẽ xử lý message theo cách sử dụng bộ nhớ hằng số; nội bộ provider có thể buffer. Muốn kiểm soát memory/performance, đo và kiểm thử đúng JDK/provider mục tiêu thay vì dựa vào tên mode.

### 9.2. Đừng băm hai lần ngoài ý muốn

Một lỗi phổ biến trong code review:

```java
byte[] digest = MessageDigest.getInstance("SHA-512").digest(message);
Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(new EdDSAParameterSpec(true));
signer.initSign(privateKey);
signer.update(digest); // KHONG PHAI Ed25519ph(M)
byte[] signature = signer.sign();
```

Đây là đoạn **phản minh họa**: `EdDSAParameterSpec(true)` sẽ khiến engine tự tính **`PH(digest)`**, tức với Ed25519ph là **`SHA-512(SHA-512(M))`** (trên bytes digest 64 byte), rồi dùng domain separation của `Ed25519ph`. Kết quả là **Ed25519ph(digest)**, không phải Ed25519ph của M ban đầu.

Một phương thức nhận `byte[]` không biết bạn đã băm dữ liệu hay chưa. Trách nhiệm giữ đúng ý nghĩa **M** thuộc về thiết kế giao thức và người viết code.

## 10. Tương tác với thư viện/provider khác

### 10.1. Standard name và provider hỗ trợ

Java SE chuẩn hóa các tên `"EdDSA"`, `"Ed25519"` và `"Ed448"` cho `Signature`, `KeyPairGenerator` và `KeyFactory`. Tuy nhiên, việc mỗi provider hỗ trợ đầy đủ các mode và parameter spec vẫn phụ thuộc vào triển khai.

Những lỗi cần biết:

| API / lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Signature.getInstance("Ed25519")` → `NoSuchAlgorithmException` | Không có provider cung cấp dịch vụ | Kiểm tra JDK/provider/security policy; không tự đổi sang thuật toán khác |
| `signer.setParameter(new EdDSAParameterSpec(true))` → `InvalidAlgorithmParameterException` | Provider không hỗ trợ prehash mode hoặc tham số không hợp lệ | Dùng provider hỗ trợ mode chuẩn hoặc xử lý lỗi cấu hình rõ ràng; **không fallback pure** |
| `signer.initSign(key)` → `InvalidKeyException` | Key sai curve, dạng khóa không tương thích hoặc provider không cho sử dụng | Xác định curve Ed25519/Ed448 và key provenance/format |
| `verifier.initVerify(key)` → `InvalidKeyException` | Public key sai loại hoặc không tương thích | Chọn public key đúng curve và provider |
| `signer.update(...)` / `signer.sign()` → `SignatureException` | Trạng thái/mode hoặc dữ liệu không hợp lệ, engine lỗi | Kiểm tra thứ tự init → update → sign và cấu hình provider |
| `verifier.verify(sig) == false` | Sai message, mode, context hoặc public key | Đối chiếu exact M/context/curve/key; không đoán sửa chữ ký |
| `verify(sig)` ném `SignatureException` | Signature hỏng encoding/độ dài hoặc provider không xử lý được | Phân biệt malformed signature và chữ ký hợp lệ nhưng không khớp |
| Context dài hơn 255 byte | Giới hạn RFC/Javadoc | Kiểm tra byte count trước khi tạo `EdDSAParameterSpec` |
| `MessageDigest("SHAKE256")` không có | Provider không hỗ trợ tên digest đó | Không tự thay SHA-512 cho Ed448ph; dùng `Signature` với `EdDSAParameterSpec(true)` |

Chữ ký được coi là **không hợp lệ** nếu không verify được theo **chính xác** contract đã chọn. Trong production, không tự chạy lại xác minh theo pure mode khi prehash thất bại, vì như vậy đang nới điều kiện chấp nhận ngoài đặc tả.

### 10.2. Biến thể pure, ctx và ph giữa các thư viện

Một thư viện có thể cung cấp:

- `sign(message)`: nhận M và tự thực hiện phần ký.
- `signPrehashed(digest)`: nhận đầu vào đã là `PH(M)`, tức **caller** phải tính digest đúng mode.
- `signWithContext(message, context)`: nhận M và context nhưng chưa chắc là prehash.
- `signPrehashMode(message)`: nhận M, tự tính PH(M) và chọn domain.

Không thể nhận biết chỉ bằng tên method. Cần đối chiếu **giả định input**, **mode flag**, **domain separation**, **curve** và kết quả **test vectors của RFC 8032**. Nếu một hệ thống ký bằng Java còn hệ kia verify bằng native library, kiểm thử cả một signature của mỗi bên và bảo đảm cùng byte serialization.

### 10.3. Chữ ký số không tự xác thực danh tính public key

`Signature.verify(...) == true` xác minh **chữ ký đúng cho public key bạn cung cấp**. Nó không tự khẳng định public key thuộc về đúng tổ chức hay service. Phân phối public key phải có cơ chế tin cậy (certificate validation, pinning, registry có xác thực, v.v.).

Chế độ prehash/domain separation **không thay thế** việc giữ kín private key, kiểm soát ai được gọi Sign, hay xác thực key ID. Đừng đưa private key vào log, hard-code trong source hoặc dùng key của Ed25519 như key X25519.

## 11. Kiểm thử cần làm cho một giao thức EdDSA

Để bảo đảm chế độ được triển khai đúng, ngoài trường hợp ký/verify thành công còn cần **negative tests**:

| Trường hợp | Cấu hình ký | Cấu hình verify | Kỳ vọng |
| --- | --- | --- | --- |
| Ed25519 thuần đúng | Pure, M, C absent | Pure, M, C absent | `true` |
| Ed25519ph đúng | Prehash, M | Prehash, M | `true` |
| Khác mode | Prehash, M | Pure, M | `false` |
| Khác mode, cùng digest ngoài | Pure, `SHA-512(M)` | Prehash, M | `false` |
| Thay message | Prehash, M | Prehash, M khác | `false` |
| Context đúng | Ed25519ctx, C1 | Ed25519ctx, C1 | `true` |
| Context khác | Ed25519ctx, C1 | Ed25519ctx, C2 | `false` |
| Ed448ph đúng | Prehash, Ed448, M | Prehash, Ed448, M | `true` |
| Ed448ph vs Ed448 pure | Prehash, Ed448, M | Pure, Ed448, M | `false` |
| Sai public key | Ph, key A | Ph, key B | `false` |
| Khác encoding M | Ký UTF-8 của M | Verify UTF-16/khác canonicalization | `false` |
| Provider không hỗ trợ mode | Yêu cầu prehash | Provider từ chối `setParameter` | Ném lỗi rõ, không tự chuyển mode |

Bảng nêu hành vi mong đợi với chữ ký và khóa hợp lệ trong mô hình giao thức. Nếu bytes signature sai format, JCA provider có thể ném `SignatureException` thay vì trả `false`. Hãy xử lý cả hai thành “không xác thực”, giữ thông tin chẩn đoán an toàn và không để dữ liệu chưa tin cậy làm ứng dụng chấp nhận kết quả.

Trong test liên ngôn ngữ, hãy dùng **key fixture test không phải production**, các **test vectors chính thức RFC 8032** và context/PH được mô tả rõ. Kết quả `signature.length` không đủ để phân biệt chế độ.

## 12. Những sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Ed25519 thuần không có hash” | Ed25519 dùng hash **nội bộ**, chỉ không có prehash `PH(M)` riêng | Phân biệt PH(M) và các hash để tạo nonce/challenge |
| Tự `SHA-512(M)` rồi Ed25519 và gọi đó là Ed25519ph | Thiếu `dom2(phflag=1, C)` của RFC 8032 | Chọn `EdDSAParameterSpec(true)`, truyền M gốc |
| Tự `SHA-512(M)` rồi Ed25519ph | Bị **prehash message digest thêm lần nữa** | Bỏ bước MessageDigest; đưa M gốc vào `update` |
| Dùng SHA-512 làm `PH` cho Ed448ph | RFC quy định `SHAKE256(M, 64)` | Dùng engine Ed448 + prehash flag, không tự thay digest |
| Tưởng `"Ed25519ph"` là tên chuẩn `Signature.getInstance` | Tên standard JCA là `Ed25519`/`Ed448`/`EdDSA` | Dùng `EdDSAParameterSpec` để chọn mode |
| Bật prehash chỉ vì nghĩ mạnh hơn | Prehash có trade-off và RFC không khuyên mặc định | Dùng pure trừ khi giao thức/interoperability cần ph |
| Dùng `new EdDSAParameterSpec(false, emptyContext)` như pure Ed25519 | Context **có mặt** có thể chọn Ed25519ctx, khác absent context | Với pure Ed25519 dùng constructor một tham số `(false)` |
| Dùng String length cho giới hạn context | Giới hạn là **255 byte** | Encode UTF-8 và kiểm tra `byte[].length` |
| Không lưu/trao đổi mode và context trong protocol | Bên verify không tái tạo cùng điều kiện | Định nghĩa curve/mode/context trong hợp đồng có version |
| Tự động thử mọi mode khi verify thất bại | Nới hợp đồng, tăng rủi ro algorithm confusion | Chọn mode từ policy tin cậy, verify đúng một cấu hình đã cho |
| Cho rằng prehash luôn dùng ít bộ nhớ | Provider vẫn có thể buffer | Đo trên provider cụ thể; streaming `update` không đồng nghĩa memory bound |
| Chỉ dựa vào `verify(true)` mà bỏ kiểm tra danh tính key | Verify xác nhận quan hệ signature–public key, không tự gắn danh tính | Xác thực nguồn gốc/key ID/certificate theo trust model |
| Ký một JSON nhưng verify JSON đã serialize khác | Dù ý nghĩa JSON giống nhau, bytes M khác | Dùng canonical byte encoding thống nhất |
| In private key/chữ ký test production vào log | Có thể lộ bí mật hoặc dữ liệu nhạy cảm | Dùng test fixture, tránh log secret và payload nhạy cảm |

## 13. Quy tắc ghi nhớ nhanh

**Nếu hợp đồng ghi “Ed25519” hoặc “Ed448” mà không có prehash/context**, dùng biến thể thuần và đưa **M gốc** vào `Signature.update(...)`.

**Nếu hợp đồng ghi “Ed25519ph”**, dùng `Signature("Ed25519")` + `EdDSAParameterSpec(true)` và đưa **M gốc** vào `update`. **Không** tự SHA-512 trước.

**Nếu hợp đồng ghi “Ed448ph”**, dùng `Signature("Ed448")` + `EdDSAParameterSpec(true)` và đưa **M gốc** vào `update`. Đừng tự SHA-512 vì chuẩn prehash của Ed448ph dùng SHAKE256.

**Nếu giao thức ghi “băm rồi ký” nhưng không nêu mode, algorithm ID và exact input bytes**, yêu cầu làm rõ/đối chiếu đặc tả và test vector trước khi triển khai. Đó là thông tin mật mã quan trọng, không phải chi tiết được phép đoán.

**Nếu dùng context**, phải khớp chính xác context bytes, tình trạng absent/present, curve, mode và serialized message trên cả hai phía.

## 14. Tài liệu chính thức, đang còn áp dụng

- **RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)**, mục 3–5, Ed25519/Ed25519ctx/Ed25519ph, Ed448/Ed448ph, `PH` và domain separation: https://www.rfc-editor.org/rfc/rfc8032.html
- **Java SE 15 — `EdDSAParameterSpec`**: constructors, `isPrehash()`, `getContext()`, giới hạn 255 byte và mapping mode: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html
- **Java SE hiện đại — `EdDSAParameterSpec`**, API tiếp tục được duy trì: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html
- **Java SE 15 — `Signature`**, `setParameter(AlgorithmParameterSpec)`, `initSign/initVerify`, `update` và `verify`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/Signature.html
- **Java Security Standard Algorithm Names** — tên `EdDSA`, `Ed25519`, `Ed448`: https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html
- **OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (Java 15)**: https://openjdk.org/jeps/339
- **RFC 8032, Section 8** — lưu ý bảo mật về các biến thể prehash, context và lựa chọn chế độ: https://www.rfc-editor.org/rfc/rfc8032.html#section-8

**Kết luận:** prehash theo RFC 8032 là **chọn một biến thể thuật toán**, không phải thao tác “ứng dụng tự băm trước” có thể tự hoán đổi. Trong Java 15+, hãy dùng **`EdDSAParameterSpec` để chỉ định mode/context**, đưa đúng **message bytes gốc** vào engine và kiểm thử signature **cùng lẫn khác mode/context** để bảo đảm tính tương tác và an toàn.
