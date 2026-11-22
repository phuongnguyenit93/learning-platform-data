# Tương thích môi trường: hệ điều hành, kiến trúc và thư viện native

Trong một đợt nâng cấp hoặc di chuyển ứng dụng Java, mã nguồn và bytecode có thể chạy trên nhiều nền tảng, nhưng toàn bộ ứng dụng vẫn có thể phụ thuộc vào hệ điều hành, kiến trúc CPU và thư viện native bên dưới. Một ứng dụng chạy ổn trên Windows x86_64 chưa chắc chạy được trên Linux ARM64; một JAR giống hệt nhau có thể hoạt động trên máy phát triển nhưng thất bại trong container Alpine vì thư viện native được biên dịch cho glibc thay vì musl.

Bài học này trình bày cách nhận diện các ranh giới tương thích đó, cách tổ chức dependency và đóng gói, cũng như cách kiểm tra ứng dụng khi chuyển môi trường.

## 1. Hiểu đúng các lớp tương thích

Java cung cấp tính di động ở lớp ngôn ngữ và bytecode. Một file .class hoặc JAR thuần Java thường có thể chạy trên nhiều hệ điều hành và kiến trúc nếu runtime đáp ứng đúng phiên bản Java và các API mà ứng dụng yêu cầu. Tuy nhiên, tính di động này không tự động bao phủ mọi thành phần đi kèm ứng dụng.

| Lớp | Thành phần cần tương thích | Ví dụ lỗi khi di chuyển |
|---|---|---|
| Java runtime | Phiên bản Java, API, module, JVM vendor và tùy chọn khởi chạy | Ứng dụng biên dịch bằng API mới nhưng chạy trên JRE cũ |
| Hệ điều hành | API hệ thống, đường dẫn, quyền, tiến trình, biến môi trường và hành vi filesystem | Gọi lệnh bash trên Windows hoặc dùng đường dẫn cố định kiểu Unix |
| Kiến trúc CPU | Tập lệnh, kích thước con trỏ và định dạng binary | JVM ARM64 cố nạp thư viện DLL hoặc SO x86_64 |
| ABI và thư viện native | Định dạng thư viện, calling convention, libc và các dependency native bắc cầu | Thư viện SO được liên kết với glibc không nạp được trên môi trường chỉ có musl |
| Đóng gói và triển khai | JAR, native bundle, image container, đường dẫn thư viện và cấu hình runtime | JAR có mặt nhưng file native cần thiết không được đưa vào image |

Khi điều tra lỗi, hãy xác định lớp nào đang không tương thích. Thông báo lỗi có thể xuất hiện ở Java, nhưng nguyên nhân nằm trong dynamic linker của hệ điều hành hoặc trong binary native được đóng gói.

Một nguyên tắc hữu ích là phân biệt ba câu hỏi:

1. **JVM có chạy được ứng dụng không?** Kiểm tra phiên bản Java, bytecode target, module và tùy chọn runtime.
2. **JVM có tương tác được với môi trường không?** Kiểm tra filesystem, tiến trình, quyền, encoding và các API hệ điều hành.
3. **Các thành phần native có nạp và chạy được không?** Kiểm tra OS, CPU architecture, ABI và dependency native bắc cầu.

## 2. Tương thích hệ điều hành

### 2.1. Những khác biệt thường gặp

Các hệ điều hành cung cấp những quy ước và dịch vụ khác nhau. Dù Java che giấu nhiều khác biệt, ứng dụng vẫn có thể gặp vấn đề ở các điểm sau:

- **Đường dẫn:** Windows thường dùng ký tự ổ đĩa và dấu \; Linux và macOS thường dùng dấu /. Windows còn có đường dẫn UNC như \\\\server\\share.
- **Phân biệt chữ hoa và chữ thường:** Filesystem trên Linux thường phân biệt Config.properties với config.properties. Một số cấu hình Windows và macOS không phân biệt; cấu hình cụ thể có thể thay đổi.
- **Quyền truy cập:** Unix-like sử dụng mô hình quyền và owner/group; Windows sử dụng ACL. Cách xử lý symbolic link, file lock và quyền thực thi cũng khác nhau.
- **Tiến trình và shell:** Tên executable, cú pháp shell, cách trích dẫn tham số và biến môi trường không giống nhau. bash, sh, cmd.exe và PowerShell không thể thay thế lẫn nhau.
- **Dòng kết thúc và encoding:** File có thể dùng LF hoặc CRLF. Encoding mặc định và cấu hình locale có thể khác giữa máy phát triển, máy chủ và container.
- **Dịch vụ hệ thống:** Cách cài đặt service, gửi tín hiệu, quản lý tiến trình và cấu hình startup phụ thuộc nền tảng.

