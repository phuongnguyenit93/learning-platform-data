# Non-resolvable parent POM và sai relativePath trong Maven

## 1. Lỗi xuất hiện ở đâu và vì sao Maven dừng sớm?

Trong Maven, một project con có thể khai báo **parent POM** để kế thừa `groupId`, `version`, properties, dependencyManagement, pluginManagement hoặc cấu hình build. Maven phải **tìm và đọc POM cha** trước khi có thể xây dựng effective model của project con. Nếu bước này thất bại, Maven có thể dừng ngay khi **Scanning for projects**, trước `compile`, `test`, `package`.

Hai thông báo thường gặp:

```text
[FATAL] Non-resolvable parent POM for com.example:sample-app:1.0.0:
Could not find artifact com.example:sample-parent:pom:1.0.0
and 'parent.relativePath' points at wrong local POM
```

hoặc:

```text
[FATAL] Non-resolvable parent POM for com.example:sample-app:1.0.0:
Could not transfer artifact com.example:sample-parent:pom:1.0.0
from/to company-releases (https://repo.example.org/releases):
status code: 401, reason phrase: Unauthorized
and 'parent.relativePath' points at no local POM
```

**Đây là các log minh họa, không phải lỗi thực tế đã thu thập từ một project.** Đặc biệt, thông điệp có thể gồm *hai vế*: không resolve parent từ repository **và** `relativePath` không tìm được POM cha đúng trong checkout. Đừng chỉ nhìn cụm `wrong local POM` rồi sửa đường dẫn một cách mù quáng, vì nguyên nhân gốc có thể là sai tọa độ GAV, parent chưa publish, sai repository/mirror, authentication, DNS/TLS hoặc cache.

Bài hướng dẫn các nhánh chẩn đoán **parent POM không resolve** và **`relativePath` sai**, với ví dụ Maven multi-module Java 17 chạy được, phương án dùng POM cha trong checkout, phương án parent lấy từ repository, kiểm tra repository/settings, lỗi cache và cách xác nhận sửa đúng.

## 2. Phân biệt parent, aggregator và dependency

Đây là ba vai trò liên quan nhưng **không đồng nghĩa**.

| Khái niệm | Khai báo ở đâu? | Tác dụng |
| --- | --- | --- |
| **Parent POM** | Trong `<parent>` của child | Kế thừa model/configuration từ parent |
| **Aggregator** | Trong `<modules>` của root | Gom modules vào một Maven reactor build |
| **Dependency** | Trong `<dependencies>` | Cung cấp các artifacts trên classpath/đồ thị dependency |
| **BOM** | Trong `dependencyManagement`, `type=pom`, `scope=import` | Import quản lý versions; không phải `parent` |

Một POM root có thể vừa là parent vừa là aggregator, nhưng:
- `<modules>` **không tự biến root thành parent** của child nếu child không khai báo `<parent>`.
- `<parent>` **không tự biến child thành module của reactor** nếu aggregator không liệt kê nó.
- Một library JAR không thể thay chức năng POM cha chỉ bằng việc đưa vào `<dependencies>`.
- POM của BOM import không được tìm bằng `<parent><relativePath>`.

**Packaging parent:** parent/configuration-only POM thường đặt `<packaging>pom</packaging>`. Nếu bỏ `<packaging>`, Maven mặc định `jar`; đó không phải cách thường dùng để phát hành parent-only POM. Đảm bảo parent artifact tại repository có **extension `pom`**, ví dụ:

```text
com/example/build/company-parent/2.4.0/company-parent-2.4.0.pom
```

Đường dẫn Maven repository lấy từ `groupId` chuyển dấu chấm thành slash, rồi `artifactId`, `version`, filename tương ứng. Một repository artifact chỉ có JAR mà thiếu POM phù hợp không giải quyết được parent model.

## 3. Maven tìm parent theo thứ tự nào?

Theo Maven Model Reference, child khai báo:

```xml
<parent>
    <groupId>com.example.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>2.4.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Quy trình khái niệm:

1. **Filesystem:** kiểm đường dẫn từ vị trí **POM con** tới POM cha, thông qua `relativePath`.
2. **Local Maven repository:** tìm parent POM ứng với `groupId:artifactId:version` trong repository local.
3. **Configured remote repositories:** nếu cần, resolve từ Maven repositories/mirrors thích hợp.

**Ba tọa độ GAV trong `<parent>` là bắt buộc và phải khớp POM được tìm.** Nếu file ở `relativePath` tồn tại nhưng `groupId`, `artifactId`, `version` trong đó không khớp, Maven không thể coi đó là parent đã yêu cầu và sẽ tìm trong repositories. Vì vậy có thể thấy cảnh báo `parent.relativePath points at wrong local POM` **dù file `../pom.xml` tồn tại**.

### 3.1. `relativePath` tính từ thư mục nào?

**Từ directory chứa `pom.xml` của child**, không phải từ shell working directory, project aggregator root hay Maven local repository.

Ví dụ:

```text
workspace/
├── pom.xml                   (company-parent)
└── services/
    └── billing/
        └── pom.xml           (child)
```

Từ `services/billing/pom.xml`:
- `../pom.xml` chỉ tới `services/pom.xml` (**sai**, vì không có file đó).
- `../../pom.xml` chỉ tới `workspace/pom.xml` (**đúng**).

Nếu bạn đứng tại `workspace` và chạy `mvn -f services/billing/pom.xml validate`, `relativePath` vẫn tính theo `services/billing/pom.xml`, **không đổi do current working directory**.

### 3.2. Khi không ghi `relativePath`

Mặc định Maven hiểu:

```xml
<relativePath>../pom.xml</relativePath>
```

Vì vậy cấu trúc parent nằm ngay bên trên child là trường hợp thuận tiện:

```text
repo/
├── pom.xml              (parent)
└── child/
    └── pom.xml          (child)
