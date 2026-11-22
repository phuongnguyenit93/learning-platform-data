# Từ khai báo phụ thuộc đến đồ thị thư viện thực tế

Trong một dự án Java, build script thường chỉ khai báo một số thư viện trực tiếp. Khi Gradle chuẩn bị biên dịch hoặc chạy ứng dụng, nó có thể cần hàng chục hoặc hàng trăm module khác: dependency bắc cầu của thư viện, các phiên bản được chọn sau khi giải quyết xung đột, những biến thể dành cho compile/runtime và các thành phần do platform hoặc plugin bổ sung.

Vì vậy, danh sách dependency trong build script không phải lúc nào cũng giống danh sách thư viện cuối cùng mà một task sử dụng. **Đồ thị phụ thuộc (dependency graph)** là mô hình Gradle tạo ra cho một configuration cụ thể sau khi đi theo các khai báo trực tiếp và bắc cầu, đọc metadata, áp dụng quy tắc chọn phiên bản và chọn variant phù hợp.

Hiểu quá trình này giúp trả lời những câu hỏi thường gặp:

- Vì sao khai báo một thư viện nhưng Gradle tải thêm nhiều thư viện khác?
- Vì sao hai thư viện cùng yêu cầu một module ở hai phiên bản khác nhau?
- Vì sao compile classpath và runtime classpath không giống nhau?
- Vì sao thay đổi một dependency trong build script chưa chắc làm version thực tế thay đổi như mong đợi?
- Làm thế nào biết thư viện nào đã được chọn và ai đưa nó vào graph?

## 1. Khai báo dependency mới là điểm bắt đầu

Một khai báo dependency thường cho Gradle biết project muốn sử dụng một module nào và trong phạm vi nào. Ví dụ với Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.google.guava:guava:33.3.1-jre'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
~~~

Ở đây, project khai báo hai dependency trực tiếp:

- Guava được dùng trong code chính thông qua configuration implementation.
- JUnit Jupiter được dùng trong code kiểm thử thông qua configuration testImplementation.

Khai báo này chưa liệt kê tất cả module sẽ có mặt trên classpath. Guava có thể phụ thuộc vào module khác; JUnit cũng có thể kéo theo những module hỗ trợ. Gradle cần đọc metadata của các module để tìm các dependency bắc cầu đó.

Có thể hình dung luồng tổng quát:

~~~mermaid
flowchart TD
    A["Khai báo trong dependencies {}"] --> B["Configuration được tiêu thụ"]
    B --> C["Đọc dependency metadata"]
    C --> D["Đi theo dependency trực tiếp và bắc cầu"]
    D --> E["Giải quyết phiên bản và constraint"]
    E --> F["Chọn variant phù hợp"]
    F --> G["Dependency graph đã resolve"]
    G --> H["Tải artifact cần thiết"]
    H --> I["Task dùng compile/runtime classpath"]
~~~

Một điểm quan trọng: đồ thị được giải quyết cho từng configuration. Không có một danh sách duy nhất đại diện cho mọi task của project. Compile, runtime, test và các configuration tùy chỉnh có thể có graph khác nhau.

## 2. Đọc tọa độ dependency

Với Maven-compatible repository, dạng khai báo phổ biến là:

~~~text
group:name:version
~~~

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Ba thành phần có ý nghĩa:

| Thành phần | Giá trị ví dụ | Ý nghĩa |
|---|---|---|
| Group | org.apache.commons | Namespace hoặc tổ chức phát hành |
| Name/module | commons-lang3 | Tên module |
| Version | 3.17.0 | Phiên bản được yêu cầu |

Tọa độ này thường tương ứng với một module trong repository. Gradle dùng repository đã cấu hình để tìm metadata và artifact.

Dependency cũng có thể trỏ đến project khác trong cùng build:

~~~groovy
dependencies {
    implementation project(':shared-library')
}
~~~

Đây là project dependency. Thay vì tải một module từ Maven repository, Gradle liên kết project hiện tại với component được cung cấp bởi project shared-library. Quan hệ này cũng tham gia vào graph và task graph, để Gradle biết output của project phụ thuộc cần được tạo trước khi consumer sử dụng.

Ngoài module dependency và project dependency, Gradle còn hỗ trợ file dependency, dependency từ included build, platform và các dạng dependency khác. Mỗi loại có cách nhận diện và metadata khác nhau.

## 3. Configuration quyết định dependency được dùng ở đâu

