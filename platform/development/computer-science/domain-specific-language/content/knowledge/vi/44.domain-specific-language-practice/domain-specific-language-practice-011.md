# Đóng gói và tài liệu hóa dự án DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vai trò của đóng gói và tài liệu hóa trong vòng đời một project DSL.
- Tổ chức source, schema, test, example, resource, cấu hình và tài liệu.
- Thiết kế manifest mô tả tên, version, DSL version, runtime, dependency và entry point.
- Phân biệt source, generated code, build artifact và package phân phối.
- Quản lý dependency, lockfile và cấu hình theo môi trường.
- Tạo build có thể tái tạo và xác định chính xác nội dung package.
- Viết README, quick start, tutorial, reference, architecture guide và runbook.
- Tạo ví dụ chạy được, sơ đồ và tài liệu API.
- Quản lý changelog, semantic versioning và migration guide.
- Kiểm soát license, checksum, signature, provenance và SBOM.
- Phân phối, cài đặt, xác minh và nâng cấp package.
- Bàn giao project để người khác có thể sử dụng và bảo trì độc lập.

## 1. Đóng gói và tài liệu hóa là gì?

Một project DSL không chỉ gồm các file source. Để người khác sử dụng, triển khai hoặc tiếp tục phát triển, project cần có cấu trúc, metadata, dependency, artifact và tài liệu phù hợp.

**Đóng gói (packaging)** là quá trình tập hợp các thành phần cần thiết thành một đơn vị có thể lưu trữ, cài đặt, triển khai hoặc phân phối. Package có thể là archive, module, plugin, thư viện, container image hoặc định dạng riêng của DSL runtime.

**Tài liệu hóa (documentation)** là quá trình giải thích mục đích, cách cài đặt, cách sử dụng, cấu trúc, contract, giới hạn và cách bảo trì project.

Một project sẵn sàng bàn giao cần giúp người nhận trả lời được:
- Project giải quyết vấn đề gì?
- Cần compiler hoặc runtime version nào?
- Cần dependency nào?
- Build và chạy bằng cách nào?
- Input và output có dạng gì?
- Cần cấu hình nào?
- Lỗi thường gặp được xử lý ra sao?
- Artifact nằm ở đâu và triển khai thế nào?
- Version mới có ảnh hưởng gì?
- Ai duy trì project?

Source có thể chạy trên máy tác giả nhưng vẫn chưa phải một sản phẩm có thể bàn giao nếu thiếu manifest, dependency hoặc hướng dẫn.

## 2. Phân biệt source, build output và package

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Source | File gốc do nhóm phát triển duy trì | DSL, schema, config template |
| Build output | Kết quả compile hoặc generate | Bytecode, generated client, query plan |
| Package | Đơn vị phân phối chứa file cần thiết | ZIP, JAR, module, plugin, image |

Source thường được lưu trong version control. Build output có thể được tạo lại từ source. Package là tập hợp được chọn lọc theo contract phân phối.

### 2.1. Không đưa mọi file trong workspace vào package

Workspace có thể chứa file tạm, log, cache, IDE metadata, test fixture nội bộ, secret cục bộ, backup và build output cũ. Package chỉ nên chứa thành phần cần thiết cho mục đích phân phối.

### 2.2. Source package và runtime package

Source package có thể chứa DSL source, schema, examples và metadata để người nhận tiếp tục chỉnh sửa. Runtime package có thể chỉ chứa artifact đã compile, runtime descriptor và resource cần thiết để thực thi.

Một project có thể phát hành cả hai loại.

### 2.3. Package là một contract

Package cần quy định tên, version, platform hoặc runtime được hỗ trợ, entry point, dependency, resource, cách cài đặt, cách cấu hình, compatibility và license. Contract không rõ sẽ buộc consumer suy đoán.

## 3. Cấu trúc thư mục dự án

Một cấu trúc minh họa cho project DSL:

~~~text
order-automation/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── manifest.yml
├── dsl/
│   ├── schemas/
│   │   ├── order.schema.dsl
│   │   └── customer.schema.dsl
│   ├── rules/
│   │   └── eligibility.rules.dsl
│   ├── workflows/
│   │   └── fulfillment.workflow.dsl
│   └── integrations/
│       └── shipping.integration.dsl
├── config/
│   ├── defaults.yml
│   └── profiles/
│       ├── development.yml
│       └── test.yml
├── resources/
│   └── templates/
├── examples/
│   ├── sample-order.json
│   └── run-example.dsl
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
│   ├── getting-started.md
│   ├── architecture.md
│   ├── language-reference.md
│   ├── operations.md
│   └── diagrams/
├── scripts/
│   └── package-project.sh
└── build/
~~~

Đây là cấu trúc mẫu; tên folder cần theo quy ước toolchain và quy mô project.

### 3.1. Source DSL

Tổ chức source theo chức năng hoặc bounded context. Schema, rule, workflow và integration có thể nằm trong folder riêng để người đọc hiểu project nhanh.

### 3.2. Configuration

Tách cấu hình mặc định khỏi profile môi trường. Không đưa secret vào source hoặc file config được commit.

### 3.3. Resources

Template, schema ngoài, static file và resource runtime cần được quản lý rõ. Nếu DSL tham chiếu resource, package phải chứa nó hoặc mô tả cách cung cấp.

### 3.4. Examples và tests

Examples nên chạy được bằng dữ liệu giả lập. Tests nên phân biệt unit, integration và fixture để người bảo trì biết mỗi test cần môi trường nào.

### 3.5. Documentation

Đặt tài liệu gần project và version hóa cùng source để docs thay đổi đồng bộ với behavior.

### 3.6. Build output

Folder build thường được tạo tự động. Có thể loại nó khỏi version control nếu output tái tạo được, nhưng package phát hành phải lấy đúng artifact từ build tương ứng.

## 4. Manifest và metadata project

Manifest mô tả project cho compiler, package manager hoặc runtime.

~~~yaml
name: order-automation
version: 1.2.0
description: Order fulfillment rules and workflows
dsl:
  languageVersion: 3.0
  runtime: 6.2
entry:
  workflow: dsl/workflows/fulfillment.workflow.dsl
dependencies:
  - name: customer-schema
    version: 2.1.0
  - name: shipping-connector
    version: 4.0.2
