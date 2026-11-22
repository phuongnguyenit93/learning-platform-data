# Đọc effective-pom, effective-settings và các thuộc tính đã nội suy trong Maven/Spring Boot

## 1. Vì sao phải đọc cấu hình Maven đã được tính toán?

File `pom.xml` của dự án Spring Boot thường chỉ khai báo một phần cấu hình. Maven còn sử dụng **Super POM**, POM cha (parent), các `dependencyManagement`/BOM, plugin management, profile đang bật, thuộc tính được truyền trên dòng lệnh và cấu hình máy trong `settings.xml`. Bởi vậy, nhìn riêng file POM của module có thể không trả lời được:

- Tại sao `spring-boot-starter-web` không ghi phiên bản mà Maven vẫn chọn được phiên bản?
- Tại sao bản Maven Compiler Plugin hoặc mức Java khác điều mình tưởng?
- Vì sao máy A dùng mirror/repository khác máy B dù `pom.xml` giống nhau?
- Tại sao chạy `-Pprod` lại làm artifact được đặt tên khác?
- Giá trị thực tế của `${project.version}`, `${java.version}`, một property do profile định nghĩa, hoặc biến môi trường là gì?

**Apache Maven Help Plugin** có ba công cụ bổ sung cho nhau:

| Goal | Giải đáp | Nội dung chính |
|---|---|---|
| `help:effective-pom` | “Maven thấy mô hình dự án cuối cùng là gì?” | POM đã kết hợp inheritance, cấu hình và các profile hoạt động |
| `help:effective-settings` | “Maven đang dùng cấu hình máy/người dùng nào?” | Settings kết hợp global/user, mirrors, servers, profiles, local repository... |
| `help:evaluate` | “Một biểu thức/property được Maven đánh giá thành gì?” | Giá trị một biểu thức, tiện kiểm tra hoặc dùng trong script |

Dùng thêm `help:active-profiles` để biết **profile Maven** nào đang bật; dùng `dependency:tree` để biết **dependency thực tế sau resolution**. Effective POM **không phải** toàn bộ dependency tree, cũng không bảo đảm hiển thị mọi giá trị chỉ được plugin đánh giá khi goal thực thi.

## 2. POM gốc, effective POM và settings khác nhau như thế nào?

```text
                  Super POM của Maven
                            |
                    Parent POM (có thể nhiều cấp)
                            |
                POM của module đang xét
                            |
             + Các Maven profile đang active
             + Property/interpolation áp dụng
             + Dependency/plugin management
                            |
                            v
                  EFFECTIVE POM
                   (mô hình dự án)

  Global settings.xml + User settings.xml
                 + Maven settings profiles
                            |
                            v
                EFFECTIVE SETTINGS
           (cấu hình môi trường Maven)

  effective model + CLI -D + môi trường + plugin
                            |
                            v
       Giá trị biểu thức / cách goal chạy thực tế
```

**POM** là cấu hình thuộc dự án, nên thường được lưu trong Git. **`settings.xml`** thường là cấu hình của môi trường hoặc người dùng: mirror, proxy, repository, server credential và những profile settings hợp lệ. Các phần từ settings có thể **ảnh hưởng đến quá trình build**, nhưng không biến tất cả các mục `<servers>` hoặc `<mirrors>` thành phần tử trong effective POM.

Thông thường:

- Global settings: `${maven.home}/conf/settings.xml` (trong bản Maven distribution đang sử dụng).
- User settings: `${user.home}/.m2/settings.xml` (Linux/macOS thường là `~/.m2/settings.xml`, Windows thường dưới `%USERPROFILE%\.m2\settings.xml`).
- User settings có ưu tiên khi có cấu hình trùng với global settings, theo quy tắc hợp nhất của Maven.
- Maven Wrapper (`mvnw`/`mvnw.cmd`) chọn bản Maven của dự án; Help Plugin vẫn đọc POM và settings của lần gọi Maven đó.

Lưu ý: **Spring profile** (`spring.profiles.active`) quyết định cấu hình **ứng dụng Spring chạy ở runtime**. **Maven build profile** (`-Pprod`) thay đổi **mô hình build**. Hai hệ profile độc lập, trừ khi bạn chủ động cấu hình cách truyền thông tin từ build sang runtime.

