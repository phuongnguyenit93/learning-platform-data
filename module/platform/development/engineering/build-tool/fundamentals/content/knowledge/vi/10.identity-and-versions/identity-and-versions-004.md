# Phiên bản phát hành ổn định và phiên bản đang phát triển

Một thư viện hoặc ứng dụng Java thường trải qua nhiều lần thay đổi trước khi được phát hành. Trong lúc phát triển, nhóm có thể cần chia sẻ bản build mới để kiểm thử, tích hợp hoặc nhận phản hồi. Khi đã phát hành, người dùng cần một phiên bản có định danh rõ ràng và có thể tải lại với cùng nội dung.

Vì vậy, dự án thường phân biệt **phiên bản đang phát triển** với **phiên bản phát hành ổn định**. Sự phân biệt này ảnh hưởng đến cách đặt version, cách xuất bản artifact, cách build tool tìm dependency và cách CI/CD quản lý bản phát hành.

Ví dụ một chu kỳ phát triển:

```text
Đang phát triển phiên bản tiếp theo
          |
          v
     1.5.0-SNAPSHOT
          |
          | Hoàn tất tính năng, kiểm thử và xác nhận phát hành
          v
       1.5.0
          |
          | Bắt đầu chu kỳ tiếp theo
          v
     1.6.0-SNAPSHOT
```

`1.5.0-SNAPSHOT` biểu thị một bản phát triển đang thay đổi. `1.5.0` biểu thị phiên bản phát hành ổn định. Khi đã phát hành `1.5.0`, artifact mang định danh đó cần giữ nguyên nội dung để người dùng có thể tái lập build và tin cậy dependency.

## 1. Version dùng để định danh điều gì?

Build tool cần biết artifact nào đang được tạo và artifact đó thuộc phiên bản nào. Với thư viện Java, định danh thường gồm ba thành phần:

- **Group:** tổ chức hoặc nhóm sở hữu, ví dụ `com.example`.
- **Artifact:** tên thư viện hoặc module, ví dụ `payment-core`.
- **Version:** phiên bản cụ thể, ví dụ `1.5.0`.

Trong Maven, ba thành phần này thường được gọi là `groupId`, `artifactId` và `version`. Trong Gradle, chúng tương ứng với `group`, tên project/module và `version` khi xuất bản.

Một dependency có thể được biểu diễn như sau:

```text
com.example:payment-core:1.5.0
|           |             |
|           |             +-- Version
|           +---------------- Artifact
+---------------------------- Group
```

Build tool sử dụng định danh này để tìm artifact trong repository, phân biệt các phiên bản và đưa đúng JAR vào compile/runtime classpath. Khi version thay đổi, dependency được xem là một định danh khác và build tool có thể phải giải quyết artifact tương ứng.

Version của ứng dụng hoặc thư viện cũng khác với phiên bản của công cụ build. Các giá trị sau có mục đích riêng:

| Loại phiên bản | Ví dụ | Ý nghĩa |
|---|---|---|
| Phiên bản ứng dụng/thư viện | `1.5.0` | Định danh sản phẩm đang build hoặc phát hành. |
| Phiên bản Gradle Wrapper | `8.5` trong `gradle-wrapper.properties` | Chọn phiên bản Gradle dùng để chạy build. |
| Phiên bản JDK/toolchain | `21` | Chọn bộ công cụ Java dùng để biên dịch hoặc chạy. |
| Phiên bản plugin | `org.springframework.boot` `3.3.x` | Chọn phiên bản plugin mở rộng quy trình build. |

Nâng Gradle Wrapper hoặc JDK không tự động có nghĩa ứng dụng đã tăng version phát hành. Hãy quản lý từng loại theo mục đích của nó.

## 2. Phiên bản phát hành ổn định

Phiên bản phát hành ổn định là phiên bản đã được nhóm chấp nhận để người dùng hoặc hệ thống khác phụ thuộc vào. Ví dụ:

```text
1.0.0
1.2.3
2.0.0
```

Một bản stable thường có các đặc điểm:

- Đã qua những bước kiểm tra và phê duyệt phát hành của dự án.
- Có định danh version rõ ràng và được công bố trong repository phát hành.
- Artifact được xem là bất biến sau khi phát hành.
- Có thể được dùng làm dependency lâu dài trong các dự án khác.
- Có thể được truy vết về source commit, quy trình build và các dependency đã sử dụng.

