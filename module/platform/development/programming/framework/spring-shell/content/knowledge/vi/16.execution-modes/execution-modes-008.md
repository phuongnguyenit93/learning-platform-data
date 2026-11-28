# Cấu hình `spring.shell.interactive.enabled` theo đúng thế hệ

Spring Shell hỗ trợ hai cách chạy CLI: interactive mode mở một phiên REPL để người dùng nhập nhiều command, còn non-interactive mode thực thi command hoặc script rồi kết thúc lượt chạy. Property `spring.shell.interactive.enabled` điều khiển việc chọn runner, nhưng **mặc định của property và cách phối hợp các runner đã thay đổi giữa các thế hệ Spring Shell**.

Vì vậy, không nên sao chép một đoạn `application.yml` từ dự án Spring Shell 3 sang dự án Spring Shell 4 mà không kiểm tra version. Spring Shell 3.3 thay đổi mặc định so với 3.2; Spring Shell 4 tiếp tục thay đổi theo hướng chọn một mode ngay khi khởi động và bật interactive mode mặc định. Bài viết giúp xác định đúng dòng phiên bản, chọn cấu hình cho REPL, chạy command một lần hoặc chạy script, rồi kiểm tra hành vi thực tế.

## 1. Interactive và non-interactive khác nhau thế nào?

**Interactive mode** duy trì một phiên shell hoạt động. Người dùng nhìn thấy prompt, nhập command, xem kết quả rồi tiếp tục nhập command khác. Đây là cách chạy phù hợp khi cần trợ giúp, tự hoàn thành, history và thao tác nhiều bước.

**Non-interactive mode** nhận command từ đối số của tiến trình hoặc từ script, thực thi rồi kết thúc. Cách này phù hợp với shell script, CI/CD, automation và các tác vụ chỉ chạy một lần.

| Tiêu chí | Interactive | Non-interactive |
|---|---|---|
| Vòng đời | Duy trì REPL cho đến khi người dùng thoát | Thực thi command/script rồi hoàn tất |
| Đầu vào | Người dùng nhập tại prompt | Process arguments hoặc file script theo runner/phiên bản |
| Trợ giúp và completion | Có thể dùng trực tiếp trong phiên | Không có trải nghiệm Tab/REPL như terminal tương tác |
| Tình huống phù hợp | Quản trị thủ công, khám phá lệnh, thao tác nhiều bước | CI, cron, automation, chạy lệnh trong pipeline |
| Kết thúc | Người dùng thoát shell hoặc ứng dụng đóng context theo cấu hình | Runner hoàn tất command/script và trả quyền điều khiển cho tiến trình gọi |

Việc một ứng dụng có command được khai báo không quyết định mode. Mode được chọn bởi cấu hình và runner của phiên bản Spring Shell đang dùng.

## 2. Bảng thay đổi theo thế hệ Spring Shell

Các mốc quan trọng cần nhớ:

| Thế hệ | Cơ chế runner và mặc định | Cách cấu hình cần chú ý |
|---|---|---|
| 2.1.x | Bổ sung hỗ trợ phân biệt interactive và non-interactive; lựa chọn mode dựa trên cách shell được khởi chạy và đối số dòng lệnh | Đọc tài liệu đúng bản 2.1.x; không áp dụng máy móc bộ property runner của 3.3+ |
| 3.2.x | `InteractiveShellRunner`, `NonInteractiveShellRunner` và `ScriptShellRunner` đều được bật mặc định | Có thể bật/tắt từng runner bằng `spring.shell.interactive.enabled`, `spring.shell.noninteractive.enabled` và `spring.shell.script.enabled` |
| 3.3.x–3.4.x | Chỉ `NonInteractiveShellRunner` được bật mặc định; REPL cần bật tường minh | Đặt `spring.shell.interactive.enabled=true` để bật interactive runner; script runner vẫn có property riêng |
| 4.x | Chọn mode ngay khi khởi động; interactive mode được bật mặc định | `spring.shell.interactive.enabled=false` chuyển sang `NonInteractiveShellRunner`; không còn mô hình ba property runner của 3.x |

