# Maven: Đăng ký nguồn bổ sung bằng plugin phù hợp

> **Build Tool Maven · Tài nguyên và sinh mã**  
> Trọng tâm: thêm các **source roots** ngoài `src/main/java` và `src/test/java` bằng **MojoHaus Build Helper Maven Plugin**, phân biệt nguồn Java với resources và bảo đảm mã sinh ra được biên dịch đúng phase.

## 1. Vấn đề thực tế: có file Java nhưng Maven không biên dịch

Một project Maven Java chuẩn thường đặt:

```text
src/main/java/       mã Java của ứng dụng
src/main/resources/  tài nguyên dùng khi chạy
src/test/java/       mã Java kiểm thử
src/test/resources/  tài nguyên kiểm thử
```

Đây là **quy ước mặc định**, không phải toàn bộ những vị trí Maven có thể biên dịch. Đôi khi project có thêm:

- Mã Java dùng chung nằm trong `src/additional/java`.
- Mã Java sinh từ schema, API specification hoặc model nằm ở `target/generated-sources/...`.
- Mã kiểm thử hỗ trợ riêng ở `src/additional-test/java`.
- Source code được tạo bởi công cụ khác trong phase `generate-sources` hoặc `generate-test-sources`.

Nếu những thư mục đó có `.java` nhưng **không được đăng ký là compile source root/test compile source root**, Maven Compiler Plugin có thể **không đọc chúng**. Kết quả thường là `package ... does not exist`, `cannot find symbol`, hoặc **build thành công nhưng class/test phụ trợ không hề được biên dịch**.

Giải pháp trong Maven 3.x là **đăng ký các thư mục đúng loại vào mô hình build**, không phải copy bừa Java source vào `src/main/java` hoặc thay hẳn `<sourceDirectory>` một cách nguy hiểm.

**Plugin tiêu biểu:** `org.codehaus.mojo:build-helper-maven-plugin`, với:

- `build-helper:add-source`: bổ sung source roots cho **mã chính**.
- `build-helper:add-test-source`: bổ sung source roots cho **mã test**.
- `build-helper:add-resource`: bổ sung các thư mục **resources** của mã chính.
- `build-helper:add-test-resource`: bổ sung **test resources**.

Bài sử dụng **Build Helper Maven Plugin 3.6.2**, **Maven Compiler Plugin 3.14.1**, **Maven 3.x** và **JDK 17+**. Các phần sau sẽ chỉ rõ sự khác nhau giữa **đăng ký thư mục** và **thực sự sinh file**, cũng như cách đặt phase để không rơi vào tình huống compiler chạy quá sớm.

### Mục tiêu sau bài

1. Hiểu compile source root/test source root và vì sao Java files ở một thư mục bất kỳ không tự được Maven biên dịch.
2. Chọn đúng `add-source`, `add-test-source`, `add-resource` hoặc `add-test-resource`.
3. Viết POM đầy đủ để thêm nhiều thư mục Java mà **không làm mất các roots mặc định**.
4. Biên dịch và chạy project Java 17 có một main class trong root mặc định và một helper class ở thư mục nguồn bổ sung.
5. Thêm một thư mục test source bổ sung, xác minh `.class` được sinh ra, rồi chạy một smoke check.
6. Liên kết code generation với lifecycle `generate-sources` → `compile` và tránh khai báo trùng roots mà code generator đã tự đăng ký.
7. Chẩn đoán trường hợp đường dẫn sai, binding sai phase, module sai, compile không cập nhật hoặc IDE không nhận thư mục.

## 2. Source root thực sự là gì?

Một **source root** là đường dẫn thư mục mà công cụ build coi là gốc của cây package Java.

Ví dụ:

```text
src/additional/java/
└── com/
    └── example/
        └── shared/
            └── Greeter.java
```

Khi source root là `src/additional/java`, class:

```java
package com.example.shared;
```

nằm đúng đường dẫn tương đối:

```text
com/example/shared/Greeter.java
```

Tương tự, `src/main/java` là source root mặc định; vì vậy file:

```text
src/main/java/com/example/app/Main.java
```

có package `com.example.app`.

**Điều cần đăng ký là thư mục `src/additional/java`, không phải file `Greeter.java`, cũng không phải thư mục `com/example/shared` bên trong nó.** Nếu trỏ vào mức thư mục sai, compiler có thể không thấy lớp hoặc xử lý source package không đúng.

Trong Maven, các compile roots thường được biểu diễn qua `project.compileSourceRoots`; các test roots qua `project.testCompileSourceRoots`. Maven Compiler Plugin sử dụng source roots để biết **nguồn nào phải biên dịch**. Tài liệu Compiler Plugin mô tả tham số `compileSourceRoots` mặc định xuất phát từ `${project.compileSourceRoots}`.

### 2.1. Source root không phải classpath dependency

Đăng ký `src/additional/java` khiến các file `.java` trong thư mục được compiler đưa vào **cùng module**. Nó **không**:

- Tạo một artifact Maven mới với `groupId:artifactId:version` riêng.
- Tự thêm dependency từ module khác.
- Tự giải quyết JAR thiếu trên classpath.
- Tự xuất bản các file source thành source JAR.
- Tự thay đổi runtime version hoặc Java target.

Nếu bạn muốn dùng class nằm ở **module Maven khác**, cách phù hợp thường là khai báo `<dependency>` tới module đó; **không** đăng ký thư mục source của module bên cạnh làm root của module hiện tại. Thêm source xuyên module dễ tạo biên giới kiến trúc và đường build khó bảo trì.

### 2.2. Source root không phải resource root

| Đầu vào | Ví dụ | Đích điển hình | Cách khai báo phù hợp |
| --- | --- | --- | --- |
| Java source chính | `Greeter.java` | `target/classes/*.class` theo package | `build-helper:add-source` |
| Java source test | `SourceRootCheck.java` | `target/test-classes/*.class` | `build-helper:add-test-source` |
| Resource chính | `messages.properties` | Được copy vào `target/classes` | `<resources>` hoặc `build-helper:add-resource` |
| Test resource | `test-data.json` | Được copy vào `target/test-classes` | `<testResources>` hoặc `build-helper:add-test-resource` |
| Java generated source | `target/generated-sources/api/.../*.java` | Sau biên dịch thành class chính | Generator + source-root registration **nếu cần** |
| Test generated source | `target/generated-test-sources/.../*.java` | Sau testCompile thành test classes | Generator + test-source registration **nếu cần** |
| Artifact JAR khác | `shared-lib-1.0.jar` | Classpath qua dependency resolution | `<dependencies>` |

