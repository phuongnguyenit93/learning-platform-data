# Artifact

Trong quy trình xây dựng và triển khai phần mềm, **artifact** là sản phẩm được tạo ra từ source code, cấu hình, dependency và các bước build. Artifact có thể là file thực thi, thư viện, package, container image, bundle frontend, manifest triển khai, tài liệu được sinh tự động hoặc một gói dữ liệu khác mà hệ thống tiếp theo có thể sử dụng.

Với một DSL xây dựng và triển khai (*build and deployment DSL*), artifact là một khái niệm trung tâm. DSL mô tả source đầu vào, build engine thực hiện các task, sau đó tạo artifact có tên, loại, vị trí lưu trữ và metadata xác định. Các bước kiểm thử, ký số, publish và deploy có thể tham chiếu artifact đó.

Ví dụ:

~~~text
project "catalog-service" {
    source = "src/"

    target "java" {
        output = artifact("catalog-service.jar")
    }

    package "container" {
        from = artifact("catalog-service.jar")
        image = "registry.example.com/catalog-service"
        tag = project.version
    }
}
~~~

Đây là cú pháp minh họa. Ý tưởng chính là build engine tạo ra một sản phẩm có identity rõ ràng, sau đó các task khác dùng đúng sản phẩm đó. Artifact giúp tách kết quả build khỏi máy đã build và giúp kiểm thử, lưu trữ, chia sẻ, triển khai cũng như rollback có thể tái hiện.

## 1. Artifact là gì?

Artifact là một đầu ra có thể nhận diện được của một hoạt động build hoặc packaging. Artifact thường được lưu dưới dạng file, tập file, image hoặc đối tượng trong artifact repository.

Một artifact có thể là:

- File thực thi như executable hoặc binary.
- Thư viện như JAR, DLL, shared library hoặc package.
- Gói ứng dụng như ZIP, TAR, WAR hoặc package native.
- Container image.
- Frontend bundle gồm HTML, CSS, JavaScript và asset.
- Bộ manifest hoặc chart phục vụ triển khai.
- Tài liệu API, schema hoặc code được sinh tự động.
- Test report, coverage report hoặc SBOM.
- Gói plugin, extension hoặc module DSL.

Artifact không nhất thiết phải là thứ được deploy trực tiếp. Một test report cũng là artifact của task kiểm thử; một SBOM là artifact mô tả thành phần của phần mềm; một deployment package có thể chứa manifest và tham chiếu đến container image.

### 1.1. Source, build output và artifact

Ba khái niệm này liên quan nhưng không giống nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Source | Đầu vào mà người phát triển duy trì | File Java, DSL, TypeScript |
| Build output | Dữ liệu được tạo bởi một bước build | Class file, bundle, generated source |
| Artifact | Sản phẩm được định danh và quản lý để dùng tiếp | JAR đã đóng gói, image, package |

Một build output có thể là file trung gian và chưa được coi là artifact phát hành. Ví dụ, các file object trong thư mục tạm là output của compiler, còn binary được đóng gói, gắn metadata và lưu trong repository là artifact có thể phân phối.

### 1.2. Artifact và release

Artifact là sản phẩm kỹ thuật. Release là một đơn vị phát hành có ý nghĩa với người dùng hoặc vận hành. Một release có thể chứa nhiều artifact:

~~~text
Release 2.4.0
├── catalog-service.jar
├── catalog-worker.jar
├── catalog-web.tar.gz
├── container image
├── deployment manifest
└── SBOM
~~~

Release còn có thể kèm release notes, policy, migration script và thông tin tương thích.

### 1.3. Artifact và deployment

Deployment là quá trình đưa một phiên bản ứng dụng hoặc cấu hình vào môi trường đích. Artifact là đầu vào của quá trình đó.

Ví dụ, cùng một container image có thể được deploy ở staging và production với các cấu hình môi trường khác nhau. Image mô tả phần mềm đã build; cấu hình triển khai xác định cách chạy phần mềm trong một môi trường cụ thể.

## 2. Vai trò của artifact trong build pipeline

Một build pipeline thường chuyển source thành một hoặc nhiều artifact qua các bước:

~~~text
Source + Configuration + Dependencies
                  |
                  v
             Compile
                  |
                  v
              Package
                  |
                  v
              Artifact
                  |
          +-------+--------+
          |                |
          v                v
        Test             Scan
          |                |
          +-------+--------+
                  |
                  v
          Sign and Publish
                  |
                  v
               Deploy
~~~

Artifact là ranh giới rõ giữa giai đoạn tạo phần mềm và giai đoạn sử dụng phần mềm. Khi artifact đã được tạo và định danh, các môi trường sau có thể dùng cùng một nội dung thay vì build lại từ source.

### 2.1. Tách build khỏi deploy

Build tập trung tạo sản phẩm. Deploy tập trung cấu hình và đưa sản phẩm vào môi trường.

Tách hai giai đoạn giúp:

- Kiểm thử đúng binary sẽ được phát hành.
- Không phụ thuộc compiler hoặc toolchain trên máy production.
- Dùng cùng artifact cho staging và production.
- Dễ rollback về artifact đã biết.
- Quản lý quyền build và quyền deploy riêng.

### 2.2. Artifact là đầu ra của task

Trong build graph, một task có thể tạo artifact và task khác phụ thuộc vào artifact đó:

~~~text
compile
   |
   v
package-jar
   |
   +----> test-package
   |
   +----> build-image
              |
              v
          publish-image
              |
              v
            deploy
~~~

Build engine cần biết task nào tạo artifact, task nào tiêu thụ artifact và điều kiện để artifact được xem là hợp lệ.

### 2.3. Một task có thể tạo nhiều artifact

Một task packaging có thể tạo file archive, checksum và manifest:

~~~text
packageRelease
  outputs:
    - catalog-service.tar.gz
    - catalog-service.tar.gz.sha256
    - artifact-manifest.json
~~~

Các output có quan hệ với nhau và cần được ghi nhận trong metadata hoặc output collection.

