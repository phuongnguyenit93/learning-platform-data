# ChaCha20 và mô hình stream cipher trong Java 11

## Mục tiêu bài học

**ChaCha20** là một thuật toán mã hóa đối xứng dạng **stream cipher** hiện đại: từ một khóa bí mật, nonce và bộ đếm block, thuật toán tạo ra một dãy byte giả ngẫu nhiên gọi là **keystream**; plaintext được XOR với keystream để tạo ciphertext. Thuật toán này được chuẩn hóa cho nhiều giao thức Internet trong **RFC 8439**, còn Java 11 giới thiệu triển khai chuẩn qua **JEP 329** và Java Cryptography Extension (**JCE**).

ChaCha20 vẫn là kiến thức hiện hành. Tuy nhiên, **`Cipher.getInstance("ChaCha20")` chỉ cung cấp mã hóa, không tự bảo vệ tính toàn vẹn hoặc tính xác thực**. Với hầu hết ứng dụng lưu trữ/truyền thông điệp độc lập, hãy ưu tiên **`ChaCha20-Poly1305`** (AEAD) hoặc một AEAD được hệ thống hỗ trợ như AES-GCM, không lấy stream cipher thuần làm giải pháp bảo mật mặc định.

Sau bài học, bạn có thể:

1. Giải thích **stream cipher**, `keystream` và phép XOR khi mã hóa/giải mã, phân biệt nó với block cipher như AES.
2. Mô tả bộ tham số ChaCha20 theo RFC 8439: **khóa 256 bit (32 byte), nonce 96 bit (12 byte), bộ đếm block 32 bit**, đầu ra **64 byte cho mỗi block keystream**.
3. Hiểu sơ lược cách ChaCha20 sử dụng các phép cộng modulo 2³², XOR và phép quay bit (**ARX**) trong 20 rounds; không nhầm «20» với số bit khóa.
4. Dùng `Cipher.getInstance("ChaCha20")`, `ChaCha20ParameterSpec`, `KeyGenerator`, `SecureRandom`, `Cipher.update` và `doFinal` trong **Java 11**.
5. Giải thích vì sao **không được lặp lại cặp (key, nonce)**, không được tùy tiện reset counter hoặc tái sử dụng một keystream cho các thông điệp khác.
6. Chứng minh ChaCha20 thuần **có tính malleable**: sửa một bit ciphertext có thể sửa một bit plaintext tương ứng mà không báo lỗi.
7. Sử dụng **`ChaCha20-Poly1305` với `IvParameterSpec`**, `updateAAD` và kiểm tra tag để chống sửa đổi ciphertext/AAD; nhận biết `AEADBadTagException`.
8. Biên dịch và chạy chương trình Java 11 so với **test vector RFC 8439**, kiểm thử tiếng Việt/Unicode, dữ liệu nhiều block, xử lý theo chunk, validation và AEAD.

Bài được xây dựng từ API của Java SE 11 và RFC 8439, đối chiếu với tài liệu JDK hiện hành. Không sử dụng RC4/ARCFOUR làm khuyến nghị hay một thuật toán legacy khác để thay thế ChaCha20.

## 1. Stream cipher là gì?

### 1.1. Từ khóa và nonce tới keystream

Trong stream cipher, luồng byte cần bảo vệ không được xử lý theo kiểu «mỗi khối plaintext = một khối ciphertext có padding cố định» như những chế độ block cipher truyền thống. Thay vào đó, thuật toán dùng **secret key**, nonce và trạng thái bộ đếm để tạo một luồng byte giả ngẫu nhiên. XOR luồng này với plaintext:

~~~text
              key (32 bytes) + nonce (12 bytes) + counter
                                   |
                                   v
                          ChaCha20 keystream
                              K[0], K[1], ...
                                   |
plaintext P[0], P[1], ... -------- XOR --------> ciphertext C[0], C[1], ...

C[i] = P[i] XOR K[i]
P[i] = C[i] XOR K[i]
~~~

Vì `a XOR b XOR b = a`, **giải mã chỉ cần phát lại cùng keystream và XOR với ciphertext**. Phía gửi và phía nhận phải có cùng:

- Khóa (key) chính xác.
- Nonce chính xác.
- Block counter ban đầu chính xác.
- Thứ tự bytes/cách phân đoạn liên tục chính xác.

Một kết quả ciphertext dài `N` byte thường vẫn **dài `N` byte** với ChaCha20 thuần; thuật toán không tự thêm padding hay authentication tag. Nếu ứng dụng cần bảo vệ dữ liệu, **không được suy ra «đúng số byte» là «dữ liệu không bị sửa đổi»**.

### 1.2. ChaCha20 khác gì AES?

| Tiêu chí | ChaCha20 stream cipher | AES block cipher |
| --- | --- | --- |
| Đơn vị nguyên thủy | Tạo keystream qua các block 64 byte; XOR với plaintext | Hoán vị một block 128 bit, phải chọn chế độ hoạt động để mã hóa dữ liệu dài |
| Khóa chuẩn được nói đến ở đây | 256 bit | 128, 192 hoặc 256 bit tùy cấu hình |
| Nonce/counter | Nonce 96 bit, counter 32 bit theo biến thể IETF | Phụ thuộc chế độ, ví dụ AES-GCM có nonce/IV và counter riêng |
| Padding | Không dùng padding cho bản stream cipher thuần | Tùy mode; AES-GCM không dùng PKCS#5 padding |
| Xác thực ở chế độ thô | **Không** | AES thuần cũng không bảo đảm; AES-GCM là AEAD |
| Giải pháp thường nên cân nhắc cho message thật | **ChaCha20-Poly1305 (AEAD)** | **AES-GCM (AEAD)** |

Không khẳng định ChaCha20 «luôn nhanh hơn AES»: kết quả phụ thuộc CPU, hỗ trợ tăng tốc phần cứng, provider JCE, kích thước dữ liệu và workload. Cả ChaCha20-Poly1305 và AES-GCM đều là lựa chọn hiện đại khi được cấu hình đúng. **RC4/ARCFOUR là stream cipher cũ không còn phù hợp để thiết kế hệ thống mới.**

### 1.3. Dữ liệu mã hóa là byte, không phải ký tự

`Cipher` hoạt động trên **`byte[]` / `ByteBuffer`**. Với văn bản Java `String`, cần mã hóa ký tự rõ ràng:

~~~java
String text = "Tiếng Việt";
byte[] plaintext = text.getBytes(StandardCharsets.UTF_8);

// ... Encrypt/decrypt plaintext as bytes ...

String decoded = new String(decrypted, StandardCharsets.UTF_8);
~~~

Đây là **đoạn minh họa**, chưa phải chương trình độc lập. `String.length()` đếm UTF-16 code units, không phải số byte UTF-8; tiếng Việt có dấu hoặc ký tự bổ sung như U+1F642 có thể dùng nhiều byte. ChaCha20 không diễn giải Unicode và cũng không «tự parse JSON». Hãy mã hóa/cấu trúc hóa dữ liệu trước khi đưa vào cipher.

## 2. Cấu trúc ChaCha20 theo RFC 8439

### 2.1. Đầu vào và trạng thái 16 words

Phiên bản IETF của ChaCha20 trong RFC 8439 có:

| Tham số | Kích thước | Vai trò |
| --- | --- | --- |
| **Key** | 256 bit / 32 byte | Bí mật chung giữa các phía được phép mã hóa/giải mã. |
| **Nonce** | 96 bit / 12 byte | Giá trị **không được lặp lại cho cùng một key** ở các lần mã hóa độc lập. |
| **Block counter** | 32 bit | Chỉ số block keystream đầu tiên; tăng khi sang block tiếp theo. |
| **Keystream block** | 512 bit / 64 byte | Đầu ra của một lần gọi ChaCha20 block function. |
| **Rounds** | 20 | Các phép biến đổi ARX, thường mô tả là 10 double-rounds. |

Trạng thái gồm **16 words 32 bit**, tổng cộng 512 bit:

~~~text
  word[ 0.. 3] : 4 constants ("expand 32-byte k")
  word[ 4..11] : 8 words từ key 256 bit
  word[12]     : counter 32 bit
  word[13..15] : 3 words từ nonce 96 bit

  +----------+----------+----------+----------+
  | constant | constant | constant | constant |
  +----------+----------+----------+----------+
  | key[0]   | key[1]   | key[2]   | key[3]   |
  +----------+----------+----------+----------+
  | key[4]   | key[5]   | key[6]   | key[7]   |
  +----------+----------+----------+----------+
  | counter  | nonce[0] | nonce[1] | nonce[2] |
  +----------+----------+----------+----------+
~~~

Các words được giải thích theo **little-endian**. ChaCha20 áp dụng **quarter-round** trên các vị trí xác định của ma trận, kết hợp cộng số nguyên modulo 2³², XOR và quay trái 32-bit. Sau 20 rounds, cộng trạng thái ban đầu theo modulo 2³² rồi serialize thành 64 byte.

Mã hóa một plaintext dài hơn 64 byte không đơn giản là lặp lại block cũ: block keystream tiếp theo dùng **counter tăng thêm 1**, với cùng key và nonce cho **cùng thông điệp**. Không tự viết lại hàm quarter-round cho sản phẩm khi JCE/provider đáng tin cậy đã có sẵn.

### 2.2. Chỉ số counter không phải nonce

Ví dụ với plaintext 150 byte, đầu vào counter ban đầu là 1:

~~~text
plaintext bytes 0..63    -> ChaCha20(key, nonce, counter=1), XOR 64 bytes
plaintext bytes 64..127  -> ChaCha20(key, nonce, counter=2), XOR 64 bytes
plaintext bytes 128..149 -> ChaCha20(key, nonce, counter=3), XOR 22 bytes
~~~

Trong **một** lời gọi `Cipher` được init đúng, JCE quản lý việc đi qua các block nội bộ. Bạn không nên tự reset counter thành 1 mỗi khi gọi `Cipher.update(...)` trên từng chunk: làm như vậy có nguy cơ tái sử dụng keystream cho các đoạn khác nhau.

**Counter và nonce giải quyết hai việc khác nhau:**

- **Counter:** phân biệt các block keystream **bên trong cùng một stream/message**.
- **Nonce:** phân biệt những lần mã hóa **độc lập** dưới cùng key.

Không được nói «tôi đổi counter là đã đủ để tái sử dụng nonce tùy ý»: nếu các khoảng counter trùng hoặc bị khởi tạo lại sau restart, keystream có thể chồng lấn. Chính sách phổ biến và dễ audit nhất là **cấp nonce mới độc nhất cho mỗi message dưới cùng key**, bắt đầu counter theo định nghĩa của biến thể/protocol.

### 2.3. Giới hạn bộ đếm

Bộ đếm IETF là **32-bit**; mỗi block tạo 64 byte. Không được đi qua ranh giới khiến counter lặp lại/wrap và tái sử dụng keystream. Giới hạn lý thuyết của cặp key/nonce theo counter 32-bit là 2³² block (khoảng **256 GiB**, nếu tính tất cả các giá trị counter); khi bắt đầu ở counter khác 0, phần còn lại nhỏ hơn. **Giới hạn của protocol/AEAD cụ thể có thể còn nghiêm hơn**; không lấy con số tối đa lý thuyết làm quota vận hành mặc định.

Trước khi mã hóa dữ liệu khổng lồ, cần tính số block bằng cách không tràn số nguyên, ví dụ công thức toán học `ceil(bytes / 64)` và kiểm đủ không gian counter từ giá trị bắt đầu. Với file lớn, thiết kế chia file thành các **record độc lập có nonce mới và authentication tag** thay vì chỉ tăng counter bất tận. Mỗi record nên có sequence number/metadata được xác thực.

## 3. Mối nguy nghiêm trọng: tái sử dụng keystream

### 3.1. Cùng (key, nonce) có thể làm lộ quan hệ giữa hai plaintext

Ký hiệu hai plaintext là `P1` và `P2`, nếu chúng bị mã hóa bằng **cùng keystream `K`** thì:

~~~text
C1 = P1 XOR K
C2 = P2 XOR K

C1 XOR C2
 = (P1 XOR K) XOR (P2 XOR K)
 = P1 XOR P2
~~~

Keystream bị triệt tiêu. Kẻ quan sát biết **XOR của hai plaintext**; nếu biết/đoán được một plaintext, có thể suy ra phần tương ứng của plaintext còn lại. Đây không phải lỗi xác suất nhỏ của JDK: đó là hệ quả toán học trực tiếp của XOR stream cipher.

**Quy tắc bảo mật tuyệt đối:** với cùng một key, mỗi lần mã hóa độc lập phải dùng một **nonce khác nhau**. Không lặp lại cặp (key, nonce) trong ChaCha20, và điều này **cũng bắt buộc với ChaCha20-Poly1305** vì tái sử dụng nonce có thể phá cả tính bí mật lẫn xác thực.

### 3.2. Nonce không cần giữ bí mật, nhưng phải duy nhất

Không được tạo nonce bằng `"000000000000"` cố định cho mọi request chỉ vì nonce không phải secret. Ngược lại, **nonce có thể đi kèm ciphertext** và thường được lưu trong record để phía nhận tái tạo cùng luồng.

Cách tạo nonce có hai chiến lược thường gặp:

| Chiến lược | Ưu điểm | Trách nhiệm còn lại |
| --- | --- | --- |
| 12 byte từ `SecureRandom` cho mỗi message | Đơn giản cho workload vừa phải và test; xác suất trùng rất thấp nếu lượng message không quá lớn | **Không có bảo đảm tuyệt đối** về uniqueness; đánh giá birthday collision theo tổng số lần mã hóa cùng key. |
| Counter/sequence được quản lý bền vững và mã hóa thành nonce 12 byte | Có thể bảo đảm duy nhất trong một không gian key nếu quản lý đúng | Cần state không rollback, không đụng độ giữa thread/process/host, reset/key rotation an toàn. |
| Partition nonce space theo sender + sequence | Hỗ trợ nhiều tiến trình/sender dưới cùng key | Phải cấp sender ID duy nhất và bảo đảm sequence không lặp. |

Ví dụ runnable dùng `SecureRandom.nextBytes(nonce)` để test, nhưng **sản phẩm có volume rất lớn hoặc nhiều sender chia sẻ key cần chiến lược duy nhất chắc chắn hơn**. Khi lưu state nonce/counter, phải tính tới crash, rollback backup và nhân bản hệ thống. Không giảm kích thước nonce để tiện truyền; JCE ChaCha20 IETF yêu cầu **12 byte**.

### 3.3. ChaCha20 thuần không chống sửa đổi ciphertext

Vì `C = P XOR K`, người tấn công có thể thay đổi một bit ciphertext; phía nhận sẽ thu được bit plaintext tương ứng bị thay đổi, **không cần biết key**:

~~~text
original:  C[i] = P[i] XOR K[i]
tampered:  C'[i] = C[i] XOR 0000_0001
decrypted: P'[i] = P[i] XOR 0000_0001
~~~

