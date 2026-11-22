# Quản lý phiên bản công cụ

## 1. Quản lý phiên bản công cụ là gì?

Quản lý phiên bản công cụ (tool version management) là quá trình xác định, ghi nhận, khóa, cập nhật và kiểm soát các phiên bản phần mềm tham gia vào quá trình phát triển, phân tích, biên dịch, thực thi và bảo trì một DSL (Domain-Specific Language).

Một dự án DSL thường phụ thuộc vào nhiều thành phần:

- Compiler hoặc interpreter của DSL.
- Runtime và thư viện chuẩn.
- Grammar, parser generator và lexer generator.
- Framework hoặc SDK dùng để nhúng DSL vào ứng dụng.
- Plugin của IDE và language server.
- Formatter, linter, debugger và documentation generator.
- Build tool, plugin build và dependency bên ngoài.
- Schema, code generator và công cụ migration.

Ví dụ, một project có thể dùng compiler DSL phiên bản 3.2, runtime 3.2, language server 2.8, grammar package 1.4 và plugin build 5.1. Nếu các thành phần này được nâng cấp độc lập mà không có quy tắc tương thích, cùng một source có thể cho kết quả khác nhau giữa máy developer và CI.

Mục tiêu của quản lý phiên bản là bảo đảm mọi thành phần dùng đúng tổ hợp đã được hỗ trợ, có thể tái tạo build, nâng cấp có kiểm soát và quay lại trạng thái ổn định khi có sự cố.

## 2. Vì sao toolchain DSL cần quản lý phiên bản?

Toolchain DSL thường có nhiều thành phần liên kết với nhau. Compiler cần grammar và runtime tương thích; plugin IDE cần language server tương thích; generated code cần API runtime phù hợp; build plugin cần hiểu định dạng artifact mà compiler tạo ra.

Nếu không quản lý phiên bản, có thể gặp:

1. Source biên dịch được trên máy này nhưng lỗi trên máy khác.
2. IDE hiển thị diagnostic hoặc completion khác với CI.
3. Compiler mới tạo bytecode mà runtime cũ không chạy được.
4. Plugin build gọi API đã bị xóa.
5. Formatter thay đổi toàn bộ output sau một lần nâng cấp.
6. Cache AST hoặc IR cũ không còn đọc được.
7. Dependency gián tiếp kéo vào phiên bản thư viện không tương thích.
8. Khó xác định phiên bản công cụ đã tạo một artifact trong môi trường production.

Quản lý phiên bản giúp dự án trả lời được các câu hỏi: đang dùng công cụ nào, phiên bản nào, ai nâng cấp, thay đổi ảnh hưởng gì, có thể tái tạo kết quả cũ không và cần làm gì khi rollback.

## 3. Các loại phiên bản trong hệ sinh thái DSL

Không nên dùng một số phiên bản duy nhất cho mọi thành phần. Các lớp có vòng đời và hợp đồng riêng:

| Thành phần | Phiên bản mô tả điều gì? |
|---|---|
| Language version | Cú pháp và ngữ nghĩa của DSL |
| Compiler version | Phiên bản công cụ phân tích và sinh artifact |
| Runtime version | API và môi trường thực thi |
| Runtime ABI version | Hợp đồng liên kết giữa artifact và runtime |
| Artifact format version | Cấu trúc file AST, IR hoặc bytecode đã lưu |
| Grammar package version | Phiên bản grammar dùng cho parser hoặc editor |
| Language server version | Phiên bản dịch vụ ngôn ngữ cho IDE |
| IDE extension version | Phiên bản plugin tích hợp editor |
| Build plugin version | Phiên bản plugin tích hợp compiler vào build |
| Dependency version | Phiên bản thư viện mà toolchain sử dụng |
| Documentation template version | Phiên bản layout và renderer tài liệu |

Ví dụ, compiler 4.0 có thể tiếp tục hỗ trợ language version 2 và 3, nhưng chỉ tạo artifact format 3. Runtime 5.0 có thể chạy artifact format 2 và 3. IDE extension 3.1 có thể dùng language server 2.9.

Việc tách version giúp nâng cấp một thành phần mà không bắt buộc mọi thành phần khác phải tăng số cùng lúc. Tuy nhiên, quan hệ tương thích giữa chúng phải được công bố.

