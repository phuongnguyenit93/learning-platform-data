# 1.8. Môi trường thực hành Java 21 và cách đối chiếu API với phiên bản JDK

Bài này thiết lập môi trường thực hành **Java 21** cho module Security & Cryptography, đồng thời chỉ ra cách xác minh một lớp, phương thức hoặc thuật toán bảo mật thực sự có mặt trong **phiên bản Java và JDK đang dùng**. Đây là bước nền tảng trước khi học `MessageDigest`, `Cipher`, `Signature`, `KeyStore`, TLS/JSSE và các API mới.

## Mục tiêu sau bài học

- Cài và chọn đúng **JDK 21**, kiểm tra `java`, `javac`, `jshell`, IDE và build tool có đang sử dụng bản phù hợp.
- Biên dịch, chạy chương trình Java 21 đơn giản với thư viện chuẩn và một API mật mã.
- Tự đối chiếu API qua **tài liệu Java SE 21/JDK 21**, trường `Since`, module, chữ ký phương thức và lệnh `javac --release`.
- Phân biệt **API tồn tại**, **bytecode tương thích**, và **thuật toán/provider thực sự khả dụng tại runtime**; tránh hiểu nhầm khi phát triển ứng dụng mật mã.

## 1. Hiểu đúng ba tầng phiên bản

| Tầng cần kiểm tra | Công cụ hoặc nguồn kiểm tra | Ý nghĩa |
| --- | --- | --- |
| JDK dùng để phát triển | `javac -version`, cấu hình Project SDK/toolchain | Quyết định trình biên dịch và các công cụ có sẵn. |
| Java dùng để chạy | `java -version`, `Runtime.version()` | Quyết định runtime thực thi, thư viện/module và security provider có hiệu lực. |
| Java tối thiểu mà sản phẩm hỗ trợ | `javac --release 21`, kiểm thử trên runtime mục tiêu | Ràng buộc cú pháp, API nền tảng và phiên bản class file được phép phát hành. |

**JDK** gồm compiler (`javac`), runtime (`java`), công cụ phân tích (`javap`, `jdeps`), công cụ thử nhanh (`jshell`), `keytool` cùng thư viện/module chuẩn. Chỉ cài một runtime mà thiếu compiler không đủ cho bài thực hành. “Java 21” là dòng phiên bản chính; số cập nhật như `21.0.x`, nhà phân phối JDK và hệ điều hành/kiến trúc có thể khác nhau. Ưu tiên bản cập nhật bảo mật mới trong dòng 21 lấy từ nguồn phát hành đáng tin cậy.

**Lưu ý:** JDK được chọn trong terminal có thể khác JDK của IDE, Maven, Gradle, service hoặc container. Kết luận “đang chạy Java 21” phải dựa trên môi trường **thực sự biên dịch và chạy chương trình**.

## 2. Chuẩn bị JDK 21 và kiểm tra đường dẫn

1. Tải và cài một bản **JDK 21** tương thích hệ điều hành (ví dụ Oracle JDK 21 hoặc một bản OpenJDK 21 được hỗ trợ như Eclipse Temurin). Chọn đúng kiến trúc CPU; xác minh nhà phát hành và cập nhật bản vá bảo mật.
2. Thiết lập `JAVA_HOME` trỏ đến **thư mục gốc JDK** (thư mục chứa `bin`), và đưa `JAVA_HOME/bin` vào `PATH` theo cơ chế của hệ điều hành.
3. Mở terminal mới rồi chạy:

```text
java -version
javac -version
jshell --version
```

Kết quả kỳ vọng có **major version 21** ở cả ba lệnh (chuỗi đầy đủ khác tùy nhà phát hành, bản vá và hệ điều hành). `java -version` và `javac -version` phải tương thích với môi trường đã chọn.

Kiểm tra file thực thi mà terminal sẽ gọi:

```powershell
# Windows PowerShell
where.exe java
where.exe javac
$env:JAVA_HOME
```

