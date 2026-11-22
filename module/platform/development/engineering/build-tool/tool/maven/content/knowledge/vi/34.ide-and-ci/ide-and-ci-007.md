# Lưu cache kho Maven cục bộ với khóa phù hợp và kiểm soát dữ liệu cũ trong IDE và CI

## 1. Vì sao cache giúp build nhanh nhưng cũng có thể gây lỗi khó hiểu?

Khi chạy Maven, build cần tải rất nhiều artifacts: dependencies trực tiếp, dependencies bắc cầu, POM cha, BOM quản lý phiên bản, Maven plugins và phụ thuộc của plugins. Một CI runner mới có thể tải lại cùng các file ở mỗi job nếu không giữ cache. Ngược lại, khi IDE và CI dùng dữ liệu kho cục bộ không phù hợp, triệu chứng thường rất khó truy vết:

- Cùng `pom.xml` nhưng IDE dùng một phiên bản `SNAPSHOT` cũ, CI lại lấy bản mới.
- Thay JDK hoặc Maven Wrapper nhưng pipeline vẫn tái sử dụng một kho download được tạo trong môi trường khác.
- Cache restore thành công nhưng Maven báo không resolve được artifact vì có metadata hoặc kết quả download thất bại từ lần trước.
- Một module nội bộ đã `mvn install` một bản phát triển vào local repository; job sau vô tình dùng bản đó thay vì artifact từ nguồn đáng tin.
- Proxy/repository mirror đã đổi nhưng cache không được phân vùng theo cấu hình nguồn tải.
- PR từ nguồn không tin cậy có cơ hội ảnh hưởng dữ liệu cache mà job có quyền phát hành về sau sẽ đọc.
- CI chỉ đo “cache hit” rồi kết luận build đúng, dù unit tests hoặc dependency integrity checks chưa chạy.

**Mục tiêu đúng:** cache làm **tăng tốc tải lại** những artifact hợp lệ; nó **không thay thế** nguồn dependency có kiểm soát, Maven versioning, tests, checksums, CI permissions hay quy trình làm mới dữ liệu.

Bài này nằm trong chủ đề **IDE và CI**. Trọng tâm là chiến lược **lưu kho Maven cục bộ bằng cache key phù hợp**, điều kiện cache hit/miss, phân biệt dữ liệu cũ nhưng hợp lệ với dữ liệu cũ sai lệch, cách refresh có mục tiêu và cách kết nối IDE với CI mà không phá kho dùng chung.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt Maven local repository, cache của CI, build output `target` và IDE index.
2. Hiểu Maven giữ JAR/POM/plugin/metadata như thế nào, vì sao các file `.lastUpdated` và `maven-metadata*.xml` có thể ảnh hưởng hành vi.
3. Thiết kế cache key theo hệ điều hành, kiến trúc, bộ mô tả dependencies, Maven Wrapper, extensions, repository configuration và khi cần theo JDK.
4. Hiểu restore key/prefix fallback làm tăng cache hit nhưng tăng rủi ro dùng dữ liệu cũ.
5. Dùng `actions/setup-java@v6` để cache Maven trong GitHub Actions.
6. Tạo cache GitLab CI bằng `cache:key:files`, `cache:paths` và `cache:policy`.
7. Biết tránh cache secrets, `settings.xml` có credentials, build output tạm hoặc artifacts phát hành chưa được xác minh.
8. Phân biệt release cố định, `SNAPSHOT` mutable, version ranges, parent BOM và plugin resolution.
9. Chạy `mvn -U`, dùng local repository sạch hoặc `dependency:purge-local-repository` đúng trường hợp.
10. Chẩn đoán IntelliJ IDEA reimport/cache index mà không xóa toàn bộ `~/.m2/repository`.
11. Tạo project Java 17/JUnit5 có dependency thật để kiểm tra cache, build và stdout chính xác.
12. Đo chất lượng cache qua duration, cache size, source consistency và test reliability, không chỉ hit rate.
13. Hiểu các ranh giới bảo mật cache poisoning và cách dùng read-only caches cho luồng kém tin cậy.
14. Thiết kế chính sách làm mới, cô lập và kiểm toán reproducibility phù hợp với CI matrix.

Ví dụ dùng Maven **3.9.x**, Java **17+**, Maven Compiler Plugin **3.14.1**, Surefire **3.5.4**, JAR Plugin **3.4.2**, Exec Plugin **3.6.4**, Dependency Plugin **3.10.0**, Commons Lang **3.17.0** và JUnit Jupiter **5.11.4**. Các version được ghim cho demo; môi trường thật vẫn phải theo bản vá và policy đã kiểm tra.

---

## 2. Phân biệt bốn lớp lưu trữ

| Lớp | Vị trí thường gặp | Dùng làm gì? | Có nên đưa vào cùng cache dependency? |
| --- | --- | --- | --- |
| Maven local repository | `~/.m2/repository` | JAR/POM/dependencies/plugins/metadata đã resolve | **Có**, với chính sách khóa và trust phù hợp |
| Maven Wrapper distribution | `~/.m2/wrapper/dists` | Maven distribution được Wrapper tải | Có thể cache **riêng**, theo wrapper properties |
| Build output | `<project>/target` | Classes, test reports, JAR tạm, generated files | **Không trộn** với dependency download cache |
| IDE caches/indexes | Thư mục dữ liệu của IDE | Indexing, symbol completion, metadata UI | Không phải Maven local repository; không xóa chung |

### 2.1. Maven local repository

Maven lưu artifacts được resolve từ repositories bên ngoài, từ build đa module và từ lệnh `mvn install` vào local repository.

Mặc định, kho nằm ở:

~~~text
~/.m2/repository
~~~

Ví dụ đường dẫn của một dependency:

~~~text
~/.m2/repository/org/apache/commons/commons-lang3/3.17.0/
    commons-lang3-3.17.0.jar
    commons-lang3-3.17.0.pom
    _remote.repositories
~~~

Tên file trong ví dụ đại diện cấu trúc thường gặp; các metadata/checksum/marker thật sự có thể khác theo Maven Resolver, repository policy và lịch sử tải.

**Không nhầm `~/.m2` với `~/.m2/repository`.** Thư mục `~/.m2` còn có thể chứa `settings.xml` (credentials), `toolchains.xml` hoặc `wrapper/dists`. Cache toàn bộ `~/.m2` sẽ đưa thêm dữ liệu ngoài dependency store vào archive CI và có thể rò rỉ bí mật.

### 2.2. Cache của CI

GitHub/GitLab CI lưu một bản archive của thư mục được chỉ định dưới một **cache key**, phục hồi ở job khác khi key hoặc restore rule phù hợp.

~~~text
Maven Central / private mirror
          |
          v
CI job A: tải thư viện vào local repo
          |
          v
CI cache service: save repo snapshot theo key
          |
          v
CI job B: restore cache snapshot
          |
          v
Maven dùng cache, vẫn có thể kiểm remote khi cần
~~~

Cache CI là **snapshot tối ưu hiệu năng**, không phải một artifact release được kiểm chứng provenance hoặc một database giao dịch.

### 2.3. `target` khác cache dependency

`target/classes`, `target/*.jar` và `target/surefire-reports` là kết quả của một build cụ thể. Nếu trộn chúng vào cache dependency, bạn có thể giữ lại output từ commit/JDK/profile trước và vô tình báo build xanh giả.

Dùng **CI artifacts** để chuyển binaries/test reports giữa jobs khi cần, với identity và retention policy riêng. Dùng **cache** để tăng tốc tải dependencies. GitHub và GitLab đều phân biệt hai mục đích này.

### 2.4. Cache IDE không phải cache Maven

IDE có các indexes phục vụ auto-complete và import resolution. Khi IntelliJ IDEA hiển thị “Cannot resolve symbol”, nguyên nhân có thể là:

- POM import chưa được reload.
- Maven local repository đang thiếu/mismatch artifact.
- IDE Maven runner trỏ tới `settings.xml`/local repo khác terminal.
- IDE đang bật offline mode.
- IDE indexes bị cũ.

