# Lộ trình học từ lệnh đầu tiên đến công cụ có thể phân phối và kiểm thử

Spring Shell giúp biến một ứng dụng Spring thành công cụ dòng lệnh (CLI). Người dùng có thể mở shell để nhập lệnh tương tác, hoặc gọi lệnh từ terminal và script để tự động hóa công việc. Một CLI tốt cần nhiều hơn vài phương thức được gắn annotation: lệnh phải dễ nhớ, tham số phải rõ ràng, lỗi phải có hướng xử lý, output phải phù hợp với người đọc lẫn chương trình khác, và toàn bộ hành vi cần được kiểm thử trước khi phân phối.

Bài học này đi theo một dự án nhỏ xuyên suốt. Ở mỗi chặng, bạn sẽ tạo thêm một phần của CLI quản lý công việc, từ lệnh `hello` đầu tiên đến ứng dụng có thể chạy tự động, kiểm thử và đóng gói.

## 1. Xác định công việc mà CLI cần giải quyết

Trước khi tạo command, hãy mô tả người dùng và công việc họ cần hoàn thành. CLI thường phù hợp với các tác vụ có đầu vào rõ ràng, lặp lại được, cần chạy nhanh hoặc cần tích hợp vào quy trình tự động. Ví dụ: tạo công việc, liệt kê công việc đang mở, đánh dấu một công việc đã hoàn thành và xuất báo cáo.

Viết trước một bản phác thảo cú pháp:

| Nhu cầu | Lệnh dự kiến | Kết quả mong đợi |
| --- | --- | --- |
| Tạo công việc | `task-add --title "Viết tài liệu"` | Tạo một công việc và trả về mã định danh |
| Liệt kê công việc | `task-list --status OPEN` | Hiển thị các công việc đang mở |
| Hoàn thành công việc | `task-done --id 42` | Cập nhật trạng thái công việc số 42 |
| Xuất báo cáo | `task-export --format csv` | Xuất dữ liệu theo định dạng CSV |

Một command nên diễn đạt một hành động cụ thể. Dùng tên nhất quán, ưu tiên động từ và đối tượng; đặt tên option dễ hiểu; quy định rõ option nào bắt buộc, option nào có giá trị mặc định. Tránh để một lệnh vừa đọc dữ liệu, vừa sửa dữ liệu, vừa xuất báo cáo vì người dùng khó đoán tác động của nó.

Hãy quyết định ngay từ đầu lệnh sẽ được dùng theo những cách nào:

- **Tương tác:** người dùng mở shell, xem lời nhắc, nhập lệnh và nhận gợi ý.
- **Không tương tác:** một lệnh được truyền từ terminal, script hoặc hệ thống CI và trả kết quả rồi kết thúc.
- **Theo kịch bản:** nhiều lệnh được thực thi theo một chuỗi đã chuẩn bị.

Các cách chạy này nên dùng chung nghiệp vụ. Khác biệt chỉ nằm ở cách nhận đầu vào và trình bày kết quả.

## 2. Tạo ứng dụng Spring Shell và chạy command đầu tiên

Tạo một ứng dụng Spring Boot với JDK và phiên bản Spring Boot được Spring Shell release bạn chọn hỗ trợ. Thêm dependency `org.springframework.shell:spring-shell-starter` vào dự án. Với Maven, dependency có dạng:

```xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-starter</artifactId>
    <version>${spring-shell.version}</version>
</dependency>
```

Khai báo thuộc tính `spring-shell.version` theo phiên bản Spring Shell tương thích với Spring Boot của dự án. Không ghép tùy ý các phiên bản chỉ vì chúng là bản mới nhất; hãy kiểm tra ma trận tương thích và hướng dẫn của release đang sử dụng.

Ứng dụng vẫn khởi động như một ứng dụng Spring Boot thông thường:

```java
@SpringBootApplication
public class TaskCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskCliApplication.class, args);
    }
}
```

Tạo một lớp command và đánh dấu bằng `@ShellComponent`. Mỗi phương thức có `@ShellMethod` sẽ được Spring Shell đăng ký thành một lệnh:

```java
@ShellComponent
public class GreetingCommands {

    @ShellMethod(key = "hello", value = "Gửi lời chào")
    public String hello(
            @ShellOption(value = {"--name", "-n"}, defaultValue = "bạn")
            String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Trong ví dụ này:

- `@ShellComponent` cho Spring Shell biết lớp này chứa command.
- `@ShellMethod` khai báo command có tên `hello` và mô tả hiển thị trong phần trợ giúp.
- `@ShellOption` khai báo option `--name`, bí danh ngắn `-n` và giá trị mặc định `bạn`.
- Giá trị trả về là nội dung Spring Shell hiển thị cho người dùng.

Khi shell đang chạy, nhập `hello` để dùng giá trị mặc định hoặc `hello --name Ada` để truyền tên. Có thể dùng `-n` thay cho `--name`. Thử gọi `help` và `help hello` để xem danh sách lệnh và hướng dẫn của command. Trợ giúp nên là một phần của thiết kế command, không phải tài liệu được viết bổ sung sau cùng.

**Kết quả cần đạt:** ứng dụng khởi động được, command xuất hiện trong trợ giúp, option nhận đúng giá trị và giá trị mặc định hoạt động như dự kiến.

## 3. Thiết kế tham số và quy tắc validation

Khi CLI phát triển, tham số thường gồm chuỗi, số, boolean, ngày tháng, đường dẫn hoặc danh sách giá trị. Spring Shell kết hợp cơ chế chuyển đổi kiểu của Spring để chuyển dữ liệu người dùng nhập thành kiểu Java tương ứng. Hãy khai báo kiểu dữ liệu cụ thể thay vì nhận mọi thứ dưới dạng `String` rồi tự phân tích ở nhiều nơi.

Ví dụ, lệnh thêm công việc có thể nhận tiêu đề và mức ưu tiên:

```java
@ShellComponent
public class TaskCommands {

    private final TaskService taskService;

    public TaskCommands(TaskService taskService) {
        this.taskService = taskService;
    }

