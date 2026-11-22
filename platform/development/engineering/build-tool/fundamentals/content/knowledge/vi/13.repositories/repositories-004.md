# Metadata POM và vai trò trong phân giải phụ thuộc bắc cầu

Khi Gradle lấy một thư viện từ Maven repository, nó cần biết nhiều thông tin hơn tên tệp JAR. Nó phải xác định module đó là gì, phiên bản nào được phát hành, dependency nào đi kèm, dependency nào chỉ dùng trong một phạm vi nhất định và những quy tắc nào ảnh hưởng đến việc phân giải.

Một nguồn thông tin phổ biến là tệp **POM** (Project Object Model) theo định dạng Maven. POM là metadata XML mô tả một artifact và các quan hệ của nó với những artifact khác. Gradle có thể đọc POM từ Maven repository để biết các dependency bắc cầu cần được xem xét khi tạo classpath cho compile, runtime hoặc test.

Hiểu POM giúp giải thích vì sao chỉ khai báo một thư viện trong build script nhưng Gradle lại tải thêm nhiều JAR, vì sao một dependency có trong runtime mà không có trong compile classpath, và vì sao một dependency được đánh dấu optional hoặc bị exclude có thể không xuất hiện trong graph.

## 1. POM là gì?

POM là tệp XML mô tả một Maven project hoặc artifact. Với một thư viện đã phát hành, POM thường được lưu cùng JAR trong Maven repository.

Một artifact có thể có tọa độ:

~~~text
groupId:artifactId:version
~~~

Ví dụ:

~~~text
org.apache.commons:commons-lang3:3.14.0
~~~

Trong đó:

- **groupId:** nhóm phát hành artifact.
- **artifactId:** tên artifact.
- **version:** phiên bản artifact.

Trong repository Maven, các thành phần thường được sắp xếp theo group, artifact và version:

~~~text
repository/
└── org/
    └── apache/
        └── commons/
            └── commons-lang3/
                └── 3.14.0/
                    ├── commons-lang3-3.14.0.pom
                    └── commons-lang3-3.14.0.jar
~~~

Tệp **commons-lang3-3.14.0.pom** mô tả metadata của phiên bản 3.14.0. Tệp **commons-lang3-3.14.0.jar** chứa bytecode và tài nguyên của thư viện.

POM không phải chính thư viện và cũng không phải tệp JAR. Nó là dữ liệu để công cụ build hiểu cách sử dụng artifact và những module mà artifact cần.

## 2. Cấu trúc cơ bản của một POM

Một POM đơn giản có thể trông như sau:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>report-client</artifactId>
    <version>2.1.0</version>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>json-core</artifactId>
            <version>1.5.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Các thành phần chính:

- **modelVersion:** phiên bản mô hình POM; với Maven POM thông dụng hiện nay thường là **4.0.0**.
- **groupId:** nhóm phát hành artifact.
- **artifactId:** tên artifact.
- **version:** phiên bản artifact.
- **packaging:** loại artifact được đóng gói, ví dụ **jar** hoặc **pom**.
- **dependencies:** các dependency mà project khai báo.

Phần **dependencies** đặc biệt quan trọng đối với phân giải phụ thuộc bắc cầu. Khi ứng dụng khai báo **report-client:2.1.0**, Gradle đọc metadata của report-client. Nếu POM cho biết nó phụ thuộc vào **json-core:1.5.0**, Gradle có thể thêm json-core vào graph phù hợp.

Ví dụ khai báo trong Gradle Kotlin DSL:

~~~kotlin
repositories {
    mavenCentral()
}

dependencies {
    implementation("com.example:report-client:2.1.0")
}
~~~

Nếu repository cung cấp POM hợp lệ, Gradle có thể dùng metadata đó để tìm các dependency của report-client mà không cần người viết build script khai báo từng JAR.

## 3. POM mô tả dependency bắc cầu như thế nào?

Một dependency trong POM thường được khai báo bằng các trường:

- **groupId**
- **artifactId**
- **version**
- **scope**
- **optional**
- **exclusions**

