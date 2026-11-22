# Vì sao khai báo quản lý không tự thêm thư viện vào dự án?

> **Build Tool Maven · BOM và quản lý chung**  
> Chủ đề cốt lõi: **`dependencyManagement` và BOM quy định cách chọn phiên bản/cấu hình khi một dependency được sử dụng; `dependencies` mới khai báo dependency thực sự của project.**

## 1. Câu trả lời ngắn gọn

Trong Maven, **quản lý dependency** và **sử dụng dependency** là hai hành động riêng biệt:

- **`<dependencyManagement>`** là nơi xác định **quy tắc** cho một artifact: thông thường là version, có thể gồm scope, type hoặc exclusions. Nó **không tự quyết định** rằng mọi module đều phải tải và sử dụng artifact ấy.
- **`<dependencies>`** là nơi project tuyên bố **những thư viện nó thực sự phụ thuộc**. Một dependency khai báo ở đây được Maven đưa vào đồ thị phụ thuộc; các JAR cần thiết có thể đi vào classpath compile, test và runtime tùy scope.
- **BOM (Bill of Materials)** là POM đóng vai trò **danh mục các phiên bản/cấu hình được quản lý**. Import BOM vào `dependencyManagement` không có nghĩa import toàn bộ những JAR mà BOM quản lý vào ứng dụng.
- **`<parent>`** cho phép kế thừa cấu hình từ POM cha, trong đó có `dependencyManagement`. Kế thừa bảng quản lý phiên bản **vẫn không tự thêm JAR** vào module con.

Ví dụ, BOM quản lý `jackson-databind` version `2.17.2`; module muốn dùng `ObjectMapper` phải có **dependency declaration** tương ứng. Nếu chỉ import BOM, Java compiler có thể báo `package com.fasterxml.jackson.databind does not exist`, mặc dù `mvn validate` đã đọc BOM thành công.

Một cách nhớ:

> **Management trả lời “nếu cần thư viện X thì dùng phiên bản/cấu hình nào?”; Dependencies trả lời “dự án này thật sự cần thư viện nào?”**

Sau bài học, bạn có thể tự giải thích, thực hành và chẩn đoán hai bước này trong dự án Java 17, POM kế thừa và reactor nhiều module.

## 2. Mô hình tư duy: bảng quản lý khác đồ thị phụ thuộc

Hãy hình dung Maven có hai tập thông tin:

```text
                     POM HIỆU LỰC CỦA MODULE
                                |
                 +--------------+--------------+
                 |                             |
                 v                             v
         dependencyManagement              dependencies
         (BẢNG QUY TẮC)                   (DANH SÁCH DÙNG)
                 |                             |
       Jackson databind -> 2.17.2             |  nếu có declaration
       Jackson core     -> 2.17.2             +----> jackson-databind
       Jackson annotations -> 2.17.2                   |
                 |                                     +--> jackson-core
                 |                                     +--> jackson-annotations
                 |                             |
        KHÔNG TỰ TẠO CẠNH                 ĐƯA VÀO DEPENDENCY GRAPH
        TRONG DEPENDENCY GRAPH            VÀ CLASSPATH THEO SCOPE
```

Phía trái giống **bảng chính sách chọn phiên bản**. Phía phải là **nhu cầu sử dụng** của module. Khi Maven thấy một dependency được khai báo trong `<dependencies>` hoặc đi vào đồ thị chuyển tiếp (*transitive dependency*), nó dùng các quy tắc management thích hợp để tính cấu hình hiệu lực.

Điều này là một thiết kế quan trọng cho dự án nhiều module. Nếu parent quản lý 100 thư viện nhưng module `api` chỉ cần 2 thư viện và module `web` cần 10, ta không muốn mỗi module tự động nhận cả 100 JAR. **Quản lý chung không đồng nghĩa sử dụng chung.**

### 2.1. Bảng phân biệt ba cấu trúc dễ nhầm

| Cấu trúc | Nơi khai báo | Tác dụng chính | Có tự thêm JAR vào module? |
| --- | --- | --- | --- |
| `dependencyManagement` | `project/dependencyManagement/dependencies` | Quản lý version/scope/metadata cho dependency được gặp trong graph | **Không** |
| `dependencies` | `project/dependencies` | Khai báo dependency trực tiếp của project; giải quyết transitive dependencies | **Có**, theo scope và artifact type |
| BOM import | Một dependency `type=pom`, `scope=import` **bên trong** `dependencyManagement` | Nhập các mục management từ POM khác | **Không** |
| `parent` | `project/parent` | Kế thừa mô hình, gồm management và các cấu hình được kế thừa | **Không chỉ nhờ quản lý**; xem phân biệt parent `dependencies` ở phần 8 |
| `pluginManagement` | `project/build/pluginManagement` | Quản lý version/cấu hình plugin | Không tự chạy plugin tùy ý |
| `build/plugins` | `project/build/plugins` | Khai báo plugin thực sự tham gia cấu hình build | Có thể thực thi goal nếu được bind/called |

Cột “Có tự thêm JAR?” nói về **classpath dependency của project Java**, không phải chính POM metadata hoặc plugin dependencies. Maven vẫn cần **tải hoặc đọc file BOM POM** để xác định các version được quản lý, nhưng bước ấy khác hoàn toàn với tải và thêm mọi JAR được liệt kê trong BOM.

## 3. `dependencyManagement` làm những gì?

Một POM có thể quản lý hai thư viện:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-core</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **fragment XML**, chưa phải một POM đầy đủ.

Nó có nghĩa:

1. Nếu model của module cần `jackson-databind` và phiên bản của dependency đó được quản lý theo mục này, Maven có quy tắc chọn version `2.17.2`.
2. Nếu module **không** khai báo `jackson-databind`, cũng không có dependency chuyển tiếp nào đòi hỏi nó, **management không tự sinh dependency**.
3. Nếu một module khác muốn dùng `jackson-databind`, nó có thể khai báo dependency ở cấp module và bỏ `version` khi management phù hợp đã có hiệu lực.
4. Với dependency chuyển tiếp, management của **project đang build** có thể ảnh hưởng version/scope hiệu lực theo quy tắc Maven. Đây là quản lý dependency đã tham gia đồ thị, **không phải tự thêm một artifact không hề được yêu cầu**.

