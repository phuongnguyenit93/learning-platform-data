# Sử dụng Maven profile cho biến thể bản dựng Spring Boot

## 1. Mục tiêu và bối cảnh

Cùng một dự án Spring Boot đôi khi cần nhiều **biến thể bản dựng**: chạy nhanh trên máy lập trình viên, chạy thêm integration tests trong CI, hoặc gắn metadata khi tạo artifact phát hành. Apache Maven hỗ trợ **build profile** để thay đổi một phần cấu hình build theo ngữ cảnh mà vẫn dùng một `pom.xml`.

Sau bài học, bạn có thể:

1. Giải thích Maven profile là gì, phần nào của bản dựng có thể thay đổi và phần nào cần giữ ổn định.
2. Tạo profile trong `pom.xml`, kích hoạt rõ ràng bằng `-P`, và hiểu kích hoạt theo property, JDK, OS, environment hoặc file.
3. Thiết kế ví dụ `local`, `ci`, `release` có kết quả quan sát được; bật integration test trong một biến thể.
4. Xác nhận **profile thực sự hoạt động** bằng Maven Help Plugin, effective POM và output build, thay vì chỉ nhìn tên profile.
5. Phân biệt **Maven build profile** với **Spring runtime profile** (`spring.profiles.active`) và tránh mang secret/cấu hình môi trường runtime vào artifact.
6. Xử lý các lỗi thường gặp khi cùng một lệnh build cho kết quả khác giữa máy cá nhân và CI.

**Bối cảnh:** Các ví dụ giả định bạn đã có dự án Spring Boot dùng Maven, có `pom.xml`, Maven Wrapper (`mvnw`, `mvnw.cmd`) và Java phù hợp với Spring Boot. Các đoạn XML sẽ được ghi rõ là *phần cần thêm vào POM hiện có* hay *file độc lập*. Không cần đổi Gradle/Maven Wrapper hoặc tạo dự án mới để học cơ chế profile.

## 2. Maven profile thực chất là gì?

**Maven profile** là một tập cấu hình Maven có điều kiện. Khi profile hoạt động, Maven ghép hiệu ứng của nó vào mô hình build để quyết định property, dependency, plugin, resource, repository hoặc một số phần cấu hình khác. Một profile **không phải một Maven lifecycle độc lập**: `package`, `verify`, `install` vẫn là các phase như trước.

Ví dụ:

- `local`: mặc định dùng cấu hình build cơ bản, chỉ chạy các test nằm trong lifecycle thông thường.
- `ci`: khi được chọn, bật Failsafe để chạy thêm integration test trong phase `integration-test` và kiểm tra kết quả tại `verify`.
- `release`: gắn nhãn metadata của bản dựng, hoặc cấu hình bước kiểm soát phát hành nếu quy trình dự án yêu cầu. **Chỉ chọn tên `release` không tự triển khai ứng dụng hoặc ký artifact.**

Một Maven profile có thể định nghĩa `<properties>`, `<dependencies>`, `<dependencyManagement>`, `<build>` với plugins/resources và các thành phần Maven hỗ trợ. Không phải mọi phần tử của POM đều được phép đặt vào `<profile>`, vì vậy hãy tuân đúng schema POM thay vì di chuyển nguyên project vào profile.

### Maven profile và Spring profile: cùng chữ “profile”, khác nhiệm vụ

| Tiêu chí | Maven build profile | Spring Boot runtime profile |
| --- | --- | --- |
| Chọn bằng | `-Pci`, `-Prelease`, `<activation>`, `settings.xml` | `spring.profiles.active`, biến môi trường `SPRING_PROFILES_ACTIVE`, `@ActiveProfiles` trong test |
| Thời điểm | Khi Maven tính mô hình build và thực thi plugin/lifecycle | Khi Spring ApplicationContext được khởi tạo |
| Ảnh hưởng | Plugin, dependency, resource, property, artifact và quy trình build | Bean, `application-{profile}.yml`, cấu hình, điều kiện runtime |
| Lệnh ví dụ | `./mvnw -Pci clean verify` | `java -jar target/app.jar --spring.profiles.active=dev` (thay đúng tên JAR thực tế) |
| Tự động liên kết? | **Không** | **Không** |

