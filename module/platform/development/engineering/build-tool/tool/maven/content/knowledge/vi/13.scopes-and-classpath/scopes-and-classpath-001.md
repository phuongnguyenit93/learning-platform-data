# Maven dependency scope: classpath và tính bắc cầu hoạt động như thế nào?

## 1. Tư duy đúng: scope trả lời hai câu hỏi

Trong Maven, một dependency không chỉ được xác định bằng `groupId`, `artifactId`, `version`, `type` và `classifier`. Thuộc tính **`scope`** quyết định hai điều rất quan trọng:

1. **Classpath nào nhận dependency đó?** Java compiler có thấy thư viện khi biên dịch mã chính không? Test compiler có thấy không? Khi chạy ứng dụng, thư viện có nằm trong classpath runtime được Maven chuẩn bị không?
2. **Dependency đó lan sang project khác như thế nào?** Nếu A dùng B và B dùng C thì A có tự thấy C không? Scope của C trong A có thể khác scope mà B đã khai báo không?

Ví dụ cấu hình một dependency trực tiếp trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
    <scope>compile</scope>
</dependency>
~~~

`compile` ở đây ảnh hưởng classpath dùng để biên dịch, chạy và test dự án, đồng thời có thể được truyền qua dependency bắc cầu. Nếu bỏ hoàn toàn `<scope>`, Maven dùng **`compile` mặc định**.

Một sơ đồ để phân biệt:

~~~text
                       project hiện tại
                              |
              +---------------+----------------+
              |               |                |
          compile CP       test CP         runtime CP
              |               |                |
       javac mã chính   biên dịch/chạy    chạy mã chính
                        kiểm thử          với dependencies
                              |
                    scope quyết định
                    thành phần ở mỗi CP

Project A  --dependency-->  Project B  --dependency-->  Library C
                scope A→B                   scope B→C
                              |
                      scope kết quả của C
                      được Maven suy ra cho A
~~~

**Classpath** là tập các thư mục/class/JAR mà Java compiler, test runner hoặc JVM được cho phép tìm lớp. Maven scope không trực tiếp sửa classloader của một chương trình bất kỳ; các plugin Maven và cách bạn chạy Java phải sử dụng classpath do Maven chọn. Nếu tự chạy `java -cp target/classes ...`, bạn **chỉ** cấp các lớp trong `target/classes`, không tự động đưa mọi dependency vào classpath.

## 2. Các classpath cần phân biệt

Khi nói “thư viện có trên classpath”, hãy chỉ rõ thời điểm:

| Ngữ cảnh | Nội dung chủ yếu | Ví dụ hành động |
| --- | --- | --- |
| **Main compile classpath** | Những dependency cần để biên dịch `src/main/java` | `maven-compiler-plugin:compile` |
| **Test compile classpath** | Lớp đã biên dịch của mã chính và dependency cần cho `src/test/java` | `maven-compiler-plugin:testCompile` |
| **Test runtime classpath** | Mã chính, mã test và dependency dùng khi test chạy | `maven-surefire-plugin:test` |
| **Application runtime classpath** | Mã ứng dụng và thư viện cần chạy ứng dụng bình thường | `exec:java` với `classpathScope=runtime`, hoặc runtime classpath do launcher thiết lập |

Maven cũng có cơ chế resolve classpath với scope được các plugin dùng, ví dụ các mức `compile`, `runtime`, `test`; trong thực tế **test compile** và **test execution** đều cần một tập thư viện giàu hơn main compile classpath. Không nhầm “test runtime” với “application runtime”: JUnit có thể cần khi chạy test nhưng không phải khi chạy ứng dụng giao cho người dùng.

Một file JAR bình thường được Maven JAR Plugin đóng gói thường là **thin JAR**: chứa class/resource của project, **không tự nhét tất cả dependency JAR vào trong**. Scope chỉ xác định thư viện nào được chọn cho từng ngữ cảnh; muốn một *fat/uber JAR* cần cấu hình packaging/plugin riêng, ví dụ Maven Shade Plugin. Khi triển khai WAR, phạm vi `provided` còn được dùng để tránh mang những thư viện container đã cung cấp.

## 3. Sáu scope Maven và hành vi thực tế

Maven có sáu scope chuẩn: `compile`, `provided`, `runtime`, `test`, `system`, `import`.

### 3.1. `compile` — mặc định, phổ biến nhất

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
    <scope>compile</scope>
</dependency>
~~~

Mã chính có thể `import org.apache.commons.lang3.StringUtils;` lúc biên dịch. Thư viện cũng dùng được khi test và chạy ứng dụng, nếu runtime launcher cung cấp dependency classpath. `compile` có khả năng **truyền bắc cầu** sang dự án tiêu thụ thư viện của bạn.

Có thể bỏ `<scope>compile</scope>` vì đây là giá trị mặc định. Nên khai báo trực tiếp những thư viện mà mã nguồn project thực sự dùng, ngay cả khi chúng cũng tình cờ có mặt qua một thư viện khác.

### 3.2. `provided` — biên dịch được, runtime bên ngoài cung cấp

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

Mã trong web app có thể biên dịch với các lớp Servlet API, nhưng một Servlet container tương thích được kỳ vọng cung cấp chúng khi ứng dụng chạy. Maven đưa dependency `provided` vào classpath biên dịch mã chính và kiểm thử, **không đưa vào application runtime classpath do Maven xử lý**. Nó không được export như dependency bắc cầu thông thường tới project khác.

Đây là **hợp đồng triển khai**, không phải lời hứa rằng lớp chắc chắn có ở production: nếu runtime không cung cấp đúng phiên bản API, ứng dụng vẫn có thể gặp `ClassNotFoundException` hoặc `NoClassDefFoundError`. Với ứng dụng Java SE thường chạy bằng `java -cp`, không nên dùng `provided` chỉ để giảm kích thước JAR khi thực tế không có runtime nào cung cấp thư viện.

### 3.3. `runtime` — không cần compile mã chính, nhưng cần khi chạy

Ví dụ driver JDBC mà mã chính chỉ gọi API chuẩn `java.sql`:

~~~xml
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <version>2.2.224</version>
    <scope>runtime</scope>
</dependency>
~~~

Nếu mã chính chỉ dùng `DriverManager.getConnection(...)` và không import trực tiếp class của H2, chương trình không cần H2 để **biên dịch** mã chính nhưng cần driver khi **chạy**. Maven đưa `runtime` vào classpath chạy ứng dụng và classpath test, **không** đưa vào main compile classpath.

