# ChaCha20 trong Java 11+: Cipher, SecretKey và lựa chọn provider

> **Chủ đề cha:** ChaCha20. Bài này giải thích ba lớp API quan trọng trong Java Cryptography Architecture (JCA/JCE): `javax.crypto.Cipher` để mã hóa/giải mã, `javax.crypto.SecretKey` để biểu diễn khóa bí mật, và `java.security.Provider` để chọn implementation. Mã chạy trên Java 11+ sử dụng ChaCha20 và ChaCha20-Poly1305 được đưa vào Oracle/OpenJDK từ JDK 11 (JEP 329). Các API này vẫn được hỗ trợ trên JDK hiện đại; không sử dụng các thuật toán stream cipher cũ hoặc kỹ thuật bỏ kiểm tra xác thực.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **ChaCha20 thuần** (stream cipher, chỉ bảo mật nội dung) với **ChaCha20-Poly1305** (AEAD: mã hóa **và** kiểm tra tính toàn vẹn/xác thực dữ liệu).
2. Tạo `Cipher` bằng `Cipher.getInstance("ChaCha20")` hoặc `Cipher.getInstance("ChaCha20-Poly1305")`, rồi `init` và `doFinal` đúng cách.
3. Tạo khóa ChaCha20 256-bit bằng `KeyGenerator.getInstance("ChaCha20")`; biết khi nào dùng `SecretKeySpec` cho khóa đã được cung cấp an toàn.
4. Cấu hình nonce 12 byte và counter 32-bit bằng `ChaCha20ParameterSpec` cho ChaCha20 thuần; dùng `IvParameterSpec` cho ChaCha20-Poly1305 trong SunJCE.
5. Phân biệt **tên thuật toán Cipher**, **tên thuật toán khóa** và **tên provider**; không gọi nhầm `KeyGenerator.getInstance("ChaCha20-Poly1305")`.
6. Để JCA/JCE chọn provider mặc định, kiểm provider thực sau `init`, và chỉ định provider rõ khi compliance/hardware/key material thực sự yêu cầu.
7. Thực thi demo có khóa ngẫu nhiên, nonce ngẫu nhiên, AEAD round-trip, phát hiện sửa ciphertext/tag, và so sánh với ChaCha20 thuần.
8. Thiết kế key/nonce lifecycle an toàn: không tái sử dụng cặp **(key, nonce)** cho các lần mã hóa khác nhau, không log key, không bỏ kiểm tra tag.
9. Biết các lỗi `NoSuchAlgorithmException`, `InvalidKeyException`, `InvalidAlgorithmParameterException`, `AEADBadTagException` và cách QA bằng test matrix.

## 2. Cơ chế nền tảng: Cipher, Key, Parameters và Provider

Khi làm việc với ChaCha20, các đối tượng có nhiệm vụ khác nhau:

~~~text
Tên transformation
    |
    | Cipher.getInstance("ChaCha20-Poly1305")
    v
Cipher (engine API JCE) --------------------------+
    |                                             |
    | Cipher.init(ENCRYPT_MODE, key, params)       | Provider: SunJCE hoặc
    v                                             | provider hợp lệ khác
SecretKey (256-bit key)                           |
    +--- KeyGenerator("ChaCha20")                  |
    +--- hoặc SecretKeySpec(keyBytes, "ChaCha20")  |
                                                  |
AlgorithmParameterSpec                            |
    +--- IvParameterSpec(12-byte nonce)       <----+
             |
             v
       updateAAD(aad)  [chỉ khi AEAD]
             |
             v
       doFinal(plaintext)
             |
             v
    ciphertext || 16-byte authentication tag
~~~

**Vai trò từng API:**

| Thành phần | Câu hỏi nó trả lời | Không tự làm gì |
| --- | --- | --- |
| `Cipher` | “Tôi mã hóa/giải mã bằng transformation nào?” | Không tự bảo đảm nonce duy nhất trong toàn hệ thống |
| `SecretKey` | “Khóa bí mật nào sẽ được dùng?” | Không sinh nonce, không thực hiện mã hóa |
| `KeyGenerator` | “Sinh một khóa ngẫu nhiên hợp lệ bằng cách nào?” | Không lưu/rotate key lâu dài cho bạn |
| `SecretKeySpec` | “Bọc byte khóa đã có thành một Key object như thế nào?” | **Không** kiểm rằng byte đến từ nguồn ngẫu nhiên an toàn |
| `ChaCha20ParameterSpec` | “Nonce và block counter cho ChaCha20 thuần là gì?” | Không phải tham số cho Poly1305 của SunJCE |
| `IvParameterSpec` | “Nonce/IV nào được dùng cho ChaCha20-Poly1305?” | Không tự bảo đảm nonce chưa từng được sử dụng |
| `Provider` | “Implementation của thuật toán ở đâu?” | Không tự chứng minh thuật toán được phê duyệt theo mọi compliance regime |

**Điểm cần ghi nhớ:** `SecretKey` là interface, **không phải một kiểu khóa “khác nhau” cho mỗi chế độ**. Với Oracle/OpenJDK SunJCE, cùng khóa 256-bit có nhãn thuật toán `ChaCha20` được sử dụng cho ChaCha20 stream cipher **hoặc** ChaCha20-Poly1305; nhưng mỗi lần **mã hóa** phải có nonce mới, và nên quản lý purpose/key separation rõ ràng.

## 3. Hai transformation cần phân biệt thật rõ

### 3.1. ChaCha20: stream cipher không có authentication tag

~~~java
Cipher raw = Cipher.getInstance("ChaCha20");
~~~

ChaCha20 nhận:

- **Key:** 256 bit = 32 byte.
- **Nonce:** 96 bit = 12 byte.
- **Initial block counter:** 32-bit integer, truyền trong `ChaCha20ParameterSpec`.
- **Plaintext** và **ciphertext** có cùng số byte, vì đây là stream cipher không có padding theo block.
- **Không có authentication tag.** Việc `Cipher.doFinal` giải mã ra byte **không chứng minh** ciphertext chưa bị chỉnh sửa.

Cơ chế dùng keystream kết hợp XOR với plaintext. Nếu ai đó đổi một bit trong ciphertext, bit tương ứng của plaintext có thể bị thay đổi khi giải mã mà **không có exception**. Vì vậy, để bảo vệ dữ liệu ứng dụng một cách độc lập, **không chọn ChaCha20 thuần làm mặc định**.

### 3.2. ChaCha20-Poly1305: AEAD có kiểm tra toàn vẹn

~~~java
Cipher aead = Cipher.getInstance("ChaCha20-Poly1305");
~~~

ChaCha20-Poly1305 kết hợp:

- **ChaCha20** để mã hóa dữ liệu;
- **Poly1305** để tính/kiểm authentication tag;
- **AAD (Additional Authenticated Data)** nếu ứng dụng có metadata cần kiểm toàn vẹn nhưng **không cần mã hóa**.

Với biến thể thông dụng trong SunJCE: **nonce 12 byte**, **tag 16 byte**. Kết quả `doFinal` khi mã hóa chứa `ciphertext || tag`. Khi giải mã, `doFinal` kiểm tag; nếu ciphertext, tag, AAD, key hoặc nonce không khớp, nó thường ném `AEADBadTagException`.

**Vì sao AEAD được khuyến nghị:** nhiều ứng dụng cần cả bảo mật nội dung và bảo đảm ciphertext không bị giả mạo. ChaCha20 thuần chỉ đáp ứng phần thứ nhất; tự gắn một MAC thủ công là thiết kế khó và dễ mắc lỗi về thứ tự, key separation, message format. Với dữ liệu mới, hãy ưu tiên **ChaCha20-Poly1305** (hoặc một AEAD được hệ thống/chính sách cho phép, ví dụ AES-GCM).

### 3.3. Bảng đối chiếu

