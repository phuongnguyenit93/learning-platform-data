# Profile trong POM, settings và phạm vi tác động của Maven

## 1. Mục tiêu và bản chất của Maven profile

Một dự án Java thường có một `pom.xml` chung nhưng cần những cấu hình build khác nhau: chạy kiểm thử nhanh ở máy lập trình viên, kiểm thử đầy đủ trên CI, tải thư viện từ kho nội bộ, hoặc dùng một số tham số phù hợp hệ điều hành. Maven **build profile** cho phép nhóm các cấu hình có tên riêng và kích hoạt chúng theo lệnh hoặc điều kiện.

Profile là **cơ chế cấu hình tại thời điểm Maven dựng mô hình và chạy build**. Nó không phải một Java profile khi chương trình đã chạy, không tự tạo Spring profile, không tự khởi động database và không tự cấu hình plugin nếu chưa khai báo cấu hình hợp lệ. Khi active, profile đóng góp những thành phần được Maven cho phép vào mô hình hiệu lực.

Hai nơi định nghĩa quan trọng:

- **POM profile:** nằm trong `pom.xml`, được quản lý như một phần cấu hình dự án. Có thể thay đổi properties, dependencies, plugins và nhiều mục build được phép.
- **Settings profile:** nằm trong `settings.xml` cấp cài đặt hoặc cấp người dùng. Chủ yếu cung cấp properties, repositories và pluginRepositories theo môi trường.

Mục tiêu của bài này là hiểu **nơi khai báo**, **điều kiện kích hoạt**, **phạm vi ảnh hưởng**, **quy tắc ưu tiên** và **cách kiểm chứng** bằng Maven. Ta cũng sẽ xây một ví dụ Java 17 để quan sát hai loại profile hoạt động đồng thời.

## 2. Profile trong POM: cấu hình thuộc về dự án

Profile POM đặt dưới `<project><profiles>`. Một cấu trúc đơn giản:

```xml
<profiles>
    <profile>
        <id>qa</id>
        <properties>
            <demo.profile.mode>qa</demo.profile.mode>
        </properties>
    </profile>
</profiles>
```

Đây là **đoạn trích**, không phải một POM độc lập. Khi chạy `mvn -P qa verify` trong dự án chứa profile đó, Maven áp dụng giá trị `demo.profile.mode=qa` cho mô hình build của dự án.

POM profile có thể ảnh hưởng tới các thành phần được phép trong Maven model, chẳng hạn:

- `<properties>`: giá trị cho interpolation, compiler/test/plugin/resource;
- `<dependencies>`: các thư viện thực sự được thêm vào classpath trong phạm vi phù hợp;
- `<dependencyManagement>`: quản lý version và cấu hình dependency;
- `<build><plugins>` hoặc `<pluginManagement>`: mục tiêu, cấu hình và execution của plugin;
- `<build><resources>` / `<testResources>`: quy tắc xử lý resource;
- `<repositories>` và `<pluginRepositories>`: nơi tìm artifact/plugin;
- `<modules>`: tập module mà aggregator thu thập trong một số kịch bản build;
- một số phần tử hợp lệ khác như reporting/distributionManagement.

**Không phải mọi phần tử của `<project>` đều có thể đặt vào profile**. Ví dụ, không dùng `<artifactId>` trong profile để đổi tùy tiện GAV của project. Không thể đặt những mục `<build>` ngoài tập con được Maven hỗ trợ vào profile rồi mong POM vẫn hợp lệ. Maven có thể báo `Malformed POM` nếu cấu trúc sai.

**Nên dùng POM profile khi sự khác nhau là quy tắc build của dự án có thể chia sẻ và review bằng Git**, chẳng hạn bộ integration test, plugin kiểm tra chất lượng, dependency dành cho tính năng thử nghiệm. Những thứ cần tái lập ổn định trên mọi máy nên đặt ngoài profile hoặc đặt thành mặc định rõ ràng trong POM/parent.

## 3. Profile trong settings: cấu hình theo cài đặt hoặc người dùng

### 3.1. Hai vị trí `settings.xml` trong Maven 3

```text
Global settings: ${maven.home}/conf/settings.xml
User settings:   ${user.home}/.m2/settings.xml
```

