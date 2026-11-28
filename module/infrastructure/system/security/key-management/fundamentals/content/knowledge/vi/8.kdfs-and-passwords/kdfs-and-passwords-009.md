# Pepper — Bí mật bổ sung trong bảo vệ mật khẩu

## 1. Pepper là gì?

**Pepper** là một **bí mật do hệ thống quản lý**, được đưa vào quy trình xử lý mật khẩu nhằm bổ sung một lớp bảo vệ cho giá trị dùng để xác minh mật khẩu. Khác với **salt**, pepper phải được giữ bí mật và **không lưu chung với cơ sở dữ liệu chứa các bản ghi mật khẩu đã băm**. Pepper thường là một khóa ngẫu nhiên có entropy cao, được giữ trong hệ thống quản lý bí mật, KMS hoặc HSM.

Ví dụ, một ứng dụng Java lưu các bản ghi gồm tên người dùng, salt và kết quả của hàm băm mật khẩu Argon2id. Khi cơ sở dữ liệu bị sao chép, kẻ tấn công có thể thực hiện thử đoán mật khẩu ngoại tuyến nếu đủ tài nguyên. Nếu thiết kế còn dùng **pepper được bảo vệ ở một miền khác**, người chỉ có dữ liệu từ database sẽ thiếu một đầu vào bí mật cần thiết để kiểm tra các phỏng đoán theo đúng quy trình của ứng dụng.

Pepper **không thay thế** một thuật toán băm mật khẩu chuyên dụng, salt ngẫu nhiên hoặc kiểm soát truy cập. Nó là một **lớp phòng vệ bổ sung** với chi phí vận hành riêng: bảo vệ pepper, duy trì tính sẵn sàng để đăng nhập, phân quyền cho các dịch vụ và xử lý xoay vòng khi pepper bị lộ.

Trong chương **KDF và mật khẩu** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, học pepper giúp kết nối password hashing/KDF với quản lý khóa mật mã: từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**, cùng cơ chế KMS/HSM, envelope encryption, phân quyền và kiểm toán. Điểm quan trọng là xác định rõ **pepper là bí mật bảo vệ điều gì và kẻ tấn công có thể tiếp cận những thành phần nào**.

> **Nguyên tắc:** Salt được lưu cùng bản ghi mật khẩu; pepper được giữ ở một ranh giới bảo vệ khác. Cả hai phải được dùng cùng một **password hashing function** phù hợp, thay vì lưu mật khẩu ở dạng rõ hoặc chỉ dùng SHA-256 trực tiếp.

## 2. Phân biệt password, salt, pepper và password hash

| Thành phần | Mục đích | Có cần bí mật? | Vị trí lưu thường gặp |
| --- | --- | --- | --- |
| **Password** | Bí mật do người dùng cung cấp để xác thực | **Có** | Chỉ tồn tại tạm thời trong quá trình xử lý, không lưu plaintext |
| **Salt** | Giá trị ngẫu nhiên riêng cho từng mật khẩu/bản ghi; ngăn các bản ghi dùng cùng mật khẩu có cùng kết quả và hạn chế bảng tra cứu dựng sẵn | **Không** | Cùng bản ghi password hash |
| **Pepper** | Bí mật cấp hệ thống hoặc phạm vi dịch vụ, được dùng thêm trong bước tính/kiểm tra hash | **Có** | Tách khỏi database password hash, như secret manager/KMS/HSM |
| **Password hash / verifier** | Kết quả tính bằng password hashing function để kiểm tra mật khẩu | Không phải plaintext; vẫn là dữ liệu nhạy cảm | Database, kèm thuật toán, tham số, salt, phiên bản |
| **Key ID / pepper version** | Chỉ ra phiên bản pepper cần dùng để kiểm tra | Thường **không bí mật** | Metadata đi kèm bản ghi hoặc registry có kiểm soát |

### 2.1. Salt xử lý vấn đề nào?

Nếu hai người dùng đặt cùng mật khẩu và hệ thống dùng hàm băm thông thường không có salt, hai bản ghi có thể có cùng giá trị hash. Salt ngẫu nhiên riêng cho từng bản ghi giúp:

- Cùng một mật khẩu cho các bản ghi khác nhau tạo ra kết quả khác nhau.
- Hạn chế việc sử dụng bảng băm mật khẩu dựng sẵn (precomputed/rainbow tables).
- Buộc kẻ tấn công thường phải xử lý từng salt hoặc từng bản ghi khi thử đoán.

Salt **không cần bí mật**. Hầu hết định dạng lưu password hash chuẩn chứa salt cùng tham số và kết quả hash. Salt nên được tạo bằng **CSPRNG** và đủ dài theo yêu cầu của thuật toán/chính sách, chẳng hạn 16 byte ngẫu nhiên khi sử dụng Argon2id.

### 2.2. Pepper xử lý vấn đề nào?

Pepper cung cấp một bí mật **ngoài cơ sở dữ liệu** để kẻ chỉ có bản dump database không thể tái tạo toàn bộ quá trình xác minh mật khẩu. Trong một thiết kế tốt, pepper có thể giảm rủi ro **offline password cracking sau khi chỉ database bị lộ**.

