# compile và thư viện dùng trong biên dịch, thực thi thông thường

## 1. `compile` là gì trong Maven?

Maven dùng **dependency scope** để xác định một thư viện nằm trong những **classpath** nào và có được truyền bắc cầu sang dự án phụ thuộc hay không. Trong các scope của Maven, **`compile` là scope mặc định**: nếu một `<dependency>` không khai báo `<scope>`, Maven xem dependency đó thuộc scope `compile`.

Scope này dành cho những thư viện mà **mã Java chính (`src/main/java`) cần khi biên dịch và ứng dụng tiếp tục cần khi chạy bình thường**. Ví dụ: Apache Commons Lang, thư viện JSON mà ứng dụng import trực tiếp, thư viện HTTP client được gọi từ business code, hoặc một API/implementation dùng tại cả compile time lẫn runtime.

Đoạn dưới thuộc phần `<dependencies>` của POM:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Nó có ý nghĩa giống:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
    <scope>compile</scope>
</dependency>
~~~

Không bắt buộc phải viết `<scope>compile</scope>`; việc bỏ scope là cách khai báo Maven thông thường. Chỉ viết rõ khi muốn người đọc dễ đối chiếu hoặc khi quy ước dự án yêu cầu.

**Đừng nhầm hai chữ `compile`:**

- **Scope `compile`**: thuộc tính của một dependency; quyết định thư viện được thêm vào compile, runtime và test classpath như thế nào.
- **Phase `compile`**: một mốc thuộc **default lifecycle**, được gọi bằng `mvn compile`; khi packaging có binding phù hợp, Maven Compiler Plugin biên dịch mã chính.
- Thư viện có scope `compile` vẫn được Maven đưa vào runtime/test classpath dù bạn gọi `mvn test`, `mvn package` hay `mvn verify`; nó không chỉ hoạt động khi gõ đúng lệnh `mvn compile`.

**Kết luận cốt lõi:** compile-scope dependency có mặt trong **mọi classpath thông thường của dự án**, gồm main compile, main runtime và test. Nhưng **được Maven tính vào runtime classpath** không đồng nghĩa nó tự được nhúng vào JAR do `mvn package` tạo ra.

## 2. Classpath Java và các thư mục của Maven

**Classpath** là tập các thư mục chứa `.class` và các JAR mà Java compiler hoặc JVM dùng để tìm lớp cần thiết. Java 17 có sẵn API chuẩn của JDK như `java.lang` và `java.util`, nhưng không tự có thư viện Apache Commons Lang hay JUnit.

Cấu trúc mặc định của một dự án Maven packaging `jar` thường là:

~~~text
project/
├── pom.xml
├── src/
│   ├── main/java/             nguồn Java chính
│   ├── main/resources/        resource chính
│   ├── test/java/             nguồn Java kiểm thử
│   └── test/resources/        resource kiểm thử
└── target/
    ├── classes/              lớp và resource chính đã xử lý
    ├── test-classes/         lớp và resource test đã xử lý
    ├── surefire-reports/     báo cáo chạy unit test
    └── artifact-version.jar  artifact khi package (tên thực phụ thuộc POM)
~~~

Các thư viện ngoài JDK Maven tải về thường nằm trong **Maven local repository**, mặc định ở `~/.m2/repository/`, trừ khi cấu hình khác. Đây là nơi cache dependency và plugin cho Maven, **không phải một thư mục mà lệnh `java` tự quét**.

Maven Compiler Plugin thường xây dựng **main compile classpath** gồm các dependency thuộc scope phù hợp. Maven Surefire Plugin thường dùng **test runtime classpath**, bao gồm mã chính, mã test cùng các dependency phục vụ test. Một chương trình Java được khởi động riêng bằng `java -cp ...` chỉ dùng classpath do launcher nhận được; nó không đọc POM để tự tải JAR.

### `compile` xuất hiện ở classpath nào?

| Ngữ cảnh | Có dependency trực tiếp scope `compile`? | Ý nghĩa |
| --- | --- | --- |
| Main compile (`src/main/java`) | **Có** | Compiler tìm được API/class để biên dịch mã chính. |
| Main runtime | **Có** | JVM tìm được class nếu launcher/distribution cung cấp đúng runtime classpath. |
| Test compile (`src/test/java`) | **Có** | Test code có thể import/call class của thư viện compile. |
| Test runtime | **Có** | Test chạy được mã chính cần thư viện compile. |
| Consumer phụ thuộc vào JAR của dự án | **Thông thường được truyền bắc cầu** | Còn tùy optional, exclusions, version mediation và dependency graph. |

