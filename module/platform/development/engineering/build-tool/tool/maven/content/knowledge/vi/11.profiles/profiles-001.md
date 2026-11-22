# Profile là gì và khi nào cần biến thể cấu hình build trong Maven?

## 1. Khái niệm Profile và mục đích

**Maven Build Profile** là một tập cấu hình có tên, được Maven kích hoạt theo yêu cầu hoặc theo điều kiện. Khi profile được kích hoạt, những cấu hình của nó được hợp nhất vào **effective POM**, từ đó ảnh hưởng cách Maven phân giải dependency, thực thi plugin, xử lý resource, biên dịch, kiểm thử hoặc đóng gói.

Một POM có thể chứa nhiều profile như **dev**, **prod**, **integration-tests** hoặc **quality**. Chúng không phải những dự án khác nhau: vẫn là cùng Maven project, nhưng **có biến thể cấu hình build**.

Ba khái niệm cần tách biệt:

- **Lifecycle/phase**: thứ tự công việc của Maven, chẳng hạn validate, compile, test, package, verify.
- **Plugin goal**: hành động thực tế, ví dụ compiler:compile hoặc resources:resources.
- **Profile**: lựa chọn cấu hình sẽ có hiệu lực khi chạy lifecycle/goals đó.

Ví dụ, profile **prod** có thể đặt một property phục vụ Maven Resources Plugin; nếu không có plugin hoặc resource nào dùng property, việc chọn profile này không tự thay đổi output. Profile **không tự có nghĩa triển khai lên production**. Deploy là một công việc riêng có pipeline, permissions và đích triển khai.

**Khi nào cần profile?** Khi cùng source/POM nền tảng phải tạo các kết quả build có khác biệt hợp lý và được kiểm soát: bật plugin check chỉ trong một job, sinh bộ tài nguyên khác, chọn generator phù hợp, thêm integration checks, hoặc xử lý khác biệt JDK/OS đáng kể.

**Khi nào không cần?** Nếu ứng dụng chỉ cần URL database, token, log level hoặc số worker khác nhau khi *chạy*, thường nên quản lý cấu hình runtime. Một artifact bất biến build một lần rồi deploy nhiều nơi thường dễ kiểm soát hơn việc tạo các JAR khác nhau chỉ để đổi endpoint.

## 2. Một Profile được khai báo như thế nào?

Trong **pom.xml**, profile nằm trong phần tử **<profiles>**. Mỗi **<profile>** có **<id>** làm tên nhận diện, có thể có **<activation>** và những phần cấu hình được phép.

Ví dụ (mảnh POM, cần đặt bên trong **<project>**):

~~~xml
<profiles>
    <profile>
        <id>dev</id>
        <properties>
            <build.mode>development</build.mode>
        </properties>
    </profile>
    <profile>
        <id>prod</id>
        <properties>
            <build.mode>production</build.mode>
        </properties>
    </profile>
</profiles>
~~~

Chọn một profile bằng tùy chọn Maven **-P**:

~~~bash
mvn -Pdev clean package
mvn -Pprod clean package
~~~

Khi **dev** active, property **build.mode** được cung cấp với giá trị **development**. Khi **prod** active, giá trị là **production**. Cấu hình thực sự được sử dụng bởi các plugin trong quá trình build; một Java program không tự đọc được giá trị Maven property chỉ vì POM khai báo nó.

Các thành phần thường có thể khai báo trong POM profile:

| Phần tử | Ý nghĩa khi profile active |
| --- | --- |
| **id** | Tên profile để chọn/quan sát |
| **activation** | Điều kiện tự kích hoạt |
| **properties** | Thêm hoặc ghi đè project properties |
| **dependencies** | Bổ sung dependency khi cần |
| **dependencyManagement** | Quản lý version/scope/exclusions cho dependency |
| **build** | Điều chỉnh resources, plugins, executions và phần build hỗ trợ |
| **repositories** | Bổ sung nguồn phân giải artifacts |
| **pluginRepositories** | Bổ sung nguồn tải Maven plugins |
| **reporting** | Thay đổi cấu hình reporting theo phạm vi model hỗ trợ |

