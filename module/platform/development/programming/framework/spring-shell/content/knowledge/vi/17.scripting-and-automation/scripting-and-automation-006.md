# Xác định chính sách dừng hoặc tiếp tục sau lỗi

Một tệp script Spring Shell có thể chạy nhiều command theo thứ tự. Nhưng khi một command thất bại, quy trình nên dừng ngay, tiếp tục các bước còn lại hay chỉ bỏ qua những bước phụ thuộc vào kết quả lỗi? Câu trả lời phụ thuộc vào nghiệp vụ và hậu quả của từng bước.

Spring Shell cung cấp cơ chế thực thi command, `ExitStatus` và ánh xạ exception. Các thành phần này giúp báo lỗi có cấu trúc, nhưng không thay thế việc thiết kế chính sách cho toàn bộ workflow. Bài này hướng dẫn chọn chính sách, phân biệt lỗi command với mã thoát của tiến trình, triển khai workflow có thể dừng hoặc tiếp tục và kiểm thử hành vi automation.

Bài sử dụng API Spring Shell 4.x và tài liệu phiên bản 4.0.4.

## 1. Xác định ý nghĩa của lỗi trước khi chọn chính sách

Không phải lỗi nào cũng cần xử lý giống nhau. Hãy phân loại lỗi theo khả năng phục hồi và ảnh hưởng tới các bước sau:

| Loại lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Lỗi đầu vào | Thiếu option, UUID sai định dạng, ngày không hợp lệ | Dừng bước hiện tại; yêu cầu sửa input |
| Lỗi cấu hình | Thiếu endpoint, credential sai, file cấu hình không đọc được | Thường dừng workflow vì các bước sau không thể chạy đúng |
| Lỗi phụ thuộc | Không kết nối được database trước khi migrate | Dừng các bước phụ thuộc; có thể tiếp tục bước độc lập |
| Lỗi tạm thời | Timeout, dịch vụ từ xa trả lỗi tạm thời | Có thể retry có giới hạn; sau retry thất bại mới áp dụng chính sách dừng/tiếp tục |
| Lỗi nghiệp vụ | Bản ghi không tồn tại, trạng thái không cho phép thao tác | Dừng hoặc ghi nhận và tiếp tục tùy mục tiêu của batch |
| Lỗi không mong đợi | Null pointer, lỗi lập trình, invariant bị phá vỡ | Thường dừng để tránh tạo thêm tác động khó dự đoán |

Một command thất bại không nhất thiết có nghĩa toàn bộ script phải dừng. Ví dụ, khi nhập danh sách 100 tài khoản, có thể cần bỏ qua 3 tài khoản không hợp lệ và xử lý 97 tài khoản còn lại. Ngược lại, nếu bước tạo backup thất bại thì bước xóa dữ liệu cũ không nên tiếp tục.

## 2. Chọn chính sách cho workflow

Ba chính sách thường gặp:

| Chính sách | Hành vi | Trường hợp sử dụng |
|---|---|---|
| `STOP_ON_ERROR` (fail-fast) | Dừng ở lỗi đầu tiên; không chạy bước sau | Triển khai, migration, thao tác có phụ thuộc chặt hoặc nguy cơ gây hỏng dữ liệu |
| `CONTINUE_ON_ERROR` | Ghi nhận lỗi của bước hiện tại rồi chạy các bước còn lại | Batch độc lập, kiểm tra nhiều đối tượng hoặc thu thập kết quả từ nhiều nguồn |
| `CONTINUE_INDEPENDENT` | Tiếp tục bước không phụ thuộc vào bước lỗi; bỏ qua bước phụ thuộc | Workflow có nhiều nhánh hoặc đồ thị phụ thuộc |

Không chọn `CONTINUE_ON_ERROR` chỉ vì muốn script “chạy cho xong”. Nếu bước sau dùng dữ liệu mà bước trước chưa tạo được, tiếp tục có thể làm tình trạng tệ hơn. Hãy lập bảng phụ thuộc trước khi quyết định.

Ví dụ workflow triển khai:

```text
validate configuration
          |
          v
       backup
          |
          v
      migrate DB
          |
          v
      deploy app
          |
          v
      smoke test
```

Nếu `backup` thất bại, `migrate DB` và `deploy app` không nên chạy. Với một batch gửi thông báo cho nhiều người nhận độc lập, lỗi ở một người nhận có thể được ghi lại rồi tiếp tục người tiếp theo.

## 3. Spring Shell thực thi script theo thứ tự