## 3. Lệnh đọc nhanh trên Linux/macOS và Windows

Chạy tại thư mục dự án chứa `pom.xml` và Maven Wrapper. Trên Linux/macOS:

```bash
# POM cuối cùng sau inheritance và Maven profiles
./mvnw help:effective-pom

# Ghi ra file để dễ tìm kiếm/đối chiếu (file đặt tại thư mục hiện tại)
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Kèm bình luận gợi ý nguồn gốc từng phần tử (Help Plugin hiện hành)
./mvnw help:effective-pom -Dverbose -Doutput=effective-pom.xml

# Cấu hình settings hiệu lực
./mvnw help:effective-settings -Doutput=effective-settings.xml

# Profile đang hoạt động
./mvnw help:active-profiles

# Đọc đúng một giá trị
./mvnw -q help:evaluate -Dexpression=project.version -DforceStdout
```

Windows PowerShell dùng script `mvnw.cmd`:

```powershell
.\mvnw.cmd help:effective-pom -Doutput=effective-pom.xml
.\mvnw.cmd help:effective-pom -Dverbose -Doutput=effective-pom.xml
.\mvnw.cmd help:effective-settings -Doutput=effective-settings.xml
.\mvnw.cmd help:active-profiles
.\mvnw.cmd -q help:evaluate -Dexpression=project.version -DforceStdout
```

Trên Command Prompt, dùng `mvnw.cmd`; nếu dự án không có Wrapper và Maven đã được cài, dùng `mvn`. Các lệnh dùng `help:...` có thể cần tải Maven Help Plugin và các POM/metadata liên quan lần đầu.

**Giải thích những cờ chính:**

| Cờ | Công dụng |
|---|---|
| `-Doutput=effective-pom.xml` | Ghi kết quả help goal ra file XML thay vì in toàn bộ ra terminal |
| `-Dverbose` | Với `help:effective-pom`, thêm XML comments mô tả xuất xứ cấu hình; được hỗ trợ từ Maven Help Plugin 3.2.0 |
| `-Dexpression=project.version` | Chọn biểu thức Maven cần đánh giá; **không thêm** `${...}` ở giá trị tham số |
| `-q` | Quiet: ẩn đa số log Maven |
| `-DforceStdout` | Cho `help:evaluate` in giá trị ngay cả khi dùng `-q`; hữu ích cho CI/script |
| `-Pprod` | Kích hoạt **Maven build profile** tên `prod` |
| `-Dkey=value` | Truyền user property cho Maven của lần chạy đó |
| `-s path/to/settings.xml` | Chỉ định user settings thay cho vị trí mặc định |
| `-gs path/to/global-settings.xml` | Chỉ định global settings thay cho mặc định |

Nếu muốn ổn định phiên bản chính **Maven Help Plugin**, có thể gọi goal theo tọa độ đầy đủ. Ví dụ:

```bash
./mvnw org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose -Doutput=effective-pom.xml
```

Maven Help Plugin `3.5.2` là phiên bản cụ thể dùng để minh họa cú pháp; lựa chọn phiên bản thực tế phải tương thích Maven/JDK và quy ước build. Khi gọi shorthand `help:effective-pom`, phiên bản plugin được giải quyết theo cấu hình dự án/repository nên không nên tự giả định giống nhau ở mọi môi trường.

## 4. Ví dụ Spring Boot 3.x: parent, profile và property nội suy

Ví dụ hoàn chỉnh sau sử dụng **Java 17**, **Spring Boot 3.5.0** làm phiên bản minh họa đã pin và Maven Wrapper hoặc Maven có sẵn. Không dùng ví dụ này để khẳng định Spring Boot 3.5.0 là bản mới nhất.

Tạo `pom.xml` trong thư mục root:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-service</artifactId>
    <version>0.1.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <finalName>demo-service-${build.channel}</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
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
                <build.channel>local</build.channel>
            </properties>
        </profile>
        <profile>
            <id>prod</id>
            <properties>
                <build.channel>prod</build.channel>
            </properties>
        </profile>
    </profiles>
