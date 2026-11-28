# Mã hóa có xác thực và quản lý nonce với JCA/JCE trong Java 27

Trong chương **Bảo mật ứng dụng Java**, việc “mã hóa một chuỗi thành dữ liệu không đọc được” chưa đủ để bảo vệ thông tin. Ứng dụng còn phải phát hiện khi ciphertext, dữ liệu mô tả hoặc ngữ cảnh sử dụng đã bị sửa đổi. **Authenticated Encryption with Associated Data (AEAD)** giải quyết đồng thời hai mục tiêu: **bí mật của plaintext** và **tính toàn vẹn/xác thực đối với ciphertext cùng dữ liệu liên kết**.

Java 27 có những API hiện hành của **Java Cryptography Architecture (JCA)** và **Java Cryptography Extension (JCE)** để triển khai AEAD: `Cipher`, `SecretKey`, `KeyGenerator`, `SecureRandom`, `GCMParameterSpec`, `AEADBadTagException` và các cơ chế liên quan. Hai lựa chọn có thể dùng là **AES-GCM** và **ChaCha20-Poly1305**. Bài học tập trung vào AES-GCM vì có API rõ ràng và được hỗ trợ rộng rãi trong JDK.

**Thông điệp quan trọng nhất:** với AES-GCM, **không bao giờ mã hóa hai thông điệp bằng cùng cặp `(key, nonce)`**. Ngay cả khóa AES đủ mạnh và authentication tag dài cũng không bù đắp được sai sót này. Nonce có thể được lưu công khai cạnh ciphertext, nhưng **tính duy nhất trong phạm vi từng khóa** là một ràng buộc bảo mật bắt buộc.

> Bài học tuân theo Java 27 và kiến thức mật mã hiện hành, không dựa vào `DES`, `RC4`, `ECB`, finalization hoặc những hướng dẫn mã hóa không xác thực đã lỗi thời. Đoạn mã minh họa dùng JCA/JCE chuẩn, không tự triển khai thuật toán mật mã. Ví dụ tạo khóa mới trong bộ nhớ chỉ để thử nghiệm; hệ thống lưu trữ thật cần giải pháp quản lý khóa bền vững.

## 1. AEAD giải quyết những vấn đề nào?

Một phép mã hóa chỉ bảo đảm **confidentiality** không nhất thiết bảo đảm ciphertext chưa bị chỉnh sửa. Với AEAD, người nhận chỉ chấp nhận plaintext khi **authentication tag** được kiểm tra thành công dưới đúng khóa, nonce và dữ liệu liên kết.

```text
                       ENCRYPT
Key K ----------------------+
Nonce N --------------------+--> AEAD Encrypt ---> Ciphertext C + Tag T
Plaintext P ----------------+
AAD A ----------------------+

                       DECRYPT
Key K ----------------------+
Nonce N --------------------+--> AEAD Decrypt/Verify ---> P hoặc FAIL
Ciphertext C + Tag T -------+
AAD A ----------------------+
```

Kết quả xác thực chỉ có ý nghĩa khi **khóa bí mật được quản lý an toàn** và các ràng buộc về nonce/độ dài/giao thức được tuân thủ.

| Thành phần | Có cần bí mật? | Có cần nguyên vẹn? | Vai trò |
| --- | --- | --- | --- |
| `SecretKey` | **Có** | **Có** | Khóa dùng cho mã hóa và xác thực |
| Plaintext | Thường có | Có | Nội dung cần bảo vệ |
| Nonce/IV | **Không** | Phải dùng đúng giá trị với ciphertext | Phân biệt từng lần mã hóa cùng khóa |
| Ciphertext | Không | **Có, nhờ tag** | Dữ liệu đã mã hóa |
| Authentication tag | Không | **Có** | Dùng để phát hiện thông điệp không hợp lệ |
| AAD | Không bắt buộc bí mật | **Có, nhờ tag** | Ràng buộc metadata/ngữ cảnh vào ciphertext |

Điều AEAD **không tự cung cấp**:

- Không chống **replay**: attacker có thể gửi lại toàn bộ gói hợp lệ cũ trừ khi ứng dụng kiểm tra message ID, sequence hoặc freshness.
- Không tự cung cấp **chữ ký số** hay bằng chứng không thể chối bỏ. Nếu nhiều bên chia sẻ cùng khóa, việc giải mã thành công không phân biệt chắc chắn bên nào đã tạo thông điệp.
- Không bảo vệ thông tin bị lộ qua **độ dài ciphertext**, thời gian truy cập, tên file hoặc metadata không được mã hóa.
- Không thay thế **authorization**, kiểm tra quyền tenant, quản lý khóa hoặc bảo vệ thiết bị.

## 2. AES-GCM là gì? Tag và nonce hoạt động thế nào?

**AES-GCM** kết hợp AES ở chế độ counter với cơ chế xác thực Galois. Khi dùng JCE, transformation được viết rõ:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

Tên `NoPadding` không có nghĩa “không có tag” hoặc “không cần cấu hình”. Nó chỉ xác định transformation. **Tag** vẫn được tạo và kiểm tra như một phần thiết yếu của GCM.

Những tham số thường dùng:

| Thành phần | Cấu hình minh họa |
| --- | --- |
| Thuật toán | `AES/GCM/NoPadding` |
| Khóa AES | 128 hoặc 256 bit |
| Nonce/IV | **96 bit = 12 byte**, nếu giao thức không có yêu cầu khác |
| Authentication tag | **128 bit = 16 byte** |
| AAD | Chuỗi byte tùy chọn; phải giống nhau ở encrypt/decrypt |

NIST SP 800-38D khuyến nghị IV 96 bit cho GCM vì thuận tiện cho phép tính nội bộ và thiết kế giao thức. Trong các ví dụ dưới đây, tag dài 128 bit để tránh giảm độ an toàn xác thực.

### 2.1. Ciphertext và tag trong Java

Với provider thường dùng của JDK, `Cipher.doFinal(plaintext)` trong `AES/GCM/NoPadding` trả về:

```text
ciphertext bytes || authentication tag bytes
```

Khi giải mã, `Cipher.doFinal(ciphertextAndTag)` **xác minh tag** trước khi chấp nhận kết quả. Bạn **không cần và không nên** tự tách tag rồi so sánh bằng `equals()` hoặc viết hàm kiểm tra MAC riêng.

