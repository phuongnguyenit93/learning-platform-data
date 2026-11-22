# Giới hạn nội dung profile khi khai báo trong settings.xml của Maven

## 1. Bản chất của profile trong settings

Maven dùng **profile** để áp dụng một tập cấu hình khi đáp ứng điều kiện hoặc khi người dùng chủ động kích hoạt. Tuy nhiên, **profile đặt trong `settings.xml` không có đầy đủ khả năng của profile đặt trong `pom.xml`**. Đây là một ranh giới thiết kế: `settings.xml` mô tả môi trường thực thi Maven (tài khoản, mạng, repository, thuộc tính theo máy), còn POM mô tả dự án và cách xây dựng nó.

**Quy tắc cần nhớ:** một profile bên trong `settings.xml` chỉ có những thành phần chính **`id`, `activation`, `properties`, `repositories` và `pluginRepositories`**. Bốn khối nội dung được hỗ trợ là `activation`, `properties`, `repositories`, `pluginRepositories`; `id` dùng để định danh profile.

Không thể đặt nguyên cấu hình plugin build, dependencies hay danh sách module vào một settings profile rồi kỳ vọng Maven xử lý như POM profile. Ngược lại, việc đưa property vào settings profile có thể **ảnh hưởng gián tiếp** đến cấu hình build nếu POM/plugin chủ động tham chiếu property đó.

Ví dụ kiến trúc:

```text
                    project/pom.xml
                           |
       project model: dependencies, plugins, build, modules
                           |
                           +------> Maven build
                           |
~/.m2/settings.xml         |
  profiles                 |
    - activation ----------+  bật profile theo điều kiện
    - properties ----------+  cung cấp thuộc tính cho model/filter
    - repositories --------+  tìm dependencies
    - pluginRepositories --+  tìm Maven plugins
  mirrors / servers / proxies (mục khác ở cấp settings)
```

Bài này giải thích cả **phạm vi XML hợp lệ**, **phạm vi tác động thực tế**, **cách kích hoạt**, **các giới hạn của property interpolation** và **cách phân chia cấu hình giữa settings và POM**.

## 2. Bảng so sánh settings profile và POM profile

| Cấu hình / nhu cầu | Profile trong `settings.xml` | Profile trong `pom.xml` |
| --- | --- | --- |
| `<id>` | Có | Có |
| `<activation>` | Có | Có |
| `<properties>` | Có | Có |
| `<repositories>` | Có | Có |
| `<pluginRepositories>` | Có | Có |
| `<dependencies>` | **Không** | Có |
| `<dependencyManagement>` | **Không** | Có |
| `<build>` | **Không** | Có |
| `<plugins>` hoặc `<pluginManagement>` bên trong build | **Không** | Có |
| `<modules>` | **Không** | Có trong profile của POM khi phù hợp |
| `<reporting>` | **Không** | Có |
| Đổi `finalName`, source directory, goal binding trực tiếp | **Không** | Có qua cấu hình build phù hợp |
| Khai báo nơi tải dependencies/plugins | Có | Có |
| Truyền giá trị cho một plugin đã được POM cấu hình bằng property | Có, **gián tiếp** qua `properties` | Có |
| Phụ thuộc vào tệp riêng trên máy người chạy | Có | Hạn chế, vì làm giảm tính tái lập |

Một điểm hay nhầm: `<pluginRepositories>` trong settings profile **chỉ khai báo nơi tìm plugin Maven**; nó **không phải** `<build><plugins>` để khai báo phiên bản, tham số hoặc execution của plugin.

Cũng không có nghĩa mọi thứ bị cấm ở **bên trong profile** đều bị cấm ở **toàn bộ settings**. Ví dụ `<servers>`, `<mirrors>`, `<proxies>`, `<localRepository>` và `<activeProfiles>` là những thành phần hợp lệ ở **cấp trực tiếp dưới `<settings>`**, không phải phần tử con của `<profile>`.

## 3. Cấu trúc settings.xml hợp lệ

Maven dùng một tệp global settings, thường ở `${maven.home}/conf/settings.xml`, và một tệp user settings, thường ở `${user.home}/.m2/settings.xml`. Khi cả hai tồn tại, Maven hợp nhất chúng; user settings được ưu tiên đối với các cấu hình tương ứng. Truyền `-s /duong-dan/settings-lab.xml` để chọn một **user settings khác** cho lần chạy, hoặc `-gs` nếu cần thay global settings.