Điểm quan trọng nhất là tính ổn định của định danh. Nếu `com.example:payment-core:1.5.0` đã được phát hành, không nên tải lên một JAR khác với nội dung thay đổi nhưng vẫn dùng đúng tọa độ đó. Một nhóm build hôm nay và một nhóm build tháng sau phải nhận được cùng artifact khi yêu cầu cùng phiên bản release.

Nếu phát hiện lỗi trong phiên bản đã phát hành, hãy sửa mã nguồn rồi tạo version mới theo chính sách versioning của dự án, ví dụ `1.5.1`. Việc ghi đè artifact release cũ làm mất khả năng tái lập và có thể khiến cache của người dùng giữ nội dung khác với repository.

## 3. Phiên bản đang phát triển

Phiên bản đang phát triển đại diện cho mã nguồn chưa được chốt thành một bản phát hành ổn định. Nhóm có thể build và chia sẻ nhiều lần trong cùng chu kỳ phát triển.

Ví dụ:

```text
1.5.0-SNAPSHOT
1.5.0-alpha.1
1.5.0-beta.2
1.5.0-rc.1
```

Các dạng version trên không hoàn toàn đồng nghĩa:

- `1.5.0-SNAPSHOT` thường được dùng theo quy ước Maven cho bản snapshot đang phát triển.
- `1.5.0-alpha.1` thường biểu thị bản thử nghiệm sớm.
- `1.5.0-beta.2` thường biểu thị bản beta, đã có thêm tính năng nhưng vẫn đang kiểm chứng.
- `1.5.0-rc.1` thường là release candidate, ứng viên phát hành cần được xác nhận.

Những hậu tố `alpha`, `beta`, `rc` là quy ước phổ biến trong quản lý phiên bản. Dự án cần công bố ý nghĩa cụ thể của chúng để người dùng biết mức độ sẵn sàng. Một bản `rc` có thể được xem là gần phát hành nhưng vẫn chưa phải stable release.

Trong quá trình phát triển, cùng một nhánh version có thể được build nhiều lần. Nếu repository cho phép thay đổi artifact cùng một tọa độ snapshot, người dùng có thể nhận nội dung mới sau khi build tool làm mới metadata hoặc hết thời gian cache. Điều này thuận tiện cho tích hợp liên tục nhưng khiến snapshot không phù hợp làm dependency ổn định dài hạn.

## 4. Quy ước Semantic Versioning

Một quy ước phổ biến để đặt version là Semantic Versioning (SemVer). Dạng cơ bản:

```text
MAJOR.MINOR.PATCH
```

Ví dụ `2.4.1` gồm:

- `MAJOR = 2`: tăng khi có thay đổi không tương thích với API hoặc hợp đồng công khai theo chính sách của dự án.
- `MINOR = 4`: tăng khi bổ sung chức năng tương thích ngược.
- `PATCH = 1`: tăng khi sửa lỗi tương thích ngược.

Ví dụ minh họa một thư viện có API công khai:

| Thay đổi | Version trước | Version sau |
|---|---:|---:|
| Sửa lỗi không làm thay đổi API công khai | `2.4.1` | `2.4.2` |
| Thêm method mới mà vẫn tương thích | `2.4.2` | `2.5.0` |
| Xóa hoặc đổi chữ ký method công khai gây không tương thích | `2.5.0` | `3.0.0` |

SemVer còn hỗ trợ nhãn prerelease:

```text
2.5.0-alpha.1
2.5.0-beta.1
2.5.0-rc.1
2.5.0
```

Theo quy tắc precedence của SemVer, bản phát hành không có nhãn prerelease có độ ưu tiên cao hơn các bản prerelease cùng `MAJOR.MINOR.PATCH`. Trong chuỗi prerelease, các định danh được so sánh theo quy tắc SemVer; ví dụ `alpha` đứng trước `beta`, rồi đến `rc` nếu các nhóm dự án dùng thứ tự đó.

SemVer mô tả ý nghĩa của version dựa trên API công khai. Nó không tự kiểm tra thay đổi mã nguồn và không tự quyết định version cho bạn. Nhóm phát triển phải đánh giá thay đổi và chọn số version phù hợp.