Một dependency declaration luôn nằm trong một configuration. Configuration xác định mục đích sử dụng và các dependency nào được đưa vào classpath tương ứng.

Với Java plugin, một số configuration thường gặp:

| Configuration | Mục đích |
|---|---|
| implementation | Dependency cần cho code chính và runtime của project |
| compileOnly | Cần khi biên dịch nhưng không được đưa vào runtime classpath của project theo configuration này |
| runtimeOnly | Cần khi chạy nhưng không cần để biên dịch source chính |
| testImplementation | Dependency dùng khi biên dịch và chạy test |
| testRuntimeOnly | Dependency chỉ cần khi chạy test |
| annotationProcessor | Processor dùng trong quá trình biên dịch source chính |
| testAnnotationProcessor | Processor dùng khi biên dịch test source |

Java Library plugin bổ sung configuration api, dùng cho dependency thuộc public API và cần được consumer nhìn thấy trên compile classpath của họ.

Ví dụ:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'com.example:public-model:2.0.0'
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    runtimeOnly 'org.postgresql:postgresql:42.7.4'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
~~~

api và implementation không đơn giản là hai cách viết khác nhau. Chúng biểu đạt hợp đồng của library với consumer:

- api: kiểu hoặc thành phần của dependency xuất hiện trong public API và consumer cần dependency đó để biên dịch.
- implementation: dependency phục vụ nội bộ implementation; consumer không cần nhận nó như compile dependency công khai.

Với một application không phát hành public library API cho consumer khác, implementation là configuration thường dùng cho dependency chính.

### 3.1. Compile classpath và runtime classpath

Một project Java có nhiều classpath. Ví dụ, compileClasspath phục vụ biên dịch source chính, còn runtimeClasspath phục vụ chạy ứng dụng.

Một cách khái quát:

- compileClasspath gồm các dependency cần cho compile, bao gồm implementation và compileOnly cùng những thành phần API được kế thừa phù hợp.
- runtimeClasspath gồm dependency cần lúc chạy, như implementation và runtimeOnly, cộng các dependency bắc cầu cần thiết.
- testCompileClasspath và testRuntimeClasspath có thêm dependency dành cho test và output của source set chính.

Vì vậy, một thư viện được khai báo bằng compileOnly có thể xuất hiện khi biên dịch nhưng không có trên runtime classpath. Nếu ứng dụng cần thư viện đó lúc chạy mà không có nguồn cung cấp khác, có thể gặp ClassNotFoundException hoặc NoClassDefFoundError.

Ví dụ một annotation API chỉ cần compiler có thể phù hợp với compileOnly; JDBC driver thường được khai báo bằng runtimeOnly nếu code không cần kiểu của driver khi biên dịch.

### 3.2. Dependency declaration và configuration có thể kế thừa nhau

Configuration có thể kế thừa dependency từ configuration khác. Ví dụ, test configuration của Java plugin được thiết kế để sử dụng output và dependency phù hợp của source set chính. Các configuration cũng có thể được plugin tạo và nối với nhau.

Do đó, không nên nhìn riêng block dependencies rồi tự cộng các dòng để suy ra classpath. Hãy xem graph của configuration cụ thể mà task sử dụng.

## 4. Dependency trực tiếp và dependency bắc cầu

**Dependency trực tiếp (direct dependency)** là dependency được project khai báo trực tiếp trong build logic.

**Dependency bắc cầu (transitive dependency)** là dependency được một dependency khác yêu cầu trong metadata của nó, hoặc được kéo vào thông qua các quan hệ dependency tiếp theo.

Giả sử project có graph như sau:

~~~text
orders-service
└── library-a:1.0
    ├── common-core:2.1
    │   └── logging-api:1.5
    └── json-support:3.0
        └── common-core:2.0
~~~

Project chỉ khai báo library-a:1.0, nhưng Gradle phải xem xét cả common-core, logging-api và json-support. common-core xuất hiện qua hai đường đi và có hai version request khác nhau. Gradle cần giải quyết xung đột để xác định version được chọn trong configuration đó.

Dependency bắc cầu giúp consumer không phải khai báo thủ công mọi thư viện mà dependency trực tiếp cần. Nhưng nó cũng khiến graph thực tế lớn hơn danh sách khai báo trong build script.

### 4.1. Một module có thể được yêu cầu qua nhiều đường

Ví dụ:

~~~text
application
├── library-a:1.0
│   └── commons-io:2.11.0
└── library-b:2.0
    └── commons-io:2.15.1
~~~

Hai dependency trực tiếp cùng yêu cầu module commons-io, nhưng version khác nhau. Gradle phải áp dụng quy tắc resolution để chọn một version phù hợp cho configuration.

Trong graph đã resolve, cùng một component/version thường được chia sẻ thay vì tải hai bản độc lập chỉ vì nó xuất hiện trên hai đường. Tuy nhiên, graph có thể chứa nhiều version của cùng module trong những trường hợp resolution rules, capabilities hoặc cấu hình đặc biệt cho phép điều đó; không nên giả định mọi graph đều chỉ có một version cho mọi module.

### 4.2. Dependency graph không phải chỉ là danh sách JAR

Graph thể hiện quan hệ giữa các component và những yêu cầu dependency. Một component có thể có nhiều variant hoặc artifact. Một variant có thể cung cấp nhiều artifact; một artifact có thể là JAR, ZIP hoặc loại file khác.

Vì vậy cần phân biệt:

- **Component/module:** sản phẩm được nhận diện bằng tọa độ hoặc project identity.
- **Dependency edge:** yêu cầu từ component này sang component khác.
- **Variant:** cách component được cung cấp cho một mục đích sử dụng cụ thể.
- **Artifact:** file vật lý được tải hoặc lấy từ output của project.

Graph resolution chọn component và variant phù hợp trước khi task lấy artifact cần thiết.

## 5. Gradle biến khai báo thành graph như thế nào?

Có thể chia quá trình thành các bước khái quát:

1. Task hoặc build logic yêu cầu một configuration, chẳng hạn runtimeClasspath.
2. Gradle đọc các dependency trực tiếp được khai báo trong configuration đó và những configuration mà nó kế thừa.
3. Gradle tìm metadata của từng module từ repository hoặc project tương ứng.
4. Metadata cho biết dependency bắc cầu, variant, constraint và artifact được cung cấp.
5. Gradle mở rộng graph bằng cách đi theo những dependency được yêu cầu.
6. Gradle giải quyết xung đột phiên bản, áp dụng constraint, platform và resolution rule.
7. Gradle chọn variant phù hợp với attributes của consumer.
8. Khi task cần file vật lý, Gradle lấy các artifact thuộc variant đã chọn và đưa chúng vào classpath hoặc đầu vào task.

Đây là mô tả khái niệm; các bước nội bộ có thể được tối ưu và không nhất thiết xảy ra tuần tự theo một lượt đơn giản. Một số metadata hoặc artifact có thể đã có trong cache, còn một số configuration chưa cần resolve trong invocation hiện tại.

### 5.1. Metadata đến từ đâu?

Gradle có thể đọc metadata từ:

- Gradle Module Metadata (.module).
- Maven POM (.pom).
- Ivy metadata.
- Metadata của project dependency hoặc component được cung cấp bởi plugin/build logic.

Metadata cho Gradle biết module yêu cầu dependency nào, variant nào tồn tại, thuộc tính của variant và artifact tương ứng. Gradle Module Metadata có thể biểu diễn mô hình variant phong phú hơn POM Maven. Nếu repository cung cấp cả hai, Gradle có thể ưu tiên metadata Gradle khi được công bố theo cơ chế tương ứng.

Nếu metadata sai hoặc không đầy đủ, graph có thể thiếu dependency, chọn variant không phù hợp hoặc khiến consumer nhận classpath khác kỳ vọng.

## 6. Giải quyết xung đột phiên bản

Một xung đột xảy ra khi graph có nhiều yêu cầu phiên bản cho cùng một module. Ví dụ:

~~~text
orders-service
├── library-a:1.0
│   └── jackson-databind:2.15.0
└── library-b:2.0
    └── jackson-databind:2.17.1
~~~

Với quy tắc mặc định thông thường của Gradle, khi cùng một module được yêu cầu ở nhiều version, Gradle chọn version cao hơn theo quy tắc so sánh version của nó. Vì vậy, trong ví dụ đơn giản trên, jackson-databind:2.17.1 thường được chọn cho configuration đó.

Đây là quy tắc resolution mặc định, không phải lời khẳng định rằng version cao nhất luôn tương thích với mọi thư viện. Nâng version có thể làm thay đổi hành vi hoặc gây lỗi tương thích. Nhóm cần kiểm tra test và constraint của hệ sinh thái đang sử dụng.

