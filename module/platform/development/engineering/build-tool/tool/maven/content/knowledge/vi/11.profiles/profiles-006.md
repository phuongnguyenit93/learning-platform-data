# Maven Profiles: Nhiều profile cùng hoạt động và xung đột giá trị cấu hình

## 1. Khi nhiều profile cùng được bật, Maven làm gì?

Trong Apache Maven, một **build profile** là tập điều chỉnh có điều kiện cho mô hình dự án (*Project Object Model* — POM). Profile có thể thay đổi `properties`, dependencies, plugin executions, repositories và những thành phần cấu hình được Maven cho phép. Profile hữu ích để bật kiểm thử tích hợp, cấu hình phát hành hoặc bổ sung công cụ phân tích, nhưng cũng dễ tạo **xung đột** khi hai profile cùng định nghĩa một tham số với các giá trị khác nhau.

Ví dụ, POM có hai profile:

```xml
<profiles>
    <profile>
        <id>dev</id>
        <properties>
            <app.message>DEV</app.message>
        </properties>
    </profile>
    <profile>
        <id>qa</id>
        <properties>
            <app.message>QA</app.message>
        </properties>
    </profile>
</profiles>
```

Đây là **fragment POM** cần nằm bên trong `<project>`, không phải một tệp POM độc lập. Nếu chạy:

```bash
mvn package -P dev,qa
```

Maven tạo **một mô hình POM hiệu lực (effective POM)** với tác dụng của cả hai profile đang hoạt động; nó không tự chạy một lượt build cho `dev` rồi lượt thứ hai cho `qa`. Khi cùng gán `app.message`, Maven phải chọn giá trị hiệu lực. Quy tắc của **những profile trong cùng POM** là: **profile được khai báo sau trong file** có ưu tiên khi cùng ghi một giá trị đơn; trong ví dụ, `qa` thắng và `app.message=QA`.

Mục tiêu của bài:

1. Nhận diện tất cả cách kích hoạt profile: `-P`, `settings.xml`, `activeByDefault`, activation theo property/JDK/OS/file.
2. Dự đoán kết quả xung đột scalar property khi **nhiều profile cùng active trong một POM**, không nhầm **thứ tự `-P`** với **thứ tự khai báo XML**.
3. Hiểu điểm khác nhau giữa **ghi đè giá trị đơn** và **hợp nhất danh sách/plugin configuration**.
4. Kiểm tra profile nào thực sự active, giá trị nào được dùng, và artifact cuối bằng Maven Help Plugin.
5. Xây dựng ví dụ Java 17 đầy đủ, tạo JAR và quan sát tác động của `local`, `dev`, `qa`, `audit`.
6. Tổ chức profiles để build trên máy phát triển và CI nhất quán, tránh cấu hình release sai do merge ngầm.

Phần thực hành lấy **Maven 3.9.x và JDK 17+** làm ngữ cảnh. Một số tính năng và cách kiểm tra profile trong Maven 4 khác với Maven 3; không đồng nhất chúng khi viết pipeline.

## 2. Các cách kích hoạt profile có thể xảy ra đồng thời

| Cơ chế | Ví dụ | Lưu ý |
| --- | --- | --- |
| Bật tường minh bằng CLI | `-P dev,qa` | Đây là danh sách profile ID; có thể bật nhiều ID |
| Được bật trong settings | `<activeProfiles><activeProfile>company</activeProfile></activeProfiles>` | Có thể đến từ user/global `settings.xml` |
| Hoạt động mặc định | `<activeByDefault>true</activeByDefault>` | Có thể tắt khi một profile khác trong cùng POM được kích hoạt |
| Activation theo property | `-Ddemo.target=qa` | Có thể hoạt động song song với `-P dev` |
| Activation theo JDK | `<jdk>[17,)</jdk>` | Xét JDK Maven đang chạy; không tự cài JDK |
| Activation theo OS | `<os><family>Windows</family></os>` | Có thể khác giữa máy cá nhân và Linux CI |
| Activation theo file | `<file><exists>...</exists></file>` | File chỉ có trên một máy có thể làm build khác |
| Điều kiện đặc biệt | Activation theo packaging ở các bản Maven hỗ trợ | Cần đối chiếu Maven version đang sử dụng |

Maven profiles được khai báo tại **POM của project**, **user settings** (`~/.m2/settings.xml`) hoặc **global settings** của Maven. Settings profile có **phạm vi cấu hình hạn chế hơn**: chủ yếu `activation`, `properties`, `repositories` và `pluginRepositories`; không thể tùy ý khai báo `build/plugins` như trong POM profile.

Một build có thể đồng thời có profile `dev` được bật bởi `-P`, profile `qa` được kích hoạt do property, và profile repository được active từ settings. Việc chỉ nhìn thấy `-P dev` trên terminal **không đủ** để kết luận chỉ có một profile đang active.

