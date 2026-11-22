# Chuẩn hóa username, email và chính sách phân biệt chữ hoa, chữ thường

## 1. Vì sao một tài khoản cần chính sách định danh rõ ràng?

Trong hệ thống có Spring Security, người dùng có thể nhập `Lan`, `lan`, `LAN`, ` Lan ` hoặc một địa chỉ như `Sales@Example.COM` để đăng nhập. Nếu màn hình đăng ký, cơ sở dữ liệu, `UserDetailsService` và trang đăng nhập **xử lý các chuỗi ấy theo những quy tắc khác nhau**, ứng dụng dễ phát sinh lỗi: một người không đăng nhập được dù đúng mật khẩu, nhiều tài khoản dùng tên trông như nhau, kiểm tra trùng không nhất quán hoặc liên kết nhầm danh tính.

**Chuẩn hóa định danh (identifier normalization)** là quá trình áp dụng một quy tắc đã công bố để tạo **khóa so sánh ổn định** từ dữ liệu người dùng nhập. **Phân biệt chữ hoa/chữ thường (case sensitivity)** là một quyết định của mô hình danh tính, phải được nhất quán trong toàn bộ vòng đời tài khoản: đăng ký, đăng nhập, tìm kiếm, cập nhật, liên kết danh tính, kiểm tra tính duy nhất và migration.

Một thiết kế tốt thường tách:

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| `user_id` | `4f2d...` hoặc ID số do hệ thống cấp | Khóa nội bộ ổn định, dùng cho foreign key và phân quyền. |
| `username_display` | `Lan_08` | Giữ cách viết người dùng chọn, nếu sản phẩm muốn hiển thị như vậy. |
| `username_key` | `lan_08` | Tra cứu và ràng buộc duy nhất theo chính sách username. |
| `email_original` | `Sales@Example.COM` | Địa chỉ người dùng cung cấp để xác minh/liên lạc; giữ nguyên phần local. |
| `email_lookup_key` | `Sales@example.com` | Một khóa tìm kiếm email theo chính sách có chủ đích; không mặc nhiên phải viết thường toàn bộ email. |
| `email_verified_at` | Thời điểm xác nhận quyền kiểm soát email | Phân biệt email được khai báo và email đã xác minh. |

Không nhất thiết mọi ứng dụng đều phải có đủ tất cả các cột. **Điều bắt buộc là thống nhất quy tắc**: đâu là khóa định danh, đâu là thông tin hiển thị/liên hệ, và chuỗi nào được dùng trong truy vấn tìm tài khoản.

Trong Spring Security, `UserDetailsService.loadUserByUsername(String username)` **không áp đặt chung một chính sách phân biệt hoa/thường**. Theo hợp đồng API, implementation có thể tìm kiếm có phân biệt hoặc không phân biệt chữ hoa, chữ thường; `UserDetails` trả về thậm chí có username khác kiểu chữ với tham số được yêu cầu. Chính sách thực tế thuộc về user store/adapter và dữ liệu của ứng dụng.

## 2. Ba hành động thường bị gọi chung là “chuẩn hóa”

Phải phân biệt ba bước, vì nhầm lẫn có thể gây mất dữ liệu hoặc gộp nhầm tài khoản:

1. **Validation**: xác định dữ liệu được chấp nhận. Ví dụ username chỉ gồm các ký tự ASCII `a-z`, chữ số, dấu chấm, gạch dưới, gạch ngang; email demo chỉ nhận một tập cú pháp đơn giản.
2. **Canonicalization**: đưa những chuỗi được xem **tương đương theo chính sách đã chọn** về cùng khóa. Ví dụ `Lan_08` và `LAN_08` đều có `username_key=lan_08` khi username được quy định không phân biệt hoa/thường.
3. **Presentation/preservation**: lưu dữ liệu nguyên bản có ích cho giao diện hoặc trao đổi với hệ thống bên ngoài. Ví dụ giữ `Sales@Example.COM` làm email gốc thay vì tự động biến thành `sales@example.com`.

Các phép biến đổi có thể tạo **va chạm (collision)**. Trước khi chuẩn hóa, `Lan` và `lan` là hai chuỗi khác nhau. Sau khi chuẩn hóa theo chính sách không phân biệt hoa/thường, chúng trở thành **một khóa**. Đây là hành vi mong muốn cho đăng ký mới nếu hệ thống quy định username không phân biệt case, nhưng là vấn đề lớn nếu dữ liệu cũ đã có **hai tài khoản khác nhau**.

**Quy tắc thiết kế:** xác định chuẩn hóa để tạo khóa, kiểm tra va chạm rồi mới lưu. Không đổi chính sách trên hệ thống đang hoạt động mà chưa kiểm tra dữ liệu hiện có.

## 3. Quyết định chính sách cho username

Username là định danh **do chính ứng dụng quản lý**, nên sản phẩm có quyền lựa chọn chính sách hợp lý, ví dụ:

| Chính sách | `Lan` và `lan` có cùng khóa? | Lợi ích | Đánh đổi |
| --- | --- | --- | --- |
| **Case-insensitive ASCII** | Có | Người dùng ít phải nhớ kiểu chữ; đơn giản trong API và database. | Phải chặn trùng theo canonical key; hạn chế chữ ngoài ASCII. |
| **Case-sensitive ASCII** | Không | Hai chuỗi có thể đại diện hai tài khoản riêng. | Dễ gây nhầm trong hỗ trợ, tìm kiếm và đăng nhập; migration khó khi đổi chính sách. |
| **Unicode với case folding có quy tắc** | Phụ thuộc thuật toán | Cho phép tên đa ngôn ngữ. | Cần giải quyết Unicode normalization, full case folding, confusables, versioning và collisions. |

