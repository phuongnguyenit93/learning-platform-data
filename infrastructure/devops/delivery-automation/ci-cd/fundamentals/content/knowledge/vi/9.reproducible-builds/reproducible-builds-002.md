# Sử dụng wrapper và toolchain để giảm khác biệt môi trường

Một dự án Java có thể build thành công trên máy của lập trình viên nhưng thất bại trên CI chỉ vì hai nơi đang dùng phiên bản Gradle, Maven hoặc JDK khác nhau. Một máy có thể vô tình dùng Gradle cài toàn cục, JDK mới hơn và cấu hình Maven cá nhân; runner lại dùng một bộ công cụ khác. Khi đó, lỗi biên dịch, khác biệt plugin hoặc thay đổi hành vi của công cụ có thể xuất hiện dù mã nguồn không đổi.

Wrapper và toolchain giúp dự án mô tả rõ công cụ cần dùng. Wrapper cố định phiên bản build tool được dự án sử dụng; toolchain chọn bộ công cụ thực hiện những tác vụ như biên dịch và kiểm thử. Khi kết hợp chúng với dependency được khóa phiên bản và môi trường CI nhất quán, nhóm giảm được nhiều khác biệt giữa máy cá nhân và máy build.

Hai cơ chế này giải quyết các lớp khác nhau. Gradle Wrapper hoặc Maven Wrapper không tự cố định JDK. Java toolchain cũng không tự cố định phiên bản Gradle, Maven, hệ điều hành, thư viện phụ thuộc hay mọi biến môi trường. Muốn build đáng tin cậy, cần xác định rõ từng lớp và kiểm soát chúng theo mức độ cần thiết.

## 1. Nhìn đúng các lớp của môi trường build

Một build Java thường phụ thuộc vào nhiều thành phần:

| Lớp | Ví dụ | Cách kiểm soát thường dùng |
|---|---|---|
| Build tool | Gradle 8.x, Maven 3.x | Wrapper và phiên bản được khai báo trong repository |
| JDK chạy build tool | JVM khởi chạy Gradle hoặc Maven | JDK được cài trong môi trường, image CI hoặc cấu hình JVM |
| JDK thực hiện tác vụ | Compiler, test launcher, Javadoc | Java toolchain hoặc Maven Toolchains |
| Plugin build | Gradle plugin, Maven plugin | Khai báo phiên bản rõ ràng và quản lý dependency |
| Thư viện phụ thuộc | JAR, BOM, dependency bắc cầu | Dependency locking, checksum hoặc verification |
| Hệ điều hành và kiến trúc | Linux x64, Windows ARM64 | Container/image và runner được chuẩn hóa |
| Cấu hình môi trường | Locale, timezone, biến môi trường, encoding | Khai báo mặc định rõ và truyền cấu hình có kiểm soát |

Có thể hình dung chuỗi công cụ như sau:

~~~text
Git checkout
    |
    v
Wrapper trong repository
    |
    v
Phiên bản Gradle hoặc Maven đã khai báo
    |
    +---- JVM chạy build tool
    |
    v
Java toolchain được chọn
    |
    v
Compiler / Test / Javadoc
    |
    v
Dependency và plugin đã được phân giải
    |
    v
Artifact build
~~~

Nếu một lớp không được kiểm soát, hai máy vẫn có thể tạo kết quả khác nhau. Ví dụ, cùng dùng Gradle 8 nhưng một máy dùng JDK 17 và máy khác dùng JDK 21 để chạy build tool; hoặc cùng dùng JDK 17 nhưng dependency được phân giải ở hai thời điểm khác nhau.

## 2. Wrapper bảo đảm build tool nhất quán

### Vì sao nên dùng wrapper?

Wrapper là script đi kèm repository để gọi đúng phiên bản build tool mà dự án yêu cầu. Thành viên nhóm và CI không cần cài sẵn đúng phiên bản Gradle hoặc Maven toàn cục. Nếu bản phân phối chưa có trong máy, wrapper có thể tải về theo cấu hình của dự án rồi khởi chạy.

