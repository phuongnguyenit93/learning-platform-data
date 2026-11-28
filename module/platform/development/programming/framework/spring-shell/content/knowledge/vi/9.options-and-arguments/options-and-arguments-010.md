# Boolean dạng cờ ở mô hình cũ và giá trị tường minh ở parser 4.x

Option Boolean thường biểu diễn một lựa chọn bật/tắt như `--dry-run`, `--verbose` hoặc `--include-archived`. Cách nhập option này thay đổi theo mô hình và phiên bản Spring Shell. Trong legacy annotation model của Spring Shell 3.1.x, kiểu `boolean` và `Boolean` được xử lý đặc biệt như cờ: người dùng có thể chỉ cần đặt tên option để bật giá trị. Parser mới của Spring Shell 4.x hỗ trợ cú pháp option có giá trị; một số bản 4.0.x đầu yêu cầu truyền giá trị Boolean tường minh. Vì vậy, cách viết như `--dry-run=true` hoặc `--dry-run false` là rõ ràng và an toàn khi chuyển phiên bản.

Có một khác biệt theo bản phát hành cần lưu ý: tài liệu cú pháp của các bản 4.0.x đầu tiên mô tả option luôn cần giá trị, kể cả Boolean; tài liệu stable Spring Shell 4.0.4 hiện nay đã hỗ trợ cả Boolean flag không kèm giá trị lẫn giá trị `true`/`false` tường minh. Do đó, khi viết script hoặc duy trì ứng dụng chạy nhiều bản 4.x, nên truyền giá trị rõ ràng và kiểm tra tài liệu đúng phiên bản đang dùng.

## 1. Boolean option là gì?

Một option Boolean nhận một trong hai giá trị logic `true` hoặc `false`. Ví dụ trong ứng dụng quản lý kho:

- `--dry-run`: chạy thử và không lưu thay đổi.
- `--verbose`: hiển thị thêm thông tin chẩn đoán.
- `--include-archived`: bao gồm cả dữ liệu đã lưu trữ.
- `--force`: cho phép thực hiện thao tác cần xác nhận.

Khác với option chuỗi hoặc số thường phải đi kèm giá trị, Boolean thường được thiết kế theo dạng cờ. Khi người dùng có mặt option, command hiểu rằng tính năng được bật; khi không có option, command dùng giá trị mặc định.

Trong Java có hai kiểu thường dùng:

| Kiểu | Giá trị | Ý nghĩa khi không truyền option |
|---|---|---|
| `boolean` | Chỉ `true` hoặc `false` | Phải có một giá trị mặc định cụ thể, thường là `false` |
| `Boolean` | `true`, `false` hoặc `null` | Có thể biểu diễn thêm trạng thái chưa được người dùng chỉ định nếu cấu hình default là `null` |

Không nên chọn `Boolean` chỉ vì tên kiểu giống Boolean hơn. Chọn kiểu theo ý nghĩa nghiệp vụ: nếu chỉ cần bật/tắt, `boolean` là đủ; nếu cần phân biệt “người dùng không chọn” với “người dùng chọn false”, dùng `Boolean` và cấu hình giá trị mặc định phù hợp.

## 2. Legacy annotation model 3.1.x: Boolean hoạt động như cờ

Trong Spring Shell 3.1.3, tham số `boolean` hoặc `Boolean` có arity mặc định bằng 0. Điều đó cho phép parser xử lý sự hiện diện của option như một cờ mà không cần người dùng nhập thêm token.

Ví dụ command xuất báo cáo:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ReportCommands {

    @ShellMethod(value = "Xuất báo cáo tồn kho.", key = "stock report")
    public String export(
            @ShellOption(value = "--dry-run", defaultValue = "false")
            boolean dryRun) {

        if (dryRun) {
            return "Đã mô phỏng xuất báo cáo; không ghi file.";
        }

        return "Đã xuất báo cáo tồn kho.";
    }
}
```

Với `defaultValue = "false"`, có thể gọi command như sau:

```text
shell:>stock report
Đã xuất báo cáo tồn kho.