Điều này có ích cho dự án nhiều module: một parent hoặc BOM có thể quản lý nhiều version mà không làm mọi module cồng kềnh.

### 3.1. Khi module thật sự cần Jackson

Khai báo trực tiếp:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Maven có thể lấy version `2.17.2` từ bảng management ở trên. **Không cần lặp lại `<version>2.17.2</version>`** nếu quản lý đó đang áp dụng.

Nếu module không có management tương ứng và khai báo JAR không có `version`, Maven 3 thông thường báo lỗi model kiểu:

```text
'dependencies.dependency.version' for
com.fasterxml.jackson.core:jackson-databind:jar is missing.
```

Đây là **dạng lỗi minh họa**; số dòng, phần prefix và định dạng log thay đổi theo Maven version. Maven không thể tự đoán một version đáng tin chỉ vì người dùng bỏ trống trường version.

### 3.2. `dependencyManagement` không chỉ là `<version>`

Ngoài version, mục management có thể xác định `scope`, `type`, `classifier`, `exclusions` và các thông tin Maven cho phép. Cấu hình hiệu lực phụ thuộc cách khai báo trực tiếp và cách Maven hợp nhất từng trường.

Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>shared-api</artifactId>
            <version>1.3.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây **không** phải lệnh thêm `shared-api` vào tất cả modules. Module thực sự dùng API đó mới khai báo:

```xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>shared-api</artifactId>
</dependency>
```

Nếu scope được quản lý và module không chỉ định scope khác, Maven có thể áp dụng `provided` từ management. **Vẫn phải có artifact thật** tại repository và cách sử dụng scope hợp lý. Tọa độ `org.example:shared-api:1.3.0` chỉ là minh họa cấu trúc, không giả định Maven Central có artifact này.

## 4. BOM là gì và tại sao import BOM vẫn không có JAR?

**BOM — Bill of Materials** là một POM công bố các mục dependencyManagement cho một tập thư viện được thiết kế/kiểm thử cùng nhau. Ví dụ BOM của Jackson định nghĩa version cho Jackson Databind, Jackson Core, Jackson Annotations và nhiều module Jackson khác.

Trong **Maven 3.x**, cách import BOM tiêu chuẩn là khai báo nó **bên trong** `dependencyManagement` với:

- `<type>pom</type>`
- `<scope>import</scope>`
- Tọa độ đúng: `groupId`, `artifactId`, `version`

Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.17.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Maven tải **POM artifact** `com.fasterxml.jackson:jackson-bom:2.17.2`, đọc các mục quản lý dependency trong đó, và tích hợp chúng vào bảng management hiệu lực. Nó không diễn giải “import” là “mọi artifact trong BOM đều trở thành `<dependencies>`”.

Đối với chính Jackson BOM `2.17.2`, các tọa độ được dùng trong bài:

```text
BOM artifact:
  com.fasterxml.jackson:jackson-bom:pom:2.17.2

Một artifact BOM quản lý:
  com.fasterxml.jackson.core:jackson-databind:jar:2.17.2

Một số artifact liên quan:
  com.fasterxml.jackson.core:jackson-core:jar:2.17.2
  com.fasterxml.jackson.core:jackson-annotations:jar:2.17.2
```

Lưu ý: các Jackson JAR chỉ được chọn vào **resolved dependency graph** khi project có một dependency trực tiếp hoặc chuyển tiếp cần tới chúng.

### 4.1. Scope `import` không giống scope `compile`

`import` là scope đặc biệt, **chỉ có ý nghĩa** với dependency `type=pom` **trong `<dependencyManagement>`**. Nó dùng để thay mục import bằng nội dung dependencyManagement của POM được import.

Đừng làm như sau:

```xml
<!-- SAI MỤC ĐÍCH: không phải cách nhập BOM vào bảng management -->
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson</groupId>
        <artifactId>jackson-bom</artifactId>
        <version>2.17.2</version>
        <type>pom</type>
        <scope>import</scope>
    </dependency>
</dependencies>
```

Đây là **phản ví dụ**, không phải file POM dùng để build. `scope=import` nằm sai ngữ cảnh nếu đặt trong `<dependencies>` thường. Một BOM cũng **không phải thư viện JAR** chứa `ObjectMapper` để bạn import class từ đó.

### 4.2. BOM quản lý version không có nghĩa tất cả module cùng cần thư viện

Giả sử BOM quản lý 30 artifacts. Một module chỉ xử lý JSON với `jackson-databind`; module khác cần thêm `jackson-dataformat-xml`; module thứ ba không xử lý JSON. Mỗi module **chỉ khai báo những dependencies cần dùng**. BOM giúp phiên bản của chúng đồng bộ mà không gây ra 30 dependencies không cần thiết.

Đây chính là giá trị của BOM: **giảm lặp lại version và tạo chính sách tương thích nhất quán**, không thêm thư viện đại trà.

## 5. Ví dụ Java 17 hoàn chỉnh: chỉ import BOM thì chưa biên dịch được

Bài thực hành gồm hai trạng thái của **cùng một project**:

- **Giai đoạn A:** import Jackson BOM nhưng **chưa có direct Jackson dependency**. Maven đọc BOM thành công, song Java code dùng `ObjectMapper` không compile vì thiếu JAR trên classpath.
- **Giai đoạn B:** thêm direct dependency `jackson-databind` **không ghi version**. Maven lấy version từ BOM, resolve JAR và các transitive dependencies; Java biên dịch và chạy được.

Đây là một kiểm nghiệm rõ ràng: **BOM quản lý version; direct declaration đưa thư viện vào project**.

### 5.1. Cấu trúc project

