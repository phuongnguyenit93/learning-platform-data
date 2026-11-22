# Cấu hình Java Toolchains trong Maven và Gradle

## 1. Java Toolchains giải quyết vấn đề gì?

Khi phát triển ứng dụng Spring Boot, một máy tính có thể cài đồng thời JDK 17 và JDK 21. Lệnh **java -version** trên terminal có thể hiện Java 21; IDE có thể dùng JDK 17; CI lại dùng JDK khác. Nếu cấu hình build không rõ ràng, mã có thể biên dịch thành công trên máy này nhưng lỗi trên máy khác, hoặc vô tình sử dụng API quá mới so với môi trường chạy thật.

**Java Toolchain** là cơ chế để công cụ build lựa chọn bộ công cụ Java phù hợp với yêu cầu dự án, ví dụ **javac 17** để biên dịch, JDK 17 để chạy test và javadoc để tạo tài liệu. Toolchain thường gồm các công cụ lấy từ một bản cài JDK. Mục tiêu là làm rõ yêu cầu JDK của **các tác vụ build có hỗ trợ toolchain**.

Trong Spring Boot, cần phân biệt bốn khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **JDK chạy công cụ build** | JVM khởi động tiến trình Maven hoặc Gradle daemon và chạy logic/plugin của công cụ build. | Maven khởi động trên JDK 21. |
| **JDK toolchain** | JDK được chọn cho task/plugin hỗ trợ, như biên dịch Java hoặc chạy test. | Maven Compiler Plugin dùng javac 17. |
| **Mức tương thích đầu ra** | Phiên bản cú pháp, API và bytecode mà ứng dụng hướng đến. | Java 17, bytecode major version 61. |
| **JVM chạy ứng dụng khi triển khai** | Lệnh java thật sự chạy JAR sau build, trong server/container/máy người dùng. | Runtime Java 17 hoặc Java 21 tương thích. |

**Toolchain không tự đổi JAVA_HOME, không cài thay JDK chạy Maven/Gradle, và không tự đổi JVM của lệnh java -jar độc lập.** Một task hoặc plugin không hỗ trợ toolchain có thể tiếp tục dùng JVM chạy công cụ build, JDK từ PATH hoặc cấu hình riêng.

Bài này sử dụng **Java 17** làm mục tiêu vì Spring Boot 3.x yêu cầu Java 17 trở lên. Các ví dụ được đặt trong bối cảnh **Spring Boot 3.3.5**; số phiên bản này là cấu hình mẫu để minh họa, không hàm ý đây là bản Spring Boot mới nhất.

## 2. Khi nào cần cấu hình Toolchains?

- **Nhiều JDK trên cùng máy:** hệ thống mặc định dùng Java 21 nhưng dự án cần biên dịch theo Java 17.
- **Đồng nhất máy phát triển và CI:** developer và pipeline cùng chọn JDK 17 cho tác vụ Java.
- **Repository nhiều module:** module A cần Java 17, module B cần Java 21; từng module đặt yêu cầu tương ứng.
- **Biên dịch bằng JDK mới cho runtime cũ:** có thể dùng javac 21 kèm **--release 17** để chỉ sử dụng ngôn ngữ/API và bytecode của Java 17.
- **Điều tra lỗi môi trường:** xác định liệu lỗi đến từ JVM chạy Maven/Gradle, JDK biên dịch, Java chạy test, hay JDK chạy ứng dụng.

Cấu hình toolchain không thay thế việc kiểm tra **tính tương thích giữa Spring Boot, Gradle/Maven, plugin, JDK và môi trường triển khai**. Ví dụ, nếu một plugin yêu cầu JVM 17 để khởi động, không thể chạy plugin đó trên JVM 11 rồi mong toolchain 17 tự sửa được.

## 3. Maven: chọn JDK bằng Maven Toolchains Plugin

Trong Maven, phần lớn cấu hình dự án nằm ở **pom.xml**. Toolchains là một cơ chế bổ sung: **maven-toolchains-plugin** chọn JDK phù hợp và đưa lựa chọn đó vào ngữ cảnh build để các plugin **toolchain-aware** sử dụng. **maven-compiler-plugin** là ví dụ quan trọng nhất.

