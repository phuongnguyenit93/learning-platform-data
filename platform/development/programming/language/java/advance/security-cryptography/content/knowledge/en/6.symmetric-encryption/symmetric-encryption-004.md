# 6.4. Chu trình `Cipher.init`, `update`, `doFinal` và tính toán bộ đệm đầu ra

## Mục tiêu

Bài này giải thích vòng đời **`javax.crypto.Cipher`** trong Java Cryptography Architecture (JCA) khi mã hóa và giải mã đối xứng. Trọng tâm là cách dữ liệu đi qua **`init` → `update` → `doFinal`**, cách tính chỗ chứa output bằng **`getOutputSize`**, và cách dùng đúng các overload nhận mảng/`ByteBuffer` khi không biết mỗi lần `update` sẽ phát ra bao nhiêu byte.

Sau khi học, bạn có thể:

- Khởi tạo `Cipher` đúng chiều mã hóa/giải mã, khóa, IV/nonce và tham số thuật toán.
- Xử lý thông điệp trong **một phần hoặc nhiều phần** mà không bỏ sót output của `update` và `doFinal`.
- Phân biệt output của block cipher có padding với output của AEAD như AES-GCM, bao gồm authentication tag.
- Cấp phát buffer dựa trên **`getOutputSize(inputLen)`** và theo dõi **số byte thực tế đã ghi**.
- Xử lý `ShortBufferException`, `BadPaddingException`, `AEADBadTagException` và tránh reuse IV/nonce, nhận plaintext trước khi được xác thực.

Mã trong bài dùng **Java 17+**, `AES/GCM/NoPadding` làm ví dụ chính; `AES/CBC/PKCS5Padding` chỉ dùng để minh họa block padding và sizing. **AES-GCM được ưu tiên cho dữ liệu cần đồng thời bảo mật và xác thực**, với key/nonce được quản lý đúng cách.

## 1. Một `Cipher` đi qua những trạng thái nào?

`Cipher` là **engine có trạng thái**, không phải hàm biến đổi byte độc lập. Trước khi xử lý payload, phải chọn transformation và gọi `init`:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, nonce));
```

Đây là **snippet**, trong đó `key` là `SecretKey` AES và `nonce` là mảng 12 byte hợp lệ, đã tạo riêng cho thao tác. Cần import `javax.crypto.Cipher` và `javax.crypto.spec.GCMParameterSpec`, đồng thời xử lý checked exceptions.

`Cipher.getInstance("AES/GCM/NoPadding")` chọn **transformation đầy đủ** gồm thuật toán, mode, padding. Tránh chỉ ghi `"AES"` vì cách diễn giải mode/padding mặc định phụ thuộc provider và có thể không phù hợp về bảo mật.

Các bước chính:

```text
Cipher.getInstance(transformation)
       |
       v
chưa init: KHÔNG update/doFinal
       |
       v
init(ENCRYPT_MODE/DECRYPT_MODE, key, params)
       |
       +-- đối với AEAD: updateAAD(aad) trước dữ liệu payload
       |
       v
update(chunk 1) -> update(chunk 2) -> ... -> update(chunk n)
       |               có thể xuất 0 hoặc nhiều byte mỗi lần
       v
doFinal(last chunk hoặc không có thêm input)
       |
       +-- xử lý byte tồn đọng, padding hoặc tag
       +-- trả phần output CUỐI; với GCM decrypt, xác minh tag
       |
       v