## 4. Semantic Versioning

Semantic Versioning (SemVer) thường biểu diễn phiên bản theo dạng MAJOR.MINOR.PATCH:

~~~text
4.2.1
| | |
| | +-- PATCH: sửa lỗi tương thích
| +---- MINOR: thêm chức năng tương thích ngược
+------ MAJOR: thay đổi không tương thích
~~~

- **MAJOR:** thay đổi public contract hoặc hành vi mà người dùng phụ thuộc.
- **MINOR:** thêm tính năng tương thích ngược.
- **PATCH:** sửa lỗi mà không chủ ý phá vỡ hợp đồng công khai.

Ví dụ:

- Compiler 4.2.0 thêm một toán tử mới mà không đổi ý nghĩa chương trình cũ.
- Compiler 4.2.1 sửa lỗi hiển thị source location.
- Compiler 5.0.0 loại bỏ cú pháp đã deprecated hoặc đổi định dạng artifact.

SemVer chỉ hữu ích khi dự án định nghĩa rõ public contract. Một thay đổi không làm source lỗi compile vẫn có thể là breaking change nếu nó làm đổi kết quả runtime. Ngược lại, thay đổi cấu trúc nội bộ không được công khai có thể không cần tăng MAJOR.

### 4.1. Pre-release và build metadata

Phiên bản có thể có hậu tố pre-release:

~~~text
5.0.0-alpha.1
5.0.0-beta.2
5.0.0-rc.1
~~~

Pre-release dùng để thử nghiệm trước khi phát hành ổn định. Build metadata có thể ghi thông tin build:

~~~text
5.0.0+build.184
~~~

Theo SemVer, build metadata không quyết định thứ tự precedence của phiên bản. Không nên dùng build metadata thay cho version của language, artifact hoặc runtime ABI.

### 4.2. Version range

Dependency declaration có thể cho phép một khoảng phiên bản:

~~~text
compiler = ">=4.2.0 <5.0.0"
~~~

Range giúp nhận bản vá tương thích, nhưng nếu không có lockfile thì hai lần resolve có thể chọn hai phiên bản khác nhau. Với build cần tái lập, nên kết hợp range với lockfile hoặc pin chính xác phiên bản trong release pipeline.

## 5. Khóa phiên bản toolchain

Pinning là chỉ định chính xác phiên bản công cụ mà dự án sử dụng. Ví dụ:

~~~yaml
toolchain:
  dslCompiler: 4.2.1
  dslRuntime: 4.2.1
  languageServer: 2.9.0
  formatter: 1.8.3
  buildPlugin: 5.1.0
~~~

Khi mọi developer và CI dùng cùng manifest, giảm nguy cơ kết quả khác nhau do tự động tải phiên bản mới nhất.

Có thể khóa version theo nhiều cách:

- Version file trong repository.
- Build configuration.
- Package manager manifest.
- Lockfile chứa phiên bản và checksum dependency.
- Container image digest cho môi trường build.
- Toolchain manager riêng của dự án.

Không nên chỉ ghi phiên bản trong README nếu build system không thực sự đọc và kiểm tra giá trị đó. Manifest cần là nguồn cấu hình có thể thực thi.

## 6. Toolchain manifest

Toolchain manifest là file mô tả bộ công cụ và quy tắc tương thích của project. Một manifest minh họa:

~~~yaml
toolchain:
  languageVersion: 3
  compiler:
    version: 4.2.1
    artifactFormat: 3
  runtime:
    version: 5.0.2
    abi: 2
  languageServer:
    version: 2.9.0
  formatter:
    version: 1.8.3

dependencies:
  - name: sales-domain
    version: 4.1.0
  - name: shared-types
    version: 2.3.2
~~~

Manifest có thể chứa:

- Phiên bản language.
- Phiên bản compiler và runtime.
- Artifact format và runtime ABI.
- Build plugin, formatter, linter và documentation tool.
- Dependency trực tiếp.
- Repository hoặc registry nguồn.
- Checksum hoặc signature nếu được hỗ trợ.
- Các ràng buộc phiên bản.

Manifest nên được review cùng source vì nó ảnh hưởng trực tiếp tới cách project được xây dựng. Thay đổi version compiler có thể làm output hoặc diagnostic thay đổi dù DSL source không đổi.

