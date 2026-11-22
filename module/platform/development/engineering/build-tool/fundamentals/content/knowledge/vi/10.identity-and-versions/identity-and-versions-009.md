# Định danh artifact theo phiên bản và truy vết về mã nguồn

Khi một dự án Java được build và publish, kết quả thường là một hoặc nhiều artifact như JAR, WAR, thư viện nguồn hoặc tài liệu. Để những project khác có thể tìm và sử dụng đúng artifact, hệ sinh thái build cần một cách định danh ổn định. Với Maven và Gradle, định danh phổ biến của một module thư viện dựa trên **group**, **artifact/module name** và **version**.

Định danh cho biết artifact thuộc nhóm nào, tên module gì và được phát hành dưới phiên bản nào. Tuy nhiên, chỉ nhìn vào tọa độ artifact chưa chắc biết được nó được tạo từ commit Git nào. Muốn truy vết từ một JAR đang chạy về mã nguồn, cần kết hợp tọa độ phiên bản với metadata build, mã commit, checksum và thông tin provenance của quá trình tạo artifact.

## 1. Artifact là gì và vì sao cần định danh?

**Artifact** là sản phẩm được tạo ra hoặc phân phối bởi một quy trình build. Trong dự án Java, artifact thường là JAR hoặc WAR; ngoài ra có thể là JAR chứa mã nguồn, JAR chứa Javadoc, file ZIP, báo cáo, SBOM hoặc một gói được publish lên repository.

Ví dụ, một thư viện xử lý đơn hàng có thể tạo ra:

```text
order-service-1.4.0.jar
order-service-1.4.0-sources.jar
order-service-1.4.0-javadoc.jar
order-service-1.4.0.pom
```

Các tệp này có liên hệ với cùng một module và phiên bản, nhưng nội dung và mục đích khác nhau. JAR chính chứa bytecode và tài nguyên của thư viện; `sources.jar` chứa mã nguồn để IDE hỗ trợ xem hoặc debug; `javadoc.jar` chứa tài liệu API; POM mô tả metadata và dependency theo định dạng Maven.

Nếu repository chỉ lưu các tệp với tên tùy ý như `latest.jar` hoặc `final-new.jar`, consumer khó xác định chính xác artifact nào cần tải, phiên bản nào đang được dùng và liệu hai tệp cùng tên có cùng nội dung hay không. Tọa độ artifact giải quyết bài toán định danh ở cấp module và phiên bản.

## 2. Tọa độ artifact: group, artifact và version

Trong Maven, định danh cơ bản của một artifact là:

```text
groupId:artifactId:version
```

Ví dụ:

```text
com.example.orders:order-service:1.4.0
```

Ba thành phần có ý nghĩa:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `groupId` | Nhóm hoặc namespace tổ chức các module có liên quan. | `com.example.orders` |
| `artifactId` | Tên module hoặc artifact trong group. | `order-service` |
| `version` | Phiên bản được publish. | `1.4.0` |

`groupId` thường được đặt theo namespace của tổ chức hoặc dự án. `artifactId` thường phản ánh tên module. Hai giá trị này không bắt buộc phải giống Java package. Ví dụ, artifact `com.example.orders:order-service` có thể chứa các package như `com.example.order.api` và `com.example.order.domain`.

### 2.1. Classifier và extension

Trong Maven repository, ngoài GAV còn có thể có **classifier** và **extension** để phân biệt các tệp artifact cùng tọa độ module/version.

- **Extension** là phần mở rộng định dạng tệp, chẳng hạn `jar`, `war`, `pom`, `zip`.
- **Classifier** phân biệt một biến thể hoặc nội dung bổ sung, chẳng hạn `sources`, `javadoc`, `tests`.

Ví dụ các artifact cùng thuộc `com.example.orders:order-service:1.4.0`:

```text
order-service-1.4.0.jar
order-service-1.4.0-sources.jar
order-service-1.4.0-javadoc.jar
order-service-1.4.0-tests.jar
```

Trong các tên trên, `sources`, `javadoc` và `tests` là classifier; `jar` là extension. Cùng GAV nhưng khác classifier hoặc extension có thể đại diện cho các tệp khác nhau.

Maven thường biểu diễn tọa độ đầy đủ theo dạng:

```text
groupId:artifactId:version[:extension[:classifier]]
```

Trong khai báo dependency Maven, phần tử `<type>` thường được dùng để xác định loại artifact và được ánh xạ sang extension/handler tương ứng; classifier là trường riêng. Vì vậy, khi làm việc với artifact đặc biệt, cần xét cả type và classifier thay vì chỉ nhìn GAV.

### 2.2. Đường dẫn artifact trong Maven repository

Maven repository tổ chức artifact theo group, artifact và version. Dấu chấm trong `groupId` được chuyển thành dấu `/` trong đường dẫn repository.

Với tọa độ:

```text
com.example.orders:order-service:1.4.0
```

đường dẫn repository dạng Maven thường là:

```text
com/example/orders/order-service/1.4.0/
├── order-service-1.4.0.jar
├── order-service-1.4.0.pom
├── order-service-1.4.0-sources.jar
└── order-service-1.4.0-javadoc.jar
```

Đường dẫn này giúp repository và build tool tìm đúng artifact khi consumer yêu cầu tọa độ tương ứng. Trong thực tế còn có thể có checksum, chữ ký, metadata và Gradle Module Metadata đi kèm.

## 3. Định danh module trong Gradle

Gradle sử dụng định danh module dạng:

```text
group:name:version
```

Ví dụ:

```text
com.example.orders:order-service:1.4.0
```

Với dependency từ Maven repository, cách viết này tương thích trực tiếp với tọa độ GAV. Trong Gradle build, `group` và `version` là thuộc tính của project; tên project thường được dùng làm artifact/module name mặc định, nhưng có thể cấu hình riêng khi publish.

Ví dụ cấu hình:

```groovy
// build.gradle
plugins {
    id 'java-library'
}

group = 'com.example.orders'
version = '1.4.0'

base {
    archivesName = 'order-service'
}
```

Các thuộc tính này giúp xác định tọa độ module khi sử dụng hoặc publish. `archivesName` điều khiển tên archive được tạo trong những trường hợp phù hợp; khi publish Maven, có thể đặt `artifactId` rõ ràng trong publication.

### 3.1. Khai báo dependency Gradle bằng tọa độ

Một project khác có thể sử dụng thư viện đã publish:

```groovy
repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.example.com/releases')
    }
}

dependencies {
    implementation 'com.example.orders:order-service:1.4.0'
}
```

Gradle tìm module theo group, name và version trong các repository được cấu hình, sau đó phân giải metadata và artifact cần thiết cho configuration tương ứng.

### 3.2. Publish một Java component lên Maven repository

