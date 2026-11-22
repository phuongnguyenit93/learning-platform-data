# Sở hữu ngôn ngữ DSL

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) có thể bắt đầu như một tập cú pháp nhỏ do một nhóm phát triển tạo ra để giải quyết một nhu cầu cụ thể. Khi DSL được nhiều nhóm sử dụng, có compiler, runtime, plugin, tài liệu, thư viện và sản phẩm phụ thuộc, ngôn ngữ đó trở thành một tài sản kỹ thuật cần được quản trị lâu dài. Khi ấy, câu hỏi quan trọng không chỉ là ai viết parser hoặc ai sửa một rule, mà là **ai chịu trách nhiệm về ngôn ngữ, ai có quyền quyết định cách ngôn ngữ thay đổi và ai bảo đảm nó tiếp tục được duy trì**.

**Sở hữu ngôn ngữ** (*language ownership*) là việc xác định tổ chức, nhóm và cá nhân chịu trách nhiệm về định hướng, đặc tả, chất lượng, tương thích, bảo mật và vòng đời của DSL. Quyền sở hữu không nhất thiết có nghĩa một cá nhân kiểm soát mọi quyết định. Nó là một mô hình trách nhiệm và quyền quyết định rõ ràng, giúp người dùng biết nơi đề xuất thay đổi, nhóm phát triển biết ai phê duyệt, còn tổ chức biết ai duy trì ngôn ngữ khi đội ngũ hoặc nền tảng thay đổi.

Một DSL không có chủ sở hữu rõ ràng dễ phát triển theo những hướng không nhất quán: compiler thêm cú pháp mà tài liệu chưa cập nhật, plugin tự định nghĩa semantics riêng, nhiều nhóm dùng cùng tên với ý nghĩa khác nhau hoặc không ai chịu trách nhiệm xử lý lỗ hổng và breaking change. Quản trị ownership giúp ngôn ngữ có định hướng ổn định, có quy trình thay đổi minh bạch và có người chịu trách nhiệm từ lúc hình thành đến khi ngừng hỗ trợ.

## 1. Khái niệm sở hữu ngôn ngữ

### 1.1. Language ownership là gì?

Language ownership là trách nhiệm tổng thể đối với một DSL như một sản phẩm hoặc nền tảng dùng chung. Phạm vi thường gồm:
- Tầm nhìn và mục tiêu của ngôn ngữ.
- Phạm vi miền nghiệp vụ mà DSL giải quyết.
- Grammar và semantics chính thức.
- Type system, built-in function và standard library.
- Compiler, interpreter, runtime và toolchain tham chiếu.
- API mở rộng, plugin và tích hợp.
- Tài liệu, ví dụ và hướng dẫn migration.
- Quy tắc versioning và compatibility.
- Bảo mật, hỗ trợ và vòng đời phát hành.
- Quyết định deprecation và end-of-life.

### 1.2. Ownership khác authorship

Author là người viết một phần nội dung hoặc mã. Owner là người hoặc nhóm chịu trách nhiệm cuối cùng về trạng thái và quyết định của tài sản. Một developer có thể viết một feature nhưng language owner phải bảo đảm feature phù hợp với định hướng, đặc tả và compatibility policy.

### 1.3. Ownership khác maintenance

Maintenance thường tập trung vào sửa lỗi và cập nhật implementation. Ownership bao gồm cả việc quyết định DSL nên trở thành gì, nên hỗ trợ use case nào, thay đổi nào được chấp nhận và khi nào một tính năng nên bị loại bỏ.

### 1.4. Ownership không đồng nghĩa quyền sở hữu pháp lý

Trong tổ chức, language owner có thể chịu trách nhiệm kỹ thuật nhưng quyền sở hữu trí tuệ có thể thuộc công ty, khách hàng, cộng đồng hoặc tác giả theo hợp đồng và license. Hai khái niệm cần được phân biệt và ghi nhận rõ.

### 1.5. Vì sao cần xác định owner?

Khi không có owner:
- Không ai giải quyết tranh luận về semantics.
- Feature được thêm không theo một nguyên tắc chung.
- Breaking change xuất hiện bất ngờ.
- Tài liệu và implementation có thể lệch nhau.
- Lỗ hổng hoặc dependency lỗi không có người xử lý.
- Kiến thức tập trung ở một cá nhân và dễ mất khi người đó rời nhóm.
- Người dùng không biết gửi yêu cầu hoặc báo lỗi ở đâu.

### 1.6. Ownership là trách nhiệm liên tục

Ngôn ngữ cần được quản trị sau khi release. Owner tiếp tục theo dõi adoption, lỗi, hiệu năng, security advisory, nhu cầu người dùng và khả năng tương thích trong các phiên bản tiếp theo.

## 2. Tài sản nào thuộc phạm vi ownership?

### 2.1. Đặc tả ngôn ngữ

Đặc tả chính thức mô tả:
- Cú pháp và lexical grammar.
- Cấu trúc câu lệnh và biểu thức.
- Type system và type inference.
- Evaluation order.
- Null và error semantics.
- Scope và name resolution.
- Quy tắc module/import.
- Built-in function và operator.
- Quy tắc serialization hoặc interchange nếu có.

### 2.2. Implementation

