# Cảnh báo di trú

## Cảnh báo di trú trong DSL là gì?

Một ngôn ngữ chuyên miền (domain-specific language, DSL) thường được sử dụng trong thời gian dài và được nâng cấp qua nhiều phiên bản. Khi grammar, type system, host API, module format hoặc runtime semantics thay đổi, source DSL đã viết trước đó có thể cần điều chỉnh để tiếp tục được hỗ trợ. Hệ thống cần thông báo sớm những điểm có thể bị ảnh hưởng để người dùng có thời gian chuẩn bị.

**Cảnh báo di trú (migration warning)** là diagnostic thông báo rằng một construct, API, cú pháp, kiểu dữ liệu, cấu hình hoặc hành vi đang dùng có thể cần thay đổi khi nâng cấp DSL hoặc thành phần liên quan. Cảnh báo thường xuất hiện trước khi một tính năng bị loại bỏ hoặc trước khi một behavior cũ thay đổi. Nó giúp tác giả nhận biết rủi ro, hiểu lý do và thực hiện thay đổi phù hợp.

Ví dụ, DSL version 1 hỗ trợ:

~~~text
RULE oldDiscount {
  WHEN customer.level == "GOLD"
  THEN order.total * 0.10
}
~~~

Từ version 2, cú pháp rule được chuẩn hóa thành:

~~~text
POLICY goldDiscount {
  WHEN customer.level == "GOLD"
  APPLY order.total * 0.10
}
~~~

Compiler mới có thể tiếp tục chấp nhận RULE và THEN trong language version cũ, nhưng phát cảnh báo:

~~~text
MIGR001: RULE declaration is deprecated in language version 2.
Use POLICY and APPLY instead.
This syntax is scheduled for removal in language version 3.
~~~

Cảnh báo này giúp người dùng biết source vẫn đang được chấp nhận ở thời điểm hiện tại, nhưng cần lập kế hoạch chuyển đổi trước khi nâng lên version có thể loại bỏ cú pháp cũ.

Cảnh báo di trú hữu ích khi:

- Một keyword, operator hoặc grammar construct đã bị deprecated.
- Một host function hoặc plugin API sắp bị thay thế.
- Một type hoặc field trong schema được đổi tên.
- Một default value hoặc configuration option thay đổi.
- Một behavior cũ được giữ tạm qua compatibility mode.
- Một artifact format cần được rebuild hoặc migrate.
- Một workflow definition cần được chuyển sang version mới.
- Một permission hoặc security policy cũ không còn được khuyến nghị.
- Một backend hoặc runtime dependency sắp ngừng hỗ trợ.

Cảnh báo di trú cần cho biết điều gì đang bị ảnh hưởng, mức độ quan trọng, thời điểm thay đổi có hiệu lực và cách xử lý. Một thông báo chung như "API cũ không còn được khuyến nghị" không đủ để người dùng xác định vị trí cần sửa hoặc đánh giá tác động.

## Phân biệt migration warning, deprecation warning và error

Các loại diagnostic này liên quan nhưng không đồng nhất.

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Info | Thông tin hữu ích, không yêu cầu hành động ngay | Một option đang dùng giá trị mặc định mới |
| Warning | Có rủi ro hoặc cách dùng không được khuyến nghị | Một API vẫn chạy nhưng có behavior dễ gây lỗi |
| Deprecation warning | Construct vẫn được hỗ trợ nhưng đã có lộ trình loại bỏ | Keyword cũ sẽ bị xóa ở language version 3 |
| Migration warning | Người dùng cần chuẩn bị thay đổi khi chuyển version hoặc schema | Field cũ cần đổi sang field mới |
| Error | Source hoặc cấu hình không hợp lệ theo version đang chạy | Runtime mới không hỗ trợ syntax này |
| Migration error | Quá trình chuyển đổi không thể hoàn tất an toàn | Không thể ánh xạ type cũ sang type mới |

Deprecation là một trường hợp thường gặp của migration warning, nhưng migration warning có phạm vi rộng hơn. Ví dụ, một warning có thể yêu cầu chuyển đổi persisted workflow state dù không có cú pháp nào bị deprecated.

### Warning không phải lỗi

Một construct deprecated có thể vẫn chạy theo compatibility mode. Compiler nên cho phép tiếp tục nếu version và policy hỗ trợ, đồng thời phát diagnostic để người dùng có thời gian sửa.

Nếu warning được nâng thành error trong một version mới, thay đổi đó cần được công bố và kiểm thử. Không nên âm thầm đổi severity trong một patch release nếu điều đó làm pipeline đang thành công chuyển thành thất bại mà không có policy.

### Warning không đồng nghĩa với migration đã xảy ra

Diagnostic chỉ thông báo. Nó không tự sửa source, cập nhật database hoặc chuyển workflow instance. Việc thực hiện migration là một bước riêng, có thể do người dùng, migration tool hoặc release process điều khiển.

### Warning và compatibility mode

Runtime có thể hỗ trợ một số behavior cũ thông qua compatibility mode. Warning cần nêu rõ behavior đang được giữ nhờ mode nào và mode đó được hỗ trợ đến phiên bản nào.

Ví dụ:

~~~text
MIGR014: Legacy null comparison semantics are active.
Set languageVersion = "2" and migrate the expression before upgrading to runtime 4.
~~~

## Vòng đời của một migration warning

Một tính năng thường trải qua nhiều giai đoạn trước khi bị loại bỏ.

~~~text
Supported
    |
    v
Deprecated
    |
    v
Migration guidance available
    |
    v
Compatibility mode / warning period
    |
    v
