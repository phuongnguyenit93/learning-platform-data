# Dependency mediation và lựa chọn phiên bản trong đồ thị Maven

## 1. Vì sao Maven cần dependency mediation?

Trong một ứng dụng Java, ít khi tất cả thư viện đều được khai báo trực tiếp trong `pom.xml`. Một thư viện mà ứng dụng dùng lại có thể kéo theo các thư viện khác, tạo thành **transitive dependencies** (phụ thuộc bắc cầu). Khi nhiều đường trong đồ thị dẫn đến **cùng một artifact nhưng yêu cầu các version khác nhau**, Maven phải chọn phiên bản phù hợp cho dependency graph của project.

Ví dụ:

```text
app
├── service-a
│   └── common-lib:1.0
└── service-b
    └── common-lib:2.0
```

Chẳng lẽ classpath của `app` luôn có hai phiên bản `common-lib`? Với một artifact thông thường có cùng định danh xung đột (như cùng `groupId:artifactId` và loại `jar`), Maven thực hiện **dependency mediation** (điều giải xung đột phiên bản) để chọn **một phiên bản thắng** trong tập dependency được phân giải.

Quy tắc quan trọng trong Maven 3 là:

1. **Nearest definition wins**: phiên bản được định nghĩa qua **đường gần project gốc hơn** trong dependency graph thường thắng.
2. **Cùng độ sâu, khai báo trước thắng**: khi hai ứng viên ở khoảng cách bằng nhau, **đường từ dependency được khai báo trước** có thể quyết định kết quả.
3. **Direct dependency**: khi project khai báo trực tiếp version của artifact, nó có đường dài một cạnh và là cách rõ ràng để chủ động chọn phiên bản.
4. **`dependencyManagement`**: có thể quản lý version transitive dependency mà không cần thêm artifact thành direct dependency; nó thường được áp dụng **trước quy tắc mediation thông thường** trong phạm vi project dependencies.

Đây không phải thuật toán “luôn lấy version mới nhất”, cũng không phải “đường được khai báo ở module sâu nhất thắng”. Nếu không hiểu cơ chế, bạn có thể gặp `NoSuchMethodError`, `ClassNotFoundException`, kết quả test khác CI, hoặc vô tình đóng gói một phiên bản có lỗ hổng.

Mục tiêu bài học là: đọc đồ thị, dự đoán đúng phiên bản, kiểm chứng bằng Maven Dependency Plugin, phân biệt mediation với quản lý phiên bản, và biết cách khóa version có chủ ý.

## 2. Phân biệt artifact, dependency graph và classpath

### 2.1. Artifact được xác định như thế nào?

Tọa độ Maven thông dụng gồm:

```text
groupId:artifactId:version
```

Ví dụ `org.apache.commons:commons-lang3:3.12.0`. Trong ngữ cảnh phân giải đầy đủ còn có `type`, `classifier`, `scope` và các thông tin khác. Khi nói “hai phiên bản của cùng một artifact đang xung đột”, hãy chắc chắn chúng thuộc **cùng khóa artifact tương ứng**; hai biến thể có classifier/type khác nhau không nhất thiết là một xung đột version giống như hai JAR mặc định.

`groupId` và `artifactId` xác định thư viện về mặt tên, `version` cho biết phiên bản cụ thể. Trong bản dependency graph đã chọn, Maven xác định artifact/version cần có ở mỗi classpath theo quy tắc phân giải. Không suy luận rằng chỉ vì hai file JAR khác version tồn tại trong `~/.m2/repository` thì cả hai sẽ cùng được dùng khi compile hoặc chạy.

### 2.2. Đồ thị nguồn và cây hiển thị không hoàn toàn giống nhau

Maven thu thập các dependency được mô tả bởi POM, xét scope, optional/exclusion, dependency management, version requirements và chọn nhánh/phiên bản. **`dependency:tree` thường hiển thị cây kết quả đã phân giải**. Những nhánh bị loại do xung đột hoặc trùng lặp có thể không xuất hiện trong output mặc định, dù POM gốc của thư viện vẫn khai báo chúng.

Sơ đồ ý tưởng:

```text
Đồ thị thu thập:
  app -> alpha -> X:1.0
  app -> beta  -> X:2.0

Sau mediation (ví dụ alpha được ưu tiên):
  app -> alpha -> X:1.0  [được chọn]
  app -> beta  -> X:2.0  [không phải version thắng]

Classpath được phân giải: X:1.0
```

**Một module có dependency bị “omitted for conflict” không đồng nghĩa cả module bị bỏ.** Nếu `beta` cũng có class riêng cần cho app, module beta vẫn có thể nằm trong classpath; chỉ ứng viên version `X:2.0` không được chọn.

### 2.3. Kho local và repository không quyết định version thắng theo kiểu “có sẵn thì dùng”