Một tệp settings độc lập, có thể dùng cho ví dụ trong bài:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <profiles>
        <profile>
            <id>course-env</id>
            <properties>
                <course.greeting>Chào từ settings</course.greeting>
            </properties>
        </profile>
    </profiles>

    <activeProfiles>
        <activeProfile>course-env</activeProfile>
    </activeProfiles>
</settings>
```

Lưu ví dụ trên ở `~/.m2/settings-lab.xml` (hoặc vị trí riêng có quyền đọc phù hợp), **không sửa hoặc ghi đè settings thật của máy nếu đang dùng cho công việc khác**.

Cấu trúc trong ví dụ:

- `<settings>` là phần tử gốc của settings XML.
- `<profiles>` là danh sách các profile môi trường.
- `<profile><id>course-env</id>...` định nghĩa một profile có tên.
- `<properties>` cung cấp property `course.greeting` khi profile hoạt động.
- `<activeProfiles>` nằm ở **cấp settings**, không nằm trong profile; nó yêu cầu kích hoạt profile `course-env`.

Không có `<repositories>` hoặc `<pluginRepositories>` vẫn hợp lệ; đây là các phần **tùy chọn**, không bắt buộc khai báo hết bốn khối. Khi không cần kho tùy chỉnh, Maven tiếp tục sử dụng repository mặc định và các cấu hình hiện hành.

**Đừng copy một profile nguyên khối từ POM sang settings.** Cấu trúc hợp lệ trong một tài liệu XML không đồng nghĩa hợp lệ trong tài liệu XML khác, dù cả hai đều có tên phần tử `profile`.

## 4. Bốn khối nội dung được phép

### 4.1. activation: khi nào profile có hiệu lực?

`<activation>` mô tả điều kiện kích hoạt profile. Tùy phiên bản Maven, các điều kiện phổ biến gồm JDK, hệ điều hành, property hoặc sự tồn tại của tệp.

Đây là **đoạn nội dung minh họa bên trong `<profile>`**, không phải toàn bộ tệp settings:

```xml
<id>env-demo</id>
<activation>
    <property>
        <name>course.mode</name>
        <value>lab</value>
    </property>
</activation>
<properties>
    <course.greeting>Chào từ chế độ lab</course.greeting>
</properties>
```

Khi profile chứa đoạn trên, có thể chạy:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" "-Dcourse.mode=lab" help:active-profiles
```

Cờ `-Dcourse.mode=lab` đóng vai trò **điều kiện kích hoạt profile**, khác với `-Dcourse.greeting=...` vốn đặt property thực tế cho Maven. Để lệnh thực hành có hiệu lực, phải lưu cấu hình `env-demo` ở tệp settings và dùng đúng ID. Nếu giữ cấu hình `course-env` ở mục 3, profile đó được bật qua `<activeProfiles>` chứ không cần điều kiện này.

Ngoài kích hoạt tự động, có thể chọn profile bằng `-Pcourse-env` hoặc liệt kê tên trong `<activeProfiles>` ở settings. Việc kích hoạt bằng `-P` là lựa chọn **theo lần chạy**; liệt kê trong `<activeProfiles>` áp dụng thường xuyên khi settings đó được dùng.

**Lưu ý về tác động:** điều kiện kích hoạt không mở rộng những phần tử XML được phép trong settings profile. Một profile đã bật vẫn không được chứa `<build>` hoặc `<dependencies>`.

### 4.2. properties: đưa giá trị môi trường cho mô hình

`<properties>` là danh sách property có tên do bạn định nghĩa, ví dụ:

```xml
<properties>
    <course.greeting>Chào từ settings</course.greeting>
    <course.channel>local</course.channel>
</properties>
```

Đây cũng là **đoạn con của profile**, không phải tệp settings hoàn chỉnh.

Khi profile hoạt động, các property có thể được tham chiếu tại vị trí POM/plugin/resource có hỗ trợ biểu thức `${course.greeting}` hoặc placeholder filtering tương ứng. Nhưng Maven **không tự tạo hành vi** cho property `course.greeting`. Bạn phải có POM/plugin/code dùng giá trị ấy.

Hai giới hạn quan trọng:

1. Property của settings profile có thể tham gia nội suy POM, nhưng **không dùng các property vừa khai báo trong settings profile để nội suy chính tệp settings.xml**. Ví dụ, không nên trông đợi `<localRepository>${course.repo}</localRepository>` nhận giá trị từ `<properties><course.repo>...</course.repo></properties>` của profile.
2. Những trường POM cố định và không tham chiếu property, như `<artifactId>library</artifactId>` hoặc một giá trị `<version>1.0.0</version>` viết cứng, không tự đổi chỉ vì settings khai báo property cùng tên.

