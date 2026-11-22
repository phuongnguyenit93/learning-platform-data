# Chính sách phiên bản phát hành và tránh thay thế artifact đã công bố

Khi một thư viện hoặc ứng dụng Java được publish lên artifact repository, các module khác có thể tải và sử dụng nó bằng tọa độ như groupId:artifactId:version trong Maven hoặc dependency notation tương ứng trong Gradle. Từ thời điểm đó, version trở thành một phần của hợp đồng giữa producer và consumer. Nếu cùng một tọa độ được publish lại với nội dung khác, consumer có thể nhận những byte khác nhau dù dependency declaration không đổi. Một máy có cache có thể vẫn dùng file cũ, trong khi CI mới tải file vừa bị thay thế. Điều này làm build khó tái lập, gây lỗi khó giải thích và làm mất khả năng truy vết artifact.

Vì vậy, chính sách phát hành cần quy định cách đặt version, khi nào được dùng version snapshot/development, khi nào một version trở thành release bất biến và repository phải ngăn việc ghi đè artifact đã công bố như thế nào. Mỗi release cần gắn với một source revision, một build process và một tập artifact xác định. Khi phát hiện lỗi sau publish, nhóm nên phát hành version mới hoặc áp dụng quy trình thu hồi/ẩn version theo chính sách repository; không âm thầm thay nội dung dưới version cũ.

## 1. Artifact coordinates định danh một bản phát hành

Một artifact Java thường được định danh bằng các thành phần:

- groupId: nhóm hoặc namespace sở hữu artifact.
- artifactId: tên artifact/module.
- version: phiên bản của artifact.
- packaging hoặc extension: loại file, ví dụ JAR, WAR, POM.
- classifier: biến thể bổ sung, ví dụ sources, javadoc, tests hoặc một biến thể platform.

Ví dụ tọa độ Maven:

    com.example.platform:customer-client:2.4.1

Với JAR thông thường, file có thể có tên:

    customer-client-2.4.1.jar

POM tương ứng:

    customer-client-2.4.1.pom

Trong Gradle, consumer có thể khai báo:

    dependencies {
        implementation 'com.example.platform:customer-client:2.4.1'
    }

Trong Maven:

    <dependency>
        <groupId>com.example.platform</groupId>
        <artifactId>customer-client</artifactId>
        <version>2.4.1</version>
    </dependency>

Khi cùng tọa độ được sử dụng, consumer kỳ vọng nhận cùng một nội dung artifact. Vì vậy, một release version nên đại diện cho đúng một nội dung đã được công bố. Nếu build lại từ source khác rồi publish đè lên tọa độ đó, tên dependency vẫn không đổi nhưng bytecode, resource hoặc metadata có thể thay đổi.

### 1.1. Tên file giống nhau không đủ để xác định artifact

Hai file cùng tên customer-client-2.4.1.jar có thể có nội dung khác nhau. Để xác định chính xác một artifact, cần kết hợp tọa độ với checksum, nguồn repository và metadata build. Trong quy trình phát hành, nên ghi nhận:

- Tọa độ đầy đủ và classifier/extension.
- Source commit hoặc tag đã tạo artifact.
- Build run ID và toolchain.
- SHA-256 của từng file được publish.
- Repository đích và thời điểm publish.
- Chữ ký/provenance nếu tổ chức sử dụng.

### 1.2. Các file của một release phải nhất quán

Một release thường gồm nhiều file liên quan: binary JAR, POM/module metadata, sources JAR, Javadoc JAR, checksum và signature. Không nên thay một file trong nhóm mà không kiểm soát các file còn lại. Ví dụ, thay JAR nhưng giữ POM cũ có thể khiến dependency graph hoặc metadata không khớp với binary mới.

Với Gradle Module Metadata, variant và dependency information có thể được công bố thêm bên cạnh POM. Chính sách bất biến phải áp dụng cho toàn bộ nội dung tại tọa độ/version đó, không chỉ file JAR chính.

## 2. Vì sao không được thay nội dung của release đã công bố?

Giả sử hai CI job cùng publish com.example:payments:3.1.0. Job đầu tạo file có SHA-256 là aaa...; job thứ hai chạy trên một commit khác và ghi đè bằng file có SHA-256 là bbb....

~~~mermaid
flowchart TD
    A["Consumer A resolve payments:3.1.0"] --> B["Nhận JAR nội dung X"]
    C["Producer publish lại payments:3.1.0"] --> D["Repository thay bằng nội dung Y"]
    E["Consumer B resolve payments:3.1.0"] --> F["Nhận JAR nội dung Y"]
    B --> G["Cùng tọa độ, khác byte"]
    F --> G
