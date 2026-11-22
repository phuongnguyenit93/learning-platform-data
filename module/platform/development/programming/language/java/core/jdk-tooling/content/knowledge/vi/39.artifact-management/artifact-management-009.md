# Artifact Retention cho Java build

## 1. Artifact retention là gì?

**Artifact retention** là chính sách xác định artifact build được lưu ở đâu, giữ trong bao lâu, ai được phép truy cập, khi nào được archive và điều kiện nào cho phép xóa.

Trong một dự án Java, artifact có thể gồm:

- JAR, WAR, EAR và các file ZIP phát hành.
- Maven POM, Gradle module metadata và file checksum.
- SBOM, chữ ký số, provenance attestation và release manifest.
- Test report, coverage report, build log và build scan.
- Container image, native image và package phụ trợ.
- Build output tạm của pull request, nightly build hoặc integration test.

Lưu giữ tốt giúp nhóm tải lại đúng binary đã phát hành, điều tra sự cố, đáp ứng kiểm toán, khôi phục sau sự cố và xác minh nguồn gốc artifact. Chính sách cũng phải kiểm soát dung lượng, chi phí và rủi ro lưu dữ liệu quá lâu.

Retention là một phần của software supply chain. Nếu artifact đã được triển khai trong production, nhóm cần biết chính xác file nào đã được dùng và có thể lấy lại file đó cùng metadata tương ứng.

## 2. Phân biệt artifact, cache, backup và archive

Bốn khái niệm này có mục đích khác nhau:

| Loại | Mục đích | Ví dụ |
|---|---|---|
| Build artifact | Kết quả được tạo từ một lần build. | JAR, WAR, SBOM, test report. |
| Cache | Tăng tốc thao tác có thể tạo lại. | Maven local repository, Gradle dependency cache. |
| Backup | Khôi phục dữ liệu sau lỗi, xóa nhầm hoặc thảm họa. | Backup repository manager, database và blob store. |
| Archive | Lưu dài hạn để tra cứu, kiểm toán hoặc tái lập release. | Release bundle, provenance, SBOM và build manifest. |

Không nên xem cache là nơi lưu artifact phát hành. Cache có thể bị xóa hoặc hết hạn mà không làm mất nguồn dữ liệu chính thức.

Backup cũng không thay thế retention policy. Backup có thể giữ một bản sao của dữ liệu đã bị xóa, nhưng cần biết bản sao nào phải khôi phục và thời điểm nào được phép phục hồi.

Archive nên chứa đủ dữ liệu để xác định và xác minh release, không chỉ một file JAR không có thông tin nguồn.

## 3. Phân loại artifact trước khi đặt thời hạn

Mỗi loại artifact có vòng đời riêng:

| Nhóm | Ví dụ | Cách lưu giữ |
|---|---|---|
| Pull request / feature build | JAR kiểm thử, test report. | Ngắn hạn, hết hạn tự động. |
| Nightly / integration build | Binary dùng cho test tích hợp. | Giữ đủ để điều tra regression gần đây. |
| Maven SNAPSHOT | 1.4.0-SNAPSHOT. | Giới hạn theo tuổi và số bản timestamp. |
| Release candidate | 1.4.0-rc.1. | Giữ đến khi release hoặc hết thời gian đánh giá. |
| Stable release | 1.4.0. | Giữ theo thời gian hỗ trợ và yêu cầu audit. |
| LTS / regulated release | Bản phát hành có cam kết hỗ trợ dài hạn. | Theo hợp đồng, luật và legal hold. |
| Dependency cache | .m2, Gradle cache. | Xóa được khi có thể tải/tái tạo lại. |
| Release evidence | SBOM, signature, provenance, manifest. | Giữ cùng hoặc lâu hơn artifact liên quan. |

Không áp dụng một thời hạn duy nhất cho tất cả nhóm. Một test artifact chỉ dùng trong vài ngày có vòng đời khác với một JAR đã triển khai cho khách hàng.

## 4. Xây dựng retention policy

Một policy cần trả lời các câu hỏi:

1. Artifact thuộc loại nào?
2. Nơi lưu trữ chính thức là gì?
3. Thời gian được tính từ ngày build, ngày publish, ngày release hay lần tải cuối?
4. Có giữ tối thiểu một số version gần nhất không?
5. Có release nào phải được bảo vệ vì đang được hỗ trợ không?
6. Có legal hold, audit hold hoặc customer contract không?
7. Ai phê duyệt ngoại lệ và ai được phép xóa?
8. Sau khi hết hạn, artifact bị xóa ngay, soft-delete hay chuyển sang archive?
9. Metadata và bằng chứng xác minh có bị xóa cùng binary không?
10. Làm thế nào chứng minh cleanup đã chạy đúng?

Nên đặt policy thành cấu hình có version, owner, ngày hiệu lực và lý do. Không dựa vào một lệnh xóa thủ công không có audit trail.

## 5. Ví dụ retention matrix

Bảng dưới đây là điểm khởi đầu minh họa cho một nhóm Java thông thường. Đây không phải thời hạn pháp lý hay quy định bắt buộc; tổ chức cần điều chỉnh theo vòng đời sản phẩm, hợp đồng và compliance.

| Artifact class | Thời hạn ví dụ | Điều kiện giữ thêm |
|---|---:|---|
| Pull request build | 14 ngày | Giữ lâu hơn nếu đang điều tra lỗi. |
| Nightly / integration | 60 ngày | Giữ bản liên quan regression hoặc release candidate. |
| SNAPSHOT | 30 ngày | Giữ ít nhất 5 bản timestamp gần nhất. |
| Release candidate | 90 ngày sau quyết định release | Giữ nếu có incident hoặc audit đang mở. |
| Stable release | Trong thời gian hỗ trợ + 2 năm | Không xóa khi còn được triển khai. |
| LTS release | Theo chính sách LTS/hợp đồng | Giữ cả release evidence. |
| Build logs | 90 ngày | Giữ log release và log liên quan security incident lâu hơn. |
| Maven/Gradle cache | 30 ngày không sử dụng | Có thể tái tạo từ repository. |
| SBOM/signature/provenance | Ít nhất bằng thời gian giữ artifact | Giữ lâu hơn khi cần audit hoặc điều tra. |

Các con số chỉ minh họa cách chia lớp. Hãy ghi rõ đơn vị, mốc bắt đầu, timezone và cách xử lý ngày nghỉ/hết hạn trong policy thực tế.

## 6. Chọn mốc tính tuổi artifact

Retention có thể dựa trên nhiều loại thời gian:

- **Created/uploaded time:** thời điểm artifact được tạo hoặc publish.
- **Last downloaded time:** lần cuối consumer tải artifact.
- **Release date:** ngày bản release được phê duyệt.
- **End-of-support date:** ngày kết thúc hỗ trợ sản phẩm.
- **Legal hold release date:** ngày cơ quan có thẩm quyền cho phép bỏ hold.

Age-based policy phù hợp với build tạm và snapshot. Usage-based policy giúp nhận ra component không còn được sử dụng. Release support policy cần dựa trên lifecycle sản phẩm.

Chỉ dựa vào last downloaded có thể xóa một release hiếm khi được tải nhưng vẫn đang chạy ở production. Với stable release, hãy kết hợp support status, deployment inventory và release approval.

## 7. Maven release và SNAPSHOT có vòng đời khác nhau

Maven phân biệt release version và snapshot version.

Release:

~~~xml
<version>1.4.2</version>
~~~

Snapshot:

~~~xml
<version>1.5.0-SNAPSHOT</version>
~~~

Release version đại diện cho một bản phát hành cụ thể. Repository chính thức nên cấu hình để từ chối redeploy cùng release coordinates sau khi đã publish.

Maven không tự đảm bảo mọi repository server đều bất biến. Quy tắc không redeploy phải được thực thi ở repository manager hoặc release pipeline.

Snapshot là bản phát triển có thể được publish nhiều lần dưới cùng base version. Repository remote có thể lưu các file timestamped và dùng maven-metadata.xml để phân giải 1.5.0-SNAPSHOT tới lần deploy hiện tại.