Các khác biệt này thường không lộ ra trong unit test chạy trên một máy duy nhất. Chúng xuất hiện khi ứng dụng đọc file do hệ thống khác tạo, khởi chạy tiến trình ngoài, ghi dữ liệu vào thư mục triển khai hoặc chạy bằng tài khoản dịch vụ có quyền hạn khác.

### 2.2. Dùng API Java đa nền tảng

Ưu tiên API chuẩn của Java để thao tác với filesystem và tiến trình.

Dùng Path và Files thay vì ghép chuỗi đường dẫn:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path configDirectory = Path.of("config");
Path configFile = configDirectory.resolve("application.properties");

if (Files.isRegularFile(configFile)) {
    String content = Files.readString(configFile);
    System.out.println(content);
}
```

Path.resolve tự xử lý dấu phân cách phù hợp với filesystem hiện tại. Trong ứng dụng cần hỗ trợ Java cũ hơn Java 11, có thể dùng Files.readAllBytes hoặc Files.newBufferedReader thay cho Files.readString.

Không giả định thư mục làm việc hiện tại là thư mục chứa JAR. Working directory phụ thuộc cách người dùng khởi chạy ứng dụng, service manager, IDE hoặc container. Hãy xác định rõ thư mục cấu hình và dữ liệu thông qua tham số khởi chạy, biến môi trường hoặc cấu hình triển khai.

Nếu phải khởi chạy chương trình bên ngoài, dùng ProcessBuilder với từng tham số riêng:

```java
import java.io.IOException;
import java.util.List;

List<String> command = List.of(
    "git",
    "rev-parse",
    "--show-toplevel"
);

Process process = new ProcessBuilder(command)
    .redirectOutput(ProcessBuilder.Redirect.INHERIT)
    .redirectError(ProcessBuilder.Redirect.INHERIT)
    .start();

int exitCode;
try {
    exitCode = process.waitFor();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IOException("Interrupted while waiting for command", e);
}

if (exitCode != 0) {
    throw new IOException("External command failed: " + exitCode);
}
```

Ví dụ trên minh họa cách truyền command và argument tách biệt, đồng thời chuyển output về tiến trình cha để tránh buffer stdout/stderr đầy khi chờ. Trong ứng dụng thực tế, cần kiểm tra command có được cài đặt và có trong PATH của tài khoản chạy ứng dụng hay không.

Tránh ghép toàn bộ lệnh thành một chuỗi rồi đưa qua shell, chẳng hạn sh -c hoặc cmd /c, trừ khi thực sự cần cú pháp shell. Cách làm đó tạo thêm khác biệt về quoting, escaping và injection. Nếu cần gọi công cụ theo từng nền tảng, đóng gói phần lựa chọn command trong một adapter riêng và kiểm tra adapter trên từng OS được hỗ trợ.

### 2.3. Encoding và nội dung văn bản

Đừng dựa vào charset mặc định của máy khi đọc hoặc ghi dữ liệu trao đổi giữa các hệ thống. Hãy chỉ định charset rõ ràng:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
    Path.of("data.txt"),
    StandardCharsets.UTF_8
);

Files.writeString(
    Path.of("result.txt"),
    text,
    StandardCharsets.UTF_8
);
```

Java 18 trở lên mặc định dùng UTF-8 cho charset mặc định trong các môi trường thông thường, nhưng ứng dụng di chuyển giữa nhiều phiên bản Java vẫn nên khai báo charset ở ranh giới đọc/ghi dữ liệu. Cần phân biệt charset của nội dung với line separator của hệ điều hành. Khi xử lý định dạng dữ liệu có quy định newline cụ thể, hãy tuân theo định dạng đó thay vì tự động thay thế mọi dòng bằng System.lineSeparator().

### 2.4. Khi nào cần nhận diện OS?

Nếu dùng API Java chuẩn thì thường không cần phân nhánh theo OS. Chỉ nhận diện OS khi ứng dụng thật sự phải chọn binary, command hoặc cấu hình riêng cho từng nền tảng.

Có thể thu thập thông tin môi trường bằng các system property:

```java
String osName = System.getProperty("os.name", "unknown");
String osVersion = System.getProperty("os.version", "unknown");
String architecture = System.getProperty("os.arch", "unknown");

System.out.println("OS: " + osName);
System.out.println("OS version: " + osVersion);
System.out.println("Architecture: " + architecture);
```

Các giá trị này hữu ích cho chẩn đoán và chọn gói native, nhưng không nên dùng một phép so sánh chuỗi đơn giản để quyết định mọi hành vi. Tên OS có thể khác giữa các vendor và phiên bản. Nếu phải phân loại, hãy chuẩn hóa giá trị tại một vị trí duy nhất, xử lý rõ các nền tảng được hỗ trợ và từ chối có thông báo với nền tảng chưa hỗ trợ.

