# Kích hoạt tường minh bằng -P và kiểm tra profile đang hoạt động trong Maven

## 1. Profile giải quyết vấn đề gì?

Một dự án Java dùng Apache Maven có thể được build trong nhiều bối cảnh: máy cá nhân, CI, môi trường kiểm thử, hoặc lượt kiểm tra chuyên biệt. Các bối cảnh có thể cần khác nhau về thuộc tính, dependency, plugin và cấu hình đóng gói. **Build profile** là tập cấu hình được Maven áp dụng khi profile đó được kích hoạt.

Ví dụ, POM có thể định nghĩa:
- `dev`: chọn giá trị cấu hình cho phát triển;
- `ci`: chọn cấu hình khi pipeline tự động build;
- `audit`: thêm một thuộc tính hoặc plugin kiểm tra chuyên biệt;
- `local-default`: profile mặc định khi không có profile khác của cùng POM được kích hoạt.

**Nội dung của profile do dự án quyết định.** Tên `dev` không tự khiến Maven bật debug, chạy server hay bỏ qua test. Cần đọc POM để biết profile sửa các giá trị nào.

Bài này có hai mục tiêu trực tiếp: **kích hoạt tường minh bằng `-P`** và **xem profile đang hoạt động bằng `help:active-profiles`**. Một lệnh mẫu:

```bash
mvn -Pdev clean verify
mvn -Pdev help:active-profiles
```

Lệnh thứ nhất chạy build với profile `dev` trong phiên Maven đó; lệnh thứ hai truy vấn danh sách active profiles trong **một phiên Maven mới nhưng cùng lựa chọn `-Pdev`**. Maven không “nhớ” lựa chọn profile của lệnh trước.

Không nhầm ba khái niệm: `-Pdev` là cờ chọn **profile**, `-Denv=dev` là tham số đặt **user property**, còn `verify` là một **phase** của Maven lifecycle. Một user property có thể kích hoạt profile nếu POM khai báo điều kiện tương ứng, nhưng `-Denv=dev` không mặc nhiên đồng nghĩa `-Pdev`.

## 2. Profile được khai báo ở đâu?

Profile có ID và các phần cấu hình. Trong một `pom.xml`, nó nằm dưới `<project><profiles>`:

```xml
<profiles>
    <profile>
        <id>dev</id>
        <properties>
            <app.mode>development</app.mode>
        </properties>
    </profile>
    <profile>
        <id>ci</id>
        <properties>
            <app.mode>continuous-integration</app.mode>
        </properties>
    </profile>
</profiles>
```

Đây là **đoạn XML minh họa**, không phải POM hoàn chỉnh: nó thiếu phần tử gốc `<project>` và Maven coordinates. Profile `dev` ghi đè property `app.mode` bằng `development` nếu có hiệu lực; `ci` cung cấp giá trị khác.

Ba nơi cấu hình profile thường gặp:

| Nguồn | Vị trí | Ý nghĩa |
| --- | --- | --- |
| Project POM | `pom.xml` | Profile gắn với dự án; có thể khai báo nhiều loại cấu hình build |
| User settings | `${user.home}/.m2/settings.xml` | Profile và activeProfiles cho tài khoản đang chạy Maven |
| Global settings | `${maven.home}/conf/settings.xml` | Cấu hình theo bản cài Maven |

Profile trong `settings.xml` hỗ trợ tập phần tử hạn chế hơn profile trong POM, chủ yếu `properties`, `repositories` và `pluginRepositories`. Profile trong POM có thể cấu hình thêm các dependency/plugin và phần build được hỗ trợ. Không đặt tùy tiện mọi phần tử POM vào profile settings.

Ngoài ra, Maven có **profile tự kích hoạt** theo JDK, OS, property, tệp hoặc `activeByDefault`. Vì vậy kích hoạt `-Pdev` không bảo đảm chỉ duy nhất profile `dev` active.

## 3. Cú pháp chính xác của -P

Maven chấp nhận cờ ngắn `-P` và cờ dài `--activate-profiles`:

```bash
mvn -Pdev verify
mvn -P dev verify
mvn --activate-profiles dev verify
```

Ba lệnh này cùng yêu cầu kích hoạt profile ID `dev` (trong điều kiện profile đó được Maven tìm thấy). Ghi ID đúng chữ hoa/chữ thường, không tự thêm hậu tố môi trường hay dấu cách.

