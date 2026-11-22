# `licenses`, `developers`, `scm` và thông tin phục vụ xuất bản trong Maven POM

## 1. Vì sao POM cần thông tin xuất bản?

Một tệp `pom.xml` không chỉ mô tả cách biên dịch Java. Nó còn cho người dùng và hệ thống quản lý repository biết **artifact là gì, ai duy trì, được phân phối theo giấy phép nào, mã nguồn nằm ở đâu và cần báo lỗi ở đâu**. Khi dự án được xuất bản dưới một tọa độ Maven, các thông tin đó có thể đi cùng POM để công cụ và con người hiểu nguồn gốc của thư viện.

Bài này tập trung vào metadata cấp dự án: `<name>`, `<description>`, `<url>`, `<organization>`, `<licenses>`, `<developers>`, `<scm>` và các trường phụ trợ cho phát hành. Bạn sẽ:

1. Viết POM hợp lệ cho một dự án Java 17.
2. Phân biệt **metadata mô tả dự án** với **cấu hình upload artifact**.
3. Hiểu ý nghĩa từng trường của giấy phép, người phát triển và quản lý mã nguồn.
4. Xác minh cấu hình bằng Maven, phân biệt `package`, `install` và `deploy`.
5. Nhận biết những bước bổ sung trước khi công bố thư viện lên kho công cộng hoặc kho nội bộ.

Phạm vi ví dụ là một artifact Java JAR thông thường; các URL như `git.example.org` và `maven.example.org` bên dưới chỉ mang tính minh họa và **không phải điểm xuất bản hoạt động**.

## 2. Nhìn tổng thể: metadata, tọa độ và phân phối

Các trường POM giải quyết những câu hỏi khác nhau:

| Thành phần POM | Trả lời câu hỏi | Tác động chính |
| --- | --- | --- |
| `groupId`, `artifactId`, `version`, `packaging` | Artifact nào, phiên bản nào, định dạng gì? | Định danh và đường dẫn artifact trong Maven repository. |
| `name`, `description`, `url` | Dự án tên gì, làm gì, xem thông tin ở đâu? | Hiển thị trong catalog, site, trang repository và tài liệu. |
| `licenses` | Dự án này được phân phối theo giấy phép nào? | Metadata pháp lý cho người sử dụng và dịch vụ kiểm tra artifact. |
| `developers`, `contributors`, `organization` | Ai phát triển, đóng góp, chịu trách nhiệm hoặc đại diện dự án? | Metadata liên hệ, trách nhiệm và truy vết. |
| `scm` | Mã nguồn được quản lý ở đâu và dùng kết nối nào? | Liên kết mã nguồn, tích hợp công cụ SCM/release khi được cấu hình. |
| `issueManagement`, `ciManagement`, `mailingLists` | Theo dõi vấn đề, CI, trao đổi ở đâu? | Liên kết kênh vận hành và hỗ trợ. |
| `distributionManagement` | Với cơ chế Maven Deploy truyền thống, upload artifact đến repository nào? | Cấu hình đích xuất bản ở bước `deploy`. |

Không nhầm `<licenses><license><distribution>repo</distribution>` với `<distributionManagement>`. Từ `distribution` trong giấy phép mang ý nghĩa về **phương thức phân phối theo giấy phép**, còn `distributionManagement` chứa **thông tin repository đích** phục vụ triển khai.

Metadata không có tác dụng tự tạo quyền sở hữu tên miền, cấp phép sử dụng mã nguồn, cấu hình Git remote hay gửi artifact lên Internet. Đó là những công việc riêng cần có xác nhận và công cụ tương ứng.

## 3. Ví dụ `pom.xml` đầy đủ

Giả sử nhóm sở hữu một thư viện minh họa `pom-metadata-demo` và **thực sự có quyền phát hành mã của mình dưới Apache License 2.0**. Dự án có cây thư mục:

~~~text
pom-metadata-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── Demo.java
~~~

