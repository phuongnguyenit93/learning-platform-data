# Đọc POM của thư viện để hiểu các phụ thuộc đi kèm

## 1. Vì sao thêm một thư viện lại kéo theo nhiều JAR?

Giả sử dự án của bạn chỉ khai một dependency:

```xml
<dependency>
    <groupId>dev.learning</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>1.0.0</version>
</dependency>
```

Tuy nhiên, `greeter-lib` cũng dùng một thư viện khác là `shared-model`. Khi Maven resolve dependency, nó không chỉ tải JAR của `greeter-lib`; Maven còn đọc **POM mô tả artifact `greeter-lib`** để tìm những dependency mà thư viện khai báo. Các dependency đủ điều kiện có thể đi vào classpath của ứng dụng dưới dạng **phụ thuộc bắc cầu (*transitive dependencies*)**.

```text
consumer-app (ứng dụng của bạn)
    |
    +-- greeter-lib:1.0.0          ← direct dependency
            |
            +-- shared-model:1.0.0 ← transitive dependency
```

Chính POM của `greeter-lib`, không phải việc Maven tự quét bytecode trong JAR để tìm các lệnh `import`, cung cấp khai báo giúp Maven đi tiếp đến `shared-model`.

Mục tiêu bài học:

1. Biết tìm và đọc đúng file `.pom` của một artifact cùng phiên bản đã resolve.
2. Phân biệt thông tin **được khai trong POM của thư viện** với dependency **thực sự có trong cây của ứng dụng**.
3. Hiểu tác động của `scope`, `optional`, `exclusions`, `dependencyManagement`, BOM, parent POM và cơ chế chọn phiên bản.
4. Dùng `mvn dependency:tree` để đối chiếu, điều tra các đường đi tới dependency bất ngờ.
5. Thực hành một dự án Java 17 gồm ba module, cho thấy một dependency duy nhất có thể đưa theo dependency thứ hai.

## 2. Maven dựa vào metadata nào?

Một tọa độ artifact thường được biểu diễn bởi **groupId:artifactId:version**, kèm `type`/`classifier` khi cần. Khi bạn khai dependency tới `dev.learning:greeter-lib:1.0.0`, Maven có thể tải hai loại file riêng từ repository:

```text
greeter-lib-1.0.0.jar   ← class/resource của thư viện
greeter-lib-1.0.0.pom   ← metadata khai báo project và dependencies
```

File có đuôi `.pom` về cơ bản là XML theo Maven Project Object Model. Tên đuôi file trong Maven repository thường là `.pom`, còn khi lập trình trong source repository nó thường mang tên `pom.xml`.

Một phần POM có thể trông như sau:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>dev.learning</groupId>
            <artifactId>shared-model</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

Đây là ví dụ về **POM rút gọn**, không phải bằng chứng một artifact công khai có thật. Trong dự án thực, POM có thể chứa `<parent>`, `<properties>`, `<dependencyManagement>`, `<profiles>`, `<repositories>`, `<build>`, metadata license... Muốn suy ra chính xác bản dependency sẽ được dùng, đôi khi cần đọc thêm POM cha, BOM và POM của chính ứng dụng.

Điều quan trọng nhất: **POM của thư viện cho biết thư viện đề xuất hoặc khai báo những dependency nào; cây dependency đã resolve của ứng dụng cho biết Maven cuối cùng chọn những artifact nào.** Hai danh sách này không nhất thiết trùng nhau.

## 3. Tìm đúng POM của thư viện ở đâu?

### 3.1. Trong Maven local repository

Maven mặc định lưu artifact đã tải hoặc cài tại local repository trong thư mục `~/.m2/repository` của người dùng (có thể được đổi qua settings hoặc tham số Maven).

Quy tắc chuyển GAV thành đường dẫn:

```text
groupId         dev.learning       → dev/learning/
artifactId      greeter-lib        → greeter-lib/
version         1.0.0              → 1.0.0/
POM file                            greeter-lib-1.0.0.pom
```

Vị trí thường thấy trên Linux/macOS:

```text
~/.m2/repository/dev/learning/greeter-lib/1.0.0/greeter-lib-1.0.0.pom
```

Trên Windows:

```text
%USERPROFILE%\.m2\repository\dev\learning\greeter-lib\1.0.0\greeter-lib-1.0.0.pom
```

Đường dẫn Windows ở trên giả định local repository dùng vị trí mặc định. Nếu tổ chức cấu hình repository khác, hãy kiểm tra `settings.xml`, biến môi trường hoặc tham số CLI thích hợp thay vì cố đọc một file không tồn tại.

**Lưu ý:** không nên sửa trực tiếp file `.pom` trong local repository để “sửa dependency”; thay đổi đó không tái lập được trên máy khác và có thể bị ghi đè khi artifact được tải lại. Hãy sửa POM của project bạn quản lý hoặc dùng cơ chế dependency management/exclusion có chủ đích.

### 3.2. Trên remote Maven repository

Nếu artifact được publish lên Maven Central hoặc repository nội bộ, metadata POM thường nằm tại đường dẫn dạng:

```text
https://repo.example.invalid/repository/maven-public/
    dev/learning/greeter-lib/1.0.0/greeter-lib-1.0.0.pom
```

URL trên chỉ minh họa; `example.invalid` không phải endpoint tải được. Với artifact công khai, bạn có thể dùng giao diện repository hoặc URL POM từ repository chính thức. Với repository private, Maven có thể cần credentials trong `settings.xml`.

Bạn cũng có thể yêu cầu Maven Dependency Plugin resolve một POM cụ thể, nếu artifact đó tồn tại trong repository đã cấu hình:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get \
  -Dartifact=dev.learning:greeter-lib:1.0.0:pom \
  -Dtransitive=false
```

Dòng lệnh trên dành cho **Bash** với ký tự nối dòng `\`; trên PowerShell hãy gõ trên một dòng hoặc dùng cú pháp nối dòng của PowerShell:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get -Dartifact=dev.learning:greeter-lib:1.0.0:pom -Dtransitive=false
```

Cú pháp artifact có dạng `groupId:artifactId:version[:packaging[:classifier]]`. `pom` chọn artifact kiểu POM; `-Dtransitive=false` yêu cầu **không** resolve toàn bộ cây dependency khi thực hiện thao tác lấy artifact. Ví dụ `dev.learning` chỉ có thể thực hiện sau khi bạn publish hoặc `mvn install` các module mẫu ở phần thực hành.

### 3.3. Đọc đúng **phiên bản**

Nếu ứng dụng giải quyết `greeter-lib:1.0.0` mà bạn mở POM của `greeter-lib:1.1.0`, danh sách dependencies có thể đã thay đổi. Tương tự, cùng `artifactId` nhưng khác `groupId` có thể là một thư viện hoàn toàn khác. Khi tra cứu, luôn ghi lại **groupId, artifactId, version, type, classifier và repository đang dùng** nếu có khác biệt.

## 4. Đọc POM theo thứ tự nào để hiểu dependency?

Khi mở file POM của thư viện, hãy đọc theo các bước:

1. **Xác định tọa độ project:** `<groupId>`, `<artifactId>`, `<version>`, `<packaging>`. Nếu thiếu `groupId` hoặc `version` ở cấp project, xem `<parent>`.
2. **Tìm `<dependencies>`:** đây là những dependency được project trực tiếp khai báo. Ghi lại tọa độ, `scope`, `optional`, `type`, `classifier` và `exclusions` nếu có.
3. **Tìm `<dependencyManagement>`:** các khai báo ở đây có thể cung cấp/điều phối version và scope khi một dependency thực sự được sử dụng; **không tự bổ sung tất cả artifact ở đây vào classpath**.
4. **Kiểm tra `<parent>` và `<properties>`:** version có thể là `${some.version}`, hoặc dependency được kế thừa từ parent. Đọc biểu thức XML mà chưa resolve property có thể khiến bạn kết luận sai version.
5. **Kiểm tra BOM imports:** một POM khác với `type=pom` và `scope=import` trong `dependencyManagement` có thể quản lý version cho cả nhóm thư viện.
6. **Đối chiếu với ứng dụng:** dùng `dependency:tree` trên POM ứng dụng vì scope, exclusions, dependency management và xung đột version của consumer quyết định cây cuối cùng.

