# Đóng gói sản phẩm DSL

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường được phát triển cùng compiler, runtime, thư viện, plugin và công cụ hỗ trợ. Khi một dự án đã sẵn sàng chuyển từ môi trường phát triển sang kiểm thử hoặc production, nhóm cần cung cấp một đơn vị phân phối có thể cài đặt, cấu hình, chạy và nâng cấp một cách nhất quán. Công việc đó được gọi là **đóng gói sản phẩm** (*product packaging*).

Đóng gói sản phẩm là quá trình tập hợp mã nguồn hoặc artifact đã biên dịch, runtime cần thiết, metadata, dependency, cấu hình mặc định, tài liệu và thông tin phiên bản thành một hoặc nhiều package có cấu trúc xác định. Package phải mô tả rõ cách cài đặt, kiểm tra tính toàn vẹn, khởi chạy, cập nhật và gỡ bỏ sản phẩm. Với DSL, package còn cần bảo đảm compiler, runtime, plugin và phiên bản ngôn ngữ tương thích với nhau.

Một package tốt giúp sản phẩm được chuyển giao từ nhóm phát triển sang nhóm vận hành hoặc khách hàng mà không phụ thuộc vào những file rời rạc trên máy lập trình viên. Nó cũng tạo cơ sở cho build tái lập, phân phối an toàn, rollback và kiểm soát vòng đời. Đóng gói vì vậy là một phần của quy trình xây dựng và triển khai sản phẩm, không chỉ là nén thư mục thành ZIP.

## 1. Đóng gói sản phẩm là gì?

### 1.1. Khái niệm

Package là đơn vị phân phối được tạo từ một sản phẩm hoặc thành phần phần mềm. Một package có thể chứa:

- Source DSL hoặc model đã chuẩn hóa.
- Artifact đã biên dịch như bytecode, IR hoặc mã sinh.
- Runtime hoặc thông tin runtime dependency.
- Plugin và thư viện phụ thuộc.
- Manifest mô tả package.
- Cấu hình mặc định và schema cấu hình.
- Tài liệu, license và hướng dẫn cài đặt.
- Checksum, chữ ký và metadata nguồn gốc build.

Không phải package nào cũng cần chứa tất cả các thành phần này. Thành phần cụ thể phụ thuộc vào người nhận, cách triển khai và mô hình cấp phép.

### 1.2. Phân biệt build, package và deploy

Ba hoạt động có liên quan nhưng khác mục tiêu:

| Hoạt động | Mục tiêu | Ví dụ đầu ra |
|---|---|---|
| Build | Biến source thành artifact có thể sử dụng | Bytecode, generated source, IR |
| Package | Tập hợp artifact và metadata thành đơn vị phân phối | ZIP, JAR, OCI image |
| Deploy | Đưa package vào môi trường và cấu hình để chạy | Release đang hoạt động |

Build có thể tạo nhiều artifact. Packaging chọn và sắp xếp chúng theo cấu trúc sản phẩm. Deployment cài đặt package vào môi trường cụ thể, kết nối cấu hình và dịch vụ cần thiết.

### 1.3. Package không phải bản sao workspace

Workspace phát triển thường chứa:

- File tạm.
- Cache.
- Log debug.
- IDE metadata.
- Test output.
- Credential cục bộ.
- File build trung gian.

Những nội dung này thường không thuộc sản phẩm phát hành. Package cần được tạo từ danh sách artifact được kiểm soát, tránh đóng gói toàn bộ thư mục làm việc.

### 1.4. Package là hợp đồng chuyển giao

Người nhận package cần biết:

- Package chứa những gì.
- Cần phiên bản runtime nào.
- Cách cấu hình.
- Cách xác minh tính toàn vẹn.
- Cách cài đặt và khởi chạy.
- Cách nâng cấp và rollback.
- Những giới hạn hoặc tính năng được hỗ trợ.

Nếu các thông tin này không rõ, package có thể cài được trên máy tạo ra nó nhưng thất bại ở môi trường khác.

## 2. Mục tiêu của đóng gói DSL

### 2.1. Tính nhất quán

Cùng một package cần có cùng nội dung dù được cài trên máy developer, máy kiểm thử hay production. Khác biệt giữa các môi trường nên đến từ cấu hình bên ngoài được khai báo, không phải do package bị sửa thủ công.

### 2.2. Tính đầy đủ

Package phải có đủ artifact và dependency cần thiết để thực hiện chức năng được công bố. Nếu sản phẩm yêu cầu runtime hoặc plugin riêng, manifest cần mô tả rõ yêu cầu đó.

### 2.3. Tính tái lập

Có thể tái tạo package từ source, toolchain, dependency và cấu hình build đã khóa. Điều này giúp điều tra sự cố và xác minh bản phát hành.

### 2.4. Tính toàn vẹn

Người nhận có thể xác minh package không bị thay đổi trong quá trình lưu trữ hoặc phân phối bằng checksum và chữ ký số.

### 2.5. Khả năng tương thích

Package phải khai báo phiên bản DSL, compiler, runtime, plugin API và nền tảng được hỗ trợ. Tránh cài một package lên môi trường không đáp ứng yêu cầu rồi chỉ phát hiện lỗi lúc chạy.

### 2.6. Khả năng vận hành

Package cần hỗ trợ cài đặt, cấu hình, quan sát, nâng cấp và gỡ bỏ theo quy trình có thể tự động hóa.

### 2.7. Khả năng bảo trì

Artifact, dependency, license và nguồn gốc build cần được ghi nhận để tổ chức biết mình đang vận hành phiên bản nào và có thể xử lý lỗ hổng ra sao.

## 3. Những thành phần của sản phẩm DSL

### 3.1. Source DSL

Source có thể gồm:

- File DSL.
- Schema và model miền.
- Rule, query hoặc workflow.
- Template sinh mã.
- Tài nguyên tham chiếu.

Source có thể được phân phối cho khách hàng để tùy chỉnh, hoặc chỉ được giữ nội bộ khi sản phẩm cung cấp runtime artifact.

### 3.2. Artifact biên dịch

