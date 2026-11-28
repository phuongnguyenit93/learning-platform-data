# PrintWriter từ CommandContext trong mô hình 4.x

Trong Spring Shell 4.x, một command có thể ghi nội dung trực tiếp vào shell thông qua **PrintWriter** lấy từ **CommandContext**. Đây là cách được khuyến nghị khi command cần chủ động điều khiển nhiều dòng output, định dạng bảng, in kết quả theo từng phần hoặc tạo dữ liệu có cấu trúc. Thay vì ghi thẳng vào **System.out**, command dùng writer mà Spring Shell cung cấp cho lần gọi hiện tại.

API này thuộc package **org.springframework.shell.core.command**. **CommandContext** là record chứa thông tin runtime của lần thực thi command, trong đó có **outputWriter()** trả về **java.io.PrintWriter**. API CommandContext được giới thiệu từ Spring Shell 4.0.0.

```java
@Command(name = "hello")
public void hello(CommandContext context) {
    context.outputWriter().println("Xin chào!");
    context.outputWriter().flush();
}
```

Đoạn code ngắn trên thể hiện hai thao tác cốt lõi:

1. Lấy writer từ **context.outputWriter()**.
2. Ghi nội dung bằng các phương thức của **PrintWriter**, sau đó gọi **flush()** khi cần đẩy dữ liệu ra ngay.

## 1. CommandContext cung cấp writer nào?

Trong Spring Shell 4.x, CommandContext là record có các thành phần chính:

| Thành phần | Kiểu | Vai trò |
| --- | --- | --- |
| **parsedInput()** | ParsedInput | Kết quả phân tích command người dùng đã nhập |
| **commandRegistry()** | CommandRegistry | Registry chứa các command đã đăng ký |
| **outputWriter()** | PrintWriter | Ghi nội dung của command vào shell output |
| **inputReader()** | InputReader | Đọc dữ liệu người dùng nhập trong command |

Ngoài các accessor của record, context còn cung cấp các phương thức tiện ích như **getOptionByName(...)**, **getOptionByLongName(...)**, **getOptionByShortName(...)** và **getArgumentByIndex(...)**.

Trong bài này, trọng tâm là **outputWriter()**. Nó trả về một PrintWriter đã được gắn với ngữ cảnh thực thi shell. Command sử dụng writer đó để gửi văn bản đến đầu ra mà Spring Shell đang quản lý.

Import trong Spring Shell 4.0.3:

```java
import java.io.PrintWriter;

import org.springframework.shell.core.command.CommandContext;
```

Không tự tạo **new PrintWriter(System.out)** để thay thế writer được cấp. Làm như vậy sẽ bỏ qua writer gắn với lần thực thi command và có thể khiến nội dung không đi theo cùng luồng output mà shell, test hoặc runner đang quản lý.

## 2. Khi nào dùng outputWriter và khi nào return giá trị?

Với command annotation, Spring Shell có thể tự in giá trị mà method trả về. Nếu command chỉ cần trả một chuỗi ngắn, cách đó đơn giản:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(name = "hello")
    public String hello() {
        return "Xin chào từ Spring Shell";
    }
}
```

Khi method trả về một giá trị, Spring Shell chuyển giá trị đó thành shell output. Vì vậy, command không cần tự gọi **System.out.println(...)**.

Dùng **CommandContext.outputWriter()** khi command cần kiểm soát cách ghi:

- In nhiều dòng theo trình tự cụ thể.
- In bảng hoặc báo cáo có căn cột.
- Ghi từng phần kết quả khi xử lý dữ liệu.
- Tạo output JSON, CSV hoặc định dạng văn bản do ứng dụng quy định.
- Chủ động gọi **flush()** để đẩy nội dung trước khi command hoàn tất.

Ví dụ method trả void và tự ghi:

```java
import java.io.PrintWriter;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    @Command(name = "report summary")
    public void summary(CommandContext context) {
        PrintWriter out = context.outputWriter();
        out.println("Báo cáo tổng quan");
        out.println("Số dự án: 12");
        out.println("Trạng thái: READY");
        out.flush();
    }
}
```

Tránh vừa ghi toàn bộ kết quả bằng outputWriter() vừa trả về một chuỗi chứa lại cùng nội dung. Nếu method có return value, Spring Shell có thể in thêm giá trị đó sau phần đã ghi, khiến output bị lặp hoặc khó dự đoán. Hãy chọn một cách làm chủ đạo cho mỗi command.

## 3. Lấy writer một lần và tái sử dụng trong command

Có thể lấy writer ra biến cục bộ để code dễ đọc:

```java
@Command(name = "project status")
public void status(CommandContext context) {
    PrintWriter out = context.outputWriter();

    out.println("Workspace: demo");
    out.println("Branch: main");
    out.println("Build: SUCCESS");
    out.flush();
}
```

Việc gán vào biến cục bộ giúp:

- Giảm lặp **context.outputWriter()** ở nhiều dòng.
- Dễ truyền writer vào một helper được gọi ngay trong command.
- Làm rõ mọi output của command đang đi qua cùng một writer.

Ví dụ tách phần trình bày thành helper:

```java
private void printProject(PrintWriter out, Project project) {
    out.println("Mã dự án: " + project.id());
    out.println("Tên dự án: " + project.name());
    out.println("Trạng thái: " + project.status());
}