Ownership có thể bao gồm compiler, parser, lexer, interpreter, runtime, optimizer, code generator, debugger và language server. Nếu có nhiều implementation, cần phân định implementation nào là reference hoặc implementation nào được hỗ trợ chính thức.

### 2.3. Standard library

Các kiểu miền, hàm dựng sẵn, operator, connector và utility được coi là một phần của ngôn ngữ hoặc nền tảng. Owner cần quản lý tên, semantics, version và deprecation của chúng.

### 2.4. Extension ecosystem

Plugin API, extension point, package registry, SDK và mẫu plugin cũng là tài sản cần quản trị. API mở rộng không có owner có thể thay đổi tùy tiện và làm hỏng plugin bên thứ ba.

### 2.5. Tooling

Editor, formatter, linter, debugger, language server, test harness và build plugin ảnh hưởng trực tiếp đến trải nghiệm người dùng. Cần xác định tool nào là core, tool nào là optional và ai duy trì.

### 2.6. Documentation

Grammar reference, tutorial, migration guide, release notes và security guidance cần có chủ sở hữu. Tài liệu cũ có thể gây lỗi giống như implementation sai.

### 2.7. Artifact và hạ tầng phát hành

Repository, package registry, build pipeline, signing key, release automation, documentation site và issue tracker cần có quyền quản trị và kế hoạch dự phòng.

### 2.8. Intellectual property

Tên ngôn ngữ, logo, source code, grammar, tài liệu, test corpus và generated artifact có thể chịu các điều khoản sở hữu trí tuệ khác nhau. Owner kỹ thuật cần biết các giới hạn liên quan và phối hợp với bộ phận pháp lý.

## 3. Mô hình tổ chức ownership

### 3.1. Centralized ownership

Một nhóm trung tâm kiểm soát đặc tả, compiler và quyết định thay đổi.

Ưu điểm:
- Semantics và roadmap nhất quán.
- Dễ áp dụng policy chung.
- Có một đầu mối hỗ trợ và release.

Hạn chế:
- Nhóm trung tâm có thể trở thành bottleneck.
- Domain team phải chờ phê duyệt.
- Owner có thể thiếu hiểu biết sâu về từng miền sử dụng.

### 3.2. Federated ownership

Một nhóm core giữ grammar, type system và runtime contract; các nhóm miền quản lý extension hoặc profile riêng trong ranh giới được công bố.

Ưu điểm:
- Chia sẻ trách nhiệm.
- Nhóm miền có quyền phản hồi nhanh.
- Core vẫn giữ semantics chung.

Hạn chế:
- Cần quy tắc rõ về core và extension.
- Có nguy cơ phân mảnh nếu extension trở thành dialect không tương thích.
- Cần cơ chế phối hợp và giải quyết xung đột.

### 3.3. Community governance

Trong dự án mở, cộng đồng có thể đề xuất và review thay đổi qua public repository, RFC và steering group. Quyền merge, release và trademark cần được quy định riêng.

### 3.4. Vendor-owned language

Một nhà cung cấp có thể sở hữu DSL thương mại. Khách hàng sử dụng theo license và có thể đề xuất feature nhưng không nhất thiết có quyền quyết định roadmap. Hợp đồng cần làm rõ quyền sử dụng, export và hỗ trợ.

### 3.5. Internal platform language

Một tổ chức có thể sở hữu DSL nội bộ. Ownership thường nằm trong platform engineering hoặc architecture group, với domain teams tham gia định nghĩa semantics.

### 3.6. Chọn mô hình theo quy mô và mục tiêu

Mô hình cần phù hợp với:
- Số nhóm sử dụng.
- Mức độ quan trọng của DSL.
- Tốc độ thay đổi nghiệp vụ.
- Mức độ mở của dự án.
- Yêu cầu compliance.
- Nguồn lực duy trì.
- Số implementation và plugin ecosystem.

Không nên tạo một hội đồng lớn nếu DSL chỉ phục vụ một nhóm nhỏ. Ngược lại, một cá nhân duy nhất không nên là điểm quyết định duy nhất cho nền tảng có hàng chục nhóm phụ thuộc.

## 4. Vai trò và trách nhiệm

### 4.1. Language Owner

Language Owner chịu trách nhiệm tổng thể:
- Duy trì vision và scope.
- Phê duyệt roadmap.
- Quyết định các thay đổi ảnh hưởng semantics hoặc compatibility.
- Đảm bảo có người phụ trách implementation và documentation.
- Điều phối release và deprecation.
- Báo cáo rủi ro và tình trạng vòng đời.

### 4.2. Language Architect

Language Architect định hướng kiến trúc:
- Grammar và semantics.
- Type system.
- AST/IR.
- Evaluation model.
- Extension API.
- Backend và runtime architecture.
- Compatibility strategy.

### 4.3. Specification Maintainer

Specification Maintainer duy trì văn bản đặc tả:
- Cập nhật grammar.
- Mô tả semantics.
- Quản lý normative và informative text.
- Theo dõi issue và ambiguity.
- Đảm bảo thay đổi spec có version và lịch sử.

### 4.4. Compiler/Runtime Maintainer

Nhóm implementation:
- Duy trì lexer, parser và compiler.
- Duy trì runtime và backend.
- Sửa bug và performance issue.
- Bảo đảm implementation phù hợp spec.
- Cung cấp test và release artifact.

