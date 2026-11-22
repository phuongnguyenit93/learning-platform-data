# Artifact là gì: thư viện, ứng dụng và các tệp đi kèm

Trong quy trình build Java, **artifact** là sản phẩm được tạo ra và đóng gói để một bên khác có thể sử dụng, phân phối, triển khai hoặc lưu trữ. Artifact có thể là một thư viện JAR để project khác thêm vào dependency, một executable JAR để chạy ứng dụng, một WAR để triển khai lên application server, một distribution ZIP/TAR chứa chương trình và các file cần thiết, hoặc một container image.

Vì vậy, artifact không chỉ có nghĩa là “một file JAR”. Điều quan trọng là artifact được tạo ra để phục vụ ai, được tiêu thụ theo cách nào, cần những thành phần nào đi kèm và được nhận diện bằng thông tin phiên bản nào.

Một thư viện và một ứng dụng có thể cùng được build từ Java source và cùng tạo file JAR, nhưng hợp đồng sử dụng của chúng khác nhau. Thư viện được project khác đưa vào classpath để sử dụng API. Ứng dụng được khởi chạy hoặc triển khai như một sản phẩm hoàn chỉnh. Các file đi kèm như POM, Gradle module metadata, checksum, chữ ký, source JAR, Javadoc, license, SBOM hoặc file cấu hình giúp người dùng và hệ thống phân phối hiểu, xác minh và sử dụng artifact đúng cách.

## 1. Hiểu artifact qua mục đích sử dụng

Có thể định nghĩa artifact theo ba yếu tố:

- **Nội dung:** file hoặc gói chứa code, resource, dependency, metadata hay tài liệu.
- **Danh tính:** tên, phiên bản, loại file, classifier và thông tin nguồn gốc.
- **Hợp đồng tiêu thụ:** cách người dùng hoặc hệ thống khác lấy và sử dụng sản phẩm đó.

Ví dụ:

| Artifact | Ai sử dụng? | Cách sử dụng |
|---|---|---|
| `orders-domain-1.4.0.jar` | Một Java service khác | Khai báo dependency và gọi API |
| `orders-service-1.4.0.jar` dạng executable | Runtime hoặc người vận hành | Chạy bằng `java -jar` nếu được đóng gói phù hợp |
| `orders-service-1.4.0.war` | Application server hoặc container servlet | Triển khai theo mô hình WAR |
| `orders-service-1.4.0-dist.zip` | Người cài đặt hoặc hệ thống triển khai | Giải nén và chạy script đi kèm |
| Container image | Container runtime hoặc nền tảng orchestration | Pull image rồi tạo container |
| POM hoặc Gradle module metadata | Build tool của consumer | Đọc dependency và thông tin publication |

Một artifact có thể được tạo bởi Gradle task, Maven plugin, công cụ đóng gói container hoặc một pipeline kết hợp nhiều công cụ. Artifact cuối cùng thường được đưa vào repository, registry hoặc hệ thống lưu trữ để consumer lấy về.

### 1.1. Artifact không đồng nghĩa với mọi file trong thư mục build

Thư mục `build/` có thể chứa rất nhiều file:

- Class files đã biên dịch.
- Source được sinh tự động.
- Resource đã xử lý.
- Test results và reports.
- File tạm.
- JAR hoặc WAR.
- ZIP distribution.
- Metadata phục vụ publication.

Một số file là intermediate output chỉ phục vụ task tiếp theo. Một số file là artifact cần phân phối. Một số file là báo cáo kiểm chứng. Chỉ vì một file nằm trong `build/` không có nghĩa file đó là sản phẩm được phát hành.

Cũng có artifact được tạo bên ngoài thư mục `build/`, ví dụ container image được đẩy lên registry hoặc gói được xuất bản bởi một hệ thống release. Hãy xác định artifact dựa trên task tạo ra nó và mục đích tiêu thụ, không chỉ dựa vào vị trí file.

## 2. Thư viện Java: artifact để project khác sử dụng

Một Java library cung cấp code và resource để project khác sử dụng. Consumer thường không chạy thư viện như một chương trình độc lập. Họ khai báo thư viện trong dependency configuration, build tool tải artifact và đưa nó vào compile classpath hoặc runtime classpath tùy mục đích.

Ví dụ, một project có thể khai báo:

~~~groovy
dependencies {
    implementation 'com.example:orders-domain:1.4.0'
}
~~~

Ở đây:

- `com.example` là group.
- `orders-domain` là artifact name.
- `1.4.0` là version.

Build tool tìm publication có tọa độ tương ứng trong repository được cấu hình, đọc metadata và resolve các dependency cần thiết.

### 2.1. Nội dung thường có trong library JAR

Một JAR thư viện thông thường có thể chứa:

~~~text
orders-domain-1.4.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── orders/
            ├── Order.class
            ├── OrderId.class
            └── OrderStatus.class
~~~

Ngoài class files, JAR có thể chứa:

- Resource mà thư viện cần khi chạy.
- File cấu hình mặc định hoặc schema.
- Service provider configuration trong `META-INF/services/`.
- Metadata do annotation processor hoặc framework sử dụng.
- Package metadata hoặc thông tin module Java khi dự án có cấu hình tương ứng.

Một library JAR thường không chứa tất cả dependency của nó. Dependency được mô tả qua publication metadata để consumer build tool resolve riêng. Đây là khác biệt quan trọng giữa một thư viện thông thường và một fat JAR hoặc shaded JAR.

### 2.2. API và implementation dependencies

Với Gradle Java Library plugin, có thể phân biệt dependency công khai và dependency nội bộ:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'com.example:public-types:2.0.0'
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

`api` dùng cho dependency có kiểu hoặc API xuất hiện trong public API của thư viện và cần được consumer nhìn thấy trên compile classpath theo mô hình Java Library plugin. `implementation` dành cho dependency cần để triển khai thư viện nhưng không được phơi ra như compile dependency của consumer.

Ví dụ, nếu một public method nhận kiểu `PublicType` từ dependency khác, dependency đó có thể cần khai báo bằng `api`. Nếu dependency chỉ được dùng bên trong implementation, `implementation` thường phù hợp hơn.

Khai báo đúng giúp consumer không phải nhận quá nhiều dependency compile không cần thiết, đồng thời tránh lỗi thiếu kiểu khi biên dịch code sử dụng thư viện.

### 2.3. Library cần metadata publication

Khi phát hành thư viện lên Maven-compatible repository, file JAR thường đi kèm POM. POM mô tả tọa độ và dependency để Maven hoặc các build tool khác có thể tiêu thụ publication.

Với Gradle, publication cũng có thể cung cấp Gradle Module Metadata, thường có phần mở rộng `.module`. Metadata này biểu diễn các variant và dependency theo mô hình Gradle phong phú hơn POM trong nhiều trường hợp.

Consumer không nên phải tự đoán thư viện cần dependency nào. Metadata là một phần quan trọng của hợp đồng tiêu thụ artifact.

## 3. Ứng dụng Java: artifact để chạy hoặc triển khai

Một ứng dụng Java thường được build để chạy như một chương trình hoặc triển khai vào môi trường runtime. Khác với library, consumer chính của application artifact thường là Java runtime, application server, container platform hoặc hệ thống triển khai.

Các dạng phổ biến:

- Executable JAR chứa ứng dụng và cách khởi chạy phù hợp.
- WAR triển khai lên application server hoặc servlet container.
- Distribution ZIP/TAR chứa binary, script, thư viện và file cấu hình.
- Container image chứa runtime, ứng dụng và các thành phần cần thiết theo cách đóng gói đã chọn.

### 3.1. JAR thông thường chưa chắc chạy độc lập được

Java plugin cung cấp task `jar` để đóng gói output của source set chính thành JAR. JAR này thường chứa class và resource của project, nhưng không tự động chứa toàn bộ dependency runtime.

Vì vậy, lệnh:

~~~bash
java -jar orders-service.jar
~~~

chỉ chạy được nếu JAR có cấu trúc và manifest phù hợp, đồng thời các dependency cần thiết có sẵn theo cách runtime mong đợi. Một library JAR hoặc JAR thông thường không nhất thiết có main class hay dependency bundle để chạy độc lập.

Để chạy ứng dụng, có thể dùng một trong các cách:

- Cung cấp classpath cùng dependency runtime.
- Đóng gói executable/fat JAR bằng plugin phù hợp.
- Tạo application distribution có script khởi động.
- Đóng gói ứng dụng vào container image.

### 3.2. Executable JAR và fat JAR