~~~

Những hệ quả thường gặp:

- **Build không tái lập:** cùng source và dependency declaration có thể cho kết quả khác tùy thời điểm resolve.
- **Cache không nhất quán:** máy có cache giữ artifact cũ; máy cache trống tải artifact mới.
- **Khó điều tra sự cố:** log chỉ ghi version, không đủ xác định binary thực tế đã chạy.
- **Sai lệch checksum/signature:** checksum hoặc chữ ký đã lưu có thể không còn khớp file mới.
- **Rủi ro supply chain:** kẻ có quyền ghi repository có thể thay nội dung của một release đã được tin cậy.
- **Ảnh hưởng dây chuyền:** nhiều ứng dụng đang dùng cùng version có thể nhận hành vi khác nhau mà không thay dependency declaration.
- **Khó rollback:** nhóm không còn một tọa độ ổn định để tham chiếu lại nội dung cũ.

Release bất biến giúp version có ý nghĩa lâu dài: khi consumer khai báo 3.1.0, họ luôn nhận cùng artifact đã được phê duyệt.

## 3. Chính sách versioning

Versioning là quy tắc đặt tên cho các bản phát hành và truyền đạt mức độ thay đổi. Chính sách cần phù hợp với loại sản phẩm, public API, cách consumer nâng cấp và quy trình release.

### 3.1. Semantic Versioning

Semantic Versioning (SemVer) sử dụng dạng:

    MAJOR.MINOR.PATCH

Ví dụ: 2.4.1.

- **MAJOR:** thay đổi không tương thích ngược trong public API hoặc contract đã công bố.
- **MINOR:** thêm chức năng tương thích ngược.
- **PATCH:** sửa lỗi tương thích ngược, không cố ý phá vỡ contract.

Với thư viện Java, các thay đổi cần cân nhắc gồm public class/method, constructor, visibility, kiểu tham số/trả về, exception behavior, serialization format, annotation contract và dependency được lộ qua public API.

SemVer hữu ích khi nhóm có thể xác định rõ public API và cam kết compatibility. Nếu artifact là ứng dụng triển khai nội bộ, schema/data migration hoặc deployment contract có thể quan trọng hơn chữ ký Java; nhóm cần ghi rõ quy tắc version tương ứng.

### 3.2. Pre-release versions

SemVer cho phép nhãn prerelease sau dấu gạch nối:

    2.5.0-alpha.1
    2.5.0-beta.2
    2.5.0-rc.1

Các bản alpha/beta/rc thể hiện trạng thái chưa phải release ổn định. Chúng có thể được dùng để thử nghiệm với consumer trước khi phát hành version chính thức.

Theo quy tắc SemVer, prerelease có precedence thấp hơn version release tương ứng. Ví dụ 2.5.0-rc.1 đứng trước 2.5.0. Cách so sánh version thực tế còn phụ thuộc quy tắc của package manager/repository, do đó không nên giả định mọi công cụ xử lý mọi chuỗi version giống hệt SemVer.

### 3.3. Build metadata

SemVer cho phép build metadata sau dấu cộng, ví dụ 2.5.0+build.184. Metadata này không làm thay đổi precedence theo SemVer. Tuy nhiên, Maven version comparison và cách repository chuẩn hóa version có quy tắc riêng. Trước khi đưa chuỗi chứa dấu cộng vào artifact coordinates, cần xác nhận tương thích với Maven, Gradle và repository manager. Với CI build cần version duy nhất, một prerelease identifier như 2.5.0-dev.184 hoặc một version nội bộ theo quy ước của tổ chức thường dễ kiểm soát hơn.

### 3.4. Version theo lịch hoặc build number

Một số sản phẩm dùng Calendar Versioning (CalVer), ví dụ 2026.11.0, hoặc version nội bộ kết hợp build number/commit. Cách này có thể phù hợp với ứng dụng phát hành thường xuyên hoặc sản phẩm không cam kết SemVer.

Điều quan trọng là phải công bố quy tắc:

- Thành phần nào biểu thị năm/tháng hoặc release train?
- Version nào được xem là tương thích?
- Bản hotfix được đặt tên ra sao?
- Build thử nghiệm và release ổn định khác nhau thế nào?
- Version có tăng đơn điệu không?

Không nên đổi hệ versioning tùy tiện giữa các release vì consumer và công cụ quản lý dependency cần hiểu thứ tự nâng cấp.

## 4. Release version và snapshot/development version

Một chính sách phổ biến là phân biệt version phát triển có thể thay đổi với release version bất biến.

