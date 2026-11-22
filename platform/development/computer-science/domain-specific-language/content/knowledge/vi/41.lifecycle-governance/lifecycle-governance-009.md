# Kế hoạch ngừng dùng

Trong quản trị vòng đời của ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **kế hoạch ngừng dùng (deprecation plan)** là kế hoạch có kiểm soát để đưa một cú pháp, API, schema, plugin, provider hoặc capability ra khỏi phạm vi hỗ trợ. Kế hoạch mô tả vì sao cần ngừng dùng, ai và hệ thống nào bị ảnh hưởng, lựa chọn thay thế, thời gian chuyển tiếp, cách di trú, tiêu chí sẵn sàng loại bỏ và quy trình xử lý rủi ro.

Đánh dấu một tính năng là deprecated chỉ là bước thông báo. Để thực sự loại bỏ nó, nhóm phát triển cần biết nơi nó đang được sử dụng, consumer nào còn phụ thuộc, replacement đã đủ khả năng chưa, migration có giữ nguyên semantics hay không và việc xóa có làm hỏng pipeline hoặc project đang vận hành không. Một kế hoạch tốt biến quyết định kỹ thuật thành chuỗi công việc có owner, mốc thời gian và bằng chứng hoàn tất.

Ví dụ, DSL từng hỗ trợ directive legacyHealthCheck nhưng nay có cấu trúc healthProbe rõ ràng hơn. Kế hoạch ngừng dùng cần xác định version bắt đầu cảnh báo, compiler nào còn chấp nhận directive cũ, project nào đang sử dụng, quick fix có chuyển đổi an toàn không, khi nào strict mode được bật và version nào sẽ loại bỏ hẳn. Nếu directive cũ được dùng trong hàng trăm repository hoặc template, chỉ phát warning rồi xóa ở release kế tiếp có thể tạo gián đoạn lớn.

~~~mermaid
flowchart TD
    A[Identify candidate] --> B[Assess impact and alternatives]
    B --> C[Approve deprecation plan]
    C --> D[Announce and mark deprecated]
    D --> E[Support migration]
    E --> F[Measure adoption and readiness]
    F --> G{Removal criteria met?}
    G -->|No| E
    G -->|Yes| H[Remove in planned release]
    H --> I[Verify and close lifecycle]
~~~

## 1. Kế hoạch ngừng dùng là gì?

Deprecation plan là tài liệu và quy trình quản trị vòng đời của một thành phần đã hoặc sẽ bị ngừng hỗ trợ. Nó kết nối quyết định thiết kế với công việc thực tế của consumer.

### 1.1. Mục tiêu

Mục tiêu là loại bỏ thành phần cũ theo cách có thể dự đoán, giảm rủi ro breaking change, cung cấp lối chuyển đổi rõ ràng và tránh duy trì compatibility code vô thời hạn.

### 1.2. Phạm vi

Kế hoạch có thể áp dụng cho một keyword, field, type, function, plugin API, generated class, CLI option, event contract, endpoint hoặc toàn bộ integration provider.

### 1.3. Artifact quản trị

Một plan thường gồm rationale, scope, owner, consumer inventory, replacement, compatibility behavior, timeline, migration steps, communication plan, readiness criteria, rollback/mitigation và removal checklist.

### 1.4. Kế hoạch khác với marker

Marker là metadata gắn vào phần tử và được hiển thị trong compiler hoặc IDE. Plan mô tả toàn bộ hoạt động cần thiết để đưa phần tử qua các trạng thái deprecated, sunset và removed.

### 1.5. Kế hoạch khác với release note

Release note thông báo một thay đổi trong một bản phát hành. Deprecation plan quản lý nhiều release và nhiều nhóm consumer xuyên suốt thời gian chuyển tiếp.

## 2. Khi nào cần lập kế hoạch ngừng dùng?

Không phải mọi thay đổi nhỏ đều cần một quy trình lớn. Kế hoạch chính thức đặc biệt cần thiết khi thành phần có consumer, trạng thái bền vững hoặc tác động vận hành.

### 2.1. Cú pháp hoặc API không còn phù hợp

Một cú pháp cũ có thể khó hiểu, trùng lặp hoặc cản trở phát triển ngôn ngữ. Plan giúp chuyển consumer sang model mới.

### 2.2. Thay đổi kiến trúc

Một provider, plugin interface hoặc transport cũ có thể được thay bằng kiến trúc mới. Cần quản lý cả source configuration, runtime và deployment.

### 2.3. Vấn đề bảo mật

Một option hoặc API có thể cho phép hành vi không an toàn. Kế hoạch có thể cần thời gian chuyển tiếp ngắn, mitigation ngay và removal sớm hơn lịch thông thường.

### 2.4. Dependency upstream hết hỗ trợ

Thư viện, protocol hoặc service bên ngoài có thể bị ngừng hỗ trợ. DSL cần có kế hoạch thay dependency và kiểm tra compatibility.

### 2.5. Schema hoặc contract tiến hóa

Field, event type hoặc endpoint có thể được thay bằng contract mới. Consumer có thể nâng cấp độc lập nên cần inventory và migration coordination.

### 2.6. Chi phí bảo trì quá cao

Một legacy path ít người dùng nhưng làm tăng code, test matrix và support burden có thể được lên kế hoạch loại bỏ.

### 2.7. Thay đổi sản phẩm hoặc policy

Một capability có thể không còn phù hợp với định hướng sản phẩm hoặc policy tổ chức. Plan cần giải thích tác động đến người dùng hiện tại.

## 3. Nguyên tắc lập kế hoạch

Một kế hoạch hiệu quả cân bằng tính minh bạch, an toàn, khả năng di trú và chi phí duy trì.

### 3.1. Consumer-first

Bắt đầu từ hệ thống và người dùng bị ảnh hưởng. Không quyết định removal chỉ dựa trên việc code nội bộ đã được thay thế.

### 3.2. Replacement trước removal

