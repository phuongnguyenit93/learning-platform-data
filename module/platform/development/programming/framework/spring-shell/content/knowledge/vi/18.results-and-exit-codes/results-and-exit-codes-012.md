# Không báo thành công khi cập nhật thất bại hoặc mới hoàn thành một phần

Một command cập nhật dữ liệu có thể xử lý nhiều bản ghi hoặc nhiều tài nguyên trong một lần chạy. Nếu một số thao tác thành công nhưng các thao tác còn lại thất bại, thông báo `Cập nhật thành công` sẽ khiến người dùng, script hoặc pipeline hiểu sai trạng thái thực tế. Điều tương tự xảy ra khi command bắt exception, chỉ in cảnh báo rồi kết thúc với mã thành công.

Command cần báo kết quả phản ánh đúng điều đã xảy ra: hoàn tất toàn bộ, thất bại toàn bộ, hoàn thành một phần hoặc chưa xác định được kết quả. Với Spring Shell, nội dung hiển thị và exit status là hai phần của hợp đồng command. Hãy thiết kế cả hai cùng dựa trên kết quả nghiệp vụ đã xác nhận.

## Vì sao không được trả thành công quá sớm?

Giả sử command cập nhật năm cấu hình:

```text
config-update --file batch.yml
```

Kết quả thực tế:

| Bản ghi | Kết quả |
|---|---|
| config-a | Cập nhật thành công |
| config-b | Cập nhật thành công |
| config-c | Thất bại vì dữ liệu không hợp lệ |
| config-d | Cập nhật thành công |
| config-e | Thất bại do dịch vụ đích timeout |

Nếu command chỉ đếm số lần gọi không ném lỗi rồi luôn trả `OK`, hệ thống gọi command sẽ nghĩ cả năm bản ghi đã được cập nhật. Pipeline có thể triển khai bước tiếp theo, xóa file đầu vào hoặc đánh dấu release hoàn tất dù hai cấu hình vẫn sai hoặc chưa rõ trạng thái.

Không dùng một câu thông báo chung như `Hoàn tất cập nhật` khi kết quả có lỗi. Cần phân biệt rõ:

- **Thành công hoàn toàn:** mọi mục tiêu cần cập nhật đã được xác nhận ở trạng thái mong muốn.
- **Thất bại hoàn toàn:** không có thay đổi nào được commit, hoặc thao tác thất bại trước khi bắt đầu.
- **Hoàn thành một phần:** một số mục tiêu đã commit, một số mục tiêu thất bại.
- **Kết quả chưa xác định:** request đã gửi nhưng mất phản hồi, nên chưa thể kết luận hệ thống đích đã cập nhật hay chưa.

Kết quả chưa xác định rất quan trọng với thao tác từ xa. Timeout không chứng minh request thất bại; server có thể đã hoàn tất nhưng phản hồi bị mất. Hãy truy vấn lại trạng thái hoặc dùng idempotency key trước khi báo thất bại chắc chắn hay thử lại thao tác có side effect.

## Xác định hợp đồng cập nhật trước khi viết command

Trước khi quyết định exit code, hãy xác định nghiệp vụ muốn xử lý lỗi theo cách nào:

| Chính sách | Hành vi | Kết quả phù hợp |
|---|---|---|
| All-or-nothing | Tất cả thay đổi thuộc một transaction; một lỗi làm rollback toàn bộ | Thành công hoặc thất bại |
| Continue-on-error | Tiếp tục xử lý các mục còn lại sau khi một mục thất bại | Có thể thành công một phần; phải báo số lượng và mã khác 0 |
| Stop-on-first-error | Dừng ở lỗi đầu tiên; các mục trước đó có thể đã commit | Báo thất bại hoặc một phần tùy trạng thái đã xác nhận |
| External operation | Gọi API, dịch vụ hoặc thiết bị không tham gia transaction cục bộ | Có thể cần compensation/reconciliation; không tự nhận là rollback |

Không nên chọn chính sách chỉ dựa vào cách viết vòng lặp. Hãy xem yêu cầu nghiệp vụ có chấp nhận trạng thái một phần hay không, dữ liệu có thể rollback trong cùng transaction không và hệ thống đích có hỗ trợ thao tác bù hay truy vấn trạng thái không.

