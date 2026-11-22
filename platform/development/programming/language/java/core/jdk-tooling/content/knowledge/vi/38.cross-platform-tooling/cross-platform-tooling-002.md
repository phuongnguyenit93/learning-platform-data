# Khác biệt macOS khi phát triển và build Java

macOS có nền tảng Unix và hỗ trợ đầy đủ Java Development Kit (JDK), nhưng môi trường phát triển khác Linux và Windows ở cách cài JDK, quản lý nhiều phiên bản, kiến trúc CPU, shell, filesystem, thư viện native, quyền chạy file và cơ chế bảo vệ ứng dụng.

Khi chuyển một dự án Java sang Mac, hãy kiểm tra cả JDK mà terminal sử dụng, JDK mà IDE sử dụng và JDK trong CI. Trên Apple Silicon, cần xác định tiến trình đang chạy native ARM64 hay qua Rosetta x86_64. Với dự án có native library hoặc đóng gói ứng dụng desktop, kiến trúc binary và code signing cũng là một phần của quá trình build.

## 1. Hai kiến trúc Mac cần phân biệt

Mac Intel dùng CPU x86_64. Mac Apple Silicon dùng ARM64, thường được gọi là arm64 hoặc AArch64. JDK được phân phối riêng cho từng kiến trúc; tải đúng bản là bước đầu tiên khi cài đặt.

| Máy Mac | Kiến trúc phần cứng | JDK package tương ứng |
|---|---|---|
| Mac Intel | x86_64 | macOS x64 |
| Mac Apple Silicon | ARM64 | macOS AArch64/ARM64 |

Oracle JDK cung cấp installer cho cả macOS x64 và macOS AArch64. Không giả định một thư mục JDK hoặc native library có thể dùng chung giữa hai kiến trúc.

### 1.1. Kiểm tra kiến trúc máy và tiến trình

Mở Terminal:

~~~sh
sw_vers
uname -m
arch
~~~

Kết quả thường gặp:

- uname -m trả về arm64 trên Apple Silicon.
- uname -m trả về x86_64 trên Mac Intel.
- Trên Apple Silicon, một tiến trình x86_64 chạy qua Rosetta có thể hiển thị kiến trúc tiến trình khác với kiến trúc phần cứng.

Kiểm tra executable Java:

~~~sh
command -v java
file "$(command -v java)"
file "$JAVA_HOME/bin/java"
~~~

Trên Apple Silicon, có thể kiểm tra tiến trình có đang được dịch qua Rosetta hay không:

~~~sh
sysctl -in sysctl.proc_translated 2>/dev/null || echo 0
~~~

Giá trị 1 cho biết tiến trình hiện tại đang chạy qua Rosetta. Nếu lệnh không có trên máy hoặc không áp dụng, hãy dùng uname -m và file để xác định binary.

### 1.2. Rosetta không thay thế JDK native

Rosetta 2 cho phép chạy một số chương trình x86_64 trên Apple Silicon. Điều này hữu ích khi một build tool hoặc native dependency chưa có bản ARM64. Tuy nhiên, chạy JDK x86_64 qua Rosetta có thể làm build chậm hơn và buộc native library phải cùng kiến trúc x86_64.

Với dự án mới, ưu tiên JDK ARM64 và native dependency ARM64 trên Apple Silicon. Chỉ dùng Rosetta khi có lý do tương thích cụ thể, rồi giữ kiến trúc nhất quán cho toàn bộ tiến trình và thư viện native.

Nếu Java chạy ARM64 nhưng JNI library chỉ có x86_64, JVM không thể nạp thư viện đó. Tương tự, JDK x86_64 chạy qua Rosetta không thể nạp một native library chỉ được build cho ARM64.

## 2. Cài đặt JDK trên macOS

Có hai cách thường gặp: installer của vendor hoặc Homebrew. Cả hai có thể cùng tồn tại, nhưng cần chọn đúng JDK cho terminal, IDE và build process.

### 2.1. Cài bằng installer của vendor

Với Oracle JDK, tải package đúng kiến trúc:

- Mac Intel: file có hậu tố macos-x64.
- Apple Silicon: file có hậu tố macos-aarch64.