Từ Maven Toolchains Plugin **3.2.0**, goal **select-jdk-toolchain** hỗ trợ khám phá JDK ở các vị trí phổ biến và qua biến môi trường. Ví dụ dưới dùng plugin **3.3.0**.

### 3.1. Ví dụ pom.xml đầy đủ cho ứng dụng Spring Boot

Lưu vào **pom.xml** ở thư mục gốc của một dự án Maven. Ví dụ yêu cầu chọn một JDK thuộc nhánh **17.x** cho các plugin hỗ trợ toolchain:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>toolchain-maven</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <toolchain.jdk.version>[17,18)</toolchain.jdk.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>select-jdk-toolchain</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích chính xác từng phần:**

1. **java.version = 17:** nêu baseline Java của Spring Boot Maven parent. Dự án muốn chạy ứng dụng trên Java 17 nên giữ giá trị này là 17.
2. **maven.compiler.release = 17:** yêu cầu javac tạo mã theo mức Java 17, bao gồm cú pháp, tập API chuẩn và bytecode. Với Spring Boot starter parent, thuộc tính này thường đã được nối với java.version; ghi rõ ở đây để thấy mục tiêu tương thích.
3. **toolchain.jdk.version = [17,18):** chọn JDK có version từ 17 (bao gồm) đến dưới 18. Dùng khoảng này vì JDK thực tế có thể được mô tả là **17** hoặc **17.0.12**. Giá trị **17** đơn lẻ không luôn khớp **17.0.x** trong các toolchains thủ công.
4. **select-jdk-toolchain:** goal tự lựa chọn một JDK phù hợp từ các JDK được phát hiện hoặc khai báo; goal được gắn vào pha **validate** của Maven. Khi chạy các pha sau như compile/package/verify, pha validate được đi qua.
5. **spring-boot-maven-plugin:** phục vụ build và đóng gói ứng dụng Boot; plugin này không phải bản thân cơ chế lựa chọn JDK toolchain.

**Lưu ý về điều kiện chạy:** Maven và Spring Boot Maven Plugin vẫn phải được khởi động trên một JVM tương thích. Ví dụ thực tế dễ hiểu là Maven chạy trên **JDK 21**, trong khi compiler lấy từ **JDK 17**. Nếu máy chỉ có JDK 21 mà cấu hình bắt buộc **[17,18)**, Maven không thể tự tạo JDK 17 chỉ nhờ select-jdk-toolchain; phải cài JDK 17 hoặc thay đổi yêu cầu phù hợp dự án.

### 3.2. Kiểm tra JDK mà Maven phát hiện

Từ thư mục dự án có Maven Wrapper:

~~~bash
./mvnw -version
./mvnw org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
./mvnw clean verify
~~~

- **-version** hiển thị phiên bản Maven và JVM **đang chạy Maven**, chưa đủ chứng minh compiler toolchain.
- **display-discovered-jdk-toolchains** liệt kê những JDK mà plugin tìm thấy cùng metadata; đây là lệnh chẩn đoán, **không** phải goal đặt toolchain cho toàn bộ build.
- **clean verify** thực thi các pha cần thiết và dùng toolchain được chọn nếu plugin/task có hỗ trợ.
- Trên Windows dùng **mvnw.cmd** thay **./mvnw**; nếu không có wrapper, dùng lệnh **mvn** từ bản Maven đã cài.

Khi cần phân tích vấn đề chọn toolchain, có thể chạy **./mvnw -X compile** để xem log chi tiết. Không suy ra compiler JDK chỉ bằng **java -version** hoặc **./mvnw -version**.

### 3.3. Lựa chọn khác: toolchains.xml thủ công

Khi JDK nằm ở thư mục không được tự phát hiện, hoặc tổ chức muốn chỉ định đường dẫn cố định cho một agent build, Maven hỗ trợ file cấu hình cá nhân **~/.m2/toolchains.xml**. File này nằm trong Maven user home; đường dẫn phụ thuộc hệ điều hành. Ví dụ minh họa cho máy Linux có JDK 17 ở **/opt/jdks/jdk-17**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

