# Binding mặc định, execution bổ sung và nguy cơ chạy trùng Maven Plugin

## 1. Vấn đề cốt lõi

Trong Maven, một **build lifecycle** gồm các **phase** có thứ tự; mỗi phase có thể được gắn với một hoặc nhiều **plugin goal**. Khi gọi `mvn package` cho một project Java có `packaging=jar`, Maven tự chạy những goal quen thuộc như:

- `resources:resources` để xử lý tài nguyên.
- `compiler:compile` để biên dịch mã nguồn chính.
- `resources:testResources` và `compiler:testCompile` để chuẩn bị test.
- `surefire:test` để chạy test.
- `jar:jar` để đóng gói JAR.

Người dùng **không cần tự khai báo mọi goal này trong `<executions>`**. Chúng đã được Maven gắn theo **default lifecycle bindings** cho packaging `jar`.

Rủi ro xuất hiện khi developer muốn chỉnh một tham số như Java release, test settings hoặc JAR manifest, rồi **tạo thêm execution cho chính goal vốn đã được gắn mặc định**. Maven có thể thực thi goal đó hai lần: một lần do packaging binding, một lần do execution bổ sung. Hậu quả có thể là compile/resource processing thừa, test chạy lặp, output bị ghi đè hoặc lỗi khi packaging hai main artifacts.

Mục tiêu của bài là phân biệt:

1. **Binding mặc định do packaging** với **execution tự khai báo**.
2. **Plugin-level configuration** với **execution-level configuration**.
3. **Default execution ID** như `default-compile` với một ID mới như `compile-again`.
4. **Chạy hai lần thật** với **nhiều dòng log do build nhiều module**.
5. Cách cấu hình mở rộng **có chủ đích** mà không làm build chạy trùng.

## 2. Lifecycle, phase, plugin, goal, execution: năm khái niệm

| Thuật ngữ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Lifecycle** | `default`, `clean`, `site` | Chuỗi phase phục vụ mục tiêu build |
| **Phase** | `compile`, `test`, `package` | Mốc trong lifecycle, có thứ tự |
| **Plugin** | `maven-compiler-plugin` | Gói chứa một hoặc nhiều goals |
| **Goal** | `compiler:compile` | Tác vụ cụ thể Maven thực thi |
| **Execution** | `<execution><id>...` | Cách cấu hình/bind goal vào phase hoặc tùy chỉnh lần chạy |

Ví dụ:

~~~bash
mvn clean package
~~~

Ở đây `clean` thuộc **clean lifecycle**, còn `package` là một phase trong **default lifecycle**. Maven thực hiện clean, sau đó đi qua các phase của default lifecycle tới `package`. Các goal được gắn với những phase tương ứng sẽ chạy theo execution plan.

Một ví dụ khác:

~~~bash
mvn compiler:compile
~~~

Đây là **gọi goal trực tiếp**, không phải gọi phase `compile` và cũng **không tự chạy tất cả các phase trước compile** theo cách `mvn compile` làm. Phân biệt này rất quan trọng nếu resources hoặc generated sources cần được chuẩn bị trước khi compiler chạy.

**Một phase không mặc định bằng một goal.** Có phase không có goal nào được bind. Có phase có nhiều goals, và có goal được bind trong nhiều executions ở những phase khác nhau.

## 3. Default bindings phụ thuộc vào packaging

Trong POM:

~~~xml
<packaging>jar</packaging>
~~~

Maven chọn bộ binding mặc định cho packaging `jar`. Nếu không khai báo `<packaging>`, mặc định của một POM Maven project thông thường là `jar`.

Bảng các binding chính trong **default lifecycle**, đối với packaging `jar` của Maven 3:

| Phase | Goal được bind mặc định | Execution ID thường gặp |
| --- | --- | --- |
| `process-resources` | `resources:resources` | `default-resources` |
| `compile` | `compiler:compile` | `default-compile` |
| `process-test-resources` | `resources:testResources` | `default-testResources` |
| `test-compile` | `compiler:testCompile` | `default-testCompile` |
| `test` | `surefire:test` | `default-test` |
| `package` | `jar:jar` | `default-jar` |
| `install` | `install:install` | `default-install` |
| `deploy` | `deploy:deploy` | `default-deploy` |

Trong thực tế, version và cách hiển thị của plugin phụ thuộc Maven installation, pluginManagement và POM hiệu lực. **Execution ID** là danh tính của lần chạy, không phải tên goal.

Ví dụ `mvn compile` đã đi qua `process-resources` và `compile`; `mvn test` đi xa hơn đến test; `mvn package` còn chạy goal đóng gói. Không phải mỗi phase đều chạy một lần `compiler:compile`.

### Các packaging khác có binding khác

**`packaging=pom`** thường dành cho parent, aggregator hoặc BOM, không có default goal biên dịch Java và đóng gói JAR của `jar` project. **`war`** có packaging goal `war:war`; **`ear`** có binding riêng; **`maven-plugin`** cần các goal liên quan plugin descriptor. Vì vậy:

- Không copy default binding table của `jar` rồi cho rằng mọi project đều giống.
- Không thấy `compiler:compile` trong log của POM-only module chưa chắc là lỗi.
- Nếu POM con thay packaging, cần xét bộ lifecycle mapping tương ứng.
- Build extensions/custom packaging cũng có thể ảnh hưởng binding; kiểm tra setup của project thực tế.

### Điểm then chốt: “default” không có nghĩa bất biến

Maven đã gắn goal nào vào phase còn phụ thuộc vào loại packaging. Tuy nhiên, **configuration và version của plugin** có thể được thay đổi trong POM, parent hoặc pluginManagement. Do đó, goal mặc định vẫn có thể dùng cấu hình dự án; **không cần tạo một goal execution mới chỉ để sửa tham số**.

## 4. Ba nơi hay nhầm khi cấu hình plugin

Giả sử dự án muốn biên dịch bằng Java 17. Có ba cấu hình dễ thấy:

### Cách A — Property mà Compiler Plugin hỗ trợ

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Với Compiler Plugin phiên bản hỗ trợ `release`, đây thường là cách ngắn gọn để đặt Java target. Nó **không tạo thêm compiler execution**.

### Cách B — Configuration ở cấp plugin

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

**`<configuration>` nằm trực tiếp dưới `<plugin>`**, có thể áp dụng cho các goal executions thích hợp của plugin. Đối với `jar` packaging, default `compiler:compile` vẫn được Maven gọi một lần theo binding mặc định nếu không có execution khác thêm vào.

### Cách C — Configuration cho đúng default execution

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <executions>
        <execution>
            <id>default-compile</id>
            <configuration>
                <release>17</release>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**`default-compile` là ID của implied execution** được lifecycle binding tạo cho `compiler:compile`. Khi child/POM cung cấp configuration cho đúng ID này, nó **tùy chỉnh execution mặc định**, không có ý định thêm một lượt compile độc lập.

Ở ví dụ này không cần lặp `<phase>compile</phase>` hay `<goals><goal>compile</goal></goals>` để nhận diện execution mặc định; ID đã trỏ vào default execution tương ứng. Nếu muốn cấu hình test compiler riêng, có implied ID `default-testCompile`.

Ba cách không nên dùng đồng thời cho cùng một mục tiêu nếu không cần thiết. **Cách A hoặc B** thường đủ để thống nhất Java 17; **C** hữu ích khi từng execution của cùng plugin cần config riêng.

## 5. Execution ID mặc định: cơ chế quan trọng để tránh trùng

Apache Maven có cơ chế định danh **implied executions**:

- Goals được **lifecycle mapping của packaging** bind có ID theo mẫu **`default-<goalName>`**.
- Goals được gọi **trực tiếp từ CLI** có execution ID **`default-cli`**.
- Executions có **ID tự đặt** là những lần chạy được cấu hình thêm hoặc kế thừa theo model.

Ví dụ với Compiler Plugin:

| Kiểu chạy | Lệnh/cấu hình | ID |
| --- | --- | --- |
| Lifecycle compile | `mvn compile` trên jar project | `default-compile` |
| Lifecycle testCompile | `mvn test` đi qua test-compile | `default-testCompile` |
| CLI trực tiếp | `mvn compiler:compile` | `default-cli` |
| Execution tự khai báo | `<id>compile-again</id>` | `compile-again` |

**`default-cli` không phải binding mặc định của phase compile.** Nó dùng cho goal được gọi trực tiếp. Nếu có nhu cầu config riêng cho CLI, có thể khai báo một `<execution><id>default-cli</id>...` với configuration phù hợp, nhưng không nên dùng nó như một cách thêm goal vào mọi lần chạy lifecycle.

**Execution ID chỉ có ý nghĩa trong phạm vi một plugin**: hai plugin khác nhau có cùng execution ID không tự hợp nhất với nhau.

## 6. Bẫy phổ biến: tạo execution mới cho goal vốn đã bind

Ví dụ **không khuyến nghị**, giả sử đặt mảnh sau trong plugin Compiler của một project `packaging=jar`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <executions>
        <execution>
            <id>compile-again</id>
            <phase>compile</phase>
            <goals>
                <goal>compile</goal>
            </goals>
            <configuration>
                <release>17</release>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Maven đã có binding:

~~~text
compile phase
    |
    +-- compiler:compile (default-compile)    <- packaging=jar
    |
    +-- compiler:compile (compile-again)     <- execution vừa thêm
~~~

Với một lệnh:

~~~bash
mvn clean compile
~~~

log có thể có hai goal invocations, minh họa:

~~~text
--- maven-compiler-plugin:3.13.0:compile (default-compile) @ binding-demo ---
--- maven-compiler-plugin:3.13.0:compile (compile-again) @ binding-demo ---
~~~

