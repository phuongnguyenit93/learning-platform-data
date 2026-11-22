# Nâng cấp giá trị băm và xử lý dữ liệu mật khẩu từ hệ thống cũ

Một ứng dụng tồn tại nhiều năm có thể lưu mật khẩu theo nhiều kiểu: một phần tài khoản dùng bcrypt nhưng không có tiền tố nhận diện; tài khoản mới sử dụng một cấu hình bcrypt mạnh hơn; một hệ thống rất cũ từng lưu MD5, SHA-1 hoặc thậm chí plaintext. Nếu đổi `PasswordEncoder` sang phiên bản mới và triển khai ngay, nhiều người dùng có thể đột nhiên không đăng nhập được. Nhưng nếu tiếp tục cho phép các cách lưu không an toàn vô thời hạn, hệ thống lại kéo dài nguy cơ lộ mật khẩu.

Bài học này giải quyết một bài toán chuyển đổi thực tế: **làm thế nào để xác minh mật khẩu cũ trong giai đoạn quá độ, nâng cấp hash sau khi người dùng nhập đúng mật khẩu, không làm mất tài khoản, không cấp quyền sai và không duy trì thuật toán yếu lâu dài?**

Phạm vi tập trung vào **lưu trữ mật khẩu của người dùng** và cơ chế `PasswordEncoder` trong Spring Security; không nhầm với JWT, chữ ký số, giải mã dữ liệu hay việc chuyển đổi mật khẩu giữa hai nhà cung cấp SSO. Ví dụ thực hành là **Java 17+**, Spring Security **7.1.2** ở dạng chương trình Gradle độc lập. Ứng dụng dùng Spring Boot nên để **Boot BOM** quản lý các dependency Spring Security thay vì tự khóa từng phiên bản.

Kết quả mong muốn:

- Hiểu vì sao password hash là phép **một chiều** và không thể lấy lại mật khẩu gốc để “hash lại hàng loạt”.
- Biết cách phân loại dữ liệu legacy, thêm metadata nhận diện thuật toán mà không thay đổi giá trị mật mã trong trường hợp hợp lệ.
- Dùng `DelegatingPasswordEncoder` với định dạng `{id}encodedPassword` và chuyển đổi dần sang cấu hình mục tiêu.
- Hiểu đúng `PasswordEncoder.matches`, `upgradeEncoding`, `DaoAuthenticationProvider` và `UserDetailsPasswordService.updatePassword`.
- Biết thiết kế cập nhật an toàn khi có nhiều request cùng lúc, cache, đổi/reset mật khẩu, tài khoản không hoạt động và lỗi database.
- Có ma trận test, checklist triển khai, rollback và giải thích các tình huống thường bị hiểu sai.

## 1. Không nhầm “hash”, “mã hóa” và “mã hóa lại”

Trong xác thực mật khẩu, máy chủ không nên lưu plaintext. Khi tạo hoặc đổi mật khẩu, nó tạo một **password hash** bằng thuật toán có chi phí cố ý cao và salt phù hợp:

~~~text
User chọn password (raw secret)
         |
         v
PasswordEncoder.encode(raw)
         |
         v
Password hash gồm metadata / tham số / salt / output
         |
         v
Credential store (database được bảo vệ)

Lần login tiếp theo:
  raw password mới nhập + hash đã lưu
             |
             v
  PasswordEncoder.matches(raw, stored)
             |
        true hoặc false
~~~

**Password hashing là phép một chiều**, không phải mã hóa đối xứng có khóa để giải mã. Không có thao tác `decode(storedHash)` hợp lệ để khôi phục mật khẩu rồi tạo lại bcrypt/Argon2.

Trong Spring Security:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là chữ ký khái niệm rút gọn theo API (các bản Java API mới có annotation nullability), không phải một interface người học cần tự định nghĩa. Cả ba phương thức giải quyết những việc khác nhau:

| Phương thức | Mục đích | Không nên suy ra |
| --- | --- | --- |
| `encode(raw)` | Tạo giá trị băm **mới** từ plaintext đang có trong lần đăng ký/đổi/reset/rehash sau login | Có thể gọi `encode(oldHash)` để nâng cấp mật khẩu người dùng |
| `matches(raw, stored)` | Kiểm tra raw password vừa được cung cấp có khớp hash đã lưu không | Trả lại plaintext hoặc cho biết password đã “được giải mã” |
| `upgradeEncoding(stored)` | Xác định giá trị băm đang lưu có nên nâng cấp theo policy encoder không | Tự cập nhật database; tự bảo đảm nâng cấp trên mọi loại `PasswordEncoder` |

Với nhiều implementation, `upgradeEncoding` mặc định là `false`. Nếu muốn nâng cấp tự động, phải **chọn encoder có chính sách nâng cấp thích hợp** và **có thành phần cập nhật bản ghi**.

### Một ví dụ “nâng cấp” sai

~~~java
// SAI: chỉ có oldHash, không có raw password.
String newHash = new BCryptPasswordEncoder(12).encode(oldHash);
~~~

Mã trên tạo hash của **chuỗi hash cũ**, không phải hash của mật khẩu gốc. Nếu login sau dùng `matches(rawPassword, newHash)`, nó không khớp. Một hệ thống có thể cố ý xây dựng thuật toán bọc hash cũ theo tầng trong giai đoạn đặc biệt, nhưng đó là giao thức xác minh khác cần thiết kế và đánh giá riêng, **không phải phép nâng cấp trực tiếp tương đương rehash raw password**.

## 2. Kiểm kê dữ liệu cũ trước khi sửa PasswordEncoder

Đừng bắt đầu bằng cách đổi bean rồi để người dùng phát hiện không đăng nhập được. Bước đầu tiên là **kiểm kê thực trạng có bằng chứng**.

| Loại dữ liệu tìm thấy | Ví dụ định dạng | Ý nghĩa | Hướng xử lý |
| --- | --- | --- | --- |
| BCrypt có prefix | `{bcrypt}$2a$10$...` | Spring có metadata chọn encoder | Có thể xác minh và đánh giá work factor |
| BCrypt không prefix | `$2a$10$...` | Có thể là bcrypt từ hệ cũ | Xác nhận nguồn rồi gắn metadata chính xác hoặc dùng adapter tạm |
| PBKDF2/SCrypt/Argon2 có metadata | `{pbkdf2...}...`, `{scrypt}...` | Có tham số/format theo implementation | Giữ verifier tương thích, có kế hoạch đổi tham số |
| SHA-1/MD5 không salt | Chuỗi hex tương đối ngắn | Hash rất nhanh, dễ bị dò ngoại tuyến khi lộ | Ưu tiên reset, giới hạn rất chặt hỗ trợ cũ nếu bắt buộc |
| SHA-256 đơn thuần | Có thể là chuỗi hex 64 ký tự | Nhanh, không phải password KDF thích ứng | Chuyển sang KDF thích ứng qua login/reset |
| Plaintext | Chuỗi mật khẩu đọc được | Rủi ro cao và có khả năng vi phạm chính sách nghiêm trọng | Xử lý như sự cố bảo mật, loại bỏ, cưỡng bức reset theo kế hoạch |
| Không rõ nguồn/pepper/salt | Chuỗi không khớp catalog nào | Không thể xác minh an toàn khi thiếu hợp đồng | Cách ly và yêu cầu reset; không đoán |
| Được xác thực ở IdP ngoài | Không có hash nội bộ | SSO/OIDC sử dụng một hệ khác xác minh | Không tự tạo mật khẩu nội bộ từ token/claims |

**Độ dài chuỗi không đủ để nhận diện thuật toán.** Hai hệ thống có thể dùng cùng một loại hash nhưng khác salt encoding, charset, cách chuẩn hóa Unicode hoặc thứ tự ghép. Với một hàng không có prefix, cần đối chiếu phiên bản ứng dụng đã ghi nó, cấu hình encoder, schema, lịch sử migration, bản backup được kiểm soát và metadata đáng tin cậy.

