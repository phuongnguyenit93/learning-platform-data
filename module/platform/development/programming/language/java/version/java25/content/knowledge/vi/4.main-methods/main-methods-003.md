# Sử dụng main với String[] để xử lý đối số dòng lệnh trong Java 25

Một chương trình Java không nhất thiết nhận mọi dữ liệu từ bàn phím hay file cấu hình. Khi chạy từ terminal, CI/CD hoặc một tác vụ tự động, bạn có thể truyền trực tiếp các **đối số dòng lệnh** cho ứng dụng. Phương thức `main(String[] args)` là điểm nhận các giá trị này, chẳng hạn tên file cần xử lý, số lần lặp, chế độ chạy hoặc tùy chọn hiển thị.

Bài thuộc chương **Hàm main** của module `JAVA_VERSION_JAVA25`. Trong Java 25, **compact source files và instance main methods** đã trở thành tính năng chính thức (JEP 512), nên bạn có thể viết chương trình ngắn mà không cần khai báo class tường minh hoặc `static`. Tuy vậy, `String[] args` **vẫn là cơ chế tiêu chuẩn để nhận đối số**; hiểu nó giúp bạn thiết kế CLI đáng tin cậy và chuẩn bị cho các bài thực hành Java 25 hiện đại hơn.

> **Phạm vi hiện hành:** Các ví dụ dùng Java 25 GA, không cần `--enable-preview`. Bài tập trung vào cú pháp và hành vi còn được hỗ trợ trong Java 25; những API cũ chỉ để tương thích ngược hoặc các cơ chế main thuộc giai đoạn preview trước Java 25 không được dùng làm hướng dẫn triển khai mới.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mảng `String[] args` được tạo như thế nào và phần nào của lệnh `java` trở thành phần tử mảng.
2. Dùng `main(String[] args)` trong **class thông thường** và **compact source file** của Java 25.
3. Phân biệt `main(String[])`, `main(String...)` và `main()`; biết phương thức nào được Java 25 ưu tiên khi khởi chạy.
4. Đọc đối số theo vị trí và theo tên như `--name`, `--times`, `--uppercase`.
5. Kiểm tra đối số thiếu, không hợp lệ, trùng lặp và xử lý chuỗi chứa khoảng trắng.
6. Trả mã thoát (exit code) rõ ràng để terminal/CI nhận biết thành công hay lỗi.
7. Viết kiểm thử cho logic CLI mà không phải gọi `System.exit` trong từng test.

Ví dụ xuyên suốt là ứng dụng chào người dùng. Tuy đơn giản, nó thể hiện đủ nguyên tắc để mở rộng thành công cụ nhập dữ liệu, xử lý batch hoặc tác vụ tự động.

## 2. Java 25 cho phép những dạng main nào?

Cách quen thuộc vẫn hợp lệ:

```java
public class HelloCli {
    public static void main(String[] args) {
        System.out.println("Số đối số: " + args.length);
    }
}
```

Java 25 mở rộng giao thức tìm entry point theo Java Language Specification `12.1.4` và JEP 512. Một phương thức có thể dùng làm điểm bắt đầu nếu tên là `main`, trả về `void`, có **một tham số `String[]` hoặc không có tham số**, và có quyền truy cập `public`, `protected` hoặc package-private; nó có thể là `static` **hoặc instance**.

| Khai báo | Có thể là entry point Java 25? | Nhận đối số CLI? |
|---|---|---|
| `public static void main(String[] args)` | Có | Có |
| `static void main(String[] args)` | Có | Có |
| `void main(String[] args)` | Có, là instance main | Có |
| `void main(String... args)` | Có, `String...` tương đương mảng khi khai báo phương thức | Có |
| `public static void main()` | Có | Không |
| `void main()` | Có, là instance main | Không |
| `private static void main(String[] args)` | Không phải entry point hợp lệ | — |
| `int main(String[] args)` | Không phải entry point hợp lệ | — |
| `void main(String text)` | Không phải entry point hợp lệ | — |

**Quy tắc chọn:** nếu lớp có một `main(String[])` hợp lệ, Java **ưu tiên phương thức đó**, bất kể nó là static hay instance. Chỉ khi không có phương thức nhận mảng phù hợp, Java mới chọn `main()` không tham số.

Ví dụ:

```java
class SelectionDemo {
    static void main() {
        System.out.println("Không có args");
    }

    void main(String[] args) {
        System.out.println("Có args: " + args.length);
    }
}
```

Chạy `java SelectionDemo.java abc` sẽ gọi **instance `main(String[])`** và in `Có args: 1`. Nếu phương thức được chọn là instance, Java cần tạo đối tượng bằng constructor không tham số phù hợp. Đừng cố khai báo đồng thời static và instance `main(String[])` có cùng chữ ký: Java không cho phép hai phương thức chỉ khác `static`.

### 2.1. Compact source file với `main(String[] args)`