Cách nói **“scope compile chỉ cần lúc biên dịch”** là không chính xác. Với thư viện mà ứng dụng còn gọi lúc chạy, compile chính là lựa chọn hợp lý.

## 3. So sánh với provided, runtime và test

| Scope | Main compile CP | Main runtime CP | Test CP | Tình huống điển hình |
| --- | :---: | :---: | :---: | --- |
| **compile** (mặc định) | Có | Có | Có | Thư viện code chính import và gọi cả khi chạy. |
| **provided** | Có | Không | Có | API do JDK/container/môi trường chạy cung cấp. |
| **runtime** | Không | Có | Có | Implementation cần lúc chạy, code chính không import API riêng của nó khi biên dịch. |
| **test** | Không | Không | Có | JUnit, Mockito và thư viện chỉ dùng trong test. |
| **system** | Có | Có, từ file hệ thống theo mô hình Maven | Có | Cơ chế đường dẫn file JAR cục bộ, kém tái lập, nên tránh. |
| **import** | Không phải classpath scope | Không phải classpath scope | Không phải classpath scope | Nhập BOM type `pom` trong `dependencyManagement`. |

Bảng nói về **classpath mà Maven xây dựng**. Nó không có nghĩa một JAR thông thường tự mang theo mọi dependency ở các classpath đó.

Các ví dụ lựa chọn:

- Mã trong `src/main/java` gọi `org.apache.commons.lang3.StringUtils`: **compile**.
- Mã trong `src/test/java` import `org.junit.jupiter.api.Test`: **test**.
- Web app chạy trong servlet container, container cấp Servlet API: **provided**, sau khi xác nhận đúng version/contract.
- Mã chính chỉ dùng JDBC chuẩn `java.sql`; driver cụ thể được phát hiện khi runtime qua SPI: có thể **runtime**.
- BOM dùng để quản lý version: **import** trong `dependencyManagement`, không phải JAR.
- API JDK như `java.util.List`: **không thêm dependency bên thứ ba**.

Maven không có scope `compileOnly` riêng như một số build tool khác. Đừng tạo scope không được hỗ trợ; khi môi trường chạy cung cấp thư viện theo hợp đồng, thường cân nhắc `provided`.

## 4. Ví dụ Java 17 hoàn chỉnh: thư viện compile dùng cả khi chạy

Ta tạo dự án **compile-scope-demo** dùng Commons Lang trong mã Java chính và JUnit Jupiter cho test. Mục tiêu là quan sát cùng một thư viện **giúp mã chính biên dịch** và **được JVM cần khi chạy**.

Cần JDK 17+, Maven cùng kết nối tải dependency/plugin từ repository hợp lệ.

Cấu trúc:

~~~text
compile-scope-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/scope/Main.java
    └── test/java/vn/example/scope/MainTest.java
~~~

### 4.1. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>compile-scope-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
            <!-- Không có scope: Maven hiểu là compile -->
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
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

**Giải thích:**

1. Project có packaging `jar`, tọa độ `vn.example:compile-scope-demo:1.0.0`.
2. Java Compiler Plugin dùng `maven.compiler.release=17`; mã nguồn UTF-8.
3. `commons-lang3` là **compile** theo mặc định, có trong main compile/test/runtime classpaths của Maven.
4. `junit-jupiter` có scope **test** nên không phải dependency runtime của ứng dụng.
5. Compiler, Surefire và JAR Plugin được chốt version cho ví dụ; không khẳng định các version này là mới nhất.
6. JAR Plugin ở cấu hình này **không được yêu cầu đóng gói Commons Lang vào JAR dự án**.

### 4.2. src/main/java/vn/example/scope/Main.java

~~~java
package vn.example.scope;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static String greet(String name) {
        return "Xin chào, " + StringUtils.capitalize(name) + "!";
    }

    public static void main(String[] args) {
        System.out.println(greet("maven"));
    }
}
~~~

`StringUtils.capitalize("maven")` trả về **Maven**. Thư viện được dùng trong **mã chính**, không chỉ trong mã test, nên scope compile là lựa chọn hợp lý. Nếu thiếu Commons Lang khi javac chạy, import sẽ không giải quyết được. Nếu thiếu Commons Lang khi gọi `Main.greet(...)` ở runtime, JVM sẽ không tải được `StringUtils`.

