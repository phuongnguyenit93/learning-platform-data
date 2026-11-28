# Tách cấu hình Java 26 khỏi ví dụ preview Java 27

Bài thực hành này thiết lập hai môi trường Java độc lập: một môi trường để chạy các ví dụ ổn định thuộc Java 26 và một môi trường dành riêng cho mã sử dụng tính năng preview của Java 27. Mục tiêu là bảo đảm phiên bản JDK dùng để biên dịch, chạy thử, kiểm thử và cấu hình trong IDE luôn khớp với yêu cầu của từng ví dụ.

Trong module Java 26, các chủ đề có thể bao gồm HTTP/3 của HTTP Client API, pattern matching, structured concurrency, Vector API, API bảo mật và tối ưu JVM. Các chủ đề này không có cùng trạng thái phát hành. Ví dụ, HTTP/3 là chức năng chính thức của JDK 26; Primitive Types in Patterns, instanceof, and switch và Structured Concurrency vẫn là preview trong JDK 26; Vector API là incubator. Vì vậy, cần kiểm tra trạng thái của từng JEP trước khi chọn cờ biên dịch.

## 1. Phân biệt phiên bản JDK và trạng thái của tính năng

Tính đến ngày 27/11/2026:

| Phiên bản | Trạng thái phát hành | Vai trò trong bài thực hành |
|---|---|---|
| JDK 25 | LTS, phát hành tháng 09/2025 | Lựa chọn LTS hiện hành khi ứng dụng cần một nền tảng dài hạn và không phụ thuộc tính năng chỉ có từ Java 26 trở lên |
| JDK 26 | Bản phát hành tính năng, GA ngày 17/03/2026; không phải LTS | Dùng để tái hiện và kiểm tra các chức năng được giới thiệu trong Java 26 |
| JDK 27 | Bản phát hành tính năng, GA ngày 15/09/2026; không phải LTS | Dùng cho ví dụ yêu cầu API hoặc ngôn ngữ preview của JDK 27 |

JDK 27 đã là bản phát hành GA. Cụm từ “preview Java 27” trong tài liệu này nói đến những tính năng được đánh dấu preview bên trong JDK 27, không có nghĩa toàn bộ JDK 27 là bản preview hoặc Early Access.

Một số ví dụ về trạng thái tính năng trong JDK 26:

| Tính năng | Trạng thái trong JDK 26 | Cách chuẩn bị môi trường |
|---|---|---|
| HTTP/3 cho HTTP Client API (JEP 517) | Chính thức | Dùng JDK 26; không cần --enable-preview chỉ vì sử dụng HTTP/3 |
| Primitive Types in Patterns, instanceof, and switch (JEP 530) | Preview lần thứ tư | Dùng JDK 26 để biên dịch và chạy, đồng thời bật preview ở cả hai bước |
| Structured Concurrency (JEP 525) | Preview lần thứ sáu | Dùng JDK 26 và bật preview ở cả biên dịch lẫn runtime |
| Vector API (JEP 529) | Incubator lần thứ mười một | Dùng JDK 26 và cấu hình module incubator tương ứng; --enable-preview không thay thế --add-modules |
| PEM Encodings of Cryptographic Objects (JEP 524) | Preview lần thứ hai | Dùng đúng JDK 26 và bật preview ở cả biên dịch lẫn runtime |

Trạng thái của một tính năng có thể thay đổi giữa các bản JDK. Không suy luận rằng một tính năng từng ở preview trong JDK 26 vẫn giữ nguyên trạng thái, cú pháp hoặc API trong JDK 27. Hãy kiểm tra JEP và release notes của đúng phiên bản đang sử dụng.

JDK 26 là bản phát hành không thuộc nhóm LTS. Theo timeline vòng đời JDK được công bố, mốc kết thúc vòng đời của dòng JDK 26 là tháng 09/2026; chính sách cập nhật và hỗ trợ thực tế còn tùy nhà cung cấp JDK. Vì vậy, có thể giữ JDK 26 trong môi trường học tập để tái hiện ví dụ, nhưng cần kiểm tra chính sách hỗ trợ của nhà cung cấp trước khi dùng nó cho hệ thống đang vận hành. Nếu ứng dụng cần nền tảng LTS, Java 25 là dòng LTS hiện hành tại thời điểm viết bài; chỉ chọn nó khi mã nguồn không phụ thuộc API hoặc cú pháp chỉ có từ Java 26 trở lên.

