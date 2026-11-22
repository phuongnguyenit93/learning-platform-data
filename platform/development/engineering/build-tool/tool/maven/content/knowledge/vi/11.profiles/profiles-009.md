# Thiết kế profile cho kiểm chứng hoặc công cụ tùy chọn trong Maven

## 1. Mục đích: giữ build mặc định ổn định, bật công cụ khi cần

**Maven build profile** là cơ chế áp dụng một tập cấu hình có điều kiện lên mô hình POM đang được xây dựng. Profile có thể bổ sung property, dependency, plugin, plugin execution, repository hoặc một số cấu hình build mà không phải duy trì nhiều bản pom.xml cho cùng dự án.

Trong thực tế, nhóm phát triển thường cần hai loại hoạt động:

- **Kiểm chứng (verification):** chỉ chạy thêm các quy tắc chất lượng hoặc điều kiện môi trường khi review pull request, chạy pipeline chuyên biệt, nâng phiên bản công cụ hoặc chuẩn bị phát hành.
- **Công cụ tùy chọn (optional tooling):** tạo báo cáo coverage, phân tích code, kiểm tra dependencies hoặc sinh một artifact phụ cho người đang điều tra; không làm mọi lượt build thông thường tốn thời gian.

Ví dụ với cùng một dự án:

~~~bash
mvn clean verify
mvn -Pquality-gate clean verify
mvn -Pcoverage-report clean verify
mvn -Pquality-gate,coverage-report clean verify
~~~

Bốn lệnh dùng cùng POM và lifecycle **default**, nhưng ba lệnh sau kích hoạt thêm plugin execution theo **ID profile**. Mục tiêu thiết kế là **một đường build nền tảng đáng tin cậy**, còn các bước tùy chọn có tên, đầu ra và điều kiện kích hoạt rõ ràng.

**Lưu ý an toàn chất lượng:** Không nên giấu những kiểm tra **bắt buộc** sau một profile mà CI có thể quên bật. Nếu test, license, bảo mật hoặc quy tắc phát hành là điều kiện bắt buộc với mọi bản phát hành, hãy bind chúng trong cấu hình build nền hoặc buộc CI thực thi một lệnh chuẩn có kiểm tra. Profile là phương tiện điều phối công cụ, không phải lý do để bỏ qua chất lượng.

## 2. Profile hoạt động ở bước nào của Maven?

Maven đọc POM, xử lý inheritance và các profile đang kích hoạt để dựng **mô hình hiệu lực (effective project model)**. Sau đó các lifecycle phase như **validate**, **compile**, **test** và **verify** mới thực thi các plugin goal đã được bind.

Một profile được khai báo trong POM thường có dạng:

~~~xml
<profiles>
    <profile>
        <id>my-optional-tool</id>
        <build>
            <plugins>
                <!-- plugin chỉ thêm vào mô hình khi profile này active -->
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Đây chỉ là **đoạn cấu trúc**, không phải POM hoàn chỉnh. ID **my-optional-tool** có thể được kích hoạt tường minh bằng **-Pmy-optional-tool**.

| Thành phần | Vai trò |
| --- | --- |
| **profiles/profile/id** | Tên profile để bật, tắt và chẩn đoán. |
| **profiles/profile/activation** | Điều kiện tự kích hoạt, nếu dự án chủ động sử dụng. |
| **profiles/profile/properties** | Giá trị áp dụng khi profile hoạt động. |
| **profiles/profile/dependencies** | Dependency bổ sung cho biến thể build. |
| **profiles/profile/build/plugins** | Plugin và execution bổ sung/hợp nhất vào cấu hình hiệu lực. |
| **-Pprofile-id** | Yêu cầu Maven kích hoạt profile có ID tương ứng. |
| **help:active-profiles** | Kiểm tra profile nào đang được kích hoạt. |
| **help:effective-pom** | Xem cấu hình đã hợp nhất sau khi các profile có hiệu lực. |

**Profile không phải một lifecycle mới.** Lệnh **mvn -Pcoverage-report verify** vẫn chạy lifecycle thông thường tới phase **verify**; khác biệt là có thêm goal từ JaCoCo ở các phase thích hợp.

**Khai báo plugin không đồng nghĩa plugin tự chạy.** Một goal chỉ chạy trong lifecycle khi được bound bởi packaging/default lifecycle, execution có phase hoặc cơ chế binding tương ứng. Với công cụ tùy chọn, nên khai báo rõ execution, goal và phase để mọi người biết công cụ sẽ chạy khi nào.

## 3. Nguyên tắc chọn điều gì vào profile

Một profile phù hợp khi cấu hình phụ thuộc vào **mục đích thực thi**, không phải do dự án cần các phiên bản POM riêng cho mỗi môi trường.