Executable JAR thường có thông tin entry point trong manifest, chẳng hạn `Main-Class`, hoặc một cơ chế loader do framework cung cấp. Fat JAR/uber JAR thường gộp dependency vào cùng một archive hoặc tổ chức chúng theo cấu trúc đặc biệt.

Với Spring Boot Gradle plugin, task `bootJar` tạo executable JAR theo cấu trúc loader của Spring Boot. Một cấu trúc điển hình:

~~~text
orders-service-1.4.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    └── lib/
        ├── spring-core-....jar
        └── ...
~~~

Các class của ứng dụng nằm trong `BOOT-INF/classes/`, còn dependency runtime thường nằm trong `BOOT-INF/lib/`. Đây là cấu trúc đặc thù của executable Spring Boot JAR; không nên giả định mọi JAR đều có cấu trúc này.

Có thể kiểm tra cấu trúc bằng:

~~~bash
jar tf build/libs/orders-service-1.4.0.jar
~~~

Và chạy ứng dụng nếu artifact thực sự là executable JAR:

~~~bash
java -jar build/libs/orders-service-1.4.0.jar
~~~

### 3.3. WAR và application server

WAR (Web Application Archive) là định dạng đóng gói web application thường dùng với servlet container hoặc application server. WAR có thể chứa:

- Web application classes.
- Web resources.
- Dependency library trong `WEB-INF/lib/`.
- Deployment descriptor hoặc metadata cần thiết.
- Static assets.

Ví dụ:

~~~text
orders-web.war
├── index.html
├── WEB-INF/
│   ├── classes/
│   ├── lib/
│   └── web.xml
└── ...
~~~

Cấu trúc cụ thể phụ thuộc framework và cách đóng gói. Với Gradle War plugin, task `war` tạo WAR từ source set và web application resources theo cấu hình. Cách triển khai phụ thuộc server đích và phiên bản Jakarta/Servlet API tương ứng.

WAR không giống executable JAR. Chúng có hợp đồng triển khai khác nhau, vì vậy không thể thay thế lẫn nhau chỉ bằng cách đổi phần mở rộng file.

### 3.4. Application distribution

Khi ứng dụng cần đi kèm script khởi động, thư viện, file cấu hình mẫu hoặc tài liệu cài đặt, một distribution có thể phù hợp hơn một JAR đơn lẻ.

Gradle Application plugin hỗ trợ tạo application distribution. Các task thường gặp gồm:

- `installDist`: tạo cấu trúc distribution đã cài đặt trong build output.
- `distZip`: tạo ZIP distribution.
- `distTar`: tạo TAR distribution.

Ví dụ cấu trúc:

~~~text
orders-service/
├── bin/
│   ├── orders-service
│   └── orders-service.bat
└── lib/
    ├── orders-service-1.4.0.jar
    ├── dependency-a.jar
    └── dependency-b.jar
~~~

Distribution có thể bao gồm application JAR, dependency và script khởi chạy được tạo theo cấu hình plugin. Nó hữu ích khi người dùng cần cài đặt và chạy ứng dụng mà không phải tự dựng classpath.

### 3.5. Container image

Một ứng dụng Java cũng có thể được phát hành dưới dạng container image. Image có thể chứa:

- Base operating system hoặc runtime image.
- JRE/JDK phù hợp.
- Application artifact.
- Dependency đã được đóng gói hoặc đặt trong filesystem.
- Entry point và cấu hình mặc định.

Image thường được định danh bằng tên repository và tag, hoặc digest bất biến. Ví dụ:

~~~text
registry.example.com/platform/orders-service:1.4.0
registry.example.com/platform/orders-service@sha256:...
~~~

Tag giúp con người nhận diện phiên bản nhưng có thể được di chuyển hoặc ghi đè tùy registry policy. Digest nhận diện nội dung image cụ thể. Một release nghiêm túc nên ghi lại image digest khi cần truy nguyên chính xác.

Container image là artifact ở cấp triển khai. JAR bên trong image vẫn có thể là artifact ứng dụng ở cấp Java. Một pipeline có thể quản lý cả hai lớp sản phẩm.

## 4. Các tệp đi kèm artifact

Artifact chính không phải lúc nào cũng đủ để consumer sử dụng hoặc để tổ chức phát hành sản phẩm an toàn. Nhiều file đi kèm cung cấp metadata, dependency, tài liệu, khả năng xác minh hoặc hướng dẫn vận hành.

