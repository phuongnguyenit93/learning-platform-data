# Phân biệt tái lập môi trường build với tạo artifact giống từng byte

## 1. Hai mục tiêu gần nhau nhưng không giống nhau

Trong dự án Java/Spring Boot, câu nói **“build này đã tái lập được”** có thể mang nhiều nghĩa. Người A muốn đồng nghiệp cài đúng Java, Maven và dependencies để chạy `mvn clean package` thành công. Người B muốn dùng cùng source code, tự build lại ở một máy độc lập và thu được file `.jar` có **mọi byte giống hệt** bản phát hành. Đây là **hai mức bằng chứng khác nhau**.

**Tái lập môi trường build** (*recreating the build environment*) có nghĩa là xác định và tái dựng tương đối chính xác các đầu vào, công cụ và điều kiện thực thi: source revision, JDK, Maven/Gradle, plugin versions, dependency graph, repositories, biến môi trường và các bước build. Nó giúp người khác thực hiện **cùng quy trình**, nhưng kết quả có thể vẫn khác bytes.

**Tạo artifact giống từng byte** (*bit-for-bit/byte-for-byte identical artifact*) có nghĩa hai lần build tạo ra các file được chỉ định có **cùng dãy byte**, tức cùng kích thước, nội dung và SHA-256 (với điều kiện so đúng file). Một kiểm chứng bằng phép so sánh bytes đầy đủ là bằng chứng trực tiếp; SHA-256 là fingerprint thực dụng rất mạnh. Muốn đạt mức này, ngoài tái lập đầu vào phải loại bỏ **nguồn không xác định** (*nondeterminism*) bên trong build: timestamp, thứ tự ZIP entries, path/user/hostname bị nhúng, dữ liệu ngẫu nhiên, generator chạy theo thời gian, binary dependency khác nhau...

Bài thuộc mục **Bản dựng tái lập** của chủ đề **Spring Boot Build Tooling Packaging**. Bạn sẽ biết:

1. Phân biệt môi trường build “giống nhau” với output có bytes giống nhau.
2. Nhận ra những phần tạo ra khác biệt ngay cả khi source, JDK và Maven version khớp.
3. Cấu hình Maven và Spring Boot Maven Plugin để giảm tính bất định của executable JAR.
4. Dùng Java 17 và hai checkout độc lập để kiểm tra artifact raw bytes, không dựa vào cảm giác build “đã thành công”.
5. Hiểu Gradle reproducible archives, toolchains, dependency locking và phạm vi bảo đảm.
6. Chẩn đoán sai khác trong `META-INF/MANIFEST.MF`, `BOOT-INF`, timestamps, dependencies, class files và metadata.
7. Thiết kế CI để **build → so sánh → publish đúng artifact được kiểm chứng**, không vô tình kiểm tra một file rồi phát hành file khác.

**Phạm vi:** trọng tâm là tính tái lập của **JAR/WAR và quy trình build Spring Boot**. OCI image, SBOM, chữ ký số và provenance được nhắc khi chúng ảnh hưởng kết luận, không đồng nhất chúng với checksum của JAR.

## 2. Một thang mức độ bảo đảm hữu ích

| Mức | Điều có thể nói | Ví dụ bằng chứng | Chưa thể kết luận |
| --- | --- | --- | --- |
| 1. Build chạy được | Source build thành công trên một máy | `mvn clean package` trả exit code 0 | Lần build khác cho kết quả tương tự |
| 2. Môi trường có thể tái dựng | Đã khóa và ghi nhận source, tools, dependencies, commands | Git commit, Maven Wrapper/JDK, plugin versions, repository policy | File JAR giống bytes |
| 3. Hành vi sản phẩm tương đương | Hai artifact đều chạy, smoke tests pass | `java -jar`, HTTP/CLI contract | Hai ZIP/JAR giống từng byte |
| 4. Hai artifact giống từng byte | So sánh raw files cho kết quả bằng nhau | `cmp`, `Files.mismatch`, SHA-256 đồng nhất | Các hệ điều hành, JDK hoặc bên thứ ba khác cũng tái tạo được |
| 5. Reproducible build được kiểm chứng độc lập | Bên khác tái tạo từ source, instructions, environment đã nêu và đối chiếu artifact | Hai môi trường thực sự độc lập, cùng checksum/artifact set | Đó là bằng chứng tuyệt đối cho mọi bản build tương lai |

Theo tài liệu Apache Maven, một *reproducible build* là quy trình cho phép tạo lại các bản sao artifact giống bit-by-bit từ **cùng source, build environment và instructions**. Trong thực tế, một phép thử hai lần trên **cùng máy/cùng cache** hữu ích để bắt lỗi timestamp nhưng **chưa chứng minh** môi trường khác độc lập tái tạo được. Vì vậy cần ghi rõ **phạm vi đã kiểm chứng**.

Ba câu sau không tương đương:

- “Hai máy đều có Java 17 và Maven 3.9” → mới khớp một phần môi trường.
- “Hai máy chạy cùng commit, cả hai build xanh” → mới chứng minh hai build thành công.
- “Hai file executable JAR do hai máy build có SHA-256 giống nhau” → có bằng chứng mạnh rằng **đúng file ấy** giống bytes.

Một artifact byte-identical không có nghĩa các chương trình bên trong an toàn hoặc đúng nghiệp vụ. Một lỗi phần mềm có thể được tái tạo chính xác ở cả hai bản. Reproducibility hỗ trợ audit và supply-chain verification, **không thay** kiểm thử, security review hay ký/phát hành artifacts đáng tin.