Không có authentication tag nên `Cipher.doFinal(...)` của **`ChaCha20` thuần** có thể hoàn tất bình thường và trả plaintext đã bị sửa. Trường hợp plaintext sau sửa trông như văn bản lỗi không làm cipher tự ném exception; mã hóa không tương đương xác thực dữ liệu.

**Kết luận thiết kế:** với dữ liệu có nguy cơ bị sửa hoặc giả mạo, ưu tiên **`ChaCha20-Poly1305`** (AEAD), hoặc một giao thức kết hợp mã hóa + MAC chuẩn đã được thiết kế/kiểm chứng. Không tự tạo giải pháp bằng cách nối một `hash` không có khóa vào ciphertext; hash không xác thực danh tính bên gửi.

## 4. API ChaCha20 thuần trong Java 11

Java 11 triển khai ChaCha20 và ChaCha20-Poly1305 theo **JEP 329**, cung cấp algorithm names trong JCA/JCE. Dùng **`javax.crypto.Cipher`** từ `java.base`:

~~~java
Cipher cipher = Cipher.getInstance("ChaCha20");
~~~

Với provider SunJCE của JDK 11 thông thường, tên chính thức `"ChaCha20"` đã đủ để lấy stream cipher. Không dựa vào string biến thể không được chuẩn hóa giữa mọi provider, như tự nối `"/CTR/PKCS5Padding"` vào ChaCha20. Thuật toán stream này **không sử dụng PKCS#5 padding**.

### 4.1. Khóa 256-bit bằng KeyGenerator

~~~java
SecureRandom rng = new SecureRandom();
KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
generator.init(256, rng);
SecretKey key = generator.generateKey();
~~~

Đoạn trên là **minh họa** trong scope có imports. Với SunJCE, `KeyGenerator` sinh key phù hợp ChaCha20. Dùng CSPRNG, quản lý key bằng secret manager/KMS/HSM thích hợp với hệ thống; không sử dụng `"password".getBytes(UTF_8)` trực tiếp làm key.

Nếu đầu vào là **password của người dùng**, phải sử dụng KDF được thiết kế cho password với salt và cost thích hợp (ví dụ Argon2id qua thư viện được phê duyệt, hoặc PBKDF2 theo chính sách), sau đó tạo key đúng 32 byte. Không tự trộn/slice password hoặc hash không salt rồi coi đó là key ngẫu nhiên.

`SecretKeySpec` hữu ích khi có **key bytes 32 byte đã được cung cấp an toàn** hoặc khi chạy **test vector công khai**:

~~~java
byte[] knownKey = new byte[32];
// Trong test vector công khai mới gán bytes đã biết.
SecretKey key = new SecretKeySpec(knownKey, "ChaCha20");
~~~

**Không sử dụng `new byte[32]` làm khóa thật**. Key toàn zero hoặc vector test là dữ liệu công khai, chỉ dùng trong unit test.

### 4.2. ChaCha20ParameterSpec: nonce và counter

~~~java
byte[] nonce = new byte[12];
rng.nextBytes(nonce);

ChaCha20ParameterSpec parameters =
        new ChaCha20ParameterSpec(nonce, 1);

Cipher cipher = Cipher.getInstance("ChaCha20");
cipher.init(Cipher.ENCRYPT_MODE, key, parameters);
byte[] ciphertext = cipher.doFinal(plaintextBytes);
~~~

`ChaCha20ParameterSpec` (Since Java 11) yêu cầu:

- **Nonce đúng 12 byte**. Sai độ dài gây `IllegalArgumentException` ở constructor; `null` gây `NullPointerException`.
- **Counter kiểu `int`** là giá trị khởi đầu của block counter 32 bit. Trong Java, `int` có dấu nhưng tham số biểu diễn word 32-bit; không tự diễn giải một giá trị âm là «counter không hợp lệ» nếu provider không quy định như vậy.
- `getNonce()` trả **bản sao mảng** theo Javadoc, tránh lộ trực tiếp vùng nhớ nội bộ của `ChaCha20ParameterSpec`.

`Cipher.init(...)` cần key đúng 256 bit; key sai kích thước có thể bị từ chối bằng `InvalidKeyException`. Giữa các JCE provider, ngoại lệ/mô tả lỗi có thể khác đôi chút, nên vẫn dùng thuật toán/provider nằm trong compatibility matrix của sản phẩm.

### 4.3. Mã hóa và giải mã bằng cùng bộ tham số

~~~java
Cipher encrypt = Cipher.getInstance("ChaCha20");
encrypt.init(Cipher.ENCRYPT_MODE, key,
        new ChaCha20ParameterSpec(nonce, 1));
byte[] encrypted = encrypt.doFinal(plaintextBytes);

Cipher decrypt = Cipher.getInstance("ChaCha20");
decrypt.init(Cipher.DECRYPT_MODE, key,
        new ChaCha20ParameterSpec(nonce, 1));
byte[] decrypted = decrypt.doFinal(encrypted);
~~~

Đây là đoạn **minh họa** giả định `key`, `nonce`, `plaintextBytes` đã được tạo. **Việc giải mã dùng lại nonce và counter của cùng message là đúng** — vì phải phát lại cùng keystream để XOR ngược. Điều bị cấm là **mã hóa một message độc lập khác** bằng cùng (key, nonce) hoặc để các khoảng counter chồng lấn.

Một instance `Cipher` sau khi dùng/`doFinal` **không được chia sẻ tùy tiện giữa các thread** và không được coi `Cipher.init` nhiều lần bằng cùng cặp (key,nonce) là cách tái sử dụng bộ mã hóa. Tạo instance riêng cho từng thao tác, quản lý vòng đời/khóa/nonce rõ ràng.

### 4.4. Xử lý theo chunk bằng update và doFinal

`Cipher.update(...)` cho phép mã hóa/giải mã theo nhiều đoạn thay vì nạp toàn bộ plaintext trong một lời gọi. Ví dụ mô hình:

~~~java
Cipher decrypt = Cipher.getInstance("ChaCha20");
decrypt.init(Cipher.DECRYPT_MODE, key,
        new ChaCha20ParameterSpec(nonce, 1));

byte[] a = decrypt.update(ciphertext, 0, 7);
byte[] b = decrypt.update(ciphertext, 7, 80);
byte[] c = decrypt.doFinal(
        ciphertext, 87, ciphertext.length - 87);
~~~

Đoạn trên là **minh họa**, cần đảm bảo input dài ít nhất 87 byte. Các đoạn `a/b/c` được ghép **đúng thứ tự** để tái lập plaintext. Tùy API/provider/chế độ, `Cipher.update(...)` có thể trả `null` hoặc mảng độ dài 0 khi chưa có output, nên code robust cần kiểm trước khi ghép.

**Không tạo một `Cipher` mới với counter 1 cho mỗi chunk** rồi nghĩ rằng kết quả là stream mã hóa liên tục. Một instance duy nhất đã được init đúng sẽ quản lý trạng thái keystream, kể cả lúc chunk cắt giữa hai block 64 byte.

Khi xử lý dữ liệu **không tin cậy**, **AEAD streaming** cần cẩn trọng hơn: không được giải phóng/đưa ra hệ thống plaintext chưa xác thực trước khi kiểm Poly1305 tag ở cuối. Nếu dùng `Cipher.update` trong AEAD mode, tuyệt đối không hành động dựa trên plaintext chưa xác thực trước `doFinal` thành công.

## 5. Vì sao ứng dụng nên dùng ChaCha20-Poly1305?

