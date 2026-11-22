# Gradle Repository Publishing: xuất bản Java artifact lên repository

## 1. Repository publishing là gì?

Repository publishing là bước đưa artifact đã build vào một kho lưu trữ để project khác, CI pipeline hoặc người dùng có thể khai báo dependency và tải về theo tọa độ ổn định.

Với thư viện Java, artifact thường là JAR chứa class và resource. Khi publish, build còn tạo metadata mô tả group, artifact, version, dependency, license, developer và các biến thể sử dụng. Repository có thể là Maven repository, Ivy repository hoặc Maven Local trên máy phát triển.

Cần phân biệt ba hoạt động:

- **Build:** biên dịch source, chạy task kiểm tra và tạo artifact trong thư mục build.
- **Publish:** tải artifact cùng metadata lên repository đã cấu hình.
- **Resolve dependency:** project tiêu thụ đọc metadata từ repository, chọn variant phù hợp và tải artifact về cache.

Một file JAR nằm trong build/libs chưa tự trở thành dependency dùng được từ repository. Nó cần được publish cùng tọa độ và metadata phù hợp.

## 2. Maven coordinates và repository layout

Maven nhận diện artifact bằng ba thành phần chính:

```text
groupId:artifactId:version
```

Ví dụ:

```text
com.example:greeter:1.2.0
```

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| groupId | Nhóm hoặc namespace của thư viện | com.example |
| artifactId | Tên module được phát hành | greeter |
| version | Phiên bản artifact | 1.2.0 |

Gradle ánh xạ các giá trị thường dùng:

- project.group → groupId.
- MavenPublication.artifactId → artifactId.
- project.version → version.

Nếu không gán artifactId riêng, Gradle thường dùng tên project. Nên đặt group và version rõ ràng trong build script để tránh phát hành nhầm tọa độ.

Maven repository dùng groupId để tạo đường dẫn thư mục. Dấu chấm trong groupId trở thành dấu gạch chéo:

```text
com.example:greeter:1.2.0
→ com/example/greeter/1.2.0/
    greeter-1.2.0.jar
    greeter-1.2.0.pom
    greeter-1.2.0.module
    greeter-1.2.0-sources.jar
    greeter-1.2.0-javadoc.jar
```

POM mô tả dependency theo mô hình Maven. File .module là Gradle Module Metadata, có thể mô tả variant và thuộc tính phong phú hơn. Không phải repository nào cũng bật hoặc phục vụ mọi loại metadata theo cùng chính sách; cần kiểm tra repository thực tế.

## 3. Các plugin và publication model của Gradle

Gradle có hai plugin publishing tích hợp thường gặp:

| Plugin | Publication | Repository |
|---|---|---|
| maven-publish | MavenPublication | Maven repository |
| ivy-publish | IvyPublication | Ivy repository |

Để phát hành thư viện Java lên Maven repository:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
```

Java Plugin hoặc Java Library Plugin cung cấp component Java. Maven Publish Plugin tạo publication và các task publish tương ứng.

Publication là mô tả artifact sẽ được phát hành. Repository là đích nhận artifact. Có thể khai báo nhiều publication hoặc nhiều repository, nhưng phải quản lý cẩn thận để không phát hành nhầm version hoặc nhầm môi trường.

## 4. Xuất bản Java component bằng from components.java

Cách thông dụng nhất để publish thư viện Java là lấy component do Java Plugin cung cấp:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

`from components.java` đưa output và metadata của component Java vào publication. Gradle biết artifact chính, dependency và các variant do plugin Java tạo ra.

Ưu tiên publish component thay vì tự tạo một publication chỉ có file JAR. Nếu chỉ thêm JAR thủ công, metadata dependency có thể thiếu hoặc không phản ánh đúng cách consumer cần compile và chạy thư viện.

Với Java Library Plugin, component có thể biểu diễn API dependency và implementation dependency riêng. Điều này đặc biệt hữu ích khi thư viện được dùng bởi nhiều project khác.

## 5. Java Plugin và Java Library Plugin ảnh hưởng đến metadata

`java` và `java-library` đều hỗ trợ biên dịch, đóng gói và publish Java component. Java Library Plugin bổ sung quy ước API rõ hơn:

- `api`: dependency là một phần API mà consumer cần thấy khi compile.
- `implementation`: dependency dùng nội bộ; không cần đưa vào compile classpath của consumer, nhưng có thể cần ở runtime.

Ví dụ:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-api:2.0'
    implementation 'org.example:internal-helper:1.4'
}
```

