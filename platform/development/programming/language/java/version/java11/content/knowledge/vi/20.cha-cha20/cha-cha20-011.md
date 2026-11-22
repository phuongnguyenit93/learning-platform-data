# Kiểm thử mã hóa–giải mã ChaCha20: đúng khóa, sai khóa, sai nonce (Java 11+)

## 1. Mục tiêu của bài học

Trong **Java 11**, Java Cryptography Architecture (JCA/JCE) cung cấp `Cipher.getInstance("ChaCha20")` và `Cipher.getInstance("ChaCha20-Poly1305")`. Hai thuật toán có quan hệ nhưng khác hẳn **cách kiểm tra tính đúng đắn và xử lý dữ liệu bị sửa**:

- **ChaCha20 thuần** là *stream cipher*: mã hóa và giải mã bằng cùng một keystream được tạo từ **khóa bí mật 256 bit**, **nonce 96 bit** và **initial block counter 32 bit**. Nó bảo vệ tính bí mật nếu dùng đúng, nhưng **không kèm cơ chế xác thực toàn vẹn**. Sai khóa, nonce hoặc counter thường cho ra dữ liệu sai mà `Cipher.doFinal(...)` vẫn thành công.
- **ChaCha20-Poly1305** là *AEAD* (Authenticated Encryption with Associated Data): mã hóa dữ liệu đồng thời tạo **authentication tag 16 byte**, có thể xác thực cả **AAD**. Khi giải mã sai khóa, sai nonce, sai AAD hoặc ciphertext/tag bị sửa, cơ chế xác thực từ chối kết quả, trong JDK được biểu hiện điển hình bằng **`AEADBadTagException`**.

Bài học này giải quyết trọn vẹn các câu hỏi:

1. Tạo một bài kiểm tra **encrypt → decrypt → so sánh plaintext** như thế nào?
2. Với ChaCha20 thuần, điều gì thực sự xảy ra khi thử **sai khóa** và **sai nonce**?
3. Vì sao kiểm thử âm tính không được chỉ `assert` rằng giải mã “không ném exception”?
4. Vì sao **AEAD** báo lỗi xác thực khi sai khóa/nonce/AAD, thay vì trả plaintext rác?
5. Thiết kế test, chọn dữ liệu, quản lý khóa/nonce và đọc kết quả ra sao để **không tạo thói quen mật mã không an toàn**?

`ChaCha20`, `ChaCha20-Poly1305`, `ChaCha20ParameterSpec` và `IvParameterSpec` đều là API còn được duy trì trong JDK hiện đại. Nội dung áp dụng **Java 11 trở lên**, không dựa vào RC4, phương thức đã legacy hoặc kỹ thuật tắt xác thực.

## 2. Cơ chế căn bản để hiểu kết quả test

### 2.1. ChaCha20: keystream và phép XOR

ChaCha20 thuần tạo dòng byte khóa từ:

```text
           key[32 byte]   nonce[12 byte]   counter[32 bit]
                 \              |               /
                  \             |              /
                   ChaCha20 block function
                            |
                   keystream, mỗi block 64 byte
                            |
        plaintext XOR keystream = ciphertext
        ciphertext XOR keystream = plaintext
```

Với cùng `key`, `nonce` và `initialCounter`, hai phía tạo cùng keystream. Giải mã vì vậy trả về plaintext ban đầu. Nếu **một trong ba tham số khác**, keystream không còn tương ứng với ciphertext và byte giải mã sẽ sai.

Đây là phép biến đổi trên **byte**, không phải trên ký tự Unicode: dùng `StandardCharsets.UTF_8` khi chuyển text Java thành byte[]. `String.length()` đếm số đơn vị UTF-16, không phải số byte ciphertext.

**Giới hạn quan trọng:** ChaCha20 thuần không có tag để kiểm tra kết quả. Kẻ tấn công sửa một bit ciphertext có thể làm đổi bit tương ứng trong plaintext, mà phép giải mã không thông báo “tampered”. Vì vậy test với sai khóa/nonce thường xác nhận **kết quả khác plaintext gốc**, chứ không mong chờ `AEADBadTagException`.

### 2.2. ChaCha20-Poly1305: mã hóa kèm xác thực

AEAD sử dụng ChaCha20 để mã hóa payload và Poly1305 để tính một authentication tag. Sơ đồ khái niệm:

```text
      key + nonce[12] + plaintext + AAD
                       |
              ChaCha20-Poly1305
                       |
             ciphertext || tag[16]
                       |
   DECRYPT với đúng key, nonce, AAD và tag
                       |
            tag hợp lệ? ---- Không ----> AEADBadTagException
                  |
                 Có
                  |
           plaintext được xác thực
```

**AAD** (*Additional Authenticated Data*) là dữ liệu được **xác thực nhưng không mã hóa**, chẳng hạn version, message type hoặc key identifier. Hai phía phải cung cấp **chính xác cùng dãy byte AAD** trước khi gọi `doFinal(...)`.

Với ChaCha20-Poly1305, nếu khóa/nonce khác hoặc bất kỳ bit nào của ciphertext/tag/AAD bị sửa, tag tính lại gần như chắc chắn không khớp. API phản ánh lỗi xác thực bằng `AEADBadTagException`; phải từ chối dữ liệu chứ không tự “thử đọc plaintext còn lại”.

**Phân biệt kỳ vọng:** test ChaCha20 thuần sai key/nonce **không yêu cầu exception**, còn test ChaCha20-Poly1305 sai key/nonce **phải từ chối xác thực**. Không đánh đồng hai chế độ khi thiết kế assertions.

## 3. Các API Java 11 liên quan