Không nên giả định rằng mọi hệ thống có tên chứa Linux đều có cùng libc, package manager hoặc bộ thư viện hệ thống. OS name không đủ để kết luận ABI tương thích.

## 3. Tương thích kiến trúc CPU

### 3.1. JVM và kiến trúc tiến trình

Một JVM được xây dựng cho một kiến trúc CPU cụ thể. Mã Java thuần thường không cần biên dịch riêng cho x86_64 và ARM64, nhưng JVM và thư viện native thì cần binary phù hợp.

Các tên kiến trúc thường gặp gồm:

| Nhóm | Tên có thể xuất hiện | Ghi chú |
|---|---|---|
| x86 64-bit | amd64, x86_64, đôi khi x64 | Các tên này thường chỉ cùng nhóm kiến trúc |
| ARM 64-bit | aarch64, arm64 | Phổ biến trên máy chủ ARM và máy Apple Silicon |
| x86 32-bit | x86, i386, i686 | Có giới hạn về không gian địa chỉ và khả năng hỗ trợ của runtime |
| ARM 32-bit | arm, armv7l | Cần xác định đúng ABI và biến thể ARM |

Giá trị os.arch phản ánh kiến trúc mà JVM đang chạy hoặc được nhận diện, không nhất thiết là kiến trúc vật lý của máy chủ. Ví dụ, JVM x86_64 có thể chạy trong môi trường giả lập trên máy ARM64. Khi đó thư viện native phải phù hợp với JVM process, không chỉ với CPU vật lý.

Vì vậy, cần kiểm tra kiến trúc ở đúng nơi ứng dụng thực thi: máy developer, runner CI, image container và máy triển khai. Không nên suy ra kiến trúc từ tên máy hoặc từ kiến trúc của máy build.

### 3.2. Vì sao kiến trúc ảnh hưởng đến native code?

Binary native chứa mã máy và tuân theo quy ước ABI của nền tảng. Một thư viện x86_64 không thể được nạp trực tiếp vào JVM ARM64 chỉ vì cả hai đều chạy cùng hệ điều hành. Tương tự, thư viện 32-bit và 64-bit thường không thể trộn trong cùng một tiến trình.

Các khác biệt liên quan gồm:

- Tập lệnh CPU và các extension mà binary sử dụng.
- Kích thước con trỏ, kiểu dữ liệu phụ thuộc nền tảng và alignment.
- Calling convention và quy tắc truyền tham số giữa Java và native code.
- Định dạng binary và loader của hệ điều hành.
- ABI của compiler, runtime C/C++ và các thư viện mà binary liên kết.

Không nên tự suy luận rằng mọi CPU ARM64 đều tương thích với mọi binary ARM64 trong mọi môi trường. Phiên bản instruction set, ABI, hệ điều hành và các thư viện phụ thuộc vẫn cần khớp.

### 3.3. Chuẩn hóa tên kiến trúc

Nếu cần ánh xạ tên kiến trúc sang tên classifier nội bộ, hãy chuẩn hóa một lần và xử lý trường hợp không biết:

```java
import java.util.Locale;

static String normalizedArchitecture() {
    String arch = System.getProperty("os.arch", "")
        .toLowerCase(Locale.ROOT);

    if ("amd64".equals(arch)
            || "x86_64".equals(arch)
            || "x64".equals(arch)) {
        return "x86_64";
    }

    if ("aarch64".equals(arch) || "arm64".equals(arch)) {
        return "aarch64";
    }

    if ("x86".equals(arch)
            || "i386".equals(arch)
            || "i486".equals(arch)
            || "i586".equals(arch)
            || "i686".equals(arch)) {
        return "x86";
    }

    throw new UnsupportedOperationException(
        "Unsupported CPU architecture: " + arch
    );
}
```

Danh sách alias cần dựa trên các JVM và nền tảng mà sản phẩm cam kết hỗ trợ. Không nên tự động coi một giá trị chưa biết là x86_64 hoặc ARM64; điều đó có thể khiến ứng dụng chọn nhầm binary rồi thất bại ở bước nạp thư viện.

## 4. Thư viện native và ABI

### 4.1. Native library là gì?

Thư viện native là mã đã biên dịch cho hệ điều hành và kiến trúc cụ thể. Java thường gặp native code qua các cơ chế sau:

- **JNI (Java Native Interface):** Cho phép Java gọi hàm native và native code tương tác với JVM.
- **JNA (Java Native Access):** Cung cấp lớp truy cập thư viện native thông qua cơ chế ánh xạ hàm và kiểu dữ liệu.
- **Foreign Function & Memory API:** Cung cấp API Java để làm việc với hàm và bộ nhớ ngoài JVM; khả năng sử dụng phụ thuộc phiên bản Java mà ứng dụng hỗ trợ.
- **Dependency gián tiếp:** Một thư viện Java có thể tự tải native binary bên trong hoặc phụ thuộc vào một thư viện native khác mà ứng dụng không gọi trực tiếp.

