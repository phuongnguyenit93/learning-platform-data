# Nguồn cấu hình: tệp dự án, dòng lệnh, môi trường và cấu hình người dùng

Một dự án Java thường cần nhiều giá trị cấu hình: phiên bản Java, địa chỉ dịch vụ, cổng ứng dụng, repository tải thư viện, proxy, tùy chọn compiler, profile phát triển và thông tin xác thực. Nếu mọi giá trị đều được ghi cố định trong mã nguồn hoặc tệp build, dự án sẽ khó dùng trên máy khác và dễ làm lộ thông tin riêng.

Build tool cung cấp nhiều nguồn cấu hình. Một số thuộc về chính dự án và được chia sẻ qua Git; một số chỉ dành cho một lần chạy; một số đến từ môi trường máy hoặc CI; một số được lưu trong hồ sơ người dùng trên từng máy.

Bài học này giải thích các nguồn cấu hình thường gặp, cách Maven và Gradle đọc chúng, cách truyền giá trị từ dòng lệnh hoặc biến môi trường, cách dùng cấu hình người dùng và cách kiểm soát thứ tự ưu tiên mà không làm mất tính tái lập của build.

## 1. Vì sao có nhiều nguồn cấu hình?

Không phải mọi giá trị đều có cùng phạm vi sử dụng.

Ví dụ, một dự án Java có thể cần:

- Phiên bản Java và plugin build mà cả nhóm phải dùng thống nhất.
- Địa chỉ database phát triển trên máy cá nhân.
- URL repository nội bộ chỉ có trong mạng công ty.
- Token để truy cập dịch vụ trong CI.
- Tùy chọn bật/tắt một nhóm test trong một lần chạy.
- Proxy và thư mục cache riêng của người dùng.

Nếu đưa tất cả vào cùng một tệp dự án, ta dễ gặp một số vấn đề:

- Máy cá nhân của mỗi thành viên có cấu hình khác nhau nhưng không rõ khác ở đâu.
- Giá trị chỉ dùng nội bộ bị commit lên Git.
- Thay đổi tạm thời cho một lần chạy lại làm bẩn cấu hình dự án.
- Build trên CI không có đủ thông tin vì phụ thuộc vào một thiết lập cục bộ.
- Người mới clone dự án không biết cần khai báo thêm giá trị nào.

Vì vậy, cần chọn nguồn cấu hình dựa trên phạm vi và vòng đời của giá trị đó.

## 2. Bốn nhóm nguồn cấu hình chính

### 2.1. Tệp cấu hình của dự án

Đây là các tệp được lưu cùng mã nguồn và thường được commit vào Git. Chúng mô tả những quy tắc mà cả nhóm cần chia sẻ, chẳng hạn:

- Phiên bản plugin hoặc build tool.
- Phiên bản Java mục tiêu.
- Dependency của ứng dụng.
- Cấu trúc module và source set.
- Các task hoặc lifecycle cần thực hiện.
- Giá trị mặc định không nhạy cảm.

Ví dụ, Maven dùng **pom.xml**; Gradle dùng **build.gradle** hoặc **build.gradle.kts**, cùng với **settings.gradle** hoặc **settings.gradle.kts** để cấu hình cấu trúc dự án.

Tệp dự án nên chứa các giá trị mặc định có thể chia sẻ. Nếu một giá trị thay đổi theo máy hoặc môi trường, nên cung cấp cơ chế ghi đè phù hợp.

### 2.2. Tham số dòng lệnh

Tham số dòng lệnh áp dụng cho một lần gọi build. Đây là cách thuận tiện để ghi đè giá trị mặc định hoặc yêu cầu build tool thực hiện một hành động cụ thể.

Ví dụ:

- Chọn profile Maven.
- Ghi đè một project property của Gradle.
- Bỏ qua test trong một lần chạy có chủ đích.
- Chọn tệp settings hoặc chế độ offline.
- Bật log chi tiết khi tìm lỗi.

Tham số dòng lệnh có thể được đưa vào script CI hoặc terminal mà không cần sửa tệp build. Tuy nhiên, nếu một tham số quan trọng được dùng thường xuyên, nhóm nên ghi rõ trong tài liệu hoặc đưa vào cấu hình pipeline để tránh mỗi người tự nhớ một lệnh khác nhau.

### 2.3. Biến môi trường

Biến môi trường được cung cấp bởi shell, hệ điều hành, container hoặc hệ thống CI. Chúng phù hợp với những giá trị phụ thuộc nơi chạy, chẳng hạn:

- Đường dẫn JDK.
- Thư mục cache hoặc home của build tool.
- Port ứng dụng.
- URL của dịch vụ.
- Token và mật khẩu được cấp qua secret store.