Tệp `pom.xml` sau đây hợp lệ với mô hình POM 4.0.0 và có thể dùng để build Java 17; trước khi xuất bản thật phải thay toàn bộ thông tin định danh/liên hệ giả định bằng thông tin chính xác:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>pom-metadata-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>POM Metadata Demo</name>
    <description>Ví dụ Java về metadata phục vụ xuất bản Maven.</description>
    <url>https://git.example.org/team/pom-metadata-demo</url>
    <inceptionYear>2026</inceptionYear>

    <organization>
        <name>Example Team</name>
        <url>https://example.org</url>
    </organization>

    <licenses>
        <license>
            <name>Apache-2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
            <distribution>repo</distribution>
        </license>
    </licenses>

    <developers>
        <developer>
            <id>maintainer-one</id>
            <name>Example Maintainer</name>
            <email>maintainer@example.org</email>
            <organization>Example Team</organization>
            <organizationUrl>https://example.org</organizationUrl>
            <roles>
                <role>maintainer</role>
                <role>developer</role>
            </roles>
        </developer>
    </developers>

    <scm>
        <connection>scm:git:https://git.example.org/team/pom-metadata-demo.git</connection>
        <developerConnection>scm:git:ssh://git@git.example.org/team/pom-metadata-demo.git</developerConnection>
        <tag>HEAD</tag>
        <url>https://git.example.org/team/pom-metadata-demo</url>
    </scm>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Hai lưu ý về ví dụ:

- `com.example`, các địa chỉ thuộc `example.org` và tên `Example Maintainer` chỉ phục vụ học cú pháp. Chúng **không** chứng minh bạn sở hữu namespace `com.example` hoặc có repository Git tương ứng. Khi phát hành thật, sử dụng tọa độ/URL/liên hệ có quyền quản lý và tồn tại thực tế.
- Không nên khai báo một giấy phép chỉ để đủ metadata. Phải kiểm tra quyền với mã nguồn, nội dung LICENSE thực tế và các thành phần bên thứ ba. Bản POM ví dụ giả định dự án có quyền dùng Apache-2.0; không tự cấp giấy phép cho nội dung bạn không sở hữu.

Tệp Java **`src/main/java/com/example/Demo.java`** giúp xác minh POM còn build được như dự án Java bình thường:

~~~java
package com.example;

public final class Demo {
    private Demo() {
    }

    public static void main(String[] args) {
        System.out.println("POM metadata demo");
    }
}
~~~

Sau khi có JDK 17+ và Maven, mở terminal tại thư mục chứa POM:

~~~bash
mvn clean package
java -cp target/pom-metadata-demo-0.1.0-SNAPSHOT.jar com.example.Demo
~~~

**Stdout của lệnh Java thứ hai:**

~~~text
POM metadata demo
~~~

Lệnh build thường kết thúc với `BUILD SUCCESS` nếu Maven tải được các plugin cần thiết và môi trường tương thích. `java -cp` được dùng vì POM này không khai báo `Main-Class` cho manifest JAR; metadata `licenses`, `developers`, `scm` không biến JAR thành executable JAR.

## 4. Trường `<licenses>`: giấy phép áp dụng trực tiếp cho dự án

Trong ví dụ:

~~~xml
<licenses>
    <license>
        <name>Apache-2.0</name>
        <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
        <distribution>repo</distribution>
    </license>
</licenses>
~~~

`<licenses>` chứa một hoặc nhiều phần tử `<license>`. Các trường thường dùng:

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Tên giấy phép. Dùng **SPDX identifier** khi phù hợp, ví dụ `Apache-2.0` hoặc `MIT`, giúp công cụ nhận diện thống nhất. |
| `url` | Liên kết đến văn bản hoặc trang mô tả giấy phép chính thức. |
| `distribution` | Cách phân phối theo metadata giấy phép: `repo` (có thể phân phối qua Maven repository) hoặc `manual` (cài đặt/phân phối thủ công theo điều kiện giấy phép). |
| `comments` | Ghi chú bổ sung nếu cần; không thay thế nội dung pháp lý của giấy phép. |

**Đặc biệt cần nhớ:** `licenses` nói về **giấy phép của chính artifact đang xuất bản**, không phải danh sách mọi giấy phép của những dependency mà artifact sử dụng. Các dependency có metadata giấy phép riêng; khi phân phối sản phẩm, vẫn cần kiểm tra nghĩa vụ pháp lý của chúng độc lập.