**Global settings** là file của Maven distribution đang chạy; dùng Maven Wrapper hay Maven cài ở vị trí khác có thể dẫn đến file global khác. **User settings** thuộc tài khoản hệ điều hành mà process Maven đang chạy; trong CI, đó thường là tài khoản runner.

Nếu cả hai tồn tại, Maven **hợp nhất** chúng, với **user settings có ưu tiên khi xung đột**. Nội dung chỉ có ở global vẫn có thể tiếp tục có hiệu lực. File user settings không bắt buộc phải tồn tại.

Một settings profile điển hình:

```xml
<profiles>
    <profile>
        <id>company-network</id>
        <properties>
            <demo.profile.region>office</demo.profile.region>
        </properties>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>company-network</activeProfile>
</activeProfiles>
```

Đây là **đoạn trích bên trong root `<settings>`**, không phải toàn bộ file. `<activeProfiles>` là danh sách ID cần active theo settings. Một profile settings có thể active cả khi không có POM profile cùng tên.

### 3.2. Chính xác settings profile có thể chứa gì?

Settings profile chỉ có tập con so với profile POM: **`<activation>`, `<properties>`, `<repositories>`, `<pluginRepositories>`**, cùng định danh `<id>`. Settings profile **không trực tiếp được khai báo** `<build>`, `<dependencies>`, `<dependencyManagement>` hay `<plugins>`.

Lưu ý phân biệt **profile settings** với **toàn bộ settings file**: các mục như `<servers>` (credentials), `<mirrors>` và `<proxies>` được định nghĩa ở **cấp root của settings**, không nằm bên trong một `<profile>`. Một settings profile có thể bổ sung repository, nhưng không được nhét mật khẩu vào một cấu trúc POM hoặc Java resource.

Properties trong settings profile **có thể ảnh hưởng gián tiếp tới build** nếu POM/plugin sử dụng chúng làm biến interpolation. Ví dụ POM cấu hình `<filtering>true</filtering>` có thể đọc property môi trường từ settings profile rồi đưa vào một file `.properties`. Tuy nhiên, settings profile vẫn không thể gắn plugin execution trực tiếp.

### 3.3. So sánh phạm vi hai loại profile

| Thuộc tính | Profile POM | Profile settings |
| --- | --- | --- |
| Nơi lưu | `pom.xml` dự án/parent | Global hoặc user `settings.xml` |
| Thường có trên Git? | Có khi POM được commit | Không nên commit settings cá nhân |
| Khai báo properties | Có | Có |
| Khai báo repository/pluginRepository | Có | Có |
| Bổ sung dependencies | Có | Không trực tiếp |
| Điều chỉnh plugins/build | Có, theo các phần tử hợp lệ | Không trực tiếp |
| Kích hoạt `-P` | Có | Có |
| Điều kiện JDK/OS/property/file | Có | Có |
| Phạm vi sử dụng | Dự án / model kế thừa phù hợp | Maven session dùng settings đó |
| Lựa chọn nên dùng | Hành vi build của project | Đặc thù mạng, môi trường, người dùng |

**Nguyên tắc:** thông tin thuộc cách xây dựng sản phẩm nên mô tả trong POM, còn thông tin đặc thù một máy hoặc môi trường nên nằm trong settings. Điều này giúp source portable và hạn chế rò rỉ credentials.

## 4. Cách kích hoạt profile

### 4.1. Bật tường minh bằng `-P`

`-P` nhận ID hoặc danh sách ID ngăn bởi dấu phẩy:

```bash
mvn -P qa clean verify
mvn -P qa,extra-checks verify
```

Lệnh đầu bật profile `qa` cho lần Maven hiện tại; lệnh sau yêu cầu cả hai. `-P` không tạo profile mới, không sửa POM hoặc settings và không có nghĩa profile sẽ active ở các lần gọi sau nếu bỏ cờ.

Có thể tắt một profile bằng cú pháp phủ định, chẳng hạn:

```bash
mvn -P=-local-default verify
```

