# DelegatingPasswordEncoder và tiền tố thuật toán trong giá trị đã băm

## Mục tiêu học tập

Một hệ thống quản lý tài khoản thường phải đối mặt với hai yêu cầu tưởng như mâu thuẫn: **mật khẩu mới phải được lưu bằng cơ chế băm an toàn đang được khuyến nghị**, nhưng **mật khẩu đã lưu từ những phiên bản trước vẫn phải xác minh được trong giai đoạn chuyển đổi**. Spring Security giải quyết phần chọn thuật toán qua `DelegatingPasswordEncoder` và định dạng **`{id}encodedPassword`**.

Thay vì đoán thuật toán bằng chiều dài chuỗi hash, hệ thống ghi một **mã định danh thuật toán** ở đầu giá trị đã lưu, ví dụ `{bcrypt}`. Khi nhận mật khẩu người dùng cung cấp, `DelegatingPasswordEncoder` đọc prefix để chọn `PasswordEncoder` phù hợp. Khi tạo mật khẩu mới, một cấu hình khác gọi là **`idForEncode`** chọn bộ mã hóa hiện hành. Nhờ đó việc **đọc hash cũ** có thể khác với việc **tạo hash mới**, nhưng cả hai vẫn thực hiện qua cùng interface.

Bài này sử dụng **Java 17, Spring Boot 3.5.0, Spring Security 6.5.x, Spring MVC/Servlet**. Ví dụ chính có thể chạy bằng Maven, sử dụng `PasswordEncoderFactories.createDelegatingPasswordEncoder()`; phần nâng cao minh họa chuyển một tài khoản có hash cũ sang bcrypt khi đăng nhập thành công. Các ví dụ `{noop}` chỉ dành cho việc phân tích dữ liệu legacy/test, **không phải cách lưu mật khẩu trong hệ thống mới**.

Sau khi hoàn thành, bạn sẽ:

1. Phân biệt **mật khẩu gốc (raw)**, **hash lưu trữ**, **salt/work factor** và **prefix `{id}`** của Spring Security.
2. Giải thích `PasswordEncoder.encode`, `matches`, `upgradeEncoding` và vai trò của `DelegatingPasswordEncoder`.
3. Hiểu cấu hình `idForEncode`, `idToPasswordEncoder` và hành vi chọn algorithm khi encode/match.
4. Đọc một chuỗi `{bcrypt}$2a$10$...` mà không nhầm prefix với salt hoặc chứng cứ password đã đúng.
5. Biết vì sao hash thiếu tiền tố hoặc `{unknown}` mặc định gây lỗi khi `matches`, và cách xử lý migration có kiểm soát.
6. Nhận biết mapping phổ biến `bcrypt`, `pbkdf2@SpringSecurity_v5_8`, `scrypt@SpringSecurity_v5_8`, `argon2@SpringSecurity_v5_8` và legacy `noop`/digest.
7. Tạo PasswordEncoder bean nhất quán với `UserDetailsService` và `DaoAuthenticationProvider` trong ứng dụng Spring Boot.
8. Thiết kế test cho đúng/sai mật khẩu, prefix, unknown id, legacy unprefixed BCrypt, upgrade-on-login và HTTP 200/401/403.
9. Tránh các lỗi lưu plaintext, hash hai lần, so hai chuỗi bcrypt trực tiếp, dùng fallback `noop` toàn cục, cắt ngắn cột DB và lộ hash/credentials.

## 1. Vì sao phải có DelegatingPasswordEncoder?

### 1.1. Không phải mọi account được tạo cùng thời điểm

Hãy hình dung một ứng dụng vận hành nhiều năm:

- Nhóm A từng được lưu bằng một format cũ.
- Nhóm B đã chuyển sang bcrypt.
- Hệ thống muốn nâng mức cost của bcrypt khi khả năng phần cứng thay đổi.
- Ứng dụng sẽ cần chuyển sang thuật toán khác trong tương lai, tùy khuyến nghị và điều kiện hạ tầng.

Nếu `PasswordEncoder` chỉ biết đúng một thuật toán, các bản ghi cũ có thể không xác minh được khi bạn thay implementation. Nếu cố viết nhiều phép thử theo độ dài/regex hash, sẽ dễ tạo fallback mơ hồ hoặc chấp nhận nhầm dữ liệu không đáng tin.

**`DelegatingPasswordEncoder` là bộ điều phối**, không tự thay thế công thức bcrypt/Argon2/PBKDF2. Nó nhận danh sách encoder theo tên `id` và định tuyến:

```text
User nhập raw password
         |
         v
DelegatingPasswordEncoder.matches(raw, stored)
         |
         +--> stored bắt đầu bằng "{bcrypt}"?
         |          -> BCryptPasswordEncoder.matches(raw, hashBody)
         |
         +--> stored bắt đầu bằng "{pbkdf2@SpringSecurity_v5_8}"?
         |          -> PBKDF2 encoder theo mapping được đăng ký
         |
         +--> stored bắt đầu bằng "{noop}"?
         |          -> Legacy no-op encoder (KHÔNG AN TOÀN để lưu mới)
         |
         +--> Không có id / id không được map?
                    -> Mặc định IllegalArgumentException
```

Khi tạo mới:

```text
rawPassword
    |
    v
DelegatingPasswordEncoder.encode(rawPassword)
    |
    v
idForEncode = "bcrypt"
    |
    v
BCryptPasswordEncoder.encode(rawPassword)
    |
    v
"{bcrypt}" + bcryptHash
    |
    v
Lưu nguyên chuỗi vào database
```

**Cơ chế xác thực vẫn phải kiểm chứng raw password**; chỉ có prefix không chứng minh user đăng nhập thành công. `matches` trả true/false cho dữ liệu hợp lệ, hoặc có thể ném exception nếu format/id không được hỗ trợ. Đừng xem prefix là chữ ký số, secret, hay thông tin chống chỉnh sửa record.

### 1.2. PasswordEncoder khác AuthenticationManager

| Thành phần | Vai trò | Điều không thực hiện |
| --- | --- | --- |
| `PasswordEncoder` | Hash raw password, đối chiếu raw với hash lưu, báo nhu cầu rehash. | Không biết người dùng được vào endpoint nào. |
| `DelegatingPasswordEncoder` | Chọn encoder cụ thể theo `{id}` và `idForEncode`. | Không tự quản lý user store hoặc HTTP session. |
| `UserDetailsService` | Tải `UserDetails` gồm username, encoded password, trạng thái tài khoản, authorities. | Không tự xác thực một HTTP request. |
| `DaoAuthenticationProvider` | Phối hợp tải user và `PasswordEncoder.matches` để xác thực password. | Không tự mở tất cả URL cho user. |
| `AuthenticationManager` / `ProviderManager` | Điều phối providers và trả `Authentication` đã xác minh hoặc exception. | Không thay authorization theo object/tenant. |
| `SecurityFilterChain` | Áp cơ chế authentication/authorization trên HTTP. | Không mã hóa password thay database. |
| `UserDetailsPasswordService` | Cho phép cập nhật encoded password của user trong một số flow như rehash sau login. | Không phải API cho client tự đổi password không xác minh. |

Điểm cần nhớ: **encode khi lưu**, **matches khi xác thực**, **authorization sau authentication**. Không gửi hash về client và yêu cầu client dùng hash như password; khi đó hash có thể trở thành một secret có thể phát lại (pass-the-hash trong thiết kế sai).

## 2. Định dạng {id}encodedPassword

Định dạng được Spring Security công bố:

```text
{id}encodedPassword
```

Trong đó:

- Ký tự `{` mở đầu id và `}` đóng id, theo định dạng mặc định.
- `id` là tên **mapping** trong `DelegatingPasswordEncoder`, ví dụ `bcrypt`.
- `encodedPassword` là kết quả do encoder tương ứng tạo ra, có thể chứa salt, cost, version hoặc tham số nội bộ của thuật toán.
- Toàn bộ chuỗi là **giá trị mật khẩu lưu trong user store**, không phải mật khẩu gốc.

Ví dụ một giá trị bcrypt minh họa:

```text
{bcrypt}$2a$10$dXJ3SW6G7P50lGmMkkmwe.20cQQubK3.HZWzG3YB1tlRy.fqvM/BG
|------| |--| |-| |----------------------------------------------------|
   id   ver cost        salt + hash encoded theo định dạng bcrypt
```

**Hai lớp metadata độc lập:**