Ngược lại, nếu `src/main/java` import trực tiếp `org.h2.Driver`, mã chính **cần** H2 khi biên dịch; lúc đó `runtime` có thể khiến javac báo `package org.h2 does not exist`. Sửa bằng cách xem lại thiết kế code và chọn scope phù hợp, không ép mọi thư viện thành `runtime`.

### 3.4. `test` — chỉ để biên dịch/chạy kiểm thử

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
~~~

JUnit được test code sử dụng, không cần cho `src/main/java` và không nên là dependency runtime của sản phẩm bình thường. `test` có mặt trong test compile/test runtime classpath, nhưng không nằm trong main compile và application runtime classpath. Nó không tự được truyền thành dependency bắc cầu của project khác tiêu thụ JAR chính.

**Quan trọng:** Nếu source chính dùng class của JUnit thì đó là vấn đề kiến trúc hoặc sai scope; không đổi `test` thành `compile` theo phản xạ mà hãy xác định API thực sự cần ở production.

### 3.5. `system` — tham chiếu JAR ở đường dẫn máy, không khuyến nghị

Ví dụ minh họa cú pháp `system` (không phải POM hoàn chỉnh):

~~~xml
<dependency>
    <groupId>vendor.local</groupId>
    <artifactId>legacy-api</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>${project.basedir}/lib/legacy-api.jar</systemPath>
</dependency>
~~~

Maven không lấy artifact này từ repository mà sử dụng đường dẫn file cục bộ. Build trở nên kém tái lập khi file không tồn tại trên máy CI hoặc trên máy người khác. `system` là trường hợp đặc biệt có hành vi gần `provided` ở một số classpath, **không phải một cách thông thường để tải thư viện hoặc phát hành dependency**.

Thực hành tốt hơn: đưa JAR được cấp phép vào **repository riêng** và khai báo dependency bằng GAV cùng scope thực sự cần (`compile`, `runtime` hoặc `test`). Không dùng `systemPath` để trỏ ngẫu nhiên vào JAR trong cài đặt JDK 17; các lớp chuẩn của JDK vốn không cần khai báo dependency Maven.

### 3.6. `import` — chỉ dùng ở dependency management với POM BOM

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`import` chỉ hợp lệ cho dependency `type=pom` trong `<dependencyManagement>`. Nó **nhập danh sách version/quy tắc quản lý** từ BOM vào mô hình quản lý dependency, **không** đưa chính BOM lên compile/test/runtime classpath.

Sau khi import BOM, project vẫn cần khai báo dependency thực sự dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Version có thể lấy từ BOM. `dependencyManagement` chỉ định cách **quản lý** dependency, không có nghĩa artifact tự được thêm vào project dù chưa có đường dependency thực tế.

## 4. Bảng classpath dành cho dependency khai báo trực tiếp

Với một dependency **trực tiếp**, các trường hợp phổ biến:

| Scope trực tiếp | Main compile | Test compile/test runtime | App runtime | Lan tới project tiêu thụ |
| --- | :---: | :---: | :---: | --- |
| `compile` | Có | Có | Có | Có, theo quy tắc bắc cầu |
| `provided` | Có | Có | Không | Không export trực tiếp như dependency thông thường |
| `runtime` | Không | Có | Có | Có, kết hợp scope theo đường phụ thuộc |
| `test` | Không | Có | Không | Không export trực tiếp |
| `system` | Tùy cơ chế tương đương provided/transport | Tùy cơ chế | Không nên dùng để phân phối | Không dùng như cơ chế repository transitive |
| `import` | Không | Không | Không | Chỉ ảnh hưởng dependency management |

Bảng mang ý nghĩa **dependency resolution trong Maven**; một test plugin có thể tùy chỉnh classpath và môi trường runtime cũng có thể cung cấp thư viện riêng. Không suy ra những gì có sẵn trên JVM chỉ từ tên scope.

Với bốn scope thường dùng, có thể ghi nhớ:

~~~text
compile  : main compile + test + runtime
provided : main compile + test, KHÔNG app runtime
runtime  : test + runtime, KHÔNG main compile
test     : chỉ test compile/test run
~~~

**Phân biệt câu “`provided` không transitive” với một trường hợp bên trong cây:** Nếu project X khai báo một dependency A ở scope `provided`, khi Maven giải quyết các dependency **của A để build X**, một số dependency compile/runtime nằm dưới A vẫn có thể xuất hiện ở phạm vi `provided` của X theo bảng kết hợp ở mục 6. Nhưng project khác tiêu thụ artifact X sẽ **không tự nhận dependency `provided` X khai báo**. Đây là hai thời điểm giải quyết hai cây phụ thuộc khác nhau, không mâu thuẫn.

## 5. Transitive dependency: A → B → C

Giả sử:

~~~text
A (ứng dụng)
└── B (thư viện trực tiếp của A)
    └── C (thư viện trực tiếp của B)
~~~

A chỉ ghi B trong `pom.xml`. Khi Maven resolve B, nó đọc POM của B để tìm C. Nếu quy tắc scope/optional/exclusions/version mediation cho phép, C trở thành **transitive dependency** của A.

Ví dụ: `B` dùng Commons Lang trong mã chính, `A` phụ thuộc B scope `compile`. Maven thông thường sẽ đưa Commons Lang vào classpath compile/runtime của A với scope hiệu lực `compile`.

Tuy nhiên **không phải mọi dependency con đều được kéo lên với scope nguyên gốc**. Maven có quy tắc hợp nhất giữa:

- **Scope của B trong A** — do A khai báo trực tiếp.
- **Scope của C trong B** — do B khai báo.
- **Scope hiệu lực của C trong A** — kết quả Maven tính sau khi đi qua cạnh A→B.

Đây là lý do scope vừa giới hạn classpath vừa giới hạn tính bắc cầu. Một dependency ở scope `test` của B không tự thành dependency test của A; nếu A muốn kiểm thử với C, A cần khai báo C trực tiếp hoặc nhận qua một đường hợp lệ khác.

## 6. Ma trận chính thức kết hợp scope bắc cầu

Bảng dưới áp dụng cho những scope `compile`, `provided`, `runtime`, `test` trong ví dụ A→B→C, theo tài liệu **Introduction to the Dependency Mechanism** của Apache Maven. Hàng là **scope B được khai báo trực tiếp trong A**. Cột là **scope C được khai báo trong B**. Ô là scope hiệu lực của **C trong A**.