Có thể dùng các **system properties** như `${user.home}` và **biến môi trường** như `${env.HOME}` cho nội suy phù hợp trong settings. Tuy nhiên, không nhầm những nguồn đó với `<properties>` do profile trong cùng settings định nghĩa.

### 4.3. repositories: nơi tải dependencies

Trong settings profile, `<repositories>` mô tả remote repositories mà Maven có thể sử dụng để phân giải dependencies. Cú pháp minh họa:

```xml
<repositories>
    <repository>
        <id>team-dependencies</id>
        <url>https://repo.example.org/repository/maven-public/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
```

Đây là đoạn con của `<profile>`, và URL `repo.example.org` **chỉ là ví dụ**, không phải địa chỉ thực để thử tải artifact. Cần thay bằng repository được cấp quyền truy cập, hoặc bỏ hẳn mục này nếu không cần.

Cấu hình `releases` và `snapshots` cho biết loại artifact được phép phân giải từ repository ấy. Dù profile chứa repository, Maven vẫn có thể áp dụng `mirror` từ settings và các quy tắc repository hiệu lực khác.

**Lưu ý chiều dữ liệu:** `<repositories>` là nơi **lấy dependencies**, không phải đích mặc định của `mvn deploy`. Đích publish của dự án thường được khai báo trong `<distributionManagement>` của POM hoặc cấu hình Deploy Plugin thích hợp. Settings profile không cho phép `<distributionManagement>`.

### 4.4. pluginRepositories: nơi tải Maven plugins

`<pluginRepositories>` mô tả remote repository chứa plugin Maven khi cần phân giải plugin:

```xml
<pluginRepositories>
    <pluginRepository>
        <id>team-build-plugins</id>
        <url>https://repo.example.org/repository/maven-plugins/</url>
    </pluginRepository>
</pluginRepositories>
```

Cũng là ví dụ URL giả, không dùng để thực hành trực tiếp. Nó không bật một plugin, không thêm execution và không thay phiên bản plugin cho dự án. Để cấu hình `maven-compiler-plugin`, `maven-surefire-plugin` hoặc một goal, hãy dùng `<build><plugins>` ở POM hoặc profile trong POM.

Khác biệt mấu chốt:

- `repositories`: nơi lấy **dependency artifact**.
- `pluginRepositories`: nơi lấy **plugin artifact**.
- `build/plugins`: plugin **nào được cấu hình và chạy như thế nào**; không được đặt trong settings profile.

## 5. Những phần không được đặt trong settings profile

Một profile của POM có thể chứa cấu hình làm thay đổi **mô hình dự án**, ví dụ dependencies, build plugin hoặc reporting. Settings profile **không hỗ trợ** những phần đó.

Ví dụ **sai cấu trúc nếu đặt trong settings.xml**:

```xml
<profile>
    <id>bad-build-profile</id>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</profile>
```

Đây là đoạn **cố ý không hợp lệ trong settings**, chỉ để nhận diện lỗi. Maven có thể báo phần tử không được công nhận khi đọc settings; không nên dựa vào việc Maven im lặng bỏ qua rồi coi cấu hình đã có hiệu lực.

Những cấu trúc **không đặt trong settings profile** gồm:

- `<dependencies>`, `<dependencyManagement>`: thêm hoặc quản lý phiên bản thư viện dự án.
- `<build>`, `<plugins>`, `<pluginManagement>`, `<executions>`: cấu hình plugin và vòng đời build.
- `<modules>`: chọn các module của reactor.
- `<reporting>`: khai báo báo cáo của dự án.
- `<distributionManagement>`: nơi xuất bản artifact.
- `<name>`, `<description>`, `<artifactId>` ở vị trí mô hình dự án: metadata POM.

Đưa những phần đó vào `<profile>` bên trong `pom.xml` khi thật sự cần lựa chọn cấu hình theo môi trường, hoặc đặt chúng ở POM chính nếu là chuẩn chung. Đừng dùng settings profile để thay một cơ chế build nên được review cùng source code.

## 6. Phân biệt giới hạn của profile và phạm vi của toàn bộ settings

Một vấn đề khác là dùng **đúng vị trí trong cây XML**. Các phần tử sau thuộc mức **trực tiếp dưới `<settings>`**, không phải phần tử con của profile:

| Phần tử cấp settings | Mục đích |
| --- | --- |
| `<localRepository>` | Đường dẫn kho cục bộ của máy chạy Maven |
| `<mirrors>` | Chuyển hướng repository khi tải từ xa |
| `<servers>` | Cấu hình thông tin xác thực cho server/repository ID |
| `<proxies>` | Proxy của môi trường Maven |
| `<offline>` | Chế độ offline mặc định |
| `<interactiveMode>` | Cho phép tương tác hay không |
| `<pluginGroups>` | Nhóm plugin khi giải quyết tên goal viết tắt |
| `<profiles>` | Chứa các profile settings |
| `<activeProfiles>` | Danh sách profile ID được kích hoạt |

Ví dụ, nếu công ty có proxy dùng chung, **không** đặt `<proxies>` bên trong một profile để bật/tắt proxy theo kiểu profile. Cấu hình proxy thuộc cấp settings; một settings riêng được chọn bằng `-s` có thể mang cấu hình proxy phù hợp với môi trường.

Tương tự, muốn dùng kho local riêng:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <localRepository>${user.home}/.m2/repository-course</localRepository>
    <profiles>
        <profile>
            <id>course-env</id>
            <properties>
                <course.greeting>Chào từ settings</course.greeting>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>course-env</activeProfile>
    </activeProfiles>
</settings>
```

Đây là một settings XML **hoàn chỉnh** với `<localRepository>` đặt đúng vị trí. Nó tạo thêm kho riêng cho Maven, nhưng không thay đổi những phần tử được phép của profile. Đường dẫn dùng `${user.home}`, là thuộc tính hệ thống có thể được Maven nội suy; không phụ thuộc vào property `course.greeting`.

## 7. Ví dụ runnable Java 17: settings profile cung cấp một property cho dự án

Để kiểm chứng **settings profile tác động qua property nhưng không khai báo plugin build**, ta tạo một ứng dụng Java 17 có Maven Resources Plugin lọc tệp văn bản lúc build.

Cấu trúc:

```text
settings-profile-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/course/App.java
    │   └── resources/banner.properties
    └── test/
        └── java/dev/course/AppTest.java
```

### 7.1. POM hoàn chỉnh

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>settings-profile-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
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
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tại sao `<build>` ở đây nằm trong POM?** Vì settings profile không được phép chứa build. POM quyết định **có filtering hay không**, còn settings profile chỉ cung cấp **giá trị** được lọc vào resource khi profile hoạt động.

### 7.2. Resource sử dụng property do settings profile cung cấp

Tạo `src/main/resources/banner.properties`:

```properties
greeting=@course.greeting@
```

Trong Maven Resources Plugin, `@course.greeting@` là placeholder được hỗ trợ. Khi profile `course-env` ở settings đang active, Resources Plugin dùng property để tạo tệp `target/classes/banner.properties` có nội dung:

```properties
greeting=Chào từ settings
```

Tệp nguồn trong `src/main/resources` **không bị sửa**. Nếu profile không hoạt động, property không có nguồn thay thế trong ví dụ này; placeholder có thể còn nguyên trong resource, vì vậy chương trình bên dưới chủ động báo lỗi cấu hình. Điều này minh họa rõ **tính phụ thuộc môi trường** của settings profile.

### 7.3. Java đọc resource sau khi Maven filtering

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String messageFor(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không được để trống");
        }

        Properties properties = new Properties();
        try (InputStream stream =
                     App.class.getResourceAsStream("/banner.properties")) {
            if (stream == null) {
                throw new IllegalStateException("Thiếu banner.properties");
            }
            properties.load(new InputStreamReader(
                    stream, StandardCharsets.UTF_8));
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "Không đọc được banner.properties", exception);
        }

        String greeting = properties.getProperty("greeting");
        if (greeting == null || greeting.isBlank()
                || greeting.contains("@course.greeting@")) {
            throw new IllegalStateException(
                    "Thiếu course.greeting từ settings profile");
        }
        return greeting + ", " + name.strip() + "!";
    }

    public static void main(String[] args) {
        System.out.println(messageFor("Lan"));
    }
}
```

Dùng `Properties.load(Reader)` với UTF-8, thay vì mặc định `Properties.load(InputStream)` đọc ký tự theo quy ước ISO-8859-1, để không làm sai chữ tiếng Việt trong resource.