Một báo cáo kiểm kê hữu ích bao gồm: số tài khoản theo format, thời điểm cập nhật credentials, tỷ lệ đăng nhập gần đây, tỷ lệ tài khoản lâu không login, tỉ lệ bị disable/locked, nhóm không xác định định dạng, và nguy cơ reset hàng loạt. Không export toàn bộ password hash vào dashboard hay file CSV thông thường để tiện thống kê.

### Bất biến khi phân loại

1. Không biến một chuỗi tùy ý thành `{noop}` chỉ vì không xác định được thuật toán.
2. Không tự suy luận mọi hash thiếu prefix là bcrypt nếu hệ thống từng dùng cả SHA-1, MD5 và bcrypt.
3. Không đặt một “default encoder” quá rộng cho mọi chuỗi thiếu/không rõ id.
4. Không đưa lựa chọn thuật toán từ HTTP request hoặc thông tin do người dùng tự khai.
5. Không log password hash thô trong báo cáo migration; chỉ ghi **nhóm định dạng, số lượng và trạng thái**.

## 3. DelegatingPasswordEncoder và định dạng {id}encodedPassword

Spring Security hỗ trợ cách lưu:

~~~text
{id}encodedPassword

Ví dụ:
  {bcrypt}$2a$10$...
  {bcrypt10}$2a$10$...
  {bcrypt12}$2a$12$...
  {pbkdf2@SpringSecurity_v5_8}...
~~~

Phần `id` là metadata của ứng dụng/Spring Security để chọn bộ xác minh; nó **không phải một phần của bcrypt hash gốc**. `DelegatingPasswordEncoder` có bảng map từ id đến `PasswordEncoder`, cùng `idForEncode` để chọn thuật toán **khi ghi hash mới**.

Ví dụ cấu hình rõ cho một đợt migration:

~~~java
PasswordEncoder oldBcrypt = new BCryptPasswordEncoder(10);
PasswordEncoder newBcrypt = new BCryptPasswordEncoder(12);

Map<String, PasswordEncoder> algorithms = Map.of(
    "bcrypt10", oldBcrypt,
    "bcrypt12", newBcrypt
);

DelegatingPasswordEncoder encoder =
    new DelegatingPasswordEncoder("bcrypt12", algorithms);
~~~

Đây là **mảnh code** sử dụng `org.springframework.security.crypto.password.PasswordEncoder`, `DelegatingPasswordEncoder`, `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder` và `java.util.Map`. Ở Spring Security 7.1.x, kiểm tra import của `BCryptPasswordEncoder` theo module API thực tế; ví dụ chạy được ở phần 6 ghi imports đầy đủ.

Với cấu hình trên:

- `encoder.matches(raw, "{bcrypt10}...")` dùng bộ kiểm tra bcrypt cũ.
- `encoder.matches(raw, "{bcrypt12}...")` dùng bộ kiểm tra bcrypt mới.
- `encoder.encode(raw)` **luôn tạo** giá trị có prefix `{bcrypt12}`, vì `idForEncode="bcrypt12"`.
- `encoder.upgradeEncoding("{bcrypt10}...")` được kỳ vọng trả `true` vì id cũ khác id mục tiêu.
- `encoder.upgradeEncoding("{bcrypt12}...")` còn phụ thuộc policy `upgradeEncoding` của encoder hiện hành; với hash cost 12 tạo từ cấu hình trên, không cần nâng cấp thêm.

`bcrypt10` và `bcrypt12` ở đây là **ID do ví dụ tự đặt**, không phải tên thuật toán mặc định có sẵn trong mọi cấu hình Spring Security. Chúng giúp mã hóa chính sách work factor trong metadata. Có thể dùng ID khác nếu hệ thống đã có convention lâu dài, nhưng phải nhất quán giữa DB, encoder map và migration.

### Không phải idForEncode quyết định cách kiểm tra hash cũ

Giả sử `idForEncode="bcrypt12"`, một bản ghi lưu `{bcrypt10}...`. Spring Security không so password bằng bcrypt12 rồi mong kết quả khớp. Nó đọc prefix **của bản ghi**, tìm encoder tương ứng, xác minh bằng dữ liệu/format đó, rồi mới đánh giá có nên ghi lại bằng encoder mục tiêu hay không.

Đây là nền tảng cho **migration dần mà không ép mọi user reset password ngay**, miễn là format cũ còn được phép hỗ trợ tạm thời và vẫn có thể xác minh đúng cách.

### Thiếu prefix hoặc id không biết sẽ xảy ra gì?

Với `DelegatingPasswordEncoder` mặc định, một hash thiếu `{id}` hoặc có id không nằm trong map thường dẫn đến `IllegalArgumentException` khi xác minh; không nên coi đây là bằng chứng “mật khẩu chắc chắn sai”.

Spring có `setDefaultPasswordEncoderForMatches(...)` để chọn fallback khi không tìm được id. **Đây không phải cách an toàn để phỏng đoán mọi dữ liệu cũ**. Nếu dùng fallback quá rộng, một chuỗi lưu sai format có thể bị kiểm tra bằng thuật toán không đúng hoặc che dấu lỗi dữ liệu. Ưu tiên chuẩn hóa metadata theo nguồn dữ liệu đã xác minh hoặc viết adapter rất hẹp có kiểm tra định dạng, kèm hạn gỡ bỏ rõ ràng.

## 4. Có thể gắn prefix vào bare bcrypt mà không cần plaintext không?

**Có, với điều kiện đã xác nhận chắc chắn** giá trị đó thực sự là hash bcrypt tương thích và metadata còn thiếu là vấn đề duy nhất.

Ví dụ từ hệ thống cũ:

~~~text
Trước:
  stored_hash = $2a$10$[53 ký tự mã hóa salt+hash]

Sau migration metadata:
  stored_hash = {bcrypt10}$2a$10$[cùng 53 ký tự]
~~~

Trong trường hợp này, thêm `{bcrypt10}` **không tính lại bcrypt** và không làm work factor tăng từ 10 lên 12; nó chỉ bổ sung thông tin để `DelegatingPasswordEncoder` chọn bộ verifier đúng. Đây là bước **chuẩn hóa định dạng**, chưa phải bước **nâng cấp sức mạnh hash**.

Cần phân biệt hai pha:

~~~text
Pha A — chuẩn hóa metadata:
  bcrypt cost 10 thiếu id
          |
    kiểm kê + xác nhận nguồn/format
          |
    gắn {bcrypt10} mà giữ nguyên phần bcrypt
          |
    vẫn là bcrypt cost 10

Pha B — rehash thật khi có raw password hợp lệ:
  login bằng raw password
          |
    matches(raw, "{bcrypt10}...") -> true
          |
    encode(raw) bằng bcrypt cost 12
          |
    lưu "{bcrypt12}..." bằng cập nhật an toàn
          |
    lần sau dùng bcrypt cost 12
~~~

Bước A có thể thực hiện offline nếu format đáng tin cậy; bước B chỉ thực hiện được khi có **raw password vừa được cung cấp** trong một phiên xác thực hợp lệ (hoặc người dùng đặt mật khẩu mới qua quy trình reset).

Nếu database đang chứa nhiều loại hash thiếu prefix, **không chạy một câu UPDATE phủ toàn bảng**. Hãy giới hạn theo nhóm đã được chứng minh, kiểm tra mẫu có kiểm soát, có backup/rollback và dự phòng cho bản ghi không đủ điều kiện. Một format giống bcrypt vẫn phải được đánh giá nguồn ghi và version thật sự.

### Tại sao không được lưu {noop} cho plaintext legacy?

`{noop}` tương ứng cơ chế so chuỗi không dùng password hashing an toàn. Dù Spring Security có hỗ trợ để đọc dữ liệu cũ trong một số ngữ cảnh, **đưa plaintext vào định dạng Delegating không làm plaintext trở nên an toàn**. Nếu hệ thống thực sự còn plaintext, đó là tình huống ưu tiên khắc phục: khóa truy cập dữ liệu, đánh giá rủi ro/sự cố, reset mật khẩu theo chính sách, ngừng ghi plaintext và loại bỏ bản sao/backup theo quy trình lưu giữ.