| Thuộc tính | `ChaCha20` | `ChaCha20-Poly1305` |
| --- | --- | --- |
| Kiểu thuật toán | Stream cipher | AEAD |
| Java Cipher name | `"ChaCha20"` | `"ChaCha20-Poly1305"` |
| Key | 256 bit | 256 bit |
| Nonce | 12 byte | 12 byte |
| Java 11 SunJCE parameter | `ChaCha20ParameterSpec(nonce, counter)` | `IvParameterSpec(nonce)` |
| Counter từ ứng dụng | Có, trong `ChaCha20ParameterSpec` | Không cấu hình trực tiếp; AEAD quản lý nội bộ |
| Authentication tag | **Không có** | **16 byte** |
| AAD | Không có | Có, qua `updateAAD` |
| Giải mã khi dữ liệu bị sửa | Có thể trả plaintext sai và **không báo** | Kiểm tag và từ chối khi không hợp lệ |
| Khuyến nghị cho lưu/truyền dữ liệu mới | Không dùng đơn độc nếu cần xác thực | Thường là lựa chọn phù hợp |

**Tuyệt đối không nhầm** `ChaCha20` của JCE với cipher suite TLS có tên chứa `CHACHA20_POLY1305`. TLS là giao thức riêng, JSSE thương lượng cipher suites qua TLS handshake; không phải bạn tự dùng `Cipher.getInstance(...)` để bật một TLS cipher suite trên HTTP Client.

## 4. Lấy Cipher instance: chọn đúng tên transformation

### 4.1. Tên được Oracle/OpenJDK Java 11 hỗ trợ

~~~java
Cipher stream = Cipher.getInstance("ChaCha20");
Cipher authenticated = Cipher.getInstance("ChaCha20-Poly1305");
~~~

Đây là **hai lời gọi minh họa**, cần import `javax.crypto.Cipher` và khai báo/handle ngoại lệ theo `GeneralSecurityException`.

Theo JEP 329 và tài liệu SunJCE, đây là những algorithm name thích hợp. SunJCE mô tả chúng tương ứng với `None/NoPadding` ở bảng transformation. Không tự suy diễn và viết `"ChaCha20/GCM/NoPadding"` hoặc `"ChaCha20/CBC/PKCS5Padding"`: GCM/CBC là các chế độ của những thuật toán khác, **không phải mode hợp lệ của ChaCha20**.

Với hầu hết block cipher, Oracle khuyên chỉ định transformation đầy đủ để tránh mode/padding mặc định của provider. Riêng **`"ChaCha20"` và `"ChaCha20-Poly1305"` là algorithm name có ý nghĩa xác định** trong provider hỗ trợ, nên dùng đúng các tên này; không cần tự thêm một block cipher mode tùy ý.

### 4.2. Cipher được tạo chưa sẵn sàng sử dụng

~~~java
Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");

// Chưa gọi init: không thể doFinal một payload thành công.
cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));

byte[] result = cipher.doFinal(plaintext);
~~~

Đây là **mã minh họa** trong method có `key`, `nonce` và `plaintext` đã được tạo an toàn.

`Cipher.getInstance` chỉ tìm implementation; `init` mới đặt mode, key và parameters; `doFinal` mới hoàn tất phép xử lý. Không cố gọi `doFinal` trên Cipher chưa init. Không dùng cùng `Cipher` như một singleton đa luồng: nó có **trạng thái nội bộ thay đổi**, không được xem là thread-safe.

### 4.3. “Có Cipher” chưa đồng nghĩa “đã chọn đúng provider cuối”

JCA có cơ chế provider lookup và **delayed provider selection** ở một số engine, trong đó có `Cipher`. Provider cuối cùng có thể chỉ được xác định khi `init` thấy kiểu `Key` thực tế. Vì vậy:

~~~java
Cipher c = Cipher.getInstance("ChaCha20-Poly1305");
c.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));

String selectedProvider = c.getProvider().getName();
~~~

**Mã minh họa.** Đọc `getProvider()` **sau `init`** phản ánh provider đã chọn để dùng key/parameters. Theo tài liệu JDK Security Developer's Guide, gọi `getProvider()` trước init có thể làm JDK chọn provider sớm hơn cần thiết; với key dạng HSM/opaque, điều đó có thể dẫn tới incompatibility.

## 5. SecretKey: sinh khóa đúng, không tự dùng mật khẩu làm khóa

### 5.1. Cách ưu tiên: KeyGenerator("ChaCha20")

~~~java
KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
generator.init(256);

SecretKey key = generator.generateKey();
~~~

Đây là **mã minh họa**; cần import `KeyGenerator` và `SecretKey`. `256` là số **bit**, tức 32 byte. Với SunJCE, `KeyGenerator.getInstance("ChaCha20")` tạo key phù hợp cho **cả ChaCha20 và ChaCha20-Poly1305**.

Không đặt `KeyGenerator.getInstance("ChaCha20-Poly1305")` như mặc định: trong JDK, algorithm name chuẩn cho **key generator** là `"ChaCha20"`, dù Cipher có tên `"ChaCha20-Poly1305"`.

Nếu muốn kiểm soát nguồn ngẫu nhiên:

~~~java
SecureRandom random = new SecureRandom();

KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
generator.init(256, random);

SecretKey key = generator.generateKey();
~~~

`SecureRandom` tạo ngẫu nhiên có chất lượng mật mã theo provider. **Không dùng `java.util.Random`, thời gian hiện tại, UUID ngẫu nhiên rồi cắt ghép, hay chuỗi ASCII cố định** làm key production. Một key 256-bit cần đủ entropy; kích thước 32 byte **không tự làm** một khóa yếu thành mạnh.

### 5.2. SecretKeySpec: khi đã có raw key bytes đúng cách

~~~java
byte[] keyBytes = loadKeyFromSecureStore(); // Helper do ứng dụng cung cấp.

if (keyBytes.length != 32) {
    throw new IllegalArgumentException("Expected 32-byte ChaCha20 key");
}

SecretKey key = new SecretKeySpec(keyBytes, "ChaCha20");
~~~

**Đoạn minh họa**, cần triển khai `loadKeyFromSecureStore()`, import `SecretKeySpec` và `SecretKey`. `SecretKeySpec` chỉ **bọc byte và tên thuật toán**; nó không lấy dữ liệu từ KMS/HSM, không tạo ngẫu nhiên, không xác thực rằng nguồn dữ liệu đáng tin và không bảo đảm key được lưu an toàn.

**Không làm:**

~~~java
// SAI: mật khẩu UTF-8 không phải key 256-bit ngẫu nhiên.
byte[] keyBytes = password.getBytes(StandardCharsets.UTF_8);
SecretKey wrong = new SecretKeySpec(keyBytes, "ChaCha20");
~~~

Đoạn sai là ví dụ anti-pattern; `password` là biến giả định. Nếu phải mã hóa bằng mật khẩu người dùng, cần **password-based KDF** phù hợp chính sách, random salt, work factor và quản lý key. Không đổi mật khẩu trực tiếp thành key bằng cách `getBytes`/truncate/hash đơn giản rồi xem như an toàn.

### 5.3. Key.getAlgorithm() và getEncoded()

`SecretKey` kế thừa `Key`:

| API | Ý nghĩa | Điều cần cảnh giác |
| --- | --- | --- |
| `key.getAlgorithm()` | Tên thuật toán, thường `ChaCha20` | Không cho biết key có được bảo vệ an toàn hay không |
| `key.getFormat()` | Format biểu diễn key, nếu xuất khẩu được | Opaque/HSM key có thể không có format xuất khẩu |
| `key.getEncoded()` | Byte key theo format hoặc `null` | Không log/in/đưa trực tiếp vào JSON/API response |
| `key.getClass()` | Kiểu class của Key implementation | Không dùng để suy diễn luôn có raw bytes |
| `KeyGenerator.getProvider()` | Provider tạo key | Có thể khác provider thực của `Cipher` khi key được chuyển qua hợp lệ |

