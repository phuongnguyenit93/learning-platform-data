# Thứ tự truy cập kho và chẩn đoán artifact không tìm thấy trong Maven

## 1. Vấn đề: tại sao Maven báo không tìm thấy artifact dù “trên kho có file”?

Khi chạy `mvn clean package`, bạn có thể gặp những thông báo như:

```text
Could not resolve dependencies for project ...
Could not find artifact org.example:client-lib:jar:2.0.0
```

hoặc:

```text
... was not found in ... during a previous attempt.
This failure was cached in the local repository ...
```

Nguyên nhân có thể là **tọa độ sai, repository chưa được cấu hình, mirror chặn hoặc chuyển hướng, kho không cho phép loại artifact đó, token hết hạn, mạng/TLS lỗi, hoặc Maven đang dùng một kết quả không tìm thấy đã cache**. Cũng có trường hợp kho đúng nhưng artifact thiếu POM, thiếu JAR, khác classifier hoặc nằm trong snapshot repository khác release repository.

Để chẩn đoán hiệu quả cần trả lời **ba câu hỏi theo thứ tự**:

1. **Maven đang cần tìm artifact nào?** Xác định chính xác `groupId:artifactId:version`, `type`, `classifier`, dependency/plugin/parent/BOM và policy release hay snapshot.
2. **Maven thực sự kiểm tra những kho nào?** Tính đến local repository, effective settings, POM/parent/Super POM, active profiles và mirror.
3. **Khi truy cập kho, chuyện gì đã xảy ra?** Không tìm thấy thật (404), chưa có quyền (401/403), DNS/TLS/timeout, bị Maven chặn HTTP, bị cache hoặc bị offline mode.

**Nguyên tắc trọng tâm:** đọc **error message + tọa độ artifact + repository ID/URL hiệu lực**, không chỉ nhìn dòng “artifact not found” rồi xóa toàn bộ thư mục `~/.m2`.

## 2. Một lần resolve dependency gồm những lớp nào?

Mô hình tư duy đơn giản:

```text
pom.xml + parent POM + active profiles + settings.xml
              |
              v
         Artifact request
      G:A:V:type:classifier
              |
              v
       Local repository manager
      (cache + locally installed)
              |
       chưa thỏa điều kiện?
              v
       Danh sách remote repositories
       theo effective configuration
              |
              v
       Áp dụng mirror selection
       trước từng remote request
              |
              v
       Metadata / POM / JAR / checksum
              |
          thành công?
       /              \
      có              không
      |                 |
      v                 v
 cập nhật cache     lỗi phù hợp / cache kết quả
      |
      v
 dependency graph / classpath / plugin execution
```

Lược đồ này mô tả tư duy, không phải sơ đồ triển khai nội bộ cố định cho mọi Maven/Resolver version. Local repository manager của Maven có thể lưu thông tin **nguồn gốc remote** của artifact; một file đã có trên đĩa không phải lúc nào cũng được coi là hợp lệ với tập repositories của một build khác.

Bốn loại artifact thường dễ lẫn:

| Loại cần resolve | Ví dụ | Vị trí cấu hình quan trọng |
| --- | --- | --- |
| **Project dependency** | `org.apache.commons:commons-lang3:3.14.0` | `<dependencies>`, `<repositories>`, dependency management |
| **Build plugin** | `org.apache.maven.plugins:maven-compiler-plugin:3.13.0` | `<build><plugins>`, `<pluginRepositories>` |
| **Parent POM** | `dev.company:company-parent:pom:1.0.0` | `<parent>`, `relativePath`, repositories |
| **Imported BOM POM** | `dev.company:company-bom:pom:1.0.0` | `<dependencyManagement>` với `type=pom`, `scope=import` |

Một lỗi plugin resolution không nhất thiết được chữa bằng cách thêm `<repository>` của project; Maven dùng cấu hình **plugin repositories** cho việc tìm plugin.

## 3. Local repository: kiểm tra trước, nhưng không phải “cứ có file là dùng”

Vị trí local repository phổ biến:

- Linux/macOS: `~/.m2/repository`.
- Windows: `%USERPROFILE%\.m2\repository`.
- Có thể thay đổi bằng settings hoặc `-Dmaven.repo.local=/path/to/repository`.

Với artifact `org.apache.commons:commons-lang3:3.14.0`:

```text
~/.m2/repository/
└── org/apache/commons/commons-lang3/3.14.0/
    ├── commons-lang3-3.14.0.pom
    └── commons-lang3-3.14.0.jar
```

Local repository chứa **artifact đã tải từ remote** và **artifact do `mvn install` cài vào**. Khi các artifact hợp lệ đã sẵn có và thỏa bối cảnh resolution, Maven thường không cần tải lại từng file ở mỗi build.

Tuy nhiên, Maven Resolver với **enhanced local repository manager** có thể lưu metadata về repository nguồn, chẳng hạn file `_remote.repositories`. Ví dụ artifact từng tải từ repository A nhưng build mới chỉ cho phép repository B có thể không coi file cache đó là đủ điều kiện, dù cùng tọa độ và file vẫn nằm trên disk. Không nên dùng việc nhìn thấy `.jar` trong `~/.m2` làm bằng chứng Maven nhất định sẽ sử dụng nó.

Các khả năng thường gặp:

- **Cache hoàn chỉnh, nguồn hợp lệ:** Maven có thể dùng artifact tại local.
- **Local `.pom` có nhưng `.jar` thiếu:** chưa đủ cho dependency kiểu JAR.
- **POM phụ thuộc/parent không resolve được:** artifact JAR có thể tồn tại nhưng model của dependency chưa dựng được.
- **File metadata nguồn hoặc trạng thái cache mâu thuẫn:** Maven cần kiểm tra remote tương ứng.
- **Artifact cài bằng `mvn install`:** thường được nhận là artifact local install, khác với bản tải từ remote.
- **Chạy `-o` offline:** Maven không được truy cập remote; nếu local thiếu điều cần thiết thì build thất bại.

Đừng chỉnh tay `_remote.repositories` hoặc xóa ngẫu nhiên cache để lừa Maven nhận artifact. Hãy xác định repository thực sự phải cung cấp artifact.

## 4. Thứ tự các remote repository mà Maven xem xét

Theo hướng dẫn **Setting up Multiple Repositories** của Apache Maven, khi cần lấy artifact từ remote, Maven xem xét các địa chỉ repository theo thứ tự ưu tiên cấu hình (sau khi đã xử lý project model và active profiles):

1. **Effective settings**: cấu hình từ global `settings.xml` và user `settings.xml`.
2. **Local effective build POM**: `pom.xml` đang build, các parent POM theo chuỗi kế thừa, rồi **Super POM**.
3. **Effective POMs nằm trên dependency path** dẫn tới artifact cần resolve.

Ở mỗi nguồn cấu hình, **repositories trong những profile được kích hoạt** được xem xét theo cơ chế thứ tự profile của Maven. Các cấu hình cùng ID được hợp nhất/ghi đè theo quy tắc effective model, nên đừng hiểu đơn giản rằng Maven cứ nối mọi danh sách XML nguyên trạng rồi gọi tất cả.

**Trước khi gửi request tải từ một repository, Maven áp dụng cấu hình mirror**. Do đó thứ tự cấu hình logic và URL HTTP(S) thực sự được gọi **có thể khác nhau**.

Ví dụ:

```text
Effective repository candidate list:
  private-releases
  central

Mirrors in settings:
  mirrorOf="*" → corporate-group

Actual remote endpoint for both candidates:
  https://repo.example.invalid/repository/maven-group/
```

Trong trường hợp này, việc sửa `<url>` của `central` trong POM mà bỏ qua `mirrorOf="*"` có thể không thay đổi URL mà Maven sử dụng để tải.

### 4.1. Super POM và Maven Central

Nếu project không khai repository bổ sung và không có mirror ghi đè, Maven sử dụng repository mặc định từ **Super POM**, thường được nhận diện bởi ID `central` và URL Maven Central. Nhưng một doanh nghiệp có thể cấu hình mirror bắt toàn bộ request qua proxy/nội bộ.

**Không nên kết luận “Maven đang kết nối trực tiếp Maven Central” chỉ vì error/log chứa repository ID `central`.** Hãy kiểm tra mirror selection và URL thực tế. Với Maven hiện đại, HTTPS là mặc định phù hợp; đừng cấu hình lại thành HTTP không bảo mật để khắc phục lỗi TLS.

### 4.2. Repository trong settings khác repository trong POM thế nào?

Trong POM, project có thể khai:

```xml
<repositories>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.invalid/repository/team-releases/</url>
    </repository>
</repositories>
```

Đây là **đoạn POM minh họa**, không phải địa chỉ có thật. Trong `settings.xml`, repository có thể xuất hiện **bên trong một profile**:

```xml
<profiles>
    <profile>
        <id>internal-repositories</id>
        <repositories>
            <repository>
                <id>team-releases</id>
                <url>https://repo.example.invalid/repository/team-releases/</url>
            </repository>
        </repositories>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>internal-repositories</activeProfile>
</activeProfiles>
```

Đây là **đoạn trích bên trong `<settings>`**. Một profile **không active** có thể khiến repository bạn nhìn thấy trong file settings **không tham gia resolution**.

Maven sử dụng **repository ID** để nhận diện repository trong metadata/cấu hình; mỗi ID cần được quản lý nhất quán. Nếu POM và settings dùng cùng ID, effective settings có thể thay thế repository trong POM theo cơ chế ưu tiên của Maven. Cần nhìn **effective settings/POM** thay vì chỉ đọc XML nguồn.

### 4.3. Lệnh quan sát nguồn cấu hình

```bash
mvn help:active-profiles
mvn help:effective-settings
mvn help:effective-pom -Dverbose
```

- `help:active-profiles`: profile nào đang hoạt động.
- `help:effective-settings`: cấu hình settings Maven đã hợp nhất, bao gồm mirror, profiles, servers và repository liên quan.
- `help:effective-pom -Dverbose`: POM hiệu lực, có thể thêm chú thích nguồn cho các phần của model tùy version Help Plugin.

**Lưu ý bảo mật:** effective settings và log debug có thể chứa thông tin cấu hình nhạy cảm; các plugin/phiên bản có thể ẩn password theo cách khác nhau. Không gửi output nguyên văn lên ticket/public chat khi chưa redact credentials/token/URL chứa thông tin xác thực.

## 5. Mirror: nguồn gây bất ngờ phổ biến nhất

Mirror được cấu hình **trong settings**, không phải trong POM của thư viện:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>corporate-group</id>
            <url>https://repo.example.invalid/repository/maven-group/</url>
            <mirrorOf>*</mirrorOf>
        </mirror>
    </mirrors>
