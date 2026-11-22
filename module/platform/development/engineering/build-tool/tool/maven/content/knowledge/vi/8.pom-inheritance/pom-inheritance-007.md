# inherited và kiểm soát việc truyền cấu hình plugin trong Maven POM

## 1. Mục tiêu và vấn đề thực tế

Khi một hệ thống Maven có nhiều module, người xây dựng thường đặt cấu hình plugin chung trong **POM cha (parent POM)** để các module dùng cùng phiên bản Compiler Plugin, Surefire Plugin và cùng quy tắc build. Ví dụ, dự án có `core` và `app`; cả hai cần biên dịch Java 17, nhưng một số tác vụ như tạo báo cáo cho toàn dự án chỉ nên chạy ở parent.

Nếu không phân biệt đúng phạm vi, một execution của plugin khai báo ở parent có thể được truyền xuống các module con và chạy thêm ở những nơi không cần thiết. Maven cung cấp thẻ **`<inherited>`** để kiểm soát việc truyền **khai báo plugin hoặc execution** từ POM cha sang POM con.

Sau bài này, bạn có thể:

1. Giải thích vì sao `<parent>` trong POM con mới tạo quan hệ kế thừa và vì sao `<modules>` không tự tạo inheritance.
2. Phân biệt `<build><plugins>` và `<build><pluginManagement>`: khai báo được thực thi so với quản lý phiên bản/cấu hình.
3. Dùng `<inherited>false</inherited>` ở đúng **mức plugin** hoặc **mức execution**.
4. Giải thích cách Maven hợp nhất plugin configuration khi child override, đặc biệt `combine.self="override"` và `combine.children="append"`.
5. Đọc effective POM và log build của module con để xác minh cấu hình cuối cùng, không đoán từ POM cha.
6. Thực hành trên parent, core, app bằng Maven 3.9.x, JDK 17 và JUnit Jupiter.

**Ý nghĩa cốt lõi:** `inherited=false` không cấm plugin chạy ở chính POM khai báo. Nó ngăn một phần khai báo ở POM cha **được kế thừa** vào POM con. Đó là cơ chế tạo mô hình build, không phải cờ skip tạm thời.

## 2. Ba quan hệ Maven thường bị nhầm lẫn

| Quan hệ | Nơi khai báo | Điều Maven làm |
| --- | --- | --- |
| Aggregation | `<modules><module>core</module><module>app</module></modules>` ở POM gốc | Gom các module thành một reactor; bản thân nó không tạo kế thừa POM |
| Inheritance | `<parent>...</parent>` trong POM con | Cho phép con nhận các phần cấu hình được kế thừa từ parent |
| Dependency | `<dependencies>` trong module sử dụng mã khác | Đưa artifact vào dependency graph và classpath; chi phối thứ tự build reactor |

Parent và aggregator có thể là cùng một POM nhưng không bắt buộc. Nếu `core` xuất hiện trong `<modules>` của parent **mà không khai báo `<parent>`**, `core` vẫn có thể được reactor build cùng parent nhưng không nhận cấu hình plugin theo inheritance từ POM đó.

Ví dụ trong `core/pom.xml`:

~~~xml
<parent>
    <groupId>vn.example</groupId>
    <artifactId>plugin-parent</artifactId>
    <version>1.0.0</version>
</parent>
~~~

Maven 3 mặc định kiểm tra `../pom.xml` làm đường dẫn POM cha tương đối khi file `core/pom.xml` nằm một cấp dưới, sau đó đối chiếu tọa độ parent; có thể thay bằng `<relativePath>` nếu bố cục khác. Nếu parent không nằm ở đó, Maven có thể giải quyết parent từ repository. Một POM con có thể kế thừa plugin mà không cùng thư mục với parent nếu `<parent>` được giải quyết hợp lệ.

## 3. Plugin được khai báo ở đâu?

### 3.1. `build/plugins`: plugin tham gia mô hình build

Một plugin khai báo trong `<build><plugins>` có thể cung cấp cấu hình và các execution. Khi execution gắn với một phase (ví dụ `validate`), Maven sẽ chạy goal đó nếu build tới phase và plugin/goal hợp lệ.