Đây là **hai executions của cùng goal**, không phải chỉ do Maven đi qua phase `compile` hai lần. Compiler Plugin có thể nhận thấy class đã cập nhật ở lần đầu và in “Nothing to compile” ở lần sau; **không có nghĩa goal thứ hai đã biến mất**. Trong những dự án lớn hoặc cấu hình khác, công việc lặp lại có thể tốn CPU hoặc gây sự cố.

**Sửa đúng:** nếu mục đích duy nhất là dùng `release=17`, chuyển cấu hình thành property `maven.compiler.release`, plugin-level `<configuration>`, hoặc `<execution><id>default-compile</id>`; **không cần execution ID mới**.

## 7. Chạy trùng còn xảy ra với Resources, Surefire và JAR

### 7.1. Resources Plugin: xử lý cùng resource hai lần

Một jar project đã chạy `resources:resources` ở `process-resources`. Nếu thêm:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>copy-resources-again</id>
            <phase>process-resources</phase>
            <goals>
                <goal>resources</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

thì cùng phase có thể chạy:

~~~text
resources:resources (default-resources)
resources:resources (copy-resources-again)
~~~

Nếu hai executions dùng cùng source/target, Maven có thể copy/filter resource hai lần hoặc tạo output conflict. Nếu chỉ muốn đổi filtering/encoding, nên cấu hình **default resource processing** qua build/resources và plugin settings; không cần tạo thêm một lượt `resources`.

### 7.2. Surefire Plugin: test chạy trùng

Một jar project đã bind `surefire:test` ở phase `test`. Nếu thêm:

~~~xml
<execution>
    <id>run-unit-tests-again</id>
    <phase>test</phase>
    <goals>
        <goal>test</goal>
    </goals>
</execution>
~~~

dưới đúng `maven-surefire-plugin`, Maven có thể gọi **Surefire test goal hai lần**: `default-test` rồi `run-unit-tests-again`.

Điều đó không đảm bảo mỗi test method chạy hai lần trong mọi cấu hình vì có test selection, skip, reports, forks và plugin behavior; **nhưng số goal invocations là hai**. Nếu test có side effects như tạo dữ liệu, mở port hoặc gọi service ngoài, chạy trùng rất nguy hiểm.

Nếu muốn **đổi `forkCount`, `reuseForks`, `argLine` hoặc các test settings chung**, cấu hình ở cấp plugin hoặc đúng `default-test`. Nếu muốn chạy integration tests riêng, thường dùng **Failsafe** ở các phase thích hợp và có naming conventions rõ ràng; không tự nhân đôi Surefire test vô cớ.

### 7.3. JAR Plugin: hai executions cùng tạo main JAR

`packaging=jar` đã có `jar:jar` ở `package`. Nếu thêm execution mới cho `jar` mà **không tạo classifier khác**:

~~~xml
<execution>
    <id>make-jar-again</id>
    <phase>package</phase>
    <goals>
        <goal>jar</goal>
    </goals>
</execution>
~~~

có thể tạo xung đột khi plugin cố tạo/attach main artifact lần hai, hoặc ghi đè output tùy version/configuration. Không hứa một thông báo lỗi cố định áp dụng cho mọi plugin version.

Để thay đổi manifest/excludes của JAR chính, đặt cấu hình ở `maven-jar-plugin` hoặc tùy chỉnh **`default-jar`**. Nếu có mục đích tạo **artifact phụ**, nên dùng classifier và cấu hình minh bạch, chẳng hạn `jar:test-jar` cho test classes thay vì chạy lại main `jar:jar`.

## 8. Bảng xác định khi nào một execution thật sự được thêm

| POM configuration | Với `packaging=jar` | Nguy cơ trùng |
| --- | --- | --- |
| Khai báo Compiler Plugin **chỉ có version** | Default compile vẫn chạy | Không thêm execution |
| Compiler `<configuration><release>17</release>` | Đổi config của goal thích hợp | Không thêm execution |
| `<id>default-compile</id>` config | Tùy chỉnh implied compile execution | Không tạo goal compile độc lập |
| `<id>compile-again</id><phase>compile</phase><goal>compile</goal>` | Thêm execution `compiler:compile` | **Có** |
| Surefire `<id>default-test</id>` config | Tùy chỉnh default test execution | Không thêm test invocation |
| Surefire `<id>second-tests</id><goal>test</goal>` ở `test` | Thêm test execution | **Có** |
| JAR `<id>default-jar</id>` config | Tùy chỉnh main JAR | Không tạo main jar execution mới |
| JAR `<id>second-jar</id><goal>jar</goal>` ở `package` | Thêm JAR invocation | **Có**, dễ conflict |
| Plugin riêng `build-helper:add-source` ở `generate-sources` | Thêm việc mới chưa có trong jar defaults | Thường phù hợp nếu thực sự cần |
| JAR `test-jar` ở `package` | Tạo attached test artifact riêng | Có thêm goal **có chủ đích**, không phải cùng main JAR |

