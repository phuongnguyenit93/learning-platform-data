# maven-compiler-plugin và cấu hình release

Khi nâng một dự án Java, thay đổi phiên bản JDK trên máy hoặc trong CI chỉ là bước đầu. Mã nguồn có thể được biên dịch bằng JDK 21 nhưng vẫn cần chạy trên Java 17; ngược lại, một dự án cấu hình target Java 8 có thể vô tình gọi API mới của JDK 17 và chỉ thất bại khi triển khai lên JVM 8. Những vấn đề này thường đến từ việc nhầm lẫn giữa **JDK dùng để build**, **mức cú pháp Java cho phép**, **phiên bản class file** và **API của Java Platform mà code được phép sử dụng**.

Trong Maven, maven-compiler-plugin là thành phần chủ yếu điều khiển việc biên dịch Java trong lifecycle. Tham số **release** của compiler plugin giúp thiết lập mục tiêu tương thích chính xác hơn so với chỉ dùng source và target. Bài học này thuộc **Java Advance Compatibility Migration**, chương **Maven và Gradle**, tập trung vào cách cấu hình, kiểm chứng và chuyển đổi maven-compiler-plugin khi nâng Java, cũng như cách đối chiếu với cơ chế release và toolchain tương ứng trong Gradle.

Mục tiêu sau bài học là đọc được cấu hình compiler thực tế của một Maven project, chọn đúng release, tránh dùng API Java quá mới ngoài ý muốn, phân biệt Maven runtime với JDK compiler, xử lý multi-module/annotation processing và xây dựng quy trình kiểm thử tương thích trước khi chuyển production.

## 1. Bốn phiên bản thường bị nhầm lẫn

Một dự án Java có thể có ít nhất bốn mức phiên bản độc lập:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| JDK chạy Maven | JVM thực thi Maven và một số Maven plugins | Maven chạy trên JDK 21 |
| JDK compiler | Bộ javac được dùng để biên dịch project | javac từ JDK 21 |
| Java release target | Mức Java source, class file và Java Platform API được code nhắm tới | Java 17 |
| JRE/JDK production | Runtime thực sự chạy artifact | Java 17 |

Ngoài ra còn có Maven version, maven-compiler-plugin version, annotation processor version, Java agents và dependency bytecode baseline.

Ví dụ một project hợp lệ có thể:

~~~text
Maven process:        JDK 21
Compiler toolchain:   JDK 21
maven.compiler.release: 17
Produced bytecode:    Java 17 (major 61)
Production runtime:   JDK 17
~~~

Điều này khác với:

~~~text
Maven process:        JDK 17
Compiler toolchain:   JDK 17
maven.compiler.release: 21
~~~

Trường hợp thứ hai không hợp lệ nếu javac thực sự là của JDK 17, vì compiler đó không thể biên dịch target release Java 21. Cần nâng compiler JDK hoặc sửa release target.

### 1.1. Một nhầm lẫn cốt lõi

**JDK build mới hơn không đồng nghĩa artifact yêu cầu JDK mới hơn.** Một compiler mới có thể build cho release cũ nếu hỗ trợ release đó.

**Class file có phiên bản cũ không bảo đảm ứng dụng chỉ dùng API cũ.** Đây là lý do --release quan trọng hơn việc chỉ đặt target.

## 2. maven-compiler-plugin nằm ở đâu trong Maven lifecycle?

Với packaging jar hoặc các loại packaging có compiler lifecycle phù hợp, Maven thường chạy goal compile của maven-compiler-plugin khi tới pha compile, và goal testCompile khi tới pha test-compile.

~~~text
validate
   |
   v
generate-sources
   |
   v
process-sources
   |
   v
compile           <-- maven-compiler-plugin:compile
   |
   v
process-test-sources
   |
   v
test-compile      <-- maven-compiler-plugin:testCompile
   |
   v
test              <-- thường do maven-surefire-plugin
   |
   v
package
   |
   v
verify / install / deploy
~~~

Maven Compiler Plugin chủ yếu biên dịch source. Nó **không tự chạy unit tests**, không quyết định JVM chạy test và không bảo đảm mọi dependency có bytecode tương thích với target release.

Một câu lệnh:

~~~bash
./mvnw clean compile
~~~

biên dịch main sources sau khi xóa output cũ. Còn:

~~~bash
./mvnw clean verify
~~~

có thể đi qua các pha compile, test-compile, test, package và verify tùy plugin/lifecycle của dự án.

Với Windows, tùy repository có thể dùng mvnw.cmd thay cho ./mvnw. Nếu project chưa có Maven Wrapper, sử dụng lệnh mvn từ Maven installation đã được quản lý.

## 3. source, target và release khác nhau như thế nào?

Ba tham số thường gặp:

- **source:** xác định mức cú pháp Java được javac chấp nhận.
- **target:** xác định phiên bản class file mà javac tạo.
- **release:** trên compiler hỗ trợ --release, kết hợp mức cú pháp, class-file target và **bộ API Java Platform của release đích**.

### 3.1. source giới hạn cú pháp

Ví dụ:

~~~xml
<configuration>
    <source>8</source>
</configuration>
~~~

Khi compile với source level 8, code không thể sử dụng cú pháp được đưa vào Java 10, 14, 16 hoặc 17 như local variable type inference bằng var, switch expression, record hay sealed class.

Tuy nhiên, source không tự cấm tham chiếu API mới được thêm vào JDK compiler hiện tại.

### 3.2. target giới hạn class-file version

Ví dụ:

~~~xml
<configuration>
    <target>8</target>
</configuration>
~~~

javac cố tạo class file theo target Java 8, tương ứng major version 52. Điều này không có nghĩa mọi method từ thư viện chuẩn mà code gọi đã tồn tại ở Java 8.

### 3.3. release giới hạn cả cú pháp, bytecode và API nền tảng

Ví dụ:

~~~xml
<configuration>
    <release>8</release>
</configuration>
~~~

Trên compiler có hỗ trợ --release, Java code chỉ được biên dịch với các API Java Platform tương ứng release 8. Nếu code gọi một method chỉ xuất hiện ở Java 9, compiler sẽ báo lỗi dù JDK đang chạy javac có method đó.

### 3.4. Bảng so sánh

| Điều kiện | source=8 | target=8 | release=8 |
|---|---|---|---|
| Hạn chế cú pháp Java mới | Có | Không tự làm điều này | Có |
| Tạo class file Java 8 | Không tự đủ | Có | Có |
| Hạn chế Java SE API theo Java 8 | Không | Không | Có, với javac hỗ trợ --release |
| Hạn chế dependency bên thứ ba | Không | Không | Không |
| Quy định JVM chạy Maven | Không | Không | Không |
| Quy định JVM chạy test | Không | Không | Không |

