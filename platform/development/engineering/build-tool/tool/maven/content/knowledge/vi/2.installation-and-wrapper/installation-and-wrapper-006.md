# Tạo Maven Wrapper bằng `wrapper:wrapper` và quản lý các tệp được sinh

## 1. Vì sao dự án Maven cần Wrapper?

**Maven Wrapper** là bộ script và cấu hình đặt ngay trong repository để mọi người chạy dự án bằng phiên bản Apache Maven đã chọn, kể cả khi máy chưa cài Maven toàn cục. Thay vì yêu cầu tất cả lập trình viên cài cùng một bản Maven rồi chạy `mvn clean verify`, dự án cung cấp `./mvnw clean verify` (Linux/macOS) hoặc `.\mvnw.cmd clean verify` (Windows). Lần chạy đầu, Wrapper có thể tải bản phân phối Maven theo cấu hình; những lần sau thường tái sử dụng bản đã tải.

Cần phân biệt ba thành phần:
- **Maven Wrapper Plugin** cung cấp goal `wrapper:wrapper` để **tạo hoặc cập nhật tệp Wrapper** trong cây nguồn dự án.
- **Wrapper scripts** (`mvnw`, `mvnw.cmd`) là lệnh mà thành viên và CI chạy hằng ngày.
- **Maven distribution** là bộ thực thi Maven thật được Wrapper tải/chạy theo `distributionUrl`; ở một số kiểu Wrapper còn có `maven-wrapper.jar` làm chương trình khởi động.

Wrapper cố định **phiên bản Maven**, không tự cài JDK và không thay thế `pom.xml`, cấu hình dependency hay plugin build. Máy vẫn cần Java/JDK thích hợp với dự án; lần tải đầu cần mạng hoặc kho phân phối nội bộ có thể truy cập.

## 2. Tạo Wrapper lần đầu với `wrapper:wrapper`

Mở terminal **tại thư mục gốc của dự án**, nơi đặt `pom.xml` (với dự án đa module, dùng thư mục chứa POM tổng). Ở bước khởi tạo này cần có sẵn một lệnh `mvn` chạy được để thực thi plugin:

```bash
mvn -version
mvn wrapper:wrapper
```

Goal `wrapper:wrapper` là goal của `org.apache.maven.plugins:maven-wrapper-plugin`. Nó sinh script và tệp cấu hình ngay trong thư mục dự án. Nếu không chỉ rõ phiên bản Maven cần dùng, plugin mặc định chọn phiên bản Maven của tiến trình `mvn` đang chạy. Để dự án có phiên bản đã thống nhất, hãy chỉ định rõ:

```bash
mvn wrapper:wrapper -Dmaven=3.9.9 -Dtype=only-script
```

`3.9.9` ở đây là **phiên bản minh họa**; chọn một bản Maven phát hành chính thức đã được dự án kiểm thử. `-Dmaven` đặt phiên bản Maven chạy lúc build; `-Dtype` quyết định cách Wrapper khởi động và những tệp được sinh.

Khi cần khóa cả phiên bản **plugin tạo Wrapper** để thao tác tái tạo có thể kiểm soát, dùng tên plugin đầy đủ, ví dụ:

```bash
mvn org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.9 -Dtype=only-script
```

Tên plugin đầy đủ cũng hữu ích nếu Maven không phân giải được tiền tố goal `wrapper`. Lệnh trên chỉ để khởi tạo/cập nhật Wrapper: từ đó về sau, người sử dụng dự án thường chạy `mvnw`, không cần chạy lại `wrapper:wrapper` mỗi lần build.

## 3. Những tệp sinh ra và vai trò của từng tệp

Với kiểu **`only-script`** (mặc định khi tạo mới bằng Maven Wrapper Plugin từ 3.2.0 trở lên), cấu trúc cơ bản là:

```text
project-root/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── .mvn/
    └── wrapper/
        └── maven-wrapper.properties
```