Gradle có `maven-publish` plugin để publish component theo định dạng Maven repository.

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.orders'
version = '1.4.0'

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
            artifactId = 'order-service'
        }
    }

    repositories {
        maven {
            name = 'localTest'
            url = layout.buildDirectory.dir('repo').get().asFile.toURI()
        }
    }
}
```

Lệnh publish tới repository thử nghiệm cục bộ:

```bash
./gradlew publish
```

Ví dụ này tạo publication từ Java component và publish vào thư mục `build/repo`. Với repository dùng chung, hãy cấu hình URL và thông tin xác thực qua biến môi trường hoặc secret của CI theo chính sách của tổ chức. Không đưa mật khẩu hoặc token vào build script đã commit.

### 3.3. Gradle Module Metadata và POM

Khi publish qua Gradle, repository Maven có thể chứa POM và Gradle Module Metadata (`.module`). POM mô tả tọa độ, dependency và metadata theo mô hình Maven. Gradle Module Metadata có thể biểu diễn thêm thông tin variant, capability, attributes và dependency constraints mà mô hình POM không thể hiện đầy đủ.

Vì vậy, tọa độ `group:name:version` xác định module ở mức cơ bản; metadata giúp Gradle chọn biến thể phù hợp với nhu cầu consumer, chẳng hạn compile/runtime hoặc các attribute cụ thể.

## 4. Phiên bản artifact và ý nghĩa của version

Version là phần quan trọng của định danh. Nó cho consumer biết module nào đang được yêu cầu. Tuy nhiên, Maven và Gradle không tự áp đặt một chính sách phát hành duy nhất cho mọi dự án. Nhóm phát triển cần chọn quy ước version và thực thi quy ước đó trong quy trình publish.

### 4.1. Phiên bản release

Một version release thường là một giá trị ổn định, ví dụ:

```text
1.4.0
1.4.1
2.0.0
```

Nhiều nhóm áp dụng Semantic Versioning:

```text
MAJOR.MINOR.PATCH
```

- **MAJOR** tăng khi có thay đổi không tương thích theo chính sách API của dự án.
- **MINOR** tăng khi thêm chức năng tương thích ngược.
- **PATCH** tăng khi sửa lỗi tương thích ngược.

SemVer là quy ước mà dự án lựa chọn; chỉ vì version có ba phần số không có nghĩa công cụ build tự xác minh rằng thay đổi mã nguồn tuân theo đúng quy tắc tương thích.

### 4.2. Phiên bản pre-release

Trước khi phát hành chính thức, nhóm có thể publish bản thử nghiệm như:

```text
1.5.0-alpha.1
1.5.0-beta.2
1.5.0-rc.1
```

Những version này biểu thị trạng thái phát triển trước release. Cách so sánh thứ tự và lựa chọn version còn phụ thuộc quy tắc của công cụ, metadata repository và quy ước version mà dự án áp dụng. Không nên giả định mọi hệ thống đều diễn giải mọi chuỗi version giống hệt SemVer.

### 4.3. Snapshot và phiên bản phát triển

Maven thường dùng hậu tố `-SNAPSHOT` cho phiên bản đang phát triển:

```text
1.5.0-SNAPSHOT
```

Snapshot là một phiên bản phát triển có thể được publish lại khi mã nguồn thay đổi. Repository Maven có thể lưu artifact snapshot với tên có timestamp và build number, đồng thời cập nhật metadata để xác định snapshot mới nhất.

Do snapshot có thể thay đổi nội dung trong khi tọa độ logic vẫn giữ nguyên, nó phù hợp cho tích hợp trong quá trình phát triển nhưng không nên được xem như một release bất biến. Với release chính thức, nên dùng version cố định và repository áp dụng chính sách không ghi đè artifact đã phát hành.

Gradle có thể sử dụng version snapshot từ Maven repository và cũng hỗ trợ các selector động như `1.+` hoặc `latest.release`. Selector động làm kết quả phân giải có thể thay đổi theo thời điểm hoặc metadata repository. Chỉ dùng khi thực sự cần, đồng thời cân nhắc dependency locking và thời gian cache phù hợp.

### 4.4. Version cố định, version động và dependency locking

| Cách khai báo | Ví dụ | Đặc điểm |
|---|---|---|
| Version cố định | `1.4.0` | Yêu cầu đúng version logic đó. |
| Snapshot | `1.5.0-SNAPSHOT` | Phiên bản phát triển có thể được cập nhật trong repository. |
| Version động | `1.+` | Build tool chọn version phù hợp theo metadata và quy tắc resolution. |
| Version range | `[1.2,2.0)` | Yêu cầu một version nằm trong khoảng theo cú pháp được công cụ hỗ trợ. |

Trong Gradle, dependency locking có thể ghi lại phiên bản đã được phân giải để các lần build sau sử dụng cùng lựa chọn. Locking giúp ổn định lựa chọn version nhưng không tự bảo đảm một repository không ghi đè nội dung của artifact đã publish. Muốn tăng độ tin cậy, cần kết hợp release bất biến, checksum/verification và kiểm soát repository.

Trong Maven, dependency management và BOM giúp quản lý version giữa các module; Maven cũng có các cơ chế kiểm soát dependency khác. Dù dùng công cụ nào, cần biết version đã khai báo và version thực tế được phân giải có thể khác nhau khi dùng range, dynamic selector, parent hoặc BOM.

## 5. Khai báo tọa độ trong Maven

Trong `pom.xml`, project tự khai báo tọa độ của mình:

```xml
<groupId>com.example.orders</groupId>
<artifactId>order-service</artifactId>
<version>1.4.0</version>
<packaging>jar</packaging>
```

Project consumer khai báo dependency:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.orders</groupId>
        <artifactId>order-service</artifactId>
        <version>1.4.0</version>
    </dependency>
</dependencies>
```

Nếu dependency cần classifier, có thể khai báo:

```xml
<dependency>
    <groupId>com.example.orders</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0</version>
    <classifier>tests</classifier>
    <type>test-jar</type>
</dependency>
```

Ví dụ này yêu cầu test JAR được publish với classifier `tests`. Artifact test JAR cần được tạo và publish đúng cách; chỉ khai báo classifier ở consumer không tự tạo ra tệp đó.

### 5.1. Tọa độ Maven trong multi-module project

Mỗi module Maven có thể khai báo `artifactId` riêng và kế thừa `groupId` hoặc version từ parent POM. Ví dụ:

```xml
<parent>
    <groupId>com.example.orders</groupId>
    <artifactId>orders-parent</artifactId>
    <version>1.4.0</version>
</parent>

<artifactId>order-service</artifactId>
```

Tọa độ hiệu lực của module là `com.example.orders:order-service:1.4.0`. Khi parent version thay đổi, các module kế thừa có thể được cập nhật theo. Với release multi-module, cần đảm bảo các module liên quan được publish theo một bộ version nhất quán và dependency nội bộ trỏ tới đúng version.

## 6. Tọa độ artifact không phải là mã commit

Một tọa độ như:

```text
com.example.orders:order-service:1.4.0
```

cho biết module và version được công bố. Nó không tự chứa thông tin commit Git đã tạo ra JAR.

Ví dụ, một nhóm có thể build commit `abc1234`, publish `1.4.0`, sau đó vô tình build commit `def5678` và ghi đè cùng tọa độ `1.4.0` trong repository nội bộ cho phép overwrite. Tọa độ vẫn giống nhau nhưng nội dung JAR đã thay đổi. Khi đó, chỉ nhìn GAV không thể xác định chính xác source revision.

Muốn truy vết đáng tin cậy, cần liên kết các thông tin:

```text
Repository mã nguồn
       |
       v
Git commit SHA và trạng thái source tree
       |
       v
Build invocation / CI workflow / toolchain / dependency
       |
       v
Artifact coordinates (group:name:version)
       |
       v
SHA-256 digest của artifact
       |
       v
Repository URL và provenance/attestation
```

Mỗi thành phần trả lời một câu hỏi riêng:

- Tọa độ trả lời: module và version nào?
- Commit SHA trả lời: mã nguồn ở revision nào?
- Digest trả lời: tệp artifact cụ thể có byte content nào?
- Provenance trả lời: artifact được tạo bởi builder/workflow nào, từ source và material nào?
- Repository URL trả lời: artifact được lấy từ đâu?

## 7. Ghi metadata mã nguồn vào artifact

Một cách đơn giản để bắt đầu truy vết là ghi commit SHA và một số thông tin build vào metadata bên trong JAR. Java JAR hỗ trợ manifest tại `META-INF/MANIFEST.MF`.

Các trường manifest thường dùng gồm:

- `Implementation-Title`: tên module hoặc thành phần.
- `Implementation-Version`: version của artifact.
- `Build-Revision`: commit SHA được dùng để build.
- `Build-Source-Repository`: địa chỉ repository mã nguồn.

`Build-Revision` và `Build-Source-Repository` là custom attributes do dự án tự quy ước; không phải trường bắt buộc mà mọi công cụ đều tự tạo.

### 7.1. Ghi manifest bằng Gradle

CI thường cung cấp commit SHA qua biến môi trường. Ví dụ với Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
}

group = 'com.example.orders'
version = '1.4.0'

def buildRevision = providers.environmentVariable('GIT_COMMIT')
    .orElse('unknown')

tasks.named('jar') {
    manifest {
        attributes(
            'Implementation-Title': project.name,
            'Implementation-Version': project.version,
            'Build-Revision': buildRevision.get(),
            'Build-Source-Repository': 'https://git.example.com/orders/order-service'
        )
    }
}
```

Khi chạy CI, có thể truyền commit đầy đủ vào môi trường trước khi gọi Gradle. Ví dụ shell:

```bash
GIT_COMMIT="$(git rev-parse HEAD)" ./gradlew clean jar
```

Trên Windows PowerShell:

```powershell
$env:GIT_COMMIT = (git rev-parse HEAD).Trim()
.\gradlew.bat clean jar
```

Trong pipeline thật, nên dùng biến commit SHA mà hệ thống CI cung cấp cho đúng checkout đang build hoặc xác minh giá trị đó khớp `git rev-parse HEAD`. Không nên chỉ dùng tên branch vì branch có thể di chuyển theo thời gian.

### 7.2. Ghi manifest bằng Maven

Với Maven Jar Plugin, có thể đưa revision vào manifest:

```xml
<properties>
    <scm.revision>unknown</scm.revision>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifestEntries>
                        <Implementation-Title>${project.artifactId}</Implementation-Title>
                        <Implementation-Version>${project.version}</Implementation-Version>
                        <Build-Revision>${scm.revision}</Build-Revision>
                    </manifestEntries>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

