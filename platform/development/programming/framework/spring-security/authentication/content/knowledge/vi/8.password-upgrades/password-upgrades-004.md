# Xử lý giá trị băm thiếu tiền tố hoặc dùng thuật toán không được chấp nhận

Một ứng dụng Spring Security chuyển từ kho mật khẩu cũ sang `DelegatingPasswordEncoder`. Một số người dùng có giá trị `password_hash` dạng `$2a$10$...` (bcrypt nhưng không có `{bcrypt}`), một số bản ghi dùng `{sha256}...` hoặc `{noop}...`, số khác có tiền tố không được hệ thống nhận diện. Sau khi triển khai, login báo lỗi kiểu:

```text
java.lang.IllegalArgumentException:
There is no PasswordEncoder mapped for the id "null"
```

Đây **không nhất thiết là người dùng nhập sai password**. Rất có thể database đang lưu verifier không có định danh thuật toán theo hợp đồng của encoder hiện tại. Ngược lại, một bản ghi có `{id}` hợp lệ về cú pháp **không đồng nghĩa thuật toán đó được tổ chức cho phép sử dụng**. Nếu sửa lỗi bằng cách bật `NoOpPasswordEncoder` hoặc fallback tùy ý cho mọi hash không nhận dạng, hệ thống có thể đánh đổi tính toàn vẹn xác thực để lấy một login “hết lỗi”.

Bài thuộc nhóm **Nâng cấp mật khẩu** của *Spring Security - authentication*, giải quyết hai tình huống chính:

1. **Thiếu tiền tố hoặc định dạng hỏng:** hash có khả năng đúng thuật toán nhưng thiếu `{id}`, có dấu ngoặc lỗi, whitespace, identifier không khớp hoặc dữ liệu sai.
2. **Thuật toán không được chấp nhận:** verifier khai báo `{noop}`, `{sha256}`, một scheme cũ/yếu, scheme không có trong allowlist của tổ chức, hoặc cost/parameters dưới chính sách.

**Nguyên tắc an toàn:** xác định **định dạng thực và nguồn gốc** trước khi sửa; chỉ thêm `{id}` khi thuật toán đã được chứng minh; không tự giải mã/re-hash mật khẩu nếu không có raw password; từ chối/đặt lại password đối với format nguy hiểm hoặc không rõ; nếu cần chuyển tiếp tạm thời, giới hạn chặt loại legacy và **nâng cấp sau một lần xác thực thành công**.

Ví dụ dùng **Java 17+, Spring Security Crypto 6.5.x và Gradle**. Có chương trình độc lập chạy được, lệnh chạy và stdout dạng boolean ổn định; các phần cấu hình Spring Boot/provider/SQL phía sau được phân biệt rõ là mẫu tích hợp, không phải một ứng dụng hoàn chỉnh nếu chưa nối vào kho người dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc định dạng lưu `{id}encodedPassword`, phân biệt `idForEncode` và danh sách `idToPasswordEncoder` được phép *matches*.
2. Giải thích nguyên nhân `id=null`, `id` không có mapping, và sự khác nhau giữa ngoại lệ cấu hình/định dạng với password không khớp.
3. Hiểu vì sao `PasswordEncoderFactories.createDelegatingPasswordEncoder()` có thể mang mapping cho các thuật toán legacy, nhưng **không phải danh sách được phép của tổ chức**.
4. Tạo `DelegatingPasswordEncoder` với allowlist rõ (ví dụ chỉ bcrypt theo policy), tránh fallback `NoOp`.
5. Sửa bản ghi bcrypt không tiền tố khi đã xác minh chính xác thuật toán và nguồn gốc; phân biệt **bổ sung metadata** với **nâng cấp sức mạnh hash**.
6. Xây chiến lược legacy migration online: xác thực raw password đúng scheme đã biết → encode bằng scheme mới → ghi có kiểm soát → thu hẹp/loại bỏ scheme cũ.
7. Biết khi nào phải buộc reset password hoặc cô lập bản ghi, thay vì thử đoán thuật toán từ dữ liệu không đáng tin.
8. Thiết kế kiểm thử không chấp nhận thuật toán ngoài chính sách, chống downgrade và bảo đảm người dùng không gặp HTTP 500 không cần thiết.

## 2. Bốn khái niệm không được lẫn

| Thuật ngữ | Nghĩa | Ví dụ |
| --- | --- | --- |
| **Raw password** | Bí mật người dùng nhập tại lần login/đổi password, chỉ tồn tại tạm thời. | Chuỗi do form login gửi qua HTTPS. |
| **Encoded password / verifier** | Kết quả từ hàm một chiều có tham số/salt, dùng để kiểm password mà không lưu raw. | Hash bcrypt có cost và salt. |
| **Algorithm identifier (`id`)** | Nhãn phía trước giúp Spring chọn `PasswordEncoder` để đọc verifier. | `bcrypt` trong `{bcrypt}...`. |
| **Password policy / allowlist** | Quy định thuật toán, work factor, định dạng và tình huống legacy được chấp nhận. | Chỉ bcrypt với cost tối thiểu theo môi trường. |

Một prefix là **metadata định tuyến encoder**, không phải salt và không phải bằng chứng hash an toàn. Bcrypt hash có cost thấp vẫn là bcrypt; `{bcrypt}` trên một chuỗi không phải bcrypt không biến chuỗi đó thành verifier bcrypt. Mật khẩu gốc **không thể khôi phục** một cách hợp lệ từ password hash để tự tạo hash mới offline.

### Hash khác mã hóa đảo ngược

`PasswordEncoder.encode(raw)` thực hiện một phép biến đổi một chiều, còn `matches(raw, stored)` so khớp raw với verifier đã lưu. Không có `decode(stored)` cho mật khẩu. Nếu cần đổi từ SHA-1/MD5 sang bcrypt mà chỉ có hash cũ, **không thể cứ decode rồi encode lại mật khẩu**. Bạn phải có một lần người dùng cung cấp lại raw password qua xác thực hợp lệ, hoặc buộc reset. Cách “bcrypt(MD5(password))” dựa trên hash cũ tạo một cơ chế mới phải phân tích kỹ rủi ro; không coi nó tương đương bcrypt trực tiếp từ password và không tự triển khai như giải pháp mặc định.

### Thuật toán “có hỗ trợ” không bằng “được phép”

Một thư viện có thể chứa encoder cho scheme cũ để hỗ trợ chuyển đổi. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` cung cấp nhiều mapping hơn mục tiêu “chỉ dùng bcrypt hiện tại”; một số legacy encoder tồn tại vì khả năng tương thích chứ không được khuyến nghị lưu mật khẩu mới. Chính sách hệ thống phải chọn rõ **scheme nào có thể tạo hash mới, scheme nào được tạm chấp nhận để verify và nâng cấp, scheme nào bị cấm hoàn toàn**.

## 3. DelegatingPasswordEncoder đọc {id} như thế nào?

Spring Security dùng format chung:

```text
{id}encodedPassword
  |        |
  |        +--> Phần verifier được encoder đích hiểu.
  +------------> Nhãn chọn PasswordEncoder trong mapping.