Muốn bật **nhiều profile đồng thời**, dùng danh sách ID cách nhau bởi dấu phẩy:

```bash
mvn -Pdev,audit verify
mvn -P dev,audit verify
```

Không dùng `-Pdev audit` để ám chỉ hai profile: `audit` có thể bị hiểu là một phase hoặc plugin goal riêng. Cũng không viết `-Pdev;ci`, vì dấu chấm phẩy là toán tử shell trong nhiều môi trường.

| Tình huống | Lệnh đúng |
| --- | --- |
| Chỉ nạp POM để kiểm tra profile dev | `mvn -Pdev validate` |
| Biên dịch với profile ci | `mvn -Pci compile` |
| Chạy test với dev | `mvn -Pdev test` |
| Verify tự động với ci | `mvn -B -ntp -Pci clean verify` |
| Bật dev cùng profile bổ sung audit | `mvn -Pdev,audit clean verify` |
| Liệt kê profile active khi chỉ định dev | `mvn -Pdev help:active-profiles` |
| So sánh effective POM của ci | `mvn -Pci help:effective-pom` |

Trong Bash/macOS/Linux, nếu repository có Maven Wrapper, có thể thay `mvn` bằng `./mvnw`:

```bash
./mvnw -Pdev,audit clean verify
./mvnw -Pdev,audit help:active-profiles
```

Trong Windows PowerShell:

```powershell
.\mvnw.cmd '-Pdev,audit' clean verify
.\mvnw.cmd '-Pdev,audit' help:active-profiles
```

Ví dụ Wrapper giả định file `mvnw`/`mvnw.cmd` đã được tạo và commit vào dự án. Wrapper chỉ chọn cách khởi động Maven; nó không tự thêm profile hay thay đổi ID profile.

## 4. Xem đúng những profile đang hoạt động

Maven Help Plugin cung cấp goal:

```bash
mvn help:active-profiles
```

Goal này liệt kê các profile **đang active cho build hiện tại**. Để kiểm chứng `-Pdev`, phải truyền cùng cờ cho lệnh kiểm tra:

```bash
mvn -Pdev help:active-profiles
mvn -Pci help:active-profiles
mvn -Pdev,audit help:active-profiles
```

Một ví dụ về hình thức kết quả:

```text
The following profiles are active:

 - dev (source: pom)
 - audit (source: pom)
```

Đây chỉ là **output minh họa** cho tình huống bật `dev,audit` từ POM; thứ tự, dòng log và cách trình bày chi tiết tùy phiên bản Maven Help Plugin và cấu hình thực tế.

Điểm cần đọc là **ID** profile và **source**. Nếu có profile khác `company-repos (source: settings.xml)`, đó có thể là cấu hình settings của người dùng/tổ chức, không phải profile từ POM mẫu.

Nếu tiền tố plugin `help` không phân giải được, có thể gọi đầy đủ goal và ghim phiên bản:

```bash
mvn -Pdev org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
```

Có thể lưu danh sách ra file để so sánh:

```bash
mvn -Pdev help:active-profiles -Doutput=active-profiles.txt
```

`-Doutput` ở đây là tham số của **help:active-profiles**, không phải cờ tổng quát để chuyển mọi log Maven vào file. File được tạo trong working directory của project (hoặc đường dẫn chỉ định) cần được mở đúng nơi.

**Phân biệt bốn lệnh Help Plugin:**

| Goal | Câu hỏi được trả lời |
| --- | --- |
| `help:active-profiles` | Profile nào active **trong lượt Maven hiện tại**? |
| `help:all-profiles` | Profile nào có trong tập cấu hình của project, kể cả inactive? |
| `help:effective-pom` | Sau khi áp dụng inheritance/profile, cấu hình POM cuối là gì? |
| `help:evaluate` | Giá trị một property/biểu thức Maven cụ thể là gì? |

`help:all-profiles` không phải bằng chứng mọi profile được khai báo đều active. `help:active-profiles` cho biết **profile được bật**, nhưng chưa đủ chứng minh một plugin đã sử dụng cấu hình của nó.

## 5. Bài thực hành có thể chạy với Maven và Java 17

Ta tạo một Maven project có bốn profile `local-default`, `dev`, `ci` và `audit`. Dự án sử dụng Maven Resources Plugin để **filter** property trong `app.properties`, rồi Java đọc tài nguyên đã tạo. Nhờ vậy người học kiểm chứng được thay đổi ở **đầu ra thực tế**, không chỉ nhìn danh sách active profiles.

