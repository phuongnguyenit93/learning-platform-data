# Cấu hình group, artifactId, version và thông tin POM khi xuất bản artifact bằng Gradle

## 1. Vấn đề: một file JAR chưa đủ để người khác sử dụng thư viện

Khi viết một thư viện Java và chạy `./gradlew jar`, Gradle có thể tạo ra file `build/libs/my-library-1.2.3.jar`. Nhưng để một dự án khác khai báo thư viện bằng:

~~~groovy
dependencies {
    implementation 'org.example.academy:greeting-api:1.2.3'
}
~~~

cần **xuất bản artifact** vào một repository theo định dạng mà Maven/Gradle hiểu. Repository cần biết **module nào**, **phiên bản nào**, **artifact files nào** và **thông tin phụ thuộc** đi kèm. Với Maven-compatible repository, bộ ba định danh phổ biến là:

~~~text
groupId : artifactId : version
org.example.academy : greeting-api : 1.2.3
~~~

Bên cạnh JAR, một publication thường có **POM (Project Object Model)**: XML chứa định danh module, loại đóng gói, dependencies, mô tả, URL dự án, giấy phép, nhà phát triển và nguồn SCM. Khi dùng Gradle, plugin **`maven-publish`** cho phép tạo và xuất bản các thành phần đó.

Bài thuộc nhóm **Xuất bản artifact** của **Build Tool Gradle**, tập trung đúng vào **cấu hình `group`, `artifactId`, `version` và thông tin POM** trong dự án Java/Groovy DSL. Các ví dụ sử dụng Java 17 và Gradle Wrapper, có phần thực hành **xuất bản thử vào Maven repository dạng thư mục cục bộ**, không cần tài khoản Maven Central hoặc secrets.

Sau bài, bạn có thể:

1. Phân biệt `project.group`, `project.name`, `project.version` với `MavenPublication.groupId`, `artifactId` và `version`.
2. Dự đoán tên file JAR, tọa độ dependency và đường dẫn Maven repository sau khi thay `artifactId`.
3. Cấu hình `plugins { id 'java-library'; id 'maven-publish' }` và `from components.java`.
4. Viết POM metadata có `name`, `description`, `url`, `licenses`, `developers`, `scm`; biết khi nào cần thêm metadata khác.
5. Sinh và kiểm `pom-default.xml` trước khi publish; phân biệt `publish`, `publishToMavenLocal` và publish vào repository được đặt tên.
6. Hiểu mapping các dependencies từ `api`/`implementation`/`testImplementation` sang metadata công bố; biết tác động của `versionMapping`.
7. Quản lý version release/SNAPSHOT, tránh ghi đè release và bảo vệ credentials khi publish qua CI.
8. Debug lỗi sai tọa độ, POM thiếu dependencies, khác tên file hoặc consumer không resolve được artifact.

**Phạm vi:** Gradle Maven Publish Plugin, không phải plugin `maven` legacy và không phải tự upload JAR bằng HTTP. Dùng Gradle version hiện đại tương thích Java 17; task names/reports lấy từ Gradle Maven Publish Plugin.

## 2. Ba tọa độ Maven: groupId, artifactId, version

| Thuộc tính | Ví dụ | Vai trò | Lưu ý |
| --- | --- | --- | --- |
| `groupId` | `org.example.academy` | Namespace để phân biệt publisher/module family | Thường giống reverse domain, nhưng không phải Java package bắt buộc |
| `artifactId` | `greeting-api` | Tên module/artifact trong namespace đó | Có thể khác project name và tên Java package |
| `version` | `1.2.3` | Nhận diện release hoặc snapshot cụ thể | Cần chính sách release, tránh ghi đè version bất biến |

Một dependency coordinate:

~~~text
org.example.academy:greeting-api:1.2.3
          groupId       artifactId version
~~~

Khi xuất bản vào Maven repository, Maven layout thường có dạng:

~~~text
org/example/academy/greeting-api/1.2.3/
    greeting-api-1.2.3.pom
    greeting-api-1.2.3.jar
    greeting-api-1.2.3-sources.jar
    greeting-api-1.2.3-javadoc.jar
~~~

Các file `sources` và `javadoc` chỉ xuất hiện khi publication có cấu hình xuất bản chúng. Một Gradle publication hiện đại cũng có thể tạo **Gradle Module Metadata `.module`** và checksum files, tùy repository/metadata/settings. Layout trên là **đường dẫn Maven logical**, không phải output `build/libs` trước khi publish.

### 2.1. groupId không phải tên Java package

Có thể đặt:

~~~text
groupId: org.example.academy
artifactId: greeting-api
Java package: org.example.academy.greeting
Main source: src/main/java/org/example/academy/greeting/Greeting.java
~~~

Những tên này có liên hệ theo quy ước của nhóm, nhưng **Gradle không bắt groupId phải trùng Java package**. Tọa độ Maven giúp dependency resolution tìm artifact; `package` quyết định namespace class khi Java compile và runtime.

Nếu đổi groupId từ `org.example.academy` thành `org.example.tools`, class `org.example.academy.greeting.Greeting` có thể vẫn giữ package cũ. Tuy nhiên coordinate đổi sẽ ảnh hưởng consumers và có thể cần publication migration/relocation, không nên coi là rename vô hại.

### 2.2. artifactId không phải file name của Gradle task `jar`

Nếu `settings.gradle` có:

~~~groovy
rootProject.name = 'greeting-core'
~~~

và `build.gradle` có:

~~~groovy
group = 'org.example.academy'
version = '1.2.3'
~~~

thì JAR task theo convention thường tạo:

~~~text
build/libs/greeting-core-1.2.3.jar
~~~

Nhưng nếu `MavenPublication` cấu hình:

~~~groovy
artifactId = 'greeting-api'
~~~

artifact được **xuất bản** trong Maven repository dưới tên:

~~~text
greeting-api-1.2.3.jar
~~~

và POM có `<artifactId>greeting-api</artifactId>`. Đừng sửa `jar.archiveBaseName` chỉ vì muốn đổi artifactId công bố, trừ khi bạn thực sự cần đổi tên **build output**. Hai nơi có thể khác nhau hợp lệ.

### 2.3. version là một phần định danh, không chỉ mô tả marketing

Version `1.2.3` và `1.2.4` là hai modules versions khác nhau. Người dùng Gradle có thể yêu cầu cụ thể:

~~~groovy
dependencies {
    implementation 'org.example.academy:greeting-api:1.2.3'
}
~~~

Một release process tốt có tính chất:

- **Cùng tọa độ release không bị republish với byte khác.**
- Version tăng khi artifact được phát hành mới, theo chính sách SemVer hoặc chính sách đã công bố.
- Code tag/commit, changelog, JAR, POM và published metadata cùng chỉ đến một quyết định release.
- Phiên bản dạng `1.2.4-SNAPSHOT` dành cho build thử nghiệm; không dùng snapshot như một release bất biến.
- Không dùng `unspecified` hoặc một version ngẫu nhiên từ máy dev làm version cho public release.

## 3. Mặc định Gradle lấy identity từ đâu?

