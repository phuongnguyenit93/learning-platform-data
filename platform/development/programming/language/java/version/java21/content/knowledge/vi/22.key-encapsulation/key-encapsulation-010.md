# Quản lý SecureRandom, private key và dữ liệu nhạy cảm trong kiểm thử

Trong Key Encapsulation Mechanism (KEM), bên gửi dùng public key của bên nhận để tạo một shared secret cùng dữ liệu encapsulation; bên nhận dùng private key tương ứng để khôi phục cùng shared secret. Độ an toàn của quy trình phụ thuộc vào chất lượng nguồn ngẫu nhiên, cách bảo vệ private key và việc xử lý shared secret trong suốt vòng đời ứng dụng.

Kiểm thử KEM cần xác nhận việc encapsulate/decapsulate và xử lý lỗi mà không đưa khóa production hoặc secret thật vào test fixture, log hay kho mã nguồn. Java 21 cung cấp `SecureRandom`, KeyStore API và KEM API chuẩn hóa; thuật toán KEM cụ thể vẫn phụ thuộc provider được cài đặt. Bài viết tập trung vào cách quản lý key material và dữ liệu nhạy cảm trong Java 21, đồng thời chỉ ra những giới hạn không thể giải quyết chỉ bằng cách xóa một mảng byte.

## 1. Phân biệt các loại dữ liệu trong KEM

Khi làm việc với KEM, không phải dữ liệu nào liên quan đến khóa cũng có cùng mức độ bí mật:

| Dữ liệu | Vai trò | Cách xử lý |
|---|---|---|
| Public key | Dùng để encapsulate shared secret cho bên nhận | Có thể phân phối công khai; vẫn cần xác thực nguồn gốc và gắn đúng danh tính/thuật toán |
| Private key | Dùng để decapsulate dữ liệu encapsulation | Phải được bảo vệ như bí mật mật mã; giới hạn quyền truy cập và export |
| Encapsulation | Dữ liệu bên gửi chuyển cho bên nhận để decapsulate | Thường không phải secret; cần bảo vệ tính toàn vẹn và gắn đúng phiên/giao thức |
| Shared secret | Bí mật chung được tạo ra ở cả hai phía | Không log hoặc ghi ra file; dùng cho KDF/giao thức mật mã tiếp theo |
| Seed và trạng thái của SecureRandom | Vật liệu góp phần tạo số ngẫu nhiên | Không cố định trong production, không log hoặc chia sẻ như dữ liệu kiểm thử |
| Password bảo vệ keystore | Cho phép mở kho hoặc truy cập private key | Lấy từ secret manager, tránh hard-code và xóa bản sao trong bộ nhớ khi có thể |

KEM chỉ thiết lập shared secret và dữ liệu encapsulation. Nó không tự định nghĩa toàn bộ giao thức xác thực peer, phân phối public key, dẫn xuất khóa ứng dụng hay mã hóa dữ liệu. Ứng dụng cần dùng một giao thức đã được thiết kế và kiểm chứng, kết hợp KEM với KDF và cơ chế mã hóa/xác thực phù hợp.

## 2. Dùng SecureRandom cho key generation và encapsulation

`java.security.SecureRandom` là API tạo số ngẫu nhiên phù hợp cho mục đích mật mã. Khi tạo key pair hoặc thực hiện thao tác mật mã cần randomness, hãy dùng `SecureRandom` thay vì `java.util.Random`, `ThreadLocalRandom`, timestamp hoặc bộ sinh số tự viết.

Ví dụ tạo một nguồn ngẫu nhiên:

```java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
```

Constructor mặc định yêu cầu provider cung cấp một nguồn ngẫu nhiên được seed theo cơ chế của môi trường. Thông thường, ứng dụng không cần tự tạo seed từ thời gian hoặc dữ liệu request.

Khi cần chọn thuật toán/provider cụ thể, có thể dùng `getInstance`:

```java
SecureRandom secureRandom = SecureRandom.getInstance("DRBG");
```

`DRBG` là tên thuật toán SecureRandom được hỗ trợ trong các JDK/provider hiện đại, nhưng lựa chọn thực tế cần tuân theo provider, cấu hình và chính sách bảo mật của môi trường triển khai. Không nên hard-code giả định về provider nếu ứng dụng phải chạy trên nhiều JDK hoặc HSM khác nhau.

### Không cố định seed trong production

Không làm như sau:

```java
SecureRandom random = new SecureRandom();
random.setSeed(123456789L); // Không dùng giá trị cố định làm nguồn entropy
```

Không dùng giá trị cố định hoặc entropy thấp làm nguồn seed cho khóa production. `setSeed` bổ sung dữ liệu seed theo implementation; nó không phải API reset một `SecureRandom` về trạng thái deterministic. Tuy nhiên, tự cung cấp seed không đủ entropy có thể làm suy yếu nguồn ngẫu nhiên, đặc biệt nếu implementation chưa tự seed. Không tạo seed từ `System.currentTimeMillis()`, request ID, UUID tự chế hoặc dữ liệu dễ dự đoán. Nếu cần kiểm thử có thể tái lập, hãy dùng known-answer test vectors thay vì điều khiển seed của nguồn ngẫu nhiên production.

`SecureRandom.getInstanceStrong()` chọn một thuật toán từ cấu hình `securerandom.strongAlgorithms`. Lựa chọn đó có thể có hành vi hiệu năng hoặc blocking khác với `new SecureRandom()`. Không dùng `getInstanceStrong()` một cách máy móc trong mỗi request; chỉ chọn khi yêu cầu bảo mật và đặc tính vận hành của provider đã được đánh giá.

### Truyền SecureRandom cho KeyPairGenerator

Khi API tạo khóa cho phép nhận `SecureRandom`, hãy truyền nguồn ngẫu nhiên rõ ràng:

```java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.AlgorithmParameterSpec;

static KeyPair generateKeyPair(
        String keyAlgorithm,
        AlgorithmParameterSpec parameters,
        SecureRandom random) throws GeneralSecurityException {

    KeyPairGenerator generator = KeyPairGenerator.getInstance(keyAlgorithm);
    generator.initialize(parameters, random);
    return generator.generateKeyPair();
}
```

`keyAlgorithm` và `parameters` phải phù hợp với KEM algorithm và provider đang sử dụng. Không có một key size hoặc `AlgorithmParameterSpec` chung cho mọi KEM. Hãy lấy cấu hình từ tiêu chuẩn thuật toán và tài liệu provider, không tự chọn tham số chỉ vì ví dụ của thuật toán khác sử dụng được.

`SecureRandom` được thiết kế để an toàn khi nhiều thread cùng sử dụng. Có thể quản lý một instance dùng chung trong phạm vi ứng dụng nếu provider và workload phù hợp. Không cần tạo một `SecureRandom` mới cho mỗi request chỉ để tránh chia sẻ; nếu cần tối ưu, hãy đo trên provider thực tế.

## 3. Thuật toán KEM phụ thuộc provider

Java 21 chuẩn hóa API `javax.crypto.KEM` để ứng dụng gọi thao tác encapsulation và decapsulation theo một giao diện thống nhất. API không có nghĩa mọi thuật toán KEM đều được cung cấp bởi mọi JDK hoặc provider.

Ví dụ dưới đây minh họa luồng API; `kemAlgorithm` phải là tên thuật toán mà provider được triển khai hỗ trợ:

```java
import javax.crypto.KEM;
import javax.crypto.SecretKey;
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;

static void encapsulateAndDecapsulate(
        String kemAlgorithm,
        PublicKey recipientPublicKey,
        PrivateKey recipientPrivateKey,
        SecureRandom random) throws GeneralSecurityException {

    KEM kem = KEM.getInstance(kemAlgorithm);

    KEM.Encapsulated encapsulated =
            kem.newEncapsulator(recipientPublicKey, random).encapsulate();

    byte[] encapsulation = encapsulated.encapsulation();
    SecretKey senderSecret = encapsulated.key();

    SecretKey receiverSecret = kem.newDecapsulator(recipientPrivateKey)
            .decapsulate(encapsulation);

    // Sử dụng senderSecret và receiverSecret trong kiểm tra hoặc giao thức.
}
```

Đoạn mã chỉ minh họa API. Ứng dụng thực tế cần kiểm tra thuật toán/provider, tham số, định dạng encapsulation, KDF và cách sử dụng shared secret theo giao thức. Nếu provider không hỗ trợ thuật toán yêu cầu, `KEM.getInstance` có thể ném `NoSuchAlgorithmException`; không nên âm thầm chuyển sang một thuật toán yếu hoặc không tương thích.

Không suy luận rằng một thuật toán hậu lượng tử cụ thể đã có sẵn trong JDK 21 chỉ vì API KEM đã được chuẩn hóa. Thuật toán và provider cần được kiểm tra trên runtime thực tế; các thuật toán được bổ sung trong JDK hoặc provider mới hơn không mặc nhiên tồn tại trong Java 21.

## 4. Bảo vệ private key trong ứng dụng

Private key là dữ liệu nhạy cảm nhất trong quy trình decapsulation. Nếu kẻ tấn công lấy được private key, họ có thể giải mã/khôi phục shared secret cho các encapsulation tương ứng theo khả năng của thuật toán và giao thức.

Các nguyên tắc cơ bản:

1. **Giới hạn quyền truy cập:** chỉ thành phần cần decapsulate mới được phép sử dụng private key.
2. **Không hard-code:** không đặt private key hoặc password trong source code, file cấu hình được commit hay test resource công khai.
3. **Bảo vệ khi lưu trữ:** dùng KeyStore được bảo vệ, HSM hoặc dịch vụ quản lý khóa phù hợp với yêu cầu triển khai.
4. **Hạn chế export:** nếu provider/HSM hỗ trợ private key không exportable, ưu tiên giữ thao tác trong boundary bảo mật.
5. **Tách môi trường:** development, test, staging và production dùng key riêng, không chia sẻ private key production với CI.
6. **Có vòng đời:** định nghĩa tạo, phân phối, rotation, thu hồi, backup và xử lý khi key bị lộ.

`PrivateKey` là một đối tượng API, không đồng nghĩa private key luôn được lưu dưới dạng byte array mà ứng dụng có thể đọc. Provider có thể giữ key material trong đối tượng opaque hoặc thiết bị phần cứng. Không gọi `getEncoded()` chỉ để log, debug hoặc kiểm tra; phương thức này có thể trả encoded key material nếu provider cho phép export.

`PrivateKey` cũng kế thừa hợp đồng `Destroyable`. Có thể yêu cầu implementation hủy key bằng `destroy()` khi vòng đời kết thúc, nhưng provider có thể không hỗ trợ việc hủy hoặc chỉ có thể thực hiện ở mức best effort. Không xem lời gọi này là bảo đảm xóa mọi bản sao trong bộ nhớ; vẫn cần bảo vệ key trong storage và giới hạn quyền truy cập.

### Lưu khóa trong KeyStore

Khi cần lưu private key có thể export, dùng KeyStore với quyền truy cập và password được quản lý riêng. PKCS#12 là một định dạng keystore phổ biến được Java hỗ trợ:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;