Khi publish Maven POM, Gradle ánh xạ dependency sang scope phù hợp. Với Gradle Module Metadata, dependency được gắn vào variant tương ứng như apiElements và runtimeElements.

Chọn `api` khi kiểu public của thư viện phụ thuộc vào kiểu từ dependency đó, hoặc consumer phải có dependency để compile code gọi API. Dùng `implementation` cho chi tiết triển khai để giữ API gọn và tránh làm lộ dependency không cần thiết.

Không khai báo mọi dependency là api chỉ để khắc phục lỗi compile ở consumer; trước tiên hãy kiểm tra public API và dependency thực sự cần được công khai.

## 6. Maven POM và Gradle Module Metadata

Một publication Maven thường tạo ít nhất:

- JAR chính.
- POM XML.
- Gradle Module Metadata với đuôi .module nếu được bật.
- Sources/Javadoc JAR nếu publication có các artifact này.
- Checksum sidecar do repository hoặc Gradle tạo.

POM XML chứa groupId, artifactId, version, name, description, URL, license, developer, SCM và dependency scopes.

Gradle Module Metadata có thể mô tả:

- Variant API và runtime.
- Java target compatibility.
- Usage và library elements.
- Dependency constraints.
- Sources và Javadoc variants.
- Artifact file cùng checksum.

Các variant Java thường gặp là apiElements, runtimeElements, sourcesElements và javadocElements.

Khi Gradle đọc repository có Gradle Module Metadata được publish đúng cách, Gradle thường ưu tiên metadata này để chọn variant. Maven client đọc POM theo mô hình Maven. Vì vậy cần kiểm tra cả hai khi thư viện phục vụ cả Maven và Gradle consumer.

Không xóa file .module hoặc marker metadata trong POM một cách tùy tiện. Làm vậy có thể khiến Gradle consumer mất thông tin variant mà publisher đã cung cấp.

## 7. Bổ sung metadata cho POM

Metadata giúp người dùng nhận diện thư viện và repository có đủ thông tin để quản lý artifact.

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = 'Greeter Library'
                description = 'A reusable greeting library.'
                url = 'https://example.org/greeter'

                licenses {
                    license {
                        name = 'Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                        distribution = 'repo'
                    }
                }

                developers {
                    developer {
                        id = 'example-maintainers'
                        name = 'Example Maintainers'
                    }
                }

                scm {
                    connection = 'scm:git:https://example.org/greeter.git'
                    url = 'https://example.org/greeter'
                }
            }
        }
    }
}
```

Thay các giá trị ví dụ bằng thông tin thật của thư viện trước khi phát hành. License phải khớp license thực tế của source và binary. Không khai báo license, developer, SCM hoặc URL sai chỉ để POM trông đầy đủ.

Dùng DSL pom có kiểu dữ liệu cho các trường chuẩn. Chỉ can thiệp XML trực tiếp qua withXml khi cần trường mở rộng mà DSL không hỗ trợ và đã hiểu ảnh hưởng lên consumer.

## 8. Sources JAR và Javadoc JAR

Thư viện công khai thường nên phát hành source và API documentation để IDE và người dùng có thể tra cứu.

Bật hai artifact bằng Java extension:

```groovy
java {
    withSourcesJar()
    withJavadocJar()
}
```

Khi publication lấy từ components.java, Gradle tự gắn sources JAR và Javadoc JAR vào publication. Không cần tự tạo publication riêng cho từng file.

Ví dụ artifact:

```text
greeter-1.2.0.jar
greeter-1.2.0-sources.jar
greeter-1.2.0-javadoc.jar
```

Sources JAR thường chứa source trong source set main. Javadoc JAR chứa tài liệu API được sinh từ Javadoc comments và class public.

Trước khi publish, kiểm tra Javadoc task chạy được. Bổ sung @param, @return và @throws cho API public để tài liệu hữu ích và tránh cảnh báo. Nếu dự án có nhiều source set hoặc variant, kiểm tra rõ artifact nào được đưa vào publication.

## 9. Thêm artifact tùy chỉnh

Publication có thể chứa artifact bổ sung như schema, API specification, distribution archive hoặc tài liệu đặc biệt.

Ví dụ dạng cấu hình:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            artifact(tasks.apiDocsZip) {
                classifier = 'api-docs'
                extension = 'zip'
            }
        }
    }
}
```

