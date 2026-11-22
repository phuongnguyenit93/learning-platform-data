# Testcontainers: Chọn image, ghim phiên bản và kiểm soát tính lặp lại

## 1. Một test tích hợp có thể đổi kết quả dù mã Java không đổi

Bạn viết test Spring Boot kết nối PostgreSQL bằng Testcontainers:

```java
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:latest");
```

Hôm nay test xanh. Một tuần sau, máy CI mới kéo image khác dưới cùng tag `latest`, database server hoặc hệ điều hành trong image thay đổi và migration thất bại. Máy developer vẫn xanh vì Docker local cache chứa image cũ. Không có thay đổi nào trong Java source, nhưng **điều kiện thực thi đã thay đổi**.

Đây là lý do phải quản lý image giống một **test dependency**. Có ba câu hỏi riêng biệt:

1. **Chọn image nào?** Đúng dịch vụ, engine, architecture, version, extensions và nguồn phát hành tin cậy?
2. **Ghim image thế nào?** Dùng mutable tag, version tag hay digest `sha256`? Ghim đến mức nào để có kết quả ổn định?
3. **Kiểm soát tính lặp lại thế nào?** Khi image đã ghim, những nguồn biến thiên khác (JDK, Gradle, dependencies, schema, timezone, locale, dữ liệu test, container startup và CI runtime) còn gây kết quả khác không?

Một **tag cụ thể theo patch** như `postgres:16.6-alpine` giảm thay đổi ngoài ý muốn so với `postgres:latest`, nhưng **tag vẫn có thể bị registry republish**. Docker image **digest** định danh một manifest hoặc multi-platform image index bất biến về nội dung. Khi dùng một digest đã được xác minh, runtime không tự chọn một manifest mới chỉ vì chủ registry cập nhật tag. Tuy nhiên, digest pinning **không tự bảo vệ khỏi lỗ hổng bảo mật, thiếu image trên registry hoặc khác biệt giữa các kiến trúc CPU**.

Bài này giải thích cơ chế, cách ra quyết định, quy trình nâng image an toàn và một dự án **Java 17 + Spring Boot 3.3 + Testcontainers + PostgreSQL** có thể chạy, trong đó lựa chọn image được đưa thành cấu hình tường minh và được kiểm tra cùng phiên bản database thực tế.

## 2. Kết quả học tập

Sau bài bạn sẽ:

1. Hiểu Docker image, repository name, tag, digest, manifest, image index và local image ID khác nhau thế nào.
2. Chọn image theo vendor/major/minor/patch, bản phân phối, kiến trúc, extensions và môi trường vận hành.
3. Giải thích vì sao `latest`, `16`, `16-alpine` và thậm chí `16.6-alpine` vẫn là **tag có thể thay đổi**.
4. Biết dùng `docker pull`, `docker image inspect` và `docker buildx imagetools inspect` để xác định digest thực, không bịa hash.
5. Phân biệt **index digest đa nền tảng** với **manifest digest của một architecture**.
6. Dùng `DockerImageName.parse(...)` và Testcontainers module chuyên dụng để tham chiếu image được ghim.
7. Quản lý image từ private registry/mirror và trường hợp `asCompatibleSubstituteFor(...)`.
8. Hiểu image pull policy và Docker local cache, tránh nghĩ “test chạy trên tag X” đồng nghĩa đã pull image X mới nhất.
9. Viết JUnit `@DataJpaTest` với PostgreSQLContainer, `@ServiceConnection`, Flyway, Hibernate validation và test SQL PostgreSQL thật.
10. Ghi nhận `DatabaseMetaData`, `server_version_num`, schema migration version và input image reference để chẩn đoán.
11. Hiểu vì sao JDK/Gradle/Boot BOM/JDBC driver, migrations, locale/timezone, container state và platform vẫn ảnh hưởng repeatability.
12. Thiết kế quy trình nâng digest có đánh giá bảo mật, kiểm thử và rollback về version trước.
13. Phân biệt reproducibility của **binary image** với tính lặp lại của **test result** và mức tương đồng production.
14. Chọn cách pin cho PR gate, compatibility matrix, nightly security refresh và release tests.

## 3. Image, container, tag và digest: bản đồ thuật ngữ

| Thuật ngữ | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| Registry | Hệ thống lưu/phân phối images | `docker.io`, registry nội bộ |
| Repository | Tên kho image trong registry | `library/postgres` |
| Tag | Nhãn trỏ tới image manifest/index | `16.6-alpine`, `16-alpine`, `latest` |
| Image reference | Chuỗi chỉ định image để kéo/chạy | `postgres:16.6-alpine` |
| Digest | Hash nội dung một manifest hoặc image index | `sha256:...` |
| Image ID | Định danh image/config ở Docker local | Chuỗi `sha256:...` từ `docker image inspect` |
| Image manifest | Mô tả config/layers cho một image cụ thể | Manifest `linux/amd64` |
| Image index / manifest list | Tập các manifest cho nhiều platform | Index gồm `linux/amd64`, `linux/arm64` |
| Container | Instance chạy được tạo từ image | PostgreSQL process của một test run |
| Volume/data directory | Storage của container khi chạy | `PGDATA`, data được khởi tạo trong test |
| Testcontainers module | Java API khởi động một loại dịch vụ | `PostgreSQLContainer` |

Hai nhận định hay bị nhầm:

**Tag là tên, không phải cam kết immutable.** Registry có thể thay mapping tag → manifest/index. Một tag `16.6-alpine` có vẻ rất cụ thể vẫn có thể được rebuild để nhận security patch cho base image, hoặc do chính sách phát hành của publisher.

**Digest là định danh nội dung manifest/index, nhưng không là bằng chứng nhà phát hành đáng tin.** Biết hash không có nghĩa bạn đã kiểm tra provenance, chữ ký, license hoặc vulnerability status. Image có thể bị xóa khỏi registry dù digest vẫn là định danh hợp lệ.

### 3.1. Một image reference có thể có dạng nào?

```text
postgres:latest
postgres:16
postgres:16-alpine
postgres:16.6-alpine
docker.io/library/postgres:16.6-alpine
postgres@sha256:<digest-thuc-duoc-xac-minh>
docker.io/library/postgres@sha256:<digest-thuc-duoc-xac-minh>
```

Hai dòng có ký hiệu `<digest-thuc-duoc-xac-minh>` **chỉ diễn đạt cú pháp**, không phải lệnh runnable; phải thay bằng digest SHA-256 **thực tế lấy từ registry**. Không viết một chuỗi hash 64 ký tự tưởng tượng chỉ để ví dụ có vẻ thật.

### 3.2. Tag và digest có thể cùng xuất hiện

Docker hỗ trợ tham chiếu tên image kèm tag và digest trong một số cú pháp (`name:tag@sha256:...`). Khi digest được chỉ định, **digest là thứ khóa nội dung được chọn**. Tag có thể giúp người đọc nhận biết “dòng version” nhưng không được xem tag là bằng chứng nội dung nếu digest không khớp với mong muốn.

Khi quản lý test config, nên ghi cả:

- **Human-readable version intent:** PostgreSQL 16, Alpine variant.
- **Resolved immutable reference:** image repository + verified digest.
- **Source và thời điểm xác minh:** registry/publisher, ngày và quy trình update.
- **Platform:** `linux/amd64` hoặc `linux/arm64` khi có ý nghĩa.

## 4. Vì sao `latest` không phù hợp cho regression tests quan trọng?

Xét test:

```java
new PostgreSQLContainer<>("postgres:latest");
```

Những rủi ro:

- `latest` có thể chuyển sang **major version mới**, thay đổi SQL behavior, extension compatibility hoặc server defaults.
- Developer A và CI B có local image cache khác nhau.
- Image publisher có thể rebuild cùng tag, cập nhật OS packages mà không đổi tên.
- CI cold cache kéo bản hiện tại; developer warm cache vẫn dùng bản cũ.
- Một lỗi migration có thể chỉ xuất hiện trên một máy, khó giải thích từ Git commit.
- Trong ngày release, không biết test đã dùng version nào nếu logs chỉ ghi `postgres:latest`.

**Không dùng `latest` cho test gate cần xác định cùng điều kiện khi rerun.** Dùng `latest` có thể hữu ích trong một job riêng có mục tiêu phát hiện sớm compatibility với bản mới; nhưng job đó phải được mô tả là **moving target**, không phải môi trường kiểm tra tái hiện chính xác.

### 4.1. Pin major, minor, patch và digest

| Cách | Ví dụ | Độ cố định | Khi nào hợp lý |
| --- | --- | --- | --- |
| Không pin | `postgres:latest` | Rất thấp | Canaries theo dõi upstream |
| Pin major | `postgres:16` | Cố định dòng major, patch có thể đổi | Compatibility trong một major |
| Pin major + distro | `postgres:16-alpine` | Cố định major/variant, vẫn cập nhật | CI muốn nhận patch thường xuyên |
| Pin patch tag | `postgres:16.6-alpine` | Cụ thể hơn nhưng **tag vẫn mutable** | Local lab/compatibility matrix có kiểm soát |
| Pin digest | `postgres@sha256:...` | Khóa manifest/index | PR/release gate cần traceability |
| Pin verified internal digest | `registry.example...@sha256:...` | Khóa artifact từ registry nội bộ | Doanh nghiệp dùng mirroring/allowlist |

