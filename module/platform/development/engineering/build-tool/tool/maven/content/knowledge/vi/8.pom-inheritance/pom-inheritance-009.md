# Rủi ro tạo vòng tham chiếu giữa parent, BOM và mô-đun trong Maven

## 1. Mục tiêu: phân biệt ba kiểu quan hệ trước khi tìm vòng lặp

Trong dự án Maven nhiều module, một tệp `pom.xml` có thể vừa kế thừa **parent POM**, vừa import một **BOM (Bill of Materials)**, vừa phụ thuộc vào một **module** khác. Những quan hệ này trông giống nhau vì đều dùng tọa độ `groupId:artifactId:version`, nhưng Maven xử lý chúng ở những giai đoạn khác nhau.

Một cấu trúc thiếu định hướng có thể gây **circular parent inheritance**, **circular BOM import**, **reactor cyclic dependency**, hoặc tình trạng cần build module A mới tạo được parent/BOM của chính A. Kết quả thường là Maven không thể xây dựng effective POM, không phân giải được mô hình dự án, không sắp xếp được thứ tự build, hoặc phải dựa vào artifact cũ trong local repository.

Sau bài này, bạn sẽ:

1. Phân biệt **`<parent>`**, **`<dependencyManagement>` + `scope=import`**, **`<modules>`** và dependency thông thường.
2. Vẽ mũi tên phụ thuộc đúng chiều và phát hiện chu trình ở lớp **mô hình POM** hoặc **reactor build**.
3. Hiểu tại sao parent import BOM nhưng BOM lại dùng chính parent là cấu trúc nguy hiểm.
4. Biết cách tách BOM độc lập, làm gọn parent, hướng dependency giữa module theo một chiều và chẩn đoán lỗi Maven.
5. Thực hành với một bộ dự án Java 17 / JUnit 5 có parent, BOM và hai module **không tạo vòng**.

Bối cảnh minh họa dùng Maven 3.9.x với POM model 4.0.0. Maven 4 có thêm tính năng và packaging BOM riêng; ví dụ dạng `pom` ở đây vẫn là kiểu cấu hình phổ biến cho các dự án cần tương thích Maven 3. Khi chẩn đoán thực tế, luôn kiểm tra phiên bản Maven đang chạy.

## 2. Bốn loại mũi tên khác nhau trong Maven

### 2.1. Parent inheritance: module lấy cấu hình từ parent

POM con khai báo:

```xml
<parent>
    <groupId>com.example.academy</groupId>
    <artifactId>academy-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Đây là **đoạn XML** nằm trong POM con, không phải một POM độc lập. Nó diễn đạt quan hệ:

```text
app --[parent inheritance]--> academy-parent
```

Parent POM có `<packaging>pom</packaging>`. Nó giúp module con kế thừa `groupId` và `version` (khi không khai báo lại), `properties`, `dependencyManagement`, cấu hình plugin và nhiều thành phần khác. `artifactId` của module con vẫn riêng. Maven phải phân giải chuỗi parent để dựng **effective POM** của module.

Vòng kiểu `A parent B` đồng thời `B parent A` là vô nghĩa: muốn dựng model của A phải dựng B, mà B lại cần A. Dạng vòng dài `A → B → C → A` cũng sai.

### 2.2. BOM import: lấy quy tắc quản lý phiên bản, không kéo JAR vào classpath

Một BOM thường là POM có `packaging=pom` với `dependencyManagement`. Dự án khác import nó ở **bên trong `dependencyManagement`**:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.academy</groupId>
            <artifactId>academy-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Quan hệ:

```text
app --[BOM import]--> academy-bom
```

Import BOM đưa các **managed dependency versions** vào mô hình hiệu lực của consumer; import này **không tương đương** với việc thêm mọi artifact do BOM quản lý vào `<dependencies>`, và không tự khiến chúng xuất hiện trên runtime classpath. Consumer vẫn phải khai báo các dependency thực sự sử dụng, trừ các cơ chế khai báo khác của dự án.

**Đây cũng là quan hệ phải được giải quyết ở giai đoạn dựng mô hình POM.** Nếu A import B, B lại import A (trực tiếp hoặc qua các BOM khác), Maven không có chuỗi import hợp lệ để dựng dependency management. Cấu hình kiểu đó có thể gây lỗi mô hình/nhập BOM ngay trước khi source được biên dịch.

### 2.3. Aggregation: một POM liệt kê các module để build cùng nhau

POM aggregator có thể khai báo:

```xml
<packaging>pom</packaging>
<modules>
    <module>core</module>
    <module>app</module>
