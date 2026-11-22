# Xuất bản thư viện vào kho thử nghiệm và dùng từ dự án khác với Maven

## 1. Bài thực hành tổng hợp cần chứng minh điều gì?

Đây là bài **Thực hành tổng hợp** của chủ đề **Build Tool Maven**. Bạn sẽ đóng vai hai nhóm phát triển:

- **Nhóm A** tạo thư viện Java `calc-kit` có public API, viết unit tests, đóng gói và **xuất bản** artifact vào một Maven repository thử nghiệm.
- **Nhóm B** tạo một Maven project hoàn toàn độc lập, khai dependency bằng `groupId:artifactId:version`, **tải lại artifact từ repository** và dùng API của thư viện trong code Java.

Bài kiểm cuối cùng không chỉ là “producer chạy `BUILD SUCCESS`”. Nó còn phải chứng minh consumer **không dùng nhầm JAR được cài sẵn trong local repository** của producer hoặc một module cùng reactor.

```text
calc-kit-library (project độc lập)
  | Java 17 + JUnit 5
  | mvn clean verify      -> JAR, POM, sources JAR
  | mvn clean deploy      -> deploy to file:// sandbox
  v
Sandbox Maven repository (remote-style, trên filesystem)
  | GAV: dev.example.training.mavenlab:calc-kit:1.0.0
  | calc-kit-1.0.0.jar
  | calc-kit-1.0.0.pom
  | calc-kit-1.0.0-sources.jar
  v
calc-kit-consumer (project Maven khác)
  | chỉ khai repository URL và GAV
  | local Maven repository riêng, ban đầu không có calc-kit
  | mvn clean verify
  v
consumer: double(21)=42
```

Bài dùng **Apache Maven 3.9.x**, **JDK 17**, **Maven Deploy Plugin 3.2.0** và **JUnit Jupiter 5.11.4**. Đích xuất bản là `file://`, không phải Maven Central/Nexus/Artifactory thật. Đây là một protocol repository được Maven hỗ trợ, giúp trải nghiệm publish/resolve giống cách dùng kho qua HTTPS nhưng không cần server hay token.

### Mục tiêu sau bài

1. Phân biệt `package`, `verify`, `install`, `deploy` và `deploy-file`.
2. Hiểu GAV và layout đường dẫn artifact.
3. Tạo thư viện có source, 4 JUnit tests và source JAR đính kèm.
4. Publish JAR + POM + attached artifacts vào sandbox repository.
5. Tạo consumer độc lập với dependency Maven chuẩn, không có `systemPath`.
6. Chỉ định repository đọc bằng `<repositories>` và property CLI.
7. Dùng local repo cách ly để **chứng minh artifact đến từ sandbox**.
8. Chạy consumer compile/tests/app với stdout chính xác.
9. Kiểm `dependency:tree`, `jar tf`, checksums và các lỗi thường gặp.
10. Biết cách versioning, nâng phiên bản, xử lý SNAPSHOT, CI permissions và credential management.

## 2. Khái niệm: POM, JAR, Maven repository và coordinates

### 2.1. GAV — danh tính của thư viện

Một dependency được nhận diện bởi ba thành phần chính:

```text
groupId    = dev.example.training.mavenlab
artifactId = calc-kit
version    = 1.0.0
type       = jar
```

Dạng biểu diễn artifact đầy đủ có thể là:

```text
dev.example.training.mavenlab:calc-kit:jar:1.0.0
```

`groupId` thường mô tả namespace của tổ chức/nhóm và được đổi từ dấu chấm sang folder separator. `artifactId` là tên thư viện. `version` giúp người tiêu thụ chọn chính xác bản họ cần, thay vì tự lấy “bản mới nhất”.

### 2.2. Repository layout

Với GAV trên, sandbox sẽ chứa ít nhất các file:

```text
<repository-root>/
└── dev/
    └── example/
        └── training/
            └── mavenlab/
                └── calc-kit/
                    └── 1.0.0/
                        ├── calc-kit-1.0.0.jar
                        ├── calc-kit-1.0.0.pom
                        └── calc-kit-1.0.0-sources.jar
```

Maven có thể tạo `maven-metadata.xml` và các checksum sidecar files khác. Không coi chỉ có đúng ba file là điều kiện cần. Điều quan trọng là **artifact chính, POM metadata và classifier sources đã được publish đúng tọa độ**.

### 2.3. Local repository khác repository để chia sẻ

| Vị trí | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Local của producer | `~/.m2/repository` | Cache dependencies và artifacts được install trên máy A |
| Sandbox repository | `file:///tmp/maven-calc-lab-repo` | Nơi A publish để B tải |
| Local cách ly của consumer | `/tmp/maven-calc-consumer-m2` | Cache riêng, tạo phép thử không phụ thuộc producer |
| Maven Central/mirror | HTTPS repository | Nơi tải Maven plugins/JUnit dùng trong demo |

Maven xem repository `file://` là **remote repository theo chức năng resolve/deploy**, dù vật lý ở cùng máy. Để giả lập hai máy mà không cần chạy hai máy thật, ta dùng các local repository tách biệt.

### 2.4. Vì sao JAR thôi chưa đủ?

Binary JAR có class files cho Java compiler và runtime. Nhưng **POM** mô tả GAV, packaging, dependencies, scopes và metadata. Nếu producer chỉ copy JAR bằng tay mà không deploy POM, consumer có thể không resolve được transitive dependencies hoặc Maven báo artifact descriptor missing.

Source JAR là artifact **đính kèm** có classifier `sources`, giúp IDE xem source. Nó không thay binary JAR và không được Maven compiler dùng thay JAR chính.

## 3. Chuẩn bị môi trường, phạm vi và cấu trúc

### 3.1. Kiểm công cụ

```bash
mvn -version
java -version
```

`mvn -version` phải chỉ ra Maven 3.9.x chạy bằng JDK 17 trở lên cho ví dụ. Java 17 hỗ trợ `Math.multiplyExact` được dùng trong thư viện. Maven plugins/JUnit có thể cần tải từ Central hoặc mirror; sandbox file repository không thay thế các kho công khai đó.