Không minh họa “cách nhanh nhất” bằng việc thêm NoOp làm fallback cho toàn bộ dữ liệu production.

## 5. Rehash-on-login: nơi có plaintext hợp lệ trong một thời gian ngắn

Không thể nâng cấp mọi password hash offline vì hash là một chiều. Nhưng khi người dùng vừa nhập **đúng mật khẩu**, nhà cung cấp xác thực có plaintext **trong thời gian xử lý request**. Đây là thời điểm có thể tạo hash mới.

Spring Security cung cấp các điểm nối:

- `PasswordEncoder.matches(raw, stored)`: xác minh đúng/sai.
- `PasswordEncoder.upgradeEncoding(stored)`: encoder xác định stored hash có cần nâng cấp không.
- `DaoAuthenticationProvider`: trong luồng username/password, sau khi xác minh thành công có thể thực hiện nâng cấp nếu được cấu hình.
- `UserDetailsPasswordService.updatePassword(user, newPassword)`: hợp đồng để ghi **hash mới đã được encode** vào nguồn lưu và trả `UserDetails` đã cập nhật.

Từ góc nhìn triển khai:

~~~text
Request login
  |
  v
DaoAuthenticationProvider
  |
  +--> UserDetailsService.loadUserByUsername("mai")
  |       stored="{bcrypt10}..."
  |
  +--> PasswordEncoder.matches(rawPassword, stored)
  |         |
  |      false --> từ chối login, KHÔNG rehash
  |         |
  |      true
  |         v
  +--> kiểm tra điều kiện trạng thái/account theo provider
  |
  +--> PasswordEncoder.upgradeEncoding(stored)
            |
          false --> tiếp tục thành công, không ghi DB
            |
           true
            |
            v
      PasswordEncoder.encode(rawPassword)
      -> "{bcrypt12}..."
            |
            v
      UserDetailsPasswordService.updatePassword(user,newHash)
            |
            +--> ghi DB/CAS + trả updated UserDetails
            |
            v
      Authentication thành công, ProviderManager
      dọn credentials theo chính sách
~~~

Sơ đồ mô tả các **điểm quyết định**, không phải cam kết thứ tự chi tiết của tất cả provider/phiên bản. Việc nâng cấp ở `DaoAuthenticationProvider` đòi hỏi **đã gắn `UserDetailsPasswordService` thích hợp**; nếu không có service ghi, chỉ triển khai `PasswordEncoder.upgradeEncoding` không đủ để thay đổi database.

**Chỉ nâng cấp sau khi xác minh credentials đúng và account thỏa chính sách.** Không được lấy raw password từ một request chưa xác thực rồi ghi đè hash của bất kỳ username nào. Cần bảo vệ quá trình update khỏi sự thay đổi mật khẩu đồng thời.

### UserDetailsPasswordService nhận loại dữ liệu nào?

Hợp đồng:

~~~java
UserDetails updatePassword(UserDetails user, String newPassword);
~~~

`newPassword` ở đây là **password đã được encoder băm mới**, không phải raw password. Implementation phải ghi nó vào kho dữ liệu lâu dài và trả về `UserDetails` tương ứng với bản ghi mới.

Một lỗi dễ gặp:

~~~java
// SAI: newPassword vốn đã là hash, encode tiếp thành hash(hash).
String doubleEncoded = encoder.encode(newPassword);
repository.savePasswordHash(username, doubleEncoded);
~~~

Cách đúng là **lưu nguyên chuỗi hash mới đã được cung cấp**, sau khi xác minh update được phép thực hiện, dữ liệu đúng user và trạng thái cập nhật đồng thời an toàn.

## 6. Ví dụ chạy được: legacy bcrypt10 → bcrypt12 qua DaoAuthenticationProvider

Ví dụ này dùng Spring Security thật, không dùng database ngoài. Một `ConcurrentHashMap` đóng vai trò **credential store** để người học thấy rõ trước và sau login; `UserDetailsService` tạo **một UserDetails mới ở mỗi lần tải**.

Điều kiện học tập:

- Legacy: bcrypt cost 10 **đã được gắn prefix có kiểm chứng** `{bcrypt10}`.
- Chính sách mới: bcrypt cost 12, id `{bcrypt12}`.
- Mật khẩu demo: `demo-password` (không dùng với tài khoản thật).
- Sau lần đăng nhập hợp lệ đầu tiên, hash lưu trong store chuyển sang id `{bcrypt12}`.
- Lần đăng nhập thứ hai vẫn thành công.
- Mật khẩu sai bị từ chối và **không đổi stored hash**.

Ở production, lựa chọn work factor phải dựa trên benchmark phần cứng và threat model; bcrypt 10/12 trong bài là hai mức minh họa, không phải tuyên bố “12 luôn đủ” cho mọi thời điểm/hạ tầng.

### 6.1. Cấu trúc và build.gradle

~~~text
password-migration-lab/
  build.gradle
  src/main/java/PasswordMigrationDemo.java
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.1.2'
    implementation 'org.springframework.security:spring-security-crypto:7.1.2'
}

application {
    mainClass = 'PasswordMigrationDemo'
}
~~~

Với một dự án Spring Boot, không copy các version Security trên; dùng starter và để Boot BOM quản lý.

### 6.2. Tệp Java đầy đủ

Tạo `src/main/java/PasswordMigrationDemo.java`:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordMigrationDemo {

    // Kho lưu chỉ phục vụ demo. Trong sản phẩm thật là DB/credential service.
    static final class MemoryUsers
            implements UserDetailsService, UserDetailsPasswordService {

        private final ConcurrentMap<String, String> hashes =
                new ConcurrentHashMap<>();

        void put(String username, String encodedHash) {
            hashes.put(username, encodedHash);
        }

        String storedHash(String username) {
            return hashes.get(username);
        }

        @Override
        public UserDetails loadUserByUsername(String username) {
            String encoded = hashes.get(username);
            if (encoded == null) {
                throw new UsernameNotFoundException("Unknown account");
            }

            // Tạo object MỚI, không trả shared mutable User trong cache.
            return User.withUsername(username)
                    .password(encoded)
                    .roles("USER")
                    .build();
        }

        @Override
        public UserDetails updatePassword(
                UserDetails user, String newPassword) {

            String previousHash = user.getPassword();
            if (previousHash == null || newPassword == null ||
                    !hashes.replace(
                        user.getUsername(), previousHash, newPassword)) {
                // CAS thất bại: có thể một request khác đã reset/đổi
                // password trong lúc login này đang chạy.
                throw new AuthenticationServiceException(
                        "Password changed during upgrade");
            }

            // Trả bản UserDetails mới với hash mới; không encode lần nữa.
            return User.withUserDetails(user)
                    .password(newPassword)
                    .build();
        }
    }

    private static Authentication authenticate(
            AuthenticationManager manager,
            String username,
            String rawPassword) {

        var input = UsernamePasswordAuthenticationToken
                .unauthenticated(username, rawPassword);
        try {
            return manager.authenticate(input);
        } finally {
            // Dọn reference credentials của input do caller tạo.
            input.eraseCredentials();
        }
    }

    private static String idOf(String encodedHash) {
        int closing = encodedHash.indexOf('}');
        if (!encodedHash.startsWith("{") || closing < 0) {
            throw new IllegalArgumentException("Missing password id");
        }
        return encodedHash.substring(0, closing + 1);
    }

    public static void main(String[] args) {
        PasswordEncoder bcrypt10 = new BCryptPasswordEncoder(10);
        PasswordEncoder bcrypt12 = new BCryptPasswordEncoder(12);

        DelegatingPasswordEncoder encoder =
                new DelegatingPasswordEncoder(
                    "bcrypt12",
                    Map.of("bcrypt10", bcrypt10, "bcrypt12", bcrypt12)
                );

        MemoryUsers users = new MemoryUsers();

        // Giả lập dữ liệu bcrypt cũ KHÔNG prefix, đã xác minh nguồn:
        String oldBareHash = bcrypt10.encode("demo-password");

        // Chỉ gắn metadata {bcrypt10}; chưa rehash.
        String verifiedLegacyHash = "{bcrypt10}" + oldBareHash;
        users.put("mai", verifiedLegacyHash);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(users);

        AuthenticationManager manager = new ProviderManager(provider);

        System.out.println("before=" + idOf(users.storedHash("mai")));
        System.out.println("upgrade-needed-before="
                + encoder.upgradeEncoding(users.storedHash("mai")));

        Authentication first =
                authenticate(manager, "mai", "demo-password");
        System.out.println("first-login=" + first.isAuthenticated());

        String upgradedHash = users.storedHash("mai");
        System.out.println("after=" + idOf(upgradedHash));
        System.out.println("stored-hash-changed="
                + !verifiedLegacyHash.equals(upgradedHash));
        System.out.println("upgrade-needed-after="
                + encoder.upgradeEncoding(upgradedHash));

        Authentication second =
                authenticate(manager, "mai", "demo-password");
        System.out.println("second-login=" + second.isAuthenticated());

        String beforeWrong = users.storedHash("mai");
        boolean rejected = false;
        try {
            authenticate(manager, "mai", "wrong-password");
        } catch (BadCredentialsException expected) {
            rejected = true;
        }
        System.out.println("wrong-password-rejected="
                + (rejected && beforeWrong.equals(users.storedHash("mai"))));
    }
}
~~~