</modules>
```

Tức là aggregator **thu thập** `core` và `app` để reactor build chúng cùng lần chạy. `<modules>` không tự làm chúng kế thừa parent, cũng không tự thêm JAR của `core` vào dependency của `app`.

Đây là điểm dễ nhầm khi phân tích vòng: một POM có thể **vừa là parent vừa là aggregator**. Quan hệ `aggregator -> các thư mục module` và `module -> parent` đặt cạnh nhau trông giống hai mũi tên ngược chiều, nhưng **đó là cấu trúc Maven hoàn toàn bình thường**, không phải cứ thấy mũi tên hai chiều trên hình là reactor báo cycle.

Hãy phân loại cạnh theo **ngữ nghĩa** thay vì gộp tất cả thành một đồ thị vô danh. `<modules>` chỉ định thành viên build, còn `<parent>` chỉ định kế thừa model.

### 2.4. Dependency thực sự: module cần artifact khác

Ví dụ `app` dùng class ở `core`:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.academy</groupId>
        <artifactId>academy-core</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Quan hệ:

```text
app --[real dependency]--> academy-core
```

Reactor cần build `academy-core` trước `app`. Nếu `core` lại phụ thuộc trực tiếp vào `app`, hai project cùng nằm trong reactor và hình thành chu trình dependency, Maven không thể sắp xếp thứ tự hợp lệ.

**Managed dependency không có nghĩa là real dependency.** Chỉ đặt `academy-core` trong BOM/`dependencyManagement` không khiến reactor phải build core trước app. Theo hướng dẫn Maven, reactor sorting chủ yếu xét các quan hệ thực sự được khai báo/sử dụng (`dependencies`, plugin, extension, parent...), còn `dependencyManagement` và `pluginManagement` tự chúng không đặt thứ tự build.

## 3. Các vòng tham chiếu sai thường gặp

### 3.1. Vòng kế thừa parent POM

Giả sử có hai POM với định danh A và B:

```text
A --parent--> B
B --parent--> A
```

Một POM A chứa `<parent>` trỏ B, trong khi POM B lại chứa `<parent>` trỏ A. Tạo effective POM cho A cần B; muốn có B lại cần A. Maven sẽ báo lỗi mô hình về vòng kế thừa hoặc parent resolution, không phải lỗi thiếu class Java.

**Cách sửa:** quy hoạch chuỗi parent đi theo một chiều, ví dụ `company-parent → product-parent → app` nếu vẽ từ parent xuống child (khi dùng mũi tên inheritance `child → parent` thì chiều ngược lại). Parent cấp cao nhất không được kế thừa bất kỳ descendant nào.

### 3.2. Parent import BOM, nhưng BOM kế thừa chính parent

Đây là tình huống rất đáng chú ý vì xuất phát từ ý tưởng tưởng như hợp lý: muốn mọi module thống nhất version nên đặt BOM vào parent; đồng thời muốn BOM dùng cùng plugin/properties nên cho BOM kế thừa parent.

```text
academy-parent --[BOM import]--> academy-bom
academy-bom   --[parent]-----> academy-parent
```

Một đoạn trong `academy-parent/pom.xml`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.academy</groupId>
            <artifactId>academy-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Trong `academy-bom/pom.xml` lại có:

```xml
<parent>
    <groupId>com.example.academy</groupId>
    <artifactId>academy-parent</artifactId>
    <version>1.0.0</version>