**Lưu ý an toàn:** Không đưa credentials thật vào POM hoặc command demo. Chỉ chạy `deploy` với `-DaltDeploymentRepository` trỏ đúng folder sandbox. Nếu dùng parent POM công ty có `distributionManagement`, kiểm effective POM để tránh vô ý publish tới production.

### 3.2. Cấu trúc hai project tách rời

```text
maven-publish-consume-lab/
├── calc-kit-library/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/example/mavenlab/calc/SafeMath.java
│       └── test/java/dev/example/mavenlab/calc/SafeMathTest.java
└── calc-kit-consumer/
    ├── pom.xml
    └── src/
        ├── main/java/dev/example/mavenlab/app/ConsumerMain.java
        └── test/java/dev/example/mavenlab/app/ConsumerMainTest.java
```

**Không có POM aggregator root** và không có `<modules>` ghép hai projects. Library và consumer có `pom.xml` riêng, phải chạy Maven ở từng thư mục. Điều này quan trọng vì một reactor multi-module có thể resolve sibling project trực tiếp mà chưa cần remote repository; như vậy không chứng minh được bài toán chia sẻ artifact.

## 4. Project A — POM thư viện hoàn chỉnh

Tạo `calc-kit-library/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example.training.mavenlab</groupId>
    <artifactId>calc-kit</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Calc Kit Training Library</name>
    <description>Java 17 utility library used in Maven repository lab</description>

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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.3.1</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.1. Hiểu POM producer

- `groupId:artifactId:version` quyết định thư mục repository.
- `packaging=jar` kích hoạt lifecycle phù hợp: compile, test, package JAR.
- `maven.compiler.release=17` xác định bytecode API mức Java 17.
- `junit-jupiter` chỉ có scope **test** nên không thành runtime transitive dependency của consumer.
- `maven-surefire-plugin` chạy JUnit tests có tên `*Test`.
- `maven-source-plugin:jar-no-fork` bind phase `package` để tạo **attached** `calc-kit-1.0.0-sources.jar`.
- `maven-deploy-plugin:3.2.0` xử lý publish theo `id::url`.
- Không có `distributionManagement` hay tokens vì lab cố ý yêu cầu chỉ định đích rõ ràng trên CLI.

**Sự khác nhau giữa plugin và dependency:** `maven-deploy-plugin` là build plugin của producer, không xuất hiện như một compile dependency trong `pom.xml` của consumer. Maven plugins làm việc trong lifecycle; Java application libraries được khai dưới `<dependencies>`.

### 4.2. Tại sao không cấu hình Maven Central ở đây?

Maven Central có yêu cầu xác minh namespace, metadata, signing/publisher protocol và quyền publish riêng. Bài chỉ cần hiểu cơ chế Maven artifact repository, không phải xin tài khoản Central. `file://` giúp thử quy trình một cách an toàn mà không tạo một GAV thật trên Internet.

## 5. Project A — Java source và unit tests

### 5.1. SafeMath.java

Tạo `calc-kit-library/src/main/java/dev/example/mavenlab/calc/SafeMath.java`:

```java
package dev.example.mavenlab.calc;

public final class SafeMath {

    private SafeMath() {
    }

    public static int doubleExact(int value) {
        return Math.multiplyExact(value, 2);
    }

    public static String describe(int value) {
        return "double(" + value + ")=" + doubleExact(value);
    }
}
```

Library có public API `doubleExact(int)` và `describe(int)`:
- Với input `21`, `doubleExact` trả 42 và `describe` trả chính xác `double(21)=42`.
- `Math.multiplyExact` ném `ArithmeticException` khi số nguyên bị tràn, tránh kết quả overflow không phát hiện.
- Class không phụ thuộc thư viện ngoài Java 17.
- Constructor private phù hợp utility class chỉ chứa static methods.

### 5.2. SafeMathTest.java

Tạo `calc-kit-library/src/test/java/dev/example/mavenlab/calc/SafeMathTest.java`:

```java
package dev.example.mavenlab.calc;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class SafeMathTest {

    @Test
    void doublesPositiveNumber() {
        assertEquals(42, SafeMath.doubleExact(21));
    }

    @Test
    void doublesNegativeNumber() {
        assertEquals(-6, SafeMath.doubleExact(-3));
    }

    @Test
    void describesValue() {
        assertEquals("double(21)=42", SafeMath.describe(21));
    }

    @Test
    void reportsOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> SafeMath.doubleExact(Integer.MAX_VALUE));
    }
}
```

Đây là **4 JUnit Jupiter unit tests**. Hãy giữ tests trong `src/test/java` đúng package và tên `*Test`. Nếu log báo `Tests run: 0`, đó không phải kết quả mong đợi dù Maven vẫn có thể in BUILD SUCCESS.

### 5.3. Verify trước khi publish

Từ `calc-kit-library`:

```bash
mvn -B -ntp clean verify
```

Đây là lệnh chạy build lifecycle đến `verify`, chưa thực hiện `install` hoặc `deploy`.

Tóm tắt log kỳ vọng, không phải bản chép nguyên console:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Các artifact chính trong `target`:

```text
target/
├── calc-kit-1.0.0.jar
├── calc-kit-1.0.0-sources.jar
├── classes/
├── test-classes/
└── surefire-reports/
```

Các files bổ sung như Maven status/metadata có thể xuất hiện tùy plugin.

### 5.4. Kiểm binary và sources JAR

```bash
jar tf target/calc-kit-1.0.0.jar
jar tf target/calc-kit-1.0.0-sources.jar
```

Trong binary JAR cần có:

```text
dev/example/mavenlab/calc/SafeMath.class
```

Trong source JAR cần có:

```text
dev/example/mavenlab/calc/SafeMath.java
```

Đây là các **dòng đại diện trong listings**, không phải toàn bộ output. Nếu chỉ thấy `SafeMath.java` mà không có `SafeMath.class` trong JAR chính, consumer không thể compile API qua dependency bình thường.

## 6. Tạo sandbox Maven repository trên Linux/macOS

### 6.1. Chuẩn bị folder

```bash
mkdir -p /tmp/maven-calc-lab-repo
```

Đây là một folder thử nghiệm, không chứa thông tin production. URI tương ứng:

```text
file:///tmp/maven-calc-lab-repo
```