Kho `~/.m2/repository` là **cache artifact** Maven từng tải/cài. Nó có thể chứa nhiều version. Việc chọn version dựa chủ yếu vào mô hình dependency và quy tắc giải quyết; Maven sau đó tìm/tải artifact tương ứng từ local/remote repositories. Artifact có sẵn trong cache không tự đánh bại version đã được chọn vì mediation.

Nếu version được chọn không thể tải xuống, Maven có thể **fail resolution**; không nên mặc định rằng Maven sẽ tùy ý đổi sang version cũ hơn đang có trong cache.

## 3. Quy tắc “nearest definition”: ưu tiên đường gần project gốc

### 3.1. Độ sâu của đường phụ thuộc

Xét:

```text
app
├── facade
│   └── adapter
│       └── parser:2.0
└── api-client
    └── parser:1.0
```

Tính số cạnh từ `app` tới `parser`:

- `app → facade → adapter → parser:2.0`: **3 cạnh**.
- `app → api-client → parser:1.0`: **2 cạnh**.

Theo **nearest definition**, `parser:1.0` qua đường ngắn hơn thắng trong tình huống Maven 3 thông thường (giả sử không có dependency management, version range hoặc ràng buộc khác làm thay đổi quy tắc). Dù 2.0 “mới” hơn, Maven **không mặc định chọn 2.0**.

Maven không tính “module nào đã build gần đây hơn”, “ai ghi version cao hơn” hoặc “ai khai báo dependency trên dòng cuối”. Tiêu chí đang bàn là **khoảng cách từ project gốc đến node candidate**.

### 3.2. Direct dependency chỉ cách project gốc một cạnh

Nếu `app` khai báo trực tiếp:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>parser</artifactId>
        <version>2.0</version>
    </dependency>
</dependencies>
```

thì đường `app → parser:2.0` chỉ có **1 cạnh**, gần hơn các đường bắc cầu. Vì vậy phiên bản trực tiếp thường là ứng viên thắng. Đây là một cách chủ động chọn version, đồng thời làm rõ thư viện mà source code của app phụ thuộc trực tiếp.

**Tuy nhiên, đừng thêm direct dependency chỉ để “đánh bại” graph nếu app không dùng thư viện đó.** Nếu chỉ muốn kiểm soát version bắc cầu, `dependencyManagement` có thể rõ ràng hơn; và dù chọn version nào, vẫn cần test compatibility với các thư viện upstream.

### 3.3. Khi “nearest” không giải thích được mọi trường hợp

Nearest-definition là quy tắc nền tảng nhưng **không đứng tách biệt** khỏi toàn bộ Maven resolver:

- `dependencyManagement` có thể áp version cho transitive dependency.
- Một dependency có `scope` hoặc `optional` phù hợp có thể không đi vào classpath đang xét.
- `<exclusions>` có thể cắt một đường tới artifact, làm thay đổi tập ứng viên.
- Version requirement/range cứng có thể giới hạn phiên bản hợp lệ.
- Profile và parent POM có thể thay đổi effective dependencies.
- Các plugin có dependency graph khác với project runtime dependencies.

Khi có các yếu tố đó, hãy xem **effective POM và dependency tree đã phân giải**, không dự đoán chỉ bằng một ảnh cây vẽ tay.

## 4. Cùng độ sâu: dependency được khai báo trước có thể thắng

### 4.1. Trường hợp tie đơn giản

```text
app
├── alpha
│   └── common:1.0
└── beta
    └── common:2.0
```

Cả hai đường `app → alpha → common` và `app → beta → common` đều dài **2 cạnh**. Khi không có yếu tố quản lý version khác, Maven áp dụng quy tắc **“first declaration wins”**: thứ tự các direct dependencies trong `app/pom.xml` là điều có thể quyết định version thắng.

Với:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>alpha</artifactId>
        <version>1.0</version>
    </dependency>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>beta</artifactId>
        <version>1.0</version>
    </dependency>
</dependencies>
```

thì `common:1.0` ở nhánh alpha thường được chọn. **Đảo thứ tự alpha và beta có thể khiến `common:2.0` được chọn**, dù không sửa POM của alpha hoặc beta.

Vì vậy thứ tự dependency ở POM không phải lúc nào cũng chỉ là trình bày. Tuy nhiên, **đảo thứ tự để ép version** là giải pháp mong manh: khi một dependency khác xuất hiện, graph có thể có đường ngắn hơn hoặc dependencyManagement khác. Hãy ghi rõ ý định qua direct dependency hoặc dependencyManagement nếu version là quyết định quan trọng.

### 4.2. Thứ tự của `<modules>` không thay cho mediation

Một aggregator nhiều module có:

```xml
<modules>
    <module>alpha</module>
    <module>beta</module>
    <module>app</module>
</modules>
```