### 4.5. Domain Expert

Domain Expert xác nhận:
- Thuật ngữ nghiệp vụ.
- Invariant.
- Decision semantics.
- Edge case.
- Mức độ phù hợp của DSL với miền.

### 4.6. Documentation Owner

Documentation Owner đảm bảo tutorial, reference, example và migration guide cập nhật theo release.

### 4.7. Security Owner

Security Owner phối hợp threat modeling, security review, vulnerability response, dependency policy và release advisory.

### 4.8. Release Manager

Release Manager quản lý version, release schedule, artifact, signing, changelog, promotion và rollback plan.

### 4.9. Consumer Team

Nhóm sử dụng DSL có trách nhiệm:
- Cung cấp feedback và use case.
- Báo lỗi kèm reproduction.
- Thử nghiệm release candidate.
- Migration theo policy.
- Không phụ thuộc vào undocumented behavior nếu muốn được hỗ trợ lâu dài.

### 4.10. RACI

RACI phân biệt:
- Responsible: người trực tiếp thực hiện.
- Accountable: người chịu trách nhiệm cuối cùng.
- Consulted: người cần được tham vấn.
- Informed: người cần được thông báo.

Ví dụ:

| Hoạt động | Language Owner | Architect | Maintainer | Domain Expert | Security |
|---|---|---|---|---|---|
| Roadmap | A | R | C | C | C |
| Grammar change | A | R | R | C | C |
| Runtime implementation | I | A | R | C | C |
| Domain semantics | A | C | R | R | C |
| Security policy | A | C | R | C | R |
| Release | A | C | R | I | C |
| Deprecation | A | R | C | C | C |

Ma trận cần được điều chỉnh theo tổ chức. Mỗi hoạt động quan trọng nên có đúng một vai trò Accountable để tránh trách nhiệm bị phân tán.

## 5. Language charter

### 5.1. Mục đích

Language charter là văn bản ngắn mô tả vì sao DSL tồn tại, ai sử dụng và các nguyên tắc quản trị cơ bản.

### 5.2. Nội dung

Một charter có thể xác định:
- Tên và mục đích DSL.
- Domain và use case nằm trong scope.
- Use case ngoài scope.
- Nhóm người dùng.
- Language owner và các maintainer.
- Nguyên tắc thiết kế.
- Quy trình thay đổi.
- Chính sách compatibility.
- Lịch phát hành.
- Support window.
- Security contact.
- License và quyền sử dụng.

### 5.3. Design principles

Nguyên tắc có thể gồm:
- Cú pháp ưu tiên rõ ràng và dễ đọc.
- Semantics nhất quán giữa backend.
- Type safety và diagnostics tốt.
- Hạn chế implicit side effect.
- Extension qua API công khai.
- Có khả năng kiểm thử và tái lập.
- Bảo mật mặc định.
- Không thay đổi semantics âm thầm.

### 5.4. Scope boundary

Charter cần nêu những vấn đề DSL giải quyết và những vấn đề nên giao cho ngôn ngữ hoặc nền tảng khác. Nếu scope không rõ, DSL dễ trở thành một ngôn ngữ tổng quát thứ hai với chi phí duy trì lớn.

### 5.5. Charter có thể thay đổi

Charter là tài liệu quản trị, không phải luật bất biến. Thay đổi charter cần được review và ghi lại lý do, tác động và người phê duyệt.

## 6. Quyền quyết định và governance

### 6.1. Decision rights

Cần phân định ai có quyền:
- Đề xuất syntax hoặc semantic change.
- Chấp thuận RFC.
- Thay đổi public API.
- Thêm built-in function.
- Thay đổi plugin contract.
- Phát hành major version.
- Đánh dấu feature deprecated.
- Kết thúc hỗ trợ một version.
- Thay đổi license hoặc trademark policy.

### 6.2. Quyết định theo mức ảnh hưởng

Không phải mọi thay đổi đều cần cùng cấp phê duyệt:
- Sửa typo tài liệu có thể do documentation maintainer duyệt.
- Sửa bug không đổi semantics có thể theo code review thường.
- Thêm syntax có thể cần architect và language owner.
- Breaking change cần impact analysis và phê duyệt chính thức.
- Thay đổi license hoặc quyền sở hữu cần quy trình pháp lý.

### 6.3. Decision log

Mỗi quyết định quan trọng nên ghi:
- ID.
- Ngày.
- Bối cảnh.
- Các lựa chọn.
- Quyết định.
- Lý do.
- Hệ quả.
- Người phê duyệt.
- Phiên bản bắt đầu áp dụng.

### 6.4. Architecture Decision Record

ADR ghi lại quyết định kiến trúc như chọn AST representation, plugin isolation hoặc versioning model. ADR giúp nhóm mới hiểu vì sao thiết kế hiện tại tồn tại.

### 6.5. Escalation

Khi các nhóm không đồng thuận, charter cần chỉ rõ cách đưa vấn đề lên architect hoặc steering group, thời hạn phản hồi và cách ghi nhận quyết định cuối.

### 6.6. Tránh quyết định qua trao đổi riêng

Quyết định ảnh hưởng người dùng nên được ghi ở nơi có thể tìm kiếm và review. Nếu quyết định chỉ tồn tại trong chat hoặc email cá nhân, nhóm khác khó biết semantics chính thức.