**Một lựa chọn thực tế cho ứng dụng học Spring Security**: username đăng nhập theo chính sách **ASCII, không phân biệt chữ hoa/chữ thường**, chiều dài và tập ký tự giới hạn; nếu cần tên tiếng Việt hoặc emoji, dùng trường **display name** riêng. Cách này giúp người học tập trung vào hợp đồng `UserDetailsService` và `DaoAuthenticationProvider`, tránh các trường hợp Unicode phức tạp chưa được thiết kế.

Một chính sách cụ thể có thể là:

- Chỉ chấp nhận tên 3–30 ký tự sau khi loại khoảng trắng đầu/cuối.
- Ký tự đầu là chữ ASCII hoặc chữ số.
- Những ký tự tiếp theo thuộc `a-z`, `0-9`, `.`, `_` hoặc `-`.
- Chữ `A-Z` được chấp nhận và chuyển thành chữ thường trong **khóa tra cứu** bằng `toLowerCase(Locale.ROOT)`.
- Khoảng trắng nằm giữa username bị từ chối; các ký tự Unicode không thuộc tập chấp nhận bị từ chối.
- Không đăng ký hai tài khoản có cùng `username_key`.
- Nên có danh sách username dành riêng cho hệ thống như `admin`, `root`, `support` theo chính sách sản phẩm.

**Ví dụ:**

| Input | Username key | Hợp lệ? |
| --- | --- | --- |
| `Lan_08` | `lan_08` | Có |
| ` LAN_08 ` | `lan_08` | Có, vì chính sách cho phép loại khoảng trắng đầu/cuối |
| `lan.08` | `lan.08` | Có |
| `lan name` | — | Không, có khoảng trắng ở giữa |
| `Lân_08` | — | Không trong chính sách ASCII của ví dụ |
| `ab` | — | Không, ít hơn 3 ký tự |

Đây là **một chính sách đề xuất để minh họa**, không phải quy tắc bắt buộc của Spring Security hay một chuẩn quốc tế về username. Ứng dụng có thể chọn case-sensitive hoặc Unicode, nhưng phải khai báo tường minh và giữ nhất quán ở tất cả nơi tạo/đọc/sửa tài khoản.

## 4. Java 17: tại sao cần `Locale.ROOT` khi tạo identifier key?

Java có cả `String.toLowerCase()` và `String.toLowerCase(Locale locale)`. Bản **không có tham số** phụ thuộc default locale của JVM, nên có thể sinh khóa khác nhau trên các máy đang dùng locale khác nhau.

Ví dụ chữ `I` viết hoa trong ngôn ngữ Turkish có thể chuyển thành `ı` (chữ i không dấu chấm) khi lower-case với locale `tr-TR`. Nếu một service dùng mặc định tiếng Anh còn service khác dùng Turkish, quy trình tra cứu/đăng ký có thể bất đồng về cùng một username.

Với **mã định danh trung lập ngôn ngữ** trong chính sách ASCII, dùng:

```java
String key = input.strip().toLowerCase(Locale.ROOT);
```

`Locale.ROOT` giúp kết quả không phụ thuộc locale mặc định của máy. `strip()` loại một số khoảng trắng Unicode ở đầu/cuối theo `Character.isWhitespace`; nó **không xóa khoảng trắng bên trong**. Sau bước chuyển đổi, ứng dụng **phải validate** lại toàn bộ chuỗi theo tập ký tự và độ dài đã chọn.

**Không nhầm `toLowerCase(Locale.ROOT)` với “Unicode full case folding”.** Chuyển chữ thường của Java không tự giải quyết mọi trường hợp tương đương về Unicode như `ß` và `ss`, ký tự có dấu kết hợp, ký tự trông giống nhau ở nhiều hệ chữ, hoặc phiên bản Unicode khác nhau. Nếu hệ thống thực sự cho username Unicode, cần chính sách normalization/folding chuyên biệt và kiểm thử đa ngôn ngữ; không chỉ gọi `toLowerCase` rồi tuyên bố mọi ký tự tương đương.

### NFC, NFKC và rủi ro nhập nhằng

Unicode có thể biểu diễn một ký tự hiển thị bằng nhiều chuỗi code point. Ví dụ chữ có dấu có thể dùng một code point dựng sẵn hoặc ký tự cơ sở kèm dấu kết hợp.

- **NFC** gộp các chuỗi tương đương theo *canonical equivalence*; thường là một phần của chính sách username Unicode.
- **NFKC** áp dụng thêm tương đương tương thích, có thể thay đổi dạng hiển thị/ý nghĩa của một số ký tự. Không tự ý dùng NFKC để “sửa mọi tên giống nhau”.
- **Case folding đầy đủ** khác lower-casing thông thường; cần thư viện và quy tắc xác định, đặc biệt với các hệ chữ đa ngôn ngữ.
- **Confusables/homoglyphs**: ký tự Latin `a` có thể trông giống ký tự từ hệ chữ khác; NFC/NFKC hoặc lowercase không tự ngăn giả mạo bằng ký tự trông giống nhau.

Nếu chọn Unicode username, phải quy định **thứ tự normalize → fold → validate → lưu key**, công bố dạng Unicode được hỗ trợ và kiểm tra mọi nguồn ghi. Khi đổi thư viện hoặc Unicode version, cần test lại collisions trước khi áp dụng.

## 5. Email khác username ở một điểm then chốt: local part và domain

Email có dạng khái quát `local-part@domain`, ví dụ `Sales@Example.COM`:

- **Domain** nằm sau `@`. Theo quy tắc DNS/SMTP, tên miền **không phân biệt chữ hoa/chữ thường**: `Example.COM` và `example.com` cùng một tên miền.
- **Local part** nằm trước `@`. Theo chuẩn SMTP, phần này **phải được bảo toàn nguyên dạng chữ hoa/chữ thường** khi xử lý địa chỉ; một số máy chủ có thể phân biệt `Sales` và `sales`. Mặc dù nhiều nhà cung cấp hiện nay không phân biệt case ở local part, ứng dụng **không thể giả định điều đó cho mọi domain**.