Ví dụ trích đoạn:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
            <executions>
                <execution>
                    <id>create-marker</id>
                    <phase>validate</phase>
                    <goals>
                        <goal>run</goal>
                    </goals>
                    <configuration>
                        <target>
                            <echo message="Validate reached"/>
                        </target>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Nếu khai báo ở parent và **không giới hạn inheritance**, execution này có thể được truyền xuống các POM con rồi thực thi khi con chạy phase `validate`. Điều này đôi khi đúng ý: mọi module cần kiểm tra cùng một quy tắc. Đôi khi lại không đúng: một báo cáo tổng hợp của parent bị tạo lặp tại từng module.

### 3.2. `pluginManagement`: quản lý cấu hình plugin được dùng

Một cấu hình trong `<build><pluginManagement><plugins>` chủ yếu **quản lý** version, configuration và executions để dùng khi plugin được kích hoạt ở nơi thích hợp.

Ví dụ parent:

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
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Module con có `packaging=jar` đã có binding của Compiler Plugin với phase `compile` trong lifecycle mặc định. Vì thế phiên bản và cấu hình compiler do parent quản lý **có thể được áp dụng**, ngay cả khi child không tự viết một mục Compiler Plugin trong `build/plugins`.

Nhưng nếu bạn chỉ liệt kê một plugin tùy ý trong `pluginManagement`, Maven **không tự tạo goal execution mới** chỉ vì có mục quản lý. Plugin cần được sử dụng, được gắn bởi lifecycle hoặc được gọi một cách hợp lệ. Hãy phân biệt *cấu hình có sẵn để dùng* với *một goal chắc chắn đã chạy*.

## 4. Hai nơi đặt inherited và sự khác biệt

### 4.1. `inherited=false` ở mức plugin

Ví dụ trong `build/plugins` của parent:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <inherited>false</inherited>
    <executions>
        <execution>
            <id>parent-report</id>
            <phase>validate</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="Only parent uses this plugin declaration"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Maven vẫn có thể chạy `antrun:run` ở **chính POM parent**. Tuy nhiên **toàn bộ khai báo plugin này** không được truyền từ parent xuống các POM child. Nếu child tự khai báo cùng plugin, đó là cấu hình của child và có thể được xử lý riêng.

Giá trị mặc định `<inherited>` của plugin là `true`. Bạn chỉ cần viết `false` khi muốn chặn inheritance có chủ đích. Không nhầm với `<skip>true</skip>` mà một số plugin hỗ trợ để bỏ một công việc tại runtime.

### 4.2. `inherited=false` ở mức execution

Một plugin có thể có nhiều executions và bạn chỉ muốn ngăn **một execution** truyền xuống:

~~~xml
<executions>
    <execution>
        <id>shared-task</id>
        <phase>process-classes</phase>
        <goals>
            <goal>run</goal>
        </goals>
    </execution>

    <execution>
        <id>parent-only-task</id>
        <inherited>false</inherited>
        <phase>validate</phase>
        <goals>
            <goal>run</goal>
        </goals>
    </execution>
</executions>
~~~

Đây là **trích đoạn để minh họa vị trí**, chưa có `<configuration><target>` của AntRun nên không phải ví dụ hoàn chỉnh. Bản chạy được ở mục 6 cung cấp cấu hình đủ cho từng execution.

Trong ví dụ trên, `shared-task` được truyền xuống child theo mặc định, còn `parent-only-task` chỉ thuộc parent. **Plugin vẫn được kế thừa**; chỉ một execution bị chặn. Nếu đặt `<inherited>false</inherited>` vào thẻ `<plugin>` thay vì `<execution>`, cả hai execution sẽ bị chặn khi truyền xuống con.

| Khai báo parent | Parent có thể chạy? | Child kế thừa? |
| --- | --- | --- |
| Plugin không khai báo inherited | Có, nếu goal được kích hoạt | Có theo mặc định |
| Plugin khai báo inherited=false | Có | Không nhận khai báo plugin đó từ parent |
| Một execution khai báo inherited=false | Execution vẫn có thể chạy ở parent | Không nhận execution đó; execution khác có thể còn |
| Plugin chỉ ở pluginManagement | Không tự tạo execution mới | Cấu hình được quản lý để áp dụng khi plugin được dùng |

