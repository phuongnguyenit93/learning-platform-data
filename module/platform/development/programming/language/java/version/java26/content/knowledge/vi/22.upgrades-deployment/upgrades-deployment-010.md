# Kế hoạch quay lui dựa trên dữ liệu, cấu hình và phiên bản đã kiểm chứng

> **Mốc cập nhật: 28-11-2026.** Rollback an toàn phải khôi phục được một bộ phiên bản đã biết là tương thích: artifact ứng dụng, JDK/runtime, cấu hình, schema dữ liệu và dependency. Đổi lại container image hoặc chạy JAR cũ chưa đủ nếu database đã đổi cấu trúc, secret đã xoay vòng hoặc binary cũ không còn chạy trên JDK hiện tại.

## 1. Mục tiêu

Khi nâng cấp ứng dụng lên JDK 26, nhóm triển khai cần trả lời được trước khi phát hành:

- Phiên bản ứng dụng nào đã chạy ổn định gần nhất?
- Artifact đó được build bằng JDK vendor, version, build và target release nào?
- Artifact cũ có chạy được với runtime dự kiến sau rollback không?
- Schema database hiện tại có còn tương thích với binary cũ không?
- Cấu hình, JVM flags, feature flags và secret nào cần khôi phục?
- Dữ liệu đã ghi bởi phiên bản mới có thể được phiên bản cũ đọc và xử lý đúng không?
- Nếu dữ liệu đã biến đổi không thể đảo ngược, phải dùng backup/PITR hay migration bù?
- Bằng chứng nào cho thấy bản cũ và đường quay lui đã được kiểm thử?

Bài này xây dựng kế hoạch rollback cho nâng cấp Java 26, đồng thời xét tình huống nâng tiếp lên JDK 27 hoặc quay về một bản LTS. Trọng tâm là dữ liệu, cấu hình và phiên bản đã kiểm chứng.

## 2. Rollback là khôi phục một bộ tương thích

Không có một nút rollback duy nhất cho toàn bộ hệ thống. Một lần phát hành có thể thay đổi độc lập nhiều lớp:

1. **Application artifact:** JAR/WAR, thư viện, native library và dependency.
2. **JDK runtime:** vendor, major release, update/build, architecture và image hệ điều hành.
3. **Database:** schema, index, constraint, stored procedure, dữ liệu và migration version.
4. **Configuration:** biến môi trường, JVM flags, config file, feature flags và secret version.
5. **External contract:** API, event format, message schema, cache key, file format và giao thức kết nối.

Kế hoạch phải chỉ rõ lớp nào được quay lui, lớp nào giữ nguyên và điều kiện tương thích giữa chúng.

Ví dụ: nếu JDK 26 mới làm ứng dụng lỗi do một thư viện dùng deep reflection, có thể cần quay lại artifact/runtime đã kiểm chứng. Nếu lỗi chỉ nằm ở tính năng HTTP/3 mới, có thể tắt đường HTTP/3 và giữ nguyên JDK 26. Nếu schema database đã bị xóa cột mà binary cũ cần đọc, quay lại JAR cũ sẽ làm lỗi nặng hơn.

~~~mermaid
flowchart TD
    A["Phát hiện lỗi sau rollout"] --> B{"Lỗi nằm ở lớp nào?"}
    B --> C["Ứng dụng / dependency"]
    B --> D["JDK / JVM flags"]
    B --> E["Cấu hình / feature flag"]
    B --> F["Schema / dữ liệu"]
    C --> G["Khôi phục artifact đã kiểm chứng"]
    D --> H["Khôi phục runtime + JVM flags tương thích"]
    E --> I["Khôi phục config snapshot / tắt feature"]
    F --> J{"Dữ liệu còn tương thích?"}
    J -->|Có| K["Giữ schema mở rộng, chạy binary cũ"]
    J -->|Không| L["PITR / backup / migration bù đã diễn tập"]
    G --> M["Smoke test và kiểm tra SLO"]
    H --> M
    I --> M
    K --> M
    L --> M
~~~

Một nguyên tắc quan trọng: **không tự động rollback database chỉ vì đã rollback ứng dụng**. Database thường chứa dữ liệu mới phát sinh trong lúc phiên bản mới đang chạy. Phục hồi sai thời điểm có thể xóa giao dịch hợp lệ.

## 3. Chọn phiên bản quay lui theo support lifecycle

Phiên bản trước đó không nhất thiết còn được hỗ trợ hoặc còn nhận bản vá bảo mật. Tại ngày 28-11-2026, roadmap Oracle công bố:

| Release | Loại | Mốc hỗ trợ Oracle Premier Support | Ý nghĩa với kế hoạch |
|---|---|---|---|
| Java 25 | LTS | Đến 09-2030 | Baseline LTS hiện hành trong roadmap này. |
| Java 26 | Non-LTS | Đến 09-2026 | Đã qua mốc Premier Support của Oracle. |
| Java 27 | Non-LTS | Đến 03-2027 | Release mới hơn, nhưng cửa sổ hỗ trợ ngắn. |
| Java 29 | LTS dự kiến | 09-2027 | Mốc LTS kế tiếp theo kế hoạch Oracle đã công bố. |

Các mốc trên là roadmap sản phẩm Oracle; nhà cung cấp JDK khác có thể có chính sách cập nhật và hỗ trợ riêng. Phải kiểm tra đúng distribution đang chạy, hợp đồng hỗ trợ và nền tảng OS/CPU trước khi chốt phiên bản. Không suy luận rằng mọi bản OpenJDK của mọi vendor có cùng ngày kết thúc hỗ trợ. [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)

Oracle công bố JDK 27.0.1.1 ngày 17-11-2026 và đặt lịch CPU tiếp theo vào 19-01-2027. Trong khi đó, consolidated release notes của Oracle nêu JDK 26.0.2.1 không được khuyến nghị sử dụng sau CPU ngày 20-10-2026. Vì vậy, ở thời điểm của bài học, không nên coi JDK 26.0.2.1 là runtime rollback an toàn cho production Oracle. [JDK 27 Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) · [JDK 26 Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)