Với Gradle, các file thường được commit gồm:

- gradlew: script chạy trên Unix-like.
- gradlew.bat: script chạy trên Windows.
- gradle/wrapper/gradle-wrapper.jar: chương trình wrapper.
- gradle/wrapper/gradle-wrapper.properties: phiên bản và nguồn phân phối Gradle.

Với Maven Wrapper, repository thường có:

- mvnw và mvnw.cmd: script chạy trên Unix-like và Windows.
- .mvn/wrapper/maven-wrapper.properties: cấu hình bản phân phối Maven.
- Các file wrapper bổ trợ tùy kiểu wrapper được tạo.

Commit các file wrapper cần thiết cùng mã nguồn. Thành viên nhóm nên chạy wrapper của repository thay vì gọi gradle hoặc mvn toàn cục. Điều này làm cho lệnh build trong tài liệu, máy cá nhân và CI nhất quán hơn.

### Gradle Wrapper

Trong file gradle/wrapper/gradle-wrapper.properties, thuộc tính distributionUrl chỉ rõ bản phân phối Gradle:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
distributionSha256Sum=REPLACE_WITH_VERIFIED_SHA256
~~~

Ví dụ sử dụng Gradle 8.10.2. Giá trị checksum minh họa cần được thay bằng SHA-256 chính thức của đúng file phân phối đã chọn trước khi áp dụng. Không chép một checksum không được xác minh hoặc để placeholder trong cấu hình phát hành.

distributionSha256Sum cho phép wrapper kiểm tra nội dung file phân phối sau khi tải. Nó giúp phát hiện file tải về không khớp với giá trị đã tin cậy. Checksum cần lấy từ nguồn phân phối đáng tin cậy và được review cùng thay đổi nâng phiên bản.

Chạy lệnh qua wrapper:

~~~bash
# Linux hoặc macOS
./gradlew clean build

# Windows
gradlew.bat clean build
~~~

Nếu cần nâng Gradle, dùng một phiên bản Gradle đã được dự án chấp thuận để cập nhật wrapper, sau đó review các file wrapper thay đổi và chạy lại build:

~~~bash
./gradlew wrapper --gradle-version 8.10.2
./gradlew wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

Lệnh wrapper có thể được chạy hai lần trong một số quy trình nâng cấp để cập nhật cả cấu hình và các file wrapper theo phiên bản mới. Hãy xem diff thực tế, kiểm tra script và wrapper JAR, rồi chạy lại lệnh bằng wrapper vừa cập nhật.

### Maven Wrapper

Trong file .mvn/wrapper/maven-wrapper.properties, khai báo URL bản phân phối Maven:

~~~properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
wrapperUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.3.2/maven-wrapper-3.3.2.jar
~~~

Đây là ví dụ chọn Maven 3.9.9 và wrapper JAR 3.3.2. Tên thuộc tính và file được sinh ra có thể phụ thuộc kiểu Maven Wrapper đã chọn. Nếu cấu hình hỗ trợ checksum cho bản phân phối, hãy khai báo checksum chính thức tương ứng và xác minh theo tài liệu của phiên bản wrapper đang dùng.

Chạy lệnh qua Maven Wrapper:

~~~bash
# Linux hoặc macOS
./mvnw clean verify

# Windows
mvnw.cmd clean verify
~~~

Có thể tạo hoặc cập nhật wrapper bằng một bản Maven đã được nhóm chấp thuận:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Sau khi tạo wrapper, commit các file cần thiết và xác minh lệnh mvnw hoạt động trên môi trường sạch. Không yêu cầu thành viên cài một bản Maven toàn cục rồi mới chạy dự án.

### Wrapper không thay thế kiểm soát bảo mật

Wrapper có khả năng tải và thực thi build tool. Vì vậy, các file wrapper là một phần của chuỗi cung ứng phần mềm và cần được review như mã nguồn:

- Lấy script, JAR và bản phân phối từ nguồn đáng tin cậy.
- Kiểm tra checksum của bản phân phối khi cơ chế hỗ trợ.
- Review thay đổi URL, phiên bản và wrapper JAR.
- Không chạy wrapper từ repository chưa tin cậy trong môi trường có secret hoặc quyền ghi rộng.
- Cập nhật wrapper có chủ đích, không tự động nhận phiên bản mới nhất trong mỗi lần build.

## 3. Toolchain chọn JDK cho tác vụ build

### Phân biệt JDK chạy build tool và JDK thực hiện tác vụ

Gradle hoặc Maven bản thân cũng chạy trên một JVM. JVM này có thể khác với JDK được dùng để biên dịch mã nguồn hoặc chạy test.

Ví dụ, Gradle có thể chạy trên JDK 21 nhưng dùng Java toolchain 17 để biên dịch và kiểm thử dự án. Điều đó chỉ hợp lệ khi phiên bản Gradle đang dùng hỗ trợ JDK 21 làm JVM chạy Gradle. Ngược lại, một dự án có thể cần biên dịch bằng JDK 21 nhưng build tool vẫn được chạy trên JDK 17 nếu phiên bản build tool hỗ trợ cấu hình đó.

Đừng nhầm thuộc tính source/target hoặc release với việc chọn JDK thực thi. Việc yêu cầu bytecode tương thích Java 17 không tự chứng minh compiler và test đang chạy bằng đúng JDK 17.

### Gradle Java Toolchains

Với dự án Gradle dùng Kotlin DSL, có thể khai báo toolchain trong build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Với Groovy DSL, cấu hình tương đương trong build.gradle:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Khai báo này yêu cầu Gradle chọn JDK có phiên bản ngôn ngữ 17 cho các tác vụ Java hỗ trợ toolchain, chẳng hạn biên dịch và test. Gradle tìm trong các JDK đã cài đặt; việc tự tải JDK phụ thuộc cấu hình resolver và môi trường. Không nên giả định chỉ thêm toolchain là mọi máy tự có JDK phù hợp.

Có thể kiểm tra toolchain Gradle phát hiện được bằng:

~~~bash
./gradlew -q javaToolchains
./gradlew --version
~~~

Lệnh đầu tiên hiển thị các Java toolchain mà Gradle phát hiện. Lệnh thứ hai cho biết phiên bản Gradle và JVM đang chạy Gradle. Hai kết quả này trả lời hai câu hỏi khác nhau.

Nếu cần chỉ định vendor hoặc implementation, có thể bổ sung tiêu chí vào toolchain. Chỉ thêm tiêu chí khi dự án thực sự cần đặc tính riêng của nhà cung cấp hoặc runtime; nếu không, yêu cầu quá hẹp có thể khiến build không tìm được JDK trên runner.

### Tự động cấp phát JDK

Gradle có thể tự động tải JDK phù hợp khi dự án được cấu hình Java toolchain resolver. Khả năng này phụ thuộc plugin resolver, repository phân phối và chính sách mạng của môi trường. Trong CI, nên quyết định rõ JDK được cài trước trong image hay được cấp phát bởi Gradle.

Nếu dùng resolver, cần kiểm soát nguồn tải, phiên bản và khả năng truy cập. Nếu dùng JDK cài sẵn, pipeline nên xác minh phiên bản trước khi chạy build. Hai cách đều có thể dùng được; điều quan trọng là kết quả chọn JDK phải có thể quan sát và lặp lại.

### JVM chạy Gradle daemon

Java toolchain không nhất thiết quyết định JVM chạy Gradle daemon. JVM của Gradle có thể được chọn bởi JAVA_HOME, cấu hình daemon hoặc môi trường khởi chạy. Thuộc tính org.gradle.java.home có thể ảnh hưởng JVM chạy Gradle, nhưng không thay thế khai báo Java toolchain cho compiler/test.

Khi điều tra lỗi, ghi nhận cả:

- Phiên bản Gradle và JVM đang chạy Gradle.
- JDK toolchain được chọn cho compile.
- JDK toolchain được chọn cho test.
- Các tùy chọn JVM và tham số compiler liên quan.

## 4. Maven Toolchains

Maven Wrapper cố định phiên bản Maven, còn Maven Toolchains cho phép plugin sử dụng một JDK khác với JVM đang chạy Maven.

### Khai báo JDK cục bộ

Maven thường đọc danh sách toolchain từ file cấu hình người dùng như ~/.m2/toolchains.xml. File này trỏ đến JDK đã cài trên máy và không nên chứa đường dẫn riêng của một lập trình viên trong repository.

Ví dụ cấu hình cho JDK 17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/temurin-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Đường dẫn /opt/jdks/temurin-17 chỉ là ví dụ trên một máy Linux. Mỗi môi trường cần ánh xạ đến JDK 17 đã được cài đặt tại đó. Không commit file toolchains.xml chứa đường dẫn máy cá nhân vào repository.

### Yêu cầu toolchain trong pom.xml

Có thể dùng Maven Toolchains Plugin để chọn JDK phù hợp:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-toolchains-plugin</artifactId>
      <version>3.2.0</version>
      <executions>
        <execution>
          <goals>
            <goal>toolchain</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <toolchains>
          <jdk>
            <version>17</version>
          </jdk>
        </toolchains>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Khi chạy, Maven tìm một JDK đáp ứng yêu cầu trong danh sách toolchain đã cấu hình. Compiler plugin và các plugin hỗ trợ Maven Toolchains có thể sử dụng JDK được chọn. Cần xác minh các plugin thực tế trong dự án có hỗ trợ toolchain; không phải plugin nào cũng tự động dùng JDK này.

### Chọn JDK trong CI

Trong CI, cài JDK cần thiết trước khi gọi Maven Wrapper và cung cấp toolchain tương ứng. Ví dụ với một runner Linux đã có JDK 17 tại đường dẫn do hệ thống cấp:

~~~bash
export JAVA_HOME=/opt/jdks/temurin-17
export PATH="$JAVA_HOME/bin:$PATH"

java -version
./mvnw -version
./mvnw -B clean verify
~~~

Nếu Maven chạy bằng chính JDK 17 và compiler plugin dùng cùng JDK, cấu hình có thể đơn giản hơn. Khi muốn tách JVM chạy Maven và JDK thực hiện tác vụ, khai báo toolchain và cung cấp file toolchains.xml phù hợp trong CI.

## 5. Đặt yêu cầu phiên bản rõ ràng

Wrapper và toolchain phát huy tác dụng khi dự án có một chính sách phiên bản rõ:

| Thành phần | Câu hỏi cần trả lời | Ví dụ cách khai báo |
|---|---|---|
| Gradle hoặc Maven | Dự án dùng phiên bản build tool nào? | distributionUrl trong wrapper properties |
| JDK chạy build tool | Build tool được khởi chạy bằng JVM nào? | JAVA_HOME hoặc image CI |
| JDK compile/test | Compiler và test dùng JDK nào? | Gradle Java toolchain hoặc Maven Toolchains |
| Plugin | Phiên bản plugin nào được phép? | Version cụ thể trong build script hoặc pom.xml |
| Dependency | Phiên bản thư viện có thay đổi ngoài ý muốn không? | Dependency lock và version constraint rõ ràng |
| Container | Hệ điều hành và công cụ hệ thống nào? | Image có tag bất biến hoặc digest |

Không nên dùng phiên bản động như latest hoặc một dải không có giới hạn trong những thành phần ảnh hưởng trực tiếp đến kết quả build. Khi nâng phiên bản, tạo thay đổi riêng, xem release note, chạy kiểm thử và cập nhật tài liệu môi trường.

### Phiên bản Java và mức tương thích bytecode

