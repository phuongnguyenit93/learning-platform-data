# Tổ chức ví dụ Java 7 trên một JDK còn được hỗ trợ

## 1. Mục tiêu và phạm vi

Trong module Java 7, tên phiên bản cho biết **thời điểm một tính năng xuất hiện**, không có nghĩa phải cài hoặc chạy Java 7 để học tính năng đó. Cách học có giá trị hiện nay là dùng một **JDK đang được nhà cung cấp cập nhật bảo mật**, rồi thực hành những cơ chế vẫn tồn tại và còn được sử dụng trong Java hiện đại.

Sau bài này, bạn có thể:

- Chọn và xác minh JDK dùng để biên dịch, chạy và kiểm thử ví dụ.
- Sắp xếp ví dụ theo cấu trúc thư mục, tên lớp, yêu cầu đầu vào và kết quả đầu ra nhất quán.
- Viết một chương trình độc lập dùng `try-with-resources` và `java.nio.file`, hai khả năng xuất hiện từ Java 7 nhưng vẫn hữu ích.
- Hiểu sự khác nhau giữa **JDK biên dịch**, **mức Java đích** và **JDK chạy**, tránh ví dụ hoạt động trên máy tác giả nhưng thất bại ở môi trường khác.
- Dùng lệnh `javac`/`java` hoặc Java toolchain của Gradle để chạy lại một cách có thể kiểm chứng.

**Lựa chọn cho bài thực hành:** JDK **21 LTS** với mức biên dịch `--release 21`. Tính đến tháng 11/2026, JDK 25 là bản LTS mới hơn; JDK 21 vẫn là một nhánh LTS. Việc một bản cài đặt còn được hỗ trợ phụ thuộc **nhà phân phối, hệ điều hành và lịch cập nhật**: kiểm tra chính sách của nhà cung cấp, dùng bản vá hiện hành và nâng cấp theo chính sách dự án. Không cần dựng môi trường Java 7 cũ cho bài học này.

## 2. Xác minh môi trường trước khi chạy

Cài **JDK**, không chỉ runtime, từ nguồn phát hành được tổ chức tin cậy và còn cung cấp bản vá. Mở terminal mới rồi kiểm tra:

~~~sh
java --version
javac --version
~~~

Hai lệnh phải chạy được; phiên bản được chọn phải phù hợp với mức biên dịch của ví dụ. Để xác định lệnh nào đang nằm trên `PATH`:

~~~powershell
# Windows PowerShell
where.exe java
where.exe javac
~~~

~~~sh
# Linux/macOS
command -v java
command -v javac
~~~

Nếu có nhiều JDK, kiểm tra cả cấu hình JDK trong IDE và Gradle toolchain; đừng kết luận IDE, terminal và Gradle chắc chắn dùng cùng một JDK chỉ vì một lệnh `java --version` thành công. `JAVA_HOME` và `PATH` cũng cần trỏ đến cài đặt mong muốn nếu công cụ đang dựa vào chúng. Khi thay đổi JDK hoặc bản vá, chạy lại ví dụ và kiểm thử.

Phân biệt ba khái niệm:

| Thành phần | Vai trò | Ví dụ của bài |
| --- | --- | --- |
| JDK biên dịch | Cung cấp `javac` và công cụ phát triển | JDK 21 có bản vá hiện hành |
| Mức Java đích (`--release`) | Giới hạn cú pháp, API nền tảng và phiên bản bytecode được biên dịch | 21 |
| JDK chạy | Thực thi chương trình đã biên dịch | JDK 21 tương thích |

Có thể dùng một JDK mới hơn để biên dịch với `--release 21` nếu trình biên dịch hỗ trợ mức đó. Ngược lại, chương trình được biên dịch cho Java 21 không thể mặc nhiên chạy trên runtime Java 17. `--release` cũng không thay thế việc kiểm thử trên runtime thực tế, nhất là khi có thư viện ngoài, native code hoặc khác biệt hệ điều hành.

## 3. Tổ chức một ví dụ thành đơn vị học độc lập

Mẫu tối thiểu cho bài học này:

~~~text
jdk-examples/
├── README.md
└── src/
    └── main/
        └── java/
            └── demo/
                └── JdkSupportExample.java
~~~

Khi dự án cần kiểm thử tự động, có thể bổ sung `src/test/java/demo/`; khi sử dụng Gradle, thêm `build.gradle` và Gradle Wrapper do dự án quản lý. Thư mục `out/` từ lệnh biên dịch thủ công là sản phẩm sinh ra, không phải mã nguồn cần lưu vào Git.