## Mô hình kết quả cho một batch update

Một service batch nên trả về kết quả có cấu trúc thay vì chỉ trả `boolean` hoặc một chuỗi thông báo. Kết quả tối thiểu nên cho biết số mục đã thử, số mục thành công, số mục thất bại và danh sách lỗi có thể xử lý tiếp.

```java
import java.util.List;

public record ItemFailure(String itemId, String reason) {
}

public record UpdateReport(
        int attempted,
        int succeeded,
        int failed,
        List<ItemFailure> failures) {

    public boolean isComplete() {
        return failed == 0 && succeeded == attempted;
    }

    public String summary() {
        return "Đã xử lý " + attempted + " mục: "
                + succeeded + " thành công, "
                + failed + " thất bại.";
    }
}
```

`UpdateReport` là kết quả nghiệp vụ. Nó không tự quyết định exit code; command adapter sẽ ánh xạ kết quả sang status phù hợp. Nhờ tách riêng, service có thể được dùng trong API, batch job hoặc command mà không phụ thuộc Spring Shell.

Không đặt `succeeded = attempted` chỉ vì vòng lặp đã kết thúc. Chỉ tăng bộ đếm thành công sau khi service xác nhận thay đổi đã commit hoặc hệ thống đích đã trả kết quả thành công theo hợp đồng.

## All-or-nothing: dùng transaction và chỉ báo thành công sau commit

Nếu yêu cầu là mọi bản ghi phải cùng thành công, hãy đặt transaction ở service nghiệp vụ. Khi một bước thất bại, để exception thoát khỏi phương thức transactional để transaction manager có thể rollback.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CatalogUpdateService {

    private final CatalogRepository repository;

    CatalogUpdateService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int updateAll(List<CatalogChange> changes) {
        int updated = 0;
        for (CatalogChange change : changes) {
            repository.apply(change);
            updated++;
        }
        return updated;
    }
}
```

Nếu `repository.apply(...)` ném `RuntimeException`, Spring transaction mặc định đánh dấu transaction rollback. Command chỉ nên in thông báo thành công sau khi lời gọi service trả về; khi đó proxy transaction đã thực hiện commit thành công.

```java
@Command(name = "catalog-update")
public String update() {
    int updated = catalogUpdateService.updateAll(loadChanges());
    return "Đã cập nhật " + updated + " mục.";
}
```

Nếu service ném exception, dòng trả về thành công không được chạy. Exception đi lên lớp xử lý command để được hiển thị và ánh xạ thành status thất bại.

### Chú ý checked exception và rollback rules

Theo mặc định của Spring Framework, `@Transactional` rollback khi có `RuntimeException` hoặc `Error`; checked exception không tự động làm rollback. Nếu nghiệp vụ ném checked exception và vẫn yêu cầu rollback, khai báo rõ `rollbackFor`:

```java
@Transactional(rollbackFor = Exception.class)
public int updateAll(List<CatalogChange> changes) throws Exception {
    int updated = 0;
    for (CatalogChange change : changes) {
        repository.apply(change);
        updated++;
    }
    return updated;
}
```

Đừng bắt exception bên trong phương thức transactional rồi trả về một kết quả thành công hoặc `UpdateReport` mà không đánh dấu rollback. Khi exception đã bị bắt và không thoát khỏi transaction boundary, transaction manager có thể commit những thay đổi đã thực hiện trước đó.

Nếu muốn bắt lỗi để ghi log hoặc bổ sung ngữ cảnh, hãy ném lại exception hoặc dùng rollback rule phù hợp. Chỉ dùng `setRollbackOnly()` khi cần chủ động đánh dấu rollback trong một luồng đã bắt exception và hiểu rõ tác động của transaction hiện tại.

Transaction cơ sở dữ liệu chỉ bao phủ tài nguyên tham gia cùng transaction manager. Nó không tự rollback email đã gửi, API từ xa, file đã ghi hoặc một dịch vụ khác không tham gia giao dịch phân tán.

## Continue-on-error: báo rõ kết quả một phần

Nếu yêu cầu cho phép xử lý tiếp sau khi một mục thất bại, service cần ghi nhận từng kết quả. Mỗi mục nên được xử lý trong transaction riêng để một lỗi không làm rollback các mục đã thành công trước đó.

Một cách triển khai là dùng một bean riêng cho thao tác từng mục với `REQUIRES_NEW`. Việc đặt phương thức transactional ở bean khác giúp lời gọi đi qua Spring proxy; gọi một phương thức `@Transactional` khác trên cùng đối tượng (`self-invocation`) thường không kích hoạt proxy transaction.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
class CatalogItemUpdater {

    private final CatalogRepository repository;

    CatalogItemUpdater(CatalogRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateOne(CatalogChange change) {
        repository.apply(change);
    }
}
```

