# Khắc phục lỗi không mở được JAR

## 1. Hiểu đúng lỗi “không mở được JAR”

JAR (Java ARchive) là file đóng gói dựa trên định dạng ZIP, thường chứa class file, resource và metadata của ứng dụng hoặc thư viện Java. Một file có đuôi .jar không nhất thiết là ứng dụng có thể chạy bằng cách nhấp đúp.

Có hai mục đích sử dụng chính:

- **Executable JAR:** có điểm vào chương trình được khai báo bằng thuộc tính Main-Class trong manifest. Có thể khởi chạy bằng java -jar app.jar.
- **Library JAR:** chứa class/resource để ứng dụng khác sử dụng. Nó có thể hoàn toàn hợp lệ dù không có Main-Class; không thể chạy độc lập bằng java -jar.

Cần xác định thao tác nào thất bại:

1. Nhấp đúp file trong Explorer/Finder không mở ứng dụng.
2. Java launcher báo không truy cập được file.
3. Java báo thiếu Main-Class hoặc không tìm thấy main class.
4. Chương trình bắt đầu chạy nhưng thiếu dependency.
5. JAR bị hỏng, tải chưa đủ hoặc thực chất không phải JAR.
6. JDK hiện tại quá cũ so với bytecode trong JAR.
7. Ứng dụng khởi chạy nhưng cửa sổ đóng ngay, không hiện log hoặc lỗi.
8. JAR phụ thuộc native library, module hoặc runtime riêng.

Không nên xử lý tất cả các trường hợp bằng cách cài lại Java. Trước tiên hãy chạy JAR từ terminal để lấy thông báo lỗi thật.

## 2. Kiểm tra Java đã được cài và PATH đúng chưa

Mở Terminal, Command Prompt hoặc PowerShell và chạy:

~~~bash
java --version
javac --version
jar --version
~~~

java là runtime launcher, javac là compiler, còn jar dùng để tạo và kiểm tra archive. Máy chỉ cần chạy ứng dụng có thể không cần javac, nhưng cần JDK nếu muốn biên dịch hoặc dùng các công cụ phát triển.

Nếu gặp thông báo:

~~~text
'java' is not recognized as an internal or external command
~~~

hoặc:

~~~text
java: command not found
~~~

thì Java chưa được cài hoặc thư mục bin của JDK chưa có trong PATH.

Trên Windows PowerShell, kiểm tra executable đang được gọi:

~~~powershell
Get-Command java, javaw, jar | Select-Object Name, Source
$env:JAVA_HOME
~~~

Trên Linux/macOS:

~~~bash
command -v java
command -v jar
echo "$JAVA_HOME"
~~~

Nếu có nhiều JDK, kiểm tra java --version để biết phiên bản thực sự đang chạy. JAVA_HOME và PATH có thể trỏ tới hai JDK khác nhau.

## 3. Chạy JAR từ terminal để xem lỗi thật

Không dùng nhấp đúp làm bước chẩn đoán đầu tiên. Mở terminal tại thư mục chứa file và chạy:

~~~bash
java -jar app.jar
~~~

Nếu đường dẫn có khoảng trắng, đặt toàn bộ đường dẫn trong dấu nháy:

~~~powershell
java -jar "C:\Users\Public\My Apps\app.jar"
~~~

Trên Linux/macOS:

~~~bash
java -jar "/opt/my apps/app.jar"
~~~

Nếu ứng dụng nhận argument:

~~~bash
java -jar app.jar input.txt "two words"
~~~

Java truyền hai argument cuối cho main(String[] args). Dấu nháy bảo vệ khoảng trắng để shell không tách một argument thành nhiều phần.

Ghi lại toàn bộ thông báo và exit code. Trên PowerShell:

~~~powershell
java -jar ".\app.jar"
$LASTEXITCODE
~~~

Trên Bash:

~~~bash
java -jar ./app.jar
echo $?
~~~

Exit code khác 0 cho biết lần chạy thất bại; nội dung stderr/stdout mới cho biết nguyên nhân cụ thể.

## 4. Lỗi “no main manifest attribute”

Thông báo thường gặp:

~~~text
no main manifest attribute, in app.jar
~~~

Java đã đọc được JAR nhưng không tìm thấy thuộc tính Main-Class trong META-INF/MANIFEST.MF. java -jar cần biết class nào chứa phương thức:

~~~java
public static void main(String[] args)
~~~

Trước tiên kiểm tra manifest:

~~~bash
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

Mở file META-INF/MANIFEST.MF và tìm dòng:

~~~text
Main-Class: com.example.Main
~~~

Tên phải là tên class đầy đủ gồm package, đúng chữ hoa/chữ thường và không có hậu tố .class.

Nếu JAR là thư viện, không có Main-Class là bình thường. Hãy dùng nó trên classpath khi chạy ứng dụng khác, không chạy nó như executable JAR.

## 5. Tạo executable JAR đúng cách bằng JDK

Ví dụ cấu trúc source:

~~~text
project/
├── src/
│   └── com/example/Main.java
├── build/
└── dist/
~~~

Nội dung src/com/example/Main.java:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("JAR opened successfully");
        System.out.println("argument.count=" + args.length);
    }
}
~~~

Biên dịch với Java 17:

~~~bash
javac --release 17 -d build/classes src/com/example/Main.java
~~~

Đóng gói và chỉ định main class:

~~~bash
jar --create --file dist/app.jar --main-class com.example.Main -C build/classes .
~~~

Chạy:

~~~bash
java -jar dist/app.jar first "two words"
~~~

Stdout chính xác:

~~~text
JAR opened successfully
argument.count=2
~~~

Tùy chọn --main-class ghi thuộc tính Main-Class vào manifest. Có thể kiểm tra lại:

~~~bash
jar --list --file dist/app.jar
jar --extract --file dist/app.jar META-INF/MANIFEST.MF
~~~

Nếu dùng JDK cũ không hỗ trợ cú pháp option hiện đại, hãy xem jar --help của đúng JDK hoặc tạo manifest riêng bằng jar cfm.

## 6. Lỗi “Could not find or load main class”

Thông báo có thể giống:

~~~text
Error: Could not find or load main class com.example.Main
Caused by: java.lang.ClassNotFoundException: com.example.Main
~~~

Các nguyên nhân thường gặp:

- Main-Class ghi sai package hoặc tên class.
- Class không được đóng gói vào JAR.
- Cấu trúc package trong archive không đúng.
- Tên class sai chữ hoa/chữ thường.
- Chạy nhầm JAR hoặc phiên bản build cũ.
- Đang dùng -cp với đường dẫn sai.

Kiểm tra archive:

~~~bash
jar --list --file app.jar
~~~

Với class com.example.Main, archive phải có entry:

~~~text
com/example/Main.class
~~~

Nếu class không tồn tại, kiểm tra output của compiler và lệnh đóng gói. Với project có package, không tự đổi tên class hoặc bỏ package để sửa lỗi một cách tùy tiện; manifest phải khớp với class thực tế.

## 7. Lỗi “Unable to access jarfile”

Thông báo:

~~~text
Error: Unable to access jarfile app.jar
~~~

Java launcher không mở được đường dẫn đã truyền. Kiểm tra:

- File có tồn tại ở working directory hiện tại không?
- Tên file và phần mở rộng có đúng không?
- Đường dẫn có khoảng trắng nhưng chưa được quote không?
- User chạy lệnh có quyền đọc file và thư mục cha không?
- File có bị di chuyển, xóa hoặc đổi tên sau khi copy không?
- Đang dùng relative path tính từ thư mục nào?

PowerShell:

~~~powershell
Get-Location
Test-Path -LiteralPath ".\app.jar"
Get-Item -LiteralPath ".\app.jar" | Select-Object FullName, Length, LastWriteTime
~~~

Linux/macOS:

~~~bash
pwd
ls -l ./app.jar
test -r ./app.jar && echo "JAR is readable"
~~~

Thử đường dẫn tuyệt đối để loại trừ lỗi working directory. Trên Windows, dùng -LiteralPath khi kiểm tra tên file có ký tự đặc biệt.

## 8. Lỗi “Invalid or corrupt jarfile”

Ví dụ:

~~~text
Error: Invalid or corrupt jarfile app.jar
~~~

File không có cấu trúc archive hợp lệ hoặc bị cắt/hỏng. Nguyên nhân thường gặp:

- Download chưa hoàn tất hoặc bị gián đoạn.
- File bị copy thiếu byte.
- Một trang đăng nhập hoặc trang lỗi HTML được lưu nhầm với đuôi .jar.
- Công cụ upload/download đã xử lý sai file binary.
- JAR bị ghi đè hoặc chỉnh sửa trong lúc build.

Kiểm tra nội dung archive:

~~~bash
jar --list --file app.jar
~~~

Nếu có unzip:

~~~bash
unzip -t app.jar
~~~

Trên Windows có thể dùng:

~~~powershell
7z t .\app.jar
~~~

Hoặc dùng công cụ archive hỗ trợ kiểm tra ZIP. Nếu không đọc được, tải lại từ nguồn tin cậy và so sánh SHA-256 với checksum do nhà phát hành công bố:

~~~powershell
Get-FileHash .\app.jar -Algorithm SHA256
~~~

Linux:

~~~bash
sha256sum app.jar
~~~

macOS:

~~~bash
shasum -a 256 app.jar
~~~

Không chỉ đổi đuôi .zip hoặc .jar để sửa file hỏng. Đổi tên không thể phục hồi byte đã mất.

## 9. Dùng jar --validate đúng mục đích

JDK có lệnh:

~~~bash
jar --validate --file app.jar
~~~

Option này kiểm tra các ràng buộc của nội dung JAR, đặc biệt hữu ích với multi-release JAR và API giữa các phiên bản. Nó bổ sung cho việc liệt kê archive, không thay thế toàn bộ kiểm tra integrity ZIP.

Trong thử nghiệm JDK 24.0.2, jar --validate có thể in thông báo zip END header not found cho file hỏng nhưng vẫn trả exit code 0. Vì vậy, CI không nên chỉ dựa vào exit code của lệnh này. Hãy kiểm tra nội dung output và dùng thêm jar --list, unzip -t hoặc 7z t để xác nhận archive có thể đọc.

Phân biệt ba câu hỏi:

- jar --list: archive có thể được đọc và liệt kê entry không?
- unzip -t hoặc 7z t: cấu trúc ZIP và dữ liệu entry có qua kiểm tra integrity không?
- jar --validate: nội dung JAR có vi phạm các ràng buộc mà option này kiểm tra không?

Một lệnh pass không chứng minh ứng dụng có main class, dependency đầy đủ hoặc tương thích với JDK đang chạy.

## 10. Lỗi “NoClassDefFoundError” và thiếu dependency

Ví dụ:

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: com/example/lib/Helper
Caused by: java.lang.ClassNotFoundException: com.example.lib.Helper
~~~

JAR chính có thể hợp lệ và có Main-Class, nhưng class cần dùng không có trong runtime classpath/module path.

Kiểm tra dependency:

- Dependency JAR có được phát hành cùng ứng dụng không?
- Đường dẫn dependency có đúng so với thư mục chạy không?
- Build có khai báo dependency runtime hay chỉ compile-time không?
- Có dependency bắc cầu bị thiếu không?
- Có dùng reflection hoặc plugin loader để nạp class động không?

Nếu ứng dụng gồm JAR chính và thư viện riêng, có thể chạy bằng classpath.

Windows:

~~~powershell
java -cp "app.jar;lib/*" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

Dấu phân cách classpath là ; trên Windows và : trên Linux/macOS. Đặt toàn bộ classpath trong dấu nháy để bảo vệ khoảng trắng và wildcard khỏi shell.

Khi dùng java -jar app.jar, classpath được truyền bằng -cp hoặc -classpath không được dùng như cách bổ sung dependency. Chọn một trong hai cách: chạy main class qua -cp, hoặc khai báo dependency trong manifest Class-Path.

## 11. Khai báo dependency bằng manifest Class-Path

Với executable JAR có thư mục thư viện đi kèm:

~~~text
dist/
├── app.jar
└── lib/
    └── helper.jar
~~~

Manifest có thể khai báo:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/helper.jar
~~~

Đường dẫn trong Class-Path là URL tương đối với vị trí của JAR chứa manifest; dùng dấu slash / trong giá trị này kể cả khi chạy trên Windows.

Có thể tạo manifest riêng rồi đóng gói:

~~~bash
jar --create --file dist/app.jar --manifest manifest.mf -C build/classes .
~~~

Sau đó chạy:

~~~bash
java -jar dist/app.jar
~~~