### 6.1. Vì sao không nên chỉ nhìn version khai báo trực tiếp?

Giả sử build script ghi:

~~~groovy
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.15.0'
}
~~~

Nhưng một dependency khác yêu cầu 2.17.1. Graph đã resolve có thể chọn 2.17.1 theo quy tắc mặc định. Dòng khai báo trực tiếp thể hiện version request, không nhất thiết là version cuối cùng được sử dụng.

Để biết version được chọn, hãy kiểm tra graph hoặc dùng task dependencyInsight, thay vì suy luận từ build script.

### 6.2. Rich version constraints

Gradle hỗ trợ version constraint phong phú hơn một chuỗi version đơn giản. Ví dụ:

~~~groovy
dependencies {
    implementation('com.example:shared-core') {
        version {
            strictly '2.4.0'
        }
    }
}
~~~

Các khái niệm thường gặp:

- require: yêu cầu một version hoặc phạm vi version theo constraint.
- strictly: giới hạn version được phép; nếu không thể thỏa constraint, resolution có thể thất bại.
- prefer: thể hiện version ưu tiên khi có thể.
- reject: loại trừ những version không được chấp nhận.

Ví dụ khai báo prefer:

~~~groovy
dependencies {
    implementation('com.example:shared-core') {
        version {
            prefer '2.4.0'
        }
    }
}
~~~

prefer không phải một khóa cứng. Một constraint mạnh hơn hoặc yêu cầu khác trong graph có thể dẫn đến lựa chọn khác. Nếu muốn giới hạn nghiêm ngặt, cần dùng cơ chế constraint phù hợp và hiểu ảnh hưởng tới các consumer.

### 6.3. Dependency constraints

Dependency constraint cho biết version nào nên hoặc phải được dùng nếu module đó xuất hiện trong graph. Constraint không tự thêm module vào graph.

Ví dụ:

~~~groovy
dependencies {
    implementation 'com.example:orders-client:1.0.0'

    constraints {
        implementation('com.example:shared-core:2.4.0') {
            because 'Các module trong ứng dụng cần cùng dòng shared-core'
        }
    }
}
~~~

Nếu shared-core được kéo vào qua dependency bắc cầu, constraint có thể ảnh hưởng version được chọn. Nếu không có đường dependency nào đưa module vào graph, constraint đơn thuần không làm module xuất hiện.

Điều này khác với việc khai báo dependency trực tiếp.

### 6.4. Force và resolution strategy

Gradle có thể ép version bằng resolution strategy:

~~~groovy
configurations.configureEach {
    resolutionStrategy {
        force 'com.example:shared-core:2.4.0'
    }
}
~~~

force là công cụ mạnh và có thể hữu ích khi cần áp dụng một version thống nhất trong phạm vi đã xác định. Nhưng nó có thể ghi đè ý định từ metadata hoặc constraint khác, nên dễ che khuất nguyên nhân của xung đột.

Ưu tiên dùng dependency constraints, platform/BOM hoặc version catalog kết hợp với quy tắc rõ ràng khi có thể. Nếu dùng force, hãy giới hạn phạm vi và ghi lý do.

## 7. Platform và BOM giúp đồng bộ nhiều dependency

Một số thư viện được phát hành theo một bộ version tương thích. Ví dụ, hệ sinh thái có nhiều module liên quan và nhà cung cấp công bố BOM (Bill of Materials) để đề xuất các version tương thích.

Với Gradle, có thể import platform:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
~~~

Platform cung cấp dependency constraints cho các module thuộc bộ version đó. Nhờ vậy, project không cần ghi version riêng cho từng starter trong ví dụ.

platform(...) nhập các constraints theo cơ chế platform thông thường. enforcedPlatform(...) áp dụng constraints có tính cưỡng chế mạnh hơn cho consumer resolution; cần dùng cẩn thận vì nó có thể truyền ảnh hưởng tới những project tiêu thụ component đã công bố.

### 7.1. BOM không nhất thiết thêm mọi module vào graph

BOM chủ yếu quản lý version. Nếu BOM liệt kê một trăm module nhưng project chỉ khai báo ba module, không có nghĩa cả một trăm module đều được tải. Những module không được yêu cầu qua dependency edge sẽ không tự xuất hiện chỉ vì chúng có version trong BOM.

### 7.2. Version catalog khác platform

