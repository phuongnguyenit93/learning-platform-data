# Phân biệt JAR, WAR và POM ở cấp mô hình dự án Maven

## 1. Ba giá trị packaging nói lên điều gì?

Trong một dự án Maven, tệp `pom.xml` mô tả **mô hình dự án**: tọa độ (`groupId`, `artifactId`, `version`), dependency, plugin, cấu hình build và cách đóng gói. Phần tử `<packaging>` là một lựa chọn quan trọng: nó quyết định **loại artifact chính** của dự án và các **plugin goal được Maven gắn mặc định vào từng pha build**.

Ba loại thường gặp:

| `<packaging>` | Artifact chính thường thu được | Mục đích tiêu biểu | Goal tại pha `package` theo binding mặc định |
| --- | --- | --- | --- |
| `jar` | `<artifactId>-<version>.jar` | Thư viện Java, ứng dụng Java hoặc module chứa lớp và tài nguyên | `jar:jar` |
| `war` | `<artifactId>-<version>.war` | Ứng dụng web theo mô hình Servlet, thường triển khai lên servlet container | `war:war` |
| `pom` | Tài liệu mô hình POM (artifact dạng `.pom` khi cài đặt/phát hành) | Parent POM, aggregator nhiều module, BOM hoặc dự án cung cấp metadata | Không có goal tạo JAR/WAR mặc định ở `package` |

**Cần phân biệt ba khái niệm:** (1) `pom.xml` là **tệp cấu hình** mà mọi dự án Maven đều cần; (2) `<packaging>pom</packaging>` là **kiểu đóng gói của chính dự án**; (3) artifact `.pom` là **mô hình dự án được lưu vào Maven repository** khi cài đặt hoặc phát hành. Tên giống nhau nhưng vai trò khác nhau.

Nếu không khai báo `<packaging>`, Maven mặc định dùng **`jar`**. Việc đổi `packaging` không đơn thuần là đổi đuôi tệp: nó làm thay đổi các goal mặc định của lifecycle và cách thu gom nội dung để đóng gói.

## 2. `packaging` gắn với tọa độ artifact như thế nào?

Một dự án tối thiểu có thể khai báo:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.acme</groupId>
    <artifactId>catalog-core</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
</project>
```

`groupId:artifactId:version` là ba thành phần tọa độ cơ bản xác định dự án, ở ví dụ là `dev.acme:catalog-core:1.0.0`. `packaging` mô tả **dạng artifact**, thường ảnh hưởng tới phần mở rộng của artifact chính. Các dependency còn có `type`, `classifier` và scope khi cần phân biệt variant; với dependency Java bình thường, Maven giả định `type=jar`.

Giữ nguyên `groupId`, `artifactId`, `version` nhưng đổi từ `jar` sang `war` sẽ khiến `mvn package` hướng tới tạo `catalog-core-1.0.0.war` theo cách đóng gói web. Đây là **thay đổi mô hình dự án**, không phải thao tác an toàn chỉ vì tên tệp đầu ra khác. Bạn phải kiểm tra cấu trúc nguồn, dependency và plugin phù hợp với loại mới.

Tên file artifact theo mặc định dựa trên `artifactId` và `version`; `finalName`/plugin configuration có thể đổi tên file trong `target/`, nhưng không tự đổi tọa độ dependency. Không lấy tên file trên ổ đĩa làm nguồn duy nhất để suy ra GAV.

## 3. JAR: module Java và thư viện

**JAR (Java ARchive)** là tệp ZIP theo quy ước Java, thường gồm `.class` và tài nguyên. Với `packaging=jar`, Maven mặc định gắn `maven-jar-plugin:jar` vào pha `package`. Tệp thường nằm ở `target/<artifactId>-<version>.jar`.

Cấu trúc dự án JAR điển hình:

```text
catalog-core/
├── pom.xml
└── src/
    └── main/
        ├── java/dev/acme/catalog/Greeter.java
        └── resources/application.properties