```

Trong layout này có thể **bỏ hẳn `<relativePath>`** hoặc ghi rõ `../pom.xml`. Nhưng nếu child nằm hai hay nhiều cấp thư mục, bỏ nó không có nghĩa Maven tự tìm ancestor tùy ý.

### 3.3. Khi dùng `<relativePath/>`

```xml
<relativePath/>
```

**Chuỗi rỗng tắt việc kiểm parent POM qua relative filesystem path**, để Maven lấy parent qua repositories. Nó **không**:
- tắt cơ chế inheritance;
- vô hiệu hóa `<parent>`;
- tự download một parent chưa tồn tại;
- biến cấu hình sai GAV thành đúng;
- giải quyết lỗi HTTP 401, 403 hay mirror không chứa parent.

Dùng giá trị rỗng khi parent là **external/corporate parent đã install/deploy hợp lệ** và bạn **không muốn** Maven vô tình chọn một `../pom.xml` không liên quan trong checkout.

**Không dùng `<relativePath/>` như phản xạ cho mọi lỗi local parent.** Nếu parent là source nằm ngay trong cùng repository và chưa publish, bạn có thể biến một lỗi đường dẫn dễ sửa thành lỗi “artifact not found”.

## 4. Bảng đọc nhanh các loại thông báo

| Thông báo/triệu chứng | Giả thuyết cần kiểm | Không nên làm ngay |
| --- | --- | --- |
| `parent.relativePath points at wrong local POM` | File tại path không có GAV parent được yêu cầu | Xóa toàn bộ `.m2` |
| `parent.relativePath points at no local POM` | Path sai/missing, hoặc chủ động dùng repository-only | Tự ý đổi parent version |
| `Could not find artifact ...:pom:...` | Parent chưa install/deploy, GAV sai, repository thiếu | Thêm random repositories |
| `401 Unauthorized` | Thiếu/sai credentials, server id/mirror | Đưa password vào `pom.xml` |
| `403 Forbidden` | Tài khoản/token thiếu quyền hoặc policy chặn | Vô hiệu TLS/auth |
| `404 Not Found` | GAV/version không publish, URL sai, chính sách snapshots | Chạy `-U` lặp vô hạn |
| `Unknown host`, timeout | DNS/proxy/VPN/network | Sửa đường dẫn local nếu parent vốn remote |
| `PKIX path building failed` | SSL truststore/TLS/proxy certificate | Bỏ qua kiểm certificate |
| `Cannot access ... in offline mode` | Parent chưa có trong local repository khi `-o` | Kỳ vọng Maven tự tải offline |
| `resolution is not reattempted until update interval` | Negative lookup result bị cache | Xóa toàn bộ repository |
| `Non-parseable POM` | XML sai cú pháp, khác parent resolution | Dùng `-U` để sửa XML |

**Đọc cả `Caused by` và repository id/URL trong lỗi.** Một chuỗi `parent.relativePath ...` có thể đi kèm lỗi remote chủ đạo. Chẩn đoán đúng cần xác định parent **nên được lấy từ filesystem hay repository** trước tiên.

## 5. Quy trình chẩn đoán tối thiểu, ít thay đổi

### Bước 1. Ghi lại môi trường và lệnh đang lỗi

```bash
mvn -version
java -version
mvn -B -ntp validate
```

Nếu lệnh cuối fail vì parent, **đó là bình thường**. Giữ log gốc, đọc tên project child, parent GAV và vế nguyên nhân. Lệnh `validate` được chọn vì nó đơn giản và đủ ép Maven dựng model; không cần `clean package` để phân tích parent.

Kiểm shell đang ở đúng folder chứa POM project bị lỗi. Với workspace có nhiều POM, dùng `-f` chỉ chính xác:

```bash
mvn -B -ntp -f services/billing/pom.xml validate
```

Ở đây `services/billing/pom.xml` là **đường dẫn minh họa** cho layout mục 3, không phải file được tạo trong ví dụ code chính của bài.

### Bước 2. Kiểm `<parent>` trong POM con

Tìm:

```xml
<parent>
    <groupId>com.example.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>2.4.0</version>
    <relativePath>../../pom.xml</relativePath>
</parent>
```

Đây là **fragment** cho một layout parent hai cấp phía trên, không phải một POM hoàn chỉnh. Kiểm:
- Chính xác `groupId`, `artifactId`, `version` (phân biệt snapshot/release).
- Không nhầm tên artifact của aggregator với tên module khác.
- File cha tại path dự kiến thật sự tồn tại.
- Nếu child khai báo `<relativePath>` rỗng, parent phải có trong repositories.
- Không đoán rằng child `<version>` đã thay thì parent `<version>` tự thay theo.

**Quan trọng:** Các tọa độ parent cần được cung cấp đúng theo model, không dựa vào property nội suy tùy ý trong `<parent>`. Với Maven CI-friendly versions có ngoại lệ được hỗ trợ như `${revision}`, nhưng trong bài lỗi thông thường nên dùng version literal để tránh một biến số nữa.

### Bước 3. Nếu dùng local parent, kiểm file đích và GAV

Ví dụ layout:

```text
workspace/
├── pom.xml
└── services/
    └── billing/
        └── pom.xml
