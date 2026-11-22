# Kho mã và cấu trúc dự án

Một dự án DSL (Domain-Specific Language) không chỉ gồm các file source viết bằng ngôn ngữ chuyên biệt. Để phát triển, kiểm thử, biên dịch và phát hành một DSL, nhóm cần quản lý grammar, compiler, thư viện, plugin, ví dụ, cấu hình, tài liệu, dependency và artifact. Những thành phần này cần được tổ chức trong một kho mã có cấu trúc rõ ràng để người mới có thể hiểu, công cụ tự động có thể xử lý và các nhóm có thể cộng tác lâu dài.

**Kho mã (code repository)** là nơi lưu trữ có phiên bản của source code và những tài nguyên cần thiết để phát triển một sản phẩm phần mềm. **Cấu trúc dự án (project structure)** mô tả cách chia source, module, test, configuration, documentation và build output thành những phần có ranh giới rõ ràng.

Trong chương **Quản trị vòng đời**, kho mã và cấu trúc dự án là nền tảng để quản lý toàn bộ vòng đời của DSL: khởi tạo, phát triển, review, kiểm thử, phát hành, bảo trì, nâng cấp và lưu trữ. Cấu trúc tốt giúp xác định thành phần nào thuộc sản phẩm, ai sở hữu nó, cách build và cách thay đổi mà không phá các phần khác.

Ví dụ một repository cho DSL có thể được tổ chức như sau:

~~~text
domain-dsl/
    README.md
    LICENSE
    CONTRIBUTING.md
    CHANGELOG.md
    settings.gradle
    build.gradle
    gradle/
    docs/
    examples/
    language/
        grammar/
        standard-library/
    compiler/
        lexer/
        parser/
        semantic/
        codegen/
    runtime/
    plugins/
    tools/
    tests/
    scripts/
~~~

Đây chỉ là một cấu trúc minh họa. Dự án nhỏ có thể dùng ít thư mục hơn; dự án lớn có thể tách repository hoặc chia nhiều module. Điều quan trọng là cấu trúc phản ánh ranh giới domain, dependency và ownership, đồng thời giữ cho build và release có thể tái lập.

## 1. Kho mã trong vòng đời phát triển DSL

Repository là nơi tập trung source và lịch sử thay đổi. Nó hỗ trợ nhiều hoạt động:

- Lưu source code và grammar.
- Theo dõi lịch sử bằng version control.
- Review thay đổi qua pull request hoặc merge request.
- Chạy test và build trong CI.
- Quản lý issue, release và tag.
- Lưu tài liệu, ví dụ và migration guide.
- Theo dõi dependency và license.
- Tạo artifact phát hành.

### 1.1. Repository không chỉ là thư mục source

Một repository hoàn chỉnh thường chứa code, test, build definition, documentation, project metadata và automation. Một số tài nguyên như secret, dữ liệu người dùng, cache và build output không nên được commit.

### 1.2. Source of truth

Repository thường là nguồn chuẩn cho source code và build configuration. Nếu một file được tạo tự động, cần xác định source of truth nằm ở file generator, schema hay generated output.

Ví dụ, grammar có thể là nguồn chuẩn để sinh parser. Nếu nhóm sửa generated parser thủ công nhưng không sửa grammar, lần build tiếp theo có thể ghi đè thay đổi.

### 1.3. Lịch sử và khả năng truy vết

Mỗi thay đổi nên có thể truy ngược tới commit, issue, reviewer và release chứa thay đổi đó. Khả năng truy vết đặc biệt quan trọng khi sửa bug compiler, thay grammar hoặc thay đổi semantics.

### 1.4. Repository là một phần của sản phẩm

README, contribution guide, test fixture và build script ảnh hưởng trực tiếp tới khả năng phát triển và sử dụng DSL. Chúng cần được bảo trì như code, có review và kiểm tra.

## 2. Project, repository, workspace và module

Các khái niệm này thường được dùng gần nhau nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Repository | Đơn vị lưu trữ có version control | domain-dsl |
| Project | Sản phẩm hoặc phạm vi phát triển | DSL compiler |
| Workspace | Không gian làm việc chứa một hay nhiều project/module | IDE workspace |
| Module | Thành phần có interface và dependency riêng | parser module |
| Package | Đơn vị phân phối hoặc namespace code | dsl-parser |
| Artifact | Kết quả build có thể phân phối | compiler JAR |

Một repository có thể chứa nhiều project; một project có thể gồm nhiều module; một workspace có thể mở nhiều repository.

### 2.1. Repository boundary

Ranh giới repository nên phản ánh ownership, release cadence, access control và dependency. Nếu hai thành phần luôn thay đổi cùng nhau, cùng team sở hữu và cùng release, chúng có thể phù hợp trong một repository.

### 2.2. Project boundary

Project mô tả mục tiêu sản phẩm hoặc build unit. Ví dụ compiler, runtime và plugin SDK có thể là các project trong một mono-repository.

### 2.3. Workspace

Workspace có thể chứa project source, module được import và cấu hình editor. Cần xác định workspace root, project root và cách resolve relative path để tool hoạt động nhất quán.

### 2.4. Module

Module nên có trách nhiệm rõ, public interface và dependency được khai báo. Module parser không nên phụ thuộc ngược vào CLI nếu không có lý do kiến trúc.

### 2.5. Package

Package có thể được build và phát hành độc lập. Tên package, version, metadata và dependency constraints là một phần contract với consumer.

## 3. Chọn monorepo hay multi-repository

Có hai cách tổ chức phổ biến: nhiều thành phần trong một repository (monorepo) hoặc mỗi thành phần có repository riêng (multi-repo).

### 3.1. Monorepo

Monorepo lưu nhiều module hoặc project trong cùng một repository.

Ví dụ:

~~~text
domain-dsl/
    compiler/
    runtime/
    cli/
    plugin-sdk/
    language-server/
    docs/
~~~

Ưu điểm:

- Thay đổi đồng bộ giữa các module dễ hơn.
- Một pull request có thể cập nhật API và consumer cùng lúc.
- Có thể chia sẻ build logic và tooling.
- Dễ chạy test tích hợp trên cùng commit.
- Lịch sử thay đổi tổng thể nằm ở một nơi.

Thách thức:

- Repository lớn dần và build có thể chậm.
- Ownership cần rõ để tránh review bottleneck.
- CI cần chọn đúng phần bị ảnh hưởng.
- Quyền truy cập thường khó tách theo module.
- Release độc lập cần quy ước version rõ.

### 3.2. Multi-repo

Mỗi sản phẩm hoặc module có repository riêng:

~~~text
dsl-language/
dsl-compiler/
dsl-runtime/
dsl-cli/
dsl-plugin-sdk/
dsl-language-server/
~~~

Ưu điểm:

- Ownership và quyền truy cập độc lập.
- Release cadence riêng.
- Repository nhỏ và tập trung.
- Team có thể lựa chọn quy trình riêng.

Thách thức:

- Thay đổi xuyên repository cần phối hợp.
- Dependency version có thể lệch.
- Tích hợp end-to-end phức tạp hơn.
- Cần registry hoặc cơ chế phát hành artifact rõ.

### 3.3. Chọn theo ranh giới thay đổi

Không nên chọn chỉ vì monorepo hoặc multi-repo đang là xu hướng. Hãy xem xét:

- Các module có thường thay đổi cùng nhau không?
- Team nào sở hữu chúng?
- Có cần release độc lập không?
- Access control có cần khác nhau không?
- Build và test có thể scale không?
- Dependency có ổn định và được version hóa không?

### 3.4. Hybrid

Một tổ chức có thể dùng monorepo cho compiler core và repository riêng cho plugin bên ngoài hoặc documentation site. Điều quan trọng là interface giữa các repository phải có version và quy trình cập nhật.

## 4. Xác định cấu trúc thư mục

Cấu trúc thư mục nên giúp người đọc trả lời nhanh:

- Source của ngôn ngữ ở đâu?
- Parser và compiler nằm ở đâu?
- Test được tổ chức thế nào?
- Ví dụ nào có thể chạy?
- Tài liệu ở đâu?
- Build output nằm ở đâu?
- File nào được sinh tự động?

Một layout tham khảo:

~~~text
domain-dsl/
    README.md
    CONTRIBUTING.md
    CODE_OF_CONDUCT.md
    LICENSE
    CHANGELOG.md
    docs/
    examples/
    language/
        grammar/
        schemas/
        stdlib/
    compiler/
        lexer/
        parser/
        ast/
        semantic/
        optimizer/
        codegen/
    runtime/
    cli/
    plugin-api/
    language-server/
    tests/
        fixtures/
        integration/
        compatibility/
    build-logic/
    scripts/
~~~

### 4.1. Tổ chức theo domain

Một module có thể chứa source, test và tài liệu liên quan đến cùng domain. Cách này giúp thay đổi một chức năng trong phạm vi rõ ràng.

### 4.2. Tổ chức theo technical layer

Một dự án nhỏ có thể chia lexer, parser, AST, semantic analysis và code generation thành thư mục riêng. Khi hệ thống lớn hơn, mỗi layer có thể trở thành module độc lập.

### 4.3. Tránh cấu trúc quá sâu

Thư mục lồng nhau quá nhiều khiến đường dẫn dài và khó tìm. Chỉ tạo cấp thư mục khi có nhóm file đủ rõ hoặc có boundary về ownership.

### 4.4. Tránh thư mục tên mơ hồ

Những tên như misc, common hoặc utils dễ trở thành nơi chứa mọi thứ. Nếu dùng, cần định nghĩa phạm vi và tránh biến chúng thành dependency trung tâm không có boundary.

### 4.5. Naming convention

Tên thư mục và file nên nhất quán về casing, dấu phân cách và số ít/số nhiều. Tránh hai thư mục gần giống nhau nhưng chứa nội dung không rõ ràng.

## 5. Cấu trúc source của một DSL

Một DSL thường có nhiều phần source khác nhau:

- Grammar definition.
- Lexer/parser implementation hoặc generated source.
- AST và semantic model.
- Type checker.
- Standard library.
- Runtime.
- Backend và code generator.
- CLI và API.
- Plugin interface.
- Editor integration.

### 5.1. Grammar

Grammar nên có vị trí riêng và được xem là nguồn chuẩn nếu parser được sinh tự động. Tài liệu cần mô tả cách build parser từ grammar và cách cập nhật generated source.

### 5.2. AST và semantic model

AST thể hiện cấu trúc cú pháp; semantic model thể hiện ý nghĩa sau name resolution và type checking. Tách hai khái niệm giúp compiler dễ bảo trì.

### 5.3. Standard library

Standard library chứa type, function, module hoặc construct mặc định của DSL. Nó cần version và compatibility policy rõ.

### 5.4. Runtime

Runtime cung cấp các operation thực thi, host function và integration với môi trường. Runtime cần interface rõ với compiler và application.

### 5.5. Backend

Backend chuyển semantic model hoặc IR thành target code/artifact. Backend-specific code nên nằm trong module có ranh giới, tránh rò rỉ chi tiết target vào compiler core.

### 5.6. Generated source

Generated parser, API client hoặc schema code cần được đánh dấu rõ là generated. Không chỉnh sửa thủ công trừ khi quy trình dự án cho phép và có cách tái tạo tương ứng.

## 6. Module boundaries và dependency

Module boundary giúp giới hạn phạm vi thay đổi và xác định API giữa các thành phần.

Ví dụ dependency graph:

~~~mermaid
flowchart TD
    L[Language grammar] --> P[Parser]
    P --> A[AST and semantic model]
    A --> C[Compiler core]
    C --> B[Backends]
    C --> R[Runtime interface]
    CLI[CLI] --> C
    CLI --> P
    LS[Language server] --> P
    LS --> A
    SDK[Plugin SDK] --> A