### Trước phiên bản 1.0.0

Trong SemVer, các version `0.y.z` biểu thị giai đoạn phát triển ban đầu; API có thể thay đổi. Dự án nên mô tả rõ mức độ ổn định của API trước khi phát hành `1.0.0`.

### Không phải mọi công cụ đều so sánh version giống hệt SemVer

Maven và Gradle có cơ chế phân tích, so sánh và chọn version riêng cho dependency. Không nên dựa vào các chuỗi version tùy biến phức tạp hoặc giả định mọi công cụ đều áp dụng toàn bộ quy tắc SemVer giống nhau. Nếu cần hành vi dễ dự đoán, hãy dùng dạng version phổ biến, version cụ thể và chính sách rõ ràng của repository.

## 5. Maven: phiên bản `SNAPSHOT` và phiên bản release

Maven có quy ước nổi bật để phân biệt bản phát triển và bản release: hậu tố `-SNAPSHOT`.

Ví dụ trong `pom.xml`:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>payment-core</artifactId>
    <version>1.5.0-SNAPSHOT</version>
</project>
```

Version `1.5.0-SNAPSHOT` cho biết artifact đang được phát triển. Sau khi chốt phát hành, version được đổi thành:

```xml
<version>1.5.0</version>
```

### Snapshot repository và release repository

Repository Maven có thể được cấu hình để quản lý riêng snapshot và release. Snapshot repository chấp nhận các phiên bản phát triển có thể được cập nhật. Release repository thường chỉ chấp nhận version phát hành và không cho ghi đè artifact đã tồn tại.

Một cấu hình `distributionManagement` minh họa:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.com/maven-releases</url>
    </repository>

    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.com/maven-snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

Các URL trên chỉ là địa chỉ minh họa; thay bằng repository của tổ chức. Thông tin đăng nhập thường được khai báo trong `settings.xml` với `server/id` khớp `company-releases` hoặc `company-snapshots`, không đưa mật khẩu vào `pom.xml` được commit.

Khi chạy `mvn deploy`, Maven Deploy Plugin xuất bản artifact vào repository đã cấu hình. Với version có hậu tố `-SNAPSHOT`, Maven sử dụng `snapshotRepository`; với version release, Maven sử dụng `repository`.

### Snapshot timestamped

Trong repository Maven từ xa, snapshot thường được lưu bằng tên artifact có timestamp và build number. Ví dụ một version logic `1.5.0-SNAPSHOT` có thể được lưu thành một bản cụ thể như:

```text
payment-core-1.5.0-20261113.061500-4.jar
```

Repository duy trì metadata để ánh xạ version `1.5.0-SNAPSHOT` đến snapshot cụ thể mới nhất theo quy tắc của repository. Người dùng khai báo dependency bằng version logic `1.5.0-SNAPSHOT`; Maven tra metadata để tìm bản snapshot tương ứng.

Timestamp giúp repository lưu nhiều lần deploy snapshot mà không phải ghi đè trực tiếp cùng một tệp vật lý. Tuy vậy, từ góc nhìn người dùng, tọa độ `1.5.0-SNAPSHOT` vẫn là một dependency có thể thay đổi theo thời gian.

### Local install và remote deploy

Hai lệnh sau có mục đích khác nhau:

```shell
mvn install
mvn deploy
```

- `mvn install` chạy lifecycle đến `install` và đưa artifact vào local Maven repository của máy, thường là `~/.m2/repository`.
- `mvn deploy` chạy đến phase `deploy` và xuất bản artifact lên remote repository đã cấu hình.

Việc cài vào local repository chỉ giúp các dự án trên máy đó tham chiếu artifact. Nó không có nghĩa thư viện đã được chia sẻ với đồng đội hoặc CI.

## 6. Gradle: khai báo version của project

Gradle cho phép đặt `group` và `version` trong build script:

```groovy
group = 'com.example'
version = '1.5.0-SNAPSHOT'
```

Các giá trị này là metadata của project và được dùng bởi những plugin/task xuất bản hoặc đóng gói. Ví dụ, JAR được tạo bởi Java plugin thường có tên chứa project name và version:

```text
build/libs/payment-core-1.5.0-SNAPSHOT.jar
```

Tên chính xác còn phụ thuộc `archivesName`, `archiveVersion`, cấu hình archive và plugin.

### Đưa version vào thuộc tính build

Để dễ thay đổi version trong CI, có thể đọc một Gradle project property:

```groovy
group = 'com.example'
version = providers.gradleProperty('releaseVersion')
    .orElse('1.5.0-SNAPSHOT')
    .get()
