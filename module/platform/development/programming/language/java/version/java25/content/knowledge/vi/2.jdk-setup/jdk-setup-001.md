# Chọn bản phân phối JDK 25 và bản cập nhật phù hợp với nền tảng triển khai

**JDK 25** là bản Java **LTS (Long-Term Support)**, phát hành lần đầu tháng 9/2025. Khi đưa Java 25 vào dự án thực tế, chọn đúng *feature version* `25` chỉ là bước đầu. Cần xác định thêm **nhà cung cấp bản phân phối**, **bản vá đang được hỗ trợ**, **hệ điều hành/kiến trúc CPU**, **thư viện C trong Linux**, **giấy phép** và **chu trình cập nhật bảo mật**. Một JDK có thể chạy tốt trên laptop nhưng không phù hợp image Alpine của production hoặc chưa đáp ứng chính sách hỗ trợ doanh nghiệp.

Bài thuộc chương **Thiết lập JDK 25** của module `JAVA_VERSION_JAVA25`. Mục đích là chọn và xác minh môi trường Java 25 làm nền tảng cho các nội dung vẫn có giá trị trong phát triển Java hiện đại: chương trình nguồn gọn, `import module`, hàm khởi tạo linh hoạt, `ScopedValue`, API dẫn xuất khóa, AOT cache và quan sát bằng JFR. Bài tập trung vào **bản phát hành ổn định, đang được duy trì**; không hướng dẫn sử dụng bản early-access, các cơ chế đã ngừng hỗ trợ hay API preview như yêu cầu bắt buộc của môi trường production.

> **Mốc kiểm chứng: 27/11/2026.** Bản cập nhật bảo mật quan trọng của dòng 25 vào ngày **17/11/2026** là **25.0.5.1**. Ví dụ Oracle JDK có build `25.0.5.1+4`; Eclipse Temurin có bản `jdk-25.0.5.1+2`. Số build của từng nhà cung cấp **không nhất thiết giống nhau**. Sau mốc ngày này, hãy kiểm tra lại trang download và security advisory của nhà cung cấp trước khi lựa chọn. Không dùng một số version được ghi trong tài liệu như cam kết nó luôn là phiên bản mới nhất.

## 1. Phân biệt Java SE, OpenJDK, nhà phân phối và bản vá

**Java SE 25** xác định đặc tả nền tảng Java. **OpenJDK** là dự án nguồn mở triển khai nền tảng đó. Các bản phân phối như **Eclipse Temurin**, **Amazon Corretto**, **Azul Zulu** và các bản của **Oracle** có lịch phát hành, nền tảng nhị phân, điều khoản cấp phép và dịch vụ hỗ trợ khác nhau. Phần lớn ứng dụng Java thuần có thể chuyển giữa các bản phân phối tương thích Java SE nhưng vẫn phải kiểm thử khi thay nhà cung cấp JVM.

| Khái niệm | Ví dụ | Ý nghĩa khi triển khai |
|---|---|---|
| Feature version | `25` | Ngôn ngữ/API Java 25; **không** biểu thị tình trạng đã vá bảo mật. |
| Update / patch version | `25.0.5.1` | Mức cập nhật trong nhánh Java 25. Cần đối chiếu security baseline. |
| Build identifier | `25.0.5.1+4`, `25.0.5.1+2` | Bản build cụ thể; có thể khác nhau giữa Oracle và Temurin. |
| Distribution / vendor | Eclipse Temurin, Corretto, Zulu, Oracle JDK | Nhà cung cấp artifact, gói cài, container image, lịch hỗ trợ. |
| Runtime package | JDK, runtime/JRE do vendor cung cấp, runtime từ `jlink` | JDK có `javac` và công cụ chẩn đoán; runtime gọn có thể thiếu công cụ. |
| Platform tuple | `linux/amd64/glibc`, `linux/arm64/musl`, `windows/x64` | Phải khớp bản nhị phân và môi trường triển khai thực tế. |
| Release channel | GA + security update, EA, nightly | Production chọn bản **GA ổn định** và đã qua quy trình cập nhật. |

Một bản `openjdk version "25"` được cài từ ngày phát hành đầu tiên **không có mức an toàn tương đương** `25.0.5.1`. Các bản `25-ea` và nightly chỉ nên dùng thử nghiệm tính năng/khả năng tương thích, không thay thế security release cho production.

### 1.1. Cách đọc phiên bản của JDK

Ví dụ kết quả `java --version` có thể chứa:

```text
openjdk 25.0.5.1 2026-11-17 LTS
OpenJDK Runtime Environment Temurin-25.0.5.1+2
OpenJDK 64-Bit Server VM Temurin-25.0.5.1+2
```

Đây là **output minh họa**, không phải kết quả đã chạy trên máy người học. Điều cần kiểm tra là: Java feature bằng 25; update đã đạt baseline cần thiết; vendor đúng bản đã chọn; `javac` ở cùng nhánh phát hành; architecture đúng môi trường. Một chuỗi `java.version` giống nhau không chứng minh hai gói có cùng build hoặc cùng phần vá theo chính sách của vendor.