```

Các ví dụ:

```text
{bcrypt}$2a$12$......         Đã có id bcrypt; phần sau là hash bcrypt.
$2a$12$......                 Có dấu hiệu bcrypt nhưng thiếu {id}.
{sha256}abcdef...             Id rõ ràng, nhưng chính sách có thể cấm SHA-256 thuần.
{noop}password                 Raw password dưới nhãn noop: KHÔNG an toàn.
{unknown}abcdef...            Id chưa được ánh xạ.
{BCRYPT}$2a$12$......         Sai case nếu mapping chỉ có "bcrypt".
{bcrypt}not-a-bcrypt-hash     Id được biết nhưng dữ liệu sau prefix sai.
bcrypt}$2a$12$......          Cú pháp id bị hỏng.
```

Các đoạn trên chỉ **minh họa định dạng**; `......` không phải bcrypt verifier thực tế. Một verifier bcrypt thật chứa chuỗi salt/hash có cấu trúc và số ký tự tương ứng. Không sao chép những chuỗi minh họa vào database rồi kỳ vọng login được.

### 3.1 `idForEncode` và `idToPasswordEncoder`

`DelegatingPasswordEncoder` thường được xây bằng:

```java
String idForEncode = "bcrypt";
Map<String, PasswordEncoder> idToPasswordEncoder = Map.of(
        "bcrypt", new BCryptPasswordEncoder(12));

PasswordEncoder encoder = new DelegatingPasswordEncoder(
        idForEncode, idToPasswordEncoder);
```

Đây là đoạn cấu hình, cần imports `java.util.Map` và các class `org.springframework.security.crypto.password` tương ứng. Ý nghĩa:

- `idForEncode="bcrypt"`: gọi `encode(raw)` tạo verifier mới bằng bcrypt và tự gắn `{bcrypt}`.
- Map chứa `"bcrypt"`: gọi `matches(raw, "{bcrypt}...")` được định tuyến tới BCrypt encoder.
- Không có `"noop"`/`"sha256"`: những prefix đó không được nhận trong cấu hình này, dù thư viện Spring có lớp encoder hỗ trợ.
- Có thể cho scheme cũ **chỉ trong giai đoạn migration được phê duyệt**, nhưng cần ràng buộc đối tượng/dataset, thời hạn và kế hoạch xóa.

### 3.2 PasswordEncoderFactories là cấu hình tiện dụng, không thay chính sách

Cấu hình thường gặp:

```java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
```

Factory chọn encoder cho việc tạo hash mới và đăng ký một số encoder cho việc đọc các định dạng cũ. Điều này giúp chuyển đổi hệ thống nhưng **không thay thế quyết định “scheme nào được phép”**. Nếu chính sách cấm `{noop}`/digest nhanh thì dùng allowlist riêng hoặc lớp policy kiểm trước khi gọi encoder, đừng nghĩ rằng việc factory tạo ra một encoder là giấy phép sử dụng mọi id.

### 3.3 Các nhánh của matches()

| Dữ liệu lưu trữ | Kết quả với strict map chỉ có bcrypt | Lý do |
| --- | --- | --- |
| `{bcrypt}` + hash bcrypt đúng, raw password đúng | `true` | Encoder đích xác minh thành công. |
| `{bcrypt}` + hash bcrypt đúng, raw password sai | `false` | Credential không khớp. |
| Hash bcrypt nhưng không có `{bcrypt}` | Mặc định `IllegalArgumentException` với id `null` | Không tìm được id ở đầu chuỗi. |
| `{unknown}...` | Mặc định `IllegalArgumentException` | Không có mapping cho id. |
| `{sha256}...` hoặc `{noop}...` | Mặc định `IllegalArgumentException` trong strict map | Id bị loại khỏi allowlist. |
| `{bcrypt}` + body không phải bcrypt | Thường `false`/bị từ chối bởi BCrypt validator | Body không hợp format hoặc không khớp. |
| Password verifier rỗng/missing | Không nên dùng để xác thực | Dữ liệu bị lỗi hoặc account không có password auth. |

Lưu ý quan trọng: `DelegatingPasswordEncoder` không mặc định trả `false` cho mọi id không nhận diện; tài liệu Spring Security nêu **`IllegalArgumentException`**. Nếu ngoại lệ đó rò ra ngoài authentication flow không được xử lý, ứng dụng có thể biểu hiện thành lỗi 500. Không được “chữa” bằng cách luôn chấp nhận password hoặc bỏ qua `matches`.

## 4. Chẩn đoán lỗi trước khi đổi cấu hình

### 4.1 Đọc lỗi đúng ngữ cảnh

Lỗi kinh điển:

```text
There is no PasswordEncoder mapped for the id "null"
```

Thường nghĩa là encoded verifier **không bắt đầu bằng prefix `{...}` đúng format**. Nó không khẳng định password không tồn tại, cũng không chứng minh bản ghi là bcrypt. Những tình huống có thể giống nhau:

- Database lưu bcrypt dạng bare `$2a$...` từ ứng dụng cũ.
- Column `password` thực ra chứa plaintext từ thời hệ thống không dùng encoder.
- Một migration xóa mất ký tự đầu hoặc nhập dữ liệu có khoảng trắng.
- Tài khoản từ nguồn LDAP/legacy scheme khác không dùng format `{id}...`.
- Đọc nhầm cột (ví dụ username/email thay cho verifier), nối chuỗi sai hoặc mapping sai.
- Một số bản ghi được tạo bởi `BCryptPasswordEncoder` trực tiếp, số khác từ `DelegatingPasswordEncoder`.

Không log full hash/token khi debug; thông tin hữu ích có thể là số lượng bản ghi, loại prefix được nhận diện, độ dài và một mã lỗi đã chuẩn hóa. Hash cũng là dữ liệu nhạy cảm vì có thể bị đoán mật khẩu offline nếu bị lộ.

### 4.2 Phân biệt id không có mapping và id bị cấm

`{sha256}...` không nhất thiết là “unknown” đối với factory mặc định, nhưng có thể bị **chính sách bảo mật nội bộ cấm**. Ngược lại `{external-kdf-v1}...` có thể là scheme mạnh trong một hệ thống khác nhưng app hiện chưa có decoder/mapping đúng; chưa được phép suy ra nó an toàn.

Để hệ thống chẩn đoán đúng, nên tách hai trạng thái:

1. **Unsupported format:** không biết id/metadata hoặc không biết đọc scheme một cách xác định.
2. **Disallowed format:** biết scheme/định dạng nhưng policy hiện hành không cho verify bằng cơ chế đó.

Cả hai đều phải dẫn tới **không cấp quyền đăng nhập** cho request thông thường, cho tới khi có quy trình xử lý phù hợp. Chỉ khác ở biện pháp khắc phục: chỉnh metadata/compatibility được kiểm soát, hoặc reset/migrate khỏi scheme bị cấm.

### 4.3 Kiểm nhanh theo từng lớp

1. **Dữ liệu:** `UserDetails.getPassword()` trả chính xác cột verifier nào? Có thể đã encode hai lần, bị trim/đổi encoding, thêm dấu cách hoặc mất prefix không?
2. **Cấu hình:** `PasswordEncoder` bean nào đang được `DaoAuthenticationProvider` thực tế sử dụng? Có custom manager/filter khác không?
3. **Định dạng:** prefix nằm từ ký tự đầu không? `id` có trong map không? Bcrypt body có đúng cú pháp không?
4. **Policy:** scheme đó được phép tạo mới, tạm verify để nâng cấp, hay bị từ chối?
5. **Nguồn dữ liệu:** có phân biệt theo tenant/identity provider/schema/version không? Cùng username ở hai tenant có thể lấy nhầm verifier.
6. **Ghi dữ liệu:** luồng register/reset/password-change đang dùng `encoder.encode(raw)` hay đang lưu raw/hardcode `{noop}`?
7. **Quan sát:** có rò encoder exception/stack trace cho client không? Có metric số login bị từ chối theo nhóm định dạng (không ghi raw secret) không?

## 5. Phân loại bản ghi và quyết định hành động

Bảng quyết định thực tế:

| Dạng verifier trong DB | Nhận định có thể | Cách xử lý khuyến nghị |
| --- | --- | --- |
| `{bcrypt}` + bcrypt hash đúng tham số được phép | Mapped, approved | Verify bằng bcrypt; kiểm `upgradeEncoding` nếu policy tăng work factor. |
| Bcrypt trần `$2a$...`, có provenance chắc chắn | Thiếu metadata `{bcrypt}` | Có thể bổ sung prefix **một cách có kiểm soát**, rồi xét nâng cost khi raw password được cung cấp hợp lệ. |
| Hash trần không rõ thuật toán | Không thể tự suy ra chính xác | Cô lập/đánh dấu cần kiểm; yêu cầu reset nếu không có phương án xác minh legacy được phê duyệt. |
| `{bcrypt}` nhưng body sai | Bị hỏng/corrupt | Không “đoán lại” body; fail closed, audit và reset theo quy trình. |
| `{BCRYPT}` hoặc id typo | Format metadata sai | Xác minh nguồn và bản chất verifier trước khi chuẩn hóa, không mapping rộng theo case tùy tiện. |
| `{noop}password` | Plaintext được gắn prefix | Không chấp nhận trong policy production; xử lý như credential compromise, bắt buộc reset/migrate theo kế hoạch an ninh. |
| `{sha256}...` hoặc MD5/SHA-1 nhanh, không muối | Hash yếu | Không dùng cho password auth bình thường nếu policy cấm; reset hoặc migration legacy bị giới hạn chặt theo quyết định an ninh. |
| Prefix lạ có scheme documented nhưng không được cài | Unsupported | Chỉ thêm verifier nếu được đánh giá/đồng ý; không fallback dùng một encoder bất kỳ. |
| Hash có prefix phù hợp nhưng cost quá thấp | Cần tăng work factor | Xác minh bằng scheme phù hợp rồi re-encode raw password sau login thành công, ghi atomic. |
| Prefix khác chuẩn do database migration lỗi | Integrity issue | Khôi phục từ nguồn tin cậy, kiểm bản ghi chịu ảnh hưởng, không sửa hàng loạt bằng regex thiếu bằng chứng. |

**Không nên dùng cùng một phản ứng cho mọi trường hợp.** Khi thuật toán thật sự đã được xác nhận là bcrypt, **thêm tiền tố** có thể là sửa metadata. Khi thuật toán yếu hoặc không rõ, **thêm tiền tố giả** không nâng cấp tính bảo mật và có thể tạo đường xác thực sai.

## 6. Cấu hình chặt: allowlist bcrypt, không fallback tự động

Một policy đơn giản có thể là:

- Dữ liệu lưu trữ hợp lệ cho password auth: chỉ `{bcrypt}` và body bcrypt.
- Hash mới: bcrypt với work factor do tổ chức đánh giá (mẫu dưới chọn 10 để demo; không khẳng định đây là giá trị tối ưu cho production).
- Không cho `{noop}`, `{sha256}`, id lạ và verifier thiếu prefix đăng nhập bình thường.
- Nếu hệ thống có kế hoạch migrate từ legacy: đó là **luồng riêng được ghi chính sách**, không phải fallback mặc định trong mọi request.
- Unknown/invalid format → authentication failure chung, không cấp quyền, không tự encode lại dữ liệu.

Để kiểm thô, có thể tạo strict delegate:

```java
PasswordEncoder bcrypt = new BCryptPasswordEncoder(10);

