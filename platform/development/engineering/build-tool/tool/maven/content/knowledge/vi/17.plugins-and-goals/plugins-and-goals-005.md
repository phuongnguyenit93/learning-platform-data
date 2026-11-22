# Plugin goal được gọi trực tiếp và goal được gắn vào vòng đời Maven

## 1. Mục tiêu học tập

Sau bài này, bạn có thể giải thích sự khác biệt giữa **gọi một Maven plugin goal trực tiếp** và **để Maven gọi goal khi thực thi một build phase**, đọc cấu hình `<executions>`, nhận ra execution ID trong log và lựa chọn lệnh đúng khi build/test/phát hành dự án.

Hai lệnh sau **không tương đương về quy trình**:

~~~bash
mvn compiler:compile
mvn compile
~~~

Ở lệnh đầu, `compiler:compile` là **goal** của Maven Compiler Plugin được gọi trực tiếp. Ở lệnh sau, `compile` là **phase** trong default lifecycle. Maven đi qua các phase từ đầu vòng đời đến `compile`, gọi mọi goal đã được gắn vào những phase ấy.

Với project `jar` thông thường, `mvn compile` có thể thực hiện `resources:resources` ở `process-resources` rồi mới `compiler:compile`. Còn `mvn compiler:compile` không mặc nhiên xử lý các resource hoặc goal tạo source đã được bind ở các phase trước. Đôi khi cả hai vẫn tạo được cùng một file `.class` trong dự án đơn giản; kết quả giống nhau **không chứng minh cách thực thi giống nhau**.

Điều tương tự xảy ra với:

~~~bash
mvn surefire:test
mvn test
~~~

`mvn test` đi theo lifecycle, thường bao gồm biên dịch mã chính, biên dịch test và chạy Surefire. Gọi riêng `surefire:test` thường không tự tạo lại test classes từ mã nguồn; nếu project vừa được `clean`, lệnh có thể không tìm thấy test để chạy hoặc thất bại tùy cấu hình. Do đó **thành công của một goal được gọi trực tiếp không có nghĩa toàn bộ lifecycle đã qua kiểm tra**.

## 2. Ba khái niệm phải phân biệt

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Lifecycle** | Chuỗi có trật tự các phase phục vụ một quy trình build | `default`, `clean`, `site` |
| **Phase** | Mốc trong lifecycle, nơi một hay nhiều goal có thể được gắn vào | `compile`, `test`, `package`, `verify` |
| **Plugin goal (Mojo)** | Hành động cụ thể do Maven plugin thực thi | `compiler:compile`, `surefire:test`, `jar:jar` |
| **Plugin execution** | Cấu hình xác định các goal, phase và tham số cho một lần thực thi | `<execution><id>verify-jar</id>...` |
| **Binding** | Mối liên hệ khiến goal được Maven gọi khi đến phase | `jar:jar` ở `package` cho packaging `jar` |

Maven plugin có thể chứa nhiều goals. Maven Compiler Plugin có `compile` và `testCompile`; Maven Resources Plugin có `resources` và `testResources`. Tên goal và tên phase có thể trùng một phần nhưng **không có quan hệ một-một**.

Trong POM, `<build><plugins>` là nơi khai báo/cấu hình plugin; `<executions>` là nơi thường dùng để **gắn goal vào phase**. Còn `<pluginRepositories>` chỉ mô tả nơi Maven có thể tìm plugin, không phải nơi gắn goal vào lifecycle.

## 3. Maven đi qua những phase nào?

Maven có ba lifecycle tích hợp: `clean`, `default` và `site`. Chuỗi dưới đây là các mốc chính của **default lifecycle**, không phải toàn bộ phase:

~~~text
validate
   ↓
process-resources
   ↓
compile
   ↓
process-test-resources
   ↓
test-compile
   ↓
test
   ↓
package
   ↓
pre-integration-test
   ↓
integration-test
   ↓
post-integration-test
   ↓
verify
   ↓
install
   ↓
deploy
~~~

Giữa những mốc trên còn nhiều phase như `initialize`, `generate-sources`, `process-sources` và `prepare-package`. Một phase có thể có **không, một hoặc nhiều goal**. Maven đến một phase không có goal được bind thì không tự thực thi một phép kiểm tra đặc biệt.

Khi chạy:

~~~bash
mvn verify
~~~

Maven đi qua những phase của default lifecycle đến `verify` và thực thi các goal đã được bind. Khi chạy:

~~~bash
mvn clean verify
~~~

Maven thực thi clean lifecycle đến `clean` rồi default lifecycle đến `verify`. `clean` là phase của một lifecycle **khác**, không phải phase đứng trước `validate` trong default lifecycle.

## 4. Mapping mặc định phụ thuộc packaging

Với `<packaging>jar</packaging>`, Maven cung cấp các binding thông dụng:

| Phase | Goal thường được gọi |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |
| `install` | `install:install` |
| `deploy` | `deploy:deploy` |

Với JAR project thông thường, phase `verify` **không tự chạy mọi loại scanner/integration test chỉ vì tên phase mang nghĩa kiểm chứng**. Muốn kiểm tra độ phủ, integration tests hoặc quy tắc chất lượng, dự án cần plugin/goals phù hợp được cấu hình và bind.

Packaging khác sẽ có mapping khác. `war` có goal đóng gói WAR, còn `pom` không mặc nhiên biên dịch Java và tạo JAR. Vì vậy đừng khẳng định rằng mọi `mvn package` đều gọi `jar:jar`.

Các binding mặc định cũng có **execution ID**. Ví dụ compiler goal trong packaging JAR thường hiện dưới ID `default-compile`, Surefire là `default-test`, JAR plugin là `default-jar`. ID giúp chẩn đoán đó là một goal được gọi từ mapping hay từ execution tự đặt.

## 5. Cú pháp gọi goal trực tiếp

Dạng thường gặp:

~~~bash
mvn compiler:compile
mvn surefire:test
mvn dependency:tree
mvn help:effective-pom
~~~

Trong `compiler:compile`, `compiler` là plugin prefix và `compile` là goal name. Maven phải tìm được plugin phù hợp từ metadata, plugin group, plugin repositories và POM.

Muốn ghi rõ cả version:

~~~bash
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile
~~~

Cú pháp tổng quát:

~~~text
groupId:artifactId:version:goal
~~~

Đây vẫn là **gọi goal trực tiếp**, không biến thành phase `compile`. Dùng fully qualified goal hữu ích khi muốn tránh nhầm plugin prefix/version; nó không thay thế các phase prerequisite của project.

Một số goal chẩn đoán như `dependency:tree`, `help:effective-pom` có ích khi gọi riêng. Những goal xử lý artifact như `jar:jar` hoặc chạy test như `surefire:test` thường phụ thuộc vào đầu ra của những bước trước; gọi trực tiếp từ trạng thái sạch có thể cho kết quả không đầy đủ.

## 6. Gắn goal vào lifecycle bằng `<executions>`

Một plugin được khai báo trong `<build><plugins>` **không nhất thiết tự chạy**. Để bảo đảm một goal chạy khi đến phase cụ thể, thường khai báo execution:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>verify-jar</id>
            <phase>verify</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <available
                        file="${project.build.directory}/${project.build.finalName}.jar"
                        property="jar.ready"/>
                    <fail unless="jar.ready"
                          message="Expected JAR is missing"/>
                    <echo message="VERIFY-JAR: expected archive exists"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **đoạn XML bên trong `<build><plugins>`**, chưa phải POM độc lập. Maven Antrun Plugin có goal `antrun:run`, cho phép chạy Ant tasks. Trong đoạn trên:

- `<id>verify-jar</id>` đặt tên execution để dễ nhận diện và chọn cấu hình.
- `<phase>verify</phase>` là thời điểm Maven tự gọi goal trong lifecycle.
- `<goals><goal>run</goal></goals>` chỉ định thực thi `antrun:run`.
- `<target>` gồm ba Ant tasks: `available` xem JAR có tồn tại, `fail` dừng build nếu không có, `echo` in xác nhận nếu có.
- `${project.build.directory}` và `${project.build.finalName}` là các giá trị model Maven; theo POM demo sẽ trỏ tới `target/goal-lifecycle-lab-1.0.0.jar`.

**Cảnh báo phạm vi:** check này chỉ chứng minh **file JAR có mặt**, chưa chứng minh JAR đúng nội dung, dependency an toàn hay integration tests đạt yêu cầu. Mục đích là minh họa rõ binding/phase và direct invocation.

Trong `mvn verify` của JAR project, goal đóng gói JAR thường chạy ở `package` trước khi `verify-jar` kiểm tra. Nhưng gọi riêng `antrun:run` **không có nghĩa Maven tự chạy tới `package`**.

## 7. Dự án Java 17 hoàn chỉnh để thực hành

Ta dùng project đơn giản có một class chính, một bài JUnit test và execution kiểm tra JAR ở phase `verify`. Cấu trúc:

~~~text
goal-lifecycle-lab/
├── pom.xml
└── src/
    ├── main/java/demo/goals/App.java
    └── test/java/demo/goals/AppTest.java
~~~

Yêu cầu JDK 17+, Maven 3.9+ hoặc Maven tương thích với các plugin đã khai báo, cùng khả năng tải artifact từ Maven Central/repository được cấu hình. Các phiên bản plugin dưới đây là **version ví dụ đã cố định**, không phải khẳng định bản mới nhất.