Tạo `src/test/java/dev/course/AppTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AppTest {
    @Test
    void usesGreetingFromSettings() {
        assertEquals("Chào từ settings, Lan!",
                App.messageFor("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> App.messageFor("   "));
    }
}
```

Kiểm thử thứ nhất cố ý **đòi hỏi settings profile cụ thể** để chứng minh cấu hình môi trường được sử dụng. Trong dự án thực tế, nên cân nhắc các giá trị mặc định hoặc kiểm thử độc lập với môi trường; đây là bài thực hành quan sát cơ chế settings, không phải thiết kế khuyến nghị cho mọi ứng dụng.

### 7.4. Chạy với settings riêng

Lưu tệp `settings-lab.xml` ở mục 3 vào vị trí đã chọn. Trên Linux/macOS, tại thư mục `settings-profile-demo`:

```bash
mvn -version
mvn -s "$HOME/.m2/settings-lab.xml" clean verify
java -cp target/classes dev.course.App
```

Khi build thành công, Surefire chạy **2 bài kiểm thử**. Lệnh Java in **chính xác**:

```text
Chào từ settings, Lan!
```

Maven đã biến resource thành `target/classes/banner.properties`, biên dịch mã Java ở `target/classes/dev/course/App.class` và chạy test từ `target/test-classes`. Nếu cần đóng gói, `mvn -s "$HOME/.m2/settings-lab.xml" package` sẽ tạo JAR của dự án trong `target/` (có thể không chạy được bằng `java -jar` nếu chưa khai báo Main-Class; lệnh `java -cp` ở trên thì hoạt động).

Trên Windows PowerShell, sau khi tạo tệp settings trong thư mục `.m2` của người dùng:

```powershell
$settings = Join-Path $env:USERPROFILE ".m2/settings-lab.xml"
mvn -s "$settings" clean verify
java -cp target/classes dev.course.App
```

Nếu không thấy chuỗi như mong đợi, hãy xác minh Maven thật sự đọc settings qua `-s`, profile `course-env` active và resource đã được lọc. Nếu tệp XML có lỗi, sửa settings trước khi suy đoán mã Java sai.

## 8. Kích hoạt profile theo cách nào?

Profile settings có thể hoạt động nhờ điều kiện `<activation>`, chỉ định `<activeProfiles>` hoặc sử dụng CLI `-P`. Các cách đó không thay đổi giới hạn XML.

| Cách | Cấu hình / lệnh | Ý nghĩa |
| --- | --- | --- |
| Tự kích hoạt theo điều kiện | `<activation><property>...</property></activation>` | Khi điều kiện khớp |
| Active qua settings | `<activeProfiles><activeProfile>course-env</activeProfile></activeProfiles>` | Mặc định khi dùng settings ấy |
| Active qua CLI | `mvn -s settings-lab.xml -Pcourse-env verify` | Yêu cầu bật profile trong lần chạy |
| Vô hiệu hóa một profile đã chọn | `mvn -P!course-env ...` trên một số shell cần quote ký tự `!` | Phụ thuộc cú pháp Maven/shell; kiểm tra profile hiệu lực |

Để thực hành một cách đơn giản, dùng `<activeProfiles>` như ví dụ mục 3, rồi xác nhận với Maven Help Plugin:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" help:active-profiles
```

Khi đó phải thấy profile `course-env` trong tập active. Cũng có thể dùng lệnh:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" help:evaluate -Dexpression=course.greeting -q -DforceStdout
```

Với môi trường bài thực hành, giá trị mong đợi là:

```text
Chào từ settings
```

Chú ý profile được định nghĩa **ngoài POM** (ở settings) không tự được đóng gói hoặc mang theo mã nguồn. Đồng nghiệp clone dự án mà không có settings phù hợp có thể không tái hiện được hành vi của profile. Đây là một lý do cần giữ logic build cốt lõi trong POM.

## 9. Khi settings và POM có profile cùng ID

Maven có thể có profile có cùng tên trong POM và settings. Tài liệu Maven chỉ ra rằng **giá trị của profile đang active từ settings có thể ưu tiên so với profile có ID tương đương trong POM** ở những phần phù hợp. Nếu cùng tên nhưng nội dung khác nhau, người học dễ hiểu nhầm vì nhìn vào POM mà không thấy cấu hình thực tế.

Ví dụ:

- POM có profile `course-env` khai báo `course.greeting=Chào từ POM`.
- Settings của một máy có profile cùng ID `course-env` khai báo `course.greeting=Chào từ settings`.
- Khi settings profile hoạt động, các giá trị trùng tên có thể dẫn đến kết quả khác với việc chỉ nhìn POM.

