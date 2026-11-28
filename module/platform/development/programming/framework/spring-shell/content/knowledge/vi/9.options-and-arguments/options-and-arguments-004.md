# Phân biệt không truyền, truyền chuỗi rỗng và truyền giá trị null

Khi xây dựng CLI, một tham số có thể không xuất hiện trên dòng lệnh, xuất hiện với giá trị là chuỗi rỗng hoặc mang giá trị Java `null`. Ba trường hợp này có ý nghĩa khác nhau. Nếu gộp chúng thành một trường hợp “không có nội dung”, command có thể vô tình xóa dữ liệu, ghi đè giá trị đang có hoặc bỏ qua một yêu cầu cập nhật.

Ví dụ, một command cập nhật ghi chú hồ sơ có thể cần ba hành vi:

- Người dùng không truyền `--note`: giữ nguyên ghi chú hiện tại.
- Người dùng truyền `--note=""`: cập nhật ghi chú thành chuỗi rỗng.
- Người dùng yêu cầu xóa ghi chú: cập nhật giá trị Java thành `null`.

Spring Shell cung cấp các API để nhận biết option hoặc argument có xuất hiện trong lần gọi hay không, đồng thời giữ giá trị đầu vào. Bài học này giải thích cách phân biệt ba trạng thái, cách chúng được ánh xạ vào Java và cách thiết kế command để không làm mất ý nghĩa của dữ liệu.

## 1. Ba trạng thái không thể thay thế cho nhau

Xét một option có tên `note` kiểu `String`:

| Trạng thái | Cách gọi ví dụ | Giá trị trong Java | Ý nghĩa |
|---|---|---|---|
| Không truyền | `profile` | `null` nếu option tùy chọn và không có mặc định | Người dùng không đưa ra chỉ dẫn cho trường này |
| Truyền chuỗi rỗng | `profile --note=""` | `""` | Người dùng chủ động cung cấp một giá trị có độ dài bằng 0 |
| Truyền chữ `null` | `profile --note=null` | `"null"` | Người dùng truyền bốn ký tự n, u, l, l |
| Giá trị Java null | Không có token CLI tương ứng | `null` | Tham chiếu Java không trỏ tới đối tượng nào |

Trong một command line, terminal truyền văn bản. Vì vậy, gõ `null` không tự tạo ra một tham chiếu Java null. Parser nhận được chuỗi ký tự `"null"`; ứng dụng chỉ chuyển nó thành null nếu chủ động quy định một quy tắc ánh xạ như vậy.

Chuỗi rỗng cũng là một giá trị thật. Nó có thể mang ý nghĩa “xóa nội dung về rỗng”, “không có nhãn” hoặc “ghi đè bằng giá trị rỗng”. Không nên tự động thay `""` bằng null nếu nghiệp vụ cần phân biệt hai trạng thái này.

## 2. Spring Shell 4.x xử lý option không được truyền

Với một option không bắt buộc, không có giá trị mặc định, hành vi hiện tại của Spring Shell 4.0.1 trở lên là:

- Tham số tham chiếu như `String`, `Boolean` hoặc `Integer` nhận `null` khi người dùng bỏ qua option.
- Tham số nguyên thủy như `boolean` hoặc `int` nhận giá trị mặc định của Java, tương ứng là `false` hoặc `0`.
- Nếu khai báo `defaultValue`, command nhận giá trị mặc định khi người dùng bỏ qua option.
- Nếu khai báo `required = true`, việc bỏ qua option làm cho đầu vào không hợp lệ và command không được thực thi.

Có một khác biệt lịch sử cần lưu ý khi nâng cấp. Trong Spring Shell 3.x, một option String không được truyền có giá trị null. Spring Shell 4.0.0 từng trả về chuỗi rỗng trong trường hợp này; lỗi tương thích đó được sửa ở 4.0.1. Issue #1273 ghi rõ thay đổi này: khi không khai báo default value, kiểu tham chiếu trở lại giá trị mặc định null. Issue #1262 cũng dẫn đến việc dùng giá trị mặc định của Java cho kiểu nguyên thủy. Hãy kiểm tra phiên bản thực tế của ứng dụng nếu command đang chạy trên 4.0.0.

Ví dụ command có option tùy chọn:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ProfileCommands {

    @Command(name = "profile")
    public String profile(
            @Option(longName = "note") String note) {

        if (note == null) {
            return "Không có chỉ dẫn cập nhật ghi chú.";
        }
        if (note.isEmpty()) {
            return "Ghi chú được truyền là chuỗi rỗng.";
        }
        return "Ghi chú mới: " + note;
    }
}
~~~

