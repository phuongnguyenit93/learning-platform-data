# Dùng Maven Artifact Plugin để kiểm tra và so sánh artifact

Maven có thể tạo được một JAR chạy đúng nhưng **không tái lập được cùng tập byte** khi build lại từ cùng nguồn. Một file ZIP/JAR có timestamp của từng entry, thứ tự file, manifest, metadata, nguồn generated code hoặc môi trường biên dịch khác nhau có thể dẫn đến kết quả byte-for-byte khác dù ứng dụng có vẻ hoạt động giống nhau. **Apache Maven Artifact Plugin** hỗ trợ phát hiện và điều tra điều đó bằng cách phân tích *execution plan*, mô tả output và **so sánh artifact đang build với artifact tham chiếu**.

Trong chủ đề **Build tái lập**, mục tiêu của bài là trả lời ba câu hỏi thực tiễn:

1. Build plan hiện tại có dùng plugin version hoặc goal nào đã biết có vấn đề về reproducible build?
2. Một lần build thực sự tạo ra những artifact nào, với dấu vân tay và bối cảnh nào?
3. Với **cùng nguồn, cùng hướng dẫn build và môi trường được kiểm soát**, kết quả có khớp bản reference đã cài hoặc phát hành hay không?

Điểm cốt lõi: **`artifact:check-buildplan` là kiểm tra cấu hình/rủi ro, không phải bằng chứng bytes khớp; `artifact:compare` mới đối chiếu output thực tế với reference.** Phép compare trên một máy là bước thử hữu ích nhưng **không thay thế rebuild độc lập** trên máy/container khác và so với release chính thức.

Bài sử dụng **Maven 3.9.x, Java 17+, Maven Artifact Plugin 3.7.0**, một thư viện Java nhỏ có JUnit 5, JAR Plugin và Source Plugin hỗ trợ timestamp cố định. Chúng ta sẽ tạo reference với `clean install`, build lại bằng `clean verify` kèm `artifact:compare`, đọc `.buildcompare`/`.buildinfo`, thử mismatch có kiểm soát, phân tích bằng `diffoscope` khi cần và đưa gate vào CI. Không cần Docker để thực hành nội bộ, nhưng phần cuối trình bày cách xác minh độc lập ở môi trường khác.

## 1. Phân biệt Artifact Plugin với các công cụ có tên gần giống

| Công cụ | Nhiệm vụ | Có chứng minh tái lập byte-for-byte không? |
| --- | --- | --- |
| **Maven Artifact Plugin** (`maven-artifact-plugin`) | Kiểm build plan, mô tả build output, so sánh artifact với reference, tạo `.buildcompare` | **`compare`** trực tiếp kiểm bytes/fingerprints theo phạm vi |
| Maven JAR Plugin | Đóng gói `.class` và resources vào JAR; có tùy chọn ổn định archive metadata | Chỉ tạo output, không so với reference |
| Maven Source Plugin | Tạo sources JAR đính kèm | Không tự so các lần build |
| Maven Install Plugin | Cài POM, main artifact và attachments vào local repository | Tạo **reference local** cho buổi thực hành, không tự kiểm bytes |
| Maven Deploy Plugin | Đưa artifacts lên repository dùng chung | Phát hành, không phải bộ kiểm tái lập |
| Maven Dependency Plugin | Xem/copy/analyze dependencies | Không phải công cụ so toàn bộ build outputs |
| Maven Enforcer Plugin | Áp rules phiên bản JDK/Maven/dependencies | Bổ trợ, không thay compare |
| `sha256sum` / `Get-FileHash` | Tính digest cho file cụ thể | Có thể so bytes cùng một file, nhưng thiếu Maven-aware scope/reference/workflow |
| `diffoscope` | So sánh sâu nội dung hai archive/files | Giải thích **vì sao** khác, không tự xây Maven reference |

Không nhầm Artifact Plugin với `mvn dependency:tree` hay thao tác `jar tf`. Một chương trình có dependencies y hệt vẫn có thể tạo JAR khác từng byte do timestamp hoặc generated files.

### 1.1. Reproducible build là gì?

Một build được gọi là **reproducible** khi cùng source, build instructions và **các đầu vào/môi trường đã được xác định**, các bên độc lập có thể tạo lại các artifact có **nội dung byte-for-byte giống bản reference**. Có sự khác biệt giữa:

- **Functional equivalence:** chương trình chạy và trả kết quả tương tự.
- **Deterministic build trên một máy:** cùng môi trường tạo ra cùng bytes trong các lần chạy.
- **Reproducible build độc lập:** một hệ thống/đơn vị khác, với các đầu vào đã công bố và setup tương thích, dựng lại bytes giống release.
- **Verified provenance:** thêm bằng chứng nguồn, builder, chính sách ký số/attestation; so byte bằng nhau giúp ích nhưng **không tự chứng minh** nguồn an toàn hay build không bị xâm phạm.

Ví dụ hai JAR đều in `net=200` nhưng một file chứa ZIP entry timestamps khác, nên SHA-256 khác. Kiểm Java stdout không thay so sánh archive.

### 1.2. Phạm vi của một lần compare

Artifact Plugin quan tâm **những file output mà Maven xác định là artifacts**, chẳng hạn main JAR/POM và **attached artifacts**. Nó không mặc nhiên kiểm mọi log, file tạm hay mọi file trong `target/`. Do đó:

- Cần biết POM nào, các modules nào và những classifiers nào đã được build/attach.
- Không tự xem việc không so một file là “file đó khớp”.
- Khi có skip/ignore rules, phải audit xem chính sách có vô tình loại các output quan trọng không.
- Với release có nhiều modules, phải so tất cả các modules/variants dự kiến, không chỉ module cuối hoặc một `-pl` subset.

## 2. Các goal chính của Maven Artifact Plugin 3.7.0