Maven repository layout sẽ được tạo dưới folder này. Trước khi chạy, xác nhận path đúng và writable. **Không sử dụng `~/.m2/repository` làm đích deploy**, vì đó là local cache chứ không phải kho chia sẻ.

### 6.2. Deploy bằng Maven Deploy Plugin 3.2.0

Trong `calc-kit-library`:

```bash
mvn -B -ntp clean deploy \
  '-DaltDeploymentRepository=training-sandbox::file:///tmp/maven-calc-lab-repo'
```

Theo Apache Maven Deploy Plugin 3.x, `altDeploymentRepository` dùng format:

```text
-DaltDeploymentRepository=id::url
```

Ở đây:
- `training-sandbox` là **repository ID**;
- `file:///tmp/maven-calc-lab-repo` là URL filesystem repository;
- `::` là hai dấu hai chấm ngăn cách;
- không dùng format plugin 2.x `id::layout::url`.

**Vì sao `clean deploy` chứ không chỉ `deploy:deploy`?** `mvn clean deploy` chạy compile/tests/package và phase deploy theo Maven lifecycle, nên tạo main JAR và source JAR trước upload. Gọi `deploy:deploy` trực tiếp không tự bảo đảm source đã compile và artifacts đã package.

### 6.3. Mối quan hệ install và deploy

Trong Maven 3 default lifecycle, `deploy` ở sau `install`. `mvn clean deploy` có thể:
- tạo JAR/POM/sources;
- chạy 4 tests;
- install artifacts vào **local repository của producer**;
- deploy artifacts vào sandbox repository.

Vì thế việc consumer chạy cùng local repository producer **không chứng minh** repository sandbox hoạt động. Phần 9 sẽ dùng một local Maven repository mới riêng biệt.

### 6.4. Kiểm files trong sandbox

```bash
find /tmp/maven-calc-lab-repo -type f
```

Những đường dẫn quan trọng:

```text
/tmp/maven-calc-lab-repo/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.jar
/tmp/maven-calc-lab-repo/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.pom
/tmp/maven-calc-lab-repo/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0-sources.jar
```

Có thể tồn tại `maven-metadata.xml` và checksum sidecars. Không đòi danh sách file chính xác giống nhau trên mọi Maven/Resolver transport versions; điều cần kiểm là **3 artifact files trên có thật và thuộc đúng GAV**.

### 6.5. So bytes của artifact

```bash
cmp target/calc-kit-1.0.0.jar \
  /tmp/maven-calc-lab-repo/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.jar
```

Với hai binary files giống nhau, `cmp` trả exit code 0 và không in nội dung.

```bash
sha256sum target/calc-kit-1.0.0.jar
sha256sum /tmp/maven-calc-lab-repo/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.jar
```

Nếu bytes khớp, hai SHA-256 digests khớp. Chúng phụ thuộc artifact cụ thể, không nên tự bịa checksum vào tài liệu. **Hash chứng minh equality/integrity theo bytes, không xác thực danh tính người đã publish**.

## 7. Windows PowerShell: deploy tới file:// an toàn

Nếu dùng Windows, chọn folder:

```powershell
New-Item -ItemType Directory -Force -Path 'C:\Temp\maven-calc-lab-repo' |
    Out-Null
```

Trong `calc-kit-library` chạy:

```powershell
mvn -B -ntp clean deploy '-DaltDeploymentRepository=training-sandbox::file:///C:/Temp/maven-calc-lab-repo'
```

Đường dẫn filesystem `C:\Temp\maven-calc-lab-repo` và URI `file:///C:/Temp/maven-calc-lab-repo` là hai cách biểu diễn khác nhau. URI dùng dấu `/`, không dùng `file://C:\Temp\...`. Hãy tạo folder trước và bảo đảm user có quyền ghi.

Kiểm kết quả:

```powershell
Get-ChildItem -LiteralPath 'C:\Temp\maven-calc-lab-repo' -Recurse -File
Get-FileHash 'target\calc-kit-1.0.0.jar' -Algorithm SHA256
Get-FileHash 'C:\Temp\maven-calc-lab-repo\dev\example\training\mavenlab\calc-kit\1.0.0\calc-kit-1.0.0.jar' -Algorithm SHA256
```

Hai file JAR có Hash giống nhau khi nội dung deployment đúng. Trên Windows Shell truyền tham số Maven với single quotes ở PowerShell; CMD có quy tắc quotes khác, nên trong CMD dùng double quotes. Không copy một `file:///C:/...` vào Linux mà không sửa đường dẫn.

## 8. Project B — POM consumer hoàn chỉnh

Tạo `calc-kit-consumer/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example.training.mavenlab</groupId>
    <artifactId>calc-kit-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <repositories>
        <repository>
            <id>training-sandbox</id>
            <url>${lab.repo.url}</url>
            <releases>
                <enabled>true</enabled>
            </releases>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>dev.example.training.mavenlab</groupId>
            <artifactId>calc-kit</artifactId>
            <version>1.0.0</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

### 8.1. Cách consumer tìm được library

- `<repositories>` khai **nơi Maven tải dependencies**. Nó không dùng để publish.
- `<url>${lab.repo.url}</url>` là property Maven được cung cấp bằng CLI: `-Dlab.repo.url=file:///tmp/maven-calc-lab-repo`. **Không bỏ qua tham số**; nếu property chưa được thay, URL chưa hợp lệ cho sandbox.
- `releases=true` tương ứng thư viện `1.0.0` không phải SNAPSHOT.
- Dependency `calc-kit` có default scope **compile**, vì không khai `<scope>`.
- JUnit là test dependency **của chính consumer**; scope `test` trong producer không được truyền cho consumer như runtime dependency.
- Không có `systemPath` hay source của `SafeMath` trong consumer.
- Không có `distributionManagement`, vì consumer đang **dùng** library chứ không publish library.

### 8.2. Vì sao property URL tốt hơn hard-code?

Linux/macOS và Windows có file paths khác nhau, nhưng consumer POM vẫn giống nhau. Bằng cách truyền `-Dlab.repo.url=...`, bạn có thể đổi sandbox root mà không sửa tọa độ hay Java source. Trong production, nhiều nhóm lấy repository URL từ parent POM hoặc settings/mirror policy thay vì CLI; trong bài tập, property tường minh giúp dễ kiểm sai/đúng.