## 3. Mô hình đầu vào và đầu ra của build

Hãy coi build là một phép biến đổi:

~~~text
SOURCE
  + TOOLCHAIN (JDK, Maven/Gradle, plugins)
  + DEPENDENCIES (binary bytes, repositories)
  + CONFIGURATION (profiles, properties, resource filters)
  + ENVIRONMENT (OS, locale, timezone, path, filesystem)
  + NONDETERMINISTIC INPUTS (clock, random, network)
               |
               v
       build steps / packaging
               |
               v
      class files + resources
               |
               v
     plain JAR / executable JAR / WAR
~~~

Đầu ra **phụ thuộc vào tất cả nguồn được đọc**, không chỉ `src/main/java`. Một generator có thể gọi `Instant.now()`; một plugin có thể lấy user name hoặc đường dẫn checkout; một build script có thể gắn Git dirty-state hoặc runtime-specific hostname vào `build-info.properties`; một ZIP writer có thể lặp qua filesystem theo thứ tự khác nhau.

Hình dung cùng commit nhưng hai lần build:

~~~text
Build A: pom.xml giống, JDK17 giống, Maven giống, runtime libs giống
         archive entry timestamp = 2026-11-09 09:00
Build B: pom.xml giống, JDK17 giống, Maven giống, runtime libs giống
         archive entry timestamp = 2026-11-09 09:05
~~~

Nếu file ZIP entries lưu timestamps khác nhau thì **raw archive bytes khác nhau** dù class Java thực tế hoàn toàn tương tự. Đây là phản ví dụ trực tiếp cho suy luận “cùng môi trường ⇒ cùng checksum”.

Ngược lại, nếu build deterministically ở hai môi trường khác nhau mà output giống bytes, ta có **bằng chứng thực nghiệm mạnh hơn** rằng các khác biệt môi trường đang được kiểm soát hoặc không ảnh hưởng tới artifact.

## 4. Các nguồn bất định phổ biến trong Java/Spring Boot

| Nguồn khác biệt | Biểu hiện trong artifact | Biện pháp |
| --- | --- | --- |
| ZIP/JAR entry timestamps | Same entries nhưng archive SHA-256 khác | Đặt reproducible output timestamp hoặc bỏ preserve source timestamps |
| Thứ tự ZIP entries | Danh sách hoặc vị trí entries thay đổi | Sử dụng plugin/tác vụ có deterministic file order |
| Build date trong file sinh ra | `build.time`, manifest, Git properties khác | Dùng thời điểm cố định theo revision, hoặc bỏ build-time field |
| UUID/random number | Tên resource hoặc metadata mỗi lần khác | Cấp seed cố định khi có lý do, tránh random trong artifacts |
| Absolute build path | Generated source/metadata nhúng `/home/a/...` vs `C:\work\...` | Dùng relative paths, kiểm soát generator/debug metadata |
| Username/hostname | Metadata chứa người build hoặc tên máy | Không nhúng hoặc chỉ nhúng dữ liệu ổn định của source |
| Locale/timezone/encoding | Properties, resource filtering hoặc format khác | Charset xác định, normalization, không lấy locale mặc định tùy tiện |
| JDK/compiler khác | Bytecode, debug info, ordering hoặc jar tooling khác | Toolchain được ghi nhận, thử trên đúng JDK/version/vendor khi cần |
| Snapshot/range/dynamic deps | Dependency binaries khác dù POM/source không đổi | Pin versions, loại ranges/SNAPSHOT với release; kiểm soát repositories |
| Plugin/task versions thay đổi | JAR layout, manifest, compression behavior khác | Quản lý plugin versions và build tool Wrapper |
| ZIP compression/extra fields | Cùng entry contents nhưng raw ZIP khác | Pin archiver/library/plugin; hiểu byte-level packaging |
| File permissions/line endings | Resource contents thay đổi theo OS checkout | `.gitattributes`, normalization, fixed modes khi phù hợp |
| Parallel task order | Generated lists/services files khác thứ tự | Sort explicit, không dựa vào HashMap/filesystem traversal |
| Mutable external service | Download code/data mới hoặc file từ endpoint mạng | Biến external inputs thành versioned, verified dependencies |

Hai artifact có thể chứa **cùng classes/resources có ý nghĩa** nhưng raw ZIP bytes khác vì entry metadata hoặc compression. Cần phân biệt **semantic equivalence** với **byte identity**. Nếu yêu cầu là supply-chain reproducibility, không được tự “bỏ qua mấy byte timestamp” rồi báo byte-identical.

## 5. Chốt môi trường build: điều kiện cần, chưa phải kết quả

### 5.1. Đầu vào tối thiểu nên ghi nhận

Một build record có thể gồm:

~~~text
Git revision         : commit SHA của source được build
Working tree         : clean / uncommitted changes?
JDK                  : vendor, feature, patch, architecture
Maven/Gradle         : Wrapper distribution + checksum
Build plugins        : versions; effective POM hoặc Gradle scripts
Dependencies         : resolved coordinates và actual artifact hashes
Repositories         : trusted source, mirrors, immutable policy
Build command        : clean package / bootJar, profiles, skip flags
Environment          : OS/arch, locale, timezone, file encoding
Output artifact      : path, filename, SHA-256
Build time source    : fixed timestamp hoặc SOURCE_DATE_EPOCH policy
~~~

Các thông tin này giúp **tái lập môi trường và lần theo nguyên nhân**. Nhưng việc có một file record đầy đủ không tự làm cho plugin/generated code deterministic.