Version catalog (libs.versions.toml) giúp tập trung alias, version và plugin declaration để build script dễ đọc hơn.

Ví dụ:

~~~toml
[versions]
junit = "5.11.0"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
~~~

Sử dụng trong build script:

~~~kotlin
dependencies {
    testImplementation(libs.junit.jupiter)
}
~~~

Version catalog giúp quản lý khai báo ở cấp build. Nó không tự thay thế dependency graph resolution và cũng không phải lockfile. Version cuối cùng vẫn chịu ảnh hưởng của dependency bắc cầu, constraints, platforms và resolution rules.

## 8. Chọn variant: cùng module nhưng khác cách cung cấp

Một module có thể cung cấp nhiều variant cho các mục đích khác nhau. Ví dụ, Java library có thể công bố variant cho compile và runtime. Một variant có thể chứa API cần cho compile; variant khác cung cấp runtime dependencies.

Gradle dùng attributes để so sánh yêu cầu của consumer với variant mà producer cung cấp. Một số attribute phổ biến liên quan tới:

- Usage: java-api hoặc java-runtime.
- Category: library, platform hoặc documentation.
- Target JVM version.
- Library elements như JAR hoặc classes.
- Bundling hoặc cách đóng gói.

Ví dụ, compileClasspath cần variant phù hợp cho compile, còn runtimeClasspath cần variant phù hợp cho runtime. Cùng một tọa độ module có thể được chọn ở các variant khác nhau tùy configuration.

Nếu producer không công bố variant phù hợp, Gradle có thể báo lỗi không tìm thấy variant tương thích. Đây không nhất thiết là lỗi “không tìm thấy version”; module có thể tồn tại nhưng không có variant đáp ứng attributes của consumer.

### 8.1. Capability conflict

Một số component có thể cung cấp cùng một capability, tức là cùng tuyên bố cung cấp một chức năng hoặc API. Nếu graph kéo vào hai provider không thể cùng tồn tại, Gradle có thể báo capability conflict.

Ví dụ, hai implementation khác nhau của cùng một logging backend có thể cùng cung cấp capability tương tự. Chỉ thêm dependency hoặc loại bỏ version conflict không giải quyết đúng vấn đề; cần chọn provider mong muốn bằng dependency metadata hoặc resolution rule thích hợp.

### 8.2. Platform-specific variants

Với native library hoặc plugin có nhiều target, variant có thể khác theo OS, architecture hoặc ABI. Consumer cần khai báo hoặc cung cấp attributes phù hợp để Gradle chọn đúng variant. Nếu không có variant phù hợp, việc tải một artifact cùng tên nhưng build cho nền tảng khác có thể dẫn đến lỗi khi chạy.

## 9. Exclude và dependency substitution

### 9.1. Exclude dependency bắc cầu

Nếu một dependency kéo vào một module không mong muốn, Gradle hỗ trợ exclude trên dependency edge:

~~~groovy
dependencies {
    implementation('com.example:legacy-client:1.2.0') {
        exclude group: 'commons-logging', module: 'commons-logging'
    }
}
~~~

Exclude này loại module khỏi nhánh dependency cụ thể. Nếu một dependency khác vẫn kéo commons-logging vào graph qua đường khác, module vẫn có thể xuất hiện.

Do đó, exclude không phải lệnh “xóa module khỏi toàn bộ build” trong mọi trường hợp. Hãy kiểm tra graph sau khi áp dụng và xác định đường nào vẫn đưa module vào.

Không nên exclude chỉ vì muốn graph ngắn hơn. Nếu thư viện thực sự cần dependency đó lúc runtime, việc loại bỏ có thể gây lỗi khi chạy.

### 9.2. Dependency substitution

Dependency substitution cho phép thay một dependency bằng một component khác. Ví dụ, trong quá trình phát triển, có thể thay module external bằng project local:

~~~groovy
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('com.example:shared-core') using project(':shared-core')
    }
}
~~~

Điều này hữu ích trong multi-project build hoặc khi phát triển nhiều module liên quan cùng lúc. Gradle có thể dùng project output thay cho module đã publish.

Substitution thay đổi component được chọn trong graph. Vì vậy, nó có thể làm thay đổi task graph, nguồn artifact và cách version được xác định. Cần kiểm tra đúng project path và tránh để rule chỉ dành cho local development vô tình ảnh hưởng publication hoặc CI.

## 10. Repository ảnh hưởng đến việc tìm metadata và artifact

