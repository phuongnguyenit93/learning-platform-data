# Extension cache build và điều kiện khai báo đầu vào đúng trong Maven

## 1. Build cache nhanh hơn khi nào, nguy hiểm khi nào?

Trong một ứng dụng Java nhiều module, Maven thường phải biên dịch, kiểm thử và đóng gói lại các module dù một phần lớn mã nguồn không đổi. **Apache Maven Build Cache Extension** cho phép lưu kết quả build để dùng lại khi đầu vào của một module tương đương với lần đã build trước.

Vấn đề cốt lõi không chỉ là tốc độ. Nếu một plugin sinh Java source từ `schemas/order.proto` nhưng extension không đưa `order.proto` vào dấu vân tay đầu vào, việc sửa schema có thể không làm cache key đổi. Maven có thể **HIT cache và lấy output cũ**, dù một build không cache sẽ tạo code khác. Kết quả có thể là `BUILD SUCCESS` nhưng JAR **sai**.

> **Chỉ tái sử dụng cache khi mọi đầu vào có ảnh hưởng tới output mà dự án quan tâm đều được nhận diện, hoặc được kiểm tra bằng một cơ chế tương đương đủ đáng tin.**

Bài thuộc nhóm **Hiệu năng – Build Tool Maven**, giải thích phiên bản **Apache Maven Build Cache Extension 1.3.0**, Maven **3.9.x**, Java **17+**. Phiên bản 1.3.0 có trong danh mục Apache Maven phát hành vào tháng 8/2026. Cấu hình demo dùng đúng model XML 1.3.0 và một project Java 17/JUnit Jupiter 5 thực sự biên dịch được.

### Mục tiêu học tập

- Phân biệt Maven dependency cache `~/.m2/repository` với build result cache.
- Hiểu fingerprint/cache key, HIT, MISS, false HIT và false MISS.
- Khai extension trong `.mvn/extensions.xml`, không nhầm với Maven dependency/plugin bình thường.
- Sử dụng `.mvn/maven-build-cache-config.xml`, input `glob`, `includes`, `excludes` và plugin `dirScan`.
- Nhận diện source/resources, dependencies, effective POM, plugin parameters và môi trường là các đầu vào có thể ảnh hưởng build.
- Kiểm `buildinfo.xml` thay vì chỉ suy đoán file nào đã được hash.
- Thử thay đổi resource ngoài `src/main/resources` và quan sát cache invalidation.
- Phân biệt chính xác `skipCache`, `skipSave`, `enabled=false` và remote cache switches.
- Kiểm outputs được restore, goals có side effects và quyền truy cập remote cache.
- Xây quy trình kiểm correctness so với clean build không cache trước khi tối ưu hit rate.

## 2. Maven local repository khác Maven build cache

| Loại cache | Nội dung | Mục đích |
| --- | --- | --- |
| Maven local repository | JAR/POM/plugins tải từ repositories hoặc `mvn install` | Không phải tải dependencies lặp lại |
| Build Cache Extension local cache | Records, input hashes, cached project outputs | Không phải compile/test/package lại phần tương đương |
| Remote build cache | Records và outputs dùng chung giữa agents | Tăng reuse giữa CI runners và developers |
| IDE compiler cache | Index và class/analysis của IDE | Tăng tốc thao tác trong IDE |

Maven local repository thường nằm ở `~/.m2/repository`. Build Cache Extension mặc định sử dụng thư mục `build-cache` cạnh local Maven repository (thường `~/.m2/build-cache`). Hai nơi phục vụ mục đích khác nhau. Khi xóa dependency cache, Maven phải tải dependencies lại; khi xóa build cache, Maven mất records có thể giúp skip build. Không dùng thao tác xóa toàn `~/.m2` để giải quyết một cache miss thông thường.

### 2.1. Luồng xử lý

```text
Git checkout + POM + resource + schema + dependencies
                       |
                       v
             Maven Build Cache Extension
                       |
              Inspect configured inputs
                       |
                 Calculate cache key
                       |
                +------+-------+
                |              |
                v              v
             Cache HIT       Cache MISS
                |              |
                v              v
           Restore output    Run Maven goals
                |              |
                v              v
            Reconcile        Save cache
            plugin state      if allowed
                |              |
                +-------+------+
                        |
                        v
                 Build result
```

Cache Extension sử dụng **hash của nội dung file**, không đơn thuần là timestamp. Theo tài liệu Apache, thuật toán tạo key xét **sources, project dependencies, effective POM và plugin parameters**; một số plugin properties còn được kiểm ở runtime qua reconciliation. Khi có cache record tương đương, extension có thể khôi phục artifact và tránh lặp một số build goals.

Tuy nhiên, Maven build historically không phải hệ thống khai báo đầy đủ mọi input/output của mỗi plugin. Custom plugins có thể đọc file ngoài project, biến môi trường, network API hoặc sinh file ở thư mục bất thường. Vì vậy **build owner chịu trách nhiệm xác minh input contract thực tế**, không chỉ bật extension rồi mặc định tin cache.

### 2.2. Cache HIT, MISS và hai lỗi khác nhau

**HIT đúng:** Cùng input được dùng lại một artifact tương đương với output của build thông thường.

**MISS đúng:** Đầu vào quan trọng đổi, extension chạy lại công việc để tạo output mới.

**False MISS:** Cache key đổi do thay đổi vô hại, chẳng hạn `scratch/run.log`, nên tốn thời gian build lại. Đây là vấn đề hiệu năng.

**False HIT:** Đầu vào chức năng đổi nhưng key vẫn được xem tương đương, dẫn tới output stale. Đây là vấn đề **correctness**, có thể làm mất kiểm chứng test hoặc phát hành binary sai.

Khi lựa chọn giữa một số lần cache miss dư thừa và khả năng false HIT, **ưu tiên loại bỏ false HIT**. Chỉ loại thêm input để nâng hit rate khi chứng minh được nó không ảnh hưởng output/validation mà policy yêu cầu.

## 3. Cache key: những gì phải được nhận diện

Hãy xem build là một hàm trừu tượng:

```text
Output = Build(Source, Dependencies, BuildModel, Environment, ExternalState)
```

Trong đó:
- **Source:** Java, resources, tests, templates, SQL, Proto, OpenAPI YAML/JSON.
- **Dependencies:** các JAR và POM được resolve, transitive graph, annotation processors, plugin dependencies.
- **BuildModel:** effective POM, parent/BOM, active Maven profiles, compiler/surefire/resources settings.
- **Environment:** JDK version/vendor, OS/architecture, encoding, locale, filesystem behavior, toolchains.
- **ExternalState:** dữ liệu API/schema server, env variables, credentials làm thay build behavior, clock/random inputs.

