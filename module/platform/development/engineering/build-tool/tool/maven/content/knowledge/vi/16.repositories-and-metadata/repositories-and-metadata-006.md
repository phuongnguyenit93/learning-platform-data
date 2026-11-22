# SNAPSHOT, Maven Metadata và artifact có timestamp

## 1. SNAPSHOT là gì và vì sao cần hiểu metadata?

Maven định danh một artifact bằng các tọa độ thường gặp **groupId:artifactId:version**, thêm packaging/type và classifier khi cần. Ví dụ `org.example.learning:snapshot-library:1.0-SNAPSHOT` là một thư viện đang trong quá trình phát triển. Hậu tố **`-SNAPSHOT`** có ý nghĩa đặc biệt: cùng một base version có thể được build/deploy nhiều lần và người tiêu thụ có thể nhận **nội dung mới hơn** khi Maven kiểm tra snapshot repository.

Một số điểm cốt lõi:

- **Base version:** `1.0-SNAPSHOT` là tọa độ mà `pom.xml` của producer/consumer thường khai báo.
- **Timestamped snapshot version:** Khi upload SNAPSHOT lên remote repository với cơ chế snapshot duy nhất thông thường, Maven thay phần `SNAPSHOT` bằng thời điểm UTC và build number, ví dụ `1.0-20261110.143025-3`.
- **Artifact có timestamp:** JAR có thể được lưu trên remote dưới tên `snapshot-library-1.0-20261110.143025-3.jar`, còn thư mục repository vẫn mang base version `1.0-SNAPSHOT`.
- **`maven-metadata.xml`:** metadata của repository giúp Maven ánh xạ **`1.0-SNAPSHOT` → bản timestamped hiện đang được công bố** cho từng artifact extension/classifier.
- **Local repository:** `mvn install` và artifact cache từ remote **không bắt buộc có cùng cách đặt tên** trên đĩa. Bản tự build/install thường dùng base version, trong khi bản cache từ remote có thể dùng timestamped filename.
- **Tính tái lập:** `1.0-SNAPSHOT` là **moving target**. Hai lần resolve vào những thời điểm khác nhau có thể dùng bytecode khác nhau dù POM consumer không đổi.

SNAPSHOT thuận tiện cho **thử nghiệm và tích hợp liên tục**; **RELEASE** như `1.0.0` phù hợp hơn cho bản phát hành cần nhận diện ổn định. Tên có timestamp không đồng nghĩa có Git commit, cũng không phải mọi timestamp là thời điểm mã được commit.

Mục tiêu của bài: hiểu cơ chế snapshot resolution/deployment, vị trí và nội dung metadata, sự khác nhau giữa local/remote repositories, cách kiểm soát cập nhật và cách phân tích lỗi khi CI hoặc máy khác nhận nhầm phiên bản.

## 2. Từ 1.0-SNAPSHOT đến artifact timestamped: một ví dụ dễ hình dung

Giả sử thư viện có:

~~~xml
<groupId>org.example.learning</groupId>
<artifactId>snapshot-library</artifactId>
<version>1.0-SNAPSHOT</version>
<packaging>jar</packaging>
~~~

Khi deploy, Maven có thể tạo một snapshot duy nhất với version đã biến đổi:

~~~text
POM producer:
  org.example.learning:snapshot-library:1.0-SNAPSHOT
                          |
                    mvn deploy
                          |
                          v
Remote snapshot repository:
  org/example/learning/snapshot-library/1.0-SNAPSHOT/
    snapshot-library-1.0-20261110.143025-3.jar
    snapshot-library-1.0-20261110.143025-3.pom
    maven-metadata.xml
    ... checksum và artifact đính kèm nếu có
~~~

Đọc version timestamp:

~~~text
1.0-20261110.143025-3
 |  |       |     |
 |  |       |     +-- buildNumber = 3
 |  |       +-------- HHmmss = 14:30:25 (UTC)
 |  +---------------- yyyyMMdd = 2026-11-10 (UTC)
 +------------------- version prefix = 1.0
~~~

**Các con số ngày/giờ/build number trong toàn bài đều là ví dụ minh họa**, không phải thông tin về repository thật. Với Maven snapshot remote mặc định, timestamp theo **UTC** và có dạng `yyyyMMdd.HHmmss`; build number là số thứ tự tăng gắn với snapshot deployment của base version tại repository đó. Nó **không phải** JDK version, Git commit number, số run toàn hệ thống CI hay số version `1.0.3`.

**Điểm rất quan trọng:** Consumer vẫn thường khai báo `<version>1.0-SNAPSHOT</version>`. Maven đọc metadata để biết cần lấy file JAR/POM có **version thực tế** nào. Consumer không cần sửa POM sau từng lần producer deploy.

## 3. Phân biệt baseVersion, version và thư mục lưu trữ

Trong Maven Resolver, cách gọi **baseVersion** thường chỉ version tọa độ logic kết thúc bằng `-SNAPSHOT`, ví dụ `1.0-SNAPSHOT`. Một **resolved snapshot version** có thể là bản timestamped `1.0-20261110.143025-3`.

Bảng phân biệt:

| Thành phần | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| Version producer khai báo trong `pom.xml` | `1.0-SNAPSHOT` | Version logic của artifact đang phát triển. |
| Version consumer thường khai báo | `1.0-SNAPSHOT` | Muốn dùng snapshot hiện có theo cơ chế repository/update policy. |
| Remote directory của base version | `.../snapshot-library/1.0-SNAPSHOT/` | Nơi lưu metadata và các snapshot builds cùng base version. |
| Filename một remote JAR đã deploy | `snapshot-library-1.0-20261110.143025-3.jar` | Phiên bản bytecode cụ thể được lưu trên repository. |
| Filename remote POM tương ứng | `snapshot-library-1.0-20261110.143025-3.pom` | Descriptor artifact của deployment tương ứng. |
| Version-level metadata | `maven-metadata.xml` | Ánh xạ SNAPSHOT logic sang timestamped artifact mới nhất theo extension/classifier. |
| Bản `mvn install` ở local repository | Thường `snapshot-library-1.0-SNAPSHOT.jar` | Bản tự build và install cục bộ, dùng baseVersion. |
| Bản cache khi tải từ remote | Có thể mang timestamped filename | Phụ thuộc Maven Resolver và cách tổ chức local repository. |

