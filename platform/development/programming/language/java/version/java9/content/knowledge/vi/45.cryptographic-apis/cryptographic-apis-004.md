# Phân biệt hàm băm dữ liệu với lưu mật khẩu (Java 9+)

Cả việc kiểm tra dữ liệu và xác thực mật khẩu đều có thể dùng các phép toán được gọi chung là “hash”, nhưng **mục tiêu bảo mật khác nhau dẫn đến thuật toán, dữ liệu cần lưu và cách kiểm tra khác nhau**. Với dữ liệu thông thường, ta thường cần hàm băm mật mã nhanh như SHA-256 để tạo một dấu vân tay. Với mật khẩu của người dùng, ta cần **hệ thống băm mật khẩu chuyên dụng** có salt riêng và chi phí tính toán có thể điều chỉnh để làm chậm việc đoán mật khẩu khi cơ sở dữ liệu bị lộ.

Bài này thuộc chủ đề **Mật mã chuẩn**. Ví dụ dùng các API JDK hiện hành trong `java.security` và `javax.crypto`; chương trình thực hành yêu cầu Java 17+ vì dùng `HexFormat`, còn các khái niệm và API `MessageDigest`, `SecureRandom`, `SecretKeyFactory`, `PBEKeySpec` áp dụng cho Java 9 và Java hiện đại. Nội dung sử dụng những phương án vẫn được khuyến nghị cho hệ thống mới.

## 1. Phân biệt hai bài toán trước khi chọn thuật toán

**Bài toán A — băm dữ liệu:** Ứng dụng tải một tệp, đồng bộ một payload, kiểm tra nội dung cache hoặc so sánh dữ liệu trước–sau. Nó cần trả lời “hai đầu vào có cùng dấu vân tay mật mã không?”. Dùng `SHA-256(data)` để tính **digest 256 bit**, là 32 byte thường biểu diễn bằng 64 ký tự hexadecimal. Cùng dữ liệu byte cho cùng digest; đổi dù chỉ một byte thường làm digest thay đổi hoàn toàn.

**Bài toán B — lưu mật khẩu:** Ứng dụng cần xác minh người đăng nhập biết bí mật ban đầu mà **không giữ mật khẩu dạng rõ**. Mật khẩu do con người đặt thường dễ đoán hơn khóa ngẫu nhiên. Nếu database bị đánh cắp, kẻ tấn công có thể thử rất nhiều ứng viên offline. Thuật toán SHA-256 vốn được tối ưu chạy nhanh, nên `SHA-256(password)` hoặc `SHA-256(salt || password)` **vẫn không phù hợp** để lưu mật khẩu.

| Tiêu chí | Hash dữ liệu | Lưu mật khẩu |
| --- | --- | --- |
| Đầu vào | Byte của file, thông điệp, bản ghi | Mật khẩu người dùng và salt ngẫu nhiên |
| Mục tiêu | Nhận biết dữ liệu thay đổi, tạo digest | Xác thực mà không lưu mật khẩu gốc; tăng chi phí đoán offline |
| Tính toán | **Nhanh** để xử lý được nhiều dữ liệu | **Cố ý tốn CPU/bộ nhớ**, có tham số chi phí |
| Lựa chọn thông dụng | `SHA-256` qua `MessageDigest` | `Argon2id`; hoặc `PBKDF2-HMAC-SHA256` khi cần giải pháp chuẩn có sẵn trong JDK |
| Giá trị lưu | Digest (và ngữ cảnh/thuật toán khi cần) | Thuật toán, phiên bản, cost, salt, kết quả dẫn xuất |
| Khi cần kiểm tra | Hash dữ liệu mới rồi so digest | Đọc salt/cost đã lưu, dẫn xuất lại từ mật khẩu nhập và so kết quả |
| Có “giải mã” được không? | Không | Không; chỉ tính lại để xác minh |