Không nhất thiết tất cả thành phần trên được hash bằng cùng một cách. Một số được phản ánh ở effective POM hoặc dependencies; một số được kiểm qua **plugin reconciliation**; một số phải **pin môi trường** hoặc không thể cache đáng tin.

### 3.1. Những file dễ bị bỏ sót

| Path | Ảnh hưởng tiềm năng | Cách xử lý |
| --- | --- | --- |
| `src/main/java` | Bytecode | Thường auto discovered; vẫn xem metadata |
| `src/test/java` | Test behavior | Theo dõi sources và test execution policy |
| `src/main/resources` | File trong artifact | Kiểm packaging và input list |
| `src/test/resources` | Fixtures và tests | Đưa vào fingerprint |
| `build-input/label.properties` | Config được đóng gói vào JAR | Explicit `include` hoặc kiểm auto discovery |
| `schemas/*.proto` | Generated Java | Bổ sung `*.proto`, folder, generator options |
| `openapi/*.yaml` | OpenAPI-generated sources | Thêm YAML path/glob và plugin config |
| `templates/*.ftl` | Generated resources | Thêm templates folder/type |
| `db/migration/*.sql` | Test schema/resources | Include nếu build/tests tiêu thụ |
| `assembly/*.xml` | JAR/WAR/ZIP layout | Include descriptor |
| `frontend/package-lock.json` | Frontend bundle dependencies | Include lockfile và phụ thuộc ngoài Maven |
| `docs/*.md` | Maven Site output | Include nếu site là output cần cache, không tự ép cho JAR |
| `scratch/*.log` | Log tạm | Có thể exclude nếu chứng minh không ảnh hưởng output |

**Đưa vào một directory mà quên mở rộng file glob vẫn có thể bỏ sót file.** Ví dụ `<include>schemas</include>` nhưng `<glob>{*.java,*.xml}</glob>` có nguy cơ bỏ qua `*.proto`. Hãy kiểm filename/path xuất hiện trong `buildinfo.xml`.

### 3.2. BuildModel không chỉ là pom.xml

Một POM effective có thể tổng hợp từ parent, BOM, active profiles, pluginManagement và properties. Sửa `maven.compiler.release`, `resources filtering` hoặc `surefire skipTests` có thể thay output hay mức validation ngay cả khi `src/main/java` không đổi.

Đặc biệt, nếu một cached build có `skipTests=true`, không được dùng record đó làm bằng chứng rằng tests đã chạy cho invocation yêu cầu `skipTests=false`. Plugin runtime reconciliation hoặc chính sách **always-run tests** phải được xem xét.

### 3.3. External inputs không thể mặc định tự phát hiện

Một codegen plugin đọc `/opt/company/schema.json` hoặc một API service, nhưng Maven build không khai báo giá trị external đó. Không thể chỉ hash source tree rồi khẳng định build tương đương. Cách xử lý:
1. Đưa schema thành dependency/file được version hóa.
2. Khai input hoặc plugin parameter sao cho cache engine theo dõi.
3. Pin external tool/service versions và environment.
4. Nếu không làm được, tắt cache cho module/goal hoặc luôn chạy bước đó.

Đừng “tối ưu” bằng cách exclude external config khỏi key chỉ vì nó làm hit rate thấp.

## 4. Cài Apache Maven Build Cache Extension 1.3.0

### 4.1. Điều kiện môi trường

Apache Maven Build Cache Extension yêu cầu **Maven 3.9.0 trở lên**, có tài liệu cho Maven 4. Bài mẫu dùng JDK 17.

```bash
mvn -version
java -version
```

`mvn -version` cho biết Maven thực sự chạy bằng JDK nào; `java -version` có thể khác nếu PATH/JAVA_HOME không đồng nhất. Maven cache extension 1.3.0 và cấu hình của nó nên được pin cùng Maven toolchain/CI image để tránh thay đổi behavior giữa agents.

### 4.2. .mvn/extensions.xml

Từ root project tạo `.mvn/extensions.xml`:

```xml
<extensions>
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
```

Đây là **Maven core extension**, không đặt trong `<dependencies>` của application. Apache còn hỗ trợ `<build><extensions>` trong POM, nhưng `.mvn/extensions.xml` là cách được khuyến nghị để extension có thể tương tác với Maven APIs từ sớm.

Commit file này vào Git. Khi nâng extension, chạy lại kiểm thử cache key, output restore và version compatibility. Không dùng `LATEST` hoặc snapshot extension không kiểm thử trong pipeline release.

### 4.3. .mvn/maven-build-cache-config.xml

File cấu hình tùy chọn nằm tại `.mvn/maven-build-cache-config.xml`. Đối với **1.3.0**, dùng root namespace/schema version phù hợp:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<cache xmlns="http://maven.apache.org/BUILD-CACHE-CONFIG/1.3.0"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://maven.apache.org/BUILD-CACHE-CONFIG/1.3.0 https://maven.apache.org/xsd/build-cache-config-1.3.0.xsd">

    <configuration>
        <enabled>true</enabled>
        <hashAlgorithm>SHA-256</hashAlgorithm>
        <local>
            <maxBuildsCached>3</maxBuildsCached>
        </local>
        <debugs>
            <debug>FileHash</debug>
            <debug>EffectivePom</debug>
        </debugs>
    </configuration>

    <input>
        <global>
            <glob>{*.java,*.xml,*.properties}</glob>
            <includes>
                <include>build-input</include>
            </includes>
            <excludes>
                <exclude>scratch</exclude>
            </excludes>
        </global>
    </input>
</cache>
```

**Ý nghĩa từng thành phần:**
- `enabled=true` bật extension.
- `SHA-256` dùng thuật toán hash được schema hỗ trợ, nhưng có thể tốn CPU hơn thuật toán `XX` mặc định. Đây là lựa chọn bài lab, không phải khẳng định SHA-256 luôn nhanh nhất.
- `maxBuildsCached=3` giữ số cache records local có hạn cho mỗi artifact, không quyết định số Maven dependencies.
- `FileHash` cho phép lưu per-file digests trong build metadata.
- `EffectivePom` lưu effective POM cho việc tìm lý do MISS; metadata có thể nhạy cảm, xem trước khi chia sẻ remote.
- `glob` chỉ chọn một số file types. Trong project có YAML/Proto/Groovy/templates, **phải bổ sung types ấy nếu chúng là inputs**.
- `include build-input` thêm đường dẫn custom resource vào danh sách kiểm.
- `exclude scratch` bỏ folder demo chứa log tạm; chỉ đúng khi folder không ảnh hưởng output.

Đây là **một file XML hoàn chỉnh** có thể đặt trực tiếp trong lab. Các fragment nâng cao ở phần sau sẽ được ghi rõ nếu **không phải file đầy đủ**.

### 4.4. Có nên dùng XX hay SHA-256?

Maven Build Cache Extension dùng một số thuật toán nhanh như `XX`, `XXMM`, `METRO` bên cạnh SHA-1/SHA-256/SHA-384/SHA-512. `XX` là default hướng hiệu năng. SHA-256 giảm lo ngại collision từ thuật toán phi mật mã, nhưng **không tự xác thực danh tính máy ghi remote cache**.

Một cache remote chịu nguy cơ actor không đáng tin phải được bảo vệ bằng **TLS/ACL, quyền ghi tách biệt, integrity/provenance của artifacts**, không chỉ thay hashAlgorithm. Quyết định hash algorithm dựa trên hiệu năng và threat model, không nhầm với chữ ký số.

## 5. Điều kiện include/glob/exclude đúng

### 5.1. Global glob

```xml
<input>
    <global>
        <glob>{*.java,*.xml,*.properties,*.yaml,*.yml,*.json,*.proto}</glob>
    </global>