```

Từ `services/billing`:

```bash
ls -l ../../pom.xml
```

Trên Windows PowerShell:

```powershell
Test-Path -LiteralPath "../../pom.xml"
```

Sau khi xác nhận tồn tại, **mở POM cha và đối chiếu GAV**, không chỉ filename. Một `pom.xml` tại đúng số cấp thư mục nhưng thuộc project khác vẫn **không phải parent đúng**.

### Bước 4. Nếu dùng repository parent, tìm artifact GAV đúng

Ví dụ parent:

```text
com.example.build:company-parent:pom:2.4.0
```

Maven local repository mặc định trên Linux/macOS:

```text
~/.m2/repository/com/example/build/company-parent/2.4.0/company-parent-2.4.0.pom
```

Nhưng Maven có thể dùng local repo khác qua `settings.xml` hoặc `-Dmaven.repo.local`. Vì vậy hãy đối chiếu **repository thực tế**, không tự kết luận một file thiếu trong `~/.m2` nghĩa là Maven chưa có artifact.

Nếu parent chỉ nằm ở private repository:
- Repository URL đúng và accessible?
- Đúng release/snapshot repository policy?
- Settings profile có active?
- Mirror có chặn/redirect sang repository thiếu artifact?
- Credentials có được gửi đến đúng repository/mirror id?
- Parent version đó đã deploy thành công chưa?

### Bước 5. Chạy chẩn đoán phù hợp

```bash
mvn -B -ntp -e validate
```

Khi cần chi tiết repository resolution:

```bash
mvn -B -ntp -X validate
```

**Chú ý:** `-X` có thể ghi rất nhiều thông tin về repository/proxy/environment. Không chia sẻ raw debug log khi chưa rà soát URLs nội bộ, tokens, username và dữ liệu nhạy cảm.

Không dùng `help:effective-pom` như bước cứu đầu tiên khi child model còn không dựng được: **goal Help Plugin cũng cần đi qua bước đọc project model** trong những ngữ cảnh có project. Chỉ xem effective POM **sau khi đã sửa parent resolution**.

## 6. Ví dụ Java 17 chạy được: parent nằm hai cấp trên

Ta tạo một Maven reactor có root aggregator/parent và hai modules cùng nằm trong `modules/`. Ví dụ minh họa đúng `relativePath` khi child POM nằm **hai cấp dưới** parent POM.

### 6.1. Cây thư mục

```text
parent-path-lab/
├── pom.xml                             (parent + aggregator)
└── modules/
    ├── util/
    │   ├── pom.xml                     (child, parent ../../pom.xml)
    │   └── src/
    │       ├── main/java/com/example/diagnostics/util/TextUtil.java
    │       └── test/java/com/example/diagnostics/util/TextUtilTest.java
    └── app/
        ├── pom.xml                     (child, parent ../../pom.xml)
        └── src/main/java/com/example/diagnostics/app/Main.java
```

**Lưu ý đếm cấp:**
- Từ `modules/util/pom.xml`, `../pom.xml` trỏ tới `modules/pom.xml` (**không tồn tại**).
- `../../pom.xml` trỏ tới `parent-path-lab/pom.xml` (**đúng**).
- Từ `modules/app/pom.xml` cũng cần `../../pom.xml`.

Cấu hình này thể hiện một case thực tế rất thường gặp khi module được chuyển từ `root/app` sang `root/modules/app` mà không sửa parent relative path.

### 6.2. File `parent-path-lab/pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.diagnostics</groupId>
    <artifactId>parent-path-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <name>Parent Path Lab</name>

    <modules>
        <module>modules/util</module>
        <module>modules/app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.jupiter.version}</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
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
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

**Đây là POM root hoàn chỉnh**, đóng hai vai trò:
1. **Parent** được hai POM con khai báo trong `<parent>`.
2. **Aggregator** liệt kê modules qua `<modules>`.

Maven compiler release 17 và encoding UTF-8 được inherited. `dependencyManagement` chỉ **quản lý** version/scope JUnit; nó không tự thêm JUnit dependency vào mọi child. `pluginManagement` quản lý versions cho goals được lifecycle chạy.

### 6.3. File `parent-path-lab/modules/util/pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.diagnostics</groupId>
        <artifactId>parent-path-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../../pom.xml</relativePath>
    </parent>

    <artifactId>parent-util</artifactId>
    <packaging>jar</packaging>
    <name>Parent Util</name>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
```

Đúng ba tọa độ trong `<parent>`:
- Group `com.example.diagnostics`;
- Artifact `parent-path-lab`;
- Version `1.0.0`.

Đúng đường dẫn `../../pom.xml`. Child kế thừa `groupId` và `version` nếu không khai báo riêng.

### 6.4. File `parent-path-lab/modules/app/pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.diagnostics</groupId>
        <artifactId>parent-path-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../../pom.xml</relativePath>
    </parent>

    <artifactId>parent-app</artifactId>
    <packaging>jar</packaging>
    <name>Parent App</name>

    <dependencies>
        <dependency>
            <groupId>com.example.diagnostics</groupId>
            <artifactId>parent-util</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

App có Maven dependency tới Util. Khi build reactor từ root, Maven biết thứ tự:
`parent-path-lab` (parent) → `parent-util` → `parent-app`.

Chạy từ root bảo đảm dependency module có trong cùng reactor. Nó **không thay thế việc khai báo parent relativePath đúng**, vì Maven cần dựng model của mỗi module trước khi chạy goals.

### 6.5. File `modules/util/src/main/java/com/example/diagnostics/util/TextUtil.java`

```java
package com.example.diagnostics.util;

import java.util.Locale;

public final class TextUtil {

    private TextUtil() {
    }

    public static String normalize(String input) {
        if (input == null || input.isBlank()) {
            return "GUEST";
        }
        return input.strip().toUpperCase(Locale.ROOT);
    }
}
```

Code dùng Java 17. `Locale.ROOT` giúp kết quả uppercase không phụ thuộc default locale của máy.

### 6.6. File `modules/util/src/test/java/com/example/diagnostics/util/TextUtilTest.java`

```java
package com.example.diagnostics.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TextUtilTest {

    @Test
    void trimsAndNormalizes() {
        assertEquals("MAVEN", TextUtil.normalize("  maven  "));
    }

    @Test
    void handlesBlank() {
        assertEquals("GUEST", TextUtil.normalize("   "));
    }

    @Test
    void handlesNull() {
        assertEquals("GUEST", TextUtil.normalize(null));
    }
}
```