## 3. Các loại artifact phổ biến

Loại artifact phụ thuộc ngôn ngữ, nền tảng và mục đích phân phối.

### 3.1. Binary và executable

Binary là file thực thi được tạo bởi compiler hoặc linker. Nó có thể phụ thuộc hệ điều hành, kiến trúc CPU, runtime hoặc thư viện native.

Ví dụ tên file:

~~~text
catalog-server
catalog-server.exe
libcatalog.so
catalog.dll
~~~

Artifact binary cần ghi target platform và kiến trúc để tránh phân phối nhầm cho môi trường không tương thích.

### 3.2. Library và package

Library được các ứng dụng hoặc module khác sử dụng. Package thường gồm binary, metadata, dependency declaration và tài nguyên cần thiết.

Ví dụ:

- JAR hoặc WAR trong hệ sinh thái Java.
- NuGet package trong .NET.
- Wheel hoặc source distribution trong Python.
- npm package trong JavaScript.
- Native package như DEB hoặc RPM.

### 3.3. Archive

Archive gom nhiều file thành một đối tượng:

~~~text
catalog-release/
├── bin/catalog
├── config/default.yml
├── lib/runtime.jar
└── README.txt
~~~

Archive có thể dùng để phân phối ứng dụng hoặc chuyển giao cho một hệ thống triển khai.

### 3.4. Container image

Container image đóng gói filesystem, application binary, runtime và metadata cần để tạo container.

~~~text
registry.example.com/catalog-service:2.4.0
~~~

Image có thể gồm nhiều layer. Tag thường dễ đọc nhưng có thể được di chuyển sang nội dung khác; digest mới là định danh nội dung cụ thể.

### 3.5. Frontend bundle

Frontend build có thể tạo:

~~~text
web-dist/
├── index.html
├── assets/
│   ├── app.8a21c.js
│   └── app.4c92d.css
└── favicon.ico
~~~

Bundle có thể được lưu trong archive hoặc publish trực tiếp lên static hosting.

### 3.6. Deployment artifact

Deployment artifact mô tả cách triển khai một hoặc nhiều sản phẩm:

- Kubernetes manifests.
- Helm chart.
- Terraform module hoặc plan.
- Deployment descriptor.
- Service definition.
- Environment template.

Deployment artifact có thể tham chiếu container image bằng digest thay vì chỉ bằng tag.

### 3.7. Documentation và report

Build pipeline có thể tạo tài liệu API, schema reference, test report, coverage report, license report và SBOM. Những file này là artifact vì chúng có nguồn gốc, version và vòng đời riêng.

## 4. Khai báo artifact trong DSL

DSL có thể cung cấp một construct để định nghĩa artifact, hoặc cho phép task khai báo output rồi build engine tự tạo artifact record.

Một cách khai báo khái niệm:

~~~text
artifact "server" {
    type = "java-archive"
    file = "build/libs/server.jar"
    version = project.version
    platform = "any"
}
~~~

Một cách khác là định nghĩa output trong task:

~~~text
task compileServer {
    inputs = files("src/main/")
    outputs = artifact("server-classes")
}

task packageServer {
    dependsOn = [compileServer]
    inputs = [artifact("server-classes")]
    outputs = artifact("server-jar")
}
~~~

### 4.1. Artifact identity

Artifact cần có định danh ổn định trong build graph. Identity có thể là tên logic, coordinates, URI hoặc một ID nội bộ.

Ví dụ:

~~~text
group = "com.example"
name = "catalog-service"
version = "2.4.0"
classifier = "sources"
extension = "jar"
~~~

Các trường này tạo thành coordinates để phân biệt artifact với các sản phẩm khác trong repository.

### 4.2. Artifact type

Type cho biết artifact là JAR, image, archive, package, report hay một định dạng riêng. Type giúp task consumer biết cách đọc hoặc xử lý artifact.

### 4.3. Output path

DSL cần quy định output path là tương đối với project root, build directory hay working directory. Output path cũng cần được kiểm soát để tránh ghi ra ngoài phạm vi cho phép.

### 4.4. Một artifact có nhiều file

Một artifact có thể là collection:

~~~text
artifact "web-bundle" {
    type = "directory"
    files = directory("build/web/")
}
~~~

Khi publish, collection có thể được đóng gói thành archive hoặc upload theo từng object. Cần xác định cách giữ cấu trúc thư mục và file permission.

### 4.5. Artifact declaration và generated output

Build engine có thể tạo output path tự động, nhưng DSL vẫn nên định nghĩa output logic. Khi path vật lý thay đổi, các task downstream không phải sửa mọi tham chiếu nếu chúng dùng artifact identity.

## 5. Artifact metadata

Metadata mô tả artifact và giúp hệ thống nhận diện, tìm kiếm, xác minh, triển khai hoặc phân tích nó.

| Trường | Ý nghĩa |
|---|---|
| Name | Tên artifact |
| Group/namespace | Nhóm hoặc tổ chức |
| Version | Phiên bản logic |
| Type | Loại artifact |
| Classifier | Biến thể, ví dụ sources hoặc javadoc |
| Extension | Định dạng file |
| Digest | Hash của nội dung |
| Size | Kích thước |
| Build ID | Lần build tạo artifact |
| Source revision | Commit hoặc revision nguồn |
| Created at | Thời điểm tạo |
| Builder | Công cụ hoặc pipeline tạo artifact |
| Target | OS, CPU, runtime hoặc platform |
| Dependencies | Thành phần phụ thuộc |

### 5.1. Metadata logic và metadata vật lý

Metadata logic mô tả tên, version, type và coordinates. Metadata vật lý mô tả path, size, digest, media type và storage location.

Không nên dùng một path tạm trên máy build làm identity duy nhất vì path đó có thể không tồn tại ở máy khác.

### 5.2. Metadata tự mô tả

Một artifact manifest có thể được lưu cạnh artifact:

~~~json
{
  "name": "catalog-service",
  "version": "2.4.0",
  "type": "java-archive",
  "file": "catalog-service.jar",
  "sha256": "4f2c...",
  "sourceRevision": "a81c92d",
  "buildId": "build-1842",
  "target": "java-21"
}
~~~

Manifest giúp hệ thống tiếp theo xác định sản phẩm và đối chiếu nội dung.

### 5.3. Metadata schema

Metadata cần có schema và version. Nếu mỗi pipeline tự thêm field không có quy ước, consumer sẽ khó hiểu hoặc xử lý sai. Có thể định nghĩa required fields, optional fields và extension namespace.

### 5.4. Metadata không thay thế nội dung

Một manifest có thể nói artifact version là 2.4.0, nhưng không chứng minh nội dung file thực sự tương ứng với version đó. Cần digest hoặc signature để xác minh nội dung.

## 6. Versioning và coordinates

Version giúp phân biệt các lần phát hành hoặc biến thể của artifact.

### 6.1. Version logic

Ví dụ:

~~~text
catalog-service:2.4.0
catalog-service:2.5.0-rc.1
catalog-service:2.5.0
~~~

Version có thể tuân theo Semantic Versioning hoặc quy tắc riêng của tổ chức. DSL cần xác định cách xử lý prerelease, build metadata và version range.

### 6.2. Coordinates

Một package repository thường định danh artifact bằng nhiều thành phần:

~~~text
group:name:version:classifier@extension
~~~

Ví dụ:

~~~text
com.example:catalog-service:2.4.0:sources@jar
~~~

Coordinates giúp phân biệt cùng tên nhưng khác group, version hoặc classifier.

### 6.3. Version và digest

Version trả lời “đây là release nào?” Digest trả lời “nội dung chính xác là gì?” Hai artifact có thể có cùng version string nhưng digest khác nhau nếu pipeline cho phép ghi đè hoặc build không tái lập.

### 6.4. Không ghi đè version đã publish

Artifact đã publish nên được xem là immutable. Nếu cần sửa, tạo version mới hoặc build ID mới. Ghi đè nội dung dưới cùng coordinates làm mất khả năng tin cậy của lịch sử và cache.

## 7. Digest và content-addressed artifact

Digest là hash được tính từ nội dung artifact, thường dùng SHA-256 hoặc thuật toán mạnh tương đương.

Ví dụ:

~~~text
sha256:4f2c9a...
~~~

### 7.1. Xác minh nội dung

Khi tải artifact, consumer tính lại digest và so sánh với digest đã công bố. Nếu khác nhau, artifact có thể bị hỏng, bị thay đổi hoặc tải nhầm.

### 7.2. Content-addressed storage

Trong content-addressed storage, nội dung được định danh bằng digest:

~~~text
objects/
└── sha256/
    └── 4f2c9a...
~~~

Hai build tạo nội dung byte-for-byte giống nhau có thể tham chiếu cùng object. Cách này hỗ trợ deduplication và cache.

### 7.3. Hash không chứng minh nguồn gốc

Digest chứng minh nội dung có khớp với digest được tham chiếu hay không. Nó không tự chứng minh ai tạo artifact hoặc artifact có được build từ source đáng tin cậy hay không. Muốn chứng minh nguồn gốc cần provenance và chữ ký đáng tin cậy.

### 7.4. Canonical representation

Nếu digest được tính trên manifest hoặc cấu trúc nhiều file, cần định nghĩa canonicalization: thứ tự file, encoding, path separator, metadata permission và cách xử lý timestamp. Nếu không, cùng nội dung logic có thể tạo hash khác nhau.

## 8. Tính bất biến của artifact

Artifact được publish nên bất biến. Một khi đã định danh và phân phối, nội dung không được thay đổi tại chỗ.

### 8.1. Lợi ích của immutability

- Mọi môi trường có thể dùng đúng một nội dung.
- Cache không bị stale do ghi đè.
- Rollback có thể trỏ về digest đã biết.
- Audit và provenance có thể xác định chính xác sản phẩm.
- Incident investigation có thể lấy lại đúng artifact lịch sử.

### 8.2. Mutable tag và immutable digest

Container tag như latest hoặc 2.4 có thể được cập nhật để trỏ sang image khác. Digest định danh chính xác image content.

~~~text
registry.example.com/catalog:2.4.0
registry.example.com/catalog@sha256:4f2c...
~~~

Tag thuận tiện cho con người; digest phù hợp để pin deployment và xác minh.

### 8.3. Không tái sử dụng coordinates

Nếu một artifact đã phát hành với 2.4.0, không nên upload nội dung mới dưới cùng coordinates. Cần phát hành version mới hoặc artifact identity mới.

### 8.4. Immutable storage

Repository có thể hỗ trợ policy cấm overwrite, retention lock hoặc object versioning. Build DSL và publish task cần tôn trọng policy đó.

## 9. Reproducible build

Reproducible build là khả năng tạo cùng một artifact từ cùng source và các điều kiện build đã xác định. Đây là nền tảng để kiểm chứng artifact và giảm sự phụ thuộc vào máy build.

### 9.1. Các yếu tố ảnh hưởng

Artifact có thể khác nhau do dependency version thay đổi, compiler hoặc plugin version khác, environment variable khác, timestamp được nhúng vào file, thứ tự file trong archive không ổn định, locale hoặc timezone khác, path tuyệt đối của workspace được nhúng vào output, random value hoặc network response, toolchain và platform khác.

### 9.2. Pin dependency

Không nên chỉ khai báo version range rộng cho build phát hành. Lockfile hoặc dependency lock giúp cố định chính xác dependency resolution.

~~~text
dependencies {
    library("com.example:core:2.1.4")
}

dependencyLocking {
    enabled = true
}
~~~

Cú pháp tùy DSL, nhưng mục tiêu là build sau dùng cùng dependency graph.

### 9.3. Pin toolchain

Compiler, linker, formatter, packager và plugin có thể ảnh hưởng byte output. Cần khai báo hoặc ghi nhận version của toolchain.

### 9.4. Hermetic build