```

Trong `gradle.properties`:

```properties
releaseVersion=1.5.0-SNAPSHOT
```

Hoặc truyền giá trị khi chạy:

```shell
./gradlew build -PreleaseVersion=1.5.0
```

Trên Windows:

```powershell
.\gradlew.bat build -PreleaseVersion=1.5.0
```

Nếu dùng thuộc tính theo môi trường hoặc CI, hãy xác định rõ nguồn version được ưu tiên. Tránh để cùng lúc nhiều file và biến môi trường có thể đặt các version khác nhau mà không có quy tắc rõ ràng.

### Xem version hiện tại

Gradle có thể hiển thị các thuộc tính của project:

```shell
./gradlew properties
```

Tìm các dòng `group`, `name` và `version` trong kết quả. Với build nhiều module, có thể xem riêng một project bằng cách gọi task tương ứng theo đường dẫn project, hoặc thêm task in metadata nếu dự án cần báo cáo version cho tất cả module.

## 7. Gradle và dependency thay đổi (changing modules)

Gradle quản lý cache dependency để tránh tải lại metadata và artifact ở mọi lần build. Tuy nhiên, một dependency có thể thay đổi nội dung dù tọa độ version không đổi. Đây là trường hợp của module được xem là *changing*; Maven SNAPSHOT được Gradle nhận diện như một dạng dependency thay đổi khi phân giải từ Maven repository.

Ví dụ dependency:

```groovy
dependencies {
    implementation 'com.example:payment-core:1.5.0-SNAPSHOT'
}
```

Nếu nhóm vừa deploy một snapshot mới lên repository, Gradle có thể vẫn dùng metadata hoặc artifact đã cache trong khoảng thời gian cache policy cho phép. Vì vậy, người phát triển đôi khi cần làm mới dependency để nhận snapshot mới.

Chạy:

```shell
./gradlew build --refresh-dependencies
```

`--refresh-dependencies` yêu cầu Gradle làm mới quá trình phân giải dependency. Nó không có nghĩa mọi tệp đều luôn được tải lại nguyên trạng; Gradle vẫn có thể kiểm tra metadata và nội dung để quyết định cần tải gì.

### Thay đổi thời gian cache cho changing modules

Có thể cấu hình thời gian cache cho dependency thay đổi:

```groovy
configurations.configureEach {
    resolutionStrategy.cacheChangingModulesFor 0, 'seconds'
}
```

Ví dụ trên yêu cầu Gradle không giữ kết quả changing module trong khoảng thời gian cache thông thường. Điều này có thể hữu ích khi phát triển với snapshot cập nhật liên tục, nhưng làm tăng số lần kiểm tra repository và có thể làm build chậm hơn hoặc phụ thuộc mạng nhiều hơn.

Không nên tùy tiện tắt cache cho mọi dependency trong build dùng chung. Hãy chọn chính sách phù hợp với môi trường phát triển, CI và khả năng sẵn sàng của repository.

## 8. Xuất bản artifact bằng Gradle

Gradle không tự áp đặt quy trình release/snapshot cho mọi dự án. Plugin xuất bản và cấu hình repository quyết định artifact được gửi đi đâu. Với Maven Publish Plugin, một dự án Java có thể khai báo publication như sau:

```groovy
plugins {
    id 'java'
    id 'maven-publish'
}