`-Pprod` **không tự động** làm Spring Boot chạy `application-prod.yml`. Ngược lại, đặt `SPRING_PROFILES_ACTIVE=prod` cho JVM chạy ứng dụng không nhất thiết làm Maven profile `prod` hoạt động. Bạn có thể cấu hình sự liên hệ một cách có chủ đích, nhưng cần kiểm soát vì build-time và runtime là hai vòng đời khác nhau.

Với ứng dụng triển khai tới nhiều môi trường, một lựa chọn vững chắc là **build một artifact giống nhau**, rồi cung cấp môi trường runtime qua biến môi trường, secret manager hoặc deployment config. Chỉ tạo artifact khác nhau bằng Maven profile khi có yêu cầu đóng gói thực sự.

## 3. Maven profile có thể được khai báo ở đâu?

| Vị trí | Dùng cho | Đặc điểm |
| --- | --- | --- |
| `pom.xml` của dự án | Biến thể build mà cả nhóm và CI cần biết | Version-control cùng code; có thể điều chỉnh dependencies, plugins và resource processing |
| `~/.m2/settings.xml` của người dùng | Mirror/repository/properties riêng máy hoặc tổ chức | Profiles trong settings có phạm vi cấu hình hẹp hơn; không định nghĩa được `<build><plugins>` như POM profile |
| Maven global settings | Cấu hình Maven ở mức bản cài | Phụ thuộc môi trường, kém dễ mang sang CI; cần cân nhắc khi dùng |
| POM cha / các POM module | Chính sách chung hoặc phần riêng của module | Profile khai báo ở mỗi POM không “kế thừa nguyên hình”; **hiệu ứng của profile đã active trong parent** mới có thể được kế thừa |

**Khuyến nghị:** Đặt biến thể build dùng chung trong `pom.xml`; giữ thông tin máy cá nhân, proxy, repository nội bộ và credentials trong settings/secret management thích hợp. Không commit mật khẩu, token, private key hay đường dẫn JDK tuyệt đối vào profile của dự án.

### Maven Wrapper

Chạy build bằng Wrapper đi cùng repository để thống nhất Maven version:

~~~bash
# Linux/macOS, tại thư mục có pom.xml và mvnw
./mvnw --version
./mvnw clean verify
~~~

~~~powershell
# Windows PowerShell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
~~~

Nếu thiếu Wrapper thì cần dùng Maven phiên bản phù hợp theo quy định dự án. Nếu chạy sai thư mục, Maven có thể báo không tìm được `pom.xml`; các ví dụ bên dưới đều chạy từ **thư mục gốc module/dự án có POM được chọn**.

## 4. Kích hoạt profile bằng `-P` và đọc trạng thái thực tế

Maven cho phép chọn profile theo ID, mỗi ID phân biệt với Maven phase/goal:

~~~bash
# Không bật profile "ci" hoặc "release" bằng lệnh
./mvnw clean verify

# Kích hoạt một profile được định nghĩa trong POM
./mvnw -Pci clean verify

# Kích hoạt profile release và chỉ xây tới package
./mvnw -Prelease clean package

# Kích hoạt nhiều profile có chủ đích
./mvnw -Pci,release clean verify
~~~

Trên Windows PowerShell, thay `./mvnw` bằng `.\mvnw.cmd`. `-Pci` cũng có thể đặt sau goal, nhưng thống nhất một vị trí trong script sẽ dễ đọc hơn.

**Lưu ý:** `-Pci,release` không phải lúc nào cũng là “CI rồi release” theo thứ tự khai báo CLI. Nếu các profile cùng thay đổi một property, Maven sẽ hợp nhất mô hình theo các quy tắc ưu tiên, bao gồm thứ tự định nghĩa profile trong cùng POM. Tốt nhất tránh kích hoạt hai profile **có tác động xung đột**. Với Maven 4, một profile ID được chỉ định nhưng không tồn tại có thể làm build thất bại; đừng xem cảnh báo profile không tìm thấy là vô hại.

Để biết profile nào thực sự active:

~~~bash
./mvnw help:active-profiles
./mvnw help:all-profiles
./mvnw -Pci help:active-profiles
~~~