Hash là phép biến đổi một chiều, **không phải mã hóa**. Không có “khóa giải mã SHA-256”. Tuy nhiên, một chiều không có nghĩa dữ liệu đầu vào ngắn/yếu là an toàn: kẻ tấn công có thể đoán đầu vào, tự hash rồi so kết quả.

## 2. SHA-256 dùng đúng ở đâu?

Dạng khái niệm:

```text
data bytes ── SHA-256 (nhanh) ──> 32-byte digest
new bytes  ── SHA-256 (nhanh) ──> 32-byte digest ── so với digest ban đầu
```

Ví dụ băm chuỗi ASCII `abc` bằng SHA-256:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Đây là **64 chữ số hex = 256 bit**. Giá trị đó cố định cho cùng chuỗi byte `abc`; khác biệt trong encoding văn bản hoặc ký tự xuống dòng sẽ tạo một đầu vào byte khác. SHA-256 được thiết kế để chống va chạm và khó tìm đầu vào phù hợp từ digest, nhưng đó không thay thế yêu cầu chống thử mật khẩu hàng loạt.

Trong Java:

```java
byte[] digest = MessageDigest.getInstance("SHA-256").digest(dataBytes);
```

Đoạn mã này **chỉ là mảnh tích hợp**: `dataBytes` là mảng byte do ứng dụng cung cấp; cần `import java.security.MessageDigest;`. Đối với file lớn, có thể đọc theo từng buffer và gọi `MessageDigest.update(...)` rồi `digest()` để không cần nạp toàn bộ file vào RAM.

**Ranh giới an toàn:** SHA-256 thuần không chứng minh ai đã tạo dữ liệu. Nếu đối thủ có thể thay cả file lẫn digest đi kèm, họ chỉ cần tính lại digest mới. Để xác minh *nguồn gốc* hoặc chống giả mạo bởi người không có khóa, dùng **HMAC-SHA-256** với khóa bí mật qua `javax.crypto.Mac`, hoặc dùng **chữ ký số** khi cần xác thực bằng khóa công khai. Đây là bài toán xác thực thông điệp, khác với cả kiểm tra checksum lẫn lưu mật khẩu.

## 3. Vì sao không thể lấy SHA-256 trực tiếp để lưu mật khẩu?

Giả sử hệ thống lưu:

```text
username = alice
hash     = SHA-256("MatKhauDeDoan!")
```

Nếu database lộ, kẻ tấn công có thể thử danh sách mật khẩu trên GPU/CPU và đối chiếu SHA-256 rất nhanh. Thêm một salt duy nhất ngăn việc tra bảng hash dựng sẵn hoặc dùng chung một kết quả giữa tài khoản, **nhưng SHA-256 vẫn là hàm băm nhanh**. Vì vậy “salt + SHA-256 một lần” không đủ cho kho mật khẩu.

Mục tiêu đúng là:

```text
Đăng ký:
password + random salt + cost ── password hashing/KDF ──> verifier
Lưu vào DB: algorithm + cost + salt + verifier
Không lưu: mật khẩu rõ; khóa/secret không cần thiết cho việc xác minh

Đăng nhập:
password nhập + salt/cost đã lưu ── cùng KDF ──> verifier mới
so verifier mới với verifier đã lưu ──> hợp lệ / không hợp lệ
```

Trong mô hình này:

- **Salt** là chuỗi byte ngẫu nhiên mới cho **mỗi bản ghi mật khẩu**, thường 16 byte (128 bit) trở lên từ `SecureRandom`. Salt **không phải bí mật** và được lưu cạnh verifier. Hai tài khoản dùng cùng mật khẩu vẫn phải có salt khác nhau.
- **Cost/work factor** tăng lượng tài nguyên cần dùng **cho mỗi lần đoán**. Argon2id còn yêu cầu bộ nhớ đáng kể, gây khó khăn hơn cho kiểu bẻ khóa song song quy mô lớn. PBKDF2 làm chậm bằng nhiều lượt lặp.
- **Verifier/hash dẫn xuất** là kết quả lưu trong database để so sánh sau này; việc lưu salt và cost không tiết lộ mật khẩu gốc.
- **Pepper** là bí mật cấp ứng dụng được quản lý tách biệt với kho hash, có thể thêm một lớp phòng vệ nếu cơ sở dữ liệu bị lộ. Pepper không thay thế salt hay KDF, và phải có kế hoạch quản lý khóa, luân chuyển và khôi phục phù hợp.
- **Mật khẩu mạnh, giới hạn số lần đăng nhập sai, kiểm tra mật khẩu bị lộ, MFA khi phù hợp và TLS** vẫn quan trọng. Hashing chậm chủ yếu giảm tốc tấn công **offline** sau khi DB lộ; giới hạn tốc độ xử lý đăng nhập giảm thử đoán **online**.

Cùng một mật khẩu, cùng thuật toán và cost nhưng **salt khác nhau** sẽ cho hai verifier khác nhau. Khi đăng nhập, **không sinh salt mới** để kiểm tra: phải dùng lại salt nằm trong bản ghi đã lưu. Salt mới chỉ dùng lúc tạo/đổi mật khẩu hoặc khi cần tạo bản ghi mới.

## 4. Chọn cơ chế hiện hành

| Nhu cầu | Lựa chọn | Lưu ý |
| --- | --- | --- |
| Hệ thống mới và dùng được thư viện mật mã đã kiểm chứng | **Argon2id** | Ưu tiên cơ chế tốn bộ nhớ; cần thư viện/framework đáng tin cậy vì JDK tiêu chuẩn không cung cấp `Argon2id` như một thuật toán `SecretKeyFactory` phổ quát |
| Cần API thuần JDK, hoặc giải pháp được phép dùng trong môi trường yêu cầu FIPS phù hợp | **PBKDF2-HMAC-SHA256** | Có sẵn qua `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`; đặt iterations đủ cao, đánh giá trên hạ tầng thực |
| Khó triển khai Argon2id nhưng có thư viện phù hợp | **scrypt** | Lựa chọn memory-hard thay thế; phải cấu hình CPU/bộ nhớ đúng |
| Băm nội dung để phát hiện khác biệt | **SHA-256** | Tính nhanh; không dùng trực tiếp cho mật khẩu |
| Kiểm tra tính xác thực thông điệp bằng bí mật chia sẻ | **HMAC-SHA256** | MAC có khóa bí mật; không thay thế password KDF |

Theo [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), các cấu hình khởi điểm được khuyến nghị khi soạn bài gồm:

- Argon2id: `m=19456 KiB` (19 MiB), `t=2`, `p=1`, hoặc cấu hình tương đương phù hợp máy chủ.
- PBKDF2-HMAC-SHA256: **ít nhất 600.000 lượt lặp** trong kịch bản dùng PBKDF2, đặc biệt khi cần FIPS-140.
- Salt: phát sinh ngẫu nhiên riêng cho từng bản ghi; chọn số byte đủ lớn, ví dụ 16 byte.

**Đó là điểm khởi đầu, không phải con số bất biến.** Cần benchmark độ trễ đăng nhập, số request đồng thời và giới hạn tài nguyên trên phần cứng thực tế; đánh giá, cập nhật chi phí theo thời gian. Với cấu hình Argon2id, cần tính cả RAM tiêu thụ khi nhiều yêu cầu xác thực chạy song song.

[NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html) (bản chính thức 2025) cũng yêu cầu mật khẩu lưu dưới dạng salted hash sử dụng một **password hashing scheme phù hợp** và cost được chọn đủ cao để cản đoán offline. Đừng nhầm “HMAC-SHA256” bên trong PBKDF2 với việc gọi HMAC một lần rồi lưu kết quả: **PBKDF2 có vòng lặp và salt riêng**.

## 5. Ví dụ Java 17+: hai đầu vào, hai cách băm