Đảm bảo lib/helper.jar thực sự tồn tại tương đối với app.jar. Nếu dependency nằm ở vị trí khác, cập nhật manifest hoặc dùng classpath command phù hợp.

Manifest không tự đóng gói thư viện vào JAR. Nó chỉ khai báo nơi Java launcher tìm thêm class. Nếu muốn phân phối một file duy nhất, cần dùng cách đóng gói phù hợp như shaded/fat JAR và kiểm tra việc gộp resource, service descriptor và chữ ký.

## 12. Phân biệt executable JAR và library JAR

Không phải JAR nào cũng cần chạy được bằng java -jar.

| Loại JAR | Nội dung | Cách sử dụng |
|---|---|---|
| Executable JAR | Có entry point và Main-Class. | java -jar app.jar. |
| Library JAR | Class/resource để project khác sử dụng. | Thêm vào classpath hoặc module path. |
| Modular JAR | Có module-info.class. | Dùng module path và module name. |
| Fat/shaded JAR | Đóng gói ứng dụng cùng một phần hoặc toàn bộ dependency. | Thường chạy bằng java -jar nếu manifest có main class. |

Ví dụ dùng library JAR:

~~~powershell
java -cp "app.jar;lib/helper.jar" com.example.Main
~~~

Lệnh này dùng dấu ; cho Windows. Trên Linux/macOS thay bằng :.

Nếu nhà phát hành chỉ cung cấp thư viện, hãy đọc hướng dẫn sử dụng và dependency coordinates của nó. Việc không có Main-Class không phải lỗi của thư viện.

## 13. Lỗi UnsupportedClassVersionError

Thông báo thường gặp:

~~~text
java.lang.UnsupportedClassVersionError:
com/example/Main has been compiled by a more recent version
of the Java Runtime
~~~

JAR chứa bytecode được biên dịch bởi JDK mới hơn runtime hiện tại. Mỗi phiên bản Java class file có major version tương ứng.

Một số mốc:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Kiểm tra Java runtime:

~~~bash
java --version
~~~

Có thể xem bytecode version của class:

~~~bash
javap -verbose -classpath app.jar com.example.Main
~~~

Tìm dòng major version.

Cách khắc phục:

- Cài và dùng JDK/JRE đủ mới theo yêu cầu của ứng dụng.
- Hoặc build lại source với javac --release 17 nếu muốn chạy trên Java 17 và code/dependency tương thích.
- Kiểm tra cả dependency; một thư viện mới hơn cũng có thể yêu cầu JDK mới.
- Không đổi tên file hoặc sửa manifest để xử lý lỗi bytecode version.

--release kiểm soát API Java mục tiêu và bytecode khi compile; chỉ đặt source/target mà không kiểm soát API có thể vẫn tạo ứng dụng gọi API không tồn tại trên runtime cũ.

## 14. Kiểm tra JDK được dùng để chạy

Một máy có thể cài nhiều JDK. Terminal, IDE, Maven, Gradle và Windows file association có thể dùng những Java executable khác nhau.

Kiểm tra:

~~~powershell
Get-Command java, javaw | Select-Object Name, Source
$env:JAVA_HOME
java --version
~~~

Trên Linux/macOS:

~~~bash
which java
readlink -f "$(which java)"
java --version
~~~

Trên macOS có thể dùng:

~~~bash
/usr/libexec/java_home -V
~~~

Nếu terminal chạy được JAR nhưng IDE hoặc nhấp đúp thất bại, so sánh JDK của các môi trường đó. Cấu hình runtime trong IDE hoặc ứng dụng launcher về cùng JDK tương thích.

Không chỉ kiểm tra biến JAVA_HOME; hãy kiểm tra đường dẫn executable và phiên bản thực tế được gọi.

## 15. Nhấp đúp JAR không mở ứng dụng trên Windows

Nhấp đúp phụ thuộc file association của Windows. Phần mở rộng .jar có thể đang được gắn với phần mềm nén archive, IDE hoặc ứng dụng khác thay vì Java launcher.

Kiểm tra association:

~~~cmd
assoc .jar
~~~

Lệnh trên trả về ProgID. Sau đó kiểm tra lệnh mở của ProgID đó:

~~~cmd
ftype ProgID
~~~