Task apiDocsZip phải thật sự tạo file đầu ra và được nối dependency với publication. Classifier phân biệt artifact phụ với JAR chính; extension thể hiện định dạng file.

Không publish cùng một file hai lần với cùng classifier và extension. Trước khi thêm artifact, kiểm tra nó có thực sự cần được tải qua tọa độ Maven hay nên được phân phối bằng một kênh riêng.

## 10. Khai báo Maven repository đích

Repository được cấu hình bên trong publishing.repositories:

```groovy
publishing {
    repositories {
        maven {
            name = 'test'
            url = layout.buildDirectory.dir('test-maven-repo')
        }
    }
}
```

Đây là repository local nằm trong build directory, phù hợp để thử nghiệm. Khi publish thành công, Gradle tạo Maven layout theo groupId, artifactId và version.

Repository từ xa thường dùng HTTPS:

```groovy
publishing {
    repositories {
        maven {
            name = 'internalReleases'
            url = uri('https://repo.example.org/releases')
        }
    }
}
```

URL phải trỏ tới endpoint publish của repository manager, chẳng hạn Nexus, Artifactory hoặc dịch vụ Maven repository của tổ chức. Endpoint tải dependency có thể khác endpoint upload; hãy dùng đúng URL do quản trị repository cung cấp.

Một repository có thể là release hoặc snapshot repository. Không trỏ publication production vào thư mục build local hoặc endpoint test chỉ vì task publish chạy thành công.

## 11. Quản lý credentials và bí mật

Không ghi username, password, access token hoặc private key trực tiếp vào build.gradle, POM hay repository.

Gradle hỗ trợ PasswordCredentials:

```groovy
publishing {
    repositories {
        maven {
            name = 'internalReleases'
            url = uri('https://repo.example.org/releases')
            credentials(PasswordCredentials)
        }
    }
}
```

Với repository tên internalReleases, Gradle có thể lấy các project properties:

```properties
internalReleasesUsername=publisher
internalReleasesPassword=secret-value
```

Có thể đặt các giá trị này trong file gradle.properties ở Gradle User Home, không commit vào repository source. Trong CI, inject bằng secret store và ánh xạ thành project properties qua biến môi trường:

```text
ORG_GRADLE_PROJECT_internalReleasesUsername
ORG_GRADLE_PROJECT_internalReleasesPassword
```

Giới hạn quyền của tài khoản publish theo repository và loại artifact cần phát hành. Dùng token riêng cho CI, xoay vòng khi cần và tránh in credentials trong log. Bắt buộc dùng HTTPS cho repository từ xa để bảo vệ thông tin xác thực khi truyền tải.


## 12. Release và snapshot versions

Maven phân biệt release version và snapshot version.

| Loại | Ví dụ | Cách dùng |
|---|---|---|
| Release | 1.2.0 | Bản phát hành ổn định |
| Snapshot | 1.3.0-SNAPSHOT | Bản phát triển có thể được cập nhật |

Snapshot repository thường quản lý metadata để xác định bản snapshot mới nhất, có thể ánh xạ version dạng SNAPSHOT sang file snapshot timestamped. Release repository thường áp dụng chính sách version bất biến: một release đã phát hành không nên bị ghi đè bằng binary khác.