Ví dụ nếu plaintext dài 20 byte, với tag 16 byte, kết quả `doFinal` của GCM thường dài 36 byte. Nonce **không nằm mặc định trong byte[] trả về**, nên ứng dụng phải lưu/truyền nonce cùng ciphertext bằng một định dạng có contract rõ ràng.

### 2.2. `GCMParameterSpec`: tag tính theo bit, nonce theo byte

```java
byte[] nonce = new byte[12];
secureRandom.nextBytes(nonce);

GCMParameterSpec spec = new GCMParameterSpec(128, nonce);
```

**`128` là số bit của tag**, không phải 128 byte. `nonce` có độ dài 12 byte. Đảo lẫn đơn vị hoặc dùng IV dài tùy tiện là lỗi thường gặp.

`GCMParameterSpec` cung cấp các tham số cho operation, không phải trình quản lý phân phối nonce tự động toàn hệ thống. **Caller chịu trách nhiệm về tính duy nhất** của nonce trên mọi lần mã hóa với cùng khóa.

## 3. Sinh khóa AES bằng `KeyGenerator`

Không tạo khóa từ một chuỗi dễ đoán, password viết thẳng trong source hoặc một seed cố định:

```java
// KHÔNG AN TOÀN:
// byte[] raw = "my-secret-password".getBytes(UTF_8);
// SecretKey key = new SecretKeySpec(raw, "AES");
```

Tạo khóa ngẫu nhiên đúng bằng API mật mã:

```java
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import java.security.SecureRandom;

KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());

SecretKey key = generator.generateKey();
```

AES-256 là lựa chọn thường dùng khi có yêu cầu bảo vệ dài hạn; AES-128 cũng là thuật toán mạnh và được Java SE hỗ trợ. Chọn theo threat model, chính sách tổ chức, tính tương thích provider/HSM và yêu cầu tuân thủ.

Trong ví dụ này, `key` chỉ sống trong bộ nhớ. Nếu chương trình **khởi động lại và sinh khóa mới**, những ciphertext mã hóa bằng khóa cũ **không thể giải mã** nếu không có cơ chế lưu/phục hồi khóa. **Không dùng cách sinh khóa mới mỗi request hoặc mỗi lần khởi động để bảo vệ dữ liệu cần lưu lâu dài**.

### 3.1. SecretKey không đồng nghĩa key đã được bảo vệ

`SecretKey` là abstraction cung cấp khóa cho JCE. Trong một số provider, key material có thể được export qua `getEncoded()`; trong HSM/keystore không xuất khóa, điều này có thể khác.

Những quy tắc thực tế:

1. Không hard-code khóa trong repository, container image hoặc tài liệu.
2. Không log `SecretKey`, dữ liệu `getEncoded()`, mật khẩu hay key material.
3. Ưu tiên KMS, HSM, vault hoặc keystore có quyền truy cập và audit phù hợp.
4. Chỉ cấp quyền mã hóa/giải mã cho thành phần thực sự cần.
5. Có kế hoạch rotation, backup/restore an toàn và thu hồi khóa.
6. Phân biệt **data encryption key (DEK)** với **key encryption key (KEK)** khi dùng envelope encryption.

## 4. `SecureRandom` và nonce: giá trị công khai nhưng phải duy nhất

Trong một ứng dụng mức tải vừa với hạn mức sử dụng khóa được quản lý, có thể tạo **nonce ngẫu nhiên 96 bit** bằng `SecureRandom`:

```java
import java.security.SecureRandom;

SecureRandom random = new SecureRandom();
byte[] nonce = new byte[12];
random.nextBytes(nonce);
```

`SecureRandom` là nguồn byte ngẫu nhiên phù hợp cho mục đích mật mã. **Không** dùng `java.util.Random`, `ThreadLocalRandom`, `Math.random()` hoặc một thời gian timestamp đơn giản để sinh nonce/key cho một giao thức AEAD tự thiết kế.

Nonce **không phải secret**: có thể đặt nó ở đầu bản mã để người nhận giải mã. Tuy nhiên, đối với **cùng khóa**, các lần mã hóa phải có nonce khác nhau theo chính sách bảo đảm tính duy nhất.

### 4.1. Random 96 bit có phải chắc chắn không trùng?

**Không.** Số lượng giá trị nonce 96 bit là `2^96`; nếu sinh độc lập và đều, xác suất có ít nhất một cặp trùng sau `q` lần xấp xỉ khi `q` còn đủ nhỏ:

\[
P(\text{collision}) \approx \frac{q(q-1)}{2^{97}}.
\]

Đây là ước lượng *birthday bound*, không phải bảo đảm tuyệt đối. Khi tải và số node tăng, phải tính **tổng số lần mã hóa sử dụng cùng khóa**, không chỉ số lần của một JVM.

Theo hướng dẫn NIST SP 800-38D hiện hành, với cơ chế nonce ngẫu nhiên, **tổng số lần gọi mã hóa GCM trên cùng khóa không được vượt `2^32`**, cùng các ràng buộc khác về độ dài và khả năng lặp IV. Đó là **giới hạn trên**, không phải mục tiêu phải dùng đến mới xoay khóa. Hệ thống thường đặt ngưỡng thực tế thấp hơn theo threat model, tổ chức, tải và rủi ro.

### 4.2. Nonce phải duy nhất cho mỗi lần **mã hóa**

Ví dụ sai:

```java
byte[] nonce = new byte[12]; // Toàn số 0
GCMParameterSpec spec = new GCMParameterSpec(128, nonce);

// Dùng lại spec + cùng key để ENCRYPT nhiều message là SAI.
```

Việc nonce được dùng một lần để **giải mã lại ciphertext cũ** là bình thường: người nhận phải dùng chính nonce đã được mã hóa với thông điệp đó. Ràng buộc nghiêm ngặt là **không tạo nhiều ciphertext mới bằng cùng `(key, nonce)`**.

### 4.3. Tái sử dụng nonce nguy hiểm như thế nào?

Với AES-GCM, sử dụng lại một `(key, nonce)` có thể làm lộ quan hệ giữa plaintext do tái sử dụng keystream và phá vỡ tính an toàn xác thực; có thể dẫn đến khả năng làm giả thông điệp. Đây là lỗi **nghiêm trọng ở mức thiết kế**, không phải chỉ giảm entropy một chút.