Ngoài việc chọn JDK, dự án cần xác định mức Java mà mã được phép sử dụng và bytecode được tạo ra. Với Gradle, có thể dùng options.release:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Toolchain chọn JDK thực hiện compile; release đặt giới hạn API và bytecode mục tiêu mà compiler được yêu cầu tạo ra. Nếu dự án cần chạy trên Java 17, nên kiểm tra cả toolchain, release và môi trường runtime thực tế.

Với Maven Compiler Plugin, khai báo release rõ ràng trong pom.xml:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Giá trị release không thay thế việc chọn JDK compiler. Cần phối hợp cấu hình compiler plugin và toolchain để bảo đảm compiler thực sự được lấy từ JDK phù hợp.

## 6. Dùng cùng một lệnh build trên máy cá nhân và CI

Một nguyên tắc đơn giản là tài liệu hướng dẫn và pipeline phải gọi cùng wrapper command. Tránh để máy cá nhân dùng ./gradlew nhưng CI lại gọi gradle; hoặc lập trình viên dùng ./mvnw nhưng runner gọi mvn.

Ví dụ pipeline CI cho Gradle:

~~~yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4

  - name: Set up JDK
    uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'

  - name: Verify wrapper and build
    run: |
      java -version
      ./gradlew --version
      ./gradlew clean check
~~~

Ví dụ pipeline CI cho Maven:

~~~yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4

  - name: Set up JDK
    uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'

  - name: Verify wrapper and build
    run: |
      java -version
      ./mvnw -version
      ./mvnw -B clean verify
~~~

Các action và phiên bản trong ví dụ là minh họa. Trong repository thực tế, nên pin action theo chính sách bảo mật của tổ chức, đồng thời xác định phiên bản JDK patch hoặc image cụ thể khi mức độ tái lập yêu cầu cao hơn. Trên Windows runner, dùng gradlew.bat hoặc mvnw.cmd.

### Quyền thực thi của wrapper script

Trên Linux và macOS, file gradlew và mvnw cần có quyền thực thi trong Git. Nếu thiếu, có thể gặp lỗi Permission denied. Kiểm tra mode của file trong Git và sửa quyền trong repository khi cần:

~~~bash
git ls-files --stage gradlew mvnw
git update-index --chmod=+x gradlew mvnw
~~~

Lệnh trên chỉ phù hợp với file tồn tại trong repository và cần được commit như một thay đổi metadata. Không nên yêu cầu mỗi thành viên tự chmod sau mỗi lần checkout.

## 7. Giảm khác biệt ngoài wrapper và toolchain

Wrapper và toolchain chỉ kiểm soát một phần môi trường. Để giảm sai khác sâu hơn, cần xem xét các yếu tố sau:

### Dependency và plugin

- Khai báo phiên bản plugin rõ ràng.
- Tránh dependency version động khi build cần ổn định.
- Dùng dependency locking để cố định phiên bản được phân giải.
- Có thể bật dependency verification hoặc checksum để phát hiện artifact bị thay đổi.
- Dùng repository đáng tin cậy và tránh để cùng tọa độ artifact trả về nội dung khác nhau.

Với Gradle, dependency locking có thể được bật theo configuration hoặc theo quy ước dự án. Sau khi cập nhật lockfile có chủ đích, commit các file khóa cần thiết. Với Maven, có thể quản lý phiên bản qua dependencyManagement và BOM, đồng thời dùng repository nội bộ có chính sách lưu trữ và kiểm tra artifact.

### Hệ điều hành và kiến trúc

Một build có thể phụ thuộc vào native library, shell, đường dẫn, quyền file hoặc kiến trúc CPU. Nếu cần môi trường hệ điều hành ổn định, dùng container image đã pin. Với yêu cầu tái lập chặt, pin theo digest thay vì chỉ dùng tag có thể thay đổi.

~~~bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  eclipse-temurin:17-jdk@sha256:REPLACE_WITH_VERIFIED_DIGEST \
  ./gradlew clean check
~~~

Digest trong ví dụ là placeholder. Phải thay bằng digest đã xác minh của image phù hợp với kiến trúc runner. Container giúp cố định userland và một số công cụ hệ thống; nó không tự cố định kernel host, CPU feature, thời gian, mạng hoặc mọi nguồn dữ liệu bên ngoài.