`help:active-profiles` liệt kê profile đang hoạt động trong ngữ cảnh dự án; `help:all-profiles` cho biết các profile có sẵn. Khi dự án có multi-module, đầu ra có thể thể hiện theo từng module. **ID tồn tại không đồng nghĩa nó đã hoạt động**.

Để xem cấu hình cuối cùng sau khi ghép parent, profile và plugin:

~~~bash
./mvnw -Pci help:effective-pom -Doutput=target/effective-ci.xml
./mvnw -Prelease help:effective-pom -Doutput=target/effective-release.xml
~~~

Có thể mở các file effective POM để so sánh plugin, property và resource. Đây là **file kiểm tra sinh ra**, không phải nguồn cấu hình để sửa tay. Nếu Maven trả lỗi tạo file vì thư mục output chưa tồn tại theo setup hiện tại, hãy chọn đường dẫn ghi hợp lệ và tạo thư mục trước khi chạy lệnh.

## 5. Ví dụ xuyên suốt: ba biến thể build có kết quả kiểm chứng được

Trong một dự án Spring Boot Maven có sẵn `pom.xml` và test dependency `spring-boot-starter-test`, ta thiết kế:

| Biến thể | Cách chọn | Tác động có chủ đích | Lệnh nên dùng |
| --- | --- | --- | --- |
| Mặc định (`local`) | Không cần `-P` | Resource metadata ghi `local`; các unit test thông thường vẫn chạy | `./mvnw clean verify` |
| `ci` | `-Pci` | Metadata ghi `ci`, gắn Failsafe integration-test và verify goals | `./mvnw -Pci clean verify` |
| `release` | `-Prelease` | Metadata ghi `release` để có thể nhận biết biến thể artifact | `./mvnw -Prelease clean package` |

**Mặc định `local` là một property trong POM gốc**, không cần tạo profile `local` active-by-default. Cách này giúp bản dựng có fallback rõ ràng ngay cả khi bật profile khác.

### 5.1. Cấu hình thêm vào `pom.xml` hiện có

Trong POM của dự án Spring Boot Maven, giữ nguyên `parent`/BOM, dependency và các plugin hiện hữu. **Ghép** các phần sau vào `<project>`: nếu POM đã có `<properties>`, `<build>`, hoặc `<profiles>`, thêm nội dung vào phần tương ứng; không tạo phần tử cùng cấp trùng lặp.

~~~xml
<!-- Trích đoạn bên trong <project> của pom.xml hiện có -->
<properties>
    <build.flavor>local</build.flavor>
</properties>

<build>
    <resources>
        <!-- Giữ file ứng dụng, YAML và tài nguyên thông thường nguyên vẹn. -->
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>

        <!-- Chỉ filter file metadata được thiết kế để filter. -->
        <resource>
            <directory>src/main/build-resources</directory>
            <filtering>true</filtering>
            <includes>
                <include>build-variant.properties</include>
            </includes>
        </resource>
    </resources>
</build>

<profiles>
    <profile>
        <id>ci</id>
        <properties>
            <build.flavor>ci</build.flavor>
        </properties>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-failsafe-plugin</artifactId>
                    <version>3.3.1</version>
                    <executions>
                        <execution>
                            <goals>
                                <goal>integration-test</goal>
                                <goal>verify</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>

    <profile>
        <id>release</id>
        <properties>
            <build.flavor>release</build.flavor>
        </properties>
    </profile>
</profiles>
~~~

**Đây là trích đoạn cấu hình, không phải POM độc lập.** Plugin Failsafe `3.3.1` chỉ là phiên bản ví dụ; dự án nên dùng phiên bản được parent/pluginManagement của dự án hỗ trợ và được nhóm phê duyệt. Nếu `pom.xml` đã có cấu hình `maven-failsafe-plugin`, cần hợp nhất logic thay vì định nghĩa hai execution mâu thuẫn. Nếu project chưa có JUnit/test dependency, cần bổ sung bộ test phù hợp trước khi chạy kiểm thử.

Cơ chế:

1. Property `build.flavor` là `local` khi build không có profile.
2. `-Pci` làm property thành `ci` và thêm Failsafe vào build; `-Prelease` làm property thành `release`.
3. Resource filtering biến placeholder `@build.flavor@` thành giá trị build property trong file đầu ra. Dữ liệu ấy được **đóng gói vào JAR** nếu build có bước đóng gói tương ứng.
4. Với profile `ci`, Maven Failsafe chạy các integration tests khớp quy tắc tên class ở các phase `integration-test` và `verify`, nếu có test được cấu hình/phát hiện.

### 5.2. Tạo file metadata để có output quan sát được

Tạo file văn bản độc lập `src/main/build-resources/build-variant.properties` với nội dung chính xác:

~~~properties
build.variant=@build.flavor@
~~~

Không tạo file này trong `src/main/resources` nếu đã giữ `filtering=false` ở thư mục đó, vì Maven sẽ sao chép placeholder nguyên vẹn. Khi Maven chạy `process-resources`, nó đọc property từ mô hình build và sinh `target/classes/build-variant.properties`.

**Lưu ý an toàn:** chỉ filter những file text do bạn chủ động chọn. Không bật filtering bừa cho toàn bộ `src/main/resources`, đặc biệt các file `application.yml` chứa cú pháp placeholder của Spring, certificate, ảnh, file nhị phân hoặc nội dung cần bảo toàn. Maven resource filtering có thể thay đổi dữ liệu hoặc làm hỏng file binary nếu cấu hình sai.

### 5.3. Build và xem kết quả trên Linux/macOS

~~~bash
./mvnw clean package
cat target/classes/build-variant.properties

./mvnw -Pci clean verify
cat target/classes/build-variant.properties

./mvnw -Prelease clean package
cat target/classes/build-variant.properties
~~~

Output được mong đợi của lệnh `cat`, **lần lượt sau mỗi build thành công**, là:

~~~text
build.variant=local
build.variant=ci
build.variant=release
~~~

Ba dòng này là kết quả của **ba lần đọc riêng biệt**, không phải ba dòng cùng nằm trong một file. Dòng `BUILD SUCCESS` và log plugin Maven sẽ xuất hiện riêng và thay đổi theo dự án.

### 5.4. Build và xem kết quả trên Windows PowerShell

~~~powershell
.\mvnw.cmd clean package
Get-Content .\target\classes\build-variant.properties

.\mvnw.cmd -Pci clean verify
Get-Content .\target\classes\build-variant.properties

.\mvnw.cmd -Prelease clean package
Get-Content .\target\classes\build-variant.properties
~~~

Nếu thấy file không tồn tại, kiểm tra vị trí chứa POM, resource folder và log `maven-resources-plugin`; **đừng mặc định rằng JAR build thất bại chỉ vì bạn đang đứng ở sai module**. Nếu dự án multi-module, `target` tương ứng nằm ở từng module có đóng gói.

## 6. Kiểm chứng integration test thực sự chạy dưới `ci`

Plugin Maven Surefire thường chạy unit tests tại phase `test`; **Failsafe** được dùng cho integration tests tại `integration-test` và `verify`. Với quy ước tên phổ biến, test `*IT.java` được Failsafe phát hiện, còn Surefire mặc định thường không chạy tên đó.

Nếu project đã có `spring-boot-starter-test` hoặc JUnit Jupiter được cấu hình phù hợp, có thể tạo file Java 17+ minh họa dưới đây:

**File:** `src/test/java/com/example/demo/BuildVariantIT.java`

~~~java
package com.example.demo;

import java.io.InputStream;
import java.util.Properties;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class BuildVariantIT {

    @Test
    void ciProfileFiltersBuildMetadata() throws Exception {
        InputStream stream = getClass().getClassLoader()
                .getResourceAsStream("build-variant.properties");
        assertNotNull(stream, "Filtered resource must exist");

        try (stream) {
            Properties values = new Properties();
            values.load(stream);
            assertEquals("ci", values.getProperty("build.variant"));
        }
    }
}
~~~

**Mã này là test class thuộc project, không có `main`;** hãy chạy qua Maven/JUnit thay vì `java BuildVariantIT`. Nếu package của project khác, chọn đường dẫn/package tương ứng. Tên `*IT` là một trong các pattern phổ biến mặc định của Failsafe.

Chạy:

~~~bash
./mvnw -Pci clean verify
~~~