| Loại version | Ví dụ | Tính chất thường dùng |
|---|---|---|
| Development/Snapshot | 2.5.0-SNAPSHOT | Có thể được cập nhật trong repository snapshot |
| Alpha/Beta/RC | 2.5.0-rc.1 | Bản prerelease riêng, nên có tọa độ duy nhất |
| Release | 2.5.0 | Bất biến sau khi công bố |
| Hotfix | 2.5.1 | Release mới sửa lỗi từ bản trước |

### 4.1. Maven SNAPSHOT

Trong Maven, version kết thúc bằng -SNAPSHOT biểu thị phiên bản phát triển. Repository Maven có thể lưu snapshot bằng tên timestamped/build number và metadata cho biết snapshot mới nhất.

Consumer khai báo:

    <dependency>
        <groupId>com.example.platform</groupId>
        <artifactId>customer-client</artifactId>
        <version>2.5.0-SNAPSHOT</version>
    </dependency>

Maven có thể resolve snapshot mới hơn theo metadata repository và update policy. Do snapshot có thể thay đổi, hai lần build ở thời điểm khác nhau có thể nhận binary khác nhau dù POM consumer không đổi.

Snapshot phù hợp cho tích hợp phát triển giữa các module chưa phát hành. Không nên dùng snapshot mutable làm dependency nền tảng cho một release production cần tái lập.

### 4.2. Gradle development version

Gradle không bắt buộc phải dùng hậu tố -SNAPSHOT, nhưng nhiều repository và nhóm dùng quy ước tương tự. Có thể dùng version prerelease hoặc version riêng cho build thử nghiệm. Với dependency được đánh dấu changing module hoặc version động, Gradle có thể cần kiểm tra lại metadata theo cache policy.

Ví dụ:

    dependencies {
        implementation 'com.example.platform:customer-client:2.5.0-SNAPSHOT'
    }

Khi dùng version có thể thay đổi, hãy hiểu changing semantics, cache TTL và repository metadata policy. Đừng nhầm việc đặt hậu tố SNAPSHOT với một cơ chế đảm bảo mọi lần resolve tự động nhận nội dung mới ngay lập tức.

### 4.3. Snapshot repository và release repository

Nên tách repository hoặc ít nhất tách policy cho snapshot và release:

- Snapshot repository cho phép cập nhật version phát triển theo quy tắc.
- Release repository từ chối redeploy cùng tọa độ/version.
- Consumer production chỉ resolve release repository theo policy.
- Consumer development có thể thêm snapshot repository khi cần.

Tách repository giúp tránh publish nhầm snapshot vào nơi chứa release ổn định và giúp áp dụng retention khác nhau.

### 4.4. Không dùng một version release cho nhiều commit

Nếu 2.5.0 đã được publish từ commit A, commit B không được publish đè lên 2.5.0. Nếu commit B chứa sửa lỗi cần phát hành, hãy tạo 2.5.1 (hoặc version mới theo chính sách). Điều này giữ lịch sử release rõ ràng.

## 5. Quy tắc bất biến trong artifact repository

Chính sách version chỉ hiệu quả khi repository manager thực thi được quy tắc ghi. Build script có thể kiểm tra version, nhưng nơi lưu artifact cần từ chối thao tác redeploy release.

### 5.1. Disable redeploy cho release repository

Repository manager thường có thiết lập tương đương:

- Release repository: không cho phép redeploy/redeployment.
- Snapshot repository: cho phép cập nhật snapshot theo policy.
- Staging repository: nhận candidate release trước khi promote.

Tên tùy chọn khác nhau theo sản phẩm, nhưng mục tiêu giống nhau: một release coordinate đã được publish không thể bị ghi đè bằng file khác.

### 5.2. Không xóa rồi publish lại cùng version để sửa lỗi

Xóa artifact cũ rồi upload lại cùng version vẫn phá vỡ tính bất biến. Consumer có thể đã cache file cũ, mirror có thể giữ metadata cũ và checksum/signature trước đó có thể còn được lưu ở nơi khác.

Khi release có lỗi, hãy:

1. Giữ nguyên artifact đã công bố để phục vụ điều tra và truy vết.
2. Xác định source/commit gây lỗi.
3. Sửa code hoặc build configuration.
4. Tăng version theo chính sách.
5. Chạy lại release pipeline.
6. Công bố release mới và thông báo migration/upgrade.

Nếu cần ngăn consumer mới tải version lỗi, repository có thể hỗ trợ quarantine, yanking hoặc block download theo chính sách. Thao tác đó khác với thay binary dưới cùng tọa độ.

