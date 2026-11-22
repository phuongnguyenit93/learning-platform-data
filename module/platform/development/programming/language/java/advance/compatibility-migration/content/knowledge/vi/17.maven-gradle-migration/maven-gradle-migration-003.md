# Maven Toolchains và lựa chọn JDK cho từng nhóm plugin

Khi nâng cấp JDK hoặc phát hành thư viện hỗ trợ nhiều phiên bản Java, câu hỏi “dự án đang dùng Java mấy?” không đủ để kiểm tra tính tương thích. Một project Maven có thể **chạy Maven bằng JDK 21**, **biên dịch mã nguồn bằng JDK 21 nhưng đặt `--release 17`**, **chạy unit test trên JDK 17**, **chạy integration test trên JDK 21** và **tạo Javadoc bằng JDK 21**. Nếu chỉ đọc `JAVA_HOME` hoặc `mvn -version`, nhóm phát triển có thể hiểu sai JDK mà từng giai đoạn thực sự sử dụng.

**Maven Toolchains** cung cấp cơ chế lựa chọn JDK cho những Maven plugin có hỗ trợ, độc lập với JVM đã khởi động Maven. Ngoài **toolchain mặc định** được Maven Toolchains Plugin đặt trong session, một số plugin như Maven Compiler, Surefire, Failsafe và Javadoc còn có tham số `jdkToolchain` để chọn JDK riêng.

Đối với Java Advance Compatibility Migration, mục tiêu không chỉ là cho build thành công. Cần bảo đảm compiler, bytecode target, bộ test và plugin khác được chạy đúng JDK đã công bố, đồng thời kết quả đó có thể tái tạo trên máy phát triển và CI.

## 1. Bốn vai trò JDK cần phân biệt

| Vai trò | Thực thi những gì? | Cách xác nhận |
|---|---|---|
| **Maven JVM** | Maven core và các Maven plugin goals/mojos chạy trong tiến trình Maven | `mvn -version` |
| **Compiler JDK** | `javac` được Maven Compiler Plugin chọn để biên dịch main/test source | Log Compiler Plugin, thông tin toolchain |
| **Test JVM** | JVM mà Surefire/Failsafe dùng để chạy unit/integration tests | Log fork và `java.version` trong test |
| **JDK tools khác** | `javadoc`, `jdeps`, `jlink`, `jarsigner` và công cụ ngoài nếu plugin hỗ trợ | Log của từng plugin/goal |

Sơ đồ một build có thể có:

~~~text
JAVA_HOME -> JDK 21
        |
        v
Maven JVM 21
        |
        +-- Compiler -> javac JDK 21, --release 17
        |
        +-- Surefire -> JVM 17 (unit tests)
        |
        +-- Failsafe -> JVM 21 (integration tests)
        |
        +-- Javadoc -> javadoc JDK 21
        |
        +-- Plugin không hỗ trợ toolchain
                       |
                       v
                Có thể dùng Maven JVM 21
~~~

### 1.1. `mvn -version` không trả lời toàn bộ bài toán

Lệnh:

~~~bash
mvn -version
~~~

cho biết JDK đang chạy **Maven**. Khi một compiler/test plugin đã chọn toolchain khác, đây không còn là bằng chứng về JDK của `javac` hoặc test JVM.

Chiều ngược lại cũng quan trọng: toolchain JDK 21 **không làm một phiên bản Maven hoặc plugin cũ tự động tương thích với JVM 21**. Những thành phần chạy trong Maven JVM vẫn chịu yêu cầu runtime của Maven/plugin đó.

### 1.2. Toolchain không tự điều khiển mọi JVM con

Một plugin có thể fork Java process, gọi native executable, tạo container hoặc chạy logic ngay trong Maven JVM. Toolchain chỉ ảnh hưởng tới tác vụ đã tích hợp cơ chế đó. Ví dụ, Surefire có thể fork JVM theo `jdkToolchain`, nhưng một service Java được integration test khởi động qua Docker image sẽ dùng JDK của image, không tự đổi theo Failsafe.

Vì vậy khi lập ma trận JDK cần hỏi: **process nào thực thi compiler/test/plugin, process đó được tạo bởi ai và JDK được chọn bằng cơ chế gì?**

## 2. Maven Toolchains hoạt động ra sao?

Toolchain là mô tả về một bộ công cụ có sẵn trên máy build, ví dụ JDK 17 hoặc JDK 21 cùng đường dẫn cài đặt và metadata. Maven Toolchains Plugin chọn một JDK khớp yêu cầu, đưa lựa chọn vào **Maven session**, và các plugin toolchain-aware có thể truy cập lựa chọn đó.

~~~text
Máy / CI runner:
  JDK 17 ----+
             |
  JDK 21 ----+--> toolchains.xml hoặc JDK discovery
                             |
                             v
                    Maven Toolchains Plugin
                             |
                             v
                     Toolchain mặc định
                             |
                 +-----------+-----------+
                 |           |           |
               Compiler    Surefire     Javadoc
                 |           |           |
                 +-- Có thể có jdkToolchain riêng --+
~~~