**Invalidate IDE caches** không đồng nghĩa xóa Maven local repository; đồng thời xóa Maven repository cũng không nhất thiết sửa lỗi indexing của IDE.

---

## 3. Cache key: tính đúng quan trọng hơn hit rate

Một cache key tốt mô tả **những điều kiện có thể khiến nội dung local repository cần khác đi**.

Ví dụ ý tưởng:

~~~text
maven-deps-v3
  / linux
  / amd64
  / jdk17              (khi việc cô lập theo JDK là cần thiết)
  / maven-wrapper-hash
  / pom-files-hash
  / extensions-hash
  / repository-config-revision
~~~

Không nhất thiết phải cho tất cả thành phần vào một key literal; CI caching action có thể tự xây dựng key. Quan trọng là **ý nghĩa và khả năng invalidation**.

### 3.1. Những đầu vào nên xét

| Chiều khóa | Vì sao quan trọng? | Hướng xử lý |
| --- | --- | --- |
| OS/architecture | Một số plugins/native artifacts phụ thuộc platform | Tách cache khi dùng multi-OS/arch |
| POM files | Dependencies/plugins/parent/BOM versions có thể đổi | Hash các POM liên quan |
| Maven Wrapper properties | Distribution Maven được chọn có thể đổi | Dùng hash `.mvn/wrapper/maven-wrapper.properties` |
| Maven core extensions | Resolver/build extension thay đổi hành vi | Hash `.mvn/extensions.xml` nếu có |
| Java toolchain | Compiler/JDK-specific artifacts được `install` vào repo | Cô lập JDK khi có nguy cơ này |
| Mirror/repository config | Nguồn resolve và trust boundary khác | Cấu hình version/fingerprint không chứa secrets |
| Cache schema version | Thay policy hoặc lọc file trong cache | Tăng prefix `v2`, `v3` |
| Branch/trust level | PR không đáng tin không nên cung cấp cache cho release | Cô lập writes và dùng read-only restores |
| SNAPSHOT/update cadence | Một key lâu không đổi có thể chứa dữ liệu cũ | Xây chính sách refresh TTL hoặc cache rotation |

**Lưu ý:** nhiều JAR dependencies thuần Java có thể dùng chung giữa các JDK, nên tách cache theo JDK không phải yêu cầu bắt buộc trong mọi dự án. Nếu local repo chứa **artifacts do job `mvn install` tạo**, toolchains hoặc native dependencies thay đổi, cô lập theo JDK/OS sẽ an toàn hơn.

### 3.2. Cache key quá hẹp

Ví dụ key tệ:

~~~text
maven-cache
~~~

Nó không đổi khi POM thay, khi chuyển mirror hoặc thay repository policy. Lần restore từ cache cũ có thể vẫn build đúng nếu Maven kiểm remote và resolve lại, nhưng sẽ gây thêm những tình huống khó phân tích và nguy cơ reuse artifacts không mong muốn.

### 3.3. Cache key quá rộng

Ví dụ key chỉ dùng commit SHA:

~~~text
maven-cache-<commit-SHA>
~~~

Thay source code một dòng dù không thay dependencies cũng khiến key đổi. Cache miss và việc tải lại tăng đáng kể.

**Tối ưu:** tách **dependency identity** khỏi **source revision** khi phù hợp. Không dùng commit SHA như biến số duy nhất cho cache dependencies, trừ khi chính sách bảo mật yêu cầu isolation rất chặt.

### 3.4. Cache key không phải lockfile

Hash `pom.xml` giống nhau không chứng minh bytes dependency giống nhau:

- POM có thể dùng `SNAPSHOT` mutable.
- Imported BOM hoặc parent nằm ngoài repo được thay nội dung tại nguồn không tin cậy.
- Repository mirror có thể trả một artifact khác cùng GAV do cấu hình sai.
- Plugin có thể dùng metadata/resolution không ổn định.
- Local `mvn install` từng chèn artifact cùng coordinate.

Cache key giúp **chọn bản cache để phục hồi**, không cryptographically pin toàn bộ dependency graph và không kiểm tra tất cả artifacts có đúng checksum đáng tin.

---

## 4. Đồ thị phụ thuộc và cache invalidation

Giả sử project khai:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
</dependency>
~~~

Khi version đổi `3.17.0` thành một version khác, POM hash đổi nếu key được tạo từ POM. CI cache có thể miss theo key mới rồi tải những artifacts cần thiết.

Nhưng nếu bạn không đổi `pom.xml` mà remote snapshot metadata hoặc parent POM thay, **key có thể giữ nguyên**. Maven Resolver có update policies riêng để quyết định khi nào tìm remote metadata.

### 4.1. Multi-module Maven

~~~text
my-parent/pom.xml
├── core/pom.xml
├── api/pom.xml
└── worker/pom.xml
~~~

Nếu key chỉ hash root `pom.xml`, việc `api/pom.xml` thêm dependency không làm key đổi. Với reactor nhiều module, phải hash **tất cả POM tham gia build** hoặc một lock/fingerprint đầy đủ có thể được CI xác minh.

### 4.2. Imported Maven BOM

Dự án có thể import BOM để quản lý version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **snippet minh họa**, không phải artifact thực có sẵn. Cùng version string của một BOM đã publish không nên bị thay bytes; với internal SNAPSHOT BOM, nội dung có thể đổi và gây stale cache dù project POM giữ nguyên.

### 4.3. Profiles và settings

Một profile trong `settings.xml` có thể thêm repository hoặc bật mirror. Thay settings mà key không đổi có thể khiến Maven dùng cache được tạo từ nguồn khác.

Không cache `settings.xml` có secret. Thay vào đó, **nếu repository configuration là input cần phân vùng**, ghi một version/fingerprint **không nhạy cảm** (chẳng hạn tên environment “public-central”/“trusted-internal”) trong key, hoặc dùng namespace riêng cho runners.

---

## 5. Tài liệu trong local repository có thể “cũ” theo nhiều nghĩa

Không phải mọi file tồn tại lâu ngày đều sai. **Release immutable đã được xác minh** có thể reuse lâu dài. Các tình huống cần phân biệt:

| Loại dữ liệu | Biểu hiện | Có nên xóa ngay? |
| --- | --- | --- |
| Release JAR/POM hợp lệ, version cố định | Build vẫn resolve đúng | **Không** |
| Newer SNAPSHOT chưa được fetch | IDE/CI chạy code cũ | Dùng `-U` hoặc kiểm updatePolicy |
| `*.lastUpdated` ghi lỗi tải trước đó | Maven chặn/thử lại theo policy | Chẩn đoán lỗi mạng/mirror, refresh có mục tiêu |
| `maven-metadata-*.xml` cũ | Version/snapshot metadata không cập nhật | Kiểm repo, updatePolicy, refresh |
| Artifact hỏng hoặc thiếu file | Checksum/unzip/classpath lỗi | Purge **đúng tọa độ** và resolve lại |
| Đã `mvn install` bản nội bộ cũ | Local artifact che bản mới | Dùng repo sạch/isolation và kiểm origin |
| Credentials/mirror lỗi | 401/403/TLS/proxy | Sửa config, **không** xóa toàn repo |
| IDE Maven model cũ | Editor đỏ nhưng CLI build pass | Reload Maven project/index theo trình tự |
| CI cache có nội dung độc hại | Khả năng cache poisoning | Cô lập/drop cache theo incident procedure |

### 5.1. SNAPSHOT có thể thay đổi dưới cùng version

Maven SNAPSHOT convention cho phép nhiều bản xây dựng khác nhau dưới một coordinate logic như:

~~~text
vn.example:shared-api:1.2.0-SNAPSHOT
~~~

Remote repository có metadata timestamped snapshots. Local repository giữ metadata và bản tải tại thời điểm tương ứng. CI cache không có lý do tự động biết một SNAPSHOT mới xuất hiện nếu chỉ nhìn POM hash.

**Vì vậy:** nếu project thật sự cần SNAPSHOT mới, phải có update policy/refresh đúng hoặc key rotation. Với release quan trọng, ưu tiên dependencies có version immutable và provenance được quản lý.