Do đó, snapshot có thể được cleanup theo tuổi và số bản cần giữ. Stable release cần retention dài hơn và phải được bảo vệ khỏi cleanup snapshot.

## 8. Cấu hình Maven repository cho release và snapshot

Ví dụ distributionManagement:

~~~xml
<distributionManagement>
  <repository>
    <id>internal-releases</id>
    <url>https://repo.example.com/repository/maven-releases/</url>
  </repository>
  <snapshotRepository>
    <id>internal-snapshots</id>
    <url>https://repo.example.com/repository/maven-snapshots/</url>
  </snapshotRepository>
</distributionManagement>
~~~

Credential được cấu hình trong settings.xml theo đúng repository ID:

~~~xml
<settings>
  <servers>
    <server>
      <id>internal-releases</id>
      <username>BUILD_USER</username>
      <password>INJECTED_SECRET</password>
    </server>
    <server>
      <id>internal-snapshots</id>
      <username>BUILD_USER</username>
      <password>INJECTED_SECRET</password>
    </server>
  </servers>
</settings>
~~~

Trong CI, lấy credential từ secret manager hoặc secret store của pipeline. Không commit password/token vào POM, settings.xml trong repository hoặc artifact.

Dùng Maven Wrapper và deploy bằng:

~~~bash
./mvnw -B -ntp clean deploy
~~~

Maven chọn release repository hay snapshot repository theo version của project. Repository manager cần áp dụng quyền publish, chính sách redeploy và cleanup riêng cho từng repository.

## 9. Maven repository layout và dữ liệu cần giữ

Maven repository layout biến coordinates thành đường dẫn.

Ví dụ:

~~~text
com/acme/payment-service/1.4.2/
  payment-service-1.4.2.jar
  payment-service-1.4.2.pom
  payment-service-1.4.2.jar.sha1
  payment-service-1.4.2.jar.md5
  payment-service-1.4.2.pom.sha1
  payment-service-1.4.2.pom.md5
~~~

Một repository có thể có thêm detached signature .asc, SHA-256 sidecar và file metadata. Maven metadata maven-metadata.xml hỗ trợ version discovery và snapshot resolution.

Không xóa riêng POM hoặc metadata theo cách khiến artifact còn tồn tại nhưng không còn resolve được qua Maven coordinates. Không tự xóa file snapshot timestamp mà bỏ qua metadata quản lý snapshot.

Repository manager hiểu package layout và quan hệ giữa các asset; nên dùng cleanup policy của manager thay vì xóa file trực tiếp trên blob storage.

## 10. Snapshot timestamp và cleanup

Một remote snapshot có thể được lưu với tên timestamp:

~~~text
retention-demo-1.0.1-20261110.142015-3.jar
retention-demo-1.0.1-20261110.142015-3.pom
maven-metadata.xml
~~~

Base version vẫn là 1.0.1-SNAPSHOT, nhưng lần deploy cụ thể có timestamp và counter.

Khi đặt retention cho snapshot, cân nhắc đồng thời:

- Giữ snapshot không quá số ngày quy định.
- Giữ ít nhất N lần deploy gần nhất.
- Không xóa snapshot đang được release candidate hoặc integration test sử dụng.
- Có grace period sau khi phát hành release tương ứng.
- Bảo đảm repository metadata vẫn hợp lệ sau cleanup.

Ví dụ: giữ 5 snapshot mới nhất và xóa các bản cũ hơn 30 ngày, trừ snapshot được đánh dấu hold. Con số này phải phù hợp tốc độ build và nhu cầu rollback/debug của nhóm.

## 11. Giữ release bất biến

Một stable release đã được publish nên có các thuộc tính:

- Coordinates không thay đổi.
- Binary bytes không bị thay thế.
- Digest được lưu và có thể xác minh.
- POM và metadata phát hành được giữ cùng binary.
- SBOM, signature và provenance trỏ tới đúng digest.
- Release tag và source commit được ghi lại.

Nếu cần sửa lỗi, tạo version mới, ví dụ 1.4.3, rồi phát hành lại toàn bộ metadata. Không thay JAR của 1.4.2 bằng một binary khác mà giữ nguyên version.

