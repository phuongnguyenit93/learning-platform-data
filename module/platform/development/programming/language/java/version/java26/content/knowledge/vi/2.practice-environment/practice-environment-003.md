# Biên dịch, chạy preview bằng cùng phiên bản JDK

Bài này thuộc module **JAVA_VERSION_JAVA26**, tập trung vào cách chuẩn bị môi trường để thực hành các cải tiến của Java 26 về HTTP, pattern matching, đồng thời có cấu trúc, Vector API, bảo mật và tối ưu JVM. Các ví dụ dưới đây dùng JDK 26. Trước khi thử một tính năng, cần xác định nó đã là tính năng chính thức, còn ở trạng thái preview hay thuộc một module incubator; mỗi trạng thái có cách bật và giới hạn tương thích khác nhau.

Mục tiêu là bảo đảm trình biên dịch, bộ chạy và công cụ kiểm thử dùng cùng feature release JDK. Đây là điều kiện quan trọng khi thử preview, vì mã bytecode phụ thuộc preview của một release chỉ chạy trên chính release đó.

## 1. Phân biệt trạng thái tính năng trước khi biên dịch

| Trạng thái | Ý nghĩa | Cách bật khi biên dịch | Cách bật khi chạy |
|---|---|---|---|
| Chính thức (final) | Đặc tả và API đã ổn định trong Java SE hoặc JDK | Thường dùng **--release 26** | Không cần cờ preview |
| Preview | Tính năng đã được triển khai để lấy phản hồi nhưng còn có thể thay đổi hoặc bị rút khỏi release sau | **--enable-preview --release 26** bằng javac của JDK 26 | **--enable-preview** bằng java của JDK 26 |
| Incubator | API nằm trong module thử nghiệm riêng; hợp đồng API chưa được cam kết ổn định | Thêm module bằng **--add-modules** | Thêm cùng module bằng **--add-modules** |

Java 26 có preview ngôn ngữ **Primitive Types in Patterns, instanceof, and switch (JEP 530)**. API **StructuredTaskScope** cũng được đánh dấu preview trong tài liệu API của JDK 26. Vì vậy, mã dùng các phần này cần bật preview ở cả bước biên dịch lẫn chạy.

Vector API nằm trong module **jdk.incubator.vector** và vẫn được đánh dấu là incubator trong tài liệu JDK 26. Nó cần được đưa vào module graph bằng **--add-modules jdk.incubator.vector**. Cờ này không thay thế **--enable-preview**, và bật preview cũng không tự động bật module incubator.

Không nên suy luận trạng thái chỉ từ tên chủ đề hoặc từ một bài viết cũ. Hãy kiểm tra JEP và tài liệu API của đúng phiên bản JDK đang dùng. Một tính năng từng là preview ở release trước có thể đã trở thành final, tiếp tục preview với thay đổi, hoặc bị loại bỏ.

## 2. Xác nhận compiler và runtime cùng dùng JDK 26

Trên Windows PowerShell, chạy:

    java --version
    javac --version
    Get-Command java, javac -All | Select-Object Name, Source
    $env:JAVA_HOME

Kết quả mong đợi là cả **java** và **javac** đều báo phiên bản 26.x. Hai lệnh cũng cần trỏ đến cùng thư mục cài đặt JDK. Chỉ nhìn số phiên bản là chưa đủ nếu máy có nhiều JDK 26 của các nhà cung cấp hoặc bản cài khác nhau.

**JAVA_HOME** nên trỏ đến thư mục gốc của JDK, còn thư mục **bin** của JDK đó cần đứng trước các đường dẫn Java khác trong **PATH**. Có thể đặt tạm trong cửa sổ PowerShell hiện tại như sau; thay giá trị mẫu bằng đường dẫn cài đặt thật:

    $env:JAVA_HOME = '<duong-dan-toi-jdk-26>'
    $env:Path = "$env:JAVA_HOME/bin;$env:Path"
    & (Join-Path $env:JAVA_HOME 'bin/java.exe') --version
    & (Join-Path $env:JAVA_HOME 'bin/javac.exe') --version