### Locale, timezone và encoding

Test có thể thất bại khác nhau nếu định dạng ngày giờ, sắp xếp chuỗi hoặc encoding phụ thuộc cấu hình máy. Hãy đặt mặc định rõ ràng trong CI và trong test:

~~~bash
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
./gradlew clean check
~~~

Ứng dụng và test vẫn nên chỉ định locale/timezone rõ ràng khi logic phụ thuộc chúng, thay vì dựa hoàn toàn vào biến môi trường. Với Java, cân nhắc cấu hình encoding UTF-8 rõ ràng và tránh giả định encoding mặc định của hệ điều hành.

### Biến môi trường và dữ liệu đầu vào

Không để build âm thầm phụ thuộc biến môi trường cá nhân, file cấu hình chưa commit hoặc dữ liệu đang thay đổi trên một dịch vụ bên ngoài. Liệt kê đầu vào cần thiết, đặt giá trị mặc định có chủ đích và truyền secret qua cơ chế quản lý bí mật của CI. Không ghi secret vào log hoặc artifact.

### Thời gian và timestamp trong artifact

Một số định dạng archive hoặc plugin có thể đưa timestamp hiện tại vào artifact. Hai build từ cùng mã nguồn vì thế có thể tạo file khác hash. Nếu cần artifact byte-for-byte giống nhau, cần cấu hình timestamp chuẩn hóa và dùng plugin hỗ trợ reproducible archive. Wrapper và toolchain không tự loại bỏ timestamp không xác định.

## 8. Xác minh môi trường build

Khi một build khác kết quả giữa máy cá nhân và CI, hãy thu thập bằng chứng trước khi thay đổi cấu hình:

~~~bash
java -version
./gradlew --version
./gradlew -q javaToolchains
~~~

Với Maven:

~~~bash
java -version
./mvnw -version
~~~

Sau đó kiểm tra:

1. Wrapper có tải đúng bản phân phối được khai báo không?
2. JVM đang chạy Gradle/Maven có đúng yêu cầu của build tool không?
3. Compiler và test có dùng đúng toolchain không?
4. Phiên bản plugin và dependency đã được khóa chưa?
5. Runner có cùng hệ điều hành, kiến trúc và công cụ hệ thống không?
6. Locale, timezone, encoding và biến môi trường có khác nhau không?
7. Build có đọc dữ liệu từ mạng hoặc nguồn thay đổi theo thời gian không?

Khi cần xác minh mức độ tái lập, build cùng commit trong hai workspace sạch, dùng cùng cấu hình đã pin, sau đó so sánh artifact digest. Nếu khác nhau, kiểm tra nội dung archive, timestamp, thứ tự file, metadata, đường dẫn tuyệt đối, generated source và các tác vụ phụ thuộc thời gian hoặc mạng.

## 9. Quy trình chuẩn hóa wrapper và toolchain trong dự án

Có thể triển khai theo trình tự sau:

**Bước 1: Kiểm kê công cụ hiện tại.** Ghi nhận phiên bản Gradle/Maven, JDK chạy build tool, JDK compile/test, plugin và môi trường CI đang dùng.

**Bước 2: Chọn phiên bản được hỗ trợ.** Chọn build tool tương thích với plugin và JDK cần dùng. Chọn JDK phù hợp với yêu cầu source, API và runtime của ứng dụng.

**Bước 3: Tạo hoặc nâng wrapper.** Commit script, JAR và file properties cần thiết. Cấu hình URL phân phối và checksum nếu cơ chế hỗ trợ.

**Bước 4: Khai báo toolchain.** Với Gradle, khai báo Java toolchain trong build script. Với Maven, cấu hình Maven Toolchains và cung cấp JDK tương ứng trong từng môi trường.

**Bước 5: Chuẩn hóa lệnh build.** Cập nhật hướng dẫn phát triển và pipeline để dùng wrapper. Không dựa vào build tool cài toàn cục.