```bash
# Linux / macOS
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
```

Nếu máy có nhiều JDK, kết quả `where.exe` có thể liệt kê nhiều đường dẫn: đường dẫn được ưu tiên trên `PATH` thường quyết định lệnh thực tế. Trên Linux/macOS, `command -v` xác định điểm vào của lệnh; có thể là symlink và cần kiểm tra thêm liên kết/Java home theo hệ thống đang dùng.

```text
java -XshowSettings:properties -version
```

Trong phần properties, chú ý `java.home`, `java.vendor`, `java.version`, `os.arch`; cách này giúp kiểm tra runtime đang hoạt động. Lệnh có thể in nhiều dòng, nên chỉ cần xem những thuộc tính liên quan. Khi làm việc với IDE/build tool, kiểm tra cấu hình SDK/JDK và lệnh chạy thực tế của chúng, không chỉ terminal.

**Bộ công cụ tối thiểu:** terminal, editor/IDE, JDK 21, thư mục chứa file `.java`. Chưa cần thêm thư viện mật mã bên ngoài để thử các API chuẩn như `MessageDigest` hay `Cipher`.

## 3. Bài thực hành đầu tiên: biên dịch và kiểm tra API mật mã

Tạo file **`ApiProbe.java`** (tên phải trùng với `public class ApiProbe`):

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.Cipher;

public class ApiProbe {
    public static void main(String[] args) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest("Java 21".getBytes(StandardCharsets.UTF_8));

        // Chỉ xác minh có implementation của transformation, chưa mã hóa dữ liệu.
        Cipher.getInstance("AES/GCM/NoPadding");