DelegatingPasswordEncoder delegate =
        new DelegatingPasswordEncoder(
                "bcrypt",
                Map.of("bcrypt", bcrypt));
```

Nếu gọi trực tiếp `delegate.matches(raw, stored)` với `stored` thiếu `{id}` hoặc id không mapped, nó có thể ném `IllegalArgumentException`. Để có phản hồi login thống nhất, một **policy adapter** nên kiểm format trước, dùng delegate để verify và thất bại an toàn khi dữ liệu sai. Không map fallback sang `NoOpPasswordEncoder`.

### 6.1 Tại sao không dùng setDefaultPasswordEncoderForMatches tùy tiện?

API `DelegatingPasswordEncoder.setDefaultPasswordEncoderForMatches(...)` thay cách xử lý id không mapped. Điểm nguy hiểm là **fallback encoder nhận nguyên chuỗi được lưu, có thể gồm cả `{id}...`**. Một fallback quá rộng có thể vô tình chấp nhận dữ liệu có prefix lạ hoặc tạo chính sách không kiểm soát, đặc biệt khi truyền nguyên bản sang một verifier tùy chỉnh.

Không cấu hình:

```java
// ANTI-PATTERN: minh họa lỗi chính sách, không chạy trong production.
delegate.setDefaultPasswordEncoderForMatches(
        NoOpPasswordEncoder.getInstance());
```

Dù mục tiêu là sửa lỗi `id=null`, dòng này làm mọi dữ liệu không mapped đi theo cơ chế so sánh plaintext. Với môi trường thật, hãy **phân loại bản ghi theo nguồn tin cậy**, cho phép đúng legacy scheme khi đã phê duyệt, và đặt ngày loại bỏ. Đừng sửa lỗi bằng cách “trong trường hợp không biết thì thử hết các encoders”.

### 6.2 Cấu hình chính sách khác với truy vấn SQL

Một `UserDetailsService` trả đúng hash trong DB, nhưng nếu `PasswordEncoder` có quá nhiều mapping thì một bản ghi `{noop}...` vẫn có thể được xác minh ở tầng authentication. Ngược lại, DB có hash bcrypt hợp lệ nhưng encoder bean chỉ nhận `{argon2}` sẽ từ chối. **Kho lưu trữ, cấu hình password policy và quá trình xác thực phải thống nhất**.

Với user thuộc nhiều tenant, hãy bảo đảm khớp đúng bản ghi account trước khi kiểm password; không được dựa vào việc encoder chấp nhận hash của tenant A rồi cấp principal thuộc tenant B.

## 7. Chương trình Java 17+ chạy được để thấy tất cả nhánh

Ví dụ dùng Spring Security Crypto 6.5.6, tạo bcrypt hash có salt ngẫu nhiên, rồi kiểm các trường hợp: approved, wrong password, bare bcrypt, bare bcrypt đã được xác minh và bổ sung prefix, id lạ, `noop`, body hỏng và work factor cũ. Không in password hash vào log; chỉ in các boolean ổn định.

### 7.1 Cấu trúc

```text
password-policy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/PasswordPolicyDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'password-policy-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.5.6'
}

application {
    mainClass = 'demo.PasswordPolicyDemo'
}
```

### 7.2 File Java đầy đủ

File `src/main/java/demo/PasswordPolicyDemo.java`:

```java
package demo;

import java.util.Map;

import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;

public final class PasswordPolicyDemo {

    private static final String RAW = "training-password-2026";

    private PasswordPolicyDemo() {
    }

