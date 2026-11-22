# 10.6 Cipher.WRAP_MODE, UNWRAP_MODE và thuật toán bọc khóa

## Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích **key wrapping** là gì, phân biệt **Key Encryption Key (KEK)** và **Data Encryption Key (DEK)** trong kiến trúc mã hóa khóa.
2. Hiểu chính xác cách dùng **Cipher.WRAP_MODE**, **Cipher.UNWRAP_MODE**, **wrap(Key)** và **unwrap(byte[], String, int)** trong Java Cryptography Architecture (JCA/JCE).
3. Lựa chọn đúng thuật toán bọc khóa: **AESWrap (RFC 3394 / AES-KW)**, **AESWrapPad (RFC 5649 / AES-KWP)**, **RSA-OAEP**, hoặc cơ chế KMS/HSM theo mục tiêu và điều kiện triển khai.
4. Viết Java 17+ để bọc và mở bọc khóa AES, kiểm tra toàn vẹn wrapped key, và cấu hình tường minh OAEP khi dùng RSA.
5. Hiểu giới hạn đối với khóa không thể xuất ra ngoài, metadata cần mang theo, khả năng tương thích giữa provider, luân chuyển KEK, sai lầm phổ biến và xử lý lỗi an toàn.

**Thông điệp cốt lõi:** Bọc khóa là thao tác bảo vệ **một khóa mật mã khác** bằng khóa/phương tiện bảo vệ phù hợp; nó không phải chỉ “Base64-encode khóa”. Trong Java, hai mode WRAP/UNWRAP đặt **Cipher** vào trạng thái chuyên dùng cho đối tượng **Key**. Độ an toàn phụ thuộc vào **thuật toán bọc, khóa bọc, tham số, provider, quản lý metadata và quyền truy cập**; chỉ chọn đúng hằng số WRAP_MODE chưa làm mọi cơ chế bọc trở nên an toàn.

## 1. Bọc khóa là gì, tại sao cần?

Giả sử dịch vụ lưu hồ sơ bằng **AES-GCM**. Mỗi hồ sơ hoặc mỗi nhóm dữ liệu có một khóa AES ngẫu nhiên **DEK** để mã hóa nội dung. Nếu lưu DEK dưới dạng plaintext cạnh ciphertext, kẻ chiếm được cả hai sẽ giải mã được hồ sơ. Hệ thống cần một cách lưu hoặc chuyển **DEK ở trạng thái được bảo vệ**.

Giải pháp phổ biến là dùng **KEK** để bọc DEK:

~~~text
TẠO VÀ LƯU

Plaintext hồ sơ
      |
 [AES-GCM encrypt] <--------- DEK (Data Encryption Key)
      |                           |
Ciphertext + tag             [KEY WRAP] <------ KEK
      |                           |
      +---- lưu record ------> wrappedDEK
                             (không phải raw DEK)

ĐỌC VÀ GIẢI MÃ

wrappedDEK --------> [KEY UNWRAP] <------ KEK được cấp quyền
                           |
                          DEK
                           |
Ciphertext + tag ----> [AES-GCM decrypt + verify tag]
                           |
                   Plaintext đã xác thực
~~~

Hai tầng bảo vệ có hai vai trò riêng:

- **DEK:** mã hóa nội dung (ví dụ AES-GCM), thường sinh ngẫu nhiên và có phạm vi sử dụng hẹp.
- **KEK:** bọc/giải bọc DEK; thường nằm trong **KMS/HSM/keystore**, có chính sách truy cập và rotation riêng.

Đây là nguyên lý cốt lõi của **envelope encryption**: dùng mã hóa đối xứng hiệu quả cho dữ liệu lớn, và cơ chế bọc khóa/trao đổi khóa để bảo vệ DEK nhỏ.

**Quan trọng:** wrappedDEK vẫn là dữ liệu nhạy cảm về mặt quản trị, nhưng không tương đương raw DEK khi thiết kế an toàn. Mức an toàn không đến từ tên biến hoặc chuỗi Base64, mà từ thực chất thuật toán và quyền truy cập KEK.

### 1.1 Bọc khóa khác gì mã hóa dữ liệu thông thường?

Mã hóa dữ liệu biến **byte[] plaintext → byte[] ciphertext**. Bọc khóa nhận **Key → byte[] wrappedKey** và mở bọc nhận byte[] cùng thông tin thuật toán/loại khóa để tạo lại **Key**.

Bản chất mật mã có thể dùng primitives gần nhau, nhưng **API và mục tiêu khác**:

| Nhu cầu | Cơ chế thường dùng | Đầu vào → đầu ra |
| --- | --- | --- |
| Mã hóa hồ sơ/ảnh/file | AES-GCM | plaintext byte[] → ciphertext + tag |
| Bảo vệ một khóa AES để lưu trữ | AES-KW/AES-KWP hoặc KMS WrapKey | Key DEK + KEK → wrapped key bytes |
| Gửi một khóa AES cho người có public key RSA | RSA-OAEP | Key DEK + public key → ciphertext của khóa |
| Dẫn xuất khóa từ secret chung | HKDF/KDF theo yêu cầu | keying material → khóa có phân tách ngữ cảnh |
| Chuyển byte thành text | Base64, hex | byte[] ↔ text, **không thêm bảo mật** |

**Key wrapping không phải key derivation** và không đồng nghĩa key agreement. Bọc khóa dùng để **vận chuyển/lưu một khóa hiện có** dưới dạng được bảo vệ; ECDH/X25519 là cơ chế để các bên **thỏa thuận material chung**, còn KDF chuyển material đó thành khóa thích hợp.

## 2. Cipher trong Java: bốn chế độ và cách gọi

Class **javax.crypto.Cipher** cung cấp bốn hằng opmode quan trọng:

| Opmode | Phương thức làm việc điển hình | Mục tiêu |
| --- | --- | --- |
| **Cipher.ENCRYPT_MODE** | update(...), doFinal(...) | Mã hóa dữ liệu byte |
| **Cipher.DECRYPT_MODE** | update(...), doFinal(...) | Giải mã dữ liệu byte |
| **Cipher.WRAP_MODE** | **wrap(Key key)** | Bọc một đối tượng Key, trả byte[] |
| **Cipher.UNWRAP_MODE** | **unwrap(byte[] wrapped, String algorithm, int keyType)** | Mở bọc để tạo lại Key |

Cấu trúc điển hình:

~~~java
// Đoạn minh họa; các biến kek, dek, wrapped đã có sẵn.
Cipher wrapper = Cipher.getInstance("AESWrap");
wrapper.init(Cipher.WRAP_MODE, kek);
byte[] wrapped = wrapper.wrap(dek);