Dạng `-P=-id` tránh những vấn đề về shell khi tham số bắt đầu bằng `!` hoặc `-`. Trong Maven 4, ID profile được chỉ định mà không tồn tại có thể khiến build bị từ chối; ký hiệu `?` cho phép đánh dấu một profile là tùy chọn trong cú pháp Maven 4. Hãy xem hướng dẫn của **phiên bản Maven đang chạy** thay vì dựa vào việc profile sai ID bị bỏ qua.

### 4.2. Bật tự động bằng `<activation>`

Một profile POM có thể active dựa trên property do CLI cung cấp:

```xml
<profile>
    <id>experimental</id>
    <activation>
        <property>
            <name>enableExperimental</name>
            <value>true</value>
        </property>
    </activation>
    <properties>
        <demo.feature.experimental>true</demo.feature.experimental>
    </properties>
</profile>
```

Đây là **đoạn nằm bên trong `<profiles>`**. Lệnh:

```bash
mvn -DenableExperimental=true verify
```

kích hoạt `experimental` vì đúng điều kiện `<activation><property>`. **`-D` tự nó chỉ cung cấp property**; nếu không có activation phù hợp, truyền `-Dfoo=bar` không tự bật một profile tên `foo`. Không nên nhầm property khai báo trong POM với property sẵn có để kích hoạt profile trong cùng quá trình model building.

Các kích hoạt tự động khác:

- **JDK:** match version hoặc khoảng phiên bản JDK đang chạy Maven;
- **OS:** match name/family/architecture/version;
- **file:** file tồn tại (`exists`) hoặc thiếu (`missing`);
- **activeByDefault:** active khi không có profile khác khiến mặc định bị tắt;
- **packaging:** trong Maven 3.9+ có thể match packaging qua activation property khi phù hợp.

Điều kiện activation sử dụng thông tin của môi trường thực; nó không phải feature flag tùy ý do Maven suy đoán từ code. Khi có nhiều **kiểu** điều kiện trong cùng một activation, các điều kiện phải đồng thời thỏa. Không nên gắn nhiều điều kiện cùng kiểu rồi kỳ vọng OR.

### 4.3. `activeByDefault` không đồng nghĩa luôn luôn bật

Một POM profile có thể có:

```xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
```

Nếu một profile khác trong cùng POM được kích hoạt theo cơ chế thích hợp, profile activeByDefault có thể tự tắt. Do đó, không đặt các cấu hình cực kỳ quan trọng **chỉ** trong profile activeByDefault mà không kiểm chứng hiệu lực trong các mode khác. Nếu yêu cầu dùng cho mọi build, cân nhắc đưa ra POM/parent ở cấp cơ sở.

### 4.4. `<activeProfiles>` trong settings

Ở root `<settings>`:

```xml
<activeProfiles>
    <activeProfile>company-network</activeProfile>
</activeProfiles>
```

Danh sách này kích hoạt profile ID được khai báo từ settings và/hoặc được Maven phân giải theo model áp dụng. Hệ quả là mọi dự án được Maven gọi với settings đó có thể nhận repository/properties của profile active, không cần POM của mỗi dự án chép lại profile settings.

Có thể dùng `-P qa` để bật POM profile **đồng thời** với một settings profile active khác. Profile từ hai nguồn không có cơ chế “mỗi lần chỉ dùng một nguồn”.

### 4.5. Chọn settings file khác bằng CLI

```bash
mvn -s my-user-settings.xml help:active-profiles
mvn -gs my-global-settings.xml help:active-profiles
```

- `-s` / `--settings` chọn **user settings** thay đường dẫn mặc định.
- `-gs` / `--global-settings` chọn **global settings** thay đường dẫn mặc định.
- Chỉ định file ở một cấp không có nghĩa Maven tự bỏ luôn settings của cấp còn lại.
- Trong CI và IDE, hãy kiểm tra file/settings và Maven distribution thực sự được chọn.

## 5. Phạm vi kế thừa và cách xác định precedence

### 5.1. Định nghĩa profile không tự kế thừa qua parent