| Goal | Mục đích | Khi nào dùng? |
| --- | --- | --- |
| `artifact:check-buildplan` | Kiểm execution plan với cơ sở dữ liệu plugin/goals có vấn đề reproducibility đã biết | Trước khi đầu tư so bytes; dùng làm kiểm tra build policy |
| `artifact:compare` | So current package/build outputs với reference đã `install` hoặc có trong remote repository, ghi `.buildcompare` | Goal **quan trọng nhất** để xác minh một lần rebuild |
| `artifact:describe-build-output` | Mô tả artifacts do build hiện tại tạo ra; hiện là **experimental** | Điều tra phạm vi build output, thường gọi từ reactor root **sau** build |
| `artifact:buildinfo` | Ghi `.buildinfo` theo định dạng phục vụ thông tin build và fingerprints | **Deprecated ở phiên bản hiện hành**; ưu tiên `describe-build-output`/`compare` cho workflow mới |
| `artifact:reproducible-central` | Tạo **report** từ dữ liệu trạng thái Reproducible Central của project/dependencies | Quan sát trạng thái bên ngoài, **không phải kiểm lại bằng máy hiện tại** |
| `artifact:help` | Xem plugin/goal parameters | Khi cần tra user property và default behavior |

**Thông tin phiên bản:** Các goals và tham số dưới đây được dựa trên hướng dẫn chính thức Maven Artifact Plugin **3.7.0**. Luôn pin plugin version trong POM hoặc dùng command tọa độ đầy đủ; tránh gọi prefix không có version từ môi trường chưa xác định.

### 2.1. artifact:check-buildplan

Goal này xem *Maven execution plan* dự kiến rồi phát hiện những plugin/goal versions có **vấn đề reproducibility đã được ghi nhận**. Ví dụ:

```bash
mvn -B org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
```

Theo goal parameters, default `check.buildplan.tasks` là `deploy` (đánh giá plan cho phạm vi lifecycle đó). Có thể chọn tasks/phase khi chính sách cần một plan nhỏ hơn; không nhầm “chạy check trên plan deploy” với “đã thực sự deploy”.

Tham số đáng biết:

- `check.failOnNonReproducible`: default **true**, có thể làm build fail khi plan chứa plugin có vấn đề đã biết.
- `check.buildplan.tasks`: xác định tasks được dùng để tính plan.
- `diagnose`: yêu cầu thêm thông tin chẩn đoán `outputTimestamp`.
- `check.plugin-issues`: dùng file danh mục plugin issues thay thế — chỉ khi tổ chức chủ đích quản trị policy này.

**Giới hạn:** không tìm thấy vấn đề trong danh sách plugin known issues **không chứng minh** kết quả đã reproducible. Một custom generator có thể ghi timestamp, username hoặc UUID vào resource dù plugin version nằm trong danh sách tương thích.

### 2.2. artifact:describe-build-output

Đây là goal **experimental**, nhằm mô tả output của build. Theo tài liệu, goal là **aggregator**, thích hợp gọi từ CLI ở reactor root **sau khi build xong**, không bind vào phase khi reactor có thể chạy goal ở root trước khi các child module tạo outputs.

Ví dụ một-module:

```bash
mvn -B clean verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:describe-build-output
```

Trong multi-module, xem build logs/file kết quả để biết nó đã liệt kê những module/artifact nào. Đừng dựa vào một tên file hoặc vị trí duy nhất chưa xác nhận từ plugin output vì behavior/output format có thể phát triển khi goal còn experimental.

### 2.3. artifact:compare

Goal `compare` lấy **current build output** rồi đối chiếu reference:

- Reference **local repository**: ví dụ project đã `mvn clean install` trước đó.
- Reference **remote repository**: ví dụ `central` hoặc một staging repository có quyền truy cập và cùng GAV.
- Khi có reference `.buildinfo`, plugin có thể sử dụng nó; nếu không, plugin có khả năng suy dựng thông tin từ downloaded reference artifacts.
- Khi khác, log và `.buildcompare` mô tả lỗi/khác biệt, giúp khoanh vùng file để so sâu.

Lệnh trọng tâm:

```bash
mvn -B clean install
mvn -B clean verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

**Lệnh thứ hai KHÔNG có `install`**, vì install lại trước compare có thể ghi đè reference local mà ta muốn đối chiếu. Theo hướng dẫn chính thức Maven, đây là bài thử cơ bản để phát hiện ZIP timestamps/build output không ổn định. Bất cứ khi nào có thể, dùng một thư mục source sạch và cùng commit cho cả hai builds.

Tham số quan trọng:

| Tham số / user property | Default | Ý nghĩa |
| --- | --- | --- |
| `compare.fail` | `true` | Khi detected difference, goal báo Maven failure. Dùng false chỉ để điều tra, không dùng làm gate phát hành |
| `reference.repo` | `central` | Repository tham chiếu; có thể là repo ID, URL hoặc `id::url` |
| `compare.aggregate.only` | `false` | Chỉ so aggregate vào cuối reactor hoặc so theo từng module |
| `buildinfo.ignoreJavadoc` | `true` | Mặc định không tính Javadoc attached artifacts vào buildinfo; phải cân nhắc nếu phát hành yêu cầu kiểm Javadoc |
| `buildinfo.ignore` | danh sách trống | Glob để bỏ qua một số artifacts; nguy cơ che missing/difference |
| `buildinfo.skipModules` | danh sách trống | Bỏ qua trọn module phù hợp glob khi policy cho phép |
| `buildinfo.detect.skip` | `true` | Tự phát hiện modules đã cấu hình bỏ install/deploy để tránh lấy fingerprint |
| `diagnose` | `false` | Chẩn đoán giá trị effective `project.build.outputTimestamp` |

Theo tài liệu, `artifact:compare` **không được đánh dấu thread-safe**; nên chạy sequential khi reproducibility check, đặc biệt trong reactor nhiều modules. Không mặc định thêm `mvn -T` vào command compare.

## 3. Điều kiện đầu vào giúp artifact ổn định

Đừng chỉ trông đợi Artifact Plugin “sửa” file khác nhau. Nó **phát hiện khác biệt**, còn việc tạo artifact ổn định thuộc cấu hình của những plugin xây artifacts.

### 3.1. project.build.outputTimestamp

Thêm property vào POM:

```xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Một số Maven archive plugins hỗ trợ property này để đặt timestamp **cố định cho ZIP/JAR entries**, thay vì đưa thời điểm hiện tại vào archive. Theo hướng dẫn Maven, đó là một trong những nền tảng cho reproducible build; đặc biệt hữu ích trên Maven 3.9.x.

