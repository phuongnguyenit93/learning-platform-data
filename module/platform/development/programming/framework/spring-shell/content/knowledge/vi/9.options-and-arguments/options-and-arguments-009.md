# Arity của option nhiều giá trị trong Spring Shell 3.x

Một option thường nhận một giá trị, chẳng hạn `--output report.csv`. Nhưng có những command cần một option nhận nhiều giá trị cùng vai trò: nhiều nhãn, nhiều đường dẫn file, nhiều mã môi trường hoặc một dãy số. Spring Shell 3.x dùng khái niệm **arity** để xác định parser phải thu thập tối thiểu và tối đa bao nhiêu token cho một option.

Ví dụ, command triển khai ứng dụng có thể nhận từ một đến ba nhãn:

```text
deploy --tag stable
deploy --tag stable candidate
deploy --tag stable candidate production
```

Nếu người dùng không truyền giá trị nào sau `--tag`, hoặc truyền bốn giá trị trong khi giới hạn là ba, parser có thể báo lỗi trước khi gọi command. Bài học này giải thích cách khai báo arity trong Spring Shell 3.x bằng programmatic registration, annotation model mới và legacy annotation model.

## 1. Arity là gì?

Arity là số lượng token mà parser thu thập cho một option. Nó xác định khoảng số lượng giá trị được phép sau tên option. Arity không thay thế kiểu Java của tham số: kiểu `String[]` hoặc collection chứa các giá trị sau khi parser thu thập, còn arity quy định parser được phép thu thập bao nhiêu giá trị.

Phân biệt ba khái niệm:

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Kiểu tham số | Dữ liệu được nhận dưới dạng gì? | `String[]`, `List<String>`, `int[]` |
| Arity | Option nhận bao nhiêu token? | Từ 1 đến 3 giá trị |
| Required | Người dùng có bắt buộc phải truyền option không? | Phải có `--tag` trong lệnh |

Ví dụ `String[] tags` cho biết phương thức nhận một mảng chuỗi. `arity(1, 3)` giới hạn option trong khoảng một đến ba token. `required()` yêu cầu người dùng phải xuất hiện option đó trong dòng lệnh. Ba cấu hình này bổ sung cho nhau.

## 2. Các mức arity dựng sẵn

Spring Shell 3.x cung cấp enum `CommandRegistration.OptionArity` với các mức phổ biến:

| Giá trị | Số token tối thiểu | Số token tối đa | Ý nghĩa |
| --- | ---: | ---: | --- |
| `ZERO` | 0 | 0 | Option không nhận giá trị |
| `ZERO_OR_ONE` | 0 | 1 | Không bắt buộc có giá trị hoặc nhận một giá trị |
| `EXACTLY_ONE` | 1 | 1 | Nhận đúng một giá trị |
| `ZERO_OR_MORE` | 0 | Không giới hạn | Nhận danh sách rỗng hoặc nhiều giá trị |
| `ONE_OR_MORE` | 1 | Không giới hạn | Nhận ít nhất một giá trị |
| `NONE` | Chưa thiết lập | Chưa thiết lập | Chưa đặt arity tường minh; dùng quy tắc mặc định của resolver |

`ZERO`, `ZERO_OR_ONE`, `EXACTLY_ONE`, `ZERO_OR_MORE` và `ONE_OR_MORE` biểu diễn các khoảng số lượng. `NONE` là giá trị kỹ thuật cho biết arity chưa được đặt, không phải một loại option mà người dùng nhập.

Khi cần một khoảng cụ thể như từ hai đến bốn giá trị, dùng min/max thay vì enum:

```java
.arity(2, 4)
```

## 3. Khai báo arity bằng programmatic registration

Với `CommandRegistration`, dùng `withOption()` để khai báo option, kiểu dữ liệu, tính bắt buộc và arity. Ví dụ sau tạo command `deploy` nhận từ một đến ba nhãn:

```java
import java.util.Arrays;
import org.springframework.context.annotation.Bean;
import org.springframework.shell.command.CommandRegistration;

@Bean
CommandRegistration deployCommand() {
    return CommandRegistration.builder()
            .command("deploy")
            .withOption()
                .longNames("tag")
                .type(String[].class)
                .required()
                .arity(1, 3)
                .and()
            .withTarget()
                .function(context -> {
                    String[] tags = context.getOptionValue("tag");
                    return "Các nhãn triển khai: " + Arrays.toString(tags);
                })
                .and()
            .build();
}
```

Các cách gọi hợp lệ:

```text
deploy --tag stable
deploy --tag stable candidate
deploy --tag stable candidate production
```

Các trường hợp không hợp lệ:

```text
deploy
deploy --tag
deploy --tag stable candidate production emergency
```

