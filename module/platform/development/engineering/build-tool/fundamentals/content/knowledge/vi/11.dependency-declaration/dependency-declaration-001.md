# Phụ thuộc trực tiếp và phụ thuộc bắc cầu

Một ứng dụng Java thường khai báo một số thư viện để sử dụng trực tiếp, chẳng hạn thư viện logging, JSON hoặc một framework. Tuy nhiên, mỗi thư viện đó có thể cần thêm các thư viện khác để hoạt động. Build tool phải giải quyết toàn bộ mạng lưới này để tạo classpath phù hợp cho biên dịch, kiểm thử và chạy ứng dụng.

Hai khái niệm quan trọng khi đọc dependency graph là **phụ thuộc trực tiếp (direct dependency)** và **phụ thuộc bắc cầu (transitive dependency)**. Phân biệt chúng giúp ta biết thư viện nào do project chủ động yêu cầu, thư viện nào được kéo vào thông qua một thư viện khác, vì sao một phiên bản xuất hiện và nên khai báo hoặc loại trừ dependency ở đâu.

## 1. Phụ thuộc trực tiếp là gì?

Phụ thuộc trực tiếp là một thành phần được project khai báo rõ ràng trong cấu hình build. Project cần thành phần đó để sử dụng API, thực hiện một công việc hoặc chạy một chức năng.

Ví dụ, một ứng dụng sử dụng SLF4J để ghi log và Jackson để đọc JSON. Với Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.13'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

Hai dòng trong khối `dependencies` là hai dependency trực tiếp của project. Chúng được nhận diện bằng tọa độ `group:artifact:version`:

- `org.slf4j` là group, `slf4j-api` là artifact, `2.0.13` là version.
- `com.fasterxml.jackson.core` là group, `jackson-databind` là artifact, `2.17.2` là version.

Project trực tiếp sử dụng API của hai thư viện này, vì vậy nó chủ động khai báo chúng. Build tool dùng khai báo đó để tìm artifact trong repository và giải quyết các thành phần cần thiết khác.

Phụ thuộc trực tiếp có thể là thư viện Maven/Ivy, một project khác trong cùng Gradle build, một platform/BOM, file dependency hoặc thành phần được cung cấp bởi plugin. Trong bài này, ví dụ chủ yếu dùng thư viện bên ngoài được phân phối qua repository.

## 2. Phụ thuộc bắc cầu là gì?

Một thư viện có thể cần các thư viện khác để thực hiện chức năng của nó. Khi metadata của thư viện khai báo những thành phần đó, build tool có thể tiếp tục phân giải chúng. Các dependency được đưa vào graph thông qua dependency khác được gọi là **phụ thuộc bắc cầu (transitive dependency)**.

Ví dụ minh họa:

```text
Ứng dụng
├── Jackson Databind                 (trực tiếp)
│   ├── Jackson Core                  (bắc cầu)
│   └── Jackson Annotations           (bắc cầu)
└── Spring Web                       (trực tiếp)
    ├── Spring Core                  (bắc cầu)
    ├── Spring Beans                  (bắc cầu)
    └── Logging API                   (bắc cầu)
```

Ứng dụng chỉ khai báo `jackson-databind` và `spring-web`, nhưng dependency graph sau khi phân giải có thể bao gồm thêm các module mà hai thư viện đó cần. Project không phải tự liệt kê lại mọi dependency bắc cầu chỉ để build tool tải được chúng.

Sơ đồ trên chỉ minh họa quan hệ. Dependency graph thực tế phụ thuộc phiên bản, metadata được phát hành, configuration đang xét và các quy tắc resolution. Một dependency bắc cầu có thể bị loại trừ, bị thay phiên bản hoặc không xuất hiện trong một classpath nhất định.

### 2.1. Vì sao dependency bắc cầu hữu ích?

Nếu không có dependency bắc cầu, người dùng một thư viện sẽ phải biết toàn bộ thư viện nền tảng mà nó cần và khai báo từng thành phần. Điều này tạo ra một số vấn đề:

- Người dùng phải hiểu chi tiết triển khai nội bộ của thư viện.
- Khi thư viện thêm hoặc thay đổi dependency nền tảng, mọi project sử dụng nó có thể phải cập nhật khai báo.
- Các project có thể khai báo thiếu hoặc sai phiên bản của thành phần mà thư viện cần.
- Build script trở nên dài và lặp lại nhiều khai báo không thuộc trách nhiệm trực tiếp của ứng dụng.