Cấu trúc chính xác:

```text
profile-activation-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/profile/App.java
        └── resources/
            └── app.properties
```

Yêu cầu JDK 17+ và Apache Maven đủ khả năng giải quyết plugin cần thiết. Ví dụ POM có khóa phiên bản các plugin liên quan để kết quả ít lệ thuộc phiên bản mặc định.

### 5.1. pom.xml hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>profile-activation-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <app.mode>base</app.mode>
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
                <version>3.14.1</version>
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
            <id>local-default</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <profile.marker>default-only</profile.marker>
            </properties>
        </profile>
        <profile>
            <id>dev</id>
            <properties>
                <app.mode>development</app.mode>
            </properties>
        </profile>
        <profile>
            <id>ci</id>
            <properties>
                <app.mode>continuous-integration</app.mode>
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

Những điểm quan trọng:
- `app.mode=base` là giá trị nền tại `<project><properties>`.
- `local-default` có `activeByDefault=true`; nó thêm `profile.marker=default-only` khi không có profile khác trong cùng POM được kích hoạt.
- `dev` thay `app.mode` bằng `development`.
- `ci` thay `app.mode` bằng `continuous-integration`.
- `audit` chỉ thêm `audit.enabled=true`; POM **chưa cấu hình plugin kiểm toán nào**, nên nó không tự chạy security scan.
- `<filtering>true</filtering>` yêu cầu Maven Resources Plugin thay property khi copy tài nguyên.
- Compiler Plugin dùng Java release 17; không cần thêm dependency ngoài JDK.

### 5.2. src/main/resources/app.properties

```properties
app.mode=${app.mode}
```

Đây là **tệp nguồn**. Sau khi Maven thực hiện `process-resources`, file `target/classes/app.properties` được tạo, và biểu thức `${app.mode}` được thay bằng giá trị Maven đã tính từ POM và các profile active.

Ví dụ, build với `-Pdev` sẽ sinh nội dung tương đương:

```properties
app.mode=development
```

Maven profile không tự trở thành Java system property. Ví dụ này **chủ động truyền giá trị từ build sang ứng dụng bằng resource filtering**. Đừng nhầm cấu hình build với runtime configuration nếu không có cầu nối như vậy.

### 5.3. src/main/java/com/example/profile/App.java

```java
package com.example.profile;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        Properties props = new Properties();
        try (InputStream in = App.class.getResourceAsStream("/app.properties")) {
            if (in == null) {
                throw new IOException("app.properties not found");
            }
            props.load(in);
        }
        System.out.println("Profile mode: " + props.getProperty("app.mode"));
    }
}
```

Tên `App.java` trùng tên public class; package `com.example.profile` trùng cấu trúc thư mục. Đây là ví dụ Java 17 **biên dịch/chạy được** khi POM và file resource được tạo đúng. Nội dung property trong ví dụ dùng ASCII, nên tương thích với `Properties.load(InputStream)`.

### 5.4. Build không truyền -P

Tại thư mục có POM:

```bash
mvn -B -ntp clean package
mvn help:active-profiles
java -cp target/classes com.example.profile.App
```

Trong điều kiện thông thường không có profile/setting bên ngoài gây xung đột, `local-default` active, `app.mode` vẫn là `base` từ project properties. **Stdout chính xác của lệnh Java cuối cùng:**

```text
Profile mode: base
```

Maven có các dòng INFO riêng; không nên gộp chúng vào stdout của chương trình Java. Đường dẫn `target/classes` được tạo bởi Maven build, khác với file resource nguồn.

### 5.5. Build với dev

```bash
mvn -B -ntp -Pdev clean package
mvn -Pdev help:active-profiles
java -cp target/classes com.example.profile.App
```

Với project này:
- `dev` active.
- `local-default` bị tắt vì một profile khác trong **cùng POM** đã được kích hoạt.
- Resource filtering sinh `target/classes/app.properties` với `app.mode=development`.
- **Stdout của Java:**

```text
Profile mode: development
```

Lệnh `help:active-profiles` phải truyền **lại `-Pdev`**. Nếu bỏ cờ, đó là một lượt chạy Maven mới và `local-default` có thể active trở lại; Maven không lưu lựa chọn dev từ lượt build trước.