    public static void main(String[] args) {
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder(10);

        // Chỉ cho phép bcrypt; không map noop/sha256.
        DelegatingPasswordEncoder strict =
                new DelegatingPasswordEncoder(
                        "bcrypt", Map.of("bcrypt", bcrypt));

        String current = strict.encode(RAW);
        String bare = bcrypt.encode(RAW);
        String lowerCost = new BCryptPasswordEncoder(4).encode(RAW);

        System.out.println("new-has-prefix="
                + current.startsWith("{bcrypt}"));

        System.out.println("new-matches="
                + approvedMatch(strict, RAW, current));

        System.out.println("wrong-password="
                + approvedMatch(strict, "wrong", current));

        System.out.println("bare-rejected="
                + !approvedMatch(strict, RAW, bare));

        // Chỉ minh họa trường hợp ĐÃ xác minh bare thực sự là bcrypt.
        System.out.println("verified-prefix-matches="
                + approvedMatch(strict, RAW, "{bcrypt}" + bare));

        System.out.println("unknown-id-rejected="
                + !approvedMatch(strict, RAW, "{madeup}value"));

        System.out.println("noop-rejected="
                + !approvedMatch(strict, RAW, "{noop}" + RAW));

        System.out.println("broken-body-rejected="
                + !approvedMatch(strict, RAW, "{bcrypt}not-a-hash"));

        System.out.println("old-cost-needs-upgrade="
                + strict.upgradeEncoding("{bcrypt}" + lowerCost));

        // Default behavior khi gọi delegate không qua policy guard.
        try {
            strict.matches(RAW, bare);
            System.out.println("unmapped-id-throws=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("unmapped-id-throws=true");
        }
    }

    private static boolean approvedMatch(
            DelegatingPasswordEncoder strict,
            String rawPassword,
            String storedHash) {

        // Không để id lạ / thiếu id rơi vào fallback.
        if (storedHash == null || !storedHash.startsWith("{bcrypt}")) {
            return false;
        }

        try {
            return strict.matches(rawPassword, storedHash);
        } catch (IllegalArgumentException badStoredFormat) {
            // Chỉ coi là không hợp lệ, không bao giờ cho qua.
            // Không ghi storedHash hoặc rawPassword vào log.
            return false;
        }
    }
}
```

**Giải thích từng tình huống:**

- `strict.encode(RAW)` tạo hash mới có `{bcrypt}`, phần hash thay đổi qua mỗi lần chạy do salt ngẫu nhiên.
- Raw password đúng với hash mới trả `true`; password sai trả `false`.
- Bcrypt trần `bare` **không được** policy guard chấp nhận; sau khi đã có bằng chứng rõ ràng rằng nó thực sự là bcrypt, việc gắn `{bcrypt}` giúp delegate định tuyến đúng. **Đoạn mã chỉ mô phỏng dữ liệu đã xác minh; không tự động sửa một DB thật.**
- `{madeup}...`, `{noop}...` và verifier sai body đều bị từ chối.
- `upgradeEncoding("{bcrypt}" + lowerCost)` báo hash có cost thấp hơn encoder được cấu hình, cần re-encode sau lần người dùng xác thực hợp lệ.
- Gọi `strict.matches(RAW,bare)` trực tiếp thể hiện hành vi ngoại lệ mặc định với id `null`. Nó được bắt riêng để demo, không biến ngoại lệ thành success.

### 7.3 Chạy và stdout chính xác

Nếu có Gradle wrapper:

```bash
./gradlew run --console=plain
```

Nếu chưa có wrapper nhưng đã cài Gradle tương thích:

```bash
gradle run --console=plain
```

Windows PowerShell dùng `.\gradlew.bat run --console=plain` khi có wrapper. Lệnh `javac PasswordPolicyDemo.java` **không đủ** nếu chưa thêm Spring Security Crypto vào classpath. Khi dùng Gradle, dependencies được giải từ Maven Central.

Phần **stdout từ chương trình Java** (không tính log tiến độ Gradle và cảnh báo riêng của logging implementation):

```text
new-has-prefix=true
new-matches=true
wrong-password=false
bare-rejected=true
verified-prefix-matches=true
unknown-id-rejected=true
noop-rejected=true
broken-body-rejected=true
old-cost-needs-upgrade=true
unmapped-id-throws=true
```

**Kiểm thử đáng tin** dựa vào boolean, không so sánh chuỗi bcrypt hash cụ thể vì salt ngẫu nhiên. Mốc cost `4` trong test chỉ để mô phỏng hash yếu; không khuyến nghị dùng cost thấp này cho mật khẩu thật.

## 8. Mẫu cấu hình Spring Boot: chặn id ngoài policy trước khi gọi provider

Trong ứng dụng Spring Boot 3.x / Spring Security 6.x, có thể cung cấp một `PasswordEncoder` bean áp dụng allowlist. **Đoạn dưới là một class cấu hình để ghép vào ứng dụng Boot đã có `UserDetailsService`, `SecurityFilterChain` và dependencies; nó không phải chương trình chạy độc lập chỉ bằng `javac`.**

```java
package demo;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordPolicyConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        DelegatingPasswordEncoder delegate =
                new DelegatingPasswordEncoder(
                        "bcrypt",
                        Map.of("bcrypt", new BCryptPasswordEncoder(12)));

        return new PasswordEncoder() {
            @Override
            public String encode(CharSequence rawPassword) {
                return delegate.encode(rawPassword);
            }

            @Override
            public boolean matches(
                    CharSequence rawPassword,
                    String encodedPassword) {
                if (encodedPassword == null
                        || !encodedPassword.startsWith("{bcrypt}")) {
                    return false;
                }
                try {
                    return delegate.matches(rawPassword, encodedPassword);
                } catch (IllegalArgumentException invalidStoredVerifier) {
                    return false;
                }
            }

            @Override
            public boolean upgradeEncoding(String encodedPassword) {
                // Khi scheme không thuộc policy, login thường bị
                // từ chối trước khi đến bước nâng cấp.
                if (encodedPassword == null
                        || !encodedPassword.startsWith("{bcrypt}")) {
                    return true;
                }
                return delegate.upgradeEncoding(encodedPassword);
            }
        };
    }
}
```

Tác dụng: provider đăng nhập username/password gọi `matches(raw, UserDetails.getPassword())`. Nếu hash thiếu prefix hoặc dùng `{noop}`, wrapper trả `false`; provider có thể chuyển thành lỗi authentication bình thường thay vì để `IllegalArgumentException` lộ ra không mong muốn. **Trả false không phải “đã sửa DB”**: phải có quy trình migration/reset riêng để user có credential lỗi vẫn có thể khôi phục tài khoản an toàn.

**Cẩn thận:** Wrapper chỉ là một lớp chính sách đơn giản; trong sản phẩm thật cần xác định cách xử lý null, chuỗi quá dài, malformed encoder body, CPU resource exhaustion, logging, rate limit, timing và các loại principal không dùng password. Nếu app có nhiều `AuthenticationManager`/`SecurityFilterChain`, phải xác minh bean đúng được gắn vào `DaoAuthenticationProvider` đang xử lý request. Không giả định thêm bean là mọi manager đều dùng cùng policy.

### 8.1 Vì sao không bắt toàn bộ Exception rồi trả success?

Không bao giờ viết:

```java
// SAI: ví dụ anti-pattern nghiêm trọng.
try {
    return passwordEncoder.matches(raw, stored);
} catch (Exception ignored) {
    return true; // Tuyệt đối không làm như vậy.
}
```

Khi dữ liệu lỗi, nguyên tắc là **fail closed**. Để tránh phản hồi 500 không cần thiết, bắt lỗi định dạng tại boundary đã kiểm soát và chuyển thành từ chối xác thực; log loại lỗi đã làm sạch cho vận hành. Không thay kiểm password bằng việc so sánh raw string với stored value một cách tùy ý.

### 8.2 Có nên ẩn ngoại lệ với client?

Có thể phản hồi HTTP 401 hoặc thông báo đăng nhập chung cho user, không tiết lộ rằng account đang dùng hash yếu/id không biết. Nội bộ cần metric và remediation route. Không nên trả full stack trace hay verifier trong HTTP body, email, logs. Cũng không nên biến mọi lỗi truy cập DB thành “mật khẩu sai” trong audit vì sẽ che sự cố vận hành; phân biệt diagnostic nội bộ với thông báo công khai.

## 9. Sửa hash bcrypt thiếu tiền tố: chỉ khi đã biết chắc

Spring Security docs nêu ví dụ chuyển:

```text
Trước: $2a$10$........
Sau:   {bcrypt}$2a$10$........
```

**Bổ sung `{bcrypt}` không thay đổi thuật toán hay cost**. Nó chỉ làm đúng metadata để `DelegatingPasswordEncoder` chọn được `BCryptPasswordEncoder`. Với bcrypt đã được tạo đúng, sau khi xác minh nguồn gốc, việc thêm prefix có thể khôi phục khả năng kiểm password mà không cần raw password.

### 9.1 Điều kiện tiên quyết

Không chạy một lệnh `UPDATE ... CONCAT('{bcrypt}', password_hash)` lên mọi hàng chỉ vì hash “trông giống bcrypt”. Chỉ cân nhắc chuyển khi:

1. Xác nhận schema/ứng dụng cũ đã sử dụng `BCryptPasswordEncoder` trực tiếp hoặc một encoder tương thích **cho đúng tập tài khoản**.
2. Kiểm mẫu cấu trúc hash (variant như `$2a$`/`$2b$`/`$2y$` theo khả năng hỗ trợ của thư viện) và độ dài/định dạng; dữ liệu không bị trim/corrupt; nhận diện format không phải bằng chứng duy nhất.
3. Xác định account IDs/tenant/dataset đúng và loại bản ghi đã có prefix hoặc bản ghi khác scheme.
4. Đối chiếu khả năng login bằng mật khẩu test của dữ liệu đã xác minh trong môi trường an toàn. Không log hoặc xuất raw password.
5. Backup có kiểm soát, transaction/rollback plan và test trên bản sao tách biệt.
6. Thay đổi đúng một lần, có audit và kiểm tổng số bản ghi trước/sau; tránh double prefix `{bcrypt}{bcrypt}...`.
7. Kiểm login và `upgradeEncoding` sau migration; nếu cost yếu, lên kế hoạch rehash với raw password ở lần xác thực sau.

### 9.2 SQL minh họa có điều kiện, không phải lệnh chạy hàng loạt mù

Giả sử tổ chức đã có cột `password_scheme` tin cậy từ migration cũ và xác nhận rằng các hàng `BARE_BCRYPT_V1` thực sự là bcrypt:

```sql
-- SQL dạng PostgreSQL minh họa; cần review/migrate tool,
-- không chạy trước khi đã kiểm chứng provenance/dataset.
UPDATE account_credentials
SET password_hash = '{bcrypt}' || password_hash,
    password_scheme = 'BCRYPT_PREFIXED'