### 5.3. Tài khoản publish phải có quyền tối thiểu

Developer thông thường không cần quyền ghi release repository. Có thể phân quyền:

- Developer: đọc release và snapshot; ghi snapshot nếu được phép.
- CI branch tin cậy: ghi snapshot hoặc prerelease.
- Release pipeline: publish/promote release sau khi đạt gate.
- Repository administrator: quản lý policy, retention và quyền.

Credential publish không nên được cấp cho mọi pull request hoặc job chạy code không tin cậy.

### 5.4. Audit log và retention

Repository manager nên lưu ai publish, khi nào, từ pipeline nào và vào repository nào. Audit log giúp điều tra khi artifact có checksum bất thường hoặc có thao tác publish ngoài quy trình.

Không xóa release artifact đã phát hành chỉ vì đã có version mới hơn. Consumer có thể vẫn phụ thuộc version cũ, cần rollback hoặc cần tái tạo một build lịch sử. Retention cần phù hợp với chính sách lưu trữ và pháp lý của tổ chức.

## 6. Cấu hình Maven để tách snapshot và release

Maven POM có thể khai báo repository đích cho release và snapshot trong distributionManagement.

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.com/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>internal-snapshots</id>
        <url>https://repo.example.com/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

id phải khớp với server entry trong Maven settings của môi trường publish:

~~~xml
<settings>
    <servers>
        <server>
            <id>internal-releases</id>
            <username>USERNAME_INJECTED_BY_CI</username>
            <password>SECRET_INJECTED_BY_CI</password>
        </server>
        <server>
            <id>internal-snapshots</id>
            <username>USERNAME_INJECTED_BY_CI</username>
            <password>SECRET_INJECTED_BY_CI</password>
        </server>
    </servers>
</settings>
~~~

Các giá trị username/password trong ví dụ là placeholder; CI nên tạo/cung cấp settings file từ secret store hoặc dùng cơ chế credentials của nền tảng. Không commit file có token thật vào repository.

### 6.1. Maven chọn repository theo version

Với 2.5.0-SNAPSHOT, Maven deploy vào snapshotRepository. Với release version như 2.5.0, Maven deploy vào repository. Repository manager vẫn phải cấu hình chính sách redeploy riêng; distributionManagement chỉ chỉ ra đích publish, không tự bảo đảm artifact bất biến.

### 6.2. Pin Maven plugin versions

Release process nên pin version của Maven Deploy Plugin, Compiler Plugin, Release Plugin và các plugin tạo metadata/package. Nếu plugin version thay đổi ngầm, cùng source có thể được publish với cách đóng gói hoặc metadata khác.

Ví dụ khai báo plugin version:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-deploy-plugin</artifactId>
            <version>3.1.3</version>
        </plugin>
    </plugins>
</build>
~~~

Version ở đây là ví dụ. Dự án nên dùng version đã được kiểm thử với Maven/JDK của mình và quản lý tập trung trong parent POM hoặc pluginManagement.

### 6.3. Không deploy release từ mọi pull request

Pull request thường nên chạy verify/test và có thể publish snapshot hoặc artifact tạm trong một repository riêng. Release repository chỉ nên được ghi bởi pipeline phát hành có điều kiện rõ ràng, ví dụ tag hợp lệ, branch được bảo vệ, required checks pass và quyền publish được cấp.

## 7. Cấu hình Gradle để publish version có kiểm soát

Gradle maven-publish tạo publication từ component Java và gửi artifact đến Maven repository. Version của project là một phần của tọa độ.

Ví dụ:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.platform'
version = providers.gradleProperty('releaseVersion')
    .orElse('2.5.0-SNAPSHOT')
    .get()

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            name = 'internal'
            url = uri(
                version.toString().endsWith('-SNAPSHOT')
                    ? 'https://repo.example.com/maven-snapshots/'
                    : 'https://repo.example.com/maven-releases/'
            )
            credentials {
                username = System.getenv('REPO_USER')
                password = System.getenv('REPO_TOKEN')
            }
        }
    }
}
~~~

Đây là ví dụ cấu hình theo quy ước version. Với build thực tế, nên lấy releaseVersion từ pipeline/tag đã xác minh, tách URL release/snapshot rõ ràng và không đưa credentials vào source. Repository manager phải từ chối redeploy release version ngay cả khi build script chọn nhầm hoặc bị thay đổi.

Publish:

~~~bash
# Publish snapshot theo version mặc định trong ví dụ
./gradlew publish

# Publish version được pipeline truyền vào
./gradlew publish -PreleaseVersion=2.5.0
~~~