Trong demo với software provider SunJCE, `getEncoded()` trả 32 byte. Trong production, **HSM/token key** có thể không cho xuất raw bytes, nên `getEncoded() == null` là tình huống có thật chứ không nhất thiết là lỗi.

**Quản lý key:** dùng KMS/HSM/keystore theo mức bảo vệ cần thiết; kiểm quyền truy cập, vòng đời, rotation, key ID, backup/recovery, key separation và xóa dữ liệu nhạy cảm khi có thể. Đừng serialize raw key vào file cạnh ciphertext chỉ để tiện giải mã.

## 6. Parameters: nonce, counter và AAD là phần không thể bỏ qua

### 6.1. ChaCha20 thuần: ChaCha20ParameterSpec

~~~java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

ChaCha20ParameterSpec params =
        new ChaCha20ParameterSpec(nonce, 1);

Cipher raw = Cipher.getInstance("ChaCha20");
raw.init(Cipher.ENCRYPT_MODE, key, params);
byte[] encrypted = raw.doFinal(plaintext);
~~~

Đây là **đoạn minh họa**; cần import `ChaCha20ParameterSpec`, `Cipher`, `SecureRandom` và có `key`/`plaintext`.

Theo API Java 11:

- `nonce` phải **đúng 12 byte**; `ChaCha20ParameterSpec` từ chối chiều dài khác.
- `counter` là số nguyên 32-bit (`int`). Trong ví dụ chọn **1**. Counter là **block counter**, không phải số message hay số nonce.
- Provider SunJCE kiểm kiểu parameter cho ChaCha20. Không dùng `IvParameterSpec` thay thế `ChaCha20ParameterSpec` cho ChaCha20 thuần.
- Đừng tự tăng `counter` để “tái sử dụng cùng nonce nhiều message” một cách tùy tiện: dễ làm các phần keystream trùng nhau, nhất là khi dữ liệu thay đổi kích thước. **Chiến lược an toàn hơn là mỗi lần mã hóa dùng nonce khác dưới cùng key**.

`ChaCha20ParameterSpec.getNonce()` trả bản sao array. Nhưng việc API sao chép dữ liệu **không thay thế** việc thiết kế tính duy nhất của nonce. Một nonce không cần bí mật; một nonce **bị tái sử dụng với cùng key** có thể phá bảo mật.

### 6.2. ChaCha20-Poly1305: IvParameterSpec

~~~java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

Cipher aead = Cipher.getInstance("ChaCha20-Poly1305");
aead.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));

aead.updateAAD("header-v1".getBytes(StandardCharsets.UTF_8));
byte[] sealed = aead.doFinal(plaintext);
~~~

Đây là **đoạn minh họa**. Trong SunJCE, `ChaCha20-Poly1305` dùng **`IvParameterSpec` với nonce đúng 12 byte**; không dùng `ChaCha20ParameterSpec` (với counter) để init AEAD. Counter nội bộ theo thiết kế ChaCha20-Poly1305, ứng dụng **không phải** tự cung cấp.

**AAD** (Additional Authenticated Data):

- Là dữ liệu **được xác thực nhưng không mã hóa**: ví dụ version, purpose, tenant ID hoặc record ID.
- Bên nhận phải cung cấp **cùng dãy byte AAD** trước `doFinal` giải mã.
- Nếu AAD khác, việc kiểm authentication tag thất bại.
- Phải gọi `updateAAD(...)` **trước** khi xử lý plaintext/ciphertext qua `update(...)` hoặc `doFinal(...)`.
- AAD không thay thế authentication/authorization của ứng dụng; nó bảo vệ sự gắn kết dữ liệu với metadata đã được xác định.

### 6.3. Nonce có phải một bí mật?

**Không.** Nonce thường được lưu cạnh ciphertext. Tuy nhiên nó phải **không trùng cho mỗi lần mã hóa dưới một key**. Với nonce 96-bit ngẫu nhiên, xác suất va chạm rất nhỏ ở quy mô vừa phải nhưng **không bằng không** và tăng theo số lần mã hóa (birthday bound). Với khối lượng rất lớn, nhiều process hoặc key sống lâu, cân nhắc một nonce manager dựa trên counter/epoch được cấp phát và lưu bền vững, hoặc chính sách rotate key. Đừng tạo nonce bằng `System.currentTimeMillis()`, PID hoặc từ một bộ đếm bị reset khi restart.

**Key rotation không sửa được ciphertext cũ bị lộ do reuse nonce**. Đây là yêu cầu thiết kế trước khi đưa hệ thống vào vận hành.

## 7. Chương trình Java 11+ hoàn chỉnh, đã kiểm thử với JDK

Bài demo sau kết nối đầy đủ ba nội dung **Cipher + SecretKey + Provider**:

1. Sinh `SecretKey` ChaCha20 256-bit bằng `KeyGenerator`.
2. Chọn `Cipher.getInstance("ChaCha20-Poly1305")` **không pin provider**.
3. Mã hóa một nội dung text nhỏ với **nonce 12 byte + AAD** và kiểm ciphertext dài hơn plaintext 16 byte do tag.
4. Giải mã và kiểm round-trip.
5. Sửa một bit của tag, kiểm `AEADBadTagException`.
6. Tạo nonce khác để mã hóa/giải mã ChaCha20 **thuần** bằng `ChaCha20ParameterSpec`; minh họa raw stream cipher **không tự phát hiện** ciphertext bị sửa.
7. Ghi provider **sau init** để phản ánh implementation thực.

Tạo tệp **`ChaCha20ProviderDemo.java`**:

~~~java
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;

public class ChaCha20ProviderDemo {