## 9. Project B — Java code và unit tests

### 9.1. ConsumerMain.java

Tạo `calc-kit-consumer/src/main/java/dev/example/mavenlab/app/ConsumerMain.java`:

```java
package dev.example.mavenlab.app;

import dev.example.mavenlab.calc.SafeMath;

public final class ConsumerMain {

    private ConsumerMain() {
    }

    public static String report(int value) {
        return "consumer: " + SafeMath.describe(value);
    }

    public static void main(String[] args) {
        System.out.println(report(21));
    }
}
```

Import `SafeMath` chỉ hợp lệ khi thư viện `calc-kit:1.0.0` nằm trên Maven compile classpath. Consumer **không nhìn thấy file SafeMath.java gốc**; nó biên dịch dựa trên public class trong binary JAR.

Với đúng thư viện, stdout chính xác:

```text
consumer: double(21)=42
```

### 9.2. ConsumerMainTest.java

Tạo `calc-kit-consumer/src/test/java/dev/example/mavenlab/app/ConsumerMainTest.java`:

```java
package dev.example.mavenlab.app;

import dev.example.mavenlab.calc.SafeMath;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class ConsumerMainTest {

    @Test
    void usesPublishedApi() {
        assertEquals(
                "consumer: double(21)=42",
                ConsumerMain.report(21));
    }

    @Test
    void supportsNegativeInput() {
        assertEquals(
                "consumer: double(-3)=-6",
                ConsumerMain.report(-3));
    }

    @Test
    void checksOverflowContract() {
        assertThrows(
                ArithmeticException.class,
                () -> SafeMath.doubleExact(Integer.MAX_VALUE));
    }
}
```

Có **3 tests**. Test đầu kiểm public API producer được gọi trong consumer; test hai kiểm giá trị âm; test ba xác nhận overflow contract. Chúng không dùng source copy hoặc file path của thư viện producer. Nếu consumer resolve nhầm version có API khác, compile/test sẽ giúp phát hiện.

## 10. Consumer phải dùng local Maven repository cách ly

### 10.1. Chiếc bẫy của mvn install

Vì producer gọi `mvn clean deploy`, Maven 3 lifecycle cũng đi qua `install`. Artifact `calc-kit:1.0.0` có thể xuất hiện ở:

```text
~/.m2/repository/dev/example/training/mavenlab/calc-kit/1.0.0/
```

Nếu ngay sau đó chạy consumer với local repo mặc định, Maven có thể dùng JAR này mà **không truy vấn sandbox**. Build consumer PASS khi đó chứng minh Java dependency resolution từ local cache, **không chứng minh đã publish thành công ra nơi chia sẻ**.

**Giải pháp:** truyền một local repository khác, mới cho consumer, bằng `-Dmaven.repo.local`. Nó có thể cần tải lại Maven plugins và JUnit từ Central/mirror; đó là hoạt động bình thường.

### 10.2. Linux/macOS — chạy consumer

Từ `calc-kit-consumer`, sau khi producer deploy thành công:

```bash
mvn -B -ntp \
  '-Dmaven.repo.local=/tmp/maven-calc-consumer-m2' \
  '-Dlab.repo.url=file:///tmp/maven-calc-lab-repo' \
  clean verify
```

Để chứng minh lần đầu thật sạch, folder `/tmp/maven-calc-consumer-m2` phải **chưa có GAV calc-kit:1.0.0**. Nếu từng chạy bài, dùng một tên folder mới; không xóa toàn `~/.m2`. Maven sẽ:
1. Đọc POM consumer.
2. Thay `${lab.repo.url}` bằng `file:///tmp/maven-calc-lab-repo`.
3. Resolve GAV `dev.example.training.mavenlab:calc-kit:1.0.0`.
4. Tìm JAR/POM ở sandbox rồi đưa vào local cache của consumer.
5. Tải các Maven plugins/JUnit chưa có từ Central/mirror.
6. Compile consumer và chạy 3 unit tests.

Tóm tắt log kỳ vọng:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là tóm tắt, log thật có thể nhiều dòng downloading và plugin executions khác.

### 10.3. Kiểm local repository của consumer

```bash
find /tmp/maven-calc-consumer-m2/dev/example/training/mavenlab/calc-kit -type f
```

Kiểm ít nhất:

```text
/tmp/maven-calc-consumer-m2/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.jar
/tmp/maven-calc-consumer-m2/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.pom
```

Source JAR **không nhất thiết tự được tải**: Maven compile/test cần binary JAR, không cần source JAR. IDE/goal resolve-sources có thể yêu cầu sources riêng.

### 10.4. Chạy consumer từ binary JAR đã tải về

```bash
java -cp \
  'target/classes:/tmp/maven-calc-consumer-m2/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.jar' \
  dev.example.mavenlab.app.ConsumerMain
```

Stdout chính xác:

```text
consumer: double(21)=42
```

`target/classes` chứa `ConsumerMain`; đường dẫn thứ hai là **artifact tải về local cache riêng của consumer**. Không dùng `calc-kit-library/target/calc-kit-1.0.0.jar` trong classpath, vì như vậy bypass Maven repository.

**Vì sao không dùng java -jar?** POM consumer chưa khai `Main-Class` trong manifest; default JAR cũng không tự đóng gói dependencies. `java -cp` mô tả chính xác runtime classpath cần thiết. Trong project thật có thể dùng Maven Exec Plugin hoặc application packaging riêng, nhưng không cần để hoàn thành phép thử publish/consume.

### 10.5. Windows PowerShell — consumer

Trong `calc-kit-consumer`:

```powershell
mvn -B -ntp '-Dmaven.repo.local=C:\Temp\maven-calc-consumer-m2' '-Dlab.repo.url=file:///C:/Temp/maven-calc-lab-repo' clean verify
```

Kiểm repository:

```powershell
Get-ChildItem -LiteralPath 'C:\Temp\maven-calc-consumer-m2\dev\example\training\mavenlab\calc-kit\1.0.0' -File
```

Chạy Java với classpath separator `;` trên Windows:

```powershell
java -cp 'target\classes;C:\Temp\maven-calc-consumer-m2\dev\example\training\mavenlab\calc-kit\1.0.0\calc-kit-1.0.0.jar' dev.example.mavenlab.app.ConsumerMain
```

Stdout giống Linux: `consumer: double(21)=42`. Nếu không có quyền tạo `C:\Temp`, dùng một folder được phép trong `$env:TEMP` và chỉnh đồng bộ cả producer sandbox URL lẫn consumer local repo path. Không copy nguyên path Windows sang macOS.

## 11. Kiểm dependency:tree và artifact contents

### 11.1. Dependency graph của consumer

Với consumer, dùng plugin version cố định:

```bash
mvn -B -ntp \
  '-Dmaven.repo.local=/tmp/maven-calc-consumer-m2' \
  '-Dlab.repo.url=file:///tmp/maven-calc-lab-repo' \
  org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
```

Dòng thể hiện quan hệ trực tiếp dự kiến:

```text
[INFO] dev.example.training.mavenlab:calc-kit-consumer:jar:1.0.0
[INFO] +- dev.example.training.mavenlab:calc-kit:jar:1.0.0:compile
```

Đây là **fragment của Maven log**, không phải toàn bộ log. Còn có các nhánh JUnit test dependencies và các transitive artifacts tương ứng. Tên version/type/scope của `calc-kit` phải khớp consumer POM.

### 11.2. Kiểm JAR trong local cache consumer

```bash
jar tf /tmp/maven-calc-consumer-m2/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.jar
```

Phải tìm được:

```text
dev/example/mavenlab/calc/SafeMath.class
```

Nếu file tồn tại nhưng class không có, có thể producer đóng gói sai artifact hoặc consumer tải một bản khác dưới cùng coordinates.

### 11.3. So SHA-256 giữa sandbox và consumer

```bash
sha256sum /tmp/maven-calc-lab-repo/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.jar
sha256sum /tmp/maven-calc-consumer-m2/dev/example/training/mavenlab/calc-kit/1.0.0/calc-kit-1.0.0.jar
```

Hashes khớp khi byte nội dung khớp; không dựa vào việc hai filenames giống nhau. SHA-256 kiểm **toàn vẹn file**, nhưng không chứng minh publisher có danh tính tin cậy hay artifact không chứa mã độc.

Trên PowerShell:

```powershell
Get-FileHash 'C:\Temp\maven-calc-lab-repo\dev\example\training\mavenlab\calc-kit\1.0.0\calc-kit-1.0.0.jar' -Algorithm SHA256
Get-FileHash 'C:\Temp\maven-calc-consumer-m2\dev\example\training\mavenlab\calc-kit\1.0.0\calc-kit-1.0.0.jar' -Algorithm SHA256
```

### 11.4. Tại sao không hard-code số file trong repository?

Maven Deploy Plugin và Resolver có thể tạo checksums, metadata và local tracking files. SNAPSHOT còn có timestamped versions và `maven-metadata.xml`. Quan trọng là artifact/path đúng và consumer thực sự compile/test. Không coi “bắt buộc đúng 3 files” là QA rule.

## 12. Negative test: giả lập URL sai và local cache mới

Để kiểm hành vi thực sự phụ thuộc sandbox URL, dùng một local Maven cache **mới khác** và URL không có thư viện:

```bash
mvn -B -ntp \
  '-Dmaven.repo.local=/tmp/maven-calc-consumer-negative' \
  '-Dlab.repo.url=file:///tmp/maven-calc-lab-repo-missing' \
  clean verify
```

**Đây là thí nghiệm lỗi có chủ đích, không phải lệnh thành công**. Với GAV mẫu không được publish ở repository khác và cache vừa tạo, Maven dự kiến fail khi resolve `calc-kit:1.0.0`. Maven có thể vẫn download public plugins/JUnit trước đó; lỗi này không thể được dùng để kết luận “Java source sai”.

Nếu lệnh sai URL mà vẫn PASS, kiểm:
- repo mới thật sự trống đối với calc-kit chưa?
- organization mirror hoặc alternate repository có cùng GAV không?
- consumer vẫn chạy từ đúng directory/POM chứ?
- Có `systemPath`, IDE-added library hay modules reactor phụ trợ không?
- `settings.xml` hoặc parent POM còn repository khác không?

**Không xóa hoặc sửa production repository để làm negative test.** Sử dụng một GAV và một local cache sandbox mới.

## 13. DistributionManagement vs repositories vs settings.xml

### 13.1. distributionManagement phục vụ publish

Trong project thật có repository manager, producer có thể khai:

```xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repository.example.invalid/releases</url>
    </repository>
    <snapshotRepository>
        <id>team-snapshots</id>
        <url>https://repository.example.invalid/snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

**Đây là fragment minh họa, không phải file POM lab và URL `example.invalid` không hoạt động.** `mvn deploy` dùng `distributionManagement` để chọn đích nếu không có alternate deployment target được áp dụng.

### 13.2. repositories phục vụ dependency download

Consumer dùng:

```xml
<repositories>
    <repository>
        <id>team-releases</id>
        <url>https://repository.example.invalid/releases</url>
    </repository>
</repositories>
```

`<repositories>` không tự cấp quyền upload. Nó chỉ cho Maven biết nơi **resolve** artifact khi local cache chưa có.

**Ghi nhớ:** `distributionManagement` của producer không được truyền tự động vào consumer POM. Consumer cần cấu hình đọc qua POM/parent/settings/mirror hoặc có repository công khai phù hợp.

### 13.3. Credentials ở settings.xml

Với một HTTPS registry bảo vệ:

```xml
<settings>
    <servers>
        <server>
            <id>team-releases</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Đây là file `settings.xml` **minh họa**, không đưa vào repository source công khai. `server/id` phải khớp repository ID được dùng khi Maven deploy, và credentials được cấp qua CI secret manager/user settings.

Trong sandbox file://, không cần server credentials: file permissions của OS quyết định khả năng ghi/đọc. Nếu Maven báo 401/403 trên HTTPS registry thật, kiểm server ID, permission/ACL và token scope; không dùng token production để thử trên PR chưa review.

