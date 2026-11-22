# Phân biệt dependencies với dependencyManagement trong Maven

## 1. Cùng chứa `<dependency>`, nhưng khác vai trò

Maven dùng **`dependencies`** để biết **module thực sự cần những thư viện nào**; dùng **`dependencyManagement`** để đặt **chính sách quản lý** những thư viện ấy, nhất là phiên bản, scope và các thông tin phù hợp khi chúng được sử dụng.

Đây là một trong những phân biệt quan trọng nhất khi thiết kế dự án nhiều module và khi nhập BOM (Bill of Materials).

- **`project/dependencies/dependency`**: tạo một dependency trực tiếp của module. Maven giải quyết artifact và các dependency bắc cầu phù hợp, sau đó xây dựng compile/test/runtime classpath.
- **`project/dependencyManagement/dependencies/dependency`**: định nghĩa một **managed dependency**, không tự thêm artifact vào dependency graph hoặc classpath chỉ vì có khai báo.

Đoạn này **chỉ quản lý** Commons Lang:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đoạn này mới **khai báo sử dụng** Commons Lang:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

Khi hai đoạn cùng nằm trong một POM hợp lệ, Maven lấy version `3.14.0` từ management cho dependency trực tiếp, và scope mặc định là **compile**. Nếu chỉ có đoạn thứ nhất, Commons Lang **không tự xuất hiện trong main compile classpath**, nên mã Java import `StringUtils` có thể không biên dịch được.

**Công thức ghi nhớ:** `dependencyManagement` = *nếu cần thư viện X, dùng quy tắc gì*; `dependencies` = *module này thực sự cần X*.

## 2. Bảng so sánh

| Tiêu chí | `dependencies` | `dependencyManagement` |
| --- | --- | --- |
| Đặt ở đâu? | Trực tiếp dưới `project`. | Dưới `project/dependencyManagement`. |
| Vai trò | Khai báo dependency của module. | Quản lý thông tin khi dependency được gặp. |
| Tự thêm dependency vào classpath? | Có, theo scope và graph được giải quyết. | **Không**. |
| Dependency có cần ghi version? | Có, trừ khi version được quản lý hợp lệ. | Entry quản lý cụ thể cung cấp version hoặc nhận được version phù hợp từ cơ chế khác. |
| Có thể ảnh hưởng dependency bắc cầu? | Có: tạo nhánh phụ thuộc. | Có: điều khiển version/scope/default của dependency phù hợp đã xuất hiện trong graph. |
| Có thể kế thừa từ parent? | Có; parent dependencies có thể được child kế thừa. | Có; child nhận **quy tắc quản lý** mà không bị ép dùng mọi thư viện. |
| Vai trò trong BOM | Không phải cơ chế nhập BOM chính. | Là nơi chứa managed dependencies và import BOM. |
| Hiển thị trong `dependency:tree` | Artifact được chọn xuất hiện trong graph. | Entry chỉ được quản lý không tự xuất hiện trong tree. |
| Dùng để quản lý plugin? | Không: đây là dependency của project. | Không quản lý các dependency bắc cầu của plugin. |

Chú ý sự khác biệt về vị trí XML. Cả hai có thẻ con `<dependencies>`, nhưng **Maven không coi chúng là cùng một danh sách**. Có thể quản lý một artifact và cũng khai báo sử dụng nó trong cùng POM mà không phải khai báo trùng sai.

## 3. Khóa định danh và nguyên tắc lấy version

Maven đối chiếu một dependency với entry tương ứng trong `dependencyManagement` bằng các thành phần:

**`groupId + artifactId + type + classifier`**

Với JAR thông thường, `type` mặc định là `jar`, `classifier` vắng mặt, nên hai thuộc tính `groupId` và `artifactId` thường đủ để tìm managed entry.

- **Version không nằm trong khóa đối chiếu**: version là giá trị có thể được management cung cấp hoặc điều khiển.
- Nếu quản lý `groupId:artifactId` cho artifact **JAR mặc định**, không nên mặc định rằng entry ấy cũng quản lý bản **test-jar** hoặc artifact có classifier `tests`.
- Scope và những thông tin hợp lệ khác có thể được quản lý như default, nhưng một khai báo dependency trực tiếp có trường tường minh cần được xét theo quy tắc hợp nhất Maven; không nên nghĩ management luôn ghi đè tất cả.