**Không sửa bằng cách tăng độ dài khóa AES**, đổi tag length hay thêm một AAD tùy ý trong khi vẫn lặp nonce. Cần sửa **chiến lược cấp phát nonce** và xử lý khóa có thể đã bị sử dụng sai.

## 5. Mã hóa AES-GCM với JCA/JCE

Các bước chuẩn:

1. Có một `SecretKey` hợp lệ.
2. Cấp một nonce mới, duy nhất trong phạm vi khóa.
3. Tạo `Cipher` theo transformation chính xác.
4. `init(ENCRYPT_MODE, key, new GCMParameterSpec(128, nonce))`.
5. Gọi `updateAAD(...)` nếu có dữ liệu liên kết.
6. `doFinal(plaintext)` để lấy ciphertext kèm tag.
7. Lưu **nonce + ciphertext/tag + metadata định dạng/khóa** theo format rõ ràng.

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
    Cipher.ENCRYPT_MODE,
    key,
    new GCMParameterSpec(128, nonce)
);

byte[] aad = "invoice:42".getBytes(StandardCharsets.UTF_8);
cipher.updateAAD(aad);

byte[] plaintext =
    "Total = 1200".getBytes(StandardCharsets.UTF_8);
byte[] sealed = cipher.doFinal(plaintext);
```

`sealed` chứa bản mã cùng tag, **không chứa `nonce`** trong cách gọi này. Ví dụ ngắn tập trung vào một lần mã hóa; bài học hoàn chỉnh ở mục 15 sẽ đóng gói nonce cùng header để người nhận giải mã được.

### 5.1. Không dùng lại cùng `Cipher` cho mã hóa lần tiếp theo mà giữ IV cũ

Theo Javadoc, một `Cipher` AEAD có thể không tự reset thành trạng thái cho phép mã hóa tiếp khi `doFinal` xong, nhằm tránh phá yêu cầu uniqueness. Ngay cả khi một provider cho phép reset theo cách nào đó, vẫn phải dùng **nonce mới**.

Đối với ứng dụng server, tạo hoặc khởi tạo lại `Cipher` theo từng operation với tham số mới. Không dùng một instance `Cipher` mutable chung cho nhiều thread mà không có thiết kế thread safety thích hợp.

## 6. Giải mã và kiểm tra tag bằng `AEADBadTagException`

Để giải mã cần biết **cùng khóa**, **nonce đã dùng cho mã hóa**, **cùng AAD** (nếu có), và ciphertext/tag nguyên vẹn.

```java
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
    Cipher.DECRYPT_MODE,
    key,
    new GCMParameterSpec(128, nonce)
);
cipher.updateAAD(aad);

try {
    byte[] recovered = cipher.doFinal(sealed);
    // Chỉ xử lý plaintext sau khi xác thực thành công.
} catch (AEADBadTagException ex) {
    // Không chấp nhận dữ liệu; không trả plaintext một phần.
    throw new SecurityException("Unable to authenticate encrypted data", ex);
}
```

Trong một số trường hợp lỗi cấu hình, format hay provider, có thể nhận exception khác thuộc `GeneralSecurityException`. Vì thế:

- Phân loại **malformed envelope** (dữ liệu sai định dạng) trước khi gọi JCE.
- Phân loại **authentication failure** khi kiểm tra tag thất bại.
- Không trả dữ liệu chưa xác thực cho tầng nghiệp vụ.
- Không log ciphertext/plaintext/key/AAD nhạy cảm chỉ để chẩn đoán.
- Không tiết lộ thông báo lỗi quá chi tiết cho caller không đáng tin.

### 6.1. Tag thất bại **không nói chính xác vì sao**

Các nguyên nhân có thể bao gồm:

- Ciphertext hoặc tag bị sửa.
- Nonce sai.
- AAD sai, thiếu hoặc sai thứ tự byte.
- Khóa sai hoặc chọn nhầm key ID.
- Payload bị cắt ngắn hoặc hỏng trong truyền tải.
- Format/encoding khác giữa hai phía.

Không nên khẳng định “bị hacker chỉnh sửa” chỉ dựa vào `AEADBadTagException`. Nên báo lỗi xác thực chung và điều tra nguyên nhân trong log/telemetry phù hợp.

### 6.2. Decryption streaming phải kiểm soát plaintext chưa xác thực

Nếu dùng `Cipher.update(...)`, một provider có thể trả một phần plaintext **trước khi đến bước xác minh tag cuối cùng**. Với dữ liệu không tin cậy, không được phát tán/ghi commit những byte đó cho hệ thống khác như đã được xác thực.

Chọn API/buffer chiến lược để **chỉ xuất bản plaintext sau khi `doFinal` xác minh thành công**; với file lớn cần thiết kế lưu tạm/quarantine và chỉ đưa thành file chính thức sau khi tag hợp lệ. Đừng giả định mọi crypto stream wrapper tự cung cấp bảo đảm “không có plaintext nào đến trước khi xác thực”.

## 7. AAD: ràng buộc ciphertext vào ngữ cảnh

**Additional Authenticated Data (AAD)** là dữ liệu tham gia xác thực nhưng **không được mã hóa**. Nó phù hợp cho metadata cần toàn vẹn, chẳng hạn:

- `tenantId` hoặc phạm vi chủ thể được phép đọc.
- `recordId`, `documentId` hay loại bản ghi.
- Phiên bản định dạng, tên thuật toán và key identifier.
- Mục đích sử dụng (*domain separation*), ví dụ `"user-profile"` khác `"payment-token"`.

Nếu lấy cùng ciphertext nhưng gắn sang record khác rồi giải mã với AAD của record mới, tag phải không hợp lệ.

```java
// Khi encrypt:
cipher.updateAAD(recordContextBytes);

