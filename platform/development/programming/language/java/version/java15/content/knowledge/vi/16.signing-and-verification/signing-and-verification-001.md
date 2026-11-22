# Signature.getInstance và chọn provider trong Java: ký, xác minh EdDSA đúng cách

> **Ngữ cảnh:** Nội dung thuộc nhóm **Ký và xác minh** của module Java 15. Bài tập trung vào `java.security.Signature.getInstance(...)`, tên thuật toán, cơ chế chọn **security provider**, cách kiểm tra provider thật sự được dùng và xử lý lỗi chọn provider. `Ed25519`/`Ed448` là các thuật toán EdDSA được đưa vào Java 15 và vẫn có trong API Java hiện đại (JDK 17, 21, 25...). Ví dụ dùng **Java 17+**, không sử dụng tính năng preview hoặc API lỗi thời.

## 1. Phân biệt thuật toán, engine và provider

Java Cryptography Architecture (**JCA**) tách mã sử dụng mật mã khỏi phần hiện thực thuật toán. Khi gọi:

```java
Signature signature = Signature.getInstance("Ed25519");
```

ba khái niệm cùng xuất hiện:

1. **Thuật toán** (`"Ed25519"`): tên yêu cầu một **biến thể chữ ký số cụ thể**.
2. **Engine class** (`Signature`): API thống nhất để khởi tạo bằng khóa, nạp bytes thông điệp và ký/xác minh. Nó cung cấp giao diện, không buộc ứng dụng phụ thuộc vào lớp thực thi mật mã cụ thể.
3. **Security provider**: một triển khai được JCA đăng ký hoặc được truyền trực tiếp, cung cấp dịch vụ `Signature` cho thuật toán đó. Ví dụ ở Oracle/OpenJDK, provider `SunEC` có hỗ trợ EdDSA.

Sơ đồ:

```text
Ứng dụng
    |
    |  Signature.getInstance("Ed25519")
    v
JCA engine: java.security.Signature
    |
    |  tìm dịch vụ type = "Signature"
    |  algorithm = "Ed25519"
    v
Security Provider được chọn
    |
    |  SignatureSpi / implementation của provider
    v
initSign(privateKey) -> update(messageBytes) -> sign() -> signatureBytes
initVerify(publicKey) -> update(messageBytes) -> verify(signatureBytes)
```

**Điểm chính:** `Signature.getInstance` **không tự ký** và **không tạo khóa**. Nó tạo **đối tượng engine** để dùng trong những bước tiếp theo. Muốn tạo cặp khóa, sử dụng `KeyPairGenerator`; muốn ký, gọi `initSign`/`update`/`sign`; muốn xác minh, gọi `initVerify`/`update`/`verify`.

Provider **không phải** private key hoặc public key. Một provider có thể xử lý khóa, cung cấp thuật toán và tương tác với phần cứng bảo mật, nhưng việc sở hữu một `Signature` chưa đồng nghĩa đã được cấp khóa để ký.

### Ví dụ phân biệt tên

| Loại | Ví dụ | Có nghĩa là gì? |
| --- | --- | --- |
| Engine | `Signature` | Loại dịch vụ cần dùng |
| Algorithm | `Ed25519` | Biến thể EdDSA cần thực thi |
| Algorithm | `Ed448` | Biến thể EdDSA khác, không trộn khóa với Ed25519 |
| Algorithm family | `EdDSA` | Tên họ thuật toán, không cố định một curve bằng chính tên đó |
| Provider | `SunEC` | Provider ECC/EdDSA trong các bản Oracle/OpenJDK có kèm nó |
| Private key | `KeyPair.getPrivate()` | Dùng khởi tạo phép ký |
| Public key | `KeyPair.getPublic()` | Dùng khởi tạo phép xác minh |
| Message | `byte[]` | Bytes **chính xác** được ký và xác minh |

**Không** viết `Signature.getInstance("SunEC")` để yêu cầu Ed25519. `SunEC` là **tên provider**, không phải tên thuật toán chữ ký.

## 2. Ba dạng `Signature.getInstance(...)` và ý nghĩa lựa chọn

API chính thức có ba overload phổ biến.

### 2.1. Chỉ nêu tên thuật toán: cho JCA lựa chọn

```java
Signature signer = Signature.getInstance("Ed25519");
```

- JCA tìm trong các **security providers được đăng ký** hỗ trợ dịch vụ `Signature` cho `Ed25519`, theo quy tắc ưu tiên của runtime.
- Nếu không có một hiện thực thích hợp, có thể ném `NoSuchAlgorithmException`.
- Ở JDK Reference Implementation, việc chọn provider cho một số engine, trong đó có `Signature`, có thể được **trì hoãn đến lúc khởi tạo bằng khóa**. Do đó không nên coi provider đã được chốt vĩnh viễn ngay sau `getInstance`.
- Cách này **thường phù hợp nhất** với mã ứng dụng thông thường: không phụ thuộc vào tên provider cụ thể, cho runtime chọn triển khai có thể xử lý khóa khi có khả năng đó.