### 5.1. AEAD kết hợp bí mật và xác thực

**ChaCha20-Poly1305** là **Authenticated Encryption with Associated Data (AEAD)**:

- ChaCha20 tạo ciphertext, bảo vệ **tính bí mật**.
- Poly1305 tạo **authentication tag 16 byte (128 bit)** cho ciphertext và metadata được xác thực.
- **AAD** (*Additional Authenticated Data*) là dữ liệu **không cần che giấu** nhưng phải chống sửa đổi: version của record, tên protocol, message ID, context của người gửi...
- Bên nhận chỉ chấp nhận plaintext khi tag xác thực chính xác. Sửa ciphertext/tag/AAD thường gây `AEADBadTagException` ở `doFinal`.

Một packet đơn giản có thể được đóng gói thành:

~~~text
version | nonce (12 bytes) | ciphertext (plaintextLength bytes) | tag (16 bytes)
                \_______________________ AEAD _______________________/
          version/context can be included in AAD
~~~

Đây là **format minh họa**; một protocol sản phẩm thật phải xác định rõ version/length/endian, AAD, message boundaries, khóa nào được dùng, nonce source và chống replay. Phần nonce và ciphertext/tag có thể được truyền công khai; **key tuyệt đối không nằm trong packet**.

**AEAD không tự chống replay** của một packet hợp lệ nguyên vẹn. Nếu attacker phát lại cùng packet với nonce, ciphertext và tag đã được server chấp nhận trước đó, tag vẫn có thể hợp lệ. Hệ thống cần sequence number/replay window/state hoặc idempotency theo tầng ứng dụng khi yêu cầu.

### 5.2. JCE: IvParameterSpec chứ không phải ChaCha20ParameterSpec

Java 11 có hai transformation names cần phân biệt:

| Transformation | ParameterSpec trong ví dụ SunJCE | Kết quả |
| --- | --- | --- |
| `Cipher.getInstance("ChaCha20")` | `new ChaCha20ParameterSpec(nonce12, counter)` | Stream ciphertext không có tag. |
| `Cipher.getInstance("ChaCha20-Poly1305")` | `new IvParameterSpec(nonce12)` | Ciphertext + Poly1305 tag 16 byte. |

Với ChaCha20-Poly1305, JCE/provider quản lý việc dùng ChaCha20 block counter **0** để sinh khóa Poly1305 và block counter **1 trở đi** cho payload theo thiết kế RFC 8439. Không tự đưa counter như khi cấu hình raw ChaCha20. **Không thay `IvParameterSpec` bằng `ChaCha20ParameterSpec`** khi khởi tạo AEAD rồi mặc định mọi provider phải hiểu.

### 5.3. Mẫu AEAD khuyến nghị

~~~java
// Đoạn minh họa, key do KeyGenerator cung cấp, nonce mới và DUY NHẤT.
Cipher authenticated = Cipher.getInstance("ChaCha20-Poly1305");
authenticated.init(Cipher.ENCRYPT_MODE, key,
        new IvParameterSpec(nonce));

authenticated.updateAAD(aadBytes); // BEFORE processing plaintext
byte[] ciphertextAndTag = authenticated.doFinal(plaintextBytes);
~~~

Giải mã:

~~~java
Cipher verified = Cipher.getInstance("ChaCha20-Poly1305");
verified.init(Cipher.DECRYPT_MODE, key,
        new IvParameterSpec(nonce));

verified.updateAAD(aadBytes);
byte[] plaintext = verified.doFinal(ciphertextAndTag);
// Chỉ dùng plaintext nếu doFinal hoàn tất bình thường.
~~~

Đối với AEAD, không tái sử dụng **cùng key và nonce** cho một lần mã hóa khác, dù plaintext hoặc AAD có khác. `updateAAD(...)` phải được gọi **trước** khi xử lý dữ liệu encryption/decryption theo hợp đồng `Cipher`. Khi giải mã, **AAD phải khớp chính xác theo bytes**. Chuỗi hiển thị giống nhau nhưng mã hóa khác UTF-8/normalization vẫn có thể cho bytes khác và làm tag không hợp lệ.

**Đừng tự viết Poly1305, tự ghép HMAC tùy ý, hoặc trộn raw ChaCha20 và ChaCha20-Poly1305 dùng cùng key/nonce vào một protocol.** Dùng transformation AEAD được JCE hỗ trợ và có test vector/integration tests.

## 6. Chương trình Java 11 runnable: RFC vector, streaming, tamper và AEAD

Để không phụ thuộc network, chương trình **ChaCha20StreamDemo.java** chạy toàn bộ trong RAM, bằng Java Cryptography Architecture/JCE. Nó minh họa cả **mô hình stream cipher** và lý do nên chuyển sang **AEAD** cho ứng dụng thực tế.

Các phép kiểm thử được tách thành tám nhóm:

1. **RFC 8439 `2.3.2:** dùng key công khai `00 01 ... 1f`, nonce `000000090000004a00000000`, counter `1`, mã hóa 64 byte zero để tạo đúng 64 byte keystream chuẩn.
2. **Unicode và nhiều block:** tạo key bằng `KeyGenerator`, nonce bằng `SecureRandom`, mã hóa tiếng Việt/emoji và payload dài hơn 128 byte; xác nhận ciphertext dài bằng plaintext.
3. **Giải mã theo chunk:** một `Cipher` liên tục xử lý chunk 7 byte, 80 byte và phần còn lại; `doFinal` trả lại plaintext gốc kể cả chunk cắt giữa block.
4. **Malleability:** sửa một bit ciphertext của ChaCha20 thuần; giải mã không báo lỗi, mà đúng một bit plaintext đổi theo.
5. **Validation:** nonce 11 byte bị constructor từ chối; khóa 16 byte bị SunJCE từ chối.
6. **AEAD round-trip:** tạo **key mới** và **nonce mới**, đặt AAD, mã hóa và giải mã; format test là `nonce || ciphertext || tag`.
7. **Tamper rejection:** sửa một bit của `tag` và xác nhận `AEADBadTagException`.
8. **AAD authentication:** đưa AAD sai khi giải mã và xác nhận tag check thất bại.

**Quan trọng:** test vector dùng khóa/nonce cố định **chỉ để đối chiếu chuẩn**; không dùng chúng cho dữ liệu bí mật. Nhánh raw ChaCha20 trong chương trình chỉ minh họa, **không phải mẫu production encryption**. Mẫu production nên dùng AEAD, quản lý khóa/nonce và metadata theo protocol được phê duyệt.

Tạo file **ChaCha20StreamDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class ChaCha20StreamDemo {
    private static void check(boolean valid, String message) {
        if (!valid) throw new AssertionError(message);
    }

    private static byte[] decodeHex(String hex) {
        String clean = hex.replace(" ", "").replace("\n", "");
        if ((clean.length() & 1) != 0) {
            throw new IllegalArgumentException("Odd hex length");
        }
        byte[] bytes = new byte[clean.length() / 2];
        for (int i = 0; i < bytes.length; i++) {
            int hi = Character.digit(clean.charAt(i * 2), 16);
            int lo = Character.digit(clean.charAt(i * 2 + 1), 16);
            if (hi < 0 || lo < 0) throw new IllegalArgumentException("Bad hex");
            bytes[i] = (byte) ((hi << 4) | lo);
        }
        return bytes;
    }

    private static Cipher raw(int mode, SecretKey key, byte[] nonce,
                              int counter) throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20");
        cipher.init(mode, key, new ChaCha20ParameterSpec(nonce, counter));
        return cipher;
    }

    private static byte[] concatenate(byte[] a, byte[] b) {
        byte[] joined = Arrays.copyOf(a, a.length + b.length);
        System.arraycopy(b, 0, joined, a.length, b.length);
        return joined;
    }

    public static void main(String[] args) throws Exception {
        byte[] vectorKey = new byte[32];
        for (int i = 0; i < vectorKey.length; i++) {
            vectorKey[i] = (byte) i;
        }
        SecretKey knownKey = new SecretKeySpec(vectorKey, "ChaCha20");
        byte[] vectorNonce = decodeHex("000000090000004a00000000");
        byte[] expectedBlock = decodeHex(
                "10f1e7e4d13b5915500fdd1fa32071c4"
              + "c7d1f4c733c068030422aa9ac3d46c4e"
              + "d2826446079faa0914c2d705d98b02a2"
              + "b5129cd1de164eb9cbd083e8a2503c4e");
        byte[] actualBlock = raw(Cipher.ENCRYPT_MODE, knownKey,
                vectorNonce, 1).doFinal(new byte[64]);
        check(Arrays.equals(expectedBlock, actualBlock),
                "RFC 8439 block-function test vector");
        System.out.println("PASS RFC 8439 ChaCha20 test vector");

        SecureRandom random = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256, random);
        SecretKey key = generator.generateKey();
        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        byte[] plaintext = ("Ti\u1EBFng Vi\u1EC7t "
                + new String(Character.toChars(0x1F642))
                + " | " + "data-".repeat(35))
                .getBytes(StandardCharsets.UTF_8);
        check(plaintext.length > 128, "multi-block input");

        byte[] encrypted = raw(Cipher.ENCRYPT_MODE, key, nonce, 1)
                .doFinal(plaintext);
        check(encrypted.length == plaintext.length,
                "stream cipher preserves byte length");
        check(!Arrays.equals(encrypted, plaintext),
                "ciphertext must differ for this fixture");
        System.out.println("PASS Unicode and multi-block encryption");

        Cipher decrypt = raw(Cipher.DECRYPT_MODE, key, nonce, 1);
        ByteArrayOutputStream recovered = new ByteArrayOutputStream();
        byte[] segment1 = decrypt.update(encrypted, 0, 7);
        byte[] segment2 = decrypt.update(encrypted, 7, 80);
        byte[] segment3 = decrypt.doFinal(encrypted, 87,
                encrypted.length - 87);
        if (segment1 != null) recovered.write(segment1);
        if (segment2 != null) recovered.write(segment2);
        if (segment3 != null) recovered.write(segment3);
        check(Arrays.equals(plaintext, recovered.toByteArray()),
                "incremental decrypt across block boundary");
        System.out.println("PASS streaming update and doFinal round-trip");

        byte[] changed = encrypted.clone();
        changed[0] ^= 1;
        byte[] changedPlain = raw(Cipher.DECRYPT_MODE, key, nonce, 1)
                .doFinal(changed);
        check(changedPlain[0] == (byte) (plaintext[0] ^ 1),
                "bit flip propagates to same plaintext bit");
        check(Arrays.equals(Arrays.copyOfRange(changedPlain, 1,
                        changedPlain.length),
                Arrays.copyOfRange(plaintext, 1, plaintext.length)),
                "raw ChaCha20 has no authentication");
        System.out.println("PASS raw stream cipher is malleable");

        boolean wrongNonceRejected = false;
        try {
            new ChaCha20ParameterSpec(new byte[11], 1);
        } catch (IllegalArgumentException expected) {
            wrongNonceRejected = true;
        }
        check(wrongNonceRejected, "nonce must have 12 bytes");
        boolean invalidKeyRejected = false;
        try {
            raw(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(new byte[16], "ChaCha20"),
                    new byte[12], 1);
        } catch (java.security.InvalidKeyException expected) {
            invalidKeyRejected = true;
        }
        check(invalidKeyRejected, "ChaCha20 requires a 32-byte key");
        System.out.println("PASS key and nonce validation");

        SecretKey aeadKey = generator.generateKey();
        byte[] aeadNonce = new byte[12];
        random.nextBytes(aeadNonce);
        byte[] associatedData =
                "application=lesson;version=1".getBytes(StandardCharsets.UTF_8);
        Cipher authenticated = Cipher.getInstance("ChaCha20-Poly1305");
        authenticated.init(Cipher.ENCRYPT_MODE, aeadKey,
                new IvParameterSpec(aeadNonce));
        authenticated.updateAAD(associatedData);
        byte[] ciphertextAndTag = authenticated.doFinal(plaintext);
        check(ciphertextAndTag.length == plaintext.length + 16,
                "Poly1305 tag is 16 bytes");
        byte[] envelope = concatenate(aeadNonce, ciphertextAndTag);

        byte[] storedNonce = Arrays.copyOfRange(envelope, 0, 12);
        byte[] storedPayload = Arrays.copyOfRange(
                envelope, 12, envelope.length);
        Cipher verified = Cipher.getInstance("ChaCha20-Poly1305");
        verified.init(Cipher.DECRYPT_MODE, aeadKey,
                new IvParameterSpec(storedNonce));
        verified.updateAAD(associatedData);
        check(Arrays.equals(plaintext, verified.doFinal(storedPayload)),
                "authenticated decryption with same AAD");
        System.out.println("PASS authenticated AEAD round-trip");

        byte[] forged = storedPayload.clone();
        forged[forged.length - 1] ^= 1;
        Cipher rejectTamper = Cipher.getInstance("ChaCha20-Poly1305");
        rejectTamper.init(Cipher.DECRYPT_MODE, aeadKey,
                new IvParameterSpec(storedNonce));
        rejectTamper.updateAAD(associatedData);
        boolean tamperRejected = false;
        try {
            rejectTamper.doFinal(forged);
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        check(tamperRejected, "AEAD must reject altered tag");
        System.out.println("PASS AEAD rejects tampered ciphertext");

        Cipher rejectAad = Cipher.getInstance("ChaCha20-Poly1305");
        rejectAad.init(Cipher.DECRYPT_MODE, aeadKey,
                new IvParameterSpec(storedNonce));
        rejectAad.updateAAD("wrong-context".getBytes(
                StandardCharsets.UTF_8));
        boolean aadRejected = false;
        try {
            rejectAad.doFinal(storedPayload);
        } catch (AEADBadTagException expected) {
            aadRejected = true;
        }
        check(aadRejected, "AEAD must authenticate associated data");
        System.out.println("PASS AEAD authenticates associated data");

        System.out.println("ALL CHACHA20 STREAM TESTS PASSED");
    }
}
~~~

### 6.1. Biên dịch và chạy

Dùng JDK 11 hoặc JDK mới hỗ trợ target Java 11, trong thư mục chứa file:

~~~bash
javac --release 11 -encoding UTF-8 ChaCha20StreamDemo.java
java ChaCha20StreamDemo
~~~

Không cần thư viện thứ ba. JEP 329 tích hợp ChaCha20/ChaCha20-Poly1305 vào SunJCE từ Java 11. Nếu chạy trên một bản Java/provider khác, phải xác minh `Cipher.getInstance(...)` thực sự hỗ trợ thuật toán theo cấu hình runtime đó; **Java SE algorithm name** và **sự hiện diện của implementation provider** là hai lớp liên quan nhưng không đồng nhất trong mọi môi trường.

**Stdout khi toàn bộ test thành công:**

~~~text
PASS RFC 8439 ChaCha20 test vector
PASS Unicode and multi-block encryption
PASS streaming update and doFinal round-trip
PASS raw stream cipher is malleable
PASS key and nonce validation
PASS authenticated AEAD round-trip
PASS AEAD rejects tampered ciphertext
PASS AEAD authenticates associated data
ALL CHACHA20 STREAM TESTS PASSED
~~~

Chương trình dùng `check(...)` ném `AssertionError` để test luôn có hiệu lực mà không cần bật `-ea`. Test vector RFC xác thực **kết quả thuật toán đúng chuẩn**; test round-trip riêng kiểm pipeline Java và Unicode; test tamper riêng chứng minh tính năng bảo vệ/không bảo vệ của hai primitive.

### 6.2. Giải thích chi tiết các assertion

**RFC vector:** ChaCha20 với plaintext 64 byte zero có ciphertext **bằng đúng 64 byte keystream**. Đối chiếu giá trị chuẩn bắt đầu bằng `10 f1 e7 e4...` và kết thúc bằng `...a2 50 3c 4e` giúp phát hiện sai thuật toán/endianness/counter/nonce. Dùng vector này không tạo một khóa bí mật vì mọi bytes đều công khai.

**Multi-block + Unicode:** plaintext gồm tiếng Việt, U+1F642 và dữ liệu lặp để vượt 128 byte. `encrypted.length == plaintext.length` xác nhận stream cipher thuần không padding/tag; `doFinal` với nonce/counter tương ứng được dùng để giải mã.

**Streaming:** một `Cipher` trong `DECRYPT_MODE` nhận các đoạn có điểm cắt không trùng ranh giới block 64 byte. JCE giữ state keystream giữa các `update`. Chương trình ghép output theo đúng thứ tự, xử lý `null` nếu có, rồi so sánh byte-for-byte với plaintext.

**Malleability:** thay đổi một bit ở byte ciphertext đầu khiến byte plaintext đầu đổi đúng bit; **không có exception** báo sửa đổi. Phần còn lại của plaintext vẫn giống cũ trong test. Điều này cho thấy **ChaCha20 thuần không cung cấp authentication** và không thể tự tin coi plaintext đã xác thực.

**Validation:** constructor `ChaCha20ParameterSpec` từ chối nonce độ dài khác 12 byte, còn provider kiểm tra key đúng 256 bit khi init. Các kiểm tra này **không** tự bảo đảm nonce độc nhất: hai nonce 12 byte giống hệt nhau vẫn có độ dài đúng nhưng không được phép dùng lặp dưới cùng key.

**AEAD:** dùng **key và nonce riêng khác nhánh raw**. Ciphertext của Java SunJCE chứa **16 byte tag cuối**; chương trình gửi/nhận envelope `nonce || ciphertext || tag`, kiểm đúng AAD và trả về plaintext gốc.

**Sửa tag:** đảo một bit của `tag` rồi giải mã, nhận `AEADBadTagException`. Không coi `AEADBadTagException` là lỗi charset hoặc lỗi HTTP; nó có nghĩa xác thực packet không thành công (có thể do key, nonce, AAD, ciphertext hoặc tag không khớp).

**AAD sai:** ciphertext/tag hoàn toàn giữ nguyên nhưng context AAD khác, xác thực vẫn thất bại. Điều này bảo vệ các metadata mà ứng dụng đã chủ động đưa vào AAD, **không** bảo vệ những metadata khác nếu bị bỏ ngoài AAD.

## 7. Thiết kế record an toàn nếu dùng ChaCha20-Poly1305

### 7.1. Envelope có version và các trường được xác thực

Trong bài tập, `nonce||ciphertext||tag` đủ để minh họa. Với sản phẩm thực, nên định nghĩa một envelope **có định dạng được version hóa**, ví dụ:

~~~text
+-----------+----------+--------------+-------------------+
| version   | nonce    | ciphertext   | Poly1305 tag      |
| 1 byte    | 12 bytes | variable     | 16 bytes          |
+-----------+----------+--------------+-------------------+

AAD can contain:
  version, algorithm id, tenant/session context, message sequence,
  content type, sender identity (as defined by the application).
~~~

Khi decode:

1. Kiểm **độ dài tối thiểu**: version + nonce + tag; từ chối record không hợp lệ trước khi cấp phát lớn.
2. Xác minh **version/algorithm** đã được ứng dụng hỗ trợ; không tự downgrade sang cipher yếu.
3. Xác định đúng key theo **key ID** trong hệ thống quản lý khóa, **không** đưa raw key vào envelope.
4. Lấy nonce, ciphertext/tag, tái tạo AAD từ **những bytes chính xác** theo protocol.
5. Gọi AEAD `doFinal` và **chỉ sau thành công** mới cho phép parser/consumer sử dụng plaintext.
6. Kiểm **message ID, replay window, authorization** và nội dung nghiệp vụ riêng.

Nếu giao thức cho phép nhiều sender dùng cùng key, không chỉ dùng một bộ đếm in-memory bắt đầu từ 0 trên mỗi host; điều đó có thể tạo nonce trùng khi hai host cùng khởi động. Thiết kế nonce coordination hoặc tách key theo sender.

### 7.2. Khóa, nonce và counter phải được quản lý độc lập

| Giá trị | Cần bí mật? | Cần duy nhất? | Nơi lưu/trao đổi |
| --- | --- | --- | --- |
| **Secret key** | **Có** | Không bắt buộc khác nhau cho mỗi message; nhưng cần rotation/lifecycle | KMS/HSM/secret store, không log hoặc gửi trong envelope |
| **Nonce** | Không | **Độc nhất với mỗi key và mỗi lần mã hóa độc lập** | Có thể lưu cạnh ciphertext, cần chống trùng |
| **Counter** | Không | Cần không lặp lại block keystream trong cùng key/nonce | Internal state của JCE hoặc policy đã quy định |
| **AAD** | Không nhất thiết | Không phải nonce; phải được xác thực đúng | Có thể là header/metadata công khai |
| **Poly1305 tag** | Không | Phải gắn chính xác với key, nonce, AAD và ciphertext | Lưu kèm ciphertext và kiểm trước khi dùng plaintext |

Một cặp (key, nonce) được lặp là lỗi bảo mật **kể cả khi plaintext hai lần khác nhau**. **Không** dùng timestamp mili giây làm nguồn nonce duy nhất: nhiều request trong cùng mili giây, clock rollback hoặc nhiều host có thể trùng. Nếu dùng random nonces, đánh giá xác suất trùng phù hợp với tải và tuổi thọ key.

### 7.3. Streaming dữ liệu lớn: chia record AEAD chứ không xuất plaintext chưa verify

ChaCha20 thuần hỗ trợ xử lý từng chunk liên tục. Nhưng khi áp dụng **AEAD**, tag là kết quả xác thực của một message; nếu bạn decrypt hàng GiB và phát ngay plaintext cho hệ thống khác **trước khi kiểm tra tag**, attacker có thể đưa nội dung giả hoặc sửa vào downstream trước khi cipher phát hiện lỗi.

Giải pháp:

- Chia stream thành các **record có giới hạn dung lượng** (ví dụ theo yêu cầu hệ thống), mỗi record có **nonce riêng** và tag AEAD riêng.
- Đưa `sequenceNumber` / record index vào **AAD**, và nếu cần kiểm thứ tự thì quản lý state/replay window ở tầng ứng dụng.
- **Xác thực đủ một record trước khi công bố plaintext record đó**.
- Thiết kế rõ bản ghi **cuối cùng** hoặc tổng số records; nếu thiếu record kết thúc, không coi stream hoàn thành.
- Hạn chế kích thước record, queue, bộ nhớ; tránh xử lý bytes nhạy cảm chưa xác thực.
- Khi retry một record, không «mã hóa mới» bằng một nonce cũ trên dữ liệu khác. Xác định policy retransmission của packet đã mã hóa, và chống replay ở consumer.

Đó là một **giao thức record AEAD**, không phải chỉ gọi `Cipher.update(...)` mà tự động nhận được stream đã xác thực từng byte.

## 8. Những sai lầm và cách phòng tránh

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `Cipher.getInstance("ChaCha20")` để bảo vệ thông điệp có thể bị sửa đổi. | Stream cipher thuần không xác thực, có tính malleable. | Dùng `ChaCha20-Poly1305` hoặc AEAD đã được phê duyệt. |
| Tái sử dụng `(key, nonce)` khi mã hóa request khác. | Tái sử dụng keystream; có thể lộ quan hệ plaintext và phá AEAD. | Quản lý nonce duy nhất theo vòng đời mỗi key, có kiểm tra concurrency/restart. |
| Tạo nonce 12 byte toàn zero cho mọi message. | Độ dài đúng nhưng giá trị trùng. | Dùng chiến lược unique nonce, không dùng fixture test. |
| Reset counter bằng cách init cipher mới cho mỗi chunk của cùng message. | Có nguy cơ lặp block keystream. | Dùng một Cipher liên tục qua `update/doFinal` hoặc record AEAD riêng có nonce mới. |
| Tưởng tăng counter làm tái sử dụng nonce cho các message độc lập luôn an toàn. | Các khoảng counter có thể chồng hoặc bị reset. | Dùng nonce khác cho mỗi message theo protocol; không tự chia khoảng tùy tiện. |
| Dùng `ChaCha20ParameterSpec` cho `ChaCha20-Poly1305`. | Hai transformation có cấu hình khác nhau. | Raw: ChaCha20ParameterSpec. AEAD Java 11: IvParameterSpec(nonce12). |
| Truyền password bytes trực tiếp vào `SecretKeySpec`. | Key dễ đoán/không đủ entropy hoặc sai kích thước. | Sinh key bằng KeyGenerator, hoặc qua KDF được phê duyệt. |
| Gọi `new byte[32]` làm key thật. | Khóa toàn zero dễ biết. | Key ngẫu nhiên từ CSPRNG/KMS; vector cố định chỉ dùng cho test. |
| Dùng `String.length()` làm số byte cần mã hóa. | UTF-16 code units khác UTF-8 bytes. | Luôn convert text sang UTF-8 bytes trước khi mã hóa. |
| Mong raw ChaCha20 tự ném exception khi ciphertext bị sửa. | Không có authentication tag. | Dùng AEAD và xử lý `AEADBadTagException`. |
| Gọi `updateAAD` sau khi mã hóa/giải mã dữ liệu. | Vi phạm thứ tự input AAD của AEAD API. | Cập nhật AAD trước `update`/`doFinal` cho dữ liệu. |
| Dùng AAD khác nhau do thứ tự JSON hoặc Unicode normalization. | Bytes AAD không khớp → tag không đúng. | Chuẩn hóa format bytes chính xác, định nghĩa protocol canonical. |
| Xem ciphertext/tag dài đúng là đủ để xác thực. | Dữ liệu có thể bị sửa và giữ cùng độ dài. | Luôn chạy AEAD tag verification trước khi dùng plaintext. |
| Phát plaintext từ `Cipher.update` AEAD trước `doFinal`. | Tag cuối chưa được kiểm, dữ liệu chưa đáng tin. | Buffer/giới hạn record và công bố plaintext sau verify. |
| Nghĩ tag AEAD tự chống replay. | Packet cũ có tag đúng vẫn có thể được gửi lại. | Dùng sequence number, replay window hoặc message ID/state. |
| Tái dùng một instance `Cipher` giữa nhiều thread. | State mutable, dễ race/corrupt keystream. | Tạo Cipher độc lập cho mỗi operation; quản lý queue/record. |
| Để keystream counter wrap hoặc cho một nonce xử lý lượng dữ liệu quá lớn. | Lặp block stream, phá bí mật. | Kiểm tổng blocks và giới hạn protocol; chia record/nonce mới. |
| Lưu raw key trong URL, log, nguồn code hoặc cùng plaintext. | Rò rỉ key, mất mọi bảo vệ. | Dùng secret store/KMS, quyền truy cập/rotation, không ghi secret vào log. |
| Dùng RC4 để «tối ưu tương thích» thay ChaCha20. | RC4 lỗi thời/không phù hợp thiết kế mới. | Dùng AEAD hiện hành, xác minh runtime/provider. |
| Tự viết Poly1305, nonce mixing hoặc «encrypt-then-hash» không key. | Dễ thiếu tính xác thực hoặc sai chuẩn. | Dùng `Cipher.getInstance("ChaCha20-Poly1305")`. |
| Cho rằng TLS tự yêu cầu app bọc thêm ChaCha20 thủ công. | Dễ tạo rủi ro triển khai và key management không cần thiết. | Dùng TLS 1.3/JSSE theo cấu hình chuẩn; mã hóa cấp ứng dụng chỉ khi thật sự có yêu cầu end-to-end riêng. |

## 9. Bộ test mở rộng nên có cho dự án

| Loại test | Đầu vào/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Standard vector | RFC 8439 `2.3.2 | Đúng toàn bộ 64 byte keystream |
| Unicode | Tiếng Việt, U+1F642, ASCII | Round-trip đúng byte và ký tự |
| Stream crossing | Cắt chunk ở 7, 87, 129 byte | Không reset counter sai, ghép bytes đúng |
| Empty input | Plaintext 0 byte | Raw ciphertext 0 byte; AEAD có tag theo mode |
| Key length | Key 16 byte thay cho 32 | Init bị từ chối |
| Nonce length | Nonce 11 hoặc 13 byte | Parameter validation bị từ chối |
| Key/nonce uniqueness | Hệ thống nhiều sender/restart | Không có cặp (key,nonce) trùng để mã hóa |
| Malleability | Đảo một bit raw ciphertext | Raw ChaCha20 **không** tự xác thực |
| AEAD tamper | Sửa ciphertext/tag một bit | Tag verification thất bại |
| Wrong AAD | Decrypt với metadata khác | Tag verification thất bại |
| Wrong key/nonce AEAD | Key/nonce không khớp | Tag verification thất bại |
| Packet truncation | Thiếu 1 hoặc nhiều bytes tag/ciphertext | Từ chối, không xuất plaintext |
| Replay | Gửi lại packet hợp lệ cùng message ID | Protocol policy từ chối/reconcile phù hợp |
| Counter limit | Gần ngưỡng block cuối | Không wrap/cấp phát quá giới hạn |
| Resource bounds | File/stream lớn | Có giới hạn memory, record, concurrency, retry |