Ví dụ độc lập dưới đây cho thấy **SHA-256 tạo digest giống nhau với cùng dữ liệu**, trong khi **PBKDF2 với salt mới tạo hai bản ghi khác nhau cho cùng mật khẩu**. Chương trình chỉ in trạng thái boolean và digest của chuỗi công khai `abc`; nó không in mật khẩu, salt, verifier hoặc dữ liệu nhạy cảm.

Vì JDK chuẩn có sẵn PBKDF2 nhưng không có Argon2id mặc định, ví dụ dùng `PBKDF2WithHmacSHA256` để thực hành **không cần thư viện ngoài**. Khi xây dựng sản phẩm mới có thể dùng thư viện Argon2id đáng tin cậy theo chính sách hệ thống.

Lưu tệp `DataHashVsPasswordDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class DataHashVsPasswordDemo {
    private static final int ITERATIONS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int HASH_BITS = 256;
    private static final SecureRandom RANDOM = new SecureRandom();

    private static byte[] sha256(String data) throws GeneralSecurityException {
        return MessageDigest.getInstance("SHA-256")
                .digest(data.getBytes(StandardCharsets.UTF_8));
    }

    private static byte[] derive(char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, HASH_BITS);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private static String storePassword(char[] password)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] verifier = derive(password, salt, ITERATIONS);
        return "pbkdf2-sha256$" + ITERATIONS + "$"
                + Base64.getEncoder().encodeToString(salt) + "$"
                + Base64.getEncoder().encodeToString(verifier);
    }

    private static boolean verifyPassword(char[] attempt, String stored)
            throws GeneralSecurityException {
        String[] fields = stored.split("\\$", -1);
        if (fields.length != 4 || !fields[0].equals("pbkdf2-sha256")) {
            return false;
        }
        try {
            int iterations = Integer.parseInt(fields[1]);
            if (iterations < 600_000 || iterations > 2_000_000) {
                return false;
            }
            byte[] salt = Base64.getDecoder().decode(fields[2]);
            byte[] expected = Base64.getDecoder().decode(fields[3]);
            if (salt.length != SALT_BYTES || expected.length != HASH_BITS / 8) {
                return false;
            }
            byte[] actual = derive(attempt, salt, iterations);
            return MessageDigest.isEqual(expected, actual);
        } catch (IllegalArgumentException badRecord) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("sha256(abc)=" + HexFormat.of().formatHex(sha256("abc")));
        System.out.println("sameData=" + MessageDigest.isEqual(
                sha256("invoice=42"), sha256("invoice=42")));
        System.out.println("modifiedData=" + MessageDigest.isEqual(
                sha256("invoice=42"), sha256("invoice=43")));

        char[] password = "correct horse battery staple!".toCharArray();
        char[] incorrect = "incorrect password".toCharArray();
        try {
            String stored1 = storePassword(password);
            String stored2 = storePassword(password);
            System.out.println("passwordCorrect=" + verifyPassword(password, stored1));
            System.out.println("passwordWrong=" + verifyPassword(incorrect, stored1));
            System.out.println("samePasswordNewSalt=" + !stored1.equals(stored2));
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(incorrect, '\0');
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 DataHashVsPasswordDemo.java
java DataHashVsPasswordDemo
```

**Stdout chính xác** (đã kiểm tra bằng JDK 24; kết quả hiển thị giống nhau trên JDK 17+ dù salt ngẫu nhiên):

```text
sha256(abc)=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
sameData=true
modifiedData=false
passwordCorrect=true
passwordWrong=false
samePasswordNewSalt=true
```

Giải thích từng kết quả:

1. `sha256(abc)` cố định; cùng chuỗi byte luôn tạo một digest giống nhau.
2. `sameData=true` vì hai thông điệp hoàn toàn giống nhau. `modifiedData=false` vì đổi nội dung từ `invoice=42` thành `invoice=43` đã đổi digest.
3. `passwordCorrect=true` vì lúc xác minh dùng **salt và iterations lấy từ bản ghi**, dẫn xuất lại ra cùng kết quả.
4. `passwordWrong=false` vì mật khẩu nhập sai dẫn xuất ra kết quả khác.
5. `samePasswordNewSalt=true` vì mỗi lần lưu gọi `SecureRandom` tạo salt mới; **không lưu cùng một verifier cố định cho mọi tài khoản cùng mật khẩu**.