hoàn tất: Cipher trở về trạng thái sau init nếu thành công
```

- `init(Cipher.ENCRYPT_MODE, ...)` khởi tạo để **mã hóa**; `init(Cipher.DECRYPT_MODE, ...)` khởi tạo để **giải mã**. Không gọi `update/doFinal` trước `init`; có thể nhận `IllegalStateException`.
- `init` còn có các mode `WRAP_MODE`/`UNWRAP_MODE` cho `wrap/unwrap` key, nhưng bài này tập trung `ENCRYPT_MODE`/`DECRYPT_MODE`.
- `update(...)` xử lý thêm một phần payload. **Số byte output một lần gọi không nhất thiết bằng số byte input**; provider có thể giữ block chưa đủ, chờ padding hoặc xác minh tag.
- `doFinal(...)` xử lý phần cuối và kết thúc phép biến đổi. Trong AES-GCM, mã hóa **gắn tag xác thực vào output**, giải mã **kiểm tra tag** và có thể ném `AEADBadTagException`.
- Sau `doFinal` thành công, theo API, `Cipher` được reset về **trạng thái đã init trước đó**. Tuy nhiên, với AES-GCM, **không được mã hóa thông điệp tiếp theo bằng cùng cặp key + nonce**: phải `init` cho mỗi encryption với nonce mới, ngay cả khi đối tượng có vẻ sẵn sàng tiếp tục.
- Nếu `doFinal` ném exception, không suy đoán state còn an toàn để sử dụng; xử lý lỗi và **khởi tạo lại** đối tượng cho một thông điệp mới.

Hình dung **một `init` và chuỗi các `update/doFinal` tương ứng với một message**. Không gọi `init` giữa các chunk của cùng message: làm vậy sẽ bỏ state của phần trước.

## 2. Vai trò của khóa, IV/nonce và AAD

`AES` dùng khóa đối xứng; để giải mã, bên nhận cần **cùng key**, mode, IV/nonce và các tham số liên quan. Với AES-GCM:

- **Key:** ví dụ AES-128 hoặc AES-256; phải lưu/truyền bằng cơ chế quản lý khóa phù hợp, **không đưa key vào log** và không nhúng key cố định trong source.
- **Nonce/IV:** thường dùng **12 byte (96 bit)** cho GCM. Mỗi lần mã hóa với **cùng key** phải có nonce **khác nhau**. Có thể tạo nonce từ `SecureRandom` cho minh họa/quy mô phù hợp; ở hệ thống sản lượng lớn cần thiết kế cấp phát nonce bảo đảm không trùng và chính sách xoay key.
- **Tag:** ví dụ `GCMParameterSpec(128, nonce)` đặt tag **128 bit = 16 byte**. Khi encryption kết thúc, `doFinal` trả thêm tag ở cuối ciphertext; khi decryption kết thúc, `doFinal` kiểm tra tag, và dữ liệu/khóa/nonce/AAD sai có thể dẫn đến xác thực thất bại.
- **AAD (Additional Authenticated Data):** dữ liệu **được xác thực nhưng không được mã hóa**, như version/header của protocol. Gọi `cipher.updateAAD(aad)` **trước** mọi `update/doFinal` xử lý payload, và bên giải mã phải cung cấp **chính xác cùng AAD**.
- **Ciphertext+tag:** đối với GCM, Java `Cipher` phát ra ciphertext cùng tag; nonce cần được truyền/lưu riêng (nonce không phải bí mật). Một định dạng đơn giản có thể là `version || nonce || ciphertext || tag` với quy tắc phân tích độ dài rõ ràng. Đừng lẫn lộn tag và nonce.

**Cảnh báo bắt buộc của GCM:** cùng key + nonce không được sử dụng cho hai lần mã hóa khác nhau. Việc `doFinal` “reset” state **không hợp thức hóa** việc reuse nonce. Khi đổi ciphertext/nonce/key/AAD hoặc tag, bên giải mã phải coi toàn bộ thông điệp **không hợp lệ** nếu kiểm tra tag thất bại.

## 3. Các overload của `update` và `doFinal`

| Phương thức | Input | Output | Điểm cần nhớ |
| --- | --- | --- | --- |
| `update(byte[] in)` | Cả mảng `in` | `byte[]`, **có thể `null`** nếu chưa phát ra block | Không được bỏ qua output khi nối nhiều chunk. |
| `update(byte[] in, int off, int len)` | Đoạn `[off, off+len)` | `byte[]`, có thể `null` | Tránh xử lý byte thừa của buffer tái dùng. |
| `update(in, off, len, out, outOff)` | Đoạn từ input | Ghi trực tiếp vào `out`; trả **số byte đã ghi** | Có thể trả 0; có thể ném `ShortBufferException`. |
| `update(ByteBuffer in, ByteBuffer out)` | Các byte còn lại của `in` | Ghi vào `out`, trả **số byte ghi** | Cập nhật position của cả hai buffer khi thành công. |
| `doFinal()` | Không thêm input; final dữ liệu đã `update` | `byte[]` | Bắt buộc để xử lý phần cuối, padding/tag. |
| `doFinal(byte[] in)` | Input cuối + dữ liệu đã buffer | `byte[]` | Có thể dùng **một lần** nếu không cần chia chunk. |
| `doFinal(in, inOff, inLen)` | Đoạn cuối | `byte[]` | Xử lý cả state từ những `update` trước. |
| `doFinal(out, outOff)` | Không thêm input | Ghi phần cuối vào `out`; trả số byte | Dùng sau các `update` đã ghi vào cùng output. |
| `doFinal(in, inOff, inLen, out, outOff)` | Input cuối | Ghi output cuối vào `out`; trả số byte | Phải còn đủ chỗ, tính đến byte đã buffer. |
| `doFinal(ByteBuffer in, ByteBuffer out)` | `in.remaining()` | Ghi trực tiếp vào `out` | Chú ý position/limit và space của output. |

**Khác `MessageDigest`:** `Cipher.update` có thể **phát output** ngay. Không thể chỉ gọi `update` rồi lấy output của `doFinal` cuối cùng nếu muốn toàn bộ ciphertext/plaintext. Khi dùng API trả `byte[]`, hãy **gom cả những mảng không null** theo đúng thứ tự. Khi dùng API ghi vào buffer có sẵn, hãy **cộng số byte đã ghi** sau mỗi lần.

Ví dụ sơ đồ xử lý ba chunk với output:

```text
in = [chunk1] [chunk2] [chunk3]
        |        |        |
     update   update    doFinal
        |        |        |
      out1     out2    out3 (gồm block cuối, padding/tag)
        \        |       /
         result = out1 || out2 || out3