Gradle cần repository để tìm module external. Ví dụ:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.example.com/releases')
    }
}
~~~

Khi resolve dependency, Gradle tìm metadata của module trong các repository đã cấu hình. Metadata có thể dẫn tới artifact binary và dependency bắc cầu.

Một số lưu ý:

- Repository phải được khai báo ở phạm vi phù hợp với dependency đang resolve.
- Plugin repository và dependency repository là hai phạm vi cấu hình khác nhau.
- Private repository có thể yêu cầu thông tin xác thực.
- Không nên khai báo repository không tin cậy chỉ để làm cho một dependency resolve được.
- Cùng tọa độ module nhưng metadata khác nhau giữa repository có thể tạo ra kết quả khó dự đoán; nên quản lý nguồn phát hành nhất quán.

Gradle có cơ chế gắn module đã tìm thấy với repository tương ứng để tránh tùy tiện trộn metadata và artifact của cùng module từ nhiều repository. Vì vậy, thứ tự và nội dung repository configuration là một phần của kiểm soát dependency.

## 11. Quan sát graph thực tế bằng Gradle

Không cần đoán dependency graph từ build script. Gradle cung cấp task để hiển thị graph theo configuration.

### 11.1. Xem toàn bộ dependency của configuration

Ví dụ xem runtime graph:

~~~bash
./gradlew :orders-service:dependencies --configuration runtimeClasspath
~~~

Xem compile graph:

~~~bash
./gradlew :orders-service:dependencies --configuration compileClasspath
~~~

Kết quả cho biết dependency trực tiếp, dependency bắc cầu và version được chọn trong configuration tương ứng. Output có thể chứa ký hiệu thể hiện version conflict hoặc trạng thái dependency.

Nếu project có test source set, có thể xem:

~~~bash
./gradlew :orders-service:dependencies --configuration testRuntimeClasspath
~~~

Hãy chọn configuration đúng với câu hỏi đang điều tra. Xem runtimeClasspath không trả lời đầy đủ điều gì có trên testCompileClasspath.

### 11.2. Tìm vì sao một version được chọn

Task dependencyInsight giúp truy nguyên một module:

~~~bash
./gradlew :orders-service:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Thông tin có thể cho biết:

- Module nào đang được xem xét.
- Version nào được chọn.
- Các version request khác.
- Đường dependency nào đưa module vào graph.
- Constraint hoặc rule nào ảnh hưởng kết quả.
- Lý do Gradle chọn version đó.

Đây thường là lệnh hữu ích nhất khi một dependency xuất hiện ở version khác với version ghi trong build script.

### 11.3. Xem dependency của project và build logic

Nếu dependency đến từ project khác, hãy xem dependency graph của project consumer và project producer. Nếu dependency đến từ plugin, cần phân biệt plugin classpath với dependency configuration của ứng dụng. Plugin dependency không tự động có nghĩa nó nằm trên runtime classpath của application.

## 12. Ví dụ xuyên suốt: từ hai khai báo tới graph đã resolve

Giả sử project orders-service khai báo:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.example:orders-client:1.0.0'
    implementation 'com.example:reporting-core:2.0.0'
}
~~~

Metadata của các module minh họa các dependency:

~~~text
orders-service
├── orders-client:1.0.0
│   ├── shared-core:2.1.0
│   └── jackson-databind:2.15.0
└── reporting-core:2.0.0
    ├── shared-core:2.3.0
    └── jackson-databind:2.17.1
~~~

Gradle mở rộng graph và phát hiện:

- shared-core được yêu cầu ở 2.1.0 và 2.3.0.
- jackson-databind được yêu cầu ở 2.15.0 và 2.17.1.

Với resolution mặc định và không có constraint/rule khác, Gradle thường chọn version cao hơn cho từng module:

~~~text
orders-service
├── orders-client:1.0.0
│   ├── shared-core:2.3.0 (selected)
│   └── jackson-databind:2.17.1 (selected)
└── reporting-core:2.0.0
    ├── shared-core:2.3.0 (selected)
    └── jackson-databind:2.17.1 (selected)
~~~

Đây là graph minh họa sau khi resolution. Hai đường dependency vẫn được giữ trong quan hệ graph, nhưng cùng tham chiếu tới component version đã chọn. Gradle sau đó chọn variant phù hợp cho compileClasspath hoặc runtimeClasspath và lấy artifact tương ứng khi task cần.