Một dependency được khai báo trong Maven hoặc Gradle không có nghĩa mọi binary cần thiết đã được đóng gói đúng. Cần kiểm tra cả artifact Java, artifact native theo nền tảng và các thư viện hệ thống mà binary native tiếp tục phụ thuộc.

### 4.2. Tên file và cơ chế nạp thư viện

Tên thư viện native thường khác nhau theo OS:

| Hệ điều hành | Định dạng thường gặp | Ví dụ |
|---|---|---|
| Windows | DLL | engine.dll |
| Linux | ELF shared object | libengine.so |
| macOS | Mach-O dynamic library | libengine.dylib |

Với JNI, System.loadLibrary("engine") yêu cầu JVM tìm thư viện theo tên logic và quy ước của nền tảng. JVM sử dụng cơ chế tìm kiếm thư viện native của runtime, trong đó có java.library.path; sau đó dynamic loader của OS còn phải tìm được các dependency bắc cầu của thư viện.

System.load("/absolute/path/to/library") tải thư viện từ một đường dẫn tuyệt đối. Cách này hữu ích khi ứng dụng tự quản lý việc giải nén native resource. Đường dẫn phải trỏ đến binary đúng định dạng và đúng kiến trúc cho JVM đang chạy.

Một lỗi như UnsatisfiedLinkError có thể có nhiều nguyên nhân:

- Không tìm thấy file thư viện.
- File có mặt nhưng sai OS hoặc kiến trúc.
- Không tương thích ABI hoặc phiên bản libc.
- Thiếu một dependency native mà thư viện chính cần.
- JVM không tìm thấy symbol hoặc hàm được yêu cầu.
- Quyền truy cập hoặc chính sách bảo mật ngăn việc nạp file.

Do đó, chỉ kiểm tra sự tồn tại của file DLL, SO hoặc dylib là chưa đủ.

### 4.3. ABI và dependency hệ thống

ABI (Application Binary Interface) quy định cách binary tương tác với hệ điều hành, compiler runtime và các binary khác. Hai thư viện cùng kiến trúc và cùng OS vẫn có thể không tương thích ABI.

Một số tình huống cần chú ý:

- **Linux glibc và musl:** Nhiều bản phân phối Linux dùng glibc, trong khi Alpine Linux thường dùng musl. Thư viện native liên kết động với glibc không mặc nhiên chạy được trong image chỉ có musl.
- **Phiên bản glibc:** Binary được build trên môi trường mới có thể yêu cầu symbol hoặc phiên bản glibc mới hơn môi trường đích.
- **Windows C/C++ runtime:** DLL có thể phụ thuộc Microsoft Visual C++ Runtime hoặc các runtime khác cần được cài đặt/đóng gói đúng cách.
- **macOS deployment target:** Binary có thể yêu cầu phiên bản macOS mới hơn phiên bản đang chạy. Universal binary có thể chứa nhiều slice kiến trúc, nhưng vẫn phải đáp ứng deployment target và dependency.
- **Dependency native bắc cầu:** Một thư viện SO có thể nạp được nhưng thất bại khi loader không tìm thấy một SO khác mà nó phụ thuộc.

Khi chuyển môi trường, hãy kiểm tra binary được build trên nền tảng nào, dùng compiler/runtime nào và yêu cầu phiên bản hệ thống tối thiểu ra sao. Build trên một môi trường cũ hơn nhưng vẫn được hỗ trợ có thể giúp tăng khả năng tương thích, miễn là quy trình build được kiểm soát và xác minh.

### 4.4. Đóng gói native dependency theo nền tảng

Có ba cách tổ chức phổ biến:

1. **Artifact riêng cho từng nền tảng:** Ví dụ, mỗi tổ hợp OS và architecture có một artifact native riêng. Build hoặc dependency resolution chọn đúng artifact khi tạo gói chạy.
2. **Một artifact chứa nhiều native binary:** JAR hoặc bundle chứa nhiều thư viện; loader của ứng dụng chọn đúng resource theo OS và architecture.
3. **Cài native library ở cấp hệ thống:** Máy triển khai hoặc image container cài dependency native bên ngoài JAR. Cách này yêu cầu tài liệu triển khai và môi trường runtime phải đồng bộ.

Tên artifact minh họa có thể theo mẫu:

```text
engine-native-windows-x86_64
engine-native-linux-x86_64
engine-native-linux-aarch64
engine-native-macos-aarch64
```

