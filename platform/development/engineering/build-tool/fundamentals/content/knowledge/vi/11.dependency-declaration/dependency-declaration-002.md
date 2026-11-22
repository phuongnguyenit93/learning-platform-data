# Phụ thuộc bên ngoài, phụ thuộc giữa mô-đun và tệp JAR cục bộ

Một ứng dụng Java hiếm khi chỉ gồm những lớp do chính nhóm phát triển viết. Dự án thường sử dụng thư viện bên ngoài như Spring, Jackson hoặc JUnit; chia mã nguồn thành nhiều module như `app`, `domain` và `infrastructure`; đôi khi còn phải tích hợp một thư viện chỉ được cung cấp dưới dạng tệp JAR. Ba loại đầu vào này đều có thể xuất hiện trên classpath, nhưng build tool quản lý chúng theo những cách khác nhau.

Khi khai báo phụ thuộc, cần xác định thư viện đến từ đâu, phiên bản nào được sử dụng, module nào cần nó và nó cần có ở giai đoạn biên dịch, chạy ứng dụng hay kiểm thử. Khai báo đúng giúp build tái tạo được trên máy khác, quản lý phiên bản nhất quán và tránh việc một module vô tình phụ thuộc vào thư viện mà nó không khai báo.

## 1. Dependency là gì?

Một dependency (phụ thuộc) là thành phần mà một phần của dự án cần sử dụng để thực hiện công việc. Trong Java, dependency thường là một hoặc nhiều lớp được cung cấp qua thư viện JAR hoặc qua một module khác.

Ví dụ, lớp sau sử dụng `ObjectMapper` của Jackson:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class JsonReader {
    private final ObjectMapper mapper = new ObjectMapper();
}
```

Lệnh `import` giúp trình biên dịch nhận diện tên lớp trong mã nguồn. Nó không tự tải Jackson và cũng không tự thêm thư viện vào classpath. Build tool phải khai báo dependency để tìm được lớp `ObjectMapper` khi biên dịch và khi ứng dụng chạy.

Tương tự, nếu module `app` sử dụng lớp `OrderService` do module `domain` cung cấp, `app` cần khai báo quan hệ phụ thuộc tới `domain`. Việc hai thư mục cùng nằm trong một repository không tự động tạo ra quan hệ đó.

## 2. Ba nguồn dependency thường gặp

| Loại dependency | Nguồn cung cấp | Cách nhận diện | Ví dụ |
|---|---|---|---|
| Phụ thuộc bên ngoài | Repository artifact như Maven Central hoặc repository nội bộ | Tọa độ group, artifact, version | `org.springframework:spring-context:6.1.14` |
| Phụ thuộc giữa module/project | Một project khác trong cùng build hoặc reactor | Định danh project hoặc tọa độ module | Gradle `project(':domain')`; Maven `com.example:domain:1.0.0` |
| JAR cục bộ | Một tệp trên filesystem | Đường dẫn đến file `.jar` | `libs/vendor-sdk.jar` |

Các loại dependency có thể cùng được dùng trong một module. Ví dụ, module `app` phụ thuộc vào module `domain`, dùng thư viện Spring từ repository và tích hợp một SDK cũ chỉ có file JAR.

```text
                       Repository bên ngoài
                      (Spring, Jackson, JUnit)
                               |
                               v
Module app --------------> Module domain
    |
    +--------------------> libs/vendor-sdk.jar