Tạo file `ArgsDemo.java` mà **không cần khai báo class**:

```java
void main(String[] args) {
    System.out.println("Số đối số: " + args.length);

    for (int i = 0; i < args.length; i++) {
        System.out.printf("args[%d] = <%s>%n", i, args[i]);
    }
}
```

Chạy trực tiếp bằng Java 25:

```bash
java ArgsDemo.java red "Nguyễn An" --debug
```

Output kỳ vọng:

```text
Số đối số: 3
args[0] = <red>
args[1] = <Nguyễn An>
args[2] = <--debug>
```

Trong Java 25, file này là **compact source file**: compiler tạo một lớp ngầm để chứa các thành viên ở top level. Bạn vẫn có thể viết các hàm trợ giúp, vòng lặp, biểu thức và `main(String[])` như trong class thông thường. Tính năng này **đã hoàn thiện**, không cần `--enable-preview`.

Khi ứng dụng tăng quy mô với nhiều package, module hoặc entry point, class được đặt tên tường minh vẫn hữu ích để quản lý API, kiểm thử và phân phối. Việc Java 25 hỗ trợ compact source file không buộc mọi dự án phải bỏ cấu trúc class.

## 3. Java launcher truyền những giá trị nào vào args?

Cú pháp launcher của JDK 25:

```text
java [tùy-chọn-JVM] TênLớp [đối-số-ứng-dụng...]
java [tùy-chọn-JVM] TênFile.java [đối-số-ứng-dụng...]
java [tùy-chọn-JVM] -jar app.jar [đối-số-ứng-dụng...]
java [tùy-chọn-JVM] --module tên.module[/TênLớp] [đối-số-ứng-dụng...]
```

**Phần sau tên lớp/file hoặc sau `app.jar`** được chuyển cho `main(String[] args)`. Phần trước đó được xử lý bởi `java` launcher/JVM. Java **không tự phân tích** `--name`, `--times`, `--format=json` thành đối tượng cấu hình; mỗi token trước hết chỉ là một `String`.

Ví dụ với `ArgsDemo.java`:

| Lệnh | `args` của chương trình |
|---|---|
| `java ArgsDemo.java` | Mảng rỗng, `length == 0` |
| `java ArgsDemo.java a b` | `["a", "b"]` |
| `java ArgsDemo.java "a b" c` | `["a b", "c"]` |
| `java ArgsDemo.java --times 3` | `["--times", "3"]` |
| `java ArgsDemo.java --times=3` | `["--times=3"]`, chỉ **một** chuỗi |
| `java -Xmx256m ArgsDemo.java a` | `["a"]`, `-Xmx256m` là tùy chọn JVM |
| `java ArgsDemo.java -Xmx256m` | `["-Xmx256m"]`, chương trình tự quyết định xử lý |

Với `java -jar tool.jar --name "Nguyễn An"`, hai phần tử truyền cho ứng dụng là `"--name"` và `"Nguyễn An"`. JAR cần khai báo entry point phù hợp trong manifest hoặc có trình đóng gói khởi chạy được.

### 3.1. Shell tách đối số trước Java

Trong terminal phổ biến, dấu ngoặc kép bao một giá trị có khoảng trắng thành **một** đối số:

```bash
java ArgsDemo.java --name "Nguyễn Văn An"
```

Khi chạy, `args.length == 2`: `args[0] == "--name"` và `args[1] == "Nguyễn Văn An"`. Nếu bỏ ngoặc kép, shell thường tách thành nhiều token. Quy tắc escape và mở rộng biến/ký tự đặc biệt phụ thuộc Bash, Zsh, PowerShell hoặc CMD; hãy kiểm tra trong terminal thực tế thay vì tự ghép chuỗi shell.

### 3.2. Mảng args chứa gì và không chứa gì?

- Các phần tử là `String` theo thứ tự đã truyền; phần tử đầu tiên ở chỉ số `0`.
- Với cách khởi chạy thông thường, **không có đối số** nghĩa là `args.length == 0`, không cần tự giả định `args == null`.
- `args` **không** chứa tên lớp hoặc tên file `.java` được chạy.
- `args` **không** chứa những JVM options đã được launcher tiêu thụ.
- `--help`, `--dry-run`, `--` và `--key=value` chỉ có ý nghĩa nếu **parser của ứng dụng** hoặc một thư viện CLI chủ động định nghĩa chúng.
- Java không tự ép `"12"` thành `int`, không tự kiểm tra path hợp lệ, cũng không tự ngăn người dùng gửi cùng option hai lần.

Ví dụ này cần phân biệt dữ liệu thô với dữ liệu đã kiểm tra kiểu; dùng `Integer.parseInt`, `Path.of` hoặc bộ kiểm tra theo hợp đồng CLI trước khi đưa vào nghiệp vụ.

## 4. Đọc đối số theo vị trí

