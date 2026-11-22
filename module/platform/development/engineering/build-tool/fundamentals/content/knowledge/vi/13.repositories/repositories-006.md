# Thứ tự kho, phạm vi nội dung kho và nguồn tải artifact

Khi một dự án Java cần thư viện, công cụ build phải biết tìm artifact ở đâu, tìm theo thứ tự nào và kho nào được phép cung cấp loại nội dung nào. Một dự án có thể khai báo nhiều repository: kho nội bộ, kho proxy Maven Central, kho snapshot, kho release hoặc kho dành riêng cho plugin. Nếu cấu hình không rõ ràng, build có thể tải nhầm nguồn, không tìm thấy dependency, dùng phiên bản cũ hoặc vô tình lấy một artifact không được phép sử dụng.

Ba câu hỏi cần được trả lời khi cấu hình repository là:

1. **Thứ tự kho:** công cụ kiểm tra các repository theo thứ tự nào?
2. **Phạm vi nội dung:** mỗi repository được phép cung cấp những group, module, version hoặc loại artifact nào?
3. **Nguồn tải artifact:** metadata và tệp thực tế được tải từ kho nào, và làm thế nào để xác nhận nguồn đó?

Bài học này tập trung vào Maven và Gradle, hai công cụ phổ biến trong hệ sinh thái Java. Cả hai đều hỗ trợ nhiều repository, nhưng cách áp dụng thứ tự và cách giải quyết dependency có những điểm khác nhau.

## 1. Repository chứa những gì?

Repository là nơi lưu metadata và artifact để công cụ build có thể phân giải dependency hoặc plugin. Với Maven, một artifact thường được nhận diện bằng các tọa độ:

    groupId:artifactId:version

Ví dụ:

    org.example:payment-client:3.2.1

Repository Maven thường tổ chức đường dẫn theo groupId, artifactId và version:

    org/example/payment-client/3.2.1/
      payment-client-3.2.1.pom
      payment-client-3.2.1.jar
      payment-client-3.2.1-sources.jar
      payment-client-3.2.1-javadoc.jar

Các tệp có vai trò khác nhau:

- **POM:** metadata mô tả artifact, dependency bắc cầu, packaging và thông tin build.
- **JAR:** bytecode và tài nguyên của thư viện.
- **sources JAR:** mã nguồn đi kèm để đọc hoặc debug.
- **javadoc JAR:** tài liệu API.
- **Metadata repository:** thông tin hỗ trợ phân giải version, đặc biệt với SNAPSHOT và version range.
- **Checksum/signature:** dữ liệu hỗ trợ kiểm tra tính toàn vẹn hoặc xác thực artifact.

Một repository có thể chứa nhiều loại artifact và nhiều version. Quy tắc cấu hình repository quyết định công cụ có được phép tìm và tải những nội dung đó hay không.

## 2. Các loại repository thường gặp

### Local repository

Local repository nằm trên máy của người phát triển. Với Maven, vị trí mặc định thường là:

    ~/.m2/repository

Trên Windows, đường dẫn thường có dạng:

    C:\Users\your-user\.m2\repository

Local repository lưu các dependency đã tải, artifact cài đặt cục bộ và metadata liên quan. Maven thường kiểm tra local repository trước khi tải từ remote repository. Nếu artifact phù hợp đã có sẵn và không cần kiểm tra cập nhật, Maven có thể dùng bản local.

Có thể cài một artifact của dự án vào local repository bằng:

    mvn install

Lệnh này hữu ích khi một module được build và cần được module khác trên cùng máy sử dụng. Artifact được cài cục bộ không tự động xuất hiện trên repository của cả nhóm.

### Remote repository

Remote repository nằm trên máy chủ và được truy cập qua HTTP(S), hoặc một giao thức được công cụ hỗ trợ. Những nguồn phổ biến gồm:

- Maven Central hoặc repository công khai khác.
- Repository manager nội bộ của tổ chức.
- Kho release do nhóm phát hành quản lý.
- Kho snapshot dùng cho artifact đang phát triển.
- Kho proxy hoặc group repository tổng hợp nhiều nguồn.