~~~

Sơ đồ là minh họa; dependency thực tế cần được xác định bởi kiến trúc dự án.

### 6.1. Dependency direction

Dependency nên đi theo hướng kiến trúc đã chọn. Ví dụ compiler core không nên phụ thuộc vào CLI chỉ để in thông báo. Có thể đưa logging hoặc diagnostics vào abstraction dùng chung.

### 6.2. Public và internal API

Không phải class hoặc package nào cũng là public API. Đánh dấu rõ interface được hỗ trợ để tránh consumer phụ thuộc vào implementation detail.

### 6.3. Dependency cycle

Module cycle làm build, test và release khó hơn. Build tool hoặc architecture test có thể phát hiện dependency cycle.

### 6.4. Shared module

Module shared nên chứa abstraction thật sự dùng chung. Nếu nó phụ thuộc ngược vào mọi module, nó đã trở thành trung tâm coupling.

### 6.5. Interface-first

Khi hai team phát triển module độc lập, xác định interface trước giúp tránh chờ implementation của bên kia. Interface cần có contract test.

## 7. Project manifest và build configuration

Project manifest mô tả metadata và cấu hình để tool hiểu project.

Ví dụ:

~~~yaml
name: orders-dsl-project
version: 1.4.0
languageVersion: "2"
modules:
  - src/main.dsl
  - modules/network.dsl
targets:
  - wasm
  - native
dependencies:
  - name: dsl-standard
    version: "2.3.1"
~~~

Đây là cấu trúc minh họa; manifest thực tế phải tuân theo schema của tool.

### 7.1. Project identity

Manifest có thể chứa tên, version, namespace, owner và mô tả project.

### 7.2. Language version

Ghi rõ language version giúp parser/compiler chọn đúng grammar và semantics. Không nên dựa vào default ngầm nếu project cần build tái lập.

### 7.3. Source roots

Source root xác định nơi tool tìm DSL file. Cần quy định path tương đối với manifest hay workspace.

### 7.4. Target definitions

Target có thể là JVM, WebAssembly, native, cloud platform hoặc một runtime riêng. Manifest nên tham chiếu target profile được hỗ trợ.

### 7.5. Build configuration

Build file mô tả task, dependency, compiler option và artifact. Cần phân biệt build configuration với runtime configuration của ứng dụng.

### 7.6. Schema validation

Manifest cần schema version và validation. Unknown key, thiếu field hoặc sai type cần có behavior rõ.

## 8. Dependency management và lockfile

DSL project có thể phụ thuộc vào standard library, plugin, module bên ngoài, compiler plugin hoặc package khác.

### 8.1. Dependency declaration

Manifest khai báo dependency theo tên và version constraint. Tránh dùng version động không kiểm soát trong release build.

### 8.2. Lockfile

Lockfile ghi lại dependency version đã resolve, checksum và source registry. Nó giúp các máy build sử dụng cùng dependency graph.

Ví dụ:

~~~text
dependencies:
    dsl-standard 2.3.1
    cloud-provider-plugin 1.8.0
    schema-tools 4.2.2
~~~

Lockfile thực tế có thể chứa metadata chi tiết hơn và được tạo bởi package manager.

### 8.3. Reproducible dependency resolution

Build tái lập cần:

- Version pin hoặc constraint có kiểm soát.
- Lockfile được quản lý.
- Registry identity rõ.
- Checksum hoặc signature khi phù hợp.
- Chính sách update dependency.

### 8.4. Dependency update

Update dependency nên được review, test compatibility và kiểm tra security advisory. Bot tự động có thể tạo pull request nhưng không thay thế việc đánh giá thay đổi.

### 8.5. Vendoring

Một số dự án lưu bản sao dependency trong repository. Cách này giúp build offline nhưng tăng kích thước repo và trách nhiệm cập nhật license/security.

### 8.6. Dependency confusion

Khi dùng cả private và public registry, cần xác định namespace và source ưu tiên để tránh package giả có tên trùng. Cấu hình registry nên được quản lý tập trung và kiểm tra.

## 9. Source, test, fixture và example

Source code, test và ví dụ có mục tiêu khác nhau, dù cùng mô tả DSL.

Một layout thường gặp:

~~~text
module/
    src/
        main/
        test/
        integrationTest/
    examples/
    fixtures/
~~~

### 9.1. Production source

Chứa implementation được build vào sản phẩm. Không nên trộn test-only helper hoặc dữ liệu thử nghiệm vào source production.

### 9.2. Unit tests

Test logic cục bộ của lexer, parser, AST, semantic analysis hoặc runtime.

### 9.3. Integration tests

Test nhiều module hoặc dependency thật phối hợp với nhau. Cần cô lập environment và cleanup tài nguyên.

### 9.4. Fixtures

Fixture là input/output cố định dùng trong test. Nên có tên mô tả, version nếu liên quan và README khi cấu trúc phức tạp.

### 9.5. Examples

Examples là chương trình DSL có thể dùng để học hoặc làm mẫu. Chúng nên chạy được với tool version được công bố.

### 9.6. Test data

Không dùng dữ liệu production nhạy cảm làm fixture. Tạo dữ liệu synthetic hoặc mask theo policy.

## 10. Documentation và project metadata

Repository cần tài liệu để developer và người dùng hiểu sản phẩm.

Các file phổ biến:

- README.md: giới thiệu, quick start và link tới tài liệu.
- CONTRIBUTING.md: quy trình đóng góp.
- CODE_OF_CONDUCT.md: quy tắc cộng đồng nếu dự án cần.
- LICENSE: quyền sử dụng và phân phối.
- CHANGELOG.md: lịch sử thay đổi.
- SECURITY.md: cách báo cáo lỗ hổng.
- SUPPORT.md: kênh hỗ trợ.

### 10.1. README

README nên trả lời:

- Dự án giải quyết vấn đề gì?
- Ai nên dùng?
- Cần cài đặt gì?
- Làm sao chạy ví dụ đầu tiên?
- Tài liệu đầy đủ ở đâu?
- Cách đóng góp hoặc báo lỗi?

### 10.2. Contribution guide

Nêu cách setup môi trường, coding convention, test command, pull request process và yêu cầu cập nhật docs.

### 10.3. License

License cần rõ cho source và tài sản đi kèm. Dependency cũng cần được kiểm tra license.

### 10.4. Security policy

Nêu cách báo cáo lỗ hổng riêng tư, phiên bản được hỗ trợ và quy trình phản hồi.

### 10.5. Changelog

Changelog nên phân loại feature, fix, breaking change và deprecation. Mỗi mục cần giúp người dùng hiểu tác động.

## 11. Generated files, build output và artifact

Không phải mọi file xuất hiện trong project đều là source.

### 11.1. Generated source

Generated source có thể gồm parser code, serializer, client SDK hoặc resource metadata. Cần xác định:

- Generator và version.
- Input source.
- Output path.
- Có commit generated file không.
- Cách regenerate.
- Cách kiểm tra file đã stale.

### 11.2. Build output

Thư mục build, target hoặc dist thường chứa file tạm và artifact. Không nên commit trừ khi có lý do phân phối rõ.

### 11.3. Artifact repository

Artifact phát hành nên được lưu ở package registry hoặc artifact store, không dựa vào file build output trên máy developer.

### 11.4. Reproducibility

Generated file nên có kết quả ổn định với cùng input và toolchain. Timestamp hoặc random identifier trong output có thể làm diff nhiễu; nếu cần, hãy tách metadata không xác định khỏi phần nội dung reproducible.

### 11.5. Artifact provenance

Artifact có thể gắn source commit, build ID, compiler version, dependency lock hash, SBOM và signature. Điều này giúp truy vết binary đã phát hành.

## 12. File ignore và quản lý dữ liệu cục bộ

Repository thường có file ignore để loại build output, cache và file cá nhân.

Ví dụ:

~~~gitignore
# Build output
build/
dist/
out/

# Local cache
.dsl-cache/
.gradle/

# IDE and operating system
.idea/
.vscode/
.DS_Store

# Local secrets
.env
.env.local
*.key
*.p12
~~~

Đây chỉ là ví dụ; cần điều chỉnh theo toolchain và chính sách của dự án.

### 12.1. Ignore không phải bảo mật

File ignore chỉ ngăn Git tự động đưa file chưa được track vào staging. Nó không xóa secret đã commit trước đó và không ngăn người dùng cố ý add file.

### 12.2. Secret scanning

Dùng secret scanning hoặc pre-commit hook để phát hiện credential vô tình được thêm vào commit.

### 12.3. Remove leaked secret

Nếu secret đã commit, cần revoke/rotate secret và xử lý lịch sử repository theo quy trình. Xóa file ở commit mới không làm credential cũ an toàn trở lại.

### 12.4. Local override

File config local có thể được ignore nhưng cần có example template được commit, ví dụ .env.example không chứa giá trị thật.

## 13. Version control và lịch sử thay đổi

Version control system (VCS) ghi lại lịch sử source và hỗ trợ cộng tác. Git là một lựa chọn phổ biến.

Các khái niệm:

- Working tree: file đang được chỉnh sửa.
- Staging area: thay đổi chuẩn bị commit.
- Commit: snapshot có định danh.
- Branch: dòng phát triển độc lập.
- Merge: kết hợp lịch sử.
- Tag: đánh dấu một commit, thường dùng cho release.

### 13.1. Commit nhỏ và có mục đích

Commit nên đại diện cho một thay đổi có ý nghĩa, giúp review và revert dễ hơn. Tránh gom nhiều thay đổi không liên quan vào một commit.

### 13.2. Commit message

Message nên nói thay đổi làm gì và vì sao. Với thay đổi grammar hoặc API, có thể liên kết issue hoặc proposal.

### 13.3. Branch strategy

Có thể dùng trunk-based development, short-lived feature branch hoặc release branch. Chọn theo nhịp release và quy mô team.

### 13.4. Tag release

Tag nên trỏ tới commit đã phát hành. Không di chuyển tag đã công bố nếu không có quy trình đặc biệt và thông báo rõ.

### 13.5. Signed commits và tags

Chữ ký có thể tăng khả năng xác minh nguồn gốc commit/release. Chính sách signing cần nêu cách quản lý key và xử lý key bị lộ.

## 14. Branching, review và collaboration

Một repository không chỉ cần cấu trúc file; nó cần quy trình thay đổi an toàn.

### 14.1. Pull request

Pull request giúp review source, test, docs và tác động API trước khi merge.

### 14.2. Code ownership

File CODEOWNERS hoặc cơ chế tương đương có thể chỉ định reviewer cho grammar, compiler, runtime, security và release tooling.

### 14.3. Required checks

Branch protection có thể yêu cầu test, lint, build, security scan và approval trước khi merge.

### 14.4. Small changes

Thay đổi nhỏ dễ review hơn. Nếu refactor lớn, nên tách bước cơ học và bước thay đổi behavior để diff rõ.

### 14.5. Merge strategy

Squash, merge commit hoặc rebase đều có trade-off. Quan trọng là team thống nhất và giữ lịch sử có thể truy vết.

### 14.6. Conflict resolution

Conflict ở grammar, lockfile hoặc generated source cần được giải quyết theo source of truth. Không chỉ chọn một phía để build pass.

## 15. Code ownership và project governance

Project lớn cần xác định ai chịu trách nhiệm từng thành phần.

Có thể phân ownership:

| Khu vực | Owner thường gặp |
|---|---|
| Grammar và language spec | Language team |
| Parser và compiler core | Compiler team |
| Runtime | Runtime team |
| Backend | Platform/backend team |
| Plugin SDK | Extension platform team |
| Docs và examples | Documentation/product team |
| Build/release | Developer productivity team |
| Security policy | Security/platform team |

