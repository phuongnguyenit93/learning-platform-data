# PasswordEncoder trong quá trình lưu và kiểm tra mật khẩu

Hãy hình dung một ứng dụng Spring Security có chức năng đăng ký tài khoản và đăng nhập bằng tên người dùng, mật khẩu. Khi Mai đăng ký, máy chủ nhận mật khẩu mà cô vừa nhập. Một thời gian sau, Mai đăng nhập bằng mật khẩu ấy. Máy chủ cần kiểm tra xem thông tin Mai đưa ra có đúng hay không, nhưng **không nên lưu mật khẩu gốc trong cơ sở dữ liệu**.

`PasswordEncoder` là hợp đồng của Spring Security giúp giải quyết phần việc này: **chuyển mật khẩu thành một giá trị lưu trữ theo hàm một chiều phù hợp**, và **kiểm tra mật khẩu do người dùng nhập với giá trị đã lưu**. Thường gọi kết quả là *password hash* (giá trị băm mật khẩu), dù các thuật toán lưu mật khẩu hiện đại còn kết hợp salt và các tham số tính toán.

Để hiểu đúng, cần tách ba giai đoạn:

- **Đăng ký hoặc đổi mật khẩu:** dùng `encode(rawPassword)` để tạo giá trị sẽ lưu.
- **Đăng nhập:** dùng `matches(rawPassword, encodedPassword)` để kiểm tra, trong đó `encodedPassword` lấy từ nơi lưu trữ đáng tin cậy.
- **Nâng cấp cách lưu:** xem xét `upgradeEncoding(encodedPassword)` sau khi người dùng vừa chứng minh được mật khẩu đúng, rồi tạo hash mới nếu chính sách cho phép.

`PasswordEncoder` không phải bộ điều khiển đăng nhập, không tạo JWT, không tự đặt quyền và không trực tiếp quyết định người dùng được phép truy cập URL nào. Nó cung cấp thao tác bảo vệ/kiểm tra mật khẩu cho các thành phần xác thực.

## 1. Vì sao không lưu mật khẩu gốc?

Nếu bảng người dùng lưu:

~~~text
username | password
---------+----------------
mai      | MySecret@2026
an       | AnotherSecret!
~~~

thì bất kỳ người hoặc sự cố nào đọc được bảng ấy cũng nhìn thấy toàn bộ mật khẩu. Rủi ro còn lan sang các dịch vụ khác nếu người dùng tái sử dụng mật khẩu.

Cách thiết kế cần hướng tới là:

~~~text
username | password_hash
---------+-------------------------------------------------
mai      | {bcrypt}$2a$...<hash và thông tin cần thiết>
an       | {bcrypt}$2a$...<hash và thông tin cần thiết>
~~~

Các chuỗi trên chỉ **mô tả hình dạng dữ liệu**, không phải hash hợp lệ để đưa vào sản phẩm. Trong thực tế, bộ mã hóa sinh salt và giá trị hash có định dạng riêng.

### Hash mật khẩu khác mã hóa có thể giải mã

| Cách xử lý | Mục tiêu | Có thể đảo ngược bằng khóa? | Phù hợp để lưu mật khẩu đăng nhập? |
| --- | --- | --- | --- |
| Lưu văn bản gốc | Giữ nguyên thông tin | Không cần giải mã | **Không** |
| Base64/hex | Biến đổi cách biểu diễn | Dễ khôi phục | **Không** |
| Mã hóa đối xứng | Cho phép bên giữ khóa giải mã | Có | Thường **không cần** cho mật khẩu người dùng |
| SHA-256 đơn thuần | Hàm băm nhanh, hữu ích cho các tác vụ khác | Không có phép giải mã trực tiếp | **Không nên** dùng một mình để lưu mật khẩu |
| Hàm băm mật khẩu thích ứng như bcrypt, scrypt, Argon2id hoặc PBKDF2 với tham số phù hợp | Làm việc thử đoán mật khẩu tốn chi phí | Không có phép giải mã thông thường | **Có**, khi cấu hình đúng |

Dù hash một chiều không thể được “giải mã” như ciphertext, người tấn công vẫn có thể **đoán** mật khẩu và tự kiểm tra từng ứng viên. Vì thế chỉ chọn một hàm băm bất kỳ là chưa đủ: thuật toán phải **cố ý tốn tài nguyên** để làm chậm hành vi thử hàng loạt.

Các hàm băm nhanh như SHA-256 có ứng dụng hợp lệ trong kiểm tra tính toàn vẹn, chữ ký, định danh nội dung. Vấn đề là **tốc độ quá cao** khi dùng trực tiếp để bảo vệ một bí mật do con người lựa chọn.

## 2. Vị trí của PasswordEncoder trong bản đồ Spring Security

Một luồng xác thực mật khẩu bằng servlet có thể hiểu như sau:

~~~text
         ĐĂNG KÝ                                 ĐĂNG NHẬP
              |                                      |
     Người dùng nhập password               Người dùng nhập password
              |                                      |
              v                                      v
  Ứng dụng kiểm tra chính sách             Authentication request
              |                                      |
              v                                      v
      PasswordEncoder.encode                  AuthenticationManager
              |                                      |
              v                                      v
       Chuỗi password_hash                   DaoAuthenticationProvider
              |                                      |
              v                              +-------+-------+
       Lưu trong database                    |               |
                                        UserDetailsService   PasswordEncoder
                                        lấy UserDetails      .matches(raw, hash)
                                        và password hash     |
                                                   +---------+
                                                   |
                                            Kiểm tra thành công?
                                               /           \
                                             Có             Không
                                             |                |
                                      Authentication       Lỗi xác thực
                                      được tin cậy         (thường exception)
                                             |
                                             v
                                      Kiểm tra authorization
                                      trên thao tác/tài nguyên
~~~

Các vai trò:

- **`PasswordEncoder`:** thực hiện encode và matches; không biết người dùng có role nào.
- **`UserDetailsService`:** tìm thông tin người dùng từ nguồn đáng tin, trong đó có **hash đã lưu**; bản thân interface này không nhận trách nhiệm kiểm tra mật khẩu.
- **`DaoAuthenticationProvider`:** triển khai `AuthenticationProvider`, sử dụng `UserDetailsService` và `PasswordEncoder` để xác thực cặp tên/mật khẩu.
- **`AuthenticationManager`**, thường được triển khai bởi `ProviderManager`: điều phối các provider được cấu hình.
- **`Authentication`:** biểu diễn yêu cầu hoặc kết quả xác thực.
- **Authorization:** sau khi xác thực, hệ thống tiếp tục xét các quyền như `ROLE_USER`, `DOC_READ`, chính sách dữ liệu, v.v.

Khi user nhập mật khẩu sai, bước `matches` sẽ không xác minh được thông tin đó. Trong một flow phổ biến, provider báo lỗi qua `AuthenticationException`, chẳng hạn `BadCredentialsException`; đừng hình dung rằng `PasswordEncoder` tự trả về response HTTP 401 hay redirect trang đăng nhập. Đó là trách nhiệm của các lớp xử lý request/xác thực.

`PasswordEncoder` được dùng khi một cơ chế **thật sự xác thực bằng mật khẩu**. Một API chỉ kiểm tra JWT hợp lệ hoặc chứng chỉ số có thể dùng thành phần xác thực khác và không gọi `PasswordEncoder` ở từng request.

## 3. Hợp đồng PasswordEncoder: ba phương thức

Giao diện quan trọng thuộc package `org.springframework.security.crypto.password.PasswordEncoder`:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là **chữ ký rút gọn để học API**, không phải bản sao đầy đủ của mã nguồn từng phiên bản. Hãy phân biệt các phương thức:

| API | Đầu vào | Kết quả | Thời điểm dùng |
| --- | --- | --- | --- |
| `encode(raw)` | Mật khẩu chưa băm | Chuỗi để lưu, thường gồm salt/metadata theo định dạng thuật toán | Đăng ký, đổi/reset mật khẩu, rehash hợp lệ |
| `matches(raw, stored)` | Mật khẩu vừa nhập và **chuỗi đã lưu** | `true` nếu khớp, `false` nếu không; cấu hình sai có thể gây exception | Xác thực mật khẩu hiện tại |
| `upgradeEncoding(stored)` | Chuỗi đã lưu | `true` nếu implementation cho rằng nên mã hóa lại để nâng bảo vệ | Đánh giá nhu cầu nâng cấp sau khi đã xác minh mật khẩu |

**Cực kỳ quan trọng: thứ tự tham số của `matches`.** Đầu tiên là **raw password do người dùng vừa nhập**, thứ hai là **encoded password từ database**:

~~~java
boolean ok = passwordEncoder.matches(submittedPassword, storedHash);
~~~

Sai lầm thường gặp:

~~~java
// SAI: không so sánh hai lần encode bằng equals.
boolean ok = passwordEncoder.encode(submittedPassword).equals(storedHash);

// SAI: đảo vị trí tham số.
boolean ok2 = passwordEncoder.matches(storedHash, submittedPassword);
~~~

Lý do đầu tiên sai: một `PasswordEncoder` hiện đại có thể tạo **salt ngẫu nhiên cho mỗi lần encode**. Cùng một raw password có thể tạo hai chuỗi hash khác nhau mà cả hai đều hợp lệ; `matches` biết cách đọc định dạng đã lưu, dùng đúng salt và tham số để kiểm tra.

### matches không giải mã mật khẩu

Mô hình ý tưởng:

~~~text
Người dùng nhập:       "MySecret@2026"
Database có:          "{bcrypt}$2a$..."
PasswordEncoder:
  - nhận định dạng/salt/tham số từ giá trị đã lưu
  - áp dụng thuật toán kiểm tra lên mật khẩu vừa nhập
  - xác định đúng/sai

Trả về: true hoặc false
~~~

`matches` không lấy ngược mật khẩu gốc từ hash. Do đó khi người dùng quên mật khẩu, ứng dụng **không gửi lại mật khẩu cũ**: cần cơ chế reset với bằng chứng và token phù hợp, rồi `encode` mật khẩu mới.

## 4. Salt và work factor giúp bảo vệ password hash ra sao?

