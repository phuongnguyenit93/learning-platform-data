# Lựa chọn JDK được hỗ trợ để thực hành Java còn giá trị hiện nay

> Bối cảnh: Bài học thuộc chủ đề Java 15, nhưng mục tiêu là học và chạy **những kiến thức Java vẫn được sử dụng, duy trì và hỗ trợ ở hiện tại**. Không cần cài JDK 15 chỉ vì tên module là “Java 15”. Thông tin về phiên bản dưới đây được đối chiếu tại thời điểm **08/11/2026**; trước khi cài đặt hoặc triển khai, luôn kiểm tra lại vòng đời hỗ trợ và bản cập nhật của nhà phân phối.

## 1. Hiểu đúng “JDK được hỗ trợ”

- **JDK (Java Development Kit)** gồm trình biên dịch `javac`, công cụ chạy `java`, thư viện và các công cụ phát triển. Để **học lập trình Java**, hãy cài **JDK**, không chỉ cài JRE (Java Runtime Environment).
- **Phiên bản Java/JDK** (ví dụ 21, 25) xác định ngôn ngữ, API tiêu chuẩn và định dạng bytecode tương ứng.
- **Nhà phân phối (distribution/vendor)** là đơn vị cung cấp bản build và các bản vá, chẳng hạn **Eclipse Temurin (Adoptium)**, Oracle JDK, Amazon Corretto, Azul Zulu hoặc Microsoft Build of OpenJDK. Cùng một major version không có nghĩa mọi nhà phân phối có lịch hỗ trợ hay điều kiện giấy phép giống nhau.
- **LTS (Long-Term Support)** là dòng được một hoặc nhiều nhà phân phối cam kết duy trì lâu hơn các bản phát hành sáu tháng. LTS không đồng nghĩa với “được hỗ trợ mãi mãi”. Cần xem cả **thời hạn hỗ trợ của vendor**, **bản vá bảo mật mới**, **hệ điều hành/CPU được hỗ trợ** và **điều khoản sử dụng**.
- **GA/stable** là bản phát hành chính thức. Bản Early Access, nightly hoặc tính năng preview chỉ dùng khi chủ đích thử nghiệm; không phải lựa chọn mặc định để học kiến thức ổn định.

Điểm mấu chốt: chọn **một bản JDK LTS đang nhận cập nhật bảo mật từ nhà phân phối đáng tin cậy**, rồi dùng thống nhất phiên bản ấy trong terminal, IDE và dự án.

## 2. Nên chọn phiên bản nào?

| Dòng JDK | Tình trạng tại 08/11/2026 | Cách sử dụng phù hợp |
| --- | --- | --- |
| **JDK 25 (LTS)** | Dòng LTS mới nhất | **Lựa chọn mặc định** cho người bắt đầu học Java và bài thực hành độc lập, khi khóa học/dự án không yêu cầu phiên bản thấp hơn. |
| **JDK 21 (LTS)** | Dòng LTS trước JDK 25, vẫn có nhà phân phối duy trì | Chọn khi giáo trình, framework, thư viện hoặc dự án đã xác nhận tương thích với Java 21. |
| **JDK 17 (LTS)** | Một số nhà phân phối vẫn cung cấp bản cập nhật | Chỉ ưu tiên khi dự án đang duy trì thực sự yêu cầu Java 17; với bài học mới không có ràng buộc, ưu tiên 25 hoặc 21. |
| **JDK 27 (feature release)** | Bản Java mới nhất, nhưng **không phải LTS** | Phù hợp thử tính năng mới trong thời gian ngắn; không cần thiết cho mục tiêu học nền tảng ổn định. |
| **JDK 15** | Bản phát hành ngắn hạn, đã qua vòng đời cập nhật thông thường | **Không cài làm môi trường học mặc định**. Vẫn có thể học các khái niệm từ giai đoạn Java 15 đã trở thành chuẩn và còn áp dụng trên JDK LTS hiện hành. |

**Quy tắc quyết định:**

1. **Học Java độc lập, không bị ràng buộc:** chọn bản **Eclipse Temurin JDK 25 LTS** mới nhất phù hợp với máy.
2. **Làm theo dự án, bài tập có cấu hình hoặc giáo trình đã xác định:** ưu tiên major version được dự án công bố và đang được vendor hỗ trợ (thường là **21**, đôi khi **17**), kể cả khi máy có cài 25.
3. **Muốn kiểm tra tính tương thích với nhiều phiên bản:** có thể cài song song 25 và 21, nhưng luôn chỉ rõ JDK nào dùng để chạy, biên dịch và build.
4. **Muốn thử JDK 27 hoặc preview:** dùng môi trường riêng; kiểm tra kỹ trạng thái cuối cùng của tính năng trước khi đưa kiến thức vào bài học chính.