```text
bom-management-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── App.java
```

Cần **JDK 17+**, **Maven 3.x** và Internet/repository cache phù hợp để giải quyết BOM/plugin/JAR.

### 5.2. POM ban đầu: chỉ quản lý, chưa khai báo dùng Jackson

Tạo `bom-management-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>bom-management-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.fasterxml.jackson</groupId>
                <artifactId>jackson-bom</artifactId>
                <version>2.17.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Đọc POM này từng bước:**

1. Project là JAR Java 17, tọa độ `org.example:bom-management-demo:1.0.0`.
2. `dependencyManagement` import một BOM phát hành dưới dạng POM.
3. **Không có block `<dependencies>` cấp project.** Do đó, project chưa yêu cầu `jackson-databind` là dependency trực tiếp.
4. Maven Compiler Plugin được ghim version; điều này không tự cung cấp thư viện JSON cho mã ứng dụng.
5. Đường `target/` là thư mục output khi Maven biên dịch thành công; chưa cần tự tạo.

### 5.3. File Java: src/main/java/org/example/App.java

```java
package org.example;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        String json =
                mapper.writeValueAsString(Map.of("status", "BOM works"));

        System.out.println(json);
    }
}
```

Mã **đúng Java 17**, package và vị trí file nhất quán. `Map.of` tạo một map chỉ có **một phần tử**, nên không phụ thuộc thứ tự duyệt của map nhiều phần tử khi đối chiếu stdout. `ObjectMapper` thuộc **`jackson-databind`**.

### 5.4. Thử giai đoạn A

Chạy từ thư mục `bom-management-demo/`:

```bash
java -version
javac -version
mvn -version
mvn validate
mvn clean compile
```

**Kỳ vọng:**

- `mvn validate` có thể thành công nếu BOM POM được resolve và mô hình Maven hợp lệ. Đây là bước **xây dựng/kiểm tra model**, không phải bước biên dịch Java.
- `mvn clean compile` **thất bại**, vì module chưa khai báo dependency chứa class `ObjectMapper`.

Thông báo compiler có thể có dạng:

```text
package com.fasterxml.jackson.databind does not exist
cannot find symbol: class ObjectMapper
```

Đây là **dạng lỗi minh họa**, không phải bản chép log chính xác theo mọi OS/JDK/compiler. Lỗi không có nghĩa BOM không quản lý `jackson-databind`; nó có nghĩa **JAR chưa được đưa lên compile classpath**.

**Quan trọng:** bạn không sửa bằng cách đưa `jackson-bom` vào `<dependencies>` thường. Bạn phải thêm **artifact JAR thực sự cần dùng**.

### 5.5. Kiểm tra dependency tree khi chỉ import BOM

Bạn có thể gọi:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core
```

Ở giai đoạn A, graph của project **không có direct `jackson-databind` dependency**, nên đừng kỳ vọng tree sẽ liệt kê tất cả các Jackson JAR chỉ vì POM có BOM import. Maven có thể tải metadata BOM và một số plugin để thực hiện goal; **metadata resolution không đồng nghĩa các library JAR được thêm vào graph của project**.

Lưu ý output tree có thể có các thông tin project/POM hoặc plugin log; không nên yêu cầu terminal hoàn toàn trống. Câu hỏi cần trả lời là **có `com.fasterxml.jackson.core:jackson-databind` trong resolved dependency graph hay chưa**.

### 5.6. Giai đoạn B: khai báo dependency thực sự

**Giữ nguyên BOM import** và thêm block này ở cấp `<project>`, cùng cấp với `<dependencyManagement>`:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Chú ý **cố tình không viết `<version>`**. Maven sẽ tra bảng management do Jackson BOM cung cấp và dùng version `2.17.2`.

Mô hình mong muốn:

```text
project
  |
  +-- dependencyManagement
  |     |
  |     +-- jackson-bom:pom:2.17.2 (import)
  |
  +-- dependencies
  |     |
  |     +-- jackson-databind:jar:(version lấy từ BOM)
  |
  +-- build / plugins
        |
        +-- maven-compiler-plugin
```

Đây là hai block **khác nhau**. Mỗi block chỉ xuất hiện một lần ở cấp project (ngoại trừ cấu hình kế thừa hợp lệ); không dán `<dependencies>` **bên trong** `<dependencyManagement>` rồi trông chờ Maven tự nhận nó là dependency trực tiếp.

### 5.7. Build và chạy chương trình

Sau khi thêm direct dependency:

```bash
mvn clean package
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=org.example.App
```

**Stdout chính xác của chương trình Java**:

```text
{"status":"BOM works"}
```

Đây là stdout do `App.main` tạo; Maven Exec Plugin có thể ghi log riêng tùy thiết lập. Chúng ta dùng goal Exec Plugin với version cố định `3.5.1` để chạy chương trình bằng classpath dependencies Maven đã resolve. Không cần thêm plugin này vào POM cho bài học.

**Tại sao không chạy ngay `java -cp target/classes org.example.App`?** Vì `target/classes` chỉ chứa classes của project, không tự chứa Jackson JAR. Lệnh `java` thuần cần đầy đủ external classpath; Exec Plugin tự dựng classpath Maven phù hợp. Tương tự, `java -jar target/bom-management-demo-1.0.0.jar` không tự tạo executable/fat JAR chỉ vì Jackson đã là dependency. Bài thực hành không cấu hình manifest Main-Class hay shading.

