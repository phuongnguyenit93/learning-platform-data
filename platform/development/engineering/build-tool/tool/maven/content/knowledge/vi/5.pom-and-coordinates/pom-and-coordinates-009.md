# Đọc một POM tối thiểu và xác định phần có thể kế thừa trong Maven

## 1. Đọc POM theo ba câu hỏi: dự án nào, build ra gì, nhận cấu hình từ đâu?

**POM (Project Object Model)** là tệp **pom.xml** mô tả danh tính và cấu hình một dự án Maven. Thay vì liệt kê tuần tự từng lệnh shell, POM khai báo dự án, dependencies, plugins và những điều kiện để Maven thực hiện build lifecycle.

Khi gặp một POM, hãy xác định:

1. **Danh tính (coordinates)**: bộ **groupId:artifactId:version** của chính dự án, kèm **packaging**.
2. **Cấu hình của dự án**: dependencies, properties, build plugins và các thiết lập liên quan.
3. **Nguồn cấu hình kế thừa**: Super POM có sẵn trong Maven, **parent POM** được khai báo trong **<parent>**, và những cấu hình chỉ được kích hoạt qua **profiles**.

Hai POM trông ngắn như nhau có thể dẫn tới build khác nhau do parent, plugin management, Super POM và profiles đang hoạt động. Vì vậy, **đọc nguyên văn pom.xml** là bước đầu; để xác định giá trị cuối cùng Maven thực sự dùng, cần kiểm tra **effective POM**.

## 2. Một POM tối thiểu hợp lệ

Ví dụ **pom.xml** độc lập:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.learning</groupId>
    <artifactId>pom-reading-demo</artifactId>
    <version>1.0.0</version>
</project>
~~~

**Từng dòng có ý nghĩa gì?**

| Thành phần | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| **<project>** | Phần tử XML gốc | Bao toàn bộ mô hình Maven project; namespace và schema chỉ cách biểu diễn POM |
| **<modelVersion>** | **4.0.0** | Phiên bản mô hình POM XML; **khác** phiên bản ứng dụng và phiên bản Maven cài trên máy |
| **<groupId>** | **com.example.learning** | Nhóm/namespace sở hữu artifact; thường theo quy ước domain đảo chiều |
| **<artifactId>** | **pom-reading-demo** | Danh tính riêng của thành phần trong group |
| **<version>** | **1.0.0** | Phiên bản của artifact này |
| **<packaging>** (không khai báo) | Mặc định **jar** | Kiểu đóng gói và các default lifecycle bindings của dự án |

Tọa độ Maven của dự án là:

~~~text
com.example.learning:pom-reading-demo:1.0.0
~~~

Nếu sử dụng **packaging=jar** với quy ước tên mặc định, đầu ra sau khi chạy pha package thường là **target/pom-reading-demo-1.0.0.jar**. Tuy nhiên, **POM tối thiểu hợp lệ không chứng minh một chương trình Java 17 bất kỳ sẽ biên dịch thành công**: bản plugin compiler mặc định theo Maven có thể không phù hợp nếu dự án không cấu hình mức Java cần dùng. Cần cấu hình compiler và plugin versions cho nhu cầu thực tế.

**Không nhầm lẫn:**

- **modelVersion=4.0.0**: phiên bản cấu trúc POM, không có nghĩa đang dùng Maven **4.0.0**.
- **version=1.0.0**: phiên bản artifact, không phải phiên bản JDK hay plugin.
- **artifactId** khác tên thư mục Java package. Một dự án có thể dùng **com.example.learning** làm groupId nhưng code Java nằm trong package khác; dù vậy, nên chọn quy ước nhất quán.
- **<name>** là tên hiển thị tùy chọn, không thay thế **artifactId** trong tọa độ.
- Maven dùng **groupId, artifactId, version** để định danh artifact; trong POM có parent, **groupId** và **version** có thể được kế thừa và không cần nhắc lại trong child.

## 3. Những thứ POM tối thiểu không viết ra vẫn có tác dụng

Maven có một **Super POM** chứa các mặc định cơ bản. Maven cũng áp dụng các mặc định theo **packaging**, lifecycle và phiên bản các plugin được chọn. Vì vậy, POM không liệt kê **src/main/java**, **src/test/java** hoặc thư mục build **target** vẫn có thể dùng cấu trúc dự án Java chuẩn.

