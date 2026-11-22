# Khởi tạo, update và doFinal với ChaCha20 — Java 11+

## 1. Mục tiêu bài học

**ChaCha20** là một **stream cipher** dùng khóa bí mật để tạo ra dòng byte giả ngẫu nhiên (*keystream*) rồi kết hợp với dữ liệu bằng XOR. Từ **Java 11**, JDK triển khai ChaCha20 và **ChaCha20-Poly1305** qua Java Cryptography Extension (`javax.crypto.Cipher`), theo **JEP 329**.

Bài học tập trung vào đúng ba thao tác khi sử dụng `Cipher`:

1. **`init(...)`:** chọn mã hóa/giải mã, cung cấp khóa và tham số như nonce, counter.
2. **`update(...)`:** cung cấp **một phần** input và lấy những byte đầu ra mà implementation đã xử lý (nếu có).
3. **`doFinal(...)`:** xử lý phần input cuối, **kết thúc một hoạt động mật mã** và trả phần output còn lại; với AEAD, đồng thời tạo hoặc kiểm tra authentication tag.

Điều đặc biệt quan trọng: **`ChaCha20` thuần và `ChaCha20-Poly1305` không giống nhau về bảo mật**.

- `Cipher.getInstance("ChaCha20")` là **mã hóa dòng**: có tính bí mật nhưng **không có authentication tag**, nên bản mã bị sửa không tự khiến giải mã bị từ chối.
- `Cipher.getInstance("ChaCha20-Poly1305")` là **AEAD** (*Authenticated Encryption with Associated Data*): đồng thời bảo vệ **bí mật và tính toàn vẹn** của bản mã cùng dữ liệu xác thực bổ sung (*AAD*), với **tag 16 byte**.

Nếu đang thiết kế cách truyền hoặc lưu dữ liệu mới, **ưu tiên AEAD** như ChaCha20-Poly1305 hoặc AES-GCM, thay vì dùng ChaCha20 thuần rồi tưởng rằng nó tự bảo vệ chống sửa đổi.

Tất cả API chính ở đây có từ **Java 11** và vẫn được hỗ trợ hiện nay. Phần ví dụ dùng `javac --release 11` để bảo đảm cú pháp và API không dựa vào tính năng Java mới hơn. Tiêu chuẩn tham khảo là **RFC 8439**, tài liệu cập nhật thay cho RFC 7539.

## 2. Khóa, nonce, counter và tag: mỗi thứ làm gì?

| Thành phần | ChaCha20 thuần | ChaCha20-Poly1305 AEAD |
| --- | --- | --- |
| Khóa bí mật | **256 bit = 32 byte** | **256 bit = 32 byte** |
| Nonce | **96 bit = 12 byte** | **96 bit = 12 byte** |
| Counter | **32-bit integer**, do ứng dụng truyền qua `ChaCha20ParameterSpec` | Được thuật toán AEAD quản lý nội bộ; **không** truyền counter riêng |
| Tham số trong `Cipher.init` | `new ChaCha20ParameterSpec(nonce, counter)` | `new IvParameterSpec(nonce)` |
| Transformation | `"ChaCha20"` | `"ChaCha20-Poly1305"` |
| AAD | Không có xác thực AAD | Có `updateAAD(...)` trước phần dữ liệu |
| Output khi mã hóa | Bản mã có cùng số byte với plaintext | Bản mã **kèm tag 16 byte** |
| Kiểm tra bị sửa | **Không** | Kiểm tra tag khi `doFinal` giải mã; sai thì từ chối |

**Khóa (`key`)** là bí mật, không được truyền chung công khai với bản mã. Có thể lấy 32 byte từ `SecureRandom` hoặc `KeyGenerator` phù hợp với thuật toán; không dùng `java.util.Random` để sinh khóa bảo mật.

**Nonce** không cần bí mật, nhưng có điều kiện quan trọng hơn: **với mỗi khóa, nonce dùng để mã hóa các thông điệp khác nhau phải không trùng**. Dùng lại cặp **key + nonce** có thể khiến ChaCha20 làm lộ quan hệ giữa hai plaintext, và làm suy yếu nghiêm trọng khả năng xác thực của ChaCha20-Poly1305.

**Counter** đếm các khối keystream 64 byte của ChaCha20. Với ChaCha20 thuần, `ChaCha20ParameterSpec` chứa nonce 12 byte và initial counter 32 bit. Counter **không phải số thứ tự message tự động**, và đổi counter một cách tùy tiện **không phải cách thay thế thiết kế nonce duy nhất**. Không để counter quấn vòng trong cùng dòng keystream.

**Tag** của ChaCha20-Poly1305 gồm 16 byte, được tính từ plaintext/ciphertext, AAD, độ dài và khóa xác thực theo chuẩn AEAD. Nó thường được **nối sau ciphertext** trong output của `Cipher.doFinal`. Người nhận phải kiểm tra tag **trước khi chấp nhận plaintext là dữ liệu đáng tin**.

### 2.1. Tại sao AEAD không nhận ChaCha20ParameterSpec?