Maven không thay đổi bản thân JVM đang chạy giữa các goals. Toolchain giúp plugin sử dụng **công cụ/JVM khác** khi plugin hỗ trợ cách làm đó.

### 2.1. Hai nơi cấu hình thường gặp

- **`~/.m2/toolchains.xml`**: mô tả các JDK đã cài trên máy và đường dẫn `jdkHome`.
- **`pom.xml`**: định nghĩa yêu cầu JDK mặc định và ngoại lệ ở những plugin cụ thể.

Với Maven 3, `~/.m2/toolchains.xml` là nơi thường dùng. Từ Maven 3.3.1 có tùy chọn `-t` / `--toolchains` để chỉ định file ở vị trí khác. Nếu môi trường CI dùng đường dẫn cài đặt riêng, nên tạo file toolchain cho agent tương ứng, không commit đường dẫn cá nhân vào POM.

### 2.2. Ưu điểm so với khai báo executable cố định

Khai báo `/home/developer/jdk-17/bin/javac` trong POM làm build khó chạy ở Windows hoặc runner khác. Toolchain cho phép POM chỉ yêu cầu version/vendor; môi trường tự cung cấp đường dẫn đúng.

Dù vậy, **toolchain là lựa chọn theo metadata**, không tự cài JDK, tải dependency hay sửa source code để phù hợp JDK.

## 3. Khai báo JDK 17 và JDK 21 trong `toolchains.xml`

Ví dụ file `~/.m2/toolchains.xml`:

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
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>

    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Các đường dẫn là ví dụ; thay bằng nơi cài JDK trên máy thực. Thư mục `jdkHome` phải chứa JDK hợp lệ, bao gồm các công cụ tương ứng, chứ không phải thư mục trống hoặc chỉ là JRE thiếu compiler.

### 3.1. Metadata phải mô tả JDK thật

`<version>` và `<vendor>` trong `<provides>` là thông tin để so khớp. Đặt `version=21` nhưng trỏ đến JDK 17 không biến nó thành JDK 21; đó là cấu hình sai.

Có thể kiểm tra bản cài thực tế:

~~~bash
/opt/jdks/temurin-17/bin/java -version
/opt/jdks/temurin-17/bin/javac -version
/opt/jdks/temurin-21/bin/java -version
/opt/jdks/temurin-21/bin/javac -version
~~~

Khi cần tái hiện lỗi JDK migration, nên lưu cả patch version và build number, vì bản cập nhật bảo mật hoặc bug fix có thể tạo khác biệt hành vi.

### 3.2. Một lỗi thường gặp: `17` không khớp `17.0.20`

Theo hướng dẫn Maven, trong cơ chế toolchain truyền thống, yêu cầu version đơn lẻ được so khớp với metadata tương ứng. Nếu `toolchains.xml` cung cấp `17.0.20` còn POM chỉ yêu cầu `17`, không thể mặc định chúng khớp nhau. Có thể dùng một version range phù hợp, ví dụ `[17,18)`, khi muốn cho phép nhiều bản JDK 17.x.

Metadata do công cụ discovery sinh có thể ghi full version, trong khi file tự tạo có thể ghi feature version. Tiêu chí vendor cũng cần khớp tên provider trong metadata; các công cụ tạo file khác nhau có thể dùng tên khác nhau.

**Nguyên tắc:** xem metadata thực tế rồi khai báo tiêu chí lựa chọn; không tự suy ra Maven sẽ hiểu hai cách ghi version/vendor là tương đương.

## 4. Chọn một JDK toolchain mặc định

Dùng goal `toolchain` của Maven Toolchains Plugin trong `pom.xml`:

~~~xml
<build>
    <plugins>
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
                        <version>21</version>
                        <vendor>temurin</vendor>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Goal lựa chọn JDK 21 phù hợp trong `toolchains.xml` và đặt nó trong session để các plugin có hỗ trợ sử dụng.

Cần hiểu giới hạn: đây là một **toolchain mặc định**, không phải một lệnh đổi `JAVA_HOME` hoặc JVM của Maven. Nếu Compiler Plugin hoặc Surefire có `jdkToolchain` riêng, phần cấu hình riêng có thể ghi đè lựa chọn mặc định đối với tác vụ của chúng.

### 4.1. Vì sao build có thể báo không tìm thấy toolchain?

Một số nguyên nhân:

- File `toolchains.xml` không ở nơi Maven đang đọc.
- Không có entry loại `jdk` phù hợp.
- `version`/`vendor` không khớp điều kiện POM.
- `jdkHome` không tồn tại hoặc trỏ sai.
- CI runner không cài bản JDK yêu cầu.
- Toolchains Plugin không được kích hoạt trong lifecycle như dự kiến.

Đây là lỗi lựa chọn công cụ. Thay `JAVA_HOME` ngẫu nhiên không phải cách phân tích đúng nếu toolchain matcher vẫn không tìm được entry.

## 5. JDK discovery trong Maven Toolchains Plugin mới