```

Điều quan trọng là build tool cần biết nguồn và danh tính của từng dependency để giải quyết chúng, xác định phiên bản và đưa đúng tệp vào classpath tương ứng.

## 3. Phụ thuộc bên ngoài: tọa độ artifact và repository

Thư viện bên ngoài thường được phân phối dưới dạng artifact có tọa độ. Với Maven, cách viết phổ biến là:

```text
groupId:artifactId:version
```

Ví dụ:

```text
com.fasterxml.jackson.core:jackson-databind:2.17.2
```

Ba thành phần có ý nghĩa:

- `groupId`: nhóm hoặc tổ chức phát hành artifact, thường phản ánh namespace của nhà cung cấp.
- `artifactId`: tên artifact cụ thể.
- `version`: phiên bản cần sử dụng.

Repository là nơi lưu trữ và phân phối artifact. Build tool dùng tọa độ để tìm metadata và các tệp cần thiết trong repository đã khai báo. Repository có thể là dịch vụ công khai như Maven Central, repository của tổ chức hoặc một repository file-system được quản lý riêng.

### Khai báo repository trong Gradle

Với Gradle, repository thường được khai báo ở cấp settings hoặc build theo chính sách của dự án. Ví dụ đơn giản trong `build.gradle`:

```groovy
repositories {
    mavenCentral()
}
```

Khai báo repository cho biết Gradle có thể tìm artifact ở đâu. Nó không tự thêm thư viện nào vào project. Muốn sử dụng thư viện, cần khai báo dependency riêng.

```groovy
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

Gradle đọc tọa độ, tìm metadata của artifact trong repository và giải quyết các dependency liên quan. Sau đó, các file cần thiết được đưa vào classpath của configuration tương ứng.

Trong build nhiều project, tổ chức có thể tập trung repository ở `settings.gradle` bằng `dependencyResolutionManagement`. Khi đó, chính sách repository được quản lý ở một nơi thay vì để mỗi module khai báo tùy ý. Cách cấu hình cụ thể phụ thuộc vào quy ước của repository.

### Khai báo repository và dependency là hai việc khác nhau

Hai khối sau có trách nhiệm khác nhau:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

`repositories` xác định nơi tìm kiếm. `dependencies` xác định module cần artifact nào. Chỉ khai báo repository không khiến thư viện tự xuất hiện trong classpath; chỉ khai báo dependency mà không có repository phù hợp có thể khiến Gradle không tìm thấy artifact.

## 4. Phụ thuộc bên ngoài trong Maven

Maven sử dụng `pom.xml` để khai báo dependency và repository. Ví dụ:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>order-app</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>
</project>
```

Maven tìm artifact theo tọa độ trong các repository được cấu hình, bao gồm repository mặc định và repository bổ sung của dự án hoặc môi trường. Thông tin repository thường được quản lý trong POM hoặc `settings.xml` tùy phạm vi và chính sách của tổ chức.

Đối với dự án thông thường, nên khai báo dependency bằng tọa độ ổn định và dùng version được quản lý rõ ràng. Không nên đưa thông tin xác thực repository vào POM được commit công khai; thông tin nhạy cảm nên được quản lý bằng cơ chế settings/credential của môi trường build.

## 5. Dependency transitive: phụ thuộc bắc cầu

Một thư viện có thể cần các thư viện khác để hoạt động. Ví dụ:

```text
application
    |
    v
library-A
    |
    +----> library-B
    |
    +----> library-C
```

Nếu module ứng dụng khai báo `library-A`, build tool có thể tự giải quyết `library-B` và `library-C` dựa trên metadata dependency của `library-A`. Những dependency được kéo theo như vậy gọi là *transitive dependencies* (phụ thuộc bắc cầu).

Metadata thường được lưu trong POM hoặc Gradle Module Metadata của artifact. Metadata mô tả các dependency khác, version constraint, variant và thông tin liên quan. Vì vậy, một dependency bên ngoài được lấy từ repository thường cung cấp cho build tool nhiều thông tin hơn một tệp JAR đơn lẻ.

Không phải mọi dependency bắc cầu đều luôn được giữ nguyên phiên bản mà thư viện gốc yêu cầu. Build tool có cơ chế giải quyết xung đột phiên bản và có thể chọn một phiên bản theo quy tắc của nó. Vì thế, khi có lỗi tương thích, cần xem dependency graph thực tế thay vì chỉ đọc một dòng khai báo trực tiếp.

## 6. Phụ thuộc giữa các module trong Gradle

Trong build nhiều project, các module thường được khai báo ở `settings.gradle`:

```groovy
rootProject.name = 'commerce'
include 'app', 'domain', 'infrastructure'
```

Cấu trúc thư mục có thể như sau:

```text
commerce/
├── settings.gradle
├── app/
│   └── build.gradle
├── domain/
│   └── build.gradle
└── infrastructure/
    └── build.gradle