ChaCha20-Poly1305 dùng ChaCha20 theo một sơ đồ cố định trong RFC 8439: một phần keystream phục vụ tạo khóa Poly1305 một lần, còn việc mã hóa message dùng các khối tiếp theo. Counter đã nằm trong thiết kế thuật toán, **không cho ứng dụng chọn tùy ý** ở tham số AEAD.

Đúng với Java 11:

```java
byte[] nonce = new byte[12];
// Ví dụ về kiểu tham số, không phải nonce an toàn để mã hóa thực.

ChaCha20ParameterSpec streamParams =
        new ChaCha20ParameterSpec(nonce, 1); // Cho "ChaCha20".

IvParameterSpec aeadParams =
        new IvParameterSpec(nonce);          // Cho "ChaCha20-Poly1305".
```

Đây là **mảnh mã giải thích kiểu tham số**; `new byte[12]` là nonce toàn số 0, **không được tái sử dụng trong nhiều lần mã hóa**. Chương trình đầy đủ dùng `SecureRandom` tạo nonce ngẫu nhiên cho mỗi hoạt động mã hóa trong ví dụ.

## 3. Khởi tạo ChaCha20 thuần bằng Cipher.init

Các import cần thiết:

```java
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.SecretKeySpec;
```

Sinh khóa và nonce cho **một message**:

```java
SecureRandom random = new SecureRandom();
byte[] keyBytes = new byte[32];   // 256-bit secret key.
byte[] nonce = new byte[12];      // 96-bit nonce.
random.nextBytes(keyBytes);
random.nextBytes(nonce);

SecretKeySpec key = new SecretKeySpec(keyBytes, "ChaCha20");
ChaCha20ParameterSpec params = new ChaCha20ParameterSpec(nonce, 1);

Cipher cipher = Cipher.getInstance("ChaCha20");
cipher.init(Cipher.ENCRYPT_MODE, key, params);
```

Đây là **mảnh mã chạy trong phương thức** có xử lý `GeneralSecurityException`. `1` là initial counter dùng cho thông điệp trong ví dụ, không phải yêu cầu mọi giao thức ChaCha20 đều có cùng counter; khi trao đổi dữ liệu, người gửi và người nhận phải thống nhất **đúng counter bắt đầu**.

### 3.1. Cipher.ENCRYPT_MODE và Cipher.DECRYPT_MODE

- `Cipher.ENCRYPT_MODE`: plaintext → ciphertext.
- `Cipher.DECRYPT_MODE`: ciphertext → plaintext, dùng **đúng cùng key, nonce và initial counter** tương ứng với lần mã hóa.
- Với ChaCha20 thuần, mã hóa và giải mã dựa trên phép XOR với cùng keystream. Do đó một byte ciphertext thay đổi thường sẽ tạo một byte plaintext thay đổi, **không phát sinh lỗi xác thực**.

**Không nhầm việc dùng cùng key/nonce ở phía giải mã với mã hóa nhiều thông điệp bằng cùng key/nonce.** Giải mã một ciphertext cần tái tạo keystream tương ứng; việc dùng lại key/nonce để **mã hóa plaintext thứ hai** là rủi ro bảo mật nghiêm trọng.

### 3.2. Kích thước tham số sai

`new ChaCha20ParameterSpec(nonce, counter)` đòi **nonce đúng 12 byte**, nếu không ném `IllegalArgumentException`. `Cipher.init` còn có thể ném `InvalidKeyException` hoặc `InvalidAlgorithmParameterException` nếu key/parameter không được provider chấp nhận.

`new SecretKeySpec(bytes, "ChaCha20")` chỉ gắn **tên thuật toán và byte khóa**; nó không tự sinh entropy. Nếu `bytes` lấy từ mật khẩu ngắn, chất lượng khóa vẫn kém. Với mật khẩu, phải dùng KDF dành cho mật khẩu và một thiết kế lưu trữ/derivation thích hợp, không lấy `password.getBytes()` làm khóa ChaCha20.

## 4. update và doFinal hoạt động thế nào?

### 4.1. Một lần doFinal cho toàn bộ message

Nếu dữ liệu đã nằm gọn trong một `byte[]`:

```java
byte[] plain = "Xin chào".getBytes(StandardCharsets.UTF_8);

Cipher c = Cipher.getInstance("ChaCha20");
c.init(Cipher.ENCRYPT_MODE, key, params);
byte[] ciphertext = c.doFinal(plain);
```

Đây là mảnh mã cần import `StandardCharsets`, và giả định `key`/`params` đã chuẩn bị. `doFinal(input)` vừa **nhận input vừa kết thúc hoạt động**. Với ChaCha20 thuần, chiều dài ciphertext bằng chiều dài plaintext.

### 4.2. Nhiều lần update và một doFinal

Với input lớn hoặc nhận dần:

```java
int split = 5;
byte[] first = c.update(plain, 0, split);
byte[] last = c.doFinal(plain, split, plain.length - split);
byte[] all = join(first, last);
```

`join` là hàm ghép output trong chương trình đầy đủ ở mục 7. Đối với các overload trả `byte[]` của `update`, API có thể trả `null` nếu chưa tạo được output; **không mặc định một lần `update` luôn trả ngay đúng số byte đã đưa vào** trên mọi mode/provider. Hàm `join` vì vậy chấp nhận `null`.