### Ba trường hợp quan trọng

**A. Dependency không có version, management có version:** Maven dùng version được quản lý.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

**B. Dependency trực tiếp ghi version tường minh:** giá trị tường minh của dependency trực tiếp được dùng cho chính dependency ấy, không tự bị thay bằng managed version khác.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.13.0</version>
    </dependency>
</dependencies>
~~~

Ở đây có **chủ đích override** version trực tiếp thành `3.13.0`; cần kiểm chứng tính tương thích và xem dependency graph, không sử dụng override chỉ để tránh quản lý version tập trung.

**C. Dependency không có version và không được quản lý:** POM có thể bị Maven từ chối với lỗi tương tự:

~~~text
'dependencies.dependency.version' for org.apache.commons:commons-lang3:jar is missing
~~~

Đây là trích đoạn **nhận diện lỗi**, không phải một stdout cố định. Có thể sửa bằng cách ghi version trực tiếp hoặc định nghĩa/import `dependencyManagement` phù hợp. Không cần ghi lại version ở mọi module nếu parent/BOM đã quản lý đúng.

## 4. Ví dụ Java 17 hoàn chỉnh: management và usage phối hợp

Ta tạo project `managed-deps-demo` dùng **Commons Lang** trong mã chính và **JUnit Jupiter** để test. Phiên bản đặt trong `dependencyManagement`; phần `dependencies` chọn hai thư viện thật sự cần.

Cần JDK 17+, Maven tương thích với các plugin được chọn và một repository tải artifact hợp lệ.

Cấu trúc:

~~~text
managed-deps-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/management/Greeting.java
    └── test/java/vn/example/management/GreetingTest.java
~~~

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>managed-deps-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.14.0</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

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
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Những gì Maven hiểu:

1. `commons-lang3` có version **3.14.0**, scope **compile** do không ghi scope trong dependency sử dụng.
2. `junit-jupiter` có version **5.10.2**, scope **test** do ghi tường minh ở dependency sử dụng.
3. Hai entry quản lý không phải hai dependency bổ sung ngoài hai entry ở `dependencies`.
4. Version của Compiler/Surefire/JAR Plugin được cấu hình riêng ở `build/plugins`: **không phải do project dependencyManagement quản lý**.

### 4.2. src/main/java/vn/example/management/Greeting.java

~~~java
package vn.example.management;

import org.apache.commons.lang3.StringUtils;

public final class Greeting {
    private Greeting() {
    }

    public static String hello(String name) {
        return "Xin chào, " + StringUtils.capitalize(name) + "!";
    }

    public static void main(String[] args) {
        System.out.println(hello("maven"));
    }
}
~~~

`Greeting` cần Commons Lang để biên dịch và chạy. `StringUtils.capitalize("maven")` cho ra **Maven**.

### 4.3. src/test/java/vn/example/management/GreetingTest.java

~~~java
package vn.example.management;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void formatsMessage() {
        assertEquals("Xin chào, Maven!", Greeting.hello("maven"));
    }
}
~~~

Test code cần JUnit, nhưng mã ứng dụng chính không cần JUnit khi chạy bình thường.

### 4.4. Chạy Maven và xem dependency tree

Từ thư mục chứa POM:

~~~bash
mvn --version
mvn -B clean verify
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
~~~

Trong môi trường phù hợp, Maven biên dịch hai source, chạy JUnit và tạo JAR. Cây dependency sẽ có các nhánh tương tự:

~~~text
vn.example:managed-deps-demo:jar:1.0.0
+- org.apache.commons:commons-lang3:jar:3.14.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.10.2:test
~~~

Đây là **trích đoạn minh họa**, không phải toàn bộ dependency tree vì JUnit có dependency bắc cầu. Dù `dependencies` không ghi version, tree vẫn phản ánh version được quản lý.

### 4.5. Chạy mã Java và runtime classpath

JAR thông thường không tự chứa mọi dependency JAR. Ta copy các dependency cần cho runtime:

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/runtime-libs
~~~

`-DincludeScope=runtime` ở Dependency Plugin bao gồm **compile + runtime dependencies**, không chỉ các mục có thẻ scope runtime; thường không copy JUnit chỉ có scope test.

**Linux/macOS**:

~~~bash
java -cp "target/classes:target/runtime-libs/*" vn.example.management.Greeting
~~~