### 5.6. Build với ci

```bash
mvn -B -ntp -Pci clean package
mvn -Pci help:active-profiles
java -cp target/classes com.example.profile.App
```

**Stdout của Java:**

```text
Profile mode: continuous-integration
```

`clean package` xóa/rebuild thư mục `target`; sau lệnh này `target/classes/app.properties` và JAR được sinh cho lượt CI đã **thay thế** kết quả của lượt dev. Muốn lưu cả hai sản phẩm để so sánh, sao chép artifact sang tên/thư mục khác trước khi build lại.

### 5.7. Bật đồng thời dev và audit

```bash
mvn -B -ntp -Pdev,audit clean package
mvn -Pdev,audit help:active-profiles
java -cp target/classes com.example.profile.App
```

Danh sách dự kiến gồm `dev` và `audit` từ POM. `audit` không ghi đè `app.mode`, nên **stdout của Java** vẫn là:

```text
Profile mode: development
```

Việc `audit` active không có nghĩa bất kỳ audit tool nào đã chạy. Một profile chỉ chứa property mới sẽ không tự thực hiện thêm plugin goal nếu POM không khai báo cơ chế sử dụng.

## 6. Kiểm tra cấu hình thực sự được áp dụng

`help:active-profiles` chứng minh ID nào active; **không nhất thiết chứng minh giá trị cuối cùng của các plugin/property**. Với project mẫu, có ba cách kiểm tra.

### 6.1. Xem Effective POM

```bash
mvn -Pdev help:effective-pom -Doutput=effective-dev.xml
mvn -Pci help:effective-pom -Doutput=effective-ci.xml
```

Mở hai file và tìm `<app.mode>` trong `<properties>`. Kết quả phù hợp sẽ là `development` và `continuous-integration` tương ứng. Effective POM là **mô hình đã kết hợp inheritance, active profiles và cấu hình Maven**, không phải file nguồn để sửa.

Nếu cần truy dấu nguồn cấu hình, dùng phiên bản Help Plugin hỗ trợ verbose:

```bash
mvn -Pdev org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-dev-verbose.xml
```

Các comment XML ở chế độ verbose có thể hỗ trợ xác định giá trị đến từ POM/module/parent nào. Không sửa output để thay đổi POM gốc.

### 6.2. Xem một property bằng help:evaluate

```bash
mvn -q -Pdev help:evaluate -Dexpression=app.mode -DforceStdout
mvn -q -Pci help:evaluate -Dexpression=app.mode -DforceStdout
mvn -q -Pdev,audit help:evaluate -Dexpression=audit.enabled -DforceStdout
```

Trong ví dụ, giá trị cần thấy lần lượt là `development`, `continuous-integration` và `true`. `-q` giảm log; `-DforceStdout` là tham số của Help Plugin để in kết quả biểu thức qua stdout khi ở chế độ quiet. Nếu plugin/repository lỗi, trước tiên kiểm tra mã thoát và log thay vì coi thông báo lỗi là giá trị property.

### 6.3. Xem file đã filter và chương trình Java

Sau `mvn -Pdev clean package`:

```bash
cat target/classes/app.properties
java -cp target/classes com.example.profile.App
```

Kết quả tài nguyên mong đợi:

```properties
app.mode=development
```

Stdout Java sẽ là `Profile mode: development`. Đây là bằng chứng rằng profile không chỉ **active** mà còn **được áp dụng vào bước xử lý tài nguyên**. Muốn kiểm tra plugin khác thì phải kiểm tra đúng output/goal của plugin đó, không suy từ ví dụ Java.

## 7. Explicit, implicit và activeByDefault

Maven có nhiều cơ chế kích hoạt:

| Kiểu kích hoạt | Ví dụ | Điểm khác biệt |
| --- | --- | --- |
| **CLI tường minh** | `mvn -Pdev verify` | ID được chỉ định trực tiếp trong lượt chạy |
| **Settings tường minh** | `<activeProfiles><activeProfile>id</activeProfile></activeProfiles>` | Cấu hình user/global, có thể bật ở các lượt chạy liên quan |
| **Property-based** | `<activation><property>...` | Kích hoạt nếu một system/CLI property thỏa điều kiện |
| **JDK-based** | `<activation><jdk>...` | Phụ thuộc JDK chạy Maven |
| **OS-based** | `<activation><os>...` | Phụ thuộc OS/kiến trúc |
| **File-based** | `<activation><file>...` | Phụ thuộc sự tồn tại/vắng mặt của file |
| **Active by default** | `<activeByDefault>true</activeByDefault>` | Bật khi không có profile khác trong cùng POM kích hoạt |