Không có một “best” dùng cho mọi job. Một hệ thống có thể đồng thời dùng:

- PR gate chạy digest đã review (ổn định).
- Nightly chạy patch tag mới của cùng major (phát hiện thay đổi upstream).
- Compatibility job chạy một vài PostgreSQL major versions được hỗ trợ.
- Security update workflow tự tạo PR thay digest và chạy toàn bộ regression suite.

### 4.2. Pin phiên bản không phải pin chất lượng

Một image cũ được ghim digest có thể **vulnerable**. Khi có CVE nghiêm trọng, quy trình đúng không phải xóa pin và quay về `latest` một cách mù quáng; cần chọn image đã được sửa, xác minh provenance/digest, thay pin trong code/lock manifest và chạy test tương thích.

Pin để **chủ động thời điểm thay đổi**, không để khóa mãi một phiên bản.

## 5. Docker local cache và image pull policy

Docker giữ image đã pull/build trên local host. Testcontainers thường tận dụng image cache và chỉ pull khi cần theo policy hiện hành. Một build có image `postgres:16-alpine` cached có thể chạy binary khác với một build cold cache dù source và tag giống nhau.

### 5.1. Hiện tượng “works on my machine”

```text
Developer A (warm cache)
  postgres:16-alpine -> digest D1
  tests -> PASS

CI B (fresh pull)
  postgres:16-alpine -> digest D2
  tests -> FAIL

Git commit + test source: giống nhau.
Image digest thực tế: khác nhau.
```

Một pin theo digest làm hai môi trường nhắm đến **cùng manifest/index** thay vì mỗi host tự resolve một tag chuyển động.

### 5.2. Có nên always pull?

Testcontainers có image pull policies:

```java
PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine")
                .withImagePullPolicy(
                        PullPolicy.alwaysPull());
```

Đây là **snippet tham khảo**, cần import `org.testcontainers.images.builder.Transferable`? **Không**; lớp cần thiết cho `PullPolicy` là `org.testcontainers.images.PullPolicy`. Không thêm import không liên quan vào code. Ý nghĩa `alwaysPull` là cố pull image theo reference đang dùng, có thể chậm hơn và lệ thuộc registry/network.

- Với **mutable tag**: always pull giúp phát hiện bản tag mới, nhưng **làm regression gate kém ổn định** nếu upstream tag chuyển.
- Với **immutable digest**: always pull không thay đổi nội dung được chọn, nhưng có thể tăng network/registry load không cần thiết.
- Với **offline CI**: luôn pull có thể fail dù đúng image đã cached.
- Với **security update**: dùng image update workflow, không chỉ bật always pull rồi hy vọng test lock tự cập nhật.

**Chọn pull policy theo mục tiêu job**, không dùng nó thay cho version pinning.

### 5.3. Pull policy không quyết định mọi image

Một Testcontainers suite có thể còn dùng auxiliary images, chẳng hạn resource reaper hoặc các sidecar/hỗ trợ tùy module và version. Pin PostgreSQL image **không tự khóa tất cả image** mà Testcontainers tải. Để audit hoàn chỉnh, ghi nhận Testcontainers library version, những image thật sự được tạo, registry/substitution và container runtime.

Không tự tắt resource cleanup chỉ để giảm image pull errors; xử lý đúng registry mirror/permissions nếu môi trường bị giới hạn.

## 6. Digest: bất biến về nội dung, nhưng còn phụ thuộc platform

Một digest `sha256` của Docker/OCI có thể thuộc:

1. **Image manifest cho một platform**, ví dụ `linux/amd64`.
2. **Image index / manifest list** chứa nhiều manifests, ví dụ `linux/amd64` và `linux/arm64`.

Khi bạn pin **index digest**, registry index không đổi, nhưng Docker trên `amd64` và Docker trên `arm64` có thể chọn **hai platform manifests khác nhau** trong cùng index. Test về logic có thể pass cả hai, nhưng binary content và hành vi OS/architecture vẫn khác.

### 6.1. Nhìn vào manifest index

Lệnh:

```bash
docker buildx imagetools inspect postgres:16.6-alpine
```

Công cụ sẽ hiển thị repository, media type, top-level digest, và có thể liệt kê các architecture/platform manifests. Đừng copy nhầm digest của `linux/arm64` vào một CI node `linux/amd64` rồi mong nó chạy native.

### 6.2. Chọn index digest hay architecture digest?

- **Index digest**: giữ cùng tập manifests, thuận tiện cho team có cả Apple Silicon/arm64 và CI Linux/amd64; hai máy có thể thực thi binary khác nhau theo platform. Đây là tính tái hiện **multi-platform release set**, không phải byte-for-byte cùng binary trên mọi máy.
- **Platform manifest digest**: khóa chính xác image cho architecture cụ thể; thích hợp khi CI fleet được cố định `linux/amd64`. Trên platform khác có thể cần emulation hoặc không chạy được.
- **Tag digest lưu trong SBOM/lockfile**: phải biết digest thuộc loại nào để không giải thích sai “image đã giống 100%”.

### 6.3. Vì sao `--platform` quan trọng?

Docker hỗ trợ chọn platform khi pull/build/run. Nhưng Testcontainers module cũng phải có runtime support, image support và host architecture phù hợp. Không ép tất cả tests chạy emulated `amd64` trên `arm64` chỉ vì muốn lặp lại; emulation có thể làm chậm, gây lỗi hệ thống và không đại diện môi trường production.

Để công bố tính lặp lại, ghi ít nhất **image digest + OS/CPU platform + database server version**.

## 7. Lấy digest thật từ image, không sao chép hash không xác minh

### 7.1. Pull một patch tag đã chọn

```bash
docker pull postgres:16.6-alpine
```

Đây là **tag minh họa cho bài lab**, không phải lời khuyên dùng một PostgreSQL 16.6 chưa được cập nhật bản vá mới nhất vào production. Khi áp dụng thật, chọn patch/digest đã được duyệt và hỗ trợ.

Docker sẽ hiển thị `Digest: sha256:...` tương ứng registry object được pull. Chỉ ghi lại **digest thực tế** từ kết quả đó.

### 7.2. Kiểm tra local RepoDigests

```bash
docker image inspect \
  --format '{{json .RepoDigests}}' \
  postgres:16.6-alpine
```

`RepoDigests` chứa các repository-digest references gắn với local image nếu thông tin có sẵn. Nó có thể thiếu ở image build local/chưa pull từ registry. Không coi `Id` của `docker image inspect` là cùng loại với registry manifest digest.

Muốn lấy một reference từ image đã pull:

```bash
docker image inspect \
  --format '{{index .RepoDigests 0}}' \
  postgres:16.6-alpine
```

Lệnh chỉ hữu ích khi `RepoDigests` không rỗng; nếu không có phần tử 0, phải kiểm tra thay vì tạo digest giả.

### 7.3. Kiểm tra registry index trực tiếp

```bash
docker buildx imagetools inspect postgres:16.6-alpine
```

Với top-level index, kết quả thường hiển thị `Digest` và các platform manifests. Nếu index digest được chọn, lưu **fully qualified name + digest**, ví dụ do chính lệnh cung cấp.

### 7.4. Vì sao không so `docker image inspect .Id` với registry digest?

`image .Id` thường là hash của image config (local image identifier). Registry digest thường là hash của manifest hoặc index. Chúng có thể bắt đầu bằng `sha256:` nhưng **hash các đối tượng khác nhau**. Test hay script so hai chuỗi này bằng nhau rồi kết luận supply-chain mismatch là sai nguyên lý.

Một báo cáo nên ghi rõ:

- `requestedImageReference`: người viết test muốn dùng image nào?
- `repoDigest`: registry manifest/index ref đã resolve?
- `imageId`: local image config ID?
- `platform`: container chạy trên architecture nào?
- `serverVersion`: chương trình thật trả về version gì?

Đừng đặt tất cả dưới một nhãn mơ hồ “image hash”.

## 8. Chọn image theo những tiêu chí nào?

Khi chọn PostgreSQL image hoặc các service images khác, áp dụng bảng sau:

| Tiêu chí | Câu hỏi cần trả lời |
| --- | --- |
| Service thật hay emulator? | PostgreSQL engine thật, hay một service giả lập? |
| Nhà phát hành | Docker Official Image/vendor image/internal image? |
| Major compatibility | Production dùng PostgreSQL major nào? |
| Patch và support | Patch đã nhận security updates chưa, còn được hỗ trợ không? |
| Distro variant | Alpine vs Debian; có ảnh hưởng libc/locale/extensions không? |
| CPU architecture | CI `linux/amd64`, developer `arm64` có manifest hỗ trợ không? |
| Extensions/features | `pg_trgm`, PostGIS, SSL, locale/ICU, logical replication cần có không? |
| Runtime startup | Entrypoint, readiness, init scripts, health checks có tương thích module không? |
| License và compliance | Cho phép phân phối và kéo image trong CI không? |
| Registry availability | CI có pull được qua network/mirror/credentials không? |
| Provenance/signature | Có cách xác minh publisher và build provenance không? |
| Data initialization | Volume trống, schema/migration/scripts nào được chạy? |
| Upgrade plan | Có quy trình chọn và kiểm tra digest mới không? |

