# 4.7 Giới hạn của digest công khai trước dữ liệu bị thay thế và mật khẩu yếu

Một **digest công khai** như SHA-256 rất hữu ích để phát hiện dữ liệu bị thay đổi **khi người kiểm tra đã có một giá trị digest đáng tin cậy**. Nhưng hàm băm không chứa bí mật: bất kỳ ai có dữ liệu cũng có thể tính lại digest. Vì thế, nếu kẻ tấn công có thể thay **cả nội dung lẫn digest đi kèm**, phép so khớp vẫn thành công. Tương tự, băm trực tiếp một mật khẩu dễ đoán bằng SHA-256 không làm mật khẩu đó trở nên khó đoán: khi digest bị lộ, đối thủ có thể thử hàng loạt ứng viên **offline**, không cần gửi yêu cầu đăng nhập.

Hai tình huống này cùng liên quan tới hàm băm nhưng có **mô hình đe dọa khác nhau**:

- **Tính toàn vẹn/xác thực nguồn dữ liệu:** người kiểm tra cần biết digest tham chiếu đến từ nguồn nào và đã được bảo vệ như thế nào. Nếu cần xác thực nguồn gốc, dùng **HMAC** với khóa bí mật chung hoặc **chữ ký số** với khóa công khai đáng tin cậy, tùy kiến trúc.
- **Lưu trữ và xác minh mật khẩu:** máy chủ cần kiểm chứng mật khẩu mà không lưu plaintext, đồng thời khiến mỗi lần đoán mật khẩu bị lộ tốn tài nguyên. Dùng **password hashing/KDF có salt riêng và work factor**, ưu tiên Argon2id khi có thư viện thích hợp; PBKDF2-HMAC-SHA256 là ví dụ thực hiện được qua API JCA/JCE trong Java.

Bài này chỉ ra chính xác giới hạn của digest, minh họa hai cuộc tấn công ở mức kiến thức, rồi xây dựng cách kiểm tra phù hợp bằng Java 17+.

## 1. Digest công khai thực sự bảo đảm điều gì?

Với `SHA-256`:

```text
Dữ liệu gốc (bytes)  ── SHA-256 ──>  digest 256 bit (32 byte)

Người kiểm tra:
  digestTinhLai = SHA-256(duLieuNhanDuoc)
  digestTinhLai == digestThamChieu ? "khớp" : "không khớp"
```

SHA-256 là một hàm băm mật mã được thiết kế có các tính chất bảo mật như kháng tìm tiền ảnh, kháng tìm tiền ảnh thứ hai và kháng va chạm. Đầu ra có độ dài cố định; thay đổi một byte của dữ liệu thường làm digest khác đi. Tuy nhiên, **đó không phải cơ chế xác thực người phát hành**. Hàm băm là thuật toán công khai, không cần khóa, nên một bên đối địch cũng có thể tính `SHA-256(noiDungGia)`.

Phân biệt các thuật ngữ thường gặp:

| Khái niệm | Câu hỏi được trả lời | Giới hạn cần nhớ |
| --- | --- | --- |
| **Digest khớp** | Dữ liệu đang có khớp với **giá trị tham chiếu được dùng để so sánh** không? | Chưa chứng minh giá trị tham chiếu đó đáng tin. |
| **Kháng va chạm** | Có khó tìm hai thông điệp khác nhau cùng digest không? | Kẻ tấn công thay cả nội dung lẫn digest **không cần tìm va chạm**. |
| **Kháng tiền ảnh** | Có khó tìm dữ liệu từ digest cho một đầu vào đủ khó đoán không? | Mật khẩu ngắn/phổ biến có không gian thử nhỏ; có thể thử từ điển. |
| **Tính toàn vẹn có nguồn tin cậy** | Dữ liệu hiện tại có trùng nội dung mà nguồn đã xác thực công bố không? | Phụ thuộc cách bảo vệ/bắt nguồn của digest tham chiếu. |
| **Xác thực nguồn gốc** | Dữ liệu có thực sự do chủ thể nắm khóa hợp lệ tạo ra không? | Cần MAC/chữ ký số và quản lý khóa; digest thuần không đủ. |

Một checksum SHA-256 được đăng trên trang chính thức có thể hữu ích nếu chính trang/kênh lấy checksum được xác thực và đối thủ không sửa được. Nếu tải file và checksum từ **cùng một kho HTTP không đáng tin** mà đối thủ kiểm soát, việc khớp checksum gần như không mang bằng chứng chống giả mạo.

### 1.1 Tấn công thay cả dữ liệu và digest

```text
BÊN PHÁT HÀNH               KÊNH CÓ THỂ BỊ THAY                BÊN NHẬN
file.bin  ----------------> [thay bằng fake.bin] ------------> fake.bin
SHA256(file.bin) ----------> [đổi thành SHA256(fake.bin)] ----> SHA256(fake.bin)

Bên nhận: SHA256(fake.bin) == SHA256(fake.bin)  => true
Bên nhận: không hề biết file.bin ban đầu là gì!
```

