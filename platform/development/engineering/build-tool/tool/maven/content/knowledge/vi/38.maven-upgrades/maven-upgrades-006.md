# POM model `4.0.0`, model `4.1.0` và giới hạn tương thích khi nâng cấp Maven

## 1. Mục tiêu và kết luận cốt lõi

`<modelVersion>` trong `pom.xml` là **phiên bản mô hình dữ liệu của POM** mà Maven dùng để đọc, kiểm tra và xây project model. Nó **không phải** phiên bản Maven CLI đang chạy, phiên bản Java, phiên bản artifact hay phiên bản Maven Compiler Plugin.

Hai giá trị quan trọng khi chuyển từ Maven 3 sang Maven 4:

- **`4.0.0`**: mô hình POM được Maven 3 sử dụng lâu dài; **Maven 4 vẫn hiểu và build được** project dùng model này.
- **`4.1.0`**: mô hình build POM bổ sung các khả năng mới trong Maven 4, ví dụ `<subprojects>`, `root="true"`, suy luận thông tin parent và version của dependency giữa các subprojects, `packaging=bom`, nguồn source linh hoạt hơn. **Maven 3 không được thiết kế để build một source POM model `4.1.0`**.

Tại sao Maven 4 đưa ra `4.1.0` nhưng vẫn phải bảo vệ `4.0.0`? Vì hàng triệu artifacts, IDEs, repository managers và build tools khác cần đọc **POM được phát hành kèm artifact**. Maven 4 tách khái niệm **build POM** (source control, phục vụ build) khỏi **consumer POM** (metadata phục vụ dependency consumer). Consumer POM được tạo để duy trì khả năng sử dụng artifact qua những công cụ chưa hiểu source model mới; tuy nhiên cần **kiểm tra POM thực tế** và tính năng chuyển đổi hiện dùng, không hứa rằng mọi cấu hình `4.1.0` đều tương thích tự động.

Bài học gồm:

1. So sánh model `4.0.0` và `4.1.0` theo **cú pháp, runtime và phạm vi tương thích**.
2. Một Maven POM model `4.0.0` và Java 17/JUnit 5 project **đầy đủ**, dùng để kiểm Maven 3 và Maven 4.
3. Một **multi-project Maven 4 model `4.1.0`** gồm root, `api`, `app`, code Java 17, tests và output mong đợi.
4. Giải thích consumer POM, flattening, BOM, parent/subprojects inference, nguồn `sources`, profile và những ngoại lệ khi publish.
5. Migration theo từng chặng, test matrix, lệnh xác minh, lỗi thường gặp và checklist release.

**Nguyên tắc nâng cấp:** đừng đổi `<modelVersion>` chỉ vì nâng executable Maven. Hãy thử Maven 4 **với source POM `4.0.0` hiện có trước**, sau đó chỉ chuyển sang `4.1.0` khi thật sự cần tính năng mới và đã chấp nhận Maven 4 là yêu cầu đối với **người build source**.

## 2. Tách bốn loại “version” trước khi chẩn đoán

Một POM có thể chứa:

```xml
<modelVersion>4.0.0</modelVersion>
<groupId>dev.example</groupId>
<artifactId>library</artifactId>
<version>1.2.0</version>
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Đọc đúng ý nghĩa:

| Thông tin | Giá trị ví dụ | Quy định điều gì? |
| --- | --- | --- |
| Maven executable | Maven 3.9.x / Maven 4.x | Chương trình build, Maven core/resolver/lifecycle |
| POM model | `4.0.0` hoặc `4.1.0` | Schema và semantics của build POM |
| Artifact version | `1.2.0` | Phiên bản GAV đưa vào Maven repository |
| Java compiler release | `17` | Language/API/class-file target khi compile |

**Sai lầm:** “Đang chạy Maven 4 thì phải ghi `<modelVersion>4.1.0</modelVersion>`.” Không đúng. Maven 4 vẫn hỗ trợ POM model `4.0.0`; chỉ những **feature thuộc model mới** mới cần `4.1.0`.

Một sai lầm khác: model `4.1.0` **không phải** “Maven 4.1.0 executable”. Nó là **POM schema version**. Những tính năng đó được tài liệu hóa cho Maven 4.0.x; Maven CLI version phải được kiểm riêng bằng `mvn -version`.

### 2.1. Maven 4 yêu cầu Java nào?

Apache Maven 4 yêu cầu **Java 17 để chạy Maven**. Đây là yêu cầu đối với Maven process, không nhất thiết yêu cầu **source code của dự án** dùng Java 17. Compiler Plugin/Toolchains được cấu hình phù hợp vẫn có thể compile source target Java thấp hơn.

Ví dụ:

```text
Maven core JVM: Java 17+
Project compiler --release: 11
Application runtime target: Java 11
```

Cấu hình trên có thể hợp lệ nếu compiler/plugin/JDK thực tế hỗ trợ release 11 và dependencies của app tương thích Java 11. Ngược lại, Maven 3 chạy JDK 17 cũng hoàn toàn có thể compile Java 17.

### 2.2. XML namespace và XSD phải đồng bộ với model

Model 4.0.0:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    ...
</project>
```

Model 4.1.0:

```xml
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0
                             https://maven.apache.org/xsd/maven-4.1.0.xsd">
    <modelVersion>4.1.0</modelVersion>
    ...
</project>
```

Dấu `...` ở hai đoạn trên là **ký hiệu phần POM được lược bỏ**, **không phải XML để chạy nguyên xi**. Trong POM chạy được, thay bằng GAV và cấu hình hợp lệ; xem phần thực hành bên dưới. Không đổi mỗi `<modelVersion>` nhưng vẫn giữ namespace/XSD cũ rồi kết luận đã migrate model mới.

## 3. Ma trận tương thích cơ bản

| Maven build executable | Source build POM `4.0.0` | Source build POM `4.1.0` |
| --- | --- | --- |
| Maven 3.9.x | **Có**, nếu plugins/JDK phù hợp | **Không**: model mới ngoài phạm vi Maven 3 |
| Maven 4.x | **Có**, với plugin/configuration được kiểm tương thích | **Có**, với Maven 4 đủ feature và plugin support |

Cột này chỉ nói về **khả năng build trực tiếp từ source POM**; nó **không** bảo đảm artifact sau deploy đã có consumer POM đúng.

Ma trận thứ hai quan trọng không kém:

| Bên tạo artifact | POM đưa lên repository | Bên tiêu thụ |
| --- | --- | --- |
| Maven 3 + POM `4.0.0` | POM thông thường model `4.0.0` | Maven 3, Maven 4, Gradle/IDE phù hợp |
| Maven 4 + build POM `4.0.0` | Consumer POM theo cơ chế/flags Maven 4 | Phải thử consumer thực tế |
| Maven 4 + build POM `4.1.0` | Dự kiến chuyển sang consumer POM tương thích `4.0.0` khi khả thi | **Phải kiểm POM đã xuất bản**, nhất là parent/BOM/profiles mới |
| Maven 3 đọc chính source POM `4.1.0` | Không phải tình huống consumer artifact | **Không** được coi là hỗ trợ |

**Tách hai quyết định:**

- **Build compatibility:** ai có thể checkout Git và chạy `mvn verify`?
- **Artifact consumption compatibility:** ai có thể lấy JAR/POM/GAV từ repository rồi compile/run?

Maven 4 được thiết kế để hỗ trợ hai nhu cầu này nhưng chúng **không phải một phép thử**. Đừng suy ra consumer Java/Gradle/Maven 3 chạy được chỉ vì producer Maven 4 `BUILD SUCCESS`.

## 4. Vì sao Maven cần build POM và consumer POM?

Trong Maven 3, cùng một `pom.xml` thường làm hai việc:

1. **Build description:** source paths, plugins, profiles, test/reporting/repository configuration, parent/module structure.
2. **Consumer metadata:** GAV, scopes, transitive dependencies, BOM/version management, thông tin cần resolve thư viện.

Khi project phát hành artifact, nhiều công cụ chỉ cần phần thứ hai. Nếu consumer phải hiểu toàn bộ mô hình build mới của Maven 4 thì ecosystem sẽ bị buộc nâng đồng loạt. Maven 4 cho phép **source build POM tiến hóa** trong khi **consumer POM được chuyển đổi** về mô hình có thể được các công cụ cũ đọc.

Sơ đồ:

```text
Git source repository
        |
        v
pom.xml: build POM, có thể model 4.1.0
        |
        v
Maven 4 xây effective model, resolve parent/subprojects
        |
        v
Compile / Test / Package
        |
        v
Chuyển metadata thành consumer POM
        |
        v
Maven repository: JAR + .pom đã xuất bản
        |
        v
Maven 3 / Maven 4 / Gradle / IDE consumer
```

**Quan trọng:** đây là sơ đồ kiến trúc, không có nghĩa mọi phiên bản/cấu hình Maven 4 đều bật **flattening hoàn toàn** theo mặc định.

### 4.1. Conversion khác flattening

Hai ý thường bị gộp sai:

- **Model conversion:** Maven 4 tạo POM dành cho consumer, cố gắng dùng model `4.0.0` để bảo vệ compatibility.
- **Flattening:** giảm/loại thông tin build-only, giải quyết inheritance/BOM dependencies để consumer không phải đọc toàn bộ source build structure; cách bật và độ sâu phụ thuộc Maven version/tùy chọn.

Tài liệu chính thức Maven 4 nêu user property:

```text
-Dmaven.consumer.pom.flatten=true
```

để yêu cầu **flattened consumer POM**; tính năng flatten có thể **không được bật mặc định** theo bản Maven 4 được sử dụng. Vì vậy đừng phát biểu “Maven 4 **luôn** xóa parent, plugin configuration và mọi properties khỏi POM đã deploy”.

Điều đúng là **đọc POM thực tế sau install/staging** và xác nhận **model version, parent, dependency scopes, BOM imports, version expressions và plugins** theo yêu cầu consumer. Với POM artifact có `<packaging>pom</packaging>` (parent/aggregator), cách giữ thông tin build có ngoại lệ so với JAR library.

### 4.2. Giới hạn các features không chuyển được

Một số Maven 4 model `4.1.0` features có thể **không biểu diễn được bằng `4.0.0`** trong mọi hoàn cảnh (ví dụ một số cấu hình profile có điều kiện mới). Maven có thể cảnh báo hoặc giữ model mới trong consumer POM, khiến Maven 3/Gradle/IDE cũ không đọc được.

Đặc biệt cần kiểm:

- POM artifact `packaging=pom` dùng làm **parent** của consumers.
- BOM POM và các classifier/type/version semantics mới.
- Profile activation có condition/packaging logic mới.
- Extension configuration hoặc source declarations khó chuyển đổi.
- Bất kỳ generated consumer POM nào vẫn có `<modelVersion>4.1.0</modelVersion>`.

**Không tự giả định conversion thành công chỉ vì file có tên `.pom`.**

## 5. Thực hành A — một project model `4.0.0` chạy được với Maven 3

Dự án này là **baseline** trước khi đánh giá Maven 4:

```text
model40-lab/
├── pom.xml
└── src/
    ├── main/java/demo/model40/
    │   ├── TextLabel.java
    │   └── App.java
    └── test/java/demo/model40/
        └── TextLabelTest.java
```

Mục tiêu:

- Dùng model `4.0.0` chuẩn.
- Chọn Java 17 để code có thể biên dịch trên Maven 3/JDK 17 và Maven 4/JDK 17+.
- Có đủ Maven Compiler/Surefire plugins và JUnit Jupiter 5.
- Có **3 unit tests** thật và output Java chính xác.
- So cùng source POM trên hai Maven executables, không sửa model version để thay tool.

### 5.1. POM model `4.0.0` hoàn chỉnh

Tệp `model40-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.model40</groupId>
    <artifactId>model40-lab</artifactId>
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
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
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
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
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
```

**Lưu ý:** plugin versions ở đây được pin để ví dụ có thể đối chiếu, **không phải khẳng định đây là bộ plugin mới nhất cho Maven 4**. Theo hướng dẫn nâng cấp, nên cập nhật trước lên bộ plugin Maven 3-compatible mới nhất phù hợp dự án, rồi đánh giá nhu cầu plugin version riêng cho Maven 4.

### 5.2. Source Java 17: TextLabel.java

Tệp `src/main/java/demo/model40/TextLabel.java`:

```java
package demo.model40;

import java.util.Locale;

public final class TextLabel {
    private TextLabel() {
    }

    public static String format(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("input required");
        }
        return "MODEL 4.0.0 | "
                + input.strip().toUpperCase(Locale.ROOT);
    }
}
```

`String.isBlank()` và `String.strip()` thuộc Java 11+, có trên Java 17. `Locale.ROOT` giúp uppercase ổn định giữa các locale. Source này **không dùng Maven-specific APIs**, chỉ kiểm Java compiler và test lifecycle.

### 5.3. App.java và stdout

Tệp `src/main/java/demo/model40/App.java`:

```java
package demo.model40;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(TextLabel.format(" Maven "));
    }
}
```

Sau khi compile, chạy:

```bash
java -cp target/classes demo.model40.App
```

Vì app chỉ dùng Java standard library, không cần external runtime dependency. Stdout **đúng một dòng**:

```text
MODEL 4.0.0 | MAVEN
```

### 5.4. Unit tests JUnit Jupiter

Tệp `src/test/java/demo/model40/TextLabelTest.java`:

```java
package demo.model40;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TextLabelTest {

    @Test
    void normalizesInput() {
        assertEquals("MODEL 4.0.0 | MAVEN",
                TextLabel.format(" Maven "));
    }

    @Test
    void rejectsBlank() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> TextLabel.format("  "));
        assertEquals("input required", error.getMessage());
    }

    @Test
    void rejectsNull() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> TextLabel.format(null));
        assertEquals("input required", error.getMessage());
    }
}
```

**Ba tests** kiểm format và validation, không phải kiểm thay đổi Maven model. Test count giúp tránh một lượt Maven test bị skip mà vẫn được coi là tương đương.

### 5.5. Chạy bằng Maven 3

Với Maven 3.9.x trên PATH, JDK 17 và đủ network/mirror:

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes demo.model40.App
```

Kỳ vọng Maven Surefire có:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Và main stdout:

```text
MODEL 4.0.0 | MAVEN
```

Sau đó có JAR dự kiến:

```text
target/model40-lab-1.0.0.jar
```

Các dòng trên là **kết quả kỳ vọng của bài thực hành**, không phải kết quả Maven đã chạy trong môi trường hiện tại.

### 5.6. Chạy cùng POM bằng Maven 4

Không sửa `pom.xml`. Dùng một Maven 4 distribution được pin và được tổ chức cho phép, qua Maven Wrapper riêng hoặc executable Maven 4 đã cài. Ví dụ nếu CLI đang trỏ Maven 4:

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes demo.model40.App
```

**So cùng source commit, Java compiler release, JUnit test count, JAR contents và stdout.** Nếu Maven 4 fail, đừng vội sửa `<modelVersion>4.0.0</modelVersion>` thành `4.1.0`; hãy đọc lỗi Maven 4 validation/plugin compatibility, fix POM Maven 3-compatible trước nếu có thể.

Một máy không thể dùng cùng lệnh `mvn` để chứng minh cả hai phiên bản **trừ khi** người đo thực sự đổi Maven executable/Wrapper giữa các lượt và ghi lại `mvn -version`. Tên tool không phải bằng chứng version.

