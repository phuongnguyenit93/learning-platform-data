# Tránh artifact khác nhau khó truy vết do Maven profile phụ thuộc máy

## 1. Vấn đề: cùng mã nguồn, cùng version nhưng hai JAR khác nhau

Một nhóm dùng Maven build ứng dụng Java. Lập trình viên A chạy `mvn clean package` trên laptop và nhận `profile-variant-demo-1.0.0.jar`. CI chạy cùng lệnh trên cùng commit và cũng tạo file tên đó, nhưng checksum SHA-256 khác. Ở môi trường A ứng dụng báo `mode=workstation`; ở CI lại báo `mode=standard`. Vì cả hai artifact mang cùng tọa độ Maven `groupId:artifactId:version`, người vận hành rất khó biết bản nào đã được triển khai.

Một nguyên nhân phổ biến là **Maven profile kích hoạt theo môi trường**. File `pom.xml` có thể khai báo profile tự bật theo biến môi trường, phiên bản JDK, hệ điều hành, file chỉ tồn tại trên một máy hoặc thiết lập trong `settings.xml`. Khi profile thay đổi properties, resource filtering, dependency hay plugin, **cùng lệnh build và cùng commit chưa chắc tạo ra cùng nội dung artifact**.

Mục tiêu của bài này là:

1. Xác định các kiểu activation có thể khiến Maven profile phụ thuộc máy.
2. Chứng minh một khác biệt **trong chính nội dung JAR**, không chỉ khác log hoặc tên file.
3. Dùng `help:active-profiles`, `help:effective-pom`, kiểm tra tài nguyên và checksum để truy vết.
4. Thiết kế lại để **một phiên bản phát hành tương ứng một nội dung artifact có thể kiểm chứng**; cấu hình chạy theo môi trường không âm thầm thay đổi file đã phát hành.
5. Xây dựng các quy tắc kiểm tra ở CI, bàn giao artifact và xử lý sự cố khi hai máy build ra kết quả khác nhau.

Bài dùng Maven **3.9.x**, JDK **17 trở lên** và ví dụ JUnit Jupiter. Phần code minh họa một lỗi thiết kế có chủ đích, rồi sửa nó. **Không nên triển khai kiểu profile phụ thuộc máy ở phần thử nghiệm đầu vào một hệ thống thật.**

## 2. Phân biệt profile với bản phát hành và môi trường runtime

**Profile** là một tập cấu hình Maven có thể được kích hoạt để điều chỉnh *effective POM* của lần build. Profile không phải một môi trường chạy ứng dụng tự động, cũng không phải mã định danh bản phát hành.

~~~text
Source commit + pom.xml + JDK/Maven + active profiles
                           |
                           v
                    Effective POM
                           |
                           v
                    Maven build
                           |
                           v
                artifact (.jar/.war)
                           |
                           v
                  triển khai và chạy
                           |
                   runtime settings
                (env, secret, config)
~~~

Cấu hình có thể tác động ở hai thời điểm rất khác nhau:

| Loại cấu hình | Ví dụ | Có nên thay đổi byte của cùng một artifact đã phát hành? |
| --- | --- | --- |
| **Build-time** | `maven.compiler.release`, dependencies, plugin, resource filtering, source code generation | Nếu thay đổi, kết quả có thể là artifact **khác**; phải xem đó là một biến thể build cần nhận diện |
| **Runtime** | URL dịch vụ, feature flag runtime, logging level, secret, chế độ chạy | Thông thường nên cấu hình **bên ngoài** artifact để dùng cùng một file cho nhiều môi trường |
| **Build infrastructure** | Mirror, proxy, cache trong `settings.xml` | Không nên thay đổi logic/nội dung artifact nếu mục tiêu là cùng một release; nhưng repository/plugin version trôi dạt vẫn có thể làm khác |
| **Release identity** | Commit, version, classifier, hash, build provenance | Dùng để truy vết chính xác artifact nào được phát hành |

Nguyên tắc vận hành mạnh là **build once, promote the same artifact**: CI xây dựng, kiểm thử và lưu **một artifact**, sau đó promote chính file đã được xác minh qua các môi trường. Nếu đội ngũ bắt buộc có hai biến thể build khác nhau, phải đặt **định danh riêng có chủ đích** và quy trình công bố rõ ràng; không xuất bản hai tập byte khác nhau dưới cùng một tọa độ GAV mà không có cơ chế phân biệt.

## 3. Các nguồn activation phụ thuộc máy

Maven profile có thể nằm trong `pom.xml`, `~/.m2/settings.xml` hoặc global settings của bản Maven. Profile ở POM có thể thay đổi phần build của project; profile trong settings giới hạn hơn, chủ yếu cấu hình repositories, pluginRepositories và properties. Những **properties từ settings đang hoạt động** vẫn có khả năng ảnh hưởng đến POM và plugin.

### 3.1. Profile được bật tường minh

~~~bash
mvn -Pci clean verify
mvn -Pfast,checks clean package
~~~

`-P` yêu cầu kích hoạt profile ID đã có. Cách này giúp ý định của một lần build **hiển thị trên command line**, nhưng bản thân nó **không bảo đảm hai artifact có byte giống nhau**: `-Pci` và `-Pfast` có thể làm khác dependency/config. CI và tài liệu phát hành phải thống nhất profile nào được phép dùng.

### 3.2. Profile tự bật theo biến môi trường hoặc property

Ví dụ:

~~~xml
<profile>
    <id>machine-workstation</id>
    <activation>
        <property>
            <name>env.BUILD_FLAVOR</name>
            <value>workstation</value>
        </property>
    </activation>
    <properties>
        <app.mode>workstation</app.mode>
    </properties>
</profile>
~~~

Trong Maven, environment variable `BUILD_FLAVOR` có thể được tham chiếu như property `env.BUILD_FLAVOR`. Profile trên tự kích hoạt **chỉ khi biến đó có giá trị phù hợp**. Hai terminal trên cùng một máy cũng có thể có môi trường khác nhau; ví dụ một terminal được IDE hoặc script khởi tạo thêm biến này.

Biến môi trường trên Windows thường được chuẩn hóa tên thành chữ hoa khi Maven đọc. `-Dbuild.flavor=...` là một **CLI user property khác** với `env.BUILD_FLAVOR`; đừng nhầm hai tên rồi kết luận profile không hoạt động.