Một thuật toán lưu mật khẩu mạnh thường có hai yếu tố:

**Salt:** giá trị ngẫu nhiên khác nhau cho mỗi lần băm, giúp hai người có cùng mật khẩu vẫn nhận hash khác nhau và làm các bảng tra cứu được tính trước khó tái sử dụng. Salt thường được lưu kèm output của hàm băm theo định dạng của thuật toán. **Salt không cần được giấu như mật khẩu**, nhưng cần ngẫu nhiên và duy nhất với xác suất cao.

**Work factor (chi phí tính toán):** tham số khiến encode và verification cố ý tốn thời gian hoặc bộ nhớ. Kẻ tấn công có database hash sẽ khó thử số lượng lớn ứng viên hơn. Cấu hình phải được chọn bằng đo lường trên máy chủ thực tế để cân bằng giữa an toàn, thời gian đăng nhập và nguy cơ bị lạm dụng gây quá tải.

Ví dụ với bcrypt, output thường bao gồm version, cost, salt và phần hash. Trong định dạng `$2a$10$...`, `10` biểu diễn cost factor. Spring Security `BCryptPasswordEncoder` hỗ trợ đặt strength/cost trong phạm vi được lớp này định nghĩa; tăng cost sẽ làm việc kiểm tra tốn tài nguyên hơn. Không cần tạo và lưu riêng salt cho `BCryptPasswordEncoder` thông thường: encoder đã làm việc đó.

Khi chọn thuật toán, cần xét khuyến nghị bảo mật hiện hành và điều kiện hệ thống:

| Thuật toán | Tính chất chính | Ghi chú triển khai |
| --- | --- | --- |
| Argon2id | Có tham số thời gian và bộ nhớ; phù hợp để chống tấn công trên phần cứng song song | Cần thư viện/triển khai tương thích, kiểm tra cấu hình và chi phí thực tế |
| scrypt | Dùng bộ nhớ và chi phí tính toán được cấu hình | Cần cân bằng bộ nhớ với số request đồng thời |
| bcrypt | Phổ biến, dùng salt và cost, nhiều ứng dụng cũ đang sử dụng | Lưu ý giới hạn đầu vào khoảng **72 byte** trong nhiều triển khai; cần chính sách mật khẩu/migration rõ ràng |
| PBKDF2 | Dựa trên nhiều vòng lặp của PRF như HMAC | Chọn biến thể và số vòng thích hợp, nhất là khi có yêu cầu tuân thủ FIPS |

Trong Spring Security, `DelegatingPasswordEncoder` cho phép dùng một thuật toán cho mật khẩu mới và vẫn nhận biết các định dạng hash cũ đã được xác minh. **Đừng đánh đồng việc Spring Security có hỗ trợ thuật toán với việc mọi cấu hình mặc định đều là khuyến nghị tốt nhất cho ứng dụng của bạn.** Cần đánh giá yêu cầu an toàn, phiên bản framework và đặc tính môi trường triển khai.

**Với bcrypt và Unicode:** mật khẩu của người dùng có thể chứa ký tự nhiều byte trong UTF-8. Một giới hạn dựa trên byte khác giới hạn dựa trên “số ký tự”. Nếu hệ thống có yêu cầu hỗ trợ mật khẩu dài, hãy kiểm tra cách thư viện và thuật toán xử lý dữ liệu đầu vào và chọn chính sách phù hợp ngay từ đầu.

## 5. Quy trình đăng ký: hash ngay trước khi lưu

Giả sử API đăng ký nhận:

~~~http
POST /api/register HTTP/1.1
Content-Type: application/json

{"username":"mai","password":"MySecret@2026"}
~~~

Mô hình xử lý:

1. Nhận dữ liệu bằng HTTPS và kiểm tra những ràng buộc hợp lý: độ dài, danh sách mật khẩu lộ lọt nếu có, quy tắc nghiệp vụ và giới hạn tài nguyên.
2. Không đưa raw password vào log, thông báo lỗi, sự kiện theo dõi, body phản hồi hoặc đối tượng `toString()`.
3. Gọi `passwordEncoder.encode(rawPassword)` tại tầng service đáng tin cậy.
4. Lưu **duy nhất chuỗi encoded/hash** trong cột dành cho mật khẩu, gắn với định danh người dùng.
5. Không tự trả hash về client. API phản hồi trạng thái tạo tài khoản hoặc quy trình xác minh tài khoản tùy chính sách.

Một cấu trúc dữ liệu cơ sở có thể là:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    username VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL
);
~~~

Đây là ví dụ schema để hiểu luồng, chưa bao gồm khóa sinh tự động, email, trạng thái tài khoản hoặc chi tiết khác. Dung lượng `password_hash` phải phù hợp với **thuật toán và định dạng thực tế**, kể cả tiền tố `{id}`; khi thay đổi thuật toán, kiểm tra lại giới hạn cột.

Đoạn logic minh họa trong một Spring service đã được tiêm `PasswordEncoder` và repository:

~~~java
// Đoạn minh họa bên trong service, chưa phải class chạy độc lập.
public void register(String username, String rawPassword) {
    validatePasswordPolicy(rawPassword);
    ensureUsernameAvailable(username);

    String encoded = passwordEncoder.encode(rawPassword);
    accountRepository.save(new Account(username, encoded));
}
~~~

`validatePasswordPolicy`, `ensureUsernameAvailable`, `accountRepository` và `Account` là các thành phần **do ứng dụng tự định nghĩa**. Điểm cốt lõi là không lưu raw password hoặc tự dùng SHA-256/Base64 ở nơi `PasswordEncoder` đang chịu trách nhiệm.

Nếu ứng dụng tạo tài khoản từ batch import, quản trị viên hoặc kịch bản khởi tạo dữ liệu, **mọi đường tạo password đều phải theo cùng chính sách**. Một vài dòng `password_hash` chứa văn bản gốc sẽ làm flow đăng nhập và bảo mật không nhất quán.

## 6. Quy trình đăng nhập: lấy hash và gọi matches

Với tài khoản `mai`, database lưu giá trị `{bcrypt}...` được tạo ở bước đăng ký. Khi Mai gửi `POST /login`:

~~~text
Browser gửi username + rawPassword
             |
             v
UsernamePasswordAuthenticationFilter hoặc thành phần tương đương
             |
             v
AuthenticationManager
             |
             v
DaoAuthenticationProvider
   |                         |
   +--> UserDetailsService --> UserDetails.getPassword()
   |                          phải chứa encoded/hash từ DB
   |
   +--> PasswordEncoder.matches(rawPassword, storedHash)
             |
       +-----+-----+
       |           |
     true         false
       |           |
Tạo kết quả     Báo lỗi xác thực
Authentication  và xử lý theo security flow
~~~

Điểm cần ghi nhớ khi tự viết `UserDetailsService`: `UserDetails#getPassword()` phải trả **hash đã lưu** phù hợp với `PasswordEncoder`. Không gọi `encode` mỗi lần truy vấn người dùng, vì điều đó có thể biến hash cũ thành hash của chính chuỗi hash cũ hoặc gây sai cách xác thực.

Mảnh mã chỉ minh họa dữ liệu được ánh xạ:

~~~java
// Bên trong UserDetailsService do ứng dụng triển khai.
Account account = accountRepository.findByUsername(username)
        .orElseThrow(() -> new UsernameNotFoundException("User not found"));

return User.withUsername(account.getUsername())
        .password(account.getPasswordHash()) // Hash đã có; KHÔNG encode lại.
        .authorities("ROLE_USER")
        .build();
~~~

Các tên `Account` và `accountRepository` trong đoạn này do ứng dụng định nghĩa; `User` là `org.springframework.security.core.userdetails.User`. Vai trò chỉ là ví dụ, không phải mọi tài khoản đều có `ROLE_USER`.

**Không trả về lỗi quá chi tiết cho phía client.** Thông báo “không tồn tại username” khác “mật khẩu sai” có thể làm lộ thông tin tài khoản. Nên thiết kế xử lý lỗi đăng nhập thống nhất, có hạn chế tốc độ yêu cầu và giám sát hành vi thử đoán.

### Khi matches trả false

`matches` kiểm tra mật khẩu với chuỗi đã lưu theo đúng cấu hình thuật toán. `false` nghĩa là không khớp, **không phải** gợi ý rằng server nên tạo lại hash và thay database. Chỉ sau khi xác minh thành công và có lý do nâng cấp rõ ràng, ứng dụng mới cân nhắc thay hash cũ.

Nếu stored hash bị hỏng, có tiền tố sai hoặc không có thuật toán phù hợp, một số implementation (đặc biệt `DelegatingPasswordEncoder`) có thể ném exception. Cần điều tra sự không nhất quán của dữ liệu/cấu hình; không “sửa lỗi đăng nhập” bằng `NoOpPasswordEncoder` trong production.

## 7. DelegatingPasswordEncoder: nhận biết thuật toán qua tiền tố

Spring Security hỗ trợ `DelegatingPasswordEncoder` để **đọc các định dạng cũ** đồng thời **tạo hash mới theo thuật toán đang chọn**. Có thể lấy một cấu hình thường dùng bằng:

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Các import là `org.springframework.security.crypto.password.PasswordEncoder` và `org.springframework.security.crypto.factory.PasswordEncoderFactories`.

Định dạng lưu trữ chung:

~~~text
{id}encodedPassword

