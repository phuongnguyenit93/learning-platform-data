# Cài đặt Apache Ant từ bản phân phối và kiểm tra tính toàn vẹn

Apache Ant là công cụ tự động hóa quá trình build dự án Java. Ant được phân phối dưới dạng gói nén đã biên dịch sẵn, vì vậy bạn có thể tải gói binary, xác minh tệp tải về, giải nén và cấu hình biến môi trường để sử dụng mà không cần tự biên dịch Ant từ mã nguồn.

Quy trình cài đặt an toàn gồm bốn việc: chọn đúng gói binary từ nguồn chính thức, kiểm tra checksum và chữ ký phát hành, giải nén vào thư mục ổn định, rồi xác nhận Ant chạy được bằng một build nhỏ.

## 1. Chuẩn bị môi trường Java

Ant chạy trên Java. Hãy cài đặt một JDK tương thích với phiên bản Ant bạn định sử dụng trước khi cấu hình Ant. Trang tải xuống và ghi chú phát hành của Apache Ant nêu yêu cầu Java cho từng phiên bản; hãy đối chiếu yêu cầu đó với JDK trên máy.

Mở terminal và kiểm tra Java:

```bash
java -version
javac -version
```

Nếu cả hai lệnh trả về phiên bản, JDK đã có thể được gọi từ `PATH`. Kiểm tra thêm `JAVA_HOME`:

Trên Windows PowerShell:

```powershell
$env:JAVA_HOME
```

Trên Linux hoặc macOS:

```bash
echo "$JAVA_HOME"
```

`JAVA_HOME` nên trỏ đến thư mục gốc của JDK, không phải thư mục `bin` và cũng không phải đường dẫn đến tệp `java`. Ví dụ, nếu Java nằm trong `C:\Program Files\Java\jdk-21`, giá trị `JAVA_HOME` là `C:\Program Files\Java\jdk-21`.

Nếu máy chưa có JDK hoặc `java` không được nhận diện, hãy cài đặt JDK và cấu hình `JAVA_HOME` cùng `PATH` trước. Việc Ant không tìm thấy Java thường bắt nguồn từ bước này.

## 2. Tải đúng bản phân phối Ant