**Không đặt tùy ý toàn bộ cấu trúc project bên trong profile.** Profiles hỗ trợ một tập con của POM; chẳng hạn cấu trúc module aggregation và tọa độ artifact không nên coi là những trường được đổi trực tiếp trong profile theo cách tùy tiện.

## 3. Ba nơi định nghĩa Profile

### 3.1. Project POM: pom.xml

Profile khai báo trực tiếp trong **pom.xml** được lưu cùng source trong version control. Đây là nơi phù hợp cho những khác biệt **có ý nghĩa về build** mà đồng đội và CI đều cần nhìn thấy.

Ví dụ:
- Chọn cách resource filtering cho môi trường build cụ thể.
- Bật test/plugin checks không cần trong local feedback loop.
- Thêm goal để generate code khi có bộ generator/tool tương ứng.

### 3.2. User settings: ~/.m2/settings.xml

Profile của người dùng trong **settings.xml** có phạm vi và khả năng khác profile trong POM. Phù hợp nhất cho những thông tin phụ thuộc máy/người dùng, như **repository**, **pluginRepository**, và **properties** theo cách Maven settings cho phép.

**Settings profile không hỗ trợ tùy ý build/plugins hoặc dependencies như POM profile.** Các phần như servers, mirrors, proxies và credentials cũng có cấu trúc settings riêng, không biến chúng thành child elements của POM profile.

### 3.3. Maven installation settings

Global Maven settings thường ở thư mục **conf/settings.xml** của Maven distribution. Các profile ở đó có thể áp dụng theo chính sách hệ thống/CI. Chúng có thể khiến build khác giữa máy cá nhân và runner dù POM Git giống hệt.

| Nơi khai báo | Ưu điểm | Rủi ro |
| --- | --- | --- |
| **pom.xml** | Dễ chia sẻ, version-control, dễ review | Có thể khiến POM phức tạp |
| **~/.m2/settings.xml** | Thích hợp cấu hình riêng của developer/CI | Build khác nhau giữa máy nếu không quản lý |
| **Global settings** | Cấu hình theo máy/Maven installation | Dễ có trạng thái ngầm, khó tái hiện nếu thiếu tài liệu |

**Không lưu secret vào pom.xml hoặc filtered resource.** Repository credentials nên được quản lý bằng settings.xml/secret manager của CI, với quyền truy cập và cơ chế redaction phù hợp.

## 4. Các cách kích hoạt Profile

### 4.1. Kích hoạt tường minh bằng Maven -P

~~~bash
mvn -Pdev test
mvn -Pprod clean package
mvn -Pprod,quality verify
~~~

**-P** nhận ID của profile; có thể chọn nhiều profile bằng danh sách dấu phẩy. Nếu kích hoạt nhiều profiles cùng ghi một property, Maven có quy tắc hợp nhất; đừng nghĩ chỉ cần viết profile nào cuối trong danh sách **-P** thì nó tự có ưu tiên cao hơn.

Với CI, dùng **-P** thường dễ audit hơn điều kiện máy tính ngầm. Hãy dùng **help:active-profiles** để xác minh profile thực sự được chọn; Maven version khác nhau có thể xử lý profile ID không tồn tại theo cách khác nhau.

### 4.2. activeByDefault

~~~xml
<profile>
    <id>dev</id>
    <activation>
        <activeByDefault>true</activeByDefault>
    </activation>
    <properties>
        <build.mode>development</build.mode>
    </properties>
</profile>
~~~

**activeByDefault** có nghĩa profile có thể active khi không có profile khác được kích hoạt trong **cùng POM** theo những cơ chế phù hợp. Khi một profile khác trong POM được kích hoạt, profile đang activeByDefault ở POM đó **bị vô hiệu**. Đây là điểm dễ bỏ sót khi sau này thêm một profile mới như **quality**.