Với Spring Shell 4.0.1 trở lên, gọi `profile` sẽ đưa null vào tham số `note`. Gọi `profile --note=""` sẽ đưa chuỗi rỗng vào tham số. Command có thể xử lý hai trường hợp theo hai nhánh khác nhau.

## 3. Truyền chuỗi rỗng một cách tường minh

Để gửi một giá trị rỗng, hãy đặt cặp dấu nháy ngay sau dấu bằng hoặc sau tên option:

~~~text
profile --note=""
profile --note ''
~~~

Dấu nháy bao ngoài được parser loại bỏ. Giá trị mà command nhận được là một String có độ dài bằng 0:

~~~java
String note = "";

note != null;       // true
note.isEmpty();     // true
note.length() == 0; // true
~~~

Không nhầm chuỗi rỗng với chuỗi chỉ có khoảng trắng:

| Giá trị | `isEmpty()` | `isBlank()` |
|---|---:|---:|
| `null` | Không gọi được trực tiếp | Không gọi được trực tiếp |
| `""` | `true` | `true` |
| `"   "` | `false` | `true` |
| `"note"` | `false` | `false` |
| `"null"` | `false` | `false` |

Trước khi gọi `isEmpty()` hoặc `isBlank()`, phải kiểm tra null. Ví dụ:

~~~java
if (note == null) {
    // Option không được truyền.
} else if (note.isEmpty()) {
    // Option được truyền với chuỗi rỗng.
} else if (note.isBlank()) {
    // Option có ký tự nhưng tất cả đều là khoảng trắng.
} else {
    // Option có nội dung.
}
~~~

## 4. Chữ null trên dòng lệnh không phải Java null

Khi người dùng gọi:

~~~text
profile --note=null
~~~

Với tham số kiểu String, giá trị nhận được là `"null"`:

~~~java
String note = "null";

note == null;       // false
"null".equals(note); // true
~~~

Điều này cũng đúng với các chuỗi như `"NULL"` hoặc `"Null"`; Java không tự chuyển chúng thành null. Với tham số có kiểu khác, converter có thể từ chối chuỗi đó nếu nó không phải giá trị hợp lệ của kiểu đích.

Không nên dùng chữ `null` làm quy ước ngầm để xóa dữ liệu trừ khi đó là cú pháp được sản phẩm định nghĩa rõ ràng. Nếu người dùng thực sự muốn lưu văn bản `null`, quy ước này sẽ khiến giá trị hợp lệ bị hiểu sai.

Nếu cần một thao tác xóa rõ ràng, hãy tạo option riêng như `--clear-note=true` hoặc command riêng như `profile clear-note`. Khi đó ứng dụng chủ động gán null trong code; terminal không cần giả lập một tham chiếu Java.

## 5. Dùng CommandContext để biết option có được truyền hay không

Giá trị của tham số phương thức giúp xử lý dữ liệu, nhưng đôi khi cần biết người dùng có thực sự gõ option hay không. Ví dụ, command khai báo `defaultValue` là `guest`. Khi người dùng bỏ qua option, tham số phương thức nhận `guest`; khi người dùng chủ động truyền `--name=guest`, tham số cũng nhận đúng chuỗi đó. Chỉ nhìn vào tham số đã bind thì không phân biệt được hai lần gọi.

Trong Spring Shell 4.x, có thể dùng `CommandContext` để kiểm tra dữ liệu đã parse:

~~~java
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ProfileCommands {

    @Command(name = "inspect-note")
    public String inspectNote(
            CommandContext context,
            @Option(longName = "note", defaultValue = "guest") String note) {

        CommandOption parsedOption =
                context.getOptionByLongName("note");

        if (parsedOption == null) {
            return "Không truyền --note; giá trị bind là: " + note;
        }

        String rawValue = parsedOption.value();
        if (rawValue == null) {
            return "Option có mặt nhưng không có giá trị chuỗi.";
        }
        if (rawValue.isEmpty()) {
            return "Người dùng đã truyền chuỗi rỗng.";
        }
        return "Người dùng đã truyền: " + rawValue;
    }
}
~~~

`getOptionByLongName("note")` trả về option đã được nhận diện trong lần gọi hoặc null nếu không tìm thấy. Do đó:

- Kết quả null cho biết option không xuất hiện trong dữ liệu đã parse.
- Một `CommandOption` có `value()` bằng `""` cho biết option được truyền với chuỗi rỗng.
- Một `CommandOption` có `value()` bằng `"null"` cho biết người dùng truyền văn bản null.

`CommandOption.value()` được đánh dấu nullable trong API. Vì vậy, ngay cả khi đã tìm thấy đối tượng option, vẫn nên kiểm tra value trước khi gọi các phương thức String.

Nếu command cần phân biệt trạng thái người dùng nhập với giá trị mặc định đã bind, hãy kiểm tra `CommandContext` hoặc `ParsedInput`. Đừng suy ra trạng thái “đã truyền” chỉ từ việc tham số phương thức khác null.