```

Nếu `app` sử dụng lớp do `domain` cung cấp, khai báo project dependency trong `app/build.gradle`:

```groovy
dependencies {
    implementation project(':domain')
}
```

`project(':domain')` tham chiếu project có path `:domain` trong cùng Gradle build. Gradle có thể thiết lập quan hệ giữa các task của hai project, giải quyết artifact nội bộ và đưa đầu ra cần thiết của `domain` vào classpath của `app`.

Khi `app` phụ thuộc vào `domain`, build tool biết rằng `domain` là một phần của build hiện tại. Nó không cần tải một bản JAR `domain` từ repository từ xa nếu dependency được khai báo đúng dưới dạng project dependency.

### Project dependency khác với import Java

Giả sử `domain` có lớp:

```java
package com.example.domain;

public class Order {
    private final String id;

    public Order(String id) {
        this.id = id;
    }

    public String getId() {
        return id;
    }
}
```

Trong `app`, ta có thể viết:

```java
import com.example.domain.Order;

public class OrderController {
    public String getOrderId(Order order) {
        return order.getId();
    }
}
```

Lệnh `import` chỉ sử dụng tên lớp trong mã nguồn. Để biên dịch được, Gradle vẫn cần `app` có dependency tới `domain`. Nếu bỏ project dependency, compiler có thể báo không tìm thấy package hoặc symbol dù file `Order.java` vẫn nằm trong repository.

### Dependency giữa module không có nghĩa là mọi module đều phụ thuộc lẫn nhau

Nên khai báo quan hệ theo hướng sử dụng thực tế. Nếu `app` cần `domain`, khai báo `app -> domain`. Nếu `domain` không sử dụng `app`, không tạo dependency ngược lại. Một chu trình như `app -> domain -> app` thường là dấu hiệu ranh giới module chưa được thiết kế tốt và có thể gây khó khăn cho việc biên dịch, kiểm thử và tái sử dụng.

## 7. `implementation` và `api` trong Gradle

Khi sử dụng plugin Java, dependency thường được khai báo qua configuration như `implementation`, `compileOnly`, `runtimeOnly` và `testImplementation`. Nếu dùng plugin `java-library`, có thêm configuration `api` để biểu diễn dependency được phơi bày trong API của thư viện.

### `implementation`

```groovy
dependencies {
    implementation project(':domain')
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

`implementation` biểu thị dependency cần cho implementation của module. Với module thư viện, dependency này không được công bố như một phần compile API cho consumer thông qua mô hình `java-library`.

Ví dụ, nếu `OrderService` dùng Jackson bên trong để đọc JSON nhưng các phương thức công khai không yêu cầu kiểu Jackson, thư viện Jackson thường nên là `implementation`.

### `api`

`api` thuộc plugin `java-library`:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'com.google.guava:guava:33.3.1-jre'
}
```

Dùng `api` khi kiểu dữ liệu hoặc chữ ký API công khai của module phụ thuộc vào kiểu từ thư viện đó và consumer cần dependency trên compile classpath để biên dịch mã sử dụng API.

Ví dụ, nếu một thư viện công khai phương thức:

```java
public ImmutableList<String> names() {
    // ...
}
```

và `ImmutableList` thuộc Guava, dependency Guava có thể cần được khai báo là `api` để consumer biên dịch được khi sử dụng chữ ký công khai đó.

Không nên dùng `api` cho mọi dependency. Phơi bày quá nhiều dependency làm API của module bị gắn chặt với thư viện bên ngoài và khiến consumer nhận nhiều compile dependency hơn cần thiết.

### `compileOnly`, `runtimeOnly` và dependency kiểm thử

| Configuration | Có ở compile classpath chính | Có ở runtime classpath chính | Mục đích |
|---|---:|---:|---|
| `implementation` | Có | Có | Thư viện dùng trong mã nguồn chính |
| `api` (`java-library`) | Có và được consumer thấy qua API | Có | Dependency thuộc API công khai |
| `compileOnly` | Có | Không mặc định | API cần khi biên dịch nhưng môi trường chạy cung cấp |
| `runtimeOnly` | Không | Có | Thành phần chỉ cần khi chạy |
| `testImplementation` | Không thuộc compile chính; có trong test compile | Có trong test runtime | Thư viện dùng cho mã kiểm thử |
| `testRuntimeOnly` | Không | Có trong test runtime | Thành phần chỉ cần khi chạy kiểm thử |

Ví dụ:

```groovy
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
    runtimeOnly 'org.postgresql:postgresql:42.7.4'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}