Ví dụ theo Spring Security:
{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
{argon2}...
~~~

**`{id}` là nhãn thuật toán để chọn delegate**, còn phần sau là output theo quy tắc của thuật toán tương ứng. `{bcrypt}` không phải salt, không phải một role và không được hiểu là “mật khẩu đã mã hóa có thể giải mã”.

Với `PasswordEncoderFactories.createDelegatingPasswordEncoder()` trong nhánh Spring Security 6.5, encoder mặc định dùng **bcrypt để encode password mới**, nên output bắt đầu bằng `{bcrypt}`. Khi kiểm tra, `DelegatingPasswordEncoder` đọc `{id}` từ hash cũ rồi chọn implementation thích hợp để so sánh.

Ví dụ diễn giải:

| Chuỗi trong database | Encoder có thể được chọn | Điều kiện |
| --- | --- | --- |
| `{bcrypt}$2a$...` | `BCryptPasswordEncoder` | Mapping có id `bcrypt` |
| `{pbkdf2}...` | `Pbkdf2PasswordEncoder` | Mapping có id `pbkdf2` tương ứng |
| `{noop}demo-only` | `NoOpPasswordEncoder` | **Chỉ dùng khi đọc dữ liệu mẫu/cũ**, tuyệt đối không tạo mới kiểu này ở production |
| `$2a$10$...` không có `{bcrypt}` | Không biết id mặc định | Có thể ném `IllegalArgumentException` do `id="null"` |

Trường hợp hash bcrypt cũ không có `{bcrypt}` là một lỗi migration thường gặp. Nếu đã xác minh chắc chắn mọi bản ghi trong nhóm dữ liệu ấy thật sự là hash bcrypt, có thể lập kế hoạch **thêm đúng tiền tố** theo dữ liệu đã kiểm chứng hoặc cấu hình khả năng đọc tương ứng trong giai đoạn chuyển đổi. Không tự thêm `{bcrypt}` cho chuỗi chưa biết nguồn gốc, và không đặt fallback không kiểm soát cho mọi kiểu hash lạ.

Cần nhớ: `PasswordEncoderFactories` có hỗ trợ một số định dạng **di sản** nhằm hỗ trợ chuyển đổi. Việc một encoder có thể `matches` với `{noop}` không biến lưu mật khẩu văn bản gốc thành an toàn. Sau xác thực hợp lệ, phải chuyển dần sang hàm băm mạnh.

## 8. Ví dụ Java 17+ chạy được: encode, matches và nhận diện hash cũ

Ví dụ sau dùng chính các lớp Spring Security. Để có kết quả đầu ra ổn định, chương trình **không in chuỗi hash ngẫu nhiên**; nó chỉ in tiền tố, kết quả `matches` và việc nhận diện dữ liệu cần nâng cấp.

Tạo tệp `build.gradle` trong thư mục thực hành Gradle độc lập:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'PasswordEncoderDemo'
}
~~~

Dependency `spring-security-core` kéo theo `spring-security-crypto`, nơi có `PasswordEncoder`. Phiên bản 6.5.11 dùng để cố định ví dụ độc lập. Trong dự án Spring Boot thực tế, nên dùng `spring-boot-starter-security` và để Spring Boot quản lý các phiên bản tương thích.

Tạo tệp `src/main/java/PasswordEncoderDemo.java`:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordEncoderDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String submitted = "Demo-password@2026";
        String stored = encoder.encode(submitted);

        // Không xuất rawPassword hoặc stored hash ra log thật.
        System.out.println("bcrypt prefix=" + stored.startsWith("{bcrypt}"));
        System.out.println("raw stored=" + submitted.equals(stored));
        System.out.println("correct password=" + encoder.matches(submitted, stored));
        System.out.println("wrong password="
                + encoder.matches("not-the-password", stored));

        // Dữ liệu di sản CHỈ để minh họa khả năng migration.
        // Không lưu mật khẩu mới dưới dạng {noop}.
        String legacy = "{noop}migration-only-demo";
        System.out.println("legacy matches="
                + encoder.matches("migration-only-demo", legacy));
        System.out.println("legacy needs upgrade="
                + encoder.upgradeEncoding(legacy));
    }
}
~~~

Chạy với JDK 17+ và Gradle đã cài, từ thư mục chứa `build.gradle`:

~~~bash
gradle run --quiet
~~~

Đầu ra các lệnh `println`:

~~~text
bcrypt prefix=true
raw stored=false
correct password=true
wrong password=false
legacy matches=true
legacy needs upgrade=true
~~~

Giải thích:

1. `createDelegatingPasswordEncoder()` chọn bcrypt để tạo hash mới, với nhãn `{bcrypt}`.
2. Chuỗi lưu khác mật khẩu gốc, nhưng `matches(submitted, stored)` vẫn đúng nhờ thuật toán/salt đi kèm.
3. Khi đưa sai mật khẩu, `matches` trả `false`.
4. Ví dụ di sản `{noop}...` vẫn có thể được đọc bởi mapping tương ứng, và `upgradeEncoding` báo nên nâng cấp vì id cũ không phải id tạo hash mới.

Đoạn minh họa **không có đăng ký tài khoản, không xác thực người dùng thật, không lưu database và không cấp quyền**. Nó cô lập ba thao tác cốt lõi của `PasswordEncoder` để học. Việc chấp nhận `{noop}` ở đây chỉ cho thấy khả năng đọc dữ liệu cũ, tuyệt đối không phải khuyến nghị dùng `{noop}` trong production.

Mỗi lần `encode` với salt ngẫu nhiên có thể tạo output khác nhau. Vì vậy **không sao chép một hash mẫu cụ thể rồi kỳ vọng chương trình tái tạo đúng từng ký tự**.

## 9. Cấu hình PasswordEncoder trong ứng dụng Spring Boot

Trong dự án Spring Boot có `spring-boot-starter-security`, cách khai báo một bean có thể là:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

