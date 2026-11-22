# Tính tái lập

## 1. Tính tái lập là gì?

Tính tái lập (reproducibility) là khả năng tạo lại cùng một kết quả từ cùng một tập đầu vào, cấu hình và quy trình đã được xác định. Trong quá trình xây dựng và triển khai DSL (Domain-Specific Language), tính tái lập giúp developer, CI và môi trường phát hành tạo ra artifact có thể kiểm chứng, giải thích và phục hồi.

Ví dụ, một project DSL có source, schema, compiler, runtime, plugin build và dependency. Nếu tất cả đầu vào giống nhau nhưng hai lần build tạo ra bytecode hoặc generated source khác nhau, kết quả chưa tái lập ở mức byte. Nếu hai artifact khác byte nhưng có cùng semantics và hành vi theo hợp đồng, chúng có thể tái lập về mặt chức năng nhưng không phải bit-for-bit reproducible.

Một quy trình tái lập cần xác định rõ:

- Những đầu vào nào quyết định kết quả.
- Phiên bản compiler, runtime và toolchain nào được sử dụng.
- Dependency nào được resolve và từ nguồn nào.
- Môi trường build có những thuộc tính gì.
- Cách xử lý timestamp, random value, thứ tự file và locale.
- Artifact nào được tạo và cách xác minh artifact.
- Cấu hình triển khai nào được dùng khi chạy artifact.

Tính tái lập không chỉ dành cho compiler. Nó còn áp dụng cho code generation, documentation generation, packaging, container image, workflow deployment, schema migration và các bước phát hành khác.

## 2. Vì sao tính tái lập quan trọng với DSL?

Một DSL có thể tạo ra nhiều loại artifact:

- Bytecode hoặc executable package.
- Generated source code.
- AST hoặc IR đã tuần tự hóa.
- Schema và migration script.
- Workflow definition hoặc rule bundle.
- Documentation và API reference.
- Container image hoặc deployment package.
- Metadata và manifest dùng ở runtime.

Nếu không thể tái tạo các artifact này, nhóm phát triển sẽ khó điều tra sự cố, so sánh release, xác minh nguồn gốc hoặc phục hồi môi trường cũ.

Tính tái lập mang lại:

1. **Build nhất quán:** cùng source và toolchain tạo cùng kết quả theo mức cam kết đã chọn.
2. **Debug đáng tin cậy:** có thể tái tạo artifact gây lỗi từ revision và cấu hình đã ghi nhận.
3. **Review rõ ràng:** thay đổi generated output phản ánh thay đổi đầu vào có chủ đích.
4. **Deployment an toàn:** môi trường staging và production triển khai cùng một artifact đã được kiểm thử.
5. **Cache chính xác:** build cache có thể tái sử dụng kết quả khi toàn bộ đầu vào liên quan giống nhau.
6. **Audit và provenance:** biết artifact được tạo từ source, dependency và công cụ nào.
7. **Khôi phục:** có thể tái tạo hoặc triển khai lại release đã phát hành.
8. **Supply-chain security:** có cơ sở kiểm chứng thành phần và nguồn tải.

Với DSL nghiệp vụ, tính tái lập còn giúp bảo đảm cùng một rule bundle hoặc workflow definition được diễn giải nhất quán giữa các môi trường, trong phạm vi semantics và runtime đã cam kết.

## 3. Các mức độ tái lập

Không phải mọi hệ thống đều cần cùng một mức tái lập. Cần xác định rõ mục tiêu:

| Mức | Cam kết | Ví dụ |
|---|---|---|
| Source reproducibility | Có thể lấy lại đúng source và cấu hình | Checkout cùng revision và manifest |
| Build reproducibility | Có thể chạy lại quy trình build với đầu vào đã khóa | Cùng compiler và dependency |
| Bit-for-bit reproducibility | Artifact có byte giống hệt | SHA-256 của hai package giống nhau |
| Functional reproducibility | Artifact có cùng semantics hoặc hành vi theo contract | Bytecode khác nhưng kết quả chương trình tương đương |
| Environment reproducibility | Có thể tái tạo môi trường chạy | Cùng container image, runtime và config schema |
| Deployment reproducibility | Có thể triển khai lại cùng artifact và cấu hình đã xác định | Cùng image digest và deployment manifest |

Bit-for-bit reproducibility là mục tiêu mạnh và dễ xác minh bằng hash, nhưng có thể khó đạt nếu toolchain ghi timestamp, random identifier hoặc đường dẫn máy local vào output.

Functional reproducibility phù hợp khi artifact chứa metadata không ổn định nhưng semantics vẫn giống nhau. Tuy nhiên, cần có cách so sánh đáng tin cậy như normalized output, semantic test hoặc conformance test.

Không nên tuyên bố "reproducible" mà không nêu rõ mức nào và phạm vi nào được bảo đảm.

## 4. Đầu vào quyết định kết quả build

Build output phụ thuộc vào nhiều yếu tố hơn source file. Một build model nên xem xét:

- DSL source và generated source đầu vào.
- Schema, grammar và module manifest.
- Compiler, parser generator và code generator.
- Runtime SDK và build plugin.
- Dependency trực tiếp và dependency bắc cầu.
- Cấu hình compiler và target platform.
- Environment variable được phép ảnh hưởng build.
- JDK, native compiler và hệ điều hành nếu liên quan.
- Locale, timezone, encoding và line ending.
- Template và resource được đóng gói.

