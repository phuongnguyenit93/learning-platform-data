# Điều khiển hợp nhất cấu hình Maven plugin bằng combine.self và combine.children

## 1. Vì sao phải điều khiển việc ghép cấu hình plugin?

Trong hệ thống Maven nhiều module, parent POM thường quy định cấu hình chung cho Compiler, Surefire, Resources, JAR hoặc các plugin kiểm tra chất lượng. Một module con có thể cần thêm một option vào danh sách parent, chỉ đổi một tham số hoặc thay toàn bộ một nhánh cấu hình. Nếu chưa hiểu cách Maven hợp nhất XML, kết quả có thể khác ý định: một item của cha bị mất, một task lặp hai lần, hay cấu hình Java bắt buộc vô tình bị override.

Maven có hai thuộc tính XML quan trọng đặt **trên một phần tử trong cấu hình plugin**:

- `combine.children="append"`: giữ các phần tử con của parent rồi nối thêm các phần tử con của child.
- `combine.self="override"`: thay toàn bộ **nhánh tương ứng** của parent bằng nhánh được khai trong child.

Khi **không khai hai thuộc tính**, mặc định Maven dùng cách merge theo **tên phần tử XML**. Có thể viết tường minh `combine.children="merge"` hoặc `combine.self="merge"` nhưng trong thực tế thường không cần.

Đây là **hướng dẫn cho Maven model merger**, không phải tham số riêng của một plugin. Compiler Plugin không có “chức năng append” đặc biệt; chính Maven ghép XML trước khi plugin nhận cấu hình có hiệu lực.

### Sau bài học bạn sẽ làm được gì?

1. Phân biệt quan hệ parent–child và reactor aggregation, điều kiện để cấu hình plugin thực sự được kế thừa.
2. Dự đoán kết quả merge mặc định theo tên phần tử.
3. Dùng `combine.children="append"` cho danh sách có thể nối và `combine.self="override"` cho nhánh cần thay.
4. Hiểu thứ tự parent → child khi append, không tự loại trùng và không tự áp dụng đệ quy xuống node cháu.
5. Hiểu vì sao dùng cả hai trên cùng phần tử thì override thắng; vì sao combine hint có thể được kế thừa xuống POM cháu.
6. Phân biệt combine với `<inherited>false</inherited>`, `pluginManagement`, `execution id`, lifecycle goal và Maven property.
7. Tạo dự án **Maven 3.9.x, Java 17 và JUnit 5** với POM cha/con, sử dụng AntRun Plugin để quan sát ba kiểu merge qua file marker.
8. Kiểm chứng bằng `help:effective-pom`, log Maven và kết quả build sạch, nhận diện lỗi và sửa ở đúng nhánh.

## 2. Cơ chế hợp nhất diễn ra ở đâu?

Maven xây dựng **effective POM** của mỗi project từ POM gốc, parent, pluginManagement, cấu hình project hiện tại và ảnh hưởng của những profile đang hoạt động.

Ví dụ:

~~~text
merge-demo/
├── pom.xml           parent POM + aggregator
└── app/
    ├── pom.xml       child POM (packaging=jar)
    └── src/
        ├── main/java/vn/example/merge/App.java
        └── test/java/vn/example/merge/AppTest.java
~~~

Parent có thể khai `<modules><module>app</module></modules>` để reactor build app. **Chỉ có modules chưa tạo POM inheritance**: trong `app/pom.xml` phải khai `<parent>` trỏ đúng parent. Khi parent và child có cùng plugin, Maven có thể hợp nhất cấu hình từ hai cấp.

Một plugin được xác định bằng tọa độ như:

~~~text
org.apache.maven.plugins:maven-antrun-plugin:3.1.0
~~~

Khi có cùng `groupId:artifactId` ở parent và child, Maven hợp nhất plugin theo quy tắc của mô hình. `<version>` có thể được inherited hoặc quản lý từ `pluginManagement`. Nếu plugin có các executions, **`<execution><id>`** được dùng để ghép execution tương ứng.

### Các tầng nên phân biệt

| Tầng | Cơ chế | Câu hỏi |
| --- | --- | --- |
| Aggregation | `<modules>` | Dự án nào có mặt trong reactor? |
| POM inheritance | `<parent>` | Module con nhận cấu hình nào từ POM cha? |
| Plugin identity | `groupId:artifactId` | Đây là cùng plugin hay plugin khác? |
| Plugin management | `<pluginManagement>` | Version và config plugin được quản lý thế nào? |
| Execution merge | `<execution><id>` | Có đang sửa cùng execution hay tạo execution mới? |
| XML configuration merge | `combine.self`, `combine.children` | Các nhánh cấu hình cha/con được ghép ra sao? |
| Goal execution | `phase`, `goal` hoặc lệnh CLI | Plugin có thực sự chạy không? |