static PrivateKey loadPrivateKey(
        Path keyStorePath,
        char[] storePassword,
        char[] keyPassword,
        String alias) throws Exception {

    KeyStore keyStore = KeyStore.getInstance("PKCS12");
    try (InputStream input = Files.newInputStream(keyStorePath)) {
        keyStore.load(input, storePassword);
    }

    return (PrivateKey) keyStore.getKey(alias, keyPassword);
}
```

Ví dụ này giả định file và password đã được cung cấp an toàn; trong production, file keystore cần quyền filesystem hạn chế và password nên lấy từ secret manager hoặc cơ chế bảo vệ tương đương. Với HSM hoặc PKCS#11, private key có thể không exportable và thao tác được thực hiện qua provider tương ứng.

Password nên được truyền dưới dạng `char[]` khi API hỗ trợ, tránh tạo thêm `String` bất biến chứa secret. Sau khi dùng xong, xóa các bản sao `char[]` do ứng dụng quản lý bằng `Arrays.fill`. Việc này chỉ là best effort vì provider, thư viện hoặc runtime có thể đã tạo bản sao khác.

## 5. Quản lý shared secret sau decapsulation

Shared secret từ KEM phải được xem là key material nhạy cảm. Không in ra console, log, assertion message, exception message, test report hoặc tracing attribute.

Trong một giao thức hoàn chỉnh, shared secret thường được đưa qua KDF đã được chuẩn hóa/kiểm chứng để tạo khóa cho mục đích cụ thể. Không dùng trực tiếp một shared secret cho nhiều mục đích không liên quan, không tự chế KDF bằng cách nối chuỗi hoặc hash tùy tiện. Việc lựa chọn KDF, context binding, salt và thông tin phiên phải theo đặc tả giao thức.

Các nguyên tắc:

- Chỉ giữ shared secret trong phạm vi cần thiết.
- Không ghi raw secret vào file tạm, database hoặc fixture.
- Không dùng shared secret làm password hoặc token loggable.
- Không tái sử dụng secret giữa test case hoặc session không liên quan.
- Dùng API/provider phù hợp để dẫn xuất hoặc tiêu thụ key material.
- Xóa các bản sao byte có thể truy cập khi không còn cần thiết, nhưng không xem thao tác này là bảo đảm xóa mọi bản sao trong bộ nhớ.

Một số `SecretKey` có thể là opaque và `getEncoded()` trả `null`. Điều này có thể là chủ đích của provider để không cho ứng dụng export raw key bytes. Đừng ép chuyển key opaque thành byte array bằng cách thay provider hoặc xuất khóa ra ngoài chỉ để thuận tiện cho test.

## 6. Sinh key pair tạm thời cho kiểm thử

Test chức năng nên dùng key pair riêng cho test, được tạo trong lúc chạy hoặc lấy từ test vector được công bố. Không dùng private key production để làm test fixture.

Một test có thể tạo key pair tạm thời ở phần setup:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.AlgorithmParameterSpec;

final class KemTestSupport {
    private final SecureRandom random = new SecureRandom();

    KeyPair newTestKeyPair(
            String keyAlgorithm,
            AlgorithmParameterSpec parameters) throws Exception {

        KeyPairGenerator generator = KeyPairGenerator.getInstance(keyAlgorithm);
        generator.initialize(parameters, random);
        return generator.generateKeyPair();
    }
}
```

`keyAlgorithm` và parameters ở đây là cấu hình test của provider được chọn. Nếu thuật toán/provider yêu cầu tham số khác, hãy dùng cấu hình chính xác của provider đó. Không sao chép một bộ tham số từ thuật toán khác.

Sinh key pair tạm thời giúp mỗi test độc lập và giảm nguy cơ key fixture bị dùng nhầm trong môi trường thật. Nếu chi phí sinh key lớn, có thể tạo một key pair cho mỗi test class hoặc suite theo chiến lược isolation đã chọn, nhưng không chia sẻ mutable state hoặc secret giữa test chạy song song nếu không cần thiết.

## 7. Kiểm thử round-trip encapsulation và decapsulation

Một kiểm thử chức năng cơ bản xác nhận bên gửi và bên nhận tạo được cùng shared secret từ cùng một cặp khóa và dữ liệu encapsulation.

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.security.MessageDigest;
import java.security.KeyPair;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