### 15.1. Ownership không chỉ là reviewer

Owner chịu trách nhiệm về compatibility, bug, roadmap và lifecycle của thành phần.

### 15.2. Decision record

Quyết định kiến trúc quan trọng có thể được ghi trong Architecture Decision Record (ADR): bối cảnh, lựa chọn, hệ quả và trạng thái.

### 15.3. RFC cho language change

Thay đổi grammar hoặc semantics lớn nên có proposal, ví dụ, compatibility analysis và migration plan trước khi triển khai.

### 15.4. Shared responsibility

Một module có thể có nhiều contributor nhưng cần một owner rõ để xử lý conflict và release decision.

## 16. Cấu trúc dự án theo giai đoạn vòng đời

Cấu trúc và quy trình cần hỗ trợ các giai đoạn:

~~~mermaid
flowchart LR
    A[Initialize] --> B[Develop]
    B --> C[Review]
    C --> D[Test]
    D --> E[Release]
    E --> F[Maintain]
    F --> G[Upgrade or migrate]
    G --> H[Archive]
~~~

### 16.1. Initialize

Tạo repository, license, README, build skeleton, CI, branch protection và module layout.

### 16.2. Develop

Developer làm việc trong branch, thay đổi source, test, docs và manifest cùng nhau.

### 16.3. Review

Review đánh giá behavior, architecture, security, compatibility và documentation.

### 16.4. Test

CI chạy unit, integration, compatibility và build verification. Test fixtures cần được quản lý như source.

### 16.5. Release

Build artifact, version, changelog, tag, sign và publish theo quy trình.

### 16.6. Maintain

Sửa bug, cập nhật dependency, hỗ trợ release branch và xử lý security advisory.

### 16.7. Upgrade hoặc migrate

Thay đổi module, language version hoặc repository layout cần migration guide và tooling hỗ trợ.

### 16.8. Archive

Khi project ngừng phát triển, giữ source, tag, artifact và tài liệu cần thiết. Đánh dấu trạng thái archived để người dùng biết không còn hỗ trợ.

## 17. Build system và multi-module project

Build system mô tả cách compile, test, package và publish các module.

Ví dụ multi-module:

~~~text
domain-dsl/
    settings.gradle
    build.gradle
    compiler-core/
    parser/
    runtime/
    cli/
    plugin-api/
~~~

### 17.1. Module descriptor

Mỗi module cần khai báo tên, source set, dependency và plugin build cần thiết.

### 17.2. Dependency graph

Build tool dùng dependency graph để xác định thứ tự task. Cycle cần được phát hiện.

### 17.3. Shared build logic

Quy tắc compile, lint và test dùng chung nên được tập trung để tránh cấu hình lệch giữa module.

### 17.4. Build cache

Cache có thể tăng tốc nhưng cần key phản ánh input, toolchain và dependency. Cache không đáng tin cậy không nên trở thành nguồn duy nhất cho artifact release.

### 17.5. Incremental build

Incremental build chỉ chạy task bị ảnh hưởng. Cần xác định input/output task đúng để tránh dùng output stale.

### 17.6. Build isolation

Task nên khai báo input/output và tránh phụ thuộc vào file ngoài build graph. Điều này giúp build tái lập và chạy song song an toàn.

## 18. Cấu hình môi trường phát triển

Repository cần mô tả môi trường để contributor có thể build và test.

Thông tin thường gồm:

- JDK hoặc runtime version.
- Compiler/toolchain version.
- Build tool version.
- Dependency registry.
- Environment variables.
- Database hoặc service test.
- Cách chạy test.
- Cách build documentation.

### 18.1. Version pin

Dùng toolchain file, wrapper hoặc container image để pin phiên bản cần thiết.

### 18.2. Bootstrap script

Script setup có thể cài dependency hoặc tạo local config. Script cần idempotent, có diagnostics và không yêu cầu quyền rộng không cần thiết.

### 18.3. Environment template

Cung cấp sample config với placeholder. Không đưa credential hoặc endpoint nội bộ nhạy cảm.

### 18.4. Development container

Dev container có thể giúp môi trường nhất quán. Cần pin image và giới hạn quyền mount/network phù hợp.

### 18.5. Local services

Nếu test cần database hoặc broker, tài liệu nên cung cấp cách khởi động local service và cleanup.

## 19. Test organization trong repository

Test nên được đặt gần module mà nó bảo vệ hoặc theo test scope rõ ràng.

Một cấu trúc:

~~~text
tests/
    unit/
    integration/
    end-to-end/
    compatibility/
    performance/
    security/
    fixtures/
~~~

### 19.1. Unit tests

Nhanh, cô lập và không phụ thuộc network hoặc service bên ngoài.

### 19.2. Integration tests

Kiểm tra parser, compiler, runtime và backend kết hợp. Dùng dependency thật hoặc test container khi phù hợp.

### 19.3. End-to-end tests

Chạy CLI hoặc API trên project mẫu để xác nhận workflow hoàn chỉnh.

### 19.4. Compatibility tests

Giữ fixture từ release trước để kiểm tra language, API và artifact compatibility.

### 19.5. Performance tests

Theo dõi compile time, memory và throughput trên workload đại diện.

### 19.6. Security tests

Kiểm tra input không tin cậy, plugin isolation, secret handling và resource limits.

### 19.7. Test ownership

Test cần owner như production code. Test flaky hoặc stale nên được sửa, không bị bỏ qua vô thời hạn.

## 20. CI/CD và automation repository

Continuous Integration (CI) tự động build và test thay đổi. Continuous Delivery/Deployment (CD) tự động chuẩn bị hoặc phát hành artifact.

Pipeline có thể:

1. Checkout commit.
2. Resolve dependency theo lockfile.
3. Kiểm tra formatting và lint.
4. Compile grammar/parser.
5. Chạy unit test.
6. Chạy integration test.
7. Kiểm tra API compatibility.
8. Chạy security và dependency scan.
9. Build artifact.
10. Tạo SBOM và provenance.
11. Publish snapshot hoặc release artifact theo policy.