    public static void main(String[] args) throws Exception {
        SecureRandom rng = new SecureRandom();

        KeyGenerator keyGen = KeyGenerator.getInstance("ChaCha20");
        keyGen.init(256, rng);
        SecretKey key = keyGen.generateKey();

        System.out.println("key.algorithm=" + key.getAlgorithm());
        System.out.println("key.bytes=" + key.getEncoded().length);

        // Mỗi lần ENCRYPT dùng nonce mới; nonce không cần bí mật.
        byte[] nonce = new byte[12];
        rng.nextBytes(nonce);

        byte[] aad = "metadata-v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] clear = "Hello ChaCha20"
                .getBytes(StandardCharsets.UTF_8);

        // AEAD: ciphertext + authentication tag.
        Cipher seal = Cipher.getInstance("ChaCha20-Poly1305");
        seal.init(Cipher.ENCRYPT_MODE, key,
                new IvParameterSpec(nonce));
        seal.updateAAD(aad);

        byte[] sealed = seal.doFinal(clear);
        System.out.println("aead.provider="
                + seal.getProvider().getName());
        System.out.println("aead.tagBytes="
                + (sealed.length - clear.length));

        Cipher open = Cipher.getInstance("ChaCha20-Poly1305");
        open.init(Cipher.DECRYPT_MODE, key,
                new IvParameterSpec(nonce));
        open.updateAAD(aad);

        byte[] result = open.doFinal(sealed);
        System.out.println("aead.roundTrip="
                + Arrays.equals(clear, result));

        // Thử sửa tag trong dữ liệu nhận được.
        byte[] tampered = sealed.clone();
        tampered[tampered.length - 1] ^= 1;

        boolean rejected = false;
        Cipher verify = Cipher.getInstance("ChaCha20-Poly1305");
        verify.init(Cipher.DECRYPT_MODE, key,
                new IvParameterSpec(nonce));
        verify.updateAAD(aad);

        try {
            verify.doFinal(tampered);
        } catch (AEADBadTagException expected) {
            rejected = true;
        }

        System.out.println("aead.tamperRejected=" + rejected);

        // ChaCha20 THUẦN: dùng nonce KHÁC nonce của AEAD.
        byte[] nonce2 = new byte[12];

        do {
            rng.nextBytes(nonce2);
        } while (Arrays.equals(nonce2, nonce));

        ChaCha20ParameterSpec parameters =
                new ChaCha20ParameterSpec(nonce2, 1);

        Cipher raw = Cipher.getInstance("ChaCha20");
        raw.init(Cipher.ENCRYPT_MODE, key, parameters);
        byte[] rawCiphertext = raw.doFinal(clear);

        Cipher rawDecode = Cipher.getInstance("ChaCha20");
        rawDecode.init(Cipher.DECRYPT_MODE, key, parameters);

        System.out.println("raw.provider="
                + raw.getProvider().getName());
        System.out.println("raw.roundTrip="
                + Arrays.equals(clear,
                        rawDecode.doFinal(rawCiphertext)));

        // Sửa ciphertext thuần: không có tag để báo lỗi.
        byte[] changed = rawCiphertext.clone();
        changed[0] ^= 1;

        Cipher altered = Cipher.getInstance("ChaCha20");
        altered.init(Cipher.DECRYPT_MODE, key, parameters);

        System.out.println("raw.tamperingIsUndetected="
                + !Arrays.equals(clear, altered.doFinal(changed)));
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac ChaCha20ProviderDemo.java
java ChaCha20ProviderDemo
~~~

Có thể kiểm tính tương thích API Java 11 bằng JDK mới:

~~~bash
javac --release 11 ChaCha20ProviderDemo.java
java ChaCha20ProviderDemo
~~~

**Stdout đã chạy kiểm chứng trên OpenJDK 24.0.2 có provider SunJCE:**

~~~text
key.algorithm=ChaCha20
key.bytes=32
aead.provider=SunJCE
aead.tagBytes=16
aead.roundTrip=true
aead.tamperRejected=true
raw.provider=SunJCE
raw.roundTrip=true
raw.tamperingIsUndetected=true
~~~

**Giải thích từng dòng:**

1. `key.algorithm=ChaCha20`: đúng algorithm name của key generator.
2. `key.bytes=32`: key từ **software SunJCE** trong demo có `getEncoded()` dài 32 byte; key không xuất khẩu được của HSM có thể trả `null` nên không dùng dòng in này như logic production tổng quát.
3. `aead.provider=SunJCE`: provider của `Cipher` AEAD **sau init** trong môi trường thử. JVM có provider khác có thể in tên khác, không có nghĩa phép mã hóa khác chuẩn nếu implementation tuân thủ đặc tả.
4. `aead.tagBytes=16`: ChaCha20-Poly1305 tạo tag 128-bit, ciphertext AEAD dài hơn plaintext 16 byte.
5. `aead.roundTrip=true`: cùng key, nonce và AAD, giải mã nhận lại nội dung ban đầu. **Dùng lại nonce để DECRYPT chính ciphertext là bình thường**; điều bị cấm là dùng lại nonce để **ENCRYPT một message khác dưới cùng key**.
6. `aead.tamperRejected=true`: đổi một bit trong tag khiến kiểm xác thực thất bại; `AEADBadTagException` được bắt đúng.
7. `raw.provider=SunJCE` và `raw.roundTrip=true`: ChaCha20 thuần với nonce/counter giống nhau giữa một phép mã hóa và giải mã phục hồi plaintext.
8. `raw.tamperingIsUndetected=true`: đổi một bit của ciphertext thuần làm plaintext giải mã khác bản gốc mà **không có tag để báo lỗi**. Điều này không có nghĩa sửa dữ liệu được cho phép; nó chứng minh không nên dùng raw ChaCha20 đơn độc cho dữ liệu cần tính toàn vẹn.

**Phạm vi demo:** Các nonce được sinh ngẫu nhiên và không in ra để stdout ổn định. Ứng dụng thật cần lưu **nonce + ciphertext/tag + định dạng/phiên bản + key ID** an toàn để có thể giải mã sau khi restart; demo giữ tất cả trong một process. Hai lần giải mã khác nhau của cùng ciphertext trong demo **không tạo hai lần mã hóa mới**, do đó không vi phạm quy tắc nonce duy nhất của encryption.

## 8. Lựa chọn provider theo JCA/JCE

### 8.1. Mặc định: không pin tên provider

~~~java
Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");

cipher.init(Cipher.ENCRYPT_MODE, key,
        new IvParameterSpec(nonce));

System.out.println(cipher.getProvider().getName());
~~~

Đây là **đoạn minh họa**. `Cipher.getInstance(transformation)` cho JCA chọn một provider có implementation phù hợp theo **thứ tự ưu tiên và khả năng nhận key**. Cấu hình provider có thể đến từ JDK, `java.security`, security policy, hoặc provider ngoài do ứng dụng cài đặt.

Tài liệu Oracle cho biết **ứng dụng tổng quát không nên cố định provider** khi không có nhu cầu cụ thể, vì:

- Ở JDK/vendor khác có thể không có provider đó;
- Một provider mới có thể hỗ trợ hardware acceleration hoặc cấu hình chuyên dụng tốt hơn;
- Key ở HSM/PKCS#11 có thể không xuất được và chỉ dùng được với một provider tương thích;
- Pin `SunJCE` có thể làm code mất tính di động hoặc không dùng được hardware-backed key;
- Dùng tên provider không đúng không tự làm thuật toán “an toàn hơn”.

**Khuyến nghị:** chỉ định **tên transformation đúng**, dùng key/params đúng, để JCA chọn provider rồi **ghi nhận provider thực sau init** khi cần chẩn đoán.

### 8.2. SunJCE là gì?

Trong Oracle/OpenJDK phổ biến, `SunJCE` là provider JCE đi kèm JDK; tài liệu JDK 11 và JDK mới liệt kê:

- `Cipher`: `ChaCha20`, `ChaCha20-Poly1305`;
- `KeyGenerator`: `ChaCha20`, key 256-bit;
- Các thuật toán và ciphers khác của JCA/JCE.

Tên `SunJCE` ở đây **mô tả implementation của một bản phân phối JDK**, không phải phần bắt buộc của một đoạn code chạy trên mọi Java runtime. Một máy có thể có provider FIPS, PKCS#11 hoặc provider doanh nghiệp khác.

Không được kết luận “mọi provider có Cipher ChaCha20 đều có KeyGenerator ChaCha20” hoặc “mọi provider có cả hai Cipher đều nhận mọi dạng SecretKey”. **Khả năng sử dụng phụ thuộc service type, algorithm, key representation, parameter support và policy.**

### 8.3. Khi nào mới nên chọn provider tường minh?

~~~java
Cipher cipher = Cipher.getInstance(
        "ChaCha20-Poly1305", selectedProvider);
~~~

**Đoạn minh họa**, `selectedProvider` là một `java.security.Provider` đã được chọn/kiểm chứng. Overload nhận đối tượng `Provider` không bắt buộc đối tượng phải nằm trong danh sách registry, nhưng provider phải triển khai thuật toán và chấp nhận key/params.

Chỉ pin khi có **lý do rõ ràng**:

- Compliance/FIPS hoặc certification yêu cầu một provider đã được chấp thuận;
- Key thuộc HSM/token và implementation phải chạy bên trong provider của thiết bị;
- Bài kiểm thử/benchmark cần so sánh **một implementation cụ thể**;
- Có yêu cầu vận hành đã đánh giá về provider/version và compatibility.

**Lưu ý FIPS:** không mặc định ChaCha20-Poly1305 được phép trong mọi môi trường FIPS/compliance. Việc provider có thuật toán **không đồng nghĩa** thuật toán/đường thực thi đó đã được chuẩn/chứng nhận của tổ chức cho phép. Nếu policy chỉ cho một tập thuật toán khác, phải chọn phương án được security team phê duyệt thay vì bypass policy.

### 8.4. Chọn tên provider có rủi ro gì?

~~~java
// Ví dụ chỉ hợp lệ khi provider có tên SunJCE đã được cài đặt.
Cipher pinned = Cipher.getInstance(
        "ChaCha20-Poly1305", "SunJCE");
~~~

Đoạn trên **không phải cách viết khuyến nghị mặc định**. Nếu provider đó không có, có thể nhận `NoSuchProviderException`; nếu provider tồn tại nhưng không hỗ trợ transformation thì có `NoSuchAlgorithmException` hoặc `NoSuchPaddingException` tùy yêu cầu.

Nếu key không thuộc định dạng mà provider đã pin chấp nhận, có thể gặp `InvalidKeyException` tại `init`. Một provider có sẵn trong runtime **chưa bảo đảm** dùng được với key cụ thể.

### 8.5. Liệt kê provider phục vụ chẩn đoán

~~~java
for (Provider provider : Security.getProviders()) {
    Provider.Service service =
            provider.getService(
                    "Cipher", "ChaCha20-Poly1305");

    if (service != null) {
        System.out.println(
                provider.getName() + " supports Cipher:"
                        + service.getAlgorithm());
    }
}
~~~

**Mã minh họa** trong một method, cần import `java.security.Provider` và `Security`. Không có stdout cố định vì danh sách provider thay đổi theo JDK/vendor/cấu hình.

Có thể dùng:

~~~java
Provider[] candidates =
        Security.getProviders("Cipher.ChaCha20-Poly1305");
~~~

Đây là **đoạn minh họa**. `candidates` có thể là `null` khi không có provider đăng ký phù hợp; cần kiểm trước khi duyệt.

**Quan trọng:** `getService(...) != null` chỉ cho thấy provider đăng ký service; vẫn phải thử `Cipher.init(...)` với **key và params thực** và test round-trip/authentication. Đó mới là cách kiểm khả năng tương thích của một provider trong ứng dụng.

## 9. Delayed provider selection và khả năng tương thích khóa

JCA/JCE hỗ trợ lựa chọn provider muộn với một số engine như `Cipher`. Điều này đặc biệt hữu ích khi ứng dụng dùng khóa có nguồn gốc từ HSM.

### Ví dụ tình huống

~~~text
KMS/HSM trả SecretKey (opaque, getEncoded() == null)
             |
             v
Cipher.getInstance("ChaCha20-Poly1305")
             |
             v
Cipher.init(..., opaqueKey, params)
             |
             +---- Provider A: chỉ nhận software raw key -> không phù hợp
             |
             +---- Provider B: quản lý khóa trong HSM -> có thể phù hợp
             |
             v
getProvider() sau init -> provider đã được chọn thực tế
~~~

Đây là **mô hình khái niệm**, không khẳng định một HSM cụ thể hỗ trợ ChaCha20-Poly1305.

**Rủi ro nếu gọi `getProvider()` quá sớm:** Security Developer's Guide mô tả việc gọi `getProvider()` trước `Cipher.init(...)` có thể thúc đẩy chọn một provider khi chưa có key để đánh giá, khiến khóa hardware-backed không tương thích. Vì thế:

1. Lấy Cipher theo transformation, không pin provider nếu chưa có lý do.
2. Cung cấp **SecretKey** và **nonce/params** tại `init`.
3. Khi init thành công, đọc `cipher.getProvider()` để audit.
4. Tạo Cipher instance mới nếu cần một ngữ cảnh khác hoặc provider có thể thay đổi theo key. Đừng dựa vào việc tự reselection khi reuse cùng object đã init.
5. Không giải quyết bằng cách xuất private/raw key ra bộ nhớ nếu policy cấm. Hãy kiểm provider/algorithm support hoặc chọn thiết kế crypto phù hợp.

### KeyGenerator và Cipher có thể có provider khác

~~~java
KeyGenerator keygen = KeyGenerator.getInstance("ChaCha20");
SecretKey key = keygen.generateKey();

Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
cipher.init(Cipher.ENCRYPT_MODE, key,
        new IvParameterSpec(freshNonce));

System.out.println(keygen.getProvider().getName());
System.out.println(cipher.getProvider().getName());
~~~

**Mã minh họa**, cần khai báo `freshNonce` đúng 12 byte. Hai tên provider **có thể khác**. Không mặc định vì `KeyGenerator` đến từ provider X thì `Cipher` nhất thiết đến từ provider X.

## 10. Thiết kế định dạng dữ liệu mã hóa và giải mã an toàn

`Cipher.doFinal` không tự tạo file format có version, key ID hoặc lưu nonce vào nơi khác. Ứng dụng phải thiết kế **định dạng thông điệp** nếu muốn lưu ciphertext.

Ví dụ sơ đồ:

~~~text
+---------+------------------+----------------+---------------------+
| version | key-id / context | nonce (12 B)   | ciphertext || tag   |
+---------+------------------+----------------+---------------------+
        metadata được kiểm qua AAD     phần mã hóa và gắn tag
~~~

Một format production tốt thường có:

- **Version:** một giá trị/byte version để hỗ trợ migration giữa các thuật toán.
- **Key ID:** tham chiếu đến khóa được lưu an toàn, **không phải raw key**.
- **Nonce:** 12 byte công khai; giải mã cần cùng nonce.
- **Ciphertext + tag:** phần đã mã hóa và xác thực.
- **AAD:** gắn version/key-id/context với ciphertext nếu cần, theo một encoding duy nhất và được bảo đảm kiểm đúng phía giải mã.
- **Length bounds:** từ chối dữ liệu quá lớn/format sai trước khi cấp phát.
- **Canonical encoding:** các trường metadata có quy tắc encode độ dài rõ ràng để tránh nhập nhằng ghép chuỗi.

### Một ví dụ AAD hợp lý

Nếu một bản ghi thuộc về tenant `tenant-42` và version `v1`:

~~~java
byte[] aad = "v1|tenant-42"
        .getBytes(StandardCharsets.UTF_8);
~~~

Đây là **đoạn minh họa**. Trong thiết kế thật, không nên ghép delimiter mù quáng nếu tên tenant/key ID có thể chứa chính delimiter. Dùng encoding độ dài cố định, cấu trúc protobuf/CBOR có quy tắc canonical hoặc schema rõ ràng.

**AAD không bị mã hóa.** Không đưa bí mật vào AAD rồi cho rằng nội dung đó đã được che. AAD giúp phát hiện việc sửa metadata nhưng không thay thế kiểm quyền xem bản ghi của tenant.

### Giải mã và kiểm tag trước khi sử dụng plaintext

~~~java
Cipher open = Cipher.getInstance("ChaCha20-Poly1305");
open.init(Cipher.DECRYPT_MODE, key,
        new IvParameterSpec(nonce));

open.updateAAD(aad);
byte[] plaintext = open.doFinal(ciphertextAndTag);
~~~

Đây là đoạn minh họa. Với dữ liệu không tin cậy, chỉ **sử dụng/công bố plaintext sau khi `doFinal` xác thực thành công**. Không gửi plaintext chưa xác thực cho parser, logger, UI hoặc database khi tag chưa được kiểm.

**Không thay thế `AEADBadTagException` bằng fallback “cứ giải mã tiếp”**. Tag sai là lỗi bảo mật/tính toàn vẹn, không phải warning nhỏ.

## 11. Reuse nonce là lỗi nghiêm trọng, không phải tối ưu hóa

Nguyên tắc bất biến: **đối với mỗi key, nonce của hai phép mã hóa khác nhau phải khác nhau**.

| Tình huống | Có chấp nhận? | Vì sao |
| --- | --- | --- |
| Encrypt message A với (key K, nonce N) | Có, nếu N mới | Một lần sử dụng cặp K,N |
| Decrypt ciphertext của A với (K,N) | **Có** | Bên nhận phải dùng đúng key/nonce để xác thực/giải mã |
| Encrypt message B khác với (K,N) | **Không** | Nonce reuse gây phá bảo mật |
| Encrypt B với (K,N2) khác N | Có, nếu đảm bảo uniqueness và policy | Cặp key+nonce mới |
| Encrypt B với (K2,N) khóa khác K | Có thể, nếu key separation đúng | Quy tắc uniqueness áp theo key |
| Đổi mỗi initial counter với cùng K,N để encrypt B | Không nên làm tùy tiện | Có nguy cơ tái dùng/chồng lấp keystream, khó audit |
| Sinh N từ thời gian hoặc một counter khởi động lại | Không an toàn | Có thể trùng nonce sau restart hoặc trên nhiều process |
| Sinh ngẫu nhiên 96-bit nonce bằng SecureRandom | Thực dụng cho quy mô vừa phải | Có xác suất va chạm; hệ thống cần định lượng, theo dõi key lifetime |
| Counter nonce duy nhất được phân phối/persist | Có thể phù hợp quy mô lớn | Cần tránh trùng khi failover/restart/sharding |

Một số provider có thể từ chối reuse nonce trên **cùng Cipher object** hoặc mode nhất định. Nhưng **đừng dựa vào provider phát hiện được nonce đã dùng bởi một Cipher object khác, process khác hoặc lần restart trước**. Quy tắc uniqueness là trách nhiệm của thiết kế ứng dụng.

### Khi ứng dụng dùng nhiều process

Mỗi worker độc lập gọi `new SecureRandom().nextBytes(nonce)` cho cùng một key là thiết kế có xác suất va chạm thấp ở quy mô vừa phải, nhưng không phải lời bảo đảm “unique tuyệt đối”. Với hàng tỷ message, backup/restore hoặc failover, hãy dùng một phương án cấp nonce/epoch đã được đánh giá và kiểm thử concurrency. Không đặt counter vào `String.format("%d", System.currentTimeMillis())` rồi xem là 12-byte nonce an toàn.

## 12. Vòng đời Cipher và thao tác update/doFinal

### 12.1. Cipher không phải đối tượng nên chia sẻ giữa các thread

Mỗi Cipher có internal state: mode, key, nonce/counter, lượng dữ liệu đã xử lý, AAD và auth state.

**Không nên:**

~~~java
// Anti-pattern minh họa:
static final Cipher SHARED = Cipher.getInstance(
        "ChaCha20-Poly1305");

// Sau đó nhiều thread cùng gọi init/update/doFinal trên SHARED.
~~~

Đây là **mã anti-pattern**, và khai báo static như trên cần xử lý checked exception nên không phải class chạy độc lập. Dù bạn có khóa đồng bộ, **mỗi phép encrypt phải có nonce mới**; có một Cipher singleton dễ dẫn tới state/reinit misuse.

**Nên:** tạo Cipher mới cho từng thao tác hoặc quản lý mỗi Cipher bằng lifecycle riêng rõ ràng; dùng `SecretKey` theo key management policy, nonce manager thread-safe và kiểm tài nguyên.

### 12.2. Tách updateAAD, update, doFinal theo đúng thứ tự

~~~java
Cipher seal = Cipher.getInstance("ChaCha20-Poly1305");
seal.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));