## 7. Lockfile và dependency resolution

Manifest thường khai báo dependency trực tiếp hoặc range. Lockfile ghi lại kết quả resolve đầy đủ, gồm cả dependency bắc cầu.

Ví dụ:

~~~text
Project
  dsl-compiler 4.2.1
    parser-core 2.6.0
    diagnostics-api 1.9.2
  dsl-runtime 5.0.2
    expression-vm 3.4.1
    money-types 2.2.0
~~~

Lockfile có thể lưu:

- Tên package.
- Phiên bản chính xác.
- Nguồn tải.
- Checksum.
- Dependency graph.
- Metadata platform hoặc variant.

Khi lockfile được commit, build có thể tái sử dụng đúng dependency đã resolve. Nếu manifest thay đổi, lockfile cần được cập nhật có chủ đích và review diff.

### 7.1. Dependency trực tiếp và bắc cầu

Dependency trực tiếp được khai báo bởi project. Dependency bắc cầu được kéo vào bởi package khác. Một thư viện parser có thể phụ thuộc vào thư viện collection, logging hoặc serialization mà project không khai báo trực tiếp.

Xung đột có thể xảy ra nếu hai dependency yêu cầu các phiên bản khác nhau của cùng một package. Package manager cần có quy tắc chọn phiên bản, cô lập hoặc từ chối resolve.

### 7.2. Dependency constraints

Một package có thể yêu cầu:

~~~text
runtime >= 5.0.0 and < 6.0.0
~~~

Nếu project khóa runtime 4.9.0, resolver nên báo xung đột thay vì âm thầm chọn phiên bản không đáp ứng hợp đồng.

### 7.3. Repository và registry

Dependency có thể đến từ public registry, private registry, artifact repository hoặc source control. Manifest nên xác định nguồn tin cậy. Tránh cấu hình fallback tùy tiện tới repository không được kiểm soát vì có thể tải nhầm package cùng tên.

## 8. Ma trận tương thích giữa các thành phần

Các thành phần cần có ma trận tương thích được công bố:

| Compiler | Language version | Artifact format | Runtime hỗ trợ |
|---|---|---|---|
| 3.x | DSL 1, 2 | 1, 2 | Runtime 3.x, 4.x |
| 4.x | DSL 2, 3 | 2, 3 | Runtime 4.x, 5.x |
| 5.x | DSL 3, 4 | 3, 4 | Runtime 5.x, 6.x |

Bảng chỉ minh họa cách trình bày. Dự án thực tế cần xác định rõ các tổ hợp được kiểm thử và hỗ trợ.

Ma trận có thể bao gồm:

- Compiler và language version.
- Compiler và runtime ABI.
- Artifact format và runtime.
- Build plugin và compiler API.
- Language server và LSP client capability.
- IDE extension và editor version.
- Formatter và grammar version.
- Documentation generator và schema version.

Không nên chỉ dựa vào số version lớn/nhỏ để suy ra tương thích. Cần kiểm tra theo hợp đồng và ma trận đã xác nhận.

## 9. Tương thích giữa compiler và runtime

Compiler có thể tạo bytecode hoặc generated source dựa trên API runtime. Nếu runtime thay đổi, artifact cũ có thể không còn chạy.

Ví dụ compiler sinh lời gọi:

~~~java
RuntimeRules.evaluate(ruleId, context);
~~~

Runtime mới đổi API thành:

~~~java
RuleEngine.execute(ruleId, context, options);
~~~

Các cách quản lý:

- Giữ wrapper API cũ trong runtime mới.
- Sinh code theo runtime target version.
- Dùng adapter package.
- Chuyển đổi artifact cũ sang format mới.
- Ghi runtime ABI vào metadata của artifact.

Artifact nên mang metadata tối thiểu để runtime biết cách đọc:

~~~yaml
languageVersion: 3
artifactFormat: 3
compilerVersion: 4.2.1
runtimeAbi: 2
~~~

Nếu runtime không hỗ trợ artifact format hoặc ABI, nên từ chối với lỗi rõ ràng. Không nên thử chạy bằng cách bỏ qua instruction hoặc metadata không hiểu.

## 10. Quản lý phiên bản grammar và parser generator