</settings>
```

**Đây chỉ là settings mẫu minh họa**: domain `repo.example.invalid` không hoạt động. Nếu dùng nguyên mẫu, mọi request bị chuyển về URL giả và build thật sẽ lỗi. Hãy thay bằng repository manager thật do tổ chức quản lý.

Ý nghĩa:

- `id`: ID của **mirror endpoint** thực sự.
- `url`: nơi Maven gửi request sau khi áp dụng mirror.
- `mirrorOf=*`: mirror cho tất cả repository ID đủ điều kiện.
- `mirrorOf=central`: mirror riêng cho repository có ID `central`.
- `mirrorOf=external:*`: bắt các repository không thuộc localhost hoặc file-based.
- `mirrorOf=*,!internal-staging`: bắt mọi repository trừ `internal-staging`.

Đặt **một** mirror cho một repository trong một lần resolution, không phải “mirror A lỗi thì thử mirror B như hai remote bình thường”. Nếu bạn muốn gộp nhiều nguồn, sử dụng **repository manager group/proxy** được cấu hình upstream đúng cách.

### 5.1. Khi nhiều mirror cùng khớp

Maven tìm **mirror có `mirrorOf` khớp chính xác repository ID** trước. Nếu không có exact match, nó chọn **mirror đầu tiên** khớp theo quy tắc wildcard/list, vì vậy **thứ tự khai mirrors trong settings có ý nghĩa**.

Ví dụ:

```xml
<mirrors>
    <mirror>
        <id>all-proxy</id>
        <mirrorOf>*</mirrorOf>
        <url>https://repo.example.invalid/repository/group/</url>
    </mirror>
    <mirror>
        <id>central-proxy</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.invalid/repository/central-proxy/</url>
    </mirror>
</mirrors>
```

Đây là đoạn settings minh họa. Với repository ID `central`, mirror có exact match `central-proxy` được ưu tiên hơn wildcard `all-proxy` dù xuất hiện sau.

### 5.2. Credentials phải khớp ID endpoint thực tế

Nếu Maven dùng mirror `corporate-group` và repository đó cần xác thực, credentials trong `settings.xml` thường phải được cấu hình dưới `<servers><server><id>corporate-group</id>`. Chỉ cấu hình server ID của repository gốc có thể không đủ sau khi nó được mirror.

```xml
<servers>
    <server>
        <id>corporate-group</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_PASSWORD}</password>
    </server>
</servers>
```

Đây là **đoạn settings**, biến môi trường phải được CI/terminal cung cấp thực. Không commit plaintext token/password vào POM, script hoặc repository Git. Khác biệt giữa 401 (chưa xác thực đúng) và 403 (thường là không đủ quyền/policy) phải được kiểm tra cùng server ID và quyền của token.

### 5.3. Maven 3.8.1+ và HTTP blocker

Các bản Maven 3.8.1+ thường có cấu hình chặn những repository HTTP bên ngoài (không an toàn), khiến log nhắc `maven-default-http-blocker`/`Blocked mirror for repositories`. Đây không phải dấu hiệu artifact chắc chắn không tồn tại. **Sửa repository URL thành HTTPS hoặc cấu hình proxy an toàn**; không vô hiệu hóa xác minh TLS/HTTP blocker chỉ để build chạy.

## 6. Dependency repository, plugin repository và nơi deploy là ba khái niệm khác nhau

| Cấu hình | Dùng cho | Không nên lẫn với |
| --- | --- | --- |
| `<repositories>` | Tìm project dependencies và metadata thích hợp | Plugin repository |
| `<pluginRepositories>` | Tìm Maven build plugins/metadata plugin | Dependency repository |
| `<distributionManagement>` | Chỉ nơi **upload/deploy** artifact khi phát hành | Nơi Maven tự động tải dependency |

Ví dụ dự án cần cả dependency từ private repo và plugin nội bộ:

```xml
<repositories>
    <repository>
        <id>company-libs</id>
        <url>https://repo.example.invalid/repository/maven-libs/</url>
    </repository>
</repositories>

<pluginRepositories>
    <pluginRepository>
        <id>company-plugins</id>
        <url>https://repo.example.invalid/repository/maven-plugins/</url>
    </pluginRepository>
</pluginRepositories>
```

Đây là **hai đoạn POM minh họa**, cần đặt trong POM hoàn chỉnh. Nếu lỗi `PluginResolutionException` cho compiler/plugin khác, hãy kiểm tra `pluginRepositories`, mirror và plugin version chứ không chỉ `repositories`.

**`distributionManagement` không phải nơi bổ sung repository tải dependency.** Một POM khai URL publish chỉ giúp Deploy Plugin xác định đích phát hành; nó không tự bảo đảm Maven sẽ tìm thấy các artifact ở URL ấy khi build.

### Lỗi “No plugin found for prefix ...”

Ngoài việc resolve plugin artifact, cú pháp viết tắt `mvn myplugin:goal` còn có thể cần **plugin prefix metadata** và plugin group configuration. Nếu plugin được triển khai nội bộ, hãy kiểm tra `pluginGroups` trong settings, plugin repositories và metadata, hoặc gọi goal bằng **tọa độ đầy đủ**:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Việc ghi đầy đủ `groupId:artifactId:version:goal` giúp tránh lỗi **prefix lookup**, nhưng Maven vẫn phải resolve plugin version và phụ thuộc của plugin.

## 7. POM, JAR và metadata: Maven tải những file nào?

Tọa độ artifact Maven được dùng để tạo path theo quy ước. Ví dụ:

```text
GAV:
  groupId    = org.apache.commons
  artifactId = commons-lang3
  version    = 3.14.0