Vì vậy có hai câu hỏi **khác nhau**:

1. **Dùng email để gửi thông báo:** lưu địa chỉ người dùng đã cung cấp/đã xác minh và không tự ý sửa local part. Có thể chuẩn hóa domain theo chính sách DNS/IDNA; phải đảm bảo định dạng giao vận chính xác.
2. **Dùng email làm tên đăng nhập/khóa tài khoản:** ứng dụng phải chọn quy tắc tra cứu rõ ràng. Có thể quyết định không phân biệt hoa/thường trên cả địa chỉ vì UX, **nhưng khi làm vậy sẽ gộp những local part mà một số mail server có thể coi là hộp thư khác nhau**.

| Địa chỉ A | Địa chỉ B | So theo domain không phân biệt case | So local part theo SMTP |
| --- | --- | --- | --- |
| `Sales@Example.COM` | `Sales@example.com` | Cùng domain | Cùng local part |
| `Sales@example.com` | `sales@example.com` | Cùng domain | **Có thể là hai hộp thư khác nhau** |
| `alice+promo@example.com` | `alice@example.com` | Cùng domain | **Không được mặc định gộp** |
| `first.last@gmail.com` | `firstlast@gmail.com` | Cùng domain | Đừng áp dụng quy tắc loại dấu chấm cho mọi nhà cung cấp |

**Không xóa dấu chấm, dấu cộng, suffix sau `+` hoặc lower-case local part một cách toàn cục.** Cách một nhà cung cấp xử lý alias/dấu chấm là quy tắc riêng của nhà cung cấp đó, có thể thay đổi và không áp dụng cho mọi domain. Kể cả khi sản phẩm biết một provider có aliasing đặc biệt, việc liên kết tài khoản vẫn cần kiểm tra quyền sở hữu và rủi ro bảo mật.

### Email có thể là thuộc tính liên hệ, không phải khóa định danh vĩnh viễn

Một địa chỉ email có thể đổi chủ, người dùng có thể đổi email, domain có thể ngừng hoạt động và thông tin email từ IdP có thể không được xác minh. Vì vậy:

- Khóa nội bộ cho user nên là `user_id` ổn định, không dùng email làm foreign key nghiệp vụ.
- Không tự gộp hai tài khoản chỉ vì cùng email sau một phép chuẩn hóa mới.
- Nếu dùng email cho login/password reset, cần **xác minh quyền kiểm soát email**, quy trình đổi email an toàn và chính sách xử lý trùng.
- Với đăng nhập OIDC, định danh phù hợp để liên kết thường dựa vào cặp `issuer` + `sub`; không dùng duy nhất email từ một claim chưa chắc được xác minh.
- Khi đổi email, lưu lịch sử/metadata liên quan theo yêu cầu bảo mật và quyền riêng tư, nhưng tránh lộ dữ liệu nhạy cảm.

### Địa chỉ quốc tế hóa

Email thực tế có thể bao gồm **internationalized domain names (IDN)** và **SMTPUTF8/EAI** với local part Unicode; cũng có dạng local part được đặt trong dấu ngoặc kép theo cú pháp SMTP. Một regex ngắn **không thể đại diện toàn bộ chuẩn email**. Hệ thống production nên dùng thư viện xác thực email được duy trì, quy trình IDNA phù hợp và kiểm thử gửi/nhận qua hạ tầng email thực.

Đối với domain Unicode, có khái niệm **IDNA** để biểu diễn bằng dạng ASCII tương ứng, nhưng bản chuẩn/thuật toán có khác biệt. Không lấy `String.toLowerCase` làm toàn bộ giải pháp IDN. Ví dụ Java tiếp theo **cố ý chỉ nhận subset email ASCII, local part không có dấu ngoặc kép và domain kiểu thông dụng** để làm rõ nguyên tắc case.

## 6. Chọn chính sách email login: phải ghi thành quyết định sản phẩm

Có ba lựa chọn cần phân biệt:

| Mô hình | Khóa tra cứu | Hệ quả |
| --- | --- | --- |
| **Email để liên lạc, username để login** | Login theo `username_key`; email lưu nguyên dạng và trạng thái xác minh. | Tách ổn định định danh nội bộ và giao vận email, giảm nhầm lẫn về local part. |
| **Email login bảo toàn local part** | `localOriginal@domainLower`, so exact key. | Tôn trọng khả năng local part phân biệt case; người dùng phải nhớ kiểu chữ khi login. |
| **Email login không phân biệt case theo chính sách ứng dụng** | `localLower@domainLower` sau validation. | UX đơn giản hơn, nhưng có thể gộp mailbox khác nhau; chỉ dùng khi đã đánh giá provider, chính sách xác minh, collisions và vòng đời tài khoản. |

Bất kỳ lựa chọn nào cũng phải áp dụng **giống nhau** tại endpoint đăng ký, đăng nhập, đổi email, password reset, tìm tài khoản và unique constraint. Không nên đăng ký theo key có phân biệt case nhưng đăng nhập bằng phép so không phân biệt case: hai tài khoản `Sales@...` và `sales@...` sẽ gây ánh xạ không xác định.

Nếu dự án đã tồn tại, **không tự thay đổi chính sách case email** theo một “best practice” chung. Trước hết hãy phân tích dữ liệu, mailbox thực, quy trình xác minh và khả năng collision.

## 7. Ví dụ Java 17 chạy độc lập: tạo canonical key một cách tường minh

Ví dụ dưới đây sử dụng **chỉ JDK 17+**, không cần Spring Boot hay thư viện ngoài. Nó thể hiện hai chính sách có chủ đích:

- Username chỉ dùng ASCII, **không phân biệt case**, cho phép loại khoảng trắng đầu/cuối, chiều dài 3–30 ký tự.
- Email trong **subset ASCII**: giữ nguyên local part trong `smtpKey`, lower-case domain; xuất thêm `foldedLoginKey` **chỉ để cho thấy va chạm nếu sản phẩm chọn bỏ phân biệt case local part**. Không sử dụng khóa này để tự khẳng định hai mailbox là một.