</parent>
```

**Hai khối XML trên là ví dụ cấu hình sai, không ghép thành dự án để chạy.** Để dựng parent, Maven cần import BOM; để dựng BOM, Maven phải phân giải parent mà BOM đang kế thừa. Chu trình này có thể chặn quá trình tạo effective model.

Tài liệu Maven về dependency mechanism đặc biệt cảnh báo **không để POM nhập một BOM làm parent hoặc grandparent của chính BOM được nhập**; ở đây các liên kết được diễn đạt theo chiều import và inheritance. Nguyên tắc thực hành là **BOM được parent import phải độc lập với parent đó và chuỗi ancestor của parent**.

### 3.3. Hai BOM import lẫn nhau

```text
bom-a --[import]--> bom-b
bom-b --[import]--> bom-a
```

Dù không có mã Java, chu trình `dependencyManagement` vẫn có thể khiến mô hình không được giải quyết. Nếu cần quản lý những phiên bản dùng chung, hãy tạo **BOM nền độc lập** được cả A và B nhập, hoặc giữ việc quản lý ở một BOM duy nhất. Một BOM không nên phụ thuộc ngược vào BOM tiêu thụ nó.

### 3.4. Aggregator import BOM là một module con của chính nó

Một POM gốc `platform/pom.xml` vừa liệt kê `<module>bom</module>` vừa muốn import BOM này vào chính `dependencyManagement` của POM gốc. Khi Maven dựng model của root, BOM con có thể chưa được resolve từ repository; đồng thời việc nhập BOM là điều kiện để dựng root. Đây là **bootstrap problem** và được tài liệu Maven chính thức cảnh báo: **không cố import một POM được định nghĩa trong submodule của chính POM đang import**.

Nếu BOM đó còn có parent trỏ root thì tạo thêm vòng parent/import rõ rệt ở mục 3.2. Nhưng ngay cả khi BOM không có parent trỏ root, cấu trúc import submodule của chính importer vẫn có nguy cơ **không tìm thấy BOM ở thời điểm model building**. Không nên giải quyết bằng cách dựa vào một bản BOM cũ tình cờ còn trong `~/.m2`: clean build/CI có thể vẫn lỗi.

Một lưu ý tinh tế: **root có `<modules>` và children có `<parent>` trỏ root là bình thường**. Vấn đề nằm ở **BOM bị import theo hướng không thể bootstrap** hoặc dependency/plugin graph thật sự tạo vòng, chứ không phải tự thân từ việc root có module.

### 3.5. Vòng dependency giữa các module

```text
app  --[dependency]--> core
core --[dependency]--> app
```

Đối với hai module có dependency thực sự lẫn nhau, Maven reactor không thể tìm thứ tự để build cả hai từ đầu: app cần core đã build, core lại cần app đã build. Có thể thấy lỗi đại ý `The projects in the reactor contain a cyclic reference`. Thông báo chi tiết phụ thuộc phiên bản Maven và cấu hình.

**Cách sửa kiến trúc:** đưa những interface/model dùng chung xuống một module cấp thấp (ví dụ `common-api`), rồi cho app và core cùng phụ thuộc vào module này theo một chiều; hoặc đảo chiều bằng interface và dependency injection thay vì giữ vòng JAR vật lý.

Thêm version vào `dependencyManagement` **không khắc phục** quan hệ phụ thuộc vòng, bởi vì module vẫn có `<dependencies>` thực sự trỏ vào nhau.

## 4. Dấu hiệu lỗi và cấp độ phát sinh

| Dấu hiệu khi chạy Maven | Hướng kiểm tra |
| --- | --- |
| Parent POM có vòng hoặc không thể phân giải | Đọc chuỗi `<parent>` của từng POM; kiểm tra tọa độ, `relativePath` và parent đã có hay chưa |
| Lỗi liên quan `import` BOM / vòng import | Mở `dependencyManagement` của importer và BOM được import, lần theo chuỗi `scope=import` và parent của BOM |
| `Non-resolvable import POM` khi BOM nằm trong submodule | Kiểm tra BOM đã có trong repository lúc model được dựng chưa; có đang import child BOM ngay từ root không |
| `The projects in the reactor contain a cyclic reference` | Vẽ graph dependency/plugin/extension/parent giữa các module trong reactor, tìm chu trình |
| Build máy cá nhân PASS nhưng CI sạch FAIL | Có thể local repo đang chứa parent/BOM hoặc JAR từ build cũ, che một bootstrap problem |
| Thêm `<modules>` mà build order kỳ lạ | Kiểm tra real dependency/plugin edge; thứ tự trong `<modules>` không thay dependency graph |
| `dependency:tree` không cho thấy import BOM | Bình thường: BOM import là dependency management, không phải JAR runtime dependency |
| Maven báo duplicate/mismatch GAV | Kiểm tra module POM có tọa độ trùng hay `relativePath` chỉ nhầm vào POM khác |

Không khẳng định mọi lỗi đều có đúng một thông điệp cố định. Maven có thể báo model building, artifact resolution hoặc reactor cycle tùy loại quan hệ khiến quá trình thất bại trước.

## 5. Kiến trúc an toàn: Parent, BOM và module ở đúng vai trò

Một cách tổ chức dễ hiểu:

```text
workspace/
├── academy-bom/
│   └── pom.xml              # BOM độc lập, không parent về academy-parent
└── platform/
    ├── pom.xml              # parent + aggregator, KHÔNG import academy-bom
    ├── core/
    │   ├── pom.xml          # parent = platform/pom.xml
    │   └── src/main/java/com/example/academy/core/Greeter.java
    └── app/
        ├── pom.xml          # parent = platform, import academy-bom
        ├── src/main/java/com/example/academy/app/App.java
        └── src/test/java/com/example/academy/app/AppTest.java