| Cần thực hiện | Đặt ở đâu thường hợp lý? | Vì sao |
| --- | --- | --- |
| Biên dịch Java 17 | Cấu hình **build** nền. | Tất cả developer/CI cần kết quả Java tương thích. |
| Chạy unit test cơ bản ở **test** | Surefire trong build nền hoặc binding mặc định có version được quản lý. | Test nền không nên vô tình bị bỏ qua. |
| Ràng buộc version của plugin quan trọng | **pluginManagement** hoặc plugin nền. | Giữ build ổn định và tái lập. |
| Chạy thêm rule về duplicate dependency/JDK trong pipeline chuyên biệt | Profile **quality-gate** nếu thực sự tùy chọn; hoặc build nền nếu bắt buộc. | Kiểm soát chi phí và mục đích chạy. |
| Thu thập unit-test coverage bằng agent | Profile **coverage-report**. | Không phải lượt build nào cũng cần instrument JVM và sinh report. |
| Chạy one-off **dependency:tree** | Gọi goal trực tiếp khi cần. | Không nhất thiết thêm profile chỉ cho một lệnh thủ công. |
| Đổi database/credentials runtime theo dev/prod | Thường dùng cấu hình ứng dụng/secret management ở runtime. | Tránh đóng secrets vào JAR và tránh artifact khác nhau khó kiểm soát. |
| Bật thư viện tối quan trọng cho code production | Dependency nền, không để tùy chọn tùy tiện. | Thiếu dependency có thể khiến build/ứng dụng chạy sai. |

Một profile tốt có **tên diễn đạt tác dụng**, **đầu ra quan sát được**, **không tự bật bất ngờ**, và **không thay đổi version/logic sản phẩm ngoài phạm vi cần thiết**.

Trong bài, ta dùng hai profile độc lập:

- **quality-gate**: Maven Enforcer kiểm tra version Maven/JDK và dependency khai báo trùng ở phase **validate**.
- **coverage-report**: JaCoCo chuẩn bị agent ở **initialize**, thu dữ liệu khi test chạy và tạo báo cáo ở **verify**.

Hai profile không sửa code Java, không đổi dependency runtime của ứng dụng và có thể bật cùng nhau.

## 4. Dự án mẫu Java 17 hoàn chỉnh

Cần JDK 17+, Maven 3.9+ (hoặc phiên bản Maven tương thích với các plugin đã chọn), kết nối tải plugin/dependency từ repository được cấu hình. Các version sau được **chốt cụ thể cho ví dụ**, không khẳng định là phiên bản mới nhất của mọi plugin.

Cấu trúc:

~~~text
optional-profile-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── vn/example/profile/NumberLabel.java
    └── test/
        └── java/
            └── vn/example/profile/NumberLabelTest.java
~~~

### 4.1. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>optional-profile-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>quality-gate</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-enforcer-plugin</artifactId>
                        <version>3.5.0</version>
                        <executions>
                            <execution>
                                <id>check-build-requirements</id>
                                <phase>validate</phase>
                                <goals>
                                    <goal>enforce</goal>
                                </goals>
                                <configuration>
                                    <rules>
                                        <requireMavenVersion>
                                            <version>[3.9,)</version>
                                        </requireMavenVersion>
                                        <requireJavaVersion>
                                            <version>[17,)</version>
                                        </requireJavaVersion>
                                        <banDuplicatePomDependencyVersions/>
                                    </rules>
                                </configuration>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>

        <profile>
            <id>coverage-report</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.jacoco</groupId>
                        <artifactId>jacoco-maven-plugin</artifactId>
                        <version>0.8.12</version>
                        <executions>
                            <execution>
                                <id>attach-coverage-agent</id>
                                <phase>initialize</phase>
                                <goals>
                                    <goal>prepare-agent</goal>
                                </goals>
                            </execution>
                            <execution>
                                <id>generate-coverage-report</id>
                                <phase>verify</phase>
                                <goals>
                                    <goal>report</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
~~~

**Giải thích POM:**