Trên Linux hoặc macOS, dùng **which -a java javac** để xem các executable được tìm thấy và kiểm tra **$JAVA_HOME**. Sau khi đổi JDK, mở terminal mới hoặc nạp lại cấu hình shell để tránh dùng giá trị PATH cũ.

Cần kiểm tra riêng các tiến trình do IDE hoặc build tool khởi chạy. JDK chạy IDE, JDK chạy Gradle/Maven, compiler toolchain, JVM chạy test và JVM chạy ứng dụng có thể là những cấu hình khác nhau. Việc terminal báo JDK 26 không chứng minh tất cả các tiến trình đó đều dùng JDK 26.

## 3. Biên dịch và chạy mã chỉ dùng tính năng chính thức

Với mã Java 26 không dùng preview hay incubator, dùng **--release 26**:

    javac --release 26 -encoding UTF-8 -d out src/Main.java
    java -cp out Main

**--release 26** đặt đồng thời quy tắc ngôn ngữ, phiên bản bytecode đích và tập API được phép sử dụng cho Java 26. Đây là lựa chọn phù hợp để biên dịch theo một release cụ thể. Không ghép **--release** với **--source** hoặc **--target** trong cùng lệnh.

Nếu lớp có khai báo package, hãy chạy bằng tên đầy đủ của lớp. Ví dụ lớp **demo.Main** được đặt trong **src/demo/Main.java**, sau khi biên dịch vào **out** thì chạy bằng:

    java -cp out demo.Main

Không bật preview cho toàn bộ dự án chỉ vì một bài thực hành có sử dụng preview. Giữ cấu hình mặc định cho phần mã final giúp phát hiện sớm việc vô tình phụ thuộc vào API chưa ổn định.

## 4. Biên dịch và chạy preview của JDK 26

Với mã dùng preview, thêm **--enable-preview** khi biên dịch và khi chạy:

    javac --enable-preview --release 26 -encoding UTF-8 -d out src/PreviewDemo.java
    java --enable-preview -cp out PreviewDemo

Cả hai lệnh phải được thực thi bằng JDK 26. Cờ ở bước biên dịch cho phép compiler chấp nhận cú pháp hoặc API preview của release 26. Cờ ở bước chạy cho phép JVM nạp các class phụ thuộc preview của release đó. Thiếu một trong hai bước sẽ dẫn đến lỗi tương ứng ở compile time hoặc runtime.

Ví dụ sau dùng primitive pattern trong **instanceof**, thuộc JEP 530 và đang ở trạng thái preview trong Java 26:

    public class PreviewDemo {
        public static void main(String[] args) {
            Object value = Integer.valueOf(42);

            if (value instanceof int number) {
                System.out.println("value = " + number);
            }
        }
    }

Lưu mã vào **src/PreviewDemo.java**, sau đó chạy hai lệnh ở trên. Khi compiler thông báo mã đang dùng preview language features, đó là dấu hiệu cần kiểm tra xem tính năng có đúng là preview và có chủ ý được bật hay không; không nên bỏ qua cảnh báo mà không đọc nội dung.

API preview cũng tuân theo quy tắc bật preview ở cả hai phía. Chẳng hạn, **StructuredTaskScope** trong JDK 26 được đánh dấu preview trong Java API Specification. Nếu một bài thực hành dùng API này, hãy biên dịch bằng javac 26 với **--enable-preview** và chạy bằng java 26 với cùng cờ.

Một class file phụ thuộc preview của Java SE 26 được gắn với release 26. Không thể chuyển class file đó sang một release khác rồi kỳ vọng nó chạy chỉ bằng cách thêm **--enable-preview**. Khi nâng lên JDK khác, cần biên dịch lại bằng release mới và điều chỉnh mã theo phiên bản preview tương ứng. Đừng dùng class file cũ trong thư mục output để kết luận rằng mã nguồn tương thích với JDK mới.