1. `{bcrypt}` là prefix của **Spring Security DelegatingPasswordEncoder**, cho biết encoder mapping cần dùng.
2. `$2a$10$...` là định dạng **nội bộ bcrypt**. `$2a` là marker phiên bản, `10` là cost/work factor, phần còn lại lưu thông tin salt và password hash được mã hóa theo bcrypt.

Không đọc `10` là “10 vòng SHA-256” hay “salt 10 ký tự”; nó là work factor theo bcrypt. Không tự cắt chuỗi bằng độ dài hoặc tự base64-decode hash để kiểm tra. Hãy dùng encoder của thư viện đã được kiểm chứng.

### 2.1. Một số prefix tiêu biểu

| Prefix/id | Ý nghĩa theo mapping Spring Security | Lưu ý |
| --- | --- | --- |
| `{bcrypt}` | `BCryptPasswordEncoder` | Mặc định dùng để encode mới của factory trong Spring Security 6.5. |
| `{pbkdf2}` | PBKDF2 mapping cũ trong factory | Tham số cụ thể khác id phiên bản mới; không tự đổi id. |
| `{pbkdf2@SpringSecurity_v5_8}` | PBKDF2 với cấu hình tương ứng thế hệ 5.8 | Version trong id giúp tránh đọc sai cost/salt/hash format. |
| `{scrypt}` | scrypt mapping cũ | Không đồng nhất với mapping được version hóa. |
| `{scrypt@SpringSecurity_v5_8}` | scrypt theo bộ tham số tương ứng | Có thể cần đánh giá memory/cost trên hạ tầng thực. |
| `{argon2}` | Argon2 mapping đời cũ | Hỗ trợ thư viện/phụ thuộc và chi phí cần đối chiếu theo version. |
| `{argon2@SpringSecurity_v5_8}` | Argon2 theo mapping thế hệ 5.8 | Một số implementation Argon2 của Spring Security dựa vào Bouncy Castle. |
| `{noop}` | NoOpPasswordEncoder | Plaintext, không an toàn; chỉ để học/migration có kiểm soát. |
| `{MD5}`, `{SHA-1}`, `{sha256}` | Một số mappings legacy/digest | Không phù hợp lưu password mới, dễ bị tấn công offline. |

Danh sách mapping có thể thay đổi giữa các release. **Không đoán rằng mọi thuật toán trong bảng được bật trong một encoder tự tạo từ Map**. Chúng được minh họa theo factory mappings của dòng Spring Security 6.5; nếu bạn tự tạo `DelegatingPasswordEncoder`, chỉ các id thực sự thêm vào map mới được nhận.

### 2.2. Prefix không phải tham số tùy ý do user nhập

`id` được đọc từ **giá trị hash đã lưu**, không từ một trường “algorithm” do client login tự gửi rồi tự quyết định quyền. Với cùng một input, việc chọn encoder phải theo cấu hình server và dữ liệu đã lưu được kiểm soát, không theo lời khai của browser.

Dù DB record có thể bị sửa trong một sự cố, mã định danh không tự tải class từ Internet hay chạy mã tuỳ ý; nó là key tra cứu trong map encoder đã đăng ký. Tuy nhiên, một hệ thống cho phép ghi đè password hash/prefix tùy ý vẫn có lỗ hổng nghiêm trọng: kẻ tấn công có thể thay hash bằng giá trị nó biết và đăng nhập.

### 2.3. Bao nhiêu ký tự nên dành cho cột password?

Không giả định hash luôn dài 60 ký tự như bcrypt raw. Có thêm `{bcrypt}` và nhiều định dạng PBKDF2/scrypt/Argon2 dài hơn tùy cost, salt, cấu hình. Cột password quá ngắn dễ **cắt mất prefix hoặc phần hash**, gây lỗi login hàng loạt hoặc giảm khả năng di trú thuật toán.

Trong thiết kế database, thường dùng một cột text/`VARCHAR` đủ rộng theo các encoder được hỗ trợ, cộng validation không cắt ngắn, migration schema và test dữ liệu qua driver. Không hứa một độ dài cố định phù hợp mọi thuật toán/mọi tương lai.

## 3. Ba phương thức của PasswordEncoder

Hợp đồng cơ bản:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Đây là **hình dạng đơn giản** để học, không phải file cần tự tạo. Class/interface thực do `org.springframework.security.crypto.password` cung cấp.

### 3.1. encode(rawPassword): tạo giá trị lưu

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String stored = encoder.encode("spring-is-fun");
```

Với factory 6.5.x, `stored` bắt đầu bằng `{bcrypt}`. Vì bcrypt sinh salt ngẫu nhiên, **hai lần encode cùng một raw password không có chuỗi kết quả giống nhau** một cách thông thường:

```java
String first = encoder.encode("same-password");
String second = encoder.encode("same-password");

// Không dùng equals(first, second) để khẳng định password giống nhau.
```

Điều đó đúng thiết kế; các thuật toán password hashing hiện đại sử dụng salt và cost để chống tấn công so sánh hash đơn giản, precomputed tables và thử mật khẩu hàng loạt rẻ tiền.

### 3.2. matches(raw, encoded): đối chiếu, không giải mã

```java
String stored = encoder.encode("spring-is-fun");

boolean correct =
    encoder.matches("spring-is-fun", stored); // true

boolean incorrect =
    encoder.matches("wrong-password", stored); // false
```

Không có thao tác “giải mã bcrypt để lấy lại password”. `matches` tính/đối chiếu theo cơ chế hash tương ứng với salt/parameters đã lưu. Trong ứng dụng đăng nhập, raw password do người dùng vừa cung cấp và stored password do `UserDetailsService` tải từ server-side store.

**Tránh:**

```java
// SAI: mỗi lần encode bcrypt thường có salt mới.
boolean wrong =
    encoder.encode(submitted).equals(stored);
```

Đây là fragment anti-pattern; `submitted` và `stored` phải được khai báo trước nếu copy vào file Java. Cách đúng là `encoder.matches(submitted, stored)`.

### 3.3. upgradeEncoding(encoded): có nên băm lại không?

`PasswordEncoder.upgradeEncoding` là tín hiệu cho biết một giá trị đã lưu có nên được mã hóa lại theo cơ chế/cost mới hay không. Mặc định của interface là `false`; một số encoder, gồm `DelegatingPasswordEncoder`, có logic riêng.

Ví dụ logic dự kiến với factory 6.5:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String current = encoder.encode("secret-pass");

boolean currentNeedsUpgrade =
    encoder.upgradeEncoding(current); // thông thường false

boolean legacyNeedsUpgrade =
    encoder.upgradeEncoding("{noop}secret-pass"); // true
```

`upgradeEncoding` **không tự thay đổi database**. Nó chỉ trả boolean. Để thực hiện rehash thật, bạn cần **raw password đang có trong phiên xác thực thành công** và một cơ chế cập nhật password hash như `UserDetailsPasswordService`, được kết nối với `DaoAuthenticationProvider` hoặc service tin cậy.

Nếu bcrypt cost của hash thấp hơn cấu hình hiện tại, implementation có thể báo cần upgrade dù prefix vẫn là `{bcrypt}`. Vì vậy chỉ so prefix không đủ xác định mật khẩu đã đạt strength hiện hành.

## 4. DelegatingPasswordEncoder chọn thuật toán như thế nào?

### 4.1. Hai tham số không được nhầm

`DelegatingPasswordEncoder` có khái niệm:

- **`idForEncode`:** id dùng cho **mọi lệnh encode mới** trên instance đó.
- **`idToPasswordEncoder`:** map `id → PasswordEncoder` dùng để **nhận biết và đối chiếu các giá trị đã lưu**.

Định nghĩa với API constructor cơ bản:

```java
DelegatingPasswordEncoder encoder =
    new DelegatingPasswordEncoder(
        "bcrypt",
        Map.of(
            "bcrypt", new BCryptPasswordEncoder(12),
            "pbkdf2@SpringSecurity_v5_8",
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8()
        )
    );
```

Đây là **fragment có chủ ý tùy chỉnh**, cần imports `java.util.Map`, `DelegatingPasswordEncoder`, `BCryptPasswordEncoder` và `Pbkdf2PasswordEncoder`. Với cấu hình đó:

- Mật khẩu **mới** được băm bằng BCrypt cost 12, prefix `{bcrypt}`.
- Hash có `{pbkdf2@SpringSecurity_v5_8}` có thể được kiểm tra bằng PBKDF2 mapping đã đăng ký.
- Hash mang `{noop}` **không có trong map** sẽ bị coi là id không được hỗ trợ và mặc định ném exception.
- Cấu hình không tự chuyển hash PBKDF2 cũ sang bcrypt trong database; cần flow nâng cấp riêng.

