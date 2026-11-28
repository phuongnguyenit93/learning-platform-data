# Thuộc tính bật từng runner và thay đổi mặc định từ 3.3

Spring Shell 3.x sử dụng các **runner** để quyết định cách ứng dụng tiếp nhận và thực thi command khi khởi động. Ba runner có sẵn là `InteractiveShellRunner`, `NonInteractiveShellRunner` và `ScriptShellRunner`. Mỗi runner phục vụ một kiểu sử dụng khác nhau và có thuộc tính cấu hình riêng.

Thay đổi quan trọng xuất hiện từ Spring Shell 3.3: các phiên bản đến 3.2.x bật cả ba runner theo mặc định, còn từ 3.3.x chỉ bật `NonInteractiveShellRunner`. Vì vậy, một ứng dụng nâng từ 3.2 lên 3.3 có thể không còn mở prompt tương tác sau khi khởi động nếu chưa bật runner tương tác.

Bài học này tập trung vào ba thuộc tính `spring.shell.interactive.enabled`, `spring.shell.noninteractive.enabled` và `spring.shell.script.enabled`, cách phối hợp chúng theo nhu cầu triển khai và thay đổi API `ShellRunner` trong 3.3.

## 1. Runner là gì?

Runner quyết định cách Spring Shell nhận đầu vào và bắt đầu vòng đời xử lý command. Một runner có thể mở vòng lặp nhập lệnh, thực thi một command từ tham số khởi chạy hoặc đọc một file script.

Spring Shell tổ chức việc này qua hai thành phần:

- `ShellApplicationRunner` là điểm tích hợp với Spring Boot. Nó nhận `ApplicationArguments` sau khi ApplicationContext khởi động.
- `ShellRunner` thực hiện một kiểu chạy cụ thể. Spring Shell cung cấp các implementation tương ứng với interactive, non-interactive và script.

Trong cấu hình mặc định, `DefaultShellApplicationRunner` điều phối danh sách `ShellRunner` theo thứ tự ưu tiên. Nó gọi runner phù hợp với đầu vào hiện tại; khi một runner nhận xử lý, các runner tiếp theo không cần chạy nữa.

Thứ tự ưu tiên của ba implementation có sẵn trong Spring Shell 3.3.0 là:

| Thứ tự | Runner | `@Order` | Ý nghĩa |
|---:|---|---:|---|
| 1 | `ScriptShellRunner` | `-100` | Kiểm tra đối số `@file` trước |
| 2 | `NonInteractiveShellRunner` | `-50` | Thử xử lý command được truyền qua đối số |
| 3 | `InteractiveShellRunner` | `0` | Mở REPL nếu các runner trước không nhận xử lý |

Thứ tự này giải thích vì sao có thể bật nhiều runner cùng lúc: script có cơ hội xử lý trước, sau đó đến command một lần, cuối cùng interactive runner có thể mở prompt khi không có đầu vào phù hợp cho hai runner trước.

Có thể hình dung:

```text
Spring Boot khởi động ApplicationContext
                 |
                 v
       ShellApplicationRunner
                 |
                 v
        Danh sách ShellRunner
                 |
                 v
       Chọn runner phù hợp đầu vào
          /        |         \
         v         v          v
    Interactive  Non-interactive  Script
       REPL       Một command    File lệnh
```

Một ứng dụng thường chỉ cần một `ShellApplicationRunner` làm bộ điều phối, nhưng có thể có nhiều bean `ShellRunner` để hỗ trợ các cách chạy khác nhau. Spring Shell cũng cho phép thay thế bộ điều phối nếu ứng dụng có yêu cầu thực thi riêng.

## 2. Ba runner và thuộc tính cấu hình

Mỗi runner có một thuộc tính bật/tắt riêng:

| Runner | Thuộc tính | Mặc định từ 3.3.x | Vai trò |
|---|---|---:|---|
| `InteractiveShellRunner` | `spring.shell.interactive.enabled` | `false` | Mở REPL để người dùng nhập nhiều command liên tiếp |
| `NonInteractiveShellRunner` | `spring.shell.noninteractive.enabled` | `true` | Thực thi command được truyền khi khởi chạy rồi kết thúc |
| `ScriptShellRunner` | `spring.shell.script.enabled` | `false` | Đọc và thực thi các command từ file script rồi kết thúc |

Các giá trị mặc định trong bảng áp dụng cho cấu hình runner của Spring Shell 3.3.x. Nếu dự án có file cấu hình riêng, biến môi trường hoặc tham số dòng lệnh ghi đè property, giá trị thực tế sẽ theo cấu hình được nạp.

### 2.1. InteractiveShellRunner

Runner tương tác khởi động REPL (Read-Eval-Print Loop). Ứng dụng hiển thị prompt, chờ người dùng nhập command, thực thi command rồi quay lại prompt để nhận lệnh tiếp theo.

Ví dụ phiên làm việc:

```text
shell:>help
AVAILABLE COMMANDS
...

shell:>project list
...

shell:>project create --name demo
...

shell:>exit
```

Để bật runner này trong Spring Shell 3.3.x, cấu hình:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Thuộc tính này chỉ bật runner tương tác. Các tính năng terminal như prompt, lịch sử lệnh và completion phụ thuộc vào cấu hình terminal cùng các thành phần mà ứng dụng đưa vào classpath.

### 2.2. NonInteractiveShellRunner

Runner không tương tác nhận command từ các đối số khi khởi chạy ứng dụng, thực thi command và kết thúc tiến trình. Cách này phù hợp với script của hệ điều hành, CI/CD, cron job hoặc các lời gọi tự động.

Ví dụ:

```bash
java -jar project-cli.jar project list
java -jar project-cli.jar project create --name demo
java -jar project-cli.jar project delete --id 42
```

Trong Spring Shell 3.3.x, runner này được bật mặc định:

```yaml
spring:
  shell:
    noninteractive:
      enabled: true
```

Nếu ứng dụng chỉ cần nhận một command rồi thoát, có thể giữ runner này bật và tắt interactive runner. Nếu muốn cùng một artifact hỗ trợ cả prompt lẫn command một lần, hãy bật cả hai runner.

### 2.3. ScriptShellRunner

Runner script tìm các đối số tiến trình bắt đầu bằng ký tự `@`. Phần theo sau `@` được hiểu là đường dẫn tới file chứa các command cần chạy. Runner đọc và thực thi script rồi kết thúc.

Ví dụ file `commands.shell`:

```text
project list
project create --name demo
project show --name demo
```

Gọi ứng dụng:

```bash
java -jar project-cli.jar @commands.shell
```

Bật runner script bằng:

```yaml
spring:
  shell:
    script:
      enabled: true
```

Đừng nhầm `ScriptShellRunner` với command tích hợp `script`. Runner này nhận file script thông qua đối số khởi chạy có tiền tố `@`; command `script` là một lệnh mà người dùng có thể gọi trong shell theo cơ chế riêng của nó.

Script nên chứa các command đã được kiểm tra trước. Nếu script chạy trong CI/CD, hãy xác định rõ cách xử lý khi một command thất bại, output nào được ghi lại và mã thoát nào được hệ thống gọi bên ngoài sử dụng.

## 3. Thay đổi mặc định từ Spring Shell 3.3

Điểm thay đổi cần nhớ:

| Phiên bản | Interactive | Non-interactive | Script |
|---|---:|---:|---:|
| Đến 3.2.x | Bật | Bật | Bật |
| Từ 3.3.x | Tắt | Bật | Tắt |

Trước 3.3, ứng dụng mới thường có thể mở prompt ngay sau khi khởi động vì runner tương tác được bật mặc định. Từ 3.3, ứng dụng mặc định ưu tiên cách gọi command một lần qua tham số khởi chạy.

Ví dụ một dự án cũ có lệnh khởi động:

```bash
java -jar project-cli.jar
```

