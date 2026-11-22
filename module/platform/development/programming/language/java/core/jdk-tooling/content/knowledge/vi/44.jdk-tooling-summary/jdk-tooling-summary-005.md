# Checklist phát hành ứng dụng Java

Phát hành một ứng dụng Java là quá trình đưa một phiên bản đã được xác minh từ source code tới người dùng hoặc môi trường vận hành. Một release đáng tin cậy cần trả lời được các câu hỏi: **đang phát hành commit và version nào, được build bằng JDK/tool nào, đã qua những kiểm tra gì, artifact cuối cùng nằm ở đâu, làm sao xác minh artifact, triển khai thế nào và quay lui ra sao nếu có lỗi?**

Checklist này áp dụng cho thư viện Java, ứng dụng JAR, service Spring Boot, CLI, application distribution và artifact được đóng gói vào container. Không phải mục nào cũng áp dụng cho mọi dự án; hãy đánh dấu các mục không liên quan là N/A kèm lý do trong release record.

Một release hoàn chỉnh cần có artifact bất biến, version rõ ràng, kết quả kiểm thử, dependency/SBOM, checksum và chữ ký theo chính sách, release notes, kế hoạch triển khai và rollback. Không nên phát hành chỉ vì lệnh build kết thúc với exit code 0.

## 1. Xác định phạm vi và chủ sở hữu release

Trước khi build, ghi lại thông tin nhận diện release:

- Tên sản phẩm, service hoặc library.
- Version sẽ phát hành và loại version: stable, release candidate, beta hoặc snapshot.
- Source repository và commit SHA chính xác.
- Git tag tương ứng; nếu tổ chức yêu cầu, dùng annotated/signed tag.
- Người chịu trách nhiệm release và người phê duyệt.
- Môi trường nhận release: staging, canary, production hoặc Maven repository.
- Các issue, thay đổi và dependency được đưa vào phiên bản.
- Phạm vi thay đổi API, config, database schema và hành vi runtime.
- Ngày phát hành, cửa sổ triển khai và kênh thông báo.

Dùng version nhất quán trong POM/Gradle, manifest, artifact filename, container tag, release notes và deployment metadata. Không build từ một working tree có thay đổi chưa commit rồi ghi release như thể nó đến từ một commit sạch.

Nếu dùng Semantic Versioning, phân biệt:

- **MAJOR:** thay đổi không tương thích API/contract.
- **MINOR:** thêm chức năng tương thích ngược.
- **PATCH:** sửa lỗi tương thích ngược.
- **Pre-release:** ví dụ 2.5.0-rc.1, chưa phải stable release.

SemVer là quy ước về version, không tự bảo đảm binary compatibility. Với Java library, kiểm tra public API và compatibility bằng công cụ/phương pháp phù hợp với chính sách dự án.

## 2. Khóa source và Git state

Trước khi chạy release build:

```sh
git status --short
git rev-parse HEAD
git log -1 --oneline
git tag --list
```

Kiểm tra:

- Working tree sạch hoặc mọi thay đổi được commit có chủ đích.
- Commit thuộc đúng branch đã được review/merge.
- Pull request đã được phê duyệt và required checks đã pass.
- Tag chưa bị dùng cho một artifact khác.
- Không có file local, generated file hoặc secret vô tình được commit.
- Submodule/LFS content đã được checkout đúng revision nếu dự án dùng chúng.
- Git metadata được ghi lại trong release record.

Tạo tag theo quy trình của tổ chức sau khi version được chốt. Ví dụ tạo annotated tag:

```sh
git tag -a v2.5.0 -m "Release 2.5.0"
git show v2.5.0
```

Nếu tag đã được publish và gắn với release artifact, không di chuyển tag sang commit khác. Nếu phát hiện lỗi sau phát hành, tạo version/tag mới theo chính sách; giữ lại lịch sử để có thể audit.

## 3. Xác nhận JDK và build toolchain

Build cần chạy bằng JDK đã được dự án phê duyệt. Kiểm tra môi trường:

```sh
java --version
javac --version
jar --version
mvn --version
./gradlew --version
```