Ví dụ **đoạn XML trong `<profiles>`** để bật theo property:

```xml
<profile>
    <id>ci-auto</id>
    <activation>
        <property>
            <name>env</name>
            <value>ci</value>
        </property>
    </activation>
    <properties>
        <app.mode>continuous-integration</app.mode>
    </properties>
</profile>
```

Nếu đoạn này được thêm vào POM, `mvn -Denv=ci verify` có thể kích hoạt `ci-auto`. Đây là **implicit activation qua property**, khác với gọi thẳng `mvn -Pci-auto verify`. Không có `<activation>` đó, `-Denv=ci` không mặc nhiên kích hoạt profile `ci`.

Ví dụ **đoạn settings.xml**:

```xml
<activeProfiles>
    <activeProfile>company-repos</activeProfile>
</activeProfiles>
```

Đoạn này yêu cầu kích hoạt ID `company-repos` theo settings, nhưng vẫn cần định nghĩa profile có ID đó trong phạm vi được Maven giải quyết. Nó không tự tạo phần `repositories` hay properties khi profile chưa được định nghĩa.

**Lưu ý activeByDefault:** Các profile được đánh dấu `activeByDefault` trong một POM không đồng thời tiếp tục mặc định active khi một profile khác trong cùng POM được kích hoạt theo CLI/điều kiện. Trong ví dụ, bật `dev` hoặc `ci` khiến `local-default` không còn active. Đừng hiểu tên “default” là được bật mọi lúc.

## 8. Tắt một profile và Maven 4 optional profile

Maven còn hỗ trợ deactivation profile bằng tiền tố `!` hoặc `-`. Một cách tránh lỗi CLI khi giá trị bắt đầu bằng dấu trừ:

```bash
mvn -P=-local-default help:active-profiles
```

Lệnh trên yêu cầu tắt profile `local-default` trong lượt chạy. Với Bash/Zsh, nếu dùng `!` phải trích dẫn hoặc escape vì shell có thể dùng ký tự này làm history expansion:

```bash
mvn -P '!local-default' help:active-profiles
```

Đây là thao tác **theo lượt chạy**, không xóa profile khỏi `pom.xml`. Trên hệ thống thực tế cần tắt một profile liên tục, hãy xem lại thiết kế activation thay vì buộc mọi CI job phải mang cờ tắt.

**Khác biệt phiên bản Maven:** Maven 4 kiểm tra chặt hơn khi `-P` nhắc tới profile không thể giải quyết. Trong Maven 4, có thể đánh dấu một profile **tùy chọn** bằng tiền tố `?`:

```bash
mvn '-Pdev,?optional-check' help:active-profiles
```

Không giả định cú pháp optional có hành vi giống hệt ở các bản Maven 3 cũ. Để tránh vô tình bỏ qua lỗi gõ sai profile, tốt nhất khai báo ID rõ ràng, dùng Maven Wrapper/phiên bản nhất quán và xác minh active profiles.

## 9. Bật nhiều profile: xung đột và thứ tự hợp nhất

`-Pdev,ci` **không có nghĩa Maven chỉ chọn một trong hai**. Cả `dev` và `ci` đều được yêu cầu kích hoạt. Trong POM mẫu, chúng cùng đặt `app.mode` khác nhau, nên kết quả cần được xác minh bằng effective POM hoặc help:evaluate.

Đặc biệt, **đừng mặc định profile đứng cuối danh sách CLI luôn thắng**. Maven xử lý các profile active theo quy tắc mô hình và thứ tự khai báo/merge, có thể còn tác động từ settings hoặc POM cha. Thiết kế tốt nên tránh các cặp profile cùng chỉnh một thuộc tính nếu chúng có khả năng được bật cùng lúc.

Khi phát hiện lệnh đáng ngờ như `mvn -Pdev,ci package`:

1. Chạy `mvn -Pdev,ci help:active-profiles` để biết hai ID có active không.
2. Chạy `mvn -q -Pdev,ci help:evaluate -Dexpression=app.mode -DforceStdout` để xem kết quả thật.
3. Xem POM/settings và cấu hình plugin liên quan để biết nguồn ghi đè.
4. Chuẩn hóa script thành **một profile môi trường chính** (`dev` hoặc `ci`), chỉ thêm profile độc lập như `audit` khi cần.

