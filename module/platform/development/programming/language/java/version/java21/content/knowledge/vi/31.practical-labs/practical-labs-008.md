# Thực hành KEM với provider và cặp khóa được hỗ trợ trên Java 21

Trong bài thực hành này, bạn sẽ dùng API `javax.crypto.KEM` của Java 21 để thiết lập một shared secret giữa hai phía. Bài lab khám phá security provider đang cung cấp thuật toán KEM, tạo cặp khóa X25519 bằng `KeyPairGenerator`, thực hiện encapsulation ở phía gửi và decapsulation ở phía nhận, sau đó xác minh hai phía thu được cùng secret.

Phạm vi module là `JAVA_VERSION_JAVA21` (Java 21), thuộc nội dung thực hành tổng hợp. Bài lab dùng thuật toán `DHKEM` với khóa X25519, một tổ hợp được hỗ trợ bởi provider chuẩn trong các bản OpenJDK/Oracle JDK 21 thông dụng. Provider KEM và provider tạo key pair có thể khác nhau; chương trình sẽ khám phá provider có service cần thiết thay vì giả định tất cả dịch vụ mật mã nằm trong cùng một provider. Nội dung chỉ sử dụng API ổn định của Java 21, không cần preview.

## Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

- Liệt kê security provider và tìm provider đăng ký service `KEM` với thuật toán `DHKEM`.
- Lấy một `KEM` instance từ provider cụ thể.
- Tạo cặp khóa X25519 bằng `KeyPairGenerator` và nhận biết provider tạo khóa.
- Dùng public key để encapsulate và nhận shared secret cùng encapsulation bytes.
- Dùng private key tương ứng để decapsulate và khôi phục shared secret.
- Kiểm tra hai secret giống nhau mà không ghi nội dung khóa ra log.
- Thử dùng private key không tương ứng để quan sát kết quả khác biệt.
- Nhận biết giới hạn của KEM: thiết lập secret không đồng nghĩa xác thực danh tính hoặc mã hóa payload.

## Điều kiện và cấu trúc bài lab

Bạn cần JDK 21 để biên dịch và chạy ví dụ. `javax.crypto.KEM` được cung cấp trong module `java.base`, vì vậy bài lab không cần thêm module hoặc thư viện bên ngoài.

Tạo file `KemProviderLab.java` với nội dung ở phần tiếp theo. Biên dịch bằng `javac --release 21` để xác nhận mã sử dụng API thuộc Java 21:

```bash
javac --release 21 KemProviderLab.java
java KemProviderLab
```

Không cần thêm `--enable-preview`. Nếu lệnh `javac` hoặc `java` đang trỏ tới JDK khác, kiểm tra `java -version` và `javac -version` trước khi chạy.

## Bước 1: Khám phá provider có hỗ trợ DHKEM

Java Security sử dụng provider để cung cấp implementation cho các API mật mã. `KEM.getInstance("DHKEM")` tìm implementation đã đăng ký; overload nhận `Provider` cho phép chọn rõ provider sau khi đã kiểm tra service.

Đoạn mã sau liệt kê provider có service KEM tên `DHKEM`:

```java
import java.security.Provider;
import java.security.Security;

for (Provider provider : Security.getProviders()) {
    Provider.Service service = provider.getService("KEM", "DHKEM");
    if (service != null) {
        System.out.println("DHKEM provider: " + provider.getName());
        System.out.println("Implementation: " + service.getClassName());
    }
}
```

Trên các bản OpenJDK/Oracle JDK 21 thông dụng, `SunJCE` cung cấp service `DHKEM`. Kết quả thực tế phụ thuộc JDK build và provider đã cài đặt. Nếu không có provider nào xuất hiện, không được giả định thuật toán tự động có sẵn; cần kiểm tra runtime hoặc cài provider đã được tổ chức phê duyệt.

Provider cung cấp KEM không nhất thiết là provider tạo cặp khóa. Ví dụ, `DHKEM` có thể đến từ `SunJCE`, trong khi `KeyPairGenerator` cho `X25519` thường đến từ `SunEC`. Chương trình phải ghi nhận riêng hai provider.

## Bước 2: Chạy chương trình encapsulate/decapsulate hoàn chỉnh