seal.updateAAD(aad);             // AAD TRƯỚC payload.
byte[] firstPart = seal.update(part1);
byte[] lastPart = seal.doFinal(part2);
~~~

Đoạn minh họa; với một số provider, `update` có thể trả mảng rỗng hoặc `null` tùy buffering. Không giả định số byte trả ở mỗi `update` bằng số byte đầu vào. Đối với AEAD, authentication tag được đưa vào output hoàn tất; xử lý đúng cách nếu dùng API nhiều phần.

### 12.3. Đừng dùng CipherInputStream để “nuốt” lỗi tag

Javadoc Java 11 của `CipherInputStream` cảnh báo lớp này có thể bắt lỗi `BadPaddingException`/kiểm toàn vẹn và **không chuyển tiếp** cho caller trong một số trường hợp. Vì vậy ứng dụng yêu cầu authenticated decryption nên cân nhắc **Cipher API trực tiếp** để bắt được lỗi tag.

Với file lớn, có thể làm streaming theo format có cap và **quarantine plaintext chưa xác thực** cho tới khi `doFinal` thành công. Không publish file tạm hoặc stream plaintext đến người dùng khi kiểm tag chưa hoàn tất.

**Không có nghĩa mọi file lớn đều phải đọc toàn bộ vào RAM**: hãy dùng thiết kế streaming AEAD đúng với provider và hệ thống storage an toàn, giới hạn kích thước, xử lý exception/cleanup cụ thể.