Một CLI rất nhỏ có thể yêu cầu **tên** là phần tử đầu tiên, **số lần chào** là phần tử thứ hai.

```java
public class PositionalGreeting {

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println(
                "Cách dùng: java PositionalGreeting.java <ten> <so-lan>");
            System.exit(2);
        }

        String name = args[0];

        if (name.isBlank()) {
            System.err.println("Tên không được rỗng.");
            System.exit(2);
        }

        int count;
        try {
            count = Integer.parseInt(args[1]);
        } catch (NumberFormatException ex) {
            System.err.println("Số lần phải là số nguyên.");
            System.exit(2);
            return;
        }

        if (count < 1 || count > 5) {
            System.err.println("Số lần phải nằm trong khoảng 1..5.");
            System.exit(2);
        }

        for (int i = 0; i < count; i++) {
            System.out.println("Xin chào, " + name + "!");
        }
    }
}
```

Lưu file `PositionalGreeting.java` và chạy:

```bash
java PositionalGreeting.java "Nguyễn An" 2
```

Kết quả:

```text
Xin chào, Nguyễn An!
Xin chào, Nguyễn An!
```

**Vì sao kiểm tra `args.length` trước khi đọc `args[0]` hoặc `args[1]`?** Nếu chạy không đủ đối số, truy cập phần tử không tồn tại gây `ArrayIndexOutOfBoundsException` và in stack trace khó hiểu. Kiểm tra hợp đồng đầu vào giúp trả thông báo và mã lỗi nhất quán.

**Vì sao cần `try/catch` khi parse số?** `Integer.parseInt("hai")` ném `NumberFormatException`; không nên để một dữ liệu CLI không hợp lệ thành lỗi runtime chưa được kiểm soát. Đoạn ví dụ dùng `System.exit` để minh họa mã lỗi trong phương thức `main`; phần tiếp theo tách logic để dễ kiểm thử hơn.

### 4.1. Nhược điểm của đối số theo vị trí

Với `PositionalGreeting "An" 3`, người dùng phải nhớ vị trí của từng tham số. Khi ứng dụng có nhiều giá trị tùy chọn, việc thêm một phần tử vào giữa có thể làm lệnh cũ bị hiểu sai.

| Phù hợp positional arguments | Phù hợp named options |
|---|---|
| Chỉ có 1–2 tham số bắt buộc rõ nghĩa | Nhiều tham số tùy chọn, có giá trị mặc định |
| Thứ tự mang ý nghĩa nghiệp vụ | Muốn truyền tham số theo thứ tự tùy ý |
| Lệnh ngắn, chạy thủ công | CLI dùng trong CI, script, cần tự mô tả |

Phần sau dùng `--name`, `--times` và `--uppercase` để có hợp đồng dễ sử dụng hơn.

## 5. Thiết kế giao diện CLI trước khi code

Chọn một hợp đồng cho lệnh `GreetingCli`:

```text
java GreetingCli.java --name <ten> [--times <1..5>] [--uppercase]
java GreetingCli.java --help
```

| Option | Kiểu | Bắt buộc | Quy tắc |
|---|---|---|---|
| `--name` | Chuỗi | Có | Không rỗng, không chỉ khoảng trắng, dài tối đa 60 ký tự |
| `--times` | Số nguyên | Không | Mặc định 1, từ 1 đến 5 |
| `--uppercase` | Cờ boolean | Không | Không cần thêm `true` hoặc `false` |
| `--help` | Cờ trợ giúp | Không | Dùng **một mình** để in cách dùng |
| Option không nhận diện | — | — | Lỗi, exit code 2 |
| Option xuất hiện trùng | — | — | Lỗi để tránh cấu hình nhập nhằng |

Ví dụ:

```bash
java GreetingCli.java --name "Nguyễn An" --times 2
java GreetingCli.java --uppercase --name Lan
java GreetingCli.java --help
```

Định nghĩa cả mã trả về:

- `0`: chạy thành công hoặc in `--help`.
- `2`: cú pháp/giá trị đối số không hợp lệ.

Đây là **quy ước do ứng dụng chọn**, không phải JVM tự quy định mọi lỗi đối số đều phải trả `2`. Với chương trình batch thực tế, có thể bổ sung mã khác cho lỗi đọc file, mạng hoặc nghiệp vụ và ghi thành tài liệu hợp đồng CLI.

## 6. CLI hoàn chỉnh: parse, validate và trả exit code

Tạo `GreetingCli.java` dưới đây. Ví dụ này dùng **class tường minh** để người học dễ tách parser ra kiểm thử; cú pháp `switch` và `String.isBlank()` là những tính năng Java ổn định, còn phù hợp khi chạy trên Java 25.