Không sử dụng `add-resource` để “biên dịch” `.java`. Goal resource chỉ làm Maven nhận thêm **thư mục cần copy/filter**, chứ không biến nó thành compile source root.

## 3. Plugin phù hợp: build-helper-maven-plugin

Tài liệu chính thức MojoHaus mô tả các goal trong plugin:

| Goal | Mục đích | Phase mặc định khi có execution |
| --- | --- | --- |
| `build-helper:add-source` | Thêm source directories cho main | `generate-sources` |
| `build-helper:add-test-source` | Thêm source directories cho test | `generate-test-sources` |
| `build-helper:add-resource` | Thêm resources của main | `generate-resources` |
| `build-helper:add-test-resource` | Thêm resources của test | `generate-test-resources` |

Các goal là **thao tác bổ sung model của build**, không phải code generator. Plugin không biết cần sinh class Java nào nếu bạn chỉ cấu hình `<sources>`.

Theo trang goal chính thức của bản **3.6.2**:

- `add-source` yêu cầu phần cấu hình `<sources>` chứa các phần tử `<source>`.
- `add-test-source` cũng dùng `<sources>`.
- Cả hai goal hỗ trợ parallel build và được đánh dấu thread-safe.
- Có tham số `skipAddSourceIfMissing`/`skipAddTestSourceIfMissing`, mặc định `false`: có thể bỏ qua **việc đăng ký** một thư mục nếu nó chưa tồn tại khi phase chạy. Không nên bật tính năng bỏ qua cho source root **bắt buộc** mà generator lẽ ra phải tạo.

### 3.1. Cấu hình add-source tối thiểu

**Fragment** này nằm trong `<build><plugins>` của POM:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.2</version>

    <executions>
        <execution>
            <id>register-main-source-roots</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>add-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>${project.basedir}/src/additional/java</source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Giải thích:

1. `<phase>generate-sources</phase>` chạy **trước** `compile`.
2. `<goal>add-source</goal>` thêm thư mục vào danh sách compile roots.
3. `${project.basedir}` là thư mục chứa POM **của module đang xử lý**, không phải thư mục cố định trên laptop.
4. `<sources>` có thể chứa **nhiều** `<source>` entries.
5. Execution `<id>` giúp phân biệt với những executions khác; tên ID là quy ước của dự án, không phải một goal.

Trong project bình thường, **không bắt buộc thêm lại** `src/main/java` vào `<sources>`: Maven đã có root mặc định. Plugin bổ sung roots, không nhất thiết thay thế chúng.

### 3.2. Thêm test sources

**Fragment** của một execution khác trong **cùng plugin**:

```xml
<execution>
    <id>register-test-source-roots</id>
    <phase>generate-test-sources</phase>
    <goals>
        <goal>add-test-source</goal>
    </goals>
    <configuration>
        <sources>
            <source>${project.basedir}/src/additional-test/java</source>
        </sources>
    </configuration>
</execution>
```

Mã trong `src/additional-test/java` sẽ thuộc **test compile roots**, không phải main compile roots. Điều này có hệ quả rõ ràng:

- Có thể sử dụng class của ứng dụng ở main output và dependencies với scope test thích hợp.
- Output đi vào `target/test-classes`.
- Test classes không được đóng vào main JAR theo packaging JAR tiêu chuẩn.
- Maven Surefire/JUnit **không mặc nhiên chạy mọi class** trong test source root; vẫn cần test framework/discovery convention.

Đây là điểm quan trọng: **đăng ký và biên dịch test source không đồng nghĩa đã thực thi test**.

### 3.3. Có thể thêm nhiều nguồn vào một execution

```xml
<sources>
    <source>${project.basedir}/src/additional/java</source>
    <source>${project.build.directory}/generated-sources/custom-api</source>
    <source>${project.build.directory}/generated-sources/custom-model</source>
</sources>
```

Các thư mục trong `target/generated-sources` thích hợp với **file sinh tự động**, còn `src/additional/java` thích hợp với mã **được quản lý trong repository**. Không trỏ source root vào **toàn bộ thư mục `target/`**: trong đó còn có compiled classes, reports, temporary outputs và các nội dung không phải source.

Một thư mục lớn chứa nhiều ngôn ngữ, resource và mã không thuộc module có thể khiến compiler quét nhầm hoặc tạo dependency không mong muốn. Nên chọn roots **hẹp, rõ và ổn định**.

## 4. Ví dụ Java 17 hoàn chỉnh: thêm main và test source roots

Chúng ta tạo một project có:

- `Main.java` ở `src/main/java` **mặc định**.
- `Greeter.java` ở `src/additional/java` **chỉ được compiler nhìn thấy sau `add-source`**.
- `SourceRootCheck.java` ở `src/additional-test/java` **chỉ được test compiler nhìn thấy sau `add-test-source`**.

Không cần thư viện bên thứ ba cho code. Build Helper Maven Plugin và Compiler Plugin là **build plugins** Maven tải khi cần; code Java chỉ dùng JDK và các class của chính project.

### 4.1. Cấu trúc thư mục

```text
extra-source-roots-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/
    │           └── example/
    │               └── app/
    │                   └── Main.java
    ├── additional/
    │   └── java/
    │       └── com/
    │           └── example/
    │               └── shared/
    │                   └── Greeter.java
    └── additional-test/
        └── java/
            └── com/
                └── example/
                    └── check/
                        └── SourceRootCheck.java
```

Tên directory `additional`, `additional-test` **không phải Maven convention bắt buộc**; đây là lựa chọn để dễ nhìn ra vì sao cần đăng ký rõ ràng. Bạn có thể đổi tên nếu đồng thời cập nhật source paths trong POM.

### 4.2. Tệp pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>extra-source-roots-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.2</version>

                <executions>
                    <execution>
                        <id>register-main-source-roots</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>add-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>${project.basedir}/src/additional/java</source>
                            </sources>
                        </configuration>
                    </execution>

                    <execution>
                        <id>register-test-source-roots</id>
                        <phase>generate-test-sources</phase>
                        <goals>
                            <goal>add-test-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>${project.basedir}/src/additional-test/java</source>
                            </sources>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Đây là POM Maven hoàn chỉnh**, không phải fragment. Mỗi plugin có tọa độ và version xác định. Hai executions của Build Helper Plugin đăng ký hai kiểu roots ở **hai phases khác nhau**. Chúng không tự biên dịch; Maven Compiler Plugin dùng các roots đã được đăng ký khi phase compile/test-compile diễn ra.

