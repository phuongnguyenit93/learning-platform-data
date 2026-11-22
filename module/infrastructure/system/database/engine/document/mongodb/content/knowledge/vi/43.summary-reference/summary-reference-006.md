# Cách tìm tài liệu chính thức, release note và ma trận tương thích MongoDB

Khi một lệnh MongoDB chạy trên máy phát triển nhưng lỗi ở production, nguyên nhân không nhất thiết nằm ở cú pháp. Hai môi trường có thể khác **phiên bản MongoDB Server**, **featureCompatibilityVersion (FCV)**, loại triển khai **Atlas hay self-managed**, phiên bản **driver**, phiên bản **Java/Node.js/Python**, lớp tích hợp **Spring Data**, topology **standalone/replica set/sharded cluster**, hoặc chỉ khác bản vá chứa một thay đổi hành vi. Một bài blog có thể đúng vào thời điểm viết nhưng không còn đúng với phiên bản phần mềm đang chạy.

Ví dụ, một project dùng MongoDB Java Sync Driver kết nối MongoDB Server không chỉ cần biết API `MongoCollection.updateOne()`. Nó còn phải kiểm tra bản driver đó tương thích với **server đang chạy**, yêu cầu **JDK** nào, Spring Data đang quản lý driver qua BOM nào, tính năng cần dùng có được phát hành ở server/Atlas tier này chưa, và liệu release note có cảnh báo breaking change hoặc security advisory nào không.

Đây là bài tổng kết và tra cứu của module **Database Engine Document MongoDB**, tập trung vào **cách tìm và kiểm chứng tài liệu chính thức**, **đọc release notes/changelog** và **lập ma trận tương thích có bằng chứng** để học tập, sửa lỗi và lập kế hoạch nâng cấp. Những phiên bản được nhắc tới là **ví dụ kiểm tra tại ngày 14/11/2026**, không phải lời khẳng định rằng các phiên bản đó luôn mới nhất về sau. Bảng tương thích và vòng đời phần mềm thay đổi theo thời gian; **luôn mở lại tài liệu chính thức vào ngày quyết định triển khai**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt tài liệu sản phẩm chính thức với blog, snippet, community post và tài liệu legacy.
2. Đi đúng nhánh tài liệu cho Server, Atlas, Compass, mongosh, drivers và Spring Data.
3. Cố định version tài liệu trước khi sao chép lệnh hoặc dùng một tính năng.
4. Tìm release notes của một **major/minor/patch** và hiểu nội dung chính.
5. Phân biệt release notes, changelog, migration/upgrade guide, compatibility table, API reference và issue tracker.
6. Tra tương thích **MongoDB Server ↔ driver ↔ language runtime ↔ framework**.
7. Diễn giải chính xác dấu “fully compatible”, “partially compatible”, “not compatible” và “untested”.
8. Phân biệt **supported**, **tested**, **works in a lab** và **available in Atlas/self-managed**.
9. Tra vòng đời EOL, security bulletin, critical advisory và quyền hỗ trợ.
10. Lấy version Server, FCV, mongosh, driver, JDK/Node.js và Spring Data từ môi trường thật.
11. Hiểu rằng nâng cấp binary và tăng FCV là hai quyết định khác nhau.
12. Đánh giá Stable API, FCV, feature flags và giới hạn deployment khi chọn một tính năng.
13. Xây bảng compatibility có URL, ngày xác minh, bằng chứng và trạng thái GO/NO-GO.
14. Lập kế hoạch thử nghiệm, rollback và audit trước khi nâng cấp production.
15. Tra cứu nhanh mà không nhầm tài liệu ở nhánh `current` với tài liệu đúng phiên bản đang dùng.

## 2. Quy tắc nền tảng: luôn xác định năm thông tin

Trước khi tìm một hướng dẫn MongoDB, điền:

| Câu hỏi | Ví dụ |
|---|---|
| **Sản phẩm nào?** | MongoDB Server, Atlas, Java Driver, mongosh, Compass |
| **Phiên bản nào?** | Server 8.0.x, Java driver 5.x, Spring Data 4.x |
| **Triển khai ở đâu?** | Atlas dedicated, Atlas auto-upgrade, Enterprise/Community self-managed |
| **Đang chạy kiểu gì?** | Standalone, replica set, sharded cluster; JDK 17 |
| **Mục tiêu là gì?** | Sửa lỗi kết nối, dùng transaction, nâng driver, kiểm tra CVE |

Ví dụ cụ thể hơn:

~~~text
Product: MongoDB Server Community
Deployment: self-managed replica set, Linux x86_64
Server binaries: 8.0.x (ghi patch chính xác)
FCV: 8.0
Application: Java 17 + Spring Data MongoDB
Driver: mongodb-driver-sync 5.x (ghi patch chính xác)
Question: Có thể nâng server/driver mà vẫn dùng transactions không?
~~~

Không trả lời bằng “MongoDB có hỗ trợ không?” khi chưa biết **MongoDB nào, phiên bản nào và trên topology nào**.

## 3. Sơ đồ các nguồn tài liệu nên mở

~~~mermaid
flowchart TD
    Q["Cần tra một thông tin MongoDB"] --> Product{"Liên quan thành phần nào?"}
    Product -->|"Server command/behavior"| Manual["MongoDB Server Manual"]
    Product -->|"Managed cluster/API"| Atlas["Atlas Documentation"]
    Product -->|"Java/Node/Python driver"| Drivers["Official Driver Docs"]
    Product -->|"Spring Data"| Spring["Spring Data MongoDB Reference"]
    Product -->|"mongosh/GUI"| Tools["mongosh / Compass Docs"]
    Manual --> Version{"Chọn đúng version"}
    Atlas --> Version
    Drivers --> Version
    Spring --> Version
    Tools --> Version
    Version --> Evidence["Reference + Release Notes + Compatibility + Tests"]
~~~

### 3.1. Danh bạ các cửa vào chính thức