Removal announced
    |
    v
Unsupported in a later version
~~~

Không phải mọi thay đổi đều cần toàn bộ các giai đoạn này. Một lỗ hổng bảo mật nghiêm trọng có thể yêu cầu loại bỏ nhanh hơn. Một syntax ít dùng có thể có thời gian deprecation dài.

### Supported

Construct được hỗ trợ và không có kế hoạch loại bỏ đã công bố. Nó vẫn cần test trong conformance suite.

### Deprecated

Construct vẫn hoạt động nhưng người dùng được khuyến nghị chuyển sang phương án mới. Compiler hoặc language server phát warning và cung cấp replacement.

### Migration window

Trong khoảng thời gian này, cả cách cũ và mới có thể cùng được hỗ trợ. Người dùng có thể nâng cấp source theo lịch của mình.

### Removal announced

Release notes hoặc migration guide xác định version dự kiến loại bỏ. Warning nên chứa version target cụ thể nếu đã được quyết định.

### Removed

Construct không còn hợp lệ trong language version mới. Compiler có thể phát error với migration hint. Không nên tiếp tục phát deprecation warning như thể source vẫn chạy được.

### Exception và security removal

Nếu construct cũ tạo rủi ro bảo mật hoặc dữ liệu, dự án có thể rút ngắn thời gian deprecation. Diagnostic cần giải thích lý do và cung cấp hành động thay thế an toàn.

## Phân loại nguyên nhân cần cảnh báo di trú

Một hệ thống DSL có thể tạo warning từ nhiều loại thay đổi.

### Syntax và grammar

- Keyword cũ được thay thế.
- Operator cũ có precedence gây nhầm lẫn.
- Cú pháp shorthand bị loại bỏ.
- Một identifier sắp trở thành reserved keyword.
- Cách khai báo module hoặc import thay đổi.
- Một grammar extension không còn được hỗ trợ.

### Type system và expression semantics

- Implicit conversion bị thu hẹp.
- Type alias bị deprecated.
- Nullability được thay đổi.
- Decimal rounding policy thay đổi.
- Overload resolution được chuẩn hóa.
- Function cũ trả về Optional thay vì nullable value.
- Collection equality hoặc ordering thay đổi.

### Host API và plugin

- Function hoặc action đổi signature.
- Host binding cũ được thay thế.
- Plugin lifecycle hook bị deprecated.
- Capability manifest thay đổi.
- Một extension API chuyển từ synchronous sang asynchronous.
- Permission cũ được thay bằng scope cụ thể hơn.

### Schema và dữ liệu

- Field được đổi tên hoặc chuyển namespace.
- Enum value bị loại bỏ.
- Một field optional trở thành required.
- Default value thay đổi.
- Serialized state cần migration.
- Database column hoặc message field đổi format.

### Runtime và execution behavior

- Transaction propagation thay đổi.
- Retry mặc định thay đổi.
- Timeout mặc định được rút ngắn.
- Error mapping được chuẩn hóa.
- Event ordering hoặc duplicate handling thay đổi.
- Một backend capability bị loại bỏ.

### Security và policy

- Permission quá rộng bị deprecated.
- Secret interpolation trực tiếp không còn được hỗ trợ.
- Một sandbox mode cũ không còn an toàn.
- TLS hoặc signature policy mới trở thành bắt buộc.
- Một action cần approval hoặc capability rõ hơn.

## Mô hình diagnostic cho migration warning

Migration warning nên được biểu diễn bằng cấu trúc ổn định thay vì chỉ là một chuỗi văn bản.

Ví dụ:

~~~text
MigrationDiagnostic
  code
  severity
  category
  message
  sourceLocation
  affectedSymbol
  currentVersion
  targetVersion
  removalVersion
  replacement
  migrationGuide
  fix
  relatedLocations
  metadata
~~~

### Diagnostic code

Mỗi warning cần một code ổn định, chẳng hạn MIGR001 hoặc DSL-MIG-014. Code được dùng trong:
- IDE filtering.
- CI allowlist hoặc suppression.
- Documentation lookup.
- Telemetry.
- Test assertion.
- Migration report.

Không nên thay code chỉ vì câu message được chỉnh sửa. Nếu semantics của rule thay đổi đáng kể, cần cân nhắc code mới hoặc metadata version.

### Severity

Severity có thể là:
- Info: thông báo về thay đổi tương lai.
- Warning: cần xem xét và lên kế hoạch.
- Error: không thể tiếp tục theo version hiện tại.
- Fatal: không thể phân tích hoặc migrate an toàn.

Một số tool cho phép user cấu hình severity, nhưng policy của CI hoặc tổ chức có thể đặt mức tối thiểu không được hạ thấp.

### Category

Category giúp nhóm warning:
- Syntax.
- Type.
- API.
- Schema.
- Runtime.
- Artifact.
- Security.
- Configuration.
- Workflow state.
- Dependency.

Category có thể dùng để lọc report hoặc phân công nhóm chịu trách nhiệm.

### Version metadata

Diagnostic nên xác định version hiện tại, version target và version dự kiến loại bỏ. Tránh các câu mơ hồ như "sẽ sớm bị xóa".

Nếu chưa có removal version, ghi rõ "chưa công bố" thay vì tự suy đoán.

### Source location

Cần giữ file, line, column và source span chính xác. Với generated DSL hoặc macro expansion, diagnostic có thể có cả vị trí source gốc và vị trí expanded construct.

### Replacement và migration guidance

Warning nên đưa ra replacement cụ thể hoặc liên kết đến tài liệu migration. Nếu không thể tự động sửa, hãy nêu bước thủ công và điều kiện cần kiểm tra.