Nếu orders-client chỉ tương thích với shared-core:2.1.0, việc chọn 2.3.0 có thể gây lỗi tương thích. Nhóm có thể cần nâng orders-client, dùng platform/constraint phù hợp, hoặc xử lý version theo chính sách tương thích của thư viện. Ép version thấp hơn mà không kiểm tra sẽ chỉ chuyển lỗi sang một dạng khác.

## 13. Tính ổn định của dependency graph

Một graph có thể thay đổi theo thời gian nếu build dùng dynamic version, changing module hoặc metadata từ repository thay đổi.

Ví dụ:

~~~groovy
dependencies {
    implementation 'com.example:shared-core:2.+'
}
~~~

Khai báo 2.+ yêu cầu một version phù hợp trong dòng 2. Khi repository có version mới, graph có thể chọn version khác ở lần resolve sau, tùy cache và trạng thái repository.

Các dạng như latest.release hoặc snapshot cũng có thể làm kết quả thay đổi. Chúng có ích trong một số quy trình phát triển, nhưng làm giảm tính ổn định nếu dùng trong build phát hành mà không có cơ chế kiểm soát.

### 13.1. Dependency locking

Dependency locking lưu lại version đã được resolve cho những configuration được khóa. Ví dụ cấu hình:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó, project cần resolve configuration và tạo/cập nhật lock state theo workflow đã thống nhất. Lockfile được quản lý trong source control để các lần build tiếp theo dùng cùng các version đã khóa, trừ khi lock state được cập nhật có chủ đích.

Locking giúp kiểm soát version graph. Nó không tự xác minh nội dung file tải về và cũng không thay thế metadata hoặc repository policy.

### 13.2. Dependency verification

Dependency verification cho phép xác minh checksum hoặc chữ ký của artifact được tải về. Nó giúp phát hiện artifact thay đổi ngoài dự kiến hoặc không khớp với metadata xác minh được quản lý.

Locking trả lời câu hỏi “version nào được chọn?”. Verification trả lời câu hỏi “artifact tải về có khớp với bằng chứng tin cậy đã cấu hình không?”. Hai cơ chế bổ sung cho nhau.

### 13.3. Version catalog không phải lockfile

Version catalog giúp quản lý alias và version request tập trung. Dependency locking ghi lại version được resolve. Dependency verification kiểm tra nội dung artifact. Ba cơ chế có mục đích khác nhau:

| Cơ chế | Kiểm soát điều gì? |
|---|---|
| Version catalog | Cách khai báo dependency và version trong build |
| Dependency constraints/platform | Quy tắc version trong graph |
| Dependency locking | Version đã resolve cho configuration |
| Dependency verification | Tính toàn vẹn/xác thực artifact tải về |

Một dự án có thể dùng đồng thời cả bốn để kiểm soát dependency rõ ràng hơn.

## 14. Những lỗi thường gặp khi đọc graph

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Version thực tế khác version khai báo trực tiếp | Dependency khác yêu cầu version cao hơn hoặc constraint tác động | Dùng dependencyInsight |
| Runtime thiếu class | Dependency chỉ có trên compile classpath hoặc bị exclude | So sánh compileClasspath và runtimeClasspath |
| Dependency xuất hiện dù không khai báo trực tiếp | Được kéo vào qua dependency bắc cầu hoặc plugin/configuration khác | Xem đường đi trong dependencies |
| Hai configuration cho kết quả khác nhau | Mỗi configuration có graph và attributes riêng | Xem từng configuration cụ thể |
| Không tìm thấy variant tương thích | Attributes của consumer không khớp variant producer | Xem thông báo variant và metadata |
| Resolve thất bại do version strict | Các constraint không thể cùng thỏa mãn | Kiểm tra constraint và dependencyInsight |
| Exclude không loại được module | Một đường dependency khác vẫn đưa module vào graph | Xem tất cả đường đi trong graph |
| Build local và CI resolve khác nhau | Repository, dynamic version, lock state hoặc metadata khác nhau | So sánh repository và dependency locks |
| Dependency được khai báo nhưng không tải ngay | Configuration chưa được task tiêu thụ hoặc artifact chưa cần | Xác định task và configuration được resolve |

Không nên sửa lỗi graph bằng cách thêm version hoặc exclude ngẫu nhiên. Trước tiên hãy tìm đường dependency đưa module vào, version request và quy tắc resolution đang áp dụng.