## 7. Quy trình đề xuất thay đổi ngôn ngữ

### 7.1. Change proposal

Đề xuất cần nêu:
- Vấn đề hiện tại.
- Use case và ví dụ.
- Hành vi mong muốn.
- Cú pháp hoặc API dự kiến.
- Ảnh hưởng đến semantics.
- Compatibility impact.
- Tác động đến compiler, runtime và tooling.
- Tác động security/performance.
- Các lựa chọn đã cân nhắc.

### 7.2. RFC

RFC (Request for Comments) là tài liệu đề xuất để cộng đồng hoặc các nhóm liên quan thảo luận. RFC nên có trạng thái như Draft, In Review, Accepted, Rejected hoặc Withdrawn.

### 7.3. Review

Review có thể gồm:
- Language design.
- Domain correctness.
- Implementation feasibility.
- Security.
- Performance.
- Documentation.
- Migration impact.

### 7.4. Prototype

Với thay đổi lớn, prototype có thể chứng minh cú pháp và semantics trước khi cam kết đưa vào spec. Prototype không tự động trở thành chuẩn.

### 7.5. Decision

Người có quyền quyết định ghi rõ chấp nhận, từ chối hoặc yêu cầu sửa. Nếu chấp nhận, cần ghi target version và các bước tiếp theo.

### 7.6. Implementation và spec alignment

Đặc tả, compiler, runtime, test và documentation cần được cập nhật theo cùng một change proposal. Không phát hành implementation có semantics chưa được mô tả.

### 7.7. Feedback sau release

Sau khi release, theo dõi issue và usage để biết thay đổi có đạt mục tiêu hay tạo tác dụng phụ. Nếu cần điều chỉnh, tạo proposal mới thay vì thay đổi ngầm.

## 8. Quản trị đặc tả và semantics

### 8.1. Một nguồn sự thật

Cần xác định tài liệu nào là normative specification. Tutorial và blog có thể giải thích nhưng không nên mâu thuẫn với đặc tả chính thức.

### 8.2. Normative và informative

Normative text quy định hành vi implementation phải tuân thủ. Informative text giải thích, đưa ví dụ hoặc gợi ý. Phân biệt hai loại giúp tránh việc ví dụ bị hiểu nhầm thành yêu cầu bắt buộc.

### 8.3. Grammar version

Grammar cần được version hóa. Thay đổi lexical token, precedence hoặc parsing rule có thể ảnh hưởng source cũ.

### 8.4. Semantic specification

Cần mô tả rõ:
- Evaluation order.
- Short-circuit behavior.
- Numeric precision và overflow.
- Null semantics.
- Error propagation.
- Side effect.
- Scope và name resolution.
- Concurrency nếu có.
- Serialization semantics.

### 8.5. Undefined behavior

Không nên để hành vi quan trọng ở trạng thái undefined. Nếu một trường hợp chưa được quy định, cần quyết định từ chối, cảnh báo hoặc xác định semantics trước khi nhiều implementation diễn giải khác nhau.

### 8.6. Reference examples

Ví dụ chính thức nên có expected output hoặc test để ngăn tài liệu và implementation lệch nhau.

### 8.7. Conformance suite

Một bộ test chuẩn có thể xác định implementation nào tuân thủ spec. Nếu có nhiều compiler hoặc runtime, conformance suite giúp kiểm tra semantics nhất quán.

## 9. Quản trị implementation và nhiều backend

### 9.1. Reference implementation

Reference implementation là implementation được dùng làm điểm tham chiếu để giải thích và kiểm tra spec. Nó không nhất thiết là implementation nhanh nhất hoặc duy nhất.

### 9.2. Multiple implementations

Nếu có nhiều compiler hoặc runtime, owner cần xác định:
- Implementation nào được hỗ trợ.
- Phiên bản nào tuân thủ spec.
- Feature nào còn experimental.
- Hành vi khác nhau có được phép không.
- Ai xử lý bug khác biệt.

### 9.3. Conformance level

Có thể phân loại:
- Core conformance.
- Optional capability.
- Experimental extension.
- Deprecated feature.

### 9.4. Backend equivalence

Cùng một chương trình DSL cần có kết quả tương đương trên backend được công bố hỗ trợ, trừ những khác biệt được spec cho phép.

### 9.5. Toolchain support

Compiler, formatter, linter, debugger và language server cần có compatibility matrix. Không nên để mỗi công cụ hỗ trợ một grammar version không được công bố.

### 9.6. Test corpus

Owner duy trì test corpus gồm source hợp lệ, source không hợp lệ, expected diagnostics và expected runtime result. Corpus cần được version hóa cùng spec.

## 10. Versioning và compatibility policy

### 10.1. Version của ngôn ngữ

Language version nhận diện grammar và semantics. Nó có thể khác product version hoặc compiler version.

### 10.2. Semantic versioning

Nếu dùng SemVer:
- MAJOR: thay đổi không tương thích.
- MINOR: thêm tính năng tương thích ngược.
- PATCH: sửa lỗi không đổi contract công khai.

Cần định nghĩa cụ thể thế nào là compatibility trong DSL; sửa bug có thể làm thay đổi kết quả của source dựa vào behavior cũ.

### 10.3. Source compatibility

