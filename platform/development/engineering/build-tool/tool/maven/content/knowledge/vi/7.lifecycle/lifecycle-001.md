# Maven Lifecycle, Phase và Goal: phân biệt ba khái niệm

## 1. Tại sao cần phân biệt?

Khi chạy `mvn package`, Maven có thể kiểm tra dự án, xử lý tài nguyên, biên dịch Java, biên dịch bài test, chạy test rồi tạo tệp JAR. Nhưng từ `package` trong lệnh **không phải** tên một plugin; đó là một **phase** (giai đoạn) nằm trong **lifecycle** (vòng đời) build. Công việc cụ thể ở từng phase lại do **goal** của các Maven plugin thực hiện.

Một sai lầm thường gặp là coi `mvn test` tương đương `mvn surefire:test` hoặc coi `mvn clean` tương đương `mvn clean:clean`. Các cặp lệnh này có thể cùng gọi một goal nào đó, nhưng phạm vi thực hiện và các bước chuẩn bị khác nhau.

Sau bài này, bạn có thể:

1. Nêu chính xác sự khác biệt giữa **lifecycle**, **phase** và **plugin goal**.
2. Giải thích tại sao gọi một phase sẽ đi qua mọi phase đứng trước nó trong cùng lifecycle.
3. Phân biệt ba lifecycle dựng sẵn của Maven: `default`, `clean` và `site`.
4. Mô tả cách `packaging` và `pom.xml` quyết định goal nào được gắn vào phase nào.
5. So sánh lệnh `mvn compile`, `mvn test`, `mvn package`, `mvn verify`, `mvn install`, `mvn deploy` và lệnh gọi trực tiếp `plugin:goal`.
6. Đọc log để nhận diện goal, execution id và thứ tự chạy; cấu hình một plugin goal cho một phase bằng `<executions>`.
7. Thực hành với dự án Java 17 có mã nguồn và kiểm thử thật; xử lý lỗi do chọn nhầm phase hoặc goal.

**Ba khái niệm cốt lõi:**

| Khái niệm | Hiểu đơn giản | Ví dụ | Vai trò |
| --- | --- | --- | --- |
| **Lifecycle** | Một quy trình build gồm nhiều giai đoạn có thứ tự | `default`, `clean`, `site` | Xác định chuỗi phase và quan hệ trước–sau |
| **Phase** | Một mốc/giai đoạn trong lifecycle | `compile`, `test`, `package`, `verify` | Là điểm dừng khi người dùng yêu cầu Maven chạy lifecycle |
| **Goal** | Một tác vụ cụ thể do plugin cung cấp | `compiler:compile`, `surefire:test`, `jar:jar` | Thực sự thực hiện công việc như biên dịch, kiểm thử, đóng gói |

Mô hình tư duy:

~~~text
Lifecycle: default
   ├── validate
   ├── ...
   ├── compile ───────────> compiler:compile  (goal của Compiler Plugin)
   ├── ...
   ├── test ──────────────> surefire:test      (goal của Surefire Plugin)
   ├── ...
   ├── package ───────────> jar:jar            (goal của JAR Plugin nếu packaging=jar)
   ├── ...
   ├── verify
   ├── install ───────────> install:install
   └── deploy ────────────> deploy:deploy
                          `
                      plugin goals làm việc
~~~

Sơ đồ chỉ hiển thị **một số phase/goal điển hình** của dự án `packaging=jar`. Trong thực tế còn các phase xen giữa, nhiều goal trên cùng phase, và goal do dự án tự cấu hình. **Không phải phase nào cũng có goal mặc định**, nên Maven có thể đi qua một phase mà không chạy tác vụ hữu hình nào tại phase đó.

## 2. Lifecycle: quy trình có thứ tự

Một **build lifecycle** là một chuỗi các phase được Maven định nghĩa. Người dùng thường gọi **phase đích**, ví dụ:

~~~bash
mvn package
~~~

Maven xác định lifecycle chứa phase `package`, sau đó xử lý các phase theo thứ tự **từ đầu đến và bao gồm `package`**. Những goal được gắn vào các phase trên đường đi sẽ được thực thi. Điều này lý giải vì sao `mvn package` thường biên dịch và chạy unit test trước khi đóng gói mà bạn không cần gõ từng lệnh riêng.

Maven có ba lifecycle dựng sẵn:

| Lifecycle | Các phase đáng nhớ | Mục tiêu |
| --- | --- | --- |
| `default` | `validate` → `compile` → `test` → `package` → `verify` → `install` → `deploy` | Xây dựng, kiểm chứng, cài đặt và phát hành artifact |
| `clean` | `pre-clean` → `clean` → `post-clean` | Dọn output của lần build trước |
| `site` | `pre-site` → `site` → `post-site` → `site-deploy` | Tạo và phát hành site/tài liệu dự án |

Ba lifecycle là những chuỗi riêng biệt. `mvn clean` đi theo **clean lifecycle**; nó **không tự** biên dịch dự án. `mvn package` đi theo **default lifecycle**; nó **không tự** xóa thư mục `target/` trước khi build. Nếu muốn vừa dọn vừa build, gọi:

~~~bash
mvn clean package
~~~

Lệnh trên có hai phase đích thuộc hai lifecycle khác nhau: Maven chạy phần `clean` trước, rồi phần `default` đến `package` theo thứ tự các tác vụ được yêu cầu trên command line. Không tồn tại một lifecycle tên `clean package`.

Một lệnh quen thuộc trong CI là:

~~~bash
mvn -B -ntp clean verify
~~~

`-B` là batch mode; `-ntp` giảm hiển thị tiến trình tải. Lệnh này dọn output rồi đi qua default lifecycle đến `verify`. Mức độ kiểm chứng thực tế phụ thuộc plugin/test được cấu hình; tên phase `verify` **không tự tạo** các bài kiểm thử chưa tồn tại.

## 3. Phase: các mốc trong từng lifecycle

### 3.1. Thứ tự đầy đủ của default lifecycle

Các phase của default lifecycle trong Maven 3 gồm:

~~~text
validate
initialize
generate-sources
process-sources
generate-resources
process-resources
compile
process-classes
generate-test-sources
process-test-sources
generate-test-resources
process-test-resources
test-compile
process-test-classes
test
prepare-package
package
pre-integration-test
integration-test
post-integration-test
verify
install
deploy
~~~

**Điều cần hiểu:** `mvn test` không chỉ chạy hai phase `compile` và `test`. Maven đi qua **tất cả** các phase từ `validate` đến `test`, kể cả những phase không hiển thị trong log vì không có goal ràng buộc.

Các nhóm phase tiêu biểu:

| Nhóm phase | Vai trò thường gặp |
| --- | --- |
| `validate`, `initialize` | Kiểm tra điều kiện/cấu hình và chuẩn bị thông tin ban đầu |
| `generate-sources`, `process-sources` | Tạo và xử lý mã nguồn nếu dự án có plugin tương ứng |
| `generate-resources`, `process-resources` | Chuẩn bị/copy tài nguyên dùng khi chạy ứng dụng |
| `compile` | Biên dịch nguồn Java chính khi có Compiler Plugin được ràng buộc |
| `generate-test-sources` đến `test-compile` | Chuẩn bị tài nguyên/mã nguồn test và biên dịch test |
| `test` | Chạy unit test bằng plugin/framework được cấu hình |
| `prepare-package`, `package` | Chuẩn bị và tạo artifact như JAR/WAR |
| `pre-integration-test`, `integration-test`, `post-integration-test` | Chuẩn bị, chạy và dọn môi trường kiểm thử tích hợp nếu đã cấu hình |
| `verify` | Thực hiện các kiểm tra/tiêu chí xác minh bổ sung được gắn vào phase |
| `install` | Đưa artifact vào Maven local repository để dự án khác trên máy sử dụng |
| `deploy` | Đưa artifact lên remote repository được cấu hình và có quyền truy cập |

Không nên hiểu tên phase như một lời bảo đảm. Ví dụ, **`test` là tên phase**, nhưng muốn chạy JUnit cần dependency test, test class phù hợp và plugin test runner tương ứng. Nếu dự án không có test, Maven vẫn có thể đi qua `test` thành công. Tương tự, nếu không cấu hình kiểm thử tích hợp, các phase integration test có thể không chạy kiểm thử tích hợp nào cả.

### 3.2. Phase có thể không có công việc

Một phase **không phải bản thân một chương trình thực thi**. Nó là vị trí để Maven sắp đặt các goal. Với dự án đơn giản, `initialize` hoặc `generate-sources` có thể không có goal nào. Việc Maven “đi qua” phase không có nghĩa log phải in một dòng tác vụ tương ứng.

Vì vậy:

- `mvn validate` có thể hoàn tất rất nhanh nếu không có goal thêm vào `validate`.
- `mvn generate-sources` có thể không sinh tệp nào nếu dự án chưa khai báo plugin code-generation.
- `mvn verify` đi qua `verify` nhưng không tự chạy kiểm tra chất lượng ngoài những goal đã ràng buộc.

Muốn thêm công việc tại một phase, bạn phải chọn plugin goal và cấu hình việc gắn goal đó với phase, hoặc dùng default binding từ packaging.

### 3.3. `clean` và `site` có phase riêng

`clean` lifecycle:

~~~text
pre-clean → clean → post-clean
~~~

`mvn clean` đi qua `pre-clean` rồi `clean`; mặc định `maven-clean-plugin:clean` dọn thư mục output build như `target/`. Nó không có nghĩa xóa source, POM, cache `~/.m2` hoặc tệp do bạn tự tạo bên ngoài thư mục output, trừ khi có cấu hình dọn bổ sung phù hợp.

`site` lifecycle:

~~~text
pre-site → site → post-site → site-deploy
~~~

`mvn site` yêu cầu Maven tạo site theo cấu hình các plugin report/site. `mvn site-deploy` đi đến phase phát hành site (và các phase site trước đó), nhưng muốn phát hành thành công cần nơi nhận được cấu hình. **Site deployment** khác với `deploy` artifact của default lifecycle.

## 4. Goal: tác vụ cụ thể thuộc một plugin

Một Maven plugin chứa một hoặc nhiều goal. Cách biểu diễn thông dụng trên dòng lệnh là `pluginPrefix:goal`:

~~~bash
mvn compiler:compile
mvn surefire:test
mvn jar:jar
mvn clean:clean
~~~

Tên đứng trước dấu `:` là **prefix của plugin**, không phải lifecycle. Phần sau dấu `:` là tên **goal** của plugin đó. Cách gọi ngắn phụ thuộc cơ chế Maven tìm plugin/prefix; để tránh phụ thuộc việc phân giải plugin, có thể gọi đầy đủ tọa độ plugin, version và goal:

~~~bash
mvn org.apache.maven.plugins:maven-compiler-plugin:3.14.0:compile
~~~

Goal tương ứng làm việc ở mức cụ thể:

| Goal | Plugin | Công việc |
| --- | --- | --- |
| `compiler:compile` | Maven Compiler Plugin | Biên dịch nguồn ứng dụng |
| `compiler:testCompile` | Maven Compiler Plugin | Biên dịch nguồn test |
| `resources:resources` | Maven Resources Plugin | Xử lý/copy tài nguyên ứng dụng |
| `resources:testResources` | Maven Resources Plugin | Xử lý/copy tài nguyên test |
| `surefire:test` | Maven Surefire Plugin | Chạy unit tests |
| `jar:jar` | Maven JAR Plugin | Tạo JAR từ output dự án |
| `clean:clean` | Maven Clean Plugin | Dọn thư mục output |
| `install:install` | Maven Install Plugin | Cài artifact vào local repository |
| `deploy:deploy` | Maven Deploy Plugin | Đẩy artifact lên remote repository |

**Goal có thể được gọi theo hai cơ chế:**

1. **Thông qua lifecycle binding:** Khi chạy `mvn package`, Maven đến phase `compile` và thực thi `compiler:compile` nếu goal này được gắn vào phase đó; tương tự với những goal liên quan.
2. **Gọi trực tiếp:** Khi chạy `mvn compiler:compile`, bạn yêu cầu một goal cụ thể, **không tự động yêu cầu Maven đi qua tất cả phase từ `validate` tới `compile`**.

Một plugin goal có thể có **default phase** trong metadata. Điều này chỉ gợi ý phase để gắn goal khi plugin được đưa vào lifecycle qua cấu hình phù hợp; nó **không biến lệnh gọi trực tiếp goal thành việc chạy cả lifecycle**. Cấu hình `<executions>` trong POM giúp khai báo khi nào goal được chạy.

## 5. Ai quyết định goal nào gắn với phase nào?

Maven ghép một **execution plan** (kế hoạch các goal thực thi) bằng cách xét:

1. Phase đích người dùng yêu cầu, ví dụ `package`.
2. Lifecycle chứa phase đó.
3. **Packaging** của dự án và ánh xạ goal mặc định cho packaging.
4. Các plugin execution được khai báo hoặc kế thừa trong `pom.xml` (bao gồm parent/profile đang hoạt động).
5. Cấu hình cụ thể của plugin, Java, dependency và môi trường.

### 5.1. Packaging tạo các ràng buộc mặc định

Trong POM:

~~~xml
<packaging>jar</packaging>
~~~

Với dự án `jar` tiêu chuẩn, Maven thường có các ràng buộc mặc định như sau:

| Phase | Goal tiêu biểu |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |
| `install` | `install:install` |
| `deploy` | `deploy:deploy` |

Đây là **ánh xạ điển hình cho packaging=jar**. Phiên bản plugin mặc định, chi tiết execution và các goal bổ sung có thể phụ thuộc phiên bản Maven, parent POM và plugin configuration. Với `packaging=war`, phase `package` có thể dùng goal đóng gói WAR thay vì `jar:jar`. Với `packaging=pom`, các phase biên dịch Java/đóng gói JAR thường không được gắn như dự án JAR, nhưng `install`/`deploy` vẫn có ý nghĩa đối với POM artifact.

**Quy tắc quan trọng:** cùng lệnh `mvn package` nhưng hai dự án có `packaging` khác nhau có thể tạo artifact khác nhau. Lifecycle và thứ tự phase là khung chung; goal nào được gắn phụ thuộc kiểu dự án.

### 5.2. Cấu hình trong POM có thể thêm goal vào phase

Ví dụ muốn in một dấu mốc vào log mỗi khi quá trình build đi qua `validate`. Bạn có thể dùng Maven Antrun Plugin và khai báo execution:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>announce-validate</id>
            <phase>validate</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="VALIDATE: checked project configuration"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **đoạn XML đặt bên trong `<build><plugins>`**, không phải một tệp POM độc lập. Giải thích:

- `artifactId` và `version` xác định plugin và bản plugin.
- `<execution>` là một cấu hình thực thi cụ thể của plugin.
- `<id>announce-validate</id>` giúp phân biệt execution trong log và khi cấu hình kế thừa.
- `<phase>validate</phase>` chỉ rõ giai đoạn goal phải tham gia.
- `<goal>run</goal>` chọn goal `antrun:run`.
- `<configuration><target>...` truyền tác vụ Ant `echo` vào goal.

Vì vậy `mvn validate` **đã có** một goal làm việc: `antrun:run` in dòng thông báo. Nếu gọi `mvn compile`, Maven vẫn đi qua `validate` nên goal này cũng chạy, rồi các goal được gắn vào những phase tiếp theo. Nếu gọi `mvn clean` riêng, Maven không đi qua default lifecycle `validate`, nên goal nói trên không được gọi chỉ bởi lệnh clean.

Nếu không khai báo `<executions>` và goal không có default lifecycle binding, **việc liệt kê plugin trong `<plugins>` không tự động làm goal chạy**. Còn khai báo version trong `<pluginManagement>` chỉ quản lý cấu hình/phiên bản cho nơi sử dụng, không tự gắn một goal mới vào lifecycle.

### 5.3. Goal có default phase vẫn cần được gắn qua cơ chế phù hợp

Nhiều Maven goal có default phase được ghi trong tài liệu plugin. Ví dụ goal `compiler:compile` có default phase `compile`; goal `compiler:testCompile` có default phase `test-compile`. Nếu tạo `<execution>` với `<goals>` mà bỏ `<phase>`, Maven có thể dùng default phase của goal. Nếu goal không có default phase, execution bỏ `<phase>` có thể không được chạy khi gọi lifecycle.

Không nên hiểu “goal có default phase” là cứ đặt plugin vào POM thì goal luôn chạy. Hãy xem packaging default binding, `<executions>` và effective POM để biết thực tế.

### 5.4. Nhiều goal ở cùng một phase

Một phase có thể có nhiều goal:

~~~text
package
  ├── jar:jar             (goal mặc định của packaging=jar)
  └── jar:test-jar        (goal thêm bằng cấu hình plugin)
~~~

Thông thường goal được gắn mặc định từ packaging chạy trước các goal bổ sung trong POM; giữa những execution do POM khai báo, thứ tự và cơ chế kế thừa có ảnh hưởng, vì vậy cần xem tài liệu Maven theo phiên bản và kiểm tra log thực tế.

**Không đồng nhất số goal với số phase:** một phase có thể có 0, 1 hoặc nhiều goal, và một goal có thể được cấu hình chạy ở nhiều execution/phase khác nhau.

## 6. Thí nghiệm Java 17 hoàn chỉnh

Dự án mẫu dưới đây cho phép quan sát cả **phase** và **goal** bằng output build. Cần JDK 17+ cùng Maven 3.x tương thích, hoặc Maven Wrapper đã được dự án chuẩn bị. Plugin/dependency có thể được tải từ Maven repository trong lần đầu.

Cấu trúc:

~~~text
lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── dev/
    │           └── example/
    │               ├── Calculator.java
    │               └── App.java
    └── test/
        └── java/
            └── dev/
                └── example/
                    └── CalculatorTest.java
~~~

### 6.1. POM đầy đủ

Tạo `pom.xml` ở gốc dự án:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>announce-validate</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo message="VALIDATE: checked project configuration"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ở POM này:

- `packaging=jar` dùng ánh xạ goal mặc định của dự án JAR.
- Compiler Plugin chịu trách nhiệm biên dịch và lấy Java target từ `maven.compiler.release=17`.
- `junit-jupiter` là dependency có `scope=test` để viết test; Surefire 3.5.2 là plugin chạy unit test khi đến phase `test`.
- JAR Plugin tạo artifact tại phase `package`.
- Antrun Plugin gắn thêm `antrun:run` vào phase `validate` và in marker dễ nhận biết.

**Lưu ý:** `<scope>test</scope>` là phạm vi dependency trên classpath; nó **không phải** tên phase `test` và không phải cách yêu cầu Maven chạy test. Sự trùng chữ “test” ở các cơ chế này không làm chúng đồng nhất.

### 6.2. Hai lớp ứng dụng

Tạo `src/main/java/dev/example/Calculator.java`:

~~~java
package dev.example;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }
}
~~~

Tạo `src/main/java/dev/example/App.java`:

~~~java
package dev.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Result: " + Calculator.add(7, 5));
    }
}
~~~

Hai lớp dùng API Java cơ bản, không cần framework. Chạy chúng bằng `java -cp target/classes dev.example.App` sau khi đã đi qua phase `compile`.

### 6.3. Test JUnit 5

Tạo `src/test/java/dev/example/CalculatorTest.java`:

~~~java
package dev.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(12, Calculator.add(7, 5));
    }
}
~~~

Lớp này được đặt trong `src/test/java`; test method có annotation `@Test`, khớp cơ chế khám phá JUnit Jupiter của Surefire. Với một test đúng như trên, báo cáo Surefire dự kiến có **1 test, 0 failure, 0 error, 0 skipped**, trừ khi cấu hình thực tế bổ sung test khác hoặc thay đổi quy tắc khám phá.

### 6.4. Chạy và quan sát theo từng phase

Mở terminal tại thư mục `lifecycle-demo`.

**Chặng 1 — chỉ validate:**

~~~bash
mvn -B -ntp validate
~~~

Trong log sẽ có một invocation của `maven-antrun-plugin:run` gắn với execution `announce-validate`, cùng marker chứa:

~~~text
VALIDATE: checked project configuration
~~~

Đây là **đoạn nhận diện trong log**, không phải cam kết toàn bộ stdout chính xác (Maven còn in metadata, tiến trình tải plugin, `BUILD SUCCESS`, v.v.). Vì chưa đến phase `compile`, không nên dùng lần chạy này để kết luận `Calculator.class` đã được biên dịch.

**Chặng 2 — đến compile:**

~~~bash
mvn -B -ntp compile
java -cp target/classes dev.example.App
~~~

Maven chạy các phase từ `validate` tới `compile`, gồm marker Antrun ở `validate` và `compiler:compile` ở `compile`. Nếu chạy lệnh Java cuối thành công, stdout chính xác:

~~~text
Result: 12
~~~

**Chặng 3 — đến test:**

~~~bash
mvn -B -ntp test
~~~

Maven đi qua `test-compile` rồi tới `test`. Bạn có thể nhận ra goal `compiler:testCompile` và `surefire:test`; test `CalculatorTest.addsTwoNumbers` được chạy. Lệnh này **không yêu cầu phase `package`**, nên không nên dùng nó làm bằng chứng rằng JAR mới đã được đóng gói.

**Chặng 4 — đến package:**

~~~bash
mvn -B -ntp package
jar tf target/lifecycle-demo-1.0.0.jar
~~~

Maven chạy đến `package`, gồm cả unit test ở phase `test` trước đó, sau đó dùng `jar:jar` tạo JAR. Lệnh `jar tf` phải có các mục như:

~~~text
dev/example/Calculator.class
dev/example/App.class
~~~

JAR ví dụ **không được cấu hình `Main-Class` trong manifest**, vì vậy lệnh `java -jar target/lifecycle-demo-1.0.0.jar` không phải cách chạy được bảo đảm. Dùng `java -cp target/classes dev.example.App` hoặc cấu hình manifest nếu thực sự cần executable JAR.

**Chặng 5 — dọn và xác minh:**

~~~bash
mvn -B -ntp clean verify
java -cp target/classes dev.example.App
~~~

`clean` xóa output build cũ (mặc định ở `target/`). `verify` của default lifecycle chạy các phase đến và gồm `verify`, vì vậy phải biên dịch và kiểm thử lại. Trong ví dụ chưa khai báo một goal chất lượng riêng tại `verify`; test thực sự chạy ở `test`. Lệnh `java` tiếp tục in `Result: 12`.

**Chặng 6 — cài vào local repository:**

~~~bash
mvn -B -ntp install
~~~

`install` đi qua các phase của default lifecycle đến `install`, tạo/cài artifact vào local Maven repository, thường ở:

~~~text
~/.m2/repository/dev/example/lifecycle-demo/1.0.0/
    lifecycle-demo-1.0.0.pom
    lifecycle-demo-1.0.0.jar
~~~

Đường dẫn cụ thể có thể khác nếu dùng `settings.xml` hoặc `-Dmaven.repo.local`. `install` **không đồng nghĩa** `deploy` lên repository từ xa.

**Chặng 7 — deploy (chỉ sau khi chuẩn bị repository thật):**

`mvn deploy` đi qua phase `deploy` và cố gắng tải artifact lên remote repository. Ví dụ POM trên **không có cấu hình địa chỉ repository/credentials**; vì vậy không kỳ vọng `mvn deploy` thành công trong môi trường mặc định. Cần `distributionManagement` hoặc cơ chế deploy phù hợp và quyền xác thực. Không dùng `deploy` chỉ để kiểm tra compile/test trong lần học đầu.

## 7. So sánh lệnh phase với lệnh gọi trực tiếp goal

Đây là phần dễ gây nhầm nhất.

| Lệnh | Loại yêu cầu | Phạm vi được Maven yêu cầu |
| --- | --- | --- |
| `mvn validate` | Phase của default | Tất cả phase từ đầu đến `validate`; chạy goal đã gắn |
| `mvn compile` | Phase của default | `validate` → ... → `compile` |
| `mvn compiler:compile` | Goal trực tiếp | Gọi goal `compile` của Compiler Plugin, **không yêu cầu chuỗi phase trước đó** |
| `mvn test` | Phase của default | `validate` → ... → `test`; gồm test-compile và goal test được gắn |
| `mvn surefire:test` | Goal trực tiếp | Gọi Surefire goal, không tự chạy toàn bộ phase đến `test` |
| `mvn package` | Phase của default | `validate` → ... → `package` |
| `mvn jar:jar` | Goal trực tiếp | Gọi JAR goal, có thể dùng output build đã có; không tự biên dịch/test |
| `mvn verify` | Phase của default | Đến `verify`, gồm `package` và các phase integration test trước đó |
| `mvn install` | Phase của default | Đến `install`, gồm `verify` |
| `mvn deploy` | Phase của default | Đến `deploy`, gồm `install` |
| `mvn clean` | Phase của clean | `pre-clean` → `clean` |
| `mvn clean:clean` | Goal trực tiếp | Chạy goal dọn của Clean Plugin, không tự chạy `pre-clean` |
| `mvn site` | Phase của site | `pre-site` → `site`; không tự gói JAR |
| `mvn clean package` | Hai phase thuộc hai lifecycle | Dọn trước, rồi chạy default đến `package` |

Ví dụ lỗi do hiểu sai:

~~~bash
mvn jar:jar
~~~

Nếu `target/classes` còn từ build cũ, goal có thể đóng gói **class cũ**; nếu thiếu class hay có cấu hình không phù hợp, goal có thể tạo JAR rỗng hoặc thất bại. Lệnh này không bảo đảm chạy compiler và unit test. Để tạo JAR từ nguồn hiện tại qua vòng đời Maven, nên dùng:

~~~bash
mvn clean package
~~~

Tương tự, `mvn surefire:test` khi chưa chạy `test-compile` có thể không có class test mới để chạy. `mvn test` là lựa chọn thông thường vì Maven tự đi qua các bước chuẩn bị theo thứ tự.

**Nhớ:** gọi phase có nghĩa **Maven đi theo lịch trình**, còn gọi trực tiếp goal có nghĩa **Maven thực hiện tác vụ được chỉ định**. Những goal trực tiếp đôi khi tự yêu cầu dữ liệu/dependency riêng, nhưng điều đó không làm chúng tương đương phase.

## 8. Vì sao gọi `mvn verify` thường an toàn hơn `mvn integration-test`?

Default lifecycle chứa ba phase liên quan kiểm thử tích hợp:

~~~text
pre-integration-test
integration-test
post-integration-test
verify
~~~

Nhóm này được thiết kế để plugin có thể **khởi tạo tài nguyên** (server/database), **chạy kiểm thử tích hợp**, **dọn môi trường**, rồi **đánh giá kết quả**.

Nếu bạn chỉ gọi:

~~~bash
mvn integration-test
~~~

Maven dừng ở `integration-test`, có thể **chưa chạy `post-integration-test` hoặc `verify`**. Khi dùng Maven Failsafe Plugin theo thiết kế phổ biến, goal `failsafe:integration-test` có thể ghi nhận kết quả để goal `failsafe:verify` kiểm tra sau. Do đó dừng sớm có nguy cơ không dọn môi trường đúng cách hoặc không báo thất bại test như bạn kỳ vọng.

Trong dự án có cấu hình integration test, lựa chọn thường dùng:

~~~bash
mvn clean verify
~~~

Nhưng đừng suy luận `verify` **mặc nhiên** chạy integration test: phải khai báo goal/plugin phù hợp, ví dụ Maven Failsafe Plugin gắn với `integration-test` và `verify`. Maven Surefire thông thường chạy unit test tại `test`, còn Failsafe hướng tới integration test khi được cấu hình.

## 9. Cách đọc log để thấy lifecycle, phase và goal

Ở log `mvn package` của ví dụ trên, bạn thường gặp những phần tương tự:

~~~text
--- maven-antrun-plugin:3.1.0:run (announce-validate) @ lifecycle-demo ---
...
--- maven-compiler-plugin:3.14.0:compile (default-compile) @ lifecycle-demo ---
...
--- maven-compiler-plugin:3.14.0:testCompile (default-testCompile) @ lifecycle-demo ---
...
--- maven-surefire-plugin:3.5.2:test (default-test) @ lifecycle-demo ---
...
--- maven-jar-plugin:3.4.2:jar (default-jar) @ lifecycle-demo ---
...
BUILD SUCCESS
~~~

Đây là **log minh họa rút gọn về các goal**, không phải toàn bộ stdout dự kiến. Maven còn chạy goal xử lý resources, có thể in thông tin tải dependency, cảnh báo và chi tiết test tùy môi trường.

Phân tích một dòng:

~~~text
maven-compiler-plugin:3.14.0:compile (default-compile) @ lifecycle-demo
~~~

- `maven-compiler-plugin`: plugin đang làm việc.
- `3.14.0`: phiên bản plugin.
- `compile`: **goal** bên trong plugin.
- `default-compile`: **execution id** (định danh lần chạy goal), không phải tên phase.
- `lifecycle-demo`: artifact/module Maven hiện tại.

Các dòng log ghi tên **goal/execution**, chứ không nhất thiết in một tiêu đề riêng cho từng phase. Để biết một goal được chạy tại phase nào, đối chiếu binding mặc định, cấu hình `<execution><phase>` và tài liệu goal. Đừng kết luận Maven “bỏ qua phase” chỉ vì log không có tên phase đó.

### 9.1. Quan sát kế hoạch hiệu lực

Các lệnh hữu ích:

~~~bash
mvn -version
mvn -B -ntp help:effective-pom
mvn -B -ntp help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
mvn -B -ntp validate
mvn -B -ntp test
mvn -B -ntp package
~~~

`help:effective-pom` cho thấy cấu hình POM sau kế thừa và kích hoạt profile (đầu ra có thể rất dài). `help:describe` cung cấp mô tả goal và cấu hình của plugin nếu Help Plugin được phân giải. Plugin đã gắn vào lifecycle qua packaging có thể có execution mặc định ngay cả khi bạn không viết `<execution>` tường minh trong POM.

Khi điều tra một build lạ, hãy đọc theo thứ tự:

1. Người dùng đã gọi **phase** hay **goal** nào?
2. Dự án có `packaging` gì?
3. Có `<executions>` hoặc parent POM/profile nào gắn thêm goal không?
4. Plugin đang chạy phiên bản nào? Goal nào, execution id nào xuất hiện?
5. Thời điểm lỗi nằm ở phase nào, và đầu vào của goal đã được tạo trước đó chưa?

## 10. Plugin, pluginManagement và execution: ba mức cấu hình

Ví dụ:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

`pluginManagement` quản lý phiên bản/cấu hình plugin cho nơi sử dụng hoặc nơi packaging mặc định đã dùng nó. Nó **không tự tạo execution mới** chỉ vì plugin được liệt kê ở đó.

Trong `<build><plugins>`, plugin-level `<configuration>` thường là phần cấu hình chung cho plugin. Các phần tử `<executions><execution>` dùng để gắn goal và/hoặc cấu hình riêng cho một lần chạy.

Ví dụ hai lần chạy khác nhau của cùng một goal ở hai phase:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>mark-validate</id>
            <phase>validate</phase>
            <goals><goal>run</goal></goals>
            <configuration>
                <target><echo message="Entering validate"/></target>
            </configuration>
        </execution>
        <execution>
            <id>mark-verify</id>
            <phase>verify</phase>
            <goals><goal>run</goal></goals>
            <configuration>
                <target><echo message="Entering verify"/></target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là đoạn đặt trong `<build><plugins>`, minh họa riêng **không ghép thêm vào POM ở mục 6** nếu bạn chỉ muốn bài thực hành cơ bản. Khi chạy `mvn verify`, execution thứ nhất diễn ra ở `validate`, execution thứ hai ở `verify`. Khi chạy `mvn test`, chỉ execution `mark-validate` chạy vì Maven dừng trước `verify`.

Nếu có nhiều execution cùng một id trong quan hệ parent/child, cấu hình có thể được merge/override theo quy tắc Maven. Dùng id rõ nghĩa và kiểm tra effective POM giúp tránh việc thay đổi lifecycle ngoài ý muốn.

## 11. Những điều lifecycle không tự bảo đảm

| Điều thường bị hiểu sai | Thực tế cần kiểm tra |
| --- | --- |
| “`mvn test` chạy mọi loại test.” | Surefire chạy unit test đã được khám phá; integration test có thể cần Failsafe/goal riêng. |
| “`mvn verify` chắc chắn kiểm tra mọi chuẩn chất lượng.” | Chỉ các kiểm tra thực sự được gắn goal/plugin và test hiện có mới chạy. |
| “`mvn package` luôn tạo executable JAR.” | JAR thường có thể thiếu `Main-Class`, dependency đi kèm và cấu hình chạy. |
| “`mvn install` là đưa ứng dụng lên máy chủ.” | `install` ghi artifact vào **local Maven repository** của máy build. |
| “`mvn deploy` triển khai ứng dụng đang chạy.” | Trong Maven core, `deploy` thường là **xuất bản artifact lên repository**, không phải deploy ứng dụng lên máy chủ. |
| “`mvn clean` xóa mọi cache và dependency.” | Clean Plugin mặc định dọn output build, không xóa `~/.m2/repository`. |
| “Khai báo plugin trong POM tức là nó chạy mọi lần build.” | Cần default binding hoặc `<executions>` phù hợp; gọi trực tiếp goal là trường hợp khác. |
| “Gọi `compiler:compile` sẽ đi qua `validate`.” | Goal gọi trực tiếp không tự chạy toàn bộ lifecycle phía trước. |
| “Mỗi phase có đúng một goal.” | Phase có thể có 0, 1 hoặc nhiều goal. |
| “`<scope>test</scope>` là phase `test`.” | Dependency scope là quy tắc classpath, độc lập với tên phase. |

Một dự án đa module còn có **reactor**: Maven xác định thứ tự xây các module dựa trên quan hệ dependency và chạy goal/phase trong phạm vi từng module cần thiết. Đừng hình dung mọi module luôn chạy phase `compile` cùng lúc rồi mới tới phase `test`. Khi xem log hãy chú ý phần `@ module-name` để biết goal đang thực hiện trên module nào.

## 12. Lỗi và phương pháp xử lý

### 12.1. Chạy `mvn compiler:compile` nhưng tài nguyên hoặc mã sinh ra bị thiếu

**Nguyên nhân:** gọi trực tiếp compiler goal, trong khi dự án cần `process-resources` hoặc `generate-sources` trước đó.

**Khắc phục:** chạy phase `mvn compile` để Maven đi qua các phase chuẩn bị; kiểm tra plugin generate-sources đã được gắn đúng phase.

### 12.2. `mvn test` không tìm thấy test nào nhưng vẫn báo thành công

**Nguyên nhân:** thiếu source test, tên/lớp test không khớp quy tắc discovery, không có test engine hoặc Surefire chưa được cấu hình phù hợp.

**Khắc phục:** kiểm tra `src/test/java`, tên test, annotation, dependency JUnit, Surefire plugin version; đọc báo cáo dưới `target/surefire-reports`. Không coi “BUILD SUCCESS” khi không có test là bằng chứng đã có kiểm thử thực sự.

### 12.3. `mvn package` tạo JAR nhưng chạy `java -jar` báo thiếu Main-Class

**Nguyên nhân:** `jar:jar` chỉ tạo archive thông thường, không tự suy luận lớp main và cách ghép dependency.

**Khắc phục:** cấu hình manifest `Main-Class` hoặc plugin đóng gói phù hợp; với ví dụ Java thuần ở mục 6, chạy `java -cp target/classes dev.example.App`.

### 12.4. Plugin khai báo rồi nhưng không chạy

**Nguyên nhân:** chỉ khai báo plugin trong `<plugins>` mà chưa có goal/execution, goal không có default phase, execution gắn phase sau phase đích, hoặc plugin nằm trong profile chưa kích hoạt.

**Khắc phục:** xem `<executions>`, `<phase>`, `<goals>` và `help:effective-pom`; kiểm tra log goal thực tế. Nếu chỉ để trong `pluginManagement`, đừng hiểu đó là một lệnh chạy plugin.

### 12.5. Goal chạy hai lần hoặc chạy sai thứ tự

**Nguyên nhân:** goal đã được packaging gắn mặc định, sau đó lại được thêm trong `<executions>`, hoặc parent và child cùng khai báo executions.

**Khắc phục:** đọc danh sách goal/execution id trong log, effective POM và packaging binding. Loại execution trùng không cần thiết hoặc tách id/cấu hình rõ ràng; không đổi phase tùy tiện khi chưa hiểu đầu vào/đầu ra của goal.

### 12.6. `mvn integration-test` chạy xong nhưng môi trường chưa được dọn

**Nguyên nhân:** bạn dừng trước `post-integration-test`.

**Khắc phục:** cấu hình đầy đủ quy trình và chạy `mvn verify` để đi qua các phase sau test, có plugin Failsafe/check kết quả phù hợp.

### 12.7. `mvn install` thành công trên máy A, máy B vẫn không có dependency

**Nguyên nhân:** `install` chỉ ghi vào local repository của máy A, không phát hành artifact lên repository chung.

**Khắc phục:** dùng remote repository và `deploy` khi dự án thực sự cần chia sẻ binary; hoặc build các module cùng reactor nếu chúng thuộc một dự án.

### 12.8. `mvn deploy` báo thiếu thông tin repository

**Nguyên nhân:** không có `distributionManagement` hoặc cấu hình deploy phù hợp, hay thiếu quyền xác thực.

**Khắc phục:** đối chiếu URL repository, repository id, `settings.xml` và quyền truy cập. Không đưa mật khẩu/token trực tiếp vào POM hoặc Git.

### 12.9. Build dùng Maven khác phiên bản nên goal mặc định khác

**Nguyên nhân:** phiên bản Maven, plugin mặc định, parent POM hoặc profile khác nhau.

**Khắc phục:** dùng Maven Wrapper của dự án, khai báo phiên bản plugin quan trọng trong POM/pluginManagement và so sánh log/effective POM. `mvn -version` hoặc `./mvnw -version` là bằng chứng bước đầu.

## 13. Lựa chọn lệnh phù hợp với mục tiêu

| Bạn muốn | Lệnh thường phù hợp | Vì sao |
| --- | --- | --- |
| Kiểm tra cấu hình cơ bản cùng goal được gắn ở `validate` | `mvn validate` | Dừng sớm, chưa yêu cầu compile/test |
| Biên dịch nguồn Java chính | `mvn compile` | Chạy cả phase chuẩn bị cần thiết trong lifecycle |
| Biên dịch và chạy unit tests | `mvn test` | Đi qua `test-compile` và `test` |
| Tạo JAR/WAR qua quy trình chuẩn | `mvn package` | Bao gồm các phase trước đóng gói |
| Dọn output rồi build và thực hiện các kiểm chứng đã cấu hình | `mvn clean verify` | Thực hiện cả clean lifecycle và default đến verify |
| Chia sẻ artifact cho dự án khác trên **cùng máy** | `mvn install` | Cài artifact vào local repository |
| Xuất bản artifact lên repository chung | `mvn deploy` | Cần cấu hình remote và quyền |
| Sinh tài liệu site | `mvn site` | Dùng site lifecycle; tách khỏi đóng gói app |
| Thử riêng một goal để chẩn đoán | `mvn plugin:goal` | Không tự yêu cầu chạy các phase trước |
| Dùng đúng bản Maven của repository | `./mvnw clean verify` (Unix) hoặc `.\mvnw.cmd clean verify` (Windows) | Maven Wrapper chọn bản Maven do dự án khai báo; JDK vẫn cần phù hợp |

Nếu tài liệu dự án bảo chạy `mvn clean install`, hãy hiểu rằng lệnh này có cả dọn output, compile, test, package, verify và cài artifact vào local repository. Không cần gọi `mvn compile`, `mvn test`, `mvn package` lặp lại trước đó chỉ để đạt những phase đã nằm trong đường đi tới `install`.

## 14. Thực hành suy luận: đoán log trước khi chạy

Với POM ở mục 6, đánh giá các nhận định sau:

1. `mvn validate` sẽ chạy marker `announce-validate`? **Có**, vì goal Antrun gắn vào phase `validate`.
2. `mvn compile` có chạy marker `announce-validate` không? **Có**, vì `validate` đứng trước `compile` trong default lifecycle.
3. `mvn clean` có chạy marker `announce-validate` không? **Không**, vì `clean` thuộc lifecycle khác.
4. `mvn test` có tạo JAR mới ở `package` không? **Không bắt buộc**, vì dừng ở `test` trước `package`.
5. `mvn package` có chạy `CalculatorTest` không? **Có**, nếu Surefire và test class được cấu hình đúng, vì `test` đứng trước `package`.
6. `mvn jar:jar` có tự chạy `CalculatorTest` không? **Không**, đó là lệnh gọi goal JAR trực tiếp.
7. `mvn verify` có tự deploy artifact lên repository chung không? **Không**, `deploy` nằm sau `verify`.
8. `mvn install` có cài artifact vào local repository không? **Có**, với lifecycle và Install Plugin được cấu hình/hoạt động đúng.
9. Dự án `packaging=pom` có mặc định tạo JAR ở `package` như `packaging=jar` không? **Không**, mapping phụ thuộc packaging.
10. Gọi `mvn compiler:compile` và `mvn compile` có tương đương mọi trường hợp không? **Không**; một bên là goal trực tiếp, một bên là phase đi qua các bước trước.
11. Một phase `verify` không có goal ràng buộc có thể đi qua thành công không? **Có**, thành công của phase không tự chứng minh bộ kiểm tra cụ thể tồn tại.
12. `mvn clean verify` có tương đương `mvn verify clean` về thứ tự không? **Không nên coi tương đương**; các tác vụ trên dòng lệnh được thực hiện theo thứ tự yêu cầu, và dọn cuối có thể xóa output vừa tạo.

**Bài mở rộng:** Trong POM ví dụ, đổi `<phase>validate</phase>` của Antrun thành `<phase>verify</phase>` rồi lần lượt chạy `mvn test` và `mvn verify`. Xem marker xuất hiện ở lệnh nào. Sau đó hoàn nguyên cấu hình. Bài này chứng minh phase quyết định **khi nào** goal được thực hiện.

## 15. Checklist để tránh nhầm lifecycle, phase và goal

- [ ] Đã biết lệnh đang gọi **phase** hay **plugin goal**.
- [ ] Đã biết phase thuộc lifecycle `default`, `clean` hay `site`.
- [ ] Hiểu Maven chạy qua **các phase trước** khi gọi một phase đích.
- [ ] Biết dự án dùng `<packaging>` nào và goal mặc định ở `compile`, `test`, `package` là gì.
- [ ] Biết các goal tự thêm trong `<executions>` chạy ở phase nào.
- [ ] Không mặc định một phase luôn có goal và không mặc định một phase chỉ có một goal.
- [ ] Không nhầm `mvn test` với `mvn surefire:test` hoặc `mvn package` với `mvn jar:jar`.
- [ ] Đã kiểm tra thực tế số test được chạy, output JAR và repository đích.
- [ ] Với integration test, dùng quy trình có đủ phase teardown và verify thích hợp.
- [ ] Đã đọc log plugin/version/goal/execution id và effective POM khi nghi ngờ binding.
- [ ] Đã cố định phiên bản plugin quan trọng và dùng Maven Wrapper khi cần kết quả nhất quán giữa môi trường.

## 16. Tài liệu chính thức

1. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — định nghĩa lifecycle, phase, goal, default/clean/site và packaging binding.
2. [Apache Maven — Running Maven](https://maven.apache.org/run.html) — cú pháp `mvn [options] [goals] [phases]` và các lệnh phổ biến.
3. [Apache Maven Core — Lifecycles Reference](https://maven.apache.org/ref/3-LATEST/maven-core/lifecycles.html) — thứ tự phase của từng lifecycle.
4. [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html) — cấu hình plugin, goal và execution/phase.
5. [Apache Maven — Guide to Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html) — execution mặc định và cấu hình mức plugin/execution.
6. [Maven Compiler Plugin — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html) — goal biên dịch và default phase.
7. [Maven Antrun Plugin 3.1.0 — Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html) — ví dụ binding `antrun:run` trong lifecycle.