1. Phần **build/plugins** ngoài profiles cấu hình compiler, Surefire và JAR Plugin dùng cho mọi build. JUnit Jupiter với **scope=test** chỉ phục vụ kiểm thử.
2. **quality-gate** không có **activation/activeByDefault**, nên không được bật chỉ vì POM được đọc. Khi được bật, Enforcer chạy **enforce** tại **validate** và có thể làm build thất bại nếu không đáp ứng rule.
3. **requireMavenVersion** yêu cầu Maven tối thiểu 3.9 theo version range **[3.9,)**; **requireJavaVersion** yêu cầu Java tối thiểu 17 theo range **[17,)**. Trường hợp dùng Maven 4 nên kiểm tra tính tương thích của chính phiên bản Enforcer đã chọn trong môi trường thực tế.
4. **banDuplicatePomDependencyVersions** phát hiện dependency trực tiếp bị khai báo trùng theo khóa của Maven. Nó không thay thế kiểm tra xung đột dependency bắc cầu hoặc mọi bài kiểm tra mã nguồn.
5. **coverage-report** bật JaCoCo tại **initialize** để chuẩn bị **argLine** chứa Java agent cho tiến trình test. Sau khi test chạy, goal **report** tại **verify** đọc dữ liệu coverage và tạo báo cáo.
6. JaCoCo **report** tạo báo cáo, **không tự đặt ngưỡng coverage bắt buộc**. Muốn fail build nếu tỷ lệ dưới ngưỡng, cần cấu hình goal **jacoco:check** và các rules thích hợp, thông thường tại **verify**.

Mẫu POM dùng **maven-surefire-plugin** với version cụ thể và **không tự đặt argLine** nên JaCoCo có thể truyền agent qua property **argLine** cho test JVM. Nếu dự án đã có cấu hình Surefire **argLine** riêng, xem mục troubleshooting về cách giữ tham số JaCoCo.

### 4.2. Tệp src/main/java/vn/example/profile/NumberLabel.java

~~~java
package vn.example.profile;

public final class NumberLabel {
    private NumberLabel() {
    }

    public static String label(int number) {
        if (number < 0) {
            return "âm";
        }
        return "không âm";
    }

    public static void main(String[] args) {
        System.out.println("Nhóm số: " + label(-2));
    }
}
~~~

Đây là class Java độc lập. Phương thức **label** có hai nhánh để test và báo cáo coverage có nội dung quan sát được. Java main không cần JUnit.

### 4.3. Tệp src/test/java/vn/example/profile/NumberLabelTest.java

~~~java
package vn.example.profile;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class NumberLabelTest {
    @Test
    void handlesNegativeNumber() {
        assertEquals("âm", NumberLabel.label(-2));
    }

    @Test
    void handlesZero() {
        assertEquals("không âm", NumberLabel.label(0));
    }
}
~~~

Tên **NumberLabelTest** phù hợp mẫu test được Surefire nhận diện; Surefire 3.2.5 hỗ trợ JUnit Platform/JUnit Jupiter. Hai bài test xác nhận hai nhánh của **label**; chúng không in ra stdout và không cần chạy **main** của NumberLabel.

### 4.4. Chạy và xem kết quả

Từ thư mục chứa **pom.xml**:

~~~bash
mvn --version
mvn -B clean verify
java -cp target/classes vn.example.profile.NumberLabel
~~~

Lệnh **mvn -B clean verify** chạy các pha build thông thường, biên dịch Java và test. **Stdout chính xác của riêng lệnh java thứ ba**:

~~~text
Nhóm số: âm
~~~

Vì không có profile nào được bật, lệnh build nền **không yêu cầu Enforcer quality-gate** và **không tạo báo cáo JaCoCo theo profile**. Nếu đã từng chạy một lượt coverage mà không dùng **clean**, file báo cáo cũ có thể còn; dùng **clean** khi muốn quan sát lượt chạy độc lập.

Để bật riêng kiểm chứng:

~~~bash
mvn -B -Pquality-gate clean verify
~~~

Enforcer được gọi ở **validate**. Nếu Maven đang chạy là 3.9+ với JDK 17+ và POM không có duplicate dependency, các rule ở ví dụ này dự kiến vượt qua. **BUILD SUCCESS** vẫn phụ thuộc các pha/plugin khác và môi trường tải artifact.

Để bật riêng công cụ coverage:

~~~bash
mvn -B -Pcoverage-report clean verify
~~~

Bên cạnh build/test bình thường, JaCoCo thiết lập agent, ghi dữ liệu sau khi JVM test kết thúc và tạo báo cáo. Với cấu hình mặc định và test chạy thành công, các đầu ra thường có:

~~~text
target/jacoco.exec
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
target/site/jacoco/jacoco.csv
~~~

**target/jacoco.exec** là dữ liệu coverage thô; **index.html** là báo cáo xem bằng trình duyệt; XML/CSV có thể dùng cho công cụ tổng hợp nếu được bật. Danh sách phụ thuộc JaCoCo/plugin và việc test JVM thực sự có chạy.

Để bật cả hai:

~~~bash
mvn -B -Pquality-gate,coverage-report clean verify
~~~

Enforcer kiểm tra ở **validate**; JaCoCo agent được chuẩn bị ở **initialize**; Maven biên dịch/chạy test ở các phase tương ứng; JaCoCo report chạy tại **verify**. Đây là ví dụ hai profile độc lập **có thể kết hợp**.

## 5. Đối chiếu bốn chế độ build