## Version-aware diagnostics

Cảnh báo di trú thường phụ thuộc language version, runtime version, host API version hoặc schema version. Compiler cần biết version context trước khi đánh giá rule.

### Language version

Source có thể khai báo version:

~~~text
LANGUAGE_VERSION "2.0"
~~~

Compiler phải áp dụng grammar và deprecation policy tương ứng. Một construct deprecated trong version 2 có thể vẫn hoàn toàn hợp lệ trong version 1 theo compatibility contract.

### Runtime version

Runtime mới có thể chạy source language cũ. Warning có thể xuất hiện vì runtime đang hỗ trợ một behavior legacy, dù source version chưa thay đổi.

### Target version

Migration checker cần biết người dùng định nâng lên version nào. Một warning có thể không quan trọng nếu target là 2.1 nhưng trở thành blocking khi target là 3.0.

### Multi-version project

Một repository có thể chứa nhiều module ở language version khác nhau. Diagnostics cần gắn version theo module hoặc file, không dùng một version toàn cục nếu DSL hỗ trợ version pinning.

### Compatibility matrix

Một migration analyzer có thể sử dụng ma trận:

| Current language | Target runtime | Construct | Kết quả |
|---|---|---|---|
| 1.x | Runtime 2.x | Legacy RULE | Warning |
| 2.x | Runtime 2.x | Legacy RULE | Warning |
| 2.x | Runtime 3.x | Legacy RULE | Error |
| 2.x | Runtime 3.x | New POLICY | Supported |

Ma trận là policy của dự án và cần được version hóa cùng compiler hoặc migration catalog.

### Tránh false warning theo version

Nếu source khai báo language version 1 và construct được hỗ trợ đầy đủ trong version đó, không nên phát warning chỉ vì runtime hiện tại mới hơn, trừ khi warning thực sự nói về kế hoạch nâng version. Diagnostic cần phân biệt "deprecated trong source version" với "khuyến nghị trước khi chuyển sang target version".

## Phân tích source và phát hiện construct cần di trú

Migration analyzer có thể hoạt động trên AST, semantic model hoặc metadata của module.

### Syntax-level analysis

Có thể phát hiện:
- Keyword cũ.
- Operator deprecated.
- Cú pháp import cũ.
- Directive cũ.
- Configuration property đã đổi tên.

Phân tích syntax phù hợp với rule không phụ thuộc kiểu hoặc symbol resolution.

### Semantic analysis

Một function name có thể được overload hoặc shadow bởi symbol khác. Chỉ tìm chuỗi văn bản không đủ để xác định API đang dùng.

Semantic analyzer cần resolve:
- Symbol ID.
- Declaring module.
- Signature.
- Type arguments.
- Host API version.
- Extension provider.
- Call site.

Nhờ đó, warning chỉ xuất hiện khi source thực sự gọi API cũ, không nhầm với identifier có cùng tên trong namespace khác.

### Data/schema analysis

Migration warning có thể phát hiện field đã deprecated trong schema hoặc persisted data. Analyzer cần biết schema version và mapping giữa field cũ với field mới.

### Runtime behavior analysis

Một số thay đổi không thể phát hiện chỉ từ source. Ví dụ behavior phụ thuộc default runtime configuration hoặc backend capability. Khi đó, analyzer cần configuration snapshot, deployment manifest hoặc runtime metadata.

### Static analysis limits

Không phải mọi construct đều có thể phân tích tĩnh:
- Dynamic function resolution.
- Script gọi API qua reflection.
- Runtime-generated DSL.
- Plugin được nạp sau startup.
- Data shape chỉ biết khi chạy.
- External schema thay đổi ngoài repository.

Diagnostic nên ghi rõ khi kết luận chỉ là khả năng hoặc cần runtime verification.

## Migration catalog và quy tắc cảnh báo

Một migration catalog tập trung định nghĩa các thay đổi qua phiên bản. Nó có thể được đóng gói trong compiler, plugin hoặc file policy.

Ví dụ:

~~~text
MIGRATION_RULE legacy-rule-syntax {
  CODE "MIGR001"
  CATEGORY SYNTAX
  INTRODUCED_IN "2.0"
  REMOVED_IN "3.0"
  MATCH AST_RULE_DECLARATION
  REPLACEMENT "POLICY declaration"
  GUIDE "migration/rule-syntax.md"
}
~~~

### Thành phần của một rule

Một rule thường có:
- ID ổn định.
- Code diagnostic.
- Version bắt đầu.
- Version kết thúc hỗ trợ.
- Pattern hoặc symbol cần phát hiện.
- Severity.
- Message template.
- Replacement.
- Auto-fix hoặc manual steps.
- Test fixtures.
- Owner hoặc nhóm chịu trách nhiệm.

### Rule ordering và duplicate

Một construct có thể khớp nhiều migration rule. Analyzer cần tránh phát nhiều warning trùng lặp hoặc đưa ra replacement mâu thuẫn.

Có thể dùng priority, category specificity hoặc rule composition. Nếu một warning tổng quát bao phủ warning chi tiết, report nên ưu tiên thông tin hữu ích hơn.

### Rule versioning

Migration rule cũng cần version. Khi thay đổi pattern hoặc severity, test và release note phải phản ánh sự thay đổi. Diagnostic code ổn định giúp user suppression, nhưng rule metadata có thể có revision riêng.

### External migration catalog

Một tổ chức có thể bổ sung rule riêng cho internal DSL hoặc host API. Catalog ngoài cần được xác thực, pin version và không được chạy arbitrary code chỉ để phân tích source.