Repository relative path:
  org/apache/commons/commons-lang3/3.14.0/

Expected artifacts:
  commons-lang3-3.14.0.pom
  commons-lang3-3.14.0.jar
```

`.pom` mô tả project và dependencies, `.jar` chứa bytecode/resources. Một dependency `type=pom` thì cần POM artifact, không nhất thiết có JAR tương ứng. Nếu artifact dùng `classifier` như `tests` hoặc `sources`, Maven cần file với classifier ấy; **JAR không classifier không thay thế được artifact classifier bị thiếu**.

### 7.1. Metadata dùng cho việc gì?

Các file như `maven-metadata.xml` giúp Maven hoặc repository resolver tìm thông tin version/snapshot, phiên bản timestamped của snapshot, v.v. Với release version cố định, Maven thường có thể dựng path trực tiếp tới POM/JAR. Nhưng với `1.2.0-SNAPSHOT`, metadata remote có vai trò xác định snapshot build cụ thể.

Snapshot thường phát hành ở dạng timestamped artifacts trên remote repo, ví dụ ý niệm:

```text
1.2.0-SNAPSHOT/
  maven-metadata.xml
  sample-lib-1.2.0-20261015.091122-3.pom
  sample-lib-1.2.0-20261015.091122-3.jar
```

Đây chỉ là tên minh họa. Không sửa tay metadata rồi tin Maven đã có phiên bản snapshot mới. Dùng quy trình publish đúng và kiểm tra metadata trên repository manager.

### 7.2. Release và snapshot policies

Repository có thể quy định tải release, snapshot và update policy riêng. Ví dụ:

```xml
<repositories>
    <repository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
        </snapshots>
    </repository>
</repositories>
```

Đây là **đoạn POM chỉ để giải thích**, URL phải được thay. Với cấu hình này, repository chỉ cho phép tìm snapshots, không phải release thông thường. Nếu khai `<version>2.0.0</version>` nhưng chỉ mở snapshot repo, Maven có thể không tìm được dù server còn hoạt động.

Các giá trị `updatePolicy` phổ biến: `always`, `daily` (thường là mặc định), `interval:X` (phút), `never`. Chúng ảnh hưởng thời điểm Maven kiểm tra lại metadata/artifact theo quy tắc tương ứng; **không bảo đảm server có phiên bản mới** hoặc cho phép bỏ qua lỗi quyền mạng.

## 8. Negative cache: vì sao kho đã có artifact mà Maven vẫn báo “previous attempt”?

Khi Maven từng thử tải một artifact/metadata và nhận **không tìm thấy**, Maven Resolver có thể ghi trạng thái lỗi vào local repository, thường qua file hậu tố:

```text
commons-lang3-3.14.0.jar.lastUpdated
commons-lang3-3.14.0.pom.lastUpdated
maven-metadata-<repoId>.xml.lastUpdated
```

Tên metadata và layout cụ thể tùy loại artifact/Resolver version. Dấu `.lastUpdated` có thể lưu thông tin request/lỗi và thời điểm kiểm tra lại. Nếu lỗi bị cache, một lần build sau có thể không truy cập network cho tới khi hết update interval hoặc có yêu cầu cập nhật cưỡng bức.

Ví dụ message:

```text
... was not found in https://repo.example.invalid/... during a previous attempt.
This failure was cached in the local repository and resolution is not reattempted
until the update interval ... has elapsed or updates are forced
```

Phân biệt ít nhất hai loại nguyên nhân:

1. **Artifact thực sự không tồn tại** (tọa độ/version/classifier sai hoặc chưa publish) — retry bao nhiêu lần cũng không tạo ra artifact.
2. **Kết quả “không tìm thấy” cũ** — artifact mới được publish sau lần thử trước, nhưng Maven chưa kiểm tra lại do cache.

Theo tài liệu Maven Resolver, Maven 3 cache lỗi loại *not found* trong local repository, còn lỗi transfer/auth/timeout thuộc loại khác và không mặc nhiên được xử lý giống negative cache. Chính sách cụ thể có thể thay đổi theo Maven/Resolver version.

### `-U` làm gì?

```bash
mvn -U clean package
```

`-U` yêu cầu Maven buộc kiểm tra cập nhật snapshots và những release bị thiếu theo hành vi CLI phiên bản Maven; nó thường hữu ích khi bạn vừa publish artifact mà Maven vẫn giữ kết quả not-found cũ.

**`-U` không phải lệnh thần kỳ:**

- Không sửa tọa độ GAV sai.
- Không mở khóa token hết hạn/401/403.
- Không bỏ qua TLS/certificate.
- Không sửa mirror trỏ sai URL.
- Không tự tạo artifact chưa được publish.
- Không bảo đảm thay thế một release JAR đã cache hợp lệ bằng nội dung release khác: **không nên overwrite release bất biến**.

Nếu `-U` vẫn lỗi, hãy đi tiếp tới repository ID/URL, policy, metadata, quyền và log, không chạy `-U` liên tục.

### `-o` và offline mode

```bash
mvn -o clean package
```

`-o` nghĩa là **offline**: Maven không dùng mạng để tải artifact/plugin/metadata thiếu. Nếu local repo chưa có dependencies hoặc plugins, lỗi trong offline mode là điều dự kiến. Đừng chẩn đoán “Maven Central bị hỏng” từ một command đang chạy `-o`.

### Không xóa toàn bộ `~/.m2/repository` một cách vội vàng

Lệnh xóa trọn local repository có thể làm mất hàng GB cache, các artifact nội bộ chỉ cài bằng `mvn install` và khiến mọi build tải lại. Khi cần thử với cache sạch để cô lập lỗi, ưu tiên **local repo riêng cho lệnh test** hoặc chỉ can thiệp tới GAV cụ thể theo quy trình được cho phép.

## 9. Thực hành Java 17: resolve một dependency thật từ Maven Central

Ví dụ này dùng một artifact công khai ổn định để bạn có thể đối chiếu cache, POM/JAR, dependency graph và cách Maven tải file.

**Yêu cầu:** JDK 17+, Maven 3.6.3+ (phù hợp với Compiler Plugin bên dưới), internet hoặc repository manager có proxy Maven Central; nếu network bị chặn, phải dùng mirror hợp lệ. Ví dụ dùng `org.apache.commons:commons-lang3:3.14.0`.

### 9.1. Tạo project

```text
repo-lookup-demo/
├── pom.xml
└── src/main/java/demo/App.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning</groupId>
    <artifactId>repo-lookup-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