### 6.3. Chạy và đọc đầu ra

Với JDK 17 trở lên và Gradle có thể tải dependency từ Maven Central:

~~~bash
java -version
gradle --version
gradle run --quiet
~~~

Dòng do chương trình in ra theo thứ tự:

~~~text
before={bcrypt10}
upgrade-needed-before=true
first-login=true
after={bcrypt12}
stored-hash-changed=true
upgrade-needed-after=false
second-login=true
wrong-password-rejected=true
~~~

Đầu ra không in raw password hoặc giá trị hash; `BCryptPasswordEncoder` dùng salt ngẫu nhiên nên **chuỗi hash cụ thể sẽ khác mỗi lần chạy**, nhưng id và các boolean theo tình huống trên là ổn định.

Giải thích chậm từng bước:

1. `oldBareHash` là một bcrypt cost 10 **đã băm**, được tạo từ password demo để mô phỏng hệ cũ.
2. `verifiedLegacyHash` chỉ thêm prefix `{bcrypt10}`; cùng hash cũ vẫn dùng để kiểm tra password.
3. `DelegatingPasswordEncoder` có `idForEncode="bcrypt12"`, nên `upgradeEncoding` trên id bcrypt10 trả `true`.
4. `DaoAuthenticationProvider` xác minh password rồi dùng `UserDetailsPasswordService` ghi hash mới qua `updatePassword`.
5. `ConcurrentHashMap.replace(username, oldHash, newHash)` là **compare-and-set**: chỉ thay nếu giá trị hiện tại vẫn bằng giá trị mà request đã xác minh.
6. `User.withUserDetails(user).password(newPassword).build()` trả object cho provider tiếp tục flow; không băm lại `newPassword`.
7. `ProviderManager` mặc định có thể dọn credentials của result sau xác thực. Store giữ chuỗi hash độc lập, không lưu một `User` mutable dùng chung.
8. Lần thứ hai dùng id bcrypt12, không cần rehash tiếp; password vẫn xác minh đúng.
9. Với `wrong-password`, provider ném `BadCredentialsException`, không cập nhật hash; kiểm tra cuối giữ nguyên giá trị.

**Demo thật sự gọi provider và password service của Spring Security**, khác một chương trình chỉ tự gọi `encoder.matches` rồi giả lập migration. Tuy nhiên đây là bản in-memory để học; không thay thế thử nghiệm HTTP, DB transaction và khả năng chạy song song ở môi trường production.

### 6.4. Vì sao CAS quan trọng?

Nếu hai request login xuất hiện cùng lúc:

~~~text
T1 đọc hash cũ A
T2 đọc hash cũ A

T1 xác minh password và ghi hash mới B
T2 cố ghi hash mới C dựa trên A

CAS:
  T1: A -> B  (thành công)
  T2: A -> C  (thất bại, vì DB đang là B)
~~~

Với migration bcrypt rehash, nếu request thứ hai thất bại CAS chỉ vì request thứ nhất vừa nâng cấp **cùng mật khẩu**, ứng dụng có thể thiết kế quy trình retry có kiểm soát. Nhưng **nếu T2 thất bại vì người dùng vừa đổi/reset password ở phiên khác**, T2 không được “ghi đè cho xong” hoặc tự cấp Authentication từ credential đã bị thay thế.

Bản demo chọn fail closed bằng `AuthenticationServiceException` khi update đồng thời thất bại. Trong môi trường production, có thể reload bản ghi và đánh giá lại toàn bộ điều kiện theo policy trước khi quyết định retry; không retry với dữ liệu nhạy cảm vô hạn.

## 7. Kết nối UserDetailsPasswordService với database thật

Ở database SQL, đừng chỉ gọi:

~~~sql
-- KHÔNG an toàn trước cập nhật đồng thời:
UPDATE account_credentials
SET password_hash = :new_hash
WHERE username = :username;
~~~

Request login đang dùng hash cũ có thể chạy đè lên một lần reset password mới. Ngoài việc có thể mất thay đổi hợp lệ, đó còn có nguy cơ khôi phục quyền sử dụng password cũ đã bị thu hồi.

Một mẫu **compare-and-swap** tốt hơn:

~~~sql
UPDATE account_credentials
SET password_hash = :new_hash,
    password_algorithm = :new_algorithm,
    password_updated_at = CURRENT_TIMESTAMP
WHERE account_id = :account_id
  AND password_hash = :old_hash
  AND password_algorithm = :old_algorithm;
~~~

Các placeholder có dấu `:` là pseudo-SQL kiểu named parameters; với `JdbcTemplate` chuẩn cần dùng `?`, còn `NamedParameterJdbcTemplate` hỗ trợ named parameters. SQL phải điều chỉnh đúng schema và phương pháp lưu prefix; đừng lưu đồng thời hai nguồn thuật toán rồi để chúng mâu thuẫn.

Nếu mật khẩu lưu nguyên chuỗi `{id}hash`, có thể không cần cột `password_algorithm` riêng. Khi dùng cả hai, phải cập nhật **cùng transaction** và bảo đảm giá trị nhất quán. `account_id` ổn định đáng tin hơn username/email có thể đổi.

### Fragment JDBC Java

~~~java
// Fragment trong service đã có JdbcTemplate, cần repository, transaction,
// mapper và class UserDetails cụ thể. Không phải chương trình độc lập.
@Override
@Transactional
public UserDetails updatePassword(UserDetails user, String newEncoded) {
    if (newEncoded == null || user.getPassword() == null) {
        throw new AuthenticationServiceException(
                "Missing password during upgrade");
    }

    int updated = jdbc.update(
        "UPDATE app_accounts SET password_hash = ? " +
        "WHERE username = ? AND password_hash = ?",
        newEncoded, user.getUsername(), user.getPassword()
    );

    if (updated != 1) {
        throw new AuthenticationServiceException(
                "Password was updated concurrently");
    }

    return User.withUserDetails(user)
               .password(newEncoded)
               .build();
}
~~~

Trong production nên dùng **ID nội bộ** thay username, thêm điều kiện version khi cần và bảo đảm status/membership không bị thay ngoài ý muốn. Nếu bản ghi đang ở một transaction read-only, lệnh UPDATE không thể chạy như dự tính; phải quyết định transaction boundary phù hợp. Kết quả `updated==1` là bằng chứng cần cho lần thay đổi có hiệu lực.

**Thứ tự lưu và trả result:** service chỉ nên trả `UserDetails` với hash mới sau khi update database đã thành công. Nếu update lỗi mà vẫn trả authenticated result, ứng dụng sẽ lệch trạng thái và có thể vi phạm chính sách thu hồi credentials.