Hermetic build hạn chế phụ thuộc không khai báo vào máy hoặc mạng. Input của task cần được xác định; tool không nên đọc file tùy ý ngoài build graph.

### 9.5. Deterministic packaging

Để archive tái lập, cần ổn định thứ tự file, timestamp, permission và compression settings. Một số format hỗ trợ normalized timestamp để tránh thời gian build làm thay đổi digest.

### 9.6. Kiểm chứng reproducibility

Có thể build hai lần trong môi trường độc lập rồi so sánh digest. Nếu digest khác, cần xác định nguồn khác biệt trước khi kết luận build không reproducible.

## 10. Dependency closure và self-contained artifact

Artifact có thể cần các dependency để chạy. Dependency closure là tập hợp đầy đủ thành phần cần thiết để tạo hoặc sử dụng artifact theo cách đã định nghĩa.

### 10.1. Thin artifact

Thin JAR hoặc package nhỏ có thể chỉ chứa code của ứng dụng và khai báo dependency bên ngoài. Runtime cần tải hoặc cung cấp dependency tương ứng.

### 10.2. Fat artifact

Fat JAR hoặc bundle có thể đóng gói nhiều dependency vào cùng một file. Cách này thuận tiện triển khai nhưng có thể làm tăng kích thước và gây xung đột tài nguyên.

### 10.3. Runtime dependency

Build dependency và runtime dependency khác nhau. Compiler plugin có thể cần trong build nhưng không cần trong production. Artifact metadata cần phân biệt scope.

### 10.4. Dependency graph

~~~text
catalog-service
├── catalog-domain
│   └── money-types
├── http-runtime
└── json-library
~~~

Dependency graph giúp xác định những package nào cần được resolve, package nào được đóng gói và package nào chỉ dùng trong build.

### 10.5. Dependency conflict

Hai dependency có thể yêu cầu các version khác nhau của cùng thư viện. Build system cần có resolution strategy và ghi lại kết quả cuối cùng trong metadata hoặc lockfile.

## 11. Packaging và cấu trúc artifact

Packaging biến build outputs thành sản phẩm có thể phân phối.

### 11.1. File layout

Một package cần cấu trúc dễ hiểu và ổn định:

~~~text
catalog-release/
├── bin/
├── lib/
├── config/
├── docs/
└── manifest.json
~~~

### 11.2. File permissions

Archive có thể mang permission và executable bit. Build cần đặt permission đúng cho script và binary, tránh để file cấu hình chứa secret có quyền đọc quá rộng.

### 11.3. Symbolic links

Nếu archive chứa symlink, extractor cần xử lý an toàn. Symlink trỏ ra ngoài thư mục giải nén có thể tạo path traversal.

### 11.4. Path traversal khi giải nén

Một archive không tin cậy có thể chứa path như ../../outside/file. Tool giải nén cần chuẩn hóa path và bảo đảm mọi file được ghi trong destination root.

### 11.5. Archive ordering và metadata

Thứ tự file, timestamp và owner metadata có thể làm thay đổi digest. Build reproducible cần chuẩn hóa các thuộc tính này.

### 11.6. Package manifest

Manifest có thể mô tả file, digest, version, license, target và entry point. Nó giúp installer hoặc deploy tool hiểu package mà không phải đoán từ tên file.

## 12. Artifact registry và repository

Artifact registry là nơi lưu và phân phối artifact. Repository có thể là package repository, container registry, object storage hoặc dịch vụ quản lý build artifact.

### 12.1. Coordinates và repository URL

Một artifact có thể được tham chiếu bằng coordinates hoặc URI:

~~~text
artifact("com.example:catalog-service:2.4.0")
~~~

Hoặc:

~~~text
oci://registry.example.com/catalog-service@sha256:4f2c...
~~~

### 12.2. Repository types

- Maven-compatible repository cho package Java.
- npm registry cho package JavaScript.
- NuGet feed cho .NET.
- Python package index.
- OCI registry cho container image và OCI artifact.
- Generic artifact store cho file archive và report.

### 12.3. Local repository và remote repository

Local repository hoặc cache giúp build nhanh và hỗ trợ offline. Remote repository chia sẻ artifact giữa nhóm và pipeline.

### 12.4. Repository configuration

DSL có thể khai báo repository:

~~~text
repositories {
    maven("https://repo.example.com/releases")
    oci("registry.example.com")
}
~~~

Credential cần được lấy từ secret store hoặc credential provider, không hardcode vào source DSL.

### 12.5. Repository trust

Không phải repository nào cũng đáng tin. Có thể cần allowlist, TLS, credential scope, package signature verification và kiểm tra namespace để tránh dependency confusion.

## 13. Publish artifact

Publish là đưa artifact vào repository để consumer khác có thể tải hoặc tham chiếu.

Một task publish có thể:

1. Xác định artifact và metadata.
2. Kiểm tra version và repository policy.
3. Tính digest.
4. Tạo hoặc đính kèm manifest.
5. Ký artifact hoặc attestation nếu policy yêu cầu.
6. Upload nội dung.
7. Xác minh upload.
8. Ghi publish event.

### 13.1. Publish không phải build

Build tạo nội dung. Publish phân phối nội dung đã tạo. Tách hai việc giúp build một lần, kiểm thử và phê duyệt, sau đó publish cùng artifact.

### 13.2. Publish idempotency

Nếu pipeline retry publish, cần xác định hành vi khi artifact đã tồn tại. Với immutable coordinates, cùng digest có thể được xác nhận là đã publish; digest khác phải gây conflict.

### 13.3. Partial publish

Release nhiều artifact có thể thất bại giữa chừng. Cần manifest release hoặc trạng thái transaction để consumer không hiểu nhầm một tập artifact chưa đầy đủ là release hoàn chỉnh.

### 13.4. Access control

Quyền upload, download, delete và promote nên được phân tách. Build job không nhất thiết có quyền xóa artifact đã phát hành.

## 14. Provenance và software supply chain

Provenance mô tả artifact được tạo ra như thế nào và từ những đầu vào nào.

