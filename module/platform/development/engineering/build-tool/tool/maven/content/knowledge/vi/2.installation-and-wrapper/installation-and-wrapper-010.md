# Xác minh nguồn tải, checksum và quyền thực thi của Maven Wrapper

## 1. Vì sao phải kiểm tra Wrapper trước khi chạy?

Maven Wrapper là bộ tệp đi kèm dự án giúp chạy đúng phiên bản Apache Maven mà dự án lựa chọn. Thay vì yêu cầu mọi thành viên tự cài cùng một Maven rồi chạy `mvn`, dự án có thể dùng `./mvnw` trên Linux/macOS hoặc `mvnw.cmd` trên Windows. Khi cần, Wrapper tải bản phân phối Maven về máy và dùng bản đó để thực hiện lệnh build.

Điểm quan trọng: **Wrapper là mã được thực thi trên máy lập trình viên hoặc CI và có thể tải thêm chương trình từ mạng**. Vì vậy, thấy tệp `mvnw` trong repository chưa đủ để kết luận an toàn. Trước lần chạy đầu tiên, cần trả lời ba câu hỏi:

1. **Nguồn tải có đáng tin?** Wrapper sẽ truy cập máy chủ nào, qua giao thức nào, để lấy bản phân phối Maven hoặc thành phần khởi động?
2. **Tệp tải về có đúng nội dung dự kiến?** Giá trị checksum SHA-256 mà dự án tin cậy có khớp với byte của tệp nhận được không?
3. **Script có được phép chạy đúng trên hệ điều hành/CI?** Tệp Unix có quyền thực thi trong Git chưa, có bị đổi kiểu xuống dòng và có đúng cách gọi không?

Ba lớp kiểm tra này giải quyết các vấn đề khác nhau. URL đúng không chứng minh byte tải về nguyên vẹn; checksum đúng không chứng minh script `mvnw` không bị sửa; quyền thực thi đúng không chứng minh nội dung script đáng tin.

## 2. Nhận diện đúng các thành phần cần kiểm tra

Một dự án Maven Wrapper thường có những tệp sau:

```text
project/
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── pom.xml
```

- `mvnw`: script dành cho môi trường dùng shell POSIX, phổ biến trên Linux và macOS. Thường gọi bằng `./mvnw`.
- `mvnw.cmd`: script dành cho Windows; trong PowerShell thường gọi `.\mvnw.cmd`.
- `.mvn/wrapper/maven-wrapper.properties`: cấu hình của Wrapper, đặc biệt là `distributionUrl` và các checksum nếu đã khai báo.
- `.mvn/wrapper/maven-wrapper.jar`: có thể có ở kiểu phân phối `bin`, hoặc được tải khi kiểu Wrapper cần JAR để khởi động.
- `.mvn/wrapper/MavenWrapperDownloader.java`: có thể có ở kiểu `source` để hỗ trợ tải thành phần Wrapper.

**Không được coi thiếu `maven-wrapper.jar` là lỗi trong mọi dự án.** Maven Wrapper hiện hỗ trợ kiểu `only-script` (mặc định khi cài mới ở các phiên bản Wrapper tương ứng), trong đó script trực tiếp tải bản phân phối Maven mà không cần JAR của Wrapper. Các kiểu `bin`, `source`, `script` có cơ chế khởi động khác nhau. Khi kiểm tra, phải nhìn các tệp thực tế và kiểu Wrapper đã được thiết lập, thay vì áp dụng một danh sách bắt buộc cho mọi phiên bản.

Wrapper **không thay thế JDK**. Máy vẫn cần Java/JDK phù hợp với yêu cầu chạy Maven và yêu cầu biên dịch của dự án. Tải đúng Maven chưa có nghĩa là đã dùng đúng phiên bản Java.

## 3. Xác minh nguồn tải trước khi cho script truy cập mạng

### 3.1. Đọc cấu hình, xác định artifact thật sự được tải

Trong `.mvn/wrapper/maven-wrapper.properties`, tập trung vào những khóa sau:

| Khóa | Dùng để làm gì? | Cần kiểm tra |
|---|---|---|
| `distributionUrl` | Địa chỉ bản phân phối Apache Maven, thường là tệp ZIP | Đúng sản phẩm, phiên bản, tên tệp, host và giao thức |
| `distributionSha256Sum` | SHA-256 kỳ vọng của tệp phân phối Maven | Có được cung cấp từ nguồn đáng tin và khớp đúng artifact ở `distributionUrl` |
| `wrapperUrl` | Nguồn tải `maven-wrapper.jar` ở kiểu Wrapper cần tải JAR | Đúng phiên bản, nguồn tin cậy; không áp dụng cho mọi kiểu |
| `wrapperSha256Sum` | SHA-256 kỳ vọng của `maven-wrapper.jar` | Chỉ dùng để xác minh JAR Wrapper, không thay checksum của Maven ZIP |