Remote repository là nguồn mà máy build truy cập khi artifact chưa có sẵn hoặc cần kiểm tra cập nhật.

### Repository manager và group repository

Trong tổ chức, người dùng thường cấu hình một địa chỉ repository manager thay vì khai báo trực tiếp nhiều máy chủ công khai. Repository manager có thể hoạt động như proxy, cache hoặc group/virtual repository.

Ví dụ, một địa chỉ nội bộ có thể tổng hợp:

    company-group
       |----> company-releases
       |----> company-snapshots
       +----> maven-central-proxy

Client chỉ cần truy cập company-group. Repository manager quyết định kho thành phần nào có thể cung cấp artifact, áp dụng quyền truy cập, cache và chính sách bảo mật.

Group repository giúp thống nhất nguồn tải và giảm việc mỗi dự án tự cấu hình nhiều URL. Tuy nhiên, thứ tự các kho thành phần bên trong group cũng có thể ảnh hưởng kết quả nếu cùng một tọa độ xuất hiện ở nhiều nơi.

## 3. Thứ tự repository trong Maven

Maven có thể tìm artifact ở local repository và nhiều remote repository. Local repository là nơi lưu artifact trên máy; remote repository được tổng hợp từ cấu hình hiệu lực của Maven, bao gồm repository khai báo trong POM và các profile đang hoạt động trong settings.xml.

Trong mô hình thông thường, Maven dùng các remote repository theo thứ tự có trong effective model. Repository khai báo ở POM, POM cha, profile và settings có thể được kết hợp; vì vậy, khi cần biết thứ tự thật, nên xem cấu hình hiệu lực thay vì chỉ đọc một đoạn POM riêng lẻ.

Ví dụ khai báo hai repository trong POM:

    <repositories>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/releases/</url>
        </repository>
        <repository>
            <id>public-proxy</id>
            <url>https://repo.example.com/maven-central/</url>
        </repository>
    </repositories>

Khai báo repository giúp Maven biết các nguồn có thể dùng để phân giải dependency. Khi cùng một artifact có mặt ở nhiều nguồn, thứ tự và metadata của repository có thể ảnh hưởng nguồn mà Maven sử dụng. Không nên dựa vào giả định rằng Maven sẽ luôn tìm ở tất cả các kho rồi chọn artifact mới nhất.

Đối với dependency SNAPSHOT, Maven còn dùng metadata và update policy để quyết định khi nào kiểm tra phiên bản triển khai mới. Thứ tự repository không thay thế cơ chế snapshot timestamp và cache.

### Xem cấu hình hiệu lực

Có thể xem effective POM:

    mvn help:effective-pom

Để lưu ra tệp:

    mvn help:effective-pom -Doutput=effective-pom.xml

Có thể xem effective settings:

    mvn help:effective-settings

Các lệnh này giúp kiểm tra repository được đưa vào mô hình hiệu lực, profile đang hoạt động và các cấu hình kế thừa. Khi điều tra lỗi, cũng cần xem settings.xml của người dùng và cấu hình mirror.

## 4. Mirror của Maven thay đổi nguồn truy cập

Maven hỗ trợ **mirror** trong settings.xml. Mirror thay thế URL repository mà Maven sẽ truy cập đối với những repository khớp quy tắc **mirrorOf**.

Ví dụ, tổ chức muốn mọi yêu cầu repository bên ngoài đi qua repository manager nội bộ:

    <settings>
        <mirrors>
            <mirror>
                <id>company-mirror</id>
                <mirrorOf>*</mirrorOf>
                <url>https://repo.example.com/all/</url>
            </mirror>
        </mirrors>
    </settings>

Với cấu hình trên, mirror khớp tất cả repository và Maven truy cập địa chỉ nội bộ thay cho từng URL gốc.

Một số mẫu mirrorOf thường gặp:

| Mẫu | Ý nghĩa |
| --- | --- |
| Ký tự đại diện * | Khớp tất cả repository. |
| external:* | Khớp các repository bên ngoài, không phải localhost hoặc file-based repository. |
| central | Khớp repository có id là central. |
| repo1,repo2 | Khớp các repository có id được liệt kê. |
| *,!internal-repo | Khớp mọi repository trừ repository có id internal-repo. |