### Phân biệt `dependencies` và `dependencyManagement`

Ví dụ POM có:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>transport-api</artifactId>
            <version>4.2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Điều đó **không có nghĩa** `transport-api:4.2.0` tự xuất hiện trong runtime classpath. Khi `transport-api` được dùng theo một khai báo dependency hoặc xuất hiện transitively, quản lý dependency có thể ảnh hưởng version được chọn. Cấu hình `dependencyManagement` của chính consumer có thể ghi đè việc chọn version của dependency bắc cầu. Cơ chế này khác việc khai một dependency trực tiếp.

Phần `dependencyManagement` **không điều khiển transitives của Maven plugin** trong `<build><plugins>`. Dependency dùng để chạy compiler/test plugin là một hệ thống riêng với project dependencies; đừng nghĩ thêm `dependencyManagement` của ứng dụng chắc chắn sửa được dependency của một plugin.

## 5. Tại sao một dependency trong POM chưa chắc đi theo consumer?

Maven không đưa mọi khai báo bên trong POM thư viện vào classpath của ứng dụng theo cùng một cách. Một số thông tin cần đọc cẩn thận:

| Trường trong `<dependency>` | Ý nghĩa | Tác động thường gặp đối với consumer |
| --- | --- | --- |
| `<scope>compile</scope>` | Cần cho biên dịch và chạy; là scope mặc định nếu không chỉ định | Có khả năng xuất hiện transitively ở classpath phù hợp |
| `<scope>runtime</scope>` | Không cần để compile mã chính của thư viện, nhưng cần khi chạy | Có thể xuất hiện ở runtime/test classpath của consumer |
| `<scope>provided</scope>` | Thư viện kỳ vọng môi trường cung cấp dependency | Thông thường không truyền như transitive dependency đến consumer |
| `<scope>test</scope>` | Dành cho biên dịch/chạy test của thư viện | Không truyền xuống consumer trong việc dùng thư viện bình thường |
| `<optional>true</optional>` | Dependency tùy chọn của thư viện | Không được tự động kéo qua dependency tới thư viện đó |
| `<exclusions>` | Loại một transitive dependency ở nhánh được chỉ định | Một đường đến artifact bị chặn; artifact vẫn có thể đi vào từ nhánh khác |
| `<type>`, `<classifier>` | Chọn dạng artifact khác JAR mặc định nếu cần | Ảnh hưởng artifact nào được resolve; không suy từ artifactId |
| `<version>` | Version mà tác giả thư viện khai | Có thể bị mediation hoặc dependencyManagement của consumer thay đổi |

Ví dụ thư viện khai:

```xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>core-api</artifactId>
        <version>2.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.example</groupId>
        <artifactId>jdbc-adapter</artifactId>
        <version>2.0.0</version>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.example</groupId>
        <artifactId>optional-metrics</artifactId>
        <version>1.0.0</version>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây chỉ là **đoạn POM minh họa** với các tọa độ `org.example` giả định, không phải project runnable độc lập.

Khi consumer khai dependency vào thư viện ấy, thông thường:

- `core-api` có thể được kéo theo để compile/run.
- `jdbc-adapter` có thể được kéo theo theo nhánh runtime.
- `optional-metrics` không tự truyền đến consumer nếu chỉ phụ thuộc vào thư viện trên; consumer muốn tính năng ấy phải tự khai dependency thích hợp.
- `junit-jupiter` dùng để test thư viện, không tự thành test dependency của consumer chỉ vì consumer dùng thư viện.

**Điều kiện cuối cùng vẫn phụ thuộc nhánh graph, scope áp dụng qua chuỗi dependency, exclusions và quản lý version của consumer.** Không chỉ nhìn một dòng `scope` rồi khẳng định mọi module sẽ có artifact ở tất cả classpath.

### Đọc `optional=true` cho đúng

`optional=true` không có nghĩa thư viện không sử dụng dependency. Nó có nghĩa **downstream consumer không tự động thừa hưởng dependency ấy** qua nhánh này. Nếu consumer cần chức năng tùy chọn, khai dependency một cách tường minh với version và scope phù hợp.

### Đọc `exclusions` cho đúng

Ví dụ consumer không muốn nhận `legacy-logger` từ `greeter-lib`:

```xml
<dependency>
    <groupId>dev.learning</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>legacy-logger</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