## 13. Khi có lỗi, phân loại đúng tầng

| Hiện tượng | Loại lỗi / nguyên nhân thường gặp | Điều nên làm |
| --- | --- | --- |
| `Cipher.getInstance("ChaCha20")` thất bại | `NoSuchAlgorithmException` hoặc `NoSuchPaddingException` (nếu transformation có padding) | Kiểm runtime/provider/transformation |
| `Cipher.getInstance("ChaCha20-Poly1305","X")` thất bại | `NoSuchProviderException` hoặc algorithm unsupported | Bỏ pin không cần thiết hoặc cài/cấu hình provider phù hợp |
| `KeyGenerator.getInstance("ChaCha20")` không tồn tại | `NoSuchAlgorithmException` | Kiểm provider/runtime và thuật toán được hỗ trợ |
| Key sai chiều dài | `InvalidKeyException` tại `init` | Dùng key 32 byte từ KMS hoặc KeyGenerator |
| Nonce AEAD sai 12 byte | `InvalidAlgorithmParameterException` với SunJCE | Chọn `IvParameterSpec` đúng 12 byte |
| Nonce raw ChaCha20 sai 12 byte | `IllegalArgumentException` tại `ChaCha20ParameterSpec` | Validate nonce trước |
| Dùng `ChaCha20ParameterSpec` cho AEAD | `InvalidAlgorithmParameterException` với SunJCE | Dùng `IvParameterSpec` |
| Dùng `IvParameterSpec` cho raw | `InvalidAlgorithmParameterException` với SunJCE | Dùng `ChaCha20ParameterSpec` |
| Cipher chưa `init` mà gọi `doFinal` | `IllegalStateException` | Khởi tạo mode/key/params trước |
| Ciphertext/tag/AAD sai khi giải mã AEAD | `AEADBadTagException` / `BadPaddingException` theo provider | Từ chối dữ liệu; **không dùng plaintext** |
| Chia sẻ Cipher giữa thread | State corruption / lỗi bất định | Mỗi operation có state riêng |
| Provider ép cứng không nhận HSM key | `InvalidKeyException`/unsupported | Chọn provider tương thích với key |
| Key không xuất được | `getEncoded()==null` | Dùng handle của HSM, không cố ép export |
| Không lưu nonce cùng ciphertext | Không thể giải mã/kiểm tag sau restart | Lưu nonce/version/key-ID theo format có xác thực |
| Dùng raw ChaCha20, ciphertext bị sửa | Có thể **không có exception** | Chọn AEAD để kiểm integrity |
| Reuse nonce với cùng key | Lỗ hổng mật mã nghiêm trọng | Nonce manager/key rotation; kiểm thiết kế trước triển khai |

**Lưu ý về exception message:** không assert nguyên văn thông điệp lỗi do JDK/provider tạo ra như một API ổn định; dùng **loại exception** và tình huống đã kiểm soát. Không log full key, plaintext, nonce reuse details nhạy cảm hay ciphertext tag thô để “debug”.

## 14. Kiểm thử tích hợp provider và tính đúng đắn

Đừng chỉ test rằng `Cipher.getInstance(...)` trả đối tượng. Một implementation phải được kiểm với **key đúng, nonce đúng, AAD đúng, bad tag, và provider mục tiêu**.

### Ma trận test