Theo tài liệu Maven Publish Plugin, các giá trị mặc định là:

| POM/publication | Nguồn mặc định |
| --- | --- |
| `groupId` | `project.group` |
| `artifactId` | `project.name` |
| `version` | `project.version` |

Bạn có thể cấu hình ở project level:

~~~groovy
group = 'org.example.academy'
version = '1.2.3'
~~~

và tên project thường đến từ `settings.gradle`:

~~~groovy
rootProject.name = 'greeting-core'
~~~

Nếu publication dùng:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

mà không ghi đè identity, publication sẽ mặc định lấy:

~~~text
org.example.academy:greeting-core:1.2.3
~~~

Nếu muốn publish thành `greeting-api` mà không đổi tên Gradle project:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            groupId = 'org.example.academy'
            artifactId = 'greeting-api'
            version = '1.2.3'
        }
    }
}
~~~

**Đoạn trên là trích đoạn riêng:** cần áp dụng `java` hoặc `java-library` cùng `maven-publish` ở project thật để có `components.java` và `publishing` extension. File `build.gradle` chạy đầy đủ sẽ có ở mục 7.

### 3.1. Project name khác publication name

Trong:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            artifactId = 'greeting-api'
            from components.java
        }
    }
}
~~~

- `mavenJava` là **tên publication trong Gradle**. Nó xuất hiện trong task names như `generatePomFileForMavenJavaPublication`.
- `greeting-api` là **artifactId công bố**. Nó xuất hiện trong POM, Maven repository path và tọa độ dependency.
- `greeting-core` có thể là **tên Gradle project**, dùng cho task path, output artifact name mặc định và nhiều model khác.

Không viết dependency `implementation 'org.example.academy:mavenJava:1.2.3'` chỉ vì tên publication là `mavenJava`.

### 3.2. Dùng giá trị project hay override trong publication?

Hai chiến lược đều hợp lệ:

**Chiến lược A — identity mặc định:** đặt `group` và `version` ở project, `rootProject.name` theo tên artifactId mong muốn; publication chỉ `from components.java`. Phù hợp project nhỏ, một module và một publication.

**Chiến lược B — override publication identity:** giữ project name phản ánh thư mục/mô hình build, đặt `artifactId` riêng cho Maven consumers. Phù hợp khi tên module nội bộ khác tên artifact được công bố, hoặc một build có nhiều publications.

Không lạm dụng override khi các giá trị thực chất giống nhau: giữ một nguồn sự thật sẽ giảm nguy cơ lệch version. Nếu override, ghi rõ lý do và có test kiểm identity của POM.

## 4. POM là gì và nó chứa thông tin nào?

POM là file XML theo mô hình Apache Maven. Nó mô tả published module, giúp Maven/Gradle consumers biết định danh, dependencies và thông tin liên quan dự án.

Một **POM tối giản minh họa**, không phải nguyên văn mọi file mà Gradle sinh:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.academy</groupId>
    <artifactId>greeting-api</artifactId>
    <version>1.2.3</version>
    <packaging>jar</packaging>
    <name>Greeting API</name>
    <description>Java 17 greetings library for the Gradle lesson.</description>
    <url>https://example.org/projects/greeting-api</url>
</project>
~~~

`example.org` là **tên miền được dành cho ví dụ kỹ thuật**, không đại diện một repository đang hoạt động hay một dự án bên ngoài đã xác minh. Khi thực sự công bố thư viện, publisher phải cung cấp website/SCM/owners/licenses thật và kiểm tra nội dung của POM.

### 4.1. Identity khác descriptive metadata

| POM element | Chức năng |
| --- | --- |
| `modelVersion` | Phiên bản mô hình POM, thường là `4.0.0` |
| `groupId`/`artifactId`/`version` | Tọa độ để Maven/Gradle tìm đúng module |
| `packaging` | Loại artifact chính như `jar` hoặc `pom` |
| `name` | Tên hiển thị dễ đọc cho con người |
| `description` | Mô tả công dụng và giới hạn của thư viện |
| `url` | Trang giới thiệu/tài liệu chính thức của dự án |
| `licenses` | Thông tin giấy phép được công bố |
| `developers` | Người/nhóm chịu trách nhiệm phát triển |
| `scm` | URL và connection của source control |
| `dependencies` | Những module khác mà consumer có thể cần |
| `dependencyManagement` | Quản lý versions của một số dependencies, theo mô hình Maven |
| `properties` | Metadata và biến sử dụng trong hệ sinh thái Maven |

`pom.name` **không phải** `artifactId`. Đổi tên hiển thị “Greeting API” thành “Greetings SDK” không đổi coordinate. Ngược lại, đổi `artifactId` làm người tiêu dùng phải thay dependency declaration, bất kể `pom.name` có giữ nguyên hay không.

### 4.2. Mô tả tốt cần có gì?

Một `description` hữu ích thường nói ngắn gọn:

- Thư viện giải quyết vấn đề gì.
- Ai là consumer mục tiêu.
- Một đặc tính quan trọng nếu có (ví dụ hỗ trợ Java 17).
- Không chứa marketing claim không có bằng chứng.

Ví dụ `'Small Java 17 library for normalized greeting messages.'` rõ hơn `'Best ever Java library'`. Đừng đưa secrets hoặc token vào POM: POM được xuất bản cho consumers và có thể đọc được bởi bất kỳ ai có quyền đọc repository.

### 4.3. Metadata giấy phép phải trung thực

Một POM có thể khai báo:

~~~groovy
pom {
    licenses {
        license {
            name = 'Apache License, Version 2.0'
            url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
            distribution = 'repo'
        }
    }
}
~~~

Đây là **cú pháp Gradle hợp lệ** để biểu diễn license metadata. Nhưng việc **ghi “Apache-2.0” trong POM không tự cấp quyền pháp lý** và không thay cho giấy phép thật. Chỉ khai thông tin nếu đúng với chủ sở hữu và license files của dự án. Khi đưa thư viện demo ra công khai, phải kiểm quyền tác giả và điền metadata được phê duyệt; các URL example được dùng trong bài chỉ là ví dụ học tập.

## 5. Maven Publish Plugin và software component

Bật plugin:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
~~~

`java-library` bổ sung khả năng `api`/`implementation` phù hợp với thư viện, đồng thời có `components.java` — một **software component** mô tả artifacts và dependency variants.

`maven-publish` tạo `publishing` extension:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'preview'
            url = layout.buildDirectory.dir('staging-repo')
        }
    }
}
~~~

Có hai cấu phần độc lập:

1. `publications`: **xuất bản cái gì và định danh ra sao** (component, artifacts, POM).
2. `repositories`: **xuất bản tới đâu** (file Maven repo, private Nexus/Artifactory, Maven Central qua quy trình thích hợp).

`from components.java` cho Gradle biết artifact và dependency metadata thuộc Java component. Nếu bỏ dòng đó và không thêm artifact tùy chỉnh, publication có thể chỉ còn metadata/POM mà thiếu JAR bạn muốn; đây là một lỗi cấu hình phổ biến.

### 5.1. `from components.java` khác `artifact tasks.jar`