**Tại sao Maven Compiler Plugin được khai báo trước Build Helper Plugin trong danh sách?** Vì chúng chạy ở **các phases khác nhau** trong ví dụ. `generate-sources` luôn đứng trước `compile`; `generate-test-sources` đứng trước `test-compile`. Thứ tự plugin declarations không làm compiler chạy trước một phase sớm hơn theo lifecycle này. Nếu nhiều executions cùng chạy trong **một phase**, thứ tự thực thi lại cần được xem xét riêng.

### 4.3. Tệp src/additional/java/com/example/shared/Greeter.java

```java
package com.example.shared;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Tệp có package đúng với `com/example/shared`, tính từ **root mới** là `src/additional/java`. Không có import ngoài JDK. Class được compiler tạo thành:

```text
target/classes/com/example/shared/Greeter.class
```

**Không phải** `target/additional/classes`, vì root bổ sung này vẫn là **source của cùng Maven module chính**.

### 4.4. Tệp src/main/java/com/example/app/Main.java

```java
package com.example.app;

import com.example.shared.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Maven"));
    }
}
```

Lớp `Main` nằm trong source root mặc định, nhưng nó import `Greeter` từ root bổ sung. Nếu bạn bỏ execution `add-source` khỏi POM và chạy **clean compile**, có thể gặp lỗi kiểu:

```text
package com.example.shared does not exist
cannot find symbol: variable Greeter
```

Dòng lỗi chỉ là **mẫu triệu chứng**, không phải nguyên văn toàn bộ `javac` log. Nguyên nhân là compiler chưa được thông báo về source root bổ sung; không phải nhất thiết do package của class sai.

### 4.5. Tệp src/additional-test/java/com/example/check/SourceRootCheck.java

```java
package com.example.check;

import com.example.shared.Greeter;

public final class SourceRootCheck {
    private SourceRootCheck() {
    }

    public static void main(String[] args) {
        String actual = Greeter.greet("Maven");
        if (!"Hello, Maven!".equals(actual)) {
            throw new AssertionError("Unexpected greeting: " + actual);
        }
        System.out.println("Test source root OK");
    }
}
```

Đây là một **smoke-check Java class có `main`**, **không phải JUnit test**. Mục đích là chứng minh thư mục source test bổ sung được **biên dịch** bằng `compiler:testCompile`, rồi có thể chạy riêng để kiểm tra. Maven Surefire có thể không tự discover và chạy class này vì nó không theo test framework/discovery convention.

Cấu trúc giúp kiểm tra hai việc độc lập:

- `Main` sử dụng `Greeter` từ compile root bổ sung.
- `SourceRootCheck` ở test compile root bổ sung cũng sử dụng `Greeter` từ main output.

### 4.6. Build từng bước

Từ thư mục `extra-source-roots-demo`:

```bash
java -version
javac -version
mvn -version
mvn clean test-compile
```

**Các phase quan trọng theo thứ tự:**

```text
generate-sources
    -> build-helper:add-source
compile
    -> compiler:compile
generate-test-sources
    -> build-helper:add-test-source
test-compile
    -> compiler:testCompile
```

Đây là sơ đồ rút gọn, **không liệt kê mọi phase** (`process-sources`, `process-resources`, `test`, v.v.). `clean` cũng là goal của lifecycle `clean` chạy trước phần default lifecycle. Mục tiêu là cho thấy registration xảy ra **trước compilation cần nó**.

Kiểm tra các file class đã tạo:

```text
target/classes/com/example/app/Main.class
target/classes/com/example/shared/Greeter.class
target/test-classes/com/example/check/SourceRootCheck.class
```

Những file này là bằng chứng trực tiếp: source ở ngoài hai roots mặc định đã được Maven compiler đưa vào quá trình biên dịch.

### 4.7. Chạy ứng dụng bằng Java CLI

Code main không có external dependency, nên có thể chạy trực tiếp:

```bash
java -cp target/classes com.example.app.Main
```

**Stdout chính xác:**

```text
Hello, Maven!
```

Đây là stdout từ `Main.main`; Maven log của bước trước không nằm trong khối output này.

### 4.8. Chạy smoke check từ test source root

Trên Linux/macOS:

```bash
java -cp "target/classes:target/test-classes" com.example.check.SourceRootCheck
```

Trên Windows PowerShell hoặc cmd:

```powershell
java -cp "target/classes;target/test-classes" com.example.check.SourceRootCheck
```

**Stdout chính xác cho cả hai nền tảng:**

```text
Test source root OK
```

Dấu phân cách classpath là `:` trên Unix và `;` trên Windows. Đây là khác biệt của **Java CLI**, không phải cú pháp danh sách `<sources>` trong POM.

Nếu Java code trong `SourceRootCheck` sai, chương trình sẽ ném `AssertionError`, không in dòng thành công. Nhưng vì kiểm tra này **không được Surefire tự chạy**, team phải dùng lệnh ở trên hoặc chuyển nó thành một bài test JUnit thật.

### 4.9. Đóng gói JAR

```bash
mvn clean package
jar tf target/extra-source-roots-demo-1.0.0.jar
```

**JAR chính** sẽ chứa classes ở `target/classes`, gồm `Main.class` và `Greeter.class`. Nó **không chứa** `SourceRootCheck.class` dưới test classes theo mặc định. Nếu muốn phát hành test-jar thì cần cơ chế riêng như `maven-jar-plugin:test-jar`, không liên quan trực tiếp tới `add-test-source`.

POM mẫu không khai báo `Main-Class` trong manifest, nên đừng giả định có thể chạy bằng:

```bash
java -jar target/extra-source-roots-demo-1.0.0.jar
```

Dùng `java -cp target/classes com.example.app.Main` là cách đáng tin cậy của bài.

## 5. Thử bỏ registration để quan sát triệu chứng

Khi muốn xác nhận chính Build Helper Plugin tạo ra sự khác biệt, có thể thử trên branch/lab project:

### 5.1. Bỏ add-source

Tạm thời bỏ **execution `register-main-source-roots`** khỏi POM, giữ nguyên các `.java`, rồi chạy:

```bash
mvn clean compile
```

Vì `Main.java` import class ngoài default root, compiler **không tìm được `com.example.shared.Greeter`**, nên build thất bại. Khôi phục execution sau thí nghiệm.

**Đừng chỉ chạy `mvn compile` sau khi bỏ registration**, bởi vì `target/classes` từ build trước có thể còn `Greeter.class`, khiến bạn đánh giá sai. Luôn dùng `clean` để tránh lớp cũ che lỗi.

### 5.2. Bỏ add-test-source

Giữ `add-source` nhưng tạm bỏ **execution `register-test-source-roots`**:

```bash
mvn clean test-compile
```

Maven vẫn có thể **BUILD SUCCESS**, vì trong `src/test/java` mặc định không có test code và file `SourceRootCheck.java` nằm ngoài những roots được biết tới. Điều này không chứng minh Maven đã biên dịch file ở `src/additional-test/java`.

Hãy kiểm tra file:

```text
target/test-classes/com/example/check/SourceRootCheck.class
```

Nó sẽ **không có** sau clean test-compile nếu không có cách đăng ký khác. Thử chạy class smoke check sẽ báo `ClassNotFoundException` hoặc lỗi không tìm thấy main class. Sau đó khôi phục execution và chạy lại.

**Bài học:** build thành công có thể có nghĩa một số nguồn **không được compile**, chứ không có nghĩa build đã nhìn thấy mọi `.java` trong workspace.

## 6. Phối hợp với code generator ở generate-sources

Một workflow sinh mã thường có hai hành động:

1. **Generator tạo file `.java`** vào thư mục đích trong `target/generated-sources/...`.
2. Maven Compiler Plugin **biên dịch file** sau khi thư mục đó được biết là source root.

Build Helper Plugin hỗ trợ **bước 2 (registration)**; nó không tự làm **bước 1 (generation)**. Một pipeline khái niệm:

```text
validate
    |