Đây là thay đổi hành vi đáng chú ý nhất khi nâng cấp: cùng một ứng dụng không cấu hình thêm có thể mở REPL ở Spring Shell 4, trong khi ứng dụng Spring Shell 3.3 có thể không mở REPL vì interactive runner mặc định đang tắt.

### Spring Shell 2.1.x

Spring Shell 2.1 giới thiệu hỗ trợ tích hợp để phân biệt hai mode. Tài liệu 2.1 mô tả việc lựa chọn mode dựa trên cách ứng dụng được khởi chạy và các command-line arguments. Đây là giai đoạn API command còn dùng các annotation như `@ShellMethod`, và command có thể khai báo `interactionMode`.

Khi duy trì ứng dụng 2.1.x, hãy dùng tài liệu đúng patch version và kiểm thử cách runner nhận đối số. Không lấy cấu hình ba runner của Spring Shell 3.3 hoặc thuộc tính của Spring Shell 4 để suy ra hành vi mặc định của 2.1.x.

## 3. Spring Shell 3.2.x: cả ba runner được bật mặc định

Trong dòng 3.2.x, Spring Shell có ba runner chính:

- `InteractiveShellRunner`: khởi chạy REPL.
- `NonInteractiveShellRunner`: thực thi command từ đối số tiến trình.
- `ScriptShellRunner`: thực thi các command trong file script.

Theo tài liệu 3.2, cả ba runner đều được bật mặc định. Có thể kiểm soát từng runner bằng các property:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
```

Các giá trị trên minh họa trạng thái mặc định của dòng 3.2.x. Nếu muốn một mode cụ thể, hãy tắt các runner không cần thiết để tránh phụ thuộc vào cách runner chọn xử lý đối số hoặc script.

Ví dụ chỉ giữ REPL:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: false
    script:
      enabled: false
```

Ví dụ chỉ giữ thực thi command một lần:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: false
```

Nếu ứng dụng cần chạy script, bật `script.enabled` theo tài liệu của đúng phiên bản và kiểm tra cú pháp script/đối số mà runner đó hỗ trợ.

## 4. Spring Shell 3.3.x và 3.4.x: interactive không còn bật mặc định

Từ Spring Shell 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định. Điều này có nghĩa ứng dụng mới có thể không mở prompt REPL khi chạy không có cấu hình bổ sung.

Để bật interactive mode, đặt:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Nếu muốn cấu hình tường minh cho một ứng dụng chỉ phục vụ người dùng tương tác:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: false
    script:
      enabled: false
```

Với ứng dụng chạy command từ script hoặc CI, giữ non-interactive runner được bật và không bật interactive runner:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: false
```

Nếu dùng `ScriptShellRunner`, bật riêng:

```yaml
spring:
  shell:
    script:
      enabled: true
```

Từ 3.3.x, `ShellRunner` có API `run(String[] args)` mới để nhận raw application arguments. Các API cũ nhận `ApplicationArguments` bị deprecated. Đây là một thay đổi API của runner bên cạnh thay đổi mặc định.

### Không suy luận rằng các cờ runner là một enum mode

Trong 3.3.x–3.4.x, ba property là các cờ bật/tắt runner. Khi nhiều runner cùng bật, cơ chế chọn runner dựa trên khả năng xử lý đầu vào và thứ tự của chúng. Nếu muốn cấu hình dễ dự đoán, hãy xác định rõ runner cần dùng và tắt các runner không thuộc mục đích triển khai.

## 5. Spring Shell 4.x: interactive bật mặc định

Spring Shell 4 thay đổi mô hình thực thi. Ứng dụng chọn mode ngay từ đầu thay vì giữ mô hình ba runner bật/tắt độc lập như dòng 3.x.

Mặc định:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Có thể bỏ hẳn property này vì `true` là mặc định. Khi chạy ứng dụng, Spring Shell khởi động interactive shell, thường dựa trên JLine.

Để chạy command từ process arguments rồi kết thúc, đặt:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Ví dụ:

```bash
java -jar catalog-cli.jar report-export --format=csv
```

Khi `interactive.enabled=false`, `NonInteractiveShellRunner` nhận command arguments, thực thi command và kết thúc lượt chạy.

### Các property 3.x không còn là cách chọn mode trong 4.x

Không sao chép các property sau từ cấu hình 3.x sang ứng dụng 4.x với kỳ vọng chúng tiếp tục bật/tắt runner như cũ:

```yaml
spring:
  shell:
    noninteractive:
      enabled: true
    script:
      enabled: true