Pepper **không giúp** khi kẻ tấn công đã có cả cơ sở dữ liệu lẫn pepper, hoặc kiểm soát được dịch vụ có quyền gọi một API sử dụng pepper không bị hạn chế. Trong những trường hợp đó, sức kháng dò đoán vẫn phụ thuộc đáng kể vào **mật khẩu, password hashing function, tham số chi phí, rate limiting và bảo vệ hệ thống**.

### 2.3. Pepper không phải gia vị thêm vào salt

Không nên dùng một chuỗi cố định dễ đoán như tên ứng dụng, domain, timestamp hoặc chuỗi hardcode ở source làm pepper. Những giá trị công khai hoặc có thể truy cập cùng database **không tạo thêm ranh giới bí mật**.

Pepper thực sự cần được **sinh ngẫu nhiên**, có **quyền truy cập và vòng đời riêng**. Không dùng cùng một pepper cho mọi hệ thống độc lập nếu việc chia sẻ đó tạo ra phạm vi ảnh hưởng quá lớn.

## 3. Mô hình đe dọa: pepper giúp đến đâu?

| Tình huống tấn công | Pepper có tác dụng gì? | Điều vẫn phải làm |
| --- | --- | --- |
| Kẻ tấn công chỉ sao chép bảng user và password hash | Thiếu pepper để kiểm tra chính xác các phỏng đoán theo thiết kế, làm giảm khả năng cracking ngoại tuyến | Dùng Argon2id/scrypt/PBKDF2 đúng tham số, salt từng bản ghi; giới hạn dữ liệu được xuất |
| Database và pepper đều bị lộ | Lớp bí mật bổ sung đã mất hiệu lực | Tham số password hashing mạnh, thông báo/xử lý sự cố, đổi pepper và reset mật khẩu khi cần |
| Ứng dụng bị chiếm quyền và có thể gọi dịch vụ sử dụng pepper | Kẻ có thể lạm dụng quyền hợp lệ, biến dịch vụ thành một oracle hỗ trợ thử đoán | Least privilege, kiểm soát API, chống brute force, giám sát và cô lập sự cố |
| Kẻ tấn công chỉ gửi yêu cầu login từ Internet | Pepper không tự ngăn thử mật khẩu online | Rate limiting, MFA, bảo vệ phiên, phát hiện credential stuffing |
| Secret manager/KMS ngừng hoạt động hoặc pepper bị mất | Đăng nhập có thể thất bại vì không tính/kiểm tra được hash | Độ sẵn sàng, backup/khôi phục được kiểm soát, quy trình khôi phục đã thử |
| Một người dùng đặt mật khẩu quá yếu | Pepper làm khó hơn trong một số tình huống rò database nhưng không cải thiện chất lượng mật khẩu | Chính sách mật khẩu, bảo vệ đăng nhập và khuyến nghị chống mật khẩu bị lộ |

**Không được khẳng định pepper khiến password hash “không thể bị crack”.** Đây là một lớp phòng vệ theo **mô hình đe dọa cụ thể**. Nếu pepper bị lộ, kẻ tấn công có thể quay về bài toán thử đoán mật khẩu như khi không còn bí mật bổ sung.

## 4. Hai cách tích hợp pepper vào password hashing

Có nhiều cách thiết kế, nhưng hai nhóm phổ biến cần phân biệt là **pre-hashing pepper** và **post-hashing pepper**. Bất kể chọn cách nào, phải mô tả rõ thứ tự thao tác và định dạng dữ liệu để tất cả phiên bản của hệ thống xác minh nhất quán.

### 4.1. Pre-hashing: xử lý password bằng HMAC có pepper trước KDF

Một kiến trúc khái niệm:

~~~text
pepperKey = bí mật ngẫu nhiên trong KMS/HSM/secret manager
salt = CSPRNG.generate(16 bytes)             # riêng từng bản ghi

prehash = HMAC-SHA-256(key=pepperKey, data=passwordBytes)
verifier = Argon2id(prehash, salt, memoryCost, timeCost, parallelism)

Lưu ở database:
    algorithm = Argon2id
    parameters = {memoryCost, timeCost, parallelism, outputLength}
    salt
    verifier
    pepperId = v3

Không lưu ở database:
    plaintext password
    pepperKey
    bản sao plaintext prehash nếu không cần thiết
~~~

**Giải thích:**

- **HMAC** là cơ chế có khóa bí mật; không dùng phép nối đơn giản **SHA-256(pepper || password)** như một thiết kế tự chế.
- **Argon2id** là một password hashing/KDF được thiết kế để tăng chi phí kiểm tra phỏng đoán, đặc biệt có tham số bộ nhớ. Salt vẫn bắt buộc ngay cả khi có pepper.
- Nếu thư viện Argon2id nhận **binary password input**, có thể đưa trực tiếp byte prehash vào. Nếu API chỉ nhận chuỗi, phải quy định chính xác encoding không nhập nhằng và kiểm tra cách thư viện xử lý, tránh các chuyển đổi làm thay đổi byte đầu vào.
- **Pepper ID** là nhãn chọn phiên bản trong tập khóa đã được cho phép; nó **không phải bí mật** và không tự tạo quyền sử dụng pepper khác.