Không thay timestamp này bằng thời điểm hiện tại trong mỗi build. Nếu muốn gắn với commit, có thể dùng **commit timestamp được truy xuất cố định** trong release process, nhưng phải đảm bảo mọi bên rebuild cùng một giá trị. Property là một phần của **build instructions**; đổi nó giữa hai lần build tạo ra đầu vào khác nhau.

### 3.2. Pin plugin và dependency versions

Reproducibility có thể bị phá bởi:

- `LATEST`/`RELEASE`, version ranges và `SNAPSHOT` động không được khóa.
- Plugin version không được pin, khiến build sau resolve khác.
- Annotation processor/plugin tải mã sinh tự động phiên bản thay đổi.
- JDK major version khác làm bytecode khác dù dùng cùng `--release 17` trong một số trường hợp.
- Build extensions/toolchains hoặc Maven repository trả artifacts khác theo thời điểm.
- Profile được bật khác, environment variables thay đổi output.
- Code/resources bị sinh bằng wall-clock, hostname, username hoặc random UUID.
- Platform text newline `CRLF` khác `LF`, locale và timezone ảnh hưởng file.
- Generated manifest/build metadata tự chèn `Build-Time` hoặc absolute path.

Dùng Maven Wrapper, Java toolchains/CI image cố định, dependency lock/policy và ghi chú full command line để môi trường rebuild có thể tái tạo cùng inputs. **Có outputTimestamp không đủ** nếu plugin khác vẫn nhúng dữ liệu biến thiên.

## 4. Dự án thực hành Java 17 có hai artifacts

Ta xây một thư viện nhỏ gồm **main JAR** và **source JAR**. Không cần database, server hay Docker; runtime chỉ dùng JDK. Có JUnit tests để build không phải ví dụ “rỗng”.

Cấu trúc:

```text
artifact-compare-lab/
├── pom.xml
└── src/
    ├── main/java/vn/example/repro/
    │   ├── PriceEngine.java
    │   └── Main.java
    └── test/java/vn/example/repro/
        └── PriceEngineTest.java
```

Mục tiêu:

1. `mvn clean verify` tạo `artifact-compare-lab-1.0.0.jar` và `artifact-compare-lab-1.0.0-sources.jar`.
2. `mvn clean install` tạo **reference local** của cả hai.
3. Rebuild same source/instructions với `clean verify` rồi `artifact:compare`.
4. Đọc `.buildcompare` và build logs, không chỉ nhìn dòng `BUILD SUCCESS`.
5. Chạy Java app; stdout xác định là `net=200`.
6. Tạo một thay đổi đầu vào có chủ đích để chứng minh công cụ **phát hiện chênh lệch**, rồi phục hồi source/property.

### 4.1. POM đầy đủ

File `artifact-compare-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>artifact-compare-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
        <junit.jupiter.version>5.11.0</junit.jupiter.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
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

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.4.0</version>
                <executions>
                    <execution>
                        <id>attach-main-sources</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-artifact-plugin</artifactId>
                <version>3.7.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích:**

- `packaging=jar` bind `jar:jar` mặc định ở phase `package`, tạo main JAR.
- Compiler Plugin cố định Java target release 17; kết quả phụ thuộc actual JDK/toolchain nên cần ghi nhận phiên bản JDK sử dụng.
- `project.build.outputTimestamp` cố định timestamp archive entries cho những plugin có hỗ trợ.
- Source Plugin `jar-no-fork` chạy ở `verify`, tạo **attached `sources` JAR**, không fork lifecycle và không cần manual command.
- Maven Install Plugin ở `install` cài POM/main/sources vào local repository. Compare **không install lại** trước khi đánh giá reference.
- Maven Artifact Plugin được pin version nhưng **không có execution tự động**; ta gọi `compare` và `check-buildplan` tường minh. Điều này tránh compare chạy quá sớm khi chưa có outputs/reference.
- JUnit là test-scoped dependency, không nằm trong runtime classpath của Main. Plugin versions pin để dễ tái lập.

### 4.2. PriceEngine.java — thuật toán có thể kiểm thử

File `src/main/java/vn/example/repro/PriceEngine.java`:

```java
package vn.example.repro;

/**
 * Computes discounted totals using integer arithmetic.
 */
public final class PriceEngine {
    private PriceEngine() {
    }