Compiler có thể tạo:

- Abstract syntax tree đã tuần tự hóa.
- Intermediate representation (IR).
- Bytecode.
- Generated source.
- Query plan.
- Metadata tối ưu.

Artifact cần gắn với compiler và phiên bản định dạng tương ứng.

### 3.3. Runtime

Runtime có thể là:

- Thư viện được nhúng trong ứng dụng.
- Runtime service độc lập.
- Engine chạy trong container.
- Runtime module được cài cùng sản phẩm.
- Hosted execution service.

Package cần nói rõ runtime đã được bao gồm hay được cung cấp bên ngoài.

### 3.4. Plugin và extension

Plugin có thể cung cấp hàm miền, validator, backend, connector dữ liệu hoặc tính năng editor. Package có thể chứa plugin, khai báo dependency plugin hoặc yêu cầu người cài đặt lấy chúng từ registry.

### 3.5. Dependency

Dependency gồm thư viện, plugin, runtime component, native library và dịch vụ ngoài. Cần phân biệt dependency được đóng gói cùng sản phẩm với dependency phải tồn tại trong môi trường triển khai.

### 3.6. Manifest

Manifest mô tả package:

- ID và tên sản phẩm.
- Version.
- Artifact entry point.
- DSL và runtime version.
- Dependency.
- Platform hoặc architecture.
- Capability.
- Cấu hình và resource.
- Metadata build.

### 3.7. Configuration schema

Schema cấu hình mô tả tham số được phép, kiểu dữ liệu, giá trị mặc định, giới hạn và trường bắt buộc. Secret cần được tham chiếu từ secret provider thay vì nhúng vào package.

### 3.8. Documentation và license

Package có thể chứa README, release notes, license, third-party notices, hướng dẫn vận hành và migration notes. Những nội dung này giúp người nhận hiểu quyền sử dụng và cách vận hành sản phẩm.

### 3.9. Test artifact

Test fixture và smoke test có thể được phân phối cùng package hoặc trong một gói kiểm chứng riêng. Không nên đưa toàn bộ dữ liệu thử nghiệm nhạy cảm vào package production.

## 4. Các mô hình đóng gói

### 4.1. Source package

Source package chứa DSL và tài nguyên để người nhận tự biên dịch:

~~~text
orders-dsl-source/
  manifest.yml
  src/
    orders.dsl
    pricing.dsl
  schemas/
    order.schema.yml
  plugins.lock
  README.md
~~~

Ưu điểm là dễ tùy chỉnh và kiểm tra. Đổi lại, người nhận cần toolchain tương thích và có thể cần quyền truy cập source.

### 4.2. Binary package

Binary package chứa artifact đã biên dịch như IR hoặc bytecode. Nó giảm yêu cầu build tại nơi cài đặt nhưng phụ thuộc vào runtime tương thích.

### 4.3. Self-contained package

Package tự chứa runtime và dependency cần thiết. Người dùng có thể cài đặt mà không phải chuẩn bị nhiều thành phần riêng.

Ưu điểm là đơn giản khi triển khai; nhược điểm là package lớn hơn, cần cập nhật runtime trong mỗi lần phát hành và phải kiểm soát license của thành phần đi kèm.

### 4.4. Thin package

Thin package chỉ chứa artifact của ứng dụng và khai báo dependency cần cài riêng. Mô hình này giảm kích thước nhưng cần dependency registry và quy trình resolution đáng tin cậy.

### 4.5. Plugin package

Plugin package chỉ chứa extension cho một host đã có. Nó cần khai báo host API version, dependency và capability.

### 4.6. Runtime service package

Runtime service có thể được đóng gói thành container image hoặc binary service. Package thường chứa runtime, cấu hình mặc định và health endpoint.

### 4.7. Workbench distribution

Workbench có thể được phân phối dưới dạng ứng dụng desktop, extension IDE hoặc dịch vụ web. Các thành phần giao diện và server có thể được đóng gói riêng.

### 4.8. SaaS product

Với sản phẩm SaaS, người dùng không nhận runtime package theo cách truyền thống. Nhà cung cấp triển khai server, còn khách hàng có thể nhận SDK, CLI, plugin hoặc package mô hình để tương tác.

### 4.9. Chọn mô hình

| Nhu cầu | Mô hình thường phù hợp |
|---|---|
| Khách hàng tự sửa DSL | Source package |
| Chạy artifact đã biên dịch | Binary package |
| Cài đặt đơn giản, ít dependency ngoài | Self-contained package |
| Mở rộng host có sẵn | Plugin package |
| Triển khai engine độc lập | Runtime service package |
| Cung cấp môi trường phát triển | Workbench distribution |

## 5. Cấu trúc thư mục package

### 5.1. Cấu trúc tham khảo

Một package DSL có thể được tổ chức như sau:

~~~text
order-policy-2.4.0/
  manifest.yml
  artifacts/
    order-policy.ir
  runtime/
    runtime-requirements.yml
  plugins/
    commerce-extension.jar
  schemas/
    order-result.schema.json
  config/
    default.yml
    config.schema.json
  docs/
    README.md
    CHANGELOG.md
    MIGRATION.md
  licenses/
    LICENSE
    THIRD-PARTY-NOTICES.txt
  checksums/
    SHA256SUMS
~~~

Đây là cấu trúc minh họa. Package thực tế có thể dùng layout khác, miễn manifest xác định rõ vị trí và ý nghĩa của từng thành phần.

### 5.2. Tách source và artifact

Nếu sản phẩm có cả source và binary, nên đặt ở vị trí riêng hoặc tạo hai package. Điều này giúp kiểm soát quyền truy cập, kích thước và mục đích phân phối.

### 5.3. Không đóng gói file không cần thiết

Loại bỏ:

- Cache và temporary file.
- Credential.
- Log phát triển.
- IDE workspace state.
- Test output không cần thiết.
- File backup cũ.
- Dependency không được sử dụng.

### 5.4. Đường dẫn tương đối