Trong `storePassword`, record có cấu trúc:

```text
pbkdf2-sha256$600000$<base64-salt>$<base64-verifier>
          │       │              │
       thuật toán  cost       dữ liệu dẫn xuất
```

Trong cấu trúc thực tế, nên dùng một chuẩn record/encoder được framework hoặc thư viện hỗ trợ nếu có, thay vì tự đưa format thử nghiệm vào dịch vụ production. **Base64 chỉ là encoding**, không phải mã hóa hay kỹ thuật bảo vệ bí mật. Salt và verifier có thể nằm trong cột text hoặc các trường byte/binary tương ứng của DB. Nên lưu đầy đủ tên thuật toán/phiên bản và tham số để có thể thay đổi thuật toán/cost có kiểm soát.

### Giải thích các API trong ví dụ

- `MessageDigest.getInstance("SHA-256")`: tạo **digest nhanh của dữ liệu**, không được thiết kế để lưu mật khẩu.
- `SecureRandom.nextBytes(salt)`: tạo salt khó dự đoán, khác nhau ở các lần lưu. Không dùng `Random` hay thời gian hiện tại để tạo salt.
- `PBEKeySpec(char[], salt, iterations, 256)`: gói mật khẩu, salt, cost và độ dài đầu ra 256 bit cho thao tác derivation.
- `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`: triển khai PBKDF2-HMAC-SHA256 do JDK cung cấp. Khi dùng làm password verifier, lưu giá trị dẫn xuất; **không dùng giá trị này làm khóa mã hóa dữ liệu một cách tùy tiện**.
- `PBEKeySpec.clearPassword()`: xóa bản sao mật khẩu do spec quản lý sau khi derive. `Arrays.fill(password, '\0')` xóa mảng do ứng dụng sở hữu sau khi dùng; không đảm bảo xóa mọi bản sao do runtime hoặc thư viện khác từng tạo.
- `Base64`: mã hóa byte thành text an toàn cho lưu trữ; khi verify thì giải mã lại byte.
- `MessageDigest.isEqual(expected, actual)`: so mảng kết quả dẫn xuất theo cách tránh so sánh byte bằng vòng lặp thông thường; với độ dài verifier đã được kiểm soát, phù hợp cho bước so kết quả. Nó không tự giải quyết rò rỉ thời gian ở toàn bộ luồng đăng nhập.

**Lưu ý về dữ liệu test:** mật khẩu tạo từ chuỗi literal trong `main` chỉ để demo có thể chạy và kiểm thử. Trong ứng dụng thật, nhận mật khẩu từ luồng nhập an toàn; không hardcode, không ghi log và hạn chế giữ mật khẩu dưới dạng `String` bất biến lâu trong bộ nhớ.

## 6. Triển khai vào luồng đăng ký và đăng nhập

Tách rõ **hai thời điểm**:

**Khi đăng ký hoặc đổi mật khẩu:**

1. Nhận mật khẩu qua kết nối được bảo vệ; áp dụng chính sách mật khẩu hiện hành và kiểm tra mật khẩu bị lộ khi có khả năng.
2. Chọn thuật toán đã được phê duyệt. Với Argon2id, dùng implementation được kiểm chứng; với JDK-only PBKDF2, áp dụng cost đã benchmark.
3. Sinh salt ngẫu nhiên mới **mỗi lần đặt mật khẩu**. Derive verifier bằng mật khẩu, salt và cost.
4. Lưu `algorithm/version + cost + salt + verifier` cho tài khoản; không lưu password rõ và không dùng một salt toàn ứng dụng.
5. Hủy hoặc hạn chế vòng đời các buffer nhạy cảm sau khi xử lý; không trả record hash về API client.