### 20.1. Fast feedback

Chạy test nhanh trước để phát hiện lỗi sớm. Test dài hoặc benchmark có thể chạy ở stage riêng.

### 20.2. Path-based CI

Monorepo lớn có thể xác định module bị ảnh hưởng để chạy test liên quan. Cần bảo đảm dependency graph được tính đúng; thay đổi shared module phải kích hoạt test của consumer.

### 20.3. Protected secrets

CI secret chỉ được cấp cho job cần thiết. Pull request từ fork hoặc source không tin cậy không nên nhận deployment credential.

### 20.4. Reproducible CI

Pin action, build image và dependency version. Tránh pipeline phụ thuộc vào latest tag hoặc tool cài ngầm không có version.

### 20.5. Artifact retention

Xác định thời gian giữ build artifact, test report và log. Release artifact cần retention dài hơn cache tạm.

## 21. Release management

Release là một trạng thái được công bố của sản phẩm. Repository cần hỗ trợ xác định chính xác source và artifact nào thuộc release.

### 21.1. Semantic versioning

Nếu dùng SemVer, version MAJOR.MINOR.PATCH biểu thị breaking change, feature tương thích và bug fix theo contract của dự án.

### 21.2. Language version và tool version

Tool version không nhất thiết bằng language version. Compiler 4.x có thể hỗ trợ DSL language 1.x và 2.x. Cần công bố compatibility matrix.

### 21.3. Release branch

Release branch có thể nhận bug fix trong khi main tiếp tục phát triển. Quy trình cherry-pick hoặc backport cần được ghi rõ.

### 21.4. Tag và artifact

Tag source commit, build artifact từ tag, ghi digest và publish release notes. Không build lại một cách không kiểm soát sau khi đã công bố artifact.

### 21.5. Release manifest

Release metadata có thể ghi:

- Version.
- Source commit.
- Artifact digest.
- Toolchain version.
- Dependency lock hash.
- Build timestamp.
- SBOM.
- Signature.

### 21.6. Support policy

Nêu phiên bản đang được hỗ trợ, thời hạn bảo trì và cách nhận security fix.

## 22. Quản lý schema, grammar và migration

DSL project thường có schema và grammar được consumer sử dụng lâu dài. Những thay đổi cần quy trình migration.

### 22.1. Language evolution

Thay grammar hoặc semantics cần:

- Language proposal.
- Ví dụ source cũ/mới.
- Compatibility analysis.
- Parser/compiler update.
- Diagnostic và deprecation.
- Migration guide.

### 22.2. Manifest schema

Project manifest có thể có schema version. Tool cần biết cách đọc version cũ và báo lỗi khi gặp version không hỗ trợ.

### 22.3. Automated migration

Có thể cung cấp command migrate để cập nhật source. Migration tool cần tạo diff rõ, hỗ trợ dry run và giữ backup hoặc version control history.

### 22.4. Lockfile migration

Khi package manager đổi format lockfile, cần migration path và bảo đảm dependency graph không thay đổi ngoài ý muốn.

### 22.5. AST/IR migration

Nếu AST hoặc IR được lưu làm artifact, cần version schema và converter hoặc chính sách invalidation cache.

## 23. Bảo mật repository

Repository là tài sản quan trọng. Nếu attacker sửa source hoặc pipeline, họ có thể chèn mã vào compiler hoặc artifact phát hành.

### 23.1. Access control

Chỉ cấp quyền write/admin cho người cần. Dùng team và branch protection để quản lý.

### 23.2. Secret scanning

Quét commit và pull request để phát hiện token, key hoặc credential.

### 23.3. Dependency security

Theo dõi advisory, pin dependency và kiểm tra nguồn package.

### 23.4. Signed release

Artifact hoặc release tag có thể được ký để consumer xác minh nguồn gốc.

### 23.5. CI hardening

Không chạy script từ pull request không tin cậy với secret production. Giới hạn permission của CI token và runner.

### 23.6. Branch protection

Yêu cầu review, status check và signed commit nếu policy cần.

### 23.7. Backup và recovery

Repository cần backup hoặc replication theo mức độ quan trọng. Kiểm thử restore để bảo đảm backup có thể sử dụng.

### 23.8. Vulnerability disclosure

Có quy trình nhận và xử lý báo cáo bảo mật, tránh buộc người báo cáo công khai chi tiết exploit.

## 24. Quản lý file lớn và binary assets

Repository DSL có thể chứa grammar, test fixture, binary fixture, model hoặc sample artifact. File lớn làm clone và history nặng.

### 24.1. Không commit build output tùy tiện

Build artifact nên nằm ở registry hoặc release storage, trừ khi repository được thiết kế để lưu binary source asset.

### 24.2. Git LFS

Git Large File Storage có thể quản lý file lớn bằng pointer trong Git và nội dung ở storage riêng. Cần đảm bảo CI và contributor có LFS client.

### 24.3. Fixture size

Giữ fixture nhỏ và tập trung. Nếu cần dataset lớn, tải từ nguồn được version và checksum rõ hoặc dùng synthetic generator.

### 24.4. Binary reproducibility

Nếu binary được commit, cần biết cách tái tạo và xác minh checksum. Tránh commit binary không có source hoặc provenance.

### 24.5. Repository history

Xóa file lớn khỏi working tree không xóa nó khỏi lịch sử Git. Rewrite history có thể ảnh hưởng clone của contributor và cần phối hợp.

## 25. Submodule, subtree và shared components

Một repository có thể cần chia sẻ component từ repository khác.

### 25.1. Git submodule

Submodule tham chiếu một commit cụ thể của repository khác. Nó giữ dependency ở revision xác định nhưng cần clone/update đúng cách.

### 25.2. Git subtree

Subtree đưa nội dung repository khác vào một thư mục và có thể đồng bộ thay đổi. Cần quy định nguồn và quy trình merge.