Ví dụ khác chỉ phản ứng khi người chạy truyền `-Drelease.mode=true`:

~~~xml
<activation>
    <property>
        <name>release.mode</name>
        <value>true</value>
    </property>
</activation>
~~~

Lệnh `mvn -Drelease.mode=true package` sẽ kích hoạt điều kiện đó. Dù tường minh ở CLI, cần ghi nhận value đã dùng trong hồ sơ build.

### 3.3. Profile tự bật theo JDK

~~~xml
<activation>
    <jdk>[17,21)</jdk>
</activation>
~~~

Đây là một **dải phiên bản JDK chạy Maven**, không nhất thiết là mức Java mà dự án biên dịch. Một laptop dùng JDK 17 có thể kích hoạt profile; một CI dùng JDK 21 có thể không. Dù POM cùng khai báo `<maven.compiler.release>17</maven.compiler.release>`, hai JVM chạy Maven có thể dẫn tới **profile khác nhau**. Dải `[17,21)` bao gồm đầu 17 và loại trừ đầu 21, theo cú pháp version range Maven.

Nếu khác biệt JDK chỉ phục vụ **khả năng tương thích**, hãy kiểm tra và giới hạn JDK ở pipeline (có thể dùng Maven Toolchains hoặc Enforcer với cấu hình phù hợp) thay vì để profile bí mật đổi nội dung ứng dụng tùy máy.

### 3.4. Profile tự bật theo hệ điều hành

~~~xml
<activation>
    <os>
        <family>Windows</family>
    </os>
</activation>
~~~

Máy Windows kích hoạt profile này, còn hệ Linux thường không. Điều kiện OS có thể hợp lý khi build cần tool native khác nhau, nhưng **không nên khiến cùng một GAV chứa nội dung ứng dụng khác nhau mà nhóm không biết**. Tên/phiên bản/architecture OS do JVM báo có thể khác giữa máy hoặc runner; `mvn -version` là bước kiểm tra cơ bản.

### 3.5. Profile tự bật theo file có hoặc không có

~~~xml
<activation>
    <file>
        <exists>local-build.flag</exists>
    </file>
</activation>
~~~

Nếu một người có `local-build.flag` trong project còn người khác không có, profile có thể bật khác nhau mà không ai gõ thêm `-P`. Một file bị bỏ khỏi `.gitignore` hoặc chỉ IDE tạo ra trên máy phát triển là nguồn **non-reproducible build** rất khó phát hiện.

Không dùng điều kiện theo file tồn tại trong workspace cho cấu hình tạo artifact phát hành nếu file đó không được xác định/kiểm soát trong cùng nguồn build. Nếu file chỉ phục vụ phát triển cục bộ, tác động của profile nên bị giới hạn vào tác vụ không ảnh hưởng artifact phát hành.

### 3.6. activeByDefault và profile trong settings.xml

~~~xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
~~~

Khi một profile trong POM dùng `activeByDefault`, nó có thể tự bật nếu không có profile khác **trong cùng POM** được kích hoạt theo các cơ chế thích hợp; việc bật profile khác có thể khiến profile mặc định này tự tắt. Vì vậy “mặc định” **không đồng nghĩa “luôn bật”**, nhất là khi thêm `-Pci` vào CI.

Ngoài POM, `~/.m2/settings.xml` có thể có:

~~~xml
<activeProfiles>
    <activeProfile>developer-repos</activeProfile>
</activeProfiles>
~~~

Đây là **đoạn đặt trong `<settings>`**, không phải một file settings hoàn chỉnh; profile ID phải có định nghĩa hợp lệ tương ứng. Một profile từ settings có thể cung cấp properties hoặc repository khác theo từng máy. Đừng chỉ nhìn file `pom.xml` của Git rồi khẳng định mọi người đang dùng cùng cấu hình.

### 3.7. Ranh giới parent–child trong multi-module

Maven **không kế thừa nguyên định nghĩa profile từ parent sang child** như các khối cấu hình POM thông thường; profile được xét trong model builder, rồi **tác động của profile đang hoạt động** có thể được kế thừa. Hai profile cùng ID ở hai POM khác nhau không mặc nhiên dùng cùng activation context. Khi một reactor tạo ra một số module khác nhau theo máy, phải kiểm tra effective POM của **đúng module** và các cấu hình settings/parent thực sự được áp dụng.

## 4. Tại sao profile làm artifact “cùng version nhưng khác nội dung”?

Maven xác định artifact chính bằng tọa độ như:

~~~text
vn.example:profile-variant-demo:jar:1.0.0
~~~

Phần GAV (groupId, artifactId, version) không tự chứa tên profile hoặc danh sách các properties của môi trường. Nếu hai lần build dùng cùng GAV nhưng profile thay đổi những thứ sau, artifact có thể khác:

- **Resource filtering**: file `application.properties`, banner, manifest hoặc JSON được thay placeholder theo property của profile.
- **Dependencies**: profile thêm/đổi dependency version, scope hoặc repository resolution, dẫn đến classpath và sản phẩm build khác.
- **Plugin configuration**: thay compiler args, Java release, code generation, shading, minification, resource excludes hoặc manifest.
- **Các bước sinh dữ liệu**: thời gian hiện tại, username, absolute path, Git branch chưa được ghim, file cấu hình ngoài Git hoặc biến môi trường.
- **Khác biệt nền tảng**: JDK/compiler, encoding, line endings, locale, timezone, file ordering hoặc cách plugin đóng gói.

Một số thay đổi chỉ ảnh hưởng test/report; một số làm khác **nội dung thực sự của JAR**. Không nên tự kết luận từ việc profile được bật là file chắc chắn khác: phải **kiểm chứng artifact thực tế**.

Để minh họa nguyên nhân một cách xác định, phần sau tạo một JAR chứa resource được lọc từ property. Khi profile bật, file resource chắc chắn mang giá trị khác, và chương trình đọc từ JAR sẽ in giá trị khác.

## 5. Dự án thực hành có chủ đích tạo artifact khác nhau

### 5.1. Cấu trúc thư mục

Tạo dự án `profile-variant-demo`:

~~~text
profile-variant-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/profiles/Edition.java
    │   └── resources/edition.properties
    └── test/
        └── java/vn/example/profiles/EditionTest.java
~~~

Dự án dùng Maven 3.9.x, JDK 17, Resources Plugin 3.3.1, Compiler Plugin 3.14.1, Surefire Plugin 3.5.4, JAR Plugin 3.4.2 và JUnit Jupiter 5.11.4. Trong lần chạy đầu, Maven có thể cần tải dependency/plugin từ repository. Mọi lệnh bên dưới được thực hiện trong thư mục chứa `pom.xml`.

### 5.2. POM đầy đủ: `profile-variant-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>profile-variant-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
        <app.mode>standard</app.mode>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
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
            <id>machine-workstation</id>
            <activation>
                <property>
                    <name>env.BUILD_FLAVOR</name>
                    <value>workstation</value>
                </property>
            </activation>
            <properties>
                <app.mode>workstation</app.mode>
            </properties>
        </profile>
    </profiles>
</project>
~~~

Giải thích chính xác những yếu tố gây khác biệt:

- Property `app.mode=standard` ở POM chính là giá trị cơ sở.
- Khi biến môi trường `BUILD_FLAVOR` bằng `workstation`, profile `machine-workstation` bật và hiệu lực `app.mode` được đổi thành `workstation`.
- `resources` bật filtering cho `src/main/resources`. Placeholder `@app.mode@` ở file properties sẽ được thay bằng giá trị có hiệu lực của property.
- `project.build.outputTimestamp` là một nỗ lực kiểm soát **timestamp entry của archive**; nó **không** ngăn việc profile thay nội dung một file. Đây là điểm cố tình đưa vào để thấy: có timestamp ổn định vẫn có thể build ra JAR khác nhau.
- Plugin/dependency versions đều được chỉ định tường minh để không biến sự khác biệt trong bài thành kết quả do plugin version ngẫu nhiên.

**Cảnh báo:** POM này là ví dụ *phản mẫu* cần nhận diện và cải thiện, không phải cấu hình phát hành nên sao chép nguyên vẹn.

### 5.3. Resource được lọc tại build time

File `src/main/resources/edition.properties`:

~~~properties
mode=@app.mode@
~~~

Maven Resources Plugin sử dụng placeholder `@app.mode@` khi resource filtering được bật. Ở lần build bình thường, file `target/classes/edition.properties` dự kiến có:

~~~properties
mode=standard
~~~

Ở lần build có profile workstation, nó trở thành:

~~~properties
mode=workstation
~~~

**File nguồn** `src/main/resources/edition.properties` vẫn chứa `@app.mode@`. Sự thay thế xảy ra ở file build output. Vì JAR Plugin lấy nội dung từ `target/classes`, giá trị đã được lọc sẽ đi **vào JAR**.

Chỉ nên bật filtering có kiểm soát đối với resource text thích hợp; không lọc bừa file nhị phân. Các giá trị minh họa ở đây chỉ chứa ASCII để tránh khác biệt encoding của Java `Properties.load(InputStream)`.

### 5.4. Mã Java đọc tài nguyên từ classpath

File `src/main/java/vn/example/profiles/Edition.java`:

~~~java
package vn.example.profiles;

import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;
import java.util.Properties;

public final class Edition {
    private Edition() {
    }

    public static String mode() {
        Properties props = new Properties();
        try (InputStream input = Edition.class.getClassLoader()
                .getResourceAsStream("edition.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing edition.properties");
            }
            props.load(input);
        } catch (IOException cause) {
            throw new IllegalStateException("Cannot load edition.properties", cause);
        }
        return Objects.requireNonNull(props.getProperty("mode"),
                "Missing mode property");
    }

    public static void main(String[] args) {
        System.out.println("artifact-mode=" + mode());
    }
}
~~~

`Edition.mode()` đọc resource **được đóng gói trong classpath/JAR**. Chương trình không đọc trực tiếp biến môi trường `BUILD_FLAVOR`. Vì vậy, nếu build time đã nhúng `workstation` vào resource, xóa biến môi trường **sau khi build** cũng không biến JAR ấy thành bản `standard`.

### 5.5. Unit test hợp lệ ở cả hai chế độ

File `src/test/java/vn/example/profiles/EditionTest.java`:

~~~java
package vn.example.profiles;

import static org.junit.jupiter.api.Assertions.assertTrue;
import java.util.Set;
import org.junit.jupiter.api.Test;

class EditionTest {
    @Test
    void hasSupportedMode() {
        assertTrue(Set.of("standard", "workstation")
                .contains(Edition.mode()));
    }
}
~~~

Test này xác nhận resource đã được tải và giá trị thuộc một trong hai mode dự kiến; nó **không bảo đảm hai artifact bằng nhau**. Đây là một bài học quan trọng: **BUILD SUCCESS + test PASS** không tương đương **reproducible artifact**.

Bạn sẽ dùng checksum và so sánh nội dung để kiểm tra câu hỏi reproducibility riêng.

## 6. Thí nghiệm A: build trên máy không có profile workstation

Từ thư mục dự án, trước tiên kiểm tra:

~~~bash
java -version
mvn -version
~~~

Hãy đảm bảo Maven đang chạy bằng JDK 17+ phù hợp cấu hình compiler.

### 6.1. Trên Linux/macOS dùng Bash

~~~bash
unset BUILD_FLAVOR
mvn help:active-profiles
mvn clean package
java -cp target/profile-variant-demo-1.0.0.jar vn.example.profiles.Edition
sha256sum target/profile-variant-demo-1.0.0.jar
~~~

Dòng in bởi **chương trình Java** là:

~~~text
artifact-mode=standard
~~~

Dòng checksum SHA-256 chứa một chuỗi 64 ký tự hexa và tên file. **Không ghi một checksum mẫu bịa đặt**: giá trị thực phụ thuộc đúng bytes của JAR được tạo trên máy.

### 6.2. Trên Windows PowerShell

~~~powershell
Remove-Item Env:BUILD_FLAVOR -ErrorAction SilentlyContinue
mvn help:active-profiles
mvn clean package
java -cp target\profile-variant-demo-1.0.0.jar vn.example.profiles.Edition
Get-FileHash -Algorithm SHA256 target\profile-variant-demo-1.0.0.jar
~~~

