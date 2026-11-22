# Thêm phụ thuộc bắc cầu rồi giải thích classpath thực tế trong Maven

## 1. Mục tiêu thực hành

Trong Maven, một thư viện có thể xuất hiện trong **classpath** của project dù project **không khai báo trực tiếp thư viện ấy** trong `pom.xml`. Đó là **transitive dependency — phụ thuộc bắc cầu**.

Bài thực hành tổng hợp này yêu cầu bạn không chỉ nhớ sơ đồ `A → B → C` mà phải **tạo một project thật**, chạy Java 17, đọc cây dependency của Maven, xuất đường dẫn classpath thực tế, tự gây lỗi thiếu JAR và sửa lỗi bằng khai báo dependency đúng.

Bạn sẽ thực hiện các bước:

1. Tạo một Maven multi-module reactor với `helper`, `facade`, `app`.
2. Cho `facade` phụ thuộc trực tiếp `helper`; `app` chỉ phụ thuộc trực tiếp `facade`.
3. Cho `app` **dùng class của `helper` ngay trong source**, dù không khai báo `helper`.
4. Chạy `mvn clean install` và xác nhận Java code vẫn biên dịch.
5. Đọc `dependency:tree`, tách dependency trực tiếp và bắc cầu.
6. Xuất **runtime classpath** bằng Maven Dependency Plugin, thêm `app/target/classes` rồi chạy Java.
7. Cố tình bỏ `helper` khỏi `java -cp` để quan sát lỗi nạp class.
8. Chạy `dependency:analyze` phát hiện sử dụng dependency chưa khai báo.
9. Sửa POM của `app` bằng dependency trực tiếp, đo lại cây và classpath.
10. Phân biệt `compile`, `runtime`, `test`, `provided`, `optional`, `exclusions`, dependency mediation và `dependencyManagement`.

**Kết quả mong đợi:** bạn giải thích được vì sao một thư viện có thể **được Maven đưa lên compile classpath**, vì sao nó phải **có mặt khi Java chạy**, và vì sao vẫn nên **khai báo trực tiếp thư viện mà mã nguồn của bạn dùng trực tiếp**.

## 2. Sơ đồ và ba khái niệm dễ bị nhầm

Sơ đồ dự án:

```text
classpath-lab (parent / aggregator)
├── helper
│   └── com.example.transitive.helper.TextNormalizer
├── facade
│   ├── dependency: classpath-helper (compile)
│   └── com.example.transitive.facade.GreetingService
└── app
    ├── dependency: classpath-facade (compile)
    ├── dependency: junit-jupiter (test)
    └── com.example.transitive.app.Main
```

Đối với **app**, đường phụ thuộc là:

```text
classpath-app
  └── classpath-facade:1.0.0          ← direct dependency
        └── classpath-helper:1.0.0    ← transitive dependency
```

**Ba khái niệm:**

| Thuật ngữ | Cách hiểu chính xác |
| --- | --- |
| **Direct dependency** | Artifact có `<dependency>` trực tiếp trong POM của project đang xét |
| **Transitive dependency** | Artifact xuất hiện do POM của một dependency khác khai báo, chịu quy tắc truyền scope/optional/exclusion/mediation |
| **Classpath** | Danh sách **thư mục classes và JARs cụ thể** mà compiler, test runner hoặc Java process dùng để tìm class/resource |

**Dependency graph không phải một chuỗi `-cp` thực thi.** Maven tính graph và chọn artifacts; Maven Compiler Plugin/Surefire chọn classpath phù hợp cho từng goal. Khi bạn chạy `java` bằng tay, **bạn tự cung cấp classpath**. Một JAR nằm ở `~/.m2/repository` không tự xuất hiện trong `java -cp` nếu không được liệt kê hoặc được một launcher khác đưa vào.

**Cùng artifact có thể xuất hiện ở các classpaths khác nhau:**
- `compile`: dùng để biên dịch `src/main/java`;
- `test`: dùng để biên dịch/chạy `src/test/java`, gồm test dependencies;
- `runtime`: dùng khi chương trình chạy thực tế;
- Classpath của một Maven plugin: tách biệt với project dependencies, không tự cùng một đường dẫn.

## 3. Maven tìm và chọn phụ thuộc bắc cầu như thế nào?

Maven đọc `pom.xml` của project và những artifact mà project phụ thuộc. POM của `facade` nói nó cần `helper`; vậy khi `app` phụ thuộc `facade` với scope `compile`, Maven thường đưa **cả `facade` lẫn `helper`** lên classpath phù hợp.

Cụ thể:
- `app → facade` có scope `compile`;
- `facade → helper` có scope `compile`;
- Theo bảng dependency scope của Maven, `compile → compile` tạo transitive dependency hiệu dụng `compile` trong app.

Maven **không sao chép source của helper vào app**. Nó giải quyết các artifacts theo GAV, scopes và các quy tắc khác, rồi đưa JAR hoặc reactor output vào classpath của plugin tương ứng.

Tính transitive không phải “mọi dependency ở mọi nhánh đều được thêm”. Các giới hạn quan trọng:

1. **Scope propagation**: một số scope không truyền tiếp.
2. **Optional**: dependency được đánh dấu optional sẽ không tự truyền đến consumer.
3. **Exclusions**: consumer có thể loại artifact tại một nhánh dependency cụ thể.
4. **Dependency mediation**: nếu nhiều nhánh mang các version khác nhau của cùng artifact, Maven chọn một version.
5. **Dependency management**: khóa/chọn versions và cấu hình cho những artifacts được gặp, không tự thêm artifact mới vào project.
6. **Artifact type/classifier**: không phải thứ gì được tải xuống cũng là JAR đưa lên Java classpath.
7. **Plugin classpath**: Maven build plugins có dependency riêng, không được quản lý giống dependencies ứng dụng.

Một phần quan trọng là **thứ tự từ POM tới classpath**:

```text
POM app
   │
   ├── direct dependencies app
   │
   └── POM của từng dependency (ví dụ facade)
            │
            └── transitive dependencies (ví dụ helper)
                    │
                    ▼
        scope/optional/exclusions/mediation
                    │
                    ▼
         resolved dependency artifacts
                    │
       ┌────────────┴────────────┐
       ▼                         ▼
compile/test classpath     runtime classpath
```

Sơ đồ là mô hình khái niệm; plugin và toolchain quyết định classpath cuối cùng trong mỗi Maven goal.

## 4. Chuẩn bị môi trường thực hành

Yêu cầu:
- JDK 17 trở lên; xem `mvn -version` để biết Maven dùng Java nào.
- Maven 3.9.x hoặc một Maven 4 được plugin trong ví dụ hỗ trợ; bài dùng cú pháp POM model `4.0.0`.
- Có thể tải Maven plugins và JUnit artifacts từ repository, hoặc đã cache đầy đủ.
- Shell Linux/macOS hay Windows PowerShell để chạy các lệnh tương ứng.