    /**
     * Returns the price after applying a discount percentage.
     *
     * @param price nonnegative price in integer units
     * @param discountPercent number from 0 through 100
     * @return discounted price, rounded down
     * @throws IllegalArgumentException for invalid inputs
     */
    public static int net(int price, int discountPercent) {
        if (price < 0 || discountPercent < 0 || discountPercent > 100) {
            throw new IllegalArgumentException("invalid price or discount");
        }
        return (int) ((long) price * (100 - discountPercent) / 100);
    }
}
```

Dùng `long` trong phép nhân để tránh overflow sớm của `int`, rồi ép về int. Vì `price` nằm trong khoảng 0..Integer.MAX_VALUE và percent 0..100 nên kết quả luôn trong khoảng 0..Integer.MAX_VALUE; cast ở đây an toàn. Không có random/time/current user trong dữ liệu tính toán.

### 4.3. Main.java — stdout chính xác

File `src/main/java/vn/example/repro/Main.java`:

```java
package vn.example.repro;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("net=" + PriceEngine.net(250, 20));
    }
}
```

Sau build:

```bash
java -cp target/artifact-compare-lab-1.0.0.jar vn.example.repro.Main
```

**Stdout duy nhất từ Java main:**

```text
net=200
```

Đây là **plain JAR** không khai `Main-Class` trong manifest, nên dùng `java -cp ... FQCN`, không mặc định `java -jar` chạy được. Test compare không phụ thuộc bạn chạy main trước hay sau khi đóng gói.

### 4.4. PriceEngineTest.java — unit tests thật

File `src/test/java/vn/example/repro/PriceEngineTest.java`:

```java
package vn.example.repro;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceEngineTest {

    @Test
    void appliesTwentyPercentDiscount() {
        assertEquals(200, PriceEngine.net(250, 20));
    }

    @Test
    void roundsDownFractionalResult() {
        assertEquals(84, PriceEngine.net(99, 15));
    }

    @Test
    void rejectsInvalidPrice() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceEngine.net(-5, 20)
        );
    }

    @Test
    void rejectsInvalidPercentage() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceEngine.net(100, 101)
        );
    }

    @Test
    void acceptsOneHundredPercentDiscount() {
        assertEquals(0, PriceEngine.net(1000, 100));
    }
}
```

Có **5 test methods**. Trong Maven Surefire, pattern `*Test` chạy class này ở phase `test`. Các assertions kiểm kết quả, rounding và invalid inputs; vẫn cần những test thiết kế riêng nếu đưa thuật toán vào nghiệp vụ production.

## 5. Chạy build lần đầu và tạo reference

Ở thư mục `artifact-compare-lab`, bảo đảm JDK 17+ và Maven 3.9.x:

```bash
java -version
mvn --version
mvn -B clean install
```

Các hành vi kỳ vọng:

1. Maven compile two production Java classes và one test class.
2. Surefire chạy 5 unit tests.
3. JAR Plugin tạo `target/artifact-compare-lab-1.0.0.jar`.
4. Source Plugin được bind `verify` tạo `target/artifact-compare-lab-1.0.0-sources.jar`.
5. Install Plugin cài main JAR, sources JAR và POM vào local repository, từ đó tạo **reference** cho lần so sánh.
6. Maven log kết thúc `BUILD SUCCESS` nếu test/plugin resolution/bộ công cụ hợp lệ.

Maven local repository mặc định có cấu trúc:

```text
~/.m2/repository/vn/example/artifact-compare-lab/1.0.0/
├── artifact-compare-lab-1.0.0.pom
├── artifact-compare-lab-1.0.0.jar
└── artifact-compare-lab-1.0.0-sources.jar
```

Có thể có metadata/resolver marker files khác. Nếu máy dùng `settings.xml` với `localRepository` tùy chỉnh hoặc `-Dmaven.repo.local`, tham chiếu **đúng directory thực tế**. Không xóa/ghi đè một reference đã dùng để audit release.

### 5.1. Kiểm các JAR đã sinh

```bash
jar tf target/artifact-compare-lab-1.0.0.jar
jar tf target/artifact-compare-lab-1.0.0-sources.jar
```

Main JAR nên chứa:

```text
vn/example/repro/Main.class
vn/example/repro/PriceEngine.class
```

Sources JAR nên chứa:

```text
vn/example/repro/Main.java
vn/example/repro/PriceEngine.java
```

Các file `META-INF`/manifest/POM descriptors có thể tồn tại thêm. **Đây là các entry bắt buộc cần tìm**, không phải output `jar tf` đầy đủ. File có tồn tại không chứng minh fingerprint giống; cần chạy `compare`.

### 5.2. Tính SHA-256 thủ công để quan sát

Trên Linux/macOS:

```bash
sha256sum target/artifact-compare-lab-1.0.0.jar
sha256sum target/artifact-compare-lab-1.0.0-sources.jar
```

Trên PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 "target\artifact-compare-lab-1.0.0.jar"
Get-FileHash -Algorithm SHA256 "target\artifact-compare-lab-1.0.0-sources.jar"
```

Không cung cấp digest cố định trong bài, vì phải tính từ bytes thực của build; **không bịa hash**. Hash check dùng để xác nhận cùng bytes của một file, còn plugin `compare` cung cấp Maven-aware workflow để xác định artifact family/reference và báo cáo những khác biệt.

## 6. Rebuild và so với reference đã install

Sau lần `clean install` **đầu tiên**, giữ nguyên source/POM và chạy:

```bash
mvn -B clean verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Hoặc trên Windows PowerShell gõ một dòng:

```powershell
mvn.cmd -B clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Vì phần `verify` chạy trước goal `compare`, các build outputs hiện tại đã tồn tại khi plugin bắt đầu lấy fingerprints. Plugin sẽ tra reference đã install trong local repository và/hoặc repo remote phù hợp, rồi đưa kết luận. Với cùng source/POM, same JDK/toolchain và các archive plugins hỗ trợ outputTimestamp, bài mẫu **dự kiến compare PASS**.

**Thứ tự cần đúng:**

```text
Lần 1: clean install
  => reference R1 trong local repository

Lần 2: clean verify + artifact:compare
  => current build B2 được so với R1
  => KHÔNG install B2 trước khi so, tránh ghi đè R1
```

Nếu lệnh so sánh phải tải reference từ `central` thay vì local, hoặc không tìm được đúng GAV, hãy xem logs và repository settings. Không tự tuyên bố “khác bytes” khi plugin thực ra gặp lỗi **thiếu reference/401/403/404/timeout**.

### 6.1. Đọc output .buildcompare

Tài liệu Maven mô tả `artifact:compare` tạo file `.buildcompare` để ghi summary và diff. Với module `artifact-compare-lab`, build logs thường chỉ file dạng:

```text
target/artifact-compare-lab-1.0.0.buildcompare
```

Plugin cũng có thể tạo file `.buildinfo` và directory chứa **downloaded reference artifacts**, tùy goal/version. Với multi-module, có thể có aggregate `.buildcompare` ở root hoặc module cuối. **Luôn lấy path thực từ Maven log** thay vì dựa tuyệt đối vào tên/vị trí ví dụ.

Nội dung file/log có thể mô tả:

- Artifacts nào có fingerprints khớp.
- Artifacts nào khác size hoặc digest.
- Build metadata (JDK/OS/outputTimestamp) giúp khoanh vùng.
- Đường dẫn tới current artifact và reference artifact để chạy diffoscope.
- Summary bao nhiêu file matched/different theo phạm vi đã chọn.

Không ghi trong bài một “số file match” cố định vì plugin có thể tính cả POM, sources và attached outputs, và một số entries phụ thuộc cấu hình. **BUILD SUCCESS + summary no differences** là kỳ vọng, không phải log đã được thực thi trong tài liệu.

### 6.2. compare.fail làm build đỏ khi khác

Theo phiên bản 3.7.0, `compare.fail` mặc định là `true`. Khi có detected artifact mismatch, Maven invocation sẽ fail theo rule của goal. Đây là đặc tính hữu ích để làm CI release gate.

Có thể dùng tạm:

```bash
mvn -B clean verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare \
  -Dcompare.fail=false
```