Thêm một profile không thay thế việc kiểm thử: **profile active không bảo đảm build thành công** và cũng không bảo đảm plugin goal bất kỳ được chạy.

## 10. POM cha, settings và reactor nhiều module

**POM cha:** Maven không đơn giản sao chép nguyên các định nghĩa profile của parent xuống child rồi kích hoạt lại theo cùng ID ở mọi module. Nó đánh giá profile trong ngữ cảnh chứa profile; **tác động của profile active** có thể được kế thừa theo quy tắc Maven. Nếu parent/child có profile cùng tên, không suy chúng tự động là một đối tượng.

**Settings:** User/global `settings.xml` có thể kích hoạt thêm profile. Kết quả `help:active-profiles` có thể hiện `dev (source: pom)` cùng `company-repos (source: settings.xml)`. `-Pdev` không đồng nghĩa chỉ có `dev` active. Profile settings và profile POM có quy tắc ưu tiên/hợp nhất; để biết property cuối phải xem effective POM.

**Đa module:** Khi reactor gồm nhiều module, ID/profile được khai báo ở các project có thể khác nhau. Nếu cần chẩn đoán một module cụ thể, chạy từ thư mục của module hoặc dùng `-f`:

```bash
mvn -f module-a/pom.xml -Pdev help:active-profiles
mvn -f module-a/pom.xml -Pdev help:effective-pom -Doutput=module-a-effective.xml
```

Hai lệnh giả định có module `module-a` và đường dẫn từ nơi chạy hợp lệ. Xác minh tọa độ project `groupId:artifactId:version` trong effective POM, tránh đọc nhầm output của parent/aggregator. Nếu Maven Help Plugin được gọi như aggregator goal, phạm vi reactor cũng có thể ảnh hưởng danh sách project được báo.

## 11. Tích hợp CI/CD và tính tái lập

Một ví dụ bước build **đơn giản** (không ràng buộc nhà cung cấp CI):

```bash
./mvnw -B -ntp -Pci help:active-profiles
./mvnw -B -ntp -Pci clean verify
```

Các nguyên tắc nên theo:
- Pin Maven bằng Wrapper và quản lý phiên bản plugin quan trọng.
- Dùng **cùng danh sách profile** cho lệnh chẩn đoán và lệnh build.
- Ghi nhận Maven/JDK thực tế nếu CI và máy phát triển cho kết quả khác nhau.
- Không thay cấu hình deploy/credential chỉ bằng cách bật `-Pprod` nếu chưa hiểu profile đó làm gì.
- Không đặt token/mật khẩu trong `pom.xml` hoặc profile commit lên Git. Dùng cơ chế secret/`settings.xml` phù hợp.
- Khi cần điều tra, lưu danh sách profile active và effective POM trong artifacts/log có kiểm soát quyền truy cập; output có thể chứa URL repository hoặc giá trị cấu hình nội bộ.
- Không nhầm một dòng `BUILD SUCCESS` của `help:active-profiles` với kết quả `clean verify`: đó là hai lệnh, hai mục đích khác nhau.

### Một profile có thể thay đổi plugin, dependency và repository