| Thành phần | Cách dùng | Ý nghĩa khi test |
| --- | --- | --- |
| `Cipher.getInstance("ChaCha20")` | Tạo cipher mã hóa dòng | Không có authentication tag |
| `ChaCha20ParameterSpec(nonce, counter)` | Nonce **12 byte** và block counter **int** | Phải trùng nhau khi giải mã ciphertext thuần |
| `Cipher.getInstance("ChaCha20-Poly1305")` | Tạo cipher AEAD | Có xác thực dữ liệu và tag Poly1305 |
| `IvParameterSpec(nonce)` | Truyền nonce 12 byte cho ChaCha20-Poly1305 | **Không** dùng `ChaCha20ParameterSpec` cho AEAD |
| `SecretKeySpec(keyBytes, "ChaCha20")` | Bọc khóa bí mật 32 byte | Test có thể tạo key bằng `SecureRandom` |
| `Cipher.init(ENCRYPT_MODE, key, params)` | Chuẩn bị mã hóa | Với mỗi lần mã hóa mới cần nonce duy nhất theo khóa |
| `Cipher.init(DECRYPT_MODE, key, params)` | Chuẩn bị giải mã | Dùng **đúng nonce đã mã hóa**, không sinh nonce mới |
| `Cipher.doFinal(byte[])` | Kết thúc mã hóa/giải mã | Trả byte[] hoặc ném lỗi theo thuật toán |
| `Cipher.updateAAD(aad)` | Gắn metadata được xác thực | AAD phải thống nhất trước khi xử lý body |
| `AEADBadTagException` | Lỗi authentication tag | Negative test AEAD phải bắt đúng lỗi, không chấp nhận plaintext |

**Lưu ý JDK/Provider:** `Cipher.getInstance(...)` chọn provider thích hợp. Ví dụ trong bài đã kiểm thử thành công trên Java với `javac --release 11`. Kết quả ciphertext ngẫu nhiên không được in; exception message của provider không nên được dùng làm tiêu chí duy nhất vì có thể khác theo JDK/provider.

### 3.1. Độ dài của khóa và nonce

Theo IETF ChaCha20 (RFC 8439):

- **Key:** 32 byte = 256 bit.
- **Nonce:** 12 byte = 96 bit.
- **Block counter:** word 32 bit; mỗi khối ChaCha20 sinh 64 byte keystream.
- **Tag AEAD:** 16 byte = 128 bit.

**Nonce không cần bí mật nhưng không được trùng với cùng key khi mã hóa một thông điệp mới.** `SecureRandom` giúp sinh nonce khó đoán; tuy nhiên **random không chứng minh tuyệt đối không trùng** sau rất nhiều message hoặc giữa nhiều instance. Production phải thiết kế uniqueness bằng sequence/counter được cấp phát đúng hoặc một chiến lược được đánh giá phù hợp lưu lượng và tuổi khóa.

**Sai key** và **sai nonce** là hai test độc lập: khi thử sai key phải **giữ nonce đúng**; khi thử sai nonce phải **giữ key đúng**. Nếu đổi cả hai, test không cô lập được nguyên nhân.

## 4. Ma trận kiểm thử cần có

| Trường hợp | ChaCha20 thuần | ChaCha20-Poly1305 |
| --- | --- | --- |
| Key + nonce đúng | Plaintext khôi phục hoàn toàn | Plaintext khôi phục, tag hợp lệ |
| **Sai key** nhưng nonce đúng | Giải mã ra byte sai, thường **không ném lỗi** | **`AEADBadTagException`** |
| **Sai nonce** nhưng key đúng | Giải mã ra byte sai, thường **không ném lỗi** | **`AEADBadTagException`** |
| **Sai block counter** | Keystream khác, giải mã ra byte sai | **Không đặt counter bằng app**; AEAD tự quản lý |
| **Ciphertext bị sửa** | Có thể giải mã ra plaintext bị sửa, **không phát hiện** | **`AEADBadTagException`** |
| **Tag bị sửa** | Không có tag | **`AEADBadTagException`** |
| **AAD bị sửa** | Không có authenticated AAD | **`AEADBadTagException`** |
| Nonce sai kích thước | `ChaCha20ParameterSpec` từ chối nonce khác 12 byte | `IvParameterSpec` không kiểm tra riêng mọi thuật toán; `Cipher.init` kiểm tra tính hợp lệ theo provider |
| Ciphertext dài bằng plaintext? | **Có**, vì đây là stream cipher không padding | Thường ciphertext kèm **16-byte tag** dài hơn plaintext 16 byte |

Trong test về **sai key/nonce**, không nên giả định mọi provider đều ném cùng một exception cho ChaCha20 thuần. Lỗi bảo mật ở đây là **mất khả năng xác thực**, không phải bắt buộc có lỗi API.

**Thứ tự thử nghiệm hợp lý:** làm baseline round-trip trước, sau đó mỗi negative case chỉ đổi **một biến**. Nếu baseline fail, không diễn giải các negative case như bằng chứng cơ chế hoạt động đúng.

## 5. Thiết kế test fixture để đáng tin và an toàn

### 5.1. Mỗi test bắt đầu từ một ciphertext hợp lệ

Luồng kiểm thử:

```text
Tạo key 256-bit + nonce 96-bit + plaintext
                   |
                   v
      Cipher ENCRYPT_MODE -> ciphertext
                   |
          +--------+-----------------------+
          |                                |
          v                                v
     Positive path                 Negative paths
  correct key, nonce             wrong key / wrong nonce
          |                         / wrong AAD / tamper
          v                                |
    Decrypt + compare              Decrypt + check expected
          |                         failure/changed output
          v                                |
         PASS                             PASS
```

Sử dụng một **bản mã hợp lệ đã tạo đúng một lần** rồi thay các **tham số giải mã** khi thử negative cases. Đây là cách tránh vô tình thực hiện nhiều lần **mã hóa** với cùng cặp `(key,nonce)`. Việc giải mã lại một ciphertext cũ bằng các tham số khác chỉ là phép kiểm thử, **không tạo ciphertext mới** và không phải reuse nonce cho hoạt động mã hóa.

### 5.2. Khi thử sai key

Từ `key.getEncoded()`, copy sang mảng mới rồi thay một bit:

```java
byte[] changed = key.getEncoded();
changed[0] ^= 1;
SecretKeySpec incorrectKey = new SecretKeySpec(changed, "ChaCha20");
```

Khóa sai **vẫn dài 32 byte** và vẫn được provider chấp nhận. Test nhắm tới tình huống **sai nội dung khóa**, không phải key sai định dạng. Nếu dùng key 16 byte để test “sai khóa”, có thể nhận `InvalidKeyException` **trước khi giải mã**, làm bài test không chứng minh vấn đề ciphertext.

### 5.3. Khi thử sai nonce

Tạo một **bản sao của nonce đúng** rồi đổi một bit:

```java
byte[] changed = nonce.clone();
changed[0] ^= 1;
```