**Khuyến nghị thông thường khi migrate:** ưu tiên dùng release cho một Java target duy nhất thay vì đặt source/target rời rạc.

## 4. Ví dụ thực tế: code build thành công nhưng chạy lỗi trên Java cũ

Java 9 giới thiệu List.of. Giả sử Maven được chạy trên JDK 17 và project cấu hình:

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
~~~

Source:

~~~java
import java.util.List;

public final class Sample {
    public static List<String> values() {
        return List.of("A", "B");
    }
}
~~~

Mã dùng cú pháp hợp lệ của Java 8. Nhưng method List.of không tồn tại ở Java 8.

Nếu compiler JDK mới biên dịch với source=8 và target=8 **mà không dùng bootclasspath/API signature của Java 8**, nó có thể tạo class file 52 có tham chiếu tới List.of. Khi chạy trên Java 8, lời gọi đó có thể gây NoSuchMethodError.

Đổi thành:

~~~xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
~~~

với compiler hỗ trợ --release sẽ khiến build báo lỗi ở List.of vì API không thuộc Java 8.

Đây là sự khác biệt có giá trị thực tế nhất của release.

### 4.1. source/target có thể phù hợp trong trường hợp nào?

Dự án rất cũ có thể bị ràng buộc bởi compiler hoặc hệ thống build chưa hỗ trợ --release. Khi đó phải quản lý bootclasspath hoặc API baseline theo cách thích hợp và kiểm thử trên runtime Java thấp nhất được hỗ trợ.

Với dự án đang chuyển sang JDK hiện đại, thông thường nên cập nhật Maven/compiler plugin và dùng release thay vì giữ cấu hình source/target thiếu kiểm soát.

### 4.2. release không kiểm tra mọi thứ

Cần nhớ --release chủ yếu hạn chế cú pháp, class file và API thuộc Java Platform. Nó **không bảo đảm**:

- Thư viện Maven bên thứ ba hỗ trợ runtime cũ.
- Java agent hoặc native dependency tương thích.
- Bytecode dependency nằm trong giới hạn target.
- Hành vi runtime giống nhau giữa các JDK.
- Framework, servlet container, JDBC driver và TLS policy tương thích.
- Các phiên bản runtime ngoài Java có cùng contract.

Cần có dependency validation và runtime tests bổ sung.

## 5. Cấu hình Maven Compiler Plugin cơ bản

Trong POM:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>migration-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version 3.13.0 trong ví dụ là một phiên bản đã hỗ trợ cấu hình release; khi áp dụng cần chọn bản compiler plugin phù hợp với Maven/JDK và chính sách dependency hiện tại của tổ chức. Không nên coi version trong ví dụ là “mới nhất” cho mọi thời điểm.

Với thuộc tính maven.compiler.release, plugin nhận release là 17 cho main Java compilation trong cấu hình thông thường. Việc khai báo plugin version rõ ràng giúp build bớt phụ thuộc vào default lifecycle mapping hoặc version đến từ parent không kiểm soát.

### 5.1. Cấu hình trực tiếp trong plugin

Thay vì property, có thể khai báo:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Hai cách là những lựa chọn cấu hình, không nhất thiết phải sử dụng cả hai cùng lúc. Nếu property, profile, plugin configuration và parent POM đặt các giá trị khác nhau, cần xem **effective configuration** mà Maven thực sự áp dụng.

### 5.2. Không nên trộn source/target/release vô ý

Một POM có cả:

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

dễ gây nhầm lẫn và có thể tạo cấu hình mâu thuẫn tùy version plugin và compiler options. Java javac không cho phép kết hợp --release với --source hoặc --target theo cách xung đột.

Nếu chọn release làm chuẩn, hãy loại bỏ các cấu hình source/target không còn cần thiết và xác nhận không có parent/profile/execution khác ghi đè.

## 6. Maven property và plugin configuration lấy giá trị từ đâu?

Một dự án lớn thường có nhiều lớp POM:

~~~text
company-parent/pom.xml
        |
        +--- service-parent/pom.xml
                  |
                  +--- app-api/pom.xml
                  +--- app-core/pom.xml
                  +--- app-server/pom.xml
~~~

Compiler plugin có thể được cấu hình qua:

- Parent POM.
- pluginManagement.
- plugins của module.
- Property trong POM.
- Maven profile.
- Command-line -D property.
- Settings/profile được kích hoạt ở môi trường.
- Goal execution riêng cho source set/module.

Do đó, chỉ tìm kiếm một chuỗi maven.compiler.release trong repository chưa đủ để khẳng định target đang dùng.

### 6.1. pluginManagement khác plugins

pluginManagement trong parent dùng để định nghĩa version/cấu hình mặc định cho plugin khi plugin được sử dụng. Nó không đồng nghĩa mọi goal tùy chọn sẽ được chạy trong mọi module. Với các goal được bind bởi default lifecycle, cấu hình plugin management có thể áp dụng khi plugin xuất hiện qua lifecycle mapping.

Ví dụ parent:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Child module có thể khai báo plugin cụ thể hoặc dùng lifecycle compiler binding tương ứng. Nếu cần một cấu hình khác ở module riêng, phải kiểm tra inheritance, merge và execution.

### 6.2. Đọc effective POM

Lệnh hữu ích:

~~~bash
./mvnw help:effective-pom
~~~

Có thể ghi ra file:

~~~bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
~~~

Trong multi-module project, cần chọn đúng module hoặc inspect effective POM của module chịu ảnh hưởng. Tên file chỉ là output chẩn đoán, không phải file cần commit vào source.

Xem active profiles:

~~~bash
./mvnw help:active-profiles
~~~

Xem giá trị property:

~~~bash
./mvnw help:evaluate -Dexpression=maven.compiler.release -DforceStdout
~~~

Lệnh trên hiển thị giá trị expression ở execution context phù hợp. Khi plugin có cấu hình trực tiếp khác, cần xem effective POM và compiler command thực tế, không chỉ property.

## 7. Xác định JDK thực sự mà Maven sử dụng

Câu lệnh đầu tiên khi điều tra:

~~~bash
./mvnw -version
~~~

Thông tin thường cho biết:

- Maven version.
- Java version.
- Java home.
- OS và các chi tiết môi trường.

Nhưng nó chỉ xác nhận JVM đang chạy Maven. Nếu dự án sử dụng **Maven Toolchains** hoặc compiler được cấu hình riêng, javac được chọn có thể đến từ một JDK khác.