Sau khi nâng dependency lên 3.3.x, lệnh trên có thể không còn mở REPL. Để khôi phục trải nghiệm prompt, thêm:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Non-interactive vẫn bật theo mặc định, vì vậy cấu hình này cho phép ứng dụng mở prompt khi không có command đầu vào và vẫn giữ khả năng thực thi command qua tham số khởi chạy theo cơ chế runner.

Nếu chỉ muốn một ứng dụng chạy một lần cho automation, hãy giữ `interactive.enabled` ở `false`. Nếu không cần xử lý file script, giữ `script.enabled` ở `false`.

## 4. Chọn cấu hình theo mục đích sử dụng

### 4.1. Chỉ cung cấp prompt tương tác

Nếu ứng dụng chủ yếu được sử dụng trực tiếp bởi con người trong terminal, bật interactive và tắt hai runner còn lại:

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

Khi đó ứng dụng khởi động vào REPL. Người dùng nhập nhiều command và kết thúc bằng command thoát phù hợp.

### 4.2. Chỉ thực thi command một lần

Nếu CLI được gọi từ pipeline hoặc script hệ điều hành, có thể cấu hình:

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

Ví dụ:

```bash
java -jar project-cli.jar project list
```

Ứng dụng thực hiện command và kết thúc. Đây là cách phù hợp khi không muốn tiến trình chờ nhập liệu.

### 4.3. Hỗ trợ cả prompt và command một lần

