# Tập trung phiên bản dự án và thư viện bằng properties trong Maven

## 1. Vấn đề: một phiên bản được lặp ở nhiều nơi

Một project Maven có thể dùng nhiều thư viện, plugin và module. Nếu mỗi `pom.xml` đều viết riêng các số phiên bản, việc nâng cấp nhanh chóng trở thành công việc tìm-và-thay-thế thiếu an toàn:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
</dependency>
~~~

Nếu cùng thư viện còn được khai báo ở năm module khác, dễ xảy ra chuyện module A dùng `3.17.0` còn module B dùng `3.16.0`. Khi phát hành một bộ nhiều module, dự án cũng có thể có parent version mới nhưng child vẫn trỏ tới artifact cũ. Plugin versions không nhất quán còn gây tình trạng CI/build trên các máy khác nhau.

**Maven properties** là cách định nghĩa một giá trị ở một nơi rồi tham chiếu giá trị đó bằng `${...}` trong những vị trí POM hỗ trợ interpolation. Nhưng chỉ gom các chuỗi vào `<properties>` **không tự** giải quyết toàn bộ quản lý phiên bản. Phải hiểu rõ:

- **Project version:** phiên bản GAV của artifact được build.
- **Library/dependency version:** phiên bản thư viện ứng dụng phụ thuộc.
- **Plugin version:** phiên bản công cụ Maven dùng để build.
- **Parent/BOM version:** phiên bản của POM quản lý kế thừa hoặc dependency catalog.
- **Resolved runtime dependency version:** phiên bản cuối cùng sau mediation/dependency management.
- **Published POM version:** tọa độ mà consumer thấy khi install/deploy.

Mục tiêu của bài: thiết kế **single source of truth hợp lý** cho các phiên bản cần đồng bộ; sử dụng `<properties>`, `<dependencyManagement>`, `<pluginManagement>`, `${project.version}` và Maven CI-friendly `${revision}` đúng vai trò; kiểm chứng phiên bản thực tế bằng Maven CLI, bản JAR và test Java 17.

## 2. Properties là giá trị được nội suy, không phải dependency

Ví dụ:

~~~xml
<properties>
    <commons.lang3.version>3.17.0</commons.lang3.version>
    <junit.jupiter.version>5.11.4</junit.jupiter.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Các property là những **cặp tên/giá trị**. Maven cho phép tham chiếu:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>${commons.lang3.version}</version>
</dependency>
~~~

Ở vị trí version của dependency, `${commons.lang3.version}` được nội suy thành `3.17.0`. Tuy nhiên **việc chỉ khai báo property không làm Maven tải thư viện**. Artifact phải thực sự xuất hiện trong `<dependencies>`, hoặc một plugin khác phải tham chiếu nó hợp lệ.

Phân biệt nhanh:

~~~text
<properties>
    <commons.lang3.version>3.17.0</commons.lang3.version>
</properties>
         |
         | nội suy
         v
<dependency><version>${commons.lang3.version}</version></dependency>
         |
         | Maven resolve
         v
org.apache.commons:commons-lang3:3.17.0
~~~

Một property **không phải Maven profile**, không phải biến môi trường OS và không phải Java system property trong ứng dụng. Cách viết `${...}` là cú pháp POM/interpolation; ứng dụng Java không tự đọc biến này bằng `System.getenv()` nếu bạn chưa truyền hoặc lọc nó vào resource/JVM.

## 3. Ba loại phiên bản phải quản lý riêng

| Nhóm | Ví dụ | Cơ chế quản lý phù hợp |
| --- | --- | --- |
| Version của artifact chính | `com.example:version-properties-demo:1.0.0-SNAPSHOT` | `<version>`; có thể dùng CI-friendly `${revision}` |
| Version thư viện | `commons-lang3:3.17.0`, `junit-jupiter:5.11.4` | `<properties>` và `<dependencyManagement>` |
| Version Maven plugins | compiler 3.13.0, surefire 3.5.2 | `<pluginManagement>` và version properties khi cần |
| Parent POM version | parent nội bộ `1.0.0` | `<parent><version>...` hoặc CI-friendly khi phù hợp |
| Imported BOM version | ví dụ BOM `x.y.z` | `<dependencyManagement>` với `type=pom`, `scope=import` |
| Java target release | Java 17 | `<maven.compiler.release>17</maven.compiler.release>` |
| Tool/runtime version | JDK, Maven executable | Maven Wrapper/CI image/toolchains, **không do một POM property tự cài đặt** |

**Không nên gộp những phiên bản không có quan hệ vào cùng một giá trị** chỉ vì tên chúng đều có chữ `version`. Ví dụ `junit.jupiter.version` và `commons.lang3.version` là hai sản phẩm độc lập; không dùng một property `<libraries.version>` cho cả hai.

Tên property nên nêu rõ đối tượng, dùng quy ước nhất quán:

~~~xml
<properties>
    <commons.lang3.version>3.17.0</commons.lang3.version>
    <junit.jupiter.version>5.11.4</junit.jupiter.version>
    <maven.compiler.plugin.version>3.13.0</maven.compiler.plugin.version>
    <maven.surefire.plugin.version>3.5.2</maven.surefire.plugin.version>
</properties>
~~~

Tránh tên quá chung như `version`, `lib.version`, `latest`, `foo` nếu dự án có nhiều dependency. Tên mang ngữ nghĩa giúp review PR nhận ra tác động của việc nâng cấp.

## 4. Nội suy property trong dependency version

Với dependency trực tiếp:

~~~xml
<properties>
    <commons.lang3.version>3.17.0</commons.lang3.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>${commons.lang3.version}</version>
    </dependency>
</dependencies>
~~~

Đây là cách **hợp lệ**. Maven model builder nội suy `${commons.lang3.version}` khi tạo model hiệu lực.

Nếu một thư viện xuất hiện ở nhiều child modules, việc copy lại cùng dòng `<version>${commons.lang3.version}</version>` tuy tốt hơn hardcode số, nhưng vẫn còn lặp **toàn bộ khai báo version**. `<dependencyManagement>` có thể loại bỏ phần lặp đó.

### 4.1. Property có thể chứa giá trị gì?

Thông thường property version chứa một **phiên bản cố định** như `3.17.0`. Maven hỗ trợ cú pháp version requirements/ranges ở các vị trí thích hợp, nhưng dùng một range thay vì version xác định có thể khiến kết quả resolve biến động theo repository và thời gian.

Vì mục tiêu ở đây là **quản lý phiên bản có thể tái tạo**, ưu tiên phiên bản chính xác, được test/approve, thay vì để CI tự chọn “bất kỳ bản mới nhất”. Đừng coi `LATEST` hoặc `RELEASE` là policy nâng cấp an toàn.

### 4.2. `-D` có thể override property khi gọi Maven

~~~bash
mvn -B -Dcommons.lang3.version=3.16.0 clean verify
~~~

Maven user property từ CLI có thể ghi đè POM property cùng tên cho lần chạy này. **Không sửa `pom.xml` trên disk**: lượt chạy sau không truyền `-D` sẽ trở về giá trị POM mặc định.

Vì thế phải ghi lại những overrides trong CI logs/metadata không nhạy cảm nếu muốn tái hiện artifact. Build có cùng Git commit nhưng `-Dcommons.lang3.version` khác có thể resolve thư viện khác và tạo artifact khác.

## 5. Quản lý các phiên bản dependency tập trung bằng dependencyManagement

Đặt trong parent POM hoặc một POM cần quản lý version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons.lang3.version}</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó một module cần Commons Lang thực sự thêm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

Không cần viết lại `<version>`; Maven lấy version được quản lý. Với JUnit:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
</dependency>
~~~

Trong ví dụ quản lý ở trên, scope `test` cũng được khai báo trong `dependencyManagement` và được áp dụng nếu dependency trực tiếp không override scope.

**Điểm dễ nhầm:** `<dependencyManagement>` chỉ **quản lý cách giải dependency khi dependency thực sự được sử dụng**, không tự thêm một dependency vào classpath. Nếu chỉ có dependencyManagement mà không có `<dependencies>`, Java source vẫn không tự import được Commons Lang.

### 5.1. Tại sao vẫn cần property nếu đã có dependencyManagement?

Bạn có thể viết:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây cũng là một **single source of truth cho dependency đó** trong parent. Property tăng giá trị khi:

- Cùng một version được dùng ở nhiều artifacts của cùng family.
- Version cần được tham chiếu trong plugin config, báo cáo, filtered resource.
- CI muốn override một tập dependency có chủ đích qua `-D`.
- Một công cụ như Versions Maven Plugin cần cập nhật property trực tiếp.
- Tổ chức có convention quản lý version names để audit.