## 2. So sánh bản phân phối còn được hỗ trợ

Các lựa chọn sau đều có bản phát hành Java 25 LTS, nhưng khác về chính sách hỗ trợ và nền tảng. Đây là **tiêu chí ra quyết định**, không phải bảng xếp hạng hiệu năng.

| Lựa chọn | Khi nào phù hợp | Giấy phép / cập nhật / điểm cần kiểm tra |
|---|---|---|
| **Eclipse Temurin 25** | Nhóm muốn bản OpenJDK miễn phí, có kiểm thử cộng đồng, cài trên Windows/macOS/Linux và dùng CI/container. | Adoptium cung cấp bản GA được kiểm thử; dòng 25 LTS được lên kế hoạch duy trì ít nhất đến **9/2031** tùy nguồn upstream. Kiểm tra ma trận platform và artifact thực có cho từng OS/CPU. |
| **Amazon Corretto 25** | Dịch vụ trên AWS hoặc đa nền tảng cần lịch hỗ trợ LTS được công bố rõ. | AWS cung cấp bản phân phối không thu phí; lộ trình **last planned update 7/2032, EOL 10/2032**. Có gói cho Linux, Windows, macOS; bao gồm lựa chọn Linux `glibc` và Alpine `musl` theo support matrix. |
| **Azul Zulu / Azul Core 25** | Doanh nghiệp cần gói nền tảng chuyên biệt, hỗ trợ thương mại/SLA hoặc lựa chọn nhiều môi trường chạy. | Azul công bố Java 25 là LTS và lịch sản phẩm riêng. Phân biệt các quyền lợi **bản miễn phí** với **hợp đồng hỗ trợ**; kiểm tra platform và gói đã mua. |
| **Oracle JDK 25** | Dự án đã tiêu chuẩn hóa Oracle JDK, cần thử tương thích hoặc hợp đồng hỗ trợ từ Oracle. | Bản cập nhật Oracle JDK 25 được cấp dưới **Oracle No-Fee Terms and Conditions (NFTC)** đến **9/2028**; các cập nhật sau đó dự kiến chuyển sang giấy phép OTN với hạn chế về sử dụng production không có hợp đồng. Đánh giá license cho **toàn vòng đời vận hành**, không chỉ ngày cài đặt. |

**Không thể suy ra** một bản JDK có hỗ trợ thương mại dài hạn chỉ từ chữ “LTS” trên `java -version`. Lịch bảo trì source, thời gian có build miễn phí, quyền nhận bản vá và hỗ trợ có SLA là bốn khái niệm khác nhau. Dự án có vòng đời hơn 5 năm phải lưu chính sách hỗ trợ của vendor như một quyết định kiến trúc.

### 2.1. Quy tắc chọn nhanh

- **Dự án phổ thông, triển khai Docker/CI và không có hợp đồng vendor đặc biệt:** cân nhắc **Temurin 25 GA mới nhất đã được phê duyệt**, kiểm tra artifact đúng platform.
- **Hệ thống tiêu chuẩn hóa Amazon Linux/AWS:** cân nhắc **Corretto 25**, nhất quán giữa runtime và image, theo lịch security update của Amazon.
- **Tổ chức có SLA hoặc yêu cầu vận hành đặc thù:** đánh giá **Azul** hoặc gói hỗ trợ của vendor tương ứng, kiểm tra giấy phép và cam kết support bằng văn bản.
- **Đang dùng Oracle JDK:** không mặc định việc “miễn phí hôm nay” có nghĩa miễn phí mọi bản vá đến hết vòng đời; lập phương án license hoặc migration trước mốc **9/2028**.

Các lựa chọn khác như Microsoft Build of OpenJDK, BellSoft Liberica, Red Hat Build of OpenJDK cũng có thể phù hợp khi nền tảng yêu cầu; hãy đánh giá theo cùng bộ tiêu chí thay vì mặc định chỉ có bốn nhà cung cấp trên.

## 3. Kiểm tra nền tảng: OS, CPU, libc và container

Điều kiện đầu tiên khi chọn artifact JDK là **khớp chính xác nơi chạy**. Máy build, máy CI và máy production có thể dùng kiến trúc khác nhau.

### 3.1. Bảng quyết định nền tảng