**Bước 6: Khóa các đầu vào quan trọng.** Pin plugin, dependency, image CI và cấu hình môi trường theo mức độ cần thiết.

**Bước 7: Chạy xác minh trên môi trường sạch.** Thử trên runner mới hoặc container sạch, kiểm tra phiên bản công cụ và so sánh kết quả build.

**Bước 8: Duy trì có kiểm soát.** Khi nâng JDK hoặc build tool, tạo thay đổi riêng, review tương thích, chạy kiểm tra và cập nhật checksum hoặc lockfile tương ứng.

## 10. Những sai lầm thường gặp

### Nghĩ wrapper đã cố định cả JDK

Wrapper cố định phiên bản Gradle hoặc Maven. JDK chạy build tool và JDK dùng để compile/test vẫn cần được quản lý riêng.

### Chỉ đặt sourceCompatibility hoặc release

Các thuộc tính này mô tả mức ngôn ngữ hoặc bytecode mục tiêu. Chúng không nhất thiết chọn đúng JDK thực thi compiler và test. Dùng toolchain để xác định JDK thực hiện tác vụ.

### Cài JDK mới nhất trên mọi runner

Tag latest hoặc cài bản mới nhất theo thời điểm khiến môi trường thay đổi mà không có commit thể hiện thay đổi đó. Hãy chọn phiên bản có chủ đích và nâng cấp qua thay đổi được review.

### Commit đường dẫn JDK của máy cá nhân

Đường dẫn trong toolchains.xml hoặc cấu hình local không tồn tại trên runner khác. Repository nên mô tả yêu cầu phiên bản; mỗi môi trường cung cấp đường dẫn JDK tương ứng.

### Cho rằng container bảo đảm tái lập tuyệt đối

Container chuẩn hóa nhiều thành phần userland nhưng không loại bỏ mọi khác biệt về kernel, CPU, thời gian, mạng hoặc dữ liệu đầu vào. Cần kiểm soát thêm nếu yêu cầu là artifact có cùng byte.

### Cập nhật wrapper mà không review file đi kèm

Wrapper script và JAR có quyền tải và thực thi build tool. Hãy review nguồn, checksum và thay đổi phiên bản trước khi merge.

### Không phân biệt JVM của build tool với toolchain

Khi build thất bại, chỉ nhìn JAVA_HOME có thể chưa đủ. Kiểm tra JVM khởi chạy Gradle/Maven và JDK mà compiler/test thực sự sử dụng.

## 11. Quy tắc thực hành

- Commit wrapper của dự án và dùng wrapper trong mọi hướng dẫn, máy cá nhân và CI.
- Cố định phiên bản Gradle hoặc Maven; kiểm tra checksum của bản phân phối khi wrapper hỗ trợ.
- Khai báo Java toolchain cho compiler và test; xác minh JDK chạy build tool riêng.
- Với Maven, dùng Maven Toolchains khi cần JDK thực hiện tác vụ khác JVM chạy Maven.
- Pin phiên bản plugin, dependency và môi trường runner theo mức độ tái lập cần thiết.
- Chuẩn hóa locale, timezone, encoding và biến môi trường có ảnh hưởng đến kết quả.
- Build trong workspace sạch và so sánh artifact khi cần chứng minh tính tái lập.
- Nâng phiên bản wrapper, JDK và dependency qua thay đổi có review, kiểm thử và bằng chứng.

Wrapper và toolchain tạo ra một hợp đồng công cụ rõ ràng giữa lập trình viên và CI. Khi chúng được kết hợp với dependency được kiểm soát và môi trường thực thi nhất quán, lỗi do khác biệt máy build giảm đáng kể, việc điều tra sự cố dễ hơn và kết quả build có cơ sở để lặp lại. Nếu yêu cầu cao hơn là tạo artifact giống hệt từng byte, cần tiếp tục kiểm soát timestamp, metadata, hệ điều hành, kiến trúc và mọi đầu vào không xác định.