| Lệnh | Enforcer ở validate | Test JUnit | JaCoCo agent | Báo cáo coverage mới |
| --- | --- | --- | --- | --- |
| **mvn clean verify** | Không, nếu không có cấu hình khác | Có, theo Surefire mặc định | Không | Không |
| **mvn -Pquality-gate clean verify** | Có | Có | Không | Không |
| **mvn -Pcoverage-report clean verify** | Không | Có | Có | Có, khi có dữ liệu test |
| **mvn -Pquality-gate,coverage-report clean verify** | Có | Có | Có | Có, khi có dữ liệu test |

Bảng nói về **chính dự án mẫu**. Trong một dự án khác, parent POM hoặc settings có thể kích hoạt thêm plugin hoặc profile; luôn kiểm tra **effective POM** và log thực tế.

Quan trọng: lệnh **mvn -Pcoverage-report package** có thể chuẩn bị agent và chạy test, nhưng **không tới verify**, nên execution JaCoCo **report** ở verify chưa chạy. Cần gọi **verify** hoặc goal report riêng khi thích hợp.

Lệnh **mvn -Pcoverage-report verify -DskipTests** có thể đi qua các phase nhưng không chạy test, khiến JaCoCo không có dữ liệu mới và bỏ qua tạo báo cáo. **Đã kích hoạt profile** không có nghĩa **báo cáo chắc chắn tồn tại**.

## 6. Xác nhận profile nào đã bật và cấu hình nào đã áp dụng

Đừng chỉ dựa vào tên profile trên lệnh người dùng gõ. Maven có thể kích hoạt profile từ CLI, settings hoặc activation condition.

### 6.1. help:active-profiles

~~~bash
mvn help:active-profiles
mvn -Pquality-gate help:active-profiles
mvn -Pquality-gate,coverage-report help:active-profiles
~~~

Trong dự án mẫu không có activation khác, lệnh thứ nhất không liệt kê hai profile tùy chọn; lệnh thứ hai liệt kê **quality-gate**, lệnh thứ ba liệt kê cả **quality-gate** và **coverage-report**. Định dạng dòng log phụ thuộc phiên bản Help Plugin, nên cần đọc ID thay vì so khớp nguyên văn stdout.

### 6.2. help:effective-pom

~~~bash
mvn help:effective-pom -Doutput=effective-base-pom.xml
mvn -Pcoverage-report help:effective-pom -Doutput=effective-coverage-pom.xml
mvn -Pquality-gate,coverage-report help:effective-pom -Doutput=effective-all-pom.xml
~~~

So sánh phần **build/plugins** trong các effective POM; bản coverage phải có cấu hình **jacoco-maven-plugin** tương ứng, còn bản bật cả hai có Enforcer và JaCoCo. Các file effective POM chỉ dùng **chẩn đoán**, không phải nơi để sửa cấu hình dự án. Nếu plugin ở parent hoặc pluginManagement, Maven có thể hợp nhất cấu hình khác trực quan ban đầu; đọc theo ngữ cảnh model hiệu lực.

### 6.3. Log goal thực tế

~~~bash
mvn -B -ntp -Pquality-gate,coverage-report clean verify
~~~

Tìm log chứa các goal như **maven-enforcer-plugin:enforce**, **jacoco-maven-plugin:prepare-agent**, **maven-surefire-plugin:test**, **jacoco-maven-plugin:report**. Nếu cần điều tra sâu có thể dùng:

~~~bash
mvn -X -Pcoverage-report verify
~~~

**-X** tạo log debug nhiều thông tin hệ thống; không chia sẻ nguyên log nếu có đường dẫn nội bộ, token hoặc dữ liệu nhạy cảm. Phân biệt **goal đã được gọi** với **goal tạo ra file mới**: ví dụ JaCoCo report có thể được gọi nhưng skip do thiếu dữ liệu.

## 7. Cách bật profile bằng -P và vô hiệu hóa khi cần

**-P** nhận danh sách ID phân cách bằng dấu phẩy. Những kiểu dùng phổ biến:

~~~bash
mvn -Pquality-gate verify
mvn -Pcoverage-report verify
mvn -Pquality-gate,coverage-report verify
~~~

Không chèn khoảng trắng tùy tiện bên trong danh sách ID để tránh shell tách đối số. ID phải được khai báo trong POM/settings phù hợp; dùng tên ổn định, không đánh dấu bằng version tùy tiện hoặc tên người phát triển.

**Tắt một profile đang được kích hoạt** (ví dụ được chọn từ settings hoặc activation) có thể dùng cú pháp dấu trừ:

~~~bash
mvn -P=-coverage-report verify
~~~

Một số shell xử lý dấu **!** khác nhau, nên tài liệu Maven khuyến nghị cách dùng **-P=-profile-id** để tránh lỗi shell. Không cần tắt profile tùy chọn của ví dụ nếu nó không có activation và không được nêu trong **-P**.