Sơ đồ luồng:

~~~mermaid
flowchart TD
    PW["Password người dùng nhập"] --> MAC["HMAC-SHA-256<br/>Pepper giữ ngoài database"]
    PEPPER["Pepper trong KMS/HSM<br/>hoặc secret manager"] --> MAC
    MAC --> ARGON["Argon2id<br/>Salt riêng từng bản ghi + cost"]
    SALT["Salt ngẫu nhiên"] --> ARGON
    ARGON --> DB["Database: verifier + salt<br/>tham số + pepperId"]
~~~

**Lưu ý:** Kiến trúc này không phải một giao thức duy nhất được mọi thư viện tự động hỗ trợ. Cần chọn cách xử lý binary/encoding, giới hạn tài nguyên, cấu hình và lưu phiên bản theo một đặc tả triển khai thống nhất.

### 4.2. Post-hashing: dùng HMAC sau bước password hashing

Một mô hình khác:

~~~text
rawHash = Argon2id(passwordBytes, salt, parameters)
storedTag = HMAC-SHA-256(key=pepperKey, data=domain || rawHash)

Database giữ:
    storedTag, salt, parameters, pepperId, version
Database không giữ:
    rawHash dùng làm đầu vào HMAC, nếu mục tiêu là bảo vệ trước rò database
~~~

Khi đăng nhập, hệ thống tính lại **rawHash** từ mật khẩu người dùng và salt, sau đó HMAC bằng đúng pepper và so sánh **storedTag** một cách an toàn.

**Cảnh báo thiết kế quan trọng:** Nếu lưu **rawHash** cùng database rồi chỉ thêm một HMAC tag bên cạnh, kẻ lấy được database vẫn có thể thử đoán mật khẩu ngoại tuyến trực tiếp với rawHash. Khi đó pepper **không đạt mục tiêu ngăn việc xác minh phỏng đoán từ một bản dump database**. Phải đánh giá chính xác vật liệu nào được lưu và đường xác minh nào vẫn có thể bị dùng để kiểm tra mật khẩu.

Trong mô hình post-hash chỉ lưu HMAC tag, không thể đổi pepper cho tất cả tài khoản bằng cách HMAC lại **rawHash** nếu không còn giữ rawHash. Thường phải có **mật khẩu người dùng khi đăng nhập lại** hoặc quy trình reset phù hợp. Đây cũng là một lý do rotation cần được tính trước.

### 4.3. So sánh hai cách

| Tiêu chí | Pre-hash HMAC rồi Argon2id | Argon2id rồi post-hash HMAC |
| --- | --- | --- |
| Đầu vào bí mật của pepper | Mật khẩu trước khi qua KDF | Kết quả KDF |
| Bản ghi lưu | Verifier Argon2id, salt, tham số, pepper ID | Chỉ tag HMAC trên raw hash, salt, tham số, pepper ID |
| Khi lộ database nhưng chưa lộ pepper | Không có đủ đầu vào để xác minh dự đoán mật khẩu theo công thức | Không có raw hash/tag mới để xác minh dự đoán theo công thức |
| Khi rotate pepper | Thường cần mật khẩu khi đăng nhập lại hoặc reset | Cũng cần password nếu không lưu raw hash |
| Điểm phải kiểm soát | HMAC input/encoding, memory-hard KDF, version | Không lưu thêm rawHash có thể crack trực tiếp, domain separation và so sánh tag |

Hai cách đều **có thể** là lựa chọn hợp lý nếu được triển khai cẩn thận. Việc chọn cách nào phụ thuộc thư viện, hệ thống hiện tại, khả năng KMS/HSM và yêu cầu migration. Không tự trộn nhiều kiểu không có đặc tả, vì bên gửi và bên xác minh có thể tính khác nhau hoặc làm lộ đường kiểm tra mật khẩu không cần pepper.

## 5. Chọn KDF và tham số khi dùng pepper

Pepper không phải lý do để dùng hàm băm mật khẩu quá nhanh hoặc bỏ salt. Nên ưu tiên **password hashing function** có khả năng cấu hình chi phí phù hợp với môi trường và tiêu chuẩn áp dụng.

| Thuật toán | Đặc tính | Vai trò của pepper |
| --- | --- | --- |
| **Argon2id** | Memory-hard; cấu hình bộ nhớ, số vòng và song song hóa | Pepper có thể được dùng qua HMAC pre-hash hoặc post-hash theo thiết kế |
| **scrypt** | Memory-hard, hỗ trợ tham số chi phí bộ nhớ/tính toán | Pepper vẫn được giữ ở miền riêng, không thay salt |
| **PBKDF2-HMAC-SHA-256** | Phổ biến trong một số hệ sinh thái, cấu hình số vòng | Có thể tích hợp pepper; số vòng cần đáp ứng chính sách và benchmark |
| **SHA-256(password)** | Quá nhanh để làm password hash cho tài khoản thông thường | **Không trở nên phù hợp chỉ nhờ có pepper** |