Kết quả kiểm chứng mong đợi: Failsafe phát hiện `BuildVariantIT`; assertion đọc file metadata và xác nhận `build.variant=ci`; `verify` báo fail nếu test thất bại. Báo cáo thường được ghi trong `target/failsafe-reports/`. Nếu không có integration test hoặc chúng không khớp pattern, một lệnh `verify` thành công **chưa đủ** để kết luận đã chạy integration tests: phải xem số test thực sự được phát hiện.

**Vì sao dùng `verify` thay cho `package`?** Maven lifecycle đi theo thứ tự `test → package → pre-integration-test → integration-test → post-integration-test → verify`. `package` kết thúc **trước** integration test. Failsafe kiểm tra kết quả tại `verify` để vẫn có cơ hội thực hiện cleanup trong `post-integration-test`. Lệnh `./mvnw -Pci clean package` chỉ đóng gói mà không đi đến các phase integration-test/verify trong ví dụ này.

Với `./mvnw clean verify` **không có `-Pci`**, profile `ci` không thêm plugin Failsafe, nên test `BuildVariantIT` không được chạy theo mặc định qua Failsafe; các unit test thông thường vẫn chạy. Trong một dự án đã cấu hình Failsafe ở nơi khác (POM cha/plugin execution khác), hành vi có thể khác; xác minh bằng effective POM và log.

## 7. Kích hoạt tự động bằng môi trường, property, JDK, OS hoặc file

Ngoài `-P`, Maven hỗ trợ điều kiện trong `<activation>`. Các đoạn dưới đây là **những cách khai báo thay thế cần ghép vào từng profile phù hợp**, không phải lệnh phải chạy chung tất cả.

### 7.1. Active theo property từ CLI

Trong profile `ci`:

~~~xml
<activation>
    <property>
        <name>build.mode</name>
        <value>ci</value>
    </property>
</activation>
~~~

Lệnh sau có thể kích hoạt profile này:

~~~bash
./mvnw -Dbuild.mode=ci clean verify
~~~

`-Dbuild.mode=ci` là **Maven user property** dùng làm điều kiện; nó không tự gắn nhãn `build.flavor=ci` trừ khi profile đã định nghĩa property ấy. `-Pci` vẫn là lựa chọn dễ hiểu khi chỉ muốn bật biến thể cụ thể. Nên tránh tên property dễ đụng với cấu hình Spring runtime.

### 7.2. Active theo biến môi trường của CI

Thay vì property CLI có thể dùng:

~~~xml
<activation>
    <property>
        <name>env.CI</name>
    </property>
</activation>
~~~

Maven expose environment variables qua `env.NAME`. Điều kiện này được thỏa khi biến `CI` tồn tại; nhiều nền tảng CI có biến này, nhưng **không phải mọi hệ thống đặt giống nhau**. Một người chạy terminal local có `CI` được đặt sẵn cũng có thể kích hoạt profile vô tình. Với pipeline quan trọng, truyền `-Pci` tường minh và ghi lệnh vào log sẽ dễ kiểm tra hơn.

### 7.3. Active theo JDK và hệ điều hành

~~~xml
<!-- Mỗi trích đoạn bên dưới thuộc một <profile> riêng nếu cần -->
<activation>
    <jdk>[17,)</jdk>
</activation>
~~~

~~~xml
<activation>
    <os>
        <family>Windows</family>
    </os>
</activation>
~~~

JDK activation dựa trên **JDK đang chạy Maven**, không nhất thiết là toolchain JDK được Maven Compiler chọn. OS activation dựa vào hệ điều hành chạy Maven. Những điều kiện này hữu ích cho khác biệt tooling/native command; đừng dùng để mặc định rẽ nhánh logic ứng dụng nếu cùng một artifact có thể dùng trên nhiều OS.

Maven cũng có file-exists/missing activation, ví dụ một file cấu hình có mặt trên máy. Nhưng file tồn tại khác nhau giữa local/CI dễ gây “build cùng source khác kết quả”; hãy dùng điều kiện này khi thực sự cần và thể hiện đường dẫn tương đối rõ ràng.

### 7.4. Active by default: hiểu đúng ngoại lệ

~~~xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
~~~

