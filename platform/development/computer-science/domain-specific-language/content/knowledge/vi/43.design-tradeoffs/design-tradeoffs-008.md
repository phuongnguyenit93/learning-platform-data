# Mức độ phụ thuộc công cụ

Khi thiết kế một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), nhóm phát triển phải lựa chọn compiler, parser generator, IDE, build system, runtime, database, cloud platform và nhiều công cụ hỗ trợ khác. Những công cụ này có thể tăng tốc phát triển, cung cấp tính năng mạnh và giảm công việc phải tự xây dựng. Tuy nhiên, mỗi lựa chọn cũng tạo ra một mức độ phụ thuộc nhất định. **Mức độ phụ thuộc công cụ (tool dependency)** mô tả phạm vi mà thiết kế, mã nguồn, quy trình phát triển và vận hành của DSL dựa vào một công cụ hoặc hệ sinh thái cụ thể.

Phụ thuộc công cụ không tự động là xấu. Một DSL dùng parser generator có thể dễ bảo trì hơn parser viết tay; một DSL tích hợp sâu với IDE có thể đem lại autocomplete và diagnostics tốt; một runtime tận dụng database cụ thể có thể tối ưu truy vấn hiệu quả. Vấn đề xuất hiện khi công cụ trở thành điều kiện bắt buộc mà không có phương án thay thế hợp lý, khi abstraction bị rò rỉ implementation detail hoặc khi chi phí chuyển đổi vượt quá lợi ích ban đầu.

Thiết kế cần cân bằng giữa năng suất, hiệu năng, khả năng tích hợp, portability, khả năng kiểm soát và chi phí dài hạn. Một nhóm có thể chủ động chấp nhận phụ thuộc vào một nền tảng vì nó đáp ứng yêu cầu sản phẩm. Điều quan trọng là hiểu phụ thuộc nằm ở đâu, ảnh hưởng đến phần nào, có thể thay thế ở mức nào và dữ liệu hoặc source artifact có thể được di chuyển ra sao.

Bài học này trình bày các loại phụ thuộc công cụ trong vòng đời DSL, lợi ích và rủi ro, vendor lock-in, portability, abstraction boundary, chuẩn mở, adapter, plugin architecture, toolchain và runtime, IDE integration, build/deployment, database và cloud, dependency management, license và chi phí, chiến lược giảm phụ thuộc, quyết định kiến trúc và ví dụ đánh giá một DSL.

## 1. Tool dependency là gì?

Tool dependency là quan hệ trong đó một phần của hệ thống dựa vào khả năng, API, định dạng hoặc quy trình của một công cụ bên ngoài.

Ví dụ, một DSL có thể:
- Dùng ANTLR để sinh parser.
- Dùng IntelliJ Platform để xây IDE plugin.
- Dùng Gradle để build compiler.
- Chạy trên JVM.
- Sinh SQL cho PostgreSQL.
- Dùng một cloud workflow service để thực thi quy trình.
- Lưu schema trong một registry cụ thể.
- Dùng một telemetry backend để quan sát runtime.

Mỗi lựa chọn có một mức độ phụ thuộc khác nhau.

### 1.1. Phụ thuộc trực tiếp

Source code gọi API hoặc import package của công cụ. Nếu đổi công cụ, code phụ thuộc cần sửa.

### 1.2. Phụ thuộc định dạng

Hệ thống tạo hoặc tiêu thụ file theo định dạng riêng của công cụ. Ví dụ, model chỉ có thể chỉnh sửa trong một proprietary project format.

### 1.3. Phụ thuộc runtime

Chương trình chỉ chạy trên runtime hoặc platform cụ thể. DSL biên dịch thành bytecode riêng của một engine có thể khó chuyển sang engine khác.

### 1.4. Phụ thuộc quy trình

Build, test, deploy hoặc release chỉ có thể thực hiện qua một hệ thống cụ thể. Quy trình có thể phụ thuộc plugin, task model và secret management riêng.

### 1.5. Phụ thuộc vận hành

Monitoring, backup, scaling, identity và incident response dựa vào dịch vụ của một nhà cung cấp.

### 1.6. Phụ thuộc kỹ năng và tổ chức

Một công cụ có thể đòi hỏi kỹ năng hiếm, quy trình đào tạo riêng hoặc một nhóm chuyên trách. Đây cũng là chi phí phụ thuộc dù không thể nhìn thấy trong source code.

## 2. Các loại công cụ trong hệ sinh thái DSL

Một DSL có thể phụ thuộc vào nhiều lớp công cụ.

### 2.1. Parser và compiler tooling

Ví dụ:
- Lexer/parser generator.
- AST framework.
- Type checker library.
- IR framework.
- Code generation library.
- Compiler plugin API.

Lựa chọn ảnh hưởng grammar, diagnostics, source mapping và cách mở rộng compiler.

### 2.2. IDE và editor

IDE tooling có thể cung cấp:
- Syntax highlighting.
- Autocomplete.
- Go to definition.
- Rename symbol.
- Refactoring.
- Diagnostics.
- Debugging.
- Formatter.
- Project navigation.

Một DSL gắn chặt với một IDE có thể đem lại trải nghiệm tốt nhưng hạn chế người dùng trên editor khác.

### 2.3. Build system