Kiểm tra:

```bash
java -version
mvn -version
```

Những mệnh lệnh trong bài chạy từ root **`classpath-lab/`**, trừ khi có chỉ dẫn `-f app/pom.xml`. Không dùng source file của dự án thật để thử phá dependency; tạo một thư mục thực hành mới.

### Lưu ý Maven Wrapper

Nếu project thực dùng `mvnw`/`mvnw.cmd`, thay `mvn` bằng Wrapper tương ứng nhằm giữ Maven distribution được pin. Wrapper **không tự sửa dependency graph**; nó chỉ chốt Maven runtime và hỗ trợ CI/đồng đội chạy cùng Maven version.

## 5. Tạo dự án multi-module hoàn chỉnh

### 5.1. Cây thư mục

```text
classpath-lab/
├── pom.xml
├── helper/
│   ├── pom.xml
│   └── src/main/java/com/example/transitive/helper/TextNormalizer.java
├── facade/
│   ├── pom.xml
│   └── src/main/java/com/example/transitive/facade/GreetingService.java
└── app/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/transitive/app/Main.java
        └── test/java/com/example/transitive/app/MainTest.java
```

Đây là một **reactor**: Maven root POM tập hợp ba modules. `helper` cung cấp một class Java; `facade` sử dụng class đó; `app` phụ thuộc facade và cố ý trực tiếp gọi helper để quan sát transitivity.

### 5.2. Root `classpath-lab/pom.xml` — đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.transitive</groupId>
    <artifactId>classpath-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>helper</module>
        <module>facade</module>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.jupiter.version}</version>
                <scope>test</scope>
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
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.4.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Giải thích:
- Root vừa là **aggregator** qua `<modules>` vừa là **parent** vì từng POM con dùng `<parent>`.
- `maven.compiler.release=17` chọn Java API/bytecode target cho compiler.
- JUnit 5 chỉ được dùng khi một child **khai báo dependency**; `dependencyManagement` không tự thêm JUnit vào cả ba modules.
- Plugin versions được ghim trong `pluginManagement`, giúp tránh biến động ngẫu nhiên giữa các môi trường.
- Artifact IDs khác nhau: `classpath-helper`, `classpath-facade`, `classpath-app`.

### 5.3. `helper/pom.xml` — đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.transitive</groupId>
        <artifactId>classpath-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>classpath-helper</artifactId>
    <packaging>jar</packaging>
</project>
```

Module `helper` không khai báo dependency bên ngoài. Vì vậy khi `facade` cần `helper`, đó là một thư viện nội bộ thuần Java mà Maven có thể dùng từ reactor hoặc local repository.

### 5.4. `facade/pom.xml` — đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.transitive</groupId>
        <artifactId>classpath-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>classpath-facade</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.transitive</groupId>
            <artifactId>classpath-helper</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

Đây là **dependency trực tiếp của facade**. Vì `<scope>` không được khai báo, scope mặc định là `compile`, làm helper xuất hiện trong compile/test/runtime classpaths của facade và có thể **được truyền sang app**.

Nếu facade thay `<scope>` thành `runtime`, chính code Java của facade trực tiếp import class helper sẽ **không biên dịch**, vì runtime dependencies không ở main compile classpath. Đừng sửa scope để “làm nhỏ cây” mà không kiểm source usage.

### 5.5. `app/pom.xml` — đầy đủ, phiên bản cố ý có dùng bắc cầu

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.transitive</groupId>
        <artifactId>classpath-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>classpath-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.transitive</groupId>
            <artifactId>classpath-facade</artifactId>
            <version>${project.version}</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
```

**Chú ý:** `classpath-app` KHÔNG khai báo `classpath-helper`. Đây là chủ đích để bạn nhìn thấy dependency bắc cầu. JUnit có `test` scope được quản lý ở root `dependencyManagement`; nó không là main runtime library.

Đây là POM app **runnable trong ví dụ**, nhưng **chưa phải best practice** nếu mã nguồn app trực tiếp dùng class của helper. Ta sẽ sửa sau khi đã quan sát.

### 5.6. `helper/src/main/java/com/example/transitive/helper/TextNormalizer.java`

```java
package com.example.transitive.helper;

import java.util.Locale;

public final class TextNormalizer {

    private TextNormalizer() {
    }

    public static String upper(String text) {
        if (text == null || text.isBlank()) {
            return "GUEST";
        }
        return text.strip().toUpperCase(Locale.ROOT);
    }
}
```

Java 17 compilable. `Locale.ROOT` tránh sai khác uppercase do locale mặc định của máy.

### 5.7. `facade/src/main/java/com/example/transitive/facade/GreetingService.java`

```java
package com.example.transitive.facade;

import com.example.transitive.helper.TextNormalizer;

public final class GreetingService {

    public String hello(String name) {
        return "Hello, " + TextNormalizer.upper(name) + "!";
    }
}
```

Facade **thực sự dùng helper**, nên khai báo helper trong `facade/pom.xml` là hợp lệ và cần thiết. Đây không phải dependency thừa để tạo sơ đồ giả.

### 5.8. `app/src/main/java/com/example/transitive/app/Main.java`

```java
package com.example.transitive.app;

import com.example.transitive.facade.GreetingService;
import com.example.transitive.helper.TextNormalizer;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        GreetingService greeter = new GreetingService();
        System.out.println(greeter.hello(" maven "));
        System.out.println(
                "Transitive API: " + TextNormalizer.upper(" Java "));
    }
}
```

**Điểm thí nghiệm quan trọng:** `Main` trực tiếp import `TextNormalizer` của **helper**, nhưng app POM chỉ khai báo facade. Maven vẫn có thể cho compiler thấy helper vì `compile → compile` truyền transitively.

Điều này cho thấy:
- **Có thể compile** không đồng nghĩa dependency khai báo đã **đúng và đầy đủ**;
- App hiện **coupled trực tiếp vào helper API** mà POM app không thể hiện;
- Nếu facade đổi implementation hoặc chuyển helper thành optional, app có thể ngừng compile dù app source không đổi.

### 5.9. `app/src/test/java/com/example/transitive/app/MainTest.java`

```java
package com.example.transitive.app;

import com.example.transitive.facade.GreetingService;
import com.example.transitive.helper.TextNormalizer;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {

    @Test
    void greeterUsesHelper() {
        assertEquals(
                "Hello, MAVEN!",
                new GreetingService().hello(" maven "));
    }

    @Test
    void appCanReachTransitiveType() {
        assertEquals("JAVA", TextNormalizer.upper(" Java "));
    }

    @Test
    void blanksAreNormalized() {
        assertEquals("GUEST", TextNormalizer.upper(" "));
    }
}
```

