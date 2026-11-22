# Chính sách releases, snapshots và updatePolicy trong Maven

## 1. Cùng một repository nhưng hai chính sách artifact khác nhau

Maven lấy thư viện, plugin, POM và metadata từ các repository. Một repository không nhất thiết chấp nhận cả **release** lẫn **snapshot**, và Maven cho phép cấu hình **chính sách tải** cho hai loại artifact một cách độc lập bằng các thẻ `<releases>` và `<snapshots>` trong `<repository>` hoặc `<pluginRepository>`.

- **Release:** phiên bản đã phát hành, thường có tọa độ cố định như `org.apache.commons:commons-lang3:3.14.0` hoặc `edu.demo:billing-api:2.1.0`. Theo thực hành tốt, byte của một version release **không được thay đổi sau khi phát hành**.
- **Snapshot:** phiên bản đang phát triển như `edu.demo:billing-api:2.2-SNAPSHOT`. Cùng một base version `2.2-SNAPSHOT` có thể trỏ tới các bản build có timestamp khác nhau, thông qua metadata của repository.
- **`updatePolicy`:** Maven kiểm tra/cố gắng cập nhật thông tin hoặc artifact từ remote theo nhịp nào khi phân giải một dependency/plugin. Nó **không phải** lịch tự động build, không tự publish phiên bản mới và không ép repository bên ngoài phải thay đổi.

Hai điều quan trọng nhất:

1. `<releases><enabled>false</enabled></releases>` **không đồng nghĩa tắt cả repository**; Maven vẫn có thể sử dụng repository đó cho snapshot nếu `<snapshots>` được bật.
2. `<snapshots><updatePolicy>always</updatePolicy></snapshots>` **không đồng nghĩa “lần nào cũng tải lại cùng JAR”**; Maven có thể kiểm tra metadata rồi thấy bản đã có vẫn là bản mới nhất. Quyết định tải phụ thuộc metadata, local repository, HTTP cache, trạng thái remote và cách resolver xử lý.

Bài này tập trung vào **chính sách tải/phân giải artifact** (*repository policy*), không phải quy trình phát hành chi tiết bằng Maven Release Plugin. Tuy nhiên, hiểu vòng đời phát hành giúp chọn chính sách an toàn cho môi trường phát triển và CI.

## 2. Release và snapshot khác nhau về ý nghĩa phiên bản

| Tiêu chí | Release | Snapshot |
| --- | --- | --- |
| Tọa độ mẫu | `edu.demo:billing-api:2.1.0` | `edu.demo:billing-api:2.2-SNAPSHOT` |
| Mục đích | Phát hành có thể kiểm chứng và tái sử dụng | Tích hợp code đang phát triển, thử nghiệm trước phát hành |
| Tính ổn định kỳ vọng | Cùng tọa độ → cùng nội dung, theo chính sách repository | Cùng base version có thể thay đổi nội dung theo lần deploy |
| Metadata quan trọng | Danh sách version/metadata phục vụ khám phá và phân giải phiên bản | Metadata mapping snapshot sang timestamp/build number, thêm danh sách phiên bản |
| Nguy cơ với CI | Release bị ghi đè bất hợp lệ, version range, cache sai | Hai build khác thời điểm có thể chọn hai snapshot khác nhau |
| Thực hành thường dùng | Version cụ thể, repository release kiểm soát ghi đè | Snapshot repository riêng, chỉ dùng khi có chủ đích |
| Phù hợp sản xuất | Thông thường có | Thông thường không khuyến khích |

### 2.1. Một release nên bất biến

Giả sử ứng dụng phụ thuộc:

```xml
<dependency>
    <groupId>edu.demo</groupId>
    <artifactId>billing-api</artifactId>
    <version>2.1.0</version>
</dependency>
```

Hệ thống phân phối artifact nên đảm bảo khi `2.1.0` đã phát hành thì byte và các metadata quan trọng của artifact đó **không bị âm thầm ghi đè**. Nếu cần sửa lỗi, tạo phiên bản mới như `2.1.1` và công bố thay đổi rõ ràng.

Nếu một server cho phép ghi đè `billing-api:2.1.0` bằng nội dung khác, Maven ở máy A và CI ở máy B có thể giữ hai bản **cùng tên nhưng khác checksum**. Chính sách `updatePolicy` không chữa được một quy trình release có artifact mutable; cần sửa chính sách của repository manager và quy trình phát hành.

### 2.2. Snapshot là base version có thể được triển khai nhiều lần

Với `billing-api:2.2-SNAPSHOT`, remote repository có thể lưu nhiều bản build theo dạng **timestamped snapshot**; ví dụ minh họa:

```text
billing-api-2.2-20261110.091500-1.jar
billing-api-2.2-20261110.103000-2.jar
```

Timestamp và build number ở đây chỉ để **minh họa cấu trúc**, không phải artifact có thật. Maven thường tham chiếu `2.2-SNAPSHOT` trong POM, còn metadata ở remote giúp ánh xạ đến bản timestamped tương ứng. Không nên ghi cứng tên JAR timestamped vào `<version>` như một giải pháp phổ quát; cách resolver và quy tắc snapshot/version cụ thể cần được tôn trọng.

Khi một snapshot mới được deploy, **một project không sửa POM vẫn có thể dùng nội dung khác ở lần build sau**, nếu Maven kiểm tra metadata và chọn bản snapshot mới. Đây là tiện ích của snapshot cho phát triển nhanh, đồng thời là lý do cần quản lý chặt snapshot trên CI và trong phát hành sản phẩm.