Các điểm cần nhớ:

1. `update(input, offset, len)` chỉ xử lý **đoạn input được chỉ định**. `offset` và `len` được tính bằng **byte**, không phải ký tự Unicode.
2. Có thể gọi `update` nhiều lần; mỗi lần thu những byte output nếu có.
3. `doFinal(...)` xử lý đoạn cuối và kết thúc. **Phải ghép cả output từ update lẫn doFinal**; bỏ một bên sẽ tạo dữ liệu không đầy đủ.
4. Với AEAD, một phần output **có thể được giữ/buffer** đến bước xác thực cuối; không phụ thuộc vào chunking cụ thể.
5. Không tiếp tục đưa dữ liệu của **cùng message** vào `update` sau khi đã kết thúc bằng `doFinal`. Muốn mã hóa thông điệp mới, tạo hoạt động mới cùng **nonce khác**.

### 4.3. Ghi ra output buffer hoặc ByteBuffer

`Cipher` có overload như:

```java
int n = c.update(input, inputOffset, inputLength,
                 output, outputOffset);
int m = c.doFinal(lastInput, 0, lastInput.length,
                  output, outputOffset + n);
```

Đây là **mảnh mã minh họa**; phải bảo đảm `output` đủ lớn cho cả hai lời gọi. Nếu buffer không đủ, API có thể ném `ShortBufferException`. `c.getOutputSize(inputLength)` giúp ước tính tối đa output trong ngữ cảnh trạng thái hiện tại; **không giả định mọi lần update tạo đúng inputLength byte**, nhất là khi dùng AEAD.

Các overload `update(ByteBuffer input, ByteBuffer output)` và `doFinal(ByteBuffer input, ByteBuffer output)` hữu ích trong pipeline NIO. Chúng thay đổi `position` của buffer theo số byte đã dùng/ghi; người dùng phải quản lý `flip()`/`clear()`, `remaining()` và giới hạn buffer.

Với stream cipher thuần, output thường xuất hiện ngay theo kích thước input. Với ChaCha20-Poly1305, đặc biệt phía **giải mã**, implementation có thể buffer đến khi có tag và xác minh thành công. **Không đưa plaintext chưa xác thực tới bộ xử lý nghiệp vụ**.

## 5. Khởi tạo ChaCha20-Poly1305 và sử dụng AAD

Đây là lựa chọn phù hợp hơn khi cần cả mã hóa và tính toàn vẹn.

### 5.1. init cho AEAD

```java
import javax.crypto.spec.IvParameterSpec;

byte[] keyBytes = new byte[32];
byte[] nonce = new byte[12];
SecureRandom rng = new SecureRandom();
rng.nextBytes(keyBytes);
rng.nextBytes(nonce);

SecretKeySpec key = new SecretKeySpec(keyBytes, "ChaCha20");
Cipher aead = Cipher.getInstance("ChaCha20-Poly1305");
aead.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
```

Trong AEAD, tham số là **`IvParameterSpec(nonce)`**, không phải `ChaCha20ParameterSpec`. Khóa vẫn có kích thước 32 byte. Với dữ liệu ở ví dụ, `nonce` vừa sinh chỉ dùng cho **một lần mã hóa** dưới `keyBytes`.

### 5.2. AAD là dữ liệu được xác thực nhưng không mã hóa

AAD (*Additional Authenticated Data*) có thể chứa metadata như phiên bản protocol, loại bản tin, ID hoặc thông tin ngữ cảnh mà hai phía đều biết:

```java
byte[] aad = "type=text;version=1"
        .getBytes(StandardCharsets.UTF_8);

aead.updateAAD(aad); // BẮT BUỘC trước update/doFinal của message.
```

Dữ liệu AAD **không được mã hóa**, nên không giấu bí mật trong AAD chỉ vì nó được “authenticate”. Khi giải mã, cả hai phía phải cung cấp **chính xác cùng các byte AAD**, nếu khác sẽ kiểm tra tag thất bại.

**Trình tự quan trọng:** với AEAD, đưa **toàn bộ AAD trước khi đưa plaintext/ciphertext** vào `update` hoặc `doFinal`. Gọi `updateAAD` sau khi đã bắt đầu xử lý nội dung có thể gây `IllegalStateException` theo triển khai và hợp đồng API.

### 5.3. AEAD encryption theo nhiều phần

```java
aead.updateAAD(aad);
byte[] part = aead.update(plain, 0, 6);
byte[] finish = aead.doFinal(plain, 6, plain.length - 6);
byte[] ciphertextAndTag = join(part, finish);
```

Trong ví dụ, `plain` và `join` đã được khai báo; đây là **mảnh mã minh họa**. Với ChaCha20-Poly1305, output hoàn chỉnh khi mã hóa gồm:

```text
ciphertext (cùng số byte với plaintext)
+
Poly1305 authentication tag (16 byte)
```

Ví dụ plaintext 19 byte UTF-8 thì output hoàn chỉnh thường là **35 byte**, không phải 19. Không tự loại 16 byte cuối rồi bỏ tag, vì bên nhận cần nó để xác thực.

### 5.4. AEAD decryption và lỗi authentication tag