PowerShell trả `Hash` ở dạng hex. Hãy ghi lại hash gọi là **H1** và ghi rõ profile đang active, JDK/Maven version cùng commit mã nguồn.

Ở lần build này, goal `resources:resources` đã copy và thay placeholder thành `mode=standard`, Compiler Plugin tạo class, Surefire chạy test và JAR Plugin đóng gói resource đó. File JAR mang tọa độ:

~~~text
vn.example:profile-variant-demo:jar:1.0.0
~~~

## 7. Thí nghiệm B: cùng mã nguồn, một biến môi trường khác

Không sửa `pom.xml`, không đổi `version`, không commit file mới. Chỉ thay biến môi trường trong terminal.

### 7.1. Linux/macOS

~~~bash
export BUILD_FLAVOR=workstation
mvn help:active-profiles
mvn clean package
java -cp target/profile-variant-demo-1.0.0.jar vn.example.profiles.Edition
sha256sum target/profile-variant-demo-1.0.0.jar
unset BUILD_FLAVOR
~~~

### 7.2. Windows PowerShell

~~~powershell
$env:BUILD_FLAVOR = 'workstation'
mvn help:active-profiles
mvn clean package
java -cp target\profile-variant-demo-1.0.0.jar vn.example.profiles.Edition
Get-FileHash -Algorithm SHA256 target\profile-variant-demo-1.0.0.jar
Remove-Item Env:BUILD_FLAVOR
~~~

Lần này `help:active-profiles` cần hiển thị profile `machine-workstation` được kích hoạt, nếu không có cấu hình nào khác làm thay đổi hành vi. Stdout của chương trình Java:

~~~text
artifact-mode=workstation
~~~

Gọi checksum mới là **H2**. Với dự án mẫu và build thành công:

- **H1 khác H2**, vì ít nhất entry `edition.properties` trong JAR chứa nội dung khác nhau.
- Cả hai lần đều có thể hiện `BUILD SUCCESS` và test `hasSupportedMode` PASS.
- Cả hai artifact đều có tên `profile-variant-demo-1.0.0.jar` và cùng `groupId/artifactId/version`.
- Giá trị cố định của `project.build.outputTimestamp` chỉ giúp kiểm soát timestamp archive; nó **không thể làm hai chuỗi `mode=standard` và `mode=workstation` trở nên giống nhau**.

Quan sát này chứng minh lỗi thiết kế: **một nguồn phát hành có thể tạo hai nội dung nhưng không có định danh biến thể trong tọa độ Maven**. Khi thay artifact lên một kho có chính sách không cho overwrite release, bạn còn có thể gặp lỗi repository; không dùng cách ghi đè release artifact để “cập nhật” một biến thể theo máy.

### 7.3. Muốn giữ cả hai JAR để so sánh thì làm thế nào?

Mỗi lần chạy `mvn clean package` xóa thư mục `target` rồi tạo JAR mới. Nếu muốn so sánh **trực tiếp hai file**, hãy copy JAR H1 và H2 ra một thư mục thí nghiệm **ngoài `target`** sau từng lần build, bằng tên phân biệt như `profile-variant-demo-standard.jar` và `profile-variant-demo-workstation.jar`. Đó chỉ là thao tác giữ mẫu để điều tra; **việc đổi tên file thủ công không tạo Maven classifier hoặc tọa độ artifact mới**.

Sau đó có thể dùng `jar tf` để xem các entry:

~~~bash
jar tf target/profile-variant-demo-1.0.0.jar
~~~

Tìm `edition.properties` và `vn/example/profiles/Edition.class`. `jar tf` chỉ **liệt kê tên entry**, nên tự nó không đủ để chứng minh giá trị `mode` khác nhau. Để xác minh nội dung, chạy `Edition.main` như trên, mở entry `edition.properties` bằng công cụ đọc JAR thích hợp, hoặc giải nén từng file mẫu vào thư mục riêng để so sánh text.

### 7.4. Khôi phục sau thử nghiệm

Xóa biến `BUILD_FLAVOR` trong terminal hiện tại và chạy:

~~~bash
mvn clean package
java -cp target/profile-variant-demo-1.0.0.jar vn.example.profiles.Edition
~~~

Đầu ra trở về `artifact-mode=standard`. Nếu biến `BUILD_FLAVOR` còn được IDE, shell profile hoặc CI job đặt **lại** trong một terminal mới, nó có thể tiếp tục kích hoạt profile. Đó chính là lý do chỉ “xóa tạm biến rồi build lại” không phải cách sửa lâu dài.

## 8. Truy vết: kiểm tra active profiles và effective POM

Khi hai máy build khác nhau, đừng lập tức xóa cache hoặc sửa `pom.xml` theo suy đoán. Hãy so sánh **cấu hình có hiệu lực** và **đầu ra**.

### 8.1. Kiểm tra profile nào thực sự bật

~~~bash
mvn help:active-profiles
~~~

Goal này cho biết những profile đang hoạt động trong bối cảnh project của lệnh. Với dự án nhiều module, kiểm tra module tương ứng; profile từ parent, child và settings có thể ảnh hưởng các project theo cách khác nhau.

Có thể chọn module cụ thể trong reactor:

~~~bash
mvn -pl :app help:active-profiles
~~~

Lệnh ở trên **chỉ là ví dụ cho dự án reactor thực sự có module `app`**; project `profile-variant-demo` trong bài chỉ có một module và không dùng được selector `:app`.

### 8.2. Xem property cuối cùng và nguồn cấu hình

~~~bash
mvn help:evaluate -Dexpression=app.mode -q -DforceStdout
mvn help:effective-pom
mvn help:effective-pom -Dverbose
~~~

Trong dự án mẫu, `help:evaluate` phải cho giá trị `standard` hoặc `workstation` tùy môi trường. `effective-pom` có thể giúp tìm profile effect, plugin, properties và dependency cuối cùng. `-Dverbose` của Help Plugin thường cung cấp thêm thông tin nơi khai báo cấu hình.

**Hạn chế cần nhớ:** effective POM thể hiện mô hình Maven, không phải toàn bộ trạng thái môi trường hoặc toàn bộ tập byte JAR. Nó không tự ghi lại tất cả file đọc ngoài POM, JDK vendor, DNS mirror, environment hay kết quả các plugin sinh dữ liệu.