Grammar DSL có thể được duy trì riêng với compiler. Các công cụ như ANTLR, Tree-sitter hoặc parser generator khác có version riêng và có thể thay đổi output hoặc API khi nâng cấp.

Cần theo dõi:

- Grammar source version.
- Parser generator version.
- Generated parser version.
- Token vocabulary hoặc token ID compatibility.
- Runtime library của parser.
- Query/highlight grammar version.

Nếu parser được sinh tự động, cần xác định generated parser có được commit hay tái tạo trong build. Nếu commit generated code, version parser generator vẫn cần được ghi lại để tái lập.

Một thay đổi token ID có thể ảnh hưởng plugin, syntax highlighter hoặc serialized parse tree. Nếu token ID là một phần của public API hoặc artifact, cần version hóa nó.

## 11. Quản lý phiên bản IDE extension và Language Server

IDE extension và language server thường phát hành độc lập với compiler. Extension có thể cần một LSP capability mới hoặc một protocol method mà server cũ chưa hỗ trợ.

Nên xác định:

- Phiên bản editor tối thiểu.
- Phiên bản LSP được hỗ trợ.
- Phiên bản language server.
- Phiên bản grammar và semantic token legend.
- Compiler SDK mà server dùng để phân tích.
- Khả năng tương thích của debug adapter hoặc formatter.

Nếu extension tự tải language server, cần khóa hoặc kiểm tra version của server. Nếu dùng server cài trong project, manifest nên chỉ ra cách tìm đúng binary.

### 11.1. Capability negotiation

LSP client và server có thể hỗ trợ tập capability khác nhau. Khi khởi tạo, hai bên thương lượng tính năng như semantic tokens, workspace folders, diagnostics hoặc completion resolve.

Server không nên giả định client hỗ trợ mọi tính năng của phiên bản giao thức mới nhất. Nó cần đọc capability và cung cấp fallback phù hợp.

### 11.2. Semantic token legend

Semantic token type và modifier là hợp đồng giữa server và client. Khi thêm hoặc đổi loại token, cần kiểm tra theme, extension và client cũ. Nếu thay đổi legend không tương thích, nên có version hoặc fallback thay vì âm thầm gửi index mà client không hiểu.

## 12. Quản lý phiên bản plugin và extension API

Build plugin, IDE plugin và extension runtime có thể phụ thuộc API của framework. Khi framework thay đổi, plugin cũ có thể không còn khởi tạo được.

Một plugin manifest có thể khai báo:

~~~yaml
plugin:
  id: dsl-workbench
  version: 3.1.0
  requires:
    workbenchApi: ">=2.4 <3.0"
    dslCompiler: ">=4.0 <5.0"
~~~

Plugin manager nên kiểm tra constraints trước khi load. Nếu không tương thích, thông báo cần nêu plugin, version hiện tại và khoảng version được yêu cầu.

Không nên dùng reflection hoặc API nội bộ của framework nếu có public extension API. Internal API thường không có cam kết tương thích và có thể đổi giữa các bản minor hoặc patch.

## 13. Quản lý phiên bản framework và workbench

Workbench là môi trường tích hợp các công cụ phát triển DSL: editor, project explorer, parser, validation, debugger, generator, documentation và deployment adapter.

Framework/workbench có thể có:

- Core API.
- Plugin API.
- Project model.
- Workspace metadata format.
- UI extension points.
- Build integration.
- Runtime integration.
- Debug protocol.

Các phần này cần có version policy riêng hoặc một release train được công bố. Khi core API thay đổi, plugin cần được kiểm tra tương thích trước khi cài.

Một workbench có thể dùng plugin catalog để công bố:

| Plugin | Version | Workbench API | Trạng thái |
|---|---|---|---|
| DSL Editor | 3.1.0 | 2.x | Stable |
| Rule Debugger | 2.4.2 | 2.x | Stable |
| Schema Viewer | 1.8.0 | 2.x | Experimental |

Trạng thái Stable hoặc Experimental cần có định nghĩa và chính sách hỗ trợ cụ thể.

## 14. Reproducible builds

Reproducible build là khả năng tạo cùng artifact từ cùng source và cùng bộ đầu vào được kiểm soát. Tool version là một phần quan trọng của đầu vào build.

Các yếu tố cần khóa:

- Compiler và runtime version.
- Build tool và plugin version.
- Dependency graph và checksum.
- JDK hoặc toolchain nền.
- Formatter và code generator.
- Environment variables ảnh hưởng build.
- Locale, timezone và line ending.
- Container image hoặc hệ điều hành nếu cần.

Một build có thể khác nhau dù DSL source không đổi nếu formatter mới đổi output hoặc compiler mới đổi thứ tự sinh file. Vì vậy, manifest và lockfile cần được đưa vào build provenance.

### 14.1. Build provenance

Provenance là thông tin mô tả artifact được tạo từ đâu và bằng công cụ nào. Một manifest artifact có thể ghi:

~~~yaml
artifact:
  name: pricing-rules
  sourceRevision: 7f31c2a
  compilerVersion: 4.2.1
  runtimeAbi: 2
  languageVersion: 3
  dependencyLockHash: sha256:...
  buildId: build-184
~~~

Thông tin này giúp điều tra lỗi, tái tạo artifact và xác định có thể chạy artifact trên runtime nào.

### 14.2. Kiểm tra tính tái lập

Có thể chạy build hai lần trong môi trường sạch và so sánh hash artifact. Nếu khác nhau, cần xác định nguồn biến động như timestamp, random ID, thứ tự file hoặc thông tin máy local.

Không phải mọi artifact đều phải byte-for-byte reproducible, nhưng dự án cần nêu rõ mức cam kết: cùng semantic output, cùng file content hay cùng byte sequence.

## 15. Cập nhật công cụ

Nâng cấp công cụ nên là một thay đổi có kế hoạch. Một quy trình cơ bản:

1. Xác định lý do nâng cấp: bảo mật, bug fix, tính năng hoặc hỗ trợ nền tảng.
2. Đọc release notes và breaking changes.
3. Kiểm tra ma trận tương thích.
4. Nâng cấp trong branch riêng.
5. Cập nhật manifest và lockfile.
6. Chạy build, test và compatibility checks phù hợp.
7. Kiểm tra generated output và diagnostic thay đổi.
8. Review dependency diff.
9. Ghi migration note nếu cần.
10. Merge và triển khai theo môi trường.

Không nên tự động nâng compiler hoặc runtime lên latest trong mỗi build production nếu dự án cần kết quả ổn định. Có thể dùng bot tạo pull request cập nhật dependency để thay đổi được review.

### 15.1. Patch update

Patch update thường sửa lỗi hoặc lỗ hổng mà không đổi API công khai. Tuy nhiên, vẫn cần kiểm tra release notes và chạy test đại diện vì bug fix có thể làm lộ hành vi mà ứng dụng trước đó vô tình phụ thuộc.

### 15.2. Minor update

Minor update có thể thêm tính năng và API mới. Cần kiểm tra dependency range, warning mới và thay đổi mặc định.

### 15.3. Major update

Major update có thể bỏ API, đổi grammar hoặc artifact format. Cần migration guide, thời gian chuyển tiếp và kế hoạch rollback.

## 16. Deprecation và migration

Deprecation là giai đoạn công bố một API hoặc tính năng sẽ không còn được khuyến nghị và có thể bị loại bỏ trong phiên bản tương lai.

Một lộ trình có thể:

1. Phát hành API mới.
2. Giữ API cũ như wrapper hoặc alias.
3. Đánh dấu API cũ deprecated.
4. Phát warning kèm replacement.
5. Cung cấp codemod hoặc migration guide.
6. Duy trì trong khoảng thời gian đã công bố.
7. Loại bỏ trong một major release theo chính sách.

Ví dụ:

~~~text
@deprecated(since = "4.2", replacement = "requireManualReview")
function requireReview(orderId: OrderId) {
    return requireManualReview(orderId);
}
~~~

Migration tool có thể:

- Chuyển cú pháp DSL cũ sang cú pháp mới.
- Cập nhật import và function name.
- Chuyển schema.
- Tái tạo AST hoặc bytecode.
- Cập nhật build configuration.
- Nâng plugin manifest.

Nếu migration thay đổi source, nên dùng parser và AST để sửa đúng cấu trúc, giữ comment và source location. Thay thế chuỗi toàn cục có thể sửa nhầm string literal hoặc comment.