static void assertKemRoundTrip(
        String kemAlgorithm,
        KeyPair recipientKeyPair,
        SecureRandom random) throws Exception {

    KEM kem = KEM.getInstance(kemAlgorithm);
    KEM.Encapsulated encapsulated = kem
            .newEncapsulator(recipientKeyPair.getPublic(), random)
            .encapsulate();

    SecretKey senderSecret = encapsulated.key();
    SecretKey receiverSecret = kem
            .newDecapsulator(recipientKeyPair.getPrivate())
            .decapsulate(encapsulated.encapsulation());

    byte[] senderBytes = senderSecret.getEncoded();
    byte[] receiverBytes = receiverSecret.getEncoded();

    try {
        assertNotNull(senderBytes, "Test provider must expose test key bytes");
        assertNotNull(receiverBytes, "Test provider must expose test key bytes");
        assertTrue(MessageDigest.isEqual(senderBytes, receiverBytes));
    } finally {
        if (senderBytes != null) {
            Arrays.fill(senderBytes, (byte) 0);
        }
        if (receiverBytes != null) {
            Arrays.fill(receiverBytes, (byte) 0);
        }
    }
}
```

Đây là test helper dành cho provider test có `SecretKey` exportable. `getEncoded()` có thể trả `null` với key opaque/non-exportable; khi đó hãy kiểm thử bằng cách dùng key trong một thao tác mật mã downstream phù hợp thay vì buộc export key.

`Arrays.fill` xóa hai bản sao byte do test lấy ra, không bảo đảm xóa bản sao nội bộ của provider, đối tượng `SecretKey`, heap dump hoặc bản sao do runtime/JIT tạo. Không ghi các mảng này ra log kể cả khi assertion thất bại.

## 8. Test vector và tính tái lập

Không nên cố định seed của `SecureRandom` trong test thông thường chỉ để kết quả key pair hoặc encapsulation giống nhau qua mỗi lần chạy. Test chức năng nên kiểm tra thuộc tính cần thiết như round-trip thành công, xử lý sai key, lỗi tham số và hành vi provider; không nên phụ thuộc vào byte ngẫu nhiên cụ thể nếu đặc tả không yêu cầu.

Khi cần kết quả xác định để kiểm thử thuật toán, hãy dùng known-answer test vectors do tiêu chuẩn hoặc nhà cung cấp thuật toán công bố. Test vector phải ghi rõ thuật toán, phiên bản, tham số, provider hoặc implementation cần kiểm tra. Không tạo một PRNG tự chế hay dùng `Random` làm nguồn ngẫu nhiên cho test rồi vô tình tái sử dụng trong production.

Nếu ứng dụng cần injection để test, có thể truyền `SecureRandom` qua constructor hoặc factory thay vì khởi tạo nó sâu bên trong lớp:

```java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.AlgorithmParameterSpec;
import java.util.Objects;

final class KeyMaterialFactory {
    private final SecureRandom random;

    KeyMaterialFactory(SecureRandom random) {
        this.random = Objects.requireNonNull(random);
    }