Ba JUnit Jupiter tests này **cố ý dùng helper transitive** ngay trong test source, để bạn thấy helper xuất hiện trên test classpath. JUnit chỉ ở test scope; không phải main application dependency. Dự kiến **3 tests, 0 failures/errors** nếu build và resolution thành công.

## 6. Build reactor và chạy Java

### 6.1. Build từ root

Từ thư mục `classpath-lab`:

```bash
mvn -B -ntp clean install
```

Vì sao chọn `install` thay vì chỉ `package` trong bài này?
- `package` đủ để build reactor và tạo JARs;
- `install` **còn đưa helper/facade/app artifacts vào local Maven repository**;
- Các thí nghiệm `dependency:tree` và `dependency:build-classpath` chạy **độc lập** với POM app ở các bước sau sẽ resolve được helper/facade từ local repository.

**Không nhầm `mvn install` với `mvn deploy`:** install chỉ ghi local repository của máy, không đẩy artifact lên remote.

Maven reactor sẽ thấy thứ tự **helper → facade → app**, do quan hệ dependencies, chứ không chỉ vì thứ tự `<modules>`. Root packaging `pom` tham gia reactor nhưng không tạo một Java app JAR.

Nếu parent/local repo chưa có Maven plugins/JUnit, lần đầu có thể cần network. Nếu thiếu dependencies vì offline/repository policy, đó là **lỗi resolution**, không phải bằng chứng transitivity thất bại.

### 6.2. Các artifacts dự kiến

```text
helper/target/classpath-helper-1.0.0.jar
facade/target/classpath-facade-1.0.0.jar
app/target/classpath-app-1.0.0.jar
app/target/surefire-reports/
```

JAR của app **không tự chứa bytecode từ helper hay facade**. Một Maven JAR chuẩn thường chỉ chứa classes/resources của module app. Thư viện bắc cầu nằm trong **những JAR tách biệt**, trừ khi bạn chủ động dùng Shade/Assembly/packaging cơ chế khác.

### 6.3. Chạy bằng classpath thư mục target — Linux/macOS

```bash
java -cp "app/target/classes:facade/target/classes:helper/target/classes" \
  com.example.transitive.app.Main
```

### 6.4. Chạy bằng classpath thư mục target — Windows

```powershell
java -cp "app/target/classes;facade/target/classes;helper/target/classes" `
  com.example.transitive.app.Main
```

Dấu phân tách classpath:
- Linux/macOS: dấu hai chấm `:`;
- Windows: dấu chấm phẩy `;`.

**Stdout chính xác của Java Main:**

```text
Hello, MAVEN!
Transitive API: JAVA
```

Đây là output của chương trình, **không phải toàn bộ Maven build log**. Java version được chọn để chạy phải tương thích bytecode mà Compiler Plugin tạo.

### 6.5. Vì sao lệnh chạy phải liệt kê đủ ba modules?

`Main.class` ở `app/target/classes`. `GreetingService.class` ở `facade/target/classes`. `TextNormalizer.class` ở `helper/target/classes`.

Khi JVM đọc bytecode, nó có thể tìm class từ các entries trên **runtime classpath**. `app` có khai báo dependency trong POM không phải là thông tin mà lệnh `java -cp` tự đọc; Java launcher không tự đọc `pom.xml`.

**Reactor build thành công chỉ nói Maven compiler/test runner đã dùng classpath thích hợp trong build.** Khi tự chạy ứng dụng, bạn phải thiết lập runtime classpath bằng JARs, class folders, launcher hoặc package mode tương ứng.

## 7. Đọc dependency:tree và phân biệt direct/transitive

Maven Dependency Plugin cung cấp goal `tree`. Sau khi đã `mvn clean install` từ root, chạy:

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
```

Điểm quan trọng: `-f app/pom.xml` chọn **project app**, Maven vẫn resolve parent qua `../pom.xml`; các artifacts helper/facade đã được install vào local repository ở bước trước.

Dữ liệu mô tả gọn, **minh họa các nhánh liên quan**, không giả mạo full output:

```text
com.example.transitive:classpath-app:jar:1.0.0
+- com.example.transitive:classpath-facade:jar:1.0.0:compile
|  \- com.example.transitive:classpath-helper:jar:1.0.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.11.4:test
   \- ... các JUnit test dependencies khác ...
```

Đọc từng dòng:
- `classpath-app` là root project của tree.
- `classpath-facade` nằm **ngay dưới app**: direct compile dependency.
- `classpath-helper` nằm **dưới facade**: transitive compile dependency.
- `junit-jupiter` nằm ngay dưới app: direct **test** dependency.
- Những artifact JUnit transitive khác cũng có thể xuất hiện ở test branch; không phải lỗi hay thư viện main runtime.

Một dependency có thể xuất hiện trong `tree` nhưng **không có trên classpath bạn đang hỏi tới**, ví dụ JUnit test artifacts không đi vào production runtime classpath.

### 7.1. Dùng scope filter

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree \
  -Dscope=compile
```

Thử `-Dscope=runtime` và `-Dscope=test` để hiểu dependency tree có lọc theo scope. Tuy nhiên **tree scope filter không phải bằng chứng tuyệt đối về thứ tự JAR trên JVM classpath**. Để quan sát danh sách file thực tế, làm mục 8.

### 7.2. Dùng verbose để thấy các node bị bỏ qua

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree \
  -Dverbose=true
```

Trong Maven Dependency Plugin 3.10.0, `verbose` cho phép thể hiện những node bị bỏ qua vì version conflict/duplicate, tùy tree. **Không sử dụng output của một goal `tree` phiên bản cũ rồi áp dụng nguyên cách diễn giải cho mọi version**.

### 7.3. Xuất cây dưới dạng file có cấu trúc

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree \
  -DoutputType=json -DoutputFile=target/dependency-tree.json
```

Dependency Plugin từ phiên bản 3.7.0 đã hỗ trợ JSON output. File được tạo dưới project app nếu đường dẫn tương đối được resolve theo project basedir. Hữu ích cho CI analysis/diff, nhưng schema/tree representation cũng cần được kiểm trên version thực.

## 8. Xuất runtime classpath thật bằng Maven Dependency Plugin

`dependency:tree` mô tả **graph**; `dependency:build-classpath` xuất **các đường dẫn JAR từ local Maven repository**.

Sau khi install reactor:

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:build-classpath \
  -DincludeScope=runtime \
  -Dmdep.outputFile=target/runtime-classpath.txt
```

**Đây là lệnh của plugin Dependency 3.10.0**. `includeScope=runtime` theo documentation bao gồm dependencies với scope hiệu dụng `compile` **và** `runtime`, nhưng không gồm những `test`-only dependencies. `mdep.outputFile` lưu classpath text vào file.

Đọc trên Linux/macOS:

```bash
cat app/target/runtime-classpath.txt
```