### 8.1. Alpine hay Debian?

Image `postgres:16.6-alpine` và một Debian-based PostgreSQL image cùng server major không nhất thiết giống nhau về base OS, glibc vs musl, locale/ICU, package set, extension availability và startup scripts.

Nếu production dùng PostgreSQL với ICU/collation cụ thể, một Alpine test image có thể **không phản ánh** collation behavior. Khi integration test bảo vệ sorting/case normalization, chọn variant và cấu hình locale sát production hoặc test riêng trên đúng môi trường.

**Lưu ý:** patch tag được ghim trong lab có thể cũ. Việc chọn đúng baseline patch theo ngày là quyết định bảo trì, không phải một giá trị cố định mang tính vĩnh viễn.

### 8.2. Image nhỏ chưa chắc khởi động tốt hơn cho mọi test

Alpine image thường nhỏ, có thể pull nhanh hơn, nhưng khi cần extensions/build tools/locale có thể phải customize. Image Debian-based có thể lớn hơn nhưng tương thích với một số extensions. Chọn theo **behavior cần kiểm chứng**, không chỉ số MB.

### 8.3. Chọn đúng image cho Kafka/Redis/MongoDB

- **Kafka:** broker image/version, KRaft vs ZooKeeper, listener advertised addresses, message format compatibility; không dùng một “Kafka-like emulator” để khẳng định broker thật.
- **Redis:** major version, standalone vs cluster, ACL, Redis Streams/TTL; một node không chứng minh failover.
- **MongoDB:** server major/FCV, indexes, BSON conversion, replica set/transaction topology.
- **RabbitMQ:** version, management plugins, queue type (classic/quorum), acknowledgment/redelivery.
- **Elasticsearch/OpenSearch:** engine version, analyzer/index settings, plugins; API tương tự không bảo đảm giống vendor.
- **LocalStack:** là emulator của một tập AWS APIs; image pin giữ emulator ổn định, **không biến nó thành AWS production service**.

Đừng gọi “chạy trong container” là đủ để có tính tương đồng production: cần đúng **loại service** và **behavior đang test**.

## 9. Testcontainers image modules và image name compatibility

Với PostgreSQL module, cách thường dùng:

```java
import org.testcontainers.containers.PostgreSQLContainer;

PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.6-alpine");
```

Khi image ref được đưa qua config hoặc digest, dùng:

```java
import org.testcontainers.utility.DockerImageName;

DockerImageName image =
        DockerImageName.parse(imageReference);

PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(image);
```

Ở snippet này biến `imageReference` phải do ứng dụng/test cung cấp (lab có code đầy đủ ở phần 14). `DockerImageName.parse` giúp Testcontainers xử lý registry/path/tag/digest qua cấu trúc image name thay vì tự ghép chuỗi thủ công.

### 9.1. Private registry/mirror

Một CI giới hạn Docker Hub có thể mirror official PostgreSQL image vào registry nội bộ, ví dụ:

```text
registry.example.invalid/mirror/postgres:16.6-alpine
```

Đây là **tên minh họa không có server thật**. Khi dùng module chuyên dụng, Testcontainers có thể kiểm tra image thuộc family tương thích. Với mirror có **cùng behavior PostgreSQL** được kiểm duyệt, có thể biểu đạt:

```java
DockerImageName mirrored =
        DockerImageName.parse(
                "registry.example.invalid/mirror/postgres:16.6-alpine")
            .asCompatibleSubstituteFor("postgres");

PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(mirrored);
```

Đây là **snippet không runnable** vì registry URL là minh họa. `asCompatibleSubstituteFor("postgres")` là lời **khai báo trách nhiệm rằng image thay thế tương thích với official postgres**; nó **không** xác minh binary hoặc tự kéo image gốc từ upstream.

Trước khi cho phép mirror trong CI:

1. Verify digest upstream và digest mirror, hiểu manifest/index có thể được thay đổi khi copy.
2. Kiểm tra image thật sự chạy PostgreSQL version cần test.
3. Kiểm tra extensions, entrypoint/env và kiến trúc.
4. Quản lý registry auth bằng CI secret store.
5. Không hardcode registry password trong Java source/Gradle.
6. Nếu image mirror được rebuild/customize, coi đó là **artifact mới** và cập nhật attestation/review.

### 9.2. Automatic image name substitution

Testcontainers hỗ trợ image name substitution thông qua cấu hình/custom substitutor. Điều này giúp một source code dùng official image name nhưng CI resolve sang registry mirror.

Tính linh hoạt này có một hệ quả: **Image reference viết trong test không nhất thiết là image thực sự được chạy**. Khi yêu cầu audit/reproducibility, phải ghi cả requested ref và resolved ref thực tế, và có policy kiểm soát substitution.

Không tự diễn giải một test đang yêu cầu `postgres:16.6-alpine` là proof nó đã pull đúng official Docker Hub image nếu hệ thống có substitutor/registry mirror.

## 10. Image pinning không tự đồng bộ version của thư viện Java

Một bài test tích hợp có nhiều version layers:

```text
Git revision
  |
  +-- JDK 17 toolchain / Gradle wrapper
  +-- Spring Boot version + Spring Dependency BOM
  +-- Testcontainers Java artifacts
  +-- PostgreSQL JDBC driver / Hibernate
  +-- Flyway/Liquibase version
  +-- Testcontainers image reference/digest
  +-- PostgreSQL server binary version
  +-- SQL migrations + seed data
  +-- OS/CPU architecture + container runtime
  +-- Locale/UTC + test execution order/concurrency
  |
  v
Test behavior
```

Pin `postgres@sha256:...` nhưng để Gradle dùng dynamic version `+` hoặc `latest.release` vẫn có thể khiến dependency tree đổi khi rerun. Ngược lại, khóa Maven dependencies nhưng dùng `postgres:latest` vẫn để service engine đổi.

### 10.1. Dùng Spring Boot BOM, đừng hardcode version lung tung

Trong Spring Boot 3.3, Testcontainers integration cùng các thư viện Spring/JUnit thường được Boot dependency management phối hợp. Chọn một Spring Boot line rồi để BOM quản lý versions tương thích. Khi cần override Testcontainers version, nên có lý do, compatibility checks và Gradle lockfiles.

**Không** ghép tùy tiện API/code của Testcontainers 2.x mới nhất vào project Boot 3.3 đang dùng bộ artifacts 1.x mà không rà breaking changes. Cú pháp `@ServiceConnection` và cách phân bố module dependencies có thể thay đổi theo major line.

### 10.2. Gradle Wrapper và dependency locking

- Commit `gradle/wrapper/gradle-wrapper.properties`/wrapper files được tổ chức chấp nhận.
- Dùng Java toolchain để target Java 17 thay vì lấy Java runtime ngẫu nhiên của developer.
- Không dùng dynamic dependencies nếu mục tiêu rerun đúng phiên bản.
- Cân nhắc Gradle dependency locking (`dependencyLocking { lockAllConfigurations() }`) khi cần khóa transitive dependencies.
- Review lockfile khi nâng BOM/JDBC/Testcontainers.
- Nếu dùng internal Maven mirror, kiểm tra artifact provenance và cache policy.

### 10.3. Database image tag vs server version

`postgres:16.6-alpine` mô tả tag mong muốn. SQL thực:

```sql
SELECT current_setting('server_version_num');
```

là một cách xác minh server major/minor/patch number từ **database process đang chạy**. Nó không thay thế digest check, nhưng giúp đảm bảo test kết nối engine/version đúng.

Đừng assert full string `SELECT version()` bằng so sánh byte-for-byte trong CI: text có thể chứa compiler/OS/build metadata khác theo platform. Nếu contract chỉ yêu cầu major 16, assert major, và ghi exact server version như diagnostic metadata.

## 11. Ghim image mà vẫn cho phép nâng có chủ đích

Một pattern hiệu quả là tách **cấu hình baseline** khỏi **cách override**:

```text
DEFAULT_TEST_IMAGE = "postgres:16.6-alpine"  // tag patch cho bài học
CI_LOCKED_TEST_IMAGE = verified repo@sha256:digest
NIGHTLY_TARGET_IMAGE = reviewed newer candidate
```

Đây là sơ đồ chính sách, không phải Java syntax/runnable config. Trong lab:

- Java test đọc system property `test.postgres.image`.
- Gradle truyền vào property từ `-PtestPostgresImage=...`.
- Nếu không override, dùng tag minh họa `postgres:16.6-alpine` để người học dễ chạy.
- CI release/PR gate nên override sang **verified digest**.
- Test kiểm tra actual PostgreSQL major và migration version để không pass trên engine sai.

Điều này cho phép **cùng một test code** chạy trên artifact được duyệt mà không chèn digest giả vào README.

### 11.1. Image reference phải là một đơn vị cấu hình nguyên vẹn

Không tự xây image name bằng:

```java
String ref = "postgres:" + System.getenv("PG_MAJOR");
```

nếu mục tiêu là pin digest. Cách này chỉ chọn major tag và vô tình bỏ patch/digest. Hãy truyền **image reference đầy đủ** (repository + tag hoặc repository + digest) và validate theo policy.