Build system quản lý:
- Dependency resolution.
- Compilation.
- Test.
- Packaging.
- Code generation.
- Caching.
- Release.
- Reproducibility.

Build logic có thể phụ thuộc task API, plugin và convention riêng.

### 2.4. Runtime platform

Runtime quyết định:
- Execution model.
- Memory management.
- Threading.
- Async.
- Security boundary.
- Serialization.
- Debugging.
- Deployment unit.

### 2.5. Database và data platform

DSL query hoặc data mapping có thể sinh SQL, query plan hoặc connector call cho database cụ thể. Tính năng như JSON operator, window function và full-text search có thể không đồng nhất giữa các engine.

### 2.6. Cloud và orchestration

Workflow DSL có thể dựa vào managed workflow engine, container platform, serverless function hoặc queue service. Mỗi nền tảng có semantics retry, timeout, state persistence và identity khác nhau.

### 2.7. Observability

Log, metric, trace, profiler và alerting có thể dùng backend khác nhau. Nếu instrumentation chỉ gọi API proprietary, đổi backend sẽ khó hơn.

### 2.8. Security và identity

Secret manager, identity provider, authorization engine và policy service cũng tạo dependency. Cần xác định phần nào là contract của DSL và phần nào là integration cụ thể.

## 3. Vì sao sử dụng công cụ chuyên biệt?

Công cụ tốt có thể giúp nhóm tập trung vào giá trị cốt lõi của DSL.

### 3.1. Tăng tốc phát triển

Parser generator, compiler framework và IDE SDK giúp tránh tự xây dựng những thành phần phổ biến. Nhóm có thể dành thời gian cho semantics của miền nghiệp vụ.

### 3.2. Chất lượng đã được kiểm chứng

Công cụ trưởng thành có thể cung cấp parser recovery, incremental build, memory management hoặc security patch mà nhóm nhỏ khó tự duy trì.

### 3.3. Tích hợp sẵn

Một công cụ có thể kết nối với database, cloud, CI/CD hoặc IDE hiện có. Tích hợp này giảm công việc vận hành.

### 3.4. Hiệu năng

Một runtime hoặc database chuyên biệt có thể tối ưu workload tốt hơn giải pháp tổng quát.

### 3.5. Hỗ trợ và hệ sinh thái

Documentation, community, plugin, training và commercial support giúp giảm thời gian giải quyết vấn đề.

### 3.6. Tiêu chuẩn hóa

Dùng chuẩn hoặc công cụ phổ biến giúp nhiều nhóm hiểu cùng một quy trình, dễ tuyển dụng và chia sẻ kiến thức.

### 3.7. Time to market

Một dependency có thể giúp sản phẩm ra mắt sớm hơn. Nếu lợi ích kinh doanh lớn và rủi ro được quản lý, phụ thuộc có chủ đích là lựa chọn hợp lý.

## 4. Chi phí và rủi ro của phụ thuộc công cụ

Phụ thuộc tạo ra chi phí hiện tại và tương lai.

### 4.1. Vendor lock-in

Vendor lock-in xảy ra khi chuyển khỏi nhà cung cấp trở nên tốn kém vì API, dữ liệu, workflow hoặc quy trình gắn sâu với nền tảng đó.

### 4.2. API coupling

Nếu domain logic gọi trực tiếp API của công cụ, thay đổi version có thể lan rộng khắp source code.

### 4.3. Format coupling

Nếu source hoặc artifact chỉ tồn tại trong định dạng riêng, việc export hoặc migrate có thể mất metadata hoặc semantics.

### 4.4. Runtime coupling

Một DSL chỉ chạy trên engine độc quyền có thể bị giới hạn về môi trường triển khai, scaling và chi phí.

### 4.5. Upgrade burden

Tool version mới có thể thay API, behavior, dependency graph hoặc minimum runtime. Nhóm phải dành thời gian nâng cấp và xử lý regression.

### 4.6. Security exposure

Dependency có thể chứa vulnerability hoặc bị ngừng hỗ trợ. Cần theo dõi security advisory, patch và transitive dependency.

### 4.7. License và pricing

License có thể thay đổi, tăng theo user, execution, CPU, data volume hoặc environment. Chi phí cần được dự báo ở quy mô tương lai.

### 4.8. Operational dependency

Một service ngoài bị outage có thể làm compiler, build hoặc runtime không hoạt động dù source DSL không thay đổi.

### 4.9. Skills concentration

Nếu chỉ một vài người hiểu công cụ đặc thù, hệ thống có rủi ro vận hành khi họ rời nhóm hoặc không sẵn sàng.

### 4.10. Reduced design freedom

Tool framework có thể áp đặt lifecycle, threading, data model hoặc extension mechanism. Nhóm phải điều chỉnh thiết kế DSL theo giới hạn của công cụ.

## 5. Phân biệt phụ thuộc chấp nhận được và phụ thuộc nguy hiểm

Không cần loại bỏ mọi dependency. Cần đánh giá mức độ ảnh hưởng và khả năng thay thế.

