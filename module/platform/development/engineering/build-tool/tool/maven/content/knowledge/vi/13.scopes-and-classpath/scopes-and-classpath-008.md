# Đọc bảng lan truyền scope qua phụ thuộc bắc cầu trong Maven

## 1. Phân biệt scope khai báo với scope nhận được trong dự án tiêu thụ

Trong một ứng dụng Java, Maven giải quyết không chỉ những dependency được khai báo trực tiếp mà còn những dependency do các thư viện đó khai báo. Những thư viện phía sau gọi là **transitive dependencies** (phụ thuộc bắc cầu). Scope của chúng khi được nhìn từ ứng dụng **có thể khác** scope gốc trong POM của thư viện trung gian.

Xét sơ đồ:

```text
Dự án P  --(scope A)-->  thư viện A  --(scope B)-->  thư viện B
                        trực tiếp                  bắc cầu đối với P
```

Ở đây, P khai báo dependency vào A. Chính POM của A khai báo dependency vào B. Chúng ta cần trả lời câu hỏi: **Khi Maven xây classpath cho P, B có scope gì?**

Đáp án không chỉ dựa vào dòng `<scope>` trong POM của B hoặc của A. Ta phải kết hợp:

1. Scope của cạnh **P → A** (dependency A nhìn từ project P).
2. Scope của cạnh **A → B** (dependency B được khai báo trong POM của A).
3. Bảng lan truyền scope do Maven quy định.

Nếu B bị loại qua nhánh P → A → B, B vẫn có thể được khai báo trực tiếp trong P hoặc đến qua một đường khác. Vì vậy, **một cạnh bị loại không có nghĩa B biến mất khỏi toàn bộ graph**.

## 2. Bảng lan truyền scope 4×4 chuẩn của Maven

Tài liệu chính thức **Apache Maven — Introduction to the Dependency Mechanism** cung cấp bảng sau. Hàng bên trái là scope của **dependency trực tiếp A tại P**; cột phía trên là scope của **dependency B tại A**; ô giao nhau là **scope của B tại P**.

| Scope P → A ↓ / Scope A → B → | **compile** | **provided** | **runtime** | **test** |
| --- | --- | --- | --- | --- |
| **compile** | **compile** | **—** | **runtime** | **—** |
| **provided** | **provided** | **—** | **provided** | **—** |
| **runtime** | **runtime** | **—** | **runtime** | **—** |
| **test** | **test** | **—** | **test** | **—** |

Ý nghĩa của dấu **`—`**: Maven **không đưa B vào P qua nhánh A này**. Đây không phải scope thứ năm; không phải scope `provided`, cũng không phải một lệnh exclusion áp dụng toàn cục.

Đọc đủ tám ô có kết quả:

- `A=compile`, `B=compile` → **B=compile** tại P.
- `A=compile`, `B=runtime` → **B=runtime** tại P.
- `A=provided`, `B=compile` → **B=provided** tại P.
- `A=provided`, `B=runtime` → **B=provided** tại P.
- `A=runtime`, `B=compile` → **B=runtime** tại P.
- `A=runtime`, `B=runtime` → **B=runtime** tại P.
- `A=test`, `B=compile` → **B=test** tại P.
- `A=test`, `B=runtime` → **B=test** tại P.

**Hai cột B=provided và B=test chỉ gồm dấu gạch ngang.** Nếu A khai báo B bằng `provided` hoặc `test`, B không được truyền vào P qua cạnh ấy theo bảng này.

### 2.1. Thứ tự hàng và cột không thể đổi chỗ

Đôi khi người mới học thấy hai scope trên đường và cố gắng tự tính “scope hạn chế hơn sẽ thắng”. Cách đó sai. Hãy so:

```text
P --provided--> A --compile--> B    → B là provided trong P
P --compile-->  A --provided--> B   → B bị loại qua A
```

Hoặc:

```text
P --test-->    A --compile--> B     → B là test trong P
P --compile--> A --test-->    B     → B bị loại qua A
```

Scope **gắn với cạnh có hướng**. Khi đảo hai scope, ta đã đổi câu hỏi nên có thể nhận kết quả khác.