### 7.1. File `IdentityPolicyDemo.java`

```java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

public final class IdentityPolicyDemo {

    private static final Pattern USERNAME =
            Pattern.compile("[a-z0-9][a-z0-9._-]{2,29}");

    // Subset ASCII dành riêng cho demo, không phải parser email RFC đầy đủ.
    private static final Pattern LOCAL =
            Pattern.compile("[A-Za-z0-9_%+-]+(?:\\.[A-Za-z0-9_%+-]+)*");

    private static final Pattern DOMAIN =
            Pattern.compile("[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                    + "(?:\\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}"
                    + "[A-Za-z0-9])?)+");

    private record EmailKeys(
            String original,
            String smtpKey,
            String foldedLoginKey) {
    }

    static String usernameKey(String input) {
        String key = Objects.requireNonNull(input, "username")
                .strip()
                .toLowerCase(Locale.ROOT);

        if (!USERNAME.matcher(key).matches()) {
            throw new IllegalArgumentException("Invalid username");
        }
        return key;
    }

    static EmailKeys emailKeys(String input) {
        String original = Objects.requireNonNull(input, "email").strip();
        int at = original.indexOf('@');

        if (at < 1 || at != original.lastIndexOf('@')
                || at == original.length() - 1) {
            throw new IllegalArgumentException("Invalid email");
        }

        String local = original.substring(0, at);
        String domain = original.substring(at + 1);

        if (original.length() > 254 || local.length() > 64
                || !LOCAL.matcher(local).matches()
                || !DOMAIN.matcher(domain).matches()) {
            throw new IllegalArgumentException("Invalid email");
        }

        String domainKey = domain.toLowerCase(Locale.ROOT);
        return new EmailKeys(
                original,
                local + "@" + domainKey,
                local.toLowerCase(Locale.ROOT) + "@" + domainKey);
    }

    public static void main(String[] args) {
        String first = usernameKey("  LaN_08  ");
        String second = usernameKey("LAN_08");

        System.out.println("username.key=" + first);
        System.out.println("username.sameKey=" + first.equals(second));

        Set<String> uniqueKeys = new HashSet<>();
        System.out.println("username.registerFirst=" + uniqueKeys.add(first));
        System.out.println("username.registerSecond=" + uniqueKeys.add(second));

        EmailKeys mail = emailKeys("Sales@Example.COM");
        System.out.println("email.original=" + mail.original());

        EmailKeys sameLocal = emailKeys("Sales@example.com");
        System.out.println("email.domainEquivalent="
                + mail.smtpKey().equals(sameLocal.smtpKey()));

        EmailKeys differentLocal = emailKeys("sales@example.com");
        System.out.println("email.localPreservedDistinct="
                + !mail.smtpKey().equals(differentLocal.smtpKey()));
        System.out.println("email.optionalFoldCollides="
                + mail.foldedLoginKey().equals(
                        differentLocal.foldedLoginKey()));

        EmailKeys plusAlias = emailKeys("sales+promo@example.com");
        System.out.println("email.plusIsDistinct="
                + !plusAlias.smtpKey().equals(
                        differentLocal.smtpKey()));

        try {
            usernameKey("lan name");
        } catch (IllegalArgumentException ex) {
            System.out.println("badUsernameRejected=true");
        }

        try {
            emailKeys("a@@example.com");
        } catch (IllegalArgumentException ex) {
            System.out.println("badEmailRejected=true");
        }

        System.out.println("passwordCaseSensitive="
                + !"Secret123!".equals("secret123!"));
    }
}
```

### 7.2. Biên dịch và chạy

Lưu file trên với mã hóa UTF-8. Tại thư mục chứa file, dùng JDK 17+:

```bash
javac -encoding UTF-8 IdentityPolicyDemo.java
java IdentityPolicyDemo
```

**Stdout dự kiến từ chương trình:**

```text
username.key=lan_08
username.sameKey=true
username.registerFirst=true
username.registerSecond=false
email.original=Sales@Example.COM
email.domainEquivalent=true
email.localPreservedDistinct=true
email.optionalFoldCollides=true
email.plusIsDistinct=true
badUsernameRejected=true
badEmailRejected=true
passwordCaseSensitive=true
```

### 7.3. Điều ví dụ thực sự chứng minh

1. `LaN_08` và `LAN_08` có chung `username_key=lan_08` do chính sách của ứng dụng; `HashSet` từ chối thêm khóa trùng lần thứ hai. Trong DB thật cần ràng buộc unique, không dựa vào `HashSet`.
2. Hai email có **cùng local part** nhưng domain khác kiểu chữ có cùng `smtpKey`.
3. `Sales@...` và `sales@...` có `smtpKey` khác nhau vì **local part được bảo toàn**. Việc chúng thực sự đi tới hai hộp thư hay một hộp thư phải do mail server quyết định.
4. `foldedLoginKey` cho thấy nếu sản phẩm tự lower-case toàn bộ email, hai chuỗi trên sẽ **va chạm**. Đây là một quyết định nhận diện tài khoản, không phải sự thật phổ quát về mailbox.
5. `sales+promo@...` và `sales@...` được xem là hai local part khác nhau theo chính sách bảo toàn; không tự giả định dấu cộng là alias.
6. Username có khoảng trắng nội bộ và email có nhiều dấu `@` bị từ chối theo **subset demo**.
7. Mật khẩu vẫn **phân biệt chữ hoa/chữ thường**. **Không gọi `strip()`, `toLowerCase()` hay Unicode normalization trên password** để “đồng bộ” với username; việc biến đổi secret sẽ thay đổi ý nghĩa xác thực và có thể làm giảm độ mạnh.

