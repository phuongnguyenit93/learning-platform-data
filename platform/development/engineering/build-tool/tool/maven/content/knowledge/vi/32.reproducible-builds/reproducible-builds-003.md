# Rủi ro từ SNAPSHOT, khoảng phiên bản và nguồn tải thay đổi trong Maven

> **Build Tool Maven · Build tái lập**  
> Đối tượng: người học Maven 3.9.x, Java 17 và nhóm vận hành CI/CD. Mục tiêu là hiểu vì sao **cùng một Git commit, cùng `pom.xml` nhưng hai lần build có thể tải khác dependencies, khác plugin hoặc cho JAR khác bytes**, sau đó thiết kế quy trình phát hiện, ngăn chặn và đối chiếu. Bài có POM runnable, Java 17, JUnit 5, Maven Enforcer, lệnh đọc dependency graph/repositories, mô phỏng tình huống rủi ro và checklist release.

## 1. “Build tái lập” đòi hỏi điều gì?

Theo hướng dẫn Apache Maven về *reproducible builds*, hai lần xây dựng với **cùng source code, build environment và build instructions** cần tạo ra các artifacts được chỉ định giống nhau **tới từng byte**. Bản build phát hành phải có khả năng được bên khác dựng lại độc lập trong những điều kiện được ghi nhận.

Điều này mạnh hơn việc hai lần chạy đều in:

```text
BUILD SUCCESS
```

và mạnh hơn việc hai file đều mang tên:

```text
repro-risk-demo-1.0.0.jar
```

Tên artifact/Maven GAV chỉ mô tả tọa độ dự kiến; `BUILD SUCCESS` chỉ nói các goals đã hoàn tất trong điều kiện của lần chạy ấy. Để so sánh bytes, có thể dùng **SHA-256** trên file JAR/POM cuối; nếu bytes khác thì digest gần như chắc chắn khác. Digest giống nhau là dấu hiệu cùng bytes, nhưng **không tự chứng minh nguồn build đáng tin hay artifact đã ký**.

Để build thật sự tái lập, phải kiểm soát đồng thời:

1. **Source:** Git commit, submodules, generated sources, tài nguyên tải thêm.
2. **Dependencies:** trực tiếp, bắc cầu, test dependencies, BOM và parent POM.
3. **Plugins/extensions:** Maven plugin versions, plugin dependencies, build extensions.
4. **Nguồn tải:** repository URLs, mirror, proxy, credentials, repository manager và metadata.
5. **Toolchain:** Maven/JDK/OS, locale, timezone, environment variables.
6. **Build instructions:** profiles, `-D` properties, goals, offline/update flags.
7. **Output:** archive timestamps, file order, line endings, random/generated metadata.
8. **Evidence:** dependency graph đã resolve, hashes, CI run ID và artifact đã xuất bản.

Bài này tập trung sâu vào ba rủi ro liên quan đến **dependency resolution**:

- **`-SNAPSHOT`:** cùng một version khai báo có thể trỏ tới **binary mới được publish**.
- **Version range:** một yêu cầu cho phép **nhiều version** có thể chọn version khác sau khi metadata thay đổi.
- **Nguồn tải thay đổi:** Maven có thể nhận metadata/POM/JAR khác từ mirror, repository manager hoặc cache dù tọa độ giữ nguyên.

### 1.1. Sơ đồ nguyên nhân

```text
                 Git commit X + pom.xml giống nhau
                               |
                +--------------+--------------+
                |                             |
           Máy A / CI A                   Máy B / CI B
                |                             |
        settings/mirror A              settings/mirror B
        metadata cache A               metadata cache B
                |                             |
        SNAPSHOT build #5               SNAPSHOT build #6
        range chọn 3.14.0              range chọn 3.20.0
                |                             |
        dependency graph A             dependency graph B
                |                             |
              JAR A                         JAR B
                |                             |
           SHA-256 A                      SHA-256 B
```

**Cùng POM không đồng nghĩa cùng resolved dependency graph.** Dependency graph cần được resolve và lưu bằng chứng của **chính lần build**.

## 2. SNAPSHOT: version không đổi nhưng binary có thể thay đổi

Trong Maven, một version như:

```xml
<dependency>
    <groupId>org.example.shared</groupId>
    <artifactId>pricing-api</artifactId>
    <version>1.2.0-SNAPSHOT</version>
</dependency>
```

là ví dụ **rủi ro** (không phải dependency có thật để copy chạy). Hậu tố `-SNAPSHOT` biểu thị một phiên bản đang phát triển, có thể được publish nhiều lần.

### 2.1. Base SNAPSHOT và timestamped snapshot

Với remote Maven repository, một SNAPSHOT theo mô hình phổ biến có thể được publish thành các artifacts được phân biệt bởi timestamp và build number. Ví dụ minh họa:

```text
pricing-api-1.2.0-20261109.083000-5.jar
pricing-api-1.2.0-20261110.090000-6.jar
```

Cả hai đều tương ứng với yêu cầu logic:

```text
org.example.shared:pricing-api:1.2.0-SNAPSHOT
```

Thông tin trong `maven-metadata.xml` giúp Resolver biết phiên bản timestamped snapshot nào nên dùng theo metadata hiện có.

**Không ghi tên timestamped file thành kết quả luôn cố định cho mọi repository.** Local repository layout, caching, snapshot metadata và quy tắc server có thể khác nhau.

### 2.2. Hai lần build khác thời điểm

| Mốc | Source/POM | Metadata remote | Dependency được tải |
| --- | --- | --- | --- |
| Sáng thứ Hai | Git commit X; `1.2.0-SNAPSHOT` | Trỏ build #5 | Snapshot JAR #5 |
| Thứ Ba | Git commit X; cùng POM | Trỏ build #6 | Snapshot JAR #6 |
| Sau đó, máy offline | Git commit X; cùng POM | Không truy cập remote | Dùng snapshot trong local cache (nếu có) |

Ngay cả khi code ứng dụng không thay đổi, hành vi compile/test/runtime có thể thay đổi nếu API hoặc implementation của snapshot dependency thay đổi.

### 2.3. `updatePolicy` quyết định khi nào thử cập nhật, không khóa bytes

Maven hỗ trợ repository policy:

```xml
<snapshots>
    <enabled>true</enabled>
    <updatePolicy>daily</updatePolicy>
</snapshots>
```

Các giá trị được tài liệu Maven liệt kê:

| `updatePolicy` | Ý nghĩa |
| --- | --- |
| `always` | Thử kiểm tra cập nhật mỗi khi thích hợp |
| `daily` | Theo nhịp ngày; thường là mặc định |
| `interval:X` | Kiểm tra lại sau X phút, ví dụ `interval:60` |
| `never` | Không tự kiểm tra cập nhật thường xuyên theo policy |

**Đừng hiểu `never` là một dependency lockfile**. Nó chỉ giảm kiểm tra cập nhật, có thể làm máy A tiếp tục dùng cache cũ trong khi máy B có một snapshot khác ngay từ lần tải đầu. Nó cũng có thể khiến máy đã cache không thấy bản vá mới, gây rủi ro vận hành.

### 2.4. `-U`, `-o` và cache không giải quyết vấn đề gốc

Các lệnh:

```bash
mvn -U clean verify
mvn -o clean verify
```

có mục đích khác nhau:

- `-U` yêu cầu Maven kiểm tra lại những cập nhật liên quan SNAPSHOT/metadata theo semantics của phiên bản Maven, giúp lấy snapshot mới hoặc phát hiện metadata mới.
- `-o` dùng **offline mode**, không cố tải từ remote; build chỉ thành công nếu những dependencies/plugins/metadata cần thiết đã có đủ trong cache.

**`-U` không pin một snapshot**; nó có thể làm kết quả đổi. **`-o` không tự đảm bảo reproducible**; nó chỉ phụ thuộc những thứ máy đang có. Hai máy offline khác local cache vẫn có thể có inputs khác nhau.