CI có thể truyền revision khi chạy Maven:

```bash
./mvnw -Dscm.revision="$(git rev-parse HEAD)" clean package
```

Giá trị mặc định `unknown` giúp build local không bị lỗi khi không có biến truyền vào, nhưng artifact release nên yêu cầu revision hợp lệ. Có thể cấu hình pipeline kiểm tra biến này trước khi publish để tránh phát hành artifact không truy vết được.

### 7.3. Metadata trong JAR không thay thế provenance

Manifest thuận tiện khi cần đọc nhanh version hoặc commit từ một JAR. Tuy nhiên, metadata bên trong artifact do chính quá trình build ghi vào; nếu builder hoặc nguồn build không đáng tin cậy, nội dung metadata cũng có thể sai.

Manifest không chứng minh rằng JAR thực sự được tạo từ commit được ghi. Để tăng độ tin cậy, cần kết hợp:

- CI checkout commit cụ thể và lưu lại log của workflow.
- Build sạch trong môi trường được kiểm soát.
- Artifact digest được tính sau khi build.
- Provenance/attestation ghi nhận source, builder, workflow và artifact digest.
- Chữ ký hoặc cơ chế xác minh danh tính builder khi tổ chức yêu cầu.

## 8. SCM metadata và liên kết với repository

Build metadata nên chỉ ra nơi chứa mã nguồn và revision chính xác. Maven POM hỗ trợ khai báo thông tin SCM:

```xml
<scm>
    <connection>scm:git:https://git.example.com/orders/order-service.git</connection>
    <developerConnection>scm:git:ssh://git.example.com/orders/order-service.git</developerConnection>
    <url>https://git.example.com/orders/order-service</url>
    <tag>v1.4.0</tag>
</scm>
```

Các giá trị URL ở trên là ví dụ minh họa. `connection` mô tả kết nối SCM, `developerConnection` thường dùng cho người có quyền ghi, `url` là trang repository và `tag` ghi nhận nhãn SCM gắn với release theo quy ước của dự án.

Thông tin SCM trong POM giúp người dùng tìm repository, nhưng tag vẫn có thể di chuyển hoặc bị thay đổi nếu repository cho phép. Commit SHA đầy đủ là định danh revision chắc chắn hơn. Với Git, nên lưu cả URL repository và SHA commit; nếu build từ source tree có thay đổi chưa commit, cần ghi nhận trạng thái dirty hoặc từ chối publish release theo chính sách.

## 9. Checksum: định danh nội dung chính xác của artifact

Tọa độ version cho biết artifact logic nào được yêu cầu. Checksum cho biết nội dung byte của tệp cụ thể.

Ví dụ, sau khi tạo `order-service-1.4.0.jar`, có thể tính SHA-256:

```bash
sha256sum order-service-1.4.0.jar
```

Trên PowerShell:

```powershell
Get-FileHash .\order-service-1.4.0.jar -Algorithm SHA256
```

Giả sử kết quả là:

```text
SHA256: 8f... (64 ký tự hex)
```

Digest đầy đủ có thể dùng để so sánh artifact tải từ repository với artifact đã được CI xác nhận. Nếu cùng tọa độ `1.4.0` nhưng digest khác nhau, hai tệp không có cùng nội dung byte.

Checksum không chứng minh ai đã tạo artifact hoặc mã nguồn nào đã được dùng. Kẻ có quyền thay artifact cũng có thể thay file checksum nếu cả hai được lưu trong cùng một nơi không được bảo vệ. Vì vậy, checksum cần được lấy từ một kênh đáng tin cậy hoặc được ràng buộc trong chữ ký/attestation.