generate-sources
    |-- [Generator Plugin] tạo GeneratedApi.java
    |     trong target/generated-sources/custom-api/
    |
    |-- build-helper:add-source
    |     đăng ký target/generated-sources/custom-api/
    |
process-sources
    |
generate-resources / process-resources
    |
compile
    |-- maven-compiler-plugin biên dịch cả:
    |      src/main/java/
    |      target/generated-sources/custom-api/
```

**Thứ tự trong cùng phase quan trọng.** Nếu generator và `build-helper:add-source` cùng bind vào `generate-sources`, hãy xác nhận plugin executions được Maven sắp xếp đúng như mong muốn và folder thực sự tồn tại trước khi bạn dùng `skipIfMissing`. Trong Maven 3, executions trong POM thường được gọi theo thứ tự cấu hình trong một phase, sau default bindings tương ứng; vẫn nên kiểm tra execution logs thay vì chỉ đoán.

### 6.1. Fragment add-source cho generated code

Trong plugin `build-helper-maven-plugin` của module tiêu thụ, execution có thể cấu hình:

```xml
<execution>
    <id>register-generated-api-sources</id>
    <phase>generate-sources</phase>
    <goals>
        <goal>add-source</goal>
    </goals>
    <configuration>
        <sources>
            <source>${project.build.directory}/generated-sources/custom-api</source>
        </sources>
    </configuration>
</execution>
```

Đây **chỉ là fragment cấu hình đăng ký**, không phải một generator đầy đủ; bạn phải có một generator/step khác tạo `.java` vào chính thư mục đó. Nếu tên folder output của generator khác, hãy lấy **giá trị cấu hình thật** của generator thay vì copy một đường dẫn đoán.

**Lưu ý về thời điểm:** `generate-sources` trước `compile`, nhưng cũng cần xét generator có chạy ở phase khác hoặc chỉ chạy theo profile không. Nếu generator bị skip ở CI, Build Helper Plugin vẫn có thể đăng ký một folder trống và Maven compiler không thấy file, tạo ra lỗi downstream hoặc bỏ mất generated API.

### 6.2. Không tự thêm nếu generator đã đăng ký source roots

Nhiều công cụ/code generators có sẵn logic bổ sung generated source root vào Maven project. Một số tình huống:

- Maven Compiler Plugin có thể tự làm việc với generated sources của annotation processing theo cấu hình plugin/version.
- Plugin sinh API/schema có thể tự thêm output directory vào compile roots.
- Một số Maven integrations cho Protobuf, JAXB hoặc DSL có goal tạo source kèm đăng ký root.

**Không giả định plugin nào cũng tự đăng ký.** Đọc tài liệu của **đúng plugin và version**. Nếu generator đã đăng ký, cấu hình `build-helper:add-source` trùng có thể làm log khó hiểu, tăng nguy cơ quét lại hoặc tạo sự khác biệt giữa IDE/CI. Trước khi thêm Build Helper, kiểm tra compiler inputs thực tế.

### 6.3. Source sinh ra nên ở target chứ không nằm lẫn với mã viết tay

Thư mục hợp lý:

```text
target/generated-sources/custom-api/
```

hơn là ghi đè:

```text
src/main/java/
```

Vì generated source trong `target`:

- Có thể bị dọn sạch bằng `mvn clean`.
- Không cần commit vào Git nếu generator được chạy tái lập.
- Không ghi đè code do người phát triển viết.
- Tách nguồn do công cụ tạo với nguồn quản lý thủ công.
- Dễ thấy output của từng generator qua tên thư mục con.

Tuy nhiên, **không commit file generated source rồi đồng thời tự sinh lại nội dung bất định mà không có quy ước**. Team phải thống nhất nguồn chân lý là schema/spec hay generated files và cách kiểm tra drift.

### 6.4. Generated test sources cần phase tương ứng

Nếu generator tạo test Java ở:

```text
target/generated-test-sources/custom-tests/
```

thì đăng ký bằng `build-helper:add-test-source` ở `generate-test-sources`, trước `test-compile`. Đừng đưa generated tests vào main compile roots chỉ vì code ở đó là `.java`; nếu làm vậy các test helpers/framework classes có thể bị đóng vào artifact ứng dụng.

## 7. Khi nào dùng add-source, khi nào dùng add-resource?

Đây là nhầm lẫn thường gặp trong chủ đề **Tài nguyên và sinh mã**.

### 7.1. Ví dụ file properties

Nếu có:

```text
src/extra-config/config.properties
```

và bạn muốn file đó nằm trên runtime classpath khi packaging, hãy dùng **resources** (Maven Resources Plugin hay Build Helper `add-resource`), không dùng `add-source`.

Một fragment POM cho Build Helper:

```xml
<execution>
    <id>add-extra-resource-directory</id>
    <phase>generate-resources</phase>
    <goals>
        <goal>add-resource</goal>
    </goals>
    <configuration>
        <resources>
            <resource>
                <directory>${project.basedir}/src/extra-config</directory>
            </resource>
        </resources>
    </configuration>