### 5.8. Xác minh version và đồ thị sau khi khai báo

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core
mvn help:effective-pom -Doutput=effective-pom.xml
```

Giờ tree sẽ có `jackson-databind` là **direct dependency**. Jackson Databind còn có transitive dependencies như `jackson-core` và `jackson-annotations`; versions cuối có thể chịu tác động của BOM, dependencyManagement bổ sung hoặc dependency mediation trong project lớn.

Đối với **POM mẫu duy nhất** chỉ import Jackson BOM `2.17.2`, các version Jackson Core/Annotations/Databind chính được căn theo BOM đó. Trong effective POM, bạn có thể thấy nhiều **managed dependencies** do BOM nhập, nhưng graph thực tế chỉ gồm những artifact cần tới bởi dependency trực tiếp và transitive.

Cần đối chiếu **cả hai**:

- `effective-pom` cho biết **quy tắc management** và declarations hiệu lực.
- `dependency:tree` cho biết **đồ thị dependency đã được chọn**.

Một người mới thường mở effective POM thấy vài chục mục trong `dependencyManagement`, rồi tưởng Maven đã kéo ngần ấy JAR. Cách hiểu đó **sai**.

## 6. Vì sao BOM import hoạt động theo cách này?

### 6.1. BOM giải quyết vấn đề phiên bản, không giải quyết nhu cầu sử dụng

Nếu `module-a` dùng Jackson Databind, `module-b` dùng Jackson Dataformat XML, `module-c` không cần Jackson, BOM chung vẫn hữu ích:

```text
parent / common BOM
      |
      +-- quản lý jackson-databind / jackson-core / ...
      |
      +-- module-a: dependencies -> jackson-databind
      |
      +-- module-b: dependencies -> jackson-dataformat-xml
      |
      +-- module-c: không có Jackson dependencies
```

Mỗi module chỉ lấy những gì nó cần. Kế thừa/import BOM cho phép mọi module dùng cùng chính sách version nhưng không ép tất cả modules tải/library mọi artifact trong BOM. Sự phân tách này làm mô hình POM phản ánh chính xác kiến trúc module và giảm phụ thuộc không cần thiết.

### 6.2. Một BOM có thể chứa nhiều mục management hơn nhu cầu ứng dụng

Một BOM cho framework có thể quản lý hàng trăm artifact. Import nó có thể khiến effective POM dài hơn, nhưng **không có nghĩa classpath hoặc JAR phình ra tương ứng**. Khi muốn biết thứ gì thực sự vào classpath, hãy kiểm tra dependency graph và packaging.

### 6.3. BOM không phải “starter”

Một framework có thể cung cấp cả:

- **BOM:** danh mục version, import ở `dependencyManagement`.
- **Starter** hoặc dependency tổng hợp: một artifact được khai báo **trong `dependencies`** và kéo theo nhiều modules thông qua transitive dependencies.

Hai thứ có mục đích khác nhau. Một *starter* có thể chủ động kéo thêm thư viện vào module; BOM đơn thuần **không** làm vậy.

Đừng suy ra “import BOM X sẽ tự có tính năng X”. Nếu module cần một API/implementation, hãy đọc tài liệu của thư viện để khai báo artifact thích hợp.

## 7. Parent POM: `dependencyManagement` và `dependencies` có hiệu ứng khác nhau

Trong dự án multi-module, nhiều người biết rằng parent POM có thể chia sẻ cấu hình cho các child, rồi nhầm rằng **mọi thứ khai báo ở parent đều mang cùng ý nghĩa**.

### 7.1. Parent quản lý version — child vẫn phải chọn dependency

**POM cha, fragment:**

```xml
<project>
    <!-- Các tọa độ, packaging=pom, modelVersion... -->
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.fasterxml.jackson.core</groupId>
                <artifactId>jackson-databind</artifactId>
                <version>2.17.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Đây **không phải POM hoàn chỉnh để copy chạy**, vì các phần tử mô hình tối thiểu đã được lược bỏ có chú thích. Ý nghĩa: parent **quản lý** version `2.17.2`, không tự thêm dependency vào module con.

**POM con muốn dùng Jackson, fragment:**

```xml
<parent>
    <groupId>org.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>

<artifactId>json-module</artifactId>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Nếu POM parent thực tế có tọa độ đúng và `<packaging>pom</packaging>`, child kế thừa bảng management, không cần ghi lại version. `relativePath` chỉ giúp Maven tìm parent POM trong workspace; nó **không** mang nghĩa “thêm dependencies của bảng management”.

### 7.2. Trường hợp khác: parent khai báo `<dependencies>` thật

**POM cha, fragment:**

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.2</version>
    </dependency>
</dependencies>
```

Khác với `dependencyManagement`: dependencies trong parent POM **thường được kế thừa** bởi child dưới quy tắc inheritance của Maven, trừ các cấu hình riêng và cơ chế kế thừa thích hợp. Khi đó child có thể nhận Jackson làm dependency **thật**, ngay cả khi child không tự viết block Jackson tương ứng.

Vì vậy câu “parent không tự thêm thư viện” **chỉ đúng đối với mục nằm trong `dependencyManagement`**, không đúng khi parent có **`dependencies` trực tiếp** được kế thừa. Phải đọc đúng vị trí XML thay vì chỉ nhìn có tên artifact trong parent.

### 7.3. Vì sao nên để version chung ở dependencyManagement thay vì parent dependencies?

Nếu parent thêm một dependency trong `<dependencies>`, nhiều module con có thể nhận dependency dù không cần. Với hệ thống lớn, điều này khiến mọi module dễ bị kéo theo classpath không đúng ranh giới.

Khuyến nghị thực tế:

1. Parent/BOM **quản lý** những version dùng chung.
2. Mỗi module **khai báo** artifact thật sự sử dụng.
3. Dùng một số dependencies chung ở parent **chỉ khi mọi module thực sự cần** và đã xem xét hệ quả kế thừa.
4. Không trộn mục tiêu “quản lý nhất quán” với “áp tất cả thư viện lên mọi module”.

### 7.4. Inheritance không giống aggregation

- `<parent>` trong POM con tạo **quan hệ kế thừa** model.
- `<modules>` trong POM aggregator nói Maven **build những module nào** trong reactor.

Một aggregator khai báo modules **không tự làm chúng kế thừa dependencyManagement** nếu POM từng module không có quan hệ parent phù hợp. Ngược lại, một child có parent **không nhất thiết được root aggregator build** nếu nó không nằm trong modules.