| Test | Kỳ vọng |
| --- | --- |
| `KeyGenerator("ChaCha20")` 256-bit | Key đúng size, dùng được với cipher mục tiêu |
| ChaCha20-Poly1305 round-trip | Plaintext phục hồi nguyên byte |
| ChaCha20-Poly1305 đổi ciphertext | `AEADBadTagException` |
| ChaCha20-Poly1305 đổi tag | `AEADBadTagException` |
| ChaCha20-Poly1305 đổi AAD | `AEADBadTagException` |
| ChaCha20-Poly1305 đổi nonce | Tag sai, giải mã bị từ chối |
| ChaCha20-Poly1305 sai key | Tag sai, giải mã bị từ chối |
| ChaCha20-Poly1305 empty plaintext | Vẫn có tag, test round-trip đúng |
| ChaCha20 raw round-trip | Byte giải mã đúng với nonce/counter phù hợp |
| ChaCha20 raw bị sửa ciphertext | Không được coi plaintext đã xác thực |
| Key 16 byte | Bị từ chối với ChaCha20 256-bit |
| Nonce 11 hoặc 13 byte | Bị từ chối theo đúng parameter spec/provider |
| Provider không có Cipher service | Báo unsupported, không silent fallback sang thuật toán khác |
| Explicit provider hỗ trợ nhưng key không hợp lệ | `init` thất bại có thể quan sát |
| Key HSM không xuất được | Không phụ thuộc `getEncoded()`; dùng provider phù hợp |
| Nhiều thread encrypt cùng key | Các nonce phải khác nhau, không chia sẻ Cipher state |
| Restart/failover nonce manager | Không tái dùng cặp key+nonce cũ |
| Test vector RFC chính thức | Ciphertext/tag khớp giá trị kỳ vọng của algorithm, tránh chỉ test tự encrypt/decrypt |

### Vì sao cần official test vectors?

Round-trip có thể **thành công cả khi cùng một provider có lỗi đối xứng trong cả encrypt/decrypt**. Khi đánh giá crypto implementation hoặc một provider mới, kiểm thêm **known-answer vectors** từ RFC 8439 và những case biên (nonce, counter, empty plaintext, AAD, tag), không chỉ tự round-trip.

Các test bằng Java 11 nên chạy trên **cả JDK target và provider/cấu hình production thực**; không lấy kết quả SunJCE của một máy để suy đoán rằng HSM/FIPS provider khác đều có cùng behavior.

### Unit test và integration test khác nhau

- **Unit test**: kiểm validator length/format, nonce-manager, key-ID encoding, xử lý exception và không lộ dữ liệu.
- **Integration test**: chạy `Cipher.init/doFinal` trên provider thật với key thật đã được cấp trong môi trường test; kiểm kết quả và bad tag.
- **Security test**: kiểm không reuse nonce giữa nhiều node, không xuất key ngoài policy, không bypass tag, không pin provider ngoài chính sách.
- **Regression test**: chạy lại sau khi JDK/provider được nâng cấp; một thay đổi ưu tiên provider có thể làm lộ lỗi tương thích với hardware key.

## 15. Lựa chọn thực tế theo kịch bản

| Nhu cầu | Gợi ý |
| --- | --- |
| Ứng dụng Java 11+ mã hóa dữ liệu nhỏ theo khóa bí mật | `ChaCha20-Poly1305` với 256-bit SecretKey, nonce 12 byte duy nhất, AAD khi cần |
| Muốn giải mã lại sau restart | Quản lý key và key-ID riêng, lưu nonce và ciphertext+tag theo versioned format |
| Muốn kiểm provider đang dùng | `cipher.getProvider()` **sau init** |
| Muốn portability across JVM | Dùng `Cipher.getInstance("ChaCha20-Poly1305")` không pin provider, kiểm support của runtime |
| Dùng key trong HSM | Chọn provider phù hợp với key, không đòi `getEncoded()` |
| Compliance bắt buộc provider cụ thể | Pin theo chính sách đã phê duyệt; test trên môi trường thật |
| Hệ thống chỉ dùng TLS/HTTPS | Để JSSE/HTTP client thương lượng TLS; không tự dùng `Cipher` cho TLS record layer |
| Chỉ cần XOR keystream mà không cần integrity | Hiểu hạn chế raw ChaCha20; trong ứng dụng mới thường vẫn chọn AEAD |
| Mã hóa file rất lớn | Có stream processing có giới hạn, xác thực trước publish, cleanup tệp tạm |
| Nhiều service cùng dùng một key | Thiết kế nonce cấp phát đa tiến trình và key separation, không dựa chỉ vào clock |
| App phải chạy trên provider không hỗ trợ ChaCha20 | Chọn thuật toán AEAD được policy/runtime hỗ trợ (ví dụ AES-GCM) thay vì tự triển khai ChaCha20 |

**Đừng tự chọn ChaCha20 chỉ vì “nhanh hơn AES”**: hiệu năng tùy CPU, provider, platform, dataset và khả năng tăng tốc phần cứng. Đo thực tế bằng benchmark phù hợp; ưu tiên security policy và tính tương thích trước.

## 16. Sai lầm thường gặp khi code review

| Nhầm lẫn | Vì sao nguy hiểm/sai | Cách sửa |
| --- | --- | --- |
| “`Cipher.getInstance("ChaCha20")` đã có authentication.” | Không có MAC/tag | Chọn `ChaCha20-Poly1305` |
| “`KeyGenerator` cũng dùng tên `ChaCha20-Poly1305`.” | KeyGenerator standard name là `ChaCha20` | Dùng đúng algorithm service |
| “`SecretKeySpec` sinh key mạnh.” | Nó chỉ bọc byte có sẵn | `KeyGenerator`/KMS, entropy đủ |
| “32 ký tự ASCII = key 256-bit mạnh.” | Entropy có thể thấp | Không dùng chuỗi/mật khẩu thô làm key |
| “`getEncoded()` luôn trả raw key.” | HSM/token key có thể opaque | Dùng handle/provider tương thích |
| “`getProvider()` trước `init` luôn phản ánh provider sẽ dùng.” | Delayed provider selection | Đọc sau `init` |
| “Pin SunJCE ở mọi môi trường là an toàn nhất.” | Giảm portability, có thể phá HSM/compliance | Không pin trừ khi cần |
| “Cipher AEAD dùng `ChaCha20ParameterSpec`.” | SunJCE yêu cầu `IvParameterSpec` | Tham số đúng theo transformation |
| “ChaCha20 raw dùng `IvParameterSpec`.” | Raw cần nonce + counter | `ChaCha20ParameterSpec` |
| “Nonce phải giấu như mật khẩu.” | Nonce không cần bí mật | Lưu cùng ciphertext, đảm bảo duy nhất |
| “Mỗi lần encrypt dùng cùng nonce nếu plaintext khác.” | Dẫn đến nonce reuse | Cấp nonce mới cho mỗi lần encrypt |
| “Thay mỗi counter trong cùng nonce là đủ.” | Có nguy cơ overlap keystream | Nonce duy nhất theo message |
| “Poly1305 tag là dữ liệu có thể bỏ.” | Bỏ integrity/authenticity | Lưu và verify tag |
| “Có AAD thì AAD được mã hóa.” | AAD chỉ authenticated, không encrypted | Không đặt bí mật vào AAD |
| “Gặp AEADBadTagException thì cứ lấy plaintext.” | Dữ liệu chưa xác thực | Từ chối và cleanup |
| “Raw ChaCha20 đổi bit sẽ tự báo BadPaddingException.” | Stream cipher không có tag | Dùng AEAD |
| “Cipher là thread-safe singleton.” | Có state thay đổi | Mỗi operation có Cipher riêng |
| “Kiểm round-trip là đủ đánh giá provider.” | Chưa phát hiện sai khác chuẩn | Test vectors + negative cases |
| “CipherInputStream luôn báo lỗi tag.” | Javadoc cảnh báo có thể nuốt integrity exceptions | Dùng Cipher trực tiếp/thiết kế streaming đã xác thực |
| “Một key dùng vô hạn message với random nonce chắc chắn không đụng.” | Collision probability tăng theo số lần dùng | Hạn mức/key rotation/nonce manager |
| “Provider có tên SunJCE là compliant mọi nơi.” | Compliance phụ thuộc module/mode/chứng nhận | Kiểm policy và provider certification thực tế |