### 11.2. Nếu thiếu override trong release CI?

Fail closed là lựa chọn nghiêm ngặt:

- Bắt buộc `-PtestPostgresImage` là repo+digest trong pipeline release.
- Nếu không có, pipeline dừng với thông báo rõ.
- Local lab cho phép fallback patch tag để học.
- Một job riêng có thể chạy moving tag để theo dõi upstream, nhưng không gắn nhãn reproducible gate.

Trong ví dụ runnable, fallback được giữ cho dễ học; policy fail-closed được trình bày như **hướng mở rộng CI**, không giả vờ mã demo đã tự enforce.

## 12. Dự án runnable: Java 17 + Spring Boot 3.3 + PostgreSQL Testcontainers + Flyway

Mục tiêu: tạo một **JPA test slice** kết nối PostgreSQL 16 thực, không dùng H2, với schema được tạo bởi **Flyway migration** thay vì Hibernate `create-drop`. Chúng ta sẽ:

1. Đặt PostgreSQL image reference qua Gradle project property (có thể thay bằng digest).
2. Dùng `DockerImageName.parse` và `PostgreSQLContainer`.
3. Dùng `@ServiceConnection` để Boot lấy JDBC connection details từ container.
4. Dùng `@AutoConfigureTestDatabase(replace=NONE)` vì Spring Boot **3.3** mặc định có thể thay datasource trong `@DataJpaTest`.
5. Dùng Flyway tạo schema/index và Hibernate `ddl-auto=validate` để xác minh mapping.
6. Assert database thật là PostgreSQL major 16, migration version bằng 1.
7. Chạy native SQL `ILIKE` để chứng minh behavior của PostgreSQL.
8. Để PostgreSQL từ chối duplicate unique key và negative price CHECK constraint.

### 12.1. Cấu trúc dự án

```text
test-image-reproducibility/
├── settings.gradle
├── build.gradle
├── src/main/java/example/imagepin/
│   ├── ImagePinApplication.java
│   ├── InventoryItem.java
│   └── InventoryRepository.java
├── src/main/resources/db/migration/
│   └── V1__create_inventory_item.sql
└── src/test/java/example/imagepin/
    └── PinnedPostgresIntegrationTest.java
```

Tạo những file theo đúng đường dẫn/package. Ví dụ dùng `Spring Boot 3.3.0` **để giữ imports nhất quán**, không đề xuất đây là release production mới nhất. Người dùng hệ thống thực cần chọn bản đang được hỗ trợ và có security patches. PostgreSQL tag `16.6-alpine` cũng chỉ là **baseline minh họa**, phải cập nhật sang digest/version đã duyệt trước khi dùng trong release pipeline.

### 12.2. `settings.gradle`

```groovy
rootProject.name = 'test-image-reproducibility'
```

### 12.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.flywaydb:flyway-core'

    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()

    systemProperty 'test.postgres.image',
            providers.gradleProperty('testPostgresImage')
                    .orElse('postgres:16.6-alpine')
                    .get()
}
```

**Vì sao dùng Gradle `systemProperty`?** Một project property `-PtestPostgresImage=...` chỉ tồn tại trong Gradle process; test chạy trong forked JVM. `tasks.named('test').systemProperty(...)` đưa giá trị vào JVM chạy JUnit để `System.getProperty("test.postgres.image")` đọc được. Nếu chỉ chạy `./gradlew test -Dtest.postgres.image=...` mà không chuyển property vào test worker, không được mặc định nó đã xuất hiện ở JUnit JVM.

**Vì sao có `flyway-database-postgresql`?** Flyway hiện đại dùng module database-specific cho PostgreSQL; Spring Boot 3.3 BOM quản lý versions phù hợp. Chỉ có `flyway-core` có thể không đủ với tổ hợp Flyway 10.x/PostgreSQL.

**Vì sao không có H2?** Mục tiêu là PostgreSQL thật. Không cần H2 test driver; nhưng vẫn ghi `replace=NONE` để hành vi rõ và phù hợp Boot 3.3.

**Gradle Wrapper:** nếu máy đã có Gradle 8.x tương thích, chạy một lần `gradle wrapper --gradle-version 8.7` và commit wrapper files. Sau đó dùng `./gradlew` hoặc `.\gradlew.bat`. Project tree chỉ liệt kê source trọng tâm, không in những binary wrapper files trong README.

### 12.4. `ImagePinApplication.java`

**`src/main/java/example/imagepin/ImagePinApplication.java`:**

```java
package example.imagepin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImagePinApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImagePinApplication.class, args);
    }
}
```

`@DataJpaTest` sẽ dùng application class này để tìm auto-configuration và quét entity/repository tương ứng, không nạp toàn bộ ordinary service/controller như `@SpringBootTest`.

### 12.5. `InventoryItem.java`

**`src/main/java/example/imagepin/InventoryItem.java`:**

```java
package example.imagepin;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_item")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, length = 40)
    private String sku;

    @Column(name = "title", nullable = false, length = 120)
    private String title;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    protected InventoryItem() {
        // Required by JPA.
    }

    public InventoryItem(
            String sku,
            String title,
            long priceCents) {
        this.sku = sku;
        this.title = title;
        this.priceCents = priceCents;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getTitle() {
        return title;
    }

    public long getPriceCents() {
        return priceCents;
    }
}
```

Entity có `GenerationType.IDENTITY` để PostgreSQL tạo ID. Test **không** assert ID bắt đầu từ 1; sequence/identity counters có thể tăng ngay cả khi transaction rollback.

### 12.6. `InventoryRepository.java`

**`src/main/java/example/imagepin/InventoryRepository.java`:**

```java
package example.imagepin;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);

    @Query(
            value = """
                    SELECT *
                      FROM inventory_item
                     WHERE title ILIKE CONCAT('%', :term, '%')
                     ORDER BY sku
                    """,
            nativeQuery = true
    )
    List<InventoryItem> searchTitleIgnoreCase(
            @Param("term") String term);
}
```

`ILIKE` là cú pháp PostgreSQL-specific. Nếu test chạy trên H2 một cách vô ý, câu truy vấn này không phải bằng chứng tương đương PostgreSQL; metadata assertion và explicit datasource giúp xác minh engine thật.

`@Param` bind query parameter thay cho nối raw SQL string với input. Nếu đầu vào chứa `%` hoặc `_` thì pattern matching semantics có wildcard; muốn search theo literal substring cần escape wildcard theo contract, không tự kết luận parameter binding đã biến LIKE into literal-text matching.

### 12.7. Flyway migration `V1__create_inventory_item.sql`

**`src/main/resources/db/migration/V1__create_inventory_item.sql`:**

```sql
CREATE TABLE inventory_item (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL,
    title VARCHAR(120) NOT NULL,
    price_cents BIGINT NOT NULL,
    CONSTRAINT uk_inventory_item_sku UNIQUE (sku),
    CONSTRAINT ck_inventory_nonnegative
        CHECK (price_cents >= 0)
);

CREATE INDEX idx_inventory_item_title_lower
    ON inventory_item (lower(title));
```

Migration này chứa PostgreSQL DDL hợp lệ cho phiên bản trong lab. Hibernate **không tạo lại schema**, vì test đặt `ddl-auto=validate`.

Điều cần phân biệt:

- `uk_inventory_item_sku` bảo vệ unique business key.
- `ck_inventory_nonnegative` bảo vệ price không âm ở database.
- Index function `lower(title)` là một ví dụ index phục vụ biểu thức, nhưng **không tự bảo đảm** sẽ tối ưu `ILIKE '%term%'`; query có wildcard đầu chuỗi có thể cần `pg_trgm` extension và index phù hợp.
- SQL migration là một thành phần của tính lặp lại: cùng image nhưng migration đổi sẽ tạo schema khác.
- Trong production có thể có Flyway history, baseline/repair/validate và migrations từ phiên bản cũ; lab chỉ có migration V1 tạo schema trống.

**Không copy `ddl-auto=create-drop` vào migration integration test**: Hibernate có thể tạo schema thay Flyway và che lỗi DDL production.

## 13. Test đầy đủ `PinnedPostgresIntegrationTest.java`

**`src/test/java/example/imagepin/PinnedPostgresIntegrationTest.java`:**

```java
package example.imagepin;

import java.sql.Connection;
import java.util.List;

