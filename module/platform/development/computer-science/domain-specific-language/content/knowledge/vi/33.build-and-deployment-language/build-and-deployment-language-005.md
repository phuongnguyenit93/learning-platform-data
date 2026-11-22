# Pipeline phát hành

Trong một dự án sử dụng DSL (Domain-Specific Language), việc đưa thay đổi từ mã nguồn đến môi trường sử dụng cần một quy trình có thể lặp lại và kiểm soát được. **Pipeline phát hành (release pipeline)** là chuỗi bước tự động hóa việc kiểm tra, đóng gói, tạo phiên bản và chuyển giao artifact của DSL hoặc ứng dụng được sinh từ DSL đến các môi trường triển khai.

Pipeline phát hành không chỉ chạy lệnh build. Nó xác định đầu vào nào được xem là một bản phát hành, những điều kiện phải đạt trước khi tiếp tục, artifact nào được tạo ra, cách artifact được xác định phiên bản, ai hoặc hệ thống nào được phép phê duyệt, cách triển khai và cách khôi phục khi có sự cố.

Với dự án DSL, pipeline còn phải quản lý các thành phần đặc thù như grammar, metamodel, compiler, generator, runtime library, generated source, schema cấu hình và các file workflow. Một thay đổi nhỏ trong grammar có thể ảnh hưởng đến parser, dữ liệu DSL hiện có và mã đích được sinh ra. Vì vậy, pipeline cần kiểm soát cả công cụ tạo DSL lẫn sản phẩm được tạo từ DSL.

## 1. Pipeline phát hành là gì?

Pipeline phát hành là một quy trình gồm các stage và job có quan hệ phụ thuộc. Mỗi stage nhận đầu vào, thực hiện một nhóm công việc, tạo output và chỉ cho phép bước tiếp theo chạy khi điều kiện đã thỏa.

Một pipeline tổng quát:

```text
Commit / Tag / Release request
             |
             v
      Checkout source
             |
             v
      Resolve dependencies
             |
             v
      Build DSL toolchain
             |
             v
      Validate and test
             |
             v
      Package artifacts
             |
             v
      Sign and publish candidate
             |
             v
      Deploy to staging
             |
             v
      Verify and approve
             |
             v
      Promote to production
             |
             v
      Monitor / rollback
```

Các stage cụ thể phụ thuộc sản phẩm. Một DSL chỉ được dùng để tạo cấu hình có thể không cần deploy runtime; một DSL sinh ứng dụng có thể cần compile và kiểm thử generated code; một framework DSL cần phát hành parser, editor plugin và runtime library.

### 1.1. Build pipeline và release pipeline

Build pipeline tập trung tạo và xác minh output từ source. Release pipeline bao gồm cả việc xác định phiên bản, đóng gói, ký, lưu trữ, phê duyệt, promote và triển khai artifact. Nhiều tổ chức kết hợp hai quy trình thành một pipeline có stage build và stage release riêng.

### 1.2. CI và CD

Continuous Integration (CI) thường chạy khi có commit hoặc pull request để phát hiện lỗi sớm. Continuous Delivery/Deployment (CD) tiếp tục đưa artifact đã được xác minh đến môi trường đích. Continuous Delivery giữ bước phê duyệt trước production; Continuous Deployment có thể tự động triển khai khi mọi policy đều đạt.

### 1.3. Pipeline không thay thế release policy

Pipeline thực thi các quy tắc đã được định nghĩa. Chính sách phát hành vẫn phải quyết định versioning, mức kiểm tra, phê duyệt, bảo mật, tương thích và tiêu chí rollback. Một pipeline chạy xanh không tự chứng minh sản phẩm phù hợp với mục tiêu nghiệp vụ.

## 2. Artifact trong dự án DSL

Trước khi thiết kế pipeline, cần xác định chính xác những gì được phát hành. Một dự án DSL có thể tạo nhiều loại artifact:

| Artifact | Ví dụ |
|---|---|
| DSL source package | Các file `.dsl`, schema và module definitions |
| Grammar/tooling | Parser, compiler, validator và language server |
| Runtime library | Thư viện hỗ trợ thực thi DSL |
| Generated source | Java, Kotlin, TypeScript hoặc mã target khác |
| Compiled output | Bytecode, binary hoặc executable package |
| Configuration bundle | Cấu hình đã resolve và validate |
| Deployment package | Container image, chart hoặc deployment manifest |
| Editor extension | Plugin Eclipse, VS Code extension hoặc language tooling |
| Documentation | Reference, migration guide và release notes |
| SBOM/provenance | Danh sách thành phần và nguồn gốc build |

### 2.1. Phân biệt source và generated artifacts

Generated source là output của generator, không nên được coi là source of truth nếu có thể tái tạo từ DSL và toolchain. Pipeline cần lưu rõ source revision, compiler/generator version và cấu hình đã dùng để tạo output.

### 2.2. Một release có thể chứa nhiều artifact

