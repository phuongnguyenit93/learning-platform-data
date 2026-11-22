# Các dạng Maven Wrapper và yêu cầu tải xuống khi khởi động

## 1. Maven Wrapper là gì, và “khởi động” ở đây nghĩa là gì?

**Maven Wrapper** cho phép thành viên trong dự án chạy đúng phiên bản Apache Maven đã được dự án chỉ định thông qua hai script **mvnw** (Unix/macOS/Linux) và **mvnw.cmd** (Windows). Khi chạy script, Wrapper có thể tự tải bản phân phối Maven cần thiết, lưu trong bộ nhớ đệm rồi gọi Maven thực sự. Nhờ đó, đồng đội hoặc CI không bắt buộc phải cài sẵn lệnh **mvn** toàn cục.

“Khởi động” trong bài này là **bootstrap công cụ build trước khi Maven chạy mục tiêu như clean, test, package**. Đây không phải quá trình khởi động ứng dụng Java mà Maven xây dựng.

Cần phân biệt ba thành phần:

1. **Wrapper scripts**: **mvnw**, **mvnw.cmd**; đây là lối vào do repository cung cấp.
2. **Wrapper JAR**: **.mvn/wrapper/maven-wrapper.jar**; một chương trình nhỏ dùng để tải và chạy Maven trong các kiểu Wrapper sử dụng JAR. Một số kiểu không cần file này.
3. **Maven distribution**: gói Apache Maven thật, thường là **apache-maven-<version>-bin.zip**, có thể cần tải và giải nén trước khi thực thi.

Khi Maven đã khởi chạy, Maven còn có thể tải **plugins, parent POM và dependencies** theo cấu hình dự án. Đây là một lượt tải khác, xảy ra *sau* giai đoạn Wrapper chuẩn bị bản phân phối Maven.

Ví dụ dùng dự án đã có Wrapper:

~~~bash
# Linux/macOS, chạy từ thư mục gốc của dự án
./mvnw -v
./mvnw clean verify
~~~

~~~powershell
# PowerShell trên Windows, chạy từ thư mục gốc
.\mvnw.cmd -v
.\mvnw.cmd clean verify
~~~

Lệnh **-v** xem phiên bản Maven mà Wrapper sử dụng. Ngay cả thao tác này cũng có thể kích hoạt tải Maven ở lần chạy đầu nếu máy chưa có bản phân phối phù hợp.

**Wrapper quản lý phiên bản Maven, không tự cài JDK.** Máy chạy vẫn cần Java/JDK tương thích với phiên bản Maven và dự án, cùng một môi trường shell/phương tiện tải xuống thích hợp cho kiểu Wrapper đã chọn.

## 2. Các file Wrapper thường xuất hiện trong repository

Một dự án cấu hình Wrapper có hình dạng cơ bản như sau:

~~~text
hello-project/
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       ├── maven-wrapper.properties
│       ├── maven-wrapper.jar          # khi chọn bin; không có ở only-script
│       └── MavenWrapperDownloader.java  # khi chọn source
└── pom.xml
~~~

Sơ đồ liệt kê **các file có thể có**, không có nghĩa một dự án phải chứa đồng thời cả JAR lẫn Java downloader.

- **mvnw / mvnw.cmd**: hai script khởi chạy tương ứng nền tảng; thường commit vào Git cùng dự án.
- **.mvn/wrapper/maven-wrapper.properties**: khai báo URL Maven distribution, loại Wrapper, checksum nếu được cấu hình và một số thông số bootstrap.
- **maven-wrapper.jar**: nếu được lưu sẵn trong repository (**bin**), hoặc được tải khi cần (**script**, **source**), nó thực hiện phần bootstrap.
- **MavenWrapperDownloader.java**: mã nguồn công cụ tải Wrapper JAR hỗ trợ đường dự phòng cho **source**.
- **pom.xml**: cấu hình Maven build của dự án. Wrapper có nhiệm vụ đưa Maven lên trước; Maven sau đó mới đọc POM và chạy lifecycle.