Package nên dùng đường dẫn tương đối hoặc cơ chế resource lookup của runtime. Tránh hard-code đường dẫn máy build vì package cần chạy ở môi trường khác.

### 5.5. Quyền file

Với package chứa script hoặc executable, cần xác định quyền chạy. Không nên cấp quyền ghi cho toàn bộ file nếu chỉ cần đọc.

## 6. Manifest sản phẩm

### 6.1. Vai trò

Manifest là metadata có cấu trúc để công cụ cài đặt và runtime hiểu package mà không cần suy đoán từ tên file.

### 6.2. Ví dụ manifest

~~~yaml
product:
  id: com.example.order-policy
  name: Order Policy
  version: 2.4.0
  description: Rule set for order decisions

language:
  id: order-dsl
  version: 3
  artifactFormat: 2

runtime:
  id: dsl-runtime
  version: ">= 5.1 < 6.0"
  entrypoint: artifacts/order-policy.ir

dependencies:
  plugins:
    - id: com.example.dsl.commerce
      version: 1.8.2

platforms:
  - os: linux
    architecture: x86_64

configuration:
  schema: config/config.schema.json
  defaults: config/default.yml
~~~

Đây là một schema khái niệm. Hệ thống thật cần quy định kiểu, required field, version range và cách xử lý metadata không nhận diện.

### 6.3. Product ID

Product ID cần ổn định và duy nhất trong registry hoặc phạm vi tổ chức. Tên hiển thị có thể đổi mà không làm thay đổi định danh package.

### 6.4. Entry point

Entry point chỉ artifact hoặc module mà runtime cần nạp đầu tiên. Nó cần nằm trong phạm vi package và được kiểm tra trước khi thực thi.

### 6.5. Capability

Manifest có thể công bố capability như query execution, rule evaluation, streaming hoặc plugin extension. Runtime dùng thông tin này để xác định package có phù hợp với môi trường hay không.

### 6.6. Manifest version

Schema của manifest cũng cần version. Khi schema thay đổi, installer cần biết cách đọc phiên bản cũ hoặc từ chối package không tương thích.

## 7. Quản lý phiên bản sản phẩm

### 7.1. Product version

Product version nhận diện một bản phát hành. Nó thường theo semantic versioning:

- MAJOR: thay đổi không tương thích.
- MINOR: thêm tính năng tương thích ngược.
- PATCH: sửa lỗi tương thích ngược.

Đây là quy ước phổ biến; tổ chức cần định nghĩa rõ phạm vi tương thích của sản phẩm.

### 7.2. Các version độc lập

Một sản phẩm DSL có thể có nhiều version:

- Product version.
- DSL language version.
- Compiler version.
- IR format version.
- Runtime version.
- Plugin API version.
- Plugin version.
- Schema version.

Không nên giả định chúng luôn tăng cùng nhau.

### 7.3. Compatibility range

Manifest có thể khai báo khoảng runtime hoặc plugin API được hỗ trợ. Installer cần kiểm tra version thực tế trước khi cài.

### 7.4. Pre-release

Các bản alpha, beta hoặc release candidate cần có nhãn riêng và không nên bị coi là bản stable nếu policy chưa cho phép.

### 7.5. Build metadata

Build metadata có thể ghi commit, build number hoặc pipeline ID. Nó hữu ích cho truy vết nhưng không nhất thiết là một phần của thứ tự ưu tiên version.

### 7.6. Không tái sử dụng version

Một version đã phát hành nên trỏ đến nội dung bất biến. Nếu cần sửa artifact, hãy phát hành version mới thay vì ghi đè package cũ.

## 8. Quản lý dependency

### 8.1. Dependency trực tiếp và gián tiếp

Dependency trực tiếp được package khai báo rõ. Dependency gián tiếp được kéo vào bởi thư viện hoặc plugin khác. Cả hai đều cần được biết để kiểm soát tương thích và bảo mật.

### 8.2. Dependency declaration

Manifest cần khai báo:

- Package ID.
- Version hoặc version range.
- Nguồn registry.
- Capability hoặc module cần thiết.
- Phạm vi bắt buộc hay tùy chọn.

### 8.3. Lockfile

Lockfile ghi lại phiên bản cụ thể đã được resolve:

~~~yaml
dependencies:
  - id: com.example.dsl.commerce
    version: 1.8.2
    checksum: sha256:...
  - id: com.example.money
    version: 2.1.0
    checksum: sha256:...
~~~

Nhờ lockfile, build sau có thể dùng cùng tập dependency thay vì resolve một phiên bản mới theo thời điểm.

### 8.4. Dependency conflict

Hai plugin có thể yêu cầu hai version không tương thích của cùng thư viện. Package manager cần giải quyết bằng version constraint, isolation hoặc báo lỗi rõ ràng.

### 8.5. Dependency optional

Dependency optional chỉ cần khi một capability cụ thể được bật. Runtime cần kiểm tra capability trước khi gọi thành phần tùy chọn.

### 8.6. Vendoring

Vendoring đưa dependency vào package. Nó giúp cài đặt offline và cố định nội dung, nhưng làm tăng kích thước và trách nhiệm cập nhật bảo mật.

### 8.7. Dependency từ xa

Nếu runtime tải dependency khi khởi chạy, cần kiểm soát registry, checksum, timeout, cache và chính sách offline. Không nên tải bản mới nhất một cách âm thầm trong production.

## 9. Reproducible build

### 9.1. Khái niệm

Reproducible build là khả năng tạo ra artifact giống nhau từ cùng source, toolchain, dependency và cấu hình build đã xác định.

### 9.2. Những nguyên nhân gây khác biệt

- Dependency không khóa version.
- Timestamp được nhúng vào archive.
- File được đóng gói theo thứ tự không xác định.
- Locale hoặc timezone khác nhau.
- Compiler version khác nhau.
- Environment variable ảnh hưởng output.
- Generated ID hoặc random value.
- File path phụ thuộc máy build.

### 9.3. Khóa toolchain

Ghi rõ compiler, runtime, package manager và phiên bản công cụ tạo package. Có thể dùng build container hoặc toolchain image đã cố định.