Installer .dmg mở một package .pkg; chạy installer và cấp quyền quản trị khi được yêu cầu. JDK được đặt trong:

~~~text
/Library/Java/JavaVirtualMachines/jdk-<FEATURE>.jdk/Contents/Home
~~~

Ví dụ JDK 24 có thể nằm trong:

~~~text
/Library/Java/JavaVirtualMachines/jdk-24.jdk/Contents/Home
~~~

Thư mục .jdk là bundle của macOS. JAVA_HOME phải trỏ vào Contents/Home, không trỏ vào thư mục .jdk bên ngoài.

Không xóa hoặc thay thế các file Java trong /usr/bin. Đây là vị trí chứa công cụ do macOS quản lý; hãy cài và gỡ JDK trong /Library/Java/JavaVirtualMachines.

### 2.2. Cài bằng Homebrew

Homebrew cung cấp OpenJDK hiện tại và các formula theo phiên bản như openjdk@21.

~~~sh
brew search openjdk
brew info openjdk@21
brew install openjdk@21
~~~

Homebrew đánh dấu các formula OpenJDK là keg-only. Điều này có nghĩa formula không tự thay thế các Java tool của hệ thống. Nếu cần các ứng dụng macOS hoặc /usr/libexec/java_home nhận diện JDK này, hãy đọc caveat do brew info openjdk@21 in ra.

Với formula openjdk@21, Homebrew hướng dẫn tạo link bundle vào thư mục JDK hệ thống:

~~~sh
sudo ln -sfn "$(brew --prefix)/opt/openjdk@21/libexec/openjdk.jdk" \
  /Library/Java/JavaVirtualMachines/openjdk-21.jdk
~~~

Lệnh này tạo symbolic link trong /Library; cần quyền quản trị. Kiểm tra đường dẫn caveat của formula trước khi chạy, nhất là khi sử dụng formula hoặc phiên bản khác.

Không hardcode Homebrew prefix. brew --prefix tự trả về prefix của cài đặt hiện tại; Apple Silicon và Intel thường có prefix mặc định khác nhau.

### 2.3. So sánh installer và Homebrew

| Tiêu chí | Installer vendor | Homebrew |
|---|---|---|
| Cài đặt | .dmg/.pkg hoặc archive | brew install |
| Vị trí thường gặp | /Library/Java/JavaVirtualMachines | Homebrew prefix |
| Nhận diện bởi java_home | Thường được nhận diện trực tiếp | Formula keg-only có thể cần link bundle |
| Cập nhật | Theo installer/release của vendor | Qua Homebrew formula |
| Chọn vendor/build | Theo nhà cung cấp package | Theo formula có sẵn |
| Quyền | Installer có thể yêu cầu admin | Cài formula vào prefix; link hệ thống có thể cần admin |

Dùng một phương thức cài đặt nhất quán trong mỗi môi trường CI để giảm khác biệt đường dẫn và cách cập nhật.

## 3. Chọn đúng JDK bằng java_home và JAVA_HOME

macOS cung cấp công cụ /usr/libexec/java_home để tìm và chọn JDK đã cài. Đây là điểm khác biệt đáng chú ý so với cách quản lý JAVA_HOME thủ công trên nhiều máy Linux.

### 3.1. Liệt kê JDK đã cài

~~~sh
/usr/libexec/java_home -V
~~~

Kiểm tra JDK mặc định:

~~~sh
java -version
javac -version
echo "$JAVA_HOME"
command -v java
command -v javac
~~~

Lưu ý: java và javac được phân giải theo PATH. Một JDK có thể đã cài nhưng không phải JDK mà terminal đang dùng.

### 3.2. Chọn một feature release

Chọn JDK 21 cho shell hiện tại:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

Chọn JDK 17 cho một lệnh riêng mà không đổi cấu hình shell:

~~~sh
/usr/libexec/java_home -v 17 --exec java -version
/usr/libexec/java_home -v 17 --exec javac -version
~~~

Cách này tiện khi phải kiểm tra cùng một project trên nhiều feature release. Nếu không có JDK phù hợp, java_home sẽ không thể trả về đường dẫn; hãy cài đúng version trước khi build.