Khi có thể, làm cho replacement sẵn sàng và được kiểm chứng trước khi bắt đầu thời gian chuyển tiếp.

### 3.3. Mốc rõ ràng

Nêu version deprecated, mốc migration, version hoặc ngày removal và support window. Nếu mốc chưa xác định, ghi rõ điều kiện để xác định.

### 3.4. Tính tương thích được công bố

Mô tả chính xác phiên bản compiler/runtime nào vẫn đọc hoặc chạy được cấu hình cũ và khi nào hành vi thay đổi.

### 3.5. Di trú có thể kiểm chứng

Không chỉ yêu cầu người dùng “chuyển sang API mới”. Cần có migration guide, tool, test và tiêu chí chứng minh behavior tương đương.

### 3.6. Có owner và quyết định

Mỗi action cần owner. Mỗi ngoại lệ cần người phê duyệt. Không để một kế hoạch tồn tại nhưng không ai chịu trách nhiệm cập nhật.

### 3.7. An toàn khi không chắc chắn

Nếu chưa biết consumer hoặc tác động, mở rộng assessment và giữ compatibility trong phạm vi được hỗ trợ. Không coi thiếu dữ liệu là không có rủi ro.

### 3.8. Không kéo dài vô hạn

Compatibility layer cần thời hạn hoặc điều kiện removal. Nếu phải kéo dài, ghi lý do, owner và quyết định mới.

## 4. Xác định đối tượng và phạm vi ngừng dùng

Trước tiên cần xác định chính xác phần tử nào bị loại bỏ và những hành vi liên quan.

### 4.1. Element identity

Dùng ID ổn định, namespace, element kind và version range. Tránh chỉ ghi tên hiển thị nếu tên có thể trùng.

### 4.2. Public và internal surface

Phân biệt API public, internal API, experimental feature và extension point. Public surface thường có cam kết hỗ trợ rộng hơn.

### 4.3. Source-level scope

Liệt kê keyword, directive, field, type, function, annotation và syntax form liên quan.

### 4.4. Runtime scope

Xác định runtime behavior, generated code, service adapter, plugin, provider và external dependency nào bị ảnh hưởng.

### 4.5. Tooling scope

Kiểm tra parser, formatter, IDE completion, CLI, migration tool, schema registry, documentation generator và CI rules.

### 4.6. Version scope

Ghi các phiên bản DSL, compiler, runtime và plugin đang nhận diện thành phần. Cùng một element có thể có lifecycle khác nhau theo version.

### 4.7. Explicit exclusions

Nêu những trường hợp không nằm trong plan, ví dụ nhánh LTS, API nội bộ không public hoặc integration vẫn được hỗ trợ theo hợp đồng riêng.

## 5. Rationale và mục tiêu thay đổi

Người dùng cần hiểu lý do thay đổi để đánh giá mức ưu tiên và rủi ro migration.

### 5.1. Problem statement

Mô tả vấn đề cụ thể của thành phần cũ: semantics mơ hồ, khó mở rộng, thiếu bảo mật, phụ thuộc công nghệ hết hỗ trợ hoặc gây lỗi thường xuyên.

### 5.2. Desired outcome

Nêu trạng thái mong muốn sau removal: một API thống nhất, type-safe hơn, ít dependency hơn hoặc policy an toàn hơn.

### 5.3. Alternatives considered

Ghi các phương án đã cân nhắc như giữ nguyên, sửa semantics, thêm alias hoặc thay hoàn toàn. Nêu trade-off quan trọng.

### 5.4. User impact

Giải thích việc thay đổi ảnh hưởng đến source, build, runtime, deployment, data migration và vận hành ra sao.

### 5.5. Success measure

Có thể dùng số project đã di trú, số consumer còn dùng, tỷ lệ build warning, số exception hoặc mức giảm support burden.

### 5.6. Non-goals

Nêu phần không được giải quyết trong đợt này để tránh plan bị mở rộng không kiểm soát.

## 6. Consumer inventory và dependency discovery

Đây thường là bước quan trọng nhất. Không thể lập timeline thực tế nếu không biết ai đang dùng thành phần.

### 6.1. Repository search

Tìm identifier, syntax pattern, package coordinate, CLI flag hoặc schema field trong repository được quản lý.

### 6.2. Static analysis

Dùng parser hoặc semantic index để tìm usage chính xác, tránh nhầm comment, string literal và tên tương tự.

### 6.3. Build telemetry

Compiler có thể tổng hợp deprecation diagnostic theo project hoặc CI job. Thu thập cần tuân thủ privacy và policy nội bộ.

### 6.4. Runtime telemetry

Với API hoặc provider, telemetry có thể xác định consumer thực sự gọi tính năng. Cần xác định phạm vi dữ liệu và retention.

### 6.5. Consumer registry

Event/API catalog hoặc plugin registry có thể liệt kê consumer đã đăng ký. Registry cần được duy trì và kiểm tra tính đầy đủ.

### 6.6. Generated and vendored usage

Usage có thể nằm trong code được sinh, repository mirror, template, sample hoặc vendored package. Cần xác định ai sở hữu và cách cập nhật.

### 6.7. External consumers

Public DSL hoặc integration có thể được dùng ngoài tổ chức. Không thể dựa hoàn toàn vào repository nội bộ để kết luận đã hết usage.

### 6.8. Confidence level

Ghi rõ inventory đầy đủ đến mức nào, dữ liệu được lấy từ đâu và khoảng mù còn lại. Một danh sách “không tìm thấy” không đồng nghĩa không có consumer.

## 7. Phân tích tác động

Impact analysis đánh giá thay đổi lan đến thành phần, nhóm và quy trình nào.

### 7.1. Source compatibility

Xác định source cũ có parse/compile được trên version mới không, warning xuất hiện ở đâu và replacement có thể chuyển tự động không.

### 7.2. Binary compatibility

Nếu generated code hoặc runtime API được compile thành artifact, removal có thể làm consumer binary không liên kết được. Cần đánh giá ABI và runtime linkage.