import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.TestPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataJpaTest(properties = {
        "spring.jpa.hibernate.ddl-auto=validate"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class PinnedPostgresIntegrationTest {
    private static final String IMAGE =
            System.getProperty(
                    "test.postgres.image",
                    "postgres:16.6-alpine");

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>(
                    DockerImageName.parse(IMAGE))
                    .withDatabaseName("inventory_it")
                    .withUsername("inventory")
                    .withPassword("inventory");

    @Autowired
    InventoryRepository repository;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    Flyway flyway;

    @Test
    void usesRealPostgresMajor16NotH2()
            throws Exception {
        assertTrue(POSTGRES.isRunning());
        assertTrue(!IMAGE.isBlank());

        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }

        String value = jdbc.queryForObject(
                "SELECT current_setting('server_version_num')",
                String.class);

        assertNotNull(value);

        int versionNumber = Integer.parseInt(value);
        int major = versionNumber / 10000;

        assertEquals(16, major);
    }

    @Test
    void flywayMigrationIsAppliedBeforeJpaValidation() {
        assertNotNull(flyway.info().current());

        assertEquals(
                "1",
                flyway.info().current()
                        .getVersion().toString());

        Long count = jdbc.queryForObject(
                """
                SELECT count(*)
                  FROM information_schema.tables
                 WHERE table_schema = current_schema()
                   AND table_name = 'inventory_item'
                """,
                Long.class);

        assertEquals(Long.valueOf(1L), count);
    }

    @Test
    void postgresIlikeQueryRunsOnRealEngine() {
        repository.saveAllAndFlush(List.of(
                new InventoryItem(
                        "CAM-01", "Camera Body", 10000L),
                new InventoryItem(
                        "CAM-02", "camera Lens", 5000L),
                new InventoryItem(
                        "ACC-01", "Tripod", 2000L)));

        List<InventoryItem> found =
                repository.searchTitleIgnoreCase("cAmErA");

        assertEquals(
                List.of("CAM-01", "CAM-02"),
                found.stream()
                        .map(InventoryItem::getSku)
                        .toList());
    }

    @Test
    void realUniqueConstraintRejectsDuplicateSku() {
        repository.saveAndFlush(
                new InventoryItem(
                        "DUP-01", "First", 1000L));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new InventoryItem(
                                "DUP-01", "Second", 2000L)));

        // End method after SQL error; test transaction rolls back.
    }

    @Test
    void realCheckConstraintRejectsNegativePrice() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new InventoryItem(
                                "BAD-PRICE", "Invalid", -1L)));

        // Do not keep querying a transaction after violation.
    }
}
```

**Đây là một class có 5 JUnit methods**, không có network HTTP server. Nó kiểm tra **JPA slice + PostgreSQL engine + Flyway schema**. Điều này tập trung đúng mục tiêu image/version/reproducibility mà không nạp controller/service ngoài phạm vi.

### 13.1. Vì sao dùng `@ServiceConnection`?

Trong Spring Boot 3.3, `@ServiceConnection` trên typed `PostgreSQLContainer<?>` giúp Boot cung cấp `JdbcConnectionDetails` cho DataSource. Không hardcode container host/port, bởi cổng host được cấp động.

Nếu dùng `@DynamicPropertySource` thay thế, phải tự đưa `spring.datasource.url`/username/password từ container vào Environment. Không dùng cả hai đường cấu hình cùng lúc nếu không có lý do cụ thể, vì rất khó truy nguyên bean/URI cuối cùng.

### 13.2. Vì sao `@AutoConfigureTestDatabase(replace=NONE)`?

`@DataJpaTest` trong Spring Boot 3.3 có test database auto-configuration; default `Replace.ANY` có thể thay DataSource bằng embedded DB. `NONE` diễn đạt ý định “giữ datasource thật do Testcontainers cung cấp”.

**Version caveat:** Từ Spring Boot 3.4 có thêm `Replace.NON_TEST` làm default mới, nhưng enum ấy không có trong Boot 3.3. Ví dụ cố ý dùng `NONE` để tương thích đúng version đã chọn.

`NONE` không phải security guard: nếu datasource bị trỏ tới production, nó sẽ vẫn giữ datasource ấy. Trong lab, connection details đến từ PostgreSQL container, nhưng CI cần tách production secrets và network.

### 13.3. Vì sao assert actual DB vendor và server version?

Test `usesRealPostgresMajor16NotH2` xác nhận:

- Container runtime đã start.
- Bean `DataSource` đang kết nối engine thực báo `PostgreSQL`.
- SQL server trả `server_version_num` và major 16.

Nếu vô tình dùng H2, metadata assertion fail. Nếu đổi image sang PostgreSQL 17 trong một “compatibility run”, major assertion cũng fail — đó là điều **chủ ý** ở baseline cố định, nhưng compatibility job cần thay assertion/expected tương ứng nếu muốn hỗ trợ multi-major.

**Không nhầm:** major 16 không chứng minh image digest đúng; hai PostgreSQL 16 patch images khác digest vẫn trả major 16. Image digest phải được xác minh ở artifact/registry/container runtime layer riêng.

### 13.4. Flyway kiểm tra yếu tố repeatability nào?

`flywayMigrationIsAppliedBeforeJpaValidation` assert migration V1 đã chạy và bảng được tạo. Kết hợp `ddl-auto=validate`, nếu entity mapping/schema không khớp, application context có thể fail ngay khi nạp.

Migrations tạo ra **schema đầu vào** nhất quán hơn giữa các CI runs. Nhưng từ V1 trên database trống không thay thế test “upgrade dữ liệu từ schema N-1” hoặc migrations áp dụng trên production datasets.

### 13.5. Vì sao test ILIKE không chỉ test bằng Java?

`postgresIlikeQueryRunsOnRealEngine` thực thi native PostgreSQL SQL `ILIKE`. Mockito có thể return list tùy ý; test này khiến chính PostgreSQL parse, chạy query và JDBC/Hibernate map rows.

Kết quả có thứ tự vì SQL có `ORDER BY sku`. Tránh assert thứ tự không được hợp đồng query quy định.

### 13.6. Unique và CHECK constraints là database behavior

Hai negative tests không dùng Bean Validation để giả lập kết quả. DDL Flyway tạo `UNIQUE` và `CHECK(price_cents >= 0)`; PostgreSQL phải từ chối các INSERT vi phạm.

Với `GenerationType.IDENTITY`, Hibernate có thể INSERT ngay trong `save` để lấy ID, nên bọc **toàn bộ `saveAndFlush` trong `assertThrows` lambda** thay vì khẳng định lỗi chỉ phát tại `flush()`.

Sau một SQL exception, transaction/persistence context có thể không còn dùng an toàn. Method kết thúc và Spring TestContext rollback; không query thêm trong cùng negative test sau exception.

## 14. Lệnh chạy local và CI với image reference tường minh

### 14.1. Chạy mặc định bằng patch tag minh họa

Nếu đã có Gradle Wrapper và Docker:

```bash
./gradlew test
```

Test worker nhận property `test.postgres.image=postgres:16.6-alpine` từ `build.gradle`. Kết quả **dự kiến**: 5 methods pass với PostgreSQL engine 16, Flyway V1 và test schema phù hợp. Trên máy lần đầu có thể cần image pull, cần quyền truy cập Docker Hub/registry.

**Chưa thực thi Docker trong phạm vi nội dung này**. Không trình bày một runtime log, cổng hoặc digest giả như kết quả đã đo.

### 14.2. Ghim một image reference khác đã kiểm tra

Linux/macOS:

```bash
./gradlew test \
  '-PtestPostgresImage=postgres:16.6-alpine'
```

Windows PowerShell:

```powershell
.\gradlew.bat test '-PtestPostgresImage=postgres:16.6-alpine'
```

Đây vẫn là tag pin theo patch, **chưa phải immutable digest**.

### 14.3. Chạy bằng digest thật lấy từ local image

Sau khi pull image và xác nhận `RepoDigests` không rỗng:

```bash
IMAGE_REF=$(docker image inspect \
  --format '{{index .RepoDigests 0}}' \
  postgres:16.6-alpine)