Danh sách module là để Maven **gom project vào reactor**, không phải cơ chế chọn version trong `app`. Reactor sắp xếp thứ tự build dựa trên các quan hệ phụ thuộc thực tế. **Thứ tự `<modules>` không phải là thứ tự ưu tiên version transitive**. Khi phân tích tie, hãy xem **thứ tự các `<dependency>` được khai báo ở consumer effective POM**, cùng các quy tắc mediation khác.

## 5. `dependencyManagement`: quản lý version chủ động

### 5.1. Khác biệt giữa “quản lý” và “thêm” dependency

`<dependencies>` cho biết **project có phụ thuộc** vào artifact nào. `<dependencyManagement>` cho biết **nếu artifact đó tham gia graph thì các thông tin được quản lý như version/scope có thể áp dụng thế nào**.

Ví dụ POM của `app`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đoạn XML này **không tự kéo commons-lang3 vào app**. Nhưng nếu app phụ thuộc alpha/beta và những module ấy mang `commons-lang3` vào graph, version được quản lý có thể được áp cho transitive dependency mà không cần thêm direct dependency tương ứng.

Theo hướng dẫn Maven chính thức, **dependency management của project có ưu tiên so với mediation thông thường đối với transitive dependencies**. Vì vậy, dù alpha xuất hiện trước beta, consumer có thể chủ động quản lý `commons-lang3` về version được duyệt.

### 5.2. Version ở dependency trực tiếp và version được quản lý

Nếu `app` khai báo direct dependency:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.12.0</version>
</dependency>
```

và một cấu hình quản lý có version khác, đừng tự kết luận rằng management sẽ thay **version explicit của direct dependency**. Trong mô hình Maven thông dụng, version được khai báo trực tiếp trong dependency của consumer thể hiện lựa chọn cụ thể; management thường cấp version cho dependency thiếu version và/hoặc can thiệp vào transitive graph. **Hãy kiểm chứng bằng effective POM và dependency tree**, nhất là với parent/BOM nhập nhiều tầng.

Để tránh khó hiểu, chỉ định version chủ đạo ở **một nơi có chủ đích**: dùng `dependencyManagement` rồi để direct dependencies của module con bỏ `<version>`, hoặc dùng direct version tại consumer khi cần override riêng.

### 5.3. Parent POM và BOM import

Một parent POM có thể định nghĩa:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module con kế thừa cấu hình management theo Maven model. Một BOM `packaging=pom` có thể chứa danh sách managed versions; consumer import BOM bằng dependency `<type>pom</type>` và `<scope>import</scope>` **bên trong dependencyManagement**, không phải trong `<dependencies>` thông thường.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn minh họa**, chỉ chạy được nếu `platform-bom` tồn tại. Import BOM giúp dùng bảng phiên bản đã quản lý, **không tự làm mọi thư viện trong BOM thành dependencies**. Trong tình huống cùng artifact được quản lý ở nhiều nơi, cần xét thứ tự import, mức độ ưu tiên khai báo trong current POM/parent và effective POM, không quy hết về nearest-definition.

**Cảnh báo:** `dependencyManagement` của project không quản lý các **dependencies riêng của Maven plugins** như thể plugin là project runtime dependency. Plugin graph có cơ chế khai báo/giải quyết riêng. Maven Compiler/Surefire chạy được với dependency riêng không có nghĩa JAR đó xuất hiện trên classpath của ứng dụng.

## 6. Thực hành Java 17: hai đường có cùng độ sâu và hai version commons-lang3

Ví dụ này tạo một reactor gồm **parent + 3 module**: `alpha`, `beta`, `app`.

- `alpha` khai báo `org.apache.commons:commons-lang3:3.12.0`.
- `beta` khai báo `org.apache.commons:commons-lang3:3.14.0`.
- `app` khai báo dependency vào alpha **trước**, beta **sau**.
- Cả hai thư viện `alpha` và `beta` gọi `StringUtils.upperCase` — API có ở cả 3.12.0 và 3.14.0 — để chương trình có thể chạy với version được chọn.

Bài thực hành cố ý dùng hai version có sẵn ở Maven Central. Cần Maven 3.9.x, JDK 17+, khả năng tải artifacts/plugins, và thao tác trong thư mục gốc `mediation-lab`.

### 6.1. Cấu trúc thư mục

```text
mediation-lab/
├── pom.xml
├── alpha/
│   ├── pom.xml
│   └── src/main/java/com/example/mediation/alpha/Alpha.java
├── beta/
│   ├── pom.xml
│   └── src/main/java/com/example/mediation/beta/Beta.java
└── app/
    ├── pom.xml
    └── src/main/java/com/example/mediation/app/App.java