```

Không giả định `out1.length == chunk1.length` hoặc `out2.length == chunk2.length`. Với block cipher có padding, `update` có thể trả `null`/0 vì chưa đủ dữ liệu; với GCM decrypt, một provider có thể giữ plaintext đến khi tag được xác minh. Ứng dụng **không được công bố/tiêu thụ plaintext chưa xác thực** trước khi `doFinal` thành công.

## 4. `Cipher.getOutputSize(inputLen)` là gì?

Phương thức:

```java
int capacity = cipher.getOutputSize(inputLen);
```

trả về kích thước buffer **đủ chứa output của lượt `update` hoặc `doFinal` sắp tới** với `inputLen` byte đầu vào, **có tính đến dữ liệu đã buffer ở các `update` trước**, padding và authentication tag của AEAD. Đây là **cận trên cần thiết**, **không phải** số byte chắc chắn sẽ ghi: kết quả thực có thể ngắn hơn.

**Các quy tắc áp dụng:**

1. **Phải `init` trước khi gọi `getOutputSize`**; nếu Cipher ở state không hợp lệ có thể ném `IllegalStateException`.
2. Khi đã biết số byte của toàn bộ message, có thể tính **một lần sau `init`, trước các `update`**: `byte[] output = new byte[cipher.getOutputSize(totalInputLength)]`. Sau đó nạp các chunk và cộng số byte được ghi qua các overload có output buffer.
3. Nếu đang giữa một quy trình, gọi `getOutputSize(remainingInputLength)` tại **state hiện tại** để dự trù kết quả cho thao tác tiếp theo, bao gồm dữ liệu đã tích lũy; **không dùng các cận trên tính từ thời điểm khác như thể chúng là số byte đã xuất ra**.
4. Dùng **số byte trả về thực tế** từ từng `update`/`doFinal` để xác định phần hợp lệ trong output. **Không** gửi/lưu toàn bộ mảng đã cấp phát nếu mới điền một phần.
5. Với `ByteBuffer`, `remaining()` là chỗ chứa còn lại, không phải `capacity()` tổng; `output.position()` tăng theo số byte ghi.
6. Nếu buffer không đủ, API ghi output có thể ném **`ShortBufferException`**. Theo Javadoc, sau lỗi thiếu buffer có thể gọi lại thao tác đó với output lớn hơn; nhưng sau lỗi xử lý/padding/authentication khác, phải thiết kế tái khởi tạo state rõ ràng.
7. Đừng tự suy `update` sẽ tạo bao nhiêu byte từ riêng `inputLen`. Kể cả khi biết block size, buffering/padding/AEAD khiến **thời điểm output xuất hiện** phụ thuộc implementation.

Mẫu tổng quát khi **đã biết `allInput.length`** (snippet trong phương thức đã khởi tạo `cipher`):

```java
byte[] allInput = /* bytes của một thông điệp */;
int split = allInput.length / 2;
byte[] output = new byte[cipher.getOutputSize(allInput.length)];
int written = 0;

written += cipher.update(allInput, 0, split, output, written);
written += cipher.update(
        allInput, split, allInput.length - split, output, written);