| Môi trường | Artifact cần tìm | Những điều dễ nhầm |
|---|---|---|
| Windows x64 | JDK 25 **Windows x64**, MSI/ZIP vendor phát hành | `PATH` còn trỏ tới bản JDK cũ; PowerShell thấy `java` khác với IDE. |
| Windows ARM64 | JDK 25 **Windows ARM64** nếu vendor có build được hỗ trợ | Chạy x64 qua emulation không tương đương binary ARM64 gốc; kiểm tra availability thực tế. |
| macOS Apple Silicon | JDK 25 **macOS aarch64/arm64** | Nhầm với `x64`; Homebrew/Terminal chạy qua Rosetta có thể làm chọn nhầm architecture. |
| macOS Intel | JDK 25 **macOS x64** | Không dùng artifact macOS ARM64 chỉ vì đều là `.pkg`. |
| Ubuntu/Debian/RHEL/Amazon Linux | JDK 25 **Linux x64/aarch64 glibc** hoặc package `.deb`/`.rpm` | Kiểm tra phiên bản distro, libc, CPU, phiên bản tối thiểu được vendor hỗ trợ. |
| Alpine Linux | Bản JDK 25 được build cho **musl libc** | Không lấy bản Linux `glibc` thông thường rồi mặc định chạy trên Alpine. |
| Kubernetes trên AMD64 + ARM64 | Image JDK đa kiến trúc có manifest phù hợp | Tag tồn tại không đảm bảo đủ image cho mọi architecture/node pool. |
| Windows container | Image theo Windows Server Core/NanoServer **phù hợp host Windows** | Windows container có thêm ràng buộc tương thích host OS, khác Linux container. |

Không “chuyển” gói JDK Linux sang Windows/macOS và không coi `x86_64` với `aarch64` là cùng architecture. Linux `glibc` và `musl` cũng là hai mục tiêu binary riêng: nếu triển khai Alpine, chọn gói hoặc image **được vendor xác nhận cho Alpine**.

### 3.2. Lệnh kiểm tra trên Linux/macOS

```bash
uname -s
uname -m

# Trên Linux, xem bản phân phối:
cat /etc/os-release

# Trên hệ glibc, lệnh có thể hiển thị phiên bản glibc;
# trên Alpine musl, output/cách chạy khác.
ldd --version

# Vị trí JDK sẽ được shell chọn:
command -v java
command -v javac
```

Ví dụ `uname -m` có thể trả `x86_64` hoặc `aarch64` (trên macOS Apple Silicon thường là `arm64`). Kiểm tra thêm kiến trúc của **container image/node** chứ không chỉ máy developer.

### 3.3. Lệnh kiểm tra trên Windows PowerShell

```powershell
$env:PROCESSOR_ARCHITECTURE
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
```

Nếu máy cài nhiều JDK, `JAVA_HOME` và `PATH` phải trỏ đến bản được chọn; chỉ đổi `JAVA_HOME` có thể chưa thay được `java` mà terminal đang tìm thấy. IDE và build tool cũng có cấu hình JDK riêng.

## 4. Chọn bản vá JDK 25 đúng thời điểm

Nhánh Java 25 được cập nhật theo lịch **Critical Patch Update (CPU)** định kỳ, thông thường theo quý, và có thể có bản ngoài lịch khi cần xử lý vấn đề bảo mật. Không nên giữ `25.0.0` hoặc `25.0.5` chỉ vì ứng dụng vẫn khởi động được.

**Tại ngày 27/11/2026**, chuỗi cần lưu ý:

| Thời điểm | Bản Java 25 | Hành động đúng |
|---|---|---|
| 16/09/2025 | JDK 25 GA ban đầu | Mốc phát hành tính năng, **không phải** baseline bảo mật hiện tại. |
| 20/10/2026 | `25.0.5` | Đã có bản vá tiếp theo vào tháng 11; không xem đây là mức mới nhất cho triển khai mới. |
| 17/11/2026 | `25.0.5.1` | Bản cập nhật bảo mật cho dòng 25, do các vendor phát hành với số build riêng. |
| 24/11/2026 | Oracle `25.0.5.1.1` (BPR) | Bản sửa lỗi bổ sung theo release notes Oracle; đánh giá theo nhu cầu lỗi cụ thể và gói tải thực có. |
| 19/01/2027 (dự kiến) | `25.0.6` | Mốc CPU tiếp theo, **chưa phát hành** tại ngày viết; chuẩn bị lịch cập nhật và kiểm thử. |

Bản **BPR** là bản vá lỗi được vendor công bố trong cùng nhánh, không có nghĩa mọi vendor phát hành cùng số version nhỏ đó. Khi kiểm tra compliance/security, dùng **security baseline, CVE/advisory và release notes của bản vendor thực cài**.

### 4.1. Quy trình nhận bản vá

1. Theo dõi trang security advisory/release notes chính thức của vendor đang sử dụng.
2. Chọn **bản GA/security update mới nhất đã được phát hành cho đúng OS/CPU/libc**; không lấy `EA`/nightly thay thế.
3. Tải từ kênh chính thức và kiểm tra SHA-256/signature hoặc attestations khi được cung cấp.
4. Cập nhật **JDK build/CI** và **runtime image/VM** trong cùng một nhịp có kiểm thử; ghi nhận nơi nào có thể cần lệch phiên bản tạm thời.
5. Chạy lại build, unit/integration tests, smoke tests, test TLS/crypto và workload đại diện.
6. Thử trên staging/canary, kiểm tra logs/JFR/metrics và khả năng rollback.
7. Phát hành cùng bản ghi vendor, `java.runtime.version`, image digest hoặc package checksum, ngày áp dụng.