Đây là **3 JUnit Jupiter tests**, chạy trong module Util. Khi POM đầy đủ và Maven resolves JUnit, Surefire sẽ chạy 3 tests, kỳ vọng không có failures hoặc errors.

### 6.7. File `modules/app/src/main/java/com/example/diagnostics/app/Main.java`

```java
package com.example.diagnostics.app;

import com.example.diagnostics.util.TextUtil;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Parent resolved: " + TextUtil.normalize("  maven  "));
        System.out.println("Blank fallback: " + TextUtil.normalize("   "));
    }
}
```

### 6.8. Build và chạy từ root

Yêu cầu: **JDK 17+**, Maven tương thích các plugin đã pin, truy cập repository để tải plugins/JUnit nếu chưa có trong local cache.

```bash
mvn -version
mvn -B -ntp clean verify
```

Cần thấy reactor `Parent Path Lab`, `Parent Util`, `Parent App`, chạy 3 tests ở Util và tạo các JAR:
- `modules/util/target/parent-util-1.0.0.jar`;
- `modules/app/target/parent-app-1.0.0.jar`.

Chạy trên Linux/macOS:

```bash
java -cp "modules/app/target/classes:modules/util/target/classes" com.example.diagnostics.app.Main
```

Windows PowerShell:

```powershell
java -cp "modules/app/target/classes;modules/util/target/classes" com.example.diagnostics.app.Main
```

**Stdout chính xác của Java main**, không gồm Maven log:

```text
Parent resolved: MAVEN
Blank fallback: GUEST
```

POM app không thiết lập executable `Main-Class` và không tạo fat JAR, vì vậy **không dùng `java -jar modules/app/target/parent-app-1.0.0.jar` rồi kỳ vọng demo chạy**.

## 7. Case 1: sai `relativePath` khi di chuyển module

Trong layout mục 6, nếu copy nhầm từ một project có child ở ngay dưới root:

```xml
<parent>
    <groupId>com.example.diagnostics</groupId>
    <artifactId>parent-path-lab</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

thì từ `modules/app/pom.xml` nó trỏ tới `modules/pom.xml`, thay vì root `pom.xml`.

**Kết quả có thể xảy ra:**
- Nếu `modules/pom.xml` **không tồn tại** và parent `com.example.diagnostics:parent-path-lab:pom:1.0.0` **chưa nằm trong repositories**, Maven báo `Non-resolvable parent POM` với vế `points at no local POM`.
- Nếu `modules/pom.xml` tồn tại nhưng là POM **khác GAV**, Maven có thể cảnh báo `points at wrong local POM`; nếu fallback repository cũng không có parent, build thất bại.
- Nếu đúng parent đã được install/deploy, Maven có thể vẫn resolve từ repository và build thành công, che đi path sai. Vì vậy **build pass một lần trên máy developer không chứng minh local path đúng**.

**Sửa đúng khi parent có trong checkout:** 

```xml
<relativePath>../../pom.xml</relativePath>
```

Rồi chạy từ root project:

```bash
mvn -B -ntp clean verify
```

Không thay parent groupId/artifactId/version chỉ để khớp một file POM ngẫu nhiên ở path sai. Parent được khai báo là **một contract** và phải khớp parent thực sự dự định.

### Khi build trên CI khác cấu trúc directory

Một local parent path chỉ hoạt động nếu checkout/monorepo có **cấu trúc tương ứng**. Đừng dùng path tuyệt đối như `C:\Users\Alice\projects\parent\pom.xml` hoặc `/home/alice/private-parent/pom.xml` trong POM chia sẻ.

Nếu CI chỉ checkout module con riêng, cần lựa chọn:
- Checkout cùng parent source đúng cấu trúc và giữ relative path;
- Hoặc publish/install parent POM rồi dùng repository-only resolution.

Việc chỉ copy child module mà không copy parent POM **là thay đổi đầu vào**, không phải Maven “quên parent”.

## 8. Case 2: file local tồn tại nhưng không đúng GAV

Giả sử:

```text
repo/
├── pom.xml                  (artifactId=some-other-parent, version=9.0)
└── child/pom.xml            (parent=company-parent:2.4.0)
```

`child/pom.xml` dùng mặc định `../pom.xml`, và file `repo/pom.xml` **có tồn tại**. Nhưng nó là POM khác; Maven phải bỏ qua ứng viên không khớp và tìm `company-parent:2.4.0` trong repositories.

Vì vậy lỗi:

```text
'parent.relativePath' points at wrong local POM
```

không nhất thiết nói rằng path có lỗi syntax hoặc file không mở được. Nó còn nói rằng **file tại path đó không phải parent với GAV đã khai báo**.

**Phương án sửa:**
- Nếu đúng parent nằm ở chỗ khác trong checkout, chỉ định path thực.
- Nếu parent phải đến từ repo, dùng `<relativePath/>`.
- Nếu child GAV khai báo sai, sửa version/coordinates theo thiết kế.
- Nếu POM tại path sai vì ai đó đổi artifactId, không đổi tùy tiện GAV mà chưa kiểm parent hierarchy.

Tách **layout** (file ở đâu) khỏi **identity** (`groupId:artifactId:version` là gì) sẽ giúp tránh sửa chữa sai nguyên nhân.

## 9. Case 3: parent nằm ở Maven repository, không ở checkout

Với corporate/external parent đã publish, một fragment hợp lý:

```xml
<parent>
    <groupId>com.example.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>2.4.0</version>
    <relativePath/>