## Nội dung của một cảnh báo tốt

Một migration warning hữu ích cần giúp người dùng trả lời năm câu hỏi:

1. Construct nào đang bị ảnh hưởng?
2. Vì sao nó cần thay đổi?
3. Khi nào thay đổi có hiệu lực?
4. Nên thay bằng gì?
5. Làm sao xác nhận migration đúng?

Ví dụ:

~~~text
MIGR014 WARNING
File: workflows/order.dsl:42:7

The "RETRY FOREVER" policy is deprecated.
Use an explicit retry budget with MAX_ATTEMPTS and MAX_DELAY.
The legacy policy remains available in language version 2
and is removed from language version 3.

Suggested replacement:
  RETRY
    MAX_ATTEMPTS 5
    BACKOFF EXPONENTIAL
    MAX_DELAY 2 MINUTES

Guide: migration/retry-policy
~~~

### Message ngắn và chi tiết bổ sung

Diagnostic chính nên ngắn, nêu hành động cần thiết. IDE hoặc report có thể mở rộng:
- Vì sao rule được phát.
- Version liên quan.
- Replacement.
- Ví dụ trước/sau.
- Link migration guide.
- Related diagnostics.

Không nên nhồi toàn bộ tài liệu migration vào một dòng message.

### Tránh ngôn ngữ mơ hồ

Các cụm như "có thể sắp thay đổi" hoặc "nên cân nhắc dùng API mới" không đủ cụ thể. Nếu chưa có lịch removal, hãy nói rõ điều đó. Nếu replacement chưa có, cần ghi rằng người dùng phải theo dõi release note hoặc dùng workaround được công bố.

### Tránh đổ lỗi cho người dùng

Message nên mô tả construct và hành động, không phán xét người viết. Mục tiêu là hỗ trợ migration, không làm warning trở thành thông báo gây khó chịu.

## Auto-fix và migration suggestion

Một số warning có thể được sửa tự động bằng code action hoặc migration tool. Auto-fix giúp giảm công việc lặp lại nhưng chỉ an toàn khi transformation bảo toàn semantics.

### Text replacement

Nếu một keyword được đổi tên và không có ảnh hưởng cấu trúc, có thể thay token trong source span.

Ví dụ:

~~~text
BEFORE:
RULE discount { ... }

AFTER:
POLICY discount { ... }
~~~

Text replacement cần dùng source span đã resolve, tránh replace cùng tên trong comment hoặc string literal.

### AST transformation

Với thay đổi cấu trúc, nên transform AST rồi serialize source. Ví dụ chuyển positional arguments sang named arguments hoặc thay một node bằng cấu trúc mới.

AST transformation giúp tránh sửa nhầm text, nhưng cần giữ comment, formatting và source mapping nếu tool cam kết bảo toàn chúng.

### Semantic-preserving fix

Một fix chỉ nên tự động áp dụng khi:
- Target API tồn tại.
- Type mapping rõ.
- Không thay đổi evaluation order.
- Không làm mất null behavior.
- Không tạo side effect mới.
- Không thay đổi transaction hoặc permission semantics.
- Không cần quyết định nghiệp vụ mà tool không biết.

Nếu không chứng minh được, đưa ra suggestion và yêu cầu người dùng xác nhận.

### Quick fix

IDE có thể hiển thị action:
- Replace deprecated keyword.
- Add explicit type.
- Update function name.
- Add required argument.
- Migrate import.
- Open migration guide.
- Convert to new schema field.

Quick fix nên hiển thị diff trước khi áp dụng nếu thay đổi nhiều dòng hoặc nhiều file.

### Batch migration

Migration tool có thể áp dụng nhiều fix trên repository. Nên hỗ trợ:
- Preview diff.
- Dry run.
- Chỉ chọn một category hoặc version range.
- Báo các warning không tự sửa được.
- Giữ encoding và line ending.
- Ghi report về file đã thay đổi.
- Chạy formatter hoặc parser validation sau transform.

### Idempotency của migration tool

Chạy migration lần thứ hai không nên tiếp tục thay đổi source đã được chuyển đổi. Tool có thể ghi version marker hoặc chỉ match construct cũ. Test cần xác nhận transform idempotent.

### Không tự sửa source khi chỉ chạy compiler

Compiler thông thường nên phát warning. Việc ghi file là hành động riêng cần quyền và thao tác rõ ràng. CI không nên tự sửa repository trong một build kiểm tra.

## Warning cho schema và persisted data migration

Không phải migration nào cũng liên quan source code. DSL có thể tham chiếu schema hoặc lưu trạng thái dài hạn.

### Field rename

Ví dụ schema cũ:

~~~text
customer.fullName
~~~

Schema mới:

~~~text
customer.displayName
~~~

Analyzer có thể phát warning tại property access cũ và gợi ý replacement. Nếu field mới có semantics khác, không nên tự động thay chỉ dựa trên tên.

### Type change

Nếu field cũ là Integer và field mới là Decimal, migration cần xác định conversion, precision và overflow. Warning nên nói rõ trường hợp không thể chuyển tự động.

### Default change

Một field trước đây mặc định true nhưng version mới mặc định false có thể làm behavior thay đổi dù source không khai báo field. Cần phát warning tại nơi dùng implicit default hoặc trong migration report của configuration.

### Enum evolution

Enum value bị deprecated hoặc đổi tên cần warning và mapping. Nếu giá trị cũ đã được lưu trong database hoặc event history, source migration không đủ; cần data migration.

### Persisted workflow state