**Maven 4** nghiêm ngặt hơn với ID profile không tồn tại: có thể từ chối build khi nhận profile không giải quyết được. Maven 4 cho phép đánh dấu ID tùy chọn bằng tiền tố **?** khi cố tình chấp nhận thiếu profile trong một reactor đa module hoặc lệnh chung. Đừng dùng tùy chọn này để che lỗi gõ sai; với build CI quan trọng, nên yêu cầu profile cần thiết thực sự tồn tại.

## 8. Activation tự động: khi nào nên dùng?

Có thể tự kích hoạt profile dựa trên **JDK**, **hệ điều hành**, **property**, **file có/không có**, hoặc một số điều kiện mới hơn tùy phiên bản Maven. Điều này hữu ích khi profile phản ánh **điều kiện khách quan**, nhưng dễ tạo build khác nhau giữa local và CI.

### 8.1. Kích hoạt khi có property -D

Ví dụ một **đoạn profile trong pom.xml** (không thay POM mẫu nếu không muốn đổi cách bật):

~~~xml
<profile>
    <id>quality-gate</id>
    <activation>
        <property>
            <name>run.quality</name>
            <value>true</value>
        </property>
    </activation>
    <!-- giữ các plugin/rule của profile tương ứng -->
</profile>
~~~

Khi đặt **-Drun.quality=true**, Maven có thể kích hoạt profile này mà không cần ghi **-Pquality-gate**:

~~~bash
mvn -Drun.quality=true clean verify
~~~

**-P** chọn profile theo ID; **-D** đặt user property. Hai cơ chế khác nhau và có thể dùng kết hợp. Trong tài liệu dự án, nên chọn **một cách bật chuẩn** để tránh CI và developer dùng lẫn lộn.

### 8.2. activeByDefault là một bẫy thường gặp

~~~xml
<profile>
    <id>local-default</id>
    <activation>
        <activeByDefault>true</activeByDefault>
    </activation>
    <properties>
        <build.mode>local</build.mode>
    </properties>
</profile>
~~~

Đây là **đoạn profile độc lập minh họa**, không có trong POM mẫu. Một profile **activeByDefault** trong một POM thường sẽ **tự bị vô hiệu hóa khi profile khác thuộc cùng POM được kích hoạt**. Nếu đặt các kiểm tra bắt buộc trong profile activeByDefault và sau đó chạy **-Pcoverage-report**, chúng có thể vô tình biến mất.

Vì vậy **không sử dụng activeByDefault như cơ chế bảo đảm một quality gate bắt buộc luôn chạy**. Đặt các kiểm tra bắt buộc ngoài profiles hoặc cấu hình CI rõ ràng.

### 8.3. Điều kiện file, JDK và OS

Ví dụ một profile chỉ bật khi file marker tồn tại:

~~~xml
<profile>
    <id>local-extra-tools</id>
    <activation>
        <file>
            <exists>.enable-local-tools</exists>
        </file>
    </activation>
    <!-- cấu hình plugin tùy chọn -->
</profile>
~~~

Điều kiện file thích hợp cho công cụ tùy chọn **trên máy cá nhân**, nhưng không nên dùng làm điều kiện bí mật khiến CI chạy thêm bước không được ghi trong pipeline. Maven xử lý activation từ rất sớm; các giá trị do chính POM định nghĩa như **${project.build.directory}** không phải lúc nào dùng được để nội suy điều kiện file. Tài liệu Maven chỉ bảo đảm những nguồn phù hợp như Java system properties và environment variables trong ngữ cảnh file activation.

Điều kiện **<jdk>[17,)</jdk>** có thể bật profile theo JDK đang chạy Maven; điều kiện **<os>** có thể match platform. Không nên bật quality gate chỉ ở một hệ điều hành nếu mục tiêu là bảo đảm chất lượng trên mọi nền tảng.

**Thực hành khuyến nghị:** cho công cụ **tùy chọn do ý định con người quyết định**, ưu tiên **-Pprofile-id** tường minh. Dùng activation khi một điều kiện môi trường là chủ đích thiết kế và được kiểm thử.

## 9. POM profiles, settings profiles và inheritance

Maven có các nơi khai báo profile khác nhau:

- **POM profiles** trong **pom.xml**: có thể cấu hình plugin execution, dependencies và những phần model được phép theo ngữ cảnh project. Phù hợp cho **quality-gate** và **coverage-report** vì cấu hình này được version-control cùng mã nguồn.
- **Settings profiles** trong **~/.m2/settings.xml** hoặc global settings: chỉ hỗ trợ một tập giới hạn như **repositories**, **pluginRepositories**, **properties**; **không phải nơi đặt toàn bộ build/plugins tùy chỉnh giống POM profile**.
- **Settings activeProfiles** có thể chỉ định ID profile cần kích hoạt, bao gồm profile trong POM khi resolution phù hợp, nhưng không nên dùng cấu hình cá nhân bí mật để định nghĩa tiêu chuẩn chất lượng của nhóm.