**Giới hạn rõ ràng:** regex demo không nhận được toàn bộ email hợp lệ theo RFC, local part được quote, email Unicode/SMTPUTF8, domain quốc tế hóa, address literal hay cú pháp phức tạp. Nó cũng không kiểm tra MX, khả năng nhận thư hoặc quyền sở hữu địa chỉ. Không copy hai `Pattern` này làm cơ chế xác thực email production.

## 8. Kết nối chính sách username với Spring Security

### 8.1. `UserDetailsService` là ranh giới quan trọng

`DaoAuthenticationProvider` gọi `UserDetailsService.loadUserByUsername(...)` để tải thông tin tài khoản. Hợp đồng cho phép implementation tìm kiếm theo chính sách case riêng, vì vậy **chính adapter phải dùng đúng canonical key mà hệ thống đăng ký/lưu trữ đã chọn**.

Ví dụ một adapter cho application dùng Spring Data:

```java
// Đoạn minh họa, không phải class Java chạy độc lập.
// Dự án đã định nghĩa AccountRepository, Account và UsernameKeys.
// UsernameKeys.toKey(...) thực hiện đúng policy như usernameKey ở ví dụ 7.
@Service
final class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    AccountUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String enteredUsername) {
        String key = UsernameKeys.toKey(enteredUsername);

        Account account = accounts.findByUsernameKey(key)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));

        return User.withUsername(account.usernameDisplay())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .authorities(account.authorities())
                .build();
    }
}
```

Cần các import Spring `@Service`, `UserDetailsService`, `UserDetails`, `User`, `UsernameNotFoundException` và các kiểu dự án. Đây là phác thảo adapter, không phải ví dụ đã có schema hoặc repository hoàn chỉnh.

Điều phải giữ nhất quán:

- Đăng ký: tạo `username_key` theo một hàm canonicalization duy nhất.
- Truy vấn khi đăng nhập: dùng **cùng hàm** tạo khóa trước khi gọi repository.
- Đổi username: kiểm tra trùng theo khóa và cập nhật nguyên tử.
- Lookup ngoài login (quên mật khẩu, quản trị): theo cùng policy, nhưng không để response lộ tài khoản tồn tại.
- Cache/identity mapping: khóa cache bằng một định danh ổn định hoặc cùng canonical key, không trộn `Lan` và `lan` thành hai entry khi chính sách coi chúng là một.
- Quyền: đọc authorities từ dữ liệu tài khoản đã tìm thấy, **không** từ tên/role do client gửi.

Nếu `UsernameKeys.toKey` có thể ném `IllegalArgumentException` do input sai, adapter cần có chính sách xử lý phù hợp để biến lỗi nhập thành thất bại xác thực an toàn; ví dụ dùng một `UsernameNotFoundException` hoặc cho filter/service validate trước. Không để ngoại lệ validation tùy ý gây HTTP 500 hay làm lộ sự tồn tại của user.

### 8.2. `UserDetailsService` không tự quyết định case sensitivity

Trong Spring Security, `UserDetailsService` chỉ là hợp đồng đọc user. Một triển khai in-memory có thể dùng khóa lowercase, một repository JPA có thể so exact, còn một truy vấn SQL với collation không phân biệt case có thể có kết quả khác. Không có lời hứa rằng **mọi implementation của `UserDetailsService` đều case-insensitive**.

Đặc biệt, `InMemoryUserDetailsManager` trong mã nguồn Spring Security hiện hành lưu/tra cứu username bằng `toLowerCase(Locale.ROOT)`. Điều này tiện cho demo, nhưng nếu đổi sang database với cột dùng so sánh phân biệt case, hành vi đăng nhập có thể thay đổi. Vì vậy hãy viết bài test contract chung trước khi thay store.

**Không chỉ sửa chuỗi đầu vào trong HTTP filter.** Một user còn được tìm qua nhiều luồng (registration, admin, reset password, integration) ngoài login filter. Quy tắc phải nằm ở tầng identity/domain chung, và được áp dụng nhất quán khi tạo, cập nhật, tìm kiếm.

### 8.3. `getName()` không nhất thiết đúng kiểu chữ đã nhập

Nếu request gửi username `LAN_08` nhưng `UserDetailsService` trả `UserDetails.username="Lan_08"`, kết quả `Authentication.getName()` có thể chứa `Lan_08`. Đây không phải xác thực thất bại. Hợp đồng service cho phép implementation trả username khác kiểu chữ với chuỗi yêu cầu.

Không dùng `authentication.getName()` làm foreign key chính cho dữ liệu như hóa đơn, tài liệu hay đơn hàng; dùng `user_id` ổn định từ principal/domain mapping. Nếu cần khóa so, tạo key theo đúng policy từ nguồn đáng tin cậy và tránh dựa vào spelling của request chưa kiểm chứng.

### 8.4. Email login cần một lookup strategy riêng

Nếu cho đăng nhập bằng username **hoặc** email, đừng kiểm tra đơn giản “chuỗi có `@` thì hạ chữ thường toàn bộ” mà chưa có chính sách email.

Một thiết kế có thể:

1. Nhận `loginIdentifier` từ filter/form.
2. Phân loại theo định dạng/chính sách đã xác định.
3. Với username, tạo `username_key` và tìm user.
4. Với email, validate input và tạo **email lookup key đã công bố**, tra về đúng **một user** có email đã xác minh theo rule.
5. Tải `UserDetails` và để provider kiểm tra password hash cùng trạng thái account.
6. Nếu lookup có 0 hoặc nhiều candidate, từ chối/đưa vào luồng xử lý thích hợp, **không tự chọn một account tùy ý**.

Trong hệ thống cho phép đổi email hoặc một email dùng cho nhiều account, email có thể không còn là khóa login duy nhất. Khi đó cần policy khác, ví dụ chỉ username login hoặc một định danh thứ ba không thay đổi.

## 9. Database: ràng buộc duy nhất phải nằm trên canonical key