### 2.5. Vì sao snapshot có ích trong phát triển nhưng nguy hiểm cho release?

Trong vòng lặp phát triển, `-SNAPSHOT` thuận tiện để thử phiên bản API sắp ra mắt. Trong build release hoặc build cần kiểm toán, nó gây ra vấn đề:

- Khó tái tạo chính xác một build cũ từ GAV.
- Cùng version nhìn thấy trên POM nhưng bytes có thể đổi.
- CI và máy developer có thể giải quyết snapshot metadata khác nhau.
- SBOM hoặc hồ sơ kiểm toán chỉ ghi base `1.2.0-SNAPSHOT` có thể thiếu bản snapshot thực tế.
- Rebuild hoặc rollback có thể tải một artifact khác với artifact đã kiểm thử.

**Chính sách thực tế:** có thể cho phép snapshot ở nhánh development có kiểm soát; **chặn snapshot dependencies trong release pipeline**, hoặc nếu tổ chức có ngoại lệ, phải khóa/ghi được **timestamped artifact + digest và repository origin**, lưu bytes không thể thay đổi và công bố rõ rủi ro.

## 3. Version range: cùng yêu cầu, phiên bản được chọn có thể khác

Maven cho phép dependency version requirements. Ví dụ:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>[3.10,4.0)</version>
</dependency>
```

Đây là **anti-pattern khi mục tiêu là reproducible release**, không phải cấu hình của POM runnable bên dưới.

Ý nghĩa của `[3.10,4.0)` là **tối thiểu 3.10 (kể cả), nhỏ hơn 4.0 (không kể)**. Resolver có thể chọn phiên bản cao nhất thỏa các ràng buộc cứng và metadata đang biết; version mới được publish có thể làm lựa chọn khác lần trước.

### 3.1. Cú pháp version requirements

| Cú pháp | Ý nghĩa |
| --- | --- |
| `3.14.0` | Yêu cầu phiên bản thường, nhưng Maven dependency mediation vẫn có thể ảnh hưởng một graph nhiều nhánh |
| `[3.14.0]` | Ràng buộc cứng chỉ cho phép `3.14.0` |
| `[3.10,4.0)` | Từ 3.10 inclusive tới dưới 4.0 |
| `(,2.0]` | Các phiên bản tới 2.0 inclusive |
| `[1.5,)` | Từ 1.5 trở lên, không giới hạn trên |
| `(,1.0],[1.2,)` | Cho phép trước/tới 1.0 hoặc từ 1.2 trở lên; không cho vùng giữa |

Apache Maven POM Reference phân biệt **soft requirement** (ví dụ `1.0`) và **hard requirement** (ví dụ range). Một tập hard requirements không có giao nhau sẽ khiến resolution lỗi, thay vì chọn đại một version.

### 3.2. Dữ liệu ví dụ để hiểu tính bất ổn

Đây là các **giả định minh họa**, không phải lịch sử phát hành của commons-lang3:

```text
POM: dependency version = [3.10,4.0)

Repository metadata tại T1:
  3.12.0
  3.14.0
=> Maven có thể chọn 3.14.0

Repository metadata tại T2:
  3.12.0
  3.14.0
  3.20.0
=> Maven có thể chọn 3.20.0
```

Cùng Git commit, cùng POM và lệnh:

```bash
mvn clean verify
```

không đảm bảo dependency graph giống nhau nếu kết quả range resolution đã thay đổi. Một local cache cũ có thể che sự thay đổi này trên máy developer.

### 3.3. Cảnh báo quan trọng: range `< 2.0` không đồng nghĩa chỉ lấy bản ổn định `1.x`

Tài liệu Maven POM Reference lưu ý một biểu thức như:

```text
[1.0,2.0)
```

có thể bao gồm pre-release kiểu `2.0-rc1`, vì `2.0-rc1` được so sánh nhỏ hơn `2.0`. Tức là range **không tự hiểu semantic versioning policy của nhóm bạn**.

Khi xây quy tắc phát hành an toàn, đừng lấy một range mở làm cách “chỉ nhận những bản vá ổn định”. Hãy chốt version cụ thể sau khi xem changelog, compatibility và dependency graph.

### 3.4. `LATEST`, `RELEASE` cũng là dynamic versions

Ví dụ di sản:

```xml
<version>LATEST</version>
```

hoặc:

```xml
<version>RELEASE</version>
```

phụ thuộc metadata repository và không nên dùng trong reproducible release POM. Các token này không phải cách đáng tin cậy để “luôn tự nhận bản an toàn mới”. Enforcer rule `banDynamicVersions` có thể cấm chúng cùng SNAPSHOT và ranges.

### 3.5. Chốt version chính xác có phải đủ chưa?

Không. Đổi:

```xml
<version>[3.10,4.0)</version>
```

thành:

```xml
<version>3.14.0</version>
```

loại bỏ **một nguồn dynamic selection**. Nhưng build vẫn có thể khác nếu:

- Dependency bắc cầu có policy khác.
- Parent/BOM/plugin versions không ổn định.
- Repository manager cho phép thay bytes của release `3.14.0`.
- Profiles/settings kích hoạt repositories khác.
- JDK/plugin/toolchain/output timestamps khác nhau.

Vì vậy **pin trực tiếp + lưu resolved dependency graph + kiểm soát repository + so hash** phải đi cùng nhau.

## 4. Nguồn tải thay đổi: cùng GAV nhưng có thể nhận dữ liệu khác

Maven biết những nơi tải artifacts từ nhiều nguồn:

- **Repositories** dưới `<repositories>` trong POM hoặc các POM được kế thừa/liên quan.
- **Plugin repositories** dưới `<pluginRepositories>`; plugins và dependencies của plugins có cơ chế resolution riêng với application dependencies.
- **Profiles** của POM và `settings.xml`, tùy điều kiện kích hoạt.
- **Super POM**, thường cung cấp Maven Central.
- **Mirrors** ở `settings.xml` có thể định tuyến các repositories sang repository manager khác.
- **Local repository** (`~/.m2/repository` theo mặc định, có thể cấu hình khác).
- **Parent POM, BOM imports và plugin/build extensions** cũng có thể dẫn đến tải metadata/artifacts.

Một POM không ghi repository URL không có nghĩa Maven không tải từ mạng: nó có thể dùng Central từ Super POM, cấu hình người dùng hoặc mirror do CI cung cấp.

### 4.1. Ví dụ repository policy ở POM

Một cấu hình **minh họa**, không phải phần của POM runnable:

```xml
<repositories>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/maven/releases</url>
        <releases>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
```

`repo.example.invalid` là URL **cố ý không hoạt động**, dùng để minh họa nơi thay bằng repository manager của tổ chức. Với Maven Central, **không cần** thêm repository giả để chạy bài lab.

Cấu hình trên yêu cầu repository được khai báo **không phục vụ SNAPSHOT**. Nó **không tự cấm snapshot từ tất cả nguồn khác** nếu active profiles hoặc repositories khác còn được phép phục vụ snapshots.

`checksumPolicy=fail` yêu cầu phản ứng nghiêm khi checksum thiếu/sai trong quá trình tải theo cơ chế Maven. Nó **không thay thế chữ ký/nguồn gốc đáng tin cậy** nếu kẻ tấn công kiểm soát cả artifact lẫn checksum bên cạnh.

### 4.2. `pluginRepositories` phải được xem riêng

Một build có thể pin `commons-lang3:3.14.0`, nhưng Maven cần tải Compiler/Surefire/JAR/Enforcer plugins. Nếu plugin version bỏ trống hoặc plugin repository/mirror thay đổi:

- Plugin được chọn có thể khác.
- Dependencies riêng của plugin có thể khác hoặc không tải được.
- Output có thể khác dù application dependency graph không đổi.
- Maven build có thể fail trước cả bước compile.

Đừng chỉ kiểm tra `dependency:tree` rồi kết luận **toàn bộ** build inputs đã được khóa. `dependency:tree` thông thường mô tả **project dependency graph**, không phải danh sách đủ của mọi plugin binary/extension đang chạy.

### 4.3. Mirror trong `settings.xml`

Ví dụ **chỉ để hiểu cấu hình**, phải thay URL bằng nguồn đã được duyệt trước khi sử dụng:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <mirrors>
        <mirror>
            <id>company-maven-manager</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.invalid/maven-group</url>
        </mirror>
    </mirrors>
</settings>
```