Tạo file `KemProviderLab.java`:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Provider;
import java.security.Security;
import java.util.Arrays;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class KemProviderLab {
    public static void main(String[] args) throws Exception {
        Provider kemProvider = findProvider("KEM", "DHKEM");
        KEM kem = KEM.getInstance("DHKEM", kemProvider);

        KeyPairGenerator keyPairGenerator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeyPair = keyPairGenerator.generateKeyPair();

        // Phía gửi: dùng public key của người nhận để encapsulate.
        KEM.Encapsulated encapsulated = kem
                .newEncapsulator(recipientKeyPair.getPublic())
                .encapsulate();

        SecretKey senderSecret = encapsulated.key();
        byte[] encapsulation = encapsulated.encapsulation();

        // Phía nhận: dùng private key tương ứng để decapsulate.
        SecretKey recipientSecret = kem
                .newDecapsulator(recipientKeyPair.getPrivate())
                .decapsulate(encapsulation);

        // Chỉ export trong bài lab để kiểm tra hai phía có cùng secret.
        byte[] senderBytes = exportForLab(senderSecret);
        byte[] recipientBytes = exportForLab(recipientSecret);
        boolean sameSecret = MessageDigest.isEqual(senderBytes, recipientBytes);

        if (!sameSecret) {
            throw new IllegalStateException("Hai phía không tạo cùng shared secret");
        }

        System.out.println("KEM algorithm: " + kem.getAlgorithm());
        System.out.println("KEM provider: " + kem.getProvider().getName());
        System.out.println("KeyPairGenerator: " + keyPairGenerator.getAlgorithm());
        System.out.println("KeyPair provider: " + keyPairGenerator.getProvider().getName());
        System.out.println("Recipient public key algorithm: "
                + recipientKeyPair.getPublic().getAlgorithm());
        System.out.println("Encapsulation length: " + encapsulation.length);
        System.out.println("Shared secrets match: " + sameSecret);

        // Thử decapsulate bằng một private key X25519 khác.
        KeyPair unrelatedKeyPair = keyPairGenerator.generateKeyPair();
        SecretKey unrelatedSecret = kem
                .newDecapsulator(unrelatedKeyPair.getPrivate())
                .decapsulate(encapsulation);

        boolean unrelatedSecretMatches = MessageDigest.isEqual(
                senderBytes, exportForLab(unrelatedSecret));
        System.out.println("Unrelated private key matches: " + unrelatedSecretMatches);

        if (unrelatedSecretMatches) {
            throw new IllegalStateException("Kết quả thử nghiệm không như mong đợi");
        }

        // Không in senderBytes, recipientBytes hoặc nội dung SecretKey.
        Arrays.fill(senderBytes, (byte) 0);
        Arrays.fill(recipientBytes, (byte) 0);
    }

    private static Provider findProvider(String type, String algorithm)
            throws NoSuchAlgorithmException {
        return Arrays.stream(Security.getProviders())
                .filter(provider -> provider.getService(type, algorithm) != null)
                .findFirst()
                .orElseThrow(() -> new NoSuchAlgorithmException(
                        "Không có provider hỗ trợ " + type + "/" + algorithm));
    }

    private static byte[] exportForLab(SecretKey key) {
        byte[] encoded = key.getEncoded();
        if (encoded == null) {
            throw new IllegalStateException(
                    "Provider không cho export secret; dùng cách kiểm tra phù hợp provider");
        }
        return encoded;
    }
}
```

Chương trình thực hiện các thao tác sau:

1. Tìm provider có service `KEM/DHKEM` và tạo KEM instance từ provider đó.
2. Tạo cặp khóa X25519 của người nhận.
3. Người gửi gọi `newEncapsulator(publicKey).encapsulate()` để nhận `SecretKey` và encapsulation bytes.
4. Người nhận gọi `newDecapsulator(privateKey).decapsulate(encapsulation)` để khôi phục secret.
5. So sánh hai bản mã hóa của secret bằng `MessageDigest.isEqual()`.
6. Thử dùng một private key X25519 khác; secret thu được phải khác secret ban đầu.

`getEncoded()` chỉ được dùng trong bài lab để xác minh hai phía. Trong production, hạn chế export shared secret; dùng `SecretKey` trực tiếp làm đầu vào cho bước dẫn xuất khóa hoặc API mật mã phù hợp. Không ghi secret, private key hoặc byte array của khóa ra console, log hay telemetry.

## Bước 3: Đọc kết quả chạy

Kết quả điển hình trên một bản JDK 21 có provider chuẩn hỗ trợ DHKEM có dạng:

```text
KEM algorithm: DHKEM
KEM provider: SunJCE
KeyPairGenerator: X25519
KeyPair provider: SunEC
Recipient public key algorithm: XDH
Encapsulation length: <độ dài do provider trả về>
Shared secrets match: true
Unrelated private key matches: false
```

Tên provider và tên thuật toán của public key cần được đọc từ runtime thực tế. `XDH` là tên thuật toán khóa có thể được trả về bởi implementation dù generator được yêu cầu bằng tên `X25519`. Độ dài encapsulation không nên hard-code vào test tổng quát; nó phụ thuộc thuật toán và định dạng được provider hỗ trợ.

Nếu chương trình báo không tìm thấy provider, kiểm tra danh sách `Security.getProviders()` và service `KEM/DHKEM`. Nếu provider tìm thấy nhưng `newEncapsulator()` báo khóa không hợp lệ, kiểm tra loại public key và tổ hợp thuật toán mà provider hỗ trợ. Không thay khóa bằng một loại khác một cách ngẫu nhiên; phải chọn cặp khóa nằm trong tập được provider hỗ trợ.

## Bước 4: Hiểu vai trò của public key và private key

Trong KEM:

- Người nhận tạo cặp khóa và giữ private key bí mật.
- Người nhận phân phối public key qua một kênh có xác thực.
- Người gửi dùng public key để encapsulate, tạo shared secret và encapsulation bytes.
- Người gửi chuyển encapsulation bytes cho người nhận.
- Người nhận dùng private key tương ứng để decapsulate và thu được shared secret.

Encapsulation bytes không phải private key và không cần giữ bí mật, nhưng cần được chuyển nguyên vẹn theo định dạng giao thức. Private key phải được bảo vệ theo chính sách quản lý khóa của ứng dụng.

Thí nghiệm với private key không tương ứng cho thấy KEM không tự xác thực danh tính người nhận. Một decapsulation bằng khóa khác có thể vẫn trả về một secret khác thay vì báo lỗi xác thực. Vì vậy, ứng dụng phải xác thực public key trước khi encapsulate; không được coi việc decapsulation không ném exception là bằng chứng peer đúng danh tính.

## Bước 5: Kiểm tra lỗi provider và khóa không tương thích

Thực hiện lần lượt các thay đổi sau và ghi lại loại lỗi thực tế:

| Thử nghiệm | Cách thực hiện | Điều cần quan sát |
| --- | --- | --- |
| Thuật toán KEM không có provider | Thử `KEM.getInstance()` với tên service không được đăng ký | `NoSuchAlgorithmException` |
| Không có generator X25519 | Thử `KeyPairGenerator.getInstance("X25519")` trên runtime không hỗ trợ | `NoSuchAlgorithmException` |
| Khóa không thuộc thuật toán được KEM hỗ trợ | Truyền một public key không tương thích vào `newEncapsulator()` | Lỗi khóa không hợp lệ theo provider/API |
| Private key khác cặp | Decapsulate encapsulation bằng private key X25519 độc lập | Có thể nhận secret khác; không xem đây là xác thực thất bại |
| Encapsulation sai định dạng | Thay đổi hoặc cắt ngắn byte array trước decapsulation | Provider từ chối dữ liệu không hợp lệ bằng lỗi decapsulation tương ứng |

Không phụ thuộc vào exception message vì nội dung có thể thay đổi theo JDK hoặc provider. Test nên kiểm tra loại exception/cause theo hợp đồng API và không khẳng định một provider phải xử lý mọi dữ liệu hỏng giống hệt provider khác.

## Bước 6: Thực hành chọn provider tường minh

Trong chương trình chính, `findProvider()` tìm provider đầu tiên có service `KEM/DHKEM`. Khi triển khai, có thể chọn provider theo tên đã được tổ chức phê duyệt:

```java
Provider approvedProvider = Security.getProvider("SunJCE");
if (approvedProvider == null
        || approvedProvider.getService("KEM", "DHKEM") == null) {
    throw new NoSuchAlgorithmException("Provider không cung cấp DHKEM");
}