./gradlew test "-PtestPostgresImage=$IMAGE_REF"
```

Nếu command trả repo-digest reference như `docker.io/library/postgres@sha256:...`, class `PinnedPostgresIntegrationTest` sẽ dùng `DockerImageName.parse(IMAGE)` để chọn ref đó. **Không bịa sha256**; lấy từ Docker thực sự. Với môi trường kiểm soát registry index/platform nghiêm ngặt, dùng `docker buildx imagetools inspect` để xác minh digest loại nào đã chọn.

Windows PowerShell:

```powershell
$imageRef = docker image inspect --format '{{index .RepoDigests 0}}' postgres:16.6-alpine
.\gradlew.bat test "-PtestPostgresImage=$imageRef"
```

**Cảnh báo:** `RepoDigests` có thể chứa nhiều references hoặc rỗng; nếu image build local/không có pulled registry digest, không tự coi `.Id` tương đương. Kiểm tra output và policy trước khi dùng trong release gate.

### 14.4. Lệnh xác minh phiên bản PostgreSQL sau khi container chạy

Trong Java test, `current_setting('server_version_num')` đã được assert major 16. Có thể bổ sung quan sát (không bắt buộc trong runnable suite):

```sql
SELECT current_setting('server_version');
SELECT current_setting('server_version_num');
SELECT current_setting('TimeZone');
SHOW server_encoding;
```

Output thực tế thay đổi theo image, platform, runtime và configuration. Nếu business contract cần timezone/encoding cụ thể, cấu hình và assert chúng rõ ràng; đừng chỉ nhìn một log “PostgreSQL started” và kết luận mọi environment default giống nhau.

## 15. Ba thứ “được ghim” nhưng vẫn có thể thay đổi kết quả

### 15.1. Database schema

Cùng PostgreSQL digest nhưng Flyway migration thay đổi sẽ tạo schema khác. Tính lặp lại cần:

- Migration scripts versioned trong Git.
- Flyway version phù hợp với Boot BOM.
- Cấu hình Flyway locations/placeholder/baseline nhất quán.
- Hibernate `validate` thay vì tự tạo schema khi mục tiêu là migration.
- Không dùng một shared database đã chứa dữ liệu từ test run trước.

### 15.2. Fixtures và dữ liệu

Test dùng `Instant.now()`, random UUID không kiểm soát hoặc thời gian chờ cố định có thể flaky dù image không đổi. Nên:

- Tạo fixtures với business keys rõ và không phụ thuộc thứ tự methods.
- Dùng `Clock.fixed(...)`/fixed timestamps khi giờ hiện tại không phải thứ cần test.
- Tránh assert identity sequence luôn bằng 1.
- Test có cả positive và negative data.
- Dùng database cô lập/test-managed transaction rollback phù hợp.
- Khi có server thread hoặc `REQUIRES_NEW` transaction, cleanup riêng cho writes đã commit.

Trong lab, mỗi `@DataJpaTest` method có transaction và rollback mặc định; Flyway schema tạo trước tests. Hai negative tests kết thúc sau DB exception, không tiếp tục query transaction lỗi.

### 15.3. Host/container runtime

Cùng digest vẫn có thể khác:

- Docker/Podman/compatible runtime version.
- Linux kernel và filesystem driver.
- CPU architecture và host resources.
- CI container nesting/remote daemon network.
- DNS/registry mirror và proxy.
- Locale/timezone.
- CPU/memory pressure ảnh hưởng timing.
- Parallel test execution và context/container lifecycle.

**Pin image là cần thiết cho một số mục tiêu nhưng không đủ để test lặp lại 100%.** Khi có flakes, hãy so environment metadata và test boundary, không đổ ngay cho image digest.

## 16. Vì sao cache, reuse và state làm mất tính lặp lại?

### 16.1. Image cache khác container data state

Image cache là các layers/manifest đã pull. Container data là những files/database rows/queues tạo khi container chạy. Hai lần tạo container từ **cùng image digest** có thể cho kết quả khác nếu khởi tạo data/volume khác hoặc app test reuse container cũ.

### 16.2. Reusable containers

Testcontainers có cơ chế container reuse (tùy version, opt-in/experimental). Nó có thể giúp local development nhanh nhưng tạo nguy cơ state còn sót giữa test runs:

- PostgreSQL rows/sequences/migration history còn lại.
- Redis keys và TTL chưa hết.
- Kafka topic/offsets cũ.
- MongoDB collections/indexes còn.
- Cleanup có thể va vào test khác đang dùng cùng container.

**Đừng bật reuse trên CI release gate như mặc định** nếu chưa có chiến lược isolation/reset được kiểm chứng. Việc test vẫn kết nối một container còn sống **không chứng minh** nó khởi tạo từ image digest mới vừa pin.

### 16.3. Spring TestContext cache và @Container lifecycle

`@Container` static dưới JUnit extension thường sống trong phạm vi **test class**. Spring TestContext có thể cache `ApplicationContext` lâu hơn, kể cả qua classes. Nếu context còn giữ datasource tới container đã dừng, class sau có thể bị connection error hoặc kết quả bất định.

Với nhiều integration classes chia sẻ DB:

- Dùng container bean do Spring quản lý với lifecycle tương ứng context, nếu Boot version hỗ trợ và thiết kế phù hợp.
- Hoặc singleton container pattern với lifecycle JVM và cleanup nhất quán.
- Không kết hợp singleton container với JUnit `@Container` nếu extension sẽ dừng nó cuối class.
- Nếu cần isolation theo class, tạo riêng context/container hoặc database/schema tương ứng.
- `@DirtiesContext` không phải phép rollback hay cách sửa mặc định mọi lifecycle vấn đề.

Lab chỉ có một PostgreSQL JUnit class để tránh tình huống phức tạp này.

### 16.4. Random mapped ports là tốt, không phải thiếu repeatability

Testcontainers map PostgreSQL port 5432 trong container sang một **host port động** để tránh collision. Repeatability không yêu cầu port host cố định; yêu cầu **app dùng đúng URL do runtime cấp**, và assertions không dựa vào một cổng cố định.

Cần giữ các yếu tố **hợp đồng** ổn định, không ép những yếu tố hạ tầng vốn được phân phối động.

## 17. CI policy: ghim digest trong PR gate, nâng có review

Một quy trình có kiểm soát:

```text
Developer/Dependency update proposes new image
           |
           v
Check publisher, registry, version, OS, arch support
           |
           v
Resolve actual digest from trusted registry
           |
           v
Scan vulnerabilities, license/provenance/signature
           |
           v
Update approved image reference in CI config/lock
           |
           v
Run unit + slice + Testcontainers integration tests
           |
           v
Check SQL migrations, error behavior, performance risks
           |
           v
Review/merge, record old->new image digest
           |
           v