Metadata dependency cho phép tác giả thư viện công bố những thành phần cần thiết. Build tool đọc metadata và xây dựng graph phù hợp cho từng configuration.

### 2.2. Dependency graph là mạng lưới, không chỉ là một danh sách

Một thư viện có thể được nhiều dependency trực tiếp yêu cầu. Ví dụ:

```text
Ứng dụng
├── Library A
│   └── Common X 1.2
└── Library B
    └── Common X 1.5
```

Ở đây, `Common X` được yêu cầu qua hai đường dẫn và hai phiên bản khác nhau. Build tool cần giải quyết xung đột để xác định phiên bản cuối cùng trong configuration đang phân giải.

Do đó, khi nhìn vào dependency graph, cần phân biệt:

- **Dependency declaration:** những gì project hoặc plugin khai báo trực tiếp.
- **Dependency graph đã phân giải:** toàn bộ thành phần và phiên bản được chọn sau khi áp dụng metadata, constraints, exclusions và quy tắc resolution.

Hai tập hợp này không nhất thiết giống nhau. Một dependency được khai báo có thể không xuất hiện trong graph cuối nếu bị loại trừ hoặc bị thay thế theo quy tắc cấu hình. Một thư viện không được project khai báo trực tiếp vẫn có thể xuất hiện vì một dependency khác yêu cầu nó.

## 3. Cách Gradle quản lý dependency trực tiếp và bắc cầu

### 3.1. Khai báo dependency trực tiếp

Trong Gradle, dependency được khai báo trong khối `dependencies`. Configuration xác định dependency thuộc phạm vi nào.

```groovy
dependencies {
    // Dùng trong mã nguồn chính và runtime của ứng dụng
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'

    // Chỉ cần cho biên dịch và chạy test
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}
```

`implementation` và `testImplementation` là hai configuration do Java plugin cung cấp. Khi một task cần compile classpath hoặc runtime classpath tương ứng, Gradle phân giải dependency graph cho configuration đó.

Không nên coi dependency graph là một graph duy nhất áp dụng cho mọi hoạt động. Project có các configuration khác nhau như `compileClasspath`, `runtimeClasspath`, `testCompileClasspath` và `testRuntimeClasspath`. Một thư viện có thể xuất hiện trong runtime classpath nhưng không xuất hiện trong compile classpath, hoặc chỉ có trong classpath của test.

### 3.2. Dependency trực tiếp của module khác trong cùng build

Trong build nhiều module, project có thể khai báo một project dependency:

```groovy
dependencies {
    implementation project(':domain')
}
```

Đây là dependency trực tiếp của module đang khai báo. Gradle sử dụng metadata của project `:domain` và các dependency mà project đó công bố để giải quyết graph. Quan hệ project dependency cũng giúp Gradle sắp xếp task sao cho đầu ra cần thiết của project được phụ thuộc sẵn sàng.

### 3.3. Dependency bắc cầu trong Gradle

Gradle mặc định cho phép dependency bắc cầu. Khi phân giải một configuration, Gradle đọc metadata của các module để tìm những dependency khác mà chúng yêu cầu.

Ví dụ:

```groovy
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

`jackson-databind` có thể đưa các module Jackson liên quan vào graph. Tập module cụ thể phụ thuộc metadata của version được chọn. Không cần thêm các module đó vào `dependencies` nếu mã nguồn ứng dụng không trực tiếp sử dụng API của chúng và không có yêu cầu cấu hình đặc biệt.

### 3.4. `api` và `implementation` trong thư viện Gradle

Với plugin `java-library`, hai configuration `api` và `implementation` có ý nghĩa quan trọng khi project được dùng như một thư viện:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'com.google.guava:guava:33.2.1-jre'
    implementation 'org.slf4j:slf4j-api:2.0.13'
}
```

- `api`: dependency là một phần của API công khai mà consumer cần nhìn thấy trên compile classpath khi sử dụng thư viện.
- `implementation`: dependency phục vụ nội bộ implementation của thư viện; consumer vẫn có thể cần nó ở runtime theo metadata, nhưng không nhất thiết phải nhìn thấy nó trên compile classpath.