### 7.1. Toàn bộ `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.goals</groupId>
    <artifactId>goal-lifecycle-lab</artifactId>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>verify-jar</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <available
                                    file="${project.build.directory}/${project.build.finalName}.jar"
                                    property="jar.ready"/>
                                <fail unless="jar.ready"
                                      message="Expected JAR is missing"/>
                                <echo message="VERIFY-JAR: expected archive exists"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM này có các plugin Compiler, Surefire và JAR cho lifecycle mặc định; AntRun có execution riêng tại `verify`. Maven dùng Compiler Plugin để biên dịch Java 17 và Surefire chạy test JUnit 5. Plugin AntRun chỉ dùng cho bước kiểm tra file demo.

### 7.2. `src/main/java/demo/goals/App.java`

~~~java
package demo.goals;

public final class App {
    private App() {
    }

    public static String greet(String name) {
        return "Hello, " + name.trim();
    }

    public static void main(String[] args) {
        System.out.println(greet("Maven"));
    }
}
~~~

Class chỉ dùng thư viện chuẩn JDK, giúp người học chạy được trực tiếp từ `target/classes` sau khi compile mà không cần lắp thêm runtime JAR.

### 7.3. `src/test/java/demo/goals/AppTest.java`

~~~java
package demo.goals;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void greetsWithNormalizedName() {
        assertEquals("Hello, Maven", App.greet(" Maven "));
    }
}
~~~

Unit test thuộc `src/test/java`. JUnit Jupiter dùng scope `test`, không phải dependency runtime thông thường của `App.main`.

## 8. Thử nghiệm A: gọi trực tiếp Compiler Plugin

Từ thư mục chứa POM:

~~~bash
mvn -B -ntp clean compiler:compile
~~~

Lệnh thực hiện clean lifecycle rồi gọi **một goal** `compiler:compile`:

1. `clean` xóa output cũ trong `target` theo cấu hình thông thường.
2. `compiler:compile` biên dịch mã trong `src/main/java`.
3. Goal testCompile, Surefire, JAR Plugin và AntRun execution ở verify **không được lệnh này yêu cầu**.

Dự kiến file `target/classes/demo/goals/App.class` được tạo. Từ trạng thái clean, **chưa có** `target/test-classes/demo/goals/AppTest.class` và `target/goal-lifecycle-lab-1.0.0.jar`.

Chạy chương trình:

~~~bash
java -cp target/classes demo.goals.App
~~~

**Stdout chính xác của ứng dụng:**

~~~text
Hello, Maven
~~~

`mvn compiler:compile` **không tự gọi** `App.main`; dòng này đến từ lệnh `java` riêng. Trong project demo không cần generated resources, direct goal đủ biên dịch App. Nhưng với project có source generation ở `generate-sources` hoặc resource filtering ở `process-resources`, gọi riêng compiler có thể bỏ sót đầu vào quan trọng.

## 9. Thử nghiệm B: gọi phase `compile`

~~~bash
mvn -B -ntp clean compile
~~~

Lệnh yêu cầu clean lifecycle rồi default lifecycle đến `compile`. Với packaging `jar`, Maven thường đi qua `process-resources` và gọi `resources:resources` trước `compiler:compile`.

Bảng đối chiếu từ một project clean:

| Kết quả | `mvn clean compiler:compile` | `mvn clean compile` |
| --- | --- | --- |
| Xóa output cũ | Có | Có |
| Gọi goal `compiler:compile` | Có | Có (theo lifecycle binding) |
| Thực thi các goals đã bind trước phase `compile` | Không mặc nhiên | Có |
| Chạy JUnit test | Không | Không |
| Đóng gói JAR | Không | Không |
| AntRun execution ở `verify` | Không | Không |

Đối với ví dụ không có resource, hai lệnh có thể tạo `App.class` giống nhau. **Sự khác biệt nằm ở execution plan**, không nhất thiết nằm ở nội dung class trong ví dụ nhỏ.

## 10. Thử nghiệm C: phase `test`, `package`, `verify`

Chạy từng lệnh sau **riêng biệt** để so từ trạng thái sạch:

~~~bash
mvn -B -ntp clean test
mvn -B -ntp clean package
mvn -B -ntp clean verify
~~~

### 10.1. `mvn clean test`

Maven thực thi những binding trước và tại phase `test`: main compile, test compile và Surefire. Unit test `greetsWithNormalizedName` PASS.

Một đoạn kết quả test dự kiến:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Maven chưa đến `package` và `verify`, nên không yêu cầu tạo JAR, cũng không gọi execution `verify-jar`.

### 10.2. `mvn clean package`

Maven chạy các phase đến `package`:

- Chạy compilation và test như trên.
- Maven JAR Plugin đóng gói `target/goal-lifecycle-lab-1.0.0.jar`.
- **Không tự chạy** AntRun execution vì nó được bind ở phase `verify`, nằm **sau** `package`.