Khi cần dùng tính năng Java 26 trong môi trường production, hãy xác minh vendor có còn cung cấp bản vá JDK 26 phù hợp hay không. Nếu không có support/update phù hợp, cần cân nhắc chuyển lên release được hỗ trợ hoặc giữ tính năng Java 26 trong một nhánh thử nghiệm có giới hạn. Không kéo dài việc sử dụng runtime đã hết cửa sổ cập nhật chỉ vì nó là bản trước của rollout.

## 4. Khả năng tương thích giữa artifact và runtime

Rollback JDK có thể thất bại ngay cả khi JAR cũ vẫn còn nguyên. Điều cần xác minh là bytecode và API mà artifact thực sự sử dụng.

### 4.1. Artifact stable và API mới của Java 26

Một class file biên dịch theo Java 26 stable có major version 70. Runtime Java 25 không thể nạp class file đó. Ngoài ra, source có thể gọi API chỉ xuất hiện trong Java 26.

Ví dụ:

- UUID.ofEpochMillis(long) có từ Java 26.
- Cipher.getInstance("HPKE") và HPKEParameterSpec là API HPKE của Java SE 26.
- Artifact gọi các API này không thể được đưa về JDK 25 chỉ bằng cách đổi image runtime.

Nếu phải hỗ trợ rollback về JDK 25, cần giữ một artifact tương thích Java 25 đã build và kiểm thử trước đó. Artifact đó phải có đường xử lý thay thế cho tính năng chỉ có ở JDK 26, hoặc không sử dụng tính năng đó.

### 4.2. Preview class file gắn với release

Preview class file có minor version 65535 và gắn với release đã biên dịch:

| Artifact | Runtime phù hợp | Điều kiện |
|---|---|---|
| Java 26 stable | JDK 26 trở lên | API và dependency vẫn tương thích. |
| Java 26 preview | JDK 26 | Bật preview ở runtime cùng release. |
| Java 27 stable | JDK 27 trở lên | Không phụ thuộc API mới hơn runtime. |
| Java 27 preview | JDK 27 | Bật preview ở runtime JDK 27. |

Class preview của JDK 26 không phải artifact để chạy trên JDK 27 hoặc JDK 25. Class preview của JDK 27 cũng không thể chạy trên JDK 26. Muốn thử preview ở release mới, phải biên dịch lại source bằng compiler release đó và kiểm thử lại. Cờ feature flag trong ứng dụng không thể loại bỏ sự phụ thuộc preview đã ghi vào class file.

### 4.3. Preview và incubator cần được ghi trong manifest

JDK 26 có các tính năng preview như Primitive Types in Patterns (JEP 530), Lazy Constants (JEP 526), Structured Concurrency (JEP 525) và PEM Encodings (JEP 524); Vector API là incubator (JEP 529). JDK 27 tiếp tục có preview và incubator riêng, ví dụ JEP 532, JEP 531, JEP 533 và JEP 537.

Nếu ứng dụng có sử dụng các tính năng này, manifest phải ghi:

- JEP/API/module cụ thể.
- JDK release dùng để compile.
- Cờ compile và runtime như --enable-preview.
- Module cần thêm, ví dụ jdk.incubator.vector.
- Cách build lại artifact khi chuyển release.
- Artifact stable thay thế nếu cần quay lui về LTS.