Cipher unwrapper = Cipher.getInstance("AESWrap");
unwrapper.init(Cipher.UNWRAP_MODE, kek);
Key recovered = unwrapper.unwrap(
        wrapped, "AES", Cipher.SECRET_KEY);
~~~

Đây là đoạn mã phụ thuộc các biến/nhập khẩu từ ngữ cảnh bên ngoài, **không phải chương trình độc lập**. Chương trình Java 17 có thể biên dịch/chạy được nằm ở mục 6.

### 2.1 Điều gì xảy ra với wrap(Key)?

**Cipher.wrap(Key key)** yêu cầu một đối tượng Key cần được bọc. Provider dùng thuật toán, mode, wrapping key và tham số đã cấu hình để tạo **byte[]**. Với nhiều provider phần mềm, thao tác này sử dụng **dạng encoded của Key** để bảo vệ bằng mật mã. Tuy nhiên một số HSM/provider có thể hỗ trợ bọc khóa trong phần cứng mà không bao giờ xuất khóa ở dạng plaintext cho JVM.

Không được giả định mọi Key đều có thể wrap:

- **key.getEncoded() có thể trả null** nếu khóa không cho phép xuất ra ngoài hoặc không có dạng encoding được hỗ trợ.
- **Cipher.wrap(...)** có thể ném **InvalidKeyException** khi không thể hoặc không an toàn để bọc khóa; **IllegalBlockSizeException** có thể xảy ra tùy thuật toán và độ dài encoded key.
- Provider có thể không hỗ trợ wrap/unwrap đối với thuật toán hoặc loại Key cụ thể, kể cả khi hỗ trợ encrypt/decrypt.
- Quyền sử dụng KEK có thể bị giới hạn trong HSM/KMS (chỉ wrap, chỉ unwrap, chỉ cho một loại khóa).

**WRAP_MODE không bỏ qua chính sách bảo vệ private key hoặc quy định extractability của HSM.**

### 2.2 unwrap(...) không thể chỉ nhận một mảng byte

Chữ ký phương thức:

~~~java
Key unwrap(byte[] wrappedKey,
           String wrappedKeyAlgorithm,
           int wrappedKeyType)
~~~

Hai đối số cuối có ý nghĩa:

- **wrappedKeyAlgorithm:** tên thuật toán của **khóa sau khi mở bọc**, chẳng hạn **"AES"**, **"HmacSHA256"**, hoặc **"RSA"**. Đây **không phải** tên thuật toán bọc "AESWrap" hoặc "RSA/ECB/OAEPPadding".
- **wrappedKeyType:** một trong ba hằng **Cipher.SECRET_KEY**, **Cipher.PUBLIC_KEY**, **Cipher.PRIVATE_KEY** để provider biết kiểu Key cần tái tạo.

Ví dụ đúng:

~~~java
Key dataKey = unwrapper.unwrap(
        wrappedBytes, "AES", Cipher.SECRET_KEY);
~~~

Ví dụ sai về mặt ý nghĩa API:

~~~java
// Sai: AESWrap là thuật toán BỌC, không phải thuật toán của DEK.
Key dataKey = unwrapper.unwrap(
        wrappedBytes, "AESWrap", Cipher.SECRET_KEY);
~~~

Đừng tự chọn thuật toán/loại khóa từ các chuỗi không tin cậy. **Algorithm name và key type truyền cho unwrap không tự được xác thực bởi phép bọc trong mọi định dạng.** Với nhiều provider, byte key đã mở bọc có thể được gán một nhãn thuật toán theo tham số caller; phải kiểm tra schema, key length và mục đích khóa.

### 2.3 Cipher unwrap trả về Key, không nhất thiết trả SecretKeySpec

Kết quả khai báo kiểu **java.security.Key**. Sau khi kiểm tra đúng loại, ứng dụng có thể dùng như SecretKey, PublicKey hoặc PrivateKey nếu provider trả kiểu tương ứng.

~~~java
Key recovered = unwrapper.unwrap(
        wrapped, "AES", Cipher.SECRET_KEY);
if (!(recovered instanceof javax.crypto.SecretKey)) {
    throw new IllegalStateException("Unexpected key type");
}
javax.crypto.SecretKey dek = (javax.crypto.SecretKey) recovered;
~~~

Đoạn trên là minh họa, cần biến unwrapper và wrapped có sẵn.

**Không gọi getEncoded() chỉ để sử dụng lại khóa nếu provider có thể thao tác trực tiếp bằng đối tượng Key.** Với khóa trong HSM, encoded bytes có thể không bao giờ xuất hiện. Nếu cần bảo vệ dữ liệu, tốt hơn là truyền Key cho Cipher hợp lệ và giới hạn phạm vi lộ khóa.

## 3. Các thuật toán bọc khóa quan trọng

### 3.1 AESWrap / AES-KW (RFC 3394, NIST SP 800-38F)

**AESWrap** là tên thuật toán Java cho **AES Key Wrap (AES-KW)** theo RFC 3394. Nó dùng khóa AES làm **KEK** để bảo vệ bytes của khóa khác, kèm cơ chế kiểm tra integrity theo cấu trúc thuật toán.

Ví dụ tương thích điển hình:

~~~text
KEK:      AES key 128 hoặc 256 bit
DEK:      AES key 128 bit (16 byte)
Algorithm: AESWrap
wrapped:  24 byte = 16 byte DEK + 8 byte overhead
~~~

Với **AES-KW RFC 3394**, dữ liệu đầu vào cần dài tối thiểu **16 byte** và có độ dài là bội số của **8 byte** (cho thuật toán chuẩn). Đầu ra dài hơn đầu vào **8 byte**; ví dụ 16 byte thành 24 byte, 32 byte thành 40 byte.

Cơ chế có **kiểm tra integrity** bằng giá trị kiểm tra theo RFC 3394; kẻ không biết KEK rất khó thay đổi wrapped key rồi vẫn được unwrap chấp nhận. Tuy vậy:

- AES-KW **không phải** một cơ chế AEAD có AAD tùy ý như AES-GCM.
- Nó **không ràng buộc tự động** tenant ID, key ID, thời hạn hay các trường metadata bên ngoài.
- Đừng gọi overhead 8 byte là **tag GCM 128 bit**; tính chất và định dạng khác nhau.
- Nó không tự xác thực danh tính người gửi hoặc chứng minh khóa được phép dùng cho mọi nghiệp vụ.

Oracle Java SE 17 liệt kê **AESWrap** tương ứng AES-KW RFC 3394; provider SunJCE hỗ trợ **AESWrap**. Tùy provider, có thể dùng transformation **"AESWrap"** hoặc những tên định dạng tương đương như **"AES/KW/NoPadding"** khi được hỗ trợ. Cần kiểm tra tên thuật toán và khả năng tương thích thực tế, không tự giả định các alias luôn tương đương ở mọi provider.