| Đặc điểm | Phụ thuộc có kiểm soát | Phụ thuộc rủi ro cao |
| --- | --- | --- |
| Boundary | Nằm sau interface rõ | Rải khắp domain logic |
| Data format | Có export và schema rõ | Chỉ đọc được bằng công cụ độc quyền |
| Replacement | Có adapter hoặc migration path | Phải viết lại toàn bộ |
| Versioning | Có compatibility policy | Upgrade bất ngờ phá behavior |
| Operations | Có fallback hoặc runbook | Một outage làm dừng mọi hoạt động |
| Cost | Có thể dự báo | Phụ thuộc usage không minh bạch |
| Ownership | Có người chịu trách nhiệm | Không ai theo dõi dependency |

### 5.1. Dependency criticality

Đánh giá công cụ có phải single point of failure không. Nếu parser generator không có sẵn trong build environment, liệu compiler có thể build từ source artifact đã sinh không?

### 5.2. Blast radius

Một thay đổi hoặc outage của công cụ ảnh hưởng một adapter, một stage hay toàn bộ hệ thống?

### 5.3. Exit cost

Ước lượng chi phí chuyển đổi gồm code, data, test, đào tạo, vận hành, downtime và mất tính năng.

### 5.4. Replacement frequency

Một dependency ổn định và hiếm khi thay có thể chấp nhận mức coupling cao hơn một dịch vụ thường xuyên đổi API hoặc giá.

### 5.5. Strategic importance

Nếu một công cụ là lợi thế cốt lõi, nhóm có thể đầu tư sâu. Nếu nó chỉ là hạ tầng commodity, abstraction và portability thường có giá trị hơn.

## 6. Abstraction boundary

Abstraction boundary xác định phần nào của hệ thống được phép biết chi tiết của công cụ.

### 6.1. Domain core

Domain core chứa semantics của DSL:
- Type.
- Rule.
- Workflow meaning.
- Validation.
- Domain operation.
- Error model.

Phần này nên phụ thuộc ít nhất vào framework cụ thể.

### 6.2. Adapter layer

Adapter chuyển contract nội bộ sang API công cụ:

~~~text
DSL Domain Model
       |
       v
Internal Interface
       |
       +--> PostgreSQL Adapter
       +--> Cloud Workflow Adapter
       +--> Local Runtime Adapter
       |
       v
External Tool
~~~

### 6.3. Ports and adapters

Ports and adapters (hexagonal architecture) đặt interface ở phía domain và implementation adapter ở phía ngoài. Domain gọi port, adapter thực hiện tương tác với công cụ.

### 6.4. Anti-corruption layer

Khi tích hợp một hệ thống có model khác, anti-corruption layer chuyển dữ liệu và semantics sang model nội bộ. Nó ngăn thuật ngữ và behavior của vendor lan vào domain.

### 6.5. Interface phải có ý nghĩa

Không nên tạo abstraction chỉ để bọc một method mà không có contract độc lập. Interface tốt thể hiện nhu cầu thật của DSL, không sao chép nguyên API vendor.

### 6.6. Boundary không loại bỏ mọi dependency

Adapter vẫn phụ thuộc công cụ. Mục tiêu là giới hạn nơi dependency xuất hiện và làm cho phần còn lại ít bị ảnh hưởng khi thay đổi.

## 7. Chuẩn mở và portability

Chuẩn mở có thể giảm phụ thuộc vào một implementation cụ thể, nhưng cần xem mức độ tương thích thực tế.

### 7.1. Open format

Dùng định dạng có đặc tả công khai cho schema, artifact hoặc interchange. Ví dụ JSON, XML, Protocol Buffers, OpenAPI hoặc SQL chuẩn có thể hỗ trợ trao đổi giữa công cụ.

### 7.2. Open protocol

Giao tiếp qua HTTP, gRPC, message protocol hoặc tracing protocol được đặc tả giúp nhiều implementation có thể tham gia.

### 7.3. Portability của source

Source DSL có thể độc lập với IDE nếu grammar và project format không bị khóa vào editor. Có thể cung cấp CLI và language server để nhiều editor dùng chung compiler.

### 7.4. Portability của runtime

Một IR ổn định có thể được biên dịch sang nhiều target. Tuy nhiên, semantics như transaction, time, async và security có thể khác nhau giữa target.

### 7.5. Portability của data

Export dữ liệu cần giữ schema, type, nullability, timezone, precision và relationship. Chỉ export CSV có thể làm mất nhiều semantics.

### 7.6. Standard không bảo đảm tương thích hoàn toàn

Hai database cùng hỗ trợ SQL vẫn có khác biệt về type, collation, locking và query planner. Cần test trên từng target.

### 7.7. Conformance suite

Một bộ test conformance xác minh adapter hoặc runtime implementation tuân theo contract chung. Đây là cách quan trọng để giữ portability thực tế.

## 8. Phụ thuộc vào parser và compiler framework

Compiler tooling thường là dependency sớm nhất khi xây DSL.

### 8.1. Parser generator

Parser generator giúp sinh lexer và parser từ grammar. Lợi ích gồm grammar có thể review, parser nhất quán và hỗ trợ error recovery tùy framework.

### 8.2. Grammar coupling

Nếu grammar sử dụng extension riêng của parser generator, việc chuyển sang parser khác có thể cần viết lại grammar. Giữ grammar ở dạng đặc tả rõ và tách semantic action khỏi parser giúp giảm coupling.

### 8.3. AST coupling

Nếu toàn bộ compiler dùng node class của framework, thay framework có thể ảnh hưởng type checker, optimizer và editor integration. Có thể chuyển parse tree thành AST nội bộ ổn định.