Lệnh publish có side effect lên repository. Chỉ chạy trong job có quyền và điều kiện phù hợp. Trước khi publish, pipeline cần xác nhận version chưa tồn tại hoặc repository sẽ từ chối nếu đã có.

### 7.1. Tách version của project khỏi version của build thử nghiệm

Không nên để mọi local build tự động dùng version release chính thức. Có thể dùng SNAPSHOT, prerelease identifier hoặc build number riêng cho artifact thử nghiệm. Pipeline release sẽ lấy version từ tag đã được xác minh và kiểm tra rằng tọa độ đó chưa được sử dụng.

### 7.2. Multi-module versioning

Trong multi-project build, các module có thể dùng cùng version hoặc version độc lập. Nếu phát hành cùng một sản phẩm/BOM, dùng version alignment thường giúp consumer hiểu một release bao gồm những module nào. Nếu module có vòng đời độc lập, có thể version riêng nhưng cần quản lý dependency compatibility rõ ràng.

Không publish hai binary khác nhau dưới cùng tọa độ module/version chỉ vì chúng được build từ hai nhánh khác nhau.

## 8. Quy trình release từ source revision đến repository

Một release đáng tin cậy nên có chuỗi bước có thể truy vết:

~~~mermaid
flowchart TD
    A["Chọn commit và tạo release tag"] --> B["Xác minh version và working tree"]
    B --> C["Build sạch bằng Wrapper/toolchain đã pin"]
    C --> D["Compile, test và quality gates"]
    D --> E["Tạo candidate artifacts"]
    E --> F["Kiểm tra tọa độ chưa được phát hành"]
    F --> G["Publish vào staging"]
    G --> H["Kiểm tra POM, metadata, checksum và signature"]
    H --> I{"Được duyệt?"}
    I -->|Không| J["Hủy staging candidate và sửa version/source"]
    I -->|Có| K["Promote sang release repository"]
    K --> L["Lưu provenance và thông báo release"]
~~~

### 8.1. Chọn source revision

Release cần gắn với một commit/tag xác định. Nên dùng tag được bảo vệ hoặc quy trình release branch rõ ràng. Tránh publish từ working tree có thay đổi chưa commit.

### 8.2. Xác minh version

Pipeline cần kiểm tra version tuân theo quy tắc của sản phẩm, version khớp với release tag hoặc metadata release, không phải version snapshot nếu đang publish vào release repository, tọa độ/version chưa được sử dụng và các module/BOM liên quan có version alignment phù hợp.

### 8.3. Build và kiểm chứng

Chạy clean verification với Wrapper/JDK/plugin đã pin. Bao gồm compile, unit/integration tests cần thiết, static analysis, coverage và security checks theo release policy.

### 8.4. Staging repository

Staging cho phép publish candidate trước khi công bố rộng rãi. Nhóm có thể kiểm tra nội dung, metadata, dependency graph và chữ ký. Sau khi đạt yêu cầu, staging repository được promote hoặc release theo cơ chế repository manager.

Staging giúp tránh để consumer nhìn thấy một release chưa hoàn chỉnh trong lúc nhiều file đang được upload. Nếu publish thất bại giữa chừng, có thể đóng/hủy staging candidate và tạo lại theo quy trình mà không thay đổi release đã công bố.

### 8.5. Publish/promote một lần

Sau khi candidate được phê duyệt, promote vào release repository. Release repository nên từ chối redeploy. Nếu pipeline bị retry sau khi publish thành công nhưng response bị timeout, bước retry cần kiểm tra tọa độ và checksum trước khi thực hiện lại; không giả định upload lần hai là an toàn.

## 9. Release tag, version và artifact phải khớp nhau

Một quy ước phổ biến là tag Git v2.5.0 tương ứng với artifact version 2.5.0. Prefix v là quy ước của Git tag, không nhất thiết xuất hiện trong Maven/Gradle coordinates.

Ví dụ:

    Git tag: v2.5.0
    Maven version: 2.5.0
    Artifact: com.example.platform:customer-client:2.5.0

Pipeline có thể lấy version từ tag, bỏ prefix đã quy định, rồi truyền vào build. Cần xác minh tag là tag hợp lệ và trỏ tới commit được phép phát hành.

### 9.1. Không để version được nhập độc lập ở nhiều nơi

Nếu version nằm trong gradle.properties, pom.xml, release tag, Docker tag và manifest nhưng mỗi nơi được cập nhật thủ công, chúng có thể lệch nhau. Hãy chọn một nguồn version chính và sinh/kiểm tra các giá trị còn lại từ nguồn đó.

