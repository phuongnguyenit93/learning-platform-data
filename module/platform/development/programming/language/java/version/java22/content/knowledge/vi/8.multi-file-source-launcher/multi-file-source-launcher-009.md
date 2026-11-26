# Tổ chức tiện ích dòng lệnh cùng ví dụ học tập gồm nhiều tệp

## Chạy chương trình Java nhiều tệp bằng source-file mode

Trong module `JAVA_VERSION_JAVA22`, nội dung này tập trung vào những tính năng được giới thiệu ở Java 22 và vẫn hữu ích trên JDK hiện đại. JEP 458 mở rộng source-file mode của lệnh `java`, vốn đã có từ JDK 11, để launcher tự tìm và biên dịch những tệp nguồn Java khác mà chương trình cần. Tính năng này được phát hành chính thức trong JDK 22; đây là khả năng ổn định của Java launcher, không phải preview hay incubator.

Trước JDK 22, source-file mode chủ yếu phù hợp với chương trình nằm trong một tệp. Từ JDK 22, có thể chia một tiện ích nhỏ thành nhiều tệp theo trách nhiệm, rồi chạy tệp chứa điểm vào bằng một lệnh `java`. Launcher biên dịch mã nguồn trong bộ nhớ và tự tìm các source file phụ thuộc trong cây thư mục nguồn.

Ví dụ trong bài xây dựng tiện ích dòng lệnh đếm số dòng, số từ và số ký tự của một tệp văn bản. Chương trình được tách thành các phần phân tích đối số, xử lý tệp, định dạng báo cáo và điểm vào `main`.

## 1. Source-file mode hoạt động như thế nào?

Khi đối số đầu tiên trên dòng lệnh không phải option là một đường dẫn đến tệp `.java` đang tồn tại, launcher chọn source-file mode. Launcher biên dịch tệp đó cùng các source file khác cần thiết trong source tree, sau đó chạy lớp đầu tiên được khai báo ở cấp cao nhất trong tệp nguồn được chỉ định. Lớp này phải có entry point `main` hợp lệ.

Ví dụ đơn giản:

```bash
java Hello.java
```

Với chương trình nhiều tệp, vẫn chỉ định tệp chứa `main`:

```bash
java src/com/example/cli/Main.java
```

Nếu `Main.java` tham chiếu đến `Arguments`, `WordCounter` và `ReportFormatter`, launcher có thể tìm các tệp nguồn tương ứng trong cây nguồn và biên dịch chúng cùng chương trình. Không cần gọi `javac` trước hoặc tự liệt kê tất cả tệp `.java` trên dòng lệnh.

Source-file mode có thể hiểu gần đúng như quy trình biên dịch vào một vùng lưu trữ tạm trong bộ nhớ rồi chạy các class vừa biên dịch. Đây là mô hình giải thích; người dùng không cần tạo thư mục `classes` hay quản lý các tệp `.class` cho lần chạy này.

## 2. Tổ chức thư mục và package

Launcher xác định source root từ package của lớp được khởi chạy. Các thư mục bên dưới source root phải phản ánh cấu trúc package. Ví dụ, nếu `Main.java` khai báo `package com.example.wordcount;` và nằm ở `src/com/example/wordcount/`, source root là `src/`.

Cấu trúc tiện ích đếm từ:

```text
wordcount/
├── data/
│   └── sample.txt
└── src/
    └── com/
        └── example/
            └── wordcount/
                ├── Main.java
                ├── Arguments.java
                ├── WordCounter.java
                └── ReportFormatter.java
```

Tất cả bốn tệp nguồn khai báo cùng package `com.example.wordcount`. Cách tổ chức này giữ các lớp cùng một package để có thể gọi nhau trực tiếp và làm cho đường dẫn nguồn dễ dự đoán.

Quy tắc quan trọng:

- Nếu lớp khởi chạy có khai báo package, đường dẫn của tệp phải phản ánh package đó; launcher đi ngược các thành phần package để tìm source root.
- Nếu lớp thuộc unnamed package, thư mục chứa tệp khởi chạy là source root.
- Các source file phụ thuộc phải nằm trong cây nguồn bắt đầu từ source root và ở vị trí phù hợp với package của chúng.
- Launcher chỉ cần biên dịch các source file mà chương trình tham chiếu; không nên hiểu rằng mọi tệp trong thư mục đều được biên dịch vô điều kiện.

## 3. Xây dựng tiện ích CLI gồm nhiều tệp

### Tệp `Arguments.java`

Lớp này kiểm tra và chuyển đối số dòng lệnh thành dữ liệu có kiểu. Ví dụ yêu cầu đúng một đường dẫn tệp đầu vào:

```java
package com.example.wordcount;

import java.nio.file.Path;

public record Arguments(Path inputFile) {
    public static Arguments parse(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Cach dung: java Main.java <tep-can-dem>"
            );
        }

        return new Arguments(Path.of(args[0]));
    }
}
```

`record` phù hợp để biểu diễn dữ liệu đầu vào nhỏ, bất biến. `Path.of(...)` tạo đường dẫn từ chuỗi người dùng nhập.

### Tệp `WordCounter.java`

Lớp này đảm nhận việc đọc tệp UTF-8 và tính các thống kê. Số ký tự trong ví dụ được tính theo Unicode code point và không tính ký tự xuống dòng:

```java
package com.example.wordcount;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class WordCounter {
    private WordCounter() { }

    public record Counts(long lines, long words, long characters) { }

    public static Counts count(Path file) throws IOException {
        long lines = 0;
        long words = 0;
        long characters = 0;

        try (BufferedReader reader = Files.newBufferedReader(
                file, StandardCharsets.UTF_8)) {
            String line;

            while ((line = reader.readLine()) != null) {
                lines++;
                characters += line.codePointCount(0, line.length());

                String content = line.strip();
                if (!content.isEmpty()) {
                    words += content.split("\\s+").length;
                }
            }
        }

        return new Counts(lines, words, characters);
    }
}
```

`try-with-resources` bảo đảm reader được đóng sau khi đọc xong hoặc khi xảy ra lỗi. `readLine()` loại bỏ ký tự kết thúc dòng, vì vậy bộ đếm ký tự ở đây không cộng `\n` hay `\r\n`. Cách tách từ dùng chuỗi khoảng trắng theo biểu thức chính quy `\\s+`, phù hợp cho ví dụ học tập; ứng dụng xử lý ngôn ngữ tự nhiên cần quy tắc tách từ chuyên biệt hơn.

### Tệp `ReportFormatter.java`

Tách phần trình bày kết quả khỏi logic đọc tệp:

```java
package com.example.wordcount;

import java.nio.file.Path;

public final class ReportFormatter {
    private ReportFormatter() { }

    public static String format(Path file, WordCounter.Counts counts) {
        return "Tệp: " + file + System.lineSeparator()
            + "Số dòng: " + counts.lines() + System.lineSeparator()
            + "Số từ: " + counts.words() + System.lineSeparator()
            + "Số ký tự (Unicode code point, không tính xuống dòng): "
            + counts.characters();
    }
}
```

### Tệp `Main.java`

Đây là lớp điểm vào kết nối các thành phần:

```java
package com.example.wordcount;

import java.io.IOException;

public final class Main {
    private Main() { }

    public static void main(String[] args) {
        try {
            Arguments arguments = Arguments.parse(args);
            WordCounter.Counts counts = WordCounter.count(arguments.inputFile());
            System.out.println(
                ReportFormatter.format(arguments.inputFile(), counts)
            );
        } catch (IllegalArgumentException e) {
            System.err.println(e.getMessage());
            System.exit(2);
        } catch (IOException e) {
            System.err.println("Khong doc duoc tep: " + e.getMessage());
            System.exit(1);
        }
    }
}
```

