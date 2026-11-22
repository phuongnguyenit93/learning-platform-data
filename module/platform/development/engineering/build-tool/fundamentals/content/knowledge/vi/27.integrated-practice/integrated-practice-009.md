# Thiết kế một chuỗi CI có lưu báo cáo và artifact truy vết được

Một chuỗi CI tốt không chỉ chạy lệnh build rồi trả về trạng thái xanh hoặc đỏ. Nó cần tạo ra bằng chứng cho biết source revision nào đã được kiểm tra, công cụ và dependency nào đã tham gia build, test nào đã chạy, artifact nào được tạo, artifact đó có đúng nội dung hay không và file nào đã được chuyển tới môi trường tiếp theo.

Khi pipeline chỉ giữ trạng thái job mà không lưu report hoặc artifact, nhóm có thể biết build thất bại nhưng khó tìm nguyên nhân; hoặc biết build thành công nhưng không thể xác định chính xác file nào đã được phát hành. Thiết kế CI cần coi **báo cáo** và **artifact có định danh** là đầu ra quan trọng của build.

Một chuỗi CI có thể được tổ chức theo luồng:

```text
Commit / Pull request
        |
        v
Checkout + record revision
        |
        v
Setup JDK + build tool wrapper
        |
        v
Compile + unit tests + static checks
        |
        v
Integration tests + package
        |
        v
Inspect artifact + smoke test
        |
        v
Create checksum + provenance + SBOM
        |
        v
Upload reports + immutable artifact
        |
        v
Promote/deploy exact artifact
```

Pipeline cần lưu báo cáo ngay cả khi một bước thất bại, trong giới hạn phù hợp với chính sách lưu trữ. Khi thành công, nó cần lưu chính artifact đã được kiểm tra cùng checksum và metadata truy vết. Nhờ đó, một người có thể đi từ commit tới build run, từ build run tới report, rồi từ report tới artifact và deployment record.

## 1. Mục tiêu của một chuỗi CI có thể truy vết

Một pipeline có khả năng truy vết cần trả lời được các câu hỏi:

- Artifact được tạo từ commit/tag nào?
- Build chạy trong workflow/job nào và thời điểm nào?
- JDK, Gradle/Maven Wrapper, plugin và dependency quan trọng nào được sử dụng?
- Unit test, integration test, static analysis và các quality gate nào đã chạy?
- Có test nào fail, skip, retry hoặc không được thực thi không?
- Báo cáo nằm ở đâu và được giữ trong bao lâu?
- Artifact được tạo ở bước nào, có version/digest nào và được lưu ở đâu?
- Artifact đã qua kiểm tra nội dung, checksum, chữ ký hoặc smoke test nào?
- Artifact được deploy lên môi trường nào và có đúng digest đã kiểm tra không?
- Ai hoặc workflow nào đã publish/promote artifact?

Các mục tiêu này hỗ trợ nhiều hoạt động:

| Mục tiêu | Giá trị |
|---|---|
| Debug build | Có log, test report và môi trường để tìm nguyên nhân |
| Review thay đổi | Reviewer thấy test và quality gate thực sự đã chạy |
| Release | Biết artifact nào được phép phát hành |
| Incident response | Truy ngược deployment tới artifact, commit và dependency |
| Rollback | Tìm lại chính xác artifact của phiên bản trước |
| Audit/compliance | Có bằng chứng build, kiểm tra, phê duyệt và publish |
| Tối ưu CI | Có thời gian task, cache và lịch sử build để phân tích |

## 2. Phân biệt log, report và artifact

Ba loại đầu ra này có vai trò khác nhau.

| Loại | Nội dung | Ví dụ |
|---|---|---|
| Log | Diễn biến tiến trình và thông báo trong khi chạy | Gradle console output, Maven output, daemon log |
| Report | Kết quả có cấu trúc của một hoạt động kiểm tra/phân tích | JUnit XML, HTML test report, coverage report, static analysis report |
| Artifact | Sản phẩm build có thể dùng, phân phối hoặc triển khai | JAR, WAR, ZIP distribution, container image |
| Metadata/provenance | Thông tin nhận dạng và nguồn gốc artifact | Commit SHA, build ID, checksum, SBOM, attestation |

Log giúp điều tra trình tự xảy ra. Report giúp đọc kết quả theo test, rule hoặc metric. Artifact là sản phẩm được tạo. Metadata liên kết các phần này thành một chuỗi bằng chứng.

Không nên coi file log là test report hoặc coi file JAR là đủ bằng chứng cho release. Một JAR có thể tồn tại dù integration test không chạy; một test report có thể pass nhưng artifact được upload lại là file khác.

## 3. Xác định đầu vào và đầu ra của pipeline

Trước khi viết YAML hoặc script CI, hãy xác định contract của pipeline.

### 3.1. Đầu vào

Các đầu vào thường gồm:

- Source revision hoặc tag.
- Build script và wrapper.
- JDK/toolchain version.
- Dependency declarations, lockfiles và verification metadata.
- Build parameters/profile có chủ đích.
- CI environment và quyền truy cập repository.
- Các dịch vụ test như database, message broker hoặc container.

### 3.2. Đầu ra

Các đầu ra có thể gồm:

- Build log.
- Unit test report.
- Integration test report.
- Coverage/static analysis/security report.
- JAR/WAR/distribution hoặc container image reference.
- Checksum/signature.
- SBOM và provenance/attestation.
- Release/deployment metadata.