</project>
```

Tạo file `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Đây là một ứng dụng Spring Boot **không có starter web**; khi chạy không mặc định mở HTTP endpoint. Vì có Spring Boot parent và đã khai báo Spring Boot Maven Plugin, `package` chạy goal `repackage` theo cấu hình parent, tạo executable JAR. Khởi động ứng dụng có log thay đổi theo môi trường, nên không giả định stdout cố định.

### 4.1. Trường hợp mặc định: profile `local`

Tại root dự án, chạy:

```bash
./mvnw help:active-profiles
./mvnw -q help:evaluate -Dexpression=project.version -DforceStdout
./mvnw -q help:evaluate -Dexpression=build.channel -DforceStdout
./mvnw -q help:evaluate -Dexpression=project.build.finalName -DforceStdout
./mvnw help:effective-pom -Dverbose -Doutput=effective-pom.xml
```

Với đúng ví dụ POM trên, không có settings/CLI khác ép profile hoặc property, **các lệnh evaluate riêng lẻ** lần lượt trả:

```text
0.1.0
```

```text
local
```

```text
demo-service-local
```

Ba block trên là **đầu ra của ba lệnh `help:evaluate` tương ứng**, không phải một lần chạy in cả ba dòng. Trong effective POM có thể tìm:

```xml
<finalName>demo-service-local</finalName>
```

Các phần tử khác của effective POM còn được kế thừa từ `spring-boot-starter-parent` và Super POM; chúng không nhất thiết xuất hiện nguyên văn trong `pom.xml` bạn tự viết.

Build và chạy artifact:

```bash
./mvnw clean package
java -jar target/demo-service-local.jar
```

`clean package` cần Maven/JDK thích hợp và quyền tải các plugin/dependency khi cache chưa có. Kết quả build thực tế được xác nhận qua log và file đầu ra, không suy từ tên file đơn thuần.

### 4.2. Trường hợp bật Maven profile `prod`

```bash
./mvnw -Pprod help:active-profiles
./mvnw -Pprod -q help:evaluate -Dexpression=build.channel -DforceStdout
./mvnw -Pprod -q help:evaluate -Dexpression=project.build.finalName -DforceStdout
./mvnw -Pprod help:effective-pom -Doutput=effective-pom-prod.xml
```

Các kết quả evaluate tương ứng là:

```text
prod
```

```text
demo-service-prod
```

Vì `local` là profile `activeByDefault` **trong cùng POM**, kích hoạt `prod` khiến `local` mặc định ngừng hoạt động (nếu không có cấu hình kích hoạt khác). Trong effective POM `-Pprod`, `<finalName>` dự kiến thành `demo-service-prod`. Nếu build:

```bash
./mvnw -Pprod clean package
java -jar target/demo-service-prod.jar
```

`-Pprod` ở đây **chỉ đổi tham số build và tên artifact**. Nó không tự đặt Spring runtime profile thành `prod`. Muốn bật Spring runtime profile, cần cấu hình ứng dụng hoặc truyền tham số riêng khi chạy, ví dụ:

```bash
java -jar target/demo-service-prod.jar --spring.profiles.active=prod
```

Lệnh Java trên truyền tham số cho **ứng dụng Spring**. Đây là một quyết định khác với việc Maven đã chọn profile `prod` trong quá trình build.

### 4.3. Ghi đè property bằng lệnh Maven

Với `-Dbuild.channel=staging`, Maven nhận user property trên lần gọi đó. Ví dụ:

```bash
./mvnw -q help:evaluate -Dexpression=build.channel -Dbuild.channel=staging -DforceStdout
```

Giá trị được in là:

```text
staging
```

Trong ví dụ, user property trên CLI có ưu tiên cao đối với biểu thức này. Tuy nhiên, profile activation, plugin parameter hoặc cấu hình đặc biệt có thể tạo ra hành vi không hiển nhiên; khi có khác biệt, kiểm tra `help:active-profiles`, `help:evaluate` và effective POM **trong cùng tập tham số** dùng để build thật.

## 5. Đọc effective POM đúng cách

### 5.1. Tìm nguồn gốc một cấu hình

Khi dự án kế thừa `spring-boot-starter-parent`, nhiều giá trị mặc định như Java compilation, plugin version và cấu hình plugin không được lặp lại ở POM con. Chạy:

```bash
./mvnw help:effective-pom -Dverbose -Doutput=effective-pom.xml
```