### 7.1. Các nguồn JDK khác nhau

| Thành phần | Có thể dùng JDK nào? |
|---|---|
| Maven launcher | JAVA_HOME hoặc Java được wrapper/environment chọn |
| maven-compiler-plugin | JDK Maven đang chạy hoặc JDK toolchain/compilation setup |
| maven-surefire-plugin | JVM riêng theo cấu hình hoặc JVM build phù hợp |
| maven-failsafe-plugin | JVM integration tests theo cấu hình |
| javadoc plugin | Có thể dùng JDK toolchain hoặc executable riêng |
| Annotation processor | Thường chạy trong ngữ cảnh compiler được chọn |
| Production | JDK ở server/container khi triển khai |

Do đó, một dự án có thể compile bằng JDK 21 nhưng test bằng JVM khác. Cần xác định rõ, không giả định “chạy Maven bằng Java 21” đồng nghĩa tất cả plugin và test đều chạy bằng Java 21.

### 7.2. Môi trường developer và CI

Một lỗi phổ biến là developer dùng JDK 21 trong IDE, trong khi CI vẫn chạy Maven bằng JDK 17. POM đặt release 21; local compile thành công nhưng CI báo:

~~~text
error: release version 21 not supported
~~~

Giải pháp là cập nhật compiler toolchain của CI hoặc chọn lại release phù hợp. Không nên che lỗi bằng cách xóa release để build “thành công” với bytecode sai.

## 8. Maven Toolchains: tách JVM chạy Maven khỏi compiler JDK

Toolchains cho phép các plugin hỗ trợ toolchain chọn JDK theo tiêu chí thay vì chỉ dùng JDK chạy Maven.

Một use case:

~~~text
Maven chạy trên JDK 17
          |
          v
Toolchain chọn JDK 21
          |
          v
Compiler javac JDK 21
          |
          v
maven.compiler.release = 17
          |
          v
Artifact target Java 17
~~~

Điều này hữu ích khi hệ thống build có nhiều JDK hoặc khi cần Maven và một số plugin tiếp tục chạy trên JVM khác với compiler.

### 8.1. Toolchains file

Maven có thể dùng file cấu hình toolchains trong thư mục người dùng, thường là:

~~~text
~/.m2/toolchains.xml
~~~

Ví dụ minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
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

Đường dẫn và tên vendor là ví dụ. Cần khớp với JDK thật được cài đặt và criteria mà project yêu cầu.

### 8.2. Khai báo yêu cầu toolchain trong POM

Một cấu hình cổ điển có thể sử dụng maven-toolchains-plugin với goal toolchain:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.1.0</version>
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

Maven Toolchains Plugin có thêm những khả năng và goal khác theo version. Ví dụ trên minh họa cơ chế dựa vào file toolchains.xml và criteria; khi áp dụng nên dùng cấu hình được tài liệu của version hiện tại hỗ trợ.

### 8.3. Toolchain không thay thế release

Toolchain trả lời: “Dùng javac nào?”

Release trả lời: “Biên dịch cho mức Java nào?”

Vẫn cần cả hai khi dự án muốn compiler JDK 21 nhưng artifact target Java 17. Một project dùng JDK 21 toolchain mà không đặt release có thể tạo class file Java 21 và dùng các Java API mới ngoài dự kiến.

### 8.4. Plugin nào cũng dùng toolchain?

Không. Một plugin chỉ dùng toolchain nếu nó hỗ trợ và được cấu hình phù hợp. Build có thể có compiler dùng JDK 21, nhưng plugin kiểm thử, kiểm tra mã hoặc documentation sử dụng JVM Maven hoặc JDK khác.

Cần kiểm tra log, toolchain selection và các task thực tế để xác nhận.

## 9. Chọn release theo yêu cầu ứng dụng

Không nên đặt release bằng đúng JDK đang cài chỉ vì đó là phiên bản mới nhất. Release phải gắn với runtime được cam kết hỗ trợ.

Ví dụ:

| Loại sản phẩm | Release cần cân nhắc | Lý do |
|---|---|---|
| Dịch vụ nội bộ chỉ chạy trên JDK 21 | 21 | Có thể dùng ngôn ngữ/API Java 21 |
| Thư viện phải hỗ trợ Java 17+ | 17 | Consumer Java 17 cần tải được class |
| CLI còn hỗ trợ Java 11 | 11 | Giữ baseline tương ứng |
| Ứng dụng đang chuyển từng giai đoạn từ Java 8 | 8 tạm thời, sau đó nâng | Tách nâng compiler/build và nâng runtime |
| Multi-release library | Nhiều release với nguồn/tệp class phân tách | Cần cấu trúc đặc biệt, không chỉ một property |

Các quyết định còn cần xét framework, dependency, annotation processors, container/runtime và yêu cầu bảo mật.

### 9.1. Release target nên là yêu cầu sản phẩm

Nếu chính sách sản phẩm tuyên bố Java 17 là runtime tối thiểu, compiler release 17 là baseline hợp lý. Nhưng nếu runtime production vẫn có node Java 11, chọn release 17 sẽ làm những node đó không tải được class file.

Nên xác định:

- Tập runtime thực sự đang triển khai.
- Phiên bản thấp nhất còn được hỗ trợ.
- Khả năng nâng runtime đồng bộ.
- Dependency ecosystem đã hỗ trợ version đích chưa.
- Kế hoạch rollback khi release mới được deploy.

Không nên chuyển maven.compiler.release lên 21 trước khi production runtime được nâng ít nhất lên mức tương ứng.

## 10. Class-file version và cách xác minh artifact

Một số mốc phổ biến:

| Java | Class-file major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Ví dụ muốn kiểm tra class sau compile:

~~~bash
javap -verbose -classpath target/classes com.example.Main
~~~

Trong output có thể thấy:

~~~text
major version: 61
~~~

Nếu class được tạo theo release Java 17 thì major version tương ứng thường là 61.

Có thể kiểm tra file class cụ thể:

~~~bash
javap -verbose target/classes/com/example/Main.class
~~~

Class-file version chỉ cho biết mức bytecode, **không đủ chứng minh** compatibility với dependency hoặc API ngoài Java Platform.

### 10.1. Khi gặp UnsupportedClassVersionError

Ví dụ:

~~~text
UnsupportedClassVersionError:
class file version 65.0,
this Java Runtime only recognizes ... 61.0
~~~

Điều này gợi ý artifact được biên dịch cho Java 21 nhưng đang chạy trên runtime chỉ hỗ trợ tối đa Java 17.