**Ghi chú kiểm thử:** lỗi `AEADBadTagException` của SunJCE được quan sát với `doFinal` trong ví dụ; các provider khác nhau có thể có chi tiết lỗi khác. Không phân biệt «sai key» và «ciphertext bị sửa» trong thông báo trả cho người dùng bên ngoài nếu điều đó gây lộ thông tin. Phía trong có thể ghi exception type/mã lỗi, nhưng không log key, nonce nhạy cảm theo context hay plaintext.

## 10. Câu hỏi tự đánh giá

**Câu 1.** Vì sao ChaCha20 được gọi là stream cipher?

**Đáp án:** Nó tạo **keystream** từ key/nonce/counter rồi XOR từng byte với plaintext. Với một đầu vào dài, nó tạo các keystream blocks 64 byte liên tiếp khi counter tăng.

**Câu 2.** Theo biến thể IETF của RFC 8439, key, nonce và counter có kích thước bao nhiêu?

**Đáp án:** Key **256 bit**, nonce **96 bit (12 byte)**, counter **32 bit**; mỗi block function tạo **64 byte** keystream.

**Câu 3.** Có thể dùng cùng key và nonce cho hai plaintext độc lập nếu chúng khác nhau không?

**Đáp án:** **Không.** Cùng keystream sẽ làm `C1 XOR C2 = P1 XOR P2`, có thể tiết lộ thông tin plaintext và phá cơ chế xác thực AEAD nếu cũng lặp nonce trong ChaCha20-Poly1305.