### 8.4. Compiler framework

Framework có thể cung cấp symbol table, type system, IR và optimization pass. Cần đánh giá mức độ framework áp đặt semantics của DSL.

### 8.5. Code generation backend

Nếu DSL sinh code cho một target duy nhất, dependency vào backend có thể hợp lý. Nếu cần nhiều target, định nghĩa IR hoặc target-neutral model có thể giúp.

### 8.6. Source mapping

Debugging và diagnostic phụ thuộc source location. Nếu framework không giữ source mapping ổn định, generated output khó truy ngược về DSL.

### 8.7. Tool version

Pin compiler framework version và kiểm thử upgrade. Không nâng dependency chỉ vì có phiên bản mới nếu chưa đánh giá API và output compatibility.

## 9. Phụ thuộc vào IDE và editor

IDE integration ảnh hưởng trải nghiệm học và sử dụng DSL.

### 9.1. IDE-specific plugin

Plugin riêng có thể cung cấp refactoring và debugger sâu, nhưng thường gắn với platform và version API của IDE.

### 9.2. Language Server Protocol

Language Server Protocol (LSP) tách language intelligence khỏi editor. Một language server có thể phục vụ nhiều editor tương thích.

### 9.3. Debug Adapter Protocol

Debug Adapter Protocol (DAP) giúp debugger dùng chung giữa runtime và editor. DSL có thể triển khai debug adapter để hỗ trợ breakpoint, stack và variable inspection.

### 9.4. CLI fallback

CLI cho phép parse, validate, format và compile mà không cần IDE cụ thể. Nó cũng phù hợp với CI và môi trường tự động.

### 9.5. Formatter và linter

Nếu formatter chỉ chạy trong một IDE, CI và editor khác có thể tạo output không nhất quán. Cung cấp formatter CLI hoặc service dùng chung.

### 9.6. Project format

Một project file độc quyền có thể gây lock-in. Cân nhắc manifest dạng văn bản có schema rõ và có thể đọc bằng công cụ khác.

### 9.7. Version compatibility

Plugin cần tương thích với compiler và IDE version. Có thể dùng protocol version và capability negotiation để tránh phụ thuộc API nội bộ.

## 10. Phụ thuộc vào build system và CI/CD

Build system quản lý cách source DSL trở thành artifact.

### 10.1. Build logic

Nếu compiler build logic phụ thuộc sâu vào Gradle plugin API, chuyển sang Maven hoặc Bazel có thể tốn công. Giữ compiler executable hoặc library có thể được gọi từ nhiều build system.

### 10.2. Reproducible build

Pin dependency, compiler version, environment và configuration. Ghi artifact checksum và provenance.

### 10.3. Build cache

Cache riêng của công cụ có thể cải thiện tốc độ nhưng không nên là nơi duy nhất lưu artifact quan trọng. Cache cần key ổn định và invalidation rõ.

### 10.4. CI pipeline

Pipeline nên dùng command hoặc contract có thể chạy ở môi trường khác. Tránh để domain logic chỉ tồn tại trong một workflow UI không thể export.

### 10.5. Deployment integration

Một deploy adapter có thể chuyển artifact sang nhiều environment. Artifact nên độc lập với deployment target khi có thể.

### 10.6. Secret và identity

Build tool có thể cung cấp secret injection và OIDC. Không lưu credential trong build file hoặc artifact.

### 10.7. Migration giữa build systems

Nếu cần chuyển build system, cần inventory task, plugin, cache, test report, code generation và release logic. Không chỉ chuyển file cấu hình.

## 11. Phụ thuộc vào runtime platform

Runtime là một trong những quyết định có tác động dài hạn lớn nhất.

### 11.1. Host language runtime

DSL có thể chạy trên JVM, .NET, JavaScript runtime hoặc native process. Lựa chọn ảnh hưởng GC, concurrency, startup, deployment và ecosystem.

### 11.2. Interpreter độc lập

Một interpreter riêng có thể giảm phụ thuộc host language nhưng tăng chi phí tự xây dựng và tối ưu.

### 11.3. Bytecode hoặc IR

Một IR ổn định có thể hỗ trợ nhiều backend. Cần định nghĩa semantics, version và compatibility của IR.

### 11.4. WebAssembly

WebAssembly có thể cung cấp portability và sandbox model. Nhưng host imports, WASI support và runtime feature vẫn tạo dependency.

### 11.5. Managed workflow runtime

Một managed engine giúp persistence, retry và scaling. Đổi lại, state model và execution semantics có thể gắn với vendor.

### 11.6. Runtime portability test

Chạy cùng conformance suite trên các target. Kiểm tra numeric behavior, timezone, exception, ordering, async và resource limits.

### 11.7. Performance trade-off

Một target portable có thể chậm hơn target chuyên biệt. Cần quyết định theo workload và SLO, không chỉ theo mục tiêu portability.

## 12. Phụ thuộc vào database và query engine

Query DSL có thể bị ràng buộc bởi database dialect và behavior.

### 12.1. SQL dialect

PostgreSQL, MySQL, SQL Server và các engine khác có khác biệt về type, JSON, date, index, function và transaction.

### 12.2. Database-specific feature

Một feature riêng như full-text search hoặc spatial operation có thể đem lại giá trị lớn. Nên đánh dấu rõ là extension của target thay vì giả vờ portable.