### 3.3. Lưu cấu hình cho zsh

Các bản macOS hiện đại thường dùng zsh làm shell mặc định. Với login shell, cấu hình môi trường thường được đặt trong ~/.zprofile; cấu hình cho interactive shell thường nằm trong ~/.zshrc.

Ví dụ thêm vào file cấu hình phù hợp:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Sau khi lưu, mở terminal mới hoặc nạp lại file cấu hình:

~~~sh
source ~/.zprofile
java -version
javac -version
~~~

Chọn đúng file khởi tạo theo cách terminal được mở. Không thêm cùng một đoạn nhiều lần mỗi khi đổi JDK; sửa giá trị version tại một vị trí để tránh PATH bị lặp.

IDE mở từ Finder, ứng dụng desktop hoặc launchd có thể không nhận cùng môi trường shell như Terminal. Nếu IDE dùng sai Java, kiểm tra Project SDK/Gradle JVM/Maven JDK trong IDE và cấu hình runtime của chính ứng dụng.

## 4. Đường dẫn và biến môi trường khác Windows

macOS và Linux dùng đường dẫn kiểu POSIX; Windows dùng dấu gạch chéo ngược trong nhiều đường dẫn và dấu chấm phẩy để phân tách phần tử PATH.

| Thuộc tính | macOS/Linux | Windows |
|---|---|---|
| Dấu phân cách thư mục | / | \ |
| Phân cách phần tử PATH | : | ; |
| Biến môi trường shell | $JAVA_HOME | $env:JAVA_HOME trong PowerShell |
| JDK home phổ biến | .../Contents/Home | ...\jdk-<version> |
| Shell mặc định phổ biến | zsh | PowerShell/Command Prompt |

Trong Java, không ghép đường dẫn bằng dấu phân cách cố định. Dùng API của Java:

~~~java
import java.nio.file.Path;

public class PathProbe {
    public static void main(String[] args) {
        Path config = Path.of("config", "application.yml");
        System.out.println(config);
        System.out.println("file.separator=" + System.getProperty("file.separator"));
        System.out.println("path.separator=" + System.getProperty("path.separator"));
    }
}
~~~

Path.of("config", "application.yml") tự tạo đường dẫn phù hợp với hệ điều hành. file.separator thường là / trên macOS và Linux, và \ trên Windows; path.separator là : trên macOS/Linux và ; trên Windows.

Đừng giả định một đường dẫn tuyệt đối như /Users/alice/project hoặc C:\Users\alice\project tồn tại trên mọi runner. Dùng working directory, environment variable hoặc cấu hình theo từng nền tảng.

## 5. APFS và phân biệt chữ hoa/thường trong tên file

APFS là filesystem phổ biến trên Mac. Volume APFS mặc định là case-insensitive nhưng vẫn case-preserving: hệ thống không phân biệt chữ hoa và chữ thường khi tìm file, nhưng giữ cách viết gốc của tên file. Người dùng có thể tạo APFS volume dạng case-sensitive.

Điều này tạo ra khác biệt khi project được phát triển trên Mac và build trên Linux:

- Trên APFS mặc định, Config.java và config.java có thể trỏ tới cùng một file.
- Trên filesystem case-sensitive, hai tên đó là hai đường dẫn khác nhau.
- Một import hoặc resource path sai chữ hoa/thường có thể chạy trên máy Mac này nhưng lỗi trên Linux CI.

Dùng chính xác cùng casing trong tên file, package, resource path và câu lệnh build. Tránh tạo hai file chỉ khác chữ hoa/thường trong cùng thư mục.

Nếu cần đổi tên file chỉ khác casing trên volume mặc định, dùng tên trung gian với Git:

~~~sh
git mv Config.java Config.tmp
git mv Config.tmp config.java
~~~

Kiểm tra thay đổi trước khi commit:

~~~sh
git status --short
git diff --summary
~~~

Không dựa vào việc máy local có phân biệt casing hay không để kết luận repository portable.

## 6. Quyền thực thi và line ending của shell script