group = 'com.example'
version = '1.5.0-SNAPSHOT'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'internal'
            url = uri(
                version.toString().endsWith('SNAPSHOT')
                    ? 'https://repo.example.com/maven-snapshots'
                    : 'https://repo.example.com/maven-releases'
            )
        }
    }
}
```

Các URL là ví dụ và cần được thay bằng repository thực tế. Cấu hình trên chọn đích xuất bản dựa trên hậu tố version. Repository đích cũng cần có chính sách cho phép snapshot hoặc release tương ứng.

Gradle tạo các task xuất bản theo publication và repository đã khai báo. Có thể xem các task bằng:

```shell
./gradlew tasks --all
```

Với publication tên `mavenJava` và repository tên `internal`, các task thường có tên tương tự:

```shell
./gradlew publishMavenJavaPublicationToInternalRepository
```

Để xuất bản vào local Maven repository:

```shell
./gradlew publishToMavenLocal
```

Task cụ thể phụ thuộc tên publication, repository và plugin đã cấu hình. Hãy kiểm tra task list của chính dự án trước khi gọi.

Thông tin xác thực repository nên được truyền qua Gradle properties, biến môi trường hoặc secret của CI. Không ghi token hoặc mật khẩu trực tiếp vào build script hay file được commit.

## 9. Quy trình chuyển từ development sang stable release

Một quy trình release thường có các bước sau:

```text
Mã nguồn đang phát triển
          |
          v
Version development
          |
          v
Build + unit test + integration test
          |
          v
Kiểm tra artifact và metadata
          |
          v
Chốt version release
          |
          v
Build từ source commit đã xác định
          |
          v
Publish vào release repository
          |
          v
Tạo tag và ghi release notes
          |
          v
Tăng version cho chu kỳ tiếp theo
```

Các bước cụ thể tùy quy trình của tổ chức, nhưng nên bảo đảm:

1. **Chọn version trước khi build release:** version trong source, manifest, POM và artifact cần nhất quán.
2. **Xác định source commit:** có thể truy ngược artifact về commit đã tạo ra nó.
3. **Chạy các kiểm tra bắt buộc:** test, kiểm tra tương thích, kiểm tra bảo mật hoặc các bước phê duyệt của dự án.
4. **Kiểm tra artifact:** xác nhận tên, version, manifest, dependency metadata và nội dung gói.
5. **Publish một lần vào release repository:** repository nên từ chối ghi đè version release đã tồn tại.
6. **Gắn tag và ghi chú phát hành:** giúp nhóm và người dùng tìm lại source, thay đổi và artifact.
7. **Chuyển sang version phát triển tiếp theo:** ví dụ sau `1.5.0` thì bắt đầu `1.6.0-SNAPSHOT` theo kế hoạch.

Với Maven, một quy trình release có thể đổi `1.5.0-SNAPSHOT` thành `1.5.0`, deploy bản release, sau đó cập nhật POM lên `1.6.0-SNAPSHOT`. Có thể dùng Maven Release Plugin hoặc quy trình CI riêng để tự động hóa, nhưng cần hiểu các thay đổi mà plugin thực hiện với SCM và POM.

Với Gradle, nhóm có thể truyền `releaseVersion` từ pipeline, tạo artifact từ commit/tag đã xác định và publish đến release repository. Sau khi phát hành, cập nhật version phát triển tiếp theo trong source hoặc cấu hình version của pipeline.

## 10. Vì sao không nên ghi đè một version release?

Giả sử hai lần build tạo ra:

```text
com.example:payment-core:1.5.0
```

Lần thứ nhất chứa nội dung A. Sau đó một người tải lên nội dung B với cùng group, artifact và version. Từ thời điểm đó, cùng một dependency declaration có thể cho kết quả khác nhau tùy repository, cache hoặc thời điểm build.

Hệ quả có thể gồm:

- Build không còn tái lập được từ cùng source declaration.
- Máy của lập trình viên và CI có thể giữ hai nội dung khác nhau trong cache.
- SBOM, kiểm tra lỗ hổng và báo cáo phát hành không còn trỏ đến một artifact duy nhất.
- Người dùng không thể xác định chắc chắn JAR nào đã được kiểm thử hoặc triển khai.
- Việc rollback trở nên khó khăn vì version cũ không còn đại diện cho cùng nội dung.

Vì vậy, release repository thường áp dụng chính sách immutability: một tọa độ release đã tồn tại thì không được ghi đè. Nếu cần phát hành lại sau khi sửa lỗi, hãy tăng version, ví dụ `1.5.1`, và ghi rõ thay đổi.

Snapshot repository có thể cho phép cập nhật cùng version logic vì mục đích của snapshot là phục vụ quá trình phát triển. Dù vậy, CI vẫn nên lưu lại timestamp, build number, commit SHA hoặc checksum để biết chính xác bản snapshot nào đã được kiểm thử.

## 11. Ảnh hưởng đến dependency và tính tái lập của build

Khi một dự án phụ thuộc vào thư viện khác, version khai báo quyết định artifact mà build tool cần phân giải.

### Dùng version cụ thể cho dependency ổn định

Ví dụ Gradle:

```groovy
dependencies {
    implementation 'com.example:payment-core:1.5.0'
}
```

Ví dụ Maven:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>payment-core</artifactId>
    <version>1.5.0</version>
</dependency>
```