## 8. Các trường hợp version, scope và ưu tiên cần hiểu rõ

### 8.1. Direct declaration có version tường minh

Nếu BOM quản lý `jackson-databind=2.17.2` nhưng module viết:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.1</version>
    </dependency>
</dependencies>
```

Module đang yêu cầu version khác **một cách tường minh**. Đừng nghĩ BOM luôn “khóa cứng” mọi dependency không cho module ghi version riêng. Cách chọn version hiệu lực phụ thuộc direct declaration, management và quy tắc mediation; trong tình huống này, module đã cố tình đi chệch phiên bản được BOM quản lý, nên cần đánh giá tính tương thích.

**Khuyến nghị:** nếu muốn BOM kiểm soát một tập modules tương thích, bỏ version ở declarations trong các module tiêu thụ, tránh override tùy tiện.

### 8.2. DependencyManagement và transitive dependencies

Maven có cơ chế *dependency mediation* — khi có nhiều đường đi tới một artifact, Maven thường dùng **nearest definition**, với trường hợp ngang mức có quy tắc declaration order. Tuy nhiên, **dependencyManagement trong project hiện tại** có thể chi phối version của artifact nằm trong đồ thị chuyển tiếp và có ưu tiên theo quy tắc Maven; không chỉ làm đầy phần `<version>` bị bỏ ở direct dependency.

Ví dụ module dùng thư viện A, A kéo C version cũ. Nếu project đang quản lý C version khác, management có thể chọn C theo version đã quản lý **khi C tham gia graph**. Nhưng management **không tự thêm C** nếu không ai yêu cầu C trực tiếp hay transitively.

Một lưu ý chính thức: management đối với **project dependencies** không tự điều khiển phiên bản **plugin dependencies** của build plugins. Muốn quản lý plugin cần dùng `pluginManagement`/cấu hình plugin và cơ chế riêng.

### 8.3. Scope trong management

Giả sử parent quản lý một API là `provided`, child khai báo artifact không ghi scope. Maven có thể áp dụng scope từ management. Nhưng scope có ý nghĩa với classpath/packaging thực tế:

| Scope | Ảnh hưởng thông dụng |
| --- | --- |
| `compile` | Có trên compile/test/runtime classpath của project và có thể đi theo dependency graph |
| `provided` | Cần compile/test, runtime dựa vào môi trường cung cấp |
| `runtime` | Cần khi chạy/test; không dùng để compile API nguồn chính |
| `test` | Dành cho test compile/test runtime |
| `import` | Chỉ dùng với BOM/POM import trong `dependencyManagement` |

Không đổi scope hoặc ghi scope trực tiếp chỉ để loại warnings mà không hiểu classloader và môi trường deploy.

### 8.4. Exclusions và optional dependencies

BOM/management có thể cung cấp exclusions trong một số trường hợp, song **không phải nguồn thay thế cho việc khai báo dependency**. Nếu một direct dependency kéo theo thư viện không mong muốn, có thể dùng exclusion ở declaration phù hợp. Điều đó khác với việc một mục management độc lập tự đưa artifact lên classpath.

Tương tự, một dependency được đánh dấu `optional=true` ở upstream không mặc nhiên lan tới mọi consumer. Nếu ứng dụng thật sự cần artifact optional, hãy khai báo trực tiếp.

## 9. Khi import nhiều BOM: xung đột phiên bản xử lý thế nào?

Một dự án có thể import nhiều BOM để phối hợp nhiều nhóm thư viện:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>platform-a-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>platform-b-bom</artifactId>
            <version>2.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **fragment minh họa**; `org.example:platform-a-bom` và `platform-b-bom` là tên giả, không giả định artifact tồn tại trên repository.

Nếu hai BOM cùng quản lý artifact X nhưng ở hai phiên bản, chúng tạo ra **xung đột management**. Tài liệu Maven nêu rằng khi hai BOM import cùng một mục và project nhập chưa khai báo mục đó trực tiếp trong `dependencyManagement` của chính nó, **BOM được khai báo trước** có thể được chọn cho mục trùng. Đừng áp dụng quy tắc “version cao hơn luôn thắng” hoặc đoán rằng BOM sau luôn thắng.

Nếu thực sự cần version riêng, khai báo management tường minh trong project:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.17.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Ở đây mục tường minh và BOM cùng version chỉ để minh họa **cấu trúc ưu tiên**. Nếu override sang version khác, bạn cần tự đánh giá tương thích với phần còn lại của Jackson BOM. Không coi override là giải pháp tốt mặc định khi hai BOM tranh chấp.

**Ranh giới quan trọng:** xung đột *management* khác với xung đột trong *resolved dependency tree*. Xem `help:effective-pom` để biết management cuối; xem `dependency:tree` để biết artifact version nào đã thực sự tham gia graph. Chỉ dựa vào một loại output có thể gây hiểu nhầm.

## 10. Phân biệt BOM import với parent kế thừa

Một project chỉ có thể có **một parent POM trực tiếp** nhưng có thể **import nhiều BOM**. Đây là lý do Maven đưa ra BOM import: tổ chức muốn tổng hợp version policies từ nhiều hệ sinh thái mà không biến mọi BOM thành parent.

Ví dụ:

```xml
<parent>
    <groupId>org.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.17.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là fragment đặt bên trong POM con. **Parent** có thể cấp properties, build settings, pluginManagement, repositories... tùy Maven inheritance. **Jackson BOM** chỉ đóng góp các mục dependencyManagement được import, **không biến thành parent thứ hai**. Chúng không có cùng vai trò.

Không dùng `<parent>` chỉ để quản lý nhiều hệ thư viện nếu team cần dùng parent tổ chức hiện có. Import BOM là cơ chế phù hợp hơn khi mục tiêu là **phối hợp phiên bản dependency**.

### 10.1. Import BOM không kế thừa toàn bộ properties/plugins của BOM

