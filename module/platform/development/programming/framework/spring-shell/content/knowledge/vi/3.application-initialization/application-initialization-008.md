# Chạy từ IDE so với chạy bằng terminal thực

Một ứng dụng Spring Shell có thể khởi chạy từ IDE trong lúc phát triển hoặc chạy như một tiến trình Java độc lập từ terminal. Cả hai cách đều có thể dùng cùng mã nguồn và cùng Spring Application Context, nhưng môi trường khởi chạy có nhiều điểm khác nhau: classpath, thư mục làm việc, biến môi trường, tham số, luồng nhập xuất và khả năng của terminal. Vì vậy, một command chạy đúng trong cửa sổ Run của IDE chưa chắc đã hoạt động giống hệt khi người dùng chạy JAR trên máy của họ.

Mục tiêu của bài học là hiểu những khác biệt đó, thiết lập hai cách chạy có thể tái lập và xác minh ứng dụng bằng chính gói sẽ được phân phối. Đây là bước quan trọng khi xây dựng CLI bằng Spring Shell: ứng dụng cần phục vụ cả người phát triển đang debug lẫn người dùng chạy lệnh trong terminal và script.

## 1. Hai cách chạy sử dụng cùng điểm vào ứng dụng

Một ứng dụng Spring Shell thường được khởi động như ứng dụng Spring Boot. Lớp chính có thể có dạng:

```java
@SpringBootApplication
public class TaskCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskCliApplication.class, args);
    }
}
```

Spring Boot tạo application context, nạp cấu hình và khởi tạo các bean. Spring Shell phát hiện những lớp command, chẳng hạn lớp được đánh dấu `@ShellComponent`, rồi đăng ký các phương thức `@ShellMethod` để người dùng gọi.

Khi chạy từ IDE, IDE gọi phương thức `main` bằng cấu hình Run/Debug. IDE thường chuẩn bị classpath từ module và các dependency trong dự án, sau đó hiển thị luồng output trong cửa sổ console tích hợp.

Khi chạy từ terminal, người dùng hoặc script khởi động ứng dụng bằng Maven/Gradle trong lúc phát triển, hoặc chạy executable JAR sau khi đóng gói. Ví dụ với Maven Wrapper:

```bash
# Chạy ứng dụng từ dự án trong lúc phát triển
./mvnw spring-boot:run

# Đóng gói ứng dụng
./mvnw clean package

# Chạy executable JAR sau khi đóng gói
java -jar target/task-cli-0.0.1-SNAPSHOT.jar
```

Trên Windows PowerShell, Maven Wrapper thường được gọi bằng `.\mvnw.cmd`:

```powershell
.\mvnw.cmd spring-boot:run
.\mvnw.cmd clean package
java -jar target\task-cli-0.0.1-SNAPSHOT.jar
```

Tên JAR phụ thuộc `artifactId`, `version` và cấu hình build của dự án. Hãy dùng tên artifact thực tế được tạo trong thư mục `target` hoặc `build/libs`. Chạy `java -jar` chỉ hoạt động khi dự án đã được cấu hình đóng gói thành executable Spring Boot JAR.

Điểm quan trọng là hai cách chạy cần khởi tạo cùng ứng dụng và cùng bộ command. Khác biệt nằm ở môi trường tiến trình và cách người dùng tương tác. Nếu IDE đang chạy một cấu hình khác profile, tham số hoặc classpath, kết quả sẽ không còn là phép so sánh công bằng.

## 2. Cấu hình Run/Debug trong IDE

Tạo một cấu hình chạy riêng cho ứng dụng CLI. Tùy IDE, tên trường có thể khác nhau, nhưng thường cần xác định các thông tin sau:

| Thiết lập | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Main class | Lớp chứa `main` | `com.example.taskcli.TaskCliApplication` |
| Use classpath of module | Module cung cấp class và dependency | `task-cli` |
| Working directory | Thư mục hiện hành của tiến trình | Thư mục gốc dự án |
| Program arguments | Tham số truyền cho ứng dụng | `--spring.profiles.active=dev` hoặc tham số command theo cách chạy đã cấu hình |
| VM options | Tham số cho JVM | `-Dfile.encoding=UTF-8`, `-Xmx512m` |
| Environment variables | Biến môi trường | `SPRING_PROFILES_ACTIVE=dev` |

Phân biệt **Program arguments** với **VM options**. Program arguments được truyền vào `main(String[] args)` và có thể được Spring Boot hoặc Spring Shell xử lý. VM options được JVM đọc trước khi ứng dụng khởi động, ví dụ `-Duser.timezone=UTC`. Đặt nhầm một thuộc tính JVM vào Program arguments hoặc ngược lại có thể khiến cấu hình không có tác dụng như mong muốn.