## 3. Đọc cấu hình repository policy trong POM

Mỗi repository có URL/id, cùng các policy dành cho release và snapshot:

```xml
<repositories>
    <repository>
        <id>company-releases</id>
        <url>https://artifacts.example.invalid/maven-releases</url>
        <releases>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>

    <repository>
        <id>company-snapshots</id>
        <url>https://artifacts.example.invalid/maven-snapshots</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>interval:10</updatePolicy>
            <checksumPolicy>fail</checksumPolicy>
        </snapshots>
    </repository>
</repositories>
```

**Đây là đoạn POM để giải thích chính sách**, đặt bên trong một `<project>` hợp lệ, không phải tệp độc lập có thể build. Domain `example.invalid` được dùng có chủ đích vì không phải endpoint repository đang hoạt động; phải thay bằng URL được tổ chức cấp phép trước khi sử dụng thực tế.

Cách đọc:

- `company-releases`: được phép dùng cho release; không được dùng cho snapshot qua policy đó.
- `company-snapshots`: được phép dùng cho snapshot; không dùng cho release.
- `enabled` kiểm soát loại artifact mà Maven có thể tải từ repository được khai báo, **không phải quyền deploy lên server**.
- `updatePolicy` kiểm soát nhịp Maven kiểm tra cập nhật ở phía client.
- `checksumPolicy=fail` yêu cầu lỗi kiểm tra checksum làm build thất bại thay vì chỉ cảnh báo; điều này có ý nghĩa với tính toàn vẹn dữ liệu tải về.
- `id` là định danh quan trọng để chọn/ghi nhận repository và liên kết đến credential khi cần. Hai repository cần id nhất quán, dễ phân biệt.

Một repository duy nhất cũng có thể phục vụ cả release và snapshot bằng hai policy khác nhau. Tách thành hai endpoint thường giúp quản lý quyền deploy, retention, kiểm duyệt và chính sách release bất biến dễ hơn, nhưng **Maven không bắt buộc phải dùng hai server riêng**.

## 4. Bốn giá trị của updatePolicy: đọc đúng từng trường hợp

Apache Maven định nghĩa các giá trị:

| Giá trị | Ngữ nghĩa | Phù hợp khi | Cần chú ý |
| --- | --- | --- | --- |
| `always` | Mỗi khi quá trình phân giải yêu cầu và cần xét policy, Maven thực hiện kiểm tra cập nhật từ remote | Snapshot thay đổi nhanh, thử nghiệm tích hợp thường xuyên | Có thể tăng số yêu cầu mạng và phụ thuộc tình trạng repository |
| `daily` | Kiểm tra tối đa theo chu kỳ hằng ngày mà Maven dùng; đây là giá trị mặc định khi không cấu hình | Cân bằng tải mạng và độ mới | Snapshot mới publish trong cùng ngày có thể chưa được thấy ngay |
| `interval:X` | Đặt khoảng tối thiểu giữa các lần kiểm tra theo **X phút**, ví dụ `interval:10` | Cần snapshot mới trong nhịp phát triển xác định | Không có nghĩa Maven tự thức dậy cứ 10 phút để tải |
| `never` | Tránh kiểm tra cập nhật khi nội dung cần thiết đã được lưu cục bộ; thường chỉ tải nếu chưa tồn tại cục bộ | Kho đặc biệt đóng băng, cache cố định có chủ đích | Dễ dùng metadata cũ, kể cả metadata release có thể thay đổi |

**Mặc định của `updatePolicy` là `daily`.** Không có giá trị `hourly`, `weekly`, `every-build` hay `interval:30s` trong bộ giá trị chuẩn. `interval:X` tính bằng **phút nguyên**, không phải giây.

### 4.1. Ví dụ: snapshot mới xuất hiện sau lần kiểm tra đầu tiên

Giả sử lúc 09:00 Maven đã phân giải `billing-api:2.2-SNAPSHOT` và thấy bản snapshot số 1. Remote deploy bản số 2 lúc 09:05. Sau đó chạy build:

| Thời điểm | `updatePolicy` | Điều có thể xảy ra |
| --- | --- | --- |
| 09:06 | `always` | Maven kiểm tra metadata mới; nếu remote phản ánh bản số 2, có thể chọn/tải bản mới |
| 09:06 | `interval:10` | Thường chưa đến hạn kiểm tra từ 09:00; có thể tiếp tục dùng bản đã lưu |
| 09:11 | `interval:10` | Đã qua khoảng 10 phút; Maven có thể kiểm tra bản mới trong lần phân giải tiếp theo |
| 09:06 | `daily` | Trong chu kỳ ngày chưa đến hạn; thường giữ metadata đã cache |
| 09:06 | `never` | Không chủ động kiểm tra metadata mới nếu đã có dữ liệu cần thiết |

Đây là **mô hình thời gian minh họa**, không phải log bảo đảm đúng đến từng giây trong mọi Maven Resolver/repository manager. Nhiều yếu tố khác ảnh hưởng quyết định thực: thời điểm kiểm tra được ghi lại, trạng thái local cache, HTTP response, mirror, phiên bản Maven và chính sách cache ở server.

**Điểm mấu chốt:** `updatePolicy` chỉ được xét **khi Maven thực hiện resolution**; Maven không chạy cron ngầm để tự kiểm tra sau mỗi 10 phút.