Không nên dùng activeByDefault làm điều kiện bảo vệ duy nhất cho release production: nếu cấu hình ở nhiều profiles cùng POM phát triển phức tạp, rất dễ xảy ra trường hợp default mất tác dụng.

### 4.3. Kích hoạt bằng property

~~~xml
<profile>
    <id>quality</id>
    <activation>
        <property>
            <name>runQuality</name>
            <value>true</value>
        </property>
    </activation>
    <properties>
        <quality.level>strict</quality.level>
    </properties>
</profile>
~~~

Lệnh:

~~~bash
mvn -DrunQuality=true verify
~~~

làm điều kiện activation khớp. Nhưng **quality.level=strict** chỉ là property; nếu muốn kiểm tra chất lượng thực tế thì cần plugin goal đọc property hoặc execution được profile kích hoạt.

### 4.4. Kích hoạt theo JDK

~~~xml
<activation>
    <jdk>[17,)</jdk>
</activation>
~~~

Điều kiện này dựa trên JDK dùng **để chạy Maven**, không đương nhiên là bytecode target. Đặt **maven.compiler.release** hoặc cấu hình Compiler Plugin/Toolchains thích hợp nếu yêu cầu artifact biên dịch cho một phiên bản Java cố định.

### 4.5. Kích hoạt theo OS

~~~xml
<activation>
    <os>
        <family>windows</family>
    </os>
</activation>
~~~

Chỉ dùng khi công cụ thật sự cần path/tool chuyên biệt. Nếu không, output khác nhau giữa Windows laptop và Linux CI làm mất tính reproducible.

### 4.6. Kích hoạt theo file hiện diện

~~~xml
<activation>
    <file>
        <exists>local-build-marker.txt</exists>
    </file>
</activation>
~~~

Có thể dùng để lựa chọn tooling cục bộ, nhưng nếu file ngoài Git tồn tại ngẫu nhiên trên một máy, developer có thể nhận build khác CI mà không hay biết.

### 4.7. Kích hoạt qua settings.xml

Profile trong settings có thể được đưa vào danh sách **activeProfiles**:

~~~xml
<activeProfiles>
    <activeProfile>corporate-repo</activeProfile>
</activeProfiles>
~~~

Đây là **mảnh settings.xml** chứ không phải thành phần của pom.xml. Khi dùng cơ chế này, hãy kiểm tra profile được định nghĩa đúng nơi và settings đang được Maven sử dụng.

## 5. Những trường hợp biến thể build có giá trị thực tế

| Tình huống | Profile có thể làm gì? | Ranh giới |
| --- | --- | --- |
| Demo và release cần metadata/resource khác nhau | Đặt property để filter một resource văn bản | Artifact khác nhau, cần phân biệt biến thể |
| CI yêu cầu static checks bổ sung | Kích hoạt check plugin execution | Nếu check bắt buộc, nên bảo đảm CI không thể bỏ qua |
| Chạy integration tests cần thêm service/container | Bật cấu hình plugin cho pha verify | Không dùng profile để thay thế unit tests |
| Hệ điều hành cần công cụ riêng | Điều chỉnh plugin/tool phù hợp OS | Cần tránh phụ thuộc máy để build được |
| Cần sinh Java từ schema ở một loại packaging | Bật generator và đăng ký source root | Source sinh phải sẵn trước compile |
| Chỉ trong mạng công ty có private repository | Bật profile trong settings | Không cất token/password trong Git |
| Build tài liệu/site tùy chọn | Thêm plugin report hoặc execution chuyên biệt | Không phải lý do tách riêng toàn bộ POM |
| Một tham số runtime khác theo server | Thường **không cần** Maven profile | Ưu tiên environment/runtime config |

Mỗi profile cần có **mục đích cụ thể** và **khác biệt được kiểm chứng**. Nếu dự án có mười profile nhưng không ai biết profile nào được dùng trong CI, thiết kế đó khó bảo trì hơn một POM có phần chung rõ ràng và vài profile đặc thù.