## 10. Provenance và chuỗi truy vết nguồn gốc

**Build provenance** là thông tin ghi nhận nguồn gốc và quá trình tạo ra một artifact. Một bản provenance hữu ích có thể bao gồm:

- Repository và revision nguồn (commit SHA).
- Builder, hệ thống CI và workflow đã chạy.
- Tham số hoặc cấu hình quan trọng của build.
- Các material đầu vào, chẳng hạn dependency hoặc source archive.
- Tọa độ artifact được tạo.
- Digest của artifact đầu ra.
- Thời điểm hoặc định danh lần chạy build.

Provenance giúp trả lời câu hỏi: artifact này được tạo từ source nào, bởi hệ thống nào và có đúng là artifact đã được kiểm tra không? Các định dạng attestation phổ biến có thể biểu diễn thông tin theo một schema chuẩn và được ký để consumer xác minh.

Trong quy trình bảo mật chuỗi cung ứng phần mềm, provenance thường đi cùng SBOM (Software Bill of Materials). SBOM liệt kê thành phần phần mềm được sử dụng trong sản phẩm; provenance mô tả nguồn gốc và cách artifact được tạo. Hai tài liệu bổ sung cho nhau nhưng không thay thế nhau.

Một chuỗi truy vết nên có thể đi theo cả hai chiều:

```text
Từ source đến artifact:
  commit SHA
    → CI workflow run
    → build metadata và dependency materials
    → artifact coordinate
    → artifact digest

Từ artifact về source:
  JAR / image đang triển khai
    → đọc coordinate và digest
    → tra provenance của digest
    → xác minh builder và source revision
    → mở đúng commit trong repository
```

Nếu không có provenance, metadata trong manifest vẫn là đầu mối hữu ích, nhưng mức độ tin cậy thấp hơn vì nó không tự xác minh lịch sử tạo artifact.

## 11. Tính bất biến của release và quy tắc publish

Một tọa độ release nên ánh xạ ổn định tới cùng nội dung artifact. Nếu repository cho phép ghi đè `1.4.0`, consumer có thể tải hai nội dung khác nhau ở hai thời điểm dù dependency declaration không đổi.

Một chính sách publish đáng tin cậy thường gồm:

1. Không tái sử dụng version release cho nội dung khác.
2. Dùng version snapshot hoặc version pre-release cho quá trình phát triển cần cập nhật thường xuyên.
3. Chỉ publish release sau khi test và các bước kiểm tra bắt buộc thành công.
4. Lưu digest của mọi artifact đã publish.
5. Lưu metadata commit và provenance gắn với digest.
6. Giới hạn quyền ghi repository và bật chính sách chống overwrite nếu repository hỗ trợ.

Nếu phát hiện lỗi trong `1.4.0`, cách xử lý thông thường là sửa mã, chạy kiểm tra và phát hành `1.4.1` hoặc version mới phù hợp với chính sách. Việc thay nội dung phía sau tọa độ `1.4.0` khiến lịch sử tiêu thụ và điều tra sự cố khó tin cậy.

## 12. Tái lập build và truy vết là hai mục tiêu liên quan

**Reproducible build** hướng đến việc tạo ra artifact giống nhau về byte khi build lại từ cùng source và cùng các đầu vào được kiểm soát trong môi trường tương đương. **Traceability** hướng đến việc biết artifact cụ thể đến từ source revision và quy trình nào.

Hai mục tiêu liên quan nhưng không giống nhau:

| Mục tiêu | Câu hỏi | Thông tin/cơ chế hỗ trợ |
|---|---|---|
| Định danh | Đây là module và version nào? | Group, artifact/module name, version, classifier, extension |
| Truy vết source | Được build từ commit nào? | Repository URL, commit SHA, trạng thái source tree |
| Xác định nội dung | Đây chính xác là tệp nào? | SHA-256 digest |
| Provenance | Ai/hệ thống nào tạo và từ những đầu vào nào? | CI workflow, builder identity, materials, attestation |
| Tái lập | Có thể build lại ra cùng nội dung không? | Toolchain, dependency versions, lock state, cấu hình và quy trình xác định |