### 9.2. Tag bất biến

Tag release nên được bảo vệ và không di chuyển sang commit khác. Nếu tag v2.5.0 đã được dùng để publish, không force-update tag để trỏ sang commit khác. Nếu cần sửa release, tạo tag/version mới theo chính sách.

### 9.3. Version của container image

Container image thường được gắn tag version và digest. Tag có thể bị cập nhật nếu registry cho phép; digest định danh nội dung image. Release process nên lưu digest và dùng digest khi cần triển khai chính xác cùng image đã kiểm chứng.

## 10. Checksum, signature và provenance

Tính bất biến của repository giúp tọa độ ổn định. Checksum, chữ ký và provenance bổ sung khả năng xác minh nội dung và nguồn gốc.

### 10.1. Checksum

SHA-256 có thể xác nhận file tải về có cùng nội dung với file đã ghi nhận:

~~~bash
sha256sum customer-client-2.5.0.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'customer-client-2.5.0.jar'
~~~

Checksum phát hiện khác biệt byte, nhưng nếu checksum được tải từ cùng một nguồn đã bị xâm nhập thì nó không tự chứng minh nguồn gốc đáng tin cậy.

### 10.2. Chữ ký số

Chữ ký số cho phép consumer xác minh artifact được ký bởi identity sở hữu khóa tương ứng và nội dung không bị thay đổi sau khi ký. Quy trình cần bảo vệ private key, quản lý key rotation và công bố public key/fingerprint qua kênh đáng tin cậy.

Không lưu private signing key trong repository hoặc log CI. Có thể dùng signing service hoặc secret manager/HSM theo chính sách tổ chức.

### 10.3. Provenance

Provenance mô tả artifact được tạo từ source revision nào, bởi build definition/tool nào, trong môi trường và identity nào. Với release, nên liên kết artifact digest với repository và commit SHA, release tag/version, CI workflow và run ID, JDK/build tool/plugin quan trọng, dependency/SBOM nếu có và identity của pipeline tạo artifact.

Provenance giúp điều tra và xác minh chuỗi tạo artifact. Nó không thay thế repository immutability hoặc chữ ký.

### 10.4. SBOM

Software Bill of Materials liệt kê dependency/thành phần trong sản phẩm. SBOM giúp nhóm biết release chứa thư viện nào để đánh giá lỗ hổng hoặc license. SBOM nên được gắn với đúng artifact digest/version; một SBOM của commit khác không thể đại diện cho binary đã publish.

## 11. Version conflict và dependency resolution

Khi nhiều module yêu cầu các version khác nhau của cùng dependency, Gradle/Maven có thể chọn version theo quy tắc resolution. Điều này không nên được dùng để che giấu việc release artifact bị ghi đè.

### 11.1. Gradle dependency constraints và platforms

Gradle có thể dùng platform/BOM hoặc constraints để căn chỉnh version:

~~~groovy
dependencies {
    implementation platform('com.example.platform:platform-bom:2.5.0')
    implementation 'com.example.platform:customer-client'
}
~~~

BOM giúp quản lý một tập version tương thích. Version của BOM cũng cần bất biến. Khi phát hành BOM mới, tăng version của BOM thay vì thay nội dung dưới version đã công bố.

### 11.2. Maven dependencyManagement

Maven có thể quản lý version tập trung:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.platform</groupId>
            <artifactId>customer-client</artifactId>
            <version>2.5.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Consumer có thể khai báo dependency mà không lặp lại version. Tuy nhiên, dependencyManagement chỉ quản lý version mặc định; module vẫn phải khai báo dependency thực sự cần dùng.

### 11.3. Tránh dynamic versions trong release

Các khai báo như 1.+, latest.release, version range hoặc changing modules có thể resolve sang version khác theo thời gian. Chúng có thể tiện trong development nhưng làm giảm khả năng tái lập của release build.

Release pipeline nên resolve dependency theo version đã pin hoặc lock, lưu dependency tree/SBOM và xác minh checksum. Không dựa vào việc repository tình cờ trả về cùng một version trong mọi lần chạy.

## 12. Sửa lỗi sau khi release

Nếu phát hiện bug sau khi publish, cách xử lý phụ thuộc mức độ nghiêm trọng và khả năng tương thích.

### 12.1. Phát hành patch version

Nếu sửa lỗi tương thích ngược, phát hành patch version mới. Ví dụ:

    2.5.0  ->  2.5.1

Consumer nâng dependency có chủ đích. Release 2.5.0 vẫn giữ nguyên nội dung để những hệ thống đã dùng nó có thể tái tạo build.

