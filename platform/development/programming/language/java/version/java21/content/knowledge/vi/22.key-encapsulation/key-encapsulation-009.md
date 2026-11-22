# Chọn thuật toán, độ dài khóa và xử lý đầu vào không hợp lệ

Java 21 đưa `javax.crypto.KEM` vào Java Cryptography Architecture (JCA), cung cấp API thống nhất cho hai thao tác: đóng gói một shared secret ở phía gửi (*encapsulation*) và khôi phục shared secret ở phía nhận (*decapsulation*). API này giúp hai bên thiết lập bí mật chung qua kênh công khai; bản thân KEM không mã hóa dữ liệu ứng dụng.

Khi chọn KEM, cần xác định thuật toán mà cả hai phía hỗ trợ, loại khóa và tham số của thuật toán, kích thước encapsulation message, kích thước shared secret, cùng cách xử lý dữ liệu đầu vào sai định dạng. Với Java 21, provider SunJCE tích hợp cung cấp `DHKEM`. Các chuẩn hậu lượng tử ML-KEM được chuẩn hóa sau khi Java 21 phát hành và có hỗ trợ trong các JDK/provider mới hơn; cần phân biệt rõ khả năng của runtime đang chạy.

## 1. KEM làm gì và không làm gì?

Một KEM gồm ba bước logic:

1. Bên nhận tạo một cặp khóa KEM và công bố public key.
2. Bên gửi dùng public key đó để tạo một shared secret cùng một thông điệp encapsulation; gửi thông điệp này cho bên nhận.
3. Bên nhận dùng private key và thông điệp encapsulation để khôi phục cùng shared secret.

```text
Bên nhận                                  Bên gửi
   |                                         |
   |-- Công bố public key ----------------->|
   |                                         |
   |                              Encapsulate(public key)
   |                              -> shared secret S
   |                              -> encapsulation E
   |<------------- gửi E -------------------|
   |                                         |
Decapsulate(private key, E)                  |
   -> shared secret S                        |
   |                                         |
   +------------ Hai bên có cùng S ----------+
```

Shared secret thường được đưa qua một key derivation function (KDF) để tạo khóa mã hóa, khóa xác thực hoặc các khóa phiên khác. Dữ liệu ứng dụng sau đó được bảo vệ bằng một thuật toán đối xứng có xác thực (AEAD), chẳng hạn AES-GCM hoặc ChaCha20-Poly1305.

KEM không tự cung cấp:

- Mã hóa và giải mã payload tùy ý.
- Xác thực danh tính chủ sở hữu public key.
- Chống sửa đổi cho dữ liệu ứng dụng.
- Quản lý phiên, nonce, replay hoặc thứ tự thông điệp của giao thức.

Nếu cần một giao thức mã hóa hoàn chỉnh, nên dùng một triển khai HPKE theo RFC 9180 hoặc giao thức đã được đánh giá, thay vì tự ghép KEM, KDF và AEAD theo một định dạng riêng.

## 2. API KEM có trong Java 21

`KEM` là lớp trong package `javax.crypto`, có từ Java 21. Những thành phần thường dùng:

| API | Vai trò |
|---|---|
| `KEM.getInstance(algorithm)` | Lấy implementation của thuật toán KEM từ provider khả dụng |
| `newEncapsulator(publicKey)` | Tạo đối tượng encapsulator ở phía gửi |
| `Encapsulator.encapsulate()` | Tạo shared secret và encapsulation message |
| `KEM.Encapsulated.key()` | Lấy shared secret dưới dạng `SecretKey` |
| `KEM.Encapsulated.encapsulation()` | Lấy byte array cần gửi cho bên nhận |
| `newDecapsulator(privateKey)` | Tạo đối tượng decapsulator ở phía nhận |
| `Decapsulator.decapsulate(encapsulation)` | Khôi phục shared secret |
| `secretSize()` | Lấy số byte của shared secret |
| `encapsulationSize()` | Lấy số byte của encapsulation message |
| `providerName()` | Xem provider thực tế được chọn cho encapsulator/decapsulator |