</parent>
```

**Đây là fragment**, không phải POM hoàn chỉnh. Nó thể hiện chủ đích luôn resolve parent qua local/remote repositories, không thử `../pom.xml`.

Parent phải tồn tại dưới dạng:

```text
com.example.build:company-parent:pom:2.4.0
```

trong local Maven repository hoặc một remote repository được cấu hình có thể truy cập. Nếu artifact chưa deploy và Maven local cache cũng chưa có, dùng `<relativePath/>` **chắc chắn không tạo ra artifact**.

### 9.1. Cài parent POM vào local repository có chủ đích

Với một parent source project **đã có sẵn**, có thể chạy ở root parent:

```bash
mvn -B -ntp -N install
```

`-N` (non-recursive) chỉ xây root POM hiện tại, tránh tự xây modules child; nó phù hợp khi cần cài **parent POM** trước để một checkout con độc lập có thể resolve được parent từ local repo.

Đối với ví dụ mục 6, có thể chạy trong `parent-path-lab`:

```bash
mvn -B -ntp -N install
```

rồi thử một child với `<relativePath/>` trong **bản sao thực hành**. Nhưng:
- Nếu `parent-app` có dependency `parent-util`, để build app đầy đủ còn phải install util hoặc build reactor chứa util.
- `-N install` chỉ cài parent POM, **không** tự publish các child JAR.
- Local install không giúp **máy CI khác** trừ khi CI cũng có cách nhận đúng parent artifact.
- Khi muốn phát hành parent dùng chung, phải **deploy** parent lên repository được quản trị theo quy trình release, không chỉ install trên một máy.

### 9.2. Maven repository không phải plugin repository

Parent POM là một **project POM artifact**. Khi Maven resolve parent, nó cần `<repositories>` phù hợp hoặc repository profiles trong settings. **`<pluginRepositories>` chỉ dành cho Maven plugins** và không phải cách thêm nơi tìm parent POM.

Nếu company parent chỉ có trong Nexus/Artifactory/private repository, cấu hình repository/mirror đúng và credentials bên ngoài POM. Không thêm một plugin repository rồi mong parent có thể tải xuống.

## 10. Case 4: remote repository, mirror và authentication

Một child có parent GAV đúng, `relativePath` rỗng, nhưng Maven vẫn báo `401`, `403`, `not found` hoặc timeout. Đó là **nhánh repository resolution**, không phải lỗi local relativePath.

### 10.1. Repositories và settings

Maven chọn repositories từ effective settings/build model, áp dụng mirrors trước khi tải artifacts. Những nguyên nhân thường gặp:
- Repository URL sai hoặc mirror trỏ đến host không proxy parent.
- Repository profile chưa active.
- Chỉ có `pluginRepositories`, thiếu repository cho POM artifact.
- Policy không cho tải SNAPSHOT trong releases-only repository.
- `settings.xml` không có credentials phù hợp cho repository/mirror.
- Network yêu cầu VPN, proxy, TLS truststore.
- Parent version chưa được publish lên repository đó.

**Không đặt username/password trực tiếp vào `pom.xml`.** Dùng Maven user/global settings, CI secrets hoặc repository manager. Khai báo `server` phải khớp **repository id thực mà Maven đang kết nối**, bao gồm id của mirror nếu nó thay thế repository gốc.

Ví dụ **đoạn settings.xml minh họa**, endpoint `repo.example.org` chỉ là URL mẫu:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>

    <profiles>
        <profile>
            <id>company-repo</id>
            <repositories>
                <repository>
                    <id>company-releases</id>
                    <url>https://repo.example.org/releases/</url>
                    <releases>
                        <enabled>true</enabled>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </repository>
            </repositories>
        </profile>
    </profiles>

    <activeProfiles>
        <activeProfile>company-repo</activeProfile>
    </activeProfiles>
</settings>
```

**Đây là settings file mẫu**, không đưa credentials thật vào bài học. Các biến environment chỉ hoạt động nếu môi trường thực sự cung cấp chúng. Với Maven 3.10+ và Maven 4, security còn kiểm **repository origins** của credentials; không sửa security scope bừa bãi để né lỗi. Xem Settings Reference theo Maven version đang chạy.

Không ghi đè settings thật nếu chưa biết tổ chức đang dùng mirrors/profile/proxy nào. Với production, copy/chỉnh settings theo chính sách company, dùng secret manager và bảo đảm HTTPS/TLS.

### 10.2. Mirror có thể đổi repository đích

Nếu user settings có mirror `<mirrorOf>*</mirrorOf>`, Maven có thể đưa **mọi yêu cầu repository** qua repository manager đó. Nếu manager không proxy/host private parent, dù child POM khai báo repository đúng, Maven vẫn nhận 404.

Kiểm tra:
- Mirror id, `mirrorOf`, URL;
- Credentials `server.id` khớp id mirror/repository thực;
- Parent GAV có tồn tại trên host đích;
- Repository group có bao gồm hosted releases/snapshots cần thiết không.

**Không dùng `http` không mã hóa hoặc tắt TLS verification chỉ để build qua được.** Sửa truststore, proxy, repository manager và credentials đúng chính sách.

### 10.3. Đọc effective settings

Sau khi có một project khỏe mạnh/địa điểm có thể thực thi Help Plugin, có thể chạy:

```bash
mvn -B -ntp help:effective-settings -Doutput=effective-settings.xml
```

Nếu **child model đang lỗi parent**, chạy Help Plugin ngay trong child có thể cũng thất bại trước goal. Chạy từ một minimal healthy POM hoặc build project khác khi cần xem effective settings; không coi failure của Help Plugin là kết luận “settings bị hỏng”.

Kiểm tra files/outputs này vì có thể chứa thông tin môi trường/private URLs. Không upload công khai nếu chưa rà soát.

## 11. Case 5: lỗi cache của lần resolve trước và `-U`

Maven Resolver có thể lưu kết quả không tìm thấy artifact/failed transfer vào local repository, thường qua các file `*.lastUpdated`, rồi không thử lại cho đến khi đủ update interval. Vì vậy sau khi parent POM vừa được deploy, Maven vẫn có thể báo:

```text
Failure to find com.example.build:company-parent:pom:2.4.0
was cached in the local repository, resolution will not be reattempted
until the update interval has elapsed
```