### 5.2. Maven Wrapper và JDK

Maven Wrapper như `./mvnw`/`mvnw.cmd` giúp project sử dụng phiên bản Maven distribution được khai báo. Tuy nhiên nó **không tự khóa JDK**; Maven thường chạy bằng Java theo môi trường máy, trừ khi có configuration/toolchains hoặc container image được quản lý.

Kiểm tra:

~~~bash
./mvnw -version
java -version
git rev-parse HEAD
git status --short
~~~

Trong Windows PowerShell, dùng `.\mvnw.cmd -version` nếu repo có Wrapper. Nếu project không có Maven Wrapper, dùng `mvn -version` và ghi lại Maven version. Đừng cố chạy `./mvnw` trong project không có script ấy.

JDK version chính cũng chưa đủ cho mọi yêu cầu byte identity: compiler patch/vendor và platform-dependent tools/generators có thể tác động output. Với release nhạy cảm, pin toolchain/environment đủ cụ thể và so checksum trong các môi trường dự kiến.

### 5.3. Dependencies và repositories

Trong Maven, quản lý `<dependencyManagement>`/BOM giúp khóa versions; vẫn cần tránh version ranges, `-SNAPSHOT` có thể thay nội dung và plugin resolve không kiểm soát. Một Maven coordinate **không tự chứng minh** binary bytes bất biến nếu repository cho phép ghi đè. Với reproducibility mạnh, kiểm tra cả integrity của resolved artifacts và repository policy.

Trong Gradle, có thể dùng version catalogs, dependency locking và dependency verification. Chúng giải quyết **những nhiệm vụ khác nhau**: catalog quản lý versions được khai báo, locking giữ resolved versions, còn verification kiểm tra checksum/signature đã khai báo. Không nên nói “đã có `gradle.lockfile` nên mọi JAR download đều chắc chắn giống bytes” nếu không kiểm tra binary integrity và môi trường network.

## 6. Maven: cấu hình reproducible archive timestamp

### 6.1. project.build.outputTimestamp

Apache Maven hướng dẫn đặt property `project.build.outputTimestamp` để các Maven plugins tương thích sử dụng một **timestamp xác định**, thay vì thời gian hiện tại khi tạo archive entries:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Giá trị trên là ISO 8601 **cố định cho ví dụ**, không phải đề nghị mọi bản phát hành vĩnh viễn mang thời gian 2024. Với release pipeline, nên chọn giá trị ổn định theo source/release commit và giữ nguyên giữa mọi lần tái build **cùng revision**.

Spring Boot Maven Plugin `repackage` có parameter `outputTimestamp` với default là property `project.build.outputTimestamp`. Maven JAR Plugin và các plugin đóng gói tương thích khác cũng có cơ chế tương tự. Điều đó giúp giảm nguồn khác nhau từ timestamps của **archive entries**.

**Điều không được suy ra:** chỉ thêm một property là bảo đảm SHA-256 luôn giống nhau. Nếu một task tự ghi `build-number=Instant.now()` vào resource, property của archive writer **không tự sửa nội dung resource**. Nếu runtime JAR dependencies khác bytes, executable Boot JAR vẫn khác.

Theo tài liệu Maven hiện hành, Maven 3.10+/4.0-beta mới có thêm hành vi reproducible mode mặc định. Không dựa vào mặc định đó cho mọi bản Maven cũ; cách rõ ràng nhất trong ví dụ học tập là **khai báo timestamp** và kiểm tra thực tế.

### 6.2. SOURCE_DATE_EPOCH và thời gian của nguồn

`SOURCE_DATE_EPOCH` là chuẩn biến môi trường truyền **Unix timestamp (giây kể từ 1970-01-01 UTC)** được suy ra ổn định từ source hoặc quá trình release; các tool có hỗ trợ có thể dùng nó thay đồng hồ wall-clock.

Ví dụ POSIX shell, khi build từ Git commit đã chốt:

~~~bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
printf 'SOURCE_DATE_EPOCH=%s\n' "$SOURCE_DATE_EPOCH"
~~~

Đây là một lựa chọn khi project/toolchain **thực sự hỗ trợ đọc biến ấy**. Không coi `SOURCE_DATE_EPOCH` là công tắc thần kỳ kiểm soát mọi Maven/Gradle plugin; kiểm tra parameter, version và output. Bạn có thể chuyển nó vào POM bằng một property được resolve rõ ràng nếu policy release yêu cầu.

**Tránh:** `<project.build.outputTimestamp>now</project.build.outputTimestamp>`, timestamp đổi theo mỗi build, hoặc dùng giá trị từ hệ thống CI không ổn định giữa hai lần tái build. Đồng hồ của máy ảo/container cùng giờ vẫn không đủ; build kéo dài khác nhau có thể tạo timestamps khác nếu code gọi giờ tại nhiều giai đoạn.

### 6.3. Metadata Spring Boot build-info

Spring Boot Maven Plugin có goal `build-info` tạo `META-INF/build-info.properties`; trường `build.time` cũng là **nội dung bên trong artifact**. Với plugin có hỗ trợ, tham số `time` dùng `project.build.outputTimestamp` theo mặc định, hoặc thời điểm session start khi không đặt. Nếu bạn cấu hình goal `build-info` hay thêm custom generated metadata, hãy xem **file output thật** và cấu hình version hiện tại.

Mặt khác, không nên xóa metadata build chỉ vì thấy hash khác mà chưa hiểu dữ liệu đó dùng để audit/rollback. Có thể thay wall-clock bằng source commit timestamp, hoặc đưa thông tin release vào hệ thống provenance **ngoài** artifact nếu hợp đồng triển khai cho phép.