API cũng có overload cho phép truyền `SecureRandom`, `AlgorithmParameterSpec` hoặc yêu cầu một phần byte của shared secret với tên thuật toán khóa. Không phải provider nào cũng hỗ trợ mọi tổ hợp tham số; chỉ dùng các tổ hợp được provider và giao thức đích công bố hỗ trợ.

## 3. Chọn thuật toán trong Java 21

Tên thuật toán chuẩn được JDK 21 công bố cho `KEM` là `DHKEM`, tức DH-Based KEM theo RFC 9180. Trong Oracle JDK 21, provider SunJCE triển khai `DHKEM` và chấp nhận các loại khóa sau:

- EC trên các đường cong `secp256r1`, `secp384r1`, `secp521r1`.
- XDH trên Curve25519 (`X25519`) và Curve448 (`X448`).

Tên `DHKEM` là tên dịch vụ KEM. Đường cong của public/private key xác định nhóm Diffie-Hellman cụ thể được dùng. Vì vậy, hai phía phải thống nhất cùng thuật toán, cùng nhóm/đường cong và cùng định dạng encapsulation.

### Chọn nhóm khóa

| Nhóm khóa | Shared secret (`Nsecret`) | Encapsulation (`Nenc`) | Ghi chú |
|---|---:|---:|---|
| `secp256r1` / P-256 | 32 byte | 65 byte | Phù hợp khi hệ thống đã dùng EC P-256 |
| `secp384r1` / P-384 | 48 byte | 97 byte | Lựa chọn EC với mức bảo vệ cao hơn P-256 |
| `secp521r1` / P-521 | 64 byte | 133 byte | Kích thước thông điệp lớn hơn; cần xác nhận khả năng tương thích |
| `X25519` | 32 byte | 32 byte | Lựa chọn gọn, được RFC 9180 định nghĩa |
| `X448` | 64 byte | 56 byte | Nhóm XDH với kích thước và chi phí lớn hơn X25519 |

Các kích thước trong bảng là kích thước shared secret và encapsulation message theo bộ DHKEM tương ứng trong RFC 9180. Chúng không phải số bit bảo mật, cũng không phải kích thước khóa AES. Ví dụ, shared secret 64 byte không có nghĩa thuật toán có mức bảo mật 512 bit.

Với một ứng dụng mới trên Java 21, `X25519` thường là lựa chọn thực tế nếu các bên đều hỗ trợ và giao thức cho phép. Nếu cần tương thích với hạ tầng EC sẵn có, chọn P-256 hoặc P-384 theo chính sách mật mã của tổ chức. Không chọn nhóm chỉ dựa trên độ dài byte; cần xem xét mức bảo mật, interoperability, yêu cầu chứng nhận, hiệu năng và định dạng khóa của hai đầu.

### Kiểm tra provider trước khi triển khai

JCA cho phép nhiều provider cung cấp cùng một dịch vụ. Nên yêu cầu thuật toán bằng tên chuẩn và để JCA chọn provider phù hợp, trừ khi chính sách triển khai bắt buộc một provider cụ thể:

```java
KEM kem = KEM.getInstance("DHKEM");
KEM.Encapsulator encapsulator = kem.newEncapsulator(recipientPublicKey);

System.out.println("KEM: " + kem.getAlgorithm());
System.out.println("Provider: " + encapsulator.providerName());
System.out.println("Secret bytes: " + encapsulator.secretSize());
System.out.println("Encapsulation bytes: " + encapsulator.encapsulationSize());
```

`KEM.getInstance("DHKEM")` chỉ thành công nếu có provider hỗ trợ thuật toán. `newEncapsulator` còn kiểm tra public key có hợp lệ và được implementation chấp nhận hay không. Không nên chỉ kiểm tra tên thuật toán ở compile time; hãy xác minh trên đúng JDK, provider và loại khóa của môi trường triển khai.

## 4. Độ dài shared secret và khóa đối xứng

Kích thước shared secret do KEM và bộ tham số quy định. Không tự ý giả định mọi KEM đều trả về 32 byte. Có thể truy vấn trước khi encapsulate:

```java
KEM kem = KEM.getInstance("DHKEM");
KEM.Encapsulator encapsulator = kem.newEncapsulator(recipientPublicKey);

int sharedSecretLength = encapsulator.secretSize();
int messageLength = encapsulator.encapsulationSize();
```