Một **rủi ro kinh điển** là chỉ kiểm tra trùng trong Java:

```java
if (!accounts.existsByUsernameKey(key)) {
    accounts.save(new Account(...));
}
```

Hai request đăng ký đồng thời có thể đều thấy “chưa tồn tại” rồi cùng ghi. Vì vậy **kiểm tra trong service phục vụ UX; ràng buộc unique ở database mới xử lý race condition**.

Một schema minh họa, không cố áp đặt cú pháp của một hệ quản trị cụ thể:

```sql
CREATE TABLE app_users (
    user_id        BIGINT PRIMARY KEY,
    username_display VARCHAR(30) NOT NULL,
    username_key     VARCHAR(30) NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    email_original   VARCHAR(254),
    email_lookup_key VARCHAR(254),
    email_verified_at TIMESTAMP,
    enabled          BOOLEAN NOT NULL
);

CREATE UNIQUE INDEX ux_app_users_username_key
    ON app_users (username_key);
```

Trong hệ quản trị cụ thể, còn cần quy định sinh `user_id`, collation/index tương thích quy tắc canonicalization, transaction, charset và cách quản lý giá trị NULL. Nếu sản phẩm yêu cầu **một email đã xác minh chỉ thuộc một tài khoản**, cần thiết kế unique constraint/index trên email key **phù hợp với trạng thái verified và khả năng NULL** của chính hệ quản trị đó. Đừng vội thêm `UNIQUE(email_original)` nếu sản phẩm không dùng email làm login hoặc email chưa qua xác minh.

**Tại sao vừa lưu key vừa để ý collation?** Có thể Java chuẩn hóa `Lan` thành `lan`, nhưng DB có collation khác (case/accent-insensitive) dẫn tới `lan` và một tên có dấu nào đó bị coi là trùng ngoài dự kiến. Ngược lại, nếu lookup dùng case-insensitive nhưng unique index dùng exact comparison, hai account có thể cùng được phép tạo rồi gây ambiguities khi đăng nhập.

Cần kiểm thử thực tế trên DB được triển khai:

- So sánh `Lan`/`LAN` theo `username_key` phải ra kết quả mong đợi.
- Không có hai hàng cùng canonical key khi register đồng thời.
- `ORDER BY` hoặc search có thể khác với kiểm tra equality trong unique index; đừng suy ra một từ cái kia.
- App và DB phải đồng ý về kiểu encoding, length và quy tắc xử lý dấu/Unicode.
- Nếu DB hỗ trợ index trên expression như `lower(username)`, đánh giá kỹ chức năng đó có thực sự tương đương **toàn bộ hàm canonicalization của ứng dụng** hay không; thường cột canonical riêng dễ quản lý hơn khi chính sách phức tạp.

## 10. Migration: đổi chính sách case không chỉ là một câu lệnh SQL

Giả sử DB cũ có:

| user_id | username_display | username_key mới |
| --- | --- | --- |
| 101 | `Lan` | `lan` |
| 207 | `lan` | `lan` |
| 310 | `LAN` | `lan` |
| 420 | `Mai` | `mai` |

Nếu đột ngột tạo index unique trên `username_key`, ba bản ghi đầu **va chạm**. **Không gộp user 101, 207 và 310 chỉ vì spelling giống nhau sau normalization**: họ có thể là các cá nhân khác nhau, dữ liệu và quyền khác nhau.

Một lộ trình migration có kiểm soát:

1. **Công bố chính sách mới**: username/email nào được chấp nhận, quy tắc hoa/thường, Unicode, dấu và whitespace.
2. **Backfill vào cột shadow**: tính `username_key_v2` cho tất cả tài khoản theo cùng một hàm. Chưa dùng key này cho login.
3. **Báo cáo collisions**: nhóm theo key mới, đếm account và xác định account nào là độc lập. Không tự chọn người thắng.
4. **Giải quyết collisions hợp lệ**: yêu cầu đổi username, tạo alias có kiểm soát, hoặc quy trình xác minh quyền sở hữu trước khi liên kết dữ liệu.
5. **Ngăn tạo collision mới**: triển khai validation và unique constraint/backfill theo kế hoạch, xử lý ghi đồng thời, versioned rollout giữa nhiều instance.
6. **Dual-read/dual-write có giới hạn** nếu cần tương thích: tránh một instance dùng rule cũ, một instance dùng rule mới mà không có cơ chế hòa giải.
7. **Đổi lookup chính thức** sau khi dữ liệu sạch; thêm DB unique, theo dõi lỗi login/registration và có rollback plan.
8. **Dọn legacy path** sau thời gian chuyển tiếp và kiểm tra lại các luồng reset password, external login, cache, audit và tìm kiếm.

Với email, va chạm còn nguy hiểm hơn: `Sales@...` và `sales@...` có thể là hai mailbox riêng theo hệ thống đích. **Không hợp nhất account hoặc đặt lại mật khẩu dựa trên kết luận rằng email khác case luôn giống nhau.** Cần xác minh địa chỉ và quyền sở hữu theo policy đã đánh giá.

## 11. Kiểm thử phải bao phủ cả dữ liệu và Spring Security

### Ma trận test canonical username

| Input | Kết quả mong đợi với chính sách ASCII-insensitive |
| --- | --- |
| `Lan_08` | `lan_08` |
| `  LAN_08  ` | `lan_08` |
| `lan_08` | `lan_08` |
| `lan name` | Validation error |
| `ab` | Validation error |
| `lân_08` | Validation error do không nằm trong subset ASCII |
| `Ivy` khi JVM dùng Turkish locale | `ivy` vì có `Locale.ROOT` |
| Hai request cùng key | Database chỉ cho một bản ghi |

### Ma trận test email