## 7. Thực hành hoàn chỉnh: Spring Boot executable JAR có timestamp cố định

Ví dụ Java 17+ dưới đây tạo một CLI Spring Boot application nhỏ. Không có web server hay database để yếu tố ngoài không làm nhiễu phép so sánh.

### 7.1. Cấu trúc thư mục

~~~text
repro-demo/
  pom.xml
  CompareArtifacts.java
  src/
    main/
      java/
        demo/
          Application.java
~~~

`CompareArtifacts.java` là công cụ QA **độc lập ở root**, không nằm trong `src/main/java`. Maven chỉ compile ứng dụng trong thư mục source bình thường.

### 7.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>repro-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích từng quyết định:**

- Parent Boot `3.3.5` quản lý dependency/plugin configuration, nên bản ví dụ dùng một bộ phiên bản có chủ đích.
- `java.version=17` đặt Java compile target theo Spring Boot parent.
- `project.build.sourceEncoding=UTF-8` kiểm soát encoding cho các plugin/source processing có hỗ trợ.
- `project.build.outputTimestamp` cố định thời gian entries cho Maven JAR Plugin và Boot repackage khi plugin hỗ trợ parameter ấy.
- Maven JAR Plugin `3.4.2` được khai báo rõ để khả năng xử lý timestamp không phụ thuộc việc Maven global defaults thay đổi.
- `spring-boot-maven-plugin` được parent quản lý version; việc khai báo plugin khiến goal `repackage` tham gia package lifecycle theo parent.
- Chúng ta **không** thêm `build-info` goal hoặc generated file chứa timestamp ngẫu nhiên; đây là ví dụ cô lập vấn đề archive bytes.

Với project không dùng Boot parent, cần bind `repackage` và quản lý versions độc lập; không giả định bất kỳ POM chứa Boot dependency cũng tạo executable JAR.

### 7.3. Application.java đầy đủ