Ví dụ `distributionUrl` cho một phiên bản Maven cụ thể:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

Đây là **ví dụ cấu trúc URL với Maven 3.9.9**, không phải lời khuyên rằng dự án mới phải dùng phiên bản đó. Phiên bản đã chọn cần phù hợp yêu cầu dự án và chính sách cập nhật. Giá trị checksum thực tế phải lấy/kiểm chứng cho **đúng tệp ZIP** rồi mới ghi vào properties; không tự điền một chuỗi băm mẫu.

Cần kiểm tra host thực tế (chẳng hạn kho artifact chính thức được dự án chấp thuận hoặc repository manager nội bộ), HTTPS và mọi chuyển hướng tới máy chủ khác. Với repository manager nội bộ, cần biết ai quản lý mirror, nguồn upstream và cách mirror kiểm tra artifact đầu vào. Một địa chỉ trông giống tên miền quen thuộc hoặc dùng HTTPS chỉ giúp xác nhận kết nối tới host theo hệ thống chứng chỉ; tự nó chưa chứng minh nội dung bản phát hành đã được nhà phát hành xác nhận.

Không nên mặc định `distributionUrl` là nguồn duy nhất có thể ảnh hưởng đến tải xuống: cấu hình của Wrapper, loại phân phối, biến môi trường (ví dụ cấu hình repository manager `MVNW_REPOURL`) và hạ tầng mạng của CI có thể tác động tới đích tải. Khi điều tra sai khác giữa máy cá nhân và CI, hãy đối chiếu cả các cấu hình đó.

### 3.2. Kiểm tra nguồn của chính script Wrapper

Script `mvnw` và `mvnw.cmd` nằm trong repository, vì thế chúng cũng là mã thực thi. Một checksum được khai báo cho Maven ZIP **không tự xác thực nội dung của hai script**. Trước khi chạy script từ nhánh hoặc pull request chưa tin cậy, hãy kiểm tra thay đổi so với phiên bản đã được nhóm phê duyệt:

```bash
git status --short -- mvnw mvnw.cmd .mvn/wrapper
git diff -- mvnw mvnw.cmd .mvn/wrapper
git diff --cached -- mvnw mvnw.cmd .mvn/wrapper
```

Ba lệnh trên chỉ xem trạng thái, thay đổi chưa stage và thay đổi đã stage; chúng không thực thi Wrapper. Với tệp chưa được Git theo dõi, phải mở và kiểm tra nội dung riêng vì `git diff` thông thường chưa hiển thị nội dung tệp untracked.

Đặc biệt chú ý những dòng thêm lệnh tải/chạy chương trình ngoài dự kiến, thay đổi `distributionUrl` hoặc `wrapperUrl`, bỏ kiểm tra checksum, chèn lệnh gửi biến môi trường hoặc thông tin bí mật đi nơi khác, và thay đổi script không đi kèm lý do cập nhật Wrapper. Khi cần cập nhật Wrapper, ưu tiên sinh lại bộ tệp bằng công cụ/plugin chính thức trên môi trường tin cậy rồi review diff trước khi commit.

## 4. Kiểm tra checksum đúng cách

### 4.1. Checksum xác minh điều gì?

SHA-256 biến nội dung của một tệp thành giá trị băm dài 256 bit, thường biểu diễn bằng **64 ký tự hex**. Nếu nội dung ZIP thay đổi, giá trị băm tính lại gần như chắc chắn sẽ khác. Maven Wrapper hỗ trợ cấu hình:

- `distributionSha256Sum`: SHA-256 kỳ vọng của **tệp phân phối Maven** được tải.
- `wrapperSha256Sum`: SHA-256 kỳ vọng của **JAR Maven Wrapper** khi thành phần đó được dùng/tải.

Apache Maven Wrapper yêu cầu các giá trị checksum khai báo ở dạng hex chữ thường. Kiểm tra checksum phải diễn ra trước khi tin và thực thi tệp tải về.