// Khi decrypt:
cipher.updateAAD(theSameRecordContextBytes);
```

**AAD phải có cùng byte sequence** ở hai phía. Kết hợp chuỗi mơ hồ có thể gây lỗi domain binding:

```java
// DỄ MƠ HỒ nếu không có phân định độ dài:
// tenant + ":" + recordId
```

Nếu input có ký tự `:` hoặc các trường có encoding/normalization khác nhau, nhiều cặp giá trị có thể tạo cùng chuỗi. Nên dùng serialization **có phiên bản và ranh giới trường rõ ràng**: length-prefix, format canonical hoặc một giao thức chuẩn được kiểm tra.

### 7.1. AAD không bí mật

Nếu AAD chứa `tenantId` hay `documentId`, những giá trị này không được giấu chỉ bằng cách đưa vào `updateAAD`. Nếu metadata đó cũng cần bí mật, đưa nó vào **plaintext** trước khi mã hóa; nếu còn cần ràng buộc ngoài ciphertext, có thể cân nhắc cơ chế kết hợp với AAD thích hợp.

### 7.2. Thứ tự gọi API rất quan trọng

Với AES-GCM, **cung cấp toàn bộ AAD trước khi gọi `update` hoặc `doFinal` xử lý plaintext/ciphertext**:

```java
cipher.init(Cipher.ENCRYPT_MODE, key, params);
cipher.updateAAD(header);
cipher.updateAAD(context);
byte[] sealed = cipher.doFinal(plaintext);
```

Gọi `updateAAD` sau khi bắt đầu xử lý dữ liệu có thể ném `IllegalStateException` theo contract. Mã hóa và giải mã phải dùng đúng chuỗi AAD cùng thứ tự.

## 8. Thiết kế định dạng lưu ciphertext (envelope)

Bản mã **không tự mang đầy đủ thông tin giải mã**. Một hệ thống lưu trữ lâu dài nên xác định format có phiên bản:

```text
+-----------+----------+----------+----------+---------------------+
| magic     | version  | keyId    | nonce    | ciphertext || tag   |
+-----------+----------+----------+----------+---------------------+
```

Các thành phần:

| Trường | Mục đích |
| --- | --- |
| Magic/version | Phát hiện định dạng không hỗ trợ và định tuyến parser |
| Algorithm ID | Xác định AEAD suite nếu hệ thống có nhiều thuật toán |
| Key ID | Chọn đúng khóa giải mã trong keyring/KMS |
| Nonce | Khôi phục tham số dùng khi mã hóa |
| Ciphertext + tag | Nội dung có xác thực |
| AAD external | Ràng buộc vào tenant/record/context bên ngoài |

Magic/version/key ID/nonce **không phải bí mật**. Nếu là metadata quan trọng về mặt ngữ nghĩa, nên cho nó tham gia AAD để sau khi parse sẽ được **xác thực**, tránh nhầm lẫn chéo định dạng hoặc cross-protocol.

### 8.1. Không cho người gửi điều khiển key lookup vô hạn

Key ID từ envelope chưa được xác thực trước khi decrypt; nó chỉ là **gợi ý chọn khóa**. Vì vậy:

1. Validate chiều dài và cấu trúc key ID trước khi tra cứu.
2. Chỉ cho phép key ID thuộc keyring/domain được cấu hình.
3. Hạn chế request rate để tránh key lookup amplification.
4. Xác thực envelope/AAD với khóa đã chọn rồi mới chấp nhận dữ liệu.
5. Không đưa path/URL từ key ID vào một request mạng tự do.

Nếu một key đã được rút khỏi quyền giải mã theo chính sách, việc nhìn thấy ID của nó trong ciphertext không tự cấp quyền truy cập lại.

## 9. Quản lý nonce bằng bộ đếm và định danh node

Khi khối lượng mã hóa lớn hoặc yêu cầu đảm bảo tránh collision một cách định danh, có thể sử dụng **nonce deterministic 96 bit** với phân vùng rõ ràng. Ví dụ kiến trúc minh họa:

```text
Nonce 96 bit = fixed field 32 bit || invocation field 64 bit
                node/namespace          counter
```

Theo NIST SP 800-38D, deterministic construction có fixed field phân biệt device/context và invocation field không được lặp trong context đó. Đây là **thiết kế giao thức**, không phải cứ nối `nodeId` với một `long` là tự động an toàn.

Những yêu cầu triển khai:

- Fixed field phải **duy nhất giữa các instance dùng cùng khóa**, không cấp trùng khi autoscaling hoặc khôi phục từ backup.
- Counter phải **đơn điệu và không tái sử dụng**, kể cả sau crash, rollback hoặc failover.
- Nếu một counter value đã được cấp/tiềm ẩn có thể dùng, không được cấp lại sau khôi phục.
- Một key không được dùng với hai cơ chế cấp nonce không có phân vùng duy nhất rõ ràng.
- Phải **ngăn overflow** và xoay khóa/namespace trước khi exhausted.
- Hệ thống phân tán cần bộ cấp phát dải counter có transaction/lease bền vững hoặc một cơ chế chứng minh uniqueness tương đương.

### 9.1. Vì sao `AtomicLong` riêng trong mỗi JVM là chưa đủ?

```java
// MINH HỌA THIẾU ĐIỀU KIỆN AN TOÀN, KHÔNG DÙNG CHO PRODUCTION:
static final java.util.concurrent.atomic.AtomicLong COUNTER =
    new java.util.concurrent.atomic.AtomicLong();