Parser/compiler và runtime library có thể cần phát hành đồng bộ. Editor plugin có thể phụ thuộc phiên bản language server. Nếu các artifact không tương thích, pipeline phải đóng gói chúng thành một release set hoặc công bố compatibility matrix.

### 2.3. Artifact bất biến

Sau khi tạo và xác minh, artifact nên được xem là bất biến. Không nên build lại một gói khác dưới cùng version sau khi đã promote. Nếu cần sửa, tạo build/release mới với định danh mới.

## 3. Trigger của pipeline

Pipeline có thể bắt đầu từ nhiều sự kiện:

- Pull request hoặc merge vào branch chính.
- Commit vào branch release.
- Tạo tag phiên bản như `v2.4.0`.
- Tạo release candidate.
- Lệnh phát hành thủ công từ người có quyền.
- Lịch định kỳ cho nightly hoặc snapshot build.
- Sự kiện dependency/toolchain được cập nhật.

### 3.1. Pull request pipeline

Pull request pipeline thường chạy kiểm tra nhanh: format, compile, unit tests, parser fixtures, validation tests và kiểm tra tương thích. Nó giúp phát hiện vấn đề trước khi code được merge.

### 3.2. Main branch pipeline

Sau khi merge vào branch chính, pipeline có thể tạo snapshot artifact hoặc build candidate. Snapshot không nhất thiết là bản phát hành chính thức cho người dùng.

### 3.3. Tag-based release

Tag được dùng để xác định source revision phát hành. Pipeline cần xác minh tag hợp lệ, version trong tag khớp metadata và commit được tag nằm trong lịch sử branch được phép phát hành.

### 3.4. Manual release trigger

Phát hành thủ công hữu ích khi cần chọn release candidate hoặc thực hiện maintenance. Tuy nhiên, người kích hoạt không nên được tùy ý thay đổi source, version hoặc artifact đầu vào sau khi pipeline đã bắt đầu.

### 3.5. Tránh trigger vòng lặp

Pipeline có thể commit version file hoặc cập nhật release metadata. Cần tránh việc commit do bot tạo lại kích hoạt một pipeline phát hành khác ngoài ý muốn. Có thể dùng commit convention, path filters hoặc trigger rules.

## 4. Các stage cơ bản

Pipeline nên được chia thành stage theo mục tiêu và ranh giới kiểm soát.

### 4.1. Checkout và xác định revision

Pipeline lấy source code từ revision cụ thể. Nên ghi nhận commit SHA, tag, branch, submodule revisions và trạng thái working tree nếu có.

### 4.2. Resolve dependencies

Dependency cần được lấy từ repository đáng tin cậy và theo version đã khóa. Với DSL, dependency có thể gồm Xtext/EMF, parser generator, runtime, plugin, target SDK và thư viện sinh mã.

### 4.3. Build toolchain

Build compiler, parser, generator, runtime và tooling. Nếu grammar hoặc metamodel thay đổi, pipeline có thể chạy workflow generation trước khi compile các module phụ thuộc.

### 4.4. Validate source DSL

Parse và validate các DSL fixtures hoặc project mẫu. Kiểm tra syntax, linking, type constraints, schema và quy tắc miền.

### 4.5. Test generated output

Nếu DSL sinh code hoặc config, pipeline nên compile, validate hoặc chạy test trên output. Chỉ kiểm tra generator không đủ để chứng minh artifact đích có thể sử dụng.

### 4.6. Package

Đóng gói các artifact đã xác minh, metadata version, documentation và dependency manifests. Package phải có cấu trúc và naming ổn định.

### 4.7. Sign và publish candidate

Artifact có thể được ký số và đẩy vào artifact repository ở trạng thái candidate. Quyền truy cập repository cần được giới hạn theo pipeline identity.

### 4.8. Deploy và verify

Candidate được triển khai vào staging hoặc môi trường kiểm thử. Pipeline chạy smoke tests, health checks và các kiểm tra tương thích trước khi cho phép promote.

### 4.9. Promote

Promote chuyển cùng artifact đã được xác minh sang môi trường tiếp theo. Không nên build lại từ source khi promote nếu mục tiêu là đảm bảo artifact production chính là artifact đã kiểm tra ở staging.

## 5. Pipeline riêng cho DSL và code generation

Pipeline DSL cần kiểm soát chuỗi phụ thuộc giữa language definition, toolchain và output.

```text
Grammar / Metamodel / Generator templates
                  |
                  v
           Generate tooling
                  |
                  v
           Compile toolchain
                  |
                  v
             Parse DSL files
                  |
                  v
         Resolve and validate model
                  |
                  v
          Generate target artifacts
                  |
                  v
        Compile / validate generated output
                  |
                  v
           Package release set
```

### 5.1. Grammar generation

Với framework như Xtext, grammar và cấu hình MWE2 có thể tạo parser, metamodel và language infrastructure. Pipeline phải chạy đúng workflow và dùng phiên bản toolchain đã khóa.

### 5.2. Model compatibility

Thay đổi grammar có thể thay đổi metamodel hoặc semantics. Nếu người dùng có DSL source cũ, pipeline nên kiểm tra fixtures đại diện và các migration cần thiết.