Kẻ tấn công không phá SHA-256, không giải thuật toán, cũng không cần tìm hai file trùng digest. Họ chỉ thay **một cặp dữ liệu + digest tương ứng**. Nếu người nhận có digest gốc được xác minh từ một kênh độc lập, phép đối chiếu với cặp giả sẽ **không khớp**.

Do đó cần đặt đúng câu hỏi: *“Ai có quyền thay nội dung? Ai có quyền thay digest tham chiếu? Dựa vào đâu ta tin digest tham chiếu?”* Trả lời ba câu này trước khi nói một checksum “bảo vệ tính toàn vẹn”.

### 1.2 Khi nào chỉ SHA-256 là phù hợp?

- **Phát hiện lỗi truyền/lưu trữ ngoài ý muốn:** ví dụ checksum của bản sao lưu hoặc file build, khi điểm đối chiếu ban đầu đáng tin.
- **Nhận diện nội dung (content addressing/deduplication):** dùng digest để phân loại nội dung; cần bổ sung biện pháp kiểm soát nguồn/giá trị mong đợi khi có đối thủ chủ động.
- **Kiểm tra tải xuống:** file có digest trùng với digest chuẩn đã nhận qua kênh tin cậy. Digest lấy từ cùng nguồn không bảo vệ thì không chứng minh nhà phát hành.
- **Không thích hợp một mình:** xác thực webhook, bảo đảm manifest cập nhật không bị tráo, ký gói phần mềm, bảo vệ dữ liệu khỏi người có thể sửa đồng thời cả dữ liệu và checksum, hoặc bảo vệ cơ sở dữ liệu mật khẩu yếu.

## 2. Ba cách bảo vệ dữ liệu khỏi bị tráo

Khi cần chống đối thủ có thể thay đổi dữ liệu, lựa chọn cơ chế theo bên nào cần kiểm chứng và bên nào nắm khóa.

| Cơ chế | Bí mật/điểm tin cậy cần giữ | Ai có thể kiểm chứng? | Dùng cho |
| --- | --- | --- | --- |
| `SHA-256(data)` và **expected digest được xác thực** | Kênh/manifest chứa digest tham chiếu phải đáng tin | Bất cứ ai có expected digest đáng tin | Kiểm tra file download, checksum bản phát hành. |
| `HMAC-SHA256(key, data)` | **Khóa đối xứng bí mật** chỉ chia sẻ giữa các bên hợp lệ | Bên giữ cùng khóa | Xác thực webhook nội bộ hoặc thông điệp giữa hai dịch vụ chia sẻ khóa. |
| **Chữ ký số** `Sign(privateKey, data)` | Khóa riêng của bên ký; danh tính và khóa công khai của họ phải được xác thực | Bất cứ ai có **khóa công khai tin cậy** | Phân phối phần mềm, manifest phát hành, nhiều bên xác minh độc lập. |
| **AEAD** (ví dụ AES-GCM) | Khóa mã hóa hợp lệ, nonce/IV đúng quy tắc và tag | Bên giữ khóa giải mã | Khi cần **bí mật nội dung và xác thực bản mã**, không phải chỉ checksum. |

**HMAC** dùng hàm băm bên trong nhưng có **khóa bí mật**, nên một bên chỉ sửa dữ liệu mà không biết khóa sẽ không tự tạo được MAC hợp lệ. Không dùng `SHA256(key || message)` tự chế thay cho HMAC; hãy dùng `javax.crypto.Mac` và `HmacSHA256`. Khóa HMAC phải đủ ngẫu nhiên, được cấp và quản lý an toàn, không hardcode. Bên nào biết cùng khóa cũng có khả năng tạo MAC, vì vậy HMAC không đem lại tính chứng minh công khai ai đã ký như chữ ký số.

Với chữ ký số, API Java là `java.security.Signature`. Nhà phát hành ký bằng `PrivateKey`, bên nhận kiểm tra bằng `PublicKey` **được gắn với danh tính đáng tin**. Tải khóa công khai từ cùng kho đang bị tấn công mà không kiểm tra nguồn cũng có thể dẫn tới xác minh một chữ ký giả được tạo bằng khóa của đối thủ. Nếu dùng certificate, phải kiểm tra chuỗi tin cậy, mục đích sử dụng và trạng thái phù hợp chính sách.

HMAC/chữ ký số cũng **không tự ngăn phát lại** một thông điệp cũ vốn hợp lệ. Nếu hệ thống cần chống replay/rollback, đưa version, timestamp, sequence/nonce hoặc định danh sự kiện vào dữ liệu được xác thực và kiểm soát trạng thái ở phía nhận.