### 13.4. altDeploymentRepository có thể override đích

```text
-DaltDeploymentRepository=training-sandbox::file:///tmp/maven-calc-lab-repo
```

Định dạng `id::url` áp dụng cho Maven Deploy Plugin 3.x. Plugin 2.x trước đây dùng `id::layout::url`; copy nhầm format làm deploy fail. Với server credentials thật, không gán repository ID có token production vào một URL tùy tiện: một số plugin version có protections chống credential reuse, nhưng policy/CLI review vẫn là bắt buộc.

## 14. package, verify, install, deploy và deploy-file

| Maven command | Hoạt động | Repository side effect |
| --- | --- | --- |
| `mvn clean package` | Compile/test/package JAR | Không tự install/deploy |
| `mvn clean verify` | Package rồi chạy verify goals | Không tự install/deploy |
| `mvn clean install` | Verify + cài artifacts | Ghi local Maven repository |
| `mvn clean deploy` | Lifecycle đến deploy | Ghi remote repository theo config, trong Maven 3 còn đi qua install |
| `mvn deploy:deploy-file` | Upload một artifact file có sẵn | Không tự bảo đảm chạy compile/tests của project |

### 14.1. deploy:deploy-file dùng cho artifact có sẵn

Ví dụ chỉ mang tính cú pháp:

```bash
mvn org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file \
  '-Dfile=/absolute/path/to/third-party.jar' \
  '-DpomFile=/absolute/path/to/third-party.pom' \
  '-DrepositoryId=training-sandbox' \
  '-Durl=file:///tmp/maven-calc-lab-repo'
```

**Không thể chạy nguyên văn** vì đường dẫn `third-party.jar`/`.pom` chỉ là minh họa. Goal này hữu ích khi bên thứ ba cung cấp JAR/POM nhưng không có source Maven project. Còn project `calc-kit-library` của bài có POM đầy đủ và attached sources, nên **`mvn clean deploy`** mới là lựa chọn phù hợp.

### 14.2. Install không phải xuất bản liên máy

Một developer chạy `mvn install` rồi ngay lập tức build consumer trên chính máy đó có thể lầm tưởng thành công publish. Thực ra artifact chỉ tồn tại trong local repository của developer. Máy khác dùng local repo mới vẫn không tìm được nếu không có remote repository. Phần local repo cách ly là **bước chứng minh tối quan trọng**.

## 15. Versioning: release vs SNAPSHOT

### 15.1. Release version 1.0.0

`1.0.0` là bản phát hành cụ thể. Trong production, release artifacts thường được xem là immutable để tránh hai developer có cùng GAV nhưng lấy được hai bytes khác nhau.

Sandbox file:// không có đầy đủ các chức năng của repository manager như ACL, staging, immutable deployment enforcement. Không dùng khả năng overwrite trên filesystem sandbox để biện minh cho việc publish đè release artifact ở production.

### 15.2. Nâng lên 1.0.1

Một thí nghiệm:
1. Đổi library POM version thành `1.0.1`.
2. Giữ API `SafeMath.doubleExact`/`describe` để tương thích, hoặc thêm một method mới.
3. Chạy `verify` rồi deploy lại sandbox.
4. Consumer ban đầu vẫn khai `1.0.0` nên tiếp tục nhận binary cũ.
5. Đổi consumer dependency version sang `1.0.1`, build với local repo riêng.
6. Dùng `dependency:tree` xác nhận Maven thực sự chọn `1.0.1`.

**Bài học:** Có bản mới trong repository **không có nghĩa** Maven tự chọn bản đó khi POM đã pin `1.0.0`. GAV là đầu vào có chủ đích để build reproducible.

### 15.3. SNAPSHOT

Nếu version là `1.0.1-SNAPSHOT`:
- Publish theo snapshot policy, có thể có timestamped artifacts và metadata.
- Consumer repository phải bật `<snapshots><enabled>true</enabled></snapshots>`.
- `mvn -U` có thể buộc check snapshot updates; **không phải cơ chế bắt buộc tải lại mọi release JAR đã cached**.
- Đừng coi SNAPSHOT là immutable release.
- Với repository manager thật, tách release/snapshot repositories và ACL.

### 15.4. Các classifier và attached artifacts

`calc-kit-1.0.0-sources.jar` có classifier `sources`. Maven binary dependency mặc định không cần classifier, nên lấy `calc-kit-1.0.0.jar`. Nếu yêu cầu source files, IDE hoặc Maven Dependency Plugin có thể tải thêm `sources` artifact; nó không tự thay runtime JAR.

Trong thư viện public, Javadoc JAR và chữ ký số có thể là điều kiện bổ sung tùy registry. Không nhầm `SHA-256`, `sources.jar` với GPG signature/provenance.

## 16. CI/CD và quyền publish

### 16.1. PR pipeline chỉ build/test

Pull request từ fork hoặc branch chưa review có thể sửa `pom.xml` và Maven plugin executions, nên `mvn verify` là code execution từ PR. **Không cấp publish secrets cho PR job**.

Một workflow GitHub Actions minh họa, nằm trong repository `calc-kit-library`:

```yaml
name: Verify library PR

on:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
      - run: mvn -B -ntp clean verify
```

Workflow trên **không publish** và không cấu hình registry credentials. Với production, nên pin actions theo reviewed commit SHA, đặt branch protections/required checks, và không cho untrusted PR job chạy trên self-hosted runner có quyền production.

### 16.2. Trusted release pipeline

Khi phát hành:
1. Checkout protected branch/tag đã review.
2. Kiểm POM version/GAV, active profiles và dependency graph.
3. Chạy tests/security checks ở environment phù hợp.
4. Chỉ job publish có credentials ghi đúng registry.
5. Deploy và ghi lại artifact inventory/chữ ký/checksums.
6. Khi upload partial failure, kiểm registry state trước khi retry.
7. Không dùng `-DskipTests` chỉ vì muốn nhanh mà không có equivalent verified test artifact.

Trong thực tế có thể dùng Nexus/Artifactory/GitHub Packages/Maven Central theo các quy trình riêng; không suy rằng `file://` demo chứng minh mọi bước staging, ACL, signing hay trusted publishing đã được cấu hình.