Đây là điểm rất dễ nhầm: **profile definition không tự được child POM kế thừa**. Maven xử lý profile khá sớm khi dựng model. **Tác động của parent profile đã active**—ví dụ cấu hình plugin hoặc property được đưa vào parent effective POM—có thể được kế thừa theo quy tắc bình thường. Nhưng child không nhận một profile definition “mới” để tự xử lý activation khác chỉ vì có quan hệ `<parent>`.

Hình dung:

```text
parent/pom.xml:
  profiles:
    id=quality       (chỉ ảnh hưởng khi active trong parent model)
    khi active: cấu hình plugin hoặc property

child/pom.xml:
  <parent>...parent...</parent>
  không tự sở hữu profile id=quality
```

Cùng ID profile trong parent và child cũng không đồng nghĩa một điều kiện activation tại child sẽ tự kích hoạt profile ở parent. Kích hoạt ngầm gắn với phạm vi khai báo tương ứng, không phải cơ chế broadcast toàn reactor.

### 5.2. Profile settings gắn với môi trường Maven, không gắn parent

Một profile trong user/global settings có thể ảnh hưởng tới mọi project trong lần build dùng settings đó. Nó không được truyền qua `<parent>`. Khi một thành viên khác clone Git, **POM profile đi cùng dự án**, nhưng user settings profile có thể vắng mặt hoàn toàn.

Vì vậy, khi build không tái lập trên CI, câu hỏi đầu tiên không phải “Maven có hỗ trợ profile không?” mà là **profile nào được định nghĩa ở nguồn nào, nó có active trên máy này không, và kết quả effective POM khác ra sao?**

### 5.3. Quy tắc ưu tiên cần biết

1. **POM cơ sở + POM profile active:** các phần tử hợp lệ trong profile có thể override hoặc mở rộng phần tử cơ sở, tùy model merge.
2. **Nhiều profile active cùng POM hoặc cùng file external:** với thuộc tính xung đột, profile **được định nghĩa sau** có ưu tiên hơn profile được định nghĩa trước; không mặc định dựa theo thứ tự ID trong chuỗi `-P a,b`.
3. **Global settings + user settings:** khi nội dung trùng nhau, user settings là bên ưu tiên trong phép hợp nhất hai settings.
4. **Settings profile và POM profile trùng ID:** tài liệu Settings Reference ghi nhận settings profile đang active có thể override giá trị tương ứng của profile POM cùng ID. Nên tránh trùng ID giữa hai nguồn trừ khi đã chủ động thiết kế và kiểm chứng.
5. **CLI `-D` và nguồn property khác:** những property này cũng ảnh hưởng interpolation và build. Không nên xây “một thứ tự ưu tiên duy nhất” cho mọi loại phần tử (property, repository, plugin, dependency) nếu chưa xét loại merge và phiên bản Maven.

Quan trọng: **precedence không phải activation**. Một profile không active thì không đóng góp các giá trị của nó, dù ID hoặc vị trí khai báo có vẻ “ưu tiên”. Hãy kiểm tra tuần tự: **profile tồn tại → active → cho phép sửa phần tử đó → hiệu ứng đã merge thế nào**.

### 5.4. `dependencyManagement` khác `dependencies` ngay cả trong profile

POM profile có thể đưa thư viện vào `<dependencies>` hoặc chỉ khai báo version trong `<dependencyManagement>`. Phần dependencyManagement **không tự thêm một thư viện vào classpath**. Ví dụ đoạn trích:

```xml
<profile>
    <id>managed-versions</id>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.17.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</profile>
```

Đoạn này **không phải POM độc lập**. Nếu profile active, dependency management có thể dùng khi một dependency thực sự được khai báo. **Không đặt** đoạn này trong settings profile vì settings không hỗ trợ dependencyManagement.

## 6. Ví dụ Java 17 có thể chạy: profile POM và settings cùng tác động

Ta tạo một Maven project **không dùng dependency ngoài** để đơn giản hóa. POM profile điều khiển property `demo.profile.mode`; settings profile cung cấp property `demo.profile.region`. Maven Resources Plugin filter file `app.properties` khi build. Java 17 đọc file đã lọc để hiển thị kết quả.

Đây là ví dụ minh họa **build-time configuration**, không phải Java API truy vấn profile Maven. Nó cũng không nhúng secret.

### 6.1. Cấu trúc file