**Điểm then chốt về nguồn gốc checksum:** nếu kẻ tấn công có thể thay đồng thời tệp ZIP và giá trị băm mà bạn lấy từ cùng nguồn không đáng tin, phép so khớp vẫn có thể “PASS”. Hãy lấy checksum từ kênh phát hành đáng tin, hoặc xác minh tính xác thực của bản phát hành trước khi tính checksum mà dự án sẽ cố định.

Apache công bố checksum SHA-512 và chữ ký PGP cho nhiều gói phân phối Maven. `distributionSha256Sum` của Wrapper lại yêu cầu **SHA-256**. Hai thuật toán này không thể hoán đổi: không dán chuỗi SHA-512 vào trường SHA-256. Có thể xác minh tệp phát hành bằng SHA-512/chữ ký PGP từ Apache, sau đó tính SHA-256 của **đúng byte ZIP đã xác thực** để đưa vào cấu hình Wrapper. Khi dùng PGP, còn phải xác minh khóa ký thuộc về nhà phát hành bằng kênh đáng tin; chỉ thấy thông báo “Good signature” với khóa chưa xác thực là chưa đủ.

### 4.2. Tính SHA-256 của một ZIP đã được xác thực

Giả sử đã tải và xác minh tệp phát hành `apache-maven-3.9.9-bin.zip` bằng nguồn/chữ ký đáng tin. Cách tính SHA-256 trên các hệ điều hành:

**Linux:**

```bash
sha256sum apache-maven-3.9.9-bin.zip
```

**macOS:**

```bash
shasum -a 256 apache-maven-3.9.9-bin.zip
```

**Windows PowerShell:**

```powershell
(Get-FileHash .\apache-maven-3.9.9-bin.zip -Algorithm SHA256).Hash.ToLowerInvariant()
```

Mỗi lệnh tạo giá trị băm của tệp thực tế; **không có một chuỗi SHA-256 cố định nào đúng cho mọi phiên bản hoặc mọi dạng nén**. Sau khi xác minh nguồn phát hành và chọn đúng bản ZIP ở `distributionUrl`, ghi giá trị SHA-256 tương ứng vào `distributionSha256Sum`. Nếu đổi phiên bản Maven hoặc đổi sang tệp TAR/ZIP khác, phải xác minh và cập nhật checksum tương ứng.

Khi dự án dùng JAR Wrapper, cũng cần xác nhận nguồn gốc `maven-wrapper.jar` và checksum `wrapperSha256Sum` theo đúng byte JAR, không tái sử dụng SHA-256 của Maven ZIP. Với `only-script`, không có JAR Wrapper để tính checksum đó; trọng tâm chuyển sang việc review script và xác minh bản phân phối Maven.

### 4.3. Diễn giải kết quả kiểm tra

| Kết quả | Ý nghĩa | Hành động |
|---|---|---|
| Tệp tải về có SHA-256 khớp giá trị kỳ vọng đáng tin | Byte của tệp khớp bản đã được chấp thuận | Có thể tiếp tục các bước xác minh và build |
| SHA-256 không khớp | Tệp không giống byte đã được duyệt, hoặc checksum/URL được cấu hình sai | Dừng build, kiểm tra nguồn, phiên bản, mirror, cache; không tắt xác minh để “cho chạy được” |
| Chưa có checksum được tin cậy | Chưa có bằng chứng đầy đủ về byte được duyệt | Lấy/xác thực checksum rồi cố định vào cấu hình |
| Chỉ kiểm tra SHA-256 của ZIP | Chỉ bao phủ byte ZIP đó | Vẫn phải xem xét script, JAR Wrapper nếu có, JDK, plugin và dependency khác |

Checksum không thay thế rà soát mã nguồn, chữ ký phát hành, kiểm soát quyền sửa repository hay kiểm tra thư viện/plugin. Đây là một lớp kiểm tra tính toàn vẹn trong chuỗi cung ứng phần mềm.

## 5. Xác minh quyền thực thi và kiểu xuống dòng

### 5.1. Linux/macOS: quyền thực thi của `mvnw`

Trên hệ Unix, gọi `./mvnw` yêu cầu tệp script có quyền thực thi với người dùng đang chạy. Kiểm tra trên máy:

```bash
ls -l mvnw
test -x mvnw
```

`ls -l` cho thấy các bit quyền; `test -x mvnw` trả mã thoát `0` nếu có quyền thực thi phù hợp, khác `0` nếu không. Hai lệnh này không chạy nội dung Wrapper.

Vì mã nguồn được chia sẻ qua Git/CI, cần kiểm tra cả **mode đã được ghi vào Git index**, không chỉ quyền trên máy cá nhân:

```bash
git ls-files --stage -- mvnw
```

Nếu được lưu đúng là tệp thực thi, mode trong dòng kết quả thường là `100755`. Nếu là `100644`, Git đang ghi nhận tệp không thực thi; một máy khác checkout có thể gặp `Permission denied` khi gọi `./mvnw`.

Sau khi nhóm đã xác minh script và quyết định bật quyền thực thi, người có quyền cập nhật repository có thể sửa:

```bash
chmod +x mvnw
git add mvnw
git ls-files --stage -- mvnw
```

Nếu hệ thống tệp/thiết lập Git không nhận thay đổi mode qua `chmod`, có thể cập nhật chỉ mode trong index bằng:

```bash
git update-index --chmod=+x mvnw
git ls-files --stage -- mvnw
```

Việc sửa mode chỉ giải quyết khả năng thực thi, **không làm script trở nên đáng tin**. `chmod 777 mvnw` không cần thiết và cấp quyền ghi quá rộng. Không dùng quyền quản trị/root chỉ để khắc phục `Permission denied` khi vấn đề là bit thực thi.

Một lỗi khác là file `mvnw` bị chuyển xuống dòng Windows CRLF, khiến dòng shebang có thể bị hiểu thành đường dẫn chứa `^M`. Giữ LF cho `mvnw` khi làm việc đa nền tảng; có thể quy định bằng `.gitattributes`, ví dụ:

```gitattributes
/mvnw text eol=lf
```

### 5.2. Windows: dùng đúng script

Windows có `mvnw.cmd` và không phụ thuộc bit `+x` của POSIX cho chính tệp `.cmd`. Trong PowerShell, cách gọi rõ ràng từ thư mục dự án là:

```powershell
.\mvnw.cmd --version
```

Trong Command Prompt, có thể dùng `mvnw.cmd --version`. Ngược lại, `./mvnw --version` là lệnh shell POSIX và có thể không chạy trong môi trường Windows thuần túy nếu không có shell tương thích.

**Chỉ chạy lệnh kiểm tra phiên bản sau khi nguồn tải, script và checksum đã được xác minh**: `--version` vẫn có thể kích hoạt quá trình tải Maven lần đầu. Không nên nghĩ “chỉ xem version” là thao tác không cần tin cậy nguồn thực thi.

### 5.3. CI và container

Trong CI Linux hoặc container, `mvnw` có thể thiếu bit thực thi nếu được đóng gói/copy từ hệ thống tệp không bảo toàn mode. Nên kiểm tra mode trong Git và quyền sau checkout/copy, rồi sửa ở nguồn nếu sai. Chèn `chmod +x mvnw` tạm trước mọi job có thể che giấu lỗi quyền trong repository; nếu chọn dùng cách đó có chủ đích, hãy ghi rõ lý do.

CI cần có JDK phù hợp, quyền ghi thư mục lưu Maven tải về, truy cập repository được phép và cơ chế kiểm soát checksum. Với PR từ nguồn chưa tin cậy, không chạy tự động script Wrapper vừa bị thay đổi cùng với quyền truy cập secrets hoặc token có đặc quyền. Hãy review thay đổi Wrapper trước khi cho job tin cậy thực thi.

## 6. Quy trình kiểm tra thực tế trước lần chạy đầu tiên

Áp dụng lần lượt cho repository vừa clone hoặc một pull request có thay đổi Maven Wrapper:

1. **Nhận diện tệp**: tìm `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`, và xác định có JAR/source downloader hay không. Hiểu kiểu Wrapper đang sử dụng.
2. **Review thay đổi**: kiểm tra script và properties so với phiên bản đã được chấp thuận; để ý tệp mới chưa được Git theo dõi, URL lạ, đoạn mã thực thi bổ sung và checksum bị bỏ.
3. **Xác minh nguồn tải**: kiểm tra `distributionUrl` đúng sản phẩm/phiên bản và repository tin cậy; kiểm tra `wrapperUrl` nếu kiểu Wrapper cần JAR. Xem cả cấu hình mirror/biến môi trường có thể thay đổi nơi tải.
4. **Cố định checksum**: lấy SHA-256 đáng tin cho đúng artifact, cấu hình `distributionSha256Sum`; nếu cần `maven-wrapper.jar`, kiểm tra `wrapperSha256Sum`. Không dùng giá trị băm của phiên bản/định dạng khác.
5. **Kiểm tra khả năng chạy**: trên Linux/macOS, xác nhận `mvnw` có mode `100755` trong Git, quyền `x` sau checkout và xuống dòng LF; trên Windows, dùng `mvnw.cmd` với shell phù hợp.
6. **Chạy kiểm chứng sau khi duyệt**: dùng `./mvnw --version` hoặc `.\mvnw.cmd --version`; đối chiếu phiên bản Maven/JDK trong kết quả với yêu cầu dự án. Sau đó mới chạy goal build/test phù hợp.