Không khai `<repositories>` bổ sung: với cấu hình Maven thông thường, Super POM cung cấp Maven Central; nếu máy bạn cấu hình mirror công ty thì Maven sẽ dùng endpoint mirror tương ứng.

File `src/main/java/demo/App.java`:

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Repo lookup OK: " +
                StringUtils.capitalize("artifact resolved"));
    }
}
```

### 9.2. Build và quan sát dependency tree

Từ `repo-lookup-demo/`:

```bash
mvn -version
mvn -B -ntp -U clean package
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Giải thích các tùy chọn:

- `-B`: batch mode, không hỏi tương tác.
- `-ntp`: không in tiến độ tải transfer, giúp log dễ đọc.
- `-U`: ép kiểm tra cập nhật theo quy tắc Maven, có ích trong bài quan sát cache.
- `clean package`: xóa output build rồi compile/package; không deploy artifact.
- `dependency:tree`: xem dependency thực tế đã resolve trong project.

Trong dependency tree, tìm `org.apache.commons:commons-lang3:jar:3.14.0:compile`. Maven cũng cần resolve các **plugin build** (compiler, jar, resources...) để tạo JAR, vì vậy log có thể chứa request tới nhiều artifact khác ngoài dependency của ứng dụng.

### 9.3. Chạy ứng dụng với classpath đúng

Để tránh phụ thuộc đường dẫn `~/.m2` của từng máy, dùng Maven Dependency Plugin copy dependencies sang `target/dependency`:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
```

Sau đó trên Linux/macOS (Bash):

```bash
java -cp "target/classes:target/dependency/*" demo.App
```

Trên Windows PowerShell:

```powershell
java -cp "target\classes;target\dependency\*" demo.App
```

**Stdout chính xác từ `App.main`:**

```text
Repo lookup OK: Artifact resolved
```

Điều này chứng minh Maven đã resolve được `commons-lang3` và JVM có lớp `StringUtils` trên runtime classpath. JAR ứng dụng mặc định không phải fat JAR; nếu tự dùng `java -jar target/repo-lookup-demo-1.0.0.jar` mà chưa cấu hình manifest/classpath, bạn có thể gặp lỗi riêng không liên quan repository.

### 9.4. Kiểm tra artifact trong local repository

Với local repository mặc định, bạn thường thấy:

```text
~/.m2/repository/org/apache/commons/commons-lang3/3.14.0/
  commons-lang3-3.14.0.pom
  commons-lang3-3.14.0.jar
```

Có thể kiểm tra JAR chứa class thật:

```bash
jar tf target/dependency/commons-lang3-3.14.0.jar
```

Tìm entry `org/apache/commons/lang3/StringUtils.class`. Cách này phân biệt “artifact JAR thực sự chứa API” với trường hợp build chỉ tải POM metadata mà không có bytecode mong muốn.

### 9.5. Tái hiện resolution bằng local repo riêng (tùy chọn)

Nếu muốn phân biệt lỗi do cache cũ hay do remote, tạo **một local repository thử nghiệm riêng** thay vì xóa `~/.m2/repository`. Đứng tại `repo-lookup-demo/`:

```bash
mvn -B -ntp -U -Dmaven.repo.local=./sandbox-m2 clean package
```

`sandbox-m2` là đường dẫn **tương đối**; Maven sẽ dùng nó làm local repository của invocation này. Vì chưa có cache, việc resolve sẽ phụ thuộc remote network/mirror thực tế, bao gồm cả các plugin cần cho build. Thư mục này không phải file output của Maven thông thường, nên hãy đưa `sandbox-m2/` vào `.gitignore` trong project thử nghiệm và xóa nó theo quy trình dọn dẹp khi không còn cần. Không sử dụng kiểu kiểm tra này trên CI có dung lượng hạn chế nếu không cần thiết.

**Diễn giải kết quả:**

- Repo cũ build được, repo riêng không build được: có khả năng remote/mirror/auth/network đang có vấn đề nhưng cache cũ che lỗi.
- Repo riêng build được, repo cũ không build được: cần điều tra cache/source tracking hoặc trạng thái artifact trong local repo cũ.
- Cả hai lỗi giống nhau: kiểm tra GAV, mirror, quyền, TLS và repository thực tế.

Đây là một kỹ thuật chẩn đoán, không phải bằng chứng tự động rằng lỗi 100% nằm ở cache.

## 10. Chẩn đoán theo thứ tự: từ dễ xác minh tới khó

### Bước 1 — chép chính xác tọa độ artifact lỗi

Log có thể viết:

```text
Failed to read artifact descriptor for
dev.company:private-client:jar:2.5.0
```

Điều này gợi ý POM/artifact descriptor/parent của dependency có vấn đề, **không nhất thiết chỉ thiếu JAR chính**.

Xác minh:

- `groupId` đúng chưa (ví dụ `com.acme` khác `org.acme`)?
- `artifactId` có typo hoặc đổi tên artifact không?
- `version` có thực sự được phát hành không?
- `-SNAPSHOT` có đi nhầm release repository?
- `type=pom` hay `jar`? Có classifier `tests`/`sources` không?
- Có biến/property chưa resolve như `${revision}`, profile hoặc BOM đang quản lý version không?
- Lỗi xuất phát từ project dependency, Maven plugin, parent POM hay BOM import?

**Thử một artifact cụ thể** bằng Dependency Plugin khi plugin có thể resolve:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get -Dartifact=org.apache.commons:commons-lang3:3.14.0 -Dtransitive=false
```