**Thay jdkHome bằng đường dẫn cài JDK thật**. Tệp trên mô tả những JDK có sẵn; để dùng cơ chế cũ **toolchains:toolchain**, cấu hình plugin trong pom.xml như **đoạn thay thế** dưới đây. Đoạn sau **không phải pom.xml đầy đủ** và dùng **thay cho** block maven-toolchains-plugin có goal select-jdk-toolchain ở mục 3.1:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
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
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

**Cơ chế chọn:** Maven tìm entry loại **jdk** có version khớp rồi cung cấp toolchain cho các plugin hỗ trợ. Metadata như **vendor** ở toolchains.xml là chuỗi mô tả phục vụ so khớp, không phải bằng chứng Maven đã xác minh JDK thật thuộc hãng đó. Cần đảm bảo jdkHome trỏ đến JDK đúng, gồm **bin/javac**. Tệp toolchains.xml không có nghĩa là Maven sẽ tự dùng toolchain trong mọi build nếu không có goal hoặc plugin chọn nó.

**Không đặt đường dẫn JDK riêng của máy cá nhân vào pom.xml dùng chung.** Mỗi máy/CI có thể khai báo JDK của mình; POM chỉ biểu diễn ràng buộc về phiên bản. Cơ chế discovery mới tiện hơn khi JDK được phát hiện; cấu hình thủ công thích hợp khi môi trường khó tự khám phá.

## 4. Gradle: Java Toolchains trong build.gradle

Gradle Java Toolchains là khả năng tích hợp của các plugin Java. Với Gradle Groovy DSL, dự án thường có hai tệp:

- **settings.gradle**: tên root project, module con và tùy chọn resolver JDK khi cần.
- **build.gradle**: yêu cầu JDK và cấu hình task Java của từng project.

Trong ví dụ dưới, nên dùng **Gradle Wrapper 8.5** hoặc một bản mới hơn có hỗ trợ Java/Spring Boot plugin tương ứng. Gradle 8.5 hỗ trợ chạy Gradle trên Java 21 và sử dụng Java 21 qua toolchain; với Java 17, đây cũng là nền tảng phù hợp.

### 4.1. settings.gradle đơn giản

~~~groovy
rootProject.name = 'toolchain-gradle'
~~~

Đây là toàn bộ file settings.gradle đủ cho dự án một module có JDK 17 đã cài và được Gradle nhận diện. Không cần thêm cơ chế download nếu JDK 17 sẵn có.

### 4.2. build.gradle đầy đủ cho Spring Boot

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là một build.gradle **Groovy DSL hoàn chỉnh** cho dự án demo. Đối với **build.gradle.kts** (Kotlin DSL), cú pháp plugin, dependency, task phải viết lại đúng kiểu Kotlin; không đổi đuôi file rồi giữ nguyên cú pháp Groovy.

**Phân biệt hai thiết lập Java:**

- **java.toolchain.languageVersion = 17:** Gradle tìm JDK 17 rồi cung cấp công cụ của JDK đó cho những task Java có hỗ trợ, như **JavaCompile**, **Test** và **Javadoc** do plugin Java cung cấp.
- **options.release = 17:** trình biên dịch chỉ được dùng ngôn ngữ và API Java 17 và tạo class file tương thích Java 17. Thiết lập này bảo vệ mục tiêu chạy trên Java 17, kể cả khi một ngày nào đó dự án cố ý đổi toolchain sang JDK 21.

Không phải cứ đặt **sourceCompatibility = 17** hoặc **targetCompatibility = 17** là bảo đảm không dùng API chỉ tồn tại từ Java 21. Với javac đời mới, cặp -source/-target **không** giới hạn toàn bộ API chuẩn như **--release**.

### 4.3. Kiểm tra Gradle đang dùng JVM và JDK nào

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean build
./gradlew compileJava --info
~~~