</execution>
```

Đây là fragment **của cùng plugin** `build-helper-maven-plugin` trong `<executions>`. Trong project đơn giản, bạn cũng có thể khai báo `<build><resources>` mà không cần Build Helper Plugin, nếu không phải thêm một resource root có điều kiện trong lifecycle.

**Không dán một `<build><resources>` mới một cách cẩu thả làm mất `src/main/resources` mặc định.** Khi cấu hình custom resources, xác minh root mặc định còn được xử lý nếu project cần nó.

### 7.2. So sánh kết quả

| File đầu vào | Goal phù hợp | Điều xảy ra điển hình |
| --- | --- | --- |
| `src/additional/java/.../Greeter.java` | `add-source` | `compiler:compile` tạo `.class` |
| `src/additional-test/java/.../SourceRootCheck.java` | `add-test-source` | `compiler:testCompile` tạo test `.class` |
| `src/extra-config/config.properties` | `add-resource` | `resources:resources` copy vào `target/classes` |
| `src/extra-test-data/input.json` | `add-test-resource` | `resources:testResources` copy vào `target/test-classes` |

**Đăng ký resource không tự bật filtering.** Nếu muốn thay placeholder trong `.properties`/`.xml`, cần cấu hình filtering đúng và tránh chạy filter trên binary data. Những việc này thuộc Maven Resources Plugin và cấu hình `<resources>`, không phải logic của Java compiler.

## 8. Đừng thay `<sourceDirectory>` khi chỉ muốn thêm root

Maven POM hỗ trợ:

```xml
<build>
    <sourceDirectory>src/additional/java</sourceDirectory>
</build>
```

Đây là **cấu hình thay đổi source directory chính**, không phải cách chuẩn để thêm một source directory **cạnh** `src/main/java`. Nếu bạn thay `<sourceDirectory>` sang thư mục mới, dự án có thể **không còn biên dịch mã ở `src/main/java`** như trước.

Cách an toàn hơn khi muốn **giữ mặc định và bổ sung** là:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>extra-main</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>add-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>${project.basedir}/src/additional/java</source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **fragment** đã được trình bày trong POM hoàn chỉnh ở mục 4. Nếu module chỉ có một source directory hoàn toàn khác và không cần `src/main/java`, cấu hình `<sourceDirectory>` có thể hợp lý. Nhưng khi có **nhiều roots**, Build Helper Plugin dễ thể hiện đúng ý định hơn.

### 8.1. Đừng chuyển `Greeter.java` thành dependency JAR nếu nó thuộc cùng module

Nếu `Greeter.java` là code thuộc cùng artifact/app, đăng ký extra source root là hợp lý trong hệ thống legacy hoặc codegen. Tuy nhiên, nếu đó là một thư viện dùng chung thực sự cho nhiều dịch vụ, cân nhắc **tách thành Maven module riêng** với GAV và dependency rõ ràng, thay vì để nhiều modules cùng biên dịch một cây source với bản sao code khác nhau.

Điều quan trọng là chọn đúng **ranh giới module** chứ không phải mọi vấn đề compiler không thấy class đều giải quyết bằng `add-source`.

## 9. Parent POM và multi-module: tránh thêm nhầm cho tất cả module

Trong một reactor multi-module, parent POM có thể cấu hình Build Helper Plugin trong `<build><plugins>` và children kế thừa plugin/executions. Khi đó **mỗi module** có thể thử đăng ký:

```text
${project.basedir}/src/additional/java
```

tại thư mục riêng của module. Điều này có thể tốt nếu tất cả modules đều dùng cấu trúc giống nhau; nhưng cũng có thể tạo roots trống hoặc hành vi không mong muốn.

### 9.1. Dùng pluginManagement khi muốn quản lý version, không bắt mọi child chạy

Parent có thể chỉ quản lý version:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đây là **fragment parent POM**. Nó không tự tạo source roots cho mọi module; module cần plugin execution có thể khai báo trong `<build><plugins>` và kế thừa version managed.

### 9.2. Module cụ thể khai báo executions

Ví dụ `api-codegen` thực sự có generated sources, còn `web` không. Nên chỉ module `api-codegen` đăng ký:

```xml
<source>${project.build.directory}/generated-sources/api</source>
```

trong execution tương ứng. Tránh đưa đường dẫn generated API vào POM cha rồi mọi module đều nhận nó khi chưa có code generator.

### 9.3. Aggregation khác inheritance

Root `<modules>` giúp Maven biết tập project trong reactor. Nhưng plugin executions trong parent chỉ được child kế thừa khi child có quan hệ `<parent>` phù hợp. **Chỉ được liệt kê trong `<modules>` không làm một module tự kế thừa build-helper config.**

Đối với lỗi compile chỉ ở module `app`, hãy chạy ở module đó hoặc dùng `mvn -pl :app -am ...`; không sửa bừa parent config trước khi xác định module nào đang thiếu source root.

## 10. Kiểm tra registered roots: dựa vào output thật

Lý tưởng là kiểm tra **cả ba tầng**:

1. **POM:** plugin đã khai báo goal và phase đúng.
2. **Maven execution logs:** goal `build-helper:add-source` / `add-test-source` thật sự được thực thi trước compiler.
3. **Compiled artifacts:** các `.class` từ roots bổ sung tồn tại ở đúng `target/classes` hoặc `target/test-classes`.

Các lệnh hữu ích:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean test-compile
mvn -X clean test-compile
```

`effective-pom` giúp xem **execution configuration** sau parent/profile inheritance. Nhưng source roots do Build Helper Plugin thêm **trong lúc chạy lifecycle** có thể **không hiện thành danh sách cuối cùng trong effective POM của một invocation khác**. Do đó đừng kết luận goal không hoạt động chỉ vì `help:effective-pom` không hiện một phần tử `<sourceDirectory>` mới.