| Scope A→B \\ Scope B→C | `compile` | `provided` | `runtime` | `test` |
| --- | --- | --- | --- | --- |
| **`compile`** | `compile` | Bỏ qua | `runtime` | Bỏ qua |
| **`provided`** | `provided` | Bỏ qua | `provided` | Bỏ qua |
| **`runtime`** | `runtime` | Bỏ qua | `runtime` | Bỏ qua |
| **`test`** | `test` | Bỏ qua | `test` | Bỏ qua |

“Bỏ qua” nghĩa là **đường bắc cầu đó không đưa C vào A**. Nếu A khai báo C trực tiếp hoặc có một đường phụ thuộc khác không bị loại, C vẫn có thể xuất hiện trong dependency graph cuối. Vì vậy không được kết luận “C không có ở đâu cả” chỉ từ một ô bị bỏ qua.

### 6.1. Bốn tình huống tiêu biểu

**Trường hợp 1: A→B `compile`, B→C `compile`.**

~~~text
A
└── B : compile
    └── C : compile  → C được nhìn thấy ở A với scope compile
~~~

A có thể dùng C khi compile, chạy và test. Tuy nhiên nếu mã A import class của C trực tiếp, nên khai báo C trực tiếp để tránh phụ thuộc vào cấu trúc nội bộ của B.

**Trường hợp 2: A→B `compile`, B→C `runtime`.**

~~~text
A
└── B : compile
    └── C : runtime → C ở A có scope runtime
~~~

C có trong runtime/test classpath của A nhưng không trong main compile classpath. Đây là cách một implementation/driver chỉ cần lúc chạy được mang theo qua một library.

**Trường hợp 3: A→B `runtime`, B→C `compile`.**

~~~text
A
└── B : runtime
    └── C : compile → C ở A có scope runtime
~~~

Mặc dù B cần C khi biên dịch, A chỉ cần B ở runtime. Vì vậy Maven đưa C tới runtime của A nhưng không cần đặt C trên compile classpath của A.

**Trường hợp 4: A→B `compile`, B→C `test` hoặc `provided`.**

~~~text
A
└── B : compile
    ├── C : test     → C không đi theo đường transitive này tới A
    └── D : provided → D không đi theo đường transitive này tới A
~~~

Unit test của B không bắt người dùng B phải mang JUnit vào runtime. Nếu B compile bằng Servlet API `provided`, thì container mà A chạy trên đó phải cung cấp API phù hợp; Maven không export nó như compile dependency của A.

### 6.2. Khi B được A khai báo `test`

Giả sử A dùng B chỉ để kiểm thử:

~~~text
A
└── B : test
    ├── C : compile → C ở A mang scope test
    └── D : runtime → D ở A mang scope test
~~~

C và D có thể hỗ trợ test của A, nhưng không thuộc application runtime của A. Điều này giải thích vì sao thư viện hỗ trợ test có thể kéo nhiều dependency vào test classpath mà không trực tiếp làm tăng runtime dependencies của sản phẩm.

**Điều không nên làm:** xem scope là phép cộng tuyến tính hoặc “giữ cái scope hẹp hơn”. Ma trận là quy tắc Maven có định nghĩa; `compile + runtime` ra `runtime`, nhưng `provided + runtime` ra `provided`, không thể suy đoán bằng một quy tắc đơn giản chung.

## 7. Ví dụ Maven đa module Java 17: quan sát bắc cầu trong thực tế

Ta tạo reactor với hai module: `library` và `application`.

- `library` trực tiếp dùng **Commons Lang** trong mã nguồn, scope `compile`.
- `library` khai báo **Commons IO** scope `runtime`, để mô phỏng một thư viện sử dụng implementation/helper lúc chạy.
- `application` trực tiếp phụ thuộc `library` scope `compile`.
- `application` dùng **JUnit Jupiter** scope `test`.
- Java `Main` minh họa Commons IO có thể được load qua **runtime classpath** trong khi app không import nó lúc compile.

Để tránh phụ thuộc tình cờ vào phiên bản plugin máy cục bộ, POM ghim phiên bản compiler, surefire và exec plugin phù hợp Java 17. Các version chỉ là phiên bản dùng trong ví dụ, **không phải khẳng định mới nhất**.

### 7.1. Cấu trúc

~~~text
scope-lab/
├── pom.xml
├── library/
│   ├── pom.xml
│   └── src/main/java/demo/library/TextTools.java
└── application/
    ├── pom.xml
    ├── src/main/java/demo/app/Main.java
    └── src/test/java/demo/app/MainTest.java
~~~

Các file đặt đúng đường dẫn `src/main/java` và `src/test/java`. Trong lệnh Maven, thư mục gốc là `scope-lab/`.

### 7.2. Parent `scope-lab/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.scope</groupId>
    <artifactId>scope-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>library</module>
        <module>application</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
        </plugins>
    </build>
</project>
~~~

`<modules>` cho phép Reactor build các module theo thứ tự phụ thuộc. `<parent>` trong POM con giúp các module kế thừa version Java và plugin. Aggregation (`modules`) và inheritance (`parent`) là hai cơ chế khác nhau; ví dụ khai báo cả hai để dễ tái lập.

### 7.3. `library/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>demo.scope</groupId>
        <artifactId>scope-lab</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>library</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
            <scope>compile</scope>
        </dependency>

        <dependency>
            <groupId>commons-io</groupId>
            <artifactId>commons-io</artifactId>
            <version>2.16.1</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
</project>
~~~

Ở `library`, Commons Lang thuộc compile classpath, Commons IO thuộc runtime/test classpath. Commons IO được khai báo dù mã `library` mẫu chưa gọi nó: mục tiêu ví dụ là **quan sát sự truyền scope `runtime`**. Trong code sản xuất, chỉ giữ một dependency nếu thực sự cần; không sao chép dependency thừa vào dự án thật.

### 7.4. `library/src/main/java/demo/library/TextTools.java`

~~~java
package demo.library;

import org.apache.commons.lang3.StringUtils;

public final class TextTools {
    private TextTools() {
    }

    public static String title(String text) {
        return StringUtils.capitalize(StringUtils.trimToEmpty(text));
    }
}
~~~

`StringUtils` là class của Commons Lang. `library` cần dependency `compile` vì mã Java có import trực tiếp nó.

