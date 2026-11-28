# `ShellOption.NULL` và quy ước legacy 3.x

Trong mô hình annotation legacy của Spring Shell 3.x, `@ShellOption` dùng thuộc tính `defaultValue` để quyết định điều gì xảy ra khi người dùng không truyền một option. Một giá trị đặc biệt là `ShellOption.NULL`: nó đánh dấu option không bắt buộc và yêu cầu Spring Shell truyền Java `null` vào tham số nếu người dùng bỏ qua option đó.

Điểm này dễ gây nhầm lẫn vì `ShellOption.NULL` và `ShellOption.NONE` có ý nghĩa trái ngược nhau. `NULL` có nghĩa là *có giá trị mặc định và giá trị đó là null*; `NONE` có nghĩa là *không có giá trị mặc định*, do đó tham số là bắt buộc. Bài học này giải thích quy ước đó trong bộ annotation legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption` của Spring Shell 3.x, đồng thời phân biệt nó với mô hình annotation mới.

## 1. Vì sao cần `ShellOption.NULL`?

Một command có thể nhận dữ liệu bắt buộc và dữ liệu tùy chọn. Ví dụ khi tìm người dùng, email có thể không được cung cấp; nếu không có email, command sẽ tìm theo trạng thái hoặc trả về danh sách mặc định.

Java cần biểu diễn được hai tình huống:

- Người dùng đã truyền một giá trị, ví dụ `--email linh@example.com`.
- Người dùng bỏ qua option `--email`, vì vậy phương thức nhận `null`.

Trong legacy annotation model, `@ShellOption` không có thuộc tính `required = false`. Cách đánh dấu option tùy chọn là đặt `defaultValue = ShellOption.NULL`:

```java
@ShellMethod(key = "user search")
public String search(
        @ShellOption(value = "--email", defaultValue = ShellOption.NULL)
        String email) {

    if (email == null) {
        return "Tìm người dùng mà không lọc theo email";
    }

    return "Tìm người dùng theo email " + email;
}
```

Hai cách gọi thể hiện hai kết quả khác nhau:

```text
shell:> user search --email linh@example.com
Tìm người dùng theo email linh@example.com