### Tách migration khỏi thao tác đổi mật khẩu chủ động

Có ít nhất ba nguồn phát sinh thay đổi hash:

1. Người dùng nhập đúng password cũ và provider nâng cấp hash **mà không đổi password**.
2. Người dùng đổi password qua một flow đã xác thực/step-up.
3. Người dùng reset password nhờ token/chứng cứ khôi phục riêng.

Ba nguồn này không có cùng mức độ đảm bảo và cũng không nên dùng cùng một hàm ghi DB bỏ qua audit. Mọi thay đổi hash phải được ghi nhận một cách tối thiểu, nhưng **không log password hoặc hash**.

## 8. Chọn chiến lược cho từng nhóm legacy

Không có một bộ chuyển đổi áp dụng cho mọi loại dữ liệu. Có thể lập bảng quyết định:

| Nhóm legacy | Có thể xác minh tạm? | Có thể nâng cấp tự động lúc login? | Hướng vận hành |
| --- | --- | --- | --- |
| bcrypt cost thấp, có prefix | Có, nếu hệ thống còn chấp nhận policy | Có, sau khi `matches` đúng | Rehash-on-login, đo tiến độ |
| bcrypt thiếu prefix nhưng nguồn xác định | Có, sau bước gắn metadata/adapter hẹp | Có, sau login | Chuẩn hóa prefix và nâng cost |
| PBKDF2/scrypt/Argon2 cũ, params biết rõ | Có thể, cần đúng version/params | Có, nếu encoder tương thích và user đăng nhập | Dùng id phân biệt version; rehash |
| Salted SHA-1/MD5 tự chế | Chỉ cân nhắc trong cửa sổ chuyển đổi đã đánh giá rủi ro | Về mặt kỹ thuật có thể khi raw đúng, nhưng thuật toán yếu | Ưu tiên force reset; sunset rõ và giám sát |
| Unsalted hash yếu | Rủi ro cao | Có thể xác minh rồi rehash, nhưng không được kéo dài | Reset ưu tiên, giảm exposure |
| Plaintext | Không nên duy trì login từ dữ liệu dễ lộ | Có raw nhưng hệ đã có rủi ro | Xử lý sự cố và bắt buộc đổi/reset |
| Không rõ thuật toán/pepper/charset | Không có verifier đáng tin | Không | Khóa đường đăng nhập liên quan và reset an toàn |
| Không hoạt động lâu | Có thể còn hash rất cũ | Không có raw password nếu chưa login | Campaign reset/expiration, không chờ vô hạn |
| Tài khoản SSO không có password nội bộ | Không có hash để nâng cấp | Không | Chuyển trách nhiệm sang IdP; không tự tạo mật khẩu |

**Chìa khóa:** “có thể xác minh cũ” không đồng nghĩa “an toàn để tiếp tục chấp nhận vô hạn”. Trong trường hợp hash yếu, hãy đặt ngày hết hạn cho verifier legacy và quy trình reset cho người chưa chuyển đổi; tùy tình hình cần chặn login cũ ngay.

### Trường hợp không thể xác minh old hash

Không cố gắng suy đoán mật khẩu gốc hay đổi hash bằng cách hash chính old hash. Quy trình reset an toàn là hướng hợp lý: xác minh quyền sở hữu bằng kênh đáng tin, phát token reset một lần và ngắn hạn, lưu hash của token nếu lưu server-side, kiểm soát TTL và replay, sau đó tạo hash mới từ password do user đặt.

Đặc biệt, **không gửi mật khẩu mới bằng plaintext qua email**, không gửi hash cũ để “người dùng tự khôi phục”, và không tạo password mặc định giống nhau cho cả nhóm tài khoản.

## 9. Work factor: chọn mức mới có thể vận hành được

Các thuật toán password hashing hiện đại dùng **chi phí tính toán cố ý cao**. Với bcrypt, `strength` hoặc `cost` là hệ số log2 rounds: chi phí tăng nhanh khi tăng cost.

Ví dụ:

~~~java
PasswordEncoder bcrypt10 = new BCryptPasswordEncoder(10);
PasswordEncoder bcrypt12 = new BCryptPasswordEncoder(12);
~~~

Cost 12 thường tốn nhiều công hơn cost 10; **không** nghĩa “độ an toàn cao gấp đúng bốn lần” theo một thước đo tuyến tính áp dụng cho mọi hardware. Mục tiêu là làm password guessing offline tốn tài nguyên, đồng thời hệ thống còn đủ năng lực xử lý tải login hợp pháp.

Tài liệu Spring Security khuyên cân chỉnh work factor dựa trên thời gian xác minh thực tế trên hệ thống (tài liệu đưa một mốc tham khảo cỡ một giây cho thao tác verify), không dùng mặc định một con số cho mọi máy. Cần đo:

- P50/P95/P99 latency cho `PasswordEncoder.matches` và `encode`.
- Số request login đồng thời, CPU/memory và queue, đặc biệt khi có brute-force.
- Chi phí rehash-on-login trong thời gian migration (mỗi lần login cũ có thêm thao tác hash).
- Mức tải khi người dùng đăng nhập hàng loạt sau deploy và tác động autoscaling.
- Giới hạn request/rate-limit, timeout, circuit breaker/compromised-password checks nếu tích hợp.

**Đừng hạ cost đến mức yếu chỉ để qua bài load test**, nhưng cũng đừng đẩy cost cao đến mức kẻ tấn công gửi nhiều yêu cầu làm cạn tài nguyên xác thực. Sử dụng rate-limit nhiều lớp và theo dõi hệ thống.

### Nếu chọn Argon2, scrypt hoặc PBKDF2

Cũng cần mô tả tường minh **version của implementation, tham số, salt, output format và dependency tương ứng**. Đừng đổi `{id}` của một hash bcrypt thành `{argon2}` mà không tính lại từ raw password. `{id}` là selector, không phải phép chuyển đổi mật mã.

Một migration từ bcrypt sang Argon2 có thể dùng `DelegatingPasswordEncoder` với cả hai verifier, đặt `idForEncode` mới, rehash-on-login và reset cho tài khoản lâu không hoạt động. Nhưng khả năng chọn Argon2 còn phụ thuộc chính sách tổ chức, runtime và nguồn thư viện, nên phải đối chiếu dependency/security review của phiên bản đang dùng.

## 10. Bẫy của bcrypt: giới hạn độ dài và chuẩn hóa Unicode

**Bcrypt truyền thống có giới hạn đầu vào theo byte**, thường liên quan mốc 72 byte. Một số implementation có thể cắt/ngừng chấp nhận những chuỗi dài quá giới hạn, và cách chuyển `String` thành bytes ảnh hưởng hành vi. Đối với mật khẩu có emoji hoặc ký tự Unicode, 72 **byte** không phải 72 **ký tự**.

Trong migration, cần xác nhận:

1. Hệ cũ đã dùng encoding nào để biến mật khẩu thành bytes?
2. Có cắt/truncate mật khẩu dài không, và cắt trước hay sau khi UTF-8 encode?
3. Có `trim`, chuyển lower-case hoặc normalization Unicode trước khi hash không?
4. Nếu thay thư viện bcrypt, phiên bản mới có xử lý cùng kiểu `$2a`, `$2b`, `$2y` không?
5. Có tài khoản dùng password rất dài hoặc mật khẩu chứa ký tự đa byte không?

**Đừng âm thầm đổi cách chuẩn hóa mật khẩu trong đợt rehash**; cùng mật khẩu người dùng nhập có thể cho kết quả so khớp khác giữa hai implementation. Nếu cần sửa một hợp đồng xử lý password cũ không an toàn, phải có kế hoạch chuyển đổi/đặt lại rõ ràng; không “tự cắt” password mới để hợp legacy.

Ví dụ này dùng password ASCII ngắn để tập trung vào cơ chế upgrade, không chứng minh mọi password cũ trên đời đều tương thích.

## 11. Pepper, salt và việc đổi khóa bên ngoài hash