@Command(name = "project show")
public void show(CommandContext context) {
    Project project = projectService.findCurrent();
    PrintWriter out = context.outputWriter();

    printProject(out, project);
    out.flush();
}
```

Helper chỉ nhận writer để trình bày dữ liệu. Nó không cần biết writer đến từ terminal, test hay một runner khác.

Không lưu CommandContext hoặc PrintWriter vào field của một Spring singleton để dùng cho lần gọi command sau. Context mô tả một lần thực thi cụ thể; hãy lấy writer trong method xử lý command và truyền nó xuống các helper chỉ trong phạm vi lời gọi đó.

## 4. Các phương thức ghi thường dùng

**PrintWriter** là lớp tiện ích của JDK để ghi văn bản và dữ liệu đã định dạng. Những phương thức thường dùng gồm:

| Phương thức | Tác dụng | Ví dụ |
| --- | --- | --- |
| **print(value)** | Ghi giá trị, không tự thêm dòng mới | **out.print("Đang chạy");** |
| **println(value)** | Ghi giá trị rồi kết thúc dòng | **out.println("Hoàn tất");** |
| **write(text)** | Ghi chuỗi ký tự, không tự thêm dòng mới | **out.write("READY");** |
| **append(text)** | Nối thêm ký tự hoặc chuỗi | **out.append("OK");** |
| **printf(format, args...)** | Ghi chuỗi theo format | **out.printf("Tổng: %d%n", total);** |
| **format(format, args...)** | Ghi chuỗi theo format | **out.format("%-12s %d%n", name, count);** |
| **flush()** | Đẩy dữ liệu đang đệm ra đích | **out.flush();** |
| **checkError()** | Flush và kiểm tra trạng thái lỗi ghi | **boolean failed = out.checkError();** |

### print và println

**print(...)** không tự kết thúc dòng:

```java
out.print("Đang xử lý ");
out.print(25);
out.println("%");
out.flush();
```

Output:

```text
Đang xử lý 25%
```

**println(...)** ghi giá trị rồi dùng ký tự phân cách dòng của hệ điều hành. Khi muốn mỗi thông tin nằm trên một dòng riêng, đây là lựa chọn dễ đọc nhất:

```java
out.println("Tên: api-service");
out.println("Trạng thái: RUNNING");
out.println("Phiên bản: 1.4.2");
out.flush();
```

### write và append

**write(...)** ghi đúng chuỗi được truyền vào, không tự thêm dòng mới:

```java
out.write("id,name,status\n");
out.write("P101,Portal,READY\n");
out.flush();
```

**append(...)** hữu ích khi ghép nhiều đoạn văn bản:

```java
out.append("Dự án ")
        .append(project.id())
        .append(" đã chuyển sang ")
        .append(project.status())
        .println();
