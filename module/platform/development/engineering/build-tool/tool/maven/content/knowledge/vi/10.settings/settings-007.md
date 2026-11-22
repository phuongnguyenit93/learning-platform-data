# `profiles` và `activeProfiles` trong Maven `settings.xml`

## 1. Mục tiêu: chọn cấu hình theo môi trường mà không sửa POM

Một dự án Maven có thể được build ở máy cá nhân, máy CI hoặc trong mạng nội bộ của tổ chức. Những môi trường đó có thể khác nhau về máy chủ chứa dependency, proxy, repository mirror và các thuộc tính dùng trong quá trình build. Thay vì sửa `pom.xml` mỗi lần đổi môi trường, Maven cung cấp cơ chế **profile** để kích hoạt nhóm cấu hình theo điều kiện hoặc bằng lựa chọn tường minh.

Trong `settings.xml`, hai phần quan trọng là:

- **`<profiles>`**: nơi **định nghĩa** các profile, mỗi profile có một `<id>` và một số nhóm cấu hình được phép khai báo.
- **`<activeProfiles>`**: nơi **liệt kê ID của profile cần luôn được kích hoạt** khi Maven sử dụng tệp settings đó.

Định nghĩa và kích hoạt là **hai bước khác nhau**. Một profile được viết trong `<profiles>` không mặc nhiên có hiệu lực; nó cần được kích hoạt qua `<activeProfiles>`, `-P` hoặc cơ chế `<activation>` phù hợp.

Sau bài này, bạn có thể tạo một tệp settings mẫu, kiểm tra profile nào đang active, sử dụng thuộc tính từ settings trong build Java 17 và phân biệt profile của settings với profile trong `pom.xml`. Bạn cũng sẽ hiểu rủi ro khi profile trỏ tới repository/mirror hoặc chứa thông tin không nên công khai.

**Phạm vi:** ví dụ sử dụng Maven 3.x và dự án Java 17. Chi tiết chẩn đoán có thể khác theo phiên bản Maven/Help Plugin; luôn ghi nhận `mvn --version` của môi trường thực tế.

## 2. `settings.xml` nằm ở đâu và Maven đọc nó thế nào?

Maven thường có hai cấp settings:

| Cấp cấu hình | Vị trí thường gặp | Phạm vi |
| --- | --- | --- |
| Global settings | `<MAVEN_HOME>/conf/settings.xml` | Cấu hình của bản cài Maven, có thể áp dụng cho nhiều người dùng. |
| User settings | `~/.m2/settings.xml` | Cấu hình cho tài khoản người dùng chạy Maven. |

Trên Windows, `~` chỉ thư mục home của người dùng; vị trí thực tế cần xác minh thay vì sao chép đường dẫn Linux. Maven Wrapper, IDE hoặc CI có thể dùng bản Maven hay tệp settings riêng.

Khi cả global và user settings có mặt, Maven hợp nhất chúng theo cơ chế settings model; **user settings thường có ưu tiên cao hơn đối với phần cấu hình trùng nhau**. Không nên coi hai tệp là một đoạn XML được nối văn bản đơn giản.

Có thể chỉ định một **user settings** khác cho một invocation:

~~~bash
mvn -s settings-lab.xml validate
~~~

Tham số `-s` (hoặc `--settings`) chọn tệp user settings thay thế. Nó không tự ghép toàn bộ nội dung từ `~/.m2/settings.xml` vào tệp thử nghiệm; vì vậy trong công ty có mirror/proxy/credential riêng, lệnh `-s` với một tệp mẫu thiếu cấu hình mạng có thể khiến bước tải plugin thất bại. Maven còn có tùy chọn `-gs`/`--global-settings` để chỉ định global settings theo mục đích quản trị.

**Phân biệt:** `settings.xml` mô tả cấu hình Maven theo môi trường, còn `pom.xml` mô tả dự án và những thứ nên đi cùng mã nguồn. Thông thường không commit user settings có token/password lên Git.

## 3. Cấu trúc `profiles` và `activeProfiles`

Ví dụ một tệp `settings.xml` hợp lệ, rút gọn vào những phần liên quan:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">

    <profiles>
        <profile>
            <id>lab</id>
            <properties>
                <demo.message>Hello-from-settings-profile</demo.message>
            </properties>
        </profile>
    </profiles>

    <activeProfiles>
        <activeProfile>lab</activeProfile>
    </activeProfiles>
</settings>
~~~

Ý nghĩa từng phần:

1. `<settings>` là phần tử gốc của **Maven settings model**, không phải `<project>` của POM.
2. `<profiles>` chứa một hoặc nhiều định nghĩa `<profile>`.
3. `<id>lab</id>` định danh profile. Chọn ID rõ ý nghĩa như `dev`, `company-repo`, `ci`; không nên dùng tên mơ hồ.
4. `<properties>` khai báo thuộc tính có thể được Maven dùng trong quá trình xử lý model và các plugin hỗ trợ interpolation.
5. `<activeProfiles>` nằm **ngang cấp** với `<profiles>` ở dưới `<settings>`, không nằm bên trong một profile.
6. `<activeProfile>lab</activeProfile>` tham chiếu tới ID đã được khai báo; nó không tạo thêm một profile mới.

Có thể có nhiều mục `<activeProfile>`:

~~~xml
<activeProfiles>
    <activeProfile>company-repo</activeProfile>
    <activeProfile>dev</activeProfile>
</activeProfiles>
~~~

Đoạn này chỉ là **mảnh cấu hình** và chỉ hoạt động đúng như ý định nếu các profile tương ứng có định nghĩa phù hợp trong phạm vi Maven có thể tìm. Khi hai profile cùng định nghĩa một property hoặc repository ID, việc hợp nhất/ưu tiên phụ thuộc model và ngữ cảnh; **không thiết kế hệ thống dựa vào việc đoán thứ tự ghi của `activeProfile` sẽ luôn thắng**. Hãy tránh xung đột và xem effective configuration của đúng invocation.

### `profiles` khác `activeProfiles` như thế nào?

| `profiles` | `activeProfiles` |
| --- | --- |
| **Định nghĩa** nội dung profile. | **Chọn kích hoạt** profile theo ID. |
| Có thể chứa `id`, `activation`, `properties`, `repositories`, `pluginRepositories`. | Gồm danh sách các phần tử `activeProfile`, thường chỉ chứa ID. |
| Một profile có thể tồn tại nhưng không active. | Không khai báo thuộc tính, repository hay plugin trực tiếp. |
| Có thể được kích hoạt bằng cách khác ngoài activeProfiles. | Có tác dụng chọn profile khi Maven đọc tệp settings. |
| Đặt bên trong root `settings`. | Cũng đặt trực tiếp dưới root `settings`. |

**Bẫy cú pháp thường gặp:** viết `<activeProfile>lab</activeProfile>` trong `<profiles>` mà không có thẻ `<profile>`, hoặc viết `<activeProfiles>` bên trong `<profile>`. Đó không phải cấu trúc settings hợp lệ.

## 4. Settings profile được phép cấu hình những gì?

Profile trong `settings.xml` **không đầy đủ như profile trong `pom.xml`**. Trong settings, những nhóm cấu hình quan trọng nhất là:

| Thành phần | Mục đích |
| --- | --- |
| `id` | Tên profile duy nhất trong nhóm profile liên quan. |
| `activation` | Điều kiện kích hoạt profile. |
| `properties` | Cung cấp giá trị build theo môi trường. |
| `repositories` | Khai báo repository dùng để giải quyết dependency. |
| `pluginRepositories` | Khai báo repository dùng để tìm plugin. |

Ví dụ profile của mạng nội bộ có thể tham chiếu một repository riêng:

~~~xml
<profiles>
    <profile>
        <id>company-repo</id>
        <repositories>
            <repository>
                <id>company-public</id>
                <url>https://repo.example.org/maven/public</url>
                <releases>
                    <enabled>true</enabled>
                </releases>
                <snapshots>
                    <enabled>false</enabled>
                </snapshots>
            </repository>
        </repositories>
        <pluginRepositories>
            <pluginRepository>
                <id>company-plugins</id>
                <url>https://repo.example.org/maven/plugins</url>
            </pluginRepository>
        </pluginRepositories>
    </profile>
</profiles>
~~~

Đây là **mảnh XML minh họa**, không phải điểm cuối repository đang hoạt động. Chỉ thay nó bằng URL được quản trị viên cung cấp, đừng đưa nguyên `example.org` vào CI thật. Nếu sử dụng repository manager làm mirror cho mọi nguồn, thông thường cần cấu hình **`<mirrors>` ở cấp settings** bên ngoài profile thay vì chỉ thêm `<repository>`.

### Không được nhét cấu hình build của POM vào settings profile

Các mục như dưới đây **không thuộc phạm vi của settings profile**:

- `<dependencies>` và `<dependencyManagement>`.
- `<build>`, `<plugins>` và `<pluginManagement>`.
- `<modules>`, `<packaging>` hoặc cấu hình compiler execution phức tạp.

Các thành phần đó thuộc POM/parent POM hoặc profile của POM. Chẳng hạn, một profile trong `pom.xml` có thể đổi cách chạy test hoặc cấu hình Maven Compiler Plugin, còn một profile trong `settings.xml` thường chỉ cung cấp properties/repository để POM và plugin đã định nghĩa sử dụng.