**Hãy sửa nguyên nhân thật trước**: parent đã publish chưa, GAV và repository URL đã đúng chưa, quyền download đã có chưa.

Sau đó có thể buộc Maven kiểm tra remote metadata/cached failure một lần:

```bash
mvn -B -ntp -U validate
```

`-U` giúp Maven thử cập nhật theo cơ chế của Resolver, nhưng **không sửa**:
- `relativePath` trỏ sai;
- GAV parent bị typo;
- parent POM thực sự chưa publish;
- repository 401/403;
- offline mode hoặc DNS/TLS hỏng.

Nếu buộc phải dọn cache, **chỉ nhắm artifact parent GAV bị lỗi** sau khi đã có backup/quyền phù hợp. Không xóa toàn bộ `~/.m2/repository` hoặc local repository dùng chung vì sẽ làm những project khác phải tải lại dữ liệu và có thể che nguyên nhân.

Một chẩn đoán tạm an toàn hơn là thử **local repo cô lập**:

```bash
mvn -B -ntp -Dmaven.repo.local=/tmp/maven-parent-probe validate
```

Đây là path ví dụ cho Linux/macOS; thư mục này sẽ được Maven tạo/nạp artifacts và có thể dùng network. Nếu không có quyền tải hoặc repository auth, lỗi vẫn còn. Trên Windows dùng thư mục tạm thuộc quyền bạn và syntax path thích hợp.

**Không lặp `mvn -U` mù quáng** khi lỗi thực là 401/404 hoặc POM coordinates sai.

## 12. Case 6: lỗi chỉ xảy ra ở CI hoặc sau khi di chuyển project

Một số pattern:

### 12.1. Developer có parent trong `.m2`, CI chưa có

Local developer từng chạy `mvn install` với parent. Child có `relativePath` sai nhưng vẫn dùng cached parent trong repository, nên build pass. CI sạch thiếu parent artifact, lỗi lộ ra.

Cách sửa tùy kiến trúc:
- Repo chứa parent source → sửa `relativePath` đúng, chạy reactor root.
- Parent corporate được publish → khai báo đúng parent GAV, `<relativePath/>`, cấu hình CI repository/auth.
- Parent chưa publish → thêm bước publish/install parent theo pipeline hợp lệ, không tạo build phụ thuộc vào cache cá nhân.

### 12.2. Chạy một child từ folder lẻ

Một multi-module reactor cần dependencies sibling có thể build thành công từ root, nhưng `mvn -f modules/app/pom.xml package` không resolve `parent-util` nếu util chưa được install. **Đó là lỗi dependency sibling**, khác với parent non-resolvable nếu parent local path đã đúng.

Nếu muốn build chọn module và kèm upstream trong reactor:

```bash
mvn -B -ntp -pl :parent-app -am verify
```

Chạy từ **root aggregator**. `-pl` chọn App; `-am` xây các required upstream modules trong reactor. Nó hữu ích **sau khi parent models resolve đúng**, chứ không phải lệnh “vá” sai parent GAV.

### 12.3. Checkout dạng monorepo khác nhau

Nếu CI chỉ lấy `modules/app` mà không checkout root `pom.xml`, `../../pom.xml` sẽ không còn tồn tại. Đó là khác biệt **input filesystem layout**. Có thể dùng sparse checkout giữ root parent và required modules, hoặc dùng parent artifact từ repository nếu được phát hành hợp lệ.

**Không hard-code absolute path** đến workstation trong `<relativePath>`, vì Maven build sẽ gãy ở máy khác.

### 12.4. Parent mới là SNAPSHOT

Ví dụ child:

```xml
<parent>
    <groupId>com.example.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>2.5.0-SNAPSHOT</version>
    <relativePath/>
</parent>
```

Nếu remote repository chỉ cho releases, SNAPSHOT không được tìm thấy. Cần repository có snapshots enabled và version đó đã deploy, không đổi thành release version không tồn tại chỉ để build pass. Với team, hãy phân biệt **SNAPSHOT repository policy** và **cache update interval**.

### 12.5. Maven chạy offline

```bash
mvn -B -ntp -o validate
```

`-o` yêu cầu Maven dùng artifacts đã có; nếu parent chưa được cài vào local repo, repository-only parent không thể tự được tải từ remote. Có thể thử online sau khi có network/credentials; nếu môi trường bắt buộc offline, cần chuẩn bị local repository đầy đủ đúng GAV.

## 13. Sửa đúng nguyên nhân: cây quyết định

```text
Non-resolvable parent POM
|
+-- Parent có trong cùng checkout?
|   |
|   +-- Có --> Từ child pom.xml xác định đúng relativePath
|   |          --> Kiểm file target có parent GAV khớp?
|   |          --> Sửa path hoặc GAV theo thiết kế
|   |          --> mvn validate từ root
|   |
|   +-- Không --> Parent đã install/deploy?
|               |
|               +-- Chưa --> Install/publish parent theo release workflow
|               |
|               +-- Rồi --> Dùng <relativePath/> khi chỉ lấy từ repo
|                          --> Kiểm local/remote repository thực
|
+-- Có 401/403? --> Kiểm settings servers, repository/mirror id, permissions
|
+-- Có 404/not found? --> Kiểm GAV, repository URL, releases/snapshots
|
+-- Timeout/TLS/DNS? --> Kiểm VPN/proxy/truststore/connectivity
|
+-- Cached failure? --> Sửa gốc trước, thử -U; dọn đúng artifact nếu cần
|
+-- Model đã resolve? --> Mới chạy effective-pom, compile, tests, package
```

Đây là flow text minh họa các nhánh, không phải shell script có thể chạy trực tiếp.

### Thứ tự thao tác an toàn

