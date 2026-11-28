# Giá trị bắt buộc, tùy chọn và giá trị mặc định

Khi thiết kế command cho Spring Shell, mỗi tham số cần có quy tắc rõ ràng: người dùng có bắt buộc phải cung cấp hay không, có thể bỏ qua trong trường hợp nào và ứng dụng sẽ dùng giá trị gì nếu tham số không xuất hiện. Spring Shell 4 hỗ trợ các quy tắc này qua `@Argument` và `@Option`. Các ví dụ và cú pháp boolean trong bài theo tài liệu Spring Shell 4.0.4.

`@Argument` mô tả dữ liệu theo vị trí trong dòng lệnh. `@Option` mô tả dữ liệu có tên, thường được viết dưới dạng `--name value` hoặc `-n value`. Hai loại tham số có cách khai báo tính bắt buộc khác nhau, vì vậy cần chọn đúng annotation trước khi thiết lập giá trị mặc định.

## 1. Phân biệt argument và option

Một command có thể nhận cả argument lẫn option:

```text
deploy production --replicas 3 --region ap-southeast-1
```

Trong ví dụ này:

- `production` là positional argument, được xác định bằng vị trí.
- `--replicas 3` là named option có tên `replicas` và giá trị `3`.
- `--region ap-southeast-1` là named option có tên `region`.