Khi giải mã, bên nhận có **cùng key**, **cùng nonce** và **cùng AAD**, đồng thời nhận **ciphertext + tag**:

```java
Cipher decrypt = Cipher.getInstance("ChaCha20-Poly1305");
decrypt.init(Cipher.DECRYPT_MODE,
        key, new IvParameterSpec(nonce));
decrypt.updateAAD(aad);

byte[] tentative = decrypt.update(ciphertextAndTag, 0, 9);
byte[] finalPlain = decrypt.doFinal(
        ciphertextAndTag, 9, ciphertextAndTag.length - 9);
byte[] verifiedPlain = join(tentative, finalPlain);
```

Đây là mảnh mã có import/biến tương ứng. **Chỉ sau khi `doFinal` trả về thành công**, kết quả `verifiedPlain` mới được coi là dữ liệu đã xác thực. Trong ví dụ, `tentative` chỉ nằm trong bộ nhớ tạm, chưa được gửi sang subsystem khác.

Nếu tag, ciphertext, nonce, key hoặc AAD sai, `doFinal` phía giải mã sẽ ném `AEADBadTagException` (lớp con của `BadPaddingException`). Không được bắt lỗi rồi vẫn công bố dữ liệu từ `update`; hãy bỏ toàn bộ plaintext chưa xác thực và xử lý như thông điệp hỏng/không đáng tin.

**Không dùng `Cipher.ENCRYPT_MODE` cho giải mã hoặc cố sửa ciphertext bằng cách bỏ tag.** AEAD cần xác minh đồng bộ tất cả tham số của message.

## 6. Vòng đời Cipher và quản lý nonce

### 6.1. Không tái sử dụng key + nonce để mã hóa thông điệp mới

Đối với cùng một khóa:

```text
Message A -> key K + nonce N1
Message B -> key K + nonce N2
Message C -> key K + nonce N3
Điều kiện: N1, N2, N3 phải khác nhau.
```

Không làm:

```java
// CỐ Ý SAI: dùng lại cùng key/nonce để mã hóa plaintext khác.
Cipher c1 = Cipher.getInstance("ChaCha20-Poly1305");
c1.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
byte[] first = c1.doFinal(messageA);

Cipher c2 = Cipher.getInstance("ChaCha20-Poly1305");
c2.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
byte[] second = c2.doFinal(messageB);
```

Đây là **mảnh mã chống chỉ định**, không biên dịch độc lập nếu chưa định nghĩa biến. Ngay cả khi provider không ném exception, hai lần mã hóa như vậy vẫn **sai về mật mã**. Một số provider chỉ phát hiện nonce reuse khi tái khởi tạo cùng instance, không thể bảo đảm phát hiện reuse giữa hai `Cipher` hoặc giữa nhiều process.

Giải pháp: thiết kế **nonce duy nhất theo mỗi key** (ví dụ counter 96-bit lưu bền vững và phân vùng theo thiết bị/session, hoặc nonce ngẫu nhiên 96-bit với giới hạn số lượng thông điệp và rotation key phù hợp). Sinh ngẫu nhiên cho ví dụ một lần là đủ, nhưng khi có lượng lớn dữ liệu hoặc nhiều sender dùng chung khóa, **nonce phải được quản lý có hệ thống**. Không dùng timestamp độ phân giải thấp hay số 0 cố định.

### 6.2. Không dựa vào việc Cipher được reset sau doFinal để mã hóa lần nữa

Các phương thức `doFinal` kết thúc một hoạt động. API `Cipher` nói đối tượng có thể cố reset về trạng thái sau `init`, nhưng AEAD/stream ciphers có ràng buộc **nonce duy nhất**; một số provider không cho `update`/`doFinal` tiếp trước khi `init` mới.

**Quy tắc vận hành an toàn:** mỗi thông điệp mã hóa dùng một phiên `Cipher.init(Cipher.ENCRYPT_MODE, key, newNonceParameters)` và nonce mới; có thể tạo `Cipher` mới để tránh chia sẻ state. Không gọi `doFinal` lần hai trên cùng state với key/nonce cũ để mã hóa một message mới.

### 6.3. Decryption phải dùng nonce tương ứng, nhưng chống replay là việc riêng

Để giải mã một ciphertext, client phải biết nonce đã dùng khi mã hóa và đưa vào `init(DECRYPT_MODE, ...)`. Nonce có thể được truyền kèm packet vì nó **không bí mật**, nhưng phải được **kiểm tra kích thước và định dạng**.

Giải mã một ciphertext hợp lệ không tự chứng minh packet chưa từng được gửi trước đó. Nếu ứng dụng không cho phép replay, phải có message ID, counter/sequence number, cửa sổ chống replay hoặc kiểm tra trạng thái nghiệp vụ. AEAD xác minh nội dung, **không tự bảo đảm mỗi bản tin được xử lý đúng một lần**.

### 6.4. Không tự giảm mức an ninh khi có lỗi

Nếu provider không hỗ trợ `"ChaCha20-Poly1305"`, xử lý `NoSuchAlgorithmException` đúng nghĩa; không âm thầm đổi sang `"ChaCha20"` mà bỏ luôn xác thực. Với cùng kiểu dữ liệu, có thể dùng **AES-GCM** được thiết kế/kiểm thử đúng cách nếu chính sách sản phẩm cho phép. Tuyệt đối không fallback sang RC4 hay mã hóa ECB không xác thực.