### 4.2. Tại sao không nên đặt never cho mọi release?

Release đã phát hành nên bất biến, nhưng **metadata release vẫn có thể thay đổi** khi có phiên bản **mới** của artifact, khi resolver cần thông tin version hoặc khi plugin sử dụng metadata.

Vì vậy, `<releases><updatePolicy>never</updatePolicy></releases>` có thể làm thông tin khám phá phiên bản cũ đi, nhất là khi dùng version range hoặc các trường hợp phân giải dựa metadata. Tài liệu POM chính thức cũng cảnh báo `never` vì nó có thể ảnh hưởng cả **artifact và metadata** theo phiên bản Maven/Resolver.

Với build cần tái lập, ưu tiên **chốt release version cụ thể, không ghi đè release và quản lý cache**, thay vì dùng `never` như một cách duy nhất để khóa thế giới bên ngoài.

## 5. enabled không giống updatePolicy

Hai trường có vai trò khác nhau:

- `<snapshots><enabled>false</enabled></snapshots>`: Maven **không sử dụng repository đó** để tìm/tải snapshot qua chính sách snapshot.
- `<snapshots><enabled>true</enabled><updatePolicy>never</updatePolicy></snapshots>`: repository được phép phân giải snapshot, nhưng các bản đã cache sẽ không được chủ động kiểm tra cập nhật theo chính sách.

Tình huống:

```text
repository company-releases
  releases.enabled = true
  snapshots.enabled = false

dependency trong app
  edu.demo:billing-api:2.2-SNAPSHOT
```

Maven không thể lấy snapshot đó **từ company-releases** qua policy đang tắt snapshot. Nó có thể tìm ở **repository khác** có snapshot enabled, hoặc thấy artifact phù hợp trong local repository theo quy tắc resolution; chính sách của một repository không có nghĩa cấm artifact trên toàn bộ môi trường Maven.

Ngược lại, nếu snapshot repo được bật nhưng URL sai hoặc server trả 401/404, đặt `updatePolicy=always` cũng không giúp Maven có quyền tải hoặc tạo artifact chưa tồn tại.

## 6. Maven metadata: điều gì được kiểm tra và vì sao snapshot “đổi” được?

Một Maven repository lưu artifact theo đường dẫn của tọa độ, và thêm các tệp metadata XML có tên như `maven-metadata.xml`. Metadata không phải một dependency mà người dùng thêm trực tiếp vào POM; Maven Resolver vận hành nó khi cần.

### 6.1. GA/A-level metadata: liệt kê các version được công bố

Ở cấp `groupId/artifactId`, metadata có thể liệt kê các version đã biết và thời gian cập nhật, ví dụ giản lược:

```xml
<metadata>
    <groupId>edu.demo</groupId>
    <artifactId>billing-api</artifactId>
    <versioning>
        <latest>2.2-SNAPSHOT</latest>
        <release>2.1.0</release>
        <versions>
            <version>2.1.0</version>
            <version>2.2-SNAPSHOT</version>
        </versions>
        <lastUpdated>20261110101500</lastUpdated>
    </versioning>
</metadata>
```

Đây là **mẫu metadata minh họa**, không phải file nguyên văn được tải từ một repository có thật. Các trường có mặt có thể thay đổi tùy repository và bản metadata. Nó minh họa vì sao một repository release có artifact bất biến vẫn có metadata cập nhật khi bản release mới xuất hiện.

### 6.2. V-level metadata: ánh xạ base version SNAPSHOT đến bản timestamped

Trong thư mục version `2.2-SNAPSHOT`, snapshot metadata có thể mô tả:

```xml
<metadata>
    <groupId>edu.demo</groupId>
    <artifactId>billing-api</artifactId>
    <version>2.2-SNAPSHOT</version>
    <versioning>
        <snapshot>
            <timestamp>20261110.103000</timestamp>
            <buildNumber>2</buildNumber>
        </snapshot>
        <lastUpdated>20261110103000</lastUpdated>
        <snapshotVersions>
            <snapshotVersion>
                <extension>jar</extension>
                <value>2.2-20261110.103000-2</value>
                <updated>20261110103000</updated>
            </snapshotVersion>
            <snapshotVersion>
                <extension>pom</extension>
                <value>2.2-20261110.103000-2</value>
                <updated>20261110103000</updated>
            </snapshotVersion>
        </snapshotVersions>
    </versioning>
</metadata>
```

Mẫu này thể hiện **cách mapping snapshot thường thấy**, không phải metadata bắt buộc có từng trường và giá trị y hệt. Bản JAR timestamped được tham chiếu trong metadata có thể là:

```text
billing-api-2.2-20261110.103000-2.jar
```

POM người dùng vẫn thường khai báo `<version>2.2-SNAPSHOT</version>`. Khi Maven cập nhật metadata, base version đó có thể được giải đến một file timestamped mới. Một cache Maven cũ có thể giữ mapping trước đó nếu chưa tới hạn kiểm tra `updatePolicy`.

### 6.3. Metadata không đảm bảo artifact đã tải thành công

Có thể metadata nói snapshot số 2 tồn tại nhưng JAR/POM tương ứng chưa truy cập được vì repository manager đang đồng bộ, quyền thiếu hoặc upstream không có. Khi đó Maven vẫn có thể báo lỗi resolution dù metadata mới.

Vì vậy khi debug snapshot, phân biệt:

1. **Maven có đang kiểm tra metadata hay dùng cache?**
2. **Metadata đã chỉ đến build/timestamp nào?**
3. **Artifact thật của timestamp đó có tồn tại và tải được không?**
4. **JAR cuối cùng mà project dùng đến từ local repo hay remote nào?**

## 7. Khai báo repository trong POM và settings.xml

### 7.1. POM profile: chia sẻ chính sách không chứa secrets

Một repository snapshot có thể được bật bằng Maven profile có chủ đích:

```xml
<profiles>
    <profile>
        <id>use-company-snapshots</id>
        <repositories>
            <repository>
                <id>company-snapshots</id>
                <url>https://artifacts.example.invalid/maven-snapshots</url>
                <releases>
                    <enabled>false</enabled>
                </releases>
                <snapshots>
                    <enabled>true</enabled>
                    <updatePolicy>interval:10</updatePolicy>
                    <checksumPolicy>fail</checksumPolicy>
                </snapshots>
            </repository>
        </repositories>
    </profile>
</profiles>
```

Đây là đoạn POM có URL **giả định**. Trong một dự án có repository thật, có thể bật profile bằng:

```bash
mvn -Puse-company-snapshots -B test
```

Nếu profile chưa khai báo trong POM/settings, `-P` không tự tạo repository; cần thực sự có profile tương ứng. Đặt snapshot repo trong profile giúp CI release không vô tình phụ thuộc vào snapshot khi profile chưa bật.

### 7.2. Settings profile: cấu hình theo môi trường

Có thể đặt repository policy trong `settings.xml` theo môi trường; ví dụ **tệp settings đầy đủ tối giản** không có credential:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <profiles>
        <profile>
            <id>snapshot-development</id>
            <repositories>
                <repository>
                    <id>company-snapshots</id>
                    <url>https://artifacts.example.invalid/maven-snapshots</url>
                    <releases>
                        <enabled>false</enabled>
                    </releases>
                    <snapshots>
                        <enabled>true</enabled>
                        <updatePolicy>interval:10</updatePolicy>
                        <checksumPolicy>fail</checksumPolicy>
                    </snapshots>
                </repository>
            </repositories>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>snapshot-development</activeProfile>
    </activeProfiles>
</settings>
```

Tệp này chỉ là ví dụ cấu trúc và **không hoạt động với domain .invalid**. Trong môi trường thật, dùng URL nội bộ chính thức, kiểm tra id và quyền truy cập. Settings profile có các thành phần phù hợp như repositories, pluginRepositories và properties, **không phải nơi thay thế toàn bộ cấu hình build của POM**.

### 7.3. Credential trong settings tách biệt khỏi POM

Nếu repository cần authentication, có thể có đoạn:

```xml
<servers>
    <server>
        <id>company-snapshots</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
</servers>
```

Đây chỉ là **một phần settings.xml**, không phải XML độc lập. Các biến môi trường phải do secret manager của CI cấp, không commit token hay password vào Git. `server id` cần khớp **repository id thực tế được kết nối hoặc mirror id khi mirror được sử dụng**, chứ không chỉ là tên server trong tài liệu.

Phần `<servers>` không sửa chính sách snapshot/release của repository. Nó giải quyết **cách Maven xác thực khi truy cập**. Nếu HTTP 401/403, đổi `updatePolicy` không giải quyết quyền.

## 8. Plugin repositories có chính sách releases/snapshots riêng

Maven phân biệt nơi lấy **dependency của ứng dụng** với nơi lấy **build plugins**:

- `<repositories>`: nơi phân giải project dependencies.
- `<pluginRepositories>`: nơi phân giải Maven plugins và các artifact dùng cho plugin theo cơ chế plugin resolution.

Nếu một nhóm phát hành Maven plugin nội bộ ở phiên bản `1.5-SNAPSHOT`, có thể cần khai báo snapshot policy cho `pluginRepository`, không chỉ `repository`.

Ví dụ **đoạn POM**:

```xml
<pluginRepositories>
    <pluginRepository>
        <id>company-plugin-snapshots</id>
        <url>https://artifacts.example.invalid/maven-plugin-snapshots</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
            <checksumPolicy>fail</checksumPolicy>
        </snapshots>
    </pluginRepository>
</pluginRepositories>
```

Nếu Maven lỗi `Plugin ... could not be resolved`, kiểm tra cả pluginRepository, mirror, metadata và quyền truy cập; không chỉ thêm dependency repository cho Java.

**Khuyến nghị:** cố định plugin version cho build quan trọng. Dùng plugin bản snapshot liên tục có thể khiến quá trình build thay đổi dù POM của ứng dụng không đổi.

## 9. Mirror và repository manager có thể làm kết quả khác chính sách client

Trong nhiều công ty, Maven không kết nối trực tiếp đến Maven Central hay snapshot server mà dùng một repository manager (Nexus, Artifactory hoặc sản phẩm phù hợp). `settings.xml` có thể cấu hình mirror:

```xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>external:*</mirrorOf>
        <url>https://artifacts.example.invalid/maven-group</url>
    </mirror>