### 9.4. Khóa dependency

Dùng lockfile và checksum. Không chỉ khóa dependency trực tiếp mà cần kiểm soát cả dependency bắc cầu.

### 9.5. Chuẩn hóa archive

Để tạo archive xác định, cần chuẩn hóa:

- Thứ tự file.
- Timestamp.
- Permission.
- Encoding.
- Metadata không cần thiết.

### 9.6. Build từ source revision

Mỗi package cần tham chiếu commit hoặc revision nguồn. Không build từ workspace có thay đổi chưa commit mà không ghi nhận.

### 9.7. So sánh artifact

Có thể build hai lần trong môi trường sạch và so sánh checksum. Nếu khác, điều tra metadata không xác định hoặc dependency chưa khóa.

## 10. Build pipeline cho sản phẩm DSL

### 10.1. Các bước tổng quát

~~~mermaid
flowchart TD
    A["Source DSL and Config"] --> B["Parse and Validate"]
    B --> C["Type and Semantic Checks"]
    C --> D["Compile or Generate"]
    D --> E["Resolve Dependencies"]
    E --> F["Assemble Package"]
    F --> G["Generate Manifest and SBOM"]
    G --> H["Checksum and Sign"]
    H --> I["Verify Package"]
    I --> J["Publish to Registry"]
~~~

### 10.2. Parse và validation

Kiểm tra cú pháp, schema, kiểu và semantics trước khi tạo artifact. Package không nên chứa model đã biết là không hợp lệ, trừ khi sản phẩm có mục đích phân phối source chưa biên dịch.

### 10.3. Compile hoặc generate

Tạo IR, bytecode, generated source hoặc artifact tương ứng. Output cần được đặt trong thư mục build riêng.

### 10.4. Dependency resolution

Resolve dependency theo manifest và lockfile. Nếu thiếu dependency bắt buộc hoặc có conflict, pipeline cần dừng.

### 10.5. Assembly

Tập hợp artifact, resource, config schema, documentation và license vào package layout.

### 10.6. Metadata generation

Sinh manifest cuối cùng, SBOM, build provenance và checksum. Metadata phải mô tả đúng nội dung thực tế được đóng gói.

### 10.7. Verification

Kiểm tra archive có thể mở, manifest hợp lệ, entry point tồn tại, dependency đầy đủ và chữ ký có thể xác minh.

### 10.8. Publish

Đưa package bất biến lên registry hoặc kho artifact. Chỉ publish sau khi các bước xác minh thành công.

## 11. Định dạng package

### 11.1. ZIP và TAR

ZIP và TAR phù hợp với package chứa nhiều file, resource và metadata. Chúng dễ phân phối và có thể được giải nén trên nhiều nền tảng.

### 11.2. JAR và module archive

Nếu compiler hoặc runtime dựa trên JVM, JAR có thể chứa class, resource và metadata. Package nhiều module có thể dùng một archive cấp cao hơn để chứa các JAR và manifest.

### 11.3. Native package

Trên một số hệ điều hành, sản phẩm có thể được phân phối bằng installer hoặc package manager native. Những định dạng này có thể tích hợp quyền, service và uninstall.

### 11.4. OCI container image

Runtime service có thể được đóng gói thành OCI image để triển khai trên container platform. Image cần có tag version bất biến hoặc digest, entrypoint, health check và metadata.

### 11.5. WebAssembly module

Một DSL runtime hoặc plugin có thể được đóng gói thành WebAssembly module nếu host hỗ trợ. Cần công bố import, export, ABI và giới hạn runtime.

### 11.6. Package manager riêng

Một hệ sinh thái DSL có thể xây package format riêng để quản lý manifest, dependency, plugin và artifact. Format riêng cần có tài liệu, schema version và công cụ kiểm tra.

### 11.7. Chọn định dạng

Chọn định dạng dựa trên:

- Nền tảng triển khai.
- Khả năng cài đặt và cập nhật.
- Cách quản lý dependency.
- Yêu cầu offline.
- Kích thước artifact.
- Cách ký và xác minh.
- Tích hợp với registry hiện có.

## 12. Đóng gói cho nhiều nền tảng

### 12.1. OS và architecture

Native artifact có thể phụ thuộc OS và CPU architecture. Manifest cần công bố target như Linux x86_64, Linux ARM64 hoặc Windows x64.

### 12.2. Cross-compilation

Cross-compilation tạo artifact cho target khác với máy build. Cần kiểm tra toolchain, native library và ABI của target.

### 12.3. Portable artifact

IR hoặc bytecode có thể portable hơn native binary nếu runtime có trên các nền tảng. Tuy nhiên, plugin hoặc native connector vẫn có thể tạo phụ thuộc platform.

### 12.4. Platform matrix

CI có thể build và test từng target:

| Target | Build | Install test | Runtime smoke test |
|---|---|---|---|
| Linux x86_64 | Có | Có | Có |
| Linux ARM64 | Có | Có | Có |
| Windows x64 | Có | Có | Có |
| macOS ARM64 | Theo hỗ trợ | Theo hỗ trợ | Theo hỗ trợ |

Chỉ công bố target đã được kiểm chứng theo chính sách release.

### 12.5. Runtime matrix

Nếu package hỗ trợ nhiều runtime version, cần kiểm tra tổ hợp DSL version, artifact format, runtime version và plugin API. Ma trận lớn có thể được rút gọn theo các tổ hợp được cam kết hỗ trợ.

## 13. Cấu hình và môi trường

### 13.1. Không đóng cứng cấu hình môi trường

Package nên chứa default an toàn, còn endpoint, credential, region và tài nguyên production được cung cấp khi triển khai.

### 13.2. Configuration schema

Schema cấu hình nên định nghĩa:

- Tên trường.
- Kiểu dữ liệu.
- Required hay optional.
- Default value.
- Min/max hoặc pattern.
- Secret flag.
- Mô tả và ví dụ.

### 13.3. Environment-specific config

Có thể dùng cấu hình riêng cho development, staging và production, nhưng cần tránh tạo các package khác nhau chỉ vì endpoint hoặc secret khác nhau.