Một build có thể được mô hình hóa:

~~~text
artifact = build(
    sourceRevision,
    toolchain,
    dependencies,
    buildConfiguration,
    targetPlatform,
    controlledEnvironment
)
~~~

Nếu một yếu tố có thể làm thay đổi output, nó phải được khóa, được ghi nhận hoặc được loại bỏ khỏi build. Những đầu vào không được kiểm soát là nguồn phổ biến của build không tái lập.

## 5. Quản lý source revision

Source revision xác định nội dung đầu vào của build. Thường dùng commit ID của version control, nhưng cần lưu ý source tree có thể chứa thay đổi chưa commit hoặc file generated không được quản lý.

Một quy trình build phát hành nên ghi:

- Repository identity.
- Commit hoặc revision ID.
- Branch hoặc tag dùng để tạo release.
- Trạng thái working tree có sạch hay không.
- Submodule revision nếu có.
- Git LFS object hoặc file lớn đã được tải đúng hay chưa.
- Source archive checksum.

Ví dụ:

~~~yaml
source:
  repository: example/pricing-rules
  revision: 7f31c2a
  dirty: false
~~~

Nếu build từ working tree có thay đổi chưa commit, revision ID không đủ để tái tạo source. CI phát hành nên build từ checkout sạch hoặc lưu patch và checksum của mọi đầu vào bổ sung.

### 5.1. Generated source

Generated source có thể được commit hoặc tạo lại trong build. Cả hai cách đều có thể dùng được, nhưng cần quy định nguồn sự thật:

- Nếu generated source được commit, cần kiểm tra nó đồng bộ với source và generator.
- Nếu generated source được tạo trong build, cần khóa generator version và input.
- Nếu generated source phụ thuộc vào environment, cần đưa các yếu tố đó vào build model hoặc loại bỏ sự phụ thuộc.

Không nên vừa sửa generated file thủ công vừa mong generator tạo lại cùng kết quả. Thay đổi cần được thực hiện ở source hoặc template có thẩm quyền.

## 6. Pinning toolchain và dependency

Compiler hoặc runtime thay đổi có thể làm output khác dù DSL source không đổi. Vì vậy, project cần khai báo phiên bản chính xác cho các công cụ quan trọng.

Ví dụ:

~~~yaml
toolchain:
  dslCompiler: 4.2.1
  dslRuntime: 5.0.2
  parserGenerator: 4.13.1
  formatter: 1.8.3
  buildPlugin: 5.1.0
  documentationGenerator: 2.6.0
~~~

Manifest cần được build tool đọc và xác minh. Chỉ ghi version trong README không bảo đảm build thực sự sử dụng đúng công cụ.

### 6.1. Dependency lockfile

Manifest có thể khai báo version range, còn lockfile ghi kết quả resolve cụ thể cho cả dependency bắc cầu.

Lockfile thường cần lưu:

- Package name và exact version.
- Repository hoặc registry.
- Checksum của artifact.
- Dependency graph.
- Platform variant nếu package có nhiều bản.

Ví dụ:

~~~text
dsl-compiler 4.2.1
  parser-core 2.6.0
  diagnostics-api 1.9.2
dsl-runtime 5.0.2
  expression-vm 3.4.1
  money-types 2.2.0
~~~

Commit lockfile giúp các lần build resolve cùng dependency. Khi cập nhật dependency, diff lockfile cần được review để phát hiện package mới, version thay đổi hoặc nguồn tải bất thường.

### 6.2. Không dùng latest trong build phát hành

Dependency kiểu latest có thể thay đổi giữa hai lần chạy. Một package mới có thể được phát hành mà project không thay đổi source. Build phát hành nên dùng exact version hoặc lockfile đã xác minh.

### 6.3. Checksum và chữ ký

Version pinning xác định tên và version package, nhưng checksum xác nhận nội dung package thực tế. Nếu registry trả về nội dung khác cho cùng tọa độ package, checksum sẽ phát hiện sự khác biệt.

Chữ ký package hoặc provenance attestation có thể bổ sung bằng chứng về nguồn phát hành. Cần dùng cơ chế xác minh được hỗ trợ bởi hệ sinh thái package, không tự thiết kế thuật toán kiểm tra.

## 7. Hermetic build

Hermetic build là build chỉ sử dụng những đầu vào đã khai báo và kiểm soát. Nó không âm thầm lấy dữ liệu từ môi trường bên ngoài như package chưa khóa, file ngoài workspace, network resource thay đổi hoặc biến môi trường không được quản lý.

Một build hermetic thường:

- Chạy trong sandbox hoặc môi trường cô lập.
- Chỉ đọc source và dependency đã khai báo.
- Không tải dependency tùy ý trong lúc compile.
- Kiểm soát environment variable.
- Khóa toolchain và platform.
- Ghi output vào thư mục xác định.
- Không phụ thuộc trạng thái máy developer.

Ví dụ pipeline:

~~~text
declared inputs
    |
    v
isolated build environment
    |
    v
DSL compiler and generators
    |
    v
declared outputs
~~~