- **--version** cho biết Gradle và JVM/daemon mà Gradle sử dụng, không phải bằng chứng duy nhất về JDK của compileJava.
- **javaToolchains** liệt kê JDK Gradle đã phát hiện và thông tin của chúng.
- **build** biên dịch, chạy test và tạo artifact theo task graph; Spring Boot plugin tạo task **bootJar**.
- **compileJava --info** hữu ích để xem JDK/toolchain được lựa chọn, compiler và lý do task chạy hoặc được bỏ qua.

Trên Windows thay **./gradlew** bằng **gradlew.bat**. Gradle Wrapper khóa phiên bản Gradle của dự án; **wrapper không khóa hoặc cài sẵn JDK**.

### 4.4. Khi máy chưa có JDK 17: auto-provisioning

Gradle có thể **tự tải JDK phù hợp khi cần**, nhưng phải cấu hình một **toolchain download repository/resolver**. Với dự án sử dụng Gradle 8.5, ví dụ có thể dùng Foojay resolver convention plugin **0.8.0** trong **settings.gradle**:

~~~groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '0.8.0'
}

rootProject.name = 'toolchain-gradle'
~~~

Đây là **toàn bộ settings.gradle để thay cho** bản đơn giản ở mục 4.1; file build.gradle ở mục 4.2 vẫn giữ nguyên. Plugin Foojay là **settings plugin**, không đặt vào build.gradle như plugin ứng dụng. Khi không phát hiện JDK đáp ứng yêu cầu, Gradle có thể tải JDK tương ứng từ resolver đã cấu hình, tùy kết nối mạng và chính sách môi trường. Việc tự tải JDK **không đồng nghĩa** Gradle sẽ tự đổi JVM đang chạy Gradle daemon.

Nếu CI không cho phép tải JDK từ mạng, hãy **cài JDK 17 trước** và bảo đảm Gradle nhận ra JDK đó. Không phụ thuộc vào việc auto-provisioning sẽ luôn hoạt động offline.

### 4.5. Khi Gradle không tự nhận ra JDK đã cài

Kiểm tra **./gradlew -q javaToolchains** trước. Gradle hỗ trợ thuộc tính cài đặt như **org.gradle.java.installations.paths**, liệt kê đường dẫn JDK ngoài các vị trí tự phát hiện. Ví dụ cho máy Linux, đặt trong **gradle.properties** của môi trường hoặc dự án khi đường dẫn thật sự phù hợp với mọi máy build:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
~~~

Đường dẫn là minh họa; không sao chép nguyên nếu JDK thực tế ở nơi khác. Tránh commit đường dẫn riêng cho một máy làm cấu hình chung của team. Có thể đặt lựa chọn này trong **~/.gradle/gradle.properties** trên máy cụ thể.

Nếu thay đổi vị trí JDK nhưng daemon vẫn giữ kết quả dò cũ, dùng **./gradlew --stop** rồi chạy lại. Không cần sửa cấu hình build khi chỉ khác vị trí cài đặt cục bộ.

## 5. Bài thực hành: cùng một class Java, biên dịch bằng hai công cụ

Ta dùng một class Java thuần để nhìn thấy trực tiếp tác động của Java Toolchains. Class này hợp lệ với Java 17+, không phụ thuộc framework:

**src/main/java/com/example/demo/ToolchainDemo.java**

~~~java
package com.example.demo;

public class ToolchainDemo {
    public static void main(String[] args) {
        System.out.println("Toolchain demo OK");
    }
}
~~~

File Java trên là **chương trình hoàn chỉnh** với package/class trùng đường dẫn. Đặt nó trong dự án Maven ở mục 3.1 **hoặc** dự án Gradle ở mục 4.2.

**Với Maven**, biên dịch bằng wrapper rồi chạy class từ thư mục project:

~~~bash
./mvnw clean compile
java -cp target/classes com.example.demo.ToolchainDemo
~~~

**Với Gradle**, chạy:

~~~bash
./gradlew clean classes
java -cp build/classes/java/main com.example.demo.ToolchainDemo
~~~

Khi JVM của lệnh **java** cuối cùng là Java 17 trở lên, cả hai ví dụ đều in **đúng một dòng stdout từ chương trình**:

~~~text
Toolchain demo OK
~~~