Không ghi chung chung “đã dùng Java 26”. Hãy ghi rõ API nào là stable, API nào là preview và module nào là incubator. [JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html) · [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

## 5. Lập release manifest trước khi triển khai

Mỗi lần phát hành cần lưu một manifest bất biến cùng artifact. Có thể dùng YAML, JSON hoặc metadata của hệ thống phát hành. Ví dụ:

~~~yaml
release:
  application: order-service
  version: "4.8.0"
  gitCommit: "7a91c2e"
  artifactSha256: "sha256:..."
  containerImage: "registry.example.com/order-service@sha256:..."
  build:
    jdkVendor: "Oracle"
    jdkVersion: "27.0.1.1+4"
    compilerRelease: 26
    previewEnabled: false
    incubatorModules: []
    buildTool: "Maven"
    dependencyLockHash: "sha256:..."
  runtime:
    jdkVendor: "Oracle"
    jdkVersion: "27.0.1.1+4"
    osImageDigest: "sha256:..."
    architecture: "linux/amd64"
    jvmFlags:
      - "-Xms2g"
      - "-Xmx2g"
      - "-XX:+UseG1GC"
    moduleOptions: []
  database:
    schemaVersion: "2026.11.28.3"
    migrationIds:
      - "V20261128_01"
    backwardCompatibleWith:
      - "4.7.x"
    backupId: "db-backup-20261128T0100Z"
    restorePoint: "2026-11-28T01:00:00Z"
  configuration:
    configVersion: "order-service-prod-184"
    configSha256: "sha256:..."
    featureFlagsVersion: "flags-72"
    secretReferences:
      - "db-credential:v19"
  verification:
    smokeTestRun: "pipeline-4821"
    integrationTestRun: "pipeline-4823"
    canaryWindow: "30m"
    rollbackArtifact: "order-service:4.7.6"
    rollbackImageDigest: "sha256:..."
~~~

Các giá trị trong ví dụ là placeholder, không phải phiên bản hoặc secret thật. Không đưa password, private key, token hay nội dung secret vào manifest; chỉ lưu tên/version reference và hash không tiết lộ bí mật.

### 5.1. Vì sao cần digest thay vì chỉ dùng tag?

Tag như order-service:stable có thể được registry trỏ sang image khác. Digest định danh nội dung image bằng hash và không thay đổi khi tag được di chuyển. Khi rollback, hãy trỏ về digest đã xác minh và còn được lưu trong registry.

Kubernetes khuyến nghị tránh tag latest trong production vì khó theo dõi và rollback; image digest giúp các Pod chạy đúng cùng một image. [Kubernetes: Images](https://kubernetes.io/docs/concepts/containers/images/)

### 5.2. Ghi lại runtime thật sự

Không chỉ dựa vào Dockerfile hoặc file cấu hình. Cần lưu kết quả quan sát từ tiến trình đang chạy:

~~~bash
java -version
java -XshowSettings:properties -version
java --list-modules
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
~~~

Thay <pid> bằng process ID thực tế. Bảo vệ output vì command line và system properties có thể chứa thông tin nhạy cảm trong một số hệ thống. Không đính kèm secret vào log triển khai.

Manifest phải ghi cả vendor và full build string. Hai JDK cùng ghi 26 hoặc 27 vẫn có thể khác nhà cung cấp, build, security patch, OS image và tập module.

## 6. Kiểm tra tương thích trước khi nâng cấp

Oracle mô tả quy trình migration là lặp: thử chạy ứng dụng trên JDK mới, cập nhật thư viện, biên dịch nếu cần và dùng jdeps để tìm phụ thuộc nội bộ. Khi ứng dụng khởi động được, vẫn phải chạy lại test để phát hiện khác biệt hành vi. [Preparing for Migration](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html)

### 6.1. Chạy thử trên JDK đích trước khi đổi compiler

Thực hiện trên staging với đúng artifact hiện tại:

1. Dùng runtime JDK đích để chạy artifact đang production.
2. Thu thập startup log, warning, exception và JVM flags.
3. Chạy smoke test và integration test.
4. Kiểm tra định dạng ngày, giờ, currency, locale và timezone.
5. Kiểm tra TLS, certificate, thuật toán mật mã và kết nối database.
6. Kiểm tra thư viện, agent, framework, JDBC driver, logging backend và build plugin.

Oracle lưu ý dữ liệu locale có thể khiến định dạng ngày và currency thay đổi giữa các JDK. Hãy so sánh output thực tế với hợp đồng API và dữ liệu nghiệp vụ; không dựa vào chuỗi định dạng cũ nếu chuỗi đó không phải contract được công bố.

### 6.2. Quét API nội bộ và API sắp bị loại bỏ

Chạy trên artifact trước khi nâng cấp:

~~~bash
jdeps -jdkinternals application.jar
jdeprscan --release 26 --for-removal application.jar
jdeprscan --release 26 -l --for-removal
~~~

- jdeps -jdkinternals giúp tìm phụ thuộc vào package/class nội bộ JDK.
- jdeprscan giúp phát hiện API deprecated; tùy chọn --for-removal tập trung vào API được đánh dấu để loại bỏ.
- Kết quả static analysis không thay thế runtime test; reflection động có thể không được phát hiện đầy đủ.

JDK 26 đã loại bỏ Applet API và một số API khác, trong đó có Thread.stop(). JDK 26 cũng loại bỏ tool jrunscript. Nếu ứng dụng hoặc dependency còn phụ thuộc các thành phần đã bị loại bỏ, phải thay thế bằng API được hỗ trợ trước khi phát hành. Không lập kế hoạch quay lui dựa trên việc khôi phục công nghệ đã bị loại bỏ khỏi runtime mới. [Removed APIs](https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html) · [Removed Tools and Components](https://docs.oracle.com/en/java/javase/26/migrate/removed-tools-components.html)

### 6.3. Kiểm tra JVM flags

JDK mới có thể cảnh báo hoặc loại bỏ một số tùy chọn VM. JDK 26 migration guide yêu cầu xem warning về obsolete VM options và removed GC options khi thử chạy. Một số flag như AggressiveHeap, MaxRAM, AlwaysActAsServerClassMachine và NeverActAsServerClassMachine đã được đánh dấu deprecated for removal trong JDK 26.

Không copy toàn bộ JVM flags từ runtime cũ sang runtime mới. Với từng flag:

- Xác minh flag còn được hỗ trợ.
- Xác minh ý nghĩa và default có thay đổi không.
- Đo tác động đến heap, GC, startup và throughput.
- Bỏ flag nếu default mới đã phù hợp và không còn lý do kỹ thuật để giữ.
- Ghi lại đúng tập flags cho artifact/runtime rollback.

### 6.4. Kiểm tra thay đổi liên quan Java 26

| Thay đổi | Rủi ro khi nâng cấp | Bằng chứng cần lưu |
|---|---|---|
| HTTP Client hỗ trợ HTTP/3 | HTTP/3 không được chọn mặc định; nếu ứng dụng chủ động yêu cầu HTTP/3, proxy, firewall hoặc mạng có thể không cho phép QUIC/UDP. | Kết quả test HTTP/3, HTTP/2, timeout, retry và fallback theo cấu hình ứng dụng. |
| HPKE API trong Java SE 26 | Runtime/provider cũ không có thuật toán hoặc API tương ứng. | Ciphersuite, provider, key format và test interoperability. |
| UUIDv7 qua UUID.ofEpochMillis() | Binary dùng API Java 26 không chạy trên JDK 25. | Compiler release, artifact hash và bản build tương thích LTS nếu cần. |
| AOT Cache | Cache không phù hợp với build/runtime/OS/CPU hiện tại. | JDK build, application build, kiến trúc và cache artifact tương ứng. |
| G1 throughput improvements | Kết quả latency/throughput có thể khác cấu hình cũ. | Baseline GC, pause, allocation rate và throughput. |
| Final field integrity warnings | Dependency dùng deep reflection để thay đổi final field có thể phát warning hoặc bị giới hạn trong tương lai. | Danh sách warning, dependency và giải pháp tương thích đã kiểm thử. |
| Primitive patterns, Lazy Constants, Structured Concurrency | Đây là preview; class/API gắn với release tương ứng. | JEP, compile/runtime flags và artifact riêng. |
| Vector API | Incubator module, không phải API ổn định của Java SE. | Module name, CPU architecture, benchmark và artifact fallback scalar. |

JDK 26 có các cải tiến HTTP/3, G1, AOT cache và cảnh báo final-field mutation; các tính năng preview/incubator phải được đánh dấu riêng. [Significant Changes in JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)

Khi chuyển tiếp lên JDK 27, cần kiểm tra thêm thay đổi default của release đó: G1 trở thành collector mặc định trong mọi môi trường và Compact Object Headers được bật mặc định theo release notes. JDK 27 cũng tiếp tục các preview/incubator riêng. Đo lại memory, GC, startup và latency trên runtime thực tế thay vì mặc định rằng tuning của JDK 26 vẫn tối ưu. [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

## 7. Thiết kế database để binary cũ vẫn chạy được

Dữ liệu là phần khó nhất của rollback. Một bản JAR cũ có thể được phục hồi trong vài phút, nhưng không thể đọc schema đã bị xóa hoặc dữ liệu đã chuyển đổi không còn tương thích.

### 7.1. Dùng expand-contract

Chia migration thành các giai đoạn có thể cùng tồn tại:

1. **Expand:** thêm bảng/cột/index mới theo cách không phá vỡ ứng dụng cũ. Nếu phù hợp, thêm cột nullable hoặc default tương thích.
2. **Deploy compatible code:** bản ứng dụng mới đọc được schema cũ và mới; có thể ghi đồng thời hai dạng trong giai đoạn chuyển tiếp.
3. **Backfill:** chuyển dữ liệu theo batch có checkpoint, idempotent và có thể tiếp tục sau lỗi.
4. **Cut over:** chuyển đọc sang cấu trúc mới bằng feature flag hoặc cấu hình có version.
5. **Validate:** so sánh số dòng, checksum, tổng hợp nghiệp vụ, foreign key và dữ liệu mẫu.
6. **Contract:** chỉ xóa cột/bảng cũ sau khi hết thời gian rollback và đã xác nhận không còn consumer dùng chúng.

~~~mermaid
flowchart LR
    A["Schema cũ<br/>App cũ"] --> B["Expand schema<br/>App cũ vẫn chạy"]
    B --> C["App mới đọc/ghi tương thích"]
    C --> D["Backfill + đối soát"]
    D --> E["Chuyển đọc sang cấu trúc mới"]
    E --> F{"Hết cửa sổ rollback?"}
    F -->|Chưa| G["Giữ cấu trúc cũ và mới"]
    G --> E
    F -->|Rồi, đã xác minh| H["Contract: bỏ cấu trúc cũ"]
~~~

Không gộp expand, backfill và drop column vào một migration không thể tách. Nếu cần rollback binary, schema cũ phải còn nguyên hoặc vẫn có thể đọc qua lớp tương thích.

### 7.2. Dual-write phải có quy tắc đối soát

Ghi vào cả cột cũ và mới giúp hai phiên bản cùng hoạt động, nhưng có thể tạo dữ liệu lệch nếu một lần ghi thành công và lần còn lại thất bại.

Nếu dual-write được dùng:

- Ghi trong cùng transaction khi cả hai trường nằm trong cùng database và điều kiện transaction cho phép.
- Nếu ghi qua nhiều hệ thống, dùng outbox/CDC hoặc cơ chế đồng bộ có retry và idempotency.
- Ghi nhận lỗi đồng bộ và có công cụ đối soát.
- Chỉ chuyển nguồn đọc chính sau khi dữ liệu đã đạt điều kiện nhất quán.
- Không xóa đường ghi cũ trước khi bản cũ không còn được phép rollback.

AWS Prescriptive Guidance cũng khuyến nghị giữ tương thích ngược trong thời gian chuyển đổi, duy trì logic cũ có kiểm soát và dùng feature flag để quay lại đường xử lý đã xác minh. [Rollback strategy for business logic](https://docs.aws.amazon.com/prescriptive-guidance/latest/database-decomposition/logic.html)

### 7.3. Backfill phải có thể tiếp tục và kiểm chứng

Một backfill an toàn cần:

- Chia batch theo khóa ổn định hoặc khoảng ID.
- Ghi checkpoint đã xử lý đến đâu.
- Có thể chạy lại mà không nhân đôi hoặc làm hỏng dữ liệu.
- Lưu số bản ghi đọc, ghi, bỏ qua và lỗi.
- Kiểm tra checksum hoặc invariant nghiệp vụ.
- Có giới hạn tốc độ để không làm quá tải database production.

Không coi số lượng bản ghi được cập nhật là bằng chứng duy nhất. Cần kiểm tra quan hệ, nullability, giá trị mặc định và kết quả nghiệp vụ sau chuyển đổi.

### 7.4. Backup và point-in-time recovery

Trước migration có khả năng phá hủy hoặc chuyển đổi dữ liệu:

- Xác định backup nào sẽ dùng để phục hồi.
- Kiểm tra thời điểm backup và độ trễ replication.
- Thử restore vào môi trường cô lập.
- Kiểm tra tính nhất quán giữa database, object storage, message queue và các hệ thống ngoài.
- Đặt RPO và RTO cụ thể.
- Ghi rõ ai được phép thực hiện PITR và ai xác nhận dữ liệu sau phục hồi.

PITR có thể làm mất các giao dịch phát sinh sau restore point. Nếu phải phục hồi, cần xác định cách đối soát hoặc phát lại những giao dịch hợp lệ phát sinh sau thời điểm đó. Không tự động restore toàn bộ database chỉ vì một endpoint mới trả lỗi.

## 8. Cấu hình và secret cũng phải có phiên bản

Một rollback thường thất bại vì binary cũ nhận cấu hình chỉ dành cho binary mới.

Mỗi release cần lưu:

- Config version và hash.
- JVM flags.
- Feature flag snapshot.
- Endpoint/service discovery version nếu thay đổi.
- Database connection pool settings.
- HTTP protocol, TLS và cipher policy.
- Logging/metrics configuration.
- Secret reference và secret version.

### 8.1. Tách feature flag khỏi config triển khai

Feature flag hữu ích khi cần tắt một tính năng mà không cần build lại hoặc đổi runtime. Ví dụ:

| Feature | Cách quay lui |
|---|---|
| HTTP/3 | Tắt lựa chọn HTTP/3 hoặc chuyển sang HTTP/2 theo cấu hình đã kiểm thử. |
| Đường đọc schema mới | Chuyển về đường đọc cũ khi schema cũ còn được giữ. |
| Logic nghiệp vụ mới | Tắt flag và dùng implementation cũ đã kiểm chứng. |
| AOT cache | Tắt cache hoặc dùng cache đã xác minh với đúng runtime/build. |
| Vectorized processing | Chuyển sang implementation scalar nếu đã có và đã benchmark. |

Feature flag không thể làm cho class preview chạy được trên JDK khác release, cũng không thể tạo lại API đã bị thiếu trong runtime. Nếu binary tham chiếu API Java 26 thì phải chạy trên runtime tương thích.

### 8.2. Không khôi phục secret đã bị thu hồi

Nếu trong lúc rollout đã xoay vòng credential:

- Không khôi phục secret cũ nếu secret đó đã bị revoke hoặc nghi ngờ bị lộ.
- Kiểm tra binary cũ có đọc được secret version mới không.
- Nếu không, chuẩn bị bản tương thích hoặc quy trình xoay vòng credential mới.
- Không ghi secret vào manifest, ticket hoặc log.
- Giữ lịch sử secret version/reference đủ để xác định cấu hình đã dùng, nhưng quyền đọc secret vẫn phải được kiểm soát.

### 8.3. JVM flags là một phần của phiên bản

Đừng chỉ lưu JAVA_OPTS dưới dạng một chuỗi không kiểm soát. Hãy version hóa từng flag và giải thích lý do giữ nó. Khi quay lại runtime cũ, dùng tập flags đã kiểm chứng cho runtime đó; khi giữ runtime mới, không tự áp flags cũ nếu chúng đã deprecated hoặc thay đổi ý nghĩa.

## 9. Triển khai theo canary và đặt ngưỡng dừng trước

Không đưa toàn bộ traffic sang JDK mới ngay khi smoke test thành công. Hãy triển khai theo nhóm nhỏ hoặc theo một tập người dùng/instance được xác định.

Một tiến trình mẫu:

1. Build artifact và runtime image bất biến.
2. Kiểm thử trong staging với bản sao dữ liệu đã che thông tin nhạy cảm.
3. Chạy một instance canary không nhận traffic hoặc chỉ nhận traffic nội bộ.
4. Chuyển một phần nhỏ traffic.
5. Giữ cửa sổ quan sát đủ dài để đi qua các loại workload quan trọng.
6. Tăng tỷ lệ traffic theo từng bước nếu SLO đạt.
7. Chỉ hoàn tất rollout sau khi xác minh cả chỉ số kỹ thuật và nghiệp vụ.

Tỷ lệ 1%, 5%, 25%, 50%, 100% có thể dùng làm ví dụ, nhưng phải điều chỉnh theo quy mô, số replica, khả năng tách traffic và mức độ rủi ro của hệ thống.

### 9.1. Baseline và ngưỡng rollback

Trước phát hành, đo baseline từ phiên bản đang chạy. Đặt ngưỡng cụ thể cho:

- Tỷ lệ HTTP 5xx và lỗi nghiệp vụ.
- p95/p99 latency.
- Throughput và queue lag.
- CPU, heap, allocation rate và GC pause.
- OOM, crash, restart, thread starvation.
- Connection pool saturation và database latency.
- TLS handshake failures, HTTP protocol fallback.
- Số giao dịch thành công, sai lệch dữ liệu, duplicate event.
- Tỷ lệ request phải retry hoặc timeout.

Ví dụ ngưỡng minh họa:

| Chỉ số | Ví dụ điều kiện dừng | Hành động |
|---|---|---|
| HTTP 5xx | Cao hơn baseline 1 điểm phần trăm trong 5 phút | Dừng tăng traffic, kiểm tra canary; rollback nếu xác nhận liên quan release. |
| p99 latency | Cao hơn baseline 25% liên tục qua cửa sổ quan sát | Dừng rollout, so sánh trace và GC. |
| OOM/restart | Có OOM mới hoặc restart lặp lại | Dừng rollout ngay, giữ log và heap evidence an toàn. |
| Data invariant | Có giao dịch sai hoặc checksum không khớp | Tắt feature gây lỗi, bảo toàn dữ liệu, kích hoạt quy trình data incident. |
| TLS/authentication | Handshake hoặc xác thực thất bại tăng bất thường | Dừng rollout; không hạ chính sách bảo mật để che lỗi. |

Các con số trên chỉ là ví dụ. SLO và ngưỡng production phải được định nghĩa trước theo baseline, tải, mức độ ảnh hưởng và thời gian phát hiện của hệ thống.

## 10. Runbook rollback theo thứ tự

Runbook phải đủ cụ thể để người trực có thể thực hiện mà không phải suy đoán trong lúc incident.

### Bước 1: Xác nhận release và phạm vi ảnh hưởng

Ghi lại:

- Release ID, commit, image digest và runtime version đang lỗi.
- Thời điểm bắt đầu và nhóm traffic bị ảnh hưởng.
- Database schema version và migration ID hiện tại.
- Config version, feature flags và secret references.
- Metric, log, trace và event ID liên quan.

Không xóa Pod, log hoặc dữ liệu chẩn đoán trước khi lưu bằng chứng cần thiết.

### Bước 2: Dừng rollout

- Ngừng tăng tỷ lệ traffic.
- Pause pipeline hoặc rollout controller nếu cần.
- Giữ số replica ổn định để tránh thay đổi thêm trong lúc chẩn đoán.
- Nếu có feature flag gây lỗi, tắt flag đó theo quy trình đã thử.
- Không chạy migration contract/drop column trong thời gian xử lý.

### Bước 3: Kiểm tra tương thích trước khi đổi binary

Trả lời ba câu hỏi:

1. Binary cũ có chạy được với JDK hiện tại không?
2. Binary cũ có đọc/ghi được schema hiện tại không?
3. Binary cũ có đọc được config và secret hiện tại không?

Nếu cả ba điều kiện đạt, có thể rollback application artifact mà vẫn giữ JDK và schema mới.

Nếu binary cũ không chạy trên JDK hiện tại, cần khôi phục runtime cùng artifact đã kiểm chứng. Không đổi runtime riêng lẻ khi binary dùng API mới hơn runtime.

Nếu binary cũ không đọc được schema mới, không rollback vội. Chuyển sang đường dữ liệu tương thích hoặc thực hiện phục hồi dữ liệu theo kế hoạch đã diễn tập.

### Bước 4: Khôi phục artifact và runtime

- Chọn đúng artifact SHA-256 và image digest từ release manifest.
- Khôi phục JDK vendor/full version đã kiểm chứng.
- Khôi phục JVM flags tương ứng với runtime đó.
- Xác nhận module path và preview flags.
- Khởi động canary của bản cũ trước.
- Chạy smoke test và health check trước khi chuyển toàn bộ traffic.

Nếu chỉ lỗi ở tính năng mới, ưu tiên tắt feature flag hoặc quay về implementation tương thích. Không cần đổi JDK nếu nguyên nhân không nằm ở runtime.

### Bước 5: Khôi phục cấu hình

Dùng config snapshot của release mục tiêu, sau khi đối chiếu với trạng thái bảo mật hiện tại:

- Khôi phục protocol/feature flags đã kiểm chứng.
- Khôi phục pool sizes, timeout và JVM flags.
- Giữ secret mới nếu secret cũ đã bị revoke.
- Kiểm tra endpoint, certificate và permission.
- Xác nhận config hash sau khi triển khai.

### Bước 6: Xử lý database và dữ liệu

Chọn một trong ba hướng:

- **Schema vẫn tương thích:** giữ schema mở rộng và chạy binary cũ.
- **Dữ liệu mới không tương thích nhưng có thể chuyển đổi:** chạy migration bù hoặc replay event theo quy tắc idempotent.
- **Dữ liệu bị hỏng hoặc migration phá hủy:** dùng backup/PITR đã xác minh, sau đó đối soát và xử lý giao dịch phát sinh sau restore point.

Không tự chạy migration down nếu migration đó có thể làm mất dữ liệu hoặc không đảo ngược được. Migration down phải được kiểm thử với dữ liệu mô phỏng và có tiêu chí rõ ràng.

### Bước 7: Chuyển traffic và xác minh

- Chuyển traffic về bản canary cũ.
- Theo dõi health/readiness, lỗi, latency và throughput.
- Kiểm tra giao dịch nghiệp vụ, message queue, outbox và các job nền.
- So sánh dữ liệu mới phát sinh trong cửa sổ incident.
- Chỉ đóng incident khi metric ổn định và đối soát dữ liệu đạt yêu cầu.

## 11. Ví dụ rollback Kubernetes

Kubernetes hỗ trợ xem lịch sử rollout và quay về một revision Deployment trước đó:

~~~bash
kubectl rollout history deployment/order-service
kubectl rollout undo deployment/order-service --to-revision=12
kubectl rollout status deployment/order-service
kubectl get pods -l app=order-service
~~~

Thay order-service và revision 12 bằng giá trị thực đã xác minh.

**Giới hạn cần nhớ:** kubectl rollout undo chỉ khôi phục phần Pod template của Deployment. Nó không tự quay lui database, ConfigMap/Secret bên ngoài, message queue, feature flag service hoặc hệ thống khác. Nếu ConfigMap/Secret được tham chiếu bằng tên mutable, Pod cũ có thể vẫn nạp cấu hình mới. Vì vậy hãy version hóa config hoặc pin reference trong Pod template.

Giữ đủ Deployment history để rollback. Kubernetes mặc định giữ 10 ReplicaSet cũ; nếu đặt revisionHistoryLimit bằng 0, khả năng rollback qua lịch sử ReplicaSet sẽ bị loại bỏ. [Kubernetes Deployments: Rolling Back](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)

Với RollingUpdate, đặt maxUnavailable, maxSurge, readiness probe và progressDeadlineSeconds theo khả năng phục vụ thực tế. Một rollout bị stalled không tự bảo đảm ứng dụng đã được rollback; hệ thống giám sát hoặc quy trình vận hành phải phát hiện và quyết định hành động.

## 12. Ma trận quyết định theo tình huống

| Tình huống | Rollback phù hợp | Điều kiện trước khi thực hiện |
|---|---|---|
| JDK mới khởi động lỗi do JVM flag | Khôi phục runtime/flags hoặc bỏ flag không tương thích | Có image và command line đã kiểm chứng. |
| Ứng dụng lỗi sau khi dùng API Java 26 | Khôi phục artifact tương thích với runtime cũ hoặc giữ runtime Java 26 | Artifact cũ không gọi API thiếu trên runtime mục tiêu. |
| Preview API thay đổi giữa JDK 26 và 27 | Dùng artifact stable hoặc build riêng theo đúng release | Không dùng preview class file chéo release. |
| HTTP/3 lỗi qua proxy/firewall | Tắt HTTP/3 hoặc chuyển về protocol đã kiểm thử | Đường HTTP/2 hoặc protocol fallback hoạt động. |
| AOT cache không tương thích | Tắt hoặc tạo lại cache với đúng runtime/build | Có quy trình khởi động không phụ thuộc cache. |
| Vector API không có module/CPU phù hợp | Dùng implementation scalar đã kiểm chứng | Kết quả tính toán phải giống và hiệu năng đạt ngưỡng. |
| Schema đã expand nhưng chưa contract | Quay binary về bản cũ, giữ schema mở rộng | Binary cũ vẫn tương thích schema. |
| Schema đã drop cột hoặc chuyển đổi phá hủy | Migration bù hoặc PITR/backup | Có restore point và phương án xử lý giao dịch phát sinh. |
| Secret đã rotate | Giữ secret mới và cập nhật binary cũ nếu cần | Binary cũ phải đọc được secret version hiện tại. |
| Security/TLS regression | Dừng rollout, khôi phục runtime/config đã xác minh | Không hạ thuật toán hoặc trust policy để che lỗi. |

## 13. Ví dụ kế hoạch nâng cấp từ Java 25 lên Java 26

Giả sử dịch vụ hiện tại chạy Java 25 LTS, database schema v41, artifact 4.7.6. Bản Java 26 mới dùng UUID.ofEpochMillis() và bật một đường xử lý HTTP/3 tùy chọn.

Kế hoạch an toàn:

1. Lưu artifact 4.7.6, JDK 25 image digest, config snapshot và schema v41.
2. Chuẩn bị artifact mới build theo release 26, JDK/runtime 26 đã kiểm tra vendor/support.
3. Giữ schema v41 hoặc chỉ expand schema theo cách binary 4.7.6 vẫn đọc được.
4. Tách HTTP/3 thành feature flag; giữ protocol đã chạy ổn định làm đường mặc định ban đầu.
5. Triển khai canary với một nhóm request không quan trọng.
6. Đo p95/p99, lỗi kết nối, TLS, CPU, GC và dữ liệu nghiệp vụ.
7. Nếu HTTP/3 lỗi nhưng phần còn lại ổn định, tắt flag và giữ JDK 26.
8. Nếu JDK 26 runtime gây lỗi nghiêm trọng, quay về artifact/JDK 25 đã lưu. Artifact quay lui phải được build cho Java 25 và không được gọi UUID.ofEpochMillis() hoặc API chỉ có trong Java 26.
9. Giữ schema mở rộng và dữ liệu mới cho đến khi đã xác minh binary cũ đọc/ghi đúng.
10. Chỉ drop schema cũ sau khi cửa sổ rollback kết thúc và có xác nhận của chủ sở hữu dữ liệu.

Nếu hiện tại dịch vụ đã chạy Java 26 và muốn lên Java 27, lặp lại quy trình với baseline JDK 27. Kiểm tra các thay đổi runtime mặc định của JDK 27, các preview/incubator mới và khả năng tương thích của dependency. Không coi JDK 26 là fallback production an toàn nếu vendor đã kết thúc cập nhật cho bản phân phối đang sử dụng.

## 14. Diễn tập rollback

Một kế hoạch chỉ có giá trị khi đã thử khôi phục thật. Thực hiện diễn tập định kỳ trong staging hoặc môi trường khôi phục cô lập:

- Khôi phục artifact và image digest cũ từ registry.
- Khởi động artifact cũ trên schema đã expand.
- Khôi phục config snapshot và xác nhận secret version.
- Tắt một feature flag trong lúc có traffic giả lập.
- Tạo lỗi startup do JVM flag không tương thích và chạy runbook.
- Mô phỏng HTTP/3 bị chặn để kiểm tra đường protocol dự phòng.
- Mô phỏng dữ liệu backfill bị gián đoạn rồi chạy lại.
- Restore backup/PITR vào môi trường riêng và đo thời gian.
- Kiểm tra message queue, outbox và event replay không tạo duplicate.
- Ghi lại RTO thực tế, RPO thực tế, thao tác thủ công và điểm runbook còn mơ hồ.

Mỗi lần diễn tập cần có kết quả: thời gian phát hiện, thời gian quyết định, thời gian khôi phục traffic, thời gian đối soát dữ liệu và bằng chứng test. Nếu RTO/RPO vượt mục tiêu, điều chỉnh kế hoạch trước lần phát hành tiếp theo.

## 15. Những lỗi rollback thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ lưu tag image | Tag có thể trỏ sang image khác. | Lưu digest và giữ image trong registry. |
| Quay binary nhưng giữ runtime không tương thích | UnsupportedClassVersionError, NoSuchMethodError hoặc lỗi khởi động. | Lưu artifact/runtime pair đã kiểm chứng. |
| Quay runtime nhưng giữ binary dùng API mới | Runtime thiếu class/method/algorithm. | Build artifact riêng cho baseline rollback. |
| Rollback ứng dụng rồi rollback DB ngay | Mất dữ liệu mới hoặc binary cũ không còn chạy. | Giữ schema mở rộng trong cửa sổ rollback. |
| Chạy migration down chưa kiểm thử | Dữ liệu mất hoặc không nhất quán. | Dùng expand-contract, migration bù hoặc PITR đã diễn tập. |
| Khôi phục toàn bộ config cũ | Secret đã revoke hoặc policy bảo mật bị lùi. | Diff config và giữ trạng thái bảo mật hiện tại. |
| Chỉ tắt preview bằng feature flag | Class file vẫn phụ thuộc preview release. | Build artifact stable riêng và kiểm tra class-file version. |
| Dùng AOT cache từ build khác | Startup fail hoặc cache bị từ chối. | Pin cache theo runtime/application/OS/CPU và regenerate khi đổi. |
| Rollback Deployment nhưng không pin ConfigMap | Pod cũ nhận config mới. | Version hóa config reference trong Pod template. |
| Dùng JDK đã hết security update làm fallback | Quay lại trạng thái dễ bị khai thác. | Chọn fallback còn được vendor hỗ trợ hoặc roll-forward. |
| Không giữ ReplicaSet history | Không thể dùng rollout undo. | Đặt revisionHistoryLimit phù hợp và lưu manifest độc lập. |
| Chỉ kiểm tra health endpoint | Lỗi nghiệp vụ hoặc sai dữ liệu không bị phát hiện. | Thêm synthetic transaction và data invariant checks. |

## 16. Checklist trước khi phát hành

### Phiên bản và artifact

- [ ] Đã xác định JDK vendor, full version, build, OS và architecture.
- [ ] Đã xác minh support/update lifecycle của đúng vendor.
- [ ] Đã lưu application artifact hash và container image digest.
- [ ] Đã lưu compiler release, dependency lock hash và SBOM.
- [ ] Đã ghi rõ preview flags và incubator modules nếu có.
- [ ] Đã có artifact fallback tương thích với runtime rollback.
- [ ] Đã kiểm tra JVM flags, module options và startup command.

### Dữ liệu và cấu hình

- [ ] Schema migration theo expand-contract.
- [ ] Binary cũ đã được thử với schema sau expand.
- [ ] Backfill idempotent, có checkpoint và đối soát.
- [ ] Có backup/PITR, đã thử restore và biết RPO/RTO.
- [ ] Config có version/hash và có snapshot trước rollout.
- [ ] Feature flags có owner và đường tắt đã thử.
- [ ] Secret references đã ghi nhận; không rollback về secret bị revoke.
- [ ] Message/event format tương thích với consumer cũ.

### Triển khai và giám sát

- [ ] Có canary/blue-green hoặc rollout theo nhóm nhỏ.
- [ ] Baseline SLO và rollback thresholds đã định nghĩa.
- [ ] Có cảnh báo startup, 5xx, latency, GC, OOM, restart và data invariant.
- [ ] Đã xác minh health/readiness và synthetic transaction.
- [ ] Có người quyết định rollback và người phụ trách dữ liệu.
- [ ] Có runbook từng bước và quyền truy cập cần thiết.
- [ ] Đã diễn tập rollback gần nhất và ghi lại RTO/RPO.
- [ ] Deployment history và image digest cũ vẫn còn.

## 17. Bài tập thực hành

1. Tạo manifest cho một dịch vụ Java 25 đang chuẩn bị nâng lên Java 26; ghi artifact hash, JDK build, dependency lock, schema version, config hash và secret references.
2. Build hai artifact: một bản tương thích Java 25 và một bản dùng API Java 26. Xác minh bản nào có thể chạy trên từng runtime.
3. Thử chạy class preview Java 26 trên JDK 25 và JDK 27; giải thích vì sao phải build lại theo đúng release.
4. Viết migration expand thêm cột mới nhưng vẫn để binary cũ hoạt động.
5. Tạo backfill có checkpoint và chạy lại sau khi cố ý dừng giữa chừng.
6. Chạy đối soát dữ liệu giữa schema cũ và mới.
7. Tạo feature flag cho đường HTTP/3 và kiểm tra khả năng tắt mà không build lại.
8. Ghi lại JVM flags từ tiến trình đang chạy và so sánh với cấu hình release trước.
9. Dùng jdeps -jdkinternals và jdeprscan để rà soát dependency trước khi nâng JDK.
10. Thực hiện canary giả lập và kích hoạt rollback khi 5xx hoặc p99 vượt ngưỡng.
11. Dùng Kubernetes rollout history/undo để quay Pod template, sau đó xác minh ConfigMap/Secret và database vẫn ở trạng thái mong đợi.
12. Restore backup vào môi trường cô lập và đo thời gian đạt RTO/RPO.
13. Mô phỏng secret rotation trước rollback và chứng minh bản cũ vẫn kết nối được bằng credential hiện hành.
14. Viết một runbook phân biệt ba quyết định: rollback binary, rollback runtime và phục hồi dữ liệu.
15. Thực hiện diễn tập có người trực khác với người viết runbook để kiểm tra tính rõ ràng.

## 18. Mẫu quyết định rollback

Trước khi thực hiện, ghi ngắn gọn:

~~~text
INCIDENT_ID=
CURRENT_RELEASE_ID=
CURRENT_ARTIFACT_DIGEST=
CURRENT_JDK_VENDOR_VERSION=
CURRENT_SCHEMA_VERSION=
CURRENT_CONFIG_VERSION=
CURRENT_FEATURE_FLAGS_VERSION=

TARGET_ARTIFACT_DIGEST=
TARGET_JDK_VENDOR_VERSION=
TARGET_SCHEMA_COMPATIBILITY=
TARGET_CONFIG_VERSION=
TARGET_FEATURE_FLAGS_VERSION=

DATABASE_ACTION=KEEP_EXPANDED_SCHEMA | COMPENSATING_MIGRATION | PITR
DATA_BACKUP_OR_RESTORE_POINT=
RPO_TARGET=
RTO_TARGET=

TRIGGER=
EVIDENCE=
ROLLBACK_OWNER=
DATA_OWNER=
SECURITY_APPROVER=
POST_ROLLBACK_CHECKS=
DECISION=ROLLBACK | ROLL_FORWARD | DATA_RECOVERY
~~~

Không bắt đầu rollback dữ liệu nếu chưa xác định restore point, phạm vi mất dữ liệu có thể xảy ra và người chịu trách nhiệm xác nhận. Nếu chỉ cần tắt feature hoặc quay binary, không thực hiện phục hồi database không cần thiết.

## Tài liệu tham khảo chính thức

- [Oracle Java SE Support Roadmap — Updated October 20, 2026](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/index.html)
- [Preparing for Migration — JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html)
- [Significant Changes in JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [Removed APIs — JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html)
- [Removed Tools and Components — JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/removed-tools-components.html)
- [Consolidated JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)
- [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- [Kubernetes: Deployments and Rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes: Update a Deployment Without Downtime](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/)
- [Kubernetes: Container Images and Immutable Digests](https://kubernetes.io/docs/concepts/containers/images/)
- [AWS Prescriptive Guidance: Rollback Strategy for Business Logic](https://docs.aws.amazon.com/prescriptive-guidance/latest/database-decomposition/logic.html)