shell:>stock report --dry-run
Đã mô phỏng xuất báo cáo; không ghi file.

shell:>stock report --dry-run false
Đã xuất báo cáo tồn kho.
```

Trong mô hình này, `--dry-run` đứng riêng được hiểu là bật cờ. Người dùng cũng có thể truyền `true` hoặc `false` tường minh như ví dụ cuối. Khi không truyền option, giá trị mặc định được sử dụng.

### 2.1. Giá trị mặc định

Giá trị mặc định quyết định command làm gì khi người dùng bỏ qua option.

```java
@ShellMethod(value = "Đồng bộ dữ liệu.", key = "data sync")
public String sync(
        @ShellOption(value = "--verify", defaultValue = "true")
        boolean verify) {
    return verify ? "Đồng bộ kèm kiểm tra." : "Đồng bộ không kiểm tra.";
}
```

Khi bỏ qua `--verify`, command nhận `true`. Nếu cần tắt kiểm tra, người dùng truyền `--verify false`. Với option có mặc định `false`, sự hiện diện của cờ sẽ bật nó.

Hãy chọn default theo hành vi an toàn và mong đợi của người vận hành. Ví dụ, `--force` hoặc `--delete` thường nên mặc định `false`; command chỉ thực hiện hành động mạnh khi người dùng chủ động bật.

### 2.2. Phân biệt boolean và Boolean

Kiểu `boolean` không thể nhận `null`. Kiểu `Boolean` có thể nhận `null`, nhưng cần cấu hình để framework dùng `null` khi người dùng bỏ qua option.

```java
@ShellMethod(value = "Gửi thông báo.", key = "notification send")
public String send(
        @ShellOption(value = "--notify", defaultValue = ShellOption.NULL)
        Boolean notify) {

    if (notify == null) {
        return "Chưa chỉ định có gửi thông báo hay không.";
    }
    return notify ? "Đã bật gửi thông báo." : "Đã tắt gửi thông báo.";
}
```

`ShellOption.NULL` là hằng đặc biệt chỉ định giá trị mặc định là `null`; nó khác với việc không khai báo default. Điều này hữu ích khi nghiệp vụ có ba trạng thái: bật, tắt và chưa quyết định.

Trong ví dụ tài liệu Spring Shell 3.1.3, `Boolean` không khai báo default trong legacy annotation sample nhận `false` khi bỏ qua option. Vì vậy, nếu cần trạng thái thứ ba, hãy khai báo `defaultValue = ShellOption.NULL` một cách tường minh và kiểm tra lại trên phiên bản dự án.

## 3. Đăng ký Boolean bằng mô hình lập trình 3.x

Với `CommandRegistration`, có thể khai báo kiểu Boolean và giá trị mặc định trong builder. Khi target nhận `CommandContext`, dùng `hasMappedOption(...)` nếu cần biết option có thực sự được người dùng truyền hay không.

```java
CommandRegistration registration = CommandRegistration.builder()
        .command("stock report")
        .withOption()
            .longNames("dry-run")
            .type(boolean.class)
            .defaultValue("false")
            .and()
        .withTarget()
            .function(context -> {
                boolean dryRun = context.getOptionValue("dry-run");
                return dryRun
                        ? "Đã mô phỏng xuất báo cáo."
                        : "Đã xuất báo cáo.";
            })
            .and()
        .build();
```

Khi dùng wrapper `Boolean` mà không đặt default, target programmatic có thể nhận `null` nếu option không được ánh xạ:

```java
Boolean includeArchived = context.hasMappedOption("include-archived")
        ? context.getOptionValue("include-archived")
        : null;