Mỗi lớp có một trách nhiệm rõ ràng. Launcher tự phát hiện các phụ thuộc `Arguments`, `WordCounter` và `ReportFormatter` khi biên dịch `Main.java`.

## 4. Chạy chương trình và truyền đối số

Đứng tại thư mục `wordcount/`, chạy:

```bash
java src/com/example/wordcount/Main.java data/sample.txt
```

Đường dẫn `src/com/example/wordcount/Main.java` xác định tệp nguồn cần khởi chạy. Mọi đối số đứng sau tệp nguồn được truyền vào `main(String[] args)`, vì vậy `data/sample.txt` trở thành `args[0]`.

Nếu `data/sample.txt` có nội dung:

```text
Hello Java
Source launcher
```

Kết quả sẽ có dạng:

```text
Tệp: data/sample.txt
Số dòng: 2
Số từ: 4
Số ký tự (Unicode code point, không tính xuống dòng): 25
```

Nếu đường dẫn có dấu cách, đặt nó trong dấu nháy theo shell đang dùng:

```bash
java src/com/example/wordcount/Main.java "data/my notes.txt"
```

Khi không truyền đúng số đối số, tiện ích in hướng dẫn sử dụng và kết thúc với mã thoát `2`. Khi không đọc được tệp, chương trình in thông báo lỗi và kết thúc với mã `1`.

## 5. Dùng thư viện bên ngoài

Source-file mode hỗ trợ các tùy chọn ảnh hưởng đến môi trường biên dịch như `--class-path` và `--module-path`. Đặt các tùy chọn này **trước** đường dẫn tệp nguồn:

```bash
java --class-path "lib/*" \
     src/com/example/wordcount/Main.java \
     data/sample.txt
```

Trong ví dụ, các JAR trong `lib/` được thêm vào class path để các source file có thể tham chiếu đến lớp thư viện đã biên dịch. Trên Windows, ký tự phân tách nhiều phần tử class path là dấu chấm phẩy (`;`); trên Linux và macOS là dấu hai chấm (`:`). Dạng wildcard `lib/*` được launcher mở rộng thành các JAR trong thư mục đó.

Các tùy chọn liên quan đến runtime và biên dịch cần xuất hiện trước tệp nguồn để launcher có thể xử lý. Những đối số sau tệp nguồn được dành cho chương trình, không phải tùy chọn của compiler.

## 6. Dùng module-info.java khi cần module

Nếu `module-info.java` nằm ngay tại source root, launcher dùng khai báo module đó cho các lớp được biên dịch trong source tree. Ví dụ cấu trúc:

```text
wordcount/
└── src/
    ├── module-info.java
    └── com/example/wordcount/
        ├── Main.java
        ├── Arguments.java
        ├── WordCounter.java
        └── ReportFormatter.java
```

Nội dung `src/module-info.java`:

```java
module com.example.wordcount {
    // Các package không cần export nếu chỉ dùng trong module này.
}
```

Khi có `module-info.java`, các source file trong source tree được biên dịch trong module được khai báo. Khi không có tệp này, các lớp được biên dịch trong unnamed module. Cơ chế này hữu ích cho ví dụ một module nhỏ; nếu dự án cần biên dịch nhiều module nguồn độc lập, hãy dùng quy trình module source path của `javac` hoặc build tool phù hợp.

## 7. Giới hạn cần biết

Source-file mode được thiết kế cho việc chạy nhanh chương trình từ mã nguồn. Nó không thay thế toàn bộ quy trình build của một ứng dụng lớn.