### 12.3. Logical query model

Một logical plan trung gian cho phép optimizer và backend generate query theo target. Đây là abstraction hữu ích nếu cần nhiều database.

### 12.4. Capability negotiation

Backend có thể khai báo hỗ trợ window function, recursive query hoặc JSON path. Compiler chọn cách triển khai phù hợp hoặc báo feature không hỗ trợ.

### 12.5. Migration và portability

DDL sinh ra có thể phụ thuộc engine. Schema migration cần target-specific adapter và test trên database tương ứng.

### 12.6. Transaction semantics

Isolation level, locking và constraint timing khác nhau. DSL không nên giả định mọi backend có cùng transaction behavior.

### 12.7. Avoid lowest-common-denominator trap

Chỉ hỗ trợ phần giao nhỏ nhất của mọi database có thể làm DSL mất giá trị. Có thể có core portable và extension target-specific với diagnostics rõ.

## 13. Phụ thuộc vào cloud và dịch vụ managed

Cloud service có thể giảm gánh nặng vận hành nhưng tăng lock-in.

### 13.1. Managed service

Managed database, queue, workflow và identity service giảm công việc cài đặt, backup và scaling. Nhưng API và operational model có thể riêng.

### 13.2. Proprietary workflow semantics

Managed workflow engine có thể có state size limit, retry policy, timeout và event model riêng. DSL runtime adapter cần chuyển semantics mà không làm sai behavior.

### 13.3. Cloud-specific identity

IAM policy và service identity có thể gắn với provider. Domain DSL nên dùng capability hoặc permission model nội bộ, adapter ánh xạ sang IAM.

### 13.4. Storage format

Object storage API có thể tương tự nhưng metadata, consistency và lifecycle khác nhau. Cần abstraction cho object operations nếu portability quan trọng.

### 13.5. Infrastructure as code

Infrastructure definition có thể phụ thuộc Terraform provider, CloudFormation hoặc nền tảng khác. Cần quản lý version và drift.

### 13.6. Multi-cloud không miễn phí

Thiết kế để chạy trên nhiều cloud có thể tăng complexity, test matrix và vận hành. Chỉ làm khi có yêu cầu rõ như resilience, regulation hoặc bargaining power.

### 13.7. Exit strategy

Với service quan trọng, ghi cách export data, recreate infrastructure, chuyển identity và chuyển traffic. Exit plan không cần thực hiện thường xuyên nhưng cần khả thi.

## 14. Plugin architecture và adapter

Plugin và adapter giúp thay thế hoặc mở rộng công cụ mà không làm domain core phụ thuộc trực tiếp.

### 14.1. Plugin contract

Một plugin contract nên định nghĩa:
- Interface.
- Version.
- Capability.
- Lifecycle.
- Input/output schema.
- Error behavior.
- Security boundary.
- Compatibility policy.

### 14.2. Adapter

Adapter chuyển interface nội bộ sang API của tool cụ thể:

~~~text
interface QueryBackend {
  execute(plan: LogicalPlan): QueryResult
}

class PostgresBackend implements QueryBackend {
  execute(plan) {
    // Translate plan to PostgreSQL query
  }
}
~~~

Ví dụ code chỉ minh họa cấu trúc. Domain code nên dùng QueryBackend thay vì gọi API PostgreSQL trực tiếp.

### 14.3. Dependency injection

Dependency injection cho phép chọn implementation theo environment hoặc configuration. Cần tránh để mọi module có thể truy cập service locator tổng quát.

### 14.4. Plugin discovery

Plugin có thể được đăng ký tĩnh, khai báo trong manifest hoặc discovery qua registry. Dynamic discovery cần kiểm tra signature, version và trust.

### 14.5. Isolation

Plugin không tin cậy nên chạy trong process hoặc runtime riêng, với capability và quota giới hạn.

### 14.6. Fallback

Nếu adapter chính lỗi, fallback chỉ được dùng khi semantics tương đương. Không tự chuyển sang implementation có behavior khác mà không thông báo.

### 14.7. Conformance test

Mọi adapter cần chạy chung contract test để đảm bảo các implementation trả kết quả và error theo cùng semantics.

## 15. Dependency management và supply chain

Phụ thuộc công cụ không chỉ là API trực tiếp. Dependency bắc cầu cũng ảnh hưởng bảo mật và khả năng bảo trì.

### 15.1. Pin version

Dùng version cụ thể hoặc constraint có kiểm soát. Không tự động lấy latest trong build production.

### 15.2. Lockfile

Lockfile ghi dependency graph đã resolve. Nó giúp build có thể tái lập giữa developer và CI.

### 15.3. SBOM

Software Bill of Materials liệt kê thành phần và version trong artifact. SBOM hỗ trợ kiểm tra vulnerability và license.

### 15.4. Vulnerability scanning

Quét dependency và theo dõi advisory. Có policy về severity, thời gian xử lý và exception.

### 15.5. License compliance

Kiểm tra license trực tiếp và transitive. Một dependency có thể giới hạn việc phân phối compiler hoặc runtime.

### 15.6. Artifact provenance

Ghi source revision, build tool, compiler version, dependency digest và environment. Điều này giúp xác định artifact nào bị ảnh hưởng khi một dependency có vấn đề.

### 15.7. Private registry