Không phải dự án nào cũng cần mọi loại report. Hãy chọn theo yêu cầu chất lượng và rủi ro sản phẩm, nhưng cần xác định rõ file nào phải tồn tại khi pipeline thành công và file nào cần được lưu khi pipeline thất bại.

## 4. Các stage nên có trong CI Java

Một pipeline Java thường có các stage sau. Tùy dự án, một số stage có thể gộp hoặc tách thành job riêng.

| Stage | Công việc | Bằng chứng/đầu ra |
|---|---|---|
| Checkout | Lấy source revision chính xác | Commit SHA, branch/tag, trạng thái working tree |
| Toolchain | Cài/chọn JDK và build tool wrapper | Java/Maven/Gradle version, toolchain info |
| Compile | Biên dịch source và generated source | Compile log, task result |
| Unit test | Chạy test nhanh và độc lập | JUnit XML, HTML report |
| Static analysis | Kiểm tra style, bug pattern, coverage hoặc policy | Analysis report, quality gate result |
| Integration test | Kiểm tra tương tác với service/database | Integration test report, service logs nếu cần |
| Package | Tạo JAR/WAR/distribution | Artifact file và metadata |
| Artifact verification | Kiểm tra archive, manifest, dependency, smoke test | Verification log/report, checksum |
| Publish/store | Lưu artifact và bằng chứng | Repository coordinates hoặc artifact run ID |
| Promotion/deploy | Đưa đúng artifact vào môi trường | Deployment record, digest, health check |

### 4.1. Fail fast và vẫn lưu report

Nếu compile thất bại, không cần chạy các bước phụ thuộc vào artifact chưa được tạo. Tuy nhiên, các report đã được tạo trước đó vẫn cần được lưu. Ví dụ unit test có thể chạy xong rồi integration test thất bại; pipeline cần giữ cả unit report và integration report.

Một cấu hình CI tốt tách hai quyết định:

- **Có tiếp tục stage phụ thuộc hay không?** Thường phụ thuộc exit code và quality gate.
- **Có upload report đã có hay không?** Thường cần thực hiện ngay cả khi job fail.

Nhiều CI platform có cơ chế `always`, `when: always`, `if: always()` hoặc post-job action. Hãy dùng cơ chế tương ứng để upload report sau khi lệnh build kết thúc, kể cả khi exit code khác 0.

## 5. Ghi nhận source revision và build identity

Mỗi lần chạy CI cần có một định danh không mơ hồ. Các trường nên lưu:

- Repository/project name.
- Commit SHA đầy đủ.
- Branch hoặc tag.
- CI provider và run/build ID.
- Job/stage ID.
- Thời điểm bắt đầu và kết thúc.
- Người hoặc event khởi chạy pipeline nếu nền tảng cung cấp.
- Trạng thái working tree, nếu build có thể dùng generated/uncommitted input.

Ví dụ file metadata:

```properties
project=order-service
version=2.4.0
source.revision=a1b2c3d4e5f6...
source.branch=release/2.4
ci.provider=example-ci
ci.run=18427
build.jdk=21
build.tool=Gradle 8.x
```

Đây là ví dụ về metadata có thể lưu cạnh artifact hoặc trong provenance. Không ghi token, password, hostname nội bộ hoặc đường dẫn workspace nếu không có lý do rõ ràng. Nếu thêm build timestamp, hãy hiểu nó làm artifact khác byte giữa các lần build; có thể lưu thời gian trong CI metadata bên ngoài artifact để giữ khả năng reproducible.

### 5.1. Build ID không thay thế commit SHA

Build ID định danh một lần chạy pipeline. Cùng commit có thể được build nhiều lần, do đó mỗi run có build ID khác nhau. Commit SHA xác định source revision nhưng không tự định danh JDK, dependency, build parameters hoặc artifact bytes.

Nên lưu cả hai:

```text
source revision: a1b2c3d...
CI run:          18427
artifact:        order-service-2.4.0.jar
SHA-256:         7f9e...
```

## 6. Chuẩn hóa môi trường build

Build trên CI cần dùng đúng toolchain mà dự án hỗ trợ. Nếu máy developer dùng JDK 21 nhưng runner tự động chọn JDK 17, kết quả có thể khác hoặc compile thất bại.

Ghi nhận:

```bash
java -version
javac -version
```

Gradle:

```bash
./gradlew --version
```

Maven:

```bash
mvn -version
```

Nên commit wrapper và dùng `./gradlew`/`mvnw` thay vì phụ thuộc version cài toàn cục. Với Gradle Java toolchain, khai báo language version phù hợp. Với Maven, cấu hình compiler release và plugin version rõ ràng.

### 6.1. Không chỉ ghi nhận JDK của shell

Gradle daemon có thể chạy bằng một JVM trong khi Java toolchain dùng một JDK khác để compile/test. Maven có thể chạy bằng JDK được chọn trong CI nhưng compiler plugin hoặc toolchain configuration chọn compiler khác. Khi điều tra lỗi, cần ghi nhận cả runtime JVM của build tool và toolchain thực tế nếu khác nhau.

### 6.2. Cố định dependency

Để pipeline có thể tái hiện, tránh version động không kiểm soát như `1.+` hoặc dependency thay đổi nội dung mà không đổi version. Dùng version rõ ràng, dependency locking/verification phù hợp và repository được quản lý.