Source compatibility xác định chương trình cũ có còn parse và compile trên version mới hay không.

### 10.4. Behavioral compatibility

Behavioral compatibility xác định chương trình vẫn cho kết quả và side effect như trước. Source parse được không đồng nghĩa hành vi giữ nguyên.

### 10.5. Binary và runtime compatibility

Artifact đã compile có thể phụ thuộc IR format, bytecode, runtime API và plugin API. Cần policy riêng cho từng lớp.

### 10.6. Compatibility matrix

| Thành phần | Câu hỏi |
|---|---|
| Source DSL | Version mới có parse source cũ không? |
| Compiler | Compiler mới có giữ semantics không? |
| IR/bytecode | Runtime mới có đọc artifact cũ không? |
| Plugin API | Plugin cũ có chạy được không? |
| Schema | Payload/model cũ có còn hợp lệ không? |
| Tooling | Formatter và language server có hỗ trợ grammar không? |

### 10.7. Compatibility promise

Owner cần công bố thời gian hỗ trợ, mức tương thích và trường hợp ngoại lệ. Không nên hứa backward compatibility vô hạn nếu tổ chức không có nguồn lực duy trì.

## 11. Roadmap và quản lý ưu tiên

### 11.1. Roadmap

Roadmap mô tả hướng phát triển theo giai đoạn:
- Năng lực core.
- Cải thiện tooling.
- Plugin ecosystem.
- Runtime và backend.
- Bảo mật và compliance.
- Migration và deprecation.

### 11.2. Prioritization

Có thể đánh giá đề xuất theo:
- Giá trị cho người dùng.
- Số nhóm bị ảnh hưởng.
- Mức độ rủi ro.
- Chi phí implementation.
- Tác động compatibility.
- Tính phù hợp với scope.
- Khả năng duy trì lâu dài.

### 11.3. Không chạy theo mọi feature request

Một DSL có thể trở nên khó học và khó duy trì nếu thêm mọi yêu cầu. Owner cần xem một yêu cầu có thuộc miền mục tiêu hay nên giải quyết bằng library, plugin hoặc API bên ngoài.

### 11.4. Public roadmap

Với dự án mở hoặc nền tảng dùng chung, public roadmap giúp consumer chuẩn bị và đóng góp. Roadmap cần phân biệt committed, planned và exploratory.

### 11.5. Capacity planning

Roadmap phải tính nguồn lực cho bug fixing, security, support và documentation, không chỉ feature mới.

## 12. Release management

### 12.1. Release train

Release train xác định nhịp phát hành, ví dụ theo quý hoặc theo milestone. Nhịp ổn định giúp consumer lên kế hoạch nâng cấp.

### 12.2. Release candidate

RC cho phép nhóm dùng thử trước khi phát hành stable. Phản hồi từ RC có thể phát hiện compatibility hoặc migration issue.

### 12.3. Release notes

Release notes cần nêu:
- Feature mới.
- Bug fix.
- Thay đổi semantics.
- Breaking changes.
- Deprecated feature.
- Security fix.
- Migration action.
- Known issue.

### 12.4. Artifact provenance

Release cần ghi source revision, compiler/build version, dependency và pipeline identity. Artifact đã phát hành nên bất biến.

### 12.5. Signing và distribution

Package cần checksum và chữ ký theo policy. Quyền publish và signing key cần được bảo vệ.

### 12.6. Rollback

Cần xác định cách quay về release trước, đặc biệt khi release mới thay schema, IR hoặc persisted state.

### 12.7. Support matrix

Công bố version đang active, maintenance, security-only và end-of-life. Consumer cần biết version nào còn nhận bug fix và security update.

## 13. Deprecation và migration

### 13.1. Deprecation là gì?

Deprecation thông báo một cú pháp, API hoặc tính năng không còn được khuyến nghị và dự kiến bị loại bỏ trong tương lai. Nó tạo thời gian để consumer chuyển đổi.

### 13.2. Quy trình deprecation

Một quy trình có thể:
1. Xác định lý do.
2. Phân tích usage.
3. Đề xuất thay thế.
4. Thông báo trước.
5. Thêm warning hoặc diagnostic.
6. Cung cấp migration guide.
7. Theo dõi adoption.
8. Loại bỏ theo policy đã công bố.

### 13.3. Không deprecate âm thầm

Consumer cần biết version bắt đầu cảnh báo, version dự kiến loại bỏ và thời hạn hỗ trợ. Release notes và diagnostics phải nhất quán.

### 13.4. Migration tooling

Có thể cung cấp codemod hoặc migration tool để chuyển source cũ sang cú pháp mới. Tool cần có dry-run, diff và backup.

### 13.5. Automated migration tests

Test migration trên corpus source thực tế, kiểm tra cú pháp mới parse được và semantics giữ nguyên trong phạm vi cam kết.

### 13.6. Sunset policy

Sunset policy quy định khoảng thời gian tối thiểu từ deprecation đến removal. Với DSL được nhúng trong sản phẩm khách hàng, khoảng thời gian có thể cần dài hơn một thư viện nội bộ.

## 14. Security ownership

### 14.1. Ai chịu trách nhiệm?

Cần chỉ định security contact hoặc team chịu trách nhiệm:
- Nhận vulnerability report.
- Đánh giá mức độ.
- Phối hợp maintainer.
- Chuẩn bị patch.
- Phát hành advisory.
- Theo dõi dependency và runtime.