Maven chọn một mirror phù hợp cho mỗi repository theo quy tắc matching; mirror không tự động hợp nhất nhiều mirror thành một nguồn tải. Nếu có nhiều mirror cùng khớp, thứ tự cấu hình trong settings có thể ảnh hưởng mirror được chọn. Vì vậy, cần viết quy tắc mirror rõ ràng và tránh các cấu hình chồng lấn khó dự đoán.

Mirror chỉ quyết định endpoint thay thế. Việc mirror có phục vụ release, snapshot hoặc một tập group cụ thể còn phụ thuộc cấu hình và chính sách của repository manager.

## 5. Thứ tự repository trong Gradle

Gradle cho phép khai báo nhiều repository trong build script hoặc cấu hình quản lý dependency. Với các repository được khai báo trong cùng một danh sách, thứ tự khai báo có ý nghĩa: Gradle tìm metadata của module theo thứ tự repository. Khi tìm thấy module trong một repository, Gradle gắn nguồn của module đó với repository đã tìm thấy; các artifact của module sau đó được tải từ nguồn tương ứng thay vì tùy tiện chuyển sang một repository khác.

Ví dụ:

    repositories {
        maven {
            url = uri('https://repo.example.com/releases/')
        }
        mavenCentral()
    }

Gradle sẽ xét repository nội bộ trước rồi mới đến Maven Central. Nếu module được tìm thấy trong repository đầu tiên, Gradle sử dụng metadata từ nguồn đó.

Điều này giúp tránh trường hợp metadata của một module được lấy từ một nguồn, còn artifact có cùng tọa độ lại được lấy từ nguồn khác không liên quan. Nó cũng có nghĩa thứ tự repository có thể ảnh hưởng nguồn artifact được chọn.

### Repository nội bộ trước hay Maven Central trước?

Nếu tổ chức có thư viện nội bộ, hãy đặt repository nội bộ phù hợp trước và giới hạn nội dung của nó theo group nội bộ. Sau đó mới khai báo repository công khai cho các thư viện bên ngoài.

Ví dụ:

    repositories {
        maven {
            url = uri('https://repo.example.com/releases/')
            content {
                includeGroupByRegex('com\\.company(\\..*)?')
            }
        }
        mavenCentral()
    }

Quy tắc này cho biết repository nội bộ chỉ được dùng cho các group khớp **com.company** và các group con. Các module công khai khác được tìm ở Maven Central.

Không nên đặt một repository không giới hạn nội dung trước Maven Central nếu không cần thiết. Điều đó có thể khiến repository nội bộ vô tình trở thành nguồn cung cấp một tọa độ công khai cùng tên, gây khó khăn cho việc kiểm soát nguồn và độ tin cậy.

## 6. Phạm vi nội dung repository trong Maven

Trong Maven, repository có thể bật hoặc tắt việc phân giải release và snapshot. Hai loại nội dung này có vòng đời khác nhau.

Ví dụ:

    <repositories>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/releases/</url>
            <releases>
                <enabled>true</enabled>
            </releases>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
        <repository>
            <id>company-snapshots</id>
            <url>https://repo.example.com/snapshots/</url>
            <releases>
                <enabled>false</enabled>
            </releases>
            <snapshots>
                <enabled>true</enabled>
                <updatePolicy>always</updatePolicy>
            </snapshots>
        </repository>
    </repositories>

Trong ví dụ, kho release chỉ phục vụ phiên bản phát hành, còn kho snapshot chỉ phục vụ phiên bản phát triển. Cấu hình updatePolicy **always** yêu cầu Maven kiểm tra cập nhật snapshot thường xuyên hơn.

Việc bật snapshots không có nghĩa repository tự động chứa mọi snapshot. Artifact vẫn phải được deploy vào kho và quyền truy cập phải cho phép tải.

### Phạm vi theo group hoặc module