Không nên dựa vào va chạm ID như một cách ghi đè tùy tiện. Chọn tên khác nhau theo trách nhiệm, chẳng hạn `project-fast-tests` cho POM profile và `company-repository` cho settings profile. Nếu buộc phải dùng cùng ID, hãy ghi rõ chủ đích và kiểm tra **effective settings**, **active profiles** và **đầu ra build** trên phiên bản Maven thực tế.

Một điểm bổ sung: profile **không được kế thừa nguyên khối** như một “định nghĩa profile mới” cho mọi POM con; các **tác động của profile đã active** mới có thể ảnh hưởng đến model sau khi xây dựng. Việc tự kích hoạt profile theo điều kiện chỉ áp dụng cho profile trong nơi nó được định nghĩa, chứ không có nghĩa một profile khác cùng ID ở mọi module đều tự active.

## 10. Không thể dùng properties để lách giới hạn trực tiếp

Đôi khi có người hỏi: “Vì settings profile không chứa `<build>`, tôi đặt `<properties><compiler.release>21</compiler.release></properties>` có giống thêm cấu hình plugin không?”

**Không tự động.** Tính năng này phụ thuộc POM/plugin:

- Nếu POM có `<release>${compiler.release}</release>` trong Maven Compiler Plugin, một property tương ứng có thể cung cấp giá trị cho tham số đó.
- Nếu POM viết cứng `<release>17</release>` và không tham chiếu property thích hợp, đặt `compiler.release=21` trong settings không tự thay giá trị ấy.
- Nếu plugin hỗ trợ user property như `maven.compiler.release`, vẫn cần xem cấu hình plugin có ưu tiên một giá trị viết cứng hay không. Không có một quy tắc toàn cục “mọi property trong settings luôn thắng mọi phần tử POM”.
- Bản thân settings profile không định nghĩa thêm dependency, plugin execution hay module chỉ bằng việc đặt một tên property tùy ý.
- Đổi `maven.compiler.release` không tự chuyển JDK đang chạy Maven sang một phiên bản mới; phiên bản JDK thực tế phải hỗ trợ release được yêu cầu.

Minh họa cấu hình **hợp lệ trong POM**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>${compiler.release}</release>
    </configuration>
</plugin>
```

Đây chỉ là **đoạn nằm trong `<build><plugins>` của POM**, không phải đoạn đặt trong settings. Khi đó `compiler.release` có thể được định nghĩa trong POM hoặc profile, và Maven nội suy nó theo ngữ cảnh. Nếu muốn build tái lập, hãy cung cấp giá trị mặc định ngay trong POM thay vì buộc mọi người phải có cùng một settings cá nhân.

## 11. Lưu ý riêng về nội suy settings.xml

Maven Settings Reference nêu một giới hạn dễ bị bỏ qua: **property được định nghĩa trong profile của settings không được dùng để nội suy chính settings.xml**. Chẳng hạn đoạn sau không phải cách đáng tin để đổi kho local:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <localRepository>${my.local.repo}</localRepository>
    <profiles>
        <profile>
            <id>repo-lab</id>
            <properties>
                <my.local.repo>/tmp/maven-lab</my.local.repo>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>repo-lab</activeProfile>
    </activeProfiles>
</settings>
```

**Ví dụ trên cố ý mô tả cấu hình không hoạt động như kỳ vọng**: `my.local.repo` không được nội suy từ profile settings vào `localRepository` cùng tệp. Nếu cần kho local riêng, hãy khai báo trực tiếp đường dẫn (hoặc dùng một system/env property được hỗ trợ), ví dụ:

```xml
<localRepository>${user.home}/.m2/repository-lab</localRepository>
```

Hoặc truyền từ CLI:

```bash
mvn "-Dmaven.repo.local=$HOME/.m2/repository-lab" verify
```

Điều đó khác với việc một property như `course.greeting` đi từ settings profile sang **POM và resource filtering** như phần thực hành đã chứng minh.

## 12. Thực hành repository mà không làm hỏng project build

Có thể bổ sung một settings profile dành riêng cho môi trường mạng, ví dụ chỉ thêm `<repositories>` hoặc `<pluginRepositories>` để các dependency/plugin của nhóm được tìm từ kho nội bộ. Khi cấu hình như vậy:

1. Đặt URL thật, ID ổn định, policy releases/snapshots đúng yêu cầu.
2. Nếu kho yêu cầu xác thực, dùng `<servers>` tại **cấp settings**, với ID tương ứng; không đặt mật khẩu vào `<profile><properties>`.
3. Nếu cần mirror Maven Central qua repository manager, cân nhắc khai báo `<mirrors>` tại **cấp settings** thay vì tạo thêm một repository bất kỳ và hy vọng nó luôn được ưu tiên.
4. Giữ `<dependencies>`, phiên bản plugin, cấu hình test và bước đóng gói trong POM được commit cùng dự án.
5. Kiểm tra bằng một repository manager thật được cấp, không chạy các URL `example.org` trong ví dụ.

Trong CI/CD, có thể phát sinh settings tạm từ kho bí mật rồi truyền qua `-s`, trong khi vẫn dùng cùng POM được review. Cách này tách **cấu hình môi trường và xác thực** khỏi **logic build của sản phẩm**.

**Không đưa token vào `pom.xml`, không đưa username/password vào các property dùng chung và không đăng công khai nội dung effective settings/log debug khi chứa thông tin hạ tầng.**

## 13. Kiểm tra và gỡ lỗi

Bốn lệnh chẩn đoán dưới đây hữu ích khi không chắc settings profile đã có tác dụng hay chưa. Chạy từ thư mục dự án thực hành:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" help:active-profiles
mvn -s "$HOME/.m2/settings-lab.xml" help:effective-settings
mvn -s "$HOME/.m2/settings-lab.xml" help:effective-pom
mvn -s "$HOME/.m2/settings-lab.xml" help:evaluate -Dexpression=course.greeting -q -DforceStdout
```

Đọc chúng theo thứ tự:

- `help:active-profiles` cho biết profile nào đang active.
- `help:effective-settings` cho biết settings đã hợp nhất, gồm nguồn repository và active profiles.
- `help:effective-pom` cho biết model sau khi Maven tổng hợp POM, kế thừa và profile.
- `help:evaluate` đọc biểu thức cụ thể, ví dụ `course.greeting`.

**Kiểm chứng quan trọng nhất của ví dụ** vẫn là tệp `target/classes/banner.properties` và stdout của Java. Một profile có tên đúng nhưng không dùng bất kỳ property nào trong POM chưa chắc tạo ra thay đổi dễ thấy ở chương trình.

Các lệnh Help Plugin có thể cần tải plugin về local repository trong lần chạy đầu. Kết quả từ effective settings có thể chứa thông tin môi trường nội bộ; không đăng nguyên văn khi chưa kiểm tra dữ liệu nhạy cảm.

### Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Maven báo thẻ `build` không được công nhận trong settings | Đã copy POM profile sang settings | Chuyển `<build>` vào POM hoặc POM profile |
| Maven không chạy plugin dù có `pluginRepositories` | Nhầm nơi tải plugin với khai báo thực thi plugin | Đặt `<build><plugins>` trong POM |
| Dependency không được thêm dù khai báo `<dependencies>` trong settings profile | Settings profile không hỗ trợ dependencies | Khai báo dependency trong POM |
| Profile có trong settings nhưng không hoạt động | Thiếu `<activeProfiles>`, `-P` hoặc activation không khớp | Kiểm tra `help:active-profiles` |
| `course.greeting` không được thay trong resource | Không bật filtering, sai placeholder hoặc profile không active | Kiểm tra POM, `@course.greeting@` và profile |
| Giá trị property đúng trong settings nhưng POM không đổi | POM không tham chiếu property | Tạo chỗ sử dụng property rõ ràng trong POM/plugin |
| Dùng property trong settings profile để đặt `localRepository` | Không hỗ trợ nội suy từ profile của cùng settings | Dùng system/env property hoặc đường dẫn trực tiếp |
| Maven vẫn tải từ repository không mong muốn | Mirror, repository profile khác hoặc cache có hiệu lực | Kiểm tra effective settings, cấu hình mirror và log |
| Cấu hình chạy được máy A, lỗi máy B | Settings cá nhân khác nhau hoặc thiếu profile | Đưa logic build vào POM; tài liệu hóa phần môi trường |
| Lệnh `-Pprofile` không tìm thấy profile | Sai ID hoặc profile không được định nghĩa trong phạm vi hiện tại | Xem version Maven và profile ID; Maven 4 có thể từ chối ID không tồn tại |
| Tưởng `<servers>` trong profile là cách bật credential | `servers` thuộc cấp settings | Chuyển `<servers>` ra ngoài profile |
| XML parse được nhưng kết quả không đúng | Cấu hình bên ngoài profile không dùng, property trùng tên | Xem effective POM, active profiles và artifact thật |

## 14. Cách quyết định nên đặt cấu hình ở đâu

Dùng một quy tắc thiết kế đơn giản:

| Nhu cầu | Vị trí nên dùng |
| --- | --- |
| Thêm thư viện JUnit hoặc JDBC | `pom.xml` → `dependencies` |
| Chỉ rõ Compiler Plugin release, Surefire, Shade, executions | `pom.xml` → `build/plugins` hoặc POM profile |
| Chọn nhóm module cho một biến thể build | `pom.xml` / POM profile theo cấu hình Maven |
| Đổi property đầu vào đã được POM/plugin tham chiếu | Settings profile, POM profile hoặc CLI `-D`, tùy chủ sở hữu giá trị |
| Chọn nơi Maven tải dependency từ mạng nội bộ | Settings profile → `repositories` |
| Chọn nơi Maven tải plugin | Settings profile → `pluginRepositories` |
| Khai báo mirror, proxy và credential | Cấp `settings`, không đặt trong profile |
| Chọn local repository theo máy | Cấp `settings` hoặc `-Dmaven.repo.local` |
| Cần build giống nhau trên máy mới clone | POM + mã nguồn + wrapper/CI được quản lý và tài liệu môi trường |
| Cần cấu hình phát hành lên remote repository | POM → `distributionManagement`, credentials riêng ở settings/CI |

Nguyên tắc thực tế: **thứ gì quyết định chức năng, dependency và cách tạo sản phẩm nên nằm trong POM được version-control; thứ gì quyết định môi trường truy cập repository, máy tính và bí mật nên nằm trong settings hoặc hệ thống cấu hình an toàn.** Property trong settings nên bổ sung tham số môi trường chứ không thay thế cấu trúc build của dự án.

## 15. Câu hỏi và bài tập

1. Trong một settings profile, hãy phân loại các phần tử sau thành **được phép** hoặc **không được phép**: `id`, `activation`, `repositories`, `pluginRepositories`, `properties`, `dependencies`, `build`, `modules`, `reporting`.
2. Vì sao có thể đặt `<servers>` trong `settings.xml` nhưng không được đặt nó dưới `<profile>`? Hãy chỉ ra đúng cấp trong cây XML.
3. Dùng ví dụ chạy được: tạo `settings-lab.xml`, chạy `mvn -s ... clean verify`, kiểm tra `target/classes/banner.properties` và xác nhận Java in `Chào từ settings, Lan!`.
4. Bỏ `<activeProfiles>` khỏi settings và không truyền `-Pcourse-env`. Trong môi trường không có nguồn khác của `course.greeting`, tại sao bài kiểm thử của ví dụ sẽ thất bại? Khôi phục cấu hình sau thử nghiệm.
5. Một đồng nghiệp đặt `<build><plugins>...</plugins></build>` trong settings profile vì muốn chỉ bật plugin ở máy CI. Bạn sẽ chuyển cấu hình đó về POM/POM profile như thế nào?
6. Hãy giải thích tại sao `<pluginRepositories>` không phải nơi thêm Maven Compiler Plugin vào build.
7. Dùng `help:active-profiles` và `help:effective-settings` để phân biệt profile được khai báo với profile thực sự đang active.
8. Một settings profile có `<my.local.repo>/tmp/lab-repo</my.local.repo>` trong properties, trong khi top-level settings có `<localRepository>${my.local.repo}</localRepository>`. Vì sao đó không phải cách chọn kho local đáng tin? Nêu hai cách đúng.
9. Liệt kê nguy cơ khi dự án chỉ build được nếu máy có settings cá nhân mà POM hoặc tài liệu không mô tả; đề xuất cách làm dự án dễ tái lập hơn.

**Kết luận:** Profile trong `settings.xml` là **công cụ cấu hình môi trường Maven có phạm vi thu gọn**, chủ yếu về kích hoạt, thuộc tính và nơi phân giải artifact. Khi cần thay đổi dependency, plugin, module hoặc logic build, hãy dùng **profile trong `pom.xml`** và kiểm chứng bằng effective model cùng kết quả build.

## 16. Nguồn tham khảo chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Maven Settings Model — Profile](https://maven.apache.org/ref/3-LATEST/maven-settings/settings.html)
- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Apache Maven — Help Plugin](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