**Không đổi id của một hash cũ một cách tùy tiện.** Ví dụ hash PBKDF2 cũ không thể tự “trở thành bcrypt” bằng cách thay `{pbkdf2}` thành `{bcrypt}`. Tiền tố có nghĩa chọn phép kiểm tra tương ứng với **hash body hiện có**.

### 4.2. Factory mặc định

Spring Security cung cấp:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

Đây là fragment đặt bên trong `@Configuration` với import `@Bean` và `PasswordEncoderFactories`. Factory đăng ký nhiều mappings tương thích legacy và các id hiện đại, đồng thời chọn **`bcrypt` làm `idForEncode`** ở dòng Spring Security 6.5. Vì vậy tạo password mới cho user thông thường sẽ cho dạng:

```text
{bcrypt}$2a$10$...nội-dung-bcrypt-thực...
```

Dấu `...` ở đây là **ký hiệu minh họa**, không phải hash hợp lệ để lưu. Mỗi lần chạy, bcrypt có salt nên chuỗi cụ thể khác nhau. Để có hash hợp lệ, gọi `encoder.encode(rawPassword)`; **không tự nối một chuỗi giả vào {bcrypt}**.

### 4.3. Tại sao factory cho phép đọc format cũ?

Mục tiêu của DelegatingPasswordEncoder là giảm khó khăn khi nâng cấp ứng dụng: legacy account có thể xác minh bằng id đã được mapping, sau đó ứng dụng băm lại bằng thuật toán hiện hành.

**Khả năng đọc một định dạng yếu không đồng nghĩa khuyến nghị tạo mới bằng định dạng đó.** `{noop}` và digest yếu chỉ nên tồn tại trong migration hữu hạn với chính sách mạnh: giới hạn số tài khoản, kiểm soát thời gian, logging an toàn và yêu cầu reset khi cần. Việc tiếp tục support legacy quá lâu làm diện tấn công còn tồn tại.

### 4.4. id là case-sensitive

Trong các mappings mặc định, `bcrypt` khác `BCRYPT`, `MD5` khác `md5` nếu map định nghĩa khác nhau. Cần lưu nguyên id đã đăng ký. Không chuẩn hóa lowercase hàng loạt trên dữ liệu đã lưu nếu chưa biết mapping; một phép chuyển case có thể biến id hợp lệ thành unknown.

## 5. Bảng tình huống: encode, match và lỗi

Với `PasswordEncoderFactories.createDelegatingPasswordEncoder()` trong Spring Security 6.5:

| Giá trị lưu | Raw password đưa vào | Hành vi kỳ vọng | Lý do |
| --- | --- | --- | --- |
| Hash thật do `encoder.encode("secret")` tạo | `secret` | `true` | `{bcrypt}` định tuyến về bcrypt với salt/cost trong hash body. |
| Cùng hash đó | `wrong` | `false` | Algorithm hợp lệ nhưng password không khớp. |
| `{noop}legacy-demo` | `legacy-demo` | `true` theo legacy mapping | Chỉ minh họa khả năng đọc plaintext cũ; **không lưu như vậy ở sản phẩm mới**. |
| `{noop}legacy-demo` | `wrong` | `false` | NoOp legacy chỉ so giá trị gốc. |
| `{not-registered}whatever` | `whatever` | Mặc định ném `IllegalArgumentException` | Id không có mapping. |
| `$2a$10$...` không có `{bcrypt}` | `secret` | Mặc định ném `IllegalArgumentException` | Không đọc được Spring Security id. |
| `{bcrypt}not-a-real-bcrypt-hash` | `secret` | Không xác thực được (thường false; có thể cảnh báo format) | Prefix có mặt nhưng hash body không hợp lệ. |
| `{pbkdf2@SpringSecurity_v5_8}...` có hash hợp lệ | Raw đúng | Kết quả theo PBKDF2 mapping nếu có | Cần hash body đúng format và cấu hình tương thích. |

Các dòng có `...` chỉ là **ví dụ cấu trúc**, không phải dữ liệu để bỏ vào test/database nguyên văn. Dòng `{noop}` trong bảng cố tình là dữ liệu legacy vô bảo vệ, vì không thể học migration an toàn nếu lầm tưởng prefix tự khiến plaintext thành hash.

### 5.1. Phân biệt sai password với sai format

- **Sai password**, hash body hợp lệ và id được map: `matches` trả `false`.
- **Thiếu id** hoặc **id không được map**: mặc định `DelegatingPasswordEncoder` ném `IllegalArgumentException`; đây có thể là lỗi migration/configuration của dữ liệu.
- **Hash body hỏng/không tương thích:** encoder cụ thể có cách phản ứng riêng (false, warning hoặc exception); không đoán duy nhất một loại lỗi cho mọi thuật toán.

Trong HTTP login, một exception format có thể tạo lỗi 500 hoặc bị bao bọc tùy security flow, **không nên giả định mọi lỗi hash đều là 401**. Khắc phục bằng phân tích data format và mappings trên môi trường an toàn; không đổi default matcher sang `noop` để “cho login chạy”.

### 5.2. Unknown id không phải cơ hội thử mọi encoder

Một thiết kế nguy hiểm là “nếu `{id}` không biết thì thử plaintext, bcrypt, MD5, SHA-1 cho đến khi cái nào khớp”. Điều này làm luật xác thực mơ hồ, có thể chấp nhận format yếu ngoài dự kiến và khiến migration không thể kiểm soát.

**Nguyên tắc an toàn:** một hash lưu trữ phải có **format được khai báo**, số lượng thuật toán cho phép hữu hạn và cấu hình kiểm tra cụ thể. Nếu cần tạm hỗ trợ giá trị cũ không prefix, chỉ làm sau khi **chắc chắn** nó là định dạng nào, giới hạn phạm vi và có kế hoạch loại bỏ fallback.

## 6. Ví dụ Java nhỏ: quan sát chính xác prefix và matches

Đây là một file Java có `main` độc lập về mặt class, nhưng cần **Spring Security crypto dependency** từ project Maven ở mục 10.

### 6.1. PasswordFormatDemo.java

```java
package com.example.delegatingpassword;

import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordFormatDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "sample-pass";
        String stored = encoder.encode(raw);

        System.out.println(stored.startsWith("{bcrypt}"));
        System.out.println(encoder.matches(raw, stored));
        System.out.println(encoder.matches("wrong-pass", stored));
        System.out.println(encoder.matches(
            "legacy-pass", "{noop}legacy-pass"
        ));
        System.out.println(encoder.upgradeEncoding(
            "{noop}legacy-pass"
        ));
    }
}
```

Với Spring Security 6.5 factory mặc định, dự kiến in ra **đúng các dòng sau**:

```text
true
true
false
true
true
```

Không in ra `stored` vì hash bcrypt có salt ngẫu nhiên; so chuỗi hash cố định sẽ khiến demo không ổn định. Ví dụ này vẫn không có Spring Boot startup; nó chỉ dùng crypto API.

### 6.2. Tại sao {noop} khớp được?

`DelegatingPasswordEncoder` mặc định còn biết `noop` từ mappings của factory. Khi thấy `{noop}legacy-pass`, nó đưa phần body `legacy-pass` tới `NoOpPasswordEncoder` và đối chiếu trực tiếp. **Điều đó chứng minh tương thích legacy, không chứng minh khả năng bảo vệ mật khẩu.**

Khi đăng ký mới, luôn dùng `encoder.encode(raw)` để tạo hash mạnh; không lưu `{noop}...`. Nếu DB đang chứa `{noop}`, cần kế hoạch migration/forced reset nhanh chóng.

## 7. Không có prefix: xử lý đúng theo tình huống

Một tình huống rất phổ biến khi nâng cấp từ app cũ:

```text
$2a$10$XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

Đây chỉ là ký hiệu mô tả raw bcrypt body, chưa phải một hash chắc chắn hợp lệ. `BCryptPasswordEncoder` có thể đọc trực tiếp **raw bcrypt body** trong format hợp lệ, nhưng `DelegatingPasswordEncoder` cần biết **id**. Nếu DB lưu bcrypt mà **không có `{bcrypt}`**, default delegator không biết mapping nên ném lỗi.

### 7.1. Cách ưu tiên: bổ sung prefix cho giá trị đã xác minh là bcrypt

Nếu bạn đã xác định một tập record là bcrypt raw hợp lệ, và có backup/audit, có thể chuyển:

```text
TRƯỚC
$2a$10$...bcrypt-body...