Đây là quy ước đặt tên ví dụ, không phải tên artifact chuẩn của Maven. Dự án cần chọn một quy ước ổn định và ánh xạ nó với đúng binary, ABI và phiên bản thư viện.

Với Maven hoặc Gradle, có thể dùng profile, classifier, variant hoặc module dependency riêng để chọn native artifact. Việc lựa chọn nên diễn ra trong build/package process có thể tái lập. Nếu ứng dụng cần chạy trên nhiều nền tảng từ cùng một gói, bundle tất cả native resource cần thiết và chọn đúng resource khi chạy.

Không nên chỉ dựa vào profile của máy build nếu sản phẩm được build trên một OS nhưng triển khai sang OS khác. Khi đó build có thể vô tình đóng gói binary của máy build thay vì binary của môi trường đích. Hãy phân biệt rõ **build platform** và **target platform**.

### 4.5. Giải nén native resource từ JAR

Một resource nằm trong JAR không phải lúc nào cũng có đường dẫn file thông thường. Nếu API native loader cần một file thật, ứng dụng phải đọc resource stream và giải nén nó ra một vị trí trên filesystem trước khi gọi System.load.

Ví dụ minh họa:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

static Path extractNativeLibrary(String resourceName, String fileName)
        throws IOException {
    Path directory = Files.createTempDirectory("myapp-native-");
    Path library = directory.resolve(fileName);

    try (InputStream input =
            NativeLoader.class.getResourceAsStream(resourceName)) {
        if (input == null) {
            throw new IOException(
                "Native resource not found: " + resourceName
            );
        }

        Files.copy(
            input,
            library,
            StandardCopyOption.REPLACE_EXISTING
        );
    }

    return library.toAbsolutePath();
}
```

Sau khi giải nén, có thể tải bằng System.load(libraryPath.toString()). Ví dụ chỉ minh họa bước giải nén; ứng dụng hoàn chỉnh còn phải chọn resourceName và fileName theo OS/architecture, xử lý lỗi nạp thư viện và quản lý vòng đời file.

Khi thiết kế loader, cần lưu ý:

- Tên resource phải xác định đúng tổ hợp OS, architecture và ABI.
- Thư mục giải nén phải cho phép tài khoản ứng dụng ghi và đọc.
- Không dùng tên file cố định chung cho nhiều phiên bản hoặc nhiều tiến trình có thể chạy đồng thời.
- Nếu cache native library, khóa cache nên bao gồm phiên bản thư viện và nền tảng; cần xử lý trường hợp file cache bị thiếu, hỏng hoặc không còn tương thích.
- Trên Windows, file đang được nạp thường bị khóa và khó xóa ngay; trên Unix-like, hành vi xóa file đã nạp có thể khác. Không dựa vào một quy trình cleanup duy nhất cho mọi OS.
- Không giải nén từ dữ liệu không tin cậy rồi nạp như mã thực thi. Binary native phải đến từ artifact đã được kiểm soát và xác minh tính toàn vẹn.

## 5. Các yếu tố môi trường thường bị bỏ sót khi migration

Ngay cả khi OS, architecture và native library đã khớp, ứng dụng vẫn có thể hành xử khác do cấu hình runtime.

### 5.1. Phiên bản và bản phân phối Java

Kiểm tra phiên bản Java thực tế bằng:

```shell
java -version
```

Trong môi trường có nhiều JDK, lệnh java trong PATH có thể không phải JDK mà build tool hoặc service đang dùng. Hãy ghi nhận JAVA_HOME, đường dẫn executable và vendor của runtime trong log khởi động.

Ngoài phiên bản ngôn ngữ, cần kiểm tra:

- Bytecode target và API tối thiểu mà ứng dụng sử dụng.
- Module có mặt trong runtime image hay không.
- JVM options có còn hợp lệ trên phiên bản mới không.
- Native access, security policy hoặc các tùy chọn liên quan đến native loading có thay đổi giữa các phiên bản hay không.
- Vendor và cách build JVM có cung cấp đúng kiến trúc, TLS provider và thành phần cần thiết không.

### 5.2. Locale, timezone và charset

Ứng dụng có thể tạo kết quả khác nhau nếu dựa vào locale hoặc timezone mặc định của máy. Ví dụ, định dạng ngày, dấu thập phân và cách chuyển chữ hoa/thường có thể thay đổi theo locale.

Khi dữ liệu cần định dạng ổn định, hãy chỉ định rõ Locale, ZoneId và Charset:

```java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);