Maven có thể sử dụng repository manager để giới hạn group, path hoặc loại artifact được phục vụ. Các chính sách đó thường được cấu hình ở phía máy chủ. Trong POM, cấu hình repository cơ bản tập trung vào URL và release/snapshot policy; không có một content filter tổng quát tương đương Gradle cho mọi group/module.

Nếu cần đảm bảo dependency nội bộ chỉ được lấy từ kho nội bộ, hãy cấu hình mirror, repository manager hoặc chính sách phía máy chủ phù hợp. Không nên xem việc khai báo URL nội bộ là đủ để bảo đảm nguồn nếu cùng tọa độ vẫn có thể được lấy từ một kho công khai khác.

## 7. Phạm vi nội dung repository trong Gradle

Gradle cung cấp content filtering để giới hạn những module mà một repository được phép cung cấp.

Ví dụ, repository nội bộ chỉ phục vụ group của công ty:

    repositories {
        maven {
            url = uri('https://repo.example.com/releases/')
            content {
                includeGroup('com.company')
                includeGroupByRegex('com\\.company\\..*')
            }
        }
        mavenCentral()
    }

Một số phương thức thường dùng:

| Phương thức | Công dụng |
| --- | --- |
| **includeGroup(group)** | Chỉ cho phép group được chỉ định. |
| **includeGroupByRegex(regex)** | Chỉ cho phép group khớp biểu thức chính quy. |
| **includeModule(group, name)** | Chỉ cho phép một module cụ thể. |
| **excludeGroup(group)** | Loại group khỏi repository. |
| **excludeModule(group, name)** | Loại module cụ thể khỏi repository. |

Có thể giới hạn theo version hoặc thuộc tính module thông qua các rule content phù hợp với Gradle version đang dùng. Hãy xem tài liệu của phiên bản Gradle trong dự án trước khi dùng API nâng cao.

### Exclusive content

Khi một nhóm module chỉ được phép đến từ repository nội bộ, Gradle có thể dùng **exclusiveContent** để ràng buộc nguồn:

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'companyRepository'
                    url = uri('https://repo.example.com/releases/')
                }
            }
            filter {
                includeGroupByRegex('com\\.company(\\..*)?')
            }
        }

        mavenCentral()
    }

Exclusive content có ý nghĩa mạnh hơn content filter thông thường: các module khớp filter được dành riêng cho repository được chỉ định, và không được tìm từ các repository khác trong tập cấu hình đó. Cách này hữu ích để tránh dependency nội bộ bị giả mạo hoặc bị thay thế bởi một module cùng tọa độ từ nguồn khác.

## 8. Repository cho dependency, plugin và buildscript

Không phải mọi repository trong cấu hình đều phục vụ cùng mục đích. Maven và Gradle có các khu vực cấu hình riêng cho thư viện ứng dụng và plugin build.

### Maven repositories và pluginRepositories

Trong POM:

- **repositories** dùng để phân giải dependency của project.
- **pluginRepositories** dùng để tìm Maven plugin.

Ví dụ:

    <pluginRepositories>
        <pluginRepository>
            <id>company-plugins</id>
            <url>https://repo.example.com/maven-plugins/</url>
        </pluginRepository>
    </pluginRepositories>

Plugin được khai báo trong phần build/plugins hoặc build/pluginManagement. Việc thêm một repository vào repositories không nhất thiết làm plugin có thể được tìm ở đó; pluginRepositories là cấu hình riêng cho mục đích này.

### Gradle pluginManagement

Gradle dùng phần **pluginManagement.repositories** trong settings.gradle hoặc settings.gradle.kts để tìm plugin được khai báo bằng plugins DSL:

    pluginManagement {
        repositories {
            gradlePluginPortal()
            maven {
                url = uri('https://repo.example.com/gradle-plugins/')
            }
        }
    }

Đây là danh sách repository dành cho plugin resolution. Nó tách biệt với repository dependency của ứng dụng.

### Gradle dependency repositories

Repository cho dependency của project thường được khai báo trong build.gradle:

    repositories {
        mavenCentral()
    }