```

Các module kế thừa `groupId=com.example.mediation` và `version=1.0.0` từ parent. Không có vòng phụ thuộc nội bộ: `app → alpha` và `app → beta`; alpha/beta đều kéo JAR commons-lang3 từ repository.

### 6.2. `mediation-lab/pom.xml` — parent và aggregator

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example.mediation</groupId>
    <artifactId>mediation-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>alpha</module>
        <module>beta</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
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
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Parent này cố ý **chưa định nghĩa dependencyManagement cho commons-lang3**, để trong thí nghiệm đầu Maven phải dùng mediation. `<pluginManagement>` ghim version các lifecycle plugins phổ biến; nó không quản lý version của `commons-lang3` trong app.

### 6.3. `mediation-lab/alpha/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.mediation</groupId>
        <artifactId>mediation-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>mediation-alpha</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.12.0</version>
        </dependency>
    </dependencies>
</project>
```

POM này khai báo commons-lang3 **trực tiếp đối với module alpha**. Không có cơ chế version mediation giữa hai phiên bản **khi build riêng alpha**; alpha chỉ yêu cầu 3.12.0. Khi alpha trở thành transitive dependency của app, yêu cầu phiên bản này có thể cạnh tranh với yêu cầu của beta.

### 6.4. `mediation-lab/alpha/src/main/java/com/example/mediation/alpha/Alpha.java`

```java
package com.example.mediation.alpha;

import org.apache.commons.lang3.StringUtils;

public final class Alpha {
    private Alpha() {
    }

    public static String label() {
        return StringUtils.upperCase("alpha");
    }
}
```

`StringUtils.upperCase` có mặt trong các version commons-lang3 đang dùng. Đây là class thư viện, không có `main()` riêng.

### 6.5. `mediation-lab/beta/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.mediation</groupId>
        <artifactId>mediation-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>mediation-beta</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</project>
```

Beta khai báo direct dependency của **chính beta** với commons-lang3 version 3.14.0. Đừng nhầm “direct của beta” thành “direct của app”: đối với app, commons-lang3 được kéo qua beta nên là transitive dependency.

### 6.6. `mediation-lab/beta/src/main/java/com/example/mediation/beta/Beta.java`

```java
package com.example.mediation.beta;

import org.apache.commons.lang3.StringUtils;

public final class Beta {
    private Beta() {
    }

    public static String label() {
        return StringUtils.upperCase("beta");
    }
}
```

Khi được build riêng, beta dùng version 3.14.0 để compile. Nhưng lúc app chạy và Maven đã mediation, version commons-lang3 trên runtime classpath của app có thể khác với version beta dùng để compile. **Đây chính là nguy cơ binary compatibility** nếu beta dựa vào API chỉ có ở version mới hơn.

Trong ví dụ, `StringUtils.upperCase` tồn tại ở cả hai version nên mã chạy được trong cả hai trường hợp; không nên dùng ví dụ đơn giản này để kết luận tất cả cặp version đều tương thích.

### 6.7. `mediation-lab/app/pom.xml` — alpha đứng trước beta

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.mediation</groupId>
        <artifactId>mediation-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>mediation-app</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.example.mediation</groupId>
            <artifactId>mediation-alpha</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>com.example.mediation</groupId>
            <artifactId>mediation-beta</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

Đây là POM quan trọng nhất: app không khai báo trực tiếp `commons-lang3`, cũng chưa có `dependencyManagement`. Hai version của commons-lang3 nằm ở **cùng độ sâu 2**. Vì dependency alpha được liệt kê trước beta, **dự kiến Maven 3 chọn commons-lang3:3.12.0 cho app**.

### 6.8. `mediation-lab/app/src/main/java/com/example/mediation/app/App.java`

```java
package com.example.mediation.app;

import com.example.mediation.alpha.Alpha;
import com.example.mediation.beta.Beta;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Alpha.label() + " | " + Beta.label());
    }
}
```

Java 17 biên dịch app vì app dùng public class Alpha và Beta, không import trực tiếp commons-lang3. Khi chạy app, Alpha và Beta đều dùng commons-lang3 từ classpath mà Maven đã giải quyết cho app.

### 6.9. Build toàn bộ reactor và xem version thắng

Mở terminal tại thư mục `mediation-lab` (chứa parent `pom.xml`):

```bash
mvn -version
mvn clean install
```

Maven sẽ build parent, alpha, beta và app theo reactor. `install` cũng cài POM/JAR các module vào local repository để bạn có thể gọi dependency plugin trên riêng `app/pom.xml` sau đó. Mặc dù alpha và beta có thể dùng các version commons-lang3 khác nhau khi tự compile, **maven-dependency-plugin chạy ở app** mới trả lời chính xác câu hỏi “version nào được chọn cho graph của app?”.

Chạy:

```bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Phần cấu trúc dependency **dự kiến** (đã bỏ log, nhánh parent và các thông tin trình bày không cố định):