## 7. Thu thập test report với Gradle

Gradle Java plugin dùng `Test` task và thường tạo:

```text
build/reports/tests/test/index.html
build/test-results/test/TEST-*.xml
```

HTML report thuận tiện cho con người. XML report phù hợp để CI platform nhập kết quả và hiển thị từng test case.

Ví dụ cấu hình:

```kotlin
tasks.test {
    useJUnitPlatform()
    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }
}
```

Sau khi chạy:

```bash
./gradlew test
```

CI nên upload cả HTML và XML report. Nếu pipeline có nhiều module, report có thể nằm ở nhiều thư mục `build/` tương ứng; cần cấu hình glob/path phù hợp để không bỏ sót.

### 7.1. Integration test riêng

Nếu dự án có source set `integrationTest` và task riêng, cần bật report cho task đó:

```kotlin
tasks.withType<Test>().configureEach {
    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }
}
```

Đoạn này áp dụng cho các `Test` task được cấu hình trong build. Hãy xác nhận task integration test thực sự được nối vào lifecycle như `check` hoặc được gọi trực tiếp trong CI.

Không nên chỉ upload `build/test-results/test/**` nếu integration test ghi report vào `build/test-results/integrationTest/**` hoặc thư mục khác.

### 7.2. Test report vẫn cần được upload khi test fail

Test task thường trả exit code khác 0 khi test fail. Nếu bước upload report chỉ chạy khi job thành công, báo cáo có giá trị nhất lại bị mất.

CI nên có post-step upload report với điều kiện chạy kể cả khi test step thất bại. Giữ lại:

- XML report.
- HTML report.
- Log console của test task.
- Service/container log nếu integration test dùng dịch vụ phụ trợ.
- Thông tin test retry hoặc flaky test nếu có.

## 8. Thu thập test report với Maven

Maven Surefire thường lưu report unit test trong:

```text
target/surefire-reports/
```

Maven Failsafe thường lưu report integration test trong:

```text
target/failsafe-reports/
```

Các file XML có dạng `TEST-*.xml`; report text cũng có thể được tạo tùy cấu hình. CI có thể đọc XML để hiển thị tổng số test, pass/fail/error/skipped.

Ví dụ Surefire/Failsafe được gắn vào lifecycle:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.2.5</version>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>3.2.5</version>
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

Chạy:

```bash
mvn clean verify
```

Surefire chạy unit test ở phase `test`; Failsafe thực hiện integration-test và xác nhận kết quả ở phase `verify` theo cấu hình. Nếu chỉ chạy `mvn package`, integration test có thể chưa được xác nhận theo lifecycle Failsafe.

### 8.1. Multi-module Maven

Với project nhiều module, report thường được tạo trong `target/` của từng module. CI cần thu thập report từ mọi module, ví dụ glob tương đương:

```text
**/target/surefire-reports/TEST-*.xml
**/target/failsafe-reports/TEST-*.xml
```

Hãy kiểm tra CI platform có hỗ trợ glob recursive và cách xử lý file không tồn tại. Không nên để upload step fail chỉ vì một module không có integration test nếu đó là cấu hình hợp lệ; nhưng cũng không được âm thầm bỏ qua report của module lẽ ra phải chạy test.

## 9. Báo cáo coverage và static analysis

Test report cho biết test nào chạy và kết quả ra sao. Coverage report cho biết phần code nào được thực thi trong test; static analysis report phát hiện một số vấn đề về code, style hoặc bug pattern.

Các loại report có thể gồm:

- JaCoCo XML/HTML coverage.
- Checkstyle/PMD/SpotBugs report.
- SonarQube hoặc quality platform analysis.
- Dependency vulnerability report.
- License compliance report.
- SBOM.

Ví dụ JaCoCo với Gradle:

```kotlin
plugins {
    jacoco
}

tasks.test {
    finalizedBy(tasks.jacocoTestReport)
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}
```

CI có thể upload:

```text
build/reports/jacoco/test/html/**
build/reports/jacoco/test/jacocoTestReport.xml
```

Đường dẫn phụ thuộc task/configuration và phiên bản plugin. Hãy kiểm tra output thực tế của dự án.

### 9.1. Quality gate cần được thể hiện rõ

Một report có thể được tạo nhưng không tự làm build thất bại khi metric vi phạm ngưỡng. Cần cấu hình quality gate trong plugin hoặc CI. Ví dụ, nếu coverage dưới ngưỡng, task verification phải fail hoặc CI phải đánh dấu gate không đạt.

Không nên chỉ upload report rồi coi như đã kiểm tra. Cần xác định metric nào là gate bắt buộc, ngưỡng bao nhiêu và ai chịu trách nhiệm xử lý exception.

## 10. Lưu log và chẩn đoán khi pipeline thất bại

Khi job fail, cần giữ log đủ để xác định task và nguyên nhân. Với Gradle:

```bash
./gradlew clean check build --stacktrace --info --console=plain
```

Với Maven:

```bash
mvn clean verify -e
```

Chỉ bật debug sâu (`--debug` hoặc Maven `-X`) khi cần vì log rất lớn và có thể chứa URL, đường dẫn hoặc thông tin nhạy cảm. Trước khi upload/chia sẻ, cần redaction.

Nên lưu:

- Console log đầy đủ.
- Test report.
- Build profile/scan nếu được phép.
- Dependency tree khi lỗi resolution.
- Thread dump nếu job treo.
- Service/container log cho integration test.
- Exit code và thời gian thực hiện.