Biến môi trường có thể được đọc bởi build tool, plugin hoặc chính ứng dụng. Không phải biến môi trường nào cũng tự động trở thành project property; mỗi công cụ có quy tắc riêng.

### 2.4. Cấu hình người dùng hoặc cấu hình toàn máy

Đây là thiết lập được lưu ngoài repository, thường trong thư mục home của người dùng hoặc thư mục cài đặt công cụ. Ví dụ:

- Maven user settings trong **~/.m2/settings.xml**.
- Gradle user properties trong **~/.gradle/gradle.properties**.
- Cấu hình proxy.
- Repository mirror nội bộ.
- Thư mục cache và tùy chọn JVM.
- Thông tin xác thực cho repository riêng.

Cấu hình người dùng hữu ích khi một thiết lập chỉ liên quan đến máy hoặc tài khoản của một người. Thành viên khác không cần nhận bản sao tệp cá nhân đó qua Git.

## 3. Cách chọn nguồn cấu hình phù hợp

Một nguyên tắc dễ áp dụng:

| Loại giá trị | Nguồn thường phù hợp |
|---|---|
| Quy tắc build mà cả nhóm cần thống nhất | Tệp cấu hình dự án |
| Giá trị mặc định không nhạy cảm | Tệp cấu hình dự án |
| Ghi đè tạm thời cho một lần chạy | Dòng lệnh |
| Giá trị khác nhau giữa dev, test, staging và production | Biến môi trường hoặc profile môi trường |
| Token, mật khẩu, private key | Secret store hoặc biến môi trường được bảo vệ |
| Proxy và mirror riêng của người dùng | Cấu hình người dùng |
| Cache, thư mục home, JVM riêng của máy | Cấu hình người dùng hoặc biến môi trường |

Không nên đặt mật khẩu thật trong **pom.xml**, **build.gradle**, **gradle.properties** được commit hoặc script build được chia sẻ. Tệp dự án có thể chứa tên biến hoặc giá trị mặc định không nhạy cảm; giá trị bí mật được cấp lúc chạy từ môi trường an toàn.

## 4. Nguồn cấu hình trong Maven

Maven sử dụng một số tệp và cơ chế khác nhau. Các thành phần quan trọng gồm:

| Nguồn | Phạm vi | Nội dung thường dùng |
|---|---|---|
| **pom.xml** | Dự án | Dependency, plugin, build, profile và property của dự án |
| **.mvn/maven.config** | Dự án | Các tham số Maven mặc định cho repository |
| **.mvn/jvm.config** | Dự án | Tùy chọn JVM dùng để chạy Maven |
| **~/.m2/settings.xml** | Người dùng | Mirror, proxy, server credentials, local repository và profile người dùng |
| **Maven installation/conf/settings.xml** | Toàn bộ cài đặt Maven | Settings mặc định của bản cài |
| Dòng lệnh | Một lần chạy | Goal, phase, profile, system/user property và tùy chọn |
| Biến môi trường | Máy hoặc tiến trình | Java home, Maven home, thông tin môi trường và giá trị được POM tham chiếu |

### 4.1. pom.xml: cấu hình chia sẻ của dự án

POM mô tả dự án, dependency, plugin và các quy tắc build. Ví dụ:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>sample-app</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <app.port>8080</app.port>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

Trong ví dụ:

- **maven.compiler.release** xác định mức Java mà compiler nhắm đến khi plugin compiler được cấu hình theo property này.
- **app.port** là property tùy chỉnh của dự án.
- **project.build.sourceEncoding** khai báo encoding cho những plugin hỗ trợ property này.

Các giá trị này được chia sẻ cùng mã nguồn. Người phát triển có thể dùng mặc định 8080, còn CI hoặc môi trường chạy có thể cung cấp giá trị khác khi cần.

Để sử dụng property trong cấu hình plugin hoặc phần khác của POM, Maven hỗ trợ biểu thức nội suy dạng ${app.port}. Ví dụ cấu hình plugin có thể tham chiếu property thay vì lặp lại giá trị cố định.

### 4.2. Profile trong Maven

Profile cho phép chọn một nhóm cấu hình theo môi trường hoặc điều kiện. Profile có thể được khai báo trong POM hoặc trong settings.xml.

Ví dụ profile trong POM:

```xml
<profiles>
    <profile>
        <id>dev</id>
        <properties>
            <app.environment>development</app.environment>
            <app.port>8081</app.port>
        </properties>
    </profile>

    <profile>
        <id>production</id>
        <properties>
            <app.environment>production</app.environment>
            <app.port>8080</app.port>
        </properties>
    </profile>
</profiles>
```

Kích hoạt profile bằng dòng lệnh:

```bash
./mvnw -Pdev package
./mvnw -Pproduction verify
```