### 8.3. Xem settings và lựa chọn Maven/JDK

~~~bash
mvn --version
mvn help:effective-settings
~~~

`settings.xml` có thể bật profiles hoặc cung cấp repository, mirror và properties. Trong dự án doanh nghiệp, global settings và user settings trên hai máy có thể khác nhau dù `pom.xml` giống nhau.

**Cẩn thận khi chia sẻ:** effective settings, effective POM và debug logs có thể bộc lộ hostname repository nội bộ, đường dẫn hoặc properties nhạy cảm. Help Plugin mặc định che password trong effective settings, nhưng vẫn cần rà soát nội dung trước khi đưa vào ticket công khai. Không bật chế độ hiện mật khẩu.

### 8.4. Đọc đúng đầu ra cần so sánh

| Bằng chứng | Trả lời câu hỏi gì? | Có thể chứng minh artifact trùng bytes không? |
| --- | --- | --- |
| `git rev-parse HEAD` | Hai máy dùng cùng commit nào? | Chưa |
| `mvn --version` | Maven/JDK runtime đang dùng là gì? | Chưa |
| `help:active-profiles` | Profile nào active trong project hiện tại? | Chưa |
| `help:effective-pom` | Config build cuối cùng của project là gì? | Chưa |
| `help:effective-settings` | Settings/repository/profiles người dùng nào có hiệu lực? | Chưa |
| Nội dung `target/classes/edition.properties` | Resource filtering đã ra giá trị gì? | Chỉ chứng minh một đầu vào JAR |
| `jar tf` | JAR có những entry nào? | Chưa; cùng tên entry vẫn có thể khác bytes |
| **SHA-256 của JAR** | Byte của file JAR có khớp nhau hay không? | Có, với xác suất va chạm thực tế không đáng kể; vẫn cần xác minh nguồn gốc tin cậy |

Nếu hash khác, tiếp tục kiểm tra **cấu trúc và nội dung archive**, không chỉ so sánh file name hoặc dòng `BUILD SUCCESS`. Nếu hash giống, bạn đã có bằng chứng mạnh về nội dung **file đó**, nhưng không có nghĩa toàn bộ deployment (secrets, config, dữ liệu, services) sẽ hành xử giống nhau.

## 9. Cách sửa ưu tiên: bỏ activation theo máy khỏi artifact phát hành

Trong ví dụ POM đang có:

~~~xml
<profiles>
    <profile>
        <id>machine-workstation</id>
        <activation>
            <property>
                <name>env.BUILD_FLAVOR</name>
                <value>workstation</value>
            </property>
        </activation>
        <properties>
            <app.mode>workstation</app.mode>
        </properties>
    </profile>
</profiles>
~~~

Để sửa nguồn gốc sai khác, **xóa toàn bộ profile `machine-workstation`** khỏi POM phát hành, nếu ứng dụng không thật sự cần nhiều binary variants. Giữ property cơ sở `<app.mode>standard</app.mode>` chỉ khi nó là **dữ liệu cố định của artifact**, không phải môi trường triển khai.

Sau thay đổi, hai máy có hoặc không có `BUILD_FLAVOR=workstation` sẽ không còn vì chính profile này mà lọc ra hai edition khác nhau. Cần kiểm tra thêm các nguồn profile khác, plugin, JDK, settings và tài nguyên ngoài repository trước khi kết luận build tái lập hoàn toàn.

**Không dùng `-P=-machine-workstation` làm phương án sửa vĩnh viễn** nếu POM vẫn chứa profile nguy hiểm và một hệ thống build nào đó quên truyền cờ. Maven hỗ trợ cú pháp vô hiệu hóa profile `-P=-machine-workstation`, có ích khi điều tra hoặc cưỡng chế tạm thời, nhưng giải pháp bền vững là loại đường kích hoạt không mong muốn ở chính mô hình build.

### 9.1. Nếu thật sự cần profile, kích hoạt tường minh và ghi nhận

Một số profile là lựa chọn build chủ đích, ví dụ một bộ kiểm tra tĩnh, tạo tài liệu, hoặc một variant sản phẩm với chức năng khác. Khi đó hãy ưu tiên:

- Profile có tên có ý nghĩa, được định nghĩa trong Git và **không tự bật chỉ vì hostname, username hoặc biến môi trường cục bộ**.
- Một **lệnh build được chuẩn hóa** trong CI, chẳng hạn `mvn -B -ntp -Pci clean verify` nếu POM thực sự có profile `ci`.
- Build record lưu commit, Maven/JDK version, active profiles, plugin/dependency lock hoặc version, SHA-256 và nguồn artifact.
- Nếu profile làm artifact khác bytes, hãy phát hành dưới **tọa độ/variant nhận diện riêng** (ví dụ artifactId/version hoặc classifier được cấu hình bằng plugin và chính sách artifact repository), thay vì phát hành hai nội dung khác nhau cùng một GAV.

Kể cả profile kích hoạt **tường minh** vẫn có thể tạo artifact khác nhau; sự tường minh chỉ giúp quản trị/truy vết, không tự tạo reproducibility.

## 10. Tách runtime configuration ra khỏi build artifact

Cách thường dùng để triển khai **cùng một JAR** ở dev, staging và production là ứng dụng đọc cấu hình **khi khởi động**, thay vì Maven nhúng tên môi trường vào JAR.

Trong dự án mẫu, sau khi **xóa profile kích hoạt theo máy** như mục 9, có thể thêm một lớp Java 17 độc lập đọc Java system property tại runtime.

File mới `src/main/java/vn/example/profiles/RuntimeMode.java`:

~~~java
package vn.example.profiles;

public final class RuntimeMode {
    private RuntimeMode() {
    }

    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "standard");
        System.out.println("runtime-mode=" + mode);
    }
}
~~~

Lớp này **không phụ thuộc** vào file `edition.properties`. Sau khi bổ sung nó và build **một lần**:

~~~bash
mvn clean package
java -cp target/profile-variant-demo-1.0.0.jar vn.example.profiles.RuntimeMode
java -Dapp.mode=staging -cp target/profile-variant-demo-1.0.0.jar vn.example.profiles.RuntimeMode
java -Dapp.mode=production -cp target/profile-variant-demo-1.0.0.jar vn.example.profiles.RuntimeMode
~~~