### 5.3. Generated code validation

Generated source cần được compile bằng target compiler phù hợp. Nếu generator sinh SQL, cần validate hoặc chạy trên database test. Nếu sinh deployment config, cần kiểm tra schema của nền tảng triển khai.

### 5.4. Reproducible generation

Cùng source, dependency và cấu hình phải tạo output tương đương. Pipeline có thể kiểm tra diff giữa generated output và output đã lưu hoặc chạy generator hai lần trong điều kiện giống nhau để phát hiện nondeterminism.

### 5.5. Không publish artifact khi source validation thất bại

Nếu DSL model không parse hoặc validate được, pipeline cần dừng trước khi package artifact có thể được triển khai. Trường hợp warning cần có policy rõ, ví dụ warning nào cho phép release và warning nào phải được xử lý.

## 6. Test strategy trong release pipeline

Các lớp test nên được sắp xếp theo chi phí và mức độ bao phủ.

| Lớp kiểm tra | Mục tiêu | Ví dụ |
|---|---|---|
| Static checks | Kiểm tra cấu trúc source | Format, lint, dependency policy |
| Unit tests | Kiểm tra logic nhỏ | Scope resolver, type checker, generator helper |
| Parser tests | Kiểm tra cú pháp | DSL fixtures hợp lệ và không hợp lệ |
| Semantic tests | Kiểm tra ngữ nghĩa | Linking, type rules, validation |
| Generator tests | Kiểm tra output | Golden files, deterministic output |
| Target compilation | Kiểm tra output có thể build | Compile Java/Kotlin hoặc validate SQL |
| Integration tests | Kiểm tra các thành phần kết hợp | DSL runtime với database/service giả lập |
| End-to-end tests | Kiểm tra luồng thực tế | Build package và deploy staging |
| Compatibility tests | Kiểm tra nâng cấp | DSL source cũ với compiler mới |
| Security checks | Kiểm tra rủi ro supply chain | Dependency scan, secret scan, SBOM |

### 6.1. Chạy test nhanh trước, test nặng sau

Lint và unit tests có thể chạy sớm. Integration, end-to-end và compatibility matrix có thể chạy ở stage sau hoặc theo trigger phù hợp. Cách tổ chức này giảm thời gian phản hồi nhưng vẫn giữ điều kiện release.

### 6.2. Test fixtures của DSL

Fixtures nên đại diện cho cú pháp thực tế: file nhỏ, project nhiều module, import, symbol references, profile, workflow và trường hợp lỗi. Cần lưu fixture cùng expected diagnostics hoặc expected generated output.

### 6.3. Golden tests

Golden tests so sánh generated output với file mong đợi. Khi output thay đổi có chủ đích, reviewer có thể xem diff. Golden tests cần tránh phụ thuộc timestamp, absolute path hoặc thứ tự collection không ổn định.

### 6.4. Compatibility matrix

Compiler mới có thể cần đọc DSL source được tạo bởi phiên bản cũ. Có thể kiểm tra nhiều phiên bản schema, runtime hoặc target compiler để xác định phạm vi tương thích.

### 6.5. Flaky tests

Test phụ thuộc mạng, thời gian, thứ tự chạy hoặc tài nguyên dùng chung có thể thất bại không ổn định. Pipeline nên cô lập dữ liệu, dùng fake clock khi phù hợp và ghi nhận retry test riêng biệt; không nên tự động bỏ qua lỗi để làm release xanh.

## 7. Versioning và release candidate

Pipeline cần định danh rõ bản build và bản phát hành.

### 7.1. Semantic Versioning

Với artifact có public API, Semantic Versioning thường dùng dạng `MAJOR.MINOR.PATCH`:

- MAJOR: thay đổi không tương thích.
- MINOR: thêm chức năng tương thích ngược.
- PATCH: sửa lỗi tương thích ngược.

Đối với DSL, public API có thể bao gồm grammar, metamodel, built-in functions, runtime API, generated code contract và event/config schema.

### 7.2. Pre-release versions

Release candidate hoặc beta có thể dùng nhãn như `2.5.0-rc.1`. Pipeline cần phân biệt pre-release với stable release trong repository và deployment policy.

### 7.3. Version đồng bộ giữa các artifact

Compiler, runtime và editor plugin có thể dùng cùng version hoặc version độc lập kèm compatibility range. Dù chọn cách nào, release metadata cần cho biết bộ phiên bản nào tương thích.

### 7.4. Build number và commit SHA

Build number và commit SHA giúp truy xuất source của artifact. Chúng bổ sung cho version người dùng nhìn thấy, không thay thế version contract.

### 7.5. Không tái sử dụng version đã phát hành

Artifact repository nên từ chối ghi đè cùng tọa độ/version. Nếu cần sửa artifact, tạo version hoặc build identifier mới để audit và rollback có thể xác định chính xác.

## 8. Artifact repository và package layout