### 7.3. Configuration compatibility

File cấu hình cũ có được đọc không? Nếu được, nó có được normalize sang model mới và có giữ nguyên behavior không?

### 7.4. Data compatibility

Schema hoặc database migration có thể cần chuyển dữ liệu đã lưu. Đánh giá field cũ, default, nullability, backfill và rollback.

### 7.5. Runtime behavior

Replacement có thể thay đổi timeout, ordering, retry, error handling hoặc default. Cần so sánh behavior chứ không chỉ source syntax.

### 7.6. Operational impact

Đánh giá downtime, rollout order, credential, monitoring, alert, runbook và khả năng rollback.

### 7.7. Ecosystem impact

Plugin author, IDE extension, generator, tutorial, template và đối tác có thể cần thay đổi. Liệt kê các nhóm này trong plan.

### 7.8. Risk classification

Có thể phân loại low, medium, high hoặc critical dựa trên số consumer, mức độ ảnh hưởng, khả năng rollback và hậu quả khi migration sai.

## 8. Đánh giá replacement

Không nên bắt đầu đếm ngược removal nếu replacement chưa đáp ứng các use case cần thiết.

### 8.1. Feature parity

So sánh khả năng của API cũ và mới. Nêu rõ chức năng nào tương đương, chức năng nào thay đổi và chức năng nào chưa có.

### 8.2. Semantic differences

Xác định khác biệt về default, error behavior, ordering, type conversion, security và performance.

### 8.3. Performance

Đo replacement trên workload đại diện. API mới có thể sạch hơn nhưng chậm hơn hoặc cần thêm resource.

### 8.4. Compatibility range

Xác định replacement cần compiler/runtime version nào và có hỗ trợ nhánh LTS không.

### 8.5. Documentation and examples

Replacement cần API reference, tutorial, sample và migration guide trước khi yêu cầu consumer sử dụng.

### 8.6. Operational readiness

Với service/provider, xác minh capacity, monitoring, incident response và support ownership.

### 8.7. Adoption blocker

Ghi những trường hợp replacement chưa hỗ trợ. Nếu blocker quan trọng, giải quyết trước hoặc xác định exception chính thức.

## 9. Timeline và milestone

Timeline biến kế hoạch thành các mốc có thể theo dõi.

| Milestone | Nội dung | Bằng chứng hoàn tất |
|---|---|---|
| Proposal | Đề xuất ngừng dùng | Rationale và scope được review |
| Assessment | Inventory và impact analysis | Consumer list, risk assessment |
| Replacement ready | API mới và tài liệu sẵn sàng | Tests, docs, support sign-off |
| Deprecation release | Phát marker và warning | Release note, compiler diagnostic |
| Migration window | Consumer chuyển đổi | Progress report và migration evidence |
| Removal candidate | Kiểm tra readiness | Removal criteria được đáp ứng |
| Removal release | Xóa thành phần cũ | Release và compatibility tests |
| Closure | Dọn adapter và cập nhật tài liệu | Owner sign-off, catalog cập nhật |

### 9.1. Deprecation release

Phiên bản bắt đầu phát warning và công bố replacement. Mốc này cần thống nhất với release notes và metadata.

### 9.2. Migration window

Khoảng thời gian consumer có thể cập nhật. Độ dài phụ thuộc release cadence, số consumer, LTS và khả năng tự động hóa.

### 9.3. Feature freeze

Có thể ngừng phát triển tính năng mới trên API cũ ngay khi deprecated, chỉ cho phép sửa lỗi hoặc security fix.

### 9.4. Removal candidate

Bản release candidate có thể bật removal trong môi trường thử nghiệm để consumer phát hiện usage còn sót.

### 9.5. Removal release

Version chính thức không còn chấp nhận thành phần cũ. Release notes cần nêu diagnostic và replacement.

### 9.6. Post-removal monitoring

Theo dõi lỗi upgrade, support ticket, build failure và consumer chưa di trú sau removal.

### 9.7. Lịch có điều kiện

Nếu milestone phụ thuộc vào readiness, ghi điều kiện chuyển bước thay vì chỉ ghi ngày cố định.

## 10. Versioning và compatibility policy

Kế hoạch phải phù hợp với quy tắc versioning mà DSL đã công bố.

### 10.1. Language version

Source có thể khai báo DSL version. Compiler dùng version này để quyết định element là stable, deprecated hay removed.

### 10.2. Compiler version

Compiler mới có thể đọc nhiều language version. Cần phân biệt compiler release và language semantics.

### 10.3. Semantic versioning

Nếu dùng SemVer, deprecation có thể được đưa vào minor release và removal là breaking change trong major release. Policy cụ thể phải được công bố.

### 10.4. LTS branch

Nhánh LTS có thể giữ compatibility lâu hơn. Plan cần nêu rõ removal có áp dụng cho LTS hay chỉ nhánh hiện hành.

### 10.5. Compatibility mode

Compatibility mode có thể cho phép source cũ tiếp tục hoạt động trong một phạm vi version. Nó cần ngày hoặc version kết thúc.

### 10.6. Minimum supported toolchain

Consumer có thể cần nâng compiler hoặc runtime trước khi dùng replacement. Nêu minimum version để tránh lỗi khi migration.

### 10.7. Version matrix

Lập bảng tổ hợp source version, compiler version, runtime version và plugin version được hỗ trợ. Test những tổ hợp nằm trong cam kết.

## 11. Chiến lược migration

Migration strategy xác định cách chuyển consumer từ cũ sang mới.

### 11.1. Big-bang migration

Mọi consumer chuyển trong một lần. Cách này đơn giản về trạng thái cuối nhưng rủi ro cao khi có nhiều repository hoặc hệ thống đang chạy.

### 11.2. Phased migration

Chuyển theo nhóm, domain, environment hoặc consumer tier. Cách này cho phép học từ nhóm đầu tiên và điều chỉnh hướng dẫn.

### 11.3. Strangler approach

