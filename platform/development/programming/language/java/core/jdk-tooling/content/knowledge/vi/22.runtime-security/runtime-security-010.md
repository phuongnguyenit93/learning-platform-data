# Cập nhật bản vá JDK

## 1. Cập nhật bản vá JDK là gì?

Cập nhật bản vá JDK là quá trình đưa một bản JDK đang sử dụng lên bản cập nhật mới hơn trong cùng dòng phiên bản hoặc sang bản phát hành phù hợp đã được nhà cung cấp hỗ trợ. Mục tiêu thường là khắc phục lỗ hổng bảo mật, sửa lỗi runtime, cải thiện độ ổn định và duy trì khả năng tương thích.

JDK (Java Development Kit) bao gồm compiler, công cụ phát triển và môi trường chạy Java. Vì vậy, một bản vá JDK có thể ảnh hưởng tới:

- Ứng dụng Java đang chạy trên JVM.
- Build agent và máy dùng javac, javadoc, jlink hoặc jshell.
- Máy chủ ứng dụng, dịch vụ nền và batch job.
- Container hoặc ứng dụng đóng gói kèm runtime riêng.
- Công cụ CI/CD, IDE và môi trường kiểm thử.

Ứng dụng có thể không thay đổi mã nguồn nhưng vẫn cần bản vá vì lỗ hổng nằm trong JVM, thư viện nền tảng, bộ xử lý TLS, parser, công cụ hoặc thành phần khác được đóng gói cùng JDK.

Một bản vá chỉ có hiệu lực với tiến trình JVM được khởi chạy từ runtime đã cập nhật. Cài JDK mới trên máy không tự động thay đổi JVM đang chạy hoặc bảo đảm mọi service đã chuyển sang bản mới.

## 2. Phân biệt update, patch và nâng cấp feature release

Java dùng cách đánh số phiên bản theo thời gian. Theo JEP 322, các thành phần chính của version string có ý nghĩa:

| Thành phần | Ý nghĩa |
|---|---|
| FEATURE | Dòng phát hành tính năng, ví dụ 17, 21 hoặc 25 |
| INTERIM | Bản phát hành trung gian tương thích |
| UPDATE | Bản cập nhật tương thích, có thể chứa sửa lỗi bảo mật, hồi quy và lỗi khác |
| PATCH | Bản vá khẩn cấp được phát hành khi cần xử lý vấn đề nghiêm trọng |

Ví dụ version string 21.0.4 có feature release là 21, interim là 0 và update counter là 4. Số build và phần hậu tố có thể bổ sung thông tin về nhà cung cấp hoặc bản build cụ thể.

Cần phân biệt ba loại thay đổi:

- **Update trong cùng feature release:** ví dụ cập nhật từ một bản 21.0.x cũ lên bản 21.0.x mới hơn. Đây thường là lựa chọn có rủi ro tương thích thấp hơn khi mục tiêu là vá bảo mật.
- **Emergency patch:** bản vá ngoài nhịp thông thường khi có vấn đề nghiêm trọng cần xử lý khẩn cấp.
- **Feature upgrade:** chuyển từ dòng Java 17 sang 21 hoặc 25. Đây là thay đổi lớn hơn, có thể liên quan tới API, hành vi, công cụ build, thư viện và chính sách hỗ trợ.

Một bản update tương thích vẫn có thể làm thay đổi hành vi bảo mật, thuật toán mật mã, bộ chứng thư tin cậy hoặc cách xử lý giao thức. Vì vậy, update cùng feature release vẫn cần kiểm thử.

Tham khảo: [JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322).

## 3. Vì sao phải cập nhật bản vá JDK?

JDK cũ có thể chứa lỗ hổng cho phép kẻ tấn công gây từ chối dịch vụ, vượt qua kiểm soát bảo mật, đọc hoặc sửa dữ liệu, hoặc khai thác thành phần nền tảng khi ứng dụng xử lý dữ liệu không tin cậy.

Các lý do cần duy trì bản vá:

- **Khắc phục CVE:** cập nhật sửa các lỗ hổng đã được nhà cung cấp xác định.
- **Giảm nguy cơ khai thác:** bản vá loại bỏ hoặc giảm khả năng khai thác trên runtime bị ảnh hưởng.
- **Duy trì hỗ trợ:** nhà cung cấp có thể ngừng hỗ trợ các bản update cũ trong một dòng feature release.
- **Sửa lỗi runtime:** một update có thể sửa lỗi JVM, garbage collector, class loading, TLS hoặc thư viện nền tảng.
- **Duy trì tương thích:** các bản sửa mới có thể cải thiện khả năng hoạt động với hệ điều hành, chứng thư và phần mềm hiện hành.
- **Đáp ứng kiểm toán:** tổ chức có thể cần chứng minh runtime đang ở mức bản vá được phê duyệt.

Không nên chờ tới khi ứng dụng có lỗi mới cập nhật. Lỗ hổng có thể bị khai thác trước khi xuất hiện triệu chứng rõ ràng trong log.

## 4. Các kênh phát hành bản vá bảo mật

Nhịp phát hành phụ thuộc nhà cung cấp JDK. Oracle, các bản build OpenJDK của nhà cung cấp Linux, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK và các nhà cung cấp khác có quy trình đóng gói, hỗ trợ và thông báo riêng.

Với Oracle Java SE, các kênh bảo mật chính gồm:

| Kênh | Mục đích |
|---|---|
| Critical Patch Update (CPU) | Bản cập nhật bảo mật định kỳ, thường chứa tập hợp bản sửa cho nhiều lỗ hổng |
| Critical Security Patch Update (CSPU) | Bản sửa có mục tiêu cho lỗ hổng ưu tiên cao giữa các CPU |
| Security Alert | Thông báo và bản sửa ngoài lịch khi vấn đề quá nghiêm trọng để chờ đợt cập nhật kế tiếp |

Oracle mô tả CPU là bản cập nhật thường mang tính tích lũy. CSPU bổ sung các bản sửa ưu tiên cao giữa các CPU; CPU tiếp theo có thể bao gồm các bản sửa đã phát hành trong CSPU trước đó. Security Alert được dùng khi cần xử lý vấn đề không thể chờ lịch phát hành thường lệ.

Tại thời điểm biên soạn **10-11-2026**, trang Oracle Security Alerts liệt kê CPU tháng 10-2026 (Rev 3, cập nhật ngày 4-11-2026) và CSPU kế tiếp dự kiến ngày 17-11-2026. Lịch và chính sách có thể thay đổi; luôn kiểm tra thông báo hiện hành trước khi lập lịch bảo trì.

Các mốc CPU và CSPU nói trên là lịch của Oracle, không phải cam kết lịch chung cho mọi bản phân phối OpenJDK. Với bản JDK khác, hãy theo dõi advisory và lịch cập nhật của chính nhà cung cấp đó.

Nguồn chính thức:

- [Oracle Critical Patch Updates, Critical Security Patch Updates and Security Alerts](https://www.oracle.com/security-alerts/)
- [Oracle Security Fixing Policies](https://www.oracle.com/corporate/security-practices/assurance/vulnerability/security-fixing/)

## 5. Đọc security advisory trước khi chọn bản vá

Khi có thông báo bảo mật, không nên chỉ nhìn số phiên bản mới nhất rồi cài ngay. Trước tiên, đọc advisory của nhà cung cấp để xác định hệ thống có bị ảnh hưởng hay không.

Những thông tin cần kiểm tra:

1. **CVE ID:** mã định danh lỗ hổng để tra cứu và đối chiếu với công cụ quản lý lỗ hổng.
2. **Affected versions:** những dòng JDK, bản update và nền tảng bị ảnh hưởng.
3. **Fixed versions:** phiên bản đầu tiên đã có bản sửa cho từng dòng được hỗ trợ.
4. **Severity/CVSS:** mức độ nghiêm trọng được công bố; không dùng điểm số đơn lẻ để thay thế đánh giá rủi ro thực tế.
5. **Attack vector và điều kiện khai thác:** lỗ hổng có thể bị khai thác từ xa, qua mạng nội bộ, qua dữ liệu đầu vào hay chỉ trong điều kiện đặc biệt.
6. **Exploit status:** có bằng chứng khai thác thực tế hoặc cảnh báo khẩn cấp hay không.
7. **Workaround:** biện pháp giảm thiểu tạm thời nếu chưa thể cập nhật ngay.
8. **Vendor-specific guidance:** yêu cầu cài đặt, giới hạn nền tảng, giấy phép và điều kiện hỗ trợ.

Ưu tiên xử lý dựa trên mức độ ảnh hưởng tới hệ thống thực tế. Một runtime công khai trên Internet, xử lý dữ liệu không tin cậy hoặc chạy workload quan trọng có thể cần được vá trước một máy phát triển ít phơi nhiễm hơn.

Không giả định mọi JDK có cùng số phiên bản đều nhận cùng một bản sửa trong cùng ngày. Hãy dùng bảng affected/fixed version của nhà cung cấp build đang cài.

## 6. Kiểm kê JDK và runtime đang được sử dụng

Trước khi cập nhật, cần xác định chính xác JDK nào đang tồn tại và tiến trình nào đang dùng chúng. Một máy có thể cài nhiều bản JDK, trong khi service, IDE hoặc script gọi một đường dẫn Java khác với đường dẫn mặc định của terminal.

Phạm vi kiểm kê nên gồm:

- Máy chủ production, staging và development.
- Máy build, CI runner và agent triển khai.
- Máy tính của lập trình viên và máy kiểm thử.
- Application server, scheduler, worker và service nền.
- Container image, Kubernetes workload và job ngắn hạn.
- Runtime được đóng gói cùng ứng dụng hoặc công cụ của bên thứ ba.

Ghi lại tối thiểu: hostname hoặc workload, môi trường, nhà cung cấp, feature release, version/update, kiến trúc, đường dẫn cài đặt, tiến trình sử dụng, chủ sở hữu và trạng thái hỗ trợ.

### 6.1. Kiểm tra phiên bản mặc định

Trên mọi hệ điều hành:

```bash
java -version
javac -version
```

java -version cho biết runtime mà lệnh java hiện tại tìm thấy; javac -version cho biết compiler được tìm thấy. Hai lệnh có thể trỏ tới hai bản JDK khác nhau nếu PATH được cấu hình không nhất quán.

### 6.2. Tìm đường dẫn executable trên Windows

PowerShell:

```powershell
Get-Command java -All
Get-Command javac -All
$env:JAVA_HOME
```

Có thể kiểm tra thêm:

```powershell
where.exe java
where.exe javac
```

Nếu có nhiều kết quả, xem thứ tự PATH và xác định file nào được gọi trước.

### 6.3. Tìm đường dẫn executable trên Linux/macOS

```bash
command -v java
command -v javac
echo "$JAVA_HOME"
readlink -f "$(command -v java)"
```

Trên macOS, cách phân giải symbolic link và vị trí bundle có thể khác Linux; dùng công cụ hệ thống hoặc hướng dẫn của nhà cung cấp để xác định đường dẫn JDK thực tế.

### 6.4. Kiểm tra thuộc tính runtime

Có thể xem một số system property:

```bash
java -XshowSettings:properties -version
```

Chú ý các thuộc tính như java.version, java.runtime.version, java.vendor và java.home. Chúng giúp phân biệt phiên bản, nhà cung cấp và thư mục runtime mà lệnh đang sử dụng.

## 7. Xác định phiên bản của JVM đang chạy

java -version chỉ kiểm tra executable được shell gọi tại thời điểm kiểm tra. Nó không chứng minh một service đã chạy lâu từ trước đang sử dụng JDK mới.

Dùng jcmd để liệt kê JVM trên cùng máy:

```bash
jcmd -l
```

Lệnh trả về process ID, main class và các đối số khởi chạy có thể quan sát được. Sau khi xác định PID của service, xem phiên bản JVM:

```bash
jcmd <PID> VM.version
```

Có thể kiểm tra command line của tiến trình:

```bash
jcmd <PID> VM.command_line
```

jcmd phải chạy trên cùng máy và với effective user/group phù hợp với tiến trình JVM. Danh sách jcmd -l không hiển thị đầy đủ các JVM chạy trong container riêng từ môi trường host; trong trường hợp đó, hãy kiểm tra từ bên trong container hoặc dùng công cụ quản lý container để xác định PID.

Sau khi đổi JAVA_HOME, một tiến trình đang chạy không tự chuyển sang JVM mới. Cần khởi động lại service theo quy trình vận hành rồi kiểm tra lại phiên bản của PID mới.

Tài liệu: [The jcmd Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).

## 8. Chọn đúng bản vá cho hệ thống

Khi chọn bản cài, đối chiếu tất cả điều kiện sau:

- **Nhà cung cấp:** dùng bản build đã được tổ chức phê duyệt và có kênh cập nhật rõ ràng.
- **Feature release:** chọn bản update mới nhất được hỗ trợ trong dòng ứng dụng đang sử dụng, trừ khi kế hoạch đã cho phép nâng feature release.
- **Hệ điều hành:** đúng Windows, Linux hoặc macOS và đúng phiên bản hệ điều hành được hỗ trợ.
- **Kiến trúc:** đúng x64, AArch64/ARM64 hoặc kiến trúc mục tiêu khác.
- **Gói cài:** JDK đầy đủ hay runtime image rút gọn tùy workload.
- **Điều khoản hỗ trợ:** kiểm tra license, support entitlement và nguồn tải của nhà cung cấp.
- **Tính toàn vẹn:** tải từ website, repository hoặc package repository chính thức; xác minh checksum hoặc chữ ký theo hướng dẫn.

Không lấy một JDK từ website không rõ nguồn, không đổi vendor chỉ vì số phiên bản trông mới hơn và không ghép các thư mục nội bộ của hai bản phân phối khác nhau.

Nếu ứng dụng còn phụ thuộc Java 17, hãy ưu tiên bản vá mới nhất được hỗ trợ của dòng 17 trong kế hoạch vá. Nâng lên Java 21 hoặc 25 là một dự án feature upgrade riêng, cần đánh giá tương thích và kiểm thử sâu hơn.

## 9. Chuẩn bị trước khi cài bản vá

Trước cửa sổ bảo trì, lập kế hoạch thay đổi và ghi nhận trạng thái hiện tại.

Checklist chuẩn bị:

- Xác định service, batch job, build agent và workload bị ảnh hưởng.
- Ghi lại phiên bản JDK, vendor, đường dẫn và tham số JVM hiện tại.
- Xác định service owner, thời gian bảo trì và người phê duyệt.
- Đọc release notes, security advisory và known issues của bản đích.
- Kiểm tra dung lượng ổ đĩa, quyền cài đặt và yêu cầu restart.
- Lưu cấu hình tùy chỉnh trong conf/, truststore, keystore, security policy và cấu hình service.
- Lưu giá trị JAVA_HOME, PATH, symbolic link, biến môi trường và đường dẫn Java trong script.
- Lưu container image tag/digest, manifest triển khai và cấu hình build.
- Chuẩn bị bản cài trước đó hoặc image đã biết hoạt động tốt theo chính sách rollback.
- Xác định test chức năng, TLS, database, native library và hiệu năng cần chạy sau cập nhật.

Không sao chép đè toàn bộ thư mục lib hoặc các thư mục triển khai nội bộ từ JDK cũ sang JDK mới. Đây là chi tiết triển khai của runtime; việc trộn chúng có thể làm hỏng cài đặt hoặc đưa mã cũ trở lại bản vá mới.

Với cấu hình tùy chỉnh, hãy so sánh từng file và áp dụng lại những thay đổi còn cần thiết. Không thay toàn bộ thư mục conf mới bằng thư mục cũ mà chưa review.

## 10. Cài đặt bản vá trên Linux

Cách cài phụ thuộc nhà cung cấp và phương thức triển khai: package manager của hệ điều hành, gói .deb/.rpm, archive hoặc installer chính thức.

Nếu JDK được quản lý bằng package repository của Debian/Ubuntu, một ví dụ cập nhật package đã cài là:

```bash
sudo apt-get update
sudo apt-get install --only-upgrade openjdk-21-jdk
```

Trên hệ thống dùng DNF, tên package có thể có dạng:

```bash
sudo dnf upgrade java-21-openjdk-devel
```

Đây là ví dụ theo tên package phổ biến; tên chính xác và bản update khả dụng phụ thuộc repository, phiên bản hệ điều hành và chính sách của nhà cung cấp. Kiểm tra package nguồn trước khi chạy trong production.

Nếu cài từ archive hoặc installer của vendor:

1. Tải đúng gói cho hệ điều hành và kiến trúc.
2. Xác minh checksum/chữ ký.
3. Đọc hướng dẫn cài đặt của phiên bản đó.
4. Dừng các JVM nếu hướng dẫn yêu cầu thay thế thư mục đang dùng.
5. Cài vào vị trí được quản lý theo chính sách của tổ chức.
6. Cập nhật symbolic link, alternatives hoặc JAVA_HOME theo cách quản lý của hệ thống.
7. Khởi động lại service và kiểm tra tiến trình thực tế.

Không mặc định mọi installer Linux đều cài side-by-side. Một số gói thay thế bản cũ trong cùng feature line; một số archive hoặc vendor installer tạo thư mục versioned riêng. Hãy kiểm tra hành vi của đúng gói đang sử dụng.

## 11. Cài đặt bản vá trên Windows

Trên Windows, thường dùng installer .exe hoặc .msi do nhà cung cấp phát hành.

Quy trình tổng quát:

1. Tải installer đúng vendor, phiên bản, kiến trúc và loại gói.
2. Xác minh publisher/chữ ký số và checksum theo hướng dẫn.
3. Đọc hướng dẫn của installer về nâng cấp cùng feature release.
4. Dừng service Java trước khi thay thế thư mục JDK mà service đang sử dụng.
5. Chạy installer với quyền quản trị nếu được yêu cầu.
6. Cập nhật JAVA_HOME, PATH và cấu hình service nếu đường dẫn runtime thay đổi.
7. Mở terminal mới để tránh dùng biến môi trường cũ.
8. Kiểm tra java -version, javac -version và đường dẫn executable.

Ví dụ kiểm tra sau cài đặt trong PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
java -version
javac -version
```

Ví dụ cấu hình cho phiên PowerShell hiện tại:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
```

Đây chỉ thay đổi môi trường của cửa sổ PowerShell hiện tại. Cấu hình lâu dài cho user, máy hoặc Windows service cần được cập nhật tại đúng nơi quản lý biến môi trường/service.

Hành vi installer thay đổi theo vendor và phiên bản. Ví dụ, một số bản cài Oracle JDK 24 thay thế bản cùng feature release, trong khi hướng dẫn Oracle JDK 25 mô tả thư mục versioned và junction latest. Không áp dụng quy tắc của một installer cho mọi bản JDK.

Tài liệu tham khảo: [Oracle JDK Installation Guide — Windows](https://docs.oracle.com/en/java/javase/25/install/installation-jdk-microsoft-windows-platforms.html).

## 12. Cập nhật JAVA_HOME và cấu hình service

Một lỗi thường gặp là đã cài JDK mới nhưng service vẫn dùng đường dẫn cũ được ghi trực tiếp trong cấu hình.

Các vị trí cần kiểm tra:

- JAVA_HOME ở cấp user hoặc system.
- PATH của user, system hoặc service account.
- Đường dẫn Java trong Windows service wrapper.
- ExecStart và Environment trong systemd unit.
- Script khởi động ứng dụng và file cấu hình scheduler.
- Cấu hình runtime trong application server.
- Build tool daemon hoặc IDE đang giữ JDK riêng.
- Biến môi trường và command trong container entrypoint.

Trên Linux, một phiên shell có thể trỏ tới JDK mới bằng:

```bash
export JAVA_HOME=/opt/jdk/current
export PATH="$JAVA_HOME/bin:$PATH"
java -version
```

Đường dẫn /opt/jdk/current chỉ là ví dụ. Dùng đường dẫn thật do tổ chức quản lý.

Với systemd, cập nhật unit hoặc environment file theo chuẩn của hệ thống rồi reload cấu hình và restart service theo quy trình vận hành. Không chỉ thay biến trong terminal quản trị rồi kết luận service đã chuyển runtime.

Với Windows service, kiểm tra cấu hình executable hoặc Java home trong service wrapper. Restart service sau thay đổi và xác nhận PID mới.

## 13. Cập nhật JDK trong container và runtime đóng gói kèm ứng dụng

Một số ứng dụng không dùng JDK được cài trên host. Chúng mang theo runtime riêng trong image hoặc thư mục triển khai. Trong trường hợp này, cập nhật host JDK không vá runtime đã đóng gói.

Với Docker hoặc container image:

1. Xác định base image và digest đang dùng.
2. Kiểm tra nhà cung cấp image và phiên bản JDK bên trong image.
3. Chọn base image đã được cập nhật từ vendor đáng tin cậy.
4. Cập nhật Dockerfile hoặc build manifest.
5. Build lại image và ghi nhận digest mới.
6. Chạy test trong image mới.
7. Triển khai image mới qua staging/canary rồi rollout.
8. Kiểm tra runtime bên trong container sau khi chạy.

Không nên chỉ vào container đang chạy rồi cập nhật thủ công package bên trong. Thay đổi đó thường không được ghi lại trong image build và sẽ mất khi container được tạo lại.

Với runtime image tạo bằng jlink, cần tạo lại image từ module/JDK đã vá. Kiểm tra pipeline tạo runtime image và đảm bảo đầu vào JMOD/module path đến từ bản JDK mới.

Với ứng dụng đóng gói kèm JRE/JDK hoặc native installer, phải cập nhật artifact đóng gói và phát hành lại ứng dụng. Cập nhật máy chủ mà không cập nhật runtime đi kèm sẽ để lại bản Java cũ.

## 14. Kiểm tra sau khi cài bản vá

Sau cài đặt, cần xác nhận cả executable, compiler và tiến trình đang chạy.

### 14.1. Xác nhận phiên bản và vendor

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Đối chiếu java.version, java.runtime.version, java.vendor và java.home với phiên bản đích trong change record.

### 14.2. Xác nhận tiến trình mới dùng JVM đã vá

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
```

Chạy kiểm tra sau khi service được restart. Nếu tiến trình cũ vẫn tồn tại, nó có thể tiếp tục chạy trên runtime cũ dù lệnh java -version đã hiển thị bản mới.

### 14.3. Kiểm tra cấu hình và thư viện bảo mật

Đối chiếu những thành phần có thể bị ảnh hưởng:

- TLS protocol và cipher suite.
- Truststore, CA certificate và chứng thư doanh nghiệp.
- java.security và security provider.
- Chính sách thuật toán bị vô hiệu hóa.
- Keystore, chữ ký số và xác thực.
- Native library và JNI.
- Cấu hình proxy, DNS và kết nối database.

Một bản vá có thể thay đổi thuật toán hoặc chứng thư được tin cậy. Nếu ứng dụng kết nối hệ thống cũ, kiểm tra tương thích TLS và certificate chain thay vì tự động nới lỏng chính sách bảo mật để làm test chạy qua.

## 15. Kiểm thử ứng dụng sau cập nhật

Bản vá JDK thường hướng tới tính tương thích, nhưng vẫn cần test theo rủi ro của workload.

Một bộ kiểm thử sau cập nhật có thể gồm:

| Nhóm kiểm thử | Nội dung |
|---|---|
| Startup | Service khởi động, load class và đọc cấu hình thành công |
| Functional | Các luồng nghiệp vụ chính hoạt động đúng |
| Integration | Kết nối database, message broker, HTTP API và dịch vụ ngoài |
| TLS/security | Handshake, certificate, cipher suite, chữ ký và xác thực |
| Persistence | Đọc/ghi dữ liệu, serialization và tương thích định dạng |
| Native | JNI/JNA, thư viện native và kiến trúc CPU |
| Performance | Startup time, throughput, latency, GC và memory |
| Operations | Log, metrics, health check, shutdown và restart |
| Build | Compiler, test runner, annotation processor và plugin build |

Chạy test trên đúng phiên bản JDK, hệ điều hành, kiến trúc và cấu hình JVM dự kiến triển khai. Kiểm tra cả workload dài hạn và job chạy theo lịch.

Nếu ứng dụng sử dụng reflection, custom security provider, TLS cũ, thư viện native hoặc framework phụ thuộc chi tiết JVM, hãy bổ sung test tương ứng.

## 16. Triển khai theo từng giai đoạn

Với hệ thống nhiều instance, tránh cập nhật tất cả node cùng lúc nếu kiến trúc cho phép rollout dần.

Một quy trình rollout thường dùng:

1. **Lab:** cài bản vá trên môi trường thử nghiệm và chạy smoke test.
2. **Staging:** chạy test tích hợp với cấu hình gần production.
3. **Canary:** triển khai lên một instance hoặc một nhóm nhỏ.
4. **Observe:** theo dõi lỗi, log, latency, throughput, GC, memory và kết nối.
5. **Expand:** mở rộng theo từng nhóm instance nếu chỉ số ổn định.
6. **Complete:** xác nhận toàn bộ workload đã chạy bản vá mục tiêu.
7. **Audit:** lưu version, vendor, build, image digest và thời điểm hoàn tất.

Nếu phát hiện lỗi hồi quy, dừng rollout và xác định phạm vi ảnh hưởng trước khi tiếp tục. Ghi lại chính xác instance nào đã cập nhật và instance nào còn chạy bản cũ để tránh trạng thái hỗn hợp kéo dài.

Với ứng dụng stateful hoặc cluster, kiểm tra tương thích giữa các node trong thời gian rollout, đặc biệt khi có giao thức trao đổi, serialization hoặc native dependency.

## 17. Rollback khi bản vá gây hồi quy

Rollback là phương án phục hồi dịch vụ khi bản cập nhật gây lỗi nghiêm trọng và chưa có bản sửa thay thế. Nó không làm mất đi rủi ro bảo mật của bản JDK cũ.

Trước khi rollback:

- Xác định lỗi có liên quan trực tiếp tới JDK update hay không.
- Ghi nhận phiên bản đã triển khai và các instance bị ảnh hưởng.
- Kiểm tra bản runtime/image trước đó có còn được phép sử dụng hay không.
- Đánh giá lỗ hổng bảo mật mà bản cũ còn mắc phải.
- Có phê duyệt và thời hạn khắc phục nếu phải quay lại bản dễ bị tổn thương.

Các phương án phục hồi:

- Trỏ JAVA_HOME hoặc symbolic link về bản đã lưu nếu mô hình cài đặt hỗ trợ.
- Triển khai lại package hoặc artifact đã được lưu trữ.
- Rollback container image về digest trước đó theo quy trình quản lý image.
- Khôi phục cấu hình service và tham số JVM tương ứng với bản runtime trước.

Sau rollback, xác minh service hoạt động và ghi nhận runtime thực tế bằng java -version cùng jcmd PID VM.version.

Không giữ JDK cũ dễ bị tổn thương như runtime mặc định sau khi hoàn tất điều tra. Nếu cần thời gian để sửa lỗi, áp dụng biện pháp giảm thiểu được security owner phê duyệt, giới hạn phơi nhiễm và đặt hạn hoàn thành cập nhật lại.

## 18. Lỗi thường gặp khi cập nhật JDK

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| java -version vẫn hiện bản cũ | PATH ưu tiên thư mục JDK cũ hoặc shell giữ môi trường cũ | Kiểm tra Get-Command, where.exe, command -v và PATH |
| javac và java khác phiên bản | Compiler và runtime trỏ tới hai JDK khác nhau | Đồng bộ JAVA_HOME, PATH và cấu hình IDE/build |
| Service vẫn dùng JDK cũ | Service có đường dẫn tuyệt đối hoặc chưa restart | Kiểm tra service configuration và jcmd PID VM.version |
| Installer báo không thể nâng cấp | Quy tắc cài đặt của vendor hoặc quyền hệ thống | Đọc hướng dẫn installer, kiểm tra phiên bản hiện tại và quyền |
| Service không khởi động sau patch | Thay đổi TLS, security property, native library hoặc cấu hình | Đọc log, kiểm tra release notes và chạy smoke test có mục tiêu |
| Kết nối TLS thất bại | Certificate, CA, protocol hoặc cipher không còn được chấp nhận | Kiểm tra certificate chain và chính sách TLS; không nới bảo mật tùy tiện |
| Container vẫn chứa Java cũ | Base image hoặc runtime đóng gói chưa được rebuild | Cập nhật Dockerfile/base image và triển khai image digest mới |
| Bản vá không áp dụng vào runtime bundled | Ứng dụng mang JRE/JDK riêng | Cập nhật và phát hành lại artifact chứa runtime |
| Kiểm thử pass nhưng production lỗi | Khác vendor, OS, kiến trúc, tham số JVM hoặc traffic | Đối chiếu môi trường và rollout canary |
| Bản cũ vẫn còn trên máy | Cài song song hoặc gói cũ chưa được gỡ theo chính sách | Kiểm kê, đánh giá dependency và gỡ bản không còn được phép dùng |

Không xóa thủ công thư mục JDK đang được service sử dụng. Xác định đúng tiến trình và quy trình cài đặt trước khi gỡ bản cũ.

## 19. Tự động hóa và quản lý trạng thái bản vá

Khi có nhiều máy hoặc nhiều workload, kiểm tra thủ công từng host dễ bỏ sót runtime.

Có thể tự động hóa các công việc sau:

- Thu thập java.version, java.runtime.version, java.vendor và java.home.
- Lấy version từ tiến trình đang chạy, không chỉ từ PATH.
- Đối chiếu inventory với fixed version trong advisory của vendor.
- Quét container image và artifact đóng gói runtime.
- Tạo báo cáo runtime đã vá, chưa vá, không còn hỗ trợ hoặc chưa xác định.
- Tạo ticket cho workload có rủi ro cao và theo dõi thời hạn khắc phục.
- Lưu bằng chứng kiểm thử, version, build ID, image digest và thời điểm triển khai.

Mỗi bản ghi inventory nên phân biệt rõ **JDK đã cài** và **JVM đang chạy**. Một máy có thể đã cài bản mới nhưng service vẫn dùng bản cũ.

Không nên so sánh version bằng cách sắp xếp chuỗi ký tự. Version Java là các thành phần số; hãy dùng bộ phân tích version hoặc công cụ quản lý package phù hợp. Với build của vendor, giữ cả version string đầy đủ và thông tin vendor/build.

## 20. Checklist cập nhật bản vá JDK

Trước khi cập nhật:

- [ ] Kiểm kê JDK, vendor, version và tiến trình đang chạy.
- [ ] Đọc advisory, CVE, affected version và fixed version.
- [ ] Xác định feature release cần giữ và bản update được hỗ trợ.
- [ ] Tải gói từ nguồn chính thức và xác minh tính toàn vẹn.
- [ ] Đọc release notes, known issues và hướng dẫn cài đặt.
- [ ] Lưu cấu hình, truststore, service definition và bản runtime/image trước đó.
- [ ] Chuẩn bị test, canary, giám sát và kế hoạch rollback.

Sau khi cập nhật:

- [ ] Xác nhận java -version và javac -version.
- [ ] Xác nhận java.home, vendor và runtime version.
- [ ] Restart workload cần thiết.
- [ ] Dùng jcmd PID VM.version kiểm tra JVM thực tế.
- [ ] Chạy smoke test, integration test và kiểm tra TLS/security.
- [ ] Theo dõi log, metrics, lỗi và hiệu năng.
- [ ] Cập nhật inventory, ticket và bằng chứng kiểm toán.
- [ ] Gỡ runtime cũ theo chính sách sau khi hết thời gian rollback.

## 21. Tổng kết

Cập nhật bản vá JDK là hoạt động bảo trì bảo mật cần được thực hiện thường xuyên và có kiểm soát. Công việc không kết thúc ở bước cài installer: phải xác định đúng runtime, chọn bản vá phù hợp, cập nhật mọi nơi chứa JDK, restart workload, kiểm tra JVM thực tế và chạy test sau thay đổi.

Những nguyên tắc cần nhớ:

- Theo dõi security advisory của đúng nhà cung cấp JDK đang dùng.
- Phân biệt update trong cùng feature release với feature upgrade.
- Kiểm kê cả JDK đã cài, JVM đang chạy và runtime đóng gói trong container/ứng dụng.
- Cập nhật từ nguồn tin cậy và theo đúng hướng dẫn của vendor.
- Kiểm tra java -version, javac -version và jcmd PID VM.version.
- Kiểm thử TLS, certificate, security provider, native library và chức năng ứng dụng.
- Rollout theo giai đoạn, có giám sát và kế hoạch rollback được phê duyệt.
- Duy trì inventory và bằng chứng để biết workload nào đã đạt security baseline.

**Tài liệu tham khảo chính thức:**

- [Oracle Security Alerts — CPU, CSPU and Security Alerts](https://www.oracle.com/security-alerts/)
- [Oracle Security Fixing Policies](https://www.oracle.com/corporate/security-practices/assurance/vulnerability/security-fixing/)
- [JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322)
- [The jcmd Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK Installation Guide — Windows](https://docs.oracle.com/en/java/javase/25/install/installation-jdk-microsoft-windows-platforms.html)
- [Oracle JDK Installation Guide — Linux](https://docs.oracle.com/en/java/javase/24/install/installation-jdk-linux-platforms.html)