## 3. Ví dụ Java 17+: thay dữ liệu, thay digest, đối chiếu HMAC và đoán mật khẩu yếu

Lưu thành **`PublicDigestDemo.java`**. Ví dụ dùng `MessageDigest` tính SHA-256; `Mac` tính HMAC-SHA256. Đoạn đoán mật khẩu chỉ chạy trên mẫu `123456` được tạo ngay trong chương trình để giải thích cơ chế tấn công offline.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class PublicDigestDemo {
    static byte[] sha256(String text) throws GeneralSecurityException {
        return MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.UTF_8));
    }

    static byte[] hmac(String text, byte[] key) throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(text.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws GeneralSecurityException {
        String original = "name=invoice;amount=100";
        String changed = "name=invoice;amount=900";

        byte[] trustedDigest = sha256(original);
        byte[] replacedDigest = sha256(changed);

        // Attacker chỉ thay file; expected digest gốc được bảo vệ.
        System.out.println("1. Digest cu khop noi dung bi doi: "
                + MessageDigest.isEqual(trustedDigest, sha256(changed)));

        // Attacker thay được cả file lẫn expected digest đi kèm.
        System.out.println("2. Digest gia khop noi dung bi doi: "
                + MessageDigest.isEqual(replacedDigest, sha256(changed)));

        // Khóa ví dụ được tạo ngẫu nhiên, hai đầu hợp lệ phải chia sẻ an toàn.
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        try {
            byte[] trustedMac = hmac(original, key);
            // Bên nhận tự tính lại MAC bằng khóa bí mật của mình.
            System.out.println("3. HMAC cu khop noi dung bi doi: "
                    + MessageDigest.isEqual(trustedMac, hmac(changed, key)));
        } finally {
            Arrays.fill(key, (byte) 0);
        }

        // Chỉ minh họa một mật khẩu yếu tự tạo; không dùng làm xử lý thật.
        byte[] leakedDigest = sha256("123456");
        boolean guessed = false;
        for (String candidate : new String[]{"admin", "123456", "welcome"}) {
            if (MessageDigest.isEqual(leakedDigest, sha256(candidate))) {
                guessed = true;
                break;
            }
        }
        System.out.println("4. Doan duoc mat khau yeu offline: " + guessed);
    }
}
```

Chạy bằng Java 17+ với provider JDK thông dụng hỗ trợ SHA-256 và HmacSHA256:

```bash
javac -encoding UTF-8 PublicDigestDemo.java
java PublicDigestDemo
```

Stdout (không phụ thuộc giá trị khóa ngẫu nhiên):

```text
1. Digest cu khop noi dung bi doi: false
2. Digest gia khop noi dung bi doi: true
3. HMAC cu khop noi dung bi doi: false
4. Doan duoc mat khau yeu offline: true
```

Đọc kỹ bốn kết quả:

1. `false`: digest của dữ liệu giả **khác** digest gốc đáng tin. Đây là trường hợp đối chiếu checksum hữu ích.
2. `true`: digest giả được tính trên dữ liệu giả nên khớp. Đây là **thất bại của nguồn tham chiếu không được bảo vệ**, không phải lỗi của SHA-256.
3. `false`: MAC hợp lệ của thông điệp gốc không còn khớp với thông điệp đã thay. Trong thực tế, đối thủ **không biết khóa** nên không thể đơn giản tự tính một MAC mới hợp lệ; bên nhận phải lấy MAC gốc từ nguồn chính sách cho phép và kiểm tra nó.
4. `true`: chỉ từ một digest SHA-256 của mật khẩu yếu, chương trình đoán trúng bằng danh sách ứng viên nhỏ. Không có thao tác “giải mã hash”: nó chỉ **băm từng ứng viên rồi so sánh**.

`MessageDigest.isEqual(byte[], byte[])` phù hợp để so sánh các digest/MAC ở mức byte; tránh phép so chuỗi tự chế dừng tại ký tự sai đầu tiên. Không được nhầm “so sánh cẩn thận” với “ngăn brute force”: nó không làm phép băm trở nên chậm và không tạo bí mật cho digest công khai. Ví dụ dùng `String` cố định để dễ đọc; dữ liệu thực phải được xác thực trên **chuỗi byte chính xác**, với định dạng/canonicalization nhất quán.

## 4. Vì sao SHA-256 thuần không bảo vệ mật khẩu yếu?

Giả sử cơ sở dữ liệu lưu:

```text
username = alice
password_hash = SHA256("123456")
```

Khi bản ghi bị lộ, đối thủ biết thuật toán là SHA-256 và biết digest được lưu. Họ có thể đoán hàng triệu ứng viên từ từ điển/bộ quy tắc ở máy riêng, tính `SHA256(candidate)` rồi so sánh. Không bị giới hạn bởi tốc độ endpoint đăng nhập, CAPTCHA hoặc khóa tài khoản, vì đây là **tấn công offline trên dữ liệu đã lộ**. Năng lực thực tế tùy phần cứng và thuật toán, nhưng SHA-256 được thiết kế chạy nhanh; điều đó rất tốt cho checksum, lại bất lợi khi mật khẩu có độ ngẫu nhiên thấp.

Các hiểu lầm cần sửa:

- **“SHA-256 không đảo ngược nên không ai tìm được mật khẩu.”** Không cần đảo ngược: chỉ cần thử các mật khẩu có xác suất cao. Một giá trị như `123456` bị đoán rất nhanh.
- **“Đổi SHA-256 sang SHA-512 là đủ.”** SHA-512 cũng là digest tổng quát nhanh; chỉ tăng độ dài digest không bổ sung work factor đủ lớn.
- **“Băm hai/lần vài lần sẽ an toàn.”** Lặp một vài vòng SHA-256 tự thiết kế không tương đương password hashing đã được phân tích và điều chỉnh chi phí.
- **“Thêm salt sẽ khiến mật khẩu khó đoán.”** Salt chủ yếu ngăn dùng bảng băm tính trước và giảm hiệu quả tái sử dụng kết quả trên nhiều tài khoản. Salt **không tăng entropy thực** của mật khẩu.
- **“Giữ kín tên thuật toán là đủ.”** Không nên dựa vào bí mật của thuật toán: thiết kế phải chống chịu ngay cả khi lộ thuật toán, tham số và salt.
- **“Có rate limit là đã an toàn.”** Rate limit bảo vệ truy cập **online**, không chặn thử offline trên dữ liệu hash bị lộ.

Nếu mật khẩu chỉ thuộc một tập nhỏ, đối thủ có thể thử toàn bộ tập đó với bất kỳ hash công khai nào. Mật khẩu phải đủ khó đoán, hệ thống nên sàng lọc mật khẩu phổ biến/đã lộ theo chính sách và dùng password hashing có chi phí đáng kể.

### 4.1 Salt, work factor và pepper khác nhau ra sao?

```text
password (bí mật người dùng) + salt riêng (công khai)
                |
                v
 Password KDF (ví dụ PBKDF2-HMAC-SHA256)
   có cost / iterations lớn và được hiệu chuẩn
                |
                v
    derived hash / verifier
                |
                v