Bạn có thể thấy trong file BOM POM gốc các phần như `<properties>`, parent POM, build plugins... Điều được import qua scope `import` là **nội dung quản lý dependency hiệu lực**, không phải tất cả sections trong BOM theo cách inheritance. Vì vậy:

- Không kỳ vọng properties riêng của BOM tự trở thành properties dùng chung trong POM của bạn.
- Không kỳ vọng plugin của BOM tự được cấu hình/thực thi trong project.
- Không kỳ vọng BOM tự tạo một runtime classpath.
- Có thể tham khảo BOM metadata để biết version managed, nhưng muốn dùng thư viện vẫn phải khai báo dependency.

## 11. PluginManagement là phép so sánh hữu ích, nhưng không trộn vai trò

Maven có cơ chế gần giống trong build plugins:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đây là fragment quản lý version plugin, tương tự một **bảng quy tắc**. Nó không có nghĩa mọi plugin goal tùy ý đã được kích hoạt. Nhưng **có khác biệt cần chú ý**: Maven có các **default plugin bindings** theo packaging/lifecycle (ví dụ compiler goal cho JAR). Do đó đừng hiểu phép so sánh quá máy móc thành “plugin trong pluginManagement chắc chắn không bao giờ chạy”; plugin có thể đã được bind mặc định hoặc khai báo ở nơi khác.

Điểm chung cần học: **quản lý cấu hình** không đồng nghĩa **tuyên bố sử dụng trực tiếp**. Còn mechanism chi tiết của plugins và dependencies là khác nhau.

## 12. Xác minh thực tế bằng Maven Help Plugin và Dependency Plugin

Sau khi sửa POM và build project ví dụ, dùng:

```bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core
mvn dependency:analyze
```

Những lệnh này trả lời các câu hỏi khác nhau:

| Công cụ | Trả lời câu hỏi | Không chứng minh được |
| --- | --- | --- |
| `mvn help:effective-pom` | POM hiệu lực có những mục dependencyManagement và dependencies nào? | Tất cả mục managed đều có mặt trên runtime classpath |
| `mvn dependency:tree` | Artifact nào đã được resolve và qua cạnh nào? | Source Java có thực sự dùng API của tất cả artifact đó? |
| `mvn dependency:analyze` | Bytecode tham chiếu dependency được khai báo trực tiếp hay chuyển tiếp? | Mọi use qua reflection, ServiceLoader hoặc cấu hình runtime |
| `mvn clean compile` | Source có biên dịch với compile classpath hiện tại không? | Đủ providers khi chạy ở production |
| `mvn clean verify` | Lifecycle và các quality gates đến verify có hoàn tất không? | Artifact chắc chắn an toàn hoặc tương thích mọi runtime |

### 12.1. Khi Maven báo missing version