## 7. Chương trình Java 11 độc lập: init, update, doFinal, AAD và tag

Chương trình dưới đây **không cần mạng, file input hay thư viện ngoài JDK**. Nó chạy hai biến thể `Cipher` riêng biệt:

- **ChaCha20 thuần:** init với `ChaCha20ParameterSpec(nonce, 1)`, mã hóa bằng một lần `update` + `doFinal`, giải mã theo nhiều phần. Sau khi sửa một byte ciphertext, phía giải mã **vẫn trả plaintext đã bị thay đổi**, không có authentication error.
- **ChaCha20-Poly1305:** init với `IvParameterSpec(nonce)`, gọi `updateAAD` trước data, mã hóa bằng `update` + `doFinal`, giải mã lại đúng. Sau đó thử sửa tag và thay AAD; cả hai trường hợp đều bị từ chối bằng `AEADBadTagException`.
- **Kiểm tra tham số:** nonce 11 byte gây `IllegalArgumentException` ở `ChaCha20ParameterSpec`.

Mã sinh random key/nonce mới ở mỗi lần chạy và **không in khóa bí mật hoặc bản mã**. Đầu ra ổn định vì chỉ in thông tin xác minh.

Tạo tệp **`ChaCha20UpdateFinalDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class ChaCha20UpdateFinalDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    private static byte[] randomBytes(int n) {
        byte[] result = new byte[n];
        RANDOM.nextBytes(result);
        return result;
    }

    private static byte[] join(byte[] a, byte[] b) {
        if (a == null) a = new byte[0];
        if (b == null) b = new byte[0];
        byte[] result = Arrays.copyOf(a, a.length + b.length);
        System.arraycopy(b, 0, result, a.length, b.length);
        return result;
    }

    private static byte[] decryptRaw(byte[] key, byte[] nonce, byte[] bytes)
            throws Exception {
        Cipher c = Cipher.getInstance("ChaCha20");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "ChaCha20"),
                new ChaCha20ParameterSpec(nonce, 1));
        return join(c.update(bytes, 0, 7),
                c.doFinal(bytes, 7, bytes.length - 7));
    }

    private static byte[] decryptAead(byte[] key, byte[] nonce, byte[] aad,
                                       byte[] bytes) throws Exception {
        Cipher c = Cipher.getInstance("ChaCha20-Poly1305");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "ChaCha20"),
                new IvParameterSpec(nonce));
        c.updateAAD(aad);
        return join(c.update(bytes, 0, 9),
                c.doFinal(bytes, 9, bytes.length - 9));
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        byte[] message = "Xin chào ChaCha20!"
                .getBytes(StandardCharsets.UTF_8);

        byte[] rawKey = randomBytes(32), rawNonce = randomBytes(12);
        Cipher raw = Cipher.getInstance("ChaCha20");
        raw.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(rawKey, "ChaCha20"),
                new ChaCha20ParameterSpec(rawNonce, 1));
        byte[] encrypted = join(raw.update(message, 0, 5),
                raw.doFinal(message, 5, message.length - 5));
        byte[] roundTrip = decryptRaw(rawKey, rawNonce, encrypted);
        check(Arrays.equals(message, roundTrip),
                "Raw round trip failed");
        System.out.println("ChaCha20 round trip = "
                + new String(roundTrip, StandardCharsets.UTF_8));
        System.out.println("ChaCha20 length unchanged = "
                + (encrypted.length == message.length));

        byte[] modified = encrypted.clone();
        modified[0] ^= 1;
        byte[] modifiedPlaintext =
                decryptRaw(rawKey, rawNonce, modified);
        check(!Arrays.equals(message, modifiedPlaintext),
                "Modified ciphertext did not change plaintext");
        System.out.println("ChaCha20 rejects tampering = false");

        byte[] aeadKey = randomBytes(32), aeadNonce = randomBytes(12);
        byte[] aad = "type=text;version=1"
                .getBytes(StandardCharsets.UTF_8);
        Cipher auth = Cipher.getInstance("ChaCha20-Poly1305");
        auth.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(aeadKey, "ChaCha20"),
                new IvParameterSpec(aeadNonce));
        auth.updateAAD(aad);
        byte[] ciphertextAndTag =
                join(auth.update(message, 0, 6),
                     auth.doFinal(message, 6, message.length - 6));
        check(ciphertextAndTag.length == message.length + 16,
                "Expected 16-byte tag");

        byte[] recovered = decryptAead(
                aeadKey, aeadNonce, aad, ciphertextAndTag);
        check(Arrays.equals(message, recovered),
                "AEAD round trip failed");
        System.out.println("AEAD round trip = "
                + new String(recovered, StandardCharsets.UTF_8));
        System.out.println("AEAD tag bytes = "
                + (ciphertextAndTag.length - message.length));

        byte[] tampered = ciphertextAndTag.clone();
        tampered[tampered.length - 1] ^= 1;
        boolean tagRejected = false;
        try {
            decryptAead(aeadKey, aeadNonce, aad, tampered);
        } catch (AEADBadTagException expected) {
            tagRejected = true;
        }
        check(tagRejected, "Tampered tag was accepted");
        System.out.println("AEAD tamper rejected = "
                + tagRejected);

        byte[] wrongAad = "type=json;version=1"
                .getBytes(StandardCharsets.UTF_8);
        boolean aadRejected = false;
        try {
            decryptAead(aeadKey, aeadNonce, wrongAad,
                        ciphertextAndTag);
        } catch (AEADBadTagException expected) {
            aadRejected = true;
        }
        check(aadRejected, "Wrong AAD was accepted");
        System.out.println("AEAD wrong AAD rejected = "
                + aadRejected);

        boolean badNonceRejected = false;
        try {
            new ChaCha20ParameterSpec(new byte[11], 1);
        } catch (IllegalArgumentException expected) {
            badNonceRejected = true;
        }
        check(badNonceRejected, "11-byte nonce was accepted");
        System.out.println("11-byte nonce rejected = "
                + badNonceRejected);
        System.out.println("ALL CHECKS PASSED");

        Arrays.fill(rawKey, (byte) 0);
        Arrays.fill(aeadKey, (byte) 0);
    }
}
```