Batch service bắt lỗi theo từng mục và tổng hợp kết quả:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.stereotype.Service;

@Service
class CatalogBatchService {

    private final CatalogItemUpdater itemUpdater;

    CatalogBatchService(CatalogItemUpdater itemUpdater) {
        this.itemUpdater = itemUpdater;
    }

    public UpdateReport updateIndividually(List<CatalogChange> changes) {
        int succeeded = 0;
        List<ItemFailure> failures = new ArrayList<>();

        for (CatalogChange change : changes) {
            try {
                itemUpdater.updateOne(change);
                succeeded++;
            } catch (RuntimeException ex) {
                failures.add(new ItemFailure(change.id(), ex.getMessage()));
            }
        }

        return new UpdateReport(
                changes.size(), succeeded, failures.size(), List.copyOf(failures));
    }
}
```

Mỗi lần gọi `updateOne()` có transaction riêng. Nếu một mục lỗi, transaction của mục đó rollback; các mục đã commit trước đó vẫn được giữ. Đây là partial update có chủ đích, không phải một giao dịch all-or-nothing.

Nếu không muốn xử lý tiếp sau lỗi đầu tiên, dừng vòng lặp khi gặp lỗi và vẫn phải báo số mục đã commit trước đó. Không gọi kết quả đó là rollback toàn bộ.

### Command phải trả status khác 0 khi có mục thất bại

Trong Spring Shell 4.x, command programmatic có thể kế thừa `AbstractCommand` và trả về `ExitStatus` từ `doExecute()`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Bean
Command catalogUpdateCommand(CatalogBatchService batchService) {
    return new AbstractCommand("catalog-update", "Cập nhật danh mục") {

        @Override
        public ExitStatus doExecute(CommandContext context) {
            List<CatalogChange> changes = loadChanges();
            UpdateReport report = batchService.updateIndividually(changes);

            context.outputWriter().println(report.summary());
            for (ItemFailure failure : report.failures()) {
                context.outputWriter().println(
                        "- " + failure.itemId() + ": " + failure.reason());
            }
            context.outputWriter().flush();

            if (!report.isComplete()) {
                return new ExitStatus(20, "PARTIAL_UPDATE");
            }
            return ExitStatus.OK;
        }
    };
}
```

`loadChanges()` đại diện cho phần đọc dữ liệu đầu vào của ứng dụng. Mã `20` là quy ước do ứng dụng chọn cho trạng thái cập nhật một phần; cần ghi rõ quy ước đó trong tài liệu CLI để script gọi command biết cách xử lý.

Kết quả hiển thị có thể như sau:

```text
Đã xử lý 5 mục: 3 thành công, 2 thất bại.
- config-c: Giá trị không hợp lệ.
- config-e: Hết thời gian chờ dịch vụ đích; cần kiểm tra trạng thái.
```

Exit status `PARTIAL_UPDATE` có mã khác 0 nên pipeline không nhầm trạng thái này với thành công hoàn toàn. Đồng thời, người vận hành biết những mục nào cần kiểm tra hoặc chạy lại.

## Spring Shell 4.x: ExitStatus và exception mapping

`ExitStatus` trong Spring Shell 4.x là record gồm `code` và `description`, nằm trong package `org.springframework.shell.core.command`. Các status dựng sẵn gồm:

| Status | Mục đích |
|---|---|
| `ExitStatus.OK` | Command hoàn tất thành công |
| `ExitStatus.EXECUTION_ERROR` | Lỗi khi thực thi command |
| `ExitStatus.USAGE_ERROR` | Lỗi cách dùng hoặc đầu vào command |
| `ExitStatus.AVAILABILITY_ERROR` | Command chưa khả dụng |
| `new ExitStatus(code, description)` | Mã và mô tả do ứng dụng định nghĩa |