```

Trong Spring Shell 4, điều khiển mode bằng `spring.shell.interactive.enabled`. Non-interactive runner có thể xử lý một command hoặc một file script; file script được chỉ định bằng cách đặt tiền tố `@` trước tên file trong process arguments.

Ví dụ chạy script:

```bash
java -jar catalog-cli.jar @commands.txt
```

File `commands.txt` chứa mỗi command trên một dòng:

```text
help
report-export --format=csv
system-status
```

Đảm bảo `spring.shell.interactive.enabled=false` khi dùng cách chạy này. Nếu để interactive mặc định, ứng dụng sẽ khởi động REPL theo mode đã chọn thay vì dùng runner non-interactive để xử lý script.

## 6. Vì sao không nên dùng cùng một YAML cho mọi major version?

Giả sử một file cấu hình cũ có:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: true
```

Trong Spring Shell 3.x, đây là cấu hình điều khiển các runner riêng. Khi nâng lên Spring Shell 4.x, `interactive.enabled=false` vẫn có ý nghĩa và chọn non-interactive mode, nhưng `noninteractive.enabled` và `script.enabled` không còn là các cờ điều khiển runner độc lập theo mô hình 3.x.

Ngược lại, nếu một ứng dụng 3.3.x chỉ có:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

thì đây là cấu hình quan trọng để bật REPL vì 3.3.x không bật interactive runner mặc định. Khi nâng lên 4.x, giá trị `true` vẫn chạy interactive, nhưng giờ đây nó cũng chính là mặc định nếu property bị bỏ qua.

Hãy quản lý cấu hình theo major version của dependency, thay vì giả định tên property giống nhau đồng nghĩa với cùng một default và cùng mô hình runner.

## 7. Cấu hình theo profile môi trường

Một ứng dụng có thể cần REPL cho phát triển thủ công và non-interactive cho CI. Có thể tách cấu hình bằng Spring profile, nhưng mỗi profile phải phù hợp với thế hệ Spring Shell đang chạy.

Ví dụ cho Spring Shell 4.x:

`application-dev.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

`application-ci.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Chọn profile khi khởi chạy:

```bash
java -jar catalog-cli.jar --spring.profiles.active=dev
```

hoặc:

```bash
java -jar catalog-cli.jar --spring.profiles.active=ci report-export --format=csv
```

Nếu ứng dụng có cấu hình `setAddCommandLineProperties(false)` như bài về phân tách tham số Boot và Spring Shell, không dùng `--spring.profiles.active=...` sau tên JAR để chọn profile. Khi đó hãy đặt profile bằng biến môi trường `SPRING_PROFILES_ACTIVE`, Java System Property trước `-jar`, hoặc cơ chế cấu hình khác được ứng dụng cho phép.

Với Spring Shell 3.3.x, profile interactive cần bật `interactive.enabled=true`; profile non-interactive giữ runner đó tắt và dùng runner tương ứng. Với 3.2.x, hãy xét cả ba runner và đặt rõ các cờ trong từng profile.

## 8. Chọn mode bằng biến môi trường hoặc tham số JVM

Spring Boot externalized configuration cho phép đặt property bằng biến môi trường hoặc Java System Properties. Cách này hữu ích khi cùng một artifact được triển khai ở nhiều môi trường.

Với Spring Shell 4.x, property:

```text
spring.shell.interactive.enabled=false
```

có thể được đặt bằng biến môi trường:

```bash
SPRING_SHELL_INTERACTIVE_ENABLED=false java -jar catalog-cli.jar report-export --format=csv
```

Hoặc bằng Java System Property trước `-jar`:

```bash
java -Dspring.shell.interactive.enabled=false -jar catalog-cli.jar report-export --format=csv
```

PowerShell:

```powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar .\catalog-cli.jar report-export --format=csv
```

Tên biến môi trường theo quy tắc relaxed binding của Spring Boot: dấu chấm chuyển thành dấu gạch dưới, chữ hoa được dùng và dấu gạch nối cũng được chuẩn hóa thành dấu gạch dưới.

Với Spring Shell 3.x, các biến môi trường tương ứng có thể là `SPRING_SHELL_INTERACTIVE_ENABLED`, `SPRING_SHELL_NONINTERACTIVE_ENABLED` và `SPRING_SHELL_SCRIPT_ENABLED`. Chỉ dùng các biến runner tương ứng khi ứng dụng thực sự chạy 3.x.

## 9. Kiểm tra version Spring Shell trước khi đổi cấu hình

Trước khi sửa YAML, xác định dependency thực tế trong runtime classpath. Không dựa vào phiên bản Spring Boot để đoán Spring Shell vì ứng dụng có thể khóa version riêng hoặc dùng BOM.

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.shell:*
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-shell --configuration runtimeClasspath
```

Sau đó xác định dòng:

- `2.1.x`: kiểm tra tài liệu mode detection của 2.1.x.
- `3.2.x`: xét cả ba runner mặc định bật.
- `3.3.x` hoặc `3.4.x`: bật interactive tường minh nếu cần REPL.
- `4.x`: interactive mặc định; đặt `interactive.enabled=false` cho non-interactive.

Nếu dependency tree hiển thị nhiều module Spring Shell khác version, cần giải quyết dependency management trước khi kết luận hành vi runner. Một classpath trộn major version có thể tạo lỗi cấu hình hoặc linkage không dễ chẩn đoán.

## 10. Kiểm thử mode trong môi trường thực tế

Hãy thử cả khởi chạy không có đối số, có command arguments và có script. Cùng một file JAR có thể có hành vi khác nhau chỉ vì profile hoặc property được nạp khác.

| Phiên bản | Cấu hình thử | Lệnh chạy | Kết quả cần xác nhận |
|---|---|---|---|
| 3.2.x | Ba runner bật mặc định | Chạy JAR không đối số | Interactive runner có thể mở REPL theo cơ chế chọn runner |
| 3.2.x | Chỉ interactive bật | Chạy JAR không đối số | Mở REPL |
| 3.3.x–3.4.x | Cấu hình mặc định | Chạy JAR không đối số | Không mặc định mở REPL; non-interactive runner là runner bật mặc định |
| 3.3.x–3.4.x | `interactive.enabled=true` | Chạy JAR không đối số | Mở REPL |
| 3.3.x–3.4.x | Interactive tắt, non-interactive bật | Chạy JAR kèm command | Thực thi command một lần |
| 4.x | `interactive.enabled=true` hoặc bỏ property | Chạy JAR không đối số | Mở REPL |
| 4.x | `interactive.enabled=false` | Chạy JAR kèm command | Thực thi command rồi kết thúc |
| 4.x | `interactive.enabled=false` | Chạy JAR với `@commands.txt` | Thực thi các command trong file rồi kết thúc |

Với 3.x, nếu nhiều runner được bật, hãy kiểm tra cách runner chọn xử lý đối số trên đúng minor version. Đừng chỉ xác nhận property đã bind; hãy xác nhận mode thực sự khởi động.

### Kiểm tra trong automated test

Khi tạo `ApplicationContext` trong test, interactive runner có thể chờ input và làm test treo. Cấu hình test nên chọn non-interactive hoặc loại runner tương tác khỏi context.

Ví dụ profile test cho Spring Shell 4:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Với Spring Shell 3.3.x, cấu hình test cũng cần tránh bật interactive runner; có thể đặt `spring.shell.interactive.enabled=false` và giữ runner non-interactive theo mục đích test. Với 3.2.x, tắt interactive và script runner nếu test chỉ cần khởi tạo context.

Không dùng `@SpringBootTest` tạo context có interactive REPL trong test tự động nếu không có cơ chế cung cấp input và kết thúc shell rõ ràng.

## 11. Các lỗi thường gặp khi nâng cấp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Nâng từ 3.2 lên 3.3 nhưng REPL không mở | Từ 3.3 chỉ non-interactive runner bật mặc định | Đặt `spring.shell.interactive.enabled=true` |
| Nâng từ 3.4 lên 4 và ứng dụng mở REPL ngoài dự kiến | Spring Shell 4 bật interactive mặc định | Đặt `spring.shell.interactive.enabled=false` cho script/CI |
| Copy `noninteractive.enabled` và `script.enabled` sang 4.x | Đây là mô hình runner độc lập của 3.x | Chọn mode bằng `interactive.enabled` trong 4.x |
| Script cũ không được chạy sau khi nâng major | Cơ chế script runner của 3.x khác runner/script input của 4.x | Đọc migration guide và chuyển sang cú pháp script được phiên bản mới hỗ trợ |
| Test treo khi tạo ApplicationContext | Interactive runner chờ terminal input | Tắt interactive trong test profile hoặc thay runner |
| Command có `interactionMode` không còn biên dịch | API `InteractionMode` đã bị loại bỏ trong 4.x | Bỏ khai báo mode trên command; mode do ứng dụng chọn khi khởi động |
| Truyền command arguments nhưng vẫn thấy prompt | Mode cấu hình không phù hợp với version hoặc profile chưa được nạp | Kiểm tra dependency tree, property source và mode runner thực tế |

## 12. Checklist cấu hình theo thế hệ

- [ ] Đã xác định chính xác phiên bản Spring Shell trong runtime classpath.
- [ ] Đã phân loại ứng dụng thuộc 2.1.x, 3.2.x, 3.3–3.4.x hay 4.x.
- [ ] Không suy luận default của `interactive.enabled` từ major khác.
- [ ] Với 3.2.x, đã xét cả interactive, non-interactive và script runner.
- [ ] Với 3.3–3.4.x, đã bật interactive tường minh khi cần REPL.
- [ ] Với 4.x, đã để interactive mặc định cho REPL hoặc đặt `interactive.enabled=false` cho one-shot/script.
- [ ] Không mang `noninteractive.enabled` và `script.enabled` của 3.x sang 4.x như thể chúng vẫn điều khiển runner độc lập.
- [ ] Đã chuyển script theo cú pháp mà runner của major version hỗ trợ.
- [ ] Profile dev, CI và test có cấu hình mode riêng, đúng version.
- [ ] Đã kiểm thử khởi chạy không đối số, có command arguments và script.
- [ ] Đã kiểm tra `ApplicationContext` và tiến trình kết thúc đúng vòng đời.

## Tài liệu tham khảo

1. [Spring Shell 4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html) – runner, interactive/non-interactive mode và `spring.shell.interactive.enabled`.
2. [Spring Shell 4 – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) – thay đổi mặc định interactive và cách chọn mode trong 4.x.
3. [Spring Shell 3.3 – Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html) – ba runner và mặc định chỉ non-interactive runner được bật từ 3.3.x.
4. [Spring Shell 3.3 – Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html) – bật interactive runner để sử dụng REPL.
5. [Spring Shell 3.2 – Reference Documentation](https://docs.spring.io/spring-shell/docs/3.2.0-SNAPSHOT/docs/) – cả ba runner được bật mặc định và các property điều khiển riêng.
6. [Spring Shell 2.1 – Execution](https://docs.spring.io/spring-shell/docs/2.1.15/site/reference/htmlsingle/) – lịch sử phân biệt interactive/non-interactive từ 2.1.x.
7. [Spring Shell 4 – `NonInteractiveShellRunner` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html) – chạy một command hoặc script file qua process arguments.

Hãy bắt đầu bằng việc xác định đúng version Spring Shell rồi mới chọn cấu hình. Property `spring.shell.interactive.enabled` có cùng tên qua nhiều thế hệ, nhưng default và mô hình runner thay đổi: 3.3.x chuyển sang non-interactive mặc định, còn 4.x quay lại interactive mặc định và dùng `false` để chọn non-interactive. Kiểm thử mode thực tế trên đúng artifact là bước cuối để bảo đảm cấu hình phù hợp với môi trường triển khai.