### 3.2 AESWrapPad / AES-KWP (RFC 5649)

**AES-KWP** mở rộng AES-KW để xử lý cả dữ liệu khóa có **độ dài không phải bội số của 8 byte** hoặc ngắn hơn phạm vi của AES-KW, bằng cấu trúc padding/integrity chuyên dụng.

Tên Java chuẩn là **AESWrapPad** theo RFC 5649 và NIST SP 800-38F. Đừng tự lấy một byte[] ngắn rồi thêm zero thủ công để “vừa AESWrap”: bên unwrap sẽ cần biết chính xác độ dài gốc và chuẩn hóa, và thêm padding tự chế có thể làm sai thuộc tính bảo mật/giao thức.

**Không thể trộn AESWrap và AESWrapPad** chỉ vì cả hai đều bắt đầu bằng chữ AES. Chúng là hai thuật toán với cấu trúc wrapped bytes khác nhau.

Java có danh mục tên chuẩn cho AESWrapPad, nhưng **việc provider cụ thể trong môi trường triển khai hỗ trợ hay không phải được kiểm tra**. Không suy từ việc provider có AESWrap mà kết luận AESWrapPad cũng hoạt động. Ví dụ chạy được bên dưới dùng AESWrap đã được tài liệu hóa cho SunJCE.

### 3.3 RSA-OAEP dùng public key để bọc secret key

Nếu bên gửi chỉ có **public key RSA** của bên nhận, có thể dùng **RSA-OAEP** để wrap một DEK AES nhỏ; người nhận dùng private key để unwrap.

~~~text
Sender                                Recipient
Public RSA key                       Private RSA key
     |                                     |
WRAP_MODE + RSA-OAEP                  UNWRAP_MODE + RSA-OAEP
     |                                     |
wrap(AES DEK)                         unwrap(bytes, "AES", SECRET_KEY)
     |                                     |
wrapped DEK ----------- gửi ----------> AES DEK
~~~

Cấu hình OAEP cần thống nhất tường minh:

- **OAEP digest** (ví dụ SHA-256).
- **MGF** (thường MGF1).
- **MGF1 digest** (ví dụ SHA-256).
- **Label bytes** (ví dụ empty label hoặc UTF-8 của "key:v1").
- RSA key pair tương ứng và ciphertext encoding.

Trong Java 17, có thể dùng:

~~~java
OAEPParameterSpec spec = new OAEPParameterSpec(
        "SHA-256",
        "MGF1",
        MGF1ParameterSpec.SHA256,
        new PSource.PSpecified(
                "key:v1".getBytes(StandardCharsets.UTF_8))
);
~~~

Đây là đoạn cấu hình minh họa, không phải chương trình độc lập. **Không suy luận MGF1 digest từ tên transformation có SHA-256**: với một số provider, các mặc định có thể khác nhau. Truyền **OAEPParameterSpec** giống nhau vào **Cipher.init** cho cả hai bên.

Với RSA-2048, kết quả wrap thường là **256 byte**; với OAEP SHA-256, plaintext tối đa **190 byte** (k - 2hLen - 2), đủ chứa khóa AES 16/32 byte nhưng không đủ để mã hóa cả file. RSA-OAEP có ngẫu nhiên hóa nên wrapped key khác nhau mỗi lần wrap cho cùng DEK.

**RSA-OAEP không tự xác thực người gửi**: ai biết public key của người nhận đều có thể tạo ciphertext mới. Nếu cần chứng minh nguồn gốc, dùng cơ chế chữ ký/xác thực giao thức độc lập.

### 3.4 AES-GCM có thể mã hóa key bytes không?

Về mặt mật mã, **AES-GCM với nonce duy nhất và AAD** có thể bảo vệ các byte bí mật nhỏ, kể cả encoded key, khi được sử dụng qua một giao thức được thiết kế đúng.

Nhưng **không suy ra mọi provider hỗ trợ Cipher.wrap khi Cipher được cấu hình ở AES/GCM/NoPadding**; khả năng wrap/unwrap là chức năng của từng CipherSpi/provider. Nếu chọn AES-GCM để bảo vệ key bytes, phải quản lý **nonce, tag, AAD**, tuân thủ điều kiện **nonce duy nhất theo KEK**, và đưa metadata vào định dạng kết quả. Với tác vụ key wrap thông thường, AES-KW/KWP hoặc dịch vụ wrap key chuyên dụng giúp tránh tự thiết kế giao thức không cần thiết.

**Không dùng AES/ECB/NoPadding, AES/CBC/PKCS5Padding hoặc XOR tùy ý để tự bọc khóa**, rồi cho rằng độ bí mật và integrity tương đương AES-KW. CBC thuần không cung cấp xác thực toàn vẹn; ECB làm lộ cấu trúc. Những thuật toán này không trở thành key wrap an toàn chỉ nhờ gọi WRAP_MODE.

## 4. So sánh thuật toán theo loại khóa và giới hạn

| Thuật toán | Khóa bọc (KEK) | Đối tượng phù hợp | Điều kiện nổi bật | Khả năng integrity |
| --- | --- | --- | --- | --- |
| **AESWrap / AES-KW** | AES đối xứng | Encoded secret key bytes phù hợp độ dài | Ít nhất 16 byte, bội số 8 | Có kiểm tra theo chuẩn AES-KW |
| **AESWrapPad / AES-KWP** | AES đối xứng | Encoded key bytes có độ dài linh hoạt | Provider phải hỗ trợ đúng chuẩn KWP | Có kiểm tra theo chuẩn AES-KWP |
| **RSA-OAEP** | Public key RSA của người nhận | DEK nhỏ; dùng private key tương ứng để unwrap | OAEP hash, MGF1 digest, label, giới hạn modulus | Có kiểm tra cấu trúc OAEP khi giải mã; không xác thực người gửi |
| **KMS/HSM WrapKey** | Key nội bộ KMS/HSM theo quyền | Key được quản lý bởi hạ tầng khóa | API/policy/key handle của hệ thống, quyền và audit | Theo thuật toán và bảo đảm của dịch vụ |
| **AES-GCM trên encoded key bytes** | AES đối xứng | Key bytes trong protocol tự thiết kế đúng | Nonce duy nhất, AAD, tag, framing | Có AEAD khi xác minh tag thành công |

**Không có “một thuật toán bọc tốt cho mọi loại khóa”.** Cần xét mô hình tin cậy, yêu cầu tương thích, khả năng export key, giới hạn kích thước và loại metadata phải được xác thực.

### 4.1 Tại sao tên AESWrap cũng không giải thích được DEK là AES?

**"AESWrap"** là tên cipher dùng để bảo vệ key bytes. DEK được bọc có thể là một loại secret key khác nếu dạng byte và thuật toán/độ dài hợp lệ với cơ chế bọc.