Log của Maven/Gradle có thể xuất hiện ở các lệnh build trước đó, không được tính vào stdout của ToolchainDemo.

**Tại sao lệnh java vẫn cần chú ý?** Dòng **java -cp ...** được shell tìm qua PATH/JAVA_HOME và **không tự được Maven hoặc Gradle toolchain điều khiển**. Vì vậy, class có thể biên dịch thành công cho Java 17 nhưng chạy lỗi **UnsupportedClassVersionError** nếu người dùng cố chạy nó bằng Java 11.

### 5.1. Kiểm chứng class file biên dịch đúng mục tiêu

Sau khi compile, dùng **javap** từ một JDK đủ mới để đọc thông tin class file:

~~~bash
javap -verbose target/classes/com/example/demo/ToolchainDemo.class
~~~

Với Gradle, thay đường dẫn bằng:

~~~bash
javap -verbose build/classes/java/main/com/example/demo/ToolchainDemo.class
~~~

Trong output dài, tìm dòng:

~~~text
major version: 61
~~~

**61** là major version của class file **Java 17** (Java 21 là **65**). Đây là phép kiểm tra mức bytecode, **không xác nhận tuyệt đối compiler nào đã chạy**, cũng không chứng minh mọi plugin/test đã dùng đúng JDK. Muốn xác nhận compiler JDK, xem log toolchain của Maven hoặc **compileJava --info** ở Gradle.

### 5.2. Tình huống JDK 21 biên dịch ra bytecode Java 17

Giả sử build server cài JDK 21 và muốn dùng compiler 21 nhưng vẫn phục vụ runtime Java 17:

- **Maven:** thay điều kiện chọn toolchain thành **[21,22)**, nhưng **giữ maven.compiler.release = 17** và java.version phù hợp với mức runtime của ứng dụng.
- **Gradle:** thay **JavaLanguageVersion.of(17)** thành **JavaLanguageVersion.of(21)**, nhưng **giữ options.release = 17**.

Javac 21 với **--release 17** phát sinh bytecode Java 17, đồng thời không cho mã dự án gọi các API chuẩn chỉ được thêm sau Java 17. Ví dụ này chứng minh **toolchain JDK** và **mức release** là hai quyết định riêng. Chiều ngược lại không hợp lệ: **javac 17 không thể thực hiện --release 21**.

Để đơn giản và tránh bất ngờ, dự án Spring Boot chạy ở Java 17 thường có thể dùng **toolchain 17 + release 17** như cấu hình chính trong bài.

## 6. Maven/Gradle: điểm giống và khác khi chọn JDK

| Câu hỏi | Maven Toolchains | Gradle Java Toolchains |
| --- | --- | --- |
| Khai báo yêu cầu JDK trong file nào? | **pom.xml**, qua maven-toolchains-plugin hoặc jdkToolchain của plugin riêng. | **build.gradle**, qua java.toolchain hoặc cấu hình task. |
| JDK được tìm từ đâu? | Maven Toolchains Plugin từ 3.2.0 có discovery; cách truyền thống dùng **~/.m2/toolchains.xml**. | Gradle tìm bản cài JDK đã nhận diện; có thể cấu hình paths và resolver tải JDK. |
| Có tự tải JDK khi thiếu? | Goal discovery của Maven Toolchains Plugin **không cài JDK mới**. | **Có thể**, nếu cấu hình toolchain download repository và môi trường cho phép. |
| Bắt buộc thay JVM chạy công cụ build? | **Không**; JVM Maven là lựa chọn khác. | **Không**; Gradle daemon JVM khác toolchain dùng cho task. |
| Compile/test tự dùng toolchain? | Phụ thuộc plugin có **toolchain-aware** hay không. | Java plugin hỗ trợ các task Java tiêu chuẩn; task/plugin khác cần kiểm tra. |
| Chặn API mới hơn runtime mục tiêu? | **maven.compiler.release** cho javac. | **options.release** cho JavaCompile. |
| Xem JDK đã phát hiện? | Goal **display-discovered-jdk-toolchains**. | Task **javaToolchains**. |