Mở file và tìm lần lượt:

- `<parent>`: đang kế thừa parent nào, phiên bản nào.
- `<properties>`: các thuộc tính cuối được đưa vào mô hình.
- `<dependencyManagement>`: những phiên bản dependency **được quản lý**.
- `<dependencies>`: những dependency **đã được khai báo** ở mô hình hiện tại.
- `<pluginManagement>`: version/configuration mặc định dành cho plugin.
- `<build><plugins>`: plugin thực sự được cấu hình trong build và các execution liên quan.
- `<finalName>`, `<sourceDirectory>`, `<resources>`: thông tin đầu ra và đường dẫn.

Với `-Dverbose`, Maven Help Plugin thêm comment về **vị trí khai báo nguồn** để dễ lần từ effective POM trở lại parent POM hoặc module POM. Không phải mọi phiên bản Help Plugin đều hỗ trợ verbose; bản hiện hành hỗ trợ từ phiên bản `3.2.0` trở lên.

**Một nguyên tắc quan trọng:** `<dependencyManagement>` hoặc một Spring Boot BOM quản lý phiên bản **không tự thêm** dependency vào ứng dụng. Vì vậy thấy một thư viện được quản lý trong effective POM không đủ để khẳng định thư viện nằm trên classpath.

### 5.2. Biết giới hạn của effective POM

Effective POM là mô hình dự án sau inheritance/interpolation/profile. Nó **không phải**:

1. Danh sách đầy đủ các **transitive dependencies** và phiên bản cuối cùng được chọn. Muốn biết phần này, dùng `dependency:tree`.
2. Snapshot mọi tham số plugin ở **thời điểm chạy goal**. Một số biểu thức trong plugin configuration được đánh giá muộn hơn, có thể còn nguyên `${...}` trong cách trình bày của effective POM.
3. Danh sách mọi máy chủ mà Maven chắc chắn đã truy cập. Settings/mirrors, repositories, cache và quá trình resolution mới quyết định việc đó.
4. Bằng chứng rằng JAR/WAR đã đóng gói đúng. Cần build, kiểm tra artifact và chạy thử.

Lệnh bổ sung:

```bash
./mvnw dependency:tree
./mvnw help:active-profiles
./mvnw -X validate
```

`-X` là debug, giúp nhìn thêm thông tin Maven/plugin khi cần, nhưng log có thể chứa đường dẫn và chi tiết môi trường; không chia sẻ nguyên log nếu có dữ liệu nhạy cảm.

## 6. Effective settings: đọc cấu hình của máy và CI

Maven sử dụng settings để điều khiển nơi lấy artifact và một số tham số môi trường. Những mục thường cần tra trong effective settings:

| Phần tử | Ý nghĩa | Lỗi liên quan |
|---|---|---|
| `<localRepository>` | Đường dẫn Maven local repository | Build dùng cache khác nơi dự kiến |
| `<mirrors>` | Ánh xạ repository ID/pattern tới mirror URL | Maven bị chuyển hướng qua mirror lỗi hoặc thiếu artifact |
| `<servers>` | Thông tin kết nối/xác thực theo server ID | 401/403 khi truy cập repository |
| `<proxies>` | Proxy và quy tắc không qua proxy | Không tải được dependency/plugin |
| `<profiles>` | Repository, pluginRepository, property được cấu hình trong settings profiles | Máy A/B resolve từ kho khác hoặc có property khác |
| `<activeProfiles>` | Settings profile được kích hoạt mặc định | Profile mong muốn không được áp dụng |

Lệnh:

```bash
./mvnw help:effective-settings -Doutput=effective-settings.xml
./mvnw help:active-profiles
```

Effective settings **kết hợp global settings với user settings** và các thiết lập áp dụng để chạy Maven. Ví dụ máy có mirror nội bộ, trong POM chỉ thấy Maven Central nhưng Maven thực tế được chuyển qua mirror; lúc này hãy xem `<mirrors>` và repository ID trong effective settings.

**Bảo mật:** mặc định `help:effective-settings` **ẩn các password** (`showPasswords=false`). Không bật `-DshowPasswords=true` để gửi log cho người khác. Dù password đã che, file kết quả vẫn có thể chứa hostname nội bộ, username, đường dẫn hoặc thông tin hạ tầng. Không commit `effective-settings.xml` vào repository và không gửi công khai nếu chưa rà soát.