### 10.1. Upload report khi job fail

Logic tổng quát:

```text
Run build/test command
        |
        +--> Exit 0: continue pipeline
        |
        +--> Exit non-zero: mark job failed
        |
        v
Always collect available logs and reports
        |
        v
Upload diagnostics
        |
        v
Stop downstream release/publish stages
```

Upload report sau failure không được làm pipeline chuyển từ failed thành success. Bước thu thập bằng chứng nên giữ trạng thái thất bại ban đầu.

## 11. Tạo và kiểm tra artifact

Sau verification, pipeline tạo artifact cần lưu. Với Gradle:

```bash
./gradlew clean check build
```

JAR thường nằm trong `build/libs/`. Với Maven:

```bash
mvn clean verify
```

JAR/WAR thường nằm trong `target/`.

Không nên giả định tên file cố định nếu version, classifier hoặc archive configuration thay đổi. Pipeline nên lấy đúng output từ task/build metadata hoặc dùng quy ước tên đã được xác nhận.

### 11.1. Kiểm tra nội dung archive

Với JAR/WAR:

```bash
jar tf build/libs/order-service-2.4.0.jar
```

Kiểm tra:

- Manifest và `Main-Class` nếu là executable JAR truyền thống.
- Class/resource bắt buộc.
- Dependency layout nếu là fat JAR hoặc distribution.
- Version metadata.
- Không có file tạm hoặc secret.

Với Maven, thay đường dẫn bằng file trong `target/`.

### 11.2. Smoke test trên artifact đã đóng gói

Unit test chạy trên class output có thể không phát hiện lỗi thiếu resource hoặc dependency trong JAR. Nếu ứng dụng có self-test:

```bash
java -jar build/libs/order-service-2.4.0.jar --self-test
```

Nếu ứng dụng là server, có thể khởi động tiến trình trong môi trường test, đợi health endpoint sẵn sàng, gửi request và dừng tiến trình có timeout. Với WAR, deploy lên servlet container tương thích và kiểm tra endpoint. Với distribution ZIP, giải nén vào thư mục tạm rồi chạy script bên trong.

Smoke test cần chạy đúng artifact sẽ được upload. Không dùng classpath IDE hoặc thư mục output khác để thay thế.

## 12. Định danh artifact bằng version và build metadata

Artifact nên gắn với:

- Project/module name.
- Release version.
- Classifier/extension nếu có.
- Source commit.
- CI run/build ID.
- JDK/build tool version.
- Dependency lock/verification state hoặc SBOM.
- Checksum.

Ví dụ file `build-info.properties` có thể chứa:

```properties
application=order-service
version=2.4.0
commit=a1b2c3d4e5f6
ci.run=18427
java.release=21
```

Chỉ nhúng metadata không nhạy cảm và ổn định. Build ID có thể thay đổi giữa hai lần build cùng commit; nếu yêu cầu byte-for-byte reproducibility, lưu build ID trong sidecar metadata/provenance thay vì trong artifact. Nếu dự án chủ động nhúng build ID, hãy coi đó là một phần output và không kỳ vọng hai lần build tạo byte giống nhau.

## 13. Checksum và xác minh tính toàn vẹn

Sau khi artifact được tạo, tính SHA-256:

```bash
sha256sum build/libs/order-service-2.4.0.jar > order-service-2.4.0.jar.sha256
```

PowerShell:

```powershell
Get-FileHash .\build\libs\order-service-2.4.0.jar -Algorithm SHA256
```

Khi artifact được tải ở job khác, tính lại hash và so sánh. Nếu không khớp, không tiếp tục publish/deploy.

Checksum giúp xác nhận file không thay đổi so với giá trị đã lưu. Nếu attacker có thể thay cả artifact và checksum ở cùng nơi, checksum không chứng minh nguồn gốc. Với release quan trọng, dùng chữ ký và provenance được xác minh bằng identity/key tin cậy.

## 14. Provenance và SBOM

**Provenance** ghi nhận cách artifact được tạo: source revision, builder, workflow, thời gian, tham số và các thông tin liên quan. Có thể lưu ở dạng attestation theo chuẩn/công cụ của tổ chức.

**SBOM** liệt kê các thành phần phần mềm trong artifact hoặc dependency graph. Định dạng thường gặp là CycloneDX hoặc SPDX.

Một gói release có thể gồm:

```text
release-2.4.0/
├── order-service-2.4.0.jar
├── order-service-2.4.0.jar.sha256
├── sbom.cdx.json
├── provenance.json
├── test-summary.json
└── release-metadata.json
```

Tên file chỉ minh họa. Tổ chức có thể lưu provenance/SBOM trong artifact repository, OCI registry, CI artifact storage hoặc hệ thống attestation riêng. Cần liên kết chúng với digest của artifact để tránh nhầm metadata của một build với file khác.

### 14.1. Không tự tạo provenance giả định

Một file JSON tự ghi `builder=trusted` không tự chứng minh build đáng tin cậy. Provenance có giá trị khi được tạo bởi hệ thống build/attestation được tin cậy, có chữ ký hoặc identity xác minh được và liên kết chính xác với digest artifact.

Nếu chưa có hệ thống attestation, vẫn có thể lưu metadata cơ bản như commit, CI run, toolchain, checksum và log; hãy mô tả đó là build metadata, không gọi nó là bằng chứng mật mã.