**Đừng nhầm:** một `<configuration>` có mặt trong effective POM không chứng minh goal đã chạy. Phải xem phase, execution và log.

## 3. Merge mặc định: cùng tên thì child ưu tiên, không trùng thì parent còn

Xem một ví dụ **XML minh họa**, chưa gắn vào plugin cụ thể.

Parent:

~~~xml
<configuration>
    <items>
        <item>parent-1</item>
        <item>parent-2</item>
    </items>
    <properties>
        <parentKey>parent</parentKey>
    </properties>
</configuration>
~~~

Child:

~~~xml
<configuration>
    <items>
        <item>child-1</item>
    </items>
    <properties>
        <childKey>child</childKey>
    </properties>
</configuration>
~~~

Kết quả merge mặc định cho các nhánh này:

~~~xml
<configuration>
    <items>
        <item>child-1</item>
    </items>
    <properties>
        <childKey>child</childKey>
        <parentKey>parent</parentKey>
    </properties>
</configuration>
~~~

Vì sao?

- Node `items` có ở cả parent và child. `item` của child được ưu tiên theo quy tắc merge theo tên; hai `item` parent **không được tự động nối** vào danh sách.
- `childKey` chỉ ở child nên còn trong kết quả.
- `parentKey` chỉ ở parent nên vẫn được giữ.

Giá trị `parent-1` hay `child-1` **không phải khóa so trùng**. Maven giải quyết phần này như XML DOM theo tên phần tử, không tự hiểu “danh sách tác vụ”, “bộ cờ compiler” hay “danh sách resources”.

### Ví dụ với tham số Compiler Plugin

Parent:

~~~xml
<configuration>
    <release>17</release>
    <showWarnings>true</showWarnings>
</configuration>
~~~

Child:

~~~xml
<configuration>
    <showWarnings>false</showWarnings>
</configuration>
~~~

Kết quả:

~~~xml
<configuration>
    <release>17</release>
    <showWarnings>false</showWarnings>
</configuration>
~~~

Đây là trường hợp merge mặc định **rất hợp lý**: child thay một option nhưng giữ `release=17` do parent quy định.

**Lưu ý:** `items`/`properties` ở ví dụ đầu là tên giả để giải thích cơ chế XML, không phải tham số được bảo đảm tồn tại trong Maven Compiler Plugin.

## 4. combine.children="append": nối các phần tử con trực tiếp

Để giữ cả danh sách parent lẫn child, đặt attribute trong **child POM** tại node muốn ghép:

~~~xml
<configuration>
    <items combine.children="append">
        <item>child-1</item>
    </items>
</configuration>
~~~

Khi parent có hai item như ở mục 3, kết quả:

~~~xml
<configuration>
    <items combine.children="append">
        <item>parent-1</item>
        <item>parent-2</item>
        <item>child-1</item>
    </items>
</configuration>
~~~

Quy tắc:

1. **Parent children trước, child children sau.**
2. Các phần tử **con trực tiếp** được nối làm siblings, không tự khử phần tử trùng nội dung.
3. Attribute ảnh hưởng **nhánh chứa nó**, không tự chuyển toàn bộ nested XML thành append.
4. Một plugin có thể không chấp nhận nhiều phần tử sau khi append nếu parameter chỉ cho phép một giá trị; cần đọc docs của plugin.

### Ví dụ thực với Compiler Plugin

Parent:

~~~xml
<compilerArgs>
    <arg>-Xlint:deprecation</arg>
</compilerArgs>
~~~

Child:

~~~xml
<compilerArgs combine.children="append">
    <arg>-Xlint:unchecked</arg>
</compilerArgs>
~~~

Phần merged configuration chứa:

~~~xml
<compilerArgs combine.children="append">
    <arg>-Xlint:deprecation</arg>
    <arg>-Xlint:unchecked</arg>
</compilerArgs>
~~~

Compiler Plugin nhận cả hai option, khi tham số `compilerArgs` được dùng đúng cách. Nếu child cũng thêm `-Xlint:deprecation`, nó có thể xuất hiện **hai lần**; Maven không tự loại trùng do nội dung text giống nhau.

### Khi nào append là lựa chọn đúng?

Phù hợp cho một danh sách plugin-specific mà việc thêm mục **có chủ đích và an toàn**: compiler flags, danh sách resource filters hoặc một tập Ant tasks. Không dùng append cho một nhánh mà plugin mong đợi chỉ chứa một mục duy nhất; XML hợp lệ chưa chắc plugin hiểu đúng.

## 5. combine.self="override": thay toàn bộ nhánh được đánh dấu

Parent:

~~~xml
<configuration>
    <properties>
        <parentKey>parent</parentKey>
        <sharedKey>old</sharedKey>
    </properties>
    <otherSetting>kept</otherSetting>
</configuration>
~~~

Child:

~~~xml
<configuration>
    <properties combine.self="override">
        <childKey>child</childKey>
    </properties>
</configuration>
~~~

Kết quả:

~~~xml
<configuration>
    <properties combine.self="override">
        <childKey>child</childKey>
    </properties>
    <otherSetting>kept</otherSetting>
</configuration>
~~~

`combine.self="override"` ở `properties` loại toàn bộ **nội dung properties của parent** và giữ nhánh child. Nhưng `otherSetting` là **node anh em**, không bị xóa do override ở `properties`.

Ví dụ thực tế: parent có `<compilerArgs>` với deprecation warning và child muốn **thay** bằng unchecked warning:

~~~xml
<configuration>
    <compilerArgs combine.self="override">
        <arg>-Xlint:unchecked</arg>
    </compilerArgs>
</configuration>
~~~

Node `compilerArgs` child thay node tương ứng của parent, trong khi các option ở **nhánh anh em** như `<release>17</release>` có thể vẫn được kế thừa qua merge mặc định.

**Nguyên tắc:** đánh dấu override ở **nhánh nhỏ nhất đủ để đạt ý định**. Đừng override cả configuration chỉ để bỏ một arg nếu parent còn quy tắc Java release, security scanning hoặc output bắt buộc.

## 6. Nếu đặt cả hai attribute trên cùng một node?

Đây là ví dụ **không khuyến nghị**:

~~~xml
<items combine.children="append" combine.self="override">
    <item>child-only</item>
</items>
~~~

Theo Apache Maven, **override thắng append**. Không có thao tác “nối rồi chỉ thay một nửa” có ý nghĩa ở đây.

| Mong muốn | Cách dùng |
| --- | --- |
| Giữ các node parent không có ở child, child ưu tiên khi cùng tên | Không khai combine; mặc định merge |
| Nối toàn bộ danh sách parent rồi child | `combine.children="append"` |
| Thay một nhánh parent bằng nhánh child | `combine.self="override"` |
| Vừa append vừa override trên chính một phần tử | Không nên; override có ưu tiên |
| Chặn plugin hoặc execution truyền từ parent sang child | `<inherited>false</inherited>`, không phải combine |

Có thể sử dụng append trên `compilerArgs` và override trên một **nhánh khác** của cùng configuration nếu plugin semantics yêu cầu.

## 7. Phạm vi attribute và ba thế hệ POM

Hai sự thật cần đọc cùng nhau:

- `combine.children="append"` trên `items` chỉ quyết định hợp nhất **các phần tử con trực tiếp** của `items`. Nó **không tự lan xuống mọi node nested** như `items/item/flags/flag`.
- Nhưng **combine hints có thể được kế thừa từ parent qua child rồi đến grandchild**. Nếu một ancestor để lại combine attribute trên một node, cách ghép node tương ứng ở thế hệ POM sau có thể tiếp tục bị ảnh hưởng.

Minh họa:

~~~text
company-parent
    compilerArgs: -Xlint:deprecation
    combine.children="append"
         |
         v
service-parent
    compilerArgs: -Xlint:unchecked
         |
         v
service-app
    compilerArgs: -Xlint:fallthrough
~~~

Nếu hint được inherited và không bị thay, effective compilerArgs ở tầng sâu có thể chứa nhiều args từ các thế hệ. Không đọc mỗi file `service-app/pom.xml` rồi kết luận chắc chắn nó chỉ có một arg.

Hãy phân biệt:

- **Cây XML**: attribute không tự thay strategy của mọi descendant.
- **Cây inheritance của các POM**: attribute trên cùng nhánh có thể còn tác dụng khi một thế hệ tiếp tục merge.

Vì vậy, khi gặp kết quả “append dù child không ghi append”, hãy xem parent chain và effective POM.

## 8. Plugin-level config, execution-level config và inherited=false

Một plugin có thể khai:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <configuration>
        <!-- Tham số chung ở plugin level -->
    </configuration>
    <executions>
        <execution>
            <id>check-files</id>
            <phase>validate</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <!-- Tham số riêng execution -->
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đoạn này **chỉ minh họa cấu trúc**, không phải POM hoặc Ant target runnable. Trong dự án thật, plugin-level và execution-level configuration có thể được kết hợp khi goal chạy. Nếu parent đặt target trong execution còn child override **một target khác ở plugin-level**, kết quả có thể khác suy luận từ một tầng.

Maven còn dùng **execution id** để merge executions giữa parent/child. Nếu parent có id `check-files`, child khai cùng id có thể điều chỉnh execution ấy. Nếu child khai id `child-files`, nó thường tạo **execution thứ hai**, không phải sửa execution cũ.