## 6. Ví dụ độc lập Java 17: build dev và prod từ cùng mã nguồn

Ví dụ này cho thấy profile **thay đổi dữ liệu được đóng gói**, bằng Maven Resources Plugin. Mã Java đọc resource đã lọc trong JAR. Với cấu hình thật, có thể chạy trên Maven 3.9+ và JDK 17+ sau khi các plugin/dependency có thể tải từ repository.

### 6.1. Cấu trúc dự án

~~~text
profile-build-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/profile/App.java
    │   └── resources/build-info.properties
    └── test/
        └── java/com/example/profile/AppTest.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>profile-build-demo</artifactId>
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
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <includes>
                    <include>build-info.properties</include>
                </includes>
                <filtering>true</filtering>
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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
            <id>dev</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <build.mode>development</build.mode>
            </properties>
        </profile>
        <profile>
            <id>prod</id>
            <properties>
                <build.mode>production</build.mode>
            </properties>
        </profile>
    </profiles>
</project>
~~~

**Đọc POM:**

1. **groupId:artifactId:version** của cả hai build vẫn là **com.example:profile-build-demo:1.0.0**.
2. **maven.compiler.release=17** giữ việc biên dịch phù hợp Java 17, bất kể chọn dev/prod.
3. **junit-jupiter** thuộc test scope, không trở thành dependency runtime của JAR thông thường.
4. **build/resources** lọc file văn bản **build-info.properties**, không lọc tùy tiện file nhị phân.
5. **dev** có activeByDefault, nên khi không chọn profile khác từ cùng POM trong ví dụ, property **build.mode=development**.
6. **prod** kích hoạt bằng -Pprod và cung cấp **build.mode=production**, đồng thời tắt dev activeByDefault.
7. Những plugin build chính được pin version để ví dụ ổn định hơn; JAR cuối không tự có manifest Main-Class.

### 6.3. Resource được filter

Tạo **src/main/resources/build-info.properties** với **đúng nội dung**:

~~~properties
mode=${build.mode}
~~~

Trong Maven Resources Plugin, **filtering=true** thay placeholder có dạng **${...}** (thực chất là cú pháp Maven với ký hiệu dollar trước dấu ngoặc nhọn) bằng property tương ứng. Ở file thực tế vừa nêu, placeholder là **${build.mode}** và được thay bởi profile khi build.

Sau build dev, tài nguyên đầu ra dưới **target/classes/build-info.properties** là:

~~~properties
mode=development
~~~

Sau build prod:

~~~properties
mode=production
~~~

**Chỉ file nguồn là placeholder; file trong target/classes/JAR mới chứa giá trị đã lọc.** Nếu filtering chưa bật, placeholder sẽ còn nguyên. Đối với image hoặc file nhị phân, không nên bật filtering do có thể làm hỏng nội dung.

### 6.4. Java 17 đọc giá trị từ classpath

Tạo **src/main/java/com/example/profile/App.java**:

~~~java
package com.example.profile;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String mode() {
        try (InputStream input =
                App.class.getResourceAsStream("/build-info.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing /build-info.properties");
            }

            Properties properties = new Properties();
            properties.load(input);
            return properties.getProperty("mode", "missing");
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    public static void main(String[] args) {
        System.out.println("Mode: " + mode());
    }
}
~~~

**Class.getResourceAsStream("/build-info.properties")** lấy dữ liệu từ gốc classpath. Code dùng Java chuẩn, không cần thư viện khác ở runtime. Properties.load(InputStream) dùng quy tắc encoding của Java Properties, nhưng ví dụ chỉ chứa ASCII nên không phát sinh khác biệt chữ tiếng Việt.

### 6.5. Test JUnit cho hai biến thể

Tạo **src/test/java/com/example/profile/AppTest.java**:

~~~java
package com.example.profile;

import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class AppTest {

    @Test
    void supportedBuildMode() {
        assertTrue(
                Set.of("development", "production").contains(App.mode()),
                "Unrecognized mode in packaged resource"
        );
    }
}
~~~

