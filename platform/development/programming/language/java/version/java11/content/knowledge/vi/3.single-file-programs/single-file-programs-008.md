# Ứng dụng tiện ích dòng lệnh và thử nghiệm nhỏ bằng chương trình một tệp Java (Java 11+)

## Bạn sẽ làm được gì?

Sau bài này, bạn có thể viết một tiện ích Java nhỏ, chạy trực tiếp từ tệp `.java`, đọc tham số dòng lệnh, xử lý lỗi, thử nhanh API Java và xác định khi nào nên chuyển thành dự án có cấu trúc. Ví dụ chính sử dụng cú pháp và API **Java 11 trở lên**; không cần Gradle, Maven hoặc thư viện ngoài.

Bài tập trung vào hai tình huống thực dụng:
- **Tiện ích dòng lệnh:** đọc một tệp văn bản UTF-8 và hiển thị các dòng có số thứ tự, tùy chọn bỏ dòng trống.
- **Thử nghiệm nhỏ:** kiểm tra một giả định về hành vi API Java bằng chương trình tối giản, có kết quả rõ ràng.

## 1. Chương trình nguồn một tệp hoạt động như thế nào?

Từ Java 11 (JEP 330), trình khởi chạy `java` có thể **biên dịch và chạy trực tiếp mã nguồn**:

```bash
java LineViewer.java notes.txt --nonblank
```

Khi tên đối số là tệp mã nguồn tồn tại với đuôi `.java`, lệnh `java` chọn *source-file mode*: sử dụng trình biên dịch để biên dịch mã nguồn vào bộ nhớ, rồi chạy lớp chứa điểm vào `main`. Vì vậy:

- Mã vẫn là **Java biên dịch và kiểm tra kiểu**, không phải một ngôn ngữ script diễn giải.
- Bạn không cần gọi `javac` riêng cho lần chạy nhỏ này; launcher thông thường không tạo tệp `.class` của chương trình nguồn ra thư mục hiện tại.
- Mỗi lần khởi chạy lại thực hiện bước biên dịch phù hợp; dùng build thông thường khi cần xây dựng, đóng gói hoặc chạy lặp đi lặp lại ở quy mô lớn.
- Các đối số **đứng sau tên tệp mã nguồn** được chuyển vào `String[] args` của chương trình.

Có thể viết điểm vào thông dụng, tương thích Java 11:

```java
public class HelloTool {
    public static void main(String[] args) {
        System.out.println("Hello from Java");
    }
}
```

Lưu trong `HelloTool.java`, sau đó:

```bash
java HelloTool.java
```

Kết quả:

```text
Hello from Java
```

Để chạy được, hãy cài **JDK 11 hoặc mới hơn**, mở terminal tại thư mục chứa tệp và kiểm tra `java -version`. Trong bài này, chúng ta giữ dạng `public static void main(String[] args)` để tương thích Java 11 và dễ nâng cấp thành chương trình biên dịch thông thường.

### So sánh hai cách chạy

| Chạy mã nguồn trực tiếp | Biên dịch riêng rồi chạy |
| --- | --- |
| `java HelloTool.java` | `javac HelloTool.java`, sau đó `java HelloTool` |
| Phù hợp thử ý tưởng hoặc tiện ích nhỏ | Phù hợp khi cần sản phẩm biên dịch, kiểm thử và phân phối |
| Launcher biên dịch trước khi chạy | Bước biên dịch và chạy tách biệt |
| Không cần quản lý tệp `.class` cho lần chạy này | `javac` mặc định tạo `.class` trên đĩa |

## 2. Ví dụ hoàn chỉnh: xem nhanh tệp log hoặc ghi chú theo số dòng

Giả sử bạn cần kiểm tra tệp log, bỏ những dòng chỉ chứa khoảng trắng và vẫn biết dòng gốc nằm ở vị trí nào. Một tiện ích nhỏ có thể giúp hơn việc viết ngay cả một ứng dụng lớn.

**Tệp: `LineViewer.java`** — chạy trên Java 11+

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;

public class LineViewer {
    private static void usage() {
        System.err.println(
                "Usage: java LineViewer.java <file> [--nonblank]");
    }