        System.out.println("Runtime feature: " + Runtime.version().feature());
        System.out.println("SHA-256 bytes: " + digest.length);
        System.out.println("Hex characters: "
                + HexFormat.of().formatHex(digest).length());
        System.out.println("AES/GCM available: true");
    }
}
```

Trong thư mục chứa file, chạy:

```text
mkdir out
javac --release 21 -encoding UTF-8 -d out ApiProbe.java
java -cp out ApiProbe
```

Trên **JDK 21 chuẩn có provider hỗ trợ AES/GCM**, kết quả là:

```text
Runtime feature: 21
SHA-256 bytes: 32
Hex characters: 64
AES/GCM available: true
```

Giải thích:

- `--release 21` buộc compiler kiểm tra cú pháp và tập API nền tảng tương ứng Java 21, đồng thời tạo bytecode cho Java 21. `-encoding UTF-8` tránh phụ thuộc encoding mặc định của máy; `-d out` đưa các `.class` vào thư mục riêng.
- `java -cp out ApiProbe` chạy class vừa tạo trên runtime đang được lệnh `java` trỏ tới. Nếu runtime là Java 24, dòng `Runtime feature` sẽ hiển thị `24` dù bytecode được biên dịch với `--release 21`.
- SHA-256 luôn cho 256 bit = **32 byte**; dạng hexadecimal không phân tách dùng **64 ký tự**. `HexFormat` là API chuẩn xuất hiện từ Java 17.
- `Cipher.getInstance("AES/GCM/NoPadding")` yêu cầu một **transformation** từ security provider. Đoạn này chỉ chứng minh provider có thể cung cấp transformation, **chưa** kiểm tra việc dùng khóa, IV/nonce, AAD hay tính an toàn của một quy trình mã hóa. Nếu provider không cung cấp transformation, lệnh sẽ ném exception thay vì in dòng cuối.

`Runtime.version().feature()` dùng để biết phiên bản runtime hiện hành; nó không tự xác nhận phiên bản đã dùng để biên dịch. Tách bạch hai việc khi báo cáo lỗi môi trường.

## 4. Đối chiếu một API với đúng bản JDK: quy trình năm bước

Giả sử bạn gặp một ví dụ dùng `javax.crypto.KEM` hoặc `java.util.HexFormat` và muốn biết có chạy được trên Java 17/21 hay không.

**Bước 1 — Xác định tên đầy đủ.** Ghi rõ package, tên lớp và phương thức/overload cần gọi. Ví dụ `javax.crypto.KEM.getInstance(String)` khác với chỉ nói “KEM”. Một lớp có thể tồn tại từ phiên bản cũ nhưng **phương thức riêng** lại được bổ sung sau.

**Bước 2 — Mở tài liệu gắn với phiên bản mục tiêu.** Với Java 21, dùng [Java SE 21 & JDK 21 API Specification](https://docs.oracle.com/en/java/javase/21/docs/api/). Tìm đúng lớp và đọc lần lượt:

- `Module` và `Package` (ví dụ `javax.crypto.KEM` thuộc `java.base`).
- Mô tả công dụng, phương thức, kiểu tham số, kiểu trả về và checked exceptions.
- `Since` của **lớp** và, khi có, của **constructor/phương thức/field** đang dùng.
- `Deprecated`, `forRemoval`, yêu cầu về preview/incubator (nếu có), điều kiện provider hoặc phần ghi chú triển khai.

**Bước 3 — Đối chiếu với bản cũ và bản đang chạy.** Tài liệu Java 17 và Java 21 có thể khác nhau. Ví dụ:

| API | Thông tin từ tài liệu chính thức | Cách kết luận |
| --- | --- | --- |
| `java.util.HexFormat` | `Since: 17` | Có trong API nền tảng từ Java 17 trở đi. |
| `javax.crypto.KEM` | `Since: 21` | Không thuộc API Java 17; mã tham chiếu lớp này cần baseline Java 21 hoặc mới hơn. |
| `java.security.MessageDigest` | API có từ lâu, nhưng thuật toán phụ thuộc provider | Có lớp chưa đồng nghĩa mọi tên thuật toán đều được hỗ trợ. |

Đọc `Since` giúp biết **mốc xuất hiện API**. Nó không bảo đảm hành vi giống nhau trong mọi bản vá, mọi provider hay mọi vendor. Nếu một yêu cầu gắn với version cụ thể, kiểm tra tài liệu của **đúng version** thay vì tìm kiếm chung trên web (có thể trả tài liệu cho Java 22/25/26...).

**Bước 4 — Để compiler kiểm chứng compatibility.** Dùng `--release` với mức Java mà ứng dụng muốn hỗ trợ. Cách này mạnh hơn việc chỉ xem một trang tài liệu.

**Bước 5 — Kiểm tra trên runtime mục tiêu.** Với API bảo mật, khâu runtime cần xác nhận provider, cấu hình chính sách bảo mật, thuật toán và tham số hoạt động. Build thành công mới chứng minh code tham chiếu được API trong thời điểm biên dịch; nó chưa bảo đảm thuật toán được triển khai khi chạy.

## 5. Thử nghiệm chính xác với `--release`: API chỉ có từ Java 21

Theo [Javadoc của `javax.crypto.KEM` cho Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html), lớp `KEM` có `Since: 21`. Tạo file **`VersionGate.java`**:

```java
import javax.crypto.KEM;

