# Cài đặt bản cập nhật JDK 21 được nhà cung cấp duy trì

Java 21 là một bản phát hành LTS (Long-Term Support). Khi dự án cần tiếp tục chạy trên Java 21, hãy giữ nguyên major version 21 và cập nhật các bản vá trong nhánh 21.0.x từ một nhà cung cấp còn duy trì bản phân phối đó. Bản cập nhật mới thường chứa bản vá bảo mật, sửa lỗi JVM, thư viện chuẩn và dữ liệu múi giờ; cài JDK mới giúp môi trường phát triển nhận được các sửa lỗi này mà không phải chuyển dự án sang major version khác.

Ngày 16/11/2026, nhánh cập nhật mới nhất đang được các nhà cung cấp công bố là JDK 21.0.13. Ví dụ, Eclipse Temurin công bố bản 21.0.13 vào ngày 30/10/2026 và Amazon Corretto cung cấp bản 21.0.13. Hãy kiểm tra trang phát hành của nhà cung cấp ngay trước khi cài đặt vì số hiệu bản vá và thời điểm phát hành có thể khác nhau giữa các bản phân phối.

## Chọn bản phân phối JDK 21 còn được duy trì

OpenJDK là nền tảng mã nguồn mở chung. Các nhà cung cấp đóng gói, kiểm thử, phát hành và đặt lịch hỗ trợ riêng cho bản phân phối của họ. Vì vậy, nhãn LTS cho biết dòng Java có vòng đời dài hơn, nhưng thời hạn cập nhật và hình thức hỗ trợ vẫn phụ thuộc vào nhà cung cấp.

| Bản phân phối | Tình trạng và thời hạn được công bố | Khi nào nên chọn |
| --- | --- | --- |
| **Eclipse Temurin 21** của Eclipse Adoptium | Dòng LTS; Adoptium công bố thời hạn duy trì ít nhất đến tháng 12/2029. Hỗ trợ cộng đồng; Eclipse không trực tiếp cung cấp hợp đồng SLA thương mại. | Phù hợp cho học tập, phát triển và triển khai khi cần bản dựng OpenJDK miễn phí, phổ biến và có quy trình phát hành công khai. |
| **Amazon Corretto 21** | Dòng LTS; Amazon dự kiến phát hành cập nhật cuối cùng vào tháng 7/2030 và kết thúc hỗ trợ vào tháng 10/2030. Cập nhật theo quý, đồng thời có thể phát hành bản sửa lỗi khẩn cấp ngoài lịch. | Phù hợp khi muốn dùng bản phân phối được AWS duy trì, đặc biệt trong môi trường chạy trên AWS hoặc khi cần lịch hỗ trợ được công bố rõ. |
| **Oracle JDK 21** | Oracle công bố Premier Support đến tháng 9/2028 và Extended Support đến tháng 9/2031. Từ bản 21.0.13 phát hành sau tháng 9/2026, Oracle JDK 21 chuyển sang Oracle Technology Network License Agreement (OTN). | Chọn khi tổ chức đã xác định rõ quyền sử dụng và nhu cầu hỗ trợ của Oracle. Phải đọc điều khoản OTN hoặc dùng quyền hỗ trợ phù hợp trước khi triển khai. |