### inherited=false không cùng nghĩa

- `<inherited>false</inherited>` tại **plugin** ngăn khai báo plugin parent truyền xuống POM con.
- `<inherited>false</inherited>` tại **execution** ngăn riêng execution đó truyền xuống, các execution khác còn có thể được kế thừa.
- `combine.*` chỉ xử lý **XML của cấu hình đã được đưa vào quá trình merge**.

Nếu một execution parent đã bị chặn inheritance, dùng `combine.children="append"` trong child không “khôi phục” execution bị chặn ấy. Tương tự, override target **không** tự làm AntRun ngừng chạy nếu execution vẫn được gắn vào phase.

## 9. Thực hành: một dự án Java 17 có ba kiểu merge nhìn thấy bằng file

Ta dùng **Maven AntRun Plugin 3.1.0** vì goal `run` có tham số `<target>` nhận Ant tasks. Parent tạo:

- `shared.marker` bằng `touch`;
- `parent.marker` bằng `echo`;
- thư mục `target` bằng `mkdir`.

Child khai một `echo` tạo `child.marker`. Ta thay duy nhất một XML attribute trong `app/pom.xml` để quan sát:

1. Merge mặc định: giữ `touch` của parent, child `echo` thay parent `echo` cùng tên.
2. Append: giữ **tất cả task** parent rồi child.
3. Override: chỉ còn những task child khai trong target.

Java source và test giữ nguyên trong ba lần. Mục đích là kiểm tra **cấu hình plugin**, không phải viết một ứng dụng có business logic phức tạp.

### 9.1. Cây thư mục

~~~text
merge-demo/
├── pom.xml
└── app/
    ├── pom.xml
    └── src/
        ├── main/java/vn/example/merge/App.java
        └── test/java/vn/example/merge/AppTest.java
~~~

Bạn cần Maven 3.9.x, JDK 17+ và repository có thể giải quyết Maven plugins/JUnit. Tạo đúng các file sau và chạy lệnh từ thư mục `merge-demo`.

### 9.2. POM cha hoàn chỉnh: merge-demo/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>merge-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
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
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>

                <configuration>
                    <target>
                        <mkdir dir="${project.build.directory}"/>
                        <touch file="${project.build.directory}/shared.marker"/>
                        <echo file="${project.build.directory}/parent.marker"
                              message="PARENT"/>
                    </target>
                </configuration>

                <executions>
                    <execution>
                        <id>make-markers</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `packaging=pom`: parent làm cấu hình/aggregator, không tạo JAR ứng dụng.
- `modules`: reactor tìm module `app`; không tự tạo inheritance.
- `pluginManagement`: quản lý các plugin dùng cho lifecycle `jar` của child.
- AntRun nằm ở `build/plugins`, có execution `make-markers` tại phase `validate`, nên goal `antrun:run` được gọi khi build đi qua phase ấy.
- AntRun `<configuration><target>` nằm ở **plugin-level**, không nằm trong execution. Điều này làm phần merge trong demo dễ quan sát hơn.
- `${project.build.directory}` dùng đường dẫn `target` của project hiệu lực. Parent và child có hai thư mục target riêng.
- `mkdir` tạo thư mục trước khi các task ghi file; `touch` tạo shared.marker, `echo` ghi parent.marker.
- Không có `<inherited>false</inherited>`; execution được truyền xuống child theo mặc định.

### 9.3. POM con hoàn chỉnh: merge-demo/app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example</groupId>
        <artifactId>merge-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <configuration>
                    <target>
                        <mkdir dir="${project.build.directory}"/>
                        <echo file="${project.build.directory}/child.marker"
                              message="CHILD"/>
                    </target>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.merge.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đọc cấu hình đúng cách:

- `<parent>` của app trỏ đến `merge-parent:1.0.0`.
- Child khai **cùng plugin identity** của AntRun nhưng không lặp version và execution. Nó nhận version `3.1.0` cùng execution `make-markers` từ parent.
- Node `<target>` trong child hiện **không có combine attribute**. Đây là **trạng thái A — default merge**.
- Child có `mkdir` riêng để bảo đảm thư mục tồn tại, kể cả khi khi merge các task parent không còn. Khi append, hai mkdir cùng mục tiêu có thể xuất hiện nhưng không hại trong demo.
- JAR Plugin ở child nhận version từ parent pluginManagement; cấu hình manifest giúp `java -jar` chạy ứng dụng không có external runtime dependency.
- JUnit Jupiter là **test dependency**, không phải Maven plugin; Surefire Plugin chạy JUnit theo lifecycle.

### 9.4. Java source chạy được: App.java

