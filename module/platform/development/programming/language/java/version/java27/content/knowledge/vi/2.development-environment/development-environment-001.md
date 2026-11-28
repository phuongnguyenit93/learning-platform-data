# Lựa chọn bản phân phối và cài đặt JDK phù hợp với Java 27

Java 27 đã được phát hành chính thức. Để biên dịch và chạy chương trình bằng phiên bản này, bạn cần cài một **JDK 27** phù hợp với hệ điều hành và kiến trúc máy tính. Có nhiều nhà cung cấp JDK; các bản phân phối có thể khác nhau về lịch cập nhật, điều khoản sử dụng, nền tảng hỗ trợ và dịch vụ hỗ trợ, dù cùng hướng tới Java SE 27.

Bài viết này tập trung vào các bản phân phối còn được duy trì tại ngày **27/11/2026**. Khi tải JDK, hãy kiểm tra lại phiên bản cập nhật và danh sách nền tảng trên trang chính thức của nhà cung cấp vì các gói cài đặt có thể thay đổi theo thời gian.

## 1. Phân biệt phiên bản Java và bản phân phối JDK

**Java 27** chỉ phiên bản của nền tảng Java. **Bản phân phối JDK** là bộ công cụ do một nhà cung cấp xây dựng, đóng gói và cập nhật, chẳng hạn Oracle JDK, Eclipse Temurin hoặc Amazon Corretto.

Một JDK dùng cho phát triển thường bao gồm:

- `java`: khởi chạy chương trình Java.
- `javac`: biên dịch mã nguồn `.java` thành bytecode `.class`.
- `jshell`: chạy thử các biểu thức và đoạn mã Java tương tác.
- Các công cụ đóng gói, kiểm tra, tạo tài liệu và chẩn đoán như `jar`, `javadoc`, `jcmd` và `jstack`.
- Thư viện chuẩn và môi trường chạy Java cần thiết.

Vì vậy, khi học lập trình hoặc xây dựng ứng dụng, hãy chọn gói **JDK**, không chỉ chọn một môi trường chạy tối giản. Bạn không cần cài thêm một JRE riêng để có trình biên dịch `javac`.

Các nhà cung cấp có thể phát hành JDK với số bản dựng khác nhau. Ví dụ, cùng nhánh cập nhật Java 27 tháng 11/2026, Oracle JDK và Temurin có thể hiển thị `27.0.1.1+4`, trong khi Amazon Corretto hiển thị `27.0.1.1.4`. Hãy đối chiếu cả phiên bản Java, nhà cung cấp và thông tin bản dựng thay vì cho rằng chuỗi phiên bản phải giống hệt nhau.

## 2. Hiểu chu kỳ phát hành của Java 27 trước khi chọn

JDK 27 được phát hành chính thức ngày **15/09/2026**. Bản cập nhật bảo mật và sửa lỗi `27.0.1.1` được phát hành ngày **17/11/2026**; đây là bản cập nhật nên ưu tiên khi cài mới tại thời điểm viết bài.

Java 27 là một **Feature Release**, không phải bản LTS. Java 25 hiện là bản LTS mới nhất. Theo lịch phát hành OpenJDK, JDK 28 dự kiến thay thế JDK 27 vào tháng 03/2027; lịch hỗ trợ cụ thể còn phụ thuộc vào nhà cung cấp JDK bạn chọn.

Hãy quyết định theo mục tiêu:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Học và thực hành đúng tính năng của Java 27 | JDK 27, luôn dùng bản cập nhật mới nhất từ nhà cung cấp |
| Dự án hoặc bài tập yêu cầu biên dịch/chạy trên Java 27 | JDK 27 và cấu hình IDE, công cụ build cùng dùng phiên bản này |
| Chọn nền tảng cho hệ thống cần chu kỳ bảo trì dài | Cân nhắc Java 25 LTS, trừ khi yêu cầu kỹ thuật bắt buộc Java 27 |
| Kiểm thử khả năng tương thích khi nâng cấp | Cài song song JDK 25 LTS và JDK 27, sau đó chọn JDK theo từng dự án |

Không nên chọn Java 27 cho một hệ thống dài hạn chỉ vì đây là số phiên bản mới hơn. Với Feature Release, nhóm phát triển cần có kế hoạch cập nhật sang phiên bản kế tiếp khi chu kỳ hỗ trợ của nhà cung cấp kết thúc.