Không viết code/script giả định rằng mọi máy luôn có đường dẫn `~/.m2/repository/.../artifact-1.0-SNAPSHOT.jar`. Maven local repository là **cache và nơi chứa artifact tự install**, layout có thể thay đổi theo Resolver, cấu hình split repository và nguồn artifact. Nên để Maven giải quyết tọa độ thông qua API/tool hoặc dùng goal có mục đích rõ ràng, thay vì tự nối đường dẫn local repository vào script.

Cũng không nên suy ra “file có timestamp” nghĩa là artifact đã được publish thành **RELEASE**. Một timestamped snapshot vẫn thuộc chính sách snapshot và có thể bị công cụ release/version validation coi là SNAPSHOT.

## 4. maven-metadata.xml có ba cấp: group, artifact và version

Maven repositories có nhiều dạng metadata phục vụ các mục đích khác nhau. Theo phân loại **G/A/V** trong tài liệu Apache Maven:

| Cấp metadata | Vị trí theo layout Maven | Mục đích chính |
| --- | --- | --- |
| **G (groupId)** | `org/example/learning/maven-metadata.xml` | Ánh xạ **plugin prefix → artifactId** cho Maven plugins có liên quan. Không phải nơi tìm timestamp của library snapshot. |
| **A (artifactId)** | `org/example/learning/snapshot-library/maven-metadata.xml` | Liệt kê/khám phá versions của artifact (cả release và snapshot tùy repository): `latest`, `release`, `versions`, `lastUpdated`. |
| **V (version/baseVersion)** | `org/example/learning/snapshot-library/1.0-SNAPSHOT/maven-metadata.xml` | Ánh xạ SNAPSHOT baseVersion thành timestamped artifact, gồm `snapshot` và `snapshotVersions`. |

Đối với chủ đề này, **V-level metadata là quan trọng nhất**. Maven cần nó để giải quyết `1.0-SNAPSHOT` sang file JAR/POM đã deploy.

**Không nhầm hai mục metadata:**

- `<versioning><versions>...` ở **A level** nói repository biết những **version logic** nào, ví dụ `1.0-SNAPSHOT`, `1.0.0`, `1.1-SNAPSHOT`.
- `<versioning><snapshotVersions>...` ở **V level** nói **file mới nhất theo từng extension/classifier** của một baseVersion `1.0-SNAPSHOT` đang trỏ tới version timestamped nào.

Metadata **không phải artifact được khai báo trực tiếp bằng groupId:artifactId:version**; Maven thao tác với chúng để khám phá và resolve artifact. Metadata cùng artifact có thể được repository manager cung cấp/gộp theo cơ chế riêng, không nên tự sửa trực tiếp trên server.

## 5. Đọc một tệp version-level maven-metadata.xml mẫu

Giả sử producer đã deploy bản `1.0-SNAPSHOT` lúc 14:30:25 UTC ngày 10/11/2026 và được đánh số 3. Metadata remote có thể có dạng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <groupId>org.example.learning</groupId>
    <artifactId>snapshot-library</artifactId>
    <version>1.0-SNAPSHOT</version>
    <versioning>
        <snapshot>
            <timestamp>20261110.143025</timestamp>
            <buildNumber>3</buildNumber>
        </snapshot>
        <lastUpdated>20261110143025</lastUpdated>
        <snapshotVersions>
            <snapshotVersion>
                <extension>jar</extension>
                <value>1.0-20261110.143025-3</value>
                <updated>20261110143025</updated>
            </snapshotVersion>
            <snapshotVersion>
                <extension>pom</extension>
                <value>1.0-20261110.143025-3</value>
                <updated>20261110143025</updated>
            </snapshotVersion>
        </snapshotVersions>
    </versioning>
</metadata>
~~~

Đây là **metadata minh họa**, không phải bản tải từ một server thật. Hãy hiểu các phần tử:

- `groupId`, `artifactId` và `version`: tọa độ mà metadata mô tả; `version` vẫn là **baseVersion `1.0-SNAPSHOT`**.
- `<snapshot><timestamp>`: thời điểm snapshot deployment được biểu diễn theo UTC, dạng `yyyyMMdd.HHmmss`.
- `<snapshot><buildNumber>`: build number tăng theo cơ chế deployment metadata, ví dụ `3`.
- `<lastUpdated>` và `<snapshotVersion><updated>`: thời điểm cập nhật metadata, dạng `yyyyMMddHHmmss`, **không có dấu chấm**.
- `snapshotVersions/snapshotVersion/extension`: nhóm artifact theo extension, ví dụ `jar` hoặc `pom`.
- `snapshotVersions/snapshotVersion/classifier`: nếu có, phân biệt artifact đính kèm như `sources`, `javadoc`, `tests`.
- `snapshotVersions/snapshotVersion/value`: **resolved timestamped version**, dùng để tạo tên file tương ứng.

Khi artifact có classifier `sources`, metadata có thể bổ sung:

~~~xml
<snapshotVersion>
    <classifier>sources</classifier>
    <extension>jar</extension>
    <value>1.0-20261110.143025-3</value>
    <updated>20261110143025</updated>
</snapshotVersion>
~~~