File `app/src/main/java/vn/example/merge/App.java`:

~~~java
package vn.example.merge;

public final class App {
    private App() {
    }

    public static String message(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Merge configuration OK: " + name.trim();
    }

    public static void main(String[] args) {
        System.out.println(message("Maven"));
    }
}
~~~

Ứng dụng sử dụng API của JDK 17, không cần thư viện runtime ngoài. Stdout **chính xác** khi gọi `App.main`:

~~~text
Merge configuration OK: Maven
~~~

### 9.5. Unit test: AppTest.java

File `app/src/test/java/vn/example/merge/AppTest.java`:

~~~java
package vn.example.merge;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void formatsMessage() {
        assertEquals("Merge configuration OK: Lan",
                App.message(" Lan "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> App.message("   "));
    }
}
~~~

Với POM đã khai đúng, Surefire chạy **2 tests PASS**, 0 failures/errors. Để so sánh ba kiểu merge, không cần chỉnh Java/test.

## 10. Thí nghiệm A — merge mặc định

Từ thư mục root `merge-demo`:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

`clean` xóa output cũ của parent và app, rồi `verify` chạy đến phase cần thiết của default lifecycle. AntRun goal `run` sẽ thực hiện ở phase `validate` của parent và app. Compiler/Surefire/JAR goal làm phần việc của module `jar`.

Với cấu hình mặc định, phần target của child được merge theo tên:

- `mkdir`: parent và child đều có, child có node cùng tên nên node child có ưu tiên.
- `touch`: chỉ có ở parent, được giữ để tạo `shared.marker`.
- `echo`: parent và child đều có, child `echo` thay parent `echo` trong default merge.

Do đó sau build sạch:

| Marker | Root parent | app child |
| --- | --- | --- |
| `shared.marker` | **Có** | **Có** |
| `parent.marker` | **Có** | **Không** |
| `child.marker` | **Không** | **Có** |

Các file nằm tại `target/<marker>` ở root và `app/target/<marker>` tại app. Kết quả này chỉ đúng khi đã chạy **một lần build sạch**; không dùng file còn sót từ build trước để suy luận.

JAR nằm ở:

~~~text
app/target/app-1.0.0.jar
~~~

Chạy:

~~~bash
java -jar app/target/app-1.0.0.jar
~~~

Stdout:

~~~text
Merge configuration OK: Maven
~~~

Việc AntRun tạo marker và stdout của `java -jar` là hai đầu ra độc lập. Test PASS xác nhận mã Java, còn file marker xác nhận việc merge/goal AntRun.

### Xem effective POM của app

~~~bash
mvn -pl :app help:effective-pom
mvn -pl :app help:effective-pom -Dverbose
~~~

Trong plugin `maven-antrun-plugin`, tìm `<configuration><target>`. Với thí nghiệm A, bạn cần thấy logic `mkdir`, `touch shared.marker`, `echo child.marker`; không có task ghi parent.marker trong app.

`-Dverbose` giúp truy nguồn một số khai báo. Không đếm số lần xuất hiện chuỗi `parent.marker` ở toàn output POM nếu nó còn trong comments/metadata; kiểm tra **target hiệu lực của đúng plugin**.

## 11. Thí nghiệm B — nối danh sách bằng combine.children="append"

Trong `app/pom.xml`, **chỉ đổi target của AntRun** thành:

~~~xml
<target combine.children="append">
    <mkdir dir="${project.build.directory}"/>
    <echo file="${project.build.directory}/child.marker"
          message="CHILD"/>
</target>
~~~

Đừng thêm attribute vào parent và đừng sửa execution id `make-markers`.

Phần target trong effective POM của app bây giờ tương đương:

~~~xml
<target combine.children="append">
    <!-- Tasks parent -->
    <mkdir dir="${project.build.directory}"/>
    <touch file="${project.build.directory}/shared.marker"/>
    <echo file="${project.build.directory}/parent.marker"
          message="PARENT"/>

    <!-- Tasks child được nối sau -->
    <mkdir dir="${project.build.directory}"/>
    <echo file="${project.build.directory}/child.marker"
          message="CHILD"/>
</target>
~~~

Những comment ở snippet này chỉ giải thích **nguồn gốc task**, không nhất thiết được in bởi Help Plugin. Thứ tự parent trước, child sau là quy tắc của append. Hai `mkdir` cùng xuất hiện vì append **không lọc trùng**.

Chạy:

~~~bash
mvn clean verify
mvn -pl :app help:effective-pom
~~~

Kết quả marker:

| Marker | Root parent | app child |
| --- | --- | --- |
| `shared.marker` | Có | **Có** |
| `parent.marker` | Có | **Có** |
| `child.marker` | Không | **Có** |