Nguồn vòng đời: [Adoptium Support](https://adoptium.net/support), [Amazon Corretto FAQs](https://aws.amazon.com/corretto/faqs/) và [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html). Adoptium cung cấp hỗ trợ cộng đồng và hướng dẫn tìm đơn vị hỗ trợ thương mại trên trang [Temurin Support](https://adoptium.net/support). Với Oracle JDK 21.0.13 trở lên, không mặc định rằng điều khoản miễn phí của các bản 21 trước đó vẫn áp dụng cho triển khai thương mại; xem [Oracle Java SE Licensing FAQ](https://www.oracle.com/java/technologies/javase/jdk-faqs.html).

Đối với phần lớn dự án cần một JDK 21 miễn phí, Temurin và Corretto là hai lựa chọn thực tế. Chọn một bản phân phối thống nhất cho máy phát triển, máy build và môi trường chạy để giảm khác biệt giữa các môi trường. Nếu doanh nghiệp yêu cầu SLA, hãy chọn nhà cung cấp có hợp đồng hỗ trợ phù hợp; hỗ trợ cộng đồng không thay thế cam kết phản hồi theo SLA.

## Kiểm tra môi trường trước khi cập nhật

Mở terminal hoặc PowerShell và ghi nhận phiên bản hiện đang được sử dụng:

```bash
java -version
javac -version
```

`java` hiển thị runtime đang được gọi; `javac` xác nhận trình biên dịch của JDK có sẵn. Nếu `javac` không được nhận diện, máy có thể chưa cài JDK hoặc `PATH` chưa trỏ đến thư mục `bin` của JDK.

Kiểm tra đường dẫn thực thi để biết hệ điều hành đang ưu tiên bản cài nào:

```powershell
# Windows PowerShell
where.exe java
$env:JAVA_HOME
```

```bash
# macOS hoặc Linux
command -v java
echo "$JAVA_HOME"
```

Nếu dự án dùng Maven hoặc Gradle, kiểm tra cả JVM mà công cụ build đang chạy:

```bash
mvn -version
./gradlew -version
```

IDE, Maven, Gradle và các script khởi chạy có thể chọn JDK riêng. Vì vậy, kết quả `java -version` trong terminal chưa đủ để kết luận toàn bộ dự án đã chuyển sang JDK mới.

Trước khi tải bộ cài, xác định hệ điều hành và kiến trúc CPU. Chọn đúng gói `x64` (Intel/AMD 64-bit) hoặc `aarch64`/`ARM64` (ARM 64-bit), đúng hệ điều hành và đúng major version 21. Khi phát triển Java, chọn gói **JDK** để có cả `java`, `javac` và các công cụ phát triển.

## Tải và cài đặt JDK 21

Chỉ tải bản phát hành ổn định từ trang chính thức của nhà cung cấp hoặc repository chính thức của họ. Không dùng bản nightly, bản early-access hoặc một bản lưu trữ cũ làm môi trường phát triển thường ngày. Trang tải của [Eclipse Temurin 21](https://adoptium.net/temurin/releases/?version=21) cho phép chọn phiên bản, hệ điều hành, kiến trúc và định dạng gói. [Trang tải Amazon Corretto 21](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/downloads-list.html) cung cấp các gói cài đặt cùng checksum SHA-256 và chữ ký cho những định dạng tương ứng.

### Windows

1. Mở trang tải Temurin 21 hoặc Corretto 21, chọn **JDK**, Windows và kiến trúc CPU của máy. Với Temurin, tải gói `.msi`; với Corretto, tải bộ cài `.msi` dành cho Windows.
2. Đối chiếu SHA-256 của tệp tải về với giá trị do nhà cung cấp công bố. Trong PowerShell, chạy:

   ```powershell
   Get-FileHash .\ten-goi-cai.msi -Algorithm SHA256
   ```

3. Chạy tệp `.msi` và hoàn tất trình cài đặt. Ghi lại thư mục cài đặt JDK 21 vừa tạo.
4. Mở **System Properties → Advanced → Environment Variables**. Tạo hoặc cập nhật biến `JAVA_HOME` trỏ đến thư mục gốc của JDK, ví dụ `C:\Program Files\Eclipse Adoptium\<thu-muc-jdk-21>`; thêm `%JAVA_HOME%\bin` vào `Path` và đặt mục này trước các đường dẫn Java cũ.
5. Mở một cửa sổ terminal mới để kiểm tra biến môi trường đã được nạp.

Nếu cài Amazon Corretto bằng MSI, tài liệu AWS cũng yêu cầu đặt `JAVA_HOME` đến thư mục cài đặt của phiên bản hiện tại và thêm `%JAVA_HOME%\bin` vào `PATH`. Tham khảo [hướng dẫn cài Corretto 21 trên Windows](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/windows-install.html).

### macOS

1. Tải gói `.pkg` của Temurin 21 hoặc Corretto 21. Chọn đúng kiến trúc Intel (`x64`) hoặc Apple Silicon (`aarch64`).
2. Kiểm tra checksum SHA-256 nếu trang tải cung cấp giá trị này. Có thể tính checksum bằng:

   ```bash
   shasum -a 256 ten-goi-cai.pkg
   ```

3. Mở tệp `.pkg` và làm theo trình cài đặt. Sau khi cài, liệt kê các JDK mà macOS nhận diện:

   ```bash
   /usr/libexec/java_home -V
   ```

4. Chọn JDK 21 cho terminal hiện tại:

   ```bash
   export JAVA_HOME=$(/usr/libexec/java_home -v 21)
   export PATH="$JAVA_HOME/bin:$PATH"
   ```

   Để áp dụng cho các phiên terminal tiếp theo, thêm hai dòng `export` vào file cấu hình shell đang dùng, thường là `~/.zshrc` với zsh hoặc `~/.bash_profile` với bash, rồi mở terminal mới.

AWS mô tả vị trí cài Corretto 21 trong `/Library/Java/JavaVirtualMachines/` và cách chọn `JAVA_HOME` trong [hướng dẫn cài Corretto trên macOS](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/macos-install.html). Lệnh `java_home -v 21` giúp chọn JDK 21 mà macOS nhận diện thay vì phải tự ghi một thư mục có số bản vá cụ thể.

### Debian hoặc Ubuntu Linux

Ví dụ dưới đây cài Amazon Corretto 21 từ repository chính thức của AWS. Thao tác thêm khóa và repository một lần trên máy:

```bash
wget -O - https://apt.corretto.aws/corretto.key \
  | sudo gpg --dearmor -o /usr/share/keyrings/corretto-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/corretto-keyring.gpg] https://apt.corretto.aws stable main" \
  | sudo tee /etc/apt/sources.list.d/corretto.list
```

Cập nhật danh sách gói và cài JDK 21:

```bash
sudo apt-get update
sudo apt-get install -y java-21-amazon-corretto-jdk
```

Nếu đã cài gói này và chỉ muốn lấy bản vá mới nhất trong nhánh 21, chạy:

```bash
sudo apt-get update
sudo apt-get install --only-upgrade java-21-amazon-corretto-jdk
```

### Linux dùng RPM (Amazon Linux, RHEL hoặc hệ tương thích)

Thêm khóa và repository Corretto chính thức:

```bash
sudo rpm --import https://yum.corretto.aws/corretto.key
sudo curl -L -o /etc/yum.repos.d/corretto.repo https://yum.corretto.aws/corretto.repo
```

Cài JDK 21:

```bash
sudo yum install -y java-21-amazon-corretto-devel
```

Khi cần cập nhật bản vá cho gói đã cài:

```bash
sudo yum update java-21-amazon-corretto-devel
```

Trên hệ dùng `dnf`, có thể thay lệnh `yum` tương ứng bằng `dnf`. Tên gói và hướng dẫn theo từng bản phân phối được duy trì trong tài liệu [cài Corretto 21 trên Linux](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/generic-linux-install.html). Nếu chọn Temurin, hãy làm theo hướng dẫn repository chính thức tại [Adoptium Linux installation](https://adoptium.net/installation/linux/) và cài gói `temurin-21-jdk`.

## Chọn JDK 21 làm phiên bản đang hoạt động

Có thể cài nhiều major version Java trên cùng một máy. Sau khi cài bản cập nhật, cần bảo đảm `JAVA_HOME` và `PATH` cùng trỏ đến JDK 21 mong muốn.

- **Windows:** `JAVA_HOME` phải trỏ đến thư mục gốc của JDK 21; mục `%JAVA_HOME%\bin` nên đứng trước đường dẫn Java cũ trong `Path`. Cập nhật đường dẫn nếu thư mục cài đặt thay đổi sau khi nâng cấp.
- **macOS:** dùng `export JAVA_HOME=$(/usr/libexec/java_home -v 21)` để chọn một JDK 21 đã cài. Đặt `$JAVA_HOME/bin` ở đầu `PATH`.
- **Debian/Ubuntu:** nếu nhiều JDK cùng tồn tại, chọn runtime và compiler bằng `sudo update-alternatives --config java` và `sudo update-alternatives --config javac`.
- **RPM-based Linux:** trên hệ dùng alternatives, chọn lần lượt `java` và `javac` bằng `sudo alternatives --config java` và `sudo alternatives --config javac`.

Không chỉ kiểm tra `java`. Một số dự án gọi trực tiếp `javac`, Maven hoặc Gradle; các công cụ này cũng phải sử dụng cùng JDK 21. Trong IDE, kiểm tra **Project SDK/JDK**, JVM chạy Gradle và JDK của Maven runner nếu có cấu hình riêng.

## Xác minh sau khi cài đặt hoặc cập nhật

Đóng và mở lại terminal, sau đó chạy:

```bash
java -version
javac -version
```

Kết quả phải cho biết major version `21` và patch version đang được cài, ví dụ `21.0.13`. Chuỗi thông tin cũng nên nhận diện đúng nhà cung cấp mà bạn đã chọn, chẳng hạn `Temurin` hoặc `Corretto`. Nếu `java` hiển thị 21 nhưng `javac` không tồn tại hoặc hiển thị major version khác, hãy kiểm tra lại `JAVA_HOME` và thứ tự `PATH`.

Tiếp tục xác minh công cụ build:

```bash
mvn -version
./gradlew -version
```

Kiểm tra dòng JVM trong kết quả. Sau đó chạy build và các bài kiểm thử của dự án. Nếu terminal dùng JDK 21 nhưng build vẫn dùng phiên bản khác, kiểm tra cấu hình JDK của IDE, Maven toolchain hoặc Gradle Java toolchain. Khởi động lại terminal, IDE hoặc tiến trình build nền sau khi đổi biến môi trường để chúng nhận cấu hình mới.

Giữ bản JDK cũ trong thời gian xác minh ứng dụng và các dịch vụ phụ thuộc. Chỉ gỡ bản cũ sau khi xác nhận không còn công cụ hoặc ứng dụng nào cần nó.

## Duy trì các bản cập nhật JDK 21

Các bản cập nhật bảo trì OpenJDK thường được phát hành theo chu kỳ hàng quý, thường rơi vào tháng 1, 4, 7 và 10. Adoptium công bố lịch phát hành theo chu kỳ này; Corretto cũng lên kế hoạch cập nhật hàng quý và có thể phát hành bản sửa lỗi khẩn cấp ngoài lịch. Theo dõi trang phát hành và lịch hỗ trợ của chính nhà cung cấp thay vì chỉ kiểm tra một lần khi cài đặt.

Quy trình cập nhật định kỳ nên gồm các bước sau:

1. Kiểm tra trang phát hành hoặc repository chính thức để xác định bản vá JDK 21 mới nhất và tình trạng hỗ trợ của nhà cung cấp.
2. Cập nhật gói JDK 21 qua repository/package manager đã cấu hình hoặc tải bộ cài mới từ trang chính thức. Giữ major version 21 nếu dự án vẫn yêu cầu Java 21.
3. Kiểm tra checksum hoặc chữ ký số theo thông tin nhà cung cấp công bố trước khi cài gói tải thủ công.
4. Cập nhật `JAVA_HOME` nếu đường dẫn cài đặt thay đổi; kiểm tra lại `PATH`, IDE và công cụ build.
5. Chạy `java -version`, `javac -version`, build và test của dự án. Ghi nhận phiên bản JDK đã xác minh trong tài liệu môi trường hoặc pipeline CI.
6. Theo dõi thời hạn hỗ trợ của nhà cung cấp và lên kế hoạch chuyển sang một LTS còn được duy trì trước khi dòng JDK 21 kết thúc hỗ trợ.

Khi cấu hình CI, chỉ định rõ phân phối và major version, ví dụ Temurin 21 hoặc Corretto 21. Nếu yêu cầu build có thể tái lập tuyệt đối, ghi nhận cả số hiệu bản vá/build đã kiểm thử và chủ động cập nhật nó theo lịch. Nếu chỉ khóa major version, cấu hình pipeline làm mới JDK theo lịch cập nhật để tiếp nhận các bản vá bảo mật trong nhánh 21.

## Xử lý một số lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| `java -version` vẫn hiển thị Java 17 hoặc một phiên bản cũ | `PATH` ưu tiên thư mục Java cũ hoặc terminal chưa nạp biến môi trường mới. | Kiểm tra `where.exe java` trên Windows hoặc `command -v java` trên macOS/Linux; đưa `%JAVA_HOME%\bin` hoặc `$JAVA_HOME/bin` của JDK 21 lên trước. Mở terminal mới. |
| `java` chạy được nhưng `javac` không tồn tại | Máy chỉ có runtime hoặc `PATH` không chứa thư mục `bin` của JDK. | Cài đúng gói JDK và kiểm tra `JAVA_HOME` trỏ đến thư mục gốc của JDK 21. |
| `java` và `javac` hiển thị hai phiên bản khác nhau | Hai lệnh được phân giải từ các đường dẫn khác nhau hoặc cấu hình alternatives chưa đồng bộ. | Kiểm tra đường dẫn của cả hai lệnh; chọn lại `java` và `javac` bằng công cụ alternatives trên Linux. |
| Terminal dùng Java 21 nhưng IDE/build dùng phiên bản khác | IDE, Maven runner, Gradle JVM hoặc toolchain có cấu hình JDK riêng. | Chọn JDK 21 trong cấu hình dự án và công cụ build; chạy lại `mvn -version` hoặc `./gradlew -version`. |
| Bộ cài không chạy hoặc báo sai kiến trúc | Tải nhầm gói x64 cho máy ARM64 hoặc ngược lại, hoặc chọn sai hệ điều hành. | Kiểm tra kiến trúc máy và tải lại gói tương ứng từ trang nhà cung cấp. |
| Checksum hoặc chữ ký không khớp | Tệp tải bị hỏng, tải sai nguồn hoặc nội dung không trùng với bản phát hành được công bố. | Không cài tệp đó. Tải lại từ nguồn chính thức và xác minh lại checksum/chữ ký. |

## Tài liệu chính thức

- [Eclipse Temurin 21 — bản phát hành và bộ cài](https://adoptium.net/temurin/releases/?version=21)
- [Adoptium — lịch phát hành và thời hạn hỗ trợ](https://adoptium.net/support)
- [Adoptium — hướng dẫn cài đặt theo hệ điều hành](https://adoptium.net/installation)
- [Adoptium — cài Temurin trên Linux](https://adoptium.net/installation/linux/)
- [Amazon Corretto — lịch hỗ trợ](https://aws.amazon.com/corretto/faqs/)
- [Amazon Corretto 21 — bộ tải, checksum và chữ ký](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/downloads-list.html)
- [Amazon Corretto 21 — cài đặt trên Windows](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/windows-install.html)
- [Amazon Corretto 21 — cài đặt trên macOS](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/macos-install.html)
- [Amazon Corretto 21 — cài đặt trên Linux](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/generic-linux-install.html)
- [Oracle — Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [Oracle — Java SE Licensing FAQ](https://www.oracle.com/java/technologies/javase/jdk-faqs.html)