Artifact repository lưu trữ các gói được pipeline tạo ra. Có thể là Maven repository, container registry, package registry, object storage hoặc hệ thống nội bộ.

Một release set có thể chứa:

```text
release-2.5.0/
├── dsl-compiler-2.5.0.jar
├── dsl-runtime-2.5.0.jar
├── language-server-2.5.0.zip
├── editor-plugin-2.5.0.vsix
├── generated-app-template-2.5.0.zip
├── docs/
├── sbom.spdx.json
├── provenance.json
└── checksums.txt
```

Đây là ví dụ minh họa; package thực tế phụ thuộc cách phân phối sản phẩm.

### 8.1. Snapshot và release repository

Snapshot repository dùng cho artifact phát triển hoặc build liên tục. Release repository lưu artifact version bất biến được công bố. Không nên promote snapshot trực tiếp thành stable release mà không tạo candidate có version rõ.

### 8.2. Checksums

Checksum giúp phát hiện artifact bị thay đổi hoặc hỏng trong quá trình truyền. Pipeline nên tạo checksum cho từng file hoặc package và kiểm tra trước khi deploy.

### 8.3. Retention policy

Artifact cũ có thể cần giữ theo chính sách lưu trữ, yêu cầu audit và khả năng rollback. Xóa artifact đang được triển khai hoặc cần cho reproducibility có thể làm mất khả năng khôi phục.

### 8.4. Metadata

Mỗi artifact nên có metadata về version, source revision, build ID, dependency set, target platform và pipeline run. Metadata cần được lưu cùng artifact hoặc trong hệ thống provenance có thể truy vấn.

## 9. Artifact promotion giữa các môi trường

Promotion là chuyển một artifact đã được tạo và xác minh sang môi trường tiếp theo.

```text
Build candidate
      |
      v
Artifact repository
      |
      v
Deploy to test
      |
      v
Deploy same digest to staging
      |
      v
Approval / policy gate
      |
      v
Deploy same digest to production
```

### 9.1. Build once, promote many

Một nguyên tắc quan trọng là build artifact một lần rồi promote chính artifact đó qua các môi trường. Nếu staging và production dùng hai artifact được build riêng, kết quả staging không còn chứng minh trực tiếp artifact production.

### 9.2. Digest thay vì tag dễ thay đổi

Container image tag như `latest` có thể trỏ đến nội dung khác theo thời gian. Promotion nên dùng immutable digest hoặc version đã được repository bảo vệ.

### 9.3. Environment-specific configuration

Artifact ứng dụng có thể giống nhau nhưng cấu hình runtime khác nhau. Cấu hình môi trường nên được cung cấp qua profile/parameter/secret an toàn và được validate trước khi deploy.

### 9.4. Approval gates

Production promotion có thể yêu cầu phê duyệt, kiểm tra change window, xác nhận backup hoặc policy scan. Gate phải được thực thi bởi hệ thống pipeline, không chỉ là ghi chú trong release description.

### 9.5. Promotion không rebuild

Nếu cần thay cấu hình deployment, pipeline có thể tạo deployment manifest riêng gắn với artifact digest. Không nên âm thầm rebuild binary vì một thay đổi cấu hình không liên quan.

## 10. Phê duyệt và release gates

Release gate là điều kiện phải đạt trước khi pipeline tiếp tục.

Các gate có thể gồm:

- Tất cả test bắt buộc thành công.
- Không có vulnerability vượt ngưỡng policy.
- SBOM và provenance được tạo.
- Artifact được ký hợp lệ.
- Staging smoke tests đạt.
- Migration database đã được review.
- Release notes và migration guide đã sẵn sàng.
- Có approval từ người có quyền.
- Change window và deployment freeze được tuân thủ.

### 10.1. Automated gates

Automated gate kiểm tra dữ liệu máy có thể xác minh như test result, scan report, checksum, signature, policy evaluation và health check.

### 10.2. Manual approval

Manual approval phù hợp với quyết định cần đánh giá con người như thay đổi rủi ro cao, release lớn hoặc triển khai production. Approval cần ghi người phê duyệt, thời điểm, release ID và thông tin đã xem xét.

### 10.3. Tách quyền

Người tạo artifact không nhất thiết là người duyệt production. Tách quyền giúp giảm rủi ro một tài khoản hoặc pipeline bị xâm phạm có thể tự tạo và tự triển khai thay đổi.

### 10.4. Không bỏ qua gate bằng thao tác thủ công

Nếu có emergency bypass, nó cần quyền riêng, lý do, audit và phạm vi giới hạn. Bypass không nên xóa lịch sử hoặc khiến pipeline hiển thị như tất cả kiểm tra đã thành công.

## 11. Database migration và thay đổi schema

Ứng dụng được sinh từ DSL có thể cần thay đổi database schema hoặc cấu hình hạ tầng. Migration là một phần quan trọng của release.

### 11.1. Expand-contract

Một chiến lược an toàn là:

1. Expand: thêm cột hoặc cấu trúc mới theo cách tương thích.
2. Deploy: phát hành ứng dụng có thể làm việc với cả schema cũ và mới.
3. Migrate data: chuyển dữ liệu dần.
4. Contract: loại bỏ cấu trúc cũ sau khi không còn consumer phụ thuộc.

### 11.2. Migration có thể rollback không?

Không phải migration nào cũng đảo ngược an toàn, nhất là khi đã xóa dữ liệu hoặc thay đổi ý nghĩa. Pipeline cần phân loại migration reversible/irreversible và có kế hoạch backup, forward-fix hoặc restore.

### 11.3. Kiểm tra migration

Có thể chạy migration trên database tạm chứa schema/data đại diện, kiểm tra thời gian thực thi và xác nhận phiên bản schema sau migration.

### 11.4. Generated migration

Nếu DSL sinh migration, pipeline cần validate SQL, kiểm tra thứ tự phụ thuộc và tránh thực thi migration nguy hiểm chỉ vì generator tạo ra file hợp lệ về cú pháp.

## 12. Deployment strategy

Pipeline có thể hỗ trợ nhiều chiến lược triển khai tùy yêu cầu sẵn sàng và khả năng rollback.

| Chiến lược | Cách hoạt động | Điểm cần cân nhắc |
|---|---|---|
| Recreate | Dừng phiên bản cũ rồi chạy phiên bản mới | Có downtime |
| Rolling update | Thay instance theo từng nhóm | Cần tương thích giữa phiên bản cũ/mới trong thời gian chuyển tiếp |
| Blue-green | Duy trì hai môi trường và chuyển traffic | Cần tài nguyên gấp đôi trong giai đoạn chuyển |
| Canary | Chuyển một phần traffic sang bản mới | Cần metric và tiêu chí dừng rõ |
| Shadow | Gửi bản sao traffic để quan sát mà không trả response cho người dùng | Cần tránh side effects |

### 12.1. Rolling deployment

Rolling deployment thay instance từng bước. Với DSL runtime hoặc API, phiên bản mới và cũ có thể cùng hoạt động trong một khoảng thời gian. Vì vậy, event schema, database schema và API cần tương thích tạm thời.

### 12.2. Blue-green deployment

Blue-green tạo môi trường mới song song, kiểm tra health rồi chuyển traffic. Nếu lỗi, có thể chuyển lại môi trường cũ nhanh hơn, miễn là dữ liệu và side effects tương thích.

### 12.3. Canary release

Canary đưa một tỷ lệ nhỏ traffic đến phiên bản mới. Pipeline hoặc deployment controller theo dõi error rate, latency và business metrics; nếu vượt ngưỡng, dừng hoặc rollback.

### 12.4. Feature flags

Feature flags cho phép tách thời điểm deploy code khỏi thời điểm bật tính năng. Flag cần có owner, expiry và policy; flag cũ không nên tồn tại vô thời hạn.

## 13. Rollback và recovery

Rollback đưa hệ thống về phiên bản hoặc cấu hình trước khi có sự cố. Tuy nhiên, rollback không phải lúc nào cũng chỉ là deploy image cũ.

### 13.1. Rollback application

Nếu artifact mới lỗi nhưng database schema tương thích, có thể triển khai lại artifact trước đó. Artifact cũ cần được giữ lại và xác định bằng version/digest.

### 13.2. Rollback configuration

Nếu lỗi đến từ profile hoặc parameter, có thể khôi phục revision cấu hình trước. Nên version hóa configuration bundle và lưu provenance.

### 13.3. Rollback database

Database rollback có thể mất dữ liệu hoặc không khả thi. Một số thay đổi cần forward migration hoặc restore từ backup. Pipeline nên phân biệt rollback code với rollback data.

### 13.4. Compensation

Với workflow phân tán, không thể luôn đảo transaction đã commit ở dịch vụ khác. Có thể cần compensation như hoàn tiền, hủy reservation hoặc phát thông báo điều chỉnh.

### 13.5. Recovery plan

Release plan nên xác định người chịu trách nhiệm, trigger rollback, tiêu chí quyết định, thời gian phục hồi mục tiêu và cách xác nhận hệ thống đã ổn định.

## 14. Bảo mật pipeline và supply chain

Pipeline có quyền đọc source, lấy dependency, ký artifact và triển khai. Vì vậy, nó là mục tiêu quan trọng trong chuỗi cung ứng phần mềm.

### 14.1. Least privilege

Mỗi job chỉ nên có quyền cần thiết. Job build không cần quyền deploy production; job deploy không cần quyền sửa source repository.

### 14.2. Secret management

Token registry, signing key và credential deployment nên lấy từ secret manager hoặc cơ chế cấp credential ngắn hạn. Không ghi secret vào source, pipeline YAML hoặc log.

### 14.3. Dependency pinning

Khóa dependency version và kiểm tra nguồn tải. Với toolchain DSL, thay đổi phiên bản parser generator hoặc runtime có thể làm output khác, vì vậy cần kiểm soát dependency rõ ràng.

### 14.4. SBOM