Khi cấu hình Argon2id, cần chọn **memory cost, time cost, parallelism, output length** thông qua tiêu chuẩn/chính sách và benchmark trên hạ tầng triển khai. Tham số quá thấp tạo điều kiện thử đoán ngoại tuyến; tham số quá cao có thể khiến đăng nhập gây quá tải CPU/RAM và trở thành điểm tấn công từ chối dịch vụ.

Một ví dụ về metadata lưu hash:

~~~text
hashAlgorithm: Argon2id
hashParameters: {memoryKiB: 65536, iterations: 3, parallelism: 1}
salt: <16 bytes ngẫu nhiên, có thể công khai>
verifier: <kết quả KDF hoặc MAC, tùy scheme>
pepperId: pepper-auth-prod-v3
schemeVersion: 2
~~~

**Các tham số trên chỉ để minh họa cấu trúc dữ liệu, không là cấu hình bắt buộc cho mọi hệ thống.** Cần đo hiệu năng và cập nhật theo hướng dẫn áp dụng tại thời điểm triển khai.

### 5.1. Vì sao không sử dụng pepper làm salt?

Salt nên **riêng cho từng bản ghi** và được lưu cùng hash để thuật toán có thể xác minh lại. Pepper thường **được chia sẻ trong một phạm vi** và phải giữ bí mật. Dùng một pepper duy nhất thay salt sẽ đánh mất đặc tính phân biệt các bản ghi cùng mật khẩu.

Nếu mỗi tài khoản có cả salt ngẫu nhiên riêng và pepper thuộc một phiên bản hệ thống, hai cơ chế cùng phục vụ mục tiêu khác nhau: salt giảm lợi thế của bản hash trùng lặp và tiền tính, còn pepper bổ sung bí mật ngoài database.

## 6. Thực hành Java: bước pre-hash bằng HMAC-SHA-256

JDK có sẵn API **javax.crypto.Mac** và **SecureRandom**, nhưng **Argon2id không phải một API password hashing chuẩn có sẵn trên mọi bản JDK**. Ví dụ Java dưới đây minh họa **bước tạo salt và HMAC bằng pepper**; phần Argon2id cần dùng thư viện được thẩm định, cấu hình đúng và kiểm soát toàn bộ quy trình lưu/xác minh.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class PepperPrehashDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private PepperPrehashDemo() {}

    // Chỉ dùng khi khởi tạo pepper mới.
    // Production: đưa pepper tới kho bí mật/KMS/HSM qua quy trình an toàn.
    static byte[] newPepper() {
        byte[] pepper = new byte[32];
        RNG.nextBytes(pepper);
        return pepper;
    }

    // Salt riêng cho mỗi bản ghi mật khẩu.
    static byte[] newSalt() {
        byte[] salt = new byte[16];
        RNG.nextBytes(salt);
        return salt;
    }

    static byte[] prehashPassword(char[] password, byte[] pepper)
            throws Exception {
        if (pepper == null || pepper.length != 32) {
            throw new IllegalArgumentException("Invalid pepper length");
        }
        if (password == null) {
            throw new IllegalArgumentException("Password required");
        }

        // Tránh tạo String plaintext từ password nếu có thể.
        ByteBuffer encoded = StandardCharsets.UTF_8
                .encode(CharBuffer.wrap(password));
        byte[] passwordBytes = new byte[encoded.remaining()];
        encoded.get(passwordBytes);

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(pepper, "HmacSHA256"));
            return mac.doFinal(passwordBytes);
        } finally {
            Arrays.fill(passwordBytes, (byte) 0);
            if (encoded.hasArray()) {
                Arrays.fill(encoded.array(), (byte) 0);
            }
        }
    }
}
~~~

**Cách kết nối với Argon2id (mã giả, API phụ thuộc thư viện):**

~~~text
// Khi đăng ký hoặc đổi mật khẩu:
pepper = secretProvider.getPepper("pepper-auth-prod-v3")
salt = CSPRNG.generate(16 bytes)
prehash = PepperPrehashDemo.prehashPassword(passwordChars, pepper)
verifier = Argon2id.hashRaw(prehash, salt, approvedParameters)
save(userId, salt, approvedParameters, verifier, "pepper-auth-prod-v3")

// Khi xác minh đăng nhập:
record = loadUserPasswordRecord(userId)
pepper = secretProvider.getApprovedPepper(record.pepperId)
prehash = PepperPrehashDemo.prehashPassword(passwordChars, pepper)
candidate = Argon2id.hashRaw(prehash, record.salt, record.parameters)
valid = constantTimeEqual(candidate, record.verifier)
if valid:
    authorizeLoginAccordingToAccountPolicy()
else:
    rejectWithGenericAuthenticationError()
~~~

**Những lưu ý kỹ thuật:**