    @ShellMethod(key = "task-add", value = "Tạo một công việc mới")
    public String add(
            @ShellOption(value = "--title") String title,
            @ShellOption(value = "--priority", defaultValue = "3") int priority) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("--title không được để trống");
        }
        if (priority < 1 || priority > 5) {
            throw new IllegalArgumentException("--priority phải nằm trong khoảng 1 đến 5");
        }

        Task task = taskService.add(title.trim(), priority);
        return "Đã tạo công việc " + task.getId() + ": " + task.getTitle();
    }
}
```

Ví dụ trên minh họa hai tầng kiểm tra. Spring Shell xử lý việc nhận và chuyển đổi tham số; command kiểm tra những điều kiện gắn với cách gọi CLI; `TaskService` vẫn phải bảo vệ quy tắc nghiệp vụ để những nơi gọi khác cũng không tạo được dữ liệu không hợp lệ. Nếu dự án dùng Jakarta Bean Validation, có thể bổ sung constraint và cấu hình method validation phù hợp, nhưng cần xác minh rằng validation thực sự được kích hoạt trong ứng dụng.

Khi thiết kế option, hãy thống nhất các quy tắc sau:

- Dùng option có tên cho tham số dễ nhầm lẫn hoặc có khả năng mở rộng, chẳng hạn `--from`, `--to` và `--format`.
- Chỉ đặt giá trị mặc định khi giá trị đó an toàn và có ý nghĩa với hầu hết trường hợp.
- Kiểm tra giới hạn số, định dạng ngày, đường dẫn tồn tại và quan hệ giữa nhiều tham số trước khi gọi nghiệp vụ.
- Thông báo lỗi phải chỉ rõ tham số sai và cách sửa. Không buộc người dùng đọc stack trace để hiểu lỗi nhập liệu.
- Không đặt bí mật như mật khẩu hoặc token trực tiếp trong option nếu lịch sử terminal hay danh sách tiến trình có thể làm lộ chúng. Ưu tiên biến môi trường, kho bí mật hoặc đầu vào bảo mật phù hợp.

Với lệnh chỉ dùng được sau khi kết nối hoặc đăng nhập, Spring Shell có cơ chế kiểm soát khả dụng command. Có thể dùng `@ShellMethodAvailability` cùng kết quả `Availability` để đánh dấu lệnh sẵn sàng hay giải thích vì sao lệnh tạm thời chưa thể chạy. Điều kiện này giúp người dùng biết bước cần thực hiện trước khi gọi lệnh.

## 4. Hoàn thiện trợ giúp và tự hoàn thành

Tên command, mô tả và metadata của option tạo nên trải nghiệm trợ giúp. Mô tả nên bắt đầu bằng động từ, nói rõ tác động và tránh lặp lại tên lệnh. Với option, giải thích đơn vị, định dạng, giá trị mặc định và ví dụ khi cách dùng chưa hiển nhiên.

Tự hoàn thành (tab completion) giúp người dùng khám phá cú pháp và giảm lỗi gõ. Spring Shell cho phép cung cấp gợi ý giá trị thông qua `ValueProvider` gắn với option. Ví dụ, option `--project` có thể gợi ý tên những dự án mà người dùng hiện tại được phép truy cập. Nguồn gợi ý nên lấy dữ liệu từ service, phản ánh trạng thái hiện tại và tránh hiển thị tài nguyên người dùng không có quyền xem.

Không nên đưa toàn bộ dữ liệu vào danh sách gợi ý nếu danh sách có thể rất lớn. Hãy giới hạn hoặc lọc theo phần người dùng đã nhập. Với giá trị cố định, dùng danh sách gợi ý ngắn; với dữ liệu thay đổi, dùng provider truy vấn service khi cần.

Kiểm tra trợ giúp và completion cùng với command thực tế. Một option có thể chạy đúng nhưng vẫn khó dùng nếu tên, mô tả hoặc gợi ý không phản ánh hành vi của nó.

## 5. Xây dựng luồng tương tác và chế độ script

Không phải tác vụ nào cũng nên yêu cầu người dùng nhập từng câu trả lời. Hãy dùng prompt khi người dùng cần được hướng dẫn qua các lựa chọn hoặc khi việc chọn sai có thể gây hậu quả đáng kể. Với luồng nhiều bước, Spring Shell có các thành phần tương tác và `ComponentFlow` để tổ chức câu hỏi, lựa chọn, xác nhận và kết quả.

Ví dụ, một luồng xóa dữ liệu có thể yêu cầu chọn phạm vi, hiển thị số bản ghi bị ảnh hưởng rồi hỏi xác nhận. Luồng nên trình bày rõ hành động sắp thực hiện và cho phép người dùng hủy. Với tác vụ thường xuyên được tự động hóa, cung cấp option tường minh để script truyền đủ dữ liệu và không phải chờ prompt.

Một command nên hoạt động theo cùng quy tắc nghiệp vụ trong cả hai cách gọi:

```text
# Trong phiên shell tương tác
task-add --title "Viết tài liệu" --priority 2