Một bước ký thông thường:

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signed = signer.sign();
```

Đây là snippet, với `privateKey` và `messageBytes` đã tồn tại; cần đặt trong phương thức xử lý ngoại lệ phù hợp. Chương trình runnable có ở phần 6.

### 2.2. Chỉ định tên provider: buộc chọn một provider đã đăng ký

```java
Signature signer = Signature.getInstance("Ed25519", "SunEC");
```

- `"SunEC"` là **tên provider đã đăng ký** trong runtime đang chạy, không phải lựa chọn Java SE bắt buộc ở mọi bản phân phối.
- JCA tìm `Signature` cho `Ed25519` **chỉ trong provider được chỉ rõ**, không tự rơi sang provider khác nếu provider ấy không cung cấp thuật toán hoặc không chấp nhận khóa.
- Nếu provider có tên đó **chưa đăng ký**, ném `NoSuchProviderException`.
- Nếu provider có đăng ký nhưng **không có** dịch vụ `Signature` cho thuật toán yêu cầu, ném `NoSuchAlgorithmException`.
- Nếu tên provider là `null` hoặc chuỗi rỗng, ném `IllegalArgumentException` theo hợp đồng overload.

**Khi dùng:** đã có yêu cầu vận hành xác định như một provider FIPS được kiểm định theo chính sách, PKCS#11/HSM cụ thể, hoặc cần chạy trên môi trường đã biết rõ bộ provider và kiểm thử tương thích. Không chọn tên provider chỉ vì một ví dụ trên mạng dùng tên đó.

### 2.3. Truyền đối tượng `Provider`: dùng instance cụ thể

```java
Provider p = Security.getProvider("SunEC");
if (p == null) {
    throw new IllegalStateException("SunEC is not registered");
}
Signature signer = Signature.getInstance("Ed25519", p);
```

Đây là snippet đặt trong phương thức có thể ném `NoSuchAlgorithmException`. `Security.getProvider` có thể trả `null`; ví dụ kiểm tra trạng thái trước khi truyền vào `getInstance`.

Khác biệt với overload theo tên:

- `Signature.getInstance(String algorithm, Provider provider)` dùng **đối tượng provider cụ thể**.
- Theo API, đối tượng này **không bắt buộc đã đăng ký** trong danh sách provider của hệ thống.
- Nếu đối tượng provider là `null`, ném `IllegalArgumentException`.
- Nếu chính đối tượng provider không có implementation cho thuật toán, ném `NoSuchAlgorithmException`.
- Không tự động “nhảy” sang provider khác khi đã chỉ định đối tượng cụ thể.

Dùng đối tượng `Provider` là phù hợp khi provider đã được cấu hình/khởi tạo bởi ứng dụng hoặc thư viện/hệ thống bảo mật theo quy trình tin cậy. Tránh tự đăng ký provider toàn cục chỉ để gọi một lần nếu overload nhận `Provider` đã phù hợp.

### Bảng tổng hợp ba overload

| Lời gọi | Phạm vi chọn provider | Điều kiện đáng chú ý | Cách sử dụng khuyến nghị |
| --- | --- | --- | --- |
| `getInstance("Ed25519")` | Các provider đã đăng ký; chọn tự động theo runtime | Có thể dùng lựa chọn trì hoãn dựa trên key ở JDK RI | **Mặc định** cho ứng dụng thông thường |
| `getInstance("Ed25519", "SunEC")` | Provider đăng ký có tên `SunEC` | Tên phải có trong registry; không fallback | Môi trường được quản lý, bắt buộc provider cụ thể |
| `getInstance("Ed25519", providerObject)` | Chính đối tượng `Provider` được truyền | Không đòi object đã đăng ký, nhưng object phải hỗ trợ thuật toán | Provider được cấu hình ở tầng ứng dụng/HSM/framework |

**Tách biệt rõ “thuật toán” khỏi “provider”:** mã Java phải nêu thuật toán đúng hợp đồng chữ ký; tên/provider object chỉ quyết định **ai thực thi thuật toán đó**.

## 3. Chọn thuật toán: `Ed25519`, `Ed448` hay `EdDSA`?

Java cung cấp các tên chuẩn trong danh sách **Java Security Standard Algorithm Names**:

- `"Ed25519"`: chữ ký EdDSA với bộ tham số Ed25519.
- `"Ed448"`: chữ ký EdDSA với bộ tham số Ed448.
- `"EdDSA"`: tên **họ** thuật toán.

Chọn thuật toán **theo giao thức và loại khóa**. Ví dụ ứng dụng đã quy định Ed25519 thì nên viết nhất quán:

```java
KeyPairGenerator kpg =
        KeyPairGenerator.getInstance("Ed25519");
Signature signer = Signature.getInstance("Ed25519");
Signature verifier = Signature.getInstance("Ed25519");
```

**Đừng** chọn `Ed448` ở một phía rồi dùng key/signature Ed25519 ở phía còn lại. Việc provider từ chối khóa có thể được báo bằng `InvalidKeyException` ở `initSign`/`initVerify`; khi dữ liệu chữ ký không khớp, `verify` có thể trả `false` hoặc báo lỗi định dạng thích hợp.

### Vì sao tên `EdDSA` đôi khi gây nhầm?

`EdDSA` là tên thuật toán tổng quát. Một provider có thể chọn bộ tham số theo **khóa** hoặc theo các thông số được cung cấp, nhưng **đừng suy luận rằng mọi provider áp dụng cùng mặc định cho mọi lệnh**.

Với yêu cầu giao thức xác định, chọn `Ed25519` hoặc `Ed448` rõ ràng giúp:

1. Đọc mã thấy ngay biến thể yêu cầu.
2. Tránh chọn nhầm tham số mặc định của provider khi tạo khóa.
3. Viết kiểm thử chính xác theo độ dài và định dạng chữ ký.
4. Ràng buộc chính sách khóa/protocol với lựa chọn được ghi rõ.

Theo RFC 8032, chữ ký Ed25519 dài **64 bytes**; chữ ký Ed448 dài **114 bytes**. Đó là độ dài **chữ ký thô theo thuật toán**, không phải độ dài public key dạng X.509 SubjectPublicKeyInfo hoặc private key dạng PKCS#8.

### Đừng tự sáng chế tên signature algorithm

Không dùng các chuỗi không thuộc hợp đồng provider như `"SHA512withEd25519"` với suy nghĩ Ed25519 là một biến thể ghép hash theo mẫu tên RSA. `Ed25519` đã xác định toàn bộ quy trình chữ ký theo RFC 8032; tên JCA chuẩn là `"Ed25519"`.

Tương tự, không tự hash message rồi gọi `Ed25519.sign` trên digest và coi đó là `Ed25519ph`: bạn chỉ đang ký **một message khác**. Nếu giao thức yêu cầu prehash/context theo chuẩn, phải sử dụng cơ chế/provider thực sự hỗ trợ theo hợp đồng tương ứng.

## 4. Làm sao biết runtime có provider nào hỗ trợ?

Danh sách provider được đăng ký có thể truy cập qua:

```java
Provider[] registered = Security.getProviders();
```

Với mỗi `Provider`, dịch vụ riêng lẻ có thể kiểm tra bằng:

```java
Provider.Service service =
        provider.getService("Signature", "Ed25519");
```

Nếu `service != null`, provider **quảng bá dịch vụ Signature** cho tên thuật toán được hỏi. Tuy nhiên điều này **không tự bảo đảm** provider chấp nhận mọi loại key hay đáp ứng mọi policy cấu hình: muốn biết có ký/xác minh được với **khóa thực**, hãy thực hiện `initSign`/`initVerify` và một phép thử phù hợp.

### Ví dụ runnable: khảo sát provider, không hard-code tên

Tạo file **`ProviderDiscoveryDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.Provider;
import java.security.Security;
import java.security.Signature;