Cách xử lý:

1. Xác nhận JVM production thực tế.
2. Xác định class nào bị lỗi: application hay dependency.
3. Kiểm tra release của module chứa class.
4. Nếu cần runtime Java 17, biên dịch lại application theo release 17 và sử dụng dependency tương thích.
5. Nếu feature cần Java 21, nâng runtime theo kế hoạch thay vì giảm target một cách máy móc.

## 11. Multi-module Maven: một release chung hay nhiều release?

Trong một dự án nhiều module, không phải module nào cũng có cùng yêu cầu.

Ví dụ:

~~~text
platform-parent
  |
  +-- core-api          Java 11 baseline
  +-- business-core     Java 17 baseline
  +-- service-app       Java 21 runtime
  +-- integration-test  Java 21 test environment
~~~

Một lựa chọn là đặt release 17 ở parent rồi override những module cần Java 11 hoặc 21. Nhưng cần quan tâm **hướng dependency**:

- Module target Java 11 không nên phụ thuộc vào artifact chỉ chạy trên Java 17.
- Module target Java 17 không thể nạp class file yêu cầu Java 21 trên runtime Java 17.
- Module Java 21 có thể tiêu thụ artifact Java 17 thông thường nếu API/dependency tương thích.

### 11.1. Parent POM

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

### 11.2. Module cần baseline khác

~~~xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
~~~

Việc override property có thể là lựa chọn rõ ràng, nhưng chỉ đúng nếu plugin đang đọc property đó và không có cấu hình trực tiếp trong parent/profile ghi đè.

### 11.3. Kiểm tra đúng module

~~~bash
./mvnw -pl core-api -am clean verify
~~~

Tùy cấu trúc và tên module, -pl chọn project còn -am thêm những dependency modules cần build cùng. Cần chạy validation cho các module có baseline khác nhau, thay vì chỉ chạy ở root và xem build tổng “đã xanh”.

### 11.4. Không sử dụng release như công cụ thay thế kiến trúc module

Nếu một module cần dùng Java 21 API còn một module khác phải hỗ trợ Java 11, không thể đạt cả hai bằng cách chuyển property qua lại trong cùng một source set. Có thể cần tách module, sử dụng adapter hoặc multi-release JAR khi use case thật sự yêu cầu và đáp ứng giới hạn kỹ thuật.

## 12. Annotation processing và generated source

Nhiều dự án Java sử dụng Lombok, MapStruct, Hibernate metamodel, Dagger, QueryDSL hoặc annotation processors tự viết. Khi nâng JDK compiler, annotation processor có thể bị lỗi dù code do con người viết không thay đổi.

Các ranh giới cần phân biệt:

1. Compiler JDK thực sự chạy processor.
2. API/compiler internals mà processor sử dụng.
3. Source mà processor tạo ra.
4. Release target của source được compile.
5. Thứ tự generate-sources và compile.
6. Version của processor và dependency phát sinh.

### 12.1. Vì sao --release không bảo vệ processor khỏi JDK mới?

Giả sử JDK 21 compiler biên dịch project với release 17. Annotation processor thường vẫn chạy trong ngữ cảnh javac/JDK 21, không phải trong một JVM 17 giả lập.

Nếu processor phụ thuộc vào internals của javac, nó có thể gặp IllegalAccessError hoặc lỗi tương tự khi compiler internals thay đổi. Điều này cần được xử lý bằng việc nâng processor hoặc chọn phiên bản compiler phù hợp, không bằng cách chỉ đổi release.

### 12.2. Khai báo annotationProcessorPaths

Ví dụ maven-compiler-plugin có thể cấu hình annotation processor path:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>org.mapstruct</groupId>
                <artifactId>mapstruct-processor</artifactId>
                <version>1.6.3</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Đây là ví dụ về cách đặt processor lên processor path; version được nêu chỉ để minh họa cú pháp, phải chọn bản tương thích với dependency MapStruct và JDK thực tế.

Trong các JDK mới, việc tự động phát hiện processor có thể thay đổi theo chính sách bảo mật và compiler defaults. Nên khai báo processor rõ ràng, không dựa vào việc javac ngầm quét toàn bộ classpath.

### 12.3. Không chỉnh sửa generated code trực tiếp

Nếu generated source sử dụng một Java API quá mới hoặc cú pháp không hợp với release, nên sửa generator version/configuration/source template. Sửa output trong target/generated-sources chỉ có hiệu lực tạm thời và có thể bị ghi đè ở lần build sau.

### 12.4. Processor cần toolchain riêng?

Một số dự án có nhiều source generators hoặc plugin không hỗ trợ toolchains. Phải xem từng goal để biết JDK nào chạy phần đó. Maven.compiler.release không ép mọi task generate source chạy trên một JDK cụ thể.

## 13. Test compile và JVM chạy test là hai việc khác nhau

Maven Compiler Plugin cũng xử lý test compilation trong default lifecycle. Nhưng JVM thực thi test thường do Surefire/Failsafe và cấu hình liên quan điều khiển.

~~~text
maven-compiler-plugin:testCompile
          |
          v
target/test-classes
          |
          v
maven-surefire-plugin:test
          |
          v
JVM chạy unit tests
~~~

### 13.1. Vì sao compile được nhưng test vẫn lỗi?

Các tình huống:

- Test được biên dịch theo release 17 nhưng Surefire fork JVM Java 11.
- Runtime test thiếu dependency do scope sai.
- Framework/test agent chưa hỗ trợ JDK mới.
- Code dùng reflection vào JDK internals và bị strong encapsulation chặn.
- TLS/certificate policy khác giữa JDK cũ và mới.
- Generated test sources có class-file version khác.
- Test environment cần mở module cho framework mock.

Để bảo đảm tương thích runtime, hãy chạy test trên đúng JDK được sản phẩm hỗ trợ. Nếu cần hỗ trợ Java 17 và 21, CI nên có matrix hai runtime.

### 13.2. Test code có thể có baseline khác main code

Một số project chỉ phân phối main artifact cho Java 17 nhưng chạy test bằng JDK 21 và dùng công cụ test mới. Điều này có thể hợp lệ nếu cấu hình rõ ràng. Tuy nhiên, đừng để test configuration vô tình che đi việc main artifact dùng API mới.

Compiler plugin có thể hỗ trợ cấu hình test compilation riêng tùy version. Khi cần khác biệt, hãy đọc tham số của phiên bản plugin đang dùng và kiểm tra effective executions. Không suy luận rằng một property main release tự động giải quyết mọi trường hợp test-source đặc biệt.

