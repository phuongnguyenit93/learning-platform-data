# Đối số dòng lệnh, biến môi trường và mã thoát

## 1. Ba kênh giao tiếp giữa chương trình và môi trường chạy

Một chương trình Java dòng lệnh thường nhận dữ liệu từ ba nguồn: đối số được truyền khi khởi chạy, biến môi trường do hệ điều hành hoặc nền tảng triển khai cung cấp, và mã thoát được trả về khi tiến trình kết thúc. Ba cơ chế này có vai trò khác nhau:

- **Đối số dòng lệnh** mô tả yêu cầu cụ thể của lần chạy, chẳng hạn định dạng xuất, tệp đầu vào hoặc chế độ thực thi.
- **Biến môi trường** cung cấp cấu hình gắn với môi trường chạy, chẳng hạn thư mục đầu ra, địa chỉ dịch vụ hoặc tên môi trường.
- **Mã thoát** cho biết tiến trình hoàn thành thành công hay thất bại để shell, script, CI/CD hoặc tiến trình cha xử lý tiếp.

Luồng dữ liệu tổng quát:

~~~mermaid
flowchart TD
    A[Shell, scheduler hoac process cha] -->|Arguments| B[Java launcher]
    A -->|Environment| C[Environment cua process]
    B --> D[main(String[] args)]
    C --> E[System.getenv]
    D --> F[Ung dung kiem tra va thuc thi]
    E --> F
    F -->|System.exit status hoac ket thuc main| G[Exit status]
    G --> H[Shell, CI/CD hoac process cha]
~~~

Java cung cấp API để đọc những dữ liệu này. Quy ước đặt tên biến môi trường, định dạng đối số và ý nghĩa từng mã thoát là hợp đồng do ứng dụng thiết kế; chúng cần được ghi rõ để người dùng và công cụ tự động gọi chương trình nhất quán.

## 2. Nhận và đọc đối số dòng lệnh

Với dạng điểm bắt đầu truyền thống, Java launcher gọi phương thức:

~~~java
public static void main(String[] args)
~~~

Mỗi phần tử trong mảng **args** là một đối số mà shell chuyển cho chương trình. Mảng rỗng có nghĩa là người dùng không truyền đối số ứng dụng. Các đối số luôn là chuỗi; nếu cần số, boolean, ngày hoặc đường dẫn, ứng dụng phải phân tích và kiểm tra giá trị trước khi sử dụng.

Ví dụ:

~~~java
public class Greeting {
    public static void main(String[] args) {
        if (args.length == 0) {
            System.out.println("Xin chao!");
            return;
        }

        String name = args[0];
        System.out.println("Xin chao, " + name + "!");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -d out Greeting.java
java -cp out Greeting "Nguyen An"
~~~

Trong ví dụ này, shell xử lý dấu ngoặc kép và truyền một đối số chứa khoảng trắng vào Java. Dấu ngoặc kép thường không xuất hiện trong giá trị của **args**. Cách viết để nhóm đối số có khoảng trắng có thể khác giữa Bash, PowerShell và các shell khác; hãy kiểm tra cú pháp của shell đang dùng.

Đối số của Java launcher và đối số của ứng dụng nằm ở hai vị trí khác nhau. Các tùy chọn JVM như **-Xmx** hoặc thuộc tính hệ thống **-Dapp.mode=production** được đặt trước tên lớp hoặc tùy chọn **-jar**. Những gì đứng sau tên lớp chính hoặc tên JAR được chuyển cho ứng dụng.

~~~bash
java -Dapp.mode=production -jar report-cli.jar --format csv
~~~

Ở đây **app.mode** được đọc bằng **System.getProperty("app.mode")**; mảng **args** của ứng dụng nhận hai phần tử **--format** và **csv**. Thuộc tính hệ thống và biến môi trường là hai cơ chế riêng biệt.

## 3. Phân tích và xác thực đối số

Không nên truy cập **args[0]**, **args[1]** trước khi kiểm tra độ dài mảng. Tương tự, không nên chuyển một chuỗi sang số hoặc đường dẫn rồi sử dụng ngay mà chưa xử lý trường hợp dữ liệu không hợp lệ.

Với một CLI nhỏ, có thể kiểm tra số lượng đối số và tên tùy chọn trực tiếp:

~~~java
if (args.length != 2 || !"--format".equals(args[0])) {
    System.err.println("Usage: report-cli --format <csv|json>");
    return;
}

String format = args[1].toLowerCase(java.util.Locale.ROOT);
if (!java.util.Set.of("csv", "json").contains(format)) {
    System.err.println("Format must be csv or json");
    return;
}
~~~

Đối với giá trị số, dùng phương thức phân tích phù hợp và bắt lỗi định dạng:

~~~java
int limit;
try {
    limit = Integer.parseInt(rawLimit);
} catch (NumberFormatException exception) {
    System.err.println("Limit must be an integer");
    return;
}

if (limit < 1 || limit > 10_000) {
    System.err.println("Limit must be between 1 and 10000");
    return;
}
~~~

Ứng dụng nên kiểm tra cả cú pháp lẫn ý nghĩa: tùy chọn bắt buộc có được truyền hay chưa, hai tùy chọn có xung đột không, giá trị có nằm trong phạm vi cho phép không và đường dẫn có thể truy cập hay không. Thông báo lỗi nên nêu cách sử dụng ngắn gọn, tránh in stack trace cho lỗi nhập liệu thông thường.

Khi CLI có nhiều tùy chọn, kiểu dữ liệu, subcommand, help và completion, hãy cân nhắc một thư viện phân tích command line đang được duy trì. Dù dùng thư viện nào, hợp đồng đối số vẫn cần được tài liệu hóa và kiểm thử.

## 4. Đọc biến môi trường trong Java

Biến môi trường được tiến trình nhận từ môi trường khởi chạy. Java đọc một biến theo tên bằng **System.getenv(String)**:

~~~java
String outputDirectory = System.getenv("REPORT_OUTPUT_DIR");

if (outputDirectory == null || outputDirectory.isBlank()) {
    System.err.println("REPORT_OUTPUT_DIR is required");
    return;
}
~~~

Nếu biến không tồn tại, phương thức trả về **null**. Nếu biến tồn tại nhưng giá trị rỗng hoặc chỉ có khoảng trắng, ứng dụng cần quyết định đó có phải cấu hình hợp lệ hay không. Không nên giả định rằng biến môi trường luôn có giá trị.

Có thể lấy toàn bộ tập biến môi trường qua **System.getenv()**:

~~~java
Map<String, String> environment = System.getenv();
String region = environment.get("APP_REGION");
~~~

Map trả về dùng để đọc và không cho phép ứng dụng thay đổi môi trường của chính tiến trình. Việc thay đổi biến môi trường của tiến trình đang chạy không được hỗ trợ bằng API Java tiêu chuẩn. Hãy truyền cấu hình cần thiết vào thành phần ứng dụng qua tham số hoặc một đối tượng cấu hình để dễ kiểm thử.

Tên biến môi trường thường được viết hoa và dùng dấu gạch dưới, ví dụ **APP_REGION**, **REPORT_OUTPUT_DIR**. Đây là quy ước phổ biến, không phải cú pháp bắt buộc của Java. Tính phân biệt chữ hoa chữ thường của tên biến phụ thuộc hệ điều hành; vì vậy nên chọn một cách viết thống nhất và dùng đúng tên đó trong tài liệu triển khai.

## 5. Phân biệt biến môi trường với system properties

Biến môi trường thuộc về môi trường tiến trình và thường được nền tảng triển khai cấp cho ứng dụng. System property là thuộc tính JVM, thường được đặt qua tùy chọn **-D** hoặc trong mã Java.

| Nhu cầu | Cơ chế | Cách đọc |
|---|---|---|
| Cấu hình do hệ điều hành/container cung cấp | Environment variable | **System.getenv("APP_REGION")** |
| Cấu hình riêng của lần chạy JVM | System property | **System.getProperty("app.mode")** |
| Đối số của lần gọi chương trình | Command-line argument | **args[index]** |

Ví dụ chạy với cả system property và biến môi trường:

~~~bash
APP_REGION=ap-southeast-1 java -Dapp.mode=production -jar report-cli.jar --format csv
~~~

Cú pháp gán biến môi trường ở ví dụ trên dành cho shell kiểu POSIX. Trong PowerShell, có thể thiết lập biến trước khi chạy:

~~~powershell
$env:APP_REGION = "ap-southeast-1"
java -Dapp.mode=production -jar report-cli.jar --format csv
~~~

Không nên nhầm **System.getProperty("APP_REGION")** với **System.getenv("APP_REGION")**. Hai lời gọi đọc hai không gian cấu hình khác nhau; việc đặt một biến môi trường không tự động tạo system property cùng tên.

Một chính sách cấu hình thường dùng là ưu tiên theo thứ tự: đối số dòng lệnh, biến môi trường, tệp cấu hình và giá trị mặc định. Đây là quy ước thiết kế của ứng dụng, không phải thứ tự ưu tiên do Java tự áp dụng. Hãy công bố thứ tự này và xử lý rõ trường hợp giá trị bị thiếu hoặc không hợp lệ.

## 6. Quản lý cấu hình nhạy cảm

Không nên ghi mật khẩu, access token, khóa riêng hoặc thông tin xác thực vào mã nguồn, tệp cấu hình được commit hay log. Đối số dòng lệnh có thể xuất hiện trong lịch sử shell, thông tin tiến trình hoặc hệ thống ghi nhận lệnh, vì vậy không nên dùng đối số làm kênh mặc định để truyền bí mật.

Biến môi trường thuận tiện để truyền cấu hình từ container, CI/CD hoặc nền tảng triển khai, nhưng cũng có thể bị lộ qua công cụ chẩn đoán, quyền truy cập tiến trình hoặc cấu hình log sai. Với bí mật có giá trị cao, ưu tiên secret manager hoặc cơ chế cấp phát bí mật của nền tảng; chỉ đưa giá trị vào tiến trình theo thời gian và phạm vi cần thiết.

Một số nguyên tắc thực tế:

- Không in toàn bộ kết quả của **System.getenv()** để debug.
- Không ghi giá trị token, mật khẩu hoặc header xác thực vào log.
- Kiểm tra sự tồn tại và định dạng của cấu hình khi ứng dụng khởi động.
- Giới hạn quyền đọc cấu hình và bí mật theo nguyên tắc tối thiểu.
- Tách cấu hình môi trường khỏi artifact để cùng một bản build có thể triển khai ở nhiều môi trường.

## 7. Truyền biến môi trường cho tiến trình con

Khi Java khởi chạy một chương trình khác bằng **ProcessBuilder**, ứng dụng có thể thiết lập môi trường riêng cho tiến trình con thông qua **ProcessBuilder.environment()**. Map này có thể sửa đổi và các thay đổi được áp dụng cho tiến trình được tạo ra, không làm thay đổi môi trường của JVM hiện tại.

~~~java
ProcessBuilder builder = new ProcessBuilder("java", "-jar", "worker.jar");
builder.environment().put("APP_REGION", "ap-southeast-1");

Process child = builder.start();
int childExitCode = child.waitFor();
~~~

**waitFor()** chờ tiến trình con kết thúc và trả về mã thoát của nó. Vì phương thức có thể ném **InterruptedException**, mã gọi cần xử lý interruption đúng cách, thường là khôi phục trạng thái interrupt trước khi kết thúc tác vụ hoặc chuyển lỗi lên tầng quản lý.

~~~java
try {
    int childExitCode = child.waitFor();
    if (childExitCode != 0) {
        System.err.println("Worker failed with exit code " + childExitCode);
    }
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while waiting for worker", exception);
}
~~~

Dùng danh sách đối số của **ProcessBuilder** để truyền từng tham số. Tránh ghép dữ liệu không tin cậy thành một chuỗi lệnh shell; cách đó có thể gây lỗi xử lý dấu cách hoặc tạo lỗ hổng command injection. Nếu thực sự cần shell, phải xác định rõ shell đích và quy tắc escape của shell đó.

## 8. Mã thoát của tiến trình Java

Mã thoát là một số nguyên mà tiến trình trả về khi kết thúc. Quy ước phổ biến là:

- **0:** tiến trình hoàn thành thành công.
- **Khác 0:** có lỗi hoặc kết quả không thành công; ý nghĩa cụ thể do ứng dụng quy định.

Nếu phương thức **main** kết thúc bình thường mà không gọi cơ chế kết thúc tiến trình, trạng thái thoát mặc định là **0**. Ứng dụng có thể yêu cầu trạng thái cụ thể bằng **System.exit(int)**:

~~~java
System.exit(0);  // Thanh cong
System.exit(2);  // Vi du: loi cu phap lenh
~~~

Lời gọi này kết thúc JVM sau khi thực hiện quy trình shutdown, bao gồm chạy các shutdown hook đã đăng ký. Nó ảnh hưởng đến toàn bộ tiến trình, vì vậy chỉ nên được gọi ở lớp khởi chạy của ứng dụng dòng lệnh. Thư viện dùng chung không nên tự gọi **System.exit**, vì thư viện không sở hữu vòng đời của tiến trình chứa nó.

Nên tách phần xử lý nghiệp vụ thành phương thức trả về mã trạng thái. Cách này giúp kiểm thử logic mà không kết thúc JVM kiểm thử. Lớp **main** chịu trách nhiệm chuyển kết quả đó thành trạng thái tiến trình.

~~~java
static int run(String[] args, Map<String, String> environment) {
    // Validate arguments and configuration, then perform the work.
    return 0;
}

public static void main(String[] args) {
    int status = run(args, System.getenv());
    if (status != 0) {
        System.exit(status);
    }
}
~~~

Mã **0**, **2** hay **3** trong ví dụ là hợp đồng do ứng dụng chọn, không phải danh sách mã lỗi chuẩn của Java. Hãy định nghĩa các hằng số có tên, mô tả ý nghĩa và duy trì tài liệu để script gọi chương trình có thể xử lý. Giữ mã thoát nhỏ và không dùng nó để truyền thông tin chẩn đoán dài; chi tiết lỗi nên nằm trong thông báo chuẩn lỗi hoặc log. Cách hệ điều hành và shell biểu diễn mã thoát có thể khác nhau.

## 9. Ví dụ CLI hoàn chỉnh

Ví dụ sau nhận định dạng báo cáo qua đối số **--format** và thư mục xuất qua biến môi trường **REPORT_OUTPUT_DIR**. Phương thức **run** nhận Map cấu hình từ bên ngoài để có thể kiểm thử mà không phụ thuộc môi trường máy đang chạy.

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public final class ReportCli {
    private static final int SUCCESS = 0;
    private static final int USAGE_ERROR = 2;
    private static final int CONFIGURATION_ERROR = 3;

    private ReportCli() {
    }

    public static void main(String[] args) {
        int status = run(args, System.getenv());
        if (status != SUCCESS) {
            System.exit(status);
        }
    }

    static int run(String[] args, Map<String, String> environment) {
        if (args.length != 2 || !"--format".equals(args[0])) {
            System.err.println("Usage: report-cli --format <csv|json>");
            return USAGE_ERROR;
        }

        String format = args[1].toLowerCase(Locale.ROOT);
        if (!Set.of("csv", "json").contains(format)) {
            System.err.println("Format must be csv or json");
            return USAGE_ERROR;
        }

        String outputDirectory = environment.get("REPORT_OUTPUT_DIR");
        if (outputDirectory == null || outputDirectory.isBlank()) {
            System.err.println("REPORT_OUTPUT_DIR is required");
            return CONFIGURATION_ERROR;
        }

        System.out.printf("Preparing %s report in %s%n", format, outputDirectory);
        return SUCCESS;
    }
}
~~~

Chạy trên shell kiểu POSIX:

~~~bash
REPORT_OUTPUT_DIR=./reports java -jar report-cli.jar --format csv
echo $?
~~~

Chạy trong PowerShell:

~~~powershell
$env:REPORT_OUTPUT_DIR = ".\reports"
java -jar report-cli.jar --format csv
$LASTEXITCODE
~~~

Lệnh cuối của mỗi ví dụ đọc mã thoát của tiến trình Java trong shell tương ứng. Nếu truyền sai đối số, chương trình trả về **2**; nếu thiếu cấu hình thư mục, chương trình trả về **3**; khi xử lý thành công và **main** kết thúc bình thường, tiến trình trả về **0**.

Có thể kiểm thử phương thức **run** trực tiếp:

~~~java
@Test
void returnsSuccessWhenArgumentsAndEnvironmentAreValid() {
    int status = ReportCli.run(
        new String[] {"--format", "csv"},
        Map.of("REPORT_OUTPUT_DIR", "build/reports")
    );

    assertEquals(0, status);
}
~~~

Bằng cách truyền đối số và Map môi trường giả lập, kiểm thử có thể bao phủ các trường hợp thiếu tham số, định dạng không hỗ trợ, thiếu biến cấu hình và giá trị hợp lệ. Không gọi **System.exit** trong kiểm thử đơn vị; hãy kiểm tra giá trị trả về của phương thức xử lý.

## 10. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| **ArrayIndexOutOfBoundsException** khi đọc args | Truy cập chỉ số trước khi kiểm tra số lượng đối số | Kiểm tra **args.length** và hiển thị hướng dẫn sử dụng |
| Cấu hình trả về **null** | Biến môi trường chưa được thiết lập hoặc sai tên | Kiểm tra môi trường tiến trình và chính tả tên biến |
| Giá trị cấu hình là chuỗi rỗng | Nền tảng đã khai báo biến nhưng không cấp giá trị | Kiểm tra cả **null** và **isBlank()** khi trường bắt buộc |
| Đọc system property không thấy biến đã thiết lập | Nhầm environment variable với system property | Dùng **System.getenv** cho biến môi trường, **System.getProperty** cho thuộc tính JVM |
| Script vẫn chạy dù Java báo lỗi | Script không kiểm tra mã thoát hoặc đã ghi đè trạng thái | Kiểm tra trạng thái ngay sau lệnh Java và truyền lỗi lên pipeline |
| Tiến trình con dùng cấu hình khác | Chưa đặt môi trường trong **ProcessBuilder** hoặc cấu hình bị ghi đè | Kiểm tra **builder.environment()** trước khi gọi **start()** |
| Kiểm thử bị dừng đột ngột | Mã kiểm thử gọi **System.exit** | Tách xử lý thành phương thức trả về mã trạng thái và kiểm thử phương thức đó |

## 11. Checklist thiết kế chương trình dòng lệnh

- [ ] Tài liệu mô tả cú pháp, tùy chọn bắt buộc, giá trị mặc định và ví dụ gọi chương trình.
- [ ] Mọi đối số đều được kiểm tra số lượng, định dạng và miền giá trị trước khi sử dụng.
- [ ] Cấu hình môi trường được đọc bằng đúng API và có thông báo khi thiếu.
- [ ] Chính sách ưu tiên giữa đối số, biến môi trường và cấu hình mặc định được công bố.
- [ ] Bí mật không bị in ra log hoặc truyền qua đối số dòng lệnh một cách tùy tiện.
- [ ] Mã thoát có quy ước rõ ràng, ổn định và được kiểm thử.
- [ ] **System.exit** chỉ được dùng tại ranh giới sở hữu vòng đời tiến trình.
- [ ] Tiến trình con nhận đúng đối số và môi trường cần thiết.
- [ ] Script và CI/CD kiểm tra mã thoát trước khi thực hiện bước tiếp theo.

Khi ba kênh đối số, cấu hình môi trường và mã thoát được thiết kế thành hợp đồng rõ ràng, chương trình Java có thể được gọi lặp lại từ terminal, script, scheduler, container và pipeline CI/CD. Điều đó giúp ứng dụng dễ vận hành, dễ tự động hóa và dễ kiểm thử trên nhiều môi trường.