Không biến mọi dependency thành thêm một property nếu điều đó chỉ làm POM khó đọc. Có thể quản lý version thẳng trong dependencyManagement khi mỗi version chỉ có một chỗ sử dụng và không cần CLI override.

## 6. Plugin versions: pluginManagement khác dependencyManagement

Maven Compiler, Surefire, Resources, JAR, Shade và các plugin khác **không phải dependencies của ứng dụng**. Chúng chạy trong Maven build environment.

Dùng:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>${maven.compiler.plugin.version}</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${maven.surefire.plugin.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

**`pluginManagement` quản lý versions/config của plugin**, tương tự nhưng **không giống** dependencyManagement. Nó không có nghĩa mọi plugin được liệt kê ở đây đều được tự kích hoạt tùy ý.

Một plugin được default lifecycle binding gọi cho packaging tương ứng (như Compiler/Surefire/JAR trong `jar` packaging) có thể nhận version do pluginManagement quản lý. Với plugin không có binding mặc định, bạn vẫn cần khai báo goal/execution hoặc gọi goal trực tiếp.

Ví dụ một module muốn chạy Exec Plugin phải cấu hình trong `<build><plugins>` hoặc gọi goal qua CLI; một `<pluginManagement>` entry cho Exec Plugin không tự chạy chương trình ngoài.

### 6.1. Vì sao không chỉ dùng `<properties>`?

Một property như:

~~~xml
<properties>
    <maven.surefire.plugin.version>3.5.2</maven.surefire.plugin.version>
</properties>
~~~

không buộc Maven dùng Surefire 3.5.2 nếu không có **một chỗ cấu hình plugin version tham chiếu property đó**. Property chỉ mang giá trị; `<pluginManagement>` hoặc `<plugins>` mới áp nó lên plugin.

### 6.2. Phân biệt library/runtime và build tool

| Khai báo | Mục tiêu | Tác dụng |
| --- | --- | --- |
| `<dependencies><dependency>` | Dependencies của project | Ảnh hưởng compile/test/runtime graphs |
| `<dependencyManagement>` | Quản lý dependency metadata | Chọn version/scope cho dependencies được khai báo |
| `<build><plugins>` | Plugins thực sự dùng | Chạy goals theo lifecycle hoặc explicit invocations |
| `<pluginManagement>` | Quản lý plugin version/config | Áp dụng khi plugin được sử dụng |
| `<properties>` | Giá trị chung | Nội suy vào những cấu hình trên khi được tham chiếu |

**Không đặt Maven Compiler Plugin trong `<dependencies>` để “khóa compiler version”**. Và không đặt Commons Lang chỉ trong `<pluginManagement>` rồi mong Java code compile được.

## 7. Project version: không dùng tên property tùy ý trong `<project><version>` của Maven 3

Đây là ngoại lệ quan trọng nhất của bài.

Bạn có thể nghĩ rằng:

~~~xml
<properties>
    <application.version>1.0.0-SNAPSHOT</application.version>
</properties>
<version>${application.version}</version>
~~~

sẽ hoạt động y hệt một dependency version. **Không nên dùng như mẫu quản lý project version của Maven 3**: Maven POM model có các ràng buộc đối với expression trong trường project version. Maven hỗ trợ đặc biệt cơ chế **CI-friendly versions** cho ba tên:

- `${revision}`
- `${sha1}`
- `${changelist}`

Ví dụ được Maven tài liệu hóa:

~~~xml
<version>${revision}</version>

<properties>
    <revision>1.0.0-SNAPSHOT</revision>
</properties>
~~~

Kể từ Maven 3.5.0-beta-1 đã có cơ chế CI-friendly, và với demo bài này dùng **Maven 3.9.x** để tránh phụ thuộc bản quá cũ.

### 7.1. Dùng revision để tập trung project version

~~~xml
<project>
    ...
    <groupId>com.example</groupId>
    <artifactId>sample-app</artifactId>
    <version>${revision}</version>
    <properties>
        <revision>1.0.0-SNAPSHOT</revision>
    </properties>
</project>
~~~

Đây là fragment, không phải POM XML độc lập. Với CLI:

~~~bash
mvn -Drevision=2.1.0-SNAPSHOT clean package
~~~

Artifact có effective project version `2.1.0-SNAPSHOT` trong lượt build đó, nếu các cấu hình khác không đổi.

### 7.2. Khi cần changelist (SNAPSHOT/release)

Một pattern có thể là:

~~~xml
<version>${revision}${changelist}</version>

<properties>
    <revision>2.1.0</revision>
    <changelist>-SNAPSHOT</changelist>
</properties>
~~~

Khi build mặc định: `2.1.0-SNAPSHOT`. Khi bỏ changelist bằng CLI:

~~~bash
mvn -Dchangelist= clean package
~~~

có thể tạo effective version `2.1.0`. Chỉ thao tác này **chưa phải toàn bộ quy trình release**: cần đảm bảo không có snapshot dependencies, publish đúng repository, tags/provenance/changelog và security gates.

`${sha1}` là placeholder thứ ba được hỗ trợ trong CI-friendly version strings; nó **không tự tính Git commit SHA**. Nếu cần giá trị từ CI, phải cấp vào đúng property theo quy trình của build.

### 7.3. Không lồng property khác vào revision một cách tùy tiện

Mẫu:

~~~xml
<revision>1.0.0-${build.number}-SNAPSHOT</revision>
~~~

rồi `<version>${revision}</version>` **không phải cách Maven CI-friendly đảm bảo một level property expansion tùy ý**. Tài liệu Maven cảnh báo không dùng dạng tùy biến này rồi kỳ vọng nó nội suy như ý. Hãy cung cấp revision hoàn chỉnh từ CI, hoặc dùng `${revision}${sha1}${changelist}` theo cách Maven hỗ trợ.

**Không coi `${revision}` là một Maven plugin.** Nó là một cơ chế xử lý phiên bản đặc biệt của Maven Core.

## 8. Ví dụ thực hành hoàn chỉnh: quản lý tất cả phiên bản trong một POM

Ta xây một project Java 17 có:

- `project.version` dùng `${revision}`.
- Commons Lang version dùng `${commons.lang3.version}`.
- JUnit Jupiter version dùng `${junit.jupiter.version}`.
- Compiler/Surefire/Resources/JAR plugins được pin qua version properties.
- Dependency versions tập trung ở `<dependencyManagement>`.
- Plugin versions tập trung ở `<pluginManagement>`.
- Resource `.properties` được Maven filtering để ứng dụng hiển thị **effective project và library versions**.
- Flatten Maven Plugin tạo POM xuất bản an toàn khi dùng CI-friendly version.
- Exec Maven Plugin giúp chạy Java `main` với runtime dependencies do Maven resolve.
- JUnit test chạy mà không hardcode project version để có thể thử CLI override.

### 8.1. Cấu trúc project

~~~text
version-properties-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/versioning/App.java
    │   └── filtered-resources/
    │       └── version-info.properties
    └── test/
        └── java/com/example/versioning/AppTest.java
~~~

`src/main/filtered-resources` là một **folder được chọn có chủ đích** để filter riêng một file dạng text. Ta không bật filtering cho mọi binary asset trong `src/main/resources`, tránh làm hỏng ảnh, font, zip, certificates hoặc các file không phải text.

### 8.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>version-properties-demo</artifactId>
    <version>${revision}</version>
    <packaging>jar</packaging>

    <properties>
        <revision>1.0.0-SNAPSHOT</revision>

        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>

        <commons.lang3.version>3.17.0</commons.lang3.version>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>

        <maven.resources.plugin.version>3.3.1</maven.resources.plugin.version>
        <maven.compiler.plugin.version>3.13.0</maven.compiler.plugin.version>
        <maven.surefire.plugin.version>3.5.2</maven.surefire.plugin.version>
        <maven.jar.plugin.version>3.4.2</maven.jar.plugin.version>
        <exec.maven.plugin.version>3.7.0</exec.maven.plugin.version>
        <flatten.maven.plugin.version>1.8.0</flatten.maven.plugin.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>${commons.lang3.version}</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.jupiter.version}</version>
                <scope>test</scope>
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
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
            </resource>
            <resource>
                <directory>src/main/filtered-resources</directory>
                <filtering>true</filtering>
            </resource>
        </resources>

        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>${maven.resources.plugin.version}</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>${maven.compiler.plugin.version}</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>${maven.surefire.plugin.version}</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>${maven.jar.plugin.version}</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>${exec.maven.plugin.version}</version>
                <configuration>
                    <mainClass>com.example.versioning.App</mainClass>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>flatten-maven-plugin</artifactId>
                <version>${flatten.maven.plugin.version}</version>
                <configuration>
                    <updatePomFile>true</updatePomFile>
                    <flattenMode>resolveCiFriendliesOnly</flattenMode>
                </configuration>
                <executions>
                    <execution>
                        <id>flatten</id>
                        <phase>process-resources</phase>
                        <goals>
                            <goal>flatten</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>flatten.clean</id>
                        <phase>clean</phase>
                        <goals>
                            <goal>clean</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **POM đầy đủ** cho Maven 3.9.x. Một số plugin có phase binding mặc định theo `packaging=jar`; `pluginManagement` pin version cho chúng. `exec-maven-plugin` không bind thêm goal vào default lifecycle, nên **chỉ chạy khi gọi `mvn exec:java`**. `flatten-maven-plugin` có execution ở `process-resources` và `clean` như minh họa.