Private registry có thể tăng kiểm soát nhưng cũng là dependency vận hành. Cần backup, access control và quy trình phục hồi.

### 15.8. Dependency removal

Xóa dependency không dùng giúp giảm attack surface, build time và upgrade burden. Cần xác minh không còn runtime path nào sử dụng nó.

## 16. Đánh giá chi phí và tổng chi phí sở hữu

Một công cụ miễn phí không đồng nghĩa tổng chi phí thấp.

### 16.1. License cost

Tính theo user, worker, execution, data volume, environment hoặc feature tier. Ước lượng ở quy mô dự kiến.

### 16.2. Engineering cost

Bao gồm integration, upgrade, custom plugin, workaround, migration và training.

### 16.3. Operational cost

Bao gồm hosting, monitoring, backup, support, on-call và incident recovery.

### 16.4. Exit cost

Tính chi phí export data, thay adapter, chuyển source format, viết lại test và đào tạo lại.

### 16.5. Opportunity cost

Thời gian xử lý dependency issue là thời gian không dành cho semantics hoặc feature cốt lõi của DSL.

### 16.6. Total Cost of Ownership

TCO nên xem xét toàn bộ vòng đời, không chỉ giá mua ban đầu.

### 16.7. Cost of not using a tool

Tự xây một compiler framework hoặc workflow engine cũng có chi phí lớn. Tránh phụ thuộc bằng mọi giá có thể dẫn đến một nền tảng nội bộ khó duy trì.

## 17. Ma trận đánh giá dependency

Có thể chấm mỗi công cụ theo một số tiêu chí.

| Tiêu chí | Câu hỏi đánh giá |
| --- | --- |
| Functional fit | Có đáp ứng yêu cầu cốt lõi không? |
| Integration | Tích hợp với kiến trúc hiện tại dễ đến đâu? |
| Portability | Có thể thay bằng implementation khác không? |
| Stability | API và release policy ổn định không? |
| Security | Có quy trình patch và advisory rõ không? |
| Performance | Đáp ứng workload và SLO không? |
| Cost | Chi phí hiện tại và tương lai ra sao? |
| Skills | Nhóm có thể vận hành và hỗ trợ không? |
| Data ownership | Có thể export dữ liệu đầy đủ không? |
| Exit strategy | Có đường chuyển đổi thực tế không? |

### 17.1. Weighted score

Có thể gán trọng số theo mục tiêu sản phẩm. Ví dụ, một compiler dùng trong môi trường offline có thể coi portability và deterministic build quan trọng hơn managed support.

Không nên dùng điểm tổng để che một rủi ro không thể chấp nhận, như không thể export dữ liệu hoặc thiếu security patch.

### 17.2. Risk register

Với dependency quan trọng, ghi:
- Risk.
- Likelihood.
- Impact.
- Owner.
- Mitigation.
- Trigger.
- Exit option.

### 17.3. Decision record

Lưu lý do chọn công cụ, phương án đã cân nhắc, trade-off và điều kiện xem xét lại. Điều này giúp nhóm tương lai hiểu quyết định thay vì chỉ thấy dependency trong build file.

## 18. Chiến lược giảm phụ thuộc mà không tạo abstraction thừa

Không cần abstraction cho mọi thư viện. Chọn nơi boundary đem lại giá trị.

### 18.1. Isolate high-impact dependencies

Ưu tiên cô lập database, cloud workflow, identity, compiler framework và proprietary runtime nếu chúng có khả năng thay đổi hoặc ảnh hưởng lớn.

### 18.2. Keep domain model internal

Không dùng vendor DTO làm domain model chính. Map sang type nội bộ ở adapter boundary.

### 18.3. Use open interchange formats

Cho phép export schema, source, data và artifact metadata ở định dạng có thể đọc bằng công cụ khác.

### 18.4. Keep CLI entry points

Cung cấp command line cho compile, validate, format, test và package. Điều này giảm phụ thuộc vào IDE hoặc CI UI.

### 18.5. Separate compiler from build plugin

Compiler nên có thể chạy độc lập; plugin build system chỉ là adapter gọi compiler và tích hợp report.

### 18.6. Keep generated artifacts

Nếu parser hoặc code generator được sinh từ toolchain, có thể lưu generated source trong release artifact để build consumer không cần tool generator, tùy license và policy.

### 18.7. Pin and test upgrades

Upgrade theo kế hoạch, đọc changelog, chạy conformance suite và đo performance. Tránh nâng nhiều dependency lớn cùng lúc.

### 18.8. Avoid abstraction for commodity details

Không cần tự định nghĩa wrapper cho mọi utility library. Abstraction nên bảo vệ semantics hoặc boundary có giá trị thực.

## 19. Khi nào nên chấp nhận phụ thuộc sâu?

Một số trường hợp phụ thuộc sâu là lựa chọn hợp lý.

### 19.1. Công cụ tạo lợi thế sản phẩm

Nếu một IDE platform cho phép refactoring và debugging mà nhóm không thể tái tạo dễ dàng, tích hợp sâu có thể đáng giá.

### 19.2. Workload chuyên biệt

Một database hoặc runtime có feature rất phù hợp với domain có thể cải thiện hiệu năng và đơn giản hóa implementation.

### 19.3. Platform đã được tổ chức chuẩn hóa