### 2.2. Ví dụ thường gặp nhất

```text
P (compile) → A (runtime dependency B) → B
```

Điền hàng `compile` và cột `runtime` nhận `runtime`. Nghĩa là B **không cần ở compile classpath chính** của P, nhưng được đưa vào runtime/test classpath của P.

Ngược lại:

```text
P (test) → A (compile dependency B) → B
```

Điền hàng `test` và cột `compile` nhận `test`. B cần để **test của P hoạt động**, nhưng không phải dependency compile/runtime sản phẩm của P.

## 3. Hai bảng phải đọc theo thứ tự: scope propagation rồi classpath

Bảng ở phần 2 cho biết **scope hiệu lực của B**. Sau khi có scope đó, dùng bảng classpath để biết nó xuất hiện vào giai đoạn nào.

| Scope hiệu lực tại P | Compile classpath chính | Runtime classpath chính | Test classpath |
| --- | --- | --- | --- |
| `compile` | Có | Có | Có |
| `provided` | Có | Không | Có |
| `runtime` | Không | Có | Có |
| `test` | Không | Không | Có |

Ví dụ:

- Tra bảng propagation được B=`compile` → B dùng trong compile, runtime và test.
- Tra được B=`provided` → B có ở compile và test, nhưng Maven không đưa B vào runtime classpath chính.
- Tra được B=`runtime` → B chỉ vào runtime/test, không vào compile classpath chính.
- Tra được B=`test` → B phục vụ test compile/test execution, không xuất hiện trong compile/runtime sản phẩm.
- Tra được dấu `—` → B không được kéo vào qua đường A, nên không thể suy ra B có mặt ở classpath nào từ đường đó.

**Không nhầm compile classpath với test-compile classpath:** test-compile thường nhìn thấy cả dependency dùng cho test, còn compile của mã trong `src/main/java` chỉ cần những dependency phù hợp cho sản phẩm.

### 3.1. Scope của dependency trực tiếp khác scope sau lan truyền

Nếu P khai báo trực tiếp dependency `<scope>test</scope>`, chính dependency trực tiếp đó là `test` tại P. Nhưng nếu B được A khai báo `compile`, trong P **B trở thành test** qua quan hệ P→A→B khi A được P khai báo ở `test`.

Vì vậy, dòng `org.apache.commons:commons-lang3:jar:3.14.0:test` trong `dependency:tree` của P **không có nghĩa Commons Lang được A khai báo ở test scope**. Cần nhìn đúng POM trung gian.

## 4. Hiểu sâu từng hàng trong bảng

### 4.1. Hàng A = compile

Project P cần A để biên dịch và chạy. Nếu A khai báo B là compile, B được lan truyền thành compile. Ví dụ B là kiểu dữ liệu mà API công khai của A sử dụng, nên P có thể cần B để biên dịch khi sử dụng A.

Nếu A khai báo B ở runtime, P nhận B ở runtime: B phục vụ thực thi các tính năng của A mà P không phải compile trực tiếp theo B.

Nếu A khai báo B ở provided hoặc test, **P không nhận B qua cạnh A**. Chẳng hạn API Servlet được container cung cấp hoặc JUnit dùng để test chính A không mặc nhiên trở thành dependency của mọi project tiêu thụ A.

```text
A=compile; B=compile   → compile
A=compile; B=provided  → —
A=compile; B=runtime   → runtime
A=compile; B=test      → —
```

### 4.2. Hàng A = provided

P biên dịch với A nhưng dự kiến JDK/container sẽ cung cấp A lúc chạy. Theo bảng, dependency compile hoặc runtime của A sẽ mang scope provided tại P:

```text
A=provided; B=compile   → provided
A=provided; B=provided  → —
A=provided; B=runtime   → provided
A=provided; B=test      → —
```

Đây là điểm dễ nhầm: tài liệu Maven gọi scope `provided` là **không transitive** khi project bị một project khác tiêu thụ. Nhưng câu đó **không đồng nghĩa cả hàng A=provided là dấu gạch ngang**. Từ góc nhìn của project hiện tại P, B ở compile/runtime phía sau A vẫn có thể được nhận là `provided`.