Đây là ví dụ vì sao “đã có file JAR” không tương đương “mọi bước kiểm chứng sau khi đóng gói đều đã chạy”.

### 10.3. `mvn clean verify`

Maven chạy các phase đến `verify`, nên trong project demo:

- Compiler tạo `App.class` và test class.
- Surefire chạy một JUnit test.
- JAR Plugin tạo JAR.
- AntRun execution `verify-jar` được gọi; `available` tìm thấy file, `fail` không kích hoạt và `echo` in:

~~~text
[echo] VERIFY-JAR: expected archive exists
~~~

Dòng này thuộc **log của AntRun**, không phải stdout của `App.main`. Dấu `[echo]` là dạng hiển thị thường gặp; Maven còn in thông tin plugin/version/timing. Nếu các bước thành công, lệnh kết thúc bằng `BUILD SUCCESS`.

### 10.4. Bảng ghi nhớ

| Lệnh từ trạng thái clean | Main compile | Chạy test | Tạo JAR | Chạy `verify-jar` |
| --- | :---: | :---: | :---: | :---: |
| `mvn clean compile` | Có | Không | Không | Không |
| `mvn clean test` | Có | Có | Không | Không |
| `mvn clean package` | Có | Có | Có | Không |
| `mvn clean verify` | Có | Có | Có | Có |

Bảng chỉ áp dụng cho **cấu hình project demo**. Một POM khác có thể bind additional goals ở bất kỳ phase nào hoặc dùng packaging khác.

## 11. Thử nghiệm D: gọi trực tiếp goal đã được bind ở `verify`

Đây là phần bộc lộ sự khác biệt rõ nhất. AntRun goal có cấu hình riêng trong execution `verify-jar`. Từ Maven 3.3.1, Maven hỗ trợ cú pháp **`goal@executionId`** khi gọi goal trực tiếp:

~~~bash
mvn -B -ntp clean antrun:run@verify-jar
~~~

Lệnh có thứ tự:

1. Chạy clean lifecycle đến `clean`, xóa JAR từ lần build trước.
2. Gọi riêng `antrun:run`, lấy cấu hình của execution có ID `verify-jar`.
3. Không yêu cầu default lifecycle tới `package` nên JAR chưa tồn tại.
4. Ant task `available` không đặt property `jar.ready`; `fail unless="jar.ready"` làm goal thất bại.

Đoạn thông báo lỗi **dự kiến**:

~~~text
Expected JAR is missing
BUILD FAILURE
~~~

Đây là lỗi **được thiết kế có chủ ý** trong ví dụ. Nó không chứng tỏ POM hỏng; nó chứng minh rằng `@verify-jar` **chỉ chọn cấu hình execution, không tự chạy tới phase `verify`**.

Sau đó chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Kết quả dự kiến là `BUILD SUCCESS`, vì Maven đã tạo JAR trong phase `package` trước khi execution AntRun ở `verify` kiểm tra.

### Vậy `mvn antrun:run` không có `@verify-jar` thì sao?

~~~bash
mvn -B -ntp antrun:run
~~~

Trong ví dụ, `<target>` chỉ nằm trong execution `verify-jar`, không có plugin-level `<configuration>` hoặc execution `default-cli`. Vì vậy **không được giả định** lệnh này chạy logic kiểm tra JAR. AntRun Plugin 3.1.0 có thể chạy goal mà không có `<target>` cấu hình và khi đó không thực hiện Ant task hữu ích.

Phân biệt:

- `mvn verify`: Maven đi theo lifecycle và **tự gọi** execution `verify-jar` tại phase `verify`.
- `mvn antrun:run@verify-jar`: Maven **gọi trực tiếp** goal cùng cấu hình execution ấy, **không tự đi qua các phase trước**.
- `mvn antrun:run`: Maven **gọi trực tiếp** goal nhưng sử dụng cấu hình CLI/định nghĩa chung, không tự lấy cấu hình của execution ID khác.

## 12. `default-cli` và `default-compile`

Maven dùng execution ID để xác định cấu hình cho từng lần gọi:

- **`default-cli`**: ID dành cho goal được gọi trực tiếp từ command line khi không chỉ rõ execution ID.
- **`default-<goalName>`**: ID cho goal được bind từ default lifecycle mapping của packaging. Ví dụ `default-compile` cho `compiler:compile` và `default-testCompile` cho `compiler:testCompile`.
- **ID tự đặt**: ví dụ `verify-jar`, `check-style`, `integration-test`.

Đây là các ID **của execution**, không phải tên phase. Trong Maven log, một dòng có thể gần như:

~~~text
--- compiler:3.13.0:compile (default-compile) @ goal-lifecycle-lab ---
--- antrun:3.1.0:run (verify-jar) @ goal-lifecycle-lab ---
~~~

Mẫu trên chỉ minh họa cách nhận diện, không phải transcript từ một lần chạy cụ thể. Version/format và plugin khác có thể làm log khác.