Working directory ảnh hưởng đến mọi đường dẫn tương đối. Ví dụ, nếu ứng dụng đọc `config/task-cli.yml`, đường dẫn này được giải quyết dựa trên thư mục làm việc của tiến trình, không nhất thiết dựa trên vị trí file Java hoặc vị trí JAR. Đặt working directory rõ ràng trong IDE và ghi lại quy ước này trong hướng dẫn chạy.

Khi debug, đặt breakpoint trong command và service, chạy command cần kiểm tra rồi quan sát tham số, kết quả và exception. Có thể dùng console của IDE để nhập lệnh, nhưng cần nhớ rằng cửa sổ Run/Debug không phải lúc nào cũng cung cấp đầy đủ hành vi của một terminal tương tác.

## 3. Cấu hình môi trường khi chạy từ terminal

Terminal khởi chạy tiến trình với môi trường kế thừa từ shell hiện tại. Các giá trị có thể khác IDE gồm biến môi trường, thư mục làm việc, PATH, Java được chọn, locale, timezone và quyền truy cập file.

Ví dụ, đặt Spring profile trước khi chạy ứng dụng.

Trên macOS/Linux:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar target/task-cli.jar
```

Trên Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar target\task-cli.jar
```

Có thể truyền system property trực tiếp cho JVM. Các tùy chọn JVM phải đặt trước `-jar`:

```bash
java -Dfile.encoding=UTF-8 -Duser.timezone=UTC -jar target/task-cli.jar
```

Các tham số cấu hình ứng dụng của Spring Boot, như `--spring.profiles.active=dev`, là application arguments và được đặt sau tên JAR:

```bash
java -jar target/task-cli.jar --spring.profiles.active=dev
```

Spring Shell cũng có thể nhận tham số để thực thi command không tương tác. Cách phân tách tham số cấu hình Spring Boot với tên command và option của Spring Shell, cùng các thuộc tính bật/tắt interactive mode hoặc non-interactive mode, phụ thuộc phiên bản Spring Shell. Hãy dùng đúng cú pháp được tài liệu của phiên bản trong dự án quy định và kiểm tra nó bằng một tiến trình JAR thực tế. Không sao chép nguyên cấu hình command-line từ một phiên bản khác mà chưa xác minh.

Không lưu mật khẩu, access token hoặc khóa riêng trong cấu hình Run/Debug được commit vào repository hay trong lịch sử terminal. Dùng cơ chế cấp bí mật của môi trường, biến môi trường được quản lý an toàn hoặc secret store phù hợp. Tệp cấu hình mẫu chỉ nên chứa giá trị giả và tên biến cần thiết.

## 4. Working directory, classpath và tài nguyên

Một nguyên nhân phổ biến khiến ứng dụng chạy được trong IDE nhưng lỗi từ terminal là hai môi trường đang tìm tài nguyên ở vị trí khác nhau.

**Classpath trong IDE** thường bao gồm thư mục class đã biên dịch, tài nguyên trong `src/main/resources` và các dependency của module. Khi chạy JAR, Spring Boot đóng gói class và tài nguyên vào cấu trúc archive riêng. Không nên đọc file cấu hình đóng gói bằng cách giả định rằng mọi tài nguyên classpath đều là một `File` vật lý. Với tài nguyên chỉ đọc, dùng `ClassPathResource` hoặc cơ chế resource của Spring; với file người dùng cần chỉnh sửa, dùng một đường dẫn bên ngoài JAR được cấu hình rõ ràng.

Ví dụ đọc tài nguyên classpath thông qua Spring:

```java
@Component
public class BannerLoader {

    private final Resource banner;

    public BannerLoader(ResourceLoader resourceLoader) {
        this.banner = resourceLoader.getResource("classpath:banner.txt");
    }

    public String load() throws IOException {
        try (InputStream input = banner.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

Với file do người dùng cung cấp, hãy cho phép truyền đường dẫn hoặc cấu hình thư mục dữ liệu. Chuẩn hóa và kiểm tra đường dẫn trước khi đọc/ghi, xử lý trường hợp file không tồn tại và thông báo quyền truy cập cần thiết.

Để so sánh công bằng, chạy IDE với working directory tương ứng thư mục mà người dùng sẽ dùng khi khởi chạy terminal, hoặc làm cho ứng dụng không phụ thuộc vào một thư mục cụ thể. Kiểm tra ít nhất các trường hợp: chạy từ thư mục gốc dự án, chạy từ thư mục khác và chạy JAR bằng đường dẫn tuyệt đối.

## 5. Console của IDE và terminal thực khác nhau thế nào?

Cửa sổ console trong IDE chủ yếu hiển thị output và chuyển input đến tiến trình. Terminal thực còn cung cấp một thiết bị đầu cuối (TTY hoặc pseudo-terminal) với các khả năng như điều khiển con trỏ, xử lý phím, thay đổi kích thước cửa sổ, màu ANSI, chế độ nhập liệu và tín hiệu của hệ điều hành.

| Khía cạnh | Console của IDE | Terminal thực |
| --- | --- | --- |
| Nhập lệnh | Có thể nhập văn bản qua cửa sổ Run | Có line editing, phím tắt và lịch sử của terminal/shell |
| Tab completion | Có thể không truyền đầy đủ phím Tab hoặc phím điều khiển | Có thể dùng completion của Spring Shell/JLine khi terminal được nhận diện đúng |
| Màu và điều khiển con trỏ | Tùy cách IDE mô phỏng console | Hỗ trợ theo terminal emulator và cấu hình màu |
| Kích thước màn hình | Có thể không phản ánh terminal width thật | Có số cột, số dòng và sự kiện resize |
| Input/output | IDE thu nhận và hiển thị stream | Có thể kết nối TTY, pipe hoặc chuyển hướng sang file |
| Ngắt tiến trình | Nút Stop của IDE | Ctrl+C hoặc cơ chế quản lý tiến trình của hệ điều hành |

Spring Shell sử dụng hạ tầng terminal, trong đó JLine đảm nhiệm nhiều chức năng tương tác. Khi terminal được nhận diện là TTY, người dùng có thể có trải nghiệm nhập lệnh, completion, màu và điều khiển dòng tốt hơn. Nếu input hoặc output được chuyển hướng, hoặc IDE chỉ cung cấp console đơn giản, một số tính năng tương tác có thể bị giới hạn hoặc tắt.

Đừng dùng riêng `System.console() != null` để kết luận toàn bộ ứng dụng có thể chạy tương tác hay không. IDE, terminal emulator và pipe có cách cung cấp console khác nhau; hãy kiểm tra hành vi thực tế của Spring Shell/JLine trong môi trường mục tiêu. Với lệnh cần chạy trong script, thiết kế sao cho có thể nhận đủ tham số và không chờ người dùng nhấn phím.

## 6. Standard input, output, error và mã thoát

Một tiến trình dòng lệnh giao tiếp qua ba luồng chuẩn:

- **stdin:** dữ liệu đầu vào, có thể là bàn phím hoặc dữ liệu được pipe từ tiến trình khác.
- **stdout:** kết quả chính của command, có thể hiển thị trên terminal hoặc chuyển tiếp cho chương trình khác.
- **stderr:** thông báo lỗi và chẩn đoán.

Trong cửa sổ Run của IDE, các luồng này thường được gom vào một vùng console để tiện quan sát. Trong terminal, người dùng có thể tách hoặc chuyển hướng chúng:

```bash
java -jar target/task-cli.jar > task-output.txt 2> task-error.txt
```

Nếu command xuất JSON hoặc CSV cho pipeline, không ghi banner, prompt, log hoặc thông báo debug vào stdout vì chúng sẽ làm dữ liệu đầu ra không còn hợp lệ. Gửi chẩn đoán vào logger/stderr theo cấu hình phù hợp. Nếu shell đang ở chế độ tương tác, có thể trình bày thông báo cho người dùng; còn chế độ script cần output có hợp đồng ổn định.

Mã thoát là tín hiệu để shell hoặc script biết tiến trình hoàn thành thành công hay thất bại. Thông thường `0` biểu thị thành công và giá trị khác `0` biểu thị lỗi. Kiểm tra mã thoát ngay sau khi tiến trình kết thúc.

Trong PowerShell:

```powershell
java -jar target\task-cli.jar
$LASTEXITCODE
```

Trong Bash:

```bash
java -jar target/task-cli.jar
echo $?
```

IDE có thể hiển thị process exit code trong cửa sổ Run, nhưng không phải lúc nào cũng thể hiện cách script bên ngoài sẽ nhận stdout, stderr và mã thoát. Vì vậy, hãy kiểm tra tiến trình từ terminal thực trước khi phát hành.

## 7. Encoding, locale và các khác biệt hệ điều hành

CLI thường hiển thị tiếng Việt, đọc file và xử lý tên đường dẫn. Kết quả có thể khác nhau giữa IDE và terminal do encoding, font, locale, timezone hoặc cách shell xử lý dấu nháy.

Các nguyên tắc nên áp dụng:

- Đọc và ghi tệp văn bản với UTF-8 được chỉ định rõ trong API, ví dụ `StandardCharsets.UTF_8`.
- Kiểm tra font terminal có hỗ trợ ký tự tiếng Việt và cấu hình encoding của terminal.
- Không giả định dấu phân cách đường dẫn luôn là `/`; dùng `Path` và `Paths` của Java.
- Đặt timezone rõ ràng khi dữ liệu hoặc báo cáo phụ thuộc thời gian; tránh dựa vào timezone ngầm của máy phát triển.
- Trích dẫn chuỗi có dấu cách đúng cú pháp của shell đang dùng. Bash, PowerShell và Command Prompt có quy tắc quoting khác nhau.
- Kiểm tra quyền đọc/ghi, đường dẫn có khoảng trắng, tên file Unicode và sự khác nhau giữa chữ hoa/chữ thường trên hệ thống file.

Ví dụ xây dựng đường dẫn theo cách độc lập hệ điều hành:

```java
Path output = Paths.get("data", "exports", "tasks.csv");
Files.createDirectories(output.getParent());
Files.writeString(output, csvContent, StandardCharsets.UTF_8);
```

Ví dụ này vẫn dùng đường dẫn tương đối theo working directory hiện tại. Nếu ứng dụng cần một thư mục dữ liệu ổn định, hãy nhận thư mục đó từ cấu hình và hiển thị đường dẫn thực tế khi có lỗi.

## 8. Chọn cách chạy phù hợp với từng giai đoạn

| Công việc | Nên chạy từ IDE | Nên chạy từ terminal/JAR |
| --- | --- | --- |
| Đặt breakpoint, xem biến và call stack | Có | Không thuận tiện bằng |
| Thử nhanh một command khi sửa code | Có | Có thể dùng Maven/Gradle |
| Kiểm tra tab completion, màu và TTY | Chỉ kiểm tra sơ bộ | Có |
| Kiểm tra biến môi trường và working directory như máy người dùng | Có thể cấu hình mô phỏng | Có |
| Kiểm tra executable JAR | Không thay thế được | Có |
| Kiểm tra redirect, pipe và exit code trong script | Hạn chế | Có |
| Xác nhận gói phân phối | Không | Có |

Trong giai đoạn phát triển, IDE giúp rút ngắn vòng lặp sửa code và debug. Trước khi phát hành, terminal thực giúp xác minh cách ứng dụng hoạt động như một tiến trình độc lập. Hai cách chạy bổ trợ nhau: IDE phù hợp để tìm nguyên nhân lỗi, còn JAR chạy trong môi trường gần với người dùng giúp kiểm tra tính sẵn sàng phân phối.

## 9. Quy trình xác minh từ IDE đến JAR

Thực hiện quy trình sau mỗi khi thay đổi cách khởi chạy, cấu hình hoặc xử lý input/output:

1. **Chạy từ IDE:** dùng đúng main class, profile, biến môi trường và working directory đã ghi trong cấu hình Run. Gọi `help`, một command đọc dữ liệu và một command có tham số.
2. **Chạy từ Maven/Gradle:** khởi động ứng dụng từ terminal của dự án để phát hiện khác biệt giữa IDE và công cụ build.
3. **Đóng gói:** chạy `clean package` hoặc tác vụ build tương ứng, xác nhận build thành công và xác định chính xác đường dẫn artifact.
4. **Chạy JAR:** mở một terminal mới, chuyển đến thư mục dự kiến, chạy JAR và thử các command cốt lõi.
5. **Thử môi trường khác:** chạy từ một working directory khác, đặt profile bằng biến môi trường và kiểm tra file cấu hình bên ngoài.
6. **Thử terminal và script:** kiểm tra completion, Unicode, redirect stdout/stderr, input không tương tác và mã thoát.
7. **Ghi lại cách chạy:** cập nhật README với phiên bản Java, lệnh khởi chạy, biến môi trường, thư mục dữ liệu, ví dụ command và cách diễn giải lỗi.

Một bảng kiểm tra có thể dùng để ghi nhận kết quả:

| Hạng mục | IDE | Terminal/JAR |
| --- | --- | --- |
| Ứng dụng khởi động và đóng đúng | ☐ | ☐ |
| Command xuất hiện trong `help` | ☐ | ☐ |
| Option bắt buộc và giá trị mặc định đúng | ☐ | ☐ |
| Profile và cấu hình được nạp đúng | ☐ | ☐ |
| Đọc/ghi tài nguyên đúng vị trí | ☐ | ☐ |
| Tiếng Việt hiển thị đúng | ☐ | ☐ |
| Lỗi đi vào luồng chẩn đoán phù hợp | ☐ | ☐ |
| Exit code phản ánh thành công/thất bại | ☐ | ☐ |
| Chạy không tương tác không chờ bàn phím | ☐ | ☐ |

Không cần mọi tính năng đều được kiểm tra bằng cùng một cơ chế. Ví dụ, debug breakpoint chỉ cần IDE; còn redirect và exit code cần được xác minh từ một tiến trình terminal.

## 10. Các lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| IDE chạy được nhưng JAR báo thiếu class | Dependency không được đóng gói hoặc chạy nhầm artifact | Kiểm tra executable JAR và cấu hình Spring Boot Maven/Gradle plugin |
| Không tìm thấy file cấu hình | Working directory hoặc đường dẫn tương đối khác nhau | In working directory, kiểm tra đường dẫn tuyệt đối và vị trí file |
| Profile khác giữa hai môi trường | IDE có biến môi trường/VM option riêng | Kiểm tra `SPRING_PROFILES_ACTIVE`, application arguments và system properties |
| Tab completion không hoạt động trong IDE | Console không chuyển phím Tab hoặc không có TTY đầy đủ | Thử terminal emulator thực và kiểm tra khả năng terminal được nhận diện |
| Tiếng Việt bị lỗi ký tự | Encoding hoặc font không tương thích | Kiểm tra UTF-8 khi đọc/ghi và cấu hình terminal |
| Command chờ nhập mãi trong script | Command hoặc chế độ chạy đang yêu cầu prompt | Cung cấp đủ option, kiểm tra interactive mode và stdin |
| Script nhận dữ liệu JSON bị lỗi | Banner, log hoặc prompt trộn vào stdout | Tách output dữ liệu khỏi stderr/log |
| IDE báo thành công nhưng script coi là thất bại | Process exit code không được ánh xạ như mong đợi | Chạy JAR trực tiếp và kiểm tra `$LASTEXITCODE` hoặc `$?` |

Khi điều tra, hãy ghi nhận lệnh khởi chạy đầy đủ, phiên bản Java, profile, working directory và biến môi trường liên quan. Không đưa bí mật vào log hoặc báo cáo lỗi. So sánh hai môi trường theo từng yếu tố sẽ giúp khoanh vùng nguyên nhân nhanh hơn.

## 11. Bài thực hành

Tạo một Spring Shell CLI có command `task-list` và `task-add`, sau đó xác minh ứng dụng qua hai cách chạy.

1. Cấu hình Run/Debug trong IDE với main class, working directory và profile `dev`.
2. Chạy ứng dụng từ IDE, dùng `help`, thêm một công việc và liệt kê dữ liệu.
3. Đóng gói executable JAR bằng Maven hoặc Gradle.
4. Mở terminal tại thư mục dự án và chạy JAR với cùng profile. Xác minh dữ liệu cấu hình và hành vi command.
5. Chạy lại JAR từ một thư mục khác. Nếu ứng dụng đọc/ghi file, xác nhận đường dẫn được giải quyết đúng theo thiết kế.
6. Chuyển output vào file và kiểm tra nội dung, đồng thời kiểm tra mã thoát của tiến trình.
7. Thử một đầu vào không hợp lệ và xác nhận lỗi được báo rõ, tiến trình trả mã thất bại theo quy ước dự án.
8. Ghi các lệnh chạy và biến môi trường cần thiết vào README để một người khác có thể lặp lại.

Sau bài thực hành, bạn cần giải thích được vì sao console IDE có thể khác TTY, Program arguments khác VM options như thế nào, working directory ảnh hưởng ra sao, và vì sao phải chạy artifact đã đóng gói trước khi phân phối.

## 12. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Chạy từ IDE | Cấu hình Run/Debug rõ ràng và có thể tái lập |
| Chạy từ terminal | Khởi động được ứng dụng từ Maven/Gradle và executable JAR |
| Cấu hình | Phân biệt đúng application arguments, VM options và environment variables |
| Tài nguyên | Không phụ thuộc ngầm vào working directory hoặc classpath của IDE |
| Tương tác | Hiểu giới hạn console IDE và xác minh terminal thực |
| Tự động hóa | stdout, stderr, stdin và exit code có hành vi rõ ràng |
| Phân phối | README đủ để người khác chạy artifact trong môi trường sạch |

Khi các tiêu chí này đạt, bạn có thể dùng IDE để phát triển và debug, đồng thời tự tin rằng ứng dụng Spring Shell sẽ hoạt động đúng khi được khởi chạy như một công cụ dòng lệnh độc lập.