### 5.2. Maven updatePolicy

Repository policy có thể khai:

~~~xml
<repositories>
    <repository>
        <id>trusted-snapshots</id>
        <url>https://repo.example.invalid/snapshots</url>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
        </snapshots>
        <releases>
            <enabled>false</enabled>
        </releases>
    </repository>
</repositories>
~~~

Đây chỉ là **POM fragment minh họa**, không phải POM runnable, và domain `example.invalid` không phục vụ tải thật.

Các giá trị `updatePolicy` Maven hỗ trợ:

- `always`: kiểm cập nhật thường xuyên mỗi lúc cần resolve theo policy.
- `daily`: mặc định, có thể chưa lấy ngay bản snapshot mới trong cùng ngày.
- `interval:60`: ví dụ chờ 60 phút giữa các lần kiểm.
- `never`: không kiểm cập nhật theo policy sau khi đã có locally; có nguy cơ dữ liệu lâu không đổi.

Đừng chuyển mọi repository thành `always` để chữa một lần lỗi: nó tăng network traffic và không sửa vấn đề credentials/mirror.

### 5.3. Maven -U

~~~bash
mvn -U -B -ntp clean verify
~~~

`-U` / `--update-snapshots` buộc Maven kiểm tra **updated snapshots và missing releases** ở remote repositories. Nó không có nghĩa:

- xóa sạch local repository;
- ép ghi đè mọi immutable release artifact;
- chứng minh cache không bị poisoning;
- chữa được 401/403/TLS/proxy;
- thay đổi version trong POM;
- làm mọi plugin tự động cập nhật lên bản mới.

Nếu dependency bị hỏng dù coordinate release cố định, cần xem error và dùng targeted purge/fresh repo khi thích hợp.

### 5.4. Negative cache và `.lastUpdated`

Sau lần tải thất bại, Maven Resolver có thể để lại marker như:

~~~text
commons-lang3-3.17.0.jar.lastUpdated
~~~

Tên/path cụ thể phụ thuộc artifact và Maven Resolver version. Marker ghi nhận kết quả transfer không thành công và giúp Maven tránh lặp request theo update policy.

Nếu lỗi tải do repository tạm mất kết nối, sau khi hạ tầng được sửa:

~~~bash
mvn -U -B -ntp verify
~~~

có thể kích hoạt lần kiểm lại. Nếu vẫn fail, xem Maven log **đúng repository URL/id và lỗi HTTP/TLS**; đừng liên tục retry không kiểm soát hoặc xóa toàn bộ `~/.m2`.

---

## 6. Maven local repository không phải một thư mục JAR đơn giản

Bên cạnh `.jar`/`.pom`, kho chứa metadata phục vụ resolution:

~~~text
~/.m2/repository/com/example/internal-lib/1.0.0-SNAPSHOT/
    internal-lib-1.0.0-SNAPSHOT.pom
    internal-lib-1.0.0-SNAPSHOT.jar
    maven-metadata-*.xml
    _remote.repositories
    *.lastUpdated
~~~

Đây là một cấu trúc minh họa tổng hợp; không phải tất cả files luôn cùng tồn tại cho mọi artifact.

### 6.1. `_remote.repositories`

Maven Resolver có metadata liên quan origin/repository ID. Khi bạn đổi repository ID, mirror hoặc policy mà một artifact cũ đã được lấy từ nguồn khác, kết quả resolution có thể không giống kỳ vọng. Đừng xóa marker này mù quáng: kiểm tra source repository config và provenance trước.

### 6.2. `maven-metadata-*.xml`

Các file metadata có thể chứa thông tin versions và snapshot timestamps. Khi TTL/update policy chưa hết hoặc mirror không trả metadata mới, IDE/CI có thể nhìn thấy version cũ.

### 6.3. Cùng version nhưng khác bytes do local install

Nếu developer build một module nội bộ rồi:

~~~bash
mvn install
~~~

artifact của module đó được ghi vào local repository theo cùng GAV/version của project. Nếu cache CI giữ directory này và một job khác dùng GAV ấy, build có thể resolve artifact **từ lần build trước**, không phải thứ vừa được build trong invocation hiện tại.

Điều này cần chú ý với `SNAPSHOT` và CI jobs tách rời. Dùng full reactor + `-am` khi phù hợp, hoặc fresh repository, hoặc artifact promotion có version/provenance rõ. Không chia sẻ writable `~/.m2/repository` giữa nhiều runners không tin cậy.

---

## 7. Dự án Java 17 runnable để minh họa tải và tái dùng dependency

Tạo ba file:

~~~text
maven-cache-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/cache/App.java
    └── test/java/vn/example/cache/AppTest.java
~~~

Dự án dùng Commons Lang làm compile dependency và JUnit Jupiter làm test dependency. Lần đầu Maven cần resolve các artifacts và plugins; lần sau có thể reuse local repository.

### 7.1. POM hoàn chỉnh

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-cache-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.cache.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.10.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tại sao ghim các versions?

- Compiler, Surefire và JAR Plugin không phải lúc nào cũng có phiên bản mặc định giống nhau giữa Maven/toolchain.
- Dependency Plugin sẽ được dùng cho diagnostics và targeted purge.
- Exec Plugin chạy main trong Maven-managed dependency classpath.
- Commons Lang 3.17.0 có thật trên Maven Central và dùng được trong ví dụ; đây là **fixture học tập**, không phải hướng dẫn giữ bản này mãi trong production.
- JUnit test dependency minh họa rằng cache chứa **cả compile/runtime và test artifacts**.

### 7.2. Java main class

File `src/main/java/vn/example/cache/App.java`:

~~~java
package vn.example.cache;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message(String value) {
        return StringUtils.capitalize(StringUtils.trimToEmpty(value)) + " ready";
    }

    public static void main(String[] args) {
        System.out.println(message(" cache "));
    }
}
~~~

Class dùng Commons Lang thực sự, không chỉ khai một dependency “cho có”.

### 7.3. JUnit 5 tests

File `src/test/java/vn/example/cache/AppTest.java`:

~~~java
package vn.example.cache;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void formatsCacheMessage() {
        assertEquals("Cache ready", App.message(" cache "));
    }

    @Test
    void formatsAnotherName() {
        assertEquals("Maven ready", App.message(" maven "));
    }
}
~~~

**Hai tests** kiểm tra xử lý chuỗi. Chúng không xác minh cache integrity, nên CI cần kết hợp Maven dependency resolution và chính sách cache.

### 7.4. Build và chạy ứng dụng

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Khi Maven 3.9.x/JDK17+ và dependency repository truy cập được, kết quả mong đợi:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kết quả dự kiến**, không phải log đã được thực thi trên máy của người học.

Dùng Exec Plugin để chạy main:

~~~bash
mvn -q -Dexec.mainClass=vn.example.cache.App exec:java
~~~

Stdout **của App.main** chính xác:

~~~text
Cache ready
~~~

JAR này **không phải fat JAR**. Chạy `java -jar target/maven-cache-demo-1.0.0.jar` mà không cung cấp Commons Lang trong runtime classpath có thể báo `NoClassDefFoundError`; hãy dùng Exec Plugin hoặc distribution/fat JAR riêng. Điều đó không phải lỗi của cache Maven.

---

## 8. Thử nghiệm: cùng build với kho riêng và kho có sẵn

### 8.1. Dùng repository tách biệt bên ngoài target

Trong thư mục root dự án:

~~~bash
mvn -B -ntp "-Dmaven.repo.local=.m2-sandbox/repository" clean verify
~~~

Chú ý `.m2-sandbox/repository` nằm **ngoài target**, vì `clean` sẽ xóa build output. Maven tạo các directories cần thiết nếu có quyền ghi.

Lần đầu có thể tải nhiều JAR/POM/plugin. Lần sau:

~~~bash
mvn -B -ntp "-Dmaven.repo.local=.m2-sandbox/repository" clean verify
~~~