Với command programmatic cần chủ động trả status dựa trên kết quả nghiệp vụ, dùng `AbstractCommand.doExecute()` như ví dụ trên. Với command annotation-based, lỗi phát sinh trong method được chuyển thành `ExitStatus` qua `ExitStatusExceptionMapper`.

### Map exception thành status

Khi một exception thể hiện cập nhật thất bại hoặc một phần, có thể tạo mapper bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Bean
ExitStatusExceptionMapper updateExceptionMapper() {
    return exception -> {
        if (exception instanceof PartialUpdateException) {
            return new ExitStatus(20, "PARTIAL_UPDATE");
        }
        return ExitStatus.EXECUTION_ERROR;
    };
}
```

Gắn mapper vào command annotation bằng tên bean:

```java
@Command(
        name = "catalog-update",
        exitStatusExceptionMapper = "updateExceptionMapper")
public void update() {
    UpdateReport report = catalogBatchService.updateIndividually(loadChanges());
    if (!report.isComplete()) {
        throw new PartialUpdateException(report);
    }
    System.out.println("Đã cập nhật toàn bộ danh mục.");
}
```

`PartialUpdateException` cần giữ lại `UpdateReport` hoặc thông tin lỗi đủ để exception handler có thể ghi chi tiết phù hợp. Ví dụ này minh họa ánh xạ status; nếu cần in danh sách lỗi, hãy ghi summary qua output writer ở command adapter hoặc tạo một lớp xử lý phù hợp để giữ nội dung lỗi.

Một exception đơn giản có thể giữ số lượng thành công/thất bại trong message:

```java
public class PartialUpdateException extends RuntimeException {

    public PartialUpdateException(UpdateReport report) {
        super("Đã cập nhật " + report.succeeded() + "/" + report.attempted()
                + " mục; còn " + report.failed() + " mục thất bại.");
    }
}
```

Mapper chỉ được gọi khi exception đi ra khỏi command. Nếu command bắt exception rồi trả về bình thường, mapper không thể biết thao tác đã thất bại. Đặc biệt, không bắt exception rồi in `Đã cập nhật thành công` hoặc trả `ExitStatus.OK`.

### Command status và process exit code là hai lớp khác nhau

Spring Shell 4.x mô tả `ExitStatus` là trạng thái của command. Tài liệu exception handling cũng phân biệt command status với mã thoát của tiến trình JVM; cấu hình `ExitStatusExceptionMapper` tự nó không cấu hình process exit code.

Khi chạy CLI trong pipeline, cần xác minh mã thoát của tiến trình thật bằng integration test hoặc chạy ứng dụng như một process. Không chỉ kiểm tra `ExitStatus` nội bộ hay nội dung terminal rồi kết luận shell script sẽ nhận đúng `$?` hoặc `%ERRORLEVEL%`. Đặc biệt, non-interactive runner và cách đóng ứng dụng phải được kiểm tra trên đúng phiên bản Spring Shell/Spring Boot của dự án.

## Spring Shell 3.x: exit code và exception resolver

Trong Spring Shell 3.3.x/3.4.x, exception handling dùng `CommandHandlingResult`, `CommandExceptionResolver`, `@ExceptionResolver` và `@ExitCode`. API khác với `ExitStatusExceptionMapper` của 4.x.

### Mã mặc định và CommandRegistration

Tài liệu Spring Shell 3.3.4 mô tả mã mặc định:

| Trường hợp | Exit code mặc định |
|---|---:|
| Lỗi phân tích option command | `2` |
| Lỗi tổng quát | `1` |
| Không có lỗi | `0` |

Với command đăng ký programmatic, có thể cấu hình ánh xạ exception sang exit code bằng `CommandRegistration.Builder.withExitCode()`:

```java
CommandRegistration registration = CommandRegistration.builder()
        .command("catalog-update")
        .withExitCode()
            .map(PartialUpdateException.class, 20)
            .and()
        .build();