### 6.1. Dùng file settings khác để tái hiện môi trường

Khi chẩn đoán chênh lệch giữa local và CI, có thể chạy với một file settings được cấp đúng quyền:

```bash
./mvnw -s ci-settings.xml help:effective-settings -Doutput=effective-settings-ci.xml
./mvnw -s ci-settings.xml help:active-profiles
./mvnw -s ci-settings.xml help:effective-pom -Doutput=effective-pom-ci.xml
```

`ci-settings.xml` ở đây là **ví dụ tên đường dẫn**, file phải thật sự tồn tại nếu chạy lệnh. Các lệnh không tự tạo settings mới. `-s` thay vị trí user settings được sử dụng cho lần gọi đó; `-gs` có thể dùng để chỉ định global settings. Mỗi lần so sánh phải dùng **cùng Maven/JDK/profile/property** và mô tả rõ file settings nào được chọn.

Trong `settings.xml`, profile có tập phần tử **giới hạn** (chẳng hạn `repositories`, `pluginRepositories` và `properties`); nó không phải nơi thay toàn bộ `<build><plugins>` của POM. Nếu muốn quyết định plugin execution, thường cấu hình trong POM/parent/plugin management.

## 7. Thuộc tính đã nội suy: cú pháp và cách kiểm tra

**Property interpolation** là cơ chế thay tham chiếu kiểu `${...}` bằng giá trị khi Maven xây dựng mô hình hoặc plugin đánh giá biểu thức. Không phải mọi tham chiếu đều được giải quyết tại cùng một thời điểm.

| Biểu thức trong POM/plugin | Ý nghĩa thường gặp | Lệnh kiểm tra |
|---|---|---|
| `${project.groupId}` | Group ID của dự án | `help:evaluate -Dexpression=project.groupId` |
| `${project.artifactId}` | Artifact ID | `help:evaluate -Dexpression=project.artifactId` |
| `${project.version}` | Phiên bản dự án | `help:evaluate -Dexpression=project.version` |
| `${project.basedir}` | Thư mục gốc POM/module | `help:evaluate -Dexpression=project.basedir` |
| `${project.build.finalName}` | Tên artifact cuối (bỏ đuôi) | `help:evaluate -Dexpression=project.build.finalName` |
| `${java.version}` | Property do dự án/parent/profile khai báo, nếu có | `help:evaluate -Dexpression=java.version` |
| `${env.JAVA_HOME}` | Biến môi trường của tiến trình Maven | `help:evaluate -Dexpression=env.JAVA_HOME` |
| `${settings.localRepository}` | Local repository Maven sử dụng | `help:evaluate -Dexpression=settings.localRepository` |
| `${build.channel}` | Property tùy chỉnh của POM ví dụ | `help:evaluate -Dexpression=build.channel` |

Ví dụ trên Linux/macOS:

```bash
./mvnw -q help:evaluate -Dexpression=project.artifactId -DforceStdout
./mvnw -q help:evaluate -Dexpression=java.version -DforceStdout
./mvnw -q help:evaluate -Dexpression=project.build.finalName -DforceStdout
```

Đối với POM ở mục 4, ba giá trị lần lượt là `demo-service`, `17` và `demo-service-local` khi không có overrides khác.

**Phân biệt ba lớp biểu thức:**

- `${project.version}` và `${project.build.finalName}` dựa trên **model Maven** đang xử lý.
- `${env.JAVA_HOME}` phụ thuộc **environment variables** của shell/CI **lúc Maven khởi chạy**. Có thể khác nhau giữa IDE, terminal và pipeline.
- `${my.property}` do POM/parent/profile/settings hoặc `-D` cung cấp; giá trị nào được chọn tùy nguồn và quy tắc ưu tiên.

Không được dùng cú pháp `-Dexpression=${project.version}`: parameter của `help:evaluate` cần tên biểu thức **không chứa** `${...}`. Cũng không nên assume mọi `${...}` trong file cấu hình tài nguyên của Spring Boot tự được Maven xử lý: **Maven resource filtering** phải được bật và cấu hình rõ nếu muốn thay nội dung file resource lúc build. Spring Boot hỗ trợ cách dùng placeholder resource riêng; còn Spring runtime property resolution là một cơ chế khác.