macOS dùng quyền file kiểu Unix. Script wrapper Maven/Gradle cần có executable bit để gọi trực tiếp bằng ./mvnw hoặc ./gradlew.

Nếu nhận lỗi Permission denied, kiểm tra và sửa quyền:

~~~sh
chmod +x mvnw gradlew
git add --chmod=+x mvnw gradlew
git ls-files --stage mvnw gradlew
~~~

Trong Git index, file executable thường có mode 100755. Nếu mode là 100644, checkout trên Unix có thể không chạy được bằng ./mvnw.

Shell script trên macOS cũng nên dùng line ending LF. File script có CRLF có thể gây lỗi interpreter, ví dụ đường dẫn shebang bị thêm ký tự ^M.

Có thể quy định trong .gitattributes:

~~~gitattributes
*.sh text eol=lf
mvnw text eol=lf
gradlew text eol=lf
~~~

Sau đó chuẩn hóa file đã có trong repository khi cần:

~~~sh
git add --renormalize .
git diff --cached --check
~~~

Chỉ commit thay đổi line ending khi đã xem diff để tránh tạo một commit thay đổi hàng loạt ngoài ý muốn.

## 7. BSD tools và GNU tools trên macOS

macOS có nhiều tiện ích dòng lệnh theo họ BSD. Chúng không phải lúc nào cũng hỗ trợ toàn bộ option của GNU coreutils.

Một số script chạy trên Linux có thể lỗi trên macOS vì:

- sed -i của GNU và BSD có cú pháp khác nhau.
- date -d là option thường gặp trên GNU date nhưng không tương thích với BSD date.
- readlink -f không có sẵn theo cùng cách trên mọi bản macOS.
- stat có option khác nhau giữa BSD và GNU.

Khi viết build script:

1. Ưu tiên lệnh POSIX và các option có trên các nền tảng mục tiêu.
2. Dùng Java, Python hoặc Node cho xử lý file phức tạp cần hành vi nhất quán.
3. Nếu thật sự cần GNU coreutils, khai báo dependency và cài qua Homebrew trong môi trường Mac.
4. Không giả định sed, date hoặc stat trên Mac giống hệt Linux.

Kiểm tra tool đang được gọi:

~~~sh
command -v sed
sed --version
command -v date
date
~~~

Trên BSD sed, sed --version có thể không được hỗ trợ. Đây là một ví dụ để nhận biết khác biệt implementation, không phải lệnh kiểm tra chung bắt buộc cho mọi shell script.

## 8. Native library và JNI trên macOS

Java bytecode thường chạy được trên nhiều hệ điều hành, nhưng native library không tự động portable. Thư viện JNI/JNA phải được build cho đúng OS và CPU architecture.

| Nền tảng | Định dạng native library thường gặp |
|---|---|
| macOS | .dylib |
| Linux | .so |
| Windows | .dll |

Một JAR có thể chứa nhiều native library theo classifier hoặc thư mục riêng cho từng nền tảng. Build cần chọn đúng artifact cho macOS ARM64 hay macOS x64.

Nếu JVM báo không nạp được native library:

1. Kiểm tra đường dẫn được cấu hình trong java.library.path.
2. Kiểm tra file thực tế có tồn tại và có quyền đọc hay không.
3. Kiểm tra kiến trúc của JVM và thư viện.
4. Kiểm tra các dependency động mà thư viện cần.

Trên macOS:

~~~sh
file path/to/libexample.dylib
otool -L path/to/libexample.dylib
~~~

file giúp xem kiến trúc binary; otool -L liệt kê các dynamic library dependency. Trên Linux thường dùng file và ldd; trên Windows có công cụ tương ứng như dumpbin.

Không ép mọi native library dùng chung một cache key. Cache hoặc artifact của native code cần tách theo OS, architecture, compiler/toolchain và phiên bản dependency.

## 9. Xcode Command Line Tools khi build native code

Một project Java thuần thường chỉ cần JDK để biên dịch Java. Nhưng project có JNI, C/C++, native image, một số package hoặc build script có bước gọi compiler native có thể cần Xcode Command Line Tools.

Kiểm tra:

~~~sh
xcode-select -p
clang --version
xcrun --find clang
~~~

Nếu máy chưa cài công cụ phát triển cần thiết, macOS có thể yêu cầu cài Command Line Tools:

~~~sh
xcode-select --install
~~~

Chỉ cài khi build thực sự cần compiler hoặc SDK của Apple. Không nhầm Xcode Command Line Tools với JDK; javac thuộc JDK, còn clang là compiler native.

Khi build native library cho Apple Silicon và Intel, chạy build trên từng kiến trúc hoặc cấu hình cross-compilation có chủ đích. Không coi một binary ARM64 là artifact dùng được cho runner Intel.

## 10. Gatekeeper, code signing và notarization

macOS có Gatekeeper để kiểm tra phần mềm tải từ bên ngoài Mac App Store. Installer, ứng dụng desktop và plugin native được phân phối cho người dùng Mac cần quan tâm tới Developer ID code signing và notarization.

Điều này đặc biệt quan trọng khi dùng jpackage để đóng gói ứng dụng Java thành .app hoặc installer .pkg.

- **Code signing** gắn chữ ký để xác định nhà phát hành và kiểm tra nội dung đã ký.
- **Notarization** gửi phần mềm đã ký tới Apple để hệ thống tự động kiểm tra các vấn đề bảo mật và code signing.
- **Gatekeeper** sử dụng thông tin chữ ký/notarization để quyết định cách cảnh báo và cho phép mở phần mềm.
- Notarization không phải App Review.

Với installer hoặc app bundle tải từ vendor, hãy dùng nguồn chính thức và kiểm tra chữ ký. Không tắt Gatekeeper hoặc xóa quarantine attribute như cách xử lý mặc định cho lỗi cài đặt. Nếu phần mềm hợp lệ bị chặn, kiểm tra chữ ký, notary status và hướng dẫn của nhà phát hành.

Một số lệnh kiểm tra:

~~~sh
pkgutil --check-signature path/to/jdk-installer.pkg
codesign --verify --deep --strict --verbose=2 path/to/MyApp.app
spctl --assess --type execute --verbose path/to/MyApp.app
~~~

Với ứng dụng Java được phân phối bên ngoài tổ chức, quy trình release thường cần:

1. Build ứng dụng và native dependency cho đúng kiến trúc.
2. Tạo app bundle hoặc installer.
3. Ký các executable và bundle theo đúng thứ tự.
4. Notarize bằng Apple notary service.
5. Staple ticket khi loại deliverable hỗ trợ.
6. Kiểm tra lại trên một máy Mac sạch trước khi phát hành.

Không đưa private signing key, certificate password hoặc notarization credentials vào source repository hay cache build công khai. Lưu chúng trong secret store của CI và giới hạn job có quyền sử dụng.

## 11. Dịch vụ nền trên macOS dùng launchd

Linux thường dùng systemd cho service; macOS dùng launchd cho LaunchAgent và LaunchDaemon.

Một Java service chạy từ Terminal có thể hoạt động nhưng thất bại khi được khởi chạy bởi launchd. Nguyên nhân phổ biến là môi trường khác nhau:

- PATH ngắn hơn shell interactive.
- JAVA_HOME chưa được khai báo.
- Working directory khác với project directory.
- File hoặc thư mục log không có quyền ghi.
- Service không được phép truy cập một số vị trí người dùng.

Trong plist, khai báo rõ đường dẫn executable, arguments, working directory và environment cần thiết. Có thể gọi Java bằng đường dẫn tuyệt đối dưới JDK home thay vì trông chờ shell profile được nạp.

Ví dụ đường dẫn executable:

~~~text
/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/bin/java
~~~

Kiểm tra service bằng công cụ launchctl. Đừng dùng systemctl trên macOS.

## 12. GitHub Actions: kiểm thử macOS Intel và Apple Silicon

Runner macOS có thể khác nhau về hệ điều hành, CPU architecture, Xcode và các tool được cài sẵn. Với GitHub-hosted runners, label macos-26 hiện chỉ Apple Silicon ARM64, còn macos-26-intel dành cho x64.