Sau unwrap, Java cần biết tên thuật toán và loại Key cần khôi phục:

~~~text
Wrapping algorithm: AESWrap
Wrapping key:       KEK là AES
Wrapped key type:   Cipher.SECRET_KEY
Wrapped algorithm:  "AES" hoặc "HmacSHA256" theo hợp đồng
~~~

Không được nhầm wrapping algorithm với **wrappedKeyAlgorithm** trong chữ ký unwrap.

## 5. SecretKey, PublicKey, PrivateKey và encoding

JCA có interface **java.security.Key** cùng các interface con:

- **javax.crypto.SecretKey:** khóa đối xứng; dạng mã hóa thường là **RAW** khi export được.
- **java.security.PublicKey:** khóa công khai; dạng mã hóa phổ biến **X.509 SubjectPublicKeyInfo**.
- **java.security.PrivateKey:** khóa bí mật bất đối xứng; dạng mã hóa phổ biến **PKCS#8** nếu được phép xuất.

Các constant type lúc unwrap:

~~~java
Cipher.SECRET_KEY
Cipher.PUBLIC_KEY
Cipher.PRIVATE_KEY
~~~

Đây là **hằng chỉ loại Key**, không phải thuật toán mật mã và không phải giá trị mode. Sai loại Key hoặc tên algorithm có thể làm unwrap thất bại, hoặc tạo đối tượng key không phù hợp với mục đích sử dụng sau đó.

### 5.1 getAlgorithm(), getFormat(), getEncoded()

**Key.getAlgorithm()** nói tên thuật toán (ví dụ "AES"). **Key.getFormat()** cho biết định dạng encoded key khi được hỗ trợ. **Key.getEncoded()** trả byte[] encoding hoặc có thể **null**.

Với secret key phần mềm xuất được, có thể gặp:

~~~text
key.getAlgorithm(): AES
key.getFormat():    RAW
key.getEncoded():   [16, 24 hoặc 32 byte]
~~~

Các byte này là **secret**, không phải metadata công khai. Không ghi chúng vào log, metrics, file cấu hình hoặc response. Việc chúng có thể được trả về cho test **không có nghĩa luôn nên export** trong production.

### 5.2 Khóa HSM/KMS không export được

Một HSM có thể lưu key material dưới một key handle và từ chối getEncoded(). Một Cipher phần mềm không thể tự wrap khóa mà nó không được đọc byte; ngược lại, HSM có thể có cơ chế wrap bên trong phần cứng theo policy.

JavaDoc của **Cipher.wrap(Key)** mô tả InvalidKeyException khi việc wrap không thể hoặc không an toàn, ví dụ một khóa bảo vệ bởi phần cứng được đưa cho cipher chỉ chạy bằng phần mềm.

**Không tìm cách phá rào extractability** bằng reflection, in-memory dump hay tải private key ra JVM để “chạy ví dụ”. Hãy dùng API wrap/unwrap của provider/HSM hoặc workflow KMS chính thức, với kiểm soát vai trò và key usage thích hợp.

### 5.3 Có nên wrap private key không?

Có các trường hợp **private key backup/escrow/di chuyển** được phép và cần bảo vệ rất nghiêm ngặt. Tuy nhiên private key thường được khuyến nghị **giữ non-exportable** trong HSM khi mô hình bảo mật yêu cầu.

Nếu một private key thực sự được cho phép export, format như PKCS#8, thuật toán bọc, quản lý KEK, quyền và audit phải được quy định rõ; không giả định gọi **wrap(privateKey)** sẽ thành công trên mọi provider. Đối với private key không exportable, giải pháp thích hợp thường là key handle và chức năng bảo vệ nội bộ của HSM.

## 6. Java 17+ hoàn chỉnh: AESWrap, kiểm tra dữ liệu bị sửa và RSA-OAEP

Chương trình dưới đây minh họa:

1. Sinh **KEK AES-128** và **DEK AES-128** trong cùng lần chạy bằng KeyGenerator.
2. Bọc DEK bằng **AESWrap**, mở bọc bằng cùng KEK.
3. Đổi một bit của wrapped bytes để kiểm tra **integrity** của AESWrap.
4. Sinh keypair RSA-2048, bọc chính DEK bằng public key với **RSA-OAEP SHA-256/MGF1-SHA-256/label "key:v1"**.
5. Mở bọc bằng private key và cố tình dùng label khác để chứng minh cấu hình phải thống nhất.

Đây là chương trình **độc lập**, dùng API hiện diện từ Java 17 và SunJCE/SunRsaSign trên JDK phù hợp. Demo tạo khóa ngẫu nhiên trong một tiến trình; ứng dụng thực tế dùng KEK/DEK được cấp phát và quản lý bởi hệ thống khóa phù hợp.

Tạo **KeyWrapDemo.java** (UTF-8):