## 5. Bật Vector API incubator

Vector API trong JDK 26 được cung cấp qua module **jdk.incubator.vector**. Với chương trình dùng module này nhưng không dùng preview khác, thêm module ở cả compile time và runtime:

    javac --release 26 --add-modules jdk.incubator.vector -d out src/VectorDemo.java
    java --add-modules jdk.incubator.vector -cp out VectorDemo

Nếu một chương trình đồng thời dùng Vector API và cú pháp hoặc API preview, kết hợp cả hai nhóm cờ:

    javac --enable-preview --release 26 --add-modules jdk.incubator.vector -d out src/VectorDemo.java
    java --enable-preview --add-modules jdk.incubator.vector -cp out VectorDemo

Trong mã nguồn, chương trình có thể import các lớp thuộc **jdk.incubator.vector**. Nếu dùng dự án module có **module-info.java**, khai báo phụ thuộc module tương ứng theo cấu trúc dự án; các lệnh trên minh họa trường hợp chạy trên class path.

Có thể xác nhận module tồn tại trong JDK đang được gọi bằng:

    java --list-modules | Select-String 'jdk.incubator.vector'

Incubator không đồng nghĩa với preview. Vector API được đánh dấu incubating và tài liệu cảnh báo module có thể bị loại bỏ trong một release tương lai. Vì thế, hãy giới hạn việc dùng API này trong thử nghiệm hoặc thành phần mà dự án chấp nhận rủi ro thay đổi. Không đưa API incubator thành phụ thuộc sản phẩm ổn định nếu chưa có quyết định kỹ thuật rõ ràng và phương án thay thế.

## 6. Đồng bộ IDE và build tool

Trong IDE, kiểm tra riêng các cấu hình sau:

- **Project SDK/JDK** trỏ đến JDK 26.
- Mức ngôn ngữ và compiler dùng release 26.
- Cấu hình compiler truyền **--enable-preview** cho source set có dùng preview.
- Cấu hình chạy ứng dụng và cấu hình chạy test truyền **--enable-preview** cho JVM.
- Nếu dùng Vector API, compiler và runtime đều resolve **jdk.incubator.vector** bằng **--add-modules** hoặc cấu hình module tương ứng.

Với Gradle, toolchain giúp chỉ định JDK dùng để biên dịch. Ví dụ Groovy DSL:

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(26)
        }
    }

    tasks.withType(JavaCompile).configureEach {
        options.release = 26
        options.compilerArgs.add("--enable-preview")
    }

    tasks.withType(Test).configureEach {
        jvmArgs("--enable-preview")
    }

    tasks.withType(JavaExec).configureEach {
        jvmArgs("--enable-preview")
    }

Đây là cấu hình cho dự án có chủ ý dùng preview. Nếu dự án chỉ dùng tính năng final, bỏ **--enable-preview** khỏi compiler và JVM. Phiên bản Gradle wrapper cũng phải hỗ trợ JDK 26; toolchain không tự nâng cấp Gradle hoặc bảo đảm một wrapper cũ tương thích.

Với Maven hoặc IDE khác, áp dụng cùng nguyên tắc: cấu hình compiler release 26, bật preview ở compiler, rồi truyền cờ preview cho test runner và application runner. Kiểm tra log của build để xác nhận compiler và JVM thực sự được khởi chạy từ JDK mong muốn. Chỉ đặt **JAVA_HOME** ở terminal không thay thế được cấu hình toolchain hoặc JDK của build daemon.

