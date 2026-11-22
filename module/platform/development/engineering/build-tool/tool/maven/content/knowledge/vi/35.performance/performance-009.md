# Phân biệt build tăng dần của từng Maven plugin với cache đầu ra

## 1. Vấn đề thực tế: hai lần build nhanh giống nhau nhưng cơ chế khác nhau

Bạn chạy một Maven project:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp verify
~~~

Lần thứ hai có thể nhanh hơn lần đầu. Nhưng **không thể kết luận “Maven đã lấy JAR từ build cache”** chỉ vì thấy dòng `Nothing to compile`, số giây giảm hoặc `target/classes` vẫn tồn tại.

Có ít nhất ba cơ chế độc lập:

1. **Incremental work trong một plugin:** chính plugin quyết định công việc nào đã cập nhật trong workspace hiện tại; ví dụ Maven Compiler Plugin bỏ qua compile khi không thấy nguồn/dependency thay đổi, Maven Resources Plugin tránh ghi lại file output khi content không đổi, Maven JAR Plugin có thể không tạo lại archive nếu không cần.
2. **Reuse artifacts đã được tải:** Maven Resolver lưu **dependencies/plugins** trong local repository `~/.m2/repository`. Nó giúp tránh download, **không đồng nghĩa reuse output của project hiện tại**.
3. **Build-output cache:** một cơ chế cache như **Apache Maven Build Cache Extension** tính khóa từ inputs/model/config, lưu các build outputs và khôi phục kết quả từng module cho lần build có đầu vào tương đương, kể cả khi thư mục `target/` đã bị xóa trong những trường hợp được hỗ trợ.

Đề bài này tập trung phân biệt **(1) khả năng build tăng dần riêng của từng plugin** với **(3) cache đầu ra**, đồng thời nhận diện (2) để tránh đo sai hiệu năng.

**Mục tiêu:** giải thích cơ chế, biết quan sát log, thiết kế kiểm chứng theo từng tình huống thay đổi và xây một thử nghiệm Java 17/JUnit 5 có thể chạy bằng Maven, sau đó chủ động bật cache extension để so sánh. Không hứa mọi plugin luôn incremental và không hứa cache hit trong mọi môi trường.

## 2. Định nghĩa: “incremental” không phải một nút bật chung của Maven core

Một Maven lifecycle thực hiện các goals gắn ở các phases:

~~~text
validate
  -> process-resources  (resources:resources)
  -> compile            (compiler:compile)
  -> process-test-resources
  -> test-compile       (compiler:testCompile)
  -> test               (surefire:test)
  -> package            (jar:jar)
  -> verify
~~~

Trong mô hình thông thường, **Maven core điều phối** các plugin goals. Nó không có một hợp đồng input/output đầy đủ cho mọi goal để tự biết “goal này chắc chắn không cần chạy”. Chính **từng plugin** quyết định có tính toán lại, ghi lại output, bỏ qua hay làm mới tác vụ của mình.

Ví dụ:
- Compiler Plugin có trạng thái incremental riêng và so source/dependency changes.
- Resources Plugin có chiến lược xác định file resource output cần ghi lại.
- JAR Plugin có khả năng bỏ qua tạo archive khi inputs/output có vẻ không đổi.
- Surefire Plugin bình thường vẫn thực thi JUnit tests theo goal nếu được gọi và không skip; một lần compiler no-op **không đồng nghĩa tests không cần chạy**.
- Các plugins tự viết hoặc code generators có thể không hỗ trợ incremental chính xác.

**Quan trọng:** “incremental build” có thể được dùng để nói **giảm công việc trong một plugin**, hoặc **chỉ rebuild modules bị ảnh hưởng**, hoặc **reuse toàn bộ output từ cache**. Khi trao đổi hiệu năng phải nói rõ đang dùng nghĩa nào.

## 3. Bảng so sánh ba cơ chế

| Tiêu chí | Incremental của plugin | Build-output cache | Dependency cache |
| --- | --- | --- | --- |
| Phạm vi | Một plugin goal/lần chạy trong module | Kết quả build theo inputs, thường module-level | Dependencies và build plugins từ repositories |
| Dữ liệu đánh giá | Plugin-specific: timestamp, source/dependency changes, output state… | Key/fingerprint từ POM, sources, dependencies, plugin params và cấu hình nhận biết | GAV, repository resolution, metadata, files tải |
| Output tái sử dụng | `target/classes`, resources, archive đã ở workspace | Artifacts/reports/attached outputs do extension lưu và restore theo policy | JAR/POM của third-party hoặc artifacts đã `install` |
| Sau khi `mvn clean` | Thường mất local `target` output để so | Có thể vẫn **restore** từ cache bên ngoài `target` | Vẫn còn dependencies trong `.m2` |
| Hỗ trợ CI agent mới | Không nếu workspace output không tồn tại | Có thể, nếu có remote/shared cache được cấu hình và trust | Có nếu dependency cache/repository có sẵn |
| Điểm lỗi | Stale output, rebuild chưa đủ hoặc quá nhiều | Cache key thiếu input, restore thiếu output, side effect bị bỏ qua | Artifact cũ/mismatch hoặc resolution sai |
| Quan sát | Plugin log: no sources to compile, content unchanged… | Cache hit/miss/save/restore, buildinfo/cache reports | Maven download/resolver logs |
| Thử nghiệm an toàn | So `verify` liên tiếp không `clean` | Bật/tắt extension và so trên `clean verify` | So máy/repo tải dependency khi warm/cold |
| Khả năng chia sẻ output build | Không trực tiếp | Có, khi remote cache được phê duyệt | Không có ý nghĩa như output cache |

Không xếp tất cả dưới một nhãn “Maven cache”. Một build nhanh nhờ JDK file-system cache, warmed JVM, repository local, plugin no-op hoặc cache-output hit là các hiện tượng khác nhau.

## 4. Compiler Plugin 3.x: cách hiểu incremental chính xác

Trong **Maven Compiler Plugin 3.15.0**, option:

~~~xml
<configuration>
    <useIncrementalCompilation>true</useIncrementalCompilation>
</configuration>
~~~

có **default `true`** cho cấu hình javac thông thường. Tài liệu plugin diễn giải rằng nó kiểm source files được thêm/sửa/xóa và những dependency JAR thay đổi trong lần build; khi phát hiện thay đổi cần compile, **plugin có thể biên dịch lại toàn bộ source files của module**, không chỉ đúng một file.

Điều này khiến hai quan sát đều đúng:

- **Không có thay đổi:** plugin có thể bỏ qua compile; log thường nói không cần compile.
- **Một source thay đổi:** plugin có thể biên dịch lại **tất cả sources của module**, vì cách conservative này tránh bỏ sót class dùng API đã đổi.

“Incremental” ở đây **không phải** một hệ thống fine-grained dependency graph cấp method hay class như nhiều người tưởng.

### 4.1. Tại sao `useIncrementalCompilation=false` dễ gây lỗi?

Tài liệu Compiler Plugin mô tả chế độ `false` (không được khuyến nghị với javac):

~~~xml
<configuration>
    <useIncrementalCompilation>false</useIncrementalCompilation>
</configuration>
~~~

Nó có xu hướng chỉ compile các source mới hơn class tương ứng. Nếu đổi API của class `LibraryA` nhưng không biên dịch lại class `LibraryB` đang gọi API cũ, class `LibraryB.class` có thể mang bytecode cũ và gây lỗi khi chạy.

Ví dụ:

~~~java
// Phiên bản cũ trong LibraryA:
public static int price() {
    return 200;
}

// Sau khi sửa:
public static long price() {
    return 200L;
}
~~~

Nếu class consumer đã biên dịch gọi `int price()` mà không được compile lại, bạn có thể gặp `NoSuchMethodError` khi runtime resolve method signature mới. `javac` và JVM không tự bảo đảm mọi class phụ thuộc đã được biên dịch lại chỉ vì bạn chọn tốc độ.

**Không bật `false` như một mẹo tối ưu mặc định**. Đầu tiên đo ở cấu hình an toàn, giảm module size và cải thiện hot path; chỉ tùy chỉnh incremental mode khi hiểu rõ dependency graph/compiler behavior và có clean-build verification.

### 4.2. Plugin version khác có thuật toán khác

Compiler Plugin **4.x** có parameter `incrementalCompilation` mới với các chế độ như `dependencies`, `sources`, `classes`, `rebuild-on-change`, `rebuild-on-add`, `modules`, `none` và tổ hợp tùy version. Đừng sao chép cú pháp/semantics của **4.x** vào POM đang dùng **3.15.0** rồi khẳng định chúng tương đương.