Tên file tương ứng thường là:

~~~text
snapshot-library-1.0-20261110.143025-3-sources.jar
~~~

**Metadata không mặc nhiên là lịch sử đầy đủ của mọi bản đã từng deploy.** V-level `snapshotVersions` mô tả mapping snapshot mới nhất **cho từng cặp extension/classifier**; server có thể vẫn giữ nhiều file timestamped cũ, hoặc đã dọn chúng theo retention policy. Không dùng số lượng `snapshotVersion` để đếm toàn bộ các lần deploy.

Ngoài ra, trong một repo bị upload lỗi giữa chừng, các entry cho `jar`, `pom` và `sources.jar` có thể lệch nhau hoặc thiếu. Điều tra phải xem metadata của **đúng repository** và cả file thực tế, không suy chỉ từ `timestamp`/`buildNumber`.

## 6. Vai trò của Maven metadata khi consumer resolve SNAPSHOT

Giả sử `consumer/pom.xml` có:

~~~xml
<dependency>
    <groupId>org.example.learning</groupId>
    <artifactId>snapshot-library</artifactId>
    <version>1.0-SNAPSHOT</version>
</dependency>
~~~

Khi Maven cần dependency, quá trình tổng quát:

~~~text
Consumer cần:
  org.example.learning:snapshot-library:1.0-SNAPSHOT
                     |
                     v
Xác định repository có snapshot enabled
                     |
                     v
Đọc hoặc sử dụng cache V-level maven-metadata.xml
                     |
                     v
Tra snapshotVersions (jar, classifier rỗng)
                     |
                     v
Resolved: 1.0-20261110.143025-3
                     |
                     v
Tải POM/JAR timestamped hợp lệ và dependencies của POM
                     |
                     v
Đưa artifact vào compile/test/runtime classpath theo scope
~~~

Dạng đường dẫn remote có thể là:

~~~text
https://repository.example.invalid/maven-snapshots/
  org/example/learning/snapshot-library/1.0-SNAPSHOT/
    maven-metadata.xml
    snapshot-library-1.0-20261110.143025-3.pom
    snapshot-library-1.0-20261110.143025-3.jar
~~~

URL `example.invalid` chỉ dùng để minh họa đường dẫn; **không phải server tồn tại để tải artifact**. Repository manager có thể hiển thị UI/download URL khác với physical storage layout; quan sát Maven repository endpoint, không suy từ trình quản lý file.

Vì ánh xạ `SNAPSHOT → timestamped version` có thể thay đổi sau lần deploy mới, cùng POM consumer có thể lấy JAR mới vào lần build sau. **Đó là lý do SNAPSHOT không tái lập tuyệt đối chỉ bằng một chuỗi `1.0-SNAPSHOT` trong POM.**

## 7. SNAPSHOT và RELEASE: tính ổn định khác nhau ra sao?

| Tiêu chí | `1.0-SNAPSHOT` | `1.0.0` (RELEASE) |
| --- | --- | --- |
| Mục đích | Tích hợp/kiểm thử phiên bản đang phát triển. | Bản phát hành được định danh ổn định. |
| Có thể deploy nhiều lần cùng version logic? | Thường có, mỗi deploy remote tạo bản timestamped mới nếu repository hỗ trợ. | Nên bất biến; repository manager thường ngăn redeploy release theo policy. |
| Filename remote | Thường mang timestamp + buildNumber. | Thường giữ version thường như `artifact-1.0.0.jar`. |
| Metadata version-level | V-level metadata của snapshot dùng cho timestamp mapping. | Không dùng V-level snapshot metadata theo cùng cơ chế. |
| Resolver update | Có thể kiểm tra bản mới theo `updatePolicy` và `-U`. | Không phải moving target theo cùng kiểu; version release cố định cần được giữ bất biến. |
| Dùng trong release pipeline | Nên tránh cho artifact cần tái lập/chứng nhận. | Ưu tiên release version đã kiểm thử, có checksum/provenance phù hợp. |

**Một timestamped SNAPSHOT không tự trở thành RELEASE.** Tọa độ được consumer resolve vẫn liên quan đến snapshot version, nên build promotion/release tooling có thể từ chối dự án còn phụ thuộc SNAPSHOT, kể cả khi bạn ghi version dạng timestamped vào dependency.

**RELEASE không có nghĩa tuyệt đối an toàn** nếu repository cho overwrite artifact, dùng version ranges hay build không pin plugin/JDK. Nhưng một release repository có chính sách **immutable artifacts** giúp tái lập và truy vết đáng tin cậy hơn so với `-SNAPSHOT`.

## 8. maven install, deploy và snapshot repository: khác nhau

Ba lệnh này phục vụ mục đích khác nhau:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp clean install
mvn -B -ntp clean deploy
~~~

- `package`: tạo JAR/POM output trong thư mục `target/` (và các artifact liên quan theo plugin).
- `install`: thực hiện các phase tới `install` và cài artifact vào **local Maven repository** của máy hiện tại. Nó **không upload** cho các máy khác.
- `deploy`: thực hiện phase tới `deploy`, dùng Maven Deploy Plugin để **upload lên remote repository** đã cấu hình; thường cần quyền ghi, endpoint hợp lệ và credentials nếu repository bảo vệ.

Với cùng project version `1.0-SNAPSHOT`:

~~~text
mvn install:
  local Maven repository
  .../snapshot-library/1.0-SNAPSHOT/
      snapshot-library-1.0-SNAPSHOT.jar   (thường là local install)
      snapshot-library-1.0-SNAPSHOT.pom

mvn deploy:
  remote snapshot repository
  .../snapshot-library/1.0-SNAPSHOT/
      snapshot-library-1.0-20261110.143025-3.jar
      snapshot-library-1.0-20261110.143025-3.pom
      maven-metadata.xml