### 14.2. Threat model

Threat model cần xem xét:
- DSL source không tin cậy.
- Plugin.
- Expression evaluation.
- Data access.
- File và network.
- Deserialization.
- Resource exhaustion.
- Tenant isolation.

### 14.3. Security response

Quy trình xử lý lỗ hổng cần xác định severity, thời gian phản hồi, cách phối hợp disclosure và cách phát hành patch.

### 14.4. Security support window

Version đã hết hỗ trợ có thể không nhận security fix. Owner cần công bố rõ và khuyến nghị nâng cấp.

### 14.5. Dependency policy

Compiler và runtime phụ thuộc parser generator, database driver, template engine hoặc plugin framework. Cần theo dõi vulnerability và có quy trình cập nhật.

### 14.6. Security decision log

Quyết định tắt một tính năng, thay default hoặc giới hạn capability nên được ghi lại cùng lý do và tác động.

## 15. Documentation và developer experience ownership

### 15.1. Tài liệu là một phần của sản phẩm

Một DSL khó sử dụng nếu grammar đúng nhưng tài liệu không giải thích cách dùng. Documentation owner cần cập nhật cùng release.

### 15.2. Các loại tài liệu

- Getting started.
- Language reference.
- Type system guide.
- Standard library reference.
- API/plugin guide.
- Security guide.
- Migration guide.
- Troubleshooting.
- Release notes.

### 15.3. Ví dụ executable

Ví dụ nên được chạy tự động trong CI hoặc documentation build. Điều này tránh ví dụ cũ không còn compile.

### 15.4. Feedback loop

Issue tracker, forum, internal support channel và user interview giúp owner hiểu nơi người dùng gặp khó khăn.

### 15.5. Support boundary

Công bố phần nào được hỗ trợ chính thức, phần nào là community/experimental và cách báo lỗi.

### 15.6. Accessibility và localization

Nếu DSL có editor hoặc workbench, owner cần xem xét accessibility, keyboard navigation và tài liệu đa ngôn ngữ theo nhu cầu.

## 16. Intellectual property và licensing

### 16.1. Quyền đối với source và đặc tả

Cần biết ai sở hữu:
- Source code.
- Grammar và specification.
- Documentation.
- Test corpus.
- Logo và tên.
- Plugin do cộng đồng đóng góp.
- Generated artifact.

### 16.2. Copyright

Copyright xác định quyền sao chép, sửa đổi và phân phối tác phẩm. Người đóng góp cần hiểu điều khoản áp dụng cho code và tài liệu.

### 16.3. License

License quy định quyền sử dụng, phân phối và nghĩa vụ đi kèm. Có thể là open source license, commercial license hoặc license nội bộ.

### 16.4. Contribution agreement

Dự án có thể dùng Contributor License Agreement (CLA) hoặc Developer Certificate of Origin (DCO) để làm rõ quyền đóng góp. Lựa chọn cần phù hợp policy của tổ chức.

### 16.5. Trademark

Tên DSL và logo có thể được bảo hộ như trademark. Quyền sử dụng tên không nhất thiết giống quyền sử dụng source code.

### 16.6. Third-party component

Compiler hoặc runtime có thể chứa parser generator, library và plugin từ bên thứ ba. Cần kiểm tra license compatibility và giữ notices theo nghĩa vụ.

### 16.7. Customer extension

Hợp đồng cần xác định quyền đối với DSL model, plugin và extension do khách hàng tạo. Không mặc định công ty sở hữu mọi nội dung do khách hàng viết.

### 16.8. Legal review

Thay đổi license, chuyển repository hoặc phân phối binary có thể cần review pháp lý. Language owner phối hợp nhưng không tự thay thế vai trò pháp lý.

## 17. Community và đóng góp

### 17.1. Contribution guide

Nêu cách mở issue, tạo proposal, gửi pull request, chạy test và tuân thủ code style.

### 17.2. Code of conduct

Dự án cộng đồng cần quy tắc ứng xử và quy trình xử lý vi phạm để giữ môi trường cộng tác an toàn.

### 17.3. Review policy

Xác định ai có quyền approve và merge, yêu cầu review cho spec change và cách xử lý khi reviewer không đồng thuận.

### 17.4. Maintainer succession

Không để một người duy nhất nắm toàn bộ quyền phát hành hoặc kiến thức. Có maintainer dự phòng và quy trình chuyển giao quyền.

### 17.5. Community feedback

Theo dõi issue, discussion, adoption và plugin ecosystem. Cần phân biệt số lượng yêu cầu với nhu cầu có giá trị dài hạn.

### 17.6. Governance transparency

Ghi decision, roadmap và release plan ở nơi người liên quan có thể truy cập theo policy.

## 18. Quản trị rủi ro key-person dependency

### 18.1. Bus factor

Bus factor thấp khi chỉ một hoặc hai người biết cách build, release hoặc giải thích semantics quan trọng. Nếu họ rời nhóm, DSL có thể ngừng phát triển.

### 18.2. Documentation of operations

Ghi rõ cách:
- Build compiler.
- Tạo release.
- Ký package.
- Cập nhật registry.
- Phục hồi build.
- Xử lý security report.
- Thực hiện migration.