shell:> user search
Tìm người dùng mà không lọc theo email
```

Khi không có `--email`, Spring Shell truyền `null` cho tham số `email`. Phương thức có thể kiểm tra `email == null` để chọn nhánh xử lý phù hợp.

## 2. Phân biệt `ShellOption.NULL`, `ShellOption.NONE` và giá trị mặc định thông thường

`ShellOption.defaultValue()` là một chuỗi được chuyển đổi sang kiểu tham số. Spring Shell định nghĩa hai marker đặc biệt để phân biệt “không có default” với “default là null”.

| Cách khai báo | Ý nghĩa khi người dùng bỏ qua option | Trạng thái |
| --- | --- | --- |
| `@ShellOption()` | Không có giá trị mặc định; thiếu option là lỗi | Bắt buộc |
| `@ShellOption(defaultValue = ShellOption.NONE)` | Không có giá trị mặc định; thiếu option là lỗi | Bắt buộc |
| `@ShellOption(defaultValue = ShellOption.NULL)` | Gán Java `null` cho tham số | Tùy chọn |
| `@ShellOption(defaultValue = "ACTIVE")` | Gán chuỗi `ACTIVE`, sau đó chuyển đổi theo kiểu tham số | Có giá trị mặc định |

`ShellOption.NONE` là giá trị mặc định của thuộc tính `defaultValue`; vì vậy, khai báo `@ShellOption()` đã có nghĩa là tham số bắt buộc. Thông thường không cần ghi `defaultValue = ShellOption.NONE` một cách tường minh, trừ khi muốn nhấn mạnh quy ước trong ví dụ hoặc tài liệu.

Ví dụ so sánh ba cách khai báo:

```java
@ShellMethod(key = "user inspect")
public String inspect(
        @ShellOption(value = "--id") Long id,
        @ShellOption(value = "--email", defaultValue = ShellOption.NULL) String email,
        @ShellOption(value = "--status", defaultValue = "ACTIVE") String status) {

    return "id=" + id + ", email=" + email + ", status=" + status;
}
```

Khi gọi `user inspect --id 42`, `id` được truyền từ người dùng, `email` nhận `null`, còn `status` nhận `ACTIVE`. Nếu bỏ `--id`, shell báo thiếu tham số bắt buộc và không gọi phương thức với một mã người dùng hợp lệ.

Không nên thay `ShellOption.NULL` bằng chuỗi ký tự `"null"`. Chuỗi `"null"` là dữ liệu văn bản thông thường và với tham số `String`, phương thức nhận đúng bốn ký tự `n`, `u`, `l`, `l`; nó không phải Java `null`. Hãy dùng hằng `ShellOption.NULL` để framework nhận biết marker đặc biệt.

## 3. Ví dụ thực tế: tìm kiếm với nhiều option tùy chọn

Command tìm kiếm thường có một số bộ lọc không bắt buộc. Nếu tất cả bộ lọc đều bị bỏ qua, command có thể trả về danh sách mặc định; nếu người dùng truyền một bộ lọc, command áp dụng bộ lọc đó.

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class UserSearchCommands {

    @ShellMethod(key = "user search", value = "Tìm người dùng theo bộ lọc.")
    public String search(
            @ShellOption(value = "--email", defaultValue = ShellOption.NULL)
            String email,
            @ShellOption(value = "--status", defaultValue = "ACTIVE")
            String status,
            @ShellOption(value = "--min-age", defaultValue = ShellOption.NULL)
            Integer minAge) {

        StringBuilder result = new StringBuilder("Bộ lọc: status=")
                .append(status);

        if (email != null) {
            result.append(", email=").append(email);
        }

        if (minAge != null) {
            result.append(", minAge=").append(minAge);
        }

        return result.toString();
    }
}
```

Các lời gọi minh họa:

```text
shell:> user search
Bộ lọc: status=ACTIVE

shell:> user search --email linh@example.com
Bộ lọc: status=ACTIVE, email=linh@example.com

shell:> user search --status DISABLED --min-age 21
Bộ lọc: status=DISABLED, minAge=21

shell:> user search --email linh@example.com --status DISABLED --min-age 21
Bộ lọc: status=DISABLED, email=linh@example.com, minAge=21
```

Trong ví dụ, `email` và `minAge` có thể nhận `null`; `status` luôn có giá trị vì đã đặt default `ACTIVE`. `Integer` được dùng cho `minAge` để có thể biểu diễn trường hợp không truyền giá trị. Nếu dùng `int`, Java không thể lưu `null` vào tham số nguyên thủy.

## 4. Dùng kiểu tham chiếu khi giá trị có thể là null

`ShellOption.NULL` yêu cầu framework truyền `null` khi option bị bỏ qua. Vì vậy, tham số phải có kiểu dữ liệu có thể nhận `null`.

| Kiểu tham số | Có thể nhận `null`? | Gợi ý sử dụng |
| --- | --- | --- |
| `String` | Có | Phù hợp với chuỗi tùy chọn |
| `Integer`, `Long`, `Double` | Có | Phù hợp với số có thể không được cung cấp |
| `Boolean` | Có | Có thể phân biệt trạng thái null với true/false nếu cú pháp và arity được cấu hình phù hợp |
| Enum | Có | Có thể dùng khi một lựa chọn enum là tùy chọn |
| `int`, `long`, `double`, `boolean` | Không | Không dùng nếu nhánh xử lý cần nhận Java `null` |

Ví dụ nên dùng wrapper type:

```java
@ShellMethod(key = "user find")
public String find(
        @ShellOption(value = "--age", defaultValue = ShellOption.NULL)
        Integer age) {

    if (age == null) {
        return "Không giới hạn độ tuổi";
    }

    return "Tìm người dùng từ " + age + " tuổi";
}
```