`inherited=false` có thể áp dụng cả cho một mục plugin trong `pluginManagement`: nó chặn việc truyền mục quản lý đó đến child. Điều này **không loại bỏ binding compiler/test mặc định** do `packaging` hoặc một khai báo riêng của child tạo ra; goal có thể vẫn chạy với cấu hình khác.

## 5. Vì sao nên ưu tiên chặn đúng execution?

Giả sử parent dùng một plugin có hai tác vụ:

- Execution `shared-marker` đánh dấu mọi module đã đến `process-classes`.
- Execution `parent-only-marker` đánh dấu parent đã đến `validate`.

Nếu cả plugin được kế thừa, mọi module sẽ tạo cả hai marker. Nếu chặn **plugin-level inheritance**, child sẽ không nhận **cả hai**. Nhưng nếu chỉ đặt `<inherited>false</inherited>` cho execution `parent-only-marker`, child vẫn chạy `shared-marker`.

Mức execution thường phù hợp khi một plugin phục vụ **hai nhóm công việc**: một nhóm dùng chung và một nhóm chỉ dành cho POM cha. Mức plugin phù hợp khi toàn bộ plugin chỉ có ý nghĩa tại parent.

Một sơ đồ dự án:

~~~text
plugin-parent/pom.xml
├── compiler trong pluginManagement
│   └── phiên bản 3.14.1, release 17
├── antrun trong build/plugins
│   ├── shared-marker            inherited=true (mặc định)
│   └── parent-only-marker       inherited=false
├── core/pom.xml
│   ├── <parent>plugin-parent</parent>
│   └── nhận shared-marker; không nhận parent-only-marker
└── app/pom.xml
    ├── <parent>plugin-parent</parent>
    ├── dependency tới core
    └── nhận shared-marker; không nhận parent-only-marker
~~~

## 6. Ví dụ Maven 3.9, Java 17, hai module và marker có thể kiểm chứng

### 6.1. Tạo cấu trúc dự án

~~~text
plugin-demo/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/vn/example/core/Calculator.java
│       └── test/java/vn/example/core/CalculatorTest.java
└── app/
    ├── pom.xml
    └── src/main/java/vn/example/app/Main.java
~~~

Mỗi file có nội dung bên dưới. Hãy tạo chính xác tên file và các thư mục tương ứng package. Ví dụ cần JDK 17+, Maven 3.9.x và kết nối mạng lần đầu để tải plugin/JUnit nếu cache chưa có. Chạy các lệnh Maven từ thư mục `plugin-demo`.

### 6.2. POM cha: `plugin-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>plugin-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

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
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>shared-marker</id>
                        <phase>process-classes</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo file="${project.build.directory}/shared.marker"
                                      message="Shared execution ran"/>
                            </target>
                        </configuration>
                    </execution>
                    <execution>
                        <id>parent-only-marker</id>
                        <inherited>false</inherited>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo file="${project.build.directory}/parent-only.marker"
                                      message="Parent-only execution ran"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các điểm cần đọc đúng:

- Parent dùng `packaging=pom`: bản thân nó không đóng JAR Java.
- `core` và `app` được khai báo trong `modules` để reactor biết đến.
- Compiler/Surefire ở `pluginManagement` cung cấp phiên bản/cấu hình chuẩn cho các module.
- Hai executions của AntRun có tên `shared-marker` và `parent-only-marker`. Chúng có **id khác nhau**.
- Execution `parent-only-marker` nằm trong POM cha nhưng khai báo `inherited=false`. Nó vẫn chạy tại cha khi đến `validate`.
- Cả hai `echo` ghi vào `${project.build.directory}` của project hiện tại. Khi execution chạy ở con, đường dẫn đích tương ứng là `core/target` hoặc `app/target`.
- Marker đặt **ngoài `target/classes`**, vì mục tiêu là kiểm tra phase đã chạy, không đưa marker vào JAR.

AntRun Plugin có thể thực thi Ant task `echo`, và cấu hình `<target>` là một phần của execution. Không cần tự tạo file marker bằng tay.