Trên Windows:

```powershell
.\mvnw.cmd -Pdev package
.\mvnw.cmd -Pproduction verify
```

Profile chỉ được kích hoạt khi điều kiện tương ứng được thỏa mãn. Ngoài kích hoạt bằng **-P**, Maven còn hỗ trợ kích hoạt theo JDK, hệ điều hành, property hoặc sự tồn tại của file. Profile activeByDefault cũng có quy tắc riêng: khi một profile khác trong cùng POM được kích hoạt, profile mặc định có thể không còn được kích hoạt.

Không nên xem profile là cơ chế lưu secret. Profile phù hợp với việc chọn cấu hình build; thông tin xác thực nên nằm trong settings hoặc secret store.

### 4.3. settings.xml: cấu hình người dùng và máy

Maven thường đọc settings từ hai vị trí:

- Settings toàn cục trong thư mục cài Maven, thường là **MAVEN_HOME/conf/settings.xml**.
- Settings của người dùng, thường là **~/.m2/settings.xml**.

Maven hợp nhất hai nguồn settings theo quy tắc của nó; settings người dùng có thể ghi đè các thiết lập toàn cục tương ứng. User settings phù hợp với thông tin riêng của từng máy hoặc tài khoản.

Một số nội dung thường đặt trong settings.xml:

- Mirror để chuyển yêu cầu tải dependency qua repository nội bộ.
- Proxy khi truy cập mạng.
- Server credentials cho repository yêu cầu xác thực.
- Local repository path.
- Profile chỉ dùng trên máy hoặc trong một môi trường nhất định.

Ví dụ cấu hình server:

```xml
<settings>
    <servers>
        <server>
            <id>internal-releases</id>
            <username>your-user</username>
            <password>value-from-secure-setup</password>
        </server>
    </servers>
</settings>
```

Giá trị minh họa không phải thông tin xác thực thật. Trong thực tế, hãy dùng cơ chế mã hóa hoặc secret management phù hợp của Maven và môi trường; không commit settings cá nhân có mật khẩu vào repository.

POM có thể khai báo repository với một id tương ứng. Maven dùng id đó để tìm cấu hình server credentials trong settings.xml. Điều này tách thông tin repository của dự án khỏi thông tin đăng nhập của người dùng.

### 4.4. Property từ dòng lệnh

Maven cho phép truyền user property bằng **-D**:

```bash
./mvnw -Dapp.port=9090 package
./mvnw -DskipTests=true package
```

Nếu POM hoặc plugin sử dụng property tương ứng, giá trị truyền từ dòng lệnh có thể ghi đè giá trị mặc định của dự án. Ví dụ **skipTests** là user property thường được Surefire Plugin hỗ trợ để bỏ qua việc chạy test trong một lần build.

Cần phân biệt **-D** với **-P**:

- **-Dname=value** đặt system/user property cho Maven và plugin.
- **-Pprofile** kích hoạt một hoặc nhiều Maven profile.

Chúng giải quyết hai nhu cầu khác nhau. Truyền một property không tự động kích hoạt profile có cùng tên.

Có thể chọn tệp settings khác cho một lần chạy:

```bash
./mvnw -s ./config/ci-settings.xml verify
```

Tùy chọn **-s** chọn user settings thay thế. Tùy chọn **-gs** chọn global settings thay thế. Không nên đưa file settings chứa credentials vào repository chỉ để tiện gọi lệnh; CI có thể tạo file settings tạm từ secret store.

### 4.5. Biến môi trường trong Maven

Maven cho phép tham chiếu biến môi trường từ POM bằng tiền tố **env.**. Ví dụ:

```xml
<properties>
    <app.port>${env.APP_PORT}</app.port>
</properties>
```

Khi shell hoặc CI cung cấp biến APP_PORT, Maven có thể nội suy giá trị đó cho property. Nếu biến không tồn tại, không nên giả định Maven tự chọn giá trị mặc định phù hợp; hãy cung cấp default rõ ràng trong cấu hình hoặc kiểm tra biến trước khi chạy.

Một số biến môi trường phổ biến:

| Biến | Vai trò |
|---|---|
| **JAVA_HOME** | Chỉ đến JDK/JRE mà Maven dùng để khởi chạy |
| **MAVEN_OPTS** | Tùy chọn JVM khi chạy Maven |
| **MAVEN_HOME** | Vị trí cài Maven trong một số môi trường |
| **M2_HOME** | Biến cũ vẫn có thể gặp trong môi trường hiện hữu |
| **APP_PORT** | Ví dụ biến riêng do ứng dụng hoặc pipeline định nghĩa |