~~~java
import java.security.*;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.*;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public class KeyWrapDemo {
    private static OAEPParameterSpec oaep(String label) {
        return new OAEPParameterSpec(
            "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
            new PSource.PSpecified(
                label.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey kek = generator.generateKey();
        SecretKey dek = generator.generateKey();

        Cipher aesWrap = Cipher.getInstance("AESWrap");
        aesWrap.init(Cipher.WRAP_MODE, kek);
        byte[] wrappedAes = aesWrap.wrap(dek);

        Cipher aesUnwrap = Cipher.getInstance("AESWrap");
        aesUnwrap.init(Cipher.UNWRAP_MODE, kek);
        Key restoredAes = aesUnwrap.unwrap(
            wrappedAes, "AES", Cipher.SECRET_KEY);

        System.out.println("AESWrap bytes: " + wrappedAes.length);
        System.out.println("AES key restored: "
            + Arrays.equals(dek.getEncoded(), restoredAes.getEncoded()));

        byte[] tampered = wrappedAes.clone();
        tampered[tampered.length - 1] ^= 1;
        boolean tamperRejected;
        try {
            aesUnwrap.unwrap(tampered, "AES", Cipher.SECRET_KEY);
            tamperRejected = false;
        } catch (GeneralSecurityException expected) {
            tamperRejected = true;
        }
        System.out.println("AESWrap tamper rejected: " + tamperRejected);

        KeyPairGenerator rsaGenerator = KeyPairGenerator.getInstance("RSA");
        rsaGenerator.initialize(2048);
        KeyPair recipient = rsaGenerator.generateKeyPair();

        Cipher rsaWrap = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaWrap.init(Cipher.WRAP_MODE, recipient.getPublic(), oaep("key:v1"));
        byte[] wrappedRsa = rsaWrap.wrap(dek);

        Cipher rsaUnwrap = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaUnwrap.init(Cipher.UNWRAP_MODE, recipient.getPrivate(),
            oaep("key:v1"));
        Key restoredRsa = rsaUnwrap.unwrap(
            wrappedRsa, "AES", Cipher.SECRET_KEY);

        System.out.println("RSA-OAEP wrapped bytes: " + wrappedRsa.length);
        System.out.println("RSA-OAEP restored: "
            + Arrays.equals(dek.getEncoded(), restoredRsa.getEncoded()));

        Cipher wrongLabel = Cipher.getInstance("RSA/ECB/OAEPPadding");
        wrongLabel.init(Cipher.UNWRAP_MODE, recipient.getPrivate(),
            oaep("key:v2"));
        boolean wrongLabelRejected;
        try {
            wrongLabel.unwrap(wrappedRsa, "AES", Cipher.SECRET_KEY);
            wrongLabelRejected = false;
        } catch (GeneralSecurityException expected) {
            wrongLabelRejected = true;
        }
        System.out.println("RSA-OAEP wrong label rejected: "
            + wrongLabelRejected);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 KeyWrapDemo.java
java KeyWrapDemo
~~~

Stdout mong đợi trong JDK có hỗ trợ các transformation nêu trên:

~~~text
AESWrap bytes: 24
AES key restored: true
AESWrap tamper rejected: true
RSA-OAEP wrapped bytes: 256
RSA-OAEP restored: true
RSA-OAEP wrong label rejected: true
~~~

**Cơ sở của các con số:**

- AES DEK 128 bit = **16 byte**. Với AES-KW RFC 3394, wrapped key dài **24 byte**, tức 16 + 8.
- RSA modulus 2048 bit = **256 byte**. Wrapped RSA-OAEP dài **256 byte**.
- Hai phép so sánh restored dùng **getEncoded() chỉ trong demo** cho khóa AES phần mềm do KeyGenerator sinh. Trong production, có thể phải thao tác trực tiếp với Key object mà không export raw bytes.
- Đổi byte wrapped AES-KW làm integrity check thất bại với xác suất áp đảo; demo nhận ra thông qua exception.
- OAEP SHA-256/MGF1-SHA-256 đúng nhưng **label "key:v2"** thay vì **"key:v1"** khiến unwrap không thành công.

Vì khóa AES và keypair RSA được tạo ngẫu nhiên mỗi lần chạy, raw wrapped bytes sẽ khác nhau. Ví dụ chỉ in **độ dài và điều kiện đúng/sai**, không in raw key, private key, ciphertext hay tag.

**Giới hạn của ví dụ:** Đây là kiểm thử chức năng local, không có KMS, không có giao thức truyền hay quyền truy cập thực; việc bắt GeneralSecurityException nhằm minh họa đường từ chối khi unwrap lỗi, không nên dùng exception message để trả thông tin mật mã ra client.

### 6.1 Vì sao bắt GeneralSecurityException trong demo?

**Cipher.wrap(...)** có thể ném InvalidKeyException hoặc IllegalBlockSizeException; **Cipher.unwrap(...)** thường báo InvalidKeyException hoặc NoSuchAlgorithmException theo JavaDoc. Việc unwrap sai không nhất thiết có cùng loại exception trên mọi provider và thuật toán.

Dùng **GeneralSecurityException** ở ranh giới minh họa cho phép bắt các lỗi mật mã đã được khai báo, rồi xem việc unwrap không thành công là một trạng thái từ chối. Trên dịch vụ thật, có thể phân loại nội bộ theo nguyên nhân hợp lệ (khóa không có quyền, định dạng sai, thuật toán không hỗ trợ, integrity check thất bại), nhưng **trả lỗi tổng quát** cho đối tượng không tin cậy và tránh tạo một oracle tiết lộ quá nhiều thông tin.

Lưu ý **UnsupportedOperationException** là runtime exception nếu provider không triển khai chức năng wrap/unwrap. Đây là vấn đề hỗ trợ API/cấu hình triển khai, không phải tín hiệu cho phép fallback sang mã hóa không an toàn.

### 6.2 Việc cùng key bytes được khôi phục chứng minh gì?

Trong demo, **AES key restored: true** cho thấy byte[] encoded key khớp với DEK ban đầu. Đây là một **round-trip test**, chưa chứng minh:

- KEK đang được bảo vệ trong môi trường thực;
- wrapped blob thuộc đúng tenant/record;
- người gửi có quyền tạo wrapped key;
- wrapped key chưa bị replay hoặc tráo giữa tài nguyên;
- dữ liệu mã hóa dưới DEK đã vượt kiểm tra tag AEAD.

Để chứng minh hệ thống đúng, cần cả **key recovery test** lẫn **policy, metadata binding, key lifecycle và data encryption test**.

## 7. Bọc khóa, metadata và thiết kế envelope encryption

### 7.1 Định dạng record phải rõ ràng

Một record mã hóa ứng dụng thường cần nhiều hơn wrapped bytes. Ví dụ một định dạng do ứng dụng tự thiết kế:

~~~text
envelopeVersion:   1
tenantId:          tenant-A
recordId:          report-2026-07
wrappingAlg:       AESWrap
kekId:             kms-key/finance-v3
wrappedDek:        Base64( AES-KW(KEK, DEK) )
dataAlg:           AES/GCM/NoPadding
nonce:             Base64(12-byte nonce)
dataCiphertext:    Base64(ciphertext || GCM tag)
keyPurpose:        record-encryption
~~~

Đây là **ví dụ cấu trúc**, không phải giao thức tiêu chuẩn đã được xác thực. Mỗi trường có vai trò:

- **envelopeVersion:** chọn schema và các thuật toán được chính sách cho phép.
- **tenantId/recordId/keyPurpose:** ràng buộc quyền, chủ sở hữu dữ liệu, loại khóa.
- **wrappingAlg:** xác định cách unwrap wrappedDEK.
- **kekId:** tham chiếu KEK trong KMS/HSM; không chứa raw KEK.
- **wrappedDek:** binary wrapped key được biểu diễn Base64 cho JSON/text, không có quyền năng bảo mật nhờ Base64.
- **dataAlg/nonce/dataCiphertext:** mô tả dữ liệu được mã hóa bởi DEK.

**AES-KW không có AAD**, nên những metadata như tenantId, recordId, keyPurpose **không tự được kiểm tra bằng AESWrap**. Cần ràng buộc metadata vào giao thức có xác thực (ví dụ AES-GCM AAD cho dữ liệu và metadata tương ứng, hoặc record được ký/MAC theo mô hình tin cậy), kiểm tra authorization và gắn wrappedDEK với đúng ngữ cảnh. Không nhận metadata do client tùy ý thay đổi rồi chỉ kiểm tra “unwrap thành công”.

### 7.2 Luồng đọc dữ liệu được bảo vệ

Quy trình hợp lý:

1. **Xác thực request** và kiểm tra người gọi có quyền đọc record cụ thể.
2. Parse và kiểm tra **envelopeVersion, thuật toán cho phép, kích thước, key ID**, các trường metadata và mối quan hệ tenant/record.
3. Tra cứu KEK theo key ID trong **KMS/HSM** theo quyền, không cấp KEK cho mọi client.
4. **Unwrap DEK** bằng thuật toán và tham số chính xác. Nếu integrity check thất bại, từ chối.
5. Kiểm tra loại Key, algorithm, độ dài DEK và **key usage**; không tin nhãn algorithm từ payload một cách mù quáng.
6. Dùng DEK giải mã dữ liệu theo **AES-GCM**, cung cấp đúng nonce/AAD, xác thực tag; không sử dụng plaintext nếu xác thực thất bại.
7. Chỉ sau các bước kiểm tra mới đưa plaintext cho phần nghiệp vụ được cấp quyền.
8. Ghi audit tối thiểu (key ID, record ID, outcome, request ID), không log raw KEK/DEK hoặc plaintext.

Unwrap thành công **không bảo đảm payload dataCiphertext hợp lệ**: còn cần giải mã và xác thực dữ liệu. Ngược lại, payload GCM hợp lệ trong một ngữ cảnh cũng **không cấp thêm quyền truy cập** cho người gọi khác.

### 7.3 Khi dùng RSA-OAEP thay AESWrap trong envelope

Với RSA-OAEP:

~~~text
wrappingAlg:       RSA-OAEP
rsaRecipientKeyId: recipient-key-2026
oaepDigest:        SHA-256
mgf:               MGF1
mgfDigest:         SHA-256
oaepLabel:         Base64(UTF8("key:v1"))
wrappedDek:        Base64(RSAES-OAEP(publicKey, DEK))
~~~

Người nhận chọn **private key có quyền** và cùng bộ tham số. Không để các field chưa được xác thực buộc server tự hạ cấp thuật toán hoặc thử key không thuộc tenant. Nếu các field có thể bị sửa, ứng dụng phải kiểm tra/chặn ở tầng policy hoặc ràng buộc chúng vào cơ chế xác thực của record/giao thức.

**RSA-OAEP không chứng minh nguồn gốc của key**: người giữ public key có thể tự tạo wrapped key. Muốn biết ai gửi, cần chữ ký số hoặc xác thực kết nối và chính sách phân quyền phù hợp.

## 8. Vòng đời KEK và DEK: rotation, rewrap và quyền truy cập

### 8.1 Đổi KEK không nhất thiết phải mã hóa lại file lớn

Nếu DEK vẫn còn hợp lệ và không bị lộ, có thể luân chuyển **KEK** theo cách:

~~~text
wrappedDEK_old --[UNWRAP với KEK_old]--> DEK
DEK            --[WRAP với KEK_new]----> wrappedDEK_new
~~~

Các thao tác này phải được bảo vệ bởi KMS/HSM hoặc môi trường tin cậy, hạn chế thời gian DEK xuất hiện trong bộ nhớ. Cập nhật **wrappedDEK + kekId/version** nhất quán và đảm bảo kế hoạch phục hồi nếu quá trình rotation bị ngắt.

**Rewrap không tạo DEK mới** và không mã hóa lại dataCiphertext. Nó chỉ thay cách bảo vệ cùng DEK. Nếu chính DEK bị lộ, chỉ đổi KEK không làm ciphertext đã mã hóa dưới DEK trở nên bí mật trở lại: cần đánh giá cấp DEK mới, mã hóa lại dữ liệu, thu hồi quyền và phạm vi ảnh hưởng.

### 8.2 Quyền “wrap” và “unwrap” nên tách

Một hệ thống có thể cấp cho dịch vụ ghi quyền tạo wrapped DEK, còn dịch vụ đọc có quyền mở bọc để giải mã. Không phải tiến trình nào cần lưu ciphertext cũng phải được cấp quyền unwrap mọi record.

KMS/HSM thường cung cấp:

- Key ID/alias và version.
- Tách quyền encrypt/wrap/decrypt/unwrap theo vai trò và chính sách.
- Audit các thao tác sử dụng key.
- Rotation, disable, revoke và backup/restore phù hợp.
- Khả năng giữ root/KEK không rời phần cứng.

**Đừng nhầm “ứng dụng được quyền wrap” với “được quyền unwrap”.** Việc cấp quyền dư thừa làm tăng tác động khi một service bị xâm nhập.

### 8.3 Chính sách hết hạn và phục hồi

Không xóa KEK cũ trước khi các wrapped DEK phụ thuộc vào nó đã được rewrap hoặc không còn cần giải mã, trừ khi có lý do thu hồi bảo mật mạnh hơn. Cần lưu key version, trạng thái rotation, dữ liệu đã migrate và chính sách phục hồi.

Đồng thời, đừng giữ KEK cũ hoạt động vô hạn để tương thích nếu khóa có thể đã lộ. Kế hoạch chuyển đổi phải cân bằng khả năng phục hồi với yêu cầu thu hồi và bảo mật.

## 9. Đúng thuật toán nhưng vẫn có thể sai an toàn

### 9.1 Sai lầm: lưu KEK cạnh wrapped DEK

Nếu DB có wrappedDEK và cùng hệ thống cấp cho tiến trình bất kỳ quyền lấy KEK plaintext, giá trị bảo vệ giảm mạnh. **Tách miền quyền** giữa storage và key service là phần quan trọng của envelope encryption.

Có thể đặt KMS key ID cùng record; **key ID thường không phải secret**. Nhưng raw KEK không nên được lưu/ghi log trong cùng mức quyền truy cập với dữ liệu nó bảo vệ.

### 9.2 Sai lầm: dùng cùng KEK cho mọi tenant và mục đích

Một KEK chung làm phạm vi ảnh hưởng khi compromise rộng hơn. Thiết kế theo **tenant/ứng dụng/mục đích** khi phù hợp, kết hợp policy ngăn một client unwrap DEK của client khác. Việc tách KEK còn giúp rotation độc lập và audit rõ ràng.

**Thay khóa cho từng tenant không tự thay thế authorization**; vẫn phải kiểm tra user có quyền trên record hay không.

### 9.3 Sai lầm: không kiểm tra “khóa trả về có dùng đúng mục đích?”

**Cipher.unwrap(..., "AES", SECRET_KEY)** giúp provider dựng Key có algorithm "AES" nhưng không phải một cơ chế chứng thực mục đích sử dụng từ phía người tạo record. Nếu dữ liệu có thể đưa vào dưới ngữ cảnh khác, cần key ID/version, key type, độ dài, tenant, purpose và chính sách rõ ràng.

Ví dụ DEK AES-128 được phép mã hóa hồ sơ nội bộ không có nghĩa service có quyền dùng nó để mã hóa payload thuộc tenant khác.

### 9.4 Sai lầm: xem integrity của wrapped key như integrity của mọi thứ

AES-KW kiểm tra integrity **wrapped key bytes** theo lược đồ. Nó không biết username, nội dung file, quyền truy cập, bản ghi gốc hay timestamp nếu các thông tin đó không được bảo vệ bằng cơ chế khác.

Hãy phân biệt ba lớp:

1. **Key wrapping integrity:** wrappedDEK có thể được mở bọc hợp lệ theo KEK.
2. **Payload integrity:** ciphertext dữ liệu được xác thực bằng AES-GCM tag/MAC phù hợp.
3. **Authorization/business integrity:** đúng tenant, đúng người, đúng thao tác và không bị replay/tráo record.

Cần cả ba khi hệ thống có yêu cầu tương ứng.

### 9.5 Sai lầm: tự fallback sang thuật toán yếu hơn

Nếu unwrap bằng AESWrap thất bại, không nên thử các transformation tùy ý như AES/ECB/NoPadding hay RSA/ECB/PKCS1Padding với hy vọng ra một Key “đọc được”. Với giao thức có version, server chỉ chấp nhận **thuật toán và tham số được phép cho version đó**, từ chối trường hợp không phù hợp.

### 9.6 Sai lầm: wrap là thay thế cho xác thực người gửi

Một public RSA key được công khai. RSA-OAEP cho phép gửi wrapped key bí mật tới private-key holder, nhưng **bất kỳ ai có public key** cũng có thể tạo wrappedDEK. Nếu bên nhận cần tin “đúng Alice tạo key này”, phải có chữ ký số, MAC với khóa chung phù hợp, mTLS hoặc xác thực giao thức độc lập.

## 10. Những lỗi và exception cần xử lý

| Lỗi/tình huống | Biểu hiện thường gặp | Cách xử lý |
| --- | --- | --- |
| Cipher chưa init WRAP_MODE, gọi wrap | IllegalStateException | Sửa trạng thái Cipher, không tiếp tục |
| Provider không hỗ trợ wrap | UnsupportedOperationException hoặc không lấy được transformation | Kiểm tra khả năng/provider, không fallback yếu |
| Key không thể export hoặc không tương thích | InvalidKeyException khi wrap | Dùng provider/HSM phù hợp, không phá extractability |
| Dữ liệu key bytes không thỏa giới hạn AES-KW | Lỗi wrap hoặc khi init theo provider | Chọn KWP/hệ thống phù hợp khi đã được hỗ trợ |
| Wrapped bytes sai/bị sửa, KEK sai | Unwrap thất bại (thường InvalidKeyException) | Từ chối, không sử dụng key nào |
| Sai RSA private key/OAEP digest/MGF1 digest/label | Unwrap không hợp lệ | Từ chối, kiểm tra cấu hình và key ID đã thỏa thuận |
| wrappedKeyAlgorithm không được hỗ trợ | NoSuchAlgorithmException hoặc lỗi provider | Kiểm tra whitelist algorithm, không tin text tùy ý |
| Sai wrappedKeyType | Lỗi dựng Key hoặc dựng kiểu khác không dùng được | Đối chiếu schema, không thử mọi loại tự động |
| Key ID/version không tồn tại | Lỗi policy/KMS | Từ chối có kiểm soát; audit metadata tối thiểu |
| Mở bọc được nhưng GCM tag của dữ liệu sai | AEADBadTagException lúc giải mã payload | Không công bố plaintext; điều tra theo chính sách |

**Không lấy thông điệp exception của provider làm API công khai.** Những lỗi phân biệt sâu về padding, key length, key validity có thể tạo oracle hữu ích cho đối thủ. Tạo mã lỗi tổng quát phía client và log nội bộ đã kiểm soát; tránh log raw key hoặc payload bí mật.

Trên hệ thống đa luồng, **Cipher có trạng thái và không nên dùng chung đồng thời giữa các request**. Khởi tạo riêng theo operation hoặc có cơ chế quản lý instance không dùng chung trạng thái. Không giữ Cipher đã init WRAP_MODE rồi gọi unwrap; phải init UNWRAP_MODE với đúng key và parameters.

## 11. Checklist triển khai an toàn

Trước khi đưa chức năng key wrapping vào sản xuất, kiểm tra:

- [ ] Xác định rõ **KEK/DEK**, thuật toán và mục đích của từng khóa.
- [ ] Sinh khóa bằng **SecureRandom/KeyGenerator** hoặc KMS/HSM an toàn, không dùng password plaintext làm KEK trực tiếp.
- [ ] Chọn **AESWrap**, **AESWrapPad**, **RSA-OAEP** hoặc dịch vụ KMS/HSM theo đặc tả; không tự chế key wrapping.
- [ ] Kiểm tra **provider thực tế** có hỗ trợ transformation/mode/loại Key định dùng.
- [ ] Với AES-KW, kiểm tra encoded key bytes có kích thước hợp lệ; với KWP, kiểm tra đúng chuẩn/provider.
- [ ] Với RSA-OAEP, cấu hình **OAEP hash, MGF1 digest, label** tường minh và thống nhất hai bên.
- [ ] Với HSM, tuân thủ tính **non-exportable**, quyền wrap/unwrap và key handle.
- [ ] Ghi rõ **algorithm/key type/key ID/version/encoding** trong giao thức và kiểm tra whitelist.
- [ ] Không log raw KEK, DEK, private key, plaintext hoặc các buffer bí mật.
- [ ] Không xem Base64/hex là lớp bảo vệ mật mã.
- [ ] Metadata và quyền truy cập phải được **kiểm tra/ràng buộc với ngữ cảnh**; chống tráo wrapped key giữa tenant/record.
- [ ] Chỉ dùng DEK để giải mã dữ liệu sau khi unwrap hợp lệ, xác thực payload AEAD thành công và authorization được xác nhận.
- [ ] Có kế hoạch **KEK rotation / DEK rotation / backup / recovery / revocation**.
- [ ] Test corrupted wrapped bytes, sai KEK, sai key type, sai thuật toán/label, provider không hỗ trợ và lỗi KMS.
- [ ] Giám sát lỗi, giới hạn request, tách quyền và không xây logic fallback hạ cấp thuật toán.

### 11.1 Test matrix tối thiểu

| Test | Kết quả mong đợi |
| --- | --- |
| AESWrap: KEK đúng, DEK AES-128 16 byte | wrap → unwrap khôi phục đúng Key |
| AESWrap: lật một bit trong wrapped bytes | Integrity check thất bại |
| AESWrap: đổi sang KEK khác | Không mở bọc thành công |
| AESWrap: đầu vào key encoding có độ dài không hợp lệ | Reject hoặc dùng KWP đúng chuẩn nếu chính sách cho phép |
| AESWrapPad: provider không hỗ trợ | Phát hiện ở khâu capability, không tự fallback |
| RSA-OAEP: đúng private key/hash/MGF1/label | Mở bọc DEK thành công |
| RSA-OAEP: sai private key hoặc label | Mở bọc thất bại |
| Gửi raw wrapped bytes qua Base64 rồi decode | Giữ nguyên byte, không tăng bảo mật |
| Nhầm wrappedKeyAlgorithm với wrapping algorithm | Phát hiện mismatch qua schema/key validation |
| Non-exportable key đưa cho software-only provider | Reject; dùng hardware wrapping nếu được phép |
| Tráo wrappedDEK từ tenant khác | Reject qua authorization/context binding |
| Unwrap thành công nhưng payload GCM tag sai | Từ chối plaintext |
| KEK rotation | DEK được rewrap, dữ liệu cũ giải mã được theo chính sách mới |

**Đừng chỉ đo “unwrap trả Key”.** Một bộ test an toàn phải kiểm chứng cả loại Key, độ dài, quyền, metadata và xử lý lỗi.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** WRAP_MODE khác ENCRYPT_MODE như thế nào?

**Trả lời:** WRAP_MODE dành cho **Cipher.wrap(Key)** để bảo vệ đối tượng Key và trả byte[]; ENCRYPT_MODE dành cho mã hóa byte dữ liệu qua doFinal/update. Chọn WRAP_MODE không tự bảo đảm thuật toán an toàn.

**Câu 2.** UNWRAP_MODE cần những thông tin nào?

**Trả lời:** Cipher phải được init với key/params đúng; unwrap nhận wrapped bytes, **tên thuật toán của khóa được khôi phục** và **loại Key (SECRET_KEY/PUBLIC_KEY/PRIVATE_KEY)**.

**Câu 3.** Wrapped DEK có phải dữ liệu gốc đã mã hóa không?

**Trả lời:** Không. Nó là **bản bảo vệ khóa DEK**, khác với ciphertext của bản ghi/hồ sơ được mã hóa bằng DEK.

**Câu 4.** Vì sao bọc AES-128 bằng AESWrap thường tạo 24 byte?

**Trả lời:** AES-128 key có 16 byte; AES-KW RFC 3394 thêm overhead 8 byte khi bọc.

**Câu 5.** Khi nào dùng AESWrapPad?

**Trả lời:** Khi cần bọc key bytes không đáp ứng điều kiện độ dài AES-KW, **với điều kiện provider hỗ trợ AES-KWP và giao thức thống nhất đúng thuật toán**.

**Câu 6.** Key.getEncoded() trả null có phải lỗi phải sửa bằng cách xuất secret cưỡng bức không?

**Trả lời:** Không. Nó có thể là thuộc tính bảo vệ của HSM/provider. Cần sử dụng API wrap/unwrap ở phần cứng hoặc KMS được phép.

**Câu 7.** RSA-OAEP dùng khóa gì để wrap và unwrap?

**Trả lời:** Wrap bằng **public key** người nhận; unwrap bằng **private key** tương ứng, cùng OAEP digest/MGF1 digest/label.

**Câu 8.** Bản mã RSA-OAEP bọc DEK AES có chứng minh Alice đã gửi DEK không?

**Trả lời:** Không. Public key có thể được biết bởi nhiều người; cần xác thực nguồn gốc riêng.

**Câu 9.** Nếu mở bọc DEK thành công, có thể bỏ qua tag AES-GCM của dữ liệu không?

**Trả lời:** Không. Unwrap bảo vệ DEK, còn integrity của payload phải được xác thực ở tầng mã hóa dữ liệu.

**Câu 10.** Vì sao AESWrap không tự bảo vệ tenantId trong JSON envelope?

**Trả lời:** AES-KW không có AAD tùy ý. Cần xác thực metadata ở lớp giao thức/record và kiểm tra quyền.

**Câu 11.** Rewrap DEK khi đổi KEK có cần mã hóa lại cả file dữ liệu không?

**Trả lời:** Không nhất thiết, nếu DEK vẫn an toàn và thiết kế cho phép; mở bọc bằng KEK cũ rồi bọc lại bằng KEK mới. Nếu **DEK bị lộ**, có thể phải cấp DEK mới và mã hóa lại dữ liệu.

**Câu 12.** Nếu AESWrap unwrap báo lỗi, có nên thử AES/ECB/NoPadding để được Key không?

**Trả lời:** Không. Phải từ chối và chẩn đoán theo version/thuật toán được phép, không downgrade.

## 13. Tài liệu chuẩn để tra cứu

- [Oracle Java SE 17 — javax.crypto.Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): WRAP_MODE, UNWRAP_MODE, wrap(Key), unwrap(...), exception và vòng đời Cipher.
- [Oracle Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): AESWrap, AESWrapPad, RSA và tên transformation.
- [Oracle Java SE 17 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): những transformation được provider cụ thể hỗ trợ.
- [RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm](https://www.rfc-editor.org/rfc/rfc3394): thuật toán AES-KW, cấu trúc, độ dài và kiểm tra integrity.
- [RFC 5649 — Advanced Encryption Standard (AES) Key Wrap with Padding](https://www.rfc-editor.org/rfc/rfc5649): AES-KWP, mở rộng điều kiện độ dài.
- [NIST SP 800-38F — Methods for Key Wrapping](https://csrc.nist.gov/pubs/sp/800/38/f/final): khuyến nghị phương thức bảo vệ khóa.
- [RFC 8017 — RSAES-OAEP](https://www.rfc-editor.org/rfc/rfc8017.html#section-7.1): giới hạn và cấu trúc RSA-OAEP.

## Kết luận

**Cipher.WRAP_MODE và Cipher.UNWRAP_MODE là hai chế độ API xử lý đối tượng Key, không phải thuật toán bảo mật tự thân.** Để lưu trữ hoặc chuyển DEK, hãy chọn cơ chế bọc được thiết kế cho khóa (AES-KW/KWP, RSA-OAEP hoặc KMS/HSM), quản lý KEK và tham số chặt chẽ, kiểm tra loại/độ dài khóa, bảo vệ metadata và phân quyền. **wrap(Key)** tạo wrapped bytes; **unwrap(..., wrappedKeyAlgorithm, wrappedKeyType)** tái tạo Key khi điều kiện mật mã và provider cho phép. Chỉ coi dữ liệu ứng dụng là hợp lệ khi cả **key protection**, **payload authentication** và **authorization** đã đạt yêu cầu.