Test chấp nhận hai giá trị hợp lệ để dùng chung cho dev/prod. Nó không đảm bảo một release job đã chọn đúng prod; nhiệm vụ kiểm tra variant chính xác cần thêm assert/cổng kiểm tra ở CI, hoặc đọc effective POM và artifact.

### 6.6. Build dev: không chỉ định -P

Từ thư mục **profile-build-demo**:

~~~bash
mvn -version
mvn clean package
java -cp target/profile-build-demo-1.0.0.jar com.example.profile.App
~~~

Khi dev activeByDefault theo POM ví dụ và không có activation xung đột, test pass và chương trình in stdout:

~~~text
Mode: development
~~~

Chạy Maven trong thư mục đúng chứa pom.xml; nếu plugin/dependency chưa cache, cần repository có thể truy cập được.

### 6.7. Build prod: chọn -Pprod

~~~bash
mvn -Pprod clean package
java -cp target/profile-build-demo-1.0.0.jar com.example.profile.App
~~~

Stdout:

~~~text
Mode: production
~~~

**-Pprod** chọn profile Maven; nó không tự deploy JAR. **clean** loại dữ liệu dev cũ khỏi target trước khi tạo artifact mới. Bản build mới có thể dùng **cùng tên file JAR** nhưng chứa **resource khác**, nên phải quản lý variant/metadata nếu đưa vào artifact repository.

Lệnh **java -cp ... com.example.profile.App** chạy được vì JAR có class App và resource. Ví dụ chưa thêm Main-Class vào manifest, nên không mặc định dùng **java -jar**.

### 6.8. Kiểm tra artifact thay vì suy đoán

~~~bash
jar tf target/profile-build-demo-1.0.0.jar
~~~

Trong danh sách phải có:

~~~text
build-info.properties
com/example/profile/App.class
~~~

Kết quả **jar tf** còn có các entry META-INF và thư mục; hai dòng trên chỉ minh họa những mục cần hiện diện. Muốn xác nhận giá trị cụ thể, chạy App như trên hoặc đọc file resource bên trong archive bằng công cụ ZIP/JAR thích hợp.

**Kết luận của ví dụ:** profile thực sự thay dữ liệu trong artifact qua resource filtering. Điều này rất phù hợp để minh họa nguyên lý, nhưng không phải lúc nào cũng là cách tối ưu để chuyển môi trường runtime.

## 7. Quan sát profile nào đang active

Maven Help Plugin hỗ trợ các lệnh sau:

~~~bash
mvn help:active-profiles
mvn -Pprod help:active-profiles
~~~

Với POM ví dụ và không có profile khác ảnh hưởng:

- Lệnh đầu dự kiến hiển thị profile **dev** (source: pom).
- Lệnh sau dự kiến hiển thị profile **prod** (source: pom).

Đầu ra thật có thể có thêm thông tin từ settings hoặc module khác; không nên sao chép cứng log làm điều kiện kiểm tra.

Kiểm tra giá trị property:

~~~bash
mvn help:evaluate -Dexpression=build.mode -q -DforceStdout
mvn -Pprod help:evaluate -Dexpression=build.mode -q -DforceStdout
~~~

Giá trị kỳ vọng **theo từng lệnh**:

~~~text
development
production
~~~

Sinh effective POM để xem cấu hình cuối:

~~~bash
mvn help:effective-pom -Doutput=effective-dev.xml
mvn -Pprod help:effective-pom -Doutput=effective-prod.xml
~~~

Đây là file **chẩn đoán được sinh ra**, không phải nguồn chính cần chỉnh sửa. Hãy tìm **build.mode**, resources filtering và plugin configuration; sau đó kiểm tra output thực tế trong **target/classes** hoặc JAR.

Nếu dùng Maven nhiều module, phải biết lệnh đang xét project/module nào, vì mỗi module có POM và profile container riêng.

## 8. Profile và quyền ưu tiên khi nhiều profile active