Bean dùng chung giúp logic tạo hash và logic xác thực dùng cùng hợp đồng định dạng. Không nên có ba nơi tự tạo ba kiểu encoder không tương thích: ví dụ API đăng ký băm với `BCryptPasswordEncoder` thuần và cất chuỗi không tiền tố, còn provider đăng nhập dùng `DelegatingPasswordEncoder` cần `{id}`. Hai cách đó phải được thiết kế/ánh xạ nhất quán.

Với Spring Security servlet 6.5, `DaoAuthenticationProvider` có thể dùng `UserDetailsService` và `PasswordEncoder` được cấu hình cho quá trình xác thực. Ví dụ mảnh cấu hình **không chạy độc lập** bên trong một `@Configuration` khi bạn muốn tự lắp `AuthenticationManager`:

~~~java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);

    return new ProviderManager(provider);
}
~~~

Các kiểu `DaoAuthenticationProvider`, `ProviderManager`, `AuthenticationManager`, `UserDetailsService` thuộc các package tương ứng của Spring Security. Mã còn cần import, bean/repository và cấu hình bảo mật theo ứng dụng. Nhiều dự án Spring Boot để Spring Security tự cấu hình provider; không phải lúc nào cũng cần khai báo `AuthenticationManager` thủ công.

### Tại sao BCryptPasswordEncoder và DelegatingPasswordEncoder có thể gây nhầm?

Hai đoạn này không tạo cùng một **chuỗi lưu trữ**:

~~~java
String a = new BCryptPasswordEncoder().encode("secret");
String b = PasswordEncoderFactories.createDelegatingPasswordEncoder()
        .encode("secret");
~~~

`a` thường bắt đầu bằng `$2a$`, `$2b$` hoặc `$2y$` theo phiên bản thuật toán; `b` có **tiền tố `{bcrypt}`** ở phía trước output bcrypt. Cả hai có thể dùng bcrypt bên trong nhưng cần dùng encoder tương thích khi kiểm tra.

Không suy ra `a.equals(b)` vì có salt ngẫu nhiên; đừng dùng chuỗi hash như một khóa tìm kiếm theo mật khẩu.

## 10. Đổi mật khẩu, reset mật khẩu và nâng cấp hash

### Đổi mật khẩu khi người dùng biết mật khẩu hiện tại

Một luồng đổi mật khẩu an toàn thường gồm:

1. Đảm bảo request đến từ tài khoản đã được xác thực và trải qua kiểm tra CSRF nếu dùng cookie tự động gửi.
2. Xác minh mật khẩu hiện tại bằng `matches(oldRaw, storedHash)` hoặc thực hiện một bước xác minh danh tính tương đương theo chính sách.
3. Kiểm tra mật khẩu mới theo chính sách (độ dài, mật khẩu bị lộ, không cho giống mật khẩu cũ nếu chính sách yêu cầu).
4. `encode(newRaw)` rồi lưu hash mới trong giao dịch phù hợp.
5. Xử lý việc hủy phiên/token còn hiệu lực trên các thiết bị khác nếu chính sách yêu cầu, gửi thông báo an toàn và ghi sự kiện audit **không chứa mật khẩu**.

Quên mật khẩu là luồng riêng: xác minh người yêu cầu bằng token reset **ngẫu nhiên, ngắn hạn và một lần**, rồi cho đặt mật khẩu mới; không có thao tác “giải mã hash để gửi lại mật khẩu cũ”.

### upgradeEncoding hỗ trợ di chuyển mà không cần biết mật khẩu gốc trước đó

Giả sử database còn hash tạo từ bộ tham số cũ. Khi người dùng đăng nhập thành công, máy chủ đang có raw password *trong thời gian ngắn* từ yêu cầu hợp lệ. Đó là thời điểm thích hợp để:

~~~java
// Pseudocode trong luồng đã xác thực thành công.
if (passwordEncoder.matches(rawPassword, storedHash)
        && passwordEncoder.upgradeEncoding(storedHash)) {

    String upgradedHash = passwordEncoder.encode(rawPassword);
    accountRepository.updatePasswordHashIfUnchanged(
            userId, storedHash, upgradedHash);
}
~~~

Đây là **mảnh mã minh họa**: ứng dụng phải định nghĩa `accountRepository`, bảo vệ giao dịch và cập nhật có điều kiện để không ghi đè mật khẩu vừa được thay đổi ở request khác. Đừng quên raw password phải được xử lý nhạy cảm và không giữ lâu hơn cần thiết.

`upgradeEncoding` chỉ **báo nhu cầu**, không có nghĩa framework luôn tự thay database khi được gọi. Với `DaoAuthenticationProvider`, Spring Security có cơ chế tích hợp cập nhật hash khi cung cấp `UserDetailsPasswordService` phù hợp; cần cấu hình và kiểm thử đường này. Nếu bạn viết cơ chế xác thực riêng, tự chịu trách nhiệm cho việc nâng cấp an toàn.

### Kế hoạch migration cho dữ liệu cũ