Với project demo, các class cần quan sát:

```text
target/classes/com/example/app/Main.class
target/classes/com/example/shared/Greeter.class
target/test-classes/com/example/check/SourceRootCheck.class
```

Nếu file `Greeter.class` tồn tại từ một build cũ mà bạn chưa chạy `clean`, đó **không phải** bằng chứng phiên cấu hình mới đúng. Luôn dùng `mvn clean test-compile` khi chẩn đoán.

### 10.1. Kiểm tra bằng javap

Sau build:

```bash
javap -classpath target/classes com.example.shared.Greeter
javap -classpath target/test-classes com.example.check.SourceRootCheck
```

Nếu các lệnh in được signatures/class tương ứng, những `.class` đang hiện diện. Nếu không tìm thấy, quay lại kiểm tra phase, đường dẫn root, output file và plugin configuration.

Đây là cách kiểm tra **sản phẩm compilation**, không phải một API đọc runtime `project.compileSourceRoots`. Đối với debug chuyên sâu, có thể dùng `mvn -X` để xem plugin/Compiler Plugin đang nhận source roots nào.

### 10.2. Những thứ `mvn test` không chứng minh

`mvn test` chạy lifecycle đến `test`, nên các phases `generate-test-sources` và `test-compile` đã có cơ hội chạy. Tuy nhiên:

- Không có `@Test` hay test provider phù hợp thì test runner có thể chạy **0 tests**.
- Test source root không được đăng ký có thể **không gây compile error** nếu source bị bỏ qua.
- Một test class với tên khác naming convention không tự chạy.
- Test có thể bị skip qua flags/config.

Nếu bạn cần **kiểm thử tự động thật**, dùng framework phù hợp (ví dụ JUnit Jupiter) và Maven Surefire Plugin có version tương thích; xác nhận số test executed, test reports và exit code. Bài demo dùng **smoke check bằng Java CLI** để độc lập với external test libraries.

## 11. Cấu hình `skipIfMissing`: tiện nhưng dễ che lỗi generator

Theo docs Build Helper 3.6.2, một số tham số liên quan:

| Goal | Tham số | Default | Ý nghĩa |
| --- | --- | --- | --- |
| `add-source` | `skipAddSource` | `false` | Bỏ qua toàn bộ goal |
| `add-source` | `skipAddSourceIfMissing` | `false` | Không thêm root nếu folder chưa tồn tại |
| `add-test-source` | `skipAddTestSource` | `false` | Bỏ qua toàn bộ goal |
| `add-test-source` | `skipAddTestSourceIfMissing` | `false` | Không thêm test root nếu folder chưa tồn tại |

Ví dụ cho **nguồn thực sự tùy chọn**:

```xml
<configuration>
    <skipAddSourceIfMissing>true</skipAddSourceIfMissing>
    <sources>
        <source>${project.build.directory}/generated-sources/optional-model</source>
    </sources>
</configuration>
```

Đây là **fragment** cho `build-helper:add-source`, không phải POM hoàn chỉnh. Nếu thư mục chưa có khi goal chạy, plugin có thể **không thêm root**.

Tình huống nguy hiểm: generator lẽ ra phải tạo code ở `generate-sources` nhưng bị lỗi hoặc skip; `skipAddSourceIfMissing=true` làm root không được thêm, và compiler có thể không gặp generated source cần thiết. Với generated source **bắt buộc**, không dùng `skipIfMissing` để che hỏng generation; kiểm tra plugin generator đã chạy và tạo output.

Ngược lại, với source root thực sự tùy chọn, option này có thể giúp tránh đăng ký đường dẫn không tồn tại, nhất là khi profile bật/tắt tính năng. Cần phân biệt **tùy chọn được thiết kế** và **một bước build bị lỗi**.

## 12. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Khắc phục |
| --- | --- | --- |
| `package com.example.shared does not exist` | Không đăng ký `src/additional/java`, phase chưa chạy hoặc path sai | Kiểm tra `add-source`, path và `mvn clean compile` |
| `cannot find symbol: Greeter` | `Greeter.java` không nằm trong source root compiler nhận | Kiểm tra source root và package/path |
| `Greeter.class` có từ trước nhưng source mới không compile | Cache `target/classes` cũ che lỗi | `mvn clean compile`, xem `.class` mới |
| `mvn compile` OK nhưng test helper không có | Chưa đến phase `generate-test-sources`/`test-compile` | `mvn clean test-compile` |
| `mvn test` thành công nhưng không chạy test | Test root không đăng ký hoặc không có test discovery | Kiểm tra compiled tests, Surefire và reports |
| Test class được compile vào main JAR | Dùng `add-source` thay cho `add-test-source` | Chuyển sang test roots và clean build |
| `.properties` không xuất hiện trên classpath | Đăng ký bằng add-source thay vì resource mechanism | Dùng `<resources>` hoặc `add-resource` |
| Java source bị copy nguyên dạng vào JAR | Dùng resource copy thay vì compiler | Dùng `add-source` để tạo `.class` |
| Chỉnh `<sourceDirectory>` rồi mất `src/main/java` | Đã thay source root chính, không phải bổ sung | Khôi phục default và dùng `add-source` |
| Generated Java không được compile | Generator chưa chạy, sai output folder hoặc registration muộn | Rà `generate-sources` và compiler source roots |
| Source root được add nhưng folder không có | Sai path hoặc generator chưa tạo | Xác minh artifact output/generator |
| `skipIfMissing` làm mã bị bỏ qua | Flag bật khi folder chưa được tạo | Bỏ flag cho source bắt buộc và sửa generator |
| Plugin chạy trong mọi child module | Kế thừa execution từ parent | Đặt execution tại module cần nó |
| Plugin được quản lý nhưng không thực thi | Chỉ có trong `pluginManagement` | Khai báo plugin/execution ở `<build><plugins>` |
| IDE báo đỏ imports, Maven CLI build OK | IDE importer chưa nhận generated/additional sources | Reload Maven project, xem generated-source settings |
| Maven CLI lỗi nhưng IDE chạy được | IDE tự add source folder riêng, POM thiếu execution | Sửa POM để CI/CLI là nguồn chân lý |
| Registration chạy sau compile | Bind goal vào phase quá muộn | Đổi sang `generate-sources` hoặc `generate-test-sources` |
| Class duplicated / duplicate class | Cùng Java class xuất hiện ở hai roots | Loại bản sao, chuẩn hóa generator output |
| Mã từ module khác được add làm source | Nhầm ranh giới Maven modules | Dùng GAV dependency thay vì trỏ vào source module khác |
| Path source chạy ở laptop, lỗi trên CI | Đường dẫn tuyệt đối phụ thuộc máy | Dùng `${project.basedir}`/`${project.build.directory}` |
| `target/generated-sources` được commit | Build output bị quản lý như code viết tay | Thống nhất source-of-truth và `.gitignore` |
| Biên dịch chỉ thấy nguồn một module | Reactor selection và plugin inheritance khác kỳ vọng | Kiểm tra `-pl`, `-am`, effective POM từng module |