SAU
{bcrypt}$2a$10$...bcrypt-body...
```

Việc thêm prefix chỉ bổ sung **metadata về thuật toán**; phần bcrypt body không thay đổi, nên về nguyên lý `matches(raw, "{bcrypt}" + oldHash)` dùng cùng phép kiểm tra trước đó.

**Phải biết chắc format trước khi sửa hàng loạt.** Không chỉ thêm `{bcrypt}` cho mọi giá trị thiếu `{id}`; một số có thể là hash SHA-256 cũ, plaintext hoặc dữ liệu hỏng. Dùng migration script có guard, sample validation, transaction/backup và rollback plan. Không expose raw hashes trong báo cáo hoặc issue tracker.

### 7.2. Khi giá trị đã mang {noop}

Bạn không thể “biến” plaintext thành bcrypt bằng cách sửa `{noop}` thành `{bcrypt}`. Body vẫn là plaintext và không thể xác minh như bcrypt. Phải **băm lại giá trị gốc trong ngữ cảnh được ủy quyền**, hoặc yêu cầu reset password.

Một đường nâng cấp phổ biến là: cho phép tài khoản legacy đăng nhập thành công **một lần qua cơ chế kiểm tra legacy**, rồi dùng raw password của lần login đó tạo hash mới và cập nhật store. Phần 12 sẽ minh họa với `DaoAuthenticationProvider` + `UserDetailsPasswordService`.

**Không tự đọc plaintext password từ database để chuyển hàng loạt** trừ khi đang xử lý dữ liệu legacy đã được biết và có quy trình bảo mật đặc biệt; plaintext tồn tại là tình trạng cần ưu tiên khắc phục, không phải tính năng mong muốn.

### 7.3. setDefaultPasswordEncoderForMatches: công cụ migration có rủi ro

`DelegatingPasswordEncoder` có method:

```java
delegating.setDefaultPasswordEncoderForMatches(fallback);
```

Nó chỉ dùng khi `id` không được mapping, kể cả id null/thiếu prefix. **Fallback nhận nguyên chuỗi stored password được truyền cho `matches`, gồm cả `{id}` nếu có**; Spring Security không tự cắt id khỏi dữ liệu khi gọi fallback.

Đây là một fragment API, `delegating` phải là `DelegatingPasswordEncoder` và `fallback` là một `PasswordEncoder` bạn đã thiết kế. Không tự ghi:

```java
// KHÔNG DÙNG:
delegating.setDefaultPasswordEncoderForMatches(
    NoOpPasswordEncoder.getInstance()
);
```

Một NoOp fallback không giới hạn có thể khiến cả những hash thiếu/unknown id được so như plaintext. Điều đó tạo đường kiểm tra rất yếu, che giấu dữ liệu lỗi và khiến migration không thể kiểm soát.

Nếu bắt buộc hỗ trợ raw bcrypt unprefixed trong thời gian ngắn, fallback nên **chỉ nhận dạng format bcrypt cụ thể**, từ chối mọi giá trị khác, được giám sát và bị loại bỏ sau migration. Phần lớn hệ thống sẽ an toàn/dễ audit hơn khi thực hiện **data migration thêm prefix** thay vì giữ fallback runtime lâu dài.

## 8. Custom mapping: thay đổi thuật toán ghi mà không phá dữ liệu cũ

Bạn có thể tự tạo `DelegatingPasswordEncoder` để minh họa thế nào là ghi mới bằng thuật toán X nhưng đọc thêm Y:

```java
import java.util.Map;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;

DelegatingPasswordEncoder encoder =
    new DelegatingPasswordEncoder(
        "bcrypt",
        Map.of(
            "bcrypt", new BCryptPasswordEncoder(12),
            "pbkdf2@SpringSecurity_v5_8",
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8()
        )
    );
```

Đây là **fragment đặt trong class/method Java**, không phải file Java độc lập. Nó không dùng toàn bộ mapping factory. Mật khẩu mới được encode bằng bcrypt 12; hash PBKDF2 5.8 được đọc với đúng mapping. Hash có `{pbkdf2}` (không có suffix version) sẽ **không tự được map** trong ví dụ này. Muốn nhận, phải thêm mapping tương ứng sau khi xác minh format dữ liệu.

### 8.1. Một id phiên bản có ích gì?

Các thuật toán như PBKDF2, scrypt và Argon2 có tham số: iteration count, salt length, memory cost, parallelism hoặc bản phối hợp. Nếu cùng dùng một tên chung `pbkdf2` trong mọi thời kỳ, hệ thống có thể hiểu nhầm hash cũ theo thông số mới. Spring Security đưa một số id dạng `@SpringSecurity_v5_8` để phân biệt cấu hình.

**Không tự thêm hoặc bỏ suffix version** mà không đối chiếu encoder implementation. Một hash được băm theo thông số khác có thể không xác minh được dù tên thuật toán cùng là PBKDF2.

### 8.2. Bcrypt cost và nâng cấp strength

Nếu bạn sử dụng `new BCryptPasswordEncoder(12)`, hash mới có cost 12. Khi user lưu bcrypt cost 10, `upgradeEncoding` của encoder tương ứng có thể cho biết nó nên được băm lại với strength hiện tại; bản thân `matches` vẫn có thể kiểm tra đúng hash cost 10.

Không nâng cost lên giá trị quá cao mà không benchmark CPU, latency và tải đăng nhập; password hashing phải tốn công để chống brute force nhưng cũng tiêu tốn tài nguyên server khi bị tấn công. Cần rate limiting, controls chống credential stuffing và quan sát hiệu năng.

### 8.3. Thay thuật toán không giống thay tiền tố

Đổi `idForEncode` chỉ ảnh hưởng **hash sinh ra từ encode mới**. Hash cũ vẫn còn id cũ và phải được map khi match. Muốn rehash số user hiện có, thường cần raw password ở lần đăng nhập hợp lệ hoặc một quy trình reset. Không có phép toán toán học “dịch” trực tiếp từ bcrypt hash sang Argon2 hash mà không có raw password.

## 9. Một dự án Spring Boot hoàn chỉnh để luyện tập

Lab có ba endpoint đơn giản:

| HTTP endpoint | Policy | Kết quả |
| --- | --- | --- |
| `GET /public/ping` | `permitAll()` | Anonymous có thể gọi 200. |
| `GET /api/me` | `authenticated()` | Cần HTTP Basic login; user hợp lệ nhận username. |
| `GET /admin/ping` | `hasRole("ADMIN")` | Chỉ tài khoản admin được vào. |
| Các request khác | `denyAll()` | Mặc định từ chối. |

Hai account demo được tạo bằng password **đã encode**:

- `learner` / `learner-pass` → `ROLE_USER`.
- `admin` / `admin-pass` → `ROLE_USER`, `ROLE_ADMIN`.

Dự án không có endpoint tạo user/reset password từ browser. Phần migration/password-upgrade dùng unit test tách biệt, không mở một cửa đăng nhập legacy `{noop}` trên HTTP app. Mật khẩu trong source chỉ dành cho **localhost/test**, không đưa vào môi trường thực.

### 9.1. Cấu trúc project

```text
delegating-password-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/delegatingpassword/
    │   ├── DelegatingPasswordApplication.java
    │   ├── SecurityConfig.java
    │   ├── IdentityController.java
    │   └── PasswordFormatDemo.java
    └── test/java/com/example/delegatingpassword/
        ├── DelegatingPasswordEncoderTest.java
        ├── PasswordUpgradeTest.java
        └── PasswordHttpTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>delegating-password-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

Parent/BOM Spring Boot quản lý dependency versions tương thích cho Spring Security và JUnit. `3.5.0` được chọn làm ví dụ API; dự án thật phải nâng lên bản vá còn được hỗ trợ. Không thêm Spring WebFlux vào lab Servlet này; WebFlux dùng cấu hình security khác.

### 9.3. DelegatingPasswordApplication.java

```java
package com.example.delegatingpassword;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DelegatingPasswordApplication {
    public static void main(String[] args) {
        SpringApplication.run(DelegatingPasswordApplication.class, args);
    }
}
```

Lớp khởi động nằm ở package gốc để component scan tìm `SecurityConfig` và `IdentityController`. PasswordFormatDemo là một entry point khác dùng để quan sát encoder; không phải class của web request.

### 9.4. SecurityConfig.java