Với cấu hình quản lý tập trung, settings.gradle có thể dùng dependencyResolutionManagement:

    dependencyResolutionManagement {
        repositories {
            mavenCentral()
        }
    }

### Gradle buildscript repositories

Các plugin hoặc thư viện được nạp qua classpath của build script cũ có thể dùng:

    buildscript {
        repositories {
            mavenCentral()
        }
        dependencies {
            classpath 'com.example:build-plugin:1.2.0'
        }
    }

Không nên nhầm buildscript.repositories với repositories của dependency ứng dụng. Nếu plugin không được tìm thấy, cần kiểm tra đúng khu vực cấu hình repository tương ứng với cách plugin được áp dụng.

## 9. Nguồn tải artifact: metadata và tệp thực tế

Khi công cụ build phân giải một dependency, nó có thể cần tải nhiều hơn một tệp:

1. Metadata của module hoặc POM để biết dependency, variant, packaging và thông tin liên quan.
2. Artifact chính, chẳng hạn JAR.
3. Các artifact bổ sung như sources JAR, javadoc JAR hoặc classifier khác.
4. Checksum hoặc signature nếu repository và công cụ hỗ trợ.

Nguồn metadata có thể ảnh hưởng cách công cụ hiểu dependency. Với Maven, POM là metadata quan trọng. Với Gradle, repository có thể cung cấp Gradle Module Metadata, Maven POM hoặc metadata theo định dạng khác được hỗ trợ.

Gradle thường ưu tiên metadata theo quy tắc lựa chọn của repository và cấu hình metadataSources. Khi một module được tìm thấy ở một repository, Gradle gắn module đó với repository nguồn đã chọn. Việc tải artifact của module tuân theo nguồn đó.

Điều này có ý nghĩa bảo mật: không nên để một repository không tin cậy cung cấp metadata cho module nội bộ, rồi kỳ vọng artifact sẽ được tải từ repository tin cậy khác. Hãy kiểm soát nguồn metadata và artifact cùng nhau.

## 10. Tải mã nguồn và tài liệu của artifact

Nhiều thư viện công bố thêm sources JAR và javadoc JAR. Những tệp này thường không cần cho việc chạy ứng dụng nhưng hữu ích khi đọc mã, debug hoặc xem API.

Ví dụ Maven repository có thể chứa:

    payment-client-3.2.1.jar
    payment-client-3.2.1-sources.jar
    payment-client-3.2.1-javadoc.jar

Trong IDE, người phát triển có thể chọn tải hoặc đính kèm sources và documentation cho dependency. IDE thường yêu cầu Maven/Gradle phân giải artifact classifier tương ứng từ repository.

Với Maven Dependency Plugin, có thể yêu cầu tải sources:

    mvn dependency:sources

Goal này yêu cầu phân giải các artifact sources mà repository đã xuất bản. Sources JAR thường được nhận diện bằng classifier **sources**, còn Javadoc JAR bằng classifier **javadoc**. Việc tải Javadoc thường được thực hiện qua tích hợp IDE hoặc bằng cách yêu cầu artifact classifier javadoc cụ thể từ repository.

Với Gradle, có thể bật tải source và Javadoc cho các dependency trong cấu hình IDE hoặc thông qua tích hợp của IDE. Không nên thêm sources JAR vào runtime classpath của ứng dụng; đó là artifact phục vụ phát triển và debug.

Nếu repository không xuất bản sources hoặc javadoc, việc yêu cầu tải các classifier đó có thể không tìm thấy artifact. Điều này không nhất thiết có nghĩa JAR chính bị thiếu.

## 11. Cấu hình xác thực và bảo vệ nguồn tải

Repository nội bộ có thể yêu cầu username, password hoặc token. Thông tin xác thực cần được giữ trong cấu hình người dùng hoặc secret store của CI.

### Maven server credentials

Trong settings.xml:

    <servers>
        <server>
            <id>company-releases</id>
            <username>build-user</username>
            <password>token-from-secret-store</password>
        </server>
    </servers>

Giá trị **id** phải khớp với id repository hoặc distributionManagement tương ứng. Không commit mật khẩu hoặc token thật trong POM.