WHERE password_scheme = 'BARE_BCRYPT_V1'
  AND password_hash NOT LIKE '{%'
  AND password_hash LIKE '$2%';
```

Câu lệnh chỉ thể hiện **sử dụng metadata tin cậy và điều kiện idempotency**. Điều kiện `LIKE '$2%'` không đủ để xác minh mật mã; không thực hiện nếu không chắc encoder gốc. Production cần thêm account/tenant scoping, kiểm affected row count, transaction, kiểm backup và ngoại lệ; cùng với format validation đã được test. SQL concatenation/escaping phụ thuộc database dialect.

### 9.3 Tại sao không tự thêm tiền tố cho SHA-256/MD5?

Một hash digest nhanh gắn `{bcrypt}` vẫn không phải bcrypt, nên bcrypt verifier từ chối. Gắn `{sha256}` có thể khiến factory default verify được scheme yếu, trái chính sách cấm; dù người dùng login thành công, hash vẫn yếu cho tới khi được rehash bằng raw password. Với scheme thật sự bị cấm, quy trình reset/reenrollment hoặc migration có hạn và kiểm soát riêng mới giải quyết đúng.

## 10. Nâng cấp hash sau xác thực thành công

Có hai trường hợp phải phân biệt:

- **Format repair**: hash bcrypt tốt nhưng thiếu `{bcrypt}`. Sửa metadata có thể không cần raw password, sau khi xác minh provenance.
- **Cryptographic upgrade**: hash sử dụng cost/thuật toán dưới policy hiện hành. Muốn nâng cấp thật, cần **raw password hợp lệ** tại một sự kiện authentication/đổi mật khẩu, sau đó chạy `encode(raw)` bằng scheme mới và ghi hash mới.

### 10.1 Vai trò upgradeEncoding()

`PasswordEncoder.upgradeEncoding(encodedPassword)` cho biết verifier **nên được encode lại** theo khả năng/tiêu chí của encoder. Với `DelegatingPasswordEncoder`, id cũ khác `idForEncode` hoặc tham số của encoder đích có thể cho kết quả cần upgrade. **Đây chỉ là tín hiệu**, không tự ghi database. Một hash có id không được chấp nhận cũng có thể báo cần upgrade, nhưng login của nó không được cho phép chỉ để đi đến bước nâng cấp.

Một flow an toàn:

```text
1. Client gửi username + raw password qua HTTPS.
2. Account lookup lấy đúng password verifier và trạng thái từ server.
3. Kiểm policy legacy/approved scheme (không nhận scheme lạ).
4. matches(raw, storedVerifier) phải thành công.
5. Nếu upgradeEncoding(storedVerifier) hoặc policy bắt buộc:
     newVerifier = encoder.encode(raw)  // scheme được phép hiện hành
     cập nhật có điều kiện/transaction, không ghi đè thay đổi đồng thời
6. Login thành công với principal/authorities tin cậy.
7. Xóa/giảm vòng đời raw password, audit metadata đã lọc.
```

Nếu verifier sai hoặc scheme cấm, **không rehash dựa trên raw password người dùng vừa thử** rồi tự tạo một account login thành công. Một lần gõ mật khẩu không chứng minh quyền sở hữu nếu chưa được xác minh bởi một scheme đã được tin cậy.

### 10.2 UserDetailsPasswordService trong Spring Security

`DaoAuthenticationProvider` hỗ trợ `setUserDetailsPasswordService(UserDetailsPasswordService)`. Khi cấu hình đúng và xảy ra nâng cấp hợp lệ, service này có thể nhận **new encoded password** để lưu. Giao diện rút gọn:

```java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(
            UserDetails user,
            String newPassword);
}
```

Tên tham số `newPassword` trong hợp đồng này thường là **giá trị đã encode**, không phải raw password. Phải kiểm hợp đồng phiên bản/provider thực tế; không tự `encoder.encode(newPassword)` thêm lần nữa khi lưu, vì sẽ double-hash làm login kế tiếp thất bại.

Cấu hình minh họa cho Spring Security 6.x (cần các bean/service/repository thật):

```java
@Bean
DaoAuthenticationProvider daoAuthenticationProvider(
        UserDetailsService users,
        PasswordEncoder passwordEncoder,
        UserDetailsPasswordService passwordUpdates) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(passwordEncoder);
    provider.setUserDetailsPasswordService(passwordUpdates);
    return provider;
}
```

Đây **không phải file Java độc lập**; cần import annotation, class, cấu hình SecurityFilterChain và implementation cập nhật DB có transaction. Chỉ khai báo `UserDetailsPasswordService` không bảo đảm tất cả authentication paths sẽ nâng cấp: provider phải dùng đúng encoder/service, người dùng phải xác thực thành công, scheme phải qua policy và cơ chế hiện hành phải thực sự gọi upgrade.

### 10.3 Cập nhật có điều kiện để không ghi đè password reset mới

Trong kho tài khoản có nhiều request đồng thời, tránh tình huống:

1. Login A đọc hash cũ.
2. Người dùng reset password ở request B và lưu hash mới.
3. Login A hoàn thành rồi vô tình ghi đè hash mới bằng kết quả rehash từ password cũ.

Cách giải quyết là dùng **compare-and-swap** hoặc optimistic locking theo version của record, kiểm affected row count:

```sql
UPDATE accounts
SET password_hash = :new_encoded,
    password_version = password_version + 1