- **Phân loại và xác minh** định dạng hash hiện có: bcrypt không prefix, legacy PBKDF2, định dạng nội bộ hoặc dữ liệu không được bảo vệ.
- **Cấu hình đối chiếu tương thích** trong giai đoạn chuyển đổi, giới hạn rõ các kiểu được phép đọc; không mở fallback tùy ý.
- **Mật khẩu mới** luôn tạo bằng chính sách hiện hành. **Mật khẩu cũ** nâng cấp khi người dùng chứng minh đúng mật khẩu, hoặc đặt lại khi không có cách kiểm tra an toàn.
- **Ghi nhận tiến độ migration bằng metadata không nhạy cảm**, chẳng hạn phiên bản thuật toán, không ghi raw password hay hash vào log.
- **Theo dõi tỷ lệ lỗi đăng nhập** trong quá trình triển khai; không sửa lỗi `There is no PasswordEncoder mapped for the id "null"` bằng cách ép mọi mật khẩu về dạng `noop`.

Khi hash cũ được tạo bằng hàm một chiều, bạn không thể lấy lại raw password hàng loạt để mã hóa lại ngoại tuyến. Cách thông dụng là nâng cấp vào lần xác thực thành công hoặc qua luồng reset có xác minh.

## 11. Các yêu cầu bảo mật bên cạnh PasswordEncoder

Dùng thuật toán đúng **không đủ** để bảo vệ toàn bộ hệ thống đăng nhập. Một số rủi ro tồn tại ở những tầng khác:

| Rủi ro | Cách xử lý phù hợp |
| --- | --- |
| Thử đoán mật khẩu online với số lượng lớn | Rate limit, giám sát, chính sách khóa/chậm phù hợp và MFA ở nơi cần |
| Database lộ hash | Dùng password hashing thích ứng với salt, tham số đủ mạnh; giới hạn quyền đọc, mã hóa backup và giám sát |
| Mật khẩu rò qua log/trace | Không log request body của endpoint login/register; lọc dữ liệu nhạy cảm |
| Dùng HTTPS sai | Bật TLS đúng cấu hình, giảm nguy cơ nghe lén mật khẩu khi truyền |
| Hash bị lộ qua API | Không trả trường `passwordHash` trong DTO/JSON, không đưa vào exception hoặc audit |
| Dữ liệu mật khẩu cũ yếu | Migration/re-hash khi đã xác minh, reset an toàn nếu cần |
| Ứng dụng xử lý mật khẩu quá tốn CPU/RAM | Benchmark chi phí hash và giới hạn số lần xác thực đồng thời; phát hiện lạm dụng |
| Dùng tài khoản đã xác thực để truy cập dữ liệu không thuộc quyền | Quy tắc authorization riêng cho URL, method, đối tượng và phạm vi tenant |

Một kỹ thuật nâng cao là **pepper**, tức bí mật dùng chung được quản lý **tách khỏi database** để tăng lớp bảo vệ khi database hash bị lộ. Pepper không phải salt. Việc thêm pepper cần thiết kế được kiểm chứng, kho bí mật an toàn và kế hoạch luân chuyển; **không tự ghép một chuỗi pepper cố định vào mật khẩu** rồi cho rằng đã thay thế thuật toán băm thích ứng.

Nếu phải dùng chuẩn tuân thủ cụ thể hoặc có yêu cầu hiệu năng lớn, hãy đối chiếu hướng dẫn mật khẩu và kiểm thử benchmark theo môi trường trước khi chọn Argon2id/scrypt/bcrypt/PBKDF2 cùng tham số.

## 12. Những sai lầm phổ biến

1. **Lưu raw password để sau này so sánh.** Người có quyền đọc database có thể xem mật khẩu; không được.
2. **Cho rằng Base64 là mã hóa mật khẩu.** Base64 đảo ngược được; không phải password hashing.
3. **Dùng SHA-256 trực tiếp để lưu mật khẩu người dùng.** Đây là hàm băm quá nhanh cho mục đích chống đoán mật khẩu ngoại tuyến.
4. **So sánh `encode(raw).equals(stored)`.** Với salt ngẫu nhiên, hai lần encode có thể khác nhau; phải dùng `matches`.
5. **Đảo thứ tự `matches`.** Đúng là `matches(rawPassword, storedEncodedPassword)`.
6. **Gọi `encode` trên hash lấy từ DB mỗi lần load user.** Dữ liệu lưu không nên được băm thêm; `UserDetails` phải mang hash gốc từ DB.
7. **Trộn `BCryptPasswordEncoder` thuần với `DelegatingPasswordEncoder` mà không quan tâm `{id}`.** Hai cách lưu chuỗi không luôn có cùng định dạng; cần kế hoạch tương thích.
8. **Dùng `NoOpPasswordEncoder` cho production.** Lưu mật khẩu không được bảo vệ là sai; mapping legacy chỉ có ý nghĩa chuyển đổi.
9. **Hiểu `upgradeEncoding=true` là database tự cập nhật.** Phải có luồng/cấu hình cập nhật an toàn.
10. **Nâng strength quá cao mà không benchmark.** Có thể tạo độ trễ lớn hoặc rủi ro cạn CPU; chọn tham số trên hệ thống thật.
11. **Giữ hash ở frontend để “xác thực nhanh”.** Hash vẫn là dữ liệu nhạy cảm, và client không nên thay server quyết định xác thực.
12. **Đăng nhập đúng đồng nghĩa được truy cập mọi dữ liệu.** `PasswordEncoder` chỉ kiểm tra mật khẩu; authorization xử lý quyền.
13. **Đoạn code hardcode mật khẩu rồi đem dùng ở production.** Mã mẫu để dạy không phải cách nhập/giữ bí mật của ứng dụng thật.
14. **Tự viết hàm salt + hash thay vì dùng thư viện được đánh giá.** Dễ sai định dạng, xử lý byte, thời gian so sánh và kế hoạch nâng cấp.