```

Dù `AtomicLong` tránh race condition **trong một process**, sau restart nó có thể bắt đầu lại từ 0. Hai instance dùng cùng khóa cũng có thể cùng cấp nonce 0, 1, 2...

Nếu chọn hướng counter, phải **quản trị trạng thái cấp phát xuyên process và restart**. Nên dùng thư viện/giao thức đã được đánh giá hoặc KMS/encryption service có chính sách nonce rõ thay vì tự viết một nonce generator dựa trên `System.currentTimeMillis()`.

### 9.2. Random nonce và deterministic nonce: chọn một chính sách nhất quán

NIST SP 800-38D đặt yêu cầu đối với **phương án xây dựng IV** cho từng khóa, độ dài IV và các giới hạn invocation. Đừng tự phát kết hợp “một vài node random, một vài node counter” với cùng key mà không chứng minh toàn cục không trùng.

| Chiến lược | Ưu điểm | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Random 96-bit từ CSPRNG | Đơn giản, không lưu counter từng message | Collision xác suất; ngân sách invocation toàn khóa; nhiều node |
| Deterministic fixed-field + counter | Có thể chứng minh uniqueness nếu state đúng | Cấp node ID, crash persistence, restore, overflow |
| Dịch vụ cấp nonce tập trung | Có thể quản trị global sequence | Availability, throughput, atomicity, scope của khóa |
| Sinh khóa dữ liệu mới theo message/batch | Giảm số nonce dùng trên cùng DEK | Key lifecycle/DEK wrapping và metadata phức tạp hơn |

Không có phương án tối ưu cho mọi hệ thống. Quy mô, hạ tầng, lưu trữ bền, khả năng khôi phục và mô hình key rotation quyết định cách triển khai.

## 10. Multi-instance, backup, restore và hệ quả bảo mật

Rất nhiều lỗi nonce xuất hiện khi **hệ thống vận hành**, không phải ở một đoạn gọi `Cipher` đơn lẻ.

### 10.1. Khởi động lại service

Với counter-based nonce, nếu state lưu chỉ trong heap thì restart có thể khiến nonce cũ được dùng lại với cùng khóa. Giải pháp phải nằm trong quản lý trạng thái bền vững hoặc key rotation có kiểm soát.

### 10.2. Database restore

Khôi phục bản backup database có thể đưa counter về giá trị **thấp hơn những giá trị đã dùng** trước đó, trong khi ciphertext được gửi ra ngoài/backup ở nơi khác vẫn tồn tại. Cần thiết kế chống rollback: cấp phát dải cao hơn một cách bền vững, quản lý epoch/key khác hoặc xác định rõ chính sách khôi phục.

### 10.3. Horizontal scaling

Nếu có 10 service instances dùng cùng một data encryption key, “mỗi instance random 96 bit” phải được tính trong **một ngân sách nonce chung**, không phải 10 ngân sách tách biệt. Với deterministic nonce, fixed fields phải duy nhất cho từng instance/context có cùng khóa.

### 10.4. Khóa mới là ranh giới namespace mới

Nonce có thể trùng giá trị giữa **hai khóa độc lập** mà không tạo sự cố “same key, same nonce”. Nhưng ứng dụng phải chắc chắn khóa được tạo độc lập và việc ánh xạ key ID đúng; không coi việc đổi một tên `keyId` nhưng vẫn dùng raw key cũ là rotation mật mã.

## 11. Giới hạn dữ liệu mỗi operation và vòng đời khóa

AES-GCM không phải một phép mã hóa có thể nhận plaintext vô hạn hoặc một khóa dùng mãi mãi mà không cần tính toán.

Những giới hạn cần theo dõi:

- **Độ dài plaintext và AAD** cho mỗi invocation.
- **Tổng dữ liệu đã mã hóa bằng một khóa**.
- **Số lần mã hóa/nonce** trên một khóa.
- **Độ dài authentication tag** và yêu cầu chống giả mạo.
- **Chiến lược nonce** và xác suất collision.
- **Thời gian tồn tại và quyền truy cập khóa**.

NIST SP 800-38D nêu các giới hạn cụ thể theo mode/construction; không nên suy ra giới hạn sử dụng chỉ từ kích thước khóa AES hoặc tag. Hệ thống thực cần **enforce** ngân sách bằng metrics/configuration và xoay khóa trước ngưỡng an toàn.

Đối với dữ liệu rất lớn, nên dùng một giao thức **chunked AEAD** đã được phân tích với nonce/sequence riêng cho từng chunk, ràng buộc vị trí và chống cắt/đổi thứ tự. **Không đơn thuần** chia plaintext thành các chunk rồi dùng cùng nonce với cùng khóa cho tất cả chunk.

## 12. Không dùng các chế độ mã hóa không xác thực làm mặc định

Với ứng dụng mới, ưu tiên AEAD thay vì viết:

```java
// KHÔNG DÙNG CHO THIẾT KẾ MỚI:
// Cipher.getInstance("AES/ECB/PKCS5Padding");
```

ECB để lộ cấu trúc dữ liệu và không cung cấp xác thực. CBC/CTR riêng lẻ cũng không xác thực nội dung; nếu không có MAC đúng kiểu encrypt-then-MAC, attacker có thể sửa ciphertext mà ứng dụng không phát hiện theo cách an toàn.

Các sai lầm khác:

- “Mã hóa AES rồi hash plaintext” không phải một AEAD protocol đúng.
- Dùng `String.hashCode()` hoặc CRC32 làm authentication tag.
- So sánh tag tự viết qua `String.equals`.
- Dùng một `Cipher` mutable chung cho tất cả request.
- Bỏ qua kết quả xác minh tag vì muốn “khôi phục một phần dữ liệu”.

Không tự thiết kế một chế độ mã hóa mới khi đã có AEAD chuẩn từ JCE.

## 13. ChaCha20-Poly1305: AEAD thay thế AES-GCM

Java SE 27 cũng hỗ trợ transformation:

```java
Cipher.getInstance("ChaCha20-Poly1305");
```

ChaCha20-Poly1305 là AEAD dùng khóa 256 bit, nonce 96 bit và tag 128 bit theo profile tiêu chuẩn. Có thể hữu ích trong những môi trường mà AES hardware acceleration không phải điểm mạnh hoặc giao thức yêu cầu thuật toán này.

Mẫu API cơ bản:

```java
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

SecretKey key = KeyGenerator.getInstance("ChaCha20").generateKey();

byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));