### 13.4. Secret management

Không nhúng password, API key, certificate private key hoặc token vào package. Sử dụng secret manager, environment injection hoặc credential provider.

### 13.5. Configuration precedence

Thứ tự ưu tiên có thể gồm:

1. Giá trị mặc định trong package.
2. File cấu hình môi trường.
3. Environment variable.
4. Secret provider.
5. Tham số khởi chạy được cho phép.

Quy tắc cần được công bố để tránh giá trị bị ghi đè ngoài ý muốn.

### 13.6. Validate trước khi chạy

Installer hoặc runtime nên validate cấu hình trước khi mở traffic. Lỗi cấu hình cần nêu trường, lý do và cách sửa mà không in secret.

## 14. Đóng gói runtime DSL

### 14.1. Runtime embedded

Runtime embedded được liên kết hoặc đóng gói trong ứng dụng chủ. Package ứng dụng cần chứa đúng thư viện runtime và plugin tương thích.

### 14.2. Runtime service

Runtime service chạy độc lập, nhận request qua API hoặc message queue. Package cần mô tả port, protocol, health check, resource requirement và scaling behavior.

### 14.3. Runtime version

Artifact DSL cần khai báo runtime version hoặc khoảng version hỗ trợ. Runtime nên từ chối artifact có format không tương thích bằng lỗi rõ ràng.

### 14.4. Runtime dependency

Runtime có thể cần JRE, native library, database driver hoặc system package. Cần xác định dependency nào nằm trong image và dependency nào do nền tảng cung cấp.

### 14.5. Plugin runtime

Nếu runtime nạp plugin động, manifest cần khóa plugin version và kiểm tra API compatibility trước khi khởi chạy.

### 14.6. Startup validation

Trước khi phục vụ request, runtime có thể:

- Đọc manifest.
- Xác minh artifact.
- Kiểm tra runtime version.
- Resolve plugin.
- Validate config.
- Nạp model và rule.
- Khởi tạo dependency.

Nếu bước bắt buộc thất bại, service không nên báo healthy.

### 14.7. Graceful shutdown

Runtime cần dừng nhận request mới, hoàn tất hoặc hủy tác vụ đang chạy theo policy, đóng connection và giải phóng resource.

## 15. Tương thích và schema evolution

### 15.1. Compatibility contract

Package cần mô tả:

- DSL language version.
- IR format version.
- Runtime API version.
- Plugin API version.
- Schema version.
- Platform requirement.

### 15.2. Backward compatibility

Runtime mới có thể chạy artifact cũ nếu vẫn hỗ trợ format và semantics trước đó. Điều này cần được kiểm thử, không chỉ suy ra từ số version.

### 15.3. Forward compatibility

Artifact mới chạy trên runtime cũ thường khó bảo đảm. Nếu runtime không hiểu node hoặc opcode mới, nó cần từ chối với diagnostic rõ thay vì bỏ qua.

### 15.4. Migration

Nếu package chứa schema hoặc state, release mới có thể cần migration. Migration cần có version nguồn, version đích, precondition và cách rollback.

### 15.5. Deprecation

API hoặc cú pháp sắp bị loại bỏ nên có giai đoạn cảnh báo. Release notes cần nêu thời điểm loại bỏ và hướng thay thế.

### 15.6. Không tự động nâng dependency ngoài ý muốn

Installer nên dùng version đã khóa hoặc policy đã duyệt. Việc tự lấy dependency mới nhất có thể thay đổi hành vi package mà không có release mới.

## 16. Bảo mật chuỗi cung ứng phần mềm

### 16.1. Package integrity

Checksum như SHA-256 giúp phát hiện nội dung thay đổi. Người nhận cần kiểm tra checksum từ nguồn tin cậy.

### 16.2. Chữ ký số

Chữ ký số xác nhận package được ký bởi khóa tương ứng và nội dung không bị sửa sau khi ký. Hệ thống cần quản lý private key an toàn và có quy trình xoay vòng, thu hồi khóa.

### 16.3. Signing pipeline

Chỉ ký artifact sau khi build và validation hoàn tất. Quyền ký nên được giới hạn trong pipeline release và không đặt private key trong source repository.

### 16.4. SBOM

Software Bill of Materials (SBOM) liệt kê component và dependency có trong package. SBOM giúp xác định sản phẩm có sử dụng thư viện bị ảnh hưởng bởi lỗ hổng hay không.

### 16.5. Build provenance

Provenance ghi nhận source revision, builder, pipeline, toolchain và tham số build. Nó giúp truy xuất package được tạo từ đâu và trong điều kiện nào.

### 16.6. Vulnerability scanning

Quét dependency và image để phát hiện lỗ hổng đã biết. Kết quả cần được đánh giá theo mức độ, khả năng khai thác và policy release.

### 16.7. License scanning

Dependency có thể có license với nghĩa vụ phân phối hoặc thông báo riêng. Package cần bao gồm third-party notices và tuân thủ điều khoản áp dụng.

### 16.8. Secret scanning

Quét package và repository để phát hiện credential vô tình được đóng gói. Nếu phát hiện secret, cần xử lý cả việc thu hồi credential chứ không chỉ xóa file khỏi archive.

### 16.9. Package không đáng tin

Installer cần xác minh chữ ký, nguồn registry và checksum trước khi cài. Không nên thực thi script cài đặt từ package chưa được tin cậy.

## 17. Registry và phân phối package

### 17.1. Package registry

Registry lưu package cùng metadata để người dùng tìm, tải, xác minh và cài đặt. Có thể là registry public, registry nội bộ hoặc artifact repository.

### 17.2. Immutable artifact

Một version đã publish nên bất biến. Nếu cần sửa, phát hành version mới. Ghi đè package cũ làm mất khả năng tái lập và gây khó khăn khi điều tra.

### 17.3. Tags và channels

Registry có thể phân loại:

- stable.
- beta.
- candidate.
- long-term-support.
- internal.

Tag có thể di chuyển theo policy, còn version và digest nên nhận diện nội dung bất biến.