## 14. Preview features và --enable-preview

Một số tính năng ngôn ngữ Java xuất hiện dưới dạng preview trước khi được final. Nếu source sử dụng preview feature, compiler có thể yêu cầu --enable-preview, đồng thời release thường phải khớp với release của compiler đang dùng cho preview đó.

Ví dụ nguyên lý với JDK có preview:

~~~bash
javac --enable-preview --release 21 PreviewExample.java
~~~

Cú pháp code nào thật sự là preview phụ thuộc phiên bản JDK. Không nên bật preview chỉ vì project đã nâng compiler, và không nên đưa --enable-preview vào mọi module như một setting mặc định.

### 14.1. Maven compilerArgs

Một cấu hình có thể chứa:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>21</release>
        <compilerArgs>
            <arg>--enable-preview</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Nếu dùng preview code, JVM chạy test và production cũng có thể cần --enable-preview theo yêu cầu của release tương ứng. Các bản Java không bảo đảm binary preview tương thích giữa các release.

**Preview không phải đường migration tương thích mặc định.** Đó là quyết định có rủi ro ngôn ngữ/runtime cần ghi nhận rõ.

## 15. Lỗi thường gặp khi cấu hình maven-compiler-plugin

### 15.1. Release version not supported

Thông báo:

~~~text
error: release version 21 not supported
~~~

Nguyên nhân phổ biến là javac đang dùng quá cũ để hỗ trợ release 21. Hãy xem Maven -version, compiler toolchain selection và log thực tế.

Giải pháp: dùng compiler JDK hỗ trợ Java 21 hoặc chọn release phù hợp với baseline hiện có.

### 15.2. Source option hoặc target option không còn hỗ trợ

Một JDK mới có thể không hỗ trợ một source/target rất cũ. Ví dụ dự án cũ yêu cầu Java 6 trên một compiler không còn hỗ trợ mục tiêu đó.

Giải pháp: xác định baseline cần giữ, xem có cần công cụ build riêng bằng JDK cũ được kiểm soát hay phải nâng runtime tối thiểu. Không thể buộc javac hiện đại tạo mọi class-file target lịch sử.

### 15.3. NoSuchMethodError trên runtime cũ

Nếu class file target Java 8 nhưng code gọi Java 11 API, có thể đã cấu hình source/target mà không giới hạn platform APIs.

Giải pháp: dùng release đúng và xây runtime test matrix. Kiểm tra cả dependency bytecode.

### 15.4. Cannot find symbol sau khi bật release

Ví dụ khi chuyển source/target=8 sang release=8, compiler không tìm thấy List.of. Đây có thể là một lỗi hợp lệ phát hiện API dependency trước đây bị che giấu.

Giải pháp: dùng API được hỗ trợ ở Java 8, nâng baseline nếu yêu cầu sản phẩm cho phép, hoặc tách implementation theo các release có chính sách rõ ràng.

### 15.5. --release cannot be used with --source/--target

Cấu hình mâu thuẫn có thể do parent POM, profile, plugin configuration hoặc compilerArgs tự thêm options.

Giải pháp: bỏ thiết lập chồng chéo và lấy release làm nguồn chuẩn khi phù hợp.

### 15.6. Invalid target release

Thông báo kiểu:

~~~text
invalid target release: 21
~~~

thường chỉ ra compiler không biết target yêu cầu. Cần xác định javac đang thực sự chạy, không chỉ Java version của IDE.

### 15.7. Bad class file has wrong version

Ví dụ:

~~~text
bad class file: library.jar
class file has wrong version 65.0, should be 61.0
~~~

Dependency có thể được biên dịch cho Java 21 nhưng compiler/runtime đang dùng chỉ hỗ trợ Java 17.

Giải pháp: dùng bản dependency có baseline phù hợp hoặc nâng compiler/runtime theo kế hoạch. Release của application không làm dependency JAR tự chuyển thành bytecode cũ.

### 15.8. Lỗi annotation processor

Ví dụ:

~~~text
IllegalAccessError
ExceptionInInitializerError
NoClassDefFoundError
~~~

trong processor khi nâng compiler có thể phản ánh version của Lombok/processor/tooling không phù hợp với JDK. Cần xem stack trace, nâng processor và kiểm tra compiler JDK, thay vì tắt release.

## 16. Maven Wrapper, plugin version và reproducible build

Dự án nên hạn chế khác biệt giữa developer, CI và release pipeline.

Một baseline có thể gồm:

- Maven Wrapper hoặc Maven version được kiểm soát.
- Compiler plugin version rõ ràng.
- JDK toolchain được mô tả.
- maven.compiler.release được quản lý.
- Processor versions cố định.
- Dependency versions/BOM được kiểm soát.
- Test matrix runtime.
- Tập hợp plugin versions được quản lý ở parent POM.
- Build logs ghi JDK và configuration thực tế.

### 16.1. Vì sao Maven Wrapper chưa đủ?

Maven Wrapper giúp thống nhất Maven distribution, nhưng không tự cài/ép mọi JDK hoặc đảm bảo tất cả công cụ dùng cùng JDK. JAVA_HOME, PATH, toolchains và CI image vẫn cần được quản lý.

### 16.2. Vì sao plugin version cần được pin?

Nếu build phụ thuộc plugin default do Maven lifecycle hoặc parent POM thay đổi, kết quả compile có thể khác khi môi trường được cập nhật. Việc pin version và kiểm tra effective POM giúp giảm drift.

Tuy nhiên, pin version không có nghĩa giữ mãi plugin cũ. Khi nâng JDK, cần nâng plugin theo compatibility matrix và release notes tương ứng.

### 16.3. Build reproducibility không chỉ là class file

Ngoài compiler, reproducibility còn chịu tác động của:

- Annotation processor.
- Compiler flags.
- Locale/timezone.
- Thứ tự đầu vào và generated code.
- Dependency resolution.
- Resource filtering.
- Manifest và timestamps.
- Packaging plugin.
- Hệ điều hành và filesystem behavior.

Maven compiler release là một phần quan trọng nhưng không phải toàn bộ cơ chế tạo build có thể tái lập.

## 17. Tương đương trong Gradle

Trong Gradle, cũng cần phân biệt Java toolchain và release target.

Ví dụ Java/Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Đây là cấu hình dùng JDK 21 toolchain cho Java compilation và yêu cầu target release 17.

Một cấu hình chỉ đặt:

~~~groovy
sourceCompatibility = JavaVersion.VERSION_17
targetCompatibility = JavaVersion.VERSION_17
~~~