Từ **Maven Toolchains Plugin 3.2.0**, goal `select-jdk-toolchain` hỗ trợ phát hiện các JDK được cài ở vị trí thường gặp và qua biến môi trường. Có thể hiển thị kết quả với:

~~~bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
~~~

Ví dụ chọn một JDK thuộc nhánh 21:

~~~xml
<properties>
    <toolchain.jdk.version>[21,22)</toolchain.jdk.version>
</properties>

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
    </plugins>
</build>
~~~

Cơ chế này có thể lựa chọn giữa JDK đã được khai báo và JDK được phát hiện; không bắt buộc phải có `toolchains.xml` được viết tay nếu plugin đã tìm ra JDK phù hợp.

### 5.1. Discovery không phải auto-install

Nếu runner chưa cài JDK hoặc JDK nằm ở vị trí không được heuristic tìm thấy, plugin không tự tạo ra một bản JDK mới. Muốn CI tái lập được, cần chuẩn bị image/runner hoặc cấu hình discovery nhất quán.

Khi có nhiều JDK cùng phù hợp, plugin có các tiêu chí preference như LTS, current JDK, nguồn môi trường, version hoặc vendor. Không nên để một tiêu chí quá rộng tạo lựa chọn khác nhau ngoài dự kiến giữa máy và CI.

### 5.2. Khi nào dùng cơ chế nào?

| Phương pháp | Phù hợp | Lưu ý |
|---|---|---|
| `toolchains.xml` + `toolchain` | Agent được chuẩn hóa, muốn map JDK đến đường dẫn rõ ràng | Cần đồng bộ metadata, JDK và path |
| `select-jdk-toolchain` | Muốn tận dụng JDK discovery | Cần kiểm tra JDK được phát hiện và tiêu chí lựa chọn |
| `jdkToolchain` ở plugin | Từng nhóm plugin cần JDK khác nhau | Chỉ plugin hỗ trợ tham số mới áp dụng |
| Cấu hình `executable`/`jvm` riêng | Plugin cũ hoặc công cụ không có tích hợp toolchain | Kém portable, cần quản lý đường dẫn và xác minh |

Không cần kích hoạt hai cơ chế chọn mặc định cạnh tranh nhau trong cùng build nếu chưa xác định rõ thứ tự và mục đích.

## 6. Maven Compiler Plugin: chọn `javac` riêng

Compiler Plugin là ví dụ rõ nhất về khác biệt giữa **JDK của compiler** và **Java release target**.

### 6.1. Dùng toolchain JDK 21 nhưng biên dịch cho Java 17

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

Nếu toolchain mặc định chọn JDK 21, Compiler Plugin có thể dùng `javac` 21 rồi truyền `--release 17`. Tùy chọn release ràng buộc mức ngôn ngữ, class file version và API Java SE theo Java 17.

Nhưng `release=17` **không tự chọn JDK compiler 17**, không giới hạn API của dependency ngoài JDK và không bảo đảm test chạy trên Java 17.

### 6.2. Override compiler bằng `jdkToolchain`

Maven Compiler Plugin từ **3.6.0** hỗ trợ lựa chọn JDK riêng (với Maven 3.3.1 trở lên):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
            <vendor>temurin</vendor>
        </jdkToolchain>
        <release>17</release>
    </configuration>
</plugin>
~~~

Khi đó dù toolchain mặc định của session là 21, compiler có thể chọn JDK 17 khớp yêu cầu riêng của nó. Đây là cách phù hợp khi muốn xác nhận mã có thể được biên dịch bằng đúng JDK tối thiểu.

### 6.3. Phân biệt `source`/`target` với `release`

~~~xml
<configuration>
    <source>17</source>
    <target>17</target>
</configuration>
~~~

không hoàn toàn tương đương `release=17` khi compiler thực tế là JDK mới. Chỉ đặt `target` có thể tạo class file mức 17 nhưng vô tình dùng API Java SE chỉ có ở JDK 21. Khi chạy trên 17, binary có thể gặp linkage error.

Để phát hành cho Java 17, nên chọn `release=17` khi compiler hỗ trợ, kiểm tra class file version và chạy test trên runtime 17.

### 6.4. Main source và test source có mục tiêu riêng

Một dự án có thể để main code ở Java 17 nhưng dùng API 21 cho test code chạy trên Java 21. Khi đó cần phân biệt `release` của main với `testRelease` của test source và đảm bảo compiler phù hợp:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <jdkToolchain>
            <version>21</version>
        </jdkToolchain>
        <release>17</release>
        <testRelease>21</testRelease>
    </configuration>
</plugin>
~~~

Nếu dùng `testRelease=21`, không thể chạy những test classes này bằng JVM 17. Khi cần test cả hai phiên bản, có thể tách executions, source sets hoặc CI jobs, tùy cách tổ chức dự án.

Annotation processors và code generators cũng cần được tính tới: processor chạy trong môi trường compiler nhưng artifact cuối có thể nhắm Java thấp hơn. Không thể suy ra JDK của processor chỉ từ `release`.

## 7. Maven Surefire Plugin: JDK cho unit tests