written += cipher.doFinal(output, written);

byte[] actualResult = Arrays.copyOf(output, written);
```

Snippet dùng `java.util.Arrays` và có xử lý exceptions; không phải chương trình độc lập. Với GCM, phải gọi `updateAAD` trước payload nếu protocol có AAD. Chỉ `actualResult` gồm `written` byte là dữ liệu hợp lệ; output dư sau `written` không thuộc thông điệp.

### Kích thước đầu ra ví dụ

| Transformation | Input plaintext | Output encryption thực tế | Lý do |
| --- | ---: | ---: | --- |
| `AES/GCM/NoPadding`, tag 128 bit | 0 byte | 16 byte | Tag 16 byte, ngay cả khi payload rỗng. |
| `AES/GCM/NoPadding`, tag 128 bit | 3 byte | 19 byte | 3 byte ciphertext + 16 byte tag. |
| `AES/GCM/NoPadding`, tag 128 bit | 16 byte | 32 byte | 16 byte ciphertext + 16 byte tag. |
| `AES/CBC/PKCS5Padding` | 0 byte | 16 byte | Padding lấp một block. |
| `AES/CBC/PKCS5Padding` | 3 byte | 16 byte | Padding lấp block AES 16 byte. |
| `AES/CBC/PKCS5Padding` | 16 byte | 32 byte | Khi input đã tròn block vẫn phải thêm block padding. |
| `AES/CBC/NoPadding` | 3 byte | Lỗi khi final hóa | Input chưa đủ bội số block 16 byte. |

Bảng mô tả **kích thước output cuối cùng** với cấu hình đã ghi và dữ liệu hợp lệ, không phải giả định kết quả `getOutputSize` của mọi provider ở mọi state luôn bằng các con số này. Với AES-CBC + `PKCS5Padding`, nếu input có `P` byte và block AES = 16 byte, output encryption sau hoàn tất có độ dài `16 × (floor(P / 16) + 1)`. Với AES-GCM tag 128 bit, output encryption có độ dài `P + 16`; tên `NoPadding` **không có nghĩa** không có tag.

Với decryption, kích thước plaintext chỉ biết chắc **sau khi đã bỏ padding/kiểm tra tag thành công**. `getOutputSize` cung cấp kích thước buffer đủ chứa, có thể **lớn hơn** số byte plaintext thực sự.

## 5. Ví dụ đầy đủ: AES-GCM qua nhiều `update` với output buffer

Chương trình sau tạo khóa AES-128 ngẫu nhiên và nonce GCM 12 byte cho **một lần mã hóa**. Nó chia plaintext thành hai chunk, cộng số byte `update` ghi, hoàn tất bằng `doFinal`, rồi dùng cùng key/nonce/AAD để **giải mã và kiểm tra tag**. Cipher giải mã được khởi tạo **riêng**. Một lần giải mã với AAD khác được thử để chứng minh xác thực thất bại.

Lưu **`CipherFlowDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class CipherFlowDemo {
    private CipherFlowDemo() {}

    public static void main(String[] args) throws Exception {
        KeyGenerator keygen = KeyGenerator.getInstance("AES");
        keygen.init(128);
        SecretKey key = keygen.generateKey();

        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        GCMParameterSpec params = new GCMParameterSpec(128, iv);

        byte[] aad = "header:v1".getBytes(StandardCharsets.UTF_8);
        byte[] plain = "Xin chao Cipher!".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, params);
        encrypt.updateAAD(aad);

        byte[] output = new byte[encrypt.getOutputSize(plain.length)];
        int split = 5;
        int used = encrypt.update(plain, 0, split, output, 0);
        used += encrypt.update(plain, split, plain.length - split, output, used);
        used += encrypt.doFinal(output, used);
        byte[] sealed = Arrays.copyOf(output, used);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, params);
        decrypt.updateAAD(aad);

        byte[] recovered = new byte[decrypt.getOutputSize(sealed.length)];
        int received = decrypt.update(sealed, 0, split, recovered, 0);
        received += decrypt.update(sealed, split, sealed.length - split,
                recovered, received);
        received += decrypt.doFinal(recovered, received);

        Cipher wrongHeader = Cipher.getInstance("AES/GCM/NoPadding");
        wrongHeader.init(Cipher.DECRYPT_MODE, key, params);
        wrongHeader.updateAAD("header:v2".getBytes(StandardCharsets.UTF_8));
        boolean rejected;
        try {
            wrongHeader.doFinal(sealed);
            rejected = false;
        } catch (AEADBadTagException expected) {
            rejected = true;
        }

        System.out.println("plainBytes=" + plain.length);
        System.out.println("sealedBytes=" + sealed.length);
        System.out.println("encryptionBoundEnough=" + (output.length >= sealed.length));
        System.out.println("roundTrip=" +
                Arrays.equals(plain, Arrays.copyOf(recovered, received)));
        System.out.println("wrongAadRejected=" + rejected);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CipherFlowDemo.java