| Tệp | Vai trò | Có đưa vào Git? |
| --- | --- | --- |
| `mvnw` | Shell script dành cho Linux/macOS và môi trường POSIX; tải/chạy phiên bản Maven được cấu hình. | Có |
| `mvnw.cmd` | Batch script dành cho Windows; tương đương `mvnw`. | Có |
| `.mvn/wrapper/maven-wrapper.properties` | Chỉ định phiên bản/URL bản phân phối Maven, loại Wrapper và các tùy chọn hỗ trợ. | Có |
| `.mvn/wrapper/maven-wrapper.jar` | Chương trình khởi động bằng Java, **được kèm sẵn khi `-Dtype=bin`**; không có ở `only-script`. | Có, **nếu** chọn `bin` |
| `.mvn/wrapper/MavenWrapperDownloader.java` | Mã nguồn hỗ trợ tải Wrapper JAR ở kiểu `source`. | Có, **nếu** được sinh |
| `mvnwDebug`, `mvnwDebug.cmd` | Script chạy Maven ở chế độ debug; chỉ xuất hiện khi yêu cầu sinh debug script, ví dụ `-DincludeDebug=true`. | Có, nếu dùng |

Đừng nhầm `.mvn/wrapper/` với `.m2/`: thư mục `.mvn/wrapper/` nằm trong **repository** để chia sẻ cách chạy build; Maven được Wrapper tải về thường nằm dưới thư mục người dùng `~/.m2/wrapper/dists/`; dependency tải về thường nằm dưới `~/.m2/repository/`. Hai vùng cache người dùng không cần commit.

Ví dụ nội dung `.mvn/wrapper/maven-wrapper.properties` khi sinh bằng plugin 3.3.4, Maven 3.9.9 và kiểu `only-script`:

```properties
wrapperVersion=3.3.4
distributionType=only-script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

Đây là ví dụ cấu hình, không phải mẫu cố định cho mọi phiên bản plugin. `distributionUrl` quyết định bản phân phối thực sự được tải; `wrapperVersion` mô tả phiên bản Wrapper; `distributionType` mô tả cách khởi động. Ở các kiểu cần Wrapper JAR, tệp properties còn có thể chứa `wrapperUrl`; thuộc tính kiểm tra toàn vẹn có thể được thêm như `distributionSha256Sum` và `wrapperSha256Sum` theo trường hợp sử dụng.

**Lưu ý:** Không tự xóa `mvnw` hoặc `maven-wrapper.properties` chỉ vì máy mình đã cài Maven; thiếu một trong các tệp cốt lõi có thể khiến đồng đội và CI không khởi động được build.

## 4. Bốn kiểu phân phối Wrapper và cách chọn

Apache Maven Wrapper Plugin hỗ trợ bốn giá trị `-Dtype`:

| Kiểu | Tệp/chiến lược chính | Khi nào nên cân nhắc |
| --- | --- | --- |
| `only-script` | Chỉ cần hai script và properties; script tải **Maven distribution trực tiếp**, không dùng `maven-wrapper.jar` hoặc `MavenWrapperDownloader.java`. Trên Unix dùng `curl`/`wget`; Windows dùng PowerShell. | Mặc định phù hợp đa số dự án, không cần commit JAR bootstrap. |
| `script` | Script có cơ chế **tải Wrapper JAR khi cần**, rồi JAR tải/chạy Maven. | Muốn dùng bootstrap bằng JAR nhưng không lưu nhị phân JAR trong Git. |
| `bin` | Kèm sẵn `.mvn/wrapper/maven-wrapper.jar` trong repository. | Muốn tránh tải thêm Wrapper JAR khi bootstrap; phải quản lý nhị phân đã commit. |
| `source` | Thêm `.mvn/wrapper/MavenWrapperDownloader.java` để hỗ trợ biên dịch mã tải Wrapper JAR khi cần. | Môi trường muốn lưu mã nguồn bootstrap hoặc cần cơ chế tải thay thế. |

Ví dụ thay đổi kiểu:

```bash
mvn wrapper:wrapper -Dmaven=3.9.9 -Dtype=bin
```

**Không nên mặc định cho rằng mọi dự án phải có `maven-wrapper.jar`.** Với `only-script`, không có JAR là hành vi bình thường; với `bin`, thiếu JAR sau khi checkout có thể là lỗi bỏ sót tệp khi commit hoặc do quy tắc `.gitignore`. Việc dùng `bin` cũng không có nghĩa Maven distribution đã được đóng gói: bản phân phối Maven vẫn có thể phải tải trong lần chạy đầu.

Khi chạy lại `wrapper:wrapper` trên dự án đã có `maven-wrapper.properties`, plugin đọc `distributionType` hiện hữu để **giữ kiểu cũ** nếu không truyền `-Dtype`. Truyền `-Dtype` rõ ràng khi chủ động chuyển kiểu.

## 5. Chạy và xác minh Wrapper đã sinh

Sau khi sinh tệp, dùng lệnh phù hợp hệ điều hành, từ thư mục gốc dự án:

**Linux/macOS hoặc shell tương thích POSIX:**

```bash
./mvnw -version
./mvnw -B -ntp clean verify
```

**Windows PowerShell:**

```powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
```

`-version` cho biết phiên bản Maven thực sự được chạy và thông tin Java, nhờ đó kiểm tra cấu hình trước khi build. `-B` bật chế độ batch thích hợp cho CI; `-ntp` tắt thông tin tiến độ tải xuống để log gọn hơn. `clean verify` là một ví dụ vòng đời Maven thông dụng, vẫn do `pom.xml` và plugin của dự án quyết định việc cần làm. Không khẳng định build `verify` luôn thành công: kết quả còn phụ thuộc mã nguồn, test, JDK và dependency.

Ở lần đầu, Wrapper kiểm tra bản Maven đã cấu hình, tải và giải nén nếu chưa có trong cache. Các lần tiếp theo thường dùng lại bản đã có. Khi ghi hướng dẫn chạy dự án vào `README.md`, ưu tiên cặp lệnh `./mvnw ...` và `.\mvnw.cmd ...`; CI cũng nên dùng Wrapper thay cho `mvn` cài sẵn nếu muốn cùng phiên bản Maven với máy lập trình.

## 6. Quản lý tệp sinh ra trong Git

**Nguyên tắc:** Các tệp giúp tái lập cách khởi động build thuộc về mã nguồn và cần được kiểm soát phiên bản. Sau khi sinh:

```bash
git status --short
git add mvnw mvnw.cmd .mvn/wrapper/maven-wrapper.properties
git diff --cached --stat
```

Kiểm tra diff trước khi commit, nhất là `distributionUrl`, `distributionType`, `wrapperVersion` và quyền thực thi của `mvnw`. Trên Linux/macOS, nếu script chưa có quyền chạy:

```bash
chmod +x mvnw
git add --chmod=+x mvnw
```

Khi dùng `-Dtype=bin`, phải thêm `.mvn/wrapper/maven-wrapper.jar` vào Git sau khi kiểm tra nguồn gốc và chính sách của dự án. Khi dùng `source`, thêm `MavenWrapperDownloader.java` nếu tệp được sinh. Nếu `.gitignore` có quy tắc loại `*.jar` hoặc `.mvn/`, cần điều chỉnh ngoại lệ **đúng phạm vi** để không vô tình loại tệp Wrapper cần thiết; tránh gỡ bỏ toàn bộ quy tắc ignore của dự án. Không commit cache `.m2/wrapper/dists/`, `.m2/repository/`, thư mục `target/` hoặc tài khoản/secret cấu hình tải.

Trong dự án đa module, nên đặt một bộ Wrapper ở **gốc dự án** cạnh POM tổng và dùng bộ đó cho toàn reactor; không cần sinh bộ script lặp lại trong từng module con. Nếu repository chứa nhiều dự án Maven độc lập, mỗi gốc dự án có thể có Wrapper riêng theo quy ước đã thống nhất.

## 7. Nâng cấp Maven và bảo trì Wrapper

Có hai thay đổi khác nhau cần quản lý:

1. **Nâng phiên bản Maven chạy build:** chạy lại goal với `-Dmaven` là lựa chọn dễ kiểm soát, hoặc sửa `distributionUrl` sang bản Maven chính thức mong muốn. Ví dụ:
   
   ```bash
   mvn wrapper:wrapper -Dmaven=3.9.11
   ```
   
   Lệnh này minh họa nâng Maven từ 3.9.9 lên 3.9.11; phiên bản thực tế phải phù hợp Java, plugin và CI của dự án. Kiểm tra lại properties rồi chạy `./mvnw -version` và `./mvnw -B -ntp clean verify`.
2. **Nâng phiên bản Wrapper/plugin tạo Wrapper:** chạy goal với phiên bản plugin được phê duyệt, kiểm tra các script/tệp JAR/properties mới và thử trên hệ điều hành được hỗ trợ.

**Cẩn thận khi tái sinh:** `wrapper:wrapper` có thể thay thế nội dung `maven-wrapper.properties` bằng cấu hình được sinh từ các tham số hiện tại. Nếu trước đó đã dùng URL mirror nội bộ, checksum hoặc tùy chọn tùy chỉnh, phải đối chiếu diff và bảo toàn/cấp lại các giá trị cần thiết. Chỉ cập nhật một nhóm thay đổi có chủ đích, kiểm tra trên CI rồi commit cả script lẫn properties tương ứng; tránh sửa tay từng phần của script được sinh mà không kiểm thử.

Muốn thay đổi loại Wrapper từ `only-script` sang `bin` (hoặc ngược lại), dùng `-Dtype=...` và kiểm tra danh sách tệp thêm/xóa trong Git. Đừng chỉ sửa dòng `distributionType` mà giữ nguyên tập tệp không tương ứng.

## 8. An toàn, mạng và tính tái lập

- **Nguồn tải:** Chỉ dùng `distributionUrl` từ nguồn tin cậy hoặc repository manager do tổ chức quản lý, ưu tiên HTTPS. Với mạng nội bộ, cấu hình URL/mirror phù hợp ngay khi sinh Wrapper; kiểm thử trên máy sạch hoặc runner CI chưa có cache.
- **Kiểm tra toàn vẹn:** Maven Wrapper hỗ trợ `distributionSha256Sum` cho tệp phân phối Maven và `wrapperSha256Sum` cho Wrapper JAR ở các kiểu có JAR. Lấy checksum SHA-256 thật từ nguồn được xác thực và so khớp chính xác; không tự điền chuỗi hash đoán. Sau khi tái sinh, xác minh các trường checksum vẫn còn.
- **Bí mật đăng nhập:** Không commit mật khẩu hoặc token trong URL, POM hay script. Nếu kho phân phối cần xác thực, dùng cơ chế secret của môi trường (ví dụ biến môi trường `MVNW_USERNAME`, `MVNW_PASSWORD` khi phù hợp) và chính sách bảo mật của tổ chức.
- **Reproducibility có giới hạn:** Wrapper thống nhất phiên bản **Maven**, không tự cố định mọi thứ. Phiên bản JDK, plugin/dependency, repository và môi trường chạy vẫn cần được quản lý riêng.
- **Cache và offline:** Build đầu tiên thường cần tải Maven; chạy offline sẽ thất bại nếu chưa có bản phân phối hoặc dependency trong cache. Đừng nhầm lỗi mạng khi tải Maven với lỗi giải quyết dependency của chính Maven.
- **Không trộn đường chạy:** Nếu máy phát triển chạy `./mvnw` nhưng CI chạy `mvn` cài sẵn, hai môi trường có thể dùng Maven khác phiên bản dù cùng checkout một commit.

## 9. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `mvn: command not found` khi khởi tạo | Chưa có Maven toàn cục để chạy plugin lần đầu. | Cài/chuẩn bị Maven cho người khởi tạo, chạy `mvn wrapper:wrapper`; sau khi commit Wrapper, người dùng khác chạy `mvnw`. |
| `./mvnw: Permission denied` trên Unix | Bit thực thi của script chưa được lưu/khôi phục đúng. | Cấp quyền `chmod +x mvnw`, lưu bit thực thi vào Git và xác minh lại. |
| `mvnw` không được tìm thấy | Đang ở sai thư mục, gọi thiếu `./` hoặc chọn script khác hệ điều hành. | Chạy từ gốc dự án: `./mvnw` trên Unix, `.\mvnw.cmd` trên Windows PowerShell. |
| Không tải được Maven/SSL/proxy timeout | `distributionUrl`, DNS, proxy, firewall, chứng chỉ TLS hoặc xác thực repository. | Kiểm tra URL và mạng; dùng mirror tin cậy và thông tin đăng nhập qua secret nếu cần. |
| Không có `maven-wrapper.jar` | Dự án dùng `only-script` hoặc kiểu khác không kèm sẵn JAR. | Đọc `distributionType`; chỉ yêu cầu JAR trong Git nếu chọn `bin`. |
| CI chạy sai Maven | CI gọi `mvn` hệ thống hoặc chạy script ở sai gốc. | Dùng Wrapper đã commit và xác minh phiên bản bằng `./mvnw -version`. |
| Sau khi sinh lại bị mất cấu hình mirror/checksum | Plugin tạo lại `maven-wrapper.properties` từ tham số đang dùng. | Xem diff, khôi phục đúng giá trị mong muốn, kiểm tra bản tải và build trước commit. |
| `No plugin found for prefix 'wrapper'` | Không phân giải được plugin prefix/repository hoặc cấu hình plugin. | Kiểm tra repository/plugin, thử tọa độ plugin đầy đủ như ví dụ ở mục 2. |

## 10. Bài thực hành kiểm tra hoàn chỉnh

Trên một dự án Maven mẫu có `pom.xml`:
1. Chạy `mvn wrapper:wrapper -Dmaven=3.9.9 -Dtype=only-script` từ gốc.
2. Xác nhận có `mvnw`, `mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties`, đồng thời không mặc nhiên tìm `maven-wrapper.jar`.
3. Đọc `distributionType` và `distributionUrl` để giải thích vì sao Wrapper sẽ chạy đúng Maven được chỉ định.
4. Chạy `./mvnw -version` trên Unix hoặc `.\mvnw.cmd -version` trên Windows; đối chiếu Maven hiển thị với phiên bản đã chọn.
5. Chạy `clean verify` bằng Wrapper, xem kết quả thực tế; nếu thất bại thì phân biệt lỗi bootstrap, JDK, dependency và test.
6. Dùng `git status`/`git diff` xác nhận chỉ các tệp Wrapper dự định được thêm; kiểm tra quyền chạy `mvnw` và commit cùng nhau.
7. Thử khởi chạy từ một môi trường khác hoặc CI dùng cùng bộ script; xác nhận không phải cài Maven thủ công và kết quả dùng cùng phiên bản Maven.

**Tiêu chí hoàn thành:** Thành viên mới có thể clone repository, có JDK phù hợp, chạy script Wrapper đúng nền tảng, tự tải/tái sử dụng Maven đã chọn và build theo cùng một cấu hình được quản lý trong Git.

## Tài liệu chính thức

- [Apache Maven Wrapper — cách cài, chạy, đổi Maven, bảo mật](https://maven.apache.org/tools/wrapper/)
- [Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html)
- [Goal `wrapper:wrapper` và các tham số](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html)