1. **Ghi log gốc và parent GAV**.
2. **Xác định nguồn parent dự định** (checkout hay repo).
3. **Kiểm file/GAV hoặc repository/settings** tùy nguồn đó.
4. **Sửa một điều kiện có bằng chứng**.
5. **Chạy `mvn validate`** để xác nhận qua bước dựng model.
6. **Chạy `mvn clean verify`** để xác nhận build thực.
7. **Dùng `help:effective-pom`** sau khi model đã đọc được để kiểm inheritance.
8. Nếu CI lỗi riêng, chạy cùng profiles/settings/toolchain và kiểm checkout layout.

## 14. Các lệnh chẩn đoán đáng nhớ

| Lệnh | Dùng khi nào | Cần lưu ý |
| --- | --- | --- |
| `mvn -version` | Biết Maven/JDK đang chạy | Toolchain/version chênh có thể che lỗi |
| `mvn -B -ntp validate` | Kiểm model nhanh | Không cần chạy tests |
| `mvn -B -ntp -e validate` | Xem stacktrace mức vừa | Không tự sửa parent |
| `mvn -B -ntp -X validate` | Cần debug resolver | Log có thể lộ metadata nhạy cảm |
| `mvn -B -ntp -U validate` | Parent mới publish/cached miss | Không cứu GAV/path sai |
| `mvn -B -ntp -N install` | Install parent POM root mà không build modules | Chỉ local repository |
| `mvn -B -ntp -pl :parent-app -am verify` | Build App cùng upstream modules | Phải chạy từ reactor root |
| `mvn -B -ntp -o validate` | Test khả năng offline | Parent phải có trong local repo hoặc local path |
| `mvn help:effective-settings` | Xem repositories/mirrors sau config | Dùng project model khỏe mạnh |
| `mvn help:effective-pom` | Xem inheritance sau khi resolve parent | Có thể fail nếu parent vẫn lỗi |

Không phải lệnh nào cũng cần chạy cho mọi trường hợp; chọn nhánh nhỏ nhất giải quyết được triệu chứng.

## 15. Các lỗi chẩn đoán sai cần tránh

### 15.1. Thấy `relativePath` là thêm `<relativePath/>` ngay

Nếu parent nằm trong checkout và chưa publish, giá trị rỗng loại bỏ con đường local có thể hoạt động. **Sửa đường dẫn đúng thay vì bỏ tra cứu local**.

### 15.2. Chỉ sửa `<repositories>` trong POM cha đang không tải được

Nếu Maven chưa thể resolve chính POM cha, những cấu hình ở bên trong nó **không tự cứu được bước tải POM cha đó**. Cấu hình repository đủ sớm ở child/settings/active profile phù hợp và xác nhận effective repositories.

### 15.3. Thêm `<pluginRepositories>` thay vì nơi tìm POM

Parent model là artifact type `pom`; `<pluginRepositories>` là nơi resolve Maven plugins. **Dùng `<repositories>`/settings** cho parent artifacts.

### 15.4. Đổi `groupId`/version để khớp nhầm local file

Một file POM ở path đúng nhưng không phải parent dự kiến không nên bị “hợp thức hóa” bằng cách đổi GAV child bừa bãi. Cần xác định thiết kế parent hierarchy thật.

### 15.5. Dùng `-U` cho lỗi 401/TLS

`-U` chỉ liên quan cơ chế update/check remote, không cấp quyền truy cập và không sửa chứng chỉ. Fix repository credentials/proxy/TLS theo chính sách bảo mật.

### 15.6. Cài/deploy parent bằng `-DskipTests` rồi bỏ qua build quality

Nếu parent build/release thực có quality requirements, không bỏ checks chỉ để lấp artifact thiếu. Với parent-only packaging `pom`, `-N install` có thể phù hợp để thử local resolution; release thật vẫn phải tuân pipeline.

### 15.7. Xóa toàn bộ `.m2` khi chỉ một GAV bị cache miss

Việc này tốn network, ảnh hưởng các dự án khác và có thể làm lỗi khó tái hiện. Sửa root cause, dùng `-U` hoặc isolated local repo nếu cần chẩn đoán, chỉ can thiệp đúng artifact sau khi chắc chắn.

### 15.8. Công khai settings và debug log chứa token

`settings.xml` có thể chứa credentials, mirror/internal URLs; `-X` log có thể hiển thị chi tiết môi trường. **Không đưa vào issue công khai mà chưa redaction**, không vô hiệu TLS để lấy BUILD SUCCESS.

### 15.9. Nhầm lỗi parent với lỗi dependency/plugin

Ba thông báo khác nhau:
- **Non-resolvable parent POM:** Maven không lấy được POM cha để dựng model.
- **DependencyResolutionException:** POM project đã được dựng nhưng Maven không lấy dependency artifact.
- **PluginResolutionException:** Maven không lấy được plugin/plugin dependency.

Thao tác sửa repository khác nhau có thể cần `<repositories>` hoặc `<pluginRepositories>` tùy **loại artifact thực sự thiếu**. Không áp một công thức chung.

## 16. Sau khi sửa parent: kiểm inheritance thật

Khi `mvn validate` đã pass:

```bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
```

Kiểm các properties/kế thừa trong `effective-pom.xml`:
- `groupId` và `version` của child đã inherited đúng?
- Compiler release 17 từ parent có hiệu lực?
- Surefire/Compiler Plugin versions đã đúng?
- JUnit dependencyManagement có đúng version, scope không?
- Profiles được kích hoạt theo mong đợi không?

**Không coi effective POM pass là toàn build pass.** Chạy tiếp:

```bash
mvn -B -ntp clean verify
```

Rồi chạy ứng dụng Java như mục 6.8, kiểm stdout đúng hai dòng. Nếu bài đang nói parent resolution, điều quan trọng nhất là Maven đi qua model building, không còn `Non-resolvable parent POM` và các inherited settings phù hợp.

## 17. Bài tập thực hành

### Bài 1 — Đếm cấp đường dẫn

Cấu trúc:

```text
repo/
├── pom.xml
└── products/
    └── payments/
        └── pom.xml
```

