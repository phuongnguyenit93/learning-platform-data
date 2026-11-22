# Tránh gọi `clean` không cần thiết và kiểm tra đầu ra cũ trong Maven

> **Build Tool Maven · Hiệu năng**  
> Hướng dẫn thực hành với **Maven 3.9.x, JDK 17**, Maven Clean Plugin 3.5.0, Compiler Plugin 3.14.1, Resources Plugin 3.3.1, JAR Plugin 3.5.1, Surefire Plugin 3.6.1 và JUnit Jupiter 5.11.4. Mục tiêu: biết khi nào **giữ lại `target/` để build nhanh hơn**, khi nào **phải dọn sạch đầu ra cũ**, và cách **kiểm chứng JAR, class, resources, báo cáo tests** thay vì tin rằng `BUILD SUCCESS` tự chứng minh mọi file là mới.

## 1. Vấn đề: `mvn clean` luôn an toàn nhưng không luôn cần thiết

Trong quá trình phát triển, nhiều người dùng một lệnh cho mọi lần thay code:

```bash
mvn clean install
```

Cách này dễ hiểu nhưng có thể tốn thời gian: `clean` xóa output build, Maven phải biên dịch và đóng gói lại nhiều thứ; `install` còn đưa artifact vào local Maven repository khi phần việc chỉ cần test. Với project nhiều modules, sự lặp lại có thể làm chu kỳ phản hồi của IDE và CI dài hơn.

Ngược lại, bỏ `clean` trong mọi trường hợp cũng nguy hiểm. Một file còn sót trong `target/classes`, một JAR cũ trong `target/` hoặc XML kết quả kiểm thử của lần chạy trước có thể khiến người dùng **bàn giao sai binary** hoặc đọc sai tình trạng tests.

**Nguyên tắc của bài:**

- **Development inner loop:** ưu tiên lifecycle phase tối thiểu (`compile`, `test`, `package`) và tận dụng khả năng incremental của plugin khi mọi điều kiện rõ ràng.
- **Khi thay đổi cấu trúc/source/resources/plugins hoặc nghi đầu ra cũ:** xác minh và dùng `clean` khi cần để loại bỏ trạng thái cũ.
- **Release/CI quality gate:** dùng build sạch ở workspace được kiểm soát, kiểm tra tests/outputs và bàn giao đúng artifact đã QA.
- **Luôn phân biệt:** `clean` xóa output của project; nó không mặc nhiên xóa Maven dependency cache hay CI artifact đã lưu bên ngoài workspace.

Câu hỏi cần trả lời không phải “`clean` tốt hay xấu?” mà là **“đầu ra lần trước có còn hợp lệ làm input cho lần build này không?”**

## 2. Phân biệt các thư mục và loại trạng thái

Một project Java dùng packaging `jar` có thể sinh:

```text
project/
├── pom.xml
├── src/
│   ├── main/java/
│   ├── main/resources/
│   ├── test/java/
│   └── test/resources/
└── target/
    ├── classes/
    ├── test-classes/
    ├── generated-sources/
    ├── maven-status/
    ├── surefire-reports/
    └── my-app-1.0.0.jar
```

Thư mục `target/` là output mặc định của Maven project (có thể được đổi qua POM). Nó không giống:

```text
~/.m2/repository/
```

là Maven local repository chứa downloaded dependencies/plugins/POMs, metadata và các artifacts được `mvn install` vào máy.

| Vị trí | Vai trò | `mvn clean` có thường dọn? | Có nên coi là bản phát hành? |
| --- | --- | --- | --- |
| `target/classes` | Compiled main classes + copied resources | Có | Không trực tiếp |
| `target/test-classes` | Compiled tests/resources | Có | Không |
| `target/generated-sources` | Files do generators tạo | Thường có, nếu nằm dưới build directory | Không mặc định |
| `target/surefire-reports` | Test XML/text hiện có | Có | Bằng chứng, nếu đúng run |
| `target/my-app-1.0.0.jar` | Binary từ package phase | Có | Chỉ sau khi QA đúng file |
| `~/.m2/repository` | Local Maven repository | **Không mặc định** | Không tự động |
| CI dependency cache | Data tối ưu tái tải | Không do Maven Clean quản lý | Không |
| CI workflow artifact/registry | Build output được upload/publish | Không do Maven Clean quản lý | Có thể, theo policy |

**Lưu ý:** bảng mô tả default directories. Maven Clean Plugin còn hỗ trợ custom `<filesets>`, do đó cấu hình do dự án tự đặt **có thể xóa nhiều hơn**. Phải xem effective POM trước khi chạy `clean` trong dự án lạ.

### 2.1. `clean` là lifecycle riêng

Maven có các lifecycle tách biệt:

```text
clean lifecycle:
  pre-clean -> clean -> post-clean

default lifecycle (rút gọn):
  validate -> compile -> test -> package -> verify -> install -> deploy
```

`mvn clean test` yêu cầu chạy clean lifecycle rồi default lifecycle tới `test`. `mvn test` chỉ chạy default lifecycle tới `test`; nó **không âm thầm chạy** clean lifecycle.

`mvn clean` đứng một mình **không biên dịch hay đóng gói lại**. Nếu có JAR trong `target` trước lệnh, sau `mvn clean` JAR có thể bị xóa và chưa được tạo mới cho tới khi chạy phase thích hợp.

### 2.2. Maven Clean Plugin thực sự xóa cái gì?

Theo tài liệu `clean:clean`, các thư mục mặc định được xét để xóa bao gồm:

- `${project.build.directory}` (thường là `target`).
- `${project.build.outputDirectory}`.
- `${project.build.testOutputDirectory}`.
- `${project.reporting.outputDirectory}`.

Trong project thông thường, xóa `target` đã bao trùm nhiều mục. Tuy nhiên nếu các paths được cấu hình **ra ngoài** build directory, plugin vẫn có thể tác động tới chúng.

**Không xem `clean` là lệnh xóa bộ nhớ cache dependency**. Nó không mặc định xóa `~/.m2/repository`, và bạn cũng không nên xóa cả repository local chỉ vì muốn tạo JAR mới.

## 3. Vì sao gọi `clean` quá thường xuyên có thể chậm?

Một vòng làm việc cơ bản:

```text
Sửa một method Java
  -> Maven compile
  -> unit tests
  -> xem kết quả
  -> sửa tiếp
```

Nếu build không cần xóa toàn bộ output, plugin có thể tận dụng các `.class` và metadata đã tồn tại. Trong nhiều project, chi phí phát sinh của `clean` gồm:

1. Xóa `.class` files nên phải biên dịch lại phần đáng kể source code.
2. Copy/filter lại resources.
3. Tạo lại generated files khi plugin được bind.
4. Chạy lại transformations hoặc packaging cần thiết.
5. Tăng disk I/O trên workspace lớn/antivirus chậm.
6. Với multi-module, làm mất output của nhiều modules bị clean.
7. Khi CI bị cấu hình cache nhầm `target`, xóa toàn bộ incremental state trong khi cache đã restore không còn ích.
8. Dù Maven local dependency cache vẫn còn, việc compile/package vẫn phải thực hiện lại sau clean.

**Không khẳng định mọi lệnh `mvn clean test` chậm hơn `mvn test` theo một tỷ lệ cố định.** Có những project nhỏ chỉ khác vài giây, có những plugins vốn luôn tạo lại output, hoặc việc clean giúp sửa trạng thái lỗi nên tổng thời gian điều tra ngắn hơn.