Surefire thường chạy unit tests trong phase `test`. Với phiên bản hỗ trợ Toolchains, có thể dùng một JDK riêng cho test runner:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.5</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
            <vendor>temurin</vendor>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

Nếu configuration và toolchain đúng, JVM được Surefire fork để chạy test có thể là JDK 17 ngay cả khi Maven JVM đang chạy trên JDK 21.

### 7.1. `jdkToolchain` khác `jvm`

Surefire cũng có tham số `jvm` để chỉ định đường dẫn trực tiếp tới Java executable. `jdkToolchain` giúp chọn theo version/vendor thay vì cố định path. Không nên kết hợp cả hai mà chưa hiểu cơ chế ưu tiên và output thực tế của phiên bản Surefire đang dùng.

### 7.2. Kiểm tra cấu hình fork

Toolchain test áp dụng khi Surefire tạo JVM cho test. Nếu cấu hình tắt fork, chạy test trong Maven JVM hoặc dùng một provider cũ có cơ chế đặc biệt, kết quả có thể không như mong muốn. Hãy kiểm tra `forkCount`, `reuseForks`, provider và debug log.

### 7.3. Test runner có yêu cầu runtime tối thiểu

Bản `ForkedBooter` của Surefire/JUnit provider có thể được build cho phiên bản Java tối thiểu nhất định. Một JDK test quá cũ có thể ném `UnsupportedClassVersionError` trước khi thực thi test nghiệp vụ. Do đó, phải kiểm tra support matrix của plugin và framework, không chỉ metadata toolchain.

## 8. Maven Failsafe Plugin: JDK cho integration tests

Failsafe thường chạy ở phase `integration-test` và `verify`, có thể chọn JDK khác với Surefire.

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.5</version>
    <configuration>
        <jdkToolchain>
            <version>21</version>
            <vendor>temurin</vendor>
        </jdkToolchain>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Một cấu hình minh họa:

~~~text
Maven JVM:           JDK 21
Compiler:            javac 21, --release 17
Surefire:            JDK 17
Failsafe:            JDK 21
~~~

Lưu ý `mvn test` không tương đương `mvn verify`: lệnh đầu thường không chạy toàn bộ Failsafe integration-test/verify goals. Muốn kiểm tra cả hai nhóm, sử dụng phase thích hợp theo lifecycle đã cấu hình.

### 8.1. Test JVM không nhất thiết là JVM của ứng dụng tích hợp

Nếu integration test dùng Testcontainers, một microservice bên ngoài, một process Java do script tạo ra hoặc một application server độc lập, `jdkToolchain` của Failsafe thường chỉ quyết định **JVM của test runner**. Ứng dụng bên trong container hoặc tiến trình con riêng có thể chạy JDK khác.

Một hệ thống kiểm thử nhiều service cần ghi JDK của từng service, không dùng kết quả `java.version` của test runner thay thế tất cả.

## 9. Javadoc và những plugin sử dụng công cụ JDK

Maven Javadoc Plugin hỗ trợ `jdkToolchain` riêng:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <configuration>
        <jdkToolchain>
            <version>21</version>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

Khi module Java mới dùng Javadoc tags, API hoặc tính năng ngôn ngữ liên quan tới JDK mới, việc chọn `javadoc` phù hợp giúp tạo tài liệu nhất quán. Việc này không có nghĩa main class files được biên dịch bằng JDK 21.

### 9.1. Các nhóm plugin thường cần kiểm tra thêm

| Nhóm plugin | Ví dụ | Vai trò của toolchain |
|---|---|---|
| Phân tích dependencies | `maven-jdeps-plugin` | Chọn công cụ JDK để phân tích bytecode/module khi goal hỗ trợ |
| Kiểm tra API deprecated | `maven-jdeprscan-plugin` | Chọn `jdeprscan` tương thích |
| Xây runtime image | `maven-jlink-plugin`, `maven-jmod-plugin` | Dùng các module tools thích hợp |
| Ký artifact | `maven-jarsigner-plugin` | Chọn `jarsigner` từ JDK phù hợp |
| Tạo JAR | `maven-jar-plugin` | Một số version dùng toolchain cho `Build-Jdk-Spec`, không phải mọi tác vụ packaging |
| Code analysis | `maven-pmd-plugin` hoặc plugin bên thứ ba | Kiểm tra từng version/goal |
| Gọi chương trình ngoài | `exec-maven-plugin` goal `exec` | Phụ thuộc cách cấu hình và mức hỗ trợ toolchain |

**Không được suy ra plugin có mặt trong danh sách này là tự nhận `jdkToolchain` riêng.** Một plugin có thể chỉ sử dụng toolchain mặc định, chỉ hỗ trợ một số goal, hoặc không hỗ trợ ở version cũ.

### 9.2. Plugin chạy ngay trong Maven JVM

Một số plugin thực hiện code trực tiếp trong tiến trình Maven và không fork JVM. Toolchain không chuyển VM đang thực thi Mojo đó. Ví dụ goal `exec:java` có thể chạy class trong Maven JVM; không được mặc định nó chạy ở JDK được chọn bởi Maven Toolchains Plugin như một JVM con độc lập.