Ví dụ, nếu một public method của thư viện nhận hoặc trả về kiểu `ImmutableList` của Guava, consumer cần nhìn thấy Guava để biên dịch mã sử dụng API đó. Khi đó `api` có thể phù hợp. Nếu SLF4J chỉ được dùng bên trong class của thư viện, `implementation` thường phù hợp hơn.

Việc chọn `api` hay `implementation` ảnh hưởng cách dependency được công bố cho project tiêu thụ. Dùng `api` quá rộng làm lộ chi tiết nội bộ và có thể khiến consumer nhận compile dependency không cần thiết. Dùng `implementation` cho kiểu xuất hiện trong API công khai có thể khiến consumer không biên dịch được.

`api` không phải configuration mặc định của plugin `java`; nó được cung cấp bởi `java-library`. Với một ứng dụng Java thông thường, `implementation` thường là lựa chọn trực tiếp.

## 4. Cách Maven quản lý dependency trực tiếp và bắc cầu

### 4.1. Khai báo dependency trực tiếp trong POM

Maven khai báo dependency trong phần `<dependencies>` của `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.2</version>
    </dependency>
</dependencies>
```

Đây là dependency trực tiếp của project. Maven đọc metadata của artifact để tìm dependency bắc cầu và áp dụng scope cùng các quy tắc quản lý version.

### 4.2. Scope ảnh hưởng đến khả năng truyền dependency

Maven dùng scope để xác định dependency được sử dụng ở giai đoạn nào và có truyền tiếp cho project tiêu thụ hay không.

| Scope | Mục đích chính | Tính bắc cầu tiêu biểu |
|---|---|---|
| `compile` | Biên dịch và chạy; là scope mặc định nếu không khai báo | Có thể truyền tiếp cho consumer |
| `runtime` | Cần khi chạy, không cần cho compile classpath chính | Có thể truyền tiếp ở runtime |
| `provided` | Môi trường chạy dự kiến cung cấp dependency, ví dụ servlet API trong container | Không truyền tiếp theo cách thông thường |
| `test` | Chỉ dùng để biên dịch và chạy test của project hiện tại | Không truyền tiếp cho consumer |
| `system` | Dùng JAR tại một đường dẫn cục bộ cụ thể | Không truyền tiếp; không khuyến khích vì phụ thuộc máy |
| `import` | Nhập dependency management từ BOM trong `dependencyManagement` | Dùng để quản lý version, không phải dependency classpath thông thường |

Ví dụ dependency test:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.3</version>
    <scope>test</scope>
</dependency>
```

JUnit được dùng để biên dịch và chạy test của project, không trở thành dependency runtime thông thường của ứng dụng khi project được consumer sử dụng.

### 4.3. Dependency bắc cầu trong Maven

Với dependency có scope phù hợp như `compile` hoặc `runtime`, Maven có thể đưa dependency bắc cầu vào classpath theo quy tắc scope propagation. Ví dụ, nếu project A phụ thuộc B, và B phụ thuộc C với scope compile, C có thể được truyền đến A.

```text
Project A
└── B (compile)
    └── C (compile)
```

Tuy nhiên, không phải scope nào cũng truyền tiếp. Dependency `test` và `provided` của B không được truyền cho A như dependency compile thông thường. Vì vậy, khi một dependency xuất hiện hoặc không xuất hiện trong classpath Maven, cần xét cả đường đi và scope của từng cạnh trong graph.

## 5. Vì sao không nên dựa vào dependency bắc cầu cho API mình sử dụng trực tiếp?

Giả sử mã nguồn ứng dụng gọi trực tiếp một class từ thư viện `jackson-core`, nhưng build script chỉ khai báo `jackson-databind` vì thư viện này hiện đang kéo `jackson-core` vào graph.

```java
import com.fasterxml.jackson.core.JsonFactory;