### 2.1. Điều kiện activation theo property

Ví dụ **fragment profile**:

```xml
<profile>
    <id>qa</id>
    <activation>
        <property>
            <name>demo.target</name>
            <value>qa</value>
        </property>
    </activation>
    <properties>
        <app.message>QA</app.message>
    </properties>
</profile>
```

Chạy `mvn package -Ddemo.target=qa` có thể kích hoạt `qa` mà không cần `-P qa`. Nếu chạy đồng thời `-P dev -Ddemo.target=qa`, cả `dev` lẫn `qa` có thể active. Biến điều khiển activation (`demo.target`) và biến do profile định nghĩa (`app.message`) là hai mục khác nhau; cách tách này giúp tránh thiết kế activation tự tham chiếu, khó kiểm soát.

### 2.2. `activeByDefault` không phải điều kiện luôn đúng

```xml
<profile>
    <id>local</id>
    <activation>
        <activeByDefault>true</activeByDefault>
    </activation>
    <properties>
        <app.message>LOCAL</app.message>
    </properties>
</profile>
```

Khi không profile nào khác trong **cùng POM** được kích hoạt, `local` có thể active mặc định. Nếu cùng POM có một profile `audit` được bật bằng `-P audit`, `local` bị vô hiệu hóa dù `audit` hoàn toàn không khai báo `app.message`. Khi đó giá trị `app.message` có thể quay về giá trị nền ngoài `<profiles>`.

**Khuyến nghị:** các giá trị nền bắt buộc cho build nên có ở `<properties>` ngoài profiles. Đừng chỉ định nghĩa toàn bộ giá trị nền trong `activeByDefault`, vì việc bật một profile phụ có thể khiến chúng biến mất.

### 2.3. `-P` không phải danh sách ưu tiên

Hai lệnh:

```bash
mvn validate -P dev,qa
mvn validate -P qa,dev
```

kích hoạt **cùng hai ID**. Đảo vị trí tên trong CLI không phải cách đổi ưu tiên của các profile **cùng một POM**. Để thay đổi kết quả xung đột `app.message` trong ví dụ đầu, bạn phải thay đổi cấu trúc/giá trị POM hoặc không kích hoạt đồng thời các profile đó — không dùng thủ thuật đảo `-P`.

## 3. Quy tắc merge khi có nhiều active profiles

### 3.1. Giá trị đơn cùng tên: profile khai báo sau thắng trong cùng POM

Giả sử có một property nền:

```xml
<properties>
    <app.message>BASE</app.message>
</properties>
```

và hai profile đã giới thiệu ở phần 1, với `qa` được khai báo **sau** `dev`. Trong cùng POM:

| Profile active | Giá trị `app.message` |
| --- | --- |
| Không có profile ghi đè | `BASE` |
| Chỉ `dev` | `DEV` |
| Chỉ `qa` | `QA` |
| `dev`, `qa` | `QA` |
| `qa`, `dev` | `QA` |

Bảng này **giả định không có override khác** từ CLI, settings hoặc những điều kiện bổ sung. Tài liệu Maven mô tả: khi nhiều profile được kích hoạt trong **cùng POM hoặc cùng external file**, profile **được định nghĩa sau** có ưu tiên cao hơn với phần tử trùng. Đây là thứ tự trong **XML**, không phải thứ tự kích hoạt.

Nếu đổi chỗ hai block `<profile>` trong POM, kết quả có thể đổi dù lệnh build vẫn y nguyên. Vì vậy với cấu hình production, việc dựa vào “profile sau thắng” để giải quyết hai môi trường loại trừ nhau là một lỗi thiết kế tiềm ẩn.

### 3.2. Không trùng key: tác dụng có thể cùng tồn tại

Nếu `dev` đặt `app.message=DEV` còn `audit` chỉ đặt `audit.enabled=true`, bật `-P dev,audit` có thể tạo đồng thời `app.message=DEV` và `audit.enabled=true`. Hai profile được **kết hợp**, không nhất thiết chọn một.

Cách phân nhóm profile tốt:

- **Một trục môi trường:** `dev`, `qa`, `prod`; thông thường nên chọn **một** giá trị môi trường.
- **Các trục chức năng:** `audit`, `coverage`, `integration-tests`, `static-analysis`; có thể bật kèm môi trường và lý tưởng là không ghi đè các property môi trường.

Maven **không mặc định từ chối** lệnh `-P dev,prod` chỉ vì tên gợi ý mâu thuẫn. Nếu muốn bảo vệ deploy, phải có quy tắc/pipeline kiểm tra tổ hợp profile được phép.

### 3.3. `-D` là một nguồn override khác trong ngữ cảnh plugin

```bash
mvn package -P dev,qa -Dapp.message=CLI
```