`-Dtransitive=false` chỉ yêu cầu lấy artifact mục tiêu, không test toàn bộ dependency graph của ứng dụng. Với parent/BOM kiểu POM, có thể chỉ định type `pom` ở tọa độ artifact (theo tài liệu plugin). Nếu goal này lỗi vì **chính Maven Dependency Plugin không tải được**, hãy xử lý plugin repositories trước.

### Bước 2 — kiểm tra chính xác project và profile

```bash
mvn -version
mvn help:active-profiles
mvn help:effective-settings
mvn help:effective-pom -Dverbose
```

Nếu đang đứng ở repository root nhiều module, dùng `mvn -f path/to/pom.xml ...` để lấy **đúng** effective POM. Đặc biệt, profile trong settings có thể chỉ active trên CI, còn local IDE không active; hai môi trường do đó nhìn thấy hai danh sách repository khác nhau.

Xác minh Maven đang dùng đúng `user.home` và `settings.xml` nào. Trong container/CI, `HOME`, thư mục làm việc, Maven Wrapper và `-s /path/to/settings.xml` có thể khác laptop.

### Bước 3 — xem mirror trước khi đổ lỗi cho repository trong POM

Nếu effective settings có `<mirrors>`, xác định **ID/URL cuối cùng** mà request được gửi đến. Mirror `*` có thể bắt cả `central` và repository riêng; nếu mirror đó không có proxy upstream phù hợp, artifact public/private đều có thể trả 404.

Đừng thêm hàng loạt `<repository>` vào POM chỉ vì request đang bị một mirror bắt tất cả. Sửa **repository manager group/mirror configuration** đúng thẩm quyền, hoặc xác định ngoại lệ `mirrorOf` có chủ đích.

### Bước 4 — xem release/snapshot policy và quyền

Một artifact release `2.0.0` không được mong đợi tồn tại trong kho chỉ phục vụ snapshot; artifact `2.0.1-SNAPSHOT` cần snapshot repository/metadata phù hợp.

Nếu repository có xác thực, xác minh server ID tương ứng với endpoint **sau mirror**, token chưa hết hạn và scope đọc artifact hợp lệ. Không in token ra log để “kiểm tra cho nhanh”.

### Bước 5 — phân biệt HTTP/status và vấn đề mạng

| Dấu hiệu trong log | Tình huống thường gặp | Bước tiếp theo |
| --- | --- | --- |
| `Could not find artifact` / HTTP 404 | Tọa độ sai, version chưa phát hành, repository path/policy sai | Mở repository manager tìm đúng GAV/type/classifier; xem metadata |
| `previous attempt ... cached` | Negative cache của lần tìm trước | Dùng `-U` một lần, rồi kiểm tra nguyên nhân thật |
| HTTP 401 | Không có/sai credentials hoặc token hết hạn | Kiểm tra `settings.xml` server ID và phạm vi secrets |
| HTTP 403 | Quyền/policy từ chối, đôi khi repo che 404 | Kiểm tra read permission/namespace/cấu hình proxy |
| `Unknown host`/DNS | DNS, proxy, VPN hoặc URL sai | Kiểm tra resolver và network môi trường chạy |
| `Connection timed out/refused` | Không truy cập được endpoint hoặc service không nghe | Kiểm tra route/firewall/proxy/endpoint |
| `PKIX path building failed` | JVM không tin CA/certificate chain, có thể corporate proxy | Sửa trust store/CA đúng chuẩn, không tắt TLS validation |
| `Blocked mirror for repositories` | External HTTP bị Maven blocker chính sách | Chuyển sang HTTPS/đường mirror hợp lệ |
| `Checksum validation failed` | File tải hỏng, checksum/remote/proxy sai | Kiểm tra repository integrity, proxy/cache và nguồn artifact |
| `PluginResolutionException` | Plugin hoặc dependency của plugin không tải được | Kiểm tra `pluginRepositories`, mirror và plugin version |
| `Non-resolvable parent POM` | Parent `relativePath` sai hoặc remote thiếu POM | Kiểm tra parent GAV, relativePath/repository |

Tùy repository manager, một lỗi 403 có thể được hiện thực để không tiết lộ sự tồn tại artifact; không coi mapping HTTP status là chuẩn tuyệt đối cho tất cả nhà cung cấp.

### Bước 6 — bật log chẩn đoán đủ dùng, bảo vệ thông tin nhạy cảm