Có thể chọn endpoint theo version:

```groovy
def snapshotBuild = project.version.toString().endsWith('-SNAPSHOT')
def targetUrl = snapshotBuild
    ? 'https://repo.example.org/snapshots'
    : 'https://repo.example.org/releases'

publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri(targetUrl)
            credentials(PasswordCredentials)
        }
    }
}
```

Đặt version đúng trước khi publish. Không tái sử dụng cùng release version cho binary khác; tăng version khi nội dung phát hành thay đổi. Dọn snapshot cũ theo chính sách retention của repository manager để tránh repository phình to.

## 13. Các task publishing thường gặp

Maven Publish Plugin tạo task theo publication và repository name.

| Task | Mục đích |
|---|---|
| generatePomFileForMavenJavaPublication | Sinh POM |
| generateMetadataFileForMavenJavaPublication | Sinh Gradle Module Metadata |
| publishMavenJavaPublicationToTestRepository | Publish publication mavenJava tới repository test |
| publish | Chạy các task publish tới repository đã cấu hình |
| publishToMavenLocal | Publish các Maven publication vào local Maven cache |

Tên task cụ thể phụ thuộc tên publication và repository. Ví dụ publication mavenJava và repository internalReleases sẽ tạo task tương ứng với hai tên đó.

Chạy:

```bash
./gradlew tasks --all
./gradlew generatePomFileForMavenJavaPublication
./gradlew publishToMavenLocal
./gradlew publish
```

publishToMavenLocal ghi vào Maven local repository trên máy phát triển, thường là ~/.m2/repository. Nó không tải artifact lên repository từ xa và không thay thế một lần publish release chính thức.

Task publish không nên được coi là bước kiểm thử tự động. Hãy chạy check và xác nhận artifact trước khi chạy publish tới repository dùng chung.

## 14. Kiểm tra publication trước khi upload

Sau khi tạo publication, hãy kiểm tra nội dung trước khi phát hành:

1. Kiểm tra groupId, artifactId và version.
2. Mở POM để xác nhận metadata, license, SCM và dependency scope.
3. Kiểm tra .module để xem variant và artifact files.
4. Liệt kê nội dung JAR bằng jar --list.
5. Kiểm tra sources và Javadoc JAR.
6. Tính SHA-256 và so sánh checksum sidecar nếu repository cung cấp.
7. Kiểm tra không có artifact trùng classifier hoặc sai version.
8. Thử resolve dependency từ một project consumer riêng.

Các lệnh hữu ích:

```bash
jar --list --file build/libs/greeter-1.2.0.jar
jar --validate --file build/libs/greeter-1.2.0.jar
sha256sum build/libs/greeter-1.2.0.jar
```

Trên Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 ./build/libs/greeter-1.2.0.jar
```

Kiểm tra POM bằng XML parser và .module bằng JSON parser. Một file tồn tại chưa có nghĩa metadata hợp lệ hoặc dependency có thể được consumer resolve.

## 15. Kiểm thử consumer từ repository local

Cách kiểm tra đáng tin cậy là tạo một project riêng chỉ biết tọa độ dependency và repository đã publish.

Ví dụ:

```groovy
plugins {
    id 'application'
}

repositories {
    maven {
        url = uri('../greeter-library/build/test-maven-repo')
    }
}

dependencies {
    implementation 'com.example:greeter:1.2.0'
}