### 7.5. `application/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>demo.scope</groupId>
        <artifactId>scope-lab</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>application</artifactId>

    <dependencies>
        <dependency>
            <groupId>demo.scope</groupId>
            <artifactId>library</artifactId>
            <version>1.0.0</version>
            <scope>compile</scope>
        </dependency>

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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.app.Main</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`application` không cần khai báo Commons Lang/IO trực tiếp để Maven thử **bắc cầu** qua `library`; nhưng nếu `application` bắt đầu import trực tiếp API của các thư viện này trong mã chính, **thực hành tốt là thêm dependency trực tiếp tương ứng**. Trong ví dụ, `Main` chỉ import `TextTools`; Commons IO được kiểm tra bằng cơ chế reflection phục vụ bài học, không phải API app sản xuất.

### 7.6. `application/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.library.TextTools;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println(TextTools.title("  hello maven  "));

        Class.forName("org.apache.commons.io.IOUtils");
        System.out.println("runtime IOUtils=available");
    }
}
~~~

Vì `Class.forName` chỉ nhận chuỗi tên class, mã chính không import `IOUtils` nên không cần Commons IO trong main compile classpath. Khi exec plugin chạy bằng `runtime` classpath, class từ Commons IO có thể được nạp. Đó là minh họa có chủ đích về vai trò của scope `runtime`.

### 7.7. `application/src/test/java/demo/app/MainTest.java`

~~~java
package demo.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import demo.library.TextTools;
import org.junit.jupiter.api.Test;

class MainTest {
    @Test
    void formatsText() {
        assertEquals("Hello maven", TextTools.title("  hello maven  "));
    }
}
~~~

Đây là unit test JUnit 5 thực, dùng `junit-jupiter` scope `test`. Test thuộc `src/test/java`, nên không làm cho JUnit trở thành dependency runtime của sản phẩm.

## 8. Chạy thử và kiểm tra kết quả

Cần **JDK 17+** cùng Maven hỗ trợ, kết nối repository để tải dependency và plugin. Từ thư mục `scope-lab/`:

~~~bash
mvn -B -ntp clean install
~~~

Maven Reactor build parent → `library` → `application`; biên dịch Java, chạy test và đóng gói. `install` cài `library` và `application` vào Maven local repository để lần gọi plugin riêng lẻ ở module con có thể resolve dependency giữa hai module. Trên dự án chuẩn, lệnh thành công có `BUILD SUCCESS` và test `formatsText` PASS.

Sau đó chạy chương trình bằng exec plugin đã cấu hình trong `application/pom.xml`:

~~~bash
mvn -B -ntp -f application/pom.xml exec:java
~~~

Trong ví dụ, **hai dòng do `Main` in ra** là:

~~~text
Hello maven
runtime IOUtils=available
~~~

Console còn có thể chứa các dòng Maven `[INFO]`, nên đây là **stdout của chương trình**, không phải toàn bộ log của Maven. Nếu main class hoặc Commons IO không được đưa vào runtime classpath, exec có thể báo lỗi khác; khi đó cần kiểm tra POM và dependency tree.

**Không dùng lệnh `java -cp application/target/classes demo.app.Main` để chứng minh Maven bị lỗi.** Với lệnh đó, classpath JVM chỉ có class của application, chưa có JAR của `library`, Commons Lang và Commons IO. Đây là khác biệt giữa classpath do exec plugin tạo và classpath thủ công.

### Vì sao Commons IO tới được `application`?

Cây đơn giản hóa:

~~~text
application
├── library                  : compile (trực tiếp)
│   ├── commons-lang3        : compile (bắc cầu)
│   └── commons-io           : runtime (bắc cầu)
└── junit-jupiter            : test (trực tiếp)
    ├── junit-jupiter-api    : test (bắc cầu)
    └── ...                  : test (các phần JUnit khác)
~~~

Các dependency khác do JUnit hoặc plugin kéo theo có thể khiến cây thực lớn hơn. Bảng scope cho biết:

- `application → library:compile` + `library → commons-lang3:compile` ⇒ `commons-lang3` hiệu lực `compile` trong application.
- `application → library:compile` + `library → commons-io:runtime` ⇒ `commons-io` hiệu lực `runtime` trong application.
- `application → junit-jupiter:test` và các dependency con JUnit phù hợp ⇒ chỉ dùng cho test, không làm Commons IO bị chuyển thành `test`.

Khi `application` chỉ có Java source import `TextTools`, phần compile vẫn hợp lệ. Khi chạy `Main`, `TextTools` cần Commons Lang, và `Class.forName` kiểm tra Commons IO có trong runtime classpath.

## 9. `dependency:tree`: kiểm tra scope thực sự được chọn

Dùng Maven Dependency Plugin để nhìn dependency graph đã resolve, thay vì đoán từ POM:

~~~bash
mvn -B -ntp -f application/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Sau bước `install` ở trên, Maven có thể resolve `demo.scope:library:1.0.0` từ local repository. Một **trích đoạn minh họa** của cây là:

~~~text
demo.scope:application:jar:1.0.0
+- demo.scope:library:jar:1.0.0:compile
|  +- org.apache.commons:commons-lang3:jar:3.14.0:compile
|  \- commons-io:commons-io:jar:2.16.1:runtime
\- org.junit.jupiter:junit-jupiter:jar:5.11.4:test
   \- ... (các module JUnit khác)
~~~

Đừng yêu cầu output phải đúng tuyệt đối ký tự `+-`/`\-` hay vị trí mọi node: cách in, phiên bản dependency plugin và phần dependency phụ có thể khác. Điều cần đối chiếu là **tọa độ, version và effective scope**.

Có thể lọc theo scope của dependency plugin:

~~~bash
mvn -B -ntp -f application/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dscope=runtime
~~~

Tham số `scope` là bộ lọc theo cơ chế resolve, không nên hiểu đơn giản như câu lệnh “chỉ in những node có nhãn `:runtime`”; runtime resolution thường gồm cả dependency `compile` cần cho ứng dụng chạy.

Để thấy cả dependency bị loại bởi conflict/mediation khi plugin hỗ trợ, dùng:

~~~bash
mvn -B -ntp -f application/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
~~~

Với project thực, muốn tìm một thư viện:

~~~bash
mvn -B -ntp dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Đây là ví dụ filtering của Dependency Plugin. Khi alias `dependency` resolve plugin version khác, tham số/hành vi cụ thể có thể đổi; nếu cần tái lập, ghim tên plugin đầy đủ và phiên bản như các lệnh trước. Ngoài `tree`, có thể tham khảo `dependency:analyze` để phát hiện dependency được dùng nhưng chưa khai báo trực tiếp hoặc khai báo thừa; công cụ phân tích bytecode có giới hạn với reflection, annotation processor và dynamic loading nên kết quả cần được xem xét, không xóa bừa.

## 10. Cố ý đổi scope để hiểu lỗi classpath

Một cách học tốt là thay **một scope tại một thời điểm** rồi chạy `clean test`/`clean package` và đối chiếu tree.

### 10.1. Đổi `application → library` từ `compile` thành `runtime`

Trong `application/pom.xml`, đổi:

~~~xml
<scope>compile</scope>
~~~

của dependency `demo.scope:library` thành:

~~~xml
<scope>runtime</scope>
~~~

Với `Main.java` đang có `import demo.library.TextTools;`, main compile classpath **không có `library`**. Khi chạy `mvn clean package`, `javac` thường báo đại ý `package demo.library does not exist` hoặc `cannot find symbol`.

Đây không phải lỗi tải dependency (artifact có thể tồn tại), mà là **scope không phù hợp với thời điểm cần class**. Khôi phục `compile` khi mã chính có import trực tiếp `TextTools`.

### 10.2. Đổi `application → library` thành `provided`

Main Java vẫn có thể biên dịch vì `provided` có ở compile classpath. Tuy nhiên `library` và các dependency hiệu lực của nó theo đường này **không ở application runtime classpath do Maven cung cấp**. Khi exec plugin được cấu hình `runtime`, quá trình chạy ứng dụng có thể không tìm được `demo.library.TextTools`.

`provided` chỉ hợp lý nếu **runtime khác sẽ cung cấp chính các lớp đó**, ví dụ app server/container. Trong ví dụ CLI không có bên cung cấp, chọn `provided` là sai.

### 10.3. Đổi JUnit `test` thành `compile`

Trong `application/pom.xml`, nếu đổi JUnit Jupiter thành `compile`, main compile/runtime có thể nhận JUnit và các dependency hợp lệ đi kèm, làm bề mặt dependency rộng hơn mức cần thiết. Không vì test phải import JUnit mà đưa JUnit vào scope `compile`; bản thân `test` đã đủ cho `src/test/java`.

### 10.4. Đổi Commons IO `runtime` thành `test` ở library

Khi `library` gắn Commons IO ở scope `test`, dependency đó không còn được truyền qua `library` để tạo runtime dependency của `application`. `Class.forName("org.apache.commons.io.IOUtils")` trong `Main` có thể gây `ClassNotFoundException` khi chạy với runtime classpath của app. Việc `library` có thể build thành công không chứng minh Commons IO còn cần và hiện diện trong app.

**Sau bài thử**, khôi phục POM nguyên gốc và chạy:

~~~bash
mvn -B -ntp clean install
mvn -B -ntp -f application/pom.xml exec:java
~~~

Vì các dependency được Maven resolve theo metadata POM, nên khi thay scope mà chỉ chạy một goal từ module khác với artifact/POM cũ trong local repository, kết quả có thể chưa phản ánh thay đổi. Build/install lại đúng reactor trước khi so sánh.

## 11. `provided` và môi trường container: không phải “phụ thuộc không cần nữa”

Giả sử một web application biên dịch Servlet code:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

Mã Java dùng `HttpServlet` cần Servlet API khi compile. Nhưng container hỗ trợ Jakarta Servlet 6 cung cấp lớp đó lúc deploy WAR. Nếu đóng thêm một bản Servlet API không tương thích vào thư viện runtime của ứng dụng, có thể gây xung đột classloader.

**Kết quả cần hiểu đúng:**

- `provided` là tuyên bố môi trường triển khai cung cấp dependency; không phải một công tắc tăng tốc build.
- Maven đưa `provided` vào classpath compile/test, không đưa vào normal application runtime dependency classpath.
- Với WAR, plugin đóng gói và container có các quy tắc riêng về `WEB-INF/lib`. Đừng nhầm classpath runtime của Maven với toàn bộ classpath trên server.
- Nếu chạy web app trên một môi trường không cung cấp đúng Servlet API, lỗi thiếu class vẫn có thể xảy ra.

Đối với `spring-boot` hoặc các framework đóng gói executable JAR/WAR có plugin tùy biến, cách dependency được nhét vào artifact có thể có đặc thù riêng. Để kết luận một thư viện nằm trong **artifact cuối** hay không, phải xem plugin packaging và inspect JAR/WAR thực tế chứ không chỉ nhìn bảng scope.

## 12. `optional` và `exclusions` tác động lên bắc cầu như thế nào?

Scope không phải cơ chế duy nhất khiến dependency “biến mất”. Maven còn có `optional` và `exclusions`.

### 12.1. Dependency optional

Một thư viện `B` có thể dùng `C` làm chức năng tùy chọn:

~~~xml
<dependency>
    <groupId>demo.libs</groupId>
    <artifactId>feature-c</artifactId>
    <version>1.0.0</version>
    <optional>true</optional>
</dependency>
~~~

Nếu `B` khai báo C là optional, project A tiêu thụ B **không tự kéo C vào theo đường bắc cầu ấy**. A muốn sử dụng chức năng C thì phải khai báo C trực tiếp trong POM của A. Optional không có nghĩa C bị xóa khỏi classpath **của chính B** khi B xây dựng/test; nó chủ yếu ảnh hưởng người tiêu thụ B.

### 12.2. Exclusions ở cạnh dependency

Một project A có thể loại một dependency con khi kéo B vào:

~~~xml
<dependency>
    <groupId>demo.libs</groupId>
    <artifactId>library-b</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>demo.libs</groupId>
            <artifactId>unwanted-c</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Exclusion áp dụng theo **đường phụ thuộc đi qua khai báo B**. Nó không đảm bảo C không thể xuất hiện qua một đường khác trong dependency graph. Cũng không nên dùng exclusions để giấu một lỗi version mà chưa tìm rõ ai cần thư viện nào.

`optional` và `exclusion` không phải scope thứ bảy/thứ tám. Chúng điều khiển khả năng xuất hiện của node trong đồ thị; sau khi node được chọn, scope vẫn điều khiển classpath tương ứng.

## 13. Version mediation: vì sao thấy một phiên bản khác mong đợi?

Khi một artifact xuất hiện qua nhiều đường:

~~~text
application
├── library-A : compile
│   └── utility:1.0 : compile
└── library-B : compile
    └── utility:2.0 : compile
~~~

Maven không đơn giản mang cả hai version vào cùng classpath thông thường. Quy tắc *dependency mediation* của Maven chọn **nearest definition**: đường gần project nhất thắng; nếu cùng độ sâu, khai báo xuất hiện trước trong cây phụ thuộc thắng. Điều này có thể dẫn tới thư viện version khác kỳ vọng khi thứ tự dependency hoặc cấu trúc graph đổi.

Những điểm cần phân biệt:

- **Scope propagation** xác định đường nào được đưa vào và scope kết quả là gì.
- **Version mediation** xác định version nào được chọn khi nhiều đường cùng nhắc một artifact.
- **`dependencyManagement`** cho phép áp version/scope quản lý cho dependency phù hợp và có thể ưu tiên trước kết quả mediation của dependency bắc cầu.
- **Dependency direct** trong project thường làm đường tới artifact đó ngắn nhất và ghi rõ ý định dùng phiên bản.

Ví dụ quản lý version trong parent (đây là **đoạn XML**, không phải POM hoàn chỉnh):

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

Chỉ có đoạn này **chưa thêm Commons Lang vào classpath**. Nó chỉ quản lý version khi dependency được dùng trực tiếp hoặc xuất hiện qua đường hợp lệ theo quy tắc Maven. Không coi dependency management là một cơ chế “force thêm thư viện”.

Một bẫy khác: `<dependencyManagement>` của project **không tự điều khiển đồ thị dependency riêng của Maven plugins**. Plugin dependencies có cơ chế riêng trong `<build><plugins>`/`<pluginManagement>`; đừng dùng project dependency management để giả định đã giải quyết xung đột trong plugin.

## 14. Direct dependency và transitive dependency: nên khai báo thế nào?

Maven tự kéo dependency bắc cầu giúp POM gọn hơn, nhưng **lạm dụng** tính năng này có thể làm code phụ thuộc ngầm vào implementation của thư viện khác.

Ví dụ ban đầu app chỉ gọi `TextTools.title`, nên chỉ cần khai báo `demo.scope:library` trực tiếp. Nhưng nếu một ngày `Main.java` import `org.apache.commons.lang3.StringUtils` và gọi API đó trực tiếp, app lúc này **phụ thuộc trực tiếp vào Commons Lang về mặt mã nguồn**. Nên thêm vào `application/pom.xml`:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
    <scope>compile</scope>
</dependency>
~~~

Nhờ vậy, khi `library` đổi implementation sang một thư viện khác, app vẫn khai báo đúng dependency mà nó dùng. Đây cũng là cách POM phản ánh thiết kế module rõ ràng.

Một thư viện `runtime` như JDBC driver thường cần có trong package/runtime classpath, nhưng nếu app không import API cụ thể của driver thì có thể để scope runtime. Trong ví dụ đào tạo, Commons IO nằm ở library để minh họa propagation; trong ứng dụng thật, thành phần nào có hợp đồng runtime trực tiếp với thư viện thì nên tự chịu trách nhiệm khai báo sao cho phù hợp.

**Đừng kết luận tất cả transitive dependencies là xấu.** Chúng là chức năng cốt lõi của Maven. Quy tắc là khai báo **các dependency mà chính source/module có hợp đồng sử dụng trực tiếp**, và theo dõi transitive graph qua kiểm thử, dependency scanning, version policy.

## 15. Test classpath: scope `test` không có nghĩa chỉ dùng lúc `mvn test`

Một dependency test-scoped có thể được resolve khi Maven thực thi **bất kỳ goal nào cần test classpath**, không chỉ khi lệnh dừng ở phase `test`. Ví dụ `mvn verify` thường đi qua các phase compile/test rồi dùng thông tin test ở các plugin khác.

- `src/main/java` không thể compile code import JUnit chỉ vì JUnit là `test`.
- `src/test/java` được biên dịch với JUnit và những class cần thiết từ mã chính.
- Surefire/Failsafe sử dụng test classpath với cấu hình tùy plugin.
- `target/classes` là output của mã chính; `target/test-classes` là output của mã test.
- Java chạy ứng dụng bình thường không tự có `target/test-classes` hoặc test-scope JAR.

**Không nhầm dependency scope với tên Maven phase**: `runtime` không phải một phase, `test` vừa là một phase của lifecycle vừa là tên một dependency scope — nhưng đó là hai khái niệm khác nhau.

Nếu mã chính import class từ dependency `runtime` và compiler không tìm thấy, nguyên nhân không phải thiếu file test; hãy kiểm tra main compile classpath. Nếu test chạy báo thiếu class, kiểm tra test runtime classpath, dependency transitive/optional và plugin launcher.

## 16. Phân biệt project dependencies và plugin dependencies

POM có thể chứa:

~~~xml
<dependencies>
    <!-- Thư viện mà mã ứng dụng/test dùng -->
</dependencies>
~~~

và:

~~~xml
<build>
    <plugins>
        <!-- Công cụ thực thi các goal Maven, ví dụ compiler/surefire -->
    </plugins>
</build>
~~~

Một plugin Maven có thể tự kéo dependency của plugin để chạy goal. Những dependency đó **không mặc nhiên trở thành thư viện compile/runtime của mã ứng dụng**.

Ví dụ:
- Maven Compiler Plugin cần những thư viện của plugin để vận hành, không vì vậy mà chúng được đưa vào project runtime classpath.
- JUnit `test` được project dùng trong test, không nên nhầm với dependency nội bộ của Surefire.
- Khi cấu hình plugin `<dependencies>`, bạn đang thay đổi **plugin realm**/cách plugin chạy, không phải khai báo project dependency cho `Main.java`.
- `dependencyManagement` của project quản lý project dependencies, không tự đổi versions của plugin transitive dependencies.

Khi gặp `ClassNotFoundException`, trước hết xác định lỗi xảy ra trong **ứng dụng**, **test runner**, **plugin Maven**, hay **container runtime**. Mỗi nơi có classloader/classpath khác nhau; sửa scope ở `<dependencies>` không chữa mọi lỗi plugin.

## 17. Classpath Maven và nội dung artifact có giống nhau không?

Không hoàn toàn. Scope ảnh hưởng selection của dependencies; artifact cuối phụ thuộc packaging plugin.