Lưu ý: bảng minh họa **điển hình của Maven 3 và packaging jar**. Trong dự án thật, parent POM, profiles, custom packaging, lifecycle extension hoặc các execution khác có thể thay đổi bức tranh cuối cùng.

## 9. Bản demo Java 17: cấu hình chuẩn, không tạo execution trùng

Ví dụ độc lập này dùng Maven 3.9+ và JDK 17+ để build một ứng dụng nhỏ. POM chỉ cấu hình plugin versions/parameters, **không khai báo thêm `compiler:compile`, `surefire:test` hay `jar:jar` bằng một execution ID mới**.

### 9.1. Cấu trúc project

~~~text
binding-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/binding/App.java
    └── test/
        └── java/com/example/binding/AppTest.java
~~~

### 9.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>binding-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <reuseForks>true</reuseForks>
                </configuration>
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

Ở đây:

- **packaging=jar** quyết định default lifecycle bindings.
- Các plugins được **pin version** để kiểm soát build.
- Compiler nhận target Java 17 từ `maven.compiler.release`.
- Surefire nhận `reuseForks=true` ở cấp plugin.
- Không có `<executions>` mới cho những goals được bind mặc định.
- JUnit Jupiter chỉ dùng trong test scope, không là runtime dependency của main JAR thông thường.

### 9.3. Java class sản phẩm

Tạo file **src/main/java/com/example/binding/App.java**:

~~~java
package com.example.binding;

public final class App {

    private App() {
    }

    public static String message() {
        return "Default binding works";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 9.4. JUnit test

Tạo file **src/test/java/com/example/binding/AppTest.java**:

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {

    @Test
    void messageMatches() {
        assertEquals("Default binding works", App.message());
    }
}
~~~

### 9.5. Chạy build và đọc kết quả

Từ thư mục chứa **pom.xml**:

~~~bash
mvn -version
mvn -B clean verify
java -cp target/binding-demo-1.0.0.jar com.example.binding.App
jar tf target/binding-demo-1.0.0.jar
~~~

Khi Maven/JDK đúng và các plugins/dependencies phân giải được, `clean verify` đi qua các phase cần thiết, compile Java 17, chạy **1 JUnit test** và đóng gói JAR. Lệnh Java in **chính xác**:

~~~text
Default binding works
~~~

Trong danh sách `jar tf` phải có:

~~~text
com/example/binding/App.class
~~~

Ngoài ra có thể có `META-INF/` và các entry metadata; đây **không phải toàn bộ stdout của `jar tf`**. POM không khai báo `Main-Class` trong manifest nên ví dụ dùng `java -cp` thay vì mặc định dùng `java -jar`.

### 9.6. Kiểm tra những execution trong log

Trong log `mvn -B clean verify`, tìm các dòng chứa goal và execution ID. Minh họa phần tên goal có thể xuất hiện:

~~~text
resources:resources (default-resources)
compiler:compile (default-compile)
resources:testResources (default-testResources)
compiler:testCompile (default-testCompile)
surefire:test (default-test)
jar:jar (default-jar)
~~~

Đây là **những nhãn minh họa được trích từ kiểu log**, không phải toàn bộ stdout. Trong project mẫu, mỗi goal mặc định nêu trên dự kiến có **một invocation mỗi module mỗi lượt build**, không có `compile-again` hay `run-unit-tests-again`.

Quan trọng: `mvn verify` đi qua `compile`, `test`, `package` theo thứ tự; **không chạy compile lại chỉ vì bạn chọn phase cao hơn**. Maven thực thi các phase từ đầu tới mốc yêu cầu và gọi các goals trong execution plan.

## 10. Thử nghiệm gây trùng có kiểm soát, rồi sửa

Để **nhận biết** vấn đề mà không sửa project thật, hãy copy project demo sang một thư mục thử nghiệm riêng và thêm execution `compile-again` của phần 6 vào **maven-compiler-plugin**.

Chạy:

~~~bash
mvn -B clean compile
~~~

Quan sát log và đếm trong **cùng module**:

~~~text
compiler:compile (default-compile)
compiler:compile (compile-again)
~~~

**Hai dòng goal** là chứng cứ có hai executions. Trong trường hợp code không đổi ở lần thứ hai, Compiler Plugin có thể báo “Nothing to compile” nhưng vẫn đã được gọi hai lần.

Sau đó bỏ execution `compile-again`, giữ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

hoặc chuyển cấu hình vào plugin-level. Chạy clean compile lại để thấy chỉ còn `default-compile` cho cùng module.

**Không thực hiện thử nghiệm trên POM release của nhóm** nếu project có plugin goals có side effects, ví dụ deploy, upload hoặc migration database. Nên thử trên bản copy/demo hoặc branch riêng đã được quản lý.

## 11. Một ví dụ mở rộng đúng: attach test JAR thay vì tạo main JAR hai lần

Nếu dự án thật sự cần phát hành test classes để module khác dùng làm test fixture, có thể thêm **một goal khác** là `jar:test-jar`. Đặt cấu hình sau **bên trong maven-jar-plugin** của POM demo (đây là mảnh plugin configuration, không phải POM độc lập):

~~~xml
<executions>
    <execution>
        <id>attach-test-classes</id>
        <phase>package</phase>
        <goals>
            <goal>test-jar</goal>
        </goals>
    </execution>
</executions>
~~~

Khi chạy:

~~~bash
mvn -B clean package
~~~

trong project có test classes được biên dịch, dự kiến có:

~~~text
target/binding-demo-1.0.0.jar
target/binding-demo-1.0.0-tests.jar
~~~

Log thường có **main `jar:jar (default-jar)`** và **extra `jar:test-jar (attach-test-classes)`**. Đây là **hai goals khác nhau tạo hai artifact khác vai trò**, không phải chạy lại `jar:jar` vô ích.

Nếu chỉ cần module khác tái sử dụng test fixtures, hãy cân nhắc thiết kế module fixture riêng khi hợp lý; không nhất thiết phải phát hành test JAR. Test JAR chỉ có nếu plugin thực sự attach artifact; việc khai báo dependency consumer không tự tạo test JAR.

## 12. Execution mới và cấu hình mặc định là hai cơ chế độc lập

Một **plugin goal** đôi khi tự khai báo default phase trong plugin descriptor. Ví dụ `compiler:compile` có phase mặc định là compile. Khi một execution tự khai báo có `<goals><goal>compile</goal></goals>` mà không ghi `<phase>`, Maven có thể bind goal dựa vào default phase của goal.

Điều đó khác với **packaging default binding**:

- **Default phase của goal:** plugin developer mô tả phase hợp lý cho một goal khi execution tự cấu hình không chỉ rõ phase.
- **Packaging binding:** Maven xác định một goal cần chạy **mặc định** cho packaging `jar`, `war`, `pom`...
- **Execution được khai báo trong POM:** có ID và có thể cung cấp phase/goals/configuration riêng.
- **Goal được gọi trực tiếp:** có thể thực thi ngoài chuỗi lifecycle bình thường.

Vì vậy **bỏ thẻ `<phase>` khỏi execution ID mới không bảo đảm goal sẽ không chạy**. Nếu goal có default phase, nó vẫn có thể được bind và gây duplicate. Để kiểm tra, xem plugin goal docs (`mvn plugin:help` hoặc `help:describe` phù hợp), rồi xem log thực tế.

Nếu muốn đổi tham số của **default execution**, dùng ID `default-<goalName>` hoặc plugin-level config, thay vì nghĩ rằng bỏ phase là đủ.

## 13. Thứ tự thực thi khi nhiều goals cùng phase

Apache Maven hướng dẫn rằng với một phase có cả **goals do packaging bind** và **goals do POM bổ sung**, những goal từ packaging binding được thực thi trước, sau đó đến những goals cấu hình trong POM.

Ví dụ ở phase `compile`:

~~~text
compile:
  1) compiler:compile        (default-compile; jar packaging)
  2) compiler:compile        (compile-again; custom execution)