Nếu tổ chức đã dùng một cloud, identity provider và build platform rộng rãi, tái sử dụng hệ sinh thái có thể giảm operational complexity.

### 19.4. Thời gian và nguồn lực giới hạn

Một nhóm nhỏ có thể cần ưu tiên delivery. Có thể chấp nhận lock-in trong một giai đoạn nếu ghi nhận exit cost và tránh để dữ liệu không thể export.

### 19.5. Không cần portability

Nếu sản phẩm chỉ chạy trong một môi trường đã xác định và không có yêu cầu chuyển đổi, đầu tư multi-platform có thể không đem lại giá trị.

### 19.6. Quyết định có chủ đích

Chấp nhận dependency sâu cần đi kèm:
- Owner.
- Version policy.
- Cost forecast.
- Security review.
- Data export plan.
- Exit trigger.
- Operational runbook.

## 20. Ví dụ: thiết kế DSL có nhiều backend

Giả sử một DSL dùng để truy vấn dữ liệu đơn hàng và cần hỗ trợ PostgreSQL hiện tại, có thể thêm một data warehouse trong tương lai.

### 20.1. Domain query model

~~~text
query MonthlySales {
  from Order
  where status == PAID
  group by month(createdAt), storeId
  select {
    month,
    storeId,
    revenue: sum(total)
  }
}
~~~

### 20.2. Logical plan

Compiler chuyển query thành logical plan độc lập database:

~~~text
Scan(Order)
  -> Filter(status = PAID)
  -> GroupBy(month(createdAt), storeId)
  -> Aggregate(sum(total))
  -> Project(month, storeId, revenue)
~~~

### 20.3. Backend interface

~~~text
interface QueryBackend {
  capabilities(): QueryCapabilities
  execute(plan: LogicalPlan): QueryResult
}
~~~

### 20.4. PostgreSQL adapter

Adapter chuyển logical plan sang PostgreSQL SQL, bind parameter và map result về output type của DSL.

### 20.5. Warehouse adapter

Adapter khác có thể chuyển plan sang dialect hoặc API của warehouse. Nó có thể hỗ trợ thêm partition pruning hoặc columnar scan.

### 20.6. Capability negotiation

Nếu target không hỗ trợ một operator, compiler có thể:
- Rewrite thành operator khác có semantics tương đương.
- Thực hiện một phần ở runtime.
- Từ chối compile với diagnostic rõ.
- Yêu cầu người dùng chọn target có hỗ trợ.

### 20.7. Trade-off

Logical plan tăng khả năng portability nhưng có chi phí thiết kế và giới hạn feature. Nếu chỉ có một database trong toàn bộ vòng đời, adapter abstraction có thể chưa cần quá tổng quát.

### 20.8. Conformance tests

Chạy cùng query fixture trên hai backend và so sánh:
- Row set.
- Null behavior.
- Ordering.
- Decimal precision.
- Timezone.
- Error semantics.

## 21. Ví dụ: DSL workflow trên managed engine

Một DSL workflow có thể mô tả:

~~~text
workflow orderFulfillment(orderId) {
  step reserveInventory
  step collectPayment
  step arrangeShipment
}
~~~

### 21.1. Engine-specific adapter

Runtime adapter chuyển step thành task của managed workflow engine. Engine có thể cung cấp persistence, retry và scheduler.

### 21.2. Portability boundary

Domain workflow model giữ state và transition semantics nội bộ. Adapter ánh xạ sang engine-specific definition.

### 21.3. Semantic gap

Nếu engine có retry semantics khác DSL, adapter cần mô phỏng hoặc từ chối feature không tương thích. Không được silently đổi retry count hoặc timeout.

### 21.4. State portability

Nếu chuyển engine, cần export workflow instance, current state, context, timer và pending event. Một số engine không cho phép export đầy đủ execution state.

### 21.5. Quyết định

Nếu workflow engine là phần cốt lõi và không có ý định chuyển, có thể chấp nhận phụ thuộc sâu. Nếu DSL là sản phẩm cần chạy trên nhiều môi trường, cần đầu tư internal state model và adapter sớm.

## 22. Portability và semantics của DSL

Portability không chỉ là source compile được trên nhiều nền tảng.

### 22.1. Numeric semantics

Decimal precision, integer overflow và floating-point behavior có thể khác nhau giữa target. DSL cần định nghĩa semantics riêng.

### 22.2. Date và timezone

Time zone database, daylight saving và parsing behavior có thể khác. Dùng type Instant, LocalDate và explicit timezone để giảm mơ hồ.

### 22.3. String và collation

Unicode normalization, case folding và collation khác nhau giữa runtime hoặc database. So sánh chuỗi cần semantics rõ.

### 22.4. Null semantics

SQL null và null trong host language có behavior khác nhau. DSL query cần định nghĩa three-valued logic hoặc mapping phù hợp.

### 22.5. Ordering

Map hoặc collection có thể không bảo đảm order. Nếu output yêu cầu deterministic ordering, cần sort key rõ.

### 22.6. Concurrency

Thread scheduling và transaction isolation khác nhau giữa runtime. Không dựa vào race behavior không được đặc tả.

### 22.7. Error semantics

Một target có thể throw exception, target khác trả error code. Adapter cần map về error model chung mà không mất thông tin quan trọng.

## 23. Quản trị dependency theo vòng đời