## 13. Checklist kiểm thử theo vòng đời mật khẩu

| Tình huống cần thử | Kỳ vọng |
| --- | --- |
| Đăng ký thành công | Database chỉ giữ hash/định dạng hợp lệ, không giữ raw password |
| Hai tài khoản cùng một mật khẩu | Có thể nhận hash khác nhau do salt |
| Đăng nhập bằng mật khẩu đúng | `matches` true, flow xác thực thành công khi trạng thái tài khoản hợp lệ |
| Đăng nhập bằng mật khẩu sai | Không được tạo Authentication đáng tin cậy |
| Password rỗng/null hoặc vượt giới hạn cho phép | Bị xử lý theo chính sách input và API, không làm lộ thông tin |
| Hash bị hỏng hoặc thiếu `{id}` khi dùng Delegating | Xử lý lỗi có kiểm soát, có kế hoạch migration |
| Đổi mật khẩu thành công | Hash mới thay thế hash cũ; mật khẩu cũ không còn đăng nhập được |
| Reset mật khẩu | Token reset đúng hạn, một lần; hash mới tạo bằng policy hiện hành |
| Hash cũ được đánh dấu cần nâng cấp | Nâng cấp sau khi đã xác minh và cập nhật có điều kiện |
| Truy cập tài khoản người khác dù đăng nhập đúng | Vẫn bị từ chối nếu thiếu quyền theo tài nguyên |
| Truy vấn log/request trace ở môi trường thử nghiệm | Không xuất hiện raw password, token reset hoặc hash nhạy cảm |

Lưu ý về test: vì hash có salt ngẫu nhiên, một bài test không nên assert một chuỗi bcrypt cố định mới được `encode`. Hãy assert rằng chuỗi có định dạng mong muốn, `matches(raw, encoded)` thành công và `matches(wrong, encoded)` thất bại.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Hai người dùng nhập cùng mật khẩu. Tại sao hash lưu trong database có thể khác nhau?

*Trả lời:* Vì hàm băm mật khẩu hiện đại dùng salt ngẫu nhiên cho từng lần encode; bộ kiểm tra biết cách dùng salt từ chuỗi đã lưu để xác minh.

**Câu 2.** Khi login, chương trình nên gọi `passwordEncoder.encode(raw).equals(storedHash)` hay `passwordEncoder.matches(raw, storedHash)`?

*Trả lời:* Gọi `matches(raw, storedHash)`. Đây là API có đúng hợp đồng kiểm tra với hash/salt lưu trữ.

**Câu 3.** `DelegatingPasswordEncoder` thấy `{bcrypt}$2a$...` thì `{bcrypt}` có ý nghĩa gì?

*Trả lời:* Đó là id chọn delegate thích hợp; phần sau được phân tích theo định dạng bcrypt. Đây không phải một mật khẩu có thể giải mã.

**Câu 4.** Database chứa chuỗi bcrypt cũ nhưng thiếu `{bcrypt}`. Vì sao một bộ `DelegatingPasswordEncoder` mặc định có thể báo `id="null"`?

*Trả lời:* Nó cần tiền tố `{id}` để chọn encoder. Migration phải dựa trên định dạng thực đã xác minh; không tự mở fallback với mọi chuỗi không rõ nguồn gốc.

**Câu 5.** Khi `upgradeEncoding(hash)` trả true, làm gì để nâng cấp?

*Trả lời:* Chỉ sau khi mật khẩu người dùng được xác minh hợp lệ, dùng raw password trong thời gian ngắn để tạo hash mới và cập nhật an toàn; có thể tích hợp `UserDetailsPasswordService` với `DaoAuthenticationProvider`.

**Câu 6.** Hash một chiều thì vì sao database bị lộ vẫn nguy hiểm?

*Trả lời:* Kẻ tấn công có thể thử các mật khẩu dự đoán và so sánh với hash bị lộ. Salt và hàm băm thích ứng khiến công việc này tốn kém hơn, nhưng không loại bỏ mọi rủi ro, nhất là khi mật khẩu yếu.

**Câu 7.** `PasswordEncoder` kiểm tra thành công. Có nghĩa người dùng được sửa mọi tài liệu?

*Trả lời:* Không. Đó là một bước trong xác thực mật khẩu; hệ thống còn phải kiểm tra trạng thái tài khoản, authorities và quyền truy cập trên từng tài nguyên.

### Tài liệu tham khảo

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — Password Storage and Crypto Module](https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