có thể không cung cấp bảo đảm platform API như options.release trên compiler hỗ trợ --release. Cần phân biệt và kiểm tra theo Gradle/JDK version thực tế.

### 17.1. Maven và Gradle side by side

| Nhu cầu | Maven | Gradle |
|---|---|---|
| Chọn release target | maven.compiler.release hoặc plugin release | JavaCompile.options.release |
| Chọn JDK compiler | Maven Toolchains / cấu hình compiler | Java Toolchains |
| Chọn runtime build tool | JAVA_HOME, launcher, environment | JVM chạy Gradle daemon/launcher |
| Chọn JVM test | Surefire/Failsafe configuration | Test task javaLauncher/toolchain |
| Xem cấu hình resolve | effective-pom, active-profiles, debug log | task configuration, --info/--debug và Java Toolchain info |
| Kiểm tra dependency | dependency:tree | dependencies, dependencyInsight |

Ví dụ Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Ví dụ Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Hai cách cùng hướng tới ràng buộc compiler release, nhưng build lifecycle, plugin inheritance và toolchain selection vẫn khác nhau.

## 18. API baseline của thư viện và dependency graph

Khi build một thư viện target Java 17, không chỉ class do dự án tạo phải đúng baseline. Những dependency được tải ở runtime cũng phải hỗ trợ Java 17.

Ví dụ:

~~~text
my-library.jar            major 61 / Java 17
  |
  +-- dependency-a.jar    major 61 / Java 17
  |
  +-- dependency-b.jar    major 65 / Java 21
~~~

Maven Compiler Plugin có thể biên dịch main source theo release 17 nhưng không tự biên dịch lại dependency-b.jar thành Java 17. Tùy cách tham chiếu, incompatibility có thể bị phát hiện ở compile hoặc chỉ lúc runtime tải class.

### 18.1. Kiểm tra dependency graph

~~~bash
./mvnw dependency:tree
~~~

Để lọc một dependency theo groupId/artifactId, dùng các tham số thích hợp của Maven Dependency Plugin đang được sử dụng.

Cần kiểm tra:

- Direct dependencies.
- Transitive dependencies.
- Plugin dependencies.
- Annotation processors.
- Test/runtime scope.
- Java agents và framework container libraries.
- JAR multi-release nếu có.

### 18.2. Có thể kiểm tra bytecode baseline như thế nào?

Có thể dùng bytecode scanning tool/Enforcer rule hoặc script chuyên dụng để kiểm tra maximum class-file major version của runtime artifacts. Không nên tự suy luận “Maven build xanh nên mọi JAR đều chạy trên Java 17”.

Nếu một dependency đã nâng Java baseline, lựa chọn thường là:

1. Giữ phiên bản dependency còn hỗ trợ release đích trong thời gian chuyển tiếp.
2. Nâng runtime baseline của ứng dụng, nếu có thể.
3. Thay dependency.
4. Tách thành module/service dùng JVM mới hơn, với API boundary rõ ràng.

## 19. Maven Enforcer và compiler release giải quyết hai vấn đề khác nhau

maven-enforcer-plugin có thể dùng để yêu cầu những điều kiện build nhất định, chẳng hạn version của Maven hoặc Java đang chạy.

Ví dụ khái niệm:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-build-environment</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireJavaVersion>
                        <version>[17,)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Ví dụ yêu cầu Maven đang chạy trên Java 17 trở lên. Nó không đồng nghĩa compiler phát hành bytecode Java 17, bởi compiler có thể dùng toolchain khác và release target riêng.

Thêm nữa, rule requireJavaVersion áp dụng cho JVM chạy Maven theo cách plugin hoạt động. Nó không tự bảo đảm JVM production đáp ứng điều kiện hoặc mọi dependency bytecode đều đúng baseline.

Có thể kết hợp:

- Enforcer kiểm soát build environment.
- Toolchains kiểm soát compiler.
- Compiler release kiểm soát Java Platform API và class target.
- Dependency/bytecode scanning kiểm soát artifacts.
- Runtime tests kiểm soát hành vi sản phẩm.

## 20. JPMS và module-info.java khi dùng release

Khi chuyển từ Java 8 lên Java 9+, dự án có thể thêm module-info.java.

Ví dụ:

~~~java
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
}
~~~

Compiler cần source/release phù hợp với module syntax và API. Nếu release 8, module descriptor không thuộc cú pháp Java 8. Khi target 17 hoặc 21, javac có thể biên dịch module-info với những quy tắc tương ứng.

### 20.1. Module path khác classpath

maven-compiler-plugin có thể tương tác với module path khi nhận diện cấu hình modular, nhưng cần kiểm tra:

- Module descriptor.
- requires/exports/opens.
- Artifact nào là named module hoặc automatic module.
- Dependency versions.
- Annotation processors và generated modules.
- Surefire/Failsafe chạy test theo classpath hay module path.

**release=17 không tự mở package nội bộ cho reflection.** Lỗi InaccessibleObjectException, IllegalAccessError hoặc module readability cần được xử lý theo JPMS và dependency compatibility, không chỉ compiler release.

### 20.2. --release không đồng nghĩa --add-exports

Khi compile code phụ thuộc JDK internals, một số team thêm --add-exports. Nhưng với --release, javac có những hạn chế về việc truy cập API không thuộc platform release. Không nên kết hợp cờ để tiếp tục dựa vào internals như một giải pháp chuẩn.

Ưu tiên chuyển sang API công khai và thư viện hỗ trợ JDK đích.

## 21. Multi-release JAR: ngoại lệ có thiết kế

Một thư viện có thể muốn hỗ trợ Java 11 nhưng dùng implementation tối ưu riêng cho Java 17 hoặc 21. Multi-release JAR là cơ chế khác với chỉ đổi maven.compiler.release.

Ví dụ cấu trúc:

~~~text
META-INF/MANIFEST.MF
com/example/Feature.class                  (baseline Java 11)
META-INF/versions/17/com/example/Feature.class
META-INF/versions/21/com/example/Feature.class
~~~

Manifest cần khai báo cơ chế multi-release phù hợp. Build thường đòi hỏi source sets, compiler executions và output directories riêng, mỗi lớp được biên dịch với release phù hợp.

Không nên thay mỗi release property trong cùng compile step rồi mong Maven tự tạo multi-release JAR. Đó là một cấu hình đóng gói có nhiều bước và quy tắc riêng.

### 21.1. Những rủi ro khi dùng MR-JAR