1. Không ghi **password, pepper, prehash, verifier đang thử** hoặc bí mật KMS vào log. Khi có thể, hạn chế bản sao byte và xóa mảng tạm sau sử dụng. Java/JVM không bảo đảm xóa mọi bản sao dữ liệu bí mật khỏi bộ nhớ.
2. Đoạn Java minh họa nhận **pepper dạng byte**. Một KMS/HSM có khóa HMAC **non-exportable** có thể yêu cầu gọi API **GenerateMac** thay vì xuất bytes; không nên hạ chính sách HSM chỉ để dùng trực tiếp SecretKeySpec.
3. Cần quy định chính xác **mã hóa Unicode/UTF-8**, chính sách normalization (nếu có) và độ dài mật khẩu; thay đổi quy tắc giữa đăng ký và đăng nhập sẽ khiến việc xác minh thất bại.
4. Với HMAC-SHA-256, 32 byte pepper ngẫu nhiên là một lựa chọn phổ biến cho ví dụ. **Không suy ra mọi thuật toán KMS đều hỗ trợ khóa HMAC 256 bit**; kiểm tra key spec và policy thực tế.
5. Khi verify, dùng **so sánh hằng thời gian theo nội dung** cho đầu ra cùng độ dài (ví dụ MessageDigest.isEqual trong Java), tránh trả kết quả sai ngay khi một byte đầu tiên khác.
6. **Không lấy pepper ID tùy ý do client cung cấp** để mở quyền truy cập bí mật. Pepper ID đến từ metadata bản ghi và phải được ánh xạ qua danh sách khóa/phiên bản mà dịch vụ được phép sử dụng.

### 6.1. Vì sao không viết toàn bộ Argon2id bằng Java thuần?

Password hashing function phức tạp không nên tự triển khai từ đầu. Nên dùng thư viện Argon2id được duy trì và kiểm chứng, chọn phiên bản/parameters rõ ràng và xác minh đầu ra bằng test vector của thư viện. Khi dựa vào KMS/HSM, cần đọc đúng hợp đồng API về chức năng MAC, xuất khóa và giới hạn gọi để thiết kế vừa bảo mật vừa hoạt động được.

## 7. Kiến trúc lưu trữ pepper trong hệ thống

~~~mermaid
flowchart TD
    U["Client gửi yêu cầu đăng nhập qua TLS"] --> API["Authentication Service"]
    API --> DB["User DB<br/>Salt + verifier + pepperId + params"]
    API --> SECRETS["Secret manager / KMS / HSM<br/>Pepper hoặc thao tác HMAC"]
    DB --> VERIFY["Tái tính prehash + Argon2id<br/>So sánh verifier"]
    SECRETS --> VERIFY
    VERIFY --> AUTH{"Mật khẩu hợp lệ<br/>và tài khoản được phép?"}
    AUTH -->|"Có"| OK["Cấp phiên theo chính sách"]
    AUTH -->|"Không"| DENY["Từ chối + rate limit"]
    API --> AUDIT["Audit metadata<br/>Không log pepper/password"]
~~~

### 7.1. Secret manager, KMS và HSM

Có nhiều cách lưu pepper với mức kiểm soát khác nhau:

- **Secret manager:** Giữ một bí mật ngẫu nhiên được mã hóa, cấp cho workload được phép thông qua định danh/mạng/kênh an toàn. Cần kiểm soát cache, quyền đọc, log và việc cấp phát qua môi trường.
- **KMS/HSM quản lý khóa HMAC:** Nếu có API phù hợp, có thể yêu cầu dịch vụ tính **HMAC** mà không xuất pepper ra ứng dụng. Tuy nhiên, ứng dụng có quyền gọi API cần được bảo vệ và giới hạn để tránh trở thành **oracle** phục vụ thử đoán.
- **Pepper được wrap bởi KEK:** Có thể dùng **envelope encryption** để bảo vệ pepper ở trạng thái lưu trữ, trong đó KEK được bảo vệ trong KMS/HSM. Sau khi unwrap, ứng dụng vẫn phải bảo vệ pepper khi sử dụng trong RAM. Phải phân biệt **KEK bảo vệ pepper** với **pepper dùng trong công thức hash**.

**Pepper không nên nằm cùng ranh giới xâm nhập với database backup.** Chẳng hạn, để pepper trong cùng một bảng người dùng hoặc dump database không đáp ứng mục tiêu tách biệt; đặt pepper cố định trong mã nguồn hoặc container image cũng dễ khiến các bản sao của ứng dụng làm lộ bí mật.

### 7.2. Quyền truy cập theo nguyên tắc tối thiểu

Nên giới hạn:

- Chỉ dịch vụ xác thực được phép **sử dụng pepper hiện hành** hoặc yêu cầu phép HMAC cho mục đích xác thực.
- Dịch vụ analytics, báo cáo, quản trị người dùng thông thường không cần quyền đọc pepper.
- Người quản trị KMS/secret manager không mặc nhiên được đăng nhập thay người dùng; quyền quản trị, quyền sử dụng và quyền export nên tách biệt.
- Pepper của **production** không được sử dụng trong development/test; có thể tách thêm theo tenant hoặc miền bảo mật khi cần giảm phạm vi sự cố.
- Các sự kiện đọc/thay quyền/rotate pepper phải được kiểm toán; log chứa **key ID, actor/workload, thời điểm, hành động và kết quả**, không chứa bí mật.

**Dùng HSM không tự động ngăn tài khoản ứng dụng bị chiếm quyền.** Một workload vẫn có thể gọi HMAC hợp lệ nếu chính sách cho phép. Cần theo dõi tần suất, nguồn gọi, danh tính, lỗi, rate limiting và phát hiện hành vi bất thường.