| Nhu cầu | Trang khởi đầu |
|---|---|
| MongoDB Server Manual | [MongoDB Database Manual](https://www.mongodb.com/docs/manual/) |
| Server release notes | [Server Release Notes](https://www.mongodb.com/docs/manual/release-notes/) |
| Cách đặt phiên bản và upgrade paths | [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) |
| FCV command | [setFeatureCompatibilityVersion](https://www.mongodb.com/docs/manual/reference/command/setfeaturecompatibilityversion/) |
| Client library compatibility | [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/) |
| MongoDB Java Sync Driver | [Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) |
| Java driver release notes | [Java Sync Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/) |
| Java driver migration/breaking changes | [Upgrade Driver Versions](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/) |
| PyMongo documentation | [PyMongo Driver](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/) |
| Spring Data MongoDB requirements | [Spring Data MongoDB Requirements](https://docs.spring.io/spring-data/mongodb/reference/preface.html) |
| Atlas docs | [MongoDB Atlas](https://www.mongodb.com/docs/atlas/) |
| Atlas change logs | [Atlas Release Notes](https://www.mongodb.com/docs/atlas/release-notes/) |
| Atlas version policy | [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/) |
| Compass release notes | [Compass Release Notes](https://www.mongodb.com/docs/compass/release-notes/) |
| Vòng đời phần mềm | [MongoDB Software Lifecycle Schedules](https://www.mongodb.com/legal/support-policy/lifecycles) |
| Chính sách hỗ trợ | [MongoDB Software Support Policy](https://www.mongodb.com/legal/support-policy/software) |

Trang Docs có thể đổi menu, URL hoặc cấu trúc. Các liên kết trên là **điểm bắt đầu tra cứu**; kiểm tra breadcrumb, version selector và URL thực tế khi sử dụng. Với Spring Data, nhà cung cấp tham chiếu chính là Spring, không phải mọi ví dụ được đăng trên blog MongoDB đều thay thế reference của Spring.

### 3.2. Tài liệu API và tài liệu hành vi

Tài liệu Server Manual mô tả lệnh, stages, options và semantics của server. Driver docs mô tả cách **gọi qua thư viện của ngôn ngữ**. API/Javadoc mô tả classes, signatures và exceptions. Release notes mô tả **thay đổi qua các bản**; compatibility tables mô tả **mối quan hệ giữa các bản**. Cần phối hợp, không cố lấy mọi thông tin từ một trang.

### 3.3. Dùng nguồn chính thức theo thứ tự ưu tiên

1. Trang reference/versioned manual hoặc compatibility chính thức đúng sản phẩm.
2. Release notes, migration guide, upgrade/downgrade procedure tương ứng.
3. API docs/Javadoc/SDK reference của đúng version.
4. Official issue tracker/changelog và advisories khi cần bằng chứng bản vá.
5. Blog/tutorial chính thức để hiểu ngữ cảnh, nhưng đối chiếu reference.
6. Community/Stack Overflow/GitHub discussions để tìm manh mối, **không làm nguồn quyết định duy nhất** cho production.

## 4. Không nhầm sản phẩm MongoDB

“MongoDB” có thể chỉ:

- **MongoDB Server:** tiến trình `mongod` và cơ sở dữ liệu bên dưới.
- **mongos:** query router trong sharded deployment.
- **MongoDB Atlas:** dịch vụ quản lý cluster cùng control plane, tier, rollout và các sản phẩm liên quan.
- **MongoDB Shell (mongosh):** client interactive và scripting; phiên bản độc lập Server.
- **MongoDB Compass:** GUI client, có release cycle riêng.
- **MongoDB Database Tools:** các tiện ích như `mongodump`, `mongorestore`, `mongoimport` (không giả định cùng version với Server).
- **Language drivers:** Java, Node.js, Python, Go, C#..., phiên bản release riêng.
- **Spring Data MongoDB:** framework mapping/repositories, mang dependency MongoDB driver.
- **Atlas Search / Vector Search / Stream Processing:** sản phẩm hoặc thành phần có khả năng/phiên bản/availability khác Server cốt lõi.
- **Ops Manager / Kubernetes Operators / Connectors:** cần compatibility và lifecycle riêng.

### 4.1. Ví dụ lỗi “client mới nên server cũng mới”

Lệnh `mongosh --version` trả về phiên bản mongosh, **không** phải server version. Compass đang ở bản mới cũng không chứng minh cluster hỗ trợ một stage aggregation mới. Phải truy vấn Server và kiểm tra availability của tính năng đó.

### 4.2. Atlas không đồng nghĩa tất cả server features đều khả dụng

Atlas có các deployment tiers, managed settings, rollout schedules, optional services, permissions và region availability. Một tính năng trên MongoDB Server có thể cần cấu hình/plan/Atlas capability riêng, hoặc đang preview ở một deployment type. Đọc cả Server reference **và** Atlas docs liên quan.

## 5. Phân biệt trang `current` và trang theo version

Nhiều tài liệu driver dùng URL như:

~~~text
https://www.mongodb.com/docs/drivers/java/sync/current/
~~~

`current` thường trỏ tới tài liệu phiên bản tài liệu được trang đó xem là hiện hành. Nó rất hữu ích để tìm API mới nhưng **có thể không mô tả driver đã pin trong repository**.

### 5.1. Quy trình an toàn

1. Xác định version thực tế từ build/lockfile/runtime.
2. Mở trang tài liệu tương ứng.
3. Sử dụng **version selector** nếu có; ghi rõ nhánh version.
4. Với URL `current`, kiểm tra header/breadcrumb và nội dung release.
5. Đọc release notes của khoảng phiên bản đã nâng; không chỉ trang hiện tại.
6. Ghi URL, ngày truy cập và commit/dependency lock trong decision record.

### 5.2. Trang legacy có thể không còn được duy trì

Tài liệu cho các phiên bản EOL có thể chuyển sang khu vực legacy; nội dung có thể đã đóng băng và không phản ánh advisory mới. Đừng suy từ tài liệu legacy rằng một version còn được hỗ trợ.

### 5.3. Đừng thay version segment bằng suy đoán

Nếu một link có `/current/`, không giả định thay chuỗi đó bằng `/5.0/` luôn cho URL hợp lệ. Dùng version selector/navigation chính thức hoặc search site để tới đúng trang.

## 6. Cách tìm kiếm có hệ thống

Khi tìm tài liệu, dùng cụm từ chính xác thay vì hỏi quá rộng:

~~~text
MongoDB change streams resume token Server 8.0 manual
MongoDB Java driver 5.x server compatibility
Spring Data MongoDB 4.5 minimum driver compatibility
MongoDB 8.0 upgrade featureCompatibilityVersion procedure
MongoDB mongodump mongorestore compatibility tools
MongoDB Atlas search index availability tier
MongoDB partial unique index sharded restrictions
~~~

Trên search engine, dùng site filter:

~~~text
site:mongodb.com/docs/manual/ "featureCompatibilityVersion"
site:mongodb.com/docs/manual/release-notes/ "Important"
site:mongodb.com/docs/drivers/compatibility/ "Java"
site:docs.spring.io/spring-data/mongodb/reference/ "Compatibility Matrix"
site:mongodb.com/legal/support-policy/lifecycles "MongoDB 8.0"
~~~

### 6.1. Tìm theo tên lệnh chính xác

Với `$lookup`, `updateOne`, `createIndex` hay `setFeatureCompatibilityVersion`, ưu tiên reference page của operator/command; đọc phần syntax, behavior, restrictions, compatibility, examples và “Changed in version”.

### 6.2. Tìm lỗi theo mã và component

Nếu log có `MongoCommandException`, code 11000, `WriteConflict` hay `SERVER-xxxxx`, ghi đầy đủ message/error code nhưng **lọc secrets và PII** trước khi chia sẻ. Tìm official docs/advisory/issue, rồi đối chiếu server version, topology và driver version; cùng mã lỗi có thể xuất hiện ở nhiều nguyên nhân.

### 6.3. Tìm tính năng nhưng chưa thấy release

Không dùng date của blog như ngày tính năng GA. Tìm thêm release notes và trang reference ghi `New in version`, `Changed in version`, `Preview`, `Atlas only` hoặc `Deprecated`.

## 7. Phân biệt các loại tài liệu

| Loại | Trả lời câu gì? | Khi nào mở? |
|---|---|---|
| Manual/reference | Lệnh hoạt động thế nào, giới hạn gì? | Khi viết code/query |
| Tutorial/get started | Bắt đầu làm như thế nào? | Làm quen và thử nghiệm |
| Release notes | Bản mới thêm/sửa/bỏ gì? | Trước mọi upgrade |
| Changelog | Các issues/commits được sửa? | Truy lỗi cụ thể |
| Upgrade guide | Các bước và breaking changes cần xử lý? | Lập runbook |
| Downgrade guide | Có quay lại version cũ được không? | Rollback planning |
| Compatibility table | Tổ hợp versions có được hỗ trợ/test? | Chọn dependencies |
| Lifecycle/support | Còn được bảo trì và nhận fixes không? | Quản trị rủi ro |
| Security bulletin | CVE/advisory ảnh hưởng version nào? | Patch prioritization |
| API/Javadoc | Method/class/signature nào tồn tại? | Compile/implementation |

### 7.1. Release notes không phải compatibility matrix

Một release note có thể nói “driver hỗ trợ tính năng X của Server 9.0” nhưng không liệt kê mọi tổ hợp JDK/driver/server. Vẫn phải tra bảng compatibility. Một compatibility table đánh dấu ✓ cũng không đảm bảo application code **không có breaking changes** khi nâng thư viện.

### 7.2. Changelog không phải kế hoạch triển khai

Changelog liệt kê các issues rất hữu ích khi truy bug, nhưng upgrade runbook phải xét topology, FCV, app drivers, platform support, backup, rollback và test.

## 8. Kiểm tra phiên bản thực tế trên MongoDB Server

Trong `mongosh` kết nối đúng target:

~~~javascript
// In phiên bản binary Server mà phiên kết nối truy vấn.
db.version()

// Xem thông tin build/version; cần quyền phù hợp.
db.runCommand({ buildInfo: 1 })
~~~

Trên những MongoDB Server versions gần đây, `buildInfo` có thể yêu cầu xác thực hoặc quyền thích hợp. Khi sharded cluster, cần hiểu lệnh đang chạy qua `mongos` hay `mongod` nào; một giá trị từ một endpoint không chứng minh mọi shard/router đã cùng version trong quá trình rolling upgrade.

### 8.1. Xem FCV tách biệt

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
~~~

Lệnh này phải chạy trên endpoint `mongod` phù hợp và cần quyền. Trong sharded cluster có access control, việc truy FCV ở shard/config server phải tuân theo tài liệu quyền/topology; đừng kỳ vọng command chạy identically trên `mongos`. **Chỉ đọc**, không gọi set FCV trong bài thực hành.

### 8.2. Xem topology

~~~javascript
// Trong replica set context và có quyền thích hợp:
rs.status()

// Một số thông tin deployment:
db.hello()
~~~

`rs.status()` dành cho replica set member, không phải lệnh chung cho mọi standalone/mongos. `hello` cung cấp thông tin topology/wire protocol hữu ích; cách diễn giải thay đổi theo server/topology.

### 8.3. Xem phiên bản mongosh

Ở shell của hệ điều hành:

~~~bash
mongosh --version
~~~

Không lấy giá trị mongosh làm server version.

## 9. Kiểm tra version ở Java/Spring Data

Tập tin dependency thường là nguồn quan trọng hơn câu lệnh “tôi nhớ driver khoảng 5.x”.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mongodb-driver-sync --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-mongodb --configuration runtimeClasspath
~~~

Trên Windows PowerShell nếu project dùng Gradle wrapper:

~~~powershell
.\gradlew.bat dependencyInsight --dependency mongodb-driver-sync --configuration runtimeClasspath
~~~

Đây là các lệnh **để người học tham khảo**, không chạy trong môi trường production ở bài này. Tên configuration có thể khác ở project Java/Kotlin/Android và phụ thuộc cách quản lý dependencies.

### 9.1. BOM/dependency management có thể chọn version thay bạn

Spring Boot dependency management/BOM có thể pin một phiên bản Spring Data và MongoDB driver ngay cả khi `build.gradle` không nêu version tường minh. Vì vậy:

- Xem `gradle.lockfile` hoặc dependency lock/bản dependency resolved.
- Kiểm tra phiên bản `spring-boot-dependencies` và Spring Data release train.
- Đối chiếu minimum driver version và tested database generations.
- Không override driver thành bản mới chỉ vì “thấy Maven có bản đó” mà chưa kiểm tra tương thích framework.

### 9.2. Maven

~~~bash
mvn dependency:tree -Dincludes=org.mongodb
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-mongodb
~~~

Xem BOM/`dependencyManagement` nếu version không nằm trực tiếp ở dependency declaration.

### 9.3. Runtime Java

~~~bash
java -version
~~~

Driver–server tương thích chưa đủ nếu driver mới yêu cầu JDK mới hơn application runtime hoặc framework cũ không hỗ trợ driver API.

## 10. Kiểm tra Node.js/Python và các tools

Node.js:

~~~bash
node --version
npm ls mongodb --all
~~~

Với npm/yarn/pnpm, nhìn **resolved/lockfile dependency tree**, không chỉ `package.json` version range. Một ORM/ODM (ví dụ Mongoose) có thể có phiên bản driver transitive khác với kỳ vọng.

Python:

~~~bash
python --version
python -m pip show pymongo
~~~

Khi có nhiều virtual environments, chạy trên interpreter của deployment; `pip show` trong shell khác có thể không phản ánh package đang phục vụ.

Tools:

~~~bash
mongodump --version
mongorestore --version
mongoimport --version
~~~

### 10.1. Không nhầm build-time với runtime

Container image, base OS, JDK và driver JAR thật có thể khác local laptop. Ghi hash/tag của image, SBOM hoặc artifact metadata để biết production đang dùng gì.

### 10.2. Tách các lớp phiên bản

~~~text
App code + Spring Boot/Spring Data
  → MongoDB Java driver + BSON codecs
    → MongoDB wire protocol/auth/TLS
      → MongoDB Server binary + FCV + topology
        → Atlas/self-managed platform capabilities
~~~

Mỗi mũi tên có **một ràng buộc tương thích khác nhau**.

## 11. MongoDB Server release notes: đọc theo lớp phiên bản

Trang bắt đầu: [Server Release Notes](https://www.mongodb.com/docs/manual/release-notes/). Từ đó chọn đúng release series, rồi xác định bản vá đã cài và bản vá dự kiến nâng.

Một version dạng `X.Y.Z` thường có:

- **X — major release:** thay đổi khả năng/compatibility lớn, có thể cần upgrade path riêng.
- **Y — minor release:** vòng đời và availability tùy chính sách tại thời điểm phát hành. Với MongoDB từ 8.2, “minor” và cách phân phối khác một số rapid releases trước đó; kiểm tra [Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/), không giả định tất cả `8.x` được quản lý giống nhau.
- **Z — patch release:** chứa fixes, security/reliability/performance changes và một số thay đổi hành vi cần lưu ý.

### 11.1. Ví dụ về mốc tài liệu, không phải giá trị vĩnh viễn

Ở thời điểm tra cứu **14/11/2026**, trang Server Release Notes liệt kê **9.0-series** ở mục current stable và **8.3/8.0/7.0** ở các mục trước đó. Việc một trang có release mới **không** chứng minh mọi loại cluster/region/edition đã có thể nâng ngay tới release ấy. Kiểm tra riêng availability cho Atlas tier hoặc self-managed trong [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) và trang [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/).

### 11.2. Cách đọc patch notes

Khi nâng từ `8.0.a` lên `8.0.b`, không chỉ đọc một dòng ghi “latest patch”. Xem **mọi patch releases trong khoảng**, các mục:

1. Critical Advisories/Important/Warning.
2. Security fixes/CVE.
3. Data correctness, replication, sharding và storage.
4. Authentication/TLS/driver interaction.
5. Query optimizer/aggregation/index behavior.
6. Backward incompatibilities và new restrictions.
7. Issue IDs và full changelog.

Tìm hướng dẫn cụ thể nếu issue đụng vào feature bạn đang dùng; không đánh giá mức ưu tiên chỉ từ số lượng issues được sửa.

### 11.3. Release notes chính và full changelog

Release notes thường tổ chức điểm nổi bật, cảnh báo và patch summaries. Full changelog có thể liệt kê từng issue JIRA với nhóm Server/Replication/Storage/Sharding/Security. Khi điều tra một `SERVER-xxxxx`, đọc cả hai:

~~~text
Release notes (version/patch)
    → Changelog (issue ID)
        → Official issue details/advisory
            → Affected version range + verification test
~~~

Không suy “issue đã sửa ở bản X” nghĩa bản của bạn chắc chắn không bị ảnh hưởng nếu bạn chưa đối chiếu các nhánh backport và patch đang chạy.

## 12. Server release notes: checklist đọc trang

| Nội dung trên trang | Ý nghĩa khi quyết định |
|---|---|
| `New in version` | Tính năng có mốc phát hành |
| `Changed in version` | Có thể đổi semantics/default |
| `Deprecated` | Phải lên kế hoạch thay thế |
| `Removed` | Code/script cũ có thể hỏng |
| `Important/Warning` | Điều kiện cần xử lý trước release |
| `Critical Advisory` | Khả năng data/security impact |
| `Upgrade Restrictions` | Có thể không được nhảy version tùy ý |
| `Downgrade Limitations` | Rollback có thể mất tính khả thi |
| `Patch Fixes` | Xác định yêu cầu vá bảo mật/bug |

### 12.1. Một dòng “fixed issue” không đủ

Đọc affected version range, điều kiện tái hiện, workaround, bản phát hành chứa fix và deployment type. Có issue chỉ xảy ra khi sharding, với indexes đặc biệt hoặc feature flag. Chỉ chọn patch vì “nhiều fixes” không phải phương pháp.

### 12.2. Không nhầm preview và GA

Tính năng preview/experimental có thể đổi API, support policy và độ ổn định. Với sản phẩm Atlas, xem riêng tier/region/rollout. Đừng đưa vào production như một GA feature nếu nguồn chính thức chưa xác nhận.

### 12.3. Nâng cấp major có thể phải qua trung gian

Đọc **upgrade paths** thay vì tự chọn binary mới và replace ngay. Mixed-version replica set/sharded upgrades, FCV, downgrade restrictions và backup có quy trình chính thức riêng.

## 13. Cách đọc release notes của driver

Driver release notes không phải Server release notes. Ví dụ MongoDB Java Sync Driver:

- [Java Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/)
- [Java Driver Upgrade Guide](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/)
- [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/)

### 13.1. Tìm bốn nhóm thay đổi

1. **New functionality:** builder/API mới, integration mới, server feature mới.
2. **Breaking changes:** classes/package/method signatures bị đổi/xóa, dependency structure khác.
3. **Behavioral changes:** retry/timeout/authentication/serialization/monitoring mặc định thay đổi.
4. **Security/deprecation fixes:** bản vá ảnh hưởng credentials, logs, TLS, codecs hoặc transitive dependencies.

### 13.2. Ví dụ thực tế cần đọc kỹ

Trang Upgrade Driver Versions có các mục riêng về **server support dropped** ở một số nhánh driver. Điều này cho thấy nâng driver lên major/minor mới **không tự đảm bảo tiếp tục kết nối được server EOL**. Đừng kết luận “driver mới luôn backward compatible với mọi server cũ”.

### 13.3. Release notes không tự nói code của bạn compile được

Nếu Java driver major version đổi signatures, ứng dụng có thể không biên dịch được dù driver–server compatibility table ghi ✓. Chạy compile/integration tests và kiểm tra dependency compatibility giữa Spring Data, BSON codecs và Java runtime.

## 14. Atlas, Compass và tools có release notes riêng

Một hệ thống gồm Atlas + Compass + mongosh + Database Tools có **nhiều vòng release** độc lập.

| Thành phần | Nguồn cần xem | Loại thay đổi |
|---|---|---|
| Atlas control plane/cluster features | [Atlas Release Notes](https://www.mongodb.com/docs/atlas/release-notes/) | Regions, tiers, UI, backup, upgrades, managed features |
| Atlas version policy | [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/) | Auto upgrades, major version options, FCV policy |
| Compass | [Compass Release Notes](https://www.mongodb.com/docs/compass/release-notes/) | GUI, connectivity, embedded shell, security |
| Java driver | [Java Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/) | API/behavior/server support |
| Database Tools | Product-specific docs/release notes | Dump/restore/import/export behavior |
| Spring Data MongoDB | Spring release/upgrade docs | Mapping/repositories/query behavior |

### 14.1. Ví dụ Atlas

Nếu Atlas changelog ghi một tính năng “GA”, phải xem **loại cluster được hỗ trợ, vùng, tier và điều kiện bật feature**. Đừng dùng Atlas changelog để suy rằng MongoDB Community self-managed cũng có API đó.

### 14.2. Ví dụ Compass

Một lỗi GUI có thể được sửa ở Compass patch mà không liên quan Server. Nếu Compass không hiển thị một index đúng, kiểm tra Compass version/release notes trước khi thay cấu hình MongoDB Server production.

### 14.3. Các công cụ backup/restore

`mongodump`/`mongorestore` có release cycle và compatibility riêng. Khi lên kế hoạch khôi phục, kiểm tra **tool version ↔ source/target server version ↔ BSON/metadata/index compatibility**, không xem mỗi `mongod --version`.

## 15. Phiên bản nào đang được hỗ trợ?

Trang [MongoDB Software Lifecycle Schedules](https://www.mongodb.com/legal/support-policy/lifecycles) liệt kê **release date** và **End of Life (EOL)** của các product/deployment types được chính sách bao phủ.

### 15.1. Bảng lifecycle mẫu

| Cột | Ý nghĩa |
|---|---|
| Product | Server EA, Atlas, Ops Manager, Search, v.v. |
| Release version | Series được bảo trì |
| General availability/release date | Mốc bắt đầu |
| End of Life date | Mốc hết hỗ trợ theo chính sách |
| Optional extended support | Có hay không, cần hợp đồng/điều kiện |
| Source URL + verified date | Bằng chứng còn mới |

**Không** lấy EOL của Atlas Auto Upgrade áp cho Community/Enterprise Advanced, hoặc EOL của Server áp cho Compass. Đọc đúng heading của bảng lifecycle.

### 15.2. EOL không có nghĩa binary lập tức ngừng chạy

Một server EOL vẫn có thể khởi động và phục vụ request. Nhưng có thể không còn fixes/security support, driver mới bỏ tương thích, package dependencies/OS support biến mất. “Vẫn chạy” không đồng nghĩa “được hỗ trợ và an toàn”.

### 15.3. Không copy ngày EOL vào tài liệu rồi bỏ quên

Vòng đời được nhà cung cấp cập nhật theo chính sách. Trong ADR/upgrade ticket, ghi URL chính thức và **ngày xác minh**; đặt một checkpoint kiểm tra lại trước rollout.

## 16. Security advisories và critical warnings

Security patch decisions cần thông tin cụ thể, không chỉ lời truyền miệng:

1. CVE/advisory ID.
2. Product và component bị ảnh hưởng: Server, driver, Compass, tool, Atlas feature.
3. Affected version range/editions.
4. Fixed release/patch và backports.
5. Điều kiện khai thác và severity theo nguồn.
6. Mitigation hoặc workaround chính thức.
7. Khả năng triển khai fix trong topology/version hiện tại.

### 16.1. Không kết luận từ một CVE chưa đối chiếu

Một CVE cho Compass không chứng minh Server vulnerable. Một driver bug lộ credentials qua logs không nhất thiết sửa bằng nâng server. Khoanh đúng thành phần/phiên bản và log exposure trước khi sửa.

### 16.2. Kiểm tra nhiều nhánh patch

Một issue có thể được backport vào hai release series với patch numbers khác nhau. Dùng release notes/changelog của **series production đang chạy**, không chỉ đọc nhánh mới nhất.

### 16.3. Đặt bằng chứng trong ticket

~~~text
Advisory: CVE-XXXX-YYYY
Affected component: MongoDB Java driver (example)
Our resolved version: x.y.z
Fixed version available in our line: a.b.c
Official source + accessed date: ...
Mitigation until rollout: ...
Regression tests: ...
Rollback policy: ...
~~~

Các giá trị placeholder tránh khẳng định version/CVE không có chứng cứ. Đừng gửi secret URI hoặc customer data trong security ticket/chat.

## 17. Ma trận tương thích là gì?

**Compatibility matrix** là bảng các cặp (hoặc nhiều chiều) phiên bản/sản phẩm được xác nhận theo những semantics cụ thể: hỗ trợ đầy đủ, một phần, không tương thích, chưa thử nghiệm, yêu cầu runtime tối thiểu hoặc giới hạn feature.

Một ứng dụng Java Spring Data cần xem ít nhất:

~~~mermaid
flowchart TD
    App["Application + Spring Boot"] --> Spring["Spring Data MongoDB version"]
    Spring --> Driver["MongoDB Java Driver version"]
    Driver --> Jdk["JDK runtime version"]
    Driver --> Server["MongoDB Server version"]
    Server --> FCV["Feature Compatibility Version"]
    Server --> Deploy["Replica set / sharding / Atlas tier"]
    Deploy --> Feature["Feature availability"]
~~~

Mỗi mũi tên cần bằng chứng riêng. **Một dấu ✓ giữa driver và Server không xác nhận mọi lớp còn lại**.

### 17.1. Nhiều bảng, một quyết định

- Driver ↔ Server.
- Driver ↔ language runtime/JDK.
- Framework/Spring Data ↔ minimum driver/known tested Server versions.
- Server version ↔ OS/architecture/cloud deployment.
- Server binary ↔ FCV/upgrade path.
- Feature ↔ Server release/topology/Atlas tier/edition.
- Tools ↔ Server, metadata/backup format và upgrade path.

### 17.2. Tìm compatibility table chính thức

Truy cập [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/) rồi chọn **Language** và **Driver or Framework** tương ứng. Không đọc bảng Java driver cho app Node.js; không đọc bảng Node driver chung cho thư viện Mongoose mà bỏ qua dependency riêng của Mongoose.

## 18. Cách hiểu từng ký hiệu trong bảng client compatibility

Theo chú giải của bảng MongoDB Client Libraries ở thời điểm tham khảo:

| Ký hiệu | Ý nghĩa | Có thể dùng production? |
|---|---|---|
| **✓** | Tổ hợp được đánh dấu **fully compatible** theo bảng | Ứng viên phù hợp; vẫn phải test app và features |
| **⊛** | **Partially compatible**: kết nối có thể hoạt động nhưng thiếu hỗ trợ đầy đủ tính năng mới | Cần hiểu giới hạn và test nghiêm ngặt |
| **✗** | Không tương thích theo bảng | Không chọn tổ hợp này |
| **Ô trống** | Không được test/không có mark theo chú giải bảng | Không tự suy tương thích |

### 18.1. Partially compatible không có nghĩa mọi chức năng chạy đúng

Nó có thể cho phép ứng dụng dùng các chức năng cũ trong khi API mới của server chưa được driver hỗ trợ. Nếu app cần feature mới/behavior mới, phải nâng driver hoặc đổi thiết kế.

### 18.2. Ô trống không phải dấu ✓

Nếu matrix chưa kiểm tra một combo, đừng ghi trạng thái “supported” chỉ vì tự connect thử được một lần. Tìm thêm release/upgrade docs, vendor support statement hoặc yêu cầu xác minh chính thức.

### 18.3. Compatible khác supported in lifecycle

Một combo có thể kỹ thuật kết nối được nhưng chứa server EOL hoặc runtime không còn nhận security patches. Deployment decision phải vượt **cả compatibility gate và support/security lifecycle gate**.

## 19. Ví dụ đọc bảng Java Driver ↔ Server

Ví dụ lịch sử tại **14/11/2026** trên [official compatibility table](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync):

| Java Sync Driver | MongoDB Server 9.0 | MongoDB Server 8.0 | Cách hiểu |
|---|---|---|---|
| 5.12–5.13 | ✓ | ✓ | Được bảng đánh dấu tương thích đầy đủ ở hai series |
| 5.9–5.11 | ⊛ | ✓ | Với Server 9.0 thiếu hỗ trợ đầy đủ một số tính năng |
| 5.2–5.7 | Ô trống | ✓ | Không tự suy tương thích với 9.0 từ cột 8.0 |

**Lưu ý:** đây là **ảnh chụp ví dụ cách đọc bảng tại ngày đã nêu**, không dùng để chọn versions trong năm tương lai mà không mở lại nguồn. Có thể nhà cung cấp đã cập nhật driver/Server/version rows.

### 19.1. Đọc cả footnotes

Một số tổ hợp bị ảnh hưởng bởi lỗi authentication hoặc giới hạn runtime dù bản driver trông như “tương thích server cũ”. Chú thích cuối bảng thường chỉ rõ exceptions; **không bỏ qua footnotes**.

### 19.2. Đọc hai chiều

Đừng chỉ hỏi “Server 9.0 có chạy được driver 5.10 không?”. Hỏi thêm “driver 5.10 có chạy trên JDK của tôi không?”, “Spring Data version của tôi hỗ trợ driver đó không?” và “các tính năng tôi dùng có được hỗ trợ đầy đủ không?”.

### 19.3. Chưa chắc 9.0 có thể triển khai ở tier bạn dùng

Release có trong docs không đồng nghĩa cluster Atlas của bạn hoặc package self-managed đã hỗ trợ đúng series/patch đó vào thời điểm nâng. Mở policy/version availability của **deployment cụ thể**.

## 20. Driver ↔ runtime: chiều tương thích dễ quên

Ví dụ Java:

| Hệ thống đang dùng | Cần tra |
|---|---|
| Java 8 | Driver phiên bản nào còn tương thích? |
| Java 11 | Spring Data release nào hỗ trợ? |
| Java 17 | Driver API, TLS, Spring Framework requirements |
| Java 21 | Driver và runtime feature compatibility |
| Container JRE khác local JDK | Resolved runtime/JRE thật |

MongoDB Client Library Compatibility Tables có phần **Java Compatibility** riêng. Cách đọc tương tự: một dấu ✓ ghi cặp được kiểm tra/hỗ trợ theo bảng, nhưng không thay framework/runtime integration tests.

### 20.1. Node.js và Python

Bảng Node.js driver thường có thêm chiều **Node.js versions**; bảng PyMongo có Python/PyPy runtime. Trước khi nâng driver:

1. Xem minimum runtime.
2. Xem framework/ODM version.
3. Xem driver ↔ Server compatibility.
4. Chạy tests ở cùng runtime/container image với production.

### 20.2. Runtime mới cũng có thể gây bất ngờ

Thay JDK, Node.js hoặc Python có thể ảnh hưởng TLS, dependency binaries, codecs, threading và logging dù MongoDB Server không đổi. Treat runtime upgrade như thay đổi có kiểm thử riêng.

## 21. Spring Data MongoDB: hai bảng phải cùng đúng

Trang [Spring Data MongoDB Requirements](https://docs.spring.io/spring-data/mongodb/reference/preface.html) cung cấp các thông tin như:

- Spring Data release train và version MongoDB module.
- **Minimum MongoDB Java driver version**.
- MongoDB Server versions đã được **test** bởi Spring Data.
- Yêu cầu JDK và Spring Framework.

### 21.1. Ví dụ ảnh chụp tại thời điểm tra cứu

Trong bảng Spring Data MongoDB được công bố ở thời điểm tham khảo, release train **2026.0** tương ứng Spring Data MongoDB **5.1.x**, driver minimum **5.6.x**, và database test matrix nêu **6.x–8.x**. Đây là **min driver và phạm vi test của framework**, **không** có nghĩa mọi driver ≥5.6 được hỗ trợ tùy ý hoặc MongoDB Server 9.0 bị khẳng định không tương thích.

### 21.2. Ghép điều kiện có logic

~~~text
Spring Data version requirement
  ∩ Driver compatibility với Server
  ∩ Driver compatibility với JDK
  ∩ Spring Framework/Boot compatibility
  ∩ Feature/topology availability
  = candidate deployment combination
~~~

Nếu Spring Data cần driver tối thiểu 5.6 nhưng project đang pin 5.4, **NO-GO**. Nếu driver 5.10 có dấu ⊛ với Server 9.0 mà app muốn dùng feature 9.0 không được hỗ trợ, cần nâng driver/thay thiết kế trước khi GO.

### 21.3. Tested database versions ≠ absolute maximum

Spring Data có thể ghi “tested 6.x–8.x” ngay cả khi official driver matrix hỗ trợ một Server mới hơn. Điều đó có nghĩa **cần kiểm thử tích hợp/framework riêng và cân nhắc vendor support**, không tự suy “chắc chắn chạy” hoặc “chắc chắn lỗi”.

### 21.4. Boot BOM có thể chọn khác điều bạn nghĩ

Kiểm tra resolved dependency tree. Có thể Spring Data 5.x transitively dùng MongoDB Java Driver khác với version khai báo trực tiếp/override; tránh mix không tương thích giữa `mongodb-driver-sync`, `mongodb-driver-core` và `bson`.

## 22. Tạo ma trận compatibility cho dự án

Thay vì một dòng “MongoDB compatible”, dùng bảng cụ thể:

| Thành phần | Đang chạy | Dự kiến | Nguồn chính thức | Kết quả |
|---|---|---|---|---|
| MongoDB Server | x.y.z | a.b.c | Server release notes, lifecycle | TBD |
| FCV | x.y | target FCV | Versions & FCV docs | TBD |
| Topology/edition | Replica set / Atlas tier | ... | Deployment docs | TBD |
| MongoDB Java driver | x.y.z | a.b.c | Driver–Server matrix | TBD |
| Java runtime | JDK x | JDK y | Driver Java compatibility | TBD |
| Spring Data MongoDB | x.y.z | ... | Spring requirements | TBD |
| Spring Boot/Framework | x.y.z | ... | Spring support docs | TBD |
| mongosh/Compass | x.y.z | ... | Tool release notes | TBD |
| Database Tools | x.y.z | ... | Tool compatibility | TBD |
| Features used | Change streams, transactions | ... | Server/Atlas feature docs | TBD |
| Platform | OS/container architecture | ... | Supported platforms | TBD |

**TBD** không phải PASS. Điền mỗi cột sau khi đã xác minh, không suy đoán từ một successful localhost connection.

### 22.1. Thêm nguồn và thời điểm

Mỗi hàng quan trọng nên có:

~~~text
Evidence URL:
Source title:
Source product/version:
Verified at (UTC):
Owner:
Notes/footnotes:
Decision (PASS / CONDITIONAL / NO-GO / UNKNOWN):
~~~

### 22.2. Đặt khả năng tự động kiểm tra

Dependency versions có thể được thu từ build lockfiles/SBOM; Server/FCV từ một diagnostic read-only script; dates/manual review vẫn cần con người với support policies, footnotes và feature availability.

## 23. Feature Compatibility Version (FCV) là gì?

MongoDB Server binary version và **featureCompatibilityVersion** là hai thông tin khác nhau. FCV kiểm soát việc bật một số tính năng ghi dữ liệu ở định dạng/semantics không thể đọc hoặc sử dụng được ở phiên bản server cũ hơn.

~~~text
MongoDB binaries vừa được nâng
    ↓
Cluster chạy thử ở FCV trước đó theo upgrade path
    ↓
Quan sát/stabilize
    ↓
Chỉ sau khi đủ tự tin và hiểu downgrade impact
    ↓
Nâng FCV theo procedure chính thức
~~~

Theo [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/), nâng binaries và bật các tính năng FCV mới được tách thành hai bước đối với những upgrade paths phù hợp. Quy tắc cụ thể có thể khác theo version/Atlas rollout; luôn mở guide đúng release.

### 23.1. FCV không phải version của driver

Một driver mới không tự thay FCV. Một cluster binary mới với FCV cũ không đồng nghĩa được sử dụng tất cả persisted data features của binary mới.

### 23.2. FCV là điều kiện downgrade quan trọng

Khi bật tính năng lưu dữ liệu không tương thích ngược, hạ binaries về version trước có thể khó hoặc không được phép cho tới khi xử lý dữ liệu. Trước khi nâng FCV phải xem **downgrade documentation, rollback window và backup**.

### 23.3. FCV không thay test compatibility

FCV phù hợp không chứng minh driver/server/framework compatible; nó chỉ là một chiều của tình trạng deployment.

## 24. Kiểm tra FCV và thận trọng với lệnh thay đổi

**Đọc trạng thái**:

~~~javascript
// Kết nối mongod phù hợp, có quyền cần thiết.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
~~~

**Không** dùng lệnh này trong lab để vô tình nâng/hạ:

~~~text
setFeatureCompatibilityVersion
~~~

Lệnh set có thể ảnh hưởng tính năng persist dữ liệu và downgrade; các trường bắt buộc như `confirm`, `writeConcern` và điều kiện preflight có thể khác theo server release. Xem [reference command](https://www.mongodb.com/docs/manual/reference/command/setfeaturecompatibilityversion/) đúng phiên bản, không sao chép một command từ bài viết cũ vào cluster production.

### 24.1. Khác biệt Atlas

Atlas Auto Upgrades có chính sách rollout/FCV được quản lý khác self-managed; người dùng có thể không được tự chọn FCV giống một mongod tự quản. Đọc [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/).

### 24.2. Không kích hoạt FCV mới ngay trong maintenance window nếu chưa cần

Nếu upgrade guide cho phép burn-in ở FCV cũ, đó là một cửa sổ để test compatibility và phát hiện regressions trước khi bật persisted features không đảo ngược. Nhưng không giữ FCV cũ vô hạn mà quên support policy và operational requirements.

### 24.3. Không xem FCV là cờ có thể toggle tùy ý

Hạ FCV có thể có điều kiện chặt chẽ và yêu cầu xử lý persisted data/index/features. Một số đường downgrade không được hỗ trợ hoặc không bảo toàn thông tin. Luôn lập runbook/approval riêng.

## 25. Stable API giải quyết vấn đề gì?

MongoDB Stable API (còn gọi là Versioned API trong một số tài liệu) giúp ứng dụng yêu cầu một tập hành vi cho **các lệnh được API phiên bản đó bao phủ**, giảm rủi ro khi nâng driver hoặc server.

Nguồn tham khảo: [Stable API — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/stable-api/).

### 25.1. Điều Stable API không cam kết

- Không đảm bảo mọi MongoDB command/aggregation stage đều nằm trong Stable API.
- Không thay driver ↔ server compatibility matrix.
- Không bảo đảm mọi tính năng Atlas preview/edition sẽ có.
- Không giải quyết breaking changes trong Java application API, Spring Data hoặc JDK.
- Không làm backup/index/query performance tự tương thích.

### 25.2. Cách tra một command có trong Stable API không

1. Xem phiên bản Server hỗ trợ Stable API.
2. Mở Stable API reference và **danh sách commands được bao phủ**.
3. Kiểm tra command/option bạn dùng.
4. Xem `apiStrict` và `apiDeprecationErrors` behavior khi cấu hình.
5. Chạy integration tests với strict mode nếu đó là lựa chọn của dự án.

### 25.3. Java driver skeleton

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.ServerApi;
import com.mongodb.ServerApiVersion;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

ServerApi serverApi = ServerApi.builder()
    .version(ServerApiVersion.V1)
    .strict(true)
    .deprecationErrors(true)
    .build();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(
        new com.mongodb.ConnectionString(
            System.getenv("MONGODB_TEST_URI")
        )
    )
    .serverApi(serverApi)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    // Integration tests against an isolated compatible deployment.
}
~~~

Đây là ví dụ **cấu hình** cho Java Sync Driver version hỗ trợ `ServerApi`, không chạy ở đây. Với strict mode, nếu app gọi một command/option ngoài tập Stable API, nó có thể bị từ chối; kiểm tra và sửa code thay vì tự tắt các cảnh báo rồi tuyên bố mọi thao tác stable.

## 26. Ma trận tính năng khác ma trận version

Ngay cả khi Java driver 5.x và Server 8.x được đánh dấu compatible, một tính năng cụ thể còn có thể bị giới hạn:

| Tính năng | Cần kiểm tra ở đâu? | Điều có thể chặn |
|---|---|---|
| Multi-document transactions | Server transaction docs, topology | Standalone vs replica set/sharded, limits |
| Change streams | Server docs, deployment topology | Supported deployment, oplog history |
| `$lookup` với foreign sharded collection | Aggregation reference + release notes | Server version/feature restrictions |
| Atlas Search | Atlas Search docs + tier | Product availability, index requirements |
| Vector search | Atlas/Server docs + release notes | Feature GA/preview, engine/tier |
| Stable API option | Server Stable API reference | API version/command coverage |
| Queryable Encryption | Encryption docs + driver compatibility | Driver, server, key management, query type |
| CSFLE | Driver and server docs | Crypt library, KMS, BSON/feature limits |
| Resharding | Sharding/upgrade reference | Topology, FCV, restrictions |
| Time series collection | Server manual + release notes | Version-specific query/write restrictions |

### 26.1. Một ví dụ có điều kiện theo phiên bản

Các tính năng như transactions và `$lookup` với sharded collections có lịch sử hỗ trợ thay đổi qua các releases. Khi học, tìm reference pages ghi `New in version` và limitations; không suy từ cú pháp tồn tại trong mongosh rằng server hiện tại có thể thực thi mọi biến thể.

### 26.2. Server feature ≠ driver helper

Server có thể hiểu một command nhưng Java Driver version cũ chưa có builder method tiện lợi. Có trường hợp có thể gọi raw command với quyền/semantics tương ứng; **không** coi đó là cách vượt compatibility hoặc security policy tự động.

### 26.3. Atlas feature ≠ Community feature

Chỉ khi docs chính thức ghi rõ deployment support và điều kiện, mới đánh dấu PASS. Với các sản phẩm managed Search/Vector Search, không suy từ trang Atlas rằng self-managed `mongod` tự có cùng capabilities.

## 27. Platform compatibility là trục riêng

Một version MongoDB Server có thể hỗ trợ những OS distributions, architectures, CPU requirements và build packages nhất định.

### 27.1. Cần tra gì?

1. Supported Platforms theo **Server major/minor version**.
2. OS distribution/release: Ubuntu/Debian/RHEL/Windows/macOS nếu được hỗ trợ.
3. CPU architecture x86_64/ARM64 và những yêu cầu CPU feature.
4. Container image/tag/digest, base OS và library dependencies.
5. TLS/SSL/OpenSSL, FIPS và auth mechanisms nếu có.
6. Filesystem/kernel/storage requirements cho self-managed.
7. Phiên bản Docker/Kubernetes Operator/Ops Manager nếu dùng.

### 27.2. Container chạy được không đồng nghĩa được hỗ trợ

Một container có thể khởi động trên OS/kernel không nằm trong supported platforms list. Với production, supportability/security vẫn cần kiểm tra độc lập với việc smoke test đã pass.

### 27.3. Atlas che bớt nhưng không bỏ trục client

Atlas quản lý nhiều chi tiết server/platform, nhưng clients vẫn cần driver/runtime/TLS/network compatibility và phải làm theo Atlas upgrade policy.

## 28. Mixed-version deployments trong khi nâng cấp

Rolling upgrade replica set hoặc sharded cluster có thể có giai đoạn **nhiều binary versions đồng thời** theo quy trình được hỗ trợ. Điều đó không có nghĩa bất kỳ tổ hợp patch/minor nào cũng được phép.

### 28.1. Phải đọc đúng upgrade procedure

Các tình huống cần đọc:

- Upgrade standalone.
- Upgrade replica set.
- Upgrade sharded cluster, kể cả mongos/config servers/shards.
- Atlas managed rolling upgrade.
- Downgrade/restore khi upgrade chưa hoàn tất.

### 28.2. Không phát tính năng mới quá sớm

Trong mixed-version period, app mới gửi command/option chỉ bản server mới hiểu có thể gặp lỗi ở node/router cũ. Tuân theo upgrade order, FCV và rollout guidance trước khi dùng feature mới.

### 28.3. Compatibility matrix là điều kiện cần, chưa đủ

Driver có thể tương thích với cả version cũ và mới nhưng một feature của app chỉ hỗ trợ trên binary mới. Cần tests trong transitional topology theo guide.

## 29. “Supported” có những mức nào?

| Từ ngữ | Cần hiểu |
|---|---|
| **Can connect** | Client mở kết nối trong một thử nghiệm |
| **Works for tested use case** | Một vài operations đã chạy được |
| **Compatible** | Theo định nghĩa compatibility chart/vendor |
| **Fully compatible** | Bảng hỗ trợ đầy đủ theo scope được mô tả |
| **Partially compatible** | Chỉ một tập features; đọc limitations |
| **Tested by framework** | Có trong test matrix của framework |
| **Supported release** | Còn lifecycle/vendor support phù hợp |
| **GA available** | Đã GA trong product/deployment được nêu |
| **Preview/experimental** | Chưa nên suy các bảo đảm GA |
| **EOL/legacy** | Có thể vẫn chạy nhưng support/security hạn chế |

### 29.1. Không diễn giải quá mức dấu ✓

Một dấu ✓ ở driver ↔ Server chart không đảm bảo throughput, tài nguyên, topology, user permissions, deployment tier hoặc app business correctness.

### 29.2. Không diễn giải ô trống thành lỗi chắc chắn

Nó có thể nghĩa chưa được test hoặc bảng không ghi trạng thái; tìm thêm nguồn. Chỉ dấu ✗ hoặc statement chính thức rõ mới cho kết luận incompatibility ở scope được định nghĩa.

## 30. Status taxonomy cho bảng nội bộ

Nên dùng một tập trạng thái nhất quán:

| Status | Ý nghĩa | Hành động |
|---|---|---|
| `PASS` | Có bằng chứng hỗ trợ/tính năng và tests đạt | Có thể tiến hành theo rollout |
| `PASS_WITH_CONDITIONS` | Có compatibility nhưng giới hạn hoặc remediation | Chỉ GO sau khi điều kiện được đáp ứng |
| `UNKNOWN` | Chưa đủ thông tin/bảng trống | Xác minh vendor/tests |
| `NO_GO` | Vi phạm incompatibility/hard gate | Đổi version/architecture |
| `EOL_RISK` | Hết hỗ trợ hoặc security concern | Lập lộ trình thay thế |
| `NEEDS_TEST` | Bảng compatible nhưng app chưa test | Chạy integration/load/fault tests |

Đừng coi `PASS_WITH_CONDITIONS` là PASS rồi quên footnotes. Ghi người nhận trách nhiệm, deadline và evidence.

## 31. Một bảng ma trận thử nghiệm nhiều chiều

Ví dụ template **giả định** (không phải vendor certification):

| Server | Java driver | Java runtime | Spring Data | Feature | Vendor matrix | Internal test | Decision |
|---|---|---|---|---|---|---|---|
| A | B | JDK-X | SD-Y | CRUD | URL cần điền | TBD | UNKNOWN |
| A | B | JDK-X | SD-Y | Transactions | URL + topology | TBD | NEEDS_TEST |
| C | D | JDK-Z | SD-W | Change streams | URL + oplog policy | TBD | UNKNOWN |
| C | D | JDK-Z | SD-W | Feature mới | Release note + API ref | TBD | UNKNOWN |

Nên có thêm cột `OS/platform`, `FCV`, `Atlas tier`, `security advisory` và `support EOL` khi quyết định migration thật. Một bản table nhỏ trong wiki không thay được tất cả evidence, nhưng giúp **nhìn thấy những ô còn thiếu**.

### 31.1. Cùng tổ hợp versions nhưng khác topology

Transactions có thể chạy ở replica set phù hợp nhưng không ở standalone; connection to Atlas Search cần các điều kiện khác CRUD. Tạo các dòng test riêng theo features mà app thật dùng.

### 31.2. Quản lý phần “unknown”

Không tự điền giá trị đẹp khi chưa có nguồn. Lập owner/task để lấy evidence, và cấm GO nếu nó thuộc hard business requirement.

## 32. Lập kế hoạch nâng cấp từ nguồn chính thức

~~~mermaid
flowchart TD
    Inventory["Inventory versions + workload"] --> Lifecycle["Check EOL and advisories"]
    Lifecycle --> Compat["Compatibility intersection"]
    Compat --> Release["Release notes + upgrade restrictions"]
    Release --> Staging["Stage on production-like topology"]
    Staging --> Tests["Functional + concurrency + load + fault tests"]
    Tests --> Gate{"GO/NO-GO"}
    Gate -->|"NO-GO"| Fix["Change plan/version, retest"]
    Fix --> Compat
    Gate -->|"GO"| Rollout["Backup + controlled rollout"]
    Rollout --> Monitor["Monitor + burn-in + FCV decision"]
    Monitor --> ADR["Record result, update matrix"]
~~~

Các bước này là khung ra quyết định. Trình tự nâng nodes/routers/FCV phải làm **theo upgrade guide riêng của version và topology**, không theo sơ đồ khái quát.

### 32.1. Trước upgrade

- Ghi baseline server binary/FCV, driver, runtime, framework, topology.
- Tìm support lifecycle/EOL/security advisories.
- Chọn target versions dựa trên availability và upgrade paths.
- Đọc tất cả breaking/deprecation/behavior changes giữa hai mốc.
- Lập cặp phiên bản driver có thể hoạt động trong **giai đoạn chuyển tiếp**.
- Lập backup/restore, rollback window và người phê duyệt.

### 32.2. Staging

- Clone schema/indexes, dữ liệu đã ẩn danh hoặc data distributions tương đương.
- Test authentication/TLS, CRUD, aggregation, transactions, change streams.
- Test hot tenants, timeouts, retryable writes và failover.
- So query plans/`explain`, p95/p99, throughput, resource usage.
- Test application binary build, dependency lock và JDK/OS image mới.

### 32.3. Sau upgrade

- Xác minh mọi nodes/routers đúng binary versions và health.
- Kiểm tra app connection pools, server-selection errors, retries, slow queries.
- Giữ burn-in window nếu guide cho phép trước khi đổi FCV.
- Thay FCV chỉ sau approval và đọc downgrade limitations.
- Cập nhật compatibility evidence, runbooks, inventory và alert.

## 33. Không nâng tất cả lớp cùng lúc nếu không cần

Giả sử bạn muốn nâng Server, driver, Spring Data và JDK trong cùng một deployment. Nếu thất bại, nguyên nhân có thể đến từ bất kỳ lớp nào.

### 33.1. Cách giảm biến số

Tùy compatibility/support constraints, có thể nâng theo giai đoạn:

~~~text
Current Server + Current driver/framework/runtime
    ↓ driver/framework compatibility preparation
Current Server + New compatible driver
    ↓ Server binary upgrade per official procedure
New Server + New driver, previous FCV during burn-in if allowed
    ↓ FCV upgrade after validation
New Server + New FCV + New driver
    ↓ Optional framework/runtime upgrade in independent rollout
Target state
~~~

**Không** coi sơ đồ này là một upgrade order bắt buộc. Có driver/framework không hỗ trợ một server cũ, nên cần chọn intermediate versions hoặc đổi trình tự theo matrix.

### 33.2. Lợi ích của các giai đoạn

Giảm số variables trong troubleshooting, có thể rollback application layers dễ hơn và đo regression ở mỗi bước. Đổi lại, phải quản lý compatibility trong những trạng thái trung gian.

### 33.3. Khi nào bắt buộc upgrade đồng thời?

Nếu version driver mới không kết nối Server cũ hoặc framework mới yêu cầu JDK mới, cần phối hợp deployment. Không ép upgrade từng phần nếu tạo tổ hợp không supported.

## 34. Downgrade không phải “đổi binary ngược”

Một kế hoạch rollback phải xác định:

1. Có downgrade path được hỗ trợ cho version hiện tại không?
2. FCV đã nâng chưa, và có dữ liệu/feature không tương thích ngược không?
3. Sharded topology/metadata có thay đổi không?
4. Driver/framework mới có còn kết nối Server cũ không?
5. Có writes đã được xác nhận sau thời điểm backup không?
6. Restore/PITR có giữ được RPO theo business policy không?
7. External effects (payments/events) cần reconcile gì?

### 34.1. Rollback application khác downgrade database

Đưa ứng dụng về JAR cũ có thể thực hiện nhanh nếu driver/server vẫn tương thích. Hạ Server/FCV hoặc restore database có các preconditions nghiêm ngặt hơn; **không gộp** hai hành động thành một nút rollback.

### 34.2. Feature đã persist có thể chặn downgrade

Nếu một feature mới ghi data format cũ không đọc được, downgrade có thể bị từ chối hoặc đòi xử lý dữ liệu. Cần xem `Downgrade Limitations` của đúng release và có forward-fix option.

### 34.3. Không suy từ “FCV còn cũ” là downgrade 100% chắc chắn

FCV cũ giúp giữ một phần điều kiện tương thích, nhưng còn các yếu tố binary behavior, index/data corruption, support paths và operational steps. Bảo đảm rollback phải được kiểm thử theo guide.

## 35. Lập ma trận từ môi trường dev, staging, production

| Environment | Server binary | FCV | Driver resolved | Spring Data | Runtime | Notes |
|---|---|---|---|---|---|---|
| Dev | Ghi version thật | Ghi value thật | Lockfile/dependency tree | Actual artifact | JDK/Node | Local/containers |
| Staging | Ghi version thật | Ghi value thật | Deploy artifact | Actual artifact | Runtime image | Representative topology |
| Production | Ghi version thật | Ghi value thật | Deploy artifact | Actual artifact | Runtime image | Security/region/tier |

### 35.1. Tại sao dev pass nhưng prod fail?

Dev có standalone MongoDB mới; prod là sharded MongoDB cũ; driver ở dev được cập nhật bởi dependency range; staging dùng JDK 21 còn prod JDK 17; app đọc secondary ở prod hoặc Atlas tier chưa có feature. Bảng này giúp khoanh nguyên nhân nhanh.

### 35.2. Patch-level inventory

Không chỉ ghi Server 8.0; ghi `8.0.x` đúng patch trên từng member/cluster. Security fixes thường gắn với patch releases.

### 35.3. Mixed binary versions là trạng thái tạm

Khi rolling upgrade, ghi rõ thời gian chuyển tiếp và next steps. Đừng để dashboard inventory hiển thị hỗn hợp versions lâu mà không có owner.

## 36. Tìm “feature introduced in version” đúng cách

Giả sử một developer hỏi: “Có thể dùng aggregation stage X trên cluster này chưa?”.

1. Mở operator/stage reference từ Server Manual.
2. Tìm mục `Definition`, `Compatibility`, `New in version`, `Changed in version`.
3. Tra release notes của version giới thiệu.
4. Đọc restrictions: sharding, transaction, Atlas/self-managed, runtime, index.
5. Kiểm tra driver helper/API hỗ trợ stage; nếu không, quyết định theo compatibility policy.
6. Xác nhận Server binary, FCV, deployment type.
7. Chạy minimal query trong **test deployment** và integration tests.

### 36.1. Không tin autocomplete là chứng cứ

mongosh/Compass/IDE mới có thể gợi ý một stage mà server cũ không hiểu. Server là thành phần quyết định command có thực thi được không.

### 36.2. Raw command không bypass feature gates

Nếu driver thiếu builder method, gọi raw command không khiến Server cũ hỗ trợ syntax mới. Nếu Server hỗ trợ nhưng API chưa có, raw command vẫn phải tuân thủ security/support/compatibility policies và có tests.

## 37. Khi release note nói một tính năng “mới”

Phải đặt thêm:

- Mới ở **Server** hay mới ở **driver helper**?
- Mới cho **Atlas Search** hay Server core?
- Đã GA hay preview?
- Cần FCV/edition/tier/index feature khác?
- Có ở self-managed community không?
- Có deprecation hoặc changed semantics sau bản giới thiệu không?

Ví dụ “driver bổ sung builder cho aggregation stage” **không** làm Server cũ tự hiểu stage đó.

## 38. Tìm đúng trang cho backup/database tools

Khi đổi Server version nhưng vẫn chạy `mongodump`/`mongorestore` cũ:

1. Tra Database Tools release notes/compatibility cho tools đang cài.
2. Xem source và target server versions.
3. Kiểm tra dump format, metadata/index restoration và auth/TLS behavior.
4. Thử restore vào test cluster và so data/invariants.
5. Đảm bảo backup phù hợp RPO/RTO, không chỉ command exit 0.

### 38.1. Đừng nhầm export JSON/CSV với backup thay thế

`mongoexport`/`mongoimport` phục vụ luồng dữ liệu ứng dụng, không mặc nhiên bảo toàn mọi metadata/indexes/consistency tương tự giải pháp backup. Đọc docs đúng tool và mục đích.

### 38.2. Phân biệt tool binary và server binary

`mongodump --version` có thể khác `db.version()`; đó là bình thường. Chỉ cần tổ hợp được hỗ trợ/kiểm thử theo requirements của quá trình restore.

## 39. Tra cứu Spring Boot/Spring Data khi đổi driver

Đối với Spring:

1. Xác định Spring Boot version và dependency BOM.
2. Xác định Spring Data MongoDB artifact thực tế.
3. Mở [Spring Data MongoDB Requirements](https://docs.spring.io/spring-data/mongodb/reference/preface.html).
4. Ghi minimum Java driver và tested Server versions.
5. Kiểm tra MongoDB Java driver Server/JDK matrix.
6. Đọc Spring Data release notes/migration guide và driver upgrade guide.
7. Chạy repository, transaction, `@Version`/optimistic locking, custom converter, aggregation, bulk operations tests.

### 39.1. Không bỏ qua codec

Nếu đổi major Java driver và BSON codec versions, custom codecs/converters, UUID representations, Decimal128, ZonedDateTime serialization hoặc legacy class APIs có thể có behavior differences. Kiểm tra release notes + tests trên data thực.

### 39.2. Reactive và synchronous là hai sản phẩm integration khác nhau

MongoDB Java Sync Driver và Reactive Streams Driver có API/dependency khác nhau; Spring Data MongoDB reactive stack cần đúng driver và Spring integration. Không dùng bảng docs Java Sync để chứng minh mọi behavior của reactive stack.

## 40. Nghiên cứu bug: cách dựng chuỗi bằng chứng

Giả sử ứng dụng báo lỗi authentication sau Server upgrade:

~~~text
Observed:
  MongoDB Server old -> new
  Java driver old (unchanged)
  Error: handshake/authentication failure
~~~

Hướng tra:

1. Ghi exact versions/patches, auth mechanism, OS/JDK và deployment type.
2. Mở driver–Server matrix, xem footnotes về authentication.
3. Mở driver Upgrade Versions/release notes và Server release notes.
4. Xem issue advisory/changelog nếu có.
5. Tái hiện trên test deployment với driver/server matrix tương ứng.
6. Nâng driver theo supported path hoặc thay auth config dựa trên official docs.
7. Ghi root cause và regression test.

### 40.1. Không đoán chỉ từ một stack trace

Một exception kết nối có thể do TLS certificate, DNS/SRV, network ACL, auth mechanism, expired credentials hoặc driver–server mismatch. Dùng triệu chứng + environment inventory + vendor evidence.

### 40.2. Đừng chia sẻ connection string có mật khẩu

Khi lưu ticket/log, che username/password, tokens, hosts nội bộ nếu chính sách yêu cầu, customer IDs và PII; có thể để sanitized topology/port/driver metadata.

## 41. Tình huống A: nâng Server nhưng giữ Java driver cũ

Giả định một ứng dụng đang chạy:

~~~text
Server: 8.0.x
Java Sync Driver: 5.10.x
Java runtime: JDK 17
Framework: có hoặc không có Spring Data
Mục tiêu: đánh giá chuyển sang Server 9.0.x
~~~

Từ bảng compatibility ghi nhận tại ngày tham khảo, Java Driver 5.10 với Server 9.0 có ký hiệu **⊛** (partially compatible), trong khi 5.12–5.13 được đánh dấu ✓ ở cột 9.0. Đây không phải lệnh “phải nâng lên 5.13”; nó là tín hiệu cần xác định chức năng mới nào driver 5.10 chưa hỗ trợ và xem version driver/Server availability thực tế.

### 41.1. Cần hỏi tiếp

- Ứng dụng chỉ CRUD cũ hay cần tính năng mới của Server 9.0?
- Server 9.0 đã khả dụng cho tier/edition hiện tại chưa?
- Driver mới có hỗ trợ JDK 17 và Spring Data/BOM hiện hành không?
- Có auth/TLS changes, deprecations hoặc security issues nào?
- Rollback Server/FCV có được phép sau khi bắt đầu dùng feature mới không?

### 41.2. Kết luận mẫu

~~~text
Status: PASS_WITH_CONDITIONS hoặc NEEDS_TEST
Reason: driver/server partially compatible for some features
Actions: inventory commands, read driver notes, test targeted features,
         validate deployment availability, create upgrade rollback plan
~~~

Không ghi PASS chỉ vì một phép `db.runCommand({ping:1})` đã thành công.

## 42. Tình huống B: Spring Data test matrix chưa ghi Server mới

Giả định Spring Data MongoDB version của project có bảng tested database generations `6.x–8.x`, còn Server mục tiêu là 9.0.

### 42.1. Diễn giải đúng

“Tested 6.x–8.x” không phải tuyên bố “9.0 chắc chắn lỗi”. Nó có nghĩa **không được dùng hàng đó để khẳng định Spring Data đã test 9.0**. Cần đọc Spring Data release/upgrade docs, driver matrix và chạy application integration tests.

### 42.2. Không bỏ qua những thứ framework tự làm

Framework có thể phát các commands, dùng codecs, change streams, transactions hoặc indexes thay người viết app. Test toàn bộ paths:

- `MongoRepository`/`MongoTemplate` CRUD.
- Mapping/migration của `@Version` và `@Id`.
- Custom conversions và BSON types.
- Aggregation pipelines/sort/pagination.
- Reactive repositories nếu sử dụng.
- Transactions, sessions, retry behavior và idempotency.

### 42.3. Decision

Không tự gắn ✓ cho Spring Data–Server khi chưa có nguồn/test. Ghi `NEEDS_TEST` hoặc `UNKNOWN` với owner và ngày xác minh; nếu vendor support policy không đáp ứng business requirement, đó có thể là NO-GO.

## 43. Tình huống C: code mới dùng tính năng Server chưa có

Giả sử ứng dụng thấy một bài hướng dẫn về stage aggregation mới và thêm ngay vào production pipeline, nhưng Server đang ở version cũ.

### 43.1. Chuỗi tra cứu

1. Lấy **tên stage/operator chính xác**.
2. Mở Server Manual đúng version.
3. Đọc New in version/Compatibility.
4. Xác định Atlas/self-managed availability và FCV requirements nếu có.
5. Kiểm tra Java driver builder hoặc raw command API version.
6. Test trên staging với server/driver combo sản phẩm.

### 43.2. Không coi IDE autocomplete là nguồn

Driver/Compass mới có thể biết cú pháp mà server cũ không hỗ trợ. Autocomplete là chức năng client, không phải bằng chứng Server đã triển khai tính năng.

### 43.3. Nếu chưa đủ điều kiện

Chọn nâng cấp deployment theo guide, triển khai giải pháp tương thích hiện tại hoặc hoãn feature. Không tự cố gửi lệnh bằng raw BSON để vượt một hạn chế phiên bản.

## 44. Tình huống D: release note có cảnh báo security

Giả định một release note có mục `Important`, ghi một CVE và ảnh hưởng tới driver versions trong một khoảng.

### 44.1. Trình tự xử lý

1. Ghi chính xác component (Java Driver, Server, Compass, mongosh, tools).
2. Kiểm tra exact resolved version trên deployment, không dùng version range từ build file.
3. Đọc affected version ranges và fixed releases.
4. Kiểm tra có backport cho release line đang dùng không.
5. Đánh giá exposure thực: driver auth feature nào đang bật, log chứa dữ liệu gì.
6. Chọn patch supported; xem compatibility matrix và upgrade guide.
7. Test auth, TLS, connection pool, codecs và chức năng quan trọng.
8. Rollout theo quy trình security, theo dõi và ghi remediation evidence.

### 44.2. Không “nâng server” để chữa mọi CVE

Nếu lỗ hổng nằm trong driver logging code, thay server có thể không sửa. Ngược lại, Server storage bug không được sửa chỉ bằng nâng Compass. Đối chiếu component trước khi hành động.

## 45. Tình huống E: production 8.0 nhưng tài liệu current đã là 9.0

Developer search thấy snippet từ trang mới nhất và thêm option không tồn tại ở 8.0.

### 45.1. Cách phòng ngừa

- Ghi Server exact version và FCV.
- Dùng version selector trong Manual hoặc dẫn đúng version release notes.
- Tìm “Changed in version” cho option đang định dùng.
- Chạy thử trên test deployment cùng version/topology.
- Gắn comment/reference URL có version vào ADR/PR nếu behavior phụ thuộc release.

### 45.2. Không lưu mọi URL như chân lý bất biến

Link có `current` có thể trỏ phiên bản mới hơn sau vài tháng. Với quyết định lâu dài, ghi **source title, section, ngày tra cứu, version selector**; có thể dùng permalink/versioned archived page khi official site cung cấp.

## 46. Tình huống F: Atlas nâng tự động

Một cluster Atlas thuộc chính sách auto-upgrade có thể nhận server binary/features theo rollout của Atlas. Các khu vực/tier có thể không cùng mốc.

### 46.1. Cần theo dõi

1. [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/).
2. [Atlas Changelog](https://www.mongodb.com/docs/atlas/release-notes/changelog/).
3. Release notes của Server series đang được rollout.
4. Driver compatibility và App dependency inventory.
5. Maintenance window/notifications/chính sách FCV tương ứng.
6. Application canary/tests trong cluster type đại diện.

### 46.2. Không tự giả định quyền kiểm soát

Một hướng dẫn self-managed có thể yêu cầu thao tác FCV hoặc restart `mongod` mà Atlas không cho phép/không cần người dùng thực hiện. Tìm tài liệu Atlas-specific trước khi lập runbook.

## 47. Mẫu hồ sơ bằng chứng tương thích

Một YAML **mẫu điền thủ công**, không phải configuration để chạy:

~~~yaml
compatibilityReview:
  reviewId: "mongo-upgrade-2026-11-sample"
  asOf: "2026-11-14"
  owner: "<team-or-person>"
  purpose: "MongoDB Server upgrade"
  current:
    server: "<exact-version>"
    fcv: "<actual-fcv>"
    deployment: "<Atlas or self-managed, topology and tier>"
    driver: "<resolved-version>"
    framework: "<resolved-spring-data-version>"
    runtime: "<jdk-or-node-version>"
  proposed:
    server: "<target-version>"
    driver: "<target-version>"
    fcv: "<planned-fcv-if-any>"
  evidence:
    serverReleaseNotes: "https://www.mongodb.com/docs/manual/release-notes/"
    driverCompatibility: "https://www.mongodb.com/docs/drivers/compatibility/"
    springRequirements: "https://docs.spring.io/spring-data/mongodb/reference/preface.html"
    lifecycle: "https://www.mongodb.com/legal/support-policy/lifecycles"
  checks:
    driverServer: "UNKNOWN"
    runtimeDriver: "UNKNOWN"
    frameworkDriver: "UNKNOWN"
    featureAvailability: "UNKNOWN"
    securitySupport: "UNKNOWN"
    rollbackReadiness: "UNKNOWN"
  tests:
    connectivity: "NOT_RUN"
    crud: "NOT_RUN"
    transactions: "NOT_RUN"
    aggregation: "NOT_RUN"
    failover: "NOT_RUN"
    backupRestore: "NOT_RUN"
  decision: "NO_GO_UNTIL_VERIFIED"
~~~

### 47.1. Vì sao không tự fill PASS?

Mẫu chưa biết deployment thật, nên mọi ô còn `UNKNOWN`/`NOT_RUN`. Một hồ sơ review đúng cần phơi bày phần chưa rõ để con người không nhầm với chứng nhận tương thích.

### 47.2. Ghi URL tới section/version cụ thể

Ở dự án thật, thay link tới trang landing bằng link sâu tới version/section hỗ trợ claim, kèm ngày truy cập và đoạn footnote được diễn giải. Nếu source page cập nhật, người review có thể theo dõi lịch sử quyết định.

### 47.3. Evidence matrix không cần kết nối production

Có thể dựng bảng từ repository lockfiles và một inventory đã được cung cấp, không yêu cầu cấp credentials production cho người viết tài liệu. Nếu cần đọc runtime, dùng quyền read-only theo policy và không đưa secrets vào artifact.

## 48. Mẫu bảng dạng Markdown cho pull request

| Check | Current | Proposed | Official source | Evidence date | Test | Decision |
|---|---|---|---|---|---|---|
| Server EOL | TBD | TBD | Lifecycle | TBD | N/A | UNKNOWN |
| Server release | TBD | TBD | Server notes | TBD | Staging | NEEDS_TEST |
| Driver–Server | TBD | TBD | Client matrix | TBD | Connection+CRUD | UNKNOWN |
| Driver–JDK | TBD | TBD | Java compatibility | TBD | Build/smoke | UNKNOWN |
| Spring Data–driver | TBD | TBD | Spring requirements | TBD | Repository tests | UNKNOWN |
| FCV/rollback | TBD | TBD | FCV/upgrade guide | TBD | Drill | UNKNOWN |
| Atlas availability | TBD | TBD | Atlas versions | TBD | Tier check | UNKNOWN |
| Business features | TBD | TBD | Feature reference | TBD | Integration | UNKNOWN |

Reviewers có thể comment trực tiếp từng hàng, nêu missing evidence và owner. Bảng phải đi cùng release notes delta, test plan, rollback decision và approval records.

## 49. Quy trình tra cứu trong 15 phút đầu khi có lỗi

~~~text
0–3 phút:
  Xác định component, error, exact versions, deployment.
3–6 phút:
  Mở official reference và version selector.
6–9 phút:
  Mở compatibility matrix + footnotes + lifecycle.
9–12 phút:
  Mở release notes / changelog / known issues.
12–15 phút:
  Ghi 2–3 giả thuyết và test tối thiểu an toàn trên staging.
~~~

Đây là **workflow gợi ý**, không phải SLA cố định. Một sự cố production nghiêm trọng cần incident response và triage theo mức độ ảnh hưởng, không dừng ở việc đọc docs trong một khung thời gian cứng.

### 49.1. Trình tự câu hỏi

1. Có phải Server hỗ trợ command không?
2. Driver có xây/gửi command đó đúng không?
3. Framework mapping có thay đổi semantics không?
4. Runtime/TLS/auth có tương thích không?
5. FCV/feature availability đã đạt chưa?
6. Topology có hạn chế gì?
7. Đây có phải bug đã được patch/advisory ghi nhận không?

## 50. Dùng tài liệu chính thức cùng AI một cách an toàn

AI/chatbot và search snippets giúp tìm hướng nhưng có thể trộn versions, cắt mất footnotes hoặc dùng link đã đổi.

### 50.1. Đặt câu hỏi có ngữ cảnh

Thay vì:

~~~text
MongoDB version nào hỗ trợ transaction?
~~~

Hãy hỏi:

~~~text
MongoDB Server 8.0.x Community replica set, FCV 8.0,
Java driver 5.x, JDK 17: multi-document transactions
có constraints nào, official docs và compatibility links?
~~~

### 50.2. Yêu cầu nguồn và phạm vi

Một câu trả lời đáng tin cần chỉ ra **tên tài liệu, version, deployment type, caveats, ngày xác minh**. Nếu AI nêu compatibility cells mà không có nguồn chính thức, phải mở bảng gốc.

### 50.3. Kiểm tra URL trước khi dùng

Liên kết do AI đề xuất có thể 404 hoặc dẫn `current` khác version. Dùng docs navigation/official search để xác thực; đừng copy command quản trị có khả năng phá dữ liệu chỉ vì nó “được trích nguồn”.

## 51. Những bẫy tìm kiếm thường gặp

| Bẫy | Vì sao sai | Sửa như thế nào |
|---|---|---|
| Dùng top Google result không xem date | Bài rất cũ | Tìm official versioned docs |
| Tài liệu `current` cho production cũ | Option/behavior chưa tồn tại | Chọn version selector |
| Nhầm mongosh version với server | Hai products độc lập | `db.version()` hoặc buildInfo |
| Chỉ xem driver–Server | Bỏ JDK/ODM/Framework | Tra các chiều còn lại |
| Thấy dấu ⊛ coi là ✓ | Một số features chưa hỗ trợ | Đọc legend/footnotes |
| Ô trống coi là ✗ | Có thể chỉ chưa được test | Xác minh nguồn khác |
| Kết nối thành công coi là certified | CRUD mới thử, features chưa thử | Integration/load/fault tests |
| Không ghi patch | Bỏ lỡ security fixes | Exact version inventory |
| Không ghi FCV | Tính năng mới không bật | FCV read-only check |
| Bỏ deployment type | Atlas/self-managed khác nhau | Atlas/platform docs |
| Bỏ EOL | Dùng software không nhận fixes | Lifecycle schedule |
| Chỉ đọc release headline | Bỏ breaking changes/critical advisory | Changelog, upgrade guide |
| Copy lệnh set FCV từ blog | Rủi ro downgrade/data | Versioned official procedure |
| Không lưu nguồn/ngày | Không audit được quyết định | Evidence ledger |
| Đổi driver và server cùng lúc không test | Khó xác định regression | Supported intermediate states |
| Chạy test trên standalone cho production sharded | Không đại diện topology | Production-like staging |
| “Có backup” coi là phục hồi được | Restore chưa được kiểm tra | Restore drill/RPO/RTO |

## 52. Bài thực hành A — tìm trang reference đúng version

Một application dùng Server 8.0.x cần tra `$lookup`. Hãy tìm:

1. Reference của `$lookup` trong Server Manual đúng version.
2. Mục `Compatibility` và `Behavior`.
3. Ghi restrictions khi foreign collection sharded.
4. Mở release notes để biết lịch sử thay đổi quan trọng.
5. Viết một câu kết luận có URL/version thay vì chỉ nói “được hỗ trợ”.

## 53. Bài thực hành B — Server và mongosh không cùng version

Trong terminal, `mongosh --version` in ra 2.x; `db.version()` in 8.0.x. Hãy giải thích tại sao không mâu thuẫn, muốn biết command có chạy được thì phải xem docs của thành phần nào, và nếu lỗi do shell UI thì mở release notes nào.

## 54. Bài thực hành C — đọc dấu compatibility

Một ô driver ↔ Server có dấu ⊛; một ô khác trống. Hãy mô tả:

- Điều nào được khẳng định?
- Điều nào **chưa** được khẳng định?
- Có nên GO production nếu app cần feature mới trong cột ⊛ không?
- Bằng chứng và test nào cần bổ sung?

## 55. Bài thực hành D — Spring Data BOM

Project có `spring-boot-starter-data-mongodb` nhưng không khai version `mongodb-driver-sync`. Hãy liệt kê cách tìm Spring Boot BOM, Spring Data module và MongoDB driver versions đã resolve. Sau đó tra minimum driver version và MongoDB tested generations của Spring Data.

## 56. Bài thực hành E — Server version và FCV

Một cluster có binaries mới nhưng FCV vẫn ở version trước theo upgrade path. Tại sao đây là hai thông tin khác nhau? Vì sao không bật FCV mới trước khi burn-in/downgrade review? Nêu lệnh **chỉ đọc** để xem FCV.

## 57. Bài thực hành F — release notes major/patch

Giả sử muốn nâng từ Server `A.B.3` tới `A.B.8`. Hãy thiết kế bảng đọc mọi patches trong khoảng, với cột CVE/advisory, affected features, fixed issues, operational action và test.

## 58. Bài thực hành G — Atlas vs self-managed

Một tutorial Atlas mô tả tính năng mới trong một tier cụ thể. Ứng dụng của bạn chạy MongoDB Community self-managed. Có được áp dụng cùng API không? Hãy liệt kê nguồn cần xác minh, deployment constraints và phương án nếu tính năng không khả dụng.

## 59. Bài thực hành H — driver compatibility ba chiều

Project Java có Server phiên bản S, driver D và JDK 17. Hãy tự tạo bảng ba chiều với links tới Java driver Server compatibility, Java runtime compatibility và Spring Data requirements nếu framework được dùng. Thế nào là trạng thái UNKNOWN cần dừng?

## 60. Bài thực hành I — EOL risk

Một server vẫn chạy tốt nhưng đã qua EOL. Kỹ sư nói “không có lỗi nên chưa cần nâng”. Hãy giải thích khác biệt technical compatibility và support lifecycle; ghi những evidence cần có để quyết định thay thế và khoảng thời gian remediation.

## 61. Bài thực hành J — login/TLS failure sau upgrade

Sau khi nâng server, một ứng dụng driver cũ không còn kết nối, logs báo authentication handshake issue. Hãy xây trình tự tra official matrix footnotes, driver upgrade guide, release notes, auth/TLS reference và thiết kế regression test.

## 62. Bài thực hành K — Stable API

Một nhóm cho rằng bật Stable API v1 nghĩa là mọi aggregation stage và mọi driver version đều backward compatible mãi mãi. Hãy chỉ ra các phần của tuyên bố sai, và các trang tài liệu cần đọc để xác minh covered commands/options.

## 63. Bài thực hành L — ma trận nâng cấp

Xây một bảng có các hàng Server, FCV, driver, JDK, Spring Data, topology, Atlas tier, Database Tools, mongosh và critical features. Điền các cột current, proposed, official URL, verified date, vendor support, test result, status và reviewer.

## 64. Bài thực hành M — điểm dừng rollback

Ứng dụng đã nâng Server và bật một persisted feature mới qua FCV, sau đó muốn hạ server. Vì sao “thay binary ngược” không đủ? Hãy thiết kế rollback/forward-fix decision có thông tin về compatibility, data format, backups và RPO/RTO.

## 65. Bài thực hành N — tra một lỗi từ changelog

Bạn nhận một issue ID `SERVER-XXXXX` hoặc `JAVA-YYYYY` từ logs/changelog. Hãy lập hồ sơ:

~~~text
Issue ID:
Product/component:
Affected versions:
Fixed versions/backports:
Our exact version:
Prerequisites to reproduce:
Workaround:
Official release notes link:
Integration test:
Owner + decision:
~~~

Không tự gán issue ID hư cấu cho một bug thật; đây là form thực hành.

## 66. Bài thực hành O — chuẩn bị nâng production

Thiết kế GO/NO-GO review có:

- Exact version inventory.
- Compatibility intersection + footnotes.
- Security/EOL review.
- Upgrade/downgrade procedures.
- Production-like staging tests.
- Query/transaction/change-stream regression.
- Backup/restore and RPO/RTO.
- Canary/monitoring/rollback owner.

Một nhóm chưa có restore drill và chưa kiểm tra Spring Data/driver compatibility có được GO không?

## 67. Gợi ý đáp án bài thực hành

**A — Reference đúng version:** mở MongoDB Server Manual của đúng Server series, tìm `$lookup`, đọc behavior/compatibility/sharding restrictions và release notes cho thay đổi được nêu. Kết luận có nguồn/phiên bản, không chỉ trích snippet ở docs `current`.

**B — mongosh khác Server:** hai thành phần có version riêng. `mongosh --version` cho shell, `db.version()` cho server đang kết nối. Feature chạy được hay không phụ thuộc Server/FCV/deployment; UI/tool bug cần tra mongosh/Compass release notes tương ứng.

**C — Ký hiệu:** ⊛ là partially compatible theo phạm vi nhà cung cấp; ô trống không phải chứng nhận cũng không tự là incompatible. Với feature mới, phải xem limitations và upgrade/test plan, không GO chỉ vì connection ping pass.

**D — Dependency resolution:** dùng `gradle dependencies`/`dependencyInsight` hoặc Maven `dependency:tree`, xem Spring Boot BOM và Spring Data artifacts. Sau đó tra Spring Data Requirements, Driver–Server và Driver–JDK compatibility, không tự tin vào version ghi miệng.

**E — FCV:** binary xác định code Server đang chạy; FCV liên quan tính năng persist có tương thích ngược hay không. Đọc bằng `db.adminCommand({getParameter:1,featureCompatibilityVersion:1})` trên endpoint phù hợp, không chạy set FCV thiếu runbook.

**F — Patch range:** mỗi patch cần một hàng: number/date, CVE/advisory, affected versions, fixed issues, affected commands, action, regression test. Đọc official series changelog và upgrade notes, không chỉ bản cuối.

**G — Atlas vs self-managed:** không suy availability từ tutorial Atlas. Mở Atlas product/tier docs và Server manual/release notes; nếu Community không hỗ trợ, chọn managed deployment hoặc feature alternative theo business requirements.

**H — Ba chiều:** driver–server, driver–JDK và Spring Data–driver/framework đều phải có evidence. UNKNOWN xuất hiện khi một hard feature combo không có vendor support/test, chưa biết runtime version hoặc còn footnote chưa giải thích.

**I — EOL:** binary có thể vẫn chạy nhưng không còn fixes/security support. Ghi lifecycle source/date, exposure, path nâng, support contract, backup/rollback và deadline; không lấy “không có bug thấy được” làm lý do đủ.

**J — Auth failure:** lấy exact server/driver versions, auth mechanism, TLS/JDK, topology. Tra matrix notes, driver upgrade guide, Server changelog; tái hiện trong staging và chọn bản driver/Server được xác nhận hỗ trợ.

**K — Stable API:** chỉ bảo vệ subset commands/options được versioned API định nghĩa. Không thay mọi breaking change trong driver/runtime/framework và không đảm bảo features ngoài coverage; kiểm tra official Stable API reference và driver configuration.

**L — Ma trận:** mỗi component có current/proposed/exact patch, URL, verified date, compatibility statement, tests và decision. Thiếu thông tin ở hard gate thì NO-GO hoặc NEEDS_TEST, không tự đánh PASS.

**M — Rollback:** FCV/feature mới có thể persist data incompatible với version trước; phải đọc supported downgrade path, kiểm tra data/index changes và backups/RPO. Khi không thể downgrade an toàn, cân nhắc forward-fix hoặc recovery được phê duyệt.

**N — Issue:** ghi issue ID/component, affected/fixed versions, test conditions, link official notes, workaround và owner. Không đánh dấu patched nếu chỉ thấy fix trên release line khác.

**O — Production GO:** nếu chưa xác minh critical compatibility, chưa có restore drill hoặc chưa chứng minh rollback theo RPO/RTO, trạng thái phù hợp là **NO-GO/CONDITIONAL**, tùy policy và business requirements; phải hoàn tất bằng chứng trước khi triển khai.

## 68. Câu hỏi ôn tập

**1. Vì sao một bài blog không đủ làm nguồn quyết định nâng cấp?** — Có thể dùng version cũ, thiếu restrictions và không được cập nhật theo support policy.

**2. Vì sao phải xác định Server và driver versions riêng?** — Chúng có release cycles và compatibility constraints độc lập.

**3. Phiên bản mongosh phản ánh version Server?** — Không.

**4. `current` trong URL tài liệu nghĩa là gì?** — Thường là nhánh tài liệu hiện hành của sản phẩm đó, không nhất thiết phiên bản app đang chạy.

**5. Đâu là điểm bắt đầu cho MongoDB Server release notes?** — https://www.mongodb.com/docs/manual/release-notes/

**6. Đâu là điểm bắt đầu cho Client Library Compatibility Tables?** — https://www.mongodb.com/docs/drivers/compatibility/

**7. Changelog khác release notes?** — Changelog thường chi tiết từng issue; release notes tóm tắt thay đổi/patch và cảnh báo theo release.

**8. Compatibility table dấu ✓ có đảm bảo app luôn chạy đúng không?** — Không, còn topology, feature use, framework, runtime và integration tests.

**9. Dấu ⊛ được hiểu thế nào?** — Partially compatible theo chú giải của nhà cung cấp.

**10. Ô trống có tự đồng nghĩa không tương thích?** — Không; có thể chưa test/không được đánh dấu.

**11. Version cũ EOL có thể vẫn connect được?** — Có, nhưng compatibility kỹ thuật khác support/security lifecycle.

**12. FCV có giống Server binary version?** — Không.

**13. Thay FCV có thể ảnh hưởng downgrade?** — Có, nhất là với persisted incompatible features.

**14. Driver Java có thể yêu cầu runtime JDK tối thiểu?** — Có; tra Java compatibility chart.

**15. Spring Data yêu cầu driver tối thiểu có tự chứng minh mọi Server mới?** — Không; cần nhìn tested versions và driver–Server matrix.

**16. Stable API bao phủ mọi command mới?** — Không, chỉ subset được định nghĩa.

**17. Trang Atlas release notes có thể thay Server Manual không?** — Không, hai nguồn có scope khác nhau.

**18. Compass mới có thể kết nối Server cũ không?** — Phải tra compatibility/tool docs; GUI version khác Server.

**19. Khi nào cần xem exact patch chứ không chỉ major?** — Security, bug fixes, advisory, regressions và upgrade planning.

**20. Test ping thành công có chứng minh transaction hỗ trợ?** — Không; topology/feature/driver compatibility và transaction tests vẫn cần.

**21. Có thể nâng driver bất kỳ lên version mới nhất để sửa Server cũ?** — Không; driver mới có thể bỏ hỗ trợ Server EOL.

**22. “Tested by Spring Data” khác “Supported by MongoDB driver”?** — Có, là các phạm vi xác nhận khác nhau.

**23. Vì sao phải mở footnotes compatibility table?** — Có thể chứa exceptions hoặc điều kiện giới hạn quan trọng.

**24. Bản patch mới có thể mang breaking/behavioral changes không?** — Có thể thay đổi hành vi hoặc thêm restrictions/advisories; phải đọc notes.

**25. Nên lưu gì trong upgrade ticket?** — Exact versions, evidence URLs/dates, compatibility status, test results, runbook, owner và rollback.

**26. Vì sao cần production-like staging?** — Test đúng topology, traffic, TLS, FCV, data distribution và framework integrations.

**27. Có backup nghĩa là khôi phục được trong RTO?** — Không; cần restore drill.

**28. Có nên set FCV thử trên production để xem lệnh hoạt động?** — Không; chỉ theo procedure, preflight, approval và backup/rollback plan.

**29. Vì sao theo dõi EOL định kỳ?** — Support and security policies thay đổi; một bản đang chạy có thể trở thành unsupported.

**30. Một compatibility decision tốt trả lời điều gì?** — Combination nào, theo evidence nào, lúc nào, tính năng nào được kiểm chứng và rủi ro nào còn mở.

## 69. Bảng tra cứu nhanh theo câu hỏi

| Bạn cần biết... | Mở nguồn chính |
|---|---|
| Lệnh operator có cú pháp gì? | Server Manual đúng version |
| Tính năng xuất hiện từ release nào? | Reference “New in version” + Server notes |
| Patch có fix bug/CVE? | Server/driver release notes + changelog |
| Java driver kết nối Server nào? | Client Library Compatibility Tables |
| Java driver chạy JDK nào? | Driver Java Compatibility |
| Spring Data cần driver gì? | Spring Data MongoDB Requirements |
| Spring Data đã test Server nào? | Spring Data Compatibility Matrix |
| Atlas tier có feature chưa? | Atlas Docs + Atlas Versions/Changelog |
| FCV hiện là gì? | Read-only getParameter trên mongod |
| Có thể downgrade sau upgrade? | Upgrade/Downgrade docs + FCV reference |
| Version còn supported/EOL? | Software Lifecycle Schedules |
| Công cụ Compass có lỗi đã sửa? | Compass Release Notes |
| mongodump/restore có phù hợp? | Database Tools docs/release notes |
| Tại sao app vẫn lỗi dù ✓? | Release notes, framework/runtime, topology + tests |
| Có nên bật Stable API? | Stable API reference và driver docs |

## 70. Checklist cho một người học hoặc kỹ sư trước khi dùng hướng dẫn

- [ ] Đã xác định đúng sản phẩm: Server/Atlas/driver/Spring Data/mongosh/tool?
- [ ] Đã ghi exact versions/patches trong môi trường đang chạy?
- [ ] Đã xác định self-managed/Atlas tier và topology?
- [ ] Đã xem version selector/breadcrumb thay vì mặc định `current`?
- [ ] Trang nguồn là official Manual/driver/framework documentation?
- [ ] Đã đọc Syntax/Behavior/Restrictions/Compatibility của lệnh?
- [ ] Đã kiểm tra `New in version`/`Changed in version`?
- [ ] Đã mở release notes và changelog cho version dự kiến nâng?
- [ ] Đã đọc Important/Warning/Critical Advisory/footnotes?
- [ ] Đã kiểm tra đúng table Driver–Server?
- [ ] Đã kiểm tra Driver–Runtime/JDK?
- [ ] Đã kiểm tra Spring Data/Spring Boot dependency resolved và requirements?
- [ ] Đã xác định FCV hiện tại và upgrade path tương ứng?
- [ ] Đã xem availability của feature trong Atlas/edition/tier?
- [ ] Đã tra Server/driver EOL và security advisories?
- [ ] Đã phân biệt ✓, ⊛, ✗ và ô trống?
- [ ] Tất cả hard compatibility gates có bằng chứng rõ?
- [ ] Mọi UNKNOWN/NEEDS_TEST có owner và kế hoạch đóng?
- [ ] Đã chạy integration tests trong môi trường đại diện?
- [ ] Đã thử concurrency, retry, failover, transactions nếu app dùng?
- [ ] Đã đo query plans/latency khi upgrade ảnh hưởng performance?
- [ ] Đã chuẩn bị backup, restore drill, rollback/FCV decision?
- [ ] Đã lưu URL, ngày kiểm tra, result và reviewer trong PR/ADR?

## 71. Checklist cho nhóm vận hành trước major upgrade

1. **Inventory:** Server binaries từng node/router, FCV, driver patch, runtime, framework, tools.
2. **Policy:** lifecycle, support contract, security advisories, platform support.
3. **Compatibility:** driver–Server, runtime, framework, features, topology, Atlas tier.
4. **Release delta:** mọi breaking changes, deprecations, default changes, bug/CVE fixes.
5. **Procedures:** supported upgrade order, prerequisites, FCV and downgrade constraints.
6. **Backups:** khả năng phục hồi và dữ liệu external reconciliation theo RPO/RTO.
7. **Tests:** unit/integration, query/aggregation, transactions, change streams, load, failover.
8. **Rollout:** maintenance window, staged clusters, canary, owner và monitoring.
9. **Gates:** định nghĩa GO/NO-GO, auto-pause, support escalation.
10. **Postflight:** xác minh health/version/FCV, metrics, business invariants, ADR, inventory update.

### 71.1. Những trường hợp nên dừng

- Có dấu ✗ ở tổ hợp bắt buộc.
- Không biết framework/driver resolved version trong production.
- Feature critical chưa có support/availability evidence.
- Có advisory nghiêm trọng chưa được xử lý.
- Không có rollback/restore phù hợp RPO/RTO.
- Staging không đại diện topology, hoặc kết quả test thất bại.

Nếu ràng buộc được phép thay đổi, cần review business/security/operations và cập nhật kế hoạch **trước** khi GO, không tự chuyển NO-GO thành PASS.

## 72. Nguyên tắc duy trì knowledge base lâu dài

Một tài liệu tra cứu nội bộ nên có:

~~~text
Title: MongoDB Compatibility Decision — Project X
Last verified: YYYY-MM-DD
Products: Server / Java Driver / Spring Data / Atlas
Current versions:
Proposed versions:
Deployment topology and FCV:
Features tested:
Official references:
Exceptions/footnotes:
Lifecycle/EOL:
Test evidence:
Decision and approver:
Next review date:
~~~

### 72.1. Tách thông tin bền vững và thông tin thay đổi

**Bền vững:** cách đọc compatibility, tư duy chia layer, quy trình lưu bằng chứng. **Thay đổi:** version mới nhất, EOL dates, driver compatibility cells, Server features, Atlas tier availability. Đưa thông tin động vào bảng có `last verified` và link gốc.

### 72.2. Không giữ ảnh chụp bảng như nguồn duy nhất

Ảnh screenshot cũ có thể không còn phản ánh support policy. Khi quyết định nâng cấp, mở link chính thức để kiểm tra lại.

### 72.3. Khuyến khích reproducibility

Lưu lockfiles, container image digest, MongoDB buildInfo/FCV read-only outputs đã redacted, scripts smoke test và official links. Khi có regression, đội ngũ sẽ biết **tổ hợp versions nào** đã được kiểm chứng.

## 73. Nguồn tham khảo chính thức được sử dụng

Những liên kết này là **bản đồ tra cứu**, không phải một bản snapshot chứng nhận tương thích của mọi version. Trước khi quyết định production, kiểm tra lại version selector, footnotes, release dates và ngày cập nhật.

1. [MongoDB Server Manual](https://www.mongodb.com/docs/manual/) — lệnh, operators, aggregation, sharding, replication và transactions.
2. [MongoDB Server Release Notes](https://www.mongodb.com/docs/manual/release-notes/) — release series, patch releases, critical advisories.
3. [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) — version cadence, deployment modes, FCV và đường nâng cấp.
4. [setFeatureCompatibilityVersion](https://www.mongodb.com/docs/manual/reference/command/setfeaturecompatibilityversion/) — FCV semantics, preconditions, cú pháp theo Server release.
5. [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/) — driver–Server và driver–runtime matrices.
6. [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — Java APIs và navigation.
7. [Java Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/) — thay đổi từng driver release.
8. [Upgrade Java Driver Versions](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/) — breaking changes và dropped server support.
9. [Stable API for Java](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/stable-api/) — scoped versioned API behavior.
10. [Spring Data MongoDB Requirements](https://docs.spring.io/spring-data/mongodb/reference/preface.html) — JDK/framework/driver và tested Server versions.
11. [MongoDB Atlas Docs](https://www.mongodb.com/docs/atlas/) — managed deployments.
12. [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/) — Atlas release choices/auto-upgrade semantics.
13. [Atlas Release Notes](https://www.mongodb.com/docs/atlas/release-notes/) — Atlas/cloud features và changelogs.
14. [Compass Release Notes](https://www.mongodb.com/docs/compass/release-notes/) — GUI changes và patches.
15. [MongoDB Software Lifecycle Schedules](https://www.mongodb.com/legal/support-policy/lifecycles) — EOL/support tables.
16. [MongoDB Software Support Policy](https://www.mongodb.com/legal/support-policy/software) — ý nghĩa chính sách hỗ trợ.

## 74. Kết luận

Tra cứu MongoDB đúng cách là một **kỹ năng kỹ thuật có thể lặp lại**, không phải việc tìm một snippet chạy được. Luôn xác định **sản phẩm, exact version, FCV, deployment topology, driver/runtime/framework và mục tiêu nghiệp vụ** trước khi mở tài liệu. Đọc reference đúng version để hiểu semantics, release notes/changelog để biết điều đã thay đổi, upgrade/downgrade guide để biết quy trình và compatibility matrix để xác minh các cặp phiên bản.

Đặc biệt, đừng nhầm **✓ tương thích** với **feature đã có**, **framework đã kiểm thử**, **version còn được hỗ trợ**, hoặc **ứng dụng đã được chứng minh đúng trong production**. Một quyết định nâng cấp cần đủ bằng chứng ở các lớp Driver–Server, Driver–Runtime, Framework–Driver, Server–FCV, deployment availability và lifecycle/security, rồi mới được kiểm chứng bằng staging, integration/fault tests, restore/rollback rehearsal.

Khi mỗi quyết định có **URL chính thức, phiên bản, ngày xác minh, kết quả test, owner và điều kiện GO/NO-GO**, nhóm sẽ tránh được các lỗi do tài liệu cũ, nâng cấp thiếu bước hoặc hiểu nhầm một bảng tương thích. Đó là nền tảng để ứng dụng MongoDB được phát triển và vận hành an toàn qua nhiều vòng phát hành phần mềm.