Vì option được đánh dấu `required()`, gọi `deploy` mà không có `--tag` sẽ báo thiếu option bắt buộc. Khi đã truyền `--tag`, parser kiểm tra số lượng token: ít hơn một giá trị hoặc nhiều hơn ba giá trị đều vi phạm arity. Nếu option không bắt buộc, có thể bỏ `.required()` hoặc dùng `.required(false)`; khi option xuất hiện, giới hạn số token vẫn được áp dụng.

`type(String[].class)` rất quan trọng trong ví dụ này: nó cho biết target cần nhận một mảng chuỗi. Nếu option nhận các số nguyên, dùng kiểu mảng tương ứng như `int[].class` và kiểm tra chuyển đổi của từng token.

## 4. Khai báo bằng annotation model mới trong Spring Shell 3.x

Spring Shell 3.x có annotation model mới sử dụng `@Command` và `@Option`. Với model này, có thể khai báo `arity` bằng enum `OptionArity`, hoặc khai báo riêng `arityMin` và `arityMax`.

Ví dụ option nhận từ một đến ba nhãn:

```java
import java.util.Arrays;
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DeployCommands {

    @Command(command = "deploy")
    public String deploy(
            @Option(
                    longNames = "tag",
                    required = true,
                    arityMin = 1,
                    arityMax = 3)
            String[] tags) {

        return "Các nhãn triển khai: " + Arrays.toString(tags);
    }
}
```

Có thể dùng enum khi khoảng arity khớp với một trường hợp dựng sẵn:

```java
import java.util.Arrays;
import org.springframework.shell.command.CommandRegistration;

@Command(command = "deploy")
public String deploy(
        @Option(
                longNames = "tag",
                required = true,
                arity = CommandRegistration.OptionArity.ONE_OR_MORE)
        String[] tags) {
    return Arrays.toString(tags);
}
```

`ONE_OR_MORE` cho phép một hoặc nhiều giá trị; `ZERO_OR_MORE` cho phép không có giá trị hoặc nhiều giá trị. Nếu cần giới hạn trên, chẳng hạn tối đa ba giá trị, dùng `arityMin` và `arityMax`.

Quy tắc ưu tiên của thuộc tính min/max:

- Nếu `arityMin` có giá trị không âm, nó được dùng thay cho `arity`. Nếu không đặt `arityMax`, giá trị max sẽ bằng min.
- Nếu chỉ đặt `arityMax` với giá trị không âm, min mặc định là `0`.
- Nếu cả min và max đều được đặt, parser dùng đúng khoảng đó.

Ví dụ `arityMin = 2` mà không đặt `arityMax` tương đương nhận đúng hai token. `arityMax = 3` mà không đặt min tương đương khoảng từ không đến ba token. Để dễ đọc và tránh cấu hình mơ hồ, nên chọn một cách: dùng enum hoặc dùng cặp min/max.

## 5. Giới hạn của legacy annotation `@ShellOption`

Spring Shell 3.x vẫn hỗ trợ legacy annotation model với `@ShellComponent`, `@ShellMethod` và `@ShellOption`. Trong model này, `@ShellOption(arity = n)` chỉ cho phép khai báo giới hạn tối đa; không thể đặt riêng số lượng tối thiểu.

Ví dụ nhận tối đa ba nhãn:

```java
import java.util.Arrays;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class LegacyDeployCommands {

    @ShellMethod(key = "deploy")
    public String deploy(
            @ShellOption(value = "--tag", arity = 3) String[] tags) {
        return "Các nhãn triển khai: " + Arrays.toString(tags);
    }
}
```

Ở legacy model, `arity = 3` không diễn đạt được quy tắc “ít nhất một và tối đa ba”. Nếu nghiệp vụ bắt buộc ít nhất một phần tử, cần kiểm tra thêm trong phương thức hoặc service. Khi cần ràng buộc min/max ngay tại parser, ưu tiên programmatic registration hoặc annotation model mới của Spring Shell 3.x.

Không nhầm hai thuộc tính cùng tên `arity` ở hai annotation model: annotation mới nhận `OptionArity` enum và có thêm `arityMin`/`arityMax`; legacy `@ShellOption` nhận một số nguyên.

## 6. Cách người dùng truyền nhiều giá trị

Với option có arity lớn hơn một, người dùng đặt các token liên tiếp sau tên option. Không cần lặp lại tên option cho từng giá trị.

```text
deploy --tag stable candidate production
```

Parser thu thập ba giá trị vào cùng một tham số `tags`. Cách gọi sau không phải cách biểu diễn ba giá trị của một lần xuất hiện option theo arity:

```text
deploy --tag stable --tag candidate --tag production
```

Hãy truyền các giá trị liền nhau sau một lần khai báo `--tag`, theo arity đã định nghĩa.