public class ProviderDiscoveryDemo {
    public static void main(String[] args)
            throws GeneralSecurityException {
        String algorithm = "Ed25519";
        Provider first = null;
        int candidates = 0;

        for (Provider provider : Security.getProviders()) {
            if (provider.getService("Signature", algorithm) != null) {
                candidates++;
                if (first == null) {
                    first = provider;
                }
            }
        }

        System.out.println("provider.found=" + (candidates > 0));
        if (first == null) {
            System.out.println("Ed25519 unavailable");
            return;
        }

        Signature named =
                Signature.getInstance(algorithm, first.getName());
        Signature object =
                Signature.getInstance(algorithm, first);
        Signature automatic = Signature.getInstance(algorithm);

        System.out.println("byName.same="
                + named.getProvider().getName()
                        .equals(first.getName()));
        System.out.println("byObject.same="
                + object.getProvider().getName()
                        .equals(first.getName()));
        System.out.println("automatic.algorithm="
                + automatic.getAlgorithm());
    }
}
```

Chạy trên **JDK 17+**:

```bash
javac -encoding UTF-8 ProviderDiscoveryDemo.java
java ProviderDiscoveryDemo
```

Khi runtime có provider hỗ trợ `Ed25519` (như Oracle/OpenJDK thông thường có `SunEC`), stdout là:

```text
provider.found=true
byName.same=true
byObject.same=true
automatic.algorithm=Ed25519
```

Nếu không có provider nào hỗ trợ thuật toán, chương trình **không cố tạo `Signature`**, mà in:

```text
provider.found=false
Ed25519 unavailable
```

**Không in tên provider hoặc số lượng provider cố định vào expected output**, vì chúng là **cấu hình runtime**, thay đổi theo bản phân phối JDK, module có sẵn và danh sách provider được cài đặt.

### Cách in danh sách thật khi chẩn đoán

Nếu muốn biết tên các provider hiện hành, dùng đoạn code sau **bên trong một phương thức**, sau khi import `java.security.*`:

```java
for (Provider provider : Security.getProviders()) {
    Provider.Service service =
            provider.getService("Signature", "Ed25519");
    if (service != null) {
        System.out.println(provider.getName()
                + " -> " + service.getAlgorithm());
    }
}
```

Output là **dữ liệu môi trường**, không có một chuỗi cố định cho mọi máy. Ví dụ ở một bản Oracle/OpenJDK thường thấy tên `SunEC`, nhưng không nên xem tên ấy là cam kết của chuẩn Java SE cho mọi runtime.

**Chú ý:** Thứ tự từ `Security.getProviders()` thể hiện thứ tự đăng ký thông thường; JDK Reference Implementation còn hỗ trợ security property `jdk.security.provider.preferred` để điều chỉnh ưu tiên cho thuật toán cụ thể. Vì vậy không luôn suy ra provider cuối cùng chỉ bằng cách lấy phần tử đầu tiên trong một danh sách rồi bỏ qua khóa.

## 5. Delayed provider selection: tại sao nên gọi `getProvider()` sau khởi tạo?

JDK Reference Implementation có cơ chế **delayed provider selection** cho một số JCA engines. Với `Signature.getInstance(algorithm)` không chỉ định provider, JDK có thể **chưa chốt provider tại thời điểm tạo object**.

Tại sao?

- Một private key có thể nằm trong **HSM, token PKCS#11** hoặc một provider cụ thể và **không xuất được**.
- Provider phần mềm A có thể hỗ trợ `Ed25519` nhưng **không sử dụng được** private key không xuất được của token B.
- Nếu provider được chọn quá sớm theo danh sách ưu tiên mà không nhìn khóa, `initSign(privateKey)` có thể thất bại không cần thiết.
- Khi trì hoãn đến bước khởi tạo, JDK có thể dùng thông tin key để lựa chọn implementation chấp nhận khóa, **trong giới hạn provider/capability có sẵn**.

### Cách viết nên dùng

```java
Signature signer = Signature.getInstance("Ed25519");
// Chưa vội gọi signer.getProvider() ở đây.
signer.initSign(privateKey);
Provider selected = signer.getProvider();
// selected phản ánh provider đã được chọn sau bước initSign.
```

**Nguyên tắc:** Nếu không cần cố định provider, hãy **khởi tạo bằng khóa trước**, rồi mới hỏi `getProvider()` để quan sát provider thực sự phục vụ thao tác. Mã này là snippet giả định `privateKey` hợp lệ, với import `java.security.*` và checked exception đã được xử lý.

### Điều cần tránh

```java
Signature signer = Signature.getInstance("Ed25519");
Provider tooEarly = signer.getProvider(); // Có thể ép chọn provider.
signer.initSign(privateKey);              // Có thể không còn được chọn lại.
```

Trong JDK RI, gọi `getProvider()` **trước khi lựa chọn trì hoãn hoàn tất** có thể làm provider đầu tiên được cố định; provider ấy chưa chắc xử lý được khóa mà bạn truyền sau đó.

Khi provider đã được chọn (ví dụ sau lần khởi tạo đầu), JDK không tự chuyển provider khác cho các lần khởi tạo tiếp theo trên **cùng instance**. Nếu cần một lựa chọn dựa trên **key mới**, hãy gọi `Signature.getInstance(...)` tạo engine mới rồi `initSign(newKey)`, thay vì tái sử dụng instance đã cố định provider.

**Giới hạn của quy tắc này:** đây là hành vi được tài liệu hóa cho **JDK Reference Implementation**; đừng khẳng định mọi security provider, mọi JVM và mọi engine có đúng cùng thời điểm chọn provider. Với overload chỉ định `providerName` hoặc `Provider`, ứng dụng đã **cố định provider từ đầu**, không có lựa chọn tự động sang provider khác.

### Kiểm tra `getProvider()` và `getAlgorithm()` cho đúng mục đích

| Phương thức | Câu hỏi trả lời |
| --- | --- |
| `signature.getAlgorithm()` | Đối tượng engine được yêu cầu thuật toán/tên algorithm gì? |
| `signature.getProvider()` | Provider object nào đã được engine sử dụng/chọn? |
| `signature.getProvider().getName()` | Tên đăng ký hoặc tên do provider công bố |
| `Security.getProviders()` | Các provider hiện đăng ký với runtime |
| `provider.getService("Signature", algorithm)` | Provider có quảng bá dịch vụ signature tương ứng không? |

`getAlgorithm()` **không phải** cách tìm tên provider. `getProvider()` cũng **không** xác minh rằng private key nằm trong một kho khóa an toàn hay được phép sử dụng; đó là vấn đề quản trị khóa và provider configuration riêng biệt.

## 6. Ví dụ Java hoàn chỉnh: JCA tự chọn provider để ký/xác minh

Tạo tệp **`Ed25519AutoProviderDemo.java`**. Ví dụ tránh hard-code tên provider, chỉ dùng `Ed25519` làm hợp đồng thuật toán. Nó minh họa đúng trình tự **tạo khóa → tạo Signature → initSign → lấy provider → update → sign → initVerify → update → verify**.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class Ed25519AutoProviderDemo {
    public static void main(String[] args)
            throws GeneralSecurityException {
        String algorithm = "Ed25519";

        KeyPairGenerator kpg =
                KeyPairGenerator.getInstance(algorithm);
        KeyPair pair = kpg.generateKeyPair();

        byte[] original = "order=501;amount=100"
                .getBytes(StandardCharsets.UTF_8);
        byte[] changed = "order=501;amount=101"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(pair.getPrivate());
        // Lấy provider SAU initSign, tránh ép chọn quá sớm.
        System.out.println("sign.provider.selected="
                + (signer.getProvider() != null));
        signer.update(original);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(pair.getPublic());
        verifier.update(original);
        System.out.println("original.valid="
                + verifier.verify(signature));

        Signature altered = Signature.getInstance(algorithm);
        altered.initVerify(pair.getPublic());
        altered.update(changed);
        System.out.println("changed.valid="
                + altered.verify(signature));

        System.out.println("algorithm=" + signer.getAlgorithm());
        System.out.println("signature.length=" + signature.length);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 Ed25519AutoProviderDemo.java
java Ed25519AutoProviderDemo
```

