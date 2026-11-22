# Repository manager, proxy cache và mirror trong tổ chức

## 1. Vì sao nhóm phát triển Maven cần một repository manager?

Một dự án Maven không chỉ tải JAR khai báo trực tiếp trong `pom.xml`. Nó còn cần **parent POM**, dependency bắc cầu, Maven plugin, các dependency của plugin và đôi khi metadata để xác định phiên bản. Nếu mọi laptop, máy CI và môi trường build đều tự truy cập nhiều nguồn Internet, nhóm dễ gặp tình trạng tải lặp, lỗi mạng, quyền truy cập phân tán, phụ thuộc một repository bên ngoài hoặc không biết binary nào đã được đưa vào build.

**Repository manager** là một dịch vụ quản lý kho artifact nhị phân, có khả năng đứng trước các remote repository, **proxy và cache** artifact/metadata, lưu artifact nội bộ và cung cấp một endpoint dùng chung cho nhiều người. Các sản phẩm thường gặp gồm **Sonatype Nexus Repository** và **JFrog Artifactory**; tên chức năng và đường dẫn cấu hình có thể khác theo sản phẩm/phiên bản.

Một kiến trúc được dùng phổ biến trong tổ chức là:

~~~text
Developer laptop / CI runner
    |
    | Maven: pom.xml + effective settings
    v
Maven local repository (~/.m2/repository)
    |
    | cache miss / metadata cần cập nhật
    v
Maven mirror URL (ví dụ: corp-maven)
    |
    v
Repository manager (đầu vào nhóm: maven-public)
    |
    +-- proxy-central ----> Maven Central qua HTTPS
    |
    +-- proxy-partner ----> kho bên thứ ba được duyệt
    |
    +-- hosted-releases -> bản phát hành của công ty
    |
    +-- hosted-snapshots -> bản SNAPSHOT nội bộ
~~~

Sơ đồ mô tả **luồng tải**. Artifact được build để phát hành nội bộ thường đi theo **luồng upload riêng** tới hosted releases/snapshots qua `mvn deploy`, không phải gửi upload vào URL mirror chỉ dùng để tải.

**Mục tiêu chính:** quản lý nguồn binary ở một điểm tin cậy, giảm lượt tải ra ngoài, tăng độ ổn định, có khả năng kiểm soát quyền, audit và chính sách artifact. Tuy nhiên repository manager **không tự làm artifact an toàn**, không tự đảm bảo mọi dependency có sẵn và không tự hoạt động offline khi chưa được cấu hình/vận hành đúng.

## 2. Phân biệt năm thành phần hay bị nhầm

| Khái niệm | Nằm ở đâu? | Vai trò |
| --- | --- | --- |
| **Remote repository** | POM, settings profile, parent/Super POM | Nguồn Maven biết có thể dùng để giải quyết artifact theo **repository ID và URL**. |
| **Mirror** | `settings.xml` mục `mirrors` | Quy tắc client **đổi endpoint truy cập** của một repository ID sang URL thay thế. |
| **Repository manager** | Dịch vụ máy chủ (Nexus, Artifactory...) | Proxy/cache, quản lý hosted/group repository và áp dụng chính sách tập trung. |
| **Local repository** | Thường `~/.m2/repository` trên máy build | Cache artifact/metadata của **một môi trường Maven**; Maven dùng nó trước khi cần truy cập remote. |
| **HTTP proxy** | `settings.xml` mục `proxies` hoặc hệ thống mạng | Trung gian truyền kết nối HTTP(S); không phải Maven mirror và không tự hiểu artifact/repository group. |

**Mirror không phải một repository manager.** Một mirror chỉ là **quy tắc chọn URL phía Maven client**. URL đó có thể trỏ tới repository manager, một mirror server độc lập hoặc một repository khác.

**Proxy cache trong repository manager không phải local repository.** Local cache tồn tại trên máy của từng developer/runner; repository manager cache nằm trên server và có thể chia sẻ cho nhiều build. Một artifact đã có ở repository manager nhưng chưa ở local repository vẫn phải được Maven tải về máy client (thường là qua mạng nội bộ).

**Mirror không phải load balancer/failover list.** Maven chọn một mirror phù hợp cho một repository; không tự thử tuần tự mọi mirror được khai báo nếu endpoint đã chọn lỗi. Muốn HA/failover thì thiết kế ở tầng repository manager, DNS, load balancer hoặc hạ tầng phù hợp.

## 3. Repository manager thường có những loại kho nào?

### 3.1. Proxy repository

**Proxy** là một kho trung gian trỏ tới nguồn upstream, ví dụ Maven Central. Khi client yêu cầu artifact:

1. Repository manager kiểm tra liệu dữ liệu phù hợp đã được cache không.
2. Nếu có bản cache hợp lệ và chính sách cho phép, server trả về từ cache.
3. Nếu chưa có hoặc cần kiểm tra cập nhật, repository manager truy cập upstream, nhận artifact/metadata rồi lưu cache theo chính sách.
4. Server trả nội dung cho Maven client; Maven có thể lưu thêm một bản trong local repository.

Ưu điểm là giảm truy cập lặp tới upstream và có thể tiếp tục phục vụ một số artifact đã cache khi upstream gặp sự cố. **Không nên khẳng định proxy cache luôn chạy được offline:** artifact chưa từng cache, metadata cần làm mới, snapshot mới, chính sách hết hạn hoặc yêu cầu kiểm tra an toàn có thể vẫn phụ thuộc upstream.