~~~

Bảng đường dẫn là **minh họa cho layout thông dụng**; không cam kết tất cả resolver versions/local repository settings đều đặt file giống hệt. Official Maven Resolver phân biệt locally installed (base version) với remotely cached timestamped snapshots.

Nếu người A chạy `mvn install` trên laptop, người B **không tự nhận** JAR đó. Muốn chia sẻ giữa developer/CI, cần deploy vào snapshot remote mà consumer có quyền đọc và được cấu hình resolve.

## 9. Cấu hình distributionManagement để deploy SNAPSHOT

Thông thường POM producer có `distributionManagement`:

~~~xml
<distributionManagement>
    <repository>
        <id>training-releases</id>
        <url>https://repository.example.invalid/maven-releases</url>
    </repository>
    <snapshotRepository>
        <id>training-snapshots</id>
        <url>https://repository.example.invalid/maven-snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Đây là **mảnh trong `<project>`**, dùng URL `example.invalid` như một nơi giữ chỗ minh họa, **không phải endpoint có thể deploy thật**. Trên hệ thống thực tế, dùng URL do nhóm vận hành repository cấp.

- `<repository>` trong `distributionManagement` là nơi deploy **release**.
- `<snapshotRepository>` là nơi deploy **snapshot** khi được cấu hình.
- `<id>` gắn với `<server><id>` tương ứng ở Maven `settings.xml` khi cần xác thực.
- **Không đưa mật khẩu/token vào POM được commit**. Dùng settings/secret manager hoặc cơ chế auth do tổ chức cho phép.
- Nếu không khai báo `snapshotRepository`, Deploy Plugin có thể sử dụng `repository` theo quy tắc deployment; tuy nhiên server đích có thể từ chối SNAPSHOT. Nên tách rõ release/snapshot repositories.

Ví dụ cấu trúc credentials **chỉ minh họa id**:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>training-snapshots</id>
        </server>
    </servers>
</settings>
~~~

Tệp trên chỉ thể hiện **cơ chế match ID**, chưa có auth thật và **không đủ để truy cập repository yêu cầu xác thực**. Maven đọc settings user thường ở `~/.m2/settings.xml` (trên Windows trong thư mục người dùng tương ứng) hoặc settings được CI cung cấp. Không lưu secret trực tiếp trong bài học, POM hay log.

Với repository đã được cấu hình hợp lệ, lệnh:

~~~bash
mvn -B -ntp clean deploy
~~~

có thể tạo snapshot timestamped remote và cập nhật metadata. **Đừng chạy lệnh deploy này trên repository thực tế nếu chưa có quyền/phân công phát hành**, vì deploy là hành động ghi mới lên server; các hướng dẫn sau dùng local install để thực hành an toàn.

Một vài repository manager có retention/cleanup hoặc staged deployment riêng. Có thể artifact mới được upload thành công nhưng metadata/index không đồng bộ ngay do server policy hoặc cache trung gian; giải quyết bằng đối chiếu log và server thực tế, không tự sửa metadata thủ công.

## 10. Consumer cần cấu hình repository hỗ trợ SNAPSHOT

Nếu consumer phụ thuộc `1.0-SNAPSHOT` từ một remote repository riêng, dependency declaration thôi **chưa đủ** nếu Maven chưa biết repository hoặc snapshot bị tắt.

Ví dụ mảnh POM **consumer**:

~~~xml
<repositories>
    <repository>
        <id>training-snapshots</id>
        <url>https://repository.example.invalid/maven-snapshots</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
        </snapshots>
    </repository>
</repositories>
~~~

Đây là mẫu riêng cho **đọc artifact**, khác `distributionManagement` dùng khi **deploy artifact**:

| Cấu hình | Vai trò |
| --- | --- |
| `repositories/repository` | Định nghĩa nơi Maven **tải** project dependencies. |
| `pluginRepositories/pluginRepository` | Định nghĩa nơi Maven **tải Maven plugins** khi cần. |
| `distributionManagement/snapshotRepository` | Định nghĩa nơi Maven **upload** SNAPSHOT khi deploy. |
| `settings.xml/servers/server` | Xác thực dựa trên `id` repository/server tương ứng. |
| `settings.xml/mirrors` | Có thể chuyển hướng requests qua repository manager/mirror, cần xét cấu hình thực tế. |

Không mặc định Maven Central là nơi publish snapshot nội bộ; Maven Central thường phục vụ releases và không phải remote SNAPSHOT repository của dự án bạn.

Nếu repository có địa chỉ dùng trong một tổ chức, có thể cấu hình repository/mirror trong `settings.xml` hoặc parent/company build settings thay vì copy URL vào mọi POM. Tránh thêm repository bên ngoài tùy tiện; nó ảnh hưởng **nguồn tin cậy của dependency** và chính sách supply-chain.

## 11. updatePolicy, -U, cache và vì sao build không thấy bản SNAPSHOT mới

Snapshot remote là moving target, nhưng Maven không nhất thiết gọi mạng ở mỗi lần build. Repository policy quyết định nhịp kiểm tra.

Trong `<repository><snapshots>` có thể đặt:

~~~xml
<snapshots>
    <enabled>true</enabled>
    <updatePolicy>daily</updatePolicy>
    <checksumPolicy>fail</checksumPolicy>
</snapshots>
~~~

Các giá trị `updatePolicy` thông dụng:

| Giá trị | Ý nghĩa |
| --- | --- |
| `always` | Cố kiểm tra cập nhật từ remote mỗi lần phù hợp. |
| `daily` | Kiểm tra cập nhật theo nhịp mỗi ngày, là giá trị mặc định thường dùng. |
| `interval:30` | Kiểm tra lại sau khoảng 30 phút kể từ lần kiểm tra phù hợp trước đó. |
| `never` | Không chủ động làm mới remote snapshot nếu đã có bản phù hợp ở local (theo policy/resolver). |