public class JsonReaderFactory {
    public JsonFactory create() {
        return new JsonFactory();
    }
}
```

Nếu project trực tiếp sử dụng API `JsonFactory`, nên khai báo dependency cung cấp API đó một cách trực tiếp. Nếu chỉ dựa vào dependency bắc cầu, một phiên bản khác của `jackson-databind` có thể thay đổi metadata hoặc không còn kéo `jackson-core` theo cách cũ. Khi đó mã nguồn ứng dụng có thể không biên dịch được dù ứng dụng vẫn đang trực tiếp sử dụng API của thư viện.

Khai báo trực tiếp giúp:

- Thể hiện rõ project phụ thuộc vào API nào.
- Làm cho build script phản ánh đúng nhu cầu của mã nguồn.
- Giảm phụ thuộc ngầm vào cách một thư viện khác đóng gói metadata.
- Giúp công cụ phân tích dependency và người bảo trì hiểu ý định của project.
- Cho phép quản lý version và cập nhật thư viện trực tiếp một cách có chủ đích.

Quy tắc thực tế là: **nếu mã nguồn hoặc build logic của project trực tiếp sử dụng một thư viện, hãy khai báo thư viện đó trực tiếp trong cấu hình phù hợp.** Không cần khai báo lại mọi dependency bắc cầu mà project không trực tiếp sử dụng.

## 6. Xung đột phiên bản trong dependency graph

### 6.1. Vì sao xung đột xảy ra?

Hai dependency trực tiếp có thể yêu cầu hai phiên bản khác nhau của cùng một module:

```text
Ứng dụng
├── Library A
│   └── Common X 1.4
└── Library B
    └── Common X 2.1
```

Project cũng có thể khai báo trực tiếp `Common X 1.8`, trong khi một dependency bắc cầu yêu cầu `Common X 2.1`. Build tool cần chọn một phiên bản hoặc báo lỗi tùy quy tắc resolution được cấu hình.

Một phiên bản được chọn không tự động có nghĩa mọi thư viện đều tương thích với nó. Nếu A chỉ hoạt động với API của X 1.x nhưng graph chọn X 2.x có breaking change, ứng dụng có thể lỗi lúc chạy dù dependency resolution thành công.

### 6.2. Quy tắc mặc định của Gradle

Trong trường hợp thông thường, Gradle giải quyết xung đột version của cùng một module bằng cách chọn version cao hơn theo quy tắc version ordering của Gradle. Đây là hành vi mặc định, nhưng resolution strategy, version constraints, platforms, rich versions hoặc dependency substitution có thể làm thay đổi kết quả.

Có thể dùng dependency constraint để ảnh hưởng đến phiên bản được chọn mà không trực tiếp thêm một dependency vào graph:

```groovy
dependencies {
    implementation 'com.example:library-a:1.0.0'

    constraints {
        implementation('com.example:common-x:2.1.0') {
            because 'Keep the application on the compatible Common X release'
        }
    }
}
```

Constraint góp phần quản lý version khi module được yêu cầu trong graph; bản thân constraint không nhất thiết làm module xuất hiện nếu không có dependency nào yêu cầu nó.

Với dự án cần đồng bộ nhiều version, có thể dùng platform/BOM. Có thể bật chế độ báo lỗi khi gặp xung đột để buộc nhóm xử lý rõ ràng:

```groovy
configurations.configureEach {
    resolutionStrategy.failOnVersionConflict()
}
```

Không nên thêm quy tắc này một cách máy móc cho mọi build cũ vì graph hiện tại có thể chứa những xung đột đã được nhóm chấp nhận. Hãy hiểu graph và đặt chính sách resolution phù hợp với dự án.

### 6.3. Quy tắc mặc định của Maven

Maven thường dùng quy tắc **nearest definition**: dependency nằm ở độ sâu ít hơn tính từ project hiện tại thường được chọn. Nếu hai version ở cùng độ sâu, dependency được khai báo trước có thể được ưu tiên theo thứ tự trong POM.

Ví dụ:

```text
Project
├── A
│   └── Common X 1.4       (độ sâu 2)
└── B
    └── Common X 2.1       (độ sâu 2)
```

Hai version ở cùng độ sâu. Thứ tự khai báo dependency trực tiếp có thể quyết định version nào thắng. Nếu project khai báo trực tiếp `Common X 2.0`, dependency đó ở độ sâu 1 và thường thắng các yêu cầu bắc cầu ở độ sâu 2.

Maven cho phép dùng `dependencyManagement` để quản lý version của dependency khi nó xuất hiện trong graph. Cần phân biệt `dependencyManagement` với `dependencies`:

- `<dependencies>` khai báo dependency thực sự của project.
- `<dependencyManagement>` quản lý version, scope hoặc cấu hình mặc định cho dependency khi được khai báo hoặc được kế thừa trong phạm vi phù hợp; nó không tự thêm tất cả dependency vào classpath.

Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>common-x</artifactId>
            <version>2.1.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Khi một dependency trực tiếp hoặc bắc cầu yêu cầu `com.example:common-x` mà không có version được quyết định ở nơi ưu tiên cao hơn, dependency management có thể cung cấp version đã quản lý.

## 7. Platform và BOM để quản lý nhiều dependency liên quan

Một framework thường phát hành nhiều module cần tương thích phiên bản với nhau. Nếu từng module được khai báo version độc lập, project có thể vô tình trộn những version không tương thích.

### 7.1. BOM trong Maven

BOM (Bill of Materials) là một POM tập trung quản lý version của một nhóm dependency. Project có thể import BOM vào `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

