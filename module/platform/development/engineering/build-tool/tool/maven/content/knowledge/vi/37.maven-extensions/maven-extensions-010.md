# Đăng ký extension qua cấu hình phù hợp và quản lý phiên bản trong Maven

**Maven extension là mã được nạp vào hệ thống build để mở rộng Maven, không phải thư viện Java của ứng dụng và cũng không phải một plugin goal thông thường.** Extension có thể bổ sung Maven components, cải tiến lifecycle, cung cấp transport/packaging support hoặc can thiệp vào build cache. Một cấu hình sai hoặc version không tương thích có thể khiến Maven lỗi từ lúc khởi động — trước khi đọc POM đầy đủ hay chạy unit tests.

Bài thuộc nhóm **Mở rộng Maven**, tập trung hai quyết định thực hành: **đăng ký extension ở vị trí phù hợp** và **quản trị version/compatibility/rollback**. Phần lab dùng **Maven 3.9.x, Java 17, Apache Maven Build Cache Extension 1.3.0**, một extension được Apache phát hành. Từ ví dụ chạy được với POM, Java source, JUnit tests và kết quả stdout xác định, chúng ta sẽ hiểu core extension trong `.mvn/extensions.xml`, build extension trong `pom.xml`, plugin-provided extension với `<extensions>true</extensions>`; đồng thời kiểm Maven/JDK version, repository, classloader, security, CI, multi-module và lỗi thường gặp.

**Nguyên tắc:** chỉ khai extension khi cần; làm theo tài liệu publisher về **core** hay **build**; ghim tọa độ `groupId:artifactId:version` rõ ràng; không gắn `<extensions>true</extensions>` vào mọi plugin; không xem Maven cache hit là bằng chứng tests vừa chạy; và luôn có đường rollback đơn giản.

## 1. Phân biệt extension, plugin và project dependency

| Thành phần | Nơi khai báo | Vai trò |
| --- | --- | --- |
| Java dependency | `pom.xml / dependencies` | Java compile/runtime/test classpath theo scope |
| Maven plugin | `pom.xml / build/plugins` | Chạy goals/Mojos ở lifecycle hoặc CLI |
| Plugin management | `build/pluginManagement` | Quản lý versions/config mặc định cho plugins được sử dụng |
| **Core extension** | `.mvn/extensions.xml` | Nạp sớm vào Maven Core extension realm |
| **Build extension** | `pom.xml / build/extensions` | Nạp muộn hơn theo project model |
| **Plugin-provided extension** | `pom.xml / build/plugins/plugin/extensions=true` | Kích hoạt extension components do plugin cung cấp |
| Maven Wrapper | `mvnw`, `mvnw.cmd`, `.mvn/wrapper` | Cố định Maven distribution, **không tự cài extension** |
| Maven settings | `settings.xml` | Mirrors, repositories, proxy, credentials, profiles |

Các goals thông dụng như `compiler:compile`, `surefire:test` và `jar:jar` là plugin operations. Bạn không cần extension để biên dịch Java, chạy JUnit, đóng JAR hay thêm dependencies. Cần extension khi thay đổi **Maven runtime hoặc build lifecycle machinery** theo một cơ chế được publisher hỗ trợ.

Một Java library dependency:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.0</version>
    <scope>test</scope>
</dependency>
```

làm test source có JUnit API/Engine. Nó **không** biến JUnit thành Maven core extension. Ngược lại, đưa `maven-build-cache-extension` vào `<dependencies>` không phải cách bật build cache; dễ làm nhiễu project classpath.

### 1.1. Vì sao extension cần quản lý chặt hơn dependency thường?

Extension có thể nạp vào Maven process **ngay khi startup** và thực thi code với quyền của tài khoản đang build. Nó có thể tương tác với repository credentials, filesystem, plugin configuration và build artifacts. Một lỗi không tương thích Maven Core API có thể làm cả `mvn validate` hoặc `mvn help:effective-pom` không khởi chạy được.

Không sử dụng extension JAR từ nguồn không đáng tin, không tải binary thủ công vào installation global, không để CI dùng một version khác developer mà không khai báo, và không bỏ qua CVE/changelog của các dependency mà extension mang theo.

## 2. Core extension và build extension khác nhau về thời điểm nạp

Apache Maven phân biệt **Core Extensions** và **Build Extensions**:

```text
Maven launcher / startup
         |
         v
Detect .mvn/extensions.xml
         |
         v
Resolve + load core extensions
         |
         v
Read/build project models: POM, parent, modules, profiles
         |
         +--> load build/plugin extensions as appropriate
         |
         v
Construct execution plan and run lifecycle goals
```

Đây là sơ đồ **khái niệm**; thứ tự chi tiết giữa settings, model builder và components phụ thuộc Maven implementation. Khác biệt cốt lõi được Apache xác nhận: **core extension load early; build extension load late**.

| Câu hỏi | Core extension | Build extension |
| --- | --- | --- |
| Khi nạp? | Startup, trước POM processing hoàn chỉnh | Khi dựng project model |
| Khai ở đâu? | `.mvn/extensions.xml` | `<build><extensions>` hoặc plugin `extensions=true` |
| Classloading | Core extension classloader/realm | Project/plugin extension realms |
| Có thể ảnh hưởng bootstrap? | Có thể, tùy extension | Không thay core hook cần nạp sớm |
| Pin version? | `<extension><version>` trong descriptor | Extension/plugin version trong POM |
| Hợp use case? | Early Maven hooks/cache | Project-specific packaging/transport/extension components |

**Không tùy tiện chuyển qua lại:** publisher có thể chỉ hỗ trợ một kiểu, hoặc hai kiểu nhưng ưu tiên một kiểu. Với **Apache Maven Build Cache Extension 1.3.0**, tài liệu cho phép khai trong cả `.mvn/extensions.xml` và `pom.xml / build/extensions`, đồng thời **khuyến nghị core descriptor** cho khả năng truy cập Maven APIs.

## 3. Cách khai core extension đúng trong .mvn/extensions.xml

Cấu trúc project:

```text
my-project/
├── .mvn/
│   └── extensions.xml
├── pom.xml
└── src/
```

File `.mvn/extensions.xml` có dạng Maven Core Extensions Descriptor. Với extension thật:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<extensions xmlns="http://maven.apache.org/EXTENSIONS/1.1.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://maven.apache.org/EXTENSIONS/1.1.0 https://maven.apache.org/xsd/core-extensions-1.1.0.xsd">
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
```