```text
com.example.mediation:mediation-app:jar:1.0.0
+- com.example.mediation:mediation-alpha:jar:1.0.0:compile
|  \- org.apache.commons:commons-lang3:jar:3.12.0:compile
\- com.example.mediation:mediation-beta:jar:1.0.0:compile
```

Cây mặc định có thể không hiển thị ứng viên beta → commons-lang3:3.14.0 vì ứng viên này bị hòa giải xung đột. **Điểm kiểm chứng chính là commons-lang3:3.12.0 được chọn trong graph app**, không phải số lượng dòng log hoặc ký tự gạch nối của cây.

Để xem thông tin omitted/conflict trong những phiên bản plugin hỗ trợ:

```bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
```

Bạn có thể thấy một node ghi tương tự `omitted for conflict with 3.12.0`, thể hiện version 3.14.0 đã được khai báo ở một nhánh nhưng không thắng. Nếu output khác cách trình bày, hãy tập trung vào **effective resolved version** thay vì giả định mọi plugin build in cùng một thông điệp.

### 6.10. Chạy Java và kiểm chứng chức năng

Vì `mvn clean install` đã cài artifacts của các module, tại thư mục root chạy:

```bash
mvn -f app/pom.xml org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=com.example.mediation.app.App
```

Goal `exec:java` chạy `main` của app với dependency classpath Maven giải quyết cho app. **Hai module đều gọi được API StringUtils**. Dòng do code Java in ra chính xác:

```text
ALPHA | BETA
```

Maven còn có log plugin và BUILD SUCCESS; những dòng ấy **không thuộc output cố định do code Java in**.

**Chú ý quan trọng:** stdout này chứng minh code chạy, **không chứng minh version nào thắng**, vì `StringUtils.upperCase` có ở cả 3.12.0 và 3.14.0. Dùng `dependency:tree` để xác định version thắng thay vì suy luận từ dòng `ALPHA | BETA`.

### 6.11. Thí nghiệm A: đảo thứ tự direct dependencies của app

Trong **`app/pom.xml`**, chuyển dependency `mediation-beta` lên trước `mediation-alpha`, giữ mọi nội dung khác. Chỉ đổi thứ tự hai khối `<dependency>`; không sửa `<modules>` ở parent.

Lệnh kiểm tra lại:

```bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Dự kiến phiên bản được chọn là `commons-lang3:3.14.0`, vì hai đường vẫn cùng độ sâu, nhưng beta giờ đứng trước alpha. Java vẫn có thể in:

```text
ALPHA | BETA
```

vì cả hai API call đều tương thích. **Đổi thứ tự POM có thể đổi một JAR trên classpath mà không đổi mã nguồn hoặc stdout**, nên đây là yếu tố cần kiểm soát khi review thay đổi dependency.

Sau thí nghiệm, **khôi phục alpha đứng trước beta** như POM gốc trước khi làm mục tiếp theo.

### 6.12. Thí nghiệm B: dùng dependencyManagement, không cần đảo thứ tự

Trong **`app/pom.xml`**, giữ alpha trước beta, rồi chèn đoạn sau **ở cấp `<project>`, đứng cạnh `<dependencies>`**, không đặt vào bên trong một `<dependency>`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn bổ sung**, không phải POM hoàn chỉnh. Chạy:

```bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Dự kiến commons-lang3 version `3.14.0` được chọn, dù alpha vẫn là dependency đầu tiên. Điều này minh họa **consumer chủ động quản lý version transitive dependency**. Không có yêu cầu app phải import trực tiếp class commons-lang3 trong source.

Maven có thể hiển thị một số node `omitted for conflict` hoặc `version managed from...` khi bật verbose. Thông điệp cụ thể phụ thuộc plugin/resolver; giá trị cần xác minh là version ở resolved project dependency graph.

Để dọn ví dụ về trạng thái mặc định, xóa đoạn `dependencyManagement` mới thêm. Nếu muốn thử bản direct dependency, thay bằng một `<dependency>` rõ ràng cho `commons-lang3:3.14.0` trong `app/pom.xml`; lúc đó artifact là direct dependency của app, chỉ cách root một cạnh.

### 6.13. Thí nghiệm C: version nằm ở đường ngắn hơn

Giả sử graph chuyển từ hai đường cùng độ sâu sang:

```text
app
├── alpha
│   └── helper
│       └── commons-lang3:3.14.0  (3 cạnh)
└── beta
    └── commons-lang3:3.12.0      (2 cạnh)
```

Khi không có dependencyManagement hay yêu cầu version cứng can thiệp, **3.12.0 thắng vì đường qua beta ngắn hơn**, ngay cả khi alpha nằm trước trong `<dependencies>` của app. Sơ đồ ở đây là **mô hình minh họa**; không yêu cầu tạo thêm module helper vào bộ mã runnable.