```

Đoạn `pom.xml` thể hiện ý chính:

```xml
<groupId>dev.acme</groupId>
<artifactId>catalog-core</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
```

Đoạn trên **chỉ là một phần bên trong `<project>`**, không phải tệp POM XML độc lập; hãy đặt nó vào cấu trúc POM đầy đủ như ở mục 2.

Ví dụ Java 17, tệp `src/main/java/dev/acme/catalog/Greeter.java`:

```java
package dev.acme.catalog;

public final class Greeter {
    private Greeter() {
    }

    public static String greeting() {
        return "Hello from JAR";
    }

    public static void main(String[] args) {
        System.out.println(greeting());
    }
}
```

Để biên dịch trên Java 17, hãy chọn một phiên bản Maven Compiler Plugin hỗ trợ `release=17` và đặt `maven.compiler.release=17` trong `<properties>`. Một phần cấu hình phù hợp là:

```xml
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
```

Đây cũng là **đoạn nằm trong `<project>`**. Khi dự án đã có cấu hình Java và plugin thích hợp, chạy từ thư mục chứa POM:

```bash
mvn -B -ntp clean package
java -cp target/catalog-core-1.0.0.jar dev.acme.catalog.Greeter
```

Chương trình in:

```text
Hello from JAR
```

`java -cp` hoạt động với JAR ví dụ vì lớp `Greeter` có `main` và không cần dependency bên ngoài. **Không phải mọi JAR đều chạy được bằng `java -jar`**: lệnh đó cần `Main-Class` phù hợp trong manifest (hoặc cơ chế đóng gói chuyên biệt). Một JAR thư viện thông thường không cần `main`. JAR mặc định cũng không tự gom toàn bộ dependency bên ngoài vào một “fat JAR”; nếu muốn tạo executable/uber JAR cần cấu hình tương ứng (ví dụ plugin đóng gói hoặc repackage).

**Khi chọn `jar`?** Khi module cung cấp mã Java dùng lại, thư viện API/logic, thành phần hạ tầng hoặc ứng dụng Java có cách khởi động phù hợp. Dùng `jar` không buộc dự án phải là ứng dụng dòng lệnh; nó là loại artifact, không phải “kiểu giao diện”.

## 4. WAR: gói ứng dụng web cho servlet container

**WAR (Web Application Archive)** là tệp đóng gói ứng dụng web Java theo cấu trúc mà servlet container hiểu. Với `packaging=war`, Maven gắn goal `maven-war-plugin:war` vào pha `package` theo mặc định. Ứng dụng web truyền thống triển khai WAR lên servlet container tương thích như Tomcat.

Dự án web có thể có cấu trúc:

```text
catalog-web/
├── pom.xml
└── src/
    └── main/
        ├── java/                  # Servlet/controller nếu có
        ├── resources/             # Tài nguyên của classpath
        └── webapp/
            ├── index.html         # Ví dụ trang tĩnh
            └── WEB-INF/           # Có thể chứa web.xml, tùy ứng dụng
```

WAR sau khi build có các vị trí đặc trưng:

```text
catalog-web-1.0.0.war
├── index.html
└── WEB-INF/
    ├── classes/                   # Lớp đã biên dịch và tài nguyên classpath, nếu có
    └── lib/                       # Các JAR dependency cần đóng gói, nếu có
```

Nội dung thực tế phụ thuộc nguồn và dependency; các thư mục không có file có thể không xuất hiện. `src/main/webapp` cung cấp tài nguyên web (HTML, JSP, CSS, ảnh...), còn `src/main/java` là nguồn Java nếu ứng dụng có Servlet hoặc mã web. WAR thường đặt dependency ở `WEB-INF/lib`, trong khi các API do container cung cấp thường được khai báo scope `provided` để tránh đóng bản trùng.

Mẫu `pom.xml` đầy đủ cho ứng dụng web **chỉ có một trang tĩnh** (đủ để học cách đóng WAR; không cần biên dịch Servlet):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.acme</groupId>
    <artifactId>catalog-web</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo tệp `src/main/webapp/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <title>Catalog Web</title>
</head>
<body>
    <h1>Chào từ WAR</h1>
