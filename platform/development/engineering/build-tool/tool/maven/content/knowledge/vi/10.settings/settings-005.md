# mirrors, mirrorOf và điều hướng truy cập kho trong Maven

## 1. Vấn đề cần giải quyết

Maven cần tải **dependency**, **plugin**, metadata phiên bản và đôi khi parent POM từ các **remote repositories**. Theo mặc định, một dự án Maven thông thường có thể truy cập Maven Central. Trong công ty, nhóm phát triển thường muốn mọi lượt tải đi qua một **repository manager nội bộ** như Nexus hoặc Artifactory để cache, kiểm soát nguồn, thực thi chính sách và dùng thông tin xác thực tập trung.

**Mirror** là quy tắc trong **settings.xml** nói với Maven: khi chuẩn bị truy cập một remote repository nào đó, hãy dùng một địa chỉ kho khác thay cho kho gốc. **mirrorOf** xác định **repository ID nào** bị thay thế.

Ví dụ: POM hoặc Super POM cung cấp repository có **id=central**, URL **https://repo.maven.apache.org/maven2/**; settings.xml có mirror với **mirrorOf=central** và URL đến repository manager. Maven chuyển yêu cầu tải của repository **central** đến URL mirror; người viết POM không cần thay tọa độ dependency.

Ba điều quan trọng ngay từ đầu:

1. **Mirror không phải khai báo thêm một repository ứng viên.** Với một repository ID được mirror, Maven chọn **một mirror** theo quy tắc khớp; nếu mirror đó không phục vụ artifact mong muốn, Maven không tự thử mọi mirror khác cho cùng repository.
2. **mirrorOf khớp theo ID của repository gốc**, không phải groupId/artifactId của dependency, không phải tên host tùy ý và không phải ID của bản thân mirror.
3. **Mirror dùng cho việc tải/giải quyết artifact**, không mặc nhiên chuyển hướng nơi **deploy** được cấu hình bằng **distributionManagement**.

Bài học này tập trung vào cơ chế mirror, cách dùng mirrorOf, quan hệ giữa repository manager với settings, khả năng xác thực và cách chẩn đoán khi truy cập nhầm kho.

## 2. Các khái niệm và luồng truy cập

Phân biệt các đối tượng Maven thường dùng:

| Đối tượng | Nơi cấu hình thường gặp | Vai trò |
| --- | --- | --- |
| **Remote repository** | POM, parent POM, profile, Super POM hoặc settings profile | Nguồn Maven được phép dùng để giải quyết artifact. Có **id** và **url**. |
| **Plugin repository** | **pluginRepositories** trong POM/profile | Nguồn giải quyết Maven plugin và dependency của plugin. |
| **Mirror** | **mirrors** trong **settings.xml** | Thay URL/đích truy cập cho các repository khớp **mirrorOf**. |
| **Repository manager** | Dịch vụ máy chủ như Nexus/Artifactory | Proxy/cache hoặc hợp nhất nhiều remote repository và kho hosted qua một endpoint. |
| **Local repository** | Thường **~/.m2/repository/** | Cache artifact trên máy chạy Maven; **không phải** remote mirror. |
| **Server** | **servers** trong settings.xml | Username/password/token hoặc cơ chế xác thực để kết nối repository theo **id**. |
| **Proxy** | **proxies** trong settings.xml, nếu cần | Cấu hình HTTP(S) proxy ở tầng mạng; khác với cơ chế mirror chọn Maven repository. |

Luồng đơn giản:

~~~text
POM / parent / Super POM / settings profile
    |
    | cung cấp repository id=central
    v
Maven cần tải dependency hoặc plugin
    |
    v
Maven xét danh sách mirrors trong effective settings
    |
    +-- có mirror khớp? -- CÓ --> chuyển tới URL của mirror
    |                              (nếu cần, dùng server credentials theo mirror id)
    |
    +-- KHÔNG ------------------> truy cập URL repository gốc
    |
    v
Local repository cache artifact đã giải quyết
    |
    v
Compiler / test / package / plugin goal sử dụng artifact
~~~

**Repository manager** có thể đứng sau một mirror; bản thân Maven **không tự tổng hợp nhiều repository vào một endpoint**. Nếu muốn một mirror phục vụ Central, kho bên thứ ba, bản release và snapshot của công ty, endpoint của repository manager phải được cấu hình phục vụ các nguồn tương ứng.

## 3. Mirror được khai báo ở đâu?

Trong Maven 3.x, settings của người dùng thường ở **~/.m2/settings.xml**; global settings thuộc thư mục **conf/** của bản Maven đang chạy. Maven có thể được yêu cầu dùng file user settings riêng bằng **-s path/to/settings.xml**, hoặc global settings riêng bằng **-gs**. Hai lớp settings được Maven hợp nhất theo các quy tắc hiệu lực.

**Phần tử mirrors là một phần trực tiếp của settings.xml**, không đặt trong **pom.xml** và không phải phần tử con của một **profile**.

Một tệp settings.xml tối giản, đúng cấu trúc:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>corp-central</id>
            <name>Company proxy for Maven Central</name>
            <url>https://repo.example.com/repository/maven-central/</url>
            <mirrorOf>central</mirrorOf>
        </mirror>
    </mirrors>
</settings>
~~~

**https://repo.example.com/repository/maven-central/** là URL **minh họa**, không phải dịch vụ kho đã được cung cấp. Khi triển khai thật, thay bằng HTTPS endpoint **có thật và được quản trị tin cậy**. Mẫu minh họa không thể tự tải dependency nếu URL đó không tồn tại trong mạng của bạn.

Ý nghĩa từng trường:

- **id=corp-central**: ID mới của mirror, dùng để nhận diện endpoint được chọn và tra thông tin xác thực trong **servers**.
- **url**: URL Maven sẽ thực sự truy cập khi repository gốc được match.
- **mirrorOf=central**: chỉ chọn mirror này khi repository gốc có ID chính xác **central**.
- **name**: tên dễ đọc, tùy chọn.

Không đặt **id** của mirror trùng với repository gốc có ID **central**. Giữ ID mirror độc lập giúp tránh nhầm danh tính repository và giúp cấu hình server credentials rõ ràng.

**Khi nào dùng cấu hình này?** Khi nhóm chỉ muốn chuyển hướng Maven Central sang một proxy nhưng cho phép các repository với ID khác tiếp tục dùng URL gốc.

## 4. Repository ID là chìa khóa của mirrorOf

Trong Maven, repository có **id** và **url**. Ví dụ repository do một POM cấu hình:

~~~xml
<repositories>
    <repository>
        <id>partner-releases</id>
        <url>https://packages.example.org/maven/releases/</url>
    </repository>
</repositories>
~~~

Đây là **đoạn POM**, cần đặt bên trong **project**. Địa chỉ **packages.example.org** chỉ minh họa một remote repository khác; khả năng tải artifact phụ thuộc server thực tế.

Nếu mirrorOf là **central**, repository **partner-releases** **không bị mirror** vì ID không khớp. Nếu mirrorOf là **partner-releases**, Maven chuyển hướng repository đó, bất kể phần host URL có chứa từ "central" hay không.

**Không nhầm repository ID với artifact coordinates**:

- **groupId:artifactId:version** như **org.apache.commons:commons-lang3:3.14.0** nhận diện một artifact.
- **repository id** như **central** hoặc **partner-releases** nhận diện một nguồn artifact.
- **mirror id** như **corp-central** nhận diện endpoint thay thế và là khóa ghép với **servers/server/id** khi cần xác thực.

Một mirror có thể ảnh hưởng đến việc tải nhiều artifact khác nhau từ cùng repository, không chỉ một groupId hoặc một plugin.

## 5. Cú pháp mirrorOf cơ bản và nâng cao

Maven hỗ trợ cả ID chính xác và các biểu thức chọn nhiều repository:

| Giá trị mirrorOf | Ý nghĩa |
| --- | --- |
| **central** | Chỉ repository có **id=central**. |
| **partner-releases** | Chỉ repository có **id=partner-releases**. |
| **central,partner-releases** | Hai repository có ID được liệt kê. |
| ***** | Tất cả các **remote repository IDs** mà Maven xét, bao gồm repository sử dụng URL file hoặc localhost nếu không có ngoại lệ. |
| **external:*** | Các repository **không phải localhost và không dùng URL file**. |
| **external:http:*** | Các repository **HTTP bên ngoài localhost**; hữu ích để nhận diện/chặn nguồn HTTP không an toàn. Hỗ trợ từ Maven 3.8.0. |
| ***,!corp-hosted** | Tất cả repository **trừ** repository có ID **corp-hosted**. |
| **external:*,!corp-hosted** | Chỉ các repository external, đồng thời loại **corp-hosted**. |
| **central,partner-releases,!corp-hosted** | Chọn các ID được liệt kê, loại ID nêu sau dấu **!**. |

**Chú ý:** trong nội dung XML thực tế, các mẫu ***** được viết bằng dấu ***** bình thường, không phải biểu thức regex. Dấu **!** loại một repository ID, dấu phẩy phân tách các phần của expression. **Không có quy tắc regex tùy ý** hoặc cú pháp glob tự do để matching repository ID.

Đặc biệt phải tránh khoảng trắng quanh các token. Tài liệu Maven nêu ví dụ:

- **<mirrorOf>!repo1,*</mirrorOf>**: match mọi repository trừ **repo1**.
- **<mirrorOf>!repo1, *</mirrorOf>**: khoảng trắng trước ***** làm token không còn khớp theo cú pháp mong muốn, có thể khiến mirror **không được chọn**.

Vì vậy hãy dùng **external:*,!corp-hosted** hoặc ***,!corp-hosted**, không chèn khoảng trắng sau dấu phẩy.

### external không có nghĩa “ở ngoài mạng công ty”

Trong **external:***, khái niệm **external** dựa vào cách Maven phân loại repository URL: không phải localhost và không phải **file:**. Một repository nội bộ có hostname **repo.company.internal** vẫn có thể khớp **external:***. Nếu muốn không redirect kho đó, hãy loại theo **repository ID** bằng **!repo-id**.

Ví dụ repository dùng **file:///...** cho kiểm thử cục bộ hoặc một server chạy trên localhost thường được loại khỏi **external:***, nhưng vẫn có thể bị chọn bởi ***** nếu không cấu hình ngoại lệ.

### external:http:* để kiểm soát repository HTTP

Mẫu **external:http:*** nhắm các repository **HTTP bên ngoài localhost**; nó **không** match các repository HTTPS một cách tổng quát. Đây là mẫu được Maven dùng trong chính sách bảo vệ khỏi HTTP không an toàn. Không dùng **external:http:*** khi mục đích thực sự là mirror toàn bộ repository HTTPS và HTTP bên ngoài localhost; khi đó xét **external:***.

## 6. Thứ tự ưu tiên khi có nhiều mirror

Một repository cụ thể chỉ được Maven chọn **một mirror**. Quy tắc lựa chọn quan trọng:

1. Maven ưu tiên mirror có **mirrorOf khớp chính xác repository ID** (ví dụ **mirrorOf=central** cho repository central).
2. Nếu không có khớp trực tiếp, Maven xét các biểu thức/pattern như **external:***, *****, danh sách và ngoại lệ; mirror phù hợp **đầu tiên theo thứ tự khai báo** được chọn.
3. Khớp loại trừ như **!corp-hosted** giúp pattern không chọn repository tương ứng.
4. Nếu không có mirror phù hợp, Maven sử dụng URL repository gốc, trừ các chính sách/mirror khác từ effective settings.

Ví dụ đặt hai mirror trong settings theo thứ tự sau:

~~~xml
<mirrors>
    <mirror>
        <id>company-all</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <mirrorOf>external:*</mirrorOf>
    </mirror>
    <mirror>
        <id>company-central</id>
        <url>https://repo.example.com/repository/maven-central/</url>
        <mirrorOf>central</mirrorOf>
    </mirror>
</mirrors>
~~~

Dù **company-all** đứng trước, repository ID **central** vẫn được chọn bởi mirror **company-central** vì **central là khớp trực tiếp**. Một repository khác như **partner-releases** sẽ match **external:*** (nếu URL là external) và được gửi đến **company-all**.

Nếu thay mirror thứ hai bằng một pattern rộng như *****, cả hai mirror có thể khớp repository external. Khi đó thứ tự khai báo giữa những pattern sẽ quan trọng. Đừng giả định Maven tự chia tải, thử lần lượt nhiều mirror hoặc gộp danh sách nội dung của các endpoint.

**Bài toán chọn repository và chọn mirror là hai tầng khác nhau:** Maven trước hết có một tập repository có thể cung cấp artifact, sau đó mirror selector xác định endpoint thay thế khi truy cập từng repository. Một kho gốc không có artifact không tự biến thành mọi kho còn lại chỉ vì dùng dấu *****.

## 7. Ví dụ thực tế: mirror tất cả repository external qua repository manager

Khi công ty có một **repository manager group/proxy** phục vụ những remote repository đã được nhóm quản trị cho phép, cấu hình phổ biến:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <mirrors>
        <mirror>
            <id>company-maven</id>
            <name>Approved Maven repository manager</name>
            <url>https://repo.example.com/repository/maven-public/</url>
            <mirrorOf>external:*,!corp-hosted</mirrorOf>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>company-maven</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

**Đây là settings minh họa về cơ chế**, cần thay endpoint bằng repo manager HTTPS có thật, và cấp biến môi trường bằng cơ chế secrets an toàn của máy/CI. Không lưu token thật trong bài viết hoặc commit file settings chứa token vào Git. Nếu repository manager cho phép đọc không cần đăng nhập, có thể **bỏ phần servers**.

Trong ví dụ:

- Repository **central** được gửi tới **company-maven** vì khớp **external:***.
- Repository có ID **thirdparty** dùng HTTPS bên ngoài localhost cũng được gửi tới **company-maven**.
- Repository có ID **corp-hosted** được loại bởi **!corp-hosted**, nên vẫn dùng URL của chính repository đó nếu không có mirror phù hợp khác.
- Repository **file:** hoặc **localhost** không khớp **external:***.
- Username/token tra theo **server id=company-maven**, tức **ID của mirror**, chứ không phải **central**.

**Quan trọng:** **corp-hosted** trong ví dụ chỉ là một **repository ID** được loại trừ. Muốn Maven thật sự truy cập kho đó, nó phải được khai báo trong repository configuration tương ứng (POM, profile hoặc nơi hợp lệ khác). Dấu **!corp-hosted** không tự tạo repository mới.

### Mirror cho toàn bộ repository với dấu *

Nếu repository manager là điểm vào duy nhất và có đủ artifact cho cả thư viện lẫn plugin, có thể dùng:

~~~xml
<mirror>
    <id>company-maven</id>
    <url>https://repo.example.com/repository/maven-public/</url>
    <mirrorOf>*</mirrorOf>
</mirror>
~~~

Lựa chọn này rất rộng, bao gồm cả những repository sử dụng URL **file:** hoặc localhost theo quy tắc ID. Nó có thể phá workflow kiểm thử với repository cục bộ và các nguồn riêng mà repository manager không proxy. Vì vậy **chỉ dùng *** khi nhóm thực sự muốn và đã kiểm tra các ngoại lệ. Nếu cần loại một ID, dùng ***,!id**; nếu muốn giữ file/localhost, cân nhắc **external:***.

### Một mirror không phải danh sách fallback

Nếu mirror **company-maven** không chứa một plugin hoặc dependency mà dự án cần, Maven có thể báo lỗi không giải quyết được artifact. **Maven không tự bỏ qua mirror đã được chọn để tìm thử tất cả mirror khác** cho cùng repository.

Cách sửa là cấu hình **repository manager** proxy/aggregate đúng những nguồn được phép, hoặc sửa chính sách mirrorOf để repository có ID cần thiết được truy cập đúng nơi. Đừng tăng số mirror trùng pattern với hy vọng Maven tải vòng tròn hay cân bằng tải tự động.

## 8. Mirrors có ảnh hưởng đến repository nào?

Maven cần phân biệt ít nhất ba kiểu luồng:

| Luồng | Cấu hình gốc | Mirror có thể tác động? |
| --- | --- | --- |
| **Giải quyết dependency** | **repositories** trong POM/parent/profile/Super POM | **Có**, theo repository ID và mirrorOf. |
| **Giải quyết Maven plugin** | **pluginRepositories** và các cấu hình nguồn plugin | **Có**, theo repository ID và mirrorOf. |
| **Deploy artifact của dự án** | **distributionManagement** hoặc cấu hình deploy plugin | **Không mặc nhiên**; mirror không thay thế địa chỉ deploy. |

Đây là nguồn gây nhầm lẫn phổ biến: **mvn dependency:resolve** có thể tải được thư viện, trong khi một goal plugin mới vẫn báo lỗi. Kiểm tra **pluginRepositories** và mirror thực tế áp dụng cho repository plugin. Một mirror với **mirrorOf=central** thường chuyển hướng cả dependency lẫn plugin được lấy từ repository có ID **central**; nhưng các **ID khác** cần match riêng.

Ví dụ đoạn POM minh họa khai báo repository và pluginRepository:

~~~xml
<repositories>
    <repository>
        <id>partner-releases</id>
        <url>https://packages.example.org/maven/releases/</url>
    </repository>
</repositories>
<pluginRepositories>
    <pluginRepository>
        <id>partner-plugins</id>
        <url>https://packages.example.org/maven/plugins/</url>
    </pluginRepository>
</pluginRepositories>
~~~

Đây là **hai repository ID khác nhau**, dù host trông giống nhau. **mirrorOf=partner-releases** không tự match **partner-plugins**. Nếu chính sách là chuyển cả hai, dùng danh sách **partner-releases,partner-plugins** hoặc pattern phù hợp.

Với deployment, Maven thường lấy repository từ **distributionManagement/repository** hoặc **snapshotRepository** và xác thực dựa trên server ID tương ứng với đích deploy. Không sửa **mirrorOf** để giải quyết lỗi **mvn deploy** trước khi kiểm tra địa chỉ deployment và cấu hình xác thực đúng luồng.

## 9. Credentials, server ID và môi trường CI

Nếu mirror yêu cầu xác thực, cấu hình **servers/server/id** phải khớp **mirror/id** mà Maven thực sự sử dụng:

~~~xml
<mirrors>
    <mirror>
        <id>secured-mirror</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <mirrorOf>central</mirrorOf>
    </mirror>
</mirrors>
<servers>
    <server>
        <id>secured-mirror</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
</servers>
~~~

Đoạn này thuộc bên trong **settings**; riêng nó **không phải tệp XML độc lập**. Maven Settings Reference hỗ trợ nội suy biến môi trường trong settings. Trong CI cần thiết lập **MAVEN_REPO_USER** và **MAVEN_REPO_TOKEN** ở đúng tiến trình chạy Maven. Nếu không có biến hoặc token đã hết hiệu lực, có thể gặp HTTP **401/403** dù mirror selection đúng.

**Không lấy thông tin đăng nhập của repository gốc để suy ra server ID cho mirror.** Ví dụ khi repo gốc là **central** nhưng Maven dùng mirror **secured-mirror**, cần server ID **secured-mirror**. Tương tự, nếu một repository có ID **corp-hosted** được loại khỏi mirror, nó có thể cần **server id=corp-hosted** riêng khi truy cập trực tiếp.

**Server credentials** khác **HTTP proxy credentials**. Nếu mạng doanh nghiệp buộc đi qua HTTP proxy, xem **proxies** trong settings; nếu repository manager yêu cầu login, xem **servers**. Trong một build có thể cần cả hai.

**An toàn thông tin:** sử dụng token quyền tối thiểu; cấp secrets từ hệ thống CI/secret store; không commit token vào POM/settings; không công khai **mvn -X** hoặc **help:effective-settings** trước khi kiểm tra dữ liệu nhạy cảm. Không để Maven tải artifact từ endpoint HTTP không được kiểm soát chỉ để tránh lỗi chứng chỉ.

## 10. external:http:*, blocked và chính sách HTTPS

Từ nhánh Maven 3.8.x, Maven bổ sung chính sách phòng tránh repository HTTP không an toàn. Maven 3.8.1 đưa vào cấu hình **maven-default-http-blocker** trong global settings của bản phân phối, thường dùng:

~~~xml
<mirror>
    <id>maven-default-http-blocker</id>
    <mirrorOf>external:http:*</mirrorOf>
    <name>Pseudo repository to mirror external repositories initially using HTTP.</name>
    <url>http://0.0.0.0/</url>
    <blocked>true</blocked>
</mirror>
~~~

Đây là **minh họa cấu hình chặn** có thể thấy trong phân phối Maven 3.8.1+; nội dung và vị trí cụ thể cần kiểm tra trong bản Maven đang chạy. Thuộc tính **blocked=true** báo Maven từ chối request thông qua mirror đó thay vì gửi request tải. **external:http:*** match repository HTTP không phải localhost, **không có nghĩa mọi repo internet đều bị chặn**.

Khi thấy lỗi như:

~~~text
Blocked mirror for repositories: [legacy-repo (http://...)]
~~~

cần hiểu Maven từ chối HTTP endpoint gốc vì quy tắc an toàn. **Không sửa bằng cách tắt blocker một cách mù quáng**. Hướng xử lý là cập nhật repository sang **HTTPS đáng tin cậy**, cấu hình repository manager được phép sử dụng HTTPS hoặc điều chỉnh cấu trúc repository theo chính sách được duyệt.

Nếu **external:*** mirror được đặt để điều hướng mọi kho về một HTTPS repository manager, nó có thể phục vụ luồng truy cập thích hợp. Tuy nhiên cần **kiểm tra hiệu lực mirror selection** khi có cả blocker và nhiều pattern; đừng giả định một pattern rộng luôn thắng pattern khác.

**mirrorOfLayouts** là tùy chọn nâng cao để lọc mirror theo **repository layout** cùng với repository ID. Với những Maven repository hiện đại sử dụng layout **default**, thông thường không cần chỉnh. Nếu làm việc với layout cũ hoặc đặc biệt, xác nhận cấu hình này theo Maven Settings Model của phiên bản đang dùng.

## 11. Cách kiểm tra mirror mà Maven thực sự chọn

Kiểm tra nên thực hiện có thứ tự; đừng xóa cả bộ nhớ đệm Maven chỉ để “thử lại” khi chưa hiểu lỗi.

### Bước 1 — xác nhận bản Maven và settings đang áp dụng

~~~bash
mvn --version
mvn help:effective-settings
~~~

**help:effective-settings** cho biết settings hiệu lực sau khi Maven xử lý cấu hình user/global; xem phần **mirrors**, **servers** và proxy nếu cần. Trên máy khác hoặc CI, settings có thể đến từ file truyền bằng **-s** hoặc **-gs**, hoặc Maven Wrapper chạy bản phân phối khác. Không dựa vào việc file **~/.m2/settings.xml** tồn tại để kết luận Maven chắc chắn đang dùng đúng file.

Nếu muốn kiểm tra một file settings cụ thể:

~~~bash
mvn -s custom-settings.xml help:effective-settings
~~~

**custom-settings.xml** ở đây là file do bạn tự cung cấp với nội dung hợp lệ; không có sẵn trong Maven.

### Bước 2 — chạy một goal thực sự cần tải artifact

Một POM nhỏ chỉ chạy **validate** có thể chưa tải dependency nào, vì vậy có thể **không xuất hiện dòng chọn mirror** trong log. Hãy chọn một goal thực sự giải quyết dependency hoặc plugin, ví dụ:

~~~bash
mvn -B -U -X dependency:resolve
~~~

Tùy Maven/plugin, log debug thường chứa thông tin dạng:

~~~text
Using mirror company-maven (https://repo.example.com/repository/maven-public/) for central (https://repo.maven.apache.org/maven2/).
~~~

Đây là **mẫu minh họa**, không cam kết xuất hiện nguyên văn trong mọi phiên bản. Nó cho thấy Maven chọn **mirror ID** và **URL mirror** cho **repository ID central**. Nếu repository hoặc plugin đã nằm trong cache, có thể có ít lượt tải; **-U** yêu cầu Maven kiểm tra cập nhật theo cơ chế tương ứng, không xóa local repository và không bảo đảm mọi artifact được tải lại.

Dùng **-X** để chẩn đoán khi cần và **không đăng nguyên log công khai** vì log có thể chứa địa chỉ nội bộ và thông tin môi trường.

### Bước 3 — phân biệt chọn mirror và tải thành công

Maven có thể chọn đúng mirror nhưng vẫn thất bại vì:

- repository manager không proxy/host artifact cần thiết;
- credentials không đúng hoặc không có;
- proxy, DNS, TLS/certificate hoặc firewall gây lỗi;
- repository policy không cho phép snapshot/release tương ứng;
- metadata hoặc bộ nhớ đệm có trạng thái cũ;
- group repository chứa thứ tự thành viên hoặc policy sai.

Nếu không có dòng dùng mirror mong muốn, xem lại **mirrorOf**, **ID của repository gốc**, thứ tự giữa các pattern, global/user settings và repository plugin có ID khác repository dependency hay không.

## 12. Ví dụ dự án Java 17 có dependency để quan sát luồng tải

Để thực hành mà không phụ thuộc vào một URL nội bộ giả định, trước hết tạo một dự án Maven chuẩn dùng **Maven Central** khi không có mirror tùy chỉnh; sau đó áp dụng **settings của môi trường bạn có quyền truy cập** và so sánh log.

Cấu trúc:

~~~text
mirror-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/mirror/Hello.java
    └── test/
        └── java/vn/example/mirror/HelloTest.java
~~~

### 12.1. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>mirror-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các plugin và JUnit Jupiter được khai báo phiên bản rõ ràng. Maven phải giải quyết những artifact này và dependency của chúng; nếu đang dùng mirror, đường tải sẽ chịu quy tắc **mirrorOf**. JDK cần hỗ trợ **release 17**.

### 12.2. src/main/java/vn/example/mirror/Hello.java

~~~java
package vn.example.mirror;

public final class Hello {
    private Hello() {
    }

    public static String greeting(String name) {
        return "Xin chào, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(greeting("Maven"));
    }
}
~~~

### 12.3. src/test/java/vn/example/mirror/HelloTest.java

~~~java
package vn.example.mirror;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class HelloTest {
    @Test
    void checksGreeting() {
        assertEquals("Xin chào, Maven!", Hello.greeting("Maven"));
    }
}
~~~

### 12.4. Build, kiểm tra artifact và kết quả Java

Với môi trường có Maven/JDK và truy cập được Maven Central (hoặc mirror được cấu hình đúng):

~~~bash
mvn -B clean verify
java -cp target/mirror-demo-1.0.0.jar vn.example.mirror.Hello
~~~

**Stdout chính xác của riêng lệnh Java thứ hai**:

~~~text
Xin chào, Maven!
~~~

Build sẽ biên dịch Java, thực thi test JUnit phù hợp và đóng gói JAR thông thường. Không dùng **java -jar** cho POM này vì chưa thêm **Main-Class** vào manifest; lệnh **java -cp** chỉ cần JAR chứa lớp Java chính, không cần JUnit trên runtime classpath.

Sau khi đã có **settings.xml hợp lệ trỏ tới repository manager thực tế**, có thể đối chiếu:

~~~bash
mvn -s corp-settings.xml -B -U -X clean verify
~~~

**corp-settings.xml** là tên file cấu hình do người thực hành tự tạo. Nếu sử dụng nguyên URL minh họa **repo.example.com**, lệnh không có bảo đảm truy cập thành công. Mục tiêu ở đây là **so sánh log repository selection**, không phải yêu cầu mọi học viên có cùng hạ tầng công ty.

## 13. Một số bài toán điều hướng theo yêu cầu

### 13.1. Chỉ muốn chuyển Maven Central

Dùng **mirrorOf=central**. Các repository như **partner-releases** hoặc **corp-hosted** có ID khác không bị match bởi mirror này. Phù hợp khi công ty chỉ có cache Maven Central, còn một số kho khác phải giữ URL riêng.

### 13.2. Muốn cache mọi nguồn từ xa, trừ repository test trên localhost

Dùng **mirrorOf=external:*** và cấu hình repository manager làm endpoint thống nhất. Nó thường bỏ qua repository file và localhost. **Không nhầm internal hostname với localhost**.

### 13.3. Muốn mọi nguồn đi qua công ty, nhưng giữ riêng kho hosted

Dùng **mirrorOf=*,!corp-hosted** hoặc **external:*,!corp-hosted**, tùy có muốn bao gồm file/localhost. Đảm bảo kho có ID **corp-hosted** được khai báo riêng; nếu cần credentials, dùng **server id=corp-hosted**.

### 13.4. Muốn chặn HTTP public không an toàn

Dùng cơ chế an toàn mặc định của Maven 3.8.1+ hoặc chính sách **blocked=true** được quản trị thích hợp với **mirrorOf=external:http:***. Ưu tiên chuyển nguồn gốc sang HTTPS hoặc repository manager HTTPS; không tự gỡ blocker.

### 13.5. Muốn “nhiều mirror thay phiên nhau nếu một cái lỗi”

**Không phải chức năng mirrorOf.** Maven không dùng danh sách mirror trong settings làm failover/load balancer cho cùng repository. Hãy dùng một repository manager/endpoint hạ tầng có khả năng cache, retry, high availability hoặc failover theo chính sách của hệ thống.

### 13.6. Muốn deploy artifact vào kho nội bộ

Cấu hình **distributionManagement** và server credentials tương ứng; không mặc định dùng **mirrorOf** để thay URL deploy. Ví dụ POM có **distributionManagement/repository** với ID **corp-deploy**, thì credentials thường nằm dưới **server id=corp-deploy**. Không dùng nhầm ID mirror tải dependency.

## 14. Lỗi thường gặp và hướng sửa

| Triệu chứng | Nguyên nhân có thể | Hành động kiểm tra |
| --- | --- | --- |
| Vẫn tải từ Maven Central thay vì mirror | **mirrorOf** không match ID thực; settings không được nạp; profile/repository ID khác dự kiến. | Kiểm tra effective settings, repo ID và log **Using mirror ... for ...**. |
| Không tải được plugin nhưng dependency tải được | **pluginRepositories** có ID khác hoặc repository manager không proxy plugin/dependency của plugin. | Xem plugin repo ID, URL mirror và artifact báo thiếu. |
| 401 Unauthorized hoặc 403 Forbidden | Server ID không khớp mirror ID, token không được truyền, quyền repository manager không đủ. | Kiểm tra **servers/server/id**, secrets của tiến trình Maven, quyền của account. |
| 404 Not Found cho artifact đã có ở kho khác | Mirror đã chọn endpoint không chứa/không proxy nguồn cần thiết. | Xem group repository, chính sách releases/snapshots, repository ID và exclusions. |
| Blocked mirror for repositories | External HTTP bị chính sách chặn. | Chuyển sang HTTPS/repository manager được phê duyệt; không vô hiệu hóa bảo vệ tùy tiện. |
| Mirror rộng ***** làm hỏng test trên localhost | Pattern ***** chọn cả repo file/localhost. | Dùng **external:*** hoặc thêm ngoại lệ theo ID phù hợp. |
| Quy tắc **!repo1, *** không hoạt động | Có whitespace trong danh sách mirrorOf. | Sửa thành **!repo1,***. |
| Gói snapshot không tìm thấy | Repo manager/mirror không có snapshot hoặc policy chỉ cho release. | Kiểm tra snapshot repository, profile và group member tương ứng. |
| CI khác local dù cùng POM | Khác user/global settings, Maven Wrapper, profile, secrets, proxy hoặc DNS. | So sánh Maven version, settings hiệu lực và log URL đã chọn. |
| Sửa mirrorOf mà kết quả vẫn như cũ | Local cache/metadata có trạng thái cũ; hoặc không có lượt tải mới. | Đọc log debug, xem yêu cầu cập nhật **-U** và cache liên quan; không xóa toàn bộ cache vội. |
| Cố sửa lỗi deploy bằng thay mirror | Deploy dùng distributionManagement/Deploy Plugin. | Kiểm tra deployment URL, server ID và quyền ghi. |
| Kết nối lỗi TLS, PKIX, certificate | JVM không tin certificate, proxy TLS hoặc hostname sai. | Kiểm tra chain, truststore, HTTPS host; không tắt kiểm tra TLS làm cách sửa lâu dài. |

**Đừng đồng nhất “không tìm thấy artifact” với “mirrorOf không match”.** Cần xác nhận từng bước: repository gốc nào, mirror nào đã được chọn, endpoint nào nhận request, và server đó có chứa artifact hay không.

## 15. Checklist trước khi dùng mirror trong dự án hoặc CI

1. **Xác định chính sách nguồn artifact**: Central, kho bên thứ ba, snapshot nội bộ, plugin repository, và kho phục vụ deploy. Phân biệt tải với upload.
2. **Chọn endpoint quản trị tin cậy**: ưu tiên HTTPS repository manager có cache/proxy đúng nguồn, quyền truy cập rõ ràng.
3. **Đặt mirror trong settings.xml**, không đưa credentials vào POM; giữ mirror ID khác repository gốc, đặt **mirrorOf** rõ nghĩa.
4. **Chọn phạm vi vừa đủ**: **central**, danh sách IDs, **external:***, hoặc ***** có ngoại lệ khi thực sự cần. Không cho whitespace trong biểu thức.
5. **Rà soát thứ tự mirror**: direct ID match được ưu tiên; nếu nhiều pattern, thứ tự khai báo quyết định pattern nào thắng.
6. **Thiết lập servers theo mirror ID**; cấu hình secrets cho CI đúng tên và phạm vi, không log token.
7. **Kiểm tra dependency và plugin** bằng một build thực sự giải quyết artifact; chỉ **mvn validate** có thể không tạo yêu cầu tải.
8. **Đọc effective settings và debug log** ở môi trường được phép; so sánh URL mirror đã chọn với thiết kế, kiểm tra status 401/403/404 và lỗi TLS nếu có.
9. **Kiểm tra repository manager** có thể phục vụ tất cả artifact cần thiết, cả release, snapshot và plugin; đừng dùng nhiều mirror như cơ chế fallback.
10. **Duy trì chính sách an toàn HTTP** của Maven; khi gặp blocker, sửa nguồn HTTPS thay vì vượt chặn.
11. **Chạy thử trên CI từ cache sạch có kiểm soát** nếu muốn xác nhận khả năng bootstrap, tránh phụ thuộc artifact cũ trong local repository.
12. **Ghi lại chính sách trong tài liệu dự án**: file settings cần dùng, ID mirror, repository IDs được loại trừ, nơi cấp secrets và cách chẩn đoán.

**Ghi nhớ:** **repositories/pluginRepositories** xác định Maven được phép tìm artifact ở những nguồn nào; **mirrors/mirrorOf** chọn endpoint thay thế **theo repository ID** khi Maven truy cập nguồn; **servers** cung cấp xác thực cho endpoint đã chọn; **repository manager** là nơi thực hiện proxy/cache/group thực sự. Hiểu rõ bốn vai trò này giúp điều hướng truy cập kho một cách có kiểm soát và tránh lỗi tải dependency/plugin khó chẩn đoán.

### Tài liệu chính thức

- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Settings Model: mirror, mirrorOfLayouts, blocked](https://maven.apache.org/ref/3-LATEST/maven-settings/settings.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — CVE-2021-26291 and Maven 3.8.1 release notes](https://maven.apache.org/docs/3.8.1/release-notes.html)