Hỏi: `products/payments/pom.xml` dùng `../pom.xml`, `../../pom.xml` hay `<relativePath/>` để lấy parent local? **Đáp án:** `../../pom.xml`.

### Bài 2 — File tồn tại nhưng wrong local POM

Từ `child/pom.xml`, `../pom.xml` tồn tại nhưng có artifactId `unrelated-root`. Child khai báo parent `company-parent:2.4.0`. Tại sao Maven cảnh báo? **Vì GAV không khớp**, không phải chỉ vì file thiếu.

### Bài 3 — Parent từ corporate repository

Child dùng `<relativePath/>`, remote private repository đã có parent, nhưng CI báo 401. Sửa đúng thứ gì? **Kiểm settings servers, repository/mirror id, credential scope và access rights**; không đổi relativePath thành `../../pom.xml` nếu không có local parent.

### Bài 4 — Parent đã deploy nhưng Maven vẫn cached miss

Sau khi kiểm artifact và auth có thật, chạy lệnh nào một lần để yêu cầu update? **`mvn -B -ntp -U validate`**. Nếu lỗi tiếp diễn, đọc nguyên nhân mới thay vì liên tục thử `-U`.

### Bài 5 — Parent chỉ install trên máy dev

Vì sao CI sạch vẫn fail dù build local pass? **Vì local repository là trạng thái riêng của từng máy**. Parent cần hiện diện trong checkout đúng path hoặc được CI tải từ repository có cấu hình/quyền đúng.

### Bài 6 — Maven parent versus aggregator

Nếu root POM chỉ có `<modules>` nhưng child không có `<parent>`, child có kế thừa compiler release 17 không? **Không**, chỉ aggregation không tạo inheritance.

### Bài 7 — Run Java 17

Nếu tạo đúng files mục 6, chạy từ root:

```bash
mvn -B -ntp clean verify
java -cp "modules/app/target/classes:modules/util/target/classes" com.example.diagnostics.app.Main
```

**Output Java chính xác:**

```text
Parent resolved: MAVEN
Blank fallback: GUEST
```

### Bài 8 — Root chạy tốt, child chạy lẻ fail

Nếu parent resolve đúng nhưng chạy `mvn -f modules/app/pom.xml package` báo thiếu `parent-util`, đó có chắc là parent POM không resolve không? **Không.** Đó có thể là dependency sibling chưa install; chạy reactor root với `-pl :parent-app -am verify` để có upstream module khi phù hợp.

## 18. Checklist chẩn đoán hoàn chỉnh

- [ ] Có log Maven gốc, biết child POM nào fail.
- [ ] Đọc parent GAV trong child: groupId, artifactId, version.
- [ ] Xác định parent phải lấy từ checkout hay repository.
- [ ] Nếu local: tính relativePath từ **child pom.xml**, không từ shell CWD.
- [ ] Kiểm file local parent tồn tại và có đúng GAV.
- [ ] Biết mặc định relativePath là `../pom.xml`.
- [ ] Chỉ dùng `<relativePath/>` khi chủ đích repository-only parent.
- [ ] Nếu remote: kiểm parent đã install/deploy đúng packaging `pom`.
- [ ] Kiểm đúng Maven local repository path thực tế.
- [ ] Kiểm repositories/settings profiles/mirrors.
- [ ] Không nhầm pluginRepositories với repositories cho parent.
- [ ] Kiểm snapshots/releases policy theo parent version.
- [ ] Kiểm 401/403, TLS, DNS, proxy/VPN trước khi sửa XML vô cớ.
- [ ] Chỉ dùng `-U` khi cần làm mới remote/cached miss.
- [ ] Không xóa cả `.m2`, không tắt SSL, không commit secrets.
- [ ] Nếu CI khác dev, kiểm checkout layout và local cache.
- [ ] Không tin `help:effective-pom` sẽ sửa parent chưa resolve.
- [ ] Chạy `mvn validate` sau khi sửa parent.
- [ ] Chạy `mvn clean verify` để xác nhận cả build.
- [ ] Kiểm effective inheritance và parent coordinates.
- [ ] Với multi-module, dùng root reactor và `-pl/-am` phù hợp.
- [ ] Không tự coi một warning relativePath là lỗi fatal nếu Maven resolve parent thành công qua repository.
- [ ] Ghi rõ nguyên nhân đã xác minh và thay đổi thực hiện.

**Kết luận:** `Non-resolvable parent POM` là lỗi Maven **không thể tạo effective model của child vì không lấy được parent POM**. Cần phân biệt **parent identity** (`groupId:artifactId:version`) với **parent location** (`relativePath`, local repository, remote repositories). `relativePath` mặc định là `../pom.xml`, tính từ thư mục POM con; file local phải khớp GAV. Khi parent đã publish và chủ đích lấy từ repository, dùng `<relativePath/>`; khi parent nằm trong checkout, sửa đường dẫn cho đúng. Chỉ sau khi kiểm path/GAV, mới chuyển sang repository/auth/cache network và xác minh bằng `mvn validate` rồi `mvn clean verify`.

## Nguồn tham khảo

- [Apache Maven — Maven Model Reference: parent, relativePath](https://maven.apache.org/ref/3-LATEST/maven-model/maven.html)
- [Apache Maven — Maven Parent model API](https://maven.apache.org/ref/3.10.0/apidocs/org/apache/maven/model/Parent.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings)
- [Apache Maven — Multiple Repositories and Resolution Order](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
- [Apache Maven — Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Apache Maven — UnresolvableModelException](https://cwiki.apache.org/confluence/display/MAVEN/UnresolvableModelException)
- [Apache Maven — ProjectBuildingException](https://cwiki.apache.org/confluence/display/MAVEN/ProjectBuildingException)
- [Apache Maven — PluginResolutionException](https://cwiki.apache.org/confluence/spaces/MAVEN/pages/4589202/PluginResolutionException)