```java
import java.io.PrintStream;
import java.util.Locale;

public final class GreetingCli {

    private GreetingCli() {
    }

    public static void main(String[] args) {
        int exitCode = run(args, System.out, System.err);
        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }

    // Package-private để test gọi trực tiếp, không kết thúc JVM.
    static int run(String[] args, PrintStream out, PrintStream err) {
        if (args.length == 1 && "--help".equals(args[0])) {
            printUsage(out);
            return 0;
        }

        String name = null;
        int times = 1;
        boolean timesSpecified = false;
        boolean uppercase = false;

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--name" -> {
                    if (name != null) {
                        return invalid(err, "--name bị lặp.");
                    }
                    if (i + 1 >= args.length) {
                        return invalid(err, "--name thiếu giá trị.");
                    }
                    name = args[++i].trim();
                    if (name.isBlank() || name.length() > 60
                            || name.startsWith("--")) {
                        return invalid(err, "--name không hợp lệ.");
                    }
                }
                case "--times" -> {
                    if (timesSpecified) {
                        return invalid(err, "--times bị lặp.");
                    }
                    if (i + 1 >= args.length) {
                        return invalid(err, "--times thiếu giá trị.");
                    }

                    String rawTimes = args[++i];
                    try {
                        times = Integer.parseInt(rawTimes);
                    } catch (NumberFormatException ex) {
                        return invalid(err, "--times phải là số nguyên.");
                    }

                    if (times < 1 || times > 5) {
                        return invalid(err, "--times phải nằm trong 1..5.");
                    }
                    timesSpecified = true;
                }
                case "--uppercase" -> {
                    if (uppercase) {
                        return invalid(err, "--uppercase bị lặp.");
                    }
                    uppercase = true;
                }
                default -> {
                    return invalid(err, "Không hỗ trợ: " + args[i]);
                }
            }
        }

        if (name == null) {
            return invalid(err, "Thiếu tham số bắt buộc --name.");
        }

        String message = "Xin chào, " + name + "!";
        if (uppercase) {
            message = message.toUpperCase(Locale.ROOT);
        }

        for (int i = 0; i < times; i++) {
            out.println(message);
        }
        return 0;
    }

    private static int invalid(PrintStream err, String message) {
        err.println("Lỗi: " + message);
        err.println("Dùng --help để xem hướng dẫn.");
        return 2;
    }

    private static void printUsage(PrintStream out) {
        out.println("""
            Cách dùng:
              java GreetingCli.java --name <ten> [--times <1..5>] [--uppercase]
              java GreetingCli.java --help

            Ví dụ:
              java GreetingCli.java --name "Nguyễn An" --times 2
            """);
    }
}
```

**Những quyết định quan trọng trong code:**

1. `main(String[])` chỉ điều phối và trả exit code; logic ở `run(...)` dễ gọi trực tiếp bằng test.
2. `switch(args[i])` xử lý mỗi token; option có giá trị tăng `i` để dùng phần tử kế tiếp.
3. `Integer.parseInt` chuyển chuỗi thành kiểu số và bắt lỗi đúng chỗ.
4. Biến `timesSpecified` phân biệt “chưa có `--times`” với “người dùng đã nhập `--times 1`”; nhờ đó phát hiện option lặp.
5. `--uppercase` là cờ boolean; code không tự hỗ trợ cú pháp `--uppercase=true`.
6. `Locale.ROOT` giúp thao tác chuyển chữ hoa không phụ thuộc locale mặc định của server; nếu sản phẩm cần quy tắc ngôn ngữ cụ thể, hãy chọn `Locale` phù hợp.
7. Không đưa `String[] args` thẳng cho lệnh hệ điều hành, câu SQL hay log nhạy cảm; dữ liệu chỉ được sử dụng sau bước parse/validation.

**Giới hạn đã định nghĩa:** `--help` chỉ hợp lệ khi là đối số duy nhất; `--name` bắt đầu bằng `--` bị từ chối; `--name=An` và `--times=3` chưa được hỗ trợ. Những lựa chọn này là **hợp đồng parser**, không phải giới hạn của Java 25.

### 6.1. Chạy bằng source-file mode

```bash
java --version
java GreetingCli.java --name "Nguyễn An" --times 2
java GreetingCli.java --uppercase --name Lan
java GreetingCli.java --help
```

Để chạy trực tiếp file nguồn, dùng **JDK 25** và không cần bước `javac` thủ công. Lệnh launcher compile và khởi chạy source code. Đây là một chế độ chạy được hỗ trợ, không phải tính năng preview.

### 6.2. Biên dịch rồi chạy class

```bash
javac --release 25 GreetingCli.java
java GreetingCli --name "Nguyễn An" --times 2
```

Phân biệt rõ hai dạng:

- `java GreetingCli.java ...`: launcher xử lý **source file**.
- `java GreetingCli ...`: launcher tìm **class đã biên dịch** trên classpath phù hợp.

Không thêm đuôi `.class` vào tên lớp ở lệnh thứ hai. Nếu dùng package, hãy đặt file đúng cấu trúc thư mục và cung cấp tên lớp đầy đủ khi khởi chạy.