cipher.updateAAD("context".getBytes(java.nio.charset.StandardCharsets.UTF_8));
byte[] sealed = cipher.doFinal(
    "hello".getBytes(java.nio.charset.StandardCharsets.UTF_8)
);
```

**Lưu ý quan trọng:**

- `IvParameterSpec` dùng cho nonce của transformation `ChaCha20-Poly1305` trong ví dụ; **không** dùng nhầm `ChaCha20ParameterSpec` (nonce + counter) dành cho transformation `ChaCha20` thông thường.
- Vẫn bắt buộc quản lý **nonce duy nhất với từng khóa**. Chuyển từ AES-GCM sang ChaCha20-Poly1305 không sửa được lỗi tái sử dụng nonce.
- Ciphertext/tag và thuật toán phải có metadata đúng; không thể giải mã “đoán” từ một mảng byte nếu không biết suite, nonce và key.
- Lựa chọn thuật toán còn phụ thuộc compliance, FIPS provider, hệ thống nhận dữ liệu và hiệu năng đo được.

## 14. Authentication failure, replay và key separation

### 14.1. Xác thực ciphertext không tương đương xác thực người dùng

Nếu cả service A và service B có cùng symmetric key, ciphertext hợp lệ chỉ chứng minh một bên có khả năng dùng khóa đã tạo nó. Nó không chứng minh một actor cụ thể đã ký hoặc ủy quyền giao dịch.

Nếu cần non-repudiation hoặc chứng thực danh tính gửi, nghiên cứu chữ ký số hoặc các giao thức xác thực danh tính phù hợp.

### 14.2. AEAD không tự ngăn replay

Một ciphertext/tag hợp lệ cũ có thể được gửi lại nguyên vẹn; tag vẫn hợp lệ. Khi ứng dụng cần chống replay:

1. Gắn message ID/sequence/time-window vào AAD hoặc payload đã xác thực.
2. Duy trì trạng thái đã xử lý hoặc monotonic sequence đúng phạm vi.
3. Thực thi chính sách chống replay trước khi áp dụng side effect.
4. Xử lý clock skew, retry hợp pháp và idempotency của nghiệp vụ.

Không coi “nonce unique khi encrypt” là thay thế cho replay cache: nonce uniqueness đảm bảo an toàn mật mã khi **tạo** thông điệp, còn replay prevention là chính sách khi **nhận** thông điệp.

### 14.3. Domain separation và tách khóa

Không nên sử dụng một khóa cho nhiều mục đích khó phân biệt mà không có thiết kế bảo mật: ciphertext cho profile, payment token và session token có ngữ cảnh và chính sách lifetime khác nhau.

Có thể tách key theo tenant, purpose hoặc version bằng KMS/DEK riêng, hoặc dùng KDF đúng chuẩn với domain labels nếu kiến trúc yêu cầu. **Không tự cắt chuỗi từ password hoặc hash không có cấu trúc** để tạo nhiều khóa.

## 15. Ví dụ hoàn chỉnh: AES-GCM envelope có AAD và kiểm tra sửa đổi

Chương trình sau dùng một **định dạng nhỏ để học và test**, không phải file format sản xuất. Nó lưu:

```text
4 byte magic = "AGCM"
1 byte version = 1
12 byte nonce ngẫu nhiên
N byte ciphertext || 16 byte tag
```

**Magic, version và nonce đều tham gia AAD**, cùng một `context` do ứng dụng cung cấp. Dữ liệu context trong ví dụ là chuỗi cố định ổn định; khi làm thật hãy dùng encoding canonical có version, không tự nối input mơ hồ.

Lưu mã sau thành `AesGcmEnvelopeDemo.java` để thử độc lập:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Objects;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmEnvelopeDemo {
    private static final byte[] MAGIC = { 'A', 'G', 'C', 'M' };
    private static final byte VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int HEADER_BYTES = MAGIC.length + 1 + NONCE_BYTES;
    private static final SecureRandom RNG = new SecureRandom();

    private AesGcmEnvelopeDemo() { }

    static SecretKey newDemoKey() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] context)
            throws GeneralSecurityException {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(plaintext, "plaintext");
        Objects.requireNonNull(context, "context");

        // Một nonce MỚI cho mỗi lần encrypt với cùng key.
        // Chỉ dùng random-nonce policy trong ngân sách GCM đã quản trị.
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        byte[] header = ByteBuffer.allocate(HEADER_BYTES)
            .put(MAGIC)
            .put(VERSION)
            .put(nonce)
            .array();

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(header);
        cipher.updateAAD(context);

        byte[] ciphertextWithTag = cipher.doFinal(plaintext);

        return ByteBuffer.allocate(header.length + ciphertextWithTag.length)
            .put(header)
            .put(ciphertextWithTag)
            .array();
    }

    static byte[] decrypt(SecretKey key, byte[] envelope, byte[] context)
            throws GeneralSecurityException {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(envelope, "envelope");
        Objects.requireNonNull(context, "context");

        if (envelope.length < HEADER_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Envelope too short");
        }

        byte[] header = Arrays.copyOfRange(envelope, 0, HEADER_BYTES);
        byte[] magic = Arrays.copyOfRange(header, 0, MAGIC.length);

        if (!Arrays.equals(magic, MAGIC) || header[MAGIC.length] != VERSION) {
            throw new IllegalArgumentException("Unsupported envelope format");
        }

        byte[] nonce = Arrays.copyOfRange(
            header, MAGIC.length + 1, HEADER_BYTES
        );
        byte[] ciphertextWithTag = Arrays.copyOfRange(
            envelope, HEADER_BYTES, envelope.length
        );

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(header);
        cipher.updateAAD(context);

        // doFinal chỉ trả plaintext sau khi tag được xác minh.
        return cipher.doFinal(ciphertextWithTag);
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = newDemoKey();
        byte[] context =
            "purpose=invoice;record=42".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext =
            "Amount: 1200".getBytes(StandardCharsets.UTF_8);

        byte[] envelope = encrypt(key, plaintext, context);
        byte[] recovered = decrypt(key, envelope, context);

        System.out.println(new String(recovered, StandardCharsets.UTF_8));
        // Amount: 1200

        // Đổi một byte ở phần ciphertext/tag.
        byte[] tampered = envelope.clone();
        tampered[tampered.length - 1] ^= 1;

        try {
            decrypt(key, tampered, context);
            throw new AssertionError("Tampered ciphertext accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampering detected");
        }

        // Cùng ciphertext nhưng context khác cũng bị từ chối.
        try {
            decrypt(
                key, envelope,
                "purpose=invoice;record=43".getBytes(StandardCharsets.UTF_8)
            );
            throw new AssertionError("Wrong AAD accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Context mismatch detected");
        }
    }
}
```

Kết quả minh họa:

```text
Amount: 1200
Tampering detected
Context mismatch detected
```

### 15.1. Điều gì được bảo đảm trong ví dụ?

- `newDemoKey()` tạo khóa AES-256 mới cho chương trình demo.
- Mỗi lần encrypt gọi CSPRNG để tạo nonce 96 bit mới theo **chính sách random nonce**.
- Định dạng lưu nonce và metadata cạnh ciphertext.
- Header và `context` tham gia xác thực bằng `updateAAD`.
- `decrypt` kiểm tra format/độ dài tối thiểu trước khi khởi tạo Cipher.
- Nếu ciphertext/tag hoặc AAD bị sửa, `doFinal` từ chối.
- Không gọi `Cipher.update` để công bố plaintext chưa xác thực.
- Mỗi operation có `Cipher` riêng, tránh chia sẻ mutable state giữa thread.