WHERE account_id = :account_id
  AND password_hash = :expected_old_encoded
  AND password_version = :expected_version;
```

Nếu số row cập nhật = 0, phiên/record đã đổi; **không ghi đè**, tái đánh giá authentication/session theo chính sách. Khi chuyển credential, cân nhắc thu hồi phiên/token cũ và thống nhất auth version. Không log raw password hay full verifier trong audit.

### 10.4 Không giữ scheme yếu vĩnh viễn chỉ vì “đã thêm đường migration”

Một kế hoạch migration cần đủ:

- Điều kiện bật legacy verifier và ai phê duyệt.
- Tập account/tenant/scheme nào được phép, được gắn metadata server-side.
- Rate limit, monitoring, chống enumeration và phản ứng khi có brute-force.
- Thời hạn kết thúc hỗ trợ scheme yếu, tiến độ rehash/reset, cơ chế liên lạc tới user.
- Không cho phép scheme legacy cho account mới hoặc password reset mới.
- Kiểm chứng bằng metric: số account theo scheme, số upgrade thành công/thất bại, số còn cần reset, tỉ lệ login failure.
- Cuối kỳ **gỡ mapping legacy khỏi runtime**, xóa code fallback không còn dùng và xác nhận không có account bị bỏ sót.

## 11. Bản ghi không rõ nguồn hoặc thuật toán bị cấm: buộc reset khi cần

Không phải mọi hash đều có khả năng “nâng cấp âm thầm” khi user login:

- Nếu hash không rõ thuộc scheme nào, **không có một verifier đáng tin** để kiểm raw password.
- Nếu hash là plaintext/`{noop}` trong database production, phải xử lý như dữ liệu bí mật có nguy cơ lộ; chỉ thay text thành một prefix khác không khắc phục tổn thất bảo mật.
- Nếu hash là MD5/SHA-1/digest nhanh thuộc nhóm đã cấm, việc mở đường login bằng nó có thể trái policy; cần quyết định của chủ sở hữu an ninh về reset/transition có kiểm soát.
- Nếu body bị cắt/truncated, không thể khôi phục hash đúng từ chuỗi lỗi; cần phục hồi bản backup an toàn hoặc reset password.
- Nếu user thuộc IdP bên ngoài, ứng dụng có thể **không được lưu password verifier cục bộ**. Không tạo password giả rồi bật noop để “cho giống account thường”.

### 11.1 Reset không được thành con đường chiếm account

Flow reset phải xác minh người yêu cầu sở hữu account theo yếu tố độc lập và phù hợp rủi ro; dùng token một lần, entropy cao, hạn dùng ngắn, chống brute-force/replay, giới hạn rate, tránh enumeration, và TLS. Không gửi raw password qua email, không gửi hash DB cho người dùng, không dùng “câu hỏi bí mật” yếu làm yếu tố xác minh duy nhất nếu chính sách không cho.

Khi reset thành công:

1. Encode password mới bằng scheme hiện hành, lưu prefix chuẩn.
2. Tăng password/security version nếu chính sách yêu cầu revoke phiên cũ.
3. Thu hồi session/refresh/remember-me tokens liên quan theo chính sách.
4. Audit actor, thời điểm và account ID mà không log token/password.
5. Đảm bảo bản ghi không còn thuộc nhóm legacy sai định dạng; cập nhật source metadata và metric.

### 11.2 Không suy luận duy nhất từ độ dài hash

Một chuỗi 64 ký tự hex có thể là SHA-256, HMAC hoặc dữ liệu khác; cùng độ dài không khẳng định được thuật toán hay có salt/pepper. Bcrypt có dấu hiệu phiên bản và cost nhưng cũng cần provenance. Không tự chạy nhiều encoder cho đến khi một encoder khớp nếu không có boundary tin cậy; việc đó vừa mở đường downgrade, vừa tốn CPU và khó audit.

## 12. Tích hợp với UserDetailsService và DaoAuthenticationProvider

Một request username/password bình thường có đường đi:

```text
Login request (username + raw password)
  |
  v
AuthenticationFilter
  |
  v
AuthenticationManager / ProviderManager
  |
  v
DaoAuthenticationProvider
  +--> UserDetailsService.loadUserByUsername()
  |         |
  |         +--> DB account: username, encoded password, status, authorities
  |
  +--> PasswordEncoder.matches(raw, stored)
           |
           +--> id approved + body match: true
           +--> id approved + wrong password: false
           +--> id absent/unapproved: fail closed, migration/reset flow
  |
  v
Authentication success / authentication failure
```

**Điểm quan trọng:** `UserDetailsService` không nên tự verify raw password; nó trả verifier đã lưu. `DaoAuthenticationProvider` chịu trách nhiệm kiểm credential theo `PasswordEncoder`. Một custom encoder “khắc phục định dạng” ở application-wide scope cần được review kỹ vì ảnh hưởng tới mọi người dùng của provider đó, kể cả account của tenant khác.

### 12.1 Sai cấu hình bean và đường manager

Một nguyên nhân phổ biến khác của lỗi là ứng dụng đã khai báo strict `PasswordEncoder` bean nhưng lại tạo `DaoAuthenticationProvider` thủ công dùng encoder khác, hoặc có hai `SecurityFilterChain` với hai authentication managers. Muốn chẩn đoán đúng, cần kiểm:

- Filter nào tạo `UsernamePasswordAuthenticationToken`?
- Manager nào đang được gọi?
- Provider nào hỗ trợ loại token đó?
- Provider dùng `PasswordEncoder` instance nào?
- `UserDetailsService` có lấy đúng record/schema/tenant không?
- Password update pipeline có dùng cùng format/policy với login pipeline không?

Không suy ra “đã có bean PasswordEncoder” nghĩa mọi đường login đều dùng bean đó.

### 12.2 Tránh cho encoded password đi ra response hoặc log

`Authentication.getPrincipal()` sau username/password login thường chứa `UserDetails`. Đừng serialize nguyên `UserDetails` ra JSON, vì `getPassword()` có thể trả verifier nếu chưa bị erase. Dùng response DTO allowlist: account ID, display name và authorities cần thiết; giữ hash và raw credential ở ranh giới bảo mật. `ProviderManager` có cơ chế erase credentials nhưng không chứng minh đã xóa hết mọi bản sao secret trong DB cache/heap/log.

## 13. Ranh giới giữa “thiếu prefix” và “thiếu mật khẩu”

Một `UserDetails` có `getPassword()==null` có thể phản ánh account đăng nhập bằng OIDC/passkey, chưa kích hoạt password auth, hoặc dữ liệu bị lỗi. **Không tự sửa bằng cách chọn NoOpPasswordEncoder hoặc đặt hash rỗng**.

Nên có chính sách rõ:

- Account local password: verifier phải có format được chấp nhận, không được null/rỗng.
- Account external-only: password login không được hỗ trợ; chuyển hướng cơ chế IdP/passkey đã cấu hình.
- Account pending reset: password login bị từ chối cho tới khi reset được xác minh.
- Account imported legacy: có trạng thái migration riêng (verified bare bcrypt/unknown/blocked) thay vì đoán từ mọi request.
- Account locked/disabled: vẫn phải kiểm trạng thái, không cho qua vì password khớp.

Việc data model tách `credential_type` và `credential_scheme` khỏi `password_hash` có thể giúp migration khi nguồn dữ liệu rõ. Nhưng metadata phải được thiết lập/duy trì từ **nguồn có thẩm quyền**, không từ client tự khai.

## 14. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for the id "null"` | Thiếu `{id}` hoặc cấu trúc verifier lỗi | Kiểm nguồn/format; bổ sung prefix chỉ với tập hash đã chứng minh, hoặc reset. |
| `There is no PasswordEncoder mapped for the id "sha256"` | Strict encoder không map scheme đó | Xem policy; không thêm mapping chỉ để làm lỗi biến mất nếu scheme bị cấm. |
| `BadCredentialsException` | Wrong raw password hoặc policy adapter trả false vì scheme lỗi | Chẩn đoán nội bộ riêng, phản hồi client chung; kiểm verifier và status. |
| Login cũ hoạt động sau khi chuyển từ strict sang factory default | Factory chứa mappings legacy ngoài allowlist | Xây strict map/policy, test bảng danh sách id bị cấm. |
| Login thất bại sau khi sửa prefix | Hash body không đúng, format bị cắt hoặc hash scheme không phải bcrypt | Khôi phục dữ liệu đúng từ nguồn tin cậy hoặc reset, không bọc thêm prefix mới. |
| Hash có `{bcrypt}` nhưng cost yếu | Prefix đúng, work factor thấp | Dùng `upgradeEncoding` và re-encode sau xác thực thành công. |
| Hash mới thành `{bcrypt}{bcrypt}$2a$...` | Migrations chạy lặp hoặc double-prefix | Guard idempotency, kiểm số rows, rollback/correct theo provenance. |
| Password mới không khớp sau cập nhật | Double-hash hoặc lưu raw/newPassword sai hợp đồng | Phân biệt `updatePassword` nhận encoded verifier và `PasswordEncoder.encode(raw)`. |
| Một số tenant login được, tenant khác lỗi | Khác schema/encoder/namespace, lookup nhầm record | Kiểm account/tenant-scoped store và chính sách migration riêng từng dataset. |
| Reset password nhưng phiên cũ còn tồn tại | Reset hash không tự invalidate sessions/JWT | Xem password/auth version và revoke/expiry policy. |
| API trả HTTP 500 cho tài khoản có hash sai format | `IllegalArgumentException` chưa được xử lý ở boundary | Fail closed bằng adapter/handler phù hợp, audit nội bộ, không lộ verifier. |
| Legacy map được bật vĩnh viễn | Không có kết thúc migration | Đặt sunset date, thống kê còn tồn, buộc reset và gỡ legacy mapping. |