## 2. Cài đặt và giữ riêng các JDK

Cài đặt các bản JDK từ nhà cung cấp đáng tin cậy, chọn đúng hệ điều hành và kiến trúc CPU. Có thể dùng Oracle JDK hoặc một bản phân phối OpenJDK được tổ chức chấp thuận. Dùng bản cập nhật còn được nhà cung cấp hỗ trợ trong từng dòng JDK, kiểm tra chữ ký hoặc checksum theo hướng dẫn tải xuống, và ghi lại nhà cung cấp cùng số phiên bản đã chọn.

Ví dụ bố trí thư mục trên Windows:

~~~text
C:\Dev\jdks\
  jdk-26\
  jdk-27\
C:\Dev\java-labs\
  java26-stable\
  java27-preview\
~~~

Tên thư mục chỉ là ví dụ. Hãy thay bằng đường dẫn cài đặt thực tế. Không chép đè JDK 26 bằng JDK 27, cũng không đặt hai bản JDK vào cùng một thư mục. Mỗi thư mục JDK cần giữ nguyên cấu trúc cài đặt của nhà cung cấp, bao gồm bin, lib và các thành phần runtime đi kèm.

Không cần cài một JRE riêng cho các bài thực hành hiện đại: JDK đã bao gồm runtime cần thiết để chạy chương trình Java. Điều quan trọng là xác định đúng java và javac mà terminal, IDE và build tool đang sử dụng.

### Chuyển JDK trong PowerShell

Mở một terminal mới cho từng bài thực hành. Để dùng JDK 26 trong terminal hiện tại:

~~~powershell
$env:JAVA_HOME = 'C:\Dev\jdks\jdk-26'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java --version
javac --version
(Get-Command java).Source
(Get-Command javac).Source
~~~

Kết quả mong đợi là cả java và javac đều thuộc JDK 26. Đường dẫn của hai lệnh phải nằm dưới cùng thư mục JDK đã chọn.

Khi chuyển sang ví dụ preview của JDK 27, dùng terminal riêng hoặc đổi biến môi trường trong terminal hiện tại:

~~~powershell
$env:JAVA_HOME = 'C:\Dev\jdks\jdk-27'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java --version
javac --version
(Get-Command java).Source
(Get-Command javac).Source
~~~

Thay đổi $env: chỉ có hiệu lực trong tiến trình PowerShell hiện tại và các tiến trình con được khởi chạy từ đó. Đây là cách tiện để chuyển môi trường trong lúc học mà không làm thay đổi cấu hình Java mặc định của toàn hệ thống. Nếu đã mở terminal mới, hãy thiết lập lại biến môi trường cho terminal đó.

Trên Linux hoặc macOS, có thể thực hiện tương tự trong shell hiện tại:

~~~bash
export JAVA_HOME=/opt/jdks/jdk-26
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
command -v java
command -v javac
~~~

Đổi jdk-26 thành jdk-27 khi cần chạy ví dụ preview Java 27.

### Kiểm tra JDK thực sự đang được sử dụng

Không chỉ dựa vào tên biến JAVA_HOME. Một máy có thể có nhiều lệnh java trong PATH; IDE và build tool cũng có thể dùng JDK riêng. Hãy kiểm tra đồng thời:

- java --version: phiên bản runtime được gọi từ terminal.
- javac --version: phiên bản compiler được gọi từ terminal.
- Đường dẫn của java và javac: xác nhận chúng thuộc cùng JDK.
- java.home: thư mục runtime thực tế.
- JVM của Gradle hoặc Maven: có thể khác với JDK toolchain dùng để biên dịch project.
- Project SDK và cấu hình chạy của IDE: phải khớp với yêu cầu của bài.

Có thể xem java.home và java.version trên Windows PowerShell bằng lệnh:

~~~powershell
java -XshowSettings:properties -version 2>&1 |
  Select-String 'java.home|java.version'
~~~

Nếu java là JDK 27 nhưng javac là JDK 26, hoặc ngược lại, hãy sửa PATH trước khi biên dịch. Không tiếp tục thử nghiệm khi chưa xác định được chính xác phiên bản compiler và runtime.

## 3. Biên dịch ví dụ Java 26 ổn định