Workflow instance đang chạy có thể tham chiếu state hoặc variable đã đổi tên. Migration warning có thể chỉ ra definition cần migration, nhưng việc chuyển instance cần plan riêng, kiểm tra invariant và backup.

### Migration ordering

Schema migration, source migration và runtime upgrade có thể cần thứ tự:
1. Mở rộng schema tương thích.
2. Deploy runtime đọc được cả format cũ và mới.
3. Chuyển source hoặc persisted state.
4. Xác nhận dữ liệu mới.
5. Loại bỏ compatibility path sau support window.

Warning cần chỉ rõ prerequisite nếu một bước phụ thuộc migration khác.

## Warning về host API và plugin

DSL thường dùng function registry hoặc plugin extension. Migration warning cần gắn với symbol đã resolve.

### API rename

Nếu function cũ được thay bằng function mới, warning có thể chỉ ra:
- Tên cũ.
- Tên mới.
- Signature mới.
- Thay đổi parameter.
- Version target.

### Signature change

Ví dụ API cũ:

~~~text
sendNotification(userId, message)
~~~

API mới yêu cầu channel:

~~~text
sendNotification(userId, channel, message)
~~~

Không thể tự thêm channel nếu không biết nghiệp vụ. Quick fix có thể tạo placeholder hoặc mở documentation thay vì tự chọn giá trị.

### Behavior change

API có thể giữ signature nhưng đổi:
- Return type semantics.
- Retry behavior.
- Transaction participation.
- Timeout.
- Null handling.
- Permission requirement.
- Idempotency contract.

Warning cần nói rõ behavior cũ đang được giữ bằng compatibility layer nào và replacement yêu cầu thay đổi gì.

### Plugin version

Nếu plugin hiện tại không hỗ trợ runtime target, warning có thể xuất hiện trong dependency analysis. Nếu không có version tương thích, đây có thể là error chặn migration.

### Runtime-loaded extension

Nếu plugin chỉ được resolve khi runtime khởi động, static migration analyzer có thể không biết signature. Có thể tạo warning indeterminate hoặc yêu cầu kiểm tra plugin manifest trước khi chạy.

## Warning về behavior và configuration migration

Một số thay đổi không biểu hiện trực tiếp trong source syntax.

### Implicit behavior

Ví dụ, runtime cũ tự động retry ba lần; runtime mới không retry nếu không khai báo. Source không thay đổi nhưng reliability thay đổi.

Migration analyzer có thể phát warning khi thấy cấu hình phụ thuộc implicit default. Gợi ý là khai báo explicit policy để behavior ổn định.

### Configuration rename

Nếu option cũ:

~~~text
runtime.retryCount = 3
~~~

được thay bằng:

~~~text
runtime.retry.maxAttempts = 3
~~~

Warning nên gắn vào key cũ và đưa mapping rõ. Nếu nhiều option cũ được gom vào một object mới, migration có thể cần nhiều bước.

### Security tightening

Nếu runtime mới không cho phép inline secret hoặc shell execution mặc định, warning có thể yêu cầu chuyển sang secret reference hoặc command allowlist.

Với thay đổi bảo mật, severity có thể cao hơn và removal window ngắn hơn. Cần phân biệt compatibility warning với security finding để CI áp dụng policy phù hợp.

### Backend behavior

Nếu DSL compile sang nhiều backend, một construct có thể được hỗ trợ trên backend A nhưng không còn tương đương trên backend B. Warning cần gắn với target backend và feature capability.

## Warning trong IDE và Language Server

IDE là nơi thuận tiện để hiển thị migration warning vì người dùng có thể điều hướng trực tiếp đến source và áp dụng fix.

### Diagnostics

Language server có thể phát diagnostic với:
- Code.
- Severity.
- Source range.
- Message.
- Related information.
- Tags như deprecated.
- Code actions.
- Documentation link.

Diagnostic cần được gắn với document version. Khi file thay đổi, warning cũ phải được tính lại hoặc invalidation đúng.

### Hover

Hover có thể giải thích:
- Construct hiện tại.
- Version bắt đầu deprecated.
- Version dự kiến removal.
- Replacement.
- Link migration guide.

### Completion

Khi người dùng gõ API mới, completion nên ưu tiên symbol được khuyến nghị. API deprecated có thể bị hạ thứ tự hoặc gắn nhãn deprecated, nhưng không nên biến mất nếu source version vẫn hỗ trợ.

### Code actions

Code action có thể:
- Apply quick fix.
- Migrate current file.
- Migrate module.
- Open migration report.
- Suppress warning có scope.
- Change language version sau khi xác nhận.

### Workspace diagnostics

Khi mở project lớn, language server có thể chạy migration analysis nền. Cần cancellation, incremental update và progress reporting để không làm editor bị treo.

### Suppression UI

Người dùng có thể suppress một warning trong phạm vi được policy cho phép. IDE nên cho thấy suppression scope và lý do, tránh tạo suppression toàn file hoặc toàn workspace ngoài ý muốn.

## Warning trong CLI và CI/CD

Migration warning cần có cách xuất ra cho build system và release pipeline.

Ví dụ:

~~~text
dsl migrate-check --from 2.0 --to 3.0 ./src
~~~

CLI có thể hỗ trợ:
- Target version.
- Output format text, JSON hoặc SARIF.
- Severity threshold.
- Baseline file.
- Suppression configuration.
- Fail-on-new-warning.
- Migration suggestion.
- Report theo module.

### Exit code

Có thể quy định:
- 0: không có warning vượt threshold.
- 1: có migration warning mới theo policy.
- 2: có error hoặc migration blocker.
- 3: analyzer hoặc dependency gặp lỗi.