```

Bốn kiểu quan hệ trong cấu trúc này:

```text
platform/pom.xml  --[aggregates]---------> core, app
core              --[parent]------------> platform/pom.xml
app               --[parent]------------> platform/pom.xml
app               --[BOM import]--------> academy-bom
app               --[real dependency]---> core
academy-bom       --[manages version]----> core's coordinates (metadata only)
```

- `academy-bom` **không kế thừa** `platform/pom.xml` và **không phải module con** mà platform cần import trong lúc dựng model.
- `platform/pom.xml` chỉ chia sẻ cấu hình build và gom các module, **không import chính BOM phải được tạo từ platform**.
- `app` import BOM độc lập để lấy version của `core`. `app` khai báo **real dependency** vào `core`, nên reactor hiểu phải build core trước app.
- `core` **không phụ thuộc** ngược vào app, nên không có vòng JAR/module.
- Việc root vừa aggregate app/core vừa là parent của chúng là **hợp lệ**, không phải vòng sai.

Ví dụ này chọn cách **cài BOM độc lập vào local repository trước** rồi mới build reactor. Trong tổ chức, BOM cũng có thể được release vào repository nội bộ trước khi consumer build. Không cần cố đóng toàn bộ BOM/parent/module vào một graph khiến Maven phải tự bootstrap một vòng.

## 6. Thực hành đầy đủ Java 17: một cấu trúc không có chu trình

Ví dụ sau gồm **4 file POM** (BOM, parent, core, app) cùng 3 file Java. Cần JDK 17+, Maven 3.9.x phù hợp và khả năng tải plugin/JUnit lần đầu. Các file dùng cùng tọa độ `com.example.academy` mang tính minh họa.

### 6.1. `workspace/academy-bom/pom.xml` — BOM độc lập

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example.academy</groupId>
    <artifactId>academy-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.academy</groupId>
                <artifactId>academy-core</artifactId>
                <version>1.0.0</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

BOM **quản lý version**, không chứa `<parent>` trỏ `academy-parent`, không có `<modules>` và không khai báo runtime dependency lên `app`. Việc quản lý version của `academy-core` **không yêu cầu core JAR đã được build** để cài BOM dạng POM.

### 6.2. `workspace/platform/pom.xml` — parent và aggregator

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example.academy</groupId>
    <artifactId>academy-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Parent đặt Java release và phiên bản plugin cho module con. Không cần import BOM vào parent để đạt mục tiêu đó. Trong một hệ thống thật, bạn có thể tách **parent cấu hình build** và **aggregator gom module** thành hai POM nếu cần; không bắt buộc nhưng đôi khi giúp giảm coupling và bootstrap problems.

### 6.3. `workspace/platform/core/pom.xml` — module thư viện

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.academy</groupId>
        <artifactId>academy-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>academy-core</artifactId>
</project>
```