BOM cung cấp version được quản lý cho starter và các dependency liên quan. Project vẫn phải khai báo starter trong `<dependencies>` để sử dụng nó. Import BOM không tự đưa toàn bộ module trong BOM vào classpath.

### 7.2. Platform trong Gradle

Gradle có thể sử dụng Maven BOM qua platform:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Platform đưa các dependency constraints từ BOM vào resolution. `platform(...)` là cơ chế quản lý version; starter vẫn là dependency thực sự được project yêu cầu.

Gradle còn hỗ trợ `enforcedPlatform`, có mức ràng buộc mạnh hơn và có thể áp đặt version lên các dependency tiêu thụ. Chỉ nên dùng khi hiểu tác động đến consumer và toàn graph, vì enforced version có thể ghi đè lựa chọn mà project tiêu thụ mong muốn.

## 8. Loại trừ dependency bắc cầu

Đôi khi một dependency bắc cầu không cần thiết, gây xung đột hoặc bị thay bằng implementation khác. Gradle và Maven đều hỗ trợ exclusion, nhưng cần dùng cẩn thận.

### 8.1. Exclude trong Gradle

Có thể loại trừ module theo một dependency path:

```groovy
dependencies {
    implementation('com.example:legacy-client:1.5.0') {
        exclude group: 'commons-logging', module: 'commons-logging'
    }
}
```

Khai báo này loại trừ `commons-logging` khỏi graph đi qua dependency `legacy-client`. Nếu một dependency path khác vẫn yêu cầu cùng module, module đó vẫn có thể xuất hiện trong graph.

Có thể dùng exclusion ở configuration rộng hơn, nhưng phạm vi rộng làm tăng nguy cơ loại bỏ thư viện mà một thành phần khác cần. Nên giới hạn exclusion ở dependency path gây ra vấn đề khi có thể.

### 8.2. Exclude trong Maven

Maven khai báo exclusion bên trong dependency:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.5.0</version>
    <exclusions>
        <exclusion>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion áp dụng cho nhánh dependency được khai báo. Nếu một nhánh khác vẫn đưa cùng artifact vào graph, artifact vẫn có thể được phân giải qua nhánh đó.

### 8.3. Trước khi exclude, cần hiểu ai đang cần thư viện

Không nên loại trừ dependency chỉ vì thấy nó không được import trực tiếp trong mã nguồn. Một thư viện có thể cần dependency đó khi chạy, thông qua reflection, service loader hoặc cấu hình runtime.

Trước khi exclude, hãy xác định:

- Dependency nào đưa module vào graph.
- Module đó được dùng ở compile, runtime hay test.
- Thư viện cha có thật sự hỗ trợ chạy mà không cần dependency bị loại trừ không.
- Có implementation thay thế hoặc dependency version tương thích không.
- Các test tích hợp và đường chạy runtime có còn hoạt động không.

Exclusion chỉ thay đổi graph; nó không tự sửa mã nguồn hoặc cấu hình runtime đang cần lớp bị loại bỏ.

## 9. Dependency optional và dependency không truyền tiếp

Một thư viện có thể hỗ trợ tính năng tùy chọn cần thư viện khác. Tác giả thư viện có thể đánh dấu dependency là optional trong metadata Maven để consumer không tự động nhận nó qua dependency bắc cầu.

Ví dụ một thư viện hỗ trợ tích hợp với nhiều database nhưng ứng dụng chỉ sử dụng một loại. Tác giả có thể công bố driver hoặc integration module như dependency optional, yêu cầu ứng dụng chọn và khai báo phần cần dùng.

Trong Maven, dependency có thể khai báo:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>database-integration</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