Nếu một giá trị chứa dấu cách, đặt riêng giá trị đó trong dấu nháy đơn hoặc kép:

```text
deploy --tag stable "release candidate" production
```

Parser coi `release candidate` là một token. Các dấu nháy bao ngoài không trở thành một phần của giá trị sau khi phân tích. Điều này hữu ích khi một option nhận tên môi trường, đường dẫn hoặc nhãn có khoảng trắng.

Nếu command còn có option khác, có thể đặt option đó sau nhóm giá trị:

```text
deploy --tag stable candidate --region ap-southeast-1
```

Hãy kiểm tra cú pháp thực tế của command và help được sinh ra để bảo đảm parser phân định đúng nhóm giá trị và option kế tiếp. Không để một option không giới hạn arity đứng trước các tham số khác nếu parser không có ranh giới rõ ràng để biết nhóm giá trị kết thúc ở đâu.

## 7. Arity khác với required, default value và validation

Arity kiểm tra số token được gắn với option. Những quy tắc khác vẫn có vai trò riêng:

| Cấu hình | Tác dụng | Ví dụ |
| --- | --- | --- |
| `required()` / `required = true` | Bắt buộc option xuất hiện | Phải có `--tag` |
| `arity(1, 3)` / `arityMin`, `arityMax` | Giới hạn số token khi option được truyền | Có từ một đến ba nhãn |
| `defaultValue` | Cung cấp giá trị khi người dùng bỏ qua option theo cấu hình | Mặc định `--format json` |
| Bean Validation / kiểm tra nghiệp vụ | Kiểm tra nội dung của từng giá trị | Mỗi nhãn không rỗng và không chứa ký tự cấm |

Một danh sách có đúng ba phần tử vẫn có thể sai về nghiệp vụ, ví dụ chứa nhãn trùng nhau hoặc tên môi trường không tồn tại. Arity không kiểm tra những điều kiện đó. Sau khi parser bind dữ liệu, hãy dùng validation hoặc service để kiểm tra nội dung từng phần tử.

Không nên dùng default value để che giấu một option nhiều giá trị bắt buộc. Với danh sách quan trọng, khai báo required và arity rõ ràng; nếu có giá trị mặc định hợp lý, giải thích trong help cách giá trị đó được áp dụng.

## 8. Arity của option boolean

Trong Spring Shell 3.x, kiểu `boolean` và `Boolean` thường được xử lý như flag và có arity mặc định bằng `0`: sự hiện diện của option làm giá trị thành `true`. Khi không truyền option, primitive `boolean` mặc định là `false`; kiểu bọc `Boolean` có thể là `null` nếu không khai báo default value.

Ví dụ:

```java
@ShellMethod("Dừng hệ thống")
public String shutdown(boolean force) {
    return "force=" + force;
}
```

Người dùng có thể gọi `shutdown --force` để bật cờ. Nếu muốn boolean nhận một giá trị tường minh như `--force true`, đặt `@ShellOption(arity = 1, defaultValue = "false")` trong legacy model hoặc khai báo arity phù hợp trong model mới. Đây là một trường hợp riêng của boolean; không suy ra rằng mọi option nhiều giá trị đều là flag không cần token.

## 9. Điều gì xảy ra khi arity không khớp?

Spring Shell kiểm tra số lượng token trong lúc parse option. Khi số lượng thấp hơn min, parser phát sinh `NotEnoughArgumentsOptionException`. Khi số lượng vượt max, parser phát sinh `TooManyArgumentsOptionException`.

Với option `--tag` có arity từ một đến hai:

| Lệnh | Kết quả |
| --- | --- |
| `deploy --tag` | Lỗi: cần ít nhất một giá trị |
| `deploy --tag stable` | Hợp lệ, nhận một phần tử |
| `deploy --tag stable candidate` | Hợp lệ, nhận hai phần tử |
| `deploy --tag stable candidate production` | Lỗi: vượt quá hai giá trị |

Các lỗi này xảy ra trước khi logic target xử lý danh sách. Hãy giữ thông báo lỗi ngắn và chỉ rõ option đang thiếu hoặc vượt giới hạn. Nếu cần tùy biến cách trình bày, cấu hình exception handling phù hợp với command registration của ứng dụng.

## 10. Kiểm thử arity

Unit test gọi trực tiếp phương thức Java chỉ kiểm tra logic xử lý mảng hoặc collection. Nó không kiểm tra parser có thu thập đúng số token hay không. Cần có integration test chạy command thông qua Spring Shell test support của phiên bản 3.x.