    KeyPair generate(
            String algorithm,
            AlgorithmParameterSpec parameters) throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance(algorithm);
        generator.initialize(parameters, random);
        return generator.generateKeyPair();
    }
}
```

Trong production, inject `SecureRandom` được provider cấu hình đúng. Trong test, dùng test vector hoặc một test provider có tài liệu rõ ràng nếu cần deterministic behavior. Không cho phép cấu hình deterministic random lọt vào artifact hoặc profile production.

## 9. Kiểm thử lỗi và key không hợp lệ

Ngoài round-trip thành công, nên kiểm tra các điều kiện lỗi:

- Public key không đúng thuật toán hoặc không được provider hỗ trợ.
- Private key không tương ứng với public key đã encapsulate.
- Encapsulation bị cắt ngắn hoặc thay đổi.
- Provider không hỗ trợ tham số hoặc key format yêu cầu.
- KeyStore thiếu alias, password sai hoặc key entry không phải private key.
- SecretKey không exportable nhưng test lại cố gọi `getEncoded()`.

Không giả định mọi KEM phải báo lỗi giống nhau khi encapsulation không hợp lệ. Một số thiết kế có thể dùng implicit rejection và trả ra secret không đúng thay vì ném exception dễ phân biệt. Test nên theo đặc tả thuật toán/provider và kiểm tra kết quả của giao thức phía trên, chẳng hạn bước xác thực/mã hóa có thể phát hiện hai bên không có cùng secret.

Với kiểm thử sai private key, không chỉ assert rằng `decapsulate()` phải ném exception. Hãy xác định hành vi được đặc tả cho thuật toán đang dùng; nếu thuật toán không cam kết exception, hãy kiểm tra rằng secret không hợp lệ không thể hoàn tất bước xác thực tiếp theo của giao thức.

## 10. Bảo vệ secret trong test code và CI

Test code thường chạy trong môi trường có log chi tiết, báo cáo lỗi, artifact và dump khi tiến trình thất bại. Vì vậy, dữ liệu kiểm thử cũng cần được quản lý cẩn thận.

Không nên:

- Commit private key production, shared secret hoặc password vào repository.
- Đưa key bytes vào tên test, assertion message, console output hoặc snapshot.
- Dùng chung key của production, staging và CI.
- Đính kèm heap dump hoặc test artifact có key material vào ticket công khai.
- Đưa private key hoặc shared secret vào system property/command line, vì có thể bị lộ qua process listing hoặc log hệ thống.
- Ghi raw `getEncoded()` ra file để so sánh giữa các lần chạy.

Nên:

1. Sinh key tạm thời cho test hoặc dùng fixture chỉ dành riêng cho test.
2. Dùng secret manager/CI secret store cho credential cần thiết của integration test.
3. Giới hạn quyền đọc test secret và xoay vòng nếu nghi ngờ bị lộ.
4. Ghi log key alias, key ID, thuật toán, provider, trạng thái và request ID thay vì nội dung key.
5. Làm sạch byte array/char array mà test tự tạo khi đã dùng xong.
6. Kiểm soát quyền truy cập và thời gian lưu của log, crash dump và CI artifact.

## 11. Xóa dữ liệu nhạy cảm khỏi bộ nhớ: giới hạn thực tế

Java có garbage collector và runtime có thể tạo bản sao dữ liệu trong quá trình xử lý. Vì vậy, không thể bảo đảm xóa toàn bộ private key hoặc shared secret khỏi bộ nhớ chỉ bằng `Arrays.fill` một mảng.

Nếu ứng dụng có byte array do chính nó quản lý, có thể ghi đè khi không còn cần:

```java
byte[] secretCopy = secretKey.getEncoded();
if (secretCopy != null) {
    try {
        useSecretCopy(secretCopy);
    } finally {
        Arrays.fill(secretCopy, (byte) 0);
    }
}
```

Đây là biện pháp giảm thời gian tồn tại của bản sao có thể truy cập, không phải bảo đảm zeroization tuyệt đối. `getEncoded()` có thể trả `null`, tạo một bản sao khác hoặc provider có thể giữ key material ở vùng nhớ riêng. JIT, garbage collector, heap dump và thư viện native cũng ảnh hưởng đến khả năng xóa thực tế.

Với key material có yêu cầu bảo vệ cao, ưu tiên provider/HSM hỗ trợ non-exportable key và thao tác mật mã bên trong boundary bảo mật. Tránh export private key hoặc shared secret ra heap ứng dụng nếu không cần.

## 12. Kiểm tra provider và cấu hình runtime

Kết quả kiểm thử KEM phụ thuộc provider. Một test chạy được trên máy developer có provider bên thứ ba không chứng minh runtime production đã cài cùng provider hoặc cùng thuật toán.

Trong kiểm thử tích hợp, nên ghi nhận metadata không nhạy cảm:

- Tên thuật toán KEM được yêu cầu.
- Tên provider thực tế được chọn.
- Phiên bản JDK/runtime.
- Loại key và tham số theo API công khai.
- Kết quả khởi tạo, encapsulate, decapsulate và xác thực giao thức.

Không log private key, shared secret, seed hoặc byte array encapsulation nếu giao thức coi metadata đó là nhạy cảm. Public encapsulation thường được gửi qua mạng, nhưng vẫn cần bảo vệ tính toàn vẹn và gắn với đúng session/peer để ngăn việc tráo đổi hoặc replay ở tầng giao thức.

Không tự động fallback sang provider hoặc thuật toán khác khi provider dự kiến không tồn tại. Thay đổi thuật toán có thể phá tương thích giao thức và chính sách bảo mật. Hãy fail fast khi thuật toán/provider bắt buộc không có, rồi sửa cấu hình triển khai một cách có kiểm soát.

## 13. Quy trình kiểm thử khuyến nghị

Một bộ test KEM có thể được tổ chức theo các bước:

1. Chọn provider và thuật toán được hỗ trợ trên runtime test.
2. Tạo `SecureRandom` theo cấu hình provider, không seed cố định.
3. Sinh key pair tạm thời dành riêng cho test.
4. Encapsulate bằng public key và giữ encapsulation cùng sender secret trong phạm vi test.
5. Decapsulate bằng private key và thu receiver secret.
6. Xác nhận hai phía có cùng secret bằng cách so sánh an toàn nếu key exportable, hoặc bằng thao tác mật mã downstream nếu key opaque.
7. Kiểm thử sai key, dữ liệu encapsulation không hợp lệ, provider không hỗ trợ và lỗi KeyStore.
8. Không ghi secret vào log; dọn các bản sao byte/char mà test sở hữu.
9. Xác nhận CI dùng test key và secret tách biệt hoàn toàn với production.

## 14. Tổng kết

`SecureRandom` cung cấp randomness cho key generation và các thao tác mật mã; hãy dùng provider được cấu hình phù hợp, không tự đặt seed cố định và không thay bằng PRNG thông thường. Private key cần được bảo vệ trong KeyStore, HSM hoặc boundary quản lý khóa phù hợp; không hard-code, log hay export khi không cần. Shared secret sau decapsulation là key material nhạy cảm và phải được chuyển vào KDF/giao thức đã được kiểm chứng.

Trong kiểm thử, ưu tiên key pair tạm thời, test vector đã công bố và test provider được xác định rõ. Kiểm tra round-trip, lỗi key/encapsulation và khả năng hỗ trợ của provider mà không để secret xuất hiện trong báo cáo. `Arrays.fill` giúp xóa bản sao byte do ứng dụng quản lý nhưng không bảo đảm xóa mọi bản sao trong bộ nhớ; với yêu cầu cao, hãy dùng key không exportable và HSM/provider phù hợp.

## Tài liệu tham khảo

- [Java SE 21 API — SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html) — nguồn ngẫu nhiên mật mã, provider, thread safety và `getInstanceStrong()`.
- [Java SE 21 API — KeyPairGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyPairGenerator.html) — tạo key pair và cung cấp `SecureRandom`.
- [Java SE 21 API — KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html) — API encapsulator/decapsulator được chuẩn hóa trong Java 21.
- [Java SE 21 API — PrivateKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/PrivateKey.html) và [Key](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Key.html) — biểu diễn private key, format và encoded key material.
- [Java SE 21 API — KeyStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html) — lưu trữ và truy xuất key entry có kiểm soát.
- [JEP 452: Key Encapsulation Mechanism API](https://openjdk.org/jeps/452) — API KEM được hoàn thiện trong Java 21 và mô hình provider.
- [Java SE 21 Security Developer’s Guide](https://docs.oracle.com/en/java/javase/21/security/java-security-overview1.html) — kiến trúc provider và các cơ chế bảo mật của Java.