### 3.1. Vì sao không phải lúc nào bỏ `clean` cũng nhanh hơn?

Đôi khi incremental checks phải đi qua nhiều files, plugin có thể quyết định rebuild mọi source, hoặc downstream steps vốn luôn chạy. Nếu incremental state bị hỏng, việc thử build nhiều lần rồi debug sẽ **tốn hơn** một lần `clean verify`.

Mục tiêu tối ưu là **thời gian nhận phản hồi đúng**, không phải chỉ giảm số lệnh shell.

### 3.2. Phân biệt tốc độ Maven với tốc độ dependency download

Nếu lần đầu build chậm vì phải tải dependencies, chạy `clean` hay không không giải quyết nguyên nhân chính. Maven local repository vẫn được dùng để cache dependency/plugin đã tải.

Câu hỏi khác nhau:

```text
Bị chậm vì Maven phải DOWNLOAD JAR/POM?
  -> Xem repository, mirror, network, local repo

Bị chậm vì phải COMPILE hàng nghìn classes?
  -> Xem clean frequency, incremental behavior, JDK, modules

Bị chậm vì TESTS hoặc integration tests?
  -> Xem test scope, parallelism, test environment và test policy

Bị chậm vì PACKAGE hoặc code generation?
  -> Xem plugins, output invalidation và lifecycle goals
```

**Đừng dùng `-DskipTests` để che thời gian test rồi gọi đó là build tương đương** khi release yêu cầu tests. Điều đó thay đổi công việc được thực hiện, không phải chỉ là tối ưu cache.

## 4. Maven Compiler Plugin: incremental compilation có điều kiện

Maven Compiler Plugin có tham số:

```text
maven.compiler.useIncrementalCompilation
```

Với Compiler Plugin 3.x và javac mặc định, tài liệu mô tả:

- **`true` (mặc định):** theo dõi các thay đổi liên quan nguồn/dependencies và có thể biên dịch lại nhiều hoặc toàn bộ sources khi phát hiện source thêm/xóa/sửa hoặc JAR dependency đổi trong build run.
- **`false` (không khuyến nghị trong nhiều tình huống):** chủ yếu compile những source files mới hơn corresponding class files, có thể **không compile các classes phụ thuộc** vào một API đã đổi, dẫn đến lỗi như `NoSuchMethodError` tại runtime.

**Vì vậy không bật `false` mù quáng chỉ để nhanh hơn.** Tên `useIncrementalCompilation=false` không có nghĩa build đáng tin cậy hơn hoặc buộc mọi thứ được compile lại.

### 4.1. Ví dụ nguy cơ khi đổi public API

Lần đầu có:

```java
public final class Api {
    public static String getName() {
        return "old";
    }
}
```

và class khác:

```java
public final class Client {
    public static String load() {
        return Api.getName();
    }
}
```

Sau đó sửa `Api.getName()` thành `Api.name()` nhưng `Client.class` cũ không được recompile phù hợp. Nếu một incremental path không phát hiện được quan hệ phụ thuộc, ứng dụng có thể compile thiếu nhất quán hoặc lỗi runtime.

Hai class này chỉ là **fragments minh họa rủi ro**, không phải phần project runnable bên dưới. Maven Compiler Plugin mặc định cố xử lý các thay đổi liên quan; **không khẳng định mọi compiler/plugin version đều lỗi**, và cũng không cam kết mọi loại source generator/resource đã được dọn hoàn toàn khi xóa file nguồn.

### 4.2. File `.class` bị bỏ rơi

Khi đổi package, đổi tên class, xóa class cũ hoặc thay generated sources, file `.class` cũ có thể còn trong output tùy plugin/compiler/source layout. Điều đó dễ gây:

- JAR giữ `com/old/Legacy.class` dù source đã xóa.
- Reflection/ClassLoader phát hiện class cũ.
- App sử dụng resource hoặc service descriptor không còn trong source.
- Hai builds từ cùng source nhưng một bên chứa leftovers.
- Dependency scanner/SBOM nhìn thấy thành phần không mong đợi.

**Điểm cần kiểm tra là output thực**, không chỉ log “Nothing to compile” hoặc “BUILD SUCCESS”.

### 4.3. Incremental compilation không phải incremental packaging toàn diện

Maven Compiler Plugin quản lý việc biên dịch Java; Resources Plugin quản lý resources; JAR Plugin quản lý đóng gói. Chúng có cơ chế thay đổi/skip riêng.

Một build không `clean` có thể compile đúng nhưng JAR còn resource cũ do output directory bẩn. Hoặc build tests thành công nhưng final JAR chưa được cập nhật vì developer chỉ chạy tới phase `test`, chưa chạy `package`.

Không có một cơ chế incremental mặc định duy nhất **bảo đảm mọi file trong `target` luôn chỉ phản ánh source hiện tại** cho mọi plugin tuỳ chỉnh.

## 5. Maven JAR Plugin: `forceCreation` khác `clean`

Apache Maven JAR Plugin có tham số:

```xml
<forceCreation>true</forceCreation>
```

Theo tài liệu `jar:jar`, khi `forceCreation=false` (mặc định), plugin có thể **bỏ qua tạo JAR lại** nếu output JAR tồn tại và plugin xác định inputs chưa thay đổi.

Điều này giúp tránh I/O không cần thiết. Nhưng khi những plugins khác (ví dụ Shade Plugin) **post-process JAR**, plugin có thể không nhận ra file JAR đã bị post-process, khiến lần chạy sau dùng lại archive không phù hợp.

Trong trường hợp đó có thể cấu hình:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.5.1</version>
    <configuration>
        <forceCreation>true</forceCreation>
    </configuration>