Có thể chia file đi kèm thành các nhóm:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Publication metadata | POM, Gradle Module Metadata | Cho build tool biết tọa độ, variant và dependency |
| Documentation | README, Javadoc, changelog | Giúp consumer hiểu cách dùng và thay đổi |
| Source package | Sources JAR | Cho phép xem source tương ứng với library |
| License and notices | LICENSE, NOTICE | Thông tin điều khoản và attribution |
| Integrity and authenticity | SHA-256 checksum, signature | Kiểm tra tính toàn vẹn và xác thực nguồn |
| Software inventory | SBOM | Mô tả thành phần và dependency trong sản phẩm |
| Provenance | Build metadata, attestation | Ghi lại nguồn và quy trình tạo artifact |
| Runtime support files | Config mẫu, script, certificate bundle theo thiết kế | Hỗ trợ cài đặt và vận hành |

Không phải tất cả các file này đều phải nằm bên trong JAR. Một số file được đặt cạnh artifact trong repository; một số file được lưu trong release page; một số được cung cấp bởi registry hoặc pipeline. Cần xác định rõ file nào là một phần của publication, file nào là tài liệu hỗ trợ và file nào chỉ phục vụ kiểm chứng nội bộ.

### 4.1. POM và Gradle Module Metadata

POM XML là metadata phổ biến của Maven repository. Một POM có thể mô tả:

- Group ID, artifact ID và version.
- Packaging.
- Dependency.
- Scope của dependency.
- Thông tin project, license và developer nếu được khai báo.
- Các thông tin publication khác.

Gradle Module Metadata cung cấp mô hình variant và dependency chi tiết hơn. Ví dụ, một library có thể xuất bản các variant khác nhau cho compile và runtime, hoặc mang thuộc tính target JVM. Gradle consumer có thể dùng metadata này để chọn variant phù hợp.

Nếu một library được publish mà thiếu hoặc sai metadata, consumer có thể gặp lỗi resolve dependency, thiếu dependency bắc cầu hoặc nhận variant không phù hợp.

### 4.2. Sources JAR và Javadoc JAR

Một library có thể cung cấp thêm:

- Sources JAR chứa source code tương ứng với binary.
- Javadoc JAR chứa tài liệu API được sinh ra.

Những file này giúp IDE hiển thị source khi người dùng điều hướng vào dependency, hoặc cho phép developer đọc API documentation. Chúng không thay thế binary JAR và thường không được đưa vào runtime classpath.

Với Gradle Java plugin, có thể bật hai artifact này như sau:

~~~groovy
java {
    withSourcesJar()
    withJavadocJar()
}
~~~

Khi publication được cấu hình từ Java component, các artifact này có thể được đưa vào publication theo cấu hình plugin và component.

### 4.3. README, changelog, license và NOTICE

Tài liệu đi kèm giúp người sử dụng biết:

- Thư viện giải quyết vấn đề gì.
- Cách khai báo dependency.
- API chính và ví dụ sử dụng.
- Phiên bản Java tối thiểu.
- Các thay đổi đáng chú ý giữa các version.
- Điều khoản license và attribution cần thiết.

Với application distribution, README hoặc file hướng dẫn vận hành có thể mô tả cách cấu hình môi trường, cổng mạng, biến môi trường và cách khởi động/dừng chương trình.

License và NOTICE cần được xử lý theo nghĩa vụ của các dependency và chính sách phát hành. Không nên mặc định rằng chỉ cần đặt một file LICENSE chung là đã đáp ứng mọi yêu cầu của toàn bộ thành phần được phân phối.

### 4.4. Checksum, chữ ký và provenance

Checksum, ví dụ SHA-256, giúp phát hiện file thay đổi khi so sánh với giá trị tham chiếu đáng tin cậy:

~~~bash
sha256sum orders-service-1.4.0.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash .\orders-service-1.4.0.jar -Algorithm SHA256
~~~

Checksum không tự xác nhận ai đã tạo artifact. Nếu artifact và checksum cùng bị thay thế, chúng vẫn có thể khớp. Chữ ký số giúp xác minh artifact hoặc metadata được ký bởi một khóa tương ứng. Provenance/attestation ghi lại nguồn, quy trình hoặc môi trường đã tạo artifact theo định dạng và hệ thống được tổ chức sử dụng.