Trên **Oracle/OpenJDK 17+ có Ed25519 hỗ trợ và bộ provider mặc định tương thích**, stdout dự kiến:

```text
sign.provider.selected=true
original.valid=true
changed.valid=false
algorithm=Ed25519
signature.length=64
```

**Giải thích:**

1. `KeyPairGenerator.getInstance("Ed25519")` tìm một provider tạo cặp khóa phù hợp.
2. `Signature.getInstance("Ed25519")` tạo engine có cùng tên thuật toán nhưng **không nhất thiết chọn cùng provider với generator**.
3. `initSign(pair.getPrivate())` cung cấp private key, giúp engine/provider được khởi tạo cho phép ký.
4. `signer.getProvider() != null` kiểm chứng đã có provider; tên cụ thể không được in vì tùy môi trường.
5. `signer.sign()` trả signature bytes; Ed25519 chuẩn dài 64 bytes.
6. `verifier.initVerify(pair.getPublic())` dùng public key tương ứng và cùng original bytes nên `verify` trả `true`.
7. Dùng message khác vẫn cùng public key/signature, `verify` trả `false`.

Ví dụ này **không chứng minh** mọi provider đều dùng chung key object được. Trên môi trường token không xuất khóa, HSM hoặc policy đặc biệt, bộ provider có thể yêu cầu lựa chọn hoặc cấu hình khác. Chương trình được kỳ vọng chạy trên JDK có hỗ trợ `Ed25519` bằng provider tương thích như ở môi trường Oracle/OpenJDK thông thường.

## 7. Ví dụ Java hoàn chỉnh: buộc chọn `SunEC` theo tên và theo object

Tạo file **`Ed25519PinnedProviderDemo.java`**. Ví dụ này minh họa **hai overload cố định provider** một cách minh bạch. Mã kiểm tra `SunEC` có đăng ký và quảng bá cả `Signature.Ed25519` lẫn `KeyPairGenerator.Ed25519`; nếu không có, chương trình báo và kết thúc.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Provider;
import java.security.Security;
import java.security.Signature;