Nonce sai **vẫn đúng độ dài 12 byte** để provider chấp nhận tham số. Nhờ đó, negative test thực sự kiểm tra tác động của **giá trị nonce không khớp**, không bị che bởi `IllegalArgumentException` do sai length.

**Đừng thay nonce bằng một giá trị random rồi hi vọng không tình cờ trùng**: việc đảo một bit bảo đảm byte[] sai khác nguồn trong test.

### 5.4. Không in key, nonce hay ciphertext thật

Với key/nonce ngẫu nhiên, việc in hex ra console chỉ khiến test log chứa vật liệu nhạy cảm không cần thiết. Chỉ in các assertions: round-trip true/false, ciphertext length, loại exception và dấu hiệu integrity.

Không viết key production vào source hay config test. Dùng key mới do `SecureRandom` cấp cho chương trình thử nghiệm; không lưu/commit key, nonce và ciphertext của dữ liệu người dùng.

## 6. Chương trình Java 11 hoàn chỉnh

Ví dụ này **không cần Internet, database, JSON library hay JUnit**. Nó minh họa cả ChaCha20 thuần lẫn ChaCha20-Poly1305 để bạn nhìn thấy sự khác biệt của negative tests.

**Tạo tệp `ChaCha20RoundTripNegativeDemo.java`:**

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class ChaCha20RoundTripNegativeDemo {
    private static final SecureRandom RNG = new SecureRandom();

    static SecretKeySpec newKey() {
        byte[] k = new byte[32];
        RNG.nextBytes(k);
        return new SecretKeySpec(k, "ChaCha20");
    }

    static byte[] newNonce() {
        byte[] n = new byte[12];
        RNG.nextBytes(n);
        return n;
    }

    static SecretKeySpec wrongKey(SecretKeySpec key) {
        byte[] modified = key.getEncoded();
        modified[0] ^= 1;
        return new SecretKeySpec(modified, "ChaCha20");
    }

    static byte[] wrongNonce(byte[] nonce) {
        byte[] modified = nonce.clone();
        modified[0] ^= 1;
        return modified;
    }

    static byte[] raw(int mode, SecretKeySpec key, byte[] nonce,
                      int counter, byte[] input) throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20");
        cipher.init(mode, key, new ChaCha20ParameterSpec(nonce, counter));
        return cipher.doFinal(input);
    }

    static byte[] aead(int mode, SecretKeySpec key, byte[] nonce,
                       byte[] aad, byte[] input) throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(mode, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(input);
    }

    static void expectBadTag(String label, SecretKeySpec key,
                             byte[] nonce, byte[] aad, byte[] input)
            throws Exception {
        try {
            aead(Cipher.DECRYPT_MODE, key, nonce, aad, input);
            throw new AssertionError(label + " unexpectedly authenticated");
        } catch (AEADBadTagException expected) {
            System.out.println(label + ": AEADBadTagException");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] message = "Java 11 - kiểm thử ChaCha20!"
                .getBytes(StandardCharsets.UTF_8);
        SecretKeySpec rawKey = newKey();
        byte[] rawNonce = newNonce();
        int counter = 1;
        byte[] rawEncrypted = raw(Cipher.ENCRYPT_MODE, rawKey,
                rawNonce, counter, message);
        byte[] rawDecrypted = raw(Cipher.DECRYPT_MODE, rawKey,
                rawNonce, counter, rawEncrypted);

        System.out.println("raw round-trip: " +
                Arrays.equals(message, rawDecrypted));
        System.out.println("raw ciphertext same length: " +
                (rawEncrypted.length == message.length));
        System.out.println("raw wrong key restores plaintext: " +
                Arrays.equals(message, raw(Cipher.DECRYPT_MODE, wrongKey(rawKey),
                        rawNonce, counter, rawEncrypted)));
        System.out.println("raw wrong nonce restores plaintext: " +
                Arrays.equals(message, raw(Cipher.DECRYPT_MODE, rawKey,
                        wrongNonce(rawNonce), counter, rawEncrypted)));
        System.out.println("raw wrong counter restores plaintext: " +
                Arrays.equals(message, raw(Cipher.DECRYPT_MODE, rawKey,
                        rawNonce, counter + 1, rawEncrypted)));

        byte[] rawTampered = rawEncrypted.clone();
        rawTampered[0] ^= 1;
        byte[] rawTamperedPlain = raw(Cipher.DECRYPT_MODE,
                rawKey, rawNonce, counter, rawTampered);
        System.out.println("raw tamper decrypts without tag: " +
                (rawTamperedPlain.length == message.length));
        System.out.println("raw tamper changes plaintext: " +
                !Arrays.equals(message, rawTamperedPlain));

        SecretKeySpec aeadKey = newKey();
        byte[] aeadNonce = newNonce();
        byte[] aad = "version=1".getBytes(StandardCharsets.UTF_8);
        byte[] sealed = aead(Cipher.ENCRYPT_MODE,
                aeadKey, aeadNonce, aad, message);
        byte[] opened = aead(Cipher.DECRYPT_MODE,
                aeadKey, aeadNonce, aad, sealed);
        System.out.println("AEAD round-trip: " +
                Arrays.equals(message, opened));
        System.out.println("AEAD ciphertext adds 16-byte tag: " +
                (sealed.length == message.length + 16));

        expectBadTag("AEAD wrong key", wrongKey(aeadKey), aeadNonce,
                aad, sealed);
        expectBadTag("AEAD wrong nonce", aeadKey, wrongNonce(aeadNonce),
                aad, sealed);
        expectBadTag("AEAD wrong AAD", aeadKey, aeadNonce,
                "version=2".getBytes(StandardCharsets.UTF_8), sealed);

        byte[] tampered = sealed.clone();
        tampered[0] ^= 1;
        expectBadTag("AEAD ciphertext modified", aeadKey, aeadNonce,
                aad, tampered);

        byte[] tagModified = sealed.clone();
        tagModified[tagModified.length - 1] ^= 1;
        expectBadTag("AEAD tag modified", aeadKey, aeadNonce,
                aad, tagModified);

        try {
            new ChaCha20ParameterSpec(new byte[11], 1);
            throw new AssertionError("short nonce accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("raw invalid nonce: IllegalArgumentException");
        }
    }
}
```

**Chạy bằng JDK 11 trở lên:**

```bash
javac --release 11 -encoding UTF-8 ChaCha20RoundTripNegativeDemo.java
java ChaCha20RoundTripNegativeDemo
```

`--release 11` bảo đảm source biên dịch chỉ dùng ngôn ngữ và API Java 11. Nếu dùng đúng JDK 11, cũng có thể chạy `javac -encoding UTF-8 ...`. Tên file phải khớp public class.

**Đầu ra chính xác đã chạy thử:**

```text
raw round-trip: true
raw ciphertext same length: true
raw wrong key restores plaintext: false
raw wrong nonce restores plaintext: false
raw wrong counter restores plaintext: false
raw tamper decrypts without tag: true
raw tamper changes plaintext: true
AEAD round-trip: true
AEAD ciphertext adds 16-byte tag: true
AEAD wrong key: AEADBadTagException
AEAD wrong nonce: AEADBadTagException
AEAD wrong AAD: AEADBadTagException
AEAD ciphertext modified: AEADBadTagException
AEAD tag modified: AEADBadTagException
raw invalid nonce: IllegalArgumentException
```

Chương trình chạy thử thành công với **15 dòng kết quả**. Vì key và nonce được sinh ngẫu nhiên, ciphertext thực tế thay đổi giữa các lần chạy; những dòng in ở đây được thiết kế để kiểm tra **tính chất của thuật toán** thay vì tiết lộ material mật mã.

**Lưu ý về test deterministic:** hai key khác nhau hoặc hai nonce khác nhau tạo các keystream khác nhau với xác suất cực cao; phép so sánh `Arrays.equals(...)` trong một test với input ngẫu nhiên là kiểm thử hành vi thực tế, không phải một chứng minh toán học tuyệt đối chống collision. Một bộ test mật mã nghiêm túc cũng nên có **Known Answer Tests (KAT)** bằng vector chuẩn RFC để kiểm tra tính tương thích byte-for-byte.

## 7. Phân tích từng nhóm kết quả của chương trình

### 7.1. Baseline round-trip

```text
raw round-trip: true
raw ciphertext same length: true
AEAD round-trip: true
AEAD ciphertext adds 16-byte tag: true
```

- Cặp encrypt/decrypt ChaCha20 thuần dùng **cùng key, nonce, counter=1**. Kết quả phục hồi giống plaintext gốc.
- Stream cipher ChaCha20 không tự thêm padding: kích thước ciphertext bằng số byte plaintext.
- AEAD dùng **cùng key, nonce, AAD** ở hai phía; decryption xác minh tag, trả plaintext đúng.
- ChaCha20-Poly1305 theo RFC 8439 có authentication tag **16 byte**, do đó kết quả `doFinal(...)` trong ví dụ SunJCE dài hơn plaintext 16 byte.

Không kết luận “mã hóa an toàn” chỉ từ `round-trip: true`. Hai lần mã hóa sai cùng nonce vẫn có thể đều giải mã thành công; test round-trip chỉ chứng minh hai phía **đồng bộ tham số**.

### 7.2. Sai khóa khi giải mã ChaCha20 thuần

```text
raw wrong key restores plaintext: false
```

Test chỉ đổi **nội dung key 256-bit**: `wrongKey(rawKey)` lật một bit ở bản sao `key.getEncoded()`, giữ nguyên nonce và counter. Vì cipher mới nhận một key vẫn hợp lệ về độ dài, `Cipher.init` thành công và `doFinal` trả byte[].

Kết quả `false` cho biết byte[] giải mã **không giống plaintext**. Không có `AEADBadTagException`, vì ChaCha20 thuần **không có tag** để biết key sai.

**Sai lầm:** dùng `assertThrows(InvalidKeyException.class, ...)` cho một key 32 byte nhưng sai nội dung. `InvalidKeyException` thường dùng cho key **không hợp lệ về dạng/độ dài**, không phải một “password incorrect” detector cho stream cipher.

### 7.3. Sai nonce khi giải mã ChaCha20 thuần

```text
raw wrong nonce restores plaintext: false
```

`wrongNonce(rawNonce)` tạo mảng copy 12 byte rồi lật một bit. Key và counter giữ nguyên. Vì nonce vẫn đúng length, `ChaCha20ParameterSpec` chấp nhận; `Cipher` tạo keystream khác. Giải mã trả byte[] không khớp plaintext.

**Phân biệt hai loại test:**

- **Nonce sai giá trị nhưng dài 12 byte:** tham số hợp lệ, plaintext thường sai, **không có dấu hiệu integrity fail** trong ChaCha20 thuần.
- **Nonce sai độ dài, ví dụ 11 byte:** constructor `ChaCha20ParameterSpec` ném **`IllegalArgumentException`**. Đây là lỗi **validation đầu vào**, không chứng minh phát hiện dữ liệu bị sửa.

Không đánh dấu test sai nonce là PASS chỉ vì ném bất kỳ exception nào: cần biết test đang nhắm tới **sai nội dung nonce** hay **sai cấu trúc nonce**.

### 7.4. Sai counter

```text
raw wrong counter restores plaintext: false
```

ChaCha20 tạo keystream theo **block counter**. `counter=1` và `counter=2` bắt đầu ở các khối khác nhau. Nếu giải mã ciphertext từ counter=1 bằng counter=2, keystream không khớp.

Counter là số **khối 64 byte**, không phải số byte/nhân vật/vòng gọi `update`. Đừng khởi tạo lại `Cipher` với cùng key/nonce/counter cho nhiều chunk của một message: bạn sẽ bắt đầu keystream lại từ đầu.

**Giới hạn:** counter 32 bit có thể cạn không gian khối; không cho nó wrap về giá trị đã dùng với cùng key/nonce. Hãy giới hạn kích thước message, quản lý nonce cho từng record, và rekey theo chính sách.

### 7.5. Ciphertext ChaCha20 thuần bị sửa

```text
raw tamper decrypts without tag: true
raw tamper changes plaintext: true
```

Test copy ciphertext rồi sửa một bit đầu tiên. Lời gọi decrypt ChaCha20 thuần vẫn thành công, trả byte[] đúng **độ dài**, nhưng bytes đã sai. Dòng “without tag” **không nói ciphertext đúng**; nó nhắc rằng ChaCha20 thuần không có tag để xác thực.

Đây là lý do **không nên dùng ChaCha20 thuần làm giải pháp bảo vệ dữ liệu hoàn chỉnh trong ứng dụng mới**. Nếu chưa có MAC/authentication riêng được thiết kế đúng, hãy chọn AEAD.

### 7.6. Sai key hoặc nonce với ChaCha20-Poly1305

```text
AEAD wrong key: AEADBadTagException
AEAD wrong nonce: AEADBadTagException
```

Khác ChaCha20 thuần, khi giải mã AEAD, tag gắn với **key + nonce + AAD + ciphertext**. Nếu dùng sai key/nonce, xác thực tag thất bại và `Cipher.doFinal` ném `AEADBadTagException` theo hành vi JCE được kiểm thử.

**Không trả plaintext khi tag không hợp lệ.** Nếu ứng dụng có bước xử lý dữ liệu đã giải mã theo stream hoặc buffer, không sử dụng các byte chưa được xác thực từ `Cipher.update(...)` trước khi `doFinal(...)` xác minh thành công tag. Cách minh họa trong bài chỉ dùng `doFinal(byte[])`, và chỉ đọc plaintext sau khi lời gọi thành công.

### 7.7. Sai AAD hoặc ciphertext/tag

```text
AEAD wrong AAD: AEADBadTagException
AEAD ciphertext modified: AEADBadTagException
AEAD tag modified: AEADBadTagException
```

- **Wrong AAD:** key/nonce/ciphertext đúng nhưng `"version=1"` ở bên gửi trở thành `"version=2"` khi giải mã. Dù AAD không mã hóa, nó **được xác thực**, nên tag fail.
- **Ciphertext modified:** sửa một bit ở byte ciphertext nhưng giữ tag cũ. Tag không còn hợp lệ.
- **Tag modified:** chỉ sửa byte cuối cùng của tag. Lời gọi decrypt cũng bị từ chối.

**Không dựa vào nội dung message của exception** để phân loại “key sai”, “nonce sai” hay “ciphertext bị sửa”: cùng `AEADBadTagException` có thể xuất hiện cho tất cả. Hãy log loại lỗi an toàn và dùng telemetry/metadata nội bộ, không tiết lộ nguyên nhân cụ thể cho người gửi dữ liệu không tin cậy.

## 8. So sánh test pass/fail đúng với test pass/fail sai

### 8.1. Phải fail nếu negative test AEAD decrypt thành công

Helper trong chương trình:

```java
static void expectBadTag(String label, SecretKeySpec key,
                         byte[] nonce, byte[] aad, byte[] input)
        throws Exception {
    try {
        aead(Cipher.DECRYPT_MODE, key, nonce, aad, input);
        throw new AssertionError(label + " unexpectedly authenticated");
    } catch (AEADBadTagException expected) {
        System.out.println(label + ": AEADBadTagException");
    }
}
```

Đặc điểm tốt:

1. Chỉ bắt đúng `AEADBadTagException`.
2. Nếu decrypt **thành công ngoài ý muốn**, ném `AssertionError` làm test fail.
3. Nếu có **exception khác** (ví dụ sai loại tham số hoặc provider error), để nó nổi lên, **không đánh đồng với một lần xác thực tag thất bại**.
4. Không in plaintext, key, nonce hay authentication tag vào log.

**Anti-pattern:**

```java
// SAI: bắt mọi Exception rồi tuyên bố negative test đã PASS.
// try {
//     decryptWithWrongNonce(...);
//     System.out.println("PASS");
// } catch (Exception ignored) {
//     System.out.println("PASS");
// }
```

Cách trên cho PASS cả khi lỗi là `NullPointerException`, `NoSuchAlgorithmException`, cấu hình provider sai hoặc lỗi khác chưa kiểm thử. Mỗi negative case phải chỉ rõ **expected outcome**.

### 8.2. Với ChaCha20 thuần, không thể assert lỗi xác thực

```java
byte[] wrong = raw(Cipher.DECRYPT_MODE,
        wrongKey, nonce, counter, ciphertext);