**Câu 4.** Một plaintext 101 byte sau khi mã hóa bằng ChaCha20 thuần có bao nhiêu byte ciphertext?

**Đáp án:** **101 byte**, vì đây là stream cipher không padding/tag. Với ChaCha20-Poly1305 theo ví dụ SunJCE, sẽ có thêm **16 byte Poly1305 tag** (nonce đóng gói riêng).

**Câu 5.** Khi giải mã một message, có được dùng lại nonce của message đó không?

**Đáp án:** **Có**. Giải mã phải dùng cùng key, nonce và counter đã dùng khi mã hóa **message đó**. Điều bị cấm là mã hóa **một message khác** với cùng cặp (key,nonce).

**Câu 6.** Vì sao đoạn plaintext bị sửa bit vẫn có thể giải mã «thành công» với raw ChaCha20?

**Đáp án:** Vì XOR stream cipher không có authentication tag. Bit ciphertext bị đổi làm bit plaintext tương ứng đổi mà `doFinal` không thể chứng minh dữ liệu nguyên vẹn.

**Câu 7.** Khác biệt Java API giữa ChaCha20 và ChaCha20-Poly1305 là gì?

**Đáp án:** Raw ChaCha20 dùng `ChaCha20ParameterSpec(nonce, counter)` và trả ciphertext không tag; ChaCha20-Poly1305 dùng `IvParameterSpec(nonce)`, cho phép AAD, trả ciphertext có Poly1305 tag 16 byte và kiểm tag khi giải mã.