Repository manager nên bật chính sách disable redeploy hoặc release immutability. Chỉ tài khoản release service có quyền publish; quyền delete cần hạn chế riêng.

## 12. Retention cho GitHub Actions artifacts

GitHub Actions lưu workflow artifacts và log files theo retention policy của repository/organization/enterprise.

Theo tài liệu GitHub hiện hành:

- Mặc định artifacts và workflow logs được giữ 90 ngày.
- Public repository có thể cấu hình từ 1 đến 90 ngày.
- Private repository có thể cấu hình từ 1 đến 400 ngày.
- Giới hạn của organization hoặc enterprise có thể thấp hơn.
- Thay đổi repository retention chỉ áp dụng cho artifact/log mới, không tự thay đổi thời hạn của artifact đã tạo.

Có thể đặt thời hạn riêng cho artifact trong workflow:

~~~yaml
- name: Upload test output
  uses: actions/upload-artifact@v4
  with:
    name: pull-request-test-output
    path: |
      target/*.jar
      target/surefire-reports/
    retention-days: 14
~~~

retention-days không vượt quá giới hạn của repository, organization hoặc enterprise.

GitHub Actions workflow artifact phù hợp để chia sẻ output giữa job hoặc tải kết quả kiểm thử. Release package cần được publish vào package/repository registry có lifecycle và access policy phù hợp. Không nên dùng thời hạn workflow artifact làm chính sách lưu giữ duy nhất cho binary đã phát hành.

## 13. Giữ log, test report và build evidence

Build log giúp giải thích vì sao một artifact được tạo ra. Test report cho biết kiểm thử nào đã chạy và kết quả ra sao.

Với Java/Maven, evidence thường gồm:

~~~text
target/
  surefire-reports/
  failsafe-reports/
  site/
  *.jar
  bom.json
  checksums.txt
~~~

Không cần giữ toàn bộ output tạm của mọi build trong thời gian dài. Hãy chọn những dữ liệu phục vụ điều tra và audit:

- Release build log.
- Unit/integration test report.
- Test summary và coverage report.
- Dependency tree hoặc resolved dependency manifest.
- JDK, Maven/Gradle và plugin versions.
- Source commit, workflow run ID và release tag.
- Digest của final artifact.

Nếu log có secret hoặc dữ liệu cá nhân, cần lọc trước khi archive. Không lưu nguyên environment dump chứa credential chỉ để giữ bằng chứng build.

## 14. SBOM, chữ ký và provenance phải theo cùng artifact lifecycle

Một release bundle có thể gồm:

~~~text
release/
  payment-service-1.4.2.jar
  payment-service-1.4.2.pom
  bom.cdx.json
  SHA256SUMS
  payment-service-1.4.2.sigstore.json
  provenance.intoto.jsonl
  release-manifest.json
~~~

SBOM mô tả component; checksum xác định bytes; signature xác thực signer; provenance giải thích source và builder. Những dữ liệu này cần được giữ cùng release hoặc lưu ở kho metadata có liên kết bằng digest.

Nếu JAR còn được dùng ở production, SBOM và provenance của nó cũng phải còn truy cập được. Khi điều tra lỗ hổng dependency, nhóm cần biết release cụ thể có chứa component nào và build từ commit nào.

Không tạo SBOM mới rồi gắn nó với release cũ nếu dependency graph hoặc artifact bytes đã thay đổi. Mỗi lần phát hành cần xác định final artifact, tạo metadata tương ứng và lưu digest.

## 15. Phân biệt retention của dependency cache

Maven local repository thường nằm ở:

~~~text
~/.m2/repository/
~~~

Gradle dependency cache thường nằm dưới:

~~~text
~/.gradle/caches/
~~~

Đây là cache để giảm thời gian tải dependency và plugin. Có thể xóa hoặc tạo lại từ repository nếu dependency vẫn tồn tại và có thể truy cập.

Không coi .m2/repository hoặc .gradle/caches trên một developer machine là kho lưu trữ chính thức của release. Release cần được publish vào repository manager hoặc package registry.

Với proxy repository, cache upstream có thể được cleanup theo usage/age. Nếu upstream xóa package hoặc thay đổi availability, cache đã giữ lại có thể giúp build cũ tiếp tục resolve. Hãy xác định dependency nào phải mirror nội bộ để hỗ trợ build lâu dài.

## 16. Retention policy trong Sonatype Nexus Repository

Nexus Repository hỗ trợ cleanup policy theo các tiêu chí như:

- Component age.
- Component usage/last downloaded.
- Release type, ví dụ RELEASES hoặc PRELEASES.
- Giữ một số version mới nhất khi format, edition và storage backend hỗ trợ.

Cleanup policy được tạo, gắn vào repository và thực thi bằng cleanup task. Tài liệu Sonatype lưu ý cleanup policy không nhất thiết được cấu hình sẵn; quản trị viên phải chọn policy và schedule phù hợp.

Một số phiên bản Nexus soft-delete component trước. Dữ liệu blob chưa được thu hồi ngay; cần task compact blob store để giải phóng dung lượng vật lý. Vì vậy, trạng thái component biến mất khỏi UI không đồng nghĩa storage đã giảm ngay.

Với Maven, tính năng giữ số version được hỗ trợ theo edition/phiên bản và PostgreSQL backend nhất định. Kiểm tra điều kiện triển khai thực tế trước khi dựa vào retain N versions.

Trước khi chạy cleanup trên production, hãy preview danh sách component bị ảnh hưởng và kiểm tra release đang được hỗ trợ.

## 17. Retention policy trong JFrog Artifactory

Artifactory cung cấp cleanup policy cho package và build information.

Một package cleanup policy có thể dựa trên:

- Packages older than.
- Packages not downloaded since.
- Property.
- Keep last N versions.

Có thể áp dụng policy theo repository, package type hoặc stage tùy khả năng của phiên bản và license.

Artifactory hỗ trợ dry run để tạo báo cáo các item dự kiến bị xóa. Nên review báo cáo này trước khi kích hoạt cleanup thật.

Cần phân biệt build-info retention với artifact retention. Khi xóa build record, tùy lựa chọn Delete Build Artifacts, artifact liên quan cũng có thể bị xóa. Kiểm tra setting này trước khi chạy policy.

Không xóa build metadata chỉ vì build đã cũ nếu artifact vẫn nằm trong release bundle, đang được triển khai hoặc cần phục vụ audit.

## 18. Retention trong object storage và archive

Một tổ chức có thể chuyển release evidence cũ sang object storage hoặc archive tier để giảm chi phí.

Cấu trúc lưu trữ ví dụ:

~~~text
java-releases/
  payment-service/
    1.4.2/
      artifact.jar
      artifact.pom
      bom.cdx.json
      SHA256SUMS
      provenance.intoto.jsonl
      release-manifest.json
~~~

Giữ manifest chứa:

- Maven coordinates và tên file.
- SHA-256.
- Source commit và release tag.
- Thời gian publish và ngày hết hạn.
- Retention class.
- SBOM/provenance reference.
- Trạng thái legal hold.
- Repository path hoặc storage object version ID.

Object storage có lifecycle transition để chuyển object sang tier lưu trữ rẻ hơn, nhưng cần tính thời gian retrieval, phí restore và thời gian khôi phục khi production cần tải lại release.

Không xóa repository index hoặc metadata cần cho consumer khi chỉ di chuyển binary sang archive. Hãy giữ một catalog có thể tra cứu release và vị trí archive.

## 19. WORM retention và legal hold

Với dữ liệu cần bảo vệ chống sửa/xóa, có thể dùng WORM (Write Once, Read Many) storage.

Amazon S3 Object Lock hỗ trợ retention period và legal hold trên object version:

- Governance mode cho phép người có quyền bypass đặc biệt thay đổi hoặc xóa trong một số điều kiện.
- Compliance mode ngăn xóa hoặc rút ngắn thời hạn của object version trong thời gian bảo vệ, kể cả bởi root user.
- Legal hold không có ngày hết hạn cố định và chỉ kết thúc khi người có thẩm quyền gỡ hold.
- Object Lock yêu cầu S3 Versioning được bật.

Compliance mode có thể rất khó đảo ngược trước ngày hết hạn. Chỉ dùng khi policy và yêu cầu pháp lý đã được xác nhận. Governance mode phù hợp hơn khi cần một lớp bảo vệ với quy trình ngoại lệ có kiểm soát.

Legal hold nên được gắn với object version/digest cụ thể. Khi có audit, tranh chấp hoặc incident investigation, đưa artifact và evidence liên quan vào hold trước khi cleanup chạy.

## 20. Retention không thay thế backup và disaster recovery

Một repository manager có thể lưu artifact đúng thời hạn nhưng vẫn mất dữ liệu do lỗi storage, lỗi cấu hình hoặc sự cố tài khoản.

Backup strategy cần xem xét:

- Artifact binary và POM.
- Repository database và metadata.
- Blob/object storage.
- Build-info, SBOM, signature và provenance.
- Repository configuration và cleanup policies.
- Encryption keys và quyền truy cập cần thiết để restore.

Backup phải được lưu ở failure domain độc lập. Nếu artifact và backup cùng bị xóa bởi một credential hoặc một lifecycle policy sai, khả năng khôi phục sẽ không còn.

Backup phải được restore test định kỳ. Kiểm tra không chỉ file có được phục hồi mà Maven/Gradle có resolve được coordinates, digest có khớp và signature/provenance có xác minh được hay không.

## 21. Thiết kế cleanup automation an toàn

Một cleanup pipeline nên có các bước:

1. Tính danh sách artifact đủ điều kiện hết hạn.
2. Loại artifact đang được deploy hoặc nằm trong supported release.
3. Loại artifact có legal hold, audit hold hoặc exception.
4. Giữ số version tối thiểu theo policy.
5. Tạo dry-run report.
6. Review số lượng, dung lượng và danh sách release bị ảnh hưởng.
7. Thực hiện soft-delete hoặc chuyển archive.
8. Chờ grace period theo policy.
9. Compact/garbage-collect storage nếu repository manager yêu cầu.
10. Lưu cleanup report và xác nhận trạng thái sau khi chạy.

Nên chạy theo repository hoặc project nhỏ trước khi mở rộng. Nếu cleanup task có thể xóa cả build-info và artifact, hãy kiểm tra tác động bằng dry run.

Cleanup nên idempotent: chạy lại không xóa nhầm artifact mới hoặc làm hỏng metadata đã cập nhật. Không chạy lệnh xóa dựa trên wildcard path nếu chưa kiểm tra package identity.

## 22. Ví dụ GitHub Actions giữ artifact theo thời hạn

Workflow có thể giữ output kiểm thử 14 ngày:

~~~yaml
- name: Run tests
  run: ./mvnw -B -ntp clean verify

- name: Upload test evidence
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: test-evidence
    path: |
      target/surefire-reports/
      target/failsafe-reports/
    if-no-files-found: warn
    retention-days: 14
~~~

if: always() giúp upload report kể cả khi test thất bại, miễn runner còn thực thi được bước upload.

Không upload credential, toàn bộ workspace hoặc file cấu hình cá nhân vào artifact. Đặt tên artifact có run ID hoặc commit reference để tránh nhầm lẫn giữa các lần chạy.

Nếu release evidence cần giữ lâu, publish nó vào release repository/archive có policy dài hạn và liên kết với digest. Workflow artifact ngắn hạn có thể phục vụ debug; release repository giữ bản chính thức.

## 23. Xác định artifact nào đang được dùng

Một policy dựa vào last download cần biết consumer nào sử dụng artifact.

Có thể thu thập:

- Repository access/download logs.
- Deployment manifest và container image digest.
- Maven dependency coordinates từ release manifest.
- Service inventory và version đang chạy.
- Release support status.
- Customer environment hoặc branch đang pin version.

Một artifact không có lượt tải gần đây vẫn có thể đang được deploy từ cache, container image hoặc mirror nội bộ. Vì vậy, last downloaded chỉ là một tín hiệu.

Trước khi xóa stable release, đối chiếu với deployment inventory, support matrix và release manager. Nếu không thể xác định usage, giữ artifact hoặc chuyển archive cho đến khi có bằng chứng.

## 24. Bảo mật quyền xóa và audit trail

Quyền publish và quyền delete nên được tách biệt.

Một mô hình có thể dùng:

- Developer: publish snapshot và tải artifact.
- CI release service: publish stable release theo protected workflow.
- Repository administrator: cấu hình retention policy.
- Cleanup service: chỉ xóa những nhóm artifact được policy cho phép.
- Auditor: đọc metadata và cleanup reports.
- Legal/compliance owner: yêu cầu và gỡ legal hold theo quy trình.

Ghi lại ai tạo/sửa policy, ai chạy cleanup, policy version nào được áp dụng, item nào bị xóa và số dung lượng được thu hồi.

Với release repository, yêu cầu approval bổ sung trước khi xóa một version đã phát hành. Không cấp quyền bypass WORM retention cho tài khoản CI thông thường.

## 25. Lỗi retention thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Workflow artifact biến mất | Đã hết retention-days hoặc repository policy. | Kiểm tra artifact expiry và publish release cần giữ lâu vào registry. |
| Release JAR bị ghi đè | Repository cho phép redeploy cùng version. | Bật immutable release/disable redeploy. |
| Snapshot repository phình to | Không có cleanup age/count. | Giới hạn tuổi và số timestamped snapshots. |
| Maven không resolve snapshot | Metadata snapshot bị xóa hoặc không đồng bộ. | Dùng repository manager cleanup thay vì xóa file trực tiếp. |
| Artifact còn trong UI nhưng storage không giảm | Repository manager soft-delete trước. | Chạy compaction/garbage collection theo tài liệu sản phẩm. |
| Cleanup xóa release đang dùng | Policy chỉ dựa trên age/last download. | Đối chiếu support/deployment inventory và thêm hold. |
| SBOM không còn sau khi JAR còn | Metadata có retention ngắn hơn artifact. | Giữ SBOM/signature/provenance ít nhất bằng artifact. |
| Không thể khôi phục sau xóa | Backup thiếu blob hoặc metadata. | Backup cả repository database và storage; thử restore định kỳ. |
| Archive có file nhưng không tìm được | Không có catalog/manifest. | Lưu coordinates, digest, source commit và object path. |
| Legal hold không bảo vệ bản cần thiết | Hold gắn nhầm object/version. | Định danh bằng object version và digest trước khi đặt hold. |
| Storage không giảm sau cleanup | Blob chưa được compact hoặc lifecycle chưa chạy. | Kiểm tra task compaction và báo cáo storage. |
| Cleanup xóa cache dependency cần cho build cũ | Proxy cache bị cleanup theo usage. | Mirror dependency quan trọng hoặc archive build inputs. |

## 26. Kiểm chứng Maven release và snapshot trong repository cục bộ

Một project Java 17 độc lập đã được deploy bằng Maven 3.9.12 và Maven Deploy Plugin 3.1.4 tới một file repository tạm.

Lần deploy thứ nhất dùng release version:

~~~xml
<version>1.0.0</version>
~~~

Maven tạo release coordinates trong repository và file JAR chạy thành công:

~~~text
artifact-retention=ready
~~~

Sau đó project được đổi thành:

~~~xml
<version>1.0.1-SNAPSHOT</version>
~~~

Lần deploy snapshot tạo file timestamped cùng maven-metadata.xml. Release 1.0.0 vẫn tồn tại và chạy được sau lần deploy snapshot.

Kết quả này xác nhận Maven deploy và repository layout hoạt động trong project kiểm thử. Nó không chứng minh repository manager production đã bật immutable release hoặc retention policy; các thiết lập đó cần được cấu hình và xác minh tại repository thực tế.

## 27. Quy trình archive một Java release

Khi một release sắp rời khỏi hot repository:

1. Xác định release coordinates, digest và source commit.
2. Kiểm tra release còn được deploy hay hỗ trợ không.
3. Thu thập JAR/WAR, POM, SBOM, checksum, signature và provenance.
4. Lưu test report và build metadata theo policy.
5. Tạo release manifest có ngày publish và ngày hết hạn.
6. Copy sang archive tier hoặc immutable storage.
7. Xác minh digest sau khi copy.
8. Kiểm tra signature và provenance trên artifact archive.
9. Thử resolve hoặc download từ archive theo quy trình restore.
10. Cập nhật catalog để consumer biết vị trí mới.
11. Chỉ cleanup bản hot sau khi archive đã được xác minh.
12. Lưu audit record của lần chuyển và cleanup.

Nếu repository manager hỗ trợ promote/copy release, dùng chức năng đó để giữ metadata và checksum. Không copy riêng file JAR rồi xóa thư mục Maven chứa POM/metadata.

## 28. Theo dõi và kiểm toán retention

Nên theo dõi:

- Tổng dung lượng theo repository và artifact class.
- Số release, snapshot và build artifact theo tuổi.
- Số artifact sắp hết hạn.
- Cleanup run success/failure và item count.
- Số item bị hold hoặc exception.
- Blob store compaction và dung lượng thực thu hồi.
- Thời gian restore một release.
- Tỷ lệ artifact có digest, SBOM và provenance.
- Số artifact đang được deploy nhưng gần hết hạn.

Mỗi quý hoặc theo chu kỳ release, kiểm tra policy có còn phù hợp với vòng đời sản phẩm không. Thử lấy lại một release cũ, xác minh digest, chạy smoke test và kiểm tra SBOM/provenance.

Lưu báo cáo cleanup và restore test để chứng minh retention policy được thực hiện. Nếu policy thay đổi, ghi version, người phê duyệt và ngày áp dụng.

## 29. Checklist trước khi bật cleanup production

- [ ] Artifact đã được phân loại theo CI, snapshot, release, cache và evidence.
- [ ] Mỗi class có owner và retention period.
- [ ] Mốc tính tuổi đã được xác định.
- [ ] Release repository từ chối redeploy version đã publish.
- [ ] Snapshot cleanup giữ đủ số bản cần cho rollback/debug.
- [ ] Stable release đang được hỗ trợ được bảo vệ.
- [ ] SBOM, checksum, signature và provenance theo cùng artifact.
- [ ] Build logs và test reports có retention riêng.
- [ ] Deployment inventory được đối chiếu trước khi xóa release.
- [ ] Legal hold và audit hold được kiểm tra.
- [ ] Backup gồm cả database, metadata và blob storage.
- [ ] Restore test đã chạy thành công.
- [ ] Cleanup dry run đã được review.
- [ ] Quyền publish, delete và bypass retention được tách biệt.
- [ ] Cleanup report và audit trail được lưu.
- [ ] Storage compaction/garbage collection đã được lên lịch nếu cần.
- [ ] Catalog/archive manifest cho phép tìm lại artifact cũ.

## 30. Tài liệu tham khảo

- Apache Maven — Repository Layout: https://maven.apache.org/repositories/layout.html
- Apache Maven — Repository Metadata: https://maven.apache.org/repositories/metadata.html
- Sonatype Nexus — Maven Repositories: https://help.sonatype.com/en/maven-repositories.html
- Sonatype Nexus — Cleanup Policies: https://help.sonatype.com/en/cleanup-policies.html
- Sonatype Nexus — Maven SNAPSHOT Tasks: https://help.sonatype.com/en/maven-snapshot-tasks.html
- JFrog Artifactory — Retention Policies: https://docs.jfrog.com/administration/docs/retention-policies
- JFrog Artifactory — Cleanup Policies: https://docs.jfrog.com/administration/docs/cleanup-policies
- GitHub Actions — Store and share workflow artifacts: https://docs.github.com/en/actions/tutorials/store-and-share-data
- GitHub — Manage Actions artifact and log retention: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
- Amazon S3 — Locking objects with Object Lock: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html

Artifact retention phải gắn với vòng đời thực tế của từng loại dữ liệu Java build. Hãy giữ release bất biến trong thời gian hỗ trợ, dọn snapshot và CI output theo age/count, lưu SBOM và provenance cùng digest, bảo vệ legal hold, đồng thời thử restore trước khi xóa bản chính thức.