Đây là **cấu hình runnable**, không phải placeholder. Artifact được Apache Maven công bố dưới tọa độ `org.apache.maven.extensions:maven-build-cache-extension:1.3.0` và yêu cầu **Maven 3.9.0+**. Java 17 trong lab là yêu cầu của **project source/Compiler Plugin**; cũng phải kiểm runtime requirement của extension từ tài liệu khi áp vào môi trường khác.

### 3.1. Cơ chế resolve và load

Khi gọi:

```bash
mvn -B clean verify
```

Maven tìm project-root `.mvn/extensions.xml`, đọc GAV đã pin, resolve JAR và transitive dependencies bằng Maven Resolver/repository settings rồi load extension. Nếu tọa độ không tồn tại, repository bị 401/403, proxy/truststore lỗi hoặc extension không tương thích Maven Core, invocation có thể **fail rất sớm** trước cả phase `validate`.

Dạng mô hình:

```text
mvn command
  → Maven bootstrap
  → project .mvn/extensions.xml
  → extension artifact G:A:V (+ dependencies)
  → extension classloader/components
  → project POM and lifecycle
  → compiler / surefire / jar goals
```

**Không** copy JAR vào `src/main/resources` rồi mong Maven tự load; folder đó dành cho Java resources. Không khai extension như project dependency, vì classpath của Java code và classloader của Maven Core không giống nhau.

### 3.2. Không dùng POM property cho core extension version

Một cách khai **không nên dùng** trong core descriptor:

```xml
<version>${build.cache.version}</version>
```

Core extension nạp trước khi có effective POM nên không thể mặc nhiên đọc `<properties><build.cache.version>...` của project. Cũng đừng kỳ vọng `dependencyManagement` hoặc `pluginManagement` quản lý core extension version. Hãy pin **literal release version**, nâng bằng PR hoặc cơ chế riêng được Apache/publisher xác nhận.

### 3.3. Root .mvn và multi-module

Ví dụ:

```text
workspace/
├── .mvn/extensions.xml
├── pom.xml                 # packaging pom, reactor root
├── core/pom.xml
├── service/pom.xml
└── cli/pom.xml
```

Đặt descriptor tại **Maven project root**. Một invocation từ root với `-pl :service -am` vẫn đọc cùng descriptor theo session. Không nhân bản cấu hình vào mọi child hoặc đặt file trong `target`. Khi chạy Maven trực tiếp từ child hoặc IDE embedder, xác định project base directory/root đã được Maven phát hiện; khác working directory có thể đổi cơ chế phát hiện `.mvn`.

## 4. Build extension trong pom.xml/build/extensions

Nếu publisher hỗ trợ build extension, có thể khai:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    ...
    <build>
        <extensions>
            <extension>
                <groupId>org.apache.maven.extensions</groupId>
                <artifactId>maven-build-cache-extension</artifactId>
                <version>1.3.0</version>
            </extension>
        </extensions>
    </build>
</project>
```

**Đây là fragment mô tả vị trí trong POM, không phải POM runnable độc lập** (có dấu `...`). Apache Build Cache Extension docs xác nhận phiên bản 1.3.0 hỗ trợ cách khai này, nhưng khuyến nghị `.mvn/extensions.xml`. **Không dán đoạn này vào POM lab đồng thời giữ core descriptor** — chọn một supported registration theo publisher docs.

Khác biệt: POM project model phải được đọc đủ để biết build extension. Vì vậy cách này **không** thể đáp ứng mọi extension cần can thiệp trước lúc đọc POM. Với parent/inheritance, kiểm module nào thật sự dùng extension và Maven version đang chạy; đừng coi tất cả extension khai ở aggregator tự truyền tới mọi context ngoài reactor.

### 4.1. Những tình huống build extension phù hợp

- Project cần một Wagon/transport provider hoặc component chỉ dùng lúc build.
- Dự án cần packaging/lifecycle support có extension được nhà phát hành mô tả.
- Extension không cần khởi tạo trước POM processing.
- Configuration có thể quản lý trong parent POM theo dependency/plugin policy, sau khi xem inheritance thực tế.

**Không nhầm** `build/extensions` với `dependencies`. Nó không phải cách đưa thư viện Java vào `src/main/java`. Cũng không coi một extension trong POM là cơ chế thay thế hoàn toàn cho core extension khi publisher yêu cầu early loading.

## 5. Plugin-provided extension: <extensions>true</extensions>

Một Maven plugin có thể cung cấp extension component. Apache Maven dùng **Maven Bundle Plugin** để minh họa kiểu này:

```xml
<plugin>
    <groupId>org.apache.felix</groupId>
    <artifactId>maven-bundle-plugin</artifactId>
    <version>5.1.9</version>
    <extensions>true</extensions>