Profiles active sửa effective POM thông qua merge/override. Với **nhiều profiles active được khai báo trong cùng một POM**, profile khai báo **phía sau** có thể ưu tiên khi cùng ghi vào một trường đơn; danh sách hoặc plugin configurations có thể hợp nhất theo các quy tắc tương ứng.

Ví dụ minh họa:

~~~xml
<profiles>
    <profile>
        <id>first</id>
        <properties>
            <feature.level>basic</feature.level>
        </properties>
    </profile>
    <profile>
        <id>second</id>
        <properties>
            <feature.level>strict</feature.level>
        </properties>
    </profile>
</profiles>
~~~

Nếu cả first và second active trong cùng POM, **feature.level=strict** là giá trị từ profile khai báo sau trong ví dụ. **Không nên suy ra priority chỉ từ thứ tự nhập IDs trong -P**.

Nếu dev và prod là **hai biến thể loại trừ nhau**, hãy thiết kế command CI để chỉ chọn một. Các profile độc lập khác như quality hoặc docs nên có cấu hình không ghi đè nhầm property dành riêng cho môi trường.

Maven user properties từ **-Dkey=value**, settings profiles và các giá trị hiệu lực khác cũng có thể ảnh hưởng đến kết quả. Khi có xung đột, đối chiếu **help:active-profiles**, **help:effective-pom**, kết quả build thật và đúng phiên bản Maven.

## 9. Lưu ý inheritance và multi-module

**Parent POM** và **profile** là hai cơ chế khác nhau:

- POM con chỉ rõ parent bằng **<parent>** để nhận các phần cấu hình có thể kế thừa.
- Aggregator liệt kê **<modules>** để gom dự án trong reactor.
- Profile chọn biến thể cấu hình khi dựng project model.

**Định nghĩa profile không tự được kế thừa** vào POM con như một danh sách profiles. Maven xử lý profiles sớm; **chỉ hiệu ứng của những profile đã active ở parent** có thể đi vào cấu hình con thông qua cơ chế kế thừa.

Không được kết luận rằng vì parent có profile tên **integration**, mọi child đều có một profile integration riêng có thể tự kích hoạt theo điều kiện ngầm giống hệt. Activation theo JDK, property, OS hoặc file thuộc profile container thích hợp; hãy kiểm tra active profiles và effective POM của **đúng module**.

Nếu nhiều modules cần cùng Java release, compiler version hoặc dependency version, những giá trị **mặc định bắt buộc** thường nên đặt ở parent POM / pluginManagement / dependencyManagement, không cần tạo profile cho mỗi module nếu không có biến thể thực sự.

## 10. Cấu hình repository bằng settings profile

Đối với môi trường công ty cần repository nội bộ, có thể dùng settings.xml như sau (mẫu định hướng, không phải repository hoạt động):

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <profiles>
        <profile>
            <id>corporate-repo</id>
            <repositories>
                <repository>
                    <id>internal-releases</id>
                    <url>https://repository.example.invalid/maven/releases</url>
                </repository>
            </repositories>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>corporate-repo</activeProfile>
    </activeProfiles>
</settings>
~~~

**example.invalid** là domain mẫu, không thể dùng như repository thực tế. Hãy thay endpoint bằng địa chỉ được đơn vị sở hữu cung cấp và cấu hình credentials trong settings/secret manager theo policy. Ví dụ này chỉ nêu cơ chế, không bảo đảm toàn bộ repository/mirror policies đã được đáp ứng.

**Settings profile hỗ trợ subset hạn chế.** Không nên đặt một Java compiler plugin execution vào settings profile rồi coi như nó sẽ chạy. Cấu hình build/plugin phải được khai báo trong POM hoặc một cơ chế Maven được hỗ trợ phù hợp.

## 11. Bẫy activeByDefault trong POM nhiều profiles

Khi ban đầu chỉ có dev và prod, dev activeByDefault có vẻ đơn giản. Nhưng sau đó thêm **quality** rồi chạy:

~~~bash
mvn -Pquality package
~~~