Các biến riêng như APP_PORT không có ý nghĩa đặc biệt với Maven cho đến khi POM, plugin hoặc ứng dụng đọc chúng.

## 5. Nguồn cấu hình trong Gradle

Gradle cũng có nhiều lớp cấu hình, nhưng tên tệp và cách truyền property khác Maven.

| Nguồn | Phạm vi | Nội dung thường dùng |
|---|---|---|
| **settings.gradle(.kts)** | Dự án | Tên dự án, module và cấu hình settings |
| **build.gradle(.kts)** | Dự án | Plugin, dependency, task và quy tắc build |
| **gradle.properties** trong project | Dự án | Project properties và một số thiết lập Gradle |
| **GRADLE_USER_HOME/gradle.properties** | Người dùng | Property, proxy và tùy chọn riêng của máy |
| **Gradle installation/gradle.properties** | Cài đặt | Thiết lập cho bản Gradle cài đặt |
| Dòng lệnh | Một lần chạy | Project property, system property và task option |
| Biến môi trường | Máy hoặc tiến trình | Gradle home, Java home, project property và thông tin môi trường |

### 5.1. build.gradle: cấu hình build của dự án

Ví dụ build.gradle:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.test {
    useJUnitPlatform()
}
```

Tệp này mô tả plugin, dependency, repository và cách chạy test. Vì được lưu cùng dự án, những quy tắc này có thể được chia sẻ qua Git.

Cấu hình cấu trúc dự án như include module thường nằm trong **settings.gradle** hoặc **settings.gradle.kts**. Gradle đọc settings để xác định những project nào thuộc build, sau đó đọc build script của các project tương ứng.

### 5.2. gradle.properties

Gradle hỗ trợ tệp **gradle.properties** ở một số vị trí. Các vị trí thường gặp:

```text
my-project/
├── gradle.properties
├── settings.gradle
├── build.gradle
└── ...

User home:
~/.gradle/gradle.properties
```

- Tệp trong project root phù hợp với property có thể chia sẻ cùng repository.
- Tệp trong Gradle User Home phù hợp với property riêng của người dùng.
- Tệp trong thư mục cài đặt Gradle có thể cung cấp cấu hình ở phạm vi bản cài.

Nếu cùng một property được khai báo ở nhiều tệp gradle.properties, Gradle có quy tắc ưu tiên giữa các vị trí. User-level gradle.properties trong GRADLE_USER_HOME có độ ưu tiên cao hơn tệp ở project root; project root có độ ưu tiên cao hơn tệp trong Gradle installation. Property truyền trực tiếp qua dòng lệnh có thể ghi đè giá trị được khai báo trong tệp.

Ví dụ gradle.properties trong project:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.parallel=true
appPort=8080
```

Hai property đầu điều chỉnh cách Gradle chạy; appPort là project property mà build script có thể đọc.

Không nên đặt token hoặc mật khẩu thật trong tệp gradle.properties được commit. Nếu cần giá trị bí mật, dùng biến môi trường hoặc secret store.

### 5.3. Truyền project property bằng -P

Gradle hỗ trợ project property từ dòng lệnh bằng **-P**:

```bash
./gradlew -PappPort=9090 run
```

Trong build script Groovy, có thể đọc property bằng:

```groovy
def appPort = providers.gradleProperty('appPort').getOrElse('8080')

tasks.register('showAppPort') {
    doLast {
        println 'App port: ' + appPort
    }
}
```

Khi chạy:

```bash
./gradlew -PappPort=9090 showAppPort
```

giá trị 9090 được truyền cho lần build này. Nếu không có property, ví dụ dùng giá trị mặc định 8080.

Gradle cũng hỗ trợ project property qua system property có tiền tố **org.gradle.project.**:

```bash
./gradlew -Dorg.gradle.project.appPort=9090 run
```

Cách này khác với một system property tùy ý. Tiền tố org.gradle.project. cho Gradle biết system property đó cần được chuyển thành project property.

### 5.4. Đọc biến môi trường trong Gradle

Build script có thể đọc biến môi trường qua API providers. Ví dụ:

```groovy
def apiUrl = providers.environmentVariable('API_URL')
    .getOrElse('http://localhost:8080')

tasks.register('showApiUrl') {
    doLast {
        println 'API URL: ' + apiUrl
    }
}
```

Nếu biến API_URL có mặt, script dùng giá trị đó; nếu không, dùng địa chỉ local mặc định.

Gradle cũng hỗ trợ quy ước biến môi trường **ORG_GRADLE_PROJECT_name** để cung cấp project property. Ví dụ, biến:

```text
ORG_GRADLE_PROJECT_appPort=9090
```

có thể được đọc như project property **appPort**. Cơ chế này hữu ích trong CI vì pipeline có thể cấp property mà không cần ghi nó vào tệp dự án.