So với mặc định, **app/target/parent.marker giờ cũng xuất hiện**. Đây là bằng chứng hữu hình rằng child đã giữ task `echo` của parent **và** thêm task `echo` của mình.

**Lưu ý vận hành:** trong dự án thật, nối một tác vụ sinh mã hoặc gửi dữ liệu có thể chạy trùng và gây lỗi. Chỉ dùng append khi cả hai phần là danh sách thật sự có thể thực hiện nối.

## 12. Thí nghiệm C — thay target bằng combine.self="override"

Đổi target của AntRun **ở child** sang:

~~~xml
<target combine.self="override">
    <mkdir dir="${project.build.directory}"/>
    <echo file="${project.build.directory}/child.marker"
          message="CHILD"/>
</target>
~~~

Không để đồng thời `combine.children="append"` trên node ấy. Bây giờ target child thay **toàn bộ** target của parent: `touch shared.marker` và `echo parent.marker` của parent không được ghép vào app.

Chạy:

~~~bash
mvn clean verify
mvn -pl :app help:effective-pom
~~~

Kết quả:

| Marker | Root parent | app child |
| --- | --- | --- |
| `shared.marker` | Có | **Không** |
| `parent.marker` | Có | **Không** |
| `child.marker` | Không | **Có** |

`mkdir` trong child là bắt buộc đối với demo này: khi override target, bạn không còn có thể dựa vào `mkdir` parent để tạo output directory.

**Quan sát quan trọng:** AntRun trong app **vẫn chạy** ở phase `validate`. `combine.self="override"` **không tắt execution**. Nó chỉ thay nội dung target được thực thi.

### Khôi phục sau bài tập

Thay `<target combine.self="override">` trở lại `<target>` trong `app/pom.xml`, rồi chạy `mvn clean verify` để trở về trạng thái A. Đừng sửa parent, Java source hoặc JUnit đồng thời với thao tác này.

## 13. Bảng so sánh ba trạng thái

| Target ở app | app/shared.marker | app/parent.marker | app/child.marker | Kết quả |
| --- | --- | --- | --- | --- |
| `<target>` | Có | Không | Có | Merge XML mặc định: task parent không trùng tên được giữ |
| `<target combine.children="append">` | Có | Có | Có | Nối tất cả task parent rồi child |
| `<target combine.self="override">` | Không | Không | Có | Dùng duy nhất những task trong target child |

### 13.1. Lệnh kiểm tra trên Linux/macOS

Sau mỗi `mvn clean verify`:

~~~bash
test -f app/target/shared.marker && echo "shared=yes" || echo "shared=no"
test -f app/target/parent.marker && echo "parent=yes" || echo "parent=no"
test -f app/target/child.marker && echo "child=yes" || echo "child=no"
~~~

Kết quả với **mặc định**:

~~~text
shared=yes
parent=no
child=yes
~~~

Với **append**:

~~~text
shared=yes
parent=yes
child=yes
~~~

Với **override**:

~~~text
shared=no
parent=no
child=yes
~~~

### 13.2. Lệnh kiểm tra trên Windows PowerShell

~~~powershell
"shared=$(Test-Path 'app\target\shared.marker')"
"parent=$(Test-Path 'app\target\parent.marker')"
"child=$(Test-Path 'app\target\child.marker')"
~~~

PowerShell in `True` hoặc `False` thay vì `yes/no`. Nội dung file tạo bởi `echo` có thể đọc bằng:

~~~powershell
Get-Content 'app\target\child.marker'
~~~

File `child.marker` có chữ `CHILD`; nếu `parent.marker` tồn tại thì chứa chữ `PARENT`. Số newline có thể phụ thuộc cách Ant ghi file, không phải tiêu chí so sánh XML merge.

### 13.3. Vì sao phải dùng clean?

Nếu lần A đã tạo `app/target/shared.marker`, rồi lần C chỉ chạy `mvn verify`, marker cũ vẫn có thể nằm trên đĩa dù target mới không tạo nó nữa. Kết luận từ file cũ sẽ sai. Luôn dùng `mvn clean verify` trong các thí nghiệm và kiểm tra **log goal của đúng lần chạy**.

## 14. Nếu cấu hình nằm ở execution thay vì plugin?

Có thể đặt `<configuration>` bên trong một execution:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>write-files</id>
            <phase>validate</phase>
            <goals><goal>run</goal></goals>
            <configuration>
                <target>
                    <!-- Ant tasks của execution -->
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **snippet vị trí**, không phải ví dụ runnable độc lập. Để thay configuration của execution parent từ child:

- Child cần khai **cùng plugin identity**.
- Child cần dùng **cùng execution id `write-files`** nếu muốn chỉnh execution đó.
- `combine.*` đặt trên **đúng node bên trong execution configuration**.
- Phải kiểm tra plugin-level configuration có tương tác với execution-level configuration hay không.

Nếu child đặt id `child-files` khác `write-files`, Maven có thể coi đó là **một execution mới**, khiến goal chạy hai lần. `combine.children` trên node `target` không thay thế quy tắc ghép executions theo id.

## 15. Dùng combine.* trong pluginManagement có ý nghĩa gì?

Parent có thể quản lý Compiler Plugin:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                    <showWarnings>true</showWarnings>
                    <compilerArgs>
                        <arg>-Xlint:deprecation</arg>
                    </compilerArgs>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Child muốn bổ sung flag:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <compilerArgs combine.children="append">
                    <arg>-Xlint:unchecked</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Khi plugin được dùng ở child và management của parent áp dụng, cấu hình cuối có `release=17`, `showWarnings=true` cùng hai compiler args `-Xlint:deprecation` và `-Xlint:unchecked`.

Nếu child muốn thay cờ cũ, dùng:

~~~xml
<compilerArgs combine.self="override">
    <arg>-Xlint:unchecked</arg>
</compilerArgs>
~~~

Điều này chỉ thay compilerArgs, **không tự xóa release=17** ở nhánh anh em.

**Nhớ rằng:** một plugin chỉ được liệt kê trong `pluginManagement` **không tự tạo một goal execution mới**. Compiler Plugin có binding chuẩn ở `jar` lifecycle nên thường được dùng; với plugin không có binding như AntRun, bạn cần `build/plugins` + execution hoặc gọi goal phù hợp.

## 16. Tám lỗi thường gặp

| Hiện tượng | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| Child mất item parent trong danh sách | Default merge theo tên | Cân nhắc append ở đúng node danh sách |
| Child giữ cả item parent khi muốn bỏ | Append đang hoạt động, có thể inherited từ ancestor | Dùng override ở nhánh cần thay |
| Child mất thêm cấu hình bắt buộc | Override ở nhánh quá rộng | Thu hẹp override hoặc khai lại những tham số cần |
| Ghi cả append lẫn override nhưng không thấy parent | Override thắng | Chỉ giữ một attribute theo ý định |
| Plugin chạy hai execution | Child dùng execution id mới hoặc có binding thêm | Kiểm tra execution ids và log |
| Child không nhận plugin của parent | Không có parent đúng hoặc plugin/exec `inherited=false` | Kiểm tra POM inheritance và effective POM |
| XML hợp lệ nhưng plugin báo unknown parameter | Attribute/node đặt sai cấp, hoặc tên parameter không được plugin hỗ trợ | Xem plugin docs/Help Plugin describe |
| Marker còn sau khi bỏ task | Output cũ trong target | `mvn clean verify` rồi kiểm tra lại |

Ngoài ra, CI có thể chạy Maven/JDK hoặc active profiles khác laptop. Nếu cùng POM mà build khác, hãy đối chiếu `mvn -version`, effective POM, phiên bản plugin, profile, settings và đầu ra thực tế.

### Không nhầm với dependencyManagement

`dependencyManagement` giải quyết phiên bản/cấu hình của **project dependencies**, không điều khiển XML merge của plugin bằng cách thêm `combine.*` vào dependency declarations. `pluginManagement` quản lý **build plugin**, còn `combine.*` làm nhiệm vụ merge những tham số bên trong plugin configuration.

Để tránh nhầm:

- Plugin version: `build/plugins` hoặc `pluginManagement`.
- Dependency version: `dependencies`/`dependencyManagement`/BOM.
- Quyền kế thừa plugin/execution: `inherited`.
- Hợp nhất XML plugin config: `combine.self`/`combine.children`.
- Thời điểm goal chạy: lifecycle binding và execution phase.

## 17. Quy trình kiểm chứng trước khi merge PR

1. **Xác định POM cha/con** và cùng plugin `groupId:artifactId`; đừng nhầm `modules` với inheritance.
2. **Đọc cấu hình parent** và child của cùng plugin, gồm pluginManagement và execution-level config.
3. **Chỉ rõ node thay đổi**. Mục tiêu là nối danh sách, thay nhánh hay chỉ đổi một giá trị?
4. **Dự đoán merged XML** theo mặc định/append/override, ghi lại phần parent cần được giữ.
5. **Xem effective POM** của đúng module:

   ~~~bash
   mvn -pl :app help:effective-pom
   mvn -pl :app help:effective-pom -Dverbose
   ~~~

6. **Chạy build sạch** và kiểm tra log/plugin outputs:

   ~~~bash
   mvn clean verify
   java -jar app/target/app-1.0.0.jar
   ~~~