**Windows PowerShell/cmd.exe**:

~~~powershell
java -cp "target\classes;target\runtime-libs\*" vn.example.management.Greeting
~~~

**Stdout chính xác của riêng lệnh Java:**

~~~text
Xin chào, Maven!
~~~

Java launcher không tự đọc `pom.xml`. `target/classes` cung cấp class chính và `target/runtime-libs/*` thêm các JAR ngoài vào classpath. Java 17 phải được cài và terminal cần hỗ trợ Unicode để hiển thị chính xác tiếng Việt.

## 5. Chứng minh management không tự thêm thư viện

Trong POM mẫu mục 4, **giữ nguyên** `dependencyManagement` nhưng **xóa dependency Commons Lang khỏi phần `dependencies`**. Khi đó phần sử dụng chỉ còn:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **đoạn thay thế**, không phải POM độc lập. Chạy:

~~~bash
mvn -B clean compile
~~~

Mã Java vẫn import `StringUtils`, nhưng dependency Commons Lang không được khai báo sử dụng và không tự được đưa vào main compile classpath. Maven Compiler Plugin có thể báo:

~~~text
package org.apache.commons.lang3 does not exist
cannot find symbol: variable StringUtils
~~~

Trích đoạn nhận diện lỗi có thể khác về số dòng và cách trình bày. **Đúng cách sửa là thêm Commons Lang vào `dependencies`**, không cần sao chép lại version nếu đã quản lý.

Tình huống đối lập: nếu xóa hẳn `dependencyManagement` nhưng giữ Commons Lang ở `dependencies` **với version tường minh**, dự án vẫn có dependency hợp lệ. Management không bắt buộc cho mọi dự án nhỏ; nó giúp tập trung version khi số dependency/module tăng.

## 6. Parent POM và dự án đa module

Một parent POM thường là nơi tốt để quản lý version chung. Các module con kế thừa `dependencyManagement` nhưng chỉ **tự chọn dependency thực sự cần**.

Cấu trúc minh họa:

~~~text
parent-project/
├── pom.xml          (parent + aggregator, packaging pom)
├── application/
│   └── pom.xml
└── batch/
    └── pom.xml
~~~

### 6.1. parent-project/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>parent-project</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>application</module>
        <module>batch</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.14.0</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

Parent POM trên cung cấp version chung. Nó **không tự khiến Commons Lang/JUnit xuất hiện trong classpath của tất cả module**.

### 6.2. Module application muốn dùng Commons Lang

**application/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>parent-project</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>application</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Module này nhận Commons Lang `3.14.0` từ management của parent. `groupId` và version của module có thể kế thừa parent, không phải ghi lại.

### 6.3. Module batch chưa cần thư viện nào

**batch/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>parent-project</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>batch</artifactId>
</project>
~~~

`batch` kế thừa quy tắc quản lý nhưng **không có Commons Lang** trên classpath chỉ vì parent đã ghi nó trong `dependencyManagement`. Khi code của batch cần thư viện, thêm khai báo tại `batch/pom.xml`.

Các POM ở mục 6 là **mô hình cấu hình**, không chứa source Java để chạy ứng dụng. Ví dụ có source Java và stdout chính xác đã có ở mục 4.

### 6.4. Aggregator khác parent

Một POM có `<modules>` để điều phối reactor là **aggregator**. Một POM được module con tham chiếu qua `<parent>` là **parent**. Chúng có thể là cùng file như ví dụ, nhưng **`<modules>` không tự tạo quan hệ kế thừa**. Một module chỉ kế thừa management nếu nó chỉ định parent phù hợp (hoặc nhận qua một quan hệ quản lý khác).

## 7. Đặt dependency trong parent `dependencies` sẽ khác

Giả sử parent khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
~~~

Trong cơ chế inheritance thông thường, **dependency trực tiếp của parent được kế thừa vào các child POM**. Điều đó có thể khiến tất cả module con nhận Commons Lang, kể cả module `batch` không sử dụng thư viện.

Nếu cùng entry nằm trong **parent `dependencyManagement`**, child chỉ nhận **chính sách version**, còn child nào cần mới đặt mục tương ứng trong `dependencies`.

**Quy tắc thiết kế phổ biến:** parent quản lý phiên bản tại `dependencyManagement`; module chọn dependency tại `dependencies`. Đặt dependency trong parent `dependencies` không phải luôn sai — ví dụ mọi module thật sự cần nó — nhưng phải hiểu tác động trên toàn bộ con.