để chỉ thu log/file compare khi đang điều tra, **nhưng không dùng `compare.fail=false` trên job quyết định release**, vì workflow có thể xanh dù bytes khác. Những lỗi transport/reference resolution cũng không được tự phân loại thành PASS.

## 7. Thử âm tính: kiểm công cụ phát hiện output khác

Sau khi tạo reference R1, bạn có thể cố ý thay đổi **đầu vào tạo artifact** để xác minh `compare` thực sự báo mismatch.

Cách ít tác động tới Java code là đổi property trong bản thử nghiệm:

```xml
<project.build.outputTimestamp>2024-02-02T00:00:00Z</project.build.outputTimestamp>
```

rồi chạy lại **`clean verify` + `compare`** nhưng **không chạy `install`**. Vì timestamp của ZIP entries/POM là đầu vào đã đổi, artifact bytes dự kiến khác và `compare` có thể báo mismatch. Sau đó **khôi phục** property ban đầu `2024-01-01T00:00:00Z` rồi chạy lại compare.

**Phân biệt ý nghĩa kết quả:** đây chỉ là một *negative control* chứng minh comparison mechanism có khả năng bắt khác biệt. Nó **không chứng minh** bản build ban đầu không reproducible, vì bạn đã **thay đổi build instructions**. Một reproducibility test nghiêm túc phải giữ nguyên source, build instructions và đầu vào được quy định.

Cách khác có thể đổi một string literal trong `Main.java` rồi rebuild để tạo JAR khác, nhưng đó là **thay source**, nên cũng chỉ kiểm detector, không đánh giá khả năng tái lập khi cùng inputs.

### 7.1. Mismatch do code hay metadata?

Một số nguyên nhân thường gặp:

| Triệu chứng | Gợi ý nguyên nhân |
| --- | --- |
| JAR digest khác, class files giống | ZIP entry timestamps/order, manifest, `pom.properties`, extra resources |
| `Main.class` khác | JDK/compiler/options khác, generated source khác, source thực sự thay đổi |
| `pom.xml` reference khác | Bản build thay POM, release plugin chỉnh version, CI-friendly resolution |
| Sources JAR khác | Newline/encoding/file order, source filtering, generated source path |
| Classifier `javadoc` khác | Javadoc timestamps/toolchain/locale/doclint; mặc định plugin có thể ignore Javadoc |
| Diff chỉ trong build metadata | Build time, username, hostname, path, Git dirty flag, random seed |
| Compare không tìm thấy artifact | GAV/classifier/repository/auth không khớp, chưa install/deploy |
| Current chỉ có JAR, reference có sources | Source Plugin execution/profile/skip khác, **scope đã khác** |

Khi mismatch liên quan sources/Javadoc/JAR, kiểm **effective POM và plugin versions** trước; đừng tự kết luận rằng Java algorithm sai.

## 8. Phân tích chi tiết bằng diffoscope, jar tf, unzip

Artifact Plugin chỉ ra file khác; `diffoscope` (nếu được cài) có thể cho biết byte/metadata khác ở đâu. Ví dụ plugin log cung cấp paths tới reference và current main JAR:

```bash
diffoscope \
  target/reference/artifact-compare-lab-1.0.0.jar \
  target/artifact-compare-lab-1.0.0.jar
```

**Đường dẫn `target/reference/...` ở đây là minh họa**, chỉ dùng khi plugin thực tế đã lưu reference ở path đó. Nếu reference nằm trong local repo:

```bash
diffoscope \
  "$HOME/.m2/repository/vn/example/artifact-compare-lab/1.0.0/artifact-compare-lab-1.0.0.jar" \
  target/artifact-compare-lab-1.0.0.jar
```

Lệnh trên cần diffoscope đã cài riêng; Maven Artifact Plugin **không tự cài diffoscope**. Exit code/format báo cáo phụ thuộc công cụ, nhưng nó thường cho thấy sự khác biệt ở ZIP metadata, manifest, generated classes, source line endings hoặc resources.

Không có diffoscope vẫn có thể kiểm:

```bash
jar tf target/artifact-compare-lab-1.0.0.jar
unzip -l target/artifact-compare-lab-1.0.0.jar
unzip -p target/artifact-compare-lab-1.0.0.jar META-INF/MANIFEST.MF
```

`unzip` là công cụ hệ điều hành phải có sẵn hoặc được cài; `jar` có trong JDK. Trên PowerShell có thể dùng `Get-FileHash` hoặc `tar -tf` nếu môi trường hỗ trợ đọc ZIP/JAR.

**Không nhầm thứ tự hiển thị entry với nội dung class.** Digest khác có thể do byte của ZIP headers/timestamps dù unpacked Java bytecode giống; reproducibility byte-for-byte vẫn coi là khác.

## 9. Reference từ remote repository

Khi thư viện đã được publish, kiểm rebuild với artifact tham chiếu từ remote có ý nghĩa hơn so với so hai lần build của cùng một máy.

Ví dụ package GAV đã có trên Maven Central:

```bash
mvn -B clean verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare \
  -Dreference.repo=central
```

**Chỉ có ý nghĩa nếu cùng version/GAV của bản phát hành thực sự tồn tại ở Central.** Project demo `vn.example:artifact-compare-lab:1.0.0` **không tồn tại công khai như một library release hợp lệ**. Với nó, hãy dùng local reference; đừng kỳ vọng Central trả artifact cho coordinates minh họa.

Với private staging repo, plugin cho phép `reference.repo` dưới dạng repository ID, URL hoặc `id::url`. Ví dụ khái niệm:

```bash
mvn -B clean verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare \
  -Dreference.repo=staging::https://repo.example.org/repository/release-candidates/
```

Hostname là placeholder trong **cấu hình minh họa**, không phải endpoint thực. Khi dùng repository có authentication, cấu hình Maven `settings.xml` với `server.id` trùng ID và credentials từ CI secrets. Không hardcode token trên command line có thể bị ghi vào logs/process list.

### 9.1. Những điều phải ghi lại về reference

Một so sánh đáng tin cần nêu:

- Coordinates `groupId:artifactId:version` và extension/classifier.
- Repository ID/URL hoặc đường dẫn reference local.
- Hashes của reference và current artifacts, ít nhất cho main JAR và những attachments thuộc policy.
- Commit/tag source đã build, trạng thái clean/dirty của Git.
- Maven, JDK vendor/major, plugin versions, OS/locale/TZ khi chúng có thể ảnh hưởng.
- Build command, profiles, environment inputs, timestamp property.
- Output `.buildcompare` và CI job ID/dữ liệu lưu để audit.

Nếu reference trong local repository có thể đã bị ghi đè bởi một lần install mới, đó là reference **không còn bất biến**. Với release check độc lập, dùng immutable staging repository, checksums và access control.

## 10. Đưa kiểm tra vào CI

Một pipeline có thể có hai loại job:

**A. Kiểm tra lặp lại trong cùng môi trường** (fast feedback):

```text
checkout immutable commit
  -> pin JDK + Maven + plugin versions
  -> mvn -B clean install
  -> mvn -B clean verify artifact:compare
  -> archive .buildcompare / build logs
```

Với câu lệnh thật, dùng FQ goal:

```bash
mvn -B clean install
mvn -B clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Đây là test cơ bản trên local repo. CI job phải có workspace sạch khi build, không dùng `mvn -fn`, không set `compare.fail=false`. **Bản reference local có thể không độc lập**, nên job này không được quảng bá như third-party verification.

**B. Rebuild độc lập từ release reference** (chặt hơn):

```text
release artifact đã publish ở immutable repository
  -> independent machine/container/runner checkout cùng source tag
  -> pin JDK/Maven/build inputs theo hướng dẫn release
  -> mvn -B clean verify
  -> artifact:compare -Dreference.repo=<staging-or-central>
  -> store diff/buildcompare + attest verifier identity
  -> PASS chỉ khi required artifacts match và reference resolved
```

Đầu vào Maven dependencies/plugins phải được xác định ổn định; tránh SNAPSHOT/versions thay đổi giữa hai setups. Tách quyền publisher và verifier giúp tăng tin cậy cho supply-chain audit.

### 10.1. Artifact comparison không thay các quality gates khác

| Gate | Điều kiểm tra |
| --- | --- |
| Unit/integration tests | Chức năng và assertions |
| Static analysis/SCA | Code quality/vulnerabilities theo tool |
| License/secret scan | Tuân thủ chính sách và thông tin nhạy cảm |
| Maven Artifact Plugin compare | Build output khớp reference theo bytes/fingerprints |
| Signatures/checksums/attestation | Provenance/integrity/signer theo cơ chế |
| Deploy approval | Repo/namespace/version được phép phát hành |

Một JAR có thể reproducible **nhưng chứa lỗi bảo mật**. Ngược lại một chương trình chạy đúng vẫn có thể không reproducible. Cần nhiều cổng chất lượng bổ trợ, không dùng một dòng `BUILD SUCCESS` thay tất cả.

### 10.2. Lưu .buildcompare kể cả khi CI fail

Vì `compare.fail=true` có thể khiến job đỏ, CI phải thu logs và `target/**/*.buildcompare` theo cơ chế `always/finally` của platform. Đối với multi-module, đường glob cần phù hợp shell/CI artifact collector; không chắc mỗi module luôn có file ở cùng path.

Nếu chưa có reference, thất bại resolution không phải **artifact mismatch đã đo được**. CI cần phân loại riêng lỗi network/credentials/repository 401/403/404 và fail gate thay vì coi chúng là pass.

## 11. Multi-module Reactor và aggregator behavior

Xem cấu trúc:

```text
reactor-root/
├── pom.xml              # packaging pom, <modules>
├── core/pom.xml         # JAR
├── api/pom.xml          # JAR, phụ thuộc core
└── reports/pom.xml      # packaging pom, tùy project
```

Reactor build order chịu tác động của dependency graph; root `<modules>` là aggregation, không tự tạo cùng một output file. Mỗi child có `target` và Maven coordinates riêng.

Đối với Maven Artifact Plugin:

- `compare` có thể so per-module và sinh **aggregate result**; tham số `compare.aggregate.only` quyết định chỉ tính ở cuối hay thêm từng module.
- `describe-build-output` là aggregator goal experimental; tài liệu khuyên gọi ở reactor root **sau build** từ CLI, không bind sớm vào phase khi child chưa có output.
- `artifact:buildinfo` trong các bản trước có cách tạo tổng hợp `.buildinfo` ở module cuối; hiện deprecated, không nên cố xây quy trình mới chỉ dựa trên nó.
- `buildinfo.detect.skip` (default true) tìm modules bị skip install/deploy để tránh fingerprints không cần thiết, nhưng có thể cần `buildinfo.skipModules` nếu auto-detection không đúng.
- `buildinfo.ignore` match patterns theo `groupId/filename`; `buildinfo.ignoreJavadoc` mặc định true, nên nếu release yêu cầu Javadoc bit-identical, phải sửa policy và kiểm kết quả thực.
- Không dùng `mvn -T` cho compare nếu plugin không thread-safe, trừ khi xác minh behavior phiên bản riêng. Có thể parallel build ở job khác nhưng comparison stage cần chạy an toàn.

### 11.1. Scope sai có thể cho kết quả xanh giả

Một ví dụ:

```bash
mvn -pl :core -am verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Lệnh này chỉ chọn `core` và các dependencies cần trong reactor, **không** nhất thiết chọn `api` hay tất cả release modules. Nếu goal báo match ở scope đó, kết luận đúng phải là “selected modules match”, không phải “full reactor release match”.

Nếu project có nhiều classifiers `sources`/`javadoc`/`tests`, cần kiểm các attachments được tạo đúng cùng phase/profile như reference; mặc định plugin có thể ignore Javadoc, nên không suy từ compare PASS rằng **mọi** attached file đều match. Một release manifest/list các expected artifacts giúp tránh thiếu item.

## 12. .buildinfo và .buildcompare khác nhau ra sao?

**`.buildinfo`** mô tả metadata và fingerprints của build output; tùy version có thể chứa thông tin OS/JDK/reproducibility context và checksums/files. Tài liệu 3.7.0 đánh dấu goal `buildinfo` **deprecated** vì đây là internal format, khuyên dùng `describe-build-output` hoặc `compare`. Goal compare có thể vẫn tạo/tiêu thụ buildinfo **nội bộ**; deprecated ở đây là lời khuyên không xây workflow mới phụ thuộc một goal riêng lẻ, **không có nghĩa mọi file .buildinfo đều mất tác dụng**.