Quy tắc tổ chức lâu dài:

1. **Mỗi ví dụ có một mục tiêu rõ ràng.** Tên lớp, package và tên file khớp nhau; không dồn nhiều tình huống độc lập vào một `main` lớn.
2. **Có lệnh chạy lại và stdout dự kiến.** Ghi cụ thể phiên bản JDK/mức `--release` và thư mục phải đứng khi thực thi.
3. **Đầu vào chủ động và an toàn.** Ưu tiên chuỗi cố định, dữ liệu mẫu hoặc file tạm; không đòi tài khoản, bí mật, dịch vụ mạng hay đường dẫn tuyệt đối trên máy người viết.
4. **Tách phần cốt lõi khỏi tiện ích hiện đại.** Nếu đang minh họa khả năng có từ Java 7, nêu rõ phần nào là tính năng chính và phần nào là API mới hơn giúp viết ví dụ gọn hơn.
5. **Dọn tài nguyên và giữ tính lặp lại.** Đóng luồng, giải phóng file tạm, không phụ thuộc thứ tự chạy của các ví dụ khác.

## 4. Ví dụ Java hoàn chỉnh: thao tác file và tự đóng tài nguyên

Tạo file `src/main/java/demo/JdkSupportExample.java` với nội dung:

~~~java
package demo;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class JdkSupportExample {
    private JdkSupportExample() {
    }

    public static void main(String[] args) throws IOException {
        Path tempFile = Files.createTempFile("java7-lesson-", ".txt");

        try {
            Files.writeString(tempFile, "first\nsecond\n", StandardCharsets.UTF_8);

            try (BufferedReader reader =
                         Files.newBufferedReader(tempFile, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }
}
~~~

Từ thư mục `jdk-examples/`, biên dịch và chạy bằng JDK hỗ trợ `--release 21`:

~~~sh
javac --release 21 -encoding UTF-8 -d out src/main/java/demo/JdkSupportExample.java
java -cp out demo.JdkSupportExample
~~~

Hai câu lệnh `javac` và `java` ở trên cũng dùng được trong PowerShell nếu JDK đã nằm trên `PATH`. Kết quả stdout dự kiến, đúng thứ tự và không in đường dẫn file tạm:

~~~text
first
second
~~~

**Giải thích theo luồng thực thi:**

1. `Files.createTempFile` tạo file trong vùng tạm được hệ điều hành quản lý, trả về `Path`; chương trình không cần biết thư mục tạm cụ thể.
2. `Files.writeString` ghi dữ liệu với `UTF-8`. Đây là API hiện đại (có từ Java 11), được dùng có chủ đích vì bài chạy trên JDK còn được hỗ trợ; **không gán nhầm API này cho Java 7**.
3. `Files.newBufferedReader` mở trình đọc với charset tường minh. `try-with-resources` bảo đảm `reader.close()` được gọi khi rời khối `try`, kể cả khi đọc phát sinh lỗi. Cả NIO.2 và `try-with-resources` đều là các khả năng giới thiệu trong Java 7 và vẫn được dùng.
4. Vòng lặp in từng dòng cho đến `null` (kết thúc file). `finally` xóa file tạm sau khi trình đọc đã đóng; `deleteIfExists` tránh lỗi chỉ vì file không còn tồn tại. Nếu thao tác I/O thất bại, `IOException` được báo lên người chạy thay vì bị nuốt.
5. Chương trình không phụ thuộc network, múi giờ, thư viện bên thứ ba hoặc đường dẫn cá nhân. Tên file tạm có thể thay đổi giữa các lần chạy nhưng stdout không đổi.

**Điểm cần hiểu:** `try-with-resources` quản lý vòng đời đối tượng `AutoCloseable`, còn `finally` trong ví dụ quản lý vòng đời **file tạm trên hệ thống**. Đóng luồng không đồng nghĩa tự xóa file. Khi có nhiều tài nguyên trong cùng một `try-with-resources`, Java đóng chúng theo thứ tự ngược với thứ tự khai báo.

## 5. Khi chuyển từ một file sang dự án Gradle

Với nhiều ví dụ, test hoặc dependency, hãy quản lý JDK qua **Java toolchain** để thành viên trong nhóm dùng cùng mức Java khi build. Ví dụ cấu hình `build.gradle` độc lập (Groovy DSL):

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.JdkSupportExample'
}
~~~

Đặt Java source vào cùng cấu trúc `src/main/java/demo/` như trên. Với Gradle Wrapper đã được dự án cấu hình ở phiên bản tương thích JDK 21:

~~~sh
# Linux/macOS
./gradlew run
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat run
~~~

Toolchain chọn trình biên dịch/JDK theo yêu cầu của dự án; `options.release` giới hạn phiên bản Java của mã biên dịch. Chúng giải quyết **hai việc khác nhau**. Một số môi trường cần cấu hình nguồn cung cấp JDK cho Gradle toolchain nếu JDK yêu cầu chưa có sẵn. Dùng wrapper của dự án giúp thống nhất phiên bản Gradle, nhưng vẫn cần xác minh phiên bản Gradle ấy hỗ trợ JDK sử dụng.

Trong dự án nhiều bài, mỗi chương trình có thể là một lớp `main` riêng. Chỉ định `application.mainClass` cho bài muốn chạy, hoặc tạo task chạy riêng cho từng ví dụ; không buộc nhiều `main` cùng thực thi và không để logic chương trình phụ thuộc vào thứ tự các bài.

## 6. Kiểm tra tương thích và tránh lỗi phổ biến

| Tình huống | Cách xử lý phù hợp hiện nay |
| --- | --- |
| Muốn minh họa một tính năng xuất hiện ở Java 7 | Nêu rõ tính năng đó, chạy trên JDK đang được vá; dùng API hiện đại khác khi chúng chỉ đóng vai trò hỗ trợ |
| Terminal chạy được nhưng IDE/Gradle lỗi | So sánh JDK của terminal, IDE và toolchain; kiểm tra cả mức `--release` |
| Compile thành công, runtime báo `UnsupportedClassVersionError` | Kiểm tra phiên bản bytecode/JDK chạy; dùng runtime tương thích hoặc chọn mức biên dịch đúng yêu cầu |
| Dùng API mới nhưng hạ `--release` thấp hơn | Trình biên dịch phải báo lỗi; thay API bằng cách được hỗ trợ tại mức đích hoặc nâng mức đích có chủ đích |
| File xuất hiện ký tự sai | Dùng charset tường minh, nguồn UTF-8 và kiểm tra encoding của terminal |
| File tạm còn tồn tại hoặc bị khóa | Đóng tài nguyên bằng `try-with-resources`; chỉ xóa file do chương trình tạo và thực hiện cleanup sau khi đóng |
| Ví dụ chỉ chạy trên máy người viết | Bỏ đường dẫn tuyệt đối, thông tin bí mật và giả định về thư mục hiện tại; mô tả chính xác lệnh chạy |

Những thành phần Java 7 **vẫn hữu ích** để học trên JDK hiện đại gồm `try-with-resources`, NIO.2 (`Path`, `Files`), `multi-catch` và cú pháp generic diamond (`<>`). Chỉ chọn chúng khi phục vụ mục tiêu bài; không phục dựng cấu hình JVM, API nội bộ hoặc kỹ thuật đã lỗi thời chỉ để làm cho ví dụ giống môi trường phát hành cũ.

## 7. Checklist cho từng ví dụ trước khi đưa vào bộ bài học

- [ ] Mục tiêu bài và phiên bản Java mục tiêu được mô tả rõ.
- [ ] JDK có hỗ trợ cập nhật từ nhà cung cấp; `java` và `javac`/Gradle toolchain được xác minh.
- [ ] Package, tên file và lớp `public` khớp nhau; lệnh build và chạy xuất phát từ thư mục đã ghi.
- [ ] Mã dùng API được hỗ trợ ở mức `--release` đã chọn; không phụ thuộc API nội bộ.
- [ ] Chạy lại cho stdout hoặc phép kiểm thử đúng như README; tài nguyên I/O được đóng.
- [ ] Không cần credential, host mạng, file cá nhân hay tác động tới dữ liệu thật.
- [ ] Nếu ví dụ dùng API mới hơn Java 7, đã chú thích rõ để tránh nhầm mốc ra đời.
- [ ] Có thể thay phiên bản JDK hỗ trợ theo chính sách dự án mà vẫn giữ mục tiêu học tập và chạy lại kiểm thử.

**Tài liệu chính thức để kiểm chứng khi cập nhật bài:**

- Oracle Java SE Support Roadmap: https://www.oracle.com/java/technologies/java-se-support-roadmap.html
- Tùy chọn `javac --release` (JDK 21): https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Gradle Java toolchains: https://docs.gradle.org/current/userguide/toolchains.html

Hãy xem lịch hỗ trợ của **nhà cung cấp JDK cụ thể** trước mỗi lần chọn hoặc nâng phiên bản; tài liệu đào tạo không nên đóng đinh một số phiên bản thành bảo đảm hỗ trợ vĩnh viễn.