Trong một dự án thực tế:
1. Pin version Compiler Plugin.
2. Đọc **goal documentation đúng version**.
3. Kiểm trạng thái build theo tình huống thay đổi source/API/dependency.
4. So output với một lần `clean verify` có cache bị tắt.
5. Không đổi chính sách compile chỉ theo benchmark thời gian.

## 5. Maven Resources Plugin: “không copy lại” là một cơ chế khác

Maven Resources Plugin dùng để copy/optionally filter resources trong `src/main/resources` sang `target/classes`.

Với **Maven Resources Plugin 3.5.0**, parameter `changeDetection` có những chiến lược như:

- `content`: chỉ ghi đè output khi nội dung khác; **default** từ plugin 3.4.0.
- `timestamp`: dựa vào thời gian chỉnh sửa so với output.
- `timestamp+content`: kết hợp điều kiện thời gian và nội dung.
- `always`: luôn ghi đè output.
- `never`: không ghi đè target đã tồn tại.

Ví dụ cấu hình explicit:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.5.0</version>
    <configuration>
        <changeDetection>content</changeDetection>
    </configuration>
</plugin>
~~~

`content` không phải **cache build toàn project**. Plugin vẫn có thể được gọi trong phase `process-resources`, vẫn đọc/kiểm nguồn, nhưng tránh ghi đè file target nếu kết quả không đổi.

Nếu resource filtering phụ thuộc vào biến môi trường, external file hoặc profile, cần đảm bảo những inputs ấy được tính trong mọi **build-output cache key**. Chỉ cấu hình Resources Plugin kiểm content output không tự giúp cache extension biết secret/env hay các input ẩn.

### 5.1. Resources không đồng nghĩa compile Java

Nếu chỉ sửa `src/main/resources/status.txt` trong demo, Maven Resources Plugin xử lý resource và application behavior có thể đổi; không vì thế mà Compiler Plugin nhất thiết phải compile lại `.java`. Ngược lại, sửa `.java` có thể yêu cầu compiler chạy nhưng Resources Plugin không cần ghi đè một resource không đổi.

Hai plugin hoạt động ở **các phase khác nhau với quyết định riêng**. Cache toàn module lại có thể coi đổi resource là input miss và chạy lại lifecycle cần thiết.

## 6. Maven JAR Plugin: có thể không tạo lại archive

Maven JAR Plugin `jar:jar` có option:

~~~xml
<configuration>
    <forceCreation>false</forceCreation>
</configuration>
~~~

Ở phiên bản 3.4.2, **default là false**. Plugin kiểm có output JAR và inputs không thay đổi hay không; khi đủ điều kiện, nó có thể **bỏ qua tạo lại JAR**.

Lệnh:

~~~bash
mvn -B -ntp package
~~~

không đảm bảo mỗi lần đều tạo file JAR với timestamp/bytes mới. Nếu các entries giống trước và plugin nhận ra archive còn phù hợp, nó có thể tái sử dụng local file.

### 6.1. Khi nào cần `forceCreation=true`?

Nếu một plugin khác **post-process** JAR tại chỗ (ví dụ một bước nào đó chỉnh sửa/đóng gói lại archive), JAR Plugin có thể hiểu file đã tồn tại và không biết rằng nó từng bị xử lý. Một lần package khác có thể dùng nhầm archive đã post-process.

Khi đó cấu hình explicit:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <forceCreation>true</forceCreation>
    </configuration>
</plugin>
~~~

có thể được sử dụng **sau khi đã xác minh quy trình plugin**. Theo tài liệu JAR Plugin, tùy phiên bản, đây là hướng khắc phục khi downstream plugin post-process JAR. Đổi `forceCreation` làm **đổi hành vi của một plugin**, không xóa hay tắt Apache Maven Build Cache Extension.

Nếu cấu hình `forceCreation=true` không hợp lý, nó có thể làm chậm build bình thường. Không chọn đồng loạt cho mọi project chỉ để “chắc chắn”.

### 6.2. `project.build.outputTimestamp` giải quyết chuyện khác

POM có thể đặt:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Đây là một cơ chế hỗ trợ **reproducible archive timestamps**, không tự bật incremental compile hoặc output cache. Hai JAR có timestamp bên trong giống nhau chưa chắc giống bytes: compiler, dependencies, entry ordering, generated resources và plugin versions cũng ảnh hưởng.

## 7. Surefire Plugin: tests khác compiler và cache

Maven Surefire Plugin chạy unit tests ở phase `test`. Trong một build bình thường **không có build-output cache extension**:

- Nếu Compiler Plugin không cần compile, Surefire vẫn có thể được gọi và **chạy lại tests**.
- Nếu JAR Plugin thấy archive chưa đổi, việc đó không chứng minh tests đã chạy.
- `-DskipTests` hoặc `-Dmaven.test.skip=true` rút ngắn build bằng cách **bỏ kiểm chứng**, không phải incremental optimization hợp lệ cho protected CI gate.
- Một build cache extension có thể **restore kết quả build** cho input key phù hợp thay vì chạy từng goal; khi đó phải phân biệt restored result với test execution mới.

Nếu project có integration tests, security scans, secret scans, integration environments hoặc report side effects, đừng cho phép cache tự bỏ qua kiểm chứng bắt buộc mà chưa thiết kế `executionControl`/always-run rules theo đúng plugin và chính sách.

**Một `BUILD SUCCESS` từ cache hit không đồng nghĩa mọi JUnit test vừa được thực thi trên JVM hiện tại.** Nó có thể là việc tái sử dụng một kết quả kiểm chứng trong ngữ cảnh được cho là tương đương; điều này chỉ có giá trị khi input key và policy bao quát đầy đủ những yếu tố liên quan.

## 8. Maven dependency cache (`~/.m2/repository`) không phải build-output cache

`~/.m2/repository` lưu artifacts đã resolve từ remote repositories và output đã `mvn install`. Nó giúp Maven không phải tải lại JUnit, Maven plugins hoặc third-party libraries ở mỗi invocation.

Nhưng một dependency cache warm không đảm bảo:

~~~text
target/classes/
target/test-classes/
target/my-app-1.0.0.jar
target/surefire-reports/
~~~

sẽ được khôi phục sau `mvn clean`.

Cần phân biệt:

| Câu hỏi | `~/.m2/repository` | Maven Build Cache Extension |
| --- | --- | --- |
| Đã tải `junit-jupiter` chưa? | Có thể có | Không phải mục tiêu chính |
| JAR của chính module đã được build với inputs này chưa? | `mvn install` có thể lưu bản artifact | Có thể lưu cache record/build outputs |
| Biết inputs/POM đổi cần invalidate output không? | Không cung cấp hợp đồng build-output key tổng quát | Cơ chế cốt lõi là input key/fingerprint |
| Khôi phục output sau clean? | Không tự động khôi phục `target` cho lifecycle | Có thể, theo config và artifact output type |
| Chia sẻ giữa CI workers? | Cache filesystem hoặc remote dependency repo | Remote build cache được cấu hình riêng |

Các CI caches như GitHub Actions `cache: maven` của `actions/setup-java` thường nhằm cache Maven dependencies, **không đồng nghĩa đã bật Apache Maven Build Cache Extension**. Nếu CI job vẫn chạy `mvn verify`, plugin goals bình thường vẫn hoạt động theo cơ chế của chúng.

## 9. Build-output cache của Apache Maven: khái niệm và kiến trúc

**Apache Maven Build Cache Extension** là một **Maven extension**, không phải tham số của Compiler Plugin.

Phiên bản **1.3.0** đã được Apache phát hành tháng 8/2026. Theo tài liệu chính thức, extension yêu cầu **Maven 3.9+** (hỗ trợ Maven 4). Nó có thể được khai báo ở `.mvn/extensions.xml`.

Luồng khái niệm:

~~~text
Maven build của module
         |
         v
Xác định inputs:
  source files, POM/effective model,
  dependencies, plugin config và các inputs được khai báo
         |
         v
Tính fingerprint / cache key
         |
         +-- có entry hợp lệ? ---- yes ---> khôi phục outputs
         |                                  (không nhất thiết chạy từng goal)
         |
         +-- no ---> Maven lifecycle + plugins chạy bình thường
                      |
                      v
                 lưu build outputs/metadata
                 theo cấu hình cache