Hermetic không nhất thiết có nghĩa không bao giờ dùng network. Dependency có thể được tải trước vào cache có checksum hoặc được cung cấp qua artifact store đã kiểm soát. Điểm quan trọng là build không tự ý lấy đầu vào không khai báo trong lúc thực thi.

### 7.1. Network access

Network access trong build có thể tạo kết quả thay đổi theo thời gian:

- Download schema từ URL trỏ tới nội dung mới.
- Lấy package không khóa version.
- Gọi API lấy dữ liệu mẫu.
- Truy cập service tạo code hoặc metadata.

Nên tải và khóa dữ liệu cần thiết trước build, lưu checksum và sử dụng snapshot có version. Nếu build cần network, endpoint và response liên quan phải được xem là input có thể ảnh hưởng output.

### 7.2. Build sandbox

Sandbox giới hạn file system, process, network và quyền truy cập. Nó giúp phát hiện build script đọc file ngoài khai báo hoặc phụ thuộc vào trạng thái local.

Sandbox cũng giảm rủi ro từ dependency hoặc plugin độc hại. Quyền của build process nên tối thiểu, đặc biệt trong CI xử lý pull request từ nguồn không tin cậy.

## 8. Môi trường build được kiểm soát

Ngay cả khi source và dependency giống nhau, môi trường có thể làm output khác:

- Hệ điều hành và filesystem.
- Kiến trúc CPU.
- JDK hoặc native toolchain.
- Locale và timezone.
- Character encoding.
- Line ending.
- Umask và file permission.
- Environment variable.
- Path separator và thứ tự file.

Một build environment manifest có thể ghi:

~~~yaml
environment:
  osImage: linux-builder-2026.11
  architecture: amd64
  jdk: 21.0.5
  locale: en_US.UTF-8
  timezone: UTC
  fileEncoding: UTF-8
~~~

Không phải mọi thuộc tính đều cần pin cho mọi project. Chỉ cần xác định những thuộc tính có ảnh hưởng đến output hoặc hành vi.

### 8.1. Locale và timezone

Nếu compiler hoặc generator sắp xếp tên theo locale, format ngày hoặc ghi timestamp local, output có thể khác giữa máy. Dùng locale và timezone cố định hoặc định dạng độc lập môi trường.

### 8.2. Encoding và line ending

Source có thể dùng UTF-8 nhưng máy khác đọc theo code page khác. Line ending LF và CRLF cũng có thể tạo diff byte. Nên quy định encoding, line ending và cách xử lý Unicode trong repository.

### 8.3. Đường dẫn tuyệt đối

Compiler có thể ghi source path tuyệt đối vào debug metadata hoặc generated file. Build trên hai máy sẽ khác nhau vì đường dẫn khác. Dùng relative path hoặc prefix mapping nếu toolchain hỗ trợ.

## 9. Deterministic compilation

Deterministic compilation là khả năng compiler tạo output ổn định từ cùng source, cấu hình và toolchain.

Các nguồn không xác định thường gặp:

- Duyệt collection không có thứ tự.
- Parallel task ghi output theo thứ tự hoàn thành.
- Timestamp được thêm vào artifact.
- Random ID hoặc UUID.
- Absolute path của máy.
- Hash map iteration order không được cam kết.
- Locale-dependent sorting.
- Generated source chứa thông tin môi trường.

### 9.1. Sắp xếp đầu vào ổn định

Nếu compiler duyệt file theo thứ tự filesystem, hai hệ điều hành có thể tạo output khác. Hãy sắp xếp source path theo quy tắc canonical trước khi xử lý nếu thứ tự không có ý nghĩa ngữ nghĩa.

Nếu thứ tự module hoặc rule có ý nghĩa, phải dùng thứ tự được khai báo trong DSL hoặc manifest thay vì sắp xếp tùy tiện.

### 9.2. Parallel build

Build song song không nhất thiết không xác định. Nó có thể deterministic nếu mỗi task ghi output riêng và bước tổng hợp dùng thứ tự ổn định. Nếu nhiều task cùng ghi một file hoặc kết quả phụ thuộc thứ tự hoàn thành, cần thiết kế lại dependency và output ownership.

### 9.3. Timestamp

Một số archive hoặc package ghi thời điểm tạo. Có thể dùng timestamp chuẩn hóa như source epoch hoặc bỏ timestamp nếu format cho phép. Nếu timestamp là thông tin nghiệp vụ cần thiết, phải xem nó là input rõ ràng thay vì lấy giờ hiện tại ngầm định.

### 9.4. Randomness

Nếu code generation dùng random identifier, cần inject seed cố định hoặc dùng ID được tạo từ nội dung ổn định khi phù hợp. Không nên dùng seed cố định cho randomness có mục đích bảo mật; build determinism và cryptographic randomness là hai yêu cầu khác nhau.

## 10. Tái lập các bước xử lý DSL

Một DSL toolchain có thể gồm nhiều giai đoạn:

~~~mermaid
flowchart TD
    A["DSL source and schema"] --> B["Parse"]
    B --> C["Semantic analysis"]
    C --> D["IR generation"]
    D --> E["Optimization"]
    E --> F["Code generation"]
    F --> G["Packaging"]
    G --> H["Artifact verification"]
~~~

Mỗi giai đoạn cần có đầu vào và đầu ra xác định:

- Parser nhận source và grammar version.
- Semantic analysis nhận AST, symbol index và dependency metadata.
- IR generation nhận typed AST và target version.
- Optimizer nhận IR và optimization options.
- Code generator nhận IR và target runtime ABI.
- Packaging nhận generated files và package metadata.

Nếu một bước đọc thêm file hoặc gọi service không được khai báo, toàn pipeline có thể không tái lập.

### 10.1. AST và IR

Nếu AST hoặc IR được lưu làm cache, format của nó cần có version. Cache được tạo bởi compiler mới không nên được nạp bởi compiler cũ nếu schema hoặc semantics không tương thích.

Một cache key có thể gồm:

- Source content hash.
- Grammar version.
- Compiler version.
- Language version.
- Dependency symbol hash.
- Compiler options.

### 10.2. Optimization flags

Optimization level có thể làm thay đổi bytecode hoặc generated code. Manifest nên ghi rõ optimization flags và target platform. Nếu hai build dùng mức tối ưu khác nhau, không thể giả định output giống nhau chỉ vì source giống nhau.

### 10.3. Generated source và formatter

Formatter version có thể thay đổi whitespace, line wrapping hoặc thứ tự import. Nếu generated source được commit hoặc package, formatter version là một đầu vào build cần khóa.

## 11. Build cache và cache correctness

Build cache lưu output của một bước để tái sử dụng khi các đầu vào không thay đổi. Cache có thể tăng tốc đáng kể nhưng chỉ đúng khi cache key bao gồm mọi yếu tố ảnh hưởng output.

Ví dụ cache key:

~~~text
key = hash(
    sourceContent,
    compilerVersion,
    grammarVersion,
    dependencyLock,
    compilerOptions,
    targetPlatform
)
~~~

Nếu bỏ compilerOptions khỏi key, build có thể trả output được tạo với flag khác. Nếu bỏ dependency lock hash, thay đổi API của thư viện có thể không kích hoạt compile lại.

### 11.1. Cache local và remote

- Local cache giúp tăng tốc trên cùng máy.
- Remote cache chia sẻ kết quả giữa developer và CI.
- Shared cache cần xác minh input key và output integrity.
- Cache của build không tin cậy cần được cách ly hoặc xác minh trước khi dùng.

### 11.2. Cache invalidation

Khi compiler, schema, dependency hoặc build configuration thay đổi, cache liên quan phải bị vô hiệu hóa. Cache key có version là cách quan trọng để tránh dùng artifact cũ.

### 11.3. Cache không thay thế provenance

Cache hit chỉ chứng minh có output cho một key. Release vẫn cần ghi nhận artifact được tạo từ input nào, cache result có được xác minh hay không và output hash là gì.

## 12. Artifact identity và checksum

Sau build, mỗi artifact có thể được định danh bằng cryptographic hash:

~~~text
artifact: pricing-rules.bundle
algorithm: SHA-256
digest: 8f...c2
~~~

Hash giúp:

- Phát hiện artifact bị thay đổi.
- So sánh kết quả giữa hai lần build.
- Xác minh artifact được tải xuống đúng.
- Liên kết artifact với release manifest.
- Kiểm tra image hoặc package trước khi triển khai.

Hash không tự chứng minh source hoặc compiler là đáng tin cậy. Nó chỉ xác nhận nội dung khớp với digest đã biết. Muốn xác minh nguồn gốc cần provenance hoặc chữ ký từ pipeline tin cậy.

## 13. Build provenance và attestation

Build provenance mô tả artifact được tạo như thế nào. Nó có thể chứa:

- Source repository và revision.
- Build system và workflow identity.
- Compiler, runtime và plugin version.
- Dependency lockfile hash.
- Builder image digest.
- Build parameters.
- Artifact name và digest.
- Thời điểm build và danh tính pipeline.

Ví dụ:

~~~yaml
provenance:
  sourceRevision: 7f31c2a
  compilerVersion: 4.2.1
  runtimeAbi: 2
  languageVersion: 3
  dependencyLockHash: sha256:...
  builderImage: sha256:...
  artifact:
    path: dist/pricing-rules.bundle
    sha256: ...
~~~

Attestation là bằng chứng được ký hoặc xác thực về provenance hay một thuộc tính của artifact. Consumer có thể kiểm tra attestation trước khi triển khai.

### 13.1. Ai tạo provenance?

Provenance nên được tạo bởi build service hoặc pipeline có identity đáng tin cậy. Nếu source tự khai báo compiler version trong file rồi tự tạo attestation mà không có xác minh độc lập, thông tin đó không đủ để chứng minh build thực tế đã dùng compiler ấy.

### 13.2. Artifact và source mapping

Nếu compiler sinh bytecode hoặc code, source map có thể liên kết artifact với DSL source. Cần lưu source revision và mapping version để debugger hoặc incident response truy nguyên đúng nội dung.

## 14. Tái lập container image

Container image có thể đóng gói runtime, dependency hệ thống và application artifact. Để tái lập image:

- Pin base image bằng digest.
- Khóa package version.
- Kiểm soát package repository.
- Không tải dependency không khóa trong build stage.
- Chuẩn hóa file metadata nếu cần bit-for-bit output.
- Ghi build arguments có ảnh hưởng.
- Tạo SBOM và image digest.

Ví dụ:

~~~dockerfile
FROM eclipse-temurin:21-jre@sha256:<approved-digest>
WORKDIR /app
COPY dist/pricing-rules.bundle /app/
ENTRYPOINT ["java", "-jar", "/app/pricing-runtime.jar"]
~~~

Digest ở ví dụ là placeholder; project cần dùng digest thực tế đã xác minh. Tag image có thể trỏ tới nội dung mới theo thời gian, còn digest định danh nội dung cụ thể.

Container giúp đóng gói môi trường nhưng không tự bảo đảm build tái lập. Nếu image build tải package mới nhất hoặc dùng timestamp hiện tại, kết quả vẫn có thể khác.

## 15. Tái lập deployment

Deployment reproducibility là khả năng triển khai lại cùng artifact và cùng cấu hình có chủ đích vào một môi trường tương đương.

Một deployment gồm:

- Artifact hoặc container image.
- Runtime platform.
- Deployment manifest.
- Configuration.
- Secret reference.
- Network và identity policy.
- Schema version.
- Resource limits.
- Rollout strategy.

Manifest có thể mô tả:

~~~yaml
application: pricing-service
artifact:
  image: registry.example.com/pricing@sha256:...
runtime:
  dslAbi: 2
configuration:
  schemaVersion: 3
secrets:
  - reference: secret://pricing/database
resources:
  cpu: "1"
  memory: 1Gi
~~~

Deployment cần tham chiếu artifact bất biến bằng digest hoặc version đã khóa, không chỉ dùng tag mutable như latest.

### 15.1. Cấu hình và secret

Cùng artifact có thể hoạt động khác nhau nếu configuration khác. Vì vậy, cần ghi version hoặc hash của cấu hình không nhạy cảm, đồng thời quản lý secret bằng secret manager.

Không nên ghi giá trị secret vào provenance hoặc log. Có thể ghi secret reference, version hoặc metadata đủ để xác định phiên bản secret mà không làm lộ nội dung.

### 15.2. Infrastructure as Code

Hạ tầng có thể được mô tả bằng configuration hoặc DSL riêng. Tính tái lập cần kiểm soát version của provider, module, plugin và state schema.

Infrastructure plan cần được review trước khi apply. Một lệnh deploy tái lập không có nghĩa mọi tác động môi trường đều có thể đảo ngược; thay đổi database, network hoặc resource bên ngoài có thể có side effect.

## 16. Cấu hình môi trường và tách biệt artifact

Một nguyên tắc hữu ích là build artifact một lần rồi promote cùng artifact qua các môi trường:

~~~text
Build once
   |
   v
Verify artifact
   |
   v
Deploy to staging
   |
   v
Approve release
   |
   v
Deploy same artifact to production
~~~

Nếu build lại riêng cho production, output có thể khác staging dù source revision giống nhau. Dùng cùng digest giúp bảo đảm artifact đã kiểm thử chính là artifact được phát hành.

Configuration theo môi trường vẫn có thể khác, nhưng schema, nguồn cấu hình, version và policy cần được quản lý. Cần tách biến môi trường hợp lệ khỏi những biến có thể làm thay đổi artifact build.

## 17. Tái lập runtime semantics

Cùng artifact chưa chắc tạo hành vi giống nhau nếu runtime environment khác:

- Runtime library hoặc ABI khác.
- Timezone hoặc locale khác.
- Clock hoặc random source khác.
- Database state khác.
- External API trả dữ liệu khác.
- Feature flag khác.
- Policy hoặc schema registry khác.

Vì vậy, cần phân biệt build reproducibility với execution reproducibility. Build tái lập tạo cùng artifact; execution tái lập cần kiểm soát thêm state và các dependency lúc chạy.

### 17.1. Thời gian và randomness

Workflow hoặc query có thể gọi now(), currentDate() hoặc random(). Để test và replay có thể tái lập, runtime có thể inject clock và random provider.

Trong production, clock cần đáng tin cậy và random dùng cho bảo mật không được thay bằng seed cố định chỉ để làm output dễ lặp lại. Tách clock của nghiệp vụ, clock của test và cryptographic randomness.

### 17.2. External services

Một workflow gọi API bên ngoài có thể nhận response khác ở hai lần chạy. Muốn replay có thể tái lập, cần ghi event hoặc response đã được phép lưu, dùng stub/fixture trong test, hoặc định nghĩa contract rõ về external state.

Không nên khẳng định execution hoàn toàn tái lập khi kết quả phụ thuộc dịch vụ bên ngoài hoặc dữ liệu thay đổi mà không có snapshot.

### 17.3. Database state

Query trên cùng source code nhưng database state khác sẽ trả kết quả khác. Nếu cần test tái lập, dùng fixture hoặc snapshot có version. Với production workflow, ghi correlation ID và event history có thể hỗ trợ điều tra mà không cần giả định dữ liệu vẫn nguyên trạng.

## 18. Workflow replay và event history

Workflow engine có thể lưu event history để replay quyết định và trạng thái. Một workflow deterministic cần cùng event history và cùng semantics để tái tạo state.

Ví dụ event log:

~~~text
OrderReceived(order-100)
InventoryReserved(reservation-8)
PaymentAuthorized(payment-55)
OrderConfirmed(order-100)
~~~

Replay có thể tái dựng trạng thái workflow từ chuỗi event. Tuy nhiên, code workflow mới có thể tạo quyết định khác khi replay history cũ. Vì vậy, engine cần version workflow definition hoặc replay compatibility mechanism.