Đó là lý do “dependency đầu tiên thắng” **chỉ áp dụng trong tình huống đồng độ sâu**, không thay thế nguyên tắc nearest-definition.

## 7. Những yếu tố làm thay đổi kết quả ngoài quy tắc nearest

### 7.1. `scope` và đường được phép tham gia classpath

Một dependency `test` có thể được sử dụng ở test classpath nhưng không nằm trong production runtime classpath theo cùng cách. Dependency `provided` thường cần ở compile/test nhưng không được Maven đóng vào runtime classpath theo scope thông thường. Scope của transitive dependencies còn được tính theo ma trận scope mediation/derivation.

Vì vậy, khi so sánh kết quả `dependency:tree`, phải nói rõ **đang nhìn graph cho phạm vi nào**. Chọn `-Dscope=runtime` hoặc kiểm tra graph của build thực tế khi cần hiểu runtime. Đừng so một cây bị lọc chỉ `test` với output toàn bộ scopes rồi kết luận version selection bất ổn.

### 7.2. `optional` và `<exclusions>` thay đổi các đường ứng viên

- Dependency được đánh dấu `optional=true` trong POM upstream có thể không được chuyển tiếp tự động cho consumer.
- `<exclusions>` cắt một artifact trong nhánh đi qua dependency đã gắn exclusion. Nó **không cấm artifact xuất hiện qua nhánh khác**.

Nếu app exclude commons-lang3 từ alpha nhưng không exclude ở beta trong ví dụ trên, đường alpha → commons-lang3 không còn cạnh tranh, và beta có thể là nguồn còn lại. Đó là **thay đổi tập đường đi**, không phải “Maven chọn phiên bản cao hơn”.

Trước khi dùng exclusion để ép version, hãy kiểm tra alpha có thực sự cần commons-lang3 ở runtime hay không. Một thư viện upstream đã compile với API phiên bản mới có thể hỏng nếu bị buộc dùng bản cũ/khác. `dependencyManagement` hoặc nâng cấp upstream thường là lựa chọn minh bạch hơn.

### 7.3. Version ranges và version requirements

Ngoài version tường minh như `3.14.0`, Maven POM còn cho phép version requirements:

| Khai báo | Ý nghĩa khái quát |
| --- | --- |
| `1.2` | Yêu cầu mềm/khuyến nghị version theo Maven version requirement semantics |
| `[1.2]` | Ràng buộc cứng vào đúng 1.2 |
| `[1.2,2.0)` | Từ 1.2 (gồm) tới trước 2.0 |
| `[1.5,)` | Tối thiểu 1.5 |
| `(,1.0],[1.2,)` | Các khoảng được phép kết hợp |

Dấu ngoặc vuông `[ ]` biểu thị đầu mút được gồm; ngoặc tròn `( )` biểu thị đầu mút không được gồm. Việc phiên bản có đáp ứng **hard requirements** hay không được xét trong resolver; nếu không có version nào đáp ứng tất cả ràng buộc cứng, build có thể thất bại.

**Đừng đơn giản hóa thành “nearest luôn thắng bất chấp hard range” hoặc “Maven luôn lấy version cao nhất”.** Các version requirements có bước lựa chọn riêng trong quá trình giải quyết; những lời giải thích về nearest-definition trong bài chủ yếu áp dụng cho các dependency với version thông thường và không có ràng buộc cứng mâu thuẫn.

Trong dự án cần reproducible builds, tránh dùng version ranges quá rộng cho artifact nền tảng nếu không có quy trình lock/kiểm soát thay đổi; kiểm thử trên một tập artifact cụ thể đã phê duyệt.

### 7.4. SNAPSHOT, release và cờ `-U`

Một artifact version `1.0-SNAPSHOT` có thể được phát hành lại dưới cùng phiên bản SNAPSHOT. Cờ `mvn -U` yêu cầu kiểm tra lại SNAPSHOT cập nhật và những release chưa phân giải được từ remote repository; nó **không tự nâng mọi dependency lên version cao nhất** và **không đổi quy tắc mediation**.

Nếu effective POM vẫn yêu cầu `commons-lang3:3.12.0`, chạy `mvn -U` không có nghĩa Maven sẽ tự chọn `commons-lang3:3.14.0`. Muốn thay version cần sửa POM/management/BOM hoặc điều kiện version phù hợp.

### 7.5. Profiles và parent POM

Một POM profile active có thể thêm dependency hoặc quản lý version; parent POM có thể truyền `dependencyManagement` xuống child. Hai máy chạy cùng source nhưng bật profile khác nhau sẽ có **effective POM khác nhau**, kéo theo dependency graph và version selection khác nhau.

