# Boolean được phân tích khác hành vi mong đợi của phiên bản cũ

Sau khi nâng cấp Spring Shell, một Boolean option có thể cho kết quả khác với ứng dụng cũ: flag không bật, giá trị `false` bị bỏ qua, token kế tiếp bị hiểu nhầm là giá trị Boolean hoặc command báo thiếu option. Nguyên nhân thường nằm ở phiên bản parser, cách khai báo tham số và cú pháp người dùng nhập.

Spring Shell 3.3.x và 4.x không dùng cùng mô hình command. Dòng 3.3.x có legacy `@ShellMethod`/`@ShellOption` và cơ chế arity cho option. Dòng 4.x dùng `@Command`, `@Option`, `@Argument`; parser mới có quy tắc riêng để nhận Boolean flag không kèm giá trị. Ngoài khác biệt thiết kế, các bản 4.0.0 và 4.0.1 còn có lỗi parser Boolean đã được sửa trong 4.0.2.

Bài học thuộc chương **Chẩn đoán sự cố**. Nội dung giúp khoanh vùng lỗi theo phiên bản, phân biệt `boolean` với `Boolean`, kiểm tra default và arity, hiểu cách parser 4.0.4 tiêu thụ token `true`/`false`, sau đó tái hiện bằng `ShellTestClient` trước khi sửa command hoặc script.

Sau bài học, bạn có thể:

- Xác định đúng phiên bản Spring Shell đang được resolve trong ứng dụng.
- Phân biệt hành vi Boolean của legacy annotation 3.3.x và parser 4.x.
- Kiểm tra primitive `boolean`, wrapper `Boolean`, `defaultValue` và arity.
- Dự đoán cách parser xử lý bare flag, explicit `true`/`false` và argument theo sau.
- Nhận diện các lỗi Boolean của 4.0.0 và 4.0.1 đã được sửa trong 4.0.2.
- Viết test bao phủ command có subcommand, positional argument và Boolean option.
- Chọn cách sửa ổn định mà không làm thay đổi ý nghĩa của script hiện có.

## Triệu chứng thường gặp

| Triệu chứng | Biểu hiện có thể thấy |
| --- | --- |
| Flag không bật | Gọi `deploy release staging --dry-run` nhưng method nhận `false`. |
| Giá trị `false` không được nhận | `--dry-run false` cho kết quả `true` hoặc báo thừa argument. |
| Token sau flag bị mất | `--dry-run staging` làm command không nhận được argument `staging`. |
| Command báo thiếu giá trị | `--dry-run` bị xem là option cần một giá trị bắt buộc. |
| Chỉ lỗi khi có subcommand | `deploy release --dry-run` khác hành vi của command đơn giản `deploy`. |
| Test và JAR cho kết quả khác nhau | Test dùng một dependency version hoặc command registration khác với artifact triển khai. |
| Chỉ một kiểu khai báo bị lỗi | Legacy annotation, annotation mới hoặc programmatic registration có cách binding khác nhau. |

Đừng sửa ngay bằng cách đổi mọi `boolean` thành `Boolean` hoặc thêm `defaultValue`. Trước hết cần biết parser nào đang chạy và command được đăng ký bằng API nào.

## Xác định phiên bản parser thực tế