Điều này chỉ hợp lý khi runtime/container thật sự cung cấp các lớp cần thiết. Đừng gắn provided chỉ để giảm kích thước artifact mà không có cơ chế cấp dependency lúc chạy.

### 4.3. Hàng A = runtime

P chỉ cần A khi thực thi, không dùng API của A trực tiếp để compile mã sản phẩm. Các dependency compile và runtime do A khai báo đều chuyển thành runtime trong P.

```text
A=runtime; B=compile   → runtime
A=runtime; B=provided  → —
A=runtime; B=runtime   → runtime
A=runtime; B=test      → —
```

Ví dụ gần gũi là JDBC driver: ứng dụng có thể compile theo API `java.sql` của JDK, còn thư viện driver thực chỉ được cần ở runtime. Nếu mã sản phẩm lại import trực tiếp một class chỉ có runtime scope, compile có thể lỗi vì class không nằm trong compile classpath.

### 4.4. Hàng A = test

P chỉ cần A trong unit/integration test. Để A chạy được trong test, B nếu là dependency compile/runtime của A thì được đưa vào P với scope test.

```text
A=test; B=compile   → test
A=test; B=provided  → —
A=test; B=runtime   → test
A=test; B=test      → —
```

Đó là lý do một bộ test helper có thể kéo theo thư viện mình cần nhưng thư viện ấy không tự động thành runtime dependency của sản phẩm P.

**Không suy ra** tất cả dependency của A đều bị loại chỉ vì A có scope test. B compile và runtime vẫn được lan truyền ở scope test.

## 5. Bảng tình huống có đáp án và ý nghĩa

Hãy coi P là project đang xét và đường duy nhất đang phân tích là P→A→B.

| Trường hợp | Scope P→A | Scope A→B | Kết quả B ở P | Hệ quả classpath |
| --- | --- | --- | --- | --- |
| API thư viện phụ thuộc API khác | `compile` | `compile` | `compile` | Compile, runtime, test |
| API thư viện cần driver lúc chạy | `compile` | `runtime` | `runtime` | Runtime, test |
| Thư viện A cần servlet API từ container | `compile` | `provided` | `—` | Không lan qua A |
| P chỉ compile với A do container cung cấp | `provided` | `compile` | `provided` | Compile, test |
| P cần A ở provided, A cần B khi chạy | `provided` | `runtime` | `provided` | Compile, test |
| P chỉ cần A lúc chạy | `runtime` | `compile` | `runtime` | Runtime, test |
| P dùng test helper A, A dùng B để compile | `test` | `compile` | `test` | Test |
| P dùng test helper A, A cần B lúc chạy | `test` | `runtime` | `test` | Test |
| A test với JUnit nhưng P dùng A để compile | `compile` | `test` | `—` | Không kéo JUnit qua A |

Điểm đặc biệt là bảng này trả lời **sự lan truyền một dependency trên một nhánh**. Nếu B còn được khai báo trực tiếp ở P, hoặc xuất hiện qua A2, Maven sẽ xem cả graph và áp dụng thêm các quy tắc dependency resolution.

## 6. Ví dụ Maven Java 17 chạy được: test helper kéo theo Commons Lang

Bài thực hành này cố tình chọn nhánh **A=test, B=compile → B=test** để thấy sự lan truyền scope.

Ta tạo ba Maven project trong một Reactor:

- Root `scope-lab` có `packaging=pom`, chia sẻ phiên bản dependency/plugin và liệt kê modules.
- Module `helper` dùng Apache Commons Lang để xử lý tên, khai báo Commons Lang ở **compile scope**.
- Module `app` có mã sản phẩm không dùng helper, nhưng **test của app** dùng helper. Vì vậy app khai báo `helper` ở **test scope**; Commons Lang từ helper cũng trở thành **test scope đối với app**.

Các bản cụ thể trong ví dụ: Java 17, Commons Lang 3.14.0, JUnit Jupiter 5.10.2, Maven Compiler Plugin 3.13.0 và Maven Surefire Plugin 3.2.5. Đây là mốc ví dụ có tài liệu, **không phải tuyên bố phiên bản mới nhất**.