### 16.3. Side effects và partial publication

`deployAtEnd=true` của Deploy Plugin có thể trì hoãn upload trong reactor nhưng **không tạo một transaction atomic**. Nếu một batch có nhiều artifacts và có lỗi giữa các uploads, một số files có thể đã được publish. Vì vậy CI release phải kiểm artifact inventory, repository policy, retry strategy, rollback/promotion và quyền xóa. Sandbox một module không minh họa hết rủi ro multi-module production release.

## 17. Troubleshooting thường gặp

| Hiện tượng | Nguyên nhân có thể | Kiểm và sửa |
| --- | --- | --- |
| `mvn -version` báo JDK 11 | `JAVA_HOME`/Toolchain sai | Dùng Java 17+ theo POM |
| Producer không compile | Sai package/path hoặc Java source | So `SafeMath.java` và class |
| Library Tests run 0 | Surefire/JUnit không phát hiện | Kiểm tên `SafeMathTest`, JUnit engine |
| Không có binary JAR | `package`/plugin/packaging sai | `mvn clean verify`, kiểm target |
| Không có sources JAR | Source Plugin chưa bind | Kiểm `jar-no-fork` trong executions |
| `mvn deploy` thiếu repo | Không có destination | Truyền `-DaltDeploymentRepository=id::url` |
| Alternative repo format error | Dùng `id::layout::url` cũ | Plugin 3.x dùng `id::url` |
| Sandbox folder trống | Deploy thất bại/URI sai | Kiểm file:// path và logs |
| Windows file URI không hoạt động | URL chứa backslash/ổ sai | Dùng `file:///C:/...` đúng ổ |
| Maven báo permission denied | Folder không writable | Kiểm OS file permissions |
| Repo có POM nhưng thiếu JAR | Project artifact không package | Kiểm main `target/*.jar` |
| Consumer báo artifact not found | URL, version, groupId sai | So POM và layout sandbox |
| Consumer vẫn PASS khi URL sai | Artifact đã cached trong local repo | Dùng local consumer repo mới |
| Consumer POM URL unresolved | Không truyền `-Dlab.repo.url` | Thêm CLI property |
| Consumer lỗi JUnit download | Isolated repo lạnh và network/mirror | Kiểm Central/mirror, không dùng `-o` lần đầu |
| Java import SafeMath fail | Dependency GAV sai/chưa resolve | `dependency:tree`, repository URL |
| Java runtime ClassNotFound | `java -cp` thiếu calc-kit binary | Thêm JAR downloaded từ consumer cache |
| `java -jar` báo no main manifest | POM không tạo executable JAR | Dùng `java -cp` như hướng dẫn |
| JAR tồn tại nhưng thiếu class | Artifact sai/đóng gói lỗi | `jar tf` và checksum |
| Source JAR không tải về local | Maven compile không cần sources | IDE/resolve-sources khi muốn |
| Dependency version khác | `dependencyManagement`/GAV mismatch | Xem `dependency:tree` |
| SNAPSHOT không resolve | Repository snapshots policy tắt | Bật đúng snapshot repo |
| Release overwrite bị từ chối | Registry immutable policy | Dùng version mới; không force overwrite |
| HTTP 401/403 khi dùng HTTPS | Credentials/server ID/ACL sai | settings.xml, secret manager |
| HTTP 409 | GAV tồn tại hoặc conflict | Kiểm remote state, tránh retry mù |
| Maven mirror bỏ qua sandbox | settings.xml mirror pattern | Kiểm effective settings/resolver logs |
| Maven offline fail cache mới | Plugins/JUnit chưa có | Tải dependencies qua repo khi có mạng |
| SHA-256 sandbox khác producer | Artifact bytes khác | Kiểm file đúng version/build |
| CI PR có deploy token | Trust boundary sai | Tách PR verify và protected publish |
| Deploy báo success nhưng consumer sai API | Binary khác mong đợi hoặc runtime classpath | JAR listing/tests/dependency tree |
| Consumer chạy đúng chỉ trên máy producer | Depend vào local install | Test bằng fresh isolated local Maven cache |

### 17.1. Runbook khi consumer thất bại

1. Xác nhận producer GAV đúng `dev.example.training.mavenlab:calc-kit:1.0.0`.
2. Xác nhận Maven 3.9.x/JDK17 và producer 4 tests PASS.
3. Xác nhận output `calc-kit-1.0.0.jar` và sources JAR.
4. Xác nhận `mvn clean deploy` đã chạy với **sandbox file URL đúng**.
5. Kiểm file `calc-kit-1.0.0.pom` và main JAR ở repository layout.
6. Đối chiếu `lab.repo.url` được truyền vào consumer.
7. Chạy consumer với local Maven repo **chưa có** artifact GAV.
8. Kiểm Maven Resolver error (missing POM/JAR, mirror, offline, permissions).
9. Chạy `dependency:tree` và `jar tf` từ local consumer cache.
10. Kiểm 3 tests PASS và ứng dụng in đúng `consumer: double(21)=42`.
11. Nếu file khác bytes, so SHA-256 producer, sandbox và consumer.
12. Chỉ khi ba mốc producer/sandbox/consumer đạt mới ghi end-to-end PASS.

**Tránh các cách chữa tạm:** không copy JAR trực tiếp vào `.m2/repository`, không đặt `systemPath` trỏ tới `target` producer, không xóa global Maven cache, không tự cấp production token để vượt lỗi sandbox.

## 18. Checklist nghiệm thu

### Producer và sandbox

- [ ] Source library Java 17 đúng package và API.
- [ ] Producer POM có đúng GAV và version `1.0.0`.
- [ ] Maven Compiler/Surefire/Source/Deploy plugins được pin versions.
- [ ] `mvn clean verify` chạy 4 JUnit tests và PASS.
- [ ] `target/calc-kit-1.0.0.jar` có `SafeMath.class`.
- [ ] `target/calc-kit-1.0.0-sources.jar` có `SafeMath.java`.
- [ ] `mvn clean deploy` chỉ rõ `training-sandbox::file:///...`.
- [ ] Sandbox có JAR, POM, source JAR ở đúng repository path.
- [ ] Không có credentials thật hoặc production distributionManagement trong lab.
- [ ] SHA-256 producer JAR và sandbox JAR khớp.