## 8. BOM là dependencyManagement được chia sẻ qua import

**BOM** (Bill of Materials) là artifact POM cung cấp tập version được thiết kế để dùng cùng nhau. Đối với mô hình Maven POM `4.0.0` quen thuộc, cách nhập BOM là:

- Đặt dependency BOM **bên trong `dependencyManagement/dependencies`**.
- Ghi **`<type>pom</type>`**.
- Ghi **`<scope>import</scope>`**.
- Chọn BOM artifact và version có thực, tương thích với dự án.

Ví dụ nhập **JUnit BOM**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.10.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây chỉ là **đoạn đặt trong `<project>`**. `junit-bom` giúp Maven biết version tương ứng cho nhiều JUnit artifacts; **nó không tự thêm JUnit Jupiter vào test classpath**.

Module muốn chạy JUnit Jupiter vẫn khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

BOM cấp version, dependency sử dụng cấp nhu cầu. Nếu module không viết test JUnit, chỉ import BOM không có nghĩa module tự có JUnit library.

**Không đặt BOM vào `project/dependencies` thông thường rồi ghi `scope=import`**: theo mô hình Maven BOM truyền thống, import scope chỉ dùng trong `dependencyManagement` với type `pom`.

### BOM và parent không thay thế hoàn toàn cho nhau

Một dự án chỉ có **một parent trực tiếp**, nhưng có thể **import nhiều BOM**. Một parent có thể quản lý cấu hình plugin, resources, properties, modules và dependency policies; BOM import chủ yếu mang vào **managed dependencies**, không phải toàn bộ cấu hình build của POM đó.

Maven 4 giới thiệu thêm khả năng BOM/packaging riêng trong mô hình mới; khi dùng Maven 4 cần kiểm tra tài liệu tương ứng. Cú pháp `type=pom` + `scope=import` ở trên vẫn là cách học nền tảng cho POM 4.0.0/Maven 3.

## 9. Nhiều BOM, entry trực tiếp và thứ tự ưu tiên

Nếu BOM X và BOM Y đều quản lý cùng artifact nhưng khác version, **thứ tự import có thể ảnh hưởng version được sử dụng**.

Theo hướng dẫn dependency mechanism của Maven:

- **Managed dependency khai báo trực tiếp trong POM nhập BOM** có thể ưu tiên hơn entry được nhập cho cùng khóa.
- Nếu không có entry trực tiếp và hai BOM cùng quản lý một artifact, **BOM được liệt kê trước thường thắng**.
- Cơ chế import có thể diễn ra đệ quy nếu BOM nhập BOM khác.
- Trong dự án có parent/child và override, cần đối chiếu effective model; **không suy luận chỉ từ thứ tự nhìn thấy trong một POM**.

Ví dụ về cấu trúc import:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>bom-x</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>bom-y</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây chỉ là **đoạn minh họa thứ tự import**; `vn.example:bom-x` và `bom-y` không bảo đảm tồn tại ở repository. Muốn thực hành thật, phải sử dụng BOM hợp lệ, công bố hoặc cài chúng trước.

**Không thay thứ tự BOM trong sản phẩm thật chỉ để “chọn version mới”** nếu chưa kiểm tra các artifact bị overlap và chạy test hồi quy. Một thay đổi nhỏ trong import order có thể thay version của nhiều dependency khác nhau.

## 10. dependencyManagement tác động tới dependency bắc cầu

Maven có **transitive dependencies**: nếu A dùng B và B dùng C, C có thể trở thành dependency của A theo scope/optional/exclusions và các quy tắc mediation.

Giả sử:

~~~text
Ứng dụng A
  |
  +-- library-b:1.0
        |
        +-- library-d:2.0 (transitive)
~~~

A có thể khai báo `library-b` mà không khai báo `library-d` trực tiếp. Nếu POM của A có managed entry cho D:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>library-d</artifactId>
            <version>1.5.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

thì Maven có thể dùng version **1.5.0** cho dependency D xuất hiện trong graph, vì **dependencyManagement của project áp dụng cho transitive project dependencies** khi khóa phù hợp. Đây là một cách giữ các thư viện bắc cầu tương thích mà không cần thêm D thành dependency trực tiếp chỉ để ép version.