`mirrorOf=*` định tuyến các repository matching đến mirror, với ngoại lệ/behavior theo quy tắc Maven. Đây là **chính sách định tuyến**, không phải version lock.

Tại sao build có thể khác giữa hai ngày dù mirror URL không đổi? Repository manager có thể thay cấu hình nhóm upstream, quyền truy cập, artifact cache, retention, rewrite policy hoặc metadata của remote. URL endpoint giữ nguyên **không bảo đảm bytes giữ nguyên**.

### 4.4. Repository manager giải quyết được gì?

Một repository manager được kiểm soát có thể:

- Cho phép chỉ những upstream repositories đã duyệt.
- Cache metadata/artifacts, áp access control.
- Chặn overwrite release versions.
- Giới hạn SNAPSHOT cho các môi trường phát triển.
- Kiểm tra checksum/signature theo chính sách.
- Ghi audit logs và nguồn artifact.

**Nhưng:** mirror/cache manager không tự thay thế việc pin version hoặc lưu digest. Nếu manager thay đổi upstream hoặc bị xóa cache, một rebuild vẫn có thể tải dữ liệu khác. Đối với release quan trọng, cần có **bản sao immutable của artifact inputs** hoặc cơ chế verify digest/attestation.

### 4.5. Thứ tự và lựa chọn repository không đơn giản là URL đầu tiên

Maven Resolver xem repositories từ effective model/settings, mirror mapping, policy về releases/snapshots, local cache và metadata. Không suy đơn giản rằng thứ tự các dòng `<repository>` trong một POM nguồn **đủ** xác định file nào được tải.

Cần xác minh **effective settings**, **effective POM**, debug logs có kiểm soát và artifact origins/repository manager audit khi điều tra.

## 5. Cache local: nguồn nhiễu phổ biến khi thử build tái lập

Thư mục mặc định trên Linux/macOS:

```text
~/.m2/repository/
```

Trên Windows thường:

```text
%USERPROFILE%\.m2\repository\
```

Nhưng đường dẫn thật có thể khác theo `settings.xml` hoặc `-Dmaven.repo.local=...`.

Cache có thể chứa:

- Artifacts JAR/POM từ lần tải trước.
- `maven-metadata-*.xml` cho ranges/snapshots.
- Thông tin `_remote.repositories`.
- `.lastUpdated` cho các lần tải lỗi hoặc metadata update state.
- Các phiên bản plugin và transitive dependencies.

**Hai cache khác nhau là hai bộ inputs có khả năng khác nhau.** Cùng POM chạy offline trên hai máy không mặc nhiên là reproducible.

### 5.1. `mvn -o` không phải lockfile

```bash
mvn -o clean verify
```

có thể thành công ở máy A vì cache đủ, thất bại ở máy B vì thiếu plugin hoặc sử dụng một SNAPSHOT cũ ở máy C. Offline là **không truy cập mạng**, không phải **đã xác thực toàn bộ bytes của cache theo release manifest**.

### 5.2. `mvn -U` không phải cách “bảo đảm mới nhất và ổn định”

```bash
mvn -U clean verify
```

có thể giúp refresh metadata/snapshots, nhưng cũng làm build khác lần trước. Nếu artifact nguồn bị thay/metadata lỗi, `-U` có thể làm vấn đề lộ rõ, không tự sửa nguyên nhân.

`-U` **không biến release artifact mutable thành immutable**, không kiểm chứng cryptographic provenance và không khóa range selection.

### 5.3. Không xóa toàn bộ cache của người khác để debug

Khi cần so hai build, **dùng local repository riêng cho từng build**, ví dụ:

```bash
mvn -B -Dmaven.repo.local=/tmp/m2-repro-a clean verify
```

Trên CI nên cấp một local repo ở workspace riêng, cô lập và dùng repository manager có policy. Không dùng `rm -rf ~/.m2/repository` như bước mặc định, vì có thể phá nhiều workflows không liên quan.

### 5.4. Checksum cache và xác thực nguồn tải

Nếu nhận báo lỗi checksum, **không** tắt kiểm tra bằng cấu hình `ignore` chỉ để build xanh. Hãy kiểm tra:

1. Artifact thực được tải từ nguồn nào.
2. Checksum kỳ vọng có đến từ nguồn đáng tin cậy không.
3. Repository manager/mirror có trả artifact và checksum không đồng bộ không.
4. Có cache cũ hoặc partial download không.
5. Có dấu hiệu upstream artifact bị overwrite/tamper không.

Trong Maven, tùy phiên bản, `-C` yêu cầu strict checksums khi download, còn `-c` cho lax behavior; **không dùng lax để hợp thức hóa artifact có integrity mismatch**.

## 6. Anti-pattern so với cấu hình ổn định

| Mục | Có rủi ro | Phương án ổn định hơn |
| --- | --- | --- |
| Dependency version | `1.2.0-SNAPSHOT` | Release `1.2.0` đã kiểm soát và verify bytes |
| Version range | `[3.10,4.0)` | Chọn chính xác `3.14.0` |
| Version lookup | `LATEST`, `RELEASE` | Pin version cụ thể |
| Maven plugin version | Bỏ `<version>` | Ghim plugin version |
| Parent POM | `2.0-SNAPSHOT` | Parent version phát hành có immutable coordinates |
| BOM import | Khoảng version | BOM release version rõ và test consumer |
| Mirror | URL mirror khác nhau trên mỗi runner | Cấu hình repository manager chuẩn hóa |
| Snapshots policy | `always` cho release | Cấm/loại snapshots trong release; phát triển tùy nhu cầu |
| Release artifact overwrite | Cho sửa JAR/POM cùng GAV | Immutable release repository |
| Local repository | Cache cá nhân không xác minh | CI repo cô lập, resolved deps được ghi nhận |
| Archive timestamps | Giờ hiện tại mỗi lần build | `project.build.outputTimestamp` và compatible plugins |
| Source/JDK | Build từ branch/JDK tùy máy | Git commit chính xác, toolchain/policy rõ |
| Evidence | Chỉ ghi “BUILD SUCCESS” | Tree, toolchain, inputs, digest và run record |

**Không có một công tắc đơn lẻ nào biến mọi project thành reproducible.** Cần nhiều lớp kiểm soát.

## 7. Demo Java 17 an toàn: Maven POM ghim versions và từ chối dynamic deps

Demo dùng:

- **Java 17**, Maven **3.9.x**.
- `commons-lang3:3.14.0` ở **compile scope**, version cố định.
- JUnit Jupiter `5.11.4` ở **test scope**, version cố định.
- Compiler, Surefire, JAR, Resources và Clean plugins đều được ghim.
- **Maven Enforcer Plugin 3.6.3** với `banDynamicVersions`, `requireReleaseDeps`, `requireReleaseVersion`.
- `project.build.outputTimestamp` đặt giá trị cố định.
- Không khai báo thêm remote repository vì Maven Central hoặc repository manager hợp lệ được xử lý theo cấu hình môi trường.

### 7.1. Cấu trúc file

```text
repro-risk-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/org/example/repro/ReproMain.java
    └── test/
        └── java/org/example/repro/ReproMainTest.java
```

Các thư mục viết rút gọn theo path; khi tạo thực tế, tên package `org.example.repro` phải đúng với vị trí `org/example/repro`.