### 8.3. Đọc POM theo từng lớp

**Lớp một — project version:**

~~~xml
<version>${revision}</version>
...
<revision>1.0.0-SNAPSHOT</revision>
~~~

Maven resolve effective GAV của project thành `com.example:version-properties-demo:1.0.0-SNAPSHOT` khi không có CLI override.

**Lớp hai — dependency versions:**

~~~xml
<commons.lang3.version>3.17.0</commons.lang3.version>
<junit.jupiter.version>5.11.4</junit.jupiter.version>
~~~

Các giá trị được dùng trong dependencyManagement. Child `<dependencies>` của POM không cần copy lại version.

**Lớp ba — plugin versions:** các property `maven.*.plugin.version` được tham chiếu từ pluginManagement; Exec/Flatten được tham chiếu từ `<plugins>`. Không được tự động áp một property cho plugin nào đó nếu `<version>${...}</version>` không được khai báo.

**Lớp bốn — resource filtering:** file `version-info.properties` ở nguồn chứa placeholder và được Resources Plugin nội suy lúc build.

**Lớp năm — publication POM:** Flatten Plugin ở `process-resources` tạo `.flattened-pom.xml`, với `resolveCiFriendliesOnly` nhằm giải `${revision}`, `${sha1}`, `${changelist}` và giữ lại phần POM còn lại, để install/deploy không phát hành một project version chưa resolve.

### 8.4. File src/main/filtered-resources/version-info.properties

Tạo chính xác:

~~~properties
project.version=${project.version}
commons.lang3.version=${commons.lang3.version}
~~~

Đây là **source template**, không phải content cuối trong `target/classes`. Với POM mặc định, sau khi Resources Plugin filter:

~~~properties
project.version=1.0.0-SNAPSHOT
commons.lang3.version=3.17.0
~~~

Mọi giá trị trong demo đều là ASCII nên cách đọc file qua Java `Properties.load(InputStream)` là xác định. Nếu dùng version text có ký tự đặc biệt, phải hiểu syntax/escaping của `.properties`, đừng coi mọi chuỗi Unicode là an toàn khi nối trực tiếp.

### 8.5. File src/main/java/com/example/versioning/App.java