Khi phát hành phần mềm, những bằng chứng này giúp người nhận xác minh file tải về và truy nguyên build tạo ra nó.

### 4.5. SBOM

SBOM (Software Bill of Materials) là danh sách thành phần phần mềm trong một sản phẩm, thường bao gồm dependency, phiên bản và thông tin định danh liên quan. SBOM giúp tổ chức hiểu sản phẩm đang chứa những thư viện nào để phục vụ kiểm kê, đánh giá lỗ hổng và quản lý rủi ro dependency.

SBOM có thể được xuất bản kèm artifact hoặc lưu trong hệ thống release. Nó không thay thế dependency metadata dùng để resolve build; mục đích chính là mô tả thành phần của sản phẩm đã tạo ra.

## 5. Định danh artifact: tên, version, classifier và extension

Artifact cần có danh tính ổn định để consumer lấy đúng sản phẩm. Trong Maven-compatible repository, tọa độ cơ bản thường gồm:

- **groupId:** nhóm hoặc namespace của nhà phát hành.
- **artifactId:** tên module/sản phẩm.
- **version:** phiên bản phát hành.

Ví dụ:

~~~text
com.example:orders-domain:1.4.0
~~~

Một file artifact trong Maven repository thường có dạng tên:

~~~text
artifactId-version[-classifier].extension
~~~

Ví dụ:

~~~text
orders-domain-1.4.0.jar
orders-domain-1.4.0-sources.jar
orders-domain-1.4.0-javadoc.jar
orders-domain-1.4.0.pom
orders-domain-1.4.0.module
~~~

Classifier phân biệt các biến thể hoặc file phụ trợ có cùng group, artifact và version. Extension cho biết loại file, chẳng hạn `jar`, `pom`, `zip` hoặc `war`.

Không nên dùng classifier để thay thế version. `sources` và `javadoc` là những classifier phổ biến để nhận diện tài liệu/source đi kèm binary.

### 5.1. Version là một phần của danh tính sản phẩm

Version giúp consumer chọn đúng release và giúp tổ chức phân biệt các lần phát hành. Ví dụ:

- `1.4.0`: một release cụ thể.
- `1.4.1`: bản cập nhật tiếp theo.
- `2.0.0`: phiên bản có thể chứa thay đổi tương thích lớn theo chính sách versioning của dự án.
- `1.5.0-SNAPSHOT`: phiên bản phát triển chưa phải release ổn định theo quy ước Maven snapshot.

Quy tắc tăng version cần nhất quán với chính sách tương thích API và quy trình phát hành của tổ chức. Không nên chỉ thay version trong tên file mà quên metadata publication hoặc thông tin phiên bản được nhúng trong artifact.

### 5.2. Tên file không phải nguồn định danh duy nhất

Artifact có thể được đổi tên khi upload, lưu vào object storage hoặc gắn tag trong container registry. Vì vậy, cần lưu tọa độ publication hoặc digest cùng với file. Đừng chỉ dựa vào tên file để nhận diện một release.

Với Maven repository, group/artifact/version và metadata repository giúp xác định artifact. Với container registry, repository name và digest là định danh quan trọng. Với ZIP distribution, tên file thường cần chứa tên sản phẩm và version rõ ràng.

## 6. Publication của library bằng Gradle

Một library không chỉ cần tạo JAR; nó còn cần xuất bản binary và metadata để consumer resolve dependency.

Ví dụ Groovy DSL dùng Java Library và Maven Publish:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.4.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'localBuildRepository'
            url = layout.buildDirectory.dir('repo')
        }
    }
}
~~~

Cấu hình trên:

- Áp dụng Java Library plugin để tạo library component.
- Áp dụng Maven Publish plugin để tạo publication.
- Đặt group và version.
- Bật source và Javadoc artifacts.
- Tạo publication từ `components.java`.
- Cấu hình repository đầu ra trong build directory để minh họa.

Có thể chạy:

~~~bash
./gradlew publish
~~~

Gradle sẽ tạo và publish các thành phần theo cấu hình publication. Trong ví dụ, repository nằm trong build directory của project; đây là repository minh họa cho local, không phải cấu hình phát hành production.

Trong môi trường thật, repository thường là Maven repository nội bộ hoặc dịch vụ artifact repository của tổ chức. Thông tin xác thực nên được lấy từ cơ chế secret phù hợp, không hard-code trong build script hoặc commit vào Git.