Trong **Maven Resources Plugin**, user property `-Dapp.message=CLI` có thể được dùng để thay thế `@app.message@` khi filter resource, dù active POM profiles cùng khai báo `app.message`. Với ví dụ thực hành dưới đây, giá trị cuối trong resource là `CLI`.

**Không khái quát hóa** rằng `-D` luôn thay thế mọi trường model của POM. Cách nội suy và thứ tự ưu tiên tùy vào loại trường và plugin. Ví dụ resource filtering minh họa một trường hợp cụ thể, không phải phép chỉnh sửa bất kỳ tọa độ `groupId:artifactId:version`.

### 3.4. Plugin configuration và collections có quy tắc phức tạp hơn

Không phải mọi phần tử trong profile đều là scalar property. Hãy phân biệt:

| Dạng cấu hình | Điều xảy ra khi active cùng lúc | Kiểm tra |
| --- | --- | --- |
| `properties` cùng key | Giá trị trùng được override theo thứ tự thích hợp | `help:evaluate`, effective POM, output thực tế |
| Plugins khác ID | Có thể cùng được bổ sung vào build | Effective POM, plugin log |
| Cùng plugin (`groupId:artifactId`) | Cấu hình plugin được merge theo model/XML | Effective POM và goal đã chạy |
| Plugin executions | Xem execution ID, phase, goals, cấu hình kế thừa | Effective POM và log |
| Dependencies | Được kết hợp theo quy tắc model/khóa dependency | Effective POM, `dependency:tree` |
| Repositories | Danh sách, ID, nguồn settings/POM và mirror ảnh hưởng thứ tự | Effective settings/POM, resolver log |
| `build.finalName` | Giá trị đơn có thể bị profile khác thay thế | Effective POM và tên artifact |
| Cấu hình XML plugin | Có thể override/append từng phần, không phải xóa sạch cả plugin | Effective POM và plugin output |

Ví dụ hai profile cùng chạm **một plugin** (cả hai là fragment trong `<plugins>` của từng profile):

```xml
<!-- profile fast -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <skipTests>true</skipTests>
    </configuration>
</plugin>
```

```xml
<!-- profile full -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <skipTests>false</skipTests>
        <trimStackTrace>false</trimStackTrace>
    </configuration>
</plugin>
```

Khi cả `fast` và `full` active, Maven hợp nhất cấu hình theo định danh plugin và cấu trúc XML. Tham số `skipTests` cùng key có thể bị thay thế; `trimStackTrace` chỉ xuất hiện một phía vẫn có thể được giữ lại. **Không** suy ra “profile thắng” sẽ làm biến mất mọi plugin và execution còn lại. Cần xem **effective POM** và chạy chính test goal để xác nhận hành vi.

Một số cấu hình plugin hỗ trợ thuộc tính merge như `combine.self="override"` hoặc `combine.children="append"` trong ngữ cảnh phù hợp. Chúng không phải công tắc chung để định nghĩa lại thứ tự mọi profiles; chỉ dùng khi hiểu model và plugin cụ thể.

## 4. Ví dụ Java 17 hoàn chỉnh: bốn profile có thể kiểm nghiệm

Tạo ứng dụng JAR đọc một file `.properties` đã được Maven **filter tại build time**. Chúng ta dùng:

- `local`: `activeByDefault`, ghi đè `message=LOCAL`, `mode=local`.
- `dev`: đặt `message=DEV`, `mode=dev`.
- `qa`: được khai báo **sau `dev`**, đặt `message=QA`, `mode=qa`; có thêm activation qua `-Ddemo.target=qa`.
- `audit`: chỉ đặt `audit=true`.
- POM ngoài profile đặt nền `BASE`, `base`, `false`.

Java đọc dữ liệu đã được đóng vào JAR; đầu ra sẽ minh họa quy tắc merge mà không phụ thuộc thư viện ngoài.

### 4.1. Cấu trúc thư mục

```text
profile-conflict-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── profiledemo/
        │               └── Main.java
        └── resources/
            └── build-info.properties
```

Yêu cầu JDK 17+ và Maven 3.9.x. Các plugin Maven được lấy từ repository khi máy chưa cache; không cần tự tạo `target` trước.

### 4.2. Tệp pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>profile-conflict-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.message>BASE</demo.message>
        <demo.mode>base</demo.mode>
        <audit.enabled>false</audit.enabled>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build-info.properties</include>
                </includes>
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.profiledemo.Main</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>local</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <demo.message>LOCAL</demo.message>
                <demo.mode>local</demo.mode>
            </properties>
        </profile>

        <profile>
            <id>dev</id>
            <properties>
                <demo.message>DEV</demo.message>
                <demo.mode>dev</demo.mode>
            </properties>
        </profile>

        <profile>
            <id>qa</id>
            <activation>
                <property>
                    <name>demo.target</name>
                    <value>qa</value>
                </property>
            </activation>
            <properties>
                <demo.message>QA</demo.message>
                <demo.mode>qa</demo.mode>
            </properties>
        </profile>

        <profile>
            <id>audit</id>
            <properties>
                <audit.enabled>true</audit.enabled>
            </properties>
        </profile>
    </profiles>