</body>
</html>
```

Chạy:

```bash
mvn -B -ntp clean package
```

Với cấu hình trên và Maven tương thích (Maven 3.6.3+ đáp ứng yêu cầu của Maven WAR Plugin 3.5.1), kỳ vọng tạo `target/catalog-web-1.0.0.war`. Có thể xem nội dung bằng `jar tf target/catalog-web-1.0.0.war`; tên entry sẽ phản ánh cấu trúc webapp. Không có lệnh `java` chạy class nào trong ví dụ này vì ứng dụng chỉ chứa một trang HTML.

**Lưu ý:** `<failOnMissingWebXml>false</failOnMissingWebXml>` cho phép ví dụ đóng gói khi không có `WEB-INF/web.xml`; ứng dụng thực tế phải đáp ứng hợp đồng triển khai của Servlet/container và framework đang dùng. Bản WAR thông thường **không mặc nhiên là executable JAR**. Một số framework như Spring Boot có thể tạo WAR có thể thực thi riêng khi cấu hình plugin/phần khởi động thích hợp, nhưng đó là trường hợp bổ sung, không phải hành vi mặc định của `packaging=war`.

**Khi chọn `war`?** Khi sản phẩm là ứng dụng web theo mô hình Servlet và hạ tầng triển khai cần artifact WAR. Với dịch vụ chạy bằng embedded server, dự án có thể chọn JAR hoặc WAR tùy chiến lược triển khai; không suy ra “web app bắt buộc là WAR”.

## 5. POM: mô hình, parent và aggregator thay vì binary ứng dụng

**POM** là viết tắt của *Project Object Model*. Mọi dự án Maven đều có POM, thường ở `pom.xml`; nhưng một dự án với `<packaging>pom</packaging>` có **vai trò chính là cung cấp metadata/cấu hình**, chẳng hạn:

- **Parent POM:** cung cấp cấu hình hoặc version dùng chung để các POM con kế thừa qua phần tử `<parent>`.
- **Aggregator:** khai báo `<modules>` để Maven Reactor thu thập và build nhiều module trong một lần chạy.
- **BOM:** dự án POM mô tả danh sách phiên bản dependency thống nhất trong `<dependencyManagement>`, có thể được import bằng dependency `type=pom`, `scope=import` tại `<dependencyManagement>`.

Tại pha `package`, loại `pom` **không có goal JAR/WAR mặc định**. Lệnh `mvn package` trên một POM chỉ đóng vai trò parent/metadata không tự tạo `target/*.jar` hay `target/*.war` cho chính project đó. Khi `mvn install` hoặc `mvn deploy`, mô hình POM có thể được cài vào repository cục bộ hoặc phát hành lên repository từ xa dưới artifact có phần mở rộng `.pom`.

Một POM con vẫn có `pom.xml` dù `packaging` của con là `jar` hoặc `war`. Vì vậy, **POM không đối lập với việc có POM**: sự so sánh ở đây là **ba loại packaging** `jar`, `war`, `pom`.

### Parent và aggregator là hai vai trò khác nhau

- **Kế thừa (inheritance):** POM con khai báo `<parent>`, nhận thông tin/cấu hình được phép kế thừa như version, properties, dependency management, plugin management. Chỉ khai báo parent **không tự** buộc Maven build tất cả module.
- **Tổng hợp (aggregation):** POM aggregator khai báo `<modules>`, giúp lệnh chạy ở gốc kích hoạt build các module được liệt kê. Chỉ khai báo modules **không có nghĩa** mọi module phải kế thừa cấu hình từ POM đó.

Một POM gốc thường đảm nhiệm **cả hai vai trò**. Tuy nhiên, chúng không đồng nghĩa: có thể có parent bên ngoài reactor; cũng có thể aggregator liệt kê các module có parent khác. Đừng nhìn `<packaging>pom</packaging>` rồi mặc định chắc chắn phải có `<modules>`.

## 6. Ví dụ đầy đủ: một POM gốc, một module JAR và một module WAR

Ví dụ này minh họa **ba loại packaging trong cùng một Maven Reactor**. Cây thư mục:

```text
training-suite/
├── pom.xml
├── toolkit/
│   ├── pom.xml
│   └── src/main/java/dev/acme/Greeter.java
└── website/
    ├── pom.xml
    └── src/main/webapp/index.html
```

### 6.1. `training-suite/pom.xml`: gốc `pom`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.acme</groupId>
    <artifactId>training-suite</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>toolkit</module>
        <module>website</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

POM này nhận nhiệm vụ điều phối các module và cung cấp properties cho các POM con khai báo `<parent>`. `maven.compiler.release` sẽ hữu ích khi plugin compiler có phiên bản hỗ trợ `release`. **Bản thân** `training-suite` không đóng gói Java archive ở pha `package`.

### 6.2. `toolkit/pom.xml`: module `jar`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.acme</groupId>
        <artifactId>training-suite</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>toolkit</artifactId>
    <packaging>jar</packaging>

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
```

Module con kế thừa `groupId`, `version` và `properties` từ parent (vì không khai báo lại hai tọa độ đó). Tạo `toolkit/src/main/java/dev/acme/Greeter.java`:

```java
package dev.acme;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from toolkit";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Khi chạy `package`, module tạo `toolkit/target/toolkit-1.0.0.jar`. Lớp Java 17 trên chạy được bằng `java -cp toolkit/target/toolkit-1.0.0.jar dev.acme.Greeter`.

### 6.3. `website/pom.xml`: module `war`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.acme</groupId>
        <artifactId>training-suite</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>website</artifactId>
    <packaging>war</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.acme</groupId>
            <artifactId>toolkit</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `website/src/main/webapp/index.html`:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Website</title></head>
<body><h1>Trang web demo</h1></body>
</html>
```

Từ **thư mục gốc `training-suite`**, chạy:

```bash
mvn -B -ntp clean package
```

Maven Reactor tự xác định thứ tự thỏa quan hệ dependency: `toolkit` cần được build trước `website` vì `website` khai báo dependency vào `toolkit`. Kết quả dự kiến:

```text
training-suite/pom.xml
toolkit/target/toolkit-1.0.0.jar
website/target/website-1.0.0.war
```

`training-suite/pom.xml` là **tệp mô hình** của module gốc, không phải artifact JAR/WAR được tạo trong `target/`. Với Maven `install`, POM gốc và các module được cài vào local repository theo tọa độ của từng project, ví dụ POM gốc là `~/.m2/repository/dev/acme/training-suite/1.0.0/training-suite-1.0.0.pom`.

Bởi `website` phụ thuộc `toolkit` theo scope mặc định `compile`, WAR sẽ thường chứa JAR đó trong `WEB-INF/lib/toolkit-1.0.0.jar`. Thay đổi scope (như `provided`) hoặc cấu hình WAR Plugin có thể thay đổi thành phần được đóng vào WAR.

Chạy chương trình Java minh họa từ thư mục gốc sau khi build:

```bash
java -cp toolkit/target/toolkit-1.0.0.jar dev.acme.Greeter
```

**Stdout chính xác:**

```text
Hello from toolkit
```

Lệnh trên chạy lớp `Greeter` trong JAR; nó **không** chạy servlet container hay mở WAR. Để mở website thực sự, cần triển khai `website-1.0.0.war` trên servlet container phù hợp.

**Tự kiểm chứng kết quả:** tại gốc dự án, dùng `jar tf toolkit/target/toolkit-1.0.0.jar` để thấy `dev/acme/Greeter.class`; dùng `jar tf website/target/website-1.0.0.war` để thấy `index.html` và `WEB-INF/lib/toolkit-1.0.0.jar`. `jar tf` có trong công cụ JDK, chỉ liệt kê nội dung archive chứ không chạy ứng dụng.

## 7. Packaging điều khiển lifecycle, không thay thế dependency và plugin configuration

Tất cả các dự án Maven đều có vòng đời `clean`, `default` và `site`, nhưng **goal được gắn mặc định vào các pha của `default` phụ thuộc `packaging`**. Theo binding chuẩn:

| Pha | `jar` | `war` | `pom` |
| --- | --- | --- | --- |
| `compile` | `compiler:compile` | `compiler:compile` | Không có goal compile mặc định |
| `test` | `surefire:test` | `surefire:test` | Không có goal test mặc định |
| `package` | `jar:jar` | `war:war` | Không có goal đóng gói mặc định |
| `install` | `install:install` | `install:install` | `install:install` cho POM |
| `deploy` | `deploy:deploy` | `deploy:deploy` | `deploy:deploy` cho POM |

Các goal về resources và test compilation vẫn được gắn vào những pha khác đối với JAR/WAR. Plugin và execution do người dùng thêm vào POM có thể **bổ sung hoặc thay đổi hành vi** nên bảng mô tả *mặc định*, không phải quy tắc cấm các project `pom` thực hiện bất kỳ goal nào.

- `mvn package` chạy tới pha `package`, gồm các pha trước đó; `mvn install` đi xa hơn và đưa artifact/POM vào local Maven repository.
- `mvn deploy` nhằm phát hành lên repository từ xa đã cấu hình; khác với triển khai WAR lên servlet container. Từ **deploy** trong Maven lifecycle không có nghĩa “khởi động trang web”.
- `mvn -N package` từ gốc multi-module chạy **chỉ project gốc**; nếu gốc có `packaging=pom`, bạn có thể thấy `BUILD SUCCESS` mà không có JAR/WAR của các module, vì `-N` tắt đệ quy vào module.
- Có thể gọi trực tiếp goal như `mvn jar:jar`, nhưng goal đó không thay thế mọi pha chuẩn bị của `package`. Học `mvn package` trước để Maven chạy lifecycle đúng thứ tự.

Quan hệ **dependency** cũng cần hiểu độc lập với packaging: một dự án `war` có thể phụ thuộc vào `jar`; một project `jar` có thể là thư viện cho nhiều module; một POM dạng BOM cung cấp phiên bản quản lý nhưng **không được đưa vào runtime classpath như JAR**. Một ứng dụng web có thể chạy theo mô hình JAR có embedded server, nên loại đóng gói không tự quyết định toàn bộ kiến trúc triển khai.

## 8. Những nhầm lẫn phổ biến

**Nhầm 1 — “Dự án có `pom.xml` thì packaging là `pom`.”** Sai. Mọi Maven project có POM; nếu không ghi `<packaging>` thì mặc định là `jar`.

**Nhầm 2 — “Chọn `war` chỉ cần đổi tên `.jar` thành `.war`.”** Sai. WAR có cấu trúc triển khai web và goal đóng gói riêng. Đổi phần mở rộng file không tạo đúng `WEB-INF/classes`, `WEB-INF/lib` hay web resources.

**Nhầm 3 — “JAR luôn chạy được với `java -jar`.”** Sai. JAR thư viện không cần main class; executable JAR đòi manifest/cơ chế khởi động phù hợp và đôi khi cách đóng dependency riêng.

**Nhầm 4 — “WAR luôn cần server cài ngoài, JAR không thể là ứng dụng web.”** Quá tuyệt đối. WAR truyền thống thường triển khai lên servlet container; framework hiện đại có thể tạo JAR với embedded web server hoặc WAR thực thi được theo cấu hình. Phân biệt theo yêu cầu triển khai và plugin thực tế.

**Nhầm 5 — “`packaging=pom` tạo một JAR rỗng cho parent.”** Sai theo mặc định. Parent POM cung cấp metadata; khi `install`, Maven lưu POM vào repository với phần mở rộng `.pom`, không sinh `.jar` mặc định.

**Nhầm 6 — “Khai báo `<modules>` đồng nghĩa các module đều kế thừa parent.”** Sai. Aggregation qua `<modules>` và inheritance qua `<parent>` là hai quan hệ độc lập. Ví dụ ở mục 6 sử dụng cả hai.

**Nhầm 7 — “Maven `deploy` sẽ deploy WAR lên Tomcat.”** Sai. Pha `deploy` của Maven thông thường đưa artifact lên **artifact repository**; triển khai ứng dụng lên container là bước riêng theo hạ tầng/plugin.

**Nhầm 8 — “Cứ `BUILD SUCCESS` ở POM gốc là tất cả module được đóng gói.”** Chưa chắc. Kiểm tra lệnh có `-N` không, danh sách module được Reactor chọn, và báo cáo `Reactor Summary` của từng module. Nếu chạy ở gốc đúng reactor mà có lỗi module thì thường toàn lượt build thất bại, nhưng `BUILD SUCCESS` chỉ phản ánh tập project/goal đã thực sự chạy.

## 9. Chọn loại packaging khi thiết kế dự án

| Câu hỏi thiết kế | Chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Module cung cấp lớp Java/tài nguyên cho module khác? | `jar` | JAR phù hợp sử dụng làm dependency. |
| Ứng dụng web cần triển khai như một servlet web application archive? | `war` | WAR mang bố cục webapp và dependency theo hợp đồng của container. |
| Muốn định nghĩa dependency/plugin/version chung cho nhiều module? | `pom` cho parent | Các POM con có thể kế thừa cấu hình qua `<parent>`. |
| Muốn một lệnh build toàn bộ module theo thứ tự dependency? | `pom` cho aggregator + `<modules>` | Reactor thu thập và sắp thứ tự build. |
| Muốn công bố danh mục phiên bản dependency cho nhiều dự án? | `pom` cho BOM | Cung cấp metadata trong `dependencyManagement`; không phải binary runtime. |
| Muốn chạy web service với embedded server? | Phụ thuộc plugin/framework và môi trường | Nhiều dự án chọn executable JAR; cũng có cấu hình executable WAR. |

Nên bắt đầu từ **vai trò của module và cách hệ thống phân phối/triển khai sản phẩm**, sau đó mới chọn `packaging`, cấu hình plugin, dependency và cấu trúc nguồn. Trong dự án nhiều module, gốc `pom`, thư viện `jar`, ứng dụng web `war` là một bố cục phổ biến, nhưng không bắt buộc cho mọi hệ thống.

## 10. Câu hỏi tự kiểm tra

1. **POM không khai báo `<packaging>`.** Maven chọn loại nào? **`jar`** theo mặc định.
2. **Dự án `catalog-web` khai báo `<packaging>war</packaging>`.** Pha `package` mặc định gọi goal nào? **`war:war`**.
3. **Một POM gốc có `<packaging>pom</packaging>` và `<modules>`.** Gốc có tự sinh `target/*.jar` không? **Không theo binding mặc định**; các module con có thể tự sinh artifact riêng.
4. **Module A dùng `<parent>`, nhưng không có trong `<modules>` của parent.** Chỉ build từ parent có tự build A không? **Không chỉ vì inheritance**. Phải được chọn vào reactor hoặc build riêng.
5. **Một JAR thư viện thiếu `Main-Class`.** Có phải artifact lỗi? **Không**; thư viện không bắt buộc khởi chạy bằng `java -jar`.
6. **`mvn install` ở parent packaging `pom` đưa gì vào local repo?** **POM artifact** của parent và artifact của các module được build nếu reactor bao gồm chúng.
7. **Chạy `mvn -N package` từ gốc multi-module và thấy SUCCESS nhưng không có WAR.** Vì sao? **`-N` không đi vào module**; project gốc `pom` không có goal đóng WAR mặc định.
8. **Một ứng dụng Spring Boot có thể chạy như executable JAR dù phục vụ HTTP không?** **Có** khi plugin/khởi động embedded server được cấu hình; loại artifact và kiến trúc chạy được xác định bởi cấu hình thực tế.

## Tài liệu chính thức để đối chiếu

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): packaging mặc định, các goal được bind vào lifecycle của `jar`, `war`, `pom`.
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): Project Object Model, parent inheritance và aggregation.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): Reactor, thứ tự build và tùy chọn `-N`, `-pl`.
- [Apache Maven WAR Plugin — Usage](https://maven.apache.org/plugins/maven-war-plugin/usage.html): `war:war`, cấu trúc webapp và cách đóng gói WAR.
- [Apache Maven WAR Plugin — Goal war:war](https://maven.apache.org/plugins/maven-war-plugin/war-mojo.html): tham số và quy ước của WAR Plugin.

**Điểm cần nhớ:** `<packaging>` thuộc về **mô hình Maven của từng project**: `jar` đóng gói mã/tài nguyên Java, `war` đóng gói ứng dụng web Servlet, còn `pom` cung cấp mô hình và điều phối/cấu hình. Cả ba vẫn dùng `pom.xml`; mục đích của module và các goal được bind vào lifecycle mới quyết định sản phẩm của lần build.