| Input/so sánh | Kỳ vọng |
| --- | --- |
| `Sales@Example.COM` so `Sales@example.com` | Cùng key nếu chỉ lower-case domain. |
| `Sales@example.com` so `sales@example.com` | Hai `smtpKey` khác nhau; `foldedLoginKey` trùng nếu sản phẩm cố ý không phân biệt local case. |
| `sales+promo@example.com` so `sales@example.com` | Không tự gộp local part. |
| Email có nhiều `@` | Reject hoặc xử lý bằng parser email đúng chuẩn, không “sửa” bằng cách xóa ký tự. |
| Email IDN/Unicode | Kiểm thử bằng thư viện/giao thức thật; ví dụ regex ASCII cố ý không hỗ trợ. |
| Email chưa xác minh | Không dùng trực tiếp để cấp quyền reset mật khẩu hoặc liên kết account. |

### Test Spring Security

Ở integration test, tạo hai biến thể của cùng username case để chứng minh `UserDetailsService` dùng canonical key:

- Tạo user với `username_display=Lan_08`, `username_key=lan_08` và password hash hợp lệ.
- Gọi `AuthenticationManager.authenticate(...)` bằng `LAN_08` và password đúng: yêu cầu thành công.
- Gọi bằng `lan_08` và password sai: yêu cầu bị từ chối bằng `BadCredentialsException`.
- Thử đăng ký `LAN_08` khi `Lan_08` đã có: unique constraint chặn record mới.
- Xác minh kết quả authorities đến từ account đã tìm thấy, không từ tham số đầu vào.
- Test đồng thời hai request register cùng key và kiểm tra **chỉ một** commit thành công.
- Khi đổi email/username, kiểm tra cache, session và liên kết dữ liệu theo `user_id`; không tự thay đổi ownership của tài nguyên.

**Đừng dùng riêng `@WithMockUser` để chứng minh canonicalization login.** Nó tạo authentication giả lập cho test và có thể bỏ qua `UserDetailsService`. Muốn test lookup + password, phải gọi manager/provider thật hoặc chạy HTTP filter với form login/Basic theo cấu hình phù hợp. `@WithMockUser` vẫn hữu ích cho kiểm tra authorization nhưng trả lời câu hỏi khác.

### Test đặc biệt cho quốc tế hóa

Nếu ứng dụng hỗ trợ Unicode username, bổ sung test NFC vs dạng dấu kết hợp, các biến thể Turkish I, Greek sigma, German sharp S, ký tự giống nhau từ nhiều hệ chữ và ký tự định dạng vô hình. Chọn **một** kết quả theo chính sách sản phẩm, khóa version normalization và kiểm tra với mọi nơi đọc/ghi. Tránh giả định chỉ một unit test `toLowerCase(Locale.ROOT)` chứng minh Unicode case folding là an toàn.

## 12. Password là credential, không phải identifier

Một lỗi dễ xảy ra khi áp dụng quy tắc normalization chung cho mọi ô của form đăng nhập:

```java
// SAI: không chuẩn hóa mật khẩu như username.
String username = submittedUsername.strip().toLowerCase(Locale.ROOT);
String password = submittedPassword.strip().toLowerCase(Locale.ROOT);
```

**Mật khẩu phải được xử lý theo hợp đồng credential**, không tự ý strip, lowercase hoặc dùng phép chuẩn hóa mà hệ thống chưa định nghĩa trong chính sách mật khẩu. Nếu user đặt password `Secret123!`, thông thường `secret123!` phải là secret khác.

Với Spring Security:

- `UserDetailsService` tìm user bằng định danh đã chuẩn hóa theo policy.
- `DaoAuthenticationProvider` dùng `PasswordEncoder.matches(rawPassword, encodedPassword)` để so đúng raw password với hash đã lưu.
- Hash mật khẩu cần thuật toán phù hợp như BCrypt/Argon2 theo chính sách; không ghi plaintext vào database.
- Không log raw password, request body, authorization header hoặc toàn bộ token authentication.

Đối với đăng nhập API, “không tìm thấy username” và “mật khẩu sai” thường nên nhận thông báo bên ngoài có kiểm soát để tránh enumeration. Validation chi tiết có thể hiện ở luồng **đăng ký username**, nhưng endpoint login không nên vô tình công bố account có tồn tại hay không qua response, timing hoặc status.

## 13. Các lỗi thiết kế thường gặp

1. **Lowercase username trong đăng nhập nhưng không lowercase lúc đăng ký.** Tạo dữ liệu không thống nhất và collision khi tra cứu.
2. **Gọi `toLowerCase()` không có `Locale.ROOT` cho key trung lập ngôn ngữ.** Có thể lệch giữa JVM/locale khác nhau.
3. **Tin rằng Spring Security bắt buộc mọi user store case-insensitive.** `UserDetailsService` cho phép implementation tự quyết định.
4. **Nhầm `InMemoryUserDetailsManager` với database production.** Hành vi lookup của manager demo có thể khác query JPA/SQL thực tế.
5. **Dùng `equalsIgnoreCase` như một chuẩn Unicode identity toàn diện.** Nó không thay thế chính sách canonical Unicode, full case folding và kiểm tra confusables.
6. **Dùng `NFKC` vô điều kiện để “sửa” mọi ký tự.** Có thể làm nhiều identifier khác nhau đụng nhau; phải giải quyết collisions trước.
7. **Lowercase toàn bộ email và khẳng định SMTP buộc coi mọi local part giống nhau.** Domain không phân biệt case, còn local part phải được bảo toàn khi giao vận.
8. **Xóa dấu chấm/dấu cộng của mọi email vì một nhà cung cấp có aliasing đặc biệt.** Có thể gộp hai hộp thư không liên quan.
9. **Lưu email làm khóa ngoại chính cho đơn hàng.** Email thay đổi; dùng `user_id` ổn định.
10. **Dùng email chưa xác minh để reset password hoặc link SSO.** Có nguy cơ chiếm tài khoản qua claim hoặc dữ liệu giả.
11. **Chỉ gọi `existsByUsernameKey` rồi mới insert mà không có unique index.** Có race condition khi register đồng thời.
12. **Không kiểm tra collation DB.** Quy tắc equality/unique trong DB có thể khác chuẩn hóa của Java.
13. **Đổi thuật toán normalization của production mà không kiểm tra collisions.** Có thể khiến nhiều account cũ cùng khóa hoặc khóa thay đổi.
14. **Tự động merge hai account cũ sau khi thấy cùng canonical key.** Không có bằng chứng rằng chúng thuộc một người; liên kết dữ liệu có thể thành lỗ hổng nghiêm trọng.
15. **Chuẩn hóa password như username.** Làm thay đổi credential, phá vỡ kiểm tra hash và giảm tính dự đoán.
16. **Tin vào tên do client gửi để quyết định quyền.** Quyền phải lấy từ bản ghi đã được provider xác thực.
17. **So khớp tên hiển thị để kiểm tra sở hữu tài nguyên.** Dùng định danh ổn định, không dựa vào capitalization hoặc email.
18. **Test bằng mock user rồi kết luận lookup và canonicalization đã đúng.** Mock thường không đi qua password provider hoặc real user store.
19. **Làm rơi case của email_original khi lưu.** Có thể làm sai địa chỉ giao vận tới máy chủ phân biệt case local part.
20. **Thay đổi thuật toán không có version/rollout.** Nhiều service cùng lúc dùng các version khác nhau có thể xử lý cùng tên thành hai khóa.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng cho phép `Lan` và `lan` cùng tồn tại khi đăng ký nhưng login lại gọi `toLowerCase(Locale.ROOT)` trước lookup. Vấn đề là gì?