Stdout của **ba lần gọi Java**, theo thứ tự:

~~~text
runtime-mode=standard
runtime-mode=staging
runtime-mode=production
~~~

Trong ba lần chạy này **không có lệnh Maven build ở giữa**, nên chính file JAR trên ổ đĩa được giữ nguyên. Nếu tính SHA-256 trước và sau ba lần gọi, hash JAR phải giống nhau. Các giá trị `staging` và `production` chỉ tác động đến tiến trình Java đang chạy. Ở sản phẩm thật, cấu hình có thể đến từ environment variables, config file ngoài JAR, command line hoặc secret manager, tùy framework; nên có kiểm tra schema, giá trị hợp lệ và cơ chế bảo vệ secret.

Đoạn chuyển sang `RuntimeMode` chỉ là **giải pháp minh họa**. Nếu ứng dụng thực tế cần nhiều endpoint/credential, nên thiết kế một lớp configuration riêng, tránh đưa thông tin bí mật vào Maven resource filtering hoặc manifest phát hành.

## 11. Reproducible build: profile chỉ là một nguyên nhân

Khi profile đã ổn định, artifact vẫn có thể khác do plugin, timestamp, JDK, OS hoặc đầu vào khác. Theo hướng dẫn Maven về reproducible builds, cần cùng **nguồn, môi trường và hướng dẫn build** để tạo bản giống nhau đến từng byte.

### 11.1. Cố định phiên bản và đầu vào

| Đầu vào | Biện pháp |
| --- | --- |
| Maven | Cố định phiên bản bằng Maven Wrapper và kiểm tra `./mvnw --version` |
| JDK | Chỉ định JDK supported trong CI, kiểm tra `mvn --version` và có thể dùng toolchain/enforcer |
| Compiler release | Dùng `maven.compiler.release` hoặc `<release>17</release>` và plugin phù hợp |
| Plugin versions | Ghim các plugin có liên quan ở POM hoặc `pluginManagement` |
| Dependency versions | Tránh version range/SNAPSHOT cho release cần tái lập; quản lý dependency theo policy |
| OS/locale/encoding | Dùng runner/image chuẩn, UTF-8 và tránh input phụ thuộc platform |
| Resource filtering | Không nhúng username, HOME, hostname, time hiện tại hoặc biến môi trường không kiểm soát |
| Thời gian ZIP entry | Dùng `project.build.outputTimestamp` với plugin hỗ trợ reproducible archive |
| Build invocation | Chuẩn hóa phases, profile list, `-D` và settings được cho phép |
| Artifact output | Lưu checksum, tọa độ, commit và provenance ở hệ thống artifact/CI |

Trong POM mẫu có:

~~~xml
<project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
~~~

Thuộc tính này được JAR Plugin hỗ trợ để tạo timestamp ổn định cho archive entries. Nhưng **nó không chuẩn hóa nội dung resource do profile lọc**, không tự xử lý file JSON sắp thứ tự ngẫu nhiên hoặc bytecode khác do JDK. Vì vậy câu “đã bật `outputTimestamp` nên chắc chắn reproducible” là **sai**.

Giá trị timestamp nên được chọn/quản lý nhất quán theo quy trình phát hành; không cập nhật nó vô điều kiện bằng `new Date()` ở mỗi lần build. Nếu hệ thống release quản lý timestamp theo Git commit, cần bảo đảm mọi môi trường cùng dùng timestamp của cùng commit.

### 11.2. Đừng nhầm build reproducibility và runtime reproducibility

**Reproducible artifact**: cùng điều kiện đã quy định cho build, tạo file artifact giống nhau đến từng byte.

**Cùng hành vi runtime**: ứng dụng chạy ở nhiều môi trường có cùng đầu vào/cấu hình/dịch vụ thì kết quả tương đương. Hai điều này liên quan nhưng **không đồng nghĩa**. Dùng cùng JAR mà trỏ sang cơ sở dữ liệu khác có thể cho kết quả khác, đó không phải bằng chứng JAR bị build không ổn định.

Mục tiêu thường là: **same binary, different external runtime configuration**, với danh tính artifact minh bạch.

## 12. Lập quy trình CI để không phát hành nhầm variant

Một pipeline đáng tin nên thực hiện theo thứ tự:

1. Checkout commit xác định, runner/JDK/Maven Wrapper đã được chọn.
2. Xác nhận lệnh build và **danh sách profile có hiệu lực**.
3. Chạy build + test với phiên bản plugin/dependency được quản lý.
4. Lưu artifact vào repository theo version/immutable policy, cùng **checksum và thông tin nguồn gốc**.
5. Triển khai chính artifact đã lưu đó sang staging rồi production; **không build lại** cùng GAV trên mỗi máy triển khai.

Ví dụ lệnh đơn giản trên runner Linux, với giả định dự án đã thêm Maven Wrapper và **POM không còn profile `machine-workstation` gây khác biệt**:

~~~bash
java -version
./mvnw --version
./mvnw -B -ntp help:active-profiles
./mvnw -B -ntp clean verify
sha256sum target/profile-variant-demo-1.0.0.jar
~~~

Lệnh `./mvnw` chỉ dùng được **nếu dự án thực sự có script Maven Wrapper**. Dự án minh họa ở mục 5 chưa tạo `mvnw`; nếu chưa thêm Wrapper, hãy dùng `mvn` của môi trường đã được chuẩn hóa thay thế.

Nếu một tổ chức vẫn yêu cầu một profile build rõ ràng, CI có thể dùng `-Pci` và kiểm tra mục tiêu đó tồn tại. Hãy lưu “active profiles + checksum + commit + tool versions” như metadata của build. **Không lưu secrets** từ environment vào build metadata, không đưa toàn bộ effective settings/log debug công khai.

### 12.1. Kiểm tra hai lần build

Trên cùng commit và cùng tập tham số, chạy một lần build và lưu JAR; sau đó chạy lại trong **workspace/runner sạch khác** và đối chiếu checksum. So sánh trên hai môi trường khác nhau có giá trị hơn hai lần build liên tiếp trên một máy, vì nhiều vấn đề phụ thuộc HOME, file ngoài Git hoặc cache sẽ không lộ ra trong kiểm thử cục bộ.

