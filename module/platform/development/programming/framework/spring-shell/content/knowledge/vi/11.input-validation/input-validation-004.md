# Chuỗi rỗng, chuỗi trắng và tùy chọn không xuất hiện

Khi một command nhận tham số kiểu `String`, có ba trạng thái đầu vào cần phân biệt: người dùng không truyền option, người dùng truyền chuỗi rỗng (`""`) và người dùng truyền một chuỗi chỉ chứa ký tự trắng như dấu cách. Ba trạng thái này có thể mang ý nghĩa nghiệp vụ khác nhau, vì vậy không nên tự động coi chúng là một.

Ví dụ, với command cập nhật hồ sơ, option `--nickname` có thể được hiểu như sau:

- Không xuất hiện: giữ nguyên biệt danh hiện tại.
- Có mặt với giá trị rỗng: xóa biệt danh.
- Có mặt với giá trị chỉ gồm dấu cách: dữ liệu không hợp lệ.
- Có mặt với văn bản: cập nhật biệt danh theo giá trị đó.

Spring Shell chuyển dòng lệnh thành giá trị tham số trước khi gọi command. Nhà phát triển cần quyết định chính sách xử lý từng trạng thái sau khi nhận được giá trị.

## Ba trạng thái của một String

Trong Java, `null`, chuỗi rỗng và chuỗi trắng là ba giá trị khác nhau:

| Trạng thái | Giá trị Java | `isEmpty()` | `isBlank()` | Ý nghĩa |
|---|---|---:|---:|---|
| Option không xuất hiện | `null` (khi option là optional và không có default) | Không gọi được | Không gọi được | Người dùng không cung cấp giá trị |
| Chuỗi rỗng | `""` | `true` | `true` | Có một String nhưng độ dài bằng 0 |
| Chuỗi có dấu cách | `"   "` | `false` | `true` | Có ký tự, nhưng không có nội dung ngoài khoảng trắng |
| Chuỗi có nội dung | `"Lan"` | `false` | `false` | Có ít nhất một ký tự không phải khoảng trắng |

Điểm cần nhớ:

- `null` biểu thị không có đối tượng String.
- `""` là một đối tượng String có độ dài bằng 0.
- `"   "` có độ dài lớn hơn 0, nhưng chỉ chứa khoảng trắng.

Không gọi `isEmpty()` hoặc `isBlank()` trước khi kiểm tra `null`, nếu không command có thể phát sinh `NullPointerException` khi người dùng bỏ qua option.

## Spring Shell đọc các giá trị này như thế nào?

Trong Spring Shell 4.0.4, parser tách đầu vào thành các từ theo khoảng trắng. Nếu giá trị cần chứa khoảng trắng, hãy đặt toàn bộ giá trị trong dấu nháy đơn hoặc dấu nháy kép. Dấu nháy bao ngoài được loại bỏ khi parser tạo giá trị.

Giả sử command nhận option `--nickname`:

```text
shell:>profile-update
```

Option không xuất hiện trong dòng lệnh.

```text
shell:>profile-update --nickname=""
```

Option có mặt và giá trị là chuỗi rỗng.

```text
shell:>profile-update --nickname="   "
```

Option có mặt và giá trị chứa ba dấu cách. Dấu nháy giúp parser giữ các khoảng trắng bên trong thành một giá trị.

```text
shell:>profile-update --nickname="Lan Nguyen"
```

Option có mặt và giá trị là `Lan Nguyen`, gồm cả dấu cách ở giữa.

Với option kiểu String, chỉ viết tên option mà không có giá trị, ví dụ `profile-update --nickname`, là trường hợp thiếu giá trị của option. Đây không phải cách biểu diễn option vắng mặt. Muốn bỏ qua option, hãy không đưa `--nickname` vào dòng lệnh.

| Cách gọi | Ý nghĩa đầu vào |
|---|---|
| `profile-update` | Không truyền `nickname` |
| `profile-update --nickname=""` | Truyền String rỗng |
| `profile-update --nickname="   "` | Truyền String chỉ có dấu cách |
| `profile-update --nickname="Lan Nguyen"` | Truyền String có nội dung và khoảng trắng |
| `profile-update --nickname` | Thiếu giá trị cho option String |