Nếu quality thuộc **cùng POM** với dev, profile dev activeByDefault bị tắt. Property **build.mode** có thể không còn được cung cấp, trừ khi có nguồn mặc định khác. File resource đang dùng **${build.mode}** có thể không được lọc như mong muốn.

Một giải pháp tốt là đặt **fallback property ngoài profiles**:

~~~xml
<properties>
    <build.mode>development</build.mode>
</properties>
<profiles>
    <profile>
        <id>prod</id>
        <properties>
            <build.mode>production</build.mode>
        </properties>
    </profile>
</profiles>
~~~

Với cách này, development là giá trị chung; **-Pprod** mới ghi đè. Một cách khác là buộc pipeline **luôn** chọn chính xác một profile môi trường và kiểm tra property thiếu bằng plugin/rule thích hợp.

Cần thiết kế **bộ profiles hoàn chỉnh** thay vì một tập từng phần rời rạc. Profile quality độc lập không nên vô tình vô hiệu cấu hình môi trường bắt buộc.

## 12. Phân biệt build-time config và runtime config

Trong bài học, **build.mode** được filter vào JAR. Do đó dev và prod tạo **hai nội dung artifact khác nhau** mặc dù mã Java và tọa độ Maven giống nhau. Đây là khác biệt cần ghi nhận.

Nhiều hệ thống hiện đại muốn **build once, deploy many**:

- Maven tạo artifact đã kiểm thử, có checksum và metadata phát hành.
- Pipeline deploy cùng artifact đến staging/production.
- Application đọc URL/service credential, runtime toggles hoặc log configuration từ môi trường, secrets/config server hoặc deployment descriptor.
- Không cần rebuild JAR chỉ để đổi database URL hoặc token.

Profile vẫn có ích cho **đúng những biến thể build cần thiết**, như bật generator cho một artifact subtype hoặc chạy checks chuyên biệt. Nhưng không nên lạm dụng profile để nhúng dữ liệu nhạy cảm hay thay thế configuration management của môi trường chạy.

**Không đưa password/token/secret thật vào POM profile, resource filtering hoặc CI command line**; chúng có thể bị lưu trong Git, JAR, logs, artifact registry và build cache.

## 13. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Chạy **-Pprod** nhưng resource vẫn ghi dev | Profile không active, property bị override, output cũ | help:active-profiles, help:evaluate, clean package |
| Plugin không chạy dù thấy trong profile | Profile không active hoặc goal/execution không được bind | Effective POM và log plugin |
| Maven có profile trên máy A mà không có trên máy B | Profile nằm trong settings riêng hoặc parent khác | Xem settings, parent, active profiles |
| Resource còn placeholder | Filtering chưa bật, property thiếu hoặc file không nằm trong resource root | build/resources, target/classes |
| Binary resource bị hỏng | Filtering áp dụng cho file nhị phân | Filter text resource riêng, không filter ảnh/JAR |
| Profile quality làm dev mất tác dụng | dev activeByDefault bị profile khác kích hoạt trong cùng POM | Dùng fallback property hoặc profile môi trường tường minh |
| Artifact dev và prod lẫn nội dung | Đổi -P nhưng không clean, cached files | mvn clean package cho từng variant |
| Test bị skip không chủ đích | Profile ghi đè plugin/test configuration | Kiểm tra Surefire/Failsafe report và effective POM |
| CI build khác laptop | JDK/OS activation, settings, env properties khác | Cố định tool versions và log active profiles |
| Profile có tên prod nhưng không deploy | -P chỉ đổi build model | Chạy deploy pipeline/goal độc lập đúng quyền |
| Parent có profile nhưng child không có cùng definition | Profile definitions không được kế thừa như XML thường | Xem active parent effect, effective child model |
| Secret bị lưu trong JAR | Filtering từ property chứa credential | Dùng runtime secrets, không đóng gói secret |
| Cùng lúc bật dev và prod | Hai biến thể cạnh tranh | Chọn profile độc quyền, kiểm tra merge order |
| Profile trong settings khai báo plugin nhưng không áp dụng | settings profile không cho phép build/plugins tùy ý | Đưa plugin config vào POM |