### Ví dụ cấu hình CLI riêng

Đoạn XML dưới đây là **một cấu hình thay thế để minh họa**, không nên ghép nguyên vào POM hoàn chỉnh ở mục 7 nếu chưa hiểu tác động:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>default-cli</id>
            <configuration>
                <target>
                    <echo message="DIRECT INVOCATION"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Khi gọi trực tiếp `antrun:run`, Maven có thể lấy cấu hình `default-cli` để in `DIRECT INVOCATION`. Nhưng chỉ có execution `default-cli` **không tự bind goal vào phase `verify`**.

`default-cli` thường hữu ích khi muốn tham số của một goal khác đi giữa cách gọi trực tiếp và cách gọi từ lifecycle mà không phải sao chép cả POM.

## 13. Plugin-level config khác execution-level config

Hai vị trí quan trọng:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>

    <configuration>
        <target>
            <echo message="PLUGIN-LEVEL"/>
        </target>
    </configuration>

    <executions>
        <execution>
            <id>bound-check</id>
            <phase>verify</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="EXECUTION-LEVEL"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đoạn này chỉ để học cách cấu hình, **không thay thế trực tiếp POM demo**. Thông thường:

- Plugin-level `<configuration>` đặt tham số chung cho các invocation của plugin.
- Execution-level `<configuration>` chứa các tham số riêng của execution được chọn.
- Maven merge cấu hình theo quy tắc model/Plexus configuration; một số phần tử có thể được hợp nhất thay vì chỉ thay cả khối.
- Khi parent/child POM cùng cấu hình plugin, inheritance và execution ID có thể thay đổi cấu hình hiệu lực.

**Không kết luận mọi execution-level config tự được áp dụng khi gọi `plugin:goal`.** Với direct invocation thông thường, hãy tìm `default-cli`/plugin-level hoặc gọi `goal@executionId` có chủ đích.

## 14. Binding theo packaging, POM execution và default phase

Có ít nhất ba nguồn khiến goal chạy khi đến một phase:

1. **Default lifecycle mapping theo packaging**. Với `jar`, Maven đã bind `compiler:compile` vào phase `compile`.
2. **Execution khai báo phase trong POM**. Ví dụ `<phase>verify</phase>` cùng `antrun:run` trong bài.
3. **Default phase từ goal descriptor**, khi một execution hợp lệ khai báo goal có defaultPhase mà không tự nêu `<phase>`.

Trường hợp thứ ba dễ nhầm. Một goal có default phase trong metadata **không đồng nghĩa nó tự chạy trong mọi dự án chỉ vì plugin có mặt trong POM**. Phải có execution/binding hợp lệ hoặc lời gọi trực tiếp phù hợp.

Đừng tự viết:

~~~xml
<execution>
    <id>my-check</id>
    <goals><goal>check</goal></goals>
</execution>
~~~

rồi mặc nhiên khẳng định goal `check` sẽ chạy ở `verify`. Trước hết phải biết plugin nào cung cấp goal `check`, metadata default phase của goal đó và execution có được Maven bind hay không. Khi muốn một mốc cụ thể, khai báo `<phase>` rõ ràng thường dễ kiểm tra hơn.

## 15. Một phase có thể gọi nhiều goals

Không có quy tắc “một phase chỉ chạy một goal”. Ví dụ nhiều executions trên cùng phase (đây là đoạn nằm trong một plugin đã định nghĩa):

~~~xml
<executions>
    <execution>
        <id>check-first</id>
        <phase>verify</phase>
        <goals><goal>run</goal></goals>
        <configuration>
            <target><echo message="FIRST"/></target>
        </configuration>
    </execution>
    <execution>
        <id>check-second</id>
        <phase>verify</phase>
        <goals><goal>run</goal></goals>
        <configuration>
            <target><echo message="SECOND"/></target>
        </configuration>
    </execution>
</executions>
~~~

Maven có thể thực thi `antrun:run` hai lần tại `verify`, mỗi lần với ID và target khác nhau. Mỗi execution ID phải là duy nhất **trong cùng plugin declaration**. Khi kế thừa parent/child, các execution cùng ID có thể được merge/override theo quy tắc Maven.

Nếu muốn sử dụng một plugin hai lần, không nên khai báo trùng plugin thành hai entry độc lập trong `<build><plugins>`. Cách rõ ràng là **một plugin với nhiều executions**.

Thứ tự giữa các goal ở cùng phase có thể chịu ảnh hưởng của default bindings, thứ tự khai báo và inheritance. Khi thứ tự thật sự quan trọng, hãy kiểm tra lifecycle execution plan và log trên Maven đang dùng, không suy ra từ một trích đoạn POM chưa có context.

## 16. Trộn phase và goal trên một command line

Maven cho phép:

~~~bash
mvn clean dependency:tree package
~~~

Thứ tự thực thi là:

1. Chạy clean lifecycle đến `clean`.
2. Gọi trực tiếp goal `dependency:tree`.
3. Chạy default lifecycle đến `package`.

Một lệnh khác:

~~~bash
mvn clean package dependency:tree
~~~

sẽ gọi `dependency:tree` **sau** bước đóng gói. Sự khác biệt có thể quan trọng đối với goal cần output từ bước trước.

Đừng nhầm `mvn package clean` với `mvn clean package`. Lệnh đầu có thể tạo JAR rồi xóa output sau đó, vì yêu cầu phase theo thứ tự không mong muốn.

Đồng thời không cần chạy `mvn compile test` nếu mục tiêu chỉ là đến phase `test`: `mvn test` đã đi qua `compile`. Gọi thêm phase có thể làm một số goal chạy lại mà không mang thêm giá trị.

## 17. Ngoại lệ: goal trực tiếp có thể fork lifecycle

Nói “gọi goal trực tiếp **không bao giờ** chạy phase khác” là phát biểu quá tuyệt đối. Một số plugin goals có thể yêu cầu **forked lifecycle** qua metadata riêng (chẳng hạn cơ chế `@Execute` của Maven Plugin API), khiến Maven thực hiện phase/goal bổ sung trong quá trình chạy.

Nhưng đó là **hành vi riêng của goal**, không phải vì mọi lệnh `plugin:goal` đều là alias của phase. Khi cần biết chắc:

- Đọc tài liệu của goal và plugin descriptor.
- Xem goal có fork lifecycle hoặc điều kiện chuẩn bị nào không.
- Đọc log của invocation thực tế.
- Phân biệt goal yêu cầu **dependency resolution** với goal yêu cầu **chạy trước các phase**; hai việc này không giống nhau.

Chẳng hạn `compiler:compile` trực tiếp vẫn không nên được dùng như tên thay thế cho toàn bộ `mvn compile` trong project có source/resource generation.

## 18. Cách chẩn đoán execution thực sự được gọi

### 18.1. Đọc build log

Chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Tìm những dòng theo dạng:

~~~text
... resources:...:resources (default-resources) ...
... compiler:3.13.0:compile (default-compile) ...
... compiler:3.13.0:testCompile (default-testCompile) ...
... surefire:3.2.5:test (default-test) ...
... jar:3.4.2:jar (default-jar) ...
... antrun:3.1.0:run (verify-jar) ...
[echo] VERIFY-JAR: expected archive exists
~~~

Dấu ba chấm biểu thị những thành phần log khác nhau tùy Maven/plugin. Cái cần kiểm tra là **plugin goal + execution ID + kết quả thực thi**.

### 18.2. Effective POM

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

Trong file hiệu lực, tìm `maven-antrun-plugin`, `verify-jar`, `<phase>verify</phase>` và `<goal>run</goal>`. Nếu plugin/goal được khai báo trong profile hoặc parent, effective POM phản ánh những thay đổi đã áp dụng theo ngữ cảnh.

Với Help Plugin hỗ trợ verbose:

~~~bash
mvn -B -ntp help:effective-pom -Dverbose=true -Doutput=effective-verbose.xml
~~~

Các comment bổ sung có thể giúp truy nguồn một số phần tử. **Effective POM cho biết cấu hình**, không chứng minh execution đã chạy; phải đối chiếu với log, test report và artifact.

### 18.3. Describe goal và parameter

~~~bash
mvn -B -ntp help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
~~~

Help Plugin có thể trình bày tham số và một số metadata của goal. Không đoán tùy tiện rằng tham số `<foo>` luôn có thể cấu hình bằng `-Dfoo=...`; property expression được plugin khai báo có thể khác tên XML parameter.

### 18.4. Profile và module đúng

Nếu goal chỉ được cấu hình trong profile `ci`, cần chẩn đoán với đúng cờ:

~~~bash
mvn -Pci help:active-profiles
mvn -Pci help:effective-pom -Doutput=effective-ci.xml
mvn -Pci verify
~~~

Trong multi-module, module con có thể có effective POM/executions khác root. Khi điều tra, xem **đúng module**, command line `-pl`/`-am` và execution ID trong log, không chỉ đọc `pom.xml` của aggregator.

## 19. Khắc phục lỗi theo triệu chứng