### 6.1. Cây thư mục

```text
scope-lab/
├── pom.xml
├── helper/
│   ├── pom.xml
│   └── src/main/java/demo/helper/Greeter.java
└── app/
    ├── pom.xml
    ├── src/main/java/demo/app/Main.java
    └── src/test/java/demo/app/GreeterTest.java
```

### 6.2. Root pom.xml: POM cha kiêm aggregator

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>scope-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>helper</module>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
                    <version>3.2.5</version>
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
```

Root có hai vai trò khác nhau: `<modules>` tập hợp project cho Maven Reactor, `<parent>` trong POM con cho phép kế thừa `dependencyManagement` và `pluginManagement`. Chúng **không tự thêm dependency giữa helper và app**.

### 6.3. helper/pom.xml và lớp Greeter

Tệp `scope-lab/helper/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>demo</groupId>
        <artifactId>scope-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>helper</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
    </dependencies>
</project>
```

Commons Lang không khai báo `<scope>` nên mặc định **compile** trong module helper; version được quản lý ở POM cha.

Tệp `scope-lab/helper/src/main/java/demo/helper/Greeter.java`:

```java
package demo.helper;

import org.apache.commons.lang3.StringUtils;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String input) {
        if (StringUtils.isBlank(input)) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        String cleaned = input.trim();
        return "Hello, " + StringUtils.capitalize(cleaned) + "!";
    }
}
```

Greeter thật sự import `StringUtils` từ Commons Lang. Vì vậy helper **cần** Commons Lang ở compile scope, không chỉ runtime.

### 6.4. app/pom.xml: helper có test scope

Tệp `scope-lab/app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>demo</groupId>
        <artifactId>scope-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>demo</groupId>
            <artifactId>helper</artifactId>
            <version>${project.version}</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Hướng scope trong ví dụ:

```text
app --(test)--> helper --(compile)--> commons-lang3

Hàng A=test, cột B=compile của bảng: B=test
=> commons-lang3 có scope test từ góc nhìn app
```

JUnit Jupiter trực tiếp mang scope test tại app và version được quản lý trong parent. Không phải app tự khai báo Commons Lang; Commons Lang được đưa đến qua helper.

### 6.5. Main.java không phụ thuộc test helper

Tệp `scope-lab/app/src/main/java/demo/app/Main.java`:

```java
package demo.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Main uses no test helper.");
    }
}
```

Mã sản phẩm chỉ dùng JDK. Đây là thiết kế đúng khi helper chỉ dùng để kiểm thử. Nếu Main import `Greeter`, scope `test` của helper **không** đưa helper vào compile classpath chính của app, nên compile mã sản phẩm sẽ không còn hợp lệ.

### 6.6. GreeterTest.java dùng helper và Commons Lang gián tiếp

Tệp `scope-lab/app/src/test/java/demo/app/GreeterTest.java`:

```java
package demo.app;

import demo.helper.Greeter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreeterTest {
    @Test
    void formatsName() {
        assertEquals("Hello, Maven!", Greeter.greet(" maven "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                     () -> Greeter.greet("   "));
    }
}
```

`GreeterTest` gọi helper; trong helper, `StringUtils` của Commons Lang xử lý đầu vào. Để test chạy, cần đủ `helper:test` và `commons-lang3:test` trên test classpath của app.

### 6.7. Build và đọc dependency tree

Từ thư mục `scope-lab/`, với JDK 17 và Maven đủ khả năng tải plugin/dependency:

```bash
mvn -B clean verify
```

Maven Reactor nhận hai module, build helper trước app theo dependency thực. Surefire của app thực thi **2 unit test**, kỳ vọng 0 failure và 0 error khi các tệp được tạo đúng.

Xem scope Maven thực tế gán cho graph của app:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Sơ đồ rút gọn của **phần app trong dependency tree**:

```text
demo:app:jar:1.0.0
+- demo:helper:jar:1.0.0:test
|  \- org.apache.commons:commons-lang3:jar:3.14.0:test
\- org.junit.jupiter:junit-jupiter:jar:5.10.2:test
   \- ... các artifact JUnit bắc cầu ...
```