</project>
```

**Giải thích cấu trúc:**

1. Các giá trị nền `BASE`, `base`, `false` luôn có trong POM, kể cả khi `local` không được kích hoạt. Vì `activeByDefault` có thể tắt, đây là phần đặc biệt quan trọng.
2. `qa` được khai báo sau `dev` trong cùng POM. Khi cả hai active, `qa` override hai property trùng là `demo.message` và `demo.mode`.
3. `audit` định nghĩa property khác, nên có thể bổ sung cùng `dev` hoặc `qa`.
4. Activation `<name>demo.target</name><value>qa</value>` kích hoạt `qa` khi user property tương ứng có giá trị `qa`. `demo.target` **không phải** một trong hai property bị override.
5. Maven Resources Plugin được giới hạn filtering cho file text `build-info.properties`, không filter nhầm file nhị phân. Không nên bật filtering với ảnh, file JAR hoặc tài liệu binary.
6. Maven JAR Plugin đặt `Main-Class`, cho phép chạy `java -jar` vì ứng dụng không có thư viện runtime bên ngoài.

### 4.3. Tệp src/main/resources/build-info.properties

```properties
message=@demo.message@
mode=@demo.mode@
audit=@audit.enabled@
```

Maven Resources Plugin hỗ trợ delimiter `@...@`. Trong phase `process-resources`, các placeholder được thay bằng giá trị hiệu lực của property, rồi file được copy vào `target/classes/build-info.properties`. Phase `package` đưa resource đó vào JAR.

Các giá trị minh họa đều là ASCII, vì vậy Java `Properties.load(InputStream)` đọc và in ổn định. Với resource chứa Unicode/placeholder đặc biệt của framework, cần kiểm tra encoding và delimiter/filtering tương ứng.

### 4.4. Tệp src/main/java/com/example/profiledemo/Main.java

```java
package com.example.profiledemo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Properties config = new Properties();

        try (InputStream stream =
                     Main.class.getResourceAsStream("/build-info.properties")) {
            if (stream == null) {
                throw new IllegalStateException(
                        "Missing build-info.properties");
            }
            config.load(stream);
        }

        System.out.println("message=" + config.getProperty("message"));
        System.out.println("mode=" + config.getProperty("mode"));
        System.out.println("audit=" + config.getProperty("audit"));
    }
}
```

Đây là mã Java đầy đủ, không phải pseudocode. Tên `package` và thư mục `com/example/profiledemo` khớp nhau. Ứng dụng chỉ đọc dữ liệu đã filter trong JAR; nó không truy cập POM hay biết trực tiếp tên Maven profile tại runtime.

### 4.5. Build mặc định

Tại thư mục `profile-conflict-demo/`:

```bash
java -version
javac -version
mvn -version
mvn clean package
java -jar target/profile-conflict-demo-1.0.0.jar
```

Vì chưa kích hoạt profile nào khác, `local` active mặc định. **Stdout chính xác của dòng `java -jar`** (không tính log Maven):

```text
message=LOCAL
mode=local
audit=false
```

`mvn clean package` sẽ tạo `target/classes/build-info.properties`, `target/classes/com/example/profiledemo/Main.class` và `target/profile-conflict-demo-1.0.0.jar`.

### 4.6. Chỉ dev

```bash
mvn clean package -P dev
java -jar target/profile-conflict-demo-1.0.0.jar
```

Stdout:

```text
message=DEV
mode=dev
audit=false
```

Bật `dev` làm `local` activeByDefault tắt trong cùng POM. `audit.enabled` lấy giá trị nền `false`.

### 4.7. Chỉ qa

```bash
mvn clean package -P qa
java -jar target/profile-conflict-demo-1.0.0.jar
```

Stdout:

```text
message=QA
mode=qa
audit=false
```

### 4.8. Cùng active dev và qa

```bash
mvn clean package -P dev,qa
java -jar target/profile-conflict-demo-1.0.0.jar
```

Stdout:

```text
message=QA
mode=qa
audit=false
```

Đảo thứ tự tên:

```bash
mvn clean package -P qa,dev
java -jar target/profile-conflict-demo-1.0.0.jar
```

**Stdout vẫn là:**

```text
message=QA
mode=qa
audit=false
```

Tại sao? Vì `qa` được **khai báo sau `dev` trong POM**, không phải vì thứ tự CLI. Nếu đổi chỗ hai block profile trong POM, với cùng tập active profiles kết quả có thể đổi.

### 4.9. Dev kết hợp audit

```bash
mvn clean package -P dev,audit
java -jar target/profile-conflict-demo-1.0.0.jar
```

Stdout:

```text
message=DEV
mode=dev
audit=true
```

Hai profile tác động tới các key riêng, nên cấu hình được kết hợp, không loại trừ nhau.

### 4.10. Chỉ audit: tác dụng bất ngờ của activeByDefault

```bash
mvn clean package -P audit
java -jar target/profile-conflict-demo-1.0.0.jar
```

Stdout:

```text
message=BASE
mode=base
audit=true
```

**Không phải `message=LOCAL`**: `audit` được kích hoạt đã khiến `local` activeByDefault không được áp dụng. Hai property `demo.message` và `demo.mode` trở về giá trị nền trong POM. Đây là một lý do mạnh để **không đặt toàn bộ giá trị mặc định cần thiết trong profile activeByDefault**.

### 4.11. Dev, qa, audit cùng lúc

```bash
mvn clean package -P dev,qa,audit
java -jar target/profile-conflict-demo-1.0.0.jar
```

Stdout:

```text
message=QA
mode=qa
audit=true
```

`qa` thắng trên hai key trùng với `dev`, nhưng `audit` vẫn phát huy tác dụng của nó.

### 4.12. Kích hoạt qa bằng -D trong khi dev được bật bằng -P

```bash
mvn clean package -P dev -Ddemo.target=qa
java -jar target/profile-conflict-demo-1.0.0.jar
```

Stdout:

```text
message=QA
mode=qa
audit=false
```

`qa` được bật do activation property và `dev` được bật tường minh; cả hai cùng active. Trong **cùng POM**, không có quy tắc “profile được bật qua `-P` luôn mạnh hơn profile tự kích hoạt”.

### 4.13. Override message trực tiếp khi filter resource

```bash
mvn clean package -P dev,qa -Ddemo.message=CLI
java -jar target/profile-conflict-demo-1.0.0.jar
```

Stdout:

```text
message=CLI
mode=qa
audit=false
```

Tại resource filtering, user property `-Ddemo.message=CLI` được dùng thay giá trị `QA` từ POM. Điều này **không** có nghĩa Maven tắt profile `dev` hoặc `qa`; nó chỉ thay giá trị được cung cấp cho plugin trong ngữ cảnh này.

### 4.14. Bảng kết quả toàn bộ bài thực hành

Giả định không có settings/profile môi trường bên ngoài làm thay đổi mẫu:

| Lệnh build | Active POM profiles | message | mode | audit |
| --- | --- | --- | --- | --- |
| `mvn clean package` | `local` | LOCAL | local | false |
| `mvn clean package -P dev` | `dev` | DEV | dev | false |
| `mvn clean package -P qa` | `qa` | QA | qa | false |
| `mvn clean package -P dev,qa` | `dev`, `qa` | QA | qa | false |
| `mvn clean package -P qa,dev` | `qa`, `dev` | QA | qa | false |
| `mvn clean package -P dev,audit` | `dev`, `audit` | DEV | dev | true |
| `mvn clean package -P audit` | `audit` | BASE | base | true |
| `mvn clean package -P dev,qa,audit` | `dev`, `qa`, `audit` | QA | qa | true |
| `mvn clean package -P dev -Ddemo.target=qa` | `dev`, `qa` | QA | qa | false |
| `mvn clean package -P dev,qa -Ddemo.message=CLI` | `dev`, `qa` | CLI | qa | false |

**Chú ý:** mỗi trường hợp cần chạy **lại** `mvn clean package` trước `java -jar`. JAR đã tạo không đổi thông điệp chỉ vì sau đó bạn dùng profile khác mà không build lại.

## 5. Chẩn đoán thực tế: active-profiles, effective-pom và kết quả build

### 5.1. Xem chính xác profile nào active

Dùng Maven Help Plugin:

```bash
mvn help:active-profiles
mvn help:active-profiles -P dev
mvn help:active-profiles -P dev,qa
mvn help:active-profiles -P dev -Ddemo.target=qa
```

Goal `help:active-profiles` cho biết profile active và thường kèm nguồn khai báo. Trong ví dụ, lệnh cuối phải có `dev` lẫn `qa` từ POM. **Thứ tự xuất hiện trong danh sách output không phải bằng chứng về thứ tự ưu tiên**: chỉ cho biết danh sách profile được kích hoạt.

### 5.2. Xem POM hiệu lực sau khi áp dụng profiles

```bash
mvn help:effective-pom -P dev,qa -Doutput=effective-pom.xml
```

File kết quả giúp thấy `demo.message=QA`, `demo.mode=qa`, `audit.enabled=false`, các plugins và phiên bản sau khi hợp nhất. Với plugin Help hỗ trợ, có thể dùng `-Dverbose` để gợi ý nguồn của những phần tử trong effective POM.

Để xem nhanh một property:

```bash
mvn help:evaluate -q -Dexpression=demo.message -DforceStdout -P dev,qa
```

Với POM mẫu và không override ngoài, giá trị cần thấy là `QA`. Nếu dùng CLI `-Ddemo.message=CLI`, hãy kiểm tra **cả file filtered resource**, vì chính plugin và user properties quyết định giá trị được ghi vào artifact.

### 5.3. Kiểm tra settings hiệu lực

```bash
mvn help:effective-settings
```

Cần cân nhắc thông tin nhạy cảm trong settings khi chia sẻ output. Đối chiếu user `~/.m2/settings.xml`, global settings, flags `-s` và `-gs` nếu có, cũng như Maven Wrapper/IDE/CI. Settings profile cùng ID với một POM profile có quy tắc ưu tiên riêng; **không suy diễn đơn giản theo vị trí XML giữa hai file khác nhau**.

### 5.4. Kiểm tra artifact thực tế

```bash
jar tf target/profile-conflict-demo-1.0.0.jar
java -jar target/profile-conflict-demo-1.0.0.jar
```

Archive phải có `com/example/profiledemo/Main.class`, `build-info.properties` và `META-INF/MANIFEST.MF`. Xem `target/classes/build-info.properties` trước khi đóng gói cũng giúp xác định giá trị đã filter:

```text
message=QA
mode=qa
audit=false
```

Đây là **output minh họa sau `mvn clean package -P dev,qa`**, không phải file nguồn ban đầu. Trên Windows có thể dùng `Get-Content .\target\classes\build-info.properties` trong PowerShell; trên Linux/macOS dùng `cat target/classes/build-info.properties`.

## 6. Tắt một profile đã tự active

Chỉ bỏ tên `qa` khỏi `-P` có thể không đủ nếu nó vẫn được bật nhờ `-Ddemo.target=qa`, settings hoặc điều kiện kích hoạt khác.

Chẳng hạn:

```bash
mvn help:active-profiles -P dev -Ddemo.target=qa
```

Trong ví dụ, cả `dev` và `qa` có thể active.

Maven hỗ trợ deactivate bằng tiền tố phủ định `!` hoặc `-`. Để tránh các shell hiểu `!` theo cách riêng, có thể dùng cú pháp:

```bash
mvn help:active-profiles -Ddemo.target=qa -P=-qa
```

Muốn bật `dev` đồng thời tắt `qa` trong cùng lệnh:

```bash
mvn help:active-profiles -Ddemo.target=qa -P=dev,-qa
```

Luôn dùng `help:active-profiles` để xác minh kết quả với đúng Maven version và shell của bạn. Với Maven 4, cách xử lý ID profile không tồn tại và cú pháp *optional profile* có khác Maven 3; không nên chuyển nguyên flags giữa hai version mà chưa kiểm tra tài liệu.

## 7. Settings, parent POM và multi-module làm xung đột khó nhìn hơn

### 7.1. Profiles từ settings.xml

User/global `settings.xml` cho phép các profile ảnh hưởng đến **properties** và **repositories**. Ví dụ **fragment minh họa**:

```xml
<profiles>
    <profile>
        <id>company-repo</id>
        <repositories>
            <repository>
                <id>company-artifacts</id>
                <url>https://repo.example.invalid/maven/releases</url>
            </repository>
        </repositories>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>company-repo</activeProfile>