**Profiles không được kế thừa nguyên vẹn như một danh sách ID có thể tự kích hoạt xuyên module.** Maven xử lý các profile sớm trong POM chứa chúng; **tác động của profile đã active** (ví dụ plugin configuration) có thể được kế thừa. Một activation ngầm định chỉ áp dụng trong nơi profile được khai báo, không tự kích hoạt profile cùng ID ở một module khác.

Trong multi-module, nếu muốn coverage của toàn reactor, không nên tin rằng bật profile ở POM gốc là mọi module đều được instrument chính xác. Xem nơi plugin đã được kế thừa, packaging của từng module, cấu hình Surefire và mục tiêu **jacoco:report-aggregate** nếu cần báo cáo tổng. **jacoco:report** trong ví dụ chủ yếu là báo cáo cho module đang build; báo cáo tổng multi-module cần thiết kế riêng.

## 10. Tách pluginManagement khỏi việc kích hoạt goal

**pluginManagement** thường dùng để quản lý version/configuration tập trung. Một entry ở đây **không tự thực thi mọi goal** của plugin.

Ví dụ POM cha có thể quản lý version JaCoCo:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.12</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đoạn trên **chỉ minh họa quản lý version**, không tự khiến báo cáo coverage xuất hiện. Profile **coverage-report** vẫn cần một plugin execution hiệu lực trong **build/plugins**. Khi đã quản lý version ở parent, module có thể không cần lặp version trong plugin nếu kế thừa đúng. Tránh tạo hai entry cùng plugin trong một danh sách **plugins** chỉ để gắn thêm execution; hãy gộp chúng theo cơ chế Maven.

Nếu project có parent/BOM hoặc nhiều profile cùng sửa cùng cấu hình, Maven sẽ hợp nhất model theo các quy tắc inheritance/profile. Có thể xuất hiện xung đột property, execution ID hoặc configuration. Hãy dùng **help:effective-pom** để xem kết quả, thay vì suy luận rằng profile sau luôn “ghi đè toàn bộ plugin” hay profile trước luôn thắng.

## 11. Báo cáo JaCoCo không đồng nghĩa quality gate coverage

**JaCoCo prepare-agent** tạo thiết lập để test JVM thu dữ liệu. **JaCoCo report** đọc dữ liệu và tạo HTML/XML/CSV. Hai goal này khác với **JaCoCo check**, goal có thể làm build thất bại khi coverage không đạt ngưỡng.

Nếu tổ chức muốn kiểm tra coverage **bắt buộc** trong pipeline, có thể thiết kế một profile riêng như **coverage-gate**, hoặc thêm **jacoco:check** vào profile coverage đã bảo đảm luôn được bật trong CI. Ví dụ cấu hình check sau chỉ là **đoạn execution minh họa** đặt bên trong plugin JaCoCo đã có:

~~~xml
<execution>
    <id>enforce-coverage-threshold</id>
    <phase>verify</phase>
    <goals>
        <goal>check</goal>
    </goals>
    <configuration>
        <rules>
            <rule>
                <element>BUNDLE</element>
                <limits>
                    <limit>
                        <counter>LINE</counter>
                        <value>COVEREDRATIO</value>
                        <minimum>0.80</minimum>
                    </limit>
                </limits>
            </rule>
        </rules>
    </configuration>
</execution>
~~~

**0.80** là ngưỡng minh họa, không mặc định của Maven/JaCoCo. Đặt ngưỡng phải tính đến dự án, module, cách test thực thi, code sinh tự động và chính sách kiểm thử. Với ứng dụng nhỏ ở mục 4, hai nhánh đã được test; việc coverage theo bytecode vẫn phụ thuộc quá trình instrument và chạy test thực tế.

Nếu muốn báo cáo nhưng không muốn fail build vì coverage, chỉ cần **prepare-agent + report** như POM mẫu. Ngược lại, nếu muốn fail khi thấp ngưỡng, thêm **check** và xác nhận CI không skip test.

## 12. Các tác động của profile tới khả năng tái lập build

Profile là một nguồn khác biệt giữa các môi trường. Một số nguyên tắc quan trọng:

1. **Không tạo artifact ứng dụng khác nhau tùy ý** chỉ vì local bật profile còn CI không bật. Nếu profile thay dependencies, compiler version hoặc resource filtering, hãy xem liệu hai kết quả có còn tương đương về chức năng hay không.
2. **Pin phiên bản plugin** quan trọng trong pluginManagement hoặc build/plugins để tránh thay đổi không chủ đích do Super POM/Maven/plugin resolution.
3. **Giữ credentials ngoài POM**. Profile không phải nơi lưu token hoặc mật khẩu; settings/secret store hoặc environment của CI phù hợp hơn.
4. **Giữ tên profile nhất quán** trong developer docs, script và pipeline; dùng lệnh Wrapper khi repository có **mvnw/mvnw.cmd**.
5. **Kiểm thử tổ hợp profile** nếu tổ hợp được hỗ trợ, ít nhất baseline, từng profile độc lập và tổ hợp trên CI.
6. **Không dùng activeByDefault cho kiểm tra bắt buộc** vì profile mặc định có thể bị tắt khi một profile cùng POM được active.
7. **Đảm bảo công cụ tùy chọn có thể được bỏ qua mà không làm hỏng runtime chính.** Nếu ứng dụng chỉ chạy khi profile được bật, đó không còn là công cụ tùy chọn đúng nghĩa.
8. **Cân nhắc tốc độ CI**. Coverage instrumentation, static analysis và report generation có chi phí; chỉ đưa vào job/cadence thực sự cần.
9. **Khi nâng Maven 3 lên Maven 4**, kiểm tra cú pháp profile, ID không tồn tại, version plugin và inheritance. Không giả định mọi hành vi cũ giống hoàn toàn.
10. **Tài liệu hóa đầu ra** như **target/site/jacoco/index.html** để người dùng biết công cụ đang tạo gì, không chỉ biết lệnh có BUILD SUCCESS.

## 13. Ví dụ CI dùng profile có chủ đích

Một workflow CI đơn giản cho repository đã có Maven Wrapper có thể tổ chức hai đường:

**Job kiểm tra nhanh** (tên và cú pháp lệnh minh họa trong shell POSIX):

~~~bash
./mvnw -B -ntp clean verify
~~~

**Job kiểm tra sâu hơn** (chạy Enforcer và sinh coverage):

~~~bash
./mvnw -B -ntp -Pquality-gate,coverage-report clean verify
~~~

Với Windows PowerShell, dùng script tương ứng:

~~~powershell
.\mvnw.cmd -B -ntp -Pquality-gate,coverage-report clean verify
~~~

Nếu job thứ hai là điều kiện bắt buộc để merge, **CI phải yêu cầu job đó thành công**. Đừng chỉ định nghĩa profile mà không đưa vào pipeline bắt buộc. Nếu chạy CI với settings riêng, lưu ý những settings profiles đang active có thể ảnh hưởng mô hình; phải kiểm tra và cố định môi trường cần thiết.