```

Điểm khác biệt này quan trọng khi chuyển cùng một command giữa annotation và programmatic model. Hãy đọc tài liệu kiểu dữ liệu và kiểm tra giá trị thực tế ở cả trường hợp bỏ qua option, truyền flag và truyền `false`.

## 4. Parser 4.x: truyền giá trị Boolean tường minh

Spring Shell 4 chuyển sang mô hình command và parser mới. Các method command có thể dùng `@Command` và `@Option`; tham số Boolean được bind theo cú pháp option có tên.

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    @Command(name = "stock report", description = "Xuất báo cáo tồn kho.")
    public String export(
            @Option(longName = "dry-run", defaultValue = "false")
            boolean dryRun) {

        return dryRun
                ? "Đã mô phỏng xuất báo cáo; không ghi file."
                : "Đã xuất báo cáo tồn kho.";
    }
}
```

Với parser 4.x, cách viết giá trị tường minh là:

```text
shell:>stock report --dry-run true
shell:>stock report --dry-run false
shell:>stock report --dry-run=true
shell:>stock report --dry-run=false
```

Hai dạng `--key value` và `--key=value` đều được hỗ trợ. Dùng `true` hoặc `false` không phân biệt chữ hoa/thường theo quy tắc Boolean của parser.

### 4.1. Vì sao cần giá trị tường minh?

Parser 4.x phân tích option và argument theo cấu trúc chung: option có tên nhận giá trị, argument là token vị trí. Khi mọi option đều có giá trị rõ ràng, parser dễ phân biệt giá trị Boolean với argument tiếp theo.

Ví dụ:

```text
shell:>report export --include-archived false monthly
```

Parser có thể gắn `false` cho `--include-archived` và giữ `monthly` làm argument. Cách viết rõ ràng này giảm khả năng token kế tiếp bị hiểu nhầm là giá trị Boolean.

### 4.2. Hành vi theo phiên bản 4.0.x

Tài liệu cú pháp của các bản Spring Shell 4.0.x đầu tiên mô tả rằng khi một option được chỉ định, option luôn cần một giá trị, kể cả khi kiểu là Boolean. Theo hợp đồng đó, `--dry-run` đứng riêng sẽ thiếu giá trị; phải dùng `--dry-run true` hoặc `--dry-run=false`.

Tài liệu stable Spring Shell 4.0.4 hiện nay đã mô tả hành vi rộng hơn: `boolean` và `Boolean` có thể được dùng không kèm giá trị, trong đó `--verbose` tương đương `true`; cách truyền tường minh như `--verbose=false` hoặc `--verbose false` vẫn được hỗ trợ. Nếu token tiếp theo không phải `true` hoặc `false`, parser giữ token đó làm argument thay vì tiêu thụ nó như giá trị Boolean.

Vì vậy, khi cần cú pháp hoạt động nhất quán giữa các bản 4.x hoặc trong script được lưu lâu dài, hãy ưu tiên giá trị tường minh:

```text
--dry-run=true
--dry-run=false
```

Nếu muốn dùng dạng cờ ngắn gọn, hãy xác nhận phiên bản Spring Shell cụ thể hỗ trợ nó và ghi rõ quy ước đó trong trợ giúp command.

## 5. Bảng so sánh cách gọi qua các mô hình

| Ý định | Legacy annotation 3.1.x | Parser 4.0.x đầu tiên | Parser stable 4.0.4 |
|---|---|---|---|
| Tắt option | Bỏ qua option khi default là `false` | `--dry-run false` | Bỏ qua option hoặc `--dry-run false` |
| Bật option | `--dry-run` | `--dry-run true` | `--dry-run` hoặc `--dry-run true` |
| Truyền false rõ ràng | `--dry-run false` | `--dry-run false` | `--dry-run false` |
| Dạng bằng dấu `=` | Có thể dùng `--dry-run=false` theo parser option | `--dry-run=false` | `--dry-run=false` |
| Short option | `-d` có thể là flag | `-d true` hoặc `-d=false` | `-d` hoặc `-d true` |