```bash
mvn -B -ntp -e clean package
```

`-e` cho stack trace phù hợp hơn khi chỉ cần phân tích lỗi. Khi thật sự cần chi tiết Resolver:

```bash
mvn -B -ntp -X clean package
```

**`-X` có thể in rất nhiều thông tin**, bao gồm URL, đường dẫn, system properties, thông tin cấu hình và dữ liệu không nên gửi công khai. Chỉ dùng trong môi trường được phép, không bật trace shell `set -x` quanh secrets, luôn redact dữ liệu nhạy cảm trước khi chia sẻ log.

Trong log, tìm các cụm:

```text
Using mirror ...
Downloading from ...
Downloaded from ...
Could not transfer artifact ...
Could not find artifact ...
Resolution is not reattempted ...
```

Mục tiêu không phải đọc từng dòng log, mà đối chiếu **artifact GAV + repository ID + URL + outcome**.

### Bước 7 — thử lại có kiểm soát

Nếu vừa publish một artifact trước đó chưa tồn tại:

```bash
mvn -B -ntp -U clean verify
```

Nếu muốn thử offline xác nhận cache (chỉ có ý nghĩa sau khi đã tải đầy đủ dependencies/plugins):

```bash
mvn -B -ntp -o verify
```

Nếu cần cô lập local cache, dùng `-Dmaven.repo.local=...` như mục thực hành. Không lạm dụng `-U` hoặc xóa toàn bộ local repository cho mọi lỗi.

## 11. Trường hợp “artifact chính có trên kho nhưng dependency vẫn lỗi”

Một thư viện có thể publish:

```text
private-client-2.5.0.jar
private-client-2.5.0.pom
```

POM ấy lại khai dependency:

```xml
<dependencies>
    <dependency>
        <groupId>dev.company</groupId>
        <artifactId>internal-core</artifactId>
        <version>4.0.0</version>
    </dependency>
</dependencies>
```

Nếu `internal-core:4.0.0` không tồn tại ở bất kỳ remote repo hiệu lực nào, **consumer vẫn không resolve đầy đủ dependency graph** dù `private-client:2.5.0` có JAR và POM hợp lệ.

Tương tự:

- Parent POM của `private-client` chưa được publish.
- BOM nhập bởi thư viện không resolve được.
- Dependency classifier riêng chưa được publish.
- Transitive dependency nằm ở repository mà consumer không cấu hình/không được phép truy cập.
- Artifact model dùng property/profile khiến version cuối cùng khác kỳ vọng.

Hãy đọc **chuỗi “Caused by” đầu tiên liên quan artifact thực sự thiếu**, không dừng ở artifact trực tiếp mà bạn nhìn thấy trong POM. `mvn dependency:tree` giúp quan sát graph nếu project resolve được tới mức thích hợp; khi model building đã thất bại trước đó, có thể cần đọc POM của artifact và parent/BOM bằng repository manager.

## 12. CI, Docker và Maven Wrapper: cùng POM nhưng kết quả khác

Những nguyên nhân gây khác biệt thường gặp:

- Image Docker dùng user khác nên `~/.m2/settings.xml` và local repo khác.
- Runner không được truyền `-s` hoặc secret environment cho Maven.
- CI kích hoạt profile qua `-Pci`, còn laptop không kích hoạt.
- Mirror nội bộ chỉ truy cập được khi có VPN/proxy.
- Maven Wrapper bảo đảm Maven version của repo, trong khi global `mvn` trên runner khác version.
- Một job cache `~/.m2/repository` từ nhánh/môi trường khác với repository origin/tracking khác.
- Snapshot metadata và updatePolicy làm CI kiểm tra một snapshot khác.
- Maven phiên bản mới chặn HTTP repository không an toàn, bản cũ không chặn giống vậy.

Các bước so sánh môi trường an toàn:

```bash
mvn -version
mvn help:active-profiles
mvn help:effective-pom -Dverbose
```

Với settings, chạy `mvn help:effective-settings` trong môi trường có quyền phù hợp và xử lý log như dữ liệu có thể nhạy cảm. Không đính kèm file settings chứa secrets vào artifact CI.

Khi caching local repo giữa nhiều runners, ưu tiên cache riêng theo project/policy và repository manager đáng tin cậy; không chia sẻ bừa một thư mục `.m2` có thể được sửa đồng thời bởi các tiến trình. Maven Resolver có cơ chế quản lý local repository và locking riêng; shared filesystem không được bảo đảm an toàn chỉ vì Maven chạy bình thường một lần.

### Publish artifact mới và kiểm tra đường đi

Khi team vừa deploy `dev.company:private-client:2.5.0`, hãy kiểm tra:

1. Artifact đã được publish hoàn tất lên **repository đích đúng loại** (release/snapshot) chưa?
2. Group/artifact/version có đúng cả case và classifier không?
3. Repository manager group mà CI dùng có **bao gồm** hosted repository đã publish không?
4. Mirror của CI có trỏ vào đúng group/proxy đó không?
5. Cấu hình quyền cho token read artifact đã được cấp chưa?
6. Maven có đang giữ negative cache từ trước khi publish không? Thử `-U`.
7. Các parent/BOM/transitives của artifact có thể resolve từ cùng bối cảnh không?

Nếu repo manager group chưa bao gồm hosted repo, **Maven Central cũng không thể trả lời thay cho artifact nội bộ chưa được public**. Sửa routing của repository thay vì thay đổi version dependency ngẫu nhiên.

## 13. Bảng quyết định: chọn thao tác phù hợp