~~~

Trong cùng POM, thứ tự các goals cấu hình cũng liên quan tới thứ tự khai báo. Khi inheritance, profiles hoặc nhiều plugins tác động, việc suy luận chỉ từ một mảnh XML có thể sai; hãy nhìn effective POM và log.

**Không nên thiết kế producer và consumer bắt buộc cùng phase nếu thứ tự ngầm có thể thay đổi.** Khi một generator phải chạy trước compiler, thường đặt generator ở **generate-sources**, đăng ký compile source root, rồi để Compiler Plugin mặc định chạy ở **compile**. Điều này rõ ràng hơn việc dựa vào thứ tự hai executions trong compile.

Tương tự, files cần copy nên được chuẩn bị trước `process-resources`; tests được compile trước phase `test`; packaging đi sau compile. Maven lifecycle là công cụ diễn đạt những quan hệ thứ tự ấy.

## 14. Parent POM, pluginManagement, profiles: execution trùng có thể đến từ ngoài POM con

Một child POM có thể **không tự viết execution trùng**, nhưng vẫn thấy goal chạy hai lần vì được **kế thừa**.

Nguồn cần xem:

1. **Parent POM:** có `<build><plugins><plugin><executions>` gắn một goal đã bind mặc định không?
2. **pluginManagement:** có version/configuration cung cấp cho plugin khi nó được sử dụng không?
3. **Profiles đang active:** có thêm một execution cùng goal hoặc một plugin khác chạy cùng công việc không?
4. **Child POM:** có execution ID mới hay đã cố định cấu hình cho default execution?
5. **Packaging:** child có thực sự là `jar` hay custom packaging?
6. **Invocation:** CLI có gọi thêm goal trực tiếp ngoài lifecycle không?