### 4.3. src/test/java/vn/example/scope/MainTest.java

~~~java
package vn.example.scope;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {
    @Test
    void greetingUsesCompileDependency() {
        assertEquals("Xin chào, Maven!", Main.greet("maven"));
    }
}
~~~

Test này sử dụng JUnit trong **test classpath**, đồng thời gọi `Main.greet` và gián tiếp dùng Commons Lang từ **compile scope**. Không phải chuyển JUnit sang compile scope để test biên dịch.

### 4.4. Build bằng Maven

Tại thư mục `compile-scope-demo/`:

~~~bash
mvn --version
mvn -B clean verify
~~~

Với Maven/JDK phù hợp và dependency tải được, build sẽ xử lý nguồn, biên dịch `Main.java`, biên dịch `MainTest.java`, chạy test và đóng gói JAR:

~~~text
target/classes/vn/example/scope/Main.class
target/test-classes/vn/example/scope/MainTest.class
target/surefire-reports/...
target/compile-scope-demo-1.0.0.jar
~~~

**`mvn verify` không tự chạy `public static void main` của ứng dụng.** Test gọi phương thức `greet`, còn stdout của ứng dụng chỉ xuất hiện khi khởi động `Main` bằng Java launcher hoặc launcher/plugin tương ứng.

## 5. Biên dịch thành công nhưng chạy JAR lại thiếu lớp

Sau `mvn clean verify`, thử:

~~~bash
java -cp target/compile-scope-demo-1.0.0.jar vn.example.scope.Main
~~~

JAR thông thường có `Main.class`, nhưng **không tự nhúng Commons Lang**. Khi chương trình chạy đến `StringUtils.capitalize`, Java có thể báo lỗi dạng:

~~~text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
~~~

Đây là **mẫu nhận diện lỗi**, không phải toàn bộ stack trace chính xác trên mọi JVM. Nó minh họa sự khác biệt giữa:

- **Compile classpath do Maven cung cấp** cho javac khi build: có Commons Lang.
- **Runtime classpath do lệnh `java -cp` ở trên nhận**: chỉ có JAR của dự án, thiếu Commons Lang.

**Đừng sửa bằng cách đổi `<scope>compile</scope>` thành `<scope>runtime</scope>`**: mã chính import `StringUtils`, đổi thành runtime còn có thể làm compiler thất bại. Sửa đúng là phân phối và cung cấp đầy đủ **runtime JARs**, hoặc dùng một cách đóng gói/launcher khác.

## 6. Chạy ứng dụng đúng: thêm compile dependency vào runtime classpath

Maven Dependency Plugin có goal `copy-dependencies`. Trong ví dụ, chạy lệnh đầy đủ để chọn rõ phiên bản plugin:

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/runtime-libs
~~~

Bộ lọc **`-DincludeScope=runtime` không có nghĩa chỉ copy dependency khai báo `<scope>runtime</scope>`**. Theo tài liệu Maven Dependency Plugin, giá trị này chọn **runtime classpath**, tức **cả `compile` và `runtime` dependencies**. Nó không chọn các dependency chỉ có scope test hoặc provided.

Sau khi thành công, thư mục sẽ có:

~~~text
target/runtime-libs/commons-lang3-3.14.0.jar
~~~

Trong các dự án lớn hơn, có thể còn nhiều JAR compile/runtime bắc cầu tương ứng.

**Linux/macOS:**

~~~bash
java -cp "target/compile-scope-demo-1.0.0.jar:target/runtime-libs/*" vn.example.scope.Main
~~~

**Windows PowerShell hoặc Command Prompt:**

~~~powershell
java -cp "target\compile-scope-demo-1.0.0.jar;target\runtime-libs\*" vn.example.scope.Main
~~~

**Stdout chính xác của lệnh Java thành công**, khi terminal hiển thị Unicode đúng:

~~~text
Xin chào, Maven!
~~~

Cách đọc lệnh:

- `target/compile-scope-demo-1.0.0.jar` chứa `vn.example.scope.Main`.
- `target/runtime-libs/*` thêm các **file JAR nằm trực tiếp trong thư mục đó** vào classpath của Java launcher.
- Linux/macOS phân tách các phần tử classpath bằng **dấu hai chấm `:`**; Windows phân tách bằng **dấu chấm phẩy `;`**.
- Dấu nháy quanh toàn bộ classpath giúp tránh shell mở rộng wildcard sai ý định. Java launcher xử lý wildcard JAR trong phần tử thư mục.
- Wildcard này **không tìm JAR đệ quy** trong mọi thư mục con.
- JUnit là scope test, nên không cần trong runtime-libs cho ứng dụng này.

Ví dụ dùng `java -cp ... Main`, **không dùng `java -jar`**, vì POM chưa cấu hình `Main-Class` trong manifest. Nếu muốn một executable/fat JAR, cần cấu hình đóng gói phù hợp; scope `compile` tự nó không thay thế bước ấy.

## 7. Scope không đồng nghĩa với cách đóng gói

Với packaging `jar`, Maven JAR Plugin thông thường đóng gói **class/resource của chính dự án**. Maven không mặc nhiên gộp tất cả JAR compile/runtime vào trong artifact.