Hoặc Windows PowerShell:

```powershell
Get-Content -Raw "app/target/runtime-classpath.txt"
```

**Kết quả minh họa trên Linux, rút gọn cho dễ đọc:**

```text
/home/student/.m2/repository/com/example/transitive/classpath-facade/1.0.0/classpath-facade-1.0.0.jar:/home/student/.m2/repository/com/example/transitive/classpath-helper/1.0.0/classpath-helper-1.0.0.jar
```

Thứ tự entries và đường dẫn local repository thật có thể khác; không hard-code `/home/student`. Trên Windows, đường dẫn sử dụng dấu `\` và các entries phân cách bằng `;`.

**Quan sát cần rút ra:**
- Cả **facade JAR** và **helper JAR** đều được đưa vào runtime dependency classpath.
- JUnit test-only JARs không nằm trong runtime classpath đã lọc.
- File này **không tự chứa `app/target/classes`**: vì goal xuất dependency artifacts, **không phải** toàn bộ launcher classpath của ứng dụng.

### 8.1. Dùng classpath export để chạy thật — Linux/macOS

```bash
CP="$(cat app/target/runtime-classpath.txt)"
java -cp "app/target/classes:$CP" com.example.transitive.app.Main
```

**Stdout kỳ vọng:**

```text
Hello, MAVEN!
Transitive API: JAVA
```

Câu lệnh này khác mục 6: thay vì liệt kê `facade/target/classes` và `helper/target/classes`, ta dùng **các JAR đã install** trong local repo mà Dependency Plugin vừa xuất ra. Hai cách là **hai cách dựng runtime classpath hợp lệ**.

### 8.2. Dùng classpath export để chạy thật — PowerShell

```powershell
$cp = (Get-Content -LiteralPath "app/target/runtime-classpath.txt" -Raw).Trim()
java -cp ("app/target/classes;" + $cp) com.example.transitive.app.Main
```

Vì PowerShell cần nối chuỗi bằng `+`, đây là một lời gọi Java thực. Không chép nguyên dấu `:` từ ví dụ Linux vào Windows.

### 8.3. So compile, runtime và test classpath

Có thể xuất thêm:

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:build-classpath \
  -DincludeScope=compile \
  -Dmdep.outputFile=target/compile-classpath.txt

mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:build-classpath \
  -DincludeScope=test \
  -Dmdep.outputFile=target/test-classpath.txt
```

Với demo:
- **Compile:** facade + helper; JUnit test-only không có.
- **Runtime:** facade + helper; JUnit test-only không có.
- **Test:** facade + helper + JUnit và các phụ thuộc test liên quan.
- **Provided** sẽ vào compile/test nhưng **không** có ở runtime.
- **Runtime-only** sẽ vào runtime/test nhưng **không** có ở main compile.

**Đây là dependency-artifact path export, không phải toàn bộ compiler/test runner classpath của từng plugin.** Surefire còn dùng `app/target/test-classes`, `app/target/classes`, provider/launcher dependencies và classloader setup riêng. Để chứng minh classpath của một JVM test cụ thể, cần quan sát cấu hình/logs của Surefire/JVM thực.

### 8.4. Tại sao không dùng effective POM làm “classpath”?

`help:effective-pom` cho biết model đã merge parent/profiles/config, nhưng không cho ra danh sách resolved JAR files dùng khi Java launcher chạy. `dependency:tree` cho biết resolved graph; `dependency:build-classpath` xuất paths; `java -cp` mới là classpath **đã được bạn đưa cho JVM thực**.

Ba thứ có ý nghĩa khác nhau và cần được đối chiếu đúng.

## 9. Cố tình làm thiếu helper trong runtime classpath

Để hiểu vì sao “Maven thấy dependency” không đủ, thử trên Linux/macOS:

```bash
java -cp "app/target/classes:facade/target/classes" \
  com.example.transitive.app.Main
```

**Không có `helper/target/classes` hoặc helper JAR**.

Điều có thể xảy ra:
- JVM tìm được Main và GreetingService;
- Khi `GreetingService.hello()` gọi `TextNormalizer.upper(...)`, JVM không nạp được `TextNormalizer`;
- Process kết thúc với `NoClassDefFoundError` (thường kèm `ClassNotFoundException` làm nguyên nhân).

Thông điệp điển hình:

```text
java.lang.NoClassDefFoundError:
    com/example/transitive/helper/TextNormalizer
```

**Đây là phần lỗi minh họa**, stacktrace đầy đủ/line numbers có thể khác tùy JDK và cách chạy. Program có thể fail trước khi in dòng `Hello, MAVEN!`, vì lời gọi helper xảy ra trước khi dòng đầu được ghi.

**Bài học:** Maven giúp resolve transitive dependencies **trong các goals của Maven**. Khi tự chạy một process Java bằng `java -cp`, không có phép màu tự động đọc POM. Nếu chạy không dùng các paths mà Maven đã resolve, bạn có thể gặp `ClassNotFoundException`/`NoClassDefFoundError` dù Maven build/test đều thành công.

### 9.1. Khác biệt ClassNotFoundException và NoClassDefFoundError

- **ClassNotFoundException** thường xảy ra khi code/classloader chủ động yêu cầu nạp một class theo tên, ví dụ `Class.forName("...")`, nhưng classloader không tìm được.
- **NoClassDefFoundError** là `LinkageError` xuất hiện khi JVM cần definition của một class từng được biết đến lúc compile/link nhưng không tìm hoặc không thể định nghĩa được trong runtime; có thể có `ClassNotFoundException` làm cause.

Không áp dụng kết luận “thiếu JAR” cho mọi `NoClassDefFoundError`: nó cũng có thể xuất hiện do lỗi initialization của class hoặc classloader isolation. Kiểm đầy đủ stacktrace/cause trước khi sửa POM.

## 10. Dùng dependency:analyze để phát hiện “used undeclared”

Maven Dependency Plugin có goal `dependency:analyze`: phân tích bytecode/test bytecode để tìm:
- **Used declared**: code dùng artifact đã khai báo trực tiếp.
- **Used undeclared**: code dùng class từ artifact không khai báo trực tiếp.
- **Unused declared**: artifact được khai báo nhưng analyzer không phát hiện sử dụng tĩnh.

Sau khi build/install reactor, chạy:

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:analyze
```

Với app demo, vì `Main` và `MainTest` **import TextNormalizer trực tiếp**, một mục cảnh báo đáng chú ý sẽ là:

```text
Used undeclared dependencies found:
   com.example.transitive:classpath-helper:jar:1.0.0:compile