Ví dụ:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>json-core</artifactId>
        <version>1.5.0</version>
    </dependency>

    <dependency>
        <groupId>org.example</groupId>
        <artifactId>logging-api</artifactId>
        <version>2.0.0</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Giả sử ứng dụng dùng report-client. Khi Gradle phân giải report-client, nó đọc hai khai báo trên và xem xét các module tương ứng theo scope. json-core có thể tham gia compile và runtime classpath; logging-api được khai báo với scope runtime nên được dùng cho runtime nhưng không phải compile classpath thông thường của dependency đó.

Đồ thị khái quát:

~~~text
Ứng dụng
└── report-client
    ├── json-core       (compile)
    └── logging-api    (runtime)
~~~

POM vì thế đóng vai trò như bản mô tả các quan hệ dependency được phát hành cùng artifact. Nó cho Gradle biết thư viện cần những module nào để hoạt động, và thông tin scope giúp xác định các module đó phù hợp với classpath nào.

## 4. Maven scopes và cách Gradle diễn giải

Maven dùng **scope** để mô tả phạm vi sử dụng của dependency. Khi Gradle đọc Maven POM, nó phải ánh xạ scope sang các configuration hoặc variant của Gradle.

Các scope phổ biến:

| Maven scope | Ý nghĩa trong Maven | Cách hiểu khi Gradle đọc POM |
|---|---|---|
| **compile** | Có sẵn cho compile, test và runtime của Maven project | Thường tham gia compile và runtime classpath của consumer |
| **runtime** | Cần khi chạy và kiểm thử, không cần cho compile mã nguồn chính của project khai báo | Chủ yếu tham gia runtime classpath; không phải compile classpath chính |
| **provided** | Cần để biên dịch và kiểm thử nhưng môi trường chạy dự kiến cung cấp | Có semantics riêng; thường không phải dependency runtime thông thường của consumer |
| **test** | Chỉ dùng trong quá trình test của chính project khai báo | Không được truyền như dependency thông thường sang consumer |
| **system** | Dùng artifact từ đường dẫn cục bộ thay vì repository | Không phù hợp với mô hình repository dependency thông thường và có hạn chế khi tiêu thụ qua POM |
| **import** | Dùng trong dependencyManagement để nhập BOM | Dùng để nhập dependency constraints từ BOM, không phải một thư viện runtime thông thường |

Cách ánh xạ chi tiết có thể phụ thuộc phiên bản Gradle, metadata và loại configuration đang được phân giải. Không nên suy ra rằng tên Maven scope và tên Gradle configuration là một-một giống nhau.

### compile

Đây là scope mặc định nếu POM không chỉ định scope. Dependency compile thường cần cho việc biên dịch và chạy ứng dụng.

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>json-core</artifactId>
    <version>1.5.0</version>
    <scope>compile</scope>
</dependency>
~~~

Nếu report-client cần các kiểu dữ liệu của json-core trong API công khai, compile scope thường là lựa chọn phù hợp trong POM của report-client.

### runtime

Dependency runtime cần có khi chạy nhưng không nhất thiết cần để biên dịch mã nguồn chính của module khai báo nó.

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>logging-impl</artifactId>
    <version>2.0.0</version>
    <scope>runtime</scope>
</dependency>
~~~

Ví dụ, một thư viện có thể sử dụng logging implementation thông qua cơ chế nạp provider lúc chạy. Consumer cần implementation trên runtime classpath nhưng không cần import API implementation đó trong mã nguồn compile của mình.

### provided

Trong Maven, provided thường biểu thị dependency cần trong compile/test nhưng dự kiến sẽ được môi trường chạy cung cấp, ví dụ một API do application server cung cấp.

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

Khi tiêu thụ POM từ Gradle, cần hiểu rằng scope provided có semantics riêng. Nó không tương đương đơn giản với một dependency implementation thông thường. Hãy kiểm tra compile và runtime classpath thực tế nếu dự án phụ thuộc vào API do container cung cấp.

### test

Dependency test chỉ dành cho kiểm thử của project phát hành POM. Consumer thông thường không nhận dependency test đó như dependency bắc cầu.

~~~xml
<dependency>
    <groupId>junit</groupId>
    <artifactId>junit</artifactId>
    <version>4.13.2</version>
    <scope>test</scope>
</dependency>
~~~