Lỗi Boolean có liên quan trực tiếp đến các bản phát hành đầu của Spring Shell 4.x. Cần kiểm tra dependency thực tế thay vì chỉ xem version trong `pom.xml` hoặc `build.gradle`, vì dependency management có thể ghi đè phiên bản.

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.shell
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-shell-core --configuration runtimeClasspath
```

Kiểm tra các điểm sau:

- `spring-shell-core` đang ở phiên bản nào.
- Có nhiều module Spring Shell bị resolve về các phiên bản khác nhau hay không.
- Test runtime và runtime của ứng dụng có dùng cùng version hay không.
- Có `CommandParser` tùy chỉnh được đăng ký trong Spring context hay không.
- Command dùng legacy annotation hay annotation mới.

Nếu dependency thực tế vẫn là 4.0.0 hoặc 4.0.1, không nên kết luận hành vi từ tài liệu của 4.0.4. Các lỗi đã được sửa qua patch release.

## Phân biệt hành vi 3.3.x và 4.x

### Spring Shell 3.3.x

Trong 3.3.x, Boolean thường được dùng làm flag. Với legacy `@ShellOption`, arity mặc định được suy ra theo kiểu tham số: kiểu Boolean có arity `0`, còn kiểu khác thường nhận một token. Tài liệu 3.3.4 minh họa các trường hợp:

| Khai báo legacy | Khi không truyền option | Khi nhập flag | Khi nhập `false` tường minh |
| --- | --- | --- | --- |
| `boolean` không có default | `false` | `true` | Có thể nhận `false` theo cấu hình binding. |
| `boolean` với default `true` | `true` | Phụ thuộc cấu hình arity/default | Kiểm thử cú pháp thực tế của command. |
| `boolean` với default `false` | `false` | Phụ thuộc cấu hình arity/default | Kiểm thử cú pháp thực tế của command. |
| `Boolean` không có default | Có thể biểu diễn `null` khi không có giá trị | `true` | `false` |

Có một chi tiết cần chú ý khi chuyển cách đăng ký command: ví dụ annotation trong tài liệu 3.3.4 hiển thị `Boolean` không truyền là `false`, trong khi ví dụ `CommandRegistration` programmatic hiển thị `null`. Điều này cho thấy không nên suy ra trạng thái vắng mặt chỉ từ kiểu wrapper; hãy kiểm tra đường binding mà ứng dụng thực sự sử dụng và đặt default tường minh nếu cần hành vi xác định.

Ví dụ legacy annotation:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
class LegacyDeployCommands {

    @ShellMethod(key = "deploy release")
    String release(
            @ShellOption(value = "environment") String environment,
            @ShellOption(value = "dry-run") boolean dryRun) {
        return "environment=" + environment + ", dryRun=" + dryRun;
    }
}
```

Cú pháp tương ứng:

```text
deploy release --environment staging
deploy release --environment staging --dry-run
deploy release --environment staging --dry-run false
```

Với legacy annotation, `@ShellOption` có thể khai báo `arity` rõ ràng. Nếu đã đặt `arity` thủ công cho Boolean, hãy kiểm tra lại vì nó có thể thay đổi số token mà option nhận so với heuristic mặc định.

### Spring Shell 4.0.4

Trong 4.0.x, command dùng `@Command`, option dùng `@Option` và positional argument dùng `@Argument`. Parser 4.0.4 quy định:

- `boolean` và `Boolean` có thể xuất hiện dưới dạng flag không có giá trị; `--verbose` đặt giá trị thành `true`.
- Giá trị tường minh được hỗ trợ qua `--verbose=true`, `--verbose=false`, `--verbose true` hoặc `--verbose false`.
- Với cú pháp có dấu cách, token tiếp theo chỉ được tiêu thụ làm giá trị Boolean nếu nó là `true` hoặc `false`, không phân biệt chữ hoa/thường.
- Nếu token tiếp theo không phải `true` hoặc `false`, nó vẫn là positional argument.
- Các option không phải Boolean vẫn cần giá trị.

Ví dụ:

```text
deploy release staging --dry-run
deploy release --dry-run staging
deploy release --dry-run=true staging
deploy release --dry-run false staging
deploy release --dry-run=false staging
```

Với command có argument `environment`, các lệnh trên lần lượt cho kết quả:

| Input | `environment` | `dryRun` |
| --- | --- | --- |
| `deploy release staging` | `staging` | `false` nếu default là `false` |
| `deploy release staging --dry-run` | `staging` | `true` |
| `deploy release --dry-run staging` | `staging` | `true` |
| `deploy release --dry-run=true staging` | `staging` | `true` |
| `deploy release --dry-run false staging` | `staging` | `false` |
| `deploy release --dry-run=false staging` | `staging` | `false` |

Quy tắc quan trọng là token `staging` không bị lấy làm giá trị Boolean vì nó không phải `true` hoặc `false`. Vì thế, nếu `staging` biến mất khỏi argument trong ứng dụng, hãy kiểm tra version parser, custom parser hoặc cách khai báo tham số trước khi thay đổi thứ tự command.