# Gọi từ terminal ở chế độ không tương tác đã cấu hình
java -jar task-cli.jar task-add --title "Viết tài liệu" --priority 2
```

Cú pháp khởi chạy không tương tác và script phụ thuộc vào cấu hình cũng như phiên bản Spring Shell. Khi triển khai, hãy xác nhận các thuộc tính bật/tắt chế độ tương ứng trong tài liệu của release đang dùng, sau đó ghi lại chính xác cách chạy trong README. Không giả định rằng một cấu hình script của phiên bản cũ vẫn đúng với phiên bản mới.

Khi thiết kế cho script:

- Không yêu cầu nhập liệu thủ công nếu tất cả giá trị cần thiết đã có trong tham số.
- Tránh prompt vô thời hạn khi standard input không được kết nối với terminal.
- Dùng mã thoát để script phân biệt thành công và thất bại.
- Giữ output ổn định, không trộn lời nhắc, banner hoặc thông báo chẩn đoán vào dữ liệu máy cần đọc.
- Đảm bảo lệnh có thể chạy lại an toàn hoặc mô tả rõ tác động nếu chạy lặp tạo ra dữ liệu trùng.

## 6. Quy ước mã thoát và xử lý lỗi

Một command chạy trong terminal cần cho chương trình gọi nó biết kết quả. Quy ước phổ biến là mã `0` cho thành công và mã khác `0` cho thất bại. Dự án nên thống nhất ý nghĩa các mã còn lại, ví dụ:

| Mã | Ý nghĩa đề xuất | Cách xử lý của script |
| --- | --- | --- |
| `0` | Lệnh hoàn tất | Tiếp tục bước kế tiếp |
| `1` | Lỗi thực thi không dự kiến | Dừng và ghi nhận lỗi |
| `2` | Tham số hoặc cách gọi không hợp lệ | Hiển thị cách dùng và yêu cầu sửa đầu vào |
| `3` | Dịch vụ phụ thuộc không khả dụng | Có thể thử lại theo chính sách của quy trình |

Đây là quy ước của dự án, không phải bộ mã bắt buộc của Spring Shell. Hãy cấu hình cơ chế ánh xạ lỗi sang mã thoát theo API của phiên bản đang dùng và kiểm tra mã thoát ở cấp tiến trình. Không chỉ kiểm tra chuỗi thông báo trên màn hình vì script thường quyết định bước tiếp theo dựa vào exit code.

Phân loại lỗi để phản hồi đúng mức:

- **Lỗi đầu vào:** nêu option hoặc giá trị sai và cách sửa.
- **Lỗi nghiệp vụ:** giải thích vì sao yêu cầu không được chấp nhận, chẳng hạn công việc đã hoàn thành.
- **Lỗi phụ thuộc:** cho biết dịch vụ, cơ sở dữ liệu hoặc tệp cần thiết không truy cập được.
- **Lỗi hệ thống:** ghi log đủ thông tin để điều tra, đồng thời hiển thị thông báo ngắn gọn cho người dùng.

Không bắt mọi exception rồi trả về chuỗi thành công. Nếu lệnh thất bại, trạng thái tiến trình cũng phải thể hiện thất bại. Tránh để lớp command chứa toàn bộ chính sách retry, kết nối hoặc giao dịch; chuyển các thao tác đó vào service để dễ kiểm thử.

## 7. Thiết kế output cho người và chương trình

Output là một phần của hợp đồng CLI. Người dùng tương tác thường cần bảng dễ đọc, trạng thái rõ và thông báo xác nhận. Script cần dữ liệu có cấu trúc, ổn định và không phụ thuộc vào cách căn lề trên terminal.

Chọn định dạng theo mục đích:

| Định dạng | Trường hợp phù hợp | Lưu ý |
| --- | --- | --- |
| Văn bản | Thông báo thành công, hướng dẫn và lỗi | Ngắn, nêu rõ hành động đã xảy ra |
| Bảng | Liệt kê hoặc so sánh dữ liệu trong terminal | Có tiêu đề cột, giới hạn chiều rộng hợp lý |
| JSON | Tích hợp với chương trình khác | Giữ tên field và kiểu dữ liệu ổn định |
| CSV | Trao đổi dữ liệu bảng với công cụ khác | Xử lý dấu phẩy, dấu nháy và ký tự xuống dòng đúng chuẩn |

Với lệnh `task-list`, có thể hỗ trợ `--format table` cho người dùng và `--format json` cho pipeline. Với `task-export`, hãy định nghĩa rõ dữ liệu được ghi ra file hay standard output, cách xử lý file đã tồn tại và mã thoát khi không thể ghi.

Tách dữ liệu kết quả khỏi log chẩn đoán. Nếu output được dùng làm đầu vào cho lệnh khác, log, banner, màu sắc và prompt không được làm hỏng dữ liệu. Đặt tên field nhất quán, sắp xếp kết quả ổn định khi phù hợp và ghi rõ đơn vị của các giá trị. Với output lớn, cân nhắc phân trang hoặc ghi trực tiếp ra file thay vì giữ toàn bộ nội dung trong bộ nhớ.

## 8. Tổ chức mã để dễ mở rộng

Command là lớp tiếp nhận giao tiếp với terminal. Nó nên đọc tham số, kiểm tra điều kiện gắn với cú pháp CLI, gọi service và chuyển kết quả thành output. Nghiệp vụ không nên phụ thuộc vào Spring Shell.

Một cấu trúc đơn giản có thể như sau:

```text
src/main/java/com/example/taskcli/
├── TaskCliApplication.java
├── command/
│   ├── GreetingCommands.java
│   └── TaskCommands.java
├── service/
│   └── TaskService.java
├── domain/
│   └── Task.java
└── config/
    └── ShellConfiguration.java