Thay ProgID bằng giá trị thực tế nhận được từ assoc. Đây là các lệnh đọc cấu hình.

Nếu JAR mở bằng WinRAR/7-Zip, chương trình đang xem nội dung archive chứ chưa chạy ứng dụng Java. Có thể dùng terminal:

~~~powershell
java -jar ".\app.jar"
~~~

Nếu muốn mở bằng nhấp đúp, chọn Java runtime phù hợp trong Windows Settings hoặc Open with. Với ứng dụng cần hiện console, chạy bằng java.exe để xem log. javaw.exe không mở console, phù hợp hơn với ứng dụng GUI không cần terminal.

Không sửa association bằng một lệnh registry ngẫu nhiên khi chưa biết ProgID và executable đang được cài. Cài đặt hoặc repair Java runtime chính thức có thể khôi phục association nếu runtime hỗ trợ thao tác đó.

## 16. Nhấp đúp trên macOS và Linux

Trên macOS, Finder có thể không biết phải dùng Java launcher nào cho file JAR. Dùng Terminal:

~~~bash
java -jar "/Applications/My App/app.jar"
~~~

Nếu ứng dụng cần cài đặt riêng hoặc có launcher .app, hãy dùng gói phân phối chính thức thay vì giả định mọi JAR đều có thể mở trực tiếp từ Finder.

Trên Linux, JAR thường không được chạy trực tiếp bằng cách nhấp đúp. Chạy:

~~~bash
java -jar ./app.jar
~~~

Không nhầm quyền execute của file với khả năng chạy JAR. Một JAR thông thường không phải native executable và không có shebang để shell biết cách khởi chạy. chmod +x app.jar không tự biến nó thành chương trình native; dùng Java launcher hoặc script launcher phù hợp.

## 17. Ứng dụng khởi chạy rồi cửa sổ biến mất

Nếu nhấp đúp một ứng dụng console, cửa sổ terminal có thể đóng ngay khi chương trình kết thúc hoặc gặp lỗi. Hãy chạy từ terminal để giữ lại output:

~~~bash
java -jar app.jar
~~~

Nếu ứng dụng là GUI:

- Kiểm tra có tạo và hiển thị cửa sổ trong code không.
- Kiểm tra exception khi khởi tạo UI.
- Kiểm tra JavaFX/Swing/AWT và module cần thiết.
- Kiểm tra app có chạy ở headless environment không.
- Kiểm tra log file hoặc cấu hình logging.
- Xác nhận chương trình không thoát ngay sau khi tạo UI.

Một JAR chỉ có class JavaFX không nhất thiết chứa JavaFX runtime. Với các JDK hiện đại, JavaFX thường được phân phối riêng; cần đúng JavaFX SDK/modules và native library cho OS/architecture tương ứng.

Đừng kết luận JAR hỏng chỉ vì không có cửa sổ. Ứng dụng có thể là command-line tool, chạy nền hoặc hoàn thành nhanh sau khi in kết quả.

## 18. Lỗi module không tìm thấy

Ứng dụng modular có thể báo:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.helper not found
~~~

Khi dùng Java Platform Module System, dependency phải có trên module path và module name phải đúng.

Ví dụ Windows:

~~~powershell
java --module-path "mods;lib" --module com.example.app/com.example.Main
~~~

Trên Linux/macOS, module path dùng dấu : thay cho ;.

Kiểm tra module name và descriptor:

~~~bash
jar --describe-module --file lib/helper.jar
~~~

Đừng dùng classpath và module path thay thế cho nhau khi ứng dụng đã được thiết kế để chạy theo module graph. Xác nhận module dependency đã được đóng gói và đặt đúng vị trí.

## 19. Lỗi native library và kiến trúc CPU

Thông báo như:

~~~text
java.lang.UnsatisfiedLinkError
~~~

có thể cho biết ứng dụng không tải được native library. Nguyên nhân gồm:

- Thiếu file .dll, .so hoặc .dylib.
- Native library không đúng OS.
- Binary x64 được dùng trên ARM64 hoặc ngược lại.
- Đường dẫn native library không đúng.
- Native dependency bắc cầu bị thiếu.
- ABI hoặc phiên bản native library không tương thích.

Kiểm tra os.name, os.arch, java.library.path và file native thực tế. Nếu dùng JNI/JNA hoặc framework có native component, tải/build đúng binary cho từng nền tảng.