### 15.2. Điều gì **chưa được bảo đảm** cho production?

1. **Chưa có durable key management:** khóa biến mất khi process kết thúc.
2. **Chưa có key ID và key rotation:** format chỉ chứa version, không chọn khóa từ keyring.
3. **Chưa enforce ngân sách nonce toàn bộ các node:** cần giới hạn invocation/metrics/rotation hoặc một chiến lược nonce deterministic có trạng thái.
4. **Chưa giới hạn kích thước envelope từ input không tin cậy:** có nguy cơ memory exhaustion nếu nhận byte[] rất lớn.
5. **Chưa chống replay:** gói hợp lệ cũ vẫn được giải mã.
6. **Context chỉ minh họa:** chuỗi nối từ input thực tế phải có encoding canonical, phân định trường và version.
7. **Chưa có audit/access control cho khóa** và chính sách xử lý sự cố.
8. **Chưa có interoperability test** với các implementation/provider/language khác.

Đừng copy ví dụ rồi coi đó là “một thư viện mã hóa production hoàn chỉnh”. Nó được thiết kế để thấy chính xác các bước mật mã và các trách nhiệm còn lại.

## 16. Tests bắt buộc cho AEAD và nonce

Một bộ kiểm thử tối thiểu cần có cả **happy path** và **negative cases**:

| Test | Kỳ vọng |
| --- | --- |
| Encrypt rồi decrypt với cùng key/nonce/AAD | Khôi phục đúng plaintext |
| Plaintext rỗng | Mã hóa và giải mã hợp lệ; vẫn có tag |
| Payload binary không phải UTF-8 | Dữ liệu byte được giữ nguyên |
| Đổi một bit ciphertext | Authentication failure |
| Đổi một bit tag | Authentication failure |
| Dùng sai khóa | Authentication failure |
| Dùng sai AAD | Authentication failure |
| Đổi nonce đã lưu | Authentication failure |
| Header format/version sai | Reject trước giải mã hoặc thất bại có kiểm soát |
| Envelope bị cắt ngắn | Reject; không xuất plaintext một phần |
| Nhiều lần encrypt cùng key | Nonce được cấp theo policy duy nhất; kiểm tra race và giới hạn |
| Nhiều thread mã hóa đồng thời | Không dùng chung Cipher không thread-safe; tránh nonce duplicate |
| Restart/crash/restore | Không tái sử dụng nonce deterministic đã cấp |
| Multi-node/failover | Không trùng fixed field/counter giữa node cùng key |
| Key rotation | Dữ liệu cũ vẫn giải mã theo chính sách key retention |
| Replay gói hợp lệ | Bị chặn ở tầng protocol nếu nghiệp vụ yêu cầu |

### 16.1. Không chứng minh nonce “an toàn” bằng vài nghìn lần random test

Một test tạo 1.000 hoặc 1.000.000 nonce rồi thấy không trùng **không chứng minh** hệ thống sẽ không collision. Với random nonce, phải đánh giá theo xác suất, số invocation, phân phối ngẫu nhiên, số instance và **ngân sách sử dụng khóa**.

Với counter, cần **test crash/restart/rollback/multi-node** để kiểm chứng uniqueness cả khi hệ thống không chạy thuận lợi. Cơ chế cấp phát phải phát hiện/không cấp lại giá trị cũ chứ không chỉ dùng một atomic counter in-memory.

### 16.2. Test tương thích và provider

Nếu ciphertext cần giải mã sau nhiều năm hoặc qua ngôn ngữ khác, hãy có **test vector** cố định cho từng format version và thuật toán. Test vector có thể dùng key/nonce cố định **chỉ trong test không mang dữ liệu nhạy cảm**, không lấy ví dụ đó làm nonce cố định cho mã hóa production.

Không dựa vào `Cipher.getInstance("AES")` vì mode/padding mặc định phụ thuộc provider. Dùng **transformation đầy đủ** và kiểm tra key size/tag/nonce/encoding theo hợp đồng.

## 17. Những lỗi bảo mật thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng lại nonce với cùng AES-GCM key | Phá tính bí mật/xác thực, có thể làm giả | Nonce policy bảo đảm unique, rotate khi phát hiện sai |
| Sinh nonce bằng `Random`, timestamp hoặc counter reset mỗi restart | Collision hoặc dự đoán/đụng độ | CSPRNG trong ngân sách hoặc counter durable |
| Quên lưu nonce cạnh ciphertext | Không đủ tham số để decrypt | Envelope format có nonce |
| Dùng một nonce cho nhiều chunk | Lặp `(key,nonce)` trong chunked encryption | Giao thức chunked AEAD chuẩn, nonce riêng và ràng buộc thứ tự |
| Nhầm `GCMParameterSpec(16, iv)` là tag 16 byte | Tham số tag là **bit**, sai độ dài | Dùng 128 cho tag 128 bit |
| Quên `updateAAD` khi decrypt | Tag verification thất bại | Cùng context và bytes ở cả hai phía |
| Gọi AAD sau khi xử lý plaintext | Sai contract GCM AEAD | Cung cấp AAD trước `update/doFinal` |
| Tin dữ liệu từ `Cipher.update` là plaintext đã xác thực | Có thể công bố dữ liệu giả mạo | Chỉ sử dụng sau xác minh `doFinal` |
| Bỏ qua `AEADBadTagException` và parse plaintext | Tin dữ liệu không hợp lệ | Reject toàn bộ message |
| Hard-code khóa ở code/config public | Lộ toàn bộ ciphertext | KMS/HSM/vault/keystore và rotation |
| Gọi `KeyGenerator` mỗi request khi dữ liệu cần đọc lại | Mất khóa cũ | Quản lý DEK với key ID/lifecycle |
| Mã hóa mà không ràng buộc record/tenant | Có thể hoán đổi ciphertext hợp lệ giữa context | AAD canonical gắn purpose/tenant/record |
| Dùng `ECB`, CBC không MAC hoặc hash không key như tag | Không có xác thực AEAD đúng | Dùng AES-GCM/ChaCha20-Poly1305 |
| Tin AEAD chống replay hoặc chứng minh người gửi cụ thể | Replay/authorization bypass | Message ID/sequence + authn/authz |
| Log khóa, token hoặc plaintext khi decrypt lỗi | Rò rỉ thông tin nhạy cảm | Generic error, telemetry có kiểm soát |
| Coi mỗi instance có ngân sách nonce riêng cho cùng key | Vượt giới hạn toàn khóa | Meter theo key toàn hệ thống |
| Giữ khóa cũ vô hạn hoặc xóa khóa quá sớm | Tăng rủi ro hoặc mất khả năng giải mã | Cryptoperiod, retention và re-encryption rõ ràng |