### 12.1. Một quy trình debug có thể lặp lại

```bash
mvn -version
mvn clean test-compile
mvn -X clean test-compile
mvn help:effective-pom -Doutput=effective-pom.xml
javap -classpath target/classes com.example.shared.Greeter
javap -classpath target/test-classes com.example.check.SourceRootCheck
```

**Lưu ý về debug:** `-X` có thể ghi thông tin về repository, đường dẫn hoặc credentials/môi trường; xem trước khi gửi log cho người khác. Với project lớn, debug đúng một module bằng `-pl :module-id` hoặc chạy từ POM module và build prerequisites bằng `-am` khi phù hợp.

### 12.2. Khi Maven báo `No sources to compile`

Đây **không tự động là lỗi**, vì POM-only module hoặc một module không có Java sources có thể không cần compile. Nhưng nếu bạn **mong đợi source Java**, kiểm tra:

- Goal `add-source` có được thực thi trước compile không?
- `<sources><source>...` trỏ tới **directory**, không phải file?
- Thư mục đã tồn tại và chứa `.java` ở package layout đúng chưa?
- Generated source đã được tạo trong đúng phase chưa?
- IDE hoặc plugin đã đổi `sourceDirectory`/compile roots ra sao?
- Có profile/skip option khiến generator hay registration bị bỏ qua không?

Đừng kết luận “No sources to compile” là đủ để chấm build đạt khi đề bài là một module đáng ra phải có code output.

## 13. Multi-language và annotation processors: khi nào không cần Build Helper?

Không phải mọi nguồn bổ sung đều nên đi qua `build-helper:add-source`.

### 13.1. Kotlin, Groovy, Scala

Các ngôn ngữ JVM khác có **compiler plugin riêng** và phase/source-layout convention riêng. Đăng ký folder Kotlin hoặc Groovy làm một Java source root chưa chắc giúp Maven Compiler Plugin biên dịch ngôn ngữ đó. Cần dùng Kotlin/Groovy/Scala Maven plugin phù hợp, kiểm tra thứ tự Java/other-language compilation và test compiler integration.

### 13.2. Annotation processing

Java annotation processors có thể sinh `.java` từ annotations trong lúc Maven Compiler Plugin chạy. Plugin có thể quản lý generated sources directory và đưa generated files vào quá trình compile theo cơ chế riêng. Không tự thêm toàn bộ `target/generated-sources/annotations` vào build-helper trước khi đã xác định Compiler Plugin và annotation processor xử lý ra sao.

Một số lỗi double-compilation/duplicate classes xuất phát từ việc vừa để compiler tự xử lý generated sources, vừa đăng ký lặp cùng thư mục như một nguồn thủ công. Cần đọc docs của compiler/processor version thực sự dùng.

### 13.3. OpenAPI, Protobuf, JAXB, jOOQ và công cụ sinh API

Mỗi generator có plugin/output configuration riêng; nhiều plugin có goal hoặc flag tự add generated source roots. Hãy trả lời:

1. Generator chạy ở **phase nào**?
2. Tạo `.java` vào **thư mục nào**?
3. Nó **có tự đăng ký** source root không?
4. File được sinh là **main** hay **test** source?
5. Nếu codegen skipped/failed, build có phát hiện sai lệch không?
6. Có sự khác biệt giữa môi trường local, IDE, CI, các profiles không?

Chỉ thêm Build Helper nếu còn thiếu bước **register root**. Đừng dùng nó làm “búa vạn năng” cho mọi code generation.

## 14. Build lặp lại, clean và Git

Một dự án với source bổ sung cần trả lời rõ **ai sở hữu nội dung của directory**.

| Loại thư mục | Nội dung | Chính sách điển hình |
| --- | --- | --- |
| `src/additional/java` | Mã viết tay có version control | Commit như mã chính |
| `src/additional-test/java` | Mã test viết tay | Commit như test source |
| `target/generated-sources/custom-api` | Mã do generator sinh trong build | Không commit; `mvn clean` xóa được |
| `target/generated-test-sources/custom-tests` | Mã test sinh tự động | Không commit; có step sinh mã rõ |
| `target/classes` | `.class` đã biên dịch | Build output, không commit |
| `target/test-classes` | `.class` test đã biên dịch | Build output, không commit |

Dù đăng ký root bằng đường dẫn tương đối/module-based có thể giúp build **portable**, nó không tự bảo đảm artifact **reproducible**. Generator có thể chèn timestamp, paths địa phương, output không xác định hoặc phiên bản plugin không được ghim. Cần kiểm soát inputs, tool versions, encoding và runtime môi trường.

### 14.1. Không dùng source root để né thiết kế module

Nếu nhiều service copy chung một folder generated sources để build, có thể xuất hiện class conflicts và phụ thuộc ẩn. Nếu shared code thực sự được dùng trong nhiều modules, cân nhắc artifact dùng chung hoặc module codegen có trách nhiệm phát hành đầu ra phù hợp. Source root bổ sung giải quyết vấn đề **compile inputs**, không thay thế quản lý dependency/architecture.

## 15. Checklist khi thêm source root mới