Đối với các test có cấu hình riêng, **không kết luận** test đang chạy JDK 17 chỉ vì compiler dùng JDK 17. Với Maven, Surefire/Failsafe và các plugin có thể hỗ trợ toolchain hoặc **jdkToolchain** riêng tùy phiên bản và cấu hình. Với Gradle, task **Test** thuộc Java plugin thường dùng launcher từ cấu hình toolchain; nếu một task custom tự khởi chạy Java, phải khai báo launcher phù hợp.

## 7. Toolchain với sourceCompatibility, targetCompatibility, --release và JAVA_HOME

Đây là phần dễ gây nhầm lẫn nhất khi chuyển dự án từ JDK 17 sang JDK 21.

| Cấu hình | Chọn bản cài JDK? | Giới hạn cú pháp/bytecode? | Giới hạn API chuẩn Java theo phiên bản? |
| --- | --- | --- | --- |
| **Toolchain JDK 17** | Có, cho task/plugin hỗ trợ. | Compiler mặc định từ JDK 17 không thể tạo class Java 21. | Không tự là cam kết target runtime khác với JDK đã chọn. |
| **--release 17** | Không. | Có. | Có, theo API chuẩn Java 17. |
| **-source 17 / -target 17** | Không. | Có ở mức cú pháp/bytecode tương ứng. | Không bảo đảm khi biên dịch bằng JDK mới hơn. |
| **JAVA_HOME** | Có thể định JVM mặc định cho Maven/Gradle và shell. | Không phải cấu hình yêu cầu build chuẩn hóa theo từng project. | Không. |

**Ví dụ lỗi thực tế:** Mã dùng một API chỉ xuất hiện ở Java 21, trong khi muốn chạy trên Java 17. Trên JDK 21, một cấu hình chỉ đặt **-source 17 -target 17** có thể vẫn biên dịch tham chiếu API mới rồi gây lỗi lúc chạy Java 17. **--release 17** chặn lỗi ngay khi compile.

Với Maven, cấu hình chuẩn cho mục tiêu Java 17 là:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây là **đoạn bên trong pom.xml**, không phải file độc lập. Với Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Đoạn Gradle này cũng là **một phần** của build.gradle. Cả hai bản release đều phải phù hợp với JDK compiler. Chỉ riêng **--release** không chọn JDK; chỉ riêng **toolchain** không thay quyết định mức runtime mà ứng dụng cần cam kết.

## 8. Sử dụng Toolchains trong dự án Spring Boot nhiều module

Với Gradle multi-project, **settings.gradle** xác định module:

~~~groovy
rootProject.name = 'learning-system'
include 'api', 'core'
~~~

Ví dụ **core/build.gradle** dùng Java 17:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Ví dụ **api/build.gradle** muốn dùng Spring Boot và phụ thuộc core, thì trong build.gradle của api phải khai báo cả plugin, dependency lẫn toolchain tương ứng. Một dependency giữa hai project có thể viết:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

Đây là **một fragment của api/build.gradle**; dự án thực tế phải bổ sung các plugin/repository/dependency cần thiết như ví dụ ở mục 4.2. **include** trong settings.gradle chỉ đưa module vào build, không tự nối dependency giữa các module.

Maven multi-module thường đặt **maven-toolchains-plugin** trong POM cha theo chính sách kế thừa phù hợp. Tuy nhiên, **pluginManagement** chỉ quản lý cấu hình/plugin, không phải mọi plugin bên trong đó đều tự chạy; cần bảo đảm goal được kích hoạt theo cách mong muốn. Khi các module có các baseline Java khác nhau, kiểm tra yêu cầu toolchain ở từng module và tính tương thích khi module này tiêu thụ class từ module khác.

**Tình huống quan trọng:** Nếu module core được build với bytecode Java 21, module api hoặc runtime dùng Java 17 sẽ không đọc được class của core. Toolchain cho riêng module api không thể sửa sự không tương thích bytecode đã có trong artifact dependency.

## 9. CI, IDE và deployment: duy trì tính nhất quán

### 9.1. Quy trình CI gợi ý