Apache Maven khuyến nghị chú ý **clean** khi chuyển giữa các biến thể profile vì resources plugin và những tác vụ copy có thể dùng logic thời điểm sửa file; không nên để output của môi trường trước lọt vào artifact mới.

## 14. Quy trình đưa profile vào dự án thật

1. Xác định **cái gì thật sự khác nhau ở build time**, không nhầm với runtime values.
2. Đặt phần cấu hình chung ở POM nền hoặc parent; chỉ để khác biệt trong profiles.
3. Đặt profiles vào đúng nơi: POM cho build behavior, settings cho repository/machine-specific settings.
4. Đặt tên profile mô tả rõ ý nghĩa, không phụ thuộc vào thành viên cụ thể.
5. Chọn activation minh bạch: **-P** trong CI/release, dùng ngầm theo JDK/OS/file khi thật sự cần.
6. Tránh nhiều profiles cạnh tranh cùng key; đừng để quality vô tình tắt default của variant.
7. Đưa giới hạn versions, compiler release, plugin versions chung vào cấu hình xác định.
8. Dùng **help:active-profiles** và **help:effective-pom** để kiểm tra mô hình được chọn.
9. Dùng **mvn clean verify** hoặc phase phù hợp cho từng variant và kiểm tra test counts.
10. Kiểm tra file đầu ra trong **target/classes** và archive thật, không chỉ tin vào tên profile.
11. Ghi nhận artifact variant/checksum khi nội dung JAR phụ thuộc profile.
12. Tránh secrets và side effects không được kiểm soát.
13. Tài liệu hóa lệnh chuẩn cho developer/CI để build lặp lại được.
14. Khi cần một artifact chung để deploy nhiều nơi, ưu tiên cấu hình runtime hơn build profiles.

## 15. Bài tập củng cố

**Câu 1.** Một POM có dev activeByDefault và prod khai báo riêng. Khi chạy **mvn -Pprod package**, cả hai cùng active?

**Trả lời:** Không trong cơ chế default thông thường của cùng POM: profile dev activeByDefault bị tắt khi prod được kích hoạt.

**Câu 2.** Chạy **mvn -Pprod package** có tự deploy ứng dụng lên production server?

**Trả lời:** Không. -P lựa chọn biến thể build; deploy là công việc khác.

**Câu 3.** Một POM chỉ có property **build.mode** trong profile, Java code không đọc property và Maven không filter file. Chương trình có tự thay đổi kết quả không?

**Trả lời:** Không. Property phải được plugin hoặc resource consumer phù hợp sử dụng.

**Câu 4.** Ứng dụng dùng một JAR nhưng URL database khác giữa test và prod. Có bắt buộc build hai JAR qua Maven profiles?

**Trả lời:** Không. Thường nên truyền URL từ runtime configuration và sử dụng cùng artifact đã kiểm thử.

**Câu 5.** Profile được khai báo trong parent; child có tự nhận định nghĩa profile ấy?

**Trả lời:** Không. Maven không kế thừa profile definition như các POM elements thông thường; chỉ tác động của active profile ở parent có thể đi vào model child.

**Câu 6.** Tại sao build dev xong chạy prod mà không clean có thể sai?

**Trả lời:** Output/resources còn sót hoặc logic copy/filter không tái xử lý như mong đợi. Clean build rồi kiểm tra artifact.

**Câu 7.** Khi chọn profile cần kiểm tra bằng lệnh nào?

**Trả lời:** **mvn help:active-profiles** xác nhận profiles hoạt động, **mvn help:effective-pom** kiểm tra model, **mvn help:evaluate -Dexpression=...** kiểm tra property, còn output thật xác nhận behavior.

## Tài liệu tham khảo

- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Building For Different Environments](https://maven.apache.org/guides/mini/guide-building-for-different-environments.html)
- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