## 17. Rollback và pin lại phiên bản

Rollback là đưa dự án hoặc môi trường về bộ công cụ đã hoạt động trước đó. Nó hữu ích khi nâng cấp gây lỗi build, thay đổi semantics hoặc tạo artifact không tương thích.

Một kế hoạch rollback nên xác định:

- Manifest và lockfile trước nâng cấp.
- Compiler/runtime artifact cũ còn có thể tải hay không.
- Generated artifact có cần tạo lại không.
- Schema hoặc dữ liệu đã migrate có thể đọc bởi version cũ không.
- Plugin và IDE extension có thể quay lại không.
- Có side effect hoặc thay đổi dữ liệu không thể đảo ngược không.

Rollback tool version không tự động rollback dữ liệu đã được migrate. Nếu schema mới đã ghi dữ liệu mà reader cũ không hiểu, cần backward reader hoặc migration ngược được thiết kế riêng.

Nên giữ artifact của các release đã triển khai, checksum và manifest tương ứng để có thể tái tạo hoặc phục hồi chính xác.

## 18. Quản lý phiên bản trong môi trường developer và CI

Máy developer cần thuận tiện cài và chuyển phiên bản; CI cần tính xác định và môi trường sạch.

Một chính sách có thể:

- Repository chứa toolchain manifest.
- Script bootstrap cài đúng phiên bản.
- IDE extension đọc version từ project.
- CI xác minh compiler/runtime khớp manifest.
- Dependency resolution dùng lockfile.
- Build lưu provenance.
- Bot tạo PR định kỳ cho dependency updates.

Ví dụ bước kiểm tra:

~~~text
read toolchain manifest
verify compiler version
verify runtime ABI
verify build plugin version
resolve locked dependencies
compile DSL sources
run tests
record build provenance
~~~

Nếu version không khớp, CI nên fail sớm với thông báo cụ thể. Không nên tự nâng phiên bản giữa build vì kết quả sẽ khó tái lập.

## 19. Quản lý phiên bản trong container và remote workbench

Container có thể đóng gói compiler, runtime, JDK, build tool và dependency nền. Điều này giúp môi trường nhất quán giữa developer và CI.

Nên pin container image bằng digest khi cần tái lập:

~~~text
registry.example.com/dsl-toolchain:4.2.1
~~~

Tag có thể bị cập nhật theo registry policy; digest xác định nội dung image cụ thể. Cần cân nhắc cập nhật bảo mật định kỳ để image không bị giữ quá lâu ở phiên bản dễ tổn thương.

Remote workbench hoặc dev container có thể cung cấp cùng toolchain cho nhiều người. Workspace manifest vẫn nên ghi version logic của DSL và plugin để project không phụ thuộc vào image một cách ngầm định.

## 20. Bảo mật chuỗi cung ứng công cụ

Toolchain có thể tải compiler, plugin và dependency từ nhiều nguồn. Mỗi package là một phần của supply chain và có thể ảnh hưởng tới source hoặc artifact.

Các thực hành hữu ích:

1. Dùng registry và repository được phê duyệt.
2. Khóa version và checksum.
3. Xác minh chữ ký package nếu hệ sinh thái hỗ trợ.
4. Giới hạn quyền của build plugin.
5. Theo dõi advisory và lỗ hổng của dependency.
6. Tạo SBOM hoặc danh sách thành phần cho artifact quan trọng.
7. Kiểm soát token và credential dùng để tải package.
8. Không chạy script cài đặt từ nguồn không tin cậy.
9. Cập nhật công cụ có lỗ hổng theo quy trình ưu tiên.

Pinning giúp tái lập nhưng không có nghĩa giữ mãi một phiên bản cũ. Cần cân bằng reproducibility với việc nhận bản vá bảo mật.

## 21. SBOM và kiểm kê phiên bản

Software Bill of Materials (SBOM) là danh sách các thành phần phần mềm có trong artifact hoặc môi trường build. Với DSL toolchain, SBOM có thể liệt kê:

- Compiler và runtime.
- Build plugin.
- Parser generator.
- IDE extension package nếu được phân phối cùng sản phẩm.
- Dependency trực tiếp và bắc cầu.
- Version, supplier và checksum.
- License hoặc thông tin bảo mật nếu có.