    public static void main(String[] args) {
        if (args.length == 1 && "--help".equals(args[0])) {
            System.out.println(
                    "Usage: java LineViewer.java <file> [--nonblank]");
            return;
        }

        if (args.length < 1 || args.length > 2
                || args[0].startsWith("--")
                || (args.length == 2 && !"--nonblank".equals(args[1]))) {
            usage();
            System.exit(2);
        }

        boolean skipBlank = args.length == 2;

        try {
            Path path = Path.of(args[0]);
            try (BufferedReader reader =
                    Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String line;
                long lineNumber = 0;
                long shown = 0;

                while ((line = reader.readLine()) != null) {
                    lineNumber++;
                    if (skipBlank && line.isBlank()) {
                        continue;
                    }
                    System.out.println(lineNumber + ": " + line);
                    shown++;
                }

                System.out.println("Shown: " + shown);
            }
        } catch (IOException | InvalidPathException | SecurityException e) {
            System.err.println("Read failed: " + e.getMessage());
            System.exit(1);
        }
    }
}
```

**Chuẩn bị dữ liệu:** tạo tệp `notes.txt` trong cùng thư mục, mã hóa UTF-8, với đúng ba dòng nội dung (dòng 2 rỗng):

```text
alpha

beta
```

Chạy từ terminal:

```bash
java LineViewer.java notes.txt --nonblank
```

**Stdout chính xác:**

```text
1: alpha
3: beta
Shown: 2
```

Cơ chế:
1. `args[0]` là đường dẫn `notes.txt`; `args[1]` là tùy chọn `--nonblank`.
2. `Path.of(...)` chuyển chuỗi đường dẫn thành `Path`; `Files.newBufferedReader(...)` mở tệp theo UTF-8.
3. `readLine()` đọc lần lượt từng dòng mà không tải toàn bộ tệp thành một danh sách; `lineNumber` tăng cả với dòng rỗng để giữ số dòng gốc.
4. `String.isBlank()` (Java 11) nhận biết chuỗi rỗng hoặc chỉ gồm ký tự khoảng trắng theo quy tắc của Java.
5. `try-with-resources` đóng bộ đọc cả khi hoàn thành lẫn khi xảy ra lỗi.
6. `IOException`, `InvalidPathException` và `SecurityException` được xử lý bằng thông báo trên stderr và mã kết thúc khác 0.

Không truyền tùy chọn `--nonblank` thì chương trình vẫn hiển thị dòng rỗng, với kết quả tương ứng:

```bash
java LineViewer.java notes.txt
```

```text
1: alpha
2: 
3: beta
Shown: 3
```

Kết quả trên giả định tệp `notes.txt` đúng như mẫu. Khi tệp thực tế khác, nội dung stdout cũng khác.

### Kiểm tra các nhánh đầu vào

```bash
java LineViewer.java --help
```

Stdout:

```text
Usage: java LineViewer.java <file> [--nonblank]
```

Lệnh không đủ hoặc sai tham số (ví dụ `java LineViewer.java` hoặc `java LineViewer.java notes.txt --unknown`) in hướng dẫn ra **stderr** và kết thúc với mã **2**. Đường dẫn không đọc được, không tồn tại hoặc tệp không có nội dung UTF-8 hợp lệ sẽ đi vào nhánh lỗi đọc, in thông báo `Read failed: ...` ra **stderr** và kết thúc với mã **1**; phần mô tả lỗi sau dấu hai chấm phụ thuộc hệ điều hành/tình huống. Kết thúc bình thường có mã **0**. Các mã 1/2 là quy ước mà ví dụ tự chọn, không phải một ánh xạ bắt buộc của ngôn ngữ Java.

**Đường dẫn có dấu cách:** đặt đường dẫn trong dấu nháy kép để shell chuyển nó thành một đối số duy nhất:

```bash
java LineViewer.java "data/my notes.txt" --nonblank
```

Ví dụ này **chỉ đọc**, không thay đổi tệp nguồn. Khi xây dựng tiện ích xử lý dữ liệu thật, nên ưu tiên thiết kế có `--help`, thông báo lỗi rõ ràng, không ghi đè đầu vào và kiểm thử với tệp trống, tệp lớn, ký tự Unicode và đường dẫn có dấu cách.

## 3. Tổ chức một tiện ích nhỏ sao cho dễ duy trì

Ngay cả với một tệp, bạn vẫn nên tách ba trách nhiệm:

1. **Xác thực đầu vào:** số lượng và ý nghĩa các đối số; hiển thị cách dùng nếu sai.
2. **Thực thi công việc:** thao tác tệp, gọi API, biến đổi dữ liệu.
3. **Thông báo kết quả/lỗi:** stdout cho kết quả máy hoặc người có thể đọc; stderr cho lỗi; mã thoát cho shell nhận biết thành công hay thất bại.

Trong `LineViewer`, các phần này vẫn nằm chung lớp vì quy mô nhỏ. Khi logic lớn hơn, có thể tách phương thức như `parseArgs(...)` và `printMatchingLines(...)`, hoặc bổ sung kiểm thử. Không cần tạo nhiều lớp chỉ để đạt hình thức “enterprise”; nhưng cũng không để `main` tăng lên hàng trăm dòng khó kiểm tra.

### Tiêu chuẩn I/O và dữ liệu lớn

- `System.out`: dữ liệu/kết quả bình thường; có thể được chuyển hướng sang tệp bằng shell.
- `System.err`: lỗi và hướng dẫn sử dụng khi tham số sai.
- `StandardCharsets.UTF_8`: mã hóa cố định cho nội dung tệp, tránh kết quả khác nhau do charset mặc định của máy.
- `BufferedReader`: phù hợp đọc tuần tự; cách này tiết kiệm bộ nhớ hơn `Files.readAllLines(...)` cho tệp rất lớn.
- `Path.of(...)`: API đường dẫn có từ Java 11; xử lý lỗi đường dẫn không hợp lệ trước khi cố đọc.
- Không in dữ liệu nhạy cảm từ log, mã truy cập hoặc thông tin cá nhân ra stdout trong công cụ dùng chung.

Khi tiện ích cần parse nhiều tùy chọn, có định dạng đầu ra cố định cho hệ thống khác, cần kiểm thử tự động liên tục, thư viện ngoài phức tạp, phân phối cho người dùng khác hoặc nhiều thành phần phụ thuộc nhau, hãy cân nhắc một dự án có cấu trúc cùng Gradle/Maven, test và quy trình đóng gói.

## 4. Thử nhanh API bằng một tệp Java riêng

Nhiều câu hỏi nhỏ không cần khởi tạo nguyên dự án: “`strip()` loại khoảng trắng ở biên ra sao?”, “`isBlank()` có trả về `true` với tab không?”, “hành vi này đúng trong phiên bản JDK mình đang dùng chứ?”.

**Tệp: `ApiProbe.java`** (Java 11+)

```java
public class ApiProbe {
    public static void main(String[] args) {
        String raw = "  Java  ";

        if (!"Java".equals(raw.strip())) {
            throw new AssertionError(
                    "strip() returned an unexpected value");
        }

        if (!" \t ".isBlank()) {
            throw new AssertionError(
                    "isBlank() returned an unexpected value");
        }

        System.out.println("API checks passed");
    }
}
```

Chạy:

```bash
java ApiProbe.java
```

Stdout chính xác:

```text
API checks passed
```

Tại sao đây là một thử nghiệm có ích?

- `String.strip()` và `String.isBlank()` là API Java 11; ví dụ không cần dependency.
- Thay vì chỉ in giá trị và tự đoán, hai điều kiện ném `AssertionError` nếu giả định sai. Nếu chạy đến thông báo cuối cùng, hai điều kiện đã đúng với input kiểm tra.
- Thử nghiệm này **không thay thế bộ kiểm thử chính thức**: nó chỉ kiểm tra hai trường hợp cụ thể. Muốn kiểm chứng hành vi tổng quát, nên thử nhiều dữ liệu đầu vào và viết kiểm thử tự động phù hợp.
- Khác với câu lệnh `assert` của Java, cách `if (...) throw new AssertionError(...)` ở đây **không phụ thuộc** tùy chọn JVM `-ea` để thực hiện kiểm tra.

Bạn có thể thay nội dung bằng một thí nghiệm khác về `HttpClient`, `Path`, collection hoặc stream; ưu tiên input có thể tái tạo và tránh dùng mạng, dữ liệu bên ngoài hay thời gian thực nếu chúng không cần thiết cho giả định đang thử.

## 5. Hiểu thứ tự đối số của launcher

Cú pháp chung:

```text
java [JVM/launcher options] SourceFile.java [program arguments]
```

Ví dụ:

```bash
java -Xmx256m LineViewer.java notes.txt --nonblank
```

- `-Xmx256m` nằm **trước tên tệp**, nên được launcher/JVM xử lý.
- `notes.txt` và `--nonblank` nằm **sau tên tệp**, nên được chuyển vào `main(String[] args)`.
- Nếu đưa một tùy chọn JVM như `-Xmx256m` sau tên tệp, nó trở thành đối số ứng dụng; chương trình không tự coi nó là cấu hình JVM.

Khi cần kiểm tra khả năng biên dịch theo nguồn/API Java 11 trên một JDK mới hơn có hỗ trợ mức 11, có thể dùng:

```bash
java --source 11 ApiProbe.java
```

`--source 11` đặt mức ngôn ngữ và API được phép dùng khi biên dịch trong source-file mode. Các phiên bản JDK tương lai có thể thay đổi tập mức `--source` được hỗ trợ; kiểm tra trợ giúp `java --help` hoặc `javac --help` trên JDK đang cài. Với chương trình của bài này, `java ApiProbe.java` đủ khi đã chạy trên JDK 11+ phù hợp.

### Thư viện ngoài và classpath

Việc chạy trực tiếp từ nguồn **không cấm** sử dụng lớp từ thư viện đã có. Nếu nguồn phụ thuộc JAR đã chuẩn bị sẵn, có thể đặt `--class-path`/`-cp` trước tên tệp nguồn, chẳng hạn:

```bash
java --class-path "lib/*" MyTool.java
```

Dòng này chỉ minh họa cách truyền classpath; `MyTool.java` và các JAR trong `lib/` phải thực sự tồn tại thì mới chạy được. Source-file mode không tự tải và quản lý các dependency như công cụ build. Khi phụ thuộc phức tạp, nên dùng công cụ build để đảm bảo phiên bản và cách chạy có thể tái tạo.

## 6. Cập nhật kiến thức cho các Java hiện đại

Tính năng nền tảng **chạy thẳng `java File.java` từ Java 11 vẫn đang được hỗ trợ**. Hai điểm phát triển về sau giúp tránh hiểu sai giới hạn cũ:

- **Java 22 — JEP 458 (chính thức):** launcher có thể tìm và biên dịch thêm những tệp nguồn liên quan trong cây thư mục nguồn khi chạy một tệp đầu vào. Vì vậy nhận định “launcher hiện nay tuyệt đối chỉ chạy được một tệp Java” là không chính xác. Dù vậy, bài này dùng **một tệp** để giữ quá trình học và tiện ích đơn giản, tương thích Java 11.
- **Java 25 — JEP 512 (chính thức):** hỗ trợ compact source files và instance main methods, cho phép các chương trình rất nhỏ có cú pháp điểm vào gọn hơn. Đây là khả năng bổ sung của JDK hiện đại. Cú pháp lớp thường và `public static void main(String[] args)` trong hai ví dụ vẫn hợp lệ và không cần chuyển đổi.

Các mở rộng của Java 22/25 không khiến cách dùng từ Java 11 trở thành “legacy” cần bỏ. Khi triển khai đa phiên bản, chọn cú pháp và API theo JDK **thấp nhất cần hỗ trợ**; tránh vô tình sao chép ví dụ chỉ chạy trên Java 25 vào dự án phải chạy Java 11.

## 7. Phân biệt các công cụ khi học và làm việc

| Nhu cầu | Công cụ hợp lý | Vì sao |
| --- | --- | --- |
| Thử một biểu thức hay vài câu lệnh tương tác | `jshell` | Có REPL, không cần tạo tệp nguồn đầy đủ |
| Chạy nhanh tiện ích nhỏ có `main`, tham số và file I/O | `java Tool.java ...` | Một lệnh để biên dịch và chạy từ nguồn |
| Muốn kiểm soát biên dịch và lấy `.class`/artifact | `javac` rồi `java` | Các giai đoạn rõ ràng |
| Ứng dụng có kiểm thử, dependencies, đóng gói hoặc CI | Gradle/Maven + JDK | Tổ chức và tái tạo build dễ hơn |

Không có một công cụ nào luôn tốt hơn: hãy chọn theo quy mô và nhu cầu có thể tái lập.

## 8. Lỗi thường gặp và cách sửa

1. **Gõ `java LineViewer` khi chưa biên dịch.** Đây là cách chạy một lớp đã biên dịch; để chạy nguồn hãy dùng `java LineViewer.java`.
2. **Chạy trên môi trường không có JDK phù hợp.** Kiểm tra `java -version` và JDK của terminal/IDE. Source-file mode cần công cụ biên dịch của JDK.
3. **Đặt tùy chọn JVM sau tên tệp.** Launcher chuyển phần sau `LineViewer.java` cho ứng dụng; hãy đưa tùy chọn JVM lên trước.
4. **Quên kiểm tra `args`.** Truy cập `args[0]` khi không truyền gì sẽ gây `ArrayIndexOutOfBoundsException`; ví dụ đã kiểm tra đầu vào trước.
5. **Bỏ qua việc đóng stream/reader.** Dùng `try-with-resources` để tránh giữ file handle sau khi hoàn thành hoặc gặp lỗi.
6. **Cho rằng mọi tệp văn bản đều UTF-8.** Tiện ích này **quy định UTF-8**. Nếu nguồn dùng charset khác, cần chọn và công bố charset thích hợp; không lặng lẽ giả định dữ liệu đầu vào luôn giống nhau.
7. **Dùng source-file mode để thay build cho chương trình lớn.** Launcher tiện cho việc nhỏ, nhưng không tự quản lý test, version dependency, packaging hay quy trình release.
8. **Nhầm Java 11 với giới hạn của Java 22/25.** Tính năng đã được mở rộng; khi viết tài liệu, nêu rõ phiên bản phát hành tính năng thay vì khẳng định các giới hạn cũ còn đúng với mọi JDK.
9. **Tin tuyệt đối vào một lần chạy thử.** Một input thành công chỉ chứng minh trường hợp đã thử; thêm input lỗi, biên, file rỗng, file dài và kiểm thử tự động khi mã quan trọng.

## 9. Bài thực hành để tự xác minh

Sau khi chạy được hai chương trình mẫu:

1. Tạo `empty.txt` rỗng và dự đoán kết quả `java LineViewer.java empty.txt --nonblank`. Kết quả mong đợi: chỉ có `Shown: 0`.
2. Thêm một dòng chỉ có dấu cách vào `notes.txt`, chạy có/không có `--nonblank` và quan sát số dòng gốc được giữ ra sao.
3. Đổi đường dẫn đầu vào thành tệp không tồn tại; kiểm tra stderr và mã kết thúc bằng lệnh phù hợp với shell (PowerShell: `$LASTEXITCODE`; bash/zsh: `echo $?`).
4. Thay giả định trong `ApiProbe` bằng một điều kiện cố ý sai để thấy `AssertionError`, rồi sửa lại.
5. Tách phần xử lý dòng ra một phương thức riêng trong cùng `LineViewer.java` mà không cần tạo dự án build.

**Tiêu chí hoàn thành:** bạn có thể giải thích nguồn nào được biên dịch, đối số nào đi vào `args`, vì sao tài nguyên được đóng, stdout/stderr khác nhau ở đâu và khi nào công cụ nhỏ cần nâng cấp thành dự án.

## Tài liệu chính thức

- [OpenJDK JEP 330 — Launch Single-File Source-Code Programs](https://openjdk.org/jeps/330): cơ sở tính năng Java 11.
- [Dev.java — Launching Simple Source-Code Programs](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/): chạy chương trình nguồn, tham số, thư viện và mở rộng nhiều tệp.
- [Oracle Java 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp launcher và source-file mode hiện đại.
- [OpenJDK JEP 458 — Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458): mở rộng trong Java 22.
- [OpenJDK JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): điểm vào và kiểu tệp nguồn rút gọn trong Java 25.