| Giới hạn | Ảnh hưởng thực tế |
| --- | --- |
| Annotation processing bị tắt, tương đương `-proc:none` | Các processor như công cụ sinh mã không chạy trong source-file mode. Nếu chương trình cần mã được sinh lúc biên dịch, hãy dùng `javac` hoặc build tool. |
| Không truyền được mọi tùy chọn riêng của compiler | Launcher chỉ xử lý các tùy chọn biên dịch được hỗ trợ trong source-file mode; không có cơ chế truyền tùy chọn như `-processor` hoặc `-Werror`. |
| Source tree được xác định từ package của tệp khởi chạy | Các source file phụ thuộc phải nằm trong cây đó và theo cấu trúc package. Đây không phải cơ chế tự tìm mã nguồn ở mọi thư mục trong repository. |
| Các lớp biên dịch được nạp bằng custom class loader | Class có sẵn trên application class path không thể tham chiếu ngược đến lớp chỉ được biên dịch từ source file trong lần chạy đó. |
| Trùng tên lớp khởi chạy trên application class path gây lỗi | Tránh để một class cùng tên với lớp được khởi chạy tồn tại trên class path. |
| Source tree chỉ được gom vào một module qua `module-info.java` tại source root | Dự án nhiều module cần quy trình biên dịch module đầy đủ. |

Nếu chương trình cần annotation processor, nhiều module nguồn, kiểm soát đầy đủ compiler flags, kiểm thử tự động, dependency locking hoặc tạo artifact phát hành, hãy dùng `javac` kết hợp Maven/Gradle hay hệ thống build của dự án. Source-file mode vẫn hữu ích để thử nghiệm, minh họa, script nội bộ và tiện ích CLI nhỏ.

## 8. Chọn source version trên JDK hiện hành

Mặc định, source-file mode biên dịch theo phiên bản JDK đang chạy. Có thể dùng `--source N` trước tệp nguồn để giới hạn phiên bản ngôn ngữ và API theo một release cụ thể:

```bash
java --source 27 src/com/example/wordcount/Main.java data/sample.txt
```

Ví dụ trên dành cho JDK 27. Tập giá trị `N` được hỗ trợ thay đổi theo từng JDK; các bản JDK mới chỉ giữ một số release trước đó. Vì vậy, khi chạy trên JDK khác, hãy kiểm tra `java --help` hoặc tài liệu `javac` của chính phiên bản đó thay vì mặc định rằng `--source 22` luôn còn được hỗ trợ. Tính năng multi-file source launch từ JDK 22 vẫn là tính năng stable; ví dụ trong bài chỉ dùng cú pháp và API Java đã được hoàn thiện, không phụ thuộc preview hoặc incubator.

## 9. Khi nào nên dùng multi-file source launcher?

| Tình huống | Cách phù hợp |
| --- | --- |
| Bài học có vài lớp tách riêng để thể hiện package và trách nhiệm | Chạy bằng `java path/to/Main.java`. |
| Tiện ích CLI nội bộ cần chạy từ source mà không tạo bước build riêng | Dùng source-file mode nếu không cần annotation processing hoặc build phức tạp. |
| Chương trình cần JAR phụ thuộc đã biên dịch | Thêm JAR bằng `--class-path` hoặc module bằng `--module-path`. |
| Dự án cần annotation processor, nhiều module nguồn, test và artifact phát hành | Dùng `javac` và build tool. |
| Chương trình cần triển khai lâu dài cho người dùng cuối | Build và đóng gói ứng dụng; không phụ thuộc vào việc người dùng có source tree và JDK để biên dịch khi chạy. |

## Kết luận

Multi-file source launcher giúp một chương trình Java nhỏ phát triển từ một tệp thành nhiều tệp mà không cần bước biên dịch thủ công trước mỗi lần chạy. Hãy đặt source file theo package, khởi chạy tệp chứa `main`, thêm dependency đã biên dịch bằng class path hoặc module path khi cần và hiểu rõ giới hạn về annotation processing, class loader cùng module. Với tiện ích CLI hoặc ví dụ học tập, đây là cách chạy gọn và trực tiếp; với ứng dụng cần build và phát hành có kiểm soát, hãy chuyển sang quy trình biên dịch và đóng gói đầy đủ.

## Tài liệu tham khảo

- [JEP 458: Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458)
- [The `java` Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Launching a Multi-File Program — dev.java](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/)
- [The `javac` Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