### Gradle credentials

Ví dụ dùng biến môi trường:

    repositories {
        maven {
            url = uri('https://repo.example.com/releases/')
            credentials {
                username = System.getenv('REPO_USER')
                password = System.getenv('REPO_TOKEN')
            }
        }
    }

Trong CI, REPO_USER và REPO_TOKEN nên được cung cấp qua secret variables. Không ghi giá trị bí mật trực tiếp vào build.gradle, settings.gradle hoặc file được commit.

### HTTPS và xác minh tính toàn vẹn

Ưu tiên HTTPS cho remote repository để bảo vệ dữ liệu trong quá trình truyền. Repository manager nên áp dụng quyền đọc/ghi phù hợp và chính sách ngăn ghi đè release.

Checksum giúp phát hiện dữ liệu tải về không khớp với giá trị được công bố. Signature có thể cung cấp bằng chứng xác thực mạnh hơn nếu được quản lý và kiểm tra đúng cách. Không nên tắt xác minh chỉ để bỏ qua lỗi checksum hoặc TLS; hãy điều tra nguồn artifact, proxy, cache hoặc cấu hình chứng chỉ.

## 12. Cùng tọa độ xuất hiện ở nhiều repository

Một rủi ro quan trọng là cùng group, artifact và version xuất hiện ở nhiều repository. Nếu nguồn không được kiểm soát, build có thể lấy artifact từ một nơi khác với dự định.

Ví dụ:

    com.company:payment-client:3.2.1

có thể được lưu ở repository nội bộ, nhưng một repository công khai hoặc mirror không đáng tin cậy cũng có thể cung cấp tọa độ trùng lặp.

Với Gradle, thứ tự repository và content filter giúp kiểm soát module được tìm từ đâu. Với Maven, mirror và repository manager giúp định tuyến nguồn; chính sách phía máy chủ có thể ngăn hoặc giới hạn việc công bố tọa độ nội bộ ở nguồn không phù hợp.

Các biện pháp hữu ích:

- Dành group nội bộ cho repository nội bộ.
- Giới hạn repository nội bộ theo group hoặc module.
- Dùng exclusive content trong Gradle khi một module chỉ được phép đến từ một nguồn.
- Dùng mirror/company repository manager trong Maven để tập trung nguồn tải.
- Không cho phép ghi đè release đã phát hành.
- Lưu log hoặc thông tin dependency resolution khi cần truy vết.
- Kiểm tra checksum/signature theo chính sách của tổ chức.

Không nên dùng thứ tự repository làm cơ chế bảo mật duy nhất. Content filter, mirror, quyền truy cập và chính sách repository manager cần phối hợp với nhau.

## 13. Chẩn đoán khi artifact được tải từ nguồn không mong muốn

Khi build tải sai nguồn hoặc không tìm thấy artifact, hãy xác định:

1. Tọa độ dependency đầy đủ: group, name/artifact, version và classifier.
2. Repository nào được cấu hình trong POM, settings hoặc build script.
3. Profile Maven hoặc cấu hình Gradle nào đang hoạt động.
4. Mirror Maven có thay thế URL gốc hay không.
5. Thứ tự repository và content filter có cho phép nguồn đó cung cấp module không.
6. Metadata được lấy từ repository nào.
7. Local cache có đang giữ metadata hoặc artifact cũ không.
8. Repository có bật loại nội dung cần tìm, ví dụ release, snapshot, plugin hoặc classifier sources không.
9. Thông tin xác thực, quyền truy cập và chứng chỉ TLS có hợp lệ không.

### Lệnh hữu ích với Maven

    mvn help:effective-pom
    mvn help:effective-settings
    mvn dependency:tree
    mvn -U dependency:resolve
    mvn -X dependency:resolve

**-U** yêu cầu kiểm tra cập nhật theo quy tắc Maven; **-X** bật log debug chi tiết. Log debug có thể chứa thông tin nhạy cảm từ môi trường hoặc URL nội bộ, nên cần cẩn thận trước khi chia sẻ.