### 7.2. `pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>repro-risk-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Repro Risk Demo</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>no-dynamic-release-inputs</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <banDynamicVersions>
                                    <allowSnapshots>false</allowSnapshots>
                                    <allowRanges>false</allowRanges>
                                    <allowLatest>false</allowLatest>
                                    <allowRelease>false</allowRelease>
                                </banDynamicVersions>
                                <requireReleaseDeps />
                                <requireReleaseVersion />
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích chính xác:**

1. `commons-lang3` dùng **version cố định** và là compile dependency.
2. `junit-jupiter` chỉ phục vụ tests; dependency graph của test cũng là input cần kiểm soát.
3. Các plugin versions trong build được ghim; không dựa vào default implicit plugin versions.
4. Enforcer chạy goal `enforce` ở **`validate`**, bắt lỗi chính sách trước compile/package.
5. `banDynamicVersions` nhận diện ranges, `LATEST`/`RELEASE` và `-SNAPSHOT` trong dependency inputs theo semantics của rule.
6. `requireReleaseDeps` cấm SNAPSHOT dependencies theo phạm vi rule; `requireReleaseVersion` cấm chính project ở version SNAPSHOT. Những rules này có mục tiêu khác nhau.
7. `requireMavenVersion` và `requireJavaVersion` đặt **ngưỡng/major compatibility**, **không pin chính xác Maven patch/JDK vendor**. CI cần cấu hình toolchain cụ thể riêng nếu muốn lặp lại chặt hơn.
8. `project.build.outputTimestamp` định hướng reproducible archive timestamp cho các plugin hỗ trợ; **không bảo đảm dependency inputs luôn ổn định**.
9. Enforcer rule **không kiểm tra cryptographic trust của repository**, không bảo đảm release artifact cùng GAV không bị overwrite, và không thay việc so resolved digests.

### 7.3. `src/main/java/org/example/repro/ReproMain.java`

```java
package org.example.repro;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class ReproMain {
    private ReproMain() {
    }

    public static String normalize(String value) {
        String cleaned = StringUtils.trimToEmpty(value);
        return StringUtils.upperCase(cleaned, Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(
                "REPRO DEMO: " + normalize(" stable "));
    }
}
```

Ứng dụng dùng **Apache Commons Lang** thực sự ở runtime. `Locale.ROOT` giúp hành vi uppercase không phụ thuộc locale hiện hành của người chạy trong ví dụ.

### 7.4. `src/test/java/org/example/repro/ReproMainTest.java`

```java
package org.example.repro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ReproMainTest {
    @Test
    void normalizesWhitespaceAndCase() {
        assertEquals("STABLE", ReproMain.normalize(" stable "));
    }

    @Test
    void normalizesNullToEmpty() {
        assertEquals("", ReproMain.normalize(null));
    }
}
```

Hai tests có assertions rõ và dùng chính implementation chứa third-party dependency. Surefire 3.6.1 + JUnit Jupiter 5.11.4 có thể discover test class theo convention `*Test`.

### 7.5. Build

Tại thư mục `repro-risk-demo/`:

```bash
java -version
mvn -version
mvn -B -ntp clean verify
```

Khi repository và plugins được resolve thành công, file output thông thường:

```text
target/classes/org/example/repro/ReproMain.class
target/test-classes/org/example/repro/ReproMainTest.class
target/surefire-reports/TEST-org.example.repro.ReproMainTest.xml
target/repro-risk-demo-1.0.0.jar
```

Dòng kết quả kiểm thử **kỳ vọng**:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Nội dung ấy không phải toàn bộ Maven stdout, vốn có thể khác theo phiên bản Maven/OS.

### 7.6. Chạy ứng dụng bằng Exec Maven Plugin

Main JAR thông thường là một **thin JAR** và POM chưa cấu hình `Main-Class`. Nó còn phụ thuộc `commons-lang3` ở runtime. Vì vậy **không** chạy `java -jar target/repro-risk-demo-1.0.0.jar` mà thiếu classpath và manifest.

Cách thuận tiện cho lab là gọi explicit Exec Maven Plugin với **version ghim**:

```bash
mvn -B -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=org.example.repro.ReproMain
```

Exec Plugin sẽ tạo project classpath phù hợp cho goal `java` và gọi main class. **Stdout của chính Java main** là:

```text
REPRO DEMO: STABLE
```

`-q` làm Maven ít in log hơn; bất kỳ cảnh báo plugin/repository từ stderr hoặc môi trường CI vẫn phải được xem xét riêng. Không gọi output “bit-for-bit reproducible” chỉ vì chuỗi stdout đúng.

### 7.7. Nếu muốn tự chạy bằng `java -cp`

Cần đưa **compiled classes và commons-lang3 JAR** vào classpath:

**Linux/macOS với default local repo:**

```bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" org.example.repro.ReproMain
```

**Windows PowerShell với default local repo:**

```powershell
java -cp "target/classes;$HOME\.m2\repository\org\apache\commons\commons-lang3\3.14.0\commons-lang3-3.14.0.jar" org.example.repro.ReproMain
```

Cả hai chỉ áp dụng khi JAR đã tải vào **default local repository**. Nếu dùng `-Dmaven.repo.local=...`, phải thay path tương ứng. Classpath separator là `:` trên Unix và `;` trên Windows.

## 8. Tự tạo ba tình huống rủi ro để quan sát

**Không sửa POM runnable ở mục 7 rồi cho rằng nó vẫn an toàn.** Những đoạn dưới đây là **cấu hình minh họa cố tình rủi ro** để học cơ chế, cần thay về pinned versions khi hoàn tất.

### 8.1. Tình huống A — SNAPSHOT dependency

Thay version compile dependency bằng ví dụ giả định:

```xml
<dependency>
    <groupId>org.example.shared</groupId>
    <artifactId>pricing-api</artifactId>
    <version>2.1.0-SNAPSHOT</version>
</dependency>
```

Đây **không phải artifact được khẳng định tồn tại** trên Maven Central. Nếu team có repository SNAPSHOT thực, có thể thử trên **nhánh development** và ghi lại snapshot resolved artifact, checksum.

Enforcer rule `banDynamicVersions`/`requireReleaseDeps` trong POM lab sẽ từ chối SNAPSHOT theo release policy khi cấu hình được áp dụng. Đó chính là **kết quả mong muốn cho release**.

### 8.2. Tình huống B — Version range

Thay version:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>[3.10,4.0)</version>
</dependency>
```

Nếu Enforcer đang bật, build được thiết kế để **fail ở kiểm soát policy**, không phải mặc nhiên chọn một version rồi tiếp tục release. Để hiểu hành vi resolver trong môi trường thử nghiệm, có thể dùng một project sandbox riêng không bật release policy, chạy dependency tree và ghi exact resolved version ở từng mốc.

**Không** khuyên tắt Enforcer trên release pipeline để minh họa rủi ro; một sandbox tách biệt với production là cách kiểm soát tốt hơn.

### 8.3. Tình huống C — Mirror trả artifacts khác

Giữ exact `commons-lang3:3.14.0` nhưng thay `settings.xml` để định tuyến qua hai mirrors khác nhau (ở hai môi trường sandbox). Nếu một mirror trả bytes khác hoặc thiếu checksum, cùng GAV vẫn không chứng minh input được giữ nguyên.

Cách học an toàn là **so digests do môi trường cung cấp**, không tự tạo một JAR giả rồi upload lại vào repository dùng chung. Với public Central repository, dùng nguồn hợp lệ; nếu cần thử intentional corruption, làm trong **repository local riêng biệt** hoặc test fixture, không can thiệp repository production.

## 9. Kiểm tra dependency graph thực tế, không chỉ đọc POM

Maven Dependency Plugin có goal:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Nó báo graph **đã resolve**, gồm transitive dependencies và effective versions. Với plugin version 3.7.0 trở lên, `tree` có thể xuất JSON:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -DoutputType=json -DoutputFile=target/dependency-tree.json
```