package:
  type: dsl-module
  include:
    - dsl/**
    - config/defaults.yml
    - resources/**
    - docs/**
    - README.md
~~~

### 4.1. Tên và version

Tên project nên ổn định, dễ nhận diện và tuân theo quy ước registry. Version nhận diện một bản phát hành. Changelog cần giải thích điều gì thay đổi giữa các version.

### 4.2. DSL version và runtime version

Version project và version ngôn ngữ không nhất thiết giống nhau. Project 1.2.0 có thể dùng DSL language 3.0 và runtime 6.2. Ghi rõ cả hai để tránh nhầm compatibility.

### 4.3. Entry point

Entry point chỉ rõ workflow, module hoặc file runtime cần nạp đầu tiên. Project có nhiều entry point cần mô tả cách chọn.

### 4.4. Dependencies

Dependency cần có tên, version constraint và nguồn phân phối. Với build cần tái lập, dùng lockfile để khóa kết quả resolution.

### 4.5. Package inclusion

Include và exclude rule xác định file nằm trong package. Không nên nén toàn bộ workspace theo mặc định.

### 4.6. Metadata bổ sung

Có thể khai báo maintainer, license, repository, documentation URL, supported platform, checksum và build provenance. Chỉ khai báo thông tin có căn cứ.

## 5. Quản lý dependency

Project DSL có thể phụ thuộc schema, connector, library, runtime extension hoặc package khác.

### 5.1. Direct và transitive dependency

Direct dependency được project khai báo trực tiếp. Transitive dependency được kéo vào bởi dependency khác.

~~~text
order-automation
  ├── customer-schema
  └── shipping-connector
        └── http-client
~~~

Project cần biết dependency nào được yêu cầu trực tiếp và dependency nào được giải quyết gián tiếp.

### 5.2. Version constraint và lockfile

Constraint cho phép nhận các version trong khoảng tương thích. Nhưng nếu không khóa kết quả resolution, build có thể thay đổi theo thời gian. Lockfile ghi lại phiên bản cụ thể để các máy build cài cùng dependency.

### 5.3. Dependency source

Dependency có thể đến từ public registry, private registry, repository nội bộ hoặc local path. Package cần khai báo nguồn và cách xác thực phù hợp.

### 5.4. Compatibility

Kiểm tra DSL version, runtime version và extension API tương thích với nhau. Không đóng gói lại dependency mà runtime đã cung cấp nếu điều đó tạo duplicate hoặc xung đột version.

## 6. Cấu hình và môi trường

Project thường chạy ở development, test, staging và production. Cấu hình cần tách biệt để cùng package có thể triển khai ở nhiều môi trường.

### 6.1. Defaults và environment profile

Default nên chứa giá trị không nhạy cảm và hợp lý, ví dụ timeout mặc định hoặc tên queue logic. Profile có thể override endpoint, logging level, resource limit hoặc feature flag.

### 6.2. Secret

Password, token, API key và private key phải được cấp qua secret manager hoặc cơ chế credential của runtime. Không commit secret vào repository, README, package hoặc build log.

### 6.3. Configuration schema

Mỗi config key nên có tên, kiểu, required/optional, default, mô tả, giá trị hợp lệ, ví dụ và phân loại nhạy cảm.

### 6.4. Validation

CLI hoặc runtime nên validate config trước khi khởi chạy. Lỗi cần chỉ ra key, kiểu mong đợi và cách sửa.

### 6.5. Tách config khỏi logic

Cấu hình thay đổi theo môi trường nên được tách khỏi logic nghiệp vụ. Không hardcode production URL vào source nếu project cần chạy ở nhiều nơi.

## 7. Build và tạo artifact

Build chuyển source DSL và dependency thành artifact có thể thực thi hoặc phân phối.

~~~text
Source + Manifest + Dependencies
              |
              v
          Validation
              |
              v
          Compilation
              |
              v
       Generated Artifacts
              |
              v
         Package Assembly
              |
              v
         Package Archive
~~~

### 7.1. Validation

Kiểm tra manifest, source syntax, type, schema và dependency trước khi đóng gói.

### 7.2. Compilation hoặc generation

Compiler có thể tạo bytecode, generated client, query plan, workflow graph hoặc artifact runtime khác.

### 7.3. Resource collection

Build cần thu thập resource được tham chiếu trong source. Thiếu resource có thể khiến package compile được nhưng runtime không khởi động.

### 7.4. Package assembly

Đưa source hoặc artifact, manifest, resource và tài liệu cần thiết vào staging directory theo layout đã quy định.

### 7.5. Archive và naming

Archive có thể là ZIP, TAR, JAR hoặc định dạng riêng. Tên file nên chứa project và version, ví dụ:

~~~text
order-automation-1.2.0.dslpkg
~~~

Nếu artifact có platform-specific variant, tên hoặc metadata cần thể hiện target.

## 8. Build có thể tái tạo

Reproducible build là khả năng tạo artifact tương đương từ cùng source, dependency, toolchain và cấu hình build đã khai báo.

### 8.1. Lợi ích

- Xác minh artifact được tạo từ source nào.
- Điều tra khác biệt giữa hai lần build.
- Giảm rủi ro dependency thay đổi ngoài dự kiến.
- Tạo kết quả nhất quán giữa CI và máy developer.
- Hỗ trợ audit và supply-chain security.

### 8.2. Pin toolchain

Ghi rõ compiler, runtime, plugin và package manager version. Nếu build phụ thuộc JDK hoặc hệ điều hành, ghi rõ target environment.

### 8.3. Lock dependency

Dùng lockfile hoặc checksum dependency để cùng manifest không resolve thành tập package khác nhau theo thời gian.

### 8.4. Chuẩn hóa metadata

Timestamp, absolute path, machine-specific identifier hoặc file ordering có thể khiến archive khác nhau dù source giống nhau. Chuẩn hóa metadata khi toolchain hỗ trợ.

### 8.5. Build provenance

Provenance mô tả source revision, toolchain, pipeline và workflow đã tạo artifact. Đây là bằng chứng hữu ích cho release.

## 9. Chọn nội dung package

Package cần có đủ thông tin cho consumer nhưng không chứa dữ liệu không liên quan.

~~~text
order-automation-1.2.0/
├── manifest.yml
├── runtime/
│   └── workflow.bundle
├── schemas/
│   ├── order.schema
│   └── customer.schema
├── resources/
│   └── templates/
├── config/
│   └── defaults.yml
├── docs/
│   └── README.md
└── metadata/
    ├── checksums.txt
    └── provenance.json
~~~

### 9.1. Include và exclude

Chỉ include file runtime hoặc người dùng cần. Loại secret, local environment file, temporary output, IDE metadata, cache, test credential, log, backup và unrelated project.

### 9.2. Generated artifact

Build phải tạo artifact mới từ source đúng version. Tránh lấy nhầm output cũ còn sót trong folder build.

### 9.3. Source map và debug metadata

Có thể đưa source map hoặc debug metadata vào package development/staging. Production package cần cân nhắc dung lượng và chính sách thông tin.

### 9.4. Test fixture

Test fixture thường không cần trong runtime package, nhưng có thể có trong source package hoặc test bundle riêng.

## 10. README: điểm bắt đầu của người dùng

README thường là trang đầu tiên người dùng mở. Nó cần giúp họ hiểu project và thực hiện bước đầu tiên.

Một README thực dụng có thể gồm:
1. Tên và mô tả ngắn.
2. Vấn đề project giải quyết.
3. Tính năng chính.
4. Yêu cầu môi trường.
5. Cài đặt.
6. Quick start.
7. Cấu hình.
8. Cách chạy test.
9. Cấu trúc thư mục.
10. Link đến tài liệu chi tiết.
11. License và thông tin hỗ trợ.

### 10.1. Mô tả rõ mục đích

Nói rõ project định nghĩa quy tắc, query hoặc workflow nào và ai sẽ dùng nó.

### 10.2. Prerequisite

Nêu compiler/runtime version, quyền truy cập registry, credential reference và dependency cần có.

### 10.3. Quick start chạy được

Quick start cần lệnh và file mẫu chính xác. Người dùng nên có thể copy lệnh và kiểm tra output mong đợi.

### 10.4. Configuration

Liệt kê config key cần thiết, default và cách cấp secret. Không đưa credential thật vào ví dụ.

### 10.5. Troubleshooting

README có thể nêu lỗi phổ biến và liên kết đến hướng dẫn chi tiết thay vì chứa mọi giải thích kỹ thuật.

## 11. Quick start và tutorial

README giới thiệu project; tutorial dạy người dùng hoàn thành một tác vụ.

Quick start nên kiểm tra prerequisite, cài package, cung cấp config mẫu, chạy example, quan sát output và chỉ ra bước tiếp theo.

Tutorial nên đi qua một use case hoàn chỉnh, ví dụ tạo workflow xử lý đơn hàng. Giải thích từng bước, vì sao chọn cấu trúc và kết quả sau khi chạy.

Không nhảy bước: nếu cần environment variable hoặc schema đã tạo trước, phải chỉ rõ cách chuẩn bị. Output mong đợi nên được ghi lại; nếu ID hoặc timestamp động, mô tả phần nào thay đổi.

## 12. Language, project và API reference

Reference là tài liệu tra cứu chính xác, khác với tutorial.

### 12.1. Language reference

Mô tả grammar, keyword, type, operator precedence, built-in function, null behavior, error semantics và version availability.

### 12.2. Project reference

Mô tả module, entry point, workflow, rule, schema, connector, configuration, resource và permission.

### 12.3. API reference

Nếu project cung cấp API hoặc extension, ghi operation, method/path, parameter, request/response schema, error code, authentication, rate limit, compatibility và ví dụ.

### 12.4. Config reference

| Key | Type | Required | Default | Mô tả |
|---|---|---|---|---|
| billing.endpoint | URL | Có | Không có | Endpoint billing |
| billing.timeout | Duration | Không | 5 seconds | Thời gian chờ |
| workflow.maxAttempts | Integer | Không | 3 | Số lần thử tối đa |
| logging.level | Enum | Không | INFO | Mức log |

### 12.5. Error reference

Mỗi error code nên có mô tả, nguyên nhân, khả năng retry, hành động đề xuất và thông tin cần cung cấp khi báo sự cố.

## 13. Tài liệu kiến trúc

Architecture document giải thích các thành phần và cách chúng tương tác.

### 13.1. System context

Sơ đồ context cho thấy project nằm giữa hệ thống nào, ai gọi nó và dữ liệu đi qua đâu.

~~~text
Order Application
       |
       v
Order DSL Runtime
   |          |
   v          v
Inventory   Payment
 Service     Service
~~~

### 13.2. Component và data flow

Mô tả parser, compiler, runtime, connector, persistence, scheduler và module quan trọng. Data flow cần nêu dữ liệu vào, transformations, nơi lưu trữ và output.

### 13.3. Sequence diagram

Dùng sequence diagram cho use case có nhiều participant, ví dụ workflow gọi inventory rồi payment.

### 13.4. Architecture decision record

Với quyết định quan trọng, ghi bối cảnh, các phương án, quyết định, lý do, hệ quả và điều kiện xem xét lại. Decision record giúp người bảo trì hiểu vì sao project được thiết kế theo cách hiện tại.

### 13.5. Giữ sơ đồ đồng bộ

Sơ đồ cần có source hoặc quy trình cập nhật. Sơ đồ cũ có thể tạo hiểu lầm.

## 14. Examples và sample project

Examples là một phần của documentation và cũng là tài sản có thể đóng gói.

- Ví dụ nhỏ tập trung vào một khái niệm.
- Ví dụ end-to-end kết hợp schema, rule, workflow, config và test.
- Fixture dùng dữ liệu giả lập.
- Example nên chạy được tự động trong CI.
- Sample project có README giải thích mục đích, prerequisite, command và output.
- Tên ví dụ nên phản ánh mục tiêu như basic-query, retrying-integration hoặc order-fulfillment.

Examples nên được kiểm tra theo version DSL tương ứng để tài liệu không trở nên lỗi thời.

## 15. Tài liệu vận hành và troubleshooting

### 15.1. Deployment guide

Nêu runtime requirement, environment variable, resource, network access, permission và thứ tự triển khai.

### 15.2. Runbook

Runbook mô tả triệu chứng, kiểm tra ban đầu, log/metric cần xem, hành động phục hồi, thời điểm escalation và cách xác nhận dịch vụ ổn định.

### 15.3. Troubleshooting guide

Mỗi mục nên có symptom, nguyên nhân có thể, cách xác minh, cách khắc phục và cách phòng ngừa.

### 15.4. Observability

Ghi tên metric, log field, trace attribute và dashboard cần thiết. Không đưa token hoặc dữ liệu nhạy cảm vào ví dụ log.

### 15.5. Backup và recovery

Mô tả dữ liệu cần backup, retention, quy trình restore và cách kiểm tra sau phục hồi.

### 15.6. Operational limits

Nêu concurrency, timeout, payload size, throughput hoặc quota nếu ảnh hưởng đến vận hành.

## 16. Changelog và release notes

Changelog ghi lại thay đổi giữa các version. Release note giải thích tác động của bản phát hành đối với người dùng.

Có thể nhóm thay đổi thành Added, Changed, Fixed, Deprecated, Removed và Security.

Viết theo tác động người dùng thay vì chỉ liệt kê tên class hoặc file. Đánh dấu breaking change, version bị ảnh hưởng và cách chuyển đổi. Nêu known issues, workaround và link migration guide khi cần.

## 17. Semantic versioning và compatibility

Semantic Versioning thường biểu diễn version theo dạng MAJOR.MINOR.PATCH:

- MAJOR: thay đổi không tương thích.
- MINOR: thêm chức năng tương thích ngược.
- PATCH: sửa lỗi tương thích ngược.

### 17.1. Public contract

Nếu project công bố API, cần xác định public surface nào được versioning. Internal implementation không nhất thiết buộc tăng major nếu không thuộc contract.

### 17.2. Language và runtime version

Language version có thể được khai báo riêng trong manifest. Compiler mới có thể hỗ trợ nhiều language version. Ghi rõ runtime range được hỗ trợ.

### 17.3. Dependency compatibility

Release cần ghi dependency version tối thiểu/tối đa hoặc constraint đã được kiểm chứng.

### 17.4. Deprecation policy

Nêu thời gian hỗ trợ, warning và version dự kiến loại bỏ. Consumer cần đủ thời gian di trú.

## 18. Migration guide và nâng cấp package

Khi release thay đổi source hoặc configuration, cần hướng dẫn chuyển đổi:

1. Kiểm tra version hiện tại.
2. Backup source và dữ liệu cần thiết.
3. Cập nhật dependency.
4. Chạy migration tool hoặc sửa source.
5. Validate và compile.
6. Chạy test.
7. Triển khai staging.
8. Theo dõi rồi mới rollout.

Đưa ví dụ before/after, thứ tự migration, giới hạn của codemod, điều kiện rollback và trường hợp cần roll-forward. Không hứa tự động chuyển những semantics không thể suy luận.

## 19. License và third-party notices

Package phân phối cần có thông tin license phù hợp.

- LICENSE nêu điều kiện sử dụng, sao chép, sửa đổi và phân phối project.
- Third-party dependencies có thể yêu cầu notice hoặc attribution.
- Không tự suy đoán license khi chưa xác định quyền phân phối.
- Manifest có thể khai báo license identifier và link nội dung.
- Hình ảnh, font, dataset và snippet bên ngoài cũng có thể có điều kiện sử dụng.

## 20. Checksum, signature và package integrity

Consumer cần xác định package tải về có nguyên vẹn và đến từ nguồn đáng tin hay không.

### 20.1. Checksum

Checksum như SHA-256 giúp phát hiện file bị thay đổi trong quá trình lưu trữ hoặc tải xuống.

~~~bash
sha256sum order-automation-1.2.0.dslpkg
~~~

Giá trị checksum phải được phân phối qua kênh đáng tin cậy.

### 20.2. Digital signature

Chữ ký số giúp xác minh package được ký bởi identity tin cậy. Private key cần được bảo vệ trong signing service hoặc hệ thống quản lý key.

### 20.3. Provenance

Provenance ghi nhận source, commit, build pipeline, toolchain và artifact. Không đặt secret vào package.

## 21. Software Bill of Materials

Software Bill of Materials (SBOM) là danh sách thành phần phần mềm trong artifact.

SBOM có thể ghi package name, version, supplier, dependency relationship, license, hash và identifier như PURL hoặc CPE khi phù hợp.

SBOM giúp biết project chứa dependency nào, hỗ trợ rà soát license, theo dõi lỗ hổng và đánh giá ảnh hưởng khi dependency có sự cố. Nó cần gắn với artifact cụ thể và được tạo lại theo mỗi release.

## 22. CI/CD cho đóng gói và tài liệu hóa

CI/CD giúp build, tạo docs và package được thực hiện nhất quán.

~~~text
Commit
  |
  v
Resolve Dependencies
  |
  v
Validate DSL
  |
  v
Compile / Generate
  |
  v
Run Tests
  |
  v
Build Documentation
  |
  v
Assemble Package
  |
  v
Generate Checksums / SBOM
  |
  v
Publish Artifact
~~~

### 22.1. Build trên môi trường sạch

CI nên build từ checkout sạch và dependency lockfile để phát hiện file local bị thiếu.

### 22.2. Validate docs và examples

Có thể kiểm tra link, code fence, generated reference và chạy example trong môi trường test.

### 22.3. Package inspection

Liệt kê nội dung archive và xác nhận không có secret, file tạm hoặc artifact cũ.

### 22.4. Artifact retention và approval

Lưu artifact theo retention policy và liên kết với commit hoặc release ID. Có thể yêu cầu review trước khi publish package chính thức.

### 22.5. Không publish artifact chưa được xác minh

Pipeline cần kiểm tra build, metadata và điều kiện release trước khi đưa package lên registry.

## 23. Phân phối và cài đặt

Package có thể được phân phối qua registry, repository nội bộ, artifact store hoặc release page.

### 23.1. Registry và private package

Registry quản lý tên package, version, metadata và access control. Private registry cần authentication qua credential manager hoặc token có scope giới hạn.

### 23.2. Installation

README cần cung cấp lệnh cài đặt theo đúng toolchain.

~~~bash
dsl package install order-automation@1.2.0
~~~

Đây là cú pháp minh họa; CLI thực tế tùy hệ sinh thái.

### 23.3. Verify sau cài đặt

Kiểm tra package version, dependency resolution, entry point và runtime compatibility.

### 23.4. Offline installation

Nếu môi trường không có internet, hướng dẫn tải artifact, dependency cache và checksum qua kênh nội bộ.

### 23.5. Uninstall và upgrade

Mô tả cách gỡ package, cập nhật version và xử lý config hoặc data còn tồn tại sau uninstall.

## 24. Quyền truy cập và bảo mật khi phân phối

Package có thể chứa source DSL, schema và logic nghiệp vụ.

- Registry có thể giới hạn quyền theo team, project hoặc environment.
- CI nên quét credential vô tình được commit hoặc đóng gói.
- Consumer có thể xác minh signature, checksum và provenance.
- Token publish chỉ nên có quyền ghi package cần thiết.
- Token cài đặt chỉ cần quyền đọc.
- Không đưa dữ liệu production hoặc thông tin cá nhân vào example và fixture.

## 25. Ví dụ tổng hợp: Order Automation

Giả sử project có order schema, customer schema, rule phân loại đơn, workflow fulfillment, connector inventory/payment, test fixture và documentation.

### 25.1. Manifest

~~~yaml
name: order-automation
version: 1.2.0
dsl:
  languageVersion: 3.0
  runtime: 6.2
entry:
  workflow: dsl/workflows/fulfillment.workflow.dsl
dependencies:
  customer-schema: 2.1.0
  inventory-connector: 3.2.1
  payment-connector: 4.0.0
~~~

### 25.2. Build

1. Đọc manifest.
2. Resolve dependency.
3. Validate schema và DSL source.
4. Compile workflow và rule.
5. Thu thập resource.
6. Tạo runtime bundle.
7. Đóng gói manifest và docs.
8. Tạo checksum, SBOM và provenance.

### 25.3. Package layout

~~~text
order-automation-1.2.0.dslpkg
├── manifest.yml
├── runtime/
│   └── order-automation.bundle
├── schemas/
│   ├── order.schema
│   └── customer.schema
├── config/
│   └── defaults.yml
├── resources/
├── docs/
│   ├── README.md
│   ├── getting-started.md
│   └── operations.md
└── metadata/
    ├── checksums.txt
    ├── sbom.json
    └── provenance.json
~~~

### 25.4. README quick start

README hướng dẫn cài runtime tương thích, cài package, cung cấp inventory và payment credential qua secret manager, chọn environment profile, chạy sample order và kiểm tra workflow result cùng trace.

### 25.5. Documentation set

Project cung cấp getting started, architecture, reference cho schema/rule/config/error code, operations và migration guide.

### 25.6. Release

Khi phát hành version 1.2.0, cập nhật changelog, xác định compatibility, build từ commit đã tag, kiểm tra package content, tạo SBOM/checksum, ký artifact, publish lên registry và lưu provenance.

### 25.7. Consumer verification

Người nhận xác minh checksum hoặc signature, kiểm tra runtime version, cài package vào sandbox, cung cấp config riêng và chạy smoke test.

## 26. Checklist bàn giao project

### Source và cấu trúc

- [ ] Source DSL nằm trong folder có ý nghĩa.
- [ ] Entry point được khai báo.
- [ ] Resource được tham chiếu có mặt trong package.
- [ ] File tạm và secret không bị đóng gói.
- [ ] Generated artifact được tạo từ đúng source.

### Metadata và dependency

- [ ] Project name và version rõ.
- [ ] DSL language và runtime version được khai báo.
- [ ] Dependency có constraint hoặc lockfile.
- [ ] Package inclusion được xác định.
- [ ] License metadata có căn cứ.

### Documentation

- [ ] README nêu mục đích và prerequisite.
- [ ] Quick start có thể làm theo.
- [ ] Example có input và output mong đợi.
- [ ] Config reference mô tả required/default.
- [ ] Architecture và data flow được giải thích.
- [ ] Troubleshooting và operations guide có sẵn.
- [ ] Changelog và migration guide được cập nhật.

### Build và release

- [ ] Build chạy từ môi trường sạch.
- [ ] Package layout ổn định.
- [ ] Artifact có tên và version rõ.
- [ ] Checksum hoặc signature được tạo khi cần.
- [ ] SBOM và provenance gắn với artifact.
- [ ] CI lưu build và release metadata.
- [ ] Consumer có cách cài đặt và verify.

## 27. Những lỗi thường gặp

1. Package phụ thuộc file local chỉ có trên máy tác giả.
2. Manifest thiếu runtime version hoặc dependency constraint.
3. Lockfile không được cập nhật khiến build khác nhau.
4. Secret bị đưa vào package.
5. README không có lệnh chạy được hoặc prerequisite rõ.
6. Documentation lệch version source.
7. Package chứa build output cũ.
8. Không có changelog nên consumer không biết breaking change.
9. Không có checksum hoặc provenance khi cần xác minh artifact.
10. Không cài thử package từ archive nên bỏ sót resource bị thiếu.

## 28. Quy trình đóng gói và tài liệu hóa

1. Xác định consumer và mục đích phân phối.
2. Chuẩn hóa cấu trúc thư mục.
3. Xác định source, resource, config và generated artifact.
4. Tạo manifest với version, entry point và dependency.
5. Khóa dependency và pin toolchain.
6. Viết README và quick start.
7. Viết language/project/API reference.
8. Tạo architecture, operations và troubleshooting guide.
9. Cung cấp examples và test fixtures an toàn.
10. Cập nhật changelog, license và migration guide.
11. Build từ workspace sạch.
12. Assemble package theo include/exclude rule.
13. Kiểm tra package content và metadata.
14. Tạo checksum, signature, SBOM và provenance khi cần.
15. Cài thử package trong môi trường sạch.
16. Phát hành artifact và tài liệu theo cùng version.
17. Lưu release record và hướng dẫn nâng cấp.

## 29. Bài tập tự kiểm tra

### Bài 1: Cấu trúc project

Thiết kế folder layout cho DSL project có schema, rules, workflow, integrations, tests, examples và docs. Giải thích lý do phân chia.

### Bài 2: Manifest

Viết manifest có name, version, languageVersion, runtime, entry point, dependencies và package include list.

### Bài 3: Package contents

Cho workspace có source, cache, log, secret, tests và generated code. Xác định file nào nên có trong source package và runtime package.

### Bài 4: Reproducible build

Nêu các yếu tố cần pin hoặc chuẩn hóa để hai lần build từ cùng source tạo artifact tương đương.

### Bài 5: README

Viết mục lục README và xác định nội dung quick start tối thiểu.

### Bài 6: Architecture docs

Vẽ context diagram và sequence diagram cho workflow gọi inventory rồi payment.

### Bài 7: Versioning

Một release đổi tên field public và loại bỏ config key cũ. Xác định version phù hợp, changelog và migration guide.

### Bài 8: Supply chain

Giải thích vai trò checksum, digital signature, provenance và SBOM. Chỉ ra mỗi loại trả lời câu hỏi nào.

### Bài 9: CI/CD

Thiết kế pipeline build package, validate examples, tạo docs, inspect archive và lưu artifact.

### Bài 10: Bàn giao

Lập kế hoạch để developer mới tải package, cài runtime, cấu hình sandbox và chạy sample project mà không cần hỏi tác giả.

## Kết luận

Đóng gói và tài liệu hóa biến source DSL thành một project có thể sử dụng, phân phối và bảo trì. Một package đáng tin cậy cần manifest rõ ràng, dependency được quản lý, cấu hình tách khỏi secret, resource đầy đủ và artifact được tạo từ build có thể tái tạo. Tài liệu nên phục vụ nhiều nhu cầu: README giúp bắt đầu, tutorial hướng dẫn tác vụ, reference tra cứu contract, architecture giải thích cấu trúc và runbook hỗ trợ vận hành. Changelog, semantic versioning và migration guide giúp consumer hiểu tác động của release. Checksum, signature, provenance, license và SBOM hỗ trợ xác minh tính toàn vẹn và nguồn gốc package. Cuối cùng, build từ môi trường sạch, kiểm tra nội dung archive và cài thử package giúp phát hiện phụ thuộc chỉ tồn tại trên máy phát triển. Khi các thành phần này được duy trì cùng version của project, việc bàn giao và phát hành DSL trở nên rõ ràng, có thể lặp lại và đáng tin cậy.