Nếu khai báo `int age` trong khi cấu hình yêu cầu giá trị mặc định là null, kiểu nguyên thủy không thể biểu diễn kết quả đó. Hãy đổi sang `Integer` hoặc chọn một giá trị mặc định nghiệp vụ như `0` nếu `0` thực sự có ý nghĩa trong miền dữ liệu.

Với boolean, cần chú ý thêm quy tắc arity. Legacy `@ShellOption` thường suy luận option boolean là cờ không cần giá trị; `boolean` và `Boolean` có thể có hành vi khác khi option bị bỏ qua hoặc được truyền trực tiếp. Nếu cần phân biệt rõ “không được cung cấp”, “true” và “false”, hãy thử cú pháp với kiểu wrapper `Boolean` trong đúng phiên bản Spring Shell của dự án và xác định arity rõ ràng khi cần.

## 5. `ShellOption.NULL` không làm cho giá trị sau option trở thành tùy chọn

Có hai câu hỏi khác nhau khi thiết kế option:

1. **Option có bắt buộc xuất hiện hay không?** `ShellOption.NULL` giải quyết câu hỏi này trong legacy annotation model.
2. **Khi option xuất hiện, nó nhận bao nhiêu từ làm giá trị?** Thuộc tính `arity` điều khiển số từ mà parser tiêu thụ.

Với một tham số `String`, arity mặc định thường là một. Vì vậy, `ShellOption.NULL` có nghĩa người dùng có thể bỏ qua toàn bộ option; nó không có nghĩa người dùng có thể nhập tên option mà không có giá trị theo sau.

Ví dụ, khai báo:

```java
@ShellOption(value = "--email", defaultValue = ShellOption.NULL)
String email
```

có các cách dùng sau:

```text
user search
user search --email linh@example.com
```

Nếu người dùng nhập `user search --email` mà không có giá trị theo sau, parser vẫn cần xử lý theo arity của tham số. Đó là lỗi thiếu giá trị cho một option đã xuất hiện, khác với trường hợp bỏ qua hoàn toàn option.

Nếu muốn một option có thể xuất hiện mà không kèm giá trị, hãy nghiên cứu `arity` và hành vi của kiểu dữ liệu tương ứng. Không dùng `ShellOption.NULL` như một cách thay thế cho cấu hình arity.

## 6. Phân biệt null, chuỗi rỗng và giá trị mặc định

Trong logic nghiệp vụ, ba trạng thái sau có ý nghĩa khác nhau:

| Trạng thái đầu vào | Ý nghĩa | Ví dụ xử lý |
| --- | --- | --- |
| Không truyền option | Tham số nhận `null` khi dùng `ShellOption.NULL` | Bỏ qua bộ lọc email |
| Truyền chuỗi rỗng | Người dùng đã truyền một giá trị chuỗi nhưng không có ký tự | Có thể từ chối hoặc chuẩn hóa thành không lọc |
| Không truyền option có default thông thường | Tham số nhận giá trị mặc định đã cấu hình | Dùng trạng thái `ACTIVE` |

Không nên kiểm tra mọi trường hợp chỉ bằng `isEmpty()`. Với một tham số tùy chọn, hãy xác định rõ ứng dụng có coi chuỗi rỗng là không được cung cấp hay là đầu vào không hợp lệ. Nếu cần, có thể chuẩn hóa chuỗi trước khi gọi service:

```java
String normalizedEmail = email == null || email.isBlank()
        ? null
        : email.trim();
```

Khi giá trị được truyền vào service, nên giữ một quy ước nhất quán: `null` nghĩa là không áp dụng bộ lọc; chuỗi có nội dung nghĩa là lọc theo giá trị đó. Điều này tránh việc một lớp coi `null` là “không giới hạn” trong khi lớp khác lại coi đó là lỗi.

## 7. Phân biệt legacy `@ShellOption` và annotation mới `@Option`

Spring Shell 3.x có hai mô hình annotation. `ShellOption.NULL` chỉ thuộc legacy annotation model dùng `@ShellMethod` và `@ShellOption` trong package `org.springframework.shell.standard`.