**Vì sao khuyến nghị Temurin?** Eclipse Adoptium công khai danh sách bản LTS, gói cài cho nhiều hệ điều hành, lịch cập nhật và chính sách hỗ trợ. Đây là một lựa chọn thuận tiện để học Java. Các nhà phân phối JDK đang được hỗ trợ khác vẫn có thể dùng nếu phù hợp yêu cầu dự án và giấy phép.

**Lưu ý giấy phép:** chính sách của **Oracle JDK** không nhất thiết trùng với Temurin hoặc các bản OpenJDK khác; các bản cập nhật Oracle JDK 21 từ tháng 10/2026 chịu điều kiện cấp phép khác với giai đoạn cập nhật NFTC trước đó. Khi sử dụng trong tổ chức hoặc phân phối sản phẩm, đọc điều khoản **của đúng vendor và đúng bản phát hành** trước khi chọn.

## 3. Tiêu chí kiểm tra trước khi tải

- **Version:** chọn major version đang nhận cập nhật, ưu tiên LTS; tải **bản vá mới nhất của dòng đó**, không cố định vào một số patch cũ trong hướng dẫn.
- **Package:** chọn **JDK** (có `javac`), không chọn nhầm gói chỉ có JRE.
- **Hệ điều hành:** Windows, macOS hoặc bản phân phối Linux của bạn phải nằm trong danh sách hỗ trợ của gói cài.
- **Kiến trúc CPU:** chọn đúng `x64` cho phần lớn máy Intel/AMD 64-bit, hoặc `aarch64/arm64` cho thiết bị ARM tương ứng (ví dụ nhiều máy Mac Apple Silicon).
- **Nguồn tải:** lấy từ trang chính thức của vendor hoặc kho gói mà vendor hướng dẫn; ưu tiên gói có checksum/chữ ký và kiểm tra khi quy trình yêu cầu.
- **Tương thích dự án:** xem cấu hình Java của dự án, thư viện, framework, công cụ build, IDE và môi trường chạy thực tế. “Chạy được trên máy mình” chưa đủ để kết luận tương thích khi triển khai.
- **Bảo trì:** biết ai cung cấp các bản vá, lịch cập nhật, ngày hết hỗ trợ và cách nâng cấp patch.