out.flush();
```

**append(...)** trả lại chính writer, nên có thể nối chuỗi lời gọi. Với dữ liệu cần định dạng phức tạp, **printf(...)** thường dễ đọc hơn.

## 5. Định dạng output bằng printf và format

**printf(...)** dùng format string tương tự **String.format(...)**. Ví dụ, **%s** dành cho chuỗi, **%d** dành cho số nguyên, **%f** dành cho số thực và **%n** tạo ký tự kết thúc dòng theo nền tảng:

```java
out.printf("Dự án: %s%n", project.name());
out.printf("Số tác vụ: %d%n", taskCount);
out.printf("Tỷ lệ hoàn tất: %.1f%%%n", completionRate);
out.flush();
```

Trong format string, **%%** tạo ký tự **%** theo nghĩa đen. Vì vậy, **%.1f%%** hiển thị số thực với một chữ số thập phân rồi thêm dấu phần trăm.

### Căn cột cho báo cáo

Có thể dùng độ rộng trường để tạo bảng văn bản:

```java
out.printf("%-12s %-24s %10s%n", "ID", "PROJECT", "TASKS");
out.printf("%-12s %-24s %10d%n", "P101", "Customer Portal", 18);
out.printf("%-12s %-24s %10d%n", "P102", "Inventory API", 7);
out.flush();
```

Output minh họa:

```text
ID           PROJECT                       TASKS
P101         Customer Portal                  18
P102         Inventory API                     7
```

Trong format:

- **%-12s** căn trái chuỗi trong vùng rộng 12 ký tự.
- **%-24s** căn trái tên dự án trong vùng rộng 24 ký tự.
- **%10d** căn phải số nguyên trong vùng rộng 10 ký tự.

Độ rộng format tính theo đơn vị ký tự mà formatter sử dụng, không đảm bảo mọi ký tự Unicode chiếm đúng một ô hiển thị terminal. Nếu bảng có tiếng Việt, emoji hoặc ký tự CJK, cần kiểm tra trực tiếp trên terminal mục tiêu; với bảng phức tạp, cân nhắc thư viện bảng có hỗ trợ độ rộng hiển thị Unicode.

### Chọn Locale khi định dạng số

**printf(...)** có overload nhận **Locale**. Dùng locale tường minh khi muốn kết quả nhất quán giữa máy chạy:

```java
import java.util.Locale;

out.printf(
        Locale.ROOT,
        "Completion: %.2f%%%n",
        completionRate
);
out.flush();
```

**Locale.ROOT** hữu ích cho output kỹ thuật hoặc dữ liệu máy đọc vì không phụ thuộc locale mặc định của máy. Nếu đang tạo báo cáo dành cho người dùng, có thể chọn locale phù hợp với ngôn ngữ và quy ước số mà ứng dụng công bố.

## 6. Ghi output nhiều phần và thời điểm flush

**PrintWriter** có thể ghi qua một lớp đệm. **flush()** yêu cầu writer đẩy phần dữ liệu đang đệm xuống đích hiện tại. Tài liệu Spring Shell minh họa việc gọi **flush()** sau khi ghi output.

Ví dụ ghi nhiều dòng rồi flush một lần:

```java
PrintWriter out = context.outputWriter();

out.println("Đang kiểm tra cấu hình...");
out.println("Đang kết nối repository...");
out.println("Đã tải 42 dự án.");
out.flush();
```

Với output theo từng mốc, flush sau mỗi nhóm thông tin cần người dùng nhìn thấy ngay:

```java
out.println("Bắt đầu đồng bộ...");
out.flush();

syncService.prepare();
out.println("Đã chuẩn bị dữ liệu.");
out.flush();

syncService.execute();
out.println("Đồng bộ hoàn tất.");
out.flush();
```

Không cần gọi **flush()** sau từng ký tự hoặc từng thao tác nhỏ nếu có thể gom nhiều dòng. Flush quá thường xuyên có thể làm giảm hiệu năng. Hãy flush tại ranh giới có ý nghĩa: sau một báo cáo, sau một nhóm kết quả hoặc sau thông báo tiến độ mà người dùng cần thấy ngay.

### Phân biệt newline và flush

**println(...)** kết thúc dòng; điều đó không đồng nghĩa chắc chắn dữ liệu đã được flush. Tự động flush phụ thuộc cách writer được tạo. Vì command không nên giả định cấu hình auto-flush của writer do framework cung cấp, hãy gọi **flush()** tường minh khi cần bảo đảm dữ liệu được đẩy ra.

## 7. Kiểm tra lỗi ghi với checkError()

Khác với nhiều API ghi dữ liệu khác, các phương thức của **PrintWriter** không ném **IOException** khi thao tác ghi thất bại. PrintWriter giữ trạng thái lỗi nội bộ; có thể kiểm tra bằng **checkError()**.

```java
PrintWriter out = context.outputWriter();
out.println("Đã xuất báo cáo.");
out.flush();