application {
    mainClass = 'consumer.Main'
}
```

Consumer source:

```java
package consumer;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet("Repository"));
    }
}
```

Chạy consumer:

```bash
./gradlew clean run
```

Stdout mong đợi:

```text
Hello, Repository!
```

Project consumer cần resolve artifact từ repository local đã publish, không lấy class trực tiếp từ source project. Như vậy mới xác nhận tọa độ, POM/Gradle metadata và JAR có thể sử dụng từ bên ngoài module producer.

Để kiểm tra đường tương thích Maven POM, cấu hình metadataSources của Gradle consumer:

```groovy
repositories {
    maven {
        url = uri('../greeter-library/build/test-maven-repo')
        metadataSources {
            mavenPom()
            artifact()
        }
    }
}
```

Cấu hình này yêu cầu consumer dùng POM và artifact. Kiểm thử cả đường Gradle Module Metadata mặc định và đường POM-only giúp phát hiện khác biệt metadata giữa các loại consumer.

## 16. Local repository, Maven Local và repository test

Có ba cách thường dùng khi phát triển:

- Repository trong build directory: dễ xóa, cô lập theo project và phù hợp để kiểm tra publication.
- Maven Local: dùng task publishToMavenLocal, artifact được lưu vào local Maven cache của người phát triển.
- Remote repository: repository dùng chung cho team hoặc pipeline.

Không nên dựa vào Maven Local để chứng minh một artifact đã được publish đúng lên repository từ xa. Local cache có thể giữ version cũ, khiến consumer resolve được artifact dù lần publish mới bị lỗi.

Khi test, ưu tiên repository riêng trong build directory và consumer project độc lập. Khi kiểm tra remote repository, dùng URL thực tế và xác nhận artifact tải về có checksum khớp với artifact đã build.

Nếu cần xóa một bản local cũ, xác định chính xác tọa độ và thư mục trước khi xóa; tránh xóa toàn bộ Maven cache vì sẽ buộc các project tải lại dependency.

## 17. Dependency metadata và version mapping

Publication phải mô tả dependency đúng với cách thư viện được resolve.

Với java-library:

- api dependency có thể cần trong compile classpath của consumer.
- implementation dependency chỉ cần nội bộ khi compile producer, nhưng có thể cần ở runtime.
- runtimeOnly dependency chỉ cần khi chạy.
- compileOnly dependency không nên tự động được coi là runtime dependency.

Gradle Module Metadata giữ các variant chi tiết. Maven POM dùng scope như compile, runtime và các scope Maven khác. Vì hai hệ thống có mô hình khác nhau, hãy kiểm tra POM sinh ra khi thư viện có dependency phức tạp.

Nếu version được resolve động hoặc cần xuất bản version thực tế theo cấu hình, xem xét versionMapping của MavenPublication. Chỉ thêm khi dự án có lý do rõ ràng và đã kiểm tra kết quả trong POM; không dùng nó như một cấu hình mặc định cho mọi thư viện.

## 18. Ivy publishing

Nếu repository của tổ chức dùng Ivy, áp dụng plugin ivy-publish và tạo IvyPublication:

```groovy
plugins {
    id 'java-library'
    id 'ivy-publish'
}

publishing {
    publications {
        ivyJava(IvyPublication) {
            from components.java
        }
    }

    repositories {
        ivy {
            name = 'internalIvy'
            url = uri('https://repo.example.org/ivy')
        }
    }
}
```

Ivy publication sinh descriptor theo mô hình Ivy và dùng repository layout do repository hỗ trợ. Consumer cần khai báo Ivy repository phù hợp để resolve.

Không trộn MavenPublication và IvyPublication chỉ vì muốn có thêm một file metadata. Chọn loại publication theo repository và consumer thực tế.

## 19. Multi-project và nhiều publication

Trong multi-project build, mỗi subproject có thể phát hành artifact riêng với tọa độ riêng. Nên đặt group và version ở nơi thống nhất nếu các module thuộc cùng một release train, sau đó chỉ định artifactId cho module khi tên project không phù hợp.

Một project có thể có nhiều publication nếu thực sự có nhiều variant hoặc định dạng cần phát hành. Hãy đảm bảo mỗi publication có tọa độ và classifier rõ ràng, không tạo hai publication ghi cùng một file ở cùng version.

Khi publish nhiều module có dependency giữa chúng, kiểm tra thứ tự release và repository metadata để consumer không tải được module mới nhưng thiếu dependency tương ứng.

## 20. CI pipeline và quy trình release

Một quy trình phát hành có thể gồm:

1. Checkout đúng commit và xác nhận working tree sạch.
2. Dùng Gradle Wrapper và JDK/toolchain đã pin.
3. Resolve dependency theo lock và verification metadata.
4. Chạy clean, test và check.
5. Tạo JAR, sources JAR và Javadoc JAR.
6. Kiểm tra POM, Gradle Module Metadata và checksum.
7. Publish vào staging hoặc repository test.
8. Dùng consumer project để resolve và chạy artifact.
9. Ký artifact nếu chính sách phát hành yêu cầu.
10. Promote hoặc publish release theo quyền CI đã cấp.
11. Lưu tọa độ, checksum, commit và build logs.

Không nên cho pull request bất kỳ publish trực tiếp vào release repository. Dùng quyền CI riêng, approval hoặc staging promotion theo chính sách của tổ chức. Snapshot có thể được publish tự động trong pipeline phát triển; release nên được gắn với tag/version và quy trình xác nhận.

Nếu publish thất bại một phần, kiểm tra trạng thái repository trước khi chạy lại. Một số repository không cho ghi đè release đã có; retry mù có thể tạo artifact không đồng nhất hoặc làm pipeline báo lỗi liên tục.

Với artifact phát hành, sử dụng môi trường CI sạch và đáng tin cậy. Nếu repository yêu cầu chữ ký, có thể dùng Signing Plugin để ký publication sau khi hoàn tất build và kiểm tra:

```groovy
plugins {
    id 'signing'
}