```text
profile-lab/
├── pom.xml
├── settings-demo.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/profilelab/App.java
        └── resources/
            └── app.properties
```

Cần Maven 3.9.x, JDK 17+ và khả năng tải các plugin lần đầu. Mở terminal ở thư mục `profile-lab`.

### 6.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>profile-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.profile.mode>base</demo.profile.mode>
    </properties>

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
                <version>3.13.0</version>
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
            <id>qa</id>
            <properties>
                <demo.profile.mode>qa</demo.profile.mode>
            </properties>
        </profile>
        <profile>
            <id>release-check</id>
            <properties>
                <demo.profile.mode>release-check</demo.profile.mode>
            </properties>
        </profile>
    </profiles>
</project>
```

POM cơ sở khai báo `demo.profile.mode=base`. Hai profile theo project cho phép thay giá trị thành `qa` hoặc `release-check`. Ví dụ **cố tình chỉ bật một mode mỗi lần**; bật cả hai thì cần xét quy tắc profile order.

`<filtering>true</filtering>` yêu cầu Maven Resources Plugin thay placeholder trong file resource text. Không bật resource filtering bừa cho ảnh/JAR hoặc tệp nhị phân vì có thể làm hỏng dữ liệu.

### 6.3. Tệp `settings-demo.xml`

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <profiles>
        <profile>
            <id>lab-machine</id>
            <properties>
                <demo.profile.region>lab</demo.profile.region>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>lab-machine</activeProfile>
    </activeProfiles>
</settings>
```

Tệp này mô phỏng **user settings** khi dùng cờ `-s settings-demo.xml`; không cần sửa settings thật trong `~/.m2`. Settings profile không chứa plugin/dependency, chỉ cung cấp property môi trường. Global settings Maven thật vẫn có thể góp thêm cấu hình; nếu có mirror/proxy của tổ chức, kết quả tải plugin phụ thuộc chúng.

### 6.4. Tệp `src/main/resources/app.properties`

```properties
demo.profile.mode=${demo.profile.mode}
demo.profile.region=${demo.profile.region}
```

Đây là resource **đầu vào**. Sau khi Maven filter thành công với profile `qa` và settings demo, file `target/classes/app.properties` có nội dung:

```properties
demo.profile.mode=qa
demo.profile.region=lab
```

Khi chỉ chạy Java mà không build lại, chương trình vẫn đọc resource được tạo từ lần build trước; đổi `-P` chỉ có tác dụng khi chạy Maven để tạo lại đầu ra.

### 6.5. Tệp `src/main/java/com/example/profilelab/App.java`

```java
package com.example.profilelab;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input = App.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            properties.load(input);
        }

        System.out.println("mode=" + properties.getProperty("demo.profile.mode"));
        System.out.println("region=" + properties.getProperty("demo.profile.region"));
    }
}
```

Chương trình Java 17 này chỉ đọc resource trên classpath qua `getResourceAsStream`. Nó không tự biết tên Maven profile nào đã active; property text đã được Maven chọn và ghi xuống file ở **thời điểm build**.

### 6.6. Lần 1: settings profile active nhưng POM mode ở mặc định

```bash
mvn -version
mvn -s settings-demo.xml clean package
java -cp target/classes com.example.profilelab.App
```

Kết quả **chính xác của lệnh Java cuối**:

```text
mode=base
region=lab
```

Giải thích: POM không bật `qa` hoặc `release-check`, nên `demo.profile.mode=base` từ POM cơ sở được dùng. Settings profile `lab-machine` active qua `<activeProfiles>` và cung cấp `demo.profile.region=lab`.

### 6.7. Lần 2: đồng thời bật POM profile `qa`

```bash
mvn -s settings-demo.xml -P qa clean package
java -cp target/classes com.example.profilelab.App
```

Stdout của Java:

```text
mode=qa
region=lab
```

`mode=qa` đến từ POM profile, còn `region=lab` đến từ settings profile. Việc bật POM profile qua `-P` không tự hủy settings profile đã active.

### 6.8. Lần 3: chọn mode khác

```bash
mvn -s settings-demo.xml -P release-check clean package
java -cp target/classes com.example.profilelab.App
```