### “Lỗi null id” không có nghĩa phải sửa code ngay

Có thể code mới hoàn toàn đúng, còn database chứa dữ liệu không theo hợp đồng. Nếu data provenance rõ, **sửa dữ liệu** có kiểm soát sẽ phù hợp hơn nới lỏng encoder. Nếu dữ liệu không rõ, **không nên làm mọi giá để login bằng được**; coi đó là một lỗi toàn vẹn dữ liệu hoặc cần reset.

## 15. Kiểm thử bảo mật và tính đúng đắn

| Test | Kết quả đúng |
| --- | --- |
| Hash mới tạo bằng `encode` | Có `{bcrypt}`, body hợp lệ, đủ cost theo policy. |
| Password đúng với hash mới | `matches` true. |
| Password sai với hash mới | False, không cấp authentication. |
| Bare bcrypt chưa migrate | Login thường bị chặn, không thử no-op. |
| Bare bcrypt đã xác minh và bổ sung prefix | Matches đúng, không thay đổi raw secret. |
| Id lạ `{madeup}` | Bị từ chối, không gọi fallback yếu. |
| Id `{noop}` trong production | Bị từ chối theo allowlist. |
| Id `{sha256}` trong strict map | Bị từ chối, dù factory có thể nhận mapping tương thích. |
| Id case sai `{BCRYPT}` | Bị từ chối, trừ khi có migration metadata được kiểm soát. |
| `{bcrypt}` nhưng body không hợp lệ | Bị từ chối; không chuyển sang encoder khác. |
| Prefix bị lặp `{bcrypt}{bcrypt}...` | Không được lặng lẽ “thử lần hai”. |
| Cost bcrypt cũ thấp | `upgradeEncoding` phát hiện cần nâng cấp; nâng cấp sau login thành công. |
| Hash không rõ nguồn | Không tự đoán scheme, chuyển reset/forensic theo policy. |
| `UserDetailsPasswordService` cập nhật mật khẩu | Ghi encoded verifier đúng một lần, CAS/transaction an toàn. |
| Hai login/reset đồng thời | Không ghi đè hash mới bằng hash rehash từ phiên cũ. |
| Thay thuật toán policy | Không có đường downgrade; account mới dùng scheme hiện hành. |
| Failure message public | Không rò account existence, stored hash, encoder map hay nội dung lỗi nội bộ. |
| Logging | Không chứa raw password, encoded hash, bearer token hay thông tin bí mật không cần thiết. |
| Tạo tài khoản mới sau migration | Không sản sinh bare hash, `{noop}` hay scheme đã cấm. |
| Disabled/locked account có hash đúng | Vẫn không login được; format đúng không bỏ qua account status. |
| Cache UserDetails có hash cũ | Khi nâng cấp/reset, cache bị invalidate/cập nhật đúng. |
| Sau sunset date | Mapping legacy bị gỡ và toàn bộ account còn lại được xử lý. |

**Kiểm thử dữ liệu migration không chỉ đếm số row.** Hãy có sample xác minh đúng nguồn, test login đúng/sai, dữ liệu bị corrupt, concurrent update và hành vi provider qua HTTP. Với đa tenant, kiểm account IDs/namespace, không chỉ username. Với password hashing adaptive, kiểm latency dưới tải thật để không tạo DoS khi tăng cost quá cao.

## 16. Các anti-pattern cần tránh

### 16.1 Bật NoOpPasswordEncoder để nhanh hết lỗi

```java
// SAI trong production
PasswordEncoder encoder = NoOpPasswordEncoder.getInstance();
```

Việc này khiến hệ thống kỳ vọng plaintext, làm hỏng chính sách lưu password một chiều. Có thể dùng các API tương thích trong tài liệu để demo/migration được kiểm soát, nhưng **không chọn no-op làm chiến lược chữa lỗi production**.

### 16.2 Dùng fallback cho mọi prefix không biết

```java
// SAI: coi mọi trường hợp không hiểu format đều là legacy.
delegate.setDefaultPasswordEncoderForMatches(someWideFallback);
```

Không có bằng chứng scheme đó đã được phép. Fallback có thể mở rộng acceptance ngoài ý định; dùng allowlist theo scheme và source provenance thay vì “thử xem có khớp không”.

### 16.3 Thêm {bcrypt} cho tất cả chuỗi không có prefix

```text
SAI:
  if (!hash.startsWith("{")) {
      hash = "{bcrypt}" + hash;
  }
```

Hàng thiếu prefix có thể là plaintext, MD5, SHA-1 hoặc bị hỏng. Thêm nhãn sai không biến dữ liệu thành bcrypt và có thể che lỗi dữ liệu. Chỉ sửa khi biết chắc source algorithm và test.

### 16.4 Băm lại chính chuỗi hash như raw password

```java
// SAI: encodedPassword không phải rawPassword.
String bad = encoder.encode(userDetails.getPassword());
```

Đây là **hash của hash**, không phải verifier của mật khẩu người dùng nhập. Hãy encode raw secret sau khi đã xác thực hợp lệ/đổi password, và không double-hash tham số `newPassword` mà `UserDetailsPasswordService` đã nhận.