</plugin>
```

**Đây là fragment nâng cao**, **không** được đưa vào POM lab mặc định. Nó buộc Jar Plugin tạo archive mới ở goal tương ứng; **không xóa các `.class` hoặc resources cũ có sẵn trong `target/classes`**.

Nếu đầu vào JAR đã chứa stale files, `forceCreation=true` vẫn có thể đóng gói stale files. Đó là lý do phải phân biệt **repackage** với **clean**.

### 5.1. Khi nào nên cân nhắc `forceCreation`?

- Plugin post-process main JAR rồi lần build sau Jar Plugin dùng lại archive đã qua transform.
- Có bằng chứng cụ thể JAR Plugin bỏ qua recreation không phù hợp với pipeline.
- Cấu hình Shade/Assembly custom yêu cầu một JAR sạch trước khi transform.

Không nên biến `forceCreation` thành cài đặt chung chỉ vì không muốn chạy clean. Hãy đối chiếu docs và output thực; nó có thể tăng I/O ở mọi build.

### 5.2. `outputTimestamp` không xóa stale input

Một property hỗ trợ reproducible archives:

```xml
<project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
```

có thể giúp ổn định timestamps trong JAR với plugin phù hợp. Nhưng nếu `target/classes` chứa một file thừa, việc cố định timestamp **không tự làm file đó biến mất**. Reproducibility cần đúng source/input set, not just timestamps.

## 6. Surefire XML: báo cáo có thể tồn tại sau một lần chạy cũ

Maven Surefire Plugin thường tạo:

```text
target/surefire-reports/TEST-*.xml
target/surefire-reports/*.txt
```

Các files này mô tả test results. Nếu một test class bị xóa hoặc tên suite đổi, cần kiểm tra việc report cũ có còn trong folder hay không; **không suy rằng mọi plugin version tự dọn mọi XML của suite đã biến mất**.

Một tình huống nguy hiểm:

1. Lần chạy trước tạo `TEST-org.example.OldTest.xml` và PASS.
2. Người dùng xóa hoặc đổi tên `OldTest`.
3. Một job hiện tại không clean, chạy tập tests khác, folder vẫn có XML cũ.
4. Tool ngoài Maven đọc **tất cả XML hiện có trong directory** rồi tính sai số tests hoặc báo cáo nhầm suite đã chạy.

**Đừng lấy tổng số XML files trong `target/surefire-reports` làm bằng chứng tests hôm nay đã chạy.**

### 6.1. Khi nào nên xóa reports cũ?

Với CI quality gate cần evidence **thuộc đúng run**, an toàn nhất là workspace sạch rồi:

```bash
mvn -B clean verify
```

Nếu muốn giữ incremental compile nhưng cần fresh reports, có thể **chỉ dọn khu vực reports** bằng phương thức đã xét an toàn cho project và chạy test lại. Tuy nhiên không được xóa `target/classes` hoặc files của job song song nếu workspace đang được dùng chung.

Trong môi trường CI, thường đơn giản và kiểm toán tốt hơn khi mỗi run có workspace mới, không restore `target/` từ cache.

### 6.2. `mvn test` và `mvn package` có khác nhau về tính mới của JAR?

Có. `mvn test` chạy default lifecycle tới `test`; nó **không bắt buộc** chạy goal `jar:jar` ở phase `package`.

Nếu JAR cũ tồn tại sau `mvn test`, đừng upload nó rồi nói đó là binary vừa được build/test. Muốn tạo JAR mới cho trạng thái source hiện tại, chạy:

```bash
mvn -B package
```

hoặc với release policy:

```bash
mvn -B clean verify
```

Sau đó kiểm tra artifact output/contents/checksum, không chỉ code exit status.

### 6.3. `-DskipTests` có thể tạo báo cáo gây hiểu nhầm

Khi dùng:

```bash
mvn -B package -DskipTests
```

Maven có thể đóng gói JAR mà không thực thi Surefire tests. Nếu reports cũ vẫn nằm trong `target`, một dashboard chỉ quét thư mục ấy có thể đưa ra trạng thái PASS không thuộc build vừa chạy.

Một CI gate đúng cần ghi **command + flags + run ID + số tests thực chạy + failures/errors/skipped**, và fail nếu policy đòi tests nhưng không có evidence hiện tại.

## 7. Lab Java 17: thấy artifact cũ còn được đóng gói dù Maven build thành công

Đây là bài thực hành **có thể chạy độc lập**; nó không phụ thuộc việc một compiler version có tự dọn `OldClass.class` khi bạn xóa Java source. Ta chủ động chèn một **file chỉ tồn tại trong output directory**, sau đó so JAR trước và sau `clean`.

### 7.1. Cây project

```text
clean-output-lab/
├── pom.xml
├── audit/
│   └── ArchiveProbe.java
└── src/
    ├── main/java/org/example/perf/HealthApp.java
    └── test/java/org/example/perf/HealthAppTest.java
```

Thư mục `audit/` chứa một **utility kiểm chứng độc lập** được chạy bằng Java 17 single-file source launcher. Nó không thuộc `src/main/java`, nên không nằm trong application JAR.

### 7.2. POM hoàn chỉnh — `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>clean-output-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Clean Output Lab</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>org.example.perf.HealthApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Lưu ý:

- Ghim plugin versions để lệnh `clean`/`verify` nhất quán với mục tiêu bài.
- Không cấu hình thêm `forceCreation`; JAR Plugin mặc định được phép tận dụng archive cũ khi inputs không đổi.
- JUnit chỉ có test scope; ứng dụng không cần thêm library runtime.
- Đặt `project.build.outputTimestamp` để ví dụ so checksum ít bị ảnh hưởng timestamp, nhưng không tuyên bố một property đủ bảo đảm mọi máy có hash giống nhau.
- Không khai báo Maven repositories hay deployment credentials; Maven Central hoặc approved mirror theo môi trường là đủ nếu có network.

### 7.3. `src/main/java/org/example/perf/HealthApp.java`

```java
package org.example.perf;

public final class HealthApp {
    private HealthApp() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static String message() {
        return "clean-output-lab: 2 + 3 = " + add(2, 3);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

### 7.4. `src/test/java/org/example/perf/HealthAppTest.java`

```java
package org.example.perf;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class HealthAppTest {
    @Test
    void addsNormally() {
        assertEquals(5, HealthApp.add(2, 3));
    }

    @Test
    void detectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> HealthApp.add(Integer.MAX_VALUE, 1));
    }

    @Test
    void printsExpectedMessage() {
        assertEquals("clean-output-lab: 2 + 3 = 5",
                HealthApp.message());
    }
}
```

Ba tests độc lập, không làm thay đổi files đầu ra tùy ý. Surefire 3.6.1 khám phá class tên `HealthAppTest` theo convention, JUnit Jupiter xử lý annotations.

### 7.5. `audit/ArchiveProbe.java`

Đây là **chương trình Java 17 runnable** đọc trực tiếp file JAR, không dựa vào Maven logs hoặc timestamp. Nó cho biết archive có entry `stale-marker.txt` hay không và kiểm tra `HealthApp.class` vẫn tồn tại.

```java
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class ArchiveProbe {
    private ArchiveProbe() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java audit/ArchiveProbe.java PATH_TO_JAR");
        }
        Path path = Path.of(args[0]);
        try (JarFile jar = new JarFile(path.toFile())) {
            boolean stale = jar.getJarEntry("stale-marker.txt") != null;
            boolean app = jar.getJarEntry(
                    "org/example/perf/HealthApp.class") != null;

            System.out.println("app-class=" + app);
            System.out.println("stale-marker=" + stale);
        }
    }
}
```

**Cách chạy trên JDK 17**:

```bash
java audit/ArchiveProbe.java target/clean-output-lab-1.0.0.jar
```

Java 17 hỗ trợ chạy một source file trực tiếp (`java path/File.java args`), nên không cần tạo `.class` ngoài Maven project hoặc chỉnh `pom.xml` để chứa utility này.

### 7.6. Bước A — build sạch làm mốc

Ở root project:

```bash
java -version
mvn -version
mvn -B clean verify
java -jar target/clean-output-lab-1.0.0.jar
java audit/ArchiveProbe.java target/clean-output-lab-1.0.0.jar
```

Stdout của chính ứng dụng:

```text
clean-output-lab: 2 + 3 = 5
```

Output chính xác của utility sau build sạch:

```text
app-class=true
stale-marker=false
```

Dòng summary tests dự kiến:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **kết quả kỳ vọng nếu Maven đã chạy ba tests**; console Maven còn nhiều dòng khác theo phiên bản OS/plugins. Nếu tests skip/fail, xử lý trước khi tiếp tục.

### 7.7. Bước B — chủ động tạo file đầu ra không còn tương ứng source

Trên Linux/macOS:

```bash
printf 'old file left by a previous build\n' > target/classes/stale-marker.txt
```

Trên Windows PowerShell:

```powershell
Set-Content -Path .\target\classes\stale-marker.txt -Value "old file left by a previous build"
```

Lúc này `stale-marker.txt` **chỉ có trong `target/classes`**, không có trong `src/main/resources`, không có Java source tạo ra nó. Đây là tình huống mô phỏng output còn sót sau lần build trước hoặc do plugin tùy chỉnh để lại.

**Không xóa/chèn file trong thư mục project thật đang phát hành.** Thao tác chỉ dành cho lab riêng, sau khi hiểu đúng path và có khả năng làm sạch lại.

### 7.8. Bước C — chạy `package` không `clean`

```bash
mvn -B package
java audit/ArchiveProbe.java target/clean-output-lab-1.0.0.jar
```

Vì `stale-marker.txt` là một resource thường có mặt trong input directory của JAR Plugin, việc đóng gói project sẽ có thể đưa file ấy vào archive. Với cấu hình và plugin version đã nêu, kết quả kỳ vọng:

```text
app-class=true
stale-marker=true
```

**Điểm quan trọng:** cả ba JUnit tests vẫn có thể PASS và chương trình vẫn in chuỗi đúng, nhưng file JAR **đã chứa đầu ra dư**. `BUILD SUCCESS` không khẳng định mọi entry trong JAR đều xuất phát từ source hiện tại.

Nếu một phiên bản/plugin tùy chỉnh tự dọn `target/classes` hoặc loại file bằng includes/excludes, kết quả có thể khác. Khi đó hãy kiểm tra `jar tf`, plugin logs và build configuration trước khi kết luận. POM lab **không có** bước tự dọn marker trước packaging.

### 7.9. Bước D — chạy `clean verify` rồi kiểm tra lại

```bash
mvn -B clean verify
java audit/ArchiveProbe.java target/clean-output-lab-1.0.0.jar
```

Output utility kỳ vọng trở về:

```text
app-class=true
stale-marker=false
```

Vì `clean` xóa build output directory; compile/resources/package tạo lại artifact từ inputs hợp lệ và không có nguồn nào sinh `stale-marker.txt`.

**Kết luận được kiểm chứng:** `clean` hữu ích khi cần bảo đảm output không chứa dữ liệu cũ còn trong `target` mà các incremental stages chưa dọn. Nhưng không cần gọi `clean` trước **mọi lần sửa một dòng Java** nếu output còn nhất quán và chưa cần package/release.

### 7.10. Kiểm tra bằng công cụ JDK thay cho utility

Ngoài `ArchiveProbe`, có thể:

```bash
jar tf target/clean-output-lab-1.0.0.jar
```

để xem entries. Trên Linux/macOS:

```bash
jar tf target/clean-output-lab-1.0.0.jar | grep "stale-marker.txt"
```

Khi archive chứa marker, `grep` in tên entry. Khi không có, `grep` thường exit 1; đó **là kết quả kiểm tra âm tính**, không phải Maven build thất bại. Trên PowerShell:

```powershell
jar tf .\target\clean-output-lab-1.0.0.jar | Select-String "stale-marker.txt"
```

Nếu không có match, `Select-String` không in dòng. Để có boolean rõ ràng trên mọi OS, dùng `ArchiveProbe` chạy bằng JDK 17 như mục trên.

## 8. Một trường hợp khác: chỉ chạy `test` nhưng deploy lại JAR cũ

Giả sử bạn đã chạy:

```bash
mvn -B package
```

và có:

```text
target/clean-output-lab-1.0.0.jar
```

Sau đó sửa `HealthApp.message()` và chỉ chạy:

```bash
mvn -B test
```

Tests có thể xác nhận code mới, nhưng default lifecycle **chưa tới phase `package`**. JAR cũ ở `target/` có thể vẫn mang bytes từ trước lần sửa. Nếu một script deploy/CI upload JAR dựa vào `test` exit code mà không gọi `package`, có thể triển khai **binary khác code vừa kiểm thử**.

### 8.1. Kiểm chứng an toàn

Đối với một binary chuẩn bị bàn giao:

```bash
mvn -B package
java -jar target/clean-output-lab-1.0.0.jar
java audit/ArchiveProbe.java target/clean-output-lab-1.0.0.jar
```

Ngoài ra tính SHA-256 trên **file JAR sau package** và gắn với build run. Không lấy file tồn tại ở `target` như bằng chứng nó vừa được tạo.

### 8.2. Khi nào dùng `compile`, `test`, `package`, `verify`?

| Nhu cầu | Lệnh thường đủ trong development | Điều chưa thể suy ra |
| --- | --- | --- |
| Kiểm tra lỗi compile main code | `mvn compile` | Unit tests hoặc final JAR đã chạy/tạo mới |
| Chạy unit tests | `mvn test` | JAR đã package và sẵn sàng bàn giao |
| Tạo JAR mới sau chỉnh source | `mvn package` | Mọi integration checks ở verify đã chạy |
| Chạy cả quality gates bind tới verify | `mvn verify` | Build sạch nếu không có `clean` |
| Xóa trạng thái cũ và QA đầy đủ | `mvn clean verify` | Tự bảo đảm security/correctness tuyệt đối |
| Cài artifact vào máy local | `mvn install` | Đã publish remote |
| Publish tới remote Maven repo | `mvn deploy` | Đúng permission/approval/provenance nếu pipeline chưa kiểm |

Lệnh nào “đủ” phụ thuộc goals được bind trong POM. Nếu có codegen, integration test hay custom checks, hãy đọc effective POM và lifecycle logs.

## 9. Files dễ trở thành stale output ngoài `.class`

### 9.1. Resources đã bị xóa/đổi tên

Ví dụ có:

```text
src/main/resources/config-old.properties
```

được copy đến:

```text
target/classes/config-old.properties
```

Sau khi xóa resource nguồn, một build không `clean` có thể giữ bản đã copy tùy Resources Plugin và output state. Khi Jar Plugin đóng gói `target/classes`, file cũ có thể lọt vào release JAR.

**Cách kiểm tra:**

```bash
jar tf target/clean-output-lab-1.0.0.jar
```

và đối chiếu với resources hiện hành. Khi thấy dư, dùng clean build, sau đó xử lý plugin configuration nếu thường xuyên phát sinh.

### 9.2. Service provider configuration

File:

```text
META-INF/services/org.example.MyService
```

trong JAR có thể khiến `ServiceLoader` tìm implementation. Nếu descriptor cũ còn trong output dù source đã xóa, runtime có thể báo class không tồn tại hoặc load implementation không mong muốn.

Đây là lý do stale files không chỉ làm JAR lớn; chúng có thể thay behavior.

### 9.3. Generated sources/resources

Các plugins tạo mã như OpenAPI, protobuf, annotation processors, JAXB hoặc custom generator có thể:

- Sinh file mới khi schema đổi.
- Không xóa một file generated đã biến mất khỏi schema.
- Ghi output vào `target/generated-sources` hoặc một directory tùy chỉnh.
- Để file cũ bị compile/đóng gói tiếp nếu không được dọn.

Nếu generator có chức năng cleanup riêng, sử dụng theo docs. Nếu không, clean build vào output directory chuẩn hóa là cách phổ biến để loại dữ liệu thừa.

### 9.4. Shade/Assembly/Spring Boot repackage

Một pipeline có thể có:

```text
target/clean-output-lab-1.0.0.jar
target/original-application.jar
target/clean-output-lab-1.0.0-exec.jar
```

Tên files trên là **minh họa**: plugin cụ thể quyết định output names. Không được kết luận mọi file có `.jar` trong `target` là final deployable.

Khi làm việc với Shade Plugin, cân nhắc JAR Plugin `forceCreation` theo docs, kiểm tra JAR đã transform thật, rồi tính digest/QA trên **final artifact sẽ publish**.

### 9.5. Surefire/Failsafe reports, Jacoco và static analysis

Các reports có thể nằm trong `target/surefire-reports`, `target/failsafe-reports`, coverage reports, static-analysis outputs. Nếu CI cache/restore `target` hoặc chạy job một phần, reports cũ có thể gây số liệu không thuộc run hiện tại.

**Không so “PASS” chỉ bằng việc file XML hoặc HTML đang tồn tại**. Liên kết reports với CI run, test count, exit status, execution config và artifact digest.

## 10. Quy tắc ra quyết định: lúc nào bỏ `clean`, lúc nào phải chạy?

| Tình huống | Quyết định gợi ý | Vì sao |
| --- | --- | --- |
| Sửa một method implementation và chạy unit tests local | Thử `mvn test` | Phản hồi nhanh, không cần JAR |
| Chạy lại tests khi source không đổi | `mvn test` hoặc scope test phù hợp | Giữ compiled classes có thể tiết kiệm thời gian |
| Chỉ muốn kiểm tra main compilation | `mvn compile` | Không cần đi tới package |
| Muốn đóng gói sau sửa source | `mvn package`, kiểm JAR | `test` không package |
| Xóa/rename Java class hoặc package | Cân nhắc `mvn clean verify` | Phát hiện output/class cũ |
| Xóa/rename resource hoặc codegen output | Ưu tiên clean + inspect | Có thể còn file được copy/sinh |
| Đổi compiler/JDK/plugin version/annotation processor | Dùng clean build | Tránh output do toolchain cũ tạo |
| Đổi Maven packaging/manifest/Shade | Clean + verify final archive | Có thể còn original/processed JAR cũ |
| Thử performance lặp với cùng code | Không clean mỗi lần nếu đo incremental, rồi đo clean riêng | Hai kịch bản là hai thí nghiệm khác nhau |
| CI PR kiểm thử với workspace hoàn toàn mới | `mvn verify` có thể đủ | Workspace mới không có outputs cũ |
| CI trên runner tái sử dụng workspace hoặc restore `target` | Clean/reject stale workspace | Cần evidence từ run hiện tại |
| Release reproducibility/provenance gate | `mvn clean verify` trong workspace tin cậy | Đảm bảo không tận dụng build outputs cũ |
| Đang debug “class lạ vẫn chạy” | Clean + `jar tf`/`javap` | Cô lập stale output |
| Test XML còn từ suite đã xóa | Clean hoặc targeted reports cleanup + rerun | Tránh báo cáo giả |
| Cần publish đúng JAR đã QA | Package/verify, hash, promote exact file | Ngăn deploy binary khác test |
| Chỉ đổi dependency cache | Không bắt buộc clean output; tùy dependency graph | Download cache khác compile output |
| Một module bị lỗi trong multi-module | Scope module phù hợp, clean có chọn lọc khi cần | Tránh xóa cả reactor vô cớ |

Đây là **quy tắc thực hành**, không phải một thuật toán Maven đảm bảo tự động. Khi project có custom plugins hoặc non-standard outputs, phải xem pipeline thực.

## 11. CI sạch nhưng không lạm dụng `clean` ở mọi bước

Một workflow phổ biến có thể tách:

```text
Developer IDE:
  mvn test
    - compile/test nhanh, dùng incremental outputs khi an toàn

Pull request CI (fresh checkout):
  mvn verify
    - QA toàn source/run hiện tại
    - không cần clean nếu runner/workspace thật sự mới

Release CI:
  mvn clean verify
    - không phụ thuộc target từ run cũ
    - chọn final binary và lưu evidence
    - package/verify đầy đủ theo policy

Deploy:
  tải đúng binary từ CI artifact/repository
  verify SHA-256/signature/provenance
  không chạy lại package một cách tùy ý
```

Một runner “có container mới” chưa chắc workspace sạch nếu workflow restore cache `target`, mount shared volume hoặc dùng self-hosted workspace. Phải kiểm tra những cache paths **thực tế**.

### 11.1. Chỉ cache `.m2` khi phù hợp

Cache dependency/plugin downloads thường là:

```text
~/.m2/repository
```

hoặc một repository local đặt bên trong workspace cho CI. Đây là **input cache**, không phải bản build output được phê duyệt.

Không dùng cache `target/` làm nguồn deploy; dễ restore JAR cũ. Dùng CI upload/download artifacts hoặc immutable Maven repository cho đúng file đã QA.

### 11.2. Cache miss khác stale output

Cache miss gây tải lại thư viện/plugin; nó không phải lỗi quality nếu build chạy đúng.

Stale output là một **file đang tồn tại không còn tương ứng inputs source/plugin hiện tại** nhưng vẫn được dùng/đóng gói/đọc. `clean` giải quyết nhiều loại stale output vì xóa build directory, nhưng không nhất thiết sửa dependency cache bị poison hoặc publisher artifact đã bị upload sai.

### 11.3. Publish binary theo digest

Với JAR cuối:

```bash
sha256sum target/clean-output-lab-1.0.0.jar
```

Trên macOS không có GNU coreutils, dùng:

```bash
shasum -a 256 target/clean-output-lab-1.0.0.jar
```

Trên Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\target\clean-output-lab-1.0.0.jar
```

Lưu digest trong CI run/release record, download file ở job sau và so digest. **Không cần dự đoán hash cụ thể** trong README vì nó phụ thuộc bytes output.

### 11.4. Dùng checksum đúng nguồn

Một file checksum nằm cùng ZIP/JAR trong một bundle có thể giúp phát hiện lỗi truyền hoặc nhầm file; tuy nhiên nếu attacker sửa được **cả JAR và checksum**, việc so hai thứ vẫn có thể PASS. Với production quan trọng, expected digest nên gắn trusted CI attestation/signature/release approval.

`clean verify` không tự tạo cryptographic authenticity. Clean build là bước quản lý state, còn provenance/signature là bước supply-chain security khác.

## 12. Multi-module Maven: tránh clean toàn bộ reactor khi chỉ cần một module

Một reactor có thể là:

```text
root-parent/           packaging=pom
├── shared-lib/        packaging=jar
├── core/              packaging=jar, depends on shared-lib
└── service/           packaging=jar, depends on core
```

Từ root:

```bash
mvn -B -pl :service -am test
```

`-pl :service` chọn module service; `-am` cũng build những project dependencies cần thiết trong reactor. Đây có thể là cách lấy phản hồi đúng cho thay đổi ở service/core mà không phải xử lý mọi module không liên quan.

**Nhưng:** `-am` có thể thêm cả modules upstream, và tests của những modules ấy có thể chạy theo lifecycle. Scope cần căn cứ vào dependency graph.

### 12.1. `-pl`, `-am` không thay thế consistency check

Nếu shared library API đổi và consumer còn `.class` cũ, giới hạn `-pl` sai có thể khiến bạn không kiểm thử tác động lên các modules phụ thuộc. Khi cần test downstream, có thể cân nhắc `-amd` hoặc một full reactor verification theo policy.

Dù scope chọn modules, quality gate cuối cùng của release nên QA mọi artifacts ảnh hưởng, không suy một module PASS ⇒ cả reactor PASS.

### 12.2. Clean có chọn lọc

Có thể thực hiện:

```bash
mvn -B -pl :service clean verify
```

để chỉ xử lý service nếu project thực sự độc lập và dependencies đã có/correct. Tuy nhiên nếu service phụ thuộc module khác chưa được install/resolve, lệnh có thể fail hoặc dùng local artifact cũ.

Một phương án:

```bash
mvn -B -pl :service -am clean verify
```

bao gồm các upstream reactor dependencies và sẽ clean **những modules được chọn**. Điều này tiết kiệm hơn clean tất cả khi không cần, nhưng trong release phải kiểm tra toàn bộ affected modules và đúng GAV/artifact set.

### 12.3. Parent module, aggregator và goal aggregate

Parent/aggregator có thể có reports hoặc goals aggregate, đôi khi cần chạy tại root hoặc toàn reactor để sinh đúng report. Nếu chỉ chọn một module, output aggregate có thể thiếu modules. Không xem `-pl` là tối ưu vô hại cho mọi Maven goal.

## 13. IDE và incremental build có thể khác Maven CLI

IDE như IntelliJ IDEA, Eclipse/m2e, VS Code Java có thể có compiler caches/incremental state riêng. Tùy cấu hình, IDE:

- Biên dịch vào `out/`, `bin/`, `target/classes` hoặc path khác.
- Delegate build/run/test tới Maven hoặc dùng IDE compiler/test runner.
- Có indexing caches độc lập.
- Dùng Maven local repository để resolve dependencies.
- Chạy Java từ IDE classpath mà chưa tạo executable JAR.

Vì vậy:

```text
Run trong IDE: PASS
```

không đồng nghĩa:

```text
mvn clean verify: PASS
```

hay:

```text
target/clean-output-lab-1.0.0.jar đã được cập nhật
```

### 13.1. Khi bị “ma class” trong IDE

Một lớp đã xóa khỏi source nhưng IDE vẫn autocomplete, test runner vẫn load hoặc runtime tìm thấy:

1. Xem IDE đang dùng output directory nào.
2. Xem Maven build dùng `target/classes` hay custom path.
3. Reimport Maven model/sync POM.
4. So Java/JDK/Maven distribution trong IDE với CLI.
5. Chạy `mvn clean verify` để cô lập Maven build state.
6. Kiểm tra `jar tf` trên **final JAR**.
7. Nếu IDE vẫn lỗi trong khi Maven CLI sạch, xử lý IDE-specific output/index.

**Invalidate IDE caches** không có nghĩa Maven `target/` hoặc `.m2` tự được dọn. Ba loại state này cần xử lý đúng nguyên nhân.

### 13.2. Không dùng Maven `clean` để xóa IDE index bừa

Các IDE caches có thể nằm ngoài project/Maven build directory. Đừng thêm `filesets` xóa toàn bộ IDE folders/HOME theo phỏng đoán; có thể làm mất user settings hoặc dữ liệu không liên quan.

## 14. Tối ưu performance đúng cách: đo trước khi thay đổi

Đừng đo bằng cảm giác. Chọn những chỉ số:

- Wall-clock duration tổng cho `compile`, `test`, `package`, `verify`.
- Compile duration/main vs test compile duration.
- Số sources thực sự được compile.
- Số tests chạy và thời gian.
- Cache hit/miss cho dependency downloads.
- Số modules của reactor tham gia.
- Tần suất output/metadata regeneration.
- CPU/memory/disk I/O, đặc biệt trên runner có antivirus hoặc network disk.
- SHA-256/contents của JAR nếu đang so binary outputs.

### 14.1. Linux/macOS measurement

Khi có shell hỗ trợ `time`:

```bash
time mvn -B test
time mvn -B test
time mvn -B clean test
```

Đây là **ba lần chạy khác điều kiện**: lần đầu có thể còn tải dependencies, lần hai warm caches và output, lần ba xóa build output. Không được kết luận chỉ từ một dãy này.

Thử nhiều lần với **cùng source/JDK/settings, cùng mức cache warm, không chạy parallel jobs**. Dùng median hoặc distribution thay vì một giá trị tốt nhất.

### 14.2. Windows PowerShell

```powershell
Measure-Command { mvn -B test }
Measure-Command { mvn -B clean test }
```

`Measure-Command` đo thời gian, nhưng vẫn phải kiểm tra Maven exit code/logs. Dù một lần đo thấy `test` nhanh hơn, điều đó không chứng minh tính đúng đắn của artifact khi source/resources/plugins đã thay đổi.

### 14.3. So sánh công bằng

| Điều kiện | Build incremental | Build clean |
| --- | --- | --- |
| Git commit/source | Cố định | Cùng commit |
| Maven/JDK/OS | Cố định | Cùng versions |
| Maven local dependency cache | Warm hoặc cold theo thiết kế | Cùng mức |
| Plugin versions/profiles | Giống | Giống |
| Tests | Cùng set, không skip tùy tiện | Cùng set |
| Workspace `target` | Có output hợp lệ từ run trước | Bị dọn trước build |
| Mục tiêu | Thời gian vòng development | Thời gian QA độc lập/sạch |

**Không so build không chạy tests với build có tests rồi gắn kết luận “clean gây chậm”.** Đó là hai tác vụ khác nhau.

## 15. Diagnostic tools: điều tra output trước khi xóa

### 15.1. Kiểm tra JAR entries

```bash
jar tf target/clean-output-lab-1.0.0.jar
```

Tìm:

- `.class` không còn source.
- Resources đã bỏ.
- `META-INF/services` cũ.
- `Main-Class`/manifest configuration bất ngờ.
- Entries từ plugin/transform cũ.

Nếu file tồn tại nhưng không có expected entry, có thể build chưa chạy tới phase package, jar plugin skipped, hoặc bạn đang chọn sai artifact.

### 15.2. Kiểm tra class được compiler tạo

Trên JDK17:

```bash
javap -classpath target/classes org.example.perf.HealthApp
```

`javap` cho biết class đang nằm trong output classpath. Nó không đọc Git source để khẳng định class vừa được compile ở lần gần nhất. Để so với source, dùng clean build hoặc kiểm tra bytecode/cấu trúc và build logs.

### 15.3. Xem plugin quyết định biên dịch/đóng gói

```bash
mvn -B compile
mvn -B package
```

Xem log Compiler Plugin và JAR Plugin: “Nothing to compile”, “Changes detected”, “Building jar” hoặc skipped creation (thông điệp cụ thể thay đổi theo versions).

Khi cần:

```bash
mvn -X package
```

`-X` in debug details, có thể lộ internal paths, repository URLs, proxy settings và metadata môi trường. Rà soát trước khi đăng log công khai.

### 15.4. Xem effective POM và lifecycle bindings

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

Kiểm tra:

- `project.build.directory`.
- Compiler/Resources/JAR/Surefire versions/config.
- `pluginManagement` và `build.plugins`.
- Active profiles.
- Custom executions bind vào phases.
- Clean Plugin `<filesets>`; có dọn ngoài `target` không.
- Shade/Assembly/Spring Boot plugin có post-process JAR không.

Không kết luận `clean` đang xóa đúng một thư mục nếu POM/parent có custom paths hoặc filesets.

## 16. Quy trình xử lý khi nghi ngờ đầu ra cũ

Một runbook thực tế:

**Bước 1 — Xác định symptom.**

```text
Class cũ vẫn tồn tại? Resource đã xóa vẫn trong JAR?
Unit test XML của suite cũ còn? JAR không cập nhật sau test?
Chỉ có lỗi trong IDE hay cả Maven CLI?
```

**Bước 2 — Ghi thông tin để tái hiện.** Lưu Git commit, Maven/JDK versions, POM/profiles, command và log; ghi file artifact đang kiểm tra.

**Bước 3 — Inspect trước khi xóa.** Dùng `jar tf`, `javap`, danh sách `target`, timestamps/checksum. Nếu sự cố quan trọng, lưu bản copy có kiểm soát của artifact lỗi để điều tra.

**Bước 4 — Làm clean verification.**

```bash
mvn -B clean verify
```

**Bước 5 — So sánh.** Kiểm tra JAR entries, test count, expected resources, SHA-256. Nếu lỗi biến mất sau clean, xác định plugin/output nào không được invalidated.

**Bước 6 — Sửa nguyên nhân.** Ví dụ đặt output generator dưới `target`, cấu hình cleanup, sửa glob/packaging, tránh restore `target` từ CI cache, nâng plugin/version theo policy hoặc buộc JAR recreation nếu Shade post-processing cần.

**Bước 7 — Đặt regression check.** Một CI job từ workspace sạch + assertion không có stale files và digest/version/provenance phù hợp sẽ ngăn lỗi tái diễn.

Đừng coi `mvn clean` là câu trả lời vĩnh viễn cho mọi lỗi; nó có thể che một custom plugin không xử lý xóa source/output đúng. Nên có regression test cho nguyên nhân thật.

## 17. Khi nào dùng targeted cleanup?

Đôi khi chỉ một output nhỏ bị stale và một full clean quá đắt. Khi **đã biết chính xác owner của file**, có thể xóa **đúng generated file/directory** rồi chạy phase tạo lại:

```bash
# Chỉ minh họa cho lab, không chạy trên project khác
rm -f target/classes/stale-marker.txt
mvn -B package
```

Trên PowerShell:

```powershell
Remove-Item -LiteralPath .\target\classes\stale-marker.txt
mvn -B package
```

**Không dùng command xóa rộng với path nhận từ biến không kiểm tra**, không xóa `src/`, HOME hoặc shared caches. Nếu output có liên hệ phức tạp với compiler, annotation processors hay checksum QA, **full `clean verify` dễ chứng minh tính đúng đắn hơn**.

### 17.1. Xóa `target/surefire-reports` có phải luôn đủ?

Không. Dọn reports cũ giúp tránh đọc XML cũ, nhưng không sửa class/resource stale. Với release build cần độc lập, clean toàn bộ build outputs vẫn là lựa chọn rõ ràng.

### 17.2. Đặt `clean` vào POM tự động mọi lần build có tốt không?

Không nên bind goal `clean` bừa vào default lifecycle. Điều đó làm mọi phase đều xóa incremental outputs, gây nhầm mô hình Maven clean/default lifecycle và có thể tạo vòng lặp khó đoán với plugins khác.

Hãy để CI/workflow chọn `mvn clean verify` khi cần; development chọn `mvn test` hoặc `mvn package`. Nếu project có output invalidation đặc biệt, giải quyết bằng chính plugin owner hoặc build policy được review.

## 18. Common mistakes và cách sửa

| Ngộ nhận / triệu chứng | Vì sao sai | Cách kiểm tra / giải pháp |
| --- | --- | --- |
| “Mọi lần sửa Java phải clean” | Compiler có incremental logic | Thử `mvn test`, inspect khi input thay cấu trúc |
| “Không clean luôn nhanh và đúng” | Stale outputs có thể tồn tại | Clean QA tại điểm cần, inspect final archive |
| `mvn test` có JAR mới | `test` không chạy phase `package` | Dùng `mvn package` |
| `BUILD SUCCESS` chứng minh JAR không có file cũ | Tests không enumerate mọi archive entry | `jar tf`/ArchiveProbe/QA |
| Xóa source Java, `.class` vẫn load | Output cũ còn hoặc IDE riêng | Clean, `javap`, kiểm classpath |
| Xóa resource nhưng vẫn trong JAR | Copied resource còn trong classes | Clean, kiểm content |
| Test suite đã xóa vẫn có XML | Report cũ trong folder | Fresh workspace/clean, count tests hiện tại |
| `-DskipTests` nhưng dashboard xanh | Đọc XML cũ hoặc skip không được báo | Fail khi tests thực tế không chạy |
| Jar Plugin không rebuild archive | Plugin cho inputs unchanged, Shade postprocess | Điều tra `forceCreation`/pipeline |
| `forceCreation=true` xóa stale class | Nó chỉ buộc tạo JAR mới | Dọn đúng source output |
| `outputTimestamp` loại stale files | Chỉ quản lý timestamp entries | So archive contents |
| `mvn clean` sẽ xóa `.m2` | Clean project outputs | Cache dependency còn |
| IDE cache và `target` là một | IDE có indexes/outputs riêng | Kiểm IDE Maven delegation |
| Clean mọi module cho thay đổi nhỏ | Có thể thừa I/O | `-pl`/`-am`, release gate đầy đủ |
| Chỉ chạy `compile` rồi upload JAR cũ | Chưa tới package | `package` + QA binary |
| CI cache `target` rồi lấy đó deploy | File có thể từ run cũ | Use artifact upload/download theo run |
| JAR cùng tên ⇒ bytes cùng | Timestamp/inputs/old output có thể khác | So SHA-256 |
| Xóa toàn bộ HOME để sửa Maven | Phá dependency cache/settings | Chỉ dọn path đã xác minh |
| Debug dùng `mvn -X` rồi share nguyên log | Có thể lộ thông tin nội bộ | Redact trước khi chia sẻ |
| Clean chạy trên root có custom filesets | Có thể xóa ngoài `target` | Xem effective POM trước |
| Một module PASS ⇒ reactor PASS | Modules downstream chưa được test | Reactor/affected modules QA |
| SHA-256 đủ chứng minh code an toàn | Hash chỉ so bytes | Tests, scanning, signature/provenance |
| Clean sau khi upload artifact | Không sửa file đã upload sai | Build lại, QA và publish đúng bytes |
| Release job đóng gói lại JAR | Có thể khác binary QA | Promote exact tested artifact |

## 19. Câu hỏi tự kiểm tra

**1.** `mvn test` có chạy `clean` không?  
**Đáp án:** Không mặc định. Clean lifecycle là riêng.

**2.** `mvn clean` có build lại JAR không?  
**Đáp án:** Không khi gọi một mình; nó chỉ thực hiện clean lifecycle.

**3.** `mvn clean verify` khác `mvn verify` thế nào?  
**Đáp án:** Lệnh đầu dọn build outputs trước default lifecycle tới verify.

**4.** `mvn clean` xóa dependency cache trong `~/.m2/repository` không?  
**Đáp án:** Không mặc định.

**5.** Vì sao development không nên always clean?  
**Đáp án:** Có thể mất lợi ích incremental compile/resources, tăng I/O và thời gian feedback.

**6.** Vì sao release thường cần fresh/clean build?  
**Đáp án:** Để không mang outputs từ run cũ sang published artifacts và dễ audit.

**7.** Compiler Plugin có `useIncrementalCompilation` mặc định là gì với 3.x/javac?  
**Đáp án:** `true` theo tài liệu của plugin 3.x.

**8.** Tại sao `useIncrementalCompilation=false` có rủi ro?  
**Đáp án:** Có thể không recompile classes phụ thuộc API vừa đổi, gây runtime linkage error.

**9.** `mvn test` có chắc tạo JAR mới sau sửa source không?  
**Đáp án:** Không; phase `package` chưa chạy.

**10.** `forceCreation` của JAR Plugin giải quyết việc gì?  
**Đáp án:** Buộc tái tạo archive dù input change detection cho rằng không cần.

**11.** `forceCreation=true` có xóa file cũ trong `target/classes` không?  
**Đáp án:** Không.

**12.** Vì sao JAR vẫn chạy đúng nhưng chưa chắc sạch?  
**Đáp án:** Có thể chứa entries thừa không được tests chạm tới.

**13.** Utility `ArchiveProbe` kiểm tra điều gì?  
**Đáp án:** Có class chính và có file `stale-marker.txt` trong JAR hay không.

**14.** Nếu sau khi chèn marker rồi chạy `mvn package`, kết quả kỳ vọng?  
**Đáp án:** `stale-marker=true` với POM/plugin lab đã nêu.

**15.** Nếu chạy `mvn clean verify` sau đó, kết quả kỳ vọng?  
**Đáp án:** `stale-marker=false`.

**16.** Vì sao không xác nhận tests chỉ bằng file `TEST-*.xml` đang có?  
**Đáp án:** Nó có thể thuộc suite/lần chạy cũ, nhất là khi không clean.

**17.** `project.build.outputTimestamp` có làm sạch resource cũ không?  
**Đáp án:** Không; nó hỗ trợ reproducible archive timestamps.

**18.** Multi-module dùng `-pl`/`-am` giúp gì?  
**Đáp án:** Giới hạn/bao gồm modules liên quan để tránh build toàn reactor không cần thiết.

**19.** `-pl :service -am clean verify` có luôn clean mọi module không?  
**Đáp án:** Không; nó áp vào reactor project selection được Maven đưa vào run.

**20.** Kiểm tra content JAR bằng lệnh nào?  
**Đáp án:** `jar tf path/to/file.jar`.

**21.** `javap` trả lời điều gì?  
**Đáp án:** Class files nào có mặt trên classpath được đọc, không chứng minh chúng mới compile.

**22.** Vì sao phải so digest của final JAR trước deploy?  
**Đáp án:** Để không triển khai một binary khác với bản được QA và phê duyệt.

**23.** Một CI workspace mới có cần clean không?  
**Đáp án:** Có thể không, nếu thật sự không chứa output cũ và policy cho phép; phải xét cache/mount.

**24.** Cache `.m2` và cache `target` khác nhau ra sao?  
**Đáp án:** `.m2` thường là dependencies/plugins inputs; `target` là output dễ stale nếu dùng chung.

**25.** Chỉ xóa `surefire-reports` có sửa stale `.class` không?  
**Đáp án:** Không.

**26.** Nếu clean mới làm lỗi biến mất, bước kế tiếp là gì?  
**Đáp án:** Điều tra plugin/output invalidation nguyên nhân, không dừng ở workaround.

**27.** `mvn clean install` có phải lựa chọn bắt buộc cho mỗi vòng sửa code không?  
**Đáp án:** Không; `install` ghi local artifacts và `clean` có thể thừa cho inner loop.

**28.** Lựa chọn chuẩn cho QA release kiểm tra đầu ra cũ?  
**Đáp án:** Build từ workspace sạch, `mvn clean verify`, inspect final JAR, tests và digest.

## 20. Checklist thực hành

- [ ] Nắm đúng clean lifecycle và default lifecycle.
- [ ] Phân biệt Maven local dependency cache với project `target`.
- [ ] Biết phase tối thiểu cần chạy cho mục tiêu hiện tại.
- [ ] Không gọi `clean install` ở mọi vòng sửa code nếu không cần.
- [ ] Không bỏ clean khi xóa/rename class/resource/generated output mà chưa xác minh.
- [ ] Không đặt `useIncrementalCompilation=false` một cách tùy tiện.
- [ ] Có kiểm soát plugin/JDK/compiler versions và đổi toolchain.
- [ ] Đã xác định đúng final JAR/WAR/other artifact.
- [ ] Khi chỉ chạy `test`, không giả định JAR đã package lại.
- [ ] Đã dùng `jar tf` hoặc utility để xem archive entries.
- [ ] Đã rà `target/classes` và resources không còn trong source.
- [ ] Reports Surefire/Failsafe được gắn với đúng CI run.
- [ ] Khi tests bị skip, không dùng XML cũ báo PASS.
- [ ] JAR Plugin `forceCreation` chỉ áp khi có lý do cụ thể.
- [ ] Reproducible timestamp không được coi là cleanup mechanism.
- [ ] CI release dùng workspace sạch hoặc explicit `clean`.
- [ ] CI cache không restore final output bừa vào `target/`.
- [ ] Nếu dùng multi-module, scope `-pl/-am` đúng và test modules ảnh hưởng.
- [ ] Có đo thời gian với cache/source/toolchain tương đương.
- [ ] Có guardrails cho `clean` custom filesets ngoài `target`.
- [ ] Không xóa `.m2`, IDE settings, shared workspaces vô cớ.
- [ ] Tính SHA-256 trên file **đã QA và sẽ publish**.
- [ ] Nếu artifact được promote sang job khác, so digest sau download.
- [ ] Giữ build logs/test count/provenance để audit.
- [ ] Có regression test khi đã tìm nguyên nhân stale output.
- [ ] Khi không chắc đầu ra có stale, ưu tiên build sạch để chốt đúng đắn trước tối ưu.

## 21. Nguồn tham khảo chính thức

1. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — clean/default/site lifecycle, các phases.
2. [Maven Clean Plugin 3.5.0 — clean:clean](https://maven.apache.org/plugins/maven-clean-plugin/clean-mojo.html) — default output dirs, filesets, clean behavior.
3. [Maven Clean Plugin — Usage](https://maven.apache.org/plugins/maven-clean-plugin/usage.html) — chạy goal/lifecycle.
4. [Maven Compiler Plugin 3.x — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html) — `useIncrementalCompilation`.
5. [Maven Compiler Plugin — Using different JDKs](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html) — toolchains/compiler environment.
6. [Maven JAR Plugin — jar:jar](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html) — `forceCreation`, output JAR, `outputTimestamp`.
7. [Maven Surefire Plugin — Overview](https://maven.apache.org/surefire/maven-surefire-plugin/) — unit tests, XML reports.
8. [Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html) — report directory, test execution parameters.
9. [Maven Resources Plugin — Resources Goal](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html) — resource copying/filtering.
10. [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — reproducibility/output timestamps.
11. [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — build directory, plugin configuration, resources.
12. [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — reactor, `-pl`, `-am`, `-amd`.
13. [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html) — JDK selection.
14. [Java SE 17 — Single-File Source-Code Programs](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — `java File.java args`.
15. [Java SE 17 — JarFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html) — inspecting JAR entries.

**Kết luận:** **Không chạy `clean` như phản xạ trước mọi thay đổi nhỏ**, vì điều đó làm mất lợi thế incremental build và kéo dài vòng feedback. Nhưng **không dùng kết quả `BUILD SUCCESS` để phủ nhận khả năng đầu ra cũ**: hãy kiểm `target/classes`, packaged JAR, resources và test reports; dùng `mvn clean verify` khi source/output không còn nhất quán hoặc trước release. Chỉ bàn giao **final artifact đã được QA và đối chiếu digest**, không phải một JAR may mắn còn trong `target/` từ lần trước.