Duy trì compatibility adapter trong khi consumer mới dùng API mới. Dần chuyển traffic hoặc usage cho đến khi phần cũ không còn được gọi.

### 11.4. Dual-read

Đọc cả format cũ và mới trong giai đoạn chuyển tiếp. Cần quy định precedence khi cả hai cùng tồn tại.

### 11.5. Dual-write

Ghi cả representation cũ và mới có thể hỗ trợ consumer cũ nhưng tạo nguy cơ dữ liệu lệch. Cần xác định nguồn sự thật và cách reconciliation.

### 11.6. Adapter migration

Adapter chuyển input cũ sang contract mới. Adapter nên có metrics để biết còn consumer nào sử dụng.

### 11.7. Consumer-by-consumer

Di trú từng consumer giúp giới hạn blast radius. Cần tracking trạng thái và owner cho mỗi consumer.

### 11.8. Data migration

Nếu thay schema lưu trữ, cần backfill, validation, cutover và kế hoạch rollback riêng với source migration.

## 12. Migration tooling và automation

Tooling giúp giảm công sức và làm migration nhất quán.

### 12.1. Usage scanner

Scanner tìm deprecated element trong source, config, script và generated file. Nó nên phân biệt exact semantic usage với text match.

### 12.2. Codemod

Codemod chuyển AST pattern cũ sang mới. Rule cần có version range, precondition và report.

### 12.3. IDE quick fix

Quick fix hữu ích cho một thay đổi cục bộ và có mapping rõ. Không nên tự áp dụng transformation phức tạp mà không cho người dùng xem diff.

### 12.4. Bulk migration

Tool có thể chạy trên nhiều repository. Cần dry-run, giới hạn scope, retry, audit và báo cáo partial success.

### 12.5. Compatibility analyzer

Analyzer kiểm tra source mới có còn sử dụng API cũ hoặc gọi adapter legacy không.

### 12.6. Migration validation

Sau rewrite, parse, type-check, test và build. Với deployment, tạo plan preview và kiểm tra drift trước khi apply.

### 12.7. Machine-readable report

Xuất kết quả dưới dạng JSON hoặc SARIF với element ID, file, location, owner, migration status và diagnostic code.

### 12.8. Tool versioning

Migration tool cần được version hóa và ghi nhận. Chạy cùng một migration rule trên cùng source revision nên cho kết quả xác định.

## 13. Governance, ownership và approval

Deprecation ảnh hưởng contract nên cần quy trình ra quyết định và trách nhiệm rõ.

### 13.1. Proposal owner

Người đề xuất chịu trách nhiệm mô tả lý do, scope, replacement và tác động dự kiến.

### 13.2. API owner

Owner của DSL/API xác nhận semantics, compatibility policy và thời điểm removal.

### 13.3. Consumer owner

Các nhóm sử dụng chịu trách nhiệm đánh giá migration và cập nhật hệ thống của họ.

### 13.4. Security review

Nếu thay đổi liên quan security, nhóm security đánh giá mitigation, deadline và rủi ro khi tiếp tục hỗ trợ.

### 13.5. Release manager

Release owner xác nhận timeline, release notes, support window và version matrix.

### 13.6. Approval gate

Removal có thể cần sign-off của owner, consumer đại diện và vận hành nếu tác động rộng hoặc không thể rollback dễ dàng.

### 13.7. Exception authority

Xác định ai có quyền cấp exception và điều kiện cấp. Không để từng team tự bỏ qua policy mà không có record.

### 13.8. Decision record

Lưu quyết định, alternatives, rationale, approver và ngày review. Điều này giúp hiểu lý do khi người phụ trách thay đổi.

## 14. Communication plan

Thông báo cần đến đúng người, đúng thời điểm và qua kênh họ sử dụng.

### 14.1. Audience segmentation

Phân nhóm người dùng DSL, plugin authors, API consumers, platform operators và đối tác. Mỗi nhóm có thể cần hướng dẫn khác nhau.

### 14.2. Early notice

Với thay đổi lớn, thông báo trong roadmap hoặc preview release trước khi bắt đầu deprecation window.

### 14.3. Release notes

Ghi element, version deprecated, reason, replacement và removal target.

### 14.4. Migration guide

Cung cấp before/after examples, behavior differences, manual steps và verification instructions.

### 14.5. Direct notification

Với consumer được biết danh tính, gửi thông báo theo kênh quản trị đã thống nhất. Không chỉ dựa vào release notes chung.

### 14.6. IDE and CLI notices

Cảnh báo trong IDE/CLI giúp developer nhận biết khi đang sửa source. Nội dung phải có link đến guide hoặc replacement.

### 14.7. Reminder cadence

Nhắc lại trước mốc removal theo lịch hợp lý. Tránh gửi thông báo quá dày gây mệt mỏi hoặc khiến người dùng bỏ qua.

### 14.8. Feedback channel

Cung cấp kênh báo blocker, yêu cầu exception và phản hồi về migration tool. Có owner và SLA phản hồi.

## 15. Risk assessment và blast radius

Risk assessment giúp xác định mức độ thận trọng và thứ tự triển khai.

### 15.1. Consumer count

Số repository, service, tenant và external consumer càng lớn thì blast radius càng rộng.

### 15.2. Criticality

Một config dùng trong production authentication hoặc payment có rủi ro cao hơn option chỉ dùng trong local development.

### 15.3. Migration complexity

Một identifier rename có thể đơn giản; thay semantics của workflow hoặc database schema có thể cần nhiều bước.

### 15.4. Reversibility

Nếu có thể rollback nhanh bằng config hoặc compatibility adapter, risk thấp hơn thay đổi data destructive hoặc protocol irreversible.

### 15.5. Failure probability

Dựa vào test coverage, migration tooling, số biến thể input và kinh nghiệm từ pilot.

### 15.6. Impact severity

Đánh giá downtime, data loss, security exposure, failed deployment và support burden.

### 15.7. Risk matrix