### 6.3. Đóng gói JAR có entry point

Với ví dụ lớp ở unnamed package:

```bash
javac GreetingCli.java
jar --create --file greeting-cli.jar --main-class GreetingCli GreetingCli.class
java -jar greeting-cli.jar --name "Nguyễn An" --times 2
```

`java -jar` chuyển các token sau tên JAR đến điểm vào ứng dụng. Đối với project Maven/Gradle lớn, dùng plugin đóng gói phù hợp và xác minh manifest/main class thực được cấu hình.

## 7. Các kịch bản thành công và thất bại

| Lệnh (rút gọn sau `GreetingCli.java`) | Kết quả kỳ vọng | Exit code |
|---|---|---:|
| `--name Lan` | In một lời chào | 0 |
| `--name "Nguyễn An" --times 2` | In hai lời chào | 0 |
| `--uppercase --name Lan` | In lời chào chữ hoa | 0 |
| `--help` | In hướng dẫn | 0 |
| Không truyền đối số | Báo thiếu `--name` | 2 |
| `--times 2` | Báo thiếu `--name` | 2 |
| `--name Lan --times abc` | Báo giá trị số không hợp lệ | 2 |
| `--name Lan --times 0` | Báo ngoài giới hạn | 2 |
| `--name Lan --times 999999999999` | Báo giá trị số không hợp lệ hoặc quá lớn | 2 |
| `--name ""` | Báo tên rỗng | 2 |
| `--name Lan --name Mai` | Báo trùng option | 2 |
| `--name Lan --unknown` | Báo option không hỗ trợ | 2 |
| `--name` | Báo thiếu giá trị | 2 |

Trong **Bash/Zsh**, sau một lệnh lỗi có thể xem mã thoát:

```bash
java GreetingCli.java --name Lan --times 0
echo $?
```

Trong **PowerShell**:

```powershell
java GreetingCli.java --name Lan --times 0
$LASTEXITCODE
```

Một CLI hỗ trợ tự động hóa nên ghi chẩn đoán lỗi vào `stderr` và dữ liệu đầu ra bình thường vào `stdout`. Người vận hành có thể dùng exit code để dừng pipeline thay vì tìm chuỗi “Lỗi” trong log.

## 8. Tách parser khỏi main để kiểm thử

Khi `main` gọi `System.exit` trực tiếp ở mọi nhánh, unit test có thể bị kết thúc cả JVM chạy test. Cách ở mục 6 chỉ dùng `System.exit` ở biên khởi chạy; `run(...)` trả `int` và nhận hai `PrintStream` nên dễ kiểm tra output.

Ví dụ JUnit 5, đặt `GreetingCliTest.java` trong cùng package với `GreetingCli`:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class GreetingCliTest {

    @Test
    void printsTwoGreetings() {
        var stdout = new ByteArrayOutputStream();
        var stderr = new ByteArrayOutputStream();

        int exitCode = GreetingCli.run(
            new String[]{"--name", "Lan", "--times", "2"},
            new PrintStream(stdout, true, StandardCharsets.UTF_8),
            new PrintStream(stderr, true, StandardCharsets.UTF_8)
        );

        assertEquals(0, exitCode);
        assertEquals(
            2,
            stdout.toString(StandardCharsets.UTF_8).lines().count()
        );
        assertEquals("", stderr.toString(StandardCharsets.UTF_8));
    }

    @Test
    void rejectsInvalidInteger() {
        var stdout = new ByteArrayOutputStream();
        var stderr = new ByteArrayOutputStream();

        int exitCode = GreetingCli.run(
            new String[]{"--name", "Lan", "--times", "abc"},
            new PrintStream(stdout, true, StandardCharsets.UTF_8),
            new PrintStream(stderr, true, StandardCharsets.UTF_8)
        );

        assertEquals(2, exitCode);
        assertTrue(
            stderr.toString(StandardCharsets.UTF_8)
                .contains("--times phải là số nguyên")
        );
    }

    @Test
    void rejectsUnknownOption() {
        var stdout = new ByteArrayOutputStream();
        var stderr = new ByteArrayOutputStream();

        int exitCode = GreetingCli.run(
            new String[]{"--name", "Lan", "--unknown"},
            new PrintStream(stdout, true, StandardCharsets.UTF_8),
            new PrintStream(stderr, true, StandardCharsets.UTF_8)
        );

        assertEquals(2, exitCode);
        assertTrue(
            stderr.toString(StandardCharsets.UTF_8)
                .contains("Không hỗ trợ: --unknown")
        );
    }
}
```

Các kiểm thử này yêu cầu JUnit 5 trên test classpath và không phụ thuộc vào môi trường container hay shell thực. Với dự án Java 25, hãy chọn phiên bản JUnit/Maven Surefire hoặc Gradle Test tương thích. Đây là **ví dụ để người học chạy**, không phải kết quả build đã thực hiện trong bài viết.

### 8.1. Unit test và CLI integration test bổ sung cho nhau

| Loại kiểm tra | Phát hiện tốt | Không phát hiện hết |
|---|---|---|
| Unit test `run(...)` | Parser, validation, output, exit code logic | Sai lệnh launcher, đóng gói JAR, shell quoting |
| Chạy `java GreetingCli.java ...` | Source-file mode, tham số thực và mã thoát | Toàn bộ hành vi khi đóng gói và triển khai |
| Chạy `java -jar ...` | Manifest entry point và truyền đối số sau `-jar` | Những nhánh parser chưa được test |
| CI trên OS khác nhau | Khác biệt shell/script, encoding terminal, Java distribution | Chất lượng nghiệp vụ không có trong testcase |

Khi ứng dụng cần bảo đảm hoạt động trên Windows và Linux, hãy có tối thiểu một smoke test CLI thật cho mỗi nền tảng mục tiêu.

## 9. Những lỗi hay gặp khi dùng String[] args

### 9.1. Đọc `args[0]` khi mảng rỗng

```java
// Sai khi chạy không có đối số:
System.out.println(args[0]);
```

Sửa bằng kiểm tra `args.length` hoặc parser đã định nghĩa hợp đồng rõ ràng.

### 9.2. Nhầm String với số

```java
// Không thể dùng trực tiếp chuỗi như một số nguyên:
String raw = args[0];