| Trường hợp | Maven thường làm gì | Điều cần kiểm chứng |
| --- | --- | --- |
| JAR mặc định | Đóng mã/resource project thành JAR thông thường | JAR không tự chứa tất cả dependency JAR |
| Maven Exec Plugin | Tạo classpath theo `classpathScope` và chạy `main` | Plugin đã được cấu hình `runtime` hay `test`? |
| WAR | Đóng web app theo quy tắc Maven WAR Plugin và scope | `provided` thường không được đóng vào `WEB-INF/lib`; container phải cung cấp |
| Maven Shade Plugin | Có thể gộp nhiều dependency vào một JAR | Bộ lọc/exclusions/transformers và dependency scopes nào được áp dụng? |
| Docker image | Có thể copy JAR, libs và launcher vào image | Entry point và các libs runtime có thực sự hiện diện? |
| Application server | Cung cấp nhiều thư viện ở classloader server | Version và visibility giữa webapp/server có tương thích? |

Một ứng dụng có `mvn package` thành công vẫn có thể gặp `NoClassDefFoundError` lúc deploy nếu launcher thiếu runtime dependencies. Ngược lại, một lớp của `provided` có thể tồn tại trên server nhưng không ở classpath khi chạy riêng trên laptop. Maven không thể bảo đảm mọi biến thể runtime bên ngoài trùng với môi trường build.

## 18. Chẩn đoán lỗi classpath theo giai đoạn

| Lỗi/triệu chứng | Giai đoạn đáng nghi | Kiểm tra |
| --- | --- | --- |
| `package ... does not exist` trong `src/main/java` | Main compile | Có dependency trực tiếp đúng scope `compile`/`provided` không? Có bị scope `runtime`/`test` không? |
| `package org.junit.jupiter.api does not exist` trong mã test | Test compile | JUnit `test` đã khai báo chưa, dependency resolve thành công không? |
| `ClassNotFoundException` khi chạy app | Application runtime | Launcher có runtime classpath không, dependency `runtime`/`compile` có được đưa vào không? |
| `NoClassDefFoundError` khi chạy trên server | Runtime/classloader | Có thiếu thư viện `provided`, xung đột version hoặc thiếu dependency transitive không? |
| `NoSuchMethodError` dù class tồn tại | Runtime version/linkage | Version mediation, dependency khác phiên bản compile/runtime, classloader |
| JAR build được nhưng không khởi chạy bằng `java -jar` | Packaging/launcher | Manifest/Main-Class, thin/fat JAR, dependency classpath |
| Thư viện test lọt vào sản phẩm | Scope/packaging tùy biến | Dependency test có bị đổi `compile` không, shade/assembly cấu hình thế nào? |
| Dependency không xuất hiện trong tree | Graph selection | `test`/`provided` của dependency cha, optional, exclusions, profile, wrong module |
| Dependency xuất hiện scope khác dự kiến | Transitive propagation | Lần theo A→B→C và bảng kết hợp |
| Version không như POM library | Mediation/management | Xem cây đầy đủ, direct version, `dependencyManagement`, BOM |

Một cách gỡ lỗi có hệ thống:

1. **Xác định class thiếu** và thư viện chứa class đó, nếu biết.
2. **Xác định lúc nào lỗi xảy ra**: `compile`, `testCompile`, Surefire, exec, packaging hay production runtime.
3. **Xem dependency tree của đúng module**; không chỉ đọc parent POM.
4. **Đối chiếu scope** trực tiếp và mọi đường bắc cầu liên quan.
5. **Kiểm tra version cuối** qua tree, dependency management, BOM và exclusions.
6. **Kiểm tra artifact/launcher** nếu lỗi chỉ xảy ra sau khi Maven báo BUILD SUCCESS.
7. **Sửa tại nguồn**: scope đúng, dependency trực tiếp, runtime packaging, managed version hoặc removal/exclusion có lý do.
8. **Chạy lại đúng môi trường** và kiểm tra test/output, không dựa vào JAR hoặc cache cũ.

Với lỗi resolve dependency (HTTP 401/403, artifact not found, TLS), vấn đề có thể là repository/settings chứ không phải scope. Trước khi sửa scope, cần phân biệt rõ lỗi **không tải được JAR** với lỗi **JAR có tải nhưng không có trong classpath của goal đang chạy**.

## 19. `dependency:tree` và các công cụ hỗ trợ quan sát

Các lệnh hữu ích cho project hiện tại:

~~~bash
mvn -B -ntp dependency:tree
mvn -B -ntp dependency:analyze
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

- **`dependency:tree`**: quan sát đồ thị resolve và scope hiện hành; lọc theo artifact khi cần.
- **`dependency:analyze`**: gợi ý dependency đã dùng nhưng chưa khai báo hoặc khai báo nhưng không dùng. Có thể báo sai với reflection, generated code, service provider và runtime-only classes.
- **`help:effective-pom`**: xem dependencies/management sau inheritance và profile activation, nhưng không thay thế cây resolve.
- **`mvn -version`**: kiểm tra Maven/JDK dùng để build; cần khi `maven.compiler.release` hoặc công cụ khác không phù hợp.

Nếu build ở CI có profile hoặc settings riêng, thêm cùng các cờ `-P`, `-D`, `-s` để công cụ chẩn đoán phản ánh đúng lần build bị lỗi. Không tự cho rằng kết quả trên máy local đại diện cho classpath của production.

Khi chia sẻ `effective-pom.xml`, dependency tree hoặc log debug, rà soát tên repository/URL nội bộ, đường dẫn, username và token. Đừng paste `-X` log chứa secret lên diễn đàn công khai.

## 20. Những suy luận sai phổ biến

**Sai 1:** “Đã khai báo dependency trong POM thì Java luôn tìm được class.”  
**Đúng:** Maven phải chọn nó vào **classpath của giai đoạn cụ thể**; scope `test` không giúp main compile, scope `provided` không cấp bình thường vào runtime.

**Sai 2:** “`compile` nghĩa là chỉ cần lúc compile.”  
**Đúng:** `compile` thường có mặt ở compile, test và runtime classpath.

**Sai 3:** “`runtime` không cần khi test.”  
**Đúng:** Runtime dependencies cũng có thể cần cho test execution và được Maven đưa vào test classpath.

**Sai 4:** “Dependency con luôn giữ scope được thư viện cha khai báo.”  
**Đúng:** Scope được **tính lại theo ma trận** dựa trên đường bắc cầu.

**Sai 5:** “`test` của thư viện B sẽ tự kéo đến mọi project A dùng B.”  
**Đúng:** Test dependencies của B không được export qua đường transitive bình thường.