Shared secret không nên được sử dụng trực tiếp như một khóa tùy ý cho mọi thuật toán. Hãy dùng KDF đã được giao thức quy định để dẫn xuất khóa đúng độ dài và đúng mục đích:

| Khóa đối xứng cần tạo | Độ dài khóa |
|---|---:|
| AES-128 | 16 byte |
| AES-256 | 32 byte |
| ChaCha20 | 32 byte |

KDF còn cung cấp domain separation và context binding: cùng một shared secret có thể được dẫn xuất thành các khóa riêng cho mã hóa, xác thực hoặc hai chiều truyền dữ liệu mà không dùng lại cùng byte khóa một cách tùy tiện. Context cần được xác định bởi giao thức, ví dụ định danh phiên, vai trò hai bên và suite đã thương lượng.

Java 21 `KEM` API trả về shared secret dưới dạng `SecretKey` và tài liệu API khuyến nghị dùng nó làm input keying material cho KDF. Nếu cần HPKE, hãy dùng implementation tuân thủ RFC 9180. Không tự viết HKDF hoặc định dạng key schedule trong ứng dụng sản xuất nếu chưa có đánh giá mật mã chuyên môn.

## 5. Ví dụ encapsulation và decapsulation với X25519

Ví dụ sau minh họa một vòng trao đổi shared secret bằng `DHKEM` trên X25519. Bên nhận tạo key pair; bên gửi chỉ cần public key; bên nhận dùng private key để decapsulate.

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class DhkemExample {
    public static void main(String[] args) throws Exception {
        // Bên nhận tạo key pair và công bố public key qua kênh đã xác thực.
        KeyPairGenerator keyPairGenerator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = keyPairGenerator.generateKeyPair();

        // Bên gửi encapsulate bằng public key của bên nhận.
        KEM kem = KEM.getInstance("DHKEM");
        KEM.Encapsulator encapsulator =
                kem.newEncapsulator(recipientKeys.getPublic());

        KEM.Encapsulated result = encapsulator.encapsulate();
        byte[] encapsulation = result.encapsulation();
        SecretKey senderSecret = result.key();

        // Bên nhận decapsulate bằng private key tương ứng.
        KEM.Decapsulator decapsulator =
                kem.newDecapsulator(recipientKeys.getPrivate());
        SecretKey receiverSecret =
                decapsulator.decapsulate(encapsulation);

        // Chỉ kiểm tra round-trip trong ví dụ minh họa.
        if (!Arrays.equals(senderSecret.getEncoded(),
                           receiverSecret.getEncoded())) {
            throw new IllegalStateException("Shared secret không khớp");
        }

        System.out.println("KEM: " + kem.getAlgorithm());
        System.out.println("Encapsulation size: " + encapsulation.length);
        System.out.println("Shared secret size: " + encapsulator.secretSize());
    }
}
```

Không gửi private key hoặc shared secret qua mạng. Chỉ gửi encapsulation message cùng thông tin giao thức cần thiết. Trong ứng dụng thật, `recipientKeys.getPublic()` phải được xác thực là khóa của đúng người nhận; nếu kẻ tấn công thay public key bằng khóa của họ, KEM vẫn có thể tạo shared secret nhưng không còn bảo đảm đang chia sẻ bí mật với đúng đối tượng.

Phép so sánh `Arrays.equals` trong ví dụ chỉ dùng để kiểm tra hai kết quả trong một bài demo. Không ghi shared secret ra log, console, telemetry hoặc exception message. Khi xây dựng giao thức thực tế, dùng KDF và AEAD/HPKE để kiểm tra tính toàn vẹn của dữ liệu đã mã hóa thay vì so sánh hoặc truyền secret thô.

## 6. ML-KEM và yêu cầu hậu lượng tử hiện nay

`DHKEM` trong Java 21 dựa trên Diffie-Hellman với EC/XDH. Đây là lựa chọn hiện hành cho các giao thức phù hợp, nhưng không phải KEM hậu lượng tử. Nếu yêu cầu hệ thống là chống lại đối thủ có máy tính lượng tử đủ mạnh, cần xem xét ML-KEM theo NIST FIPS 203.

FIPS 203 được NIST ban hành ngày 13/08/2024 và định nghĩa ba parameter set:

| Parameter set | Public encapsulation key | Private decapsulation key | Ciphertext | Shared secret |
|---|---:|---:|---:|---:|
| ML-KEM-512 | 800 byte | 1.632 byte | 768 byte | 32 byte |
| ML-KEM-768 | 1.184 byte | 2.400 byte | 1.088 byte | 32 byte |
| ML-KEM-1024 | 1.568 byte | 3.168 byte | 1.568 byte | 32 byte |

Các parameter set tương ứng các security category 1, 3 và 5. Khi lựa chọn, cân nhắc mức bảo mật, kích thước public key/ciphertext, băng thông, hiệu năng và yêu cầu interoperability. ML-KEM-768 là lựa chọn cân bằng thường được cung cấp làm mặc định trong Oracle JDK 24, nhưng quyết định cuối cùng phải theo chính sách và giao thức của hệ thống.

**Phân biệt phiên bản Java:** Oracle JDK 21 tích hợp `DHKEM` trong SunJCE; danh sách KEM standard names của Java 21 chưa có `ML-KEM`. Oracle JDK 24 bổ sung `ML-KEM`, `ML-KEM-512`, `ML-KEM-768` và `ML-KEM-1024` trong SunJCE. Do đó, mã Java 21 không thể mặc định gọi `KEM.getInstance("ML-KEM")` nếu không cài provider bên ngoài có hỗ trợ. Nếu yêu cầu hậu lượng tử là bắt buộc, cần nâng runtime hoặc dùng provider đã được đánh giá và xác nhận tương thích với FIPS 203.

Không dùng tên Kyber draft hoặc định dạng thử nghiệm cũ thay cho ML-KEM final. Khi triển khai mới, đối chiếu FIPS 203, errata hiện hành và hướng dẫn sử dụng KEM trong NIST SP 800-227.

## 7. Kiểm tra đầu vào trước khi gọi KEM

Đầu vào không hợp lệ có thể xuất hiện ở nhiều tầng. Nên xác thực dữ liệu tại ranh giới nhận request và tiếp tục để provider kiểm tra tính hợp lệ mật mã.

### Tên thuật toán và provider

- Không nhận tên thuật toán tùy ý từ người dùng rồi chuyển thẳng vào `KEM.getInstance`.
- Dùng allowlist suite đã được giao thức quy định, ví dụ `DHKEM` trong môi trường Java 21.
- Nếu không có provider hỗ trợ, `KEM.getInstance` ném `NoSuchAlgorithmException`.
- Nếu truyền `null` làm tên thuật toán, phương thức ném `NullPointerException`.
- Tránh ghim tên provider trong ứng dụng đa nền tảng trừ khi yêu cầu vận hành/chứng nhận bắt buộc; hãy kiểm tra provider thực tế bằng `providerName()`.

### Public key và private key

`newEncapsulator(publicKey)` yêu cầu public key khác null và hợp lệ với KEM/provider được chọn. `newDecapsulator(privateKey)` cũng yêu cầu private key hợp lệ. API có thể ném `InvalidKeyException` nếu key null hoặc không được chấp nhận.

Các kiểm tra nên thực hiện:

1. Xác nhận public key lấy từ certificate, key directory hoặc nguồn đã xác thực.
2. Xác nhận thuật toán và curve/parameter set đúng với suite đã thống nhất.
3. Khi nhập key từ file hoặc HSM, xác minh định dạng, nguồn gốc, trạng thái thu hồi và quyền truy cập.
4. Đảm bảo public key và private key thuộc cùng một key pair. Tốt nhất tạo chúng trong cùng quy trình key generation; nếu nhập riêng, thực hiện kiểm tra nhất quán ở giai đoạn provisioning bằng quy trình được phê duyệt.
5. Bảo vệ private key bằng keystore/HSM phù hợp; không đưa private key vào log, source code hoặc cấu hình không bảo vệ.

Không chấp nhận một public key chỉ vì nó parse được thành `PublicKey`. Khả năng parse không chứng minh key thuộc về người nhận mà ứng dụng dự định liên lạc.

### Encapsulation message

Ở phía nhận, có thể kiểm tra độ dài trước khi decapsulate:

```java
KEM.Decapsulator decapsulator = kem.newDecapsulator(recipientPrivateKey);