Một profile `activeByDefault` trong POM bị **tắt** khi profile khác **trong cùng POM** được kích hoạt. Điều này thường gây bất ngờ nếu nhóm mong profile mặc định vẫn được cộng dồn. Các giá trị dùng chung nên đặt trong POM gốc như `build.flavor=local`; chỉ đặt các **thay đổi có điều kiện** trong profile. Nếu cần tự động dùng nhiều feature độc lập, hãy thiết kế các profile theo trách nhiệm, không lạm dụng active-by-default để tạo tầng cấu hình khó đoán.

## 8. Tác động của nhiều profile, parent và `settings.xml`

Maven có thể có profile cùng ID ở POM parent, POM module hoặc `settings.xml`. Đừng chỉ nhìn tên `ci` và cho rằng mọi module sẽ có cùng hiệu ứng.

- **POM parent:** Profile được xử lý trong POM nơi nó khai báo; các *hiệu ứng* của profile active có thể được con kế thừa khi mô hình build được tạo. Profile definition không phải một cấu trúc con có thể tùy ý kích hoạt trong mọi module từ bên ngoài như plugin.
- **POM con:** Có thể có profile ID riêng, cấu hình riêng và activation riêng. Một profile auto-activated trong module này không nhất thiết auto-activated trong module khác chỉ vì ID giống nhau.
- **User/global settings:** Dùng chủ yếu cho repository, pluginRepository và properties, hoặc `<activeProfiles>` cố định cho máy. Chúng có thể thay đổi nguồn tải dependency và property mà người kiểm thử không nhận ra.
- **Nhiều profile cùng active:** Khi cùng một phần tử bị định nghĩa bởi nhiều active profiles trong cùng POM, profile định nghĩa **sau** thường có ưu tiên cao hơn khi hợp nhất những giá trị đơn; các collection/plugins có quy tắc merge riêng. Đừng dựa vào thứ tự `-Pci,release` để định nghĩa ưu tiên nghiệp vụ.

Kiểm tra config profile thực sự được kết hợp bằng:

~~~bash
./mvnw -Pci help:active-profiles
./mvnw -Pci help:effective-pom
./mvnw -Pci dependency:tree
~~~

Đặc biệt với multi-module: so sánh các module bị ảnh hưởng, plugin execution ở module con, các dependency mới xuất hiện và effective POM của từng module. Nếu cần build riêng module ứng dụng, chọn `-pl` đúng Maven selector; tránh bỏ qua parent/reactor projects mà module phụ thuộc.

## 9. Thiết kế biến thể an toàn cho Spring Boot

### Khi nào profile thay đổi dependency là hợp lý?

Một profile có thể thêm dependency chỉ cần trong một build flavor, ví dụ công cụ kiểm tra build hoặc thư viện đặc thù của một module. Tuy nhiên, thay đổi runtime dependencies qua profile làm **hai artifact có cùng tọa độ nhưng classpath khác nhau**, khiến debugging, vulnerability scan và test khó đối chiếu.

Nếu phải khác dependency:

1. Ghi rõ dependency nào và scope nào thay đổi khi bật profile.
2. Chạy `dependency:tree` dưới **mỗi profile** và lưu kết quả.
3. Kiểm tra cả `compile`, test và runtime; đừng chỉ đọc POM.
4. Giữ version do Spring Boot BOM quản lý khi có thể, tránh override không được kiểm chứng.
5. Dùng artifact classifier/version/publishing policy phù hợp nếu các biến thể được phát hành song song; đừng âm thầm xuất bản nhiều nội dung khác nhau dưới cùng một version.

### Khi nào profile thay đổi plugin là hợp lý?

CI hoặc release có thể bổ sung integration tests, coverage, code analysis, kiểm tra license hay kiểm định chất lượng. Tác động ở **build-time** này thường rõ ràng hơn việc đưa các dependency debug vào ứng dụng production. Nếu release profile tạo artifact có chữ ký, đòi hỏi secret/credential, hãy để CI cung cấp secret và không lưu secret trong POM.