### 17.4. Access control

Quyền publish, pull và quản trị package cần được tách biệt. Không phải mọi developer đều cần quyền phát hành production.

### 17.5. Replication và mirror

Tổ chức có thể mirror package để triển khai trong mạng nội bộ hoặc môi trường offline. Mirror cần giữ checksum, signature và metadata nguồn gốc.

### 17.6. Retention

Policy retention xác định package và artifact được lưu bao lâu. Cần giữ đủ version để rollback, audit và đáp ứng yêu cầu hỗ trợ.

### 17.7. Download reliability

Package lớn có thể cần resumable download, cache hoặc chunking. Installer cần xác minh checksum sau khi tải hoàn tất.

## 18. Cài đặt, nâng cấp và gỡ bỏ

### 18.1. Installation

Quy trình cài đặt có thể:

1. Xác minh package và chữ ký.
2. Kiểm tra platform và runtime requirement.
3. Resolve dependency.
4. Validate cấu hình.
5. Cài artifact vào vị trí quản lý.
6. Đăng ký service hoặc plugin nếu cần.
7. Chạy smoke check.
8. Ghi nhận version đã cài.

### 18.2. Upgrade

Upgrade cần xác định:

- Artifact nào được thay.
- Có migration không.
- Runtime có cần restart không.
- Có thể nâng cấp rolling không.
- Có tương thích với dữ liệu cũ không.

### 18.3. Atomic installation

Nếu có thể, cài version mới vào thư mục riêng rồi chuyển active pointer sau khi xác minh thành công. Điều này giảm nguy cơ package đang chạy bị thay một phần.

### 18.4. Uninstall

Gỡ sản phẩm cần phân biệt artifact, dữ liệu người dùng, cấu hình và log. Không nên xóa dữ liệu vận hành hoặc dữ liệu nghiệp vụ nếu chưa có policy rõ.

### 18.5. Side-by-side versions

Có thể giữ nhiều version cùng lúc để rollback hoặc chạy migration. Cần quản lý port, data directory và plugin isolation để chúng không xung đột.

### 18.6. Migration hook

Nếu package hỗ trợ pre-install hoặc post-install hook, hook cần có hợp đồng, timeout, logging và quyền giới hạn. Không chạy script tùy ý với quyền quản trị nếu không cần thiết.

## 19. Triển khai và cấu hình theo môi trường

### 19.1. Cùng package qua các môi trường

Một nguyên tắc quan trọng là tạo package một lần rồi promote cùng artifact qua development, staging và production. Cấu hình môi trường được cung cấp bên ngoài.

### 19.2. Environment overlay

Mỗi môi trường có thể có cấu hình overlay:

~~~yaml
environment: production
runtime:
  replicas: 3
  logLevel: INFO
connections:
  orderStore:
    credentialRef: secret://prod/order-store
~~~

### 19.3. Không sửa package sau khi build

Nếu cần thay endpoint hoặc secret, thay cấu hình triển khai. Sửa file bên trong package làm mất checksum và provenance, đồng thời khiến các môi trường chạy nội dung khác nhau.

### 19.4. Deployment descriptor

Deployment descriptor mô tả resource, replica, network, volume, health check và policy. Nó có thể được đóng gói riêng để cùng package ứng dụng được triển khai trên nhiều môi trường.

### 19.5. Health và readiness

Health check xác nhận process còn hoạt động. Readiness cần xác nhận runtime đã nạp package, dependency bắt buộc và sẵn sàng nhận traffic.

### 19.6. Rolling và blue-green deployment

Với runtime service, có thể dùng rolling hoặc blue-green deployment. Cần kiểm tra compatibility giữa version mới và dữ liệu hoặc message đang tồn tại.

## 20. Rollback và phục hồi

### 20.1. Rollback package

Rollback chuyển active deployment về một package version trước đó. Nó đơn giản khi artifact bất biến và dữ liệu không bị migration phá hủy.

### 20.2. Rollback dữ liệu

Nếu release thay schema hoặc state, rollback code có thể không đủ. Cần migration ngược, compatibility window hoặc restore backup.

### 20.3. Expand-contract migration

Một chiến lược an toàn:

1. Thêm schema mới nhưng vẫn hỗ trợ schema cũ.
2. Triển khai runtime hiểu cả hai.
3. Chuyển dữ liệu và consumer.
4. Xác nhận không còn phụ thuộc cũ.
5. Loại bỏ schema cũ ở release sau.

### 20.4. Rollback không luôn an toàn

Nếu phiên bản mới đã tạo dữ liệu mà runtime cũ không hiểu, quay lại có thể gây lỗi. Cần xác định rollback condition và kiểm thử trước.

### 20.5. Recovery artifact

Giữ package, manifest, SBOM, signature và cấu hình release để có thể tái triển khai đúng version.

## 21. Offline và air-gapped packaging

### 21.1. Môi trường không có Internet

Một số tổ chức triển khai trong mạng nội bộ hoặc môi trường cách ly. Package cần chứa hoặc có thể truy xuất từ mirror mọi dependency bắt buộc.

### 21.2. Dependency bundle

Có thể tạo bundle chứa:

- Package chính.
- Plugin và thư viện phụ thuộc.
- Runtime component.
- Signature và checksum.
- SBOM.
- Tài liệu cài đặt.

### 21.3. Xác minh offline

Public key hoặc trust root cần được đưa vào môi trường theo kênh tin cậy. Không nên bỏ qua signature chỉ vì installer không truy cập được registry.

### 21.4. Cập nhật bảo mật

Môi trường offline vẫn cần quy trình nhập package đã quét và ký từ vùng trung gian. Cần theo dõi version và thời hạn hỗ trợ.

## 22. Tài liệu và trải nghiệm người nhận package

### 22.1. README

README nên nêu:

- Sản phẩm dùng để làm gì.
- Phiên bản và yêu cầu môi trường.
- Cách cài đặt.
- Cách cấu hình.
- Cách chạy smoke test.
- Cách xem log.
- Cách nâng cấp và rollback.
- Nơi nhận hỗ trợ.