Stdout:

```text
mode=release-check
region=lab
```

**Điểm đáng lưu ý khi phát hành:** cùng `groupId:artifactId:version`, bạn có thể tạo JAR/resource khác nhau nếu build với profile khác. Để tái lập artifact, CI phải kiểm soát profile đang active, plugin versions và môi trường; đừng công bố nhiều binary khác nội dung với cùng release coordinate mà không có quy trình quản trị rõ ràng.

### 6.9. Kiểm tra profile thực sự hiệu lực

```bash
mvn -s settings-demo.xml -P qa help:active-profiles
mvn -s settings-demo.xml -P qa help:effective-pom
mvn -s settings-demo.xml help:effective-settings -DshowPasswords=false
```

- **`help:active-profiles`:** hiển thị những profile active và nguồn (POM/settings) trong lần build; ở ví dụ này mong thấy `qa` và `lab-machine`.
- **`help:effective-pom`:** cho biết dự án thực sự có properties, dependencies/plugins và các thành phần POM thế nào sau merge. Hãy tìm `demo.profile.mode` và `maven-resources-plugin`.
- **`help:effective-settings`:** cho biết settings global/user được hợp nhất và cấu hình môi trường; không thay thế effective POM.
- **`-DshowPasswords=false`:** tránh yêu cầu hiện mật khẩu trong kết quả settings. Tuy vậy log vẫn có thể lộ hostname, repository ID, home path hoặc thông tin hạ tầng.

Nếu chưa tải được Maven Help Plugin, các goal có thể yêu cầu kết nối repository phù hợp. Một cách khác là gọi plugin đầy đủ, ghim version: `org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles`.

## 7. Chọn profile theo tình huống thực tế

### 7.1. Thay đổi kiểm thử hoặc build plugin → POM profile

Ví dụ một project chỉ chạy integration test trên CI. Có thể tạo POM profile `integration-check` gắn Maven Failsafe Plugin vào lifecycle và chạy:

```bash
mvn -P integration-check clean verify
```

Điều này **chỉ có tác dụng nếu POM thực sự cấu hình plugin và test**. `-P` không tự sinh test hoặc dựng database. Không đặt `<build><plugins>` trong settings profile để thử đạt tác dụng tương tự: cấu trúc settings không cho phép.

### 7.2. Repository môi trường công ty → settings profile

Một settings profile có thể chứa repository nội bộ, ví dụ **đoạn XML minh họa không chạy được** vì URL cố tình là `example.invalid`:

```xml
<profile>
    <id>company-network</id>
    <repositories>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.invalid/releases</url>
        </repository>
    </repositories>
</profile>
```

Trong thực tế, phải dùng URL chính thức, kiểm tra mirror/repository policy và credentials. `<servers>` chứa thông tin đăng nhập là **mục root của settings**, không phải phần tử trong profile. Không đưa mật khẩu vào POM hoặc filtered resource trong JAR.

### 7.3. Cấu hình phụ thuộc OS/JDK

POM profile có thể active dựa trên JDK/OS để cấu hình native build tools hoặc compiler phù hợp. Nhưng build portability có thể bị ảnh hưởng: hai developer cùng source nhưng khác môi trường sẽ có hiệu ứng profile khác. Với sản phẩm yêu cầu JDK cố định, có thể phối hợp Maven Toolchains/Enforcer và CI image chuẩn hóa để kiểm soát.

### 7.4. Multi-module và parent POM

Parent POM có thể chứa profile dùng cho nhiều module; tuy nhiên cần hiểu **tác động được kế thừa chứ profile definition không tự kế thừa**. Nếu aggregator thay đổi `<modules>` theo profile, thứ tự reactor và dependency graph vẫn quan trọng. Dùng `-pl`/`-am` phù hợp khi cần chọn module; không coi việc bật profile là cách giải quyết vòng dependency.

## 8. Lỗi phổ biến và quy trình chẩn đoán