### 25.3. Package dependency

Thay vì nhúng repository, có thể phát hành component thành package. Cách này phù hợp khi interface đã ổn định và cần version độc lập.

### 25.4. Chọn phương án

Xem xét ownership, release cadence, build offline, security và khả năng cập nhật. Không nên dùng submodule chỉ để tránh thiết kế package version.

## 26. Project templates và repository bootstrap

Một template giúp tạo project DSL mới theo chuẩn chung.

Template có thể chứa:

- Project manifest.
- Source skeleton.
- Test skeleton.
- Build configuration.
- CI workflow.
- README và contribution guide.
- License và security policy.
- Example DSL file.

### 26.1. Template version

Ghi version template để biết project được khởi tạo từ bộ mẫu nào.

### 26.2. Bootstrap command

CLI có thể cung cấp:

~~~text
dsl init my-project --template service
~~~

Command cần tạo file có cấu trúc nhất quán, không ghi đè file hiện có ngoài ý muốn.

### 26.3. Template update

Project đã tạo có thể cần cập nhật template. Không nên tự động ghi đè thay đổi của người dùng. Có thể cung cấp diff hoặc migration tool.

### 26.4. Template validation

CI của template cần build/test project mẫu để bảo đảm template luôn dùng được.

## 27. Cấu trúc repository cho tài liệu và học tập

Tài liệu có thể ở cùng repository hoặc repository riêng.

### 27.1. Docs cùng source

Ưu điểm là docs thay đổi cùng API và được review trong cùng pull request.

### 27.2. Docs riêng

Có thể phù hợp khi tài liệu có workflow, team hoặc quyền truy cập độc lập. Cần version và release coordination.

### 27.3. API reference generated

Reference có thể sinh từ code annotation, schema hoặc CLI definition. Hướng dẫn, concept và tutorial vẫn cần biên tập.

### 27.4. Example synchronization

Examples cần được test với tool version tương ứng. Nếu examples ở repository riêng, pipeline nên kiểm tra compatibility.

### 27.5. Documentation version

Trang tài liệu cần cho phép chọn phiên bản để người dùng không đọc API mới cho binary cũ.

## 28. Monorepo scale và build performance

Khi repository lớn, thời gian clone, build và test có thể tăng.

### 28.1. Module isolation

Giữ API và dependency rõ giúp build chỉ module bị ảnh hưởng.

### 28.2. Incremental build

Khai báo input/output chính xác để build tool tái sử dụng kết quả hợp lệ.

### 28.3. Remote cache

Remote cache có thể chia sẻ build output giữa CI và developer. Cache key phải bao gồm toolchain và input cần thiết; quyền truy cập cache cần tránh lộ artifact riêng tư.

### 28.4. Sparse checkout

Contributor có thể checkout một phần repository nếu workflow hỗ trợ. Build cần biết dependency hoặc generated file nào phải được lấy thêm.

### 28.5. Test selection

Chạy test theo dependency graph giúp giảm thời gian, nhưng cần có full validation định kỳ để phát hiện mapping test bị thiếu.

### 28.6. Repository ownership

Khi module tăng, dùng CODEOWNERS, directory conventions và architecture tests để giữ ranh giới.

## 29. Quản lý nhiều project dùng chung DSL

Một DSL platform có thể phục vụ nhiều project hoặc team.

### 29.1. Workspace manifest

Workspace manifest có thể liệt kê project thành viên, path, dependency và build order.

~~~yaml
workspace:
  name: commerce-platform
  projects:
    - path: services/orders
    - path: services/payments
    - path: shared/network
~~~

### 29.2. Shared modules

Shared module cần version hoặc compatibility policy. Nếu nhiều project import trực tiếp source chung, thay đổi có thể ảnh hưởng đồng thời tất cả consumer.

### 29.3. Project ownership

Mỗi project nên có owner và contact. Workspace không nên làm mờ trách nhiệm của team.

### 29.4. Cross-project dependency

Khai báo dependency qua package hoặc module reference có version. Tránh relative path không ổn định ra ngoài workspace.

### 29.5. Independent release

Project có thể release độc lập nếu interface và dependency được version hóa. Workspace build có thể kiểm tra integration giữa các release.

## 30. Archive và decommission repository

Project có thể kết thúc vòng đời hoặc được thay thế.

### 30.1. Archive

Đánh dấu repository archived, ghi version cuối và thông báo trạng thái hỗ trợ.

### 30.2. Preserve artifacts

Giữ source tag, release artifact, checksum, SBOM và tài liệu cần thiết theo retention policy.

### 30.3. Dependency consumers

Trước khi ngừng repository, xác định consumer còn phụ thuộc. Cung cấp replacement hoặc migration path.

### 30.4. Secrets và credentials

Thu hồi credential, deploy key và token không còn cần. Xóa repository không tự động revoke credential.

### 30.5. Infrastructure cleanup

Nếu project có CI runner, registry, bucket hoặc cloud resource, cleanup theo inventory và ownership. Tránh xóa tài nguyên dùng chung.

### 30.6. Read-only preservation

Repository archived có thể chuyển read-only để giữ lịch sử mà không nhận thay đổi mới.