**Lưu ý:** Khi sao chép ví dụ trên, dùng đúng giá trị `xsi:schemaLocation` chuẩn ở ba POM còn lại, tức `http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd`. `groupId` và `version` của core được kế thừa từ parent; artifactId khác với parent. Không có dependency vào `app`, nên thư viện ở lớp thấp hơn không cần biết consumer.

### 6.4. `workspace/platform/core/src/main/java/com/example/academy/core/Greeter.java`

```java
package com.example.academy.core;

public final class Greeter {
    private Greeter() {
    }

    public static String say(String name) {
        return "Hello, " + name + "!";
    }
}
```

Mã thư viện Java 17 này không cần class `main` vì đây là module phục vụ consumer, không phải chương trình độc lập.

### 6.5. `workspace/platform/app/pom.xml` — module consumer import BOM

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.academy</groupId>
        <artifactId>academy-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>academy-app</artifactId>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.academy</groupId>
                <artifactId>academy-bom</artifactId>
                <version>1.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>com.example.academy</groupId>
            <artifactId>academy-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Maven lấy version của `academy-core` và `junit-jupiter` từ BOM đã import. Nhưng để core thật sự được đưa vào classpath, `app` vẫn phải có `<dependencies><dependency>...academy-core...`. `scope=test` là cách consumer dùng JUnit, **không phải** thuộc tính của BOM.

### 6.6. `workspace/platform/app/src/main/java/com/example/academy/app/App.java`

```java
package com.example.academy.app;

import com.example.academy.core.Greeter;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.say("Maven"));
    }
}
```

### 6.7. `workspace/platform/app/src/test/java/com/example/academy/app/AppTest.java`

```java
package com.example.academy.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.academy.core.Greeter;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void greeterProducesExpectedMessage() {
        assertEquals("Hello, Maven!", Greeter.say("Maven"));
    }
}
```

### 6.8. Lệnh build theo đúng thứ tự

Mở terminal **ở thư mục `workspace/`** trong sơ đồ. Đầu tiên cài BOM độc lập vào local repository; bước này **không cần** core/app đã build:

```bash
mvn -f academy-bom/pom.xml install
```

Sau đó chạy reactor của parent, để Maven sắp xếp core trước app:

```bash
mvn -f platform/pom.xml clean verify
```

Để chạy chương trình sau khi build, từ thư mục `workspace/` trên **Linux/macOS**:

```bash
java -cp "platform/app/target/classes:platform/core/target/classes" com.example.academy.app.App
```

Trên **Windows PowerShell/CMD**, classpath phân tách bằng dấu chấm phẩy:

```powershell
java -cp "platform\app\target\classes;platform\core\target\classes" com.example.academy.app.App
```

Stdout chính xác **chỉ của lệnh `java` cuối** là:

```text
Hello, Maven!
```

Lệnh `mvn ... clean verify` in log dài hơn tùy máy/JDK/repository, vì thế không coi những dòng tải plugin hay tổng thời gian là stdout cố định. `AppTest` chạy ở phase `test`; các JAR/plugin cần có trong cache hoặc tải được từ repository. Java runtime của ví dụ chỉ cần class `App` và `Greeter`, nên hai đường dẫn `target/classes` là đủ.

**Vì sao không build app đơn lẻ ngay từ đầu?** Nếu bạn chạy `mvn -f platform/app/pom.xml verify` khi core chưa có trong local repository, Maven có thể không phân giải được `academy-core`. Chạy từ `platform/pom.xml` đưa **cả core và app** vào cùng reactor; `app` được sắp sau `core` do dependency thật. Nếu chỉ muốn app cùng các dependency nội bộ, có thể dùng reactor selection `-pl :academy-app -am` từ root.

### 6.9. Nhìn lại: điều gì làm ví dụ này không có vòng sai?

- BOM là POM độc lập và có thể cài trước khi build consumer.
- Parent/aggregator không import BOM được sinh từ chính module của nó.
- Core và app đều kế thừa parent theo chiều từ child lên parent, nhưng parent không kế thừa ngược từ child.
- App import BOM để quản lý version, không yêu cầu BOM kế thừa app hoặc parent.
- App phụ thuộc core; core không phụ thuộc app.
- Maven reactor có thứ tự build hợp lệ: parent model → core artifact → app artifact (mô tả khái niệm; các bước model resolution xảy ra trước khi biên dịch).