thường reuse dependency artifacts hợp lệ, giảm tải mạng. Nhưng vẫn chạy compiler/tests do bạn đã gọi `clean verify`. **Cache hit không được hiểu là skip tests.**

### 8.2. Chạy với local repo khác

~~~bash
mvn -B -ntp "-Dmaven.repo.local=.m2-fresh/repository" clean verify
~~~

Nếu `.m2-fresh/repository` chưa được sử dụng, Maven phải resolve những artifacts cần thiết vào đây. So sánh log download và thời gian giữa hai môi trường.

**Không cần xóa `~/.m2/repository`** để thử fresh cache. Tạo một repo khác trong workspace demo và đưa hai thư mục sandbox này vào `.gitignore` của project khi lưu code thật.

### 8.3. Kiểm tra repository path thật

Nếu Maven đang dùng settings khác hoặc command có `-Dmaven.repo.local`, default `~/.m2/repository` có thể không phải nơi được sử dụng. Các cách điều tra:

~~~bash
mvn help:effective-settings
mvn -version
~~~

Đọc giá trị `localRepository` và cấu hình mirrors/profiles tương ứng. Không in toàn bộ logs/settings chứa credentials vào công cụ chat hoặc CI artifact công khai.

### 8.4. So thời gian, không tự bịa con số

Thời gian phụ thuộc network, disk, runner tải, local repo warm/cold và số artifacts. Bài không khẳng định “cache nhanh hơn đúng 60%”. Hãy đo cùng CI provider, cùng máy loại, cùng source/POM, tách các lần cold/warm, đồng thời đo tổng thời gian restore/save cache.

---

## 9. GitHub Actions: setup-java@v6 là đường đơn giản

Theo tài liệu hiện hành của GitHub Actions, `actions/setup-java@v6` có chế độ `cache: maven` để cache Maven dependencies. Workflow ví dụ dưới đây ở **GitHub Actions**, không phải POM hay lệnh terminal:

File `.github/workflows/maven.yml`:

~~~yaml
name: Maven verify with dependency cache

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK and Maven cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Print Maven environment
        run: mvn -version

      - name: Build and test
        run: mvn -B -ntp clean verify
~~~

Đây là workflow minh họa cho repository chứa `pom.xml` ở root. Với GitHub-hosted runner, setup-java tải/chọn JDK và khởi tạo caching; Maven executable cần sẵn có hoặc được cài riêng. Nếu repo có Maven Wrapper, có thể chuyển sang `./mvnw -B -ntp clean verify` sau khi đảm bảo script wrapper có quyền execute.

### 9.1. setup-java v6 thực sự cache gì?

Tài liệu v6 phân biệt ba loại cache:

1. **Dependency cache**: ví dụ `~/.m2/repository`.
2. **Wrapper cache**: ví dụ `~/.m2/wrapper/dists`, tách khỏi dependency cache.
3. **JDK cache**: bản JDK tải xuống, có identity riêng.

Khi `cache: maven`, setup-java hỗ trợ chúng theo cấu hình tương ứng. Đừng mô tả “mọi thứ lưu trong một zip chứa cả settings.xml”; đó không phải thiết kế được docs khuyến nghị.

### 9.2. Cache key mặc định v6

Dependency cache key v6 có thành phần **runner OS, architecture, package manager và hash các dependency-definition files**. Đối với Maven, mặc định hash:

~~~text
**/pom.xml
**/.mvn/wrapper/maven-wrapper.properties
**/.mvn/extensions.xml
~~~

Nó giúp invalidation khi POM, Maven Wrapper hoặc core extensions đổi. **Dependency cache key mặc định không phải một key theo JDK major**; JDK installation cache có identity riêng. Nếu cần cô lập `~/.m2/repository` vì artifact nội bộ được build khác theo JDK, phải dùng chiến lược key/path/runner isolation nâng cao.

### 9.3. PR read-only cache

Option:

~~~yaml
cache-read-only: ${{ github.event_name == 'pull_request' }}
~~~

khi true cho PR sẽ restore cache nhưng **không lưu các thay đổi vào cache sau job**. Điều này giảm nguy cơ một PR tùy ý trở thành nguồn cache cho workflows đáng tin hơn và tránh nạp bản cache mới từ các nhánh rất ngắn hạn.

Không chỉ dựa vào flag này như cơ chế bảo mật duy nhất: GitHub cache access còn có branch scopes, event restrictions và permissions. Nếu có untrusted code execution, cache được restore vẫn là input cần được xem như **untrusted**, đặc biệt khi job sau có secrets hoặc quyền publish.

### 9.4. Khi cache miss

Lần đầu hoặc khi key đổi, Maven vẫn có thể tải dependencies qua repository đã cấu hình. CI phải **build đúng khi không có cache**; nếu chỉ chạy được sau restore, quy trình thiếu tính tái dựng và cần điều tra.

---

## 10. GitHub Actions: monorepo và khóa theo đường dẫn

Nếu repository có nhiều Maven projects:

~~~text
services/api/pom.xml
services/worker/pom.xml
libraries/common/pom.xml
.mvn/wrapper/maven-wrapper.properties
.mvn/extensions.xml
~~~

Có thể override danh sách input files bằng:

~~~yaml
- name: Set up Java with explicit Maven cache inputs
  uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
    cache-dependency-path: |
      **/pom.xml
      **/.mvn/wrapper/maven-wrapper.properties
      **/.mvn/extensions.xml
~~~

Đây là **snippet step**, không phải toàn workflow. Điều quan trọng là các POM của các module thực sự được hash. Nếu chỉ hash `services/api/pom.xml` mà parent hoặc imported BOM config có thể đổi, cache key không phản ánh đầy đủ input.

### 10.1. Đổi localRepository path phải đổi cache-path

Nếu Maven chạy:

~~~bash
mvn "-Dmaven.repo.local=.m2-ci/repository" clean verify
~~~

nhưng setup-java vẫn cache mặc định `~/.m2/repository`, bạn đang restore một nơi và Maven lại đọc một nơi khác. Khi dùng custom path, phải khai `cache-path` đồng bộ, hoặc tốt nhất giữ Maven local repository mặc định trong GitHub-hosted runners để giảm lỗi.

Snippet tham khảo:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
    cache-path: |
      .m2-ci/repository
      !.m2-ci/repository/**/*.lastUpdated

- run: mvn -B -ntp "-Dmaven.repo.local=.m2-ci/repository" clean verify
~~~

Đây là **hai steps minh họa**, có tính tới filter `.lastUpdated` khi save/restore cache trong setup-java v6. Nếu file filtering behavior khác theo action version hoặc repository location, kiểm logs thật và xem docs v6. Không giả định custom cache path tự đồng bộ Maven local repo.

### 10.2. Khi cần phân vùng theo JDK

Ví dụ CI matrix JDK17/JDK21: pure downloaded JAR dependencies thường không đổi theo JDK, nhưng một thư viện nội bộ được install cùng coordinate từ jobs khác JDK có thể có class bytes khác.

Phương án:

- Tách cache theo JDK bằng key riêng khi dùng cache action tùy biến.
- Cấm đưa artifacts built-from-source vào cache dependencies dùng chung cross-JDK.
- Dùng repository riêng theo job/trust domain.
- Đưa internal release artifacts vào repository manager đúng version thay vì “mượn” cache giữa các jobs.

Không cấu hình một cache key thủ công trong setup-java mà action không hỗ trợ: `cache-dependency-path` thay **input file hash**, không phải một option để nhập nguyên arbitrary key. Khi cần key hoàn toàn tùy biến, dùng cache action riêng và quản lý đúng cache path/trust policy.

---

## 11. GitLab CI: cache:key:files + project-local Maven repository

GitLab CI thường chỉ cache paths nằm trong project workspace. Vì thế, thay Maven repo default `~/.m2/repository`, có thể chỉ định:

~~~text
$CI_PROJECT_DIR/.m2/repository
~~~

File `.gitlab-ci.yml` minh họa:

~~~yaml
image: maven:3.9-eclipse-temurin-17

stages:
  - test