**Quan trọng về pluginManagement:** đặt plugin trong **pluginManagement** thường để quản lý version/configuration, không phải tự bật một execution tùy ý. Tuy nhiên **plugin đã được default lifecycle binding sử dụng** vẫn có thể nhận cấu hình và version được quản lý. Đừng nói “pluginManagement hoàn toàn không có tác dụng tới default goal”.

### Execution IDs và kế thừa

Trong cùng một plugin thuộc **một POM**, execution IDs cần duy nhất. Khi parent/child có execution cùng ID, Maven **hợp nhất/ghi đè cấu hình theo quy tắc model**. Nếu IDs khác nhau, hai executions có thể cùng tồn tại.

Ví dụ parent đã có:

~~~xml
<execution>
    <id>compile-secondary</id>
    <phase>compile</phase>
    <goals><goal>compile</goal></goals>
</execution>
~~~

Child thêm:

~~~xml
<execution>
    <id>compile-child</id>
    <phase>compile</phase>
    <goals><goal>compile</goal></goals>
</execution>
~~~

Nếu cả hai đều được kế thừa/active trong project `jar`, có thể có **ba lần gọi compiler:compile**: default `default-compile`, `compile-secondary` và `compile-child`. Đây là ví dụ **nguy cơ**, không phải mẫu cấu hình nên dùng.

Nếu child cần thay config của một execution **đã tồn tại** ở parent, hãy dùng **cùng execution ID** để tùy chỉnh có kiểm soát, không tự tạo ID mới cho một goal có cùng ý nghĩa.

### inherited=false cho tác vụ chỉ chạy ở parent

Một plugin/execution phục vụ riêng aggregator đôi khi không nên truyền xuống child. Parent có thể khai báo:

~~~xml
<execution>
    <id>parent-only-check</id>
    <phase>verify</phase>
    <goals><goal>run</goal></goals>
    <inherited>false</inherited>
    <configuration>
        <target><echo message="Parent-only check"/></target>
    </configuration>
</execution>
~~~

Đây là **mảnh execution** của `maven-antrun-plugin` có goal `run`; phải đặt dưới plugin đầy đủ để dùng. Cờ **`inherited=false`** ngăn execution ấy kế thừa xuống child, **không tắt nó tại parent**.

Tránh dùng `inherited=false` như cách “sửa nhanh” mọi duplicate: trước tiên phải hiểu vì sao execution có mặt, và parent/child nào phải sở hữu công việc.

## 15. Lệnh Maven cũng có thể tự gây hai lượt goal

### 15.1. Vừa gọi phase vừa gọi goal trực tiếp

~~~bash
mvn compile compiler:compile
~~~

Đầu tiên Maven thực thi lifecycle tới phase `compile` (đã gồm `compiler:compile` mặc định), rồi gọi trực tiếp `compiler:compile` như một CLI goal. Đây là hai lần gọi compiler theo **hai yêu cầu trong cùng lệnh**, ngay cả nếu POM không có custom execution.

Nếu chỉ muốn build source đầy đủ theo lifecycle, dùng:

~~~bash
mvn compile
~~~

Nếu chỉ muốn chạy trực tiếp goal vì một lý do chẩn đoán, dùng:

~~~bash
mvn compiler:compile
~~~

nhưng nhớ lệnh gọi goal trực tiếp không tự bảo đảm resources/generated sources đã sẵn.

### 15.2. Gọi nhiều phase thuộc cùng lifecycle

~~~bash
mvn test package
~~~

Maven xử lý các task được chỉ định theo thứ tự; yêu cầu phase `test` và sau đó `package` có thể khiến những phase trước `package`, bao gồm test, được thực thi lại. Đừng dùng cách này để “chắc chắn test chạy”. Nếu muốn build và test tới package, chỉ cần:

~~~bash
mvn package
~~~

Hoặc nếu cần checks đến verify:

~~~bash
mvn verify
~~~

### 15.3. Clean không phải lần compile thứ hai

~~~bash
mvn clean package
~~~

`clean` thuộc **clean lifecycle**, sau đó `package` đi qua default lifecycle một lượt. Nó **không tự chạy compiler:compile hai lần** chỉ vì có từ clean. Đừng nhầm số phases đã qua với số executions của cùng goal.

### 15.4. Multi-module logs không đồng nghĩa goal duplicate

Trong reactor:

~~~text
parent/
├── pom.xml
├── module-a/pom.xml
└── module-b/pom.xml
~~~

Một lệnh `mvn verify` có thể có `compiler:compile (default-compile)` trong **cả module-a lẫn module-b**. Muốn xác định duplicate, hãy đếm theo **module**, **phase**, **goal**, **execution ID**, thay vì grep toàn bộ log rồi thấy nhiều dòng `compile`.

Nếu Maven chạy reactor song song với `-T`, log của nhiều modules còn có thể đan xen. Không suy ra một mục tiêu build chạy trùng chỉ từ thời điểm in log.