public class Ed25519PinnedProviderDemo {
    public static void main(String[] args)
            throws GeneralSecurityException {
        final String algorithm = "Ed25519";
        Provider provider = Security.getProvider("SunEC");

        boolean available = provider != null
                && provider.getService("Signature", algorithm) != null
                && provider.getService("KeyPairGenerator", algorithm) != null;

        System.out.println("SunEC.available=" + available);
        if (!available) {
            return;
        }

        KeyPair keys = KeyPairGenerator
                .getInstance(algorithm, provider)
                .generateKeyPair();

        byte[] message = "account=42;status=OK"
                .getBytes(StandardCharsets.UTF_8);
        byte[] modified = "account=42;status=NO"
                .getBytes(StandardCharsets.UTF_8);

        // Cố định SunEC bằng Provider object.
        Signature signer = Signature.getInstance(
                algorithm, provider);
        signer.initSign(keys.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        // Cố định SunEC bằng tên provider đã đăng ký.
        Signature verifierByName = Signature.getInstance(
                algorithm, "SunEC");
        verifierByName.initVerify(keys.getPublic());
        verifierByName.update(message);

        // Cố định lại SunEC bằng chính Provider object.
        Signature verifierByObject = Signature.getInstance(
                algorithm, provider);
        verifierByObject.initVerify(keys.getPublic());
        verifierByObject.update(message);

        System.out.println("name.provider="
                + verifierByName.getProvider().getName());
        System.out.println("object.provider="
                + verifierByObject.getProvider().getName());
        System.out.println("provider.same="
                + verifierByName.getProvider().getName()
                        .equals(verifierByObject.getProvider().getName()));

        System.out.println("byName.valid="
                + verifierByName.verify(signature));
        System.out.println("byObject.valid="
                + verifierByObject.verify(signature));

        Signature changed = Signature.getInstance(
                algorithm, provider);
        changed.initVerify(keys.getPublic());
        changed.update(modified);
        System.out.println("changed.valid="
                + changed.verify(signature));

        System.out.println("signature.length="
                + signature.length);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Ed25519PinnedProviderDemo.java
java Ed25519PinnedProviderDemo
```

Trên Oracle/OpenJDK 17+ có provider `SunEC` hỗ trợ Ed25519, stdout:

```text
SunEC.available=true
name.provider=SunEC
object.provider=SunEC
provider.same=true
byName.valid=true
byObject.valid=true
changed.valid=false
signature.length=64
```

Nếu `SunEC` vắng mặt hoặc không có các dịch vụ cần dùng, stdout chỉ là:

```text
SunEC.available=false
```

Ở nhánh thành công, cả ba engine (signer, verifier theo tên, verifier theo object) đều dùng cùng provider. **Tên provider được in có chủ đích** trong ví dụ này vì đã chọn chính `"SunEC"`. Điều đó khác với ví dụ `getInstance(algorithm)` **không cố định provider**, vốn phải cho phép JDK chọn triển khai tương thích.

### Tại sao lại tạo keypair bằng cùng provider ở ví dụ này?

`KeyPairGenerator` cũng là một JCA engine riêng. Nếu cho generator tự chọn provider khác, đối tượng private/public key được tạo ra **có thể** không tương thích với provider `SunEC` mà bạn cố định cho `Signature` trong một số hệ thống đặc biệt.

Để ví dụ dễ tái lập, mã chọn **cùng `Provider`** khi tạo cặp khóa và khi ký/xác minh. Trong môi trường thực tế dùng HSM, nên tạo hoặc tra cứu khóa **qua provider/token có thẩm quyền**, rồi dùng signature provider tương thích. **Không** xuất private key chỉ để chuyển sang một provider phần mềm khác nếu không được chính sách cho phép.

**Nhận diện giới hạn kiểm tra availability:** `provider.getService(...) != null` chỉ cho biết dịch vụ được đăng ký; khởi tạo và sử dụng với **khóa thực** vẫn có thể thất bại do quyền token, cấu hình, thuộc tính khóa hoặc provider implementation.

## 8. Khi nào nên cố định provider, khi nào để JCA tự chọn?

**Chọn tự động thường là mặc định tốt** nếu:

- Ứng dụng chỉ cần thuật toán `Ed25519` đúng chuẩn, không bị ràng buộc nhà cung cấp.
- Tổ chức muốn đổi JDK/provider hoặc bổ sung provider theo cấu hình deploy mà không sửa mã.
- Định dạng key tương thích và thuật toán được provider của runtime hỗ trợ.
- Không cần bắt buộc một thiết bị token/HSM được chỉ định để ký.

Ví dụ:

```java
Signature s = Signature.getInstance("Ed25519");
s.initSign(privateKey);
```

Đây là snippet. `initSign` có thể phát sinh `InvalidKeyException` nếu **không provider nào** dùng được khóa cần ký trong cấu hình hiện hành; đó không phải lý do để tự tạo private key mới thay thế một cách âm thầm.

**Cố định provider có lý do** nếu:

- Private key phải ở **HSM/token PKCS#11** và provider cụ thể mới có quyền dùng private key.
- Yêu cầu FIPS/chính sách nội bộ bắt buộc một implementation đã được phê duyệt.
- Bạn đang kiểm thử một provider cụ thể (tính tương thích, độ chính xác, hiệu năng hoặc cấu hình).
- Giao thức phụ thuộc vào khả năng đặc thù được provider hỗ trợ rõ ràng.

Khi cố định:

1. Xác định provider chính xác (theo tên đăng ký hoặc object được tạo từ cấu hình hợp lệ).
2. Kiểm tra provider cung cấp **`Signature` đúng thuật toán**.
3. Kiểm tra khóa cần dùng có được provider chấp nhận.
4. Kiểm tra các thuộc tính bảo mật và capability thực tế ở môi trường triển khai.
5. Xác minh tên provider **sau khởi tạo**, ghi log metadata phù hợp; không log private key.
6. Thiết kế chính sách xử lý khi provider không khả dụng: **từ chối ký** hoặc chuyển sang provider khác **chỉ khi chính sách cho phép**. Không fallback ngầm làm mất bảo đảm HSM/FIPS.

### Vì sao fallback tùy tiện là rủi ro?

Giả sử hệ thống có chính sách “mọi chữ ký thanh toán phải dùng private key trong HSM”. Nếu provider HSM không khả dụng, tự động tạo cặp khóa mới trên phần mềm hoặc chuyển sang provider không được phê duyệt có thể **vi phạm ranh giới tin cậy**, dù `sign()` tạo ra một chữ ký hợp lệ về mặt toán học.

Ngược lại, nếu ứng dụng không bị ràng buộc provider, việc hard-code `"SunEC"` khiến hệ thống khó chạy trên JDK/vendor khác mà không đem lại giá trị nghiệp vụ. Lựa chọn thuật toán và chính sách provider cần được thiết kế **tách biệt**.

## 9. Lỗi chọn provider và ngoại lệ cần nhận diện

Các lỗi từ `getInstance` khác với lỗi dùng khóa và chữ ký. Bảng sau nêu các trường hợp đáng học:

| Thao tác | Tình huống | Ngoại lệ/kết quả điển hình | Cách xử lý |
| --- | --- | --- | --- |
| `getInstance("UnknownAlgorithm")` | Không provider nào có thuật toán ấy | `NoSuchAlgorithmException` | Sửa tên thuật toán hoặc cấu hình provider |
| `getInstance("Ed25519", "MissingProvider")` | Tên provider không được đăng ký | `NoSuchProviderException` | Kiểm tra `Security.getProvider(...)` và cấu hình deployment |
| `getInstance("Ed25519", name)` | Provider đã đăng ký nhưng không hỗ trợ `Ed25519` | `NoSuchAlgorithmException` | Chọn provider có dịch vụ hoặc cấu hình đúng |
| `getInstance("Ed25519", (Provider) null)` | Provider object `null` | `IllegalArgumentException` | Khởi tạo/kiểm tra object trước khi truyền |
| `getInstance(null)` | Algorithm name `null` | `NullPointerException` | Bảo đảm thuật toán được cấu hình hợp lệ |
| `initSign(privateKey)` | Key không được provider chấp nhận | `InvalidKeyException` | Dùng đúng loại khóa, provider/token phù hợp |
| `initVerify(publicKey)` | Public key không hợp lệ hoặc không tương thích | `InvalidKeyException` | Kiểm tra nguồn key/thuật toán |
| `sign()` hoặc `update(...)` trước khi khởi tạo | Engine sai trạng thái | `SignatureException` | Khởi tạo với `initSign` hoặc `initVerify` trước |
| `verify(bytes)` | Bytes signature sai hoặc không khớp | `false` hoặc `SignatureException` theo dữ liệu/provider | Phân biệt chữ ký không hợp lệ với lỗi định dạng |
| `Security.getProvider("SunEC")` | Không có tên provider ấy | Trả `null` | Không dereference nếu `null` |

**Không đánh đồng:** `NoSuchAlgorithmException` là thiếu **implementation của thuật toán**, `NoSuchProviderException` là thiếu **provider có tên yêu cầu**, còn `InvalidKeyException` là **khóa không dùng được** trong thao tác cụ thể. Nếu `getInstance` thành công mà `initSign` thất bại, không nên vội kết luận “Java không hỗ trợ Ed25519”.

### Ví dụ phân biệt hai lỗi tên/provider

Các đoạn sau là snippet minh họa **cố tình yêu cầu tên không tồn tại**; đặt trong một phương thức có quyền xử lý checked exceptions:

```java
try {
    Signature.getInstance("Ed25519", "NoProviderForTraining");
} catch (java.security.NoSuchProviderException e) {
    System.out.println("missing provider");
}

try {
    Signature.getInstance("NotARealSignatureAlgorithm");
} catch (java.security.NoSuchAlgorithmException e) {
    System.out.println("missing algorithm");
}
```

Ở một runtime không có provider nào mang tên huấn luyện và không có thuật toán tưởng tượng này, stdout:

```text
missing provider
missing algorithm
```

Không sử dụng những tên cố tình sai trong ứng dụng thật. Chúng chỉ giúp xác định loại lỗi mà bạn cần bắt và ghi log.

### Khi `getProvider()` cho kết quả bạn không mong đợi

Kiểm tra theo thứ tự:

1. Đã gọi overload nào? Có chỉ định tên/provider object không?
2. Nếu tự chọn, đã gọi `getProvider` **trước `initSign`** hay sau?
3. Provider có được đăng ký, đang hoạt động và có implementation cho algorithm không?
4. Private key là khóa phần mềm thông thường hay khóa token không xuất được?
5. Đã tái sử dụng `Signature` object từng khởi tạo với khóa/provider trước đó hay chưa?
6. Runtime có thiết lập `jdk.security.provider.preferred`, thứ tự provider hoặc chính sách crypto riêng không?
7. Có cơ chế provider selection ở tầng framework hoặc thư viện ngoài JCA không?

Đừng sửa thứ tự provider toàn JVM chỉ để “chữa” một lời gọi nếu bạn chưa hiểu hệ quả bảo mật của việc thay đổi đó.

## 10. Đọc provider thực tế và bảo mật thông tin chẩn đoán

Một mẫu ghi log an toàn sau khi đã khởi tạo:

```java
Signature s = Signature.getInstance("Ed25519");
s.initSign(privateKey);

String algorithm = s.getAlgorithm();
String providerName = s.getProvider().getName();

System.out.println("algorithm=" + algorithm);
System.out.println("provider=" + providerName);
```

Đây là **snippet** với private key đã được chuẩn bị. Dòng `algorithm=Ed25519` là tên cố định theo yêu cầu; dòng `provider=...` **phụ thuộc runtime** và **không nên hard-code giá trị trong test dùng nhiều JDK**.

Thông tin có thể ghi log khi chẩn đoán:

- Thuật toán được yêu cầu và phiên bản giao thức.
- Provider thực tế theo `getProvider().getName()` và, khi cần, `getVersionStr()`.
- Trạng thái ký/xác minh và loại ngoại lệ (không tiết lộ thông điệp nhạy cảm).
- Mã định danh key ID **không bí mật** theo chính sách hệ thống, nếu có.

**Không log:**

- Giá trị private key hoặc bytes từ `getEncoded()`.
- Mật khẩu truy cập keystore/token, PIN HSM hoặc credential.
- Toàn bộ payload giao dịch nhạy cảm chỉ để so sánh provider.
- Tham số mật mã bí mật của provider hoặc thông tin không được phép công bố.

Provider name là **metadata** để chẩn đoán, không phải bằng chứng duy nhất rằng chữ ký tuân thủ một chính sách an toàn cụ thể. Cần kiểm tra thêm nguồn khóa, chính sách provider, cấu hình và quy trình vận hành.

## 11. Provider và vòng đời khóa: những sự khác biệt dễ bỏ sót

### 11.1. Cặp khóa và signature engine có thể từ hai provider khác nhau

`KeyPairGenerator.getInstance("Ed25519")` và `Signature.getInstance("Ed25519")` là **hai lần chọn engine độc lập**. Trong JDK thông thường, sự tương thích giữa key implementation và signature provider được thiết kế để làm việc với nhau. Nhưng trong HSM, key object có thể không thể xuất và chỉ một provider mới chấp nhận nó.

Nếu đã chọn provider rõ ràng khi tạo khóa:

```java
KeyPairGenerator generator =
        KeyPairGenerator.getInstance("Ed25519", provider);
Signature signer = Signature.getInstance("Ed25519", provider);
```

Hai snippet này giả định object `provider` đã được cấu hình và thực sự hỗ trợ cả hai dịch vụ. Việc cùng provider giúp nhất quán cấu hình nhưng **không thay thế kiểm tra chính sách và khả năng dùng khóa**.

### 11.2. Public key không bắt buộc phải dùng cùng provider với signer

Chữ ký số được thiết kế để bên nhận có thể xác minh bằng **cùng thuật toán chuẩn và public key tương ứng**, không nhất thiết cùng máy hay cùng provider. Khả năng tương tác thực tế còn phụ thuộc:

- Algorithm và tham số phù hợp (`Ed25519` hoặc `Ed448`).
- Cách serialize/deserialize public key (ví dụ `X.509 SubjectPublicKeyInfo` nếu provider hỗ trợ).
- Bytes message chính xác mà hai phía đã ký và xác minh.
- Định dạng chữ ký theo quy tắc thuật toán.
- Kiểu public key và các kiểm tra đầu vào mà provider xác minh hỗ trợ.

Không tự cho rằng cứ có `PublicKey` là mọi provider đều chấp nhận; kiểm tra `initVerify` trong môi trường thật. **Không** export private key chỉ để verifier dễ sử dụng: public key là đủ để xác minh.

### 11.3. Không đổi provider để làm mất lỗi chữ ký sai

Nếu `verify` trả `false`, trước khi quy lỗi cho provider nên kiểm tra:

1. Public key có đúng cặp với private key đã ký không?
2. Bên ký và bên xác minh có dùng cùng variant Ed25519/Ed448 không?
3. Message có giống **từng byte** không (charset, newline, dấu cách, JSON serialization)?
4. Bytes chữ ký có bị sửa khi qua Base64/HTTP/JSON không?
5. Public key đã được xác thực nguồn chưa?

Chuyển provider không làm chữ ký cho **message bị sửa** trở thành hợp lệ, và không phải cách bỏ qua việc xác thực khóa công khai.

### 11.4. Không tái sử dụng `Signature` instance bừa bãi giữa các luồng

`Signature` giữ trạng thái nội bộ: chế độ ký/xác minh, key, dữ liệu từ `update` và tham số thuật toán. Đừng chia sẻ một instance mutable cho nhiều luồng nếu không có hợp đồng và cơ chế đồng bộ phù hợp. Thông thường, tạo **instance riêng theo thao tác/yêu cầu** giúp dễ quản lý trạng thái và provider.

Sau `sign()` hoặc `verify()`, trạng thái message của engine được reset theo hợp đồng API, nhưng không biến đối tượng thành nơi lưu nhiều luồng dùng chung tùy ý. Khi cần đổi key/provider, khởi tạo instance mới rõ ràng thường an toàn, dễ đọc hơn.

## 12. Quy trình lựa chọn provider dành cho dự án thực tế

Dưới đây là một quy trình ngắn nhưng chặt chẽ:

1. **Chốt thuật toán ở cấp giao thức:** ví dụ ký dữ liệu vận hành bằng `Ed25519`. Đừng để tên thuật toán lấy tùy ý từ đầu vào không tin cậy.
2. **Xác định nơi giữ private key:** keystore phần mềm, HSM hoặc KMS có hỗ trợ Ed25519; đây là đầu vào quan trọng quyết định provider.
3. **Chọn chính sách provider:** nếu không có yêu cầu cụ thể, để JCA tự chọn; nếu có policy, cấu hình provider được chấp thuận và dùng overload tương ứng.
4. **Kiểm tra service:** sử dụng `Security.getProviders()`, `Provider.getService(...)` hoặc danh sách thuật toán của provider; không chỉ nhìn tên.
5. **Khởi tạo bằng khóa thật:** thử `initSign(privateKey)`/`initVerify(publicKey)` để xác định khả năng sử dụng thực tế.
6. **Đọc provider đã được chọn sau khởi tạo:** `signature.getProvider()`. Đối với cơ chế trì hoãn, thao tác này tránh ép lựa chọn quá sớm.
7. **Kiểm tra round-trip:** ký message bytes và verify bằng public key tương ứng; thử sửa một byte và xác nhận phép kiểm tra từ chối.
8. **Áp dụng chính sách lỗi rõ ràng:** thiếu provider/HSM hay khóa không hợp lệ phải **từ chối xử lý**, không silently fallback sang một khóa không được phê duyệt.
9. **Kiểm thử trên đúng runtime triển khai:** JDK vendor/version, hệ điều hành, module, cấu hình provider, token, certificate/keystore và chính sách bảo mật.
10. **Theo dõi thay đổi môi trường:** thêm/xóa provider hoặc đổi thứ tự/priority có thể thay implementation được chọn dù mã Java không đổi.

### Ma trận ra quyết định

| Bối cảnh | Cách gọi gợi ý | Lý do |
| --- | --- | --- |
| Dịch vụ Java thông thường, không yêu cầu provider cụ thể | `Signature.getInstance("Ed25519")` | Ít phụ thuộc vào vendor, cho JCA tự tìm implementation |
| JDK Oracle/OpenJDK trong bài thực hành nhằm thử `SunEC` | `Signature.getInstance("Ed25519", "SunEC")` | Chỉ rõ implementation để minh họa |
| Provider cấu hình riêng trả về `Provider` object | `Signature.getInstance("Ed25519", provider)` | Dùng đúng object được cấu hình, không đòi object nằm trong registry |
| Private key không xuất được trong token/HSM cụ thể | Chọn provider/token tương thích theo chính sách HSM | Bảo toàn ranh giới khóa và capability |
| Ứng dụng cần tương thích giữa nhiều runtime | Giữ thuật toán `Ed25519` làm hợp đồng, test key/serialization | Không phụ thuộc tên provider nếu không cần |
| Runtime không có Ed25519 | Cấu hình/cài provider hiện hành có hỗ trợ hoặc điều chỉnh môi trường được phê duyệt | Không tùy tiện chuyển thuật toán hoặc khóa để “chạy được” |

## 13. Các sai lầm thường gặp

| Sai lầm | Tại sao sai | Sửa thế nào |
| --- | --- | --- |
| Gọi `Signature.getInstance("SunEC")` | `SunEC` là provider, không phải signature algorithm | Dùng `getInstance("Ed25519", "SunEC")` nếu cần chỉ định provider |
| Hard-code `SunEC` cho mọi JDK | Tên/provider không được Java SE bảo đảm trên mọi runtime | Dùng chọn tự động, hoặc kiểm tra provider và cấu hình rõ |
| Gọi `getProvider()` trước `initSign` rồi ngạc nhiên khi HSM key bị từ chối | Có thể cố định provider sớm, mất delayed selection | Khởi tạo bằng khóa trước, hỏi provider sau |
| Cho rằng provider đầu trong `Security.getProviders()` luôn là provider thực tế | Có preferred property và lựa chọn trì hoãn | Đọc provider của instance đã khởi tạo |
| `getInstance` thành công là chắc chắn ký được | Provider có thuật toán nhưng có thể không dùng được private key | Gọi `initSign` và kiểm thử thật |
| Cố định provider nhưng mong nó fallback | Overload có provider không làm lựa chọn tự động sang provider khác | Tự xử lý policy fallback, hoặc dùng overload không provider |
| Dùng `EdDSA` rồi ngầm giả định luôn là Ed25519 | Tên family không chốt biến thể trong mọi provider/cấu hình | Chọn `Ed25519` hoặc `Ed448` theo protocol |
| Trộn Ed448 key với `Signature("Ed25519")` | Thuật toán/key không khớp | Dùng cùng biến thể EdDSA |
| Nhầm `NoSuchProviderException` với `NoSuchAlgorithmException` | Một lỗi thiếu provider theo tên, một lỗi thiếu algorithm implementation | Chẩn đoán theo overload và ngoại lệ |
| Gọi `getAlgorithm()` để in tên provider | Trả algorithm name, không phải provider name | `getProvider().getName()` |
| Tự đăng ký provider không được tin cậy vào registry toàn JVM | Thay phạm vi trust và lựa chọn mật mã của nhiều thành phần | Quản lý provider qua cấu hình/kiểm định thích hợp |
| Tự xuất HSM private key để phần mềm ký | Phá khả năng giữ khóa không xuất được | Giữ private key trong token và dùng provider hỗ trợ |
| Xem `verify=true` là bằng chứng nhận dạng/ủy quyền hoàn chỉnh | Chỉ chứng minh tương quan chữ ký với public key đã chọn | Xác thực nguồn public key, kiểm tra quyền và chống replay |
| Bỏ qua chính xác bytes của message | Thay newline, encoding hoặc serialization làm đổi message | Ký và verify cùng byte sequence đã quy định |

## 14. Bài tập có đáp án

**Bài 1.** Phân loại các thành phần trong lời gọi:

```java
Signature s = Signature.getInstance("Ed25519", "SunEC");
```

**Đáp án:** `Signature` là engine class; `"Ed25519"` là algorithm name; `"SunEC"` là tên provider cần **đăng ký** trong runtime. Nếu provider không đăng ký, có thể nhận `NoSuchProviderException`.

**Bài 2.** Bạn muốn deploy cùng chương trình trên nhiều JDK mà không bắt buộc provider cụ thể. Chọn overload nào?

**Đáp án:** `Signature.getInstance("Ed25519")`, sau đó `initSign(privateKey)` hoặc `initVerify(publicKey)` đúng ngữ cảnh. Đọc `getProvider()` sau khởi tạo nếu cần chẩn đoán.

**Bài 3.** Khi nào `Signature.getInstance("Ed25519", Provider p)` có thể dùng provider chưa được đăng ký?

**Đáp án:** Overload nhận **`Provider` object** không yêu cầu object ấy nằm trong registry. Nhưng chính object vẫn phải cung cấp dịch vụ `Signature` cho thuật toán và tương thích với key thực tế.

**Bài 4.** Vì sao `getProvider()` trả một tên trước `initSign` không phải cách tốt nhất để xác minh lựa chọn provider cho HSM private key?

**Đáp án:** JDK Reference Implementation có delayed selection dựa trên key. Gọi `getProvider` quá sớm có thể chốt provider trước khi engine nhìn khóa. Khởi tạo trước rồi hỏi provider sau.

**Bài 5.** `Security.getProvider("SunEC") == null` nói lên điều gì?

**Đáp án:** Không có provider được **đăng ký dưới tên `SunEC`** trong runtime đó. Nó không tự chứng minh mọi Ed25519 implementation đều vắng mặt; có thể có provider khác hỗ trợ.

**Bài 6.** `Signature.getInstance("Ed25519", "NonExisting")` báo lỗi gì nếu tên chưa đăng ký?

**Đáp án:** `NoSuchProviderException`. Nếu tên provider có tồn tại nhưng provider không hỗ trợ `Ed25519`, lỗi đúng là `NoSuchAlgorithmException`.

**Bài 7.** Một provider có dịch vụ `Signature.Ed25519`. Có thể khẳng định nó luôn dùng được private key của HSM bất kỳ không?

**Đáp án:** Không. Dịch vụ hỗ trợ algorithm là điều kiện cần nhưng key/token có thể bị ràng buộc provider/capability. Phải kiểm tra bằng `initSign` với key thật.

**Bài 8.** Cặp khóa được tạo bằng `KeyPairGenerator.getInstance("Ed25519")`. Provider của generator có bắt buộc là provider của `Signature.getInstance("Ed25519")` không?

**Đáp án:** Không. Hai engine lựa chọn implementation độc lập; chúng thường tương thích trong JDK thông thường nhưng không thể coi đó là định luật cho mọi HSM/third-party provider.

**Bài 9.** Phép verify một message đã thay đổi trả `false`. Nên đổi sang một provider khác để nó trả `true` không?

**Đáp án:** Không. Phải kiểm tra message bytes, public key và signature đã dùng. Một provider đúng chuẩn phải từ chối chữ ký không khớp message/key.

**Bài 10.** Một hệ thống dùng `Ed25519` nhưng muốn đổi sang `Ed448`. Chỉ sửa chuỗi truyền vào `Signature.getInstance` có đủ không?

**Đáp án:** Không. Cần đổi cả cặp khóa/serialization, định dạng chữ ký, lựa chọn KeyPairGenerator/KeyFactory, hợp đồng protocol, public key phân phối cho verifier và thử nghiệm tương thích.

### Checklist kiến thức

- [ ] Tôi phân biệt **algorithm**, **JCA engine** và **security provider**.
- [ ] Tôi biết ba overload của `Signature.getInstance` và khi nào nên dùng mỗi dạng.
- [ ] Tôi xác định chính xác `Ed25519`/`Ed448` theo hợp đồng, không phụ thuộc mặc định của `EdDSA`.
- [ ] Tôi biết khám phá provider qua `Security.getProviders` và `Provider.getService`.
- [ ] Tôi không giả định `SunEC` hiện diện trong mọi JDK.
- [ ] Tôi biết cơ chế delayed provider selection trong JDK Reference Implementation và rủi ro gọi `getProvider` quá sớm.
- [ ] Tôi đọc provider **sau initSign/initVerify** khi cần quan sát implementation được sử dụng.
- [ ] Tôi biết `KeyPairGenerator` và `Signature` là các engine có lựa chọn provider riêng.
- [ ] Tôi không trộn private/public key hoặc hai biến thể EdDSA.
- [ ] Tôi phân biệt `NoSuchAlgorithmException`, `NoSuchProviderException` và `InvalidKeyException`.
- [ ] Tôi có thể chạy ví dụ chọn tự động và ví dụ cố định `SunEC` với stdout dự kiến.
- [ ] Tôi biết cách xử lý không khả dụng provider/HSM theo **chính sách bảo mật**, không fallback ngầm.

## Tài liệu chính thức, còn áp dụng

1. [Java SE 25 — `java.security.Signature`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): ba overload `getInstance`, `getProvider`, `initSign`, `initVerify`, `sign`, `verify` và các ngoại lệ.
2. [Java SE 25 — `java.security.Security`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Security.html): quản lý và truy vấn providers, `getProviders`/`getProvider`.
3. [Java SE 25 — `java.security.Provider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Provider.html): danh mục services và `getService`.
4. [Java SE 25 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên `Ed25519`, `Ed448`, `EdDSA` của `Signature` và `KeyPairGenerator`.
5. [Oracle JDK 25 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html): các dịch vụ EdDSA do `SunEC` cung cấp trong Oracle/OpenJDK.
6. [Oracle JDK 25 — PKCS#11 Reference Guide](https://docs.oracle.com/en/java/javase/25/security/pkcs11-reference-guide1.html): **delayed provider selection**, khả năng khóa token không xuất được và lưu ý `getProvider` sau khởi tạo.
7. [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): cơ chế EdDSA đã được đưa vào Java 15.
8. [RFC 8032 — EdDSA](https://www.rfc-editor.org/rfc/rfc8032): đặc tả Ed25519 và Ed448.

**Kết luận:** `Signature.getInstance("Ed25519")` nêu **thuật toán cần dùng**; provider là **implementation** được JCA chọn hoặc do ứng dụng chỉ định. Với ứng dụng thông thường, để JCA lựa chọn và kiểm tra `getProvider()` **sau khi khởi tạo bằng khóa** là cách ít phụ thuộc môi trường. Chỉ cố định provider bằng tên hoặc object khi có yêu cầu rõ ràng về khóa, HSM, kiểm định hoặc vận hành; dù `getInstance` thành công, vẫn phải kiểm tra sự tương thích của khóa và xác minh chữ ký trên **cùng message bytes**.