## 6. Argument cũng có trạng thái vắng mặt và giá trị

Argument là dữ liệu theo vị trí. Ví dụ:

~~~java
@Command(name = "report")
public String report(
        CommandContext context,
        @Argument(index = 0, defaultValue = "monthly") String period) {

    CommandArgument parsedArgument =
            context.getArgumentByIndex(0);

    if (parsedArgument == null) {
        return "Không truyền kỳ báo cáo; dùng giá trị bind: " + period;
    }

    return "Kỳ báo cáo được truyền: " + parsedArgument.value();
}
~~~

Gọi `report` không cung cấp argument ở index 0; giá trị mặc định được bind vào tham số `period`. Gọi `report ""` cung cấp một argument là chuỗi rỗng. Khi cần phân biệt người dùng có đưa argument hay không, kiểm tra `getArgumentByIndex(0)` trong `CommandContext`.

Không nên đánh đồng một argument rỗng với việc không có argument. Với command có nhiều argument, việc giữ đúng index và trạng thái hiện diện đặc biệt quan trọng vì mỗi vị trí có thể mang ý nghĩa khác nhau.

## 7. required, defaultValue và validation giải quyết các vấn đề khác nhau

Ba cơ chế này có mục đích riêng:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| `required = true` | Người dùng có bắt buộc phải cung cấp option không? | Bắt buộc truyền đường dẫn đích |
| `defaultValue` | Nếu bỏ qua, command dùng giá trị nào? | Mặc định định dạng là `csv` |
| Bean Validation | Giá trị được truyền có hợp lệ không? | Không chấp nhận chuỗi rỗng hoặc chỉ có khoảng trắng |

`required = true` kiểm tra sự hiện diện của option. Nếu yêu cầu nghiệp vụ là phải có nội dung thực, hãy dùng thêm validation như `@NotBlank`:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "set-owner")
public String setOwner(
        @Option(longName = "name", required = true)
        @NotBlank
        String name) {
    return "Chủ sở hữu mới: " + name;
}
~~~

Phân biệt các constraint:

- `@NotNull` từ chối null nhưng vẫn chấp nhận chuỗi rỗng.
- `@NotEmpty` từ chối null và chuỗi rỗng, nhưng vẫn chấp nhận chuỗi chỉ có khoảng trắng.
- `@NotBlank` từ chối null, chuỗi rỗng và chuỗi chỉ có khoảng trắng.

Spring Shell tích hợp Bean Validation và chạy các constraint trên tham số trước khi thực thi command. Ứng dụng cần có implementation Bean Validation tương ứng trong classpath.

## 8. Ví dụ nghiệp vụ: cập nhật hoặc xóa ghi chú

Trong API cập nhật dữ liệu, ba trạng thái thường được ánh xạ như sau:

| Đầu vào CLI | Hành động nghiệp vụ |
|---|---|
| Không truyền `--note` và không truyền `--clear-note` | Giữ nguyên ghi chú hiện tại |
| `--note=""` | Ghi đè ghi chú bằng chuỗi rỗng |
| `--note="Nội dung mới"` | Ghi đè bằng nội dung mới |
| `--clear-note=true` | Xóa ghi chú, lưu Java null |

Ví dụ:

~~~java
@Component
class ProfileCommands {

    private final ProfileService profileService;

    ProfileCommands(ProfileService profileService) {
        this.profileService = profileService;
    }

    @Command(name = "profile update-note")
    public String updateNote(
            CommandContext context,
            @Option(longName = "note") String note,
            @Option(longName = "clear-note", defaultValue = "false")
            boolean clearNote) {

        CommandOption noteOption =
                context.getOptionByLongName("note");
        boolean noteWasProvided = noteOption != null;

        if (clearNote && noteWasProvided) {
            throw new IllegalArgumentException(
                    "Chỉ chọn --note hoặc --clear-note, không dùng cả hai.");
        }

        if (clearNote) {
            profileService.updateNote(null);
            return "Đã xóa ghi chú.";
        }

        if (noteWasProvided) {
            profileService.updateNote(note);
            return note.isEmpty()
                    ? "Đã cập nhật ghi chú thành chuỗi rỗng."
                    : "Đã cập nhật ghi chú.";
        }

        return "Không thay đổi ghi chú.";
    }
}
~~~

Các lệnh minh họa:

~~~text
profile update-note
profile update-note --note=""
profile update-note --note="Gọi lại vào thứ Sáu"
profile update-note --clear-note=true
~~~