| Triệu chứng | Khả năng thường gặp | Cách xử lý |
| --- | --- | --- |
| `mvn surefire:test` không chạy test nào | Test classes chưa được biên dịch, plugin detection khác hoặc test bị skip | Dùng `mvn test`, kiểm tra `target/test-classes` và Surefire reports |
| `mvn compiler:compile` không thấy source sinh tự động | Goal ở `generate-sources` bị bỏ qua | Dùng `mvn compile`; kiểm tra source-generation execution |
| `mvn jar:jar` tạo JAR thiếu class | Gọi JAR goal trước compile | Dùng `mvn package` sau clean |
| `mvn verify` không chạy quality scanner | Plugin chưa bind goal hoặc profile không active | Xem `<executions>` và effective POM |
| `mvn antrun:run` không chạy `verify-jar` | Execution-level config không phải `default-cli` | Chạy phase `verify` hoặc direct `antrun:run@verify-jar` |
| `antrun:run@verify-jar` fail thiếu JAR | Direct goal không tự chạy package | Dùng `mvn clean verify` hoặc tạo artifact trước |
| Goal thực thi hai lần | Bound lifecycle và bị gọi trực tiếp thêm, hoặc có nhiều executions | So command line và execution IDs |
| Maven không tìm được plugin prefix | Plugin metadata/group/repository không phù hợp | Dùng fully qualified goal để phân biệt lỗi prefix |
| Goal chạy ở phase lạ | Sai phase, defaultPhase hoặc packaging mapping | Kiểm tra descriptor, effective POM, log |
| Local khác CI | Profile, parent, plugin versions, settings hoặc Maven/JDK khác | Tái hiện bằng cùng cờ `-P`/`-D`/`-s` và đúng version |

Trước khi sửa cấu hình, hãy **xác định lỗi xảy ra trong goal nào**. `PluginResolutionException` do Maven không tải được plugin khác với goal đã tải nhưng execution không được bind. Một log `BUILD SUCCESS` cũng không đảm bảo plugin mong đợi đã được gọi.

## 20. Trường hợp integration-test và verify

Với kiểm thử tích hợp, các phase có thể có mục đích khác nhau:

~~~text
pre-integration-test  → chuẩn bị môi trường
integration-test      → chạy kiểm thử tích hợp
post-integration-test → dọn môi trường và thu thập kết quả
verify                → đánh giá kết quả, thực hiện kiểm tra cuối
~~~

Đừng kết thúc pipeline ở `mvn integration-test` nếu dự án cần cleanup/đánh giá ở phase sau. Thường chọn `mvn verify` và bind những goals cần thiết, ví dụ Failsafe Plugin có `integration-test` và `verify` goals.

Tương tự, gọi thẳng `failsafe:integration-test` hoặc `failsafe:verify` không phải lúc nào cũng tái tạo toàn bộ quy trình chuẩn bị/chạy/dọn môi trường trong lifecycle. Tài liệu plugin và POM thực tế quyết định những bước nào phải được chạy.

## 21. Thiết kế pipeline và tránh chạy thừa

Với mục tiêu **kiểm chứng từ trạng thái sạch**:

~~~bash
mvn -B -ntp clean verify
~~~

là lựa chọn phù hợp khi dự án đã cấu hình đầy đủ các checks cần thiết. Không cần tự viết một chuỗi các goal lẻ `compiler:compile` → `surefire:test` → `jar:jar` → custom check để mô phỏng lifecycle; chuỗi ấy rất dễ quên generated resources, test compilation, Failsafe cleanup và executions tùy POM.

Với mục tiêu **chẩn đoán**, gọi goal trực tiếp là hợp lý:

~~~bash
mvn -B -ntp dependency:tree
mvn -B -ntp help:effective-pom
~~~

Với mục tiêu **chạy một check theo yêu cầu**, có thể dùng `goal@executionId` nếu hiểu preconditions. Ví dụ kiểm tra JAR ở mục 7 cần artifact đã tồn tại trước khi gọi trực tiếp.

Khi bind một goal có tác dụng phụ (upload, gọi API, sửa file ngoài `target`), phải review an toàn và vị trí phase cẩn thận. Cấu hình trong POM khiến goal có thể được gọi tự động trong CI ở bất kỳ môi trường nào chạy tới phase đó.

## 22. Câu hỏi tự kiểm tra