```java
package com.example.delegatingpassword;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("learner-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/me").authenticated()
                .requestMatchers("/admin/ping").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

**Đọc cấu hình theo trách nhiệm:**

1. `passwordEncoder()` đưa một `PasswordEncoder` bean có khả năng encode mới bằng bcrypt và match theo prefix.
2. `users(...)` gọi `encoder.encode(...)` **trước khi lưu** user; từ đó `UserDetails#getPassword()` chứa hash có `{bcrypt}`.
3. `InMemoryUserDetailsManager` là user store học tập. Khi app restart, hash mới được sinh lại với salt mới, nhưng password raw demo vẫn giống.
4. `DaoAuthenticationProvider` do Spring Security/Boot cấu hình trong luồng tương ứng có thể dùng `UserDetailsService` bean và `PasswordEncoder` bean này để xác minh Basic credentials. Không phải tự gọi `encoder.matches(...)` trong controller.
5. `SessionCreationPolicy.STATELESS` giúp ví dụ Basic theo request không dựa vào session login; không biến Basic thành an toàn qua HTTP thường.
6. `httpBasic(...)` bật authentication filter; form login được tắt để 401 dễ quan sát. Không tắt CSRF mặc định; các endpoint chỉ đọc GET nên không cần CSRF token trong test này.
7. `anyRequest().denyAll()` bảo vệ route chưa khai báo. `hasRole("ADMIN")` dùng authority `ROLE_ADMIN` theo prefix role mặc định.

**Không coi createDelegatingPasswordEncoder tự sinh mật khẩu:** raw string demo vẫn nằm trong Java source, vì vậy không phù hợp production. Với ứng dụng thật, mật khẩu phải đến từ flow đăng ký/đổi mật khẩu an toàn, lưu hash vào DB, không hard-code.

### 9.5. IdentityController.java

```java
package com.example.delegatingpassword;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin/ping")
    public String adminPing() {
        return "admin-only";
    }
}
```

Controller chỉ trả username đã được xác thực, **không trả password hash, credentials hay `Authentication` object nguyên vẹn**. Việc đăng nhập/kiểm tra hash diễn ra trước controller trong security filters/providers.

### 9.6. Chạy và thử HTTP

Tại thư mục `delegating-password-lab`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Mở terminal mới:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i -u learner:learner-pass http://localhost:8080/api/me
curl -i -u learner:wrong-pass http://localhost:8080/api/me
curl -i -u learner:learner-pass http://localhost:8080/admin/ping
curl -i -u admin:admin-pass http://localhost:8080/admin/ping
```

Trên PowerShell, dùng `curl.exe` nếu `curl` là alias của `Invoke-WebRequest`.

Kết quả dự kiến:

| Request | HTTP status | Body khi thành công |
| --- | --- | --- |
| `GET /public/ping` anonymous | **200** | `pong` |
| `GET /api/me` anonymous | **401** | Không tiết lộ identity |
| `GET /api/me` learner đúng password | **200** | JSON có `username=learner` |
| `GET /api/me` learner sai password | **401** | Không có verified Authentication |
| `GET /admin/ping` learner | **403** | Thiếu ROLE_ADMIN |
| `GET /admin/ping` admin | **200** | `admin-only` |

Đây là **expected behavior** để bạn tự kiểm chứng, không phải log server đã chạy tại máy của bạn. HTTP Basic gửi Base64 của username/password, **không mã hóa đường truyền**; chỉ dùng local HTTP trong bài, sử dụng HTTPS/TLS khi có credentials thật.

## 10. JUnit test cho tiền tố, match và unknown id

Tạo `src/test/java/com/example/delegatingpassword/DelegatingPasswordEncoderTest.java`. Các test này không cần Spring Boot application context; chỉ sử dụng API crypto và JUnit.

```java
package com.example.delegatingpassword;