Cần phân biệt **“kiểm tra có bản mới không”** với **“luôn tải lại JAR”**. Maven có thể dùng metadata/cache và chỉ download khi resolved version thay đổi; proxy/repository manager có thêm tầng cache riêng.

Tùy chọn dòng lệnh hữu ích cho Maven 3:

~~~bash
mvn -U -B -ntp clean verify
~~~

`-U` yêu cầu Maven **buộc kiểm tra bản SNAPSHOT mới hơn** từ remote (và theo bản Maven có thể liên quan cập nhật metadata/chính sách của artifact bị thiếu). Nó không tự sửa repo URL, credentials, DNS, policy server hoặc tương thích binary. Nếu metadata remote vẫn trỏ bản cũ, chạy `-U` không biến một bản snapshot mới thành hiện có.

Ngược lại:

~~~bash
mvn -o -B -ntp clean verify
~~~

`-o` là chế độ **offline**: Maven chỉ dùng những artifact, plugin và metadata đã có phù hợp tại local repository; không thể phát hiện một bản SNAPSHOT vừa được deploy từ server trong phiên offline.

Các tình huống thường gặp:

1. **Producer chỉ chạy `install`:** bản mới nằm trên máy producer, người khác không có. Giải pháp là deploy remote hoặc share bằng cơ chế artifact chuẩn.
2. **Producer deploy remote nhưng consumer chưa làm mới metadata:** thử `-U` khi đúng repository và quyền đọc đã sẵn có.
3. **Consumer dùng mirror khác:** metadata mà consumer thấy có thể chưa phải metadata ở repository producer vừa deploy.
4. **Repository server đã dọn bản timestamped:** metadata/cached metadata có thể trỏ file không còn; cần kiểm tra repository manager và policy.
5. **Local cache chứa bản tự install:** Maven có thể sử dụng artifact local thay vì remote version bạn mong đợi; cách debug là phân biệt locally installed vs remotely cached.
6. **Consumer offline:** không thể lấy phiên bản timestamped mới. Đây là dự kiến, không phải lỗi Maven metadata.

Không nên xóa toàn bộ `~/.m2/repository` để chữa mọi lỗi; cách đó làm mất cache, tăng thời gian build và có thể gây lỗi mới khi offline. Điều tra chính xác tọa độ/repository trước.

## 12. Ví dụ chạy được với Java 17: một producer SNAPSHOT và một consumer

Ví dụ này minh họa **local SNAPSHOT development an toàn**: chạy `mvn install` trên máy và consumer build bằng version `1.0-SNAPSHOT`. Không cần repository remote để hoàn tất phần thực hành. Sau đó giải thích rõ điều gì **thay đổi** khi chuyển sang remote deploy.

Tạo **hai project độc lập**, ở các thư mục cạnh nhau:

~~~text
snapshot-practice/
├── snapshot-library/
│   ├── pom.xml
│   └── src/main/java/org/example/snapshot/Greeting.java
└── snapshot-consumer/
    ├── pom.xml
    └── src/main/java/org/example/consumer/Main.java
~~~

Yêu cầu: JDK 17+, Maven 3.9.x tương thích và khả năng tải Maven plugins cần thiết nếu local repository chưa cache. Các tọa độ `org.example.learning` là ví dụ cục bộ, **không khẳng định tồn tại trên Maven Central**.

### 12.1. Producer POM: snapshot-library/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.learning</groupId>
    <artifactId>snapshot-library</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là POM hoàn chỉnh, **không có `distributionManagement`**, bởi phần thực hành không deploy remote. `maven.compiler.release=17` giúp biên dịch đúng release Java 17 khi JDK hỗ trợ.

### 12.2. Producer Java source

Tệp `snapshot-library/src/main/java/org/example/snapshot/Greeting.java`:

~~~java
package org.example.snapshot;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from SNAPSHOT v1";
    }
}
~~~

Mã chỉ dùng Java standard library; không có dependency bên ngoài.

### 12.3. Consumer POM: snapshot-consumer/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.learning</groupId>
    <artifactId>snapshot-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.example.learning</groupId>
            <artifactId>snapshot-library</artifactId>
            <version>1.0-SNAPSHOT</version>
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
~~~

Consumer cố tình dùng **version SNAPSHOT** của producer. Với phần thực hành local, không cần `<repositories>` remote vì producer sẽ được install vào cùng local Maven repository.

### 12.4. Consumer Java source

Tệp `snapshot-consumer/src/main/java/org/example/consumer/Main.java`:

~~~java
package org.example.consumer;

import org.example.snapshot.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Consumer import trực tiếp `Greeting` từ artifact producer, nên đã khai báo dependency ở `snapshot-consumer/pom.xml`.

### 12.5. Build ở máy local, không cần remote repository riêng

Ở terminal thứ nhất, vào thư mục `snapshot-practice/snapshot-library`:

~~~bash
mvn -B -ntp clean install
~~~

Maven tạo JAR rồi install `snapshot-library:1.0-SNAPSHOT` vào local repository. Không có timestamped remote deployment vì **chưa chạy `deploy`**.

Sau đó vào `snapshot-practice/snapshot-consumer`:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
java -cp "target/classes:target/dependency/*" org.example.consumer.Main
~~~

Những dòng trên dành cho **Bash/Zsh** ở Linux/macOS. Trên **Windows PowerShell/CMD**, dùng lệnh chạy Java tương ứng:

~~~text
java -cp "target\classes;target\dependency\*" org.example.consumer.Main
~~~

**Stdout chính xác của riêng lệnh `java`**:

~~~text
Hello from SNAPSHOT v1
~~~

Không lẫn đoạn stdout của app với log `mvn`; Maven có thể in nhiều dòng từ Compiler/Resources/JAR/Install plugins và tải plugin lần đầu.

### 12.6. Chứng minh SNAPSHOT là một tên có thể được cập nhật

Sửa **chính một dòng** trong producer `Greeting.java`:

~~~java
return "Hello from SNAPSHOT v2";
~~~

Đây là **dòng thay thế trong method `message()`**, không phải một class Java riêng để copy độc lập.

Trong thư mục producer:

~~~bash
mvn -B -ntp clean install
~~~

Sau đó quay sang consumer và build/copy lại:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
java -cp "target/classes:target/dependency/*" org.example.consumer.Main
~~~

Stdout của riêng lệnh `java` khi copy dependency mới thành công:

~~~text
Hello from SNAPSHOT v2
~~~

Cả hai lần consumer đều khai báo `1.0-SNAPSHOT`, nhưng binary trong local repository đã được `install` lại. **Đây là minh họa sự thay đổi nội dung theo cùng baseVersion**, không phải demo về timestamped deploy. Timestamped filenames và V-level remote metadata chỉ xuất hiện ở kịch bản deploy từ phần 2–6.

Nếu ở máy consumer khác, việc producer chỉ `install` sẽ **không làm consumer đó nhận v2**. Cần đưa producer vào remote repository phù hợp, sau đó consumer kiểm tra metadata remote theo repository policy.

## 13. Mở rộng demo sang remote deploy có timestamp: các bước khái niệm

Sau khi nắm phần thực hành local, có thể xây dựng quy trình snapshot remote trên hệ thống repository manager **do tổ chức kiểm soát**:

1. Producer có POM version `1.0-SNAPSHOT`.
2. POM producer hoặc parent khai báo `distributionManagement/snapshotRepository` trỏ tới endpoint được cấp.
3. CI có cấu hình `settings.xml` với `server/id` khớp và quyền upload riêng.
4. Chạy `mvn clean verify` trên đúng JDK/Maven; kiểm tra unit/integration tests.
5. Ở job được phép publish, chạy `mvn deploy`. Maven Deploy Plugin tải metadata remote cần thiết, tính timestamp/buildNumber, upload POM/JAR/attached artifacts và metadata tương ứng.
6. Trên repository manager, quan sát thư mục `1.0-SNAPSHOT` với file version timestamped; không suy tên file chỉ từ local target output.
7. Consumer khai báo `1.0-SNAPSHOT` và có repository **snapshots enabled**.
8. Consumer chạy theo update policy hoặc `mvn -U ...` khi cần kiểm tra bản mới.
9. Đối chiếu resolved artifact version/checksum và test consumer, thay vì chỉ đọc version logic trong POM.

Đối với CI release, nên có một bước **promote thành release version riêng** sau khi kiểm thử, thay vì coi tên timestamped snapshot là release chính thức. Việc publish artefact release mới cần quy trình phê duyệt/bảo mật và repository policy tương ứng.

**Không dùng lệnh `mvn deploy` của phần này với URL `example.invalid`**: URL chỉ minh họa và không tồn tại. Không sửa hoặc upload lên repository công ty khi chưa có xác nhận quyền và endpoint thực.

## 14. Snapshot attached artifacts: sources, javadoc và classifier

Một Maven project có thể đính kèm các artifact khác ngoài JAR chính, ví dụ:

~~~text
Main JAR:      snapshot-library-1.0-20261110.143025-3.jar
POM:           snapshot-library-1.0-20261110.143025-3.pom
Sources JAR:   snapshot-library-1.0-20261110.143025-3-sources.jar
Javadoc JAR:   snapshot-library-1.0-20261110.143025-3-javadoc.jar
Tests JAR:     snapshot-library-1.0-20261110.143025-3-tests.jar
~~~

Chỉ những artifact thực sự được tạo và attach bởi Maven plugins tương ứng mới được deploy; không phải mọi SNAPSHOT tự có sources/javadoc/tests JAR.

Metadata `snapshotVersions` có thể ghi **mỗi cặp extension/classifier** một entry riêng, chẳng hạn:

| Extension | Classifier | Ý nghĩa |
| --- | --- | --- |
| `jar` | rỗng | JAR chính. |
| `pom` | rỗng | POM artifact. |
| `jar` | `sources` | Source JAR. |
| `jar` | `javadoc` | Javadoc JAR. |
| `jar` | `tests` | JAR chứa test classes nếu được cấu hình tạo. |

Nếu một consumer yêu cầu `classifier=sources` mà metadata không có entry tương ứng, nó có thể không tải được sources JAR dù main JAR resolve bình thường. Kiểm tra **classifier, extension, metadata và file upload** chứ không chỉ `snapshot.timestamp`.

Khi một build tạo nhiều attached artifacts trong cùng deployment session, Maven thường dùng timestamp của session để nhất quán mapping, nhưng metadata cuối cùng có thể ghi các entry khác nhau do attached artifact được cập nhật riêng ở các lượt deploy khác nhau. Đừng tự giả định chỉ cần buildNumber là suy ra mọi file classifier luôn tồn tại.

## 15. Kiểm tra repository metadata đúng cách

Các nơi cần kiểm tra, với tọa độ `org.example.learning:snapshot-library:1.0-SNAPSHOT`:

~~~text
Remote (khái niệm):
  /org/example/learning/snapshot-library/
    maven-metadata.xml                        # A level
    /1.0-SNAPSHOT/
      maven-metadata.xml                      # V level
      snapshot-library-1.0-<timestamp>-<n>.jar
      snapshot-library-1.0-<timestamp>-<n>.pom