Điều này giúp thư viện không bắt mọi ứng dụng sử dụng nó phải kéo thêm framework kiểm thử của chính thư viện.

## 5. Optional dependency

POM có thể đánh dấu dependency là **optional**:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>xml-adapter</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
~~~

Optional dependency thường có nghĩa là module phát hành có thể sử dụng tính năng bổ sung đó, nhưng không muốn bắt mọi consumer đều nhận dependency này một cách bắc cầu.

Ví dụ, report-client hỗ trợ JSON và XML. Phần xử lý XML có thể cần xml-adapter, nhưng ứng dụng chỉ dùng JSON. Nhà phát hành có thể đánh dấu xml-adapter là optional để consumer tự quyết định có cần thêm nó hay không.

Khi Gradle đọc POM, optional dependency không được truyền bắc cầu đến consumer theo cách dependency thông thường. Nếu ứng dụng cần tính năng XML, ứng dụng có thể phải khai báo dependency tương ứng trực tiếp:

~~~kotlin
dependencies {
    implementation("com.example:report-client:2.1.0")
    implementation("org.example:xml-adapter:1.2.0")
}
~~~

Không nên hiểu optional là dependency không bao giờ được dùng. Nó có thể cần thiết cho một tính năng cụ thể; trách nhiệm chọn dependency được chuyển sang consumer.

## 6. Exclusions trong POM

POM cho phép một dependency loại trừ dependency bắc cầu khác thông qua phần **exclusions**.

Ví dụ:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>report-client</artifactId>
    <version>2.1.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>legacy-adapter</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Khi Gradle đọc POM này, quy tắc exclusion là một phần metadata của dependency report-client. Nó tác động đến nhánh mà report-client đưa vào graph.

Nếu một module khác cũng yêu cầu **legacy-adapter**, module đó vẫn có thể xuất hiện trong dependency graph. Exclusion không nhất thiết xóa module khỏi mọi đường dependency.

Trong Gradle build script, có thể khai báo exclusion tương tự:

~~~kotlin
dependencies {
    implementation("com.example:report-client:2.1.0") {
        exclude(
            group = "org.example",
            module = "legacy-adapter"
        )
    }
}
~~~

POM exclusion và Gradle exclude đều cần được hiểu trong bối cảnh dependency graph. Nếu module vẫn xuất hiện sau khi exclude, hãy tìm các đường dependency khác thay vì cho rằng metadata bị bỏ qua.

## 7. dependencyManagement: quản lý phiên bản không đồng nghĩa thêm dependency

POM có phần **dependencyManagement** để định nghĩa version hoặc các thuộc tính quản lý dependency cho những khai báo dependency khác trong phạm vi quản lý.

Ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>json-core</artifactId>
            <version>1.5.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đoạn này quản lý phiên bản của json-core. Nó không có nghĩa json-core tự động trở thành dependency của project chỉ vì xuất hiện trong dependencyManagement.

Một dependency thực tế có thể tham chiếu đến version đã được quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>json-core</artifactId>
    </dependency>
</dependencies>
~~~

Khi Maven xây dựng model, dependencyManagement có thể cung cấp version còn thiếu cho dependency khai báo trong dependencies. Khi Gradle tiêu thụ POM, thông tin dependency management được diễn giải như metadata hoặc constraint theo cơ chế hỗ trợ của Gradle.

Cần phân biệt:

| Phần POM | Vai trò |
|---|---|
| **dependencies** | Khai báo dependency mà project cần |
| **dependencyManagement** | Quản lý version và thuộc tính dependency cho các khai báo có liên quan |
| **exclusions** | Loại dependency bắc cầu khỏi một nhánh dependency |
| **properties** | Định nghĩa giá trị có thể được tham chiếu trong POM |
| **profiles** | Điều chỉnh model Maven theo điều kiện kích hoạt |

Không nên đọc dependencyManagement rồi kết luận mọi module trong đó đều được tải xuống. Chỉ những dependency thực sự được đưa vào graph mới cần được phân giải.

## 8. BOM và scope import

Một BOM (Bill of Materials) là POM được dùng để quản lý tập trung phiên bản của nhiều dependency có liên quan. BOM thường khai báo các dependency trong dependencyManagement.