### 18.1. Workflow versioning

Khi logic workflow thay đổi, instance đang chạy có thể tiếp tục theo version cũ hoặc migrate sang version mới theo chính sách. Không nên âm thầm chạy history cũ bằng semantics mới nếu điều đó làm thay đổi quyết định đã được ghi nhận.

### 18.2. Deterministic activity boundary

Hoạt động gọi service bên ngoài thường không deterministic. Workflow engine có thể ghi kết quả activity vào history và dùng lại kết quả đó khi replay thay vì gọi service lần nữa.

Side effect cần idempotency và correlation để replay không tạo thao tác lặp.

## 19. Tái lập documentation và generated artifacts

Documentation generator, formatter, schema generator và code generator cũng là một phần của toolchain.

Để tài liệu tái lập:

- Pin template và renderer version.
- Sắp xếp symbol và module theo thứ tự ổn định.
- Chuẩn hóa anchor.
- Không chèn timestamp hoặc absolute path nếu không cần.
- Khóa locale và encoding.
- Kiểm soát plugin và extension.

Nếu cùng source tạo ra documentation diff lớn chỉ vì thứ tự symbol thay đổi, review sẽ khó nhận ra thay đổi thực sự. Deterministic output giúp diff phản ánh nội dung có ý nghĩa.

Generated schema hoặc migration script cũng cần được version hóa và có checksum nếu dùng trong release.

## 20. Schema migration và dữ liệu

Deployment có thể đi kèm schema migration. Muốn tái lập quá trình nâng cấp, cần lưu:

- Schema version trước và sau.
- Migration script và checksum.
- Tool version dùng để chạy migration.
- Thứ tự migration.
- Trạng thái đã áp dụng.
- Precondition và postcondition.

Migration nên được thiết kế idempotent khi có thể, hoặc có cơ chế ghi nhận chính xác đã chạy hay chưa. Chạy lại migration có side effect mà không kiểm tra trạng thái có thể làm hỏng dữ liệu.

Rollback application không tự động rollback schema. Cần compatibility window để phiên bản ứng dụng cũ và mới có thể cùng hoạt động trong giai đoạn rollout, hoặc có kế hoạch migration ngược được kiểm thử.

## 21. Kiểm tra tính tái lập bằng hash và diff

Một cách kiểm tra bit-for-bit:

1. Build từ checkout sạch với toolchain đã khóa.
2. Tạo checksum của artifact.
3. Build lại trong môi trường độc lập tương đương.
4. So sánh checksum.
5. Nếu khác, so sánh file và metadata để tìm nguồn biến động.

Ví dụ:

~~~text
build A -> SHA256: abc...
build B -> SHA256: abc...
result: byte-identical
~~~

Nếu hash khác, chưa thể kết luận semantics khác. Có thể khác timestamp hoặc metadata archive. Cần phân tích diff và xác định mức cam kết.

### 21.1. Normalize trước khi so sánh

Với format không canonical, có thể normalize:

- Sắp xếp key.
- Loại bỏ timestamp không có ý nghĩa.
- Chuẩn hóa line ending.
- Chuẩn hóa path.
- Parse và so sánh AST hoặc structured output.

Normalization phải được định nghĩa rõ và không được xóa những khác biệt có ý nghĩa ngữ nghĩa.

### 21.2. Independent rebuild

Để tăng độ tin cậy, có thể build trên hai worker hoặc môi trường độc lập. Nếu cả hai tạo cùng digest, bằng chứng mạnh hơn so với việc build hai lần trên cùng workspace có thể chia sẻ cache hoặc trạng thái.

## 22. CI/CD cho quy trình tái lập

Một pipeline CI/CD có thể gồm:

1. Checkout source revision sạch.
2. Xác minh toolchain manifest.
3. Resolve dependency bằng lockfile.
4. Khởi tạo builder image theo digest.
5. Chạy parser, compiler và generator.
6. Chạy test và conformance checks.
7. Tạo package và checksum.
8. Tạo provenance và SBOM.
9. Thực hiện independent rebuild nếu policy yêu cầu.
10. Đẩy artifact vào registry bất biến.
11. Deploy đúng digest lên staging.
12. Promote cùng digest sang production sau phê duyệt.

CI nên fail sớm nếu version hoặc checksum không khớp. Không nên tự tải compiler mới hoặc tự sửa lockfile trong build phát hành.

### 22.1. Build và deploy tách biệt

Build tạo artifact; deploy đưa artifact vào môi trường. Tách hai bước giúp:

- Kiểm thử artifact trước khi phát hành.
- Promote cùng digest qua môi trường.
- Audit ai đã build và ai đã deploy.
- Rollback bằng artifact đã biết.

Deploy có thể dùng config khác theo môi trường, nhưng config cần version và schema validation.

### 22.2. Release manifest

Release manifest có thể liên kết:

- Source revision.
- Artifact digest.
- Toolchain version.
- Dependency lock hash.
- Schema version.
- Deployment config version.
- SBOM reference.
- Provenance attestation.

Release manifest giúp xác định một deployment đang chạy chính xác thành phần nào.

## 23. Rollback và phục hồi