Không phải mọi lệnh đều cần trong cùng dự án; Maven project dùng Maven Wrapper, Gradle project dùng Gradle Wrapper. Wrapper giúp CI và developer sử dụng phiên bản build tool được pin trong repository.

Ghi lại:

- JDK vendor và version.
- Java release target.
- Maven/Gradle version.
- OS và architecture của build agent.
- Plugin/compiler version.
- Build flags và profile được bật.
- Dependency repository/mirror sử dụng.

### Java release target

Maven có thể khai báo:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Gradle Kotlin DSL có thể cấu hình toolchain và compiler release:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
```

Thay số 17 bằng Java release mà sản phẩm hỗ trợ. Tùy chọn --release giúp compiler kiểm tra language level, bytecode target và API của release được chọn. Chỉ đặt source/target mà không kiểm soát API có thể tạo bytecode chạy trên runtime cũ nhưng tham chiếu API mới hơn.

Đảm bảo test chạy trên các runtime được hỗ trợ, không chỉ trên JDK dùng để compile. Nếu support nhiều Java release, kiểm thử từng release theo ma trận đã công bố.

## 4. Khóa build và dependency

Build cần tái lập được càng nhiều càng tốt. Trước release:

- Dùng Maven Wrapper hoặc Gradle Wrapper đã được review.
- Pin version plugin và dependency.
- Tránh dynamic version như 1.+ hoặc latest.release trong release build.
- Bật dependency locking nếu dự án cần khóa resolved versions.
- Bật Gradle dependency verification để xác minh checksum/signature theo metadata đã review.
- Dùng repository được tổ chức phê duyệt; tránh repository không rõ nguồn.
- Kiểm tra dependency tree và các thay đổi transitive.
- Không để SNAPSHOT hoặc dependency mutable trong stable release trừ khi có ngoại lệ được phê duyệt.
- Ghi lại repository, version và checksum của artifact quan trọng.

Một số lệnh kiểm tra:

```sh
mvn -B -ntp dependency:tree
./gradlew dependencies
```

Gradle có thể tạo verification metadata bằng SHA-256:

```sh
./gradlew --write-verification-metadata sha256 help
```

Review metadata được tạo trước khi commit. Không tự động tin checksum mới chỉ vì Gradle vừa tải dependency đó; xác minh nguồn và version trước khi chấp nhận.

Với Maven, dùng repository manager có kiểm soát, cấu hình checksum policy phù hợp và bảo đảm release artifact không bị ghi đè. Checksum SHA-1/MD5 từ repository cũ không thay thế chữ ký hoặc SHA-256 được xác minh theo trust policy.

## 5. Kiểm tra source, code quality và API

Trước release, hoàn tất các kiểm tra phù hợp:

- Compile toàn bộ source set.
- Unit test và integration test.
- Test contract/API và serialization nếu có.
- Test database migration.
- Test trên runtime/OS được hỗ trợ.
- Static analysis và lint.
- Kiểm tra code formatting nếu là required check.
- Kiểm tra deprecated API và internal JDK API.
- Kiểm tra public API/binary compatibility cho library.
- Review các thay đổi về concurrency, thread lifecycle và shutdown.
- Kiểm tra xử lý lỗi, timeout, retry và resource cleanup.
- Xác nhận test không bị skip ngoài chủ đích.

Có thể dùng:

```sh
mvn -B -ntp clean verify
./gradlew --no-daemon clean check
```

Maven verify chạy các phase trước đó trong lifecycle, gồm compile, test và package theo cấu hình project. Gradle check chạy các verification task được cấu hình. Xem kết quả task/test report; không chỉ dựa vào dòng cuối của terminal.

Với ứng dụng Java, cân nhắc kiểm tra dependency/class references bằng jdeps:

```sh
jdeps --jdk-internals app.jar
jdeps --multi-release 17 --summary app.jar
```

Thay app.jar bằng artifact thực tế. Kết quả cần được xem xét theo module/dependency và Java release mục tiêu; jdeps không thay thế test runtime.

## 6. Kiểm tra bảo mật và license dependency

Trước khi phát hành:

- Chạy dependency vulnerability scan theo công cụ được tổ chức phê duyệt.
- Đánh giá CVE theo khả năng khai thác và mức độ ảnh hưởng, không chỉ điểm số.
- Kiểm tra license của direct và transitive dependency.
- Kiểm tra dependency bị bỏ bảo trì hoặc có version không được hỗ trợ.
- Kiểm tra secret scanning trên source, config và artifact.
- Xác minh không có private key, token, password hoặc credential trong repository/JAR/container.
- Review quyền truy cập build agent và signing service.
- Kiểm tra container base image và OS package nếu phát hành image.
- Ghi lại exception/risk acceptance có owner và expiry nếu chưa thể khắc phục.

Một dependency scan sạch tại thời điểm build không bảo đảm artifact an toàn mãi mãi. Lưu kết quả scan và theo dõi advisory mới theo chính sách vận hành.

## 7. Kiểm tra JAR hoặc distribution cuối cùng

Hãy kiểm tra artifact đã package, vì chạy code trong IDE không chứng minh artifact phát hành đúng.

Với JAR:

```sh
jar --list --file target/app.jar
unzip -p target/app.jar META-INF/MANIFEST.MF
```

Xác nhận:

- Tên artifact và version đúng.
- Main-Class đúng nếu là executable JAR.
- Resource bắt buộc đã được đóng gói.
- Không có file cấu hình development hoặc secret.
- Không có class/resource trùng lặp ngoài dự kiến.
- Dependency được cung cấp theo đúng mô hình: thin JAR, manifest Class-Path, fat JAR hoặc distribution.
- module-info.class và module descriptor đúng nếu dùng JPMS.
- Không chứa file tạm, test fixture, local path hoặc debug artifact ngoài chủ đích.

Chạy smoke test bằng chính artifact:

```sh
java -jar target/app.jar --version
```

Lệnh trên chỉ phù hợp nếu ứng dụng hỗ trợ option --version và JAR có đủ dependency. Với thin JAR hoặc distribution, dùng script/classpath được phát hành cùng artifact.

Không thay thế smoke test artifact bằng Maven exec:java, Gradle run hoặc chạy class từ IDE. Những lệnh đó có thể sử dụng build output và dependency classpath khác với artifact đã publish.

## 8. Kiểm tra runtime và cấu hình triển khai

Xác nhận trước khi phát hành:

- Java runtime tối thiểu và tối đa được hỗ trợ.
- JVM options: heap, GC, encoding, timezone và container memory nếu có.
- Environment variables bắt buộc.
- File cấu hình bên ngoài và thứ tự ưu tiên config.
- Port, bind address, DNS và proxy.
- File permission, service user và writable directory.
- Certificate, truststore, keystore và secret provider.
- Database/queue/cache endpoint và connection pool.
- Health, readiness và liveness endpoint.
- Graceful shutdown, timeout và xử lý SIGTERM.
- Resource limit và autoscaling policy.

Không đóng secret production vào JAR, manifest, Dockerfile, image layer hoặc release notes. Cung cấp secret qua secret manager hoặc cơ chế credential của nền tảng triển khai.

Giữ artifact giống nhau giữa staging và production khi có thể; cấu hình môi trường được inject lúc deploy. Nếu phải build riêng cho từng môi trường, ghi lại lý do và cách xác minh sự khác biệt.

## 9. Database migration và tương thích ngược

Nếu release thay đổi schema hoặc dữ liệu:

- Xem lại migration SQL và thứ tự thực thi.
- Test migration trên bản sao dữ liệu phù hợp.
- Đánh giá thời gian lock, dung lượng và thời gian chạy.
- Kiểm tra backward compatibility giữa code cũ và schema mới.
- Xác định migration có thể chạy lại an toàn hay không.
- Xác định cách xử lý nếu migration dừng giữa chừng.
- Sao lưu và kiểm tra khả năng phục hồi trước thay đổi rủi ro cao.
- Có kế hoạch expand-contract nếu nhiều phiên bản ứng dụng cùng chạy.

Một rollback binary không tự đảo ngược database migration. Thiết kế schema theo hướng code phiên bản cũ vẫn hoạt động trong giai đoạn chuyển tiếp; migration phá hủy dữ liệu cần kế hoạch riêng, backup và phê duyệt.

## 10. Tạo SBOM và provenance

SBOM (Software Bill of Materials) liệt kê component/dependency trong artifact, thường gồm tên, version, package identifier và license. Có thể dùng định dạng SPDX hoặc CycloneDX theo chính sách tổ chức.

Trước release:

- Tạo SBOM từ dependency thực tế được resolve.
- Liên kết SBOM với đúng version và checksum artifact.
- Kiểm tra component bị thiếu hoặc version không xác định.
- Lưu SBOM cùng release metadata.
- Cập nhật SBOM nếu artifact thay đổi sau build.

Provenance ghi lại artifact được tạo từ source revision, builder, workflow và tham số nào. Với release quan trọng, lưu attestation có thể xác minh thay vì chỉ ghi các dòng mô tả trong release notes.

SBOM không chứng minh artifact được build an toàn; provenance cũng không tự chứng minh code không có lỗ hổng. Hai loại metadata hỗ trợ inventory, audit và điều tra supply chain.

## 11. Ký artifact và tạo checksum

Nếu release policy yêu cầu ký JAR, ký sau khi package và mọi bước thay đổi artifact đã hoàn tất.

Ví dụ ký bằng jarsigner với keystore/alias được quản lý an toàn:

```sh
jarsigner -keystore release-keystore.p12 -storetype PKCS12 target/app.jar release-key
jarsigner -verify -strict -verbose -certs target/app.jar
```

Không đưa password keystore vào source code, script committed hoặc command line có thể bị lưu trong process log. CI nên lấy credential từ secret manager hoặc dùng signing service/workload identity. Giới hạn ai có thể ký và audit mỗi lần ký.

Sau khi ký, tính checksum của đúng file cuối cùng được phát hành:

Linux:

```sh
sha256sum target/app.jar > target/app.jar.sha256
sha256sum --check target/app.jar.sha256
```

macOS:

```sh
shasum -a 256 target/app.jar
```

Windows PowerShell:

```powershell
Get-FileHash -Path .\target\app.jar -Algorithm SHA256
```

Checksum xác nhận bytes khớp digest tham chiếu; nó không tự xác thực nhà phát hành nếu file và digest cùng đến từ nguồn bị kiểm soát. Khi cần authenticity, ký manifest/artifact và xác minh certificate/identity theo trust policy.

Nếu JAR được ký, checksum phải được tạo sau bước ký. Nếu sau đó thay đổi JAR, checksum và chữ ký cần được tạo lại.

## 12. Đặt tên và publish artifact bất biến

Một release nên có tên và tọa độ ổn định, ví dụ:

```text
orders-service-2.5.0.jar
orders-service-2.5.0.jar.sha256
orders-service-2.5.0.jar.asc
orders-service-2.5.0-sbom.json
release-notes-2.5.0.md
```

Tên file thực tế tùy quy ước repository. Đảm bảo artifact, checksum, signature, SBOM và release notes cùng trỏ tới một version/build.

Nguyên tắc publish:

- Publish vào repository/registry đã được phê duyệt.
- Không ghi đè release version đã phát hành.
- Không dùng latest làm định danh duy nhất cho production.
- Lưu artifact theo version/digest.
- Giới hạn quyền upload và delete.
- Bật audit log và retention.
- Xác minh artifact sau khi upload bằng cách download lại và kiểm tra checksum/signature.
- Không xóa release cũ khi vẫn còn deployment cần rollback hoặc dependency đang tham chiếu.

Với Maven, lệnh deploy publish artifact theo cấu hình distribution management/repository. Ví dụ:

```sh
mvn -B -ntp deploy
```

Với Gradle, dùng publishing plugin và task publish đã được cấu hình cho repository đích. Ví dụ:

```sh
./gradlew publish
```

Chỉ chạy bước publish từ pipeline release đã được phê duyệt.

## 13. Container image nếu ứng dụng được triển khai bằng Docker/Kubernetes

Nếu release có container image:

- Pin base image theo version/digest đã được phê duyệt.
- Dùng non-root user nếu ứng dụng không cần quyền cao.
- Không đưa secret vào image layer hoặc build argument có thể bị lưu.
- Chỉ copy artifact cần thiết vào final image.
- Kiểm tra image filesystem, exposed port, user và entrypoint.
- Quét OS package và dependency.
- Tạo SBOM cho image theo quy trình.
- Ký image và lưu digest.
- Deploy bằng digest khi cần bảo đảm chính xác image đã kiểm tra.

Tag image có thể bị di chuyển; digest nhận diện content cụ thể. Digest của container image khác checksum của JAR nằm bên trong image. Nếu cần xác minh cả hai lớp, ghi nhận cả artifact digest và image digest.

## 14. Kiểm thử staging và phê duyệt release

Trước production, triển khai cùng artifact dự kiến phát hành vào staging hoặc môi trường tương đương.

Kiểm tra:

- Ứng dụng khởi động và health/readiness thành công.
- Luồng nghiệp vụ quan trọng hoạt động.
- Authentication/authorization đúng.
- Database migration và integration với dependency thành công.
- Log không có lỗi bất thường hoặc secret.
- Metrics/trace cho thấy latency và resource trong ngưỡng.
- TLS, certificate, DNS, proxy và network policy đúng.
- Graceful shutdown và restart hoạt động.
- Load/performance test phù hợp đã hoàn tất.
- Backup/restore và rollback procedure đã được xác nhận khi cần.

Ghi rõ ai phê duyệt production, thời điểm, artifact digest và điều kiện dừng triển khai. Nếu staging dùng artifact khác production, giải thích và xác minh khác biệt.

## 15. Triển khai production có kiểm soát

Chọn chiến lược phù hợp với kiến trúc:

- **Rolling deployment:** thay instance từng phần; cần tương thích giữa phiên bản cũ/mới trong giai đoạn chuyển tiếp.
- **Canary:** đưa một tỷ lệ nhỏ traffic vào version mới và theo dõi trước khi mở rộng.
- **Blue/green:** triển khai môi trường mới song song rồi chuyển traffic.
- **Maintenance window:** dùng khi migration hoặc thay đổi không tương thích cần ngừng dịch vụ.

Trước khi deploy:

- Xác minh artifact digest đúng với release được phê duyệt.
- Xác minh signature/provenance nếu policy yêu cầu.
- Xác nhận capacity và maintenance window.
- Kiểm tra backup, migration plan và rollback target.
- Chuẩn bị người trực và dashboard.
- Xác định ngưỡng tự động dừng hoặc rollback.

Trong khi deploy:

- Theo dõi tỷ lệ lỗi, latency, saturation, restart và health.
- Theo dõi database connection, queue lag và dependency failure.
- Mở rộng rollout theo từng bước.
- Dừng khi vượt ngưỡng đã định; không tiếp tục chỉ vì tiến trình deploy báo thành công.

## 16. Smoke test và xác minh sau deploy

Sau khi production nhận release:

- Kiểm tra version/commit đang chạy trên từng instance.
- Xác minh health và readiness.
- Gọi các luồng nghiệp vụ quan trọng bằng test account/dữ liệu an toàn.
- Kiểm tra response code, latency và error rate.
- Kiểm tra log, trace và alert.
- Kiểm tra kết nối database, cache, queue và dịch vụ ngoài.
- Xác nhận job nền, scheduler và consumer hoạt động.
- Kiểm tra cấu hình và secret được nạp đúng.
- Xác nhận không có instance cũ ngoài dự kiến.
- Lưu deployment timestamp, artifact digest và kết quả smoke test.

Health endpoint trả UP không có nghĩa toàn bộ nghiệp vụ hoạt động. Thực hiện smoke test cho các đường đi quan trọng nhưng không tạo giao dịch thật hoặc gửi thông báo thật ngoài kế hoạch.

## 17. Kế hoạch rollback

Mỗi release production cần có tiêu chí rollback trước khi triển khai.

Xác định:

- Điều kiện kích hoạt rollback: error rate, latency, crash loop, dữ liệu sai hoặc business KPI.
- Người có quyền quyết định.
- Artifact version/digest ổn định gần nhất.
- Cách chuyển traffic về version trước.
- Cách giữ hoặc rollback cấu hình.
- Database migration có tương thích với version trước không.
- Dữ liệu phát sinh trong thời gian chạy version mới được xử lý thế nào.
- Cách xác minh hệ thống đã ổn định sau rollback.

Rollback ứng dụng không luôn đồng nghĩa rollback database. Với migration phá hủy hoặc transform dữ liệu, có thể cần forward fix hoặc restore backup thay vì chạy migration ngược. Kiểm tra điều này trước release.

Không xóa artifact cũ ngay sau khi deploy. Giữ version trước trong repository và bảo đảm có thể tải lại khi cần.

## 18. Release notes và bàn giao vận hành

Release notes cần nêu:

- Version và ngày phát hành.
- Commit/tag hoặc build identifier.
- Tính năng mới và sửa lỗi đáng chú ý.
- Breaking change và deprecation.
- Thay đổi config/environment variable.
- Database migration và tác động dữ liệu.
- Dependency/JDK/toolchain thay đổi.
- Known issues và workaround.
- Artifact location, checksum/signature và SBOM.
- Hướng dẫn deploy, verify và rollback.
- Người liên hệ và kênh báo sự cố.

Bàn giao cho vận hành phải có thông tin đủ để nhận biết version, kiểm tra trạng thái, tìm log theo correlation ID và thực hiện rollback theo quyền được giao. Không đưa secret hoặc dữ liệu nhạy cảm vào release notes.

## 19. Theo dõi sau phát hành

Trong giai đoạn sau release, theo dõi:

- Error rate và exception mới.
- p50/p95/p99 latency.
- CPU, heap, GC pause và thread count.
- Connection pool, queue lag và retry.
- Database slow query và lock.
- Restart, OOM và crash.
- Security alert và authentication failure.
- Business metric quan trọng.
- Feedback từ người dùng và support ticket.

Đặt khoảng theo dõi theo mức độ rủi ro của release. Nếu phát hiện lỗi, liên kết log/trace với release version và commit để khoanh vùng nhanh.

Sau khi release ổn định:

- Đóng change/release ticket.
- Lưu kết quả QA, approval và deployment record.
- Lưu artifact, SBOM, signature, checksum và provenance theo retention.
- Thu hồi credential hoặc quyền tạm thời.
- Xóa dump/test data tạm theo chính sách.
- Cập nhật known issues và tài liệu vận hành.
- Tổ chức review nếu có incident hoặc rollback.

## 20. Lỗi thường gặp khi phát hành

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Build local pass nhưng CI fail | JDK/toolchain, env hoặc dependency khác | Dùng wrapper/toolchain pin và ghi build environment |
| JAR chạy trong IDE nhưng fail khi deploy | Artifact thiếu resource/dependency hoặc manifest sai | Smoke test đúng file đã package |
| UnsupportedClassVersionError | Runtime thấp hơn bytecode target | Dùng runtime đúng hoặc build với release thấp hơn |
| NoClassDefFoundError | Thin JAR thiếu runtime dependency | Đóng gói distribution/fat JAR hoặc cung cấp lib |
| Dependency thay đổi giữa hai build | Dynamic version hoặc lock chưa được dùng | Pin version và review dependency lock |
| Checksum sau upload không khớp | File hỏng, nhầm version hoặc upload nhầm artifact | Download lại, xác minh nguồn và digest |
| Signature verify fail | Artifact bị sửa sau ký hoặc certificate/trust policy lỗi | Ký sau package cuối, kiểm tra signer và chain |
| Publish ghi đè artifact cũ | Repository cho phép redeploy release | Bật immutable release policy và phân quyền |
| Production thiếu config | Secret/config không được inject đúng | Kiểm tra deployment config và secret provider |
| Migration làm version cũ không chạy | Schema thay đổi không backward-compatible | Dùng expand-contract và kiểm tra rollback |
| Health UP nhưng nghiệp vụ lỗi | Health check quá nông | Chạy smoke test nghiệp vụ và theo dõi telemetry |
| Rollback không khôi phục dữ liệu | Giả định migration có thể đảo ngược | Chuẩn bị backup/forward fix và kế hoạch dữ liệu |
| Release không truy vết được commit | Thiếu tag/build metadata/provenance | Lưu commit SHA, build ID và artifact digest |

## 21. Checklist tổng hợp theo giai đoạn

### Trước build

- [ ] Version, phạm vi và owner release đã được chốt.
- [ ] Commit/branch/tag đúng và working tree sạch.
- [ ] Review và required CI checks đã pass.
- [ ] JDK vendor/version, Java release và build tool đã được pin.
- [ ] Wrapper, plugin và dependency version đã được khóa.
- [ ] Repository và dependency verification đã được kiểm tra.
- [ ] Không có secret hoặc file local trong source.

### Build và kiểm thử

- [ ] Clean build thành công.
- [ ] Unit/integration/contract test đã pass.
- [ ] Static analysis/lint đã pass.
- [ ] Dependency vulnerability và license scan đã review.
- [ ] API/binary compatibility đã kiểm tra nếu là library.
- [ ] Database migration và backward compatibility đã test.
- [ ] Test trên Java runtime mục tiêu đã hoàn tất.

### Artifact và supply chain

- [ ] JAR/distribution có tên/version đúng.
- [ ] Manifest/Main-Class/resource/dependency đã kiểm tra.
- [ ] Chính artifact cuối cùng đã được smoke test.
- [ ] Không có secret, dev config hoặc file thừa.
- [ ] SBOM và provenance được tạo/lưu theo policy.
- [ ] Artifact được ký nếu policy yêu cầu.
- [ ] Checksum được tạo sau mọi bước thay đổi artifact.
- [ ] Signature/checksum được xác minh.
- [ ] Artifact được publish bất biến và download lại kiểm tra được.

### Triển khai và sau release

- [ ] Staging đã pass và có approval.
- [ ] Backup, migration, rollout và rollback đã sẵn sàng.
- [ ] Artifact digest production khớp release record.
- [ ] Smoke test production đã pass.
- [ ] Health, metrics, logs, traces và business metrics ổn định.
- [ ] Release notes và vận hành handoff đã hoàn tất.
- [ ] Credential/quyền tạm đã thu hồi.
- [ ] Artifact, SBOM, signature, checksum và audit record đã lưu.
- [ ] Ticket/change record đã đóng hoặc chuyển theo dõi.

## 22. Mẫu release record

Có thể lưu một bản ghi cho mỗi release để người khác truy vết mà không phải dựa vào lịch sử terminal:

```text
Product: orders-service
Version: 2.5.0
Git tag: v2.5.0
Commit: <full-commit-sha>
JDK: <vendor-and-version>
Java release target: 17
Build tool: Gradle Wrapper <version>
Build result: PASS
Test result: PASS
Security/license review: PASS
Artifact: orders-service-2.5.0.jar
SHA-256: <64-hex-digest>
Signature: <signature-reference>
SBOM: <sbom-reference>
Provenance: <attestation-reference>
Repository: <artifact-repository-location>
Staging approval: <approver-and-time>
Production deployment: <deployment-id-and-time>
Smoke test: PASS
Rollback target: <previous-version-and-digest>
Release owner: <owner>
```

Thay các giá trị mẫu bằng thông tin thật. Không ghi password, token, private key hoặc nội dung secret vào release record.

## 23. Tài liệu tham khảo

- Oracle Java SE 17 — java launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java SE 17 — jar tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Oracle Java SE 17 — jarsigner: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Oracle Java SE 17 — jdeps: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Apache Maven — Lifecycle Reference: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven JAR Plugin: https://maven.apache.org/plugins/maven-jar-plugin/
- Gradle User Manual — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle User Manual — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle User Manual — Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
- CycloneDX Specification: https://cyclonedx.org/specification/overview/
- SPDX Specification: https://spdx.github.io/spdx-spec/
- SLSA — Supply-chain Levels for Software Artifacts: https://slsa.dev/

Phát hành tốt là phát hành có thể truy vết và xác minh: biết chính xác source commit, JDK/toolchain, kết quả kiểm thử, dependency, artifact digest và người phê duyệt. Hãy smoke test đúng artifact cuối cùng, publish version bất biến, triển khai theo từng bước có quan sát và chuẩn bị rollback trước khi production nhận traffic.