KEM kem = KEM.getInstance("DHKEM", approvedProvider);
```

Đoạn mã này minh họa việc chọn provider theo chính sách. Nếu ứng dụng chạy trên JDK hoặc môi trường có provider khác, hãy thay tên bằng provider đã kiểm tra và phê duyệt. Không tự động thêm provider lạ vào production chỉ để làm cho ví dụ chạy được.

Provider dùng để tạo khóa có thể được chọn độc lập:

```java
KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");
System.out.println(keyPairGenerator.getProvider().getName());
```

Điều quan trọng là public/private key phải tương thích với KEM implementation; không bắt buộc KEM provider và KeyPairGenerator provider phải cùng tên.

## Bước 7: Bài tập mở rộng

1. **Liệt kê provider:** in tất cả provider có service `KEM/DHKEM`, ghi lại tên và class implementation.
2. **Chọn provider cụ thể:** sửa chương trình để nhận tên provider qua tham số dòng lệnh và báo lỗi rõ khi provider không tồn tại hoặc không hỗ trợ DHKEM.
3. **Tách hai phía:** viết hai phương thức `encapsulate(PublicKey)` và `decapsulate(PrivateKey, byte[])`; chỉ chuyển encapsulation bytes giữa hai phương thức.
4. **Kiểm tra key mismatch:** tạo thêm một cặp X25519 độc lập và xác nhận secret decapsulate không bằng secret của người gửi.
5. **Kiểm tra dữ liệu encapsulation lỗi:** thay đổi một byte hoặc cắt ngắn dữ liệu; ghi nhận lỗi do provider trả về, không phụ thuộc message.
6. **Kiểm tra hỗ trợ khóa:** nếu provider tài liệu hóa thêm loại khóa DHKEM khác, tạo test riêng cho từng loại và chỉ ghi nhận những tổ hợp đã chạy thành công.
7. **Viết test JUnit:** kiểm tra hai secret trùng nhau, key mismatch tạo secret khác, provider không tồn tại và encapsulation malformed bị từ chối.

## Ranh giới bảo mật cần giữ

Ví dụ dùng DHKEM với X25519 để minh họa API KEM và việc provider hỗ trợ một cặp khóa cụ thể. X25519 là cơ chế Diffie–Hellman cổ điển, không phải KEM hậu lượng tử. Việc Java 21 có `KEM` API không làm cho mọi thuật toán KEM trở thành post-quantum; nếu yêu cầu ML-KEM, phải xác minh provider cài đặt thực sự cung cấp thuật toán và bộ tham số tương ứng trên runtime triển khai.

KEM cũng không phải thuật toán mã hóa payload và không xác thực public key. Trong ứng dụng thực tế, quy trình bảo mật cần có:

- Cơ chế xác thực public key/peer, chẳng hạn chứng thư hoặc giao thức handshake đã được chuẩn hóa.
- KDF để dẫn xuất khóa từ shared secret theo context của phiên.
- AEAD như AES-GCM hoặc ChaCha20-Poly1305 để bảo vệ dữ liệu ứng dụng.
- Quản lý nonce, rotation, private key, lỗi decapsulation và downgrade theo giao thức.

Không tự thiết kế giao thức mật mã bằng cách gửi shared secret hoặc nối byte tùy ý vào khóa mã hóa. Ưu tiên giao thức chuẩn hóa và provider đã được đánh giá.

## Tiêu chí hoàn thành

- [ ] Chương trình chạy bằng JDK 21 mà không bật preview.
- [ ] Tìm và in được provider hỗ trợ `KEM/DHKEM`.
- [ ] Tạo được cặp khóa X25519 từ `KeyPairGenerator` được runtime hỗ trợ.
- [ ] Encapsulate bằng public key và nhận được encapsulation bytes cùng `SecretKey`.
- [ ] Decapsulate bằng private key tương ứng.
- [ ] Xác minh hai phía có cùng shared secret mà không in nội dung secret.
- [ ] Thử private key khác và quan sát secret không khớp.
- [ ] Giải thích được provider KEM và provider tạo key pair có thể khác nhau.
- [ ] Giải thích được DHKEM/X25519 là cổ điển và KEM không tự xác thực peer hoặc mã hóa payload.

## Tài liệu tham khảo

- [Oracle Java 21 API: KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Oracle Java 21 API: KEM.Encapsulated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html)
- [Oracle Java 21 API: KeyPairGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyPairGenerator.html)
- [Oracle Java 21 API: Provider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Provider.html)
- [JEP 452: Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