| Triệu chứng | Hướng điều tra |
| --- | --- |
| `-P qa` không đổi giá trị | Kiểm tra profile ID, active-profiles, effective-pom, profile khác override hay chưa build lại resource |
| Settings profile có repository nhưng không tải được dependency | Kiểm tra activeProfiles, URL thật, mirror/mirrorOf, releases/snapshots, proxy, quyền |
| Đặt `<dependencies>` trong settings profile rồi báo lỗi | Cấu hình đó thuộc POM profile; settings chỉ có properties/repositories/pluginRepositories |
| Profile `activeByDefault` biến mất khi bật profile khác | Đây là hành vi có thể xảy ra trong cùng POM; xem active-profiles |
| `-Dflag=true` nhưng profile không active | Cần activation property đúng hoặc dùng `-P` trực tiếp |
| Parent có profile nhưng child không thấy profile ID | Profile definition không tự kế thừa; kiểm tra tác động đã active trong effective parent POM |
| Hai profile cùng active tranh chấp property | Xem thứ tự định nghĩa và model merge; không tin thứ tự `-P` là luật chung |
| Java vẫn in mode của lần build trước | Chạy `clean package` với đúng profile, kiểm tra `target/classes/app.properties` |
| CI và máy developer dùng cùng POM nhưng kết quả khác | So sánh Maven version, user/global settings, profile activation và môi trường |
| Maven 4 từ chối profile ID không tìm thấy | Kiểm tra ID hoặc cú pháp optional của Maven 4 |
| `help:effective-settings` có dữ liệu nhạy cảm | Không chia sẻ output thô; lọc ID/URL/path và không hiện credentials |

Quy trình chẩn đoán gọn:

1. Chạy `mvn -version` (hoặc Maven Wrapper) để xác định phiên bản Maven/JDK.
2. Đọc đúng POM/settings đang được dùng, kể cả tham số `-s`/`-gs` từ terminal/IDE/CI.
3. Xem `mvn help:active-profiles` với **cùng tùy chọn** đã gây ra hành vi lạ.
4. Xem `help:effective-pom` để xác định giá trị build thực tế; xem `help:effective-settings` cho repository/profile settings.
5. Kiểm tra output sau `clean package`, báo cáo test và resource đã filter.
6. Nếu cần debug sâu, dùng `-e` hoặc `-X` có chọn lọc; xử lý credentials/log trước khi chia sẻ.

`mvn -U` chỉ yêu cầu kiểm tra lại snapshot/missing release trong quá trình phân giải, **không tự bật, sửa hoặc ưu tiên một profile**. Đừng dùng cờ này để chữa mọi lỗi cấu hình profile.

## 9. Bài tập áp dụng

**Bài 1:** Chạy ba lệnh ở mục 6, dự đoán mode và region trước khi chạy `java`. Giải thích mỗi giá trị đến từ file nào.

**Bài 2:** Cần bổ sung một plugin kiểm thử khi bật CI. Nên dùng profile ở đâu? Đáp án: **POM profile**, vì settings profile không hỗ trợ `<build><plugins>`.

**Bài 3:** Cần chỉ định repository nội bộ khi làm trong mạng công ty. Nên dùng profile ở đâu? Thường **settings profile**, với URL/credentials theo policy, vì đây là thông tin môi trường.

**Bài 4:** Profile POM `activeByDefault` đang active, sau đó bạn bật profile `qa` cùng POM. Vì sao profile mặc định có thể tắt? Vì kích hoạt profile khác có thể vô hiệu chế độ activeByDefault.

**Bài 5:** Parent có profile `quality`, child có parent trỏ đúng POM ấy nhưng không định nghĩa profile `quality`. Child có tự nhận profile để kích hoạt lại không? **Không**; chỉ có thể kế thừa những tác động của parent profile đã active.

**Bài 6:** Máy A build được và máy B báo thiếu artifact dù source giống nhau. Hãy so sánh user/global settings, `help:active-profiles`, mirror, repository, Maven version và quyền trước khi sửa dependency tọa độ.

**Kết luận:** POM profile mô tả **cách xây dựng dự án**, settings profile cung cấp **thông tin môi trường cho Maven session**. Hiểu rõ nơi khai báo và activation/precedence sẽ giúp bạn xây build dễ đọc, tái lập và giảm khác biệt giữa máy developer với CI.

### Tài liệu chính thức

- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