| Mô hình | Cách khai báo option tùy chọn | Ghi chú |
| --- | --- | --- |
| Legacy 3.x | `@ShellOption(defaultValue = ShellOption.NULL)` | Dùng marker để biểu diễn default null |
| Annotation mới 3.x | `@Option(required = false)` | Dùng thuộc tính `required` để đánh dấu tùy chọn |
| Programmatic 3.x | `.required(false)` | Khai báo tính tùy chọn trên `CommandRegistration` |

Ví dụ annotation mới trong Spring Shell 3.x:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;

@Command(command = "user search")
public String search(@Option(longNames = "email", required = false) String email) {
    return email == null
            ? "Tìm người dùng không lọc email"
            : "Tìm theo email " + email;
}
```

Không chuyển `ShellOption.NULL` sang `@Option(defaultValue = "NULL")`. Trong annotation mới, hãy dùng `required = false`; nếu cần một giá trị mặc định cụ thể, dùng `defaultValue` với nội dung phù hợp.

Khi nâng cấp sang thế hệ Spring Shell không còn legacy annotation, hãy chuyển command sang mô hình annotation mới và khai báo rõ `required = false`. Không mang import `org.springframework.shell.standard.ShellOption` sang một API không còn hỗ trợ legacy model.

## 8. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bỏ option nhưng shell vẫn báo thiếu tham số | `defaultValue` vẫn là `ShellOption.NONE` mặc định | Dùng `defaultValue = ShellOption.NULL` nếu tham số thực sự tùy chọn |
| Phương thức nhận chuỗi `"null"` | Dùng `defaultValue = "null"` thay cho marker | Dùng hằng `ShellOption.NULL` |
| Không thể gán null cho tham số | Dùng kiểu nguyên thủy như `int` hoặc `boolean` | Dùng kiểu wrapper như `Integer` hoặc `Boolean` khi cần null |
| Gõ `--email` nhưng parser báo thiếu giá trị | Option đã xuất hiện nhưng arity vẫn yêu cầu một giá trị | Truyền giá trị sau option hoặc cấu hình arity đúng nhu cầu |
| Dùng `ShellOption.NULL` với `@Option` | Trộn legacy annotation và annotation mới | Dùng `@Option(required = false)` trong mô hình mới |
| Bỏ qua option nhưng nghiệp vụ xử lý sai | Không kiểm tra `null` trước khi dùng tham số | Xác định nhánh xử lý cho dữ liệu vắng mặt trước khi gọi service |

## 9. Checklist khi dùng `ShellOption.NULL`

- Xác nhận command đang dùng legacy annotation model của Spring Shell 3.x.
- Dùng `@ShellOption(defaultValue = ShellOption.NULL)` cho tham số tùy chọn cần nhận Java `null`.
- Giữ `@ShellOption()` hoặc `ShellOption.NONE` cho tham số bắt buộc.
- Dùng default thông thường nếu nghiệp vụ cần một giá trị thay thế cụ thể.
- Dùng kiểu tham chiếu thay cho kiểu nguyên thủy nếu giá trị có thể là null.
- Phân biệt bỏ qua toàn bộ option với truyền option mà thiếu giá trị theo arity.
- Xác định cách xử lý chuỗi rỗng và null trong command/service.
- Nếu dùng annotation mới, khai báo `@Option(required = false)` thay cho `ShellOption.NULL`.

## Tài liệu tham khảo

- [Spring Shell 3.4.1 — Optional Value](https://docs.spring.io/spring-shell/reference/3.4/options/optional.html)
- [Spring Shell — ShellOption API](https://docs.spring.io/spring-shell/docs/current/api/org/springframework/shell/standard/ShellOption.html)
- [Spring Shell 3.4.1 — Types](https://docs.spring.io/spring-shell/reference/3.4/options/types.html)
- [Spring Shell 3.4 — Reading Docs: Legacy and New Annotation Models](https://docs.spring.io/spring-shell/reference/3.4/basics/reading.html)
- [Spring Shell 3.4 — Arity](https://docs.spring.io/spring-shell/reference/3.4/options/arity.html)