</mirrors>
```

Maven chọn mirror phù hợp cho repository, sau đó kết nối đến URL mirror; một số rule mirror có thể bắt nhiều repository khác nhau vào một endpoint. Khi đó:

- Policy `enabled`/`updatePolicy` của các repository logic và thông tin resolver vẫn quan trọng khi Maven quyết định phân giải.
- Repository manager có **cache TTL, policy proxy, retention và quyền** riêng; client kiểm tra metadata mới không đồng nghĩa server đã refresh upstream.
- Nếu dùng mirror, credential thường gắn với **id mirror** để xác thực với endpoint mirror.
- Một mirror group chưa cấu hình proxy snapshot có thể không có artifact snapshot dù POM khai báo snapshot repository đúng.

**Không coi `-U` là công tắc bỏ qua mọi lớp cache.** Nó có thể yêu cầu Maven kiểm tra update ở phía client, nhưng không buộc repository manager xuyên qua cache upstream, không tạo artifact chưa publish và không vô hiệu các chính sách bảo mật của server.

Để chẩn đoán, cần xem **effective settings**, repository id gốc, mirror được chọn và response từ endpoint đã được phê duyệt; đừng ghi password/token vào log.

## 10. -U, -o và cache: cách tác động từ dòng lệnh

### 10.1. -U / --update-snapshots

```bash
mvn -U -B clean verify
```

`-U` được dùng để buộc Maven **kiểm tra cập nhật snapshot** và các trường hợp release bị thiếu theo hành vi của phiên bản Maven phù hợp. Tài liệu CLI thường mô tả nó là công tắc để ép kiểm tra updated snapshots/missing releases.

Nó **không đồng nghĩa**:

- Tải lại mọi bản release đã có dù byte không đổi.
- Thay version khai báo trong POM thành version mới nhất.
- Xóa local repository.
- Bỏ qua mirror hoặc quyền xác thực.
- Bảo đảm toàn bộ lần build dùng artifact mới nếu proxy repository đang stale, metadata chưa cập nhật hoặc artifact không tải được.

Ví dụ, khi đang dùng `billing-api:2.2-SNAPSHOT` và nghi ngờ cache metadata cũ, `mvn -U test` là bước chẩn đoán hợp lý. Nếu nó không thay đổi kết quả, kiểm tra profile/repository/mirror, timestamp metadata và bản snapshot thật đang được publish.

### 10.2. -o / --offline

```bash
mvn -o -B test
```

`-o` yêu cầu Maven hoạt động **offline**: không kiểm tra remote, dùng những artifact/metadata đã có trong local repository và đáp ứng resolution. Nếu dependency/plugin chưa có ở local repo, build có thể thất bại.

Điều đó khác `updatePolicy=never`:

| Tình huống | `updatePolicy=never` | `mvn -o` |
| --- | --- | --- |
| Artifact cần thiết chưa có local | Vẫn có thể tải từ remote khi cần, tùy metadata/policy | Không tải từ remote |
| Artifact đã có local | Tránh kiểm tra cập nhật định kỳ qua policy | Chỉ dùng local |
| Cần snapshot vừa deploy | Có thể không cập nhật cache hiện có | Không thể kiểm tra remote |
| Phạm vi | Policy của một loại artifact ở repository được khai báo | Chế độ của cả lần chạy Maven |

Đừng kết luận một dự án “không cần mạng” chỉ vì local chạy offline thành công: nó có thể chỉ là máy đã tải sẵn toàn bộ dependency/plugin.

### 10.3. Negative caching và file lastUpdated

Khi Maven từng không tải được artifact/metadata, local repository có thể ghi trạng thái lần thử thất bại, thường thấy qua các file `*.lastUpdated` hoặc thông tin liên quan đến cache của Resolver. Những thông báo như `... was cached in the local repository, resolution will not be reattempted until the update interval ...` có thể liên quan chính sách kiểm tra cập nhật.

Cách xử lý:

1. Kiểm tra **artifact tồn tại thật** trên remote và policy `enabled` có cho phép loại version đó không.
2. Kiểm tra URL, mirror, DNS/TLS, proxy, credentials và repository id.
3. Khi nguyên nhân đã được sửa và cần thử ngay, dùng `-U` để yêu cầu Maven kiểm tra lại theo ngữ nghĩa tương ứng.
4. Nếu vẫn lỗi, đọc log debug ở môi trường an toàn và kiểm tra trạng thái local repo; không tùy tiện xóa toàn bộ `~/.m2/repository` của máy chung.
5. Nếu cần kiểm chứng sạch, dùng **local repository tách biệt** thay vì phá hủy cache hiện tại.

Lệnh kiểm chứng có chủ đích:

```bash
mvn -B -Dmaven.repo.local=.m2-test-cache clean verify
```

Nó dùng local repository trong thư mục `.m2-test-cache` tương đối với nơi Maven được chạy. Phải đảm bảo thư mục được ignore trong Git, đủ dung lượng và policy cho phép tải dependency từ remote. Nếu dự án nhiều module hoặc cấu hình working directory khác, nên xác nhận đường dẫn thực tế.

## 11. Ví dụ Java 17 tự chạy được bằng release dependency

Bài thực hành này dùng **dependency release thực tế từ repository chuẩn**, không phụ thuộc vào server `.invalid` trong các ví dụ cấu hình ở trên. Nó giúp kiểm tra rằng khi POM chỉ có release cố định, việc build không cần cho phép snapshot repository riêng.

### 11.1. Cấu trúc dự án

```text
repository-policy-demo/
├── pom.xml
└── src/
    ├── main/java/demo/policy/PolicyApp.java
    └── test/java/demo/policy/PolicyAppTest.java
```

Cần JDK 17+, Maven tương thích và kết nối đến repository đã được tổ chức cho phép để tải dependency/plugin lần đầu. Nếu môi trường đã dùng mirror nội bộ, Maven có thể tải qua mirror thay vì trực tiếp từ Maven Central.

### 11.2. POM hoàn chỉnh

Tệp `repository-policy-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>repository-policy-demo</artifactId>
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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
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
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
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