Ví dụ trong bảng giả định option đã được khai báo với kiểu Boolean và có default `false` khi cần. Cú pháp thực tế còn phụ thuộc option name và parser của phiên bản đang chạy.

## 6. Short option và quy tắc nhóm cờ

Trong legacy model, các short option Boolean thường được dùng như cờ:

```java
@ShellMethod(key = "stock report")
public String report(
        @ShellOption(value = "-d", defaultValue = "false") boolean dryRun,
        @ShellOption(value = "-v", defaultValue = "false") boolean verbose) {
    return "dryRun=" + dryRun + ", verbose=" + verbose;
}
```

Trong các parser theo phong cách POSIX, một số CLI cho phép gộp cờ thành `-dv`. Không nên mặc định Spring Shell 4 hỗ trợ quy tắc này: tài liệu cú pháp 4.x nêu rõ short option không được nhóm thành chuỗi như `-abc`.

Với parser 4.x, dùng dạng tường minh:

```text
shell:>stock report -d true -v true
shell:>stock report -d=false -v=false
```

Hoặc dùng tên dài để dễ đọc trong script:

```text
shell:>stock report --dry-run=true --verbose=false
```

## 7. Chuyển đổi một command từ flag 3.x sang cú pháp 4.x

Giả sử command cũ cho phép người vận hành mô phỏng việc nhập dữ liệu mà không ghi thay đổi.

**Mã legacy 3.1.x:**

```java
@ShellComponent
public class ImportCommands {

    @ShellMethod(key = "stock import")
    public String importStock(
            @ShellOption(value = "--dry-run", defaultValue = "false")
            boolean dryRun) {
        return importService.run(dryRun);
    }
}
```

Lệnh cũ:

```text
shell:>stock import --dry-run
```

**Mã annotation 4.x:**

```java
@Component
public class ImportCommands {

    @Command(name = "stock import")
    public String importStock(
            @Option(longName = "dry-run", defaultValue = "false")
            boolean dryRun) {
        return importService.run(dryRun);
    }
}
```

Lệnh tương thích rõ ràng với parser yêu cầu giá trị:

```text
shell:>stock import --dry-run true
```

Việc chuyển đổi không chỉ đổi annotation. Cần rà soát các script, tài liệu trợ giúp, ví dụ trong README và lệnh được gọi từ CI/CD hoặc hệ thống điều phối để cập nhật cú pháp Boolean.

## 8. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Parser báo thiếu giá trị cho `--dry-run` | Dự án đang dùng parser 4.x yêu cầu giá trị Boolean tường minh | Truyền `--dry-run true` hoặc `--dry-run=false` |
| Option luôn là `false` dù có truyền tên option | Tên option không khớp tham số hoặc parser không nhận token như mong đợi | Kiểm tra `@ShellOption(value=...)`/`@Option(longName=...)` và xem lại `help` |
| Không phân biệt được bỏ qua và false | Dùng `boolean` primitive hoặc cấu hình default thành `false` | Dùng `Boolean` và cấu hình default `null` nếu nghiệp vụ cần trạng thái chưa chọn |
| Giá trị Boolean bị gán nhầm cho argument sau | Cú pháp hoặc thứ tự token gây mơ hồ | Dùng dạng `--flag=true` hoặc `--flag false` rõ ràng và đặt named option trước/sau theo hợp đồng command |
| `-abc` không hoạt động | Parser 4.x không hỗ trợ gộp short option | Viết `-a true -b false -c true` hoặc dùng tên option dài |
| `--flag maybe` không được chuyển thành Boolean | `maybe` không phải `true` hoặc `false` | Dùng giá trị hợp lệ hoặc đổi kiểu option nếu cần trạng thái khác |
| Command hoạt động trong REPL nhưng script cũ lỗi sau nâng cấp | Script vẫn dùng flag 3.x | Cập nhật script và kiểm thử non-interactive trên đúng phiên bản 4.x |

## 9. Kiểm thử Boolean option