import org.junit.jupiter.api.Test;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DelegatingPasswordEncoderTest {

    private final PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

    @Test
    void newPasswordIsStoredWithBcryptId() {
        String stored = encoder.encode("new-pass");

        assertThat(stored).startsWith("{bcrypt}");
        assertThat(stored).contains("$2");
        assertThat(encoder.matches("new-pass", stored)).isTrue();
    }

    @Test
    void correctRawMatchesButIncorrectRawDoesNot() {
        String stored = encoder.encode("correct-pass");

        assertThat(encoder.matches(
            "correct-pass", stored
        )).isTrue();
        assertThat(encoder.matches(
            "incorrect-pass", stored
        )).isFalse();
    }

    @Test
    void twoBcryptEncodesOfSamePasswordCanDiffer() {
        String first = encoder.encode("same-pass");
        String second = encoder.encode("same-pass");

        assertThat(first).isNotEqualTo(second);
        assertThat(encoder.matches(
            "same-pass", first
        )).isTrue();
        assertThat(encoder.matches(
            "same-pass", second
        )).isTrue();
    }

    @Test
    void legacyNoopCanBeVerifiedButNeedsUpgrade() {
        // Chỉ minh họa đọc dữ liệu plaintext cũ; KHÔNG lưu như vậy.
        String oldStored = "{noop}legacy-pass";

        assertThat(encoder.matches(
            "legacy-pass", oldStored
        )).isTrue();
        assertThat(encoder.matches(
            "wrong-pass", oldStored
        )).isFalse();
        assertThat(encoder.upgradeEncoding(oldStored)).isTrue();
    }

    @Test
    void currentBcryptNormallyDoesNotNeedUpgrade() {
        String stored = encoder.encode("already-current");

        assertThat(encoder.upgradeEncoding(stored)).isFalse();
    }

    @Test
    void unknownIdIsRejectedByDefault() {
        assertThatThrownBy(() -> encoder.matches(
            "any-pass", "{not-registered}anything"
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void missingIdIsRejectedByDefault() {
        String rawBcrypt =
            new BCryptPasswordEncoder().encode("legacy-pass");

        assertThatThrownBy(() -> encoder.matches(
            "legacy-pass", rawBcrypt
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void knownRawBcryptCanBeMatchedAfterPrefixMigration() {
        String rawBcrypt =
            new BCryptPasswordEncoder().encode("legacy-pass");

        String prefixed = "{bcrypt}" + rawBcrypt;

        assertThat(encoder.matches(
            "legacy-pass", prefixed
        )).isTrue();
        assertThat(encoder.matches(
            "wrong-pass", prefixed
        )).isFalse();
    }

    @Test
    void wrongAlgorithmIdCannotTurnPlaintextIntoBcrypt() {
        assertThat(encoder.matches(
            "plaintext",
            "{bcrypt}plaintext"
        )).isFalse();
    }

    @Test
    void rawPasswordIsNotTheValueStoredInUserDetails() {
        String stored = encoder.encode("learner-pass");

        assertThat(stored).isNotEqualTo("learner-pass");
        assertThat(stored).startsWith("{bcrypt}");
        assertThat(encoder.matches(
            "learner-pass", stored
        )).isTrue();
    }
}
```

**10 test cases** minh họa:

- Encode mới dùng `{bcrypt}`.
- `matches` so raw với hash, không so hai lần encode.
- Bcrypt dùng salt nên kết quả có thể khác nhau.
- Legacy `{noop}` được factory nhận biết nhưng cần upgrade.
- Unknown id/thiếu id mặc định ném `IllegalArgumentException`.
- Bcrypt raw thiếu prefix có thể được match khi bổ sung đúng `{bcrypt}`.
- Tự đổi prefix thành bcrypt khi body là plaintext **không làm mật khẩu hợp lệ**.

Test về hai bcrypt hash khác nhau dựa trên tính chất salt ngẫu nhiên; khả năng va chạm về mặt lý thuyết không phải bằng 0, nhưng với bộ sinh ngẫu nhiên tốt và mỗi lần gọi độc lập, việc trùng là cực kỳ khó xảy ra. Trong test production nghiêm ngặt, nên ưu tiên assert `matches` hơn là dựa vào tính khác nhau của từng chuỗi.

## 11. Migration-on-login với UserDetailsPasswordService

Trong Spring Security username/password, việc nâng cấp mật khẩu cũ sau một lần login hợp lệ có thể kết hợp:

1. `DaoAuthenticationProvider` kiểm tra mật khẩu gốc so với hash đang lưu bằng `PasswordEncoder.matches`.
2. Nếu password hợp lệ và `PasswordEncoder.upgradeEncoding(storedHash)` yêu cầu nâng cấp, provider có thể tạo hash mới bằng `encode(rawPassword)`.
3. Một `UserDetailsPasswordService` được cấu hình sẽ lưu encoded hash mới cho user.
4. Lần login sau dùng hash hiện hành, không cần special-case ở controller.

**Điều kiện then chốt:** `UserDetailsPasswordService` phải được wiring vào provider; không phải cứ khai báo DelegatingPasswordEncoder là database tự được migration. `InMemoryUserDetailsManager` hỗ trợ API cập nhật password, nhưng nó chỉ giữ dữ liệu trong RAM; bài test dùng instance riêng.

### 11.1. PasswordUpgradeTest.java

```java
package com.example.delegatingpassword;

import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PasswordUpgradeTest {

    private final PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

    private InMemoryUserDetailsManager legacyUsers() {
        return new InMemoryUserDetailsManager(
            User.withUsername("legacy")
                .password("{noop}legacy-pass")
                .roles("USER")
                .build()
        );
    }

    private AuthenticationManager managerWithPasswordUpgrade(
            InMemoryUserDetailsManager users) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        // Cho provider quyền cập nhật hash sau xác thực thành công.
        provider.setUserDetailsPasswordService(users);

        return new ProviderManager(provider);
    }

    @Test
    void successfulLegacyLoginRehashesPasswordToBcrypt() {
        InMemoryUserDetailsManager users = legacyUsers();
        AuthenticationManager manager =
            managerWithPasswordUpgrade(users);

        String before =
            users.loadUserByUsername("legacy").getPassword();

        assertThat(before).isEqualTo("{noop}legacy-pass");

        Authentication result = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "legacy", "legacy-pass"
            )
        );

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("legacy");

        String after =
            users.loadUserByUsername("legacy").getPassword();

        assertThat(after).startsWith("{bcrypt}");
        assertThat(after).isNotEqualTo(before);
        assertThat(encoder.matches(
            "legacy-pass", after
        )).isTrue();
        assertThat(encoder.upgradeEncoding(after)).isFalse();
    }

    @Test
    void wrongLegacyPasswordDoesNotTriggerUpgrade() {
        InMemoryUserDetailsManager users = legacyUsers();
        AuthenticationManager manager =
            managerWithPasswordUpgrade(users);

        assertThatThrownBy(() -> manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "legacy", "wrong-pass"
            )
        )).isInstanceOf(BadCredentialsException.class);

        assertThat(users.loadUserByUsername(
            "legacy"
        ).getPassword()).isEqualTo("{noop}legacy-pass");
    }

    @Test
    void rehashedPasswordStillAuthenticatesOnNextLogin() {
        InMemoryUserDetailsManager users = legacyUsers();
        AuthenticationManager manager =
            managerWithPasswordUpgrade(users);

        manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "legacy", "legacy-pass"
            )
        );

        Authentication again = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "legacy", "legacy-pass"
            )
        );

        assertThat(again.isAuthenticated()).isTrue();
        assertThat(users.loadUserByUsername(
            "legacy"
        ).getPassword()).startsWith("{bcrypt}");
    }

    @Test
    void encoderOnlyDoesNotRewriteUserStore() {
        InMemoryUserDetailsManager users = legacyUsers();

        assertThat(encoder.matches(
            "legacy-pass",
            users.loadUserByUsername("legacy").getPassword()
        )).isTrue();

        assertThat(encoder.upgradeEncoding(
            users.loadUserByUsername("legacy").getPassword()
        )).isTrue();

        // Chỉ gọi matches/upgradeEncoding không ghi vào store.
        assertThat(users.loadUserByUsername(
            "legacy"
        ).getPassword()).isEqualTo("{noop}legacy-pass");
    }
}
```

**4 test cases** riêng về migration:

- Đăng nhập legacy thành công → provider dùng PasswordEncoder + UserDetailsPasswordService cập nhật hash.
- Sai password → không nâng cấp/lưu gì.
- Sau khi rehash, login lần tiếp theo vẫn hợp lệ.
- Chỉ gọi `matches`/`upgradeEncoding` không tự thay đổi user store.

**Cảnh báo:** Dữ liệu `{noop}` trong test chỉ để mô phỏng giai đoạn chuyển đổi. Không đem tài khoản plaintext này vào app production. Khi có một lượng lớn record cũ, cân nhắc buộc reset password, giới hạn thời gian đọc legacy, tăng bảo vệ login và giám sát việc phần trăm record chưa được nâng cấp.

### 11.2. Tại sao cần raw password khi migration?

Hash password là hàm một chiều được thiết kế để không dễ khôi phục raw. Bạn **không thể** tạo bcrypt hash của password gốc chỉ bằng cách “đổi thuật toán” trên một hash MD5/legacy mà vẫn giữ được hợp đồng `matches(raw, newHash)`, trừ khi có raw password ở một lần login hợp lệ hoặc một quy trình reset.

Flow on-login thuận tiện vì có raw password do người dùng vừa nhập; sau khi xác minh, provider tạo hash mới ngay trong đường xử lý đáng tin. Password gốc không cần lưu ra DB/queue/log. Với những account không đăng nhập nữa, hãy có chiến lược reset/expiry thay vì duy trì hash yếu vô thời hạn.

### 11.3. Tại sao user store phải hỗ trợ updatePassword?

`UserDetailsService` chỉ đọc account. Một provider không thể tự cập nhật database nếu không có API ghi. `UserDetailsPasswordService.updatePassword(UserDetails, String newPassword)` cung cấp điểm nối cho rehash, và những manager như `InMemoryUserDetailsManager` hay implementation phù hợp có thể hỗ trợ.

Một hệ thống custom repository có thể implement `UserDetailsPasswordService` với transaction, optimistic locking và audit phù hợp. Đối với nhiều node, cần xem cache invalidation và cập nhật mật khẩu đồng thời. Nếu password đã được reset trong lúc login cũ còn đang xử lý, không được cho một rehash trễ **ghi đè mật khẩu mới**; dùng conditional update/compare-and-set theo hash/version hoặc policy nhất quán.

## 12. MockMvc: bảo đảm PasswordEncoder được dùng trong đăng nhập thật

Unit test trực tiếp `encoder.matches` chưa chứng minh cấu hình web thực đang sử dụng đúng encoder và user store. Thêm `src/test/java/com/example/delegatingpassword/PasswordHttpTest.java`:

```java
package com.example.delegatingpassword;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void privateEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void encodedPasswordWorksWithHttpBasicLogin() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username")
                .value("learner"));
    }

    @Test
    void badPasswordIsRejectedEvenForExistingUser()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void learnerCannotAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/ping")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/ping")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