1. **`mvn compile` và `mvn compiler:compile` khác nhau thế nào?** Lệnh đầu yêu cầu phase và mọi binding trước/tại đó; lệnh sau yêu cầu goal trực tiếp.
2. **`mvn test` có tự đi qua `compile` trong default lifecycle không?** Có, theo thứ tự phase.
3. **`mvn surefire:test` có bảo đảm test được biên dịch từ source sạch không?** Không nên giả định.
4. **Một plugin được đặt trong `<build><plugins>` có tự chạy ở verify không?** Không, trừ khi có binding/execution phù hợp hoặc được gọi riêng.
5. **`mvn package` trong demo có chạy `verify-jar` không?** Không, vì execution được bind ở phase `verify`.
6. **`mvn verify` trong demo chạy những bước gì?** Compile, test, đóng gói JAR rồi chạy AntRun `verify-jar` và các binding liên quan.
7. **Vì sao `mvn clean antrun:run@verify-jar` cố ý fail?** Vì clean xóa artifact và direct goal không chạy package trước.
8. **`goal@executionId` có đồng nghĩa chạy lifecycle đến phase của execution không?** Không, nó chọn execution config cho direct invocation.
9. **Gọi goal trực tiếp thường có execution ID nào?** `default-cli`.
10. **Execution ID mặc định thường dùng cho compiler compile trong JAR lifecycle?** `default-compile`.
11. **`<pluginManagement>` có tự bind mọi plugin tới phase không?** Không, nó quản lý version/cấu hình để dùng khi plugin được áp dụng.
12. **Muốn cùng goal chạy hai lần trong cùng phase, làm gì?** Tạo hai executions với ID riêng bên trong một plugin declaration.
13. **Muốn tra version/goal/phase hiệu lực dùng công cụ nào?** `help:effective-pom` và build log.
14. **Có goal trực tiếp nào vẫn có thể chạy lifecycle khác không?** Có, nếu goal được thiết kế fork lifecycle; phải đọc metadata/documentation.
15. **Vì sao `mvn compile test` thường không cần thiết khi mục tiêu là test?** `mvn test` đã đi qua compile.
16. **Khi plugin đã tải nhưng không chạy, có nên sửa pluginRepositories trước không?** Không. Kiểm tra execution binding và profile trước.
17. **Khi một goal chỉ có configuration trong execution `verify-jar`, `mvn antrun:run` tự dùng config ấy?** Không mặc nhiên; xem `default-cli` và plugin-level configuration.
18. **Trong demo, dòng `VERIFY-JAR` là stdout Java App?** Không. Đó là log từ AntRun; App chỉ in `Hello, Maven` khi được chạy bằng `java`.
19. **Một phase có thể không có goal nào không?** Có. Phase trống không tự thực hiện kiểm tra.
20. **Khi phát hành, nên dùng riêng `jar:jar` hay `verify`?** Thường nên dùng lifecycle phase phù hợp để các bước kiểm chứng đã bind có cơ hội chạy; `jar:jar` đơn lẻ không thay thế toàn bộ kiểm chứng.

## 23. Checklist khi cấu hình Maven plugin

- [ ] Đã xác định mục đích: gọi một goal hay chạy toàn bộ phase/lifecycle.
- [ ] Đã đọc tài liệu goal, parameter và điều kiện đầu vào cần thiết.
- [ ] Đã kiểm tra `packaging` cùng default lifecycle mapping.
- [ ] Nếu muốn chạy tự động, đã khai báo `<executions>`, `<phase>` và `<goals>` rõ ràng.
- [ ] Mỗi execution dùng ID dễ hiểu; nhiều executions nằm dưới một plugin declaration.
- [ ] Không nhầm plugin-level configuration, execution-level configuration và `default-cli`.
- [ ] Với direct `goal@executionId`, đã xác nhận Maven hỗ trợ và output prerequisite có sẵn.
- [ ] Đã ghim plugin versions quan trọng để tránh kết quả khác nhau theo môi trường.
- [ ] Đã xem `help:effective-pom`, active profiles và log execution IDs.
- [ ] Đã kiểm tra test reports, generated resources và artifact thực tế.
- [ ] Đã lưu ý goal có thể fork lifecycle nếu plugin thiết kế như vậy.
- [ ] Đã phân biệt project multi-module/parent inheritance với root aggregator.
- [ ] Đã tránh đưa token/password vào POM hay log debug.
- [ ] Với CI, đã chạy phase kiểm chứng phù hợp thay vì chỉ gọi những goal tiện tay.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase, goal, thứ tự, default bindings và các cách kết hợp lệnh.
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): `<executions>`, `<phase>`, goal default phase và `goal@executionId`.
- [Apache Maven — Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html): `default-cli` và `default-compile`.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): `<build><plugins>`, executions, inheritance và pluginManagement.
- [Maven AntRun Plugin — Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html): goal `antrun:run` và cấu hình `<target>`.
- [Apache Ant — Available](https://ant.apache.org/manual/Tasks/available.html) và [Fail](https://ant.apache.org/manual/Tasks/fail.html): kiểm tra file và fail build khi điều kiện không đạt.
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): quan sát POM hiệu lực.
- [Maven Help Plugin — describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html): quan sát goal và tham số plugin.

**Kết luận:** `mvn plugin:goal` là lời gọi **một tác vụ cụ thể**; `mvn phase` yêu cầu Maven đi qua **chuỗi phase** và chạy mọi goal đã được bind trên đường đi. `<executions>` kết nối goal với thời điểm lifecycle, còn `goal@executionId` chọn cấu hình của execution khi gọi trực tiếp, **không tự chạy các phase trước đó**. Khi kiểm chứng hoặc phát hành, hãy ưu tiên phase đích với quality gates đã cấu hình và xác minh goal thực sự chạy qua log/report.