Built-in command `script --file` đọc các command từ tệp, mỗi dòng một command, rồi thực thi theo thứ tự xuất hiện. Dòng chú thích bắt đầu bằng `//` được bỏ qua. Có thể gọi trong interactive shell:

```text
script --file ./scripts/maintenance.shell
```

Hoặc chạy tệp qua `NonInteractiveShellRunner` bằng đối số `@file` khi khởi động ứng dụng:

```bash
java -jar admin-cli.jar \
  --spring.shell.interactive.enabled=false \
  @./scripts/maintenance.shell
```

Tài liệu Spring Shell 4.0.4 mô tả thứ tự thực thi của các dòng script, nhưng không công bố một option built-in để chọn `stop-on-error` hoặc `continue-on-error`. Vì vậy, không tự giả định rằng một cờ như `--continue-on-error` có sẵn hoặc mọi loại lỗi đều được xử lý giống nhau. Nếu chính sách này quan trọng với production, hãy kiểm thử đúng phiên bản và cách chạy mà ứng dụng sử dụng; nếu cần hành vi chắc chắn, triển khai workflow command hoặc bộ điều phối riêng.

Phân biệt hai cách chạy:

- `script --file` chạy trong shell session hiện tại.
- `@file` chạy file qua `NonInteractiveShellRunner` khi khởi động ứng dụng; cần tắt interactive mode trong Spring Shell 4.

Hai cách không tạo transaction chung cho toàn bộ tệp. Nếu dòng đầu đã cập nhật database hoặc hệ thống từ xa rồi dòng tiếp theo lỗi, Spring Shell không tự hoàn tác tác động trước đó.

## 4. Phân biệt exception, ExitStatus và process exit code

Spring Shell 4 dùng `ExitStatus` để biểu diễn kết quả của một command. Nó có mã và mô tả. Nếu command ném exception, exception được truyền lên shell theo mặc định; `ExitStatusExceptionMapper` có thể ánh xạ exception thành một `ExitStatus` phù hợp.

Ba khái niệm cần phân biệt:

| Kết quả | Phạm vi | Ai sử dụng |
|---|---|---|
| Exception | Một lần thực thi command | Shell hoặc exception mapper |
| `ExitStatus` | Kết quả command trong Spring Shell | Command execution pipeline và thông báo lỗi |
| Mã thoát tiến trình (JVM process exit code) | Toàn bộ lần chạy ứng dụng | Bash, PowerShell, CI/CD, scheduler hoặc chương trình gọi JAR |

`ExitStatusExceptionMapper` chỉ ánh xạ exception thành trạng thái command. Cấu hình mapper không tự cấu hình mã thoát của JVM. Nếu automation bên ngoài cần biết tiến trình thành công hay thất bại, ứng dụng phải kết nối kết quả workflow với cơ chế exit code của Spring Boot và kiểm thử mã trả về thực tế.

Ngoài ra, không nên mặc định rằng chỉ cần command trả một `ExitStatus` khác 0 thì built-in script sẽ tự dừng. Tài liệu `script` mô tả thứ tự thực thi; cần kiểm thử riêng cách phiên bản đang dùng xử lý status khác 0 và exception.

## 5. Ánh xạ exception thành trạng thái command

Với command khai báo bằng annotation, có thể tham chiếu một bean `ExitStatusExceptionMapper` qua thuộc tính `exitStatusExceptionMapper`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class WorkflowErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper workflowFailureMapper() {
        return exception -> {
            if (exception instanceof WorkflowFailedException) {
                return new ExitStatus(20, exception.getMessage());
            }
            return new ExitStatus(30, "Lỗi thực thi workflow");
        };
    }
}
```

Command sử dụng mapper theo tên bean:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReleaseCommands {

    private final ReleaseWorkflow workflow;
    private final WorkflowExitCode workflowExitCode;

    ReleaseCommands(ReleaseWorkflow workflow, WorkflowExitCode workflowExitCode) {
        this.workflow = workflow;
        this.workflowExitCode = workflowExitCode;
    }

    @Command(
        name = "release run",
        description = "Chạy quy trình phát hành",
        exitStatusExceptionMapper = "workflowFailureMapper"
    )
    public String run(
            @Option(longName = "on-error", defaultValue = "STOP_ON_ERROR") FailurePolicy policy) {
        WorkflowReport report = workflow.run(policy);
        if (report.hasFailures()) {
            throw new WorkflowFailedException(report.summary());
        }
        return report.summary();
    }
}
```