if (out.checkError()) {
    logger.warn("Không thể ghi đầy đủ output của command.");
}
```

**checkError()** cũng flush writer nếu writer chưa đóng, sau đó trả về **true** nếu đã xảy ra lỗi ghi. Điều này hữu ích khi output đi qua pipe hoặc terminal đã đóng. Không nên giả định rằng mọi lần gọi **println(...)** đều ném exception nếu thiết bị đầu ra gặp sự cố.

Với output thông thường, không cần kiểm tra sau từng dòng. Với thao tác xuất dữ liệu quan trọng hoặc output lớn, kiểm tra ở cuối một đơn vị ghi hợp lý để có thể phát hiện lỗi và ghi log.

## 8. Không đóng writer do CommandContext cung cấp

Command không tạo PrintWriter này và không sở hữu tài nguyên bên dưới. Vì vậy, không gọi **close()** trên **context.outputWriter()**:

```java
// Không nên làm:
try (PrintWriter out = context.outputWriter()) {
    out.println("Kết quả");
}
```

Đóng writer có thể đóng luôn luồng output mà shell đang sử dụng cho lần thực thi hiện tại hoặc những hoạt động tiếp theo. Hãy chỉ ghi và flush; để framework quản lý vòng đời writer.

Nếu command tự mở file để ghi báo cáo, đó là tài nguyên riêng của ứng dụng. Khi đó dùng **Files.newBufferedWriter(...)**, **BufferedWriter** hoặc **PrintWriter** tự tạo cho file, rồi đóng tài nguyên do command tạo bằng try-with-resources. Không nhầm writer của file với writer của shell.

Ví dụ ghi file riêng:

```java
Path reportFile = Path.of("report.txt");

try (BufferedWriter fileWriter = Files.newBufferedWriter(reportFile)) {
    fileWriter.write("Báo cáo dự án");
    fileWriter.newLine();
    fileWriter.write("Trạng thái: READY");
}