## 16. Cách dùng Help Plugin và log để nhìn execution plan

Các lệnh chẩn đoán:

~~~bash
mvn help:effective-pom
mvn help:active-profiles
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
mvn -X clean compile
~~~

**`help:effective-pom`** cho thấy configuration đã hợp nhất từ parent/profiles và những execution khai báo trong model. Nhưng **không nên coi file này là bản in đầy đủ/đáng tin duy nhất của toàn bộ implied default binding plan** trong mọi Maven version. **Log thực thi goal/phase là bằng chứng quan trọng** rằng goal nào đã thật sự được gọi.

**`help:describe`** cho biết parameters và metadata của plugin goal, bao gồm thông tin default phase khi plugin công bố. Nó không tự cho biết build thực tế có thêm execution nào từ parent/profile.

Với lỗi trùng:

1. Chạy build tại module cần điều tra, ưu tiên môi trường thử nghiệm.
2. Ghi Maven/JDK versions và active profiles.
3. Tìm các dòng `plugin:goal (executionId) @ artifactId` trong log.
4. Nếu cùng goal xuất hiện nhiều lần trong cùng module/lifecycle, ghi lại từng ID.
5. Tìm ID tương ứng trong **effective POM**, parent POM và profiles; nhớ cả default binding.
6. Xác định mỗi lần gọi có mục đích riêng không.
7. Nếu không, sửa đúng nơi: plugin-level config, default execution ID hoặc loại execution thừa.
8. Chạy lại và đối chiếu số lần gọi **trong cùng module**.

Bật `-X` khi cần thông tin bổ sung. Debug log có thể rất dài và có đường dẫn hoặc settings nhạy cảm; hãy lọc trước khi chia sẻ.

## 17. Các hậu quả của execution trùng

Hậu quả không chỉ là build chậm:

| Goal lặp | Có thể gây ra | Điều cần xác minh |
| --- | --- | --- |
| `compiler:compile` | CPU/IO thừa, incremental compiler chạy lại, class output khác | Execution IDs, source roots, compiler config |
| `resources:resources` | Copy/filter file hai lần, output overwrite | Input/output directories, filtering |
| `surefire:test` | Test classes có thể chạy lặp, external side effects | Reports, test counts, skip/fork settings |
| `jar:jar` | Ghi đè/attach main artifact hai lần, lỗi classifier | Main artifact vs attached artifact |
| Code generator goal | Sinh nguồn hoặc dữ liệu trùng, file conflicts | Phase generate-sources, output, source roots |
| Signing/assembly goal | Ký/đóng gói nhiều lần, attached artifact xung đột | Classifier, artifact IDs, output files |
| Goal có side effects bên ngoài | Upload/deploy/migration chạy lặp | Quyền, idempotency, môi trường mục tiêu |

**Hai goal invocations không đảm bảo hai lần thực hiện cùng một lượng công việc.** Compiler có thể skip vì code không đổi, Resources Plugin có thể skip file đã up-to-date, một test goal có thể skip vì flag. Tuy nhiên việc tồn tại execution dư vẫn là vấn đề cấu hình cần được hiểu.

Khi plugin có side effects, không dùng môi trường production để thử nghiệm tình huống chạy trùng. Chẩn đoán an toàn bằng log ở local/CI sandbox.

## 18. Cách chọn phương án cấu hình đúng

| Mục đích | Phương án ưu tiên |
| --- | --- |
| Đổi Java release chung | `maven.compiler.release` hoặc Compiler plugin-level config |
| Đổi một giá trị Surefire chung | Surefire plugin-level `<configuration>` |
| Đổi riêng compile và testCompile | `default-compile` / `default-testCompile` |
| Đổi config JAR chính | JAR plugin-level config hoặc `default-jar` |
| Thêm goal mới có nhiệm vụ khác | `<executions>` với ID rõ, phase đúng |
| Tạo test JAR phụ | `jar:test-jar` thay vì main `jar:jar` lần hai |
| Tạo generated sources | Generator ở `generate-sources`, đăng ký source root |
| Chỉ chạy goal trực tiếp từ CLI với config riêng | `default-cli` khi thực sự cần |
| Parent-only execution | `inherited=false` ở cấp đúng |
| Giữ versions/plugins nhất quán nhiều module | `pluginManagement` trong parent; kích hoạt goals đúng nơi |

Quy tắc review nhanh trước khi thêm một execution:

1. Goal đã có trong **packaging default binding** chưa?
2. Parent hoặc profile đã gắn goal ấy chưa?
3. Có cần một **lần chạy mới**, hay chỉ cần đổi configuration của lần đã có?
4. Nếu cần thêm, **output và side effects khác nhau** ở điểm nào?
5. ID mới có ý nghĩa riêng không? Phase có đúng quan hệ producer/consumer không?
6. Có classifier/đường dẫn output riêng để tránh ghi đè không?
7. Trong log mỗi module, số goal invocations có đúng thiết kế không?