Không có một quy tắc “cập nhật định kỳ mỗi sáu tháng” đủ an toàn cho JDK LTS. Với Java 25 nên đặt lịch tối thiểu theo các security update được vendor công bố, đồng thời có quy trình hotfix khi có advisory ngoài lịch.

## 5. Cài đặt JDK 25 từ kênh chính thức

Nên dùng package manager hoặc installer chính thức có quản lý cập nhật, hoặc artifact archive đã kiểm tra checksum. Không tải JDK không rõ nguồn trên trang tổng hợp, không dùng bản `jdk.java.net` đã lưu trữ từ lần GA đầu cho production hiện tại.

### 5.1. Windows: Eclipse Temurin qua winget

Adoptium công bố package ID:

```powershell
winget install --id EclipseAdoptium.Temurin.25.JDK --exact
```

Sau khi cài, mở terminal mới, kiểm tra `java --version` và `javac --version`. **Package repository/winget có thể phát hành trễ hơn bản vendor download**: nếu yêu cầu cập nhật khẩn cấp, đối chiếu build thực được cài với security baseline. Với doanh nghiệp, có thể dùng MSI được phân phối qua hệ thống quản trị endpoint và khóa version bằng chính sách nội bộ.

### 5.2. Linux: dùng repository đúng nhà cung cấp

Ví dụ **đã cấu hình Adoptium package repository và khóa GPG theo hướng dẫn chính thức** trên Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install temurin-25-jdk
```

Không chạy lệnh cài trước khi thêm repository đáng tin cậy tương thích với distro. Trên RHEL/Fedora có thể dùng gói `temurin-25-jdk` qua repository RPM chính thức; với Amazon Corretto hãy dùng repository/package của Amazon tương ứng. Alpine cần repository musl được vendor hỗ trợ, không áp dụng gói `.deb`/`.rpm`.

### 5.3. macOS: PKG hoặc archive đúng architecture

Tải installer JDK 25 `.pkg` của Temurin/Corretto/Oracle từ website chính thức, chọn **aarch64** cho Apple Silicon và **x64** cho máy Intel. Kiểm tra signature/checksum được công bố và đọc `java --version` sau cài. Trên macOS, có thể liệt kê các JDK được hệ thống nhận biết bằng:

```bash
/usr/libexec/java_home -V
```

Nếu máy có nhiều bản JDK, chọn đường dẫn phù hợp cho phiên làm việc và cấu hình IDE/build tool. Đừng mặc định bản hệ thống chọn lần đầu chính là bản 25 có mức vá mới nhất.

### 5.4. Kiểm tra checksum

Ví dụ trước khi cài một file `jdk25.tar.gz` đã tải từ vendor:

```bash
sha256sum jdk25.tar.gz
```

Trên PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\jdk25.zip
```

So kết quả với checksum chính thức của **chính artifact/phiên bản đó**; không sao chép checksum của ví dụ hoặc bản build cùng số version từ vendor khác. Với môi trường đòi hỏi supply-chain assurance, kiểm tra chữ ký, SBOM/provenance và chính sách allowlist registry/package.

## 6. Kiểm tra Java runtime và compiler sau khi cài

Chạy các lệnh trên máy developer, runner CI và môi trường production; lưu lại **giá trị thực**, không chỉ ghi “Java 25” vào tài liệu.

```bash
java --version
javac --version
java -XshowSettings:properties -version
```

Các property quan trọng trong output: `java.version`, `java.runtime.version`, `java.vendor`, `java.home`, `java.vm.name`, `os.name` và `os.arch`. Đặc biệt `java.home` cho biết runtime thực sự đang chạy từ thư mục nào.

Ví dụ chương trình kiểm tra độc lập:

```java
public class JdkFingerprint {
    public static void main(String[] args) {
        String[] keys = {
            "java.version", "java.runtime.version", "java.vendor",
            "java.home", "java.vm.name", "os.name", "os.arch"
        };

        for (String key : keys) {
            System.out.println(key + "=" + System.getProperty(key));
        }

        System.out.println("runtime.feature="
                + Runtime.version().feature());
    }
}
```

Lưu tệp `JdkFingerprint.java` và thực hiện:

```bash
javac --release 25 JdkFingerprint.java
java JdkFingerprint
```

Kỳ vọng `runtime.feature=25`. Nếu `javac` không nhận `--release 25`, compiler đang dùng có thể là JDK cũ dù lệnh `java` trỏ tới JDK 25. Nếu `java.vendor` không phải vendor đã chọn, hãy rà soát `PATH`, `JAVA_HOME`, toolchains, Gradle daemon, IDE và container image. **Không** coi bản `java` trên laptop là bằng chứng runtime bên Kubernetes đã được cập nhật.

### 6.1. Kiểm tra với Maven và Gradle

```bash
./mvnw --version
./gradlew --version
```

Các lệnh wrapper xác nhận Java runtime đang **chạy build tool**. Toolchain dùng để compile/test có thể khác runtime của build tool; phải kiểm tra cả hai nếu dự án bật toolchains.

Với Maven, cấu hình target API ổn định của Java 25:

```xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>
```