context.outputWriter().println(
        "Đã lưu báo cáo tại " + reportFile.toAbsolutePath()
);
context.outputWriter().flush();
```

**BufferedWriter** ở đây thuộc quyền quản lý của command và được đóng sau khi ghi. **context.outputWriter()** vẫn được giữ nguyên để thông báo kết quả cho shell.

## 9. Vì sao nên dùng outputWriter thay cho System.out?

JDK cho phép ghi trực tiếp bằng **System.out**, nhưng Spring Shell khuyến nghị lấy **PrintWriter** từ **CommandContext**. Lý do là writer được cung cấp trong context thuộc luồng output của lần thực thi command.

| Cách ghi | Đặc điểm | Khuyến nghị |
| --- | --- | --- |
| **context.outputWriter()** | Ghi qua shell output writer của command | Ưu tiên trong command |
| **System.out.println(...)** | Ghi thẳng vào standard output của JVM | Tránh dùng để in kết quả command |
| Logger | Ghi thông tin chẩn đoán theo cấu hình logging | Dùng cho log vận hành |
| Writer tự tạo cho file | Ghi dữ liệu vào file do ứng dụng quản lý | Dùng khi cần xuất file riêng |

Ghi trực tiếp vào **System.out** có thể khiến nội dung đi ngoài luồng output mà shell hoặc test đang thu thập. Khi test command, output ghi qua CommandContext có thể được quan sát thông qua test infrastructure của Spring Shell; nội dung ghi trực tiếp ra standard output có thể không nằm trong cùng kết quả kiểm thử.

Không dùng PrintWriter để ghi byte nhị phân. Nó là writer ký tự. Nếu command cần tạo archive, ảnh hoặc file nhị phân, hãy dùng API byte stream hoặc **Files** để ghi file.

## 10. Ghi JSON hoặc CSV qua outputWriter

Khi command được dùng trong script, output có thể là dữ liệu để một chương trình khác parse. Có thể serialize dữ liệu thành chuỗi rồi ghi qua writer:

```java
@Command(name = "project export-json")
public void exportJson(CommandContext context) throws JsonProcessingException {
    String json = objectMapper.writeValueAsString(projectService.findAll());

    PrintWriter out = context.outputWriter();
    out.println(json);
    out.flush();
}
```

Với CSV, có thể ghi header và từng bản ghi:

```java
@Command(name = "project export-csv")
public void exportCsv(CommandContext context) {
    PrintWriter out = context.outputWriter();

    out.println("id,name,status");
    for (Project project : projectService.findAll()) {
        out.printf(
                "%s,%s,%s%n",
                csv(project.id()),
                csv(project.name()),
                csv(project.status())
        );
    }
    out.flush();
}
```

Hàm **csv(...)** cần escape dấu nháy kép và bao trường trong dấu nháy khi giá trị chứa dấu phẩy, dấu nháy hoặc ký tự xuống dòng. Ví dụ minh họa trên giả định ứng dụng đã có hàm escape CSV đúng chuẩn; không nên nối chuỗi CSV trực tiếp với dữ liệu tùy ý.

Nếu output là hợp đồng máy đọc, chỉ ghi dữ liệu đã công bố vào writer. Đưa thông tin debug, lời chào hoặc thông báo trạng thái sang logger. Banner, prompt hoặc log từ cấu hình ứng dụng cũng có thể làm hỏng dữ liệu nếu chúng được ghi cùng stream; cần cấu hình runner và logging phù hợp với chế độ non-interactive.

## 11. Tách phần trình bày khỏi service nghiệp vụ

Service nên trả dữ liệu hoặc kết quả nghiệp vụ. Command chịu trách nhiệm chuyển dữ liệu thành output shell. Cách phân chia này giúp service có thể được dùng từ REST API, batch job, test hoặc command khác mà không phụ thuộc vào CommandContext.

Ví dụ service trả dữ liệu:

```java
public record ProjectSummary(
        String id,
        String name,
        String status,
        int openTasks) {
}
```

Command định dạng dữ liệu bằng writer:

```java
@Command(name = "project summary")
public void summary(CommandContext context) {
    List<ProjectSummary> summaries = projectService.getSummaries();
    PrintWriter out = context.outputWriter();

    out.printf("%-10s %-22s %-12s %8s%n",
            "ID", "NAME", "STATUS", "OPEN");

    for (ProjectSummary item : summaries) {
        out.printf("%-10s %-22s %-12s %8d%n",
                item.id(),
                item.name(),
                item.status(),
                item.openTasks());
    }
    out.flush();
}
```

Service không biết PrintWriter là gì. Command có thể thay đổi format bảng mà không sửa quy tắc lấy dữ liệu hoặc nghiệp vụ của service.

## 12. Dùng writer trong command khai báo và command lập trình

Spring Shell 4.x hỗ trợ hai cách định nghĩa command. Cả hai đều có thể sử dụng **CommandContext.outputWriter()**.

### Annotation model

Đặt **@Command** trên method của một Spring bean:

```java
import java.io.PrintWriter;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class BuildCommands {

    @Command(name = "build report")
    public void report(CommandContext context) {
        PrintWriter out = context.outputWriter();
        out.println("Build: SUCCESS");
        out.println("Duration: 18 seconds");
        out.flush();
    }
}
```

Trong ứng dụng Spring Boot, auto-configuration đăng ký các command annotation được tìm thấy trong application context. Nếu không dùng Spring Boot, cần bật đăng ký command bằng **@EnableCommand** trên cấu hình phù hợp.

### Programmatic model

Có thể khai báo command bằng bean **Command** và dùng **AbstractCommand**:

```java
import java.io.PrintWriter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
public class BuildCommandConfiguration {