</activeProfiles>
```

URL dùng domain ví dụ `.invalid`, không phải repository thật. Nếu settings profile này active, nó có thể đóng góp repository khi Maven resolve dependencies. Khi settings profile có **cùng ID** với POM profile, tài liệu Maven Settings Reference mô tả settings có thể ưu tiên đối với profile trùng ID. Tuy nhiên settings không có đầy đủ khả năng khai báo `build/plugins` như POM, và quy tắc merge repositories/phần tử lặp có sắc thái riêng.

**Cách xử lý đúng:** xem `help:active-profiles`, `help:effective-settings` và `help:effective-pom` cùng lúc. Không áp quy tắc “profile khai báo sau trong một POM” để phán đoán tất cả dữ liệu từ settings và POM.

### 7.2. Parent và child: định nghĩa profile không được kế thừa nguyên vẹn

Trong Maven, **tác dụng của active profiles** có thể được kế thừa như cấu hình model sau khi profile đã được áp dụng, nhưng **block định nghĩa profile** không đơn giản được chuyển nguyên từ parent xuống child. Nếu parent và child cùng có profile ID `qa`, chúng không mặc nhiên là một profile duy nhất có một activation toàn cục.

Điều này quan trọng với reactor multi-module: lệnh `mvn -P qa package` ở root có thể có tác dụng khác nhau theo POM của từng module. Khi điều tra, hãy xem **effective POM theo module**, không chỉ xem POM root.

### 7.3. Repositories và thứ tự tra cứu

Repositories đóng góp từ settings, POM, parent, profiles và mirrors tuân theo thứ tự và quy tắc ID riêng của Maven Resolver. Trong trường hợp có nhiều repositories trùng ID hoặc khác URL, không thể kết luận chỉ dựa vào “profile cuối thắng”. Xem `effective-settings`, `effective-pom` và log resolver; bảo đảm repository IDs không xung đột và mirror đúng.

### 7.4. Profile tự kích hoạt do máy build

Một developer chạy Maven bằng JDK 21, người khác bằng JDK 17; Windows/Linux cũng có thể nhận OS activation khác nhau. Có thể còn file chỉ tồn tại trên một laptop, user settings khác hoặc `.mvn/maven.config` thêm các flags. Vì vậy build cùng command “trông giống nhau” vẫn có tập active profiles khác nhau.

Cấu hình CI đáng tin cần ghi rõ Maven/JDK versions, settings/mirror hợp lệ, flags `-P/-D`, và xác nhận profile active. Không dựa vào file vô tình tồn tại trong home directory hay local repository của người phát triển.

## 8. Thiết kế profile giảm xung đột

**Nguyên tắc 1 — một môi trường tại một thời điểm.** Nếu `dev`, `qa`, `prod` cùng định nghĩa endpoint, build mode hoặc plugin khác nhau, nên xem đó là **những lựa chọn loại trừ**. Pipeline release cần kiểm tra không có `dev` và `prod` cùng active. Maven không tự chặn tổ hợp đó.

**Nguyên tắc 2 — tác vụ bổ sung nên độc lập.** `audit`, `coverage`, `integration-tests` có thể được thiết kế như các profile cộng thêm, tránh ghi đè các key xác định môi trường. Bài mẫu cho thấy `audit` kết hợp được với `dev` hoặc `qa` mà không đè message.

**Nguyên tắc 3 — có giá trị nền ngoài activeByDefault.** Đặt property bắt buộc trong `<properties>` cấp POM; nếu profile local bị tắt do bật một profile khác, build vẫn có trạng thái rõ ràng.

**Nguyên tắc 4 — không rely vào merge ngầm cho production.** Dù profile khai báo sau thắng trên scalar property, điều này không đảm bảo kết quả an toàn khi cấu hình plugin, dependency hay repository cũng mâu thuẫn. Thêm bước kiểm tra tổ hợp trong script/pipeline hoặc rules thích hợp.

**Nguyên tắc 5 — tránh secrets trong POM, CLI và filtered resources.** Credentials nên được quản lý qua CI secret store hoặc settings được bảo vệ; CLI `-Dsecret=...` có thể lộ trong process list, history/log, còn resource filtering có thể đưa secret trực tiếp vào JAR. Những giá trị thay đổi theo môi trường deploy nên cân nhắc cung cấp lúc runtime thay vì build ra nhiều artifact khác nhau.

**Nguyên tắc 6 — giữ phiên bản plugin/tool ổn định.** Ghim plugin versions, dùng Maven Wrapper/CI toolchain phù hợp và thử các tổ hợp profile được hỗ trợ. Chuyển vị trí profile trong POM là một **thay đổi behavior**, không chỉ là sắp xếp XML cho đẹp.

## 9. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `-P dev,qa` cho giá trị QA dù dev ở đầu | `qa` được khai báo sau trong POM | Xem thứ tự profile và effective POM |
| Đổi `-P dev,qa` thành `-P qa,dev` mà giá trị không đổi | Thứ tự CLI không quyết định thứ tự ưu tiên trong cùng POM | Đừng dùng đảo CLI để sửa xung đột |
| `-P audit` làm mất property LOCAL | `local` activeByDefault bị tắt | Đặt default bắt buộc ngoài profile |
| Chỉ bật dev nhưng QA cũng active | Activation theo property/settings/JDK/OS/file | `help:active-profiles` rồi loại bỏ trigger |
| Resource trong JAR không theo POM như dự đoán | User property `-D`, filter bổ sung, build cũ | Kiểm tra flags và `target/classes/*.properties` |
| Plugin chạy hai lần hoặc goal chạy ngoài ý muốn | Merge plugin executions, ID/phase khác nhau | Đọc effective POM và log goal |
| Test bị skip ở môi trường không mong muốn | Profiles cùng chỉnh Surefire/Failsafe config | Kiểm tra `skipTests`, `maven.test.skip`, executions |
| Hai máy build khác nhau | Settings, Maven/JDK, profile tự kích hoạt khác nhau | So sánh active profiles và effective settings |
| Dependency được tải từ repo lạ | Repository profile hoặc mirror có hiệu lực | Kiểm tra repositories, IDs, mirror, resolver log |
| Child module khác root mặc dù cùng `-P qa` | Profile definitions và inheritance theo từng POM | Xem effective POM riêng cho mỗi module |
| `mvn validate` thành công nhưng artifact sai | Phase validate chưa chạy resource/package | Chạy `clean package` hoặc `clean verify` và đọc artifact |
| Profile cùng ID giữa POM và settings cho kết quả khó hiểu | Quy tắc ưu tiên nguồn và phạm vi khác nhau | Kiểm tra cả settings và POM effective |
| Tắt QA khỏi `-P` nhưng QA vẫn chạy | QA đang active bằng điều kiện khác | Dùng deactivate tường minh, kiểm tra với Help Plugin |

## 10. Tự kiểm tra kiến thức

**Câu 1:** `dev` được khai báo trước `qa` trong cùng POM, cả hai cùng đặt `app.message`. Lệnh `-P qa,dev` cho giá trị nào?  
**Đáp án:** `QA` (nếu không có override khác), vì `qa` được khai báo sau; thứ tự CLI không làm `dev` thắng.

**Câu 2:** POM có `local` activeByDefault và `audit` chỉ định một property khác. Vì sao `-P audit` có thể khiến message đổi từ LOCAL sang BASE?  
**Đáp án:** `audit` active làm `local` activeByDefault tắt. Property quay về giá trị nền ngoài profiles.

**Câu 3:** `dev` và `audit` có các key khác nhau; Maven chỉ chọn một profile?  
**Đáp án:** Không. Tác dụng của cả hai có thể cùng có mặt trong effective model.

**Câu 4:** `qa` active qua `-Ddemo.target=qa` và bạn chạy thêm `-P dev`. QA có tự tắt?  
**Đáp án:** Không. Cả hai có thể active; phải kiểm tra `help:active-profiles`.

**Câu 5:** Hai profiles định nghĩa hai plugins khác nhau, profile sau có xóa plugin của profile trước?  
**Đáp án:** Không thể suy ra như vậy. Build/plugin lists được merge theo cấu trúc model, không chỉ last-wins toàn bộ.

**Câu 6:** `-Ddemo.message=CLI` trong ví dụ thì stdout của JAR sau build là gì ở dòng message?  
**Đáp án:** `message=CLI` do Maven Resources Plugin dùng user property khi filter.

**Câu 7:** Có thể suy ra toàn bộ thứ tự plugin goals chỉ từ `help:active-profiles` không?  
**Đáp án:** Không. Cần effective POM và log build; danh sách active profiles không phải lịch goal.

**Câu 8:** Parent và child đều có profile tên QA; định nghĩa profile có tự kế thừa nguyên vẹn?  
**Đáp án:** Không. Tác dụng profile đã active có thể được kế thừa vào model, nhưng định nghĩa và activation không tự thành một profile toàn cục.

**Câu 9:** Máy bạn và CI dùng cùng `-P qa` nhưng output khác nhau. Cần xem gì?  
**Đáp án:** Settings, implicit activation, flags từ IDE/`.mvn/maven.config`, JDK/Maven versions, parent profiles và filtered artifact.

**Câu 10:** Có thể chỉ sắp xếp profile `prod` ở cuối POM để bảo đảm không ai build `dev,prod` sai không?  
**Đáp án:** Không. Cần quy tắc pipeline kiểm tra lựa chọn môi trường; quy tắc merge không thay thế việc bảo vệ build release.

## 11. Checklist thực hành và vận hành

1. Xác định profile **môi trường loại trừ** và profile **chức năng cộng thêm**, đặt ID dễ hiểu.
2. Đặt properties bắt buộc ở cấp POM ngoài profiles hoặc định nghĩa yêu cầu cấu hình rõ.
3. Không xem `activeByDefault` là luôn active; thử cả trường hợp chỉ bật profile phụ.
4. Với property trùng trong cùng POM, kiểm tra **thứ tự khai báo XML**; không dựa vào thứ tự `-P`.
5. Với plugin/dependency/repository, kiểm tra **merge model** và output thay vì áp quy tắc scalar cho mọi cấu trúc.
6. Chạy `help:active-profiles` và `help:effective-pom` bằng **cùng tập flags** như build.
7. Xác minh `settings.xml`, Maven/JDK versions và profile activation từ CI/IDE khi kết quả khác nhau.
8. Chạy `mvn clean verify` với tổ hợp profile được hỗ trợ; đọc artifact/test results.
9. Không đưa secrets vào POM, CLI công khai hoặc filtered resource.
10. Với release, chặn tổ hợp profile môi trường mâu thuẫn và ghi nhận configuration dùng để tạo artifact.

## 12. Tài liệu chính thức

- [Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
