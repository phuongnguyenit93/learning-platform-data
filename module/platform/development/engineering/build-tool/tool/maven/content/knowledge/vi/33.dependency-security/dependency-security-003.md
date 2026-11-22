# Phòng tránh tải nhầm thư viện cùng tên từ kho không mong muốn trong Maven

Một dự án Java có thể phụ thuộc vào cả thư viện công khai từ Maven Central và thư viện nội bộ do công ty tự phát hành. Rủi ro xuất hiện khi một **tọa độ artifact** được Maven tìm thấy trong **một repository không được phép cung cấp artifact đó**, chẳng hạn cùng `groupId:artifactId:version` xuất hiện ở cả kho nội bộ và kho công khai. Maven có thể tải artifact từ nguồn ngoài ý định của người quản trị build nếu cấu hình repositories, mirrors, cache hoặc repository manager không kiểm soát tốt nguồn gốc.

Vấn đề thường được gọi là **dependency confusion**, **repository confusion** hoặc **artifact source confusion**. Một trường hợp điển hình: dự án muốn dùng `dev.training.internal:billing-api:1.2.3` từ repository riêng, nhưng khi kho nội bộ thiếu version đó, đường resolution lại cho phép đi sang public proxy có một artifact mang tọa độ giống hệt. Version cố định chưa đủ để đảm bảo bytes nhận được là bản nội bộ.

**Mục tiêu phòng thủ là “đúng thư viện, đúng tọa độ, đúng nguồn đã được phép”**, không chỉ “mvn build thành công”.

> **Nguyên tắc quan trọng:** Không dựa riêng vào thứ tự repository, version lớn nhất, tên artifact hoặc `<mirrorOf>*</mirrorOf>` để khẳng định đã hết rủi ro. Hãy dùng Maven settings và **repository manager có chính sách định tuyến theo namespace/coordinate**, không fallback từ private namespace sang public proxy, kèm provenance, quyền xuất bản và kiểm tra thực tế trên CI.

Bài học giải thích chính xác Maven Resolver lựa chọn nguồn, sự khác nhau giữa GAV và “thư viện cùng tên”, cách Maven áp dụng `settings.xml`/`pom.xml`/`<repositories>`/`<pluginRepositories>`/`<mirrors>`, các biện pháp chặn HTTP repositories, thiết kế repository manager an toàn, audit dependency graph và một **lab Java 17 + Maven có thể chạy** để minh họa chính sách nguồn tin cậy mà **không tải bất kỳ artifact lạ nào để thử tấn công**.

## 1. Tên thư viện khác danh tính artifact

Trong Maven, một dependency cơ bản có:

- **`groupId`:** namespace, chẳng hạn `dev.training.internal`.
- **`artifactId`:** tên artifact, chẳng hạn `billing-api`.
- **`version`:** phiên bản, chẳng hạn `1.2.3`.
- Ngoài ra có **type/extension** và **classifier** để định danh file cụ thể, ví dụ `sources` hoặc `tests`.

Một POM dependency:

```xml
<dependency>
    <groupId>dev.training.internal</groupId>
    <artifactId>billing-api</artifactId>
    <version>1.2.3</version>
</dependency>
```

**Không được chỉ so tên `billing-api`.** Hai artifacts sau có cùng `artifactId` nhưng khác `groupId`, nên **không phải một GAV**:

```text
dev.training.internal:billing-api:1.2.3
org.example.public:billing-api:1.2.3
```

Nguy cơ nhầm nguồn nghiêm trọng hơn khi có **cùng coordinates**, chẳng hạn hai repositories đều trả về:

```text
dev.training.internal:billing-api:1.2.3
```

nhưng một repository chứa JAR/POM nội bộ đã duyệt, repository khác chứa bytes và metadata không được duyệt. Maven không có một luật mặc định kiểu “`groupId` bắt đầu bằng internal thì chỉ được tải từ kho private”. Đó là **chính sách phải được tổ chức cấu hình**.

### 1.1. Cùng GAV nhưng khác nguồn là lỗi provenance

Một Maven repository layout điển hình:

```text
dev/training/internal/billing-api/1.2.3/
    billing-api-1.2.3.pom
    billing-api-1.2.3.jar
```

Nếu hai remote repositories có cùng path, một consumer dùng đúng dependency XML cũng chưa chứng minh file nào đã được tải. Cần biết:
1. Effective remote repository set của invocation.
2. Mirror nào thay thế mỗi repository.
3. Repository manager bên trong mirror dùng hosted/private hay proxy/public nguồn nào.
4. Local repository có đang phục vụ cached artifact hoặc artifact được `mvn install` từ trước không.
5. GAV/POM/checksum/signature có khớp bản phát hành đã duyệt không.

### 1.2. Một version cao hơn không phải quy luật lựa chọn duy nhất

Trong một số hệ sinh thái, dependency confusion thường được kể là “kho công khai có version lớn hơn nên thắng”. **Không dùng câu đó như quy luật Maven tổng quát.**

Nếu POM ghi **version cố định `1.2.3`**, Maven không tự chọn `99.0.0` chỉ vì số lớn hơn. Tuy vậy, vẫn có thể nhận sai bytes của **cùng GAV `1.2.3`** nếu repository sources không tin cậy.

Nếu dùng **version range, SNAPSHOT, metadata động hoặc dependency/plugin version không ghim**, việc chọn version có thêm bước resolution/metadata và có thể làm phạm vi rủi ro lớn hơn. Nhưng repository **thứ tự và scope** vẫn quan trọng; không được khẳng định “Maven luôn chọn version cao nhất trên tất cả repositories” cho mọi trường hợp.

## 2. Mô hình tấn công và hậu quả

Ví dụ kiến trúc:

```text
                         +---------------------+
Java application ------> | Maven Resolver      |
depends on               | GAV billing-api     |
private GAV              +----------+----------+
                                    |
                         effective repositories
                                    |
                   +----------------+----------------+
                   |                                 |
          Internal hosted repo               Public proxy repo
          approved billing-api               same GAV? suspicious
                   |                                 |
                   +---------------+-----------------+
                                   |
                    Wrong source if routing permits
```

Các tình huống cần nhận diện:

**Tình huống A — Kho private không chứa version.** Team sửa `1.2.2` thành `1.2.3` trước khi publish `1.2.3` nội bộ. Nếu repository group cho phép fallback sang public cho private namespace, việc build vẫn có thể thành công với artifact từ nguồn không được duyệt. **Kỳ vọng an toàn:** fail resolution cho tọa độ private chưa có, không fallback sang public.

**Tình huống B — Reuse public GAV cho mã nội bộ.** Một project copy thông tin `groupId/artifactId` của bên ngoài rồi lưu bản sửa nội bộ dưới cùng GAV. Consumer có thể resolve các bytes khác nhau tùy repository, cache và environment. **Kỳ vọng an toàn:** thay coordinates bằng namespace riêng và phát hành version có provenance rõ.

**Tình huống C — Transitive POM khai báo thêm repository.** Một dependency có thể mang `<repositories>` trong POM của nó; Maven xét các repositories của dependency path theo context. Developer nhìn root `pom.xml` có thể không thấy mọi nguồn được dùng. **Kỳ vọng an toàn:** tập trung đi qua approved repository manager/mirror, kiểm tra effective settings và resolution logs.