Trong ví dụ, command chỉ ném `WorkflowFailedException` sau khi workflow đã tổng hợp kết quả. Mapper chuyển lỗi đó thành status có mã `20`; lỗi thực thi khác được ánh xạ thành `30`. Mã số là quy ước của ứng dụng, hãy định nghĩa bảng mã ổn định và tránh để lộ thông tin bí mật trong mô tả lỗi.

Exception nghiệp vụ có thể là một kiểu riêng:

```java
class WorkflowFailedException extends RuntimeException {

    WorkflowFailedException(String message) {
        super(message);
    }
}
```

## 6. Triển khai `STOP_ON_ERROR` và `CONTINUE_ON_ERROR` trong workflow riêng

Khi cần chính sách xác định, hãy đưa các bước nghiệp vụ vào một service điều phối. Mỗi bước trả về thành công hoặc phát sinh exception; service ghi lại kết quả và quyết định có chạy bước kế tiếp hay không.

Định nghĩa chính sách và kết quả:

```java
import java.util.List;

enum FailurePolicy {
    STOP_ON_ERROR,
    CONTINUE_ON_ERROR
}

record StepResult(String name, boolean successful, String detail) {
}

record WorkflowReport(List<StepResult> steps) {

    boolean hasFailures() {
        return steps.stream().anyMatch(step -> !step.successful());
    }

    String summary() {
        return steps.stream()
                .map(step -> (step.successful() ? "OK " : "FAILED ")
                        + step.name() + " - " + step.detail())
                .collect(java.util.stream.Collectors.joining(System.lineSeparator()));
    }
}
```

Service thực thi các bước theo chính sách:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.stereotype.Service;

@Service
class ReleaseWorkflow {

    private record Step(String name, Runnable action) {
    }

    public WorkflowReport run(FailurePolicy policy) {
        List<Step> steps = List.of(
                new Step("validate", this::validate),
                new Step("backup", this::backup),
                new Step("migrate", this::migrate),
                new Step("deploy", this::deploy),
                new Step("verify", this::verify)
        );

        List<StepResult> results = new ArrayList<>();
        for (Step step : steps) {
            try {
                step.action().run();
                results.add(new StepResult(step.name(), true, "completed"));
            } catch (RuntimeException exception) {
                results.add(new StepResult(
                        step.name(), false, safeMessage(exception)));
                if (policy == FailurePolicy.STOP_ON_ERROR) {
                    break;
                }
            }
        }
        return new WorkflowReport(List.copyOf(results));
    }

    private void validate() { /* kiểm tra cấu hình */ }
    private void backup() { /* tạo backup */ }
    private void migrate() { /* migrate database */ }
    private void deploy() { /* triển khai ứng dụng */ }
    private void verify() { /* kiểm tra sau triển khai */ }

    private static String safeMessage(RuntimeException exception) {
        return exception.getMessage() == null
                ? exception.getClass().getSimpleName()
                : exception.getMessage();
    }
}
```

Đây là ví dụ cấu trúc: các method `validate`, `backup`, `migrate`, `deploy` và `verify` cần được triển khai bằng service thực tế. `Runnable` phù hợp khi các bước phát sinh unchecked exception; nếu service dùng checked exception, hãy khai báo một functional interface riêng có `throws Exception` và bắt loại exception tương ứng.

Với `STOP_ON_ERROR`, vòng lặp dừng ngay sau bước lỗi đầu tiên. Với `CONTINUE_ON_ERROR`, service ghi nhận lỗi rồi chạy các bước còn lại. Cuối cùng, `WorkflowReport` chứa cả kết quả thành công lẫn thất bại để command hiển thị một báo cáo tổng hợp.

Không dùng cách tiếp tục này cho các bước có phụ thuộc bắt buộc. Ví dụ, nếu `backup` thất bại thì `migrate` và `deploy` không nên tiếp tục chỉ vì policy là `CONTINUE_ON_ERROR`. Với workflow có phụ thuộc, hãy thêm trạng thái `SKIPPED` và kiểm tra điều kiện tiên quyết của từng bước.

## 7. Ghi nhận lỗi nhưng không làm mất kết quả của các bước sau

Khi tiếp tục sau lỗi, báo cáo cần thể hiện rõ bước nào đã chạy, bước nào thất bại và bước nào chưa được chạy. Không chỉ in một thông báo chung như “workflow có lỗi”.

Ví dụ kết quả:

```text
OK      validate - completed
FAILED  backup   - destination is not writable
SKIPPED migrate  - prerequisite backup failed
SKIPPED deploy   - prerequisite migrate not completed
SKIPPED verify   - deployment did not run