### Consumer

- [ ] Consumer là Maven project độc lập, không nằm cùng reactor.
- [ ] POM khai dependency GAV đúng, không có `systemPath`.
- [ ] `<repositories>` có `training-sandbox` và property URL.
- [ ] CLI truyền `-Dlab.repo.url` và dùng local cache khác producer.
- [ ] Cache consumer ban đầu chưa chứa `calc-kit:1.0.0`.
- [ ] Consumer resolve JAR/POM từ sandbox, 3 unit tests PASS.
- [ ] `dependency:tree` xác nhận `calc-kit:jar:1.0.0:compile`.
- [ ] `jar tf` trên JAR đã tải cho thấy `SafeMath.class`.
- [ ] `java -cp` dùng **JAR trong local consumer repo**, không dùng producer target.
- [ ] Stdout đúng `consumer: double(21)=42`.
- [ ] Negative test URL sai được phân tích với cache mới/mirror effects.

### Khi áp dụng cho dự án thật

- [ ] Release version là immutable theo repository policy.
- [ ] Có phân quyền đọc/ghi, staging, retention và credential scopes.
- [ ] Credentials lưu trong settings/CI secrets, không ở POM.
- [ ] CI PR chỉ verify, không có publish secret.
- [ ] Protected release mới deploy, tests/quality gates đạt.
- [ ] Source/Javadoc/signing/SBOM/provenance theo yêu cầu registry.
- [ ] Artifact inventory và checksums được kiểm sau publish.
- [ ] Có runbook khi timeout, partial upload hoặc HTTP 409.

## 19. Câu hỏi tự kiểm tra

**1.** Vì sao `mvn install` chưa chứng minh library được publish cho nhóm khác? Vì nó chỉ ghi vào local Maven repository.

**2.** Mục đích `mvn deploy` trong bài? Upload artifacts vào sandbox repository `file://`.

**3.** GAV ở đây là gì? `dev.example.training.mavenlab:calc-kit:1.0.0`.

**4.** Repository path của artifact được suy ra từ gì? groupId path, artifactId, version và artifact filename.

**5.** Vì sao cần POM cùng JAR? POM chứa tọa độ, dependencies/scopes và metadata resolution.

**6.** Vì sao cần source JAR? Để IDE/tooling xem source; nó không phải binary classpath artifact.

**7.** Format `altDeploymentRepository` Deploy Plugin 3.x? `id::url`.

**8.** Consumer dùng `<repositories>` hay `distributionManagement` để tải? `<repositories>` hoặc repository/mirror tương ứng.

**9.** Producer dùng `distributionManagement` để làm gì? Khai đích publish mặc định.

**10.** Vì sao consumer phải dùng local Maven repo riêng? Tránh dùng bản producer đã `install`, chứng minh remote sandbox được dùng.

**11.** Stdout chương trình consumer là gì? `consumer: double(21)=42`.

**12.** Producer chạy bao nhiêu unit tests? **4**.

**13.** Consumer chạy bao nhiêu unit tests? **3**.

**14.** `junit-jupiter` scope test của producer có thành runtime dependency của consumer không? Không.

**15.** Khi đổi producer version thành `1.0.1`, consumer còn `1.0.0` có tự lấy version mới không? Không.

**16.** SNAPSHOT khác release ở điểm gì? Có cơ chế update/metadata riêng, không giả định immutable.

**17.** `mvn -U` có buộc mọi release JAR tải lại không? Không.

**18.** Nếu consumer chỉ dùng source JAR thì compiler có class binary không? Không; cần artifact JAR chính.

**19.** Tại sao `java -jar` của consumer không được bảo đảm? Chưa cấu hình Main-Class và bundling dependencies.

**20.** Hai SHA-256 bằng nhau chứng minh gì? Bytes tương đương, không xác thực publisher.

**21.** Một negative test URL sai nhưng vẫn PASS có thể do gì? Mirror khác hoặc local cache chứa GAV.

**22.** Có nên chạy `-o` trên local repo mới hoàn toàn không? Không nếu JUnit/plugins chưa được cache.

**23.** Publish trực tiếp vào Maven Central khi thực hành có cần thiết không? Không; sandbox file:// đủ để học cơ chế.

**24.** Khi HTTP 409 do release đã tồn tại nên làm gì? Kiểm registry và tăng version nếu cần, không overwrite mù.

**25.** Vì sao producer code dùng Math.multiplyExact? Để overflow có behavior xác định, kiểm API của library từ consumer.

**26.** `dependency:tree` từ consumer giúp làm gì? Xác nhận phiên bản/scope artifact Maven thực dùng.

**27.** Khi không tìm thấy `SafeMath.class` trong JAR từ consumer cache nên xem gì? Artifact GAV, jar listing, publish output.

**28.** Vì sao một workflow PR không nên có token upload? PR có thể thay POM/plugins, tức là có khả năng chạy code chưa tin cậy.

## 20. Kết luận

Bài **Thực hành tổng hợp** này chứng minh đầy đủ chu trình **build thư viện → kiểm thử → đóng gói → xuất bản JAR/POM vào Maven repository → dùng lại từ một Maven project độc lập**. Quan trọng nhất là kiểm bằng **consumer local cache mới**, vì `mvn deploy` có thể làm library xuất hiện trong local repository của producer và che giấu việc sandbox repository chưa thật sự hoạt động.

Khi producer có 4 tests PASS, sandbox chứa binary JAR/POM/sources, consumer dùng đúng GAV và repository URL, 3 consumer tests PASS và chương trình in **`consumer: double(21)=42`**, ta mới có đủ bằng chứng end-to-end. Sau đó có thể chuyển từ sandbox `file://` sang repository manager thực, với source trust, CI release protection, credentials, immutability và artifact provenance theo chính sách.

### Tài liệu chính thức

- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)
- [Apache Maven Deploy Plugin — deploy:deploy, altDeploymentRepository](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html)
- [Apache Maven Deploy Plugin — deploy:deploy-file](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html)
- [Apache Maven — Deployment Transports](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Source Plugin — source:jar-no-fork](https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