Một JAR có thể đọc và liệt kê bình thường nhưng vẫn không chạy được vì native dependency không tương thích. Đây là lỗi runtime integration, không phải lỗi ZIP/JAR.

## 20. JAR có chữ ký nhưng bị sửa đổi

JAR có thể được ký bằng jarsigner. Nếu nội dung archive bị thay đổi sau khi ký, kiểm tra chữ ký có thể báo digest không hợp lệ.

Kiểm tra:

~~~bash
jarsigner -verify -verbose -certs app.jar
~~~

Nếu chữ ký không hợp lệ:

- Lấy lại artifact nguyên bản từ nguồn phát hành.
- Xác nhận checksum và signer certificate theo quy trình của nhà phát hành.
- Nếu đây là JAR do chính đội ngũ tạo, build lại rồi ký lại bằng signing key hợp lệ.
- Không xóa các file chữ ký trong META-INF của JAR bên thứ ba chỉ để bỏ cảnh báo.

JAR không có chữ ký vẫn có thể là JAR hợp lệ. Phải phân biệt trạng thái unsigned với signed JAR có chữ ký không hợp lệ.

## 21. Kiểm tra JAR bằng quy trình từng bước

Có thể dùng checklist sau khi nhận một file không mở được:

1. Xác nhận file tồn tại và kích thước lớn hơn 0.
2. Kiểm tra Java version và executable đang được gọi.
3. Chạy jar --list --file app.jar.
4. Nếu có unzip, chạy unzip -t app.jar.
5. Xem META-INF/MANIFEST.MF.
6. Xác nhận Main-Class nếu muốn chạy bằng java -jar.
7. Kiểm tra main class có tồn tại trong archive.
8. Kiểm tra dependency trong classpath/manifest/module path.
9. Kiểm tra class file version so với runtime.
10. Kiểm tra native library, module và chữ ký nếu ứng dụng cần.
11. Chạy từ terminal và lưu stack trace.
12. So sánh SHA-256 với checksum phát hành nếu nghi ngờ file bị hỏng.

Không cần thực hiện mọi bước cho mọi lỗi. Hãy dùng thông báo đầu tiên để chọn nhánh chẩn đoán phù hợp.

## 22. Maven: tạo JAR có Main-Class

Với Maven JAR Plugin, khai báo main class trong pom.xml:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>com.example.Main</mainClass>
                    </manifest>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Build:

~~~bash
mvn -B clean package
~~~

Chạy JAR:

~~~bash
java -jar target/app-1.0.0.jar
~~~

Cấu hình này thêm main class vào manifest. Nó không tự đóng gói mọi dependency bên ngoài vào JAR. Nếu ứng dụng cần thư viện, hãy cấu hình runtime dependency, manifest classpath hoặc plugin đóng gói phù hợp.

## 23. Gradle: tạo JAR có Main-Class

Với Gradle Java Plugin:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

tasks.named('jar', Jar).configure {
    manifest {
        attributes 'Main-Class': 'com.example.Main'
    }
}
~~~

Build:

~~~bash
./gradlew clean jar
~~~

Windows:

~~~powershell
.\gradlew.bat clean jar
~~~

Chạy:

~~~bash
java -jar build/libs/app-1.0.0.jar
~~~

Nếu dùng Gradle Application Plugin, cấu hình application { mainClass = 'com.example.Main' } để chỉ định entry point cho application distribution và các task liên quan. JAR task vẫn cần manifest phù hợp nếu mục tiêu là chạy trực tiếp bằng java -jar.

## 24. Java demo và lỗi được tái hiện

Một fixture Java 17 nhỏ đã được biên dịch và đóng gói để kiểm tra các nhánh chẩn đoán.

Với JAR hợp lệ, có Main-Class và đường dẫn chứa khoảng trắng:

~~~powershell
java -jar "dist with spaces/app.jar" first "two words"
~~~

Stdout chính xác:

~~~text
JAR opened successfully
argument.count=2
~~~

Các lỗi đã tái hiện trên JDK 24.0.2:

| Tình huống | Kết quả quan sát |
|---|---|
| JAR hợp lệ, có Main-Class | Chạy thành công, exit code 0. |
| JAR không có Main-Class | no main manifest attribute, exit code 1. |
| File text giả dạng .jar | Invalid or corrupt jarfile, exit code 1 khi chạy. |
| JAR thiếu dependency | NoClassDefFoundError và ClassNotFoundException. |
| Thêm dependency vào classpath | Chạy thành công. |
| Khai báo manifest Class-Path đúng | java -jar tìm được dependency tương đối. |
| Java 17 chạy class được compile bằng Java 25 | UnsupportedClassVersionError (class major 69 so với mức hỗ trợ 61). |
| Maven JAR Plugin có Main-Class | Build và chạy thành công. |
| Gradle JAR manifest có Main-Class | Build và chạy thành công. |

Các fixture Maven và Gradle đều hoàn tất BUILD SUCCESSFUL, sau đó JAR được khởi chạy thành công bằng java -jar. Các kết quả trên phân biệt lỗi archive, manifest, dependency và runtime version. Nếu môi trường thực tế cho thông báo khác, hãy dùng stack trace và JAR cụ thể để điều tra tiếp.

## 25. Lỗi thường gặp và cách xử lý nhanh

| Thông báo/triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| java not found | Java chưa cài hoặc PATH sai. | Cài JDK/runtime và kiểm tra PATH. |
| Unable to access jarfile | Sai path, working directory hoặc quyền đọc. | Dùng absolute path, quote đường dẫn, kiểm tra file. |
| no main manifest attribute | Không có Main-Class. | Xác định đây là library hay executable JAR; cấu hình manifest nếu cần. |
| Could not find or load main class | Sai main class hoặc class không nằm trong JAR. | Kiểm tra manifest và jar --list. |
| Invalid or corrupt jarfile | File hỏng hoặc không phải JAR. | Kiểm tra ZIP, tải lại và so sánh checksum. |
| NoClassDefFoundError | Thiếu dependency lúc chạy. | Bổ sung classpath, manifest Class-Path hoặc module path. |
| UnsupportedClassVersionError | Runtime Java quá cũ. | Dùng JDK mới hoặc build với --release phù hợp. |
| Nhấp đúp mở bằng WinRAR/IDE | File association trỏ tới ứng dụng khác. | Kiểm tra .jar association và chạy qua java -jar. |
| Cửa sổ mở rồi đóng | Ứng dụng kết thúc hoặc lỗi không hiển thị. | Chạy từ terminal để xem output và stack trace. |
| FindException: Module not found | Module path thiếu module hoặc sai tên. | Kiểm tra module path và module descriptor. |
| UnsatisfiedLinkError | Native library thiếu hoặc sai OS/architecture. | Cài đúng native binary và kiểm tra library path. |
| Invalid signature/digest | JAR signed đã bị thay đổi hoặc hỏng. | Lấy artifact gốc hoặc build và ký lại đúng cách. |
| jar --validate báo lỗi nhưng exit code 0 | Không kiểm tra output, chỉ dựa vào exit code. | Kết hợp kiểm tra archive và parse thông báo lỗi. |

## 26. Thói quen giúp tránh lỗi khi phân phối JAR

- Ghi rõ JDK tối thiểu mà ứng dụng hỗ trợ.
- Chỉ định Main-Class cho executable JAR.
- Phân biệt artifact ứng dụng với library JAR.
- Đóng gói hoặc khai báo đầy đủ runtime dependency.
- Test java -jar trên môi trường sạch.
- Kiểm tra file sau khi upload/download và so sánh checksum.
- Kiểm tra đúng OS/architecture nếu có native library.
- Giữ manifest, module descriptor và chữ ký nhất quán.
- Cung cấp script launcher hoặc installer khi người dùng không quen terminal.
- Lưu log lỗi và phiên bản Java trong báo cáo hỗ trợ.

## 27. Tài liệu tham khảo

- [The java Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The jar Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [JAR File Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html)
- [The jarsigner Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jarsigner.html)
- [Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/)
- [Gradle Jar Task](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)

Khi JAR không mở được, hãy chạy nó từ terminal để xác định chính xác lỗi, sau đó kiểm tra archive, manifest, main class, dependency và phiên bản runtime theo đúng nhánh. Một JAR đọc được chưa chắc chạy độc lập; một JAR không có Main-Class vẫn có thể là thư viện hợp lệ.