**Settings profile không tự bật/tắt Java feature hoặc tự chạy một plugin goal.** Nếu bạn đưa `<demo.message>...` vào settings, Maven biết property đó trong ngữ cảnh thích hợp; mã Java được đóng gói không tự đọc được property đó trừ khi có cơ chế truyền giá trị rõ ràng (ví dụ resource filtering hoặc tham số JVM lúc chạy).

## 5. Các cách kích hoạt profile

### 5.1. Luôn active bằng `activeProfiles`

Cách dễ kiểm chứng cho cấu hình môi trường là:

~~~xml
<activeProfiles>
    <activeProfile>lab</activeProfile>
</activeProfiles>
~~~

Khi Maven sử dụng settings có cấu hình này, profile ID `lab` được kích hoạt theo settings. Không cần lặp `-Plab` ở từng câu lệnh. Một ID không có định nghĩa profile tương ứng sẽ không tự sinh ra nội dung cấu hình; hãy kiểm tra `help:active-profiles` thay vì coi việc ghi tên là đủ.

### 5.2. Chọn trên dòng lệnh bằng `-P`

Nếu profile `lab` được **định nghĩa** nhưng không nằm trong `activeProfiles` và không có activation tự động, bạn có thể chạy:

~~~bash
mvn -s settings-lab.xml -Plab validate
~~~

Tùy shell, có thể viết `-P lab`. Cách này hữu ích khi cùng một máy cần đổi nhiều chế độ build mà không sửa settings mỗi lần.

Để kích hoạt hai profile bằng tham số:

~~~bash
mvn -s settings-lab.xml -Plab,another-profile validate
~~~

Ở đây `another-profile` chỉ có ý nghĩa nếu có một định nghĩa thực tế tương ứng. Không coi đây là lệnh chạy ngay với tệp mẫu chỉ khai báo `lab`.

Một số phiên bản Maven cho phép **vô hiệu hóa profile** qua prefix `!` hoặc `-` trong danh sách `-P`; ví dụ trên shell có xử lý dấu `!` đặc biệt, cần quote đối số như `'-P!lab'`. Trước khi dùng trong script hoặc CI, kiểm tra cú pháp theo phiên bản Maven và shell thực tế. Nếu đang học cơ bản, cách rõ ràng nhất là quản lý đúng `activeProfiles` hoặc chạy `-P` tường minh.

### 5.3. Điều kiện trong `activation`

Một settings profile có thể dùng các điều kiện trong `<activation>`, ví dụ:

~~~xml
<profile>
    <id>env-lab</id>
    <activation>
        <property>
            <name>env.DEMO_ENV</name>
            <value>lab</value>
        </property>
    </activation>
    <properties>
        <demo.message>Environment-profile-active</demo.message>
    </properties>
</profile>
~~~

Đoạn này là **mảnh profile** cần đặt trong `<profiles>`, không phải tệp settings đầy đủ. Nó minh họa việc kích hoạt profile khi Maven nhận thấy biến môi trường `DEMO_ENV` có giá trị `lab` thông qua tên property `env.DEMO_ENV`. Ví dụ trên Bash:

~~~bash
DEMO_ENV=lab mvn -s settings-lab.xml help:active-profiles
~~~

Trên PowerShell:

~~~powershell
$env:DEMO_ENV = "lab"
mvn -s settings-lab.xml help:active-profiles
~~~

Để thử riêng cơ chế này, phải **thêm định nghĩa `env-lab` vào settings** và không dùng một mục `activeProfiles` đang ép profile đó luôn active. Đừng kết luận activation theo môi trường có tác dụng nếu chính `activeProfiles` đã kích hoạt profile trước.

Những điều kiện activation còn có thể dựa vào JDK, OS hoặc sự tồn tại/không tồn tại của một file theo khả năng phiên bản Maven và settings model. Cấu hình activation cần được kiểm chứng bằng `help:active-profiles` vì IDE, CI, shell khác nhau có thể cung cấp biến môi trường và JDK khác nhau.

### 5.4. `activeByDefault`

Một profile có thể khai báo:

~~~xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
~~~

Điều này dùng cơ chế kích hoạt mặc định của Maven, **không đồng nghĩa với một `activeProfile` tường minh ở root settings**. Tác động của việc kích hoạt các profile khác, nơi profile được định nghĩa và profile container có thể làm hành vi active-by-default khác với kỳ vọng. Khi muốn một cấu hình user-settings luôn áp dụng, `activeProfiles` rõ ID thường dễ kiểm toán hơn; khi muốn đổi theo môi trường, dùng activation điều kiện hoặc `-P`.

## 6. Thực hành hoàn chỉnh: settings profile tác động đến build Java 17