Command chỉ gọi `updateNote(null)` khi người dùng chọn hành động xóa rõ ràng. Nếu người dùng không truyền option, service không bị gọi và dữ liệu cũ được giữ nguyên. Nếu người dùng truyền chuỗi rỗng, service nhận chính chuỗi rỗng.

## 9. Kiểm thử cả ba trạng thái

Khi kiểm thử command, đừng chỉ kiểm tra trường hợp có nội dung. Cần kiểm tra riêng các trạng thái:

| Lệnh gửi | Kết quả mong đợi |
|---|---|
| `profile update-note` | Service không nhận yêu cầu cập nhật |
| `profile update-note --note=""` | Service nhận `""` |
| `profile update-note --note=null` | Service nhận chuỗi `"null"` |
| `profile update-note --clear-note=true` | Service nhận Java null |
| `profile update-note --note="   "` | Validation hoặc quy tắc nghiệp vụ xử lý khoảng trắng theo yêu cầu |
| `profile update-note --note="Mới" --clear-note=true` | Command báo xung đột tham số |

Với `ShellTestClient`, gửi từng dòng command độc lập và kiểm tra output hoặc tương tác với mock service. Khi kiểm tra việc giữ nguyên giá trị, assertion phải phân biệt `null`, `""` và `"null"`; không dùng assertion chung chỉ kiểm tra “không có chữ”.

Ngoài kiểm thử command, nên kiểm thử service riêng để bảo đảm:

- Không gọi cập nhật khi trường không được truyền.
- Ghi chuỗi rỗng đúng như dữ liệu đầu vào.
- Lưu null khi có yêu cầu xóa rõ ràng.
- Không tự chuyển chuỗi `"null"` thành null nếu nghiệp vụ không quy định.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Option bỏ qua nhưng code nhận chuỗi rỗng | Đang dùng Spring Shell 4.0.0 hoặc có logic tự thay null bằng `""` | Nâng lên bản 4.0.1 trở lên và kiểm tra nơi chuẩn hóa dữ liệu |
| Không phân biệt được không truyền với default value | Chỉ kiểm tra tham số đã bind vào phương thức | Dùng `CommandContext` để kiểm tra option có xuất hiện trong lần gọi |
| Gõ `--note=null` nhưng code không nhận null | Parser nhận chuỗi literal `"null"` | Dùng option xóa riêng và gán null trong code |
| Chuỗi rỗng bị coi là hợp lệ | Chỉ kiểm tra null hoặc dùng `@NotNull` | Dùng `@NotEmpty` hoặc `@NotBlank` theo yêu cầu |
| Chuỗi khoảng trắng lọt qua validation | Dùng `@NotEmpty` | Dùng `@NotBlank` nếu khoảng trắng không được chấp nhận |
| Không thể xóa trường trong thao tác cập nhật | Command gộp “không truyền” và “xóa” thành một trạng thái | Thêm option hoặc command xóa rõ ràng |
| Giá trị mặc định ghi đè lựa chọn rỗng | Code tự thay mọi giá trị blank bằng default | Chỉ áp dụng default khi option thực sự không được truyền |

## 11. Bài tập thực hành

Tạo command `settings set-timezone` với option `--zone` và `--clear`:

- Nếu không truyền cả hai option, giữ nguyên múi giờ hiện tại.
- Nếu truyền `--zone=""`, command phải nhận chuỗi rỗng và báo lỗi vì múi giờ không thể rỗng.
- Nếu truyền `--zone=Asia/Ho_Chi_Minh`, cập nhật múi giờ.
- Nếu truyền `--clear=true`, đặt múi giờ về Java null để hệ thống dùng cấu hình mặc định.
- Nếu truyền đồng thời `--zone` và `--clear=true`, báo lỗi xung đột.

Thử các lệnh:

~~~text
settings set-timezone
settings set-timezone --zone=""
settings set-timezone --zone=Asia/Ho_Chi_Minh
settings set-timezone --clear=true
settings set-timezone --zone=UTC --clear=true
~~~

Sau khi hoàn thành, hãy kiểm tra:

1. Command có nhận biết option đã xuất hiện hay chưa?
2. Chuỗi rỗng có được phân biệt với null không?
3. Chữ `null` có còn là một chuỗi thông thường không?
4. Giá trị mặc định có chỉ áp dụng khi người dùng bỏ qua option không?
5. Lệnh xóa có tạo ra Java null một cách tường minh không?

## Tài liệu tham khảo

- [Spring Shell – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell – Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell API – CommandContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html)
- [Spring Shell API – CommandOption](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html)
- [Spring Shell API – @Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Shell – Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Shell issue #1273 – Null default for omitted String options](https://github.com/spring-projects/spring-shell/issues/1273)
- [Spring Shell issue #1262 – Default values for primitive options](https://github.com/spring-projects/spring-shell/issues/1262)
- [Spring Shell – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