| Probability / Impact | Low impact | Medium impact | High impact |
|---|---|---|---|
| Low probability | Low | Low–Medium | Medium |
| Medium probability | Low–Medium | Medium | High |
| High probability | Medium | High | Critical |

Bảng chỉ là công cụ phân loại; tiêu chí cụ thể cần phù hợp tổ chức và domain.

### 15.8. Mitigation

Mitigation có thể gồm phased rollout, compatibility adapter, canary, backup, feature flag, extra monitoring và support window kéo dài.

## 16. Readiness criteria trước removal

Không nên loại bỏ chỉ vì đã đến ngày dự kiến. Cần các điều kiện có thể kiểm chứng.

### 16.1. Replacement stable

Replacement đã được phát hành, tài liệu đầy đủ và được hỗ trợ trong toolchain cần thiết.

### 16.2. Internal usage cleared

Repository và service nội bộ quan trọng đã chuyển hoặc có exception được phê duyệt.

### 16.3. External consumer assessment

Consumer đã đăng ký được thông báo và có trạng thái migration. Các hợp đồng công khai cần tuân thủ notice period.

### 16.4. Migration tool validated

Codemod hoặc migration guide đã được thử trên fixture và project đại diện.

### 16.5. Compatibility tests pass

Các version combination còn được cam kết hỗ trợ đã được kiểm tra.

### 16.6. Operational readiness

Monitoring, runbook, rollback/mitigation và support staffing đã sẵn sàng.

### 16.7. No unresolved critical blocker

Không còn blocker có mức độ critical hoặc high chưa có mitigation được chấp thuận.

### 16.8. Approval recorded

Owner và release authority xác nhận criteria đã được đáp ứng. Quyết định cần được ghi lại.

## 17. Rollout và staged removal

Removal có thể được triển khai theo nhiều giai đoạn để giới hạn rủi ro.

### 17.1. Warning-only phase

Compiler phát warning nhưng vẫn chấp nhận source. Đây là giai đoạn inventory và migration.

### 17.2. Strict CI phase

Repository có thể bật warning-as-error để ngăn usage mới trong khi compatibility runtime vẫn còn.

### 17.3. Opt-in removal phase

Cho phép project bật chế độ tương lai để phát hiện sớm lỗi sẽ xuất hiện sau removal.

### 17.4. Preview release

Release candidate hoặc preview compiler có thể từ chối thành phần cũ để consumer thử nghiệm trước.

### 17.5. Canary rollout

Với runtime service hoặc provider, có thể chuyển một phần consumer sang replacement trước và theo dõi metrics.

### 17.6. General removal

Khi criteria đạt, loại thành phần trong version đã công bố. Không âm thầm remove sớm trong patch release nếu policy không cho phép.

### 17.7. Post-release monitoring

Theo dõi build failures, support requests, runtime errors và usage telemetry. Có kế hoạch xử lý nhanh nếu phát hiện consumer quan trọng bị bỏ sót.

## 18. Rollback và contingency plan

Không phải mọi migration đều có thể đảo ngược, nhưng cần chuẩn bị cách giảm tác động khi có vấn đề.

### 18.1. Rollback source

Consumer có thể revert commit migration nếu source thay đổi chưa được phát hành. Cần lưu diff và biết replacement có thay đổi dữ liệu hay không.

### 18.2. Compatibility patch

Có thể phát hành patch khôi phục alias hoặc adapter tạm thời nếu removal gây ảnh hưởng ngoài dự kiến, trong phạm vi policy cho phép.

### 18.3. Runtime rollback

Nếu service/provider mới gây lỗi, chuyển traffic về implementation cũ khi nó còn hoạt động và dữ liệu tương thích.

### 18.4. Data rollback

Data migration destructive có thể không rollback trực tiếp. Cần backup, forward-fix hoặc compensation plan.

### 18.5. Stop criteria

Định nghĩa ngưỡng để dừng rollout, ví dụ tỷ lệ lỗi vượt ngưỡng, latency tăng hoặc consumer critical chưa di trú.

### 18.6. Contingency owner

Chỉ định người quyết định pause, rollback hoặc kéo dài compatibility. Không đợi sự cố xảy ra mới tìm người có thẩm quyền.

### 18.7. Communication during incident

Thông báo trạng thái, tác động và bước xử lý qua kênh đã thống nhất. Cập nhật timeline nếu removal phải hoãn.

## 19. Quản lý exception và LTS

Một số consumer không thể di trú đúng lịch chung.

### 19.1. Exception request

Yêu cầu cần nêu consumer, lý do, tác động, thời hạn và kế hoạch di trú.

### 19.2. Exception approval

Owner đánh giá liệu exception có an toàn và có làm tăng support burden hay không. Security-critical removal có thể không cho phép exception.

### 19.3. Time-bound exception

Mỗi exception nên có expiry hoặc review date. Gia hạn cần rationale mới.

### 19.4. LTS support

LTS có thể giữ feature cũ trong một thời gian đã công bố. Cần tách rõ support branch và current branch.

### 19.5. Backport policy

Bug fix cho compatibility layer có thể được backport vào LTS. Không nhất thiết phải backport replacement mới nếu branch không hỗ trợ.

### 19.6. Exception inventory

Lưu danh sách exception và owner để biết phần legacy nào vẫn cần hỗ trợ sau removal release.

### 19.7. Exit plan

Exception cần có điều kiện kết thúc: consumer nâng cấp, dependency được thay hoặc hệ thống được retire.

## 20. Metrics và theo dõi tiến độ

Metrics giúp đánh giá plan đang tiến triển hay bị đình trệ.

### 20.1. Deprecated usage count

Đếm số usage theo element, repository, version và owner. Phân biệt declaration với reference nếu cả hai được ghi nhận.

### 20.2. Active consumer count

Theo dõi consumer đang chạy hoặc build với contract cũ, không chỉ số file source có chứa identifier.

### 20.3. Migration completion rate