## 3. Các bản phân phối JDK 27 đang được cung cấp

Những lựa chọn dưới đây đều có bản JDK 27 chính thức. Hãy tải trực tiếp từ trang của nhà cung cấp và đọc điều khoản áp dụng cho đúng bản phân phối, phiên bản và mục đích sử dụng.

| Bản phân phối | Đặc điểm | Khi nào nên chọn |
|---|---|---|
| **Eclipse Temurin** | Bản dựng OpenJDK do Eclipse Adoptium cung cấp; các binary được kiểm thử và được cung cấp miễn phí, không giới hạn mục đích sử dụng theo thông báo của dự án. Có gói cài đặt và gói cho nhiều hệ điều hành. | Lựa chọn mặc định phù hợp cho người học, nhóm phát triển cần một JDK OpenJDK phổ biến và không có yêu cầu riêng từ nhà cung cấp khác. |
| **Amazon Corretto** | Bản phân phối OpenJDK miễn phí, đa nền tảng và sẵn sàng cho môi trường production. Corretto 27 được AWS công bố hỗ trợ đến tháng 04/2027. Có gói macOS Intel x64 và Apple Silicon ARM64. | Phù hợp khi dự án chạy trên AWS hoặc tổ chức đã chuẩn hóa quy trình cập nhật và vận hành theo Corretto. Cũng là lựa chọn phù hợp cho máy Mac Intel cần JDK 27. |
| **Oracle JDK** | Bản JDK do Oracle phát hành, có bộ cài và tài liệu cài đặt chính thức cho Windows, macOS và Linux. Oracle công bố JDK 27 được sử dụng trong production và phân phối lại miễn phí theo Oracle No-Fee Terms and Conditions đến tháng 03/2027. | Phù hợp khi dự án dùng hệ sinh thái Oracle, cần theo tài liệu hoặc quy trình hỗ trợ của Oracle, hoặc tổ chức đã chọn Oracle JDK. |

### Chọn nhanh theo tình huống

- **Chưa có yêu cầu từ dự án hoặc doanh nghiệp:** chọn Eclipse Temurin 27.
- **Ứng dụng triển khai trên AWS:** có thể chọn Amazon Corretto 27 để đồng nhất JDK phát triển và vận hành.
- **Cần Oracle JDK hoặc hỗ trợ thương mại từ Oracle:** chọn Oracle JDK và kiểm tra điều khoản sử dụng hiện hành.
- **Dùng Mac Intel:** ưu tiên Amazon Corretto 27 hoặc một bản phân phối khác có binary macOS x64. Eclipse Temurin 27 hiện không phát hành bản macOS x64; trang tải Oracle JDK 27 hiện cũng chỉ liệt kê gói macOS ARM64.
- **Cần thời gian hỗ trợ dài:** xem xét JDK 25 LTS và lịch hỗ trợ của nhà cung cấp trước khi chốt nền tảng.

Không có một nhà cung cấp luôn tốt nhất cho mọi dự án. Hãy ưu tiên bản phân phối mà nhóm phát triển có thể cập nhật đều đặn, kiểm soát được điều khoản sử dụng và dùng nhất quán trong môi trường phát triển, kiểm thử và triển khai.

## 4. Xác định hệ điều hành và kiến trúc CPU

Trước khi tải, xác định đúng hệ điều hành và kiến trúc CPU. Tải nhầm kiến trúc có thể khiến bộ cài không chạy hoặc JVM không khởi động được.

| Nền tảng | Cách nhận biết thường gặp | Gói cần tìm |
|---|---|---|
| Windows trên máy Intel/AMD 64-bit | `x64` hoặc `AMD64` | Windows x64, thường là `.msi` hoặc `.exe` |
| macOS trên Apple Silicon | `arm64` hoặc `aarch64` | macOS ARM64 / AArch64, thường là `.pkg` hoặc `.dmg` |
| macOS trên máy Intel | `x86_64` | macOS x64; kiểm tra kỹ nhà cung cấp có phát hành Java 27 cho kiến trúc này hay không |
| Linux trên Intel/AMD 64-bit | `x86_64` | Linux x64, thường là `.deb`, `.rpm` hoặc `.tar.gz` |
| Linux trên máy chủ ARM 64-bit | `aarch64` hoặc `arm64` | Linux ARM64 / AArch64, chọn đúng định dạng gói của bản phân phối Linux |