Ta tạo một dự án Java không cần framework. Settings profile sẽ đặt property `demo.message`, Maven Resources Plugin dùng property này để **lọc** file tài nguyên lúc build, và Java đọc file đã được đóng gói. Nhờ đó bạn phân biệt được:

1. Property do **Maven settings profile** cung cấp.
2. Giá trị được thay vào resource ở **build time**.
3. Java đọc **kết quả đã đóng gói**, chứ không tự đọc `settings.xml` lúc runtime.

### 6.1. Cấu trúc thư mục

~~~text
settings-profile-demo/
├── pom.xml
├── settings-lab.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── ProfileApp.java
        └── resources/
            └── config.properties
~~~

`settings-lab.xml` chỉ dùng cho bài tập và được chỉ định qua `-s`; nó không phải `pom.xml`, không tự được Maven đọc chỉ vì nằm cùng thư mục. Không lưu token vào file bài tập. Sau khi tạo các thư mục, dùng trình soạn thảo lưu ba tệp XML/Java và resource theo nội dung dưới đây.

### 6.2. Tệp `settings-lab.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">
    <profiles>
        <profile>
            <id>lab</id>
            <properties>
                <demo.message>Hello-from-settings-profile</demo.message>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>lab</activeProfile>
    </activeProfiles>
</settings>
~~~

Đây là **tệp đầy đủ**, dùng namespace của settings model. `demo.message` là một property của Maven khi profile `lab` active. Tệp này không khai báo mirror hay proxy; nếu môi trường của bạn cần những thứ đó, hãy dùng settings phù hợp với môi trường hoặc nhờ quản trị viên cung cấp file thực hành đã cấu hình mạng an toàn.