Tái lập giúp phục hồi release đã biết, nhưng rollback cần được thiết kế cùng deployment và data migration.

Một quy trình rollback có thể:

1. Xác định release và artifact digest ổn định trước đó.
2. Xác minh runtime tương thích với artifact.
3. Xác định schema và data migration đã diễn ra.
4. Kiểm tra configuration và secret version.
5. Deploy lại artifact cũ.
6. Xác minh health và behavior.
7. Ghi audit event và trạng thái rollback.

Không phải thay đổi nào cũng rollback an toàn. Một workflow đã gửi email hoặc charge payment không thể được hoàn tác chỉ bằng cách triển khai image cũ. Side effect cần compensation hoặc quy trình nghiệp vụ riêng.

## 24. Supply-chain security và SBOM

Tính tái lập hỗ trợ bảo mật chuỗi cung ứng vì nhóm có thể xác định dependency và nguồn tạo artifact.

Các thực hành:

- Pin package version và checksum.
- Dùng registry được phê duyệt.
- Xác minh chữ ký package khi có.
- Tạo SBOM cho release.
- Quét vulnerability theo policy.
- Giới hạn quyền build plugin.
- Cô lập build từ pull request không tin cậy.
- Lưu provenance và artifact digest.
- Không để credential xuất hiện trong log hoặc image layer.

SBOM liệt kê các thành phần phần mềm trong artifact. Lockfile mô tả dependency resolution của project; SBOM mô tả thành phần thực tế được đóng gói. Hai loại dữ liệu bổ sung cho nhau.

Reproducibility không đồng nghĩa an toàn. Một build có thể tái lập hoàn hảo nhưng vẫn chứa dependency độc hại. Cần kết hợp provenance với kiểm tra nguồn, chữ ký và vulnerability.

## 25. Quan sát và chẩn đoán sai khác giữa các lần build

Khi output khác nhau, cần có đủ dữ liệu để xác định nguyên nhân:

- Source revision và trạng thái working tree.
- Compiler/runtime/build plugin version.
- Lockfile hash.
- Builder image digest.
- Build flags và environment.
- Artifact hash.
- Generated file diff.
- Build log và provenance.

Các loại sai khác thường gặp:

| Dấu hiệu | Nguyên nhân có thể |
|---|---|
| Chỉ khác timestamp | Archive hoặc generated metadata ghi giờ hiện tại |
| Khác thứ tự file | Filesystem traversal hoặc collection order |
| Khác path | Absolute path hoặc workspace root khác |
| Khác bytecode | Compiler, optimization flag hoặc target ABI |
| Khác documentation | Renderer, template, locale hoặc symbol order |
| Khác dependency | Lockfile không được dùng hoặc registry thay đổi |
| Khác runtime behavior | Runtime, config, clock, data hoặc external service khác |

Không nên chỉ so sánh file cuối cùng. Cần so sánh provenance và intermediate artifact để tìm giai đoạn tạo ra sai khác.

## 26. Kiểm thử tính tái lập

Có thể tổ chức kiểm thử theo các lớp:

### 26.1. Clean build test

Build từ checkout sạch, không dựa vào output cũ hoặc trạng thái local. Xác nhận build không cần file ngoài khai báo.

### 26.2. Double build test

Build hai lần với cùng input và so sánh checksum hoặc normalized output.

### 26.3. Cross-worker test

Build trên worker độc lập hoặc container khác có cùng image digest để phát hiện phụ thuộc vào cache và trạng thái máy.

### 26.4. Dependency lock test

Xác nhận build không resolve version mới ngoài lockfile và checksum được kiểm tra.

### 26.5. Environment variation test

Thay đổi locale, timezone, working directory hoặc thứ tự file để xác định những yếu tố nào đang ảnh hưởng output ngoài dự kiến.

### 26.6. Cache correctness test

Thay từng input quan trọng như compiler flag, schema hoặc dependency và xác nhận cache bị invalidated đúng.

### 26.7. Deployment promotion test

Xác nhận staging và production dùng cùng artifact digest, đồng thời config và secret reference được ghi nhận riêng.

### 26.8. Replay test

Với workflow có event history, replay bằng workflow version được hỗ trợ và xác nhận state transition không tạo side effect lặp.

### 26.9. Migration test

Chạy migration trên fixture có version xác định, kiểm tra precondition, postcondition và khả năng phục hồi.

## 27. Những lỗi thiết kế thường gặp

### Chỉ khóa source nhưng không khóa toolchain

Cùng source được compile bằng compiler khác và tạo output khác. Ghi và xác minh compiler, runtime, generator và build plugin.

### Dùng dependency version range không có lockfile

Dependency bắc cầu thay đổi theo thời gian. Commit lockfile và xác minh checksum.

### Build phụ thuộc network không kiểm soát

Schema, package hoặc dữ liệu tải về có thể thay đổi. Đưa chúng thành input có version và checksum.

### Đưa timestamp hoặc path máy vào artifact

Hai build khác môi trường tạo package khác nhau. Chuẩn hóa metadata và dùng relative path khi phù hợp.

### Parallel build ghi chung output

Thứ tự hoàn thành làm nội dung thay đổi. Tách output theo task và hợp nhất theo thứ tự xác định.

### Cache key thiếu đầu vào

Cache trả kết quả được tạo từ compiler flag hoặc dependency khác. Đưa mọi input ảnh hưởng output vào key.