Workflow completed with 1 failure and 3 skipped steps.
```

Với batch độc lập, kết quả có thể như sau:

```text
OK      account-001 - synchronized
FAILED  account-002 - remote service timeout
OK      account-003 - synchronized
OK      account-004 - synchronized

Processed 4 accounts: 3 succeeded, 1 failed.
```

Ghi nhận ít nhất các trường: định danh bước/đối tượng, thời điểm, trạng thái, thông báo an toàn và mã lỗi. Không ghi password, token hoặc nội dung bí mật vào log.

## 8. Dùng `ExitCodeGenerator` để trả mã thoát tiến trình

Nếu workflow chạy trong ứng dụng Spring Boot và CI cần đọc mã thoát của tiến trình, có thể lưu kết quả tổng hợp trong một bean triển khai `ExitCodeGenerator`:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ExitCodeGenerator;
import org.springframework.stereotype.Component;

@Component
class WorkflowExitCode implements ExitCodeGenerator {

    private final AtomicInteger code = new AtomicInteger(0);

    void record(WorkflowReport report) {
        code.set(report.hasFailures() ? 20 : 0);
    }

    @Override
    public int getExitCode() {
        return code.get();
    }
}
```

Command ghi nhận kết quả trước khi ném lỗi để mapper có thể báo status command:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReleaseCommands {

    private final ReleaseWorkflow workflow;
    private final WorkflowExitCode workflowExitCode;

    ReleaseCommands(ReleaseWorkflow workflow, WorkflowExitCode workflowExitCode) {
        this.workflow = workflow;
        this.workflowExitCode = workflowExitCode;
    }

    @Command(
        name = "release run",
        exitStatusExceptionMapper = "workflowFailureMapper"
    )
    public String run(
            @Option(longName = "on-error", defaultValue = "STOP_ON_ERROR") FailurePolicy policy) {
        WorkflowReport report = workflow.run(policy);
        workflowExitCode.record(report);
        if (report.hasFailures()) {
            throw new WorkflowFailedException(report.summary());
        }
        return report.summary();
    }
}
```

Để trả mã đó về hệ điều hành, điểm vào Spring Boot có thể dùng `SpringApplication.exit` và truyền kết quả cho `System.exit`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
class AdminCliApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(AdminCliApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

Mẫu này dành cho ứng dụng CLI chạy xong rồi kết thúc. Với interactive shell, `SpringApplication.run` chỉ hoàn tất sau khi shell runner kết thúc. Không gọi `System.exit` từ method command; giữ việc kết thúc tiến trình ở điểm vào ứng dụng để command còn có thể kiểm thử và tái sử dụng.

`ExitCodeGenerator` xác định mã thoát của tiến trình khi `SpringApplication.exit` được gọi. Hãy chạy JAR thật trong test tích hợp và xác nhận mã trả về; không suy luận mã tiến trình chỉ từ thông báo `ExitStatus` trên màn hình.

## 9. Dùng orchestrator bên ngoài khi cần điều khiển từng process

Một lựa chọn khác là để Bash, PowerShell hoặc CI gọi từng command bằng một JVM riêng. Cách này cho phép orchestrator đọc process exit code sau mỗi bước và tự quyết định dừng hay tiếp tục.

Ví dụ Bash:

```bash
#!/usr/bin/env bash

JAR="target/admin-cli.jar"
POLICY="continue" # hoặc stop
FAILURES=0

run_step() {
  java -jar "$JAR" --spring.shell.interactive.enabled=false "$@"
  code=$?

  if [ "$code" -ne 0 ]; then
    echo "FAILED (exit $code): $*" >&2
    FAILURES=$((FAILURES + 1))
    if [ "$POLICY" = "stop" ]; then
      exit "$code"
    fi
  fi
}

run_step user sync --tenant staging
run_step report export --format csv --output ./reports/users.csv
run_step cache refresh --region ap-southeast-1

if [ "$FAILURES" -gt 0 ]; then
  echo "$FAILURES step(s) failed" >&2
  exit 1
fi