## 15. Upload artifact và report vào CI storage

CI platform thường có tính năng upload/download artifact theo workflow run. Cần phân biệt:

- **CI artifact storage:** lưu file của một lần chạy pipeline để job khác tải hoặc reviewer xem.
- **Package/artifact repository:** lưu package theo tọa độ/version để consumer phân giải lâu dài.
- **Container registry:** lưu image theo tag/digest.

CI artifact storage phù hợp để chuyển JAR và report giữa các job trong cùng workflow. Release lâu dài thường nên publish vào repository/registry chính thức.

### 15.1. Lưu report riêng với package

Có thể lưu report dưới dạng artifact CI riêng:

```text
ci-run-18427-reports.zip
  ├── unit-test-report/
  ├── integration-test-report/
  ├── coverage/
  └── build.log
```

Và package riêng:

```text
order-service-2.4.0.jar
order-service-2.4.0.jar.sha256
```

Tách riêng giúp đặt retention khác nhau. Test report/log có thể được giữ ngắn hơn hoặc theo chính sách điều tra; release artifact có thể cần giữ lâu hơn để rollback và audit.

### 15.2. Không upload toàn bộ workspace tùy tiện

Chỉ upload các file cần thiết. Upload toàn bộ thư mục có thể vô tình đưa vào:

- `settings.xml` hoặc `gradle.properties` chứa credential.
- `.env` và file secret.
- Cache lớn.
- File tạm và test data nhạy cảm.
- Debug dump không được phép chia sẻ.

Ưu tiên allowlist đường dẫn report và artifact. Trước khi upload, kiểm tra không có secret trong log hoặc file cấu hình.

## 16. Retention và khả năng truy xuất

Một report không có giá trị lâu dài nếu bị xóa trước khi nhóm cần điều tra. Một artifact release không thể rollback nếu repository đã xóa version cũ.

Xác định retention theo loại dữ liệu:

| Dữ liệu | Retention cần cân nhắc |
|---|---|
| Console log của pull request | Theo thời hạn CI và nhu cầu debug |
| Unit/integration test report | Đủ lâu để điều tra lỗi và xem xu hướng |
| Coverage/static analysis report | Theo chu kỳ quality tracking |
| Build artifact của commit chưa release | Theo nhu cầu test/review và dung lượng |
| Release artifact | Theo chính sách phát hành, rollback và audit |
| SBOM/provenance/signature | Theo vòng đời sản phẩm và yêu cầu supply chain |
| Deployment record | Theo yêu cầu vận hành/audit |

Không có một thời hạn phù hợp cho mọi tổ chức. Hãy xác định owner, dung lượng, quyền truy cập và quy trình xóa/archival. Với artifact release, tránh ghi đè cùng version và bảo đảm có thể tải lại đúng nội dung.

## 17. Tổ chức tên file và thư mục report

Tên report nên cho biết module, loại test và build identity nếu CI gom report từ nhiều module.

Ví dụ:

```text
reports/
├── order-domain/
│   ├── unit-tests/
│   └── coverage/
├── order-service/
│   ├── unit-tests/
│   └── integration-tests/
└── build/
    ├── build.log
    └── dependency-report.txt
```

Nếu CI upload mỗi job thành một artifact riêng, tên artifact có thể gồm project, run ID và loại dữ liệu, ví dụ `order-service-18427-test-reports`. Tránh tên chung như `reports.zip` nếu nhiều job có thể ghi đè hoặc khó phân biệt.

## 18. Ví dụ pipeline Gradle: build, report, checksum và upload

Lệnh build có thể là:

```bash
./gradlew clean check build --stacktrace --console=plain
```

Sau khi thành công, pipeline xác định JAR, kiểm tra file và tạo checksum:

```bash
test -s build/libs/order-service-2.4.0.jar
jar tf build/libs/order-service-2.4.0.jar > artifact-contents.txt
sha256sum build/libs/order-service-2.4.0.jar > artifact.sha256
```

Các tên file trên là ví dụ; nên lấy tên artifact từ cấu hình build thực tế hoặc task output provider. Nếu build có nhiều classifier/version, cần chọn đúng file.

Report có thể nằm tại:

```text
build/reports/tests/**
build/test-results/**
build/reports/jacoco/**
```

Trong CI, upload report bằng điều kiện luôn chạy, còn bước publish/deploy chỉ chạy nếu build và quality gate thành công.

### 18.1. Ví dụ GitHub Actions minh họa

Đoạn dưới đây minh họa một workflow dùng Gradle Wrapper, lưu test report kể cả khi job fail và chỉ upload JAR sau khi build thành công. Cần điều chỉnh JDK, tên artifact, version, retention và action version theo repository thực tế.

```yaml
name: Java CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Record build identity
        run: |
          mkdir -p ci-metadata
          printf 'commit=%s\n' "$GITHUB_SHA" > ci-metadata/build-info.txt
          printf 'run_id=%s\n' "$GITHUB_RUN_ID" >> ci-metadata/build-info.txt
          java -version 2> ci-metadata/java-version.txt
          ./gradlew --version > ci-metadata/gradle-version.txt

      - name: Build and verify
        run: ./gradlew clean check build --stacktrace --console=plain

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-reports-${{ github.run_id }}
          path: |
            **/build/reports/tests/**
            **/build/test-results/**
            **/build/reports/jacoco/**
            ci-metadata/**
          if-no-files-found: warn
          retention-days: 14

      - name: Create artifact checksum
        if: success()
        run: |
          sha256sum build/libs/order-service-2.4.0.jar > artifact.sha256

      - name: Upload application artifact
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: order-service-${{ github.sha }}
          path: |
            build/libs/order-service-2.4.0.jar
            artifact.sha256
            ci-metadata/**
          retention-days: 30
```