    @Bean
    Command buildReport() {
        return new AbstractCommand("build report", "In báo cáo build") {
            @Override
            public ExitStatus doExecute(CommandContext context) {
                PrintWriter out = context.outputWriter();
                out.println("Build: SUCCESS");
                out.println("Duration: 18 seconds");
                out.flush();
                return ExitStatus.OK;
            }
        };
    }
}
```

**AbstractCommand** cũng cung cấp helper **println(message, commandContext)** cho trường hợp chỉ cần in một thông báo. Khi cần nhiều dòng, format hoặc flush chủ động, lấy PrintWriter ra sẽ linh hoạt hơn.

## 13. Kiểm thử outputWriter

Khi kiểm thử command trong Spring Shell 4.x, có thể dùng **ShellTestClient** để gửi command và nhận **ShellScreen**. Output được ghi qua **CommandContext.outputWriter()** là nội dung thuộc shell output mà test client có thể kiểm tra.

Ví dụ:

```java
@Test
void printsBuildReport() throws Exception {
    ShellScreen screen = shellTestClient.sendCommand("build report");

    ShellAssertions.assertThat(screen)
            .containsText("Build: SUCCESS")
            .containsText("Duration: 18 seconds");
}
```

Nên kiểm tra những nội dung quan trọng mà người dùng cần nhìn thấy, không phụ thuộc vào toàn bộ khoảng trắng hoặc căn lề nếu đó không phải hợp đồng output. Với báo cáo dạng bảng, có thể kiểm tra header và một số giá trị tiêu biểu.

Nếu command ghi bằng **System.out**, test client có thể không thu được nội dung theo cách giống writer do shell cấp. Vì vậy, dùng outputWriter() cũng giúp test command nhất quán với cách command xuất nội dung khi chạy trong shell.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Output không xuất hiện ngay | Chưa flush writer | Gọi **flush()** sau nhóm nội dung cần hiển thị |
| Nội dung xuất hiện hai lần | Vừa ghi qua writer vừa return lại cùng chuỗi | Chọn một cách xuất output cho command |
| Output không xuất hiện trong ShellScreen | Ghi trực tiếp bằng System.out | Dùng **context.outputWriter()** |
| Command sau không ghi được output | Command trước đã gọi close() trên writer của context | Không đóng writer do framework cung cấp |
| Format bảng bị lệch | Độ rộng cột không đủ hoặc Unicode có độ rộng hiển thị khác | Điều chỉnh format và kiểm tra terminal thực tế |
| Phần trăm hiển thị sai dấu thập phân | Dùng locale mặc định không phù hợp | Dùng **printf(Locale.ROOT, ...)** hoặc locale mong muốn |
| Không bắt được IOException | PrintWriter không ném IOException từ các phương thức ghi thông thường | Dùng **checkError()** khi cần kiểm tra lỗi |
| JSON/CSV không parse được | Trộn log, prompt hoặc thông báo tự do vào output | Giữ writer cho dữ liệu; chuyển log sang logger và dùng non-interactive mode |
| Writer được dùng sau khi command kết thúc | Lưu writer vào bean hoặc truyền sang tác vụ nền kéo dài | Giữ writer trong phạm vi command; dùng cơ chế output phù hợp cho tác vụ nền |

## 15. Checklist sử dụng PrintWriter từ CommandContext

- Lấy writer bằng **context.outputWriter()** trong method command.
- Ưu tiên writer này thay cho **System.out** khi ghi nội dung command.
- Dùng **println(...)** cho các dòng riêng biệt.
- Dùng **printf(...)** hoặc **format(...)** để căn cột và định dạng số.
- Dùng locale tường minh nếu output cần ổn định giữa các máy.
- Gọi **flush()** sau một nhóm output hoặc mốc tiến độ cần hiển thị ngay.
- Dùng **checkError()** nếu cần phát hiện lỗi ghi.
- Không gọi **close()** trên writer do framework cung cấp.
- Không giữ CommandContext hoặc writer trong field của singleton.
- Không trộn log chẩn đoán vào JSON/CSV mà command xuất.
- Tách service nghiệp vụ khỏi lớp trình bày terminal.
- Kiểm tra output bằng **ShellTestClient** và **ShellScreen**.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html)
- [Spring Shell 4.0.3 — Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell 4.0.3 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0.3 — CommandContext API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html)
- [Spring Shell 4.0.3 — AbstractCommand API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html)
- [Java SE 21 — PrintWriter API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintWriter.html)