echo "All steps completed successfully"
exit 0
```

Mỗi `run_step` tạo một JVM mới. Vì vậy, state singleton trong Spring context không được chia sẻ giữa các bước; nếu cần truyền dữ liệu, hãy dùng file, database, artifact hoặc một cơ chế lưu trữ chung. Cách này phù hợp khi các command độc lập và ứng dụng đã trả process exit code đúng.

Trên Windows, có thể viết cùng logic trong PowerShell bằng cách gọi `java.exe` rồi kiểm tra `$LASTEXITCODE` ngay sau mỗi lần gọi. Đừng dùng `$?` thay cho `$LASTEXITCODE` để kiểm tra mã thoát của chương trình native.

## 10. Retry, continue và rollback là ba quyết định khác nhau

Khi một bước lỗi, có thể cân nhắc ba hành động:

- **Retry:** chạy lại cùng bước vì lỗi có khả năng tạm thời. Cần giới hạn số lần, thời gian chờ và loại lỗi được retry.
- **Continue:** chạy bước khác dù bước hiện tại thất bại. Chỉ an toàn khi bước sau độc lập hoặc đã có quy tắc bỏ qua phụ thuộc.
- **Rollback/compensation:** hoàn tác hoặc thực hiện hành động bù cho thay đổi đã thành công trước đó. Script không tự cung cấp rollback chung cho nhiều command.

Trước khi retry hoặc cho phép chạy lại toàn bộ script, hãy xem command có idempotent hay không. Một command tạo người dùng mới có thể tạo bản ghi trùng khi chạy lại; command cập nhật cấu hình theo giá trị đích có thể an toàn hơn. Nếu không thể bảo đảm idempotency, hãy lưu execution ID hoặc trạng thái bước để tránh thực hiện side effect hai lần.

Với workflow nhiều bước, có thể cần một chiến lược bù trừ:

```text
create deployment record  -> success
upload artifact           -> success
activate deployment       -> failure
          |
          v