Biên dịch và chạy bằng JDK 11 trở lên:

```bash
javac --release 11 ChaCha20UpdateFinalDemo.java
java ChaCha20UpdateFinalDemo
```

**Đầu ra đã kiểm chứng thực tế:**

```text
ChaCha20 round trip = Xin chào ChaCha20!
ChaCha20 length unchanged = true
ChaCha20 rejects tampering = false
AEAD round trip = Xin chào ChaCha20!
AEAD tag bytes = 16
AEAD tamper rejected = true
AEAD wrong AAD rejected = true
11-byte nonce rejected = true
ALL CHECKS PASSED
```

### 7.1. Diễn giải kết quả

- **`ChaCha20 round trip`**: cùng secret key, nonce và counter ở hai chiều tái tạo đúng keystream, giải mã ra plaintext.
- **`ChaCha20 length unchanged = true`**: stream cipher thuần không thêm authentication tag hay padding vào output.
- **`ChaCha20 rejects tampering = false`**: thay byte ciphertext khiến plaintext giải mã khác, **nhưng API thuần không biết bản mã đã bị sửa**; đây là lý do không dùng ChaCha20 thuần làm cơ chế kiểm tra integrity.
- **`AEAD round trip`**: cùng key, nonce, AAD và ciphertext/tag thì `doFinal` xác minh thành công.
- **`AEAD tag bytes = 16`**: Poly1305 authentication tag dài 16 byte, nối sau ciphertext.
- **`AEAD tamper rejected = true`**: sửa tag khiến `AEADBadTagException` ở bước giải mã.
- **`AEAD wrong AAD rejected = true`**: đổi dữ liệu được xác thực (dù không mã hóa) khiến tag verification thất bại.
- **`11-byte nonce rejected = true`**: `ChaCha20ParameterSpec` bắt buộc nonce 12 byte.
- **`ALL CHECKS PASSED`**: các assertion trong demo thành công. Mã không dùng ciphertext cố định, vì khóa/nonce được sinh bằng `SecureRandom` mỗi lần.

**Tại sao `decryptAead` ghép output từ update và doFinal?** Bởi vì API hỗ trợ streaming ở cả hai bước; nếu triển khai có trả plaintext trước khi tag được kiểm tra, `decryptAead` chỉ giữ nó trong biến cục bộ, **không công bố cho caller** trước khi `doFinal` thành công.

**Giới hạn demo:** nó cố tình thử giải mã một ciphertext/tampered ciphertext trong cùng process để kiểm tra tag, không xây giao thức truyền dữ liệu hay chống replay production. Các mảng chứa key ở cuối được xóa bằng `Arrays.fill` theo hướng best effort; Java runtime và provider vẫn có thể giữ bản sao ở nơi khác. Không coi `fill` là bảo đảm xóa vật lý hoàn toàn.

## 8. Đưa mã hóa ChaCha20-Poly1305 vào một định dạng message

Một ứng dụng lưu file hoặc truyền message phải quy định **những byte nào có mặt trong packet**. Ví dụ khái niệm:

```text
+------------+--------------+---------------------+----------------+
| version(1) | nonce(12)    | ciphertext(n bytes) | Poly1305 tag(16) |
+------------+--------------+---------------------+----------------+
```

Đây chỉ là **định dạng minh họa**, cần xác định rõ số byte/version, encoding, giới hạn độ dài và metadata thực tế. Key **không** nằm trong packet; hai phía lấy từ hệ thống quản lý khóa đã thỏa thuận.

Để xác thực phần header metadata nhưng không mã hóa, có thể đưa **version, message type, sender identity hoặc sequence number** vào AAD theo giao thức. Với mỗi message, cả bên gửi và nhận phải tính **cùng byte AAD**; nếu không thì tag không hợp lệ.

Ví dụ xử lý packet:

1. Parse version/nonce 12 byte; từ chối gói sai định dạng hoặc thiếu 16 byte tag.
2. Lấy đúng khóa 32 byte theo key ID/session đã xác thực.
3. Tính AAD theo canonical encoding của giao thức; tránh hai bên ghép chuỗi khác thứ tự/cách biểu diễn.
4. `init(DECRYPT_MODE, key, new IvParameterSpec(nonce))` rồi `updateAAD(aad)`.
5. Giải mã bằng `update/doFinal`; chỉ sau `doFinal` thành công mới xử lý plaintext nghiệp vụ.
6. Kiểm tra sequence number/replay policy nếu ứng dụng yêu cầu chống phát lại.

Nếu metadata không được xác thực bằng AAD hoặc transcript của protocol, người nhận có thể hiểu sai phiên bản/loại thông điệp dù ciphertext vẫn hợp lệ. Ngược lại, AAD có thể bị đọc bởi bên ngoài; không dùng AAD để ẩn thông tin bí mật.

### 8.1. Nonce random, nonce tuần tự và nhiều producer

Sinh một nonce ngẫu nhiên 12 byte bằng `SecureRandom` có thể phù hợp cho số lượng message giới hạn và kế hoạch rotation key. Nhưng trong hệ thống phát **rất nhiều** message hoặc có **nhiều máy cùng dùng một khóa**, cần dự đoán/xử lý xác suất trùng và nguy cơ hai nguồn phát vô tình cấp cùng nonce.

Một thiết kế khác là nonce từ counter duy nhất có kiểm soát. Nếu dùng counter, phải bảo đảm duy nhất **xuyên process, xuyên lần restart và trên mọi producer cùng key**. Không thể chỉ dùng biến `long count` cục bộ rồi giả định nonce không trùng khi restart. Nếu không thể kiểm soát uniqueness, cần tách khóa theo producer/session hoặc đổi kiến trúc.

### 8.2. Không hoán đổi hai transformation trong cùng protocol

`"ChaCha20"` và `"ChaCha20-Poly1305"` không phải cùng kiểu byte output:

- ChaCha20 thuần: output chính là ciphertext.
- ChaCha20-Poly1305: ciphertext **cộng tag 16 byte**, kèm AAD cần thiết cho verification.

Nếu client mã hóa bằng AEAD còn peer giải mã bằng ChaCha20 thuần, nó có thể coi tag là dữ liệu và bỏ hoàn toàn xác thực. Protocol cần cố định algorithm version và từ chối downgrade không được phê duyệt.

## 9. Những lỗi thường gặp và cách khắc phục

| Triệu chứng/sai lầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `NoSuchAlgorithmException` với tên transformation | Provider/runtime không hỗ trợ biến thể được yêu cầu | Dùng tên chuẩn `"ChaCha20"`/`"ChaCha20-Poly1305"`, xác minh JDK/provider; không fallback sang mode kém bảo mật |
| `InvalidKeyException` tại `init` | Khóa sai độ dài, thuật toán không phù hợp hoặc bị policy từ chối | Dùng khóa bí mật **32 byte**, kiểm tra nguồn tạo key |
| `IllegalArgumentException` tại `ChaCha20ParameterSpec` | Nonce không đúng 12 byte | Sinh/truyền đúng 12 byte |
| `InvalidAlgorithmParameterException` tại `init` | Tham số sai kiểu/nonce sai kích thước/cấu hình không hợp lệ | Dùng `ChaCha20ParameterSpec` cho ChaCha20; `IvParameterSpec` cho ChaCha20-Poly1305 |
| `updateAAD` bị từ chối | Gọi sau `update/doFinal` hoặc dùng cipher không phải AEAD | Gọi `updateAAD` trước dữ liệu, chỉ với ChaCha20-Poly1305 |
| Dữ liệu decrypt chỉ lấy từ `doFinal` bị thiếu | Bỏ output từ `update` | Ghép tất cả phần output theo đúng thứ tự |
| `NullPointerException` khi ghép output | `update` chưa tạo byte và trả `null` | Xử lý `null` như mảng rỗng; không giả định output luôn có |
| `ShortBufferException` với overload output array | Buffer đích quá ngắn | Kiểm tra `getOutputSize` và quản lý offset cẩn thận |
| `AEADBadTagException` ở phía decrypt | Tag/ciphertext/key/nonce/AAD không khớp | **Từ chối toàn bộ plaintext**, kiểm tra định dạng và thông số; không bỏ tag |
| Bản mã bị sửa nhưng ChaCha20 thuần vẫn giải mã | Stream cipher không có authentication | Dùng ChaCha20-Poly1305 hoặc giao thức có integrity được đánh giá |
| Cipher hoạt động không đúng sau `doFinal` | Thử tiếp message mới với state/nonce cũ | Khởi tạo hoạt động mới và **nonce mới** cho mỗi lần mã hóa |
| Hai message dưới cùng key dùng cùng nonce | Nonce reuse phá tính an toàn | Quản lý nonce uniqueness, rotation key, giới hạn producer |
| Counter bị tràn hoặc overlap | Xử lý keystream không kiểm soát giới hạn | Kiểm soát kích thước message/counter; không để wrap |
| Giải mã AEAD rồi dùng plaintext trước khi verify | `update` có thể trả dữ liệu chưa được xác thực | Chỉ công bố dữ liệu sau `doFinal` thành công |
| Lưu nonce/AAD nhưng không có quy tắc encoding | Sender/receiver tính byte khác nhau | Chuẩn hóa packet/AAD/charset/version |
| Dùng `Cipher` chung giữa nhiều thread | `Cipher` có trạng thái mutable, không thread-safe theo cách dùng chung bất đồng bộ | Tạo `Cipher` riêng cho mỗi hoạt động; không chia sẻ đang xử lý |