Các trang nên kiểm tra: [Temurin Releases](https://adoptium.net/temurin/releases/), [Temurin Support](https://adoptium.net/support/) và [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html).

## 4. Cài đặt một JDK LTS

### Windows

1. Mở [trang cài đặt chính thức của Adoptium](https://adoptium.net/installation) hoặc [Temurin Releases](https://adoptium.net/temurin/releases/); chọn **JDK 25 LTS**, Windows và đúng kiến trúc máy.
2. Dùng gói **MSI** theo hướng dẫn của Adoptium. Khi thiết lập, bật lựa chọn đưa Java vào `PATH` và có thể bật `JAVA_HOME`.
3. Hoặc nếu máy có Windows Package Manager, chạy trong PowerShell:

```powershell
winget install EclipseAdoptium.Temurin.25.JDK
```

4. Đóng và mở lại terminal/IDE sau khi cài để nhận biến môi trường mới.

### macOS

Tải đúng gói **PKG** của Temurin JDK 25 (chọn **aarch64/arm64** cho Apple Silicon, **x64** cho Intel), cài theo hướng dẫn tại [Adoptium Installation](https://adoptium.net/installation), rồi mở terminal mới. Nếu có nhiều JDK, kiểm tra đường dẫn được chọn trước khi chạy bài.

### Linux

Dùng hướng dẫn [Adoptium Linux Installation](https://adoptium.net/installation/linux) tương ứng Ubuntu/Debian, Fedora/RHEL hoặc bản phân phối được hỗ trợ. Với hệ Debian/Ubuntu **sau khi đã thêm kho gói Adoptium theo hướng dẫn**, tên gói JDK 25 là `temurin-25-jdk`. Với Fedora/RHEL và kho đã cấu hình, dùng `sudo dnf install temurin-25-jdk`. Không sao chép lệnh cài từ hướng dẫn dành cho hệ điều hành khác.

### JAVA_HOME và PATH

- `JAVA_HOME` trỏ tới **thư mục gốc của JDK**, không phải thư mục `bin` và không phải tệp `java`.
- `PATH` cần ưu tiên thư mục `bin` của JDK muốn sử dụng. Nếu nhiều bản Java cùng tồn tại, thứ tự `PATH` có thể khiến terminal dùng bản khác với mong đợi.
- IDE có thể chọn JDK riêng cho **project SDK**, **Gradle JVM** hoặc **Maven runner**; cài đúng JDK trong hệ điều hành chưa đảm bảo IDE dùng đúng bản đó.

## 5. Kiểm tra JDK thật sự đang hoạt động

Mở một terminal mới và chạy:

```text
java --version
javac --version
```

Dòng đầu xác nhận runtime, dòng sau xác nhận trình biên dịch. Nếu chọn JDK 25, cả hai cần hiển thị **major version 25**; số patch và tên vendor phụ thuộc bản cài thực tế. Nếu `javac` báo “not found”/“not recognized”, khả năng thường gặp là chỉ cài runtime hoặc `PATH` đang trỏ sai.

Để kiểm tra lệnh đang lấy Java từ vị trí nào:

```powershell
# PowerShell trên Windows
Get-Command java -All
Get-Command javac -All
```

```bash
# Terminal trên macOS/Linux
type -a java
type -a javac
```

Sau đó kiểm tra `JAVA_HOME` (nếu đã cấu hình) và đường dẫn JDK trong IDE. Khi dùng Maven hoặc Gradle, kiểm tra riêng `mvn -version` hoặc `gradle --version` để biết JVM nào chạy công cụ build; không suy ra phiên bản build chỉ từ `java --version`.

## 6. Bài thực hành xác nhận biên dịch và chạy

Tạo tệp **`HelloJdk.java`** ở một thư mục học tập, nội dung đầy đủ như sau:

```java
public class HelloJdk {
    public static void main(String[] args) {
        System.out.println("Java OK");
    }
}
```

Mở terminal tại thư mục chứa tệp và chạy:

```bash
javac -encoding UTF-8 HelloJdk.java
java HelloJdk
```

Kết quả chuẩn trên stdout:

```text
Java OK
```

Giải thích: `javac` tạo tệp `HelloJdk.class` từ nguồn `.java`; `java HelloJdk` chạy lớp `HelloJdk` trên JVM. Tên tệp phải khớp với tên `public class`, và khi chạy không thêm đuôi `.class`. Ví dụ không cần thư viện ngoài, preview feature hay API cũ.

### Nếu dự án cần chạy trên Java 21

Ngay cả khi đang cài JDK 25, bạn có thể biên dịch ví dụ đơn giản trên theo API, cú pháp và bytecode Java 21 bằng:

```bash
javac --release 21 -encoding UTF-8 HelloJdk.java
java HelloJdk
```

Tùy chọn `--release 21` giúp trình biên dịch kiểm tra tập API và mức ngôn ngữ mục tiêu thay vì chỉ giảm phiên bản bytecode. **Nhưng** vẫn cần kiểm thử ứng dụng thực tế trên JDK/JRE 21 và kiểm tra các thư viện bên thứ ba; `--release` không thay thế kiểm thử runtime.

Lỗi `UnsupportedClassVersionError` thường có nghĩa bytecode được tạo bằng một phiên bản Java mới hơn runtime đang cố chạy. Khi gặp lỗi, so sánh JDK biên dịch, target release, runtime thật và các dependency trước khi đổi cấu hình.

## 7. Học kiến thức từ thời Java 15 trên JDK mới như thế nào?

Tên bài hoặc thời điểm một khái niệm ra đời **không buộc phải dùng lại JDK cũ**. Ví dụ, **text blocks** trở thành tính năng chuẩn từ Java 15 và vẫn có thể dùng trên JDK LTS hiện đại:

```java
public class TextBlockExample {
    public static void main(String[] args) {
        String message = """
                Học Java
                với JDK LTS
                """;
        System.out.print(message);
    }
}
```

Với tệp **`TextBlockExample.java`**, chạy:

```bash
javac -encoding UTF-8 TextBlockExample.java
java TextBlockExample
```

Stdout:

```text
Học Java
với JDK LTS
```

Text block là cú pháp ổn định, làm mã chuỗi nhiều dòng dễ đọc hơn. Khi đọc tài liệu Java 15 cũ, phải phân biệt rõ **tính năng đã trở thành chuẩn** với **preview/incubator của thời điểm đó**. Chẳng hạn `record` được chuẩn hóa ở Java 16 và sealed classes ở Java 17: nếu muốn học chúng ngày nay, đọc cú pháp và tài liệu chuẩn của JDK hiện hành, thay vì bật cờ preview từ bài hướng dẫn cũ. Cũng tránh học theo quy trình applet, browser Java plugin hoặc Java Web Start như một hướng phát triển ứng dụng Java mới.

## 8. Những lỗi lựa chọn/cấu hình dễ gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cài JDK 15 chỉ vì bài thuộc module “Java 15” | Môi trường học dựa vào dòng đã hết vòng đời cập nhật thông thường | Dùng JDK 25/21 LTS đang được duy trì; thực hành kiến thức đã ổn định. |
| Chọn Java 27 chỉ vì số phiên bản lớn nhất | Dòng feature release có thời gian hỗ trợ ngắn | Với học tập và dự án dài hạn, ưu tiên LTS. |
| Cài JRE thay JDK | Không có trình biên dịch `javac` | Tải gói JDK, sau đó kiểm tra `javac --version`. |
| `java` và `javac` trỏ tới các bản khác nhau | Biên dịch hoặc chạy sai phiên bản, khó tìm lỗi | Kiểm tra đường dẫn, `JAVA_HOME`, `PATH` và cấu hình IDE. |
| Dùng API chỉ có ở JDK mới rồi chạy bằng JDK cũ | Lỗi tương thích lúc biên dịch hoặc chạy | Xác định target, dùng `--release` khi phù hợp và chạy test trên runtime mục tiêu. |
| Giữ nguyên patch JDK quá lâu | Bỏ lỡ bản vá bảo mật/corrections | Cập nhật bản vá còn được vendor hỗ trợ; chạy lại test sau nâng cấp. |
| Copy ví dụ preview hoặc hướng dẫn legacy | Mã có thể thay đổi, bị bỏ hoặc không còn là thông lệ tốt | Đọc tài liệu API/specification phiên bản hiện hành; chọn tính năng chuẩn. |

## 9. Checklist trước khi bắt đầu bài học

- [ ] Tôi chọn **Temurin JDK 25 LTS** hoặc một **JDK LTS đang được hỗ trợ** mà dự án yêu cầu.
- [ ] Tôi đã kiểm tra nguồn tải, đúng hệ điều hành/CPU và đang dùng bản vá còn được cung cấp.
- [ ] `java --version` và `javac --version` cùng cho biết major version mong muốn.
- [ ] IDE, terminal và công cụ build dùng đúng JDK; nếu dự án có target khác, tôi xác định rõ target đó.
- [ ] Chương trình `HelloJdk.java` biên dịch và in chính xác `Java OK`.
- [ ] Tôi chỉ áp dụng kiến thức Java hiện còn hợp lệ; tài liệu cũ về preview hoặc công nghệ đã ngừng được đối chiếu với tài liệu JDK hiện hành.

## Tài liệu chính thức để kiểm chứng và cập nhật

1. [Eclipse Adoptium — Temurin Releases](https://adoptium.net/temurin/releases/): tải gói JDK theo LTS, OS, kiến trúc và bản vá.
2. [Eclipse Adoptium — Installation](https://adoptium.net/installation): cách cài trên Windows, macOS, Linux.
3. [Eclipse Adoptium — Temurin Support](https://adoptium.net/support/): lịch phát hành, chính sách hỗ trợ và các dòng còn được cập nhật.
4. [Oracle — Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): vòng đời các dòng Java và lưu ý điều kiện Oracle JDK.
5. [Oracle JDK 25 — Tài liệu `javac`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): cú pháp biên dịch và tùy chọn `--release`.

**Kết luận thực hành:** không có yêu cầu riêng thì bắt đầu với **Temurin JDK 25 LTS và bản vá mới nhất**; nếu dự án yêu cầu **JDK 21 LTS** thì theo dự án. Kiểm chứng cả `java`, `javac` và chương trình mẫu, đồng thời học theo API/tính năng chuẩn còn được duy trì thay vì sao chép cấu hình thời JDK 15.