Tỷ lệ consumer đã hoàn tất migration trên tổng số consumer đã biết. Cần ghi rõ mẫu số và dữ liệu thiếu.

### 20.4. Warning trend

Theo dõi warning tăng hay giảm theo release. Nếu warning tăng, có thể replacement chưa được dùng hoặc template mới vẫn sinh syntax cũ.

### 20.5. Exception count

Số exception đang mở, sắp hết hạn và đã quá hạn.

### 20.6. Migration failure rate

Đo codemod fail, compile fail hoặc runtime regression sau migration.

### 20.7. Support load

Theo dõi ticket và incident liên quan deprecation. Tăng đột biến có thể báo hiệu guide thiếu hoặc replacement có vấn đề.

### 20.8. Removal readiness dashboard

Dashboard tổng hợp criteria, owner, milestone, blockers và sign-off. Tránh chỉ dùng một phần trăm hoàn thành không thể giải thích.

## 21. Quản lý dependency và ecosystem

Deprecation có thể lan qua nhiều lớp dependency.

### 21.1. Direct dependency

Một module có thể trực tiếp dùng API cũ. Đây là nơi thường dễ tìm bằng static analysis.

### 21.2. Transitive dependency

Plugin hoặc library có thể dùng API deprecated bên trong. Consumer không trực tiếp khai báo nhưng vẫn chịu ảnh hưởng khi nâng dependency.

### 21.3. Plugin ecosystem

Plugin author cần thời gian cập nhật và phát hành version tương thích. Có thể cần compatibility API song song.

### 21.4. Generated artifacts

Generated code có thể chứa reference cũ. Cần nâng generator và regenerate, đồng thời xác định file generated có được commit hay không.

### 21.5. Templates and examples

Template cũ có thể tiếp tục tạo usage deprecated cho project mới. Cập nhật template là điều kiện quan trọng để ngăn nợ mới.

### 21.6. Documentation dependencies

Tutorial hoặc snippet cũ có thể được sao chép rộng. Tìm và cập nhật cả docs versioned và external sample được quản lý.

### 21.7. Ecosystem compatibility window

Plugin registry hoặc marketplace có thể cần chính sách minimum host version và deadline riêng.

## 22. Deprecation plan cho schema, event và API

Contract tích hợp cần cách di trú riêng vì producer và consumer thường triển khai độc lập.

### 22.1. API endpoint

Công bố version cũ và mới, sunset date, replacement endpoint, auth behavior và error mapping.

### 22.2. Event field

Theo dõi consumer đọc field cũ, phát field mới trong transition nếu semantics cho phép và xác định ngày ngừng field cũ.

### 22.3. Schema version

Dùng compatibility checks trong registry. Không remove field chỉ vì producer đã ngừng ghi nếu consumer vẫn đọc.

### 22.4. Consumer-driven contracts

Consumer test thể hiện các field/behavior mà nó phụ thuộc. Producer có thể dùng test để xác nhận thay đổi không phá consumer đã đăng ký.

### 22.5. Dual publishing

Nếu phát cả event cũ và mới, xác định cách ngăn consumer xử lý hai message như hai sự kiện nghiệp vụ độc lập.

### 22.6. Data backfill

Nếu contract mới cần field không có trong dữ liệu cũ, xác định có thể suy ra, backfill hoặc phải đánh dấu unknown.

### 22.7. Sunset enforcement

API gateway hoặc schema registry có thể từ chối request/publish sau mốc removal. Enforcement cần cảnh báo và report trước khi bật.

## 23. Documentation và release management

Tài liệu phải theo kịp trạng thái thực tế của tính năng.

### 23.1. Deprecation catalog

Lưu danh sách element, status, since, removal target, replacement, owner và migration guide.

### 23.2. API reference

Đánh dấu deprecated rõ trên trang API. Không để ví dụ chính tiếp tục khuyến nghị cách dùng cũ.

### 23.3. Migration guide

Cung cấp hướng dẫn cụ thể, before/after, behavior mapping, manual steps và verification.

### 23.4. Release note

Thông báo thay đổi trong từng release: newly deprecated, removal planned, removed và compatibility changes.

### 23.5. Versioned documentation

Người dùng cần xem tài liệu phù hợp với version đang chạy. Link từ diagnostic nên trỏ đến guide tương ứng hoặc trang có version selector.

### 23.6. Support matrix

Nêu version compiler, runtime, plugin và LTS nào còn hỗ trợ legacy element.

### 23.7. Documentation owner

Mỗi thay đổi cần người chịu trách nhiệm cập nhật docs, examples và generated reference.

## 24. Removal execution và cleanup

Khi đủ điều kiện, removal cần được thực hiện như một thay đổi kỹ thuật có kiểm soát.

### 24.1. Remove parser support

Xóa grammar branch hoặc parser alias. Nếu có thể nhận diện cú pháp cũ, phát diagnostic chuyên biệt để hướng người dùng đến migration guide.

### 24.2. Remove semantic symbols

Xóa symbol hoặc API cũ khỏi registry, type environment và completion index.

### 24.3. Remove compatibility adapter

Xóa forwarding method, conversion layer và fallback path không còn cần thiết.

### 24.4. Remove configuration defaults

Dọn default hoặc alias legacy. Kiểm tra file cấu hình cũ không còn được đọc ngoài phạm vi đã công bố.

### 24.5. Remove tests and fixtures carefully

Xóa test chỉ dành cho legacy path nhưng giữ migration fixtures và regression test chứng minh removed feature bị từ chối đúng cách.

### 24.6. Update generated output

Regenerate code hoặc manifest để không còn reference cũ. Kiểm tra file stale và ownership trước khi xóa.

### 24.7. Remove docs for active use

Chuyển tài liệu cũ sang migration/archive nếu cần lịch sử. Không để docs cũ xuất hiện như hướng dẫn hiện hành.

### 24.8. Dependency cleanup

Loại package hoặc plugin chỉ được giữ để hỗ trợ legacy. Kiểm tra lock file và transitive dependency.

### 24.9. Final release audit