## 7. Chẩn đoán vòng tham chiếu có hệ thống

### Bước 1. Xác định lỗi nằm ở model hay reactor

Chạy từ root POM của dự án gặp lỗi:

```bash
mvn -version
mvn -e validate
```

`validate` đủ để yêu cầu Maven xây dựng project model và reactor cho nhiều lỗi cấu hình, trong khi không phải biên dịch mã. `-e` in stack trace hỗ trợ phân tích. Nếu ngay trước `validate` đã báo `Non-resolvable parent POM` hay `Non-resolvable import POM`, tập trung vào phân giải parent/BOM. Nếu lỗi nói `cyclic reference` trong reactor, tập trung vào dependency/build graph giữa module.

### Bước 2. Vẽ ba graph tách biệt

Dùng tên thực tế của các POM và ký hiệu:

```text
PARENT:      module -> parent
BOM IMPORT:  consumer -> imported BOM
DEPENDENCY:  module -> module/library thực sự cần
AGGREGATION: root -> đường dẫn các module được thu thập
```

Lần theo PARENT và BOM IMPORT để tìm vòng model, rồi xét các cạnh thật giữa các project đang tham gia reactor. **Không coi mọi cạnh AGGREGATION + PARENT trên cùng hai tệp là một vòng lỗi**: root vừa gom module vừa là parent chính là mô hình Maven rất phổ biến.

### Bước 3. Kiểm tra `relativePath` và tọa độ

Parent resolution theo Maven có thể tìm từ đường dẫn tương đối (thường mặc định `../pom.xml`) trước khi tìm repository. Kiểm tra:

- `<parent><groupId>...<artifactId>...<version>...` có trùng parent thật không?
- `relativePath` có đang trỏ nhầm vào một POM con hoặc POM có GAV khác không?
- Parent/BOM đã được cài/phát hành vào repository mà consumer đang sử dụng chưa?
- Có bản parent/BOM **cũ** nằm trong local cache khiến máy này chạy được nhưng CI sạch thất bại không?

Nếu parent chỉ được lấy từ repository, có thể dùng `<relativePath/>` để tránh Maven dò `../pom.xml` trên Maven 3; nhưng làm thế **không xóa được vòng kế thừa thực sự**. Đây chỉ là thay đổi cách tìm parent.

### Bước 4. Xem mô hình hiệu lực và phụ thuộc (khi project load được)

```bash
mvn help:effective-pom
mvn dependency:tree
```

`help:effective-pom` giúp nhìn cấu hình đã kế thừa và quản lý version; `dependency:tree` giúp phân tích dependency thực sự được chọn. Nếu chính model loading đã thất bại vì cycle, hai lệnh này **cũng có thể thất bại trước khi in được kết quả**. Khi đó phải đọc các POM nguồn và dò graph thủ công hoặc dùng công cụ phân tích XML ngoài Maven; không chờ `dependency:tree` “tự chữa” vòng import.

### Bước 5. Cắt đúng cạnh, không bỏ qua kiểm thử

- Vòng parent: **đổi cấu trúc kế thừa**, không đặt POM con làm ancestor của chính nó.
- Vòng import: **tách BOM độc lập**, không import parent/descendant theo vòng.
- Vòng module dependency: **trích xuất interface/model chung**, đảm bảo module cấp thấp không dùng ngược module cấp cao.
- Bootstrap problem: build/release BOM độc lập trước rồi consumer mới import, hoặc dùng quy trình artifact repository rõ ràng.
- Khác biệt local/CI: thử clean environment có kiểm soát, ghim version và bảo đảm pipeline build có đủ artifact cần thiết.

Không nên đổi sang `mvn -DskipTests` để “xử lý” lỗi circular POM: Maven cần dựng model và sắp reactor **trước** khi bước unit test có cơ hội chạy; skip test không giải quyết vòng.

## 8. Thiết kế parent, BOM và module để giảm rủi ro lâu dài