Nếu module khai báo:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
```

nhưng thiếu BOM/parent management hoặc BOM không quản lý đúng tọa độ/type/classifier, Maven báo thiếu version. Các câu hỏi cần kiểm tra:

1. BOM đã được import **đúng vị trí** `dependencyManagement/dependencies` chưa?
2. Có đủ `<type>pom</type>` và `<scope>import</scope>` không?
3. BOM version/tọa độ có chính xác và artifact POM có thể resolve không?
4. Dependency module khai báo đúng `groupId`, `artifactId` và type/classifier phù hợp không?
5. Parent hoặc profile có đang tạo management khác mong đợi không?
6. Có dấu hiệu sử dụng Maven settings/remote repository khác trong CI không?

### 12.2. Khi POM validate nhưng Java compile không được

Nếu lỗi là `package ... does not exist`, hãy xem **project dependency tree**. Nếu artifact JAR chứa class chưa xuất hiện ở tree, kiểm tra module đã **khai báo `<dependencies>` thật sự** chưa. Đừng dành thời gian chỉ chỉnh BOM version khi nguyên nhân là chưa có declaration.

Nếu class chỉ có ở `test` scope mà source chính đang dùng nó, vấn đề có thể là **sai scope**. Nếu class có ở `runtime` scope nhưng cần để compile, cũng có thể sai scope. Maven không tự “nâng” mọi dependency managed thành `compile` chỉ vì code đang import nó.

### 12.3. Khi artifact vẫn có trong tree dù đã bỏ direct declaration

Đây là trường hợp khác: dependency có thể đến từ **transitive dependency** hoặc **parent `<dependencies>` được kế thừa**. Chạy `dependency:tree` để tìm đường đi. Không kết luận BOM đã tự thêm JAR khi nguyên nhân thực tế là một dependency khác kéo nó vào.

Với dependency được dùng trực tiếp từ source của module, nên khai báo trực tiếp thay vì chỉ dựa vào transitive artifact. `dependency:analyze` giúp tìm `Used undeclared` trong những trường hợp bytecode có thể phát hiện.

## 13. Lỗi và ngộ nhận thường gặp

| Hiện tượng / nhận định | Giải thích đúng | Hướng xử lý |
| --- | --- | --- |
| Import BOM rồi `ObjectMapper` không compile | BOM chỉ quản lý, không thêm JAR | Thêm direct `jackson-databind` vào `<dependencies>` |
| `effective-pom` có `jackson-databind` nhưng tree không có | Đó có thể chỉ là managed entry | Phân biệt vị trí `dependencyManagement` và `dependencies` |
| Bỏ `<version>` ở dependency nhưng Maven báo thiếu | Chưa có management phù hợp | Kiểm tra BOM import, parent và tọa độ |
| BOM có type `pom` nên chắc tải luôn JAR | POM metadata không phải JAR implementation | Khai báo artifact thật sự chứa API |
| Đặt `<scope>import</scope>` trong `<dependencies>` thường | Dùng import sai ngữ cảnh | Chuyển BOM vào dependencyManagement |
| Parent chứa Jackson trong dependencyManagement nên child có Jackson | Chỉ có chính sách version được kế thừa | Child thêm dependency |
| Parent `<dependencies>` cũng không làm child có JAR | Không đúng với inheritance thông thường | Kiểm tra parent direct deps và effective POM |
| Artifact xuất hiện trong tree dù không direct declaration | Được kéo transitively hoặc kế thừa trực tiếp | Truy cạnh dependency bằng tree |
| BOM quản lý bản mới nhưng direct dep vẫn có bản khác | Module ghi version trực tiếp hoặc có override | Xem direct version, management và tree |
| Hai BOM tranh chấp version, BOM thứ hai chắc thắng | Quy tắc import có thể ưu tiên BOM khai báo trước | Đọc effective POM và khai báo override có chủ đích |
| Đưa version vào dependencyManagement của module khác | Management không phải toàn reactor tự chia sẻ | Kế thừa đúng parent hoặc import BOM ở module liên quan |
| Import BOM sẽ bật plugin cùng tên | BOM import không phải POM inheritance | Khai báo/quản lý plugin riêng |
| `mvn validate` PASS nghĩa dependency class có trên classpath | Validate không compile mã | Chạy compile và kiểm tra tree |
| `dependency:tree` có JAR nghĩa ứng dụng đang dùng nó | Tree chỉ là graph resolved artifacts | Dùng analyze và kiểm tra runtime |
| Chỉ thêm dependency trong BOM nhưng app chưa dùng được | BOM authoring và module usage là hai việc riêng | Khai báo dependency ở module tiêu thụ |
| BOM có 200 entries nghĩa build kéo 200 JAR | Managed entries không là direct dependencies | Xem dependency tree/packaging |
| `java -jar` lỗi class Jackson dù Maven package thành công | Thin JAR chưa có external runtime classpath | Dùng Maven Exec, thư viện trên classpath hoặc đóng gói phù hợp |
| Maven lỗi không tìm BOM khi build offline | BOM POM chưa có trong local repo | Chuẩn bị local cache hoặc repo access |
| Đổi BOM làm hàng loạt modules bị ảnh hưởng | Chính sách version chung thay đổi | Test reactor, xác nhận compatibility theo module |

**Không xử lý một lỗi classpath bằng cách luôn “thêm cả BOM lẫn tất cả JAR”**. Việc đó bỏ qua ưu điểm của management và có thể tạo dependencies thừa. Hãy thêm đúng artifact mà module dùng.

## 14. Khi nào nên dùng BOM và khi nào nên khai báo version trực tiếp?

**Dùng BOM** khi:

- Project có nhiều modules dùng chung một hệ thư viện.
- Một framework phát hành bộ artifact được kiểm thử theo các version phối hợp.
- Team muốn nâng cấp một tập dependencies bằng việc thay một BOM version sau khi chạy test.
- Parent POM đã dành cho cấu hình build chung, cần thêm management từ các hệ sinh thái khác mà không có parent thứ hai.

**Khai báo version trực tiếp** khi:

- Một module nhỏ có rất ít dependency và không có BOM phù hợp.
- Bạn chủ động override một artifact vì tương thích/bảo mật và đã kiểm chứng.
- Thư viện không nằm trong danh mục management hiệu lực nào.

Không có yêu cầu bắt buộc mọi dependency phải dùng BOM; **độ rõ ràng và khả năng tái lập** mới là tiêu chí. Một BOM không thay thế việc xem xét CVE, licenses, API compatibility và dependency upgrades. Các version cũ trong ví dụ chỉ có mục đích học tập, không phải đề xuất version bảo mật mới nhất cho production.

### 14.1. Những lưu ý khi nâng BOM

Khi đổi `jackson-bom` từ một version sang version khác:

1. Xác định modules nào đang thực sự sử dụng Jackson qua direct/transitive dependencies.
2. Xem managed versions dự kiến thay đổi.
3. Kiểm tra override tường minh trong direct dependencies hoặc dependencyManagement cục bộ.
4. Chạy `mvn clean verify` cho các modules được hỗ trợ.
5. Chạy integration/runtime tests với các serialization/deserialization formats thực tế.
6. So sánh `dependency:tree` và kiểm tra chính sách bảo mật/compatibility của nhóm.

Nâng BOM có thể thay version của **những thư viện đang được dùng**. Nó **không tự biến những thư viện trước đó chưa dùng thành dependencies mới**.

## 15. Dự án multi-module: ví dụ về phân quyền trách nhiệm

Giả sử một reactor:

```text
platform/
├── pom.xml            # parent + aggregator; import BOM
├── service-a/
│   └── pom.xml        # service-a dùng Jackson
└── service-b/
    └── pom.xml        # service-b không dùng Jackson
```

**Root POM** import Jackson BOM trong `dependencyManagement` và khai báo `<modules>`:

```xml
<packaging>pom</packaging>
<modules>
    <module>service-a</module>
    <module>service-b</module>