Workflow này minh họa cách lưu report kể cả khi build fail. Tên JAR được hard-code để dễ đọc; trong dự án thật nên đồng bộ với version và archive naming từ build logic. Nếu build fail trước khi tạo JAR, bước checksum/upload package sẽ không chạy. Nếu cần lưu partial artifact để debug, hãy tách riêng và đánh dấu rõ rằng nó không phải release candidate.

Không cấp publish credential cho pull request job này. Publish/release nên là job riêng với permission và approval phù hợp.

## 19. Ví dụ pipeline Maven: verify và thu thập report

Lệnh build chuẩn:

```bash
mvn -B -ntp clean verify -e
```

`-B` bật batch mode phù hợp CI; `-ntp` giảm progress transfer noise ở Maven version hỗ trợ; `verify` chạy lifecycle tới phase verification. Nếu project dùng Failsafe, integration test được thực hiện theo cấu hình plugin.

Report paths:

```text
**/target/surefire-reports/**
**/target/failsafe-reports/**
**/target/site/jacoco/**
```

Tạo checksum cho artifact:

```bash
sha256sum target/order-service-2.4.0.jar > artifact.sha256
```

CI nên upload test report sau khi lệnh Maven kết thúc kể cả khi exit code khác 0. Artifact release chỉ được upload/publish khi verification đạt.

### 19.1. Maven multi-module

Với nhiều module, artifact có thể nằm trong nhiều `target/` và test report cũng vậy. Nên xác định module nào tạo package phát hành và module nào chỉ tạo library dependency.

Nếu release gồm nhiều JAR, hãy lưu manifest/metadata release liệt kê từng tọa độ, checksum và module tương ứng. Không nên chỉ upload file đầu tiên tìm thấy bằng wildcard.

## 20. Phân tách job build, report và release

Pipeline lớn có thể tách thành nhiều job:

```text
                 +--------------------+
                 | Checkout + Build   |
                 +--------------------+
                           |
                           v
                 +--------------------+
                 | Unit/Integration   |
                 | Test + Analysis    |
                 +--------------------+
                           |
                           v
                 +--------------------+
                 | Package + Verify   |
                 +--------------------+
                           |
                           v
                 +--------------------+
                 | Store Artifact     |
                 | + Reports          |
                 +--------------------+
                           |
                     approval/gate
                           |
                           v
                 +--------------------+
                 | Promote / Deploy   |
                 +--------------------+
```

Khi tách job, cần chuyển đúng file giữa các job. Job deploy không nên checkout source rồi build lại nếu mục tiêu là deploy artifact đã được test.

### 20.1. Định danh artifact giữa các job

Không dùng “latest artifact” chung nếu nhiều pipeline có thể chạy đồng thời. Hãy dùng:

- CI run ID.
- Commit SHA.
- Artifact name/version.
- Checksum hoặc image digest.
- Repository coordinates.

Job downstream phải tải artifact thuộc đúng upstream run. Sau khi tải, xác minh checksum trước khi dùng.

## 21. Build once, promote many

Nếu cùng một release đi qua test, staging và production, nên build một lần rồi promote chính artifact đó.

```text
Build commit A
    |
    v
order-service-2.4.0.jar (SHA-256 = H)
    |
    +--> Deploy to test, verify H
    |
    +--> Deploy to staging, verify H
    |
    +--> Approve release
    |
    +--> Deploy to production, verify H
```

Các môi trường nhận cấu hình và secret riêng lúc runtime. Không sửa JAR để nhúng endpoint production hoặc build lại JAR khác cho staging.

Với container, dùng image digest thay vì chỉ dựa vào mutable tag. Với Maven/Gradle artifact, dùng version bất biến và checksum.

## 22. Gắn deployment record với artifact

Sau khi deploy, lưu thông tin:

- Environment.
- Artifact name/version/digest.
- Source commit.
- CI run/build ID.
- Thời điểm deploy.
- Workflow/job hoặc release identity.
- Kết quả health/readiness/smoke check.
- Approval/change reference nếu có.

Ví dụ deployment record:

```json
{
  "application": "order-service",
  "environment": "staging",
  "version": "2.4.0",
  "commit": "a1b2c3d4e5f6",
  "ciRun": "18427",
  "artifact": "order-service-2.4.0.jar",
  "sha256": "7f9e...",
  "deploymentStatus": "succeeded"
}
```

JSON trên chỉ minh họa schema. Dữ liệu thật cần được ghi vào deployment platform, release record hoặc hệ thống audit. Không nên chỉ lưu nó trong log không có retention.

## 23. Bảo vệ báo cáo và artifact

Report và artifact cũng có thể chứa thông tin nhạy cảm:

- Test report có thể chứa dữ liệu test hoặc giá trị request/response.
- Log có thể in URL, username, token hoặc cấu hình.
- Heap dump/thread dump có thể chứa dữ liệu runtime.
- Artifact có thể vô tình đóng gói `.env`, private key hoặc file local.
- SBOM/provenance có thể tiết lộ dependency nội bộ và thông tin build environment.