### 7.3. Tính sẵn sàng

Nếu không lấy được pepper hoặc không gọi được API MAC, ứng dụng **không thể xác minh mật khẩu** của các tài khoản phụ thuộc phiên bản đó theo quy trình đang sử dụng.

Do đó, hệ thống cần:

- Kế hoạch độ sẵn sàng, kết nối, dự phòng và khôi phục theo khả năng nhà cung cấp.
- Sao lưu hoặc quy trình phục hồi pepper được phê duyệt với mức bảo vệ tương đương, thử định kỳ và ghi nhận người chịu trách nhiệm.
- Chính sách timeout/cache có kiểm soát; cache kéo dài hoặc đặt pepper ở nhiều nơi tăng bề mặt lộ bí mật.
- **Fail closed:** Không bỏ qua bước pepper, không chuyển sang hash không có pepper, không cho đăng nhập mặc định chỉ vì KMS/secret manager lỗi.

## 8. Vòng đời pepper: tạo, cấp phát, sử dụng, xoay vòng, thu hồi và hủy

| Giai đoạn | Kiểm soát cần có | Lỗi thiết kế dễ gặp |
| --- | --- | --- |
| **Tạo** | Sinh pepper bằng CSPRNG/KMS/HSM; định rõ thuật toán, độ dài, miền, owner và key ID | Chuỗi hardcode hoặc dễ đoán, dùng chung cho mọi môi trường |
| **Cấp phát** | Cấp cho đúng auth workload bằng kênh được xác thực, giới hạn quyền đọc/sử dụng | Đưa pepper vào Git, pipeline log, chat hoặc cùng database dump |
| **Lưu trữ** | Giữ ngoài database, có bảo vệ at rest, kiểm soát backup và quyền | Mất ranh giới tách biệt do cùng bản backup/snapshot |
| **Sử dụng** | Thực thi HMAC/KDF đúng phiên bản, giới hạn truy cập, chống brute force | Bỏ salt, đổi encoding không kiểm soát, log prehash hoặc dùng thuật toán hash quá nhanh |
| **Xoay vòng** | Tạo phiên bản mới, giữ đường verify phiên bản cũ trong cửa sổ cần thiết, migrate trên login/reset | Thay pepper rồi khiến toàn bộ người dùng không đăng nhập được |
| **Thu hồi** | Khi lộ key, đánh giá phạm vi ảnh hưởng, chặn quyền, giảm thời gian chấp nhận bản cũ | Chỉ đổi tên key hoặc xóa một instance, còn cache/bản sao có quyền dùng |
| **Hủy** | Chắc chắn không còn bản ghi cần pepper cũ và hết nghĩa vụ khôi phục; xử lý bản sao theo chính sách | Hủy sớm khiến các tài khoản chưa migrate mất khả năng xác minh |

### 8.1. Vì sao xoay vòng pepper khó hơn đổi khóa mã hóa?

Với một số **DEK/KEK**, hệ thống có thể unwrap và rewrap vật liệu khóa mà không cần dữ liệu plaintext của người dùng. Nhưng **password hash là hàm một chiều**: từ verifier đã lưu, thông thường không thể khôi phục lại mật khẩu để tính lại hash bằng pepper mới.

Vì vậy, đổi pepper thường cần **mật khẩu được người dùng cung cấp khi đăng nhập hợp lệ**, hoặc quy trình buộc đặt lại mật khẩu. Không thể giả định chỉ cần chạy một lệnh “đổi khóa” trên database là tất cả verifier được chuyển đổi an toàn.

### 8.2. Chiến lược rotation theo phiên bản

Giả sử hệ thống đang dùng **pepper v1** và muốn chuyển sang **v2**:

1. **Tạo v2** bằng nguồn ngẫu nhiên an toàn; đăng ký key ID, quyền, audit và kiểm thử đường sử dụng.
2. **Bắt đầu tạo verifier mới bằng v2** khi đăng ký hoặc đổi mật khẩu.
3. Với bản ghi cũ, **chọn v1 theo pepperId được lưu trên server** và xác minh mật khẩu người dùng đưa vào.
4. Nếu xác minh thành công, **tính verifier mới từ mật khẩu vừa nhập bằng v2 và salt mới** theo chính sách, rồi cập nhật bản ghi theo giao dịch có kiểm soát.
5. Theo dõi tỷ lệ bản ghi còn dùng v1, kiểm tra khả năng rollback/khôi phục và điều phối những instance vẫn sử dụng v1.
6. Với tài khoản không đăng nhập trong thời gian chuyển đổi, thực hiện quy trình **reset mật khẩu hoặc xác minh danh tính lại** theo chính sách, thay vì giữ pepper cũ vô hạn.
7. Chỉ vô hiệu hóa/hủy v1 khi không còn bản ghi cần xác minh bằng nó và yêu cầu khôi phục đã được giải quyết.