Software Bill of Materials liệt kê thư viện và thành phần có trong artifact. SBOM hỗ trợ vulnerability management, audit và đánh giá ảnh hưởng khi dependency có vấn đề.

### 14.5. Artifact signing

Ký artifact giúp xác minh nguồn phát hành và phát hiện nội dung bị thay đổi. Khóa ký cần được bảo vệ, rotation và audit; không nên đặt private key lâu dài trong repository.

### 14.6. Build provenance

Provenance ghi lại source revision, builder identity, build parameters, dependency và artifact digest. Nó giúp chứng minh artifact được tạo từ source và quy trình nào.

### 14.7. Isolated build environments

Build nên chạy trong môi trường sạch, có giới hạn network và quyền filesystem. Điều này giảm ảnh hưởng từ máy developer, dependency không mong muốn hoặc script bị cài cắm.

## 15. Reproducible builds

Reproducible build nghĩa là cùng đầu vào được kiểm soát sẽ tạo artifact giống nhau hoặc tương đương theo tiêu chí đã định.

Các nguồn gây khác biệt:

- Dependency không khóa version.
- Timestamp được nhúng vào archive.
- Absolute path của workspace.
- Thứ tự file hoặc map không xác định.
- Locale, timezone hoặc môi trường hệ điều hành.
- Compiler/generator version khác nhau.
- Environment variable không được khai báo.

### 15.1. Pin toolchain

Ghi rõ Java/JDK, compiler, generator, build plugin, runtime và target SDK. Có thể dùng container image theo digest để cố định môi trường.

### 15.2. Normalize output

Generator nên chuẩn hóa line endings, encoding, file ordering và timestamp nếu có thể. Tránh đưa thông tin máy cá nhân vào output.

### 15.3. Verify reproducibility

Có thể build hai lần trong môi trường sạch và so sánh digest. Nếu khác nhau, pipeline cần giúp xác định thành phần nào tạo nondeterminism.

### 15.4. Reproducibility và provenance

Reproducible build cho biết có thể tái tạo output; provenance cho biết output cụ thể được tạo như thế nào. Hai cơ chế bổ sung nhau.

## 16. Release notes và migration documentation

Artifact không phải phần duy nhất của một release. Người dùng cần biết thay đổi nào ảnh hưởng đến DSL source, API và cách triển khai.

Release notes thường gồm:

- Tính năng mới.
- Bug fixes.
- Breaking changes.
- Grammar hoặc metamodel changes.
- Thay đổi runtime và generated code.
- Dependency/toolchain requirements.
- Migration steps và deprecation notices.
- Known issues và giới hạn.

### 16.1. DSL migration guide

Khi grammar hoặc semantics thay đổi, migration guide nên có ví dụ trước/sau và cách chuyển source DSL. Nếu có migration tool, pipeline có thể đóng gói cùng release.

### 16.2. Deprecation policy

API hoặc cú pháp deprecated nên có thời gian chuyển tiếp, warning rõ và phiên bản dự kiến loại bỏ. Việc loại bỏ cần được xem là thay đổi compatibility.

### 16.3. Release metadata

Có thể gắn release notes, documentation version, source tag và artifact links vào release record để người dùng truy xuất đúng tài liệu tương ứng.

## 17. Observability của pipeline

Pipeline cần cung cấp đủ thông tin để biết nó đang ở đâu, thất bại vì sao và artifact nào đã được tạo.

Các metric hữu ích:

- Thời gian mỗi stage và toàn pipeline.
- Tỷ lệ build/test/release thành công.
- Số lần retry và flaky test.
- Số vulnerability theo severity.
- Thời gian chờ approval.
- Tỷ lệ deploy/rollback thành công.
- Thời gian từ commit đến production.
- Artifact digest và release version.

### 17.1. Structured logs

Log nên chứa pipeline run ID, stage, job, commit SHA, artifact ID và environment. Không ghi credential hoặc payload nhạy cảm.

### 17.2. Failure classification

Phân biệt lỗi source, lỗi dependency, lỗi hạ tầng, lỗi test, policy rejection và lỗi deploy. Diagnostic cụ thể giúp đội ngũ xử lý đúng nguyên nhân.

### 17.3. Pipeline dashboard

Danh sách release có thể hiển thị trạng thái build, candidate, staging, approval, production và rollback. Cần tránh chỉ dùng một trạng thái “green” khi một số gate chưa chạy.

### 17.4. Audit trail

Ghi ai kích hoạt, ai phê duyệt, artifact nào được deploy, thời điểm và kết quả. Audit trail cần bất biến hoặc có kiểm soát truy cập để hỗ trợ điều tra.

## 18. Ví dụ pipeline khai báo

Một DSL triển khai có thể mô tả pipeline ở mức khái niệm:

```text
pipeline releaseDsl {
    trigger on tag matching "v*"

    stage build {
        checkout source
        resolve dependencies locked
        generate language infrastructure
        compile toolchain
    }

    stage verify dependsOn build {
        run parser tests
        run semantic tests
        validate example projects
        generate target artifacts
        compile generated sources
    }

    stage package dependsOn verify {
        create compiler package
        create runtime package
        create language-server package
        generate sbom
        sign artifacts
        publish candidate
    }

    stage staging dependsOn package {
        deploy candidate to staging
        run smoke tests
        verify health
    }

    stage production dependsOn staging {
        require approval from release-managers
        promote same artifact digest
        deploy production
        monitor errorRate for 15m
    }
}
```

Cú pháp chỉ minh họa cách mô tả các thành phần. DSL thực tế cần định nghĩa kiểu stage, dependency, permission, artifact reference, secret handling và điều kiện chạy.

### 18.1. Dependency giữa stage

`verify` chỉ chạy sau `build`; `package` chỉ chạy sau `verify`. Dependency graph giúp pipeline chạy các job độc lập song song nhưng vẫn giữ thứ tự bắt buộc.

### 18.2. Artifact handoff

Output của stage build hoặc verify nên được lưu thành artifact có định danh. Stage package tiêu thụ đúng artifact đó thay vì chạy lại lệnh build với trạng thái workspace khác.

### 18.3. Approval gate

Production stage yêu cầu nhóm release manager phê duyệt. Hệ thống cần lưu quyết định và gắn nó với candidate cụ thể.

### 18.4. Post-deploy verification

Sau deploy, pipeline kiểm tra health và metric. Nếu error rate vượt ngưỡng, nó có thể dừng rollout hoặc kích hoạt rollback theo policy đã cấu hình.

## 19. Quản lý pipeline dưới dạng code

Pipeline definition nên được lưu cùng repository hoặc repository cấu hình có kiểm soát phiên bản.

### 19.1. Review pipeline changes

Thay đổi pipeline có thể tăng quyền, bỏ gate hoặc thay cách ký artifact. Vì vậy, pipeline code cần review tương tự code ứng dụng.

### 19.2. Reusable templates

Các nhóm có thể dùng template chung cho build, scan, package và deploy. Template giúp chuẩn hóa policy nhưng cần version và compatibility contract.

### 19.3. Tách policy khỏi implementation

Có thể đặt policy như required approvals, allowed registries và vulnerability thresholds ở một lớp quản trị trung tâm. Repository pipeline tham chiếu policy thay vì tự định nghĩa lại mỗi nơi.

### 19.4. Test pipeline definition

Pipeline DSL hoặc YAML có thể được validate cú pháp, schema, dependency graph và permission trước khi thực thi. Có thể dùng dry-run để hiển thị stage graph và artifact flow.

## 20. Phát hành nhiều thành phần có phụ thuộc

Một hệ DSL có thể phát hành compiler, runtime, editor và plugin cùng lúc. Các thành phần này có thể có dependency version khác nhau.

### 20.1. Release train

Release train gom các thành phần theo lịch hoặc version set. Ví dụ compiler 3.2 yêu cầu runtime 3.2 và language server 3.2.

### 20.2. Compatibility matrix

Có thể công bố bảng:

| Compiler | Runtime | Language server | Trạng thái |
|---|---|---|---|
| 3.2 | 3.2 | 3.2 | Được hỗ trợ |
| 3.2 | 3.1 | 3.2 | Không hỗ trợ |
| 3.1 | 3.2 | 3.1 | Chỉ hỗ trợ nếu compatibility contract cho phép |

### 20.3. Atomic release set

Nếu các artifact phải được triển khai đồng bộ, pipeline có thể publish một release manifest chứa toàn bộ digest và version. Deployment chỉ được bắt đầu khi tất cả thành phần đã sẵn sàng.

### 20.4. Independent versioning

Nếu runtime và editor có vòng đời khác nhau, có thể version độc lập. Khi đó cần khai báo compatibility ranges và kiểm thử các tổ hợp được hỗ trợ.

## 21. Release pipeline cho cấu hình và workflow DSL

Không phải DSL nào cũng sinh ứng dụng. Một số DSL sinh cấu hình, workflow hoặc policy được nạp trực tiếp bởi runtime.

### 21.1. Validate configuration bundle

Pipeline parse, resolve profile, kiểm tra schema, secret references và cross-field constraints. Secret value thật có thể chỉ được resolve trong môi trường triển khai, nhưng cấu trúc reference và quyền cần được kiểm tra.

### 21.2. Workflow definition

Workflow DSL có thể được compile thành state machine hoặc deployment artifact. Pipeline cần kiểm tra transition, event schema, timeout, retry và compensation trước khi publish.

### 21.3. Policy DSL

Policy DSL có thể ảnh hưởng authorization hoặc quyết định nghiệp vụ. Release gate có thể yêu cầu test policy, kiểm tra rule coverage và approval bổ sung.

### 21.4. Không thực thi cấu hình tùy tiện trong build

Nếu DSL cho phép expression hoặc plugin, pipeline cần sandbox và giới hạn quyền. Việc validate một file cấu hình không nên tự động chạy side effects trên môi trường thật.

## 22. Disaster recovery và release continuity

Pipeline và artifact repository cũng cần kế hoạch phục hồi.