Nếu một plugin tự tạo Java process hoặc Docker container, cần kiểm tra chính xác cơ chế chọn runtime của plugin/process đó.

## 10. POM kết hợp: compile Java 17, test trên 17 và 21

Giả sử thư viện Java có runtime tối thiểu Java 17, nhưng nhóm muốn build bằng JDK 21 và kiểm tra trên cả runtime 17/21. POM có thể cấu hình toolchain mặc định JDK 21, compiler target Java 17, Surefire JDK 17 và Failsafe JDK 21:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jdk-compatibility-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <goals><goal>toolchain</goal></goals>
                    </execution>
                </executions>
                <configuration>
                    <toolchains>
                        <jdk>
                            <version>21</version>
                            <vendor>temurin</vendor>
                        </jdk>
                    </toolchains>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration><release>17</release></configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.5</version>
                <configuration>
                    <jdkToolchain>
                        <version>17</version>
                        <vendor>temurin</vendor>
                    </jdkToolchain>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.5</version>
                <configuration>
                    <jdkToolchain>
                        <version>21</version>
                        <vendor>temurin</vendor>
                    </jdkToolchain>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <jdkToolchain>
                        <version>21</version>
                    </jdkToolchain>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ cần file `toolchains.xml` có JDK 17 và 21, test dependencies phù hợp (chẳng hạn JUnit), và các bài integration test được Failsafe nhận diện. Đặt `jdkToolchain` cho Javadoc không tự chạy goal tạo Javadoc nếu lifecycle chưa gắn goal đó.

### 10.1. Cách các tác vụ chọn JDK trong ví dụ

| Tác vụ | JDK dự kiến | Lý do |
|---|---|---|
| Maven JVM | Theo launcher/`JAVA_HOME` | Toolchain không đổi Maven JVM |
| `compile`/`testCompile` | `javac` JDK 21 | Compiler dùng toolchain mặc định |
| Bytecode/API target | Java 17 | `--release 17` |
| Surefire unit tests | JVM JDK 17 | Override toolchain riêng |
| Failsafe integration tests | JVM JDK 21 | Override toolchain riêng |
| Javadoc | Công cụ JDK 21 | Override riêng |
| Plugin không toolchain-aware | Tùy plugin, có thể là Maven JVM | Cần kiểm tra |

Cấu hình này không chứng minh production cũng chạy Java 17 hoặc 21. Nó là cấu hình build/test; production image và startup runtime cần được quản lý riêng.

### 10.2. Vì sao thiếu JDK 17 nên làm CI thất bại?

Nếu một dự án tuyên bố hỗ trợ Java 17, việc thiếu JDK 17 trong job kiểm thử là một sự thiếu bằng chứng. Đừng tự động chuyển test về 21 để làm pipeline xanh rồi vẫn công bố hỗ trợ 17. Cần chuẩn bị toolchain 17 hoặc điều chỉnh công khai chính sách hỗ trợ.

## 11. Chạy cùng bộ test trên nhiều JDK

Một lifecycle Maven thường có một lựa chọn Surefire test JVM tại mỗi lần gọi. Muốn xác nhận thư viện hoạt động trên Java 17 và Java 21, có thể dùng **hai CI jobs** với profile hoặc cấu hình toolchain phù hợp.

Ví dụ hai profiles:

~~~xml
<profiles>
    <profile>
        <id>test-jdk17</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <configuration>
                        <jdkToolchain>
                            <version>17</version>
                        </jdkToolchain>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>

    <profile>
        <id>test-jdk21</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <configuration>
                        <jdkToolchain>
                            <version>21</version>
                        </jdkToolchain>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Sử dụng `pluginManagement` hoặc cấu hình plugin chung để quản lý version thống nhất. Tránh đặt một `jdkToolchain` cố định khác ở cấu hình chung khi chưa xác định Maven sẽ merge/override cấu hình profile ra sao.

Chạy từng job độc lập:

~~~bash
mvn -Ptest-jdk17 clean test
mvn -Ptest-jdk21 clean test
~~~

### 11.1. Test cùng artifact có ý nghĩa mạnh hơn hai lần build khác nhau

Nếu mục tiêu là xác nhận runtime compatibility, có thể build một artifact bằng `--release 17` rồi dùng đúng artifact đó để chạy test trên cả JDK 17 và 21:

~~~text
Compile once (javac 21 --release 17)
                 |
                 v
             Artifact A
               /    \
              v      v
       Test JDK 17   Test JDK 21
~~~

Nếu mỗi CI job build lại bằng dependency/profile/compiler khác nhau, kết quả khác biệt có thể xuất phát từ **artifact khác nhau** chứ không chỉ do runtime. Khi cần, lưu hash artifact và thông tin compiler để kiểm tra.

### 11.2. Không để profile thay đổi cả nội dung test vô tình

Một profile dành cho Java 17 có thể bật/tắt cả dependencies, includes/excludes, Java release hoặc system properties. Điều này dễ làm test “xanh” vì đã bỏ qua chính ca kiểm thử cần thiết. Cần ghi rõ profiles và test inventory thực tế cho từng job.