java CipherFlowDemo
```

**Stdout dự kiến (đã kiểm tra trên JDK 24, mã tương thích Java 17+):**

```text
plainBytes=16
sealedBytes=32
encryptionBoundEnough=true
roundTrip=true
wrongAadRejected=true
```

Dù khóa và nonce được tạo ngẫu nhiên nên **byte ciphertext mỗi lần khác nhau**, các dòng trên không in ciphertext, và vẫn ổn định với AES-GCM tag 128 bit.

**Phân tích chi tiết:**

1. `KeyGenerator` tạo khóa AES 128 bit; `SecureRandom` tạo nonce 12 byte. Demo **không xuất key/nonce**. Trong hệ thống thực tế phải bảo đảm nonce không trùng với cùng key và lưu/truyền nonce để giải mã.
2. `encrypt.init` thiết lập chiều mã hóa, khóa và `GCMParameterSpec(128, iv)`. `updateAAD` xuất hiện **trước** khi đưa byte plaintext.
3. `getOutputSize(plain.length)` cấp phát buffer đủ chỗ cho ciphertext cộng tag. `split=5` chia 16 byte thành phần đầu 5 và phần cuối 11; tổng output không đổi so với mã hóa một lần.
4. `used += encrypt.update(...)` lưu **số byte output**, không phải số byte input. `encrypt.doFinal(output, used)` ghi phần cuối và tag vào vị trí kế tiếp; `Arrays.copyOf(output, used)` loại phần buffer không sử dụng.
5. Phía nhận `decrypt.init` với **cùng key/nonce**, rồi `updateAAD` với **cùng bytes**. `decrypt.update` có thể trả 0 do buffering/authentication; không cố đoán output.
6. **Chỉ sau khi `decrypt.doFinal` thành công**, dữ liệu `recovered` mới được chấp nhận và so sánh với plaintext. Không đưa bytes từ `update` ra các hệ thống tin cậy trước khi xác minh tag.
7. `wrongHeader` giả lập AAD khác (v1 → v2). `doFinal` ném `AEADBadTagException` và demo in `wrongAadRejected=true`. Trong ứng dụng thật phải **từ chối toàn bộ thông điệp**, không xử lý plaintext chưa được xác thực.

Đây là mô phỏng trong **một tiến trình**. Nếu truyền dữ liệu qua mạng/file, sender phải gửi nonce (và thông tin phiên bản/định dạng, tag nằm trong `sealed`), receiver phải có key qua kênh bảo mật và xác định đúng AAD. **Không có bước nào được phép tái mã hóa thông điệp thứ hai bằng key + IV vừa dùng**.

## 6. Ví dụ thứ hai: CBC có padding và `ByteBuffer`

AES-CBC trong ví dụ này chỉ minh họa vì sao **3 byte input có thể tạo 16 byte output sau `doFinal`**, và cách buffer đầu ra được dùng với API `ByteBuffer`. **CBC không tự xác thực ciphertext**; đừng chọn CBC không có MAC cho dữ liệu cần chống sửa đổi. Với ứng dụng mới, ưu tiên AES-GCM có kiểm soát nonce.

Lưu **`CipherBufferSizeDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public final class CipherBufferSizeDemo {
    private CipherBufferSizeDemo() {}

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] iv = new byte[16];
        new SecureRandom().nextBytes(iv);
        IvParameterSpec params = new IvParameterSpec(iv);
        byte[] plain = "abc".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/CBC/PKCS5Padding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, params);
        int estimate = encrypt.getOutputSize(plain.length);
        byte[] ciphertext = new byte[estimate];
        int first = encrypt.update(plain, 0, 2, ciphertext, 0);
        int finalBytes = encrypt.doFinal(plain, 2, 1, ciphertext, first);
        int produced = first + finalBytes;

        Cipher decrypt = Cipher.getInstance("AES/CBC/PKCS5Padding");
        decrypt.init(Cipher.DECRYPT_MODE, key, params);
        ByteBuffer input = ByteBuffer.wrap(ciphertext, 0, produced);
        ByteBuffer output = ByteBuffer.allocate(decrypt.getOutputSize(input.remaining()));
        int restoredCount = decrypt.doFinal(input, output);
        output.flip();
        byte[] restored = new byte[output.remaining()];
        output.get(restored);

        System.out.println("plainBytes=" + plain.length);
        System.out.println("cipherBytes=" + produced);
        System.out.println("estimateEnough=" + (estimate >= produced));
        System.out.println("decodedBytes=" + restoredCount);
        System.out.println("inputConsumed=" + !input.hasRemaining());
        System.out.println("roundTrip=" + Arrays.equals(plain, restored));
    }
}
```

```bash
javac -encoding UTF-8 CipherBufferSizeDemo.java
java CipherBufferSizeDemo
```

Stdout chính xác khi transform được cung cấp:

```text
plainBytes=3
cipherBytes=16
estimateEnough=true
decodedBytes=3
inputConsumed=true
roundTrip=true
```

Giải thích:

- Input `"abc"` chứa 3 byte UTF-8. AES block size = **16 byte**; `PKCS5Padding` của JCA cung cấp padding kiểu block tương thích AES, vì vậy ciphertext cuối là 16 byte. `getOutputSize(3)` cấp phát đủ chỗ.
- `update(plain,0,2,ciphertext,0)` nạp hai byte đầu. Vì chưa đủ một block, provider có thể giữ chúng và trả **0 byte**. `doFinal(plain,2,1,ciphertext,first)` nạp byte cuối, thêm padding rồi final hóa. **Luôn cộng `first + finalBytes`**.
- Khi giải mã, `ByteBuffer.wrap(ciphertext,0,produced)` đặt giới hạn đúng ciphertext thực tế; không giả định cả buffer luôn đầy. `ByteBuffer.allocate(decrypt.getOutputSize(input.remaining()))` tạo output đủ chỗ; `decrypt.doFinal(input,output)` xử lý các byte đang remaining.
- `ByteBuffer` đầu vào tiến đến limit, output.position tăng theo số byte ghi. Gọi `output.flip()` để chuyển output sang **chế độ đọc**, rồi lấy chính phần remaining hợp lệ. `restoredCount=3` chứ không phải kích thước đã cấp phát.
- Nếu chỉ có `AES/CBC/NoPadding` thì plaintext 3 byte không đủ block và `doFinal` encryption có thể ném `IllegalBlockSizeException`. Chuyển sang mode khác không được hiểu là tự động cung cấp xác thực.

Đối với `Cipher.update(ByteBuffer input, ByteBuffer output)` và `doFinal(ByteBuffer input, ByteBuffer output)`, hai tham số **không được là cùng một `ByteBuffer` object**; output buffer cũng phải writable và có đủ `remaining()`. Với output buffer quá nhỏ có thể ném `ShortBufferException`; API thay đổi `position` dựa trên số byte đã xử lý khi thành công.

## 7. Bộ đệm kết quả: cách tư duy đúng trong production

### Biết toàn bộ input trước khi bắt đầu

Với một thông điệp vừa/bé nằm trong mảng, chiến lược đơn giản là **tính cận trên một lần**, dùng overload có output buffer, và chỉ giữ `written` byte kết quả. Mọi `update`/`doFinal` nối output liên tiếp trong mảng. Chương trình `CipherFlowDemo` ở mục 5 chính là ví dụ đầy đủ.

### Input đến theo nhiều lần, chưa biết tổng độ dài

Nếu xử lý file/stream lớn hoặc nguồn dữ liệu liên tục, **không nên** cấp phát mảng chứa toàn bộ ciphertext/plaintext chỉ vì có `getOutputSize`. Có thể cấp output buffer phù hợp cho từng bước dựa trên state và số input còn lại, ghi những byte đã hoàn thành ra sink, và phải lưu/ghi **cả byte từ `doFinal`**. Cần chú ý thêm:

- Với **GCM encryption**, gửi ciphertext theo chunk có thể phù hợp, nhưng vẫn phải ghi đầy đủ **tag ở cuối** và truyền nonce/AAD theo protocol. Mỗi message dùng nonce riêng.
- Với **GCM decryption**, plaintext phát ra từ `update` (nếu có) **chưa được xác thực** trước `doFinal`. Thiết kế receiver phải **giữ cách ly** plaintext đến lúc tag thành công; không thực thi, hiển thị hoặc ghi đè dữ liệu tin cậy dựa trên plaintext chưa được xác thực. Với message rất lớn, có thể cần spool tạm vào vùng cách ly hoặc định dạng có khung AEAD riêng từng bản tin; không coi streaming giải mã là đã xác thực từng chunk.
- Với CBC có padding, output cuối có thể chứa dữ liệu được trả sau khi bỏ padding. Cần kiểm tra lỗi `BadPaddingException`; CBC vẫn cần phương án xác thực riêng nếu dùng trong protocol nhạy cảm.
- Dùng `CipherInputStream`/`CipherOutputStream` cần đọc kỹ contract về exception và cách final ở `close`. Đặc biệt, không dùng wrapper che khuất lỗi xác thực để mặc nhiên tin tưởng plaintext từ AEAD; khi mục tiêu là xác minh tag, ưu tiên luồng kiểm soát rõ ràng quanh `Cipher.doFinal`.

### Khi nào có `ShortBufferException`?

Ví dụ với API `doFinal(input, inOff, len, output, outOff)`, nếu `output.length - outOff` không đủ cho byte kết quả, có thể bị `ShortBufferException`. Kiểm tra offset/length và hỏi lại `getOutputSize(remainingInputLen)` từ state hiện tại trước khi cấp buffer. `getOutputSize` luôn tính cả dữ liệu trước đó còn buffer; không chỉ tính theo chunk vừa đưa vào. Khi thao tác lỗi do authentication hoặc padding, **không xử lý output từng phần như dữ liệu thành công**.

### Một số lỗi state thường gặp

| Tình huống | Kết quả | Giải pháp |
| --- | --- | --- |
| `update` trước `init` | `IllegalStateException` hoặc thao tác sai state. | `getInstance`, rồi `init` chính xác. |
| `update` nhiều lần nhưng bỏ output của chúng | Ciphertext/plaintext thiếu phần đầu. | Thu cả `update` và `doFinal`, theo đúng thứ tự. |
| Giả định `update` trả đúng số byte input | Sai với buffering, padding, AEAD. | Dùng số byte trả về và `getOutputSize` để cấp phát. |
| Cấp output bằng `new byte[input.length]` | Không đủ cho padding/tag hoặc buffered bytes. | Dùng `getOutputSize`. |
| In toàn bộ mảng cấp phát dù chỉ ghi một phần | Ghi thêm zero/dữ liệu dư, phá protocol. | Chỉ dùng `[0,written)` hoặc vị trí byte thực tế. |
| Không gọi `doFinal` | Thiếu bytes cuối, thiếu GCM tag hoặc chưa xác minh tag. | Final hóa đúng một lần cho mỗi thông điệp. |
| Reuse GCM key + nonce sau `doFinal` | Phá vỡ an toàn của AEAD. | Tạo nonce **duy nhất cho mỗi lần encryption** với cùng key. |
| `updateAAD` sau payload | `IllegalStateException` hoặc sai quy trình. | Cung cấp toàn bộ AAD trước payload. |
| Tiêu thụ plaintext GCM trước tag verification | Có thể xử lý dữ liệu bị sửa/giả mạo. | Chỉ công bố plaintext sau `doFinal` thành công. |
| Dùng `Cipher.getInstance("AES")` | Mode/padding không được chỉ định rõ. | Dùng đầy đủ `AES/GCM/NoPadding`. |
| Tưởng `NoPadding` nghĩa là ciphertext không thêm byte | Quên GCM tag. | Tính cả tag trong cận trên. |
| Dùng `ByteBuffer.capacity()` thay `remaining()` | Đánh giá sai vùng có thể đọc/ghi. | Dựa trên position/limit/remaining. |
| Dùng chung một Cipher cho nhiều thread | State có thể bị trộn. | Instance riêng cho từng operation. |
| Bắt lỗi `BadPaddingException` rồi dùng plaintext dở | Dữ liệu không đáng tin, state không chắc. | Hủy output, báo lỗi và khởi tạo lại. |

## 8. API exception và trạng thái sau lỗi

Các lỗi đáng nhận diện:

- `NoSuchAlgorithmException` hoặc `NoSuchPaddingException`: transformation không được hỗ trợ theo provider đã chọn.
- `InvalidKeyException`: key không phù hợp với thuật toán hoặc provider.
- `InvalidAlgorithmParameterException`: tham số IV/nonce/mode không hợp lệ hoặc không được chấp nhận.
- `IllegalStateException`: sử dụng Cipher không đúng state (chưa init, sai mode, thứ tự AAD sai...).
- `ShortBufferException`: buffer output không đủ; với overload ghi ra buffer, API chỉ rõ trường hợp cần tăng kích thước.
- `IllegalBlockSizeException`: input không đáp ứng yêu cầu block size khi không padding, hoặc thuật toán không xử lý được input.
- `BadPaddingException`: padding không hợp lệ trong decryption của các mode có padding.
- `AEADBadTagException`: tag không khớp khi decryption trong AEAD; lớp này **kế thừa `BadPaddingException`**. Nếu cần xử lý riêng, catch `AEADBadTagException` **trước** `BadPaddingException`.

Không sử dụng lỗi tag như “một biến thể dữ liệu gần đúng”; mọi kết quả giải mã từ lần thất bại đều phải bị loại. Không giả định có thể tiếp tục gọi `update` trên đối tượng đã ném exception ở `doFinal` mà không init lại. Ghi log loại lỗi, tên transformation và ngữ cảnh không nhạy cảm; **không log key, plaintext bí mật hay thông tin tạo oracle về padding**.

## 9. Bài tập kiểm tra hiểu bài

1. **Thay split.** Trong `CipherFlowDemo` đổi `split` từ 5 thành 1, 8 và 16. Vì sao output length và `roundTrip=true` vẫn không đổi? Quan sát riêng số byte của từng `update` trên provider đang chạy và giải thích vì sao không nhất thiết bằng input chunk.
2. **Tính cận trên.** Mã hóa AES-GCM với tag 128 bit, plaintext 100 byte. Giải thích vì sao ciphertext+tag có 116 byte, nhưng code vẫn nên gọi `getOutputSize(100)` trước khi cấp buffer.
3. **Padding.** Với AES/CBC/PKCS5Padding, tính output encryption cho plaintext 0, 1, 15, 16, 17 và 32 byte. Giải thích vì sao 16 byte input cho 32 byte ciphertext.
4. **Đổi AAD.** Thay `header:v1` thành `header:v2` chỉ ở bên decrypt. Xác nhận `AEADBadTagException` và giải thích vì sao không được sử dụng bất kỳ plaintext nào từ lần decrypt đó.
5. **Đổi nonce.** Mã hóa một message, lưu nonce và sealed bytes. Với cùng key, thử giải mã bằng nonce khác; giải thích vai trò của nonce và tag. **Không tái mã hóa hai message bằng cùng key + nonce** khi làm bài.
6. **Kiểm tra output buffer.** Chủ động cấp mảng bé hơn `getOutputSize` để quan sát `ShortBufferException`; sau đó tạo Cipher mới/khởi tạo lại và cấp đủ buffer. Xác định vì sao cần lưu số byte trả về của mỗi `update`.
7. **ByteBuffer.** Thay `ByteBuffer.allocate` bằng buffer có limit hẹp để thấy `remaining` là giới hạn thực sự. Sau khi `doFinal` thành công, thực hành `flip` và so output với plaintext.
8. **Thiết kế message lớn.** Với GCM decrypt file vài GB, đề xuất nơi tạm chứa plaintext cho đến khi tag được xác minh trước khi publish. Giải thích tại sao lưu ngay plaintext vào file đích tin cậy trong lúc `update` là nguy hiểm.
9. **Sai quy trình.** Trình bày hậu quả khi bỏ `doFinal`, gọi `init` giữa các chunk, dùng Cipher chung cho hai request, hoặc gửi thiếu tag.

**Tiêu chí hoàn thành:** bạn mô tả đúng `init` chọn mode/key/params, `update` có output tùy state, `doFinal` final padding/tag và reset sau thành công; biết dùng `getOutputSize` và số byte thực viết; đồng thời giữ đúng nonce, AAD và ranh giới xác thực khi dùng AES-GCM.

## Tham khảo chính thức (Java 17)

- [`Cipher` API — `init`, `update`, `doFinal`, `getOutputSize`, `updateAAD`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html)
- [`GCMParameterSpec` — nonce và độ dài authentication tag](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)
- [`AEADBadTagException` — lỗi xác thực tag AEAD](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html)
- [`ByteBuffer` — `position`, `limit`, `remaining`, `flip`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