Các ví dụ dùng cú pháp parser của Spring Shell 4.0.4. Khi dự án dùng parser tùy chỉnh hoặc nâng/hạ phiên bản, hãy kiểm thử các trường hợp giá trị rỗng và dấu nháy trong shell tích hợp của ứng dụng.

## Option optional và giá trị nhận trong Spring Shell 4.x

`@Option` trong Spring Shell 4.x có thuộc tính `required`; mặc định là `false`. Khi option optional không được truyền và không khai báo giá trị mặc định, tham số kiểu tham chiếu như `String` nhận `null` trong Spring Shell 4.0.1 trở đi.

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ProfileCommands {

    @Command(name = "profile-show")
    public String show(
            @Option(longName = "nickname", required = false) String nickname) {

        if (nickname == null) {
            return "Không có bộ lọc biệt danh.";
        }
        if (nickname.isEmpty()) {
            return "Bộ lọc biệt danh là chuỗi rỗng.";
        }
        if (nickname.isBlank()) {
            return "Bộ lọc biệt danh chỉ chứa khoảng trắng.";
        }
        return "Tìm theo biệt danh: " + nickname;
    }
}
```

Phương thức trên thể hiện thứ tự kiểm tra cần thiết: kiểm tra `null` trước, sau đó mới kiểm tra chuỗi rỗng và chuỗi trắng. Vì `isBlank()` trả về `true` cho cả `""` lẫn chuỗi chỉ có khoảng trắng, cần kiểm tra `isEmpty()` trước nếu nghiệp vụ muốn phân biệt hai trường hợp.

### Lưu ý thay đổi giữa 4.0.0 và 4.0.1

Spring Shell 4.0.0 từng có thay đổi ngoài ý muốn: option kiểu String không được truyền nhận `""` thay vì `null`, khác với hành vi của 3.x. Vấn đề này được ghi nhận trong issue #1273 và sửa bằng commit `6ad1448`: nếu không có `defaultValue`, các kiểu tham chiếu nhận `null`; kiểu nguyên thủy nhận giá trị mặc định của kiểu Java. Bản sửa được đưa vào dòng 4.0.1.

Vì vậy, khi đọc code cũ hoặc điều tra hành vi khác nhau giữa môi trường, hãy kiểm tra chính xác phiên bản Spring Shell. Không dựa vào hành vi quan sát được trên 4.0.0 để kết luận cách xử lý của các bản 4.x sau đó.

### Khi có defaultValue

Nếu khai báo `defaultValue`, Spring Shell dùng giá trị đó khi người dùng không truyền option:

```java
@Command(name = "report-list")
public String list(
        @Option(longName = "status", defaultValue = "active") String status) {
    return "Lọc báo cáo theo trạng thái: " + status;
}
```

Khi gọi `report-list`, phương thức nhận `"active"`. Khi gọi `report-list --status=archived`, phương thức nhận `"archived"`.

Default value thay đổi ý nghĩa của trạng thái vắng mặt: tham số không còn là `null` để biểu thị người dùng bỏ qua. Nếu nghiệp vụ cần phân biệt rõ “không truyền” với “truyền đúng giá trị mặc định”, hãy cân nhắc không khai báo default ở tham số đó và xử lý trường hợp `null` trong command. Giá trị mặc định là chính sách của command, không phải bằng chứng rằng người dùng đã nhập option.

## Xử lý whitespace và chuẩn hóa chuỗi

`String.isBlank()` kiểm tra xem chuỗi rỗng hoặc chỉ chứa ký tự trắng hay không. Phương thức này phù hợp khi quy tắc nghiệp vụ yêu cầu có ít nhất một ký tự nội dung.

```java
String value = "   ";

if (value == null) {
    // Người dùng không truyền option.
} else if (value.isEmpty()) {
    // Người dùng truyền chuỗi rỗng.
} else if (value.isBlank()) {
    // Người dùng truyền ký tự trắng, nhưng không có nội dung.
} else {
    // Có nội dung thực sự.
}
```

Nếu nghiệp vụ xem chuỗi rỗng và chuỗi trắng là tương đương, có thể chuẩn hóa bằng `strip()` sau khi đã xử lý `null`:

```java
String normalized = value == null ? null : value.strip();