## 12. Multi-module Maven: không phải module nào cũng dùng cùng target

Một reactor có thể có:

~~~text
parent
  +-- api-contract-java17
  +-- service-java21
  +-- integration-tests
  +-- docs
~~~

- `api-contract-java17` cần phát hành class/API ở mức 17.
- `service-java21` có thể dùng API 21.
- `integration-tests` cần môi trường JDK của dịch vụ mục tiêu.
- `docs` có thể chọn Javadoc 21.

Trong parent POM, nên pin plugin versions và những mặc định phù hợp. Child module chỉ override khi có yêu cầu rõ ràng.

### 12.1. Phân biệt `pluginManagement` và `plugins`

`pluginManagement` cho phép quản lý cấu hình/version để plugin được kích hoạt kế thừa sử dụng; nó không tự chạy mọi goal chỉ vì plugin xuất hiện ở đó. Kiểm tra lifecycle bindings và `build/plugins` khi một cấu hình toolchain tưởng như được đặt nhưng không có tác dụng.

### 12.2. Cẩn thận chiều phụ thuộc giữa module 17 và 21

Một module cần chạy trên Java 17 không nên phụ thuộc runtime vào code chỉ có class file mức Java 21. Ngược lại, module 21 có thể sử dụng thư viện được biên dịch ở mức 17 nếu API/logic phù hợp.

`--release 17` của module đầu tiên không thể làm cho dependency JAR được build ở mức 21 tương thích ngược. Cần kiểm tra class file version và yêu cầu runtime của các dependency transitively used.

### 12.3. Annotation processors và generated sources

Annotation processor có thể yêu cầu JDK mới hơn runtime tối thiểu của artifact. Ví dụ, processor chạy với javac 21 và tạo source được biên dịch bằng `--release 17`. Điều này có thể hợp lệ.

Nhưng nếu chọn javac 17 chỉ vì muốn hỗ trợ runtime 17, một processor chỉ chạy trên JDK 21 có thể thất bại. Cần tách JDK dùng chạy compiler/processor khỏi target API/bytecode của artifact, và kiểm tra generated code không dùng API ngoài target.

## 13. Kiểm chứng thay vì chỉ nhìn POM

### 13.1. Ghi nhận Maven JVM

~~~bash
mvn -version
~~~

Lưu Maven version, Java version, vendor và Java home.

### 13.2. Xem JDK Toolchains Plugin phát hiện

~~~bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
~~~

Nếu dùng file thủ công, so sánh output với những entry trong `toolchains.xml` và đường dẫn JDK trên runner.

### 13.3. Bật Maven debug log

~~~bash
mvn -X clean verify
~~~

Tìm các thông tin cụ thể:

- Toolchain mặc định được chọn là JDK nào?
- Compiler có fork/call `javac` từ toolchain nào?
- Surefire và Failsafe khởi chạy JVM nào?
- Javadoc, jdeps hoặc signing tool dùng executable nào?
- Plugin có trực tiếp chạy trong Maven JVM không?

Không giả định một thông điệp log cố định ở mọi version plugin.

### 13.4. In JDK trong test

Ví dụ JUnit Jupiter:

~~~java
import org.junit.jupiter.api.Test;

class TestRuntimeInfo {
    @Test
    void showJavaRuntime() {
        System.out.println(
            "java.version=" + System.getProperty("java.version"));
        System.out.println(
            "java.vendor=" + System.getProperty("java.vendor"));
        System.out.println(
            "java.home=" + System.getProperty("java.home"));
    }
}
~~~

Nếu test runner in Java 21 trong khi `jdkToolchain` yêu cầu 17, cần kiểm tra effective POM, Surefire fork configuration và cách chọn runtime trước khi kết luận test đã xác minh Java 17.

### 13.5. Xem class file version bằng `javap`

~~~bash
javap -verbose -classpath target/classes com.example.App
~~~

Một số mức phổ biến:

| Java | Class file major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

`major version: 61` cho biết class file ở mức Java 17, nhưng không chứng minh dependency bên ngoài cũng hỗ trợ runtime 17, hoặc các test đã chạy trên runtime đó.

### 13.6. Xem effective POM và active profiles

~~~bash
mvn help:effective-pom
mvn help:active-profiles
~~~

Trong dự án dùng parent POM và profile phức tạp, đây là cách xem cấu hình cuối cùng. Khi một plugin chọn sai JDK, cần xác định cấu hình nào đã được kế thừa hoặc override, không chỉ nhìn một đoạn XML trong module con.