SBOM giúp nhóm xác định artifact nào bị ảnh hưởng khi một dependency có lỗ hổng. Nó bổ sung cho lockfile: lockfile phục vụ resolve dependency của project, còn SBOM mô tả thành phần thực tế trong artifact hoặc release.

## 22. Quản lý nhiều phiên bản cùng lúc

Một tổ chức có thể phải duy trì nhiều project ở các phiên bản DSL khác nhau. Không nên giả định tất cả project có thể nâng cấp cùng lúc.

Các chiến lược:

- Cài nhiều compiler version song song.
- Dùng project-local toolchain.
- Dùng wrapper chọn compiler theo manifest.
- Cô lập runtime theo service hoặc container.
- Duy trì nhiều language version trong cùng compiler nếu được hỗ trợ.
- Dùng compatibility adapter trong giai đoạn chuyển tiếp.

Một lệnh wrapper có thể đọc manifest và chọn binary phù hợp:

~~~text
dslw compile
~~~

Wrapper kiểm tra project version, tìm đúng compiler và truyền tham số. Nó giúp developer không cần tự nhớ đường dẫn hoặc version, nhưng cần hiển thị rõ compiler thực tế được chọn.

Không nên để PATH hoặc global installation âm thầm quyết định compiler khi project đã khai báo version cụ thể.

## 23. Cấu hình version trong dự án mẫu

Một cấu trúc project minh họa:

~~~text
pricing-project/
  dsl-toolchain.yml
  dsl-dependencies.lock
  build.gradle
  src/
    rules/
      pricing.dsl
  generated/
  docs/
~~~

Manifest:

~~~yaml
languageVersion: 3

tools:
  compiler: 4.2.1
  runtime: 5.0.2
  formatter: 1.8.3
  documentation: 2.6.0

compatibility:
  artifactFormat: 3
  runtimeAbi: 2
~~~

Quy trình build:

1. Đọc manifest.
2. Kiểm tra tool version và ABI.
3. Resolve dependency theo lockfile.
4. Parse và compile source.
5. Format generated source.
6. Sinh tài liệu.
7. Chạy test.
8. Ghi artifact metadata và provenance.

Nếu developer dùng compiler khác, wrapper hoặc build plugin phát hiện mismatch và hướng dẫn cài đúng phiên bản.

## 24. Kiểm thử nâng cấp toolchain

Một lần nâng cấp cần kiểm tra cả chức năng lẫn khả năng tương thích:

### 24.1. Build regression

Biên dịch corpus DSL đại diện và xác nhận các project đang hỗ trợ vẫn build được.

### 24.2. Runtime compatibility

Chạy artifact tạo từ compiler cũ trên runtime mới theo ma trận hỗ trợ.

### 24.3. API compatibility

Biên dịch plugin hoặc extension mẫu với SDK mới. Kiểm tra signature, interface và behavior.

### 24.4. Output regression

So sánh generated source, bytecode, documentation và diagnostic. Diff lớn cần được giải thích, đặc biệt nếu source DSL không đổi.

### 24.5. Reproducibility

Chạy build lặp lại trong môi trường sạch và so sánh hash hoặc nội dung theo mức cam kết.

### 24.6. Migration test

Chạy migration trên project fixture cũ, xác nhận source và cấu hình được chuyển đổi đúng. Chạy lại để kiểm tra idempotence nếu công cụ cam kết thuộc tính đó.

### 24.7. Security scan

Kiểm tra dependency mới, checksum, signature và advisory. Đảm bảo nâng cấp không đưa package không được phê duyệt vào toolchain.

## 25. Theo dõi và chẩn đoán version mismatch

Khi công cụ không tương thích, thông báo nên nêu:

- Thành phần đang chạy.
- Version được yêu cầu.
- Version thực tế.
- Constraint bị vi phạm.
- Nguồn cấu hình quyết định version.
- Cách sửa hoặc lệnh kiểm tra.

Ví dụ:

~~~text
TOOLCHAIN-003: Unsupported runtime ABI.
  Project requires: ABI 2
  Detected runtime: ABI 1
  Runtime version: 4.8.0
  Expected range: 5.x
  Action: install the runtime version declared in dsl-toolchain.yml.
~~~