Dependency cần được theo dõi từ lúc lựa chọn đến lúc loại bỏ.

### 23.1. Evaluation

Thử nghiệm tool trên workload đại diện, không chỉ theo demo hoặc marketing claim.

### 23.2. Adoption

Ghi owner, version, license, security contact, operational dependency và integration boundary.

### 23.3. Upgrade

Có lịch nâng cấp, compatibility tests và quy trình rollback. Theo dõi end-of-life và support window.

### 23.4. Incident

Khi tool outage hoặc vulnerability, biết component nào bị ảnh hưởng và cách giảm tác động.

### 23.5. Replacement

Có kế hoạch chuyển API, data và workflow. Giữ export format và contract test để giảm bất ngờ.

### 23.6. Retirement

Khi dependency không còn dùng, xóa integration, secret, permission, plugin và transitive dependency. Xác minh không còn artifact hoặc job phụ thuộc.

## 24. Những lỗi thường gặp khi quản lý tool dependency

**Chọn công cụ chỉ vì phổ biến.** Công cụ có thể không phù hợp semantics hoặc workload của DSL. Hãy đánh giá bằng use case và prototype.

**Đưa vendor API vào domain core.** Thay đổi vendor lan rộng khắp source. Hãy đặt adapter ở boundary có giá trị.

**Abstraction quá sớm và quá rộng.** Interface tổng quát khó dùng và phải hỗ trợ nhiều semantics không cần thiết. Hãy trừu tượng hóa nhu cầu hiện tại với đường mở rộng có chủ đích.

**Giả định chuẩn mở đồng nghĩa portability.** Implementation vẫn khác về semantics và feature. Hãy dùng conformance test.

**Không lưu dữ liệu ở định dạng có thể export.** Khi rời tool, dữ liệu và metadata có thể bị mắc kẹt. Hãy kiểm tra export ngay khi lựa chọn.

**Không pin dependency.** Build có thể thay đổi theo thời điểm. Hãy dùng lockfile và version policy.

**Nâng cấp nhiều công cụ cùng lúc.** Khó tìm nguyên nhân regression. Hãy chia upgrade thành thay đổi có thể kiểm chứng.

**Bỏ qua transitive dependency.** Vulnerability hoặc license có thể đến từ dependency bắc cầu. Hãy tạo SBOM và scan định kỳ.

**Không tính exit cost.** Giá hiện tại thấp nhưng migration tương lai có thể rất cao. Hãy ghi exit strategy cho dependency critical.

**Theo đuổi multi-cloud không có nhu cầu.** Portability có thể tăng complexity và giảm tận dụng dịch vụ managed. Hãy xác định lý do kinh doanh trước.

**Không kiểm thử adapter.** Hai backend có thể trả kết quả khác nhau. Hãy chạy chung conformance suite.

**Không có owner.** Dependency lỗi thời và không được nâng cấp. Mỗi dependency quan trọng cần người chịu trách nhiệm.

## 25. Quy trình đánh giá và quyết định tool dependency

Có thể thực hiện theo các bước:

1. **Nêu nhu cầu:** xác định vấn đề mà công cụ cần giải quyết.
2. **Xác định phạm vi:** parser, IDE, build, runtime, database, cloud hay operations.
3. **Liệt kê phương án:** tự xây, dùng open-source, dùng managed service hoặc proprietary platform.
4. **Prototype:** thử trên workload và integration thực tế.
5. **Đánh giá semantics:** xem tool có áp đặt behavior không phù hợp DSL không.
6. **Đánh giá portability:** source, data, artifact và runtime có thể chuyển không.
7. **Đánh giá chi phí:** license, engineering, operation, support và exit.
8. **Đánh giá security:** patch, supply chain, identity, data ownership và isolation.
9. **Thiết kế boundary:** domain interface, adapter, format và conformance test.
10. **Ghi quyết định:** lý do, trade-off, owner, version policy và exit trigger.
11. **Theo dõi:** upgrade, vulnerability, pricing và end-of-life.
12. **Xem xét lại:** khi workload, organization hoặc business strategy thay đổi.

## 26. Kết luận

Mức độ phụ thuộc công cụ là một đánh đổi kiến trúc trong toàn bộ vòng đời DSL. Parser framework, IDE, build system, runtime, database, cloud, identity và observability tool có thể giúp tăng tốc phát triển và vận hành, nhưng cũng tạo coupling, upgrade burden, vendor lock-in, chi phí và rủi ro gián đoạn.

Thiết kế tốt không có nghĩa là loại bỏ mọi dependency. Hãy giữ domain semantics và contract quan trọng trong phần lõi, đặt adapter ở boundary có giá trị, dùng chuẩn mở khi phù hợp, kiểm tra portability bằng conformance test và lưu source, data cùng artifact ở định dạng có thể truy xuất. Với dependency được chấp nhận sâu, cần owner, version policy, security monitoring, cost forecast và exit strategy tương xứng.

Hãy đánh giá công cụ theo nhu cầu thực tế, workload, semantics, chi phí toàn vòng đời và khả năng phục hồi. Khi biết chính xác hệ thống phụ thuộc vào điều gì và có kế hoạch cho thay đổi, nhóm có thể tận dụng hệ sinh thái công cụ mà vẫn giữ quyền kiểm soát đối với DSL và sản phẩm của mình.