### 6.3. Tệp `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>settings-profile-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <includes>
                    <include>**/*.properties</include>
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
        </plugins>
    </build>
</project>
~~~

Vì sao POM cần `<filtering>true</filtering>`? Mặc định không phải mọi resource đều được Maven thay placeholder. Ví dụ chủ động bật filtering cho `.properties` để property Maven `demo.message` được đưa vào nội dung tài nguyên. Nếu ứng dụng có file nhị phân như ảnh hoặc tệp nén, **không bật filtering cho chúng** vì xử lý như văn bản có thể gây hỏng dữ liệu. Khi khai báo `<resources>` như ở đây, nhóm include chỉ chọn `.properties`; muốn đóng gói thêm loại file khác, phải cấu hình resource group phù hợp.

Các phiên bản plugin trong POM được chốt để ví dụ dễ tái hiện, không khẳng định là bản mới nhất. Lần build đầu có thể cần Internet để tải chúng.

### 6.4. Tệp `src/main/resources/config.properties`

~~~properties
message=@demo.message@
~~~

`@demo.message@` là placeholder mà Maven Resources Plugin có thể xử lý trong quá trình resource filtering. Nó **không phải** biểu thức Java và không tự được thay khi mở tệp trong IDE hoặc chạy JVM. Tại đây giá trị chỉ gồm ký tự ASCII nên việc `Properties.load(InputStream)` trong ví dụ Java dưới đây không gặp vấn đề encoding. Với tài nguyên tiếng Việt UTF-8, nên dùng `Properties.load(Reader)` với charset phù hợp.

### 6.5. Tệp `src/main/java/com/example/ProfileApp.java`

~~~java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ProfileApp {
    private ProfileApp() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                     ProfileApp.class.getResourceAsStream("/config.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing config.properties on the classpath");
            }
            properties.load(input);
        }

        System.out.println("Message: " + properties.getProperty("message"));
    }
}
~~~

Đây là chương trình Java hoàn chỉnh, không dùng dependency bên ngoài JDK. `getResourceAsStream("/config.properties")` đọc file được Maven đóng gói vào classpath. `Properties.load(InputStream)` đủ cho nội dung ASCII trong ví dụ; không suy rộng rằng nó tự nhận diện UTF-8 cho mọi tệp `.properties`.

### 6.6. Kiểm tra profile và property trước khi build

Đứng trong thư mục `settings-profile-demo`, chạy:

~~~bash
mvn --version
mvn -s settings-lab.xml help:active-profiles
mvn -s settings-lab.xml help:evaluate -Dexpression=demo.message -q -DforceStdout
~~~

Lệnh `help:active-profiles` cần cho thấy ID `lab` đang active. **Giá trị của lệnh `help:evaluate` cuối cùng** phải là:

~~~text
Hello-from-settings-profile
~~~

Các lệnh là ba invocation riêng. Log của `help:active-profiles` có thể chứa thêm thông tin; không yêu cầu nó có stdout giống một mẫu cố định.

### 6.7. Build và chạy Java

~~~bash
mvn -s settings-lab.xml clean package
~~~

Sau khi thành công, kiểm tra `target/classes/config.properties`. Nội dung được filtering dự kiến:

~~~properties
message=Hello-from-settings-profile
~~~

Tệp nguồn `src/main/resources/config.properties` **vẫn chứa** `message=@demo.message@`; Maven chỉ thay placeholder trong bản resource đầu ra, không sửa file nguồn.

Chạy:

~~~bash
java -cp target/settings-profile-demo-1.0-SNAPSHOT.jar com.example.ProfileApp
~~~

**Stdout chính xác:**

~~~text
Message: Hello-from-settings-profile
~~~

Trong lệnh Java, **không có `-s` và cũng không có `-P`**. Giá trị đi vào ứng dụng qua resource đã được Maven lọc **ở thời điểm build**. Chương trình có thể chạy từ một thư mục khác hoặc máy khác nếu classpath trỏ đúng JAR và môi trường JVM đáp ứng yêu cầu Java.

Tệp JAR được tạo bởi POM này chưa cấu hình `Main-Class`, do đó dùng `java -cp ... com.example.ProfileApp`, không giả định `java -jar` có thể chạy trực tiếp.

### 6.8. Thử chọn profile bằng `-P` thay cho `activeProfiles`

Để thấy sự khác biệt rõ ràng:

1. **Giữ nguyên** định nghĩa profile `lab` trong `<profiles>` của `settings-lab.xml`.
2. **Bỏ hẳn** đoạn `<activeProfiles>...lab...</activeProfiles>`, chỉ trong bản settings dùng cho bài tập.
3. Thử `mvn -s settings-lab.xml help:active-profiles`. Lúc này không có cơ chế nào trong tệp mẫu yêu cầu profile `lab` tự active.
4. Chạy lại với `-Plab`:

~~~bash
mvn -s settings-lab.xml -Plab help:active-profiles
mvn -s settings-lab.xml -Plab help:evaluate -Dexpression=demo.message -q -DforceStdout
mvn -s settings-lab.xml -Plab clean package
~~~

Property và Java output phải trở lại đúng giá trị ở mục 6.7 nếu mọi tệp khác giữ nguyên. **Không dùng kết quả build cũ để suy luận profile đã hoạt động**: luôn chạy lại `clean package` khi thử thay cấu hình để kiểm tra nội dung được lọc ở `target/classes/config.properties`.

## 7. Profile trong `settings.xml` khác profile trong `pom.xml` ra sao?

Hai loại profile đều có ID, activation và có thể tham gia cấu hình hiệu lực, nhưng phạm vi và ý định khác nhau:

| Tiêu chí | Settings profile | POM profile |
| --- | --- | --- |
| Vị trí | `~/.m2/settings.xml`, global settings hoặc file `-s`. | Trong `pom.xml` của project hoặc POM parent. |
| Phạm vi | Cấu hình gắn với máy/người dùng/môi trường Maven. | Cấu hình gắn với dự án và có thể theo mã nguồn. |
| Property | Có thể cung cấp `properties`. | Có thể cung cấp `properties`. |
| Repository | Có thể khai báo `repositories` và `pluginRepositories`. | Cũng có thể khai báo các repository theo cơ chế POM. |
| Plugin/dependency | Không khai báo trực tiếp build/plugins/dependencies. | Có thể cấu hình build, dependencies và nhiều phần tử model khác trong giới hạn profile POM. |
| Chia sẻ | Không nên commit user settings chứa bí mật. | POM thường được commit để tái hiện build. |

Ví dụ mảnh profile trong POM:

~~~xml
<profiles>
    <profile>
        <id>fast-tests</id>
        <properties>
            <skip.optional.tests>true</skip.optional.tests>
        </properties>
    </profile>
</profiles>
~~~

**Chú ý:** property `skip.optional.tests` trong ví dụ **không tự làm Maven bỏ qua test**. Muốn thay đổi hành vi chạy test, plugin test hoặc build configuration phải tham chiếu tới property này. Không nên hiểu mỗi property có tên mô tả là một công tắc đã được Maven mặc định hỗ trợ.

Maven Help Plugin có thể giúp phân biệt profile nào đang active trong project và profile nào đến từ settings. Trong một hệ thống lớn, profile ID trùng nhau ở nhiều nguồn có thể gây hiểu nhầm; nên đặt ID rõ ràng, kiểm tra kết quả model và hạn chế phụ thuộc vào các quy tắc ưu tiên khó đoán.

### `activeProfiles` có ý nghĩa với môi trường nào?

Một profile được khai báo trong user settings của máy A **không tự xuất hiện** trên máy B. Nếu máy B dùng settings khác hoặc không có ID đó, lệnh Maven của cùng một dự án có thể phân giải repository và properties khác.

Ngược lại, profile trong POM được chia sẻ cùng source code, nhưng nó cũng không nhất thiết active cho mọi người. Cấu hình có tính bắt buộc để build được dự án thường nên đặt trực tiếp ở POM/parent; những giá trị phụ thuộc môi trường như URL repository nội bộ, token và proxy thường được quản lý ở settings/CI.

## 8. Repository profile, mirror và authentication: ba khái niệm độc lập

Một settings profile có thể thêm repository, nhưng điều đó không đồng nghĩa đang cấu hình **mirror** hoặc credential.

| Thành phần | Vị trí thường dùng | Tác dụng |
| --- | --- | --- |
| `<profiles><profile><repositories>` | Settings profile hoặc POM profile | Khai báo repository logic để Maven tải dependencies. |
| `<profiles><profile><pluginRepositories>` | Settings profile hoặc POM profile | Khai báo repository để tải Maven plugins. |
| `<mirrors>` | Root `settings.xml` | Điều hướng yêu cầu đối với repository được khớp bằng `mirrorOf`. |
| `<servers>` | Root `settings.xml` | Cung cấp cơ chế thông tin xác thực tương ứng với ID server/repository/mirror được sử dụng. |
| `<proxies>` | Root `settings.xml` | Cấu hình proxy kết nối mạng theo môi trường. |

Một cấu hình mirror tối giản **minh họa**:

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>*</mirrorOf>
        <url>https://repo.example.org/maven/all</url>
    </mirror>
</mirrors>
~~~

Đây là **mảnh XML dưới `<settings>`**, không đặt trong `<profile>`. `mirrorOf=*` có thể khiến Maven gửi yêu cầu tới mirror đối với tất cả repository phù hợp, nên rất dễ làm build ngừng hoạt động nếu URL chưa có thật hoặc mirror thiếu artifact. Đừng áp dụng mảnh ví dụ lên máy đang làm việc nếu không có repository manager được xác nhận.

Ví dụ skeleton `servers` không chứa bí mật:

~~~xml
<servers>
    <server>
        <id>company-mirror</id>
        <username>provided-by-admin</username>
    </server>
</servers>
~~~

Thẻ `id` của `server` cần khớp ID thực tế mà Maven sử dụng cho xác thực; **khi truy cập thông qua mirror, thường là mirror ID**. Cách cấp password/token nên do hệ thống quản trị, CI secret store hoặc cơ chế credentials được phê duyệt thực hiện. Không đưa token thật vào bài học, không in toàn bộ `settings.xml` có bí mật lên log công khai và không commit credential.

### Profiles dùng repository không phải cấu hình upload

`<repositories>` và `<pluginRepositories>` chủ yếu phục vụ **tải xuống** dependency/plugin. Việc **xuất bản artifact** thuộc quy trình deploy/publisher cùng quyền và đích riêng, thường liên quan `distributionManagement` của POM hoặc plugin xuất bản. Kích hoạt một settings profile chứa repository tải dependency **không tự cho phép `mvn deploy`** vào đó.

## 9. Xem cấu hình hiệu lực và nguyên nhân một profile được kích hoạt

Các lệnh cần biết:

~~~bash
mvn -s settings-lab.xml help:active-profiles
mvn -s settings-lab.xml help:effective-settings
mvn -s settings-lab.xml help:effective-pom -Doutput=effective-pom.xml
mvn -s settings-lab.xml help:evaluate -Dexpression=demo.message -q -DforceStdout
~~~

Ý nghĩa:

- **`help:active-profiles`:** báo các profile đang được kích hoạt theo project/settings trong invocation hiện tại. Dùng nó trước khi suy luận repo/property đến từ profile nào.
- **`help:effective-settings`:** cho biết cấu hình settings sau khi xử lý global/user settings trong ngữ cảnh lệnh. Dùng để kiểm tra profile definitions, active profiles, mirror/proxy và repository configuration; **không công bố đầu ra khi chưa rà soát bí mật**.
- **`help:effective-pom`:** xem POM hiệu lực sau khi kết hợp model, parent và các profile phù hợp; nhận diện tác động cuối cùng lên các thuộc tính/build.
- **`help:evaluate`:** lấy giá trị một biểu thức cụ thể. Với ví dụ này khi `lab` active, giá trị `demo.message` là `Hello-from-settings-profile`.

Thêm `-X` nếu cần debug:

~~~bash
mvn -s settings-lab.xml -X validate
~~~

Chế độ debug giúp điều tra nguồn repository/mirror và profile selection, nhưng log có thể chứa địa chỉ nội bộ, đường dẫn máy, thông tin cấu hình và các giá trị nhạy cảm. Chỉ chia sẻ đoạn đã kiểm duyệt.

### Không nhầm settings đang sử dụng

Một câu lệnh chạy từ CLI với `-s settings-lab.xml` không nhất thiết giống kết quả trong IDE hoặc CI:

- IDE có thể chọn Maven khác, user settings khác hoặc profile tự kích hoạt.
- CI có thể đặt settings qua tham số dòng lệnh hoặc file tạm được cấp từ secret store.
- Maven Wrapper `./mvnw` dùng Maven version theo dự án, nhưng vẫn phải kiểm tra settings/CLI được truyền vào.
- Hai bản Maven có thể khác plugin version, cách xử lý profile hoặc cấu hình repository theo phiên bản.

Khi phân tích lỗi, hãy ghi **Maven version, Java version, POM, user/global settings đang dùng, profile active và lệnh chính xác**, không chỉ chụp một đoạn `pom.xml`.

## 10. Lưu ý về thứ tự ưu tiên và xung đột

Một hệ thống có nhiều nguồn cho cùng property:

- `<properties>` trực tiếp trong `pom.xml`.
- Properties của parent POM.
- Profile của POM.
- Settings profile đã active.
- User property từ dòng lệnh như `-Ddemo.message=...`.
- Một plugin có thể có configuration riêng hoặc giá trị mặc định của chính nó.

Không dùng quy tắc truyền miệng như “profile viết sau luôn thắng” cho mọi nhóm cấu hình và mọi Maven version. Đối với property từ settings profile, chúng được đưa vào ngữ cảnh xử lý model khi profile active; các nguồn khác có thể ảnh hưởng giá trị cuối cùng tùy loại expression và cách plugin nhận cấu hình.

Nếu cần một bản build xác định, thực hành tốt là **đặt tên property duy nhất cho mục đích cụ thể**, không để cùng một property mâu thuẫn ở nhiều profile. Sau đó dùng `help:evaluate` để xác minh:

~~~bash
mvn -s settings-lab.xml help:evaluate -Dexpression=demo.message -q -DforceStdout
~~~

Khi dùng `-Ddemo.message=from-cli`, nhiều tình huống Maven sẽ ưu tiên user property do CLI cung cấp khi nội suy giá trị. Tuy nhiên để xác minh cơ chế cụ thể, hãy kiểm tra bằng `help:evaluate` và **đầu ra của plugin** chứ không chỉ suy luận từ tên property.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `help:active-profiles` không liệt kê `lab` | Dùng sai settings, ID không khớp, `activeProfiles` không chọn đúng hoặc activation chưa thỏa. | Kiểm tra tham số `-s`, tên `<id>` và `<activeProfile>`; xem effective settings. |
| Có `<profiles>` nhưng property không có hiệu lực | Profile chỉ được định nghĩa, chưa active. | Thêm `activeProfiles` hoặc gọi `-Plab`; kiểm tra bằng Help Plugin. |
| Maven báo settings XML lỗi hoặc không parse được | Đặt `activeProfiles` sai cấp, thiếu thẻ đóng, dùng thẻ POM không hợp lệ trong settings profile. | So với cấu trúc XML mẫu và thông báo dòng lỗi. |
| Property từ settings không được Java nhìn thấy khi chạy JAR | Maven property không tự biến thành Java system property. | Dùng resource filtering hoặc truyền tham số JVM/cơ chế cấu hình runtime phù hợp. |
| `@demo.message@` vẫn còn trong `target/classes/config.properties` | Profile chưa active, property không được định nghĩa hoặc resource filtering chưa bật/không áp dụng. | Kiểm tra `help:evaluate`, POM `<resources>`, build log và file output. |
| Thay settings rồi chạy ứng dụng vẫn thấy thông điệp cũ | JAR đang dùng là sản phẩm build trước hoặc shell đang chạy nhầm file. | Chạy lại `mvn -s ... clean package` và xác minh đúng `target/classes`/JAR. |
| `-s settings-lab.xml` khiến Maven không tải được plugin | Tệp mẫu bỏ qua mirror/proxy/credentials từ user settings bình thường. | Dùng settings do môi trường cấp; kiểm tra repository và mạng. |
| Thêm repository nhưng Maven vẫn tải từ mirror khác | `mirrors` ở root settings có thể điều hướng yêu cầu repository. | Kiểm tra effective settings và log phân giải. |
| Repository HTTP 401/403 | Thiếu quyền hoặc server ID/credential không khớp endpoint đang dùng. | Kiểm tra `servers`/mirror ID và quyền; không ghi token trong POM. |
| `-Plab` không kích hoạt được profile | ID sai hoặc profile không tồn tại trong phạm vi Maven nhận diện; shell truyền đối số sai. | So `id`, Help Plugin và lệnh đã chạy. |
| Build ở máy cá nhân khác CI dù cùng POM | Settings, active profiles, biến môi trường, Maven/JDK hoặc mirror khác nhau. | Ghi lại cấu hình hiệu lực và log của từng môi trường. |
| Nhiều profile cùng định nghĩa `demo.message` | Xung đột property khiến khó biết giá trị cuối cùng. | Giảm trùng lặp; xác minh bằng `help:evaluate`. |
| Đặt token trong `properties` của settings profile | Property có thể được log, nội suy vào artifact hoặc lộ trong effective configuration. | Chuyển sang cơ chế bảo mật phù hợp, thay token đã lộ và rà soát artifact/log. |

### Trình tự chẩn đoán hiệu quả

Khi kết quả không như dự tính, theo thứ tự:

1. **Xác nhận settings đang được đọc**: lệnh có `-s` không, IDE/CI có dùng file khác không?
2. **Xác nhận profile active**: `mvn ... help:active-profiles`.
3. **Xác nhận property**: `mvn ... help:evaluate -Dexpression=...`.
4. **Xác nhận plugin thật sự dùng property**: xem `pom.xml`, resource filtering/goal/configuration.
5. **Xác nhận artifact mới**: chạy lại build khi cần, kiểm tra `target/classes` và nội dung JAR.
6. **Nếu lỗi mạng**: kiểm tra repository logic, mirrors, proxies và server IDs; không chữa bằng cách sửa code Java không liên quan.

Không xóa cache `~/.m2/repository` hay bật/tắt tùy tiện các profile cho đến khi biết nguyên nhân. Thay đổi settings có thể ảnh hưởng **mọi dự án Maven trên cùng tài khoản**.

## 12. Bài thực hành tự kiểm chứng

Thực hiện với project `settings-profile-demo` ở mục 6:

1. Tạo `settings-lab.xml`, `pom.xml`, `ProfileApp.java` và `config.properties` đúng như mẫu.
2. Chạy `mvn -s settings-lab.xml help:active-profiles`. Chứng minh ID `lab` active nhờ `activeProfiles`.
3. Chạy `help:evaluate` cho `demo.message` và đối chiếu đúng chuỗi `Hello-from-settings-profile`.
4. Chạy `mvn -s settings-lab.xml clean package`. Kiểm tra `target/classes/config.properties` đã thay placeholder.
5. Chạy `java -cp target/settings-profile-demo-1.0-SNAPSHOT.jar com.example.ProfileApp`; đối chiếu `Message: Hello-from-settings-profile`.
6. Bỏ mục `activeProfiles` trong file settings của bài tập, chạy `help:active-profiles`; quan sát profile không được tự active.
7. Chạy lại với `-Plab`, kiểm tra property và build lại để so sánh.
8. Thử đổi `demo.message` thành `New-message` trong profile, build mới và kiểm chứng Java in `Message: New-message`; giải thích vì sao chỉ sửa settings mà không build lại không làm JAR cũ thay đổi.
9. Viết bảng phân biệt ba nơi: `settings.xml`, `pom.xml` và Java runtime; giải thích property thuộc cấp nào, nơi nào lưu credential và thao tác nào tạo artifact.

**Câu hỏi tự đánh giá:** `<profiles>` khác `<activeProfiles>` thế nào? Vì sao ID trong `activeProfile` phải khớp profile được định nghĩa? Settings profile có thể khai báo `<build><plugins>` không? `-s` khác `-P` ra sao? Mirror nằm trong profile hay ở root settings? Vì sao Java chạy từ JAR không tự đọc `demo.message` của Maven settings?

### Kết luận

**`profiles` mô tả những lựa chọn cấu hình môi trường; `activeProfiles` chọn profile nào luôn được áp dụng trong settings tương ứng.** Profile của settings thường mang properties và repository, còn cấu hình biên dịch/phụ thuộc/plugin thuộc POM và profile của POM. Giá trị settings chỉ tác động lên artifact khi một bước build thực sự sử dụng nó; ứng dụng Java không tự kế thừa user settings của Maven.

Hãy luôn nhớ chuỗi kiểm tra: **settings được chọn → profile active → property/repository hiệu lực → plugin sử dụng → artifact mới được build**. Đây là cách làm chủ các profile theo môi trường mà không biến `settings.xml` thành một bản POM thứ hai.

## Tài liệu chính thức

- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — Introduction to Build Profiles: https://maven.apache.org/guides/introduction/introduction-to-profiles.html
- Maven Help Plugin — Active Profiles: https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html
- Maven Help Plugin — Effective Settings: https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html
- Maven Resources Plugin — Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html