Khai báo tương ứng trong Spring Shell 4:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class DeploymentCommands {

    @Command(name = "deploy", description = "Triển khai ứng dụng")
    public String deploy(
            @Argument(index = 0, description = "Môi trường triển khai") String environment,
            @Option(longName = "replicas", required = true, description = "Số bản sao") Integer replicas,
            @Option(longName = "region", defaultValue = "ap-southeast-1", description = "Vùng triển khai") String region) {
        return "Deploy " + environment + " with " + replicas + " replicas in " + region;
    }
}
```

Argument có chỉ số bắt đầu từ `0`. Option được nhận diện bằng tên ngắn hoặc tên dài. Spring Shell cho phép đặt option và argument ở các vị trí khác nhau trong dòng lệnh; parser phân biệt chúng theo cú pháp thay vì chỉ dựa vào thứ tự xuất hiện.

## 2. Argument bắt buộc và argument có giá trị mặc định

Trong API annotation 4.x, `@Argument` có các thuộc tính `index`, `description` và `defaultValue`. Annotation này **không có thuộc tính `required`**.

Nếu không khai báo `defaultValue`, argument theo vị trí phải được cung cấp khi gọi command. Ví dụ:

```java
@Command(name = "user show", description = "Xem thông tin người dùng")
public String showUser(
        @Argument(index = 0, description = "Mã người dùng") String userId) {
    return "User ID: " + userId;
}
```

Lệnh hợp lệ:

```text
user show 42
```

Nếu gọi `user show` mà không có mã người dùng, Spring Shell không có giá trị để bind vào argument bắt buộc và sẽ báo lỗi trước khi gọi method.

### Làm cho argument có thể bỏ qua

Để cho phép người dùng bỏ qua argument, khai báo `defaultValue`:

```java
@Command(name = "greet", description = "Chào người dùng")
public String greet(
        @Argument(index = 0, description = "Tên người dùng", defaultValue = "World") String name) {
    return "Hello " + name;
}
```

Hai cách gọi đều hợp lệ:

```text
greet
greet Alice
```

Khi người dùng gọi `greet`, tham số `name` nhận `World`. Khi gọi `greet Alice`, giá trị được cung cấp trực tiếp sẽ thay thế giá trị mặc định.

Không có `@Argument(required = false)`. Với argument vị trí, `defaultValue` là cách khai báo một giá trị có thể được dùng khi người gọi không cung cấp token tương ứng.

## 3. Option bắt buộc

Trong `@Option`, thuộc tính `required` quyết định người dùng có phải cung cấp option đó hay không. Giá trị mặc định của `required` là `false`.

Nếu một option là điều kiện để command hoạt động, hãy đặt `required = true`:

```java
@Command(name = "backup", description = "Tạo bản sao lưu")
public String backup(
        @Option(longName = "destination", required = true,
                description = "Thư mục lưu bản sao lưu") String destination) {
    return "Backup destination: " + destination;
}
```

Lệnh cần có option `--destination`:

```text
backup --destination ./backups
```

Nếu bỏ option:

```text
backup
```

Spring Shell báo thiếu option bắt buộc và không gọi method `backup`. Đây là kiểm tra sự hiện diện của option ở tầng command binding, trước khi nghiệp vụ chạy.

Có thể dùng tên ngắn và tên dài cho cùng option:

```java
@Option(shortName = 'd', longName = "destination", required = true)
String destination
```

Khi đó người dùng có thể viết `-d ./backups` hoặc `--destination ./backups`.

## 4. Option tùy chọn

Vì `required` mặc định là `false`, option có thể bị bỏ qua nếu không khai báo thuộc tính này:

```java
@Command(name = "report list", description = "Liệt kê báo cáo")
public String listReports(
        @Option(longName = "status", description = "Lọc theo trạng thái") String status) {
    if (status == null) {
        return "Liệt kê tất cả báo cáo";
    }
    return "Liệt kê báo cáo có trạng thái " + status;
}
```

Hai cách gọi:

```text
report list
report list --status READY
```

Khi không truyền option tùy chọn không có default, tham số kiểu tham chiếu như `String` có thể nhận `null`; vì vậy cần xử lý trường hợp vắng mặt trước khi sử dụng. Với tham số số hoặc boolean có thể vắng mặt, nên cân nhắc kiểu wrapper như `Integer` và `Boolean` để biểu diễn rõ trạng thái không có giá trị. Kiểu primitive như `int` và `boolean` không thể chứa `null`.

### Tùy chọn không có giá trị mặc định khác với option có giá trị rỗng

Hai lệnh sau biểu thị hai tình huống khác nhau:

```text
report list
report list --status ""
```

Lệnh thứ nhất bỏ qua option `status`. Lệnh thứ hai có truyền option nhưng giá trị là chuỗi rỗng. Nếu nghiệp vụ cần phân biệt hai tình huống, hãy kiểm tra giá trị sau binding và quy định rõ cách xử lý chuỗi rỗng.

## 5. Giá trị mặc định cho option

Khi option thường có một giá trị được dùng trong phần lớn trường hợp, khai báo `defaultValue` để người dùng không phải nhập lại:

```java
@Command(name = "report export", description = "Xuất báo cáo")
public String exportReport(
        @Option(longName = "format", description = "Định dạng file", defaultValue = "csv") String format,
        @Option(longName = "output", description = "Đường dẫn file", defaultValue = "./report.csv") String output) {
    return "Export report as " + format + " to " + output;
}
```

Có thể gọi command mà không chỉ định option:

```text
report export
```

Spring Shell bind `format` thành `csv` và `output` thành `./report.csv`. Người dùng vẫn có thể ghi đè mặc định:

```text
report export --format json --output ./report.json
```

Giá trị được truyền rõ ràng trên dòng lệnh sẽ được dùng thay cho giá trị mặc định.

Giá trị của `defaultValue` trong annotation có kiểu `String`. Nếu tham số method là `Integer`, `Boolean`, enum hoặc một kiểu khác có converter tương ứng, Spring Shell chuyển đổi chuỗi mặc định sang kiểu tham số khi binding. Vì vậy, giá trị mặc định phải có định dạng phù hợp với kiểu dữ liệu.

Hãy chọn một chính sách rõ ràng cho mỗi option. `required = true` yêu cầu người dùng truyền option; `defaultValue` có ý nghĩa khi người dùng bỏ qua option. Tránh khai báo cả hai cùng lúc vì một thuộc tính yêu cầu sự hiện diện trong khi thuộc tính kia nhằm cung cấp giá trị khi vắng mặt.

## 6. Giá trị mặc định cho argument

`@Argument` cũng hỗ trợ `defaultValue`. Cách dùng giống option: khi người dùng không cung cấp argument ở vị trí đó, Spring Shell sử dụng giá trị mặc định.

```java
@Command(name = "server start", description = "Khởi động máy chủ")
public String startServer(
        @Argument(index = 0, description = "Profile", defaultValue = "local") String profile,
        @Argument(index = 1, description = "Port", defaultValue = "8080") Integer port) {
    return "Starting with profile=" + profile + ", port=" + port;
}
```

Ví dụ:

```text
server start
```

Sử dụng `profile=local` và `port=8080`.

```text
server start production 9090
```

Sử dụng `profile=production` và `port=9090`.

Với argument vị trí, cần giữ đúng thứ tự index. Nếu muốn người dùng chỉ thay đổi một giá trị ở vị trí sau, hãy cân nhắc dùng option có tên để tránh phải truyền lại các argument trước đó.

## 7. Bắt buộc, tùy chọn và mặc định: bảng đối chiếu

| Nhu cầu | Khai báo | Khi người dùng bỏ qua |
|---|---|---|
| Argument bắt buộc | `@Argument(index = 0)` | Thiếu argument, command không được gọi |
| Argument có mặc định | `@Argument(index = 0, defaultValue = "local")` | Nhận `local` |
| Option bắt buộc | `@Option(longName = "project", required = true)` | Thiếu option, command không được gọi |
| Option tùy chọn | `@Option(longName = "verbose")` hoặc `required = false` | Không có giá trị do người dùng truyền; xử lý trường hợp vắng mặt |
| Option có mặc định | `@Option(longName = "format", defaultValue = "json")` | Nhận `json` |

Hãy nhớ rằng `required` chỉ có trên `@Option`. `@Argument` dùng `defaultValue` để cho phép bỏ qua vị trí đó.

## 8. Boolean option có thể hoạt động như một flag

Trong Spring Shell 4.0.4, option kiểu `boolean` hoặc `Boolean` có thể được dùng như một flag không kèm giá trị. Khi người dùng chỉ ghi tên option, Spring Shell đặt giá trị thành `true`:

```text
deploy --dry-run
```

Nếu muốn truyền tường minh, có thể dùng:

```text
deploy --dry-run=false
deploy --dry-run false
```

Khi token tiếp theo sau một boolean option là `true` hoặc `false` (không phân biệt chữ hoa/thường), parser nhận token đó làm giá trị boolean. Nếu token tiếp theo là từ khác, parser giữ nó làm argument thay vì tự coi đó là giá trị boolean. Các option không phải boolean vẫn cần một giá trị khi xuất hiện.

Nếu muốn `dry-run` mặc định tắt và chỉ bật khi người dùng truyền giá trị, có thể viết:

```java
@Option(longName = "dry-run", defaultValue = "false") Boolean dryRun
```

Khi gọi `deploy`, `dryRun` là `false`. Khi gọi `deploy --dry-run`, giá trị là `true`; khi gọi `deploy --dry-run false`, giá trị là `false`.

## 9. Chọn kiểu dữ liệu phù hợp cho tham số tùy chọn

Kiểu Java ảnh hưởng đến cách ứng dụng xử lý trường hợp tham số không xuất hiện:

| Kiểu tham số | Khi phù hợp | Lưu ý |
|---|---|---|
| `String` | Văn bản tùy chọn | Có thể kiểm tra `null` và chuỗi rỗng riêng biệt |
| `Integer`, `Long`, `BigDecimal` | Số có thể vắng mặt | Wrapper cho phép biểu diễn `null` khi không có giá trị |
| `int`, `long`, `double` | Giá trị luôn phải có hoặc đã có default | Primitive không biểu diễn được `null` |
| `Boolean` | Trạng thái true/false có thể vắng mặt | Có thể phân biệt chưa cung cấp với true/false khi không đặt default |
| `boolean` | Giá trị luôn có hoặc có default rõ ràng | Primitive không biểu diễn được `null` |
| Enum | Một tập giá trị đã định nghĩa | Giá trị nhập hoặc default phải chuyển đổi được sang enum |

Ví dụ dùng `Boolean` để biểu diễn ba trạng thái:

```java
@Command(name = "cache inspect", description = "Kiểm tra cache")
public String inspectCache(
        @Option(longName = "enabled", description = "Lọc theo trạng thái cache") Boolean enabled) {
    if (enabled == null) {
        return "Không lọc theo trạng thái";
    }
    return enabled ? "Chỉ cache đang bật" : "Chỉ cache đang tắt";
}
```

Với kiểu wrapper, method có thể phân biệt người dùng không đưa option với trường hợp người dùng truyền `true` hoặc `false`. Nếu đặt `defaultValue`, trạng thái vắng mặt sẽ được thay bằng giá trị mặc định và không còn biểu diễn thành `null`.

## 10. Giá trị mặc định không thay thế validation

`required` kiểm tra sự hiện diện của option. `defaultValue` cung cấp giá trị khi người dùng bỏ qua tham số. Cả hai không tự xác nhận dữ liệu có hợp lệ theo nghiệp vụ hay không.

Ví dụ, `--replicas 0` vẫn có thể hiện diện đầy đủ nhưng không phù hợp nếu hệ thống yêu cầu ít nhất một replica. Có thể kết hợp Bean Validation để kiểm tra miền giá trị:

```java
import jakarta.validation.constraints.Min;