`exclusions` được khai **trên một cạnh dependency**, không phải lệnh cấm một artifact trên toàn hệ thống. Nếu một nhánh khác cũng mang `legacy-logger` vào, nó vẫn có thể xuất hiện. Hơn nữa, loại một dependency đang cần cho chức năng thật có thể dẫn đến lỗi `ClassNotFoundException`/`NoClassDefFoundError` khi chạy; phải hiểu tác dụng trước khi exclude.

## 6. Version thực tế: POM thư viện không có tiếng nói cuối cùng

Giả sử:

```text
consumer-app
├── greeter-lib:1.0.0
│   └── json-api:2.0.0
└── report-lib:1.0.0
    └── json-api:3.0.0
```

Cùng một `groupId:artifactId` đi đến hai version. Maven sử dụng các quy tắc dependency mediation và dependency management; nó **không tự chọn bản mới nhất** trong mọi trường hợp.

Các quy tắc cơ bản:

- **Nearest definition:** thông thường Maven chọn định nghĩa gần consumer hơn trong cây dependency.
- **Cùng độ sâu:** trong trường hợp hòa về khoảng cách, declaration được gặp trước theo thứ tự xét dependency có thể được chọn.
- **Direct declaration:** consumer có thể khai trực tiếp version muốn dùng; đây là một định nghĩa ở độ sâu gần nhất.
- **Dependency management:** consumer có thể kiểm soát version của những dependency (kể cả transitives thích hợp) mà nó quản lý; quản lý dependency có thể ưu tiên hơn quy tắc nearest khi resolve.

Ví dụ nếu consumer khai trực tiếp:

```xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>json-api</artifactId>
    <version>3.0.0</version>
</dependency>
```

thì consumer đã nói rõ version cần dùng cho dependency của mình, thay vì chỉ trông cậy version mà thư viện trung gian kéo theo. Đây là ví dụ XML minh họa, chưa chỉ ra một thư viện có thật.

Để quản lý version mà không tự thêm dependency vào project:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>json-api</artifactId>
            <version>3.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó **dùng `mvn dependency:tree` kiểm chứng** version được chọn và nhánh nào dẫn đến nó. Không tự đánh giá an toàn tương thích chỉ vì một version đã được ép: nếu API/ABI khác nhau, chương trình vẫn có thể gặp lỗi runtime.

### BOM không phải gói tất cả dependency vào ứng dụng

Một BOM theo kiểu Maven 3 phổ biến là POM có `<dependencyManagement>` cho một nhóm phiên bản. Consumer import nó bằng:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>5.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

BOM trên là ví dụ giả định. Import có tác dụng quản lý metadata/version tương ứng, **không đồng nghĩa tất cả artifact BOM nêu đều tự có trong classpath**.

## 7. POM của thư viện có thể cần parent và thuộc tính để hiểu đầy đủ

Rất nhiều thư viện không tự chứa mọi version trong file POM của chúng. Ví dụ:

```xml
<parent>
    <groupId>dev.learning</groupId>
    <artifactId>library-parent</artifactId>
    <version>1.0.0</version>
</parent>

<artifactId>greeter-lib</artifactId>

<dependencies>
    <dependency>
        <groupId>dev.learning</groupId>
        <artifactId>shared-model</artifactId>
        <version>${project.version}</version>
    </dependency>
</dependencies>
```

Đây là đoạn trích POM con, không phải XML project hoàn chỉnh. Nó minh họa:

- `groupId` và `version` của project có thể kế thừa từ parent.
- `${project.version}` là biểu thức Maven được đánh giá trong ngữ cảnh project; không nên đọc nó như một version literal của artifact.
- Parent POM có thể chứa `<dependencyManagement>`, `<properties>` hoặc `<dependencies>` được kế thừa.
- POM child và parent cần resolve được để Maven xây dựng effective model của artifact.

**Quan trọng:** `mvn help:effective-pom` từ **ứng dụng consumer** giúp bạn xem effective POM của ứng dụng, không tự thay thế việc đọc toàn bộ POM của từng thư viện. Nếu cần hiểu vì sao thư viện khai version cụ thể, đọc POM thư viện và các parent/BOM liên quan; sau đó xem **`dependency:tree` của consumer** để biết version cuối cùng được chọn trong graph.

Trong POM có `<profiles>`, những dependency/profile có điều kiện không phải lúc nào cũng được kích hoạt. Trạng thái profile và nguồn giá trị thuộc tính có thể ảnh hưởng effective model; đừng chỉ dựa vào một XML fragment mà kết luận về classpath cuối cùng.

## 8. Thực hành Java 17: tạo ba module và đọc POM của thư viện

Để không phụ thuộc một thư viện ngoài đang thay đổi, chúng ta tạo **thư viện nhỏ tại chỗ**, cài nó vào Maven local repository và quan sát consumer nhận một dependency bắc cầu.

### 8.1. Cấu trúc

```text
dependency-lab/
├── pom.xml
├── shared-model/
│   ├── pom.xml
│   └── src/main/java/dev/learning/model/Greeting.java
├── greeter-lib/
│   ├── pom.xml
│   └── src/main/java/dev/learning/greeter/Greeter.java
└── consumer-app/
    ├── pom.xml
    └── src/main/java/dev/learning/app/Main.java
```

Luồng dependency:

```text
consumer-app:1.0.0
    └── greeter-lib:1.0.0
            └── shared-model:1.0.0
```

`consumer-app` không khai trực tiếp `shared-model`; dependency này chỉ đi theo qua POM của `greeter-lib`. Ví dụ sử dụng dependency scope mặc định `compile` để dễ quan sát.

### 8.2. Root POM — `dependency-lab/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning</groupId>
    <artifactId>dependency-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-model</module>
        <module>greeter-lib</module>
        <module>consumer-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
</project>
```

Root POM có packaging `pom`, giữ thông tin parent và modules. Compiler Plugin version `3.13.0` được khai ở root để các module con kế thừa cấu hình; thuộc tính `maven.compiler.release` nhắm tới Java 17.

### 8.3. Module dữ liệu — `shared-model/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.learning</groupId>
        <artifactId>dependency-lab</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>shared-model</artifactId>
    <packaging>jar</packaging>
</project>
```

`groupId` và `version` được kế thừa từ parent. Nếu Maven không thể tìm parent theo `../pom.xml` hoặc local repository thì việc dựng model của module sẽ lỗi.

File `shared-model/src/main/java/dev/learning/model/Greeting.java`:

```java
package dev.learning.model;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Xin chao tu thu vien!";
    }
}
```

### 8.4. Module thư viện — `greeter-lib/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.learning</groupId>
        <artifactId>dependency-lab</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>greeter-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.learning</groupId>
            <artifactId>shared-model</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

Đây là **POM quan trọng nhất của bài**: `greeter-lib` khai trực tiếp `shared-model` trong `<dependencies>`, không khai `optional=true` và không đặt scope khác. Scope mặc định là `compile` nên dependency này đủ điều kiện truyền tiếp đến consumer.

File `greeter-lib/src/main/java/dev/learning/greeter/Greeter.java`:

```java
package dev.learning.greeter;

import dev.learning.model.Greeting;

public final class Greeter {
    private Greeter() {
    }

    public static String greet() {
        return Greeting.message();
    }
}
```