### 7.1. Khi nào property chưa được nội suy?

Có thể gặp XML vẫn chứa `${some.property}` hoặc goal báo biểu thức không hợp lệ. Hãy kiểm tra:

1. Tên property viết đúng chưa (có phân biệt dấu chấm, chữ hoa/thường)?
2. Nó được định nghĩa trong **POM hiện tại, parent, profile đang active, settings profile hoặc CLI** chưa?
3. Bạn đang xem **POM con trước interpolation** hay effective POM?
4. Biểu thức nằm trong **plugin configuration** chỉ được plugin xử lý khi goal chạy?
5. Có sự khác biệt Maven/JDK/profile/settings/CLI giữa lệnh kiểm tra và lệnh build?
6. Property ấy thuộc **Spring runtime**, chẳng hạn `spring.profiles.active`, chứ không phải Maven model?
7. Có đang cố sử dụng POM property để nội suy vào `settings.xml`? Settings có phạm vi và quy tắc interpolation riêng; không thể giả định settings đọc mọi property từ POM.

Dùng `help:evaluate` để kiểm tra giá trị riêng lẻ, sau đó kiểm tra **hành vi goal thực tế** nếu plugin còn xử lý biểu thức hoặc cấu hình ở bước sau.

## 8. Thứ tự ưu tiên, profile và môi trường: phương pháp so sánh

Một cấu hình cụ thể có thể bị ảnh hưởng bởi:

- **Parent POM/Super POM:** cung cấp mặc định khi POM con không khai báo.
- **POM con:** có thể thay các phần tử cho phép override so với parent.
- **Maven profile đang active:** đóng góp property/repository/plugin/dependency theo loại profile.
- **CLI user properties (`-D...`):** thường có ưu tiên cao đối với biểu thức/property được hỗ trợ.
- **Settings & môi trường:** xác định mirror, proxy, local repository và settings profile; cũng cung cấp một số property.
- **Plugin execution:** có thể đọc tham số, Java environment hoặc cấu hình ở thời điểm goal chạy.

Không áp dụng **một bảng ưu tiên tuyến tính duy nhất** cho tất cả phần tử. Quy tắc kế thừa plugin, dependency management, profile activation và repository mirror khác nhau. Cách chắc chắn là chạy cùng bộ tham số và đọc ra kết quả cụ thể.

Ví dụ để so sánh hai cách build:

```bash
# Môi trường mặc định:
./mvnw help:active-profiles
./mvnw help:effective-pom -Doutput=effective-pom-local.xml

# Bật Maven profile prod:
./mvnw -Pprod help:active-profiles
./mvnw -Pprod help:effective-pom -Doutput=effective-pom-prod.xml

# Xem khác biệt với lệnh diff có sẵn trên Linux/macOS:
diff -u effective-pom-local.xml effective-pom-prod.xml
```

Trên Windows có thể mở hai file trong công cụ so sánh văn bản. Chú ý các file có thể khác do thứ tự XML, đường dẫn tuyệt đối hoặc môi trường; hãy tập trung vào những phần tử ảnh hưởng build.

Đối với **multi-module project**, mỗi module có thể có effective POM riêng, parent và version khác nhau. Nếu module `orders-api` là một thành viên reactor, có thể chọn bằng Maven project selector:

```bash
./mvnw -pl :orders-api help:effective-pom
```

Lệnh minh họa này yêu cầu module `orders-api` thật sự tồn tại trong reactor; nếu module khác tên, thay bằng `artifactId` đúng. Với `help:effective-pom` là aggregator goal, phải đọc kỹ output khi nhiều project tham gia, thay vì giả định XML đang xem thuộc module mong muốn.

## 9. Chẩn đoán những trường hợp dễ nhầm