Ví dụ matrix kiểm thử Java trên Linux, Windows, macOS ARM64 và macOS Intel:

~~~yaml
name: Cross-platform Java

on:
  push:
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: ubuntu-24.04
          - os: windows-2025
          - os: macos-26
          - os: macos-26-intel

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'

      - name: Inspect Java toolchain
        shell: bash
        run: |
          java -version
          javac -version
          java -XshowSettings:properties -version

      - name: Build and test
        shell: bash
        run: ./mvnw --batch-mode verify
~~~

Trong matrix này:

- macos-26 chạy trên Apple Silicon ARM64.
- macos-26-intel chạy trên Intel x64.
- ubuntu-24.04 và windows-2025 kiểm tra khác biệt Linux/Windows.
- setup-java cài cùng vendor và Java feature release để so sánh kết quả công bằng.
- java -XshowSettings:properties -version in thông tin runtime để đối chiếu java.home, java.vendor và os.arch.

Runner label và image được nền tảng cập nhật theo thời gian. Pin label cụ thể khi cần môi trường ổn định; theo dõi lịch retire/upgrade của runner image trước khi nâng phiên bản.

Nếu workflow chỉ cần test Java bytecode, không cần đóng gói native library, một matrix ARM64/x64 có thể giúp phát hiện lỗi kiến trúc. Nếu ứng dụng có JNI hoặc package .app, hãy chạy thêm kiểm thử và packaging trên từng kiến trúc đích.

## 13. Ví dụ Java 17+ kiểm tra môi trường chạy

Chương trình sau in ra các thuộc tính cần đối chiếu khi chuyển project giữa macOS, Linux và Windows.

Tạo file MacEnvironmentProbe.java:

~~~java
public class MacEnvironmentProbe {
    public static void main(String[] args) {
        String[] keys = {
            "os.name",
            "os.version",
            "os.arch",
            "java.version",
            "java.vendor",
            "java.home",
            "file.separator",
            "path.separator",
            "line.separator"
        };

        for (String key : keys) {
            String value = System.getProperty(key)
                .replace("\n", "\\n")
                .replace("\r", "\\r");
            System.out.println(key + "=" + value);
        }
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac --release 17 MacEnvironmentProbe.java
java MacEnvironmentProbe
~~~

Các giá trị quan trọng cần quan sát trên Mac:

- os.name nhận diện macOS.
- os.arch phản ánh kiến trúc của JVM đang chạy; giá trị cụ thể có thể khác theo vendor.
- java.home cho biết JDK mà tiến trình thực sự dùng.
- file.separator và path.separator thể hiện khác biệt về đường dẫn.
- line.separator cho biết line ending của runtime.

Không hardcode output của một máy vào test. Hãy dùng các property này để chọn hành vi theo nền tảng hoặc in diagnostics khi CI gặp lỗi.

## 14. Lỗi thường gặp khi chuyển project sang macOS

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Unable to locate a Java Runtime | Chưa cài JDK hoặc Java launcher không tìm thấy JDK | Cài đúng package, kiểm tra /usr/libexec/java_home -V |
| Terminal dùng sai Java version | PATH trỏ tới JDK khác | Chọn JAVA_HOME và kiểm tra command -v java |
| Homebrew JDK không xuất hiện trong java_home | Formula là keg-only | Đọc brew info và link bundle theo caveat |
| Bad CPU type in executable | Binary x86_64/ARM64 không phù hợp với tiến trình hoặc máy | Kiểm tra uname -m, file và dùng đúng JDK |
| JNI báo Library not loaded | Thiếu dependency .dylib, sai rpath hoặc sai kiến trúc | Dùng otool -L và file |
| ./mvnw: Permission denied | Wrapper thiếu executable bit | chmod +x mvnw và commit mode 100755 |
| Shell báo lỗi tại cuối dòng lạ | Script có CRLF hoặc shebang không hợp lệ | Chuẩn hóa LF bằng .gitattributes |
| Build chạy trên Mac nhưng lỗi Linux CI | Filesystem local không phân biệt casing | Kiểm tra chính xác tên file và resource path |
| Script chạy trên Linux nhưng lỗi trên Mac | Dùng GNU-only option của sed, date hoặc stat | Dùng POSIX-compatible commands hoặc dependency rõ ràng |
| IDE dùng JDK khác Terminal | Project SDK hoặc Gradle/Maven JVM được cấu hình riêng | Chọn JDK trong IDE và kiểm tra runtime của build tool |
| Ứng dụng bị Gatekeeper cảnh báo | Package/app không có chữ ký hoặc notarization hợp lệ | Xác minh nguồn tải, chữ ký và trạng thái notarization |
| Service không thấy JAVA_HOME | launchd không nạp shell profile | Khai báo environment và executable path trong service config |

## 15. Quy trình kiểm tra project Java trên Mac

1. Chạy sw_vers và uname -m để biết OS và kiến trúc.
2. Chạy /usr/libexec/java_home -V để xem các JDK đã cài.
3. Chọn JDK phù hợp bằng JAVA_HOME và xác minh java -version, javac -version.
4. Kiểm tra executable Java có kiến trúc phù hợp bằng file.
5. Kiểm tra wrapper Maven/Gradle có executable bit và line ending LF.
6. Kiểm tra tên file/resource có casing chính xác để chạy được trên Linux.
7. Kiểm tra native dependency .dylib và kiến trúc nếu project dùng JNI/JNA.
8. Kiểm tra Xcode Command Line Tools nếu build có bước native.
9. Kiểm tra signing/notarization nếu tạo app bundle hoặc installer để phân phối.
10. Chạy test trên macOS ARM64 và Intel nếu hỗ trợ cả hai.
11. Chạy lại build trên Linux và Windows để phát hiện giả định riêng của Mac.
12. Ghi rõ JDK vendor/version/architecture trong tài liệu build và CI.

### Checklist

- [ ] Đã xác định Mac là Intel x64 hay Apple Silicon ARM64.
- [ ] Đã cài đúng JDK package cho kiến trúc.
- [ ] Đã kiểm tra đường dẫn .jdk/Contents/Home.
- [ ] Đã biết cách liệt kê và chọn JDK bằng /usr/libexec/java_home.
- [ ] Đã kiểm tra JAVA_HOME, PATH, java và javac.
- [ ] Đã phân biệt Homebrew keg-only với JDK cài bằng installer.
- [ ] Đã tránh trộn ARM64 và x86_64 JDK/native library.
- [ ] Đã kiểm tra path separator và file separator bằng Java API.
- [ ] Đã giữ executable bit và LF cho Maven/Gradle wrapper.
- [ ] Đã kiểm tra casing của file/resource trên filesystem.
- [ ] Đã kiểm tra BSD/GNU command compatibility.
- [ ] Đã kiểm tra JNI/JNA dependency và .dylib nếu có.
- [ ] Đã xác minh chữ ký/notarization cho app hoặc installer được phân phối.
- [ ] Đã chạy CI trên macOS ARM64 và Intel nếu là nền tảng mục tiêu.

Khác biệt macOS ảnh hưởng trực tiếp tới cách JDK được cài và chọn, kiến trúc binary, shell environment, filesystem và native dependency. Dùng java_home để chọn JDK, xác minh kiến trúc trước khi nạp native library, giữ script portable và kiểm thử trên cả ARM64 lẫn x64 khi dự án hỗ trợ hai loại Mac.

## Tài liệu tham khảo

- [Oracle JDK 24 — Installation of the JDK on macOS](https://docs.oracle.com/en/java/javase/24/install/installation-jdk-macos.html)
- [Homebrew — Language Runtimes and Packages: Java](https://docs.brew.sh/Language-Runtimes-and-Packages#java)
- [Homebrew Formulae — openjdk@21](https://formulae.brew.sh/formula/openjdk@21)
- [Apple Developer — Notarizing macOS Software Before Distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Apple Developer — Signing Mac Software with Developer ID](https://developer.apple.com/developer-id/)
- [Apple Support — APFS formats, including case-sensitive volumes](https://support.apple.com/guide/disk-utility/dsku19ed921c/mac)
- [GitHub — Actions Runner Images and macOS architectures](https://github.com/actions/runner-images)