```

Đây là **nội dung báo cáo minh họa dạng rút gọn**. Goal có thể in thêm warnings về các JUnit aggregator/transitive artifacts vì analyzer nhìn ở **mức bytecode**, không hiểu hoàn toàn reflection, service loaders, code generation, annotation processing hoặc toàn bộ runtime behavior.

**Không chạy `dependency:analyze` rồi xóa tất cả dependencies báo unused một cách mù quáng.** Một dependency có thể được dùng qua reflection, `ServiceLoader`, configuration, JNI hoặc resource loading. Xác minh trước khi xóa.

### 10.1. Tại sao “dùng được từ transitive” vẫn là một lỗi thiết kế?

Giả sử version mới của facade đổi implementation:
- Facade không còn dùng helper; nó xóa dependency helper;
- App source **vẫn import TextNormalizer**;
- Maven app không còn nhận helper transitively;
- App compile fail dù app `pom.xml` không thay.

**Vì app trực tiếp tham chiếu public class từ helper, app nên khai báo helper trực tiếp.** Đây là khuyến nghị ngay trong Apache Maven Dependency Mechanism Guide.

Phụ thuộc bắc cầu vẫn rất hữu ích: một thư viện nội bộ có thể gọi private implementation dependencies mà consumer không cần biết. Quy tắc là **khai báo trực tiếp dependencies mà chính source của module sử dụng trực tiếp**, không phải viết lại mọi transitive dependency vào POM.

## 11. Sửa POM app: biến helper thành direct dependency

Trong `app/pom.xml`, thêm **một dependency** vào `<dependencies>` hiện có:

```xml
<dependency>
    <groupId>com.example.transitive</groupId>
    <artifactId>classpath-helper</artifactId>
    <version>${project.version}</version>
</dependency>
```

**Đây là XML fragment, không phải POM độc lập.** Không xóa facade hoặc JUnit khi thêm.

Sau sửa, phần dependencies app tương đương:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.transitive</groupId>
        <artifactId>classpath-facade</artifactId>
        <version>${project.version}</version>
    </dependency>
    <dependency>
        <groupId>com.example.transitive</groupId>
        <artifactId>classpath-helper</artifactId>
        <version>${project.version}</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
```

Bây giờ `facade` và `helper` đều là **direct dependencies của app**. Maven có thể vẫn ghi một đường transitive trùng dưới facade trong verbose tree, nhưng chọn một artifact version cho classpath theo rules, **không nạp hai bản `helper-1.0.0.jar` chỉ vì có hai đường đi giống nhau**.

### 11.1. Build, đọc lại tree và analysis

```bash
mvn -B -ntp clean install

mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree \
  -Dverbose=true

mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:analyze
```

Đối với helper, mục **used undeclared** đã có lý do để biến mất, vì app hiện khai báo trực tiếp helper. Có thể còn warnings không liên quan (đặc biệt các artifacts JUnit), phải xét theo source usage và analyzer limitations.

### 11.2. So classpath trước/sau

Dù POM đã thêm helper direct, **runtime classpath cần cùng artifact `helper:1.0.0`**, không phải có thêm một bản helper khác, vì version hiện tại như nhau.

Sơ đồ trước:

```text
app
└── facade:1.0.0
    └── helper:1.0.0
```

Sơ đồ sau:

```text
app
├── facade:1.0.0
│   └── helper:1.0.0 (omitted for duplicate nếu verbose tree thể hiện)
└── helper:1.0.0 (direct)
```

**Điều thay đổi là tính tường minh và độ bền của dependency contract**, không nhất thiết là tập JAR được Java nạp. Nếu facade bỏ helper trong tương lai, app vẫn resolve helper trực tiếp.

## 12. Scope propagation quyết định classpath nào chứa JAR

Maven có những scopes quan trọng:

| Scope trong app | Main compile | Test compile/run | Runtime | Có truyền tiếp sang consumer? |
| --- | --- | --- | --- | --- |
| `compile` | Có | Có | Có | Có, theo rules |
| `provided` | Có | Có | Không | Không theo cách transitive thông thường |
| `runtime` | Không | Có | Có | Có, theo rules |
| `test` | Không | Có | Không | Không |
| `system` | Có | Có | Tùy môi trường/path | Không; nên tránh |
| `import` | Không phải classpath scope | Chỉ cho BOM POM trong dependencyManagement | Không phải JAR trực tiếp | N/A |

Ở bảng, “Có” xét dependency **trực tiếp** với scope đó trong project đang xem. Với transitive dependency, scope kết quả phụ thuộc **cả scope của cạnh đầu tiên lẫn scope của dependency bên trong**.

### 12.1. Bảng lan truyền scopes (rút gọn từ Maven Guide)

Giả sử `app` phụ thuộc `facade` với scope ở cột trái, còn `facade` phụ thuộc `helper` với scope ở cột trên:

| Scope của app → facade | helper compile | helper provided | helper runtime | helper test |
| --- | --- | --- | --- | --- |
| `compile` | `compile` | Bỏ | `runtime` | Bỏ |
| `provided` | `provided` | Bỏ | `provided` | Bỏ |
| `runtime` | `runtime` | Bỏ | `runtime` | Bỏ |
| `test` | `test` | Bỏ | `test` | Bỏ |

Từ đây:
- `app → facade:compile`, `facade → helper:compile` → helper ở **compile/test/runtime** của app.
- `app → facade:compile`, `facade → helper:runtime` → helper ở **runtime/test**, không ở main compile.
- `app → facade:compile`, `facade → helper:provided` → helper bị **bỏ khỏi transitive dependencies** của app.
- `app → facade:test`, `facade → helper:compile` → helper là test-only trong app.

**Không chỉ đọc `<scope>` của helper ở POM facade rồi kết luận scope trong app.** Phải theo cả chuỗi cạnh và mediation rules.

### 12.2. Provided scope không phải “runtime magically downloads”

`provided` nghĩa là compile/test thấy artifact, nhưng runtime môi trường khác **phải cung cấp** nó, ví dụ servlet container cung cấp Servlet API. Nếu chạy `java -cp` không có JAR đó thì class vẫn thiếu. `provided` không tự cài dependency lên máy server.

### 12.3. Runtime scope không thể compile code trực tiếp import API

Nếu bạn đổi app `classpath-helper` direct từ compile sang runtime trong khi `Main` trực tiếp import `TextNormalizer`, compiler có thể báo package/class not found nếu không có đường compile khác. Đây là **thí nghiệm scope**, không phải cách sửa dependency contract.

## 13. Optional và exclusions: phụ thuộc có thể biến mất

### 13.1. Optional dependency

Trong `facade/pom.xml`, nếu sửa helper thành:

```xml
<dependency>
    <groupId>com.example.transitive</groupId>
    <artifactId>classpath-helper</artifactId>
    <version>${project.version}</version>
    <optional>true</optional>
</dependency>
```

Facade **vẫn compile được** vì trong chính module facade nó có dependency helper. Nhưng một app phụ thuộc facade **không tự nhận helper transitively** qua cạnh optional.