Với mã Java 26 không dùng tính năng preview hoặc incubator, chọn JDK 26 làm toolchain và dùng --release 26 để giới hạn ngôn ngữ, bytecode và API có thể truy cập ở Java 26.

Ví dụ cấu trúc:

~~~text
java26-stable/
  src/
    Main.java
  out/
~~~

Trong PowerShell, sau khi đã chọn JDK 26:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 26 -d out src\Main.java
java -cp out Main
~~~

Với chương trình có package, bảo đảm đường dẫn nguồn phản ánh package và chạy bằng tên lớp đầy đủ, ví dụ java -cp out com.example.Main.

--release 26 có ý nghĩa khác với việc chỉ đặt JAVA_HOME thành JDK 26:

- Toolchain quyết định bộ JDK/compiler thực tế được sử dụng.
- --release 26 yêu cầu compiler biên dịch theo mức phát hành Java 26, bao gồm tập API công khai tương ứng và định dạng bytecode phù hợp.
- --release 26 không tự chọn JDK 26 và cũng không bật preview.

Nếu dùng JDK 27 để biên dịch mã ổn định với --release 26, compiler có thể giới hạn mã theo Java 26. Tuy nhiên, cách đó không cho phép biên dịch tính năng preview riêng của JDK 26. Khi bài học cần tái hiện đúng một preview hoặc incubator của Java 26, hãy dùng chính JDK 26.

## 4. Biên dịch và chạy ví dụ preview Java 27

Preview feature phải được bật tường minh. Với javac, dùng compiler của JDK 27, đặt release là 27 và thêm --enable-preview:

~~~powershell
javac --enable-preview --release 27 -d out src\PreviewExample.java
~~~

Khi chạy, dùng runtime của JDK 27 và bật cùng cờ:

~~~powershell
java --enable-preview -cp out PreviewExample
~~~

Hai bước đều cần cờ preview. Chỉ bật ở compiler nhưng bỏ ở runtime vẫn có thể khiến chương trình không chạy. Cũng không thể dùng JDK 26 để chạy lớp được biên dịch với preview của JDK 27.

Quy tắc cần nhớ:

1. Preview của release nào phải được biên dịch bằng JDK của release đó.
2. Khi biên dịch, kết hợp --enable-preview với --release cùng số phiên bản, ví dụ --release 27.
3. Khi chạy, dùng runtime cùng release và thêm --enable-preview.
4. Preview có thể thay đổi, tiếp tục preview hoặc bị loại bỏ ở release sau. Mã preview không phải cam kết tương thích lâu dài.
5. Không đưa mã phụ thuộc preview vào artifact phát hành production nếu chưa chấp nhận rõ ràng rủi ro thay đổi và đã có quy trình kiểm soát tương ứng.

Không dùng javac của JDK 27 với --enable-preview --release 26 để mong bật preview Java 26. Cờ preview chỉ áp dụng cho release của chính JDK đang chạy compiler. Nếu cần thử lại preview Java 26, chuyển cả compiler và runtime về JDK 26.

## 5. Cấu hình riêng trong Gradle

Với project Gradle, nên khai báo Java toolchain ở cấp project. Toolchain giúp các tác vụ biên dịch, kiểm thử và thực thi chọn đúng bộ công cụ Java. options.release đặt mức API và bytecode mà compiler được phép sử dụng. Hai cấu hình giải quyết hai việc khác nhau và có thể kết hợp.

Có thể tổ chức hai project độc lập trong cùng workspace:

~~~text
java-labs/
  settings.gradle.kts
  java26-stable/
    build.gradle.kts
    src/main/java/
  java27-preview/
    build.gradle.kts
    src/main/java/
~~~

File settings.gradle.kts ở thư mục gốc:

~~~kotlin
rootProject.name = "java-labs"

include("java26-stable", "java27-preview")
~~~

File java26-stable/build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(26))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(26)
}
~~~

File java27-preview/build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(27))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--enable-preview")
}
~~~

Trong cấu hình thứ hai, JavaCompile áp dụng cho cả mã nguồn chính và mã nguồn kiểm thử. Test bật preview cho JVM chạy test; JavaExec bật preview cho các tác vụ chạy ứng dụng. Nếu project dùng tác vụ chạy Java tùy chỉnh hoặc plugin riêng, cần bảo đảm tác vụ đó cũng truyền --enable-preview cho runtime.