if (encapsulation == null
        || encapsulation.length != decapsulator.encapsulationSize()) {
    throw new IllegalArgumentException("Encapsulation có kích thước không hợp lệ");
}

SecretKey sharedSecret = decapsulator.decapsulate(encapsulation);
```

Độ dài đúng chỉ là kiểm tra cấu trúc ban đầu; nó không chứng minh nội dung hợp lệ. Với Java KEM API, dữ liệu null có thể gây `NullPointerException`; dữ liệu sai kích thước hoặc lỗi decapsulation có thể được provider biểu diễn bằng `DecapsulateException`.

Không giả định mọi KEM xử lý ciphertext sai theo cùng cách. Ví dụ, ML-KEM theo FIPS 203 dùng *implicit rejection*: nếu kiểm tra re-encryption thất bại, thuật toán trả về một shared secret giả được dẫn xuất theo quy tắc chuẩn thay vì phát tín hiệu lỗi decapsulation trực tiếp. Vì vậy, với ML-KEM, ciphertext sai có thể đi tiếp tới bước KDF và tạo khóa khác; lỗi sau đó thường được phát hiện khi kiểm tra xác thực AEAD. Ứng dụng không được cố phân biệt nhánh implicit rejection bằng thời gian chạy, log hoặc phản hồi mạng.

### Tham số và độ dài khi yêu cầu SecretKey cụ thể

Overload `encapsulate(from, to, algorithm)` và `decapsulate(encapsulation, from, to, algorithm)` lấy một đoạn byte của shared secret và gán tên thuật toán cho `SecretKey` trả về. Cần bảo đảm `0 <= from <= to <= secretSize()`; chỉ số ngoài phạm vi gây `IndexOutOfBoundsException`. Provider có thể ném `UnsupportedOperationException` nếu không hỗ trợ tổ hợp độ dài và tên thuật toán được yêu cầu.

Không dùng overload này để tự thiết kế key schedule. Hãy theo KDF và độ dài khóa được giao thức quy định; kiểm tra cả hai phía sử dụng cùng offset, length và thuật toán.

## 8. Xử lý lỗi và tránh rò rỉ thông tin

| Tình huống | Kết quả API thường gặp | Cách xử lý |
|---|---|---|
| Thuật toán KEM không có provider hỗ trợ | `NoSuchAlgorithmException` | Kiểm tra JDK/provider và allowlist suite |
| Tên thuật toán null | `NullPointerException` | Kiểm tra cấu hình trước khi gọi |
| Public/private key null hoặc không hợp lệ | `InvalidKeyException` | Xác minh nguồn, loại key và parameter set |
| Tham số KEM sai hoặc thiếu | `InvalidAlgorithmParameterException` | Thống nhất tham số giữa encapsulation và decapsulation |
| Encapsulation null | `NullPointerException` | Kiểm tra dữ liệu tại ranh giới nhận |
| Encapsulation sai kích thước hoặc decapsulation thất bại | `DecapsulateException` với implementation phát lỗi tường minh | Ghi nhận lỗi an toàn; không tiết lộ chi tiết cho phía không tin cậy |
| Offset/length ngoài shared secret | `IndexOutOfBoundsException` | Xác thực `from`, `to` với `secretSize()` |
| Provider không hỗ trợ cách cắt/tên SecretKey yêu cầu | `UnsupportedOperationException` | Chọn cách dẫn xuất khóa được provider hỗ trợ hoặc dùng KDF riêng theo giao thức |

Không trả stack trace, loại private key, dữ liệu secret hoặc chi tiết kiểm tra nội bộ cho client không tin cậy. Phản hồi bên ngoài nên theo một chính sách lỗi thống nhất; log nội bộ chỉ ghi metadata cần thiết như suite, provider, correlation ID và loại lỗi đã được chuẩn hóa. Không log byte array encapsulation nếu giao thức hoặc chính sách bảo mật không cho phép.

Với ML-KEM, implicit rejection có nghĩa decapsulation có thể trả về một secret khác thay vì ném exception khi ciphertext bị sửa. Không coi việc `decapsulate()` trả về thành công là bằng chứng dữ liệu ứng dụng hợp lệ; phải hoàn tất bước AEAD authentication và chỉ chấp nhận plaintext sau khi tag xác thực thành công.

## 9. Các nguyên tắc an toàn khi tích hợp KEM

- Xác thực public key của người nhận trước khi encapsulate; KEM không tự xác thực danh tính.
- Dùng nguồn ngẫu nhiên mật mã do provider quản lý; không tự tạo randomness từ timestamp, counter hoặc `Random` thông thường.
- Không tái sử dụng encapsulation message hoặc tự tái sử dụng ephemeral secret theo cách ngoài giao thức.
- Dùng KDF và AEAD/HPKE được chuẩn hóa; không dùng shared secret thô để mã hóa dữ liệu tùy ý.
- Gắn context, phiên bản giao thức, danh tính hai phía và suite đã thương lượng vào key schedule theo quy định giao thức để tránh nhầm ngữ cảnh hoặc downgrade.
- Bảo vệ private key và xóa/giải phóng bản sao secret khi API và môi trường cho phép.
- Không tự viết lại thuật toán KEM, không sửa ciphertext trước khi decapsulate và không bỏ qua kiểm tra AEAD tag.
- Kiểm thử interoperability với đúng provider/JDK của cả hai phía; tên thuật toán giống nhau không bảo đảm mọi provider hỗ trợ cùng key encoding hoặc parameter set.

## 10. Checklist chọn KEM và xử lý dữ liệu

- [ ] Đã xác định yêu cầu là KEM cổ điển hay cần khả năng chống lượng tử.
- [ ] Với Java 21 tích hợp, đã xác nhận provider hỗ trợ `DHKEM` và loại key/curve cần dùng.
- [ ] Nếu cần ML-KEM, đã chọn JDK/provider hỗ trợ FIPS 203; không giả định Java 21 có sẵn thuật toán này.
- [ ] Hai phía thống nhất KEM, curve/parameter set, định dạng key và giao thức bao quanh.
- [ ] Đã xác thực public key thuộc đúng người nhận.
- [ ] Đã kiểm tra kích thước shared secret và encapsulation bằng `secretSize()`/`encapsulationSize()`.
- [ ] Không nhầm số byte shared secret với mức bảo mật hoặc kích thước khóa AEAD.
- [ ] Đã dùng KDF và AEAD/HPKE để tạo khóa phiên và bảo vệ dữ liệu.
- [ ] Đã kiểm tra null, loại key, parameter set, kích thước encapsulation và offset/length.
- [ ] Đã hiểu khác biệt giữa `DecapsulateException` và implicit rejection của ML-KEM.
- [ ] Không để lỗi decapsulation làm lộ thông tin qua timing, log hoặc phản hồi mạng.
- [ ] Đã kiểm thử round-trip và interoperability bằng đúng JDK/provider triển khai.

## Tài liệu tham khảo

- [KEM — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html): API KEM, provider selection, encapsulator/decapsulator và ví dụ X25519.
- [KEM.Encapsulator — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html): `encapsulate`, `secretSize`, `encapsulationSize` và các trường hợp đầu vào không hợp lệ.
- [KEM.Decapsulator — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html): `decapsulate`, kích thước encapsulation và `DecapsulateException`.
- [Java Security Standard Algorithm Names — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): tên chuẩn `DHKEM` theo RFC 9180.
- [JDK Providers Documentation — Java SE 21](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html): SunJCE hỗ trợ `DHKEM` và các curve EC/XDH được chấp nhận.
- [RFC 9180: Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html): DHKEM, kích thước shared secret/encapsulation và cách kết hợp KEM, KDF, AEAD trong HPKE.
- [NIST FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard](https://csrc.nist.gov/pubs/fips/203/final): ML-KEM-512, ML-KEM-768 và ML-KEM-1024; kích thước key/ciphertext và implicit rejection.
- [Oracle JDK 24 Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/24/docs/specs/security/standard-names.html): tên chuẩn ML-KEM được hỗ trợ trong các JDK mới hơn Java 21.
- [NIST SP 800-227: Recommendations for Key-Encapsulation Mechanisms](https://csrc.nist.gov/pubs/sp/800/227/final): hướng dẫn hiện hành của NIST về triển khai và sử dụng KEM an toàn.