Lệnh cuối ở môi trường Linux/macOS:

```bash
./mvnw --version
./mvnw verify
```

Trong PowerShell:

```powershell
.\mvnw.cmd --version
.\mvnw.cmd verify
```

Lệnh `verify` thực thi vòng đời Maven đến phase `verify` với các plugin/goals đã gắn vào POM. Kết quả chỉ PASS khi các bước của dự án hoàn tất theo cấu hình thực tế; nó không chứng minh mọi rủi ro chuỗi cung ứng đã biến mất.

## 7. Tình huống lỗi và cách xử lý đúng bản chất

**Tình huống A — CI Linux báo `Permission denied` khi chạy `./mvnw`.** Kiểm tra `git ls-files --stage mvnw` và quyền sau checkout. Nếu mode là `100644`, sửa thành `100755` trong Git và commit thay đổi mode đã được review. Không tắt checksum hoặc đổi sang tải script khác để chữa lỗi quyền.

**Tình huống B — Wrapper báo checksum không khớp.** Dừng build; so sánh `distributionUrl`, phiên bản/tên ZIP, giá trị `distributionSha256Sum`, nguồn tải, mirror và tệp đã tải. Nếu vừa nâng phiên bản Maven, checksum cũ không còn đúng. Không xóa trường checksum hoặc dùng băm tính từ tệp đáng ngờ làm “giá trị mới” chỉ để build vượt qua lỗi.

**Tình huống C — Trên máy có Java nhưng Wrapper không tải được Maven.** Xem kết nối mạng, DNS, proxy, chứng chỉ TLS, repository manager nội bộ và cấu hình URL. Đây là lỗi khả năng truy cập nguồn tải, không tự động có nghĩa checksum sai. Nếu chỉ được dùng mirror nội bộ, cần xác thực mirror và cấu hình đúng trước khi thử lại.

**Tình huống D — Một PR chỉnh `mvnw` và thêm lệnh lạ nhưng `distributionSha256Sum` vẫn đúng.** Checksum Maven ZIP không chứng minh script an toàn. Tạm dừng việc chạy script trên CI có secrets; review nguồn gốc thay đổi và bộ tệp Wrapper bằng quy trình cập nhật tin cậy.

**Tình huống E — `mvnw` có mode `100755` nhưng Linux báo lỗi interpreter chứa `^M`.** Đây thường là vấn đề CRLF ở shebang/script. Kiểm tra kiểu xuống dòng, chuyển tệp Unix về LF và thiết lập quy ước Git; việc tiếp tục `chmod +x` không khắc phục lỗi CRLF.

## 8. Phân biệt các mức độ “đã kiểm tra”

- **Khả dụng**: script có thể chạy, tải đúng phiên bản và build hoàn tất.
- **Toàn vẹn artifact**: byte ZIP/JAR tải về khớp checksum đã được tin cậy.
- **Nguồn gốc và tính xác thực**: artifact/script gắn với nhà phát hành hoặc nguồn nội bộ đã được xác nhận qua chữ ký, khóa đáng tin, quy trình review và kiểm soát thay đổi.
- **An toàn của cả build**: còn cần kiểm tra JDK, plugin, dependency, repository, quyền CI, secrets và những tác vụ build được POM kích hoạt.

Khi bàn giao một dự án có Maven Wrapper, bằng chứng thực tế nên bao gồm: đường dẫn nguồn tải, phiên bản Maven đã chốt, checksum đã xác thực cho artifact cần thiết, trạng thái review script, mode/line ending của `mvnw`, và lần chạy `--version`/build thành công trên môi trường mục tiêu. Những bằng chứng này giúp người nhận tái lập quá trình kiểm tra thay vì chỉ tin vào việc “máy người viết chạy được”.

### Tài liệu chính thức

- [Apache Maven Wrapper — cách cài, loại phân phối, URL và SHA-256](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Wrapper Plugin — tham số distributionUrl/distributionSha256Sum/wrapperSha256Sum](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html)
- [Apache Maven Downloads — checksum phát hành và chữ ký PGP](https://maven.apache.org/download.cgi)