Với Spring Boot Maven plugin, lệnh `spring-boot:repackage` tạo executable archive khi được cấu hình gắn với lifecycle. Profile có thể điều chỉnh plugin configuration, nhưng điều đó ảnh hưởng cấu trúc JAR/WAR: kiểm tra main class, layered JAR, classifier và khả năng chạy `java -jar` của đúng artifact. **Không giả định** `-Prelease` tự động “tối ưu” Boot JAR chỉ vì tên profile.

### Đặt ranh giới build-time và runtime

Maven profile **không nên đóng cứng** URL database production, password, token hoặc API key trong `application.yml` qua filtering. Nếu dùng Maven filtering cho file text, chỉ đưa metadata vô hại như build flavor, revision hoặc feature cho tooling. Thông tin runtime nhạy cảm phải cấp từ nơi quản lý cấu hình và secret ở môi trường triển khai.

## 10. Ví dụ CI chạy profile một cách tường minh

Đoạn YAML là một **workflow minh họa** đặt tại `.github/workflows/maven-verify.yml` của repository dùng GitHub Actions. Điều chỉnh Java version và action version theo chính sách của dự án:

~~~yaml
name: Verify Maven build

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Confirm Maven and profiles
        run: |
          java -version
          ./mvnw --version
          ./mvnw -Pci help:active-profiles

      - name: Unit and integration tests
        run: ./mvnw --batch-mode --no-transfer-progress -Pci clean verify

      - name: Inspect filtered metadata
        run: cat target/classes/build-variant.properties
~~~

Workflow giả định `mvnw` ở repository root có **executable bit** và có thể build trên Java 21 theo cấu hình project. Nếu project nhiều module, chỉnh `working-directory` hoặc đường dẫn Wrapper/môđun artifact. Lệnh `-Pci` minh bạch profile đang dùng trong CI, tránh việc môi trường runner bất ngờ làm active profile khác.

**Không dùng Maven profile để né kiểm thử:** CI nên chạy `verify` và có bằng chứng số test unit/integration thực sự được chạy. Nếu một profile `fast` có mục tiêu phát triển cục bộ, phải báo rõ test nào không chạy; không coi kết quả nhanh của nó tương đương full CI.

Release nên là job được kiểm soát riêng, chỉ kích hoạt sau các kiểm định và phê duyệt cần thiết. Trong ví dụ này `-Prelease` chỉ thay metadata, **không có chức năng deploy/publish**, không đụng kho artifact bên ngoài.

## 11. Từng bước kiểm tra khi profile dường như không hoạt động

| Triệu chứng | Nguyên nhân thường gặp | Cách điều tra |
| --- | --- | --- |
| Maven báo profile ID không tồn tại | Gõ sai tên, đang ở sai POM/module, profile nằm ở file khác hoặc Maven 4 kiểm tra strict | `help:all-profiles`, `help:active-profiles`, kiểm tra POM và `-P` |
| `-Pci` chạy nhưng `build.variant` vẫn `local` | Property bị ghi đè ở POM con, settings/user property, hoặc resource không được filter | Xem effective POM, file `target/classes`, plugin resources execution |
| `build-variant.properties` còn `@build.flavor@` | Thư mục/file không nằm trong resource đã bật filtering | Kiểm tra `<resources>` và log `maven-resources-plugin`, `clean` rồi thử lại |
| File `application.yml` bị thay nội dung bất ngờ | Bật filtering trên toàn `src/main/resources` | Tách thư mục filtered resources và chỉ định đúng file text; khôi phục nội dung nguồn |
| `-Pci clean package` không thấy integration tests | `package` đứng trước `integration-test` và `verify` | Chạy `-Pci clean verify`, xem `target/failsafe-reports` và số test |
| `verify` báo `BUILD SUCCESS` nhưng không có test IT | Không có `*IT`, thiếu Failsafe execution hoặc plugin không tìm thấy test | Kiểm tra effective POM, naming pattern, test dependencies và báo cáo Failsafe |
| `activeByDefault` ngừng hoạt động khi bật profile khác | Maven tắt profile default cùng POM khi có profile khác active | Chuyển cấu hình nền vào POM gốc; làm rõ cách kích hoạt |
| Profile tự active trên CI nhưng không active trên máy local | Khác `env.CI`, JDK, OS, file hoặc settings | Chạy `help:active-profiles`, `--version` ở cả hai nơi; ưu tiên `-P` tường minh |
| Maven profile active nhưng Spring vẫn dùng `default` | Maven profile và Spring runtime profile là hai cơ chế độc lập | Kiểm tra runtime config, `SPRING_PROFILES_ACTIVE`, log Spring ApplicationContext |
| Build được nhưng JAR chạy lỗi | Profile thay dependency/plugin, artifact hoặc resources | So sánh dependency tree, executable JAR, Java runtime và integration test |
| Một module có plugin nhưng module khác không | Profile parent/module hoặc kế thừa cấu hình khác nhau | Kiểm tra effective POM **từng module** trong reactor |
| Artifact thay đổi dù code không đổi | Profile, resource filtering, plugin, user settings hoặc dependency resolution khác | Ghi lại Maven/JDK, active profiles, properties, effective POM, môi trường CI |