Exit code phải được tài liệu hóa để CI không diễn giải nhầm warning thành success hoặc ngược lại.

### Fail on new warning

Một project lớn có thể đang có warning lịch sử. Nếu bật fail cho mọi warning, nhóm có thể khó áp dụng dần. Một policy thực tế là:
- Không cho warning mới xuất hiện.
- Không tăng số warning theo category.
- Cho phép baseline đã review.
- Đặt deadline xử lý warning nghiêm trọng.
- Nâng threshold theo release.

### Baseline

Baseline ghi nhận warning hiện có để CI tập trung vào warning mới. Baseline cần:
- Có version.
- Có owner.
- Có thời hạn hoặc review date.
- Dùng identity ổn định của diagnostic.
- Phát hiện warning đã biến mất hoặc thay đổi.
- Không được dùng để che warning security hoặc migration blocker.

Không nên định danh warning chỉ bằng line number vì thêm dòng có thể làm baseline mất ổn định. Có thể dùng code, resource ID, symbol ID, source fingerprint và normalized location.

### Output format

JSON hoặc SARIF giúp tích hợp với code scanning và dashboard. Report nên có code, severity, file, span, message, target version và fix metadata. Không đưa source text nhạy cảm nếu không cần.

## Suppression và quản lý ngoại lệ

Không phải warning nào cũng có thể xử lý ngay. Một số construct có thể phải giữ vì compatibility với hệ thống cũ hoặc dependency chưa có replacement.

Suppression cần được kiểm soát để không trở thành cách che giấu nợ migration vô thời hạn.

### Inline suppression

Ví dụ:

~~~text
// suppress MIGR001: external consumer still requires legacy syntax
RULE legacyIntegration {
  ...
}
~~~

Inline suppression nên gắn với một diagnostic code và có reason. Không nên hỗ trợ một lệnh suppress-all không giới hạn nếu policy yêu cầu migration tracking.

### File hoặc module suppression

Có thể cấu hình suppression ở module manifest cho trường hợp nhiều warning cùng loại. Scope lớn hơn cần review kỹ hơn.

### Expiration

Suppression có thể có ngày hết hạn hoặc target release. Khi hết hạn, warning xuất hiện lại hoặc CI báo suppression expired.

### Owner và reason

Một suppression record có thể gồm:
- Diagnostic code.
- Resource hoặc source scope.
- Reason.
- Owner.
- Created by.
- Created at.
- Expires at.
- Ticket hoặc migration plan.

### Suppression không thay thế policy

Một warning về security hoặc unsupported artifact có thể không được phép suppress. Compiler hoặc CI policy cần phân biệt suppressible và non-suppressible diagnostic.

### Theo dõi suppression drift

Khi source được migrate, suppression cũ có thể không còn cần. Tool nên phát hiện suppression không còn match warning để dọn dẹp.

## Quản lý false positive và chất lượng cảnh báo

Quá nhiều warning không chính xác làm người dùng bỏ qua warning thật. Migration analyzer cần độ chính xác cao và giải thích được vì sao phát cảnh báo.

### Semantic resolution

Không tìm chuỗi đơn thuần nếu có thể resolve symbol. Identifier có tên giống API deprecated nhưng thuộc namespace khác không nên bị cảnh báo.

### Version context chính xác

Cần biết language version, runtime target, schema version và plugin version. Thiếu context thì analyzer nên báo trạng thái chưa xác định hoặc yêu cầu cấu hình, không đoán.

### Suppress by design

Một construct có thể được giữ có chủ đích trong adapter hoặc compatibility module. Policy có thể cho phép exception có phạm vi rõ ràng.

### Confidence level

Analyzer có thể phân loại:
- Certain: symbol hoặc syntax match chính xác.
- Probable: pattern phù hợp nhưng còn dependency động.
- Informational: chỉ là gợi ý dựa trên usage hoặc config.
- Unknown: không đủ dữ liệu.

Confidence không thay thế severity. Một warning security có confidence thấp vẫn cần được điều tra, nhưng message phải thể hiện mức chắc chắn.

### Feedback loop

Có thể thu thập false positive report từ IDE hoặc CI. Rule owner dùng dữ liệu này để sửa pattern và test fixture. Không nên tự động gửi source code hoặc dữ liệu khách hàng ra telemetry nếu chưa có policy và consent phù hợp.

## Migration warning và bảo mật

Migration warning có thể tiết lộ cấu trúc source, tên API nội bộ, đường dẫn file hoặc schema. Diagnostic service cần tuân thủ quyền truy cập giống source.

### Không lộ secret

Nếu warning được tạo quanh một literal secret, message và related information không nên in giá trị. Chỉ hiển thị vị trí và loại construct.

### Authorization cho report

Một người có quyền đọc module có thể xem diagnostics của module đó. Không nên cho user khác tenant truy vấn migration report chỉ bằng module ID đoán được.

### Migration tool và quyền ghi file

Auto-fix cần quyền ghi đúng workspace. Tool không nên theo symlink hoặc path traversal ra ngoài root được phép.

### Supply chain của migration catalog

Catalog ngoài hoặc plugin analyzer có thể chứa logic thực thi. Nên ưu tiên rule declarative, xác thực publisher và pin version. Không chạy arbitrary migration script chỉ vì source import catalog.

### Audit

Các thay đổi source tự động có thể cần audit:
- Ai khởi chạy migration.
- Tool và catalog version.
- Files đã thay đổi.
- Diagnostic được xử lý.
- Fix nào được áp dụng.
- Kết quả validation.