~~~mermaid
flowchart TD
    A["Người dùng đăng nhập bằng mật khẩu"] --> B["Đọc verifier, salt, pepperId"]
    B --> C["Dùng pepper thuộc phiên bản được phép"]
    C --> V{"Xác minh mật khẩu hợp lệ?"}
    V -->|"Không"| F["Từ chối; rate limit"]
    V -->|"Có, key đã mới"| L["Tiếp tục kiểm tra quyền/MFA"]
    V -->|"Có, pepper cũ"| R["Tính lại hash với pepper mới<br/>và salt mới"]
    R --> U["Ghi bản ghi mới có phiên bản<br/>bằng thao tác có kiểm soát"]
    U --> L
~~~

**Nếu pepper v1 bị lộ:** Không giữ cửa sổ dùng v1 dài mà không đánh giá tác động. Cần quyết định mức độ khẩn cấp, biện pháp giảm thiểu tức thời, reset các tài khoản còn phụ thuộc v1 khi cần, xử lý các bản sao/bộ nhớ và điều tra quyền bị chiếm. Việc có một bản hash mới không thu hồi các mật khẩu mà kẻ tấn công đã đoán được trước đó.

### 8.3. Rủi ro của việc giữ cả pepper cũ và mới

Giữ pepper cũ giúp không gián đoạn đăng nhập, nhưng **mở rộng thời gian một bí mật cũ còn hiệu lực**. Nếu bí mật cũ đã bị xâm phạm, cần cân nhắc dừng xác minh bằng v1 và kích hoạt reset, thay vì cho phép fallback tự động quá lâu.

Pepper ID là metadata để định tuyến **trong tập khóa được phê duyệt**, không phải tín hiệu do client tự chọn để yêu cầu phiên bản yếu hơn. Audit cần phân biệt rõ yêu cầu xác minh v1, v2 và các thao tác thay trạng thái key.

## 9. Tình huống hệ thống Java với database và KMS

Giả sử một nền tảng nhiều tenant sử dụng Java để đăng nhập. Mỗi bản ghi người dùng có salt Argon2id riêng. Pepper được tạo và quản lý trong KMS/HSM hoặc kho bí mật có khả năng bảo vệ tương đương.

**Thiết kế đề xuất ở mức khái niệm:**

1. Dịch vụ xác thực duy nhất có quyền truy xuất/call API sử dụng pepper cho miền tenant phù hợp.
2. Password và salt đi vào hàm được định nghĩa rõ, ví dụ **HMAC-SHA-256(pepper, passwordBytes) → Argon2id(salt)**.
3. Database lưu **verifier, salt, cost parameters, schemeVersion và pepperId**; không lưu raw password hoặc pepper.
4. Đường đăng nhập có **rate limiting, khóa/mở khóa hợp lý, MFA khi cần, kiểm tra trạng thái tài khoản và cảnh báo bất thường**.
5. Khi rotate, cập nhật bản ghi trên đăng nhập thành công hoặc đi qua quy trình reset; phiên bản cũ được quản lý theo thời hạn.
6. Audit log lưu key ID, request ID, actor/workload và kết quả ở mức phù hợp; không ghi nội dung mật khẩu, pepper, prehash hay dữ liệu xác thực nhạy cảm.
7. Thử kịch bản **rò database**, **lộ quyền secret manager**, **KMS outage** và **pepper mất/thu hồi** trước khi đưa vào vận hành.

**Các trường hợp kiểm thử tư duy:**

| Sự kiện | Hành vi đúng của hệ thống |
| --- | --- |
| Hai tài khoản dùng cùng password | Salt khác nhau, verifier khác nhau theo thiết kế |
| Kẻ chỉ có database dump | Không có pepper để tự tái tạo đường Verify đầy đủ |
| Pepper ID trong request bị thay đổi | Hệ thống không dùng phiên bản do client tùy ý chọn |
| Secret manager tạm lỗi | Từ chối xác thực có kiểm soát; cảnh báo và áp dụng quy trình khôi phục |
| Password đúng nhưng bản ghi còn dùng v1 | Verify bằng v1 theo quyền, sau đó migrate sang v2 khi chính sách cho phép |
| Pepper v1 bị xác nhận đã lộ | Hạn chế/ngừng v1, điều tra, yêu cầu reset/migrate theo mức độ rủi ro |
| App có quyền dùng pepper nhưng bị chiếm | Phạm vi ảnh hưởng được giới hạn bằng quyền, giám sát, throttling và tách tenant |