Có thể thêm một JAR bằng API `artifact`, nhưng nếu dùng software component chuẩn, Gradle còn có thể công bố dependency variants/scopes và các artifacts bổ sung như sources/Javadoc. Vì thế, với thư viện Java thông thường, ưu tiên:

~~~groovy
from components.java
~~~

thay vì chỉ:

~~~groovy
artifact tasks.jar
~~~

**Đoạn thứ hai là trích đoạn so sánh**, không phải lựa chọn thay thế đầy đủ cho metadata component. Một custom artifact publication có thể cần cấu hình dependencies/variants theo mục tiêu của chính nó.

### 5.2. Sources và Javadoc JAR

Java plugin cho phép:

~~~groovy
java {
    withSourcesJar()
    withJavadocJar()
}
~~~

Khi công bố `components.java` với các variants đó, Gradle có thể tạo và publish:

~~~text
greeting-api-1.2.3.jar
greeting-api-1.2.3-sources.jar
greeting-api-1.2.3-javadoc.jar
greeting-api-1.2.3.pom
~~~

Các tên trên là **tên artifacts tại Maven repository** khi artifactId là `greeting-api`. Trong `build/libs`, files do Java tasks tạo có thể vẫn mang base name của Gradle project là `greeting-core`.

`sourcesJar` giúp IDE hiển thị source; `javadocJar` cung cấp tài liệu API. Chúng không tự làm cho chương trình chạy nhanh hơn và không chứa tất cả transitive runtime dependencies.

## 6. Cấu hình đầy đủ thông tin POM bằng Groovy DSL

Một publication có thể đặt metadata:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            groupId = 'org.example.academy'
            artifactId = 'greeting-api'
            version = project.version.toString()

            pom {
                name = 'Greeting API'
                description = 'Small Java 17 greeting library for Gradle publishing.'
                url = 'https://example.org/projects/greeting-api'

                licenses {
                    license {
                        name = 'Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                        distribution = 'repo'
                    }
                }

                developers {
                    developer {
                        id = 'training-team'
                        name = 'Training Team'
                        email = 'training@example.org'
                    }
                }

                scm {
                    connection = 'scm:git:https://example.org/scm/greeting-api.git'
                    developerConnection = 'scm:git:ssh://git@example.org/scm/greeting-api.git'
                    url = 'https://example.org/scm/greeting-api'
                }
            }
        }
    }
}
~~~

Đây là **trích đoạn publication**, cần `java-library`/`maven-publish` đã áp dụng. Những URL và email trong vùng `example.org` chỉ dùng minh họa định dạng; chúng không thể hiện repository hoặc đội ngũ có thật. Khi công bố artifact thật, thay bằng metadata đã kiểm chứng và xem xét license phù hợp.

### 6.1. Đọc từng nhóm metadata

**`pom.name`** là tên hiển thị, không phải task `jar` hay Gradle project name.

**`pom.description`** là đoạn mô tả cho consumers và repository browsers; đừng nhét secrets hoặc thông tin nội bộ không được phép chia sẻ.

**`pom.url`** nên trỏ đến trang dự án/tài liệu chính thức có thể truy cập bởi đối tượng của repository.

**`licenses.license`** gồm name/URL, và có thể có distribution/comments; repo công khai thường yêu cầu license metadata nhất quán với file LICENSE thật.

**`developers.developer`** chứa ID/name/email, nhưng không nên tự công bố địa chỉ cá nhân khi policy hoặc sự đồng ý không cho phép. Email generic/team có thể phù hợp nếu được tổ chức phê duyệt.

**`scm.connection`** diễn đạt URL source-control read-only có tiền tố `scm:git:...`. **`developerConnection`** dành cho developer access theo SCM convention; **`scm.url`** là trang browsable của source. Nếu project private, URL/metadata phải phù hợp phạm vi private repository.

### 6.2. Những trường POM khác có thể cần

Gradle `MavenPom` API còn có các trường như `inceptionYear`, `organization`, `issueManagement`, `properties`, `ciManagement` và thông tin mailing list khi phù hợp. Không bắt mọi dự án nhỏ khai tất cả trường này; hãy đọc yêu cầu của hệ thống repository đang nhắm tới.

Một **trích đoạn thêm vào `pom { }`** để minh họa:

~~~groovy
inceptionYear = '2026'

organization {
    name = 'Example Academy'
    url = 'https://example.org'
}

issueManagement {
    system = 'Issue Tracker'
    url = 'https://example.org/projects/greeting-api/issues'
}

properties = [
    'java.release': '17',
    'project.family': 'training'
]
~~~

Đây là các giá trị học tập dùng domain ví dụ. Không thêm metadata giả để “đủ form” khi publish thật; nhà phát hành phải điền thông tin chính xác.

### 6.3. Khi nào dùng `pom.withXml`?

Gradle hỗ trợ `pom.withXml { }` để can thiệp XML ở mức thấp khi cần một phần tử không có DSL chuẩn. Nhưng đây là **phương án nâng cao**: dễ tạo POM sai schema, duplicate tags hoặc metadata lệch với Gradle Module Metadata.

Nếu mục tiêu chỉ là `name`, `description`, `licenses`, `developers`, `scm` hoặc `url`, hãy dùng DSL kiểu dữ liệu trước. Sau mỗi customization phức tạp, chạy `generatePomFileForMavenJavaPublication`, kiểm XML và thử consumer thực tế.

## 7. Demo chạy được: xuất bản thư viện Java 17 vào Maven repository cục bộ

Bài thực hành chính là **một Gradle project hoàn chỉnh**, không yêu cầu tài khoản remote publisher. Ta cố ý dùng:

- Gradle project name: `greeting-core`.
- Project group: `org.example.academy`.
- Project version: `1.2.3`.
- Publication name: `mavenJava`.
- Publication artifactId: `greeting-api`.

Nhờ đó, người học có thể thấy rõ sự khác biệt giữa **tên project**, **tên task/publication** và **artifactId published**.

### 7.1. Cấu trúc thư mục

~~~text
greeting-core/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   └── java/
    │       └── org/example/academy/greeting/Greeting.java
    └── test/
        └── java/
            └── org/example/academy/greeting/GreetingTest.java
~~~

Bốn file Wrapper phải là file được sinh bởi Gradle, không phải file rỗng; chúng quyết định Gradle distribution của project. JDK17 cần được Gradle nhận diện để thực thi Java toolchain. Maven Central được dùng để resolve JUnit khi chưa cached.

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'greeting-core'
~~~

### 7.3. `build.gradle` hoàn chỉnh

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'org.example.academy'
version = '1.2.3'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }

    withSourcesJar()
    withJavadocJar()
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            groupId = 'org.example.academy'
            artifactId = 'greeting-api'
            version = project.version.toString()

            pom {
                name = 'Greeting API'
                description = 'Simple Java 17 greetings library.'
                url = 'https://example.org/projects/greeting-api'

                licenses {
                    license {
                        name = 'Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                        distribution = 'repo'
                    }
                }

                developers {
                    developer {
                        id = 'training-team'
                        name = 'Training Team'
                        email = 'training@example.org'
                    }
                }

                scm {
                    connection = 'scm:git:https://example.org/scm/greeting-api.git'
                    developerConnection = 'scm:git:ssh://git@example.org/scm/greeting-api.git'
                    url = 'https://example.org/scm/greeting-api'
                }
            }
        }
    }

    repositories {
        maven {
            name = 'preview'
            url = layout.buildDirectory.dir('staging-repo')
        }
    }
}
~~~