**`.buildcompare`** là output ghi kết quả so sánh current/reference, ví dụ summary matched/different và các đường dẫn cần điều tra. Đây là file hữu ích cho CI artifact retention và review release.

**`.jar`/`.pom`/`-sources.jar`** mới là artifacts phát hành/kiểm bytes trong ví dụ. Đừng đưa `.buildcompare` vào compile classpath; cũng đừng xem nó thay SHA-256/signature/attestation.

### 12.1. Reproducible buildinfo và ignore options

`buildinfo.reproducible` khi bật có thể giảm chi tiết metadata môi trường (ví dụ OS tổng quát, JVM major) trong buildinfo. **Điều này không làm binary artifact tự reproducible**; nó chỉ thay cách biểu diễn thông tin.

`buildinfo.ignoreJavadoc=true` mặc định có lý do thực tế vì HTML Javadoc có thể chứa khác biệt giữa môi trường, nhưng tác dụng phụ là **mức khẳng định của comparison hẹp hơn toàn bộ release bundle**. Nếu chính sách yêu cầu byte-identical docs, xem plugin help và bật kiểm Javadoc có chủ đích:

```bash
mvn -B clean verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare \
  -Dbuildinfo.ignoreJavadoc=false
```

Lệnh này chỉ nên dùng khi reference thực sự có Javadoc classifier và plugin versions/workflow tạo docs nhất quán. Đừng bật rồi bỏ qua lỗi, hoặc giữ ignore=true mà tuyên bố đã kiểm tất cả.

## 13. Các lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `compare` không tìm được reference | Chưa `install`, sai GAV, repo URL/credentials lỗi | Cài reference local hoặc cấu hình remote đúng |
| Reference bị ghi đè trước khi so | Dùng `clean install compare` trong lần thứ hai | Tách `install` trước đó và `clean verify compare` |
| ZIP/JAR khác khi build lại | Timestamp ZIP entries không được cố định | Đặt `project.build.outputTimestamp`; nâng JAR/Source plugins phù hợp |
| JAR cùng logic nhưng digest khác | Manifest, resource filtering, file order, generated metadata | Dùng diffoscope/unzip, kiểm archive entries |
| Class files khác | JDK/toolchain/compiler flags hoặc generated Java thay đổi | Pin JDK major/vendor, Compiler Plugin và sources |
| `pom.xml` artifact khác | CI-friendly version, release plugin/POM rewrite, thay build instructions | So published POM và POM hiện tại, kiểm release process |
| `check-buildplan` PASS nhưng compare FAIL | Không có known-issue plugin nhưng một generator/environment nondeterministic | Xem .buildcompare/diffoscope và sửa nguyên nhân |
| `compare` PASS khi thiếu Javadoc | Default `buildinfo.ignoreJavadoc=true` | Kiểm policy ignoreJavadoc, expected artifact inventory |
| Compare report chỉ gồm một module | `-pl` chọn subset, skipModules/ignore rules | So scope với release manifest |
| Compare PASS cùng máy nhưng fail ở máy khác | Username/path/locale/JDK/OS newline hoặc dependency differences | Independent rebuild, pin inputs, normalize metadata |
| `compare.fail=false` nên CI vẫn xanh | Flag phục vụ diagnostic, không phải release gate | Bỏ flag, sử dụng default true |
| Plugin prefix `artifact:compare` resolve version lạ | Không pin Maven Artifact Plugin | Dùng FQ goal version 3.7.0 |
| `.buildcompare` không ở path dự đoán | Multi-module aggregate output/layout khác | Đọc plugin log và tìm trong từng target |
| Plugin compare lỗi trên parallel reactor | Goal không thread-safe | Bỏ `-T` hoặc tách stage sequential |
| Source JAR không có trong compare | Source Plugin không attach/không chạy trong profile | Bind `jar-no-fork` trước verify, kiểm installed reference |
| Release 1.0.0 reference là snapshot khác | Repo metadata chọn khác build | So đúng GAV/version, pin dependencies/plugins |
| Compare FAIL do thay source/JDK | Đầu vào khác, không phải bất định cùng inputs | Khôi phục inputs rồi thử reproducibility thực |
| File hash bằng nhau nhưng tests fail | Byte-identical JAR không nói tới correctness | Dùng test/quality gates riêng |

### 13.1. Quy trình điều tra tuần tự

1. In `java -version`, `mvn --version` và các Maven profiles được bật.
2. Kiểm Git commit/dirty state, kiểm POM `project.build.outputTimestamp`.
3. Chạy `artifact:check-buildplan`, xem cảnh báo plugin versions/goals.
4. Tạo reference từ source/tag đã xác định bằng `mvn -B clean install`.
5. Dùng `mvn -B clean verify ...:compare` **không install lại** trước goal.
6. Đọc log compare, phân biệt missing reference và byte mismatch.
7. Mở `.buildcompare` và những filenames current/reference được log nêu.
8. Dùng SHA-256, `jar tf`, `unzip -l` và diffoscope để xác định byte/metadata khác.
9. Sửa plugin phiên bản, timestamp, resource filtering, generated code, line endings hoặc toolchain theo nguyên nhân.
10. Chạy lại cùng source và môi trường đã chốt; sau đó thử **independent rebuild**.
11. Lưu report/build environment provenance cùng commit, reference repository và CI job ID.
12. Giữ `compare.fail=true` trên release gate và không làm ngơ failed/missing artifacts.

## 14. Tình huống minh họa: hai JAR cùng nội dung class nhưng hash khác

Giả sử hai lần build đều tạo `Main.class` và `PriceEngine.class` giống bytes, nhưng một JAR có ZIP entry timestamp `2026-11-10` và JAR kia `2026-11-11`. Khi đó:

```text
Same Java classes and application behavior
              |
              v
Different ZIP metadata bytes
              |
              v
Different JAR SHA-256
              |
              v
artifact:compare -> mismatch (nếu artifact trong scope)
```