## 10. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Xem pepper là salt và lưu trong bảng user | Kẻ có database lấy luôn bí mật bổ sung | Lưu pepper tách biệt; vẫn dùng salt ngẫu nhiên từng bản ghi |
| Hardcode pepper trong Git hoặc container image | Secret có thể bị lấy từ code/build/artifact | Dùng secret manager hoặc KMS/HSM, giới hạn quyền và rotation |
| Dùng SHA-256(password + pepper) thay password hashing chuyên dụng | Tính toán quá nhanh, cấu trúc tự chế | Dùng Argon2id/scrypt/PBKDF2 phù hợp và HMAC khi tích hợp pepper |
| Đặt cùng pepper cho mọi miền không liên quan | Sự cố một miền ảnh hưởng hàng loạt | Tách theo môi trường, ứng dụng/tenant khi hợp lý |
| Lưu raw Argon2id hash kèm post-hash HMAC tag | Kẻ lấy database có thể cracking offline bằng raw hash | Chỉ lưu verifier đúng scheme; không để lộ đường xác minh bỏ qua pepper |
| Lưu pepper vào log, crash report hoặc backup DB | Mất lợi ích bảo vệ ngoài database | Kiểm soát logging, dump, backup và truy cập bí mật |
| Tin rằng pepper chặn mọi brute force | Không giải quyết đoán mật khẩu online hoặc oracle từ ứng dụng bị chiếm | Rate limiting, MFA, quyền tối thiểu và phát hiện tấn công |
| Mất pepper nhưng cho đăng nhập qua hash không pepper | Bỏ lớp bảo vệ khi hệ thống lỗi | Fail closed và khôi phục pepper theo quy trình |
| Rotate pepper nhưng không lưu key version | Không xác minh được tài khoản cũ hoặc không thể migrate | Lưu pepperId/schemeVersion và chính sách thời gian chuyển đổi |
| Đổi pepper trong database mà không có mật khẩu | Verifier cũ không thể được đổi đúng theo hàm một chiều | Rehash sau đăng nhập hoặc reset được kiểm soát |
| Không giới hạn việc gọi HMAC trong KMS/HSM | App bị chiếm có thể lạm dụng quyền làm oracle | Giới hạn IAM, bối cảnh, tần suất, cảnh báo và giám sát |
| Đếm lỗi mật khẩu khác nhau theo đường xử lý hoặc trả thông báo quá chi tiết | Có thể tiết lộ thông tin tài khoản/phiên bản hoặc tạo oracle phụ | Cấu trúc phản hồi xác thực nhất quán và kiểm soát side channel |

## 11. Checklist thiết kế pepper

Trước khi triển khai, hãy xác nhận:

1. **Threat model:** Pepper được thêm để giảm rủi ro nào: database dump, backup bị lộ hay sự cố khác?
2. **Hashing:** Có dùng password hashing function phù hợp với salt ngẫu nhiên riêng, tham số chi phí được đo và cập nhật không?
3. **Scheme:** Pre-hash hay post-hash? Thứ tự HMAC/KDF, encoding, domain separation và kết quả lưu đã được đặc tả rõ chưa?
4. **Nguồn sinh:** Pepper được tạo bằng CSPRNG/KMS/HSM đủ entropy, không phải chuỗi cố định dễ đoán?
5. **Tách biệt:** Pepper có thực sự nằm ngoài database, backup và môi trường có cùng quyền truy cập không?
6. **Phân quyền:** Những workload nào được dùng/export pepper? IAM có hạn chế tenant, môi trường và mục đích không?
7. **Online attack:** Có rate limit, MFA, kiểm tra quyền và giám sát API đăng nhập cũng như API KMS/HSM không?
8. **Metadata:** Có lưu algorithm, parameters, salt, schemeVersion và pepperId để xác minh đúng phiên bản?
9. **Rotation:** Có quy trình migrate khi đăng nhập/reset, cửa sổ chuyển tiếp, xử lý tài khoản không hoạt động và điều kiện hủy phiên bản cũ?
10. **Availability:** Nếu pepper/KMS không sẵn sàng, hệ thống xử lý lỗi và phục hồi thế nào mà không bỏ qua xác thực?
11. **Incident response:** Nếu lộ database hoặc pepper, có thể xác định phạm vi, thu hồi quyền, reset/migrate và xử lý bản sao không?
12. **Audit:** Có ghi ai thay đổi/đọc/sử dụng pepper, key ID và kết quả cần thiết mà không ghi bí mật?

## 12. Ghi nhớ

- **Salt công khai, riêng từng bản ghi; pepper bí mật, được lưu ở một ranh giới bảo vệ khác database.** Chúng giải quyết các vấn đề khác nhau và có thể được sử dụng đồng thời.
- **Pepper không thay thế Argon2id, scrypt hay PBKDF2**, và không làm mật khẩu yếu tự trở nên mạnh.
- **HMAC trước hoặc sau password hashing** đều cần scheme và định dạng lưu rõ ràng. Với post-hash, giữ raw password hash trong database có thể làm mất lợi ích chống cracking ngoại tuyến của pepper.
- **KMS/HSM và secret manager** hỗ trợ giữ bí mật và kiểm soát thao tác, nhưng ứng dụng có quyền dùng pepper vẫn có thể bị lạm dụng; phải có IAM, rate limiting và kiểm toán.
- **Xoay vòng pepper thường cần mật khẩu người dùng hoặc reset**, do password hash là một chiều; phải giữ key ID/version và lên kế hoạch chuyển đổi.
- **Fail closed khi không lấy được pepper**; thiết kế khôi phục hợp lệ thay vì tự giảm mức xác thực.

Pepper là một phần của **quản lý khóa mật mã**, không chỉ một chuỗi được thêm vào mật khẩu. Thiết kế đúng bắt đầu bằng ba câu hỏi: **Bí mật được cất ở đâu? Ai được dùng nó để xác minh mật khẩu? Điều gì xảy ra khi nó bị lộ, bị mất hoặc phải xoay vòng?**