Đây là file Groovy DSL đầy đủ cho ví dụ single-project. `example.org` và email ở đó là những giá trị **được dành cho ví dụ minh họa**, không phải metadata được phê duyệt để đưa lên Maven Central. Đối với production, cần sửa đúng quyền sở hữu, URL, license, developers và SCM; không phát hành bản thật dưới danh tính ví dụ.

Điểm cần quan sát:

1. **`java-library`** tạo Java component và mô hình API/implementation.
2. **`maven-publish`** tạo extension `publishing` và publish tasks.
3. **`group = ...`** và **`version = ...`** là thuộc tính project; publication chọn explicit `groupId` và lấy `version` từ project.
4. **`artifactId = 'greeting-api'`** cố tình khác `rootProject.name`.
5. **`from components.java`** lấy artifact/dependency metadata từ Java component.
6. **`withSourcesJar()`/`withJavadocJar()`** thêm publications variants cho sources/Javadoc.
7. **`pom { ... }`** khai metadata có ngữ nghĩa cho Maven ecosystem.
8. **`repositories { maven { name = 'preview'; url = ... } }`** trỏ tới file repository trong `build/staging-repo`, nên lệnh publish thử không gửi dữ liệu ra server bên ngoài.
9. Test JUnit là test-scoped, không trở thành runtime dependency của public library.
10. Không có secrets, token hay username/password trong file demo.

### 7.4. `src/main/java/org/example/academy/greeting/Greeting.java`

~~~java
package org.example.academy.greeting;

/**
 * Produces small greeting messages.
 *
 * @since 1.2.3
 */
public final class Greeting {
    private Greeting() {
    }

    /**
     * Greets a name after trimming surrounding Unicode whitespace.
     *
     * @param rawName name to normalize, or null
     * @return a greeting line
     */
    public static String message(String rawName) {
        String name = rawName == null ? "" : rawName.strip();
        if (name.isEmpty()) {
            name = "bạn";
        }
        return "Xin chào, " + name + "!";
    }
}
~~~

Đây là Java 17 source biên dịch được bằng JDK17, chỉ dùng standard library. Phương thức `String.strip()` có từ Java 11. Không dùng Maven dependencies ở production library nên POM của demo sẽ không chứa JUnit hoặc Commons Lang trong `<dependencies>` của phần công bố.

### 7.5. `src/test/java/org/example/academy/greeting/GreetingTest.java`

~~~java
package org.example.academy.greeting;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void normalizesName() {
        assertEquals("Xin chào, Gradle!", Greeting.message(" Gradle "));
    }

    @Test
    void usesFallback() {
        assertEquals("Xin chào, bạn!", Greeting.message("   "));
    }

    @Test
    void acceptsNull() {
        assertEquals("Xin chào, bạn!", Greeting.message(null));
    }
}
~~~

Test này dùng JUnit Jupiter; `testImplementation` cấp JUnit API và `testRuntimeOnly` cấp Platform Launcher cho test runtime. `test` chạy ba `@Test` methods, nhưng POM của published Java component không tự đẩy JUnit test dependencies sang consumers.

### 7.6. Chạy tests và kiểm artifact output

Từ thư mục `greeting-core`:

~~~bash
./gradlew clean build
./gradlew test
./gradlew jar
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean build
~~~

Nếu Wrapper/JDK/repository phù hợp, ba tests pass và các file chính được tạo:

~~~text
build/libs/
    greeting-core-1.2.3.jar
    greeting-core-1.2.3-sources.jar
    greeting-core-1.2.3-javadoc.jar
~~~

`withSourcesJar()`/`withJavadocJar()` và việc Gradle chạy các tasks tương ứng giải thích vì sao có ba artifacts. Tên output `greeting-core` theo project/archive base name, **chưa phải tên tọa độ `greeting-api` tại Maven repository**.

### 7.7. Sinh POM trước khi publish

Dùng:

~~~bash
./gradlew generatePomFileForMavenJavaPublication
~~~

Gradle tạo một file POM theo convention tại:

~~~text
build/publications/mavenJava/pom-default.xml
~~~

Hãy mở file này và tìm:

~~~xml
<groupId>org.example.academy</groupId>
<artifactId>greeting-api</artifactId>
<version>1.2.3</version>
<name>Greeting API</name>
<description>Simple Java 17 greetings library.</description>
<url>https://example.org/projects/greeting-api</url>
~~~

Khối XML là **trích đoạn những phần tử cần kiểm tra**, không phải một XML document đầy đủ để tự lưu thay cho Gradle-generated POM. File thật còn có XML namespace, modelVersion, packaging, licenses, developers, SCM và có thể metadata marker/cấu trúc khác theo Gradle version.

Quan trọng: task tên **`generatePomFileForMavenJavaPublication`** lấy `mavenJava` từ **publication name**. Nó không lấy `greeting-api` để tạo task name.

### 7.8. Publish vào local file Maven repository

Sau khi kiểm thử:

~~~bash
./gradlew publishMavenJavaPublicationToPreviewRepository
~~~

Tên task được tạo theo công thức:

~~~text
publish + <PublicationName> + PublicationTo + <RepositoryName> + Repository
~~~

Tức là `mavenJava` + `preview` tạo `publishMavenJavaPublicationToPreviewRepository`. Nếu bạn đổi publication/repository name, task name cũng đổi; dùng `./gradlew tasks --all` để xem tên thật.

Thư mục publish dự kiến:

~~~text
build/staging-repo/
└── org/
    └── example/
        └── academy/
            └── greeting-api/
                └── 1.2.3/
                    ├── greeting-api-1.2.3.pom
                    ├── greeting-api-1.2.3.jar
                    ├── greeting-api-1.2.3-sources.jar
                    └── greeting-api-1.2.3-javadoc.jar
~~~

**Đây là cây các file artifact chính**, không liệt kê mọi checksum, `.module`, `maven-metadata.xml` hoặc metadata khác có thể được sinh. Repo path được xác định bởi groupId chuyển dấu chấm thành directory separators, tiếp theo artifactId và version.

Việc JAR trong `build/libs` tên `greeting-core-1.2.3.jar` nhưng JAR trong Maven repository tên `greeting-api-1.2.3.jar` là **đúng**: Gradle ánh xạ artifact được publish theo Maven coordinate.

### 7.9. `publish` khác `publishToMavenLocal`

Với cấu hình trên:

~~~bash
./gradlew publish
~~~

sẽ publish các publications vào **những publishing.repositories đã khai báo**, ở đây chỉ có `preview`. Khi repo có nhiều đích, `publish` có thể tác động **mọi repository** đã cấu hình; không chạy bừa trong CI với credentials thật khi bạn chỉ muốn thử local.

Trong khi đó:

~~~bash
./gradlew publishToMavenLocal
~~~