Khi tải báo cáo coverage lên hệ thống CI, lấy output từ **target/site/jacoco/** sau job coverage; kết quả chỉ có ý nghĩa khi test thực sự chạy và JaCoCo thu được dữ liệu. Đừng coi một báo cáo cũ còn trong cache là bằng chứng của lượt build mới.

Trong pipeline release, những kiểm chứng mang tính bắt buộc có thể được chuyển ra build nền hoặc gắn vào bước release riêng được quản lý tập trung; quyết định theo chính sách nhóm thay vì để developer tùy ý bỏ qua.

## 14. Khi gặp lỗi, chẩn đoán như thế nào?

| Hiện tượng | Nguyên nhân phổ biến | Kiểm tra/sửa |
| --- | --- | --- |
| Chạy **-Pquality-gate** nhưng không thấy Enforcer | Nhầm ID, profile không active ở module cần xét, pha chưa tới validate hoặc settings/reactor khác. | Chạy **help:active-profiles**, kiểm tra **effective-pom** và log goal. |
| Enforcer fail version Maven/JDK | Bản Maven/JDK không đạt rule. | Chạy **mvn --version**; dùng Maven Wrapper/toolchain phù hợp, không âm thầm bỏ rule. |
| Build nền tạo JaCoCo report dù không bật coverage | Profile được active bởi settings/activation, có JaCoCo ở build nền, hoặc file cũ còn lại. | Kiểm tra active profiles, effective POM, thử **clean**. |
| **target/jacoco.exec** không tồn tại | Test bị skip, fork/JVM test không chạy, agent không được truyền vào Surefire hoặc plugin không active. | Kiểm tra log **prepare-agent**, Surefire, **argLine**, **skipTests**. |
| JaCoCo report được gọi nhưng không có HTML | Không có dữ liệu execution, chưa tới verify, source/classes thiếu hoặc report bị skip. | Chạy **-Pcoverage-report clean verify**, kiểm tra **target/jacoco.exec** và log. |
| Surefire cấu hình **argLine** riêng khiến coverage bằng 0 | Cấu hình Surefire ghi đè tham số Java agent. | Kết hợp JaCoCo property bằng cú pháp late evaluation như **@{argLine}** trong cấu hình Surefire, tránh ghi đè. |
| Test không chạy khi bật profile | **-DskipTests**, **-Dmaven.test.skip=true**, profile thay Surefire hoặc pattern test không khớp. | Đọc log test, xác minh test names và profile đã active. |
| **-Pcoverage-report** làm mất “default profile” | Profile activeByDefault cùng POM bị tự tắt. | Đưa cấu hình bắt buộc ra build nền; bỏ lạm dụng activeByDefault. |
| Hai profile cùng sửa một property/plugin | Cấu hình bị merge/override không như dự đoán. | So sánh effective POM của từng tổ hợp profile. |
| POM parent có profile nhưng child không active tương ứng | Profile không được kế thừa dưới dạng ID; chỉ tác động của profile active được kế thừa. | Kiểm tra POM khai báo và effective POM của từng module. |
| Build khác CI dù cùng lệnh -P | Khác Maven/JDK, settings, environment, repository hoặc profile activation. | Đồng bộ Wrapper/JDK, xem active profiles và effective settings. |
| JaCoCo lỗi JVM khi dùng **@{argLine}** ngoài profile | Late evaluation chưa có property khi agent không active. | Xác định giá trị mặc định rỗng cho **argLine** hoặc cấu hình Surefire phù hợp với cả hai chế độ. |

**Lưu ý về @{argLine}:** trong cấu hình Surefire, đây là cú pháp **late evaluation** riêng của Surefire để nhận property được JaCoCo điền sau khi Maven khởi tạo plugin. Nếu thêm **<argLine>@{argLine} ...</argLine>** vào POM mà không bật JaCoCo, cần khai báo property **argLine** rỗng hoặc cung cấp giá trị thích hợp để tránh JVM hiểu nguyên văn placeholder. POM mẫu cố ý không tự cấu hình argLine nên không gặp tình huống đó.

## 15. Checklist thiết kế profile cho công cụ mới

Khi định thêm một công cụ vào Maven, hãy trả lời lần lượt:

1. **Công cụ có thật sự tùy chọn không?** Nếu là cổng chất lượng bắt buộc, cấu hình nền hoặc CI bắt buộc có thể phù hợp hơn.
2. **Công cụ tạo giá trị gì?** Phát hiện lỗi, sinh report, xuất artifact phụ, hay chỉ hỗ trợ chẩn đoán tạm thời? Đầu ra nằm đâu?
3. **Cần goal nào và chạy ở phase nào?** Ví dụ JaCoCo prepare-agent trước test và report sau test, còn Enforcer có thể chạy ở validate.
4. **Cần nguồn/test/dependency nào?** Có làm thay đổi runtime classpath hoặc artifact chính không? Có thể chỉ bật khi cần không?
5. **Cần pin plugin/JDK/Maven version nào?** Có tương thích với Maven Wrapper của dự án không?
6. **Bật/tắt thế nào?** Có ID rõ ràng và lệnh **-P** minh bạch, tránh tự kích hoạt do máy người dùng?
7. **Tổ hợp với profile khác ra sao?** Có đè property hoặc plugin execution ID không? Kiểm tra effective POM.
8. **Mất profile có nguy hiểm không?** Nếu có, đây là dấu hiệu kiểm tra nên nằm ngoài profile tùy chọn hoặc CI phải bắt buộc chạy.
9. **Làm sao kiểm chứng?** Dùng **help:active-profiles**, effective POM, log goal, artifact/report và mã thoát của lần chạy.
10. **Có cần secrets/settings riêng không?** Không hardcode token vào POM/profile; dùng secret store phù hợp.
11. **Có tài liệu hoá quy trình cho đội không?** Cho biết lệnh baseline, lệnh nâng cao, nơi xem kết quả và xử lý lỗi.

**Tóm lại:** profile Maven phù hợp để **bổ sung có kiểm soát** một tập plugin goal hoặc điều chỉnh build cho trường hợp cụ thể. Thiết kế tốt giữ nền tảng build ổn định, bật công cụ bằng ID dễ hiểu, đặt goal đúng phase, có kết quả kiểm chứng được và tránh để các kiểm tra bắt buộc biến mất chỉ vì profile khác được kích hoạt.

### Tài liệu chính thức

- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — POM Reference: profiles](https://maven.apache.org/pom.html#profiles)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Help Plugin: active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven Help Plugin: effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Maven Enforcer — Built-in Rules](https://maven.apache.org/enforcer/enforcer-rules/)
- [JaCoCo Maven Plugin — prepare-agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html)
- [JaCoCo Maven Plugin — report](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)
- [JaCoCo Maven Plugin — check](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