Trước khi điều tra lỗi “máy tôi chọn version X, CI chọn Y”, so sánh lệnh Maven thực tế, profile active, effective POM và settings repository, không chỉ so một dòng `pom.xml` trong Git.

### 7.6. BOM không có nghĩa tất cả versions trong graph đều tự thay

Import BOM mang **managed versions** của BOM vào dependencyManagement. Nhưng:
- nó không tự thêm JAR được BOM liệt kê vào project;
- direct dependency có version explicit có ngữ nghĩa cần xét riêng;
- nhiều BOM cùng quản lý một artifact có quy tắc ưu tiên/merge, không thể mặc định “BOM cuối luôn thắng”;
- BOM chỉ quản lý những artifact matching đúng tọa độ quản lý.

Vì vậy khi BOM đổi version nhưng `dependency:tree` vẫn hiển thị version khác, cần mở **effective POM**, kiểm tra direct dependency, parent management, import order và các khai báo ghi đè tại consumer.

## 8. Công cụ kiểm chứng: dependency:tree, effective-pom và lệnh liên quan

### 8.1. Xem phiên bản đã chọn

Tại một project:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Để lọc **chỉ phần hiển thị** theo một artifact:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
```

`-Dincludes` không thay dependency graph/classpath, nó chỉ lọc những dòng được in. `-Dexcludes` của **goal tree** cũng là bộ lọc output; **không đồng nghĩa** `<exclusions>` trong POM.

### 8.2. Xem những ứng viên bị bỏ qua

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
```

Verbose tree có thể in thêm những node bị bỏ qua vì conflict hoặc duplicate. **Nó phục vụ chẩn đoán**, không nhất thiết là một cây có thể dùng trực tiếp làm runtime classpath vì có cả những ứng viên không được chọn. Trong output thường, Maven đã áp dụng mediation và loại các xung đột trước khi hiển thị.

### 8.3. Xuất graph và theo dõi thay đổi