Lưu: algorithm + parameters + salt + derived hash
```

| Thành phần | Vai trò | Có thể lưu cùng hash? |
| --- | --- | --- |
| **Salt** | Sinh riêng, ngẫu nhiên cho mỗi bản ghi; làm hai mật khẩu giống nhau thường có kết quả khác nhau; chống bảng tra cứu tính trước dùng chung. | **Có.** Salt không phải mật khẩu và không cần giữ bí mật. |
| **Work factor** | Làm mỗi lần đoán đắt hơn về CPU và/hoặc RAM; cập nhật theo thời gian khi phần cứng thay đổi. | **Có.** Phải lưu để xác minh bản ghi và hỗ trợ nâng cấp. |
| **Pepper** (tùy chọn) | Một bí mật bổ sung dùng trong thiết kế phù hợp, giúp chống lại tình huống chỉ lộ database. | **Không.** Lưu tách DB, ví dụ hệ quản lý secret hoặc HSM; không nhúng trong mã nguồn/cùng bảng hash. |
| **Password** | Bí mật mà người dùng cung cấp để xác minh. | **Không lưu plaintext** và không ghi vào log. |

**Salt không phải khóa HMAC.** Một `SHA256(salt || password)` đơn lẻ có salt tốt vẫn là phép băm **nhanh**; không đủ chống đoán offline. Salt cần dùng **cùng** KDF chuyên cho mật khẩu. Hai người có chung password nên có salt riêng và hash riêng, nhưng một mật khẩu phổ biến vẫn dễ bị đoán hơn một passphrase ngẫu nhiên mạnh.

**Pepper không thay thế salt/KDF**. Nó là biện pháp bổ sung có chi phí vận hành (quản lý/luân chuyển khóa, phục hồi), chỉ hữu ích khi khóa pepper không bị lộ cùng dữ liệu. Nếu kẻ tấn công có quyền sửa bảng hash trong database, họ còn có thể thay bản ghi theo cách khác: việc làm chậm đoán mật khẩu **không tự cung cấp tính toàn vẹn** hay phân quyền ghi cơ sở dữ liệu.

## 5. Chọn cơ chế lưu mật khẩu đúng

Mục tiêu của password hashing là làm tốn tài nguyên **mỗi lần thử ứng viên**, kể cả khi kẻ tấn công có bản ghi hash/salt. Các lựa chọn được dùng phổ biến:

| Cơ chế | Đặc điểm | Khi nên dùng |
| --- | --- | --- |
| **Argon2id** | KDF chuyên cho mật khẩu, có tham số RAM, thời gian và song song; chống đoán bằng phần cứng song song tốt hơn digest nhanh. | **Ưu tiên cho thiết kế mới** nếu có thư viện tin cậy và vận hành phù hợp. |
| **scrypt** | KDF phụ thuộc bộ nhớ với tham số CPU/RAM. | Khi Argon2id không có nhưng thư viện scrypt tin cậy sẵn có. |
| **bcrypt** | Password hash có cost điều chỉnh; nhiều triển khai có giới hạn độ dài đầu vào 72 byte. | Hệ thống cũ đã dùng bcrypt; kiểm tra chính xác giới hạn và migration. |
| **PBKDF2-HMAC-SHA256** | KDF dựa trên số vòng lặp HMAC; phổ biến và có thể dùng qua `SecretKeyFactory` trên JDK thích hợp. Không phải memory-hard. | Khi có yêu cầu tương thích/tuân thủ hoặc muốn học API JCA/JCE; phải hiệu chuẩn số vòng lặp. |
| **SHA-256/SHA-512/MD5 thuần** | Digest tổng quát, chạy nhanh, không có cost/password salt tích hợp. | **Không** dùng trực tiếp làm password verifier. |

Theo **OWASP Password Storage Cheat Sheet** được tham khảo cho bài này, cấu hình tối thiểu điển hình với Argon2id là `m=19456 KiB (~19 MiB), t=2, p=1`; với PBKDF2-HMAC-SHA256 là **600.000 vòng** (đặc biệt khi cần giải pháp theo FIPS). Các giá trị là **mức tham chiếu tại thời điểm triển khai**, phải rà lại tài liệu mới và đo trên môi trường sản xuất. Tăng cost quá mức có thể làm máy chủ bị quá tải khi nhiều lần đăng nhập; cần hạn chế lưu lượng và đánh giá tài nguyên. Không dùng duy nhất một mốc benchmark trên laptop cho mọi môi trường.

Java 17 cung cấp API `javax.crypto.SecretKeyFactory`, `javax.crypto.spec.PBEKeySpec` cho PBKDF2 qua provider có hỗ trợ `PBKDF2WithHmacSHA256`. JDK chuẩn không đưa ra một API tích hợp chung bảo đảm có Argon2id trên mọi môi trường: nếu chọn Argon2id, sử dụng thư viện được duy trì, kiểm tra phiên bản/dependency và triển khai theo hướng dẫn của thư viện.

### 5.1 Quy tắc lưu bản ghi verifier

Một bản ghi nên chứa đủ thông tin **để xác minh và nâng cấp**, chẳng hạn:

```text
pbkdf2-sha256$600000$base64(salt)$base64(derivedHash)
```

Đây là **định dạng riêng của ví dụ**; các trường lần lượt là tên scheme, số vòng lặp, salt và hash đã dẫn xuất. Tất cả các trường trừ password có thể công khai. Trong production, cần định nghĩa encoding và phiên bản định dạng ổn định, giới hạn độ dài và cost được chấp nhận để dữ liệu bản ghi hỏng không gây DoS, áp dụng migration cho bản ghi cũ, và bảo vệ quyền ghi/tính toàn vẹn của kho lưu trữ. Không bao giờ lưu mật khẩu ở dạng Base64: Base64 chỉ là mã hóa biểu diễn.

## 6. Ví dụ Java 17+: lưu và xác minh mật khẩu bằng PBKDF2 có salt

Ví dụ này chọn **PBKDF2WithHmacSHA256**, salt 16 byte từ `SecureRandom`, **600.000** vòng lặp và output 256 bit. Tên thuật toán/salt/cost được lưu cùng verifier; khi xác minh, dùng salt/cost đã lưu và so sánh `MessageDigest.isEqual`. Mật khẩu trong `main` là giá trị minh họa công khai, **không** dùng làm mật khẩu thật.

Lưu thành **`PasswordStorageDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordStorageDemo {
    private static final String SCHEME = "pbkdf2-sha256";
    private static final String JCA_ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int ROUNDS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final SecureRandom RANDOM = new SecureRandom();

    private static byte[] derive(char[] password, byte[] salt, int rounds)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, rounds, KEY_BITS);
        try {
            return SecretKeyFactory.getInstance(JCA_ALGORITHM)
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static String store(char[] password) throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] result = derive(password, salt, ROUNDS);
        try {
            return SCHEME + "$" + ROUNDS + "$"
                    + Base64.getEncoder().encodeToString(salt) + "$"
                    + Base64.getEncoder().encodeToString(result);
        } finally {
            Arrays.fill(result, (byte) 0);
        }
    }

    static boolean verify(char[] input, String record)
            throws GeneralSecurityException {
        if (record == null) return false;
        String[] fields = record.split("\\$", -1);
        if (fields.length != 4 || !SCHEME.equals(fields[0])) return false;

        int rounds;
        try {
            rounds = Integer.parseInt(fields[1]);
        } catch (NumberFormatException ex) {
            return false;
        }
        // Chặn cost bất thường trong định dạng demo do chính ứng dụng tạo.
        if (rounds < 100_000 || rounds > 2_000_000) return false;

        byte[] salt;
        byte[] expected;
        try {
            salt = Base64.getDecoder().decode(fields[2]);
            expected = Base64.getDecoder().decode(fields[3]);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (salt.length != SALT_BYTES || expected.length != KEY_BITS / 8) {
            return false;
        }

        byte[] actual = derive(input, salt, rounds);
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    public static void main(String[] args) throws GeneralSecurityException {
        char[] good = "DemoOnly#NotARealPassword".toCharArray();
        char[] wrong = "wrong-guess".toCharArray();
        try {
            String record = store(good);
            System.out.println("4. Dung mat khau: " + verify(good, record));
            System.out.println("5. Sai mat khau: " + verify(wrong, record));
            String[] fields = record.split("\\$");
            System.out.println("6. Salt 16 byte duoc luu: "
                    + (Base64.getDecoder().decode(fields[2]).length == 16));
        } finally {
            Arrays.fill(good, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

```bash
javac -encoding UTF-8 PasswordStorageDemo.java
java PasswordStorageDemo
```

Stdout (salt và hash mỗi lần chạy là ngẫu nhiên, nhưng các dòng kiểm tra dưới đây cố định):

```text
4. Dung mat khau: true
5. Sai mat khau: false
6. Salt 16 byte duoc luu: true
```

Giải thích các bước:

1. `store` tạo **salt mới** cho từng bản ghi bằng `SecureRandom`, không dùng chung một salt cố định.
2. `PBEKeySpec(password, salt, rounds, KEY_BITS)` mô tả các tham số của PBKDF2; `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` tạo kết quả dẫn xuất. Không thay bằng `MessageDigest.getInstance("SHA-256")` lặp vài lần tự chế.
3. Trường `SCHEME` và `rounds` được lưu, nên sau này có thể phân biệt bản ghi cũ/mới. Salt phải giống với lúc tạo bản ghi; **không sinh salt mới khi verify**.
4. `verify` kiểm tra định dạng, giới hạn rounds, độ dài salt và hash trước khi tính lại. Giới hạn rounds trong ví dụ ngăn tham số do bản ghi bất thường khiến CPU bị chiếm quá lâu; hệ thống thực phải định nghĩa chính sách migration cho các giá trị lịch sử.
5. `MessageDigest.isEqual` so sánh byte array sau dẫn xuất; không dùng `String.equals` trên plaintext hoặc so từng ký tự đến khi khác.
6. `PBEKeySpec.clearPassword()` xóa **bản sao password bên trong spec**, và `Arrays.fill` xóa một số buffer do chương trình sở hữu. Điều đó không bảo đảm xóa mọi bản sao trong JVM hay provider. Vì `main` chứa string literal công khai để demo, không dùng cách này nhận mật khẩu production; hãy nhận đầu vào qua quy trình bảo mật phù hợp và tránh lưu/log dưới dạng `String` lâu dài.

**Giới hạn của ví dụ:** đây là mô-đun Java console giúp học JCA/JCE, chưa có database, API đăng nhập, TLS, rate limit, pepper, kiểm tra mật khẩu đã lộ, migration hoặc giám sát tải. Các bản ghi bị kẻ tấn công **sửa trực tiếp** vẫn đòi hỏi kiểm soát quyền ghi/đảm bảo toàn vẹn database. `PBKDF2` làm chậm đoán offline nhưng không bù đắp một mật khẩu cực yếu và không thay thế quy trình quản lý tài khoản.

## 7. Vận hành password verifier thực tế

Một thiết kế thực tế cần xem password hashing trong toàn bộ vòng đời:

1. **Đăng ký/đổi mật khẩu:** kiểm tra theo chính sách chấp nhận độ dài, mật khẩu phổ biến/đã lộ và Unicode; không ép các quy tắc ghép ký tự tùy tiện. NIST SP 800-63B-4 nhấn mạnh độ dài, blocklist, mật khẩu đủ mạnh và khả năng dùng trình quản lý mật khẩu.
2. **Chuẩn hóa nhất quán:** cùng một password phải đi vào KDF dưới cùng encoding/quy tắc Unicode khi tạo và xác minh. Nếu áp dụng Unicode normalization như NFC, đưa vào contract và thực hiện nhất quán. Không âm thầm `trim`, lowercase hoặc cắt ngắn password khi xác minh.
3. **Tạo verifier:** dùng KDF, salt mới và work factor theo cấu hình đã đo. Không để người dùng điều khiển thuật toán/cost qua request; không tạo salt bằng `Random` hoặc thời gian hệ thống.
4. **Lưu có cấu trúc:** ghi algorithm/version, salt, cost và derived hash. Phân quyền DB, sao lưu và log phù hợp; không lưu plaintext/recovery hint.
5. **Xác minh:** nhận password qua TLS hoặc kênh bảo vệ tương đương; dùng tham số đã lưu, so sánh an toàn, trả thông báo thất bại không lộ account internals. Rate limit và bảo vệ abuse vẫn cần thiết dù có KDF.
6. **Nâng cấp:** khi cost hoặc scheme cũ, **sau một lần xác minh hợp lệ** có thể tạo verifier mới với salt/cost mới rồi cập nhật an toàn. Không thể chuyển trực tiếp SHA-256 hash cũ thành một password KDF mạnh tương đương mà không có password gốc; lập kế hoạch rehash hoặc reset.
7. **Giám sát và xử lý sự cố:** theo dõi thời gian/công suất xác minh, phát hiện credential stuffing và tấn công account, bảo vệ pepper riêng (nếu dùng), buộc đổi mật khẩu khi có bằng chứng lộ bí mật.

### 7.1 Đo chi phí và chống quá tải

Password hashing cố ý tốn tài nguyên. Nếu mỗi lần xác minh dùng nhiều CPU/RAM, nhiều request đồng thời có thể làm dịch vụ cạn tài nguyên. Kết hợp work factor được hiệu chuẩn, giới hạn số lần thử, kiểm soát đồng thời, timeout và theo dõi latency. Khi dùng Argon2id, đặc biệt phải tính tổng RAM ở số lượng request đồng thời; không chỉ tăng `m` đến mức tối đa trong tài liệu tham khảo.

**Không giảm work factor một cách im lặng** chỉ vì hệ thống quá tải. Hãy xác định tải thực, tối ưu luồng xác minh, thiết lập giới hạn, rồi chọn cấu hình đã được phê duyệt và tái đo khi đổi máy/JDK/provider.

## 8. Phân biệt lựa chọn qua các tình huống

| Tình huống | Chọn gì? | Vì sao? |
| --- | --- | --- |
| Muốn biết file tải xuống có đúng byte so với checksum **đã xác minh** hay không | SHA-256 + expected digest tin cậy | Kiểm tra tính khớp, không cần khóa mới khi nguồn expected đã được xác thực. |
| File và checksum cùng nằm trong kho mà đối thủ có thể thay | Chữ ký số của manifest/file hoặc digest từ nguồn bảo vệ độc lập | Digest thuần của file giả vẫn khớp digest giả. |
| Hai dịch vụ dùng bí mật chung để xác thực payload webhook | HMAC-SHA256 với quản lý key, định dạng xác thực rõ ràng | Bên không giữ key không tự tạo MAC mới hợp lệ. |
| Public download được nhiều bên kiểm tra độc lập | Chữ ký số và khóa công khai gắn danh tính đáng tin | Không phải chia sẻ khóa bí mật HMAC cho mọi người dùng. |
| Cần cả tính bí mật và xác thực bản mã | AEAD phù hợp, ví dụ AES-GCM | Digest/MAC không tự mã hóa để giấu plaintext. |
| Lưu verifier đăng nhập | Argon2id/scrypt hoặc PBKDF2 phù hợp + salt riêng + cost | Làm chậm tấn công đoán offline vào mật khẩu có thể bị lộ. |
| Người dùng chọn `123456` | Blocklist/chính sách mật khẩu, mật khẩu mạnh, KDF và cơ chế xác thực khác | KDF không biến một bí mật cực dễ đoán thành bí mật mạnh. |
| Đối thủ có quyền ghi bảng password verifier | Bảo vệ quyền ghi DB, kiểm tra toàn vẹn, giám sát thay đổi | KDF chống thử password trên bản ghi bị lộ; không tự ngăn thay bản ghi. |

### 8.1 Bốn câu hỏi để tự kiểm tra

**Câu 1.** “Tôi tải file từ máy chủ A, và máy chủ A trả kèm SHA-256. Hai giá trị khớp; tôi có chắc file không bị tráo?”  
**Trả lời:** Chỉ chắc rằng file khớp với giá trị checksum được nhận. Nếu đối thủ thay được cả hai trên đường truyền/kho lưu, không có bảo đảm về nguồn gốc. Cần xác thực kênh, checksum kỳ vọng đáng tin, hoặc chữ ký số.

**Câu 2.** “Nếu tấn công thay file và checksum mà vẫn khớp, có phải SHA-256 bị collision?”  
**Trả lời:** Không. Đối thủ tính digest mới của file mới, không cần hai file khác nhau có cùng digest. Va chạm không liên quan đến ví dụ này.

**Câu 3.** “Thêm 16 byte salt ngẫu nhiên vào `SHA256(password)` đã đủ lưu password chưa?”  
**Trả lời:** Chưa. Salt làm hash của các bản ghi khác nhau và chống bảng tính trước, nhưng SHA-256 một vòng vẫn nhanh. Dùng KDF chuyên dụng với work factor, salt riêng và mật khẩu khó đoán.

**Câu 4.** “Trong chương trình PBKDF2, vì sao lúc xác minh phải đọc salt và rounds từ record?”  
**Trả lời:** KDF phải nhận lại đúng tham số đã dùng khi tạo verifier; salt mới sẽ tạo kết quả khác. Lưu version/work factor cho phép xác minh bản ghi lịch sử và nâng cấp qua thời gian.

**Câu 5.** “Có nên che giấu tên `PBKDF2WithHmacSHA256` hoặc giá trị salt để chống lộ mật khẩu?”  
**Trả lời:** Không cần. Chúng được xem là thông tin công khai. An toàn phụ thuộc mật khẩu khó đoán, KDF được chọn/hiệu chuẩn và biện pháp bảo vệ dữ liệu/secret phụ trợ.

**Câu 6.** “Tôi dùng HMAC cho webhook. Payload cũ hợp lệ được gửi lại y hệt thì HMAC có chặn không?”  
**Trả lời:** Không. MAC vẫn hợp lệ trên thông điệp cũ. Nếu replay có hại, ký/xác thực cả timestamp, message ID hoặc sequence và kiểm tra giới hạn thời gian/dedupe ở bên nhận.

## 9. Những lỗi thường gặp

- Kiểm tra `SHA256(file)` bằng digest nằm trong cùng một phản hồi không đáng tin rồi kết luận file do đúng nhà phát hành tạo ra.
- Nghĩ tấn công thay `file + digest` đòi hỏi tìm va chạm SHA-256; thực ra chỉ cần tính digest của dữ liệu giả.
- Dùng `MessageDigest` trực tiếp làm password hash hoặc băm vài vòng tự chế rồi cho là password storage KDF.
- Dùng một salt cố định cho tất cả người dùng; lấy salt từ username, timestamp hoặc nguồn dễ đoán; hoặc coi salt là bí mật phải giấu.
- Cho rằng salt/pepper/MFA/rate limit có thể thay thế lẫn nhau. Chúng giải quyết những lớp đe dọa khác nhau.
- Dùng `SHA256(key || message)` tự chế thay HMAC; không bảo vệ key, không quản lý key rotation hoặc không kiểm soát replay.
- Dùng chữ ký số nhưng tải khóa công khai chưa xác thực từ cùng nguồn không đáng tin với file cần kiểm tra.
- Lưu plaintext password, log password, dùng Base64 như biện pháp bảo mật, giữ credential test hardcode trong production.
- Tạo record PBKDF2 nhưng không lưu salt/work factor/version; cố verify với salt mới; bỏ qua xử lý dữ liệu hỏng hoặc cost quá mức.
- Đưa toàn bộ mật khẩu yếu/compromised vào hệ thống và hy vọng KDF mạnh sẽ bù mọi rủi ro.

## 10. Checklist trước khi triển khai

**Đối với file/thông điệp:** xác định ai có thể sửa nội dung và digest; chọn expected digest đáng tin, HMAC hoặc chữ ký số; xác thực trust anchor; kiểm tra chính xác bytes/encoding và định dạng; bổ sung chống replay/rollback nếu cần.

**Đối với mật khẩu:** không lưu plaintext; sàng lọc mật khẩu yếu theo chính sách; dùng KDF đã được phân tích; sinh salt riêng; hiệu chuẩn cost; lưu schema/version/salt/cost/hash; so sánh an toàn; giới hạn thử online; kiểm soát quyền ghi DB; thiết kế nâng cấp/migration và bảo vệ pepper nếu có.

## Tài liệu đối chiếu

- [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): tính digest, `digest`, `isEqual`.
- [Java SE 21 — Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html): HMAC, `init` và `doFinal`.
- [Java SE 21 — Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): ký và kiểm tra chữ ký số.
- [Java SE 21 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html) và [PBEKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): tạo verifier PBKDF2 với salt và số vòng lặp.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id, scrypt, bcrypt, PBKDF2, salt, pepper, work factor, migration.
- [NIST SP 800-63B-4 — Password verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#verifierreq): bảo vệ password verifier khỏi tấn công offline, salt, cost và điều chỉnh theo thời gian.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): chọn cơ chế mật mã dựa trên mô hình đe dọa.

**Điểm cần nhớ:** digest công khai có ích để **so sánh với giá trị kỳ vọng đáng tin**; nó không tự xác thực tác giả khi cả dữ liệu và digest đều bị thay. Để xác thực nguồn, cần HMAC/chữ ký số với quản lý khóa phù hợp. Để bảo vệ mật khẩu yếu khỏi đoán offline, cần password hashing có salt và cost — và vẫn phải khuyến khích mật khẩu đủ mạnh.