### 12.2. Phát hành minor/major version

Nếu cần thêm API tương thích ngược, có thể tăng MINOR. Nếu thay đổi contract không tương thích, tăng MAJOR. Nhóm cần ghi migration notes và hướng dẫn nâng cấp cho consumer.

### 12.3. Yanking, quarantine hoặc block download

Repository manager hoặc registry có thể hỗ trợ đánh dấu version lỗi, ẩn khỏi kết quả mới hoặc chặn tải. Việc này giúp giảm khả năng consumer mới chọn version đó, nhưng không làm biến mất artifact khỏi các máy đã cache và không sửa dependency declaration đã pin.

Không nên xóa lịch sử release một cách tùy tiện. Hãy ghi nhận lý do, phạm vi ảnh hưởng và version thay thế.

### 12.4. Rollback

Rollback thường có nghĩa triển khai lại một artifact version trước đó đã biết là ổn định, hoặc revert source change rồi phát hành version mới theo quy trình. Với thư viện, consumer có thể pin về version trước nếu tương thích. Với database schema hoặc stateful application, rollback còn cần migration strategy riêng.

## 13. Các tình huống dễ làm ghi đè artifact ngoài ý muốn

| Tình huống | Rủi ro | Kiểm soát |
|---|---|---|
| CI retry publish sau timeout | Không biết lần đầu đã ghi thành công chưa | Kiểm tra tọa độ/checksum trước khi retry |
| Hai pipeline cùng release một version | Race condition và file bị thay thế | Single release job/lock và repository redeploy policy |
| Developer publish từ local | Artifact thiếu provenance hoặc sai commit | Giới hạn quyền publish release cho CI |
| Version lấy từ biến môi trường tùy ý | Nhiều commit dùng cùng version | Lấy version từ tag/release metadata đã xác minh |
| Snapshot bị consumer dùng như release | Dependency thay đổi theo thời gian | Tách snapshot/release repository và policy |
| Xóa release rồi upload lại | Cache/mirror/checksum không nhất quán | Tăng version mới, giữ lịch sử |
| Publish JAR và POM không đồng bộ | Metadata mô tả sai binary | Staging, kiểm tra publication hoàn chỉnh trước promote |
| Tag release bị di chuyển | Source tag không còn khớp artifact | Bảo vệ tag và lưu commit SHA |
| Repository cho redeploy | Cùng tọa độ có nhiều nội dung | Disable redeploy cho release repository |

## 14. Thiết kế CI release pipeline có tính bất biến

Một pipeline phát hành nên tách rõ verify và publish:

1. Pull request: compile/test/quality checks; không ghi release repository.
2. Main branch: kiểm chứng tích hợp, có thể publish snapshot/prerelease.
3. Release tag: xác minh tag, version và commit; chạy clean verification.
4. Candidate: tạo publication vào staging repository.
5. Validation: kiểm tra artifact coordinates, POM/metadata, checksum, signature và SBOM.
6. Promotion: promote candidate đã được duyệt vào release repository.
7. Record: lưu release manifest, provenance và checksum.
8. Notify: cung cấp release notes và version mới cho consumer.

### 14.1. Kiểm tra version tồn tại trước publish

Pipeline có thể truy vấn repository manager hoặc dùng API của nó để kiểm tra tọa độ/version. Đây là bước hỗ trợ phát hiện sớm. Repository manager vẫn cần chặn redeploy vì hai pipeline có thể kiểm tra đồng thời và cùng thấy version chưa tồn tại.

### 14.2. Xử lý publish không hoàn chỉnh

Nếu upload nhiều file và một file thất bại, không nên để consumer thấy một publication nửa vời. Staging repository hoặc transaction/promotion mechanism giúp giữ candidate chưa công bố cho đến khi tất cả file cần thiết đã có và được kiểm tra.

Nếu backend không có staging, cần có quy trình publish tuần tự, kiểm tra đầy đủ file và quyền hạn chế truy cập cho đến khi publication hoàn chỉnh.

### 14.3. Retry phải idempotent theo nội dung

Publish step có thể bị timeout sau khi server đã nhận file. Khi retry, pipeline cần xác định tọa độ đã tồn tại chưa, checksum trên repository có trùng artifact vừa build không, publication đã hoàn tất hay chỉ có một phần file và repository có policy từ chối redeploy không.

Nếu cùng version đã tồn tại với checksum giống hệt, pipeline có thể ghi nhận lần publish trước đã thành công theo policy. Nếu checksum khác, dừng và điều tra; không cố ghi đè.

## 15. Ví dụ quy tắc version cho thư viện Java