Local repository (biểu diễn thường thấy):
  ~/.m2/repository/org/example/learning/snapshot-library/1.0-SNAPSHOT/
    maven-metadata-<repository-id>.xml        # metadata cache từ remote
    maven-metadata-local.xml                  # metadata local/install nếu có
    *.jar, *.pom                              # tên thực tế tùy nguồn/cách cache
~~~

**Không hard-code mẫu trên làm đường dẫn tuyệt đối cho chương trình sản xuất**. Nên dùng Maven/Resolver API hoặc plugin chính thức để resolve. Cấu hình `-Dmaven.repo.local=...` có thể đổi local repository, và môi trường CI thường dùng cache khác.

Để tìm nguyên nhân snapshot không cập nhật, nên ghi nhận:

- GroupId/artifactId/baseVersion chính xác.
- Repository id và URL mà Maven thực sự sử dụng (có mirror không?).
- Chính sách `snapshots/enabled` và `updatePolicy`.
- V-level metadata của repository đó, đặc biệt `snapshotVersions` cho extension/classifier đang cần.
- Filename/checksum của JAR/POM resolved; file có thực sự tồn tại trên server không?
- Local cache hoặc bản tự install có trùng baseVersion và được chọn không?
- Maven/JDK/plugin versions và timestamp của log build (không chứa bí mật).

Không lấy file metadata của repository **khác** để giải thích một dependency đang được giải quyết từ mirror/virtual repository hiện tại; proxy có thể có cache hoặc metadata đã trộn khác nguồn.

## 16. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý phù hợp |
| --- | --- | --- |
| Consumer dùng `1.0-SNAPSHOT` nhưng không tải được. | Chưa cấu hình snapshot repository hoặc snapshots bị disable. | Kiểm tra `repositories`, `settings.xml`, mirror, `enabled` và endpoint. |
| Máy A có bản mới nhưng máy B vẫn dùng bản cũ. | A chỉ `install` local, chưa deploy remote. | Deploy trong quy trình được phép hoặc dùng artifact sharing chính thức. |
| Đã deploy nhưng consumer vẫn dùng bản trước. | Metadata cache/update policy hoặc proxy chưa refresh. | Kiểm tra `maven-metadata.xml` của repo đang sử dụng, thử `-U` khi hợp lý. |
| `mvn -U` vẫn không thấy snapshot mới. | Repository sai, server chưa có bản mới, quyền/metadata lỗi, CI mirror stale. | So URL/id, remote metadata, credentials và resolved filename. |
| `-o` không tải bản mới. | Offline không dùng remote. | Dùng online khi cần cập nhật và đảm bảo repository khả dụng. |
| Repo có JAR timestamped nhưng Maven báo không resolve POM. | POM upload thiếu, metadata cho `pom` không đúng, lỗi deploy/retention. | Kiểm tra cả `jar` và `pom` snapshotVersions và file thực tế. |
| Metadata trỏ một JAR đã bị xóa. | Cleanup/retention không đồng bộ với metadata hoặc proxy cache stale. | Điều tra repository manager, không tự sửa metadata bằng tay. |
| Tưởng `buildNumber=3` là CI build #3. | Nhầm metadata snapshot counter với CI pipeline number. | Ghi Git SHA/CI run ID vào build provenance riêng. |
| Thấy nhiều file timestamped nhưng chỉ một snapshotVersion jar. | Metadata mô tả mapping mới nhất theo extension/classifier, không phải toàn lịch sử. | Xem danh sách artifact trên repository manager riêng. |
| Local file là `*-SNAPSHOT.jar` còn remote là `*-timestamp-n.jar`. | `install` và remote deploy/caching có cơ chế naming khác. | Phân biệt baseVersion, resolved version, nguồn artifact. |
| Consumer vẫn đọc bytecode cũ dù project POM không đổi. | `1.0-SNAPSHOT` là moving target; chưa cập nhật/copy lại runtime dependency. | Rebuild consumer và xác minh classpath/runtime JAR đang chạy. |
| `java -cp target/classes ...` thiếu class từ producer. | JVM không tự đọc POM và thiếu dependency JAR ở runtime. | Dùng `copy-dependencies` hoặc launcher có classpath phù hợp. |
| Deploy bị HTTP 401/403. | Server id/credentials/quyền upload không đúng. | So `distributionManagement/id` với `settings.xml/servers/id`, xử lý qua admin. |
| Deploy bị từ chối SNAPSHOT tại release repo. | Repo policy chỉ nhận release. | Dùng `snapshotRepository`/endpoint được cấp. |
| Dùng SNAPSHOT trong release build gây lỗi policy. | Release tooling cấm snapshot dependency hoặc artifact chưa đạt điều kiện release. | Đổi sang release version hợp lệ, không che lỗi bằng timestamp file name. |
| Đã chuyển sang release nhưng build vẫn không tái lập. | Plugin/JDK/version ranges, repository mutable, environment khác nhau. | Pin build tool/plugins, kiểm checksum/provenance, kiểm soát repo policy. |

**Thứ tự debug hiệu quả:** xác định đang nói về **producer hay consumer** → **install local hay deploy remote** → **đúng baseVersion/repository id chưa** → **V-level metadata ánh xạ đến file nào** → **artifact/checksum có tồn tại không** → **consumer updatePolicy/cache** → **chạy lại build/test/runtime**.

## 17. Checklist phát hành SNAPSHOT và quản lý CI an toàn