Không sao chép cấu hình preview sang project Java 26 ổn định. Nếu project Java 26 thực sự dùng preview của JDK 26, hãy tạo cấu hình riêng với toolchain 26, options.release là 26, cờ --enable-preview cho compiler và runtime. Nếu dùng Vector API incubator, cấu hình thêm module incubator theo đúng JDK thay vì coi nó là preview.

Gradle daemon JVM và Java toolchain là hai lựa chọn khác nhau. JAVA_HOME hoặc cấu hình Gradle JVM quyết định JVM chạy Gradle; java.toolchain quyết định JDK mà các tác vụ Java của project dùng. Kiểm tra phiên bản Gradle wrapper và ma trận tương thích của Gradle trước khi chạy Gradle trên một JDK mới. Có thể xem JVM của Gradle bằng:

~~~powershell
.\gradlew.bat --version
~~~

Nếu Gradle daemon chạy trên JDK 25 nhưng project toolchain dùng JDK 27, điều đó có thể hợp lệ khi phiên bản Gradle hỗ trợ cấu hình ấy. Đừng kết luận project đang biên dịch bằng JDK 25 chỉ từ dòng JVM của Gradle; hãy kiểm tra toolchain mà tác vụ compile thực sự chọn.

## 6. Cấu hình IDE và môi trường CI

Trong IDE, kiểm tra riêng các mục sau:

- **Project SDK/JDK:** JDK được IDE nhận diện cho workspace.
- **Module SDK hoặc toolchain của module:** JDK áp dụng cho từng project hoặc module.
- **Language level:** mức cú pháp Java mà editor và compiler dùng để phân tích mã.
- **Build tool JVM:** JDK chạy Gradle hoặc Maven.
- **Run/Debug configuration:** runtime thực tế và các VM options khi chạy.
- **Test runner:** runtime và VM options dùng cho test.

Với module Java 26 ổn định, chọn JDK 26 và không thêm --enable-preview nếu ví dụ không dùng preview. Với module preview Java 27, chọn JDK 27, đặt language/release level 27 và thêm --enable-preview ở cả cấu hình biên dịch lẫn chạy. Một số IDE có thể lưu cấu hình chạy riêng cho từng module; hãy kiểm tra cấu hình đó thay vì chỉ nhìn Project SDK.

Trong CI, khai báo JDK cần thiết một cách tường minh. Ghi lại nhà cung cấp, phiên bản JDK, kiến trúc, phiên bản build tool và các cờ compiler/runtime. Dùng cùng cấu hình toolchain trong máy lập trình và pipeline để giảm lỗi “máy tôi chạy được”. Nếu pipeline chạy cả hai loại bài, hãy tách job hoặc tách module để log cho biết rõ tác vụ nào dùng JDK 26 và tác vụ nào dùng JDK 27.

Không dựa vào một biến JAVA_HOME dùng chung để ngầm điều khiển tất cả module. Cũng không để một tác vụ kiểm thử preview dùng nhầm runtime mặc định của máy phát triển hoặc CI.

## 7. Phân biệt preview với incubator

Hai trạng thái này không đồng nghĩa:

- **Preview** là tính năng ngôn ngữ hoặc API được phát hành để thử nghiệm và nhận phản hồi; cần bật bằng --enable-preview khi biên dịch và chạy.
- **Incubator** là API/module đang được phát triển để thu thập phản hồi; thường được cung cấp qua module có tên jdk.incubator.* và cần được thêm vào module graph, ví dụ bằng --add-modules.

Vector API trong JDK 26 là incubator, do đó --enable-preview không tự làm cho module Vector API khả dụng. Khi thực hành, dùng đúng JDK có chứa module đó và cấu hình --add-modules jdk.incubator.vector ở các bước cần thiết. Cách đóng gói và cấu hình module path có thể khác giữa chương trình chạy trực tiếp và build tool; tham khảo tài liệu của JEP 529 cho đúng release.

Một tính năng preview có thể trở thành chính thức ở release sau, tiếp tục preview với thay đổi, hoặc bị loại bỏ. Một API incubator cũng có thể đổi thiết kế hoặc tên module. Vì vậy, không dùng nhãn “preview” và “incubator” thay thế cho nhau, và không suy ra trạng thái hiện tại từ một bài viết cũ.