**Trả lời:** Hai account khác nhau có thể cùng một khóa `lan` ở bước đăng nhập, dẫn tới lookup mơ hồ hoặc sai tài khoản. Phải định nghĩa cùng một policy cho registration, unique index và authentication; xử lý collision dữ liệu cũ trước khi thay.

**Câu 2.** Tại sao `Sales@Example.COM` có thể chuẩn hóa domain thành `Sales@example.com`, nhưng không mặc nhiên thành `sales@example.com`?

**Trả lời:** Domain theo DNS không phân biệt hoa/thường. Local part theo SMTP cần giữ case; một số mail server phân biệt `Sales` và `sales`. Lowercase toàn bộ là quyết định login policy có đánh đổi, không phải quy tắc giao vận phổ quát.

**Câu 3.** `UserDetailsService.loadUserByUsername("LAN_08")` trả user với `getUsername()=="Lan_08"`. Đây có phải vi phạm API?

**Trả lời:** Không. API cho phép implementation tìm kiếm không phân biệt case và trả username khác kiểu chữ so với input.

**Câu 4.** Vì sao unique constraint trên `username_key` vẫn cần khi service đã kiểm tra tên trùng?

**Trả lời:** Hai transaction có thể cùng vượt qua phép check trước khi insert. Unique constraint xử lý race; service cần bắt và chuyển lỗi phù hợp.

**Câu 5.** Có nên dùng `toLowerCase(Locale.ROOT)` cho password không?

**Trả lời:** Không. Username và password có vai trò khác nhau. Mật khẩu phải được kiểm chứng đúng bằng `PasswordEncoder.matches(...)` mà không tự ý thay đổi ký tự.

**Câu 6.** Một hệ thống có `user_id=101, username=Lan` và `user_id=207, username=lan`. Khi đổi sang case-insensitive, nên tự merge không?

**Trả lời:** Không. Cần phát hiện collision và quy trình xác minh/đổi tên, bảo toàn dữ liệu và quyền của mỗi account.

**Câu 7.** Đăng nhập OIDC trả email trùng địa chỉ đã thấy trong DB. Có thể tự gán phiên vào tài khoản đó không?

**Trả lời:** Không tự động. Cần xem `email_verified`, issuer, `sub` và chính sách liên kết tài khoản. Email một mình không phải định danh bất biến hoặc bằng chứng sở hữu dài hạn.

**Câu 8.** Vì sao một test dùng `@WithMockUser` chưa chứng minh chuẩn hóa username trong `UserDetailsService`?

**Trả lời:** Mock tạo `Authentication` phục vụ kiểm thử mà không bắt buộc thực hiện lookup/password validation. Cần test integration gọi provider hoặc HTTP security filter chain.

## 15. Tài liệu đối chiếu

- [Spring Security — UserDetailsService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html): hợp đồng tra cứu username cho phép implementation case-sensitive hoặc case-insensitive.
- [Spring Security — InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html): kho user in-memory; hành vi của demo không thay thế chính sách của DB.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): tải user từ `UserDetailsService` và kiểm tra credentials.
- [RFC 5321 — Simple Mail Transfer Protocol, Section 2.4](https://www.rfc-editor.org/rfc/rfc5321#section-2.4): domain không phân biệt case; local part cần bảo toàn case.
- [Oracle Java 17 — String.toLowerCase(Locale)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#toLowerCase(java.util.Locale)): không phụ thuộc default locale khi chọn `Locale.ROOT`.
- [Oracle Java 17 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode NFC/NFKC và phạm vi normalization.
- [RFC 6531 — SMTP Extension for Internationalized Email](https://www.rfc-editor.org/rfc/rfc6531): local part quốc tế hóa và giới hạn của ví dụ ASCII.

**Ghi nhớ:** username có thể được chuẩn hóa theo chính sách riêng của ứng dụng, nhưng **email không đơn thuần là username có dấu `@`**. Chọn một canonical key ổn định, giữ dữ liệu liên hệ cần thiết, enforce uniqueness ở database, xử lý collisions trước migration và áp dụng cùng policy ở `UserDetailsService` lẫn mọi điểm đăng ký/cập nhật. Mật khẩu và định danh nội bộ `user_id` là hai phạm vi riêng: không biến đổi mật khẩu theo luật username, và không dùng spelling/email thay thế khóa user bất biến.