### 18.3. Shared ownership

Có ít nhất hai maintainer hiểu mỗi thành phần quan trọng. Review và pair work giúp phân tán kiến thức.

### 18.4. Succession plan

Chỉ định người hoặc nhóm kế nhiệm nếu owner rời vai trò. Quyền repository, registry, signing và domain knowledge cần có cách chuyển giao.

### 18.5. Access recovery

Tài khoản dịch vụ, signing key và registry access cần được quản lý bằng tổ chức, không gắn với tài khoản cá nhân duy nhất.

## 19. Lifecycle và end-of-life

### 19.1. Các giai đoạn vòng đời

Một DSL có thể trải qua:
1. Incubation: thử nghiệm ý tưởng.
2. Experimental: có người dùng nhưng API còn thay đổi.
3. Stable: semantics và support được cam kết.
4. Maintenance: chủ yếu sửa lỗi và bảo mật.
5. Deprecated: khuyến nghị chuyển đổi.
6. End-of-life: ngừng hỗ trợ.

### 19.2. Tiêu chí chuyển giai đoạn

Dựa trên:
- Mức độ ổn định.
- Số consumer.
- Test và documentation.
- Năng lực support.
- Security posture.
- Roadmap.
- Khả năng thay thế.

### 19.3. End-of-life

Thông báo EOL cần nêu:
- Version bị ảnh hưởng.
- Ngày kết thúc hỗ trợ.
- Security update cuối cùng nếu biết.
- Đường nâng cấp.
- Export hoặc migration option.
- Nơi lưu artifact và documentation.

### 19.4. Archival

Khi ngừng phát triển, lưu source, spec, build instructions, release artifacts và decision history. Repository có thể chuyển read-only.

### 19.5. Abandonment

Nếu không còn nguồn lực, tổ chức cần quyết định chuyển ownership, fork, chuyển sang dự án khác hoặc ngừng sử dụng. Không nên để sản phẩm ở trạng thái không ai chịu trách nhiệm nhưng vẫn được coi là supported.

### 19.6. Data and model continuity

Nếu DSL lưu model hoặc dữ liệu quan trọng, EOL cần có export format và thời gian chuyển đổi để consumer không mất khả năng đọc tài sản cũ.

## 20. Đo lường hiệu quả governance

### 20.1. Adoption

Theo dõi số dự án, nhóm, model, plugin hoặc execution đang sử dụng DSL. Số lượng cần được diễn giải theo phạm vi và mức độ hoạt động.

### 20.2. Change lead time

Đo thời gian từ proposal đến decision và từ decision đến release. Thời gian quá dài có thể cho thấy governance bottleneck.

### 20.3. Compatibility incidents

Theo dõi số lỗi do breaking change, migration thất bại hoặc compiler/runtime mismatch.

### 20.4. Support health

Đo thời gian phản hồi issue, số issue tồn đọng, thời gian sửa bug và thời gian xử lý vulnerability.

### 20.5. Release health

Theo dõi release frequency, rollback, hotfix và mức độ sử dụng release candidate.

### 20.6. Documentation health

Theo dõi ví dụ không chạy được, tài liệu thiếu version và câu hỏi hỗ trợ lặp lại.

### 20.7. Ownership health

Theo dõi số maintainer, bus factor, quyền truy cập dự phòng và trạng thái succession plan.

### 20.8. Metrics không phải mục tiêu tự thân

Không tối ưu số lượng release hoặc issue đóng nếu điều đó làm giảm chất lượng quyết định. Metrics cần giúp phát hiện vấn đề và hỗ trợ thảo luận, không thay thế judgment.

## 21. Ví dụ: mô hình ownership cho DSL chính sách nội bộ

Giả sử một tổ chức có DSL dùng chung để mô tả chính sách đơn hàng, thanh toán và phê duyệt.

### 21.1. Cấu trúc vai trò

- Platform Language Team giữ grammar, compiler, runtime và plugin API.
- Domain Council đại diện nhóm thương mại, thanh toán và rủi ro.
- Security Owner quản lý threat model và vulnerability response.
- Documentation Maintainer duy trì reference và migration guide.
- Release Manager phát hành compiler/runtime và package.

### 21.2. Quyền quyết định

Thay đổi spelling hoặc typo trong tài liệu do maintainer xử lý. Thêm built-in function cần RFC và domain review. Thay đổi evaluation order cần architect, owner và domain council phê duyệt vì có thể ảnh hưởng kết quả hiện tại.

### 21.3. Release policy

DSL có major version khi thay semantics không tương thích. Minor version thêm feature mới không phá source cũ. Patch version sửa lỗi. Runtime và plugin API có version riêng nhưng công bố compatibility matrix.

### 21.4. Deprecation

Nếu một built-in function cũ không còn phù hợp:
1. Công bố replacement.
2. Thêm warning từ một version.
3. Cung cấp migration example hoặc codemod.
4. Theo dõi usage.
5. Loại bỏ trong major version theo support policy.

### 21.5. Succession

Có ít nhất hai maintainer có quyền release. Build pipeline, signing key và registry access do tổ chức quản lý. Decision log và conformance suite được lưu trong repository.

Mô hình này giúp các nhóm miền đóng góp kiến thức mà vẫn giữ một bộ semantics thống nhất.

## 22. Những sai lầm thường gặp