</plugin>
```

Đây là **plugin fragment** (phải đặt trong `<build><plugins>`), không phải POM OSGi runnable; muốn tạo OSGi bundle cần đúng packaging/configuration theo Maven Bundle Plugin docs. Version 5.1.9 là release có thật, minh họa **pin plugin version**.

`<extensions>true</extensions>` yêu cầu Maven tải extension components của plugin. Nó **không có nghĩa** Maven tự chạy mọi goal của plugin hoặc tự chuyển một project dependency sang plugin classpath. Plugin executions và extension activation là hai chuyện khác nhau.

### 5.1. Khi không nên đặt extensions=true

Không tự thêm cờ vào:

- Maven Compiler Plugin chỉ để dùng `javac`.
- Maven Surefire Plugin chỉ để chạy JUnit.
- Maven JAR Plugin chỉ để tạo JAR.
- Một plugin bất kỳ mà publisher không mô tả extension support.
- `pluginManagement` rồi kỳ vọng plugin đã được kích hoạt. Management chỉ quản lý config/version.

Chỉ thêm khi plugin cung cấp extension thực sự và docs yêu cầu hoặc giải thích lý do. Nếu package type như `bundle` báo `Unknown packaging`, kiểm publisher docs, plugin extension flag, coordinates và phiên bản phù hợp; không sửa bằng cách đặt cờ cho plugin không liên quan.

## 6. Lab Maven 3.9.x/Java 17 đăng ký core extension thật

Bài lab dùng **Apache Maven Build Cache Extension 1.3.0**, có một Java application chỉ dùng JDK và **4 JUnit Jupiter tests**. Không cần database, docker hay server. Muốn tải artifact lần đầu phải có Maven repository internet hoặc mirror nội bộ được cấu hình hợp lệ.

Cây thư mục:

```text
extension-registration-lab/
├── .mvn/
│   └── extensions.xml
├── pom.xml
└── src/
    ├── main/java/vn/example/extensions/
    │   ├── PriceMath.java
    │   └── Main.java
    └── test/java/vn/example/extensions/
        └── PriceMathTest.java
```

**Chỉ dùng đúng một cách đăng ký: `.mvn/extensions.xml` như mục 3.** Không thêm cùng extension vào POM `build/extensions` hay `build/plugins`.

### 6.1. POM đầy đủ

File `extension-registration-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>extension-registration-lab</artifactId>
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
            <version>5.11.0</version>
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
                <configuration>
                    <release>${maven.compiler.release}</release>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Maven Compiler Plugin dùng `--release 17`. JUnit Jupiter nằm trong test scope, không đưa vào main JAR. Các plugin versions được pin riêng trong POM; core extension version được pin ở descriptor. Đó là **hai nhóm build dependencies khác nhau**.

### 6.2. PriceMath.java

File `src/main/java/vn/example/extensions/PriceMath.java`:

```java
package vn.example.extensions;

/**
 * Pure integer arithmetic for deterministic tests.
 */
public final class PriceMath {
    private PriceMath() {
    }

    /**
     * @param gross nonnegative amount
     * @param percent integer discount percentage, 0 to 100
     * @return the amount after discount, rounded down
     */
    public static int net(int gross, int percent) {
        if (gross < 0 || percent < 0 || percent > 100) {
            throw new IllegalArgumentException("invalid inputs");
        }
        return (int) ((long) gross * (100 - percent) / 100);
    }
}
```

Nhân bằng `long` tránh tràn `int`; kết quả luôn nằm trong `[0,gross]` với inputs hợp lệ. Class không chứa system time/random/user-specific path.

### 6.3. Main.java

File `src/main/java/vn/example/extensions/Main.java`:

```java
package vn.example.extensions;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("gross=250");
        System.out.println("net=" + PriceMath.net(250, 20));
        System.out.println("status=PASS");
    }
}
```

Chạy sau `mvn package` hoặc `mvn verify`:

```bash
java -cp target/extension-registration-lab-1.0.0.jar vn.example.extensions.Main
```

**Stdout chính xác từ Java main:**

```text
gross=250
net=200
status=PASS
```

Đây là plain JAR; POM không khai `Main-Class` manifest, nên dùng `java -cp ... fully.qualified.Main`, không tự giả định `java -jar` chạy được.

### 6.4. PriceMathTest.java

File `src/test/java/vn/example/extensions/PriceMathTest.java`:

```java
package vn.example.extensions;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceMathTest {

    @Test
    void appliesTwentyPercentDiscount() {
        assertEquals(200, PriceMath.net(250, 20));
    }

    @Test
    void roundsDown() {
        assertEquals(133, PriceMath.net(199, 33));
    }

    @Test
    void fullDiscount() {
        assertEquals(0, PriceMath.net(100, 100));
    }

    @Test
    void rejectsBadPercent() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceMath.net(100, 101)
        );
    }
}
```

Có **4 test methods** thực sự. Surefire 3.5.2 nhận `PriceMathTest` theo pattern `*Test`. Một cache hit hợp lệ có thể reuse build/test output chứ không nhất thiết chạy lại tests trong chính invocation đang xét, vì thế phần kiểm CI bên dưới tách **cache enabled** khỏi **baseline testing**.

## 7. Chạy build và xác nhận extension được nạp

Bắt đầu:

```bash
java -version
mvn --version
```

Yêu cầu Maven 3.9.x, JDK 17+. Bảo đảm repo có `.mvn/extensions.xml` đúng nơi và Maven có thể resolve artifact. Thử lần lượt:

```bash
mvn -B -Dmaven.build.cache.enabled=false clean verify
mvn -B clean verify
mvn -B clean verify
```

Diễn giải:

1. **Lần 1:** core extension vẫn được load, nhưng chức năng cache được tắt bằng property của **Build Cache Extension**. Đây là baseline correctness/test execution, **không phải Maven không có extension**.
2. **Lần 2:** bật cache behavior mặc định, có thể lưu hoặc đọc cache theo cấu hình/inputs.
3. **Lần 3:** source không đổi thì có thể reuse kết quả, nhưng cache hit **không được bảo đảm**; plugin reconciliation, cache config, profiles và inputs có thể buộc rebuild.

Dấu hiệu nên kiểm trong log Maven: extension activation/cache initialization hoặc lý do skip cache; test count của lần cache-disabled; Main JAR; cache records (nếu extension lưu thành công) và `buildinfo.xml`. **Không bịa một dòng “CACHE HIT” cố định** vì wording/log detail thay đổi theo extension version.

### 7.1. Kiểm JAR và Java stdout

```bash
jar tf target/extension-registration-lab-1.0.0.jar
java -cp target/extension-registration-lab-1.0.0.jar vn.example.extensions.Main
```

Archive nên chứa:

```text
vn/example/extensions/PriceMath.class
vn/example/extensions/Main.class
```

Lần `clean verify` không cache, Surefire dự kiến ghi:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đó là tóm tắt mong đợi, không phải toàn bộ log. Có thể đọc `target/surefire-reports/TEST-vn.example.extensions.PriceMathTest.xml` để kiểm counts của build có tests thực thi.

### 7.2. Maven local repository khác build cache

Theo Apache Build Cache docs, mặc định local build cache là thư mục `build-cache` nằm **cạnh** local repository:

```text
~/.m2/
├── repository/      # Maven resolved artifacts/plugins/POMs
└── build-cache/     # Maven build cache records/outputs (default)
```

Đường dẫn có thể thay đổi qua custom local repository, settings hoặc cache location property. `repository` giữ dependencies/installed artifacts; `build-cache` giữ kết quả build reusable. Một file trong repository **không tự là cache hit**; một cache record cũng **không tự đồng nghĩa** đã install artifact cho project consumer.

### 7.3. Những flags của Build Cache Extension

| Property | Ý nghĩa | Không nên hiểu thành |
| --- | --- | --- |
| `-Dmaven.build.cache.enabled=false` | Tắt cache features nhưng extension vẫn được nạp | “Không load extension” |
| `-Dmaven.build.cache.skipCache=true` | Skip cache read/lookup | Tắt mọi cache write |
| `-Dmaven.build.cache.skipSave=true` | Không lưu cache mới | Tắt cache read |
| `-Dmaven.build.cache.remote.enabled=false` | Tắt remote cache access | Xóa local cache |
| `-Dmaven.build.cache.location=...` | Chọn local cache directory | Chọn Maven local repository |
| `-Dmaven.build.cache.cacheCompile=false` | Không cache compile-only builds | Không cache package/verify |
| `-Dmaven.build.cache.restoreOnDiskArtifacts=false` | Điều khiển việc restore on-disk outputs | Bảo đảm target files luôn đủ |

Các flags này thuộc **Build Cache Extension**, không phải option chung để quản lý mọi Maven extension.

### 7.4. Tắt extension thật sự để so sánh

Nếu extension fail ngay lúc startup, `-Dmaven.build.cache.enabled=false` vẫn cần load classes nên có thể tiếp tục lỗi. Để kiểm không có extension, tạo một **Git worktree/bản sao** không chứa `.mvn/extensions.xml` (hoặc revert commit khai extension trên nhánh thử nghiệm), rồi chạy Maven invocation mới. Không xóa thư mục Maven global hay sửa project chính không kiểm soát.

## 8. .mvn/maven-build-cache-config.xml: cấu hình behavior, không phải registration

File `.mvn/extensions.xml` là **registration**. Còn `.mvn/maven-build-cache-config.xml`, nếu thêm, là **config tùy chọn** cho Build Cache Extension: chọn inputs/exclusions, plugin parameter reconciliation, remote cache và behavior nâng cao.

```text
.mvn/
├── extensions.xml
└── maven-build-cache-config.xml    # optional, theo schema của extension
```

Không tự bịa XML config khi chưa đọc schema/version. Apache cung cấp **sample config chính thức** có hướng dẫn. Tổ chức cần audit:

- Source/resource/generator inputs thực sự tạo ra artifact.
- Environment/Java version/compiler options có ảnh hưởng output.
- Plugin parameters mà cache reconciliation cần quan sát.
- Những files tạm nên exclude, nhưng **không exclude input có ảnh hưởng build**.
- Remote cache credentials/trust/ACL nếu bật.
- Output restoration cần thiết cho IDE, packaged JAR, attached artifacts.
- Cache size/eviction policy và tính nhất quán khi đổi version.

Một cache hit nhanh nhưng trả artifact cũ vì quên tracking `api-schema.yaml` hoặc generated resource là **bug correctness**, không phải tối ưu.

## 9. Quản lý version extension như build-runtime dependency

Extension version phải được review ngang mức Maven distribution, JDK toolchain và release plugins. Với core descriptor, pin:

```xml
<extension>
    <groupId>org.apache.maven.extensions</groupId>
    <artifactId>maven-build-cache-extension</artifactId>
    <version>1.3.0</version>
</extension>
```

**Tránh** version `LATEST`, `RELEASE`, ranges hoặc `-SNAPSHOT` nếu policy không cho phép. Những cách chọn động gây drift, khó tái lập hoặc thậm chí không được core descriptor hỗ trợ đầy đủ như project dependencies.

### 9.1. Chỗ nào quản lý version?