POM metadata cũng **không thay thế** tệp giấy phép thực tế. Với dự án sử dụng Apache-2.0, chủ dự án cần cung cấp văn bản LICENSE phù hợp và đáp ứng các điều kiện về thông báo, bản quyền, NOTICE nếu áp dụng. Có thể đặt `LICENSE` ở gốc repository và cân nhắc đóng gói giấy phép vào vị trí thích hợp như `META-INF/LICENSE`. Việc sử dụng license phải được người có quyền đối với mã nguồn quyết định.

Đừng gán `<distribution>repo</distribution>` rồi kết luận Maven đã được cho phép upload lên Maven Central. Đây chỉ là mô tả loại phân phối trong thông tin giấy phép. Việc upload còn phụ thuộc tài khoản, repository, quy trình phát hành và yêu cầu của nhà cung cấp.

### Khi có nhiều giấy phép

POM cho phép nhiều phần tử `license`, nhưng điều đó **không tự làm rõ** dự án là dual-licensed, có thể lựa chọn một trong hai, hay có các phần mã theo điều kiện khác nhau. Nếu dự án có nhiều giấy phép, tài liệu LICENSE và chính sách phát hành phải mô tả rõ phạm vi và quyền chọn; chỉ thêm nhiều thẻ XML là chưa đủ.

## 5. Trường `<developers>` và `<contributors>`: ai duy trì dự án?

`<developers>` mô tả những người có vai trò phát triển và duy trì dự án. Một người có thể có các thông tin sau:

~~~xml
<developers>
    <developer>
        <id>maintainer-one</id>
        <name>Example Maintainer</name>
        <email>maintainer@example.org</email>
        <organization>Example Team</organization>
        <organizationUrl>https://example.org</organizationUrl>
        <roles>
            <role>maintainer</role>
            <role>developer</role>
        </roles>
        <timezone>+7</timezone>
    </developer>
</developers>
~~~

Đoạn trên là **mảnh XML minh họa**, có thể dùng thay phần `<developers>` tương ứng trong POM đầy đủ. Ý nghĩa:

- `id`: định danh người phát triển trong metadata dự án; không phải token đăng nhập hay tài khoản Maven Central.
- `name` và `email`: tên và địa chỉ liên hệ có thể công khai trong POM được phân phối. Nên dùng thông tin đã được chấp thuận công bố.
- `organization` / `organizationUrl`: đơn vị mà người phát triển gắn với; không nhất thiết trùng mọi trường hợp với `<organization>` ở cấp dự án.
- `roles`: danh sách vai trò mô tả trách nhiệm, ví dụ `maintainer`, `developer`. Maven không cấp quyền Git, quyền deploy hoặc phân quyền CI dựa trên chuỗi `role` này.
- `timezone`: thông tin múi giờ của người phát triển; dạng `+7` là ví dụ offset. Không bắt buộc phải khai báo nếu không hữu ích.
- `properties`: metadata mở rộng theo key/value khi công cụ cụ thể sử dụng, tránh lạm dụng lưu dữ liệu riêng tư.

Một nhóm có nhiều maintainer thì thêm nhiều `<developer>` trong cùng `<developers>`. Hãy dùng thông tin thực tế, không tự động thêm toàn bộ danh sách người commit nếu họ chưa muốn công khai dữ liệu liên hệ.

`<contributors>` cũng có thể mô tả những người đóng góp nhưng không giữ vai trò developer chính. Các mục `contributor` có trường như `name`, `email`, `url`, `organization`, `roles`; cấu trúc gần giống nhưng không cần đồng nhất với danh sách maintainer. Metadata `developers` và `contributors` không thay thế lịch sử Git, chính sách bảo trì hay CODEOWNERS.

### Phân biệt người phát triển, tổ chức và tài khoản xuất bản

- **`<developers>`:** ai phát triển/duy trì dự án.
- **`<organization>`:** tổ chức/nhóm đứng sau dự án.
- **Tài khoản đăng repository:** người hoặc máy có quyền phát hành theo hệ thống repository thực tế; quyền này được xác thực ở dịch vụ lưu trữ và CI, **không suy ra từ `developers`**.

Ví dụ, một thư viện có thể do ba người bảo trì, thuộc một tổ chức, nhưng việc upload do pipeline CI được cấp token riêng. Không đưa token, khóa ký số hoặc mật khẩu vào metadata POM.

## 6. Trường `<scm>`: liên kết và kết nối đến mã nguồn

`SCM` là Software Configuration Management, thường là hệ thống quản lý mã nguồn như Git. Trong POM:

~~~xml
<scm>
    <connection>scm:git:https://git.example.org/team/pom-metadata-demo.git</connection>
    <developerConnection>scm:git:ssh://git@git.example.org/team/pom-metadata-demo.git</developerConnection>
    <tag>HEAD</tag>
    <url>https://git.example.org/team/pom-metadata-demo</url>
</scm>
~~~

| Trường | Dùng để làm gì? |
| --- | --- |
| `connection` | Cách kết nối SCM dành cho truy cập nguồn, về mặt ngữ nghĩa là kết nối đọc. |
| `developerConnection` | Cách kết nối SCM dành cho thao tác phát triển/có thể ghi nếu người dùng được cấp quyền. |
| `tag` | Nhánh/tag/điểm tham chiếu SCM của bản dự án; giá trị `HEAD` thường được dùng khi đang phát triển. Với release, nên gắn đúng tag của commit phát hành theo quy trình của nhóm. |
| `url` | Trang xem mã nguồn bằng trình duyệt để người dùng truy cập repository. |

Dạng kết nối SCM dùng quy ước:

~~~text
scm:<provider>:<provider-specific-connection>
~~~

Với Git, `provider` là `git` và phần còn lại có thể là một URL HTTPS/SSH phù hợp với trình quản lý mã nguồn. Dòng `connection` ở ví dụ chỉ mô tả địa chỉ fetch qua HTTPS; `developerConnection` mô tả SSH. **Chính hệ thống Git/SSH/token quyết định ai được phép ghi**, chứ tên thẻ XML không tự cấp quyền.

Không nhầm `scm.url` với `project.url`. Chúng có thể trỏ cùng trang khi trang chủ dự án là repository, nhưng về ý nghĩa:

- `project.url` là trang giới thiệu/trang chủ của **dự án**.
- `scm.url` là trang xem **mã nguồn**.
- `scm.connection` và `scm.developerConnection` là **chuỗi SCM connection** mà plugin có thể sử dụng, không đơn thuần là link mở web.

Định dạng `scm:git:...` không phải địa chỉ để dán nguyên xi vào trình duyệt. Nếu một plugin Maven SCM/release cần thao tác checkout, tag hay commit, plugin có thể đọc các trường này; bạn vẫn phải cấu hình đúng công cụ, thông tin xác thực và quyền truy cập.

### Giá trị `<tag>` qua chu kỳ phát hành

Khi đang phát triển `0.1.0-SNAPSHOT`, `HEAD` là ví dụ phổ biến. Sau khi phát hành bản `0.1.0` tại commit tương ứng với tag `v0.1.0`, metadata cho **bản phát hành** nên có liên kết đến tag đúng để người sử dụng truy lại source của artifact. Tên tag có thể theo quy ước khác, nhưng phải khớp tag thực tế.

Đổi `<tag>HEAD</tag>` thành `<tag>v0.1.0</tag>` trong POM **không tạo Git tag**. Ngược lại, tạo Git tag trong repository cũng không tự sửa mọi POM đã công bố. Nếu dùng Maven Release Plugin hoặc pipeline release riêng, hãy xem chính xác quy trình ấy đồng bộ phiên bản và tag như thế nào.

## 7. Các trường thông tin dự án bổ sung

Trong POM đầy đủ, bạn có thể thêm các trường để người dùng dễ tìm thông tin hơn.

### `name`, `description`, `url` và `inceptionYear`

~~~xml
<name>POM Metadata Demo</name>
<description>Ví dụ Java về metadata phục vụ xuất bản Maven.</description>
<url>https://git.example.org/team/pom-metadata-demo</url>
<inceptionYear>2026</inceptionYear>
~~~

- `name` là tên dễ đọc; khác `artifactId` là một phần tọa độ.
- `description` là mô tả ngắn, nên nói rõ artifact phục vụ mục đích gì thay vì chỉ nhắc lại tên.
- `url` là trang chủ/tài liệu chính thức, có thể là trang Git nếu dự án không có website riêng.
- `inceptionYear` là năm dự án bắt đầu, không phải phiên bản release.

Đây là metadata; không làm Java compile nhanh hơn hoặc tự công bố artifact. Nếu mô tả chứa ký tự đặc biệt của XML, ví dụ dấu `&`, cần ghi `&amp;`; các ký tự Unicode được phép khi tệp XML được lưu UTF-8 đúng khai báo.