### 8.5. Module ứng dụng — `consumer-app/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.learning</groupId>
        <artifactId>dependency-lab</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>consumer-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.learning</groupId>
            <artifactId>greeter-lib</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

Chú ý ở `consumer-app/pom.xml` **chỉ có dependency `greeter-lib`**; không có dependency `shared-model`.

File `consumer-app/src/main/java/dev/learning/app/Main.java`:

```java
package dev.learning.app;

import dev.learning.greeter.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet());
    }
}
```

`Main` chỉ import API công khai của `greeter-lib`. Nó không trực tiếp import `Greeting`; đây là cách thiết kế phù hợp nếu ứng dụng chỉ sử dụng API của thư viện trung gian.

### 8.6. Build và cài ba module vào local repository

Yêu cầu: JDK 17+, Maven 3.x tương thích, có thể tải các plugin Maven khi build lần đầu.

Từ thư mục `dependency-lab/` chứa root `pom.xml`:

```bash
mvn -version
mvn clean install
```

Vì root POM khai các module, Maven reactor xây dựng parent và các module theo thứ tự phụ thuộc: `shared-model` trước `greeter-lib`, rồi `consumer-app`. Phase `install` cài artifact (và POM tương ứng) vào local repository cho các lời gọi Maven khác có thể resolve chúng.

Sau khi thành công, có thể xem các file đã được cài:

```text
~/.m2/repository/dev/learning/
├── dependency-lab/1.0.0/dependency-lab-1.0.0.pom
├── shared-model/1.0.0/shared-model-1.0.0.pom
├── greeter-lib/1.0.0/greeter-lib-1.0.0.pom
└── consumer-app/1.0.0/consumer-app-1.0.0.pom
```

Hãy mở `greeter-lib-1.0.0.pom` vừa cài. Bạn sẽ thấy thông tin project và dependency `shared-model`, đúng như khai báo trong `greeter-lib/pom.xml`. Với các bản Maven/consumer POM khác nhau, những phần XML có thể được sinh/chỉnh dạng khi publish, nên hãy dựa vào nội dung thực tế của artifact đang dùng.

### 8.7. Xem cây dependency thực sự của ứng dụng

Từ root `dependency-lab/`, sau bước install, chạy:

```bash
mvn -f consumer-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Phần cây phụ thuộc **kỳ vọng** là:

```text
dev.learning:consumer-app:jar:1.0.0
\ - dev.learning:greeter-lib:jar:1.0.0:compile
    \ - dev.learning:shared-model:jar:1.0.0:compile