Maven cũng cung cấp hướng dẫn `maven-artifact-plugin` với goal `artifact:compare` để so sánh các bản build; cần cài/cấu hình tool tương ứng và hiểu nguồn reference artifact. Nếu kết quả hash khác, so sánh entry trong JAR, manifest, resources, class bytecode rồi truy ngược đến plugin tạo nội dung ấy; công cụ như diffoscope có thể giúp nếu môi trường hỗ trợ.

**Không tự xóa toàn bộ `~/.m2/repository` để “làm build sạch”**. `mvn clean` dọn output project, còn cache dependency nên được quản lý theo chính sách CI. Một cache thay đổi làm lộ dependency/plugin version linh động cũng là tín hiệu cần sửa cấu hình nguồn.

## 13. Tình huống nhiều module và parent POM

Một dự án reactor:

~~~text
shop/
├── pom.xml            # aggregator và parent
├── core/pom.xml
├── api/pom.xml
└── app/pom.xml
~~~

Giả sử parent có profile kích hoạt bằng `env.BUILD_FLAVOR`. Khi một profile parent được kích hoạt, các **tác động cấu hình** của nó có thể được child nhận qua inheritance. Nhưng profile definition ở parent **không được kế thừa như một profile nguyên khối**. Module con có thể có profile riêng, settings áp dụng khác hoặc property do module override.

Hệ quả: có trường hợp `core` và `api` đóng gói giống nhau trên hai máy, nhưng `app` có resource/filtering hoặc plugin khác. Nếu chỉ xem checksum JAR của `core` rồi tuyên bố cả reactor reproducible, đó là kết luận thiếu dữ liệu.

Với reactor thực sự có các module trên, từ root có thể chạy:

~~~bash
mvn -pl :app -am help:active-profiles
mvn -pl :app help:effective-pom
mvn -pl :app -am clean verify
~~~

Sau đó lưu checksum và GAV cho **từng artifact được phát hành**, không chỉ bản `app`. `-am` chọn các module upstream cần thiết, **không** tự thay cách profile được kích hoạt hoặc ghi lại trạng thái môi trường. Kiểm tra active profiles trong project cụ thể nếu cần.

## 14. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xác minh/sửa |
| --- | --- | --- |
| Hai máy cùng commit/GAV nhưng SHA-256 khác | Profile, resource, JDK, plugin, timestamp, file ngoài Git | So sánh active profiles, effective POM, outputTimestamp, JAR entries và metadata build |
| Laptop build `workstation` nhưng CI build `standard` | `env.BUILD_FLAVOR` chỉ tồn tại ở laptop | Xem biến môi trường, profile activation và filtered resource |
| Một lần mở IDE làm artifact khác terminal | IDE đặt JDK, JVM options, env hoặc Maven settings riêng | So sánh Maven/JDK runtime, active profiles và command line |
| File `local-build.flag` có ở máy A nhưng không ở B | Profile có `<activation><file><exists>...` | Truy vết file ngoài Git, bỏ activation nhạy cảm khỏi release build |
| JDK 17 và JDK 21 cho artifact khác | Profile `<jdk>` hoặc compiler/runtime/plugin khác | Chuẩn hóa JDK, kiểm tra `mvn --version` và toolchain |
| `activeByDefault` biến mất khi thêm `-Pci` | Profile khác cùng POM được kích hoạt | Xem active profile thực tế; tránh dựa vào một mặc định ngầm |
| User settings trên máy A thay đổi behavior | `settings.xml` kích hoạt profile hoặc cung cấp property khác | Kiểm tra effective settings/active profiles, không xuất bí mật |
| Test đều PASS nhưng JAR khác | Test không kiểm tra reproducibility | Kiểm tra checksum và nội dung JAR; tách hai mục tiêu kiểm thử |
| Chỉ timestamp trong ZIP khác | Plugin chưa hỗ trợ reproducible archive hoặc timestamp chưa cố định | Xem `project.build.outputTimestamp` và bản plugin |
| Cùng file JAR nhưng hành vi dev/prod khác | Runtime config, env, data hoặc external service khác | Phân biệt khác biệt runtime với build artifact |
| Một repo chấp nhận publish đè GAV | Policy artifact repository quá lỏng | Dùng immutable release, version/variant identity và provenance |
| `jar tf` giống nhau nhưng hash khác | Entry names giống nhưng bytes/timestamp/metadata khác | So sánh nội dung entry, manifest, timestamps, class/resource |
| `mvn help:active-profiles` không chạy vì plugin tải thất bại | Repository/Proxy chưa giải quyết được Help Plugin | Kiểm tra Maven settings/mạng, không kết luận không có profile |
| `-Pci` báo profile không được kích hoạt | Profile ID không tồn tại/không khả dụng | Kiểm tra profile trong POM/settings và phiên bản Maven |
| Build phụ thuộc file `.env` ngoài Git | Build plugin tự đọc file, hoặc profile kích hoạt theo file | Tách runtime config hoặc quản lý đầu vào rõ ràng và an toàn |

Đọc lỗi theo ba nguồn: **effective config**, **log thực thi plugin**, **byte đầu ra**. Không có một lệnh nào thay thế hoàn toàn cả ba lớp kiểm chứng.

## 15. Những quy tắc thiết kế profile an toàn cho artifact phát hành

Đối với một dịch vụ phát hành theo cùng artifact cho nhiều môi trường, có thể áp dụng bộ nguyên tắc:

- **Không dùng profile dựa vào `os`, `jdk`, `file`, `env` hoặc user settings để âm thầm thay code/config nhúng trong JAR phát hành.** Điều kiện môi trường có thể phù hợp cho kiểm tra kỹ thuật đặc thù nhưng cần được quản lý minh bạch.
- Đặt dependency và plugin versions ở POM/parent có thể review; hạn chế động hóa version hoặc lấy nguồn artifact tùy máy.
- Không dùng profile để đưa **secrets** vào artifact; sử dụng secret manager/runtime config.
- Nếu có biến thể sản phẩm thật sự khác, định nghĩa profile build tường minh, pipeline riêng và **artifact coordinates/classifier/version** có thể phân biệt.
- Không dùng `activeByDefault` theo cách khiến một profile khác bất ngờ tắt cấu hình bắt buộc. Thiết lập mặc định quan trọng nên nằm ở phần POM chính, kèm cơ chế override có kiểm soát.
- Kiểm tra hash của artifact đã lưu, không build lại trong deployment; gắn commit và thông tin build để truy vết.
- Dùng các bài test bảo đảm logic, **và** dùng kiểm tra reproducibility độc lập; `BUILD SUCCESS` không là bằng chứng hash tương đương.