## 8. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| invalid source release: 27 | Compiler được gọi không hỗ trợ release 27 | Kiểm tra javac --version và đường dẫn compiler; chuyển sang JDK 27 |
| Báo preview feature bị tắt khi biên dịch | Thiếu --enable-preview hoặc cờ không được truyền tới tác vụ compile | Kiểm tra lệnh compiler thực tế; thêm cờ và đặt --release cùng phiên bản JDK |
| Báo preview feature bị tắt khi chạy | Runtime chưa nhận --enable-preview | Thêm cờ vào VM options của ứng dụng, test runner hoặc tác vụ JavaExec |
| Báo preview chỉ được hỗ trợ cho release hiện tại | --release không khớp phiên bản JDK đang chạy compiler | Dùng JDK đúng release và đặt cùng số phiên bản ở --release |
| UnsupportedClassVersionError | Runtime cũ hơn mức bytecode của lớp đã biên dịch | Chạy bằng JDK đủ mới hoặc biên dịch lại với release phù hợp |
| Không tìm thấy jdk.incubator.vector | Chưa dùng JDK có module tương ứng hoặc chưa thêm module | Kiểm tra JDK và thêm --add-modules jdk.incubator.vector |
| Terminal đúng JDK nhưng IDE chạy sai | IDE, Gradle daemon hoặc test runner có cấu hình JDK riêng | Kiểm tra Project SDK, module SDK, Gradle JVM và Run/Debug configuration |
| Chạy được trên máy cá nhân nhưng lỗi trong CI | Pipeline thiếu JDK/toolchain hoặc thiếu cờ runtime | Ghi rõ JDK và build tool trong log; cấu hình compiler và runtime nhất quán |

Khi gặp lỗi, hãy ghi lại cả lệnh compile và lệnh run thực tế. Chỉ ghi “đã cài JDK 27” là chưa đủ để xác định compiler, runtime hay build tool đang dùng bản nào.

## 9. Bài thực hành kiểm chứng

Thực hiện lần lượt các bước sau và lưu lại kết quả trong ghi chú của bài:

1. Cài JDK 26 và JDK 27 vào hai thư mục riêng.
2. Mở terminal mới, chọn JDK 26, kiểm tra java --version, javac --version và đường dẫn của hai lệnh.
3. Biên dịch một chương trình Java 26 ổn định với javac --release 26, sau đó chạy bằng JDK 26.
4. Chọn JDK 27 trong terminal khác. Xác nhận cả compiler và runtime đều là JDK 27.
5. Biên dịch ví dụ preview Java 27 với --enable-preview --release 27; chạy lại với java --enable-preview.
6. Bỏ cờ preview ở bước chạy để quan sát lỗi, sau đó thêm lại để xác nhận cách khắc phục.
7. Thử dùng compiler JDK 26 cho ví dụ preview Java 27 và giải thích vì sao compiler không thể bật preview của release khác.
8. Nếu project dùng Gradle, kiểm tra JVM của Gradle wrapper và toolchain của từng module; xác nhận tác vụ test cũng truyền cờ preview.
9. Ghi rõ tính năng đang thử thuộc loại chính thức, preview hay incubator và trích dẫn JEP/release notes tương ứng.

**Tiêu chí hoàn thành:** có thể chuyển giữa hai JDK mà không làm thay đổi cấu hình toàn hệ thống; xác định được compiler và runtime thực tế; biên dịch/chạy được ví dụ Java 26 ổn định; biên dịch/chạy được ví dụ preview Java 27 với cờ phù hợp; giải thích được khác biệt giữa toolchain, --release, preview và incubator.

## 10. Tài liệu tham khảo chính thức

- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — trạng thái các tính năng, thay đổi và JEP trong JDK 26.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — thông tin phát hành và trạng thái tính năng của JDK 27.
- [Preview Features — Java 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html) — cách bật preview ở compiler và runtime, cùng giới hạn tương thích giữa các release.
- [JDK Releases](https://ops.java/releases/?lang=en) — lịch phát hành, các bản cập nhật và mốc vòng đời của các dòng JDK.
- [Gradle Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — cấu hình toolchain, --release, IDE và JVM chạy Gradle.

Khi thực hiện lại bài học ở thời điểm khác, hãy kiểm tra release notes và lịch vòng đời mới nhất. Số phiên bản, trạng thái preview/incubator và chính sách hỗ trợ có thể thay đổi sau mỗi kỳ phát hành.