signing {
    sign publishing.publications.mavenJava
}
```

Private key và mật khẩu ký phải được cấp từ secret store của CI; không commit key vào repository. Caching hữu ích cho build thông thường khi được cấu hình đúng; phép thử reproducibility nên chủ động loại trừ trạng thái cũ có thể làm kết quả không rõ nguồn gốc.

## 21. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không có task publish | Chưa áp dụng maven-publish hoặc ivy-publish | Kiểm tra plugin trong build script |
| Không thấy publication | Chưa khai báo publications | Tạo MavenPublication/IvyPublication |
| Artifact thiếu dependency metadata | Publish file JAR thủ công | Dùng from components.java |
| POM sai group/version | Project coordinates chưa cấu hình đúng | Kiểm tra group, artifactId và version |
| Consumer không resolve được | Sai repository URL hoặc tọa độ | Kiểm tra layout và metadata |
| Consumer compile lỗi thiếu kiểu public | Dependency cần thiết đang là implementation | Xem lại API dependency và dùng api khi phù hợp |
| Consumer runtime thiếu class | Thiếu runtime dependency hoặc scope sai | Kiểm tra runtimeElements và POM scopes |
| Sources/Javadoc JAR không có | Chưa bật các task artifact | Dùng withSourcesJar và withJavadocJar |
| Javadoc task lỗi | Comment hoặc cấu hình Javadoc không hợp lệ | Sửa warning/error và kiểm tra toolchain |
| HTTP 401/403 | Credentials thiếu hoặc không đủ quyền | Kiểm tra secret, account và repository permission |
| HTTP 404 khi publish | URL trỏ sai endpoint | Dùng đúng deployment endpoint |
| HTTP 409 hoặc version conflict | Release version đã tồn tại hoặc immutable | Tăng version hoặc theo quy trình repository |
| Snapshot không cập nhật như mong đợi | Cache hoặc snapshot metadata cũ | Kiểm tra repository metadata và refresh dependency |
| Gradle chọn variant không mong muốn | Metadata variant attributes không tương thích | Kiểm tra .module, Java target và consumer attributes |
| Maven consumer không thấy variant Gradle | Maven chỉ đọc POM | Đảm bảo POM có dependency scope phù hợp |
| Artifact ở Maven Local khác bản remote | Local cache giữ bản cũ | Kiểm tra checksum ở repository thực tế |
| Publish thành công nhưng CI không chạy test | Publish không tự thay thế check | Chạy check trước publish trong pipeline |

## 22. Ví dụ hoàn chỉnh: publish thư viện và dùng từ consumer

Producer project có cấu trúc:

```text
greeter-library/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── greeter/
                        └── Greeter.java