Ví dụ command 4.0.4 với default tường minh:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class DeployCommands {

    @Command(name = "deploy release")
    String release(
            @Argument(index = 0, description = "Môi trường triển khai") String environment,
            @Option(longName = "dry-run", defaultValue = "false") boolean dryRun) {
        return "environment=" + environment + ", dryRun=" + dryRun;
    }
}
```

Default tường minh giúp xác định hành vi khi option vắng mặt. Nếu nghiệp vụ cần phân biệt ba trạng thái không truyền, `true` và `false`, dùng `Boolean` và kiểm thử riêng trạng thái vắng mặt thay vì giả định wrapper luôn có cùng default ở mọi kiểu đăng ký.

## Lỗi Boolean đã được sửa trong các bản 4.0.x

Không phải mọi khác biệt đều là lỗi cấu hình của ứng dụng. Release notes ghi nhận các vấn đề cụ thể:

| Phiên bản | Thay đổi hoặc lỗi | Ảnh hưởng |
| --- | --- | --- |
| 4.0.0 | Primitive options có thể lỗi khi không truyền giá trị tường minh (`#1262`). | Bare Boolean flag không hoạt động ổn định như mong đợi. |
| 4.0.1 | Cải thiện parser để chấp nhận Boolean option không có giá trị (`#1304`). | Hành vi bare flag được cải thiện, nhưng vẫn còn lỗi khi có argument hoặc subcommand. |
| 4.0.2 | Sửa Boolean flag không có giá trị trong subcommand (`#1331`) và Boolean option không có giá trị khi command có argument (`#1309`). | Đây là mốc sửa hai trường hợp migration thường gặp. |
| 4.0.3 | Tiếp tục có các bản sửa khác của parser/completion; không ghi nhận thay đổi mới về bare Boolean trong release notes. | Kiểm tra toàn bộ release notes khi nâng patch. |
| 4.0.4 | Sửa xử lý escaped quotes trong `DefaultCommandParser` (`#1374`). | Có thể ảnh hưởng script chứa quote; không phải bản sửa chính cho Boolean flag. |

Nếu ứng dụng dùng 4.0.0 hoặc 4.0.1 và gặp lỗi ở Boolean flag, nâng lên patch có bản sửa trước khi viết workaround. Với ứng dụng đang dùng 4.0.2 trở lên, hãy tái hiện trên parser mặc định và kiểm tra command declaration, dependency version, default value hoặc custom parser.

## Chẩn đoán theo từng nguyên nhân

### 1. Bare flag trả về false

Kiểm tra theo thứ tự:

1. Xác nhận tham số thực sự có kiểu `boolean` hoặc `Boolean`, không phải `String`/`Object`.
2. Xác nhận option name trùng với cú pháp nhập, ví dụ `longName = "dry-run"` tương ứng `--dry-run`.
3. Xác nhận default không bị đặt thành giá trị khác ngoài ý muốn.
4. Xác nhận version tối thiểu có bản sửa parser Boolean cho trường hợp command có argument/subcommand.
5. Kiểm tra có custom `CommandParser`, converter hoặc wrapper nào thay đổi token trước khi binding hay không.

Với 4.0.4, thử cả `--dry-run` và `--dry-run=true`. Nếu dạng explicit true hoạt động nhưng bare flag không hoạt động, kiểm tra lại version runtime và parser đang được inject.

### 2. Giá trị false bị hiểu thành true

Thử hai cú pháp tương đương:

```text
deploy release staging --dry-run=false
deploy release --dry-run false staging
```

Nếu chỉ cú pháp có dấu `=` hoạt động, kiểm tra tokenization, quoting, custom parser và script runner. Nếu cả hai đều cho `true`, kiểm tra command method có đảo logic hay không, default có bị gán sau binding không và test có đang gọi đúng command bean không.

Không dùng `--no-dry-run`, `--dry-run=0`, `--dry-run=no` hoặc chuỗi tùy ý nếu ứng dụng chưa định nghĩa custom parser/converter cho các dạng đó. Cú pháp mặc định của Spring Shell 4.0.4 mô tả giá trị Boolean là `true` hoặc `false`.

### 3. Argument sau Boolean bị mất

Trong 4.0.4, token kế tiếp chỉ trở thành Boolean value nếu là `true` hoặc `false`. Ví dụ:

```text
deploy release --dry-run staging
```

`staging` phải được giữ làm argument. Nếu bị tiêu thụ, kiểm tra:

- Ứng dụng có đang chạy 4.0.0/4.0.1 không.
- `--dry-run` có thực sự được nhận diện là Boolean option không.
- Tham số có bị khai báo nhầm thành `String` hoặc custom type không.
- `@Argument(index = 0)` có đặt đúng trên tham số môi trường không.
- Parser tùy chỉnh có dùng quy tắc consume token cũ không.

### 4. Chỉ lỗi khi có subcommand

Tái hiện bằng command tối giản có subcommand, một Boolean option và một argument. Spring Shell 4.0.2 có bản sửa riêng cho Boolean flag không có giá trị trong subcommand. Nếu command chạy đúng khi bỏ subcommand nhưng lỗi khi thêm subcommand trên 4.0.0/4.0.1, so sánh với 4.0.2+ trước khi thay đổi annotation.

### 5. Wrapper Boolean có trạng thái vắng mặt khác dự kiến

`Boolean` có thể biểu diễn `null`, trong khi primitive `boolean` chỉ có `true`/`false`. Tuy nhiên, kết quả vắng mặt còn phụ thuộc default và cách đăng ký command. Để hành vi nhị phân ổn định, khai báo rõ:

```java
@Option(longName = "dry-run", defaultValue = "false") boolean dryRun
```

Nếu `null` mang ý nghĩa “người dùng không chỉ định”, dùng `Boolean`, không đặt default tùy tiện và viết test xác nhận giá trị vắng mặt. Tránh thay wrapper bằng primitive khi nghiệp vụ cần phân biệt “không truyền” với “false”.

### 6. Giá trị bị thay đổi sau parser

Nếu parser test cho đúng nhưng command trả kết quả khác, kiểm tra phần còn lại của đường xử lý:

- Converter tùy chỉnh cho `Boolean` hoặc wrapper type.
- Method overload hoặc command alias trỏ đến method khác.
- Default được gán ở service layer hoặc configuration binding.
- Command method đảo logic như `!dryRun` hoặc dùng điều kiện sai.
- Test context và packaged JAR không dùng cùng dependency/profile.

Ghi giá trị nhận được ở command boundary trong môi trường test để xác định lỗi xảy ra trước hay sau binding. Không ghi secret hoặc dữ liệu nhạy cảm khi bật debug logging ở production.

## Kiểm thử tái hiện bằng ShellTestClient

Kiểm thử qua `ShellTestClient` giúp xác nhận parser, command registry và parameter binding cùng hoạt động. Ví dụ dưới đây dành cho Spring Shell 4.0.4.

Thêm `spring-shell-starter-test` vào test dependencies theo hướng dẫn của đúng dòng Spring Shell đang sử dụng. Dependency này cung cấp `@ShellTest`, `ShellTestClient` và các assertion cho shell screen.

Ứng dụng test:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@SpringBootApplication
class BooleanTestApplication {

    @Command(name = "deploy release")
    String release(
            @Argument(index = 0) String environment,
            @Option(longName = "dry-run", defaultValue = "false") boolean dryRun) {
        return "environment=" + environment + ", dryRun=" + dryRun;
    }
}
```

Test:

```java
import static org.springframework.shell.test.ShellAssertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;

@ShellTest
@ContextConfiguration(classes = BooleanTestApplication.class)
class BooleanOptionTests {

    @Autowired
    ShellTestClient client;

    @Test
    void missingFlagUsesFalseDefault() throws Exception {
        ShellScreen screen = client.sendCommand("deploy release staging");
        assertThat(screen).containsText("environment=staging, dryRun=false");
    }

    @Test
    void bareFlagEnablesDryRun() throws Exception {
        ShellScreen screen = client.sendCommand("deploy release staging --dry-run");
        assertThat(screen).containsText("environment=staging, dryRun=true");
    }

    @Test
    void bareFlagBeforeArgumentKeepsArgument() throws Exception {
        ShellScreen screen = client.sendCommand("deploy release --dry-run staging");
        assertThat(screen).containsText("environment=staging, dryRun=true");
    }