Mở trang tải xuống chính thức của dự án: [Apache Ant — Binary Distributions](https://ant.apache.org/bindownload.cgi). Trang này dẫn đến các máy chủ phân phối Apache và cung cấp những tệp đi kèm để xác minh bản phát hành.

Chọn gói **binary distribution** có tên theo dạng `apache-ant-<version>-bin`. Hai định dạng phổ biến là:

| Tệp | Mục đích |
|---|---|
| `apache-ant-<version>-bin.zip` | Gói ZIP, thuận tiện trên Windows và cũng dùng được trên các hệ điều hành khác |
| `apache-ant-<version>-bin.tar.gz` | Gói TAR nén GZIP, thường được dùng trên Linux và macOS |
| `apache-ant-<version>-src.zip` hoặc `-src.tar.gz` | Mã nguồn Ant; không phải gói cần chọn khi muốn cài đặt nhanh từ bản phân phối |
| Tệp `.sha512` | Giá trị checksum SHA-512 để kiểm tra nội dung tệp |
| Tệp `.asc` | Chữ ký OpenPGP của bản phát hành |

Thay `<version>` bằng phiên bản thực tế hiển thị trên trang tải xuống. Chọn một trong hai gói binary ZIP hoặc TAR.GZ; không cần tải cả hai. Không lấy bản cài đặt từ trang chia sẻ phần mềm không rõ nguồn gốc hoặc từ một gói đã được bên thứ ba đóng gói lại.

Nên tải gói binary và các tệp xác minh tương ứng vào cùng một thư mục. Giữ nguyên tên tệp để việc đối chiếu checksum và chữ ký không bị nhầm giữa các phiên bản.

## 3. Kiểm tra tính toàn vẹn của tệp tải về

Không giải nén và sử dụng ngay tệp vừa tải. Trước tiên, kiểm tra checksum SHA-512 và chữ ký OpenPGP của đúng gói binary.

### 3.1. Kiểm tra checksum SHA-512

Checksum là giá trị băm được tính từ toàn bộ nội dung của tệp. Nếu chỉ một phần dữ liệu thay đổi, giá trị SHA-512 gần như chắc chắn sẽ khác. Hãy tính checksum của gói binary trên máy rồi so sánh với giá trị trong tệp `.sha512` tương ứng được cung cấp cùng bản phát hành.

Ví dụ với gói TAR.GZ trên Linux. Đặt biến phiên bản theo đúng tên hiển thị trên trang tải xuống:

```bash
ANT_VERSION="1.10.x" # Thay bằng phiên bản thực tế
sha512sum "apache-ant-${ANT_VERSION}-bin.tar.gz"
```

Trên macOS:

```bash
ANT_VERSION="1.10.x" # Thay bằng phiên bản thực tế
shasum -a 512 "apache-ant-${ANT_VERSION}-bin.tar.gz"
```

Trên Windows PowerShell, dùng `Get-FileHash`:

```powershell
$antVersion = "1.10.x" # Thay bằng phiên bản thực tế
Get-FileHash ".\apache-ant-$antVersion-bin.zip" -Algorithm SHA512
```

Lệnh sẽ in ra một chuỗi SHA-512. Đối chiếu toàn bộ chuỗi đó với giá trị của đúng tên tệp trong tệp `.sha512` tải từ trang phân phối Apache. Không bỏ qua ký tự, không so sánh với checksum của phiên bản khác và không chỉ so sánh vài ký tự đầu hoặc cuối.

Định dạng tệp checksum có thể khác nhau giữa các công cụ. Nếu tệp có định dạng tương thích với `sha512sum -c`, có thể kiểm tra trực tiếp:

```bash
ANT_VERSION="1.10.x" # Thay bằng phiên bản thực tế
sha512sum -c "apache-ant-${ANT_VERSION}-bin.tar.gz.sha512"
```

Nếu lệnh báo sai định dạng, hãy đọc giá trị trong tệp `.sha512` và so sánh với kết quả băm vừa tính. Lỗi định dạng đầu vào không tự nó chứng minh gói binary bị hỏng.

Kết quả mong đợi là giá trị băm của gói binary trùng khớp hoàn toàn với checksum do dự án công bố. Nếu khác nhau, hãy xóa tệp tải về, tải lại từ máy chủ phân phối chính thức và kiểm tra lại. Nếu vẫn không khớp, không sử dụng gói đó.

### 3.2. Xác minh chữ ký OpenPGP

Checksum giúp phát hiện nội dung bị thay đổi so với giá trị đối chiếu. Chữ ký OpenPGP cung cấp thêm bằng chứng rằng tệp phát hành được ký bằng khóa của người phát hành. Vì vậy, hãy xác minh chữ ký `.asc` của chính gói binary.

Trước tiên, cài đặt GnuPG nếu máy chưa có lệnh `gpg`, sau đó tải tệp `KEYS` từ trang phân phối chính thức của Apache Ant. Nhập các khóa công khai:

```bash
gpg --import KEYS
```

Thực hiện xác minh. Ví dụ với gói TAR.GZ:

```bash
ANT_VERSION="1.10.x" # Thay bằng phiên bản thực tế
gpg --verify "apache-ant-${ANT_VERSION}-bin.tar.gz.asc" "apache-ant-${ANT_VERSION}-bin.tar.gz"
```

Với gói ZIP, thay cả hai tên tệp bằng `apache-ant-<version>-bin.zip.asc` và `apache-ant-<version>-bin.zip` tương ứng.

Khi chữ ký hợp lệ, GnuPG thường hiển thị thông báo `Good signature`. Tuy nhiên, chỉ thấy thông báo này chưa đủ để xác nhận danh tính người ký: bạn còn phải kiểm tra dấu vân tay (fingerprint) của khóa đã dùng để ký. Dùng mã khóa hiển thị trong kết quả xác minh để xem fingerprint:

```bash
gpg --fingerprint 0x1234ABCD
```

Thay `0x1234ABCD` bằng mã khóa hiển thị trong kết quả xác minh, sau đó đối chiếu fingerprint đầy đủ với khóa được công bố trong `KEYS` trên nguồn chính thức của Apache Ant. Nếu có thể, đối chiếu thêm thông tin khóa từ một kênh chính thức độc lập. Cảnh báo của GnuPG về việc khóa chưa được người dùng tin cậy không đồng nghĩa chữ ký sai; nó cho biết mức độ tin cậy của khóa trong kho khóa cá nhân chưa được thiết lập.

Chỉ tiếp tục khi chữ ký hợp lệ và fingerprint khớp với khóa phát hành đáng tin cậy. Nếu GnuPG báo `BAD signature`, không tìm thấy khóa phù hợp hoặc fingerprint không khớp, không giải nén và không chạy gói đó. Hãy tải lại `KEYS`, chữ ký và gói binary từ nguồn chính thức rồi xác minh lại.

### 3.3. Hiểu đúng kết quả xác minh

| Kiểm tra | Điều nó chứng minh | Điều nó không tự chứng minh |
|---|---|---|
| SHA-512 trùng khớp | Nội dung gói tải về trùng với nội dung được mô tả bởi checksum đã tải | Người tạo checksum chắc chắn là dự án Apache nếu checksum và gói cùng bị thay thế |
| Chữ ký OpenPGP hợp lệ | Nội dung gói khớp với chữ ký được tạo bởi khóa riêng tương ứng | Khóa đó thuộc đúng người phát hành nếu bạn chưa xác minh fingerprint |
| Fingerprint khớp nguồn tin cậy | Khóa công khai dùng xác minh là khóa được dự án công bố | Máy tính đã an toàn trước mọi loại mã độc khác |

Kết hợp checksum, chữ ký và việc xác minh fingerprint giúp kiểm tra cả lỗi truyền tải lẫn nguồn gốc bản phát hành. Không nên bỏ qua bước xác minh chữ ký chỉ vì checksum đã khớp.

## 4. Giải nén và cấu hình Ant

Sau khi xác minh thành công, giải nén gói binary vào một thư mục cài đặt ổn định. Tránh giải nén vào thư mục tải xuống tạm thời vì thư mục này có thể bị dọn dẹp hoặc di chuyển.

### 4.1. Windows

Ví dụ sử dụng PowerShell và gói ZIP. Thay `<version>` bằng phiên bản đã tải:

```powershell
$antVersion = "<version>"
$installRoot = "C:\tools"
$archive = ".\apache-ant-$antVersion-bin.zip"

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $installRoot
```

Sau khi giải nén, cấu trúc thư mục thường có dạng:

```text
C:\tools\
└── apache-ant-<version>\
    ├── bin\
    ├── lib\
    ├── etc\
    └── manual\
```

Đặt `ANT_HOME` trỏ đến thư mục gốc `apache-ant-<version>`. Thêm `%ANT_HOME%\bin` vào biến môi trường `Path` của người dùng trong phần **Environment Variables** của Windows. Không đặt `ANT_HOME` trỏ thẳng vào thư mục `bin`.

Đóng terminal đang mở và mở PowerShell mới để nhận các biến môi trường vừa cập nhật. Kiểm tra:

```powershell
$env:ANT_HOME
$env:JAVA_HOME
ant -version
```

### 4.2. Linux và macOS

Ví dụ dùng gói TAR.GZ và cài vào thư mục `~/tools` của người dùng:

```bash
ant_version="1.10.x" # Thay bằng phiên bản thực tế
mkdir -p "$HOME/tools"
tar -xzf "apache-ant-${ant_version}-bin.tar.gz" -C "$HOME/tools"
```

Kết quả thường là thư mục `~/tools/apache-ant-<version>` chứa các thư mục `bin`, `lib`, `etc` và `manual`. Có thể cấu hình tạm thời cho terminal hiện tại:

```bash
export ANT_HOME="$HOME/tools/apache-ant-${ant_version}"
export PATH="$ANT_HOME/bin:$PATH"
```

Để cấu hình lâu dài, thêm hai dòng `export` vào tệp khởi tạo shell đang dùng, chẳng hạn `~/.bashrc` cho Bash hoặc `~/.zshrc` cho Zsh. Sau đó mở terminal mới hoặc nạp lại tệp cấu hình tương ứng:

```bash
source ~/.bashrc
```

Nếu đang dùng Zsh, thay bằng:

```bash
source ~/.zshrc
```

Kiểm tra các biến và phiên bản Ant:

```bash
echo "$ANT_HOME"
echo "$JAVA_HOME"
ant -version
```

`ANT_HOME` phải trỏ đến thư mục gốc của bản Ant đã giải nén. `PATH` cần chứa đường dẫn đến `$ANT_HOME/bin` để có thể gọi lệnh `ant` từ mọi thư mục.

## 5. Kiểm tra Ant hoạt động thực tế

Lệnh `ant -version` xác nhận trình khởi chạy tìm thấy Ant và có thể hiển thị phiên bản. Để kiểm tra sâu hơn, chạy:

```bash
ant -diagnostics
```

Lệnh này hiển thị thông tin môi trường, Java, thư viện và cấu hình Ant. Nếu lệnh kết thúc bình thường, hãy tạo một thư mục thử nghiệm riêng và chạy một target đơn giản.

Tạo tệp `build.xml` trong thư mục thử nghiệm với nội dung:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-smoke-test" default="hello" basedir=".">
    <target name="hello">
        <echo message="Apache Ant is working."/>
        <echo message="Ant version: ${ant.version}"/>
        <echo message="Java version: ${java.version}"/>
    </target>
</project>
```

Chạy lệnh sau ngay trong thư mục có `build.xml`:

```bash
ant hello
```

Nếu không chỉ định tệp build khác, Ant sẽ tìm `build.xml` trong thư mục hiện tại và thực thi target mặc định `hello`. Kết quả cần có dòng `Apache Ant is working.` cùng thông tin phiên bản Ant và Java. Điều đó xác nhận Ant có thể khởi động, đọc build file và thực thi target.

Bạn cũng có thể xem các target được khai báo trong build file bằng:

```bash
ant -p
```

## 6. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| `ant` không được nhận diện | Thư mục `bin` chưa có trong `PATH`, hoặc terminal chưa nạp biến mới | Kiểm tra `ANT_HOME`, kiểm tra `PATH` có `ANT_HOME\bin` (Windows) hoặc `$ANT_HOME/bin` (Linux/macOS), rồi mở terminal mới |
| Không tìm thấy Java hoặc báo lỗi Java | JDK chưa được cài, `JAVA_HOME` sai hoặc `PATH` chưa có Java | Chạy `java -version`, kiểm tra `JAVA_HOME` trỏ đến thư mục gốc JDK và sửa biến môi trường |
| `ant -version` chạy nhưng build file thất bại | Lỗi có thể nằm trong `build.xml`, target hoặc dependency của dự án | Chạy Ant từ đúng thư mục, đọc dòng lỗi đầu tiên và kiểm tra tên target, cú pháp XML, đường dẫn và thư viện mà build file yêu cầu |
| Không tìm thấy `build.xml` | Đang chạy lệnh ở thư mục không chứa build file | Chuyển đến thư mục dự án hoặc dùng `ant -f path/to/build.xml target`, thay đường dẫn và tên target theo dự án |
| Giải nén xong nhưng không thấy `bin/ant` hoặc `bin/ant.bat` | Chọn nhầm gói nguồn, giải nén sai cấp thư mục hoặc tải gói không đầy đủ | Kiểm tra tên gói có hậu tố `-bin`, xem cấu trúc thư mục và xác minh lại checksum/chữ ký |
| SHA-512 không khớp | Tệp tải về bị hỏng, tải nhầm phiên bản hoặc checksum không thuộc đúng gói | Đối chiếu tên tệp, tải lại gói và checksum tương ứng từ nguồn chính thức; không sử dụng tệp chưa xác minh |
| Chữ ký không hợp lệ hoặc fingerprint không khớp | Tệp `.asc`, gói binary hoặc khóa công khai không tương ứng | Tải lại các tệp từ nguồn chính thức, kiểm tra đúng phiên bản và xác minh fingerprint trước khi cài |

Khi thay đổi `ANT_HOME` hoặc `PATH`, hãy kiểm tra trong một terminal mới để tránh nhầm lẫn giữa cấu hình đã lưu và môi trường của tiến trình đang chạy. Trên Windows, ưu tiên chỉnh biến môi trường qua giao diện hệ thống hoặc công cụ quản trị cấu hình; tránh ghi đè toàn bộ `Path` bằng một giá trị rút gọn.

## 7. Checklist hoàn tất cài đặt

- [ ] Đã chọn đúng gói `-bin` từ trang phân phối chính thức của Apache Ant.
- [ ] Đã tính SHA-512 và đối chiếu toàn bộ giá trị với checksum của đúng gói.
- [ ] Đã xác minh chữ ký `.asc` và đối chiếu fingerprint của khóa ký với nguồn chính thức.
- [ ] Đã giải nén vào thư mục ổn định và xác định đúng thư mục gốc Ant.
- [ ] `JAVA_HOME` trỏ đến JDK tương thích và `java -version` chạy thành công.
- [ ] `ANT_HOME` trỏ đến thư mục gốc Ant và `PATH` có thư mục `bin`.
- [ ] `ant -version` hiển thị phiên bản dự kiến.
- [ ] `ant -diagnostics` chạy được và target `hello` trong build file thử nghiệm thực thi thành công.

Khi các bước trên hoàn tất, Apache Ant đã được cài đặt từ bản phân phối và bản binary đã được kiểm tra tính toàn vẹn trước khi sử dụng. Khi nâng cấp, hãy tải gói của phiên bản mới, xác minh checksum và chữ ký lại từ đầu, rồi cập nhật `ANT_HOME` đến thư mục cài đặt mới.