Xác minh release version, changelog, migration note, diagnostic và support matrix thống nhất.

## 25. Kiểm thử kế hoạch và quá trình ngừng dùng

Không chỉ implementation removal cần test; cả migration path và version policy cũng cần được xác minh.

### 25.1. Lifecycle tests

Kiểm tra stable, deprecated, removal-planned và removed ở đúng version boundary.

### 25.2. Compatibility matrix

Test source cũ với compiler version được hỗ trợ và source mới với minimum toolchain.

### 25.3. Migration fixture tests

Chạy migration tool trên project mẫu và so sánh output mong đợi.

### 25.4. Semantic equivalence tests

Chạy behavior trước/sau migration trên cùng input để xác minh semantics giữ nguyên hoặc khác biệt được chấp nhận.

### 25.5. Negative tests after removal

Ở version removal, usage cũ phải bị từ chối với diagnostic có replacement guidance.

### 25.6. Consumer contract tests

Xác minh API/event/schema mới đáp ứng consumer contract và không còn dependency vào phần tử cũ.

### 25.7. Rollback drills

Thử contingency plan trong môi trường staging hoặc test để bảo đảm có thể dừng rollout và phục hồi.

### 25.8. Documentation tests

Kiểm tra link, version và replacement metadata. Nếu diagnostic link đến guide không tồn tại, migration experience bị hỏng.

### 25.9. Telemetry validation

Xác minh usage metrics đếm đúng element và không ghi dữ liệu nhạy cảm. Metrics sai có thể dẫn đến quyết định removal sai.

## 26. Mẫu cấu trúc một deprecation plan

Một plan có thể được lưu dưới dạng tài liệu hoặc record machine-readable.

~~~yaml
deprecation:
  id: DSL-DEP-042
  element: service.legacyHealthCheck
  kind: configuration-option
  owner: platform-dsl
  status: deprecated

  reason: "Được thay bằng healthProbe có cấu hình rõ hơn."
  deprecatedSince: "3.2"
  removalTarget: "5.0"

  replacement:
    element: service.healthProbe
    guide: "migration/health-probe"

  compatibility:
    acceptedThrough: "4.x"
    behavior: "Compiler ánh xạ legacyHealthCheck sang healthProbe.enabled."

  milestones:
    - name: announce
      release: "3.2"
    - name: strict-ci
      release: "4.0"
    - name: removal
      release: "5.0"

  readiness:
    replacementStable: true
    migrationToolAvailable: true
    consumerInventoryReviewed: false

  risks:
    level: medium
    rollback: "Khôi phục compatibility adapter trong patch release nếu cần."
~~~

### 26.1. Stable ID

Plan ID không đổi khi message hoặc ngày được cập nhật. Nó giúp liên kết issue, diagnostic, release note và dashboard.

### 26.2. Status

Status có thể là proposed, approved, deprecated, migration, removal-ready, removed hoặc cancelled. Trạng thái phải có transition rule.

### 26.3. Milestone

Mỗi milestone có owner, due date, dependency và evidence. Không chỉ ghi ngày mà thiếu điều kiện hoàn thành.

### 26.4. Readiness

Readiness criteria nên là các điều kiện có thể kiểm chứng tự động hoặc có sign-off rõ.

### 26.5. Risk and rollback

Ghi mức rủi ro, mitigation, stop criteria và người quyết định rollback.

## 27. Ví dụ: kế hoạch loại bỏ CLI flag cũ

Giả sử CLI có flag --legacy-output và được thay bằng --output-format.

### 27.1. Scope

Xác định flag cũ được parser CLI nhận ở những command nào, trong script, documentation và CI template nào.

### 27.2. Replacement

Xác định mapping giữa giá trị cũ và mới. Nếu output mode mới có thêm lựa chọn, ghi rõ giá trị nào tương đương.

### 27.3. Timeline

Một ví dụ là phát warning ở version 2.8, bật warning-as-error trong CI tùy chọn ở 3.0 và loại flag ở 4.0. Mốc cụ thể phải theo release policy thực tế.

### 27.4. Inventory

Quét script repository, CI template và telemetry CLI nếu được phép. Ghi consumer owner và trạng thái migration.

### 27.5. Migration tool

Có thể cung cấp codemod cho YAML pipeline hoặc script có cấu trúc. Với shell script tùy ý, hướng dẫn thủ công có thể an toàn hơn.

### 27.6. Rollout

Cập nhật template chính thức trước, chuyển internal CI, sau đó thông báo public consumer. Theo dõi lỗi unknown option trong preview release.

### 27.7. Removal

Khi consumer quan trọng đã chuyển và support window kết thúc, xóa flag cũ và phát diagnostic gợi ý flag mới.

## 28. Những sai lầm thường gặp

### 28.1. Không lập inventory

Không biết ai đang dùng thành phần khiến removal dễ gây breaking change bất ngờ. Kết hợp static scan, telemetry và consumer registry.

### 28.2. Replacement chưa sẵn sàng

Người dùng nhận warning nhưng không có cách chuyển phù hợp. Hoàn thiện replacement và migration guide trước khi bắt đầu window nếu có thể.

### 28.3. Timeline không thực tế

Một release cycle ngắn có thể không đủ cho nhiều consumer hoặc hệ thống LTS. Dựa vào cadence và mức độ phức tạp thực tế.

### 28.4. Không có owner

Plan bị bỏ quên khi người đề xuất chuyển nhóm. Gán owner cho từng action và một accountable owner cho toàn plan.

### 28.5. Dựa vào telemetry duy nhất

Consumer bên ngoài hoặc offline có thể không xuất hiện trong số liệu. Nêu confidence và các nguồn inventory.

### 28.6. Migration chỉ sửa cú pháp

Source có thể compile nhưng behavior thay đổi. Kiểm tra semantics, default, ordering, security và operational behavior.

### 28.7. Không có rollback plan

Một removal không thể dễ dàng phục hồi có thể gây outage. Xác định stop criteria và contingency trước rollout.