    @Test
    void explicitFalseWithEqualsIsFalse() throws Exception {
        ShellScreen screen = client.sendCommand("deploy release --dry-run=false staging");
        assertThat(screen).containsText("environment=staging, dryRun=false");
    }

    @Test
    void explicitFalseWithSpaceIsFalse() throws Exception {
        ShellScreen screen = client.sendCommand("deploy release --dry-run false staging");
        assertThat(screen).containsText("environment=staging, dryRun=false");
    }
}
```

Nếu test này thất bại trên 4.0.0/4.0.1 nhưng chạy đúng trên 4.0.2+, so sánh kết quả với release notes. Nếu vẫn thất bại trên 4.0.4, kiểm tra custom parser, command declaration và version dependency trước khi tạo workaround.

## Kiểm thử với command legacy 3.3.x

Khi ứng dụng còn ở 3.3.x, giữ test cho cả primitive và wrapper nếu code đang dùng hai kiểu:

```java
@ShellComponent
class LegacyBooleanCommands {

    @ShellMethod(key = "legacy flags")
    String flags(
            @ShellOption(value = "enabled") boolean enabled,
            @ShellOption(value = "optional") Boolean optional) {
        return "enabled=" + enabled + ", optional=" + optional;
    }
}
```

Ma trận input cần kiểm tra trên chính binding style của ứng dụng:

```text
legacy flags
legacy flags --enabled
legacy flags --optional
legacy flags --optional false
```

Nếu dùng programmatic `CommandRegistration`, viết test riêng cho đường đăng ký đó; không suy ra kết quả từ test annotation. Tài liệu 3.3.4 có ví dụ cho thấy `Boolean` có thể là `null` khi không có giá trị trong programmatic registration.

## Quy trình khắc phục

1. **Chụp lại input gây lỗi:** lưu nguyên văn command, gồm vị trí Boolean flag, argument và subcommand.
2. **Xác định version runtime:** kiểm tra dependency tree của runtime và test.
3. **Xác định binding model:** legacy annotation, annotation mới hay programmatic registration.
4. **Kiểm tra chữ ký method:** kiểu `boolean`/`Boolean`, `@Option`/`@Argument`, tên option, default và arity.
5. **Tạo command tối giản:** một Boolean option và một argument để tách parser khỏi nghiệp vụ.
6. **Chạy ma trận test:** option vắng mặt, bare flag, explicit true, explicit false, token khác theo sau và subcommand.
7. **Đối chiếu release notes:** nâng qua patch có bản sửa nếu đang ở phiên bản bị ảnh hưởng.
8. **Kiểm tra script cũ:** cập nhật cú pháp hoặc quoting nếu script dựa vào cách parser cũ tiêu thụ token.
9. **Kiểm tra artifact đóng gói:** chạy cùng command trên JAR thực tế để bảo đảm runtime dependency khớp test.
10. **Chỉ thêm custom parser khi có yêu cầu tương thích:** giữ test cho toàn bộ cú pháp tùy chỉnh.

## Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bare flag không hoạt động trên 4.0.0 | Lỗi primitive option không có explicit value (`#1262`). | Nâng patch và kiểm thử lại. |
| Bare flag lỗi cùng argument trên 4.0.1 | Parser cải thiện một phần nhưng còn lỗi `#1309`. | Dùng 4.0.2+ và kiểm tra command tối giản. |
| Bare flag lỗi trong subcommand trên 4.0.1 | Lỗi `#1331` chưa được sửa. | Dùng 4.0.2+ và thêm test cho subcommand. |
| `--flag false` không thành false | Parser cũ, option không phải Boolean hoặc custom parser tiêu thụ token khác. | Xác nhận type/version; thử `--flag=false` và `--flag false`. |
| Argument sau flag bị mất | Parser cũ hoặc token bị xem là giá trị của option không phải Boolean. | Kiểm tra khai báo `@Option` và version; với 4.0.4 token không phải true/false phải còn là argument. |
| Không phân biệt được vắng mặt với false | Dùng primitive khi cần trạng thái ba giá trị hoặc default không rõ. | Dùng `Boolean` và kiểm thử null, hoặc đặt default tường minh. |
| `--flag` bị báo thiếu giá trị | Option không được nhận diện là Boolean. | Kiểm tra kiểu tham số và `longName`/`shortName`. |
| Test pass nhưng JAR lỗi | Runtime dependency khác test runtime hoặc JAR dùng profile khác. | Kiểm tra dependency tree và chạy process smoke test. |
| Chỉ command có custom parser bị lỗi | Parser tùy chỉnh không giữ quy tắc Boolean của phiên bản hiện tại. | Cập nhật parser và test toàn bộ tokenization. |
| `--flag=0` không được hiểu là false | Parser mặc định dùng literal `true`/`false`. | Dùng `--flag=false` hoặc định nghĩa converter/parser có chủ đích. |