Các biến môi trường thường gặp khác:

| Biến | Vai trò |
|---|---|
| **JAVA_HOME** | Chỉ đến Java installation được dùng khi khởi chạy Gradle |
| **GRADLE_USER_HOME** | Thay đổi thư mục user home của Gradle |
| **GRADLE_OPTS** | Tùy chọn JVM cho tiến trình Gradle client |
| **ORG_GRADLE_PROJECT_name** | Cung cấp project property tên name |
| **CI** | Thường được hệ thống CI đặt để báo build đang chạy trong môi trường CI; không phải property đặc biệt của mọi plugin |

### 5.5. Cấu hình JVM và system property

Gradle phân biệt project property với JVM system property. Ví dụ:

- **-PappPort=9090** đặt project property appPort.
- **-Dorg.gradle.project.appPort=9090** đặt project property qua system property có tiền tố đặc biệt.
- **-Dfile.encoding=UTF-8** truyền system property cho JVM theo cách Gradle hỗ trợ.
- **org.gradle.jvmargs** trong gradle.properties cấu hình JVM dùng cho Gradle daemon.

Nếu một giá trị được dùng bởi build script, hãy chọn project property hoặc provider API phù hợp. Nếu nó điều chỉnh JVM, hãy dùng cơ chế JVM tương ứng. Không nên nhầm hai loại property chỉ vì cả hai đều có thể được truyền bằng tùy chọn dòng lệnh.

## 6. Thứ tự ưu tiên và cách ghi đè cấu hình

Nhiều nguồn có thể cung cấp cùng một giá trị. Khi đó, build tool cần có quy tắc để quyết định giá trị hiệu lực.

Tuy nhiên, **không có một thứ tự ưu tiên duy nhất áp dụng cho mọi loại cấu hình của cả Maven và Gradle**. Profile, system property, project property, biến môi trường, settings và JVM option là các cơ chế khác nhau. Cần xét đúng loại property và đúng công cụ.

### 6.1. Nguyên tắc thực tế

Có thể dùng quy ước thiết kế sau cho dự án:

1. Tệp dự án cung cấp giá trị mặc định không nhạy cảm.
2. Cấu hình người dùng cung cấp thiết lập riêng của máy như proxy, mirror hoặc cache.
3. Môi trường cung cấp giá trị phụ thuộc nơi chạy và secret.
4. Dòng lệnh ghi đè tạm thời khi cần thử nghiệm hoặc chẩn đoán.

Đây là quy ước tổ chức cấu hình để dễ hiểu và bảo trì, không phải tuyên bố rằng mọi property của Maven hay Gradle luôn tuân theo chính xác thứ tự này.

### 6.2. Một số quy tắc cụ thể trong Gradle

Đối với các tệp **gradle.properties**, Gradle tìm cấu hình ở user home, project root và thư mục cài đặt; user home có độ ưu tiên cao hơn project root, và project root cao hơn Gradle installation.

Đối với project property, Gradle hỗ trợ nhiều cách cung cấp như:

- Tùy chọn dòng lệnh **-Pname=value**.
- System property **-Dorg.gradle.project.name=value**.
- Biến môi trường **ORG_GRADLE_PROJECT_name**.
- Property trong gradle.properties.

Khi cần xác định giá trị nào đang có hiệu lực, hãy xem loại property, nguồn cụ thể và tài liệu của phiên bản Gradle đang dùng. Nếu một giá trị quan trọng bị ghi đè ngoài ý muốn, kiểm tra cả tệp gradle.properties trong project lẫn tệp trong GRADLE_USER_HOME.

### 6.3. Một số quy tắc cụ thể trong Maven

Trong Maven:

- POM xác định cấu hình dự án.
- Settings toàn cục và settings người dùng được hợp nhất; user settings có thể ghi đè thiết lập toàn cục tương ứng.
- Profile được kích hoạt theo điều kiện hoặc qua **-P**.
- User property truyền qua **-D** có thể được plugin hoặc biểu thức POM dùng để ghi đè giá trị mặc định.
- Environment variable chỉ được dùng khi POM, plugin hoặc ứng dụng tham chiếu nó; không phải mọi biến đều tự động ghi đè mọi property.

Nếu một giá trị xuất hiện trong POM, profile và command line, cần xem property đó được Maven model, plugin hay ứng dụng tiêu thụ như thế nào. Không nên áp dụng máy móc một thứ tự ưu tiên từ Gradle sang Maven.

## 7. Ví dụ: cùng một dự án, nhiều môi trường

Giả sử ứng dụng có property app.port và app.environment.

Giá trị mặc định trong POM hoặc build script:

- Port: 8080.
- Environment: development.