### 6.1. Consumer sử dụng publication

Consumer có thể cấu hình repository và dependency:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.com/releases')
    }
}

dependencies {
    implementation 'com.example:orders-domain:1.4.0'
}
~~~

Build tool đọc metadata để resolve binary và dependency liên quan. Nếu publication có POM hoặc Gradle Module Metadata chính xác, consumer không cần tự tải từng JAR bắc cầu và ghép classpath bằng tay.

## 7. Đóng gói application bằng Gradle

Application có thể dùng Java Application plugin để tạo distribution:

~~~groovy
plugins {
    id 'application'
}

group = 'com.example'
version = '1.4.0'

application {
    mainClass = 'com.example.orders.Main'
}
~~~

Các task thường dùng:

~~~bash
./gradlew installDist
./gradlew distZip
./gradlew distTar
~~~

`installDist` tạo distribution trong build output để kiểm tra cấu trúc. `distZip` và `distTar` tạo archive để lưu trữ hoặc phân phối.

Với Spring Boot application, có thể áp dụng Spring Boot Gradle plugin và dùng task `bootJar` để tạo executable JAR. Với web application cần WAR, dùng War plugin và cấu hình theo môi trường triển khai.

Điểm chính là chọn dạng artifact theo cách ứng dụng sẽ được vận hành. Đừng chọn JAR chỉ vì đó là output quen thuộc nếu runtime thực tế cần distribution hoặc container image.

## 8. Variant và platform-specific artifacts

Một publication đôi khi có nhiều biến thể. Ví dụ:

- Variant compile và runtime của một library.
- Variant dành cho một Java version cụ thể.
- Artifact native cho Windows, Linux hoặc macOS.
- Artifact cho kiến trúc x86_64 hoặc ARM64.
- Variant dành cho Android hoặc một target platform khác.

Gradle có thể biểu diễn variant thông qua attributes và outgoing configurations. Consumer chọn variant phù hợp dựa trên thuộc tính của dependency và môi trường tiêu thụ.

Điều này khác với việc chỉ tạo nhiều file có tên khác nhau. Nếu publication cần hỗ trợ consumer chọn đúng variant tự động, metadata variant phải được khai báo chính xác. Classifier có thể phân biệt file, nhưng không thay thế toàn bộ mô hình variant selection.

Với native artifact, cần đặc biệt rõ hệ điều hành, kiến trúc, ABI và runtime dependency. Một binary build trên Linux không mặc nhiên chạy trên Windows chỉ vì cả hai file cùng thuộc một version.

## 9. Artifact chính và các file đi kèm cần được phát hành như thế nào?

Không có một quy tắc duy nhất cho mọi sản phẩm. Hãy phân loại theo người tiêu thụ:

| File | Library publication | Application release |
|---|---|---|
| Binary JAR/WAR | Bắt buộc theo publication | Thường là sản phẩm chính hoặc thành phần distribution |
| POM / `.module` | Cần cho dependency resolution theo repository | Thường không cần cho người chạy ứng dụng, trừ khi publish application component như dependency |
| Sources JAR | Hữu ích cho developer | Thường không cần |
| Javadoc JAR | Hữu ích cho consumer API | Thường không cần |
| Runtime dependencies | Metadata mô tả dependency; thường resolve riêng | Có thể đóng gói trong executable JAR, distribution hoặc image |
| README/changelog | Hữu ích cho consumer | Hữu ích cho cài đặt, nâng cấp và vận hành |
| LICENSE/NOTICE | Cần xem xét theo nghĩa vụ phát hành | Cần xem xét theo nghĩa vụ phát hành |
| Checksum/signature | Hỗ trợ xác minh file tải về | Hỗ trợ xác minh release artifact |
| SBOM/provenance | Hữu ích cho supply chain | Hữu ích cho supply chain và vận hành |

Với library, POM và Gradle Module Metadata thường rất quan trọng vì build tool của consumer cần đọc chúng. Với application, người vận hành thường cần binary/distribution, cấu hình, script, hướng dẫn triển khai và thông tin release. Không nên phát hành một tập file giống nhau cho mọi loại sản phẩm mà không xem xét cách tiêu thụ.

## 10. Artifact được tạo ra không đồng nghĩa đã sẵn sàng phát hành