Build có thể truy vết tốt nhưng không tái lập byte-for-byte nếu timestamp, thứ tự tệp hoặc thông tin môi trường được ghi vào archive theo cách không ổn định. Ngược lại, hai lần build có thể tạo cùng byte nhưng nếu không lưu commit và provenance thì vẫn khó biết artifact đến từ source revision nào.

Để cải thiện khả năng tái lập:

- Dùng Gradle Wrapper hoặc Maven Wrapper để khóa phiên bản build tool.
- Khai báo version plugin và dependency rõ ràng.
- Dùng dependency locking hoặc BOM/constraints theo nhu cầu.
- Chọn JDK/toolchain rõ ràng.
- Tránh dependency động trong release build.
- Giữ build script và đầu vào sinh mã trong version control.
- Tránh đưa thời gian hiện tại, đường dẫn tuyệt đối hoặc dữ liệu ngẫu nhiên vào artifact nếu không cần.
- Dùng cấu hình archive hỗ trợ timestamp và thứ tự entry ổn định khi mục tiêu yêu cầu byte-for-byte reproducibility.

## 13. Kiểm tra artifact sau khi publish

Sau khi publish, không nên chỉ kiểm tra rằng lệnh `publish` kết thúc thành công. Hãy xác minh artifact thực tế trong repository.

Với JAR, có thể:

```bash
# Liệt kê nội dung JAR
jar tf order-service-1.4.0.jar

# Đọc manifest
unzip -p order-service-1.4.0.jar META-INF/MANIFEST.MF

# Tính digest
sha256sum order-service-1.4.0.jar
```

Kiểm tra các điểm:

- Tọa độ và tên file có khớp version phát hành không?
- Manifest có ghi đúng commit SHA và version không?
- JAR có chứa bytecode và resource mong đợi không?
- POM hoặc Gradle Module Metadata có dependency và variant đúng không?
- Digest của artifact tải lại từ repository có khớp digest đã lưu sau build không?
- Có provenance hoặc attestation liên kết digest với commit và workflow không?

Nếu publish sources JAR, hãy xác nhận nó được tạo từ cùng source revision với JAR chính. Việc hai artifact có cùng version không tự bảo đảm chúng được tạo từ cùng một checkout nếu pipeline bị cấu hình sai.

## 14. Ví dụ quy trình release có truy vết

Giả sử nhóm phát hành thư viện `order-service` version `1.4.0`.

**Bước 1 — Chuẩn bị source revision.** Mã nguồn được commit vào Git. CI checkout commit đầy đủ `abc123...` và xác nhận working tree không có thay đổi ngoài dự kiến.

**Bước 2 — Xác định build inputs.** CI dùng Gradle Wrapper đã commit trong repository, chọn Java toolchain 21, phân giải plugin và dependency theo cấu hình đã khóa.

**Bước 3 — Build và kiểm tra.** CI chạy `clean build`, tạo JAR và các báo cáo test. Nếu một bước bắt buộc thất bại, pipeline không publish release.

**Bước 4 — Định danh artifact.** Publication được cấu hình với tọa độ `com.example.orders:order-service:1.4.0`. Repository nhận JAR, POM và có thể cả sources/Javadoc JAR.

**Bước 5 — Tính digest.** CI tính SHA-256 của từng tệp được publish và lưu digest trong metadata phát hành.

**Bước 6 — Ghi provenance.** Hệ thống tạo attestation liên kết source repository, commit SHA, workflow run, build materials và digest artifact.

**Bước 7 — Xác minh.** Consumer hoặc bước phát hành kiểm tra tọa độ, digest và chữ ký/provenance theo chính sách. Khi cần điều tra lỗi runtime, đội phát triển đọc manifest, lấy digest rồi tra provenance để tìm đúng commit.

Ví dụ ánh xạ cuối cùng:

| Thuộc tính | Giá trị minh họa |
|---|---|
| Group | `com.example.orders` |
| Artifact | `order-service` |
| Version | `1.4.0` |
| Source repository | `https://git.example.com/orders/order-service` |
| Source revision | `abc123...` |
| Build workflow | `release.yml`, run `8421` |
| Artifact file | `order-service-1.4.0.jar` |
| Artifact digest | SHA-256 được lưu trong release metadata |