Một ứng dụng có thể phục vụ cả người dùng trực tiếp và automation. Bật interactive và non-interactive:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: false
```

Khi chạy không có command đầu vào, runner tương tác có thể mở prompt. Khi truyền command lúc khởi chạy, runner không tương tác có thể xử lý command đó rồi thoát.

Đây là cấu hình hữu ích khi phân phối một CLI dùng được cả thủ công lẫn trong pipeline.

### 4.4. Hỗ trợ chạy file script

Nếu muốn hỗ trợ cả command một lần và file script, bật non-interactive và script:

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

Có thể gọi:

```bash
java -jar project-cli.jar project list
java -jar project-cli.jar @commands.shell
```

Nếu ứng dụng cũng cần prompt, có thể bật thêm `interactive.enabled`. Spring Shell sẽ dùng cơ chế điều phối runner để chọn cách xử lý phù hợp với đối số đầu vào.

## 5. Cấu hình bằng application.properties

Ba thuộc tính cũng có thể khai báo bằng dạng key-value:

```properties
spring.shell.interactive.enabled=true
spring.shell.noninteractive.enabled=true
spring.shell.script.enabled=false
```

Ví dụ cấu hình chỉ chạy non-interactive:

```properties
spring.shell.interactive.enabled=false
spring.shell.noninteractive.enabled=true
spring.shell.script.enabled=false
```

Chỉ chọn một định dạng cấu hình chính cho mỗi môi trường để tránh khó xác định giá trị nào đang ghi đè. Khi cần khác biệt giữa local, staging và production, có thể dùng profile Spring Boot hoặc biến môi trường.

## 6. Ghi đè property theo môi trường

Spring Boot cho phép đặt property qua file cấu hình, profile, biến môi trường hoặc tham số dòng lệnh. Điều này hữu ích khi cùng một artifact được chạy theo nhiều cách.

Ví dụ trong `application.yml`:

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

Trong môi trường phát triển, tạo `application-dev.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
```

Khi chạy profile dev:

```bash
java -jar project-cli.jar --spring.profiles.active=dev
```

Trong môi trường automation, giữ cấu hình non-interactive. Tránh bật prompt trong một tiến trình CI không có terminal tương tác, vì tiến trình có thể chờ input hoặc không kết thúc như mong muốn.

Có thể ghi đè một property ngay trên command line của Spring Boot:

```bash
java -jar project-cli.jar --spring.shell.interactive.enabled=true
```

Khi dùng tham số khởi chạy, hãy phân biệt property của Spring Boot với command và option của Spring Shell. Các tham số có thể cùng xuất hiện trong lệnh gọi, nhưng được xử lý ở các tầng khác nhau.

## 7. ShellApplicationRunner và cách runner được lựa chọn

`ShellApplicationRunner` là điểm nối với vòng đời Spring Boot. Implementation mặc định `DefaultShellApplicationRunner` nhận danh sách `ShellRunner` và điều phối đến runner có thể xử lý đối số hiện tại.

Từ Spring Shell 3.3, `ShellRunner` có phương thức:

```java
default boolean run(String[] args) throws Exception
```

Phương thức nhận mảng đối số thô và trả về boolean:

- Trả về `true` khi runner đã thực hiện xử lý; bộ điều phối không cần gọi runner tiếp theo.
- Trả về `false` khi runner không nhận xử lý đầu vào hiện tại; bộ điều phối có thể xét runner khác.

Đây là API được khuyến nghị cho runner tùy chỉnh từ 3.3. Hai phương thức cũ nhận `ApplicationArguments` là `canRun(ApplicationArguments)` và `run(ApplicationArguments)` đã bị deprecated từ 3.3.0 và được đánh dấu để loại bỏ trong phiên bản tương lai.

Khi viết runner riêng, hãy triển khai hành vi `run(String[])` và chỉ trả về `true` sau khi runner thực sự nhận xử lý. Nếu trả về `true` quá sớm, các runner còn lại sẽ không được gọi; nếu luôn trả về `false`, command có thể không được xử lý như dự định.

Thông thường, ứng dụng chỉ cần cấu hình các runner có sẵn. Chỉ tạo `ShellRunner` tùy chỉnh khi có một kiểu đầu vào hoặc quy trình thực thi mà các runner mặc định không đáp ứng.

## 8. Phân biệt runner với InteractionMode của command

Runner quyết định cách toàn bộ shell được khởi chạy. `InteractionMode` trong mô hình annotation legacy điều khiển command nào được phép dùng trong từng chế độ.

Ví dụ:

- `InteractiveShellRunner` mở REPL.
- `NonInteractiveShellRunner` thực thi command từ đối số rồi kết thúc.
- `@ShellMethod(interactionMode = ...)` giới hạn command legacy ở chế độ tương tác, không tương tác hoặc cả hai.

Hai cơ chế này không thay thế nhau. Bật `interactive.enabled` không tự động làm một command bị giới hạn ở non-interactive trở nên khả dụng trong REPL. Tương tự, đặt `InteractionMode.ALL` cho command không tự bật runner tương tác.

Khi dự án sử dụng mô hình annotation mới thay vì `@ShellMethod`, hãy kiểm tra API của phiên bản Spring Shell cụ thể trước khi áp dụng các ví dụ `InteractionMode` từ tài liệu legacy.

## 9. Ảnh hưởng đến kiểm thử và môi trường tự động

Thay đổi mặc định 3.3 có thể ảnh hưởng đến kiểm thử tích hợp. Khi test tạo ApplicationContext, nếu interactive runner được bật, ứng dụng có thể mở REPL và chờ input. Một số bài test sinh tự động từ Spring Initializr có thể bị treo hoặc gặp lỗi khi context được khởi tạo mà không có terminal tương tác.

Với test không cần kiểm tra REPL, có thể tắt interactive runner trong cấu hình test:

```yaml
# application-test.yml
spring:
  shell:
    interactive:
      enabled: false
    script:
      enabled: false