deactivate partial record / mark deployment FAILED
```

Đây là logic nghiệp vụ do ứng dụng thiết kế. Không coi việc dừng script là rollback; các thay đổi đã ghi ra hệ thống vẫn tồn tại.

## 11. Kiểm thử chính sách lỗi

Hãy kiểm thử cả kết quả từng bước lẫn kết quả tổng thể. Bộ test tối thiểu:

| Ca kiểm thử | STOP_ON_ERROR | CONTINUE_ON_ERROR |
|---|---|---|
| Tất cả bước thành công | Chạy tất cả; exit code 0 | Chạy tất cả; exit code 0 |
| Bước đầu thất bại | Dừng ngay; ghi nhận lỗi | Ghi lỗi; tiếp tục bước sau |
| Bước giữa thất bại | Không chạy các bước sau | Tiếp tục các bước còn lại |
| Nhiều bước thất bại | Ghi nhận lỗi đầu tiên đã gặp | Ghi nhận toàn bộ lỗi |
| Bước sau phụ thuộc bước lỗi | Dừng workflow | Phải đánh dấu bước phụ thuộc `SKIPPED` |
| Lỗi parse/command không tồn tại | Báo lỗi đầu vào; không thực hiện bước nghiệp vụ | Chính sách cho lỗi parse cần được kiểm thử riêng |
| Exception được mapper xử lý | Kiểm tra `ExitStatus` command | Kiểm tra `ExitStatus` và việc workflow có tiếp tục theo thiết kế không |
| Process kết thúc | Kiểm tra mã thoát thực tế | Mã thoát tổng hợp phải khác 0 nếu có bất kỳ bước thất bại nào |

Ngoài unit test cho service điều phối, cần có integration test chạy đúng Spring Shell version và cách khởi động dự kiến:

1. Chạy `script --file` trong interactive shell với command lỗi ở đầu, giữa và cuối file.
2. Chạy cùng kịch bản bằng `@file` và `NonInteractiveShellRunner`.
3. Kiểm tra riêng exception và command trả status khác 0.
4. Kiểm tra `ExitStatusExceptionMapper` được gọi đúng command.
5. Khởi chạy JAR như một process riêng, đọc exit code từ hệ điều hành.
6. Xác nhận side effect của các bước trước vẫn còn hoặc đã được bù trừ theo thiết kế.
7. Xác nhận không có secret trong output và log.

Spring Shell 4.0.2 đã sửa một lỗi khiến exit code của non-interactive runner luôn bằng 0. Dù dùng phiên bản mới, vẫn cần kiểm thử mã thoát với JAR thực tế để phát hiện cấu hình bootstrap hoặc exit-code bridge chưa đúng.

## 12. Quy trình lựa chọn chính sách

Trước khi viết script production, hãy trả lời theo thứ tự:

1. Bước này có side effect không? Nếu có, side effect có thể lặp lại an toàn không?
2. Những bước nào phụ thuộc vào kết quả của bước này?
3. Lỗi nào có thể retry và giới hạn retry là gì?
4. Khi một bước độc lập thất bại, có cần xử lý các đối tượng còn lại không?
5. Làm thế nào tổng hợp kết quả để người vận hành biết tất cả lỗi?
6. CI cần nhận mã thoát nào nếu một hoặc nhiều bước thất bại?
7. Nếu workflow dừng giữa chừng, có cách tiếp tục hoặc bù trừ không?

Với một quy trình phụ thuộc tuần tự như backup → migrate → deploy, chọn fail-fast và có bước kiểm tra trước. Với batch các bản ghi độc lập, chọn continue-on-error, tổng hợp lỗi và trả process exit code khác 0 nếu có bản ghi thất bại. Với workflow có nhánh phụ thuộc, dùng trạng thái `SUCCESS`, `FAILED`, `SKIPPED` thay vì một cờ boolean duy nhất.

## 13. Bài tập thực hành

Xây dựng workflow `release run` gồm các bước `validate`, `backup`, `migrate`, `deploy` và `verify`.

Hãy thực hiện:

1. Khai báo option `--on-error` nhận `STOP_ON_ERROR` hoặc `CONTINUE_ON_ERROR`.
2. Tạo một lỗi có chủ ý ở bước `backup`.
3. Chạy với `STOP_ON_ERROR`; xác nhận `migrate`, `deploy` và `verify` không chạy.
4. Chạy với `CONTINUE_ON_ERROR`; ghi nhận lỗi backup và chạy các bước còn lại nếu chúng độc lập.
5. Thêm dependency để `migrate` và `deploy` bị đánh dấu `SKIPPED` khi backup thất bại.
6. Tạo `WorkflowReport` chứa tên bước, trạng thái và thông báo lỗi.
7. Ánh xạ `WorkflowFailedException` sang `ExitStatus` qua `ExitStatusExceptionMapper`.
8. Kết nối kết quả tổng hợp với Spring Boot `ExitCodeGenerator`.
9. Chạy JAR như process riêng và xác nhận exit code là 0 khi thành công, khác 0 khi có bước thất bại.
10. Viết test cho lỗi đầu tiên, nhiều lỗi, retry, bước bị bỏ qua và side effect đã hoàn tất trước khi workflow dừng.

**Kết quả cần nộp:** mã nguồn workflow, bảng phụ thuộc, hai lần chạy với hai chính sách, báo cáo tổng hợp, kết quả test và mã thoát tiến trình.

## 14. Checklist trước khi phát hành script automation

- [ ] Đã phân loại lỗi đầu vào, cấu hình, phụ thuộc, tạm thời và lỗi không mong đợi.
- [ ] Đã chọn rõ `STOP_ON_ERROR`, `CONTINUE_ON_ERROR` hoặc `CONTINUE_INDEPENDENT`.
- [ ] Đã xác định quan hệ phụ thuộc giữa các bước.
- [ ] Không giả định built-in script có cờ stop/continue nếu phiên bản không công bố.
- [ ] Đã kiểm thử riêng `script --file` và `@file` nếu ứng dụng dùng cả hai.
- [ ] Đã phân biệt exception, `ExitStatus` và process exit code.
- [ ] Exception mapper có thông báo an toàn và mã lỗi ổn định.
- [ ] Workflow tổng hợp tất cả bước thành công, thất bại và bị bỏ qua.
- [ ] Retry có giới hạn và chỉ áp dụng cho lỗi phù hợp.
- [ ] Command có side effect được thiết kế idempotent hoặc có cơ chế chống chạy lặp.
- [ ] Có phương án rollback/compensation nếu nghiệp vụ cần.
- [ ] Mã thoát của JAR đã được kiểm thử từ CI hoặc shell hệ điều hành.
- [ ] Log không chứa password, token hoặc dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring Shell Reference — Script](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Shell Reference — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell API — `CommandExecutor`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutor.html)
- [Spring Shell API — `NonInteractiveShellRunner`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell v4 Migration Guide — Exception Handling](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell Releases — v4.0.2 exit-code fix](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.2)
- [Spring Boot Reference — Application Exit](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.exit)
- [Spring Boot API — `ExitCodeGenerator`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ExitCodeGenerator.html)