if (Arrays.equals(plaintext, wrong)) {
    throw new AssertionError("Wrong key unexpectedly restored plaintext");
}
```

Cách kiểm thử này kiểm tra một **tính chất mong đợi** của keystream khác với dữ liệu đã mã hóa. Nhưng nó vẫn chỉ là một bài kiểm thử: việc không trả đúng plaintext **không phải xác thực cryptographic**. Ứng dụng cần kết quả “đúng hoặc bị từ chối” phải dùng cơ chế có authentication như ChaCha20-Poly1305.

### 8.3. Tránh khẳng định quá mức từ một lần chạy

Các câu sau **không** phải kết luận hợp lệ:

- “ChaCha20 thuần tự biết khi sai key.” **Sai:** không có tag.
- “Nếu không ném exception thì ciphertext đúng.” **Sai:** dữ liệu có thể sai hoàn toàn.
- “AEADBadTagException chắc chắn do nhập sai mật khẩu.” **Sai:** có thể sai key/nonce/AAD/tag/ciphertext.
- “Round-trip thành công chứng minh nonce chưa bao giờ bị trùng.” **Sai:** uniqueness là thuộc tính của bộ cấp phát nonce, không được kiểm chứng bằng một lần encrypt/decrypt.
- “Dùng cùng nonce khi decrypt là lỗi bảo mật.” **Sai:** decrypt cần đúng nonce của ciphertext. Điều bị cấm là **hai hoạt động mã hóa khác nhau** dùng lại nonce dưới cùng key.

## 9. Sự khác nhau giữa việc tái sử dụng nonce để giải mã và mã hóa

Đây là điểm đặc biệt dễ nhầm trong bài test.

### 9.1. Giải mã ciphertext cũ cần đúng nonce

```text
ENCRYPT:
  key=K, nonce=N, counter=1, plaintext=P
  -> ciphertext=C