public class VersionGate {
    public static void main(String[] args) {
        System.out.println(KEM.class.getName());
    }
}
```

Trên **compiler JDK 21**, thực hiện lần lượt:

```text
mkdir out17
javac --release 17 -d out17 VersionGate.java
```

Lệnh trên **phải thất bại** vì `javax.crypto.KEM` chưa nằm trong API Java 17 (thông báo cụ thể có thể khác; thường chứa `cannot find symbol`). Tiếp tục:

```text
mkdir out21
javac --release 21 -d out21 VersionGate.java
java -cp out21 VersionGate
```

Kết quả khi chạy bằng Java 21 trở lên:

```text
javax.crypto.KEM
```

Ví dụ chỉ tham chiếu **kiểu API**; nó chưa gọi `KEM.getInstance(...)` và không chứng minh một thuật toán KEM cụ thể khả dụng. Đây là khác biệt quan trọng giữa **có lớp `KEM`** và **có provider hỗ trợ thuật toán KEM**.

### Vì sao dùng `--release` thay cho `--source` và `--target`?

- `--source 21` kiểm tra ngữ pháp Java 21; `--target 21` chọn phiên bản bytecode đầu ra. Khi biên dịch bằng JDK mới hơn, cặp tùy chọn này **không tự giới hạn đầy đủ API chuẩn về đúng bản Java 21**.
- `--release 21` kết hợp giới hạn ngôn ngữ, bytecode và **các API công khai của platform release 21**. Với mã cần chạy trên Java 21, đây là lựa chọn phù hợp.
- `--release` chỉ chấp nhận các mức được **compiler hiện tại hỗ trợ**. JDK 17 không thể biên dịch `--release 21`; phải chọn JDK compiler đủ mới. Cũng không thể dùng JDK 21 để chọn tùy ý một release tương lai.
- Tùy chọn này không tự kiểm tra API của dependency ngoài JDK, native library, phản xạ, cấu hình runtime hoặc tính sẵn có của thuật toán mật mã.

Mã biên dịch cho Java 21 thường có class-file major version **65**. Có thể xem `javap -verbose out/ApiProbe.class` và tìm `major version`; tuy nhiên số version class file chỉ phản ánh định dạng bytecode, **không thay thế** kiểm tra thư viện/provider khi chạy. Runtime cũ hơn không đọc được class file mới có thể ném `UnsupportedClassVersionError`.

## 6. Ba câu hỏi riêng biệt khi làm việc với Java Cryptography

**Câu hỏi A: Java có lớp và phương thức này không?** Đọc Javadoc bản mục tiêu, `Since`, module/exports và thử `javac --release`. Ví dụ `java.security.MessageDigest`, `java.security.Signature` và `javax.crypto.Cipher` đều là API trong JDK chuẩn.

**Câu hỏi B: Runtime có thuật toán/provider cần thiết không?** JCA/JCE sử dụng cơ chế **provider**. `MessageDigest.getInstance("SHA-256")` và `Cipher.getInstance("AES/GCM/NoPadding")` là các truy vấn implementation. Tên thuật toán chuẩn, chính sách và provider có thể khác giữa các bản JDK hoặc cấu hình triển khai. Lỗi `NoSuchAlgorithmException` hoặc `NoSuchPaddingException` cần kiểm tra **tên service/transformation và provider thực tế**, không suy ngay rằng lớp Java không tồn tại.

**Câu hỏi C: Cách dùng thuật toán có an toàn và tương thích giao thức không?** Provider có thuật toán mới là điều kiện cần. Còn phải chọn key size, nonce/IV, mode, padding, encoding, quy tắc lưu khóa và quản lý lỗi phù hợp. Ví dụ AES/GCM cần nonce không được tái sử dụng với cùng khóa; thử `getInstance` chưa kiểm tra quy tắc đó.

Để quan sát provider mà không sửa cấu hình, tạo file **`ProviderProbe.java`**:

```java
import java.security.MessageDigest;
import java.security.Provider;
import java.security.Security;
import javax.crypto.Cipher;