### 22.2. Release notes

Release notes mô tả:

- Tính năng mới.
- Lỗi đã sửa.
- Thay đổi không tương thích.
- Dependency được cập nhật.
- Lỗ hổng đã xử lý.
- Migration cần chạy.
- Tính năng bị deprecated.

### 22.3. Migration guide

Migration guide cần có phiên bản nguồn, phiên bản đích, bước chuyển đổi, dữ liệu bị ảnh hưởng, điều kiện trước khi chạy và cách rollback.

### 22.4. Third-party notices

Thông báo license cần liệt kê các thành phần bên thứ ba theo nghĩa vụ phân phối. Không nên giả định mọi dependency có cùng license.

### 22.5. Runbook

Với runtime service, runbook mô tả cách kiểm tra health, xem log, xử lý lỗi, restart, scale và phục hồi.

## 23. Kiểm chứng package trước khi phát hành

### 23.1. Kiểm tra cấu trúc

Xác nhận archive có thể mở, manifest hợp lệ và mọi entry point đều tồn tại.

### 23.2. Cài trong môi trường sạch

Tạo môi trường không có dependency ngẫu nhiên từ máy build. Cài package để phát hiện file hoặc thư viện bị thiếu.

### 23.3. Smoke test

Chạy một ví dụ tối thiểu qua runtime và xác nhận output cơ bản. Smoke test không thay thế kiểm thử đầy đủ nhưng phát hiện lỗi đóng gói phổ biến.

### 23.4. Compatibility test

Kiểm tra package với các runtime và platform được công bố hỗ trợ.

### 23.5. Reproducibility check

Build lại từ cùng revision và so sánh artifact theo policy.

### 23.6. Signature verification

Xác minh chữ ký và checksum bằng công cụ độc lập hoặc installer thật.

### 23.7. License và SBOM check

Kiểm tra dependency, license notice và SBOM có khớp package hay không.

### 23.8. Installation lifecycle test

Thử install, upgrade, rollback và uninstall trong môi trường thử nghiệm. Xác nhận dữ liệu người dùng được bảo toàn theo policy.

### 23.9. Package size

Theo dõi kích thước package và thay đổi lớn giữa các release. Kích thước tăng đột ngột có thể do dependency trùng, file debug hoặc resource không cần thiết.

## 24. Ví dụ: đóng gói một sản phẩm rule DSL

Giả sử sản phẩm Order Policy chứa:

- Source DSL mô tả rule.
- Compiler tạo IR.
- Runtime đánh giá IR.
- Plugin commerce cung cấp hàm tính thuế.
- Schema mô tả input và output.

### 24.1. Source

~~~text
rule FreeShipping {
    when order.total >= 1000000 VND
    then shippingFee = Money.zero(VND)
}
~~~

### 24.2. Build

Pipeline parse và kiểm tra rule, resolve hàm, validate schema rồi tạo IR. Build ghi lại compiler version, DSL version và source revision.

### 24.3. Package layout

~~~text
order-policy-2.4.0/
  manifest.yml
  artifacts/
    order-policy.ir
  plugins/
    commerce-extension.jar
  schemas/
    order-input.schema.json
    decision-output.schema.json
  config/
    default.yml
    config.schema.json
  docs/
    README.md
    CHANGELOG.md
  licenses/
    THIRD-PARTY-NOTICES.txt
  checksums/
    SHA256SUMS
  sbom/
    sbom.json
~~~

### 24.4. Manifest

Manifest khai báo product ID, version 2.4.0, DSL version, IR format, runtime range, plugin commerce version và entry point.

### 24.5. Cài đặt

Installer xác minh signature, kiểm tra platform, resolve runtime, cài package vào version directory và validate config.

### 24.6. Khởi chạy

Runtime nạp manifest, kiểm tra IR format, nạp plugin, kết nối dependency được cấu hình rồi báo readiness.

### 24.7. Nâng cấp

Release 2.5.0 có thể thêm rule mới và schema output mới. Package mới được cài song song, chạy smoke test rồi chuyển traffic. Nếu schema tương thích, rollback có thể quay lại 2.4.0.

### 24.8. Truy vết

Khi một quyết định có lỗi, operator dùng product version, package digest, rule revision và plugin version để xác định đúng artifact đã tạo quyết định.

## 25. Ví dụ: đóng gói plugin DSL

Một plugin bổ sung validator cho workflow có thể có:

~~~text
workflow-validator-1.2.0/
  manifest.yml
  plugin/
    workflow-validator.jar
  docs/
    README.md
    CHANGELOG.md
  licenses/
    THIRD-PARTY-NOTICES.txt
  sbom/
    sbom.json
~~~

Manifest cần khai báo:

- Plugin ID và version.
- Plugin API version.
- Host version range.
- Extension point workflow.validator.
- Dependency.
- Capability được yêu cầu.
- Entry point.

Host chỉ nạp plugin nếu version tương thích và policy cho phép capability. Khi nâng plugin, cần kiểm tra validator cũ và mới trên cùng fixture để phát hiện thay đổi diagnostics.

## 26. Đóng gói và cấp phép

### 26.1. License của sản phẩm

Package có thể chứa license file hoặc metadata chỉ rõ quyền sử dụng. Nếu sản phẩm thương mại, installer có thể cần kiểm tra entitlement.

### 26.2. License của dependency

Dependency bên thứ ba có thể yêu cầu giữ copyright notice, cung cấp source hoặc tuân thủ điều kiện phân phối. Cần kiểm tra từng license.

### 26.3. Runtime license

Runtime có thể được cấp phép riêng với compiler hoặc workbench. Manifest và tài liệu cần nói rõ thành phần nào được bao gồm.

### 26.4. License server

Nếu runtime cần license server, cần xác định hành vi khi server tạm thời không truy cập được, cách cache entitlement và cách xử lý hết hạn.

### 26.5. Không nhúng credential cấp phép

Không đặt license key bí mật trong package công khai hoặc repository. Sử dụng cơ chế cấp phát và bảo vệ credential phù hợp.

## 27. Quan sát và quản trị package trong production