## 10. Tự kiểm tra

**Câu 1.** Muốn dùng ChaCha20 thuần trong Java 11, `Cipher.getInstance(...)` và tham số `init` là gì?  
**Đáp án:** `Cipher.getInstance("ChaCha20")` cùng `ChaCha20ParameterSpec(nonce12, initialCounter)`, khóa 32 byte và `SecretKeySpec(..., "ChaCha20")`.

**Câu 2.** Vì sao `ChaCha20ParameterSpec` không đúng cho `ChaCha20-Poly1305`?  
**Đáp án:** AEAD tự quản lý counter theo thuật toán; dùng `IvParameterSpec` với nonce 12 byte.

**Câu 3.** Nếu mã hóa input theo hai chunk, chỉ lấy `doFinal(...)` có đủ không?  
**Đáp án:** Không. Phải ghép output từ **mọi `update`** cộng output của `doFinal`.

**Câu 4.** `ChaCha20` thuần có ném exception nếu ciphertext bị sửa không?  
**Đáp án:** Không tự phát hiện được; giải mã thường ra plaintext bị sửa. Cần cơ chế integrity hoặc AEAD.

**Câu 5.** `ChaCha20-Poly1305` tạo thêm bao nhiêu byte authentication tag?  
**Đáp án:** **16 byte** theo biến thể AEAD chuẩn RFC 8439.

**Câu 6.** `updateAAD(aad)` nên gọi trước hay sau `update(plaintext)`?  
**Đáp án:** **Trước**, và dùng cùng AAD lúc giải mã.

**Câu 7.** Nếu `AEADBadTagException` được ném, có thể tiếp tục sử dụng byte do `update` giải mã trước đó không?  
**Đáp án:** **Không**. Bỏ toàn bộ plaintext chưa xác thực, xử lý lỗi và không phát dữ liệu nghiệp vụ.

**Câu 8.** Nonce có cần giữ bí mật không?  
**Đáp án:** **Không**, nhưng phải **không trùng cho mỗi lần mã hóa với cùng key**.

**Câu 9.** Vì sao dùng `SecureRandom` tạo key/nonce thay cho `java.util.Random`?  
**Đáp án:** Khóa bí mật cần entropy mật mã; `Random` không phải bộ sinh số ngẫu nhiên dành cho bảo mật.

**Câu 10.** Gọi `doFinal` lần hai để mã hóa thông điệp mới bằng cùng cipher/nonce có đúng không?  
**Đáp án:** Không. Hãy `init` hoạt động mới với **nonce khác** (hoặc khóa khác đúng chính sách). Không phụ thuộc vào trạng thái reset của một provider cụ thể.

## 11. Tóm tắt ghi nhớ

```text
ChaCha20 (raw stream cipher)
    Cipher.getInstance("ChaCha20")
    init(ENCRYPT_MODE, key32, ChaCha20ParameterSpec(nonce12, counter))
    update(plaintext parts) ... doFinal(lastPart)
    output = ciphertext
    KHÔNG có authentication tag

ChaCha20-Poly1305 (AEAD)
    Cipher.getInstance("ChaCha20-Poly1305")
    init(ENCRYPT_MODE, key32, IvParameterSpec(nonce12))
    updateAAD(aad) trước dữ liệu
    update(plaintext parts) ... doFinal(lastPart)
    output = ciphertext || tag16
    decrypt + doFinal xác minh tag
```

- **`init`** chọn mode, key và parameter.
- **`update`** nhận từng phần input, output có thể xuất hiện từng phần hoặc bị buffer.
- **`doFinal`** xử lý phần còn lại và hoàn tất; **đối với AEAD, nó liên quan trực tiếp tới authentication tag**.
- Đừng mã hóa hai thông điệp bằng cùng **key + nonce**.
- Đừng phát plaintext AEAD ra ngoài trước khi `doFinal` xác thực thành công.
- Ưu tiên **ChaCha20-Poly1305** khi cần cả bảo mật nội dung lẫn chống sửa đổi.

### Tài liệu chính thức và tiêu chuẩn hiện hành

- [Java 11 — Cipher: init, update, doFinal, updateAAD, AEAD](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html)
- [Java 11 — ChaCha20ParameterSpec: 12-byte nonce và 32-bit counter](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html)
- [Java 11 — IvParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html)
- [Java 11 — SecretKeySpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html)
- [Java 11 — AEADBadTagException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/AEADBadTagException.html)
- [OpenJDK JEP 329 — ChaCha20 and Poly1305 Cryptographic Algorithms](https://openjdk.org/jeps/329)
- [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols; thay thế RFC 7539](https://www.rfc-editor.org/rfc/rfc8439.html)
- [Java 25 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html)