Tạo `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args -> System.out.println("repro-demo:ok");
    }
}
~~~

Build từ root:

~~~bash
mvn clean package
java -jar target/repro-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Nếu dự án có Maven Wrapper, có thể thay `mvn` bằng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (PowerShell). **Chính ứng dụng** in ra:

~~~text
repro-demo:ok
~~~

Lệnh Maven có logs riêng; cách chạy Java trên không khẳng định checksum của archive. Nó chỉ chứng minh **artifact có khả năng chạy**. Câu hỏi tiếp theo của bài này là: cùng commit có thể tạo lại **chính những bytes đó** không?

## 8. Đo byte identity bằng Java 17, không chỉ so file size

Tạo file độc lập `CompareArtifacts.java` ở root project:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareArtifacts {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java CompareArtifacts.java <artifact-a> <artifact-b>");
        }

        Path left = Path.of(args[0]);
        Path right = Path.of(args[1]);

        if (!Files.isRegularFile(left) || !Files.isRegularFile(right)) {
            throw new IllegalArgumentException(
                    "Both artifact paths must be regular files");
        }

        long mismatch = Files.mismatch(left, right);

        if (mismatch == -1L) {
            System.out.println("artifact.byte_identical=true");
        } else {
            System.out.println("artifact.byte_identical=false");
            System.out.println("first.mismatch.offset=" + mismatch);
            System.exit(1);
        }
    }
}
~~~

`Files.mismatch` (có từ Java 12, nên chạy được trên Java 17) so sánh **bytes** của hai file và trả `-1` khi giống nhau, hoặc offset của byte đầu tiên khác. Chương trình trả exit code khác `0` khi khác nhau, phù hợp làm chốt chặn CI.

Giả sử bạn đã tạo hai artifact theo mục 9, chạy:

~~~bash
java CompareArtifacts.java path/to/build-a.jar path/to/build-b.jar
~~~

**Khi hai file giống từng byte, stdout chính xác** là:

~~~text
artifact.byte_identical=true
~~~

Khi khác, chương trình in `artifact.byte_identical=false` và `first.mismatch.offset=<số vị trí thực tế>`, rồi trả exit code `1`. Vị trí khác đầu tiên phụ thuộc hai file thật, nên **không** cung cấp một offset giả như thể đã chạy build.

Nếu cần fingerprint để lưu trong báo cáo, POSIX shell có thể dùng:

~~~bash
sha256sum path/to/build-a.jar path/to/build-b.jar
~~~

Trong Windows PowerShell:

~~~powershell
Get-FileHash .\path\to\build-a.jar -Algorithm SHA256
Get-FileHash .\path\to\build-b.jar -Algorithm SHA256
~~~

So sánh digest, **không** so text đường dẫn. Nếu hai file byte-identical, SHA-256 sẽ bằng nhau. Nếu SHA-256 bằng nhau, trong thực tế đây là bằng chứng xác minh cực mạnh; còn `Files.mismatch` trực tiếp kiểm tra từng byte của hai file hiện có.

**Cần phân biệt** so sánh hai executable JARs với so sánh source classes. Khi Boot repackage, file ZIP/JAR có thể chứa class files giống nhau nhưng timestamps, nested library archives, manifest/ZIP extra fields hoặc compression khác khiến raw artifact không giống.

## 9. Hai lần build sạch từ hai checkout độc lập

### 9.1. Vì sao không build hai lần trên cùng target?

Nếu chạy `mvn package` hai lần không clean, plugin có thể reuse output cũ hoặc bỏ qua tác vụ; checksum bằng nhau khi ấy **chưa cho thấy build mới có tính xác định**. Ngay cả `mvn clean package` hai lần trong cùng thư mục vẫn dùng chung user home, cache, path, JDK và OS.

Cách kiểm tra tốt hơn cho bước đầu là build **cùng Git commit trong hai checkout khác nhau**, mỗi checkout `clean` trước, rồi so file **theo tên chính xác**. Điều này giúp phát hiện khác biệt do absolute checkout path, file order và generated metadata.

### 9.2. Ví dụ shell POSIX với Git repo đã commit đầy đủ

Giả sử project ở root của một Git repository, `pom.xml` và source đã commit; máy có `git`, `mktemp`, `mvn`, JDK 17 và dependencies có thể tải về.

~~~bash
set -eu

commit=$(git rev-parse HEAD)
work=$(mktemp -d)

git clone --quiet . "$work/build-a"
git clone --quiet . "$work/build-b"

(
  cd "$work/build-a"
  git checkout --quiet "$commit"
  mvn -B -ntp clean package
)
(
  cd "$work/build-b"
  git checkout --quiet "$commit"
  mvn -B -ntp clean package
)

a="$work/build-a/target/repro-demo-1.0.0.jar"
b="$work/build-b/target/repro-demo-1.0.0.jar"

cmp "$a" "$b"
sha256sum "$a" "$b"
~~~

Đây là một **script ví dụ đầy đủ từ repo đã commit**, không phải khẳng định code đã được chạy trong môi trường người học. Nếu `git clone .` không khả dụng do chính sách repo, có thể tạo hai checkout bằng cơ chế tương đương, miễn **cùng revision, cùng đầu vào và không dùng artifact cũ**.

Ý nghĩa của các bước:

- `git rev-parse HEAD` chốt revision, tránh build nhầm hai commits.
- `mktemp -d` tạo nơi làm việc riêng cho phép thử.
- Hai `git clone` tạo working trees khác nhau, giúp lộ những absolute paths được nhúng.
- `mvn -B -ntp clean package` tạo archive từ build sạch, không dựa vào output thư mục cũ.
- `cmp` trả exit code `0` nếu raw files bằng nhau. Nếu `cmp` fail, `set -e` khiến script dừng trước lệnh SHA-256 cuối; khi chẩn đoán lỗi nên chạy riêng hash ở cả hai file.
- Lệnh `sha256sum` cho fingerprint (nếu chạy tới đây).

**Giới hạn của phép thử này:** hai checkout trên cùng máy vẫn có thể dùng **cùng JDK, Maven installation, home repository/cache và OS**. Nếu PASS, bạn có một **same-host independent-checkout check**, không phải một bằng chứng tái tạo độc lập xuyên máy.

Nếu project là Maven multi-module, đường dẫn artifact nằm trong module tương ứng (ví dụ `service/target/...jar`), không nhất thiết ở root. Trong release pipeline, phải đo cả **artifact set** được phát hành, không chỉ chọn một file may mắn giống.

### 9.3. Hai môi trường thực sự độc lập

Bước nâng cao là tạo hai builds trên **hai clean workers/containers hoặc hai máy**, từ cùng commit và được cung cấp build instructions đầy đủ. Ghi:

- Git commit, patch/working-tree state.
- JDK vendor/feature/patch, Maven/Gradle distribution/version và plugins.
- Dependency artifact digests hoặc repository snapshot đã xác minh.
- Build command, profiles, OS/arch, locale/timezone, environment variables.
- Path của từng artifact và SHA-256.
- Sự khác nhau giữa hai môi trường có thể ảnh hưởng output.

Đóng băng môi trường bằng container image **pin theo digest** giúp tái dựng công cụ, nhưng một tag như `maven:latest` có thể trỏ tới bytes mới ở lần sau. Image digest không tự làm codegen, network và timestamps deterministic; đây vẫn là **một kiểm soát đầu vào**.

Một kết quả PASS ở hai độc lập setups có giá trị hơn một lần build lại trên cùng máy, nhưng phạm vi chứng minh vẫn là **những artifact cụ thể và điều kiện cụ thể được kiểm thử**.

## 10. Đọc artifact khi checksum không giống

Khi `Files.mismatch` hoặc `cmp` cho FAIL, **không** xóa metadata hay chỉnh ngẫu nhiên timestamp ngay. Hãy phân loại sai khác:

1. **Files khác cả nội dung classes/resources?** So sánh entries trong archive, decompile/debug khi cần.
2. **Entry names cùng nhưng ordering khác?** Kiểm tra cách tạo ZIP entries và plugin version.
3. **Entry bytes bằng nhau nhưng timestamp/extra fields khác?** Cần normalized archive timestamps và công cụ ZIP deterministic.
4. **`META-INF/MANIFEST.MF` khác?** Xem Build-Jdk, Build-By, implementation metadata hoặc generated attributes.
5. **`META-INF/build-info.properties`/`git.properties` khác?** Kiểm tra build time, source revision, dirty flag, env-derived values.
6. **`BOOT-INF/lib` khác?** Xem dependency graph và hash của nested JAR, snapshot/range/version.
7. **Binary ZIP vẫn khác dù uncompressed entries/metadata giống?** Có thể do compression level/implementation, ZIP extra attributes, comments, signatures hoặc order của local/central directory; cần công cụ phù hợp để inspect.

### 10.1. Kiểm tra manifest và entries

Từ JDK:

~~~bash
jar tf target/repro-demo-1.0.0.jar
~~~

Nếu có `unzip` trên Linux/macOS:

~~~bash
unzip -p target/repro-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

Spring Boot 3.3 JAR bình thường có `BOOT-INF/classes`, `BOOT-INF/lib` và Boot loader, nhưng không cần hardcode mọi entry name/order cho các version khác nhau.

Quan sát archive metadata cũng quan trọng: `jar tf` chỉ liệt kê tên entry, **không** chứng minh timestamps hoặc compressed ZIP bytes giống. Có thể dùng `unzip -v`/`zipinfo` nếu môi trường cài, hoặc một Java ZIP-inspection program khi cần kiểm chứng cross-platform.

### 10.2. Cùng nội dung entry chưa đủ cho raw byte identity

Ví dụ hai archive đều có:

~~~text
BOOT-INF/classes/demo/Application.class
BOOT-INF/lib/spring-core-x.y.z.jar
META-INF/MANIFEST.MF
~~~

và bytes **sau giải nén từng entry** giống nhau. Dù vậy, ZIP central directory, timestamps, order và compression metadata có thể khác → raw JAR SHA-256 khác. Nếu mục tiêu là “byte-for-byte reproducible JAR”, không được hạ tiêu chí thành “entry contents equal” rồi báo PASS.

Nhưng entry-level comparison vẫn rất hữu ích để định vị lỗi: nếu một class khác, xem compiler/generator; nếu chỉ ZIP metadata khác, tập trung vào archiver/plugin. **Đừng tự normalize artifact sau khi phát hành rồi so hash bản normalized**, vì khi ấy bạn không còn đang kiểm tra chính bytes người dùng tải.

### 10.3. Nested dependencies của Spring Boot

Spring Boot Maven Plugin `repackage` đóng gói dependencies vào `BOOT-INF/lib`. Nếu phụ thuộc runtime có cùng Maven coordinates nhưng bytes bị repository sửa, executable JAR cũng không thể byte-identical.

Để kiểm tra:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Một project phụ thuộc transitive libraries và các Maven plugins khác; cần xác nhận resolved versions **và actual binary contents**, không chỉ nhìn `pom.xml`. Không tự xóa local Maven cache để “sửa” checksum nếu chưa xác định repository có nguồn đáng tin, vì hành động đó có thể làm môi trường mất kiểm soát hơn.

## 11. Gradle: deterministic archives khác việc khóa toolchain

Gradle có các thuộc tính trên `AbstractArchiveTask`:

- `preserveFileTimestamps`: khi `false`, archive tasks không giữ timestamps gốc khác nhau của files.
- `reproducibleFileOrder`: khi `true`, thứ tự duyệt files được làm deterministic.

**Từ Gradle 9.0**, các archive tasks như `Jar`, `Zip`, `War`, `Ear` và `Tar` có mặc định reproducible: timestamps được cố định và file order deterministic. Với Gradle 8.x hoặc project vẫn cần tương thích bản cũ, có thể khai báo rõ ràng trong `build.gradle` (Groovy DSL):

~~~groovy
tasks.withType(
        org.gradle.api.tasks.bundling.AbstractArchiveTask
).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Đoạn này là **fragment đặt trong Gradle project đã có plugin/task**, không phải một `build.gradle` hoàn chỉnh. Với Spring Boot Gradle plugin, cần kiểm tra output **của `bootJar`** (và `bootWar` nếu dùng WAR) thay vì chỉ kiểm tra plain `jar`.

Một project nên dùng Gradle Wrapper cho reproducible tool version:

~~~bash
./gradlew --version
./gradlew clean bootJar
~~~

Nếu project không có Wrapper, phải ghi lại Gradle version dùng thật và tạo Wrapper theo quy trình được cấp quyền. **Gradle Wrapper không tự bảo đảm JVM mà build process và toolchain đang dùng**.

Gradle Java Toolchains giúp chọn ngôn ngữ và compiler:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Fragment này cần đặt trong project đã áp Java plugin. Toolchain giúp giảm việc build tùy tiện bằng `JAVA_HOME`, nhưng nếu yêu cầu byte identity nghiêm ngặt thì còn phải xem JDK vendor/patch và các tool ngoài JVM.

### 11.1. Dependency locking và verification

Một Gradle project có thể cấu hình:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Và tạo/cập nhật lock state có chủ đích bằng command phù hợp project:

~~~bash
./gradlew dependencies --write-locks
~~~

Locking nhằm cố định **resolved versions** đã ghi; dependency verification quản lý integrity/trust của artifacts được tải. Cả hai bổ sung cho nhau. Không kết luận rằng chỉ thêm `lockAllConfigurations()` rồi chưa commit lockfiles là đủ tái lập dependencies.

### 11.2. Spring Boot Gradle Plugin không phải Maven plugin

Maven dùng `project.build.outputTimestamp` kết hợp các plugins. Gradle sử dụng task properties riêng; không copy một `<properties>` XML từ Maven sang Gradle và mong `bootJar` áp dụng. Điều cần so là **output thật `build/libs/*.jar`**, với đúng Gradle/Spring Boot Plugin versions và các generated resources.

## 12. Đừng nhầm JAR reproducibility với container-image reproducibility

Một Docker/OCI image chứa nhiều thứ ngoài JAR:

~~~text
OCI image
  - base OS/runtime image layers
  - JRE/JDK files
  - application JAR or exploded layers
  - filesystem metadata, permissions, timestamps
  - image config, environment, entrypoint, labels
  - image manifest/layer-compression metadata
~~~

Do đó:

- **JAR SHA-256 bằng nhau** không tự làm OCI image digest bằng nhau.
- Hai image digests khác nhau không tự chứng minh file JAR bên trong khác.
- Pin `FROM ...@sha256:...` là kiểm soát base image input; vẫn phải quản lý timestamps, builder/plugins, buildpacks, metadata và compression của image.
- `spring-boot:build-image` và Spring Boot layered JAR phục vụ một bài toán có liên quan nhưng **khác** với Maven `jar/repackage` raw checksum.
- `build-info`, SBOM, attestations và chữ ký thường có nhiệm vụ ghi provenance/phát hành; nếu metadata thay đổi hoặc signature chứa thời gian/ngẫu nhiên, cần định nghĩa **tập artifact nào phải byte-identical**, và metadata nào nên được tạo/tin cậy riêng.

Một chiến lược thực dụng: kiểm chứng SHA-256 **executable JAR** trước, sau đó kiểm chứng **image runtime và image digest** theo tiêu chí của pipeline, không gộp cả hai thành một boolean không giải thích.

## 13. CI: tách build repeatability, byte identity và release verification

Một pipeline rõ ràng có thể chia ba mục tiêu:

~~~text
A. Recreate inputs
   - checkout đúng revision
   - set toolchain/Wrapper/repositories/profiles
   - pin dependency versions, validate integrity
                |
                v
B. Verify deterministic artifact
   - clean build A
   - clean build B độc lập phù hợp
   - SHA-256 / Files.mismatch trên đúng JAR/WAR
   - inspect/diff nếu FAIL
                |
                v
C. Publish exactly verified bytes
   - archive artifact A + checksum
   - không rebuild rồi lặng lẽ upload artifact B
   - promote same artifact to repository/image/deploy
                |
                v
D. Runtime smoke tests & security controls
~~~

Nếu mục tiêu chỉ là tăng độ tin cậy developer onboarding, bước A có thể đủ để người khác chạy build; nếu mục tiêu là **independent reproducibility verification** cho release/supply chain, phải hoàn thành B với môi trường độc lập, cùng source/inputs và đối chiếu output.

**Không gắn nhãn “reproducible” chỉ vì Maven cache hit hoặc Gradle task `UP-TO-DATE`.** Cache reuse có thể trả lại đúng bytes nhưng không chứng minh generator sẽ tạo lại giống. Phép thử nên có ít nhất một *real clean rebuild*, và nếu kiểm chứng sâu thì tách caches/workspaces/hệ thống phù hợp.

### 13.1. Gắn trạng thái rõ ràng trong pipeline

| Kết quả | Diễn giải đúng |
| --- | --- |
| Build A và B thành công, hashes khác | Môi trường chạy được; byte reproducibility **FAIL** theo phạm vi thử |
| Build A và B hashes bằng nhau trên cùng máy | Byte identity **PASS trong phép thử same-host**; chưa chứng minh cross-host |
| Build độc lập có hashes bằng nhau, artifact set đúng | Bằng chứng mạnh cho reproducible build trong phạm vi đã mô tả |
| Cùng hash JAR nhưng image digest khác | Cần điều tra image layer/config/builder, không kết luận lỗi JAR |
| Raw JAR hash khác nhưng smoke tests đều PASS | Functional smoke **PASS**, byte identity **FAIL** |
| Maven Wrapper và JDK pin, chưa so artifacts | Environment preparation **PASS**, artifact reproducibility **UNKNOWN** |

### 13.2. Các đầu ra cần lưu

Trong release record, có ích khi lưu:

- Git commit và clean working-tree status.
- Effective tool versions, build profile, reproducibility timestamp policy.
- Paths của artifact thực tế, SHA-256, sizes, classifiers.
- Kết quả byte comparison của hai builds (PASS/FAIL) và môi trường đối chiếu.
- Logs/ZIP diff report khi FAIL.
- Release artifact **đã được kiểm chứng**, provenance/signature và cách deploy.

Không nên lưu passwords, tokens hoặc mọi environment variable vào log public chỉ để “replay build”. Reproducibility không đòi tiết lộ bí mật; build cần phân tách secrets, sử dụng dependencies đã được cung cấp theo cơ chế kiểm soát.

## 14. Câu hỏi thường gặp và lỗi xử lý sai

| Tình huống | Suy luận sai | Cách xử lý đúng |
| --- | --- | --- |
| Hai developer đều có Maven 3.9/JDK17 | “JAR chắc chắn giống SHA-256” | Kiểm tra actual versions/dependencies, timestamp, và so JAR bytes |
| `mvn clean package` xanh cả hai máy | “Đã chứng minh reproducible build” | So artifact bytes; lưu phạm vi môi trường đã thử |
| Hash khác đúng một số ZIP metadata | “Chỉ có timestamp nên coi như PASS” | Với yêu cầu byte identity, vẫn **FAIL**; sửa archive writer |
| Hash giống sau hai lần `mvn package` không clean | “Compiler chạy lại giống hệt” | Clean builds, independent checkouts, xem cache/up-to-date |
| `project.build.outputTimestamp` đã đặt | “Mọi plugin dùng timestamp đó” | Kiểm tra plugin support, generated files và output thực tế |
| Tên dependencies cùng version | “Binary chắc chắn y hệt” | Xác minh repository immutability/checksums |
| Diff chỉ có `META-INF/build-info.properties` | “Bỏ luôn mọi build metadata” | Xác định trường biến đổi, pin time/commit hoặc tách provenance có chủ đích |
| Hash JAR giống, Docker image khác | “JAR không reproducible” | So raw JAR riêng; inspect OCI layers/config |
| Same-host comparison PASS | “Bên thứ ba tái tạo được từ release source” | Tái build độc lập với môi trường/đầu vào được mô tả |
| Compile Java17 bằng hai JDK vendors | “Bytecode chắc chắn đồng nhất” | Test thực tế, pin JDK/tools đủ cụ thể khi cần |
| Có Gradle dependency lock | “Mọi dependency artifact an toàn, bất biến” | Bổ sung integrity verification và repository policy |
| `java -jar` chạy tốt | “Build đã bit-for-bit reproducible” | Chạy smoke cho hành vi và compare bytes cho reproducibility **riêng** |

## 15. Checklist thực hành

1. **Xác định đối tượng so sánh**: executable JAR, WAR, sources JAR, docs JAR, hay OCI image? Ghi artifact set rõ.
2. **Chốt source revision** và loại working-tree changes ngoài ý muốn.
3. **Khóa toolchain**: Maven/Gradle Wrapper, JDK version/vendor phù hợp, plugin versions và build commands.
4. **Kiểm soát dependencies**: versions, snapshot/ranges, repository immutability và binary integrity.
5. **Đặt time policy**: Maven `project.build.outputTimestamp` hoặc `SOURCE_DATE_EPOCH` khi tool hỗ trợ; Gradle archive timestamps/ordering.
6. **Loại bỏ generated data bất định**: current time, random IDs, absolute paths, locale-dependent output, unordered collections.
7. **Build sạch hai lần** từ cùng source ở hai checkout độc lập; khi cần bảo đảm cao, dùng hai workers/environments tách biệt.
8. **So raw files**: `Files.mismatch`/`cmp` và SHA-256; không nhầm JAR contents với raw ZIP bytes.
9. **Nếu mismatch**, tìm entry/metadata khác, kiểm tra manifest/build-info, file ordering, embedded dependencies, compression và generator.
10. **Không làm yếu điều kiện PASS** bằng cách normalize artifact chỉ sau khi release mà không kiểm tra bytes thật.
11. **Lưu scope kết luận**: same-machine, same-container, cross-host, cross-OS hay independent rebuild.
12. **Publish đúng artifact đã kiểm chứng**, không rebuild lại trước deploy nếu không kiểm tra lần nữa.
13. **Tiếp tục runtime/security tests**: byte identity không thay thế chất lượng hành vi hay an toàn.

### Tự kiểm tra

**A.** Hai máy đều chạy Java17, Maven 3.9, cùng Git commit và build xanh. Đã chứng minh JAR giống bytes chưa?

**Trả lời:** Chưa. Có thể khác timestamp, plugin, resolved binaries, generated metadata, OS/locale hoặc ordering. Cần so chính các artifact.

**B.** Hai executable JAR có cùng danh sách classes và resources, nhưng ZIP entry timestamps khác. Byte-identical không?

**Trả lời:** Không. Raw archive chứa metadata, nên SHA-256 có thể khác dù nội dung entries sau giải nén giống nhau.

**C.** Cấu hình `project.build.outputTimestamp` giải quyết điều gì, và chưa giải quyết điều gì?

**Trả lời:** Nó giúp những Maven plugins hỗ trợ dùng timestamp xác định cho output archives. Nó **không** tự khóa JDK, dependency binaries, random generators hoặc mọi file metadata tự sinh.

**D.** Hai lần build cùng checkout nhưng task trả cache hit và hashes bằng nhau. Đã kiểm chứng independent reproducibility chưa?

**Trả lời:** Chưa. Cần clean/rebuild thực, tách workspace và lý tưởng có kiểm tra từ môi trường độc lập.

**E.** Một ứng dụng có SHA-256 JAR giống nhau nhưng `java -jar` lỗi ở production. Kết luận?

**Trả lời:** Byte identity có thể PASS, nhưng runtime compatibility, profile, JDK, permissions, network hoặc dependencies ngoài vẫn cần kiểm tra. Reproducibility không bằng runtime correctness.

**F.** Gradle 9 có default archive reproducibility. Có chắc mọi Spring Boot output đều byte-identical?

**Trả lời:** Không. Archive task defaults chỉ kiểm soát những thuộc tính nhất định của archive; custom generators, dependencies, JDK và Spring Boot tasks vẫn phải được kiểm tra qua output thực.

## 16. Tài liệu chính thức

- Maven — Configuring for Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Spring Boot Maven Plugin — Packaging Executable Archives, outputTimestamp: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot Maven Plugin — build-info time: https://docs.spring.io/spring-boot/maven-plugin/build-info.html
- Gradle — Working with Files, Reproducible Archives: https://docs.gradle.org/current/userguide/working_with_files.html#sec:reproducible_archives
- Gradle — AbstractArchiveTask DSL: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html
- Gradle — Best Practices for Security / Reproducible Artifacts: https://docs.gradle.org/current/userguide/best_practices_security.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Reproducible Builds — SOURCE_DATE_EPOCH specification: https://reproducible-builds.org/specs/source-date-epoch/
- Reproducible Builds — Timestamps: https://reproducible-builds.org/docs/timestamps/
- Java 17 — Files.mismatch: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html

**Ghi nhớ:** **Tái dựng môi trường build** là kiểm soát điều kiện và đầu vào để người khác có thể lặp lại quy trình. **Tạo artifact giống từng byte** là một kết quả đo được trên chính file phát hành và cần loại bỏ bất định trong mọi bước build/packaging. Một quy trình tốt cần **cả hai**, báo rõ phạm vi đã kiểm chứng, rồi phát hành **đúng bytes đã được so sánh**.