Nếu app **chưa** khai báo helper direct và `Main` import `TextNormalizer`, build app có thể fail. Nếu đã thêm direct helper như mục 11, app vẫn có helper vì chủ động khai báo.

Đây là ví dụ mô phỏng để hiểu optional. **Không đánh dấu helper optional trong một library thực nếu facade public behavior luôn cần helper ở runtime** mà chưa thiết kế cách cung cấp implementation tương ứng.

### 13.2. Exclusions

Nếu app muốn loại helper khỏi đường đi qua facade, có thể viết:

```xml
<dependency>
    <groupId>com.example.transitive</groupId>
    <artifactId>classpath-facade</artifactId>
    <version>${project.version}</version>
    <exclusions>
        <exclusion>
            <groupId>com.example.transitive</groupId>
            <artifactId>classpath-helper</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

**Đây là một replacement fragment cho dependency facade**, không phải POM đầy đủ. Nếu app **không có direct helper** thì `Main` compile có thể fail vì import helper; nếu app có direct helper thì exclusion tại nhánh facade không gỡ helper direct.

**Exclusion áp dụng ở đường đi cụ thể**, không phải lệnh cấm toàn cục một artifact ở mọi nhánh. Một đường khác vẫn có thể mang helper vào graph. Sau exclusion cần chạy `dependency:tree`, tests và runtime smoke test; không dùng exclusion để “fix CVE” nếu ứng dụng vẫn yêu cầu class của version cũ mà không có lựa chọn tương thích.

## 14. Dependency mediation: version nào thật sự thắng?

Trong thực tế graph có thể có nhiều version của cùng GAV:

```text
app
├── library-a
│   └── common-util:1.2.0
└── library-b
    └── adapter-x
        └── common-util:2.0.0
```

Hai đường đi tới `common-util` có độ sâu khác nhau:
- `app → library-a → common-util` là độ sâu 2.
- `app → library-b → adapter-x → common-util` là độ sâu 3.

Maven chọn **nearest definition**, nên trong ví dụ khái niệm này version **1.2.0** thắng, không phải version cao nhất **2.0.0**.

Nếu có hai đường tới `common-util` **cùng độ sâu**, theo Maven Guide, cạnh được khai báo **trước trong POM** có thể quyết định version thắng. Không dùng thứ tự trong `~/.m2` hay “newer always wins” để đoán.

**Đây chỉ là đồ thị khái niệm**, không phải POM của demo Java 17. Các artifacts `library-a`, `common-util` ở đây không cần tồn tại.

### 14.1. Khai báo direct để kiểm soát và thể hiện contract

Nếu app cần version `2.0.0` tương thích, có thể khai báo direct `common-util:2.0.0`, làm đường đi app → common-util có độ sâu 1. Nhưng phải kiểm API/runtime compatibility trước khi ép version, nhất là khi `library-a` được compile dựa trên API 1.x.

### 14.2. DependencyManagement khác thêm dependency

Trong root parent hoặc BOM, `<dependencyManagement>` quản lý version/scope/exclusions cho những dependency được dùng. Nó **không tự đưa một thư viện lên classpath**.

Ví dụ fragment quản lý version helper:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.transitive</groupId>
            <artifactId>classpath-helper</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Fragment minh họa trên chỉ có một entry; trong root POM đầy đủ của bài đã có `dependencyManagement` cho JUnit, nên **thêm entry vào cùng `<dependencies>` hiện có thay vì tạo hai khối `dependencyManagement`**.

Nếu source của app dùng `TextNormalizer` trực tiếp, app vẫn nên có **dependency direct**. DependencyManagement giúp quản lý version, không thay lời khai báo “app sử dụng helper”.

### 14.3. BOM import không nằm trên runtime classpath

BOM thường là POM import qua:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-bom</artifactId>
    <version>1.0.0</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>
```

**Đây là fragment minh họa đặt trong `<dependencyManagement><dependencies>`**, không phải dependency thường bên ngoài. BOM `import` cung cấp version management, **không phải một JAR Java có class để runtime nạp**.

## 15. Vì sao classpath thật khác giữa Maven compile và Java run?

### 15.1. Trong Maven compiler

Compiler Plugin nhận source roots, dependency artifacts phù hợp compile scope, compiler options/JDK target và có thể module path/annotation processor path riêng. Maven tự điều phối **classpath của goal**, người dùng không cần viết tất cả JARs ở shell.

### 15.2. Trong Surefire/Failsafe

Test classpath có thể chứa:
- `target/test-classes`;
- `target/classes`;
- Dependencies với scope `test`, `compile`, `runtime` và `provided` theo scope rules;
- Các provider/launcher classes do test plugin quản lý;
- Các JVM fork/classloader options.

**Đừng kết luận chính xác mọi entry trên test JVM classpath chỉ bằng `dependency:build-classpath -DincludeScope=test`.** Đây là dependency-artifact view; Surefire còn quản lý classes directories và provider process.

### 15.3. Trong `java -cp`

Java launcher chỉ nhận entries mà bạn cung cấp. Nếu app JAR được tạo bởi Maven JAR Plugin chuẩn, dependency transitive **không tự được nhúng vào bên trong JAR**. Có thể cần:
- `java -cp "app.jar:facade.jar:helper.jar" Main`;
- Plugin hỗ trợ packaging/executable distribution;
- Framework launcher;
- Maven exec goal;
- Class-Path manifest đã cấu hình; hoặc
- Uber/fat JAR được tạo bởi Shade/Assembly khi thực sự cần.

Không nên nhầm **dependencies resolved trong Maven** với **classpath trong Docker image, server startup script hay Java process thực tế**. Khi runtime fail, hãy kiểm command/process/container đang dùng chứ không chỉ POM.

### 15.4. JPMS module path

Ví dụ dùng classpath truyền thống, không có `module-info.java`. Java 9+ có **module path** và Maven plugins có thể xử lý JPMS khác với classpath. Khi project dùng named modules, cần kiểm module graph, module names và compiler/test runtime options; không áp nguyên mẫu `-cp` của bài vào project JPMS mà không điều chỉnh.

## 16. Những lệnh giúp biết classpath của project nào

Từ reactor root:

```bash
mvn -B -ntp -pl :classpath-app -am clean verify
```

`-pl :classpath-app` chọn App module; `-am` build các required upstream projects trong cùng reactor. Hữu ích khi chưa cài helper/facade vào local repository và muốn build cùng source.

**Nhưng sau lệnh `verify` chưa chắc app POM chạy standalone với `dependency:tree` sẽ resolve được các sibling JARs từ repository local.** Các thí nghiệm `-f app/pom.xml` trong mục 7–10 yêu cầu bạn đã chạy `mvn clean install` trước, hoặc có repository chứa artifacts tương ứng.

### 16.1. Ba chế độ kiểm phổ biến