```

Ví dụ trên gắn mã `20` cho `PartialUpdateException`. Mô hình annotation mới của 3.x không cung cấp cùng cấu hình `withExitCode()` trên annotation; với annotation legacy, dùng `@ExceptionResolver` và `@ExitCode`.

### Dùng @ExceptionResolver trong annotation legacy

Một method `@ExceptionResolver` có thể trả về `String`, `CommandHandlingResult` hoặc `void`. Khi xử lý lỗi, phải chú ý mã thoát mà từng kiểu trả về tạo ra. Tài liệu 3.3.4 ghi rõ method trả `void` được xem là đã xử lý exception và mặc định có exit code `0`. Nếu dùng `void` để xử lý một lỗi, cần gắn `@ExitCode` khác 0; nếu không, script có thể nhận thành công dù thao tác đã thất bại.

```java
@ShellComponent
class CatalogExceptionHandlers {

    @ExceptionResolver
    @ExitCode(code = 20)
    String partialUpdate(PartialUpdateException exception) {
        return "Cập nhật một phần: " + exception.getMessage();
    }
}
```

Với cách này, exception được xử lý thành thông báo cho người dùng và exit code `20`. Nếu muốn trả cả thông điệp lẫn mã trong một đối tượng, dùng `CommandHandlingResult`:

```java
@ExceptionResolver
CommandHandlingResult partialUpdate(PartialUpdateException exception) {
    return CommandHandlingResult.of(
            "Cập nhật một phần: " + exception.getMessage(), 20);
}
```

Đây là API 3.x legacy. Trong Spring Shell 4.x, `@ShellComponent`, `@ExceptionResolver`, `@ExitCode`, `CommandHandlingResult` và `CommandExceptionResolver` của mô hình cũ đã được thay thế trong command programming model mới; dùng `ExitStatus` và `ExitStatusExceptionMapper`.

## Không che giấu lỗi khi muốn trả kết quả một phần

Một lỗi thiết kế phổ biến là bắt mọi exception, log rồi trả `true` hoặc chuỗi `Done`:

```java
// Không nên: exception bị nuốt và caller không biết cập nhật thất bại.
public String update() {
    try {
        updateService.updateAll();
        return "Đã cập nhật thành công";
    } catch (Exception exception) {
        log.error("Update failed", exception);
        return "Đã cập nhật thành công";
    }
}
```

Nếu nghiệp vụ yêu cầu fail-fast, hãy để exception đi lên lớp command handler. Nếu nghiệp vụ yêu cầu continue-on-error, bắt lỗi ở ranh giới từng mục, tổng hợp report, rồi command phải phát status một phần khác 0.

Không dùng `catch (Exception)` để gom mọi lỗi thành cùng một kết quả nếu cần phân biệt:

- Validation error: người dùng cần sửa input.
- Authorization error: cần cấp quyền phù hợp.
- Transient infrastructure error: có thể retry sau khi kiểm tra trạng thái.
- Conflict: dữ liệu đã thay đổi bởi actor khác.
- Partial update: một số mục đã commit và cần reconcile.

Thông điệp nên cho biết số lượng và phạm vi ảnh hưởng. Không ghi bí mật, token, mật khẩu hoặc toàn bộ payload nhạy cảm vào terminal/log khi hiển thị nguyên nhân lỗi.

## Compensation khi không có transaction bao trùm

Một lệnh có thể cập nhật nhiều hệ thống: database, API quản lý tài nguyên, hệ thống cấp quyền và dịch vụ thông báo. Transaction database không thể tự rollback các hệ thống độc lập này.

Nếu nghiệp vụ cần đưa hệ thống về trạng thái nhất quán sau lỗi, hãy thiết kế compensation hoặc saga:

1. Ghi nhận mỗi bước và kết quả xác nhận.
2. Khi bước sau thất bại, xác định bước trước có thể bù được hay không.
3. Chạy hành động bù theo thứ tự phù hợp, có idempotency và có thể retry.
4. Nếu compensation cũng thất bại, ghi rõ trạng thái cần can thiệp thủ công.
5. Trả status khác 0 và thông báo rõ bước nào đã thành công, bước nào đã được bù, bước nào còn chưa xử lý.

Không gọi compensation là rollback nếu nó là một thao tác nghiệp vụ mới có thể thất bại. Ví dụ, xóa một tài nguyên vừa tạo là hành động bù; nếu xóa không thành công, tài nguyên vẫn tồn tại và kết quả phải phản ánh điều đó.

## Thiết kế mã thoát cho script và CI/CD

Mã thoát là giao ước giữa CLI và chương trình gọi nó. Hãy định nghĩa mã rõ ràng, ổn định và không trùng nghĩa:

| Mã ví dụ | Ý nghĩa |
|---:|---|
| `0` | Hoàn tất toàn bộ |
| `2` | Cú pháp hoặc tham số không hợp lệ |
| `10` | Thất bại nghiệp vụ, không có thay đổi được xác nhận |
| `20` | Hoàn thành một phần; cần kiểm tra/reconcile |
| `30` | Kết quả chưa xác định sau timeout; cần truy vấn trạng thái |
| `40` | Compensation thất bại hoặc cần can thiệp thủ công |

Đây là quy ước minh họa của ứng dụng, không phải bảng mã bắt buộc của Spring Shell. Tài liệu command và pipeline phải thống nhất cách diễn giải. Nếu pipeline chỉ phân biệt zero và non-zero, có thể dùng mọi mã khác 0 cho thất bại; nếu cần nhánh xử lý riêng, giữ bảng mã cụ thể và kiểm thử từng nhánh.

Ví dụ shell script:

```bash
./customer-cli catalog-update
status=$?