Với mỗi command có Boolean option, hãy kiểm tra các trường hợp sau:

1. Không truyền option và xác nhận default.
2. Truyền `true` tường minh.
3. Truyền `false` tường minh.
4. Với bản 3.x, kiểm tra dạng cờ không có giá trị.
5. Với bản 4.x, kiểm tra đúng cú pháp được tài liệu của patch version hỗ trợ.
6. Truyền giá trị sai như `yes`, `0` hoặc `maybe` và xác nhận thông báo lỗi dễ hiểu.
7. Kiểm tra short option nếu command cung cấp alias ngắn.
8. Chạy lại các trường hợp trong chế độ non-interactive hoặc script, không chỉ trong REPL.

Ví dụ bảng kiểm thử cho `stock import --dry-run`:

| Đầu vào | Kết quả kỳ vọng khi default là `false` |
|---|---|
| `stock import` | `dryRun=false` |
| `stock import --dry-run true` | `dryRun=true` |
| `stock import --dry-run false` | `dryRun=false` |
| `stock import --dry-run=true` | `dryRun=true` |
| `stock import --dry-run=false` | `dryRun=false` |
| `stock import --dry-run maybe` | Lỗi chuyển đổi/parse |

Đối với bản 3.1.x, bổ sung trường hợp `stock import --dry-run` và xác nhận command nhận `true`. Đối với Spring Shell 4.0.4, dạng cờ trần cũng được tài liệu hỗ trợ; với bản 4.0.x yêu cầu giá trị, dùng các dạng tường minh ở bảng.

## 10. Nguyên tắc thiết kế Boolean option

- Đặt tên option theo hành động hoặc trạng thái rõ ràng: `--dry-run`, `--verbose`, `--include-archived`.
- Dùng `boolean` nếu chỉ cần bật/tắt; dùng `Boolean` nếu cần phân biệt chưa chỉ định.
- Khai báo default tường minh, đặc biệt với thao tác có tác động dữ liệu.
- Dùng giá trị `true`/`false` rõ ràng trong script và tài liệu để tránh phụ thuộc cách parser diễn giải cờ trần.
- Không nhầm Boolean option với positional argument. Option có tên giúp parser và người vận hành hiểu rõ giá trị thuộc tham số nào.
- Khi nâng cấp 3.x lên 4.x, rà soát toàn bộ command invocation bên ngoài ứng dụng, không chỉ mã Java.

## 11. Tổng kết

Legacy annotation model Spring Shell 3.1.x xử lý `boolean` và `Boolean` theo kiểu cờ với arity mặc định bằng 0: bỏ qua option dùng giá trị mặc định, còn sự hiện diện của cờ bật option. Có thể truyền `true` hoặc `false` tường minh; nếu cần trạng thái chưa chỉ định, dùng `Boolean` và cấu hình `ShellOption.NULL`.

Parser Spring Shell 4.x chuyển sang cú pháp option có giá trị rõ ràng. Tài liệu các bản 4.0.x đầu tiên yêu cầu giá trị cho cả Boolean; stable 4.0.4 hiện hỗ trợ cả cờ trần và giá trị tường minh. Để script dễ đọc và tương thích giữa các bản, ưu tiên `--flag=true` hoặc `--flag false`, rồi xác minh hành vi bằng tài liệu và kiểm thử của phiên bản cụ thể.

## Tài liệu tham khảo

- [Spring Shell 3.1.3 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — mục 5.2 Short Format, 5.3 Arity, 5.5 Optional Value, 5.6 Default Value và 5.9.2 Boolean.
- [Spring Shell 3.1.x ShellOption API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellOption.html) — thuộc tính `arity`, `defaultValue`, `NULL` và quy tắc option.
- [Spring Shell 4.0.4 Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) — cú pháp `--key=value`, `--key value` và hành vi Boolean option hiện tại.
- [Spring Shell 4.0.3 Option API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html) — metadata option của annotation model mới.