Với Gradle Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}
```

Theo Gradle compatibility matrix hiện hành, **Gradle 9.1.0 trở lên** hỗ trợ **chạy Gradle và dùng toolchain Java 25**. Nếu wrapper cũ hơn, nâng wrapper theo hướng dẫn Gradle trước khi chạy build trên JDK 25. Với Maven, đảm bảo Maven Compiler Plugin và các plugin test/code generation tương thích với JDK và `--release 25`; không tự mặc định chỉ đổi `JAVA_HOME` là đủ.

**Lưu ý `--release 25`:** Nó kiểm soát ngôn ngữ/API target Java 25 trong compiler; nó không thay thế kiểm thử tích hợp với database driver, JNI/native libraries, instrumentation agent hoặc framework. Nếu dự án vẫn phải chạy trên Java 21, không được build artifact yêu cầu Java 25 rồi triển khai xuống runtime 21.

## 7. Chọn image JDK 25 cho container và Kubernetes

Container là nơi lỗi chọn distro dễ bị bỏ qua nhất. Một image build có JDK 25 **không đảm bảo** stage runtime dùng cùng major/update/vendor.

Adoptium có image chính thức `eclipse-temurin`. Ví dụ build và chạy ứng dụng Maven (giả định repo có Maven wrapper và JAR sinh ra đúng tên):

```dockerfile
FROM eclipse-temurin:25-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -ntp verify

FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Điều chỉnh trước khi dùng:** tên JAR ở `target`, quyền thực thi `mvnw`, cấu hình application và user permissions cần khớp dự án. Với ứng dụng cần `jcmd` hoặc `jfr` ở container runtime để chẩn đoán, image JRE tối giản có thể thiếu công cụ; cân nhắc image JDK trong môi trường cần chẩn đoán hoặc cơ chế attach phù hợp. Có thể dùng `jlink` tạo runtime tùy chỉnh khi đã kiểm thử đầy đủ module/crypto/locales.

### 7.1. Kiểm tra image theo nền tảng thực tế

```bash
docker buildx imagetools inspect eclipse-temurin:25-jre
docker run --rm eclipse-temurin:25-jre java --version
```

Kiểm tra manifest có architecture cần triển khai (`linux/amd64`, `linux/arm64`) và image base OS có phù hợp. Temurin có image Ubuntu (mặc định), Alpine (`musl`), Red Hat UBI và các biến thể khác; mỗi tag phải được tra trong catalog vendor, không tự ghép tên tag nếu chưa xác minh.

Image tag `25-jre` là **nhãn có thể di chuyển** sang bản vá mới. Với deployment cần tái lập, hãy ghi **OCI image digest** (dạng `@sha256:...`) sau khi kiểm tra và phê duyệt; tạo PR định kỳ nâng digest. Không dùng `:latest` để quyết định môi trường production và cũng không ghim digest vô hạn làm bỏ lỡ bản vá.

### 7.2. Những lựa chọn ảnh hưởng tới runtime

| Quyết định | Khuyến nghị kiểm tra |
|---|---|
| Ubuntu/UBI hay Alpine | Có thư viện JNI/native, DNS, font, timezone, CA truststore nào phụ thuộc `glibc`/`musl` không? |
| JDK hay JRE/runtime gọn | Có cần `javac`, `jcmd`, `jfr`, `jlink` tại runtime để vận hành không? |
| AMD64 hay ARM64 | Có library native và image đa kiến trúc cho cả node pool không? |
| Image digest | Có cơ chế cập nhật, scan CVE, kiểm tra nguồn gốc artifact và rollback không? |
| Security policy | Có chạy non-root, root filesystem read-only nếu phù hợp, kiểm soát secret và quyền ghi tệp không? |
| JVM trong cgroup | Đã đo heap, CPU quota, GC/JFR và startup trong giới hạn pod thực tế chưa? |

Không phải image nhỏ nhất luôn tốt nhất: nếu giảm kích thước làm hỏng native library, TLS truststore, font hoặc khả năng xử lý sự cố, tổng chi phí vận hành có thể tăng.

## 8. Pin phiên bản trong CI/CD mà vẫn nhận được bản vá

Để build có thể tái hiện, lưu tối thiểu:

```text
Java feature:        25
JDK distribution:    Eclipse Temurin (ví dụ)
Approved update:     25.0.5.1 (tại 27/11/2026)
Runtime OS/CPU:      Linux amd64 hoặc Linux arm64
Container base:      repo:tag@sha256:digest_đã_phê_duyệt
Build tool:          Maven/Gradle wrapper version
Security review:     link release notes + ngày cập nhật
```

Không cần lưu nguyên `JAVA_HOME` của từng developer vào repo; đó là đường dẫn cục bộ. Thay vào đó, dự án có thể có tệp mô tả JDK feature/vendor, cấu hình toolchain và manifest image/digest.

### 8.1. GitHub Actions minh họa

Ví dụ workflow hiện hành với `actions/setup-java@v6`:

```yaml
name: Java 25 verify
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '25'
          check-latest: true
          cache: maven
      - run: java --version
      - run: ./mvnw -B -ntp verify
```

`java-version: '25'` và `check-latest: true` thích hợp cho **kiểm tra liên tục trên bản vá mới nhất có sẵn của distribution**. Đối với **release build yêu cầu khóa chính xác**, dùng version/build đã phê duyệt và lưu artifact/checksum hoặc sử dụng immutable base image digest. Hai mục tiêu cần khác nhau: CI kiểm tra sớm patch mới, pipeline phát hành có thể tái tạo đúng binary đã duyệt.

Workflow không tự chứng minh production đã nhận bản vá nếu bước deploy vẫn dùng image cũ. Thêm kiểm tra `java --version` trong runtime container và ghi lại metadata image tại thời điểm phát hành.

## 9. Khi nâng từ JDK cũ lên JDK 25, kiểm thử những gì?

Với ứng dụng đang chạy Java 17/21, thay JDK không chỉ là thay đường dẫn. Cần kiểm tra thư viện, plugin, bytecode và tương tác với OS.

| Hạng mục | Cách xác minh thực tế | Vì sao quan trọng |
|---|---|---|
| Compiler/bytecode | `javac --release 25`, build + unit tests | Phát hiện plugin compiler hoặc annotation processor chưa hỗ trợ. |
| Framework và agent | Chạy integration tests với Spring/Quarkus, ORM, bytecode agents được hỗ trợ | Bytecode manipulation/Java agent có thể phụ thuộc phiên bản JVM. |
| API JDK nội bộ | `jdeps --jdk-internals` trên classes/jars phù hợp | Tránh phụ thuộc API nội bộ có thể bị giới hạn hoặc thay đổi. |
| TLS, crypto, certificate | Bài test HTTPS/mTLS, truststore, cipher suites | Security defaults/provider/thuật toán có thể tác động tích hợp. |
| Native/JNI | Chạy trên đúng OS/CPU/libc của production | Dễ gặp lỗi `UnsatisfiedLinkError` hoặc ABI không tương thích. |
| Timezone, locale, encoding | Test số liệu thời gian, lịch và đa ngôn ngữ | Tzdata/CLDR được cập nhật theo các bản vá JDK. |
| Startup và hiệu năng | Đo cold-start, throughput, GC pauses, RSS, CPU | JVM flags, GC và AOT cache có thể thay đổi hành vi. |
| Monitoring/JFR | Thu bản ghi JFR hoặc metrics đại diện | Đảm bảo không mất khả năng quan sát sau nâng cấp. |
| Container/Kubernetes | Cgroup resource limits, health/readiness, permissions | Thời gian startup, heap, kernel/base image ảnh hưởng trực tiếp. |
| Rollback | Giữ image/build cũ đã duyệt và DB migration tương thích | Khi rollback không được làm hỏng dữ liệu hoặc lỡ yêu cầu bảo mật. |

Ví dụ kiểm tra phụ thuộc API JDK nội bộ trên mã đã biên dịch:

```bash
jdeps --jdk-internals --recursive target/classes
```

Lệnh này có thể cần classpath của dependencies; với Spring Boot fat JAR chứa nested jars, nên quét classes/JAR theo cấu trúc build thích hợp, không kỳ vọng `jdeps` tự giải mọi nested dependency.

### 9.1. Tác động tới các tính năng của Java 25

Java 25 bao gồm nhiều cải tiến đang hữu ích như **compact source files và instance main methods**, **module import declarations**, **flexible constructor bodies**, **Scoped Values**, **key derivation API**, **AOT cache** và cải tiến quan sát **JDK Flight Recorder**. Khi lựa chọn distribution, cần:

- Dùng **JDK 25 GA đã vá** để phát triển và chạy các API/feature đã hoàn thiện trong Java 25.
- Kiểm tra các tính năng có yêu cầu **opt-in/preview** riêng theo JEP của đúng phiên bản; không mặc định bật `--enable-preview` trong production chỉ để thử nghiệm.
- Khi đánh giá AOT cache, huấn luyện và dùng cache trên môi trường/ứng dụng tương thích, đo startup với cùng workload và kiểm soát vòng đời cache.
- Khi dùng JFR, xác minh quyền ghi recording, overhead và công cụ thu thập trong image runtime đã chọn.
- Khi dùng crypto/KDF hoặc TLS, kiểm thử provider/FIPS policy nếu hệ thống có yêu cầu pháp lý/chứng nhận đặc thù.

Không chọn một distribution chỉ vì lời quảng cáo “JDK nhanh hơn” khi chưa đo trên ứng dụng, phần cứng và giới hạn container thật. Sự khác biệt hiệu năng cần số liệu benchmark và thông tin cấu hình.

## 10. Ba bài toán chọn JDK 25 thực tế

### Tình huống A — Developer Windows, deploy Linux AMD64 trên Kubernetes

**Giả định:** nhóm phát triển trên Windows, ứng dụng build Maven, container chạy Ubuntu-based Linux AMD64, không có yêu cầu vendor contract.