| Triệu chứng | Kiểm tra đầu tiên | Hướng giải quyết |
|---|---|---|
| Starter không ghi `<version>` mà vẫn build | Effective POM `dependencyManagement` và Spring Boot parent/BOM | Phân biệt version quản lý với dependency đã thêm |
| Maven chọn plugin version không rõ nguồn | `help:effective-pom -Dverbose`; mục `pluginManagement` | Tìm parent/plugin management đã định nghĩa |
| Local dùng repository khác CI | `help:effective-settings` dưới cùng tham số, kiểm tra `<mirrors>`, `<profiles>` | Đồng bộ settings/mirror và quyền truy cập |
| Property `build.channel` vẫn là giá trị local dù chạy `-Pprod` | `help:active-profiles`, `help:evaluate`, các `-D...` | Kiểm tra profile có active, CLI có override |
| Biểu thức chưa được giải quyết | `help:evaluate -Dexpression=...` và cấu hình plugin | Xác minh property tồn tại, đúng scope và thời điểm |
| `mvn help:effective-pom` không giống `./mvnw help:effective-pom` | `mvn -version` so với `./mvnw -version`; settings/JDK | Chọn Maven của project và so cấu hình |
| Dependency đã “managed” nhưng không thấy lúc chạy | `dependency:tree`, runtime classpath, artifact cuối | Kiểm tra khai báo dependency thật và scope |
| `-Pprod` không kích hoạt `application-prod.yml` | Phân biệt Maven profile với Spring runtime profile | Cấu hình `spring.profiles.active` riêng |
| Plugin chạy khác effective POM nhìn thấy | Plugin execution, goal/configuration và log debug | Kiểm tra thời điểm đánh giá tham số plugin |
| Help Plugin không tải được | Plugin repository, mirror, offline/cache | Kiểm tra settings và kết nối trước khi kết luận POM sai |
| Không xác định được output module | Reactor và `-pl`/`-f` | Chỉ đúng module/POM rồi tạo lại effective POM |

**Bài thực hành chẩn đoán:** trên một dự án Spring Boot Maven của bạn, lưu effective POM và effective settings (giữ riêng các file chẩn đoán), xác định ba giá trị `project.version`, `java.version`, `project.build.finalName`. Sau đó bật một Maven profile có property và so sánh. Nếu dependency có vẻ xung đột, xem thêm `dependency:tree`; nếu không truy cập được repository, đọc `effective-settings`. Đây là cách nối từ cấu hình dự án đến môi trường và hành vi build thực tế.

## 10. Checklist khi đọc cấu hình Maven đã hợp nhất

- [ ] Chạy từ đúng POM/module và đúng Maven Wrapper/JDK của dự án.
- [ ] Dùng `help:effective-pom` để thấy parent, property, plugin management và các profile đóng góp vào build.
- [ ] Dùng `-Dverbose` khi cần truy nguồn một phần tử về POM cha hoặc module.
- [ ] Dùng `help:active-profiles` với chính `-P`/`-D`/settings mà lệnh build sử dụng.
- [ ] Dùng `help:effective-settings` khi nghi mirror, proxy, local repository hoặc settings profile khác nhau giữa các máy.
- [ ] Dùng `help:evaluate -Dexpression=name -q -DforceStdout` để đọc giá trị biểu thức; không nhập `${name}` ở tham số `expression`.
- [ ] Phân biệt phiên bản được quản lý ở `dependencyManagement` với dependency thực có trên classpath.
- [ ] Phân biệt Maven `-P...` với Spring `spring.profiles.active`.
- [ ] Không coi effective POM là runtime dependency tree hoặc bằng chứng executable JAR đã đúng; kiểm tra goal/artifact riêng.
- [ ] Giữ kín effective settings, logs và file chẩn đoán có thể chứa URL hoặc thông tin môi trường nội bộ.

**Ghi nhớ:** `effective-pom` trả lời **Maven đã hợp nhất mô hình build như thế nào**; `effective-settings` trả lời **Maven đang chạy với cấu hình máy/người dùng nào**; `help:evaluate` trả lời **một thuộc tính/biểu thức được đánh giá thành giá trị gì**. Kết hợp ba lệnh, active profiles và dependency tree để giải thích các khác biệt giữa `pom.xml` nhìn thấy và kết quả build thực tế.

## Tài liệu tham khảo chính thức

- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Apache Maven Help Plugin — evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html)
- [Maven POM Reference](https://maven.apache.org/pom.html)
- [Maven Settings Reference](https://maven.apache.org/settings.html)
- [Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