```

Trong log thực, plugin thường vẽ nhánh bằng `+-`, `\-`, khoảng trắng và tiền tố `[INFO]`. Các dòng trên minh họa **nội dung quan hệ**, không khẳng định từng ký tự log giống hệt giữa các phiên bản và môi trường.

Đọc cây từ trên xuống: `consumer-app` trực tiếp phụ thuộc `greeter-lib`; `greeter-lib` phụ thuộc `shared-model`; Maven mang `shared-model` vào kết quả cuối cùng dù POM ứng dụng không khai nó.

Nếu sử dụng prefix plugin trong một project đã có version plugin thích hợp:

```bash
mvn -f consumer-app/pom.xml dependency:tree
```

Đó là dạng gọn của cùng mục đích. Dạng tọa độ plugin đầy đủ ở trên giúp cố định phiên bản `3.8.1` trong bài thực hành.

### 8.8. Chạy Java để kiểm tra các JAR trên classpath

Với dự án này, ứng dụng có các class trong **ba JAR riêng biệt**. JAR của `consumer-app` không phải *fat JAR* và không tự chứa `greeter-lib`/`shared-model`, vì vậy muốn chạy trực tiếp bằng `java` cần cung cấp cả ba JAR.

**Bash trên Linux/macOS** (từ root `dependency-lab/`):

```bash
java -cp "consumer-app/target/consumer-app-1.0.0.jar:greeter-lib/target/greeter-lib-1.0.0.jar:shared-model/target/shared-model-1.0.0.jar" dev.learning.app.Main
```

**Windows PowerShell** (dùng dấu `;` phân cách classpath):

```powershell
java -cp "consumer-app\target\consumer-app-1.0.0.jar;greeter-lib\target\greeter-lib-1.0.0.jar;shared-model\target\shared-model-1.0.0.jar" dev.learning.app.Main
```

Dòng **stdout chính xác của chương trình**:

```text
Xin chao tu thu vien!
```

Lệnh Java này là phép kiểm tra runtime; Maven giải quyết dependency lúc build, nhưng khi chạy với `java -cp` thủ công, chính bạn phải cung cấp classpath đầy đủ. Trong ứng dụng thực tế, có thể dùng plugin launch, container, Spring Boot packaging hoặc cơ chế assembly/shade phù hợp thay vì tự nối đường dẫn JAR.

### 8.9. Thí nghiệm về dependency trực tiếp và gián tiếp

Nếu bạn sửa `Main.java` để **trực tiếp import `dev.learning.model.Greeting`**, nó vẫn có thể compile nhờ `shared-model` đang có trên compile classpath theo đường transitive. Nhưng đây là coupling với thư viện mà POM ứng dụng không trực tiếp khai; nếu `greeter-lib` đổi hoặc bỏ dependency `shared-model`, build của ứng dụng có thể đột ngột thất bại.

**Quy tắc bảo trì tốt:** nếu source của bạn **trực tiếp sử dụng API của một artifact**, cân nhắc khai artifact đó **trực tiếp** trong `consumer-app/pom.xml`. Transitive dependencies có ích nhưng không nên thay thế khai báo những dependency mà mã của bạn thực sự dùng.

## 9. Điều tra dependency bất ngờ trong dự án thực tế

Quy trình gợi ý:

**Bước 1 — xác định artifact xuất hiện:** đọc cả GAV, type, classifier và scope từ `dependency:tree`. Nếu Maven chọn version khác mong đợi, lưu lại version thực tế ấy để điều tra.

**Bước 2 — tìm đường đi từ ứng dụng:** xem nhánh nào mang artifact đó vào; có thể có nhiều đường đi khác nhau, và Maven chỉ hiển thị các node đã chọn theo thuật toán resolve.

**Bước 3 — mở POM của dependency trực tiếp trung gian:** nhìn `<dependencies>`, `scope`, `optional`, `exclusions` và source POM parent/BOM nếu cần. Đây là câu hỏi: “Thư viện nào khai nó và khai như thế nào?”

**Bước 4 — xem POM consumer:** đọc dependency management, BOM, exclusions, direct declarations và profiles. Đây là câu hỏi: “Consumer có làm thay đổi kết quả không?”

**Bước 5 — chạy lại `dependency:tree` sau thay đổi:** xác minh graph đã đổi đúng như dự kiến; chạy compile/test/integration tests để phát hiện API incompatibility.

Một số lệnh thực tế:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.example:json-api
mvn dependency:tree -Dscope=runtime
mvn dependency:analyze
mvn help:effective-pom
```

- `-Dincludes` có thể lọc theo tọa độ để tìm artifact/nhánh liên quan; cú pháp lọc đầy đủ trong tài liệu Maven Dependency Plugin.
- `-Dscope=runtime` lọc cây theo mục đích runtime; không tự sửa dependency.
- `dependency:analyze` hỗ trợ phát hiện một số dependency được dùng nhưng chỉ được khai transitively hoặc được khai mà không dùng theo phân tích bytecode; đây là **tín hiệu hỗ trợ**, không phải chứng cứ tuyệt đối (ví dụ reflection và dynamic loading có thể khó phát hiện).
- `help:effective-pom` giúp xem POM hiệu lực của **project đang chạy Maven**.

**Không sửa version hoặc exclusions chỉ dựa vào cây mà chưa có test.** Việc loại thư viện dễ thấy là “thừa” có thể làm tính năng khác lỗi ở runtime, đặc biệt trong ứng dụng dùng reflection, service loader hoặc SPI.

## 10. Một số cạm bẫy đặc biệt khi đọc POM