**Tình huống D — Build plugin hoặc extension không tin cậy.** Maven plugins có thể thực thi code **ngay khi build**, không cần application chạy. Sai nguồn tải Maven plugin, parent POM hoặc build extension có thể gây hậu quả trước khi unit tests bắt đầu. **Kỳ vọng an toàn:** kiểm soát cả repositories của plugins/build extensions, không chỉ dependencies ứng dụng.

**Tình huống E — Cache từ môi trường khác.** Developer từng tải một artifact dưới cùng tọa độ qua một repository khác; local cache còn file đó. Một build chạy offline hoặc qua cache có thể không phản ánh cấu hình remote mới. **Kỳ vọng an toàn:** kiểm tra provenance và chạy CI với controlled settings/local repository, không coi cached bytes là bằng chứng nguồn đáng tin.

### 2.1. Vì sao đây là rủi ro supply chain?

Dependency JAR có thể chứa:
- Bytecode chạy ở runtime.
- Static initializers hoặc code được gọi từ application.
- Annotation processors hoặc runtime reflection hooks.
- Dữ liệu cấu hình hoặc resource có thể điều khiển behavior.
- Một POM khai báo dependencies transitives bất ngờ.

Maven **plugins và build extensions** còn có thể chạy trong build environment với quyền truy cập workspace, CI environment và một số credentials. Vì vậy, kiểm soát nguồn dependency là một phần của **software supply-chain security**, không chỉ cách sửa lỗi “Artifact not found”.

## 3. Maven chọn repository theo ngữ cảnh nào?

Apache Maven có tài liệu chính thức [Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html). Với artifact resolution, repositories có thể đến từ:

1. **Effective settings** (global/user `settings.xml`, active profiles).
2. **Effective build POM** (project POM, parent POM, Super POM).
3. **POMs trong dependency path** đến artifact cần tìm.

Maven áp dụng mirror mapping **trước khi liên hệ repository**. Trong mỗi tầng có quy tắc ưu tiên cho active profiles và các entries. Hướng dẫn chính thức mô tả trình tự và lưu ý rằng **repository IDs** có vai trò quan trọng với metadata/local cache.

**Tránh giản lược thành “repository đầu tiên trong root POM luôn thắng”.** Effective settings/parent/Super POM/dependency POM/mirror đều có thể tác động. Với version ranges và metadata, resolution còn có logic phiên bản riêng. Phải xem **effective repository context và log thực** của invocation.

### 3.1. Maven Central có sẵn qua Super POM

Trong Maven 3 chuẩn, **Maven Central** là một repository được cung cấp qua Super POM (và plugin repository tương ứng). Dự án không cần tự khai báo Central trong `pom.xml` để dùng dependencies công khai.

Ví dụ root POM chỉ có:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
```

không có nghĩa Maven không thể dùng Central. Một corporate `settings.xml` có `mirrorOf=*` có thể thay Central bằng repository manager nội bộ. Cũng không có nghĩa mọi repository đang được Maven dùng đều hiển thị trực tiếp trong project POM.

### 3.2. `<repositories>` khác `<pluginRepositories>`

Trong POM, có thể gặp hai danh sách:

```xml
<repositories>
    <repository>
        <id>private-dependencies</id>
        <url>https://repo.example.invalid/repository/private/</url>
    </repository>
</repositories>

<pluginRepositories>
    <pluginRepository>
        <id>approved-plugins</id>
        <url>https://repo.example.invalid/repository/plugins/</url>
    </pluginRepository>
</pluginRepositories>
```

Đây là **snippet kiến trúc**, dùng tên miền `example.invalid` không hoạt động. Không được copy nguyên URL vào dự án thực.

- `repositories` phục vụ dependency artifact resolution.
- `pluginRepositories` phục vụ Maven plugin artifact resolution.
- `distributionManagement` phục vụ **deployment** chứ không quy định source để resolve dependencies.
- `dependencyManagement` ghim versions/scopes nhưng **không là policy về origin**.

Một Maven mirror phù hợp có thể áp dụng cho repository requests trong cả hai đường resolution; đừng chỉ kiểm tra dependencies rồi bỏ qua plugins.

### 3.3. Repositories do transitive POM thêm vào

Apache Maven 3.8.1 release notes đã giải thích CVE-2021-26291: Maven có thể xem repositories trong **POM của dependency** theo repository context. Nếu một POM cũ trỏ đến HTTP repository hoặc domain bị bỏ rơi, nó có thể tạo rủi ro tải từ nguồn ngoài ý muốn. Maven 3.8.1 mặc định **chặn external HTTP repositories** bằng mirror blocker.

**Nâng cấp Maven và chặn HTTP là quan trọng, nhưng không giải quyết mọi dependency confusion qua HTTPS.** Một HTTPS endpoint có chứng chỉ hợp lệ vẫn có thể là kho **không được phép** cho private coordinates.

Nguồn: [Maven 3.8.1 release notes](https://maven.apache.org/docs/3.8.1/release-notes.html).

## 4. Mirror: cách gom luồng tải về một điểm kiểm soát

### 4.1. `mirrorOf=central` chỉ thay Central

Một `settings.xml` có thể khai báo:

```xml
<mirrors>
    <mirror>
        <id>company-central-proxy</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.invalid/repository/approved-central/</url>
    </mirror>
</mirrors>
```

Đây là **trích đoạn settings**, không phải đầy đủ file. Nó thay **repository có ID `central`**, không nhất thiết thay mọi repository mà transitive POM hoặc project tự thêm. Nếu mục tiêu là buộc mọi dependency/plugin download đi qua công ty, chỉ mirror `central` có thể không đủ.

### 4.2. `mirrorOf=*` áp dụng tất cả repository IDs

Một chiến lược quản trị thường gặp: **một approved Maven repository manager** đại diện cho mọi remote repository requests.

Tệp `ci/settings.xml` ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>company-approved</id>
            <name>Company Approved Maven Repository Manager</name>
            <url>https://repo.example.invalid/repository/maven-approved/</url>
            <mirrorOf>*</mirrorOf>
        </mirror>
    </mirrors>
</settings>
```

**Đây là cấu hình mẫu**, `repo.example.invalid` cố ý không hoạt động; để dùng thật cần thay bằng approved HTTPS endpoint được công ty quản lý và kiểm tra policy của server.

- `mirrorOf=*` khiến Maven thay các repository entries phù hợp bằng mirror đã khai báo, gồm cả repositories của dependency POMs.
- Điều này cũng có thể tác động file-based/localhost repositories dùng để test; trong workspace đặc biệt cần exemption được quản trị và đánh giá.
- Mirror entry **không gom nhiều upstream repositories thành một kho**. Nó chỉ chuyển request sang một endpoint; **repository manager** ở endpoint đó mới thực hiện aggregation/routing.
- `mirrorOf=*` không tự phân biệt private coordinates với public coordinates. Nếu server endpoint `maven-approved` group lại cho phép fallback sang public cho namespace nội bộ, vẫn còn rủi ro.
- Mirror mapping áp dụng cho tải dependencies/plugins, **không tự thay `distributionManagement`** để publish release.

### 4.3. `external:*` và `external:http:*`