**Không cần — và không nên — sao chép toàn bộ Maven Central theo kiểu mirror đồng bộ đầy đủ.** Tài liệu Apache Maven khuyến nghị dùng repository manager làm proxy cache thay vì cố mirror toàn bộ Central.

### 3.2. Hosted repository

**Hosted** là kho do chính tổ chức lưu và quản lý. Nó thường chứa artifact do pipeline của tổ chức tạo ra:

- `maven-releases`: các version ổn định, ví dụ `1.4.2`.
- `maven-snapshots`: các version đang phát triển, ví dụ `1.5.0-SNAPSHOT`.

Server cần được cấu hình **đúng chính sách release/snapshot**, quyền ghi và bảo vệ phiên bản release khỏi bị ghi đè tùy tiện.

### 3.3. Group hoặc virtual repository

**Group** (một số sản phẩm gọi là virtual repository) là endpoint hợp nhất **nhiều repository thành một giao diện đọc**:

~~~text
maven-public (group)
    |
    +-- maven-releases (hosted)
    +-- maven-snapshots (hosted)
    +-- maven-central (proxy)
    +-- partner-libs (proxy, nếu được duyệt)
~~~

Client có thể dùng một URL, còn **repository manager** quyết định thành viên nào được tìm và theo chính sách/thứ tự nào. Không giả định mọi sản phẩm giải quyết thành viên theo cùng một thuật toán; quản trị viên cần cấu hình và kiểm thử order/policy của group.

**Group endpoint thường dành cho tải, không phải nơi dùng làm đích upload mặc định.** Lệnh `mvn deploy` cần đích hosted phù hợp, có quyền ghi và có release/snapshot policy tương ứng.

### Khi nào chọn loại nào?

| Nhu cầu | Loại kho phù hợp |
| --- | --- |
| Cache Maven Central | Proxy tới Maven Central HTTPS. |
| Lưu thư viện công ty đã phát hành | Hosted releases. |
| Lưu bản build phát triển | Hosted snapshots. |
| Một địa chỉ cho Maven tải public và private artifacts | Group/virtual chứa các thành viên được duyệt. |
| Upload bản phát hành | Hosted releases, không phụ thuộc mirror download. |
| Upload phiên bản `-SNAPSHOT` | Hosted snapshots. |

**Một group không tự làm kho upstream được phép truy cập.** Nếu upstream chưa được thêm vào group/proxy, artifact đó có thể vẫn 404 mặc dù client đã chọn đúng mirror.

## 4. Dòng chảy artifact, POM và metadata từ client tới cache

Maven artifact có tọa độ **groupId:artifactId:version**; còn có `type`/`classifier` khi dùng artifact đặc biệt. Với Maven repository layout thông thường, tọa độ:

~~~text
org.apache.commons:commons-lang3:3.14.0
~~~

tương ứng những đường dẫn remote gần như:

~~~text
org/apache/commons/commons-lang3/3.14.0/
    commons-lang3-3.14.0.pom
    commons-lang3-3.14.0.jar
    các checksum / chữ ký nếu nguồn cung cấp
~~~

**POM của dependency cũng quan trọng như JAR** vì Maven đọc nó để biết transitive dependencies, packaging và metadata xây dựng dependency graph.

Các file **`maven-metadata.xml`** có vai trò riêng:

- Ở mức **groupId**: hỗ trợ ánh xạ plugin prefix của Maven plugin.
- Ở mức **groupId/artifactId**: giúp phát hiện danh sách phiên bản/release metadata.
- Ở mức **groupId/artifactId/baseVersion-SNAPSHOT**: giúp ánh xạ snapshot timestamped artifacts.

Metadata là dữ liệu Maven đọc và cập nhật theo chính sách, không phải một dependency người dùng thêm vào `pom.xml`. Một proxy cache có thể lưu cả **artifact** và **metadata**. Vì vậy hiện tượng “JAR đã nằm trong kho nhưng Maven vẫn không thấy phiên bản mới” có thể đến từ metadata hoặc cache policy, chứ không đơn thuần là thiếu file JAR.

**Release và snapshot có hành vi cập nhật khác nhau.** Release version nên được giữ bất biến trong quy trình phát hành. Snapshot được thiết kế để đổi nội dung qua những lần triển khai mới, thường có metadata timestamp/sequence; cần cẩn trọng khi cache, cập nhật và điều tra “sao CI vẫn lấy bản cũ”.

## 5. Maven lấy danh sách remote repositories từ đâu?

Maven có thể biết về repository qua nhiều nơi:

- `repositories` trong POM của dự án hoặc parent, bao gồm các profile hoạt động.
- `pluginRepositories` trong POM/profile, phục vụ việc tải Maven plugin.
- Settings profiles (`settings.xml`) khi được kích hoạt.
- Super POM có repository mặc định như Maven Central.
- Các repository trong ngữ cảnh POM của dependency khi quá trình resolution áp dụng.

Maven xác lập thứ tự repository theo **effective settings**, **effective POM** và ngữ cảnh dependency, sau đó **áp dụng mirror selection trước khi gửi request**. Các repository có ID khác nhau dù dùng chung host vẫn được xét theo ID riêng. Bởi vậy:

**`repositories` xác định các nguồn Maven được phép tìm. `mirrors` xác định endpoint thay thế khi Maven định truy cập một nguồn. Repository manager là dịch vụ phía server thực hiện proxy/cache/group.**

Đoạn POM minh họa một nguồn private:

~~~xml
<repositories>
    <repository>
        <id>partner-releases</id>
        <url>https://packages.example.invalid/maven/releases/</url>
    </repository>