| Quy tắc | Vì sao có ích |
| --- | --- |
| Parent tập trung cấu hình build/plugin/JDK và có hướng kế thừa rõ ràng | Tránh parent kéo cấu hình phụ thuộc vào child/consumer của nó |
| BOM quản lý các version, **không phụ thuộc ngược** vào parent import nó | Tránh vòng model giữa parent và BOM |
| Nếu root muốn import BOM, BOM nên được release **độc lập trước** và không là submodule của importer | Tránh bootstrap problem |
| Module thư viện nền tảng không phụ thuộc module ứng dụng | Giữ dependency graph có thứ tự build |
| `<modules>` chỉ gom các project; `<dependencies>` mới khai báo dependency thật | Không nhầm aggregator với classpath/build dependency |
| Có phiên bản release rõ ràng cho parent/BOM và quản lý nguồn artifact | Tránh CI dựa vào SNAPSHOT hoặc local cache bất ngờ |
| Dùng một hướng dependency cho API và implementation | Giúp tách interface dùng chung ra khỏi implementation |
| Xem xét quy tắc Maven 3 và Maven 4 khi migration | Maven 4 có thêm mô hình BOM/đa project; không suy diễn mọi cơ chế giống hệt Maven 3 |
| Chạy kiểm tra trên CI clean repository hợp lý | Phát hiện các bản parent/BOM “tình cờ có sẵn” ở máy người phát triển |

**Một lưu ý nâng cao:** nếu BOM cần kế thừa một POM cấu hình dùng chung, POM đó vẫn phải **không phụ thuộc và không import ngược BOM hoặc bất kỳ POM nào phụ thuộc vào BOM**. Tuy nhiên, trong nhiều dự án, BOM chỉ cần POM đơn giản chứa dependencyManagement; giữ nó độc lập thường là lựa chọn dễ giải thích và phát hành nhất.

Trong Maven 4, tài liệu chính thức mô tả thêm `bom` packaging dành cho model mới và cách xuất bản tương thích Maven 3. Dù công cụ thay đổi, nguyên tắc thiết kế vẫn là tránh vòng parent/import và duy trì thứ tự build module hợp lệ.

## 9. Bài tập tự kiểm tra

**Tình huống A:** `parent` import `bom`; `bom` có `<parent>` trỏ `parent`. Đây là vòng gì, và bạn cắt cạnh nào trước? Gợi ý: nếu BOM không cần kế thừa parent, bỏ quan hệ ấy và cung cấp cấu hình BOM một cách độc lập; hoặc thiết kế lại để không import BOM từ ancestor của nó.

**Tình huống B:** aggregator `root` liệt kê `core` và `app`; cả hai khai báo parent là `root`, `app` dependency vào `core`. Có vòng lỗi không? **Không chỉ vì thế**: đây là trường hợp parent + aggregator hợp lệ với dependency app → core một chiều.

**Tình huống C:** `core` thêm dependency tới `app` trong khi `app` đã phụ thuộc `core`. Maven báo reactor cycle. Hãy trích xuất `common-api` chứa model/interface để `core` và `app` dùng theo hướng không vòng.

**Tình huống D:** BOM nằm trong `root/modules`, còn root import BOM trong `dependencyManagement`. Máy một thành viên chạy được, CI mới setup lại không tìm thấy import POM. Hãy phân tích vì sao **artifact BOM cũ trong local repo** có thể che bootstrap problem và tại sao cần kiến trúc build/release BOM độc lập.

**Tình huống E:** bạn chạy `mvn dependency:tree` nhưng Maven không thể resolve parent. Tại sao không có output tree? **Vì bước dựng mô hình POM thất bại trước khi Maven có thể phân tích dependency graph**.

Khi nắm chắc bài học này, bạn có thể phân biệt **vòng kế thừa/import BOM ở model building** và **vòng phụ thuộc giữa module ở reactor sorting**, đồng thời thiết kế POM sao cho quá trình build không phải dựa vào chính artifact mà nó đang cố tạo.

### Tài liệu Maven chính thức

- [Introduction to the POM — parent inheritance và aggregation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [POM Reference — parent, dependencyManagement, aggregation](https://maven.apache.org/pom.html)
- [Introduction to the Dependency Mechanism — BOM import và những trường hợp vòng cần tránh](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Guide to Working with Multiple Modules — reactor sorting](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven Model Builder — effective model và model resolution](https://maven.apache.org/ref/3.9.9/maven-model-builder/)