</input>
```

Đây là **fragment**, không phải root config đầy đủ. Nó dùng để minh họa project có thêm YAML/JSON/Proto. Trong thực tế cần chỉ định file types đang được codegen/plugins tiêu thụ, thay vì liệt kê tùy tiện mọi định dạng.

**Sai phổ biến:** glob chỉ `*.java` nhưng project dùng file `*.proto` để sinh Java. Schema đổi mà cache key không đổi có thể làm HIT sai.

### 5.2. Global include

```xml
<input>
    <global>
        <includes>
            <include>schemas/</include>
            <include>build-input/</include>
        </includes>
    </global>
</input>
```

Relative paths được tính từ **module basedir**. Với multi-module, cùng chuỗi `schemas/` trong module A và B có thể trỏ tới hai locations khác nhau. Không mặc định một `include` trong root sẽ luôn đọc đúng sibling folder ở mọi module.

### 5.3. Exclude cẩn thận

```xml
<input>
    <global>
        <excludes>
            <exclude>scratch</exclude>
        </excludes>
    </global>
</input>
```

Chỉ exclude nếu folder thực sự không được tiêu thụ bởi build. Nếu `scratch/report.json` lại được một plugin dùng để tạo artifact hoặc test reports, exclude nó gây false HIT. Một file được tạo trong `target` thường là **output**, không phải input, nhưng cũng phải xem các custom plugins sử dụng nó như thế nào.

### 5.4. Auto discovery có thể đã đủ

Maven cache extension introspect Maven project, sources, resources và plugin configuration để tự xác định nhiều input paths. Nếu bạn đã khai một custom resource directory trong POM, extension **có thể tự phát hiện** nó.

Do đó, bài thực hành **không tuyên bố cứ xóa include là sẽ có false HIT**. Hãy dựa vào `buildinfo.xml`:
1. Kiểm cache metadata có `build-input/label.properties` không.
2. Nếu đã có, explicit include có thể là redundant nhưng có ích như cam kết đọc được.
3. Nếu không có, điều chỉnh include/glob/plugin dirScan.
4. Thay đổi file và kiểm lần build sau không dùng artifact cũ.
5. Xác minh bằng stdout và clean build không cache.

### 5.5. Plugin dirScan khi introspection thiếu

Một plugin có property `protoBaseDirectory` không được scanner nhận đúng có thể cần rule:

```xml
<input>
    <global>
        <glob>{*.java,*.xml,*.properties,*.proto}</glob>
    </global>
    <plugins>
        <plugin artifactId="protoc-maven-plugin">
            <dirScan mode="auto">
                <tagScanConfigs>
                    <tagScanConfig tagName="protoBaseDirectory"
                                   recursive="true"
                                   glob="{*.proto}"/>
                </tagScanConfigs>
            </dirScan>
        </plugin>
    </plugins>