Dependency optional vẫn là dependency của project phát hành nó, nhưng không được truyền tự động đến consumer như dependency bắc cầu thông thường. Consumer cần tính năng đó phải khai báo trực tiếp.

Gradle không có một cờ `optional` tương đương được sử dụng theo cùng cách trong mọi trường hợp. Khi công bố thư viện, cần thiết kế các configuration/variant và metadata phù hợp để thể hiện dependency nào thuộc API, runtime hoặc tính năng tùy chọn. Không nên dịch máy móc metadata optional của Maven thành một exclusion toàn cục.

## 10. Cách xem dependency graph và tìm nguồn dependency

Đọc dependency graph là kỹ năng quan trọng khi build có nhiều thư viện. Thay vì thêm hoặc xóa dependency theo cảm tính, hãy truy tìm đường đi đã đưa module vào graph.

### 10.1. Gradle: dependencies

Lệnh sau hiển thị dependency graph của project:

```bash
./gradlew dependencies
```

Có thể chỉ định configuration:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Ký hiệu trong output giúp nhận biết dependency bắc cầu, version được chọn hoặc nhánh đã bị loại bỏ/được thay thế. Định dạng chính xác có thể khác giữa phiên bản Gradle.

### 10.2. Gradle: dependencyInsight

Khi muốn biết vì sao một module xuất hiện và version nào được chọn:

```bash
./gradlew dependencyInsight \
    --dependency jackson-core \
    --configuration runtimeClasspath
```

`dependencyInsight` giúp xem các yêu cầu version, các đường dẫn dependency và lý do một version được chọn trong configuration đó. Đây thường là lệnh hữu ích hơn việc chỉ nhìn một danh sách artifact khi đang điều tra xung đột.

### 10.3. Maven: dependency:tree

Maven Dependency Plugin cung cấp goal `tree`:

```bash
./mvnw dependency:tree
```

Có thể lọc theo artifact:

```bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-core
```

Dependency tree cho thấy dependency trực tiếp và các nhánh bắc cầu. Output cũng thể hiện scope và các node bị omitted do conflict hoặc quy tắc resolution.

## 11. Giữ dependency graph ổn định

Một dependency graph có thể thay đổi khi metadata, version hoặc repository thay đổi. Với build cần tái lập, nhóm nên quản lý version và xác minh graph có chủ đích.

### 11.1. Khai báo version rõ ràng

Dependency trực tiếp nên có version rõ ràng hoặc được quản lý qua platform/BOM, version catalog hay dependency management. Tránh dùng version động nếu build cần cho ra cùng một tập artifact trong các lần chạy.

### 11.2. Dùng dependency locking khi phù hợp

Gradle dependency locking ghi nhận các version đã được phân giải cho configuration được khóa. Điều này giúp các lần build sau sử dụng cùng version thay vì thay đổi theo metadata mới xuất hiện trong repository.

Dependency locking không thay thế khai báo dependency hoặc platform. Nó ghi nhận kết quả resolution để tăng tính tái lập. Khi chủ động nâng version, cần cập nhật lock state theo quy trình của dự án và review thay đổi.

### 11.3. Xác minh artifact

Gradle dependency verification có thể kiểm tra checksum hoặc chữ ký artifact đã tải. Cơ chế này giúp phát hiện artifact bị thay đổi ngoài dự kiến hoặc không đúng với dữ liệu đã được tin cậy.

Locking và verification giải quyết hai vấn đề khác nhau:

- Locking kiểm soát version được chọn.
- Verification kiểm tra tính toàn vẹn/xác thực của artifact được tải.

### 11.4. Không khai báo dependency chỉ vì nó tình cờ có mặt

Nếu mã nguồn trực tiếp sử dụng API của một thư viện, hãy khai báo thư viện đó trực tiếp. Nếu project không sử dụng API và dependency chỉ cần thiết vì thư viện khác yêu cầu, hãy để metadata của thư viện mô tả quan hệ bắc cầu.

Điều này làm dependency declaration phản ánh đúng trách nhiệm của project và giảm nguy cơ build hỏng khi thư viện trung gian thay đổi.

## 12. Ví dụ thực tế: tìm dependency bắc cầu gây xung đột