### Anti-pattern và phương án thay thế

| Anti-pattern | Hậu quả | Phương án ưu tiên |
| --- | --- | --- |
| Profile `dev` tự bật trên Windows và nhúng `server.url=dev` vào JAR | Cùng version chứa URL khác | Runtime config ngoài JAR |
| Profile `prod` bật chỉ khi CI có `env.CI` | Build máy khác tạo binary khác | CI build một artifact được định danh, deploy artifact đó |
| Profile phụ thuộc file `~/.myteam` | Không thể tái lập ở runner sạch | Bỏ điều kiện hoặc kiểm soát đầu vào trong source/build specification |
| Profile thêm dependency không ghim version | Transitive dependency khác theo ngày/máy | Ghép version management + artifact policy |
| Dùng `-Pci` và `-Pdeveloper` cho hai JAR cùng GAV | Khó xác định artifact nào là bản chuẩn | Variant identity riêng hoặc chỉ phát hành một JAR |
| Tạo timestamp bằng thời gian hiện tại trong manifest | Mỗi lần build khác bytes | Timestamp có thể tái lập + plugin hỗ trợ |
| Kiểm tra mỗi file name/version | Che giấu khác biệt byte | SHA-256, provenance và archive comparison |

## 16. Bài tập thực hành và tiêu chí hoàn thành

**Bài tập A — Kích hoạt theo biến môi trường.** Với dự án `profile-variant-demo`, chạy hai lần từ trạng thái sạch: không có `BUILD_FLAVOR` và có `BUILD_FLAVOR=workstation`. Ghi active profiles, `Edition.main` stdout và SHA-256. Giải thích vì sao cùng GAV có hai file khác nội dung.

**Bài tập B — Chứng minh outputTimestamp không đủ.** Giữ `project.build.outputTimestamp` cố định trong POM. Chạy lại hai mode, xác nhận giá trị resource nhúng khác. Phân biệt timestamp ổn định với nội dung artifact ổn định.

**Bài tập C — So sánh profile activation.** Viết một bảng hai máy: JDK 17/21, Windows/Linux, file `local-build.flag` có/không, user settings profile bật/tắt. Với mỗi điều kiện, dự đoán profile được kích hoạt trong ví dụ XML liên quan. Kiểm tra bằng `help:active-profiles` khi có môi trường phù hợp.

**Bài tập D — Khắc phục đúng nguyên nhân.** Xóa profile `machine-workstation` ra khỏi POM và build lại ở hai terminal có biến môi trường khác nhau. Xác nhận cả hai chạy `Edition.main` với mode `standard`. Sau đó kiểm tra hash, đồng thời lưu ý các nguồn non-reproducibility khác vẫn có thể tồn tại.

**Bài tập E — Cùng JAR, nhiều runtime mode.** Thêm `RuntimeMode.java`, build một lần rồi chạy ba lần Java có/không có `-Dapp.mode`. Xác nhận stdout thay đổi nhưng SHA-256 của file JAR không đổi vì không build lại.

**Bài tập F — Quy tắc release.** Viết một checklist CI có commit SHA, Maven/JDK version, active profiles, POM/plugin/dependency version, JAR SHA-256 và địa chỉ artifact repository bất biến. Giải thích vì sao triển khai bằng **promote** an toàn hơn biên dịch lại trên production.

**Bài tập G — Điều tra lỗi giả lập.** Một nhóm báo “cùng commit, cùng `mvn package` nhưng CI ra nội dung khác laptop”. Lập thứ tự kiểm tra gồm: profile activation, effective POM/settings, môi trường JDK, resource filtering, ZIP entries, plugin versions và nguồn input bên ngoài. Đề xuất thay đổi **tối thiểu, có căn cứ** thay vì xóa mọi profile.

### Tự đánh giá

Bạn hoàn thành bài khi có thể trả lời rõ:

1. Profile nào đang hoạt động và **vì sao** nó được kích hoạt trên máy này?
2. Cấu hình đó thay đổi **build output** hay chỉ thay đổi quá trình chạy?
3. Cùng source/GAV nhưng khác SHA-256 có được xem là cùng artifact phát hành không? **Không, đó là hai tập byte khác nhau**.
4. Thay đổi nào ngăn biến môi trường cục bộ quyết định nội dung JAR?
5. Làm sao phát hành một binary qua nhiều môi trường mà vẫn khác URL/config runtime?
6. Thông tin tối thiểu nào giúp tìm lại đúng file đã phát hành?

Bài học quan trọng nhất là: **profile là một phần của đầu vào build. Nếu đầu vào đó phụ thuộc vào máy mà không được khai báo và ghi nhận, tên file/version sẽ không đủ để truy vết sản phẩm.** Ưu tiên build ổn định, quản lý profile có chủ đích, cấu hình runtime tách khỏi binary và sử dụng checksum cùng provenance để xác minh.

## 17. Tài liệu Maven chính thức

- [Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): kiểu profile, cách activation theo JDK/OS/property/file, `activeByDefault`, `-P`, profile inheritance và các cảnh báo về khác biệt build.
- [Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): xây dựng artifact có thể tái tạo, timestamp, kiểm tra khác biệt và hạn chế khi chỉ test cục bộ.
- [Maven POM Reference](https://maven.apache.org/pom.html): properties, build/resources, profiles và cơ chế model.
- [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html): cách `@...@` được thay bằng property khi filtering.
- [Maven JAR Plugin — jar goal](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html): tham số `outputTimestamp` và nguồn đầu vào đóng gói.
- [Maven Help Plugin](https://maven.apache.org/plugins/maven-help-plugin/): các goal `active-profiles`, `effective-pom` và `evaluate` phục vụ truy vết.