Các mặc định thường gặp:

- **packaging** mặc định là **jar** nếu không có khai báo khác.
- Thư mục nguồn sản phẩm: **src/main/java**; kiểm thử: **src/test/java**.
- Tài nguyên tương ứng: **src/main/resources**, **src/test/resources**.
- Đầu ra build thường nằm dưới **target/**.
- Repository mặc định bao gồm Maven Central trừ khi settings/repository policy thay đổi.
- Lifecycle cho **jar** thường ràng buộc các compiler/resource/test/jar plugin goals cần thiết.

Một POM thiếu **<build>** không có nghĩa không có quá trình build. Ngược lại, một POM có **<build>** cũng không đương nhiên chạy mọi plugin được liệt kê trong **<pluginManagement>**.

**Effective POM** là mô hình Maven đã tính toán sau khi hợp nhất POM hiện tại, parent, Super POM, cấu hình defaults và ảnh hưởng của các profiles đang active. File này thường dài hơn POM nguồn rất nhiều.

## 4. Ba lớp cần phân biệt: Super POM, parent POM, POM con

Có thể hình dung:

~~~text
Super POM (mặc định chung của Maven)
             |
             v
Parent POM của tổ chức/dự án (nếu được khai báo)
             |
             v
Child POM (cấu hình riêng và những giá trị ghi đè)
             |
             v
Effective POM của child (kết quả Maven tính ra)
~~~

- **Super POM**: được Maven áp dụng cho mô hình dự án; người viết không cần khai báo **<parent>** trỏ về Super POM.
- **Parent POM**: một Maven project có **packaging=pom**, khai báo qua thẻ **<parent>** trong POM con. Nó tập trung những quy tắc/phiên bản chung và những giá trị có thể được kế thừa.
- **Child POM**: mô tả một artifact cụ thể; có thể nhận **groupId/version**, properties và những cấu hình thích hợp từ parent, rồi bổ sung/ghi đè phần riêng.
- **Effective POM**: kết quả Maven dùng sau khi xử lý các lớp cấu hình liên quan; đây là công cụ kiểm chứng quan trọng nhất khi câu hỏi là “con thực sự nhận gì?”.

Đừng suy ra một child chỉ từ tên thư mục nằm bên dưới parent. Quan hệ kế thừa được xác định bằng **<parent>** và tọa độ của parent, không phải chỉ bằng cấu trúc filesystem.

## 5. Những phần được kế thừa và những phần không được kế thừa

Các nhóm giá trị trong POM thường được phân loại như sau:

| Thẻ/nhóm cấu hình | Child có kế thừa? | Cách hiểu khi đọc |
| --- | --- | --- |
| **groupId** | **Có**, nếu child không khai báo | Tọa độ groupId của child có thể đến từ parent |
| **version** | **Có**, nếu child không khai báo | Phiên bản artifact của child có thể bằng version parent |
| **artifactId** | **Không** | Child phải có artifactId riêng; artifactId của parent trong **<parent>** dùng để tìm parent |
| **name** | **Không** theo quy tắc kế thừa thông thường | Có thể khai báo tên hiển thị riêng cho child |
| **packaging** | Không tự kế thừa packaging của parent; child mặc định **jar** khi không khai báo | Parent thường **pom**, child thường **jar/war** |
| **properties** | **Có** | Child có thể dùng hoặc ghi đè các key properties |
| **dependencyManagement** | **Có** | Child nhận quy tắc quản lý phiên bản/scope cho dependencies được dùng |
| **dependencies** | **Có**, hợp nhất theo quy tắc Maven | Dependency trực tiếp trong parent có thể áp dụng cho child |
| **build / plugins / pluginManagement** | **Có** theo quy tắc hợp nhất, kế thừa của từng plugin/execution | Child có thể nhận cấu hình/version; cờ **<inherited>false</inherited>** có thể ngăn một số phần truyền xuống |
| **repositories / pluginRepositories** | **Có** | Có thể ảnh hưởng nơi Maven phân giải artifact/plugin |
| **reporting** | **Có** theo quy tắc hợp nhất | Các báo cáo/site configuration có thể truyền xuống |
| **description, url, licenses, developers, scm...** | Nhiều phần **có** | Metadata có thể được thừa hưởng và đôi khi được điều chỉnh URL tương đối |
| **profiles** | **Định nghĩa profile không tự kế thừa**; tác động của profile đang active từ parent có thể được áp dụng | Cần xem active profiles, không chỉ tìm cùng tên profile trong child |
| **modules** | **Không tạo quan hệ kế thừa** | Đây là tập đường dẫn các dự án được gom vào reactor build; xem mục aggregation |

Bảng là quy tắc thực hành để đọc **POM mô hình Maven 4.0.0**, không phải lời cam kết rằng mọi child đều nhận nguyên xi từng XML node. Với danh sách, plugin execution hay các XML configuration lồng nhau, Maven có quy tắc merge và override; một số plugin/execution có thể tắt kế thừa.

**Điểm then chốt:** thẻ **<parent>** quyết định nguồn kế thừa; thẻ **<modules>** phục vụ gom project khi build. Chúng thường xuất hiện cùng lúc nhưng là hai khái niệm khác nhau.

## 6. Đọc một bộ parent/child POM hoạt động được

Ví dụ dưới đây dùng **Maven 3.9+** và **JDK 17+**. Mục tiêu là khóa cấu hình Java và phiên bản test/plugin ở parent, còn child tự khai báo artifact và những dependencies thực sự cần dùng.

Cấu trúc:

~~~text
sample-workspace/
├── pom.xml                         # parent POM và aggregator
└── lesson-core/
    ├── pom.xml                     # child POM
    └── src/
        ├── main/java/com/example/lesson/
        │   └── App.java
        └── test/java/com/example/lesson/
            └── AppTest.java
~~~

### 6.1. Parent POM: sample-workspace/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.learning</groupId>
    <artifactId>sample-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>lesson-core</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
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
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
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
~~~

**Đọc parent từ trên xuống:**

- **com.example.learning:sample-parent:1.0.0** định danh artifact POM cha. **packaging=pom** nghĩa parent không tự đóng gói một JAR sản phẩm như module Java.
- **<modules><module>lesson-core</module></modules>** khiến lệnh Maven chạy ở thư mục gốc có thể build module **lesson-core** trong reactor. Nó là **aggregation**.
- **maven.compiler.release=17** và encoding UTF-8 là properties mà child có thể nhận. Khi compiler plugin được kích hoạt bởi lifecycle phù hợp, nó có thể sử dụng property **maven.compiler.release**.
- **dependencyManagement** đặt quy tắc cho JUnit Jupiter **5.11.4** với **scope=test**. Đây chưa phải lệnh thêm JUnit làm dependency trực tiếp cho mọi child.
- **pluginManagement** đặt phiên bản các plugin compiler, Surefire, JAR. Các plugin thuộc default lifecycle của **packaging=jar** sẽ được hưởng cấu hình quản lý tương ứng; plugin khác chỉ được quản lý phiên bản khi được khai báo/kích hoạt đúng cách.

Trong parent không có **<dependencies>** nên ví dụ không ép mọi child phải mang JUnit. Điều đó quan trọng nếu sau này có nhiều module, một số module không có test JUnit.

### 6.2. Child POM: sample-workspace/lesson-core/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.learning</groupId>
        <artifactId>sample-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>lesson-core</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

**Giải thích từng điểm quan trọng:**

1. **<parent>** chỉ đến **com.example.learning:sample-parent:1.0.0**. Đây là *tọa độ parent*, không phải tọa độ của child.
2. Child có **<artifactId>lesson-core</artifactId>**. Đây là artifactId **của chính child**, bắt buộc không thừa hưởng artifactId parent.
3. Child không khai báo **<groupId>** và **<version>** trực tiếp, nên nhận lần lượt **com.example.learning** và **1.0.0** từ parent.
4. Child không ghi **<packaging>**, nên dùng default **jar**; nó không tự biến thành **pom** chỉ vì parent đóng gói kiểu pom.
5. Child khai báo JUnit trong **<dependencies>** mà không ghi version/scope. Bản khai báo **dependencyManagement** ở parent cung cấp **version=5.11.4** và **scope=test** phù hợp.
6. Các plugin compiler, Surefire và JAR được quản lý phiên bản ở parent. Default lifecycle của kiểu **jar** tham chiếu các plugin tương ứng để biên dịch, chạy test và đóng gói.
7. Child thừa hưởng property **maven.compiler.release=17**, dù không lặp lại cấu hình Java trong POM của mình.

Vì thế, **tọa độ cuối cùng của child** là:

~~~text
com.example.learning:lesson-core:1.0.0
~~~

Còn **tọa độ parent** vẫn là:

~~~text
com.example.learning:sample-parent:1.0.0
~~~

Hai artifact khác nhau, dù cùng groupId và version.

### 6.3. Mã Java 17 và kiểm thử minh họa

Tạo **lesson-core/src/main/java/com/example/lesson/App.java**:

~~~java
package com.example.lesson;

public final class App {
    private App() {
    }

    public static String message() {
        return "POM inheritance works";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Tạo **lesson-core/src/test/java/com/example/lesson/AppTest.java**:

~~~java
package com.example.lesson;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void inheritsTestDependencyConfiguration() {
        assertEquals("POM inheritance works", App.message());
    }
}
~~~

Mã trên biên dịch với Java 17 khi dependencies/plugins được Maven phân giải thành công. **App.java** không import JUnit; **AppTest.java** có JUnit nhờ dependency của child và management từ parent.

Từ thư mục **sample-workspace/** chạy:

~~~bash
mvn -version
mvn clean verify
~~~

Lệnh này xử lý **sample-parent** rồi **lesson-core** trong reactor. Với các file và cấu hình đã nêu, Surefire chạy **1 test JUnit** và có **0 failures, 0 errors**; text log có thể thay đổi theo Maven/JDK/platform.

Chạy class sản phẩm từ thư mục gốc:

~~~bash
java -cp lesson-core/target/classes com.example.lesson.App
~~~

**Stdout chính xác:**

~~~text
POM inheritance works
~~~

Kiểm tra JAR vừa đóng gói:

~~~bash
jar tf lesson-core/target/lesson-core-1.0.0.jar
~~~

Trong danh sách sẽ có **com/example/lesson/App.class**; JAR sản phẩm mặc định **không** chứa **AppTest.class** hoặc các thư viện test JUnit. Không dùng **java -jar** ở đây vì ví dụ chưa đặt **Main-Class** trong manifest. Với ví dụ này, **java -cp** là cách chạy được chỉ rõ.

**Kết quả cần rút ra:** child kế thừa phần cấu hình có thể dùng chung, nhưng tự giữ tên artifact, dependency trực tiếp và mã nguồn riêng.

## 7. Bẫy quan trọng: dependencyManagement không tự thêm dependency

Hai đoạn XML trông gần giống nhau nhưng tác dụng khác hẳn.

**Parent quản lý phiên bản (không tự thêm dependency cho child):**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**Child chủ động sử dụng dependency đã được quản lý:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
~~~

Chỉ khi child khai báo dependency (hoặc gặp nó theo đường dependency phù hợp), các quy tắc trong dependencyManagement mới có cơ hội tác động. **dependencyManagement** không tương đương một lời khai báo “hãy thêm JUnit vào classpath của mọi child”.

Ngược lại, nếu parent đặt JUnit trực tiếp trong **<dependencies>**, cấu hình đó có thể được kế thừa làm dependency của child. Điều này đôi khi cần thiết, nhưng thường không phù hợp nếu các child khác nhau cần các bộ thư viện riêng.

| Vị trí khai báo | Child nhận gì? | Hệ quả |
| --- | --- | --- |
| Parent **dependencies** | Dependency được kế thừa theo quy tắc hợp nhất | Có thể xuất hiện trong cây dependency của child dù child không khai báo lại |
| Parent **dependencyManagement** | Quy tắc về version/scope/exclusion v.v. | Child vẫn chọn dependency nào muốn dùng |
| Child **dependencies** | Dependency trực tiếp của child | Có thể bỏ version khi đã được quản lý hợp lệ |
| Child **dependencyManagement** | Quy tắc riêng, có thể ghi đè management kế thừa | Dùng khi child cần điều chỉnh chính sách version trong phạm vi của nó |

**Lưu ý:** **scope=import** của dependency loại **pom** bên trong dependencyManagement dùng để nhập tập managed dependencies (BOM); đó là *dependency management import*, không phải inheritance từ một **<parent>** khác. Một child chỉ có một parent POM trực tiếp, trong khi có thể nhập nhiều BOM nếu mô hình/cấu hình hợp lệ. BOM import cũng không tự cho child kế thừa pluginManagement, modules hoặc properties tùy ý của BOM.

## 8. Bẫy tương tự: pluginManagement không đồng nghĩa kích hoạt plugin

Maven phân biệt:

- **<build><plugins>**: danh sách plugin được khai báo cho bản build; execution/configuration có thể được kế thừa, trừ trường hợp tắt kế thừa.
- **<build><pluginManagement>**: nơi quản lý phiên bản/cấu hình plugin để áp dụng khi plugin thực sự tham gia build. Nó không tự ép mọi plugin lạ phải chạy chỉ vì đã được nhắc trong management.

Ví dụ parent chỉ quản lý phiên bản:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-checkstyle-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

**Chỉ có đoạn trên, không có nghĩa Checkstyle tự chạy tại pha verify.** Để đưa plugin đó vào một lifecycle phase, child cần khai báo plugin và execution tương ứng:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-checkstyle-plugin</artifactId>
            <executions>
                <execution>
                    <id>check-style</id>
                    <phase>verify</phase>
                    <goals>
                        <goal>check</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Hai đoạn XML này minh họa **cấu hình bổ sung** cho parent và child tương ứng, không phải một chương trình Java. Plugin có thể được tải khi mục tiêu được chạy, và phần goal **check** có thể cần thêm Checkstyle rules/configuration hợp lệ trong dự án thực tế.

Riêng các plugin như compiler, Surefire và JAR trong ví dụ **lesson-core** được **default lifecycle của packaging=jar** ràng buộc, nên management ở parent có thể tác động tới những plugin đang được lifecycle sử dụng dù child không liệt kê thủ công mọi plugin đó. Đây là lý do phải phân biệt **default binding** với **kích hoạt một plugin tùy ý**.

Nếu một plugin của parent không nên đi xuống child, có thể đặt **<inherited>false</inherited>** cho plugin hoặc execution phù hợp. Cấu hình plugin lồng nhau có quy tắc merge/override riêng; không được giả định mọi danh sách XML chỉ đơn giản nối tiếp nhau.

## 9. Kế thừa khác với aggregation: <parent> và <modules>

Giả sử POM gốc chứa:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>lesson-core</module>
    <module>lesson-api</module>
</modules>
~~~

Đây là **aggregation**: Maven reactor xây dựng các module được chỉ ra trong cùng một phiên build và có thể sắp xếp chúng theo quan hệ dependency. Nó **không tự tạo quan hệ kế thừa** cho từng module.

Phân biệt:

| Kiểu quan hệ | Được khai báo ở đâu? | Mục đích |
| --- | --- | --- |
| **Inheritance** | Child có **<parent>...</parent>** | Child nhận những cấu hình có thể kế thừa từ parent |
| **Aggregation** | Aggregator có **<modules><module>...</module></modules>** | Gộp các dự án vào cùng Maven reactor build |
| **Dependency** | Project có **<dependencies>** | Một artifact cần dùng API hoặc runtime artifact khác |

Ba quan hệ này độc lập về ý nghĩa. Thực tế một POM gốc có thể đồng thời đóng vai trò parent và aggregator như ví dụ; tuy nhiên:

- Dự án được liệt kê trong **<modules>** chưa chắc kế thừa POM gốc.
- Dự án khai báo **<parent>** có thể ở repository khác và không cần xuất hiện trong **<modules>** của parent.
- **<modules>** cũng không có nghĩa project con phụ thuộc runtime vào nhau. Mỗi module vẫn phải khai báo dependencies nếu cần dùng artifact khác.
- **packaging=pom** thường dùng cho parent/aggregator, trong khi module Java có thể dùng **jar**, **war** hoặc packaging phù hợp.

Một lỗi phổ biến là nhìn thấy **<module>lesson-core</module>** rồi kết luận child đã nhận groupId/version/plugin configuration. Hãy mở **lesson-core/pom.xml** và tìm **<parent>** trước khi kết luận.

## 10. Cách Maven tìm parent POM và lỗi relativePath

Child tham chiếu parent bằng tọa độ trong **<parent>**. Maven cần phân giải POM cha hợp lệ; Maven 3 thường kiểm tra đường dẫn tương đối **../pom.xml** theo mặc định, rồi kho cục bộ/kho từ xa theo cơ chế phân giải thích hợp khi không tìm được parent phù hợp.

Với cấu trúc ví dụ:

~~~text
sample-workspace/pom.xml
sample-workspace/lesson-core/pom.xml
~~~

Child có thể bỏ **<relativePath>** vì **../pom.xml** trỏ đúng đến parent và tọa độ khớp.

Nếu parent nằm ở một thư mục khác, có thể khai báo đường dẫn rõ:

~~~xml
<parent>
    <groupId>com.example.learning</groupId>
    <artifactId>sample-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../build-parent/pom.xml</relativePath>
</parent>
~~~

Đây là minh họa cho **cấu trúc thư mục thay thế**, không phải sửa cho ví dụ **sample-workspace** ở trên.

Nếu muốn phân giải parent hoàn toàn qua repository thay vì sử dụng đường dẫn filesystem mặc định của Maven 3, có thể khai báo **<relativePath/>** rỗng, sau đó bảo đảm parent POM đã được install/deploy đến nơi Maven truy cập được.

Khi gặp lỗi **Non-resolvable parent POM**, kiểm tra theo thứ tự:

1. Tọa độ **parent.groupId / parent.artifactId / parent.version** trong child có đúng với parent thật không?
2. Nếu parent ở gần: **relativePath** có trỏ tới **pom.xml** đúng không?
3. Nếu parent được công bố: nó có tồn tại trong repository truy cập được, và settings/credentials đã đúng chưa?
4. Có nhầm version parent, snapshot/release, offline mode hoặc mirror không?
5. Parent POM có **packaging=pom** và cấu trúc hợp lệ không?

Không nên “sửa nhanh” bằng cách copy toàn bộ properties/plugins từ parent vào child trước khi biết lỗi phân giải parent nằm ở đâu. Việc copy sẽ tạo hai nguồn cấu hình khó duy trì.

## 11. Effective POM: cách xác minh giá trị kế thừa thật sự

Đọc từng file XML chỉ cho biết nguồn khai báo. Để xem Maven thực sự hợp nhất chúng thế nào, dùng **Maven Help Plugin**.

Từ thư mục chứa POM của child:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml -Dverbose
~~~

Hoặc từ thư mục gốc ví dụ:

~~~bash
mvn -f lesson-core/pom.xml help:effective-pom -Doutput=effective-pom.xml -Dverbose
~~~

Tham số **-Doutput** lưu effective POM vào file để tìm kiếm; tùy working directory và cách Maven/plugin giải quyết đường dẫn, hãy kiểm tra nơi file được báo tạo. **-Dverbose** thêm chú thích nguồn gốc của từng phần tử khi phiên bản Maven Help Plugin hỗ trợ.

Khi đọc effective POM của **lesson-core**, hãy tìm:

- **groupId=com.example.learning**, **artifactId=lesson-core**, **version=1.0.0**.
- **packaging=jar**.
- **maven.compiler.release=17** và **project.build.sourceEncoding=UTF-8**.
- **junit-jupiter** xuất hiện trong **dependencies** của child với phiên bản/scope đã được management giải quyết.
- **maven-compiler-plugin**, **maven-surefire-plugin**, **maven-jar-plugin** được quản lý phiên bản; chúng xuất hiện ở vị trí phù hợp với mô hình effective/lifecycle.
- Các cấu hình bổ sung từ Super POM hoặc profiles đang active.

Để hỏi một giá trị cụ thể (không cần xem toàn bộ XML):

~~~bash
mvn -f lesson-core/pom.xml help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn -f lesson-core/pom.xml help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn -f lesson-core/pom.xml help:evaluate -Dexpression=project.version -q -DforceStdout
mvn -f lesson-core/pom.xml help:evaluate -Dexpression=project.packaging -q -DforceStdout
~~~

Giá trị kỳ vọng theo từng lệnh:

~~~text
com.example.learning
lesson-core
1.0.0
jar
~~~

Khối trên mô tả **bốn giá trị mong đợi theo thứ tự**, không phải stdout của một lệnh duy nhất. Maven Help Plugin có thể phải được tải ở lần chạy đầu; log Maven và định dạng đầu ra thay đổi theo cấu hình.

**Không lưu effective-pom.xml như bản chính để chỉnh sửa**: đó là đầu ra chẩn đoán. Nguồn khai báo của dự án vẫn là các POM, settings và profiles có hiệu lực. Nếu sinh file trong thư mục dự án, có thể xóa file chẩn đoán sau khi xem, theo quy tắc Git của nhóm.

## 12. Profiles và thứ tự ghi đè cần chú ý

Parent có thể khai báo **<profiles>** để áp dụng điều kiện build theo JDK, OS hoặc property. Tuy nhiên, **định nghĩa profile không được thừa hưởng giống các phần tử POM thông thường**; những thay đổi trong model do một profile đang active của parent tạo ra có thể đi vào cấu hình hiệu lực của child.

Ví dụ profile minh họa:

~~~xml
<profiles>
    <profile>
        <id>strict-checks</id>
        <activation>
            <property>
                <name>strictChecks</name>
            </property>
        </activation>
        <properties>
            <some.validation.mode>strict</some.validation.mode>
        </properties>
    </profile>
</profiles>
~~~

Khi **strictChecks** được kích hoạt theo cấu hình thích hợp, hiệu ứng property có thể xuất hiện trong effective POM. Nếu không active, không nên giả định property ấy đã có chỉ vì thấy profile trong parent.

Kiểm tra những profile đang active:

~~~bash
mvn -f lesson-core/pom.xml help:active-profiles
~~~

Lệnh này là công cụ chẩn đoán; ví dụ **sample-workspace** chính ở trên không định nghĩa profile. Vì vậy không có profile tùy chỉnh **strict-checks** nào tự xuất hiện trừ khi người đọc bổ sung đoạn XML minh họa.

Khi child ghi đè property đã kế thừa, giá trị hiệu lực thường theo child. Với dependency management và plugin configuration phức tạp, phải nhìn POM cuối cùng thay vì suy luận một quy tắc chung duy nhất cho mọi XML node.

## 13. Quy trình đọc POM tối thiểu trong một repository lạ

Đi theo trình tự sau để vừa nhanh vừa chính xác:

1. **Xác định POM đang đọc.** Ghi lại vị trí **pom.xml**, phiên bản Maven/JDK dùng trong dự án và trạng thái profile.
2. **Tìm <modelVersion>**. Đối với dự án Maven 3 dùng POM 4.0.0, giá trị này là **4.0.0**, không phải bản Maven.
3. **Tìm <groupId>, <artifactId>, <version>, <packaging>**. Nếu thiếu groupId/version trong child, chuyển ngay sang **<parent>**; nếu thiếu packaging, nghĩ tới default **jar** thay vì tự lấy packaging parent.
4. **Nếu có <parent>**, đọc đủ tọa độ và **relativePath**, xác nhận parent POM giải quyết được.
5. **Tìm các trường kế thừa phổ biến**: properties, dependencyManagement, dependencies, pluginManagement, plugins, repositories, reporting.
6. **Phân biệt management với sử dụng thực tế**: một dependency trong management có được khai báo trong dependencies không; một plugin được quản lý phiên bản có được lifecycle hoặc plugin execution kích hoạt không?
7. **Kiểm tra <modules>**, nếu có: đây là danh sách aggregation, không đủ để kết luận quan hệ parent.
8. **Sinh effective POM cho chính child** và đọc các giá trị cuối cùng; dùng **help:evaluate** nếu chỉ cần tọa độ.
9. **Thực thi build phù hợp**, chẳng hạn **mvn clean verify**, để xác nhận model, plugin và dependencies cùng hoạt động; POM hợp lệ về XML chưa đủ chứng minh source Java hoặc test đều đúng.
10. **Nếu hành vi không khớp**, kiểm tra active profiles, parent khác phiên bản, BOM import, property override và môi trường CLI/settings.

Một ví dụ cần tập trung nhận diện:

~~~xml
<parent>
    <groupId>com.example.learning</groupId>
    <artifactId>sample-parent</artifactId>
    <version>1.0.0</version>
</parent>
<artifactId>lesson-core</artifactId>
~~~

Suy ra **groupId/version** của child từ parent là hợp lý khi parent phân giải đúng; **artifactId** của child là **lesson-core** vì được ghi riêng. Không được đọc thành **sample-parent** chỉ vì đó là artifactId xuất hiện trước trong XML.

## 14. Những lỗi đọc và tổ chức POM thường gặp

**Lỗi: tưởng version trong <parent> luôn là phiên bản duy nhất con phải có.** Parent version là tọa độ dùng để tìm parent; child có thể khai báo **<version>** riêng, hoặc bỏ đi để kế thừa parent.version. Đọc effective POM để biết version thật của child.

**Lỗi: tưởng <modules> tự làm child kế thừa.** Aggregator quyết định những project tham gia reactor; inheritance chỉ có khi child khai báo **<parent>** hợp lệ.

**Lỗi: copy cùng một plugin version sang mọi POM.** Dễ khiến các module dùng plugin khác nhau ngoài ý muốn. Đặt versions chung trong parent **pluginManagement** rồi xác định plugin nào được lifecycle/execution sử dụng.

**Lỗi: đặt dependencies dùng riêng của một child vào parent <dependencies>.** Có thể kéo dependency sang cả các child không cần. Dùng **dependencyManagement** để quản lý phiên bản, để từng child khai báo dependency trực tiếp.

**Lỗi: nghĩ pluginManagement tự kích hoạt mọi plugin.** Quản lý cấu hình không tự tạo execution. Phải có lifecycle binding hoặc khai báo plugin/execution phù hợp.

**Lỗi: nghĩ child không ghi packaging tức là packaging=pom như parent.** Mặc định của child là **jar**; nếu muốn một child là parent/aggregator riêng, cần khai báo **<packaging>pom</packaging>**.

**Lỗi: build thất bại vì parent không tìm được.** Kiểm tra tọa độ/relativePath/repository thay vì đoán lỗi dependencies của application code.

**Lỗi: đọc POM nguồn và bỏ qua Super POM/profiles.** Điều đó có thể bỏ sót default plugin/repository hoặc các giá trị kích hoạt theo môi trường. Dùng **help:effective-pom -Dverbose** và **help:active-profiles**.

**Lỗi: đóng gói kết quả từ một POM tối thiểu rồi nghĩ Maven bảo đảm đúng Java version.** Cần cấu hình compiler release/JDK và plugin versions tương thích; chỉ POM hợp lệ không đủ để bảo đảm build thành công.

**Lỗi: chỉnh trực tiếp effective-pom.xml.** File này được sinh cho chẩn đoán. Sửa nguồn trong parent/child POM theo quyền sở hữu cấu hình của nhóm.

## 15. Bài tập tự kiểm tra

Đọc POM con sau, giả sử parent **com.example:base-parent:2.4.0** tồn tại, khai báo **groupId=com.example**, **version=2.4.0**, **packaging=pom**, property **java.level=17**, và chỉ có **dependencyManagement** quản lý JUnit Jupiter **5.11.4**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>base-parent</artifactId>
        <version>2.4.0</version>
    </parent>
    <artifactId>order-api</artifactId>
    <properties>
        <java.level>21</java.level>
    </properties>
</project>
~~~

**Đáp án:**

- Tọa độ child: **com.example:order-api:2.4.0**. Tên artifact **order-api** thuộc child; **base-parent** là tên artifact parent.
- Packaging child: **jar** theo mặc định, không phải **pom**.
- Property **java.level** trong child là **21**, vì child ghi đè property **17** từ parent. Đây chỉ là một key do người dùng đặt: **java.level=21** không tự đổi compiler release nếu build không tham chiếu key này.
- JUnit Jupiter **chưa tự trở thành dependency trực tiếp** của child chỉ vì parent có dependencyManagement.
- Nếu parent có **<modules>order-api</modules>**, đó là aggregation, và không thay đổi các kết luận inheritance kể trên.
- Để xác nhận môi trường Maven thực tế, dùng **help:effective-pom** và các mục **help:evaluate** tương ứng.

Đọc POM chính xác nghĩa là tách **giá trị được khai báo trong file đang mở**, **giá trị có thể kế thừa từ parent/Super POM**, và **giá trị cuối cùng của effective POM**. Khi nắm được ba lớp này, bạn có thể xác định đúng tọa độ artifact, tránh cấu hình lặp và giải thích vì sao Maven build mỗi module theo cách khác nhau.

## Tài liệu tham khảo

- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