Các định dạng hỗ trợ của dependency plugin bao gồm text, DOT, GraphML, TGF và JSON ở các version mới:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -DoutputType=dot -DoutputFile=dependency-tree.dot
```

File DOT có thể dùng để trực quan hóa graph. Đây là **output do plugin tạo**, không phải cách sửa mediation. Khi so sánh hai revision, dùng cùng plugin version, cùng Maven/JDK, cùng active profiles và cùng scope để kết quả có thể đối chiếu.

### 8.4. Đọc effective POM và profile đang active

```bash
mvn help:active-profiles
mvn help:effective-pom
```

`help:active-profiles` cho biết profile đang active. `help:effective-pom` cho biết dependencies/management sau khi áp dụng parent/profile. Nếu đang dùng settings profile/BOM, đọc thêm settings tương ứng. **Effective POM là dữ liệu để giải thích cấu hình; dependency:tree là dữ liệu để quan sát graph đã phân giải.** Hai công cụ bổ sung cho nhau.

### 8.5. Không dùng `dependency:tree` để thay thế kiểm thử

Tree xác nhận artifact/version được Maven chọn, nhưng không thể chứng minh API tương thích ở runtime. Trường hợp:

```text
alpha compile với commons-lang3:3.12.0
beta  compile với commons-lang3:3.14.0
app   chạy với commons-lang3:3.12.0
```

thì một lệnh gọi API **chỉ có trong 3.14.0** từ beta có thể dẫn tới `NoSuchMethodError` khi app thực sự đi vào đoạn code đó, dù tree hoàn toàn hợp lệ về mặt cấu trúc. Unit test, integration test và thử nghiệm ứng dụng đóng gói thực tế là bắt buộc khi quản lý version có khả năng không tương thích.

## 9. Những lỗi rất phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể và cách kiểm tra |
| --- | --- |
| Có hai version trong POM upstream nhưng tree app chỉ in một | Đúng: Maven đã mediation, phiên bản khác bị bỏ qua/ẩn; dùng verbose để điều tra |
| Maven chọn bản cũ dù có bản mới ở một nhánh khác | Đường tới bản cũ có thể gần hơn hoặc thắng tie; xem graph và dependencyManagement |
| Đảo thứ tự dependency làm version thay đổi | Hai ứng viên có cùng độ sâu; first-declaration tie-break; khóa version qua management |
| Thêm version trong dependencyManagement nhưng app không thấy JAR | Management không tự thêm dependency; artifact chỉ xuất hiện khi có đường dependency thật |
| Đã thêm management nhưng version vẫn bất ngờ | Xem direct dependency có version explicit không, effective POM, parent/BOM/profile và version requirements |
| Lỗi `NoSuchMethodError` sau nâng thư viện khác | Có thể runtime chọn version chưa có API mà upstream compile cần; kiểm tra tree và compatibility |
| `mvn -U` không đổi version được chọn | `-U` không thay quy tắc mediation hay tự nâng version được khai báo |
| Xóa cache `.m2` vẫn chọn cùng bản cũ | Cache không phải tiêu chí chọn version; phải sửa cấu hình graph khi cần |
| App tự import class từ thư viện chỉ đến qua transitive path | Hãy khai báo direct dependency để không bị thay đổi tình cờ khi upstream đổi graph |
| Chạy tree tại module alpha thấy 3.12.0, tại app thấy 3.14.0 | Bình thường: mediation thực hiện theo **từng project gốc** khác nhau |
| Plugin vẫn sử dụng version khác với project graph | Plugin dependencies có graph riêng; dependencyManagement của app không tự quản lý chúng |
| Cờ `-Dincludes` khiến JAR “biến mất” khỏi output | Chỉ lọc tree serialization; không xóa khỏi resolved classpath |
| CI chọn khác local | So Maven version, profile, effective POM, settings, repository metadata và cách build |
| Thêm `<exclusions>` để né conflict rồi app lỗi runtime | Có thể loại artifact mà upstream thực sự cần; thử dependencyManagement và test lại |

### Quy trình xử lý đề xuất

1. **Tái hiện:** xác định chính xác command đang lỗi (ví dụ `mvn clean verify`), Maven/JDK version và các profiles/parameters.
2. **Xem kết quả:** chạy `dependency:tree` tại **module đang có vấn đề**, không chỉ ở aggregator root.
3. **Tìm nguyên nhân:** bật `-Dverbose=true` để xem các version bị bỏ; xác định chiều dài đường, thứ tự khai báo và management.
4. **Xem mô hình:** dùng `help:effective-pom` để xác định version managed, direct explicit version, parent/BOM/profile.
5. **Chọn cách kiểm soát:** dùng direct dependency nếu source thực sự dùng artifact, dependencyManagement/BOM để khóa version chung; dùng exclusion khi muốn cắt một đường không mong muốn.
6. **Xác minh compatibility:** chạy `clean verify` và test runtime trong điều kiện đại diện; xem `NoSuchMethodError`/`ClassNotFoundException` nếu có.
7. **Giữ quyết định rõ ràng:** ghi chú tại sao một version được ghim và điều kiện nâng cấp, để tương lai không ai đảo thứ tự dependency vô tình đổi classpath.

## 10. Bài tập tự đánh giá

**Bài tập 1 — nearest.** Với graph:

```text
app -> A -> B -> Z:2.0
app -> C -> Z:1.0
```

Phiên bản nào thường thắng nếu không có yếu tố khác? **Z:1.0**, vì đường ngắn hơn.

**Bài tập 2 — tie.** `app` khai báo direct dependencies `alpha` trước `beta`; alpha → X:1.0 và beta → X:2.0 đều cách app hai cạnh. Nếu không có management/range khác, version nào thắng? **X:1.0**. Nếu đảo thứ tự alpha và beta? **Có thể là X:2.0**.

**Bài tập 3 — direct dependency.** Nếu app thêm một direct dependency `X:2.0`, khoảng cách app → X còn mấy cạnh? **Một**, và đây là cách bộc lộ chủ ý version của consumer.

**Bài tập 4 — management.** App quản lý `X:2.0` bằng dependencyManagement nhưng không có bất kỳ dependency path nào tới X. X có tự được tải thành runtime dependency không? **Không**.

**Bài tập 5 — compatibility.** Một module được compile với thư viện 3.14.0, nhưng app mediation chọn 3.12.0. Tree có thể PASS nhưng runtime có thể lỗi kiểu gì? **NoSuchMethodError** nếu gọi API chỉ có ở bản mới.

**Bài tập 6 — tool.** `mvn dependency:tree -Dincludes=group:artifact` có làm mediation khác đi không? **Không**, chỉ lọc output.

**Bài tập 7 — bonus.** Vì sao parent POM có `dependencyManagement` với version mới nhưng plugin `surefire` vẫn dùng dependency version riêng? **Vì project dependencies và plugin dependencies không cùng một graph.**

### Ghi nhớ

**Nearest definition chọn đường gần nhất; cùng độ sâu thì đường khai báo trước có thể thắng; dependencyManagement cho phép consumer kiểm soát version transitive một cách chủ động.** Dự đoán bằng graph, xác nhận bằng `dependency:tree`, kiểm tra cấu hình bằng `help:effective-pom` và xác nhận tương thích bằng build/test thực tế.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference: dependencies, management và version requirements](https://maven.apache.org/pom.html)
- [Maven Dependency Plugin — dependency:tree goal](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Resolver — How Resolver Works](https://maven.apache.org/resolver/how-resolver-works.html)
- [Maven — Common Misconceptions About Dependency Resolution](https://maven.apache.org/repositories/dependency-resolution-misconceptions.html)
- [Maven Guide — Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