Lưu ý: **.mvn/wrapper/** là cấu hình và thành phần để *khởi động Maven*; **~/.m2/wrapper/dists/** thường là nơi giữ các bản Maven đã tải; **~/.m2/repository/** là kho artifact/dependency của Maven. Ba vị trí này không có cùng chức năng.

## 3. Bốn dạng Maven Wrapper

Theo tài liệu Apache Maven Wrapper hiện hành, có **bốn distribution type**: **only-script**, **script**, **bin**, **source**. Khi cài Wrapper mới bằng plugin hiện hành, **only-script** là mặc định; dự án được tạo từ công cụ hoặc phiên bản cũ có thể dùng dạng khác.

| Dạng | File đặc trưng trong repository | Cách chuẩn bị Wrapper runtime | Điều phải tải trong lượt chạy đầu nếu chưa có cache |
| --- | --- | --- | --- |
| **only-script** | Hai script + **maven-wrapper.properties** | Script trực tiếp tải/giải nén Maven rồi gọi lệnh Maven trong bản phân phối | **Maven distribution**; không tải Wrapper JAR |
| **script** | Hai script + properties, không commit Wrapper JAR | Script tìm hoặc tải **maven-wrapper.jar**, sau đó JAR chuẩn bị Maven | **Wrapper JAR** nếu thiếu, rồi **Maven distribution** nếu thiếu |
| **bin** | Hai script + properties + **maven-wrapper.jar** | Dùng JAR đã có sẵn trong repository để chuẩn bị Maven | **Maven distribution** nếu thiếu; bình thường không cần tải Wrapper JAR |
| **source** | Hai script + properties + **MavenWrapperDownloader.java** | Dùng công cụ tải JAR; có đường dự phòng biên dịch/chạy Java downloader khi thích hợp | **Wrapper JAR** nếu thiếu, rồi **Maven distribution** nếu thiếu |

Các dạng trên quyết định cách **bootstrap Maven Wrapper**. Chúng không quyết định POM sẽ tạo JAR/WAR hay plugin dự án sẽ tải bao nhiêu dependency.

### 3.1. only-script: dạng nhẹ, mặc định ở cài đặt mới

**only-script** là kiểu rút gọn: các script trực tiếp tải Maven distribution bằng **curl** hoặc **wget** trên môi trường Unix-like, hoặc **PowerShell** trên Windows, sau đó thực thi **mvn/mvn.cmd** trong bản Maven vừa chuẩn bị.

Nó **không sử dụng maven-wrapper.jar** và không cần **MavenWrapperDownloader.java**. Đây là lựa chọn gọn gàng cho đa số dự án mới có môi trường chạy script và mạng phù hợp.

Ưu điểm: ít file, không cần commit nhị phân Wrapper JAR, ít bước bootstrap. Điểm cần lưu ý: lượt đầu vẫn phải truy cập URL tải **Maven distribution** khi chưa có cache; thiếu công cụ tải, proxy chặn hoặc URL sai vẫn có thể làm bootstrap thất bại.

### 3.2. script: script tải Wrapper JAR rồi JAR tải Maven

**script** khác **only-script** ở chỗ nó **sử dụng Maven Wrapper JAR**. Nếu **.mvn/wrapper/maven-wrapper.jar** chưa có, script thử tải JAR từ **wrapperUrl** (hoặc URL được cấu hình bởi bản Wrapper tương ứng) trước. Khi JAR đã sẵn sàng, nó tải hoặc dùng Maven distribution đã cache, rồi chạy Maven.

Ưu điểm: không cần đưa file JAR nhị phân vào Git. Chi phí của lượt cold start có thể gồm **hai gói tải độc lập**: Wrapper JAR và Maven ZIP. Nếu bị chặn ở bước tải JAR thì Maven chưa thể bắt đầu.

Không được đánh đồng **script** với **only-script**: tên nghe gần giống nhau, nhưng cơ chế tải Wrapper JAR khác nhau.

### 3.3. bin: commit Wrapper JAR để bỏ bước tải JAR khi khởi chạy

**bin** đặt sẵn **.mvn/wrapper/maven-wrapper.jar** trong repository. Script có thể dùng JAR ngay mà không cần tải *chính JAR ấy* ở lần chạy đầu. Kiểu này thích hợp khi nhóm cho phép commit nhị phân đã xác minh và muốn hạn chế một phụ thuộc mạng trong bootstrap.

Tuy nhiên, **bin không đồng nghĩa với build offline**: nếu Maven distribution yêu cầu chưa có trong cache, Wrapper JAR vẫn cần tải Maven ZIP. Sau đó Maven vẫn có thể cần tải plugin và dependency.

Điểm đánh đổi là repository chứa một file nhị phân phải được quản lý, cập nhật và kiểm tra nguồn gốc.

### 3.4. source: giữ Java downloader thay cho JAR nhị phân

**source** đưa **MavenWrapperDownloader.java** vào repository. Nếu cần tải Wrapper JAR và không có đường tải bằng curl/wget phù hợp, script có thể biên dịch rồi chạy Java downloader làm phương án dự phòng. Sau khi có JAR, quy trình chuẩn bị Maven giống nhóm có JAR.

Ưu điểm: tránh commit sẵn Wrapper JAR và vẫn có phương án tải JAR bằng Java. Điều kiện là **JDK và công cụ biên dịch Java** khả dụng khi cần đường dự phòng; chỉ có Java runtime không bảo đảm biên dịch được downloader. Một số giới hạn về proxy, chứng chỉ, xác thực hoặc mạng vẫn áp dụng.

**source không có nghĩa Maven sẽ được biên dịch từ mã nguồn**: chỉ đoạn downloader của Wrapper có thể được biên dịch; Maven distribution được tải thông thường vẫn là gói Maven đã phát hành.

## 4. Tạo hoặc đổi dạng Wrapper

Để **thêm** Wrapper cho dự án chưa có Wrapper, người thiết lập cần môi trường có Maven để gọi Maven Wrapper Plugin. Chạy ở thư mục có **pom.xml**:

~~~bash
# Tạo kiểu mặc định hiện hành
mvn wrapper:wrapper

# Hoặc chỉ định rõ một kiểu; đây là các lựa chọn thay thế nhau
mvn wrapper:wrapper -Dtype=only-script
mvn wrapper:wrapper -Dtype=script
mvn wrapper:wrapper -Dtype=bin
mvn wrapper:wrapper -Dtype=source
~~~

Chỉ chạy **một lệnh tương ứng với kiểu muốn dùng**; không cần chạy tuần tự cả bốn dòng cho một dự án.

Có thể chọn phiên bản Maven cố định ngay khi tạo Wrapper, ví dụ một bản Maven 3.x cụ thể:

~~~bash
mvn wrapper:wrapper -Dtype=only-script -Dmaven=3.9.9
~~~

Sau khi các file Wrapper được sinh ra và commit, thành viên khác có thể dùng **./mvnw** hoặc **.\mvnw.cmd** mà không cần tự cài Maven CLI toàn cục. Điều kiện Java/JDK và kết nối/cache vẫn cần được đáp ứng.

Nếu chạy goal trên dự án đã có Wrapper, plugin hiện hành có thể giữ **distributionType** đang cấu hình; truyền **-Dtype=...** khi thực sự muốn thay đổi kiểu. Sau khi đổi, hãy xem lại thay đổi Git: chuyển từ **bin** sang **only-script** có thể dẫn đến bỏ file Wrapper JAR; chuyển từ **only-script** sang **source** cần giữ file downloader tương ứng. Tránh giữ nhầm file thừa và tránh xóa file do dự án sử dụng.

Lưu vào Git các script, properties và **các thành phần cần thiết cho dạng đã chọn**; không đưa toàn bộ thư mục cache **~/.m2/wrapper/dists/** hoặc **~/.m2/repository/** vào Git. Trên Unix, script **mvnw** cần có quyền thực thi; hãy bảo đảm executable bit được lưu trong Git.

## 5. Maven tải những gì khi chạy Wrapper lần đầu?

Một cách hiểu đúng là tách tải thành các lớp:

~~~text
Người dùng: ./mvnw clean verify
               |
               v
[1] Chạy script mvnw / mvnw.cmd
               |
               v
[2] Chuẩn bị thành phần Wrapper (tùy loại)
    only-script: không dùng Wrapper JAR
    script: tải Wrapper JAR nếu thiếu
    bin: dùng Wrapper JAR đã commit
    source: tải Wrapper JAR; có Java downloader dự phòng
               |
               v
[3] Xác định Maven distribution theo distributionUrl
    Cache hợp lệ? -- có --> dùng Maven đã tải
        |
       không
        v
    Tải Maven ZIP và giải nén vào wrapper cache
               |
               v
[4] Khởi chạy đúng bản Apache Maven
               |
               v
[5] Maven chạy goal/lifecycle theo pom.xml
    Có thể tải Maven plugins, POM, dependencies vào local repository
~~~

### Trường hợp A: máy mới hoàn toàn, có mạng

Với **only-script**, lần đầu thường tải Maven ZIP rồi giải nén và chạy Maven. Với **script** hoặc **source**, có thể phải tải thêm Wrapper JAR trước khi tải Maven. Với **bin**, JAR đã nằm trong repository nên thường chỉ còn lượt tải Maven distribution. Khi chạy **clean verify**, Maven cũng có thể tải các plugin, parent POM và dependencies cần cho dự án.

Các lượt tải phụ thuộc cache và cấu hình thực tế, nên không có một số lượng HTTP request cố định áp dụng cho mọi dự án.

### Trường hợp B: chạy lại trên cùng máy với cache còn nguyên

Khi Maven distribution đúng URL/phiên bản đã có trong **wrapper/dists**, Wrapper thường tái sử dụng thay vì tải mỗi lần. Maven cũng tái sử dụng các artifact phù hợp trong **~/.m2/repository/**, nếu chúng đã được tải và vẫn hợp lệ theo chính sách cập nhật.

Nếu đổi **distributionUrl** hoặc đổi bản Maven, xóa cache, đổi tài khoản người dùng hay chuyển sang CI runner mới, lượt tải có thể lại xuất hiện. Các tùy chọn cấu hình buộc tải/giải nén lại cũng có thể thay đổi hành vi.

### Trường hợp C: môi trường hoàn toàn không có Internet

**Không nên kỳ vọng Wrapper lần đầu sẽ chạy offline chỉ vì đã commit script.** Cần có sẵn Maven distribution đúng phiên bản/URL, các thành phần Wrapper cần thiết và các plugin/dependencies Maven sẽ dùng.

Tùy dạng Wrapper, chuẩn bị trước có thể là: cho phép truy cập mirror nội bộ, prewarm cache của runner, cung cấp artifact đã phê duyệt qua image CI, hoặc phân phối bản Maven phù hợp theo quy trình nội bộ. **-o** là chế độ offline của Maven khi Maven đã chạy; nó không tự tạo ra Maven distribution hay Wrapper JAR còn thiếu trong bước bootstrap.

## 6. File maven-wrapper.properties quyết định lượt tải

Ví dụ cấu hình **only-script** dùng bản Maven 3.9.9:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionType=only-script
~~~

Hai thuộc tính trên có ý nghĩa khác nhau:

- **distributionUrl** là địa chỉ của **Maven distribution** (gói Maven thực sự). Đây là đầu vào quan trọng khi Wrapper cần tải Maven.
- **distributionType** là kiểu Wrapper dùng để bootstrap; kiểu này cũng được Maven Wrapper Plugin xét khi cập nhật Wrapper. Script cũ và mới có thể có khả năng hỗ trợ khác nhau, vì vậy phải kiểm tra file thực tế được sinh bởi plugin phù hợp.

Các thuộc tính hữu ích khác khi thích hợp:

| Thuộc tính | Ý nghĩa | Khi nào quan trọng? |
| --- | --- | --- |
| **wrapperUrl** | URL lấy **maven-wrapper.jar** | **script/source** khi JAR chưa có; không cần cho cơ chế tải Maven trực tiếp của **only-script** |
| **wrapperSha256Sum** | SHA-256 kỳ vọng của Wrapper JAR | Kiểm tra file JAR tải về/được dùng, khi kiểu có JAR hỗ trợ xác minh |
| **distributionSha256Sum** | SHA-256 kỳ vọng của Maven distribution | Xác thực gói Maven tải về trước khi dùng |
| **distributionUrl** | URL Maven ZIP | Thiết lập phiên bản, nguồn tải hoặc mirror đã được phê duyệt |

**Không dùng một chuỗi checksum tự nghĩ ra**: giá trị SHA-256 phải được lấy từ nguồn phát hành đáng tin cậy và đối chiếu với đúng binary/phiên bản. Khi chỉnh URL hoặc nâng bản Maven, checksum của gói tương ứng cũng phải được cập nhật chính xác. Không lưu token hay mật khẩu trực tiếp trong URL được commit vào repository.

Tên **wrapperUrl** và **distributionUrl** phản ánh *hai thứ khác nhau*: một bên là chương trình bootstrap **Wrapper JAR**, một bên là bộ công cụ **Maven** sẽ chạy dự án.

## 7. Yêu cầu môi trường cho từng dạng và cách xử lý mạng

### 7.1. Java/JDK và script

- **Mọi dạng** đều cần Java/JDK tương thích để Maven hoạt động. Nếu dự án biên dịch Java 17, runner cần JDK đủ để thực hiện yêu cầu build, độc lập với việc đã có Maven hay chưa.
- **only-script** thường dùng **curl/wget** trên Unix-like hoặc **PowerShell** trên Windows cho phần tải Maven; cần công cụ tương ứng cùng khả năng kết nối HTTPS.
- **script** có nhu cầu tải Wrapper JAR trước nếu không có JAR.
- **source** có đường dự phòng dùng Java downloader, nên JDK và **javac** quan trọng khi phải đi theo đường này.
- **bin** giảm yêu cầu tải Wrapper JAR nhưng không loại bỏ yêu cầu tải Maven distribution khi cache trống.

Không nên suy ra **bin** sẽ dùng được mà không có công cụ mạng: JAR cũng cần phương tiện HTTP/HTTPS hoạt động để tải Maven ZIP. Trên Unix cần shell tương thích để chạy script; trên Windows có thể dùng **mvnw.cmd** thay cho **mvnw**.

### 7.2. Kho nội bộ, proxy và chứng chỉ

Mạng doanh nghiệp có thể chặn Maven Central, giới hạn domain, yêu cầu proxy hoặc xác thực. Cần tách đường tải Maven của Wrapper khỏi đường tải dependencies của Maven:

- Đối với **bootstrap**, kiểm tra URL trong **maven-wrapper.properties** (**distributionUrl**, và **wrapperUrl** nếu dạng dùng JAR). Có thể trỏ về kho/mirror HTTPS nội bộ đã được cho phép.
- Tài liệu Maven Wrapper cũng mô tả biến **MVNW_REPOURL** để hỗ trợ dùng repository manager nội bộ. Hành vi cụ thể phụ thuộc phiên bản script/plugin; cấu hình URL rõ ràng và kiểm thử trong cùng môi trường CI sẽ dễ truy vết hơn.
- Đối với **dependency/plugin resolution sau bootstrap**, Maven thường dùng các repository khai báo và mirror trong **settings.xml**. Một mirror Maven dependency đúng **chưa bảo đảm** shell Wrapper tải được ZIP Maven trước khi Maven khởi động.
- Nếu repository yêu cầu Basic Auth, Wrapper có hỗ trợ **MVNW_USERNAME** và **MVNW_PASSWORD** cho các đường tải được hỗ trợ. Đưa secret qua cơ chế quản lý bí mật của CI; không commit credentials vào properties hoặc log.

Một bản build có thể thất bại do **không tải được Maven distribution** ngay cả khi thư mục **~/.m2/repository/** chứa rất nhiều dependencies; và ngược lại, Maven đã tải sẵn nhưng thiếu dependencies thì goal vẫn có thể lỗi ở giai đoạn Maven.

### 7.3. Vị trí cache

Thông thường Wrapper lưu bản phân phối Maven đã tải dưới **~/.m2/wrapper/dists/** (đối với user hiện tại). Biến môi trường **MAVEN_USER_HOME** có thể đổi vị trí gốc dùng để lưu Maven distribution của Wrapper theo hướng dẫn của Apache. Vị trí thực tế có thể khác do hệ điều hành, tài khoản, biến môi trường hoặc phiên bản script.

Cache **Maven distributions** khác với **~/.m2/repository/**, vốn lưu dependency/plugin/POM đã được Maven phân giải. Khi tối ưu CI, cần xác định rõ đang cache loại nào; chỉ cache repository dependency không bảo đảm loại bỏ lượt tải Maven ZIP.

## 8. Ví dụ thực hành và các kết quả cần quan sát

### 8.1. Chuẩn bị một dự án có Maven Wrapper

Giả sử máy người thiết lập đã có Maven tương thích. Từ thư mục dự án có **pom.xml**, tạo **only-script** và khóa Maven ở phiên bản 3.9.9:

~~~bash
mvn wrapper:wrapper -Dtype=only-script -Dmaven=3.9.9
~~~

Kiểm tra các file được tạo: **mvnw**, **mvnw.cmd**, **.mvn/wrapper/maven-wrapper.properties**. Với **only-script**, không kỳ vọng xuất hiện **maven-wrapper.jar** hoặc **MavenWrapperDownloader.java** chỉ để bootstrap.

Sau đó chạy:

~~~bash
./mvnw -v
./mvnw test
~~~

Dòng **Apache Maven** trong kết quả **-v** phải phản ánh phiên bản cấu hình nếu Wrapper tải/chọn thành công; thông tin Java runtime cũng được in theo môi trường thực tế. Không có một stdout bất biến cho mọi hệ điều hành/JDK vì đường dẫn cài đặt, thông tin máy và log tải xuống khác nhau.

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd -v
.\mvnw.cmd test
~~~

Nếu muốn đổi sang **bin** hoặc **source**, chạy lại lệnh tạo Wrapper với **-Dtype=bin** hoặc **-Dtype=source**, xem diff repository và kiểm tra thành phần tương ứng. Chọn một kiểu và commit kết quả hợp lệ trước khi đồng đội sử dụng.

### 8.2. Đánh giá lượt “cold start” với cache trống

Trong một runner/tài khoản thử nghiệm không có cache, cần quan sát theo thứ tự:

1. **Loại Wrapper** và bộ file thực tế: chỉ script hay có JAR/downloader?
2. **URL được truy cập trước**: Wrapper JAR (nếu cần), hay Maven distribution?
3. **Gói Maven đã tải, đã giải nén và sử dụng phiên bản đúng chưa?**
4. **Maven đã khởi động chưa?** Chỉ sau mốc này mới đánh giá lỗi plugin/dependency của **pom.xml**.
5. **Chạy lần hai** có tái sử dụng Maven distribution hay tải lại vì URL/phiên bản/cache khác nhau?

Có thể bật thông tin verbose của Wrapper trong môi trường thử nghiệm:

~~~bash
MVNW_VERBOSE=true ./mvnw -v
~~~

~~~powershell
$env:MVNW_VERBOSE = 'true'
.\mvnw.cmd -v
~~~

Thông tin verbose hỗ trợ xác định bước đang xử lý, nhưng không thay thế việc xem HTTP status, log CI hoặc cấu hình mạng khi lỗi tải.

### 8.3. Phân biệt hai giai đoạn thất bại

**Tình huống 1: -v còn không chạy được, Maven chưa in phiên bản.** Tập trung vào script, Java, download Wrapper JAR, URL Maven distribution, network/proxy/chứng chỉ và cache.

**Tình huống 2: -v thành công, nhưng clean verify lỗi “Could not resolve...”** Maven đã khởi động; tập trung vào repository/plugin/dependency, **pom.xml**, **settings.xml**, xác thực repo hoặc khả năng mạng của Maven Resolver. Đây là lỗi ở giai đoạn khác.

## 9. Bảng chẩn đoán các sự cố phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra đúng |
| --- | --- | --- |
| **./mvnw: Permission denied** | Script chưa được đánh dấu executable trên Unix | Kiểm tra file mode; sửa và lưu executable bit vào Git |
| **mvnw: command not found** | Chạy sai cú pháp, sai thư mục hoặc script không có | Trên Unix dùng **./mvnw** tại thư mục chứa script; Windows PowerShell dùng **.\mvnw.cmd** |
| **Không tải được maven-wrapper.jar** | Dạng **script/source** thiếu JAR, URL không truy cập được hoặc downloader thiếu công cụ | Kiểm tra **wrapperUrl**, script, mạng và điều kiện Java downloader khi là **source** |
| **HTTP 401/403** | Repo yêu cầu quyền, credentials sai hoặc policy chặn | Xác minh URL đích và secret/mirror được phép |
| **HTTP 404** | URL sai hoặc bản Maven/Wrapper JAR không tồn tại tại nguồn | Đối chiếu **distributionUrl/wrapperUrl** với artifact thực tế |
| **HTTP 429** | Repository áp dụng rate limit | Kiểm tra quota, dùng mirror/cache nội bộ và chính sách retry của hệ thống chạy; không giả định Maven đã khởi chạy |
| **Timeout / TLS handshake / SSL certificate** | Network, proxy, CA/chứng chỉ không phù hợp | Kiểm tra đường HTTPS riêng của bootstrap và Java/plugin nếu cần |
| **Có Wrapper JAR nhưng vẫn tải Maven** | **bin** chỉ mang theo bootstrap JAR; Maven distribution chưa cache | Kiểm tra **distributionUrl** và **wrapper/dists** |
| **Chạy được online nhưng lỗi offline** | Cache Maven distro hoặc dependency/plugin còn thiếu | Chuẩn bị đủ cả cache Wrapper distribution lẫn Maven local repository |
| **Chạy lệnh mvn cho kết quả khác ./mvnw** | **mvn** trên PATH khác phiên bản được Wrapper pin | So sánh **mvn -v** với **./mvnw -v** và properties |
| **Lỗi checksum** | File tải khác dữ liệu đã phê duyệt hoặc checksum cấu hình không khớp | Kiểm tra nguồn tải, SHA-256 chính thức, bản Maven/Wrapper tương ứng; không vô hiệu kiểm tra một cách tùy tiện |

**Không “chữa” lỗi tải bằng việc xóa bừa cache trên runner đang dùng chung**. Trước hết xác định bước nào lỗi, bản phân phối nào bị ảnh hưởng và cơ chế cache của CI. Nếu cần làm sạch cache, thử trên môi trường riêng có thể tái tạo.

## 10. Quyết định chọn dạng Wrapper và checklist bàn giao cho CI

**Chọn only-script** khi runner có tiện ích tải HTTPS phù hợp, muốn repository gọn và chấp nhận tải Maven distribution khi chưa có cache.

**Chọn script** khi muốn dùng cơ chế Wrapper JAR nhưng không đưa JAR nhị phân vào Git; cần dự tính bước tải thêm chính JAR đó.

**Chọn bin** khi tổ chức cho phép lưu một Wrapper JAR đã được xác minh trong Git, giúp giảm một yêu cầu download lúc bootstrap; vẫn cần mạng/cache cho Maven và dependencies.

**Chọn source** khi tổ chức tránh commit JAR và muốn giữ Java downloader như đường dự phòng; cần kiểm tra sẵn JDK/biên dịch và yêu cầu mạng.

Trước khi bàn giao dự án hoặc cấu hình pipeline:

1. **Commit đầy đủ** các script và **maven-wrapper.properties**; commit JAR hoặc downloader đúng theo dạng đã chọn, cùng executable bit của **mvnw**.
2. **Khóa phiên bản** bằng **distributionUrl** được xét duyệt; không phụ thuộc vô tình vào phiên bản **mvn** trên máy người chạy.
3. **Cung cấp JDK phù hợp** với phiên bản Maven và yêu cầu biên dịch dự án. Wrapper không đảm nhiệm việc cài JDK.
4. **Thiết lập đường tải** Wrapper JAR (nếu cần), Maven distribution và dependency/plugin; xác định nơi lưu cache và quyền ghi.
5. **Cân nhắc checksum SHA-256** của Wrapper JAR/Maven ZIP, xác minh binary từ nguồn đáng tin, và giữ secrets ngoài repository.
6. **Thử clean runner** để xác nhận cold start, rồi thử chạy lại để quan sát cache. Nếu cần offline, thử thêm trong runner offline đã được chuẩn bị đầy đủ.
7. **Kiểm tra -v trước goal build** để phân định lỗi bootstrap với lỗi dependency hoặc mã nguồn.
8. **Ghi hướng dẫn chính xác cho từng OS**: **./mvnw** cho Unix-like, **.\mvnw.cmd** cho PowerShell hoặc **mvnw.cmd** khi chạy trong Windows Command Prompt từ thư mục dự án.

Ba câu hỏi tự kiểm tra giúp tránh nhầm lẫn:

- **Dạng Wrapper này cần Wrapper JAR không?** **only-script** không; **script/source/bin** có.
- **Wrapper JAR có sẵn thì còn phải tải Maven không?** Có, nếu Maven distribution đúng phiên bản chưa có trong cache.
- **Maven distribution đã có thì build đã offline được chưa?** Chưa chắc: Maven vẫn có thể thiếu plugin, parent POM hoặc dependency để chạy goal.

## Tài liệu tham khảo

- [Apache Maven Wrapper — Tổng quan, cách dùng, tải Maven và checksum](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Wrapper Plugin — Usage, bốn dạng Wrapper](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html)
- [Apache Maven Wrapper Plugin — wrapper:wrapper goal và thuộc tính](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html)