| Nếu thấy... | Hãy làm trước | Tránh làm |
| --- | --- | --- |
| `Could not find artifact G:A:V` | Xác minh GAV/type/classifier và repo thực chứa artifact | Xóa toàn bộ `.m2` |
| `... cached in local repository` | Đối chiếu artifact đã publish, thử `-U` | Retry vô hạn mà không xem repo |
| URL không như trong POM | Kiểm tra effective settings và `mirrorOf` | Thêm repo trùng lặp vào POM |
| Plugin không resolve | Kiểm tra plugin repo và plugin version | Chỉ sửa `repositories` |
| Parent POM không resolve | Kiểm tra `relativePath`/parent GAV/repository | Bỏ parent bừa |
| Snapshot không cập nhật | Kiểm tra snapshot repo, metadata, updatePolicy | Overwrite release bất biến |
| 401/403 | Kiểm tra `servers.server.id` sau mirror, secrets và scope | In token ra log |
| TLS/PKIX | Sửa CA, trust store, proxy/TLS endpoint | Tắt kiểm tra SSL |
| CI lỗi, local OK | So sánh settings/profile/Maven version/cache/mirror | Giả định POM khác |
| GAV đúng nhưng class vẫn thiếu | Kiểm tra JAR/classifier, transitive graph, runtime classpath | Đổ lỗi ngay cho Maven Central |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Project đã khai repo nội bộ trong POM, nhưng Maven luôn báo đang tải từ `corporate-group`. Vì sao?

**Đáp án:** Có thể `settings.xml` có mirror `mirrorOf=*` hoặc pattern phù hợp; mirror được áp dụng trước request download. Xem effective settings và log `Using mirror`.

**Câu 2.** JAR đã có ở local repo, nhưng Maven vẫn cố tải lại. Điều này luôn là bug?

**Đáp án:** Không. Local repository có cơ chế theo dõi nguồn artifact, metadata và trạng thái resolution; file vật lý có mặt chưa chắc hợp lệ với repository context hiện tại.

**Câu 3.** Thư viện nội bộ có version `2.1.0-SNAPSHOT`, nhưng chỉ khai release repository. Có hợp lý không?

**Đáp án:** Không nếu repository ấy vô hiệu hóa snapshots và không có nguồn snapshot khác. Cần khai nguồn phù hợp, kiểm tra profile/mirror/metadata và quyền.

**Câu 4.** `-U` có thể sửa lỗi 401?

**Đáp án:** Không. `-U` giúp buộc kiểm tra lại cập nhật phù hợp; lỗi 401 cần xử lý credentials/auth và server ID.

**Câu 5.** Maven báo `PluginResolutionException`, bạn chỉ thêm dependency repository có đủ?

**Đáp án:** Không chắc. Maven plugin thường được resolve từ plugin repositories; cần xác minh `pluginRepositories`, mirror, version và plugin metadata.

**Câu 6.** `mvn dependency:get ... -Dtransitive=false` thành công có chứng minh `mvn verify` sẽ thành công?

**Đáp án:** Không. Nó chỉ kiểm tra mục tiêu resolution được yêu cầu và plugin cần để chạy lệnh; build còn cần parent, dependencies, plugins, test và nhiều cấu hình khác.

## 15. Checklist dùng khi incident

- [ ] Đã xác định **GAV/type/classifier** chính xác của artifact thiếu.
- [ ] Đã phân biệt project dependency, parent, imported BOM hay Maven plugin.
- [ ] Đã xác nhận repo vật lý có POM/JAR/metadata đúng path, đúng release/snapshot.
- [ ] Đã kiểm tra local repository **và** thông tin nguồn/cached resolution, không chỉ file `.jar`.
- [ ] Đã xem profile active, effective settings và effective POM của **đúng project/module**.
- [ ] Đã tính tới thứ tự remote repositories và mirror áp dụng trước request.
- [ ] Đã kiểm tra `repositories` hoặc `pluginRepositories` đúng loại artifact.
- [ ] Đã kiểm tra server ID sau mirror, credentials, DNS/proxy/TLS và quyền truy cập.
- [ ] Đã phân biệt negative cache với artifact thực sự không tồn tại.
- [ ] Chỉ dùng `-U` để kiểm tra lại khi phù hợp; không xóa toàn bộ local repo vô cớ.
- [ ] Nếu lỗi do transitive, đã theo dấu parent/BOM/dependency descriptor.
- [ ] Đã so sánh Maven version, settings, profile và cache trên local/CI.
- [ ] Đã giữ log chẩn đoán an toàn, không in secrets.

**Kết luận:** Maven không đơn giản “đọc lần lượt các repository URL được viết trong POM”. Nó kết hợp **local repository + effective settings + effective POM/parent/Super POM + repository profiles**, áp dụng **mirror** trước khi truy cập remote và sử dụng **metadata/cache** theo loại artifact, version và update policy. Khi artifact không tìm thấy, hãy đi từ **tọa độ → URL thực sự → trạng thái HTTP/metadata → local cache**, rồi xác minh bằng một lệnh có kiểm soát. Đó là cách sửa nguyên nhân mà không phá hủy cache hoặc làm build phụ thuộc vào một cấu hình máy cá nhân.

## Tài liệu chính thức

- [Apache Maven — Setting up Multiple Repositories (Repository Order)](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Resolver — Local Repository and Error Caching](https://maven.apache.org/resolver/local-repository.html)
- [Apache Maven Dependency Plugin — dependency:get](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