</repositories>
~~~

Đây là **đoạn đặt trong `<project>`**, không phải POM hoàn chỉnh. Domain `.invalid` chỉ làm mẫu, không tồn tại để tải thật. Mirror có `mirrorOf=central` không áp dụng cho repository có ID `partner-releases`; mirror có `mirrorOf=external:*` có thể áp dụng nếu URL là external theo quy tắc Maven.

**Đừng thay mọi POM để hardcode URL repo manager của công ty.** Cấu hình tải phù hợp nên nằm trong `settings.xml`/CI khi mục tiêu là điều hướng chung mà không gắn project source với hạ tầng của một môi trường cụ thể.

## 6. Cấu hình mirrorOf để đưa lượt tải qua repository manager

Trong Maven 3, settings người dùng thường ở `~/.m2/settings.xml`, global settings trong thư mục `conf` của Maven đang chạy. Có thể chỉ định user settings khác bằng tùy chọn `-s path/to/settings.xml`.

Một file settings có mục mirror cơ bản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>corp-maven</id>
            <name>Approved company Maven repository manager</name>
            <url>https://repo.example.invalid/repository/maven-public/</url>
            <mirrorOf>external:*</mirrorOf>
        </mirror>
    </mirrors>
</settings>
~~~

**Đây là file XML hợp lệ về cấu trúc, nhưng URL `repo.example.invalid` là URL minh họa không thể truy cập.** Khi áp dụng thật, quản trị viên phải thay bằng endpoint HTTPS có thật, có quyền truy cập và cấu hình proxy/group đầy đủ. Không cố chạy build qua địa chỉ ví dụ rồi kết luận Maven hoặc repository manager bị lỗi.

Giải thích:

- `id=corp-maven` là **ID của mirror**, không phải ID của Maven Central.
- `url` là endpoint Maven sử dụng để tải khi mirror được chọn.
- `mirrorOf=external:*` chọn repository external; theo Maven, external loại những URL là localhost hoặc `file:`.
- Một repository nội bộ tại hostname `repo.company.internal` **vẫn có thể được xem là external**: external trong cú pháp Maven **không có nghĩa ngoài mạng công ty**.
- Muốn bảo toàn một remote repository cụ thể, có thể dùng ngoại lệ **theo repository ID**.

### Các biểu thức mirrorOf phổ biến

| Biểu thức | Phạm vi áp dụng |
| --- | --- |
| `central` | Chỉ repository gốc có ID chính xác `central`. |
| `central,partner-releases` | Repository có một trong hai ID được nêu. |
| `*` | Tất cả repository IDs phù hợp, kể cả nguồn `file:`/localhost nếu không bị loại. |
| `external:*` | Repository không ở localhost và không dùng `file:`. |
| `external:http:*` | Repository HTTP external; có từ Maven 3.8.0, thường liên quan chính sách chặn HTTP. |
| `*,!corp-direct` | Tất cả ngoại trừ repository có ID `corp-direct`. |
| `external:*,!corp-direct` | Các repository external trừ repository `corp-direct`. |

**Đây không phải regex hoặc phép lọc tọa độ dependency.** `mirrorOf` so với **ID của remote repository gốc**; dấu `!` loại theo ID, dấu phẩy phân tách token. Tránh khoảng trắng thừa: ví dụ `!repo1,*` đúng với ý định wildcard loại trừ, còn `!repo1, *` có thể không match như dự kiến.

### Mirror được chọn theo ưu tiên nào?

Maven kiểm tra mirror có **`mirrorOf` khớp chính xác repository ID** trước, rồi mới xét những pattern; nếu nhiều pattern cùng khớp, **thứ tự mirror trong effective settings** ảnh hưởng kết quả: Maven chọn match đầu tiên theo quy tắc.

Ví dụ có mirror A: `mirrorOf=external:*`, mirror B: `mirrorOf=central`. Khi Maven xét repository ID `central`, **mirror B có thể được chọn dù khai báo sau**, vì khớp trực tiếp ID.

**Một repository chỉ được chọn một mirror tại thời điểm truy cập.** Không tạo nhiều mirror cùng `mirrorOf=*` và kỳ vọng Maven cân bằng tải hoặc chuyển sang cái thứ hai khi cái thứ nhất 503. Nếu cần hợp nhất nhiều upstream, hãy làm việc đó trong repository manager.

## 7. Chính sách mirror trong tổ chức: một đầu vào hay ngoại lệ có kiểm soát?

Có hai mô hình hay dùng:

**Mô hình A — một đầu vào cho mọi remote repo**

~~~xml
<mirror>
    <id>corp-maven</id>
    <url>https://repo.example.invalid/repository/maven-public/</url>
    <mirrorOf>*</mirrorOf>
</mirror>
~~~

Ưu điểm: dễ áp chính sách “mọi lượt tải đi qua kho được duyệt”. Điều kiện: repository manager phải cung cấp những artifact cần thiết hoặc proxy các nguồn được phép. Nhược điểm: có thể mirror cả localhost/file repositories phục vụ test; repository chưa được group proxy sẽ không được truy cập trực tiếp. Dùng khi tổ chức thực sự cần chặn mọi nguồn download khác.

**Mô hình B — chỉ mirror external, giữ một nguồn riêng**

~~~xml
<mirror>
    <id>corp-maven</id>
    <url>https://repo.example.invalid/repository/maven-public/</url>
    <mirrorOf>external:*,!corp-direct</mirrorOf>
</mirror>
~~~