## 7. Xử lý lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| **invalid source release: 26** | javac đang chạy từ JDK thấp hơn 26 | Kiểm tra **javac --version** và đường dẫn bằng **Get-Command javac -All**; sửa PATH hoặc toolchain |
| Compiler báo preview features are disabled | Thiếu cờ preview khi biên dịch | Dùng javac 26 với **--enable-preview --release 26** |
| JVM báo preview features are not enabled | Compiler đã bật preview nhưng lệnh chạy thiếu cờ | Thêm **--enable-preview** vào lệnh java, test hoặc run configuration |
| **UnsupportedClassVersionError** liên quan preview | Class file preview được tạo bởi release khác với JVM đang chạy | Xóa output cũ, chọn cùng feature release JDK và biên dịch lại |
| Không tìm thấy **jdk.incubator.vector** | Module chưa được resolve hoặc compiler/runtime đang dùng JDK khác | Kiểm tra **java --list-modules**, đường dẫn JDK và thêm **--add-modules jdk.incubator.vector** ở cả hai phía |
| Terminal chạy đúng nhưng IDE/test thất bại | IDE, build daemon hoặc test worker dùng JDK/cờ JVM khác | Kiểm tra Project SDK, Gradle/Maven toolchain và JVM arguments của test/run task |

Khi đổi phiên bản JDK hoặc trạng thái preview, hãy xóa thư mục output cũ trước khi biên dịch lại để tránh chạy nhầm class file đã tạo từ cấu hình trước. Trên PowerShell có thể dùng:

    Remove-Item -Recurse -Force out -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force out | Out-Null

Trên Linux hoặc macOS, lệnh tương đương là **rm -rf out** rồi tạo lại thư mục output. Chỉ xóa thư mục build của dự án đang thực hành; không xóa thư mục cài JDK hoặc cache dùng chung để xử lý lỗi phiên bản.

## 8. Quy trình thực hành đề xuất

1. Đọc JEP hoặc API Specification của đúng JDK release và xác định trạng thái final, preview hay incubator.
2. Kiểm tra **java --version**, **javac --version**, **JAVA_HOME** và đường dẫn executable.
3. Chọn đúng cờ: mã final dùng **--release 26**; preview dùng thêm **--enable-preview** ở compile và run; Vector API dùng thêm **--add-modules jdk.incubator.vector** ở compile và run.
4. Làm sạch output, biên dịch lại bằng JDK 26 và chạy bằng JDK 26.
5. Chạy lại test qua chính build tool/IDE sẽ dùng trong dự án, vì môi trường của test runner có thể khác terminal.
6. Ghi nhận phiên bản JDK và các cờ cần thiết trong hướng dẫn chạy dự án để người khác tái tạo được môi trường.

Trước khi kết luận một tính năng đã hoạt động, cần xác nhận cả ba điều: đúng JDK release, đúng cờ tại từng giai đoạn, và đúng trạng thái của tính năng trong tài liệu chính thức. Quy trình này áp dụng cho các bài thực hành HTTP, pattern matching, structured concurrency, Vector API, bảo mật và JVM trong module Java 26; nó giúp tránh nhầm một thử nghiệm preview/incubator với API đã ổn định.

## Tài liệu chính thức

- [Java SE 26 — Java Language Updates](https://docs.oracle.com/en/java/javase/26/language/java-se-language-updates.pdf): trạng thái tính năng ngôn ngữ và cách biên dịch/chạy preview.
- [JDK 26 — The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): tùy chọn **--release**, **--enable-preview** và **--add-modules**.
- [JDK 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): tùy chọn runtime và source-file mode.
- [JDK 26 — Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html): trạng thái preview của JEP 530.
- [JDK 26 — StructuredTaskScope API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): xác nhận đây là preview API.
- [JDK 26 — Vector API package](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html): trạng thái incubator của Vector API.

Các lệnh và trạng thái trong bài được đối chiếu với tài liệu JDK 26 hiện hành tại ngày 27-11-2026. Khi thực hành trên release khác, hãy thay số release và kiểm tra lại JEP/API tương ứng trước khi dùng cờ hoặc mã nguồn preview.