- Public API giữa baseline và versioned classes cần tuân thủ constraints của multi-release JAR.
- Test phải chạy trên tất cả runtime được hỗ trợ.
- Dependency versions có thể khác.
- JAR tooling, shading, bytecode scanning cần hiểu structure versioned entries.
- Debug và runtime dispatch khó hơn.

Chỉ dùng MR-JAR khi lợi ích thật sự đáng với độ phức tạp; nhiều ứng dụng có thể chọn module/service riêng đơn giản hơn.

## 22. Chiến lược migration theo hai pha

Một lộ trình thực tế là **nâng công cụ build trước**, sau đó **nâng Java baseline của ứng dụng**.

### Pha A — Dùng compiler mới nhưng giữ release cũ

Giả sử ứng dụng đang chạy Java 17 nhưng muốn chuẩn bị nâng JDK build lên 21:

~~~text
Before:
  Maven/Javac JDK 17
  release 17
  runtime 17

After phase A:
  Maven/Javac JDK 21
  release 17
  runtime 17
~~~

Lợi ích:

- Phát hiện plugin/processor không tương thích compiler mới.
- Kiểm tra các build scripts trên JDK mới.
- Bảo đảm source chưa vô tình gọi API Java 21.
- Giữ production runtime không đổi trong giai đoạn đầu.

### Pha B — Nâng release cùng runtime

Khi application server, dependency và runtime đều sẵn sàng:

~~~text
After phase B:
  Maven/Javac JDK 21
  release 21
  runtime 21
~~~

Lúc này mới sử dụng cú pháp/API Java 21 một cách có chủ đích. Cần chạy tests và kiểm tra những thay đổi runtime: TLS, reflection, garbage collector, serialization và framework.

### 22.1. Ưu điểm của hai pha

Nếu build gặp lỗi trong pha A, nguyên nhân có thể thuộc compiler/plugin/processor. Nếu chỉ lỗi sau pha B, nhiều khả năng liên quan source/API baseline hoặc runtime behavior. Tách pha giúp phân tích nguyên nhân dễ hơn so với đổi tất cả cùng một lần.

## 23. CI matrix và kiểm tra artifact

Một pipeline nên báo rõ:

~~~text
Maven version
JDK running Maven
Compiler toolchain JDK
Compiler plugin version
Effective release target
Dependency versions
Main/test class-file major versions
Runtime test JDK(s)
Build/test results
~~~

### 23.1. Các job gợi ý

**Compile baseline:** Dùng compiler đã chọn với release target chính thức.

**Runtime baseline test:** Chạy unit/integration tests trên Java thấp nhất được sản phẩm hỗ trợ.

**Runtime newest-supported test:** Chạy trên Java mục tiêu mới để phát hiện thay đổi hành vi.

**Dependency scan:** Kiểm tra JAR có class-file version vượt baseline hay không.

**API scan:** Phát hiện JDK internal API hoặc API deprecated khi cần.

**Packaging smoke test:** Khởi động artifact đã đóng gói với đúng runtime/container của production.

### 23.2. Đừng chỉ chạy test trên compiler JDK

Nếu compile bằng JDK 21 và release 17, chạy tests chỉ trên JDK 21 không chứng minh artifact sẽ chạy trên JDK 17. Trong khi --release giới hạn API nền tảng, dependency, agent hoặc runtime behavior vẫn có thể gây lỗi ở JDK 17.

### 23.3. Kiểm tra JAR đã package

Chỉ kiểm tra target/classes có thể bỏ sót:

- Shaded dependencies.
- Generated classes từ plugin khác.
- Multi-release entries.
- Bytecode instrumentation.
- Dependency được nhúng vào executable JAR.

Khi chuẩn bị release, hãy kiểm tra artifact cuối cùng mà người dùng/production thực sự sẽ chạy.

## 24. Quy trình điều tra khi Maven build cho release sai

### Bước 1 — Xác định triệu chứng

Ví dụ:

- Compiler không hỗ trợ release.
- Source compile dùng API quá mới.
- Class file major cao hơn runtime.
- CI và local tạo artifact khác nhau.
- Một module của reactor dùng release khác.
- Annotation processor lỗi sau khi nâng JDK.
- Test JVM thấp hơn compiled classes.

### Bước 2 — Xác nhận maven-compiler-plugin và release thực tế

Xem:

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw help:active-profiles
~~~

Đọc parent, pluginManagement, plugin execution, profiles và command-line overrides.

### Bước 3 — Xác nhận javac/toolchain

Maven -version cho biết JVM chạy Maven. Cần thêm compiler plugin log/toolchain output để biết javac thực tế.

Nếu sử dụng executable/fork tùy biến, kiểm tra cấu hình đó. Không dựa duy nhất vào JAVA_HOME.

### Bước 4 — Chạy clean compile

~~~bash
./mvnw clean compile
~~~

Xóa output cũ tránh việc nhìn thấy class file còn tồn tại từ lần compile khác. Với reactor, chọn đúng module khi cần.

### Bước 5 — Đọc class-file major và API usage

Dùng javap cho output class. Kiểm tra source gọi Java Platform API quá mới bằng compilation với release target và phân tích JDK internals khi phù hợp.

### Bước 6 — Kiểm tra dependency bytecode

Xem dependency graph, class version của dependency và khả năng sử dụng trên runtime mục tiêu. Không suy luận từ bytecode của main artifact.

### Bước 7 — Chạy runtime tests trên JDK baseline

Nếu product phải chạy Java 17, có ít nhất một test job dùng Java 17 thật. Sau đó chạy thêm trên JDK mới.

### Bước 8 — Ghi lại cấu hình và thay đổi

Lưu Maven/JDK/plugin version, release target, dependency changes và kết quả kiểm thử. Khi build sau thay đổi, có thể so sánh thay vì đoán.

## 25. Các lỗi cấu hình phổ biến

### “JAVA_HOME đang là 21, chắc chắn artifact chạy Java 21”

Không đúng. release có thể là 17; Maven có thể dùng compiler toolchain khác; runtime production cũng độc lập.

### “source=8 và target=8 tương đương release=8”

Không đúng trên compiler hiện đại nếu thiếu giới hạn API Java Platform. Source/target có thể để code gọi API chỉ có trên JDK mới.

### “Nếu target là 8 thì không thể có NoSuchMethodError trên Java 8”

Không đúng. Class file 52 vẫn có thể tham chiếu method không tồn tại ở Java 8 nếu build không kiểm soát platform APIs.

### “Maven Toolchains thay thế cho release”

Không đúng. Toolchain chọn JDK compiler, còn release chọn Java baseline mà source và bytecode nhắm tới.

### “release giới hạn cả dependency bên thứ ba”