Đây là **tình huống giả định**, không phải log thực tế từ project mẫu. Việc dùng `project.build.outputTimestamp` cố định có thể loại một nguyên nhân timestamp không ổn định, nhưng nếu plugin chèn build time vào manifest hoặc file generated resource thì vẫn khác.

Tương tự, hai build có JAR khớp bytes trên cùng máy nhưng nhúng đường dẫn absolute chứa username và cố định trên máy đó có thể **đều khớp local**; máy của verifier khác username thì lệch. Đó là lý do cần thử independent rebuild, không chỉ local compare.

## 15. Câu hỏi tự luyện và đáp án

**Câu 1.** `artifact:check-buildplan` báo không có lỗi thì có chứng minh mọi artifact tái lập không?

**Đáp án:** Không. Goal kiểm execution plan với các vấn đề đã biết của plugin; phải thực sự rebuild và `artifact:compare`.

**Câu 2.** Vì sao hai lệnh đúng là `clean install` rồi `clean verify artifact:compare`?

**Đáp án:** Lần đầu cài reference, lần sau chỉ tạo current output rồi so. Nếu install lần hai trước compare có thể ghi đè reference local.

**Câu 3.** `project.build.outputTimestamp` dùng để làm gì?

**Đáp án:** Giúp những archive plugins có hỗ trợ đặt ZIP/JAR entry timestamps ổn định, tránh dùng thời gian hiện tại vào build output.

**Câu 4.** `artifact:buildinfo` còn được khuyến nghị làm goal chính trong 3.7.0 không?

**Đáp án:** Không. Goal được đánh dấu deprecated/internal; ưu tiên `describe-build-output` hoặc `compare`.

**Câu 5.** Khi `compare.fail=false`, pipeline xanh có chứng minh artifact match không?

**Đáp án:** Không. Flag có thể cho phép workflow tiếp tục khi differences được phát hiện, vì thế phải đọc kết quả và không dùng nó làm release gate.

**Câu 6.** Vì sao `compare` không tự kiểm mọi file trong `target/`?

**Đáp án:** Scope dựa trên Maven artifact outputs/attachments và cấu hình ignore/skip; file tạm không attach không tự thuộc danh sách so.

**Câu 7.** Tại sao so local hai lần PASS chưa đủ xác minh independent reproducibility?

**Đáp án:** Hai lần có thể cùng sử dụng username/path/locale/JDK khác với hệ thống verifier; cần một independent environment và immutable published reference.

**Câu 8.** Nếu Javadoc classifier không được kiểm mặc định, phải xem tham số nào?

**Đáp án:** `buildinfo.ignoreJavadoc`; mặc định true trong Maven Artifact Plugin phiên bản được mô tả.

**Câu 9.** Nếu đổi source giữa reference và current, compare FAIL có chứng minh build không deterministic không?

**Đáp án:** Không, vì đầu vào khác. Nó chỉ chứng minh công cụ phát hiện output khác. Reproducibility yêu cầu cùng source/build instructions/inputs.

**Câu 10.** Plugin `compare` khác `diffoscope` thế nào?

**Đáp án:** Compare xác định match/mismatch giữa Maven artifact families với reference; diffoscope giúp giải thích khác ở metadata/entry/bytes nào.

**Câu 11.** Khi chạy `-pl :core`, có thể tuyên bố toàn reactor release reproducible không?

**Đáp án:** Không. Chỉ so các modules được chọn và các artifacts thuộc phạm vi đó.

**Câu 12.** Làm sao phân biệt compare FAIL vì repo không truy cập được với artifact mismatch?

**Đáp án:** Đọc logs/HTTP/credentials/GAV; chỉ gọi mismatch khi đã truy xuất được reference và so được output. Cả hai có thể là CI failure nhưng nguyên nhân khác nhau.

## 16. Checklist nghiệm thu

- [ ] Xác định GAV/commit/reference repository bất biến và expected artifact inventory.
- [ ] Pin Maven/JDK và plugin/dependency versions; không dùng volatile SNAPSHOT/range ngoài chính sách.
- [ ] Cấu hình `project.build.outputTimestamp` ổn định và kiểm archive plugins có hỗ trợ.
- [ ] Chạy `artifact:check-buildplan`, xử lý known reproducibility issues.
- [ ] Build `clean install` một lần để tạo reference local (hoặc dùng remote release reference).
- [ ] Rebuild cùng inputs bằng `clean verify` rồi `artifact:compare`, **không overwrite reference**.
- [ ] Đối chiếu `.buildcompare`/logs, biết output files nào match/mismatch.
- [ ] Nếu có khác, dùng diffoscope/manifest/ZIP timestamps/class files để khoanh vùng.
- [ ] Không nhầm test detector bằng thay source/timestamp với phép reproducibility thật.
- [ ] Kiểm ignoreJavadoc, skipModules, ignore và các file classifier bắt buộc theo release policy.
- [ ] Trong reactor, so đúng toàn bộ module scope và tránh compare song song thiếu thread-safety.
- [ ] CI lưu reports cả khi fail, giữ `compare.fail=true` trong quality gate.
- [ ] Thử independent rebuild từ source tag và published immutable reference khi cần xác thực supply chain.
- [ ] Duy trì các test/security/attestation gates riêng; byte-for-byte match không có nghĩa phần mềm an toàn.

## 17. Tài liệu chính thức

- [Apache Maven Artifact Plugin — Introduction / Goals](https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html)
- [Artifact Plugin — Usage](https://maven.apache.org/plugins/maven-artifact-plugin/usage.html)
- [Artifact Plugin — compare goal](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html)
- [Artifact Plugin — check-buildplan goal](https://maven.apache.org/plugins/maven-artifact-plugin/check-buildplan-mojo.html)
- [Artifact Plugin — describe-build-output goal](https://maven.apache.org/plugins/maven-artifact-plugin/describe-build-output-mojo.html)
- [Artifact Plugin — buildinfo goal (deprecated)](https://maven.apache.org/plugins/maven-artifact-plugin/buildinfo-mojo.html)
- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven JAR Plugin — Examples / Configuration](https://maven.apache.org/plugins/maven-jar-plugin/examples/attached-jar.html)
- [Maven Source Plugin — jar-no-fork](https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html)
- [Reproducible Builds — Definition and Background](https://reproducible-builds.org/docs/definition/)