</modules>
```

Đây là fragment; root cũng cần tọa độ `groupId`, `artifactId`, `version`. Mỗi child khai báo `<parent>` tới root đúng GAV/đường dẫn thì mới kế thừa management.

**service-a/POM**, fragment:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

**service-b/POM** không cần Jackson nên không khai báo Jackson dependency. Dù cả hai child cùng kế thừa BOM import từ parent, graph của service-b **không có Jackson** chỉ vì BOM đó.

Nếu sau này service-b cần JSON, thêm dependency vào **service-b**, không sửa root `<dependencies>` để ép mọi module cùng dùng. Đây là mẫu phân tách hữu ích giữa **quy tắc chung** và **nhu cầu cụ thể**.

### 15.1. Đừng nhập BOM từ module con chưa thể resolve

Maven phải đọc BOM POM để dựng effective POM từ rất sớm. Nếu BOM được định nghĩa là một module chưa build trong cấu trúc vòng lặp hoặc importer dựa vào một child module chưa thể resolve, có thể gặp vòng dependency/model resolution. Tài liệu Maven cảnh báo không import BOM là submodule mà importer không thể resolve, và tránh parent/import cycle. Với BOM nội bộ, hãy thiết kế phát hành/installation/checkout rõ ràng và không tự tạo vòng.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** Import BOM `jackson-bom` rồi `ObjectMapper` không tìm được khi compile. Có phải BOM hỏng?  
**Đáp án:** Không nhất thiết. BOM có thể được đọc đúng nhưng project chưa có direct dependency `jackson-databind`. Cần kiểm tra `<dependencies>` và tree.

**Câu 2:** Tại sao `mvn validate` có thể thành công nhưng `mvn compile` thất bại trong giai đoạn A?  
**Đáp án:** Validate dựng model/kiểm tra cấu hình; compile cần class của Jackson trên compile classpath, mà BOM import không tự thêm.

**Câu 3:** Sau khi import BOM, child khai báo `jackson-databind` không có `<version>` thì Maven lấy version ở đâu?  
**Đáp án:** Từ dependencyManagement hiệu lực của BOM/parent; trong bài mẫu là `2.17.2`.

**Câu 4:** Tất cả artifact có trong `<dependencyManagement>` có xuất hiện trong `dependency:tree` không?  
**Đáp án:** Không. Tree phản ánh dependencies thực tế được resolve, không phải toàn bộ mục managed.

**Câu 5:** POM cha có `jackson-databind` trong `<dependencies>`, child có kế thừa JAR không?  
**Đáp án:** Thông thường có theo quy tắc Maven inheritance. Đây là điểm khác với `dependencyManagement`.

**Câu 6:** BOM import có làm project kế thừa compiler plugin và properties của BOM như một parent thứ hai không?  
**Đáp án:** Không. Import scope mang các mục dependencyManagement hiệu lực, không phải toàn bộ mô hình POM qua inheritance.

**Câu 7:** BOM quản lý 100 thư viện. Project chỉ khai báo 1 thư viện. Có 100 JAR ngay trên classpath không?  
**Đáp án:** Không; chỉ dependencies thực tế và các transitives được resolve phù hợp.

**Câu 8:** Hai BOM cùng quản lý artifact A khác version. Có thể mặc định rằng version cao nhất thắng không?  
**Đáp án:** Không. Cần xem quy tắc import/order và management tường minh; xác minh `effective-pom` và `dependency:tree`.

**Câu 9:** Đổi BOM version khiến một module không dùng thư viện X bị thêm X vào graph?  
**Đáp án:** Không chỉ nhờ thay management. Phải có direct/transitive dependency yêu cầu X.

**Câu 10:** `dependencyManagement` có quản lý các thư viện transitively thuộc build plugin không?  
**Đáp án:** Không theo cùng cơ chế của project dependencies; quản lý plugin/plugin dependencies có quy tắc riêng.

**Câu 11:** Khi child dùng trực tiếp class từ transitive dependency, có cần khai báo direct dependency?  
**Đáp án:** Nên khai báo. Nếu upstream thay đổi dependency graph, code vẫn có hợp đồng rõ và ít bị lỗi bất ngờ.

**Câu 12:** Trong bài thực hành, vì sao chạy chương trình bằng Maven Exec Plugin thuận tiện hơn `java -cp target/classes`?  
**Đáp án:** Exec Plugin dùng classpath Maven có Jackson dependencies; `target/classes` thuần không chứa các JAR ngoài.

## 17. Checklist nắm vững bài học

- [ ] Phân biệt được **quản lý phiên bản** và **khai báo sử dụng**.
- [ ] Biết BOM import trong Maven 3 là `type=pom`, `scope=import` đặt **trong dependencyManagement**.
- [ ] Không nhầm BOM POM metadata với JAR chứa class chạy.
- [ ] Tạo POM Java 17 với Jackson BOM 2.17.2 và hiểu vì sao `ObjectMapper` chưa compile khi chưa có direct dependency.
- [ ] Thêm `jackson-databind` dưới `<dependencies>` nhưng không ghi version.
- [ ] `mvn clean package` thành công và chạy `App.main` cho stdout `{"status":"BOM works"}`.
- [ ] Hiểu `jackson-core`, `jackson-annotations` có thể vào graph transitively từ `jackson-databind`.
- [ ] Dùng cả `help:effective-pom` và `dependency:tree` để phân biệt managed entries và resolved dependencies.
- [ ] Biết parent dependencyManagement **không tự thêm JAR**, nhưng parent `<dependencies>` có thể được kế thừa thành dependency thật.
- [ ] Không nhầm `dependencyManagement` với `pluginManagement` hoặc `build/plugins`.
- [ ] Hiểu rằng management có thể ảnh hưởng **version transitive** đã xuất hiện trong graph, không tự thêm artifact.
- [ ] Biết xử lý xung đột BOM và direct version override bằng kiểm chứng effective POM/tree.
- [ ] Trong multi-module, chỉ modules thật sự cần thư viện mới khai báo dependency tương ứng.
- [ ] Khi nâng BOM, chạy compile, unit/integration tests và kiểm tra tương thích/bảo mật, không chỉ sửa số version.

## 18. Tài liệu tham khảo

1. [Apache Maven — Introduction to the Dependency Mechanism: Dependency Management, Importing Dependencies, BOM](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
2. [Apache Maven — POM Reference: Dependencies và Dependency Management](https://maven.apache.org/pom.html)
3. [Apache Maven — Introduction to the POM: Inheritance và Aggregation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
4. [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
5. [Apache Maven Dependency Plugin — dependency:analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html)
6. [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
7. [Maven Central — Jackson BOM 2.17.2](https://central.sonatype.com/artifact/com.fasterxml.jackson/jackson-bom/2.17.2/pom)
8. [Maven Central — Jackson Databind 2.17.2](https://central.sonatype.com/artifact/com.fasterxml.jackson.core/jackson-databind/2.17.2)
9. [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)

**Thông điệp ghi nhớ:** *`dependencyManagement`/BOM xác định các phiên bản sẵn sàng được chọn; `<dependencies>` xác định các thư viện module thật sự sử dụng. Có quy tắc quản lý không đồng nghĩa có thư viện trên classpath.*