1. **Chọn Java runtime đích**, ví dụ Java 17 cho ứng dụng Spring Boot 3.x; ghi rõ mục tiêu này trong cấu hình build.
2. **Cài JDK phù hợp** trên CI; nếu dùng Maven discovery hoặc Gradle local toolchain, bảo đảm JDK 17 nằm ở nơi có thể nhận diện.
3. **Dùng Maven Wrapper/Gradle Wrapper** từ repository để cố định phiên bản công cụ build. Wrapper cố định Maven/Gradle, **không thay thế Java toolchain**.
4. **Kiểm tra JVM của công cụ build** bằng **./mvnw -version** hoặc **./gradlew --version**; kiểm tra JDK có thể chọn qua các lệnh liệt kê toolchain.
5. **Chạy build đầy đủ**: **./mvnw clean verify** hoặc **./gradlew clean build**; xem compiler/test launcher thực dùng khi điều tra lỗi.
6. **Kiểm tra artifact và môi trường chạy**: executable Spring Boot JAR vẫn cần Java runtime thích hợp. Lệnh **java -jar ...** trong production sử dụng JVM của container/server, không phải JDK toolchain từ laptop.

Một image container có Java 17 có thể chạy JAR biên dịch với **--release 17** và dependency tương thích, ngay cả khi CI đã sử dụng JDK 21 để build. Nhưng phải kiểm tra cả **thư viện phụ thuộc**, native code và yêu cầu runtime khác, không chỉ major version của class ứng dụng.

### 9.2. IDE và terminal có thể dùng JDK khác nhau

IntelliJ IDEA/Eclipse/VS Code có các lựa chọn **Project SDK**, **Gradle JVM**, **Maven runner JDK** và mức ngôn ngữ riêng. Khi IDE báo đỏ nhưng command-line build thành công (hoặc ngược lại), hãy xem phần cài đặt JVM dùng để chạy build trong IDE và yêu cầu toolchain của project. Việc đặt **Project SDK 21** không tự bảo đảm Gradle sẽ biên dịch bằng JDK 21 nếu build.gradle yêu cầu toolchain 17.

### 9.3. Không lưu đường dẫn hệ thống cá nhân vào mã nguồn chung

- Maven nên giữ yêu cầu phiên bản trong pom.xml; đường dẫn JDK riêng của máy ở **~/.m2/toolchains.xml** khi dùng phương pháp thủ công.
- Gradle nên giữ yêu cầu version trong build.gradle; cấu hình cài đặt cụ thể có thể nằm ở **~/.gradle/gradle.properties** nếu mỗi máy khác nhau.
- Khi CI cần tự cài JDK, cấu hình bước provisioning bên trong pipeline; không đặt một đường dẫn Windows/Linux giả định cho mọi máy.
- Nếu policy chặn tải file từ bên ngoài, cài và quản lý JDK tập trung; không kỳ vọng Gradle resolver sẽ tự vượt qua chính sách mạng.

## 10. Sự cố thường gặp và hướng xử lý

**1. Maven báo không tìm thấy toolchain JDK 17.** Kiểm tra JDK 17 đã cài, goal **display-discovered-jdk-toolchains**, biến môi trường và cách khai báo version. Nếu toolchains.xml ghi **17.0.12** còn POM yêu cầu chuỗi đơn **17**, hãy đổi điều kiện thành **[17,18)**. Với cấu hình thủ công, xem **jdkHome** có thực sự chỉ đến thư mục JDK hợp lệ.

**2. Maven -version hiển thị Java 21 dù POM yêu cầu Java 17.** Đây chưa phải lỗi. **mvn -version** hiển thị Java **chạy Maven**, toolchain 17 được chọn cho plugin hỗ trợ. Kiểm tra log chọn toolchain và compiler, không thay đổi JAVA_HOME một cách mò mẫm.

**3. Maven chạy trên Java quá cũ rồi lỗi khi nạp plugin Spring Boot.** Toolchain không tự thay JVM chạy Maven. Nâng hoặc chọn JDK chạy Maven tương thích với Spring Boot/plugin, sau đó để Maven Toolchains quản lý JDK cần cho compile.