```

Các version trong ví dụ chỉ minh họa cách khai báo. Trong dự án thật, cần chọn phiên bản tương thích với Java, framework và chính sách quản lý dependency của dự án.

Chọn configuration theo nơi dependency thực sự được sử dụng. Nếu khai báo nhầm `runtimeOnly` cho một thư viện mà mã nguồn import trực tiếp, biên dịch sẽ thất bại. Nếu khai báo mọi thứ bằng `implementation`, build có thể vẫn chạy nhưng compile/runtime classpath rộng hơn cần thiết và ý nghĩa dependency không rõ.

## 8. Phụ thuộc giữa các module trong Maven

Maven thường biểu diễn module bằng tọa độ `groupId`, `artifactId`, `version`. Một dự án nhiều module có thể có POM gốc khai báo các module thành viên:

```xml
<packaging>pom</packaging>

<modules>
    <module>domain</module>
    <module>app</module>
</modules>
```

POM của `domain` có thể khai báo:

```xml
<groupId>com.example</groupId>
<artifactId>domain</artifactId>
<version>1.0.0</version>
```

POM của `app` khai báo dependency tới `domain` bằng tọa độ tương ứng:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>domain</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Khi chạy Maven từ reactor root có khai báo cả hai module, Maven có thể sắp xếp thứ tự build theo quan hệ dependency và sử dụng artifact module được tạo trong cùng reactor. Nếu chạy riêng `app` mà `domain` chưa có trong reactor hoặc chưa được cài vào local repository, Maven có thể không giải quyết được dependency.

### `dependencyManagement` không tự thêm dependency

Trong POM gốc, `dependencyManagement` có thể quản lý phiên bản dùng chung:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module con vẫn phải khai báo dependency trong phần `<dependencies>` nếu nó thực sự sử dụng Jackson. `dependencyManagement` cung cấp thông tin quản lý như version và scope mặc định; nó không tự đưa artifact vào classpath của mọi module.

## 9. Dependency scope trong Maven

Maven dùng `scope` để mô tả dependency được sử dụng ở giai đoạn nào. Các scope phổ biến:

| Scope | Compile classpath | Test classpath | Runtime classpath | Ý nghĩa |
|---|---|---|---|---|
| `compile` | Có | Có | Có | Mặc định, dùng cho phần lớn thư viện ứng dụng |
| `provided` | Có | Có | Không theo runtime thông thường của ứng dụng | Môi trường triển khai cung cấp, ví dụ Servlet API trên container phù hợp |
| `runtime` | Không thuộc compile chính | Có | Có | Chỉ cần khi chạy, ví dụ JDBC driver |
| `test` | Không | Có | Có trong test runtime | Chỉ dùng cho kiểm thử |
| `system` | Có | Có | Không theo runtime thông thường | Dùng đường dẫn file cục bộ, gắn với máy; thường nên tránh |
| `import` | Không | Không | Không | Chỉ dùng để nhập BOM trong `dependencyManagement` của POM packaging |

Ví dụ:

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.3</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>42.7.4</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Chọn scope theo vai trò của thư viện. JUnit chỉ phục vụ kiểm thử nên dùng `test`; JDBC driver thường được nạp lúc ứng dụng chạy nên có thể dùng `runtime` nếu mã nguồn không tham chiếu trực tiếp lớp của driver.

## 10. Tệp JAR cục bộ là gì?

Một tệp JAR cục bộ là thư viện Java được lưu trực tiếp trong filesystem của dự án hoặc máy build, thay vì được giải quyết bằng tọa độ từ repository.

Ví dụ:

```text
my-app/
├── build.gradle
└── libs/
    └── vendor-sdk.jar