| Mô hình phân phối | Có gì trong artifact/phân phối? | Cách nạp dependency |
| --- | --- | --- |
| **JAR thường** | Class và resource của dự án. | Runtime classpath phải cung cấp các JAR ngoài. |
| **JAR + thư mục lib/** | App JAR và nhiều dependency JAR bên cạnh. | Launcher dùng `java -cp`, script hoặc manifest classpath phù hợp. |
| **Fat/Uber JAR** | Các class/resource dependency được gộp theo cơ chế đóng gói. | Cần Shade/Assembly hoặc phương pháp được dự án lựa chọn; chú ý merge resources và services. |
| **WAR** | Web application và thư viện theo packaging. | Container cung cấp một số API `provided`; những thư viện khác được đóng gói theo quy tắc web app. |

Cùng một dependency có scope compile có thể dùng trong các mô hình phân phối khác nhau. Scope là **chính sách hiện diện trên classpath Maven**, không phải lệnh chép nội dung vào JAR.

**JVM không tự đọc POM để tìm dependency** khi bạn gọi `java` riêng. Việc Maven đã tải Commons Lang vào `~/.m2/repository` cũng không giúp lệnh `java -cp app.jar ...` tự tìm được nó. Cần chỉ rõ đường dẫn hoặc dùng launcher/phương thức triển khai có hỗ trợ.

Một lưu ý Java launcher: khi chạy bằng **`java -jar`**, lệnh dùng manifest để xác định main class và không sử dụng `-cp` command line theo cách tương tự khi gọi main class trực tiếp. Nếu muốn `java -jar`, hãy thiết kế manifest và classpath phân phối đúng, hoặc tạo executable JAR.

## 8. Thư viện scope compile được truyền bắc cầu như thế nào?

Giả sử dự án A khai báo dependency B với scope compile:

~~~text
Dự án A
  |
  +-- B  (A -> B: compile)
       |
       +-- C (B -> C: compile)
       +-- D (B -> D: runtime)
       +-- E (B -> E: provided)
       +-- F (B -> F: test)
~~~

Theo bảng **dependency scope transitivity** của Maven, đối với những dependency đến qua nhánh B:

- B ở compile scope của A.
- C thường được đưa vào A với scope **compile**.
- D thường được đưa vào A với scope **runtime**.
- E (`provided`) không được truyền qua nhánh này.
- F (`test`) không được truyền qua nhánh này.

Đây là **kết quả trên một nhánh**; nếu dependency còn đến từ nhánh khác hoặc A khai báo trực tiếp thì effective graph có thể khác do version mediation, exclusions, optional và dependencyManagement.

### Các tổ hợp thường gặp

| Scope của dependency A khai báo | Scope dependency mà nó kéo theo | Scope kết quả ở A qua nhánh này |
| --- | --- | --- |
| `compile` | `compile` | `compile` |
| `compile` | `runtime` | `runtime` |
| `compile` | `provided` | Không truyền |
| `compile` | `test` | Không truyền |
| `runtime` | `compile` | `runtime` |
| `runtime` | `runtime` | `runtime` |
| `test` | `compile` | `test` |

**Có tính bắc cầu không có nghĩa nên lạm dụng.** Nếu source code A import class của C **trực tiếp**, nên khai báo C trực tiếp trong POM của A. Nếu sau này B bỏ C trong phiên bản mới, dự án A sẽ không bất ngờ mất classpath cần thiết. Các khai báo trực tiếp cũng giúp người review hiểu A phụ thuộc những API nào.

Maven không đơn giản chọn version cao nhất khi có nhiều nhánh dẫn đến cùng artifact. Version mediation thường theo **nearest definition**, và `dependencyManagement` có thể điều chỉnh phiên bản hiệu lực. Khi có xung đột, xem `dependency:tree` và chọn version được kiểm chứng.

## 9. `optional` và `exclusions` không giống scope

### Optional

Một thư viện B có thể đánh dấu dependency compile là optional:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
    <optional>true</optional>
</dependency>
~~~

Khi **build B**, Commons Lang vẫn là compile dependency của chính B. Nhưng khi **A phụ thuộc B**, Maven không tự truyền Commons Lang qua nhánh B do `optional=true`. Nếu A sử dụng trực tiếp Commons Lang hoặc một tính năng của B cần nó, A phải khai báo dependency thích hợp.

**`optional` là cơ chế kiểm soát dependency truyền sang consumer**, không phải việc chuyển compile thành provided hoặc xóa thư viện khỏi B.

### Exclusions

Ví dụ A muốn loại một artifact kéo theo từ thư viện B:

~~~xml
<dependency>
    <groupId>vn.example</groupId>
    <artifactId>library-b</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là **đoạn XML minh họa**, không phải POM độc lập; `vn.example:library-b:1.0.0` chỉ là tọa độ ví dụ, không hứa tồn tại trong repository công khai.

Exclusion có tác dụng theo **nhánh dependency** đó. Nó không chặn Commons Lang xuất hiện qua mọi nhánh còn lại. Nếu mã B thực sự cần class của Commons Lang khi chạy, exclude mà không cung cấp thư viện có thể gây lỗi `NoClassDefFoundError`.

### dependencyManagement

Một parent hoặc BOM có thể quản lý version:

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

**Đặt thư viện trong `dependencyManagement` không tự thêm nó vào bất kỳ classpath nào.** Module vẫn phải có dependency thực tế trong `<dependencies>` hoặc nhận qua graph bắc cầu. Phần management chỉ giúp kiểm soát version, scope/default và metadata tương ứng khi dependency được dùng.

## 10. Xem dependency tree và kiểm tra classpath thực tế

Maven Dependency Plugin cung cấp các goal hữu ích để kiểm chứng.

### 10.1. dependency:tree

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Một số dòng mẫu trong dự án minh họa sẽ có dạng:

~~~text
vn.example:compile-scope-demo:jar:1.0.0
+- org.apache.commons:commons-lang3:jar:3.14.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.10.2:test
~~~

Đây **chỉ là trích đoạn minh họa**; cây thực tế còn có dependency bắc cầu của JUnit và format tùy plugin. Dòng `:compile` cho thấy Maven đang giải quyết Commons Lang ở scope compile dù POM không viết scope tường minh.

Có thể lọc artifact muốn tìm:

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
~~~

### 10.2. dependency:build-classpath

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/runtime-classpath.txt
~~~

Goal này tạo chuỗi đường dẫn tới dependency JAR theo runtime classpath, thường là những file trong local repository. **Nó thường không tự thêm output lớp/JAR của dự án**. Khi tự chạy Java launcher, vẫn phải thêm `target/classes` hoặc JAR dự án vào classpath.

`includeScope=runtime` ở Maven Dependency Plugin là **ngưỡng chọn classpath**, gồm compile + runtime dependencies; **không chỉ những mục có thẻ scope runtime**.

### 10.3. dependency:copy-dependencies

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/runtime-libs
~~~

Goal copy dependency JAR và thư viện bắc cầu trong phạm vi runtime vào một thư mục. Mục 6 dùng cách này để chạy ứng dụng với classpath có đủ Commons Lang.

### 10.4. dependency:analyze

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:analyze
~~~

Goal có thể phát hiện dependency **được dùng nhưng chưa khai báo trực tiếp** và dependency **đã khai báo nhưng không thấy dùng từ bytecode**. Không nên xem phân tích này là bằng chứng tuyệt đối: reflection, SPI, JDBC driver, class được nạp động, annotation processing hoặc plugin có thể tạo kết quả cần xem thủ công.

**Lưu ý riêng về `includeScope` của plugin:** với `includeScope=compile`, tập chọn có thể gồm compile/provided/system theo ngưỡng compile classpath; nó không phải phép so khớp trực tiếp duy nhất những `<scope>compile</scope>`.

## 11. Chọn sai scope gây ra lỗi gì?

### A. Đổi Commons Lang sang runtime

Nếu thêm:

~~~xml
<scope>runtime</scope>
~~~

vào dependency Commons Lang trong POM mục 4, Maven **không** đưa JAR này vào main compile classpath. Mã `Main.java` có `import StringUtils` sẽ biên dịch lỗi, thường gồm các thông tin như:

~~~text
package org.apache.commons.lang3 does not exist
cannot find symbol: variable StringUtils
~~~

Đây là đoạn nhận diện chứ không phải log đầy đủ. Cách sửa là dùng `compile`, vì mã chính cần API thư viện khi biên dịch.

### B. Đổi Commons Lang sang test

Scope test chỉ có trên **test classpath**, không có trên main compile classpath. Dù test code có thể nhìn thấy Commons Lang, Maven vẫn phải **biên dịch mã chính trước**; Main dùng StringUtils nên build lỗi.

### C. Đổi Commons Lang sang provided

Scope provided cho phép main compile và test, nên Maven có thể build thành công. Tuy nhiên **runtime classpath Maven không chứa dependency provided**. Nếu không có container/môi trường cấp Commons Lang, ứng dụng sẽ thiếu class khi chạy.

`provided` hợp lý cho API thực sự do container cung cấp, không phải mẹo tùy tiện để giảm số JAR cần phân phối.

### D. Vẫn để compile nhưng chạy thiếu classpath

Đây là lỗi ở **cách đóng gói/khởi động**, không phải ở scope. `java -cp app.jar Main` không có Commons Lang nếu app JAR chưa chứa dependency; cần thêm dependency JAR vào classpath như mục 6.

### E. Nâng version và gặp NoSuchMethodError

Không phải mọi runtime lỗi đều là thiếu class. Nếu compiler thấy version của thư viện có phương thức A, nhưng launcher lại dùng một version JAR khác không có phương thức đó, JVM có thể báo `NoSuchMethodError`. Hãy kiểm tra version trên Maven dependency graph và những file JAR thực tế ở runtime, tránh đưa nhiều version mâu thuẫn lên classpath.

## 12. Khi nào nên dùng runtime thay vì compile?

Không phải mọi thư viện được ứng dụng cần lúc chạy đều phải có trong main compile classpath.

Ví dụ Java có JDBC API chuẩn `java.sql`. Nếu mã chính chỉ import các API chuẩn:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
~~~

thì mã có thể **biên dịch không cần** class riêng của PostgreSQL driver. Driver có thể được phát hiện/đăng ký khi runtime thông qua cơ chế JDBC. Lúc đó một đoạn dependency thích hợp có thể là:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>42.7.3</version>
    <scope>runtime</scope>
</dependency>
~~~

Đây là **đoạn dependency minh họa**, không phải chương trình kết nối cơ sở dữ liệu độc lập. Cấu hình thật còn cần URL, credentials và database đang hoạt động.

Nếu mã chính **import trực tiếp** lớp do PostgreSQL JDBC driver cung cấp, nhu cầu compile classpath thay đổi: xem lại scope `compile`. Tiêu chí chọn scope là **API nào code phải nhìn thấy tại thời điểm compile và dependency nào phải tồn tại lúc chạy**.

## 13. Trường hợp multi-module và library consumer

Giả sử repository gồm:

~~~text
parent (packaging pom)
├── shared-library (packaging jar)
└── application (packaging jar)
~~~

Mã trong application import class của shared-library. POM application có thể khai báo:

~~~xml
<dependency>
    <groupId>vn.example</groupId>
    <artifactId>shared-library</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Với packaging và graph phù hợp, Maven coi đây là compile dependency trực tiếp. Khi build reactor từ parent:

~~~bash
mvn -B -pl application -am clean verify
~~~

`-pl` chọn module application và `-am` build thêm các module trong reactor mà application phụ thuộc, nếu Maven phân giải được quan hệ. Câu lệnh này giả định đường dẫn/selector `application` tồn tại đúng trong reactor.

Những điểm cần nhớ:

- Mỗi module có `target/classes` và classpath riêng, không tự ghép output của mọi module vào một thư mục.
- Compile dependency của shared-library có thể truyền bắc cầu tới application, trừ trường hợp optional/exclusion/mediation.
- Nếu application import trực tiếp class từ một dependency bắc cầu, nên khai báo dependency đó trực tiếp để ổn định API.
- Parent POM thường có packaging `pom`; quản lý version trong parent **không** tự thêm thư viện vào mọi module.
- Reactor giúp build module liên quan trong một lượt, nhưng khi deploy app ngoài Maven vẫn phải cung cấp runtime classpath đúng.

## 14. Scope compile trong kiểm thử và triển khai thực tế

### Unit test có thể che lỗi runtime

Khi chạy `mvn test`, Maven/Surefire thường có nhiều dependency trên **test runtime classpath**, bao gồm compile, runtime, test và một số scope khác phù hợp. Test có thể pass trong khi **bản phân phối** thiếu một JAR cần thiết.

Vì vậy nên có một bước smoke test **dùng đúng app JAR và runtime-libs hoặc launcher của sản phẩm**, chứ không chỉ tin kết quả Surefire.

`-DskipTests` thường bỏ qua thực thi test nhưng vẫn có thể biên dịch test; `-Dmaven.test.skip=true` thường bỏ cả biên dịch test trong luồng plugin Maven phổ biến. Các cờ này không đổi định nghĩa scope compile; chúng thay đổi hoạt động kiểm thử.

### Xuất bản một thư viện cho consumer

Nếu project là **library**, Maven deploy JAR cùng POM metadata. Consumer Maven có thể dùng POM đó để giải quyết dependency bắc cầu. Nhưng một chương trình Java độc lập chỉ nhận được file `library.jar` **không tự giải quyết classpath từ POM**; cách chạy vẫn phải có các JAR ngoài.

Đừng làm fat JAR một cách tự động cho mọi library; nó có thể gây trùng class/service files và khó kiểm soát version khi consumer có dependencies riêng.

### Classpath và module path

Java 17 còn hỗ trợ JPMS/module-path. Maven dependency scope quyết định tập artifact thích hợp, nhưng các dự án dùng `module-info.java` có thêm quy tắc về module resolution, exported packages và module-path. Ví dụ bài học không dùng JPMS; với classpath truyền thống, việc có app JAR cùng Commons Lang JAR là đủ để chạy `Main` như mô tả.

## 15. Quy trình chẩn đoán và sửa lỗi compile/runtime

1. **Xác định giai đoạn lỗi**: Maven compile/test hay JVM chạy ứng dụng ngoài Maven. Hai trường hợp có nguyên nhân khác nhau.
2. **Đọc import trong `src/main/java`**: nếu code chính import thư viện ngoài JDK, thường cần `compile` hoặc `provided` có hợp đồng môi trường rõ ràng.
3. **Xem đúng POM module**: groupId, artifactId, version, scope, parent, dependencyManagement và profile.
4. **Chạy `mvn dependency:tree`**: kiểm tra dependency thực sự được chọn, scope hiệu lực, version và các nhánh bắc cầu.
5. **Nếu Maven chưa tải được dependency**, kiểm tra mirror/repository/credentials/network; đó là vấn đề resolution, không phải scope.
6. **Nếu javac thất bại**, xác nhận thư viện nằm ở main compile classpath; đừng đổi ngẫu nhiên sang runtime/test.
7. **Nếu test pass nhưng Java chạy lỗi**, so sánh test classpath với runtime classpath của bản phân phối.
8. **Nếu launcher chỉ có app.jar**, bổ sung compile+runtime JAR hoặc chọn cách packaging khác; đừng kỳ vọng local repository được Java quét tự động.
9. **Nếu dùng Dependency Plugin**, nhớ `includeScope=runtime` bao gồm compile + runtime; xác nhận file output có đủ JAR.
10. **Nếu nhiều version**, điều tra version mediation, exclusions, optional và dependencyManagement.
11. **Nếu class tồn tại mà vẫn lỗi**, kiểm tra module-path, classloader, binary compatibility, `NoSuchMethodError` và trùng JAR.
12. **Sau khi sửa**, chạy `mvn clean verify` và một lệnh chạy ứng dụng thật với đúng distribution; chỉ kết luận hoàn tất khi cả hai đạt.

## 16. Những hiểu lầm phổ biến

**“Compile scope chỉ có ở phase compile.”** Sai: nó áp dụng cho main compile, runtime và test classpaths.

**“Không có thẻ scope nghĩa là không có scope.”** Sai: Maven mặc định chọn `compile`.

**“Thư viện compile tự được nhúng vào JAR.”** Sai: compile scope và packaging là hai cơ chế độc lập.

**“JUnit dùng trong test compile thì phải scope compile.”** Sai: thư viện chỉ dùng ở test thường có scope `test`.

**“provided và compile giống nhau khi chạy.”** Sai: provided **không có trên main runtime classpath** do Maven xây dựng.

**“runtime luôn tốt hơn compile nếu chương trình cần thư viện khi chạy.”** Sai: nếu source chính import API của thư viện, javac cũng cần nó.

**“Thêm dependency vào dependencyManagement làm classpath xuất hiện JAR.”** Sai: management quản lý metadata/version, không tự khai báo sử dụng.

**“Compile dependency luôn được consumer nhận vô điều kiện.”** Sai: optional, exclusions, scope kết quả và graph có thể thay đổi việc truyền dependency.

**“`includeScope=runtime` chỉ copy thẻ scope runtime.”** Sai: Dependency Plugin dùng ngưỡng runtime classpath, gồm compile và runtime.

**“`mvn clean verify` thành công thì `java -jar app.jar` chắc chắn chạy được.”** Sai: JAR có thể chưa có Main-Class và các dependency runtime chưa được phân phối.

**“Maven chọn version mới nhất nếu có nhiều version.”** Sai: dependency mediation và management quyết định version cuối cùng, không mặc nhiên lấy bản cao nhất.

## 17. Bài thực hành tự kiểm tra

1. **Xác nhận scope mặc định:** chạy `dependency:tree` với POM mục 4; Commons Lang phải hiện scope compile dù không khai báo `<scope>`.
2. **Tách compile khỏi runtime:** build `mvn clean verify`, sau đó thử `java -cp target/compile-scope-demo-1.0.0.jar ...` để quan sát lỗi thiếu Commons Lang.
3. **Bổ sung classpath:** chạy `copy-dependencies` với `includeScope=runtime`, sau đó dùng lệnh Java phù hợp Linux/Windows để thấy **Xin chào, Maven!**.
4. **Cố ý chọn sai scope:** chuyển Commons Lang sang `runtime`, chạy `mvn clean compile`, giải thích vì sao main Java không biên dịch; sửa về compile.
5. **Phân biệt provided:** chuyển Commons Lang sang `provided`, biên dịch rồi chạy bên ngoài Maven mà không cấp JAR; giải thích sai khác giữa compile và runtime classpaths.
6. **Kiểm tra JUnit:** tìm JUnit trong test classpath nhưng không nằm trong runtime-libs theo bộ lọc của ví dụ.
7. **Tìm hiểu bắc cầu:** vẽ A -> B compile -> C compile và D runtime; dự đoán scope kết quả; thay C thành optional và giải thích vì sao downstream phải khai báo trực tiếp nếu cần.
8. **Tạo phân phối nhỏ:** đặt app.jar và runtime-libs trong cùng một thư mục có launcher, thử trên máy không cần cache Maven để xác minh không phụ thuộc repository của người phát triển.

### Ghi nhớ

**`compile` là scope mặc định cho thư viện mà mã ứng dụng cần lúc biên dịch và tiếp tục cần khi chạy bình thường.** Maven đưa dependency compile vào các classpath tương ứng và thường truyền nó bắc cầu đến consumer. Tuy nhiên, **scope không phải cơ chế đóng gói**: một ứng dụng Java muốn chạy ngoài Maven phải có launcher/runtime classpath thực tế chứa các JAR cần thiết. Hãy kiểm chứng cả **build** và **chạy chương trình**, không chỉ nhìn `BUILD SUCCESS`.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Dependency Scopes](https://maven.apache.org/repositories/dependencies.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Dependency Plugin — dependency:build-classpath](https://maven.apache.org/plugins/maven-dependency-plugin/build-classpath-mojo.html)
- [Maven Dependency Plugin — dependency:copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html)
- [Maven Dependency Plugin — dependency:analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html)
- [Maven JAR Plugin — Usage](https://maven.apache.org/plugins/maven-jar-plugin/usage.html)