**4. Gradle báo không tìm thấy Java installation phù hợp.** Chạy **./gradlew -q javaToolchains**, cài JDK đúng phiên bản hoặc cấu hình resolver (nếu môi trường cho phép tải). Kiểm tra **org.gradle.java.installations.paths**; sau thay đổi có thể dừng daemon bằng **./gradlew --stop**.

**5. Gradle vẫn chạy daemon trên JDK 21.** **java.toolchain.languageVersion = 17** chọn JDK cho task được hỗ trợ; nó không tự đổi JVM đã khởi động Gradle daemon. Nếu bản Gradle/plugin không chạy được trên JVM daemon hiện tại, phải đổi JVM dùng để khởi động Gradle hoặc nâng Gradle tương thích.

**6. Java 21 API lọt vào ứng dụng dự định chạy trên Java 17.** Đặt **maven.compiler.release = 17** (Maven) hoặc **options.release = 17** (Gradle). Không chỉ dựa vào **targetCompatibility**.

**7. Lệnh java -jar sau build báo UnsupportedClassVersionError.** Kiểm tra Java runtime đang chạy ứng dụng thực tế và mức class của artifact. Một class Java 21 (major 65) không chạy trên JVM 17 (chỉ nhận major 61). Chỉnh mục tiêu build và dependency hoặc nâng runtime theo chính sách dự án.

**8. Test hoặc task custom vẫn dùng JDK khác compiler.** Kiểm tra xem plugin có hỗ trợ toolchain hay không. Maven Surefire/Failsafe có khả năng chọn JDK riêng tùy phiên bản; Gradle task **Test/JavaExec** có **javaLauncher** để cấu hình rõ JDK nếu cần. Toolchain không tự áp dụng cho mọi script hay mọi subprocess.

**9. Không tải được JDK tự động trên Gradle CI.** Auto-provisioning yêu cầu resolver và kết nối tương ứng. Nếu mạng bị hạn chế hoặc không có resolver, cài trước JDK và khai báo vị trí thay vì chỉ thêm languageVersion.

**10. File settings.gradle có resolver nhưng không chạy với Gradle version cũ.** Kiểm tra tương thích giữa **Gradle Wrapper**, phiên bản plugin Foojay và JVM chạy Gradle. Plugin resolver ở mục 4.4 dành cho bối cảnh Gradle 8.5; dự án dùng bản khác cần chọn phiên bản resolver phù hợp.

## 11. Checklist tự xác minh

- [ ] Xác định runtime đích: Java 17 hay Java 21?
- [ ] Biết công cụ build nào đang dùng: Maven hay Gradle?
- [ ] Kiểm tra **JVM chạy Maven/Gradle** có phù hợp plugin Spring Boot và Gradle/Maven version?
- [ ] Cấu hình **toolchain JDK** ở đúng vị trí: pom.xml hoặc build.gradle?
- [ ] Chọn **--release** tương ứng với runtime đích, không chỉ source/target?
- [ ] Xem danh sách JDK được phát hiện và log xác nhận compiler?
- [ ] Kiểm tra task test và task custom khi chúng có thể dùng JDK khác?
- [ ] Biên dịch và chạy thử, kiểm tra **major version** của class nếu cần?
- [ ] CI và môi trường production thực sự có Java runtime tương thích?

## 12. Tài liệu tham khảo chính thức

- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains
- Apache Maven Toolchains Plugin — JDK Discovery: https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html
- Apache Maven Toolchains Plugin — select-jdk-toolchain: https://maven.apache.org/plugins/maven-toolchains-plugin/select-jdk-toolchain-mojo.html
- Gradle — Java Toolchains for JVM projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Building Java & JVM projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — Gradle 8.5 Release Notes: https://docs.gradle.org/8.5/release-notes.html

**Kết luận:** Chọn **JDK nào để build** (toolchain), **Java nào được phép xuất hiện trong artifact** (--release), **JVM nào chạy công cụ build** và **JVM nào chạy Spring Boot ở production** là bốn lựa chọn có liên quan nhưng không đồng nhất. Cấu hình rõ từng phần, kết hợp wrapper và kiểm tra thực tế giúp tránh lỗi lệch JDK giữa IDE, máy phát triển và CI.