| Thành phần | Nơi pin |
| --- | --- |
| Core extension | `.mvn/extensions.xml` trực tiếp |
| POM build extension | `build/extensions/extension/version` |
| Plugin-provided extension | `build/plugins/plugin/version`, `extensions=true` |
| Maven distribution | Maven Wrapper hoặc CI setup |
| JDK toolchain | CI/IDE/toolchains + Compiler Plugin `release` |
| Java dependencies | `dependencies` / `dependencyManagement` |
| Maven plugins | `build/plugins` / `pluginManagement` |

`dependencyManagement` không tự tác động vào `.mvn/extensions.xml`; `pluginManagement` không tự chạy một plugin hoặc tự bật plugin extension. Nếu extension GAV khác Maven project GAV, **không tự dùng `${project.version}` làm extension version**.

### 9.2. Kiểm tương thích trước khi nâng cấp

Một extension có thể phụ thuộc Maven Core APIs, Maven Resolver, Sisu/Plexus, ClassWorlds, Java runtime version và các plugins. Cần đối chiếu:

- **Minimum supported Maven** (Build Cache Extension 1.3.0: Maven 3.9.0+).
- JDK dùng chạy Maven và JDK dùng compile source.
- Plugin versions/executions, nhất là compiler, test runners, generators.
- Maven Wrapper distribution và Maven IDE embedder.
- Classloader realm/packages/exported components.
- Remote cache schema, serialized formats và cache invalidation behavior.
- Transitive dependencies, CVEs, provenance và publisher signatures.

Đừng mặc nhiên nâng Maven 3.9 lên 4 chỉ vì extension ghi “supports Maven 4”; một repository còn có plugins khác chưa tương thích Maven 4. Pin và test **cả bộ build environment**.

### 9.3. Nguồn tin cậy và bảo mật

Extension thực thi cùng Maven process, nên:

1. Chỉ lấy artifact từ Apache/Maven Central hoặc mirror được tổ chức tin cậy.
2. Kiểm GAV/version/signatures/checksums theo supply-chain policy.
3. Audit release notes, changelog và transitive dependencies.
4. Không đưa repository passwords vào POM/`extensions.xml`; dùng `settings.xml`/CI secrets.
5. Rà soát remote cache read/write permissions và nguy cơ cache poisoning.
6. Không thêm một extension bằng PR không review, vì nó có thể chạy **trước build tests**.
7. Phân tách publisher/verifier nếu release yêu cầu provenance cao.
8. Không log `-X` công khai nếu có repo URLs/credentials/nội bộ.

### 9.4. Quy trình nâng cấp 1.2.3 → 1.3.0

Ví dụ thay version:

```diff
 <extension>
     <groupId>org.apache.maven.extensions</groupId>
     <artifactId>maven-build-cache-extension</artifactId>
-    <version>1.2.3</version>
+    <version>1.3.0</version>
 </extension>
```

Đây là diff **minh họa**, không tự thay một project khác. 1.2.3 và 1.3.0 đều là release Maven Build Cache Extension. Quy trình:

1. Ghi baseline `mvn --version`, `java -version`, extension current version và CI config.
2. Đọc release notes, đặc biệt compatibility và cache-format changes.
3. Tạo PR chỉ đổi extension version/cache config có lý do rõ.
4. Chạy **clean verify khi cache disabled**, kiểm 4 tests và JAR/stdout.
5. Chạy cache enabled, kiểm logs/hit/miss và output restoration.
6. Cố tình đổi source hoặc resource input trong nhánh test để xác minh cache invalidation.
7. Kiểm một reactor nhiều module nếu production dùng multi-module.
8. Thử trên JDK/Maven/IDE/CI runners được hỗ trợ.
9. Benchmark elapsed time và memory nhiều lượt, không kết luận từ một run.
10. Kiểm remote cache policy/credentials và integrity nếu có.
11. Merge có rollback plan; chỉ bật rộng sau pilot.
12. Khi lỗi, revert version/config rồi chạy Maven invocation mới, kiểm lại artifacts.

### 9.5. Khi nào phải rollback?

Rollback nếu Maven startup fail, `NoSuchMethodError`/`ClassNotFoundException` xuất hiện sau upgrade, cache hồi phục output cũ sau đổi inputs, unit tests bị bypass bất ngờ, Java artifact không nhất quán, hoặc CI/IDE/Maven behavior lệch với policy.

Rollback tốt nhất là **Git revert** extension descriptor/config, không xóa bừa `~/.m2/repository` hoặc sửa global `lib/ext`. Nếu cache cũ không còn tin cậy, tách biệt cache location hoặc disable cache trong lúc kiểm, theo policy lưu trữ của tổ chức.

## 10. .mvn, Maven Wrapper và settings có vai trò riêng

Trong repository:

```text
.mvn/
├── extensions.xml
├── maven.config
├── jvm.config
└── wrapper/
    └── maven-wrapper.properties
mvnw
mvnw.cmd
```

- `extensions.xml`: khai core extension.
- `maven.config`: command-line arguments áp dụng cho Maven project (Maven 3.9+: **mỗi argument riêng một dòng**).
- `jvm.config`: JVM options khởi chạy Maven (ví dụ heap memory).
- `wrapper/maven-wrapper.properties`: Maven distribution cho wrapper.
- `settings.xml`: mirrors, proxies, servers/auth, active settings profiles, local repository.

Một `.mvn/maven.config` hợp lệ có thể là:

```text
-B
--no-transfer-progress
```

Không đặt XML `<extensions>` vào `maven.config` hoặc `jvm.config`. Không hardcode đường dẫn `C:\Users\...` tới một extension JAR vào Maven config của team khi có descriptor GAV chuẩn.