**Ý nghĩa:** tạo bản chụp graph tại thời điểm build, hỗ trợ diff giữa các CI runs hoặc tái dựng quyết định version mediation. Nó **không** là lockfile được Maven tự dùng để ép future builds chọn y hệt.

### 9.1. `dependency:tree` cho biết gì và chưa cho biết gì?

| Có ích để xem | Không thể kết luận chỉ từ tree |
| --- | --- |
| GAV, scopes và transitive dependencies đã resolve | SHA-256 của từng JAR |
| Version cuối sau mediation | Chính xác URL/origin đã cung cấp bytes |
| Xung đột/omissions theo tham số | Mọi plugin dependencies và extension binaries |
| Quan hệ module/library | Build output byte-for-byte identical |
| Version đã chọn bởi range ở run hiện tại | Version nào sẽ được chọn ở run tương lai |

Để có release input inventory mạnh hơn, lưu thêm artifact digests, POM digests, repository origin và plugin versions. Những dữ liệu ấy cần bước CI/tooling bổ sung, không tự xuất hiện trong `dependency:tree`.

### 9.2. `dependency:list-repositories`

Maven Dependency Plugin có goal liệt kê repositories liên quan tới dependency resolution:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:list-repositories
```

Lệnh hữu ích để điều tra project dependencies đã nhìn thấy những repository nào. Nhưng **danh sách repositories không thay thế việc kiểm tra mirror mapping/proxy hoặc log artifact được phục vụ từ đâu**.

### 9.3. `help:effective-pom` và `help:effective-settings`

Để kiểm tra nguồn cấu hình:

```bash
mvn -B help:effective-pom -Doutput=effective-pom.xml
mvn -B help:effective-settings -Doutput=effective-settings.xml
```

Hai lệnh cho thấy **model/configuration hiệu lực** sau inheritance/profiles/settings theo phiên bản plugin đã resolve. Chúng không trực tiếp cung cấp hash của mỗi artifact binary.

**Bảo mật:** effective settings và debug logs có thể chứa cấu hình nội bộ, proxy/repository URLs hoặc giá trị bí mật tùy plugin/log masking. Không upload công khai toàn bộ file mà chưa rà soát. CI nên lưu bản đã redact trong kênh được bảo vệ.

### 9.4. Cách tìm SNAPSHOT hoặc range qua source POM và graph

Search POMs cho:

```text
-SNAPSHOT
<version>[ 
<version>(
LATEST
RELEASE
```

chỉ là **kiểm tra tĩnh sơ bộ**. DependencyManagement, properties, parent POM, BOM imports và active profiles có thể ảnh hưởng cuối cùng. Vì thế phải kết hợp **POM source**, **effective POM** và **resolved graph**, cùng Enforcer ở lifecycle.

Không đánh dấu một project an toàn chỉ vì `pom.xml` chính không có chuỗi `-SNAPSHOT`.

## 10. Enforcer để chặn dynamic versions trước khi phát hành

Maven Enforcer Plugin hỗ trợ các **built-in rules**:

| Rule | Mục tiêu |
| --- | --- |
| `banDynamicVersions` | Cấm range, `LATEST`, `RELEASE`, SNAPSHOT theo policy |
| `requireReleaseDeps` | Cấm SNAPSHOT dependencies |
| `requireReleaseVersion` | Cấm project artifact đang là SNAPSHOT |
| `requirePluginVersions` | Cảnh báo/fail nếu plugins thiếu version theo phạm vi kiểm tra |
| `dependencyConvergence` | Kiểm tra graph không có các version không hội tụ theo rule |
| `requireUpperBoundDeps` | Kiểm tra resolved version không thấp hơn mức đã yêu cầu bởi những đường phụ thuộc |

Trong POM lab, ba rules đầu được bật. Nếu team muốn bật thêm `requirePluginVersions` hoặc `dependencyConvergence`, cần kiểm tra default lifecycle bindings/plugins, parent POM và transitive graph của dự án; không tự xem mọi kết quả fail là bug của Maven.

### 10.1. `banDynamicVersions` có giải quyết mọi nondeterminism?

Không. Rule này giúp **phát hiện dynamic dependency version declarations**. Nó không ngăn repository phục vụ lại những bytes khác tại **cùng release GAV**, không xác thực upstream mirror và không đóng băng JDK.

Vì vậy hãy dùng nó làm **quality gate một lớp**, song song với repository immutability, approved mirrors và digest verification.

### 10.2. `requireReleaseDeps` có tương đương `banDynamicVersions`?

Không. `requireReleaseDeps` nhắm tới SNAPSHOT dependencies. `banDynamicVersions` có phạm vi rộng hơn: ranges, `LATEST`, `RELEASE` và snapshots. Chạy cả hai có thể hơi trùng trách nhiệm, nhưng giúp policy đọc rõ ràng: release không dùng snapshot và cũng không dùng những dynamic version schemes khác.

### 10.3. `requirePluginVersions` và thiếu plugin version mặc định

Ngay cả khi `<build>` đã ghim compiler/surefire/jar, các lifecycle phases khác có thể dùng plugin không được liệt kê tường minh (install/deploy/resources/clean tùy cấu hình). Nếu bật `requirePluginVersions`, phải **pin các plugin tương ứng** trước khi đặt fail policy, đặc biệt trong parent POM dùng chung.

Không đơn giản thêm rule rồi coi một build fail là "phát hiện dependency version range" nếu lý do thật là plugin version thiếu.

### 10.4. BOM và dependencyManagement không phải lockfile

Dùng BOM có thể gom version definitions:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là fragment minh họa, BOM artifact không được khẳng định tồn tại. Nếu BOM version `1.0.0` là **immutable** và nội dung được bảo vệ, đó là cách giúp nhiều modules áp phiên bản nhất quán.

Tuy nhiên:

- BOM vẫn có thể chứa dependency versions động.
- Repository có thể bị overwrite cùng GAV.
- Plugin versions không tự được BOM quản lý.
- Không có cơ chế lock từ BOM tự đóng băng toàn bộ transitive graph/digests.

**BOM giúp quản lý versions; lock/preservation của binary inputs còn cần quy trình riêng.**

## 11. Chính sách repository và mirror cho CI release

CI release nên có một cấu hình chung về repository manager, quyền truy cập và upstreams.

Một `settings.xml` minh họa để tất cả repository lookups đi qua một manager:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <mirrors>
        <mirror>
            <id>approved-manager</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.invalid/group</url>
        </mirror>
    </mirrors>
</settings>
```

URL `.invalid` **không thể chạy thật**. Mục đích là chỉ vị trí cấu hình, cần thay bằng mirror tin cậy của tổ chức và đặt credentials qua secure CI settings (nếu cần).

### 11.1. Định tuyến thống nhất chưa phải policy bất biến

Một manager chuẩn có thể:

- Cho phép upstream whitelist.
- Không cache từ repository ngẫu nhiên.
- Chặn overwrite release coordinates.
- Tách snapshot repository và release repository.
- Bảo vệ metadata và checksum.
- Ghi audit log phục vụ truy xuất nguồn tải.

Nhưng nếu người vận hành thay upstream/cấu hình manager hoặc mirror chưa khóa release artifacts, việc `mirrorOf=*` không tự đóng băng bytes.

### 11.2. Releases và snapshots policy trong POM/settings

Fragment phù hợp release-only repository:

```xml
<repository>
    <id>approved-releases</id>
    <url>https://repo.example.invalid/releases</url>
    <releases>
        <enabled>true</enabled>
        <updatePolicy>daily</updatePolicy>
        <checksumPolicy>fail</checksumPolicy>
    </releases>
    <snapshots>
        <enabled>false</enabled>
    </snapshots>
</repository>
```

Một `pluginRepository` tương tự có thể cần thiết nếu manager áp policy riêng cho plugin resolution. Cấu hình `snapshots=false` trong **một repository** không phải bằng chứng tất cả repositories đều tắt snapshot.

**Không hardcode credentials trong POM.** Repo IDs của `settings.xml` server credentials cần khớp mirror/repo IDs thực tế theo Maven authentication model.

### 11.3. Test environment phải dùng cùng nguồn như release

Rủi ro điển hình:

```text
Developer: Central trực tiếp
Pull request CI: proxy mirror A
Release CI: repository manager B
Production rebuild: local cache C
```

Cùng POM có thể tải khác metadata hoặc artifact. Tổ chức nên thống nhất repo manager/snapshot policy, lưu resolved graph/hash và kiểm tra giữa các environments.

Nếu release cần dựng lại nhiều năm sau, một mirror sống phụ thuộc Internet hiện tại chưa chắc tái tạo được; cần artifact retention/archives đủ lâu.

## 12. So sánh hai build độc lập đúng cách

Không nên dùng hai lần chạy nối tiếp trong cùng workspace/cache rồi nói “đã chứng minh reproducible”; cả hai có thể dùng cùng cache và bỏ qua remote resolution.

Một thử nghiệm nghiêm ngặt hơn:

1. Checkout **cùng commit/tag** vào hai workspace sạch tách biệt.
2. Dùng **cùng Maven/JDK versions** hoặc ghi rõ sự khác biệt chủ đích.
3. Áp **cùng `settings.xml`/active profiles** và approved mirrors.
4. Cấp **hai local repositories** tách biệt.
5. Chạy cùng command build, không skip tests/quality gates.
6. Lưu resolved dependency trees và toolchain metadata.
7. Tính SHA-256 của **artifact cuối** sau `package/verify`.
8. Đối chiếu JAR byte digests và test results.
9. Nếu hashes khác, xem archive entries, timestamps, compiler/toolchain/plugins/dependencies.
10. Nếu digests giống, ghi rõ phạm vi artifact/env đã so, không tuyên bố source integrity được chứng thực chỉ từ hash.

### 12.1. Ví dụ Linux/macOS

Giả sử đã chuẩn bị hai checkout độc lập:

```text
workspace/repro-a/
workspace/repro-b/
```

Có thể chạy mỗi workspace với repo cache riêng:

```bash
cd workspace/repro-a
mvn -B -ntp -Dmaven.repo.local=/tmp/m2-repro-a clean verify
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -DoutputType=json -DoutputFile=target/tree-a.json

cd ../repro-b
mvn -B -ntp -Dmaven.repo.local=/tmp/m2-repro-b clean verify
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -DoutputType=json -DoutputFile=target/tree-b.json
```

**Lưu ý:** command `dependency:tree` cũng cần dùng `-Dmaven.repo.local` tương ứng nếu muốn đọc đúng cache tách biệt; ví dụ tách command ở trên là demo về graph, nhưng trong CI thật phải thêm chính property ấy cho lần gọi dependency plugin. Không để diagnostic command bí mật dùng lại cache thường.

So SHA-256 các outputs:

```bash
sha256sum workspace/repro-a/target/repro-risk-demo-1.0.0.jar
sha256sum workspace/repro-b/target/repro-risk-demo-1.0.0.jar
```

Nếu đang ở một thư mục con sau các lệnh `cd`, phải dùng **đường dẫn thực tế tương ứng**. Đây là câu lệnh minh họa khi chạy từ **thư mục cha** có `workspace/repro-a` và `workspace/repro-b`; không chạy nguyên văn từ `workspace/repro-b` mà không sửa path.

### 12.2. Ví dụ Windows PowerShell

Khi có hai workspaces `repro-a` và `repro-b` ở cùng thư mục:

```powershell
Get-FileHash -Algorithm SHA256 .\repro-a\target\repro-risk-demo-1.0.0.jar
Get-FileHash -Algorithm SHA256 .\repro-b\target\repro-risk-demo-1.0.0.jar
```

Kết quả có thể in SHA-256 ở chữ hoa, Bash có thể là chữ thường. Hãy chuẩn hóa case khi so digest hex.

### 12.3. So sánh dependency graphs

`tree-a.json` và `tree-b.json` cho bạn biết effective/resolved versions. Có thể khác format chi tiết theo Dependency Plugin version; đã pin `3.11.0` để giảm thay đổi ngoài ý muốn.

**Lưu ý:** tree giống nhau **không chứng minh bytes của mỗi dependency giống**. Nếu manager cho overwrite, cùng `groupId:artifactId:version` vẫn có thể trả artifact bytes khác. Khi cần audit sâu, lưu checksums thực tế cho project dependencies và plugin artifacts.

### 12.4. Nếu chưa có artifact reproducible từ đầu

Có thể phân tích nguyên nhân theo tầng:

```text
Khác source commit?          -> Sửa checkout/tag
Khác Maven/JDK?              -> Ghim toolchain
Khác dependency graph?       -> Pin versions/Enforcer/mirror
Graph giống nhưng bytes khác?-> So dependency JAR/POM digests
Inputs giống nhưng JAR khác? -> Archive timestamps, file order, compiler,
                               generated files, locale, OS line endings
```

Đừng ngay lập tức thêm `-o` hoặc xóa cache để “chữa” hash mismatch; cần xác định nguyên nhân trước.

## 13. “Lockfile” trong Maven: điều gì có và chưa có?

Các hệ sinh thái npm/pnpm/Cargo/Gradle có những cơ chế lock/verification riêng. Với Maven 3.x tiêu chuẩn, **`pom.xml` cùng `dependencyManagement` không tự cung cấp một lockfile đầy đủ chứa exact transitive versions và SHA-256 của mọi artifact** theo cách có thể bật một flag là bảo đảm mọi nguồn tải.

Một số lựa chọn tăng kiểm soát:

- Pin direct dependency versions và plugin versions.
- Dùng BOM/parent POM version đã publish immutable.
- Chạy Maven Enforcer để cấm dynamic versions.
- Lưu JSON `dependency:tree` của release.
- Lưu checksums của resolved input JAR/POM/plugin artifacts qua CI tooling phù hợp.
- Dùng repository manager approved/immutable và artifact retention.
- Dùng Maven Wrapper để chọn Maven distribution/version nhất quán (cũng cần verify wrapper/distribution provenance).
- Ghim JDK toolchain và môi trường build image.
- Tạo SBOM/build provenance và ký attestations nếu tổ chức yêu cầu.

### 13.1. Vì sao không chỉ dùng `dependency:go-offline`?

Dependency Plugin có goal tải dependencies/plugins để giúp build offline:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:go-offline
```

Nó hữu ích để **prefetch/cache**, nhưng không tự khóa versions, không bảo đảm mọi dynamic plugin trong tương lai đều đã cached, và không chứng thực artifact inputs bằng chữ ký.

Một build offline có thể không hoạt động nếu cần plugin/report goal chưa prefetch hoặc configuration phụ thuộc profile khác. Nếu goal hoàn tất, vẫn cần kiểm tra snapshot/versions/bytes.

### 13.2. Vì sao `dependency:tree` không đủ để rollback?

Nếu hôm nay `tree.json` ghi `org.example:api:1.2.0-SNAPSHOT`, ngày mai same base SNAPSHOT có binary khác, tree text **có thể trông giống nhau**. Cần ghi timestamped snapshot identity/digest và giữ bytes. Release rollback phải chọn **đúng binary đã deploy trước**, không chỉ dependency text.

## 14. Snapshot, range và repository risk trong các build quan trọng

### 14.1. Release artifact có project version là SNAPSHOT

Ngay cả khi tất cả dependencies là releases, nếu chính project có:

```xml
<version>1.0.0-SNAPSHOT</version>
```

nó không phải một release coordinate cố định. Maven Enforcer `requireReleaseVersion` giúp chặn kiểu project version này trong policy release.

### 14.2. Parent POM hoặc BOM là SNAPSHOT

Một child project có thể có mọi direct dependencies pinned nhưng dùng parent:

```xml
<parent>
    <groupId>org.example</groupId>
    <artifactId>build-parent</artifactId>
    <version>4.0.0-SNAPSHOT</version>
</parent>
```

Parent có thể thay build plugin config, compiler options, profiles hoặc properties, làm artifact đổi mà child POM không đổi. Đây là fragment minh họa, không phải parent artifact có thật.

**Không chỉ scan `<dependencies>`.** Kiểm tra parent, imported BOM, build plugins, pluginManagement và extensions. Enforcer rules có scope cụ thể; khi cần policy toàn bộ input graph, kiểm tra thêm bên ngoài Maven.

### 14.3. Plugin version không ghim

Một project để:

```xml
<plugin>
    <artifactId>maven-compiler-plugin</artifactId>
</plugin>
```

có thể dùng phiên bản bị quyết định bởi effective parent/pluginManagement/default mechanism, và khi môi trường nâng cấp, behavior thay đổi. Hãy pin effective plugin versions và lưu `mvn -version`; không nhầm plugin dependency với application dependency.

### 14.4. Repository overwrite một bản release

Một repository misconfiguration có thể cho phép upload file khác cùng GAV `org.example:api:1.2.0`. Cả POM lẫn `dependency:tree` vẫn có thể ghi version `1.2.0`.

Kiểm tra bằng **artifact digest** và repository immutability/audit log. Snapshot updatePolicy không có tác dụng phòng ngừa overwrite release bytes.

### 14.5. Proxy/Mirror trả stale metadata

Một mirror chưa refresh `maven-metadata.xml` có thể chọn range version cũ hoặc snapshot cũ. `-U` có thể không giải quyết nếu mirror upstream chưa đồng bộ; cần điều tra cache TTL, remote sync và proxy rules.

### 14.6. Repository bị gỡ hoặc chuyển domain

Rebuild lịch sử có thể fail vì artifact không còn tải được. Đây cũng là vi phạm khả năng tái lập theo thời gian, dù không tạo ra binary mới. Cần lưu artifact inputs/repository retention theo SLA và kiểm tra phương án phục hồi.

### 14.7. Dependency cùng version nhưng loại/classifier khác

Maven coordinates còn có `type`/`classifier` khi cần. Nếu một build dùng `tests` classifier, native artifact khác hoặc platform-specific classifier, **chỉ so groupId/artifactId/version là chưa đầy đủ**. Ghi đúng resolved artifact coordinates và checksum.

### 14.8. Version range của plugin không phải dependency range

Với plugin declarations, Maven có plugin resolution model và pluginManagement riêng; Enforcer `banDynamicVersions` nhắm dependency versions theo rule, **không thay việc rà plugin versions**. Dùng `requirePluginVersions` và kiểm soát plugin repositories nếu muốn chính sách nghiêm hơn.

### 14.9. Annotation processor tải từ remote

Java annotation processors, code generators hoặc Maven plugins có thể tải external binaries, gọi network APIs hoặc sinh timestamps. Giữ direct library versions cố định **không đủ** nếu generated output hoặc plugin inputs động.

### 14.10. Build trong container cũng có rủi ro

Docker image tag `latest` có thể trỏ image khác vào thời điểm sau. `JAVA_HOME` và Maven Wrapper có thể thay JDK/plugin versions nếu container hay distribution bị đổi. Khi yêu cầu reproducibility mạnh, nên pin image by digest, JDK version và Maven distribution checksum theo policy.

## 15. Troubleshooting theo hiện tượng

| Hiện tượng | Có thể do | Cách xử lý |
| --- | --- | --- |
| Hôm qua PASS, hôm nay FAIL mà không sửa code | SNAPSHOT/range chọn version mới | So dependency trees và metadata |
| Máy A PASS, máy B FAIL | Cache/mirror/JDK khác | Ghi effective settings, toolchain, artifact hashes |
| `mvn -U` làm test khác kết quả | Snapshot/metadata refresh | Pin release versions; điều tra changed artifacts |
| `mvn -o` PASS chỉ ở một máy | Cache máy kia thiếu hoặc khác | Dùng prefetch/isolated repository, không coi offline là lock |
| Enforcer báo `banDynamicVersions` | SNAPSHOT/range/LATEST/RELEASE | Sửa dependency version cố định |
| Enforcer báo `requireReleaseVersion` | Project version là SNAPSHOT | Dùng release POM version đúng |
| Dependency tree dùng version khác POM | Version mediation/management/profile/range | Xem effective POM và full tree |
| Tree giống nhưng JAR khác hash | Input bytes/generator/plugin/OS khác | So checksums, buildinfo và archive entries |
| Plugin behavior thay dù deps pinned | Plugin/default version hoặc repo khác | Ghim plugins, pluginRepositories |
| Mirror trả 404 | Artifact chưa được proxy/retained | Kiểm tra manager/upstream, không tắt policy |
| `checksumPolicy=fail` báo mismatch | Mirror/cache/corrupt/modified artifact | Điều tra checksum source, không bypass bằng ignore |
| Parent POM không resolve | Repo/parent SNAPSHOT/profile khác | Pin parent, kiểm tra relativePath và repository |
| Ranges chọn prerelease ngoài ý muốn | Version ordering/qualifiers | Pin version hoặc áp explicit policy |
| BOM nâng version làm graph đổi | Imported BOM version/nội dung mới | Pin BOM, lưu graph/approval |
| Release repo có cùng GAV nhưng khác bytes | Overwrite hoặc source không tin cậy | Dừng release, so digests và audit logs |
| `mvn dependency:tree` lỗi plugin | Plugin chưa cached hoặc repo blocked | Kiểm tra plugin repository, mirror, offline flags |
| `go-offline` PASS nhưng offline build FAIL | Goal chưa prefetch input/profile-specific plugin | Ghi dependency/plugin inventory theo invocation thực |
| `project.build.outputTimestamp` có nhưng JAR khác | Timestamp chỉ một điều kiện | So tools, archive entries, line endings, codegen |
| `target` JAR bị thay sau QA | Build lại giữa jobs | Promote file đã kiểm tra, verify deployed digest |
| Tests 0 nhưng BUILD SUCCESS | Test discovery/skip misconfiguration | Fail CI theo expected test count |
| Maven Central trực tiếp vs mirror group khác | settings/mirror mapping | Dùng cấu hình chuẩn và lưu origins |

### 15.1. Runbook xử lý incident

Khi thấy build khác kết quả:

1. **Không deploy** artifact mới nếu checksum khác bản đã được phê duyệt.
2. Xác nhận cùng Git commit/tag, POM và active profiles.
3. Ghi Maven/JDK versions, OS/build image và `mvn -version`.
4. So effective POM/settings; lưu bản đã redact.
5. So resolved dependency graph, plugin versions và repository origins.
6. Với SNAPSHOT, ghi timestamped version, metadata và hash artifact.
7. Với ranges, ghi version cụ thể được chọn ở từng run.
8. Kiểm tra local repo/mirror cache, không xóa bừa.
9. So JAR/POM SHA-256, rồi so archive entries nếu cần.
10. Khắc phục nguồn thay đổi bằng pinning/policy hoặc environment; rerun ở workspace sạch.
11. Lưu nguyên nhân và cập nhật CI gates để ngăn lặp.

## 16. Checklist trước khi đánh dấu build là tái lập

- [ ] Git commit/tag và source inputs đã được xác định.
- [ ] Maven/JDK versions và build image/toolchain đã ghi rõ.
- [ ] Direct dependency versions được ghim.
- [ ] Không có SNAPSHOT trong release dependency graph nếu policy cấm.
- [ ] Không có version ranges/LATEST/RELEASE trong release POM.
- [ ] Parent POM và imported BOM có versions ổn định.
- [ ] Plugin và build extension versions được kiểm soát.
- [ ] Enforcer rules hoạt động trong CI release.
- [ ] Effective POM/profiles/settings được ghi và kiểm tra.
- [ ] Repositories và pluginRepositories dùng nguồn đã duyệt.
- [ ] Mirror/repository manager không cho overwrite release.
- [ ] Update policies và snapshot permissions phù hợp môi trường.
- [ ] Dependency tree được lưu cho đúng CI run.
- [ ] Artifact JAR/POM input digests và origins được ghi khi cần.
- [ ] Local repository cho CI test được cô lập đúng mục tiêu.
- [ ] Test results có test count thực, không chỉ BUILD SUCCESS.
- [ ] `project.build.outputTimestamp` và plugin reproducible modes phù hợp.
- [ ] Không nhúng giờ/run ID/random/path máy cá nhân vào artifacts.
- [ ] So output SHA-256 từ hai build độc lập có kiểm soát.
- [ ] Deployed artifact digest khớp tested/approved digest.
- [ ] Logs, configs và artifacts được lưu đủ lâu để điều tra.
- [ ] Không chia sẻ credentials/token trong outputs hoặc logs.

## 17. Câu hỏi tự kiểm tra

**1.** SNAPSHOT dùng cùng version có bảo đảm JAR bytes giống nhau không?  
**Đáp án:** Không. Snapshot metadata có thể chọn timestamped artifact mới.

**2.** `updatePolicy=never` có khóa version không?  
**Đáp án:** Không; nó chỉ ảnh hưởng việc thử cập nhật metadata, có thể giữ cache cũ.

**3.** `mvn -U` có làm build reproducible hơn không?  
**Đáp án:** Không mặc định; nó có thể cập nhật SNAPSHOT/metadata làm inputs đổi.

**4.** `mvn -o` có tương đương một lockfile không?  
**Đáp án:** Không; nó dùng local cache hiện có.

**5.** `[3.10,4.0)` nghĩa là gì?  
**Đáp án:** Version ít nhất 3.10 và nhỏ hơn 4.0; có thể thay đổi khi repository có phiên bản mới.

**6.** Vì sao range `[1.0,2.0)` có thể chọn `2.0-rc1`?  
**Đáp án:** Vì qualifier/pre-release `2.0-rc1` được Maven so nhỏ hơn `2.0`.

**7.** `LATEST`/`RELEASE` nên dùng trong release POM không?  
**Đáp án:** Không; chúng là dynamic requirements phụ thuộc metadata.

**8.** Pin direct dependency có tự pin plugin dependencies không?  
**Đáp án:** Không; plugin versions và plugin repositories cần kiểm soát riêng.

**9.** `dependency:tree` có chứa SHA-256 của mỗi JAR không?  
**Đáp án:** Không theo output mặc định; phải thêm inventory/digest tooling.

**10.** `dependency:tree` là lockfile Maven tự đọc lại để ép future build không?  
**Đáp án:** Không.

**11.** Tại sao BOM chưa đủ để bảo đảm reproducible build?  
**Đáp án:** BOM quản lý dependency versions, không tự khóa bytes hoặc plugin inputs.

**12.** MirrorOf `*` có tự bảo đảm repository immutable không?  
**Đáp án:** Không; nó định tuyến requests, policy của manager vẫn phải được kiểm soát.

**13.** Tại sao hai machines có cache khác có thể cho kết quả khác?  
**Đáp án:** Chúng có thể giữ snapshot/metadata/artifact version khác nhau.

**14.** `checksumPolicy=fail` có tự chứng minh nguồn phát hành đáng tin cậy không?  
**Đáp án:** Không; cần expected checksum/chữ ký/provenance từ nguồn tin cậy.

**15.** `banDynamicVersions` có chặn version range không?  
**Đáp án:** Có, theo chính sách rule khi không allow ranges.

**16.** `requireReleaseDeps` và `requireReleaseVersion` khác nhau thế nào?  
**Đáp án:** Một rule xét SNAPSHOT dependencies; một rule xét chính project artifact version.

**17.** `project.build.outputTimestamp` có pin dependencies không?  
**Đáp án:** Không; nó hỗ trợ ổn định archive timestamps, không điều khiển resolver.

**18.** Vì sao hai build cùng dependency tree vẫn khác JAR?  
**Đáp án:** Binary inputs cùng tọa độ có thể khác, hoặc JDK/plugins/OS/codegen/timestamps khác.

**19.** Tại sao cần so POM và JAR hashes?  
**Đáp án:** POM có thể ảnh hưởng transitive dependencies và JAR là binary được dùng; cả hai đều là artifact inputs/outputs quan trọng.

**20.** Có nên xóa `~/.m2` khi gặp mismatch không?  
**Đáp án:** Không như mặc định; dùng repo cache cô lập và chẩn đoán origins.

**21.** Khi release `mvn deploy`, có nên rebuild JAR ở job khác?  
**Đáp án:** Tốt nhất promote đúng file đã QA; nếu rebuild, phải so SHA-256 equality.

**22.** Kết quả `BUILD SUCCESS` có chứng minh tests đã chạy?  
**Đáp án:** Không; phải đọc test runner logs và số tests executed.

**23.** Khi repository bỏ artifact lịch sử, điều gì xảy ra?  
**Đáp án:** Rebuild cũ có thể không hoàn thành; cần artifact retention/archives.

**24.** Tại sao một repository manager chuẩn vẫn cần hash verification?  
**Đáp án:** Vì manager/upstream/cache có thể đổi; URL ổn định không bảo đảm bytes.

## 18. Tài liệu tham khảo chính thức

1. [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — định nghĩa, `outputTimestamp`, plugin support, version ranges.
2. [Apache Maven — POM Reference, Dependency Version Requirements](https://maven.apache.org/pom.html) — soft/hard versions, ranges, prerelease ordering, repositories.
3. [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — mediation, transitive dependencies, dependencyManagement.
4. [Apache Maven — Settings Reference](https://maven.apache.org/settings.html) — repositories, release/snapshot policy, `updatePolicy`, `checksumPolicy`, mirrors.
5. [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings) — `mirrorOf` và repository manager.
6. [Apache Maven Enforcer — banDynamicVersions](https://maven.apache.org/enforcer/enforcer-rules/banDynamicVersions.html) — range, LATEST/RELEASE, SNAPSHOT.
7. [Apache Maven Enforcer — requireReleaseDeps](https://maven.apache.org/enforcer/enforcer-rules/requireReleaseDeps.html) — chặn snapshot dependencies.
8. [Apache Maven Enforcer — Built-in Rules](https://maven.apache.org/enforcer/enforcer-rules/index.html) — requireReleaseVersion, requirePluginVersions, dependencyConvergence.
9. [Maven Dependency Plugin 3.11.0 — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — resolved graph, JSON output.
10. [Maven Dependency Plugin — dependency:go-offline](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html) — prefetch dependencies/plugins.
11. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — `validate`, `verify`, `install`, `deploy`.
12. [Maven Wrapper Plugin / Maven Wrapper](https://maven.apache.org/wrapper/) — Maven distribution/version management.
13. [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html) — quản lý plugin versions.
14. [Apache Maven — Maven 3.10.0 Release Notes](https://maven.apache.org/docs/3.10.0/release-notes.html) — điểm mới về resolver, reproducible default; cần đọc theo Maven version đang dùng.

**Kết luận:** **SNAPSHOT** làm artifact có thể thay bytes với cùng version khai báo; **version range** làm resolved version phụ thuộc repository metadata; **nguồn tải/mirror/cache** có thể đưa vào những POM/JAR khác dù GAV không đổi. Để build tái lập, cần **pin versions, kiểm soát repositories, chặn dynamic inputs, lưu resolved graph/digests và so bytes artifact cuối ở các môi trường độc lập**. `-U`, `-o`, `updatePolicy=never` hay chỉ `BUILD SUCCESS` đều không thay thế những kiểm soát đó.