Lựa chọn khả thi: **Temurin 25** cho developer/CI và image `eclipse-temurin:25-jre` ở runtime. Kiểm tra Windows MSI/winget nhận đúng bản cập nhật; build CI Linux bằng toolchain 25, scan image và kiểm tra `java --version` trong pod. Pin runtime image digest cho mỗi release và cập nhật theo security advisories.

**Không được bỏ qua:** cùng vendor nhưng khác CPU/OS và base image, do đó phải chạy integration/smoke tests trên runtime Linux, không chỉ unit tests trên Windows.

### Tình huống B — Dịch vụ AWS dùng Amazon Linux/ARM64

**Giả định:** service chạy trên EC2 Graviton hoặc EKS ARM64, có JNI hoặc dependency native.

Lựa chọn khả thi: **Corretto 25** có build/platform hỗ trợ ARM64 phù hợp, hoặc một vendor đã được bộ phận vận hành duyệt. Kiểm tra package/image cho `linux/arm64`, ABI native, lộ trình EOL 10/2032 và cập nhật patch tháng 11/2026. Không lấy image amd64 rồi mặc định chạy native trên ARM64.

**Tiêu chí nghiệm thu:** binary và image đúng platform, integration tests trên ARM64, số version runtime khớp bản duyệt, JFR/metrics hoạt động.

### Tình huống C — Dịch vụ Alpine yêu cầu chạy nhiều năm

**Giả định:** tổ chức muốn image tối giản Alpine và cần hỗ trợ dài hạn.

Chỉ chọn bản **JDK 25 musl** đã được vendor phát hành và xác nhận cho bản Alpine mục tiêu, ví dụ image Temurin/Corretto Alpine phù hợp. Kiểm thử JNI, DNS, TLS, locale và hoạt động của monitoring agent. Nếu phụ thuộc native chỉ hỗ trợ glibc, **đổi base image sang Ubuntu/UBI có glibc** thường hợp lý hơn cố chạy binary glibc trên musl.

**Tiêu chí nghiệm thu:** image đúng libc và architecture, runtime thực có bản vá bảo mật, các native libraries hoạt động, không mất khả năng cập nhật trong vòng đời hệ thống.

## 11. Ma trận kiểm chứng khi ra quyết định

Trước khi chọn bản phân phối, hoàn thành checklist này cho **từng platform triển khai**, không chỉ ghi một dòng chung “Java 25”.

| Mã | Thao tác | Kết quả cần có |
|---|---|---|
| JDK-01 | Ghi rõ vendor, license và support roadmap | Có tên distribution, điều khoản sử dụng, mốc bảo trì tương ứng. |
| JDK-02 | Chọn bản GA/security update mới nhất đã được vendor phát hành | Không dùng EA/nightly hay bản GA gốc chưa vá. |
| JDK-03 | Đối chiếu security baseline tại ngày phê duyệt | Phù hợp advisory hiện hành; ghi ngày và URL nguồn. |
| JDK-04 | Kiểm tra OS/CPU/libc | Gói cài/image khớp target `windows/mac/linux`, `amd64/arm64`, `glibc/musl`. |
| JDK-05 | Kiểm tra checksum/signature | Artifact đến từ nguồn chính thức, fingerprint được ghi nhận. |
| JDK-06 | Chạy `java --version` và `javac --version` | Java feature=25, patch/vendor/build đúng; compiler và runtime nhất quán. |
| JDK-07 | Chạy `./mvnw --version` hoặc `./gradlew --version` | Build tool dùng JDK tương thích; Gradle wrapper đủ mới. |
| JDK-08 | Build + test với `--release 25` hoặc toolchain 25 | Pass trên ứng dụng và dependencies thực. |
| JDK-09 | Kiểm tra image/digest và architecture trong container | Runtime JDK/JRE đúng, không còn image cũ trong deployment. |
| JDK-10 | Test TLS, JNI, timezone/locale và integration | Pass trên OS/CPU/libc tương đương production. |
| JDK-11 | Đo startup, GC/JFR, heap/CPU theo workload | Không có suy giảm chưa được giải thích so với baseline. |
| JDK-12 | Thiết lập lịch cập nhật và rollback | Có chủ sở hữu theo dõi CPU/security advisory và quy trình phê duyệt. |

### 11.1. Bài tập thực hành

**Bài tập 1 — Lập bảng lựa chọn.** Chọn hai distribution khác nhau trong các lựa chọn ở mục 2, ghi hỗ trợ platform, giấy phép, ngày kết thúc cập nhật, build Java 25 đã phát hành tại thời điểm kiểm tra và nơi lấy checksum. Giải thích lựa chọn cho một ứng dụng có vòng đời tối thiểu 5 năm.

**Bài tập 2 — Tạo fingerprint.** Cài JDK 25 ở máy local hoặc CI, chạy `JdkFingerprint.java`, lưu `java --version`, `javac --version`, `java.home` và `os.arch`. Tạo một trường hợp cố ý trỏ `PATH` sang JDK khác và giải thích vì sao compiler/runtime bị lệch.