## 18. Quy trình phản ứng nếu nghi đã lặp nonce

Nếu có bằng chứng cùng `(key,nonce)` đã được dùng cho nhiều lần AES-GCM encryption, **không chỉ sửa generator rồi tiếp tục dùng khóa cũ như bình thường**.

Các bước ở mức quy trình:

1. **Dừng phát sinh mã hóa mới với khóa bị ảnh hưởng** hoặc cô lập luồng gây lỗi.
2. Xác định phạm vi: key ID, khoảng thời gian, node, message, số cặp nonce trùng và nơi ciphertext đã đi qua.
3. **Rotate sang một khóa mới độc lập**, với chính sách nonce được sửa và kiểm thử.
4. Đánh giá tác động đến tính bí mật và khả năng làm giả; xử lý dữ liệu/tác vụ phụ thuộc theo playbook bảo mật.
5. Re-encrypt dữ liệu còn tin cậy nếu phù hợp, đồng thời giữ chính sách truy cập vào bản backup cũ.
6. Bổ sung metric, alert trước ngưỡng nonce/key usage và test crash/failover.
7. Tham khảo đội ngũ mật mã/bảo mật khi đánh giá mức độ ảnh hưởng; không giả định chỉ một lần reuse là vô hại.

Lý do: với GCM, một số sai lầm về nonce có thể làm hỏng các tính chất an toàn theo cách không thể phục hồi chỉ bằng việc thay IV của các bản mã tiếp theo.

## 19. Checklist triển khai Java 27

Trước khi sử dụng AEAD để bảo vệ dữ liệu thật, hãy xác nhận:

1. Đã xác định **threat model**: bảo vệ dữ liệu khỏi ai, khi lưu ở đâu, và ai có quyền giải mã?
2. Đã chọn AEAD chuẩn được hỗ trợ (`AES/GCM/NoPadding` hoặc `ChaCha20-Poly1305`) chưa?
3. Khóa được tạo bởi CSPRNG/KMS và có độ dài phù hợp chưa?
4. Khóa có được quản lý, phân quyền, audit, backup/restore và rotate đúng không?
5. Đã có chính sách **nonce unique trên toàn bộ các lần encrypt với một khóa** chưa?
6. Nếu random nonce: đã tính collision risk, giới hạn invocation và ngân sách dùng key toàn cụm chưa?
7. Nếu deterministic nonce: đã có fixed-field ownership, durable counter, chống rollback và overflow chưa?
8. Đã thiết kế envelope gồm version, key ID, nonce, ciphertext/tag đúng không?
9. Metadata quan trọng và context (tenant, record, purpose) đã được ràng buộc vào AAD chuẩn hóa chưa?
10. Đã xác minh AAD được cung cấp trước dữ liệu trong cả encrypt/decrypt chưa?
11. Ứng dụng chỉ chấp nhận plaintext sau khi `doFinal` xác thực tag thành công chưa?
12. Có từ chối input quá dài, sai định dạng hoặc không được hỗ trợ trước khi cấp phát bộ nhớ lớn không?
13. Có test tamper, wrong key, wrong AAD, truncated ciphertext, concurrency và restart/failover không?
14. Có chiến lược replay detection riêng nếu bài toán yêu cầu không chấp nhận message cũ không?
15. Có monitoring để biết sắp đến giới hạn key usage/nonce không?
16. Có quy trình phản ứng sự cố nếu nonce bị lặp hoặc khóa bị lộ không?
17. Có test tương thích giữa các provider/JDK và format version cần hỗ trợ không?
18. Có tránh hard-code secret, mode mã hóa không xác thực và các phương án mật mã tự chế không?

**Kết luận:** trong Java 27, `Cipher` và JCE giúp mã hóa có xác thực bằng API tương đối ngắn, nhưng **độ an toàn thực tế nằm ở hợp đồng end-to-end**: quản lý khóa, cấp nonce duy nhất, AAD đúng ngữ cảnh, xác minh tag trước khi dùng dữ liệu, lưu format có phiên bản và thực hiện rotation/monitoring trên toàn hệ thống. Một đoạn `Cipher.doFinal()` đúng cú pháp chưa đủ để tạo nên một giao thức mã hóa an toàn.

## Tài liệu tham khảo

- [Java SE 27 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html): cơ chế JCE, AES-GCM, `updateAAD`, quản lý IV và luồng mã hóa/giải mã.
- [Java SE 27 API — `Cipher`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/Cipher.html): transformation, AEAD, xử lý tag và hạn chế tái sử dụng nonce.
- [Java SE 27 API — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): IV và tag length tính theo bit.
- [Java SE 27 API — `AEADBadTagException`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/AEADBadTagException.html): lỗi không xác minh được tag.
- [Java SE 27 API — `KeyGenerator`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/KeyGenerator.html): tạo khóa symmetric.
- [Java SE 27 API — `SecureRandom`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/SecureRandom.html): byte ngẫu nhiên phù hợp mật mã.
- [Java SE 27 API — `SecretKey`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/SecretKey.html): abstraction của symmetric key.
- [Java SE 27 API — `IvParameterSpec`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html): tham số IV cho transformation tương ứng.
- [NIST SP 800-38D — Recommendation for Galois/Counter Mode](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf): yêu cầu uniqueness IV, giới hạn invocation và cách xây dựng nonce cho GCM.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): thuật toán, AEAD, key management và bảo vệ dữ liệu lưu trữ.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): quản lý, lưu trữ, rotation và vòng đời khóa.