1. Xác định thư mục mới chứa **Java source**, **test Java source**, **resource** hay ngôn ngữ khác.
2. Nếu Java main source: dùng `build-helper:add-source` ở `generate-sources`.
3. Nếu Java test source: dùng `build-helper:add-test-source` ở `generate-test-sources`.
4. Nếu resource: dùng `<resources>`/`<testResources>` hoặc `add-resource`/`add-test-resource`.
5. Chỉ thêm **thư mục gốc**; đường dẫn package của `.java` phải đúng bên dưới.
6. Dùng `${project.basedir}` hoặc `${project.build.directory}`, tránh đường dẫn cá nhân.
7. Nếu có generator: chạy generator **trước** compiler và xác nhận có output thực.
8. Kiểm tra generator đã tự đăng ký root chưa; tránh cấu hình trùng.
9. Không thay `<sourceDirectory>` khi mục tiêu chỉ là **bổ sung** root.
10. Chỉ bind execution trong **module cần sử dụng**, tránh inheritance ngoài chủ đích.
11. Chạy `mvn clean test-compile` để bỏ output cũ.
12. Kiểm tra `.class` thực sự tồn tại ở `target/classes` hoặc `target/test-classes`.
13. Chạy chương trình/test bằng đúng classpath, không suy đoán Surefire đã chạy smoke check.
14. Kiểm tra IDE/CI đều hiểu POM; Maven CLI phải hoạt động trên checkout sạch.
15. Với generated sources: làm rõ phần nào được commit và phần nào build sẽ tạo lại.
16. Khi build lỗi: xem phase/execution, roots và compiler log trước khi thay toàn bộ cấu trúc project.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Mã `Greeter.java` ở `src/additional/java` không được compile; nên dùng goal nào?  
**Đáp án:** `build-helper:add-source` và khai báo `src/additional/java` trong `<sources>` ở `generate-sources`, miễn đó là Java source của cùng module.

**Câu 2.** Vì sao không chỉ đổi `<sourceDirectory>` thành `src/additional/java`?  
**Đáp án:** Vì cách đó thay source directory chính; có thể làm mất compile root mặc định `src/main/java` mà project vẫn cần.

**Câu 3.** Mã test nằm ở `src/additional-test/java`; đăng ký bằng goal gì?  
**Đáp án:** `build-helper:add-test-source` ở `generate-test-sources`.

**Câu 4.** `mvn clean test-compile` thành công nhưng không thấy `SourceRootCheck.class`. Có nghĩa code test đúng?  
**Đáp án:** Không. Test source root có thể chưa được đăng ký, nên file Java chưa được compiler đọc. Kiểm tra `.class` và compiler inputs.

**Câu 5.** `add-source` có tự sinh `.java` từ OpenAPI YAML không?  
**Đáp án:** Không. Nó chỉ đăng ký source root; cần generator phù hợp tạo file.

**Câu 6.** Generator chạy ở `generate-sources`, Build Helper đăng ký generated root ở `compile` có vấn đề gì?  
**Đáp án:** Đăng ký có thể quá muộn so với compiler goal cùng phase; nên đăng ký trong `generate-sources`, trước compile.

**Câu 7.** `.properties` có nên được đăng ký bằng `add-source` để Maven copy vào JAR?  
**Đáp án:** Không. Dùng resources mechanism; `add-source` dành cho compiler sources.

**Câu 8.** Maven Compiler Plugin tự xử lý annotation-generated sources; có cần Build Helper cho cùng output folder?  
**Đáp án:** Thường không. Kiểm tra plugin/version và roots thực tế; tránh đăng ký trùng.

**Câu 9.** Tại sao `src/additional-test/java` không được đóng trong main JAR?  
**Đáp án:** Nó được đưa vào **test compile roots**, output tại `target/test-classes`; JAR chính thường chỉ đóng `target/classes`.

**Câu 10.** Vì sao nên dùng `${project.basedir}` thay vì đường dẫn `C:\Users\...`?  
**Đáp án:** Đường dẫn module-relative chạy được trên CI, máy khác và nhiều hệ điều hành mà không phụ thuộc cấu trúc thư mục cá nhân.

**Câu 11.** Parent POM quản lý version build-helper trong pluginManagement thì mọi child có thêm root không?  
**Đáp án:** Không. Phải có plugin/execution thực sự tham gia build tại module tương ứng.

**Câu 12.** Muốn chạy Java smoke-check thuộc test root bằng `java -cp`, cần đưa gì vào classpath?  
**Đáp án:** `target/test-classes` để có test class và `target/classes` để có main class mà test dùng.

**Câu 13.** Vì sao nên dùng `mvn clean compile` khi debug source root?  
**Đáp án:** Để xóa `.class` cũ vốn có thể che việc source mới không được đăng ký hoặc biên dịch.

**Câu 14.** Một module cần class ở module Maven khác. Có nên dùng Build Helper trỏ vào source của module bên cạnh?  
**Đáp án:** Không nên. Thông thường khai báo Maven `<dependency>` tới artifact/module đúng để có ranh giới rõ.

**Câu 15.** Nếu thư mục generated Java chưa tồn tại mà đặt `skipAddSourceIfMissing=true`, điều gì có thể xảy ra?  
**Đáp án:** Build Helper bỏ qua đăng ký root và compiler không nhìn thấy mã cần sinh; nếu mã bắt buộc, cần sửa generator/phase thay vì che lỗi.

## 17. Tài liệu tham khảo

1. [MojoHaus Build Helper Maven Plugin — Tổng quan](https://www.mojohaus.org/build-helper-maven-plugin/)
2. [MojoHaus Build Helper Maven Plugin — Usage](https://www.mojohaus.org/build-helper-maven-plugin/usage.html)
3. [MojoHaus Build Helper Maven Plugin 3.6.2 — build-helper:add-source](https://www.mojohaus.org/build-helper-maven-plugin/add-source-mojo.html)
4. [MojoHaus Build Helper Maven Plugin 3.6.2 — build-helper:add-test-source](https://www.mojohaus.org/build-helper-maven-plugin/add-test-source-mojo.html)
5. [MojoHaus Build Helper Maven Plugin — Plugin Goals](https://www.mojohaus.org/build-helper-maven-plugin/plugin-info.html)
6. [Apache Maven Compiler Plugin — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
7. [Apache Maven Compiler Plugin — compiler:testCompile](https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html)
8. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
9. [Apache Maven — POM Reference: Build, Resources, Directories](https://maven.apache.org/pom.html)
10. [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)

**Ghi nhớ:** Khi có nguồn Java bổ sung, hãy **đăng ký đúng source root, đúng kiểu main/test, đúng phase trước compiler**. `build-helper:add-source` và `build-helper:add-test-source` chỉ **đưa thư mục vào mô hình build**; chúng không tự sinh mã, không tự chạy tests và không biến Java files thành resources. Sau cùng, hãy xác nhận bằng **class file và chương trình chạy thật**, không chỉ bằng `BUILD SUCCESS`.