**Quy trình gỡ lỗi ngắn:** ghi lại câu lệnh Wrapper nguyên văn → xem active profiles → xem effective POM → so sánh build output/resource → xem báo cáo test → thử lại với `clean` đúng module. Không sửa nhiều profile cùng lúc nếu chưa xác định nguyên nhân.

## 12. Bài thực hành có tiêu chí nghiệm thu

Dùng dự án Spring Boot Maven đã hoạt động và tạo một branch thử nghiệm:

1. Thêm property nền `build.flavor=local` và ba phần cấu hình resource/profile ở mục 5; tạo file `src/main/build-resources/build-variant.properties`.
2. Chạy **mặc định**: `./mvnw clean verify`; xác nhận file sinh ra có `build.variant=local`.
3. Chạy **CI**: `./mvnw -Pci clean verify`; xác nhận `help:active-profiles` có `ci`, metadata thành `ci`, và Failsafe phát hiện ít nhất một `*IT` test nếu bạn đã thêm test ở mục 6.
4. Chạy **release**: `./mvnw -Prelease clean package`; xác nhận metadata thành `release`. Ghi nhận rằng `-Prelease` không tự kích hoạt deploy hoặc Spring runtime profile.
5. Xuất/đọc effective POM của `ci` và `release`, chỉ ra sự khác nhau giữa `maven-failsafe-plugin`, resource property và build output.
6. Cố tình chạy `-Pci,release`, quan sát giá trị cuối của `build.flavor` theo quy tắc merge; sau đó **loại cách kết hợp xung đột** khỏi script CI và document lệnh đã thống nhất.
7. Trả lời bằng lời: trường hợp nào cần Maven profile, trường hợp nào cần Spring runtime profile; vì sao không nên nhúng secret production vào resource filtering; vì sao `package` chưa đủ để kết luận integration tests đã chạy.

Bạn hoàn thành khi có thể **tái hiện được sự khác nhau có chủ đích** giữa các bản dựng, chỉ ra profile active qua công cụ Maven và chứng minh test/artifact thực sự phản ánh profile đã chọn.

## 13. Nguyên tắc áp dụng vào dự án thật

- Giữ POM cơ sở build được bằng lệnh tiêu chuẩn; ưu tiên profile cho **thay đổi có lý do** thay vì mọi lựa chọn nhỏ đều có một profile riêng.
- Dùng một profile CI rõ ràng, version-control cùng source, test qua Wrapper; ghi active profiles và Maven/JDK trong log.
- Không biến một profile build thành nơi chứa cấu hình runtime production. Giữ tách bạch cách chọn Spring active profile khi ứng dụng khởi chạy.
- Tránh các profile có hiệu ứng khó quan sát: package version thay đổi, bỏ test, dependency override hoặc plugin execution chỉ chạy trên máy người tạo profile.
- Với bất kỳ biến thể phát hành nào, kiểm tra artifact thực tế, dependency graph, nguồn dữ liệu đã lọc và khả năng khởi động. Giữ truy vết profile/version/revision của bản dựng.
- Khi migration Maven hoặc Spring Boot, kiểm thử lại mọi profile có sử dụng thực tế; effective POM và lifecycle/plugin execution có thể đổi theo parent/version plugin.

## Tài liệu chính thức

- [Apache Maven – Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven – Maven POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Help Plugin – active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven Help Plugin – effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Resources Plugin – Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Spring Boot Maven Plugin – Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