### 6.3. POM con: `core/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example</groupId>
        <artifactId>plugin-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`core` không khai báo lại `groupId`/`version`, phiên bản JUnit, Compiler Plugin hay Surefire Plugin. Parent cung cấp các phần đó. Điều này chỉ hoạt động vì `core` khai báo đúng `<parent>`.

**Lưu ý:** `dependencyManagement` của parent chỉ quản lý phiên bản JUnit. Dependency `junit-jupiter` thực sự đi vào `core` do khai báo ở `<dependencies>` của `core`. Không nên nhầm cơ chế dependency management với plugin management.

### 6.4. POM con: `app/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example</groupId>
        <artifactId>plugin-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
~~~

Ở module `app`, `${project.version}` là phiên bản hiệu lực của dự án `app`, trong mẫu bằng `1.0.0` kế thừa từ parent. Cách khai báo này giúp `app` phụ thuộc đúng artifact `vn.example:core:1.0.0`. Reactor dựa vào quan hệ dependency để sắp xếp `core` trước `app` khi cần.

### 6.5. Mã Java của `core`

File `core/src/main/java/vn/example/core/Calculator.java`:

~~~java
package vn.example.core;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
~~~

File `core/src/test/java/vn/example/core/CalculatorTest.java`:

~~~java
package vn.example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(7, Calculator.add(3, 4));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> Calculator.add(Integer.MAX_VALUE, 1));
    }
}
~~~

Đây là hai test JUnit 5. `Math.addExact` trả về tổng nếu không tràn `int` và ném `ArithmeticException` khi tràn. Test thứ hai xác nhận một hành vi lỗi có chủ đích, không phải test phụ thuộc môi trường.

### 6.6. Mã Java của `app`

File `app/src/main/java/vn/example/app/Main.java`:

~~~java
package vn.example.app;

import vn.example.core.Calculator;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("3 + 4 = " + Calculator.add(3, 4));
    }
}
~~~

`app` import API của `core`; `core` không biết `app`. Đây là quan hệ phụ thuộc một chiều có thể chạy trực tiếp bằng classpath chứa hai JAR.

## 7. Build và kiểm tra sự kế thừa bằng file thực tế

Từ `plugin-demo`:

~~~bash
mvn -version
mvn clean verify
~~~

Maven phải chạy bằng JDK hỗ trợ `release=17`. Khi build thành công, trong reactor có POM parent và hai module con. Với bản POM và mã nguồn trên, hai test ở `core` phải PASS, `core-1.0.0.jar` và `app-1.0.0.jar` được tạo.

Bảng file cần kiểm tra **sau lệnh có clean**:

| Vị trí | Kỳ vọng | Tại sao |
| --- | --- | --- |
| `target/shared.marker` | Có | Parent chạy `shared-marker` |
| `target/parent-only.marker` | Có | Parent chạy `parent-only-marker` của chính nó |
| `core/target/shared.marker` | Có | `core` kế thừa `shared-marker` |
| `app/target/shared.marker` | Có | `app` kế thừa `shared-marker` |
| `core/target/parent-only.marker` | **Không** | Execution parent-only không được kế thừa |
| `app/target/parent-only.marker` | **Không** | Execution parent-only không được kế thừa |
| `core/target/core-1.0.0.jar` | Có | `core` là module JAR |
| `app/target/app-1.0.0.jar` | Có | `app` là module JAR |

Có thể có các file metadata và báo cáo bổ sung trong `target`. Những gì cần tin cậy là **sự có mặt/vắng mặt của đúng marker** sau lần build sạch, cùng với effective POM/log execution.

Trong log Maven, tìm `maven-antrun-plugin:3.1.0:run` và execution id được in cho từng project, thường có dạng `(shared-marker)` hoặc `(parent-only-marker)`. Đếm đúng project nào chạy execution, không chỉ đếm tổng số lần log có chữ “antrun”.

Chạy ứng dụng trên Linux/macOS:

~~~bash
java -cp "app/target/app-1.0.0.jar:core/target/core-1.0.0.jar" vn.example.app.Main
~~~

Trên Windows PowerShell hoặc CMD:

~~~bat
java -cp "app\target\app-1.0.0.jar;core\target\core-1.0.0.jar" vn.example.app.Main
~~~