Một provenance record có thể gồm source repository và revision, build definition hoặc pipeline revision, builder identity, build environment, dependency materials, build parameters, output artifact digest và thời điểm build.

### 14.1. Source revision

Ghi commit ID giúp liên kết artifact với source. Branch name một mình không đủ vì branch có thể di chuyển.

### 14.2. Builder identity

Builder identity cho biết pipeline hoặc service nào tạo artifact. Với build quan trọng, cần xác định builder đáng tin và quyền của builder.

### 14.3. Build attestation

Attestation là tuyên bố có cấu trúc về một artifact hoặc hoạt động build, có thể được ký để consumer xác minh nguồn gốc.

### 14.4. SBOM

SBOM (*Software Bill of Materials*) liệt kê các thành phần phần mềm trong artifact, ví dụ package, version, license và dependency relationship.

SBOM hỗ trợ tìm artifact có chứa thư viện bị ảnh hưởng bởi lỗ hổng, theo dõi license, hiểu dependency bắc cầu và hỗ trợ inventory khi có security advisory.

### 14.5. Vulnerability scanning

Scanner có thể phân tích package, binary hoặc image. Kết quả scan cũng có thể là artifact liên kết với digest của đối tượng được quét.

Khi artifact thay đổi digest, kết quả scan cũ không tự động chứng minh artifact mới an toàn.

## 15. Signing và xác minh artifact

Chữ ký số giúp consumer xác minh artifact hoặc attestation được tạo bởi một identity có quyền.

### 15.1. Sign

Quy trình ký có thể:

1. Tính digest artifact.
2. Tạo statement chứa digest và metadata.
3. Ký statement bằng key của builder hoặc release service.
4. Lưu chữ ký và certificate/reference tương ứng.

### 15.2. Verify

Consumer kiểm tra chữ ký có hợp lệ không, key hoặc certificate có thuộc identity được tin cậy không, chữ ký có còn hiệu lực theo policy không, digest trong statement có khớp artifact tải về không và provenance có đáp ứng yêu cầu builder/source không.

### 15.3. Signing key

Private key cần được bảo vệ trong KMS, HSM hoặc dịch vụ ký chuyên dụng. Không nên lưu private key trong repository hoặc build script.

### 15.4. Key rotation và revocation

Key có thể hết hạn, bị lộ hoặc bị thu hồi. Hệ thống cần quản lý lịch sử key để xác minh artifact cũ và xác định policy khi key bị compromise.

### 15.5. Signature không sửa artifact

Chữ ký thường được lưu như metadata hoặc một object liên kết. Không nên thay đổi byte của artifact sau khi tính digest và ký.

## 16. Artifact promotion giữa môi trường

Promotion là quá trình đưa cùng một artifact qua các giai đoạn như development, test, staging và production.

~~~text
Build once
   |
   v
Artifact A (digest X)
   |
   v
Development
   |
   v
Test and approval
   |
   v
Staging
   |
   v
Production
~~~

### 16.1. Build once, promote many

Một nguyên tắc phổ biến là build artifact một lần, sau đó promote cùng digest qua các môi trường. Nếu build lại cho production, sản phẩm có thể khác với sản phẩm đã kiểm thử ở staging.

### 16.2. Environment configuration

Endpoint, replica count, secret reference và feature flags thường là cấu hình triển khai, không nên nhúng trực tiếp vào artifact nếu chúng thay đổi theo môi trường.

### 16.3. Approval gate

Promotion có thể yêu cầu test pass, security scan, manual approval hoặc policy check. Approval nên gắn với artifact digest để không phê duyệt nhầm nội dung khác.

### 16.4. Promotion record

Ghi nhận artifact digest, môi trường nguồn/đích, actor, thời điểm, approval ID và kết quả promotion.

### 16.5. Không rebuild khi promote

Nếu phải thay đổi artifact để phù hợp production, cần phân biệt đó là configuration injection hợp lệ hay một artifact mới. Nếu nội dung thay đổi, digest cũng thay đổi và phải được xác minh lại.

## 17. Artifact và deployment configuration

Artifact và cấu hình triển khai có vòng đời khác nhau.

Ví dụ:

~~~text
artifact:
    image = "registry.example.com/catalog@sha256:4f2c..."

deployment:
    replicas = 4
    region = "asia-southeast1"
    logLevel = "info"
    databaseSecret = secretRef("catalog-db")
~~~

Image chứa code và runtime dependencies. Deployment config mô tả cách chạy image trong một môi trường.

### 17.1. Externalize configuration

Thông tin thay đổi theo môi trường nên được truyền qua config, environment hoặc secret reference. Điều này cho phép cùng artifact chạy ở nhiều môi trường.

### 17.2. Secrets

Secret không nên được đóng gói trong artifact hoặc manifest công khai. Nên lưu secret ở secret manager và chỉ tham chiếu đến key hoặc resource identity.

### 17.3. Config compatibility

Artifact version mới có thể yêu cầu config schema mới. Deployment pipeline cần validate config tương ứng trước khi rollout.

### 17.4. Artifact không phải trạng thái đang chạy

Artifact mô tả sản phẩm đã tạo. Runtime state như số replica hiện tại, pod health hoặc active traffic là trạng thái của môi trường triển khai.

## 18. Multi-platform artifact

Một project có thể tạo artifact cho nhiều OS, CPU architecture hoặc runtime.

~~~text
artifacts/
├── catalog-linux-amd64
├── catalog-linux-arm64
├── catalog-windows-amd64.exe
└── catalog-macos-arm64
~~~

### 18.1. Target triple

Một target có thể bao gồm architecture, vendor, operating system và ABI. Build DSL nên mô tả target rõ thay vì chỉ dùng tên chung như linux.

### 18.2. Cross-compilation

Cross-compilation tạo binary cho target khác với host build. Toolchain, sysroot và native dependency cần tương thích target.

### 18.3. Platform-specific dependency

Dependency native có thể khác theo platform. Artifact metadata cần ghi target để consumer chọn đúng variant.

### 18.4. Universal package