**Khi đăng nhập:**

1. Lấy record hash của tài khoản qua kênh truy cập DB được bảo vệ.
2. Parse và **giới hạn giá trị cost và kích thước input** từ record để tránh thao tác quá tốn tài nguyên do dữ liệu sai hoặc bị thao túng.
3. Dùng đúng salt/cost đã lưu để derive từ mật khẩu đang nhập. **Không sinh salt mới** trong verify.
4. So hai verifier với API có hành vi thời gian phù hợp, kiểm tra cả đường đi tài khoản không tồn tại và sai mật khẩu để hạn chế side channel; kết hợp rate limit và bảo vệ chống account enumeration.
5. Nếu xác minh thành công nhưng record còn dùng tham số không còn phù hợp với chính sách hiện hành, tạo lại record bằng salt mới và cost/thuật toán mới theo **kế hoạch migration riêng**. Code demo ở trên chỉ nhận bản ghi PBKDF2 mới có iterations ít nhất 600.000; không triển khai xử lý bản ghi cũ.

Các giới hạn chi phí trên mỗi phép derive phải cân bằng được hai rủi ro: quá thấp làm attacker đoán offline nhanh; quá cao có thể gây quá tải hệ thống khi nhiều lượt đăng nhập đồng thời. Để tránh DoS, kiểm soát đồng thời, timeout và giới hạn size/cost trong lúc verify theo yêu cầu hệ thống.

## 7. Những lỗi thường gặp và cách nhận biết

| Cách làm sai | Vấn đề | Cách đúng |
| --- | --- | --- |
| Lưu `SHA-256(password)` | Hàm băm quá nhanh cho việc chống thử mật khẩu offline | Dùng Argon2id hoặc PBKDF2-HMAC-SHA256 với salt/cost đúng |
| Chỉ thêm salt vào SHA-256 một lần | Có salt nhưng phép thử vẫn rất rẻ | Dùng thuật toán password hashing/KDF chuyên dụng |
| Dùng cùng một salt cho mọi người dùng | Hai người cùng mật khẩu có thể tạo dấu vết giống nhau | Salt ngẫu nhiên khác nhau cho từng record |
| Mỗi lần login lại tạo salt mới | Không khớp verifier cũ nên xác minh luôn thất bại | Đọc salt từ record đã lưu |
| Hash mật khẩu nhiều lần bằng SHA-256 tự viết vòng lặp | Không có đầy đủ đặc tính/định nghĩa được chuẩn hóa của password KDF | Dùng thư viện/algorithm chuẩn, không tự chế |
| Lưu `Base64(password)` | Có thể đảo ngược thành password gốc ngay | Chỉ lưu password verifier dẫn xuất |
| Lưu mật khẩu bằng mã hóa hai chiều để so | Cần giữ khóa giải mã; thêm rủi ro lộ password rõ | Lưu verifier một chiều |
| Tin rằng SHA-256 của file chứng minh file do bên tin cậy gửi | Kẻ thay file có thể tạo digest mới | HMAC có khóa hoặc chữ ký số |
| So sánh hash bằng thuật toán tự viết ngắt ngay ở byte đầu khác | Có thể để lộ tín hiệu thời gian | Dùng API so sánh phù hợp; kiểm soát toàn bộ luồng xác thực |
| Chọn cost theo bản demo rồi dùng vĩnh viễn | Chi phí phần cứng thay đổi và tải production khác môi trường dev | Benchmark, theo dõi và nâng cost định kỳ |
| Tự viết Argon2id, PBKDF2 hoặc quy tắc kết hợp hash | Khó đánh giá tính đúng và các lỗi bảo mật tinh vi | Dùng JDK provider hoặc thư viện đã được kiểm chứng |