Observe downstream CI and release results
```

Khi có security advisory, không để digest cũ mãi vì “test vẫn xanh”. Tạo update PR theo quy trình patch, test compatibility, rồi phát hành digest mới. Nếu regressions xảy ra, có thể quay về digest trước để điều tra **trong môi trường test**, nhưng phải cân nhắc security risk của việc rollback.

### 17.1. Một manifest kiểm soát image ở cấp repository

Có thể duy trì policy table trong README hoặc file cấu hình do tổ chức quản lý:

| Dịch vụ | Mục tiêu version | Image reference khóa | Platform | Lần review |
| --- | --- | --- | --- | --- |
| PostgreSQL | 16.x đã phê duyệt | Registry repo + verified digest | linux/amd64 | Ngày review |
| Redis | 7.x đã phê duyệt | Registry repo + verified digest | linux/amd64 | Ngày review |
| Kafka | Dòng được app hỗ trợ | Vendor image + verified digest | linux/amd64 | Ngày review |

Các giá trị này là **mẫu governance**, không phải manifest thật đã được điền. Không thêm một chuỗi “sha256” ảo chỉ để bảng trông đầy đủ.

### 17.2. Pin vs matrix

Nếu product hỗ trợ PostgreSQL 15 và 16:

- **Baseline PR gate:** dùng một digest PostgreSQL 16 đã được duyệt, chạy thường xuyên.
- **Compatibility matrix:** chạy cùng tests với PostgreSQL 15 và 16, sửa expected major cho từng job hoặc assert supported range.
- **Upgrade canary:** chạy image version candidate mới, có thể chưa block mọi PR nhưng gửi cảnh báo.
- **Release gate:** xác minh image/DB version/migration phù hợp deployment target.

Đừng chỉ dùng một test assert major 16 rồi kết luận app đã hỗ trợ cả major 15, 17. Bằng chứng phải đến từ các runs thực sự trên từng engine.

### 17.3. Vấn đề “digest đã biến mất khỏi registry”

Một digest immutable **không bảo đảm registry giữ artifact vô hạn**. Registry retention/GC có thể xóa manifest hoặc deny pull, private mirror có thể mất đồng bộ, credentials có thể hết hạn.

Muốn rerun sau nhiều tháng:

- Có artifact retention policy cho approved images.
- Mirror/replicate images vào registry được kiểm soát.
- Lưu lock manifest và metadata provenance.
- Kiểm tra pullability/availability trong CI.
- Khi cần audit lâu dài, lưu digest + source + SBOM/attestation + platform.

Đây là khác biệt giữa **content identity** và **artifact availability**.

## 18. Chọn thời điểm pull: PR, nightly và incident debugging

| Job | Reference | Pull policy gợi ý | Mục tiêu |
| --- | --- | --- | --- |
| PR gate | Verified digest | Cache-friendly | Ổn định, nhanh |
| Release verification | Approved digest | Cache/registry mirror có kiểm soát | Cùng artifact có thể truy vết |
| Nightly patch compatibility | Reviewed major/patch moving tag | Re-resolve/pull theo policy | Phát hiện thay đổi upstream |
| Incident reproduction | Digest từ run bị lỗi | Kéo đúng digest cũ nếu còn | Tái hiện binary |
| Security patch update | Candidate new digest | Pull candidate | Kiểm tra lỗ hổng + regression |
| Local exploratory | Patch tag có chủ đích | Thường dùng cache | Học nhanh, không tuyên bố byte-identical |

Không có ý nghĩa khi chạy nightly “image mới nhất” nhưng pipeline lưu mỗi tag và không log digest; lần sau không biết canary đã thấy image nào.

### 18.1. Failure attribution

Khi một test bỗng fail:

1. Git revision có đổi?
2. Image requested ref có đổi?
3. Resolved image digest có đổi?
4. Platform/architecture có đổi?
5. Server version trong container có đổi?
6. Gradle dependency lock/BOM/JDK có đổi?
7. Migrations/fixtures/test configuration có đổi?
8. Container reuse/local cache có state tồn tại?
9. Registry pull/network có lỗi không?
10. Test fail ở startup, SQL execution, schema validation hay assertion?

Danh sách này giúp tránh các “fix” sai như tăng timeout vô hạn hoặc đổi test assertion cho khớp image mới khi chưa hiểu nguyên nhân.

## 19. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| CI cold cache fail, local pass | Mutable tag resolve khác | Ghi digest thực và pin approved digest |
| Tag `latest` đổi major | Upstream phát hành phiên bản mới | Pin supported major/patch/digest |
| Đã pin patch nhưng digest khác | Publisher rebuild/republish tag | Chuyển sang verified digest |
| Pull `manifest unknown` | Tag/digest sai hoặc đã bị xóa | Inspect registry và retention policy |
| `no matching manifest for linux/arm64` | Image không hỗ trợ platform | Chọn multi-platform image hoặc CI arch phù hợp |
| `pull access denied` | Private registry auth/policy | Kiểm tra credentials/mirror |
| Container image không tương thích module | Custom mirror khác family/entrypoint | Chọn đúng image, chỉ khai báo compatible khi thật |
| `Could not find a valid Docker environment` | Container runtime thiếu | Cấu hình Docker/socket/remote runtime |
| Container startup timeout | Readiness wait sai, image init chậm | Module wait strategy, logs, resources |
| Local chạy stale image | Cache + mutable tag | Pull có chủ đích hoặc digest pin |
| Image digest giống, server version khác kỳ vọng | Chọn index/arch/entrypoint khác hoặc chạy server khác | Assert DB vendor/version, inspect runtime |
| H2 pass, PostgreSQL native SQL fail | Sai engine trong test hoặc dialect khác | `Replace.NONE`/metadata assertion |
| Flyway PostgreSQL unsupported | Thiếu `flyway-database-postgresql` | Thêm DB-specific module đúng BOM |
| Hibernate validation fail | Migration/schema và entity lệch | So migration SQL/column types |
| Unique test không fail | Index/constraint chưa tạo hoặc DB sai | Assert schema/migration/engine |
| Same digest test khác kết quả | Test data, timezone, arch, deps, concurrency | Kiểm tra reproducibility matrix |
| Test pass riêng, fail suite | Shared DB/context/cache/cleanup | Isolate state, fix lifecycle |
| Test skipped nhưng build xanh | Conditional tag/filter/CI task | Báo executed vs skipped |
| Patch image có CVE | Digest cố định quá lâu | Security update workflow, không tự dùng latest |
| Docker local image ID không khớp digest | So hai loại hash khác nhau | Phân biệt config ID vs registry manifest/index digest |
| Container chạy nhưng DB khác | Wrong DataSource/service connection | Query JDBC vendor/server/database metadata |

### 19.1. Khi gặp failure trước cả tests

`Could not find a valid Docker environment`, `manifest unknown` và `pull access denied` xảy ra ở tầng hạ tầng. Chúng **không** chứng minh query JPA sai. Đọc container/registry logs, exact requested image ref và platform trước khi thay application code.

### 19.2. Khi PostgreSQL đã start mà query fail

Kiểm tra lần lượt:

- DataSource có trỏ đúng container không?
- Flyway migration đã chạy và đúng schema chưa?
- Hibernate `validate` có pass không?
- Native `ILIKE` query, column names và parameter binding có đúng không?
- Constraint/index có được tạo không?
- Transaction nào đang active/rollback?
- JDBC driver/server version có compatible không?

**Không** sửa lỗi SQL bằng cách cho test dùng H2 rồi kết luận image đã ổn.

## 20. Bảo mật: pin digest không đồng nghĩa trust

Một digest hợp lệ chỉ nói rằng nội dung theo hash không đổi. Nó **không chứng minh**:

- Image do publisher được phê duyệt xây dựng.
- Image chưa có malware.
- Image đã được vá mọi CVE.
- Base image và transitive OS packages an toàn.
- Registry/mirror có quyền phát hành phù hợp.
- Image không chứa secrets.
- Build provenance và SBOM hợp lệ.

Các controls phù hợp tùy tổ chức:

- Registry allowlist và signed image verification.
- Software bill of materials (SBOM).
- Vulnerability scanning, exception policy và expiry.
- Attestation/provenance verification (ví dụ chuẩn Sigstore/Cosign nếu được phê duyệt).
- Pinned digest trong reviewable lock manifest.
- Patch review định kỳ.
- Không cấp production secrets/network vào test runners.
- Hạn chế quyền Docker socket/daemon.
- Dọn volumes/test data/logs với retention phù hợp.

Nếu image từ mirror bị tái build, **digest mới** dù server version giữ nguyên. Đó là artifact khác, cần review theo policy.

## 21. Những phần khác phải cố định để có test lặp lại đáng tin

### 21.1. Timezone và locale

Cùng PostgreSQL binary nhưng `SHOW TIME ZONE`, `LC_COLLATE`/collation, ICU và JVM default timezone khác có thể làm date/time, sort và case-insensitive search khác. Tốt nhất:

- Chọn contract thời gian: `Instant` vs `OffsetDateTime` vs `LocalDate`.
- Dùng fixed timestamp trong fixture.
- Cấu hình/kiểm tra timezone khi behavior cần.
- Với collation-sensitive sorting, dùng variant/locale giống production hoặc một integration test riêng.
- Không gọi `System.setDefault(TimeZone...)` bừa bãi giữa parallel tests.

### 21.2. Clock và randomness

`Instant.now()`, UUID/random seed không cố định và async retries có thể tạo flakiness độc lập image digest. Dùng injectable `Clock`, synthetic business keys và deterministic seeds khi cần; nếu test randomness chính là mục tiêu thì báo lại random seed để tái hiện.

### 21.3. Transactions và isolation

`@DataJpaTest` thường rollback mỗi method. Nhưng service chạy trên separate server thread, `REQUIRES_NEW`, async writer hoặc migration startup code có thể commit bên ngoài transaction của test.

Cùng image không bảo đảm state sạch nếu test có side effects commit. Dùng dedicated container/database hoặc cleanup đúng scope, không gọi `deleteAll()` trên production/shared DB.

### 21.4. Ready state

Container process đã start chưa chắc service đã ready. Testcontainers module cung cấp readiness logic, nhưng migrations/application startup cũng cần readiness riêng nếu phụ thuộc.

Không thay wait strategy bằng `Thread.sleep(5000)` cố định để cố giải flake. Với services như Kafka/Elasticsearch, health check có thể nhiều giai đoạn.

### 21.5. Parallel execution

Hai test classes cùng xóa bảng/queue/key của một database container có thể phá lẫn nhau. Cần database/schema-per-test, prefix riêng hoặc tuần tự hóa tests có shared mutable state.

### 21.6. Secondary images

Đừng quên image resource reaper, sidecar, emulator hoặc migration job. Một “DB image lock” chưa phải toàn bộ **test infrastructure image lock**.

## 22. Compatibility test: khác với reproducibility test

**Reproducibility test** hỏi: “Cùng code, cùng image artifact được duyệt, cùng fixtures/config, rerun có ổn định không?”

**Compatibility test** hỏi: “Code có chạy trên nhiều versions/variants mới/cũ không?”

Hai loại cần chiến lược khác nhau:

| Mục tiêu | Cách chạy |
| --- | --- |
| Reproducible PR gate | Một verified image digest, locked dependency set |
| PostgreSQL major compatibility | Matrix 15/16/17 với approved digests |
| Distro compatibility | Alpine và Debian variants theo nhu cầu |
| ARM/AMD compatibility | Matrix architecture hoặc CI fleet đa nền tảng |
| Security patch early warning | Nightly candidate image digest |
| Migration upgrade path | Starting schema/data snapshots N-1, apply migrations N |
| Performance | Workload/data/architecture/limits representative |

Không để compatibility matrix chạy mutable tags rồi gọi cả suite là fully reproducible. Có thể dùng moving targets để **phát hiện thay đổi**, nhưng phải lưu digest của từng run để chẩn đoán và retest.

## 23. Ví dụ process nâng digest trong pull request

Giả sử team đang dùng approved PostgreSQL digest D1 và có phiên bản vá D2:

1. Registry update bot/developer đề xuất D2, ghi upstream release notes.
2. Xác minh publisher, signatures/attestations, SBOM và CVEs.
3. Đối chiếu D2 có đúng PostgreSQL major và platform không.
4. Chạy Docker `imagetools inspect` để lấy index/platform digests.
5. Cập nhật lock manifest/CI image config, **không thay code test oracle để che lỗi**.
6. Chạy `PinnedPostgresIntegrationTest`: vendor, major, Flyway, native SQL, unique/CHECK.
7. Chạy thêm migrations/backward compatibility tests nếu DB version/schema có thay đổi.
8. Review diff D1→D2, lưu digest, ngày, owner.
9. Merge vào default branch, sau đó PR/release gate luôn dùng D2.
10. Nếu D2 thất bại, giữ issue rõ ràng và quyết định fix app/migration hoặc không nâng, không tự bỏ pin.

**Đổi digest là một dependency update có xét tương thích và bảo mật**, không chỉ sửa một chuỗi.

### 23.1. Cần kiểm tra tác động lên schema/extension

Nếu ứng dụng phụ thuộc `pg_trgm`, ICU collation, PostGIS hoặc TimescaleDB:

- Official PostgreSQL image có thể chưa bao gồm extension bên thứ ba.
- Cần image đã tích hợp extension và dependency versions phù hợp.
- Test migration trên đúng image/extension combination.
- Ghi provenance/digest cho custom image.
- Không nói “PostgreSQL major giống nhau nên extension chắc giống”.

### 23.2. Khi cần registry nội bộ

Mirror/air-gapped CI có thể giữ approved image tại registry riêng. Cần lưu mapping upstream digest → internal digest để biết artifact có được copy nguyên vẹn hay rebuild. Một mirror image mới không tự tương đương upstream chỉ vì cùng tag.

## 24. Bài tập thực hành

### Bài 1 — Nhìn thấy mutable tag

Trên máy học tập có Docker, chạy `docker pull postgres:16.6-alpine` rồi inspect `RepoDigests`. Giải thích tại sao có tag cụ thể nhưng còn cần digest nếu muốn tái hiện binary chính xác.

### Bài 2 — Tag vs digest

Dùng `docker buildx imagetools inspect` với PostgreSQL tag đã chọn, ghi lại top-level digest và platform manifests. Phân biệt khi nào dùng index digest và khi nào dùng architecture manifest digest.

### Bài 3 — Chạy lab ở mức patch tag

Dùng `./gradlew test`, ghi nhận server major/version và migration V1. Không kết luận full binary reproducibility nếu chỉ dùng patch tag mặc định.

### Bài 4 — Chạy lab với verified digest

Pull image, lấy `RepoDigests`, dùng Gradle `-PtestPostgresImage=<verified-image-reference>` (đây là cú pháp cần thay bằng giá trị thực). Nếu digest không tồn tại/không đúng platform, test phải fail ở image pull, không tự fallback về `latest`.

### Bài 5 — Đổi major có kiểm soát

Chạy lab với PostgreSQL 17 candidate image. Test `usesRealPostgresMajor16NotH2` dự kiến fail do major assertion. Đây là dấu hiệu **baseline pin** đang được áp dụng. Để triển khai compatibility matrix, parameterize expected major theo job và test migrations/query trên cả hai.

### Bài 6 — Xóa Flyway module PostgreSQL

Ở nhánh sandbox, tạm bỏ `runtimeOnly 'org.flywaydb:flyway-database-postgresql'`, chạy lab và đọc root cause Flyway/driver support khi dùng Flyway 10.x. Khôi phục dependency. Bài học: image version không phải toàn bộ dependency versions.

### Bài 7 — Sửa migration, thấy context fail

Thay tên cột `price_cents` trong migration nhưng không sửa entity. Hibernate `ddl-auto=validate` có thể fail lúc context bootstrap. Khôi phục. Vì sao `create-drop` có thể che lỗi migration trong integration test?

### Bài 8 — Kiểm tra constraint từ DB

Bỏ constraint `uk_inventory_item_sku` trong fresh migration của nhánh thử; duplicate-key test không còn hành vi tương tự. Khôi phục. Nêu khác biệt giữa mock repository và database thực thi constraint.

### Bài 9 — Cache vs always pull

So sánh local image cache với một clean CI agent; dùng mutable tag và ghi resolved digest. Thử `PullPolicy.alwaysPull()` trong một test sandbox. Giải thích tại sao always pull không thay được digest lock.

### Bài 10 — ARM vs AMD

Quan sát image index manifests của `linux/arm64` và `linux/amd64`. Nếu team có Apple Silicon và CI amd64, định nghĩa điều kiện “cùng image” thế nào? Ghi top-level digest, platform digest và actual server version.

### Bài 11 — Local registry mirror

Thiết kế một image name substitution policy cho CI nội bộ, dùng `asCompatibleSubstituteFor("postgres")` chỉ khi mirror image tương thích thật. Ghi mapping requested ref và resolved repo-digest.

### Bài 12 — Security update drill

Lập PR nâng image digest từ D1 sang D2 với changelog, CVE scan, sign-off, compatibility tests và rollback plan. Không bỏ qua test regression chỉ vì scanner báo image mới ít CVE hơn.

### Bài 13 — Bắt lỗi test state

Bật container reuse ở môi trường sandbox có điều kiện, thực hiện một test ghi dữ liệu commit, chạy lại và quan sát state tồn tại. Tắt reuse, dùng database ephemeral/reset đúng, giải thích vì sao image digest giữ nguyên mà test result vẫn khác.

### Bài 14 — Reproducibility matrix

Lập bảng từ hai CI runs: Git SHA, requested image, resolved repo digest, platform, server version, JDK/Gradle, Flyway version, migration checksum, timezone, test executed count. Đánh dấu nguồn biến thiên nào giải thích sự khác biệt.

## 25. Checklist review trước khi merge

- [ ] Dịch vụ/image được chọn là engine thật hoặc emulator **đúng theo mục tiêu test**.
- [ ] Image publisher/registry/distro/architecture được kiểm tra.
- [ ] Không dùng `latest` cho regression gate quan trọng.
- [ ] Hiểu rằng patch tag vẫn mutable.
- [ ] Nếu cần reproducibility artifact, dùng verified repo+digest.
- [ ] Biết digest là manifest/index hay per-platform manifest.
- [ ] Không nhầm local image config ID với registry manifest digest.
- [ ] Testcontainers module hỗ trợ image type và version đã chọn.
- [ ] Nếu dùng mirror, image compatibility và provenance được xác minh.
- [ ] Image pull policy/caching được chọn theo loại CI job.
- [ ] Có quy trình cập nhật digest khi security fix xuất hiện.
- [ ] Không khóa digest cũ mãi chỉ vì test pass.
- [ ] Java 17/Gradle/Spring Boot BOM/Testcontainers/JDBC/Flyway dependencies được kiểm soát.
- [ ] Schema migration và fixture data được versioned/khởi tạo có chủ đích.
- [ ] Không dùng Hibernate `create-drop` để che SQL migrations cần test.
- [ ] Test assert engine/vendor/server major thay vì chỉ assert container bean khác null.
- [ ] Có một database behavior thật: native SQL, constraint, index hoặc transaction.
- [ ] Không mặc định test chạy trên đúng container nếu DataSource có thể bị thay.
- [ ] Không có hardcoded host mapped port/credentials sản xuất.
- [ ] Test isolation/cleanup không đụng production/staging data.
- [ ] Không giả định container reuse làm database sạch.
- [ ] Context cache và @Container lifecycle được quản lý đúng.
- [ ] Không suy ra kết quả production topology/TLS/network chỉ từ container local.
- [ ] CI báo executed/skipped rõ ràng.
- [ ] Image/digest/platform/server-version metadata được giữ đủ để debug.
- [ ] Không bịa digest hoặc tuyên bố đã chạy Docker nếu chưa chạy.

## 26. Tóm tắt và quy tắc ra quyết định

```text
Muốn thử một dependency bằng Testcontainers?
               |
               v