Với option có arity từ một đến ba, kiểm tra ít nhất các trường hợp:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Không có option | Báo thiếu option nếu required |
| Có option nhưng không có giá trị | Lỗi không đủ số token |
| Một giá trị | Mảng có một phần tử đúng |
| Hai giá trị | Mảng giữ đúng thứ tự hai phần tử |
| Ba giá trị | Mảng giữ đúng thứ tự ba phần tử |
| Bốn giá trị | Lỗi vượt arity tối đa |
| Giá trị có dấu cách | Dấu nháy giữ giá trị thành một token |
| Giá trị sai kiểu | Lỗi chuyển đổi xảy ra trước khi gọi target |
| Nội dung không hợp lệ | Validation/service từ chối dù số lượng đúng |

Nếu dùng programmatic registration, kiểm thử cấu hình `.arity(min, max)` và kiểu `.type(...)`. Nếu dùng annotation model, kiểm thử cặp `arityMin`/`arityMax` hoặc enum `OptionArity`. Nếu còn dùng legacy `@ShellOption`, kiểm thử giới hạn max và kiểm tra riêng điều kiện min trong logic ứng dụng.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ nhận một giá trị dù arity lớn hơn một | Tham số target là kiểu đơn như `String` thay vì array/collection | Dùng `String[]`, `List<String>` hoặc kiểu tập hợp phù hợp |
| Thiếu giá trị nhưng command vẫn chạy | Min chưa được khai báo hoặc đang dùng legacy annotation | Dùng `arityMin` hoặc `.arity(min, max)`; legacy cần validation bổ sung |
| Option bị coi là thiếu dù đã nhập giá trị vị trí | Chưa cấu hình position cho option trong programmatic registration | Khai báo `.position(...)` nếu muốn ánh xạ positional token vào option |
| Giá trị sau option bị gắn nhầm cho option khác | Arity không có giới hạn phù hợp hoặc cú pháp mơ hồ | Đặt max rõ ràng và sắp xếp option dễ phân tích |
| Danh sách có phần tử sai kiểu | Token không chuyển đổi được sang kiểu phần tử | Kiểm tra conversion và thông báo kiểu mong đợi |
| Lặp tên option nhưng danh sách không được ghép | Parser xử lý một lần xuất hiện option theo arity | Đặt nhiều token sau một lần khai báo option |
| Boolean option chờ giá trị | Đã ép arity thành 1 | Chọn rõ flag arity 0 hoặc value arity 1 theo ý định |

## 12. Bài thực hành tổng hợp

Xây dựng command `deploy` nhận danh sách nhãn triển khai và một số tùy chọn:

1. Tạo option `--tag` có kiểu `String[]`, bắt buộc nhận từ một đến ba giá trị.
2. Tạo option `--region` nhận đúng một giá trị.
3. Tạo option `--dry-run` dạng boolean flag.
4. Kiểm tra tên nhãn không rỗng, không trùng và chỉ chứa ký tự hợp lệ.
5. Thử nhập một, hai và ba nhãn; sau đó thử không nhập nhãn và nhập bốn nhãn.
6. Thử một nhãn có dấu cách và xác nhận quoting hoạt động đúng.
7. Viết integration test cho parser và unit test cho validation của danh sách.
8. Viết thêm một phiên bản dùng legacy `@ShellOption` để thấy giới hạn không thể khai báo min arity; bổ sung validation trong phương thức.

Khi hoàn thành, bạn cần giải thích được arity kiểm soát số token như thế nào, vì sao kiểu tham số cần là array hoặc collection, required khác min arity ra sao và khi nào nên chọn annotation model mới thay cho legacy model.

## 13. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Khái niệm | Phân biệt arity, kiểu dữ liệu và required |
| Enum | Chọn đúng `ZERO`, `ZERO_OR_ONE`, `EXACTLY_ONE`, `ZERO_OR_MORE`, `ONE_OR_MORE` |
| Min/max | Khai báo được khoảng số lượng cụ thể |
| Programmatic | Cấu hình `.type(...)`, `.required()` và `.arity(min, max)` |
| Annotation model | Dùng `@Option(arity=...)` hoặc `arityMin`/`arityMax` |
| Legacy model | Hiểu `@ShellOption(arity=...)` chỉ đặt max và biết bổ sung validation |
| Parser | Xử lý đúng nhiều token, quoting và lỗi vượt giới hạn |
| Kiểm thử | Có test cho dưới min, trong khoảng, trên max và dữ liệu sai kiểu |

## Tài liệu tham khảo

- [Spring Shell 3.4 — Arity](https://docs.spring.io/spring-shell/reference/3.4/options/arity.html)
- [Spring Shell 3.4 — `@Option` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html)
- [Spring Shell 3.3 — `CommandRegistration.OptionArity` API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandRegistration.OptionArity.html)
- [Spring Shell 3.4 — Positional Options](https://docs.spring.io/spring-shell/reference/3.4/options/positional.html)