@Command(name = "deploy", description = "Triển khai ứng dụng")
public String deploy(
        @Option(longName = "replicas", required = true)
        @Min(1) Integer replicas) {
    return "Deploying " + replicas + " replicas";
}
```

Khi thiếu `--replicas`, kiểm tra required phát hiện option chưa được cung cấp. Khi truyền `--replicas 0`, option có mặt nhưng vi phạm `@Min(1)`. Hai lỗi này có nguyên nhân khác nhau và nên được trình bày rõ cho người dùng.

Tương tự, nếu default là `-1` trong khi `@Min(1)` yêu cầu giá trị ít nhất bằng `1`, command có thể luôn thất bại khi người dùng bỏ qua option. Hãy bảo đảm giá trị mặc định cũng thỏa mãn mọi ràng buộc validation.

## 11. Thiết kế tham số dễ sử dụng

Khi quyết định tham số nào bắt buộc, tùy chọn hoặc có mặc định, hãy dựa trên ý nghĩa nghiệp vụ:

- **Bắt buộc** khi command không thể thực hiện đúng nếu thiếu dữ liệu, chẳng hạn mã người dùng cần xem hoặc thư mục đích khi xuất dữ liệu.
- **Tùy chọn** khi có thể thực hiện hành động hợp lệ mà không cần tham số, chẳng hạn bộ lọc trạng thái hoặc từ khóa tìm kiếm.
- **Có mặc định** khi ứng dụng có một lựa chọn hợp lý, an toàn và dễ hiểu cho phần lớn lần gọi, chẳng hạn định dạng CSV hoặc số lần thử mặc định.

Không nên đặt default chỉ để tránh lỗi thiếu dữ liệu nếu giá trị đó có thể dẫn đến hành động sai. Ví dụ, không nên tự chọn một tài khoản hoặc một môi trường production khi người gọi chưa chỉ định đối tượng đích. Với thao tác có ảnh hưởng lớn, bắt buộc truyền đối tượng hoặc yêu cầu xác nhận rõ ràng thường dễ hiểu hơn.

Ưu tiên named option khi command có nhiều tham số hoặc các giá trị dễ bị nhầm thứ tự. Dùng positional argument cho một vài giá trị cốt lõi, có vị trí ổn định và dễ đọc.

## 12. Bài tập thực hành

Xây dựng command `report generate` cho hệ thống báo cáo. Command cần nhận:

- Mã báo cáo: bắt buộc.
- Định dạng: tùy chọn, mặc định `csv`.
- Số dòng tối đa: tùy chọn, mặc định `100`.
- Chỉ xem trước: tùy chọn, mặc định `false`.
- Thư mục xuất file: bắt buộc.

Hãy thực hiện:

1. Khai báo mã báo cáo bằng `@Argument(index = 0)` không có default.
2. Khai báo `format` bằng `@Option(defaultValue = "csv")`.
3. Khai báo `limit` bằng `@Option(defaultValue = "100") Integer`.
4. Khai báo `preview` bằng `@Option(defaultValue = "false") Boolean`.
5. Khai báo `output` bằng `@Option(required = true)`.
6. Chạy command với đầy đủ tham số và với các option được bỏ qua để quan sát default.
7. Bỏ mã báo cáo hoặc `output` để quan sát lỗi thiếu tham số bắt buộc.
8. Truyền `--limit 0` và bổ sung `@Min(1)` để phân biệt lỗi validation với lỗi thiếu option.
9. Ghi lại giá trị method nhận được trong từng trường hợp.

**Kết quả cần nộp:** source code command, bảng tham số và quy tắc bắt buộc/tùy chọn/default, các lệnh chạy thử và output tương ứng.

## 13. Checklist trước khi công bố command

- [ ] Đã phân biệt argument vị trí với option có tên.
- [ ] Argument bắt buộc có index và không có default không cần thiết.
- [ ] Argument có thể bỏ qua đã được khai báo `defaultValue`.
- [ ] Option bắt buộc dùng `required = true`.
- [ ] Option tùy chọn có cách xử lý rõ ràng khi không được truyền.
- [ ] Giá trị mặc định phù hợp với kiểu Java và quy tắc nghiệp vụ.
- [ ] Kiểu wrapper được cân nhắc khi cần phân biệt giá trị vắng mặt với `false` hoặc `0`.
- [ ] Đã kiểm tra quy tắc khi option xuất hiện: boolean có thể dùng như flag, các option khác cần giá trị.
- [ ] Đã thử cả trường hợp người dùng bỏ qua và ghi đè giá trị mặc định.
- [ ] Default cũng thỏa mãn các ràng buộc validation.
- [ ] Thông báo lỗi giúp người dùng biết tham số nào còn thiếu hoặc không hợp lệ.

## Tài liệu tham khảo

- [Spring Shell Reference Documentation — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell API — `@Argument`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html)
- [Spring Shell API — `@Option`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