if (normalized == null || normalized.isEmpty()) {
    // Không có nội dung để tìm kiếm.
} else {
    // Dùng normalized cho truy vấn.
}
```

`strip()` loại bỏ khoảng trắng ở đầu và cuối chuỗi theo quy tắc `Character.isWhitespace`. Nó không xóa khoảng trắng nằm giữa các từ. Ví dụ `"  Lan Nguyen  "` trở thành `"Lan Nguyen"`.

Không nên tự động trim mọi đầu vào. Với một số dữ liệu, khoảng trắng có ý nghĩa hoặc cần được giữ nguyên, chẳng hạn nội dung ghi chú, chuỗi mật khẩu hoặc dữ liệu định dạng. Hãy quy định rõ chính sách chuẩn hóa cho từng tham số.

Lưu ý rằng `isBlank()` và `strip()` dựa trên định nghĩa whitespace của Java (`Character.isWhitespace`). Một số ký tự khoảng trắng Unicode đặc biệt, ví dụ non-breaking space, có thể cần quy tắc chuẩn hóa riêng nếu ứng dụng nhận dữ liệu copy từ tài liệu hoặc trình duyệt.

## Chọn validation phù hợp

Spring Shell tích hợp Bean Validation và thực hiện kiểm tra tham số trước khi gọi command. Chọn constraint theo đúng chính sách về việc option có được phép vắng mặt, rỗng hay chỉ chứa khoảng trắng hay không.

| Constraint | `null` | `""` | `"   "` | Khi nào dùng |
|---|---:|---:|---:|---|
| `@NotNull` | Không hợp lệ | Hợp lệ | Hợp lệ | Bắt buộc có đối tượng String, nhưng không quan tâm nội dung |
| `@NotEmpty` | Không hợp lệ | Không hợp lệ | Hợp lệ | Không chấp nhận null hoặc độ dài bằng 0 |
| `@NotBlank` | Không hợp lệ | Không hợp lệ | Không hợp lệ | Cần ít nhất một ký tự không phải whitespace |
| `@Size(min = 1)` | Hợp lệ | Không hợp lệ | Hợp lệ | Cho phép null nhưng không cho chuỗi độ dài 0 |

### Option bắt buộc và không được rỗng/trắng

Khi option bắt buộc, kết hợp `required = true` để yêu cầu người dùng cung cấp option và `@NotBlank` để kiểm tra nội dung:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "user-create")
public String create(
        @Option(longName = "name", required = true)
        @NotBlank(message = "Tên người dùng không được để trống hoặc chỉ chứa khoảng trắng")
        String name) {
    return "Đã tạo người dùng: " + name;
}
```

Hai lớp kiểm tra có vai trò khác nhau:

- `required = true` yêu cầu option `--name` phải xuất hiện.
- `@NotBlank` từ chối `null`, `""` và chuỗi chỉ có whitespace trước khi command thực thi.

### Option không bắt buộc nhưng nếu xuất hiện phải có nội dung

Không nên đặt `@NotBlank` trực tiếp lên một option optional nếu việc bỏ qua là hợp lệ. `@NotBlank` cũng từ chối `null`, vì vậy trường hợp người dùng không truyền option sẽ không qua validation.

Thay vào đó, kiểm tra điều kiện trong command hoặc dùng constraint tùy chỉnh có ngữ nghĩa phù hợp:

```java
@Command(name = "customer-search")
public String search(
        @Option(longName = "email", description = "Email dùng để lọc kết quả") String email) {

    if (email == null) {
        return "Tìm khách hàng mà không áp dụng bộ lọc email.";
    }
    if (email.isBlank()) {
        throw new IllegalArgumentException("Email không được rỗng hoặc chỉ chứa khoảng trắng.");
    }

    return "Tìm khách hàng theo email: " + email;
}
```

Trong ví dụ này, không truyền `--email` là hợp lệ; truyền `--email=""` hoặc `--email="   "` là không hợp lệ. Nếu muốn chuỗi rỗng có nghĩa là xóa bộ lọc hoặc xóa dữ liệu, hãy xử lý riêng bằng `isEmpty()` trước `isBlank()`.