src/test/java/com/example/taskcli/
├── command/
└── service/
```

Khi dự án còn nhỏ, không cần tạo package cho mọi lớp. Hãy giữ ranh giới dễ hiểu: command phụ thuộc vào service; service xử lý quy tắc nghiệp vụ; domain biểu diễn dữ liệu; cấu hình shell tập trung các thiết lập dùng chung. Cách tổ chức này cho phép thay giao diện CLI hoặc gọi cùng nghiệp vụ từ một API khác mà không phải viết lại logic.

## 9. Kiểm thử từ phương thức đến tiến trình thực

Kiểm thử CLI cần bao phủ cả nghiệp vụ lẫn cách Spring Shell diễn giải command. Chia kiểm thử theo phạm vi để xác định lỗi nhanh.

**Unit test cho service** kiểm tra quy tắc nghiệp vụ mà không cần khởi động shell: tạo công việc, giới hạn mức ưu tiên, chuyển trạng thái, lọc và xuất dữ liệu. Đây là nơi phù hợp để kiểm tra nhiều trường hợp biên.

**Unit test cho command** kiểm tra việc chuyển kết quả service thành thông báo và cách command xử lý đầu vào đã được chuyển đổi. Ví dụ:

```java
class GreetingCommandsTest {

    @Test
    void greetsTheGivenName() {
        GreetingCommands commands = new GreetingCommands();

        assertEquals("Xin chào, Ada!", commands.hello("Ada"));
    }
}
```

Phương thức được gọi trực tiếp trong unit test nên test này không xác minh việc Spring Shell áp dụng giá trị mặc định hay phân tích option. Hãy kiểm tra các hành vi đó trong kiểm thử tích hợp.

**Integration test với Spring Shell** khởi động Spring context và dùng `ShellTestClient` do Spring Shell cung cấp để chạy command trong môi trường gần với ứng dụng thật. Kiểm tra command được đăng ký, option được chuyển đổi, giá trị mặc định được áp dụng, trợ giúp hiển thị đúng, lỗi validation được báo và completion đưa ra gợi ý phù hợp. Cú pháp cụ thể của test client cần theo tài liệu của phiên bản Spring Shell trong dự án.

**End-to-end test** chạy JAR đã đóng gói như một tiến trình con bằng `ProcessBuilder`. Kiểm tra exit code, standard output, standard error, mã hóa tiếng Việt, xử lý đường dẫn có khoảng trắng và hành vi khi thiếu tham số. Đây là cách phát hiện những lỗi chỉ xuất hiện sau khi ứng dụng được đóng gói hoặc khi chạy trong môi trường terminal thật.

Một ma trận kiểm thử tối thiểu nên có:

| Nhóm | Trường hợp cần kiểm tra |
| --- | --- |
| Cú pháp | Lệnh hợp lệ, lệnh không tồn tại, thiếu option bắt buộc |
| Chuyển đổi | Số, boolean, ngày tháng, đường dẫn và giá trị mặc định |
| Validation | Chuỗi rỗng, giá trị ngoài giới hạn, tổ hợp tham số không hợp lệ |
| Trợ giúp | Danh sách command, trợ giúp từng command và mô tả option |
| Completion | Gợi ý tĩnh, gợi ý động và trường hợp không có kết quả |
| Luồng tương tác | Chọn, xác nhận, hủy và xử lý khi không có terminal |
| Script | Chạy nhiều lệnh, lỗi giữa chừng và mã thoát |
| Output | Table, JSON, CSV, Unicode và dữ liệu rỗng |
| Đóng gói | Chạy JAR trên môi trường sạch với cấu hình cần thiết |

Không chỉ kiểm tra rằng command trả về một chuỗi. Hãy kiểm tra tác động lên dữ liệu, trạng thái tiến trình và khả năng tích hợp với chương trình gọi CLI.

## 10. Đóng gói và phân phối

Khi kiểm thử đã đạt, đóng gói ứng dụng thành executable JAR bằng Spring Boot Maven Plugin. Với Maven Wrapper trên macOS/Linux:

```bash
./mvnw clean verify
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd clean verify
```

Sau khi build thành công, chạy JAR được tạo trong thư mục `target`:

```bash
java -jar target/task-cli.jar
```

Tên artifact thực tế phụ thuộc cấu hình Maven của dự án. Hãy dùng đúng tên file được tạo và kiểm tra rằng JAR chứa các dependency cần thiết. Chạy lại những command quan trọng từ JAR để bảo đảm kết quả không chỉ đúng khi chạy trong IDE.

Một gói phân phối nên có:

- Executable JAR và số phiên bản rõ ràng.
- README mô tả yêu cầu JDK, cách cài đặt, cách khởi chạy, command, option và mã thoát.
- Tệp cấu hình mẫu không chứa bí mật.
- Script khởi chạy nếu cần chuẩn hóa tham số JVM, biến môi trường hoặc đường dẫn cấu hình.
- Hướng dẫn nâng cấp và tương thích cấu hình giữa các phiên bản.

Nếu người dùng không muốn tự cài JDK hoặc cần môi trường chạy đồng nhất, có thể phân phối qua container. Nếu thời gian khởi động và dung lượng là yêu cầu quan trọng, có thể đánh giá native image sau khi bản JAR đã hoạt động ổn định; khi đó cần kiểm tra thêm khả năng tương thích của thư viện, reflection, resource và cấu hình build native. Đây là lựa chọn triển khai bổ sung, không phải điều kiện để hoàn thành một CLI Spring Shell thông thường.

Trước khi phát hành, thử cài và chạy gói trên một môi trường sạch tương tự máy người dùng. Xác nhận cấu hình, quyền truy cập file, encoding, log, mã thoát và cách hiển thị trợ giúp. Ghi lại phiên bản ứng dụng và cách báo lỗi để người dùng có thể cung cấp thông tin hữu ích khi cần hỗ trợ.

## 11. Bài thực hành tổng hợp

Hãy hoàn thiện một CLI quản lý công việc với các yêu cầu sau:

1. Tạo command `task-add` nhận `--title` và `--priority`; tiêu đề không được rỗng, mức ưu tiên nằm trong khoảng 1 đến 5.
2. Tạo command `task-list` hỗ trợ lọc theo `--status` và giới hạn số dòng bằng `--limit`.
3. Tạo command `task-done` nhận `--id`; nếu không tìm thấy công việc, trả thông báo rõ ràng và mã thoát thất bại.
4. Bổ sung trợ giúp và completion cho trạng thái công việc hoặc tên dự án.
5. Tạo luồng xác nhận trước một thao tác xóa hàng loạt; cung cấp cách truyền tham số đầy đủ để script không phải trả lời prompt.
6. Cho phép `task-list` xuất bảng cho người dùng và JSON cho chương trình khác.
7. Viết unit test cho service, integration test cho command và end-to-end test chạy JAR.
8. Đóng gói, viết README và thử chạy trên một môi trường sạch.

Khi hoàn thành, bạn cần giải thích được mỗi command nhận dữ liệu thế nào, lỗi được chuyển thành thông báo và mã thoát ra sao, output nào dành cho người dùng hay script, test nào bảo vệ từng hành vi và người dùng cài đặt gói phát hành như thế nào.

## 12. Tự đánh giá lộ trình

| Chặng | Tiêu chí hoàn thành |
| --- | --- |
| Command đầu tiên | Command được đăng ký và gọi được từ shell |
| Tham số | Option, kiểu dữ liệu và giá trị mặc định hoạt động đúng |
| Validation | Đầu vào sai bị từ chối với thông báo có ích |
| Trợ giúp và completion | Người dùng khám phá được cú pháp và giá trị hợp lệ |
| Tương tác và script | Cùng nghiệp vụ chạy được trong cả hai cách sử dụng |
| Mã thoát và output | Script nhận biết kết quả; dữ liệu đầu ra có định dạng ổn định |
| Kiểm thử | Unit, integration và end-to-end test bao phủ hành vi chính |
| Phân phối | JAR cài đặt và chạy được trong môi trường sạch |

Hãy hoàn thành từng chặng trước khi tăng độ phức tạp. Khi một command có hợp đồng rõ ràng, lỗi dễ hiểu, output ổn định và test chạy được từ JAR, bạn đã có nền tảng để phát triển CLI thành công cụ đáng tin cậy cho người dùng và quy trình tự động hóa.