Các biện pháp:

- Chỉ upload file cần thiết.
- Kiểm tra log trước khi chia sẻ rộng.
- Redact secret ở nguồn và thu hồi token nếu đã lộ.
- Giới hạn quyền đọc artifact/report.
- Đặt retention phù hợp.
- Không cấp quyền publish cho job chạy mã không đáng tin cậy.
- Dùng HTTPS, access control và audit log của repository.
- Không coi log masking là biện pháp duy nhất bảo vệ secret.

## 24. Xử lý pipeline thất bại

Một pipeline thất bại vẫn nên tạo ra gói chẩn đoán hữu ích. Tuy nhiên, không được để bước upload report làm job xanh trở lại hoặc để downstream deployment tiếp tục.

Chính sách thường dùng:

| Kết quả | Upload report/log | Upload artifact release | Deploy |
|---|---|---|---|
| Compile fail | Có, nếu có log | Không | Không |
| Unit test fail | Có | Không, trừ partial artifact được đánh dấu rõ | Không |
| Integration test fail | Có | Không release | Không |
| Static analysis gate fail | Có | Theo policy; không promote | Không |
| Package fail | Có | Không | Không |
| Artifact verification fail | Có | Không release candidate | Không |
| Tất cả gate pass | Có | Có | Có thể sau approval |

Nếu muốn giữ artifact được tạo trước khi test fail để debug, hãy lưu vào khu vực riêng, gắn trạng thái `failed` hoặc `non-release`, và không cho downstream release job chọn nhầm.

## 25. Trạng thái test và báo cáo phải phản ánh đúng kết quả

Không nên suy luận “test pass” chỉ vì job có exit code 0 nếu test task bị skip hoặc report không được tạo như dự kiến.

Kiểm tra:

- Số test được phát hiện và thực thi.
- Số pass/fail/error/skipped.
- Test suite nào không chạy.
- Integration test có được gọi trong lifecycle không.
- Retry có che flaky test không.
- Report có timestamp/build identity đúng không.
- CI có import XML report thành công không.

Nếu một module không có test, report vắng mặt có thể hợp lệ. Nhưng với module bắt buộc có test, report thiếu cần được điều tra hoặc làm quality gate thất bại.

## 26. Tính tái lập và khả năng so sánh build

Nếu muốn so sánh artifact qua các lần build, cần kiểm soát:

- Wrapper/build tool và JDK.
- Plugin/dependency version.
- Repository và dependency locking.
- Timestamp và thứ tự file trong archive.
- Locale/timezone/encoding/line ending.
- Generated resource và absolute path.
- Environment variable ảnh hưởng output.

Gradle archive tasks có thể chuẩn hóa timestamp và file order. Maven plugin tương thích có thể dùng `project.build.outputTimestamp`. Những thiết lập này giúp tạo artifact ổn định hơn.

Tuy nhiên, build once/promotion không đòi hỏi phải build lại ở từng môi trường để so sánh checksum. Nó yêu cầu giữ nguyên artifact đã tạo. Reproducible build là lớp bổ sung để một bên độc lập có thể tái tạo artifact từ cùng input.

## 27. Theo dõi hiệu năng và độ tin cậy của pipeline

Ngoài trạng thái pass/fail, nên lưu metric:

- Total pipeline duration.
- Queue time và job duration.
- Compile/test/package task duration.
- Cache hit/miss.
- Test count và failure rate.
- Flaky test/retry count.
- Artifact size.
- Report upload/download duration.
- Tỷ lệ build thành công theo branch/repository.
- Thời gian từ commit tới artifact sẵn sàng.

Các metric giúp xác định pipeline chậm ở đâu và có ổn định không. Đừng tối ưu bằng cách bỏ quality gate để giảm thời gian; hãy tối ưu task, cache, test isolation hoặc phân chia job mà vẫn giữ hợp đồng build.

## 28. Một cấu trúc thư mục lưu release evidence

Ví dụ một gói evidence cho release:

```text
release-evidence/
└── order-service/2.4.0/
    ├── artifact/
    │   ├── order-service-2.4.0.jar
    │   └── order-service-2.4.0.jar.sha256
    ├── reports/
    │   ├── unit-tests/
    │   ├── integration-tests/
    │   ├── coverage/
    │   └── static-analysis/
    ├── metadata/
    │   ├── build-info.json
    │   ├── sbom.cdx.json
    │   └── provenance.json
    └── deployment/
        ├── staging.json
        └── production.json
```

Đây là cách tổ chức logic; file có thể nằm ở nhiều hệ thống khác nhau. Điều quan trọng là mọi file có liên kết bằng version, run ID và digest.

## 29. Checklist thiết kế CI có thể truy vết

### Source và môi trường

- [ ] Ghi commit SHA, branch/tag và CI run ID.
- [ ] Dùng Gradle/Maven Wrapper.
- [ ] Ghi JDK runtime và toolchain/compiler version.
- [ ] Cố định plugin/dependency và repository policy.
- [ ] Ghi các build parameter có ảnh hưởng output.

### Test và report

- [ ] Unit test được chạy và có XML/HTML report.
- [ ] Integration test được nối vào đúng lifecycle/task.
- [ ] Coverage/static analysis report được tạo nếu dự án yêu cầu.
- [ ] Report được upload kể cả khi job fail.
- [ ] Upload step không làm che trạng thái thất bại ban đầu.
- [ ] Report có thể liên kết với commit và run ID.