Nên ghi version vào log khởi động của compiler, language server và runtime. Khi điều tra lỗi production, log giúp xác định toolchain thực tế mà không phải suy đoán từ package file.

## 26. Những lỗi thiết kế thường gặp

### Dùng latest cho mọi build

Dependency tự thay đổi theo thời gian, làm build không tái lập. Khóa version hoặc dùng lockfile.

### Chỉ version hóa compiler

Runtime, grammar, plugin và formatter có thể lệch nhau. Ghi nhận toàn bộ toolchain có ảnh hưởng tới kết quả.

### Dùng một version cho mọi hợp đồng

Language, artifact, runtime ABI và plugin API có vòng đời khác nhau. Tách version để biểu đạt tương thích chính xác.

### Không commit lockfile

Dependency bắc cầu có thể được resolve khác giữa hai lần build. Commit lockfile khi dự án yêu cầu reproducibility.

### Pin phiên bản nhưng không cập nhật bảo mật

Môi trường ổn định nhưng có thể giữ dependency dễ tổn thương. Có lịch cập nhật và quy trình xử lý security advisory.

### Nâng cấp nhiều thành phần cùng lúc

Khi build hỏng khó xác định nguyên nhân. Nâng theo nhóm phụ thuộc có kiểm soát và lưu compatibility matrix.

### Không kiểm tra plugin API

Workbench core thay đổi làm extension cũ không load được. Khai báo plugin constraints và kiểm tra trước khi load.

### Rollback code nhưng không rollback schema

Runtime cũ không đọc được dữ liệu đã migrate. Lập kế hoạch rollback cho cả artifact và data format.

### Không lưu provenance

Không biết artifact được tạo bởi compiler và dependency nào. Ghi source revision, toolchain version và lock hash.

### Dùng version range quá rộng

Resolver có thể chọn bản không được kiểm thử. Giới hạn range theo compatibility policy và khóa kết quả.

## 27. Quy trình quản lý phiên bản công cụ

Một quy trình vận hành có thể gồm:

1. **Kiểm kê toolchain.** Liệt kê compiler, runtime, framework, plugin, grammar, formatter và dependency.
2. **Phân loại hợp đồng.** Xác định language version, artifact format, ABI và public plugin API.
3. **Công bố version policy.** Quy định SemVer, pre-release, deprecation và thời gian hỗ trợ.
4. **Tạo manifest.** Ghi version và constraints có thể được build tool đọc.
5. **Tạo lockfile.** Khóa dependency graph và checksum.
6. **Xác định compatibility matrix.** Công bố tổ hợp compiler/runtime/plugin được hỗ trợ.
7. **Tự động xác minh.** Fail sớm khi version thực tế không khớp manifest.
8. **Nâng cấp có kiểm soát.** Review release notes, dependency diff và breaking changes.
9. **Chạy regression và security checks.** Kiểm tra source, runtime, generated output và dependency.
10. **Lưu provenance.** Gắn artifact với source revision và toolchain đã dùng.
11. **Chuẩn bị rollback.** Giữ manifest và artifact ổn định trước nâng cấp.
12. **Theo dõi vòng đời.** Cập nhật, deprecate và loại bỏ phiên bản theo lịch công bố.

## 28. Kết luận

Quản lý phiên bản công cụ giúp một hệ sinh thái DSL giữ được tính nhất quán giữa compiler, runtime, framework, grammar, plugin, IDE, formatter và dependency. Mỗi thành phần có hợp đồng riêng, vì vậy cần phân biệt language version, compiler version, artifact format, runtime ABI và plugin API thay vì gộp tất cả vào một số phiên bản.

Toolchain manifest, lockfile, compatibility matrix và build provenance tạo nền tảng để biết chính xác project đang dùng gì và có thể tái tạo kết quả. Nâng cấp cần được review cùng release notes, kiểm thử tương thích, migration và kế hoạch rollback. Pinning cần đi cùng quy trình cập nhật bảo mật để môi trường vừa ổn định vừa không bị đóng băng ở phiên bản rủi ro.

Khi được quản lý có hệ thống, toolchain DSL trở thành một phần có thể kiểm soát của project: developer, CI và môi trường triển khai cùng dùng đúng bộ công cụ, hiểu rõ giới hạn tương thích và có thể giải thích nguồn gốc của mỗi artifact.