Trên máy cá nhân, lập trình viên có thể đổi port để tránh trùng với ứng dụng khác. Trong CI, pipeline có thể cung cấp URL dịch vụ và token. Trong production, hệ thống triển khai cấp cấu hình riêng.

Một bảng phân chia có thể là:

| Giá trị | Local development | CI | Production |
|---|---|---|---|
| Java toolchain | Theo cấu hình dự án | Cùng phiên bản được yêu cầu | Theo runtime được hỗ trợ |
| Port | 8081 | Có thể không cần mở port cố định | Do môi trường cấp |
| API URL | Local hoặc mock server | Endpoint test | Endpoint production |
| Repository mirror | Cấu hình người dùng | Mirror của CI | Không cần cho runtime |
| Access token | Không dùng hoặc token local | Secret của CI | Secret của hệ thống triển khai |
| Log level | DEBUG | INFO | INFO/WARN |

Điểm quan trọng là build artifact nên được tạo theo quy tắc rõ ràng, còn giá trị môi trường cần thiết có thể được cung cấp lúc chạy. Không nên tạo một artifact khác nhau chỉ để thay đổi một URL hoặc token nếu ứng dụng có thể nhận cấu hình từ môi trường một cách an toàn.

## 8. Ví dụ: chạy cùng một lệnh với cấu hình khác nhau

### 8.1. Gradle

Giả sử build.gradle có:

```groovy
def appPort = providers.gradleProperty('appPort')
    .orElse(providers.environmentVariable('APP_PORT'))
    .getOrElse('8080')

tasks.register('showConfig') {
    doLast {
        println 'Effective app port: ' + appPort
    }
}
```

Có thể chạy với mặc định:

```bash
./gradlew showConfig
```

Truyền project property trực tiếp:

```bash
./gradlew -PappPort=9090 showConfig
```

Hoặc cung cấp biến môi trường:

```bash
APP_PORT=7070 ./gradlew showConfig
```

Trên Windows PowerShell:

```powershell
$env:APP_PORT = '7070'
.\gradlew.bat showConfig
Remove-Item Env:APP_PORT
```

Trong ví dụ này, build script chủ động chọn thứ tự đọc giá trị: project property trước, biến môi trường sau, cuối cùng là mặc định. Đây là logic do chính build script định nghĩa, vì vậy người đọc có thể hiểu rõ giá trị nào thắng trong ví dụ này.

### 8.2. Maven

Trong POM, có thể khai báo property mặc định:

```xml
<properties>
    <app.port>8080</app.port>
</properties>
```

Nếu plugin hoặc cấu hình sử dụng property đó, có thể truyền giá trị khác:

```bash
./mvnw -Dapp.port=9090 package
```

Để đọc biến môi trường, POM có thể tham chiếu:

```xml
<properties>
    <app.port>${"$" + "{env.APP_PORT}"}</app.port>
</properties>
```

Maven sẽ nội suy biến môi trường APP_PORT nếu có. Nếu muốn có fallback, hãy định nghĩa profile hoặc cơ chế mặc định phù hợp và kiểm tra giá trị hiệu lực trong build; không nên giả định biểu thức env tự động có default.

## 9. Cấu hình người dùng và repository nội bộ

Trong một nhóm phát triển, các máy có thể cần truy cập cùng một repository dependency nhưng đi qua proxy hoặc mirror khác nhau.

Maven thường cấu hình mirror, proxy và server credentials trong settings.xml. Gradle có thể sử dụng repository được khai báo trong build script hoặc settings, còn proxy và một số tùy chọn có thể được đặt trong gradle.properties của user home hoặc JVM system properties.

Ví dụ, một thành viên có thể cần proxy để truy cập Internet; thành viên khác không cần. Đây là cấu hình theo máy và không nên bắt buộc mọi người phải commit cùng một proxy vào project.

Ngược lại, nếu dự án bắt buộc dùng một repository nội bộ để đảm bảo dependency được phân phối thống nhất, nhóm cần ghi rõ cách cấu hình repository và cung cấp hướng dẫn hoặc mirror phù hợp cho CI.

Không nên đặt credentials trực tiếp trong URL repository hoặc build script. Với Maven, dùng server id trong settings.xml. Với Gradle, đọc credentials từ environment variable hoặc secret provider và chỉ sử dụng chúng trong task cần truy cập repository.

## 10. Cấu hình JVM và cấu hình ứng dụng là hai lớp khác nhau

Một lỗi thường gặp là nhầm tùy chọn của build tool với cấu hình ứng dụng.

Ví dụ:

- JAVA_HOME chọn Java installation dùng để khởi chạy công cụ.
- GRADLE_OPTS hoặc MAVEN_OPTS truyền tùy chọn JVM cho tiến trình build tool.
- org.gradle.jvmargs điều chỉnh JVM của Gradle daemon.
- -PappPort=9090 truyền project property cho build script.
- APP_PORT có thể được ứng dụng đọc khi khởi chạy.
- -Dapp.mode=dev có thể là system property mà ứng dụng đọc bằng System.getProperty, tùy cách truyền đến tiến trình ứng dụng.

Một giá trị có thể cần được chuyển tiếp từ build tool sang tiến trình ứng dụng. Việc đặt property cho Gradle không tự động làm cho ứng dụng Java nhìn thấy cùng property đó. Ví dụ, project property **appPort** trong Gradle chỉ có sẵn cho build script cho đến khi task run được cấu hình truyền giá trị đó vào process environment hoặc JVM arguments.

Tương tự, Maven user property truyền vào Maven không mặc nhiên trở thành biến môi trường trong tiến trình Java do plugin khởi chạy. Cần cấu hình plugin để chuyển tiếp giá trị đúng cách.

## 11. Cách tìm cấu hình đang có hiệu lực

Khi build cho kết quả khác nhau giữa hai máy, hãy xác định nguồn cấu hình thực tế thay vì sửa ngẫu nhiên nhiều tệp.

### 11.1. Với Maven

Một số lệnh hữu ích:

```bash
./mvnw -v
./mvnw help:active-profiles
./mvnw help:effective-pom
./mvnw help:effective-settings
```

- **-v** cho biết Maven và Java đang dùng.
- **help:active-profiles** cho biết profile nào đang được kích hoạt.
- **help:effective-pom** hiển thị POM sau khi kế thừa và hợp nhất cấu hình.
- **help:effective-settings** hiển thị settings hiệu lực sau khi hợp nhất.

Các goal help yêu cầu Maven Help Plugin có thể tải được. Kết quả effective settings hoặc POM có thể chứa đường dẫn nội bộ hoặc thông tin không nên chia sẻ công khai; hãy xem và che thông tin nhạy cảm trước khi gửi log.

### 11.2. Với Gradle

Một số lệnh hữu ích:

```bash
./gradlew --version
./gradlew properties
./gradlew tasks --all
```

- **--version** cho biết phiên bản Gradle và JVM đang chạy.
- **properties** hiển thị các property của project.
- **tasks --all** liệt kê task, kể cả task không nằm trong nhóm mặc định.

Lệnh properties có thể hiển thị giá trị mà nhóm không muốn đưa vào log. Không nên chạy hoặc chia sẻ đầu ra chứa secret trên hệ thống công khai. Nếu cần chẩn đoán một giá trị cụ thể, hãy viết task nhỏ chỉ in giá trị không nhạy cảm hoặc chỉ xác nhận biến có tồn tại.

### 11.3. So sánh môi trường

Khi hai máy cho kết quả khác nhau, ghi lại tối thiểu:

- Phiên bản Maven hoặc Gradle từ wrapper.
- Phiên bản Java đang chạy build tool.
- Phiên bản JDK/toolchain dùng để biên dịch.
- Profile hoặc project property đang được truyền.
- Các biến môi trường liên quan.
- User settings hoặc user gradle.properties có ảnh hưởng.
- Repository mirror và dependency cache nếu lỗi liên quan đến tải thư viện.

Không cần thu thập toàn bộ biến môi trường của máy vì chúng có thể chứa secret. Chỉ kiểm tra những biến có liên quan trực tiếp đến build.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Máy cá nhân build được nhưng CI thất bại | CI thiếu biến môi trường hoặc user settings mà máy cá nhân có | Liệt kê rõ biến và cấu hình cần thiết; cung cấp qua CI secret hoặc cấu hình pipeline |
| Gradle dùng giá trị property khác mong đợi | gradle.properties trong user home ghi đè project property | Kiểm tra GRADLE_USER_HOME và nguồn property được đọc |
| Maven tải dependency từ repository khác | Mirror hoặc profile trong settings.xml đang được kích hoạt | Kiểm tra user/global settings và effective settings |
| Profile Maven không được kích hoạt | Sai id, điều kiện activation không thỏa mãn hoặc thiếu -P | Kiểm tra active profiles và lệnh gọi Maven |
| Ứng dụng không nhận được project property | Property chỉ tồn tại trong build script, chưa truyền sang tiến trình ứng dụng | Cấu hình task run hoặc plugin để chuyển tiếp qua argument, system property hoặc environment |
| Secret xuất hiện trong Git hoặc log | Giá trị bí mật được ghi vào tệp dự án hoặc in ra log | Xóa secret khỏi cấu hình chia sẻ, thu hồi/đổi secret đã lộ và dùng secret store |
| Máy dùng JDK khác nhau | JAVA_HOME hoặc cấu hình toolchain khác nhau | Xác định JDK cần dùng và cấu hình toolchain/CI rõ ràng |
| Thay đổi một tệp cấu hình nhưng kết quả không đổi | Nguồn khác có độ ưu tiên cao hơn hoặc property không được đọc | Kiểm tra effective configuration và tên property chính xác |