cache:
  key:
    prefix: "maven-jdk17-$CI_COMMIT_REF_SLUG"
    files:
      - pom.xml
  paths:
    - .m2/repository/
  policy: pull-push

verify:
  stage: test
  script:
    - mvn -version
    - mvn -B -ntp "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository" clean verify
~~~

Dùng một Docker image Maven/Java được tổ chức kiểm chứng; khi cần tính tái lập mạnh hơn, pin image digest thay vì một mutable tag.

### 11.1. Giải thích khóa

- `prefix` cho biết policy epoch/JDK và branch scope.
- `files: pom.xml` tạo hash theo content file đầu vào.
- `paths` chỉ chứa project-local Maven repository.
- `policy: pull-push` cho phép cả restore lẫn upload cache.

**Giới hạn demo:** key chỉ hash root POM vì đây là project một module. Với multi-module, phải thêm những POM ảnh hưởng graph hoặc dùng patterns/lock fingerprint theo giới hạn của phiên bản GitLab CI đang chạy. Không coi một root POM hash là đủ nếu các child khai dependencies riêng.

### 11.2. Pull-only cho jobs không đáng tin

GitLab có cache policy:

~~~yaml
cache:
  policy: pull
~~~

Khi áp dụng đúng tại job/cache, nó chỉ download cache, không upload. Có thể dùng **trusted seed job** để làm ấm cache, rồi cho PR/test matrix jobs **pull-only**. Không sao chép một cache writable dùng chung qua những trust domains khác nhau.

### 11.3. Cache vs artifacts

GitLab phân biệt:

- **Cache:** dependencies/archives có thể reuse giữa runs.
- **Artifacts:** binaries/test reports tạo ở job hiện tại để lưu hoặc truyền giữa jobs.

Đừng cache `target` chung với `.m2/repository` chỉ để tiết kiệm thời gian; bạn có thể vô tình dùng output của commit trước và làm kết quả test/release khó truy vết.

---

## 12. Jenkins và self-hosted runners

Không có một cú pháp cache key duy nhất cho mọi Jenkins installations. Jenkins có nhiều khả năng: local workspace reuse, persistent volumes, managed dependency mirrors hoặc caching plugins.

Nguyên tắc thiết kế:

1. Chọn local repo path tường minh, ưu tiên isolated workspace/agent khi jobs không cùng trust domain.
2. Không để nhiều Maven processes độc lập cùng ghi vào một local repo network share không có cơ chế phù hợp.
3. Tạo key hoặc namespace theo OS/arch/inputs/runner identity khi cache plugin hỗ trợ.
4. Không cache credentials; CI secrets và Maven settings phải được inject có kiểm soát.
5. Tách mutable development SNAPSHOTs khỏi immutable release dependencies nếu có rủi ro contamination.
6. Dùng repository manager proxy/mirror để giảm traffic mạng xuyên nhiều agents thay vì một shared writable `~/.m2` kém an toàn.

### 12.1. Repository manager không giống CI cache

Nexus/Artifactory/mirror nội bộ có thể kiểm soát downloads từ upstream, permissions, checksums, retention, quarantine và bản phát hành. CI cache chỉ cất bản sao local của lần resolve trước.

Một thiết kế thường gặp:

~~~text
Maven Central / internal upstream
          |
          v
Trusted repository manager
          |
          v
Runner Maven local repo
          |
          v
CI cache service (optional)
~~~

Đừng thay repository manager có policy bằng một folder cache không quản lý nếu sản phẩm đòi kiểm soát nguồn phần mềm.

---

## 13. IDE: khi thấy dependencies “kẹt” phiên bản cũ

Trong IntelliJ IDEA, vấn đề có thể thuộc hai nhóm:

**Maven resolution:** local repo/settings/mirrors/SNAPSHOT đang lỗi.

**IDE model/index:** project đã thay POM nhưng IDE chưa reload, indexes đang không nhất quán.

### 13.1. Quy trình xử lý nhẹ trước

1. Xem IDE đang chọn Maven distribution nào: bundled Maven, external Maven hay Wrapper.
2. Xem Maven runner JDK, Maven settings file và local repository path.
3. Kiểm tra “Work offline” có đang bật không.
4. Với SNAPSHOT, kiểm tra “Always update snapshots” hoặc chạy command Maven riêng với `-U` khi cần.
5. Reload/reimport Maven project trong IDE.
6. So với terminal chạy **cùng Maven executable, settings, JDK và local repository path**.
7. Nếu terminal build pass nhưng editor vẫn báo đỏ, mới xem IDE indexes/repair workflow.
8. Chỉ khi có evidence artifact local bị lỗi/cũ mới targeted purge hoặc fresh local repository.

IntelliJ hiện có mục `Maven | Repositories` để xem/update indexed repositories, và tùy chọn Maven “Work offline”, “Always update snapshots”, “Local repository”. Việc update **IDE repository indexes** giúp tìm kiếm/code completion, không mặc định xóa hoặc tải lại mọi JAR bị cũ.

### 13.2. Vấn đề index khác vấn đề Maven

Nếu lỗi chỉ ở symbol highlighting, thử reload Maven Projects hoặc IDE cache recovery theo tài liệu JetBrains. Chức năng “Invalidate Caches” của IDE xóa **IDE caches** cho việc indexing, không phải cách an toàn để refresh toàn bộ Maven dependency repository.

### 13.3. IDEA có thể dùng repository khác terminal

Có thể terminal dùng:

~~~text
Maven CLI: -Dmaven.repo.local=/work/cache/m2
IDE: ~/.m2/repository
~~~

Khi đó một bên có artifact, bên kia không. Đừng vội kết luận CI cache hỏng. Kiểm tra `help:effective-settings`/IDE Maven settings và so path thật.

### 13.4. IDE không tự kiểm tra mọi điều kiện CI

IDE import dependencies thành công không chứng minh:

- CI JDK/Maven có phiên bản tương ứng.
- CI mirror có quyền truy cập.
- Cache key chứa đủ input.
- Unit tests được chạy trên runner.
- Artifacts không bị thay thế bởi internal local install.

CI phải có build độc lập và verification trên clean/fresh repository theo tần suất thích hợp.

---

## 14. Xử lý cache cũ theo mức độ từ nhẹ đến mạnh

Tuyệt đối không bắt đầu bằng:

~~~text
Xóa toàn bộ ~/.m2/repository
~~~

Vì việc này xóa hàng nghìn artifact hợp lệ, làm mất lợi ích cache, tốn băng thông và có thể làm hỏng các job khác đang đọc local repo dùng chung. Nếu cần cô lập, tạo repository mới thay vì xóa kho dùng chung.

### Mức 1 — Kiểm tra cấu hình đầu vào

~~~bash
mvn -version
mvn help:effective-pom
mvn help:effective-settings
mvn dependency:tree
~~~

Mục tiêu: xác định Maven/JDK, POM/profile, dependency version, mirrors, repositories và local repo path. Thận trọng khi chia sẻ `effective-settings` hoặc debug logs vì có thể lộ config nhạy cảm, tùy plugin/options.

### Mức 2 — Refresh remote metadata/snapshots

~~~bash
mvn -U -B -ntp clean verify
~~~

Phù hợp khi SNAPSHOT/missing release đang bị cache theo update policy. Không phù hợp để sửa URL repository sai hoặc TLS error.

### Mức 3 — Purge đúng dependency

Apache Maven Dependency Plugin cung cấp `purge-local-repository`. Ví dụ với **project demo**, nếu muốn loại đúng Commons Lang khỏi **local repo hiện tại**:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:purge-local-repository \
  -DmanualInclude=org.apache.commons:commons-lang3 \
  -DreResolve=false
~~~