**Hai điểm không được quên:**

1. `dependencyManagement` **không tự thêm D** nếu D không xuất hiện qua nhánh nào và không được khai báo trực tiếp.
2. Các tọa độ `vn.example:library-b:1.0` và `vn.example:library-d:1.5.0` ở đây chỉ là **ví dụ khái niệm**, không phải artifact có thật để tải.

### So với version mediation

Nếu D đến từ nhiều nhánh với các version khác nhau và không có management quyết định, Maven thường áp dụng **nearest definition** (dependency gần root hơn); nếu độ sâu bằng nhau, **khai báo trước thắng** theo quy tắc thông thường. `dependencyManagement` giúp kiểm soát version transitive vượt khỏi nhiều kết quả mediation mặc định.

Một dependency trực tiếp có version tường minh có cơ chế ưu tiên riêng, nên **không suy diễn rằng một managed version có thể bất chấp mọi version trực tiếp**. Chẩn đoán kết quả bằng `dependency:tree` của module đang build.

### Optional và exclusions vẫn có hiệu lực

Nếu một dependency được đánh dấu **`optional=true`** hoặc bị **`exclusions`** loại khỏi nhánh, management không tự kéo nó quay lại. Management không phải lệnh “đưa artifact này vào classpath bằng mọi giá”.

Nếu mã nguồn của A **import trực tiếp API của D**, tốt hơn nên khai báo D **trực tiếp** ở `dependencies` của A. Điều này mô tả đúng nhu cầu của module và tránh sự phụ thuộc tình cờ vào cấu trúc transitive của B.

## 11. Management có thể quản lý scope và exclusions

Ví dụ quản lý JUnit Jupiter là scope test:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi module khai báo JUnit không có scope/version tường minh trong hoàn cảnh áp dụng phù hợp, Maven có thể lấy các giá trị quản lý đó. Nhưng ở những codebase lớn, **ghi `<scope>test</scope>` ngay trong dependency sử dụng JUnit** giúp người đọc biết tại sao thư viện không nằm trong runtime của ứng dụng.

`dependencyManagement` còn hỗ trợ một số metadata như `exclusions`, `type` và `classifier`. **Type/classifier phải khớp** với dependency muốn quản lý. Dùng exclusion tập trung cần cẩn thận: một thư viện bị loại có thể vẫn cần ở runtime và khiến JVM báo `ClassNotFoundException` hoặc `NoClassDefFoundError`.

Không cần thêm các trường tùy chọn vào management chỉ vì muốn cấu hình “đầy đủ”. Quản lý version chung thường là mục tiêu quan trọng nhất; những mặc định khác chỉ nên có khi nhóm thật sự thống nhất chính sách.

## 12. Phân biệt dependencyManagement với pluginManagement

Một POM Maven còn có:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

**`pluginManagement`** quản lý version/cấu hình cho Maven plugin. **`dependencyManagement`** quản lý project dependencies. Chúng **không thay thế nhau**.

Tài liệu Maven nêu rõ dependencyManagement **không ảnh hưởng dependency bắc cầu của các plugin** được dùng trong cùng effective POM. Plugin có cơ chế classpath và dependencies phục vụ chính nó; nếu cần cấu hình thư viện của plugin, phải xem cơ chế plugin/dependencies và tài liệu riêng.

Đừng nhầm thêm `maven-compiler-plugin` vào project `<dependencies>` là đã cấu hình goal `compiler:compile`. Compiler là Maven build plugin; nó chạy do packaging/lifecycle binding hoặc execution phù hợp, không phải vì được đặt vào dependencies của ứng dụng.

Một số POM parent vừa có `dependencyManagement` cho library, vừa có `pluginManagement` cho plugin version. Đây là **kiểu quản lý tập trung hợp lý**, nếu module con vẫn chọn đúng dependencies và plugin cần thiết.

## 13. Quan sát bằng effective POM và dependency tree

Để hiểu tại sao version nào đó được chọn, nên dùng **hai góc nhìn**:

- **Effective POM**: Maven thấy cấu hình gì sau khi kế thừa parent, áp dụng profile, import BOM và hợp nhất model?
- **Dependency tree**: module thực sự có những dependency nào, version/scope và đường đi bắc cầu của chúng?

### 13.1. Xem effective POM

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:active-profiles
~~~