String date = formatter.format(
    java.time.LocalDate.now(ZoneId.of("UTC"))
);
```

Chọn timezone theo nghiệp vụ. Không mặc định UTC là timezone phù hợp cho mọi hiển thị, nhưng nên dùng timezone xác định cho dữ liệu lưu trữ và trao đổi nếu thiết kế hệ thống yêu cầu.

### 5.3. Biến môi trường, thư mục tạm và quyền

Ứng dụng chạy bằng tài khoản service có thể có PATH, HOME, thư mục tạm và quyền truy cập khác người dùng đăng nhập. Không giả định ứng dụng có thể ghi vào thư mục cài đặt, thư mục gốc hoặc bất kỳ vị trí nào trên filesystem.

Dùng java.io.tmpdir hoặc API phù hợp để tìm thư mục tạm; kiểm tra quyền ghi thực tế tại nơi ứng dụng cần lưu dữ liệu. Cấu hình nhạy cảm nên được truyền bằng cơ chế quản lý secret của môi trường triển khai, không đóng cứng vào JAR hoặc native bundle.

### 5.4. TLS, chứng thư và mạng

Trust store, chứng thư CA, proxy, DNS và chính sách TLS có thể khác giữa máy developer, container và máy chủ. Một kết nối HTTPS thất bại sau migration có thể do trust store hoặc chứng thư hệ thống, dù mã Java không thay đổi.

Hãy kiểm tra trust store mà JVM thực sự sử dụng, cấu hình proxy và khả năng phân giải DNS trong đúng môi trường chạy. Tránh tắt xác minh chứng thư để xử lý tạm thời lỗi môi trường.

## 6. Lập ma trận tương thích trước khi di chuyển

Trước khi thay đổi dependency hoặc pipeline, lập ma trận các môi trường mà sản phẩm phải hỗ trợ. Không cần kiểm thử mọi tổ hợp tưởng tượng; hãy ghi rõ các tổ hợp được cam kết và các tổ hợp bị loại trừ.

Ví dụ ma trận minh họa:

| OS | Architecture | Java runtime | Native variant | Trạng thái cần xác nhận |
|---|---|---|---|---|
| Windows Server | x86_64 | Phiên bản Java được sản phẩm hỗ trợ | Windows x86_64 | Build, load và integration test |
| Linux dùng glibc | x86_64 | Phiên bản Java được sản phẩm hỗ trợ | Linux x86_64 / glibc | Kiểm tra phiên bản glibc và dependency |
| Linux dùng glibc | aarch64 | Phiên bản Java được sản phẩm hỗ trợ | Linux aarch64 / glibc | Xác minh binary ARM64 |
| Linux Alpine | x86_64 hoặc aarch64 | Phiên bản Java phù hợp image | Binary tương thích musl hoặc phương án thay thế | Kiểm tra ABI thực tế |
| macOS | aarch64 | Phiên bản Java được sản phẩm hỗ trợ | macOS ARM64 hoặc universal | Kiểm tra deployment target |

Các dòng trên là ví dụ để lập kế hoạch, không xác nhận rằng một sản phẩm cụ thể đã hỗ trợ những nền tảng đó. Chỉ đánh dấu hỗ trợ sau khi dependency, packaging và test đã được xác minh.

Ma trận nên ghi thêm phiên bản OS tối thiểu, phiên bản Java tối thiểu, libc hoặc runtime C/C++ nếu có, loại image container, và nguồn cung cấp binary native. Khi một tổ hợp không được hỗ trợ, tài liệu triển khai cần nêu rõ thay vì để lỗi xuất hiện ngẫu nhiên ở production.

## 7. Quy trình migration có kiểm soát

### Bước 1: Kiểm kê dependency và điểm phụ thuộc môi trường

Tìm các dấu hiệu cho thấy ứng dụng phụ thuộc nền tảng:

- Lời gọi System.load hoặc System.loadLibrary.
- Các dependency JNI/JNA/FFM hoặc thư viện có native component.
- Các file DLL, SO, dylib trong repository, JAR hoặc thư mục triển khai.
- Đường dẫn cố định, tên command theo OS và lệnh gọi shell.
- Mã kiểm tra os.name, os.arch hoặc file.separator.
- Cấu hình container, Dockerfile và script khởi động.

Với mỗi dependency native, ghi nhận vendor, phiên bản, URL hoặc nguồn artifact, OS/architecture được cung cấp, ABI và dependency hệ thống. Kiểm tra dependency bắc cầu thay vì chỉ xem dependency trực tiếp trong build file.

### Bước 2: Xác định target environment

Chốt các môi trường đích và phiên bản tối thiểu. Làm rõ ứng dụng sẽ chạy trực tiếp trên máy chủ, trong container, dưới service manager hay trong môi trường giả lập. Xác định JVM process architecture và libc thực tế của image.

Nếu build và deploy chạy trên hai nền tảng khác nhau, ghi rõ target platform trong pipeline và cấu hình đóng gói. Không để kết quả phụ thuộc ngầm vào máy runner.

### Bước 3: Sửa các giả định phụ thuộc OS

Thay thao tác filesystem bằng API Java đa nền tảng. Chuẩn hóa charset và timezone tại các ranh giới dữ liệu. Đưa command theo OS vào một lớp adapter nhỏ, có kiểm tra khả năng hỗ trợ và thông báo lỗi rõ ràng.

Nếu ứng dụng cần dùng API riêng của OS, cô lập phần đó sau một interface để phần nghiệp vụ không phải chứa nhiều nhánh điều kiện theo nền tảng.

### Bước 4: Chọn và đóng gói native binary

Chọn một trong các chiến lược: artifact riêng, bundle nhiều resource hoặc dependency cấp hệ thống. Đảm bảo artifact được chọn theo target OS, architecture và ABI. Kiểm tra phiên bản binary, checksum hoặc chữ ký theo quy trình phát hành của dự án.

Đối với container, image phải có cả runtime Java và native system dependency cần thiết. Base image dùng khi build native code cần được phân biệt với base image dùng khi chạy ứng dụng; hai image phải tương thích ABI.

### Bước 5: Kiểm thử trong môi trường đích

Chạy kiểm thử trên máy hoặc container có OS và architecture tương ứng. Kiểm tra cả bước khởi động, nạp thư viện, lời gọi native thực tế và luồng nghiệp vụ sử dụng native code. Một smoke test chỉ xác nhận JVM khởi động không chứng minh thư viện native hoạt động.

Nếu không có runner vật lý cho một kiến trúc, có thể dùng runner tương ứng hoặc môi trường giả lập có kiểm soát để kiểm tra sơ bộ. Tuy nhiên, kết quả giả lập không thay thế hoàn toàn kiểm thử trên target hardware và OS thực tế.

### Bước 6: Ghi nhận chẩn đoán và phát hành

Log khi khởi động nên ghi phiên bản Java, os.name, os.version, os.arch, tên native variant được chọn và phiên bản dependency native. Không ghi secret hoặc thông tin nhạy cảm vào log.

Nếu native loading thất bại, thông báo nên chỉ rõ resource/variant được chọn và nguyên nhân gốc nếu có thể xác định. Giữ lại khả năng rollback về artifact và cấu hình đã biết hoạt động; triển khai theo từng môi trường để dễ khoanh vùng lỗi.

## 8. Kiểm thử và chẩn đoán

### 8.1. Các lớp kiểm thử nên có

| Loại kiểm thử | Mục đích | Ví dụ |
|---|---|---|
| Build/package test | Xác nhận đúng native artifact được đưa vào gói | Kiểm tra nội dung JAR hoặc thư mục phân phối |
| Startup smoke test | Xác nhận JVM và cấu hình khởi động hợp lệ | Chạy ứng dụng trong image đích |
| Native loading test | Xác nhận loader tìm và nạp được binary | Gọi một hàm native tối thiểu |
| Integration test | Xác nhận hành vi native thực tế | Mã hóa, xử lý ảnh, database driver hoặc thao tác thiết bị |
| Environment test | Xác nhận filesystem, quyền, command và encoding | Chạy bằng đúng tài khoản service |
| Regression test | Bảo đảm hành vi nghiệp vụ cũ vẫn đúng | Chạy bộ test trên từng target platform |

Một bài test native loading đơn giản chỉ chứng minh thư viện có thể được nạp. Nó chưa chứng minh mọi hàm native, mọi code path hoặc mọi dependency bắc cầu đều hoạt động.

### 8.2. Thu thập thông tin môi trường

Có thể dùng một đoạn Java nhỏ để in thông tin runtime phục vụ chẩn đoán:

```java
public final class EnvironmentReport {
    public static void main(String[] args) {
        System.out.println("java.version="
            + System.getProperty("java.version"));
        System.out.println("java.vendor="
            + System.getProperty("java.vendor"));
        System.out.println("java.vm.name="
            + System.getProperty("java.vm.name"));
        System.out.println("os.name="
            + System.getProperty("os.name"));
        System.out.println("os.version="
            + System.getProperty("os.version"));
        System.out.println("os.arch="
            + System.getProperty("os.arch"));
        System.out.println("file.encoding="
            + System.getProperty("file.encoding"));
        System.out.println("java.io.tmpdir="
            + System.getProperty("java.io.tmpdir"));
        System.out.println("user.dir="
            + System.getProperty("user.dir"));
    }
}
```

Thông tin này giúp so sánh hai môi trường. Khi xử lý sự cố native, hãy bổ sung log về variant và đường dẫn thư viện đã chọn. Đường dẫn có thể tiết lộ cấu trúc hệ thống, vì vậy chỉ ghi ở mức phù hợp với chính sách log của ứng dụng.

### 8.3. Công cụ hệ điều hành

Khi cần kiểm tra binary, dùng công cụ phù hợp với nền tảng và quyền truy cập:

- Linux: file để nhận diện định dạng/architecture; ldd để xem dependency động trên binary đáng tin cậy; readelf để kiểm tra ELF và symbol/version.
- macOS: file và otool -L để xem kiến trúc và dependency của Mach-O.
- Windows: dumpbin /DEPENDENTS hoặc công cụ kiểm tra PE/DLL tương ứng để xem dependency.
- Java: java -version, system property và log của ứng dụng để xác nhận runtime thực tế.

Chỉ chạy công cụ phân tích dependency trên binary mà bạn tin cậy. Một số công cụ hiển thị dependency theo môi trường hiện tại, nên kết quả cần được đối chiếu với image hoặc máy đích.

## 9. Các lỗi thiết kế nên tránh

**Giả định JAR là đa nền tảng nên mọi dependency cũng đa nền tảng.** JAR thuần Java thường có tính di động, nhưng native component có thể phụ thuộc chặt vào OS, architecture và ABI. Hãy kiểm kê toàn bộ dependency.

**Dùng tên OS hoặc architecture chưa chuẩn hóa ở nhiều nơi.** Các alias như amd64 và x86_64 có thể chỉ cùng một nhóm. Tập trung logic ánh xạ tại một module và xử lý rõ nền tảng chưa hỗ trợ.

**Chọn native binary theo máy build thay vì máy đích.** Pipeline chạy trên Linux x86_64 có thể vô tình đóng gói native library x86_64 cho ứng dụng cần chạy trên ARM64. Hãy đưa target platform vào quá trình build/package.

**Chỉ kiểm tra file native có tồn tại.** File có thể sai định dạng, sai kiến trúc, sai ABI hoặc thiếu dependency bắc cầu. Cần thử nạp và gọi native code trong môi trường đích.

**Dùng đường dẫn và shell cố định.** Đường dẫn Unix, command bash hoặc cú pháp quoting có thể thất bại trên Windows. Dùng API Java chuẩn và adapter theo nền tảng khi thật sự cần.

**Dùng default charset hoặc timezone cho dữ liệu trao đổi.** Kết quả có thể thay đổi theo môi trường. Chỉ định rõ charset, locale và timezone theo yêu cầu nghiệp vụ.

**Build native trên môi trường mới mà không kiểm soát ABI tối thiểu.** Binary có thể yêu cầu glibc hoặc runtime C/C++ mới hơn máy đích. Xác định rõ phiên bản tối thiểu và kiểm thử trên môi trường đó.

**Bỏ qua tài khoản chạy ứng dụng.** Ứng dụng chạy trong IDE với quyền người dùng có thể thành công nhưng thất bại dưới service account vì không có quyền ghi thư mục tạm, đọc file hoặc chạy command.

## 10. Checklist trước khi hoàn tất migration

- [ ] Đã xác định phiên bản Java tối thiểu và runtime thực tế trên từng môi trường.
- [ ] Đã lập danh sách OS và architecture được cam kết hỗ trợ.
- [ ] Đã kiểm kê dependency native trực tiếp và bắc cầu.
- [ ] Đã xác định ABI, libc và runtime hệ thống mà binary native yêu cầu.
- [ ] Đã phân biệt build platform với target platform.
- [ ] Đã cấu hình lựa chọn native artifact theo target OS/architecture/ABI.
- [ ] Đã xử lý đường dẫn, quyền filesystem, command và encoding theo cách phù hợp.
- [ ] Đã kiểm tra container image có đủ native system dependency.
- [ ] Đã chạy smoke test, native loading test và integration test trên môi trường đích.
- [ ] Đã ghi nhận thông tin runtime và native variant để hỗ trợ chẩn đoán.
- [ ] Đã ghi rõ các nền tảng không hỗ trợ và chuẩn bị phương án rollback.

## Kết luận

Tương thích môi trường trong migration Java là sự kết hợp giữa khả năng chạy của JVM, hành vi của hệ điều hành, kiến trúc của tiến trình và ABI của các thư viện native. Bytecode Java có thể dùng chung, nhưng native binary và dependency hệ thống phải được chọn, đóng gói và kiểm thử theo môi trường đích.

Một quy trình migration đáng tin cậy bắt đầu bằng việc lập ma trận nền tảng, kiểm kê native dependency, tách biệt build platform và target platform, rồi xác minh ứng dụng trong đúng OS/architecture/ABI được hỗ trợ. Khi các giả định môi trường được ghi rõ và kiểm thử tự động, việc nâng cấp Java hoặc chuyển máy chủ sẽ dễ dự đoán và dễ chẩn đoán hơn.