Project profile không chỉ chứa property. Nó có thể kích hoạt dependency, cấu hình compiler, bật plugin goal hoặc khai báo repository theo những phần POM Maven cho phép. Do đó, `-P` có thể ảnh hưởng lớn đến build: thời gian chạy, artifact, mạng và nơi xuất bản. Kiểm tra profile trước khi dùng với `deploy` hoặc quy trình có tác động bên ngoài. Ví dụ `audit` ở POM mẫu **chưa** làm những việc ấy; chỉ có một property.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `help:active-profiles` không có `dev` | Quên `-Pdev` trong lệnh kiểm tra, sai ID hoặc đang đọc sai POM | Chạy cùng `-Pdev`, kiểm tra `help:all-profiles` và đường dẫn `pom.xml` |
| Profile `dev` được khai báo nhưng không active | Chưa kích hoạt và không có điều kiện implicit phù hợp | Gọi `mvn -Pdev help:active-profiles` |
| `local-default` biến mất khi bật `dev` | Active-by-default bị vô hiệu khi profile khác trong cùng POM kích hoạt | Đây là hành vi Maven theo thiết kế |
| Sau `-Pdev` Java vẫn in `Profile mode: base` | Resource chưa được filter lại, dùng output cũ, chọn sai classpath | Chạy `mvn -Pdev clean package`; mở `target/classes/app.properties` |
| `-Denv=dev` không kích hoạt `dev` | POM không định nghĩa activation theo property đó | Dùng `-Pdev` hoặc khai báo activation rõ ràng |
| `-Pdev,ci` gây giá trị bất ngờ | Nhiều profile cùng ghi một property | Dùng `help:evaluate`/`effective-pom` và tránh bật profile xung đột |
| Help Plugin báo không thấy profile | ID không tồn tại, sai version hoặc Maven 4 kiểm tra nghiêm | Xác minh `help:all-profiles`, chỉnh đúng ID; optional chỉ khi phù hợp |
| Profile khác xuất hiện dù chỉ truyền `-Pdev` | Auto activation hoặc `activeProfiles` của settings | Đọc source trong `help:active-profiles`, xem settings/điều kiện kích hoạt |
| IDE và terminal build khác nhau | IDE chạy Maven/settings/JDK khác hoặc truyền cờ khác | So sánh command thực, `mvn -version`, active profiles và effective POM |
| Không thấy cấu hình plugin thực thi | Profile chỉ khai báo property hoặc pluginManagement, chưa có goal/execution áp dụng | Kiểm tra plugin binding, lifecycle và log khi build |
| `-Pdev` có trong lệnh trước nhưng không có ở lệnh kiểm tra mới | `-P` không phải trạng thái lâu dài của project | Truyền lại `-Pdev` trong đúng lệnh muốn kiểm tra |
| Build lỗi dù profile đúng | Dependency/JDK/plugin/test/network lỗi | Xem lỗi thực tế và exit code; profile active không bảo đảm thành công |

## 13. Checklist và bài tập tự kiểm tra

Trước khi kết luận profile hoạt động đúng, hãy xác nhận:

- Tên profile đã được khai báo trong `pom.xml` hoặc settings của project thật.
- `-P` đi cùng **lệnh Maven đang cần sử dụng profile**; không dựa vào lệnh trước.
- `help:active-profiles` hiển thị đúng ID và nguồn.
- `help:effective-pom` hoặc `help:evaluate` xác nhận **giá trị cuối** của thuộc tính quan trọng.
- Khi cần thấy tác động thật, kiểm tra output plugin/resource hoặc chạy chương trình đã build.
- Không vô tình bật hai profile môi trường xung đột.
- Có hiểu `activeByDefault` và những profile tự kích hoạt khác.
- Đã dùng đúng Maven version, JDK, POM/module và settings trong CI.

Câu hỏi ôn tập:

1. `-Pdev` khác `-Denv=dev` ở điểm nào?
2. Vì sao `mvn -Pdev package` rồi `mvn help:active-profiles` có thể cho danh sách profile khác lệnh đầu?
3. Lệnh nào chứng minh cả `dev` và `audit` đang hoạt động?
4. `help:all-profiles` khác `help:active-profiles` ra sao?
5. Vì sao `local-default` bị tắt khi `dev` active trong POM mẫu?
6. Vì sao `-Pdev,ci` không nên được dùng nếu hai profile cùng đặt `app.mode`?
7. Làm sao chứng minh `target/classes/app.properties` đã nhận giá trị của profile?
8. Khi output `help:active-profiles` có một profile từ settings, có thể kết luận `-Pdev` bị bỏ qua không?
9. Vì sao cần giữ bí mật cấu hình trong settings/CI thay vì đưa vào profile commit Git?

**Kết luận:** `-P` kích hoạt tường minh profile theo **ID trong từng lượt Maven**; nhiều ID viết cách nhau bằng dấu phẩy. `help:active-profiles` xác nhận profile đang bật, còn `help:effective-pom` và `help:evaluate` giúp chứng minh cấu hình sau khi áp dụng. Kết quả build cuối cùng vẫn cần được kiểm tra bằng plugin output, mã thoát và test liên quan.

## Tài liệu chính thức

- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven Help Plugin — help:active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven Help Plugin — help:all-profiles](https://maven.apache.org/plugins/maven-help-plugin/all-profiles-mojo.html)
- [Apache Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html)
- [Apache Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