```

Nếu test cần kiểm tra command không tương tác, giữ `noninteractive.enabled` phù hợp và truyền command đầu vào qua test client. Nếu test cần xác minh prompt hoặc hành vi REPL, hãy dùng công cụ kiểm thử shell tương ứng thay vì để runner thật tự chờ terminal trong một test context thông thường.

Trong CI/CD, nên xác định rõ runner nào được bật. Một job chạy `java -jar app.jar command ...` cần non-interactive; một job chạy file lệnh cần script; một phiên terminal dành cho người vận hành cần interactive.

## 10. Các lỗi cấu hình thường gặp

**Nâng lên 3.3 nhưng quên bật interactive.** Ứng dụng không còn mở REPL như trước 3.3. Thêm `spring.shell.interactive.enabled=true` nếu cần prompt.

**Tắt non-interactive nhưng chỉ chạy command qua đối số.** Khi `noninteractive.enabled=false`, runner không nhận command một lần. Hãy bật lại runner hoặc chọn cách chạy phù hợp.

**Bật script nhưng quên ký tự @.** `ScriptShellRunner` tìm đối số có tiền tố `@` để nhận diện file. Chỉ truyền đường dẫn file như một đối số thông thường không kích hoạt cơ chế này.

**Bật cả ba runner mà không kiểm thử đường chạy.** Nhiều runner có thể cùng tồn tại; bộ điều phối chọn runner phù hợp theo đầu vào và thứ tự. Hãy kiểm tra riêng trường hợp không có đối số, có command và có `@script-file`.

**Dùng InteractionMode để bật runner.** `InteractionMode` áp dụng cho command legacy; các property `spring.shell.*.enabled` mới quyết định runner nào được tạo và tham gia điều phối.

**Giữ API ShellRunner cũ khi viết runner tùy chỉnh.** Từ 3.3, dùng `run(String[])`. Các phương thức nhận `ApplicationArguments` đã deprecated và được đánh dấu để loại bỏ.

**Bật interactive trong CI không có terminal.** Runner có thể chờ input và khiến job không kết thúc. Tắt interactive trong profile automation.

## 11. Checklist khi cấu hình runner

- [ ] Xác định ứng dụng cần REPL, command một lần, script hay kết hợp các kiểu chạy.
- [ ] Kiểm tra phiên bản Spring Shell; từ 3.3.x chỉ non-interactive runner bật mặc định.
- [ ] Đặt `spring.shell.interactive.enabled` theo nhu cầu prompt.
- [ ] Đặt `spring.shell.noninteractive.enabled` theo nhu cầu chạy command từ đối số.
- [ ] Đặt `spring.shell.script.enabled` theo nhu cầu chạy file có tiền tố `@`.
- [ ] Kiểm tra thứ tự runner khi nhiều runner cùng được bật.
- [ ] Dùng `run(String[])` nếu tự triển khai `ShellRunner`.
- [ ] Không dùng `InteractionMode` thay cho property bật runner.
- [ ] Tắt interactive trong môi trường CI hoặc test không có terminal.
- [ ] Kiểm tra cả ba cách chạy: không đối số, command trực tiếp và file script.
- [ ] Ghi rõ cấu hình runner theo profile triển khai.

## 12. Tài liệu tham khảo chính thức

- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): ba runner, thuộc tính bật/tắt và thay đổi mặc định từ 3.3.
- [Spring Shell 3.3.4 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): ví dụ bật interactive runner để mở REPL và cách chạy command không tương tác.
- [Spring Shell 3.3.0 API — ShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/ShellRunner.html): phương thức `run(String[])` và các API `ApplicationArguments` đã deprecated.
- [Spring Shell 3.3.0 API — ShellRunnerAutoConfiguration](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/ShellRunnerAutoConfiguration.NonePrimaryCommandConfiguration.html): điều kiện tạo từng runner dựa trên property.
- [Spring Shell 3.3.0 API — InteractiveShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/jline/InteractiveShellRunner.html) và [NonInteractiveShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/jline/NonInteractiveShellRunner.html): vai trò và thứ tự ưu tiên của runner.
- [Spring Shell 3.3.0 API — ScriptShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/jline/ScriptShellRunner.html): cách nhận diện đối số script bắt đầu bằng `@`.

Khi nâng Spring Shell từ 3.2.x lên 3.3.x, hãy kiểm tra lại cấu hình runner trước tiên. Nếu cần REPL, bật interactive; nếu cần chạy command từ đối số, giữ non-interactive; nếu cần thực thi file lệnh, bật script. Việc cấu hình tường minh theo môi trường giúp ứng dụng có hành vi khởi chạy dễ dự đoán trong terminal, script và CI/CD.