Giả sử thư viện customer-client có public API và phát hành theo SemVer:

| Thay đổi | Version trước | Version sau |
|---|---:|---:|
| Sửa lỗi xử lý null, không đổi API | 2.5.0 | 2.5.1 |
| Thêm method mới tương thích ngược | 2.5.1 | 2.6.0 |
| Xóa method public đã công bố | 2.6.0 | 3.0.0 |
| Thay đổi type của tham số public | 2.6.0 | 3.0.0 |
| Bản thử nghiệm trước release | 2.7.0 | 2.7.0-rc.1 |

Đây là ví dụ áp dụng SemVer. Với thay đổi hành vi, serialization, transitive dependency hoặc runtime requirement, cần đánh giá compatibility thực tế thay vì chỉ nhìn chữ ký Java.

Một release process có thể tuân theo:

    main branch:
      2.7.0-SNAPSHOT

    release candidate:
      2.7.0-rc.1
      2.7.0-rc.2

    stable release:
      2.7.0

    bug fix sau phát hành:
      2.7.1

Mỗi prerelease có tọa độ riêng và không được thay nội dung tùy tiện sau khi đã công bố. Nếu cần một candidate mới, tăng identifier như rc.2.

## 16. Checklist trước và sau khi publish

Trước publish:

- Version tuân theo chính sách của artifact.
- Release tag trỏ tới commit chính xác và không bị di chuyển.
- Working tree/build input được kiểm soát.
- Wrapper, JDK, plugin và dependency được pin theo policy.
- Clean verification và required quality gates đều pass.
- Release coordinates chưa được dùng.
- Candidate artifacts được tạo một lần từ source đã xác định.
- POM/Gradle metadata, classifier và file bổ sung đầy đủ.
- Repository đích là snapshot, staging hay release đúng mục đích.
- Job có quyền publish tối thiểu; secret không bị lộ.

Sau publish:

- Artifact có thể được resolve từ repository bằng tọa độ dự kiến.
- Checksum trên repository khớp file candidate.
- Signature/provenance/SBOM được lưu nếu policy yêu cầu.
- Release manifest liên kết version với commit và CI run.
- Release repository từ chối redeploy cùng version.
- Release notes nêu thay đổi, compatibility và hướng nâng cấp.
- Consumer được cung cấp version mới và hướng dẫn migration khi cần.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Có thể publish lại cùng version nếu chỉ sửa một lỗi nhỏ | Cùng tọa độ/version phải đại diện cho cùng nội dung; sửa lỗi cần version mới |
| Snapshot và release chỉ khác tên | Snapshot có thể thay đổi theo metadata/update policy; release cần bất biến |
| distributionManagement tự ngăn redeploy | Nó chọn repository đích; repository manager phải thực thi redeploy policy |
| Xóa version cũ rồi upload lại là an toàn | Cache, mirror, checksum và consumer hiện hữu có thể giữ nội dung cũ |
| Cùng tên JAR nghĩa là cùng artifact | Cần checksum và metadata để xác nhận nội dung |
| Chỉ cần SemVer cho mọi loại sản phẩm | Version scheme phải phản ánh contract và vòng đời của sản phẩm |
| Checksum tự chứng minh nguồn gốc | Checksum xác nhận nội dung; chữ ký/provenance giúp xác minh identity và quy trình |
| CI retry publish luôn an toàn | Cần kiểm tra tọa độ và checksum vì lần đầu có thể đã thành công |
| Release tag có thể di chuyển nếu cần hotfix | Tag đã dùng để phát hành nên bất biến; hotfix dùng tag/version mới |
| Publish thành công nghĩa là mọi file publication hoàn chỉnh | Cần kiểm tra POM, metadata, classifier, signature và staging/promotion |

Chính sách phiên bản phát hành xác định ý nghĩa của từng version và cách consumer nâng cấp. Release artifact phải bất biến: cùng tọa độ/version luôn đại diện cho cùng nội dung. Snapshot hoặc development version có thể thay đổi trong repository riêng theo update policy; release version phải được bảo vệ bằng quy tắc từ chối redeploy ở repository manager. CI nên phát hành từ commit/tag xác định, chạy đầy đủ verification, publish candidate vào staging, kiểm tra checksum/metadata/signature rồi mới promote. Khi phát hiện lỗi, phát hành version mới hoặc áp dụng cơ chế quarantine/yank theo policy, giữ lịch sử artifact cũ để có thể truy vết và rollback. Điều đó giúp build tái lập, dependency resolution đáng tin cậy và mỗi release có nguồn gốc rõ ràng.