### `organization`

~~~xml
<organization>
    <name>Example Team</name>
    <url>https://example.org</url>
</organization>
~~~

Thông tin tổ chức giúp người dùng biết đơn vị đứng sau dự án. Nó không phải bằng chứng pháp lý về quyền sở hữu namespace hay quyền kiểm soát server repository.

### `issueManagement` và `ciManagement`

Ví dụ **mảnh cấu hình thêm ở cấp `project`** (ngang hàng với `scm`, không đặt bên trong `scm`):

~~~xml
<issueManagement>
    <system>Issue Tracker</system>
    <url>https://git.example.org/team/pom-metadata-demo/issues</url>
</issueManagement>

<ciManagement>
    <system>CI Pipeline</system>
    <url>https://git.example.org/team/pom-metadata-demo/pipelines</url>
</ciManagement>
~~~

`issueManagement` mô tả nơi theo dõi lỗi, đề xuất hoặc yêu cầu thay đổi. `ciManagement` mô tả hệ thống tích hợp liên tục. Đây là liên kết/metadata; không tự tạo ticket, kích hoạt job CI hay cấu hình webhook.

POM còn có `<mailingLists>` để công bố kênh trao đổi và `<contributors>` để ghi nhận người đóng góp. Chỉ thêm trường nếu dự án có kênh/thông tin thật và có người duy trì. POM mô tả sai còn gây khó tìm hỗ trợ hơn việc không khai báo trường tùy chọn.

## 8. `distributionManagement` dùng để chỉ đích upload khi triển khai

Các trường `licenses`, `developers` và `scm` có thể giúp đáp ứng yêu cầu metadata, nhưng **chúng không chỉ ra repository nhận bản build**. Với một workflow sử dụng pha `deploy` của Maven truyền thống, cấu hình đích thường đặt ở `<distributionManagement>`.

Ví dụ **mảnh cấu hình tùy chọn** đặt trực tiếp dưới `<project>`, không nằm trong `<build>`; các URL `maven.example.org` chỉ để giải thích:

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Example Release Repository</name>
        <url>https://maven.example.org/releases</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Example Snapshot Repository</name>
        <url>https://maven.example.org/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Ý nghĩa:

- `repository`: đích dành cho **phiên bản phát hành** theo cơ chế Maven deploy thông thường.
- `snapshotRepository`: đích dành cho **phiên bản `-SNAPSHOT`** khi cấu hình repository hỗ trợ. Nếu không khai báo snapshot repository riêng, hành vi lựa chọn đích phụ thuộc cấu hình deploy/repository hiện có.
- `id`: định danh repository; quan trọng khi Maven tìm thông tin xác thực tương ứng trong phần `<servers>` của `settings.xml`.
- `url`: endpoint upload thực tế, do người vận hành repository cung cấp. Địa chỉ truy cập để tải artifact có thể khác endpoint upload.
- `name`: nhãn mô tả giúp đọc cấu hình, không có chức năng phân quyền.

Một thiết lập thực tế thường dùng `~/.m2/settings.xml` của người chạy Maven hoặc file settings được cung cấp riêng cho CI để khai báo server credentials. **`server.id` phải khớp `repository.id` hoặc `snapshotRepository.id` được sử dụng**; trong nhiều trường hợp còn cần token, chứng chỉ, quyền namespace, transport và cấu hình repository manager. Không commit mật khẩu/token vào `pom.xml` hoặc `settings.xml` nằm trong Git. Dùng kho secret và cơ chế cấp quyền phù hợp của CI.

### Phân biệt `repositories` với `distributionManagement`

Hai mục đều chứa URL repository nhưng mục đích khác:

| Cấu hình | Hướng trao đổi dữ liệu | Khi nào có tác dụng? |
| --- | --- | --- |
| `<repositories>` | Maven **tải** dependency của dự án về để build. | Trong quá trình giải quyết dependency. |
| `<pluginRepositories>` | Maven **tải** plugin và dependency của plugin. | Khi giải quyết plugin build. |
| `<distributionManagement><repository>` | Maven **upload** artifact do dự án tạo ra. | Khi thực hiện deploy theo cơ chế tương ứng. |
| `<distributionManagement><snapshotRepository>` | Maven **upload** snapshot. | Khi deploy phiên bản snapshot với cấu hình đó. |