Giả sử ứng dụng có cấu hình Gradle:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.example:report-client:1.0.0'
    implementation 'com.example:search-client:2.0.0'
}
```

Giả sử hai client cùng yêu cầu các version khác nhau của một module `com.example:common-json`. Build thành công nhưng khi chạy, ứng dụng lỗi do một API không tương thích.

Quy trình điều tra:

1. Xác định configuration bị lỗi, ví dụ `runtimeClasspath`.
2. Chạy `./gradlew dependencies --configuration runtimeClasspath` để xem graph.
3. Chạy `dependencyInsight` với `common-json` để xem đường đi và version request.
4. Kiểm tra release notes hoặc compatibility của hai client với version `common-json` được chọn.
5. Chọn cách xử lý: nâng một client, dùng platform/constraint, thay thư viện, hoặc exclude một nhánh nếu dependency đó thực sự không cần.
6. Chạy lại test và kiểm tra đường chạy runtime có sử dụng các API liên quan.

Không nên lập tức exclude `common-json` chỉ để build qua. Nếu một client cần module đó, loại bỏ nó có thể khiến lỗi chuyển từ dependency resolution sang `ClassNotFoundException` hoặc `NoClassDefFoundError` khi chạy.

## 13. Nguyên tắc lựa chọn direct và transitive dependency

- **Khai báo trực tiếp API mà project sử dụng.** Đừng dựa vào việc một thư viện khác tình cờ kéo API đó vào graph.
- **Không lặp lại mọi dependency bắc cầu.** Hãy để metadata của thư viện mô tả các dependency mà nó cần.
- **Chọn configuration hoặc scope đúng.** Compile, runtime và test có classpath khác nhau.
- **Dùng `api` có chủ đích với thư viện công bố API.** Với `java-library`, chỉ công bố dependency mà consumer thực sự cần nhìn thấy khi biên dịch API.
- **Xem graph trước khi xử lý xung đột.** Xác định module, version và đường dẫn đưa nó vào graph.
- **Dùng BOM/platform hoặc constraints để quản lý version liên quan.** Đừng sửa từng dependency bắc cầu một cách rời rạc khi chúng thuộc cùng một bộ version.
- **Exclude ở phạm vi hẹp.** Xác nhận thư viện bị loại bỏ không còn cần cho compile/runtime/test.
- **Hiểu optional dependency.** Không giả định mọi dependency của thư viện đều tự động được truyền đến consumer.
- **Khóa và xác minh dependency khi cần build tái lập.** Review thay đổi graph khi cập nhật lock state hoặc version.
- **Kiểm tra runtime, không chỉ compile.** Dependency bắc cầu có thể chỉ cần khi ứng dụng chạy.

## 14. Bài tập vận dụng

Một project khai báo trực tiếp `library-a` và `library-b`. Dependency graph hiển thị:

```text
Application
├── library-a:1.0
│   ├── common-util:1.2
│   └── json-core:2.0
└── library-b:3.0
    ├── common-util:1.5
    └── http-client:4.1
```

Hãy phân tích:

1. Những dependency nào là trực tiếp của Application?
2. Những dependency nào là bắc cầu?
3. Vì sao `common-util` có hai yêu cầu version?
4. Build tool cần làm gì để tạo một runtime classpath có một version được chọn cho `common-util`?
5. Nếu mã nguồn Application trực tiếp import một class từ `http-client`, có nên khai báo `http-client` trực tiếp không? Vì sao?
6. Nếu muốn loại trừ `json-core`, cần xác minh điều gì trước khi thêm exclusion?
7. Trong Gradle, dùng lệnh nào để xem version `common-util` được chọn và lý do chọn?
8. Trong Maven, dùng goal nào để xem dependency tree?

Có thể tự kiểm chứng bằng cách tạo một project nhỏ với hai thư viện có dependency chung, sau đó chạy `./gradlew dependencies` và `./gradlew dependencyInsight`. Với Maven, dùng `./mvnw dependency:tree`. Quan sát cách graph thể hiện các đường đi, version request, scope và version cuối cùng.

Khi đọc một dependency graph, hãy luôn xác định project trực tiếp yêu cầu những module nào, các module nào được kéo vào qua metadata, và configuration hiện tại cần những thành phần nào. Sự phân biệt này giúp build script thể hiện đúng nhu cầu của ứng dụng, xử lý version conflict có căn cứ và tránh phụ thuộc ngầm vào implementation của thư viện khác.