## 15. Quy trình điều tra một dependency không mong muốn

Khi phát hiện một thư viện hoặc version không mong đợi, có thể làm theo trình tự:

1. **Xác định task và configuration.** Ví dụ lỗi xuất hiện khi chạy ứng dụng thì bắt đầu với runtimeClasspath; lỗi compile thì xem compileClasspath.
2. **Liệt kê graph.** Chạy dependencies cho configuration đó để thấy các đường dependency.
3. **Truy nguyên module.** Dùng dependencyInsight với tên module để biết version request và lý do chọn.
4. **Xem metadata.** Kiểm tra POM hoặc Gradle Module Metadata của module liên quan để hiểu dependency bắc cầu và variant.
5. **Kiểm tra constraints/platform.** Tìm BOM, version constraints, rich versions, resolution strategy hoặc dependency substitution.
6. **Chọn cách sửa phù hợp.** Nâng dependency cha, cập nhật platform, thêm constraint có lý do hoặc loại dependency không cần thiết nếu an toàn.
7. **Xác minh lại graph.** Chạy lại dependencies và dependencyInsight để xác nhận version/variant đúng.
8. **Chạy kiểm chứng liên quan.** Compile, test và smoke test để xác nhận thay đổi không phá tương thích.

Nếu cần build ổn định giữa local và CI, cập nhật lock state và dependency verification theo quy trình của dự án.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Các dòng trong dependencies block là toàn bộ thư viện được dùng | Chúng chỉ là khai báo trực tiếp; metadata có thể kéo thêm dependency bắc cầu |
| Mỗi dependency luôn có đúng một version request | Một module có thể được yêu cầu qua nhiều đường với nhiều version |
| Version ghi trong build script luôn là version cuối | Resolution có thể chọn version khác theo conflict và constraint |
| implementation và runtimeOnly giống nhau | Một bên tham gia compile và runtime; bên kia chỉ dành cho runtime |
| BOM tự tải mọi thư viện trong danh sách | BOM cung cấp constraints; module chỉ vào graph khi được yêu cầu |
| Version catalog khóa graph | Catalog giúp khai báo; lockfile kiểm soát version đã resolve |
| Exclude trên một dependency loại module khỏi toàn build | Đường khác vẫn có thể kéo module vào graph |
| Cùng tọa độ luôn có cùng variant | Variant được chọn theo attributes của consumer |
| Dependency graph chính là task graph | Dependency graph mô tả component/module; task graph mô tả công việc cần thực thi |
| Có JAR trong cache nghĩa là dependency đang được sử dụng | Cần xem graph của configuration được task tiêu thụ |

## 17. Checklist đọc và kiểm soát dependency graph

Khi cần hiểu thư viện thực tế của một project, hãy xác định:

- [ ] Dependency được khai báo trực tiếp ở configuration nào?
- [ ] Task đang sử dụng configuration nào?
- [ ] Graph có những dependency bắc cầu nào?
- [ ] Có module nào được yêu cầu qua nhiều đường không?
- [ ] Version nào được chọn và vì sao?
- [ ] Có platform/BOM hoặc dependency constraint ảnh hưởng không?
- [ ] Variant có phù hợp với compile/runtime và target platform không?
- [ ] Có exclude, substitution, force hoặc resolution rule nào không?
- [ ] Repository và metadata nguồn có nhất quán không?
- [ ] Dependency locking có được dùng cho build cần tính ổn định không?
- [ ] Dependency verification có kiểm tra artifact tải về không?
- [ ] Sau khi thay đổi graph, compile/test/smoke test đã xác nhận hành vi chưa?

## Kết luận

Khai báo dependency trong build script chỉ mô tả những module mà project yêu cầu trực tiếp và configuration sử dụng chúng. Gradle đọc metadata, mở rộng dependency bắc cầu, giải quyết version conflict và constraint, chọn variant theo nhu cầu của consumer, rồi cung cấp artifact cần thiết cho compile hoặc runtime classpath. Kết quả là một dependency graph cụ thể cho từng configuration.

Muốn biết thư viện nào thực sự được sử dụng, hãy xem graph thay vì chỉ đọc block dependencies. Task dependencies cho thấy các đường phụ thuộc; dependencyInsight giải thích version được chọn và lý do. Kết hợp configuration phù hợp, platform/constraints, dependency locking và verification sẽ giúp graph dễ hiểu, ổn định và có thể truy nguyên hơn.