~~~java
package com.example.versioning;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Locale;
import java.util.Properties;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    private static Properties readVersionInfo() {
        try (InputStream in =
                App.class.getResourceAsStream("/version-info.properties")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing /version-info.properties");
            }

            Properties values = new Properties();
            values.load(in);
            return values;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    public static String normalize(String input) {
        return StringUtils.upperCase(
                StringUtils.trimToEmpty(input), Locale.ROOT);
    }

    public static String summary() {
        Properties values = readVersionInfo();
        return "Project: " + values.getProperty("project.version")
                + "\nLibrary: "
                + values.getProperty("commons.lang3.version")
                + "\nNormalized: " + normalize("maven");
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
~~~

Điểm cần hiểu:

1. `StringUtils` là class thật của Commons Lang; Maven lấy nó theo dependency version đã resolve.
2. `StringUtils.upperCase(..., Locale.ROOT)` giúp kết quả uppercase không phụ thuộc locale mặc định của máy.
3. `App` không thể truy cập POM runtime trực tiếp; resource đã được **lọc tại build time** mang các version values.
4. `getResourceAsStream` đọc resource từ classpath, nên chạy bằng Exec Maven Plugin khi đã compile được.
5. Nếu resource thiếu, code ném exception thay vì âm thầm in `null`.
6. `summary()` chỉ in phiên bản **không nhạy cảm**; không áp mẫu in này cho password/token.
7. Vì dùng `\n` trong Java string, chuỗi kết quả có ba dòng trước khi `println` thêm newline cuối.

### 8.6. File src/test/java/com/example/versioning/AppTest.java

~~~java
package com.example.versioning;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AppTest {

    @Test
    void normalizesUsingLibrary() {
        assertEquals("MAVEN", App.normalize(" maven "));
    }

    @Test
    void filteredVersionsAreAvailable() {
        String result = App.summary();

        assertTrue(result.contains("Project: "));
        assertTrue(result.contains("Library: "));
        assertTrue(result.contains("Normalized: MAVEN"));
        assertFalse(result.contains("${"));
    }
}
~~~

Test 1 xác nhận Commons Lang thật sự tham gia xử lý chuỗi. Test 2 xác nhận filtering đã tạo nội dung không còn `${...}` chưa được nội suy và app đọc được resource trên classpath.

Test **không hardcode** version `1.0.0-SNAPSHOT` hoặc `3.17.0`, nên vẫn qua khi chạy Maven với CLI overrides hợp lệ. Trong một sản phẩm cần kiểm soát release chặt chẽ, có thể thêm kiểm tra version policy riêng từ release metadata.

### 8.7. Build và chạy

Từ thư mục `version-properties-demo`:

~~~bash
mvn -version
java -version
mvn -B clean verify
~~~

Với Maven 3.9+, Java 17+ và repository cần thiết, kết quả mong đợi:

- Maven resolve project version `1.0.0-SNAPSHOT`.
- Resources Plugin tạo `target/classes/version-info.properties`.
- Compiler Plugin compile `App.java` theo release 17.
- Surefire chạy **2 JUnit 5 test methods**, kết quả pass.
- Maven JAR Plugin tạo `target/version-properties-demo-1.0.0-SNAPSHOT.jar`.
- Flatten Plugin tạo file `.flattened-pom.xml` dùng cho POM publication; nguồn `pom.xml` vẫn là POM developer chỉnh sửa.
- Lệnh kết thúc với `BUILD SUCCESS` nếu tests/plugins chạy thành công.

Để chạy chương trình mà không phải tự dựng `java -cp` và tìm từng JAR trong local Maven repository:

~~~bash
mvn -q exec:java
~~~

**Ba dòng stdout do `App` in**, khi dùng default properties:

~~~text
Project: 1.0.0-SNAPSHOT
Library: 3.17.0
Normalized: MAVEN
~~~

Nếu plugin/Maven in logs thêm, đó không phải một phần của ba dòng application stdout. Exec Plugin goal `exec:java` chạy Java main class trong Maven JVM với project dependencies trên classpath; demo không chứa `System.exit` hoặc tác vụ background. Vì không thêm `Main-Class` manifest và không gộp Commons Lang vào JAR, **không khẳng định `java -jar target/version-properties-demo-1.0.0-SNAPSHOT.jar` chạy độc lập**.

### 8.8. Kiểm tra version bằng Maven CLI

~~~bash
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
mvn -q help:evaluate -Dexpression=commons.lang3.version -DforceStdout
mvn -q help:evaluate -Dexpression=junit.jupiter.version -DforceStdout
~~~

Giá trị dự kiến lần lượt:

~~~text
1.0.0-SNAPSHOT
3.17.0
5.11.4
~~~

Đây là **ba lệnh độc lập**, nên ba dòng trên là các giá trị riêng được kỳ vọng, không phải stdout của một lệnh duy nhất. Với một số phiên bản Maven Help Plugin, console có thể có formatting/logs bổ sung; dùng `-DforceStdout` khi cần lấy kết quả expression.

`help:evaluate` cho biết property được nội suy; nó **không chứng minh** cuối cùng dependency resolver đã chọn đúng cùng version nếu có dependencyManagement, conflicts, classifiers hoặc active profile khác. Muốn biết version resolved, xem thêm `dependency:tree`.

### 8.9. Thử override project và library version cùng lúc

~~~bash
mvn -B -Drevision=2.1.0-SNAPSHOT -Dcommons.lang3.version=3.16.0 clean verify
mvn -q -Drevision=2.1.0-SNAPSHOT -Dcommons.lang3.version=3.16.0 exec:java
~~~

**Stdout từ App** sau lượt build/exec đó:

~~~text
Project: 2.1.0-SNAPSHOT
Library: 3.16.0
Normalized: MAVEN
~~~

Maven đã dùng:
- `revision=2.1.0-SNAPSHOT` cho project version.
- `commons.lang3.version=3.16.0` để resolve Commons Lang và lọc resource.
- `junit.jupiter.version=5.11.4` từ POM vì không override nó.

**Các `-D` ở đây chỉ áp dụng cho invocation tương ứng.** Chúng không ghi đè `pom.xml`. Sau đó, nếu chạy `mvn clean verify` không có `-D`, effective version quay về các defaults trong POM. Luôn dùng `clean` khi muốn không có resource/JAR cũ làm bằng chứng sai.

## 9. Property được kế thừa qua parent POM như thế nào?

Trong multi-module build, đặt properties chung trong parent POM để child modules **kế thừa** chúng. Ví dụ một parent:

~~~xml
<project>
    ...
    <groupId>com.example.platform</groupId>
    <artifactId>platform-parent</artifactId>
    <version>${revision}</version>
    <packaging>pom</packaging>

    <properties>
        <revision>1.2.0-SNAPSHOT</revision>
        <commons.lang3.version>3.17.0</commons.lang3.version>
    </properties>
    ...
</project>
~~~

Child khai báo:

~~~xml
<parent>
    <groupId>com.example.platform</groupId>
    <artifactId>platform-parent</artifactId>
    <version>${revision}</version>
    <relativePath>../pom.xml</relativePath>
</parent>
<artifactId>application</artifactId>
~~~

Đây là **hai mảnh POM** minh họa quan hệ parent/child, không phải hai POM độc lập đầy đủ. Maven CI-friendly support cho `${revision}` được tài liệu hóa cả ở parent version của child.

**Những điều cần nhớ:**

- Parent chứa property; child kế thừa property theo quy tắc effective model.
- Parent có thể đồng thời là aggregator qua `<modules>`, nhưng đó là **một vai trò khác**.
- Parent không tự thêm dependency vào child nếu chỉ có dependencyManagement.
- Khi child dùng `${commons.lang3.version}` trong đúng cấu hình, nó nhận giá trị đã được resolve trong effective model.
- Child có thể định nghĩa lại property cùng tên; override phải có chủ đích.
- CLI `-Dcommons.lang3.version=...` có thể ảnh hưởng nhiều modules trong cùng reactor, nên CI cần đánh giá tác động toàn hệ thống.

### 9.1. Parent không đồng nghĩa aggregator

Một parent POM dùng chung có thể được publish và kế thừa bởi nhiều repositories, dù nó không có `<modules>`. Ngược lại, aggregator có `<modules>` để thu thập modules vào reactor nhưng các child có thể kế thừa một parent khác.

Vì vậy:

- **Inheritance** mang properties/dependencyManagement/pluginManagement xuống child.
- **Aggregation** chỉ định tập modules cần build cùng nhau.
- **Dependency** tạo quan hệ classpath/build graph giữa modules.

Các khái niệm này không thể thay thế bằng một property duy nhất.

## 10. Quản lý version cho sibling dependencies: dùng `${project.version}`

Một multi-module release thường muốn các module được build theo cùng một project version.

Giả sử:

~~~text
parent version: 1.2.0-SNAPSHOT
shared-api:     1.2.0-SNAPSHOT
backend:        1.2.0-SNAPSHOT
~~~

`backend` phụ thuộc vào `shared-api`. Trong child POM `backend`, Maven CI-friendly guide khuyến nghị:

~~~xml
<dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>shared-api</artifactId>
    <version>${project.version}</version>
</dependency>
~~~

Ở đây `${project.version}` là **effective version của current Maven project**. Nếu backend và shared-api cùng version, nó chọn đúng sibling artifact.

**Không dùng `${revision}` thay cho `${project.version}` trong sibling dependency version theo hướng dẫn Maven CI-friendly multi-module**, vì có những giới hạn nội suy/kết hợp model khiến kiểu đó fail. Maven guide nêu rõ cách đúng là `${project.version}`.

Nếu sibling không cùng version, đừng dùng `${project.version}`; nên khai báo/management đúng version của library đó, ví dụ `${shared.api.version}` trong dependencyManagement.

### 10.1. Mẫu sơ đồ

~~~text
parent pom.xml
  <revision>1.2.0-SNAPSHOT</revision>
  <version>${revision}</version>
  <dependencyManagement>
      commons-lang3 -> ${commons.lang3.version}
  </dependencyManagement>
         |
         +--- shared-api/pom.xml (parent = ${revision})
         |
         +--- backend/pom.xml (parent = ${revision})
                |
                +--- dependency shared-api:${project.version}
                +--- dependency commons-lang3
~~~

Reactor biết build `shared-api` trước `backend` vì có **actual dependency**. Chỉ lưu version trong property mà không khai báo dependency thì không tạo reactor sorting edge.

## 11. Có nên dùng `${project.version}` cho mọi dependency?

**Không.** `${project.version}` chỉ thích hợp khi dependency thật sự cùng release version với current project, thường là sibling modules trong cùng release train.

Ví dụ sai về ý nghĩa:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>${project.version}</version>
</dependency>
~~~

Nếu project là `1.2.0-SNAPSHOT`, Maven sẽ cố tìm Commons Lang `1.2.0-SNAPSHOT`, không phải `3.17.0`. Đây là khác biệt giữa **project version** và **external library version**.

Dùng:

~~~xml
<version>${commons.lang3.version}</version>
~~~

hoặc quản lý qua dependencyManagement. Không đồng bộ phiên bản giữa các sản phẩm độc lập một cách máy móc.

### 11.1. Project version và Java runtime version khác nhau

`<revision>1.2.0-SNAPSHOT</revision>` là phiên bản artifact. `<maven.compiler.release>17</maven.compiler.release>` là target của Java compiler; hai giá trị không liên quan.

Một POM chứa `<java.version>17</java.version>` **không tự cài JDK 17**. Maven vẫn cần chạy bằng JDK/toolchain thích hợp. Dùng `mvn -version` để xem Maven JVM, kiểm tra compiler toolchain nếu có và thử chạy compiled Java class trên runtime mục tiêu.

## 12. Dùng BOM để quản lý một nhóm thư viện có cùng compatibility matrix

Một số ecosystem có **Bill of Materials (BOM)** để quản lý versions của một nhóm artifacts. Thay vì tự tạo hàng chục version properties cho các thư viện thuộc cùng một platform, có thể import BOM do project đó phát hành.

Mảnh POM minh họa:

~~~xml
<properties>
    <junit.bom.version>5.11.4</junit.bom.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Một dependency test được BOM quản lý:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

**BOM import không tự thêm JUnit vào test classpath**, chỉ cung cấp dependencyManagement. Module cần test vẫn phải khai báo dependency thực.

### 12.1. BOM không giống parent

- **Parent POM:** cơ chế kế thừa POM model/config/plugins/properties.
- **BOM import:** đưa tập dependencyManagement của BOM vào dependency management của current POM, không kéo theo toàn bộ pluginManagement/config của BOM.
- **Property:** giá trị như `${junit.bom.version}` để chọn bản BOM.

Nếu dự án đã dùng Spring Boot starter parent hoặc một platform BOM, hãy xem các versions đã được quản lý trước khi tự thêm properties riêng. Overriding một library đơn lẻ có thể **phá compatibility matrix** của platform. Nên nâng BOM theo bộ trừ khi có lý do đã được kiểm thử.

### 12.2. Chọn BOM hay properties riêng?

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Một library độc lập | Một entry dependencyManagement, có thể thêm property |
| Nhiều artifacts cùng family cần lockstep | BOM của nhà cung cấp nếu có |
| Spring Boot/Spring Cloud/Quarkus ecosystem | Platform BOM/parent được khuyến nghị |
| Plugin versions | pluginManagement, **không phải** BOM dependencies |
| Project release version | `${revision}`/project.version, **không phải** BOM |
| Thư viện có API không tương thích giữa versions | Theo compatibility matrix, integration tests |

## 13. Khi nào properties trùng tên bị ghi đè?

Trong POM inheritance, parent có thể định nghĩa:

~~~xml
<properties>
    <commons.lang3.version>3.17.0</commons.lang3.version>
</properties>
~~~

Child có thể định nghĩa lại:

~~~xml
<properties>
    <commons.lang3.version>3.16.0</commons.lang3.version>
</properties>
~~~

Tùy cấu hình được kế thừa/nội suy, child dùng giá trị của property override. Điều này là công cụ hữu ích cho module ngoại lệ, nhưng có thể phá tính nhất quán nếu không được review.

Các nguồn có thể tác động effective value:

1. Properties trong parent POM.
2. Properties trong child POM.
3. Maven profiles được kích hoạt.
4. Maven CLI user properties qua `-D`.
5. Environment/system/settings properties khi được tham chiếu bằng tên tương ứng.

**Không cần nhớ một quy tắc precedence “mọi loại property” bằng cảm tính**. Khi có nhiều sources hoặc profiles, hãy kiểm chứng **giá trị cuối** bằng `mvn help:evaluate` và POM hiệu lực bằng `mvn help:effective-pom`.

Với CLI `-Dcommons.lang3.version=3.16.0`, Maven user property thường có ưu tiên rất cao khi nội suy project configuration. Đó là cơ chế thuận tiện cho CI nhưng cũng có thể làm build khác POM được commit.

### 13.1. Không nhầm tên property

Các tên sau là **khác nhau**:

~~~text
commons.lang3.version
commons-lang3.version
commons.lang.version
commonsLang3Version
~~~

Nếu POM khai báo một tên nhưng sử dụng tên khác, Maven có thể để lại `${...}` chưa resolve hoặc báo version không hợp lệ. Đừng “fix” bằng cách thay nhãn tùy ý trong dependency XML; hãy thống nhất convention và kiểm `help:evaluate`.

### 13.2. Child override có thể thay đổi behavior của parent config

Maven xử lý properties trong effective model theo inheritance/interpolation rules. Một plugin configuration được kế thừa từ parent và chứa `${commons.lang3.version}` có thể nhận giá trị child override.

Vì thế một property name mang nghĩa rộng như `version` rất nguy hiểm: module con có thể vô tình thay đổi cấu hình plugin hoặc dependency ở những nơi khó thấy. Dùng tên rõ theo owner và review effective POM của module có thay đổi.

## 14. PluginManagement có thể được parent kế thừa

Một parent có:

~~~xml
<properties>
    <maven.compiler.plugin.version>3.13.0</maven.compiler.plugin.version>
    <maven.surefire.plugin.version>3.5.2</maven.surefire.plugin.version>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>${maven.compiler.plugin.version}</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${maven.surefire.plugin.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Các child kế thừa management phù hợp. Nhưng nếu một module cần một plugin ngoài default lifecycle, vẫn phải kích hoạt nó:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>exec-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Trong ví dụ fragment trên, **chỉ khai báo Exec Plugin không tự chạy một goal**; phải có execution hoặc CLI. Fragment cũng cần có version được quản lý trong parent nếu không muốn plugin version thiếu. Sự khác biệt giữa **quản lý version** và **thực thi goal** rất quan trọng.

### 14.1. Plugins không phải application dependencies

Không gộp plugin versions vào một `${commons.lang3.version}` chỉ vì plugin của bạn có dependency cùng thư viện. Maven plugin chạy trong **Maven plugin classpath**, còn application dependencies chạy trong **project classpath**. Hai classpaths và quy trình nâng cấp khác nhau.

Không dùng dependencyManagement để khóa plugin version: Maven có `<pluginManagement>` riêng.

## 15. CI-friendly version khi install/deploy: vì sao cần Flatten Maven Plugin?

Khi chỉ chạy:

~~~bash
mvn -B clean verify
~~~

project version `${revision}` có thể được Maven nội suy để tạo artifact `target/...-1.0.0-SNAPSHOT.jar`. Nhưng **POM được publish** là metadata mà các Maven consumer khác sẽ đọc.

Nếu install/deploy POM chứa phiên bản CI-friendly `${revision}` còn chưa được giải một cách tiêu thụ được, một project khác tải artifact có thể gặp lỗi phân giải parent/artifact version. Tài liệu Maven CI-friendly khuyến nghị **Flatten Maven Plugin** để phát hành POM đã xử lý các placeholders.

Trong demo, cấu hình:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>flatten-maven-plugin</artifactId>
    <version>1.8.0</version>
    <configuration>
        <updatePomFile>true</updatePomFile>
        <flattenMode>resolveCiFriendliesOnly</flattenMode>
    </configuration>
    <executions>
        <execution>
            <id>flatten</id>
            <phase>process-resources</phase>
            <goals>
                <goal>flatten</goal>
            </goals>
        </execution>
        <execution>
            <id>flatten.clean</id>
            <phase>clean</phase>
            <goals>
                <goal>clean</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

### 15.1. `resolveCiFriendliesOnly` có nghĩa gì?

Theo Flatten Plugin, mode này chủ yếu giải **CI-friendly variables** `${revision}`, `${sha1}`, `${changelist}` và giữ lại các phần khác của POM. Không nhầm nó với mode flatten mặc định có thể rút gọn nhiều developer/build elements.

`<updatePomFile>true</updatePomFile>` làm MavenProject tham chiếu flattened POM cho bước install/deploy; đặc biệt quan trọng khi project có `packaging=pom` (parent/BOM), vì plugin mặc định không luôn thay POM file của packaging `pom` nếu không bật tham số này.

### 15.2. File `.flattened-pom.xml` là output, không phải nguồn chính

Một lượt build có thể tạo:

~~~text
version-properties-demo/
├── pom.xml                 # POM developer chỉnh sửa
├── .flattened-pom.xml      # POM đã xử lý để publish
└── target/
    └── version-properties-demo-1.0.0-SNAPSHOT.jar
~~~

Không nên sửa `.flattened-pom.xml` bằng tay để quản lý version. Sửa `pom.xml` và rebuild. Có thể đưa generated flattened POM vào `.gitignore` theo convention; plugin `flatten:clean` được cấu hình dọn file khi thực thi clean phase.

### 15.3. Install và kiểm chứng

Từ demo:

~~~bash
mvn -B clean install
~~~

Nếu dependencies/plugins/repositories khả dụng, Maven tạo artifact, chạy tests, dùng Flatten Plugin và cài bản vào local repository. Artifact coordinate default:

~~~text
com.example:version-properties-demo:1.0.0-SNAPSHOT
~~~

Đây là **local installation**, không phải deploy lên môi trường ứng dụng, và cũng không tự đẩy artifact lên remote repository.

Khi release thật, hãy kiểm tra POM đã install/deploy không còn placeholder CI-friendly chưa giải ở những vị trí cần phiên bản cụ thể, và một consumer tối giản có thể resolve artifact thành công.

### 15.4. Vì sao không chỉ sửa property revision sau khi build?

Nếu `mvn verify` tạo JAR version `1.0.0-SNAPSHOT`, sau đó sửa `<revision>` thành `1.1.0-SNAPSHOT` và chạy `mvn install` mà không clean/verify tương ứng, có nguy cơ metadata/artifact/test không cùng bộ đầu vào.

Release pipeline nên **build, verify và publish cùng revision và dependency properties** trong một workflow có kiểm soát, ghi lại commit và checksum.

## 16. Parent POM và publication trong multi-module CI-friendly builds

Với parent:

~~~xml
<groupId>com.example.platform</groupId>
<artifactId>platform-parent</artifactId>
<version>${revision}</version>
<packaging>pom</packaging>
~~~

và child có parent version `${revision}`, cả parent/child phải được phát hành bằng các POM **có thể tiêu thụ**. Vì parent POM là artifact riêng, nó cũng cần handling publication đúng.

**Không chỉ flatten child JAR rồi quên parent** nếu consumer POM vẫn có parent relationship tới một POM chưa publish hoặc publish sai version. Trong multi-module, review:

1. Parent POM được build/installed/deployed ở version nào?
2. Child `<parent>` được resolve thành version nào trong published POM?
3. Dependencies giữa siblings dùng `${project.version}` đúng chưa?
4. Flatten Plugin có được cấu hình/inherited đúng module nào không?
5. `updatePomFile=true` có hiệu lực cho packaging `pom` khi cần không?
6. `dependencyManagement`/BOM/versions trong POM được publish có còn resolve được không?
7. Consumer build có thành công từ một local repo sạch không?

**Build reactor thành công không tự chứng minh published POM hợp lệ**. Reactor có thể resolve parent/siblings từ source trong cùng build, trong khi consumer ở repository khác chỉ thấy POM đã publish.

## 17. `project.version`, `pom.version`, `revision` và version resource

Trong Maven:

- `${project.version}` là tham chiếu model tới effective project version.
- `${revision}` là CI-friendly placeholder/property do bạn cấp giá trị.
- `${pom.version}` là cách tham chiếu lịch sử/alias trong một số bối cảnh; cho source POM mới nên ưu tiên `${project.version}` vì rõ nghĩa.
- `${commons.lang3.version}` là custom property của dependency.
- `System.getProperty("project.version")` trong Java process **không tự** chứa Maven project version.

Đây là lý do demo dùng Maven Resources Plugin để tạo `version-info.properties` từ `${project.version}`. Nếu ứng dụng cần đọc version runtime, phải **chủ động đóng gói metadata** hoặc dùng manifest entries/plugin/resource filtering, không cho rằng Maven POM có sẵn trên runtime classpath.

### 17.1. Filtering cần được giới hạn

Không nên bật `<filtering>true</filtering>` cho mọi `src/main/resources` nếu có hình ảnh, tệp chứng chỉ, `.zip`, binary protobuf hay assets khác. Maven filtering thay placeholders trong **text files**; làm điều đó trên binary có thể phá bytes.

Trong POM demo, tách `src/main/filtered-resources` để filter text và giữ `src/main/resources` không filter. Nếu một framework cũng dùng `${...}` trong resource runtime (chẳng hạn config templates), Maven filtering có thể vô tình thay chuỗi mà framework cần giữ. Nên chọn delimiter hoặc thư mục riêng theo project policy.

## 18. Kiểm tra kết quả qua effective POM và dependency tree

Sau mỗi thay đổi version property, ba loại bằng chứng rất hữu ích:

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
~~~

### 18.1. Effective POM

`help:effective-pom` cho biết model sau inheritance, active profiles và interpolation/management theo cơ chế Maven. Dùng nó để tìm:

- Version project/parent.
- Values của `commons.lang3.version`, `junit.jupiter.version`.
- DependencyManagement entries.
- Plugin versions trong pluginManagement và build/plugins.
- Active profiles có thay version/config không.

Với multi-module, cần xem output cho **đúng module**, không chỉ nhìn một root snippet.

### 18.2. Dependency tree

`dependency:tree` giúp xem **resolved graph** bao gồm scope, transitives, mediation và conflict. Với demo, ở một nhánh có thể thấy:

~~~text
com.example:version-properties-demo:jar:1.0.0-SNAPSHOT
  org.apache.commons:commons-lang3:jar:3.17.0:compile
  org.junit.jupiter:junit-jupiter:jar:5.11.4:test
  ...
~~~

Đây là **sơ đồ rút gọn các artifacts quan trọng**, không phải nguyên văn full Maven stdout. JUnit còn kéo các dependencies transitively khác.

Nếu có hai thư viện kéo `commons-lang3` versions khác nhau, chỉ nhìn property chưa đủ: Maven dependency mediation/dependencyManagement mới quyết định resolved version. Thay `${commons.lang3.version}` trong POM không biến tất cả transitives thành cùng một version nếu quản lý graph chưa đúng.

### 18.3. DependencyManagement ảnh hưởng cả transitive versions

Một dependencyManagement entry có thể kiểm soát version được sử dụng cho một dependency dù nó đến từ transitive paths theo Maven rules. Nhưng nó **không tự thêm bất kỳ class nào**.

Với nhiều version conflicts, kiểm tra dependency tree và chọn version tương thích với mọi direct/transitive consumers. Khi cần, thêm dependencyManagement/exclusions có chủ đích; không sửa dependency tree bằng cách copy một property tới tất cả nơi cho giống nhau mà chưa test.

## 19. Maven Versions Plugin: cập nhật property có kiểm soát

MojoHaus **Versions Maven Plugin** cung cấp các goals để xem/đề xuất/nâng versions. Không nên nhầm với Maven Core. Một số goal tiêu biểu:

| Goal | Mục đích |
| --- | --- |
| `versions:display-dependency-updates` | Xem những dependency versions có cập nhật |
| `versions:display-plugin-updates` | Xem versions plugin có thể cập nhật |
| `versions:display-property-updates` | Báo cáo những properties liên quan version có thể nâng |
| `versions:update-properties` | Cập nhật properties tới các versions mới theo cấu hình/rules |
| `versions:set-property` | Đặt giá trị property theo `newVersion`; **không tự sanity-check compatibility** |
| `versions:set` | Cập nhật project version theo cơ chế plugin |
| `versions:update-child-modules` | Hỗ trợ đồng bộ parent references của child modules trong một số workflow |

Ví dụ **lệnh để thử trên branch riêng** (không tự động chạy khi bạn đọc bài):

~~~bash
mvn -N org.codehaus.mojo:versions-maven-plugin:2.22.0:set-property -Dproperty=commons.lang3.version -DnewVersion=3.16.0
~~~

Lệnh này yêu cầu Versions Plugin sửa property trong POM. `set-property` **không tự chứng minh** dependency sẽ compile/test được sau khi đổi; theo tài liệu MojoHaus, goal này đặt version mà không có compatibility sanity checks như các goal update có lọc range.

Sau đó:

~~~bash
mvn -B clean verify
mvn dependency:tree
~~~

Và xem Git diff để biết POM nào thay đổi, có backup file nào được tạo. **Đây là một ví dụ downgrade có chủ đích để dễ quan sát property change**, không phải lời khuyên dùng bản cũ hơn trong sản phẩm. Khi nâng cấp thật, chọn version đã được phê duyệt và đáp ứng security policy.

### 19.1. Khác biệt giữa `-Dproperty=...` và `-Dcommons.lang3.version=...`

- `mvn -Dcommons.lang3.version=3.16.0 verify`: **override giá trị trong một Maven invocation**, không sửa nguồn POM.
- `mvn versions:set-property -Dproperty=commons.lang3.version -DnewVersion=3.16.0`: **công cụ chỉnh POM**, có thể tạo thay đổi được commit/review.

Đừng nhầm hai công việc. Một release pipeline dùng `-D` mà không ghi metadata có thể khó tái tạo hơn một PR nâng property version đã review/test.

### 19.2. Không update mọi thứ lên latest trong một bước

Nâng hàng loạt library, compiler, Surefire, JDK target, parent/BOM cùng lúc làm khó xác định nguồn regression. Một quy trình hợp lý:

1. Lấy reports các versions có cập nhật.
2. Kiểm tra release notes, CVEs, API compatibility, JDK requirement.
3. Chọn một nhóm thay đổi liên quan.
4. Cập nhật property hoặc BOM/version management.
5. Chạy unit/integration tests và packaging checks.
6. Xem `dependency:tree`, effective POM và test reports.
7. Review Git diff trước khi merge/publish.

Không dùng Versions Plugin như “bảo đảm library mới nhất luôn an toàn”. Nó giúp thao tác version, không thay kiểm thử/QA.

## 20. Properties và version ranges không tạo reproducibility tự động

Một property trông gọn:

~~~xml
<properties>
    <commons.lang3.version>[3.16.0,4.0.0)</commons.lang3.version>
</properties>
~~~

nhưng giá trị này **là version range**, không phải một version chính xác. Maven resolver có thể chọn release khác khi repository metadata thay đổi. Từ cùng Git commit, hai lượt build có thể ra dependencies khác nhau.

Để release có thể tái hiện:

- Pin phiên bản cụ thể cho dependencies/plugins.
- Không dùng dynamic ranges trừ khi có lý do, audit và lock/resolve policy.
- Hạn chế SNAPSHOT trong artifacts phát hành chính thức.
- Pin Maven/JDK versions trong CI.
- Ghi effective version overrides (`-D`) vào build metadata không nhạy cảm.
- Chạy `mvn clean verify` và kiểm tra resolved graph.
- Phát hành artifact cùng POM đã xử lý `${revision}`.
- Lưu artifact checksum/SBOM/provenance theo policy.

**Chuyển version từ số literal sang property không làm một dependency trở nên ít rủi ro hơn.** Giá trị được resolve vẫn cần được quản lý theo release và vulnerability policy.

## 21. Secrets không thuộc phiên bản, đừng lưu trong properties để tiện

`<properties>` thích hợp cho **non-secret build configuration**, ví dụ version dependencies, Java release hoặc feature flags không nhạy cảm. Nó **không** phải nơi lưu username/password/token chỉ vì cú pháp dễ dùng.

Không viết:

~~~xml
<properties>
    <repository.password>real-secret-here</repository.password>
</properties>
~~~

vào POM được commit. Maven repository credentials thuộc cấu hình Maven settings/secret management có quyền phù hợp; runtime application secrets thuộc runtime secret injection mechanism. Một `-Dpassword=...` cũng có thể xuất hiện trong process list/logs, nên không mặc định coi CLI là chỗ an toàn để đưa credential.

Khi demo lọc version vào resource, chỉ lọc các thông tin public/non-secret. Không lọc token/API key vào JAR rồi “xóa file sau build”: bytes có thể đã nằm trong artifact cuối.

## 22. Parent POM, BOM và version property xung đột

Ví dụ:
- Corporate parent quản lý `commons-lang3:3.16.0`.
- Module con định nghĩa `<commons.lang3.version>3.17.0</commons.lang3.version>`.
- Imported BOM có thể cũng quản lý Commons Lang một bản khác.
- CLI CI truyền `-Dcommons.lang3.version=3.18.0`.

Trong tình huống này, không đủ để nói “một tên property là single source of truth”. Cần xác định:

1. DependencyManagement entry nào có hiệu lực trong module?
2. BOM nào được import, version nào, thứ tự/precedence theo Maven model?
3. CLI/active profile có override property nào không?
4. Direct dependency có explicit version làm khác managed version không?
5. Resolver đã chọn artifact nào cho compile/runtime/test?
6. Có modules khác dùng parent version/property override khác không?

Để kiểm chứng:

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn -q help:evaluate -Dexpression=commons.lang3.version -DforceStdout
~~~

Đặc biệt với ecosystems có BOM compatibility matrix, đừng override riêng một dependency trong nhóm mà không hiểu tác động đến các dependencies khác.

## 23. Nâng project version theo release: chọn cơ chế phù hợp

Có hai chiến lược điển hình:

### 23.1. Version được viết literal trong POM

~~~xml
<version>1.0.0-SNAPSHOT</version>
~~~

Thay đổi project version được thực hiện qua plugin/công cụ như Versions Plugin, rồi commit POM changes. Đây là mô hình truyền thống, dễ hiểu, không bắt buộc dùng Flatten Plugin chỉ vì có project version literal.

### 23.2. Version được đại diện bởi CI-friendly `${revision}`

~~~xml
<version>${revision}</version>
<properties>
    <revision>1.0.0-SNAPSHOT</revision>
</properties>
~~~

Release CI có thể cấp:

~~~bash
mvn -B -Drevision=1.0.0 clean verify
~~~

và tiếp tục install/deploy **cùng revision** trong pipeline với Flatten Plugin được cấu hình đúng. Nếu chỉ đổi revision ở một lệnh mà bước publish chạy revision khác, artifact/version metadata sẽ lệch.

**Đừng coi version property như công cụ tự đánh tag Git, tự tăng version hoặc tự phát hành**. Cần thêm release policy, repository permissions, changelog, tests và provenance.

### 23.3. Khi nào dùng literal, khi nào dùng revision?

| Yêu cầu | Lựa chọn hợp lý |
| --- | --- |
| Library đơn giản, version đổi ít | Version literal hoặc workflow Versions Plugin |
| CI cần tạo cùng source với release/snapshot version khác nhau | `${revision}` |
| Multi-module release train muốn một revision cho cả reactor | `${revision}` + parent child references và `${project.version}` |
| Publish POM tiêu thụ được với CI-friendly placeholders | Flatten Maven Plugin |
| Các modules có versions độc lập | Version riêng theo module/management, không ép mọi module cùng `${revision}` |
| Chỉ muốn đổi dependency version | `<properties>` + dependencyManagement, không cần đổi project version |

## 24. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `${commons.lang3.version}` còn nguyên | Property sai tên/chưa được define, interpolation sai bối cảnh | Kiểm tra property spelling, `help:evaluate` |
| `Dependency version is missing` | Dependency không có version và không match dependencyManagement | Thêm managed entry đúng GAV/type/classifier hoặc explicit version |
| `Could not find artifact` với version lạ | Property được override sai hoặc range/SNAPSHOT khác | Xem effective POM, dependency tree |
| Parent version không resolve | Dùng custom `${application.version}` trong project version | Dùng CI-friendly `${revision}` hoặc literal theo Maven version |
| Sibling dependency fail dù parent revision đúng | Dùng `${revision}` ở sibling dependency hoặc GAV mismatch | Dùng `${project.version}` cho modules cùng version |
| Library bị đổi ngoài ý muốn | CLI `-D`/child override/profile khác | Kiểm tra active profiles và effective property |
| POM có property nhưng library không có | Chỉ define property/dependencyManagement, không thêm dependency | Thêm `<dependencies>` thực tế |
| Compiler plugin version thay đổi | Version property không được nối vào pluginManagement/plugins | Pin compiler version trong plugin config |
| JUnit không chạy | Surefire cũ/không phù hợp JUnit platform hoặc tests bị skip | Pin Surefire, kiểm reports và naming |
| Java source dùng API mới nhưng runtime cũ | `maven.compiler.release` không đồng bộ môi trường | Kiểm tra JDK/toolchain/runtime matrix |
| Publish artifact dùng `${revision}` consumer fail | POM publish chưa flatten đúng | Dùng flatten mode/goal, kiểm POM đã publish |
| Root `packaging=pom` không dùng flattened POM | `updatePomFile` không bật/không hiệu lực | Cấu hình rõ khi phát hành parent/BOM |
| `mvn -Drevision=...` không sửa POM trên disk | CLI override là transient | Dùng workflow cập nhật source nếu cần commit |
| `versions:set-property` làm build fail | Version mới không tương thích | Review release notes, test, revert diff nếu cần |
| Runtime `System.getProperty("revision")` là null | Maven property không tự gửi vào Java process | Dùng resource filtering/manifest/systemPropertyVariables |
| File binary bị hỏng sau resources phase | Bật filtering toàn bộ assets | Chỉ lọc text, tách filtered-resources |
| Build dùng hai JUnit versions | BOM/management/direct version conflict | Xem dependency tree, thống nhất compatibility matrix |
| Artifact filename vẫn là version cũ | Target cũ hoặc invocation không truyền `-Drevision` | `mvn clean ...` và kiểm effective version |
| CI chỉ đổi property nhưng cache trả artifact cũ | Repository/cache/SNAPSHOT policy | Pin versions, invalidate cache theo key chính xác |
| Một module dùng dependency mới hơn module khác | Parent management không kế thừa hoặc child override | Xem effective POM từng module |
| Maven lệnh `exec:java` không tìm App | Chưa compile, sai mainClass hoặc plugin config | Chạy `mvn clean verify`, kiểm class/package |
| `java -jar` báo no main manifest | Demo không thiết lập executable manifest | Dùng `mvn exec:java` hoặc cấu hình packaging/manifest riêng |
| Version range tự chọn bản khác | Dynamic version requirements | Pin version cụ thể, kiểm dependency tree |
| Chỉ có `dependencyManagement` mà Maven tải dependency | Có transitive/direct usage ở đâu đó | Kiểm actual dependencies và scope |

**Không “sửa lỗi version” bằng cách copy một version literal vào mọi POM.** Thứ nhất xác định nguồn giá trị sai, thứ hai xác định nơi nó được tham chiếu, thứ ba xác nhận resolved artifact cuối.

## 25. Quy trình QA khi thay version trong dự án Maven

### Bước 1 — Ghi rõ phạm vi thay đổi

Ví dụ “nâng Commons Lang từ 3.16.0 lên 3.17.0” khác “nâng Maven project release từ 1.0.0-SNAPSHOT lên 1.1.0-SNAPSHOT”. Không sửa cả hai chỉ vì cùng chứa chữ `version`.

### Bước 2 — Kiểm tra property source

~~~bash
mvn -q help:evaluate -Dexpression=commons.lang3.version -DforceStdout
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
~~~

### Bước 3 — Kiểm tra effective POM

~~~bash
mvn help:effective-pom
~~~

Với multi-module, kiểm tra module bị ảnh hưởng; parent/source POM không phải lúc nào cũng phản ánh active profiles/CLI overrides.

### Bước 4 — Kiểm tra resolved dependency graph

~~~bash
mvn dependency:tree
~~~

Xem artifact/group/version/scope thực sự, không chỉ tên property.

### Bước 5 — Clean build và test

~~~bash
mvn -B clean verify
~~~

Không skip unit/integration tests chỉ để build pass. Dùng compatibility tests cho public APIs hoặc transitive dependency updates.

### Bước 6 — Chạy artifact thật

Với demo:

~~~bash
mvn -q exec:java
~~~

Với ứng dụng thực tế, chạy đúng distribution (JAR/WAR/container) trên runtime target. Unit test dùng Maven classpath không chứng minh deployment packaging luôn đúng.

### Bước 7 — Kiểm published POM

Khi dùng `${revision}` và install/deploy, kiểm bản flattened/published POM đã giải CI-friendly placeholders và có dependency metadata hợp lệ. Có thể tạo một project consumer đơn giản để resolve artifact trong một local repository/cache sạch.

### Bước 8 — Review release/security

- Kiểm dependency CVE và license changes.
- Kiểm JDK/Maven plugin compatibility.
- Ghi release notes/PR và effective overrides.
- Lưu checksum/SBOM khi cần.
- Không đưa secrets vào version resources.
- Đảm bảo project, child và published POM versions đồng bộ.

## 26. Bài tập tự kiểm tra

**Câu 1.** Khai báo `<commons.lang3.version>3.17.0</commons.lang3.version>` có tự thêm Commons Lang vào classpath không?

**Đáp:** Không. Cần actual dependency ở `<dependencies>`; property chỉ là giá trị.

**Câu 2.** `<dependencyManagement>` khác `<dependencies>` thế nào?

**Đáp:** Management quản lý phiên bản/scope cho dependencies được sử dụng; actual dependencies mới đưa artifact vào graph/classpath.

**Câu 3.** Đặt compiler version trong `<dependencyManagement>` có phải cách pin Maven Compiler Plugin không?

**Đáp:** Không. Dùng `<pluginManagement>` hoặc `<build><plugins>`.

**Câu 4.** `<project><version>${application.version}</version>` có là best practice Maven 3 cho project version không?

**Đáp:** Không. Maven CI-friendly hỗ trợ ba tên `${revision}`, `${sha1}`, `${changelist}`; dùng revision/literal hoặc workflow được hỗ trợ.

**Câu 5.** Tại sao không viết `<version>${revision}</version>` cho sibling dependency theo Maven CI-friendly guide?

**Đáp:** Guide yêu cầu dùng `${project.version}` cho dependency giữa modules cùng version; `revision` có giới hạn trong bối cảnh này.

**Câu 6.** Với `-Drevision=2.1.0-SNAPSHOT`, file `pom.xml` có được sửa không?

**Đáp:** Không. Đây là override của Maven invocation.

**Câu 7.** Nếu project version là `2.1.0-SNAPSHOT`, version Commons Lang có nên là `${project.version}` không?

**Đáp:** Không. Commons Lang có version độc lập, nên dùng property/bom/management riêng.

**Câu 8.** `mvn clean verify` thành công có tự chứng minh POM được install/deploy tiêu thụ được không?

**Đáp:** Không. Với CI-friendly `${revision}`, phải kiểm Flatten Plugin và published POM thực sự.

**Câu 9.** Vì sao demo dùng `<flattenMode>resolveCiFriendliesOnly</flattenMode>`?

**Đáp:** Để xử lý các CI-friendly version placeholders và giữ lại các cấu hình POM khác khi phát hành theo cơ chế này.

**Câu 10.** `pluginManagement` có tự chạy mọi plugin được liệt kê không?

**Đáp:** Không. Plugin phải được lifecycle bind/khai báo/gọi goal theo cơ chế Maven.

**Câu 11.** Một BOM import có tự thêm tất cả các thư viện trong BOM vào classpath không?

**Đáp:** Không. BOM cung cấp dependency management; module vẫn khai báo dependencies thực sự cần.

**Câu 12.** Java `System.getenv("revision")` có tự nhận `<revision>` từ POM không?

**Đáp:** Không. Maven property không tự biến thành environment variable của Java app.

**Câu 13.** Tại sao khi đổi dependency property vẫn phải xem dependency tree?

**Đáp:** Vì transitive dependencies, management, scopes và mediation có thể khiến resolved graph khác điều ta tưởng từ property.

**Câu 14.** Khi Spring Boot BOM quản lý một nhóm library versions, có nên override mọi version bằng properties riêng không?

**Đáp:** Không mặc định. Nên tuân compatibility matrix của BOM/parent và chỉ override sau khi kiểm thử.

**Câu 15.** `versions:set-property` có đảm bảo bản mới compile/test được không?

**Đáp:** Không. Nó sửa property, không phải công cụ chứng minh compatibility.

**Câu 16.** Bật resource filtering cho file PNG/ZIP có an toàn không?

**Đáp:** Không. Nên filter text riêng và giữ binary assets nguyên bytes.

**Câu 17.** Nếu CI dùng một library version khác POM committed, điều gì cần ghi lại?

**Đáp:** CLI/active profile overrides, resolved graph, artifact version, commit và build environment để tái tạo.

**Câu 18.** `maven.compiler.release=17` có tự cài JDK 17 không?

**Đáp:** Không. Build environment/toolchain cần JDK tương thích.

**Câu 19.** Nếu parent POM quản lý JUnit version nhưng child không khai báo JUnit, test code có tự dùng JUnit không?

**Đáp:** Không. Child cần dependency hoặc cơ chế inherited actual dependencies hợp lệ.

**Câu 20.** Khi parent và child cùng release version, cách tham chiếu sibling dependency nào phù hợp?

**Đáp:** Dùng `${project.version}` ở dependency version (hoặc quản lý tương đương), và đảm bảo GAV của sibling trùng với project version thực tế.

## 27. Checklist áp dụng cho project thật

1. Tách rõ **project version**, dependency versions, plugin versions, Java release.
2. Đặt tên properties rõ đối tượng, không lạm dụng tên `version` chung.
3. Với dependency xuất hiện nhiều module, cân nhắc `<dependencyManagement>`.
4. Với plugins, quản lý trong `<pluginManagement>`/`<plugins>`; không dùng dependencyManagement.
5. Chỉ dùng dependencyManagement cho quản lý; module nào cần artifact phải khai báo dependency thực.
6. Không ép thư viện bên ngoài dùng `${project.version}`.
7. Với Maven 3 project version property, dùng `${revision}`/`${sha1}`/`${changelist}` theo CI-friendly guide.
8. Dùng `${project.version}` cho sibling dependencies có cùng release version.
9. Khi publish CI-friendly POM, cấu hình Flatten Plugin và kiểm POM consumer.
10. Với packaging `pom`, xem `updatePomFile` và parent/BOM publication kỹ.
11. Không đặt arbitrary nested expressions trong revision mà chưa xác minh hỗ trợ.
12. Pin dependency/plugin versions thay vì dùng dynamic ranges thiếu policy.
13. Không tự override BOM compatibility matrix ở nhiều artifacts.
14. Parent properties nên nhất quán; child overrides phải được ghi nhận.
15. Active profiles và CI `-D` phải có phạm vi/ghi nhận rõ ràng.
16. Kiểm `help:evaluate` để xem property cuối.
17. Kiểm `help:effective-pom` để xem cấu hình Maven cuối.
18. Kiểm `dependency:tree` để thấy resolved artifact version và scopes.
19. Chạy clean verify, tests và runtime/distribution checks sau đổi version.
20. Chỉ filter text resources; không nhúng secrets vào artifacts.
21. Khi dùng Versions Plugin, review diff và compatibility trước khi merge.
22. Không coi local `install` là remote deploy hoặc production deployment.
23. Giữ JDK/Maven/toolchain versions cố định trong CI.
24. Kiểm POM published, dependency metadata và consumer resolution từ sạch.
25. Duy trì release notes, SBOM/checksum/provenance theo chính sách.
26. Không bỏ qua tests hoặc che Maven failures để tránh việc nâng cấp thất bại.
27. Với multi-module, đảm bảo parent/child/sibling GAV đồng bộ.
28. Với SNAPSHOT, có chính sách repository/cache và build reproducibility.
29. Tách biệt cấu hình build-time version với runtime secrets/environment.
30. Chỉ kết luận **version upgrade thành công** khi effective model, resolved dependencies, tests và artifact thực đều đúng.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the POM: Interpolation and Variables](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference: Properties](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Maven CI Friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html)
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [MojoHaus Flatten Maven Plugin — Usage](https://www.mojohaus.org/flatten-maven-plugin/usage.html)
- [MojoHaus Flatten Maven Plugin — flatten:flatten Parameters](https://www.mojohaus.org/flatten-maven-plugin/flatten-mojo.html)
- [MojoHaus Versions Maven Plugin — Introduction](https://www.mojohaus.org/versions/versions-maven-plugin/)
- [MojoHaus Versions Maven Plugin — versions:set-property](https://www.mojohaus.org/versions/versions-maven-plugin/set-property-mojo.html)
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
- [Apache Commons Lang 3.17.0 — StringUtils API](https://javadoc.io/static/org.apache.commons/commons-lang3/3.17.0/org/apache/commons/lang3/StringUtils.html)