- [ ] Producer khai báo version có hậu tố `-SNAPSHOT` khi thực sự phát triển snapshot.
- [ ] Đã xác định snapshot repository được phép ghi và release repository tách biệt.
- [ ] `distributionManagement/snapshotRepository/id` khớp server credentials ở `settings.xml` nếu cần.
- [ ] Không commit username/password/token vào POM hay pipeline logs.
- [ ] Producer chạy `verify`/tests thích hợp trước khi publish.
- [ ] CI pin JDK/Maven/plugin versions cần thiết; dùng Maven Wrapper khi dự án có.
- [ ] Lưu **Git commit SHA**, CI job/run id, SBOM/checksum và thông tin nguồn build riêng; timestamp snapshot **không** thay cho provenance.
- [ ] Nếu deployment thành công, đã xác minh V-level metadata và JAR/POM timestamped thực sự tồn tại.
- [ ] Nếu có attached artifacts, đã kiểm tra extension/classifier riêng.
- [ ] Consumer có snapshot repository đúng, snapshot enabled, update policy phù hợp với nhu cầu.
- [ ] Consumer không dựa vào `-SNAPSHOT` như artifact bất biến cho release cần chứng nhận.
- [ ] CI cache `~/.m2` được quản lý có chủ đích; khi điều tra stale snapshots cần xem cache/metadata.
- [ ] Repository manager có retention/cleanup policy hợp lý, không làm metadata trỏ file bị dọn.
- [ ] Không xóa local repository toàn bộ theo thói quen; điều tra đúng tọa độ và nguồn.
- [ ] Khi cần bản phát hành ổn định, chuyển sang release version theo quy trình riêng và kiểm tra dependency graph.

## 18. Bài tập tự kiểm tra

1. **Producer khai báo `1.0-SNAPSHOT`, remote JAR là `1.0-20261110.143025-3.jar`. Consumer nên viết version nào để dùng cơ chế snapshot tự cập nhật?**  
   Thường vẫn viết `1.0-SNAPSHOT`; Maven dùng V-level metadata để chọn timestamped artifact phù hợp.

2. **Tại sao trong remote directory vẫn có tên `1.0-SNAPSHOT` dù file bên trong mang timestamp?**  
   Directory được tổ chức theo baseVersion; filename của snapshot deployment cụ thể mang resolved version.

3. **Khác nhau giữa metadata cấp A và cấp V?**  
   A-level liệt kê/khám phá các version của artifact; V-level ánh xạ một baseVersion SNAPSHOT sang các file timestamped theo extension/classifier.

4. **`snapshotVersions` có phải lịch sử đầy đủ mọi lượt deploy không?**  
   Không. Nó mô tả mapping snapshot mới nhất cho từng cặp extension/classifier phù hợp.

5. **`mvn install` có tạo remote timestamped artifact cho người khác tải không?**  
   Không. Install ghi vào local repository; deploy mới upload remote (khi cấu hình và quyền cho phép).

6. **Vì sao `-U` không khắc phục được mọi lỗi snapshot?**  
   Nó yêu cầu kiểm tra cập nhật, nhưng không tạo artifact chưa deploy, không sửa repository URL, credentials, metadata hỏng hoặc proxy không đồng bộ.

7. **Một tên file có timestamp có phải release đã bất biến?**  
   Không. Timestamped snapshot vẫn là snapshot; release có version/policy riêng.

8. **Tại sao `20261110.143025` khác `20261110143025`?**  
   Giá trị `snapshot/timestamp` có dấu chấm giữa ngày và giờ; `updated`/`lastUpdated` dùng dạng liền không dấu chấm.

9. **Vì sao sources JAR có classifier khác với main JAR?**  
   Metadata phân biệt file theo extension/classifier; nguồn được attach riêng khi plugin cấu hình tạo, không phải output bắt buộc.

10. **Nếu cùng baseVersion `1.0-SNAPSHOT` chứa mã mới hôm nay, một pipeline release có tự tái lập binary hôm qua?**  
    Không được bảo đảm. Cần dùng release bất biến hoặc cơ chế chốt đúng artifact/provenance theo chính sách tổ chức.

## 19. Tài liệu tham khảo Apache Maven

- [Maven Remote Repositories](https://maven.apache.org/repositories/remote.html): giải thích `SNAPSHOT → timestamp/build number` khi deploy và ánh xạ khi consumer resolve.
- [Maven Metadata](https://maven.apache.org/repositories/metadata.html): phân loại G, A, V và vai trò của version-level metadata.
- [Maven Repository Metadata Model](https://maven.apache.org/ref/3-LATEST/maven-repository-metadata/): schema, `snapshot`, `snapshotVersions`, local/remote metadata filenames.
- [Maven Repository Metadata 3.9.2 Model](https://maven.apache.org/ref/3.9.2/maven-repository-metadata/repository-metadata.html): định nghĩa chi tiết `timestamp`, `buildNumber`, `snapshotVersion/value`, `updated`.
- [Maven Local Repositories](https://maven.apache.org/repositories/local.html): phân biệt local install và remote cache, `baseVersion` và timestamped version.
- [Maven Settings Reference](https://maven.apache.org/settings.html): policies `snapshots/enabled`, `updatePolicy`, `checksumPolicy`, `servers` và `mirrors`.
- [Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin-4.x/usage.html): `distributionManagement`, `snapshotRepository` và repository credentials.
- [Maven Deployment Guide](https://maven.apache.org/guides/mini/guide-deployment-transports.html): repository ids và `settings.xml`.
- [Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): chuẩn bị JAR runtime trong bài thực hành.

**Ghi nhớ:** `-SNAPSHOT` là version logic **có thể đổi nội dung**; remote repository thường lưu các **artifact mang timestamp + build number** và dùng **V-level `maven-metadata.xml`** để chỉ tới file phù hợp. `mvn install` là việc cục bộ, `mvn deploy` là việc công bố remote, còn `updatePolicy`/`-U` ảnh hưởng thời điểm consumer kiểm tra bản mới. Khi cần release tái lập, đừng coi SNAPSHOT là artifact bất biến.