Nếu không trả lời rõ câu 3, **đừng thêm execution mới** vội.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `compiler:compile` xuất hiện hai lần trong cùng module | Custom execution ID mới trùng goal đã bind | Giữ default execution; chuyển config lên plugin-level hoặc `default-compile` |
| Test reports xuất hiện bất thường | Surefire được bind và có execution `test` thêm | Xem `default-test`, ID tự khai báo và plugin config |
| `jar:jar` báo attach artifact error | Hai goals cùng tạo main JAR | Chỉ có một main JAR; dùng classifier/goal khác nếu cần |
| Resource file được filter hai lần | Custom `resources:resources` cùng output | Xóa duplicate, cấu hình resources/default execution |
| Config trong pluginManagement mà không thấy custom goal | Management không tự bind goal tùy ý | Khai báo plugin execution thực sự hoặc dùng default binding phù hợp |
| Child chạy goal parent ngoài ý muốn | Execution được kế thừa | Kiểm tra IDs, `inherited=false`, parent plugin config |
| Không thấy goal chạy dù đã thêm `<execution>` | Goal không có phase/default phase phù hợp hoặc profile chưa active | Chỉ rõ phase, kiểm tra plugin descriptor và active profile |
| Một phase có nhiều log dòng của nhiều modules | Reactor đang build nhiều projects | Đếm theo `@ artifactId` và execution ID |
| `mvn compile compiler:compile` gọi compiler 2 lần | Vừa gọi phase vừa gọi trực tiếp goal | Chọn một cách gọi phù hợp |
| `mvn test package` làm test lặp | Yêu cầu hai phase cùng lifecycle theo thứ tự | Gọi `mvn package` hoặc `mvn verify` |
| `mvn clean package` bị hiểu là compile hai lần | Nhầm clean lifecycle với default | Đọc goal log; clean không tạo compile execution mới |
| Parent + child cùng execution ID mà config không như ý | Cơ chế merge/override theo ID | Xem effective POM; dùng IDs ổn định |
| Duplicate plugin entry trong `<plugins>` | Cùng plugin khai báo hai lần trong một POM | Gộp thành một plugin với nhiều executions có chủ đích |

## 20. Bài tập tự kiểm tra

**Câu 1.** Dự án `packaging=jar` không có compiler `<executions>`. Chạy `mvn compile` có gọi `compiler:compile` không?

**Đáp:** Có, do default binding `compiler:compile` ở phase compile.

**Câu 2.** Muốn Java release 17, có phải thêm `<execution><id>my-compile</id>`?

**Đáp:** Không. Dùng `maven.compiler.release` hoặc plugin-level configuration là đủ trong phần lớn dự án.

**Câu 3.** `default-compile` và `compile-again` có vai trò giống nhau?

**Đáp:** Không. `default-compile` là ID của implied execution; `compile-again` là ID tự khai báo có thể tạo execution bổ sung.

**Câu 4.** Nếu thêm `resources:resources` ở `process-resources` với ID `copy-again`, goal có thể chạy bao nhiêu lần trong jar project?

**Đáp:** Ít nhất có default execution và custom execution này, tức **hai goal invocations**, nếu không có cấu hình đặc biệt vô hiệu hóa chúng.

**Câu 5.** Vì `mvn verify` đi qua compile/test/package nên nó có chạy `compiler:compile` lại ở mỗi phase không?

**Đáp:** Không. Maven đi qua các phase có thứ tự; default compiler goal bind ở compile, không tự lặp tại test/package.

**Câu 6.** Hai dòng `compiler:compile (default-compile)` ở hai modules có chắc là duplicate?

**Đáp:** Không. Đó có thể là một lần compile hợp lệ cho mỗi module.

**Câu 7.** `mvn compiler:compile` có chạy đủ `process-resources` như `mvn compile`?

**Đáp:** Không. Goal được gọi trực tiếp không tự thực thi toàn bộ chuỗi phase trước compile.

**Câu 8.** Muốn có JAR test classes phụ, có nên thêm execution `jar:jar` ID `make-jar-again`?

**Đáp:** Không. Dùng goal `jar:test-jar` hoặc một thiết kế fixture artifact phù hợp.

**Câu 9.** Parent đã có execution ID `quality-check`; child muốn đổi config của đúng execution ấy, nên tạo ID khác?

**Đáp:** Không nếu chỉ muốn tùy chỉnh execution kế thừa; dùng cùng ID để merge/override config có kiểm soát.

**Câu 10.** Chạy `mvn clean package` có tự nhân đôi compile không?

**Đáp:** Không. Clean là lifecycle riêng, package chạy default lifecycle đến package.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Guide to Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Compiler Plugin — compile goal](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Apache Maven Surefire Plugin — test goal](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven JAR Plugin — test-jar goal](https://maven.apache.org/plugins/maven-jar-plugin/test-jar-mojo.html)