### 10.1. Wrapper không thay version extension

Trên Unix:

```bash
./mvnw -B clean verify
```

Trên PowerShell:

```powershell
.\mvnw.cmd -B clean verify
```

Chỉ dùng lệnh wrapper nếu repo đã có các files của Wrapper. Wrapper pin Maven distribution, **không tự cài JDK 17** hoặc thay `.mvn/extensions.xml`. Muốn project dùng bản Maven 3.9.x được hỗ trợ và extension 1.3.0, phải kiểm **cả hai**.

### 10.2. Maven 3.10 có global extension config mới

Tài liệu Maven cập nhật nêu từ **Maven 3.10.0** còn hỗ trợ:

```text
${user.home}/.m2/extensions.xml
${maven.home}/conf/extensions.xml
```

Không suy rằng **Maven 3.9.x** của lab đã hỗ trợ hai đường dẫn global này. Với 3.9.x, lựa chọn hợp lý và reproducible là project `.mvn/extensions.xml`. Legacy mechanisms như `${maven.home}/lib/ext` hoặc `-Dmaven.ext.class.path=extension.jar` có thể dùng trong tình huống đặc biệt, nhưng đòi manual file/CLI management, kém thân thiện với team/CI.

### 10.3. Repository bootstrap và settings

Core extension được resolve sớm; nếu project chỉ khai repository trong POM mà extension không tải được ngay startup, hãy kiểm **settings mirrors, repository auth, proxy/truststore, global/user settings**. Không tự “chữa” bằng thêm extension vào application dependencies. Với CI, credentials nên lấy từ secret manager và server ID khớp repository settings; không commit secrets.

## 11. Classloader realms và lỗi khó hiểu

Maven có nhiều realms:

```text
Maven Core runtime
    |
    +-- Core extension classloader
    |     └─ cache extension + dependencies
    |
    +-- Project/build extension realm
    |
    +-- Maven plugin realm
          └─ compiler/surefire/jar plugins + plugin dependencies

Java project classpath
    └─ target/classes + declared project dependencies
```

Tầng Java project **không** tự có mọi transitive dependency của extension, và Maven extension realm **không** tự sử dụng arbitrary application dependencies. Vì vậy lỗi extension không giải quyết bằng cách thêm JAR vào `<dependencies>` của Java app.

Core descriptor có tùy chọn:

```xml
<classLoadingStrategy>self-first</classLoadingStrategy>
```

Maven CoreExtensions reference cho biết giá trị mặc định **`self-first`**, ngoài ra có `parent-first` và `plugin`. **Giữ mặc định trừ khi publisher hoặc tài liệu classloading yêu cầu khác**. Thay tùy tiện có thể thay class resolution và gây binary incompatibility.

### 11.1. Bảng chẩn đoán lỗi

| Dấu hiệu | Nguyên nhân khả dĩ | Cách kiểm |
| --- | --- | --- |
| `ExtensionResolutionException` | GAV/version/repository không resolve | Descriptor, mirror/settings/auth |
| `ClassNotFoundException` startup | Extension dependency hoặc realm visibility | Binary versions/classloader/docs |
| `NoClassDefFoundError` trong Maven Core | Extension API/implementation không tương thích | Maven version vs extension version |
| `NoSuchMethodError` | Binary API khác Maven Core/Resolver | Release notes, transitive deps |
| Unknown packaging `bundle` | Plugin-provided extension chưa được kích hoạt | `extensions=true` và plugin config |
| Cache không có hit | Inputs đổi/config sai/feature disabled | Cache logs và config |
| Cache trả artifact cũ | Input selectors/critical plugin parameters thiếu | Reconcile cache inputs, tắt cache |
| Maven IDE lỗi nhưng CLI pass | IDE Maven embedder/JDK khác hoặc root phát hiện khác | Wrapper/IDE importer settings |
| Build green nhưng tests không thật chạy | Cache reuse hoặc skip flags/test phase | Surefire XML/gate và policy |
| Maven 3.9 không đọc user-global descriptor | Maven 3.10 feature không áp dụng | Project `.mvn/extensions.xml` |
| Extension version là POM property | Descriptor đọc trước POM | Literal GAV version |
| Lỗi 401/403 khi startup | Auth/proxy/mirror | Maven settings, không copy JAR lạ |
| Re-declare extension ở nhiều nơi | Duplicate components/classloader conflict | Chỉ đăng ký một supported mode |

### 11.2. Debug khi Maven chưa chạy nổi validate

```bash
mvn -B -X validate
```

`-X` có thể hiển thị Maven bootstrap, extension resolution, classloading/repository errors và properties. **Cần lọc secrets/URLs nội bộ** trước khi gửi log. Nếu core extension lỗi trước khi POM model được dựng, `mvn help:effective-pom` cũng có thể fail; dùng Git worktree sạch, rollback descriptor hoặc sửa settings để điều tra, không sửa Maven installation global một cách tùy tiện.

## 12. Build cache correctness và CI

**Một build nhanh không nhất thiết là một build đúng.** Để cache an toàn, extension phải nhận biết những inputs thực sự ảnh hưởng outputs:

- `src/main/java`, `src/test/java`, resources, generated source definitions.
- Effective plugin configs, compiler flags, test selectors và profiles.
- BOM/parent dependencies, Java toolchains và môi trường ảnh hưởng output.
- Configuration files ngoài source roots như API specs, templates, codegen inputs.
- Maven build session scopes, module dependencies và plugin executions.