### 16.5 Chặn cả login mới dù format tốt chỉ vì migration chưa hoàn chỉnh

Một policy strict đúng vẫn cần chiến lược vận hành không làm mất toàn bộ quyền truy cập của user hợp lệ. Khi batch có bare bcrypt đã chứng minh, có thể sửa metadata offline an toàn theo tập xác định; khi scheme cấm/unknown, có recovery/reset flow chống enumeration. **Khả dụng không cho phép bỏ xác thực**, nhưng tính phục hồi cũng cần được thiết kế.

## 17. Bài tập tự kiểm tra và đáp án

**Câu 1.** Spring Security báo `id "null"` cho hash bắt đầu bằng `$2a$...`. Có chắc phải bật `NoOpPasswordEncoder` không?

**Đáp án:** Không. Hash có dấu hiệu bcrypt trần thiếu `{bcrypt}`. Phải xác minh nguồn gốc và định dạng; nếu chứng minh đúng, bổ sung prefix có kiểm soát. `NoOp` là sai mục đích.

**Câu 2.** Database lưu `{sha256}...`; `PasswordEncoderFactories` đọc được, nhưng policy cấm digest nhanh. Có nên giữ mapping để người dùng không bị ảnh hưởng?

**Đáp án:** Không được tự quyết định bỏ qua policy. Cần phương án reset hoặc migration legacy có thời hạn được chấp thuận; encode mới bằng scheme mạnh và gỡ mapping cũ. “Có mapping” không đồng nghĩa “được phép”.

**Câu 3.** Có thể chuyển toàn bộ MD5 hash sang bcrypt bằng cách gọi `encoder.encode(md5Hash)` mà không cần người dùng nhập mật khẩu không?

**Đáp án:** Không thể coi kết quả là bcrypt của raw password. Nó chỉ hash một verifier cũ, khiến semantics khác và có thể tạo cơ chế yếu. Cần raw password được xác thực hoặc reset theo chính sách.

**Câu 4.** `{bcrypt}` + hash bcrypt cost 4 có còn cần upgrade không?

**Đáp án:** Có thể. Prefix đúng không chứng minh cost đáp ứng yêu cầu; `upgradeEncoding` và policy work factor xác định có cần rehash sau khi raw password được xác minh thành công.

**Câu 5.** Sau migration một hàng thành `{bcrypt}$2a$...`, app vẫn báo password sai. Có nên tự thử tất cả encoders khác rồi chọn cái trả true?

**Đáp án:** Không. Kiểm xem hash body có bị cắt/chỉnh sửa, encoder gốc có thật là bcrypt, migration đã double-prefix hay đọc nhầm account. Không tạo fallback đa thuật toán không kiểm soát.

**Câu 6.** Khi `UserDetailsPasswordService.updatePassword(user,newPassword)` được gọi, có cần encode `newPassword` một lần nữa không?

**Đáp án:** Không nếu provider đã đưa **encoded verifier mới** theo hợp đồng. Double-hash gây thất bại ở lần login sau. Hãy lưu chính xác và dùng update có điều kiện/transaction.

**Câu 7.** Vì sao cần khóa cập nhật có điều kiện khi rehash sau login?

**Đáp án:** Login và password reset có thể chạy đồng thời; nếu không dùng compare-and-swap/version, rehash từ password cũ có thể ghi đè hash mới từ reset. Nếu update thất bại do record đã đổi, cần xử lý theo chính sách, không cố ghi đè.

**Câu 8.** Bật fallback trả `false` cho id lạ có làm dữ liệu được migrate chưa?

**Đáp án:** Không. Nó chỉ biến trường hợp định dạng sai thành thất bại an toàn; database vẫn cần sửa, migration hoặc reset.

**Câu 9.** Một người dùng đăng nhập được với `{noop}password` vì library mặc định có mapping. Như vậy hash đó được tổ chức phê duyệt chưa?

**Đáp án:** Chưa. Mapping cho mục tiêu tương thích/demo không chứng minh policy cho phép; cần cấu hình strict và kiểm data/source.

**Câu 10.** Sau đổi password sang bcrypt mới, session/JWT cũ có tự mất hiệu lực không?

**Đáp án:** Không mặc định. Vòng đời session, refresh token, access token có thể độc lập; nếu chính sách yêu cầu revoke khi đổi password thì phải cài rõ version/session/token invalidation.

## 18. Checklist triển khai production

1. **Kiểm kê:** thống kê bản ghi theo prefix/schema/dataset mà không xuất hash thô; xác định chủ sở hữu và provenance của thuật toán.
2. **Policy:** định nghĩa scheme tạo mới, scheme tạm verify, scheme cấm và tham số cost tối thiểu; có phê duyệt an ninh.
3. **Strict encoder:** `DelegatingPasswordEncoder` với allowlist thực sự; tránh mapping `noop` hoặc legacy yếu ngoài nhu cầu đã kiểm soát.
4. **Error handling:** id thiếu/unknown/malformed phải fail closed, public response chung, metric nội bộ không lộ credential.
5. **Data migration:** nếu chỉ thiếu metadata, sửa đúng tập và có backup/transaction/idempotency/audit; không sửa mọi row mù.
6. **Crypto migration:** chỉ rehash sau xác thực raw password thành công hoặc reset an toàn; không encode hash như raw.
7. **Update concurrency:** CAS/optimistic locking ngăn login rehash ghi đè password reset, xác nhận affected rows.
8. **Account state:** enabled/locked/expired và tenant identity vẫn được kiểm; việc hash hợp lệ không bỏ qua account policy.
9. **Credential lifecycle:** rotate/revoke session, remember-me, refresh grants và access tokens theo threat model khi reset.
10. **Security testing:** unknown id, uppercase id, double prefix, body bị lỗi, salt/cost thấp, sai password, concurrent resets, bút toán migration.
11. **Performance:** đo adaptive hashing cost và giới hạn tần suất login dưới tải; không tăng cost gây nghẽn CPU không dự báo.
12. **Cleanup:** đặt sunset date legacy, gỡ fallback và mã cũ, ghi nhận số tài khoản còn phải reset và đánh giá hậu triển khai.

## 19. Nguồn chính thức và đọc tiếp

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): định dạng `{id}encodedPassword`, cách tạo encoder, lỗi `id=null`, hướng thêm prefix với bcrypt đã biết, các thuật toán và lưu ý NoOp.
- [Spring Security — DelegatingPasswordEncoder Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): constructor, `matches`, `upgradeEncoding` và `setDefaultPasswordEncoderForMatches`.
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, `upgradeEncoding`.
- [Spring Security — PasswordEncoderFactories](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/crypto/factory/PasswordEncoderFactories.html): mapping factory và scheme encode mặc định theo phiên bản.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): cách xác minh password từ `UserDetailsService`.
- [Spring Security — DaoAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): cấu hình `PasswordEncoder`, `UserDetailsPasswordService` và provider.
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): API cập nhật encoded verifier khi nâng cấp.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): password hashing, salt/work factor, migration và rủi ro của fast hashes.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): quy trình reset chống enumeration/replay.

**Ghi nhớ:** **Lỗi thiếu `{id}` là vấn đề định dạng/verifier cần xác định, không phải lý do bỏ kiểm mật khẩu.** Prefix đúng giúp chọn đúng encoder nhưng **không tự cải thiện sức mạnh hash**. Với thuật toán bị cấm hoặc không xác định, hãy fail closed và xử lý bằng migration có kiểm soát hoặc reset. Chỉ nâng cấp mật mã thực sự sau khi có raw password được xác thực hoặc qua recovery an toàn; bảo đảm mọi hash mới tuân policy và không còn đường downgrade.