**Sai 6:** “`provided` giúp loại dependency khỏi mọi môi trường.”  
**Đúng:** Nó vẫn cần ở compile/test; runtime triển khai phải có nguồn khác cung cấp.

**Sai 7:** “`import` đưa cả BOM vào classpath.”  
**Đúng:** BOM import chỉ cung cấp dependency management, không là runtime/compile JAR.

**Sai 8:** “POM có `<dependencyManagement>` nên không cần `<dependencies>`.”  
**Đúng:** Management không tự thêm dependency, nó quản lý những dependency thực sự được khai báo/resolve.

**Sai 9:** “`mvn package` tạo fat JAR với tất cả compile/runtime deps.”  
**Đúng:** JAR thông thường không tự chứa dependencies; xem packaging plugin và cách launcher tạo classpath.

**Sai 10:** “Mọi JAR dưới `~/.m2/repository` đều có trong classpath.”  
**Đúng:** Local repository là bộ lưu artifact, còn classpath được Maven/plugin/launcher lựa chọn theo graph, scope và môi trường.

## 21. Bài tập có đáp án

1. **A→B compile, B→C runtime. C có scope gì ở A?** `runtime`. Nó có mặt khi chạy và test A, không ở main compile classpath của A.
2. **A→B runtime, B→C compile. C có scope gì ở A?** `runtime`, vì đường A→B chỉ cần cho runtime.
3. **A→B compile, B→C test. A có C qua đường này không?** Không. Muốn C cho test A, khai báo C riêng với `test` hoặc nhận qua một đường hợp lệ khác.
4. **A→B provided, B→C compile. C có scope gì trong graph của A?** `provided`, theo bảng kết hợp; không suy ra C được export từ artifact A sang project khác.
5. **A→B test, B→C runtime. C có scope gì trong A?** `test`. Nó giúp test nhưng không là application runtime của A.
6. **Ứng dụng import trực tiếp class của thư viện D nhưng D scope runtime. Chuyện gì dễ xảy ra?** Lỗi main compile classpath; nếu mã cần D lúc compile, cân nhắc `compile` hoặc thiết kế lại để chỉ cần ở runtime.
7. **Unit test dùng JUnit Jupiter. Scope phù hợp?** `test`, vì JUnit không là runtime dependency bình thường của ứng dụng.
8. **Ứng dụng WAR compile Servlet API do container cung cấp. Scope nào thường phù hợp?** `provided`, với điều kiện container thực sự cung cấp API tương thích.
9. **Import `junit-bom` có khiến JUnit API tự ở classpath không?** Không. Cần một dependency thực sự với groupId/artifactId phù hợp.
10. **Vì sao `ClassNotFoundException` khi dùng `java -cp target/classes`, dù `mvn exec:java` chạy thành công?** Vì lệnh `java -cp` thủ công không được cấp runtime dependency classpath mà exec plugin đã chọn.
11. **Cùng thư viện có version 1 qua đường ngắn và version 2 qua đường dài. Maven thường chọn gì?** Gần project nhất, trừ khi quy tắc direct/management/mediation khác can thiệp.
12. **Library B đánh dấu C optional. App A dùng B có tự thấy C không?** Không qua đường đó. A phải khai báo C nếu cần.
13. **Nếu exclusion loại C qua B, C có thể vẫn xuất hiện ở A không?** Có, nếu một dependency path khác hợp lệ mang C vào.
14. **Lệnh nào giúp kiểm tra scope hiệu lực và nguồn transitive?** `mvn dependency:tree` hoặc goal version-pinned của Maven Dependency Plugin.
15. **Một thư viện có class dùng trực tiếp trong app, nhưng hiện chỉ đến qua transitive dependency. Nên làm gì?** Khai báo dependency trực tiếp ở app với scope phù hợp để phản ánh hợp đồng code.

## 22. Checklist chọn scope cho một dependency mới

- [ ] Mã `src/main/java` có import trực tiếp API thư viện? Cân nhắc `compile`, trừ khi runtime/container chịu trách nhiệm cung cấp thì `provided`.
- [ ] Thư viện chỉ cần khi chạy app, mã chính không dùng API cụ thể để compile? Cân nhắc `runtime`.
- [ ] Chỉ dùng trong `src/test/java` hoặc test runner? Dùng `test`.
- [ ] Môi trường chạy thật có cung cấp thư viện và version tương thích? Kiểm tra trước khi dùng `provided`.
- [ ] Có thể dùng Maven repository thay cho đường dẫn file cục bộ? Tránh `system`.
- [ ] Cần BOM để quản lý versions? Dùng `import` trong `dependencyManagement`, sau đó khai báo dependencies cần thiết.
- [ ] Nếu library export dependency, đã xem **bảng scope bắc cầu** và consumer classpath?
- [ ] Nếu source trực tiếp dùng thư viện transitive, đã khai báo direct dependency rõ ràng?
- [ ] Nếu version conflict, đã xem `dependency:tree`, `dependencyManagement`, nearest definition và thứ tự?
- [ ] Nếu runtime lỗi, đã kiểm tra packaging/launcher thay vì chỉ đổi scope?
- [ ] Nếu cần giảm dependency, đã hiểu tác động của `optional` và `exclusions` trên từng đường?
- [ ] Đã chạy build/test và kiểm tra đúng môi trường triển khai trước khi phát hành?

## Tài liệu Apache Maven chính thức

- [Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): định nghĩa scope, bảng kết hợp bắc cầu, mediation, management, optional/exclusion và system scope.
- [Maven Dependencies](https://maven.apache.org/repositories/dependencies): giải thích dependency scopes và classpaths.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xuất cây dependency, verbose và bộ lọc scope.
- [Maven Dependency Plugin — dependency:analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html): phân tích dependency dùng/không dùng.
- [Maven Project Object Model](https://maven.apache.org/pom.html): cú pháp `<dependencies>`, `<dependencyManagement>`, scopes, optional và exclusions.

**Kết luận:** `scope` là quy tắc kiểm soát **dependency có mặt ở classpath nào** và **dependency đi theo các cạnh A→B→C ra sao**. Muốn đọc đúng hành vi Maven, hãy hỏi **đang build/test/chạy ở đâu?** và **dependency đi vào project qua đường nào?**; dùng `dependency:tree` để xác minh scope hiệu lực thay vì chỉ nhìn một `<scope>` riêng lẻ trong POM.