Thêm `<repository>` vào `<repositories>` không có nghĩa Maven sẽ upload sản phẩm build lên đó. Để upload, phải có workflow publish/deploy rõ ràng.

## 9. Các lệnh Maven liên quan: kiểm tra và xuất bản

Đầu tiên, kiểm tra POM mà không xuất bản:

~~~bash
mvn validate
mvn clean package
~~~

- `validate` xác nhận những điều kiện cơ bản của model/build, ví dụ POM đọc được và các thông tin yêu cầu để khởi tạo dự án. Nó **không xác nhận** giấy phép có hiệu lực pháp lý, URL SCM tồn tại, bạn sở hữu namespace hay đã đủ điều kiện công bố lên Maven Central.
- `package` tạo artifact theo loại packaging, ví dụ `target/pom-metadata-demo-0.1.0-SNAPSHOT.jar`. Cả hai lệnh đều chưa gửi artifact đến remote repository.

Để xem cấu hình POM hiệu lực sau khi tính kế thừa từ parent, profile và mặc định của Maven Help Plugin:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

Mở `target/effective-pom.xml` và tìm `licenses`, `developers`, `scm`, `distributionManagement`. Kết quả có thể chứa thông tin kế thừa từ parent POM hoặc khai báo trong profile. **Đừng coi việc xuất hiện trường trong effective POM là bằng chứng URL và quyền truy cập thực tế đã hợp lệ.** Maven Help Plugin có thể cần tải xuống trong lần chạy đầu nếu chưa lưu cache.

Nếu muốn truy vấn một giá trị cụ thể qua Help Plugin:

~~~bash
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
~~~

Với POM mẫu, giá trị cấu hình kỳ vọng là `0.1.0-SNAPSHOT`. Tùy phiên bản plugin và tình trạng tải dependency, terminal có thể hiển thị thêm thông báo khác; kết quả này nhằm kiểm tra model dự án, không phải quyền phát hành.

### Phân biệt ba mức lưu artifact

| Lệnh | Phạm vi thao tác | Kết quả mong đợi |
| --- | --- | --- |
| `mvn package` | Build và đóng gói trong workspace. | Tạo JAR ở `target/`. |
| `mvn install` | Đi qua các pha cần thiết và cài artifact vào **repository cục bộ** của Maven. | Dự án Maven khác trên cùng môi trường có thể tham chiếu tọa độ artifact từ cache cục bộ. |
| `mvn deploy` | Đi qua các pha trước đó và thử đưa artifact/POM tới **repository từ xa** theo plugin/quy trình được cấu hình. | Có thao tác mạng và yêu cầu endpoint, xác thực, quyền, định dạng và chính sách repository phù hợp. |

**Không chạy `mvn deploy` trên POM học tập có URL giả.** Khi đã có môi trường xuất bản thực và được phép, nhóm phát hành mới cấu hình đúng đích, credential, chính sách phiên bản rồi thực hiện thao tác đó.

Một số hệ thống công bố, đặc biệt Maven Central qua **Sonatype Central Portal**, dùng plugin/quy trình publisher chuyên biệt thay vì chỉ cấu hình một `distributionManagement` thông thường. Do vậy, đừng giả định thêm một URL là đủ xuất bản lên Maven Central: cần làm theo hướng dẫn hiện hành của chính dịch vụ sử dụng.

## 10. Metadata khi chuẩn bị công bố lên Maven Central

Các kho Maven công cộng thường cần metadata đủ để người sử dụng biết cách tìm mã nguồn, giấy phép, bên duy trì và trang dự án. Với Maven Central, hãy đối chiếu yêu cầu hiện hành từ Sonatype Central Portal trước thời điểm phát hành. Những hạng mục thường cần chuẩn bị gồm:

1. **Tọa độ hợp lệ:** `groupId`, `artifactId`, `version` có tính duy nhất theo namespace được kiểm soát; không dùng `com.example` của bài minh họa để phát hành.
2. **Thông tin người dùng đọc được:** `name`, `description` và `url` có thật.
3. **Giấy phép:** `licenses` mô tả đúng quyền cấp phép của chính artifact, kèm văn bản/thông báo giấy phép liên quan.
4. **Người duy trì:** `developers` có thông tin liên hệ phù hợp để công bố.
5. **Truy vết source:** `scm` chỉ tới mã nguồn hoặc cung cấp thông tin quản lý mã nguồn hợp lệ theo chính sách repository.
6. **Artifact bổ sung:** theo yêu cầu của dịch vụ, có thể cần source JAR, Javadoc JAR, chữ ký số và metadata/checksum tương ứng.
7. **Quyền xuất bản và quy trình:** xác minh namespace, thiết lập credential/token, cấu hình plugin publisher và thực hiện bước kiểm duyệt/release của dịch vụ.

Tính sẵn có của từng plugin, chính sách signature và yêu cầu bundle thay đổi theo nhà cung cấp. Vì vậy, các mục trên là **checklist nhận thức**, không phải một file POM được đảm bảo tự xuất bản. Tài liệu chính thức để đối chiếu:

- Maven POM Reference: https://maven.apache.org/pom.html
- Sonatype Central Portal — Requirements: https://central.sonatype.org/publish/requirements/
- Sonatype Central Portal — Publishing By Using Maven: https://central.sonatype.org/publish/publish-portal-maven/

Đặc biệt, bản `-SNAPSHOT` thể hiện nhánh phát triển; nhiều kho phát hành công cộng chỉ tiếp nhận **release ổn định** và không cho thay thế nội dung phiên bản đã công bố. Quy trình xuất bản thật cần chốt version và tag source trước khi công khai, thay vì xem `mvn deploy` như một bước thử nghiệm vô hại.

## 11. Parent POM, đa module và nguồn sự thật của metadata

Trong dự án Maven có parent POM, các trường như `name`/`description`, `url`, `licenses`, `developers` hoặc `scm` có thể có giá trị kế thừa hoặc được Maven điều chỉnh theo quan hệ parent–child. Vì thế:

- Với giấy phép/tổ chức chung, **parent POM** thường là nơi hợp lý để đặt metadata dùng chung nếu mọi module cùng tuân thủ.
- Với module có website, giấy phép hoặc nhà duy trì khác, hãy khai báo đúng phạm vi ở POM con và xác minh effective POM.
- Với `scm`, đường dẫn hoặc liên kết tới module con có thể được xử lý theo cơ chế kế thừa; không tự suy ra link trên repository browser đã trỏ đúng commit của module.
- Khi phát hành nhiều artifact, cần kiểm tra **POM cuối cùng đi kèm từng artifact**, không chỉ kiểm tra parent POM trong repository.

Ví dụ một `parent` có metadata Apache-2.0 nhưng một module chứa tài nguyên bên thứ ba theo giấy phép khác: việc kế thừa thẻ `licenses` không tự giải quyết điều kiện pháp lý của những tài nguyên đó. Phải rà soát phạm vi phân phối thực tế.

## 12. Những lỗi và hiểu nhầm phổ biến