</input>
```

**Đây là fragment nâng cao** dựa trên một plugin có property tên như trên; tên thật phụ thuộc plugin/version của project. Chỉ dùng sau khi kiểm plugin configuration và input metadata. Không copy vào POM lab nếu project không có Proto generator.

### 5.6. Project-level overrides

Maven Build Cache Extension còn hỗ trợ các properties trên POM/module:
- `maven.build.cache.input.glob`: ghi đè global glob ở module.
- `maven.build.cache.input.*`: thêm paths ở module.
- `maven.build.cache.exclude.*`: excludes.
- `maven.build.cache.processPlugins`: bật/tắt introspection plugins.
- `maven.build.cache.skipCache` và `maven.build.cache.skipSave`: behavior ở project cụ thể.

Sử dụng chỉ khi module có input contract khác. Nếu người khác đặt `input.glob` chỉ còn `*.java` trong child POM, global config có thể không bao phủ YAML/Proto của module đó; xem effective properties và build metadata để nhận diện.

## 6. Dự án Java 17/JUnit Jupiter để kiểm đúng resource input

Mẫu dưới đây đặt `label.properties` trong folder `build-input` bên ngoài source resource path chuẩn. Maven Resources Plugin đóng gói nó vào JAR. Nếu đổi `alpha` thành `beta`, **đầu ra ứng dụng cũng phải đổi** — đây là một negative test đơn giản cho cache correctness.

### 6.1. Cây thư mục

```text
cache-input-lab/
├── pom.xml
├── .mvn/
│   ├── extensions.xml
│   └── maven-build-cache-config.xml
├── build-input/
│   └── label.properties
├── src/
│   ├── main/java/dev/example/cache/CacheExample.java
│   └── test/java/dev/example/cache/CacheExampleTest.java
└── .gitignore
```

Các file XML extension/cache đã có toàn văn ở mục 4.2–4.3; các file còn lại được cung cấp bên dưới. Không cần database, Docker hay repository riêng để chạy local cache demo.

### 6.2. pom.xml hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>cache-input-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Cache Input Lab</name>
    <description>Demonstrate correctness of Maven build-cache inputs</description>

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
        <resources>
            <resource>
                <directory>build-input</directory>
                <filtering>false</filtering>
                <includes>
                    <include>*.properties</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
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

**Điểm cần đọc kỹ:**
- `<resources>` nói Maven Resources Plugin lấy file từ `build-input`, không phải `src/main/resources`.
- `<filtering>false</filtering>` giữ nguyên bytes của resource.
- `<include>*.properties</include>` là **resource selector trong POM**; nó khác `<input><global><includes>` của cache config.
- Extension 1.3.0 **không** cần khai như `<dependency>` hoặc build plugin.
- Build bình thường dùng Java 17/JUnit 5, Maven Compiler/Resources/Surefire/JAR Plugin versions được pin.
- Khi project thật có `src/main/resources` và `build-input` cùng lúc, cần khai cả hai resource roots trong `<resources>` để không vô tình bỏ standard resources.
- POM không khai deploy repository/credentials; lệnh demo chỉ compile/test/package, không publish.

### 6.3. build-input/label.properties

```properties
demo.label=alpha
```

Đây là input cần đưa vào fingerprint. Thay file này phải làm resource copy/packaged JAR tương ứng thay đổi.

### 6.4. src/main/java/dev/example/cache/CacheExample.java

```java
package dev.example.cache;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class CacheExample {

    private CacheExample() {
    }

    public static String currentLabel() {
        try (InputStream input =
                     CacheExample.class.getClassLoader()
                             .getResourceAsStream("label.properties")) {

            if (input == null) {
                throw new IllegalStateException(
                        "Missing resource label.properties");
            }

            Properties values = new Properties();
            values.load(
                    new InputStreamReader(input, StandardCharsets.UTF_8));

            String result = values.getProperty("demo.label");
            if (result == null || result.isBlank()) {
                throw new IllegalStateException(
                        "Missing demo.label");
            }
            return result.strip();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    public static String format(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("blank label");
        }
        return "cache-label=" + label.strip();
    }

    public static void main(String[] args) {
        System.out.println(format(currentLabel()));
    }
}
```

Maven Resources Plugin sẽ copy `label.properties` tới root classpath trong JAR. `getResourceAsStream` đọc đúng resource đó. Chương trình không dùng clock, network, database, random hay environment variables, nên khi output khác, dễ kiểm đầu vào nào đã thay đổi.

`Properties.load(Reader)` kết hợp `UTF-8` giúp xử lý text resource có dấu Unicode. `String.isBlank/strip` có trong Java 17. Nếu resource hoặc key không tồn tại, code báo lỗi thay vì âm thầm dùng một giá trị default khiến stale result khó nhận ra.

### 6.5. src/test/java/dev/example/cache/CacheExampleTest.java

```java
package dev.example.cache;

import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class CacheExampleTest {

    @Test
    void formatsLabel() {
        assertEquals("cache-label=demo",
                CacheExample.format(" demo "));
    }

    @Test
    void rejectsBlankLabel() {
        assertThrows(IllegalArgumentException.class,
                () -> CacheExample.format(" "));
    }

    @Test
    void findsPackagedResource() {
        assertTrue(Set.of("alpha", "beta")
                .contains(CacheExample.currentLabel()));
    }
}
```

Có **3 JUnit Jupiter unit tests**. Test cuối chấp nhận cả `alpha` và `beta` có chủ đích: khi đổi input hợp lệ, build không bị đánh fail chỉ vì test pin cứng giá trị ban đầu. Nếu `label.properties` bị bỏ khỏi JAR, test phải fail ngay. Production tests có thể chặt hơn tùy business requirements.

### 6.6. .gitignore

```gitignore
target/
.m2-isolated/
scratch/
*.log
```

Không ignore `build-input` hoặc `.mvn/*.xml`. Đây là **các file cấu hình đầu vào cần commit/review**, không phải cache output. Thư mục build-cache mặc định nằm ngoài project dưới `~/.m2`.

### 6.7. Chạy build đầu tiên

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/cache-input-lab-1.0.0-SNAPSHOT.jar dev.example.cache.CacheExample
```

Khi Maven 3.9.x, Java 17+ và dependencies/plugins có thể resolve, build chạy 3 tests và tạo JAR. Build Cache Extension có thể ghi local record sau build thành công.

**Các dòng log Maven minh họa (không cam kết nguyên văn):**

```text
[INFO] Loading cache configuration from .../.mvn/maven-build-cache-config.xml
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
```

**Stdout chính xác của ứng dụng:**

```text
cache-label=alpha
```

`java -cp ...jar ClassName` không đòi thiết lập `Main-Class` trong manifest, khác với `java -jar`.

### 6.8. Chạy lại với cùng input

```bash
mvn -B -ntp clean verify
java -cp target/cache-input-lab-1.0.0-SNAPSHOT.jar dev.example.cache.CacheExample
```

Nếu cache record đủ phù hợp, có thể xuất hiện log `[CACHE]` thông báo restore/reuse và công việc được skip. Ứng dụng vẫn phải in **cache-label=alpha**. Đừng tuyên bố chắc chắn cache HIT chỉ vì `BUILD SUCCESS` hay thời gian nhanh hơn: Maven dependency cache cũng làm build lần hai nhanh dù extension chưa HIT.

### 6.9. Đổi input từ alpha thành beta

Linux/macOS:

```bash
printf 'demo.label=beta\n' > build-input/label.properties
mvn -B -ntp clean verify
java -cp target/cache-input-lab-1.0.0-SNAPSHOT.jar dev.example.cache.CacheExample
```

Windows PowerShell:

```powershell
[System.IO.File]::WriteAllText(
    "build-input/label.properties",
    "demo.label=beta" + [Environment]::NewLine,
    [System.Text.Encoding]::UTF8
)
mvn -B -ntp clean verify
java -cp target/cache-input-lab-1.0.0-SNAPSHOT.jar dev.example.cache.CacheExample
```

**Stdout chính xác nếu resource mới được đưa vào JAR:**

```text
cache-label=beta
```

Khi input contract đúng, sửa resource làm fingerprint khác và không được tái sử dụng JAR cũ có alpha. Nếu cache vẫn HIT hay stdout vẫn alpha, kiểm các khả năng: sửa nhầm folder, POM resource root sai, file không được hash, artifact restore stale, chạy nhầm JAR, hoặc cache engine có lỗi. **Không suy kết luận chỉ từ một dòng log.**

### 6.10. Đối chiếu với build không cache

```bash
mvn -B -ntp -Dmaven.build.cache.enabled=false clean verify
java -cp target/cache-input-lab-1.0.0-SNAPSHOT.jar dev.example.cache.CacheExample
```

Kết quả application phải là `cache-label=beta` khi file input đang là beta. Đây là **baseline correctness**. So cached build với uncached clean build cho cùng input, kiểm JAR resources và tests, không chỉ Maven exit code.

Nếu muốn so hash nhị phân JAR, cân nhắc `project.build.outputTimestamp`, archive ordering và plugin reproducibility. Các file JAR có thể có timestamp metadata khác nhau ngay cả khi functional behavior giống nhau. Tùy policy, có thể yêu cầu byte-for-byte equality hoặc functional equivalence; cần ghi rõ tiêu chí.

## 7. Làm sao biết input đã nằm trong cache key?

### 7.1. Quan sát buildinfo.xml

Sau khi extension build/lưu record, mở thư mục build cache. Tài liệu Apache khuyến nghị đọc `buildinfo.xml` để kiểm những source files và plugin inputs thực sự được tính.

Linux/macOS:

```bash
find "$HOME/.m2/build-cache" -name buildinfo.xml -type f
```

PowerShell:

```powershell
Get-ChildItem -Path "$HOME/.m2/build-cache" -Filter buildinfo.xml -Recurse -File
```

Nếu cấu hình location tùy biến bằng `maven.build.cache.location`, dùng đường dẫn thực từ logs. Đừng kết luận extension không chạy chỉ vì không có thư mục mặc định.

### 7.2. Những thứ cần xác minh trong record

Đối với project demo:
- `build-input/label.properties`;
- `CacheExample.java`;
- `CacheExampleTest.java`;
- relevant effective POM;
- Maven Resources Plugin settings;
- Compiler release 17, plugins versions;
- dependency graph/JUnit test settings;
- cache key/digest và kết quả build record.

Nếu `build-input/label.properties` đã có nhờ auto discovery, explicit include là **bổ sung bảo đảm cấu hình**, không thể chứng minh nó là yếu tố duy nhất khiến file được theo dõi.

### 7.3. FileHash và EffectivePom

Trong cache config:

```xml
<debugs>
    <debug>FileHash</debug>
    <debug>EffectivePom</debug>
</debugs>
```

Hai option giúp xem:
- File nào đổi digest.
- Effective POM/plugin settings nào khác.
- Vì sao hai machines hoặc profiles không dùng chung record.

Không bật debug quá rộng trong remote cache production khi metadata có thể chứa internal paths, repository URLs hoặc cấu hình nội bộ nhạy cảm. Quản lý retention và quyền đọc.

### 7.4. Diff với baseline remote

Tài liệu mô tả `failFast` và `baselineUrl` để phát hiện mismatch giữa build hiện tại và một baseline report có thật. Ví dụ **không thể chạy nguyên văn** nếu chưa có remote cache URL:

```bash
mvn verify -Dmaven.build.cache.failFast=true -Dmaven.build.cache.baselineUrl=https://cache.example.invalid/project/build-cache-report.xml
```

Khi có baseline phù hợp, extension có thể ghi `buildsdiff.xml` và `buildinfo-*.xml` trong `target/incremental-maven`. Đọc lý do mismatch: file hash, effective POM, plugin property, dependency hay runtime environment. Không xóa một tracked property chỉ vì muốn tăng hit rate.

## 8. Compiler, Surefire và runtime plugin reconciliation

### 8.1. Tại sao file hashes chưa đủ?

Hai lần build cùng source có thể khác vì:
- `maven.compiler.release` đổi từ 17 sang 21;
- annotation processor path hoặc generator version đổi;
- Maven Resources filtering bật/tắt;
- Surefire `skipTests`, includes/excludes, `argLine`, system properties thay;
- Maven Shade/Assembly layout thay;
- source timestamp/locale/encoding thay;
- profiles khác nhau bật plugin execution;
- version normalization làm manifest khác.

Nhiều thông tin nằm trong effective POM, nhưng có runtime properties không thể được đảm bảo chỉ qua file scan. Build Cache Extension có runtime reconciliation để kiểm plugin parameters quan trọng. Xem implementation và báo cáo thực tế thay vì giả định mọi tham số tự phát hiện hoàn hảo.

### 8.2. Functional và non-functional differences

| Khác biệt | Có thể đổi output/test? | Quyết định |
| --- | --- | --- |
| Java compiler release 17 vs 21 | Có | Track hoặc tách cache |
| Resources filtering true/false | Có | Track |
| Codegen version/schema | Có | Track |
| Surefire skipTests true/false | Có, test validation | Reconcile/always-run |
| Test JVM argLine agent/properties | Có thể | Không exclude tùy tiện |
| Log verbosity `-X` | Thường không | Có thể loại khỏi key khi đã kiểm |
| Temporary work directory path | Thường không | Normalize/exclude có điều kiện |
| Number of threads | Có thể tác động race order | Đo/test trước khi bỏ |
| Locale/timezone | Có thể | Pin hoặc đưa vào contract |
| Version embedded in manifest | Có | Track project version hoặc điều chỉnh output |

### 8.3. Plugin effective POM property exclusion

Tài liệu cache extension đưa ra ví dụ loại `argLine` để giảm misses khi giá trị thay nhưng output tương đương:

```xml
<input>
    <plugins>
        <plugin artifactId="maven-surefire-plugin">
            <effectivePom>
                <excludeProperties>
                    <excludeProperty>argLine</excludeProperty>
                </excludeProperties>
            </effectivePom>
        </plugin>
    </plugins>
</input>
```

Đây là **fragment nâng cao, không phải default khuyến nghị**. Nếu `argLine` thay JaCoCo agent, JVM system property hoặc test execution, loại nó có thể gây false HIT. Chỉ áp dụng sau khi biết thay đổi parameter không ảnh hưởng equivalence và tests theo chính sách dự án.

### 8.4. Test execution khi cache HIT

Một cache HIT có thể bỏ qua việc chạy lại một số Maven goals. Trong CI PR yêu cầu mỗi commit được kiểm thử đầy đủ, cần kiểm:
- Có test report mới/chính xác cho run này không?
- Nếu cached test result được cho phép, provenance có chứng minh cùng source/input/environment không?
- `skipTests` và test selectors có được reconcile không?
- Các test cần thật sự chạy mỗi lần (flaky/external integration) có dùng runAlways không?
- Artifact test không được lấy từ trust domain kém tin cậy.

Không nhầm `mvn verify` thành “Surefire chắc chắn chạy lần này” khi extension restore cached results. Nếu policy buộc real execution, điều chỉnh cache executionControl hoặc chạy kiểm thử riêng không cache.

## 9. Build outputs và generated sources

### 9.1. Không phải mọi file đều được restore

Cache record thường lưu Maven artifacts và một phần build state. Nhưng project có thể tạo:
- class files trong `target/classes`;
- generated Java trong `target/generated-sources`;
- files ở `generated/` ngoài target;
- test reports, coverage data;
- archive/custom plugin outputs;
- side effects như database migration hoặc network upload.

Không được mặc định mọi path đều được restore như lúc chạy normal Maven lifecycle. Tài liệu IDE support cảnh báo partial restoration. Bài lab chủ động chạy class từ **JAR artifact** đã build/restore, thay vì giả định `target/classes` luôn có đủ.

### 9.2. Attached outputs

Nếu project cần restore thêm generated source directories, cấu hình `attachedOutputs` trong `configuration` của cache config:

```xml
<configuration>
    <attachedOutputs>
        <preservePermissions>true</preservePermissions>
        <dirNames>
            <dirName>generated-sources/apt</dirName>
        </dirNames>
    </attachedOutputs>
</configuration>
```

Đây là **fragment**, không phải root file đầy đủ. `dirName` thường tính tương đối từ Maven build output directory (`target`). Cần kiểm đường dẫn thật và permissions. Đừng coi `target/generated-sources` là source input hash thay cho schema/template gốc; output được tạo *sau* codegen và bản chất không phải đầu vào độc lập.

### 9.3. Side-effect goals không thể “restore thay vì chạy”

Ví dụ:
- `maven-deploy-plugin:deploy`;
- `maven-install-plugin:install` khi muốn cập nhật local repo;
- ký artifact;
- upload container/image;
- migration database;
- live integration checks;
- compliance reports bắt buộc chạy mỗi lần.

Maven cache config có `executionControl/runAlways` cho plugins/goals cần thực thi ngay cả khi có cache HIT. Fragment:

```xml
<executionControl>
    <runAlways>
        <plugins>
            <plugin groupId="org.apache.maven.plugins"
                    artifactId="maven-deploy-plugin"/>
        </plugins>
    </runAlways>
</executionControl>
```

**RunAlways không cấp quyền publish và không thay security approval.** Với production/release mà correctness và audit quan trọng hơn tốc độ, cách dễ đảm bảo hơn thường là disable cache, clean build, verify outputs rồi deploy.

## 10. Các tham số điều khiển cache thường dùng

| Tham số | Tác dụng chính | Điểm dễ nhầm |
| --- | --- | --- |
| `maven.build.cache.enabled=false` | Tắt build cache | Dùng làm no-cache baseline |
| `maven.build.cache.skipCache=true` | Bỏ tìm/restore cache | **Vẫn có thể ghi** cache mới |
| `maven.build.cache.skipSave=true` | Không save cache mới | **Vẫn có thể đọc** cache cũ |
| `maven.build.cache.remote.enabled=false` | Không đọc remote cache | Local cache vẫn hoạt động |
| `maven.build.cache.remote.save.enabled=true` | Cho phép ghi lên remote nếu cấu hình | Chỉ dùng cho trusted writers |
| `maven.build.cache.remote.save.final=true` | Tránh override record remote tương ứng | Không thay server ACL |
| `maven.build.cache.location=...` | Đổi thư mục local build-cache | Khác `maven.repo.local` |
| `maven.build.cache.mandatoryClean=true` | Đòi clean lifecycle theo cache-save policy | Giảm lưu output lẫn build cũ |
| `maven.build.cache.cacheCompile=false` | Không cache compile-only phases | Theo docs hiện hành |
| `maven.build.cache.alwaysRunPlugins=...` | Chỉ định plugin/goal phải chạy | Dùng cho side effects/verification |
| `maven.build.cache.maxLocalBuildsCached=...` | Giới hạn số records per project | Ảnh hưởng disk/hit rate |

### 10.1. Buộc rebuild nhưng vẫn có thể ghi record

```bash
mvn -B -ntp -Dmaven.build.cache.skipCache=true clean verify
```

Đúng semantics: `skipCache=true` không đọc/restore existing cache, **không tự cấm save**. Đừng dùng nó khi bạn muốn loại bỏ hoàn toàn cache side effects.

### 10.2. Chỉ đọc, không ghi cache

```bash
mvn -B -ntp -Dmaven.build.cache.skipSave=true clean verify
```

Thích hợp khi PR job được phép đọc local/remote cache nhưng không được upload kết quả vào shared trust domain của release. Tuy vậy nếu remote server cấp PUT credentials cho runner, flag không phải biện pháp bảo vệ duy nhất: phải cấp quyền đọc ở server, không cấp write.

### 10.3. Bypass cache toàn bộ để so correctness

```bash
mvn -B -ntp -Dmaven.build.cache.enabled=false clean verify
```

Lệnh này yêu cầu normal Maven lifecycle, là baseline để xem kết quả chính xác khi không có cache. Tắt remote bằng `remote.enabled=false` **không tương đương** với disable cache vì local cache vẫn có thể HIT.

## 11. JDK, OS, line endings và environment

### 11.1. JDK/compiler toolchain

Source cùng commit nhưng Maven dùng JDK 17 trên CI A, JDK 21 trên CI B: bytecode, annotation processors, classpath/API behavior hoặc test results có thể khác. Dù POM `maven.compiler.release=17`, mọi khía cạnh JDK vendor/runtime không tự động tương đương.

Cách quản trị:
- Pin Maven Wrapper/JDK trong CI.
- Track compiler release/options và plugin versions.
- Tách remote cache theo toolchain nếu cần.
- So output từ two environments trước khi cho phép reuse.

### 11.2. CRLF/LF

Apache Maven Build Cache Extension hash **raw file bytes**, không tự normalize line endings. Git checkout cùng commit trên Windows có CRLF, Linux có LF sẽ tạo file digests khác, gây false MISS.

Một `.gitattributes` ví dụ:

```gitattributes
*.java text eol=lf
*.xml text eol=lf
*.properties text eol=lf
```

Áp dụng vào repo hiện có cần review vì có thể làm Git diff nhiều file. Không tự chỉnh toàn bộ source chỉ để cải thiện cache trong một commit không có kế hoạch.

### 11.3. Environment/clock/randomness

Nếu một plugin nhúng `BUILD_NUMBER`, git SHA, timezone, locale hoặc timestamp vào output mà giá trị đó không được fingerprint hoặc reconcile, hai builds có cùng file inputs vẫn có thể cho outputs khác.

Cần:
- Đưa property chức năng vào POM/plugin configuration được theo dõi.
- Chọn reproducible `project.build.outputTimestamp` nếu thích hợp.
- Pin locale/JDK/OS theo policy.
- Tách một bước integration test phụ thuộc external API khỏi cached package.
- Không cache task inherently non-hermetic nếu không thể quản lý external inputs.

### 11.4. Project version normalization

Build Cache Extension hỗ trợ reuse giữa các project versions; model có `projectVersioning`:

```xml
<projectVersioning adjustMetaInf="true"
                   calculateProjectVersionChecksum="true"/>
```

Đây là **fragment trong configuration**. `calculateProjectVersionChecksum=true` làm project version tham gia key, giảm reuse nhưng an toàn hơn khi output chứa version. `adjustMetaInf` có thể xử lý manifest metadata trong một số trường hợp, không bảo đảm mọi generated file có version đều được sửa đúng. Với release production, không mặc định version-agnostic cache luôn an toàn.

## 12. Remote cache: hiệu năng và quyền truy cập

### 12.1. Bật remote chỉ sau khi local correct

Local HIT/MISS và changed-input negative tests phải đạt trước. Remote cache giúp chia output qua CI agents, nhưng còn có:
- Permission/authentication;
- Network/HTTP PUT/GET/HEAD;
- Cache storage/retention;
- Cross-platform portability;
- Untrusted write/cache poisoning.

### 12.2. Remote config fragment

```xml
<remote enabled="true" saveToRemote="false"
        id="team-cache" transport="resolver">
    <url>https://cache.example.invalid/build-cache</url>
</remote>
```

Đây **không phải URL thật**; fragment nằm trong `<configuration>` khi có remote cache server tương thích. `saveToRemote=false` phù hợp khi chỉ muốn read. Apache docs mô tả các backend như Nexus raw repository, Artifactory generic hoặc HTTP server hỗ trợ các thao tác cần thiết.

Maven settings server authentication (fragment):

```xml
<servers>
    <server>
        <id>team-cache</id>
        <username>${env.CACHE_USER}</username>
        <password>${env.CACHE_TOKEN}</password>
    </server>
</servers>
```

Dấu `${env.CACHE_TOKEN}` sẽ được thay bằng Maven environment property syntax trong bài sau xử lý. Trong CI thật, secret phải được tiêm vào job có quyền, không commit vào POM/settings public.

### 12.3. Quyền ghi cache là một trust boundary

PR từ fork có thể chạy Maven plugins/code do contributor chưa được duyệt kiểm soát. Nếu runner có quyền PUT lên cache dùng bởi pipeline release, actor có thể cố tình đưa records/artifacts không đáng tin vào shared store.

Chính sách đề xuất:
- PR pipeline: runner ít quyền, không có remote cache write credentials; có thể đọc cache chỉ khi policy chấp nhận.
- Trusted CI trên protected branch: quyền ghi riêng, có audit.
- Release: cân nhắc no-cache build hoặc verify provenance/identities của restored artifacts.
- Storage: access control, TLS, monitoring, immutable record policy khi cần.

Các cờ `skipSave` và `remote.save.final` hữu ích nhưng **không thay thế server-side ACL**. `hashAlgorithm=SHA-256` cũng không xác thực người đã tạo cache record.

## 13. Multi-module và subtrees

Một Maven reactor:

```text
parent/
├── api/
├── service/      depends on api
├── cli/          depends on api
└── docs/
```

Nếu `api` đổi, `service` và `cli` có thể bị ảnh hưởng thông qua dependency graph; `docs` có thể reuse output nếu thực sự độc lập. Build Cache Extension có incremental/subtree support nhưng không tự sửa một graph khai sai.

Với source nằm ngoài module basedir:
- Kiểm relative `include` đang trỏ đúng folder khi chạy từ module nào.
- Nếu shared schema có thể được đóng gói thành Maven module/artifact versioned, phương án ấy thường minh bạch hơn references `../..`.
- Kiểm active profiles và full reactor discovery. Schema có `multiModule/discovery/scanProfiles` khi cần tìm modules trong profile riêng.

Fragment ví dụ:

```xml
<configuration>
    <multiModule>
        <discovery>
            <scanProfiles>
                <scanProfile>full-reactor</scanProfile>
            </scanProfiles>
        </discovery>
    </multiModule>
</configuration>
```

Không copy vào project mẫu một module vì không có profile `full-reactor`. Chỉ dùng khi project thật có profile này.

## 14. Benchmark tốc độ công bằng

So sánh:
1. **Warm Maven dependencies, cache disabled:** thời gian Maven build lifecycle bình thường.
2. **Warm dependencies, cache enabled cùng inputs:** thời gian khi cache HIT thực sự.
3. **Warm dependencies, một input thay đổi:** thời gian MISS/rebuild hợp lệ.

Tránh lấy lần Maven tải JUnit/plugins đầu tiên làm baseline duy nhất, vì download cache cải thiện lần hai dù Build Cache Extension chưa hoạt động. Đo nhiều runs, lấy median, ghi CI runner CPU/RAM/disk, JDK/Maven versions, file count, remote latency.

Chỉ số cần theo dõi:
- HIT rate theo module và type.
- False HIT incidents (mục tiêu bằng 0).
- Miss reason (source hash, effective POM, plugin parameter).
- Build wall time/CPU/CI minutes.
- Remote cache network traffic và retention size.
- Output equivalence và test execution coverage.

Nếu cache HIT quá ít, dùng `buildinfo.xml`/`buildsdiff.xml` để tìm false MISS. Không cắt bớt input chức năng một cách cảm tính.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| Maven không load extension | Maven cũ, extension coordinates sai | Kiểm Maven 3.9+, extensions.xml, version |
| Không có cache logs | File đặt sai `.mvn`, extension disabled | Kiểm root và enabled |
| Không có `buildinfo.xml` | Cache location khác hoặc chưa save | Xem log/location |
| Lần hai luôn MISS | Temp file/POM/profile/env đổi | FileHash/EffectivePom/diff |
| Sửa resource nhưng vẫn in alpha | File không fingerprint hoặc JAR cũ | buildinfo, glob, include, artifact path |
| Sửa Proto không invalidate | `*.proto` thiếu trong glob/dirScan | Bổ sung path + extension |
| Include không hiệu lực | Path tương đối sai module basedir | Xem resolved paths |
| HIT nhưng target/classes thiếu | Partial restore | Kiểm output/attachedOutputs/IDE |
| Cache HIT từ build skipTests | Reconciliation không đủ | Theo dõi skip flags/always-run |
| Cache HIT nhưng JDK đổi | Toolchain không phân biệt | Pin JDK hoặc tách namespace |
| Windows không HIT Linux cache | CRLF/LF/path differences | .gitattributes, config tương thích |
| Cache miss vì scratch log | Input thừa | Exclude khi chứng minh vô hại |
| `skipCache=true` vẫn save | Flag chỉ bỏ đọc | Dùng thêm skipSave nếu cần |
| `skipSave=true` vẫn HIT | Flag chỉ bỏ ghi | enabled=false nếu cần không cache |
| Disable remote vẫn HIT | Local cache hoạt động | enabled=false |
| Remote 401/403 | Credentials/server ID/ACL | Kiểm settings, quyền |
| Remote cache dùng dữ liệu PR | Cache poisoning | Tách trust domains, server-side ACL |
| Generated files không restore | Output directory đặc biệt | attachedOutputs hoặc always-run generator |
| Deploy goal bị skip | Side-effect execution bị cache | runAlways hoặc no-cache release |
| Build nhanh nhưng JAR sai | False HIT | So no-cache baseline, điều tra input |
| Không tăng tốc | Hash/IO overhead lớn | Benchmark, cải thiện false MISS có kiểm chứng |

### 15.1. Runbook khi nghi false HIT

1. Dừng dùng cached artifact cho release.
2. Ghi Maven/JDK/extension/plugin versions và commit SHA.
3. Xác định expected output từ input thật, ví dụ `cache-label=beta`.
4. Chạy `mvn -Dmaven.build.cache.enabled=false clean verify`.
5. So output uncached với cached theo tiêu chí được phê duyệt.
6. Kiểm `buildinfo.xml`: file/resource/schema có tham gia hash không?
7. Kiểm global glob, includes, excludes và plugin dirScan.
8. Kiểm effective POM và reconciliation của compiler/resources/surefire.
9. Kiểm env/OS/JDK/line endings/external inputs.
10. Chạy lại changed-input negative test và same-input HIT test.
11. Với remote cache, kiểm permissions và records đã publish; xử lý records lỗi theo policy.
12. Chỉ bật lại sau khi correctness được tái xác nhận.

## 16. Câu hỏi tự kiểm tra

**1.** Build cache có giống `~/.m2/repository` không? **Không.** Một bên lưu dependencies, một bên lưu kết quả build.

**2.** False MISS là gì? **Input vô hại khiến key đổi**, build chậm hơn nhưng không nhất thiết sai.

**3.** False HIT là gì? **Input quan trọng đổi nhưng cache vẫn được dùng**, có thể trả artifact stale.

**4.** Extension khai ở đâu? `.mvn/extensions.xml` hoặc supported Maven build extension location, không phải application dependency.

**5.** Build Cache Extension 1.3.0 yêu cầu Maven tối thiểu nào? Maven **3.9.0**.

**6.** Config mặc định ở đâu? `.mvn/maven-build-cache-config.xml`.

**7.** Chỉ viết `<include>schemas</include>` mà global glob loại `*.proto` có đủ không? Không, phải kiểm cả file type glob.

**8.** Vì sao không khẳng định bỏ include `build-input` chắc chắn gây false HIT? Vì extension có thể auto detect POM resource directory.

**9.** Khi label đổi alpha → beta, stdout đúng là gì? `cache-label=beta`.

**10.** Vì sao tests chấp nhận cả alpha và beta? Vì cả hai giá trị là input hợp lệ của negative test; ta kiểm change detection qua output.

**11.** `-Dmaven.build.cache.skipCache=true` có ngăn save không? Không; nó bỏ cache lookup, vẫn có thể save.

**12.** `-Dmaven.build.cache.skipSave=true` có ngăn cache restore không? Không; nó chỉ bỏ save.

**13.** Tắt remote có đồng nghĩa tắt local không? Không; dùng `enabled=false` để bypass toàn bộ.

**14.** Vì sao SHA-256 không chứng minh remote cache record đáng tin? Vì hash không xác minh danh tính actor ghi cache.

**15.** Vì sao compiler `release` là input chức năng? Nó có thể đổi bytecode/API compatibility.

**16.** Vì sao CRLF/LF khác nhau gây MISS? Hash dựa raw bytes, không auto normalize.

**17.** Chỉ có `BUILD SUCCESS` có chứng minh cache HIT? Không; xem log/metadata.

**18.** Build không cache dùng để làm gì? Đưa ra baseline output độc lập với restored cache record.

**19.** Codegen sinh generated Java trong `target` nên hash output đó làm input là đủ? Không; cần hash source schema/template/generator config.

**20.** PR code chưa review có nên ghi shared release cache? Không theo policy least privilege; tách quyền đọc/ghi ở server.

**21.** Có thể luôn exclude Surefire `argLine` để tăng hit rate không? Không nếu nó ảnh hưởng JVM/tests.

**22.** Khi project version đổi, cache luôn tái sử dụng an toàn? Không; kiểm version embedded metadata và projectVersioning policy.

## 17. Checklist trước khi triển khai cho nhóm

- [ ] Maven version hỗ trợ extension và được pin trong CI.
- [ ] Extension 1.3.0 đặt trong `.mvn/extensions.xml`.
- [ ] Cache config có đúng namespace/schema và được commit.
- [ ] File types và source/resource roots đầy đủ.
- [ ] Global glob không bỏ Proto/YAML/JSON/templates đang được dùng.
- [ ] Explicit includes đúng module basedir khi cần.
- [ ] Excludes chỉ áp dụng cho file đã chứng minh vô hại.
- [ ] `buildinfo.xml` có toàn bộ các input quan trọng.
- [ ] Plugin parameters ảnh hưởng output được reconcile.
- [ ] Surefire skip/test selectors và test policy rõ ràng.
- [ ] JDK/OS/locale/line endings/env được pin hoặc quản lý.
- [ ] Generated sources và attached outputs được restore phù hợp.
- [ ] Side-effect goals không bị cache skip sai.
- [ ] Same-input HIT được kiểm bằng logs/metadata.
- [ ] Changed-input MISS tạo output đúng.
- [ ] Cached build đã được so với clean uncached build.
- [ ] Remote cache chỉ dùng sau khi local correctness được chứng minh.
- [ ] PR/untrusted jobs không có quyền ghi cache của trusted release.
- [ ] Remote cache có TLS/ACL/provenance/retention policy.
- [ ] Release build có cơ chế bypass cache khi cần audit.
- [ ] Có thống kê wall time, HIT/MISS và phát hiện false HIT.
- [ ] Định kỳ kiểm lại khi đổi plugins, JDK, Maven, CI image hoặc source layout.

## 18. Kết luận

**Maven Build Cache Extension là công cụ tối ưu khi và chỉ khi mô hình đầu vào đủ đúng.** Nó dùng fingerprint từ sources, dependencies và build configuration để tránh lặp công việc, nhưng không thể đoán đúng mọi custom generator, environment variable hoặc external state. Một false MISS làm chậm, còn **false HIT có thể làm sai artifact mà vẫn BUILD SUCCESS**.

Cách thực hành chuẩn là ghim extension, đọc `buildinfo.xml`, xác nhận file types/paths và plugin parameters, thay từng input quan trọng để kiểm invalidate, rồi so cached output với clean uncached build. Với ví dụ `build-input/label.properties`, đổi `alpha` thành `beta` bắt buộc tạo artifact in **cache-label=beta**. Tốc độ chỉ có ý nghĩa khi kết quả đó vẫn đúng.

### Tài liệu chính thức của Apache Maven

- [Apache Maven — Available Extensions](https://maven.apache.org/extensions/index.html)
- [Maven Build Cache Extension — Getting Started](https://maven.apache.org/extensions/maven-build-cache-extension/)
- [Maven Build Cache Extension — Concepts](https://maven.apache.org/extensions/maven-build-cache-extension/concepts.html)
- [Maven Build Cache Extension — Usage](https://maven.apache.org/extensions/maven-build-cache-extension/usage.html)
- [Maven Build Cache Extension — How-To](https://maven.apache.org/extensions/maven-build-cache-extension/how-to.html)
- [Maven Build Cache Extension — Parameters](https://maven.apache.org/extensions/maven-build-cache-extension/parameters.html)
- [Maven Build Cache Extension — BuildCacheConfig schema](https://maven.apache.org/extensions/maven-build-cache-extension/build-cache-config.html)
- [Maven Build Cache Extension — Remote Cache Setup](https://maven.apache.org/extensions/maven-build-cache-extension/remote-cache.html)
- [Maven Build Cache Extension — Cache diff schema](https://maven.apache.org/extensions/maven-build-cache-extension/build-cache-diff.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