Ở đây không khai báo `<repositories>` vì Maven Super POM và settings phù hợp đã có cơ chế phân giải repository mặc định cho artifact phát hành, thường là Maven Central hoặc mirror doanh nghiệp. Các dependency và plugin được dùng đều là **release có version cụ thể**, giúp dễ tái lập hơn snapshot.

Điều đó không có nghĩa mọi máy buộc phải kết nối trực tiếp Central: `settings.xml` của CI có thể thay endpoint bằng mirror. Cần kiểm tra quyền và nguồn tải thực tế của tổ chức.

### 11.3. Mã nguồn sản phẩm

Tệp `repository-policy-demo/src/main/java/demo/policy/PolicyApp.java`:

```java
package demo.policy;

import org.apache.commons.lang3.StringUtils;

public final class PolicyApp {
    private PolicyApp() {
    }

    public static String message(String name) {
        if (StringUtils.isBlank(name)) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Repository policy: " + StringUtils.capitalize(name.trim());
    }

    public static void main(String[] args) {
        System.out.println(message("maven"));
    }
}
```

Mã thật sự gọi API của Commons Lang nên dependency `commons-lang3` là dependency compile/runtime, không chỉ để minh họa trong POM.

### 11.4. Unit test JUnit Jupiter

Tệp `repository-policy-demo/src/test/java/demo/policy/PolicyAppTest.java`:

```java
package demo.policy;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PolicyAppTest {
    @Test
    void formatsText() {
        assertEquals("Repository policy: Maven",
                     PolicyApp.message(" maven "));
    }

    @Test
    void rejectsEmptyName() {
        assertThrows(IllegalArgumentException.class,
                     () -> PolicyApp.message("  "));
    }
}
```

Hai test dùng API JUnit Jupiter; scope test giúp JUnit không thành dependency runtime sản phẩm.

### 11.5. Build và chạy

Trong thư mục `repository-policy-demo`:

```bash
mvn -B clean test
mvn -B package
```

Với POM và mã như trên, Surefire chạy **2 test, 0 failures, 0 errors** ở cả những lần build có test chưa bị skip (lần `package` có thể thực thi lại test). Log Maven cụ thể thay đổi theo phiên bản môi trường, nên phải xem `target/surefire-reports` để xác minh thay vì cố định toàn bộ stdout Maven.

Để chạy lớp Java bằng **runtime classpath thực** trên Linux/macOS, cần cung cấp cả lớp sản phẩm và Commons Lang. Nếu thư viện đã được phân giải, có thể dùng Maven Dependency Plugin lấy classpath:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/runtime.classpath
```

File `target/runtime.classpath` chứa đường dẫn đến những dependency JAR mà plugin chọn theo runtime scope, **không tự gồm `target/classes`**. Trên Linux/macOS có thể dùng:

```bash
java -cp "target/classes:$(cat target/runtime.classpath)" demo.policy.PolicyApp
```

Lệnh `$(cat ...)` là thay thế lệnh của shell POSIX, không dùng nguyên văn trong Windows PowerShell. Trên PowerShell có thể dùng:

```powershell
$deps = Get-Content -Raw target/runtime.classpath
java -cp "target\classes;$deps" demo.policy.PolicyApp
```

Khi build và runtime classpath đúng, **stdout riêng của lệnh Java** là:

```text
Repository policy: Maven
```

Nếu chạy `java -cp target/classes demo.policy.PolicyApp` mà thiếu Commons Lang, ứng dụng có thể báo `NoClassDefFoundError`. Lỗi đó không phải do snapshot/updatePolicy mà do lệnh Java ngoài Maven chưa cấp đủ runtime JAR.

### 11.6. Làm sao quan sát tác động của updatePolicy với snapshot?

POM chạy được ở trên dùng toàn release; để thử snapshot policy thật cần một artifact `*-SNAPSHOT` được **publish** vào snapshot repository đã được cấp phép, với POM và metadata hợp lệ.

Ví dụ một dependency **chỉ có thể phân giải sau khi tổ chức đã triển khai artifact tương ứng**:

```xml
<dependency>
    <groupId>edu.demo</groupId>
    <artifactId>billing-api</artifactId>
    <version>2.2-SNAPSHOT</version>