case "$status" in
  0)  echo "Cập nhật hoàn tất" ;;
  20) echo "Cập nhật một phần; cần đối soát"; exit 20 ;;
  30) echo "Kết quả chưa xác định; kiểm tra trạng thái đích"; exit 30 ;;
  *)  echo "Cập nhật thất bại (code=$status)"; exit "$status" ;;
esac
```

Không để pipeline bỏ qua status khi chạy command nối tiếp bằng `;` hoặc khi wrapper luôn kết thúc với `exit 0`. Hãy bật chế độ fail-fast phù hợp hoặc chủ động kiểm tra mã trả về sau mỗi bước.

## Kiểm thử để bảo đảm không báo thành công sai

Kiểm thử cần bao phủ cả trạng thái dữ liệu và status của command. Một test chỉ kiểm tra chuỗi `Đã cập nhật` không đủ nếu exit status vẫn là `0` khi có lỗi.

| Kịch bản | Trạng thái dữ liệu mong đợi | Status mong đợi |
|---|---|---|
| Mọi mục cập nhật thành công | Tất cả mục đạt trạng thái đích | `0` / `ExitStatus.OK` |
| Lỗi xảy ra trong transaction all-or-nothing | Không có thay đổi nào được commit | Non-zero |
| Continue-on-error, có mục lỗi | Các mục thành công đã commit; mục lỗi được liệt kê | Non-zero, ví dụ `20` |
| Request timeout, chưa rõ kết quả | Chưa thể kết luận; cần query/reconcile | Non-zero, ví dụ `30` |
| Compensation hoàn tất | Hệ thống đã được bù theo chính sách | Non-zero nếu yêu cầu gốc thất bại; thông báo nêu rõ đã bù |
| Compensation thất bại | Có trạng thái chưa nhất quán cần xử lý | Non-zero riêng, ví dụ `40` |
| Input sai | Không bắt đầu cập nhật | Usage/validation error |

Các kiểm thử quan trọng:

1. Unit test service all-or-nothing: ném lỗi ở mục giữa và xác nhận transaction rollback.
2. Unit test continue-on-error: một số mục thành công, một số mục lỗi; report có attempted/succeeded/failed chính xác.
3. Test command: report một phần phải trả `ExitStatus` có code khác 0.
4. Test exception mapper: `PartialUpdateException` được map đúng code và description; lỗi không dự kiến không bị map thành `OK`.
5. Test `@ExceptionResolver` 3.x: resolver lỗi không trả `void` với exit code mặc định `0`.
6. Test rollback rule cho checked exception nếu service dùng checked exception.
7. Integration test với `ShellTestClient`: xác minh output có summary, item lỗi và không in thông báo thành công toàn bộ.
8. Process-level test: chạy ứng dụng như process con và kiểm tra `Process.exitValue()`/mã thoát mà CI nhận được.
9. Test timeout sau khi hệ thống đích đã commit: command phải báo chưa xác định hoặc truy vấn trạng thái, không kết luận thất bại chắc chắn.
10. Test script/pipeline: status non-zero không bị wrapper ghi đè thành `0`.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Command in thành công dù một mục lỗi | Exception bị bắt và trả kết quả bình thường | Tổng hợp report và trả status khác 0 hoặc ném exception có mapper |
| Transaction vẫn commit sau lỗi | Checked exception không nằm trong rollback rule hoặc exception bị nuốt | Dùng `rollbackFor` phù hợp và để lỗi thoát transaction boundary |
| Một phần dữ liệu đã cập nhật nhưng code là `0` | Dùng continue-on-error nhưng command luôn trả OK | Định nghĩa status riêng cho partial update |
| Resolver 3.x xử lý lỗi nhưng exit code là `0` | Method `@ExceptionResolver` trả `void` mà không có `@ExitCode` | Trả `CommandHandlingResult` hoặc đặt `@ExitCode` khác 0 |
| ExitStatus 4.x không được pipeline nhận | Nhầm command status với JVM process exit code | Kiểm tra non-interactive process exit code trên đúng phiên bản |
| Mapper biến mọi exception thành cùng một lỗi | Không phân loại lỗi hoặc trả nhầm status | Map exception theo loại; lỗi không biết phải là non-zero |
| Báo rollback dù API từ xa đã xử lý | Giả định transaction cục bộ bao phủ hệ thống ngoài | Query trạng thái, dùng idempotency và compensation |
| Báo hoàn tất dù compensation lỗi | Không đưa kết quả compensation vào report | Trả status cần can thiệp và liệt kê bước còn tồn đọng |
| Test pass nhưng CI vẫn chạy bước tiếp | Chỉ test nội dung output, không kiểm tra process code | Thêm process-level test và kiểm tra wrapper pipeline |

## Quy trình triển khai

1. Xác định chính sách cập nhật: all-or-nothing, stop-on-first-error hay continue-on-error.
2. Xác định ranh giới transaction và những hệ thống không tham gia transaction.
3. Định nghĩa kiểu kết quả nghiệp vụ có số lượng, danh sách lỗi và trạng thái chưa xác định nếu cần.
4. Chỉ in thông báo thành công sau khi commit hoặc xác nhận trạng thái đích.
5. Nếu có partial update, trả summary chính xác và exit code khác 0.
6. Nếu lỗi phải kích hoạt rollback, để exception đi qua transaction boundary hoặc cấu hình rollback rule.
7. Nếu dùng Spring Shell 4.x, trả `ExitStatus` từ programmatic command hoặc dùng `ExitStatusExceptionMapper` cho exception.
8. Nếu dùng Spring Shell 3.x, cấu hình `withExitCode()` hoặc `@ExceptionResolver`/`@ExitCode` theo mô hình command đang dùng.
9. Với API/file/email hoặc side effect ngoài transaction, thiết kế compensation và reconciliation.
10. Kiểm thử cả dữ liệu sau chạy, thông báo, command status và process exit code.

Một command đáng tin cậy phải nói đúng điều hệ thống đã xác nhận. Khi cập nhật thất bại hoặc chỉ hoàn thành một phần, nội dung trả về và mã thoát đều phải giúp caller nhận ra cần dừng, retry có kiểm soát hay đối soát thủ công.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html): `ExitStatusExceptionMapper`, đăng ký bằng `Command.Builder` hoặc `@Command`, và phân biệt command status với JVM process exit code.
- [Spring Shell 4.0.3 API — ExitStatus](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html): record `code`, `description` và các status dựng sẵn.
- [Spring Shell 4.0.3 API — AbstractCommand](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html): `doExecute(CommandContext)` trả về `ExitStatus`.
- [Spring Shell 4.0.3 API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html): hợp đồng `execute(CommandContext)` trả về status.
- [Spring Shell 3.3.4 — Exit Code Mappings](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/mappings.html): mã mặc định và `CommandRegistration.Builder.withExitCode()`.
- [Spring Shell 3.3.4 — @ExceptionResolver](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/annotation.html): `CommandHandlingResult`, `@ExitCode` và hành vi của resolver trả `void`.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): quy tắc rollback mặc định và cấu hình rollback cho checked exception.
- [Spring Framework — @Transactional Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): các thuộc tính transaction và `rollbackFor`.
- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html): `ShellTestClient`, `ShellScreen` và `ShellAssertions` để kiểm thử command/output.