Đây là sơ đồ ý nghĩa, **không phải stdout Maven nguyên văn**. Plugin có thể in thêm module và các dependency khác. Dòng `commons-lang3:...:test` là kết quả lan truyền scope qua helper.

Chạy Main sau build:

```bash
java -cp app/target/classes demo.app.Main
```

Stdout **của lệnh `java`** là:

```text
Main uses no test helper.
```

Đây là ví dụ cố ý: Main không dùng helper, nên không cần cung cấp Commons Lang vào runtime classpath của Main. Điều này **không** chứng minh mọi ứng dụng đều có thể chạy chỉ với `target/classes`; nếu Main thực sự dùng dependency runtime, phải cung cấp JAR tương ứng bằng launcher/đóng gói phù hợp.

### 6.8. Đổi một ô để quan sát kết quả khác

Trong `app/pom.xml`, chỉ đổi `<scope>test</scope>` của dependency **`demo:helper`** thành `<scope>compile</scope>`. **Không đổi JUnit**, vẫn ở test scope.

Lúc này:

```text
app --(compile)--> helper --(compile)--> commons-lang3

Hàng A=compile, cột B=compile => B=compile
```

Sau `mvn -B clean verify`, dòng tương ứng trong `dependency:tree` của app sẽ có ý nghĩa:

```text
demo:helper:jar:1.0.0:compile
org.apache.commons:commons-lang3:jar:3.14.0:compile
```

Đây là mô tả hai dòng được chọn, không phải toàn bộ output nguyên văn. Bởi `Main` vẫn không import helper, stdout của Main vẫn như cũ; nhưng **compile/runtime classpaths của app đã rộng hơn**. Điều cần quan sát là Maven dependency tree, không chỉ kết quả in ra màn hình.

Một thí nghiệm bổ sung: nếu cập nhật Main để gọi `Greeter.greet("maven")`, app với `helper:test` sẽ không compile mã chính; với `helper:compile`, compiler có thể dùng helper và Commons Lang trên compile classpath. Cần cấu hình runtime classpath đúng nếu muốn chạy Main có sử dụng helper.

## 7. Khi nào áp dụng bảng là chưa đủ?

Bảng 4×4 giải thích propagation **trên một nhánh**, nhưng dependency graph Maven còn có các cơ chế khác.

### 7.1. dependencyManagement

`dependencyManagement` cho phép quản lý version, scope và một số thông tin dependency hiệu lực theo quy tắc Maven. Ví dụ parent quản lý Commons Lang:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là đoạn POM chứ không phải file đầy đủ. Nó **không tự tạo dependency** nếu không có đường direct/transitive liên quan. Khi có management thay đổi thông tin scope/version của dependency, cần nhìn effective graph thay vì áp bảng lên dữ liệu trước khi Maven giải quyết.

Cách thiết kế bền vững: **module nào import trực tiếp API của thư viện nào thì nên khai báo dependency trực tiếp vào thư viện đó** với scope phù hợp, không dựa vào một đường bắc cầu tình cờ.

### 7.2. optional

Dependency `optional=true` được dùng khi thư viện A cần B cho tính năng tùy chọn nhưng không muốn B tự động lan tới project tiêu thụ A.

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>optional-extension</artifactId>
    <version>1.0.0</version>
    <optional>true</optional>