## 31. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Không phân biệt project và repository | Ranh giới ownership và release mơ hồ | Định nghĩa project, repo, workspace và module |
| Tất cả source dồn vào một thư mục | Khó tìm và khó chia trách nhiệm | Tổ chức theo domain hoặc module |
| Thư mục common chứa mọi thứ | Coupling tăng | Đặt boundary và API rõ |
| Module phụ thuộc vòng | Build và release phức tạp | Kiểm tra dependency graph |
| Không có manifest | Tool phải suy đoán project layout | Khai báo project metadata và source roots |
| Không có lockfile | Build resolve dependency khác nhau | Pin và khóa dependency |
| Commit secret | Credential có thể bị lộ | Secret scanning, rotation và secret manager |
| Commit build output ngẫu nhiên | Repo lớn và diff nhiễu | Ignore output, lưu artifact ở registry |
| Sửa generated file thủ công | Thay đổi bị ghi đè | Sửa source generator hoặc quy trình regenerate |
| README thiếu setup | Contributor không thể build | Viết bootstrap và contribution guide |
| Không có ownership | Review và maintenance bị bỏ trống | CODEOWNERS và module owner |
| CI dùng latest tool không pin | Build khó tái lập | Pin toolchain và action |
| Không version grammar | Source cũ có thể đổi semantics | Language version và compatibility tests |
| Multi-repo không version interface | Consumer bị hỏng khi update | Package version và contract |
| Monorepo không chọn test theo dependency | CI chậm hoặc bỏ sót test | Build graph và impact analysis |
| Không quản lý archive | Consumer không biết project còn hỗ trợ | Archive policy và migration notice |

## 32. Quy trình thiết kế kho mã và cấu trúc dự án

Một quy trình thực tế có thể gồm:

1. **Xác định sản phẩm và domain:** compiler, runtime, CLI, plugin, language server và tài liệu.
2. **Chọn repository boundary:** monorepo, multi-repo hoặc hybrid theo ownership và release cadence.
3. **Xác định module boundary:** trách nhiệm, public API và dependency direction.
4. **Thiết kế directory layout:** source, test, docs, examples, grammar và generated files.
5. **Tạo manifest:** project identity, language version, source roots, targets và dependencies.
6. **Thiết lập dependency management:** version constraints, lockfile, registry và update policy.
7. **Thiết lập build:** wrapper/toolchain pin, multi-module graph, cache và reproducibility.
8. **Thiết lập VCS workflow:** branch protection, review, tags và code ownership.
9. **Thiết lập quality checks:** unit, integration, compatibility, security và docs tests.
10. **Quản lý artifact:** output directory, registry, digest, provenance và retention.
11. **Thiết lập release:** versioning, changelog, release branch và support policy.
12. **Quản lý thay đổi ngôn ngữ:** RFC, grammar version và migration.
13. **Bảo vệ repository:** access control, secret scanning, dependency scanning và backup.
14. **Quản lý vòng đời:** bootstrap, maintain, upgrade, archive và decommission.

## 33. Ví dụ tổng hợp: repository cho một DSL platform

Giả sử một nhóm xây DSL mô tả service và hạ tầng. Repository có thể dùng layout:

~~~text
service-dsl/
    README.md
    CONTRIBUTING.md
    SECURITY.md
    LICENSE
    CHANGELOG.md
    settings.gradle
    build.gradle
    gradle/
    language/
        grammar/
        stdlib/
        schemas/
    compiler/
        lexer/
        parser/
        ast/
        semantic/
        ir/
        codegen/
    runtime/
    cli/
    plugin-api/
    backends/
        kubernetes/
        terraform/
    language-server/
    docs/
        concepts/
        guides/
        reference/
        migration/
    examples/
        hello-service/
        multi-environment/
    tests/
        fixtures/
        compatibility/
        integration/
    scripts/
~~~

### 33.1. Source of truth

Grammar nằm trong language/grammar. Parser được sinh hoặc build từ grammar. Standard library và schema được version cùng language version.

### 33.2. Module dependency

Parser phụ thuộc grammar artifact và AST model. Compiler core dùng AST và semantic model. Backend phụ thuộc compiler IR. CLI gọi compiler public API. Language server tái sử dụng parser và semantic services.

### 33.3. Project manifest

Một project sử dụng DSL khai báo language version, source roots, plugin và target. Lockfile ghi dependency chính xác.

### 33.4. Test strategy

Parser unit tests nằm gần parser module; compatibility fixtures kiểm tra source từ release trước; integration tests compile project mẫu qua CLI.

### 33.5. Release

CI build các module, chạy test, tạo artifact và SBOM. Release tag gắn với commit. Compiler, CLI và plugin API có thể dùng version riêng nếu release độc lập được hỗ trợ.

### 33.6. Maintenance

Grammar change cần RFC và migration note. Dependency update chạy compatibility tests. Security fix được backport theo support policy.

### 33.7. Archive

Khi một backend không còn được hỗ trợ, giữ tag và migration guide, đánh dấu module deprecated trước khi xóa ở major release.

## 34. Tiêu chí của một repository và project structure tốt

Một repository tốt giúp người đóng góp tìm đúng source, hiểu dependency, build và test được sản phẩm, review thay đổi và truy vết release. Cấu trúc dự án tốt phản ánh domain và ownership, có manifest rõ, dependency được khóa, generated files được quản lý và artifact được phát hành có provenance.

Các câu hỏi quan trọng:

- Repository boundary có phù hợp ownership và release cadence không?
- Project, workspace, module và package có được phân biệt rõ không?
- Source grammar, parser, AST, runtime và backend nằm ở đâu?
- Public API và internal implementation có boundary không?
- Dependency graph có hướng rõ và không có cycle không?
- Manifest có khai báo language version, source root và target không?
- Dependency có version và lockfile không?
- Test, fixture, example và docs có cấu trúc dễ tìm không?
- Generated source và build output có được phân biệt không?
- Secret và local data có được bảo vệ khỏi commit không?
- CI có build/test reproducible và dùng toolchain pin không?
- Code ownership, review và branch protection có rõ không?
- Release có tag, artifact digest, changelog và support policy không?
- Grammar, manifest và IR có version/migration strategy không?
- Repository có backup, archive và decommission procedure không?

Kho mã và cấu trúc dự án là nền tảng quản trị vòng đời của một DSL. Khi repository phản ánh đúng ranh giới module, source of truth, dependency và ownership, nhóm có thể phát triển song song mà vẫn kiểm soát được thay đổi. Kết hợp với version control, build tái lập, CI, release metadata và quy trình migration, cấu trúc dự án giúp DSL duy trì được chất lượng từ lúc khởi tạo đến khi bảo trì hoặc kết thúc vòng đời.