- **Salt** là giá trị khác nhau theo từng password hash, thường có thể được lưu cùng hash và không phải bí mật. Bcrypt đã có cấu trúc chứa salt và tham số.
- **Pepper** là secret bổ sung do ứng dụng/tổ chức quản lý (nếu thiết kế sử dụng), cần lưu ở secret manager/HSM hoặc kho phù hợp, không đặt chung database như password hash.
- **Hash work factor** điều khiển chi phí tính toán, không thay thế salt/pepper.

Khi migration một hệ từng dùng pepper, cần biết **phiên bản pepper**, cách kết hợp (trước hash hay sau), encoding và nơi quản lý. Nếu mất pepper của hash cũ, có thể không còn cách xác minh password cũ, dù vẫn có hash trong DB; hướng khôi phục thường là reset.

Không ghi pepper vào source code, `application.properties` commit trong repository, migration logs hoặc message queue. Nếu hệ thống có pepper rotation, phải hỗ trợ versioning hoặc các bước phù hợp. Việc đổi pepper không thể tự giải quyết bằng đổi tiền tố `{id}` trừ khi định dạng có đầy đủ verifier tương thích với phiên bản đó.

### Có nên “hash lồng” để nhanh chóng chữa SHA-1 cũ không?

Một phép `bcrypt(sha1(password))` có thể được cân nhắc như **lớp bọc tạm trong một thiết kế đặc biệt** khi chưa có raw password, nhưng không tương đương `bcrypt(password)`. Nếu SHA-1 hash cũ từng bị lộ, attacker đã có đầu vào để đoán hoặc tính theo cơ chế bọc. Nó cũng giữ lại mọi hạn chế cũ (encoding, độ dài, normalization, salt). Vì vậy **không coi hash lồng là hoàn tất migration**; cần kế hoạch thay trực tiếp bằng hash từ raw password mới/xác minh, hoặc buộc reset theo chính sách.

## 12. Rollout có kiểm soát trong môi trường nhiều phiên bản ứng dụng

Một đợt migration tốt thường có pha rõ ràng:

| Pha | Thao tác | Điểm chặn chuyển pha |
| --- | --- | --- |
| Inventory | Thống kê format/algorithm/work factor và tỉ lệ user hoạt động | Không còn nhóm “unknown” chưa có policy |
| Chuẩn bị schema | Cột lưu đủ độ dài cho prefix/hash mới, unique/constraints, backup | Kiểm thử đọc/ghi không truncate |
| Compatibility read | Triển khai encoder đọc được **các id đã được phê duyệt** | User legacy hợp lệ vẫn login được |
| Normalization | Gắn prefix cho nhóm hash cũ đã được chứng minh | Sample verification và migration audit đạt |
| New writes | Tất cả đăng ký/đổi/reset password tạo hash theo policy mới | Không phát sinh bản ghi mới ở định dạng cũ |
| Rehash-on-login | Gắn `UserDetailsPasswordService`, CAS, metric | Login cũ nâng cấp an toàn, no privilege escalation |
| Sunset | Gỡ verifier yếu sau cửa sổ chính sách, reset user chưa chuyển | Tỉ lệ legacy về ngưỡng được phê duyệt |
| Cleanup | Xóa flag, code adapter cũ, secret/pepper không còn dùng | Audit/metrics không còn đường fallback |

### Expand → migrate → contract

Khi deploy nhiều node hoặc dùng rolling deployment, phải nghĩ về **tương thích hai chiều**:

~~~text
Node V1: hiểu {bcrypt10}, không hiểu {bcrypt12}
Node V2: hiểu {bcrypt10} và {bcrypt12}, ghi {bcrypt12}

Nếu bật ghi V2 sớm:
  user đăng nhập V2 -> DB được nâng lên {bcrypt12}
  user gọi tiếp V1 -> V1 có thể không xác minh hash mới
~~~

Để tránh lỗi:

1. **Expand:** triển khai tất cả node biết **đọc cả old và new** trước.
2. **Migrate:** chỉ khi đội node đã tương thích mới bật ghi hash mới/rehash.
3. **Contract:** sau khi tỷ lệ legacy giảm và deadline reset đến, ngừng đọc thuật toán cũ.

Cách này cũng ảnh hưởng rollback: nếu rollback về V1 không hiểu hash mới, tài khoản đã được nâng cấp sẽ bị khóa ngoài. Cần chuẩn bị release rollback **vẫn hiểu cả định dạng mới**, hoặc kế hoạch tương thích trước khi chuyển pha; đừng nghĩ restore database backup cũ là giải pháp đơn giản vì nó có thể khôi phục mật khẩu đã bị đổi/thu hồi.

### Tách feature flag đọc cũ và ghi mới

Hai cờ có thể được quản lý riêng:

~~~text
password.allowLegacyVerification = true/false
password.writeTargetAlgorithm = bcrypt12
password.upgradeOnSuccessfulLogin = true/false
~~~

Đây là **các tên chính sách giả định**, không phải property có sẵn của Spring Boot. Chúng phải được triển khai có kiểm soát trong code/config nếu dự án cần. Không để người dùng thường hoặc query parameter thay đổi flags.

## 13. Error handling và tính an toàn khi migration thất bại

Trong một yêu cầu login:

| Lỗi | Phân loại nội bộ | Cách phản ứng |
| --- | --- | --- |
| Raw password sai | `BadCredentialsException` | Không rehash; response login thất bại an toàn |
| Username không tồn tại | Thường được provider che thành bad credentials | Không lộ danh sách account |
| Hash thiếu id không được map | Dữ liệu không tương thích/config lỗi; có thể là `IllegalArgumentException` | Fail closed, phân loại và hướng khôi phục; không thêm fallback bừa |
| Hash đúng nhưng `upgradeEncoding` phát hiện policy mới | Không phải lỗi | Encode raw và cập nhật có CAS |
| Đổi mật khẩu đồng thời làm CAS thất bại | Cạnh tranh cập nhật credential | Không ghi đè; kiểm tra lại theo policy hoặc fail closed |
| DB tạm mất kết nối | Service failure | Không tự cấp login, không đánh dấu password sai |
| `UserDetailsPasswordService` không được cấu hình | Tính năng upgrade không diễn ra dù encoder đề nghị | Theo dõi metric; bổ sung wiring theo thiết kế |
| Tài khoản disabled/locked/expired | Account status | Không dùng rehash để lách policy trạng thái |
| Cost mới gây timeout | Capacity/performance issue | Đo và chỉnh chiến lược an toàn, không vô hiệu hóa authentication |
| Legacy verifier đã sunset | Không còn hỗ trợ kiểu cũ | Reset bằng cơ chế đã xác minh thay vì mở lại thuật toán yếu |

Cần **fail closed**: không có bằng chứng mật khẩu đúng thì không phát `Authentication` hợp lệ. Nhưng fail closed không có nghĩa được phép che mọi sự cố thành “mật khẩu sai”; log và metric nội bộ phải phân biệt lỗi hạ tầng, dữ liệu cũ sai format, policy hết hạn và credentials thật sự không khớp.

### Khi cần support người dùng

Đừng gửi qua email thông báo “tài khoản abc có mật khẩu SHA-1 cũ” cho địa chỉ chưa được xác minh. Một người lạ có thể dùng thông tin đó để suy đoán tài khoản tồn tại hoặc độ yếu của credentials. Giao diện đăng nhập nên giữ thông báo an toàn, còn đường reset/kích hoạt chi tiết phải có xác minh phù hợp.

## 14. Đo tiến độ migration mà không lộ password hash

Chỉ nên xuất **chỉ số tổng hợp** theo policy/algorithm, ví dụ:

~~~text
password_hash_inventory{policy="bcrypt10"}  12400
password_hash_inventory{policy="bcrypt12"}  38500
password_migration_success_total              710
password_migration_cas_conflict_total           3
password_migration_unknown_format_total         8
password_login_latency_bucket{...}             ...
~~~

Các số trên **chỉ là minh họa**, không phải dữ liệu thật. Khi thiết kế metric:

- Không gắn full username/email hoặc raw hash làm label.
- Có thể dùng account ID trong audit nội bộ có quyền truy cập hạn chế và retention phù hợp.
- Không để raw password, password hash, bearer token, DB secret hoặc pepper vào log.
- Tránh biến code migration thành công cụ dò account/algorithm qua public response hoặc thời gian xử lý.
- Phân biệt `login_success` với `rehash_success`: có login thành công không có nghĩa hash được nâng cấp nếu chưa có password service.
- Theo dõi user lâu không đăng nhập và tài khoản đang disable/locked; xử lý theo reset policy.

### KPI không nên dùng một mình

“100% lần login hôm nay dùng bcrypt12” **không** nghĩa “100% tài khoản đã được nâng cấp”: các account chưa login vẫn có thể giữ hash cũ. Vì vậy đo cả **tỉ lệ credential records theo id** và **độ tuổi lần xác thực**. Khi deadline kết thúc hỗ trợ legacy, các account chưa nâng cấp cần reset theo quy trình.

## 15. Ma trận kiểm thử kỹ thuật

Một migration đáng tin phải test đồng thời encoder, provider, storage và luồng web. Các trường hợp tối thiểu:

| Trường hợp | Kỳ vọng |
| --- | --- |
| User bcrypt10 nhập đúng password | Login thành công, stored hash chuyển sang `{bcrypt12}` |
| User bcrypt12 nhập đúng | Login thành công, không cần ghi lại hash vì policy đã đạt |
| User bcrypt10 nhập sai | Login thất bại, hash giữ nguyên |
| Unknown username | Không tự tạo user, không lộ account existence |
| Hash thiếu id nhưng không thuộc nhóm đã kiểm chứng | Fail closed, không thử `NoOp` hoặc đoán format |
| Bare bcrypt đã được xác minh nguồn | Gắn prefix đúng, `matches` hợp lệ, rồi mới rehash-on-login |
| Hash lưu sai/truncate | Không cấp quyền, báo sự cố định dạng nội bộ |
| User disabled/locked/expired | Không cho login chỉ vì password khớp |
| Hai login cùng nâng cấp từ cùng hash | Một CAS thành công, request còn lại xử lý conflict theo policy |
| User đổi/reset password lúc login legacy | Migration không ghi đè hash mới |
| DB không sẵn sàng ở bước cập nhật | Không lặng lẽ báo upgrade thành công; policy rõ fail closed/retry |
| `UserDetailsPasswordService` vắng mặt | Có thể login thành công nhưng hash không được nâng cấp; metric/cảnh báo |
| `UserDetails` bị cache chung object | Không mất password hash trong cache vì credential erasure |
| Unicode, password dài, old charset | Tương thích verifier hoặc chuyển reset rõ ràng |
| Pepper/key cũ không còn | Không đoán bí mật; reset an toàn |
| Rolling deploy V1/V2 | Mọi node active đọc được hash mới trước khi bật ghi |
| Rollback build | Vẫn đọc được hash đã nâng cấp, không khôi phục credential bị thu hồi |
| User inactive qua deadline | Reset/khóa đường legacy theo chính sách, không chờ vô hạn |
| Rate-limit và tải cao | Login throughput, P95/P99, CPU/memory đáp ứng SLO |
| API failure handler | Không lộ thuật toán, plaintext, hash, stack trace, DB details |

**Lưu ý về `@WithMockUser`:** annotation này dựng sẵn `Authentication` để test authorization, thường **không gọi** `DaoAuthenticationProvider`/ `PasswordEncoder`. Muốn chứng minh nâng cấp hash sau login thật, phải gọi `AuthenticationManager.authenticate` hoặc gửi credentials qua filter login trong integration test. Ví dụ ở phần 6 gọi manager thật.

### Kiểm thử tính chất, không so chuỗi bcrypt cố định

Bcrypt sử dụng salt ngẫu nhiên; vì vậy hai lần `encode("demo-password")` thường tạo chuỗi khác nhau. Không nên assert hash bytes bằng một literal cố định nếu không kiểm soát salt. Thay vào đó, kiểm tra:

~~~java
// Fragment test có encoder và actualHash đã được tạo.
assertTrue(encoder.matches("demo-password", actualHash));
assertTrue(actualHash.startsWith("{bcrypt12}"));
assertFalse(encoder.upgradeEncoding(actualHash));
~~~

Cần static imports JUnit và môi trường test phù hợp. Đoạn trên minh họa assertion, không phải chương trình độc lập. Với end-to-end login, assert DB hash đã đổi nhưng vẫn `matches` với cùng raw password và request sai không gây thay đổi.

## 16. Những lỗi phổ biến cần tránh

1. **“Hash cũ giải mã được, chỉ cần lấy plaintext rồi mã hóa lại.”** Sai với password hashing đúng nghĩa.
2. **“Gọi `encode(oldHash)` là nâng cấp.”** Sai: tạo hash của hash cũ, không phải của raw password.
3. **“Gắn `{bcrypt12}` trước hash cost 10 là đã tăng bảo mật.”** Sai: chỉ đổi metadata, không thay cost của hash.
4. **“Id `bcrypt10` và `bcrypt12` là id mặc định của Spring Security.”** Trong bài chúng là id tùy chỉnh có khai báo map.
5. **“Thay `idForEncode` sẽ tự nâng tất cả row.”** Không: nó chỉ quyết định encode mới; cần login/reset để có raw.
6. **“Dùng `setDefaultPasswordEncoderForMatches(NoOp)` sửa mọi record legacy.”** Rất nguy hiểm; mở rộng đối tượng được chấp nhận theo kiểu không an toàn.
7. **“Mọi chuỗi không prefix đều là bcrypt.”** Không; phải xác định nguồn và format.
8. **“`upgradeEncoding=true` tự ghi DB.”** Không; cần `UserDetailsPasswordService`/bộ cập nhật có transaction.
9. **“`updatePassword` nhận raw password.”** Không; đối số là hash mới đã được encode theo policy.
10. **“`updatePassword` nên tự encode lại cho chắc.”** Không; dẫn đến double hashing.
11. **“Password sai cũng có thể nâng cấp.”** Không; chưa có raw được xác minh.
12. **“UserDetails có cùng quyền nghĩa mọi account đều được nâng.”** Không; migration dựa trên credential và policy.
13. **“Update theo username không điều kiện là đủ.”** Có thể ghi đè password reset đồng thời; cần CAS/version.
14. **“CAS thất bại thì cứ ghi đè bằng UPDATE lần hai.”** Có nguy cơ khôi phục credential cũ đã bị thu hồi.
15. **“Hash của database có thể ghi log vì không phải plaintext.”** Hash vẫn nhạy cảm và dễ bị tấn công offline nếu lộ.
16. **“Giữ verifier MD5/SHA-1 mãi cũng không sao khi có rate limit.”** Nếu database bị đánh cắp, rate limit online không ngăn offline cracking.
17. **“Tài khoản không đăng nhập thì tự động đã được nâng cấp.”** Không: thiếu raw password, cần reset hoặc cơ chế được thiết kế riêng.
18. **“Bcrypt cost 12 là đáp án vĩnh viễn.”** Cần benchmark, cập nhật policy theo hạ tầng và đe dọa.
19. **“Một `PasswordEncoder` bean trong Boot đổi là đủ cho mọi custom provider.”** Custom provider có thể dùng encoder khác; phải kiểm tra wiring thực tế.
20. **“Có `UserDetailsPasswordService` bean thì mọi Spring Security version/flow đều tự động dùng.”** Cần bảo đảm provider cụ thể được cấu hình để gọi service và có test.
21. **“Sau upgrade người dùng không cần đổi password bị lộ.”** Rehash không làm password đã lộ trở lại bí mật; cần reset khi có sự cố.
22. **“Đổi hash là thu hồi session/JWT cũ.”** Không mặc định; session/token có vòng đời riêng.
23. **“Đã dùng BCrypt thì không cần quan tâm Unicode/giới hạn byte.”** Sai; cần kiểm tra tương thích format trước và sau migration.
24. **“Rolling deploy không cần tính đến code node cũ.”** Node cũ có thể không đọc được format mới.
25. **“Restore snapshot DB cũ là rollback migration an toàn.”** Có thể khôi phục password đã đổi/thu hồi; cần kế hoạch rollback có kiểm soát.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không thể chuyển một hash SHA-1 đã lưu sang bcrypt tương đương chỉ bằng một batch SQL?