### Dùng tag container có thể thay đổi

Image tag có thể trỏ tới nội dung mới. Dùng digest đã xác minh cho build và deployment quan trọng.

### Build lại ở production

Artifact production có thể khác artifact đã kiểm thử ở staging. Build một lần, xác minh và promote cùng digest.

### Chỉ lưu artifact mà không lưu provenance

Không biết artifact đến từ revision hoặc toolchain nào. Lưu manifest, checksum và attestation.

### Nhầm reproducible build với reproducible execution

Cùng package nhưng dữ liệu hoặc external service khác tạo hành vi khác. Kiểm soát runtime context và ghi nhận event/state khi cần replay.

### Rollback application mà quên schema

Runtime cũ có thể không đọc được dữ liệu đã migrate. Thiết kế compatibility window và rollback data riêng.

## 28. Quy trình xây dựng tính tái lập cho DSL

Một quy trình triển khai có thể thực hiện theo thứ tự:

1. **Xác định mức cam kết.** Bit-for-bit, functional, environment hay deployment reproducibility?
2. **Lập danh sách đầu vào.** Source, schema, grammar, compiler, dependency, config và platform.
3. **Pin toolchain.** Dùng manifest có thể thực thi và lockfile.
4. **Kiểm soát môi trường.** Khóa image, JDK, locale, timezone, encoding và biến môi trường liên quan.
5. **Làm deterministic compiler.** Ổn định thứ tự, loại bỏ timestamp ngầm và kiểm soát random.
6. **Thiết kế cache key đầy đủ.** Bao gồm mọi input có thể làm thay đổi output.
7. **Tạo artifact bất biến.** Gắn checksum và metadata version.
8. **Ghi provenance và SBOM.** Liên kết artifact với source và toolchain.
9. **Tách build khỏi deploy.** Promote cùng digest qua các môi trường.
10. **Version hóa config và migration.** Giữ compatibility giữa application và schema.
11. **Kiểm thử độc lập.** Double build, cross-worker, cache và deployment promotion.
12. **Lập kế hoạch rollback.** Giữ artifact, manifest và quy trình phục hồi dữ liệu.

Nên bắt đầu bằng việc khóa toolchain và dependency, sau đó kiểm tra double build để tìm nguồn không xác định. Khi build đã ổn định, có thể mở rộng sang provenance, container digest, deployment manifest và workflow replay.

## 29. Ví dụ end-to-end: build và triển khai DSL bundle

Giả sử project chứa các rule pricing và cần triển khai cùng một bundle lên staging rồi production.

Toolchain manifest:

~~~yaml
languageVersion: 3
compilerVersion: 4.2.1
runtimeAbi: 2
formatterVersion: 1.8.3
~~~

Quy trình:

1. CI checkout commit 7f31c2a trong working tree sạch.
2. Xác minh compiler 4.2.1 và runtime ABI 2.
3. Resolve dependency bằng lockfile đã commit.
4. Build trong builder image được pin bằng digest.
5. Compile DSL thành pricing-rules.bundle.
6. Chạy semantic test và integration test trên bundle.
7. Tạo SHA-256, provenance và SBOM.
8. Chạy independent rebuild và so sánh digest theo policy.
9. Đẩy bundle vào artifact registry bất biến.
10. Deploy đúng digest lên staging.
11. Chạy smoke test và phê duyệt release.
12. Promote cùng digest sang production với configuration version đã xác định.

Release manifest:

~~~yaml
release:
  sourceRevision: 7f31c2a
  compilerVersion: 4.2.1
  runtimeAbi: 2
  dependencyLockHash: sha256:...
  artifact:
    name: pricing-rules.bundle
    digest: sha256:...
  deployment:
    configVersion: pricing-prod-18
~~~

Nếu có sự cố, nhóm có thể xác định bundle đang chạy, source revision, compiler và configuration đã dùng. Rollback có thể triển khai lại digest trước đó sau khi xác nhận runtime và schema tương thích.

Ví dụ này thể hiện tính tái lập xuyên suốt từ source tới deployment, đồng thời giữ riêng artifact identity và cấu hình môi trường.

## 30. Kết luận

Tính tái lập trong xây dựng và triển khai DSL là khả năng tái tạo hoặc xác minh kết quả từ source, toolchain, dependency, môi trường và cấu hình đã được kiểm soát. Nó giúp build nhất quán, debug đáng tin cậy, cache chính xác, release có provenance và deployment có thể phục hồi.

Một quy trình vững chắc cần pin compiler và dependency, dùng lockfile, kiểm soát môi trường, làm deterministic các bước compile/generate, tạo artifact bất biến và lưu checksum cùng provenance. Với deployment, cần promote cùng artifact digest qua các môi trường và version hóa configuration, schema cùng migration. Với workflow runtime, cần kiểm soát clock, external input và event history nếu muốn replay hành vi.

Tính tái lập không tự động bảo đảm artifact an toàn hoặc mọi lần thực thi cho cùng kết quả. Nó cần đi cùng kiểm tra supply chain, policy, test, observability và định nghĩa rõ mức cam kết. Khi những yếu tố đó được quản lý, nhóm có thể giải thích artifact được tạo ra như thế nào, tái tạo release đã biết và triển khai DSL một cách nhất quán.