Theo [Maven Mirror Settings Guide](https://maven.apache.org/guides/mini/guide-mirror-settings.html):

| Pattern | Khả năng match điển hình |
| --- | --- |
| `*` | Mọi repository IDs được Maven xét để mirror |
| `central` | Repo ID `central` |
| `external:*` | External repositories, trừ local/file-based/localhost |
| `external:http:*` | External HTTP repositories; từ Maven 3.8.x dùng cho blocker |
| `*,!trusted-local` | Mọi repository trừ ID `trusted-local` |
| `repoA,repoB` | Danh sách IDs được chỉ định |

Một ví dụ blocker của Maven:

```xml
<mirror>
    <id>maven-default-http-blocker</id>
    <mirrorOf>external:http:*</mirrorOf>
    <url>http://0.0.0.0/</url>
    <blocked>true</blocked>
</mirror>
```

Đây là **cấu hình minh họa** trong Maven distributions mới hơn, không phải mirror dùng để tải tài nguyên. `<blocked>true</blocked>` làm Maven từ chối truy cập các repositories matching. Không bỏ blocker chỉ để “build pass” khi gặp POM cũ trỏ đến HTTP; tìm replacement artifact/repository hợp lệ qua HTTPS hoặc approved repository manager.

**Một điểm về precedence:** Maven ưu tiên mirror có `mirrorOf` exact match repository ID trước, nếu không có thì chọn mirror matching đầu tiên theo rules. Với nhiều wildcard mirrors, **declaration order có thể quan trọng**. Không cấu hình ba mirror cùng `mirrorOf=*` rồi kỳ vọng Maven luân phiên hoặc tổng hợp chúng.

### 4.4. Điều gì một mirror *không* giải quyết?

| Kỳ vọng sai | Thực tế |
| --- | --- |
| “`mirrorOf=*` tự bảo đảm không có dependency confusion.” | Nếu group server cho public fallback với private coordinates, vẫn có thể lấy sai |
| “Cứ HTTPS là đáng tin.” | HTTPS bảo vệ kênh, không xác nhận quyền sở hữu GAV trong business policy |
| “Private repository ở trước public proxy là đủ.” | Khi private thiếu version, group có thể tìm tiếp upstream khác |
| “Một mirror có thể chứa danh sách nhiều mirror URLs để Maven tự lựa chọn an toàn.” | Maven chọn một mirror mapping; cần repository manager quản lý upstream |
| “Mirror chỉ áp dụng dependencies, không ảnh hưởng plugins.” | Maven repository mirror mapping có thể áp cho cả hai loại retrieval |
| “Mirror sẽ ngăn `mvn deploy` upload vào repository khác.” | Deploy source nằm ở `distributionManagement`/deploy config, không do mirror điều khiển |

## 5. Chính sách quan trọng nhất: định tuyến theo namespace

Giả sử hệ thống tổ chức đặt:
- Private GAVs: `dev.training.internal:*:*`.
- Public dependencies: các GAVs đã được approve từ Maven Central.
- Private releases: repository `private-releases`.
- Public proxy: `approved-public-proxy`.
- Build clients: chỉ truy cập repository manager qua `maven-approved`.

**Quy tắc an toàn:**

1. Nếu `groupId` là `dev.training.internal` hoặc bắt đầu `dev.training.internal.`, chỉ lấy artifact từ **private-releases**.
2. Nếu private-releases không có GAV/version yêu cầu, **fail closed**: báo không tìm thấy, **không** chuyển sang public proxy.
3. Nếu là public GAV thuộc allowlist, chỉ lấy từ approved public proxy với policies về malware/vulnerabilities/licenses.
4. Các repositories hoặc domains khác đều bị từ chối.
5. Không cho public proxy phục vụ private GAV ngay cả khi nó được Central xuất bản với đúng version.
6. Không cho local developer hoặc CI dùng settings khác để bỏ qua chính sách khi build production/release.

Cơ chế thực hiện có thể là **routing rules/content selectors** hoặc repository-manager policies phù hợp với sản phẩm và phiên bản, kết hợp tách repository endpoints và ACLs. Không giả định mọi Nexus/Artifactory version có cùng tính năng hay cú pháp. **Cần thử tình huống “private version thiếu”** để xác nhận group không fallback sang public.

### 5.1. Vì sao thứ tự kho chưa đủ?

Cấu hình nguy hiểm:

```text
Repository group: maven-all
  1. hosted-private
  2. proxy-central
```

Nếu `hosted-private` có `dev.training.internal:billing-api:1.2.2` nhưng không có `1.2.3`, một group không có routing restriction có thể hỏi tiếp `proxy-central`. Vì vậy chỉ “private ở vị trí 1” không chặn hoàn toàn việc nhận GAV nội bộ từ public.

Kỳ vọng:

```text
GAV = dev.training.internal:billing-api:1.2.3
       |
       v
private namespace?
       |
      YES ---> hosted-private only
                   |
               version missing
                   |
             FAIL CLOSED (không hỏi Central)
```

**Policy phải dựa vào `groupId/GAV` hoặc path prefix phù hợp**, không dựa vào artifactId duy nhất. Path Maven cho `dev.training.internal` bắt đầu bằng `dev/training/internal/`, nhưng cần tránh prefix quá rộng trùng với namespace khác.

### 5.2. Đừng đăng mã nội bộ dưới coordinates của thư viện công khai

Nếu công ty fork `org.example:useful-lib:1.0.0` và sửa bytes để dùng riêng nhưng giữ nguyên GAV, một consumer có thể resolve bản public trong môi trường khác. Cách đúng là:
- Dùng namespace/groupId và version có chủ đích riêng.
- Hoặc dùng repository policy/documented relocation phù hợp khi cần công bố migration.
- Ghim nguồn và kiểm chứng checksums cho fork được duyệt.
- Không sử dụng public GAV làm “tên riêng” cho binary đã thay.

### 5.3. Registry namespace verification không thay internal routing

Maven Central có các quy tắc về quyền công bố namespace với publisher. Tuy nhiên điều đó không có nghĩa một organization **tự động bảo vệ được mọi private GAV trên mọi repository hoặc mọi namespace chưa đăng ký**. Ngay cả khi có namespace ownership, một repository proxy/group tùy biến vẫn có thể bị cấu hình sai. **Không dựa chỉ vào việc tên groupId nhìn giống domain nội bộ**.

### 5.4. Parent POM, BOM, plugins và extensions

Private-source policy phải áp cho:
- Dependencies trực tiếp và transitives.
- Parent POMs kế thừa.
- Imported BOM POMs trong `dependencyManagement`.
- Maven plugins qua `pluginRepositories`.
- Build/core extensions và code generators.
- Test dependencies và annotation processors.
- Plugin dependencies nếu project khai báo.

Chỉ kiểm tra production JAR trong `mvn dependency:tree` không có nghĩa toàn bộ **build-time execution graph** đã an toàn.

## 6. Ghim phiên bản giúp gì và không giúp gì?

POM tốt thường chọn version chính xác:

```xml
<dependency>
    <groupId>dev.training.internal</groupId>
    <artifactId>billing-api</artifactId>
    <version>1.2.3</version>
</dependency>
```

Điều này ngăn Maven tự chọn `99.0.0` chỉ vì nó cao hơn trong một metadata listing, nhưng **cùng `1.2.3` ở hai repositories vẫn có thể khác bytes**.

Để kiểm soát toàn graph:
- Sử dụng `dependencyManagement` hoặc BOM để quản lý versions nhất quán.
- Không dùng SNAPSHOT/dynamic versions trong release nếu không có ngoại lệ đã duyệt.
- Pin Maven build-plugin versions.
- Cập nhật dependencies qua review/pull request, không tự động chấp nhận version không được kiểm chứng.
- Kiểm tra dependencies transitives và exclusions theo nhu cầu.
- Lưu SBOM/hash/provenance, ký số nếu policy yêu cầu.
- Có allowlist source repositories và namespace routing **tại server**.

### 6.1. Enforcer và dependency convergence không giải quyết nguồn

Maven Enforcer có thể kiểm tra `dependencyConvergence`, `requireUpperBoundDeps`, `bannedDependencies`, `banDynamicVersions`. Những rules này giúp:
- Phát hiện conflict giữa versions.
- Ngăn dùng GAV bị cấm.
- Tránh dependencies quá động.

**Nhưng Enforcer không mặc nhiên phân biệt cùng GAV được tải từ kho private hay public.** Một POM đạt convergence rule vẫn có thể tải JAR sai nguồn nếu repository configuration lỗi. **Artifact provenance/routing là kiểm soát riêng.**

### 6.2. Checksums và signatures cần nguồn tin cậy

Checksums giúp phát hiện file khác với hash đã pin. Nhưng nếu attacker cũng cung cấp `.sha1` hoặc `.sha256` cùng repository, chỉ tải checksum cạnh file đó **không phải chứng cứ độc lập rằng artifact đáng tin**.

Giá trị cao hơn là so SHA-256/signature với:
- Release manifest/hash đã được approve ngoài repository nguồn.
- Signing key/identity đã được xác minh.
- Attestation/provenance từ build pipeline được tin cậy.
- Một allowlist hash cho các artifacts đặc biệt quan trọng.

Không biến disable-checksum-policy hay tắt TLS verification thành “cách sửa build”.

## 7. Local repository và origin cache

Maven local repository thường ở `~/.m2/repository`, nhưng có thể thay bằng `settings.xml` hoặc `-Dmaven.repo.local`. Nó phục vụ cả artifacts **downloaded/cache** và artifacts được `mvn install` cục bộ.

Resolver có Enhanced Local Repository Manager với cơ chế theo dõi **nguồn remote repository** cho cached artifacts. Tài liệu Resolver nêu việc artifact được tải từ repository R1 không nhất thiết được xem là sẵn cho build chỉ khai báo R2, dù cùng GAV và file tồn tại trong local cache.

**Tuy nhiên không được biến metadata cache thành security attestation.** Repository IDs có thể bị reuse hoặc config thay; local files cũng có thể được install thủ công. Các biến thể Resolver/version có thể dùng origin tracking khác nhau. CI cần build bằng settings đáng tin, cached artifacts đã được kiểm duyệt và kiểm chứng provenance khi quan trọng.

### 7.1. Cách đọc cache metadata đúng mức

Trong một Maven 3 local repository, bạn có thể thấy file kiểu:

```text
~/.m2/repository/dev/training/internal/billing-api/1.2.3/
    billing-api-1.2.3.jar
    billing-api-1.2.3.pom
    _remote.repositories
```

`_remote.repositories` chứa thông tin resolver/cache, **có thể hỗ trợ điều tra** artifact từng gắn với repository ID nào. Nó **không chứng minh** artifact được approved hoặc không bị thay: file cache có thể cũ, bị cài thủ công, hoặc repository ID đã trỏ URL khác.

### 7.2. CI có nên dùng local repo biệt lập?

Trong một môi trường thử nghiệm:

```bash
mvn -B -ntp -Dmaven.repo.local=/path/to/isolated-m2 verify
```

Đây là cú pháp minh họa cho Linux/macOS; **thay path bằng thư mục riêng có quyền ghi**. Windows dùng một path tương ứng phù hợp với PowerShell.

Một local repo riêng giúp dễ đối chiếu logs/artifacts cho **một build**, nhưng **không đủ để ngăn dependency confusion** nếu endpoint tải vẫn trỏ đến kho không mong muốn. Clean cache là bước điều tra, không phải chính sách source trust.

### 7.3. Maven version và credential origin

Ở các bản Maven mới hơn, security controls cho việc gắn credentials với repository origins đã được tăng cường. Theo [Maven Settings Reference](https://maven.apache.org/settings.html), Maven 3.10.0 và Maven 4.0.0 hỗ trợ binding credentials theo scheme/host/port của repository/mirror và `repositoryOrigins`, giảm nguy cơ gửi credentials đến host khác chỉ vì **trùng server ID**.

Đối với Maven 3.9.x hoặc các phiên bản cũ, **không mặc định có cơ chế origin binding mới**. Tránh tái sử dụng server ID cho URLs không tin cậy; nâng Maven/toolchain theo security policy. Không đưa token vào POM hoặc logs, và không dùng `-X` khi có nguy cơ xuất credentials/header nhạy cảm lên CI artifact.

## 8. Audit: thực tế Maven đang nhìn thấy repositories nào?

Không đủ để đọc root `pom.xml`. Nên xem:

```bash
mvn -version
mvn -B -ntp help:effective-settings
mvn -B -ntp help:effective-pom -Dverbose
mvn -B -ntp dependency:tree
```

Ý nghĩa:
- `help:effective-settings` cho thấy settings đã merge với profile/mirror có hiệu lực; Maven Help Plugin **ẩn password mặc định**. **Không dùng `-DshowPasswords=true`** trong CI/shared logs.
- `help:effective-pom -Dverbose` hiển thị effective POM, inheritance và nguồn một số cấu hình; giúp tìm `repositories`/`pluginRepositories`.
- `dependency:tree` cho thấy resolved graph/version; **không tự chứng minh artifact came from trusted host**.
- Build logs trong môi trường kiểm soát cho biết các remote IDs/URLs được dùng khi tải. Có thể dùng diagnostic verbosity tăng khi thật sự cần, sau khi loại secrets.

Đối với build chuyên kiểm tra, nên ghim version của Help/Dependency plugins trong build tooling; các command ngắn trên minh họa cách dùng theo plugin prefix.

### 8.1. Cẩn trọng với `settings.xml` trong CI

Một pipeline có thể dùng:

```bash
mvn -B -ntp -s ci/settings.xml clean verify
```

Lệnh **chỉ đúng khi `ci/settings.xml` trỏ đến repository manager thật và phù hợp chính sách**. Không dùng file example.invalid ở phần trên để chạy build production. Dùng secret manager cho private mirror token khi cần; hạn chế lưu effective settings/log debug như public artifact.

Nếu CI có nhiều jobs (test, package, security, release), **tất cả** jobs resolve dependencies/plugins phải sử dụng settings được quản trị nhất quán. Một job bảo mật dùng trusted repo nhưng job deploy lại tải qua default Central là một lỗ hổng quy trình.

### 8.2. Diễn giải Maven logs

Một số dấu hiệu cần kiểm tra:

```text
Downloading from company-approved: https://repo.company.example/repository/maven-approved/...
Downloaded from company-approved: ...
```

Hai dòng này **chỉ là dạng log minh họa**, không phải output từ hệ thống thật. Tên repo ID cho thấy Maven kết nối tới mirror, **không chứng minh** repository manager bên trong đã lấy artifact từ hosted-private hay public proxy. Cần audit upstream source từ repository-manager logs/policies.

**Không suy ra “mọi artifact đều private” từ một log `company-approved`**, vì endpoint đó có thể là group với public proxy.

### 8.3. Cần làm gì khi thấy repository bất ngờ?

- Xác định nó đến từ effective settings, project POM, parent POM hay dependency POM.
- Kiểm tra mirror mapping và repository ID.
- Tra đường download thực tế trong Maven logs.
- Xem repository-manager request/audit log để xác định upstream.
- Nếu private GAV được phục vụ từ public proxy, tạm chặn build/release để điều tra.
- So SHA-256 với approved manifest hoặc ký số được tin cậy.
- Xác minh artifacts đã bị cache ở CI/hosts nào.
- Sửa routing rule, không chỉ chỉnh version hay xóa local cache.
- Rebuild bằng controlled settings và cô lập artifacts đã nghi vấn nếu cần.

## 9. Lab Java 17: chính sách nguồn nào được phép

Lab tạo một **Java policy model thuần JDK**, không tải artifact qua Internet và **không can thiệp trực tiếp Maven Resolver**. Nó minh họa:
- Tọa độ `dev.training.internal:billing-api:1.2.3` **chỉ được phép** từ private repository.
- Một public GAV `org.apache.commons:commons-lang3:3.14.0` chỉ được phép từ approved public proxy.
- Private GAV đến từ public proxy bị từ chối.
- Một URL không được phê duyệt bị từ chối.
- Chú ý việc match prefix namespace phải có ranh giới dấu chấm: `dev.training.internalfake` **không phải** `dev.training.internal.*`.

**Quan trọng:** class Java này là **bài tập mô hình hóa policy**, không phải Maven plugin/hook ngăn download. Nếu ứng dụng chạy sau khi Maven đã resolve dependency thì code **không thể ngăn việc tải đã xảy ra**. Enforcement thực sự vẫn nằm ở settings + repository-manager routing/CI source attestation.

### 9.1. Cây file lab

```text
maven-repo-origin-lab/
├── pom.xml
└── src/
    ├── main/java/dev/training/security/
    │   ├── RepositoryOriginPolicy.java
    │   └── PolicyDemo.java
    └── test/java/dev/training/security/
        └── RepositoryOriginPolicyTest.java
```

Cần JDK 17+, Maven 3.9.x hoặc phiên bản Maven tương thích với các plugins được ghim. Project lab **không có production dependency bên ngoài**; JUnit là test dependency, Maven compiler/test plugins vẫn được tải theo Maven settings đang sử dụng. Vì vậy chỉ chạy Maven build trong môi trường có repository source được phép.

Linux/macOS:

```bash
mkdir -p maven-repo-origin-lab/src/main/java/dev/training/security
mkdir -p maven-repo-origin-lab/src/test/java/dev/training/security
cd maven-repo-origin-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "maven-repo-origin-lab/src/main/java/dev/training/security" | Out-Null
New-Item -ItemType Directory -Force -Path "maven-repo-origin-lab/src/test/java/dev/training/security" | Out-Null
Set-Location maven-repo-origin-lab
```

### 9.2. POM đầy đủ

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.security</groupId>
    <artifactId>maven-repo-origin-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
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
                <version>3.6.1</version>
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

Không có `<repositories>` hoặc `<pluginRepositories>` trong lab POM, để nguồn tải phụ thuộc vào environment/settings được quản trị. **Đây không phải bằng chứng lab tự an toàn trong mọi môi trường**: Maven Super POM vẫn có Central, nên một project chỉ thực sự được kiểm soát nguồn nếu môi trường Maven/CI dùng approved mirror và repository manager.

### 9.3. `RepositoryOriginPolicy.java`

Tệp `src/main/java/dev/training/security/RepositoryOriginPolicy.java`:

```java
package dev.training.security;

import java.net.URI;
import java.util.Objects;

/**
 * Minh họa chính sách source cho Maven coordinates; không gọi network.
 */
public final class RepositoryOriginPolicy {

    public static final URI PRIVATE_REPOSITORY = URI.create(
        "https://repo.example.invalid/repository/private-releases/");

    public static final URI APPROVED_PUBLIC_PROXY = URI.create(
        "https://repo.example.invalid/repository/approved-public-proxy/");

    private RepositoryOriginPolicy() {
    }

    /**
     * Một tọa độ GAV đơn giản, bắt buộc ba trường không rỗng.
     */
    public record Coordinate(
        String groupId,
        String artifactId,
        String version
    ) {
        public Coordinate {
            if (groupId == null || groupId.isBlank()
                    || artifactId == null || artifactId.isBlank()
                    || version == null || version.isBlank()) {
                throw new IllegalArgumentException(
                    "groupId, artifactId and version are required");
            }
        }

        @Override
        public String toString() {
            return groupId + ":" + artifactId + ":" + version;
        }
    }

    /**
     * Match private namespace theo dấu chấm, tránh prefix gần giống.
     */
    public static boolean isPrivateGroup(String groupId) {
        Objects.requireNonNull(groupId, "groupId");
        return groupId.equals("dev.training.internal")
            || groupId.startsWith("dev.training.internal.");
    }

    /**
     * Trả false khi nguồn tải không phù hợp GAV policy.
     *
     * Đây chỉ là mô phỏng: Maven Resolver không gọi method này.
     */
    public static boolean allowed(Coordinate coordinate, URI origin) {
        Objects.requireNonNull(coordinate, "coordinate");
        Objects.requireNonNull(origin, "origin");
        return isPrivateGroup(coordinate.groupId())
            ? PRIVATE_REPOSITORY.equals(origin)
            : APPROVED_PUBLIC_PROXY.equals(origin);
    }
}
```

Giải thích:
- `Coordinate` là Java 17 `record`, constructor kiểm soát input rỗng.
- `isPrivateGroup` dùng exact match **hoặc prefix kèm dấu chấm**. Nếu chỉ dùng `startsWith("dev.training.internal")`, namespace `dev.training.internalfake` sẽ bị nhận nhầm thành private.
- `URI` so sánh ở mức **endpoint mẫu cố định**. Một policy production cần canonicalize URL, DNS/TLS verification, approved certificates, redirect handling, repository manager routing và audit; không dựa vào hàm này như một security interceptor.
- `example.invalid` là domain **không hoạt động** được sử dụng để mô phỏng source identity; chương trình không kết nối mạng.
- Không cho phép fallback từ private coordinate sang approved-public-proxy chỉ vì GAV không được tìm thấy trong private.

### 9.4. `PolicyDemo.java`

Tệp `src/main/java/dev/training/security/PolicyDemo.java`:

```java
package dev.training.security;

import java.net.URI;

import static dev.training.security.RepositoryOriginPolicy.allowed;

public final class PolicyDemo {

    private PolicyDemo() {
    }

    public static void main(String[] args) {
        var privateArtifact =
            new RepositoryOriginPolicy.Coordinate(
                "dev.training.internal", "billing-api", "1.2.3");

        var publicArtifact =
            new RepositoryOriginPolicy.Coordinate(
                "org.apache.commons", "commons-lang3", "3.14.0");

        System.out.println("private/private=" + allowed(
            privateArtifact, RepositoryOriginPolicy.PRIVATE_REPOSITORY));

        System.out.println("private/public=" + allowed(
            privateArtifact, RepositoryOriginPolicy.APPROVED_PUBLIC_PROXY));

        System.out.println("public/public=" + allowed(
            publicArtifact, RepositoryOriginPolicy.APPROVED_PUBLIC_PROXY));

        System.out.println("public/unapproved=" + allowed(
            publicArtifact,
            URI.create("https://unknown.example.invalid/repository/")));
    }
}
```

**Stdout Java chính xác:**

```text
private/private=true
private/public=false
public/public=true
public/unapproved=false
```

`true` nghĩa policy mẫu cho phép nguồn đã chỉ định, `false` nghĩa không cho phép. Những chuỗi này **không phải Maven download logs** và **không đại diện cho kết quả một request HTTP**.

### 9.5. `RepositoryOriginPolicyTest.java`

Tệp `src/test/java/dev/training/security/RepositoryOriginPolicyTest.java`:

```java
package dev.training.security;

import java.net.URI;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RepositoryOriginPolicyTest {

    private final RepositoryOriginPolicy.Coordinate internal =
        new RepositoryOriginPolicy.Coordinate(
            "dev.training.internal", "billing-api", "1.2.3");

    private final RepositoryOriginPolicy.Coordinate external =
        new RepositoryOriginPolicy.Coordinate(
            "org.apache.commons", "commons-lang3", "3.14.0");

    @Test
    void privateCoordinateFromPrivateRepositoryIsAllowed() {
        assertTrue(RepositoryOriginPolicy.allowed(
            internal, RepositoryOriginPolicy.PRIVATE_REPOSITORY));
    }

    @Test
    void privateCoordinateFromPublicProxyIsRejected() {
        assertFalse(RepositoryOriginPolicy.allowed(
            internal, RepositoryOriginPolicy.APPROVED_PUBLIC_PROXY));
    }

    @Test
    void publicCoordinateFromApprovedProxyIsAllowed() {
        assertTrue(RepositoryOriginPolicy.allowed(
            external, RepositoryOriginPolicy.APPROVED_PUBLIC_PROXY));
    }

    @Test
    void unknownRepositoryIsRejected() {
        assertFalse(RepositoryOriginPolicy.allowed(
            external,
            URI.create("https://unknown.example.invalid/repository/")));
    }

    @Test
    void namespaceBoundaryIsRespected() {
        assertTrue(RepositoryOriginPolicy.isPrivateGroup(
            "dev.training.internal.services"));
        assertFalse(RepositoryOriginPolicy.isPrivateGroup(
            "dev.training.internalfake"));
    }

    @Test
    void emptyCoordinatesAreInvalid() {
        assertThrows(IllegalArgumentException.class,
            () -> new RepositoryOriginPolicy.Coordinate(
                " ", "billing-api", "1.2.3"));
    }
}
```

**Có 6 JUnit Jupiter tests**, test policy cho phép/từ chối, namespace boundary và invalid input. Test class kết thúc bằng `Test` nên Maven Surefire chọn theo convention.

### 9.6. Chạy Maven lab

Trong thư mục `maven-repo-origin-lab`:

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes dev.training.security.PolicyDemo
```

Để tuân thủ repository trust policy thực tế, chạy Maven với corporate settings **đã được thay URL và kiểm tra**; không dùng example.invalid. Nếu chỉ muốn kiểm tra logic Java **không tải plugin/JUnit**, có thể biên dịch trực tiếp bằng JDK:

```bash
mkdir -p out
javac -d out src/main/java/dev/training/security/RepositoryOriginPolicy.java src/main/java/dev/training/security/PolicyDemo.java
java -cp out dev.training.security.PolicyDemo
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "out" | Out-Null
javac -d out "src/main/java/dev/training/security/RepositoryOriginPolicy.java" "src/main/java/dev/training/security/PolicyDemo.java"
java -cp out dev.training.security.PolicyDemo
```

**Kết quả của `java` trong cả hai cách là bốn dòng stdout** đã ghi trên. Khi chạy Maven, phần Surefire mong đợi:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **tóm tắt test counts dự kiến**, không phải toàn bộ Maven console output. Nếu Maven không tải được dependencies/plugins từ approved repository, build thất bại vì môi trường, không phải chứng cứ policy Java đã sai.

**Không chạy demo để thử upload một GAV trùng lên Maven Central/Nexus**; các URLs sử dụng trong code hoàn toàn giả lập và Java code không gọi HTTP.

### 9.7. Giới hạn của lab: Java policy không thay Maven Resolver

Một application method chạy sau `mvn compile` không thể tác động đến quyết định source tải plugins/dependencies **đã xảy ra trước đó**. Lab chỉ dạy policy logic và cách viết tests. Khi áp dụng thật:
- Repository manager cần route private GAV chỉ tới hosted-private.
- Maven CI settings phải buộc clients qua manager.
- Audit upstream origin/checksum và lưu release manifest.
- Không chấp nhận build nếu policy bị vi phạm.

Để có enforcement trong CI, có thể xây thêm bước đọc repository-manager audit/attestation từ một trusted service, nhưng **không được giả định `dependency:tree` đã chứng minh origin**.

## 10. Thực hành cấu hình repository manager theo tư duy fail-closed

Chọn mẫu namespace và routing policy rõ:

```text
Namespaces:
  dev.training.internal.*  -> private hosted repository ONLY
  org.apache.*             -> approved public proxy if allowlisted
  org.junit.*              -> approved public proxy if allowlisted
  anything else            -> review/deny by organizational policy

Client:
  Maven settings mirrorOf=*
       |
Company repository manager (HTTPS, audited)
       |
       +-- private namespace -> hosted-private, NO public fallback
       |
       +-- allowlisted public namespace -> scanned public proxy
       |
       +-- unapproved namespace/source -> reject
```

Đây là **bản thiết kế chính sách**, không phải cấu hình Nexus/Artifactory syntax đã copy chạy được. Hãy chuyển nó sang routing rule/content selector cụ thể của sản phẩm đang dùng và test trong sandbox.

### 10.1. Ma trận QA cho repository routing

| GAV yêu cầu | Private hosted | Public proxy | Kết quả mong đợi |
| --- | --- | --- | --- |
| Private `billing-api:1.2.3` | Có bản approved | Không liên quan | Tải private |
| Private `billing-api:1.2.4` | Không có | Có tọa độ giống | **FAIL CLOSED**, không tải public |
| Public `commons-lang3:3.14.0` | Không | Có bản approved | Tải qua approved proxy |
| Public version không được approve | Không | Có file | Theo policy: reject/approval |
| Plugin có groupId lạ | Không | Có | Review trước khi cho chạy |
| POM trỏ external HTTP | Không có exception | URL HTTP | Block bởi Maven/repo policy |
| POM trỏ HTTPS unknown | Không có exception | Có trả file | Mirror/group policy không cho bypass |

**Trường hợp thứ hai là bài test quan trọng nhất**. Nếu group chỉ ưu tiên private trước public nhưng vẫn trả public khi private thiếu, chính sách phòng dependency confusion chưa đạt.

### 10.2. Test fail-closed mà không publish artifact nguy hiểm

Không cần tải artifact lạ hoặc chiếm namespace trên public registry. Có thể:
1. Trong repository manager sandbox, tạo một private artifact GAV giả chỉ tồn tại ở hosted-private.
2. Xác minh nó resolve qua approved manager.
3. Cố yêu cầu một version **không tồn tại ở private**; confirm manager **không hỏi public upstream** cho namespace private.
4. Kiểm tra logs/routing decisions.
5. Dùng một public artifact hợp lệ đã approve để xác minh public proxy vẫn hoạt động.
6. Thử metadata snapshot/range và plugin repository resolution ở môi trường tách biệt.

Điều này kiểm chứng control plane mà không cần dựng “package độc” hoặc upload thứ gì lên Maven Central thật.

## 11. Những cách phòng thủ thường bị hiểu sai

### 11.1. “Private repo nằm đầu danh sách là đủ”

Không đủ khi private thiếu GAV/version và group tìm tiếp public. Cần **deny public fallback cho private namespace**.

### 11.2. “Pin version 1.2.3 là không thể nhầm”

Pin version giảm dynamic-version confusion, nhưng **cùng GAV version** vẫn có thể xuất hiện ở nhiều repositories. Cần kiểm soát **source/provenance**.

### 11.3. “Nếu JAR từ HTTPS thì đã xác thực nguồn”

HTTPS xác thực kênh đến domain theo TLS trust, **không xác nhận artifact đó là bản nội bộ đúng**. Một proxy có TLS hợp lệ vẫn có thể route tới upstream sai.

### 11.4. “Chỉ cần một mirrorOf=*”

Nó buộc client requests qua một endpoint, rất hữu ích, **nhưng endpoint đó phải có routing rule đúng**. Nếu group server trộn public/private mà không chặn namespace collision thì rủi ro vẫn tồn tại.

### 11.5. “Chỉ cần Maven Enforcer dependencyConvergence”

Convergence kiểm version trong graph, không kiểm nguồn tải. Có thể dùng Enforcer như lớp thứ hai; source-based enforcement vẫn phải độc lập.

### 11.6. “dependency:tree cho biết download URL”

`dependency:tree` chủ yếu thể hiện **resolved dependency graph**. Download source cần logs/resolver metadata/repository-manager audit. Không suy đoán URL từ một tên artifact.

### 11.7. “Xóa ~/.m2 giải quyết triệt để”

Dọn cache giúp điều tra nguồn hiện tại, nhưng Maven vẫn có thể tải nhầm ngay lượt build sau nếu routing không đổi. Không xóa local repository dùng chung mà không có kế hoạch/approval.

### 11.8. “Chỉ sản phẩm chạy mới cần chú ý”

Maven plugins, test fixtures, annotation processors, build extensions và parent POM có thể ảnh hưởng **build environment** trước runtime. Kiểm soát cả build-time dependencies và plugin repositories.

### 11.9. “Maven 3.8.1 chặn hết các kho lạ”

Maven 3.8.1 mặc định chặn external **HTTP** repositories; HTTPS endpoint không được phép vẫn phải bị ngăn bằng mirror/source policy. Không dùng HTTP blocker làm duy nhất một supply-chain gate.

### 11.10. “Một server ID có thể trỏ qua lại đến nhiều host mà không sao”

Server IDs kết hợp settings/repository identity, có ảnh hưởng credentials và local metadata. Các phiên bản Maven mới hơn tăng origin binding. Không reuse IDs cho URLs khác nhau, đặc biệt với POM untrusted hoặc CI có secrets.

## 12. Troubleshooting khi Maven tải từ nguồn bất ngờ

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm chứng |
| --- | --- | --- |
| Maven tải private GAV từ proxy Central | Repository group cho public fallback | Kiểm tra routing policy cho namespace private |
| `mirrorOf=central` vẫn có request kho lạ | Mirror chỉ match repository ID Central | Xem effective settings/POM/transitive POM |
| Build pass local nhưng fail CI | Local cache/installed artifact khác | Dùng controlled local repo và cùng settings |
| Plugin được tải từ host khác | `pluginRepositories` hoặc mirror khác | Xem plugin repo mapping và logs |
| POM thêm HTTP repo bị block | Maven 3.8.1+ external HTTP blocker | Nâng artifact/POM, dùng HTTPS approved route |
| HTTPS URL đúng nhưng bytes sai | Proxy/server group routing sai hoặc artifact bị thay | So approved hash/attestation và audit upstream |
| Repo IDs bị trùng | Effective settings/POM IDs conflict/override | Kiểm tra unique IDs, inheritance |
| Credentials xuất hiện ở host lạ | Server ID/origin scope cấu hình yếu hoặc Maven cũ | Cô lập token, kiểm tra Maven version/origin policy |
| Transitive dependency mang repo riêng | Maven dependency-POM context | Examine POM chain và approved mirror |
| Version cao bất ngờ được chọn | Range/SNAPSHOT/dynamic metadata hoặc mediation | Pin version, xem dependency tree/metadata |
| Artifact cùng GAV khác bytes giữa machines | Cache/mirror/source divergence | Hash và build provenance, quarantine nghi vấn |
| CI dùng `-s` khác developer | Settings/profiles không đồng bộ | Ghim CI settings và review effective settings |
| Tests pass nhưng dependency vẫn không tin cậy | Tests không kiểm repository origin | Route + attestation + SCA/security review |

### 12.1. Trình tự điều tra an toàn

1. **Dừng release** nếu có dấu hiệu private GAV lấy từ public repository.
2. Ghi nhận GAV, version, classifier, project commit và Maven/JDK version.
3. Kiểm tra effective settings/mirrors, các active profiles và effective POM.
4. Xem remote repository IDs/URLs từ logs không chứa secrets.
5. Kiểm tra upstream request logs của repository manager.
6. So SHA-256 và provenance với approved artifact manifest.
7. Kiểm tra local cache và những CI runs khác có thể đã dùng artifact.
8. Nếu nghi bị thay, cô lập cache/artifact, rotate credentials khi có rò rỉ.
9. Sửa namespace routing/server policy trước khi cho builds tiếp tục.
10. Chạy lại kiểm thử trên trusted source với local repository được kiểm soát, cập nhật incident/release records.

Không kết luận một library "an toàn" chỉ vì antivirus/scanner không báo lỗi: sai nguồn tải đã là vi phạm policy ngay cả khi mã chưa có hành vi độc hại.

## 13. Checklist triển khai phòng dependency confusion

- [ ] Định nghĩa private GAV namespace rõ ràng và không trùng GAV công khai.
- [ ] Mọi internal artifacts được publish ở private hosted repository với quyền hạn thích hợp.
- [ ] Private namespace **không bao giờ fallback** sang public proxy khi thiếu artifact/version.
- [ ] Public dependencies chỉ đến từ approved upstream qua proxy đã quản lý.
- [ ] Repository manager áp routing/allowlist/deny rules ở server.
- [ ] Maven/CI đi qua approved repository manager, dùng mirror mapping có chủ đích.
- [ ] Không chỉ mirror Central rồi bỏ qua repositories khác từ POM/plugin POMs.
- [ ] Đã xem `<pluginRepositories>`, parent POM, BOM, annotation processors và build extensions.
- [ ] Maven version được hỗ trợ, chặn external HTTP repositories.
- [ ] Dùng HTTPS/TLS và xác thực origin; không tắt certificate verification.
- [ ] Không có credentials trong POM, shell history hoặc logs.
- [ ] Không reuse repository server IDs cho host lạ.
- [ ] Maven dependencies và plugins ghim version phù hợp.
- [ ] Không dùng dynamic/SNAPSHOT dependencies trong release trái chính sách.
- [ ] Hash/signatures/provenance được xác minh bằng trusted reference.
- [ ] CI giữ manifest và audit upstream origin cho artifacts quan trọng.
- [ ] Kiểm tra cả trường hợp **private version không tồn tại** và xác nhận fail-closed.
- [ ] Local cache được quản lý/cô lập khi điều tra.
- [ ] Không thử attack bằng cách công bố GAV giả trên public registry.
- [ ] Nếu phát hiện nhầm nguồn: chặn release, kiểm tra ảnh hưởng, sửa policy rồi mới tiếp tục.

## 14. Bài tập và câu hỏi ôn tập

**Bài 1.** Hai thư viện cùng `artifactId=billing-api` nhưng khác `groupId` có cùng Maven identity không?

**Đáp án:** Không. Một GAV gồm `groupId:artifactId:version`. Tuy nhiên hai repositories khác nhau có thể cung cấp **cùng GAV**, dẫn đến nguy cơ source confusion.

**Bài 2.** POM ghim `dev.training.internal:billing-api:1.2.3`. Kho private không có version đó nhưng public proxy có. Kết quả an toàn là gì?

**Đáp án:** **Resolution phải fail**, không fallback sang public cho private namespace.

**Bài 3.** `mirrorOf=central` có thay tất cả repositories không?

**Đáp án:** Không. Nó chỉ thay repository ID `central`; những repo IDs khác có thể còn khả dụng.

**Bài 4.** `mirrorOf=*` đã đủ chưa?

**Đáp án:** Chưa. Cần repository manager chặn private groupIds đi qua public proxy. Mirror chỉ route requests tới một endpoint.

**Bài 5.** Tại sao version cao nhất ở public không luôn “thắng” trong Maven?

**Đáp án:** Dependency dùng version cố định không tự chọn bản cao hơn; repository precedence/context và version-resolution strategy khác nhau. Nguy cơ vẫn tồn tại với **cùng GAV** từ nguồn sai.

**Bài 6.** `dependency:tree` chứng minh artifact tải từ host nào không?

**Đáp án:** Không trực tiếp. Cần logs/resolver metadata và repository-manager upstream audit.

**Bài 7.** `<repositories>` khác `<pluginRepositories>` thế nào?

**Đáp án:** Một danh sách cho application dependencies; danh sách kia cho Maven plugin artifacts.

**Bài 8.** Maven 3.8.1 giải quyết loại repository risk nào?

**Đáp án:** Mặc định chặn external HTTP repositories theo `external:http:*`; không chặn mọi HTTPS repository không được phép.

**Bài 9.** Vì sao HTTPS không chứng minh nguồn artifact nội bộ?

**Đáp án:** TLS bảo vệ kết nối tới host, không chứng minh repository manager đã lấy đúng private artifact thay vì public proxy.

**Bài 10.** Java lab in gì?

**Đáp án:**

```text
private/private=true
private/public=false
public/public=true
public/unapproved=false
```

**Bài 11.** Lab có bao nhiêu JUnit Jupiter tests?

**Đáp án:** **6** tests.

**Bài 12.** `dev.training.internalfake` có thuộc private namespace `dev.training.internal.*` không?

**Đáp án:** Không. Cần exact match `dev.training.internal` hoặc bắt đầu bằng `dev.training.internal.`.

**Bài 13.** Java policy class có chặn Maven tải plugin từ untrusted host không?

**Đáp án:** Không. Đây là mô phỏng logic chạy trong JVM; Maven resolver đã chạy trước. Cần settings/repository manager source policy.

**Bài 14.** Nếu root POM không có `<repositories>`, Maven không dùng Central đúng không?

**Đáp án:** Sai. Maven Super POM có Central mặc định, trừ khi effective settings/mirror thay đổi luồng resolution.

**Bài 15.** Một dependency POM transitively khai báo kho riêng. Có cần quan tâm không?

**Đáp án:** Có. Maven xét repository context của dependency path; dùng trusted mirror và audit nguồn.

**Bài 16.** Enforcer `dependencyConvergence` có chứng minh repository origin không?

**Đáp án:** Không. Nó kiểm version consistency, không kiểm source repository.

**Bài 17.** `_remote.repositories` là bằng chứng ký số hay audit chính thức không?

**Đáp án:** Không. Nó là resolver metadata, có ích để điều tra nhưng không thay checksum từ nguồn được tin hoặc server audit.

**Bài 18.** Chỉ xóa `~/.m2` có giải quyết rủi ro không?

**Đáp án:** Không. Nếu routing vẫn sai, Maven có thể tải nhầm lại ở build tiếp theo.

**Bài 19.** Repository manager group có private ở trước public, vậy chắc chắn an toàn?

**Đáp án:** Không. Khi private thiếu version, group có thể tìm public; phải chặn theo private namespace.

**Bài 20.** Cần kiểm chứng gì trong CI ngoài exit code `BUILD SUCCESS`?

**Đáp án:** Effective settings, trusted mirrors, source policy của manager, resolved GAVs, upstream audit và provenance/hash của artifacts quan trọng.

## 15. Tài liệu chính thức

- [Apache Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html): repository order, effective settings/POM, repositories trong dependency paths.
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html): `mirrorOf` patterns, multiple mirror precedence, repository manager.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): mirrors, servers, active profiles và credential-origin rules cho Maven mới.
- [Apache Maven — Maven 3.8.1 Release Notes](https://maven.apache.org/docs/3.8.1/release-notes.html): CVE-2021-26291, external HTTP blocker và custom repositories trong dependency POM.
- [Apache Maven — Security](https://maven.apache.org/security): mô hình trust của Maven đối với POM, plugins, dependencies và repositories.
- [Apache Maven — Repository Management](https://maven.apache.org/repository-management.html): repository manager làm điểm quản trị proxy, repositories và builds.
- [Apache Maven Resolver — Local Repository](https://maven.apache.org/resolver/local-repository.html): cached/installed artifacts và enhanced local repository origin handling.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repositories và artifact resolution.
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html): xem settings đã merge, mật khẩu ẩn mặc định.
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): GAV, transitive dependency, version mediation.
- [Apache Maven POM Reference](https://maven.apache.org/pom.html): repositories, pluginRepositories, dependencyManagement, build.
- [Apache Maven Enforcer Rules](https://maven.apache.org/enforcer/enforcer-rules/index.html): `banDynamicVersions`, `bannedDependencies` và các rules bổ trợ.