</dependency>
```

Tọa độ `com.example` chỉ là ví dụ khái niệm. Nếu P sử dụng tính năng cần B, P phải khai báo B trực tiếp. Bảng propagation không khiến optional dependency tự lan truyền.

### 7.3. exclusions

`<exclusions>` chặn dependency bắc cầu qua một cạnh cụ thể:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>sdk</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>old-library</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Các tọa độ ở đoạn này là minh họa, không phải artifact của ví dụ Java phần 6. Nếu `old-library` còn được kéo từ một đường khác, nó vẫn có thể xuất hiện. Dấu `—` trong bảng cũng chỉ nói một nhánh, tương tự **không phải lệnh cấm artifact trên toàn graph**.

### 7.4. Version conflict và mediation

Một artifact có thể xuất hiện qua nhiều đường với version khác nhau:

```text
app
├── library-a:1.0 --> common-api:1.2
└── library-c:2.0 --> common-api:2.0
```

Trong Maven 3, quy tắc phổ biến là **nearest definition**: đường gần hơn thường thắng; nếu bằng độ sâu, thứ tự khai báo có thể ảnh hưởng. Version management và dependency trực tiếp cũng có thể thay đổi lựa chọn. Bảng scope không thay thế cơ chế chọn version và thu gọn graph.

Một số lỗi như `NoSuchMethodError` xuất phát từ version runtime được chọn chứ không phải nhầm scope. Cần nhìn cả dependency tree và classpath thực tế.

### 7.5. system và import không nằm trong bảng 4×4

Maven còn có scope `system` và `import`, nhưng không được tự thêm chúng vào bảng bằng suy luận:

- `system` dùng JAR tại `systemPath` cục bộ, Maven không phân giải qua repository như dependency thông thường; dễ làm local/CI khác nhau và nên tránh nếu có thể.
- `import` chỉ hợp lệ cho dependency kiểu `pom` ở `dependencyManagement` để nhập BOM. Đây không phải dependency runtime/compile/test.

Một BOM không tự đưa tất cả thư viện được quản lý lên classpath. Đừng coi `import` là một ô scope mới.

## 8. Classpath, Reactor và đóng gói: tránh kết luận sai từ bảng

Trong dự án nhiều module, Maven Reactor quyết định **thứ tự xây các project có dependency thực**. `<modules>` ở root không tự tạo dependency giữa app và helper. Một module dùng helper phải khai báo dependency vào tọa độ của helper trong POM, đúng `groupId:artifactId:version` và scope.

Lệnh:

```bash
mvn -pl :app -am verify
```

chọn app và các module liên quan cần được build trong Reactor. Nếu chỉ dùng `-pl :app` từ môi trường sạch mà thiếu artifact helper trong repository, Maven có thể không giải quyết được helper. Sự cố này thuộc **tập project trong Reactor/artifact availability**, khác hoàn toàn với câu hỏi **scope bắc cầu**.

**Dependency tree không đồng nghĩa nội dung JAR.** Khi packaging mặc định là `jar`, project JAR không tự gom mọi dependency JAR vào trong. Mặc dù scope `compile` và `runtime` xác định dependency cần khi chạy, launcher ứng dụng vẫn phải được cung cấp JAR đúng cách: classpath, distribution, plugin đóng gói, container image hoặc runtime của framework.

Ngược lại, `mvn test` dùng test classpath có thể chạy thành công, trong khi `java -cp target/classes ...` thiếu dependency runtime và thất bại. Đây chưa chắc do bảng scope sai; có thể do cách khởi động Java ngoài Maven không đưa dependency vào classpath.

## 9. Lệnh Maven để kiểm tra scope đã được tính

Tại một project đang có POM, dùng Maven Dependency Plugin:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Trong Reactor có nhiều module, xác định chính xác phần cây của project muốn xét. Lệnh:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

có thể chạy goal với các project được chọn và các project cần xây cùng. Đừng nhầm scope trong cây của module helper với scope của artifact đó trong **cây app**.

Một dòng output có dạng:

```text
+- org.apache.commons:commons-lang3:jar:3.14.0:test
```

Phần cuối `test` mô tả scope được Maven chọn **cho project đang hiển thị**. Để biết scope khai báo gốc, mở POM của project trực tiếp chứa dependency đó, hoặc xem effective POM khi inheritance/management làm thay đổi dữ liệu ban đầu.

Khi cần kiểm tra cấu hình đã kế thừa và quản lý dependency:

```bash
mvn help:effective-pom
```

Khi cần kiểm tra compiler/test thực sự có dependency nào, đối chiếu `dependency:tree`, các goal/phase Maven sử dụng, Surefire reports và cách chương trình được chạy. Cấu hình IDE có thể che thiếu dependency trong POM; CI sạch là phép thử tái lập tốt.

## 10. Các hiểu lầm phổ biến và cách xử lý

| Hiểu lầm | Thực tế | Hành động phù hợp |
| --- | --- | --- |
| “Scope của B trong A luôn được giữ ở P.” | Scope có thể đổi qua bảng lan truyền. | Tra hàng P→A và cột A→B. |
| “A=test làm tất cả dependency của A bị bỏ.” | B compile/runtime qua A=test trở thành test. | Đọc đúng hàng test. |
| “A=provided làm tất cả B bị bỏ.” | B compile/runtime qua A=provided thành provided. | Đọc đúng hàng provided. |
| “A=compile, B=provided tạo B=provided.” | Cột provided cho dấu `—`. | Kết luận B bị loại qua A. |
| “A=runtime, B=compile tạo B=compile.” | B trở thành runtime. | Kiểm tra runtime/test classpath. |
| “B=test ở P chứng minh B là test ở A.” | B có thể là compile ở A nhưng được chuyển thành test ở P. | Xem POM A và tree P. |
| “Một nhánh có dấu — thì B không tồn tại trong P.” | B có thể có nhánh khác hoặc direct declaration. | Kiểm tra toàn graph. |
| “Đã có version trong dependencyManagement tức B được thêm.” | Management không tạo dependency. | Kiểm tra `dependencies` thực tế. |
| “Maven có import scope trên classpath.” | import chỉ dùng BOM trong management. | Đừng dùng import như dependency JAR. |
| “Chạy test được thì sản phẩm chắc có đủ JAR runtime.” | Test classpath có thể rộng hơn runtime app. | Kiểm tra cách đóng gói/chạy thực tế. |

Lỗi Java thường cần phân biệt:

- `package ... does not exist` trong compile: class chỉ có ở test/runtime scope hoặc dependency chưa được khai báo cho module nguồn.
- `ClassNotFoundException` / `NoClassDefFoundError` khi chạy: có thể thiếu JAR trên classpath runtime, do optional/exclusions/scope hoặc launcher không cấp thư viện.
- `NoSuchMethodError` sau nâng version: thường cần kiểm tra version mediation và binary compatibility.
- Test chỉ fail trên CI: ngoài scope, còn xem profile, Surefire, JDK, mạng và điều kiện môi trường test.

Không giải quyết những lỗi này bằng việc copy JAR thủ công vào source tree hoặc chỉ thêm thư viện trong cấu hình IDE, vì điều đó làm Maven build thiếu khả năng tái lập.

## 11. Quy trình 5 bước để đọc bảng đúng trong bài tập và dự án thật

1. **Xác định P, A, B:** P là project cần tính scope; A là dependency trực tiếp; B là dependency do A khai báo.
2. **Tìm scope của P→A:** lấy từ dependency của P, nếu vắng `<scope>` mặc định là compile trừ khi management thay đổi thông tin hiệu lực.
3. **Tìm scope của A→B:** lấy từ dependency của A, có xét các quy tắc quản lý POM hiệu lực.
4. **Tra hàng/cột trong bảng 4×4:** nếu nhận `compile`, `provided`, `runtime` hoặc `test`, tiếp tục suy ra classpath; nếu `—`, B chỉ bị loại qua nhánh đó.
5. **Kiểm chứng Maven thực tế:** đọc `dependency:tree` của đúng project, kiểm tra optional/exclusions/management/conflict và chạy build hoặc test tương ứng.

Thử tự giải:

```text
P --provided--> A --runtime--> B
Hàng provided, cột runtime => B=provided trong P
B có ở compile/test classpath P, không ở runtime classpath chính
```

```text
P --compile--> A --test--> B
Hàng compile, cột test => B bị loại qua nhánh A
Nếu P cần B trực tiếp, P phải khai báo dependency đúng scope
```

**Kết luận:** bảng transitive dependency scope không hỏi “một artifact có scope tuyệt đối là gì”, mà hỏi **“scope của B khi nó đi đến project P theo đường P→A→B là gì?”**. Bài tập đúng là bài tập gắn scope với **từng cạnh có hướng** và kiểm tra kết quả từ project đang xét.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism, bảng scope bắc cầu](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven Dependency Plugin 3.6.1 — dependency:tree](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.6.1/tree-mojo.html)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