### 22.1. Không chỉ định owner

Khi không ai accountable, quyết định bị trì hoãn hoặc mỗi nhóm tự làm theo cách riêng. Cần ghi owner và người thay thế.

### 22.2. Một người kiểm soát mọi thứ

Một cá nhân duy nhất có thể trở thành bottleneck và single point of failure. Cần phân quyền theo lĩnh vực và chia sẻ kiến thức.

### 22.3. Nhầm implementation với đặc tả

Hành vi hiện tại của compiler không nhất thiết là semantics chính thức. Cần normative specification và conformance tests.

### 22.4. Thay đổi không có RFC hoặc decision record

Thay đổi quan trọng qua commit riêng lẻ khiến consumer không biết lý do và tác động. Cần quy trình tương xứng với mức rủi ro.

### 22.5. Không quản lý compatibility

Thêm cú pháp hoặc đổi semantics có thể làm source cũ thay kết quả. Cần compatibility matrix, deprecation và migration policy.

### 22.6. Không có security owner

Lỗ hổng trong parser, runtime hoặc plugin có thể không được xử lý đúng thời hạn. Cần security contact và response process.

### 22.7. Không duy trì tài liệu

Tài liệu lỗi thời làm người dùng dựa vào behavior không còn được hỗ trợ. Documentation cần được release cùng implementation.

### 22.8. Không có succession plan

Nếu chỉ một người biết cách phát hành hoặc giải thích semantics, DSL có thể bị đình trệ khi người đó rời tổ chức.

### 22.9. Không xác định quyền sở hữu trí tuệ

Code, spec và plugin có thể chịu license khác nhau. Không làm rõ quyền đóng góp và phân phối có thể tạo rủi ro pháp lý.

### 22.10. Không công bố EOL

Người dùng có thể tiếp tục triển khai version không còn security update. EOL cần được thông báo sớm và có migration path.

## 23. Quy trình thiết lập language ownership

Một quy trình triển khai có thể gồm:
1. **Lập inventory tài sản:** spec, source, compiler, runtime, plugin, tooling, docs và registry.
2. **Xác định mục tiêu và scope:** DSL phục vụ miền nào, nhóm người dùng nào và những gì nằm ngoài scope.
3. **Chỉ định accountable owner:** có người chịu trách nhiệm cuối cùng và người dự phòng.
4. **Phân vai maintainer:** architect, spec, implementation, security, documentation và release.
5. **Viết language charter:** mục tiêu, design principles, compatibility và support policy.
6. **Thiết lập governance:** RFC, review, decision rights, ADR và escalation.
7. **Quản lý đặc tả:** normative spec, grammar version và conformance suite.
8. **Thiết lập release policy:** versioning, release train, RC, artifact signing và rollback.
9. **Thiết lập security process:** vulnerability reporting, response và dependency policy.
10. **Thiết lập contribution/IP policy:** license, CLA/DCO và quyền đối với extension.
11. **Quản lý deprecation/EOL:** notice period, migration tooling và archival.
12. **Giảm key-person risk:** nhiều maintainer, runbook và access recovery.
13. **Theo dõi metrics:** adoption, compatibility, support, release và ownership health.
14. **Review governance định kỳ:** điều chỉnh vai trò khi quy mô hoặc mức độ quan trọng của DSL thay đổi.

## 24. Câu hỏi tự đánh giá

1. Language ownership khác authorship và maintenance như thế nào?
2. Những tài sản nào thuộc phạm vi ownership của một DSL?
3. Centralized, federated và community governance khác nhau ra sao?
4. Language Owner, Architect và Specification Maintainer có trách nhiệm gì?
5. Language charter cần mô tả những nội dung nào?
6. Decision rights giúp tránh tình trạng gì?
7. RFC và ADR được dùng trong những trường hợp nào?
8. Vì sao cần phân biệt normative specification với tutorial?
9. Reference implementation và conformance suite hỗ trợ governance như thế nào?
10. Source compatibility khác behavioral compatibility ra sao?
11. Deprecation cần có những bước nào?
12. Ai chịu trách nhiệm security response?
13. CLA, DCO và license giải quyết những vấn đề gì?
14. Bus factor thấp tạo rủi ro gì cho DSL?
15. End-of-life cần thông báo và lưu trữ những gì?
16. Metrics nào giúp đánh giá sức khỏe governance?

## Kết luận

Sở hữu ngôn ngữ là mô hình trách nhiệm đối với toàn bộ vòng đời của DSL: từ mục tiêu, đặc tả, implementation và tooling đến compatibility, security, support và end-of-life. Language owner cần có quyền quyết định rõ, nhưng công việc được chia sẻ với architect, maintainer, domain expert, security owner, documentation owner và release manager.

Một mô hình ownership bền vững có language charter, nguồn đặc tả chính thức, quy trình RFC và decision record, versioning policy, conformance suite, release process, security response và kế hoạch succession. Deprecation và EOL phải được công bố với thời gian chuyển đổi phù hợp. Khi trách nhiệm, quyền quyết định và lịch sử thay đổi minh bạch, DSL có thể phát triển theo nhu cầu người dùng mà vẫn giữ semantics nhất quán, giảm rủi ro phụ thuộc cá nhân và duy trì được giá trị lâu dài cho tổ chức.