### 27.1. Package identity trong telemetry

Log và metrics nên ghi product version, package digest, runtime version và plugin set. Nhờ đó có thể phân biệt lỗi theo release.

### 27.2. Release inventory

Tổ chức cần biết package version nào đang chạy ở môi trường nào. Registry và deployment system có thể cung cấp inventory này.

### 27.3. Patch management

Khi một dependency có lỗ hổng, SBOM giúp xác định package bị ảnh hưởng. Quy trình patch cần tạo package mới, ký và triển khai theo policy.

### 27.4. Retention và audit

Giữ artifact và metadata đủ lâu để đáp ứng điều tra, rollback và yêu cầu audit. Không xóa package đang được một deployment tham chiếu.

### 27.5. End-of-life

Khi một version hết hỗ trợ, cần công bố thời hạn, rủi ro và đường nâng cấp. Runtime có thể cảnh báo hoặc từ chối version không còn được phép theo policy.

## 28. Những sai lầm thường gặp

### 28.1. Nén toàn bộ workspace

Package chứa cache, log, file tạm và credential làm tăng kích thước, rủi ro bảo mật và khó tái lập. Nên đóng gói từ danh sách artifact rõ ràng.

### 28.2. Không có manifest

Nếu installer phải đoán entry point, runtime version hoặc dependency từ tên file, việc cài đặt dễ sai và khó tự động hóa.

### 28.3. Không khóa dependency

Build hôm nay và build tuần sau có thể resolve version khác nhau. Lockfile và checksum giúp giữ kết quả ổn định.

### 28.4. Đóng gói secret

Credential trong archive có thể bị lộ qua registry, backup hoặc máy khách. Secret phải được cấp lúc triển khai.

### 28.5. Dùng package khác nhau cho từng môi trường

Tạo package riêng cho staging và production dễ dẫn đến khác biệt không kiểm soát. Nên promote cùng artifact và thay cấu hình bên ngoài.

### 28.6. Ghi đè version đã phát hành

Thay nội dung của một version cũ phá tính bất biến, checksum và khả năng tái tạo. Phát hành version mới khi có thay đổi.

### 28.7. Bỏ qua runtime compatibility

Artifact compile thành công chưa chắc chạy trên runtime đích. Cần kiểm tra format version, plugin API và platform.

### 28.8. Không thử cài trong môi trường sạch

Máy build có thể vô tình cung cấp dependency mà package không chứa. Clean install test phát hiện lỗi này.

### 28.9. Không có rollback plan

Nâng cấp package có thể thay schema hoặc state. Cần xác định rollback có khả thi trước khi triển khai.

### 28.10. Không tạo SBOM và provenance

Khi phát hiện lỗ hổng hoặc cần điều tra nguồn gốc, tổ chức sẽ khó xác định dependency và builder của package.

## 29. Quy trình đóng gói sản phẩm DSL

Một quy trình thực tế có thể gồm:

1. **Xác định loại package:** source, binary, self-contained, plugin hay runtime service.
2. **Xác định người nhận:** developer, khách hàng, operator, registry hoặc môi trường triển khai.
3. **Lập artifact inventory:** source, IR, runtime, plugin, schema, resource và tài liệu.
4. **Định nghĩa manifest:** product ID, version, entry point, compatibility và capability.
5. **Khóa toolchain:** compiler, package manager, runtime và build environment.
6. **Resolve dependency:** dùng version constraint và lockfile.
7. **Build artifact:** parse, validate, compile hoặc generate.
8. **Assemble package:** đặt file theo layout và loại bỏ nội dung không cần.
9. **Sinh metadata:** manifest, SBOM, provenance, checksum và notices.
10. **Ký package:** dùng key được bảo vệ trong release pipeline.
11. **Kiểm chứng:** clean install, smoke test, compatibility và signature verification.
12. **Publish:** đưa artifact bất biến lên registry.
13. **Promote:** triển khai cùng package qua các môi trường với cấu hình riêng.
14. **Theo dõi:** inventory, logs, metrics, version và lỗ hổng.
15. **Nâng cấp hoặc rollback:** theo migration và compatibility policy.

## 30. Câu hỏi tự đánh giá

1. Đóng gói sản phẩm khác build và deploy như thế nào?
2. Một DSL package có thể chứa những thành phần nào?
3. Source package, binary package và self-contained package khác nhau ra sao?
4. Manifest cần mô tả những trường nào?
5. Vì sao product version khác DSL version và runtime version?
6. Lockfile giúp reproducible build như thế nào?
7. Những yếu tố nào khiến hai lần build tạo artifact khác nhau?
8. ZIP, JAR, OCI image và WebAssembly module phù hợp với tình huống nào?
9. Vì sao không nên nhúng secret vào package?
10. Checksum, chữ ký số, SBOM và provenance có vai trò gì?
11. Làm thế nào promote cùng một package qua nhiều môi trường?
12. Rollback code khác rollback dữ liệu như thế nào?
13. Package offline cần chứa hoặc tham chiếu những gì?
14. Vì sao cần clean install và smoke test trước khi phát hành?

## Kết luận

Đóng gói sản phẩm DSL là quá trình biến source, model, artifact biên dịch, runtime, plugin, dependency và metadata thành một đơn vị phân phối có thể cài đặt và vận hành. Một package đáng tin cậy cần có manifest rõ, version và dependency được khóa, cấu trúc ổn định, cấu hình tách khỏi môi trường, tài liệu đầy đủ và quy tắc tương thích xác định.

Quy trình phát hành nên tạo artifact tái lập, sinh SBOM và provenance, tạo checksum, ký số, kiểm tra trong môi trường sạch rồi publish package bất biến lên registry. Khi triển khai, cùng một artifact nên được promote qua các môi trường bằng cấu hình bên ngoài. Cài đặt, nâng cấp, migration, rollback và gỡ bỏ đều cần được thiết kế như một phần của vòng đời package. Nhờ vậy, sản phẩm DSL có thể được chuyển giao, kiểm soát và duy trì nhất quán từ máy phát triển đến production.