## Migration warning cho workflow và process đang chạy

Workflow DSL thường có process instance tồn tại lâu hơn một lần deploy. Definition mới có thể thay đổi state, variable hoặc transition.

### Definition migration

Warning có thể chỉ ra:
- State cũ bị deprecated.
- Event name thay đổi.
- Variable schema đổi.
- Transition guard được thay thế.
- Timer hoặc retry policy thay đổi.
- Compensation action được thêm hoặc bỏ.

### Active instance

Không phải mọi active instance đều có thể chuyển ngay sang definition mới. Có thể:
- Giữ instance chạy theo definition version cũ.
- Chỉ migrate instance ở checkpoint an toàn.
- Chuyển state và data bằng migration script.
- Đưa instance vào manual review.

Migration warning nên chỉ ra ảnh hưởng đến active instance và version cần hỗ trợ.

### State mapping

Nếu state Approved đổi thành Accepted, migration cần mapping state cũ sang state mới. Nhưng chỉ đổi tên có thể không đủ nếu invariant hoặc action semantics đã thay đổi.

### Timer và pending task

Migration cần xử lý timer, message subscription và task đang chờ. Warning có thể yêu cầu kiểm tra các instance đang ở state bị ảnh hưởng trước khi deploy.

### Replay và audit history

Event history cũ cần được giữ để audit. Runtime mới có thể đọc event cũ qua adapter hoặc migration layer, nhưng không nên rewrite lịch sử để giả vờ event mới đã xảy ra.

## Migration warning cho serialized artifact và cache

AST, bytecode, compiled plan hoặc cache có thể được tạo bởi toolchain cũ.

### Artifact format

Nếu format cũ sắp ngừng hỗ trợ, warning nên chỉ ra:
- Artifact version hiện tại.
- Version tối thiểu runtime target chấp nhận.
- Source có sẵn để rebuild hay không.
- Command hoặc pipeline cần chạy.
- Cache nào sẽ bị invalidation.

### Rebuild warning

Một artifact có thể vẫn load được nhưng không còn tối ưu hoặc không còn được hỗ trợ trong runtime mới. Warning cần phân biệt:
- Có thể load nhưng deprecated.
- Cần rebuild trước khi deploy.
- Không thể load và phải migrate.
- Không có source để rebuild.

### Cache không phải source of truth

AST hoặc compiled cache nên có thể tái tạo từ source và toolchain. Migration warning không nên khuyến nghị sửa trực tiếp cache binary như một cách migration chính.

### Integrity

Nếu migration tool đọc artifact serialized, cần xác minh checksum, signature và format version trước khi parse. Artifact không tin cậy không nên được deserialize tùy ý.

## Deprecation telemetry và migration readiness

Một tổ chức có thể cần biết còn bao nhiêu source đang dùng construct sắp bị loại bỏ. Telemetry giúp lập kế hoạch release và ưu tiên migration tool.

### Usage metrics

Có thể thu thập:
- Số module có warning theo code.
- Số source location duy nhất.
- Language version.
- Target runtime.
- Plugin/API version.
- Warning trend theo release.
- Auto-fix availability.
- Migration completion rate.

Không nên dùng raw source text, customer ID hoặc secret làm metric label.

### Readiness report

Một report có thể nhóm theo:
- Project/module.
- Warning code.
- Severity.
- Target removal version.
- Owner.
- Có auto-fix hay không.
- Suppression status.
- Estimated migration effort nếu có dữ liệu.

### Độ tin cậy của usage data

Nếu telemetry chỉ thu thập từ một số runtime, nó không đại diện toàn bộ source đã lưu nhưng chưa chạy. Static scan trên repository hoặc module registry có thể bổ sung bức tranh.

### Privacy và retention

Migration telemetry cần có mục đích, retention và access policy. Có thể chỉ lưu aggregate count và version metadata, không cần gửi source. Với môi trường khách hàng self-hosted, cần tôn trọng cấu hình telemetry của họ.

## Kiểm thử hệ thống migration warning

Migration warning là public behavior của compiler/tooling, nên cần test như một contract.

### Rule-level tests

Mỗi migration rule nên có:
- Source khớp rule.
- Source không khớp.
- Source version cũ.
- Source version mới.
- Target version khác nhau.
- Namespace hoặc overload khác.
- Positive và negative fixtures.
- Expected code, severity, message fields và source span.

### Diagnostic stability tests

Kiểm tra code ổn định qua release. Message text có thể được cải thiện, nhưng code và metadata quan trọng cần giữ contract nếu tooling bên ngoài phụ thuộc.

### Version matrix tests

Chạy cùng source với:
- Language version cũ.
- Language version hiện tại.
- Target version sắp nâng.
- Runtime có và không có compatibility mode.
- Plugin/schema version tương ứng.

### Auto-fix tests

Với mỗi fix:
1. Chạy analyzer để nhận diagnostic.
2. Áp dụng fix.
3. Parse lại source.
4. So sánh semantics hoặc test output.
5. Chạy fix lần hai để xác nhận idempotency.
6. Kiểm tra comment, formatting và encoding theo contract.

### Suppression tests

Kiểm tra:
- Suppression chỉ áp dụng code đã chỉ định.
- Scope đúng.
- Expiration hoạt động.
- Reason bắt buộc nếu policy yêu cầu.
- Non-suppressible warning vẫn xuất hiện.
- Unused suppression được báo.

### CLI/CI tests

Kiểm tra exit code, JSON/SARIF schema, severity threshold, baseline, fail-on-new-warning và output ổn định.

### Integration tests