| Câu hỏi | Lệnh/phép kiểm |
| --- | --- |
| App direct/transitive dependency nào được chọn? | `mvn -f app/pom.xml dependency:tree` |
| App runtime dependency JAR paths là gì? | `dependency:build-classpath -DincludeScope=runtime` |
| Code app có trực tiếp dùng dependency chưa khai báo? | `dependency:analyze` |
| Tại sao class thiếu khi chạy Java? | In `java -cp`, kiểm paths/file có thật, stacktrace |
| Maven plugin nào xây classpath? | Compiler/Surefire Plugin configuration, build INFO/debug log |
| Module nào phải build trước? | Reactor Summary/dependency graph |
| Version nào thắng conflict? | `dependency:tree -Dverbose=true`, effective management |
| Artifact được cài local chưa? | `mvn install`, kiểm đúng local repo/GAV |

Nếu `mvn -f app/pom.xml dependency:tree` fail vì chưa tìm sibling artifacts nhưng full reactor `verify` pass, **đó có thể chỉ là khác biệt giữa reactor resolution và local repository availability**. Không sửa `scope=system` hoặc hard-code absolute JAR paths để che lỗi.

## 17. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| App compile được dù thiếu helper direct | Helper transitive qua facade | Khai báo helper direct nếu import API |
| App compile fail sau khi facade upgrade | Facade bỏ/đổi helper dependency | Khôi phục direct helper theo contract |
| `NoClassDefFoundError` khi `java -cp` | Thiếu helper JAR/classes ở runtime | Dùng đúng runtime paths |
| `ClassNotFoundException` khi reflection | Classloader/Classpath thiếu class theo tên | Kiểm process launcher và artifact |
| Unit tests pass, `java` fail | Surefire có test classpath đầy đủ, runtime launcher thiếu JAR | So test vs runtime classpaths |
| `dependency:tree` có JUnit | JUnit thuộc test scope | Không coi nó là runtime dependency |
| Runtime-only library không compile được khi import | `runtime` không có ở main compile | Dùng compile scope nếu source import |
| Container không cung cấp provided dependency | `provided` bị loại khỏi app runtime classpath | Kiểm container/server classpath |
| Optional helper biến mất ở app | Facade đánh dấu helper optional | Declare helper direct nếu cần |
| Exclusion gây fail | Đã loại artifact đang được code dùng | Bỏ exclusion hoặc thay dependency hợp lệ |
| Conflict chọn version “cũ hơn” | Nearest definition/tie-first | Xem tree và version mediation |
| BOM xuất hiện nhưng class vẫn thiếu | BOM chỉ quản lý versions | Khai báo real dependency |
| `dependency:analyze` báo used undeclared | App import helper transitively | Thêm helper direct |
| Analyzer báo unused nhưng code dùng reflection | Bytecode analyzer hạn chế | Review động và test thực tế |
| `build-classpath` không thấy `app/target/classes` | Goal chỉ in dependency artifacts | Tự thêm classes dir khi chạy |
| `build-classpath` fail khi chạy app standalone | Sibling artifacts chưa install | Chạy reactor install trước |
| Lệnh Unix chạy trên Windows lỗi | Dùng `:` thay `;` trong classpath | Dùng PowerShell/Windows syntax |
| Thấy JAR trong `.m2` nhưng Java vẫn fail | JVM không tự đọc local Maven repo | Thêm JAR path vào `-cp` |
| Tạo JAR nhưng không `java -jar` được | Chưa cấu hình Main-Class/packaging | Dùng `java -cp` hoặc packaging phù hợp |
| Hai version cùng artifact ở graph | Mediation và omitted nodes | Đọc verbose tree, không giả định latest wins |
| `DependencyResolutionException` | Sai GAV/repo/network/auth | Kiểm Maven repositories/settings, không sửa Java classpath mù |
| Plugin classpath khác project | Plugins có dependencies riêng | Không nhầm plugin resolution với app runtime |

### Debug theo thứ tự hiệu quả

1. Ghi source commit, `mvn -version`, Java version.
2. Đọc dependency của đúng **project app**, không phải root aggregator nếu đang hỏi app.
3. Chạy `dependency:tree` (thêm verbose nếu có conflict/omission).
4. Xác nhận scopes trên từng cạnh và optional/exclusions.
5. Chạy `dependency:build-classpath -DincludeScope=runtime` sau khi dependencies có trong local repo.
6. Kiểm file JARs trên đường dẫn có thật.
7. Chạy `java -cp` với classpath đã xuất + classes của app.
8. Nếu fail, phân biệt resolver error, compile error, runtime linkage/initialization.
9. Chạy `dependency:analyze` để tìm imports của undeclared dependencies.
10. Thêm direct dependency đúng nơi, không tùy tiện chép mọi transitive vào app.
11. Chạy clean build/tests và runtime smoke test.
12. Ghi rõ graph, scope, selected versions và thực tế `-cp`.

## 18. Bài tập nâng cao

### Bài 1 — Đọc cây hiện tại

Từ tree `app → facade:compile → helper:compile`, xác định:
- Direct dependencies của app?
- Transitive dependency?
- Helper có trên compile, test, runtime classpaths không?

**Đáp án:** facade direct; helper transitive; helper hiệu dụng compile nên có ở cả ba. JUnit của app là một **direct test dependency**, chỉ có ở test classpath.

### Bài 2 — Dự đoán stdout

Code Main gọi GreetingService và TextNormalizer. Với đúng classpath, output:

```text
Hello, MAVEN!
Transitive API: JAVA
```

Không thêm khoảng trắng thừa hoặc dấu chấm. Đây là output của Java code ở mục 5, không phải Maven build log.

### Bài 3 — Bỏ helper khỏi Java runtime

Chạy `java -cp` không gồm `helper/target/classes`. Dự đoán điều xảy ra.

**Đáp án:** `NoClassDefFoundError` hoặc một linkage error có liên quan khi runtime cần TextNormalizer. Cần xem cause để chắc chắn đúng artifact bị thiếu.

### Bài 4 — Facade chuyển helper thành optional

App chưa khai báo helper. `Main` vẫn import helper. Dự đoán điều gì sẽ thay đổi.

**Đáp án:** helper không tự lan tới app, nên app compile có thể fail. Nếu app khai báo helper direct thì vẫn có helper.

### Bài 5 — Runtime scope

Facade chuyển helper scope sang `runtime` nhưng source facade vẫn import TextNormalizer. Facade còn compile được không?

**Đáp án:** không có helper ở main compile classpath của facade từ cạnh runtime này, nên compile sẽ fail trừ khi có một compile path khác.

### Bài 6 — Dependency mediation

App nhận `common-util:1.2.0` ở depth 2 và `common-util:2.0.0` ở depth 3. Chọn version nào?

**Đáp án:** 1.2.0 theo nearest definition. Nếu equal depth, first declaration wins theo rules; không phải latest wins.