```

JAR có thể chứa các lớp Java đã biên dịch, tài nguyên và metadata như `META-INF/MANIFEST.MF`. Khi đưa JAR vào classpath, compiler và JVM có thể tìm các lớp được đóng gói bên trong.

### Khai báo file dependency trong Gradle

Với một JAR cụ thể:

```groovy
dependencies {
    implementation files('libs/vendor-sdk.jar')
}
```

Với nhiều JAR trong thư mục:

```groovy
dependencies {
    implementation fileTree(dir: 'libs', include: ['*.jar'])
}
```

`files(...)` tạo file dependency từ đường dẫn cụ thể. `fileTree(...)` tạo file collection từ các tệp khớp mẫu. Những file này có thể được đưa vào classpath của configuration được chọn.

Đường dẫn tương đối thường được tính từ project directory của build script. Cần bảo đảm file tồn tại trong repository hoặc được cung cấp theo một quy trình rõ ràng trên mọi máy build.

### Khai báo JAR cục bộ trong Maven

Maven có thể tham chiếu một JAR bằng scope `system` và `systemPath`, nhưng cách này thường không được khuyến khích:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>vendor-sdk</artifactId>
    <version>1.0</version>
    <scope>system</scope>
    <systemPath>${project.basedir}/libs/vendor-sdk.jar</systemPath>
</dependency>
```

`systemPath` gắn dependency với một vị trí filesystem cụ thể. Nó không hoạt động như một artifact repository thông thường, khó chia sẻ giữa các máy, và có thể gây vấn đề khi publish metadata cho consumer. Nếu cần dùng lâu dài hoặc nhiều module cùng sử dụng, nên cài/publish JAR vào repository nội bộ với tọa độ ổn định.

Một cách khác là cài JAR vào local Maven repository bằng `install:install-file` để phục vụ phát triển cục bộ. Tuy nhiên, thao tác cài trên một máy không tự đảm bảo CI hoặc máy của thành viên khác cũng có artifact đó. Repository nội bộ được quản lý chung thường phù hợp hơn cho dependency dùng trong nhóm.

## 11. Hạn chế quan trọng của JAR cục bộ

Một file JAR đơn lẻ thường chỉ chứa bytecode và tài nguyên. Nó không nhất thiết cung cấp metadata mô tả các thư viện khác mà nó cần.

Giả sử:

```text
application
    |
    v
vendor-sdk.jar
    |
    +---- cần library-x.jar
    |
    +---- cần library-y.jar
```

Nếu chỉ khai báo:

```groovy
dependencies {
    implementation files('libs/vendor-sdk.jar')
}
```

Gradle biết đường dẫn tới `vendor-sdk.jar`, nhưng không có POM hoặc Gradle Module Metadata để tự tìm `library-x.jar` và `library-y.jar`. Người phát triển phải tự cung cấp các dependency bổ sung:

```groovy
dependencies {
    implementation files('libs/vendor-sdk.jar')
    implementation 'com.example:library-x:2.0.0'
    implementation 'com.example:library-y:3.1.0'
}
```