Lệnh trên dành cho Bash/Linux/macOS (có ký tự nối dòng `\`). Phiên bản một dòng dùng được trên PowerShell/CMD:

~~~text
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:purge-local-repository -DmanualInclude=org.apache.commons:commons-lang3 -DreResolve=false
~~~

Trong lần build kế tiếp, Maven sẽ resolve lại dependency khi cần. **Lưu ý lệnh purge là thao tác thay đổi local repository**: chỉ chạy khi có quyền, đã xác nhận repo path và tọa độ cần làm mới, đặc biệt trên CI runner dùng chung. Nếu cần chạy thử mà không đụng repo thường dùng, thêm `"-Dmaven.repo.local=.m2-sandbox/repository"` vào command để thao tác đúng sandbox.

### Mức 4 — Dùng repository mới, sạch

~~~bash
mvn -B -ntp "-Dmaven.repo.local=.m2-audit/repository" clean verify
~~~

Khi repo mới chưa có artifact demo, Maven phải resolve từ nguồn cấu hình. Đây là cách **đối chiếu lỗi do cache** mà không hủy kho cũ.

### Mức 5 — Invalidate key CI

Thay prefix/version của key, hoặc thay inputs được hash sau khi policy đổi:

~~~text
maven-deps-v2-...
       |
       v
maven-deps-v3-...
~~~

Đổi key chỉ khiến CI chọn/sinh cache khác; nó không tự chữa artifact bị publish sai ở upstream. Nếu cần loại một cache có dấu hiệu malicious, phải xử lý theo quyền và quy trình incident/cache eviction của nền tảng CI.

---

## 15. Hiểu rõ dependency:purge-local-repository

Maven Dependency Plugin `purge-local-repository` được thiết kế để **xóa và tùy chọn re-resolve** artifacts của project.

Một số option:

| Option | Ý nghĩa |
| --- | --- |
| `-DmanualInclude=groupId:artifactId` | Chỉ định artifact(s) được purge thủ công |
| `-Dinclude=groupId:artifactId` | Giới hạn dependencies hiện có trong project tree |
| `-DreResolve=false` | Không tự resolve lại ngay sau purge |
| `-DactTransitively=false` | Giới hạn phạm vi tránh quét transitive nếu thích hợp |
| `-DresolutionFuzziness=version` | Xóa theo mức phiên bản, mặc định |
| `-DresolutionFuzziness=artifactId` | Rộng hơn, có thể xóa mọi versions của artifact |
| `-DsnapshotsOnly=true` | Chỉ xử lý SNAPSHOT trong những trường hợp áp dụng |

**Không dùng `resolutionFuzziness=groupId` bừa bãi**; có thể xóa một lượng rất lớn dependencies cùng group. Với module bình thường chỉ nghi một JAR hỏng, `manualInclude` là chiến lược hẹp hơn.

### 15.1. Purge không xóa credentials hay sửa remote

Nếu build fail vì 403, purge rồi tải lại vẫn sẽ bị 403. Nếu artifact upstream đã bị thay bytes bất thường, purge có thể tải lại artifact khác, nhưng việc làm đó không thay điều tra integrity/provenance.

### 15.2. Không purge project dependency tree giữa lifecycle tùy tiện

Maven docs cảnh báo purge dependencies **giữa một build đang chạy** có thể làm plugin khác cần artifact vừa bị xóa. Vì thế dùng goal này như bước bảo trì/diagnostics riêng, không tự bind vào những phase trong release pipeline nếu không hiểu tác động.

### 15.3. Plugin artifacts cũng có thể lỗi

`purge-local-repository` mặc định tập trung project dependency graph. Nếu lỗi là Maven plugin, imported POM hoặc parent POM, cần xác định tọa độ liên quan, dùng `manualInclude` hoặc local repo sandbox; không cho rằng purge project dependencies sẽ sửa tất cả Maven plugin resolution.

---

## 16. Khi nào cache trở thành rủi ro bảo mật?

GitHub Docs cảnh báo restored caches là **input không đáng tin** nếu workflow kém tin cậy có thể ghi cache hoặc một workflow đáng tin khôi phục nội dung độc hại từ vùng không an toàn.

### 16.1. Cache poisoning

Một luồng xấu có thể xảy ra:

~~~text
Untrusted PR job
    |
    +-- ghi/thay đổi cached dependency file
    |
    v
Trusted release job restore cùng vùng cache
    |
    +-- Maven chạy plugin/dependency bị thay đổi
    |
    v
Rủi ro thực thi mã không mong muốn hoặc build sai provenance
~~~

Không phải mọi PR tự động có quyền ghi lên default branch cache; CI provider có branch/event scope và hạn chế trust. Nhưng **không được chỉ dựa vào việc key giống khác nhau** để giải quyết toàn bộ security model.

### 16.2. Các quy tắc cốt lõi

- Không cache `settings.xml` hoặc files chứa passwords/tokens.
- PR từ fork/untrusted triggers nên restore-only khi có thể.
- Không nới quyền cache write cho low-trust workflows chỉ để tăng hit rate.
- Không chia sẻ cache writable giữa release jobs có secrets và untrusted PR jobs.
- Không dùng một cache global chỉ vì “tiết kiệm băng thông”.
- Dùng repository manager có integrity/checksum policy và nguồn artifacts đáng tin.
- Nếu phát hiện compromise, cô lập/delete cache theo quy trình CI; không chỉ tăng key rồi coi incident đã xử lý.
- Không chạy build có quyền publish từ artifact chưa được kiểm tra origin/trust boundary.

### 16.3. ChecksumPolicy

Maven có `checksumPolicy` ở repository settings/POM, với các lựa chọn như `fail` và `warn`. Chọn strict failure khi phù hợp với repository manager và quy trình kiểm soát artifacts.

**Cảnh báo:** kiểm checksum của download mới **không tự phát hiện** mọi tệp đã bị sửa bên trong restored CI cache; một attacker có khả năng ghi cache có thể ảnh hưởng dữ liệu mà Maven đọc như local artifact. Cần bảo vệ kênh cache và kiểm provenance/sha từ nguồn tin cậy, không coi checksumPolicy là thay thế access control.

### 16.4. Cache retention và xóa

CI systems có TTL/quota/eviction theo chính sách. “Giữ mọi cache mãi mãi” không phải tối ưu. Đối với release, giữ **build artifacts và provenance** theo retention của release; cache có thể xóa/tạo lại mà không ảnh hưởng tính đúng nếu remote repositories vẫn khả dụng.

---

## 17. Cache warming và giới hạn của go-offline

Khi muốn làm ấm cache trước một build matrix, Maven Dependency Plugin có goal:

~~~bash
mvn dependency:go-offline
~~~

Nó cố resolve project dependencies và plugins cùng những thành phần liên quan. Tuy nhiên **không bảo đảm** mọi artifact mà một custom plugin sẽ tải động lúc integration test hoặc packaging đều đã có. Một số plugins dựa vào lifecycle/context và có thể resolve thêm artifacts.

Vì vậy:

1. Có thể dùng `dependency:go-offline` để giảm số lần tải lại.
2. Vẫn phải chạy full `mvn clean verify` trong job kiểm chứng.
3. Đừng biến cache warming success thành quality gate.
4. Nếu job bắt buộc chạy offline, hãy kiểm thật với `mvn -o` sau khi các dependencies cần thiết đã được xác định.
5. Một offline build thành công chỉ chứng minh local repo đủ cho invocation ấy, **không chứng minh dependency là đúng/cập nhật/an toàn**.

### 17.1. Một job seed cache tin cậy

Phương án GitHub Actions v6 có thể dùng trusted push job để tạo cache, còn nhiều matrix jobs đọc cache ở chế độ read-only. Điều này tránh hàng chục parallel workers tranh ghi cùng key.

~~~text
Trusted seed:
    fetch + resolve expected dependencies
            |
            v
    save cache (trusted scope)
            |
            v
Consumer jobs:
    restore cache (read-only)
            |
            v
    build + unit tests + policy checks
~~~

Nếu seed và consumer chạy khác branch/cache scopes, cần kiểm tra CI platform cho phép restore tương ứng; đừng tự giả định chúng luôn chia sẻ một archive.

---

## 18. Chiến lược cache cho CI matrix

### 18.1. OS matrix

Nếu build trên Windows, Linux và macOS, nên có OS trong key. Một số dependencies/platform-specific binaries khác nhau. GitHub setup-java đã bao gồm runner OS/arch trong dependency key v6.

### 18.2. JDK matrix

Nếu đang kiểm Java17 và Java21:

- Pure downloaded artifacts có thể dùng chung.
- Locally installed reactor jars hoặc annotation processor/native outputs có thể khác.
- Runtime/test behavior cần được kiểm ở từng JDK.
- JDK cache của setup-java đã tách theo distribution/version.
- Dependency cache **không mặc định tách theo Java major**; muốn tách phải chủ động thiết kế.
- Không dùng cache hit để bỏ matrix verification.

### 18.3. Branch matrix

Nếu mỗi PR có key riêng quá cụ thể, cache hit ít và nhiều duplicated archives. Nếu mọi PR chia một writable cache, rủi ro contamination/poisoning lớn hơn.

Thường dùng: trusted default-branch cache làm **restore reference**, PR chỉ đọc; branch isolation theo chính sách GitHub/GitLab và repository trust levels. Không nới quyền CI token để có cache hit.

### 18.4. Dynamic inputs

Nếu project có release dependency fixed nhưng thêm internal mutable SNAPSHOT, hãy cân nhắc một trong các phương án:

- Không dùng mutable SNAPSHOT cho release builds.
- Tách namespace cache dựa trên vòng đời/snapshot policy.
- Dùng `-U` khi pipeline cần bản mới.
- Pin artifact checksum/provenance ở release verification.
- Dùng fresh repository cho release candidates cần bảo đảm không lệ thuộc developer cache.

---

## 19. Quan sát chất lượng cache một cách thực tế

Một chiến lược cache cần được đánh giá ít nhất ở các trục:

| Chỉ số | Cần đo điều gì? |
| --- | --- |
| Cache hit/miss | Bao nhiêu jobs restore đúng cache key mong muốn? |
| Restore/save duration | Network archive load có mất nhiều hơn download trực tiếp không? |
| Cache size/quota | Archive có quá lớn, lưu dư metadata hoặc artifacts cũ không? |
| Dependency network traffic | Giảm tải Maven Central/mirror bao nhiêu? |
| Cold/warm build duration | Tổng thời gian verify thực có cải thiện không? |
| Freshness | Snapshot/metadata được cập nhật theo policy chưa? |
| Correctness | Tests/compilation và quality gates có pass trên cache miss không? |
| Reproducibility | Build có pass trên fresh local repository không? |
| Security | Không có secrets, low-trust writers, poisoned artifact evidence? |
| Diagnostics | Có thể phân biệt cache issue với repository outage dễ không? |

Đừng đưa vào tài liệu một số “cache tiết kiệm 80%” nếu chưa đo trên repository/workload thật. CI cache có thể **chậm hơn** khi archive cực lớn, download/upload cache mất thời gian hoặc key thay đổi quá thường xuyên.

### 19.1. Kiểm tra fresh-build định kỳ

Một workflow có cache nóng có thể che những dependencies chỉ tồn tại cục bộ do `mvn install`. Chạy một clean build trên local repo mới theo lịch hoặc trước release giúp phát hiện sự phụ thuộc ẩn vào cache cũ.

### 19.2. Nhận biết cache miss không phải build failure

Cache không còn tồn tại chỉ làm Maven tải dependencies lại; **về lý thuyết** build vẫn đúng nếu repositories truy cập được và dependencies còn được lưu ở nguồn đáng tin. Nếu build chỉ pass khi cache hit, cần xem GAV đã bị xóa khỏi upstream, credentials sai, plugin không được pin, hoặc build đang dựa vào local-only artifact.

---

## 20. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng | Hành động |
| --- | --- | --- |
| CI cache hit nhưng vẫn tải nhiều dependencies | Key hit không đồng nghĩa cache đầy đủ; build thêm plugin | Xem download logs, cache paths, profiles |
| Cache hit nhưng `.m2` rỗng đúng nơi Maven dùng | setup-java cache-path khác Maven local repo | Đồng bộ `-Dmaven.repo.local` với cache-path |
| POM đổi mà cache key không đổi | Chỉ hash root, bỏ child POM/Wrapper | Mở rộng dependency inputs |
| Cache miss mọi commit | Key chứa commit SHA hoặc biến biến động | Dùng dependency files hash |
| Cache hit từ mirror cũ | Key thiếu repository config identity | Phân vùng cache theo trusted mirror config |
| `SNAPSHOT` cũ | UpdatePolicy/metadata/cache lưu lâu | Kiểm -U, snapshot policy và source repo |
| Lỗi “resolution will not be reattempted” | Negative cache `.lastUpdated` | Sửa remote lỗi rồi -U |
| 401/403 sau cache miss | Private repository thiếu credentials | Sửa settings/CI secret injection |
| SSL handshake/truststore error | Proxy/TLS/JDK cert config | Sửa truststore/network, không xóa toàn repo |
| Class mới có trong upstream nhưng IDE không thấy | IDE model/SNAPSHOT/local repo khác | Reload Maven, so Maven settings, -U |
| IntelliJ đỏ nhưng CLI `verify` pass | IDE index/model stale | Repair/reimport IDE, không purge trước |
| Lỗi checksum hoặc JAR hỏng | Corrupt cache/artifact | Targeted purge, fresh repo, integrity review |
| Bản code cũ bị dùng | `mvn install` đã cài internal SNAPSHOT | Cô lập repo; full reactor build |
| `mvn -o` pass nhưng clean runner fail | Cache che dependency thiếu ở upstream | Fresh repo và kiểm nguồn resolve |
| Release build chỉ pass với cache | Phụ thuộc artifact không còn reproducible | Fix repository/provenance, cấm release |
| GitHub PR có nguy cơ ghi cache đáng tin | Trust boundary thiếu | `cache-read-only`, permissions/scope |
| GitLab jobs tranh overwrite cache | pull-push chung key | Seed once, consumers pull-only |
| JDK matrix tạo class khác | Local installed artifact/JDK khác | Tách namespaces, không cache build outputs |
| GitHub action không chọn key mong muốn | cache-dependency-path globs thiếu | Đọc logs/config v6 |
| Cache lớn làm pipeline chậm hơn | Restore/save overhead lớn | Đo và giảm phạm vi/retention |
| Xóa `target` không sửa dependency | Cùng local repo giữ JAR cũ | Dùng -U hoặc purge đúng tọa độ |
| Xóa IDE indexes vẫn sai | Vấn đề Maven repo/settings thực | So effective-settings và dependency:tree |

### 20.1. Quy trình điều tra sáu bước

1. Ghi chính xác CI job/Maven command, JDK/Maven versions và profiles.
2. Kiểm tra Maven local repo path thật cùng cache path được restore.
3. Xem cache key đã được chọn, hit/miss, restore/save logs và trust scope.
4. Xem POM/effective POM, dependency:tree, mirrors, updatePolicy, SNAPSHOT metadata.
5. Chạy `-U` hoặc targeted purge nếu evidence là stale artifact; với lỗi mirror/TLS thì sửa hạ tầng.
6. So sánh fresh-repo build rồi cập nhật cache key/policy có kiểm soát; không xóa dữ liệu chung mù quáng.

---

## 21. Bài tập thực hành

### Bài A — Phân biệt cache

Maven lưu những gì ở `~/.m2/repository`? Tại sao không nên cache toàn bộ `~/.m2`? IDE index khác local repository ở chỗ nào?

### Bài B — Build demo

Tạo ba file của mục 7, chạy `mvn -B -ntp clean verify` và `mvn -q -Dexec.mainClass=vn.example.cache.App exec:java`. Xác nhận **2 tests PASS** và stdout App.main chính xác `Cache ready`.

### Bài C — Cold/warm repository

Dùng `.m2-sandbox/repository` cho hai lượt build, so số downloads và duration. Giải thích vì sao lần warm vẫn compile/test khi dùng `clean verify`.

### Bài D — Fresh repo

Dùng `-Dmaven.repo.local=.m2-fresh/repository`. Nếu fresh repo fail nhưng warm repo pass, bạn cần kiểm tra upstream credentials, missing artifacts và local `mvn install` như thế nào?

### Bài E — Thiết kế khóa

Một monorepo có 12 child POMs, Maven Wrapper và `.mvn/extensions.xml`. Nếu key chỉ hash root POM, thay child dependency có invalidation không? Thiết kế key đúng.

### Bài F — Java matrix

Hai jobs Java17 và Java21 dùng chung download cache. Khi nào reuse an toàn, khi nào phải tách? Có nên để artifacts đã `mvn install` cùng version trộn qua jobs không?

### Bài G — Snapshot cũ

Một internal library `1.2.0-SNAPSHOT` mới được publish nhưng IDE không thấy. Phân biệt IDE offline mode, Maven updatePolicy và CI cache key. Khi nào thử `-U`?

### Bài H — Negative cache

Một mirror tạm trả 503 và Maven tạo `*.lastUpdated`. Sau khi mirror phục hồi, cách kiểm tra an toàn trước khi xóa dữ liệu là gì?

### Bài I — Targeted purge

Chỉ nghi `org.apache.commons:commons-lang3` bị corrupt. Viết command `dependency:purge-local-repository` với `manualInclude` và `reResolve=false`; vì sao không xóa cả user repository?

### Bài J — GitHub cache

Phân tích `setup-java@v6`: key gồm gì, `cache-read-only` làm gì, khác gì với `cache-dependency-path`? Tại sao flag latter không trực tiếp cho phép đặt arbitrary key?

### Bài K — GitLab cache

Giải thích `cache:key:files`, `cache:paths`, `cache:policy`. Viết một trusted seed job có policy `push` và consumer job có policy `pull` theo hạ tầng của team.

### Bài L — Secrets

Một người đề xuất cache `~/.m2/settings.xml` để Maven có credentials khi restore. Tại sao nguy hiểm? Hãy nêu cách inject secrets an toàn.

### Bài M — GitHub cache poisoning

Vì sao PR from fork không nên được cấp quyền ghi cache mà release workflow có quyền deploy sẽ restore? Ngoài read-only, cần policy gì?

### Bài N — IDE đỏ nhưng CLI xanh

Terminal chạy với một local repo custom còn IDEA trỏ repo khác. Hãy kiểm tra và sửa config trước khi invalidate IDE indexes.

### Bài O — Maven Wrapper

Thay `.mvn/wrapper/maven-wrapper.properties` nhưng không thay `pom.xml`. Nếu key chỉ dựa POM hash, có vấn đề gì? Setup-java v6 mặc định xử lý input này thế nào?

### Bài P — Thời gian cache

Một cache archive 2 GB mất 80 giây restore/save trong khi cold Maven download mất 30 giây. Bạn nên đo và thay đổi gì trước khi tiếp tục cache?

### Bài Q — Checksum

Một dependency trong restored cache bị thay bytes. Vì sao `checksumPolicy=fail` khi tải remote mới chưa chắc phát hiện file đã bị sửa trong cache? Cần kết hợp trust boundary thế nào?

### Bài R — Release gate

Thiết kế pipeline kiểm đúng Maven/JDK, cache restore, `clean verify`, tests, dependency integrity, fresh repository check định kỳ, SBOM/provenance và release publish. Chỉ rõ cache miss **không nên** khiến pipeline đánh dấu chất lượng thất bại trừ khi nguồn dependencies không còn khả dụng.

---

## 22. Checklist cuối bài

- [ ] Biết local Maven repo thật và không nhầm với IDE indexes/`target`.
- [ ] Cache chính `~/.m2/repository` hoặc custom path được Maven thực sự dùng.
- [ ] Không cache `settings.xml` hoặc credentials.
- [ ] Cache key có đủ OS/arch/POMs/Wrapper/extensions theo policy.
- [ ] Multi-module key không bỏ qua child POMs.
- [ ] Có phương án cô lập repo config/mirror trust domain.
- [ ] Cân nhắc JDK tách riêng khi cache có artifacts build từ source.
- [ ] Không dùng commit SHA làm input duy nhất cho dependency cache nếu không cần.
- [ ] Biết cache hit không phải bằng chứng artifact integrity.
- [ ] Có policy xử lý SNAPSHOT, metadata và negative cache `.lastUpdated`.
- [ ] Dùng `-U` đúng mục đích; không coi nó là clean toàn repo.
- [ ] Targeted purge khi cần và xác nhận đúng tọa độ/path.
- [ ] Dùng fresh repo thay vì xóa shared repository khi chẩn đoán.
- [ ] GitHub untrusted PR jobs chỉ restore-only khi thích hợp.
- [ ] GitLab consumer jobs dùng `policy: pull` khi không nên ghi.
- [ ] Tests chạy đầy đủ sau restore; không bỏ quality gates.
- [ ] Không cache `target` chung với download dependencies.
- [ ] Cache rotation/retention có kiểm soát và đo hiệu năng thật.
- [ ] Khi IDE/CLI khác nhau, so settings/JDK/local repo trước.
- [ ] Có khả năng rebuild từ source trên cache miss với trusted repository.
- [ ] Luôn liên kết release artifacts/provenance với commit và build job.

**Kết luận:** Một cache Maven tốt không đơn giản là giữ nguyên `~/.m2` mãi mãi. Nó phải có **khóa phản ánh đầu vào phân giải dependency, phạm vi chia sẻ an toàn và chính sách refresh dữ liệu cũ**. Trong IDE, phân biệt Maven resolution với index/model cache; trong CI, lưu `~/.m2/repository` có chọn lọc, tách build artifacts, cấm cache secrets và kiểm soát trust giữa branches/runners. Khi nghi stale SNAPSHOT hoặc negative cache, dùng `-U`/targeted purge hoặc local repo sạch có kiểm soát. **Build đúng trên cache miss** mới là tiêu chuẩn để xem cache là công cụ tăng tốc chứ không phải một dependency ẩn của dự án.

## 23. Tài liệu tham khảo chính thức

- [Apache Maven Settings Reference](https://maven.apache.org/settings.html): `localRepository`, mirrors, repositories, updatePolicy, checksumPolicy.
- [Apache Maven POM Reference](https://maven.apache.org/pom.html): repository policy, plugin repositories, parent POM, dependencies.
- [Apache Maven CLI — Maven 3.9.x](https://maven.apache.org/ref/3.9.12/maven-embedder/cli.html): các flags Maven, bao gồm update snapshots.
- [Apache Maven Dependency Plugin — purge-local-repository](https://maven.apache.org/plugins/maven-dependency-plugin/purge-local-repository-mojo.html): manualInclude, reResolve, resolutionFuzziness.
- [Apache Maven Dependency Plugin — Purging Project Dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/examples/purging-local-repository.html): phạm vi xóa và warnings.
- [Apache Maven Dependency Plugin — go-offline](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html): cache warming.
- [GitHub Actions — setup-java v6](https://github.com/actions/setup-java): Maven cache default key, cache-dependency-path, cache-path, cache-read-only.
- [GitHub Actions — setup-java Advanced Usage](https://github.com/actions/setup-java/blob/main/docs/advanced-usage.md): Maven wrapper cache, plugin dependency caching.
- [GitHub Docs — Dependency Caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching): cache scope, cache poisoning và secrets.
- [GitHub Docs — Caching Concept](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching): cache so với artifacts.
- [GitLab Docs — Caching in CI/CD](https://docs.gitlab.com/ci/caching/): cache lifecycle và khác biệt với artifacts.
- [GitLab CI/CD YAML — cache:key:files và cache:policy](https://docs.gitlab.com/ci/yaml/): content-hash key và pull/push.
- [IntelliJ IDEA — Maven Settings](https://www.jetbrains.com/help/idea/maven.html): local repo, offline, update snapshots.
- [IntelliJ IDEA — Maven Repositories](https://www.jetbrains.com/help/idea/maven-repositories.html): repository indexes.
- [IntelliJ IDEA — Repair IDE](https://www.jetbrains.com/help/idea/repair-ide.html): re-sync và index recovery.
- [Maven Central — Commons Lang 3.17.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.17.0): artifact của ví dụ runnable.