### 22.1. Backup artifact

Artifact release, metadata, signature và provenance nên được backup theo retention policy. Không chỉ backup source repository.

### 22.2. Khả năng khôi phục pipeline

Pipeline definition, reusable templates, runner images và secret references cần có thể tái tạo. Credential không nên backup dưới dạng plaintext.

### 22.3. Artifact repository outage

Nếu registry không khả dụng, pipeline nên dừng promotion và retry theo policy. Không nên deploy từ một artifact tạm không có checksum hoặc provenance.

### 22.4. Release freeze

Khi có sự cố lớn, tổ chức có thể đóng băng release mới trong khi xử lý incident. Pipeline cần có cơ chế freeze được kiểm soát và audit.

## 23. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Build lại khi promote | Artifact production khác artifact đã test | Build once, promote by digest |
| Không khóa toolchain/dependency | Output thay đổi giữa các lần build | Pin versions và môi trường build |
| Chỉ test compiler, không test generated output | Mã đích có thể không compile hoặc chạy sai | Thêm target compilation/integration tests |
| Publish trước validation | Artifact lỗi có thể được triển khai | Gate validation trước package/release |
| Dùng version có thể ghi đè | Không xác định được artifact đã triển khai | Immutable version và digest |
| Secret nằm trong pipeline file | Credential có thể bị lộ | Secret manager và short-lived credentials |
| Một job có toàn quyền | Tăng tác động khi pipeline bị xâm phạm | Least privilege và tách quyền |
| Không có provenance | Khó truy source và dependency của artifact | Ghi build metadata và attestation |
| Bỏ qua migration compatibility | Phiên bản cũ/mới không cùng hoạt động được | Expand-contract và compatibility tests |
| Rollback chỉ đổi image | Database/configuration vẫn ở trạng thái không tương thích | Kế hoạch rollback/forward-fix đầy đủ |
| Gate chỉ tồn tại trong tài liệu | Pipeline vẫn cho deploy khi điều kiện chưa đạt | Enforce policy trong pipeline |
| Không có post-deploy verification | Lỗi chỉ được phát hiện sau khi người dùng báo | Health checks, metrics và canary analysis |

## 24. Nguyên tắc thiết kế pipeline phát hành

Khi thiết kế release pipeline cho DSL, có thể áp dụng các nguyên tắc sau:

1. **Xác định artifact rõ ràng.** Biết chính xác compiler, runtime, generated output và deployment package nào được phát hành.
2. **Gắn build với source revision.** Ghi commit, dependency, toolchain và cấu hình build.
3. **Tách build, verify, package và deploy.** Mỗi stage có input/output và điều kiện thành công rõ.
4. **Kiểm tra cả DSL lẫn generated output.** Parser xanh không có nghĩa output target hợp lệ.
5. **Dùng artifact bất biến.** Không ghi đè version đã publish.
6. **Build once, promote many.** Đưa cùng digest qua staging và production.
7. **Khóa toolchain và dependency.** Hỗ trợ reproducible build.
8. **Áp dụng release gates.** Test, security scan, signature, approval và health checks phải được thực thi tự động hoặc có audit.
9. **Tách quyền và bảo vệ secret.** Mỗi job chỉ có quyền cần thiết.
10. **Version hóa contract.** Grammar, metamodel, runtime API, event/schema và generated code đều có thể là public contract.
11. **Chuẩn bị rollback và recovery.** Giữ artifact trước, hiểu migration và có tiêu chí phục hồi.
12. **Theo dõi provenance và SBOM.** Có thể truy nguồn và đánh giá supply chain.
13. **Quan sát pipeline và deployment.** Log, metric, trace và audit phải liên kết với release ID.
14. **Kiểm soát thay đổi pipeline.** Pipeline code và template cần review, test và version.
15. **Tự động hóa nhưng giữ quyết định có trách nhiệm.** Approval cần đúng người, đúng artifact và được ghi nhận.

## 25. Kết luận

Pipeline phát hành là quy trình có kiểm soát đưa source DSL và các artifact liên quan từ trạng thái phát triển đến môi trường sử dụng. Với DSL, pipeline cần xây dựng và kiểm tra cả grammar, metamodel, compiler, runtime, editor tooling lẫn generated code hoặc configuration bundle.

Một pipeline đáng tin cậy chia công việc thành các stage rõ ràng, khóa dependency và toolchain, kiểm tra semantics của DSL, xác minh output target, đóng gói artifact bất biến, ký và lưu provenance, rồi promote cùng artifact qua các môi trường. Release gates, approval, migration strategy, deployment verification và rollback giúp giảm rủi ro khi đưa thay đổi đến production.

Khi pipeline được quản lý như code và mọi release có thể truy ngược về source revision, dependency, build identity và artifact digest, nhóm có thể phát hành DSL một cách lặp lại, kiểm toán được và phục hồi có kế hoạch. Đây là nền tảng để DSL phát triển từ công cụ nội bộ thành một thành phần phần mềm có vòng đời phát hành ổn định.