Có cần behavior của service engine thật?
       |                       |
      Không                    Có
       |                       |
  Unit/mock/slice       Chọn đúng vendor, major,
  có kiểm soát          distro, extension, platform
                               |
                               v
                    Mục tiêu test là gì?
                       |           |
             PR/release gate    Compatibility watch
                       |           |
             Approved digest   Reviewed moving candidate
             + locked deps     + log resolved digest
                       |           |
                       +-----+-----+
                             |
                             v
               Cô lập data, chạy migration,
               explicit readiness, fixed fixture
                             |
                             v
               Assert service version + behavior,
               ghi image/arch/runtime metadata
                             |
                             v
               Review security/update policy
```

**Bài học trọng tâm:** Chọn đúng image giúp test chạy trên dịch vụ có **hành vi cần chứng minh**. Ghim digest giúp khóa **nội dung artifact** thay vì lệ thuộc một mutable tag. Nhưng tính lặp lại của cả integration test còn phụ thuộc Java/build dependencies, schema migrations, fixtures, timezone/platform, state isolation, startup và CI runtime. Hãy **ghim có chủ đích, ghi lại điều kiện chạy, nâng cấp có kiểm chứng**, thay vì chỉ thêm `:latest` hoặc một SHA-256 vào code rồi mặc định mọi thứ đã tái hiện được.

## 27. Tài liệu chính thức

- Docker — Pull an image by digest, tag mutability và update caveat: https://docs.docker.com/reference/cli/docker/image/pull/
- Docker — Inspect image and RepoDigests: https://docs.docker.com/reference/cli/docker/image/inspect/
- Docker — Buildx imagetools inspect: https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/
- Docker — Multi-platform images and image index: https://docs.docker.com/build/building/multi-platform/
- Docker — Image content and provenance overview: https://docs.docker.com/learn/content/prove-where-your-image-came-from/
- Testcontainers Java — Image name substitution/mirrors: https://java.testcontainers.org/features/image_name_substitution/
- Testcontainers Java — Image pull policies: https://java.testcontainers.org/features/advanced_options/
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers Java — JUnit Jupiter integration: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers Java — Container lifecycle and reuse: https://java.testcontainers.org/features/reuse/
- Spring Boot 3.3 — Testcontainers and `@ServiceConnection`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.3 — `@DataJpaTest`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — `@AutoConfigureTestDatabase`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Spring Data JPA — Repositories/query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Flyway — PostgreSQL database-specific module: https://documentation.red-gate.com/flyway/reference/database-driver-reference/postgresql-database
- Gradle — Dependency locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- PostgreSQL — `ILIKE` and pattern matching: https://www.postgresql.org/docs/current/functions-matching.html
- JUnit Jupiter — Test lifecycle and assertions: https://docs.junit.org/current/user-guide/