### 28.8. Exception vô thời hạn

Exception không có expiry giữ compatibility debt mãi mãi. Đặt owner, review date và exit criteria.

### 28.9. Không cập nhật template

Project mới tiếp tục được tạo với API cũ dù consumer hiện tại đã di trú. Cập nhật template, sample và generator.

### 28.10. Xóa quá nhiều cùng lúc

Gộp nhiều deprecation không liên quan vào một release làm tăng blast radius và khó xác định nguyên nhân lỗi. Nhóm thay đổi theo dependency và khả năng rollback.

### 28.11. Không theo dõi sau removal

Lỗi có thể xuất hiện ở consumer không nằm trong inventory. Theo dõi support signal và có quy trình xử lý post-release.

### 28.12. Không phân biệt removal khỏi nhánh LTS

Người dùng có thể kỳ vọng LTS tiếp tục hỗ trợ. Nêu support branch và version matrix rõ ràng.

## 29. Nguyên tắc thiết kế kế hoạch ngừng dùng

Một deprecation plan tốt biến việc loại bỏ thành một quy trình có thể theo dõi, kiểm chứng và điều chỉnh.

### 29.1. Xác định scope chính xác

Ghi element identity, version range, source/runtime/tooling surface và các trường hợp ngoại lệ.

### 29.2. Có rationale và replacement

Giải thích vấn đề, mục tiêu và phương án thay thế. Đảm bảo replacement đã sẵn sàng cho các use case quan trọng.

### 29.3. Inventory trước timeline

Tìm consumer và dependency trước khi cam kết mốc removal. Ghi confidence của dữ liệu.

### 29.4. Impact và risk assessment

Đánh giá source, binary, configuration, data, runtime, operations và ecosystem. Lập mitigation tương ứng.

### 29.5. Milestone có owner

Mỗi giai đoạn có người chịu trách nhiệm, due date, dependency và evidence hoàn tất.

### 29.6. Migration có công cụ

Cung cấp codemod, scanner, quick fix, compatibility adapter hoặc hướng dẫn thủ công phù hợp với từng loại consumer.

### 29.7. Readiness có thể đo

Không remove chỉ vì lịch đã đến. Kiểm tra consumer status, replacement stability, migration validation, operational readiness và approval.

### 29.8. Compatibility có thời hạn

Mọi alias và adapter cần removal target hoặc exit criteria. Quản lý LTS và exception riêng.

### 29.9. Truyền thông nhiều kênh

Đồng bộ diagnostic, IDE, CLI, release notes, migration guide, catalog và direct consumer notice.

### 29.10. Chuẩn bị rollback

Đặt stop criteria, contingency owner và cách phục hồi trước khi rollout.

### 29.11. Test lifecycle end-to-end

Test version boundaries, migration, behavior equivalence, removal diagnostic, contract và rollback.

### 29.12. Đóng plan bằng bằng chứng

Sau removal, cập nhật catalog, tài liệu, dependency, adapter và metrics; ghi sign-off và các exception còn tồn tại.

## 30. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Deprecation Plan | Kế hoạch quản trị việc ngừng hỗ trợ một thành phần |
| Deprecation Lifecycle | Các trạng thái từ stable đến deprecated và removed |
| Consumer Inventory | Danh sách project, service hoặc hệ thống đang dùng thành phần |
| Impact Analysis | Phân tích phạm vi và hậu quả của việc loại bỏ |
| Replacement | API, cú pháp hoặc capability thay thế |
| Migration Window | Khoảng thời gian consumer được chuyển đổi |
| Removal Target | Phiên bản hoặc thời điểm dự kiến loại bỏ |
| Readiness Criteria | Điều kiện cần đạt trước khi removal |
| Compatibility Layer | Lớp giữ cho consumer cũ tiếp tục hoạt động |
| Migration Tool | Công cụ hỗ trợ chuyển source/configuration |
| Codemod | Công cụ rewrite source theo cấu trúc |
| Consumer-driven Contract | Hợp đồng được kiểm chứng từ nhu cầu của consumer |
| Sunset Date | Ngày kết thúc hỗ trợ của API hoặc integration |
| LTS | Nhánh hỗ trợ dài hạn |
| Exception | Trường hợp được phép tiếp tục dùng legacy theo phê duyệt |
| Blast Radius | Phạm vi tác động tiềm tàng của thay đổi |
| Staged Rollout | Triển khai theo từng giai đoạn |
| Canary | Chuyển một phần consumer để quan sát trước |
| Stop Criteria | Ngưỡng khiến rollout phải dừng |
| Rollback Plan | Kế hoạch quay lại hoặc phục hồi khi có sự cố |
| Dual Read | Đọc cả representation cũ và mới |
| Dual Write | Ghi cả representation cũ và mới |
| Removal Readiness | Trạng thái đã đáp ứng điều kiện để loại bỏ |
| Deprecation Catalog | Danh mục tập trung các phần tử và kế hoạch deprecated |
| Migration Progress | Mức độ hoàn tất chuyển đổi của consumer |
| Compatibility Matrix | Bảng tổ hợp version còn được hỗ trợ |
| Post-removal Monitoring | Theo dõi lỗi và usage sau khi loại bỏ |
| Decision Record | Hồ sơ ghi rationale, lựa chọn và người phê duyệt |

Kế hoạch ngừng dùng giúp DSL thay đổi mà không biến mỗi lần cải tiến thành một sự cố tương thích. Kế hoạch cần xác định chính xác phần tử và consumer bị ảnh hưởng, chứng minh replacement đã sẵn sàng, đặt timeline có owner, cung cấp công cụ migration và chỉ cho phép removal khi readiness criteria được đáp ứng. Khi kết hợp inventory, impact/risk assessment, communication, compatibility window, exception management, rollback và kiểm thử lifecycle, việc loại bỏ legacy trở thành một quy trình có thể dự đoán và quản trị thay vì một thao tác xóa code đơn lẻ.