Nếu source `openapi.yaml` thay đổi nhưng cache selectors không theo dõi nó, có nguy cơ reuse JAR cũ. Đây là lỗi correctness, phải tắt cache/điều chỉnh config và viết validation tests trước khi bật lại.

### 12.1. Cache hit không chứng minh test vừa chạy

Build Cache Extension có thể reuse previously validated outputs. Trong CI, phân biệt:

1. **Quick-feedback job:** cache read có thể phù hợp nếu input/attestation đáng tin.
2. **Required unit test job:** policy có thể yêu cầu Surefire chạy thật ở invocation hiện tại; dùng `-Dmaven.build.cache.enabled=false clean verify` hoặc quy trình được tổ chức xác nhận.
3. **Release job:** kiểm artifacts, required tests, signatures/provenance theo policy, không phát hành chỉ dựa vào cache hit.

Đừng dùng `BUILD SUCCESS` hay việc có `target/surefire-reports` như bằng chứng test mới chạy nếu file được restore từ cache. Ghi rõ semantic “new execution” hay “reused trusted result”.

### 12.2. Multi-module root và tính nhất quán

```text
workspace/
├── .mvn/extensions.xml
├── pom.xml                 # <modules>
├── core/pom.xml
└── app/pom.xml
```

Một Maven invocation có một root core extension policy. Không khai cùng extension version A tại root nhưng version B trong các child rồi kỳ vọng Maven dùng cả hai độc lập trong cùng JVM. Dùng root descriptor và pin one version per build session. Nếu project cần hai policy khác nhau, cân nhắc tách invocation/workspace theo docs của extension.

### 12.3. CI shell Linux tham khảo

Fragment sau yêu cầu CI runner đã checkout repo và cài JDK17/Maven3.9.x:

```bash
#!/usr/bin/env sh
set -eu

java -version
mvn --version

mvn -B --no-transfer-progress \
    -Dmaven.build.cache.enabled=false clean verify

test -s target/extension-registration-lab-1.0.0.jar
java -cp target/extension-registration-lab-1.0.0.jar \
    vn.example.extensions.Main
```

Nếu Maven command fail, `set -eu` làm job fail. File JAR phải tồn tại/không rỗng; xem Surefire reports để kiểm **4 tests executed, zero failure/error**. Điều này không tự cài tools/secrets. Một job khác có thể chạy cache-enabled build để đo hiệu năng và verify input invalidation.

### 12.4. Windows PowerShell tham khảo

```powershell
java -version
mvn.cmd --version
mvn.cmd -B "-Dmaven.build.cache.enabled=false" clean verify
java -cp "target\extension-registration-lab-1.0.0.jar" vn.example.extensions.Main
```

Cần chạy ở project root, Maven/JDK/repository settings hợp lệ. Dùng PowerShell một dòng để tránh nhầm ký tự continuation. Không nhầm dấu `\` trong Windows path với XML/URI syntax.

## 13. Một quy trình rollout/rollback vận hành được

**Rollout extension mới nên tách các lớp rủi ro:**

```text
Understand requirement
    ↓
Choose core vs build extension mode
    ↓
Pin GAV/version and document compatibility
    ↓
Review trusted publisher + transitive dependencies
    ↓
PR with clean/uncached baseline
    ↓
CI cache-enabled + invalidation + multi-module tests
    ↓
Pilot rollout
    ↓
Monitor cache hit/miss, memory, build outputs, test coverage
    ↓
Production rollout; keep revert procedure
```

**Rollback không cần sửa Maven Core installation:** revert tracked `.mvn/extensions.xml` version/config qua Git trong một invocation mới, build sạch và validate. Nếu local build cache cũ gây nghi ngờ, đổi cache location hoặc disable cache, không xóa toàn bộ `~/.m2` khi chưa có bằng chứng.

Những thay đổi extension nên được code review như thay đổi compiler/plugin toolchain vì có thể khiến code thực thi ở early build stage. Với remote cache, lập chính sách trusted branch, ACL và cache output integrity để tránh một pipeline không đáng tin ghi đè artifact được pipeline release tiêu thụ.

## 14. Những anti-pattern phải tránh

**Sai 1 — coi extension như project dependency:**

```xml
<dependency>
    <groupId>org.apache.maven.extensions</groupId>
    <artifactId>maven-build-cache-extension</artifactId>
    <version>1.3.0</version>