## 14. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra đầu tiên |
|---|---|---|
| Không có toolchain khớp | JDK chưa cài, metadata version/vendor không khớp | `toolchains.xml` và discovery |
| Maven không chạy trên JDK mới | Maven/plugin runtime không hỗ trợ | `mvn -version` và ma trận hỗ trợ |
| `UnsupportedClassVersionError` của `ForkedBooter` | Test JVM quá cũ cho test runner/provider | Surefire version và JVM fork |
| `UnsupportedClassVersionError` của class ứng dụng | Bytecode target mới hơn test JVM | `--release`, `javap`, test runtime |
| Test chạy trên JDK của Maven | Surefire không chọn toolchain mong đợi hoặc không fork | Effective POM, debug logs, `forkCount` |
| Compile xanh, runtime báo `NoSuchMethodError` | Dùng API mới ở runtime cũ hoặc dependency mismatch | `--release` và dependency tree |
| Javadoc dùng JDK sai | Toolchain override không hiệu lực hoặc plugin không hỗ trợ | Javadoc Plugin config/version |
| Plugin codegen dùng JDK sai | Plugin chạy trong Maven JVM hoặc có executable riêng | Plugin goal docs và logs |
| Local xanh, CI fail | JDK inventory khác, metadata sai | `jdkHome`, vendor, full version |
| Parent cấu hình nhưng module không dùng | Plugin chưa kích hoạt hoặc profile/child override | Effective POM |
| Surefire 17 nhưng service IT 21 | Test runner/container runtime khác nhau | Process/container `java.version` |

### 14.1. Không thể dùng Toolchains để lách yêu cầu của Maven plugin

Nếu plugin được build bằng class file chỉ chạy trên Java 21 nhưng Maven JVM đang là 17, plugin có thể không nạp được. Toolchain compiler 21 không giải quyết lỗi đó, vì chính **plugin Mojo** cần chạy trong Maven JVM. Khi đó phải chọn Maven runtime phù hợp hoặc phiên bản plugin tương thích.

### 14.2. Đừng sửa lỗi class file bằng cách chỉ thay `JAVA_HOME`

Nếu Maven compile với JDK 21 và `release=21` nhưng Surefire test JVM là JDK 17, lỗi `UnsupportedClassVersionError` là hợp lý. Giải pháp phải phù hợp hợp đồng: hoặc build/test classes cho 17, hoặc chọn test JVM 21 nếu đó mới là runtime được hỗ trợ.

### 14.3. Tránh xung đột cấu hình `jdkToolchain` và `jvm`

Một số plugin hỗ trợ nhiều cách chỉ JVM. Khi kết hợp path thủ công, toolchain mặc định và plugin-specific toolchain, kết quả có thể khác điều người đọc POM dự đoán. Chỉ dùng một cách rõ ràng cho từng tác vụ, hoặc tài liệu hóa quyền ưu tiên và kiểm tra log.

## 15. Quy trình áp dụng cho dự án Java migration

### Bước 1: Lập bảng yêu cầu phiên bản

Ví dụ:

| Thành phần | Yêu cầu JDK | Mục tiêu |
|---|---|---|
| Maven core + plugin mojos | JDK 21 | Phù hợp build tool/plugin versions |
| Compiler | JDK 21 + `--release 17` | Artifact hỗ trợ Java 17 |
| Unit test | JDK 17 và 21 | So sánh runtime behavior |
| Integration test | JDK 21 | Kiểm tra môi trường runtime mới |
| Javadoc/API tools | JDK 21 | Hỗ trợ công cụ/module hiện đại |

Chọn ma trận dựa trên chính sách sản phẩm, không áp dụng máy móc cho mọi repository.

### Bước 2: Chuẩn hóa máy build và CI

Cài các JDK cần thiết từ nguồn tin cậy, ghi version/build/vendor và cấu hình toolchains. Cần có quy trình cập nhật patch bảo mật. Tránh lưu đường dẫn cá nhân trong parent POM dùng chung.

### Bước 3: Chọn toolchain mặc định

Dùng `toolchain` và `toolchains.xml`, hoặc `select-jdk-toolchain` với tiêu chí đã định. Xác minh matcher thực sự tìm thấy JDK mong muốn.

### Bước 4: Override theo nhóm plugin, không theo cảm tính

Compiler, Surefire, Failsafe và Javadoc có thể cần các JDK khác nhau. Với plugin khác, đọc tài liệu xem có toolchain-aware không, áp dụng cho goal nào và có tham số `jdkToolchain` riêng không.

### Bước 5: Kiểm soát target và dependency

Thiết lập `--release` khi phát hành cho runtime thấp hơn compiler, kiểm tra class file version và dependency ngoài JDK. Không để thư viện chỉ chạy Java 21 lọt vào artifact được quảng bá hỗ trợ 17.

### Bước 6: Chạy kiểm thử đúng ma trận

Dùng CI jobs/profiles rõ ràng để chạy unit tests và integration tests trên các runtime cần hỗ trợ. Khi cần so sánh runtime behavior, ưu tiên dùng **cùng artifact** trên nhiều JDK.

### Bước 7: Lưu bằng chứng

Ghi Maven version, Maven JVM, compiler toolchain, Surefire/Failsafe runtime, artifact hash, active profiles và kết quả test. Mọi lỗi chênh lệch môi trường cần có thể tái hiện từ dữ liệu này.

## 16. Những hiểu nhầm phổ biến

**“`mvn -version` hiển thị Java 21 nghĩa là test đang dùng 21.”** Không. Surefire/Failsafe có thể fork một JVM khác.