// Đúng: kiểm tra và chuyển kiểu trong một ranh giới rõ ràng:
int number = Integer.parseInt(raw);
```

Phải xử lý `NumberFormatException` và giới hạn miền giá trị theo nghiệp vụ, như khoảng `1..5` trong ví dụ.

### 9.3. Nhầm JVM options với application options

```bash
# -Xmx là tùy chọn JVM:
java -Xmx256m GreetingCli.java --name Lan

# -Xmx ở sau file sẽ được parser của GreetingCli nhận và từ chối:
java GreetingCli.java --name Lan -Xmx256m
```

Tương tự, `-Dapp.mode=test` đặt **trước** tên lớp/file là system property của JVM; đặt **sau** tên lớp/file là một chuỗi trong `args`. Muốn đọc property hệ thống, dùng `System.getProperty("app.mode")`; không đồng nhất nó với CLI options.

### 9.4. Giả định Java tự hiểu cú pháp `--key=value`

```text
--times 3    -> hai phần tử ["--times", "3"]
--times=3    -> một phần tử ["--times=3"]
```

Parser mẫu chỉ hỗ trợ dạng **hai phần tử**. Muốn thêm `--times=3`, bạn phải xử lý chuỗi, hoặc chọn thư viện CLI có hợp đồng và version được duy trì phù hợp.

### 9.5. Trộn nhiều cách đọc cấu hình

Trong hệ thống lớn, cùng một tùy chọn có thể đến từ CLI, biến môi trường, file cấu hình và secret manager. Nếu không có **thứ tự ưu tiên** rõ ràng, người chạy không biết giá trị nào được áp dụng. Hãy định nghĩa quy tắc ví dụ `CLI > biến môi trường > config file > default` (nếu sản phẩm lựa chọn quy tắc này) và tránh đọc ngẫu nhiên trong nhiều lớp.

### 9.6. Dùng main không tham số rồi mong nhận args

```java
void main() {
    System.out.println("Không truy cập trực tiếp args trong phương thức này");
}
```

`main()` có thể được khởi chạy trong Java 25, nhưng **không có biến `args` được truyền tới method**. Với CLI cần đọc dữ liệu, hãy khai báo `main(String[] args)` ngay từ đầu.

## 10. Thiết kế CLI an toàn và dễ vận hành

Đối số dòng lệnh là **input không đáng tin cậy**. Dù ứng dụng chỉ chạy trong CI nội bộ, người khác có thể truyền sai kiểu, đường dẫn nhạy cảm hoặc chuỗi rất dài.

- **Bảo vệ phạm vi:** kiểm tra kiểu, chiều dài, số lượng, giá trị hợp lệ và quan hệ giữa các option trước khi xử lý nghiệp vụ.
- **Không in bí mật:** mật khẩu, access token, private key và dữ liệu cá nhân nhạy cảm không nên truyền qua CLI khi có cơ chế secret manager/credential provider phù hợp; đối số tiến trình có thể xuất hiện trong process listing, history, log CI hoặc công cụ giám sát.
- **Không nối lệnh shell bằng chuỗi thô:** dùng API tạo process với danh sách phần tử argument (`ProcessBuilder`) nếu thật sự phải gọi một tiến trình; vẫn cần kiểm tra quyền và dữ liệu.
- **Đường dẫn file:** khi thêm option `--input`, dùng `Path.of(...)` và kiểm tra path, permissions, thư mục cho phép và kiểu file trước khi đọc/ghi; dấu ngoặc kép ở shell chỉ giải quyết việc tách token, không chứng minh path an toàn.
- **Lỗi dễ hành động:** gửi thông báo rõ vào `stderr`, hướng dẫn `--help`, trả exit code khác 0; tránh in stack trace cho lỗi cú pháp người dùng.
- **Không log toàn bộ args trong production:** có thể vô tình ghi secrets hoặc thông tin nhạy cảm. Nếu cần telemetry, chỉ ghi tên lệnh, loại lỗi hoặc các trường đã được cho phép.
- **Không nhầm exit code với kết quả nghiệp vụ:** lệnh thực thi thành công về kỹ thuật có thể ghi nhận nghiệp vụ “không tìm thấy dữ liệu”; quy ước status/output cần được tài liệu hóa.

Trong ví dụ, `String.isBlank()` loại chuỗi chỉ có khoảng trắng, `Integer.parseInt` xử lý số nguyên, `PrintStream err` phân loại lỗi và `System.exit(2)` chỉ được gọi ở lớp biên CLI.

## 11. Áp dụng trong Java 25 và môi trường tự động hóa

### 11.1. Kịch bản chạy lặp trong CI

CLI ổn định là một hợp đồng giữa mã Java và script:

```bash
java GreetingCli.java --name "CI Runner" --times 2
```

Nếu CLI trả mã lỗi `2`, pipeline nên dừng hoặc báo lỗi theo chính sách build. Không nên viết script bỏ qua mọi exit code chỉ vì chương trình có in output.

Khi nâng JDK lên 25, kiểm tra `java --version` trong **môi trường thực chạy script**. Nếu application sử dụng compact source file hoặc instance main từ Java 25, runtime cũ hơn không nhất thiết khởi chạy được. Cấu hình Maven/Gradle toolchain và container image cũng phải khớp đích.

### 11.2. Khi nào dùng thư viện parser?

Với chỉ vài option, parser minh họa là đủ để học `String[]`. Khi có nhiều subcommand, help tự sinh, tùy chọn lặp, file cấu hình hoặc validate phức tạp, cân nhắc thư viện CLI còn được duy trì (ví dụ `picocli`) và khóa version được dự án kiểm tra. Thư viện giúp bớt mã parser nhưng **không thay đổi** cơ chế nền tảng: Java launcher vẫn gửi token thô qua `String[] args`.

### 11.3. Liên hệ các khả năng Java 25 khác

`main(String[] args)` có thể là biên cấu hình cho một công cụ đánh giá **AOT cache**, thu **JFR**, thử **ScopedValue** hoặc gọi API dẫn xuất khóa; tuy nhiên mỗi tác vụ cần thêm chính sách kiểm tra riêng. Đừng dùng đối số dòng lệnh để chuyển **khóa bí mật** hoặc dữ liệu nhạy cảm chỉ vì việc viết `--secret <value>` dễ dàng.

Compact source files của Java 25 giúp viết các công cụ nhỏ hoặc thử nghiệm tại terminal nhanh hơn, còn ứng dụng module lớn có thể giữ `public static void main(String[] args)` và cấu trúc package quen thuộc. Cả hai đều là Java hiện hành.

## 12. Bài tập thực hành

### Bài tập A — Khám phá mảng args

Tạo `ArgsDemo.java` dạng compact source file, chạy năm lệnh sau:

```bash
java ArgsDemo.java
java ArgsDemo.java one
java ArgsDemo.java one two
java ArgsDemo.java "one two"
java ArgsDemo.java --times=3
```

Ghi lại `args.length` và từng phần tử, giải thích vì sao `"one two"` thành một phần tử và `--times=3` vẫn là chuỗi chưa parse.

### Bài tập B — Thử lựa chọn main

Viết một class có `static void main()` và `void main(String[] args)` như phần 2. Chạy không args và có args, xác minh Java 25 luôn chọn bản nhận `String[]` khi nó tồn tại. Đổi `main(String[])` thành `private` và ghi nhận hành vi launch sau khi compile lại; dùng JLS 12.1.4 để giải thích.

### Bài tập C — Mở rộng parser

Bổ sung `--language vi|en` cho `GreetingCli`:

1. `vi` là mặc định.
2. `en` in `Hello, <name>!`.
3. Giá trị ngoài `vi`/`en` trả exit code `2`.
4. Option bị lặp phải báo lỗi.
5. Viết unit test cho giá trị hợp lệ và không hợp lệ.

Không dùng `String.contains(...)` để chấp nhận một giá trị gần giống; hãy kiểm tra tập giá trị hợp lệ theo hợp đồng.

### Bài tập D — Thêm input là đường dẫn

Tạo `--input <file>`, chuyển chuỗi thành `Path` rồi kiểm tra tồn tại, quyền đọc và loại file. Chạy thử với đường dẫn chứa khoảng trắng; xác định vì sao cần trích dẫn đường dẫn ở shell. Không in toàn bộ nội dung file hay đường dẫn nhạy cảm trong log.

### Bài tập E — Bảo vệ hợp đồng CLI

Viết kiểm thử cho các trường hợp thiếu option, duplicate, số âm, số rất lớn, chuỗi rỗng, option lạ và `--help`. Với mỗi test, kiểm tra **stdout**, **stderr** và **exit code** thay vì chỉ kiểm tra chương trình không ném ngoại lệ.

## 13. Ma trận nghiệm thu

| Mã | Kiểm tra | Kỳ vọng |
|---|---|---|
| MAIN-01 | Chạy compact source file `void main(String[] args)` trên JDK 25 | Chạy được không cần `--enable-preview` |
| MAIN-02 | Chạy không có CLI args | `args.length == 0` |
| MAIN-03 | Chạy với giá trị được đặt trong ngoặc kép | Giữ nguyên chuỗi có khoảng trắng thành một phần tử |
| MAIN-04 | Có cả `main(String[])` và `main()` | Java 25 chọn bản có `String[]` |
| MAIN-05 | `java -Xmx256m File.java value` | `-Xmx256m` là JVM option; `args` chỉ có `value` |
| MAIN-06 | `--name Lan --times 2` | Hai lời chào; exit code `0` |
| MAIN-07 | `--name Lan --times abc` | Báo lỗi vào stderr; exit code `2` |
| MAIN-08 | `--name` không có giá trị | Không truy cập ngoài mảng; exit code `2` |
| MAIN-09 | Truyền option trùng hoặc không nhận diện | Báo lỗi rõ, không âm thầm ghi đè |
| MAIN-10 | `--help` duy nhất | In hướng dẫn, exit code `0` |
| MAIN-11 | Unit test gọi `run(...)` | Không cần gọi `System.exit` trong test |
| MAIN-12 | Chạy `java -jar` từ JAR có manifest đúng | Nhận đối số như khi chạy source/class |
| MAIN-13 | Chạy qua CI trên môi trường Java 25 | Mã thoát được truyền về pipeline đúng |
| MAIN-14 | Kiểm tra không có ID/bí mật trong logs | Không in raw args hoặc gắn giá trị nhạy cảm vào telemetry |

**Sản phẩm cần nộp:** file `ArgsDemo.java`, `GreetingCli.java`, các lệnh thử nghiệm, kết quả `GreetingCliTest`, bảng exit code và một đoạn mô tả hợp đồng CLI. Hãy ghi rõ bạn kiểm thử trên **JDK 25** nào và dùng shell nào, vì cú pháp trích dẫn đối số có thể khác nhau theo môi trường.

### Câu hỏi tự kiểm tra

1. Tại sao `main(String[] args)` vẫn quan trọng dù Java 25 cho phép `main()` không tham số?
2. Khi chạy `java Program.java a "b c"`, mảng `args` có bao nhiêu phần tử?
3. Vì sao `--times=3` không tự động trở thành hai phần tử?
4. Java 25 ưu tiên phương thức nào khi lớp có cả `main(String[])` và `main()`?
5. Vì sao cần kiểm tra `args.length` trước khi đọc `args[0]`?
6. `Integer.parseInt` có thể ném lỗi gì và tại sao vẫn cần kiểm tra miền giá trị sau khi parse?
7. Vì sao tách `run(String[], PrintStream, PrintStream)` khỏi `main` giúp kiểm thử?
8. Khác nhau thế nào giữa `java -Dapp.mode=test Program` và `java Program -Dapp.mode=test`?
9. Lợi ích của `stderr` và exit code là gì trong script/CI?
10. Khi nào nên dùng một thư viện CLI có hỗ trợ subcommand thay vì viết parser thủ công?
11. Vì sao không nên nhận mật khẩu hoặc token qua command line khi có giải pháp an toàn hơn?
12. Nếu Java 25 có cả compact source file và class thông thường, bạn chọn cách nào cho công cụ nhỏ và vì sao?

## 14. Nguồn tham khảo chính thức

Các tài liệu dưới đây mô tả **hành vi Java 25 đã chuẩn hóa**, dùng để kiểm tra cú pháp và cách launcher truyền args:

- [Java Language Specification, Java SE 25 — `12.1.4 Invoke a main Method](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4)
- [Oracle Java SE 25 Language Guide — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html)
- [Oracle JDK 25 — java Command: class, JAR, module và source-file modes](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [OpenJDK JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)

**Điểm cần nhớ:** `String[] args` là cầu nối đơn giản và ổn định giữa shell và chương trình Java. Java 25 giúp viết `main` ngắn gọn hơn, nhưng **parser, validation, thông báo lỗi, mã thoát và an toàn dữ liệu** vẫn là trách nhiệm của ứng dụng. Khi thiết kế tốt ranh giới này, một chương trình Java nhỏ có thể trở thành công cụ CLI dễ kiểm thử và đáng tin cậy trong phát triển hiện đại.