## 13. Nguyên tắc tổ chức cấu hình dễ bảo trì

### Giữ giá trị mặc định trong dự án

Những gì cả nhóm cần biết và cần tái tạo nên được mô tả trong repository. Ví dụ: phiên bản plugin, Java release, dependency và cấu trúc build.

### Để giá trị riêng của máy ở user configuration

Proxy, mirror cá nhân, cache và đường dẫn riêng thường thuộc cấu hình người dùng. Tránh yêu cầu mọi thành viên sửa tệp dự án chỉ để phù hợp máy của họ.

### Đưa secret qua kênh an toàn

Không commit mật khẩu, token hoặc private key. Dùng biến môi trường được bảo vệ, CI secret hoặc secret manager của môi trường chạy.

### Ghi rõ các biến bắt buộc

README nên liệt kê tên biến, ý nghĩa, ví dụ giá trị giả và cách cấu hình trên hệ điều hành cần hỗ trợ. Không đưa giá trị bí mật thật vào ví dụ.

### Chọn tên property nhất quán

Dùng tên rõ ràng như appPort, apiUrl hoặc APP_PORT. Tránh nhiều tên gần giống nhau cho cùng một ý nghĩa giữa POM, build script, pipeline và ứng dụng.

### Không phụ thuộc vào cấu hình ngầm

Nếu build chỉ thành công khi một tệp cá nhân tồn tại, hãy ghi rõ điều kiện đó hoặc chuyển thiết lập cần thiết vào quy trình chuẩn. Build CI nên tái tạo được từ repository và các biến đầu vào đã khai báo.

### Tránh ghi đè cùng một giá trị ở quá nhiều nơi

Nếu appPort xuất hiện trong POM, profile, environment, user settings và command line mà không có quy ước rõ, người đọc khó biết giá trị nào được sử dụng. Hãy xác định một nguồn mặc định và các nguồn ghi đè có chủ đích.

## 14. Ghi nhớ

- Tệp dự án chứa quy tắc build và giá trị mặc định có thể chia sẻ.
- Dòng lệnh phù hợp với ghi đè hoặc lựa chọn cho một lần chạy.
- Biến môi trường phù hợp với giá trị phụ thuộc môi trường và secret được cấp an toàn.
- Cấu hình người dùng phù hợp với proxy, mirror, cache và thiết lập riêng của máy.
- Maven dùng POM, profile, settings.xml, user properties và environment interpolation.
- Gradle dùng build/settings script, gradle.properties, project properties, system properties và environment variables.
- Maven -D đặt property; -P kích hoạt profile.
- Gradle -P đặt project property; ORG_GRADLE_PROJECT_name cung cấp project property qua môi trường.
- Cấu hình người dùng có thể làm kết quả khác với cấu hình trong repository.
- Không có một thứ tự ưu tiên duy nhất cho mọi loại cấu hình; cần xét cơ chế cụ thể của từng công cụ.
- Build tool property không tự động trở thành cấu hình của tiến trình ứng dụng.
- Secret không được ghi vào tệp chia sẻ hoặc log công khai.

## 15. Tự kiểm tra

1. Vì sao không nên đặt mọi cấu hình của dự án trong một tệp duy nhất?
2. Khi nào nên dùng tệp cấu hình dự án, dòng lệnh, biến môi trường và cấu hình người dùng?
3. Maven dùng POM và settings.xml cho những mục đích khác nhau nào?
4. Maven -D khác -P như thế nào?
5. Gradle đọc project property từ -P và ORG_GRADLE_PROJECT_name ra sao?
6. Vì sao gradle.properties trong user home có thể làm kết quả khác với máy khác?
7. Tại sao settings.xml của Maven không nên chứa credentials thật trong repository?
8. Vì sao một Gradle project property không tự động xuất hiện trong System.getenv của ứng dụng?
9. Khi CI build thất bại vì thiếu cấu hình, nên kiểm tra những nguồn nào?
10. Vì sao không thể áp dụng một thứ tự ưu tiên duy nhất cho mọi property của Maven và Gradle?

Khi có thể xác định một giá trị nên nằm trong tệp dự án, dòng lệnh, biến môi trường hay cấu hình người dùng, đồng thời biết cách kiểm tra giá trị hiệu lực của Maven và Gradle, bạn đã nắm được nền tảng quản lý nguồn cấu hình trong quy trình build.