publish vào Maven local repository, thông thường:

~~~text
~/.m2/repository/org/example/academy/greeting-api/1.2.3/
~~~

`publishToMavenLocal` **không yêu cầu** phải thêm `mavenLocal()` vào `publishing.repositories`; đó là lifecycle task riêng của Maven Publish Plugin. Maven local là môi trường developer, có thể bị stale/thiếu files; không dùng nó như một authoritative release repository cho CI/production.

Một project tiêu thụ dùng `repositories { mavenLocal() }` có thể resolve artifacts đã publishToMavenLocal, nhưng nên dùng chủ đích và hiểu precedence repository khi cùng tọa độ tồn tại ở remote. Để test isolation tốt hơn, publish vào `build/staging-repo` rồi cho consumer trỏ vào chính thư mục đó.

## 8. Thử consumer để xác minh đúng tọa độ

Có POM chưa đủ: một smoke-test consumer nên chứng minh dependencies có thể resolve và code có thể dùng JAR đúng coordinates.

### 8.1. Ví dụ consumer Gradle ở thư mục bên cạnh

Giả sử:

~~~text
workspace/
├── greeting-core/
│   └── build/staging-repo/
└── greeting-consumer/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/demo/Consumer.java
~~~

`greeting-consumer/settings.gradle`:

~~~groovy
rootProject.name = 'greeting-consumer'
~~~