Stdout **chính xác** của ứng dụng là:

~~~text
3 + 4 = 7
~~~

Classpath cần cả hai JAR do `app` phụ thuộc `core`. Một Maven JAR thông thường không tự nhúng dependency sibling và không nhất thiết có manifest `Main-Class` để `java -jar` chạy được.

## 8. Dùng effective POM để chứng minh cấu hình cuối

Không nên kết luận chỉ bằng việc nhìn `pom.xml` ở parent. Hãy hỏi Maven **module con thực sự nhận gì**:

~~~bash
mvn -pl :core help:effective-pom
mvn -pl :app help:effective-pom
mvn -pl :core help:effective-pom -Dverbose
~~~

Trong effective POM của `core` và `app`, bạn cần tìm:

- Maven Compiler Plugin được quản lý ở phiên bản `3.14.1`, cấu hình `release=17`.
- Maven Surefire Plugin được quản lý ở phiên bản `3.5.4`.
- Maven AntRun Plugin với execution `shared-marker`, phase `process-classes`.
- Không có **execution `parent-only-marker` kế thừa từ parent**.

Ở effective POM của parent, cả hai execution của AntRun có thể xuất hiện. `inherited=false` chỉ kiểm soát truyền xuống child; nó không xóa execution khỏi POM chứa nó.

`-Dverbose` của Help Plugin giúp xem thông tin nguồn gốc cấu hình khi plugin hỗ trợ chế độ đó. Cấu hình của một plugin có thể được hợp nhất từ parent, pluginManagement, khai báo ở child và profile đang hoạt động. Vì thế **effective POM** là bằng chứng cấu hình, còn **log + artifact** là bằng chứng goal đã chạy.

## 9. Thí nghiệm A: bỏ inherited=false ở đúng execution

Trong parent `pom.xml`, tìm execution `parent-only-marker` và tạm xóa dòng:

~~~xml
<inherited>false</inherited>
~~~

Chạy lại:

~~~bash
mvn clean verify
~~~

Kỳ vọng cả ba project parent/core/app có file `parent-only.marker`, vì execution giờ được truyền xuống con theo mặc định. Đồng thời `shared.marker` vẫn có ở cả ba project.

Sau đó, **khôi phục** `<inherited>false</inherited>` bên trong execution `parent-only-marker` rồi chạy lại `mvn clean verify`. Hai marker `core/target/parent-only.marker` và `app/target/parent-only.marker` phải biến mất sau lần clean mới; marker tại root còn.

Kết quả chứng minh: **chỉ một execution bị ngăn kế thừa**, không ảnh hưởng execution `shared-marker`.

## 10. Thí nghiệm B: đặt inherited=false ở mức plugin

Trở lại bản POM gốc (parent-only execution đã có `inherited=false`). Thêm:

~~~xml
<inherited>false</inherited>
~~~

vào **maven-antrun-plugin**, ngay sau `<version>3.1.0</version>`, cùng cấp `<executions>`. Chạy:

~~~bash
mvn clean verify
~~~

Kỳ vọng sau build sạch:

| Marker | Parent | Core | App |
| --- | --- | --- | --- |
| `shared.marker` | Có | **Không** | **Không** |
| `parent-only.marker` | Có | **Không** | **Không** |

Lần này child không nhận **toàn bộ khai báo AntRun Plugin từ parent**, kể cả execution `shared-marker`. Parent vẫn chạy hai execution tại chính POM parent.

Xóa dòng `<inherited>false</inherited>` vừa thêm ở **mức plugin**, giữ nguyên dòng trong execution `parent-only-marker`, rồi build lại để trở về trạng thái ban đầu.

Nên ghi nhớ phép thử: cùng là chữ `inherited=false`, nhưng **vị trí trong cây XML** quyết định phạm vi tác động. Đặt sai cấp có thể làm mất cả một nhóm công việc dùng chung.

## 11. Thí nghiệm C: override cấu hình plugin ở một module

Trong mẫu, parent đặt Compiler Plugin trong `pluginManagement`:

~~~xml
<configuration>
    <release>17</release>
    <showWarnings>true</showWarnings>
</configuration>
~~~