7. **Đối chiếu marker và test** với bảng mục 13; test PASS không tự chứng minh task merge đúng.
8. **Kiểm tra parent chain** nếu attribute combine không nằm ngay trong child đang đọc.
9. **Review duplicate tasks/options** khi dùng append; review cấu hình bị mất khi dùng override.
10. **Chỉ sửa một yếu tố mỗi lần**, không đồng thời đổi Java version, plugin version, phase và merge strategy.

Không cần bật Maven debug `-X` nếu effective POM và output đã đủ. Khi phải debug, rà soát log trước khi chia sẻ vì có thể chứa đường dẫn, hostname repository hoặc properties nội bộ.

## 18. Bài tập và đáp án định hướng

**Bài tập A — Merge mặc định.** Parent có `<options><option>A</option><option>B</option></options>` và `<format>strict</format>`. Child có `<options><option>C</option></options>`. Hãy dự đoán: danh sách option của child thay option parent trong trường hợp này, nhưng `format=strict` vẫn còn vì child không ghi format.

**Bài tập B — Append.** Đặt `combine.children="append"` trên node options của child. Dự đoán `A, B, C` theo đúng thứ tự. Nếu child còn chứa `A` thì sao? Maven có thể giữ **hai A**, không tự khử trùng.

**Bài tập C — Override.** Đặt `combine.self="override"` trên node options của child. Kết quả chỉ còn `C` trong options; node format bên ngoài vẫn được giữ.

**Bài tập D — Chạy cấu hình mẫu.** Dựng `merge-demo` đúng POM/Java/test, chạy `mvn clean verify` và `java -jar app/target/app-1.0.0.jar`. Ghi 2 tests PASS, stdout và marker ở trạng thái A.

**Bài tập E — Thay một attribute.** Đổi target child sang `combine.children="append"`, build sạch. Xác nhận cả ba file `shared.marker`, `parent.marker`, `child.marker` có ở app, đối chiếu effective POM.

**Bài tập F — Thay cả nhánh.** Đổi target child sang `combine.self="override"`, build sạch. Chứng minh chỉ `child.marker` có trong app, trong khi parent root vẫn có hai marker của mình.

**Bài tập G — Compiler flags.** Parent có `-Xlint:deprecation`, child có `-Xlint:unchecked`. So sánh merged `compilerArgs` với mặc định, append và override. Giải thích vì sao `release=17` ở sibling node có thể vẫn còn.

**Bài tập H — inherited=false.** Nếu parent chặn inheritance của AntRun Plugin, target child có append có thể ghép lại execution parent đã bị chặn không? Không. Muốn goal chạy, child cần cấu hình plugin/execution phù hợp.

**Bài tập I — Ba thế hệ POM.** Một tổ tiên có `combine.children="append"` ở `compilerArgs`. Vì sao POM cháu không ghi attribute nhưng effective config vẫn có thể nối args? Vì combine hint có thể được inherited theo cùng nhánh.

**Bài tập J — Review PR.** Một PR thêm `combine.self="override"` vào `compilerArgs`. Hãy liệt kê những cờ parent bị mất, những sibling vẫn còn, các test cần chạy và cách xác minh bằng `help:effective-pom`.

### Tự kiểm tra

Bạn đạt yêu cầu khi giải thích được:

- Maven mặc định **merge theo tên phần tử XML**.
- `combine.children="append"` là **nối con parent rồi con child**, không tự bỏ trùng.
- `combine.self="override"` là **thay trọn nhánh** đang gắn attribute, không xóa plugin.
- Hai attribute trên cùng node **không kết hợp thành chiến lược thứ ba**; override thắng.
- Attribute không tự đệ quy xuống nested nodes, nhưng có thể được inherited qua nhiều POM.
- `inherited=false`, `pluginManagement`, execution id và lifecycle phase là những cơ chế khác.
- Không suy luận cấu hình cuối từ chỉ một snippet khi có parent/profile/management; hãy xem effective POM và chạy kiểm chứng.

**Ghi nhớ:** *append để nối, override để thay, không khai gì thì merge theo tên*. Luôn chọn đúng nhánh XML và xác minh trên module thực tế.

## 19. Tài liệu chính thức để đọc thêm

- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): *Default plugin configuration inheritance* và *Advanced configuration inheritance*, ví dụ và quy tắc `combine.children`/`combine.self`.
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): cấu trúc plugin configuration, execution và inheritance.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase và plugin goals.
- [Apache Maven AntRun Plugin 3.1.0 — Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html): tham số `target`, Ant tasks và goal `run`.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): xem POM hiệu lực sau inheritance, management và profile.
- [Apache Maven Compiler Plugin 3.14.1](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/): thông tin về `release`, `compilerArgs` và các goal biên dịch.