```

File settings.gradle:

```groovy
rootProject.name = 'greeter'
```

File build.gradle:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.2.0'

java {
    withSourcesJar()
    withJavadocJar()
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = 'Greeter Library'
                description = 'A small reusable greeting library.'
                url = 'https://example.org/greeter'
            }
        }
    }

    repositories {
        maven {
            name = 'test'
            url = layout.buildDirectory.dir('test-maven-repo')
        }
    }
}
```

File src/main/java/com/example/greeter/Greeter.java:

```java
package com.example.greeter;

/** A small reusable greeting library. */
public final class Greeter {
    private Greeter() {
    }

    /**
     * Returns a greeting for the supplied name.
     * @param name recipient name; must not be blank
     * @return a greeting containing the recipient name
     * @throws IllegalArgumentException if the name is null or blank
     */
    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name + "!";
    }
}
```

Publish vào repository local của project:

```bash
./gradlew clean publish
```

Artifact được đặt dưới:

```text
build/test-maven-repo/com/example/greeter/1.2.0/
```

Các file quan trọng:

```text
greeter-1.2.0.jar
greeter-1.2.0.pom
greeter-1.2.0.module
greeter-1.2.0-sources.jar
greeter-1.2.0-javadoc.jar
```

Consumer khai báo:

```groovy
plugins {
    id 'application'
}

repositories {
    maven {
        url = uri('../greeter-library/build/test-maven-repo')
    }
}

dependencies {
    implementation 'com.example:greeter:1.2.0'
}

application {
    mainClass = 'consumer.Main'
}
```

File src/main/java/consumer/Main.java:

```java
package consumer;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet("Repository"));
    }
}
```

Chạy consumer:

```bash
./gradlew clean run
```

Stdout chính xác:

```text
Hello, Repository!
```

Trong kiểm thử trên Gradle 9.2.1 và OpenJDK Zulu 24.0.2, producer đã publish main JAR, sources JAR, Javadoc JAR, POM và Gradle Module Metadata vào repository cô lập. POM XML và module JSON được parse thành công; JAR qua jar --validate và checksum SHA-256 sidecar khớp. Consumer resolve dependency và in đúng Hello, Repository! khi dùng metadata mặc định, đồng thời chạy thành công khi buộc dùng POM metadata.

## 23. Tổng kết

Repository publishing biến output build thành dependency có thể được các project khác resolve theo tọa độ ổn định.

Những điểm cần nhớ:

- Dùng maven-publish cho Maven repository và ivy-publish cho Ivy repository.
- Ưu tiên from components.java để publication mang theo artifact và dependency metadata.
- Đặt group, artifactId và version rõ ràng.
- Dùng java-library để phân biệt api và implementation dependency.
- Kiểm tra cả Maven POM và Gradle Module Metadata.
- Bật withSourcesJar và withJavadocJar cho thư viện cần phân phối source/documentation.
- Dùng repository local trong build directory để test publication trước khi upload.
- Không lưu credentials trong source; inject qua Gradle properties hoặc CI secrets.
- Giữ release version bất biến; dùng snapshot version cho bản phát triển.
- Chạy check, kiểm tra checksum và thử resolve từ consumer trước khi phát hành.
- Phân biệt publishToMavenLocal với publish tới repository từ xa.

**Tài liệu tham khảo chính thức:**

- [Gradle User Manual — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle DSL — MavenPublication](https://docs.gradle.org/current/dsl/org.gradle.api.publish.maven.MavenPublication.html)
- [Gradle DSL — MavenArtifactRepository](https://docs.gradle.org/current/dsl/org.gradle.api.artifacts.repositories.MavenArtifactRepository.html)
- [Gradle User Manual — Ivy Publish Plugin](https://docs.gradle.org/current/userguide/publishing_ivy.html)
- [Gradle User Manual — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle User Manual — Publishing Java Libraries](https://docs.gradle.org/current/userguide/publishing_setup.html)
- [Gradle User Manual — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)