### 10.1. Thư viện có POM nhưng dependency không được tải

Đọc thấy một dependency trong `<dependencies>` nhưng nó không có trong `dependency:tree` của consumer có thể do `scope=test/provided`, `optional=true`, `exclusions`, profile không kích hoạt hoặc mediation loại một version. Trước khi kết luận plugin lỗi, kiểm tra từng yếu tố đó.

### 10.2. Cây có dependency nhưng file POM đang mở không thấy

Dependency có thể đến từ **nhánh khác**, từ parent hoặc từ dependency transitively xa hơn. Có thể bạn đang mở POM của **version khác** với version thực tế. Hãy đọc GAV và đường nhánh trong tree rồi lần ngược từng POM.

### 10.3. Có nhiều đường tới cùng artifact

Maven hòa giải xung đột version theo quy tắc và cấu hình đã nêu. Đừng suy ra “hai đường là Maven sẽ đưa hai phiên bản JAR vào classpath”. Cây cuối cùng thường có một version được chọn cho cùng artifact coordinates phù hợp; các tool/phiên bản có thể có chế độ hiển thị các node bị loại khi debug.

### 10.4. Parent/BOM làm version trông “biến mất”

Nếu `<dependency>` không có `<version>`, có thể version được cung cấp bởi `dependencyManagement` từ POM hiện tại, parent hoặc BOM. Nếu property chứa `${lib.version}`, phải tìm nguồn giá trị thực. Không thay mọi version bằng bản tự đoán khi chưa hiểu cách project quản lý dependency.

### 10.5. Plugin dependency không phải project dependency

POM có `<build><plugins>` chứa Maven Compiler Plugin, Surefire hay Shade Plugin. Các plugin có dependency riêng phục vụ **chạy plugin**, nhưng chúng không tự trở thành compile/runtime dependency của ứng dụng. Kiểm tra đúng graph: project dependencies và plugin dependencies là hai phạm vi khác nhau.

### 10.6. POM metadata khác file JAR

POM không mô tả toàn bộ class hay bảo đảm một JAR có tất cả class mà bạn mong muốn. Ngược lại, một JAR có thể mang code đã shaded/relocated. Nếu vấn đề là `ClassNotFoundException`, hãy kết hợp dependency graph, nội dung JAR, classpath thực và hướng dẫn của nhà phát hành.

## 11. Checklist trước khi kết luận “thư viện này mang theo gì?”

- [ ] Đã xác định đúng **GAV/type/classifier/version** của thư viện mà ứng dụng resolve.
- [ ] Đã tìm đúng file `.pom` trong local/remote repository, không chỉ mở trang README.
- [ ] Đã đọc `<dependencies>` và phân biệt direct với transitive.
- [ ] Đã xét `scope`, `optional`, `exclusions` cho từng dependency đáng chú ý.
- [ ] Đã phân biệt `dependencyManagement` và BOM với dependency thật sự được đưa vào graph.
- [ ] Đã theo dấu parent POM/properties nếu version hoặc groupId được kế thừa.
- [ ] Đã kiểm tra `mvn dependency:tree` của **consumer**, không chỉ tree của thư viện.
- [ ] Đã xét xung đột version và chính sách quản lý version của ứng dụng.
- [ ] Nếu source dùng API của artifact transitively, đã đánh giá việc khai direct dependency.
- [ ] Khi đổi version hoặc exclusion, đã chạy build/test và kiểm tra runtime.
- [ ] Không chỉnh POM trong `~/.m2/repository` để “vá” dependency cho riêng máy cá nhân.

**Ghi nhớ:** POM của thư viện là **bản khai dependencies đầu vào**; Maven Resolver kết hợp các POM trên graph với scope, optional, exclusion, parent/BOM và dependency management của **consumer** để quyết định **classpath cuối cùng**. Muốn biết “thư viện này có thể kéo theo gì”, hãy đọc POM; muốn biết “ứng dụng đang thực sự dùng gì”, hãy chạy `dependency:tree`.

## Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to Optional and Excludes Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Dependency Plugin — dependency:get](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