Đây là khác biệt lớn giữa file dependency và module dependency lấy từ repository. Artifact repository thường có metadata để build tool giải quyết dependency bắc cầu; file JAR cục bộ không tự có thông tin đó.

Một JAR có thể chứa manifest hoặc metadata riêng, nhưng không nên mặc định rằng build tool sẽ hiểu mọi dependency của nó như khi đọc POM hoặc Gradle Module Metadata. Cần kiểm tra cách nhà cung cấp phân phối thư viện.

## 12. So sánh ba cách khai báo trong Gradle

| Cách khai báo | Ví dụ | Có danh tính module | Có metadata dependency bắc cầu |
|---|---|---:|---:|
| External module | `implementation 'g:a:1.0'` | Có | Có nếu repository cung cấp metadata |
| Project dependency | `implementation project(':domain')` | Có, là project trong build | Có thông qua mô hình project và các dependency được công bố/khai báo |
| File dependency | `implementation files('libs/a.jar')` | Chủ yếu là file path | Không tự có metadata module như repository artifact |

Project dependency còn giúp Gradle nối task graph và sử dụng kết quả build của module nội bộ. File dependency chỉ trỏ đến file có sẵn; Gradle không biết source project nào tạo ra nó hoặc task nào cần chạy để cập nhật nó.

Nếu JAR thực chất được tạo bởi một module trong cùng build, ưu tiên project dependency thay vì tham chiếu đường dẫn JAR nằm trong `build/libs`. Project dependency giữ quan hệ giữa các project trong build model và giúp tránh phụ thuộc vào artifact cũ còn sót lại trên ổ đĩa.

## 13. Version conflict và cách kiểm tra dependency graph

Một ứng dụng có thể nhận cùng một thư viện qua nhiều đường dependency:

```text
app
 |\
 | +--> library-A --> jackson-core 2.15
 |
 +-----> library-B --> jackson-core 2.17
```

Build tool cần chọn phiên bản phù hợp cho dependency graph. Kết quả có thể khác với suy nghĩ nếu chỉ nhìn dòng dependency trực tiếp.

### Kiểm tra trong Gradle

Có thể dùng `dependencies` để xem dependency tree:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
```

Trên Windows:

```powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
```

Để giải thích vì sao một dependency được chọn:

```bash
./gradlew :app:dependencyInsight --dependency jackson-core --configuration runtimeClasspath
```

`dependencies` cho thấy cây dependency của configuration; `dependencyInsight` tập trung vào một module và lý do phiên bản được chọn. Tên configuration có thể khác tùy plugin và loại project.

### Kiểm tra trong Maven

```bash
mvn dependency:tree
```

Lệnh này hiển thị dependency tree của project Maven. Có thể dùng bộ lọc như `-Dincludes=groupId:artifactId` để tập trung vào một dependency cụ thể.

Khi có xung đột, hãy xác định dependency nào kéo phiên bản vào, scope nào đang sử dụng và có cần quản lý phiên bản tập trung bằng constraint, platform/BOM hoặc `dependencyManagement` hay không.

## 14. Quản lý phiên bản dependency nhất quán

Không nên để mỗi module tự chọn một phiên bản thư viện dùng chung một cách tùy tiện. Khi nhiều module cần cùng thư viện, nên có chính sách quản lý version.

### Gradle version catalog

Gradle hỗ trợ version catalog trong `gradle/libs.versions.toml`. Ví dụ:

```toml
[versions]
jackson = "2.17.2"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
```

Module có thể sử dụng alias:

```groovy
dependencies {
    implementation libs.jackson.databind
}
```

Version catalog giúp đặt tên dependency và version ở một nơi, giảm lỗi gõ tọa độ và làm cấu hình giữa module nhất quán hơn. Nó không tự thêm thư viện vào mọi module; module nào dùng vẫn cần khai báo dependency.

### Maven BOM và dependencyManagement

Maven có thể nhập BOM (*Bill of Materials*) để quản lý version của một nhóm dependency:

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
```