`corp-direct` là **repository ID** giả định cần được khai báo ở POM/settings hợp lệ nếu thực sự muốn truy cập; ngoại lệ không tự tạo repository. Mô hình này có thể giữ các kho `file:`/localhost cho integration test và một remote ID riêng.

**Không dùng ngoại lệ cho nguồn công cộng chưa được kiểm duyệt chỉ để làm build tạm thành công.** Ngoại lệ có thể đi vòng kiểm soát artifact của tổ chức. Nếu thiếu thư viện hợp lệ, hãy bổ sung proxy/upstream hoặc quy trình nạp artifact được phê duyệt vào repository manager.

## 8. Xác thực: server ID phải khớp mirror ID

Nếu endpoint mirror yêu cầu đăng nhập, Maven lấy thông tin từ `servers` trong settings. Ví dụ file settings hoàn chỉnh có cả mirror và server:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>corp-maven</id>
            <url>https://repo.example.invalid/repository/maven-public/</url>
            <mirrorOf>external:*</mirrorOf>
        </mirror>
    </mirrors>
    <servers>
        <server>
            <id>corp-maven</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Đây là **cấu hình minh họa**, phải thay URL và cấp biến môi trường bằng secret management tin cậy. Với repository manager cho phép đọc ẩn danh, có thể bỏ `servers` cho download. Không commit settings chứa token vào Git hoặc đưa token vào POM.

**Khóa xác thực ở đây là `corp-maven` — ID của mirror đang được dùng**, không phải repository gốc `central`. Nếu mirror ID và server ID khác nhau, một request có thể nhận 401/403 dù URL là đúng.

Bản Maven mới có thể có cơ chế ràng buộc credentials theo **origin (scheme/host/port)** ngoài ID; xem đúng tài liệu version Maven của tổ chức. Nguyên tắc an toàn vẫn là tránh để một repository không được tin cậy nhận credentials thông qua ID trùng nhau.

### Proxy mạng khác mirror

Nếu máy chỉ ra Internet thông qua HTTP(S) proxy, settings còn có mục `<proxies>`. Nó quản lý **đường truyền mạng**, khác với mirror chọn Maven repository. Trong một mạng doanh nghiệp, Maven có thể vừa dùng **proxy mạng**, vừa dùng **mirror URL của repository manager**; cấu hình hai lớp theo đúng kiến trúc mạng. Không chép proxy credentials vào `servers` rồi kỳ vọng HTTP proxy mạng tự nhận được.

### Các nguyên tắc secrets cho CI

- Dùng account/token quyền **read** cho job chỉ cần tải dependency.
- Job deploy có thể cần account/token **write** riêng; phân quyền theo repo release/snapshot.
- Không in toàn bộ biến môi trường hoặc nội dung `settings.xml` có secrets.
- Cấp settings/credentials bằng cơ chế secret store của CI, theo đúng runner/container thực thi Maven.
- Ưu tiên endpoint HTTPS và kiểm tra chain certificate; không vô hiệu hóa kiểm tra TLS để qua lỗi tạm.

## 9. Luồng deploy khác luồng tải

**`mirrors` chuyển hướng việc Maven giải quyết dependency/plugin**, không mặc nhiên sửa URL được cấu hình cho `mvn deploy`.

Khi phát hành artifact của dự án, Deploy Plugin thường đọc `distributionManagement` của POM:

~~~xml
<distributionManagement>
    <repository>
        <id>corp-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>corp-snapshots</id>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

Đây là **đoạn XML đặt trong POM**, không phải file độc lập; hai URL là ví dụ, chưa có server thật. Bản release dùng đích `repository`, bản version kết thúc `-SNAPSHOT` thường dùng đích `snapshotRepository` nếu khai báo.

Thông tin xác thực trong settings cho deploy có ID khớp các đích:

~~~xml
<servers>
    <server>
        <id>corp-releases</id>
        <username>${env.MAVEN_DEPLOY_USER}</username>
        <password>${env.MAVEN_DEPLOY_TOKEN}</password>
    </server>
    <server>
        <id>corp-snapshots</id>
        <username>${env.MAVEN_DEPLOY_USER}</username>
        <password>${env.MAVEN_DEPLOY_TOKEN}</password>
    </server>
</servers>
~~~

Đoạn `<servers>` này được **đặt cùng file settings** với phần download mirror nếu áp dụng; không tạo hai phần `<servers>` độc lập trong cùng file. Quyền ghi và policy bất biến của release cần được repository manager áp dụng. Cũng có thể dùng hai token/role riêng cho release và snapshot khi chính sách yêu cầu.

| Hoạt động | Đích thường dùng | ID cho credentials |
| --- | --- | --- |
| `mvn dependency:resolve`, compile/test | Mirror trỏ tới group/proxy download | **Mirror ID**, ví dụ `corp-maven`. |
| Maven tải plugin | Mirror của plugin repository có ID phù hợp | Mirror ID được chọn. |
| `mvn deploy` release | Hosted releases theo distributionManagement | **Deployment repository ID**, ví dụ `corp-releases`. |
| `mvn deploy` snapshot | Hosted snapshots theo distributionManagement | **Snapshot repository ID**, ví dụ `corp-snapshots`. |

**Lỗi deploy 401/403 không nên được sửa đầu tiên bằng `mirrorOf`.** Hãy kiểm tra deployment URL, permissions, matching server ID, release/snapshot policy và việc artifact đã tồn tại.

## 10. Releases, snapshots và metadata cần chính sách khác nhau

Một repository manager phục vụ cả binary phát hành và bản phát triển phải có policy rõ:

- **Release:** version ổn định, nên bất biến; công bố một lần và kiểm soát quyền ghi/ghi đè. Thực thi quy trình promotion, approval, scan theo yêu cầu tổ chức.
- **Snapshot:** có thể được triển khai lặp lại với version `-SNAPSHOT`, metadata timestamped resolution có thể thay đổi. Tránh dùng snapshot vô kiểm soát trong sản phẩm phát hành.
- **Artifact metadata:** `maven-metadata.xml` và checksum/signature giúp Maven giải quyết phiên bản/snapshot và kiểm tra tính nhất quán. Metadata cũng bị cache, có chính sách cập nhật riêng.
- **Proxy negative cache:** một số repository manager có thể cache kết quả không tìm thấy artifact/metadata trong khoảng thời gian nhất định; việc upstream vừa xuất bản artifact không có nghĩa mọi lượt tải lập tức thấy nó.
- **Retention:** snapshot cũ nên có chính sách dọn dẹp dựa trên nhu cầu tái lập/audit; không xóa release quan trọng tùy tiện.
- **An ninh nguồn:** chỉ proxy những upstream được duyệt, áp kiểm tra checksum, vulnerability/license policy khi công cụ của tổ chức hỗ trợ. Cache nhanh không phải bảo đảm artifact an toàn.

### Maven updatePolicy không phải TTL của repository manager

Trong POM/settings repository policy, Maven hỗ trợ những giá trị `updatePolicy` như **`always`**, **`daily`**, **`interval:N`** (phút) và **`never`**. Chúng tác động tới **quyết định cập nhật của Maven client** cho repository/metadata theo ngữ cảnh.

Repository manager có **cache/metadata/negative-cache TTL riêng**. Hai lớp này độc lập về chức năng: đổi một policy ở phía client **không tự xóa cache server**, và xóa cache server **không có nghĩa local Maven sẽ lập tức tải lại mọi JAR**.

**`mvn -U`** yêu cầu Maven kiểm tra cập nhật phù hợp, đặc biệt cho snapshot và trạng thái thiếu release theo cơ chế Maven. Nó **không phải lệnh “xóa toàn bộ cache hai tầng rồi tải lại tất cả”**. Khi debug, phải phân biệt local cache, remote manager cache và upstream.

## 11. Plugin repositories cũng phải đi qua đúng nguồn

Một project có thể tải dependency thành công nhưng thất bại khi giải quyết Maven plugin. Nguyên nhân thường gặp:

- Maven có **`repositories`** cho dependency nhưng **`pluginRepositories`** khác ID/URL.
- Repository manager group chứa dependency nhưng không có plugin hoặc các dependency của plugin cần thiết.
- Mirror selection chỉ bao phủ một repository ID, ví dụ `mirrorOf=central`, còn plugin repository của dự án có ID khác.
- Plugin prefix resolution cần metadata về plugin group và artifact mà manager chưa phục vụ đúng.

Ví dụ đoạn POM có hai repository IDs:

~~~xml
<repositories>
    <repository>
        <id>partner-deps</id>
        <url>https://packages.example.invalid/maven/dependencies/</url>
    </repository>
</repositories>
<pluginRepositories>
    <pluginRepository>
        <id>partner-plugins</id>
        <url>https://packages.example.invalid/maven/plugins/</url>
    </pluginRepository>
</pluginRepositories>
~~~

Đây chỉ là **đoạn POM minh họa**. Mirror với `mirrorOf=partner-deps` **không** match `partner-plugins`; muốn chuyển cả hai cần danh sách IDs hoặc pattern phù hợp.

**Repository manager phải phục vụ Maven plugin POM/JAR và dependency của plugin**, không chỉ application libraries. Khi plugin không giải quyết được, trước hết xem **artifact nào** và **repository ID/URL nào** Maven đang thử.

## 12. Ví dụ Java 17: kiểm chứng tải dependency qua kho

Ví dụ dùng một dependency trên Maven Central để tạo yêu cầu tải thực tế. Nó chạy được **khi không cấu hình mirror hỏng** và Maven có kết nối tới nguồn artifact; sau đó dùng settings mirror **đã thay URL thật** để kiểm chứng repository manager tổ chức.

Cấu trúc:

~~~text
repo-manager-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/repository/App.java
    └── test/java/vn/example/repository/AppTest.java
~~~

### 12.1. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>repo-manager-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
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

POM này **không khai báo hạ tầng nội bộ**. Nó mô tả dependencies và plugin mà build cần; việc chọn tải trực tiếp hay qua manager do Maven settings của môi trường quyết định.

### 12.2. src/main/java/vn/example/repository/App.java

~~~java
package vn.example.repository;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String title(String raw) {
        return StringUtils.capitalize(raw.trim());
    }

    public static void main(String[] args) {
        System.out.println("Repository OK: " + title("  maven"));
    }
}
~~~

### 12.3. src/test/java/vn/example/repository/AppTest.java

~~~java
package vn.example.repository;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void formatsTextUsingDependency() {
        assertEquals("Maven", App.title("  maven"));
    }
}
~~~

### 12.4. Baseline build không dùng URL minh họa

Từ thư mục `repo-manager-demo/`, trên máy Maven/JDK có khả năng tải dependencies:

~~~bash
mvn --version
mvn -B -ntp clean verify
~~~

Build dùng những repository có hiệu lực của môi trường đó; mặc định Maven có thể truy cập Maven Central, nhưng nếu user/global settings đã có mirror khác thì Maven vẫn sử dụng mirror ấy. Muốn biết nguồn thật cần kiểm tra settings và log, không suy luận chỉ từ POM.