Ví dụ POM consumer:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>2026.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau khi import BOM, project có thể khai báo dependency mà không cần lặp lại version nếu BOM đã quản lý version đó:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>example-client</artifactId>
    </dependency>
</dependencies>
~~~

Trong Gradle Kotlin DSL, có thể dùng platform:

~~~kotlin
dependencies {
    implementation(platform("com.example:example-bom:2026.1"))
    implementation("com.example:example-client")
}
~~~

Nếu muốn các constraint của platform được áp dụng nghiêm ngặt hơn theo semantics của Gradle, có thể dùng **enforcedPlatform**:

~~~kotlin
dependencies {
    implementation(enforcedPlatform("com.example:example-bom:2026.1"))
    implementation("com.example:example-client")
}
~~~

Cần thận trọng với enforced platform vì các version constraints của nó có thể ảnh hưởng mạnh đến các consumer hoặc dependency khác. Với thư viện được phát hành để nhiều ứng dụng sử dụng, platform thông thường thường dễ kết hợp hơn; chỉ chọn enforced platform khi chính sách version thực sự cần ép buộc.

## 9. Properties và parent POM

POM có thể sử dụng properties để tránh lặp lại version string:

~~~xml
<properties>
    <json-core.version>1.5.0</json-core.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>json-core</artifactId>
        <version>${json-core.version}</version>
    </dependency>
</dependencies>
~~~

Khi đọc POM, cần hiểu rằng version có thể không được viết trực tiếp trong thẻ version mà được tham chiếu qua property.

POM cũng có thể kế thừa từ **parent POM**:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>5.0.0</version>
</parent>
~~~

Parent có thể cung cấp properties, dependency management và một số cấu hình được kế thừa. Maven xây dựng effective POM từ POM hiện tại kết hợp với parent và các cấu hình liên quan.

Khi điều tra metadata của một artifact, đừng chỉ nhìn vài dòng dependency trong POM con rồi kết luận đó là toàn bộ model. Version hoặc dependency management có thể đến từ parent POM hoặc BOM được import.

## 10. Maven profiles và giới hạn khi tiêu thụ POM

Maven POM hỗ trợ **profiles** để thay đổi model theo điều kiện kích hoạt như property, JDK hoặc môi trường. Ví dụ, một profile có thể thêm dependency cho một môi trường nhất định.

Tuy nhiên, khi một công cụ khác như Gradle tiêu thụ Maven POM từ repository, không nên giả định nó sẽ kích hoạt và xử lý mọi Maven profile giống hệt một lần chạy Maven trong project gốc. Metadata được publish thường cần biểu diễn dependency một cách ổn định cho consumer.

Nếu dependency chỉ xuất hiện khi một profile Maven được kích hoạt ở dự án phát hành, hãy kiểm tra POM thực tế được publish và metadata mà Gradle đọc. Không suy ra dependency graph từ một lệnh Maven chạy trong source project nếu artifact được consumer lấy từ repository có metadata khác.

## 11. Gradle tìm và đọc POM từ repository như thế nào?

Gradle cần biết repository nào có thể chứa artifact:

~~~kotlin
repositories {
    mavenCentral()

    maven {
        url = uri("https://repo.example.com/releases")
    }
}
~~~

Khi khai báo:

~~~kotlin
dependencies {
    implementation("com.example:report-client:2.1.0")
}
~~~

Gradle tìm module theo group, artifact và version trong các repository đã cấu hình. Với Maven repository, đường dẫn thường được tạo từ group ID (chuyển dấu chấm thành thư mục), artifact ID và version.

Với tọa độ ví dụ, Gradle có thể tìm:

~~~text
com/example/report-client/2.1.0/report-client-2.1.0.pom
com/example/report-client/2.1.0/report-client-2.1.0.jar
~~~

POM cung cấp metadata để Gradle hiểu dependency và các quy tắc liên quan. JAR cung cấp nội dung binary mà ứng dụng sử dụng.

Nếu POM không tồn tại, sai tọa độ hoặc repository không có phiên bản được yêu cầu, Gradle có thể báo lỗi không tìm thấy module hoặc không phân giải được dependency.

## 12. POM và Gradle Module Metadata