### Phân biệt @NotEmpty và @NotBlank

Hai constraint này thường bị nhầm:

- `@NotEmpty` chỉ yêu cầu giá trị khác `null` và có độ dài lớn hơn 0. Chuỗi `"   "` vẫn hợp lệ.
- `@NotBlank` yêu cầu có ít nhất một ký tự không phải whitespace. Chuỗi rỗng và chuỗi chỉ có khoảng trắng đều không hợp lệ.

Ví dụ, mã định danh `"   "` không nên được chấp nhận chỉ vì độ dài lớn hơn 0. Với trường hợp này, `@NotBlank` thể hiện đúng quy tắc hơn.

## Mô hình xử lý ba trạng thái trong nghiệp vụ

Một command cập nhật hồ sơ có thể dùng ba trạng thái để biểu diễn thao tác rõ ràng:

```java
@Command(name = "profile-update")
public String update(
        @Option(longName = "nickname", description = "Biệt danh mới; chuỗi rỗng để xóa")
        String nickname) {

    if (nickname == null) {
        return "Giữ nguyên biệt danh hiện tại.";
    }
    if (nickname.isEmpty()) {
        profileService.clearNickname();
        return "Đã xóa biệt danh.";
    }
    if (nickname.isBlank()) {
        throw new IllegalArgumentException("Biệt danh không được chỉ chứa khoảng trắng.");
    }

    profileService.updateNickname(nickname.strip());
    return "Đã cập nhật biệt danh.";
}
```

`profileService` là service nghiệp vụ do ứng dụng định nghĩa. Cách ánh xạ trạng thái trong ví dụ:

| Lệnh | Giá trị tham số | Hành động |
|---|---|---|
| `profile-update` | `null` | Giữ nguyên biệt danh |
| `profile-update --nickname=""` | `""` | Xóa biệt danh |
| `profile-update --nickname="   "` | Chuỗi trắng | Từ chối dữ liệu |
| `profile-update --nickname="Lan"` | `"Lan"` | Cập nhật biệt danh |

Mô hình này hữu ích cho thao tác cập nhật một phần dữ liệu. Tuy nhiên, nếu API nghiệp vụ không cần phân biệt “giữ nguyên” và “xóa”, có thể chọn quy tắc đơn giản hơn, chẳng hạn coi cả `null` và chuỗi trắng là không có bộ lọc.

## Kiểm thử các trường hợp đầu vào

Nên kiểm thử parser và command bằng các đầu vào đại diện cho từng trạng thái:

| Đầu vào | Giá trị mong đợi trong command | Kết quả cần xác minh |
|---|---|---|
| `customer-search` | `null` | Option optional được bỏ qua |
| `customer-search --email=""` | `""` | Chuỗi rỗng được phân biệt với null |
| `customer-search --email="   "` | Chuỗi ba dấu cách | Khoảng trắng bên trong dấu nháy được giữ nguyên |
| `customer-search --email="a@b.test"` | `"a@b.test"` | Giá trị bình thường được truyền đúng |
| `customer-search --email` | Không gọi command thành công | Parser báo thiếu giá trị cho option String |
| `user-create` | Không thực thi method | Option required bị thiếu |
| `user-create --name=""` | Validation thất bại | `@NotBlank` từ chối chuỗi rỗng |
| `user-create --name="   "` | Validation thất bại | `@NotBlank` từ chối chuỗi trắng |

Khi kiểm thử, hãy xác nhận cả giá trị mà method nhận được và phản hồi của shell. Chỉ gọi trực tiếp method Java không kiểm tra được parser có giữ đúng chuỗi rỗng hoặc whitespace đã đặt trong dấu nháy hay không.

Các nhóm kiểm thử nên bao gồm:

1. Option không xuất hiện, có và không có `defaultValue`.
2. Option xuất hiện với giá trị rỗng được đặt trong dấu nháy.
3. Option xuất hiện với một hoặc nhiều dấu cách bên trong dấu nháy.
4. Option có khoảng trắng đầu/cuối và khoảng trắng giữa các từ.
5. Option thiếu giá trị và option bắt buộc bị bỏ qua.
6. Validation với `@NotNull`, `@NotEmpty`, `@NotBlank` hoặc logic tùy chỉnh.
7. Hành vi trên đúng phiên bản Spring Shell được khai báo trong dự án.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `NullPointerException` khi gọi `isBlank()` | Option optional không xuất hiện và giá trị là `null` | Kiểm tra `null` trước |
| Option bỏ qua nhưng method nhận `""` | Dự án đang dùng Spring Shell 4.0.0 hoặc có default/logic chuyển đổi riêng | Kiểm tra phiên bản; bản sửa null cho kiểu tham chiếu có từ 4.0.1 |
| `@NotBlank` làm option optional luôn lỗi khi bỏ qua | Constraint từ chối cả `null` | Bỏ `@NotBlank` hoặc thay bằng kiểm tra có điều kiện khi option có mặt |
| `@NotEmpty` vẫn chấp nhận dấu cách | Constraint chỉ kiểm tra null và độ dài | Dùng `@NotBlank` hoặc `isBlank()` nếu whitespace không hợp lệ |
| Dấu cách trong giá trị biến mất hoặc tách thành nhiều token | Giá trị không được đặt trong dấu nháy | Dùng `--option="nhiều từ"` |
| `--option` báo thiếu giá trị | Option String được khai báo nhưng không có token giá trị | Truyền giá trị, dùng `--option=""` nếu chủ đích là chuỗi rỗng, hoặc bỏ hẳn option nếu muốn biểu thị vắng mặt |
| Dữ liệu bị thay đổi ngoài ý muốn | Tự động `trim()`/`strip()` mọi tham số | Chỉ chuẩn hóa theo quy tắc của từng trường nghiệp vụ |

## Quy trình xử lý đầu vào String

Khi thiết kế command có option kiểu String, hãy xác định trước ý nghĩa của từng trạng thái rồi triển khai theo thứ tự:

1. Quyết định option là bắt buộc hay optional.
2. Nếu optional, quyết định trường hợp vắng mặt có nghĩa là bỏ qua, dùng mặc định hay giữ nguyên dữ liệu.
3. Quyết định chuỗi rỗng có hợp lệ hay mang ý nghĩa xóa dữ liệu.
4. Quyết định chuỗi chỉ chứa whitespace có hợp lệ hay cần từ chối.
5. Dùng `required`, `defaultValue` và Bean Validation đúng với chính sách đó.
6. Kiểm tra `null` trước khi gọi phương thức trên String.
7. Chỉ chuẩn hóa khoảng trắng khi nghiệp vụ cho phép.
8. Viết kiểm thử tích hợp cho absent, empty, blank và valid text.

Khi tách rõ các trạng thái này, command có thể xử lý đúng ý định người dùng, đồng thời tránh việc dữ liệu rỗng vô tình ghi đè thông tin hiện có hoặc dữ liệu chỉ có dấu cách lọt qua validation.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): quy tắc tách từ, quote, escape và giá trị option.
- [Spring Shell 4.0.4 API — Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): thuộc tính `required` và `defaultValue`.
- [Spring Shell 4.0.4 — Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html): Bean Validation trên tham số command và validation trước khi thực thi.
- [Spring Shell 3.4.1 — Optional Value](https://docs.spring.io/spring-shell/reference/options/optional.html): khai báo option optional và mandatory trong các mô hình 3.x.
- [Spring Shell 3.4.1 — Default Value](https://docs.spring.io/spring-shell/reference/options/default.html): hành vi khi option không được truyền và có default value.
- [Spring Shell issue #1273](https://github.com/spring-projects/spring-shell/issues/1273): hồi quy ở 4.0.0 khi option String vắng mặt nhận chuỗi rỗng thay vì null.
- [Spring Shell commit 6ad1448](https://github.com/spring-projects/spring-shell/commit/6ad1448a44629cc35b4e3e95c6c3a9e3b20010fc): sửa hành vi mặc định của option không có default value cho kiểu tham chiếu.
- [Jakarta Validation 3.1 — @NotBlank](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/NotBlank.html): constraint yêu cầu giá trị khác null và có ít nhất một ký tự không phải whitespace.
- [Jakarta Validation 3.1 — @NotEmpty](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/NotEmpty.html): constraint từ chối null và giá trị rỗng.