Khi đang ở parent và muốn xem riêng module:

~~~bash
mvn -f application/pom.xml help:effective-pom -Doutput=effective-application-pom.xml
~~~

Ở phiên bản Maven Help Plugin có hỗ trợ, `-Dverbose` có thể bổ sung chú thích về nguồn cấu hình:

~~~bash
mvn help:effective-pom -Dverbose -Doutput=effective-verbose-pom.xml
~~~

**Không chỉnh file effective-pom sinh ra**; nó chỉ giúp chẩn đoán. Khi thấy một mục Commons Lang trong `dependencyManagement` của effective POM, không được kết luận module đã dùng Commons Lang. Phải kiểm tra `dependencies` và graph tương ứng.

### 13.2. Xem dependency tree

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
~~~

Lọc riêng Commons Lang:

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Nếu artifact chỉ có ở managed entries và không được dùng trực tiếp/bắc cầu, nó sẽ **không hiện như một dependency được chọn**. Khi tìm version xung đột, hãy xem cây của chính module đang bị lỗi chứ không dựa trên một module khác trong reactor.

### 13.3. Quy trình truy nguyên version

1. Xác định **POM module** đang build và những profile đang active.
2. Tìm artifact ở **`dependencies`** trực tiếp; xem có ghi version không.
3. Tìm managed entry ở POM module, parent và các BOM đã nhập.
4. Đối chiếu **groupId/artifactId/type/classifier**.
5. Nếu nhiều BOM overlap, xem thứ tự import và managed entry ghi đè.
6. Xem dependency bắc cầu có được kéo đến qua những nhánh nào; kiểm tra optional/exclusions.
7. Chạy `dependency:tree` để lấy version/scope thực tế.
8. Sau khi sửa, chạy `mvn clean verify` và test chức năng phù hợp.

Với dependency không thể tải, hãy phân biệt **lỗi version/model** với **lỗi repository/network/credentials**. Một managed version đúng nhưng artifact không tồn tại trong repository vẫn gây build thất bại khi artifact đó cần được giải quyết.

## 14. Lỗi hay gặp

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `package ... does not exist` dù đã khai báo trong dependencyManagement | Chỉ quản lý, chưa có dependency thật. | Thêm dependency vào `dependencies` của module cần dùng. |
| `dependency.version is missing` | Không có version trực tiếp và không có management phù hợp. | Khai báo version hoặc import/kế thừa đúng managed version. |
| Build dùng version khác phiên bản trong BOM mong đợi | Module có version trực tiếp, parent/management override hoặc BOM khác được chọn. | Xem effective POM, thứ tự import và dependency tree. |
| Module con có thêm thư viện dù không khai báo | Parent đặt thư viện trong **`dependencies`** và child kế thừa. | Cân nhắc chuyển policy sang `dependencyManagement` nếu không muốn ép mọi module. |
| Thêm BOM nhưng JUnit vẫn không nằm trên test classpath | BOM chỉ quản lý version, chưa khai báo `junit-jupiter` trong dependencies. | Thêm dependency `junit-jupiter` với scope test. |
| Import BOM vào sai chỗ | `scope=import` đặt trong dependencies thường hoặc thiếu `type=pom`. | Chuyển sang `dependencyManagement`, dùng `type=pom` + `scope=import`. |
| Version không được management áp dụng | Sai type/classifier, artifact hoặc POM/module/parent khác. | So khớp khóa `groupId:artifactId:type:classifier`; đọc effective POM. |
| Một plugin vẫn dùng dependency nội bộ khác version | Project dependencyManagement không chi phối plugin dependencies. | Kiểm tra cấu hình, version và dependencies riêng của plugin. |
| Sau khi loại dependency transitive, JVM lỗi | Exclusion/optional làm mất thư viện runtime cần thiết. | Xem graph, phân phối và classpath thực tế. |
| Artifact không tải được dù version được quản lý | Repository/mirror/credentials/network hoặc artifact chưa được phát hành. | Đọc lỗi resolution cụ thể, xác nhận repository và version tồn tại. |

### Một số kết luận sai cần tránh

**“dependencyManagement là danh sách thư viện ứng dụng được dùng.”** Sai: nó là danh sách quy tắc quản lý.

**“Muốn dùng Commons Lang phải ghi version ở dependencies dù parent đã có.”** Sai: version có thể được điền từ management.