**“Chọn toolchain 17 là đủ để đảm bảo tương thích Java 17.”** Không. Cần kiểm tra API/bytecode, dependency và hành vi runtime.

**“`release=17` buộc phải dùng javac 17.”** Không. Javac mới hơn có thể biên dịch với release target cũ được hỗ trợ.

**“Maven Toolchains tự đổi JVM chạy Maven.”** Không. Maven JVM đã được chọn khi khởi động lệnh Maven.

**“Mọi plugin sẽ dùng toolchain mặc định.”** Không. Chỉ plugin/goal có hỗ trợ và chưa override mới có thể dùng lựa chọn đó.

**“`jdkToolchain` trong Compiler Plugin tự đổi JDK của Surefire.”** Không. Compiler và test có thể chọn riêng.

**“`mvn test` kiểm tra toàn bộ integration tests.”** Không nếu dự án dùng Failsafe ở các phase `integration-test`/`verify`.

**“JDK discovery sẽ cài JDK chưa có.”** Không. Nó phát hiện JDK đã được cài hoặc đã được cung cấp.

**“`17` luôn khớp `17.0.x`.”** Không nhất thiết trong matcher truyền thống; cần hiểu metadata và version range.

**“Một test JVM 21 nghĩa là server trong Docker cũng dùng 21.”** Không. Runtime của process/container độc lập.

**“Plugin toolchain-aware nghĩa là code của plugin chạy trong JDK toolchain.”** Không phải luôn vậy: phần Mojo có thể vẫn chạy trong Maven JVM.

## 17. Checklist trước khi chuẩn hóa build đa JDK

- [ ] Đã phân biệt Maven JVM, compiler JDK, test JVM và JDK tools.
- [ ] Đã ghi Maven/plugin versions và yêu cầu runtime của chúng.
- [ ] Đã tạo `toolchains.xml` hợp lệ hoặc cấu hình JDK discovery.
- [ ] Đã xác minh `jdkHome`, vendor, version và tiêu chí khớp.
- [ ] Đã chọn toolchain mặc định rõ ràng.
- [ ] Đã kiểm tra Compiler Plugin `jdkToolchain` nếu cần override.
- [ ] Đã đặt `--release` phù hợp với runtime tối thiểu.
- [ ] Đã kiểm tra test classes và dependency không vượt runtime target.
- [ ] Đã cấu hình Surefire và Failsafe đúng JDK.
- [ ] Đã phân biệt test runner JVM với JVM của service/container.
- [ ] Đã xác minh Javadoc/`jdeps`/`jlink` và plugin khác có hỗ trợ toolchain.
- [ ] Đã xem active profiles, effective POM và cấu hình plugin executions.
- [ ] Đã xác minh JDK trong debug log và trong test code.
- [ ] Đã xem class file major version của artifact.
- [ ] Đã chạy test trên runtime tối thiểu và runtime mục tiêu.
- [ ] Đã lưu log/toolchain identity và artifact hash trong CI.

## 18. Tài liệu Apache Maven tham khảo

- [Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains): mô hình toolchains, `toolchains.xml`, toolchain mặc định và lựa chọn JDK riêng cho một số plugin.
- [Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): các goals `toolchain` và `select-jdk-toolchain`.
- [JDK Discovery Mechanism](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html): phát hiện JDK, version/vendor và tiêu chí lựa chọn.
- [Maven Compiler Plugin – Compiling Sources Using A Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html): `jdkToolchain` và compiler khác Maven runtime.
- [Maven Surefire – Using Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html): test JVM bằng toolchain.
- [Maven Failsafe – Using Toolchains](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/toolchains.html): integration test JVM.
- [Maven Javadoc Plugin](https://maven.apache.org/plugins/maven-javadoc-plugin/javadoc-mojo.html): tham số `jdkToolchain`.

Các phiên bản plugin trong ví dụ là các version minh họa đã có tài liệu tương ứng. Khi tích hợp vào dự án thật, cần kiểm tra support matrix và cấu hình của chính version Maven/plugin đã pin.

## 19. Kết luận

Maven Toolchains cho phép chọn JDK dùng bởi các Maven plugin có hỗ trợ mà **không phải đổi JVM chạy Maven**. Maven Toolchains Plugin có thể đặt JDK mặc định; Compiler, Surefire, Failsafe và Javadoc có thể chọn JDK riêng bằng `jdkToolchain` trong các phiên bản hỗ trợ. Cùng lúc, `--release` quyết định mức ngôn ngữ, API chuẩn và bytecode được biên dịch, còn JDK test runtime quyết định nơi hành vi thực tế được kiểm chứng.

Đối với Java Advance Compatibility Migration, điều quan trọng là **không suy ra mọi thứ từ `JAVA_HOME` hoặc một dòng cấu hình POM**. Hãy lập ma trận compiler–test–plugin, cấu hình JDK toolchain theo version/vendor có thể tái tạo, chạy đúng CI jobs, xác minh runtime bằng log và `java.version`, rồi lưu bằng chứng về artifact. Khi đó nhóm mới có cơ sở nói rằng mã đã được biên dịch và kiểm thử trên các JDK thực sự được hỗ trợ.