*Trả lời:* Không có raw password. Bcrypt(SHA-1(password)) khác với bcrypt(password). Muốn tạo hash trực tiếp từ raw phải có password người dùng cung cấp hợp lệ khi login/reset.

**Câu 2.** `{bcrypt10}$2a$10$...` khác `{bcrypt12}$2a$10$...` ở điểm nào nếu phần sau vẫn giữ nguyên?

*Trả lời:* Chỉ metadata khác, **cost bên trong bcrypt vẫn là 10**. Không được khai báo sai id để giả vờ đã nâng work factor; chỉ khi rehash tạo một hash cost 12 mới có nâng cấp thật.

**Câu 3.** `DelegatingPasswordEncoder` có thể xác minh old bcrypt và ghi new bcrypt ở cùng ứng dụng không?

*Trả lời:* Có. Map old/new ids vào verifier tương ứng, chọn `idForEncode` mới, và dùng điểm lưu hash mới sau khi `matches` thành công.

**Câu 4.** Tại sao `UserDetailsPasswordService` được cần trong một số flow upgrade tự động?

*Trả lời:* `PasswordEncoder.upgradeEncoding` chỉ trả boolean, không ghi dữ liệu. `DaoAuthenticationProvider` có thể dùng password service để cập nhật hash đã encode sau xác thực.

**Câu 5.** User đổi mật khẩu trong lúc login khác đang rehash theo hash cũ. Phải đề phòng điều gì?

*Trả lời:* Không ghi đè hash mới bằng dữ liệu dựa trên hash cũ. Dùng CAS/version, xử lý race theo policy và fail closed khi không còn chứng cứ phù hợp.

**Câu 6.** Khi dữ liệu cũ là bcrypt không prefix, có thể thêm `{bcrypt10}` mà không cần plaintext không?

*Trả lời:* Chỉ khi đã xác minh loại hash thật sự và chính sách ID phù hợp. Đây là chuẩn hóa metadata; rehash tăng work factor vẫn cần raw password lúc login/reset.

**Câu 7.** Vì sao không nên dùng `{noop}` làm đường fallback cho mọi mật khẩu legacy?

*Trả lời:* NoOp chấp nhận so plaintext, không cung cấp password hashing an toàn. Việc đặt fallback rộng có thể vô tình chấp nhận dữ liệu bị lưu sai hoặc yếu.

**Câu 8.** Khi dùng nhiều app node trong rolling deploy, phải bật tính năng đọc hay ghi hash mới trước?

*Trả lời:* Tất cả node phải **đọc hiểu hash mới** trước khi bất kỳ node nào bắt đầu ghi hash mới, nếu không rollback/định tuyến request sang node cũ gây lỗi login.

**Câu 9.** Làm thế nào biết chiến dịch đã xong khi còn 20% tài khoản không đăng nhập 2 năm?

*Trả lời:* Phải đo inventory theo bản ghi credential, không chỉ login traffic; có deadline và reset cho nhóm không thể nâng qua login. Có thể ngừng verifier legacy khi các điều kiện an toàn và truyền thông đã được hoàn thành.

**Câu 10.** Vì sao rehash không phải cách xử lý đầy đủ khi password đã bị rò rỉ?

*Trả lời:* Bên thứ ba có thể đã biết raw password. Chỉ đổi hash ở server không làm raw password ấy trở nên bí mật; phải đổi/reset và xem xét thu hồi session/token, giám sát tài khoản theo chính sách.

**Câu 11.** Mật khẩu dài chứa Unicode bị login sai sau migration dù người dùng khẳng định nhập đúng. Nên kiểm tra gì?

*Trả lời:* Character encoding, Unicode normalization, xử lý giới hạn byte bcrypt, quy tắc trim/truncate cũ và format hash/pepper; không tùy tiện biến mật khẩu người dùng thành lower-case.

**Câu 12.** Nếu `upgradeEncoding("{bcrypt12}...")` trả false, có nghĩa hash ấy không bao giờ cần nâng nữa không?

*Trả lời:* Không. Nó chỉ phản ánh policy của encoder hiện tại; khi threat model hoặc mức cost mục tiêu thay đổi, chính sách và idForEncode có thể được nâng cấp tiếp.

## 18. Checklist áp dụng vào sản phẩm thật

- [ ] Đã kiểm kê chính xác định dạng hash cũ theo nguồn và metadata, không đoán bằng độ dài.
- [ ] Schema mới đủ chỗ lưu `{id}`, salt/params/hash; migration được backup và kiểm thử.
- [ ] Mọi bản ghi legacy có thuật toán/charset/pepper được xác định hoặc có đường reset an toàn.
- [ ] Không lưu plaintext, không thêm NoOp làm fallback toàn cục, không log hash/token/password.
- [ ] Encoder map chỉ chứa các thuật toán được duyệt, idForEncode đại diện chính sách ghi mới.
- [ ] Nếu bổ sung prefix cho bare bcrypt, nguồn hash được xác minh; không xem việc gắn prefix là rehash.
- [ ] Các flow đăng ký, đổi mật khẩu, reset đều tạo hash theo chính sách mới.
- [ ] Provider thực sự dùng `PasswordEncoder` đã cấu hình, và hỗ trợ `UserDetailsPasswordService` khi cần.
- [ ] Chỉ rehash **sau xác thực thành công**, không encode(oldHash), không double encode.
- [ ] `UserDetailsPasswordService` ghi hash bằng CAS/version hoặc transaction phù hợp, không ghi đè password reset đồng thời.
- [ ] UserDetails cache không chia sẻ mutable principal bị erasure làm mất hash.
- [ ] Thời điểm login sai, account disabled/locked và DB lỗi không làm phát sinh update hash.
- [ ] Có đo work factor trên hạ tầng thật, kiểm soát quá tải/rate limits trong thời gian rehash.
- [ ] Có test cho bcrypt old/new, wrong password, concurrent update, unknown ID, Unicode/password dài và DB failure.
- [ ] Rollout theo expand-read, migrate-write, contract-remove; node cũ không phá việc đọc hash mới.
- [ ] Rollback không đưa password đã thu hồi trở về và không khôi phục thuật toán yếu vô thời hạn.
- [ ] Có migration metrics theo số **credential records**, không chỉ lượng login.
- [ ] Có deadline và kế hoạch reset cho tài khoản chưa login, hash rất yếu hoặc không tương thích.
- [ ] Sau khi xong, gỡ mã legacy verifier/flags, cập nhật tài liệu vận hành và cảnh báo.
- [ ] Nếu phát hiện password leak, có quy trình đổi/reset và thu hồi phiên/token, không chỉ rehash.

### Tổng kết

**Nâng cấp password hash là một quá trình thay đổi cách lưu bằng chứng xác thực, không phải phép giải mã.** Có thể thêm metadata cho một hash cũ đã được nhận diện chính xác mà không cần raw password. Nhưng để thực sự nâng mức bảo vệ, hệ thống phải xác minh mật khẩu người dùng nhập đúng và tạo **hash mới từ raw password**, hoặc cho người dùng đặt lại mật khẩu qua một quy trình an toàn.

Trong Spring Security, bộ ba `DelegatingPasswordEncoder` – `DaoAuthenticationProvider` – `UserDetailsPasswordService` cung cấp nền tảng cho rehash-on-login; ứng dụng vẫn phải xử lý database CAS, concurrency, cache, observability, rolling deployment và ngày ngừng hỗ trợ legacy. Làm đúng toàn bộ vòng đời mới giúp chuyển đổi mà không làm người dùng bị khóa ngoài hoặc giữ lại rủi ro của hệ thống cũ.

### Tài liệu chính thức

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — DelegatingPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security — UserDetails và Credentials Management](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