### Bài 7 — BOM import

BOM quản lý `helper:1.0.0`. App không khai báo helper và không nhận helper từ transitive branches. App có helper JAR không?

**Đáp án:** không. DependencyManagement/BOM quản lý version, **không tự thêm dependency**.

### Bài 8 — Used undeclared

App source import TextNormalizer trực tiếp, nhưng chỉ khai báo facade. `dependency:analyze` có thể cảnh báo gì?

**Đáp án:** helper là `used undeclared`. Sửa bằng khai báo helper direct và test lại.

### Bài 9 — Test-only dependency

Thử import `org.junit.jupiter.api.Test` trong `src/main/java` mà app chỉ có JUnit test scope. Có compile không?

**Đáp án:** JUnit test scope không ở main compile classpath; code main import nó có thể fail. Không đổi JUnit thành compile chỉ để tránh cấu trúc tests không đúng.

### Bài 10 — Tạo runtime classpath bằng Maven

Chạy `dependency:build-classpath` với `includeScope=runtime`. Vì sao file output không có `app/target/classes`?

**Đáp án:** plugin xây dependency-artifact paths, không tự là đầy đủ classpath Java launcher. Phải nối classes dir của project.

### Bài 11 — Khác biệt Maven reactor vs standalone app

Build root `mvn clean verify` thành công, nhưng `mvn -f app/pom.xml dependency:build-classpath` fail vì không có facade/helper JARs trong local repo. Làm sao sửa?

**Đáp án:** từ root chạy `mvn clean install` để install sibling artifacts; hoặc giữ build và resolution trong reactor phù hợp.

### Bài 12 — Sửa đúng thiết kế

Sau khi thêm helper direct vào app, helper JAR có bắt buộc xuất hiện hai lần trong runtime classpath không?

**Đáp án:** không. Maven mediation/duplicate omission tạo tập selected artifacts; đổi declaration path không tự tạo hai copies cùng version.

### Bài 13 — Scope matrix

App có facade compile, facade có helper runtime. Helper ở classpaths nào của app?

**Đáp án:** helper hiệu dụng runtime; nằm trên app runtime/test, không trên main compile. Nếu app code trực tiếp import helper, cần direct compile dependency.

### Bài 14 — Plugin dependency

Nếu một Maven plugin cần helper JAR để chạy goal, có phải helper tự có trong app runtime classpath không?

**Đáp án:** không. Build plugin dependency classloader khác project dependency classpath.

## 19. Mẫu báo cáo thực hành

Sau khi tự chạy trên máy, báo cáo nên có:

| Mục | Bằng chứng cần ghi |
| --- | --- |
| Environment | Maven/JDK/OS/version |
| Source | Commit/revision hoặc folder snapshot |
| Project root | `classpath-lab` |
| Direct graph | app → facade; app → junit-jupiter(test) |
| Transitive graph | app → facade → helper |
| Effective helper scope | compile |
| Build result | Reactor success, ba JUnit tests success |
| Actual runtime classpath | `build-classpath` output + app classes dir |
| Java stdout | Hai dòng đã xác định |
| Missing-class experiment | NoClassDefFoundError và class bị thiếu |
| `dependency:analyze` trước sửa | helper used undeclared (kỳ vọng) |
| POM thay đổi | thêm helper direct vào app |
| `dependency:tree` sau sửa | helper direct, duplicate transitive route omitted |
| Runtime sau sửa | Cùng hai dòng stdout |
| Giới hạn kết luận | Local demo, không tự phản ánh mọi project có classifier/JPMS |

**Đừng ghi một checksum hoặc đường dẫn JAR cụ thể như một dữ kiện thực** nếu chưa chạy trên máy tương ứng. Những path trong bài là minh họa.

## 20. Checklist cuối bài

- [ ] Tạo đúng root, helper, facade và app POMs.
- [ ] Đặt đúng Java source theo package và filename.
- [ ] Biết vì sao `<modules>` khác `<dependencies>`.
- [ ] Chạy `mvn -B -ntp clean install` thành công.
- [ ] Xác minh ba JUnit tests của app.
- [ ] Đọc `dependency:tree` của đúng app module.
- [ ] Chỉ ra facade là direct, helper là transitive trong bản đầu.
- [ ] Giải thích `compile → compile` truyền helper.
- [ ] Phân biệt compile/test/runtime classpaths.
- [ ] Xuất `build-classpath` với `includeScope=runtime`.
- [ ] Biết file xuất không bao gồm `app/target/classes`.
- [ ] Chạy Main với classpath đủ: stdout đúng hai dòng.
- [ ] Bỏ helper khỏi classpath và hiểu lỗi nạp class.
- [ ] Chạy `dependency:analyze`; hiểu giới hạn bytecode analysis.
- [ ] Thêm dependency trực tiếp helper trong app POM.
- [ ] Chạy lại tree/analyze, đối chiếu duplicate omitted.
- [ ] Không thêm tất cả transitive dependencies vô tội vạ.
- [ ] Biết nearest definition và tie-first khi conflict.
- [ ] Biết optional/exclusions có thể làm helper biến mất.
- [ ] Biết BOM/dependencyManagement chỉ quản lý versions.
- [ ] Biết plugin classpath và Java runtime classpath khác nhau.
- [ ] Nêu được những khác biệt Maven reactor vs local repository.
- [ ] Không nhầm JAR packaging chuẩn với fat JAR.
- [ ] Ghi điều kiện và bằng chứng trước khi kết luận.

**Kết luận:** Một module có thể compile thành công nhờ **phụ thuộc bắc cầu**: `app → facade → helper`. Maven tự đọc POM của facade và đưa helper vào selected dependency graph/classpaths theo scope rules. Tuy vậy, khi chạy `java -cp`, JVM chỉ nhìn các thư mục/JAR bạn thực sự đưa vào runtime. `dependency:tree` giải thích **vì sao helper được chọn**; `dependency:build-classpath` cho biết **các JAR dependency nằm ở đường dẫn nào**; phép chạy Java xác minh **runtime classpath có đủ không**. Nếu source app trực tiếp dùng `TextNormalizer`, hãy **khai báo helper trực tiếp trong app** để dependency contract bền vững, dù transitive vẫn có thể làm code chạy hôm nay.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Maven Dependency Plugin Goals](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Apache Maven Dependency Plugin 3.10.0 — dependency:tree](https://maven.apache.org/components/plugins-archives/maven-dependency-plugin-3.10.0/tree-mojo.html)
- [Apache Maven Dependency Plugin 3.10.0 — dependency:build-classpath](https://maven.apache.org/components/plugins-archives/maven-dependency-plugin-3.10.0/build-classpath-mojo.html)
- [Apache Maven Dependency Plugin — dependency:analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Surefire Plugin Documentation](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)