DECRYPT cùng ciphertext:
  key=K, nonce=N, counter=1, ciphertext=C
  -> P
```

Dùng lại `N` tại **DECRYPT** là đúng; đó là tham số bắt buộc để khôi phục kết quả từ lần mã hóa tương ứng.

### 9.2. Mã hóa thêm message mới phải dùng nonce khác

```text
ENCRYPT message A:
  key=K, nonce=N1, plaintext=P1 -> C1

ENCRYPT message B (cùng key):
  key=K, nonce=N2, plaintext=P2 -> C2
  yêu cầu N2 khác N1
```

Nếu dùng lại `N1` với cùng key, ChaCha20 có thể tạo lại keystream, làm lộ quan hệ `C1 XOR C2 = P1 XOR P2` khi các khoảng block counter trùng nhau. Với ChaCha20-Poly1305, việc lặp nonce còn gây tổn hại nghiêm trọng cho **integrity/authentication**.

**Đừng sử dụng counter khác để thay nonce khác** mà không có thiết kế chia không gian keystream được chứng minh: các message dài có thể dùng các block counter chồng lấn. Ứng dụng mới nên sử dụng **nonce duy nhất cho mỗi encryption dưới một key**, và để AEAD quản lý counter nội bộ.

### 9.3. Random nonce và giới hạn va chạm

Trong demo, `SecureRandom` sinh nonce 12 byte cho **một message duy nhất**, nên phù hợp để mô tả round-trip. Với hệ thống có nhiều message:

- Đảm bảo **unique per key** qua một cơ chế có thể kiểm chứng. Ví dụ sequence number bền vững, partition theo node/sender, cấp phát atomically khi dùng chung khóa.
- Nếu dùng random nonce 96 bit, cân nhắc **birthday bound** và số lượng encryption trên mỗi key. Random khó đoán **không đồng nghĩa** uniqueness tuyệt đối.
- Đừng reset bộ đếm nonce về 0 sau crash/restart mà **vẫn dùng key cũ**.
- Với **retries**, xác định rõ replay nguyên ciphertext/tag có cho phép không và khi nào cần encrypt lại bằng nonce mới.
- Cần chính sách **rekey**, giới hạn message, quản lý lưu trữ khóa và cơ chế chống phát lại nếu giao thức yêu cầu.
- Không log key, không hardcode password thành khóa, không dùng nonce time-based đơn giản thiếu chống trùng.

## 10. Thế nào là bộ kiểm thử mật mã tốt?

### 10.1. Ba lớp kiểm thử nên có

| Lớp | Nội dung | Mục đích |
| --- | --- | --- |
| **Positive round-trip** | Encrypt rồi decrypt bằng tham số đúng; so sánh byte[] | Kiểm tra mã hóa/giải mã tương thích nhau |
| **Negative / tamper tests** | Sai key/nonce/counter, sai AAD, sửa ciphertext/tag, sai độ dài tham số | Kiểm tra hành vi từ chối hoặc khác plaintext theo đúng thuật toán |
| **Known Answer Test (KAT)** | Dùng key/nonce/plaintext **công khai cố định từ RFC 8439**, so byte ciphertext với vector chuẩn | Phát hiện implementation hoặc cách đóng gói byte sai mà round-trip đơn thuần có thể bỏ sót |

**Vì sao KAT có giá trị?** Nếu cả encrypt và decrypt đều dùng cùng một implementation **cùng sai** về byte order hoặc biến đổi input, round-trip vẫn có thể PASS. Một vector chuẩn độc lập giúp phát hiện lỗi đó. KAT phải dùng **vector public dành cho test**, không dùng khóa/nonce cố định đó bảo vệ dữ liệu thật.

### 10.2. Kiểm thử nhiều độ dài dữ liệu

Ngoài message ngắn trong demo, nên kiểm tra:

- **0 byte**: payload rỗng. ChaCha20 thuần tạo ciphertext rỗng; AEAD vẫn có authentication tag khi mã hóa thông điệp rỗng.
- **1 byte**: không giả định cần padding theo block 64 byte.
- **63, 64, 65 byte**: qua ranh giới một ChaCha20 block.
- **127, 128, 129 byte**: qua ranh giới hai block.
- **Text Unicode UTF-8** và **byte[] nhị phân**: so sánh **byte** đầu vào/đầu ra, không chỉ in `String`.
- **Message dài theo giới hạn của ứng dụng**: kiểm tra streaming, memory limit và tránh overflow counter. Không thử tự sinh message kích thước cực lớn không có giới hạn.

**Ý tưởng loop test bổ sung**, là đoạn minh họa không tự chạy độc lập:

```java
for (int size : new int[] {0, 1, 63, 64, 65, 127, 128, 129}) {
    byte[] plaintext = new byte[size];
    new SecureRandom().nextBytes(plaintext);

    // Tạo key/nonce mới cho lần ENCRYPT cụ thể.
    byte[] ciphertext = encryptWithFreshKeyAndNonce(plaintext);
    byte[] recovered = decryptUsingSavedParameters(ciphertext);
    if (!Arrays.equals(plaintext, recovered)) {
        throw new AssertionError("Mismatch at size=" + size);
    }
}
```

Đoạn trên là **pseudocode Java có các helper chưa được định nghĩa**: phải tự xây bộ helper trả kèm key ID/nonce/ciphertext theo một test fixture, thay vì copy trực tiếp vào class demo và kỳ vọng compile. Ví dụ hoàn chỉnh ở mục 6 không dùng helper giả.

### 10.3. Property tests không thay các kiểm thử an toàn của giao thức

Một vòng thử hàng nghìn message với nonce/key random có thể giúp tìm lỗi xử lý dữ liệu, nhưng **không chứng minh** security architecture đã ngăn reuse nonce giữa các node, bảo vệ key, chống replay hoặc xử lý tag invalid đúng cách. Những thuộc tính đó cần **test riêng của key/nonce allocator, state persistence, serialization và boundary ứng dụng**.

Test nên có:

- Một **positive baseline** chắc chắn.
- Negative cases **thay đúng một biến**.
- Assert đúng **kiểu lỗi** hoặc đúng **khác biệt dữ liệu**.
- Dữ liệu test được tạo trong môi trường cô lập.
- **Không log secrets** và **không bỏ qua exceptions**.
- Không dùng kết quả của một lần random round-trip như kiểm chứng toàn bộ security.

## 11. Chọn đúng phương thức kiểm tra trong code thực tế

### 11.1. So sánh plaintext trong unit test

Trong test chỉ cần so sánh hai byte array:

```java
if (!Arrays.equals(expectedPlaintext, actualPlaintext)) {
    throw new AssertionError("round-trip failed");
}
```

`Arrays.equals` là cách thông dụng cho **test kết quả dữ liệu**, không phải phương thức đặc biệt để so sánh secret theo thời gian hằng. Nếu viết code production để kiểm tra MAC/secret thủ công, cần tránh timing side channels và **không tự làm MAC verification** khi provider AEAD đã xử lý đúng.

### 11.2. Dùng `AEADBadTagException` như lỗi xác thực

Trong Java JCE, `AEADBadTagException` là một lớp con của `BadPaddingException` và biểu thị **authentication tag không khớp**. Khi gặp lỗi:

1. **Không sử dụng plaintext** hoặc nội dung stream được cấp trước đó cho tới khi xác thực thành công.
2. Không tự thử các key khác một cách không kiểm soát nếu hệ thống chứa nhiều key; chỉ chọn key theo metadata/rotation policy được xác thực phù hợp.
3. Không trả về plaintext “được một phần” để cứu dữ liệu.
4. Không để thông báo lỗi cụ thể từ provider làm rò rỉ chi tiết nội bộ không cần thiết.
5. Log sự kiện xác thực thất bại an toàn và áp chính sách rate-limit/abuse khi nhận dữ liệu không tin cậy.

**Ngoại lệ AEAD không phải giải pháp chống replay.** Một ciphertext/tag hợp lệ có thể bị gửi lại; muốn chống replay phải đưa sequence number/timestamp vào AAD hoặc payload đã xác thực và theo dõi trạng thái đã xử lý.

### 11.3. Không dùng `CipherInputStream` để che lỗi xác thực

Khi thiết kế đường giải mã có xác thực, phải bảo đảm exception kiểm tra tag **được truyền và xử lý**, và ứng dụng **chỉ dùng dữ liệu sau khi đã xác thực**. Tránh chọn wrapper I/O che mất `AEADBadTagException` hoặc cho phép xử lý dữ liệu unauthenticated. Trong bài test, dùng `Cipher.doFinal(byte[])` là cách dễ quan sát rõ ràng kết quả thành công hoặc lỗi xác thực.

### 11.4. Đừng dùng một `Cipher` chung giữa các thread

`Cipher` có state nội bộ (nonce, counter, buffer, chế độ encrypt/decrypt), không được giả định thread-safe. Trong demo, mỗi lời gọi `raw(...)` hoặc `aead(...)` tạo **Cipher mới**, giúp case độc lập, tránh lẫn trạng thái giữa các tests. Sau một lỗi `doFinal`, tạo một instance mới khi thử case kế tiếp thay vì cố dùng lại object có trạng thái không chắc chắn.

## 12. Những lỗi thường gặp khi kiểm thử ChaCha20

| Hiện tượng/hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test sai key ChaCha20 thuần **không ném lỗi** | Stream cipher không có authentication tag | Assert byte[] sai khác; muốn xác thực phải dùng AEAD |
| Test sai nonce ChaCha20 thuần **không ném lỗi** | Nonce sai tạo keystream sai nhưng tham số vẫn hợp lệ | So sánh plaintext, không kỳ vọng `AEADBadTagException` |
| Dùng key 16 byte cho negative wrong-key | Provider có thể từ chối key ngay tại `init` | Dùng **key 32 byte hợp lệ** nhưng đổi nội dung một bit |
| Dùng nonce 11 byte cho wrong-nonce test | Constructor từ chối format trước khi decrypt | Dùng nonce 12 byte khác nội dung; tách validation test riêng |
| Counter ở decrypt khác encrypt | Keystream bắt đầu tại block khác | Lưu/đọc đúng counter của ciphertext thuần |
| Dùng lại key/nonce cho 2 lần encrypt | Tái sử dụng keystream, làm suy yếu confidentiality/integrity | Mỗi lần encrypt mới phải có unique nonce per key |
| Dùng `ChaCha20ParameterSpec` cho ChaCha20-Poly1305 | AEAD dùng cơ chế counter nội bộ | Dùng `IvParameterSpec` với nonce 12 byte |
| Dùng `GCMParameterSpec` cho ChaCha20-Poly1305 | GCM là thuật toán AEAD khác | Không nhầm tham số giữa các thuật toán |
| Quên `updateAAD` ở decrypt | Tag không khớp nếu encrypt có AAD | Dùng cùng AAD bytes, trước dữ liệu |
| Sửa ciphertext/tag AEAD mà decrypt vẫn được coi PASS | Test bắt exception sai hoặc bỏ qua kết quả | Assert `AEADBadTagException`, fail nếu decrypt thành công |
| `AEADBadTagException` khi key/nonce đều đúng | AAD, ciphertext, tag, format có thể sai | Kiểm tra byte-by-byte metadata, key ID, nonce, tag, serialization |
| In ciphertext rồi so với chuỗi cố định giữa hai lần chạy | Key/nonce random → ciphertext thay đổi | Kiểm tra round-trip hoặc dùng RFC KAT cố định |
| Dùng `String.length()` làm ciphertext byte length | UTF-16 code unit khác UTF-8 byte | Dùng `getBytes(UTF_8).length` |
| Bắt `Exception` chung để PASS negative test | Có thể che lỗi cấu hình/provider | Assert cụ thể expected exception |
| Gộp nhiều biến sai vào cùng case | Không biết nguyên nhân thực sự | Chỉ đổi đúng key hoặc nonce hoặc AAD/tag |
| Tái sử dụng `Cipher` giữa nhiều threads/cases | Cipher mutable, mang trạng thái | Dùng instance độc lập mỗi case |
| Coi tag hợp lệ là chống replay | AEAD xác thực nội dung, không nhớ lịch sử | Xây replay-window/sequence và lưu state |
| Copy snippet với helper chưa tồn tại rồi báo không compile | Nhầm mã minh họa và chương trình hoàn chỉnh | Dùng class chạy đầy đủ ở mục 6; helper giả chỉ là hướng triển khai |

## 13. Thực hành tốt trong CI/CD và production

**Đối với CI:**

- Chạy `javac --release 11` để xác thực tương thích Java 11 (khi dùng JDK đủ mới hỗ trợ option).
- Chạy test trên các JDK/provider mà hệ thống thực sự hỗ trợ, vì implementation hoặc policy có thể khác nhau.
- Kiểm tra **15 dòng output**, đặc biệt 5 case AEAD expected `AEADBadTagException`; có thể viết assertions thay vì so text nếu đưa vào framework test.
- Thêm KAT chuẩn RFC 8439 để kiểm chứng byte output độc lập với cách implementation tự decrypt.
- Thêm cases ở ranh giới block 64 byte, body rỗng và Unicode.
- Không đưa secret production hoặc dữ liệu khách hàng vào fixtures.
- Không dùng flag JDK nội bộ để bỏ qua lỗi xác thực hay tái sử dụng nonce.

**Đối với production:**

- **Ưu tiên ChaCha20-Poly1305 hoặc AEAD được phê duyệt** khi cần confidentiality + integrity. ChaCha20 thuần chỉ dùng khi giao thức hiện hành có cơ chế xác thực độc lập đúng đắn.
- Quản lý key 256-bit bằng KeyStore/KMS hoặc hạ tầng quản lý khóa phù hợp; không dùng password/username thô làm key.
- Mỗi encryption dưới cùng key phải có **nonce duy nhất**, kể cả sau restart, failover hoặc trên nhiều node.
- Xác thực và thống nhất format: `version`, `keyId`, nonce 12 byte, ciphertext, tag, AAD.
- Phía giải mã **lấy nonce đã lưu trong message**, không sinh nonce mới.
- Chỉ sử dụng plaintext **sau khi `doFinal` xác thực tag thành công**.
- Không đặt tag/MAC bên ngoài đúng protocol hoặc tự ghép CRC/hash thường rồi coi là authentication.
- Giới hạn kích thước message, số bản ghi trên mỗi key, dữ liệu bị lỗi và số lần retry.
- Tách HTTP/TLS security với message-level encryption; HTTPS an toàn không thay thế xác thực ciphertext đã lưu trong storage nếu ứng dụng cần bảo vệ dữ liệu ở đó.
- Log tối thiểu, không làm lộ keys, plaintext, token hay nội dung lỗi nội bộ.
- Tổ chức test âm tính và security review cho trường hợp sai key, nonce, AAD, ciphertext, tag, replay và rotation.

## 14. Bài tập tự kiểm tra

**Câu 1.** Trong ChaCha20 thuần, decryption dùng một key 32 byte khác với key encrypt, nhưng nonce và counter đúng. Có nhất thiết ném exception không?  
**Đáp án:** Không. Key vẫn hợp lệ về format, cipher tạo keystream khác, thường trả plaintext sai; không có tag để xác thực.

**Câu 2.** Sai nonce nhưng length vẫn 12 byte thì sao?  
**Đáp án:** ChaCha20 thuần thường giải mã thành byte[] sai; ChaCha20-Poly1305 từ chối khi tag không khớp, thường `AEADBadTagException`.

**Câu 3.** Nonce chỉ có 11 byte nên constructor `ChaCha20ParameterSpec` ném gì?  
**Đáp án:** `IllegalArgumentException`. Đây là input validation, không phải kiểm thử khả năng phát hiện nonce sai nhưng vẫn đúng format.

**Câu 4.** Vì sao negative test AEAD cần fail khi decryption không ném lỗi?  
**Đáp án:** Mục tiêu là chứng minh dữ liệu sai bị từ chối. Nếu giải mã sai key/nonce mà trả plaintext thành công, test phải phát hiện rủi ro.

**Câu 5.** Có dùng đúng nonce khi decrypt một ciphertext đã được encrypt trước đó không?  
**Đáp án:** Phải dùng đúng nonce, key và AAD tương ứng. Quy tắc không reuse nonce là **giữa các lần encrypt khác nhau** cùng key.

**Câu 6.** Vì sao làm round-trip bằng cùng một implementation chưa đủ?  
**Đáp án:** Nếu encrypt và decrypt cùng một lỗi logic, round-trip vẫn có thể PASS. Dùng vector Known Answer Test công khai RFC 8439 để kiểm tra byte output độc lập.

**Câu 7.** AEAD metadata `"version=1"` được dùng làm AAD khi encrypt, nhưng decrypt dùng `"version=2"`. Kết quả?  
**Đáp án:** Tag xác thực không khớp, gây `AEADBadTagException` trong JCE.

**Câu 8.** Tag 16 byte bị sửa một bit, có nên bỏ tag rồi đọc phần ciphertext không?  
**Đáp án:** Không. Phải từ chối message và không sử dụng plaintext chưa được xác thực.

**Câu 9.** Vì sao không nên log key/nonce/ciphertext đầy đủ trong test?  
**Đáp án:** Tránh rò rỉ vật liệu bảo mật và thông tin nhạy cảm; test chỉ cần log kết quả assertions, không cần in secret.

**Câu 10.** Một ciphertext AEAD có tag hợp lệ được gửi lại nguyên xi. AEAD có tự từ chối không?  
**Đáp án:** Không có bảo đảm chống replay. Cần sequence/nonce tracking và state ở tầng giao thức.

## 15. Tổng kết và tài liệu chính thức

- **Kiểm thử baseline:** encrypt rồi decrypt với cùng `key`, `nonce`, `counter` (ChaCha20) hoặc cùng `key`, `nonce`, `AAD` (ChaCha20-Poly1305), sau đó so sánh **byte[]**.
- **ChaCha20 thuần sai key/nonce/counter:** thường tạo plaintext sai mà không có exception xác thực. Đây là **đặc tính của stream cipher không có authentication tag**.
- **ChaCha20-Poly1305 sai key/nonce/AAD hoặc ciphertext/tag bị sửa:** `Cipher.doFinal` từ chối vì xác thực thất bại, điển hình **`AEADBadTagException`**.
- **Mỗi negative test chỉ thay một biến** và chỉ assert đúng outcome của thuật toán; không bắt `Exception` chung để báo PASS.
- **Phân biệt nonce reuse khi decrypt đúng ciphertext với nonce reuse giữa hai encrypt:** chỉ trường hợp sau là vi phạm uniqueness.
- **Không bỏ qua integrity:** với ứng dụng mới, ưu tiên AEAD và bảo vệ key, nonce, AAD, tag, format cùng cơ chế chống replay khi cần.
- Ví dụ Java 11 đã được biên dịch và chạy đủ **15 dòng**, hoàn toàn offline.

**Tài liệu chính thức còn áp dụng:** [Oracle Java 11 — Cipher](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html); [Oracle Java 11 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html); [Oracle Java 11 — IvParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html); [Oracle Java 25 — Cipher](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/Cipher.html); [OpenJDK JEP 329 — ChaCha20 and Poly1305](https://openjdk.org/jeps/329); [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439.html).