Một task tạo file thành công chỉ cho biết task đó hoàn thành theo cấu hình. Trước khi phát hành, cần xác định điều kiện chấp nhận của sản phẩm:

- Artifact được tạo từ đúng source revision.
- Version và tọa độ đúng.
- Đúng loại package và target platform.
- Các test và verification cần thiết đã pass.
- Dependency metadata phù hợp.
- Các file đi kèm cần thiết đã được tạo.
- Không đưa nhầm file tạm hoặc dữ liệu nhạy cảm vào package.
- Checksum/signature/provenance được tạo nếu release policy yêu cầu.
- Artifact có thể được consumer hoặc runtime sử dụng theo hợp đồng đã công bố.

Ví dụ, một library JAR có thể tồn tại nhưng thiếu public API class cần thiết. Một executable JAR có thể được tạo nhưng thiếu cấu hình runtime bắt buộc. Một distribution ZIP có thể chứa script khởi động nhưng thiếu quyền thực thi hoặc tham chiếu đường dẫn sai. Việc kiểm tra phải phù hợp với loại artifact.

### 10.1. Kiểm tra nội dung JAR

Có thể liệt kê nội dung:

~~~bash
jar tf build/libs/orders-domain-1.4.0.jar
~~~

Kiểm tra manifest:

~~~bash
unzip -p build/libs/orders-domain-1.4.0.jar META-INF/MANIFEST.MF
~~~

Đối với library, kiểm tra package/class/resource mà consumer cần. Đối với executable Spring Boot JAR, kiểm tra cấu trúc loader và dependency. Đối với WAR, kiểm tra nội dung `WEB-INF/`. Đối với distribution ZIP, liệt kê archive và xác minh thư mục `bin/`, `lib/`, config hoặc tài liệu cần thiết.

### 10.2. Smoke test theo cách tiêu thụ thật

Một cách xác minh có giá trị là thử tiêu thụ artifact theo đúng cách người dùng cuối sẽ làm:

- Library: tạo một consumer sample hoặc test fixture, khai báo dependency từ repository và biên dịch code sử dụng API.
- Executable JAR: chạy bằng lệnh khởi động dự kiến trong môi trường thử nghiệm.
- WAR: triển khai vào application server/container tương thích.
- Distribution: giải nén vào thư mục mới và chạy script trong môi trường sạch.
- Container image: pull image theo digest và chạy với cấu hình môi trường dự kiến.

Smoke test không thay thế test suite, nhưng giúp phát hiện lỗi đóng gói hoặc thiếu file mà unit test nội bộ không nhìn thấy.

## 11. Những lỗi thường gặp khi định nghĩa artifact

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Nhầm library JAR với executable JAR | Consumer không chạy được file hoặc thiếu dependency | Xác định rõ loại sản phẩm và task packaging |
| Thiếu POM hoặc module metadata | Consumer không resolve dependency đúng | Publish component và metadata theo cấu hình chuẩn |
| Dùng sai group/artifact/version | Consumer tải nhầm sản phẩm hoặc version | Quản lý tọa độ thống nhất |
| Chỉ đổi tên file để biểu diễn version mới | Metadata bên trong hoặc repository không khớp | Cập nhật project version và publication metadata |
| Thiếu dependency runtime trong distribution | Ứng dụng lỗi khi khởi chạy | Kiểm tra classpath hoặc cấu trúc distribution |
| Đưa nhầm test report vào package runtime | Package phình to hoặc lộ thông tin không cần thiết | Phân biệt output và release artifact |
| Bỏ quên license/NOTICE | Thiếu thông tin tuân thủ khi phân phối | Quản lý file pháp lý theo dependency và policy |
| Chỉ phát hành checksum mà không có nguồn tin cậy | Không xác minh được tính xác thực | Kết hợp chữ ký hoặc provenance phù hợp |
| Dùng tag container có thể ghi đè mà không lưu digest | Khó xác định chính xác image đã triển khai | Lưu digest trong release metadata |

## 12. Ví dụ tổng hợp: cùng một mã nguồn, hai loại artifact

Giả sử repository có hai project:

~~~text
commerce-platform/
├── orders-domain/
│   └── src/main/java/
└── orders-service/
    └── src/main/java/
~~~

`orders-domain` là library chứa model và nghiệp vụ dùng chung. `orders-service` là application sử dụng library đó.

Library có thể tạo publication:

~~~text
com.example:orders-domain:1.4.0
├── orders-domain-1.4.0.jar
├── orders-domain-1.4.0.pom
├── orders-domain-1.4.0.module
├── orders-domain-1.4.0-sources.jar
└── orders-domain-1.4.0-javadoc.jar
~~~

Application có thể tạo executable artifact:

~~~text
orders-service-1.4.0.jar
orders-service-1.4.0.jar.sha256
orders-service-1.4.0-sbom.json
orders-service-1.4.0-provenance.json
~~~

Nếu ứng dụng được phát hành dưới dạng distribution, tập file có thể là:

~~~text
orders-service-1.4.0-dist.zip
├── bin/
├── lib/
├── conf/
├── README.md
└── LICENSE
~~~

Library publication được consumer build tool resolve như dependency. Application artifact được runtime hoặc nền tảng triển khai sử dụng. Các file đi kèm hỗ trợ dependency resolution, tài liệu, xác minh và vận hành.

Dù hai project dùng chung một version, mỗi artifact vẫn cần danh tính riêng. Việc version đồng bộ hay độc lập phụ thuộc chính sách release của repository.

## 13. Quy tắc đặt tên và tổ chức release

Tên artifact nên giúp người nhận hiểu ngay sản phẩm, version và biến thể. Một số nguyên tắc:

- Dùng tên artifact ổn định, nhất quán với module hoặc sản phẩm.
- Dùng version theo chính sách của dự án.
- Dùng classifier cho source, Javadoc hoặc biến thể file khi phù hợp.
- Dùng extension đúng với loại package.
- Tránh tên chung như `final.jar`, `latest.jar` hoặc `output.zip` trong kho release dài hạn.
- Ghi lại tọa độ repository hoặc digest bên cạnh file.
- Không ghi đè release bất biến nếu repository policy yêu cầu version duy nhất.
- Tách snapshot/development publication khỏi release repository.

Với container image, tag có thể thân thiện với con người, nhưng digest giúp nhận diện nội dung cụ thể. Với Maven publication, tọa độ GAV là định danh chính. Với distribution ZIP, tên file thường cần có tên sản phẩm và version rõ ràng.

## 14. Checklist xác định artifact trước khi phát hành

Trước khi chuyển sản phẩm sang consumer hoặc môi trường triển khai, hãy xác nhận:

- [ ] Đã xác định đây là library, application hay distribution.
- [ ] Đã chọn đúng task tạo artifact.
- [ ] Binary chứa đúng class và resource cần thiết.
- [ ] Dependency được đóng gói hoặc mô tả đúng theo mô hình tiêu thụ.
- [ ] Tọa độ group, artifact và version chính xác.
- [ ] Classifier và extension phản ánh đúng biến thể.
- [ ] POM/Gradle Module Metadata có mặt khi publication cần chúng.
- [ ] Sources, Javadoc, README, changelog, LICENSE hoặc NOTICE đã được cung cấp khi cần.
- [ ] Runtime config và script đi kèm đúng với cách triển khai.
- [ ] Test và verification cần thiết đã hoàn tất.
- [ ] Checksum, signature, SBOM hoặc provenance được tạo theo release policy.
- [ ] Artifact đã được thử tiêu thụ hoặc khởi chạy theo cách người dùng cuối sẽ sử dụng.
- [ ] Release metadata lưu lại source revision và định danh artifact.

## Kết luận

Artifact là sản phẩm build được đóng gói để một consumer cụ thể sử dụng. Với Java library, artifact thường là JAR cùng metadata dependency và các file hỗ trợ developer. Với application, artifact có thể là executable JAR, WAR, distribution hoặc container image cùng cấu hình và tài liệu vận hành. Các file đi kèm như POM, Gradle Module Metadata, Sources/Javadoc, license, checksum, signature, SBOM và provenance bổ sung thông tin cần thiết cho việc tiêu thụ, phân phối và xác minh.

Khi xác định artifact, hãy bắt đầu từ mục đích sử dụng và hợp đồng với consumer. Từ đó chọn định dạng, task đóng gói, version, metadata và các file đi kèm phù hợp. Một file được tạo thành công mới chỉ là đầu ra của build; một artifact có thể phát hành cần có danh tính rõ ràng, nội dung đúng và đủ thông tin để người nhận sử dụng cũng như xác minh nó.