**Không đánh đồng salt và pepper:** salt không bí mật và phải riêng cho từng record; pepper là bí mật ứng dụng, nếu dùng phải nằm ngoài DB hash. Không được thay salt bằng pepper. Khi ứng dụng thực hiện hashing ở server, bảo vệ password trên đường truyền bằng TLS và bảo vệ server, log và backup là các lớp cần thiết khác.

### Trường hợp dữ liệu là mật khẩu nhưng cần hash file?

Ví dụ, một chương trình chứa **file cấu hình mật khẩu đã được người dùng tạo**. Nếu chỉ cần biết file có thay đổi so với bản trước, SHA-256 có thể dùng để tính digest toàn bộ **file**; nhưng nếu file bị lộ, nội dung mật khẩu trong đó vẫn có thể bị đọc. Hash nội dung của file **không mã hóa file**. Khi cần bảo vệ tính bí mật của file, phải áp dụng kiểm soát truy cập và mã hóa phù hợp; khi cần lưu giá trị để xác thực người dùng, vẫn phải dùng password hashing.

## 8. Câu hỏi tự kiểm tra

**Câu 1.** Hai tài khoản cùng mật khẩu có nên lưu cùng chuỗi `SHA-256(password)` không? **Đáp án:** Không. Mỗi password record phải có salt ngẫu nhiên riêng và được dẫn xuất bởi password hashing scheme có cost.

**Câu 2.** Đã dùng `SHA-256(salt || password)` thì đã đủ an toàn chưa? **Đáp án:** Chưa. Salt giảm lợi thế của bảng tính sẵn nhưng SHA-256 vẫn chạy quá nhanh để cản đoán offline.

**Câu 3.** Khi đăng nhập, có cần tạo salt mới không? **Đáp án:** Không. Dùng lại salt và cost của record đã lưu, tính lại verifier, rồi so kết quả. Salt mới chỉ sinh khi tạo record mới.

**Câu 4.** Hệ thống mới muốn dùng thuật toán có khả năng chống đoán bằng GPU tốt hơn thì chọn gì? **Đáp án:** Ưu tiên Argon2id được triển khai qua thư viện uy tín, cấu hình memory/cost theo OWASP và benchmark thực tế.

**Câu 5.** Vì sao ví dụ Java dùng PBKDF2 dù Argon2id thường được ưu tiên? **Đáp án:** `PBKDF2WithHmacSHA256` có sẵn trong JDK để demo độc lập; Argon2id cần thư viện ngoài đáng tin cậy. Cả hai là password hashing/KDF có cost, khác với SHA-256 dữ liệu.

**Câu 6.** Một nhà cung cấp gửi file và chuỗi SHA-256 cùng lúc. Chỉ so SHA-256 đã đảm bảo file là của nhà cung cấp chưa? **Đáp án:** Chưa, nếu đối thủ có thể sửa cả file và digest. Cần kênh phân phối digest tin cậy, HMAC hoặc chữ ký số tùy mô hình tin cậy.

## Tài liệu tham khảo hiện hành

- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): lựa chọn Argon2id/scrypt/PBKDF2, salt, pepper, tham số chi phí và nâng cấp.
- [NIST SP 800-63B-4 — Digital Identity Guidelines: Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): lưu password chống tấn công offline, salt + cost, thực hành xác thực.
- [Java SE 21 — `MessageDigest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): digest và `isEqual`.
- [Java SE 21 — `SecretKeyFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html): API tạo khóa dẫn xuất qua provider.
- [Java SE 21 — `PBEKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): password/salt/iterations/key length.
- [Java SE 21 — `SecureRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): nguồn salt ngẫu nhiên mật mã.

Ghi nhớ để chọn đúng: **SHA-256 trả lời “dữ liệu có cùng dấu vân tay không?”; password hashing trả lời “người đăng nhập có biết đúng mật khẩu không?” trong khi khiến mỗi lần đoán offline tốn chi phí.** Chọn công cụ theo mục tiêu, quản lý salt và cost đúng cách, và luôn kiểm tra bảo mật của toàn bộ luồng xử lý.