~~~

Theo phần *Concepts* của Apache Maven Build Cache Extension, cache phân tích model/plugins/config và dùng source content fingerprints; khi module key thay đổi, nó **chuyển cho Maven core build bình thường**, không sửa thuật toán incremental nội bộ của mỗi plugin.

**Đây là khác biệt cốt lõi:** cache extension quyết định ở mức **module build state có thể reuse**, còn Compiler/Resources/JAR Plugin quyết định **mình cần làm gì trong một lần execution cụ thể**.

### 9.1. Hit/miss có thể xảy ra sau clean

Nếu output đã được lưu trong extension cache và inputs khớp, chạy `mvn clean verify` lần tiếp theo có thể **restore build outputs** và tránh chạy lại nhiều bước. Trong Maven không bật extension, `clean` xóa `target`, khiến plugin incremental vốn cần output local khó có dữ liệu để bỏ qua công việc.

Bởi vậy, thử “`clean verify` chạy nhanh lần hai” là một phép thử hữu ích **khi biết chắc extension đã được bật** và đã kiểm log restore. Không suy ngược chỉ từ thời gian.

### 9.2. Cache local và remote khác nhau

- **Local build cache:** lưu cache entries bên ngoài workspace output, trong vị trí do extension quản lý.
- **Remote build cache:** chia sẻ cache entries qua storage/endpoint được cấu hình (cần setup riêng).
- **Không mặc định remote:** chỉ thêm `.mvn/extensions.xml` không tự làm các CI agents khác chia sẻ cache với nhau.

Tính chính xác của remote cache phụ thuộc input key, provenance/ACL, network, artifact validity và version compatibility. Cache nội bộ không đồng nghĩa một nơi công khai để bất kỳ PR nào cũng có quyền write.

## 10. Lab Java 17/JUnit 5: project tối giản nhưng có đủ ba plugin behaviors

Ta tạo project Java 17 có hai classes production, một resource và bốn unit tests. Nó phù hợp để thử:

- Compile `.java` qua Compiler Plugin.
- Copy resource qua Resources Plugin.
- Test qua Surefire.
- Package qua JAR Plugin.
- Tùy chọn cache toàn module qua Maven Build Cache Extension.

**Lab có hai chế độ:** không có extension (baseline) và có extension (cache experiment). Không bật đồng thời nhiều cơ chế khác nhau trong lần đo mà không ghi nhận trạng thái.

### 10.1. Cấu trúc project

~~~text
maven-incremental-vs-cache/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/build/
│   │   │   ├── BuildMessage.java
│   │   │   └── App.java
│   │   └── resources/
│   │       └── status.txt
│   └── test/
│       └── java/com/example/build/
│           └── AppTest.java
└── .mvn/                (chỉ tạo ở phần thử cache)
    └── extensions.xml   (chỉ tạo ở phần thử cache)
~~~

Trong phần baseline, **đừng tạo `.mvn/extensions.xml`**. File này chỉ được thêm ở bước 13.

### 10.2. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>maven-incremental-vs-cache</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

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
                <version>3.15.0</version>
                <configuration>
                    <useIncrementalCompilation>true</useIncrementalCompilation>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <changeDetection>content</changeDetection>
                </configuration>
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
                <configuration>
                    <forceCreation>false</forceCreation>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các option `useIncrementalCompilation=true`, `changeDetection=content`, `forceCreation=false` làm hành vi default của **các plugin đã pin** trở nên rõ ràng cho người học; **chúng không tạo build cache**. Cần chú ý semantics đúng versions đang sử dụng.

POM cũng không chứa `systemPath`, custom code generators hay settings từ môi trường ngoài, giúp thí nghiệm tách các nguyên nhân hiệu năng.

### 10.3. `BuildMessage.java`

Tạo `src/main/java/com/example/build/BuildMessage.java`:

~~~java
package com.example.build;

import java.util.Locale;

public final class BuildMessage {

    private BuildMessage() {
    }

    public static String compose(String raw, int first, int second) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }

        String name = raw.strip().toUpperCase(Locale.ROOT);
        return name + "=" + (first + second);
    }
}
~~~

Class Java17-compatible và không dùng bên ngoài JDK.

### 10.4. `App.java`

Tạo `src/main/java/com/example/build/App.java`:

~~~java
package com.example.build;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class App {

    private App() {
    }

    public static String status() {
        try (InputStream in =
                     App.class.getResourceAsStream("/status.txt")) {

            if (in == null) {
                throw new IllegalStateException(
                        "status.txt missing");
            }

            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public static String render() {
        return BuildMessage.compose(" maven ", 20, 22)
                + " | " + status();
    }

    public static void main(String[] args) {
        System.out.println(render());
    }
}
~~~

`App.status()` đọc resource từ runtime classpath. Nếu Resources Plugin chưa copy `status.txt` vào `target/classes`, ứng dụng báo rõ `status.txt missing` thay vì âm thầm in output sai.

### 10.5. `status.txt`

Tạo `src/main/resources/status.txt` đúng một dòng:

~~~text
resource-ok
~~~

File có hoặc không có newline cuối đều cho cùng giá trị do `strip()`. Để so file content/cache inputs, đừng tự động chèn timestamp, username hoặc biến môi trường không kiểm soát vào resource.

### 10.6. `AppTest.java`

Tạo `src/test/java/com/example/build/AppTest.java`:

~~~java
package com.example.build;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AppTest {

    @Test
    void composesNormalizedMessage() {
        assertEquals("MAVEN=42",
                BuildMessage.compose(" maven ", 20, 22));
    }

    @Test
    void rejectsMissingName() {
        assertThrows(IllegalArgumentException.class,
                () -> BuildMessage.compose("  ", 20, 22));
    }

    @Test
    void includesResource() {
        assertEquals("resource-ok", App.status());
    }

    @Test
    void rendersExpectedOutput() {
        assertEquals("MAVEN=42 | resource-ok",
                App.render());
    }
}
~~~

Có **bốn JUnit 5 test methods**, đủ kiểm logic, nhánh invalid input, resource copy và output kết hợp. Khi sửa resource trong một thí nghiệm, phải cập nhật assertions thích hợp hoặc chủ động mong đợi test fail; không được coi test fail là “cache bị hỏng” nếu expected value không còn đúng.

### 10.7. Build và stdout thực tế

Cần Maven 3.9+, JDK 17+ và repository resolve được plugins/JUnit. Trong thư mục chứa `pom.xml`:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
java -cp target/classes com.example.build.App
~~~

**Stdout chính xác từ chương trình Java**:

~~~text
MAVEN=42 | resource-ok
~~~

Surefire chạy **4 tests** khi build thường thành công. `target/maven-incremental-vs-cache-1.0.0.jar` được tạo; đây là JAR thường, **không có `Main-Class`** manifest được cấu hình để chạy bằng `java -jar`. Dùng `java -cp` như trên.

Các output điển hình:

~~~text
target/classes/com/example/build/App.class
target/classes/com/example/build/BuildMessage.class
target/classes/status.txt
target/test-classes/com/example/build/AppTest.class
target/surefire-reports/TEST-com.example.build.AppTest.xml
target/maven-incremental-vs-cache-1.0.0.jar
~~~

Thực tế mỗi plugin/JDK có thể tạo thêm metadata files; đừng coi danh sách này là toàn bộ nội dung `target/`.

## 11. Thí nghiệm A: build tăng dần khi chưa bật cache extension

**Điều kiện:** chưa tồn tại `.mvn/extensions.xml` trong project và không có extension tương đương được tự động bật từ môi trường.

Lần đầu:

~~~bash
mvn -B -ntp clean verify
~~~

Kỳ vọng: Compiler Plugin compile sources; Resources Plugin copy `status.txt`; Surefire chạy 4 tests; JAR Plugin tạo artifact.

Lần thứ hai **không clean**, không sửa gì:

~~~bash
mvn -B -ntp verify
~~~

Quan sát các plugin logs:
- Compiler Plugin thường báo không có gì để compile nếu trạng thái output/source ổn.
- Resources Plugin có thể kiểm content mà không cần ghi đè resource file.
- Surefire vẫn có thể chạy lại 4 JUnit tests.
- JAR Plugin có thể bỏ qua repackaging nếu output/input không thay đổi.
- Không có log “cache hit restored by Maven Build Cache Extension”, vì extension chưa bật.

**Kết luận đúng:** các goals vẫn được điều phối nhưng một số plugin giảm công việc. **Kết luận sai:** toàn bộ build đã được khôi phục từ cache đầu ra.

### 11.1. Đo source compile công bằng

Mỗi run nên ghi lại:
- POM/plugin versions.
- Maven/JDK version và OS.
- Lệnh có `clean` hay không.
- Thay đổi source/resource/test nào xảy ra.
- Số tests chạy/fail/skip.
- Log thật của Compiler/Resources/JAR/Surefire.
- Tổng duration và compile/test/package durations khi có profiler.

Không so thời gian `mvn clean verify` lần đầu (download nhiều dependencies) với `mvn verify` lần hai (repo đã warm) rồi kết luận incremental mang lại 90% speedup. Đầu vào benchmark đã khác quá nhiều.

## 12. Thí nghiệm B: thay đổi từng loại input và quan sát plugin

| Thao tác | Compiler Plugin | Resources Plugin | Surefire | JAR Plugin |
| --- | --- | --- | --- | --- |
| Không sửa gì, `verify` | Có thể no-op | Có thể không ghi đè | Bình thường chạy tests | Có thể skip archive |
| Sửa comment trong `BuildMessage.java` | Nhận source changed, có thể compile lại toàn module | Resource content không đổi | Chạy tests | Có thể phải xét lại archive |
| Sửa `status.txt` | Java source không đổi nên có thể no-op | Copy content mới | Tests phụ thuộc resource có thể fail | Cần đóng gói resource mới |
| Sửa `AppTest.java` | Production sources không đổi | Resource không đổi | Test compile lại rồi chạy tests | Production JAR có thể không đổi |
| Đổi dependency trong POM | Dependency classpath thay đổi có thể trigger compile | Chưa chắc resource đổi | Có thể cần rerun | Xét lại packaged outputs |
| Xóa source file | Incremental state có thể yêu cầu rebuild | Không liên quan trực tiếp | Tests có thể fail | Dùng `clean` để loại stale class chắc chắn |
| Đổi compiler/plugin configuration | Cần đánh giá compile options | Tùy settings | Tùy test runner | Tùy JAR inputs |
| Đổi JDK/toolchain | Cần kiểm bytecode/compiler state | Có thể không đổi | Test JVM có thể khác | Packaging details có thể khác |

**Không khẳng định bảng là log cố định trên mọi môi trường.** Nó dự báo trách nhiệm/điểm cần quan sát; implementation, plugin version và source timestamps ảnh hưởng outcome.

### 12.1. Kịch bản: sửa comment không đổi hành vi

Chỉ thêm comment trong `BuildMessage.java`:

~~~java
// Keep the public API stable across the experiment.
~~~

Đây là **mảnh code**, đặt ở vị trí hợp lệ trong class/source, không phải file độc lập. Khi thêm comment, source file timestamp/content đổi; Compiler Plugin `useIncrementalCompilation=true` có thể quyết định compile lại module, dù Java bytecode behavior của chương trình không thay.

Sau đó chạy:

~~~bash
mvn -B -ntp verify
java -cp target/classes com.example.build.App
~~~

Stdout vẫn:

~~~text
MAVEN=42 | resource-ok
~~~

Một rebuild do source thay đổi không phải dấu hiệu cache không hoạt động; bạn đang ở chế độ chưa bật extension trong thí nghiệm A/B.

### 12.2. Kịch bản: resource thay đổi nhưng code không đổi

Đổi `src/main/resources/status.txt` từ `resource-ok` thành:

~~~text
resource-updated
~~~

Nếu giữ các test cũ, `includesResource()` và `rendersExpectedOutput()` **phải fail** vì expected values cũ. Để kiểm lại một thay đổi hợp lệ, sửa tests mong đợi tương ứng:

~~~java
assertEquals("resource-updated", App.status());

assertEquals("MAVEN=42 | resource-updated",
        App.render());
~~~

Hai dòng trên là **fragment cần thay trong hai test methods hiện có**, không tạo một file mới. Khi `verify` pass sau thay đổi, stdout của `App` là:

~~~text
MAVEN=42 | resource-updated
~~~

**Đừng tự xóa assertions để build xanh**. Thí nghiệm chủ đích chứng minh Resources Plugin đưa content mới vào `target/classes` và archive, cùng test suites phát hiện việc thay resource.

Trước khi qua bài cache extension, hoàn nguyên source/resource/tests về **baseline** ở mục 10 để có input key ổn định.

## 13. Thí nghiệm C: bật Maven Build Cache Extension 1.3.0

Phần này là **một cấu hình bổ sung**, không có trong `pom.xml` của baseline.

Tạo `.mvn/extensions.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<extensions>
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
~~~

Maven 3.9+ tải/khởi động extension ở đầu invocation. Việc khai báo `.mvn/extensions.xml` là **Maven core extension mechanism**, không phải `<plugin>` trong `<build><plugins>`.

**Không tự thêm extension này vào project production chỉ vì có vẻ nhanh**. Cần test chính xác build inputs/outputs/side effects và có rollback switch.

### 13.1. Chạy lần đầu để tạo cache entry

Tại project demo baseline đã hoàn nguyên:

~~~bash
mvn -B -ntp clean verify
~~~

Xem log liên quan `maven-build-cache-extension`, cache key, cache lookup, build execution và save/store. Lần đầu thường là miss (nếu chưa có entry tương ứng), Maven chạy các plugin bình thường rồi cache có thể lưu output metadata.

**Không suy rằng luôn miss**: một cache local/remote đã có entry hợp lệ từ thử nghiệm trước có thể làm invocation đầu tiên sau khi bật extension đã hit.

### 13.2. Chạy lại cùng inputs

~~~bash
mvn -B -ntp clean verify
~~~

Trong môi trường đủ điều kiện, extension có thể nhận input key giống nhau và **restore results** từ entry đã lưu. Đó là **cache hit theo module**; các goals có thể được skip/không chạy thực sự tùy policy, thay vì từng plugin tự xác định timestamp như baseline.

Quan sát:
- Log cache hit, lookup result, restored artifact và build metadata.
- POM/dependency/source fingerprints trong build metadata.
- JAR và compiled output có sẵn sau invocation theo cấu hình.
- App run + tests/provenance được kiểm trong một clean/no-cache validation riêng.
- Nếu `target/classes` không được restore trong config, đừng kỳ vọng `java -cp target/classes` luôn chạy sau cache hit; artifact JAR có thể được phục hồi còn directory classes không.

**Điểm quan trọng:** tài liệu extension ghi rõ **khôi phục state là một phần (partial restoration)**. Để cần dùng `target/classes` cho IDE/tool khác, phải xem outputs/cache config cụ thể. Không đánh đồng “đã restore JAR” với “mọi tệp trung gian dưới target/ được khôi phục”.

### 13.3. Tắt cache mà không xóa cấu hình

Dùng:

~~~bash
mvn -B -ntp -Dmaven.build.cache.enabled=false clean verify
~~~

Option trên **tắt Maven Build Cache Extension** cho invocation (khi extension đã load). Nó **không tắt** `useIncrementalCompilation` của Compiler Plugin, không xóa Maven dependency cache và không vô hiệu Surefire tests.

Đây là baseline quan trọng khi cần phân biệt “plugin incremental” với “extension output reuse”.

### 13.4. `skipCache` khác `skipSave`

Extension có các property:

~~~bash
mvn -B -ntp -Dmaven.build.cache.skipCache=true clean verify
~~~

Dùng để **bỏ qua đọc cache entries** nhưng không nhất thiết cấm ghi kết quả sau build.

~~~bash
mvn -B -ntp -Dmaven.build.cache.skipSave=true clean verify
~~~

Dùng để **không ghi cache result mới**, nhưng vẫn có thể đọc một entry hợp lệ.

`enabled=false` là tắt cache mechanism; `skipCache=true` là không lấy kết quả đã lưu; `skipSave=true` là không lưu kết quả. Ba cờ này **không đồng nghĩa nhau**.

Cẩn trọng: Không dùng cache properties như cách bỏ qua test failures. Khi buộc chạy tests trên JDK khác, cần disable cache read hoặc bảo đảm cache key có JDK/toolchain/environment cần thiết và verify test execution theo CI policy.

## 14. `maven.build.cache.cacheCompile` không phải Compiler Plugin incremental

Maven Build Cache Extension 1.3.0 còn có:

~~~bash
mvn -B -ntp -Dmaven.build.cache.cacheCompile=false compile
~~~

Theo tài liệu extension, `cacheCompile` default **true**: nó có thể lưu/restore output cho compile-only builds (`compile`, `test-compile`) ngoài package/later phases. Khi đặt `cacheCompile=false`, giới hạn caching sang các builds đạt package phase trở đi.

**Đây là extension caching phase policy**, không phải:

~~~xml
<useIncrementalCompilation>false</useIncrementalCompilation>
~~~

của Maven Compiler Plugin.

| Cấu hình | Công cụ sở hữu | Tác động |
| --- | --- | --- |
| `maven.compiler.useIncrementalCompilation` | Compiler Plugin 3.x | Quyết định recompilation khi goal được thực thi |
| `maven.build.cache.cacheCompile` | Build Cache Extension | Cho phép lưu/cache hits với compile-only builds |
| `maven.build.cache.enabled` | Build Cache Extension | Bật/tắt cache extension |
| `maven.build.cache.skipCache` | Build Cache Extension | Chặn đọc cache trên invocation |
| `maven.build.cache.skipSave` | Build Cache Extension | Chặn lưu cache trên invocation |
| `maven.jar.forceCreation` | JAR Plugin | Có tạo lại archive khi input/output dường như không đổi |
| `changeDetection` | Resources Plugin | Cách xác định khi nào ghi đè output resource |

Dù tên các property đều có chữ “cache”, “incremental”, “skip”, ý nghĩa rất khác nhau. Đọc đúng plugin documentation trước khi thay.

## 15. Cache key: tại sao phải bao quát tất cả đầu vào ảnh hưởng output?

Một build output đúng về mặt cache cần **hàm của những inputs được ghi nhận**. Ví dụ:

~~~text
BuildResult = f(
  source code,
  resources,
  POM + effective profiles,
  dependencies + plugin versions,
  annotation processors,
  compiler options,
  JDK/toolchain characteristics,
  generated-source inputs,
  relevant environment/configuration,
  ...
)
~~~

Nếu cache key bỏ sót một input thực sự làm output thay đổi, nó có thể hit **sai**, trả artifact cũ và khiến CI xanh giả.

Ví dụ:
- Code generator đọc một file `schema.yaml` ngoài source tree được extension theo dõi.
- Resource filtering đọc `API_BASE_URL` từ environment nhưng key không ghi giá trị/biến phù hợp.
- Plugin đọc một config dưới `../shared/` không được khai báo làm input.
- Build script gọi Git metadata/timestamp ngoài tập inputs.
- JDK17 và JDK21 dùng compiler/tooling có behavior khác nhưng cache key không phân biệt theo policy.
- Code generation phụ thuộc network hoặc service không deterministic.
- Profiles active trong CI khác local dù POM source không đổi.

Tài liệu extension khuyến nghị rà soát **source selectors, plugin parameters, generated files, project model và exclusions**, sau đó validate build output. Không nên bật cache remote cho cả tổ chức mà chưa kiểm hit/miss correctness bằng thay đổi có kiểm soát.

### 15.1. Nguồn dữ liệu bí mật không nên nằm trong output cache

Nếu một plugin resource filter vô tình ghi token vào generated configuration/JAR, việc cache đầu ra có thể **kéo dài và phân phối sự lộ secret**. Build cache có thể là nơi lưu artifact sao chép được; không được đưa:
- private signing keys,
- deploy tokens,
- environment dumps,
- secrets từ `settings.xml`,
- credentials được nhúng vào generated resources.

Tách signing/deploy side-effect khỏi cacheable pure build hoặc cấu hình execution controls và protected CI jobs phù hợp. Không chia sẻ remote build cache write permissions với untrusted PR jobs nếu cache đó được dùng trong protected release builds.

## 16. Các đầu ra được cache và được restore không mặc định là “mọi thứ trong target”

Maven Build Cache Extension có cơ chế **standard build artifacts**, attached outputs và các danh mục output cấu hình.

Ví dụ các dữ liệu cần cân nhắc:
- Project JAR/WAR.
- Generated sources.
- Compiled classes/test-classes.
- Code-generated descriptors.
- Reports và intermediate files.
- Metadata giúp Maven hiểu build state.

Extension 1.3.0 có `attachedOutputs` để thêm output directories cần cache, và property `restoreOnDiskArtifacts` điều khiển khôi phục artifacts vào `target`. **Không có bảo đảm mọi file phát sinh từ mọi plugin sẽ được lưu và phục hồi**.

Một project IDE dùng Maven `target/classes` làm classpath trực tiếp có thể gặp hạn chế: tài liệu extension khuyến nghị IDE tránh phụ thuộc output folders được Maven build cache restore không đầy đủ, hoặc cấu hình cần thiết theo mô hình IDE.

### 16.1. Thêm output directories: chỉ khi đã hiểu dữ liệu

Một mảnh `maven-build-cache-config.xml` có thể có dạng:

~~~xml
<configuration>
    <attachedOutputs>
        <dirNames>
            <dirName>classes</dirName>
            <dirName>test-classes</dirName>
        </dirNames>
    </attachedOutputs>
</configuration>
~~~

Đây là **fragment nằm trong `<cache>` configuration**, không phải file XML hoàn chỉnh có thể copy và chạy độc lập. Tài liệu extension dùng `attachedOutputs` để chỉ rõ output dirs cần restore trong những tình huống như forked lifecycle.

Nếu output directory chứa file nhạy cảm hoặc non-deterministic data, phải kiểm định trước khi cache. Không thêm `target/` nguyên cây tùy tiện, vì có thể thu cả secrets, logs, incomplete intermediates và state không phù hợp để chia sẻ.

## 17. Single-goal và forked lifecycle: không giả định mọi command được cache

Theo tài liệu extension 1.3.0:

- Các goals được invoke trực tiếp và có **default lifecycle phase thực** ở sau clean, như `mvn compiler:compile`, có thể được cache tương đương phase phù hợp.
- Goals không có default lifecycle phase, ví dụ `exec:java` hoặc `jetty:run`, có thể **không được cache như một normal build**.
- Mixed invocations như `mvn package dependency:tree` thường được để chạy thông thường theo policy.
- Forked lifecycle khi một goal cần compile trước có thể restore phần prerequisite lifecycle trong những builder modes hỗ trợ.

Vì vậy benchmark:

~~~bash
mvn compiler:compile
mvn exec:java
mvn package dependency:tree
~~~

không nhất thiết có cùng semantics cache hit/miss. Muốn so sánh khách quan, giữ **cùng Maven command**, phase và config khi bật/tắt extension.

Không lấy một số đo từ `mvn compiler:compile` rồi khẳng định đó là tốc độ của `mvn clean verify` với full tests và package.

## 18. CI: cache build output và cache Maven dependencies là hai bước cấu hình riêng

Một CI workflow có thể thực hiện:

~~~text
Checkout source
    |
    v
Setup JDK17 / Maven 3.9+
    |
    +-- dependency cache warm (~/.m2/repository)
    |
    v
mvn -B -ntp clean verify
    |
    +-- per-plugin incremental behavior
    |
    +-- optional Maven Build Cache Extension:
          input-key calculation -> local/remote hit/restore
    |
    v
Collect JUnit reports and artifact metadata
~~~

Nếu **không có** `.mvn/extensions.xml` hay cách bật extension tương đương, cache Maven dependencies trong CI **không tạo ra build output cache**.

Nếu chỉ có local extension cache trên **ephemeral CI runner**, mỗi job có thể không giữ cache cho lần chạy sau; muốn chia sẻ cần triển khai remote cache/storage có auth và cache policy.

### 18.1. Các dạng cache dễ nhầm

| Cơ chế | Ví dụ | Đối tượng |
| --- | --- | --- |
| CI dependency cache | `actions/setup-java` `cache: maven` | Maven local repository dependencies |
| CI filesystem cache `target/` | Manual archive/restore target dirs | Không an toàn mặc định; phải kiểm build state |
| Maven Build Cache Extension | `.mvn/extensions.xml` 1.3.0 | Input-keyed build outputs |
| Compiler Plugin incremental | `useIncrementalCompilation=true` | Compile work với local state |
| IDE native compilation cache | IntelliJ/Eclipse incremental builder | IDE output/cache, không mặc định Maven lifecycle |
| Docker layer cache | Dockerfile `RUN mvn ...` | Image layers theo Docker build inputs |
| Remote binary repository | Maven Central/Nexus/Artifactory | Artifact distribution/dependency resolution |

Không xem “cache hit của GitHub Actions” là bằng chứng một `mvn verify` đã được short-circuit bởi Maven Build Cache Extension. GitHub Actions có thể chỉ restore dependencies; các plugins vẫn chạy.

## 19. Multi-module: cache và Reactor cho hai loại tối ưu khác nhau

Giả sử Reactor:

~~~text
root/pom.xml
├── api/
├── core/
├── service/
├── web/
└── integration-tests/
~~~

Dùng Maven Reactor selection:

~~~bash
mvn -B -ntp -pl :service -am verify
~~~

- `-pl :service`: chọn module `service`.
- `-am`: **also make** những modules trong Reactor mà `service` phụ thuộc.
- Goal `verify`: chạy lifecycle cho project set đã chọn.

Điều này **giảm phạm vi modules cần build**, không tự phát sinh output cache.

Maven Build Cache Extension có thể dùng input fingerprints để reuse kết quả của những modules **không thay đổi** khi toàn Reactor được build. Nhưng correctness cần biết:
- Module dependency graph.
- Parent/BOM/plugin management.
- Profiles tạo module set khác nhau.
- Resource/codegen inputs ngoài module.
- Plugin side effects.
- Trường hợp downstream module không cần rebuild dù upstream internals thay đổi.

**Một source file thay đổi ở `core` có thể ảnh hưởng `service` và `web`**, nhưng không nhất thiết ảnh hưởng `api`; cache extension phải tính dependency inputs/keys đúng. Từng Compiler Plugin vẫn quyết định recompilation khi goal được execute.

### 19.1. `-T` không phải incremental

~~~bash
mvn -T 1C -B -ntp verify
~~~

`-T 1C` thử parallel Reactor builds theo số core (tùy cách Maven hiểu) để tận dụng concurrency. Nó **không chứng minh** một goal/module bị bỏ qua hay cache hit. Chỉ dùng parallel build nếu plugins thread-safe và test/integration environments đủ isolation.

Không gộp cải thiện do `-T` với lợi ích do compiler incremental hoặc output cache trong một bảng benchmark không tách biến.

## 20. Một thiết kế benchmark công bằng

Khi kiểm hiệu năng, định nghĩa các kịch bản:

| Case | Extension | Command | Workspace | Mục tiêu |
| --- | --- | --- | --- | --- |
| A1 | Tắt | `clean verify` | Clean | Baseline đầy đủ |
| A2 | Tắt | `verify` | Warm target | Per-plugin incremental/no-op |
| B1 | Tắt | `verify` sau edit source | Warm target | Compiler detects changes |
| B2 | Tắt | `verify` sau edit resource | Warm target | Resources + tests/package |
| C1 | Bật | `clean verify` | Cache chưa được lưu | Populate cache |
| C2 | Bật | `clean verify` cùng inputs | Cache đã có | Kiểm restore/hit |
| C3 | Bật, `skipCache` | `clean verify` | Cache read bypass | So kết quả rebuild |
| C4 | Bật, `skipSave` | `clean verify` | Read tùy entry | Phân biệt cache write |
| D1 | Bật | `clean verify` sau đổi input | Cache có entry cũ | Phải miss/invalidate khi cần |
| E1 | Tắt | `clean verify` sau đổi input | Clean | Golden correctness comparison |

Để so sánh công bằng:
1. Dùng cùng JDK vendor/patch, Maven/plugin versions.
2. Cố định source revision và dependency resolution.
3. Không chạy build khác song song khi benchmark.
4. Warm dependency cache trước, đo riêng download time.
5. Chạy mỗi case nhiều lần, lấy median/thời gian phân bố thay vì một con số.
6. Lưu compiler/JAR/Resources/Cache Extension logs.
7. Kiểm JUnit tests/exceptions, không chỉ exit code.
8. So artifact checksum/behavior khi ý nghĩa và reproducibility config cho phép.
9. Không đổi output timestamp, profile, JDK hay env mà không ghi log.
10. Phân biệt cache local và remote latency.

Thời gian build phụ thuộc CPU, disk, OS, JVM warmup, network, antivirus và test workloads. **Không tự đưa con số “nhanh hơn 10 lần”** nếu chưa đo trên project/CI cụ thể.

### 20.1. Cách đo thời gian đơn giản

POSIX shell:

~~~bash
time mvn -B -ntp clean verify
~~~

PowerShell:

~~~powershell
Measure-Command { mvn -B -ntp clean verify }
~~~

`Measure-Command` trả duration, nhưng trong PowerShell bạn vẫn cần kiểm exit code Maven trong cùng workflow để không ghi nhận một build fail như benchmark thành công. Benchmark production nên thu logs, timestamps và JUnit reports per run.

## 21. Nhận diện cache hit/miss thật bằng logs và metadata

Các dấu hiệu nên kiểm theo thứ tự:

1. `.mvn/extensions.xml` có phiên bản cache extension được cấu hình.
2. Maven log có dấu vết extension initialized/đọc cache config.
3. Build có cache key cho module và trạng thái lookup.
4. Entry phù hợp được restore hay Maven core thực thi goals.
5. Module nào hit/miss và vì sao.
6. Có save cache entry khi miss thành công không.
7. Artifacts/classes/reports cần thiết có được khôi phục không.
8. Outputs có khớp với một clean no-cache build không.
9. JUnit test evidence có hợp lệ theo policy không.
10. Cache có sử dụng remote storage hoặc chỉ local.

Tài liệu extension cho biết có thể xem `buildinfo.xml` trong cache repo (thường là thư mục `build-cache` bên cạnh local `repository`), cũng như `cache-report.xml` và `diff-*.xml` cho chẩn đoán.

Nếu **không có cache-related logs**, đừng ghi “cache hit”. Có thể extension chưa load, không tìm thấy entry, config không hiệu lực hoặc command không thuộc diện được cache.

Nếu Compiler Plugin nói “Nothing to compile” nhưng không có extension, đó là **plugin no-op** chứ không phải “cached build”.

## 22. Cache invalidation: những thay đổi phải được kiểm chứng

Hãy thử một cách có kiểm soát:

- Đổi source Java và giữ tests đúng.
- Đổi resource content.
- Đổi JUnit test source.
- Đổi dependency version trong POM.
- Đổi compiler options/`maven.compiler.release`.
- Đổi active profile.
- Đổi input file cho annotation processor/code generator.
- Đổi file config ngoài module (nếu codegen dùng).
- Đổi Java toolchain/JDK (nếu có ảnh hưởng output hoặc runtime tests).
- Đổi environment variable mà build output thực sự phụ thuộc vào.

Trong từng case:
1. Kỳ vọng **cache miss** hoặc recomputation nếu changed input ảnh hưởng output.
2. Chạy cache-enabled build.
3. Chạy clean no-cache build để lấy reference.
4. Kiểm artifact content/behavior và test output.
5. Nếu hit sai, bổ sung input selection/plugin parameter reconciliation hoặc disable cache cho module/plugin cho đến khi sửa.
6. Không “sửa” bằng cách hardcode một cache key luôn đổi trên mọi build; làm vậy chỉ phá hit rate và che vấn đề modeling.

Cache có giá trị khi **hit đúng**, không phải khi hit nhiều bằng mọi giá.

## 23. Những plugin có side effects không nên được bỏ qua máy móc

Một số goals có **hành động ngoài build output thuần**:

- `maven-deploy-plugin`: gửi artifact ra remote repository.
- `maven-install-plugin:install`: đặt artifacts vào local Maven repository.
- Signing/credential/attestation goals.
- Database schema migrations.
- Notification/report publishing.
- Contract tests phụ thuộc external server state.
- Compliance scans cần chính sách “run per commit/day”.
- Code-generation goals ghi file ra đường dẫn ngoài `target/`.

Nếu build cache bypass một goal có side effect mà policy yêu cầu chạy mỗi lần, có thể xuất hiện build xanh nhưng release chưa được publish, local repo chưa có artifact hoặc security checks không được cập nhật.

Maven Build Cache Extension hỗ trợ **execution-control rules/always-run plugin lists** (chẳng hạn `maven.build.cache.alwaysRunPlugins`) và các cấu hình output restore. Sử dụng những cơ chế này dựa trên plugin/version và đánh giá an toàn, không tự giả định `deploy` sẽ luôn được chạy sau một cache hit.

**Nguyên tắc release:** tách verification cacheable khỏi bước signing/publishing cần quyền và side effects, hoặc cấu hình always-run rõ ràng cho goal bắt buộc. Dù chọn cách nào cũng kiểm end-to-end trong staging trước khi dùng production cache.

## 24. CI reproducibility: cùng input phải cho output tương đương

Build cache dùng input fingerprints. Nhưng nếu một build không deterministic:
- Archive timestamps thay đổi.
- Generated sources chứa current time.
- Compiler flags/JDK khác.
- Resource file đọc machine-specific path.
- Test phụ thuộc timezone/locale.
- Dependency snapshot thay đổi qua remote.
- Test chạy vào external database có state thay đổi.

thì việc restore output cũ có thể không phản ánh hiện trạng.

Một pipeline đáng tin cần:
- Pin JDK/Maven/plugin versions.
- Tránh dynamic dependency versions, quản lý SNAPSHOT update policy.
- Dùng `project.build.outputTimestamp` khi cần reproducible JAR.
- Không đọc environment ẩn khi tạo outputs trừ khi được modeled.
- Phân biệt test side effects và pure build results.
- Quản lý secrets và cache artifact access.
- Có clean no-cache verification lane đủ thường xuyên.
- Quản lý cache schema/version khi toolchain thay đổi.
- Có quy trình invalidate/quarantine cache entries khi phát hiện lỗi.

Reproducibility là điều kiện làm **cache sharing đáng tin hơn**, không phải việc tự động xuất hiện chỉ vì dùng extension.

## 25. Cache remote trong CI: quyền và tính toàn vẹn

Khi share remote cache qua HTTP/storage:
1. Dùng endpoint và TLS được phê duyệt.
2. Tách read/write credentials; không cho untrusted PRs poison trusted release cache.
3. Ràng buộc cache namespace theo project/branch/trust level khi cần.
4. Bảo vệ metadata và artifacts chống sửa trái phép.
5. Không chứa secrets trong outputs hoặc logs được cache.
6. Không dùng cache hit từ untrusted source làm thay thế protected signing/security checks.
7. Kiểm compatibility của cache giữa JDK/vendor/OS/config.
8. Có retention và size quotas.
9. Theo dõi hit rate, miss reason, network overhead.
10. Có khả năng tắt cache lập tức khi incident.

**Remote cache không phải Maven artifact release repository.** Cache phục vụ tăng tốc build có thể thay đổi/evict, còn hosted release repository cần GAV/version/immutability/ACL/audit riêng. Không dùng raw cache directory làm nơi phân phối library cho consumers.

## 26. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Compiler in `Nothing to compile` là cache hit” | Đó thường là Compiler Plugin tự bỏ qua compile vì local state đã cập nhật |
| “`-DskipTests` là incremental tests” | Đó là skip kiểm thử, không chứng minh correctness |
| “Đã cache `.m2` trong GitHub Actions tức có build-output cache” | Thông thường chỉ là cached dependencies/plugins |
| “`mvn clean` xóa mọi cache” | Clean xóa build output theo Clean Plugin; extension cache/dependency cache có thể còn |
| “Cache hit nghĩa mọi file trong target đã restore” | Extension có giới hạn output restore/attachedOutputs |
| “Resources Plugin content check là toàn build cache” | Chỉ so output resources trong plugin |
| “JAR Plugin không repackage nghĩa compiler không chạy” | Hai goals có hành vi riêng |
| “`useIncrementalCompilation=true` chỉ compile đúng một file sửa” | Với Compiler Plugin 3.x javac, khi source đổi có thể recompile toàn module |
| “`useIncrementalCompilation=false` luôn nhanh và an toàn” | Timestamp-only mode có thể để lại class phụ thuộc cũ |
| “Không thay source thì output không thể đổi” | POM, dependencies, environment, codegen, toolchain có thể ảnh hưởng |
| “Cache chỉ hoạt động ở package” | Extension 1.3.0 có thể cache compile-only, tùy `cacheCompile` |
| “Mọi Maven goal đều được cache” | Cache policy có giới hạn phase, goal, mixed/forked invocations |
| “Có remote cache nghĩa có thể bỏ security tests” | Không. Policy phải bảo đảm kiểm chứng đúng trust boundary |
| “Cache hit luôn tiết kiệm thời gian” | Hashing, network, restore overhead có thể lớn hơn công việc nhỏ |
| “Parallel `-T` là incremental” | Đó là concurrency optimization |
| “Maven Reactor `-pl -am` là build cache” | Đó là chọn phạm vi module, không lưu/restore output |
| “Output giống nhau thì key chắc chắn đúng” | Cần thử các changed inputs, nhất là hidden env/generated inputs |
| “Build xanh từ cache chứng minh tests vừa chạy” | Có thể tests là cached result; cần evidence và chính sách |
| “Build cache chứa artifacts nên có thể publish trực tiếp” | Cache artifact lifecycle khác release repository |
| “Xóa cache là cách chữa mọi bug” | Xóa có thể giúp diagnosis, nhưng phải tìm missing inputs/toolchain mismatch |

## 27. Troubleshooting theo triệu chứng

### 27.1. `mvn verify` biên dịch lại mọi file khi chỉ sửa một Java source

Đầu tiên kiểm Compiler Plugin 3.x `useIncrementalCompilation=true` và kiểu dependency/source change detection. **Đây có thể là hành vi đúng**. Nếu module rất lớn, cân nhắc tách module có ranh giới hợp lý, code generation và architecture; không lập tức bật timestamp-only mode.

### 27.2. `mvn verify` không biên dịch lại và runtime vẫn gọi method đã xóa

Nghi stale class. Kiểm `useIncrementalCompilation=false`, IDE compiler vs Maven output, classpath từ module khác hoặc JAR cũ trong local repo. Chạy `clean verify` với cache read disabled và xem `NoSuchMethodError`/class loading, kiểm dependency tree.

### 27.3. `mvn clean verify` vẫn rất nhanh sau khi bật extension

Xem cache logs. Nếu extension báo hit/restore, đó là output cache. Nếu không, có thể project quá nhỏ, repository warm, CPU/IO khác hoặc lệnh không chạy đầy đủ tests. Kiểm JUnit reports và output freshness, không chỉ time.

### 27.4. `mvn clean verify` lần hai vẫn build mọi thứ dù extension active

Có thể cache key thay đổi, cache entry không được save, build inputs có timestamp/random values, input selectors quá rộng, config không loaded, output side-effect/goal khiến module uncacheable, JDK/env drift hoặc remote cache unreachable.

Xem `buildinfo.xml`, `cache-report.xml`, `diff-*.xml`, module logs và các plugin parameters ảnh hưởng cache.

### 27.5. Một resource đã sửa nhưng cache trả JAR cũ

Đây là correctness incident. Tạm disable cache read cho module/job, chạy clean no-cache, xác định resource có thuộc input key không, resource filtering có lấy hidden env không, và kiểm generated output classes/archive. Không tiếp tục publish artifact từ cache đáng ngờ.

### 27.6. CI unit tests không chạy sau cache hit

Đọc cache execution-control policy: có phải test report được reuse không, có cần run tests mỗi job hay không? Nếu release gate yêu cầu thực thi mới, cấu hình always-run hoặc tách no-cache test lane, và xác minh report thật. Không ghi số “tests run” lấy từ log cũ mà không gắn provenance.

### 27.7. IDE không thấy classes dù Maven báo cache hit

Extension có partial restoration; IDE có thể cần native compiler output hoặc cấu hình attached outputs để khôi phục classes. Kiểm `target/classes` và IntelliJ/Eclipse build dirs. Không giả định artifact JAR ở cache đồng nghĩa IDE output tree đầy đủ.

### 27.8. `-Dmaven.build.cache.enabled=false` vẫn thấy compiler no-op

Điều này **bình thường** vì cache extension và Compiler Plugin incremental là hai cơ chế độc lập. Nếu không `clean` và source/output không đổi, compiler có thể skip.

### 27.9. Test fail khi đổi resource trong lab

Nếu `status.txt` đã đổi nhưng assertions vẫn mong `resource-ok`, tests fail là **đúng**. Cập nhật expected values theo contract mới rồi chạy lại. Không skip tests để “lấy benchmark”.

### 27.10. Đổi JDK version nhưng build cache vẫn hit

Nếu build output/JUnit runtime thực sự cần khác theo JDK, cache policy cần coi toolchain/JDK là input quan trọng hoặc tách cache namespace. Verify bằng clean no-cache builds trên từng JDK. Đừng coi cross-JDK hit tự nó là bằng chứng artifact portable.

## 28. Checklist trước khi bật cache trong project lớn

1. Phân biệt dependency cache, per-plugin incrementality và output cache.
2. Pin Maven/JDK/Compiler/Resources/JAR/Surefire versions.
3. Chạy clean verify đúng và pass trước khi tối ưu.
4. Đọc docs parameter incremental của **đúng plugin version**.
5. Giữ Compiler 3.x mode an toàn trước khi benchmark.
6. Không dùng `-DskipTests` thay caching.
7. Cân nhắc `forceCreation=true` khi có JAR post-process thực sự.
8. Chọn `changeDetection` của Resources Plugin theo content/filtering semantics.
9. Tách warm-target benchmark khỏi cold-target benchmark.
10. Ghi log plugin skip/no-op và cache hit/miss riêng.
11. Không dựa duy nhất vào tổng thời gian build.
12. Cố định JDK/compiler options và Maven profiles.
13. Kiểm dependencies/plugin artifacts trước khi đo để giảm network noise.
14. Nếu bật extension, dùng version được tổ chức cho phép.
15. Xác minh `.mvn/extensions.xml` được load thực tế.
16. Dùng `maven.build.cache.enabled=false` để so clean baseline.
17. Thử `skipCache`/`skipSave` đúng mục đích.
18. Kiểm inputs của code generation, annotation processors và shared configs.
19. Kiểm JDK/toolchain khác nhau có làm cache key mất đúngness không.
20. Không cache resource/JAR chứa secrets.
21. Rà soát attachedOutputs để không bỏ output quan trọng.
22. Không tự cache cả thư mục target không kiểm duyệt.
23. Cẩn trọng với plugin goals có side effects.
24. Tách signed/publish step khỏi pure cacheable build nếu phù hợp.
25. Không cho untrusted CI jobs ghi trusted release remote cache.
26. Giám sát cache hit rate và miss reasons.
27. Chạy no-cache validation sau thay đổi source/resource/POM/env.
28. Với Reactor, kiểm downstream dependencies khi upstream thay.
29. Kiểm JUnit reports theo từng job/JDK, không dùng stale files.
30. Có khả năng tắt cache và quarantine entry không đúng.
31. Xác minh output artifact bằng runtime smoke test.
32. Không kết luận một cache hit nếu chỉ thấy plugin log “Nothing to compile”.
33. Không nhầm `-pl -am` hoặc `-T` với build output cache.
34. Ghi CI policy và phạm vi cache reuse được chấp nhận.
35. Ưu tiên correctness và auditability trước tốc độ.

## 29. Câu hỏi tự kiểm tra

**Câu 1.** Compiler Plugin báo không cần compile, đã có cache hit chưa?

**Đáp:** Chưa chắc. Có thể plugin dùng incremental state trong `target` và không gọi `javac`.

**Câu 2.** Maven 3.x Compiler Plugin `useIncrementalCompilation=true` có compile đúng một source file thay đổi không?

**Đáp:** Không nhất thiết. Với javac, source/dependency thay đổi có thể khiến plugin compile lại toàn bộ sources của module để bảo đảm dependencies nội bộ không bị cũ.

**Câu 3.** Vì sao `useIncrementalCompilation=false` có nguy cơ?

**Đáp:** Nó thường chỉ compile file mới hơn class tương ứng, bỏ sót những classes dùng API đã thay đổi của một class khác.

**Câu 4.** Resources Plugin 3.5.0 `changeDetection=content` có chức năng gì?

**Đáp:** Tránh ghi đè target resource khi content đầu ra không khác; không phải một build-output cache cho cả project.

**Câu 5.** JAR Plugin `forceCreation=false` có ý nghĩa gì?

**Đáp:** Plugin có thể không tạo lại JAR nếu inputs/output không thay đổi; cần lưu ý plugins post-process JAR.

**Câu 6.** Surefire có tự bỏ qua JUnit tests chỉ vì Compiler Plugin no-op không?

**Đáp:** Không theo cơ chế mặc định; goal test vẫn có thể thực thi tests trong lifecycle.

**Câu 7.** Maven dependency cache có khôi phục `target/classes` sau clean không?

**Đáp:** Không tự động. Nó chủ yếu lưu artifacts/dependencies theo GAV.

**Câu 8.** Apache Maven Build Cache Extension làm gì khác plugin incremental?

**Đáp:** Tính fingerprint/cache key từ build inputs và restore output cho trạng thái module phù hợp, thay vì dựa vào từng plugin tự xử lý local incremental work.

**Câu 9.** `mvn clean verify` có thể hit output cache không?

**Đáp:** Có, khi extension có entry phù hợp và cache policy hỗ trợ; `clean` không nhất thiết xóa extension cache nằm ngoài target.

**Câu 10.** `maven.build.cache.cacheCompile=false` có tắt compiler incrementality không?

**Đáp:** Không. Nó điều chỉnh cache phase policy của extension.

**Câu 11.** `skipCache` và `skipSave` khác nhau thế nào?

**Đáp:** `skipCache` bỏ đọc entry; `skipSave` bỏ ghi entry.

**Câu 12.** Chỉ thêm `.mvn/extensions.xml` thì CI agent khác có chung cache không?

**Đáp:** Không. Remote/shared cache phải được cấu hình và cấp quyền riêng.

**Câu 13.** Cache hit có bắt buộc chạy Surefire tests lần này không?

**Đáp:** Không. Tùy execution-control policy, test result có thể được reuse. Release gate cần phân biệt kết quả cũ với thực thi mới.

**Câu 14.** Vì sao cần clean no-cache baseline?

**Đáp:** Để so artifact/behavior và phát hiện cache key thiếu input hoặc plugin incremental để lại stale outputs.

**Câu 15.** Sửa resource có thể yêu cầu Java source compile lại không?

**Đáp:** Không nhất thiết; Resources Plugin xử lý file resource, còn Compiler Plugin kiểm source/dependency riêng.

**Câu 16.** `-T` và `-pl -am` có phải build-output cache không?

**Đáp:** Không. Chúng là parallel execution và Reactor module selection.

**Câu 17.** Nếu cache chứa token trong generated resource thì có an toàn không?

**Đáp:** Không. Cache có thể lưu/lan truyền secret; phải ngăn secret entering artifacts và kiểm quyền cache.

**Câu 18.** Đổi JDK từ 17 sang 21 rồi cache hit có luôn đúng không?

**Đáp:** Không thể khẳng định nếu JDK/toolchain ảnh hưởng outputs hoặc runtime tests. Phải model inputs và verify.

**Câu 19.** Vì sao một module trong Reactor hit nhưng module khác miss?

**Đáp:** Input fingerprints và dependency graph khác nhau; mỗi module có trạng thái/build inputs riêng.

**Câu 20.** Điều gì nên ưu tiên khi tăng tốc Maven build?

**Đáp:** Correctness và khả năng tái tạo trước; sau đó đo hot paths, dùng incremental plugin đúng và chỉ bật output cache khi input/output model đã được kiểm chứng.

## 30. Tài liệu chính thức

- [Apache Maven Compiler Plugin 3.15.0 — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Apache Maven Compiler Plugin — `useIncrementalCompilation`](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html#useIncrementalCompilation)
- [Apache Maven Compiler Plugin 4.x — `incrementalCompilation`](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/compile-mojo.html)
- [Apache Maven Resources Plugin 3.5.0 — `resources:resources` và `changeDetection`](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html)
- [Apache Maven JAR Plugin 3.4.2 — `jar:jar` và `forceCreation`](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Apache Maven Surefire Plugin — `surefire:test`](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven Build Cache Extension 1.3.0 — Getting Started](https://maven.apache.org/extensions/maven-build-cache-extension/)
- [Apache Maven Build Cache Extension — Concepts](https://maven.apache.org/extensions/maven-build-cache-extension/concepts.html)
- [Apache Maven Build Cache Extension — Usage](https://maven.apache.org/extensions/maven-build-cache-extension/usage.html)
- [Apache Maven Build Cache Extension — Parameters](https://maven.apache.org/extensions/maven-build-cache-extension/parameters.html)
- [Apache Maven Build Cache Extension — Configuration](https://maven.apache.org/extensions/maven-build-cache-extension/build-cache-config.html)
- [Apache Maven Build Cache Extension — Cache Performance](https://maven.apache.org/extensions/maven-build-cache-extension/performance.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Local Repository](https://maven.apache.org/repositories/local.html)
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/)