## 6. Thực hành B — project model `4.1.0` dùng Maven 4-only

Khi Maven 4 đã build được baseline, ta chuyển sang **một project khác** để minh họa các tính năng POM 4.1.0. Không sửa POM baseline bởi mục tiêu của hai bài khác nhau.

Cấu trúc Maven 4 multi-project:

```text
model41-lab/
├── pom.xml
├── api/
│   ├── pom.xml
│   └── src/main/java/demo/model41/api/Salutation.java
└── app/
    ├── pom.xml
    ├── src/main/java/demo/model41/app/Application.java
    └── src/test/java/demo/model41/app/ApplicationTest.java
```

- Root `pom.xml`: `modelVersion=4.1.0`, `root="true"`, `packaging=pom`, khai báo `<subprojects>`.
- `api/pom.xml`: `modelVersion=4.1.0`, `<parent/>`, artifactId `api`.
- `app/pom.xml`: `modelVersion=4.1.0`, `<parent/>`, dependency tới `api` **không ghi version**, JUnit test.
- `api`: cung cấp class public `Salutation`.
- `app`: dùng `Salutation` và có **3 tests**, chứng minh Reactor xác định đúng version trong multi-project setup.

**Phải dùng Maven 4 có hỗ trợ model 4.1.0** và Java 17+ để chạy build. Maven 3 **không phải executable hợp lệ** của project này.

## 7. Root POM model `4.1.0` hoàn chỉnh

Tệp `model41-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0
                             https://maven.apache.org/xsd/maven-4.1.0.xsd"
         root="true">
    <modelVersion>4.1.0</modelVersion>

    <groupId>demo.model41</groupId>
    <artifactId>model41-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <subprojects>
        <subproject>api</subproject>
        <subproject>app</subproject>
    </subprojects>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
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
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.3.2</version>
                </plugin>
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
                    <version>3.2.5</version>
                    <configuration>
                        <failIfNoTests>true</failIfNoTests>
                    </configuration>
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

### 7.1. Vì sao root có `root="true"`?

Trong model 4.1.0, `root` là **attribute của `<project>`**, không phải một element `<root>` nằm trong POM. Nó đánh dấu thư mục chứa root POM, giúp Maven xác định project root và những properties liên quan.

Có thể xem:

```xml
<project ... root="true">
```

là **fragment minh họa cú pháp**, không phải project XML độc lập.

Một cách root discovery khác là đặt `.mvn` directory trong root, phù hợp cả một số workflow Maven 3. **Đặt `root="true"` thuộc model 4.1.0**, không paste attribute này vào POM Maven 3 model 4.0.0 rồi mong Maven 3 hiểu.

### 7.2. Vì sao `<subprojects>` thay `<modules>`?

Maven 4 đổi thuật ngữ để không nhầm Maven subproject với Java JPMS module. Tại model 4.1.0, `<subprojects>` là cách khai báo mới tương ứng với `<modules>`, trong khi `<modules>` được giữ để tương thích nhưng đã bị deprecate.

Hai dạng:

```xml
<!-- Maven 3 / POM 4.0.0 -->
<modules>
    <module>api</module>
    <module>app</module>
</modules>
```

```xml
<!-- Maven 4 / POM 4.1.0 -->
<subprojects>
    <subproject>api</subproject>
    <subproject>app</subproject>
</subprojects>
```

Chúng là **mảnh POM so sánh**; không khai báo cả hai danh sách chỉ để “hỗ trợ hai đời Maven” mà chưa hiểu kết quả aggregation và plugin behavior. Nếu **cần** Maven 3 build cùng source, giữ model 4.0.0 và `<modules>`.

### 7.3. Plugin management có tự chạy tests không?

Root dùng `<pluginManagement>` để thống nhất plugin versions/config cho children. Trong `api`/`app` là `jar` packaging, default lifecycle đã có compile/test/package bindings tương ứng; `pluginManagement` cung cấp versions/config phù hợp cho những plugins đó.

Đối với **custom goal không thuộc default lifecycle**, chỉ có `<pluginManagement>` **không tự chạy goal**; phải khai báo plugin execution ở `<build><plugins>` hoặc gọi goal tường minh. Đừng nhầm rule này với default lifecycle bindings của Java JAR project.

## 8. Child `api/pom.xml` với parent inference

Tệp `model41-lab/api/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0
                             https://maven.apache.org/xsd/maven-4.1.0.xsd">
    <modelVersion>4.1.0</modelVersion>

    <parent/>
    <artifactId>api</artifactId>
    <packaging>jar</packaging>
</project>
```

`<parent/>` là shorthand mới cho Maven 4 model 4.1.0: Maven dựa vào **relative parent POM trên disk** (mặc định thư mục cha) để suy luận groupId, artifactId và version. Trong cấu trúc mẫu, thư mục cha `model41-lab` có root `pom.xml`.

Đây là **source build POM**. Khi artifact `api` được publish, consumer POM cần chứa metadata đủ để consumer không phải có cùng thư mục source/một `<parent/>` không resolve được.

### 8.1. Với Maven 3, cần tọa độ parent tường minh

Nếu viết **model 4.0.0**, đoạn tương đương phải chứa đầy đủ:

```xml
<parent>
    <groupId>demo.model41</groupId>
    <artifactId>model41-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Đây là **mảnh POM** để giải thích khác biệt. Maven 3 không tự suy ra toàn bộ GAV parent từ `<parent/>` theo cách mới của model 4.1.0.

Với cả Maven 3 và Maven 4, **đừng quên sự khác biệt giữa parent và aggregator**: khai báo subprojects/modules ở root tổ chức Reactor; `<parent>` ở child xác định inheritance. Chúng liên quan nhưng không tương đương.

## 9. Java API module: Salutation.java

Tệp `model41-lab/api/src/main/java/demo/model41/api/Salutation.java`:

```java
package demo.model41.api;

public final class Salutation {
    private Salutation() {
    }

    public static String make(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        return "MAVEN4 | Hello, " + name.strip() + "!";
    }
}
```

Class chỉ dùng Java standard library và Java 17 target. Public API `make(String)` là dependency contract cho app module.

Ví dụ:

```java
Salutation.make(" Team ")
```

trả:

```text
MAVEN4 | Hello, Team!
```

Đây là **biểu thức minh họa**, chưa phải chương trình Java hoàn chỉnh. `Application.java` bên dưới có `main` runnable.

## 10. Child `app/pom.xml` với dependency version inference

Tệp `model41-lab/app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0
                             https://maven.apache.org/xsd/maven-4.1.0.xsd">
    <modelVersion>4.1.0</modelVersion>

    <parent/>
    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>demo.model41</groupId>
            <artifactId>api</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Có **hai lý do khác nhau** khiến dependency thiếu `<version>` vẫn hợp lệ trong ví dụ:

1. `demo.model41:api` là **dependency tới project nằm cùng multi-project setup**, nên model 4.1.0/Maven 4 suy luận version từ graph của chính dự án.
2. `org.junit.jupiter:junit-jupiter` là **third-party dependency**, được quản lý version 5.10.2 trong `<dependencyManagement>` của parent.

Không được suy ra từ ví dụ rằng **mọi dependency ngoài Internet đều có thể bỏ version** trong Maven 4. Nếu không thuộc project graph và không có version management khác, third-party GAV vẫn cần version để resolver chọn artifact.

### 10.1. Vì sao chỉ `<subprojects>` chưa đủ để dùng class của module `api`?

Root `<subprojects>` chỉ tập hợp project, **không tự thêm `api` vào compile classpath của `app`**. `app/pom.xml` vẫn phải có `<dependency>` tới `demo.model41:api`. Cú pháp mới giúp **suy luận version**, không xóa nhu cầu khai báo quan hệ dependency.

Nếu source `Application.java` import `demo.model41.api.Salutation` mà xóa dependency này, compiler có thể báo `package demo.model41.api does not exist`.

### 10.2. Inference phụ thuộc layout/source graph

`<parent/>` và version inference đọc cấu trúc projects **trong checkout/graph đang được Maven 4 build**. Chạy riêng `mvn -f app/pom.xml` sau khi chỉ copy mỗi folder `app` sang một máy khác có thể không đủ ngữ cảnh để suy luận parent/sibling.

Vì vậy migration sang cú pháp ngắn gọn phải đi cùng kiểm tra **cách IDE/CI checkout repository, chọn root, dùng `-f`/`-pl`, và publish consumer POM**. Không tự giả định một child source POM có thể xây hoàn toàn độc lập chỉ vì ngắn hơn.

## 11. App Java 17 và JUnit 5

Tệp `model41-lab/app/src/main/java/demo/model41/app/Application.java`:

```java
package demo.model41.app;