public class ProviderProbe {
    public static void main(String[] args) throws Exception {
        for (Provider provider : Security.getProviders()) {
            System.out.println("Provider: " + provider.getName());
        }
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.println("SHA-256: " + digest.getProvider().getName());
        Cipher aesGcm = Cipher.getInstance("AES/GCM/NoPadding");
        System.out.println("AES/GCM: " + aesGcm.getProvider().getName());
    }
}
```

Chạy:

```text
javac --release 21 -d out ProviderProbe.java
java -cp out ProviderProbe
```

Tên và thứ tự provider trong output **phụ thuộc runtime**, không nên viết một stdout cố định. Trên một số môi trường có thêm provider của hệ điều hành, phần cứng, thư viện bên thứ ba hoặc cấu hình FIPS. Theo nguyên tắc portable, thường nên gọi `getInstance("...")` **không cố định tên provider**; chỉ chỉ định provider cụ thể khi yêu cầu hệ thống buộc làm vậy và đã kiểm thử môi trường triển khai. Tránh chỉnh `conf/security/java.security` chỉ để “làm cho ví dụ chạy”; nên hiểu cấu hình và tìm nguyên nhân trước.

**Ba loại tài liệu cần đọc cùng nhau:**

1. [Java 21 API Specification](https://docs.oracle.com/en/java/javase/21/docs/api/) — lớp, phương thức, `Since`, module và hợp đồng API.
2. [Java 21 JCA Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html) và [JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html) — cách chọn provider, danh mục service và những triển khai đi kèm Oracle JDK 21.
3. [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html) — cách đặt tên thuật toán, transformation, key store và các quy ước của API bảo mật.

**Không đồng nhất “standard name” với “bảo đảm mọi provider hỗ trợ”.** Tài liệu tên chuẩn định nghĩa cách gọi; tài liệu provider cùng kiểm thử runtime cho biết implementation cụ thể.

## 7. Công cụ dòng lệnh hỗ trợ đối chiếu

| Công cụ | Ví dụ | Giá trị và giới hạn |
| --- | --- | --- |
| `java` | `java --version` | Nhận diện runtime được gọi từ terminal. |
| `javac` | `javac --release 21 ...` | Xác minh mã có nằm trong phạm vi API/cú pháp Java 21; tạo bytecode. |
| `jshell` | `jshell` rồi `Runtime.version()` | Thử nhanh biểu thức/API; dùng cùng JDK dự định kiểm tra. |
| `javap` | `javap -public javax.crypto.KEM` | Quan sát public members của lớp từ JDK đang dùng; không thay thế `Since`. |
| `jdeps` | `jdeps --jdk-internals out` | Tìm dependency tới JDK internal APIs trong class đã biên dịch; không kiểm tra độ mạnh thuật toán mật mã. |
| `keytool` | `keytool -help` | Làm quen công cụ quản lý key/certificate; chưa cần sinh khóa thật ở bài này. |

`java --list-modules` liệt kê module của runtime. `java --describe-module java.base` hoặc `javap` hỗ trợ xem module/class được cài; với API Java 21, hãy đối chiếu thêm Javadoc vì một JDK mới hơn có thể chứa API chưa tồn tại trong release 21.

Không dùng `sun.*`, `com.sun.*` nội bộ để thay cho API chuẩn chỉ vì tìm thấy class khi phân tích JDK. API nội bộ có thể bị đóng gói, thay đổi hoặc bị chặn khi chạy. `jdeps --jdk-internals` hữu ích khi rà soát vấn đề này, nhưng kết quả “không tìm thấy” không chứng minh hệ thống đã tương thích hoàn toàn với một release.

## 8. Đồng bộ IDE và build tool

Nếu dự án dùng Maven, cấu hình mức Java phát hành (đoạn trong `pom.xml`):

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Kiểm tra `mvn -version` để biết Maven đang chạy với Java nào và bảo đảm Maven Compiler Plugin đang dùng hỗ trợ `release`. Nếu dự án có cấu hình plugin/toolchain riêng thì cấu hình đó phải nhất quán với mức 21.

Nếu dùng Gradle Groovy DSL, có thể khai báo Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain chọn JDK phù hợp cho tác vụ liên quan; cần phiên bản Gradle/plugin tương thích và cài đặt hoặc khả năng resolve JDK 21. Runtime dùng để **chạy ứng dụng** vẫn cần được kiểm tra riêng. Với IDE, xem **Project SDK**, **language level**, **compiler/build JDK**, cấu hình test và cấu hình run. Sau khi sửa JDK, hãy chạy lại câu lệnh build thực tế rồi xác minh `java -version` trong môi trường chạy.

## 9. Lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra/khắc phục |
| --- | --- | --- |
| `javac` không tìm thấy | Chưa cài JDK đầy đủ hoặc `PATH` chưa có `bin` của JDK | Kiểm tra `JAVA_HOME`, `where.exe javac` / `command -v javac`. |
| `release version 21 not supported` | Compiler hiện dùng cũ hơn Java 21 | Xem `javac -version` và JDK của IDE/Maven/Gradle; chọn JDK 21 hoặc mới hơn. |
| `cannot find symbol` với một API JDK | API có từ release cao hơn; sai package/chữ ký; hoặc build dùng `--release` thấp | Đọc `Since`, chữ ký overload và thử mức `--release` cần hỗ trợ. |
| `UnsupportedClassVersionError` | Runtime cũ hơn phiên bản class file | So sánh `java -version`, `javac --release` và `javap -verbose`; chạy bằng runtime tương thích hoặc build xuống baseline. |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | Provider hiện tại không cung cấp tên thuật toán/transformation hoặc gọi sai tên | Kiểm tra Java Security Standard Algorithm Names, các provider đã đăng ký và cấu hình JDK thực tế. |
| `ClassNotFoundException` / `NoClassDefFoundError` | Sai classpath/module-path hoặc thiếu dependency lúc chạy | Xác minh `-cp`, JAR/module và dependency được đóng gói. |
| Lỗi `package ... is not visible`, `InaccessibleObjectException` | Quyền truy cập theo module/reflection, thường liên quan internal API | Tìm public API được hỗ trợ; xem exports/opens và cấu hình module thay vì phụ thuộc workaround lâu dài. |
| Terminal chạy đúng nhưng IDE/build vẫn lỗi | Các tiến trình chọn JDK/toolchain khác nhau | Kiểm tra JDK ở từng tầng: IDE, compiler plugin, test runner, runtime container. |

**Phân biệt tên thư viện:** namespace `javax.crypto` là một phần của Java SE; không có nghĩa mọi gói bắt đầu bằng `javax.` đều thuộc Java SE. Thư viện `jakarta.*` hoặc thư viện mật mã bên thứ ba cần dependency và kiểm tra phiên bản **riêng**, ngoài phạm vi `--release`.

## 10. Bài tự kiểm tra và tiêu chí hoàn thành

1. Lưu output `java -version`, `javac -version` và đường dẫn thực thi. Giải thích vì sao IDE có thể dùng JDK khác terminal.
2. Biên dịch/chạy `ApiProbe.java` bằng `--release 21`. Giải thích vì sao 32 byte SHA-256 được chuyển thành 64 ký tự hexadecimal, và vì sao `Cipher.getInstance` chưa phải phép thử mã hóa an toàn.
3. Tra Javadoc Java 21 của `HexFormat` và `KEM`, chỉ ra `Since` tương ứng, rồi thử `VersionGate.java` với `--release 17` và `--release 21`.
4. Chạy `ProviderProbe.java`, ghi lại tên provider thực tế cho SHA-256 và AES/GCM trên máy của bạn. So sánh với JDK Providers Documentation và lý giải tại sao máy khác có thể ra provider khác.
5. Tự chọn một API bảo mật (chẳng hạn `java.security.Signature` hoặc `java.security.KeyStore`), ghi rõ **tên đầy đủ → phương thức → Since → module → release mục tiêu → provider/runtime test cần thiết**.

Hoàn thành bài khi bạn có thể trả lời rõ: **“Tôi đang biên dịch với JDK nào, chạy với JDK nào, API này xuất hiện từ release nào và runtime nào cung cấp thuật toán thực tế?”**

### Tài liệu tham khảo chính thức (cố định ở Java/JDK 21)

- [Java SE 21 & JDK 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/)
- [JDK 21 Tool Specifications, bao gồm `javac`, `javap` và `jdeps`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/index.html)
- [`javac` JDK 21: ý nghĩa `--release`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [`HexFormat` (Since 17)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html)
- [`KEM` (Since 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [JCA Reference Guide JDK 21](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html)
- [JDK Providers Documentation JDK 21](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html)