Sau khi version được quản lý, module có thể khai báo dependency mà không lặp lại version nếu dependency đó nằm trong BOM hoặc `dependencyManagement` tương ứng.

Quản lý version tập trung giúp nâng cấp có chủ đích. Tuy nhiên, vẫn cần kiểm tra tương thích giữa các module, framework và phiên bản Java trước khi đổi version.

## 15. Chọn loại dependency phù hợp

Có thể dùng những câu hỏi sau để chọn cách khai báo:

**Thư viện được phát hành độc lập và có tọa độ artifact?** Dùng external module dependency từ repository. Cách này phù hợp với thư viện công khai và thư viện nội bộ đã được publish.

**Mã nguồn thuộc một project trong cùng Gradle build?** Dùng project dependency. Cách này giữ quan hệ giữa các project và cho phép Gradle quản lý task graph.

**Mã nguồn thuộc module Maven trong cùng reactor?** Khai báo dependency theo tọa độ module và bảo đảm module được đưa vào reactor build.

**Chỉ có một file JAR không có metadata?** Có thể dùng file dependency trong Gradle hoặc cơ chế tạm thời phù hợp của Maven, đồng thời khai báo rõ dependency mà JAR cần. Nếu thư viện được dùng rộng rãi, nên đưa nó vào repository nội bộ.

**JAR được tạo bởi một project khác trong cùng build?** Ưu tiên project dependency thay vì tham chiếu file JAR đầu ra bằng đường dẫn cứng.

## 16. Những lỗi thường gặp

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `package ... does not exist` | Dependency thiếu trên compile classpath hoặc sai version | Kiểm tra khai báo dependency và configuration/scope |
| `ClassNotFoundException` khi chạy | Thư viện có ở compile nhưng thiếu ở runtime | Kiểm tra `runtimeClasspath` hoặc runtime scope |
| `NoClassDefFoundError` | Thiếu lớp lúc runtime, dependency bắc cầu hoặc phiên bản không tương thích | Xem dependency tree và metadata của artifact |
| Module nội bộ không được tìm thấy | Project chưa được include hoặc tọa độ module không khớp | Kiểm tra `settings.gradle`/Maven reactor và project coordinates |
| Local JAR biên dịch được nhưng chạy lỗi | JAR cần thêm thư viện mà build không tự giải quyết | Bổ sung dependency bắc cầu hoặc publish JAR kèm metadata |
| Máy cá nhân build được, CI thất bại | JAR chỉ có trên máy cá nhân hoặc repository/credential khác nhau | Đưa artifact vào repository chung hoặc bảo đảm file được version hóa và có sẵn |
| Hai module dùng version khác nhau | Version khai báo phân tán hoặc dependency bắc cầu xung đột | Dùng catalog, platform/BOM hoặc dependency management và kiểm tra graph |
| Dùng `compileOnly` cho thư viện cần lúc chạy | Chọn sai configuration | Chọn `implementation` hoặc `runtimeOnly` theo cách sử dụng |
| Dùng `api` cho dependency nội bộ không lộ ra API | Phơi bày dependency không cần thiết | Chuyển sang `implementation` khi phù hợp |

## 17. Ví dụ tổng hợp: ứng dụng có ba module

Giả sử một ứng dụng thương mại điện tử được chia thành ba module:

```text
commerce/
├── settings.gradle
├── app/
│   └── build.gradle
├── domain/
│   └── build.gradle
└── infrastructure/
    ├── build.gradle
    └── libs/
        └── legacy-payment-sdk.jar
```

`settings.gradle`:

```groovy
rootProject.name = 'commerce'
include 'app', 'domain', 'infrastructure'
```

`domain/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
}
```

`infrastructure/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation project(':domain')
    implementation files('libs/legacy-payment-sdk.jar')
}
```

`app/build.gradle`:

```groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':domain')
    implementation project(':infrastructure')
}
```