Chạy migration analyzer qua host application hoặc language server để xác nhận configuration, source resolution, plugin registry và document version được truyền đúng.

### Migration readiness tests

Với project fixture lớn, kiểm tra report tổng hợp warning theo module, owner và target version. Xác nhận warning không bị đếm trùng do cùng source được import nhiều lần.

## Các lỗi thiết kế thường gặp

### Warning không nói rõ version

Thông báo "sẽ bị xóa" không giúp người dùng lập kế hoạch. Ghi version bắt đầu deprecate và version removal nếu đã công bố.

### Dùng message text làm diagnostic identity

Tooling dựa trên message text dễ vỡ khi sửa câu chữ hoặc dịch ngôn ngữ. Dùng diagnostic code ổn định và metadata có cấu trúc.

### Phát warning bằng tìm chuỗi

Tìm tên function trong source có thể bắt nhầm comment, string hoặc symbol khác namespace. Resolve AST và semantic symbol khi có thể.

### Không phân biệt source version với runtime version

Một construct hợp lệ trong language version cũ có thể bị cảnh báo sai nếu analyzer chỉ nhìn runtime hiện tại. Cần version-aware analysis.

### Warning không có hành động tiếp theo

Người dùng biết có vấn đề nhưng không biết sửa gì. Cung cấp replacement, migration guide hoặc giải thích rằng cần xử lý thủ công.

### Auto-fix không bảo toàn semantics

Đổi tên API có thể làm mất argument hoặc thay đổi evaluation order. Chỉ tự động sửa khi có thể chứng minh transformation an toàn.

### Suppression vô thời hạn

Warning bị che vĩnh viễn và migration không bao giờ hoàn tất. Dùng reason, owner, expiry và report suppression.

### CI fail vì warning lịch sử

Bật fail trên toàn bộ warning có thể tạo quá nhiều noise. Dùng baseline được review và fail-on-new-warning, đồng thời giữ deadline cho warning nghiêm trọng.

### Không kiểm tra active workflow

Source migration có thể thành công nhưng process instance đang chạy vẫn dùng state hoặc event format cũ. Cần report và migration strategy cho persisted state.

### Không version migration catalog

Rule thay đổi mà không có version làm report khác nhau giữa máy developer và CI. Pin catalog version và ghi trong diagnostics.

### Không đo false positive

Warning không chính xác làm người dùng bỏ qua tất cả cảnh báo. Theo dõi feedback và có positive/negative fixture.

### Tự sửa file khi chạy check

Một lệnh kiểm tra có thể vô tình sửa repository. Tách analyze, preview và apply thành các thao tác riêng.

## Quy trình thiết kế và triển khai cảnh báo di trú

Một quy trình thực tế có thể đi theo các bước:

1. **Xác định thay đổi:** mô tả construct, API, schema hoặc behavior đang được thay thế.
2. **Định nghĩa version policy:** version bắt đầu warning, target migration và version removal.
3. **Phân loại tác động:** syntax, type, API, data, artifact, runtime, security hoặc workflow state.
4. **Xây migration rule:** code ổn định, pattern, severity, message, replacement và owner.
5. **Xây analyzer:** dùng AST/semantic model và version context thay vì tìm chuỗi tùy tiện.
6. **Xác định confidence:** certain, probable hoặc informational khi có dependency động.
7. **Viết migration guide:** ví dụ trước/sau, prerequisite, manual steps và rollback.
8. **Triển khai quick fix:** chỉ với transformation bảo toàn semantics; hỗ trợ preview và dry run.
9. **Thiết kế suppression:** scope, reason, owner, expiry và policy non-suppressible.
10. **Tích hợp IDE/CLI:** diagnostics, code action, JSON/SARIF và target version.
11. **Thiết lập CI policy:** baseline, fail-on-new-warning, severity threshold và release gate.
12. **Kiểm tra dữ liệu dài hạn:** artifact, persisted schema và active workflow instance.
13. **Đo readiness:** usage metrics, warning trend, suppression và migration completion.
14. **Kiểm thử:** positive/negative fixtures, version matrix, auto-fix, suppression, CLI và host integration.
15. **Theo dõi removal:** chỉ loại bỏ construct theo support policy đã công bố và có migration path phù hợp.

Mỗi warning nên có một contract rõ ràng gồm code, category, severity, source span, version context, replacement, removal policy và suppression policy. Điều đó giúp compiler, IDE, CLI, CI và migration tool đưa ra cùng một thông điệp.

## Kết luận

Cảnh báo di trú giúp người dùng nhận biết source, API, schema, artifact hoặc behavior cần thay đổi khi DSL và các thành phần liên quan chuyển sang phiên bản mới. Một warning tốt xác định chính xác construct bị ảnh hưởng, lý do, version liên quan, replacement và cách kiểm tra migration.

Hệ thống nên dùng diagnostic code ổn định, version-aware analysis, AST/semantic resolution và migration catalog được version hóa. Auto-fix cần bảo toàn semantics và có preview; suppression cần reason, owner và thời hạn; CI cần baseline được review và chính sách fail-on-new-warning. Những thay đổi liên quan persisted data, compiled artifact hoặc workflow instance cần được xử lý riêng thay vì chỉ sửa source.

Khi migration warning được tích hợp vào compiler, language server, CLI và release pipeline, người dùng có thể xử lý thay đổi theo từng bước trước khi construct bị loại bỏ. Telemetry có kiểm soát, compatibility tests và migration report giúp nhóm phát triển đánh giá mức sẵn sàng, giảm false positive và phát hành phiên bản mới mà không làm người dùng bất ngờ.