Một package có thể chứa nhiều variant hoặc manifest trỏ đến từng variant. Cần xác định resolver chọn artifact nào theo môi trường.

## 19. Artifact caching

Artifact cache lưu kết quả build để tránh tính toán lại khi input không thay đổi.

### 19.1. Cache key

Cache key có thể phụ thuộc source files, build script, compiler và plugin version, dependency lock, build options, target platform và environment inputs đã khai báo.

Nếu một input ảnh hưởng output nhưng không có trong cache key, hệ thống có thể dùng nhầm artifact cũ.

### 19.2. Local cache và remote cache

Local cache phục vụ một máy. Remote cache cho phép nhiều máy hoặc CI worker chia sẻ kết quả.

### 19.3. Cache correctness

Cache hit chỉ an toàn khi key đại diện đầy đủ cho mọi input có ảnh hưởng. Không nên cache task có side effect không được mô hình hóa như một task thuần.

### 19.4. Cache artifact theo digest

Content-addressed artifact hỗ trợ cache và deduplication. Cùng digest có thể tham chiếu cùng nội dung ở nhiều build.

### 19.5. Cache eviction

Cache cần policy giới hạn dung lượng và tuổi. Eviction xóa bản cache, không nên xóa nhầm artifact phát hành đang được release hoặc deployment tham chiếu.

## 20. Artifact retention và cleanup

Artifact có thể tiêu tốn dung lượng đáng kể. Cần policy lưu giữ theo loại, version và trạng thái sử dụng.

### 20.1. Retention policy

Có thể giữ release artifact theo thời hạn dài, snapshot build theo số lượng hoặc số ngày, nightly build theo retention ngắn hơn, temporary output chỉ trong thời gian task hoặc pipeline, và security evidence theo yêu cầu kiểm toán.

### 20.2. Không xóa artifact đang được tham chiếu

Trước khi cleanup, hệ thống cần biết artifact có đang được release, deployment, rollback plan hoặc audit record tham chiếu không.

### 20.3. Garbage collection

Với content-addressed storage, garbage collector có thể tìm object không còn reachable từ bất kỳ reference hợp lệ nào. Quá trình cần có grace period để tránh xóa object vừa upload nhưng chưa được liên kết.

### 20.4. Legal hold và compliance

Một số artifact cần được giữ do điều tra, quy định hoặc release record. Retention policy cần hỗ trợ hold và audit việc xóa.

### 20.5. Artifact deletion

Delete quyền cao có thể bị giới hạn cho administrator hoặc repository owner. Nên ghi lại actor, lý do, artifact identity và thời điểm.

## 21. Artifact trong DSL build graph

Build DSL có thể mô hình hóa artifact như một node hoặc output type trong task graph.

Ví dụ:

~~~text
task compile {
    inputs = sourceFiles("src/")
    outputs = artifact("classes", type = "directory")
}

task package {
    dependsOn = [compile]
    inputs = [artifact("classes")]
    outputs = artifact("application", type = "jar")
}

task verify {
    inputs = [artifact("application")]
    run = testJar(artifact("application"))
}

task publish {
    dependsOn = [verify]
    inputs = [artifact("application")]
    destination = repository("releases")
}
~~~

### 21.1. Producer và consumer

Producer tạo artifact; consumer đọc artifact. Build engine cần kiểm tra artifact reference đã được producer khai báo và dependency graph có bảo đảm producer chạy trước consumer không.

### 21.2. Typed artifact reference

Một task có thể yêu cầu artifact loại JAR. Truyền một directory hoặc test report vào task đó cần bị từ chối hoặc yêu cầu adapter rõ.

### 21.3. Lazy artifact provider

Một artifact provider có thể trì hoãn việc resolve path đến khi task thực sự cần. Điều này giúp build graph được cấu hình mà không phải thực hiện build ngay trong giai đoạn configuration.

### 21.4. Artifact collection

Một task có thể tiêu thụ nhiều artifact:

~~~text
inputs = artifactCollection("runtimeLibraries")
~~~

Collection cần quy định thứ tự, xử lý duplicate và cách giữ metadata của từng phần tử.

### 21.5. Optional output

Task có thể chỉ tạo artifact trong một điều kiện. Consumer cần biết output optional và xử lý trường hợp không có artifact thay vì giả định file luôn tồn tại.

### 21.6. Output validation

Sau task, build engine có thể xác nhận output tồn tại, đúng loại, không rỗng khi yêu cầu và nằm trong output directory được khai báo.

## 22. Artifact manifest và SBOM

Manifest mô tả artifact cụ thể. SBOM mô tả thành phần bên trong artifact.

### 22.1. Manifest

~~~json
{
  "artifact": {
    "name": "catalog-service",
    "version": "2.4.0",
    "type": "container-image",
    "digest": "sha256:4f2c..."
  },
  "build": {
    "id": "build-1842",
    "sourceRevision": "a81c92d",
    "builder": "ci-release"
  }
}
~~~

### 22.2. SBOM

SBOM có thể liệt kê:

| Thành phần | Version | Loại |
|---|---|---|
| http-runtime | 4.2.1 | Direct dependency |
| json-core | 2.8.0 | Transitive dependency |
| crypto-provider | 1.9.3 | Runtime library |

SBOM cần liên kết với digest artifact để biết chính xác inventory đang mô tả đối tượng nào.

### 22.3. SBOM format

Các định dạng phổ biến gồm SPDX và CycloneDX. Tooling cần ghi rõ format/version để consumer parse đúng.

### 22.4. Scan result

Security scan report cũng nên ghi digest của artifact đã scan, scanner version, database snapshot hoặc thời điểm scan và policy threshold. Một scan result cho image digest cũ không tự động áp dụng cho image mới.

## 23. Artifact và rollback

Rollback là đưa môi trường về một artifact version đã được biết là hoạt động.

### 23.1. Giữ artifact lịch sử

Rollback chỉ khả thi nếu artifact cũ còn tồn tại và có thể tải lại. Retention policy cần tính đến khoảng thời gian rollback được hỗ trợ.