POM là định dạng metadata Maven phổ biến, nhưng Gradle còn hỗ trợ định dạng riêng gọi là **Gradle Module Metadata** (tệp **.module**).

Hai định dạng có khả năng biểu diễn thông tin khác nhau:

| Đặc điểm | Maven POM | Gradle Module Metadata |
|---|---|---|
| Định dạng | XML | JSON |
| Mô hình chính | Maven project, dependency và scope | Module, variant, attribute, capability và dependency |
| Phạm vi compile/runtime | Biểu diễn qua scope | Có thể biểu diễn variant rõ ràng |
| Variant theo thuộc tính | Hạn chế | Hỗ trợ trực tiếp |
| Dữ liệu Gradle đặc thù | Không phải mục tiêu chính | Biểu diễn được nhiều semantics riêng của Gradle |

Một module được publish bằng Gradle có thể có cả POM và **.module**. Khi repository và metadata được cấu hình theo mặc định, Gradle ưu tiên Gradle Module Metadata nếu tìm thấy metadata đó; POM là nguồn metadata quan trọng khi **.module** không có hoặc không được sử dụng theo cấu hình.

Điều này có nghĩa cùng một tọa độ module có thể được Gradle diễn giải từ **.module** thay vì POM. Nếu dependency graph không giống điều bạn dự đoán từ POM, hãy kiểm tra nguồn metadata thực tế mà Gradle sử dụng.

Có thể cấu hình nguồn metadata cho Maven repository:

~~~kotlin
repositories {
    maven {
        url = uri("https://repo.example.com/releases")

        metadataSources {
            gradleMetadata()
            mavenPom()
            artifact()
        }
    }
}
~~~

Cấu hình trên thể hiện các nguồn metadata có thể được Gradle xem xét. Thứ tự và lựa chọn nguồn metadata ảnh hưởng cách Gradle lấy thông tin module. Không nên bỏ qua Gradle Module Metadata khi điều tra một thư viện được publish bởi Gradle.

### Vì sao POM không biểu diễn được mọi variant của Gradle?

POM tập trung vào Maven scopes và mô hình dependency của Maven. Gradle có thể cần nhiều biến thể của cùng module, ví dụ API variant và runtime variant, hoặc artifact dành cho các thuộc tính nền tảng khác nhau.

Gradle Module Metadata mô tả variant và attributes chi tiết hơn. Khi chỉ có POM, Gradle phải chuyển thông tin Maven sang mô hình configuration/variant mà nó hỗ trợ. Vì vậy, một số khác biệt về variant hoặc semantics đặc thù của Gradle có thể không được biểu diễn đầy đủ trong POM.

## 13. Chẩn đoán dependency graph được tạo từ POM

Khi một thư viện kéo theo dependency ngoài dự kiến, hãy xem graph thực tế của configuration cần điều tra.

Xem runtime classpath:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Xem compile classpath:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
~~~

Tìm đường dẫn của một module cụ thể:

~~~bash
./gradlew :app:dependencyInsight --dependency json-core --configuration runtimeClasspath
~~~

Các lệnh này giúp xác định:

- Module nào đang được yêu cầu.
- Dependency trực tiếp hoặc bắc cầu nào đưa module vào graph.
- Phiên bản nào được chọn sau conflict resolution.
- Dependency có bị exclude hoặc bị ảnh hưởng bởi constraint hay không.
- Module xuất hiện trong compile, runtime hay test configuration.

Nếu muốn biết POM đang được tải về từ đâu, có thể chạy với log chi tiết hơn:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath --info
~~~

Khi cần, kiểm tra cache Gradle hoặc mở artifact metadata trong repository nội bộ theo đúng tọa độ module. Hãy xác định POM hoặc **.module** tương ứng với đúng phiên bản đang phân giải.

## 14. Những lỗi thường gặp khi POM ảnh hưởng đến phân giải