**“Parent dependencies và parent dependencyManagement giống nhau.”** Sai: dependency thật có thể được child kế thừa và đi vào classpath; managed entry không tự tạo dependency.

**“BOM là một parent khác hoặc thêm mọi thư viện của framework vào project.”** Sai: BOM import đưa vào managed entries; module vẫn cần chọn dependency.

**“Management không ảnh hưởng dependency bắc cầu.”** Sai: nó có thể điều khiển version transitive khi artifact xuất hiện trong graph.

**“Tất cả managed versions luôn ép mọi version trực tiếp.”** Sai: dependency trực tiếp khai báo tường minh, mediation và management có những quy tắc ưu tiên khác nhau.

**“dependencyManagement quản lý cả Maven plugin dependencies.”** Sai: Maven phân biệt project dependencies với plugin internals.

**“Nếu effective POM có Commons Lang thì chắc chắn runtime classpath có nó.”** Sai: phải xem vị trí trong model và dependency tree, đồng thời còn phải bảo đảm launcher phân phối đúng JAR.

## 15. Checklist thiết kế quản lý dependency

1. Liệt kê thư viện **thật sự sử dụng** trong từng module.
2. Đặt version chung ở **parent `dependencyManagement`** hoặc BOM có kiểm soát.
3. Cho mỗi module tự khai báo các thư viện cần dùng ở **`dependencies`**.
4. Tránh lặp version đã được quản lý, trừ override có chủ đích và có test.
5. Đặt BOM import đúng vị trí, bảo đảm `type=pom`, `scope=import`.
6. Xem các BOM overlap và thứ tự import; không thay tùy ý.
7. Dùng `pluginManagement` để quản lý build plugins riêng, không dùng project dependencyManagement để cố kiểm soát plugin internals.
8. Tránh đưa library vào parent `dependencies` nếu không thực sự muốn mọi child kế thừa.
9. Kiểm tra dependency transitive, optional và exclusions trước khi ép version.
10. Chạy `help:effective-pom` và `dependency:tree` trên module quan trọng.
11. Chạy `mvn clean verify`, và kiểm tra ứng dụng với runtime classpath thực tế khi cần.
12. Tài liệu hóa các quyết định override và lộ trình nâng phiên bản tập trung.

### Bài thực hành

**Bài 1.** Build POM ở mục 4; xem `dependency:tree`. Kiểm tra `commons-lang3` có scope compile và `junit-jupiter` scope test, dù không ghi version ở dependency sử dụng.

**Bài 2.** Giữ Commons Lang trong management nhưng xóa khỏi `dependencies`; chạy `mvn clean compile`, giải thích lỗi thiếu `StringUtils`. Sau đó khôi phục.

**Bài 3.** Bỏ managed version của Commons Lang nhưng không ghi version trực tiếp; chạy validate, nhận diện lỗi version missing và khôi phục quản lý hợp lệ.

**Bài 4.** Tạo parent và hai module như mục 6. Cho `application` dùng Commons Lang còn `batch` không khai báo. So sánh tree từng module để thấy chỉ module cần dùng mới nhận thư viện.

**Bài 5.** Dùng JUnit BOM `5.10.2` và khai báo JUnit Jupiter ở dependencies không có version. Chạy test để xác nhận BOM cung cấp version chứ không tự thêm test framework.

**Bài 6.** Trong môi trường có hai BOM thật quản lý chung một artifact, thử thay thứ tự import trên project thử nghiệm và so sánh effective POM; không thay đổi policy production trước khi kiểm thử.

## 16. Tổng kết

**`dependencies` = thư viện module đang dùng. `dependencyManagement` = thông tin/chính sách dùng khi thư viện đó xuất hiện.**

Dự án nhỏ có thể đặt version trực tiếp trong dependencies. Khi có nhiều module, parent và BOM, đặt version ở management rồi để từng module chọn dependencies giúp dependency graph gọn, giảm lặp phiên bản và nâng cấp nhất quán. Đặc biệt, **quản lý version không đồng nghĩa bắt buộc sử dụng thư viện**.

Hãy xác minh bằng **`help:effective-pom`** (mô hình hiệu lực) và **`dependency:tree`** (graph thực sự) thay vì chỉ nhìn thấy một artifact trong POM và suy đoán nó đã nằm trên classpath.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Dependency Plugin — dependency:copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html)