### 23.2. Deploy theo digest

Dùng digest giúp bảo đảm rollback về đúng image content, ngay cả khi tag đã được cập nhật.

### 23.3. Database migration

Rollback application artifact không nhất thiết đảo ngược được database migration. Cần quản lý compatibility giữa application version và schema version.

### 23.4. Rollback record

Ghi artifact trước và sau rollback, actor, thời điểm, lý do, deployment ID và kết quả health check.

### 23.5. Forward fix

Trong một số trường hợp, forward fix an toàn hơn rollback. Hệ thống vẫn cần giữ artifact cũ để điều tra và đối chiếu.

## 24. Tính tương thích của artifact

Artifact có thể phụ thuộc vào runtime, API, schema hoặc môi trường đích.

### 24.1. Runtime compatibility

Một JAR có thể yêu cầu Java 21. Metadata nên ghi minimum runtime hoặc target bytecode version.

### 24.2. API compatibility

Library mới có thể thay đổi public API. Package metadata hoặc release notes có thể mô tả compatibility range.

### 24.3. Config schema compatibility

Application version mới có thể yêu cầu field config mới. Build/deploy pipeline nên validate cấu hình cho từng artifact version.

### 24.4. OS và architecture

Binary native cần đúng OS, architecture và ABI. Không nên dùng một artifact identity chung cho các binary không tương thích nếu consumer không thể phân biệt variant.

### 24.5. Artifact contract

Consumer cần biết artifact cung cấp entry point nào, port nào, file nào, protocol nào hoặc schema nào. Có thể mô tả contract trong metadata hoặc deployment descriptor.

## 25. Bảo mật khi tạo và phân phối artifact

Artifact là một phần của software supply chain. Build và publish pipeline cần bảo vệ cả nội dung lẫn nguồn gốc.

### 25.1. Không đóng gói secret

Secret trong source, environment hoặc build log có thể vô tình được copy vào archive, image layer hoặc metadata. Cần loại trừ file nhạy cảm và kiểm tra artifact trước publish.

### 25.2. Build isolation

Build script và dependency có thể chạy mã. Runner cần quyền tối thiểu, workspace isolation và credential scope phù hợp.

### 25.3. Dependency verification

Có thể xác minh checksum hoặc signature của dependency trước khi dùng. Lockfile chỉ cố định tọa độ/version; nó không tự chứng minh package là đáng tin.

### 25.4. Artifact scanning

Quét malware, vulnerability, license và secret trước khi publish hoặc promote. Kết quả cần liên kết với digest.

### 25.5. Trusted publisher

Chỉ identity được cấp quyền mới được publish vào release repository. Cần bảo vệ token, dùng short-lived credential khi có thể và ghi audit event.

### 25.6. Archive extraction

Consumer cần bảo vệ trước path traversal, symlink escape, decompression bomb và file permission nguy hiểm khi giải nén artifact không tin cậy.

### 25.7. Verify before deploy

Deployment controller có thể yêu cầu digest, signature, provenance và scan policy đạt yêu cầu trước khi cho phép triển khai.

## 26. Hiệu năng và kích thước artifact

Artifact lớn làm tăng thời gian upload, download, lưu trữ và triển khai.

### 26.1. Loại bỏ file không cần thiết

Không đóng gói source map, test fixture, temporary file hoặc tài liệu nội bộ nếu runtime không cần chúng. Một số file có thể được phát hành riêng dưới classifier khác.

### 26.2. Compression

Compression giảm dung lượng nhưng tăng CPU khi đóng gói và giải nén. Cần chọn mức nén phù hợp với loại nội dung và môi trường.

### 26.3. Container layers

Layer có thể được cache và chia sẻ. Thay đổi thứ tự layer hoặc copy quá nhiều file có thể làm mất hiệu quả cache.

### 26.4. Deduplication

Content-addressed storage có thể lưu một lần nội dung trùng nhau và cho nhiều artifact tham chiếu. Cần cân nhắc chi phí index và garbage collection.

### 26.5. Split artifact

Có thể tách debug symbols, source archive hoặc optional plugin thành artifact riêng để runtime package nhỏ hơn.

## 27. Quan sát và chẩn đoán artifact

Khi artifact thiếu, sai hoặc không triển khai được, metadata và build record giúp tìm nguyên nhân.

Thông tin nên có:

- Build ID và task tạo output.
- Artifact identity và digest.
- Source revision.
- Dependency lock state.
- Toolchain version.
- Build parameters.
- Upload/publish status.
- Scan/signature result.
- Deployment references.

### 27.1. Build failure và missing artifact

Nếu task compile thất bại, task package không nên publish artifact cũ còn sót trong output directory. Build engine cần phân biệt output của lần chạy hiện tại với output stale.

### 27.2. Artifact mismatch

Nếu manifest digest không khớp file, cần dừng promotion và điều tra. Không nên cập nhật manifest tự động để che mismatch.

### 27.3. Artifact unavailable

Nếu repository không tìm thấy artifact theo coordinates, cần kiểm tra version, repository, permission, retention và publish result.

### 27.4. Traceability

Từ deployment có thể truy ngược đến digest, release, build ID, source revision và policy phê duyệt. Từ source revision có thể tìm các artifact được tạo ra từ revision đó.

## 28. Ví dụ tổng hợp: DSL tạo và publish artifact

Một project có thể mô tả:

~~~text
project "catalog-service" {
    version = "2.4.0"

    source {
        main = "src/main/"
        resources = "src/resources/"
    }

    toolchain {
        java = "21"
        compiler = "javac-21"
    }

    dependencies {
        library("com.example:http-runtime:4.2.1")
        library("com.example:json-core:2.8.0")
    }

    task compile {
        inputs = source.main
        outputs = artifact("classes", type = "directory")
    }

    task package {
        dependsOn = [compile]
        inputs = [artifact("classes"), source.resources]
        outputs = artifact("application", type = "jar")
        archiveName = "catalog-service-2.4.0.jar"
    }

    task sbom {
        inputs = [artifact("application")]
        outputs = artifact("inventory", type = "cyclonedx-json")
    }

    task verify {
        inputs = [artifact("application"), artifact("inventory")]
        requireTests = true
        requireNoCriticalVulnerabilities = true
    }

    task publish {
        dependsOn = [verify]
        inputs = [artifact("application"), artifact("inventory")]
        repository = "releases"
        immutable = true
    }
}
~~~