## Checklist xác nhận sau khi sửa

- [ ] Đã xác nhận phiên bản Spring Shell thực tế ở runtime.
- [ ] Test và packaged application dùng cùng version.
- [ ] Đã xác định command dùng legacy annotation, annotation mới hay programmatic registration.
- [ ] Đã kiểm tra kiểu `boolean` hoặc `Boolean` và default value.
- [ ] Đã kiểm tra arity của `@ShellOption` nếu vẫn dùng 3.3.x.
- [ ] Không cố cấu hình arity trên `@Option` của 4.x.
- [ ] Bare flag cho kết quả `true` trên 4.0.4.
- [ ] `--flag=true` và `--flag=false` cho kết quả đúng.
- [ ] Dạng `--flag false` được kiểm thử.
- [ ] Token khác `true`/`false` sau bare flag vẫn là positional argument trên 4.0.4.
- [ ] Command có subcommand đã được kiểm thử.
- [ ] Wrapper Boolean có test riêng cho trạng thái không truyền nếu `null` có ý nghĩa.
- [ ] Script cũ và quoting đã được kiểm tra.
- [ ] Nếu dùng custom parser/converter, đã có test riêng cho quy tắc Boolean.
- [ ] JAR hoặc executable đã được chạy smoke test bằng command gây lỗi ban đầu.

## Ghi nhớ

Hành vi Boolean khác nhau giữa Spring Shell 3.3.x và 4.x, nhưng cũng phụ thuộc cách đăng ký command, kiểu tham số và default. Trong 3.3.x, legacy `@ShellOption` mặc định dùng arity `0` cho Boolean; tài liệu cho thấy bare flag và explicit false được hỗ trợ. Trong 4.0.4, `--flag` đặt Boolean thành true; giá trị kế tiếp chỉ được tiêu thụ nếu là `true` hoặc `false`, còn token khác vẫn là argument. Spring Shell 4.0.0 và 4.0.1 có các lỗi Boolean đã được sửa trong 4.0.2. Khi chẩn đoán, xác nhận version runtime, binding model, chữ ký tham số và tái hiện bằng `ShellTestClient` trước khi thay đổi command hoặc script.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Types](https://docs.spring.io/spring-shell/reference/3.3/options/types.html): Boolean primitive/wrapper, default value và ví dụ annotation/programmatic registration.
- [Spring Shell 3.3.4 — Options](https://docs.spring.io/spring-shell/reference/3.3/options/): phân biệt option và positional parameter trong dòng 3.3.x.
- [Spring Shell 3.3.0 API — `ShellOption`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/ShellOption.html): `arity`, `defaultValue`, `NULL`, `NONE` và heuristic arity mặc định cho Boolean.
- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): quy tắc Boolean bare flag, explicit value, token kế tiếp, argument và quoting.
- [Spring Shell 4.0.4 API — `Option`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): kiểu option, `defaultValue`, `required`, `shortName` và `longName`.
- [Spring Shell 4.0.4 — Testing](https://docs.spring.io/spring-shell/reference/testing.html): `@ShellTest`, `ShellTestClient`, `ShellScreen` và assertion command.
- [Spring Shell Releases](https://github.com/spring-projects/spring-shell/releases): các lỗi Boolean trong 4.0.0/4.0.1 và bản sửa trong 4.0.2; các thay đổi parser tiếp theo.
- [Spring Shell 4.0.1 release notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.1): cải thiện bare Boolean option và các lỗi còn tồn tại trong bản này.
- [Spring Shell 4.0.2 release notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.2): sửa Boolean flag không có giá trị trong subcommand và khi có argument.