`greeting-consumer/build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    maven {
        url = uri('../greeting-core/build/staging-repo')
    }
}

dependencies {
    implementation 'org.example.academy:greeting-api:1.2.3'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Consumer'
}
~~~

`greeting-consumer/src/main/java/demo/Consumer.java`:

~~~java
package demo;

import org.example.academy.greeting.Greeting;

public final class Consumer {
    private Consumer() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message(" Gradle "));
    }
}
~~~

Trước tiên publish thư viện ở `greeting-core`, sau đó từ `greeting-consumer` chạy Wrapper của **consumer**:

~~~bash
./gradlew run
~~~

Stdout do Java main in là:

~~~text
Xin chào, Gradle!
~~~

Đây là **demo consumer riêng**, có thể chạy khi consumer cũng có Gradle Wrapper thật và cấu trúc thư mục đúng như hình. Path `../greeting-core/build/staging-repo` là relative to consumer project, không phải URL remote. `application` plugin ở consumer cung cấp `run`; publisher chỉ dùng `java-library` nên không có `run` mặc định.

### 8.2. Thử bằng `javac`/`java` không cần Gradle consumer

Nếu đã có file `build/libs/greeting-core-1.2.3.jar` trong publisher, tạo file `demo-client/Main.java`:

~~~java
import org.example.academy.greeting.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message(" Java 17 "));
    }
}
~~~

Từ thư mục `greeting-core`, sau `./gradlew jar`, Linux/macOS:

~~~bash
javac -encoding UTF-8 \
    -cp build/libs/greeting-core-1.2.3.jar \
    -d demo-client/out demo-client/Main.java

java -cp "demo-client/out:build/libs/greeting-core-1.2.3.jar" Main
~~~

Stdout chính xác:

~~~text
Xin chào, Java 17!
~~~

Trên Windows PowerShell, chỉ khác đường dẫn và classpath separator:

~~~powershell
javac -encoding UTF-8 -cp build\libs\greeting-core-1.2.3.jar -d demo-client\out demo-client\Main.java
java -cp "demo-client\out;build\libs\greeting-core-1.2.3.jar" Main
~~~

`javac`/`java` không kiểm POM, vì chúng đọc trực tiếp JAR file; thử consumer Gradle ở mục 8.1 mới xác minh **Maven coordinate + repository + metadata resolution**. Cả hai cách bổ sung cho nhau.

## 9. Đọc POM dependencies: API, implementation và test scope

Một publication không chỉ chứa tên/artifact; với `from components.java`, Gradle còn ánh xạ dependency metadata của Java component. Đặc biệt `java-library` phân biệt `api` và `implementation`:

| Gradle declaration | Vai trò | Maven POM mapping điển hình |
| --- | --- | --- |
| `api 'g:a:v'` | Public API dependency consumer cần khi compile | `compile` scope |
| `implementation 'g:b:v'` | Internal dependency nhưng cần runtime | `runtime` scope |
| `compileOnly 'g:c:v'` | Cần compile publisher, không mặc định đi cùng runtime | Không mặc định công bố như runtime dependency |
| `runtimeOnly 'g:d:v'` | Chỉ cần khi chạy library | `runtime` scope |
| `testImplementation 'g:e:v'` | Dependency chỉ cho tests | Không đưa vào main Java publication |
| `testRuntimeOnly 'g:f:v'` | Dependency chỉ để test runtime | Không đưa vào main Java publication |

Đây là mapping **điển hình của Java Library component** khi publish theo Maven POM. Những biến thể Gradle cụ thể, platform constraints và custom configurations có thể cần kiểm tra output thật; POM không thể mô tả mọi khả năng variant-aware dependency model của Gradle.

### 9.1. Ví dụ API vs implementation

Một **trích đoạn** cho thư viện khác:

~~~groovy
dependencies {
    api 'org.apache.commons:commons-lang3:3.17.0'
    implementation 'org.slf4j:slf4j-api:2.0.17'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
}
~~~

Nếu được publish bằng `from components.java`, POM thường ghi Commons Lang ở `compile` scope và SLF4J ở `runtime` scope. JUnit test dependency không trở thành dependency runtime của consumer.

Đây **không phải dependencies của demo `Greeting`**: demo chỉ dùng JDK standard library cho production API. Không thêm các libs vào demo chỉ để “có POM dependencies” nếu code không cần chúng.

### 9.2. Published POM và Gradle Module Metadata khác nhau

Khi publish, Gradle có thể xuất cả:

~~~text
greeting-api-1.2.3.pom
greeting-api-1.2.3.module
~~~

POM là định dạng Maven hiểu rộng rãi. **Gradle Module Metadata (GMM)** mô tả rich variants, attributes, capabilities và version constraints chi tiết hơn; Gradle consumers có thể ưu tiên dùng GMM khi có.

Không chỉnh POM bằng tay sau publish và kỳ vọng `.module` tự thay theo. Nếu metadata và JAR mâu thuẫn, consumer có thể resolve khác nhau tùy tool. Việc mapping từ Gradle rich versions/variants sang Maven POM có thể **mất thông tin**; Gradle có thể đưa ra warnings khi một tính năng không thể biểu diễn đầy đủ trong Maven.

### 9.3. Declared versions và resolved versions

Mặc định, khi publish POM dependency versions, Gradle thường sử dụng **declared versions** từ build declarations. Ví dụ:

~~~groovy
dependencies {
    api 'org.example:api:1.+'
}
~~~

Đây là **trích đoạn khái niệm**, không phải dependency có thật trong demo; selector `1.+` là dynamic và không phù hợp cho một POM public release ổn định nếu không có kiểm soát.

Một publication có thể chọn **resolved versions** bằng `versionMapping`:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            versionMapping {
                usage('java-api') {
                    fromResolutionOf('runtimeClasspath')
                }
                usage('java-runtime') {
                    fromResolutionResult()
                }
            }
        }
    }
}
~~~

Ý nghĩa:

- `fromResolutionOf('runtimeClasspath')` dùng versions đã resolve từ configuration đó để ánh xạ API dependencies.
- `fromResolutionResult()` dùng kết quả resolution của variant/usage mặc định tương ứng.
- Với một Java Library project, API dependencies thường ánh xạ sang Maven `compile`; implementation dependencies sang Maven `runtime`.

Khi kết hợp dependency locking và release reproducibility, resolved versions có thể hữu ích. Nhưng không áp dụng `versionMapping` như một mẹo chữa mọi lỗi POM: phải hiểu các configurations đã được resolve, scope và compatibility của consumer, đồng thời review generated POM.

## 10. Version strategy: release, snapshot và định danh ổn định

### 10.1. Semantic Versioning là quy ước, không phải Gradle tự kiểm

Ví dụ:

~~~text
1.2.3   release ổn định
1.2.4   patch mới
1.3.0   minor mới
2.0.0   major mới
1.2.4-SNAPSHOT   build thử nghiệm
~~~

Gradle không tự phân tích Java API để chắc chắn bạn tăng đúng major/minor/patch. Đó là chính sách release của nhóm và cần kiểm tra bằng tests/ABI compatibility tools nếu muốn.

**`version` cũng là project property**; nếu module dùng `group`/`version` tại root mà nhiều subprojects share version, phải xác định những modules nào được release cùng nhau. Không tăng version root tùy tiện nếu các artifacts được phát hành độc lập.

### 10.2. Tách snapshots và releases

Một repository server thường có policy khác nhau cho snapshot và release. Ở mức minh họa, cấu hình repository đích theo version có thể dùng:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'preview'

            def releaseRepo =
                layout.buildDirectory.dir('staging-repo/releases')
            def snapshotRepo =
                layout.buildDirectory.dir('staging-repo/snapshots')

            url = version.toString().endsWith('-SNAPSHOT')
                ? snapshotRepo
                : releaseRepo
        }
    }
}
~~~

**Đây là cấu hình repository thay thế**, không dán cùng nguyên khối `publishing.repositories` trong demo nếu chưa quyết định nơi lưu. Nó dùng **local file repositories**, không phải remote endpoint thực, để minh họa release/SNAPSHOT routing. Trong thực tế URL snapshot/release cần lấy từ provider đáng tin và policy server.

### 10.3. Version nên tới từ đâu?

Một số chiến lược hợp lệ:

- `version = '1.2.3'` trong `build.gradle`, explicit và dễ review.
- `version=1.2.3` trong `gradle.properties`, phù hợp nhiều modules dùng convention.
- Một release plugin hoặc CI versioning policy lấy version từ tag/commit, nhưng phải tránh thay đổi ngoài ý muốn giữa local/CI.
- Chỉ định publication version khác project version **khi có lý do rõ** và kiểm đúng JAR/POM output.

Không nhét hostname, timestamp cục bộ hoặc secret vào version mà không có policy. Với release tọa độ cố định, ưu tiên reproducible build và immutable artifact.

### 10.4. Không republish release cùng coordinates

Giả sử consumer có:

~~~groovy
implementation 'org.example.academy:greeting-api:1.2.3'
~~~

Nếu bạn publish lại JAR khác dưới cùng tọa độ `1.2.3`, caches, metadata và checksum/signature ở các clients có thể không đồng nhất. Repository release nên ngăn overwrite. Khi sửa lỗi, hãy **tăng version** và phát hành bản mới; với artifact đã công bố công khai, không âm thầm thay bytes/POM.

## 11. Xuất bản remote: credentials và bảo mật

Demo phía trên chỉ publish vào **build/staging-repo**, không cần credentials. Với Nexus/Artifactory hoặc service khác, thường cần token hoặc username/password.

Nguyên tắc:

1. **Không commit secrets** vào `build.gradle`, `gradle.properties` được theo dõi bởi Git hoặc POM metadata.
2. CI dùng secret store; developer dùng môi trường hoặc file Gradle properties nằm ngoài repository và có quyền truy cập thích hợp.
3. Cấp token phạm vi publish tối thiểu, phân biệt snapshot vs release permissions.
4. Sử dụng HTTPS và kiểm repository ownership/namespace trước khi gửi artifacts.
5. Không in credentials vào logs hoặc stack traces; kiểm report/log settings.
6. Chỉ chạy publish remote sau khi tests, POM inspection và signing/verification requirements đã pass.

Một **trích đoạn remote publishing riêng** để tham khảo, không phải phần demo local:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'internalReleases'
            url = uri(
                providers.gradleProperty('releaseRepositoryUrl').get()
            )

            credentials(PasswordCredentials) {
                username = providers.gradleProperty('releaseUser').orNull
                password = providers.gradleProperty('releasePassword').orNull
            }
        }
    }
}
~~~

Nó đòi hỏi project properties `releaseRepositoryUrl`, `releaseUser` và `releasePassword` đã được cung cấp **qua môi trường an toàn**. Nếu không có, nó sẽ fail; **đây là mẫu tích hợp**, không phải lệnh chạy được với demo local. Không dùng các URL/example.org bên trên làm đích remote thật.

Một số Gradle repositories hỗ trợ automatic credentials resolution dựa vào tên repository, ví dụ `internalReleasesUsername`/`internalReleasesPassword` qua Gradle properties khi cấu hình loại credential phù hợp. Chọn một cơ chế thống nhất và không hard-code secrets.

### 11.1. Maven Central không chỉ cần một POM

Một release công khai có thể cần kiểm soát namespace/ownership, license/SCM/developer metadata, signatures, artifact integrity và quy trình staging/validation của nhà cung cấp. **`maven-publish` cung cấp khả năng publish cơ bản, không tự bảo đảm mọi yêu cầu của Maven Central đã đáp ứng.** Hãy kiểm hướng dẫn hiện hành của nhà cung cấp dịch vụ/portal phù hợp trước khi thiết kế pipeline production.

`signing` là plugin Gradle riêng nếu cần ký artifacts; không nhầm signature với checksum và không đặt private signing key trong source control.

## 12. Multi-project build: group chung, artifactId riêng, version có kế hoạch

Giả sử repository:

~~~text
platform/
├── settings.gradle
├── gradle.properties
├── build-logic/
├── greeting-api/
│   └── build.gradle
└── greeting-tools/
    └── build.gradle
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'platform'
include 'greeting-api', 'greeting-tools'
~~~

Hai modules có thể cùng `groupId=org.example.academy` nhưng artifactIds khác nhau:

~~~text
org.example.academy:greeting-api:1.2.3
org.example.academy:greeting-tools:1.2.3
~~~

Một cách quản lý cấu hình là convention plugin dùng chung: nó apply `java-library`/`maven-publish`, chuẩn hóa POM metadata và đặt `artifactId` theo project name hoặc từ project-specific property có kiểm chứng.

**Đừng tự áp `maven-publish` lên tất cả project kể cả root aggregator hoặc module chỉ có application/distribution.** Chỉ publish module có artifact và metadata đúng. Nếu đổi artifactId một module, phải kiểm thử consumers của module đó.

### 12.1. group và version dùng chung nhưng không ép một release cycle

Nếu modules luôn release cùng nhau, `group`/`version` ở shared config có thể phù hợp. Nếu modules release độc lập, mỗi project cần nguồn version riêng và changelog/tag riêng; không gán bừa version của root lên mọi publication.

Ví dụ **trích đoạn per-module**:

~~~groovy
group = 'org.example.academy'
version = '2.1.0'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifactId = 'greeting-tools'
        }
    }
}
~~~

Đoạn này cần plugin và component đúng. Đừng suy `project(':greeting-tools')` tương đương dependency từ Maven: project dependency hoạt động trên local project variants, còn published dependency cần coordinates/repository.

### 12.2. Thay đổi artifactId cần chiến lược migration

Khi đổi từ `org.example.academy:greeting-old:1.2.3` sang `org.example.academy:greeting-api:2.0.0`, consumers phải cập nhật coordinates. Maven có cơ chế **relocation POM** để thông báo old/new coordinates khi một module được di chuyển. Tuy nhiên:

- Relocation chỉ hữu ích nếu module vẫn tương đương về ngữ nghĩa.
- Không phù hợp để giải thích trường hợp một artifact cũ bị chia thành hai artifacts không thay thế trực tiếp.
- Repository có thể chứa cả old và new artifacts, dẫn tới duplicate classes nếu consumers giữ hai dependencies.
- Cần review POM relocation và test bằng consumer, không chỉ đổi tên file ở `build/libs`.

**Relocation là một bài nâng cao**; với mục tiêu cơ bản của bài này, điều cần nhớ là **groupId/artifactId là public coordinates**, đổi chúng là thay đổi compatibility của build ecosystem.

## 13. Kiểm tra trước khi công bố artifact

Một checklist thực tế theo thứ tự:

1. `./gradlew test` hoặc `./gradlew check` — source/test code đạt yêu cầu?
2. `./gradlew jar` — artifact có classes/resources mong đợi?
3. `./gradlew generatePomFileForMavenJavaPublication` — POM có groupId/artifactId/version/name đúng?
4. Mở `build/publications/mavenJava/pom-default.xml` — giấy phép, developers, SCM, URLs, dependencies có đúng?
5. `./gradlew publishMavenJavaPublicationToPreviewRepository` — thử publish vào file repository.
6. Kiểm đường dẫn Maven repository và filenames có tương ứng coordinates?
7. Tạo consumer thật resolve `org.example.academy:greeting-api:1.2.3` từ preview repo.
8. Chạy test/compile consumer và kiểm class/package/API.
9. Nếu release public: review checksum/signature, metadata, Javadoc/sources và license files.
10. Chỉ sau khi đủ approvals mới chạy publish remote có quyền ghi.

### 13.1. Không dùng `publish --dry-run` làm bằng chứng đã publish thành công

~~~bash
./gradlew publish --dry-run
~~~

`--dry-run` có thể giúp **xem task graph dự kiến**, nhưng không gửi artifact lên repository và không xác minh repository credentials hay server validation. Để xác nhận khả năng publish thực sự mà không chạm remote, dùng **file Maven repository** riêng như demo.

### 13.2. Không commit generated artifacts như source code nếu không có policy

`build/publications`, `build/libs` và `build/staging-repo` thường là **generated build output**, không cần commit. Điều nên commit là:

- `settings.gradle` và `build.gradle`/convention plugins.
- Gradle Wrapper files.
- Java source/test source, resource files.
- License file và release metadata được quản lý có chủ đích.
- CI workflow/tài liệu release.

Nếu repository tổ chức lưu artifact binaries có chính sách riêng, làm theo chính sách ấy, nhưng đừng copy POM generated vào source rồi chỉnh tay thành nguồn sự thật thứ hai.

## 14. Lỗi phổ biến và hướng chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| POM có artifactId là `greeting-core` | Không override artifactId; mặc định lấy project.name | Đặt `artifactId='greeting-api'` trong MavenPublication |
| `gradlew jar` thành công nhưng không có POM | `jar` không phải publish task; `maven-publish` chưa apply | Apply plugin, tạo MavenPublication, chạy generatePom |
| `components.java` không có | Chưa apply `java`/`java-library` đúng project | Apply plugin vào module publish |
| `MavenPublication` không được nhận diện | Thiếu `maven-publish` hoặc sai scope | Kiểm `plugins { id 'maven-publish' }` |
| POM groupId/version là `unspecified` hoặc sai | Project group/version chưa cấu hình/override | Đặt identity có chủ đích và kiểm output |
| Build JAR name khác published artifact filename | artifactId khác project/archive base name | Đây có thể đúng; kiểm Maven repo path |
| `generatePomFileForMavenJavaPublication` không tồn tại | Publication không tên `mavenJava` hoặc chưa tạo | Dùng `./gradlew tasks --all` tìm task thật |
| `publishMavenJavaPublicationToPreviewRepository` không tồn tại | Repo name/publication name khác | Kiểm `publishing.repositories` và `publications` |
| `publish` không tạo file trong `~/.m2` | `publish` không phải `publishToMavenLocal` | Dùng đúng task hoặc preview repo |
| Consumer không tìm được module | Repo URL, groupId/artifactId/version không khớp | Kiểm POM và directory layout |
| Consumer biên dịch không thấy class | Java package/API khác kỳ vọng hoặc JAR không có class | Dùng `jar tf` và kiểm imports |
| Consumer thiếu runtime library | POM dependency metadata sai/missing | Dùng `from components.java` và kiểm scope |
| JUnit xuất hiện như production dependency | Scope/test configuration bị mô hình sai | Dùng `testImplementation`, kiểm POM |
| POM chứa link/example email không có thật | Demo metadata chưa được đổi trước public release | Điền metadata thật, review quyền sở hữu |
| POM license không trùng LICENSE file | Metadata do copy paste | Đồng bộ giấy phép và quyền phát hành |
| GitHub/SCM URL bị sai | `pom.scm` không khớp repository | Kiểm URL bằng reviewer, không dùng credential trong URL |
| Gradle Module Metadata và POM khác nhau | Rich variants/constraints không map đầy đủ | Kiểm warnings, thử Gradle và Maven consumers |
| Repo từ chối overwrite | Release coordinates đã tồn tại, immutable policy | Tăng version và phát hành lại đúng cách |
| `401`/`403` khi publish | Thiếu quyền/credentials hoặc namespace ownership | Kiểm secret store, IAM/publishing token |
| `--dry-run` thành công nhưng remote publish fail | Dry-run không gọi server | Dùng staging test/repo riêng có quyền phù hợp |
| Snapshot version bị nhầm release repo | Repo URL/version routing sai | Kiểm `endsWith('-SNAPSHOT')` và server policy |
| Toolchain không tìm JDK 17 | JDK thiếu và resolver chưa cấu hình | Cài/cấu hình JDK17, kiểm `./gradlew --version` |
| HTML/Javadoc JAR không có | Chưa bật `withJavadocJar()` hoặc task fail | Kiểm Java plugin/task setup |
| Publish thành công nhưng consumer thấy artifact cũ | Maven local/Gradle cache hoặc repo precedence | Kiểm coordinates, cache và release immutability |

### 14.1. Quy trình debug theo câu hỏi

~~~text
1. Tôi đang publish đúng Gradle project nào?
                     |
                     v
2. java-library/java + maven-publish đã apply?
                     |
                     v
3. MavenPublication có from components.java?
                     |
                     v
4. groupId / artifactId / version cuối cùng là gì?
                     |
                     v
5. generatePomFile... có POM đúng?
                     |
                     v
6. publish task có đúng repository name?
                     |
                     v
7. Repo path chứa artifact/POM/module đúng tọa độ?
                     |
                     v
8. Consumer resolve đúng repository và version?
                     |
                     v
9. Kiểm API, dependencies, license/SCM, CI/signing policy
~~~

## 15. Bài tập thực hành kèm đáp án

### Bài A — suy ra coordinate mặc định

`settings.gradle`:

~~~groovy
rootProject.name = 'core-strings'
~~~

`build.gradle`:

~~~groovy
group = 'org.example.academy'
version = '2.0.0'
~~~

Nếu publication chỉ dùng `from components.java` và không override identity, coordinate mặc định là **`org.example.academy:core-strings:2.0.0`**.

### Bài B — publication name có phải artifactId không?

Publication:

~~~groovy
mavenJava(MavenPublication) {
    from components.java
    artifactId = 'greeting-api'
}
~~~

`mavenJava` là tên Gradle publication và xuất hiện trong task `generatePomFileForMavenJavaPublication`. `greeting-api` là artifactId của published coordinate. **Không giống nhau.**

### Bài C — project JAR name và published JAR name

Project name `greeting-core`, version `1.2.3`, artifactId `greeting-api`. File `build/libs` thường có tên `greeting-core-1.2.3.jar`, còn Maven repository lưu file `greeting-api-1.2.3.jar`. **Đây là trạng thái hợp lệ.**

### Bài D — thay `pom.name` có ảnh hưởng dependency string không?

Không. Nếu `pom.name` đổi thành “Greeting Java Library” nhưng `groupId`/`artifactId`/`version` giữ nguyên, consumer vẫn khai `org.example.academy:greeting-api:1.2.3`.

### Bài E — làm sao xem POM trước publish?

Chạy:

~~~bash
./gradlew generatePomFileForMavenJavaPublication
~~~

Mở `build/publications/mavenJava/pom-default.xml`. Kiểm identity, license, developer, SCM và dependencies.

### Bài F — POM có JUnit test dependency không?

Trong demo, JUnit được khai qua `testImplementation` và `testRuntimeOnly`. Khi publish `components.java`, những dependencies đó **không thuộc runtime API của Java library**, nên không nên được công bố như production dependencies.

### Bài G — `publish` có tự đưa lên Maven Local không?

Không. `publish` đi tới các repositories được định nghĩa trong `publishing.repositories`. Để publish Maven Local, chạy `./gradlew publishToMavenLocal`. Trong demo, `publish` đi tới `build/staging-repo`.

### Bài H — release version nên đổi thế nào khi sửa lỗi?

Nếu `1.2.3` đã publish immutable và bạn sửa một bug, phát hành **version mới** (ví dụ `1.2.4`) thay vì overwrite `1.2.3`. Cần release tag, changelog và validation theo policy.

### Bài I — khi nào cần `versionMapping`?

Khi muốn xuất bản **resolved versions** thay declared versions, ví dụ dependency locking hoặc dynamic versions đã được chọn có chủ đích. Cần kiểm generated POM và compatibility, không áp dụng vô điều kiện.

### Bài J — làm sao kiểm API của JAR mà không cần Maven consumer?

Dùng `jar tf` để kiểm `Greeting.class`, hoặc compile Java consumer với `javac -cp` và chạy `java -cp` như mục 8.2. Nhưng cách này **không kiểm Maven metadata/repository resolution**; vẫn cần Gradle consumer smoke test.

### Bài K — POM licenses đủ để khẳng định có quyền publish chưa?

Chưa. Metadata chỉ là lời khai về license. Khi công bố công khai, cần kiểm quyền tác giả, license thực, nguồn bên thứ ba và yêu cầu repository.

### Bài L — đổi groupId có phải refactor Java package?

Không nhất thiết. GroupId là tọa độ publication, package là namespace Java classes. Nhưng đổi coordinate ảnh hưởng consumers và có thể cần relocation POM.

## 16. Checklist trước khi merge cấu hình xuất bản

1. Đã đặt `group` và `version` đúng nguồn sự thật?
2. Project name và Maven `artifactId` có quan hệ rõ ràng, không bị nhầm lẫn?
3. `MavenPublication` có `from components.java` cho Java library?
4. `groupId`, `artifactId`, `version` ở generated POM đúng thông số release?
5. `pom.name`, `description` và `url` mô tả đúng thư viện?
6. `licenses` trùng với giấy phép thật và file LICENSE?
7. `developers`/`scm` là thông tin được phê duyệt, không dùng URL/email minh họa khi public?
8. `api`/`implementation`/`testImplementation` có mapping đúng cho consumers?
9. Nếu dùng `versionMapping`, đã review phiên bản resolved trong POM?
10. Có sources/Javadoc artifacts phù hợp yêu cầu repository?
11. Đã chạy `generatePomFileForMavenJavaPublication` và đọc file POM thật?
12. Đã thử `publishMavenJavaPublicationToPreviewRepository` vào file repository an toàn?
13. Consumer có resolve đúng coordinate và chạy được API?
14. Release repository có quy tắc immutable, tách snapshot/release nếu cần?
15. Remote credentials/signing keys có nằm trong secret store, không commit và không vào logs?
16. CI chỉ publish remote sau khi tests, metadata checks và approvals hoàn tất?

## 17. Tài liệu tham khảo chính thức

- [Gradle — The Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): `MavenPublication`, identity defaults/overrides, POM DSL, publish tasks, Maven Local, versionMapping.
- [Gradle — Publishing a Project as Module](https://docs.gradle.org/current/userguide/publishing_setup.html): định nghĩa what/where/how to publish.
- [Gradle — MavenPublication API](https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/MavenPublication.html): groupId/artifactId/version, `from` component, artifacts và POM.
- [Gradle — MavenPom API](https://docs.gradle.org/current/dsl/org.gradle.api.publish.maven.MavenPom.html): descriptive metadata và POM customization.
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): `.module` và giới hạn chuyển đổi sang Maven POM.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`/`implementation` và consumer dependency semantics.
- [Gradle — Publishing Customization](https://docs.gradle.org/current/userguide/publishing_customization.html): thêm/bỏ artifacts và variants khi xuất bản.
- [Gradle — Signing Plugin](https://docs.gradle.org/current/userguide/signing_plugin.html): ký artifacts theo release policy.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): cấu trúc `project`, metadata và dependency scopes.
- [Semantic Versioning 2.0.0](https://semver.org/): quy ước major/minor/patch khi đội chọn SemVer.