**Câu 8.** Nếu attacker chỉ sửa AAD nhưng không sửa ciphertext, kết quả AEAD ra sao?

**Đáp án:** Nếu AAD đã được dùng trong việc xác thực, giải mã sẽ **thất bại khi kiểm tag**. Các bytes AAD gửi và nhận phải khớp chính xác.

**Câu 9.** Vì sao không thể dùng `"mật_khẩu".getBytes(UTF_8)` như key 256-bit?

**Đáp án:** Password không phải chuỗi key ngẫu nhiên 256 bit với entropy bảo đảm và có thể sai độ dài. Cần KeyGenerator/SecureRandom hoặc KDF được thiết kế cho password, kết hợp quản lý key phù hợp.

**Câu 10.** `Cipher.update` trong ChaCha20 thuần có cần khởi tạo lại nonce/counter cho mỗi chunk không?

**Đáp án:** **Không.** Dùng cùng một Cipher đã init để duy trì stream position. Nếu init lại từ counter cũ, có thể tái sử dụng keystream.

**Câu 11.** ChaCha20-Poly1305 có tự bảo vệ chống phát lại packet hợp lệ không?

**Đáp án:** **Không.** AEAD xác thực nội dung trong phạm vi key/nonce/AAD/tag, không tự duy trì replay window. Cần sequence/message ID và replay state nếu protocol yêu cầu.

**Câu 12.** Tại sao phải kiểm tag trước khi sử dụng plaintext được giải mã?

**Đáp án:** Vì plaintext chưa xác thực có thể do attacker điều khiển hoặc đến từ dữ liệu đã bị sửa. Với AEAD, chỉ sau `doFinal` kiểm tag thành công mới được chuyển plaintext sang xử lý nghiệp vụ.

**Câu 13.** Có nên tạo một nonce từ timestamp milli rồi chia sẻ key cho hàng chục worker không?

**Đáp án:** Không thể mặc định an toàn: nhiều worker có thể trùng thời gian, clock có thể rollback, và timestamp không đảm bảo duy nhất. Cần nonce allocation/partition hoặc CSPRNG + phân tích xác suất/volume và rotation.

**Câu 14.** Vì sao bài test RFC dùng key cố định `00..1f` nhưng ứng dụng thật không được làm vậy?

**Đáp án:** Test vector là dữ liệu công khai để so khớp thuật toán. Key bảo vệ bí mật phải có entropy phù hợp và được quản lý an toàn.

## 11. Checklist hoàn thành

- [ ] Phân biệt stream cipher với block cipher và hiểu `C = P XOR keystream`.
- [ ] Biết ChaCha20 IETF dùng key 32 byte, nonce 12 byte, counter 32 bit, keystream block 64 byte.
- [ ] Giải thích được nguyên lý ARX/20 rounds ở mức mô hình, không tự implement crypto primitive.
- [ ] Đặt **nonce duy nhất cho mỗi lần mã hóa dưới cùng key** và phòng trùng giữa các sender/restart.
- [ ] Không reset block counter giữa các `Cipher.update` của cùng stream.
- [ ] Biết raw ChaCha20 **không xác thực**, có thể bị sửa bit ciphertext mà không báo lỗi.
- [ ] Ưu tiên ChaCha20-Poly1305 AEAD hoặc AES-GCM cho dữ liệu cần bí mật và toàn vẹn.
- [ ] Dùng đúng `ChaCha20ParameterSpec` cho raw, `IvParameterSpec` cho ChaCha20-Poly1305.
- [ ] Gọi `updateAAD` trước data khi dùng AEAD; không phát plaintext khi chưa verify tag.
- [ ] Thiết kế envelope/protocol có version, nonce, ciphertext, tag, AAD, replay protection và giới hạn kích thước.
- [ ] Không log/commit secret key, không dùng key/nonce cố định của test trong sản phẩm thật.
- [ ] Chạy được `ChaCha20StreamDemo.java` với `javac --release 11`, đủ tám nhóm PASS.
- [ ] Xác minh behavior trên runtime/provider Java 11 thực tế trong CI nếu sản phẩm hỗ trợ baseline này.

## Nguồn chính thức

1. [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols: block function, stream encryption, nonce uniqueness, AEAD](https://www.rfc-editor.org/rfc/rfc8439)
2. [OpenJDK JEP 329 — ChaCha20 and Poly1305 Cryptographic Algorithms (Java 11)](https://openjdk.org/jeps/329)
3. [Java SE 11 — ChaCha20ParameterSpec: nonce 12 byte, counter int, Since 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html)
4. [Java SE 11 — Cipher: getInstance, init, update, doFinal, updateAAD](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html)
5. [Java SE 11 — KeyGenerator: sinh secret key](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/KeyGenerator.html)
6. [Java SE 11 — IvParameterSpec: nonce/IV cho ChaCha20-Poly1305](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html)
7. [Java SE 11 — AEADBadTagException: authentication tag mismatch](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/AEADBadTagException.html)
8. [Java SE 11 — SecureRandom: CSPRNG cho secret/nonce phù hợp](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/SecureRandom.html)
9. [Java SE 11 — Java Security Standard Algorithm Names: ChaCha20 và ChaCha20-Poly1305](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html)
10. [Java SE 26 — ChaCha20ParameterSpec: API vẫn được hỗ trợ trong JDK hiện đại](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html)