Khai báo version cụ thể giúp dependency có định danh rõ ràng. Để build có thể tái lập tốt hơn, còn cần quản lý repository, metadata, dependency bắc cầu, plugin, JDK và các đầu vào khác.

### Tránh version động trong build cần tái lập

Ví dụ Gradle:

```groovy
dependencies {
    implementation 'com.example:payment-core:1.+'
}
```

`1.+` là version động: Gradle có thể chọn một phiên bản phù hợp mới hơn theo metadata repository và cache policy. Một build chạy hôm nay và ngày mai có thể chọn version khác dù mã nguồn của dự án không đổi.

Các dạng như `latest.release`, version range của Maven hoặc wildcard tương tự cũng có thể làm kết quả phân giải thay đổi theo thời gian. Chúng có thể hữu ích trong một số quy trình cập nhật dependency có kiểm soát, nhưng không phù hợp nếu muốn mọi lần build tự động chọn chính xác cùng một dependency.

### Dependency locking

Gradle hỗ trợ dependency locking để ghi lại version đã được phân giải cho các configuration được bật khóa. Ví dụ:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi cấu hình locking, dự án có thể ghi lock state bằng các task/cách chạy phù hợp với phiên bản Gradle đang dùng. Lock file giúp giữ version đã chọn ổn định giữa các lần build. Nó không biến một snapshot thành artifact bất biến; nếu cùng version snapshot thay đổi nội dung, việc quản lý cache và repository vẫn rất quan trọng.

Maven cũng có các cơ chế quản lý dependency qua version cụ thể, dependency management và plugin hỗ trợ lock/flatten theo nhu cầu dự án. Cốt lõi là phải có chính sách rõ ràng về version được phép thay đổi và cách cập nhật chúng.

## 12. Phân biệt các dạng version thường gặp

| Dạng version | Ví dụ | Mục đích thường gặp | Tính chất |
|---|---|---|---|
| Stable release | `1.5.0` | Phát hành chính thức | Artifact cần bất biến. |
| Patch release | `1.5.1` | Sửa lỗi tương thích ngược | Một release mới với định danh mới. |
| Minor release | `1.6.0` | Bổ sung chức năng tương thích ngược | Một release mới với định danh mới. |
| Major release | `2.0.0` | Thay đổi không tương thích | Có thể cần migration. |
| Maven snapshot | `1.6.0-SNAPSHOT` | Bản phát triển liên tục | Có thể được cập nhật. |
| Alpha | `1.6.0-alpha.1` | Thử nghiệm sớm | Prerelease, chưa ổn định. |
| Beta | `1.6.0-beta.1` | Kiểm thử rộng hơn | Prerelease, còn có thể thay đổi. |
| Release candidate | `1.6.0-rc.1` | Ứng viên phát hành | Chờ xác nhận trước stable release. |

Không nên dùng các nhãn trên tùy tiện. Hãy thống nhất chính sách trong dự án: version nào được đưa vào snapshot repository, version nào được phép xuất bản release, ai phê duyệt và khi nào một candidate được chuyển thành stable.

## 13. Những lỗi và nhầm lẫn thường gặp