**Bài tập 3 — Container đa kiến trúc.** Chọn image JDK 25 chính thức, kiểm tra manifest `linux/amd64` và `linux/arm64`, tạo image chạy ứng dụng, ghi digest sau phê duyệt. So version trong build stage, runtime image và pod. Kiểm tra xem native dependencies có thể chạy trên cả hai kiến trúc không.

**Bài tập 4 — Kịch bản security update.** Mô phỏng việc xuất hiện một bản CPU mới. Thực hiện proposal đổi package/image/digest, cập nhật CI, chạy test từ JDK-06 đến JDK-11 và ghi kế hoạch rollback. Đừng dùng bản build có cảnh báo bảo mật đã biết chỉ để tiết kiệm thời gian kiểm thử.

**Bài tập 5 — Quyết định vận hành.** Đối chiếu cùng ứng dụng trên một image glibc và một image Alpine musl. Kiểm tra kích thước image, startup, TLS, JNI và công cụ JFR; chọn nền tảng dựa trên kết quả thay vì chỉ so kích thước file.

### Câu hỏi tự kiểm tra

1. Vì sao `java --version` chỉ hiển thị `25` là chưa đủ để nghiệm thu bảo mật?
2. `25.0.5.1` và `25.0.5.1+4` khác nhau ở điểm nào? Vì sao cùng update có thể có build suffix khác giữa các vendor?
3. Một JDK có nhãn LTS có đảm bảo miễn phí mọi bản vá trong 8 năm không?
4. Khi nào nên chọn Temurin, Corretto, Azul hoặc Oracle JDK? Yếu tố nào thuộc platform, yếu tố nào thuộc giấy phép/support?
5. Vì sao một binary Linux glibc không mặc nhiên chạy đúng trên Alpine musl?
6. Vì sao cần kiểm tra bản JDK của CI và pod, kể cả khi `java --version` trên laptop đã đúng?
7. Khi GitHub Actions dùng `java-version: '25'`, điều gì khiến một release build không còn hoàn toàn tái lập được nếu artifact runtime không được pin?
8. Vì sao image `25-jre` có thể không phù hợp với tác vụ cần `jcmd`/`jfr` ngay trong production container?
9. Khi phát hiện lỗi `UnsatisfiedLinkError` trên ARM64, cần kiểm tra những thành phần nào?
10. Làm sao xây một quy trình cập nhật CPU và rollback mà không giữ JDK chưa vá quá lâu?

**Tiêu chí hoàn thành:** Bạn có thể giải thích và chứng minh **vì sao chọn một distribution JDK 25, đúng mức cập nhật và đúng binary cho OS/CPU/libc**, xác minh nó từ build đến runtime, đồng thời có lịch bảo mật và quy trình kiểm thử nâng cấp. Đó là nền tảng đáng tin cậy trước khi khai thác các tính năng Java 25 như `ScopedValue`, API dẫn xuất khóa, AOT cache và JFR trên hệ thống thực.

## 12. Tài liệu nguồn cần theo dõi

Các liên kết dưới đây là **nguồn chính thức** để kiểm tra lại thông tin khi bài viết được sử dụng vào thời điểm khác; không coi snapshot ngày 27/11/2026 là vĩnh viễn.

- [Oracle — JDK 25.0.5.1 Release Notes, security baseline và lịch CPU](https://www.oracle.com/java/technologies/javase/25-0-5-1-relnotes.html)
- [Oracle — Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [Oracle — JDK licensing FAQ và NFTC cho JDK 25](https://www.oracle.com/java/technologies/javase/jdk-faqs.html)
- [Eclipse Adoptium — Temurin 25 downloads](https://adoptium.net/temurin/releases/?version=25)
- [Eclipse Adoptium — Support roadmap](https://adoptium.net/support)
- [Eclipse Adoptium — Supported platforms](https://adoptium.net/supported-platforms/)
- [Eclipse Adoptium — Installation và package managers](https://adoptium.net/installation)
- [Eclipse Adoptium — Container images](https://adoptium.net/installation/containers)
- [Amazon — Corretto FAQs, support calendar](https://aws.amazon.com/corretto/faqs/)
- [Amazon — Corretto 25 installation](https://docs.aws.amazon.com/corretto/latest/corretto-25-ug/generic-linux-install.html)
- [Azul — Support lifecycle](https://docs.azul.com/core/support-lifecycle)
- [Gradle — Java compatibility matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [GitHub Actions — setup-java](https://github.com/actions/setup-java)
- [Java releases — lịch cập nhật bảo mật OpenJDK](https://ops.java/releases/)

**Nguyên tắc sử dụng tài liệu lâu dài:** Khi cần ra quyết định mới, trước tiên cập nhật bảng ở mục 4 theo release notes và security advisory của nhà cung cấp thực tế; sau đó kiểm tra lại OS/CPU/libc, giấy phép và lịch hỗ trợ. Không tự động coi bản version hoặc một lệnh cài đặt trong bài là lựa chọn mới nhất ở tương lai.