Các giá trị trên chỉ minh họa cách ghi nhận. Trong hệ thống thực tế, hãy lấy revision, workflow run và digest từ chính lần build đã tạo artifact.

## 15. Lỗi thường gặp khi định danh và truy vết

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer không tìm thấy artifact | Sai group, artifact, version, repository hoặc classifier | So sánh tọa độ trong dependency declaration với cấu trúc repository. |
| Tải được JAR nhưng thiếu metadata dependency | POM không được publish hoặc publication thiếu metadata | Kiểm tra publication và tệp POM/`.module` trong repository. |
| Cùng version nhưng JAR có nội dung khác | Repository cho phép overwrite hoặc version snapshot bị cập nhật | Dùng release bất biến, digest và chính sách repository. |
| Không biết JAR đang chạy được build từ commit nào | Artifact không ghi source revision hoặc không có provenance | Ghi commit SHA vào manifest và lưu attestation liên kết digest. |
| Manifest ghi sai commit | CI lấy SHA từ branch hoặc biến không khớp checkout | Dùng SHA của commit thực tế và xác minh với `git rev-parse HEAD`. |
| Dependency resolution khác nhau giữa các máy | Dynamic version, snapshot, metadata cache hoặc repository khác nhau | Dùng version cố định, locking và kiểm soát repository. |
| Sources JAR không khớp bytecode | Sources và binary được build từ checkout khác nhau | Publish chúng trong cùng pipeline và gắn chung revision/provenance. |
| Checksum không xác minh được nguồn gốc | Checksum được tải từ cùng nơi không đáng tin cậy hoặc không có chữ ký | Xác minh digest qua kênh tin cậy và dùng attestation/chữ ký. |

## 16. Thực hành: truy vết một JAR về commit

Trong một project Java Gradle có thể publish vào Maven repository thử nghiệm, hãy thực hiện:

1. Xác định `group`, tên project/artifact và `version` trong build script.
2. Cấu hình `maven-publish` để publish Java component vào repository cục bộ.
3. Truyền commit SHA vào biến môi trường `GIT_COMMIT` trước khi chạy build.
4. Ghi `Implementation-Version` và `Build-Revision` vào JAR manifest.
5. Chạy `./gradlew clean build publish`.
6. Mở thư mục repository để tìm đường dẫn theo group/artifact/version.
7. Đọc `META-INF/MANIFEST.MF` trong JAR để xác nhận version và revision.
8. Tính SHA-256 của JAR và lưu kết quả cùng thông tin lần build.
9. Tải lại artifact từ repository và so sánh digest.
10. Thử thay đổi source, tăng version rồi publish lại; quan sát tọa độ và digest mới.

Với Maven, có thể làm tương tự bằng cách khai báo GAV trong POM, cấu hình `maven-jar-plugin` để ghi `Build-Revision`, chạy `clean verify` rồi `deploy` tới repository thử nghiệm.

Sau khi thực hành, hãy tự trả lời:

- Tọa độ GAV xác định những gì và không xác định được điều gì?
- Classifier `sources` khác version của artifact như thế nào?
- Vì sao version release không nên bị ghi đè?
- Commit SHA và SHA-256 artifact trả lời hai câu hỏi khác nhau ra sao?
- Manifest có đủ để chứng minh nguồn gốc artifact không? Vì sao?
- Dependency locking có bảo đảm byte của artifact bên ngoài không bao giờ thay đổi không?
- Provenance giúp nối source revision với artifact digest như thế nào?

## 17. Kết luận

Artifact được định danh bằng tọa độ module và version. Với Maven, tọa độ cơ bản là `groupId:artifactId:version`, có thể mở rộng bằng extension và classifier. Gradle dùng `group:name:version` cho module và có thể publish Java component thành Maven publication kèm metadata phù hợp.

Tọa độ version giúp consumer yêu cầu đúng module, nhưng không tự cho biết JAR được tạo từ commit nào hoặc nội dung byte chính xác ra sao. Để truy vết, hãy ghi source repository và commit SHA, tính digest artifact, lưu build metadata và provenance liên kết source, builder, materials với output. Kết hợp version bất biến, wrapper, toolchain và dependency management giúp artifact vừa dễ sử dụng, vừa có thể kiểm chứng và điều tra khi cần.