| Hiện tượng hoặc suy luận sai | Nguyên nhân/cách hiểu đúng | Cách kiểm tra |
| --- | --- | --- |
| `mvn validate` thành công, nên chắc chắn công bố được | `validate` không kiểm tra mọi yêu cầu của kho đích hoặc tính pháp lý của metadata. | Đối chiếu điều kiện repository, namespace và giấy phép; chạy kiểm tra publisher riêng. |
| `<modelVersion>4.0.0</modelVersion>` nghĩa là Maven 4 | Đây là phiên bản **mô hình POM**, không phải bản phát hành Maven CLI. | `mvn --version` để biết Maven đang chạy. |
| Thêm `<licenses>` là đã gắn giấy phép hợp pháp cho mọi file | Metadata là khai báo; quyền tác giả, văn bản LICENSE và các phụ thuộc vẫn phải được xem xét. | Đối chiếu với LICENSE, NOTICE và quyền sở hữu mã nguồn. |
| License của dependency được liệt kê trong `<licenses>` của dự án | `licenses` mô tả giấy phép áp dụng trực tiếp với artifact này. | Rà soát báo cáo dependency license riêng. |
| `<developer><id>...` cấp quyền deploy | `developer.id` là định danh metadata, không phải tài khoản xác thực. | Kiểm tra quyền trên repository, IAM và cấu hình token ngoài POM. |
| `scm.url` là Git remote đã được thiết lập | URL trong POM chỉ mô tả repository; Git remote là cấu hình Git riêng. | `git remote -v` trong đúng local repository nếu cần; không sửa Git chỉ vì metadata. |
| `scm.tag=HEAD` có nghĩa release đã được tag | `HEAD` không tự tạo tag và không chứng minh commit nguồn của bản phát hành. | Xác nhận Git tag/commit thực tế, POM phiên bản phát hành và pipeline. |
| `distributionManagement` là nơi Maven tải dependency | Đó là cấu hình deploy; dependency resolution dùng `repositories`/các nguồn khác. | Kiểm tra hai nhánh cấu hình và log tải/upload. |
| `mvn package` xong nhưng không thấy artifact ở Maven Central | `package` chỉ tạo artifact cục bộ. | Kiểm tra `target/` và workflow publish được cấp quyền. |
| Có URL deploy nhưng `mvn deploy` thất bại 401/403 | Server cần credential hoặc người dùng không có quyền. | Khớp `repository.id` với `settings.xml` và quyền thực tế; không đưa secret vào log/tệp chia sẻ. |
| Lỗi “repository not found”/404 khi deploy | Đích URL, loại release/snapshot hoặc cấu hình plugin/publisher không phù hợp. | Đối chiếu endpoint upload chính thức và version trước khi thử lại. |
| POM có XML `&` không escape | Dấu `&` là ký tự đặc biệt XML; gây lỗi parse. | Dùng `&amp;` khi muốn hiển thị dấu ampersand trong text XML. |
| Dự án đã có `developers` nhưng người dùng không tìm được hỗ trợ | Email hoặc URL không được duy trì, hoặc là dữ liệu giả. | Kiểm tra và cập nhật thông tin công bố trước release. |

Đối với lỗi metadata, một trình tự chẩn đoán hữu ích là: **kiểm tra XML/POM → xem effective POM → xác nhận URL/licensing thực tế → kiểm tra định dạng và chính sách repository → mới đánh giá log của bước publish**. Đừng vội thay JDK hoặc dependency Java khi nguyên nhân là thông tin xuất bản.

## 13. Bài thực hành và tiêu chí tự đánh giá

Trên dự án `pom-metadata-demo`:

1. Tạo POM và `Demo.java` theo mẫu; xác nhận `mvn clean package` thành công và chương trình in đúng `POM metadata demo`.
2. Chạy `mvn help:effective-pom -Doutput=target/effective-pom.xml`. Tìm từng nhóm `licenses`, `developers` và `scm` trong file kết quả.
3. Đổi `<name>` từ `POM Metadata Demo` thành `Metadata Learning Project`, chạy `mvn validate`. Xác nhận tọa độ `com.example:pom-metadata-demo:0.1.0-SNAPSHOT` **không tự đổi** theo tên dễ đọc.
4. Thêm metadata `issueManagement` và `ciManagement` theo mảnh XML ở mục 7; bảo đảm chúng là con trực tiếp của `project`.
5. Thử viết `<description>Build &amp; Publish Demo</description>` đúng cú pháp XML, rồi giải thích vì sao phải escape ký tự `&`.
6. Viết bảng mô tả đích đến của `mvn package`, `mvn install` và `mvn deploy`; chỉ thực hành hai lệnh đầu trên môi trường học, không dùng repository giả để deploy.
7. Giả định nhóm chuẩn bị phát hành bản `0.1.0`: nêu những dữ liệu cần thay (version không còn `SNAPSHOT`, SCM tag đúng, URL/liên hệ thật, xác minh license, quyền namespace, chính sách publisher).

**Câu hỏi tự kiểm tra:** Vì sao `<licenses>` khác `<distributionManagement>`? Trường `developerConnection` có cấp quyền ghi Git không? `project.url` có nhất thiết trùng `scm.url` không? `mvn validate` có bảo đảm được nhận vào Maven Central không? Khi nào cần xem `effective-pom.xml` thay vì chỉ đọc POM hiện tại?

Khi giải thích được các câu hỏi này và đối chiếu với POM đã tạo, bạn đã nắm được ranh giới quan trọng: **tọa độ xác định artifact; metadata giúp nhận diện và truy vết; cấu hình/phân quyền publishing quyết định liệu artifact có thể được công bố hay không**.