Không đúng. Cần kiểm tra dependency bytecode, transitive graph và runtime compatibility riêng.

### “Build ở root đã xanh thì mọi module cùng release”

Không nhất thiết. Module có thể override property, plugin execution, profile hoặc sử dụng source generator khác.

### “Chỉ cần sửa version compiler plugin”

Không đủ. Cần đối chiếu JDK build, release target, annotation processors, Surefire/Failsafe và dependency versions.

### “compile thành công là kiểm chứng migration xong”

Không đúng. Class file có thể chạy trên runtime khác với compiler; reflection, TLS, binary compatibility và framework behavior cần runtime tests.

### “Maven Wrapper tự bảo đảm JDK”

Không đúng. Wrapper chủ yếu giải quyết Maven distribution. JDK vẫn cần được quản lý bằng môi trường/toolchain.

### “Nâng release lên mức mới nhất luôn là tốt nhất”

Không đúng. Release phải tương ứng runtime tối thiểu và yêu cầu hỗ trợ của sản phẩm.

## 26. Mẫu cấu hình Maven có kiểm soát

Ví dụ một dự án sử dụng Maven Compiler Plugin với Java 17 baseline:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ hiển thị cả property và cấu hình release trực tiếp để minh họa các vị trí hợp lệ, nhưng trong dự án thực tế nên **chọn một nguồn cấu hình rõ ràng** nhằm tránh trùng lặp không cần thiết.

Nếu muốn một property duy nhất điều khiển target, có thể bỏ thẻ release khỏi plugin configuration và dùng maven.compiler.release. Nếu muốn toàn bộ compiler settings nằm trong plugin, có thể bỏ property release khỏi properties. Cần kiểm tra effective POM sau khi quyết định.

### 26.1. Quy tắc thiết lập tổ chức

Một convention có thể là:

- Parent POM quản lý maven-compiler-plugin version.
- Parent định nghĩa release baseline chung.
- Child chỉ override khi có lý do sản phẩm được tài liệu hóa.
- CI dùng toolchain đủ mới để compile tất cả release target.
- Plugin/processors được chọn theo compatibility matrix.
- Build luôn chạy test trên runtime tối thiểu và JDK đích.
- Không duy trì source/target song song với release trừ use case đặc biệt đã xác nhận.

Một cấu hình thống nhất giúp người review biết ngay artifact được build cho Java nào, thay vì tìm nhiều property khó theo dõi.

## 27. Checklist trước khi chốt migration

- [ ] Đã xác nhận phiên bản Maven đang chạy.
- [ ] Đã xác nhận JDK của Maven và javac compiler thực tế.
- [ ] Đã xác nhận maven-compiler-plugin version.
- [ ] Đã xem effective POM của module liên quan.
- [ ] Đã xác nhận release target trùng với runtime thấp nhất được hỗ trợ.
- [ ] Đã bỏ source/target mâu thuẫn nếu dùng release.
- [ ] Đã kiểm tra compiler JDK hỗ trợ release đã chọn.
- [ ] Đã kiểm tra module overrides và profiles.
- [ ] Đã xem annotation processors/generators tương thích với compiler JDK.
- [ ] Đã kiểm tra source không dùng Java API mới hơn release đích.
- [ ] Đã xác nhận class-file major version của main artifact.
- [ ] Đã kiểm tra bytecode/dependency baseline.
- [ ] Đã chạy clean build từ output trống.
- [ ] Đã chạy test bằng runtime Java thấp nhất được hỗ trợ.
- [ ] Đã chạy test bằng runtime Java mục tiêu mới.
- [ ] Đã kiểm tra artifact cuối cùng, kể cả shaded/multi-release JAR nếu có.
- [ ] Đã ghi nhận rủi ro còn lại và kế hoạch rollback.

## 28. Mẫu hồ sơ cấu hình compiler và release

~~~text
PROJECT / MODULE
  Repository:
  Maven version:
  Maven wrapper version:
  maven-compiler-plugin version:
  Parent POM:
  Active profiles:

BUILD JDK
  JDK running Maven:
  JAVA_HOME:
  Compiler JDK / toolchain:
  Annotation processor JDK/context:

JAVA BASELINE
  Current release:
  Target release:
  Minimal supported runtime:
  Production runtime:
  Preview features enabled?:

COMPILER CONFIG
  maven.compiler.release:
  source/target settings:
  Direct plugin configuration:
  Module overrides:
  Compiler args:
  Generated sources:

DEPENDENCIES
  Runtime dependency graph:
  Maximum dependency class-file major:
  Processor/tooling versions:
  Known unsupported APIs:

VALIDATION
  Effective POM:
  Clean compile:
  Class-file major:
  Unit tests:
  Integration tests:
  Runtime matrix:
  Packaged artifact smoke test:

DECISION
  Accepted configuration:
  Exceptions:
  Owner:
  Rollback:
  Next upgrade milestone:
~~~

Lưu hồ sơ cùng POM, CI configuration và tài liệu migration để nhóm khác có thể tái hiện chính xác công cụ và release đã dùng.

## 29. Tổng kết

maven-compiler-plugin là một trong những điểm kiểm soát quan trọng nhất khi chuyển phiên bản Java. Tính năng **release** cho phép compiler hiện đại tạo mã theo một Java baseline cụ thể và hạn chế việc vô tình gọi API mới hơn mức đã cam kết.

Những nguyên tắc cần nhớ:

1. **Đừng nhầm JDK build với target runtime.** Một JDK mới có thể compile cho release cũ.
2. **Ưu tiên release thay vì chỉ source/target.** Release hạn chế cả cú pháp, class file và Java Platform API.
3. **Toolchain và release giải quyết hai câu hỏi khác nhau.** Toolchain chọn javac; release chọn ngôn ngữ/API baseline.
4. **Đọc effective POM.** Parent, pluginManagement, profiles và child modules có thể ảnh hưởng cấu hình.
5. **Kiểm tra artifact thực tế.** Class-file major, dependencies, processors và runtime tests đều cần được xem.
6. **Tách migration theo giai đoạn.** Có thể nâng compiler/tooling trước rồi nâng Java release/runtime sau.
7. **Không coi compile success là kết thúc.** Compatibility còn bao gồm runtime, framework, reflection, TLS, native dependency và consumer behavior.

Khi chọn release dựa trên yêu cầu ứng dụng và xác minh từ POM đến artifact cuối cùng, nhóm phát triển có thể nâng Maven, JDK và dependency một cách có kiểm soát, tránh phát hành nhầm bytecode hoặc Java API vượt quá khả năng của môi trường production.