```

Có **6 HTTP tests**. Tổng tất cả các lớp có **20 tests**: 10 tests PasswordEncoder, 4 tests password migration và 6 tests HTTP.

Lợi ích của nhóm HTTP test là xác nhận **password đã băm và prefix thực sự được dùng trong authentication flow**. `@WithMockUser` có ích khi chỉ cần thử authorization nhưng không kiểm tra raw-vs-hash; do đó bài dùng HTTP Basic với credentials demo để kiểm chứng bộ encoder thực.

### 12.1. Chạy tests

```bash
mvn test
```

Kỳ vọng các tests qua nếu dependencies, code và môi trường đúng. Đây là **kết quả thiết kế**, không phải một lần Maven đã được chạy thay người học. Hash bcrypt ngẫu nhiên sẽ không khiến test sai vì assertions dùng `startsWith("{bcrypt}")` và `matches` thay vì so hash cố định.

## 13. Nâng cấp password hash trong production: quy trình khuyến nghị

Để áp dụng cho một cơ sở dữ liệu thật, cần nhiều hơn việc cấu hình factory. Một quy trình migration được quản lý tốt thường có các giai đoạn.

### Giai đoạn A — Kiểm kê chính xác, không lộ secrets

1. Xác định các dạng password hiện có: bcrypt raw thiếu id, hash đã prefix, plaintext legacy, PBKDF2/SCrypt/Argon2 và dữ liệu hỏng.
2. Thống kê **số lượng theo loại format**, không đưa raw hash/password vào dashboard/logs.
3. Đối chiếu schema column length, collation, trimming, encoding và quy tắc import/export.
4. Đánh giá rủi ro hash yếu hoặc plaintext. Với plaintext legacy, ưu tiên reset và giảm thời gian hỗ trợ.
5. Xác nhận các node ứng dụng đều sử dụng **cùng mapping** trước khi triển khai bất kỳ giá trị hash mới nào.

### Giai đoạn B — Xác lập format hiện hành

1. Chọn encoder phù hợp với chính sách mật khẩu và tải máy; benchmark cost.
2. Cấu hình `PasswordEncoder` trong toàn bộ dịch vụ xác thực/đăng ký/đổi password.
3. Chỉ ghi `encoder.encode(rawPassword)` cho account mới.
4. Nếu ứng dụng trước đó lưu raw bcrypt thiếu prefix, xem xét migration bổ sung `{bcrypt}` có guard và backup.
5. Không tạo mappings mơ hồ kiểu “thử mọi thuật toán” hoặc dùng `noop` như fallback cho giá trị chưa xác định.

### Giai đoạn C — Nâng cấp khi đăng nhập, có kiểm soát

1. Khi credentials đúng, `DaoAuthenticationProvider` xác thực bằng encoder theo id cũ.
2. `upgradeEncoding(storedHash)` cho biết có cần rehash không.
3. `UserDetailsPasswordService.updatePassword(...)` lưu hash hiện hành qua transaction/cập nhật có điều kiện.
4. Nếu có cache UserDetails, refresh/invalidate theo policy để tránh giữ hash cũ.
5. Không ghi raw password vào event bus, analytics, message queue hoặc log.
6. Xem xét retry/concurrency: reset password có thể diễn ra đồng thời với login legacy.

### Giai đoạn D — Đóng cửa legacy

1. Theo dõi số lượng account còn format yếu; không log chi tiết password.
2. Đến hạn chính sách, yêu cầu những account chưa nâng cấp thực hiện reset password.
3. Loại bỏ các mappings legacy không còn cần thiết hoặc giới hạn đường xác thực tương ứng.
4. Test rolling deployment, backups/restore, phiên đang tồn tại và các consumer đọc chung bảng user.
5. Bảo đảm mật khẩu mới không bị ghi theo format cũ từ một job/script/admin UI quên cập nhật.

**Bản thân `DelegatingPasswordEncoder` không tự viết bất kỳ báo cáo migration nào.** Các bước kiểm kê và observability là trách nhiệm hệ thống/vận hành. Cần tách riêng thống kê loại hash với logs chứa secrets.

## 14. Bảo mật và vận hành: những điều prefix không giải quyết

### 14.1. Prefix không ngăn database bị rò

Nếu DB bị lộ, attacker có thể đọc `{bcrypt}...` và thử password offline; bcrypt với salt/work factor mạnh làm chi phí thử tăng nhưng không bảo đảm tuyệt đối. Bảo vệ database, backup, privilege, audit và danh sách password phổ biến vẫn quan trọng. Dùng password policy chống mật khẩu yếu và MFA khi phù hợp.

### 14.2. Hash không thay TLS

Khi user đăng nhập, **raw password** được gửi tới server qua HTTPS/TLS. Password hash trong database không làm cho HTTP Basic over HTTP tự an toàn. Basic Base64 không phải encryption. Không gửi raw password hay encoded hash trong URL query, log, exception hoặc response.

### 14.3. Prefix không phải chữ ký chống sửa dữ liệu

Nếu attacker có quyền UPDATE cột password, họ có thể thay bằng hash của mật khẩu mình biết kèm id hợp lệ, trừ khi hệ thống có biện pháp bảo vệ khác. Phải áp least privilege, audit và kiểm soát thao tác quản trị. Prefix chỉ hỗ trợ **routing thuật toán**, không xác thực tính toàn vẹn record.

### 14.4. Password hash không giống encryption

Encryption có key và khả năng giải mã cho người có key; password hashing được thiết kế một chiều, có salt và cost. Không yêu cầu “decrypt password để gửi email nhắc lại”; luồng đúng là reset, không khôi phục password cũ.

### 14.5. BCrypt không phải password hashing duy nhất

Argon2, scrypt và PBKDF2 có các đặc trưng/cost khác nhau. Spring Security hỗ trợ các thuật toán này trong crypto module; một số cần dependency bổ sung hoặc phần cứng/benchmark phù hợp. Việc chọn thuật toán cho hệ thống mới phải theo khuyến nghị mật mã đương thời, chính sách tổ chức, tương thích FIPS nếu áp dụng và dữ liệu thực tế. **Không thay prefix chỉ vì “argon2 nghe mới hơn”.**

### 14.6. Pepper, secret rotation và key management

Một số hệ thống dùng pepper (bí mật server-side) bổ sung cho password hashing. Đây là kiến trúc riêng: phải có secret manager, kế hoạch rotation, xử lý nhiều phiên bản pepper và tránh mất khả năng login. `DelegatingPasswordEncoder` mặc định không tự thêm pepper hay giải quyết rotation. Không đặt pepper cố định trong source hoặc chung với database dump.

### 14.7. Đăng nhập sai nhiều lần và denial of service

Adaptive hashing tiêu tốn CPU/memory. Kẻ tấn công có thể gửi nhiều request với password sai nhằm lạm dụng tài nguyên. Áp rate limits, retry budgets, monitoring, chống credential stuffing, và phân bổ tài nguyên thích hợp. Không chọn cost thấp chỉ để test nhanh rồi vô tình giữ cấu hình ấy ở production.

## 15. Những lỗi phổ biến

### Lỗi 1 — “Có {bcrypt} nghĩa là hash chắc chắn đúng”

Prefix chỉ chọn mapping; body phải đúng định dạng, và raw password phải khớp. Không coi `startsWith("{bcrypt}")` là authentication success.

### Lỗi 2 — “Chỉ cần đổi {noop} thành {bcrypt}”

Nếu body là plaintext, thay prefix không biến nó thành bcrypt. Cần hash mới từ raw password hợp lệ hoặc flow reset.

### Lỗi 3 — “Hash không prefix sẽ tự được DelegatingPasswordEncoder đoán”

Mặc định thiếu id gây `IllegalArgumentException`. Dữ liệu raw bcrypt legacy cần thêm prefix đúng format hoặc fallback **rất giới hạn** với kế hoạch loại bỏ.

### Lỗi 4 — “Unknown id luôn tương đương wrong password”

Không đúng: `matches` của DelegatingPasswordEncoder mặc định ném exception nếu id unmapped, khác với false do password sai. Cần sửa mapping/dữ liệu, không vội nới auth rule.

### Lỗi 5 — “Dùng NoOpPasswordEncoder làm default matches cho mọi id”

Có thể tạo đường plaintext yếu với dữ liệu thiếu/unknown id. Không dùng fallback toàn cục như vậy.

### Lỗi 6 — “Hai lần encode raw giống nhau phải cho chuỗi giống nhau”

Bcrypt có salt ngẫu nhiên. So `encoder.matches(raw, stored)`, không so `encode(raw).equals(stored)`.

### Lỗi 7 — “Có thể double-hash password khi import”

Nếu một script gọi `encoder.encode(storedHash)` thay vì encode raw, hệ thống sẽ lưu hash của **chuỗi hash**, khiến raw password ban đầu không còn đối chiếu được. Kiểm tra rõ dữ liệu input là raw hay already-encoded.

### Lỗi 8 — “PasswordEncoder tự nâng cấp mọi record”

`upgradeEncoding` chỉ trả boolean; cần một flow như `DaoAuthenticationProvider` + `UserDetailsPasswordService` hoặc migration script có đủ quyền. Không tự thay DB.

### Lỗi 9 — “Nâng cost chỉ cần đổi id”

Cost bcrypt nằm trong hash body và cấu hình BCrypt encoder; id `bcrypt` không mã hóa trực tiếp work factor. Rehash với encoder/cost mới khi có raw password hợp lệ.

### Lỗi 10 — “Bỏ @SpringSecurity_v5_8 không ảnh hưởng”

Versioned ids có ý nghĩa xác định cấu hình PBKDF2/scrypt/Argon2. Không đổi suffix trên dữ liệu đã lưu nếu chưa chứng minh hash body tương thích.

### Lỗi 11 — “Tạo PasswordEncoder bean mới nhưng UserDetailsService vẫn lưu hash kiểu cũ tùy ý”

Cần đồng bộ cách ghi và cách đọc giữa các modules, nodes, scripts và identity providers. Đảm bảo account mới luôn có format phù hợp.

### Lỗi 12 — “Chỉ có BCryptPasswordEncoder bean nhưng database chứa {bcrypt}...”

`BCryptPasswordEncoder` trực tiếp thường kỳ vọng bcrypt body, không phải prefix `{bcrypt}` của delegating format. Dùng DelegatingPasswordEncoder hoặc xử lý mapping có kiểm chứng, không tùy tiện cắt string.

### Lỗi 13 — “Cột password chỉ cần 60 ký tự”

Bcrypt body có độ dài đặc trưng, nhưng prefix và nhiều thuật toán khác cần dài hơn. Dùng schema đủ rộng và tránh silent truncation.

### Lỗi 14 — “Trả password hash trong /api/me để debug”

Hash là dữ liệu nhạy cảm dù không phải raw password. Không để client/download/log hoặc analytics thu thập password hashes.

### Lỗi 15 — “Lưu hash trong source để khỏi cần DB”

Hard-code hash cho tài khoản thật vẫn không giải quyết lifecycle, secret rotation, lockout hoặc revoke, và source history trở thành tài sản cần bảo vệ. Demo local mới có thể dùng user in-memory.

### Lỗi 16 — “Hash password thay thế authorization”

Login thành công chứng minh identity theo cơ chế; quyền truy cập endpoint và từng object vẫn cần `hasRole`/`hasAuthority`, ownership/tenant rules và mặc định deny phù hợp.

### Lỗi 17 — “{id} là thuật toán do frontend chọn”

Không tin client tự chọn mapping khi login; server quyết định encoder từ dữ liệu đã lưu và policy. Không cho client ghi hash/prefix trực tiếp vào UserDetails.

### Lỗi 18 — “Cấu hình salt/algorithm tự chế tốt hơn thư viện”

Tự kết hợp SHA-256 một lần, salt cố định hoặc base64 password không tương đương password hashing thích hợp. Dùng implementation có kiểm chứng và benchmark work factor.

### Lỗi 19 — “Upgrade-on-login luôn an toàn trước thay đổi đồng thời”

Nếu password reset và rehash cùng ghi, có thể ghi đè giá trị mới; cần conditional update, versioning, transaction và test concurrency.

### Lỗi 20 — “Giữ legacy mapping vô thời hạn vì tiện”

Mục tiêu của mapping là chuyển đổi có kiểm soát, không phải lý do kéo dài hỗ trợ thuật toán yếu. Đặt mốc hoàn tất hoặc buộc reset.

## 16. Tự kiểm tra kiến thức

**1. Định dạng chuẩn của DelegatingPasswordEncoder là gì?**  
`{id}encodedPassword`. Prefix chỉ ra mapping encoder cho hash body, không chứa raw password.

**2. idForEncode dùng làm gì?**  
Chọn encoder dùng **khi tạo hash mới** bằng `encode`.

**3. idToPasswordEncoder dùng làm gì?**  
Cho phép tra `id` trong hash lưu và chọn encoder tương ứng khi `matches`/xem xét upgrade.

**4. Factory mặc định của Spring Security 6.5 encode mới bằng thuật toán nào?**  
Bcrypt, với prefix `{bcrypt}`.

**5. Tại sao hai lần encoder.encode("same") có thể khác nhau?**  
Bcrypt sử dụng random salt, vì vậy chuỗi hash không ổn định dù raw password giống nhau.

**6. Nên so sánh raw password thế nào?**  
Dùng `encoder.matches(rawPassword, encodedPassword)`, không dùng `encode(raw).equals(hash)`.

**7. Khi gặp hash không có prefix, mặc định DelegatingPasswordEncoder làm gì?**  
Thường ném `IllegalArgumentException` do id null/không có mapping.

**8. Khi gặp {not-registered}, mặc định làm gì?**  
Ném exception do id không được đăng ký trong map.

**9. Có thể thêm {bcrypt} cho mọi giá trị thiếu id không?**  
Không. Chỉ có thể làm vậy khi đã xác minh giá trị đó thực sự là raw bcrypt hash hợp lệ.

**10. Có thể đổi {noop} thành {bcrypt} mà giữ body không?**  
Không. Cần tạo hash bcrypt mới từ raw password hợp lệ hoặc reset.

**11. upgradeEncoding có tự lưu hash mới không?**  
Không, nó chỉ trả boolean; phải có cơ chế ghi vào user store.

**12. DaoAuthenticationProvider có thể tự rehash khi login không?**  
Có nếu được cấu hình đúng PasswordEncoder và `UserDetailsPasswordService` phù hợp, sau khi xác thực thành công và cần upgrade.

**13. BCrypt cost 10 nằm trong {bcrypt} hay trong bcrypt body?**  
Trong bcrypt body, ví dụ đoạn `$2a$10$...`.

**14. Khi đổi sang PBKDF2 hay Argon2, chỉ cần thay id không?**  
Không. Phải tạo hash mới bằng thuật toán tương ứng, giữ mapping legacy khi cần và lập kế hoạch migration.

**15. Có nên dùng {noop} cho tài khoản đăng ký mới?**  
Không. Nó lưu plaintext và không chống được việc lộ DB.

**16. Cột DB quá ngắn gây hậu quả gì?**  
Có thể cắt prefix/hash body, khiến login lỗi và migration không đáng tin. Cần schema đủ rộng.

**17. PasswordEncoder có bảo vệ đường truyền HTTP Basic không?**  
Không. Raw password vẫn đi tới server, cần HTTPS/TLS.

**18. Tại sao không log password hashes?**  
Vì hash có thể bị tấn công offline và lộ cách lưu/cấu hình; logs là một bề mặt rò dữ liệu bổ sung.

## 17. Checklist khi triển khai thật

- [ ] Xác định đầy đủ các loại hash đang tồn tại, các prefix và bản không prefix.
- [ ] Chọn `PasswordEncoder` có mapping tối thiểu cần thiết; encode mới theo chính sách hiện hành.
- [ ] Bảo đảm user store lưu nguyên chuỗi `{id}encodedPassword`, không cắt/bỏ prefix.
- [ ] Đồng nhất cấu hình giữa signup, login, reset/change-password và jobs/admin scripts.
- [ ] Kiểm thử đúng raw password, sai password, missing/unknown id, bad body và migration.
- [ ] Không cho client tự gửi hash/prefix/authorities để tạo verified identity.
- [ ] Dùng TLS, secret management, password policy, rate limits, brute-force protection và MFA khi phù hợp.
- [ ] Nếu hỗ trợ legacy, kiểm soát thời gian và phạm vi, có phương án buộc reset.
- [ ] Nếu dùng upgrade-on-login, cấu hình `UserDetailsPasswordService`, kiểm thử concurrency/caching.
- [ ] Đảm bảo password hash không có trong API responses, logs, traces, analytics, exports.
- [ ] Kiểm tra hiệu năng bcrypt/Argon2/PBKDF2/scrypt cost và giới hạn tài nguyên.
- [ ] Cập nhật tài liệu schema, backup/restore, rolling deployment và rollback.
- [ ] Kiểm soát quyền sửa bảng user; việc chỉnh password hash có thể dẫn tới account takeover.
- [ ] Phân quyền endpoint/service/tenant tiếp sau authentication, default deny khi phù hợp.
- [ ] Nâng các phiên bản Spring Boot/Security theo bản vá hỗ trợ; test hashing/mapping trước deploy.

## Kết luận

**`DelegatingPasswordEncoder` là cầu nối giữa nhiều thuật toán băm mật khẩu và một hợp đồng PasswordEncoder chung.** Prefix `{id}` ở đầu giá trị đã lưu giúp chọn bộ kiểm tra đúng khi `matches(raw, stored)`; `idForEncode` chọn thuật toán để tạo hash mới. Với factory của Spring Security 6.5, hash mới thường là `{bcrypt}...`. Prefix **không tự băm mật khẩu, không chứng minh login thành công, không mã hóa ngược được và không thay authorization**.

Một hệ thống migration an toàn cần biết chính xác hash format, giữ các mapping cần thiết trong giai đoạn chuyển tiếp, từ chối unknown id theo policy, không dùng `noop` làm fallback rộng, và thực hiện rehash sau lần xác thực hợp lệ hoặc reset password. `upgradeEncoding` là tín hiệu; `UserDetailsPasswordService` cùng provider/service tin cậy mới thực hiện cập nhật vào user store. Khi triển khai ngoài lab, cần kiểm soát TLS, quyền sửa user record, hash cost, schema, logs, session/token và kiểm thử các trường hợp lỗi.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Password Storage, DelegatingPasswordEncoder và định dạng {id}](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Crypto module và PasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [Spring Security 6.5 — PasswordEncoderFactories JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/crypto/factory/PasswordEncoderFactories.html)
- [Spring Security 6.5 — DelegatingPasswordEncoder JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security 6.5 — PasswordEncoder JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetailsPasswordService JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security 6.5 — In-memory UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — Spring MVC Security Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