Có thể kiểm tra kiến trúc bằng lệnh sau:

```powershell
# Windows PowerShell
$env:PROCESSOR_ARCHITECTURE
```

```bash
# macOS hoặc Linux
uname -m
```

Trên Windows, `AMD64` thường tương ứng với gói x64; `ARM64` tương ứng với gói ARM64 nếu nhà cung cấp có phát hành. Trên macOS, `arm64` là Apple Silicon và `x86_64` là máy Intel. Trên Linux, `x86_64` và `aarch64` là hai kiến trúc 64-bit phổ biến.

## 5. Tải JDK 27 từ nguồn chính thức

Các trang tải chính thức:

- [Eclipse Temurin 27](https://adoptium.net/temurin/releases/?version=27)
- [Amazon Corretto 27](https://docs.aws.amazon.com/corretto/latest/corretto-27-ug/downloads-list.html)
- [Oracle JDK 27](https://www.oracle.com/java/technologies/downloads/)

Khi mở trang tải, chọn lần lượt:

1. **Version:** 27.
2. **Package:** JDK.
3. **Operating System:** hệ điều hành đang sử dụng.
4. **Architecture:** x64 hoặc ARM64 đúng với máy.
5. **Installer/Package Type:** định dạng phù hợp với hệ điều hành, ví dụ MSI trên Windows, PKG trên macOS hoặc DEB/RPM trên Linux.

Nếu có nhiều bản cập nhật, chọn bản mới nhất của nhánh 27. Tại ngày 27/11/2026, nên chọn bản cập nhật `27.0.1.1` hoặc bản dựng tương ứng do nhà cung cấp phát hành. Không tải bản thử nghiệm Early Access hoặc nightly build để làm môi trường học và phát triển thông thường.

Chỉ tải từ website hoặc kho gói chính thức. Nếu nhà cung cấp công bố SHA-256 hoặc chữ ký số, hãy dùng chúng để kiểm tra file tải xuống trước khi cài, nhất là khi triển khai trên nhiều máy hoặc máy chủ.

## 6. Cài đặt trên Windows

Ví dụ dưới đây dùng Eclipse Temurin 27 trên Windows x64. Nếu chọn Oracle JDK hoặc Corretto, hãy tải đúng bộ cài Windows x64 từ trang tương ứng; các bước chạy trình cài đặt tương tự.

1. Mở [trang tải Temurin 27](https://adoptium.net/temurin/releases/?version=27), chọn `JDK`, `Windows`, `x64` và gói `MSI`.
2. Mở file `.msi` vừa tải để khởi động trình cài đặt.
3. Chấp nhận điều khoản sử dụng nếu bạn đồng ý.
4. Ở màn hình tùy chọn, bật tính năng thêm JDK vào `PATH`. Bật thêm tính năng cập nhật biến môi trường `JAVA_HOME` nếu trình cài đặt cung cấp tùy chọn này.
5. Hoàn tất cài đặt, đóng cửa sổ terminal đang mở và mở một cửa sổ PowerShell mới.

Kiểm tra:

```powershell
java -version
javac -version
where.exe java
$env:JAVA_HOME
```

Hai lệnh đầu phải hiển thị phiên bản Java 27. `where.exe java` cho biết Windows đang tìm thấy những file `java.exe` nào theo thứ tự trong `PATH`. Nếu kết quả trỏ tới một JDK cũ, hãy kiểm tra lại thứ tự các thư mục trong `PATH`.

### Thiết lập `JAVA_HOME` thủ công

Nếu `JAVA_HOME` chưa được tạo tự động:

1. Mở **Settings** và tìm **Edit the system environment variables**.
2. Trong cửa sổ **System Properties**, chọn **Environment Variables**.
3. Tạo biến `JAVA_HOME` trỏ tới thư mục gốc của JDK 27, ví dụ thư mục cài đặt nằm dưới `C:\Program Files\Eclipse Adoptium\`. Dùng đúng tên thư mục thực tế trên máy.
4. Chỉnh biến `Path`, thêm `%JAVA_HOME%\bin`.
5. Lưu thay đổi và mở terminal mới để kiểm tra lại.

`JAVA_HOME` phải trỏ tới thư mục gốc của JDK; không thêm `\bin` vào giá trị của biến này. Đường dẫn thực tế thay đổi theo nhà cung cấp và bản cập nhật.

## 7. Cài đặt trên macOS

### Mac dùng Apple Silicon

1. Mở [trang tải Temurin 27](https://adoptium.net/temurin/releases/?version=27).
2. Chọn `JDK`, `macOS`, `AArch64` và gói `PKG`.
3. Mở file `.pkg`, làm theo trình hướng dẫn và hoàn tất cài đặt.
4. Mở Terminal mới và kiểm tra:

```bash
java -version
javac -version
/usr/libexec/java_home -V
```

Nếu cần chọn JDK 27 cho terminal hiện tại:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 27)
export PATH="$JAVA_HOME/bin:$PATH"
```

Để áp dụng cho các phiên Terminal sau, thêm hai dòng `export` vào `~/.zshrc` nếu đang dùng zsh, sau đó chạy `source ~/.zshrc` hoặc mở Terminal mới.

### Mac dùng Intel

Eclipse Temurin 27 không cung cấp binary macOS x64. Hãy chọn một bản phân phối có gói Java 27 cho `x86_64`, chẳng hạn Amazon Corretto 27. Trên trang Corretto, tải gói macOS x64 dạng `.pkg`, cài đặt theo trình hướng dẫn rồi chạy các lệnh kiểm tra ở trên.

Không chọn gói ARM64 cho máy Intel. Nếu một nhà cung cấp không liệt kê macOS x64 trong trang tải của Java 27, hãy xem đó là kiến trúc chưa được nhà cung cấp hỗ trợ cho phiên bản này.

## 8. Cài đặt trên Linux

Chọn đúng định dạng gói theo hệ điều hành:

- Debian hoặc Ubuntu: tải gói `.deb` cho Linux x64 hoặc AArch64 tương ứng.
- Fedora, RHEL hoặc hệ thống tương thích RPM: tải gói `.rpm` đúng kiến trúc.
- Hệ thống không có gói DEB/RPM phù hợp: dùng archive `.tar.gz` từ trang tải chính thức và làm theo hướng dẫn cài đặt của nhà cung cấp.

Ví dụ cài một gói DEB đã tải về trên Debian/Ubuntu:

```bash
sudo apt install ./ten-goi-jdk-27.deb
```

Ví dụ cài gói RPM trên Fedora/RHEL:

```bash
sudo dnf install ./ten-goi-jdk-27.rpm
```

Thay tên file mẫu bằng đúng tên gói đã tải. Nếu muốn cài và cập nhật bằng kho của Eclipse Adoptium, hãy làm theo hướng dẫn cấu hình repository trên [trang cài đặt Linux của Adoptium](https://adoptium.net/installation/linux/); tên gói JDK có dạng `temurin-27-jdk` sau khi repository tương ứng đã được cấu hình.

Kiểm tra sau cài đặt:

```bash
java -version
javac -version
which -a java
```

Nếu cần đặt `JAVA_HOME`, lấy đường dẫn thư mục gốc JDK từ vị trí cài đặt của nhà cung cấp rồi cấu hình trong shell hiện tại:

```bash
export JAVA_HOME=/duong/dan/toi/jdk-27
export PATH="$JAVA_HOME/bin:$PATH"
```

Thay `/duong/dan/toi/jdk-27` bằng đường dẫn thật trên máy. Để lưu lâu dài, thêm các dòng này vào file cấu hình shell mà bạn đang dùng, chẳng hạn `~/.bashrc` hoặc `~/.zshrc`, rồi mở terminal mới.

## 9. Xác minh JDK đã sẵn sàng

Chạy cả `java` và `javac`:

```bash
java --version
javac --version
jshell --version
```

Kết quả cần thể hiện nhánh phiên bản **27**. Chuỗi chi tiết có thể khác giữa Oracle JDK, Temurin và Corretto. Nếu `java` là phiên bản 27 nhưng `javac` không được tìm thấy hoặc thuộc phiên bản khác, hãy kiểm tra `JAVA_HOME` và thứ tự `PATH`.

Bạn cũng có thể kiểm tra bằng một chương trình nhỏ. Tạo file `Hello.java`:

```java
class Hello {
    public static void main(String[] args) {
        System.out.println("Java 27 is ready");
    }
}
```

Biên dịch và chạy:

```bash
javac Hello.java
java Hello
```

Nếu terminal in ra `Java 27 is ready`, JDK đã có thể biên dịch và chạy một chương trình Java cơ bản.

## 10. Xử lý các lỗi cài đặt thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Terminal báo không tìm thấy `java` | Thư mục `bin` của JDK chưa nằm trong `PATH`, hoặc terminal chưa nạp biến môi trường mới | Kiểm tra `PATH`, thêm `%JAVA_HOME%\bin` trên Windows hoặc `$JAVA_HOME/bin` trên macOS/Linux; mở terminal mới |
| `java` chạy được nhưng `javac` không tồn tại | Đang trỏ tới một môi trường chỉ có runtime hoặc `PATH` chưa trỏ tới JDK | Cài gói JDK và kiểm tra `JAVA_HOME` trỏ tới thư mục gốc của JDK |
| `java -version` hiển thị phiên bản cũ | Máy có nhiều JDK và đường dẫn cũ đứng trước trong `PATH` | Dùng `where.exe java` trên Windows hoặc `which -a java` trên macOS/Linux để tìm các bản đang được gọi; sắp xếp lại `PATH` |
| Bộ cài báo sai kiến trúc hoặc không tương thích | Đã tải nhầm x64/ARM64 hoặc nhà cung cấp không phát hành gói cho hệ điều hành đó | Kiểm tra kiến trúc bằng `uname -m` hoặc `$env:PROCESSOR_ARCHITECTURE`, rồi tải lại đúng gói |
| IDE chạy phiên bản khác terminal | IDE hoặc cấu hình dự án đang chọn một JDK riêng | Chọn JDK 27 trong phần cấu hình Project SDK/Gradle JVM/Maven JDK tương ứng với IDE và công cụ build |
| Cập nhật JDK nhưng terminal vẫn dùng bản cũ | Biến môi trường hoặc liên kết hệ thống chưa trỏ sang bản mới | Kiểm tra lại `JAVA_HOME`, `PATH` và cơ chế chọn phiên bản JDK của hệ điều hành |

Khi một máy có nhiều JDK, hãy xác định rõ phiên bản theo từng dự án. Không cần gỡ JDK khác nếu chúng vẫn phục vụ dự án đang duy trì; điều quan trọng là IDE, công cụ build và môi trường chạy của mỗi dự án cùng dùng đúng phiên bản đã chọn.

## 11. Tài liệu tham khảo chính thức

- [Oracle — Java Downloads](https://www.oracle.com/java/technologies/downloads/): phiên bản JDK hiện hành, gói tải, kiến trúc và điều khoản Oracle No-Fee Terms and Conditions.
- [Oracle — JDK 27 Installation Guide](https://docs.oracle.com/en/java/javase/27/install/index.html): hướng dẫn cài Oracle JDK 27 trên Windows, macOS và Linux.
- [OpenJDK — JDK Releases](https://ops.java/releases/): ngày phát hành, lịch cập nhật và chu kỳ hỗ trợ các nhánh JDK.
- [Eclipse Adoptium — Temurin 27 Available](https://adoptium.net/news/2026/10/eclipse-temurin-27-available): công bố Temurin 27 và lưu ý không phát hành bản macOS x64.
- [Eclipse Adoptium — November 2026 security update](https://adoptium.net/news/2026/11/temurin-november-2026-cspu-java4shell): phiên bản Temurin 27.0.1.1+4 có bản vá trong đợt cập nhật tháng 11/2026.
- [Eclipse Adoptium — Installation](https://adoptium.net/installation): hướng dẫn cài Temurin bằng gói phù hợp với hệ điều hành.
- [Amazon Corretto — Downloads for Corretto 27](https://docs.aws.amazon.com/corretto/latest/corretto-27-ug/downloads-list.html): gói cài và checksum cho Windows, macOS và Linux.
- [Amazon Corretto — FAQ](https://aws.amazon.com/corretto/faqs/): lịch hỗ trợ của Corretto 27 và các phiên bản LTS.

Các phiên bản, lịch hỗ trợ, kiến trúc và điều khoản sử dụng trong bài được đối chiếu theo thông tin công bố đến ngày **27/11/2026**. Trước khi triển khai thực tế, hãy kiểm tra lại trang phát hành của nhà cung cấp để chọn bản cập nhật mới nhất và điều khoản đang có hiệu lực.