| Biểu hiện hoặc nhầm lẫn | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đã deploy snapshot mới nhưng Gradle vẫn dùng nội dung cũ | Metadata hoặc artifact còn trong cache theo chính sách changing module. | Dùng `--refresh-dependencies`, kiểm tra repository metadata và cache policy. |
| `mvn deploy` không tìm thấy repository | Chưa cấu hình `distributionManagement` hoặc cấu hình profile không được kích hoạt. | Kiểm tra `pom.xml`, active profile và repository id. |
| Maven deploy báo lỗi xác thực | `server/id` trong `settings.xml` không khớp repository id hoặc credentials sai. | Kiểm tra cấu hình đăng nhập ngoài POM và quyền của tài khoản. |
| Gradle publish không có task mong muốn | Chưa áp dụng `maven-publish`, publication hoặc repository chưa được khai báo. | Kiểm tra plugin và danh sách task bằng `tasks --all`. |
| Release repository từ chối publish | Version đã tồn tại hoặc repository không cho ghi đè. | Tăng version và tạo release mới theo chính sách. |
| Hai máy build cùng version nhưng có JAR khác nhau | Version release bị ghi đè, snapshot thay đổi hoặc đầu vào build khác nhau. | Kiểm tra checksum, commit, cache và chính sách immutability. |
| Version trong tên JAR khác version mong đợi | Project version, archive version hoặc cấu hình plugin bị đặt ở nhiều nơi. | Kiểm tra `group`, `version`, archive task và metadata publication. |
| Tăng Gradle version nhưng artifact version không đổi | Nhầm phiên bản build tool với version ứng dụng. | Quản lý wrapper/toolchain và project version độc lập. |
| Dùng `1.+` khiến build chọn bản mới bất ngờ | Version động được phân giải theo metadata và cache. | Dùng version cụ thể hoặc dependency locking. |

## 14. Quy trình kiểm tra version trước khi publish

Trước khi xuất bản một artifact, hãy xác nhận các điểm sau trong quy trình phát triển của dự án:

1. `group`, `artifact` và `version` đúng với module cần phát hành.
2. Version đang là snapshot/prerelease hay stable theo đúng trạng thái của source.
3. Version trong POM, metadata publication, tên archive và thông tin manifest nhất quán.
4. Release version chưa được sử dụng trong repository đích.
5. Build được tạo từ commit đã xác định và các kiểm tra bắt buộc đã hoàn tất.
6. Dependency version được phân giải theo chính sách đã thống nhất.
7. Artifact có thể được tải lại và checksum được lưu nếu quy trình yêu cầu.
8. Credentials được cung cấp từ môi trường/secret và không nằm trong repository.
9. Release notes, tag và thông tin truy vết được cập nhật.
10. Version phát triển tiếp theo được chuẩn bị sau khi release hoàn tất.

Đây là quy trình vận hành cần được tự động hóa phù hợp với dự án. Bản thân việc đổi chuỗi `1.5.0-SNAPSHOT` thành `1.5.0` chưa đủ để bảo đảm artifact đã được kiểm thử, publish đúng repository và không bị ghi đè.

## 15. Bài thực hành

Thực hành trên một thư viện Java nhỏ có thể đóng gói thành JAR:

1. Đặt `group` và `version` của dự án, ví dụ `com.example` và `1.5.0-SNAPSHOT`.
2. Chạy build và quan sát version xuất hiện trong tên JAR hoặc metadata của artifact.
3. Tạo một dependency có version `1.5.0-SNAPSHOT` trong một dự án thử nghiệm và xác định repository mà build tool dùng để phân giải nó.
4. Với Maven, cấu hình riêng snapshot repository và release repository bằng các địa chỉ thử nghiệm hoặc repository local phù hợp.
5. Chạy `mvn install` và xác định artifact được đưa vào local repository. Phân biệt kết quả đó với `mvn deploy` lên remote repository.
6. Với Gradle, áp dụng Maven Publish Plugin, khai báo một publication từ Java component và xem các task publish được tạo.
7. Thử thay version thành `1.5.0`, build artifact và kiểm tra định danh release.
8. Thử dùng `1.5.0-rc.1`, `1.5.0` và giải thích ý nghĩa prerelease theo quy ước versioning mà dự án chọn.
9. Thay đổi nội dung rồi build lại cùng version snapshot. Quan sát ảnh hưởng của cache và thử `--refresh-dependencies` ở dự án tiêu thụ.
10. Viết quy trình release cho thư viện: chốt commit, chọn version, chạy test, publish, tag source và tăng version development tiếp theo.

Sau bài thực hành, bạn cần phân biệt được version stable với version development, hiểu ý nghĩa của `-SNAPSHOT`, biết SemVer hỗ trợ giao tiếp về mức độ thay đổi API ra sao, phân biệt local install với remote deploy, và giải thích vì sao release artifact phải bất biến. Đây là nền tảng để quản lý dependency và phát hành thư viện Java có thể truy vết, kiểm soát và tái lập.