| Biểu hiện | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Không tìm thấy module | Sai group/artifact/version hoặc repository không chứa artifact | Kiểm tra tọa độ, repository và đường dẫn POM/JAR |
| Thiếu lớp khi compile | Dependency chỉ có scope runtime, optional hoặc không được đưa vào compile graph | Kiểm tra scope trong POM và compileClasspath |
| Thiếu lớp khi runtime | POM không khai báo dependency cần thiết, dependency bị exclude hoặc metadata publish thiếu | Xem runtimeClasspath và dependencyInsight |
| Phiên bản khác với POM mong đợi | Có conflict, dependencyManagement, BOM hoặc constraint | Dùng dependencyInsight để xem lý do chọn version |
| Dependency không xuất hiện | Optional, test scope, exclusion hoặc metadata source khác | Mở POM và kiểm tra .module nếu có |
| Khác biệt giữa Maven và Gradle | Hai công cụ có semantics và quy tắc phân giải khác nhau; metadata hoặc variant có thể khác | So sánh effective POM, metadata publish và Gradle graph |
| Module vẫn xuất hiện sau exclude | Có đường dependency khác vẫn yêu cầu module | Xem tất cả đường dẫn bằng dependencyInsight |

## 15. Quy trình đọc POM khi một dependency được thêm vào dự án

Giả sử ứng dụng khai báo **com.example:report-client:2.1.0** và bất ngờ có thêm JAR **org.example:logging-api**.

Có thể điều tra theo trình tự:

1. Xác nhận tọa độ dependency trực tiếp trong build script.
2. Xác định repository và metadata source được Gradle dùng.
3. Mở POM của report-client đúng phiên bản 2.1.0.
4. Tìm phần dependencies, kiểm tra groupId, artifactId, version, scope, optional và exclusions.
5. Nếu POM dùng property hoặc parent, xác định giá trị và metadata được kế thừa.
6. Nếu có BOM hoặc dependencyManagement, xem nó quản lý phiên bản nào và dependency nào thực sự được khai báo.
7. Chạy dependencyInsight cho logging-api để xác nhận đường dependency và phiên bản cuối cùng.
8. So sánh compileClasspath và runtimeClasspath để hiểu scope.
9. Nếu graph khác POM, kiểm tra Gradle Module Metadata và repository metadata configuration.
10. Nếu cần thay đổi, quyết định giữa exclude, dependency constraint, platform hoặc cập nhật metadata do nhà phát hành cung cấp.

Ví dụ, nếu POM có:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>logging-api</artifactId>
    <version>2.0.0</version>
    <scope>runtime</scope>
</dependency>
~~~

thì việc logging-api xuất hiện trong runtime classpath có thể là hành vi đúng. Không nên loại bỏ chỉ vì nó không xuất hiện trong compile classpath. Hãy kiểm tra report-client có cần provider này khi chạy hay không.

## 16. Những nguyên tắc cần nhớ

- POM là metadata XML mô tả artifact và các dependency mà artifact khai báo.
- Gradle đọc POM trong Maven repository để xác định dependency bắc cầu, scope, optional và exclusions.
- Maven scope ảnh hưởng configuration/classpath mà dependency tham gia; compile, runtime, provided và test có ý nghĩa khác nhau.
- Optional dependency thường không được truyền bắc cầu đến consumer; consumer cần tự khai báo nếu dùng tính năng đó.
- Exclusion trong POM tác động đến nhánh dependency liên quan; module vẫn có thể xuất hiện qua một đường khác.
- dependencyManagement quản lý version và thuộc tính, không tự động thêm tất cả module vào dependency graph.
- BOM với scope import giúp quản lý phiên bản tập trung; trong Gradle có thể tiêu thụ qua platform.
- Properties và parent POM có thể cung cấp version hoặc dependency management không hiển thị trực tiếp trong một khai báo dependency.
- Gradle Module Metadata có thể cung cấp variant và semantics phong phú hơn POM; hãy kiểm tra nguồn metadata thực tế.
- Dùng **dependencies** và **dependencyInsight** để truy nguyên dependency graph thay vì chỉ suy đoán từ build script.
- Khi nghi ngờ metadata publish sai, kiểm tra đúng POM và **.module** của đúng phiên bản trong repository.

POM là cầu nối giữa artifact được publish và dependency graph mà Gradle xây dựng. Đọc được metadata này giúp giải thích nguồn gốc của dependency bắc cầu, hiểu vì sao một module tham gia compile hoặc runtime classpath, và lựa chọn cách xử lý phù hợp khi graph không đúng với nhu cầu của ứng dụng.