Nếu riêng `core` cần tắt warning của compiler (chỉ để thử cách merge), thêm một mục `build` ngang cấp `dependencies` trong `core/pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <showWarnings>false</showWarnings>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Sau đó chạy:

~~~bash
mvn -pl :core help:effective-pom
mvn -pl :app help:effective-pom
mvn clean verify
~~~

Cấu hình hợp nhất của compiler ở `core` vẫn có `release=17`, nhưng `showWarnings=false`. `app` không override nên dùng `release=17` và `showWarnings=true`. Phiên bản Compiler Plugin `3.14.1` tiếp tục được quản lý từ parent.

Đây là cách áp dụng phổ biến: **parent quản lý cấu hình chung; child chỉ viết phần khác biệt**. Nếu muốn kết thúc thí nghiệm, bỏ phần `build/plugins` mới thêm ở `core` để khôi phục bản gốc.

**Lưu ý:** khi child tự khai báo một plugin đã được parent quản lý, không có nghĩa nó tạo một plugin thứ hai độc lập; Maven hợp nhất các mục plugin theo tọa độ và các quy tắc model tương ứng.

## 12. Phân biệt inherited với XML configuration merge

`inherited` trả lời **có truyền cấu hình từ cha xuống con hay không**. Khi nội dung được truyền, Maven còn dùng quy tắc merge XML để quyết định **giữ giá trị cha, ưu tiên giá trị con, nối danh sách hay thay toàn bộ nhánh**.

### 12.1. Merge mặc định

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

Kết quả về hai phần tử này trong effective configuration:

~~~xml
<configuration>
    <release>17</release>
    <showWarnings>false</showWarnings>
</configuration>
~~~

Điều đó giúp cấu hình chung từ parent được giữ khi child chỉ cần đổi một thuộc tính.

### 12.2. `combine.self="override"`

Nếu child khai báo:

~~~xml
<configuration combine.self="override">
    <showWarnings>false</showWarnings>
</configuration>
~~~

thì **cả nhánh `configuration`** của child thay nhánh tương ứng từ parent. Phần `<release>17</release>` không còn được giữ từ cấu hình parent **qua cơ chế merge nhánh này**. Trong mẫu đang học, đó có thể làm compiler không còn được cấu hình đúng Java 17 nếu không có một nguồn cấu hình release khác.

`combine.self="override"` hữu ích khi cần cấu hình hoàn toàn độc lập; nhưng nếu chỉ muốn đổi warning thì nó quá rộng. Dùng override ở phần tử cụ thể khi có thể, đừng xóa nhánh lớn mà không xem effective POM.

### 12.3. `combine.children="append"`

Với cấu hình dạng danh sách, đôi khi mong muốn **nối** các phần tử thay vì hợp nhất theo tên. Ví dụ XML minh họa:

Parent:

~~~xml
<configuration>
    <items>
        <item>parent-1</item>
        <item>parent-2</item>
    </items>
</configuration>
~~~

Child:

~~~xml
<configuration>
    <items combine.children="append">
        <item>child-1</item>
    </items>
</configuration>
~~~

Kết quả ở phần tử `items` sẽ có chuỗi `parent-1`, `parent-2`, `child-1` theo thứ tự. `items` ở đây là **tên giả để minh họa cơ chế XML merge**, không phải một tham số được bảo đảm tồn tại trong Compiler Plugin. Bạn phải tra đúng tham số plugin đang dùng.

Hai thuộc tính `combine.self` và `combine.children` chỉ tác động đến **phần tử cấu hình được gắn attribute**, khác với `<inherited>` của plugin/execution. Không nên kết hợp `combine.self="override"` và `combine.children="append"` trên cùng phần tử; override sẽ ưu tiên và làm ý nghĩa append mất tác dụng.

## 13. Execution id và cách child thay một execution đã kế thừa

Maven hợp nhất các plugin executions có **cùng id** giữa cha và con khi các điều kiện kế thừa hợp lệ được đáp ứng. Nếu child tạo một execution với id mới, nó có thể trở thành **một công việc thứ hai** bên cạnh execution được kế thừa.

Chẳng hạn bạn muốn `core` thay target của execution `shared-marker`, vẫn chạy ở `process-classes` nhưng tạo marker tên riêng. Trong `core/pom.xml`, khai báo plugin và execution cùng id:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <executions>
                <execution>
                    <id>shared-marker</id>
                    <configuration>
                        <target combine.self="override">
                            <echo file="${project.build.directory}/core.marker"
                                  message="Core-specific marker"/>
                        </target>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Ví dụ này **thay thế thí nghiệm compiler mục 11** trong `core`, không ghép hai snippet `<build>` độc lập vào cùng một POM. Execution id `shared-marker` khớp parent, nên cấu hình phase/goal có thể được kế thừa trong quá trình hợp nhất, còn target được child override.

Sau `mvn clean verify`, `core` dự kiến tạo `core/target/core.marker`; parent và `app` vẫn tạo `shared.marker`. Kiểm tra effective POM của `core` nếu không chắc phần `<phase>`, `<goals>` hoặc `<configuration>` nào còn lại.

Nếu dùng id `core-marker` mới thay vì `shared-marker`, execution `shared-marker` của parent có thể **vẫn tồn tại** trong child, làm AntRun chạy thêm cả execution mới. Không thay id tùy ý khi định sửa một execution được kế thừa.

## 14. inherited không đồng nghĩa với skip hoặc chọn module

| Mục đích | Cơ chế | Hiệu quả |
| --- | --- | --- |
| Ngăn plugin từ parent truyền xuống child | `<inherited>false</inherited>` trong `plugin` | Model child không kế thừa khai báo plugin đó |
| Ngăn một execution từ parent truyền xuống child | `<inherited>false</inherited>` trong `execution` | Các execution khác vẫn có thể được kế thừa |
| Bỏ việc chạy test một lần build | `-DskipTests` nếu Surefire/Failsafe hỗ trợ | Thay đổi hành vi plugin test của lần chạy, không xóa plugin khỏi POM |
| Chỉ build module `core` | `mvn -pl :core test` | Chọn project trong reactor, không thay cấu hình inheritance |
| Build `app` cùng dependency nội bộ | `mvn -pl :app -am package` | Thêm project dependency cần thiết vào reactor |
| Không đi vào submodule từ root | `mvn -N validate` | Lựa chọn chế độ non-recursive trong lần chạy, không xóa quan hệ parent |
| Quản lý version compiler | Parent `pluginManagement` | Cung cấp version/config cho plugin được dùng ở child |

Nếu muốn một tác vụ chỉ chạy ở parent, có thể cân nhắc plugin-level hoặc execution-level inherited, tùy parent còn tác vụ nào cần truyền xuống child. Nếu chỉ muốn giảm thời gian build cục bộ, sử dụng các cờ CLI tương ứng; thay POM inheritance để giải quyết một yêu cầu tạm thời thường không phù hợp.

**Profile cũng khác inheritance.** Maven không truyền nguyên định nghĩa `<profile>` như một cấu hình parent thông thường; các ảnh hưởng của **profile đang hoạt động** mới có thể góp phần vào effective POM sau khi model được dựng. Khi một plugin chỉ xuất hiện ở CI, hãy xem profile đang kích hoạt và POM hiệu lực trước khi kết luận `inherited` bị bỏ qua.

## 15. Đọc lỗi và tìm nguyên nhân có hệ thống

### 15.1. Quy trình kiểm tra

1. Kiểm tra con có `<parent>` trỏ đúng `groupId:artifactId:version` của cha không.
2. Kiểm tra plugin nằm trong `build/plugins` hay `pluginManagement`.
3. Tìm `<inherited>false</inherited>` và xác định nó nằm **trong `plugin` hay `execution`**.
4. Kiểm tra `<execution><id>` ở con có cùng id với parent không.
5. Kiểm tra `<configuration>` đã bị child override bằng `combine.self` hoặc cấu hình cùng tên chưa.
6. Chạy `mvn -pl :core help:effective-pom -Dverbose` để xem model của module cần giải thích.
7. Chạy `mvn clean verify` từ root để log/artifact phản ánh lần build sạch, rồi đối chiếu execution nào thực sự chạy.

### 15.2. Bảng triệu chứng

| Triệu chứng | Cần xem |
| --- | --- |
| Con không nhận plugin của cha | Có `<parent>` đúng không? Có `inherited=false` ở mức plugin không? Child có override không? |
| Parent có marker, con không có marker | Execution có `inherited=false`? Plugin có bị chặn nguyên khối? Build đã tới phase chưa? |
| Chỉ muốn chặn một execution nhưng cả plugin mất ở child | `inherited=false` đặt nhầm ở `plugin` |
| Plugin có trong effective POM nhưng goal không chạy | Mục có thể chỉ nằm trong pluginManagement, hoặc execution không gắn phase/phase chưa được chạy |
| Plugin chạy hai lần | Execution id khác nhau hoặc goal có binding khác; đọc id trong log |
| Child mất release 17 | Cấu hình compiler có thể bị `combine.self="override"` làm mất; kiểm tra effective POM |
| Version compiler khác dự đoán | Xem pluginManagement ở các cấp ancestor và plugin khai báo ở child |
| `release version 17 not supported` | Maven dùng JDK thấp hơn 17; kiểm tra `mvn -version`, `JAVA_HOME` |
| Thiếu file `core/target/shared.marker` sau build | Kiểm tra execution có inherited không, AntRun goal có chạy và file output path có đúng không |
| Test không chạy dù `BUILD SUCCESS` | Đọc `target/surefire-reports`, cấu hình Surefire và skip flags |
| File marker vẫn còn sau khi chặn inherited | Có thể là đầu ra cũ; chạy lại `mvn clean verify` |
| Build thiếu `core` khi chỉ chọn app | Dependency chưa có local repository; dùng `mvn -pl :app -am verify` từ reactor root |

**Đừng suy luận hành vi POM từ tên file tạo ra ở một lần build cũ.** Cần đi từ effective POM để xác định cấu hình, log Maven để xác định goal thực thi, rồi output sạch để xác nhận kết quả.

## 16. Bài tập cuối bài

**Bài tập A — Giải thích cấu trúc:** Phân biệt role aggregator và parent trong `plugin-demo`. Chỉ ra tại sao `core` và `app` nhận cấu hình compiler, và tại sao `app` vẫn cần khai báo dependency đến `core`.

**Bài tập B — Xác nhận bằng marker:** Chạy `mvn clean verify` với POM gốc và lập bảng đánh dấu có/không cho `shared.marker`, `parent-only.marker` tại parent/core/app. Đối chiếu với bảng mục 7.

**Bài tập C — Đổi mức inherited:** Chỉ bỏ thẻ `inherited=false` của execution `parent-only-marker`, build sạch và ghi sự khác biệt. Khôi phục; đặt `inherited=false` ở plugin AntRun, build sạch và giải thích vì sao `shared.marker` biến mất ở child.

**Bài tập D — pluginManagement:** Đổi `showWarnings=false` chỉ tại `core`, giữ nguyên compiler release. Dùng effective POM chứng minh phiên bản compiler và `release=17` vẫn đến từ parent.

**Bài tập E — XML merge:** Giải thích sự khác nhau giữa override riêng `showWarnings`, override cả `configuration` và append danh sách. Nêu khi nào hai thuộc tính `combine.self`/`combine.children` thực sự cần thiết.

**Bài tập F — execution id:** Thử override execution `shared-marker` bằng cùng id trong `core`. Sau đó thử id khác trong một bản sao dự án và so sánh số execution AntRun chạy. Khôi phục POM gốc sau thử nghiệm.

Hoàn thành bài khi có thể trả lời câu hỏi: **“Muốn plugin chung vẫn chạy ở child nhưng một execution chỉ chạy ở parent thì đặt inherited=false ở đâu?”** — trong chính `<execution>` cần chặn, và xác minh bằng effective POM cùng file được tạo sau một build sạch.

## 17. Tài liệu chính thức

- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): plugin inheritance, `pluginManagement`, `inherited`, execution id và `combine.self`/`combine.children`.
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): POM cha và cơ chế kế thừa.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase, default plugin binding và execution.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor, aggregation và dependency.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): đọc cấu hình POM hiệu lực.
- [Apache Maven AntRun Plugin — Usage](https://maven.apache.org/plugins/maven-antrun-plugin/usage.html): goal `run` và Ant `<target>`.