### Lệnh hữu ích với Gradle

    ./gradlew dependencies --configuration runtimeClasspath
    ./gradlew dependencyInsight --dependency payment-client --configuration runtimeClasspath
    ./gradlew build --info

Các lệnh này giúp xác định module được chọn, version và lý do phân giải. Log **--info** có thể cung cấp thêm chi tiết về hoạt động của repository và cache tùy phiên bản Gradle.

### Cache cũ

Maven và Gradle đều có cache cục bộ. Nếu artifact hoặc metadata cũ được giữ lại, kết quả có thể khác với nội dung hiện có trên remote.

Với Maven, có thể dùng **-U** để yêu cầu kiểm tra cập nhật snapshot hoặc artifact còn thiếu. Với Gradle, có thể dùng:

    ./gradlew build --refresh-dependencies

Tùy chọn này yêu cầu Gradle làm mới thông tin dependency đã cache theo cơ chế của nó. Nó không có nghĩa luôn tải lại mọi byte của mọi artifact nếu Gradle xác định nội dung vẫn hợp lệ.

Chỉ xóa cache thủ công khi đã xác định đúng artifact hoặc metadata gây lỗi. Xóa toàn bộ local repository có thể làm build tiếp theo chậm hơn và che giấu nguyên nhân cấu hình thật.

## 14. Ví dụ cấu hình tổng hợp

Giả sử tổ chức có:

- Repository release nội bộ cho group **com.company**.
- Repository snapshot nội bộ cho các version đang phát triển.
- Maven Central cho thư viện công khai.

Với Maven, có thể khai báo:

    <repositories>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/releases/</url>
            <releases>
                <enabled>true</enabled>
            </releases>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
        <repository>
            <id>company-snapshots</id>
            <url>https://repo.example.com/snapshots/</url>
            <releases>
                <enabled>false</enabled>
            </releases>
            <snapshots>
                <enabled>true</enabled>
                <updatePolicy>always</updatePolicy>
            </snapshots>
        </repository>
    </repositories>

Maven Central thường đã được khai báo qua cấu hình mặc định của Maven Super POM, nhưng tổ chức có thể thay bằng mirror trong settings.xml để mọi yêu cầu đi qua proxy nội bộ.

Với Gradle, có thể dùng:

    repositories {
        maven {
            name = 'companyReleases'
            url = uri('https://repo.example.com/releases/')
            content {
                includeGroupByRegex('com\\.company(\\..*)?')
            }
        }
        mavenCentral()
    }

Snapshot repository có thể được khai báo riêng với content filter phù hợp nếu dự án cần dependency SNAPSHOT. Trong môi trường doanh nghiệp, repository manager có thể gom release, snapshot và public proxy thành một endpoint, nhưng vẫn nên giữ chính sách nguồn rõ ràng.

## 15. Nguyên tắc thiết kế repository dễ kiểm soát

- Đặt repository nội bộ và repository công khai theo thứ tự có chủ đích.
- Giới hạn nội dung repository bằng group/module filter khi công cụ hỗ trợ.
- Dùng kho snapshot riêng cho phiên bản phát triển và kho release cho phiên bản phát hành.
- Tách repository dependency khỏi repository plugin.
- Dùng mirror hoặc repository manager để tập trung kiểm soát nguồn tải khi phù hợp.
- Không để cùng tọa độ nội bộ được cung cấp tùy tiện từ nguồn công khai.
- Dùng HTTPS và thông tin xác thực được lưu an toàn.
- Bảo vệ release khỏi bị ghi đè.
- Ghi lại nguồn và phiên bản dependency khi cần tái lập build.
- Dùng lệnh dependency tree, dependencyInsight và effective settings/POM để điều tra.

Thứ tự kho giúp quyết định nguồn nào được kiểm tra trước. Phạm vi nội dung giới hạn module hoặc loại artifact mà nguồn được phép cung cấp. Metadata và quy tắc resolution xác định artifact cụ thể được chọn, còn cache quyết định khi nào cần truy cập lại remote. Khi các phần này được cấu hình rõ ràng, build dễ dự đoán hơn và rủi ro tải nhầm artifact giảm đi.