### Artifact

- [ ] Artifact được tạo sau các verification bắt buộc.
- [ ] Nội dung archive/manifest/resource được kiểm tra.
- [ ] Smoke test chạy trên artifact đã đóng gói nếu phù hợp.
- [ ] Có version và checksum/digest.
- [ ] Artifact được lưu ở nơi có retention và access control.
- [ ] Job deploy tải đúng artifact từ build run đã xác minh.
- [ ] Không build lại hoặc sửa artifact riêng cho từng môi trường.

### Supply chain và vận hành

- [ ] Có SBOM/provenance/signature theo yêu cầu.
- [ ] Credential được giới hạn theo job/environment.
- [ ] Log/report/artifact không làm lộ secret.
- [ ] Deployment record lưu version/digest và health result.
- [ ] Có retention và quy trình rollback.
- [ ] Có metric về thời gian, cache và failure rate.

## 30. Những lỗi thường gặp

| Lỗi thiết kế | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ lưu trạng thái job | Không biết test nào fail hoặc task nào gây lỗi | Upload console log và test report |
| Chỉ upload report khi job thành công | Mất report của lần fail cần điều tra | Dùng post-step chạy luôn sau failure |
| Chỉ lưu JAR, không lưu commit/run ID | Không truy ngược được source và lần build | Gắn artifact với commit và CI run |
| Upload toàn bộ workspace | Có thể lộ secret/cache/file cá nhân | Dùng allowlist artifact/report paths |
| Chỉ test class output | Bỏ sót lỗi manifest/resource/dependency | Smoke test package đã tạo |
| Deploy artifact từ job khác không kiểm tra | Có thể lấy nhầm file hoặc file bị thay đổi | Dùng run ID/digest và verify checksum |
| Dùng tên `latest` cho release | Artifact có thể bị thay nội dung | Dùng version bất biến hoặc digest |
| Build lại ở staging/production | Artifact có thể khác với bản đã test | Build once, promote exact artifact |
| Upload report nhưng không enforce quality gate | Report có cảnh báo nhưng pipeline vẫn xanh | Cấu hình task/quality gate fail đúng ngưỡng |
| Test bị skip nhưng job vẫn pass | Thiếu kiểm tra mà không ai nhận ra | Xác nhận test count và report expectation |
| Không có retention policy | Report/artifact biến mất quá sớm hoặc storage tăng không kiểm soát | Đặt retention theo loại dữ liệu |
| Provenance chỉ là file tự khai | Không chứng minh được nguồn gốc | Dùng attestation/signature và identity tin cậy |

## 31. Quy trình triển khai từ nhỏ đến hoàn chỉnh

Không cần đưa mọi hệ thống supply-chain vào một lần. Có thể phát triển pipeline theo từng mức:

1. **Mức cơ bản:** checkout, wrapper, build/test và lưu console log.
2. **Báo cáo:** upload JUnit XML/HTML và coverage/static analysis report.
3. **Artifact:** tạo JAR/WAR/distribution, kiểm tra archive và lưu file.
4. **Truy vết:** gắn commit SHA, CI run ID, version và checksum.
5. **Artifact test:** chạy smoke test trên package đã tạo.
6. **Repository:** publish version bất biến và kiểm tra tải lại bằng consumer.
7. **Supply chain:** tạo SBOM, provenance và signature.
8. **Promotion:** triển khai cùng digest qua staging/production và lưu deployment record.
9. **Governance:** đặt retention, approval, access control và rollback policy.

Sau mỗi mức, xác nhận pipeline vẫn giữ trạng thái fail chính xác, report có thể đọc và artifact không bị thay đổi ngoài ý muốn.

## 32. Nguyên tắc cần ghi nhớ

- CI cần lưu log, report, artifact và metadata; mỗi loại có mục đích riêng.
- Gắn mọi đầu ra với commit SHA và CI run/build ID.
- Dùng wrapper và toolchain được kiểm soát; ghi nhận version thực tế.
- Gradle thường lưu test report dưới `build/reports/tests/` và `build/test-results/`; Maven Surefire/Failsafe thường lưu dưới `target/surefire-reports/` và `target/failsafe-reports/`.
- Upload report kể cả khi build/test fail, nhưng không để upload step che trạng thái thất bại.
- Artifact chỉ được release sau khi quality gate và kiểm tra package phù hợp đã đạt.
- Kiểm tra archive và chạy smoke test trên chính artifact đã đóng gói.
- Tạo checksum/digest, lưu SBOM/provenance/signature theo yêu cầu và liên kết chúng với artifact.
- Job downstream phải tải đúng artifact của build run đã xác minh; không dùng `latest` hoặc build lại theo môi trường.
- Lưu deployment record có version/digest, environment và health result.
- Đặt retention, quyền truy cập và redaction cho report/log/artifact.
- Theo dõi thời gian pipeline, cache, test failure và retry để cải tiến mà không bỏ quality gate.

Một chuỗi CI có lưu báo cáo và artifact truy vết được biến kết quả build thành bằng chứng có thể kiểm tra lại. Khi source revision, môi trường, test report, artifact digest và deployment record được liên kết rõ ràng, nhóm có thể giải thích chính xác sản phẩm nào đã được kiểm tra, sản phẩm nào đã được phát hành và cần quay lại đâu khi có sự cố.