</dependency>
```

Không kích hoạt build cache bằng cách này. Đúng là `.mvn/extensions.xml` hoặc `build/extensions` theo docs.

**Sai 2 — để version tự động trôi:**

```xml
<version>LATEST</version>
```

Không dùng dynamic version cho core extension nếu cần reproducible build. Pin literal release, nâng có review.

**Sai 3 — dùng POM property cho core descriptor:**

```xml
<version>${project.version}</version>
```

Core extension được nạp sớm, `project.version` là version ứng dụng và không phải extension release version.

**Sai 4 — thêm extensions=true vào mọi plugin:**

Một plugin bình thường không cần nạp extension components để chạy goals; cờ này có thể gây behavior thay đổi hoặc bootstrap errors. Đọc plugin docs trước.

**Sai 5 — tắt cache rồi tưởng gỡ extension:**

`-Dmaven.build.cache.enabled=false` vẫn nạp Maven Build Cache Extension. Để thử không extension, dùng worktree/revert descriptor với Maven invocation mới.

**Sai 6 — cache hit rồi bỏ quality gate:**

Cache can thiệp vào build flow; phải kiểm output correctness, invalidation và test/report policy. Không phát hành chỉ vì có `BUILD SUCCESS`.

**Sai 7 — cài JAR vào Maven global thủ công:**

Cách legacy `lib/ext` gây drift giữa developer và CI, khó audit version/transitive dependencies. Ưu tiên project descriptor GAV.

## 15. Câu hỏi ôn tập kèm đáp án

**1.** Core extension khác build extension ở đâu? **Đáp án:** thời điểm/classloader nạp; core nạp sớm qua `.mvn/extensions.xml`, build nạp muộn theo POM.

**2.** Khi thêm JUnit cho project, cần extension? **Đáp án:** không; dùng `test` dependency và Surefire plugin.

**3.** Có nên khai Build Cache Extension 1.3.0 cả ở POM và `.mvn/extensions.xml`? **Đáp án:** không; chọn một supported registration, Apache khuyến nghị core model.

**4.** Maven Wrapper có tự pin extension version? **Đáp án:** không; wrapper pin Maven distribution, extension pin riêng.

**5.** Tại sao `pluginManagement` không thay cho `<extensions>true</extensions>`? **Đáp án:** pluginManagement quản lý cấu hình/versions, không tự kích hoạt plugin extension.

**6.** `maven.build.cache.enabled=false` có ngừng load core extension? **Đáp án:** không; nó tắt cache features sau khi extension được load.

**7.** Vì sao cần version literal trong `.mvn/extensions.xml`? **Đáp án:** extension nạp trước effective POM và cần deterministic bootstrap; POM property không phải nguồn version ổn định.

**8.** Nếu Maven không qua `validate` sau upgrade, làm gì? **Đáp án:** kiểm descriptor/repository/Maven compatibility, dùng Git rollback và invocation mới.

**9.** Maven build cache local directory có phải `~/.m2/repository` không? **Đáp án:** mặc định là sibling `build-cache`, không phải repository dùng resolve dependencies.

**10.** `ClassNotFoundException` ở startup có giải quyết bằng project dependency? **Đáp án:** không mặc định; lỗi liên quan extension classloader hoặc artifact/dependency resolution ở Maven runtime.

**11.** Maven 3.9 có tự dùng `~/.m2/extensions.xml` không? **Đáp án:** không giả định; global descriptor support theo tài liệu mới bắt đầu ở Maven 3.10.0.

**12.** Cache hit có đảm bảo Surefire vừa chạy trong invocation đó? **Đáp án:** không; cần test execution policy và report/attestation phù hợp.

**13.** Cần thay classLoadingStrategy khi upgrade? **Đáp án:** chỉ nếu publisher/hướng dẫn API nói rõ và đã test; giữ default self-first nếu không cần.

**14.** Lỗi 401 khi resolve core extension sửa ở đâu? **Đáp án:** Maven settings/mirror/proxy/auth/repository availability, không chép JAR lạ vào `lib/ext`.

**15.** Rollback extension nên làm gì? **Đáp án:** revert descriptor/config có version pin, chạy Maven invocation mới, clean verify và kiểm artifacts/tests.

## 16. Checklist nghiệm thu

- [ ] Xác định extension giải quyết vấn đề Maven runtime nào, không nhầm plugin/dependency.
- [ ] Publisher docs xác nhận core hoặc build registration phù hợp.
- [ ] Core extension được khai trong `.mvn/extensions.xml` có GAV/version thật, đặt đúng root.
- [ ] Build extension/plugin extension chỉ khai nếu publisher hỗ trợ.
- [ ] Không bật `extensions=true` một cách máy móc và không đăng ký duplicate extension.
- [ ] Maven 3.9.x, JDK17 và extension compatibility được xác minh.
- [ ] Maven Wrapper/settings/repositories/credentials phù hợp trước Maven bootstrap.
- [ ] Version pin literal, không dùng dynamic versions/POM property không được hỗ trợ.
- [ ] Clean verify không cache chạy 4 JUnit tests và tạo JAR đúng.
- [ ] Java app stdout `gross=250`, `net=200`, `status=PASS`.
- [ ] Cache-enabled behavior, input invalidation và build outputs được kiểm riêng.
- [ ] Không nhầm cache hit với tests thực thi mới.
- [ ] Remote cache có ACL/integrity/branch trust policy khi áp dụng.
- [ ] Multi-module session dùng core descriptor thống nhất.
- [ ] Nâng cấp bằng PR, changelog/security review, matrix tests và performance data.
- [ ] Rollback bằng Git/revert, không phá Maven installation hoặc xóa toàn `~/.m2` tùy tiện.
- [ ] Khi lỗi startup, kiểm extension GAV/classloader/compatibility và Maven `-X` logs đã lọc secrets.
- [ ] Project/CI/IDE dùng Maven root/toolchain/extension version nhất quán.

## 17. Nguồn chính thức

- [Apache Maven — Using Extensions](https://maven.apache.org/guides/mini/guide-using-extensions.html)
- [Apache Maven — Configuring Maven](https://maven.apache.org/configure)
- [Apache Maven 3.9 — Core Extensions descriptor](https://maven.apache.org/ref/3.9.16/maven-embedder/core-extensions.html)
- [Apache Maven — Maven classloading](https://maven.apache.org/reference/maven-classloading.html)
- [Apache Maven — POM reference/build extensions](https://maven.apache.org/pom.html)
- [Apache Maven — Build Cache Extension Getting Started](https://maven.apache.org/extensions/maven-build-cache-extension/)
- [Build Cache Extension — Usage](https://maven.apache.org/extensions/maven-build-cache-extension/usage.html)
- [Build Cache Extension — Parameters](https://maven.apache.org/extensions/maven-build-cache-extension/parameters.html)
- [Build Cache Extension — Config Template](https://maven.apache.org/extensions/maven-build-cache-extension/maven-build-cache-config.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Available Extensions](https://maven.apache.org/extensions/index.html)