## 17. Checklist triển khai an toàn

- [ ] Chọn **ChaCha20-Poly1305** nếu ứng dụng cần cả secrecy và integrity.
- [ ] Dùng tên transformation `"ChaCha20-Poly1305"` và `KeyGenerator("ChaCha20")` đúng chuẩn.
- [ ] Key 256-bit từ nguồn đáng tin hoặc KMS/HSM; không lấy trực tiếp từ mật khẩu/string.
- [ ] Mỗi lần encrypt dưới một key có nonce 12 byte **duy nhất**, kể cả khi chạy đa process.
- [ ] Với AEAD dùng `IvParameterSpec`, gọi `updateAAD` trước payload nếu có AAD.
- [ ] Với raw ChaCha20 dùng `ChaCha20ParameterSpec` và hiểu rõ nó **không có authentication tag**.
- [ ] Lưu nonce, key-ID, version, ciphertext + tag theo format nhất quán.
- [ ] Chỉ công bố plaintext khi `doFinal` decrypt AEAD đã verify tag thành công.
- [ ] Không log key/plaintext/tag raw hoặc vô hiệu hóa error handling khi tag sai.
- [ ] Không pin provider nếu không có lý do; đọc provider sau `init`.
- [ ] Nếu pin provider, test thực tế cùng dạng key (software/PKCS#11/HSM), key policy và compliance.
- [ ] Không gọi `getEncoded()` trên opaque key rồi coi `null` là lỗi mã hóa.
- [ ] Không chia sẻ một Cipher state giữa nhiều thread.
- [ ] Có giới hạn kích thước dữ liệu, thời gian và tài nguyên cho streaming/file.
- [ ] Kiểm test vectors chuẩn và các negative cases: wrong key, wrong AAD, tampered ciphertext/tag.
- [ ] Chạy regression test khi nâng JDK/provider và audit nonce/key lifecycle.
- [ ] Code target Java 11 chỉ dùng API có trong Java 11 và kiến thức vẫn còn áp dụng.

## 18. Tự kiểm tra kiến thức

**Câu 1.** `Cipher.getInstance("ChaCha20")` khác `Cipher.getInstance("ChaCha20-Poly1305")` thế nào?

**Đáp án:** Cái đầu là **stream cipher không tự xác thực dữ liệu**; cái sau là **AEAD** có tag giúp phát hiện sửa dữ liệu và hỗ trợ AAD.

**Câu 2.** Tạo khóa cho ChaCha20-Poly1305 bằng `KeyGenerator.getInstance("ChaCha20-Poly1305")` đúng không?

**Không.** Algorithm name chuẩn cho KeyGenerator trong SunJCE là **`"ChaCha20"`** và key 256-bit dùng được cho cả hai Cipher transformations.

**Câu 3.** Nonce ChaCha20 có kích thước bao nhiêu trong Java 11, và raw mode truyền counter bằng gì?

**12 byte**. Raw ChaCha20 dùng `new ChaCha20ParameterSpec(nonce, initialCounter)`, với counter 32-bit.

**Câu 4.** Với AEAD, có dùng `ChaCha20ParameterSpec` để init thay `IvParameterSpec` không?

**Không trong SunJCE.** ChaCha20-Poly1305 dùng `IvParameterSpec` 12-byte nonce; counter được quản lý nội bộ.

**Câu 5.** Vì sao không nên cố định `"SunJCE"` ở mọi chỗ?

**Vì** có runtime/provider khác, HSM opaque key, compliance, hardware acceleration và delayed selection. Để JCA chọn provider nếu không có yêu cầu bắt buộc.

**Câu 6.** Muốn biết provider đã xử lý Cipher thật, đọc khi nào?

**Sau `Cipher.init(...)`** bằng `cipher.getProvider().getName()`, đặc biệt khi có khóa opaque và delayed provider selection.

**Câu 7.** Encrypt A và decrypt A cùng key + nonce là nonce reuse bị cấm không?

**Không.** Decrypt phải dùng cùng key và nonce. Điều nguy hiểm là **encrypt hai message khác nhau** với cùng cặp key+nonce.

**Câu 8.** Nếu đổi một bit của tag AEAD, có nên parse plaintext phía nhận không?

**Không.** `AEADBadTagException` cho biết dữ liệu không được xác thực; phải từ chối toàn bộ message và không release plaintext.

**Câu 9.** SecretKeySpec có tạo key từ entropy tốt không?

**Không.** Nó chỉ tạo object từ raw bytes có sẵn. Chất lượng key phụ thuộc nguồn byte và cách quản lý key.

**Câu 10.** Có thể dùng `CipherInputStream` một cách mặc định để giải mã AEAD file lớn và chắc chắn nhận lỗi tag?

**Không.** Javadoc cảnh báo có thể không truyền tiếp integrity failure. Thiết kế giải mã nên sử dụng Cipher API trực tiếp và không publish plaintext cho đến khi kiểm tag hoàn tất.

## 19. Tài liệu tham khảo chính thức — Java 11 và JDK hiện đại

- [Oracle JDK 11 Release Notes — JEP 329: ChaCha20 and Poly1305](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): xác nhận `ChaCha20` và `ChaCha20-Poly1305` đã có từ JDK 11.
- [Java SE 11 — `Cipher`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html): `getInstance`, `init`, `updateAAD`, `doFinal`, key/nonce uniqueness và exceptions.
- [Java SE 11 — `KeyGenerator`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/KeyGenerator.html): tạo `SecretKey` và lựa chọn provider.
- [Java SE 11 — `SecretKey`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/SecretKey.html): interface key bí mật.
- [Java SE 11 — `SecretKeySpec`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html): bọc raw key material.
- [Java SE 11 — `ChaCha20ParameterSpec`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html): 12-byte nonce và 32-bit initial counter cho ChaCha20.
- [Java SE 11 — `IvParameterSpec`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html): nonce cho ChaCha20-Poly1305 của SunJCE.
- [Java SE 11 — `Provider`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/Provider.html) và [`Security`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/Security.html): liệt kê và chọn provider/service.
- [Oracle JDK 11 — Providers Documentation](https://docs.oracle.com/en/java/javase/11/security/oracle-providers.html): SunJCE hỗ trợ ChaCha20/ChaCha20-Poly1305, thông tin tên algorithm và tham số.
- [Oracle JDK 26 — Providers Documentation](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): xác minh các Cipher transformations vẫn được hỗ trợ; khuyến nghị **không pin provider** cho ứng dụng tổng quát.
- [Oracle Java 11 — CipherInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/CipherInputStream.html): cảnh báo khi dùng với authenticated decryption.
- [Java SE 11 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html): key generator và transformation names.
- [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439): thuật toán, định dạng nonce/tag, test vectors chính thức.

**Ghi nhớ:** `Cipher` là API thao tác mật mã; `SecretKey` chứa/đại diện khóa bí mật; `Provider` quyết định implementation. Trong Java 11+, dùng **`KeyGenerator("ChaCha20")`** cho key 256-bit; ưu tiên **`Cipher.getInstance("ChaCha20-Poly1305")`** để bảo vệ cả bí mật và toàn vẹn; dùng **`IvParameterSpec`** cho AEAD và **`ChaCha20ParameterSpec`** cho ChaCha20 thuần. **Không reuse nonce khi encrypt bằng cùng key**, và **không ép SunJCE** nếu không có lý do security/hardware/compliance đã được đánh giá.