Quy trình khái niệm:

1. Resolve toolchain và dependency.
2. Compile source thành class files.
3. Package class files và resources thành JAR.
4. Tạo SBOM cho artifact.
5. Chạy test và security verification.
6. Tính digest và tạo metadata.
7. Publish artifact và SBOM vào release repository.
8. Ghi build provenance và publish record.

Artifact sau publish có thể được dùng bởi deployment project:

~~~text
deployment "catalog-production" {
    application = artifact(
        "com.example:catalog-service:2.4.0"
    )

    environment = "production"
    replicas = 4
    region = "asia-southeast1"
}
~~~

Trong một pipeline thực tế, deployment nên pin digest đã xác minh để bảo đảm nội dung không thay đổi nếu tag hoặc version alias được di chuyển.

## 29. Các nguyên tắc thiết kế artifact trong DSL

Khi thiết kế artifact model và build DSL, nên xác định rõ:

1. Artifact identity và coordinates.
2. Artifact type và target platform.
3. Producer task và consumer task.
4. Input, output path và output collection.
5. Metadata schema và version.
6. Digest và content verification.
7. Immutability sau publish.
8. Dependency closure và lock state.
9. Build reproducibility và toolchain provenance.
10. Repository, publish policy và access control.
11. Signature, attestation và SBOM.
12. Promotion, deployment reference và rollback.
13. Retention, archive và garbage collection.
14. Security checks trước khi phân phối.

Một artifact model rõ ràng giúp build engine kiểm tra dependency graph, cache đúng, publish có kiểm soát và cung cấp traceability cho toàn bộ vòng đời phần mềm.

## 30. Những sai lầm thường gặp

**Đồng nhất source với artifact.** Source là đầu vào; artifact là sản phẩm được tạo và quản lý để dùng tiếp.

**Dùng path tạm làm identity.** Path trên máy build không phải định danh bền vững cho hệ thống khác.

**Ghi đè artifact đã publish.** Việc này làm mất tính bất biến, gây sai cache và phá khả năng tái dựng release.

**Chỉ dùng tag để pin container.** Tag có thể thay đổi; digest xác định nội dung cụ thể.

**Không ghi dependency và toolchain version.** Build sau có thể tạo kết quả khác mà không rõ nguyên nhân.

**Build lại khi promote.** Artifact ở production có thể khác artifact đã được test ở staging.

**Đưa environment secret vào package.** Secret có thể tồn tại trong image layer hoặc archive lâu hơn dự kiến.

**Không kiểm tra archive path.** Artifact không tin cậy có thể ghi file ra ngoài destination khi giải nén.

**Coi hash là bằng chứng nguồn gốc.** Hash xác minh nội dung; provenance và signature mới giúp xác minh builder và nguồn phát hành.

**Không liên kết scan result với digest.** Báo cáo scan của artifact cũ không chứng minh artifact mới an toàn.

**Cleanup theo tuổi mà không xét reference.** Artifact vẫn được release hoặc rollback tham chiếu có thể bị xóa.

**Không giữ schema metadata cũ.** Hệ thống có thể không đọc được manifest của artifact lịch sử.

## 31. Ghi nhớ

- Artifact là sản phẩm được định danh từ build hoặc packaging, có thể là binary, library, archive, container image, deployment package, documentation hoặc report.
- Artifact khác source, build output trung gian, release và deployment.
- Build graph cần mô tả producer, consumer, input và output artifact.
- Metadata, coordinates, version và target giúp nhận diện và phân phối đúng artifact.
- Digest xác minh nội dung; provenance và signature giúp xác minh nguồn gốc.
- Artifact đã publish nên bất biến; dùng digest để tham chiếu nội dung chính xác.
- Reproducible build cần dependency lock, toolchain cố định và môi trường build được kiểm soát.
- Dependency closure xác định thành phần cần để tạo hoặc chạy sản phẩm.
- Registry lưu và phân phối artifact; publish cần policy, quyền và xử lý retry.
- SBOM và scan result cần liên kết với digest artifact cụ thể.
- Promotion nên dùng cùng artifact qua các môi trường; cấu hình môi trường được quản lý riêng.
- Retention và garbage collection phải xét đến release, deployment và rollback reference.
- Deployment cần xác minh artifact trước khi chạy và ghi lại digest đã triển khai.

## 32. Câu hỏi tự kiểm tra

1. Artifact là gì và khác source code, build output, release và deployment như thế nào?
2. Nêu năm loại artifact có thể được tạo trong một build pipeline.
3. Vì sao artifact cần identity và metadata ổn định?
4. Coordinates thường gồm những thành phần nào?
5. Version và digest trả lời hai câu hỏi khác nhau nào?
6. Vì sao artifact đã publish nên bất biến?
7. Reproducible build là gì? Những yếu tố nào làm output không tái lập?
8. Phân biệt thin artifact, fat artifact và dependency closure.
9. Artifact registry có vai trò gì trong quá trình phân phối?
10. Provenance và SBOM cung cấp thông tin gì?
11. Hash khác digital signature như thế nào?
12. Vì sao nên build một lần rồi promote cùng digest qua các môi trường?
13. Artifact và deployment configuration nên được tách ra như thế nào?
14. Cache key cần chứa những input nào để tránh dùng nhầm output cũ?
15. Làm thế nào để cleanup không xóa artifact còn được release hoặc deployment tham chiếu?
16. Vì sao scan result phải gắn với digest artifact?
17. Hãy thiết kế một build DSL tạo JAR, SBOM, test report và publish record.
18. Khi rollback một ứng dụng có database migration, những artifact và compatibility information nào cần được giữ?