Copy runtime dependency và chạy trên Linux/macOS:

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/runtime-libs
java -cp "target/classes:target/runtime-libs/*" vn.example.repository.App
~~~

Windows PowerShell/cmd.exe:

~~~powershell
java -cp "target\classes;target\runtime-libs\*" vn.example.repository.App
~~~

**Stdout chính xác của riêng lệnh Java khởi chạy App**, khi console hiển thị Unicode đúng:

~~~text
Repository OK: Maven
~~~

`mvn verify` chỉ build/test, không tự in ra stdout của `App.main`. Commons Lang được copy vào runtime-libs vì `includeScope=runtime` của Dependency Plugin bao gồm cả compile dependencies. Không dùng `java -jar` vì POM chưa khai báo `Main-Class` trong manifest và JAR thường không chứa Commons Lang.

### 12.5. Build qua repository manager của tổ chức

Sau khi có **corp-settings.xml với URL thực tế**, thử:

~~~bash
mvn -s corp-settings.xml -B -ntp clean verify
~~~

Nếu repository manager được cấu hình đúng, nó phục vụ dependency, plugin và metadata cần thiết; Maven báo build thành công. **Không dùng nguyên URL `.invalid` của bài**: nó cố tình không tồn tại và build sẽ thất bại nếu Maven thực sự cần kết nối.

Để chứng minh **mirror selection** trong log, có thể dùng:

~~~bash
mvn -s corp-settings.xml -B -ntp -X org.apache.maven.plugins:maven-dependency-plugin:3.6.1:resolve
~~~

Trong một số phiên bản Maven, debug log có dòng tương tự:

~~~text
Using mirror corp-maven (https://repo.example.invalid/repository/maven-public/) for central (https://repo.maven.apache.org/maven2/).
~~~

Dòng này **chỉ là mẫu minh họa**, không phải log chắc chắn xuất hiện nguyên văn. Với URL thật, địa chỉ sẽ khác. Nếu tất cả artifact nằm trong local repository, Maven có thể ít phát sinh request; mirror selection và việc tải thực sự là hai bước cần đọc khác nhau.

## 13. Cách kiểm tra settings, repository order và luồng mạng

### Bước 1 — xác định Maven/JDK

~~~bash
mvn --version
~~~

Nếu dự án có Maven Wrapper, kiểm tra cùng bản Maven của CI qua `./mvnw --version` hoặc `.\mvnw.cmd --version` trên Windows. Một số tính năng mirror/HTTP blocker và cách xử lý settings có thể khác giữa Maven 3 và Maven 4.

### Bước 2 — xem effective settings

~~~bash
mvn help:effective-settings
mvn -s corp-settings.xml help:effective-settings
~~~

Nếu mirror được cấu hình sai làm Maven không tải nổi Help Plugin, lệnh trên có thể thất bại; khi ấy đọc settings bằng công cụ soạn thảo bảo mật và xem log lỗi đầu tiên. Khi chia sẻ output effective settings, phải loại bỏ thông tin hạ tầng, ID nhạy cảm và credentials.

### Bước 3 — kiểm tra effective POM và profile

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:active-profiles
~~~

Những lệnh này giúp hiểu repository IDs/URLs xuất phát từ POM/parent/profile nào. Repository thứ nhất mà Maven thử **có thể khác** với repository bạn nhìn đầu tiên trong file POM đơn lẻ; Maven xét effective settings, POM và ngữ cảnh theo quy tắc repository order.

### Bước 4 — kiểm tra log mirror và artifact

~~~bash
mvn -B -ntp -X dependency:resolve
~~~

Đọc dòng có `Using mirror ... for ...`, repository ID gốc, mirror ID, URL endpoint, artifact coordinate và HTTP status thực tế. **Không đăng nguyên debug log** lên kênh công khai khi có địa chỉ nội bộ hoặc secrets.

### Bước 5 — so sánh cache hai tầng

- **Client local repository:** artifact/POM/metadata đã nằm trên runner chưa?
- **Repository manager:** artifact được cache trong proxy/hosted/group nào? Có bị negative cache hoặc metadata stale không?
- **Upstream:** manager có quyền truy cập đúng HTTPS endpoint và policy không?
- **Repository/Release policy:** artifact là release hay snapshot, group endpoint có phục vụ loại đó không?

Không xóa toàn bộ `~/.m2/repository` của máy thật khi chưa hiểu lỗi. Nếu cần thử từ một local repository tách biệt, có thể tạo một thư mục mới và chạy:

~~~bash
mvn -Dmaven.repo.local=target/fresh-m2 -B -ntp clean verify
~~~

Cách này thử khả năng tải artifact/plugin cần thiết vào một local cache riêng trong dự án, nhưng **không làm repository manager trở thành cache sạch**. Có thể dùng path riêng ở CI/terminal để tránh chạm kho Maven chính; chú ý `target/` sẽ bị `clean` xóa đầu ra, và Maven có thể tái sử dụng cấu hình khác từ user settings.

## 14. Đọc lỗi đúng tầng thay vì sửa ngẫu nhiên

| Triệu chứng | Tầng có thể gặp vấn đề | Kiểm tra đầu tiên |
| --- | --- | --- |
| Maven tiếp tục truy cập Central trực tiếp | Mirror selection/settings | Kiểm tra `mirrorOf`, repository ID gốc, file settings và debug log. |
| `401 Unauthorized` | Xác thực | `servers/server/id` có trùng mirror/deploy ID không, token có được cấp trên runner không? |
| `403 Forbidden` | Quyền/chính sách | Account có quyền đọc/ghi đúng repository? Artifact có bị cấm hoặc quarantine? |
| `404 Not Found` | Nội dung/group/upstream | Group có chứa hosted/proxy cần thiết, releases/snapshots đúng loại, negative cache còn hiệu lực không? |
| `429 Too Many Requests` | Rate limiting/quota | Hạn chế song song/retry mù, xác định điểm phát sinh 429 ở manager/upstream và quota liên quan. |
| `502/503/504` | Manager/upstream/network | Kiểm tra health, timeout, DNS, gateway, upstream status, tài nguyên máy chủ. |
| `PKIX path building failed` | TLS/certificate | Kiểm tra chain và truststore JDK, hostname và proxy TLS; không tắt kiểm tra chứng chỉ. |
| `Blocked mirror for repositories` | Chính sách HTTP không an toàn | Chuyển sang HTTPS hoặc repo manager HTTPS được duyệt; xem `external:http:*`. |
| Dependency tải được nhưng plugin không tải được | Plugin repositories/plugin graph | Kiểm tra pluginRepositories, mirror ID và plugin artifacts trong group. |
| `-SNAPSHOT` vẫn lấy bản cũ | Metadata/update policy/cache | Kiểm tra timestamped metadata, local update check, proxy cache TTL và bản đã deploy. |
| Release có vẻ đổi nội dung | Quy trình phát hành | Kiểm tra immutability/checksum; không ghi đè release để sửa lỗi tạm. |
| CI khác máy cá nhân | Settings/runner/cache | So sánh Maven/JDK, settings, profiles, token, cache và nguồn thực sự được truy cập. |

**401 khác 403; 404 khác lỗi DNS.** Nhiều vấn đề Maven đều được gói trong thông báo `Could not resolve dependencies`, nên cần đọc **root cause** (artifact, repo ID, URL, HTTP status, certificate) trước khi đổi POM.

### HTTP blocker

Từ Maven 3.8.1, phân phối Maven dùng chính sách chặn các repository HTTP external theo cấu hình mặc định (dựa vào mirror selector `external:http:*` và thuộc tính `blocked`). Mục tiêu là giảm nguy cơ tải artifact qua kênh không an toàn.

Đừng tắt blocker hoặc thêm mirror HTTP ngẫu nhiên chỉ để làm build qua. Nên thay nguồn bằng HTTPS, cập nhật dependency/POM có URL cũ hoặc đưa artifact vào repository manager HTTPS có kiểm soát.

## 15. Thiết kế hạ tầng cho CI và nhiều nhóm

### Phân tách quyền

- Developer và CI build job: **read** qua group download.
- Release pipeline: **write** vào hosted release đích đã duyệt.
- Snapshot CI job: quyền triển khai vào hosted snapshot theo quy trình.
- Quản trị viên: cấu hình group/proxy/retention và allowlist, không chia sẻ quyền admin cho runner.

### Khả năng sẵn sàng và hiệu năng

Repository manager có thể trở thành **điểm phụ thuộc chung**. Cân nhắc backup, giám sát dung lượng, HA/load balancing theo hỗ trợ của sản phẩm, health checks, metrics cache hit/miss, độ trễ upstream và cơ chế khôi phục. **Một mirror trong settings** không giải quyết tự động high availability của server.

### Chính sách nguồn và bảo mật chuỗi cung ứng

Dùng upstream allowlist, HTTPS, checksum/signature khi có, đánh giá lỗ hổng và license, quarantine artifact không đạt chính sách. Những khả năng như scan hoặc admission policy **không phải mặc định của mọi repository manager**; phải triển khai và giám sát.

Ghi lại **artifact coordinates, checksum, repository gốc, thời điểm tải và build provenance** khi hệ thống hỗ trợ. Điều đó giúp truy nguyên khi library nội bộ bị thay đổi hoặc có thông báo bảo mật.

### Quản lý chi phí

Theo dõi dung lượng blob store, metadata, artifact không còn dùng và retention snapshots. Caching tăng tốc download lặp nhưng không có nghĩa lưu vô hạn mọi bản snapshot là miễn phí.

### Cache trong CI

Các runner ephemeral có thể mất local Maven repository sau mỗi job; repository manager vẫn giúp giảm tải upstream vì cache dùng chung. Nếu runner cache local Maven artifact, nên chú ý thời gian sống, quyền truy cập, nhiều Maven versions và rủi ro lưu lại artifact cũ. Không chia sẻ local repository ghi đồng thời giữa nhiều runner theo cách không được Maven/hệ thống build hỗ trợ.

## 16. Những sai lầm thường gặp trong tổ chức

**“Thêm một mirror là Maven tự proxy được mọi kho.”** Sai. Mirror chỉ chuyển endpoint; repository manager phải cấu hình proxy/group cho những nguồn thực sự được duyệt.

**“Có nhiều mirror cùng pattern thì Maven tự failover.”** Sai. Maven chọn một mirror phù hợp, không tự tổng hợp/failover các mirror.

**“external:* nghĩa là chỉ repository trên Internet công cộng.”** Sai. Một hostname nội bộ không phải localhost cũng có thể match.

**“Đổi mirrorOf sẽ chuyển luôn đích mvn deploy.”** Sai. Deploy dùng distributionManagement/Deploy Plugin hoặc cấu hình deploy tương ứng.

**“server ID phải bằng central.”** Sai nếu Maven dùng mirror ID `corp-maven`; credentials tải theo ID endpoint đã chọn.

**“Maven chỉ giải quyết dependencies, không cần mirror plugin.”** Sai. Plugin, plugin dependency và metadata cũng cần repository phù hợp.

**“Nếu build thành công một lần, cache chắc chắn đủ mọi build sau.”** Sai. Có thể có artifact/plugin mới, snapshot mới, profile khác hoặc metadata hết hạn.

**“Dùng -U là xóa sạch cache.”** Sai. Cần hiểu update checks ở client và chính sách cache của server.

**“Cache artifact đồng nghĩa nó an toàn và đã qua scan.”** Sai. Cần xây dựng chính sách kiểm soát nguồn, kiểm tra checksum/provenance và các bước security tương ứng.

**“Tắt TLS/HTTP blocker là cách sửa ổn.”** Sai. Nó bỏ đi một lớp bảo vệ; ưu tiên HTTPS và trust chain đúng.

**“Group có chứa hosted releases, snapshots thì upload vào group cũng được.”** Không nên giả định. Deployment thường cần endpoint hosted có quyền ghi rõ ràng.

## 17. Checklist triển khai repository manager cho một nhóm

1. **Liệt kê nguồn** dự án thật sự cần: Maven Central, đối tác, private libraries, plugins, snapshot và đích deploy.
2. **Chọn repository manager** phù hợp về vận hành, quyền truy cập, backup, HA và policy; không coi sản phẩm nào tự an toàn mà không cấu hình.
3. **Tạo proxy** tới những upstream HTTPS được duyệt, với cache, metadata, SSL và policy thích hợp.
4. **Tạo hosted releases/snapshots** với quy tắc version, quyền ghi và retention riêng.
5. **Tạo group đọc** chứa những thành viên cần thiết; xác nhận order và release/snapshot support.
6. **Tạo mirror ID/URL** trong settings của máy/CI; chọn `central`, `external:*` hoặc `*` theo chính sách, thêm ngoại lệ chỉ khi có lý do.
7. **Cấp credentials theo ID thực tế** và tách quyền read/write; dùng secret store thay vì commit mật khẩu.
8. **Thiết kế deploy** bằng distributionManagement trỏ trực tiếp tới hosted phù hợp.
9. **Kiểm tra cả dependency và plugin** từ một local cache thử nghiệm riêng; kiểm tra source repository, artifact, POM, metadata và checksum.
10. **Thử release và snapshot** có kiểm soát; xác nhận timestamped metadata và updatePolicy không làm CI dùng artifact cũ.
11. **Chạy bài test Java/Maven thật**: compile, test, package, và chạy ứng dụng với runtime classpath đúng.
12. **Kiểm tra trường hợp lỗi**: sai token, repo 404, proxy upstream down, HTTP blocked, chứng chỉ hết hạn; xác định đội chịu trách nhiệm.
13. **Theo dõi vận hành**: cache hit, error rate, disk usage, latency, cert validity, availability và retention.
14. **Tài liệu hóa cho developer**: file settings được cấp, mirror ID, URL đích (không chứa secrets), cách debug và quy trình yêu cầu thêm upstream.
15. **Rà soát định kỳ** các proxy/hosted/group và quyền truy cập; tránh để những repository cũ, HTTP endpoints hoặc token toàn quyền tồn tại vô hạn.

### Bài tập kiểm chứng

**Bài 1 — ba lớp cache.** Vẽ local Maven repository, proxy cache của manager và Maven Central; cho biết khi máy A đã tải một artifact nhưng máy B chưa tải, server cache có thể giúp thế nào.

**Bài 2 — mirrorOf.** Cho repo ID `central`, `partner`, `corp-direct` với URL external. Dự đoán kết quả của `mirrorOf=central`, `external:*`, và `external:*,!corp-direct`. Giải thích tại sao `corp-direct` phải là ID, không phải hostname.

**Bài 3 — credentials.** Mirror có ID `corp-maven` và nguồn gốc ID `central`. Chọn đúng `servers/server/id` cho download, rồi chọn ID riêng cho deploy release `corp-releases`.

**Bài 4 — chẩn đoán.** Trên môi trường thử nghiệm được phép, cấu hình group thiếu một proxy cần thiết. Quan sát 404 và xác định tại sao sửa `mirrorOf=*` không tự tạo artifact trong group.

**Bài 5 — CI.** Với một runner dùng local repo trống, chạy dự án Java 17 ở mục 12 qua settings thật, xem log mirror; sau đó chạy lại để so sánh hành vi cache nhưng không kết luận mọi lần tải lại chắc chắn là cache hit.

### Tổng kết

**Maven mirror quyết định “gửi request tới URL nào”, repository manager quyết định “phục vụ artifact từ kho/nguồn nào”, còn local repository quyết định “máy build đã có dữ liệu nào”.** Proxy cache giúp chia sẻ artifact được tải qua nhiều developer/CI; hosted repositories giữ binary tổ chức; group repository gom nguồn thành một đầu vào. Một hệ thống tốt còn cần HTTPS, credentials/permissions, release/snapshot policy, kiểm soát metadata, giám sát và quy trình debug theo từng tầng.

### Tài liệu chính thức

- [Apache Maven — Best Practice: Using a Repository Manager](https://maven.apache.org/repository-management.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html)
- [Apache Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html)
- [Apache Maven — Maven 3.8.1 Release Notes: HTTP Blocker](https://maven.apache.org/docs/3.8.1/release-notes.html)
- [Maven Dependency Plugin — dependency:resolve](https://maven.apache.org/plugins/maven-dependency-plugin/resolve-mojo.html)