import demo.model41.api.Salutation;

public final class Application {
    private Application() {
    }

    public static String message() {
        return Salutation.make(" Team ");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Tệp `model41-lab/app/src/test/java/demo/model41/app/ApplicationTest.java`:

```java
package demo.model41.app;

import demo.model41.api.Salutation;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ApplicationTest {

    @Test
    void callsSiblingApi() {
        assertEquals("MAVEN4 | Hello, Team!",
                Application.message());
    }

    @Test
    void trimsName() {
        assertEquals("MAVEN4 | Hello, Alice!",
                Salutation.make(" Alice "));
    }

    @Test
    void rejectsBlankName() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> Salutation.make(" "));
        assertEquals("name required", error.getMessage());
    }
}
```

**Ba JUnit methods** trong app module. Root project và `api` module không có tests của riêng chúng trong bài; không dùng `failIfNoTests=true` **toàn root cho mọi subproject** rồi tự làm root/api thất bại vì thiếu tests. Mục tiêu QA là kiểm `app` chạy đúng ba tests, còn các projects khác chỉ cần compile/package tương ứng.

### 11.1. Kết quả chạy Main mong đợi

Sau khi Maven 4 build root thành công, muốn chạy `Application.main` bằng Java thuần phải có **cả app classes và API classes** trên runtime classpath.

Linux/macOS:

```bash
java -cp "app/target/classes:api/target/classes" \
     demo.model41.app.Application
```

Windows PowerShell:

```powershell
java -cp 'app/target/classes;api/target/classes' demo.model41.app.Application
```

Stdout của Java Main:

```text
MAVEN4 | Hello, Team!
```

`:` và `;` là các classpath separators tương ứng Unix/Windows. Đoạn chạy thủ công này kiểm source output sau build, **chưa kiểm artifact đã deploy**; muốn kiểm dependency consumption, làm bài test riêng từ repository sau install/staging.

## 12. Chạy Maven 4 multi-project và đọc kết quả

Từ thư mục `model41-lab`, dùng một **Maven 4 executable được pin**, không dùng Maven 3:

```bash
mvn -version
mvn -B -ntp clean verify
```

Đảm bảo `mvn -version` in Maven 4 thực sự và Java runtime >= 17. Kỳ vọng:

- Maven đọc root build POM `4.1.0`.
- Root khai báo hai subprojects `api`, `app`.
- Parent của children được suy luận từ root POM.
- Maven Reactor chọn build `api` trước `app` do `app` phụ thuộc `api`.
- `app` compile trên classpath chứa API của sibling project.
- Surefire trong `app` chạy **3 tests**, failures/errors/skipped 0.
- Java packages được tạo thành JARs trong từng project theo packaging `jar`.

File dự kiến:

```text
api/target/api-1.0.0-SNAPSHOT.jar
app/target/app-1.0.0-SNAPSHOT.jar
app/target/surefire-reports/TEST-demo.model41.app.ApplicationTest.xml
```

**Đây là kết quả dự kiến**, phụ thuộc plugin/Maven 4 version tương thích. Chưa được thực thi trong môi trường của tài liệu này.

### 12.1. Khi Maven 3 chạy nhầm source POM model `4.1.0`

Nếu CI dùng Maven 3 mà root POM đã đổi model sang 4.1.0, build có thể fail ngay ở **POM parsing/model validation**. Đó không phải lỗi thiếu Java library hoặc source code.

Không “sửa” bằng cách chỉ đổi dòng `<modelVersion>4.1.0</modelVersion>` thành `4.0.0` trong khi vẫn giữ `root`, `<subprojects>` hoặc `<parent/>` và dependency không version. Những features mới phải được **viết lại về cú pháp Maven 3-compatible** nếu muốn quay lại Maven 3.

### 12.2. Nếu Maven 4 không tìm được child POM

Kiểm:

- Đường dẫn `<subproject>api</subproject>` trỏ đúng thư mục có `pom.xml`?
- `app` và `api` cùng dưới root theo layout đã khai báo?
- `root="true"` nằm ở root POM, không bị copy nhầm vào child?
- `app` có dependency tới đúng `groupId:artifactId` của `api`?
- Có thay đổi `<parent>`/`relativePath>` làm suy luận parent sai?
- CI có checkout đầy đủ các folder, không sparse checkout thiếu parent?
- `-f`/working directory có khiến Maven xử lý một source POM thiếu graph không?

## 13. So sánh Maven 3 explicit parent và Maven 4 inferred parent

Trong Maven 3 model `4.0.0`, project con thường ghi:

```xml
<parent>
    <groupId>demo.model41</groupId>
    <artifactId>model41-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Ở Maven 4 model `4.1.0`, cùng layout có thể dùng:

```xml
<parent/>
```

Và sibling dependency:

```xml
<dependency>
    <groupId>demo.model41</groupId>
    <artifactId>api</artifactId>
</dependency>
```

Maven 4 **suy luận version từ sibling project graph**. Còn ở Maven 3, phải ghi dependency version tường minh hoặc quản lý bằng `<dependencyManagement>`.

Ưu điểm của inference là giảm việc đồng bộ version trong nhiều child POM khi tăng project version. Rủi ro vận hành là **source POM phụ thuộc Maven 4 và layout checkout**; những công cụ đọc POM offline mà chưa hiểu model 4.1.0 có thể không import đúng trước khi build.

### 13.1. Suy luận không có nghĩa Maven tự tải mọi phiên bản

Maven 4 inference giúp nhận biết **project own dependencies trong multi-project setup**. Nó không tự chọn latest version từ Maven Central cho arbitrary third-party dependencies. Cần GAV/version management tường minh, đúng repository và release policy.

### 13.2. Dependency management không làm dependency xuất hiện tự động

Ngay cả khi parent có:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

thì `app` vẫn phải khai báo JUnit trong `<dependencies>` với test scope. `dependencyManagement` quản lý version/scope metadata của dependency **được dùng**, không tự thêm dependency như một direct library.

## 14. Các POM vẫn thuộc hệ Maven: parent, aggregator, dependency

Một số khái niệm **không đổi** khi chuyển 4.0.0 sang 4.1.0:

- **Parent POM**: inheritance, chia sẻ plugin/dependency management.
- **Aggregator POM**: danh sách `<modules>` hoặc `<subprojects>` cho Reactor build.
- **Dependency**: quan hệ classpath giữa projects, có scope/type/optional/exclusion rules.
- **BOM**: cấu hình version alignment bằng dependency management.
- **Plugin**: code chạy build goals, quản lý ở `<build><plugins>` hoặc `<pluginManagement>`.
- **Local/remote repository**: resolve/publish artifacts qua GAV.
- **Lifecycle phases**: compile, test, package, verify, install, deploy — dù Maven 4 có những thay đổi/phase mới.

Thay đổi model giúp gọn và thêm tính năng, **không loại bỏ trách nhiệm khai báo dependency graph, test coverage hay plugin compatibility**.

## 15. `packaging=bom`: tính năng Maven 4 model `4.1.0`

Maven 3 thường dùng `packaging=pom` cho cả parent/aggregator và BOM. Maven 4 bổ sung `packaging=bom` trong **build POM model 4.1.0** để phân biệt vai trò BOM.

Ví dụ POM build của một BOM độc lập:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0
                             https://maven.apache.org/xsd/maven-4.1.0.xsd">
    <modelVersion>4.1.0</modelVersion>

    <groupId>demo.model41</groupId>
    <artifactId>deps-bom</artifactId>
    <version>1.0.0</version>
    <packaging>bom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Đây là **một POM độc lập để minh họa packaging BOM**, không phải file thứ tư cần đặt vào `model41-lab` và build cùng Reactor. Nó chỉ quản lý version JUnit, không tự chứa JUnit JAR, cũng không được coi là artifact Java runtime library.

Maven 4 có khả năng tạo POM consumer theo kiểu phù hợp để tools cũ có thể import BOM; **phải kiểm metadata sau publish** thay vì đoán `packaging=bom` sẽ tồn tại nguyên văn và Maven 3 hiểu được.

### 15.1. Dùng BOM từ một Maven 3 consumer

Khi BOM đã publish với coordinates đúng và consumer POM tương thích, một Maven 3 project có thể nhập bằng:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>demo.model41</groupId>
            <artifactId>deps-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **mảnh POM consumer Maven 3**, không thể tự chạy nếu BOM `demo.model41:deps-bom:1.0.0` chưa được publish. Consumer sau đó vẫn cần `<dependency>` thật tới `junit-jupiter` nếu source/tests dùng nó.

**BOM packaging build-time của Maven 4** và **BOM POM artifact dùng bởi consumer** là hai lớp cần kiểm. Không đưa `<packaging>bom</packaging>` vào Maven 3 POM rồi kết luận Maven 3 đã hỗ trợ.

### 15.2. Không import BOM từ cùng Reactor một cách tùy tiện

Maven 4 documentation lưu ý việc import BOM từ **cùng Reactor** có giới hạn và cảnh báo, vì dependency management cần metadata có thể resolve độc lập. Hãy dùng một BOM đã publish/staged ở repository phù hợp hoặc theo strategy chính thức của Maven 4, đặc biệt khi liên quan classifier. Đừng dùng BOM làm cách lách một circular dependency giữa parent và child.

## 16. Build source roots: từ sourceDirectory sang sources

Trong POM `4.0.0`, cách cổ điển:

```xml
<build>
    <sourceDirectory>src/main/java</sourceDirectory>
    <testSourceDirectory>src/test/java</testSourceDirectory>
</build>
```

Trong Maven 4 model `4.1.0`, model thêm `<sources>` hỗ trợ nhiều source directories và scopes:

```xml
<build>
    <sources>
        <source>
            <scope>main</scope>
            <directory>src/main/java</directory>
        </source>
        <source>
            <scope>test</scope>
            <directory>src/test/java</directory>
        </source>
    </sources>
</build>
```

Hai XML trên là **fragments giải thích schema**, không cần thêm vào POM demos vì chúng đã sử dụng **default standard Maven directory layout**. Maven 4 model mới có thể dùng `<sources>` cho các layouts phức tạp, nhưng **plugin** cũng phải hỗ trợ semantics tương ứng. Không chuyển toàn bộ project sang layout tùy chỉnh chỉ vì model 4.1.0 có element mới.

Đối với project cần Maven 3-compatible source POM, không dùng `<sources>` mới; giữ standard layout hoặc cơ chế plugin phù hợp Maven 3.

## 17. CI-friendly `${revision}`, version inference và Flatten Plugin

Các Maven 3 đời mới đã hỗ trợ một phần CI-friendly versions như:

```xml
<version>${revision}</version>
```

với property `revision` được cung cấp đúng theo Maven rules. Nhưng published POM hoặc inter-module parent/dependency references có thể gặp khó khi chưa được giải quyết hoàn toàn. Maven 3 projects có thể cần Flatten Maven Plugin hoặc một release strategy phù hợp.

Maven 4 model 4.1.0 kết hợp **sibling dependency version inference** và consumer POM generation để đơn giản hóa nhiều trường hợp `${revision}`. Không có nghĩa mọi use case/version expression đều tự chuyển chính xác nếu phụ thuộc plugins, profiles, dependency management hoặc publish pipeline tùy chỉnh.

### 17.1. Khi nâng cấp một multi-project lớn

Trước khi thay tất cả child POM thành `<parent/>`, cần:

1. Ghi rõ root/GAV/snapshot/release policy.
2. Xác định những child dependencies thuộc cùng project graph.
3. Kiểm dependencyManagement và versions của **external** libraries.
4. Kiểm CI-friendly `${revision}` được cung cấp bởi Maven environment hoặc defaults.
5. Test `mvn clean verify` trên Maven 4.
6. Test **consumer POM thực tế** sau install/staging dưới Maven 3.
7. Chỉ bỏ Flatten Maven Plugin nếu pipeline đã xác nhận artifact metadata đầu ra hợp lệ và không còn use case riêng cần nó.

**Đừng xóa Flatten Plugin ngay khi POM chưa build được hoặc chưa kiểm published POM.** Maven 4 có tính năng mới nhưng migration cũng thay packaging, plugin versions, repository metadata và khả năng phụ thuộc của IDEs.

## 18. Root directory, `.mvn` và đường dẫn mới

Maven 4 model 4.1.0 cho phép `root="true"` trên `<project>`; một cách khác là có thư mục `.mvn` ở project root. Các property dành cho đường dẫn có thể gồm:

- `${project.rootDirectory}`: root directory được xác định cho project.
- `${session.rootDirectory}`: root directory của session khi xác định được.
- `${session.topDirectory}`: top directory của Maven invocation.
- `${project.basedir}`/`${basedir}`: thư mục chứa POM của project hiện tại.

Ví dụ thư mục:

```text
model41-lab/                   root
├── pom.xml                    root="true"
├── api/pom.xml                basedir của api
└── app/pom.xml                basedir của app
```

Trong `app`, `${project.basedir}` thường chỉ `model41-lab/app`, **không phải** `model41-lab`. Nên dùng rootDirectory/session properties mới khi thực sự cần chia sẻ đường dẫn root cho checkstyle/license/config, đồng thời kiểm nó không rỗng vì root chưa được xác định.

Những property nội bộ cũ như `multiModuleProjectDirectory`/`executionRootDirectory` có thể bị deprecate hoặc loại bỏ trong Maven 4; đừng dựa vào chúng như public API bền vững.

## 19. `profiles`, plugin semantics và các feature khó publish

Maven profiles có thể thay dependencies, repositories, plugin executions, compiler settings và properties. Với Maven 4 model mới, còn có một số khả năng kích hoạt profile theo điều kiện. Đây là tiện ích cho build source nhưng có thể tạo **giới hạn chuyển đổi về consumer POM 4.0.0**, nhất là nếu consumer còn phải hiểu logic profile mới.

Khi cần publication compatibility:

- Tránh dùng profile chỉ active trên máy tác giả để xác định dependencies của thư viện.
- Không để consumer dependency graph phụ thuộc vào `env.*` chưa được quản lý.
- Kiểm POM đã `install`/`deploy` có đủ dependencies ở scopes đúng.
- Kiểm modelVersion của parent/BOM POMs, không chỉ JAR module.
- Khi Maven 4 cảnh báo không thể chuyển profile/feature, coi đó là **release blocker** nếu Maven 3 hoặc Gradle consumers còn được hỗ trợ.
- Ghi Maven distribution version chính xác, plugin versions và options bật conversion/flattening.

**Một `mvn verify` PASS không đồng nghĩa `mvn deploy` sẽ tạo metadata tương thích** với mọi tool. Đây là lý do cần một consumer integration job độc lập.

## 20. Khác biệt giữa Maven core 4 và POM model 4.1 trong lỗi thực tế

Có những lỗi khi nâng Maven 3 lên Maven 4 **ngay cả khi giữ POM model 4.0.0**:

- Maven 4 yêu cầu Java 17 làm **runtime JDK**.
- Plugin version cũ dùng Maven 2 APIs có thể không tương thích.
- Maven 4 validation chặt hơn; khai báo plugin trùng GAV, duplicate dependencies/tags hoặc config sai có thể từ warning thành failure.
- Một số directory/session properties nội bộ đã thay đổi.
- Các phase bindings và thứ tự plugin executions có thể khác.
- `installAtEnd`/`deployAtEnd` defaults có thay đổi theo plugin/core và Maven 4 guide.
- IntelliJ/Eclipse/CI wrapper có thể chưa hỗ trợ đầy đủ model 4.1 ở thời điểm nâng cấp.

Do vậy cần **hai chặng tách biệt**:

**Chặng 1:** Maven 3 → Maven 4, **giữ model 4.0.0** và sửa compatibility.

**Chặng 2:** model 4.0.0 → model 4.1.0 để dùng các feature mới, **chỉ sau khi đã chấp nhận chỉ Maven 4 build source**.

Nếu đổi cả Maven core, JDK, plugins, XML model, parent inference và repository settings cùng một commit, rất khó xác định yếu tố làm build fail.

## 21. Ba bước migration được khuyến nghị

### Bước 1 — chuẩn bị trên Maven 3

- Bắt đầu từ một source commit đang `clean verify` thành công trên Maven 3.9.x.
- Xác nhận tests/integration tests, dependency tree, build profiles, quality gates và Java target.
- Pin Maven/plugin versions, xem plugin yêu cầu Maven runtime tối thiểu.
- Sửa duplicate plugin declarations, dependency declaration lặp và warnings POM.
- Chuẩn hóa repository/mirrors và lưu baseline build reports/artifact checksums.
- Không vội thêm cú pháp model 4.1.0.

### Bước 2 — thử Maven 4 nhưng giữ POM `4.0.0`

- Cài JDK 17+ cho **Maven runtime**.
- Pin Maven 4 bằng wrapper/executable riêng; xác minh `mvn -version`.
- Chạy **chính source model 4.0.0** trên Maven 4.
- Sửa plugins/config không tương thích theo migration guide, ưu tiên fix vẫn build được trên Maven 3 khi cần dual-track.
- So test counts, dependency graph, artifact behavior và log warnings.
- Test `install`/`deploy` vào môi trường staging, so published POM.
- Chạy Maven 3 consumer độc lập trước khi tuyên bố compatibility.

### Bước 3 — quyết định dùng model `4.1.0`

Chỉ khi cần feature mới:

- Chuyển namespace/XSD/modelVersion đúng.
- Xác định root bằng `root="true"` hoặc `.mvn` theo policy.
- Đổi `<modules>` thành `<subprojects>` nếu phù hợp.
- Dùng `<parent/>` và sibling version inference khi project graph cho phép.
- Xem xét `packaging=bom`, `<sources>`, profile features mới.
- Kiểm source import trong IDEs, Maven 4 CLI, CI và release tooling.
- Kiểm **consumer POM** ở repository và parent/BOM chain cho Maven 3/Gradle.
- Thông báo rõ: **người checkout source phải dùng Maven 4**.

Lộ trình này bám theo hướng dẫn Apache Maven “prepare → test → migrate”, giảm số chiều thay đổi cùng một lúc.

## 22. Cách kiểm thực tế Maven versions và source POM

Trước khi build, ghi thông số:

```bash
java -version
javac -version
mvn -version
```

Maven Wrapper nếu có:

```bash
./mvnw -version
./mvnw -B -ntp clean verify
```

Windows PowerShell:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
```

**Lưu ý:** Maven Wrapper pin Maven distribution trong `.mvn/wrapper/maven-wrapper.properties`, **không tự đảm bảo JDK17 đã được cài**. Cấu hình wrapper cho Maven 4 chỉ khi môi trường developer/CI đã sẵn sàng.

### 22.1. Kiểm Maven 3 và Maven 4 song song

Khi migration, dùng **hai executable đã xác định rõ** (ví dụ hai Maven distributions do CI provision), hoặc hai CI jobs có Maven version khác. Pseudocode:

```text
JOB A: Maven 3.9.x + JDK 17 + source model 4.0.0 → clean verify
JOB B: Maven 4.x   + JDK 17 + source model 4.0.0 → clean verify
```

Không dùng cùng một shell command `mvn` hai lần mà không xác minh executable đã thay. **Tuyệt đối không dùng model 4.1.0 trong JOB A** nếu nó phải build source.

Sau khi chuyển source model 4.1.0:

```text
JOB C: Maven 4.x + JDK 17 + source model 4.1.0 → clean verify
JOB D: Maven 3.9.x + JDK phù hợp → consumer project độc lập, GAV từ staging
```

JOB D **không đọc source POM model 4.1.0**; nó chỉ nhận **POM đã publish** từ repository.

### 22.2. So hiệu quả và dependency graph

Có thể dùng Help/Dependency Plugin tương thích Maven version:

```bash
mvn -B org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
mvn -B org.apache.maven.plugins:maven-help-plugin:3.5.1:active-profiles
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Trong Maven 4 có thể cần plugin versions phù hợp hơn theo môi trường; ví dụ chỉ là commands gợi ý để so, không bảo đảm mọi plugin version hoạt động trên mọi Maven 4 RC. Nếu Help Plugin của một bản quá cũ không parse model mới, kiểm phiên bản plugin và migration notes trước.

Đừng tự coi `effective-pom` chính là **published consumer POM**. Nó mô tả model hiệu lực cho **build hiện tại**, trong khi consumer POM là metadata được sinh/lưu ở artifact repository.

## 23. Kiểm POM đã install, không chỉ file trong Git

Sau khi build một artifact candidate, một QA engineer nên kiểm:

```text
Build source POM:       repository Git / pom.xml
Generated build output: target/...
Installed/deployed POM: Maven local / staged repository .pom
Consumer:               project riêng tải GAV từ repository
```

Với một release artifact `demo.model41:api:1.0.0-SNAPSHOT`, đường dẫn repository kiểu Maven thường là:

```text
demo/model41/api/1.0.0-SNAPSHOT/api-1.0.0-SNAPSHOT.pom
demo/model41/api/1.0.0-SNAPSHOT/api-1.0.0-SNAPSHOT.jar
```

Tên file SNAPSHOT ở remote repository **có thể được timestamped** theo policy, vì vậy đây chỉ là đường dẫn **minh họa cho local artifact repository**. Không tự khẳng định remote staging có đúng tên file này nếu chưa xem metadata.

Những phép kiểm:

1. POM published `modelVersion` là `4.0.0` nếu còn hỗ trợ consumers Maven 3.
2. GAV của artifact và parent/bom chain resolve đầy đủ.
3. Dependency `api`/libraries có đúng version được chọn, không còn thông tin chỉ có ý nghĩa trong source checkout.
4. Không còn biến `${revision}` chưa được giải quyết khi consumer cần concrete version.
5. Không có activation/condition/packaging feature mà consumer tool không hiểu.
6. Plugin/source-only config không gây dependency resolution lỗi.
7. JAR/bytecode/API thật phù hợp Java runtime mà consumer được hứa hỗ trợ.

Đừng giả định `mvn install` sẽ làm artifact hiện diện ở **máy khác**. Để kiểm cross-machine tool compatibility, **deploy vào staging repository** có quyền cho phép và dùng một consumer Maven 3/Gradle job ở môi trường độc lập.

### 23.1. Nếu muốn flattened consumer POM

Với Maven 4 version hỗ trợ option của tài liệu chính thức:

```bash
mvn -B -ntp -Dmaven.consumer.pom.flatten=true clean install
```

Lệnh này minh họa **bật conversion/flattening theo phiên bản Maven 4 có hỗ trợ option**, không thay cho việc đọc POM đã install. Kiểm behavior `install`/`deploy`, plugin versions và external consumers sau đó. Không dùng một option từ bài hướng dẫn cũ mà không xác nhận nó còn được Maven distribution hiện tại hỗ trợ.

Nếu build có `packaging=pom` ở parent/BOM, cần kiểm **từng artifact loại POM**; conversion của JAR artifact chưa chắc bảo đảm cả parent chain không còn features 4.1.

## 24. Ví dụ Maven 3 consumer độc lập cho artifact Maven 4

Một ứng dụng Maven 3 chỉ tiêu thụ API đã published không cần đọc root build POM `model41-lab/pom.xml`. Một POM consumer **model 4.0.0**, có dependency tới API artifact:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.consumer</groupId>
    <artifactId>model41-legacy-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>demo.model41</groupId>
            <artifactId>api</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **POM consumer độc lập minh họa**; dependency `api` phải **thực sự được publish** vào repository mà Maven 3 consumer có thể resolve. Để nó trở thành demo chạy được, thêm source `LegacyApp.java` như sau.

Tệp `src/main/java/demo/consumer/LegacyApp.java`:

```java
package demo.consumer;

import demo.model41.api.Salutation;

public final class LegacyApp {
    private LegacyApp() {
    }

    public static void main(String[] args) {
        System.out.println(Salutation.make(" Legacy "));
    }
}
```

Dùng Maven 3 executable đã xác nhận, một repository chứa published API artifact và lệnh:

```bash
mvn -B clean package
```

Sau compile:

```bash
java -cp "target/classes:/path/to/api-1.0.0-SNAPSHOT.jar" \
    demo.consumer.LegacyApp
```

Stdout mong đợi:

```text
MAVEN4 | Hello, Legacy!
```

Đây là lệnh Linux/macOS với path JAR **minh họa**; thay bằng artifact path thực tế đã được consumer Maven 3 tải. Windows dùng dấu `;` giữa classpath entries. Trong CI, để tránh lệch library versions, lấy JAR từ Maven-resolved local repository hoặc dùng Maven Exec Plugin với runtime classpath thay vì hardcode một copy JAR tùy ý.

**Hợp đồng test quan trọng:** nếu consumer Maven 3 **không thể resolve POM** vì modelVersion 4.1.0, parent/BOM không tương thích hoặc unresolved version, build fail **trước khi Java compiler đến bước import class**. Đó là lỗi **artifact metadata compatibility**, không phải vì Java API method sai.

## 25. Parent POM và BOM là những trường hợp cần QA kỹ nhất

Một library JAR đơn giản có consumer POM 4.0.0 không có nghĩa **mọi phần của release train** đều tương thích. Parent/BOM POM có packaging và metadata khác library JAR.

Ví dụ:

```text
root-parent: packaging=pom  (được child POMs kế thừa)
deps-bom:    packaging=bom  (build POM Maven 4)
api:         packaging=jar
app:         packaging=jar
```

Những điểm cần xác minh:

- Parent artifact nếu được deploy có POM mà Maven 3 vẫn đọc được?
- Nếu consumer POM của `api` còn `<parent>` tới một Maven 4 parent, parent đó có modelVersion 4.0.0?
- BOM consumer POM có import scope/type và dependencyManagement dùng được bởi Maven 3?
- Nếu Maven 4 warning rằng model không chuyển được, team có **dừng phát hành** khi còn hỗ trợ tool cũ không?
- Có dùng profile condition, extension configuration hoặc `<sources>` mới trong POM loại `pom` mà conversion không thể loại bỏ?
- Maven 3 consumer ở **fresh cache** có resolve được toàn dependency graph không?

**Nên test trực tiếp published parent/BOM**, không chỉ grepping `api.jar`. Một parent POM 4.1.0 vô tình xuất bản có thể khiến consumer Maven 3 báo lỗi dù consumer POM của chính JAR trông như 4.0.0.

## 26. Lập test matrix cho nâng cấp không phá consumer

Một test matrix thực tế:

| Test | Build source version | Artifact được tiêu thụ | Kết quả cần đạt |
| --- | --- | --- | --- |
| A | Maven 3 + POM 4.0.0 | N/A | Baseline compile/test/package PASS |
| B | Maven 4 + POM 4.0.0 | N/A | Same tests / API / artifact contract PASS |
| C | Maven 4 + POM 4.1.0 | N/A | New features/parent/subprojects inference PASS |
| D | Maven 3 + POM 4.0.0 consumer | Maven 4 staged JAR + consumer POM | Dependency resolve, compile, runtime PASS |
| E | Gradle/IDE consumer còn hỗ trợ | Maven 4 staged metadata | Resolve dependency model PASS |
| F | Maven 3 import parent/BOM POM | Maven 4 staged parent/BOM | Model/POM graph compatible PASS |
| G | CI build và publish | Cùng candidate version | Checksums/provenance/published POM phù hợp |

Với artifacts cần hỗ trợ Java 11 runtime, thêm job consumer **Java 11** khi bytecode và dependencies cho phép. Maven 4 producer **vẫn chạy Java 17+**, nhưng consumer test **có thể** dùng Java 11 nếu API JAR được compile cho release 11. Chưa có test runtime thật thì không được hứa Java compatibility.

### 26.1. Chống “build xanh giả”

- Không chạy Maven 3 build trên source POM 4.1.0 rồi chuyển sang Maven 4 trong cùng job một cách mơ hồ.
- Không coi `mvn -version` trong IDE terminal là bằng chứng Maven Runner dùng cùng executable.
- Không kiểm consumer metadata bằng **source `pom.xml`** thay vì `.pom` đã publish.
- Không dùng `mvn -o` trên cache cũ để khẳng định đã tải artifact mới từ staging.
- Không skip tests trong một môi trường và chạy tests ở môi trường kia rồi so ngang.
- Không bỏ qua Maven 4 migration warnings liên quan consumer model.
- Không chỉnh parent/BOM version chỉ trong source tree mà chưa publish versions tương ứng.
- Không coi `target/classes` của sibling module là artifact public API cuối cùng đã deploy.

## 27. Những lỗi thường gặp và nguyên nhân

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Maven 3 báo unsupported model 4.1.0 | Source đã dùng schema mới | Build source bằng Maven 4 hoặc rollback model/cú pháp |
| Maven 4 build POM 4.0.0 vẫn fail | Plugin/JDK/strict validation khác | Kiểm `mvn -version`, duplicate configs, plugin versions |
| POM có `<modelVersion>4.1.0</...>` nhưng namespace 4.0.0 | XML model không đồng bộ | Dùng namespace/XSD 4.1.0 chính xác |
| `root` attribute không được hiểu | Maven 3 hoặc model4.0 source | Chỉ dùng với Maven 4 model4.1 |
| `<subprojects>` bị báo unknown | Tool chỉ hiểu model4.0 | Chọn Maven 4, hoặc `<modules>` trên model4.0 |
| `<parent/>` không resolve | Thiếu parent POM trên disk hoặc wrong root | Kiểm full checkout và relative layout |
| Child dependency thiếu version fail | Third-party không quản lý version / sibling inference không áp dụng | Thêm version/DM, kiểm graph |
| Maven 3 import POM published fail | Consumer POM còn 4.1 hoặc parent/BOM chain sai | Kiểm staged .pom và logs conversion |
| Gradle resolve sai dependencies | Metadata model/scope/BOM không tương thích | Test cross-tool consumer trên staging |
| POM plugin config biến mất khỏi consumer POM | Flattened consumer metadata | Đừng kỳ vọng consumers nhận build-only plugin config |
| Maven 4 compile dùng `release=11` fail với record | Source dùng Java17 feature | Đổi source hoặc target đúng |
| Maven 4 không chạy trên Java 11 | Maven core yêu cầu Java17 | Chọn JDK17+ cho Maven runtime |
| BOM `packaging=bom` không được Maven3 hiểu | Build-only feature của 4.1 | Publish/test consumer BOM POM 4.0.0 |
| Maven 4 warning condition profile | Feature không thể chuyển về 4.0 hoàn toàn | Đơn giản hóa profile/publish strategy |
| Maven 3 consumer thấy unresolved `${revision}` | POM output chưa giải quyết variable | Kiểm CI-friendly version/flatten metadata |
| `-pl`/root build khác IDE | Aggregation/root/subproject setup khác | So root, flags và full graph |
| Tests không chạy ở root | Packaging pom không có test source | Đọc app/module-specific Surefire XML |
| Same GAV nhưng byte artifact khác | SNAPSHOT/cache/redeploy policy | Kiểm staging provenance và checksum |
| Maven 4 migration đổi install/deploy order | Defaults/plugin execution lifecycle khác | Đọc guide, kiểm release pipeline |
| Maven 4 báo duplicate plugin | Model validation chặt hơn | Gộp duplicate declaration |
| Help Plugin không đọc được model 4.1 | Plugin/tooling version chưa hỗ trợ | Upgrade plugin/tool hoặc tránh dùng để kết luận |
| Plugin mới yêu cầu Maven4 | Đã nâng plugin trong Maven3 dual-track | Pin version tương thích mỗi stage |
| Maven Wrapper vẫn chạy Maven3 | Chưa cập nhật distribution URL hoặc IDE override | Kiểm `./mvnw -version` và IDE runner |
| `target` artifact có nhưng remote consumer fail | Install/deploy POM/parent không đúng | Test staged repository từ fresh consumer |

## 28. Security, governance và IDE/CI integration

Nâng POM model là một **thay đổi hệ sinh thái**, không chỉ chỉnh một dòng XML. Cần có bản đồ:

- Ai build từ source: developers, release automation, bots, IDE importers, build scanners?
- Maven/JDK versions được hỗ trợ?
- Có các plugins, build extensions hoặc internal tool nào dùng Maven Model APIs?
- Repo manager có kiểm POM model, checksum, signature/metadata đúng?
- Ai tiêu thụ JAR/BOM/parent bằng Maven 3, Maven 4, Gradle hoặc công cụ khác?
- Các pipelines dùng `.mvn/maven.config`, Wrapper hoặc JDK Toolchains thế nào?
- Có policy `flatten=true`, generation flag, staging gate hay alternative packaging không?
- Khi rollback Maven 4 source build, có kế hoạch viết lại các features 4.1-only không?

**Đừng giải quyết lỗi compatibility bằng cách tắt repository TLS/checksums, tải plugin từ nguồn không tin cậy hoặc ghi đè release artifact cùng GAV.** Dùng repository staging, versions cố định, build provenance, test reports và phê duyệt trước production.

### 28.1. IDE có thể chưa hiểu model 4.1.0 giống Maven CLI

Một IDE có thể vẫn import POM qua Maven model parser cũ, trong khi terminal Maven 4 compile tốt. Các biểu hiện:

- IDE đánh dấu `<subprojects>`/`root` là unknown.
- Không nhận `api` là sibling dependency vì model inference.
- Editor đòi parent GAV tường minh dù Maven 4 resolve được.
- IDE Maven Runner dùng Maven 3 bundled, còn terminal dùng Maven 4.
- Indexing khác với dependency tree từ Maven 4 CLI.

Cách xử lý: kiểm IDE/plugin version và cấu hình importer/runner dùng Maven 4, reload Maven project, chạy **actual Maven 4 goal**. Không “fix” bằng cách thêm random dependencies vào POM khi CLI compile đúng.

## 29. Checklist nghiệm thu migration theo hai trục

### 29.1. Source build compatibility

- [ ] Phân biệt Maven executable version với `<modelVersion>`?
- [ ] Maven 4 runtime có JDK 17+?
- [ ] POM model4.0.0 baseline build trên Maven3?
- [ ] Maven4 đã thử với **cùng** model4.0.0 trước khi migrate?
- [ ] Compiler plugin/source release và runtime JDK được phân biệt?
- [ ] Plugin versions/duplicate configurations đã được xử lý?
- [ ] Parent/BOM/third-party dependencies resolve đúng?
- [ ] Khi đổi sang 4.1, namespace/XSD/modelVersion đồng bộ?
- [ ] Root được xác định và `<subprojects>` đúng layout?
- [ ] Child `<parent/>` thật sự suy luận được?
- [ ] Sibling dependencies omit version chỉ khi inference hợp lệ?
- [ ] JUnit tests đủ số lượng và thực sự chạy, không skip?
- [ ] Source tools/IDE/CI đã chuyển sang Maven4 nếu dùng feature 4.1?

### 29.2. Consumer artifact compatibility

- [ ] Đã biết artifact nào được publish dạng JAR, BOM hoặc parent POM?
- [ ] Đã kiểm **published .pom**, không dùng source pom?
- [ ] Consumer modelVersion là 4.0.0 cho tools còn yêu cầu schema này?
- [ ] `maven.consumer.pom.flatten`/conversion behavior được kiểm trên Maven version đang dùng?
- [ ] Parent chain được Maven3/Gradle resolve không?
- [ ] BOM POM dependencyManagement có đúng và import được?
- [ ] Không còn `${revision}` hoặc version inference chỉ tồn tại trong source checkout?
- [ ] Profiles/condition/sources/extensions mới có chuyển đổi được không?
- [ ] Warnings không convert được đã được xử lý trước release?
- [ ] Maven3 consumer độc lập với fresh cache compile/runtime pass?
- [ ] Java runtime compatibility được kiểm riêng với target JDK?
- [ ] Staged artifact bytes/POM/checksum và release candidate là cùng một bản?
- [ ] Không redeploy đè bất biến release GAV?

**Kết luận:** POM model `4.0.0` là lựa chọn an toàn khi dự án còn cần **Maven 3 build source**, và Maven 4 vẫn hỗ trợ nó. Model `4.1.0` mở ra Maven 4 features như `root`, `<subprojects>`, `<parent/>` inference, sibling dependency version inference và `packaging=bom`, nhưng khiến **source build phụ thuộc Maven 4**. Maven 4 xây cơ chế **consumer POM** để người dùng Maven 3/Gradle tiếp tục dùng artifact, song không được đánh đồng conversion với flattening, và không được giả định mọi parent/BOM/profile mới đều chuyển được. Hãy migrate theo **prepare → test → migrate**, kiểm cả **source build** lẫn **published artifact consumption** trước khi gọi bản nâng cấp là tương thích.

### Tham khảo chính thức (Apache Maven)

- [What's new in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html)
- [Starting with Maven 4 — migration guide](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Maven 4 API — Project Model reference](https://maven.apache.org/ref/4-LATEST/api/maven-api-model/maven.html)
- [Maven 4.1.0 POM XML Schema](https://maven.apache.org/xsd/maven-4.1.0.xsd)
- [Maven 4.0.0 POM XML Schema](https://maven.apache.org/xsd/maven-4.0.0.xsd)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Guide to Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Compiler Plugin — Setting the --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