</dependency>
```

Và một repository snapshot `company-snapshots` đã khai báo/bật đúng policy. Thực hành:

1. Build lần đầu để Maven tải snapshot số 1.
2. Đảm bảo nhà phát hành deploy **snapshot số 2** cùng base version, metadata trên remote thực sự đã cập nhật.
3. Chạy lại trong khoảng thời gian chưa đến hạn của `interval:10`; quan sát có thể vẫn dùng snapshot đã cache.
4. Chạy lại sau khi hết khoảng interval hoặc dùng `mvn -U test` để yêu cầu kiểm tra mới.
5. Đối chiếu bản timestamped cụ thể được Maven resolve, checksum, dependency tree và test; không chỉ nhìn tên base version trong POM.

**Không có một stdout cố định** cho bước này: kết quả phụ thuộc server thật, thời điểm deploy, cache, policy, phiên bản Maven và network. Không nên mô tả giả một bản snapshot số 2 chắc chắn được tải nếu chưa có artifact và metadata tương ứng.

## 12. Cách chẩn đoán khi Maven “không thấy snapshot mới”

Làm theo thứ tự để phân biệt cấu hình sai với cache:

1. **Xác nhận đúng tọa độ** `groupId:artifactId:version`; version có đúng hậu tố `-SNAPSHOT` không?
2. **Xác nhận snapshot đã publish lên đúng remote repository**; kiểm tra metadata timestamp/build number bằng công cụ của repository manager trong phạm vi được cấp quyền.
3. **Kiểm tra repository policy**: `<snapshots><enabled>true</enabled></snapshots>` có hiệu lực cho repository cần thiết không?
4. **Kiểm tra profile**: repository snapshot nằm trong POM/settings profile nào, profile đó có active trên build đang chạy không?
5. **Kiểm tra mirror**: `settings.xml` có ánh xạ repository sang host khác không; group repository có thực sự chứa snapshot upstream không?
6. **Kiểm tra updatePolicy**: `daily`, `interval:10` hay `never` có đang ngăn một lượt kiểm tra cập nhật mong đợi không?
7. **Thử `-U` có kiểm soát**, không dùng như giải pháp vĩnh viễn che cấu hình sai.
8. **Kiểm tra offline**: `-o` hoặc settings `<offline>true</offline>` có đang ngăn mọi request remote?
9. **Kiểm tra lỗi mạng/quyền**: 401, 403, 404, DNS, proxy, TLS/CA và cached failures.
10. **So trên local repo tách biệt** nếu được phép, để xác định trạng thái cache cũ có phải nguyên nhân hay không.
11. **Chạy lại test và kiểm tra artifact đã được nạp** sau khi chọn snapshot mới; snapshot mới có thể không tương thích với mã hiện tại.

Các công cụ Help Plugin hữu ích:

```bash
mvn -B help:effective-settings
mvn -B help:active-profiles
mvn -B help:effective-pom
```

Chúng giúp xác định settings, profile và cấu hình POM được Maven sử dụng. Khi dùng `-X` để debug resolver hoặc HTTP, log có thể chứa URL nội bộ hoặc dữ liệu nhạy cảm. Không chia sẻ log chưa rà soát, và tuyệt đối không in credential.

## 13. Các lỗi và hiểu lầm thường gặp

| Phát biểu/triệu chứng | Vì sao chưa đúng? | Cách xử lý |
| --- | --- | --- |
| “`updatePolicy=always` sẽ tải lại JAR mỗi lần build.” | Policy yêu cầu kiểm tra cập nhật, không nhất thiết luôn tải lại byte. | Đối chiếu metadata, timestamp và local cache. |
| “`daily` nghĩa là tự động kiểm tra lúc 00:00.” | Maven không chạy lịch ngầm; chỉ kiểm tra khi có resolution và policy đến hạn. | Chạy Maven khi cần; giải thích thời điểm kiểm tra. |
| “`interval:10` là 10 giây.” | Đơn vị là **phút**. | Dùng giá trị phút nguyên đúng nhu cầu. |
| “`never` cấm tải artifact chưa có.” | Nó không giống offline; có thể vẫn tải artifact chưa có, tùy metadata/policy. | Phân biệt `never` với `mvn -o`. |
| “Release không đổi nên đặt release updatePolicy=never luôn an toàn.” | Metadata release vẫn có thể thay đổi khi phiên bản mới xuất hiện. | Dùng release bất biến, version cụ thể và policy được phê duyệt. |
| “`-U` nâng tất cả dependency lên latest.” | Nó không sửa version trong POM hoặc tự chọn latest bất chấp tọa độ. | Sửa/duyệt version riêng; dùng `-U` để kiểm tra snapshot/missing releases. |
| “Cấu hình `<snapshots><enabled>false</enabled>` ở một repo cấm snapshot trên mọi repo.” | Policy chỉ áp dụng repository đó; repo khác/local cache có thể cung cấp artifact. | Kiểm tra toàn bộ effective repositories và mirrors. |
| “Thêm `<repository>` là đủ để Maven tìm SNAPSHOT plugin.” | Plugin sử dụng hệ `pluginRepositories` riêng. | Cấu hình plugin repository đúng phạm vi. |
| “Snapshot metadata mới bảo đảm JAR đã có và tải được.” | Server có thể thiếu artifact, quyền hoặc cache chưa đồng bộ. | Kiểm tra metadata *và* artifact/HTTP response. |
| “GAV SNAPSHOT không đổi nên các build tái lập được.” | Cùng base version có thể giải ra timestamp/build mới. | Ghi nhận artifact cụ thể hoặc dùng release cho phát hành ổn định. |
| “`checksumPolicy=fail` bảo đảm hoàn toàn an toàn.” | Checksum hỗ trợ toàn vẹn, không thay thế xác thực, HTTPS, provenance hay kiểm duyệt dependency. | Dùng TLS, repository tin cậy, checksum và chính sách supply chain. |
| “Maven tải đúng trên laptop thì CI chắc giống.” | Local cache, settings, mirror, profile hoặc Maven/JDK có thể khác. | Xác minh trên agent sạch với cùng build command. |
| “404 cached thì cứ xóa cả `~/.m2/repository`.” | Có thể phá cache của dự án khác mà không chữa cấu hình sai. | Kiểm tra nguồn lỗi, `-U`, rồi thử local repo tách biệt. |

Một nguyên nhân dễ bị bỏ sót: phiên bản release hoặc snapshot đã có trong local repo **nhưng không phải bản tổ chức dự kiến** vì trước đó được cài thủ công bằng `mvn install` hoặc lấy từ một repository khác. Khi cần truy xuất nguồn gốc, xem metadata local/repository origin và quy trình phát hành; không chỉ xem tên thư mục `~/.m2/repository/...`.

## 14. Chọn chính sách cho môi trường phát triển, CI và phát hành

Không có một giá trị `updatePolicy` tối ưu cho mọi hệ thống. Quyết định dựa trên **mức độ cần cập nhật, tính tái lập, tải repository và thời gian build**.

| Môi trường | Cách tiếp cận thường hợp lý | Điều kiện để áp dụng an toàn |
| --- | --- | --- |
| Máy phát triển hằng ngày | Release version cụ thể; snapshot chỉ cho module đang tích hợp, `daily` hoặc `interval:X` hợp lý | Repository snapshot rõ nguồn, tránh tải lại liên tục vô ích |
| CI kiểm tra nhánh phát triển | Có thể bật snapshot và dùng `-U` khi cần bắt thay đổi upstream ngay | Cache được quản lý, test chạy thật, log ghi artifact đã resolve |
| CI phát hành sản phẩm | Ưu tiên release bất biến và version cố định cho dependencies/plugins | Không phụ thuộc ngầm snapshot, kiểm tra checksum, lưu manifest/SBOM |
| Build offline | Dùng `-o` sau khi chuẩn bị đầy đủ cache có nguồn gốc tin cậy | Không kỳ vọng lấy metadata/artifact mới |
| Repository nội bộ | Tách chính sách release/snapshot, chặn overwrite release, retention snapshot | Proxy/mirror, quyền deploy, snapshot cleanup và cache TTL được tài liệu hóa |

### 14.1. Ví dụ CI cho release

Trong một dự án đã quản lý version Maven Wrapper và repository hợp lệ:

```bash
./mvnw -B -ntp clean verify
```

Lệnh này không có `-U` bắt buộc vì release build nên dựa trên dependency/plugin version cụ thể. Tuy nhiên, việc không dùng `-U` **không tự đảm bảo khả năng tái lập** nếu POM có snapshot, version range, plugin version chưa chốt, repository cho phép ghi đè hoặc toolchain thay đổi.

Để kiểm tra chất lượng build, đọc báo cáo test thật, dependency graph và artifact manifest. Chỉ dùng `-ntp` trên phiên bản Maven/Wrapper hỗ trợ và đã được tổ chức chấp thuận.

### 14.2. Ví dụ CI cho nhánh tích hợp snapshot

```bash
./mvnw -B -ntp -U clean verify
```

Nếu dự án có snapshot dependency cần cập nhật ngay, `-U` giúp Maven kiểm tra snapshot theo chính sách override của lần chạy. Nhưng vẫn cần quan sát artifact timestamp nào thực tế đã được phân giải và kết quả test: hai lần chạy có thể chọn hai snapshot khác nhau và làm phát sinh regression.

### 14.3. Checklist bảo vệ tính tái lập

- [ ] Version dependency và plugin được quản lý/chốt rõ ràng khi build sản phẩm.
- [ ] Release repository áp dụng **không ghi đè version đã phát hành**.
- [ ] Snapshot chỉ được bật trong những profile/repository có chủ đích.
- [ ] `updatePolicy` phản ánh nhịp tích hợp và tải repository chấp nhận được.
- [ ] Maven Wrapper/JDK/toolchain và POM hiệu lực được ghi nhận.
- [ ] Mirror/repository manager có rule cache và quyền rõ ràng.
- [ ] Checksum policy, TLS và kiểm soát nguồn artifact đáp ứng quy định của tổ chức.
- [ ] Build trên môi trường sạch phân giải được dependency/plugin từ repository được phép.
- [ ] CI chạy thật những test quan trọng, không chỉ tạo JAR.
- [ ] Nếu dùng snapshot, lưu thông tin timestamp/build/sha hoặc artifact manifest cần thiết để truy vết.

## 15. Tổng kết: ba câu hỏi trước khi chỉnh policy

Trước khi thay `releases`, `snapshots` hay `updatePolicy`, hãy trả lời:

**1. Maven có được dùng repository này cho loại artifact đang cần không?** Xem `<releases><enabled>...` và `<snapshots><enabled>...`.

**2. Nếu được dùng, khi nào Maven thử kiểm tra cập nhật?** Xem `updatePolicy=always/daily/interval:X/never`, trạng thái local cache và có `-U` hoặc `-o` không.

**3. Server thực sự cung cấp artifact nào?** Xem `maven-metadata.xml`, snapshot mapping, mirror/repository manager, quyền và trạng thái tải thật. Policy của client không thay thế metadata hay nội dung server.

**Ghi nhớ:** **release** nên là artifact phát hành bất biến; **snapshot** là phiên bản có thể đổi theo lần deploy; **`updatePolicy`** điều chỉnh tần suất kiểm tra cập nhật **khi Maven phân giải**, chứ không ấn định build mới hoặc đảm bảo luôn tải byte mới. Muốn một hệ thống Maven đáng tin, phải kết hợp policy repository, metadata, cache, kiểm thử, version pinning và quy trình phát hành được kiểm soát.

### Tài liệu chính thức

- [Apache Maven — POM Reference: Repositories, releases, snapshots](https://maven.apache.org/pom.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html)
- [Apache Maven — Guide to Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Configuring Apache Maven](https://maven.apache.org/configure.html)