Trong ví dụ này:

- `domain` sử dụng Jackson từ repository bên ngoài.
- `infrastructure` phụ thuộc vào `domain` và một JAR cục bộ.
- `app` phụ thuộc vào hai project nội bộ.
- Dependency giữa các project được Gradle quản lý trong cùng build.
- `legacy-payment-sdk.jar` là file dependency; nếu nó cần thư viện khác, nhóm phải khai báo các thư viện đó riêng hoặc chuyển SDK vào repository có metadata.

Sơ đồ quan hệ:

```text
app
 |\
 | +----> infrastructure ----> legacy-payment-sdk.jar
 |                |
 +----------------+
                  |
                  v
                domain ----> Jackson (repository)
```

Trong thực tế, cần tránh khai báo dependency trùng không cần thiết và chỉ để `app` phụ thuộc trực tiếp vào `domain` nếu mã nguồn `app` thực sự sử dụng API của `domain`. Dependency bắc cầu có thể khiến `domain` xuất hiện trên classpath thông qua `infrastructure`, nhưng khai báo trực tiếp đôi khi vẫn cần thiết để thể hiện đúng quan hệ sử dụng và tránh phụ thuộc vào implementation detail của module trung gian.

## 18. Quy trình chẩn đoán khi dependency không được giải quyết

Khi build báo không tìm thấy dependency hoặc ứng dụng thiếu lớp lúc chạy, hãy xác định lỗi thuộc loại nào:

1. **Xác định nguồn dependency.** Nó là artifact từ repository, project nội bộ hay file JAR cục bộ?
2. **Kiểm tra danh tính.** Tọa độ group/artifact/version, project path hoặc file path có đúng không?
3. **Kiểm tra repository.** Repository đã được khai báo ở đúng phạm vi chưa? Artifact có tồn tại và môi trường build có quyền truy cập không?
4. **Kiểm tra configuration/scope.** Dependency có mặt trên compile, runtime hay test classpath cần thiết không?
5. **Kiểm tra dependency bắc cầu.** Artifact có metadata không? Local JAR có cần thư viện bổ sung không?
6. **Xem dependency graph.** Phiên bản nào được chọn và dependency nào kéo nó vào?
7. **So sánh môi trường.** Máy cá nhân và CI có cùng repository, credential, file JAR và version catalog/POM không?

Với Gradle, bắt đầu bằng `dependencies` hoặc `dependencyInsight`. Với Maven, dùng `dependency:tree`. Những lệnh này giúp chuyển từ phỏng đoán sang bằng chứng về dependency graph thực tế.

## 19. Những nguyên tắc nên giữ khi khai báo dependency

- Dùng tọa độ và version rõ ràng cho dependency bên ngoài.
- Khai báo repository ở phạm vi được dự án quản lý thống nhất.
- Dùng project dependency cho module thuộc cùng build thay vì trỏ vào JAR build cũ.
- Chọn configuration/scope theo nơi thư viện thực sự được sử dụng.
- Chỉ dùng `api` khi dependency là một phần của compile API công khai.
- Hiểu rằng file JAR cục bộ không tự cung cấp metadata dependency bắc cầu như artifact repository.
- Tránh phụ thuộc vào JAR chỉ tồn tại trên máy của một thành viên.
- Quản lý version dùng chung bằng version catalog, platform/BOM hoặc `dependencyManagement` khi phù hợp.
- Kiểm tra dependency graph khi có xung đột hoặc lỗi runtime.
- Không dùng lệnh `import` trong Java để thay thế khai báo dependency của build tool.

Khi phân biệt rõ artifact bên ngoài, project nội bộ và JAR cục bộ, build script thể hiện chính xác nguồn gốc của thư viện. Build tool có thể giải quyết dependency, dựng classpath và sắp xếp công việc theo đúng quan hệ, còn nhóm phát triển có thể kiểm soát phiên bản và tái tạo môi trường build trên nhiều máy.
