# Kiểm thử tương thích

## Kiểm thử tương thích trong DSL là gì?

Một ngôn ngữ chuyên miền (domain-specific language, DSL) thường được sử dụng lâu dài trong nhiều ứng dụng, project và môi trường khác nhau. Theo thời gian, grammar có thể mở rộng, type system được cải tiến, compiler thay đổi, host API được cập nhật, plugin được nâng cấp và backend thực thi có thể thay đổi. Những thay đổi này có thể làm source DSL cũ không còn parse được, thay đổi kết quả hoặc tạo hành vi khác giữa các phiên bản.

**Kiểm thử tương thích (compatibility testing)** là hoạt động xác nhận các thành phần của hệ sinh thái DSL tiếp tục phối hợp đúng khi phiên bản, môi trường, schema, runtime hoặc dependency thay đổi. Mục tiêu không chỉ là xác nhận chương trình vẫn chạy, mà còn bảo đảm các cam kết đã công bố về cú pháp, semantics, kiểu dữ liệu, API, artifact, dữ liệu lưu trữ và hành vi runtime được duy trì.

Ví dụ, một ứng dụng dùng DSL để mô tả rule:

~~~text
RULE discount {
  WHEN customer.level == "GOLD"
  THEN order.total * 0.15
}
~~~

Khi nâng runtime từ version 1 lên version 2, cần xác định:

- Source cũ có parse được không?
- Equality và null semantics có giữ nguyên không?
- Kiểu Decimal có còn giữ precision như trước không?
- Host function customer.level có còn signature tương thích không?
- Compiled artifact tạo từ version 1 có được version 2 nạp không?
- Plugin cũ có hoạt động với runtime mới không?
- Kết quả rule có thay đổi với cùng input không?
- Nếu có thay đổi có chủ đích, migration hoặc version declaration nào cần thiết?

Một test đơn lẻ trên phiên bản mới không đủ trả lời các câu hỏi này. Compatibility testing cần kiểm tra các cặp hoặc ma trận phiên bản, các dạng artifact và các contract giữa DSL với host application.

Trong hệ sinh thái DSL, kiểm thử tương thích thường bao gồm:
- Source compatibility: source cũ có tiếp tục hợp lệ không.
- Syntax compatibility: grammar và parsing behavior có ổn định không.
- Semantic compatibility: cùng source và input có giữ cùng ý nghĩa không.
- API compatibility: host binding, plugin và extension có còn tương thích không.
- Binary/artifact compatibility: AST, bytecode hoặc compiled module có thể được nạp không.
- Data compatibility: dữ liệu và schema cũ có được đọc đúng không.
- Runtime compatibility: behavior, performance contract và resource semantics có giữ được không.
- Environment compatibility: DSL chạy được trên runtime, OS, database hoặc backend được hỗ trợ không.

## Vì sao DSL cần kiểm thử tương thích?

DSL thường là một phần của dữ liệu và cấu hình sản phẩm. Source DSL có thể được lưu trong database, repository, workflow history hoặc do khách hàng tự quản lý. Một thay đổi runtime có thể ảnh hưởng đến hàng nghìn rule hoặc process instance đã tồn tại.

### Bảo vệ source đã được viết

Người dùng kỳ vọng một rule hợp lệ hôm nay vẫn có thể được nạp sau khi nâng cấp, trừ khi có thay đổi breaking được công bố. Compatibility test phát hiện việc thêm keyword, đổi precedence hoặc thay đổi type inference làm source cũ bị lỗi.

### Bảo vệ semantics nghiệp vụ

Một thay đổi nhỏ trong null handling, numeric conversion, timezone hoặc operator precedence có thể làm quyết định nghiệp vụ thay đổi. Source vẫn parse và chạy thành công nhưng kết quả có thể sai. Semantic compatibility cần được kiểm tra bằng input/output contract.

### Hỗ trợ nâng cấp runtime

Host application có thể nâng compiler hoặc interpreter độc lập với DSL source. Compatibility test giúp xác định phiên bản nào có thể nâng trực tiếp, phiên bản nào cần migration và artifact nào phải rebuild.

### Bảo vệ extension ecosystem

Plugin, custom function, connector và host binding thường có vòng đời phát hành riêng. Compatibility test giúp phát hiện API signature, lifecycle hook hoặc capability thay đổi làm plugin không hoạt động.

### Bảo vệ dữ liệu và workflow đang chạy

Một workflow dài có thể được tạo từ definition version cũ và tiếp tục chạy sau khi hệ thống deploy version mới. Runtime cần biết cách đọc state, event và serialized data cũ; có thể cần pin definition version hoặc migrate có kiểm soát.

### Giảm rủi ro phát hành

Compatibility regression có thể không xuất hiện trong unit test của phiên bản mới vì test chỉ dùng source mới. Bộ test với fixture từ phiên bản cũ cung cấp bằng chứng trước khi phát hành.

## Các chiều tương thích cần kiểm tra

Compatibility không phải một thuộc tính duy nhất. Một DSL có thể tương thích về cú pháp nhưng không tương thích về semantics, hoặc source tương thích nhưng plugin không tương thích.

| Chiều tương thích | Nội dung cần bảo đảm | Ví dụ regression |
|---|---|---|
| Source | Source cũ vẫn được chấp nhận | Keyword mới làm identifier cũ không parse |
| Syntax | Grammar và precedence ổn định | Biểu thức có thứ tự parse khác |
| Semantic | Kết quả và side effect giữ contract | NULL comparison đổi kết quả |
| Type | Kiểu, coercion và overload ổn định | Decimal bị chuyển thành floating point |
| API | Host function/plugin interface ổn định | Tham số đổi kiểu hoặc bị xóa |
| Artifact | Bytecode/AST/plan có thể nạp | Serialized AST không tương thích |
| Data | Schema và persisted state được đọc đúng | Field cũ bị hiểu sai |
| Runtime | Lifecycle, errors và resource behavior ổn định | Cancellation không còn được truyền |
| Backend | Cùng DSL chạy đúng trên backend hỗ trợ | SQL dialect khác semantics |
| Environment | Runtime và platform được hỗ trợ | Một JDK hoặc OS không còn hoạt động |

### Source compatibility

Source compatibility thường là cam kết quan trọng nhất với tác giả DSL. Cần xác định phạm vi: source cũ có phải chạy nguyên vẹn, hay chỉ cần có thể migrate tự động?

### Behavioral compatibility

Hai phiên bản có thể cùng parse source nhưng khác hành vi. Cần so sánh kết quả, exception, diagnostics, event, transaction và side effect theo contract.

### Compatibility theo chiều ngược và chiều xuôi

- Backward compatibility: phiên bản mới đọc hoặc chạy được input/artifact tạo bởi phiên bản cũ.
- Forward compatibility: phiên bản cũ xử lý được input/artifact từ phiên bản mới trong phạm vi đã định nghĩa.
- Cross-version compatibility: các thành phần ở phiên bản khác nhau có thể giao tiếp hoặc phối hợp.

Forward compatibility thường có giới hạn. Ví dụ, parser cũ có thể bỏ qua field metadata mới trong một format mở, nhưng không thể hiểu một syntax operator mới mà grammar cũ không biết.

## Versioning của DSL và các thành phần liên quan

Một hệ thống cần version rõ ràng cho source language và các artifact liên quan.

### Language version

Language version xác định grammar và semantics mà source được viết theo. Có thể khai báo trong file:

~~~text
LANGUAGE_VERSION "2.1"

RULE discount {
  ...
}
~~~

Hoặc metadata có thể nằm trong module manifest. Không nên suy luận language version chỉ từ ngày file được tạo hoặc version của host application.

### Runtime version

Runtime version xác định implementation cụ thể của parser, evaluator, compiler, host adapter và các thành phần hỗ trợ. Một runtime mới có thể hỗ trợ nhiều language version cũ.

### Grammar version

Grammar version hoặc fingerprint giúp cache, parser và tooling nhận diện cấu trúc cú pháp tương thích. Hai runtime cùng khai báo language version nhưng grammar implementation khác nhau vẫn có thể có bug hoặc behavior khác.

### Schema version

DSL có thể tham chiếu domain schema, type catalog hoặc host API schema. Schema version cần được quản lý riêng vì source syntax có thể ổn định trong khi field hoặc type của host thay đổi.

### Artifact format version

AST serialized, bytecode, compiled module hoặc execution plan cần format version. Không nên coi format artifact tự động giống language version.

### Plugin/API version

Extension API có thể có version độc lập. Plugin manifest nên khai báo khoảng runtime/API tương thích.

### Compatibility matrix

Một bảng hỗ trợ có thể mô tả:

| DSL language | Runtime | Host API | Plugin API | Trạng thái |
|---|---|---|---|---|
| 1.x | Runtime 2.x | Host API 1.x | Plugin API 1.x | Supported |
| 2.x | Runtime 2.x | Host API 2.x | Plugin API 2.x | Supported |
| 1.x | Runtime 3.x | Host API 2.x | Plugin API 1.x | Legacy support |
| 2.x | Runtime 1.x | Host API 1.x | Plugin API 2.x | Unsupported |

Các giá trị chỉ minh họa. Ma trận thực tế cần được công bố, kiểm thử và cập nhật theo release policy.

## Semantic versioning và compatibility policy

Semantic Versioning (SemVer) thường dùng dạng MAJOR.MINOR.PATCH:

- MAJOR: thay đổi không tương thích theo contract đã công bố.
- MINOR: bổ sung chức năng tương thích ngược.
- PATCH: sửa lỗi tương thích với behavior đã công bố.

Với DSL, cần xác định version nào đang được áp dụng: language, runtime, host API, plugin API hay artifact format.

### Khi nào là breaking change?

Ví dụ:
- Xóa operator hoặc keyword đã được hỗ trợ.
- Đổi precedence làm biểu thức cũ có kết quả khác.
- Thay null semantics.
- Thay kiểu trả về của host function.
- Đổi cách tính numeric precision.
- Bỏ một serialized artifact format.
- Thay đổi event schema theo cách consumer cũ không đọc được.
- Siết validation khiến source hợp lệ trước đây bị từ chối.

Không phải mọi thay đổi implementation đều là breaking change. Tối ưu parser nhưng giữ grammar và semantics có thể là patch/minor tùy policy.

### Bug fix và behavioral compatibility

Một số phiên bản cũ có bug khiến kết quả thực tế khác với đặc tả. Sửa bug có thể làm behavior thay đổi đối với người dùng đang phụ thuộc vào bug đó.

Release notes nên phân biệt:
- Behavior được đặc tả và giữ tương thích.
- Behavior cũ là bug và được sửa.
- Thay đổi cần migration.
- Thay đổi chỉ áp dụng khi bật language feature mới.

### Deprecation policy

Một API hoặc syntax có thể được đánh dấu deprecated trước khi bị loại bỏ. Policy nên quy định:
- Phiên bản bắt đầu cảnh báo.
- Thời gian hỗ trợ.
- Tool migration.
- Version sớm nhất được phép xóa.
- Cách xử lý source cũ.
- Diagnostics và telemetry để đánh giá mức sử dụng.

Deprecation cần có lộ trình rõ để người dùng không bị bất ngờ.

## Kiểm thử backward compatibility của source

Backward source compatibility xác nhận source hợp lệ từ phiên bản trước vẫn được parser/compiler mới chấp nhận theo cam kết.

### Golden source corpus

Có thể duy trì một tập source DSL đại diện cho các version đã phát hành:

~~~text
compatibility/
  language-v1/
    basic-rule.dsl
    nested-expression.dsl
    imports.dsl
    workflow.dsl
  language-v2/
    typed-query.dsl
    new-patterns.dsl
~~~

Mỗi fixture cần có metadata language version và mục tiêu kiểm tra. Corpus nên bao gồm:
- Syntax cơ bản.
- Biểu thức lồng nhau.
- Module/import.
- Function overload.
- Generic hoặc collection.
- Error recovery.
- Comment và encoding.
- Boundary cases của grammar.
- Construct deprecated.
- Construct có feature flag.

### Parse với runtime mới

Chạy parser của runtime mới trên source cũ theo language version được khai báo. Xác nhận:
- Parse success hoặc diagnostics đúng theo contract.
- AST shape phù hợp.
- Source span không bị lệch.
- Identifier cũ không bị diễn giải thành keyword mới ngoài policy.
- Import và module resolution vẫn đúng.

### Snapshot AST

Có thể serialize một representation ổn định của AST hoặc canonical tree để so sánh. Snapshot cần bỏ các field không ổn định như memory address hoặc internal ID ngẫu nhiên.

AST snapshot hữu ích để phát hiện grammar drift, nhưng không thay thế behavioral test. Hai AST khác cấu trúc vẫn có thể có semantics tương đương nếu implementation thay representation có chủ đích.

### Parser differential test

Chạy cùng source trên parser cũ và parser mới, sau đó so sánh:
- Parse outcome.
- Diagnostics.
- Canonical AST.
- Source mapping.
- Language feature flags.

Nếu khác biệt được dự kiến, test cần có expectation và migration note tương ứng.

## Kiểm thử semantic compatibility

Semantic compatibility kiểm tra cùng source và cùng input có tạo kết quả tương đương theo contract hay không.

### Reference behavior

Có thể lưu bộ input/output chuẩn cho các DSL construct quan trọng:

~~~text
Input:
  customer.level = "GOLD"
  order.total = 1000

DSL:
  discount = order.total * 0.15

Expected:
  discount = Decimal("150.00")
~~~

Khi nâng runtime, chạy lại fixture và so sánh output. Cần định nghĩa equality theo type system: Decimal precision, timestamp zone, collection ordering và duplicate semantics.

### Side effect contract

Với DSL có action, kiểm tra:
- Số lần gọi host function.
- Event được phát.
- Database mutation.
- Transaction commit/rollback.
- Retry và idempotency.
- Authorization decision.
- Compensation.

Chỉ so sánh final return value có thể bỏ sót side effect thay đổi.

### Error compatibility

Một phiên bản mới có thể thay đổi exception type hoặc diagnostic code. Cần xác định contract có cam kết error code, category, source location hay message.

Thông thường, error code và category ổn định hơn message text. Test nên ưu tiên những field thuộc public contract.

### Null, numeric và time semantics

Các trường hợp thường gây regression:
- NULL trong comparison, IN và NOT.
- Decimal scale và rounding.
- Integer overflow.
- Floating-point associativity.
- String collation.
- Unicode normalization.
- Timezone và daylight saving.
- Date boundary.
- Empty collection.
- Missing field và default.

Cần có fixture chuyên biệt cho từng nhóm semantics.

## Kiểm thử API compatibility giữa DSL và host

DSL thường gọi function, action hoặc service do host đăng ký. Thay đổi host API có thể phá source DSL hoặc làm runtime binding sai.

### Function signature

Một function contract có thể gồm:

~~~text
FunctionContract
  name
  parameterNames
  parameterTypes
  optionalParameters
  returnType
  nullability
  purity
  sideEffectClass
  requiredPermissions
  errorContract
~~~

Thay đổi tên tham số, overload resolution, return type hoặc nullability có thể là breaking change tùy cách DSL resolve function.

### Additive change

Thêm function mới thường tương thích nếu không gây overload ambiguity hoặc chiếm identifier đã được người dùng dùng theo cách khác. Thêm overload có thể làm call cũ resolve sang signature khác, nên vẫn cần compatibility test.

### Removing or changing a function

Nếu function bị xóa hoặc đổi signature:
- Compiler cần báo diagnostics rõ.
- Có thể giữ deprecated overload trong thời gian chuyển đổi.
- Migration tool có thể rewrite call.
- Runtime mới cần xác định có hỗ trợ source version cũ không.

### Host binding behavior

Không chỉ signature mà behavior cũng là contract:
- Error mapping.
- Transaction participation.
- Timeout.
- Cancellation.
- Idempotency.
- Authorization.
- Side effect.
- Determinism.
- Thread safety.

Một function giữ nguyên tên và kiểu nhưng đổi từ pure sang side-effecting có thể phá optimizer hoặc cache semantics.

### Contract test

Host adapter có thể có bộ contract test dùng chung để xác nhận implementation tuân thủ:
- Input validation.
- Output schema.
- Error category.
- Null handling.
- Permission enforcement.
- Transaction propagation.
- Retry semantics.

## Kiểm thử plugin và extension compatibility

Plugin có thể được phát triển và phát hành độc lập với DSL runtime. Cần kiểm tra cả binary compatibility và behavior.

### Plugin manifest

Manifest có thể khai báo:

~~~text
PLUGIN inventory-connector {
  VERSION "3.2"
  DSL_RUNTIME ">=2.0 <4.0"
  HOST_API ">=2.1 <3.0"
  PROVIDES {
    FUNCTION inventory.available
    ACTION inventory.reserve
  }
}
~~~

Runtime cần kiểm tra version range trước khi load plugin. Không nên chỉ dựa vào package name hoặc file tồn tại.

### Extension API compatibility

Thay đổi có thể ảnh hưởng:
- Interface method.
- Constructor hoặc factory.
- Lifecycle callback.
- Event type.
- Context object.
- Classloader behavior.
- Threading model.
- Permission manifest.
- Serialization contract.

### Binary compatibility

Nếu plugin được biên dịch thành bytecode hoặc binary artifact, cần kiểm tra ABI/API compatibility theo runtime và compiler target. Một plugin compile thành công nhưng load thất bại do method signature hoặc dependency version không tương thích vẫn là lỗi.

### Plugin compatibility matrix

Có thể chạy plugin test với:
- Runtime version tối thiểu được hỗ trợ.
- Runtime version mới nhất.
- Host API version thấp nhất và cao nhất.
- Các dependency version được công bố.
- Platform hoặc architecture cần hỗ trợ.

### Unknown extension node

Nếu AST hoặc serialized artifact chứa node do plugin định nghĩa, runtime không có plugin tương ứng phải báo lỗi rõ hoặc dùng compatibility fallback đã đặc tả. Không nên bỏ qua node một cách âm thầm nếu nó ảnh hưởng semantics.

## Kiểm thử binary và compiled artifact compatibility

Nhiều DSL không chỉ lưu source mà còn lưu AST, bytecode, query plan, workflow definition hoặc compiled artifact để giảm startup cost.

### Artifact metadata

Một artifact có thể chứa:
- Language version.
- Runtime/compiler version.
- Artifact format version.
- Grammar fingerprint.
- Host API fingerprint.
- Dependency versions.
- Target platform.
- Content digest.
- Build metadata.

Khi nạp artifact, runtime cần kiểm tra compatibility trước khi deserialize hoặc execute.

### Producer-consumer matrix

Cần kiểm tra các cặp:
- Artifact tạo bởi compiler cũ, runtime mới.
- Artifact tạo bởi compiler mới, runtime cũ.
- Artifact tạo trên platform A, chạy trên platform B nếu được hỗ trợ.
- Artifact có dependency plugin khác version.
- Artifact được tạo với feature flag khác.
- Artifact bị truncate hoặc corrupt.

### Rebuild và migration

Nếu artifact format không tương thích, có thể:
- Rebuild từ source.
- Migrate serialized representation.
- Chạy compatibility adapter.
- Từ chối load với diagnostic và yêu cầu redeploy.

Không nên deserialize một artifact không tương thích rồi tiếp tục thực thi với assumption rằng field thiếu sẽ tự có default đúng.

### Cache compatibility

Parse cache, AST cache và compiled plan cache cần version namespace riêng. Khi parser hoặc compiler thay đổi, cache cũ có thể cần invalidation. Cache là dữ liệu có thể tái tạo, không phải nguồn chính thức của chương trình.

## Kiểm thử data và schema compatibility

DSL có thể lưu persisted data, workflow state, query schema hoặc serialized object. Schema evolution cần được kiểm tra độc lập với source compatibility.

### Additive schema change

Thêm field optional có thể tương thích nếu reader cũ bỏ qua unknown field và writer mới cung cấp default phù hợp. Nhưng điều này phụ thuộc serialization format và contract.

### Removing or renaming fields

Xóa hoặc đổi tên field có thể làm source cũ, stored workflow hoặc plugin không resolve được property. Cần alias, migration hoặc versioned schema.

### Type evolution

Đổi Integer sang Decimal hoặc String sang Enum có thể ảnh hưởng conversion, validation và query. Không nên giả định mọi type widening đều tương thích; semantics và serialization cần được kiểm tra.

### Unknown fields

Reader có thể:
- Reject unknown fields.
- Ignore unknown fields.
- Preserve unknown fields khi round-trip.
- Lưu chúng trong extension map.

Chính sách cần rõ. Ignore field có thể làm mất dữ liệu khi một component cũ đọc rồi ghi lại object mới.

### Persisted workflow state

Workflow instance có thể lưu state name, variable schema, pending timer, task ID và event history. Version mới cần đọc được state cũ hoặc có migration script. Test cần tạo instance bằng version trước, lưu, rồi load bằng version mới.

### Migration test

Chạy migration trên bản sao fixture từ release cũ và xác nhận:
- Data không bị mất.
- Invariant vẫn đúng.
- Reference được cập nhật.
- Rollback migration hoặc recovery plan được xác định.
- Process đang chạy có thể tiếp tục.

## Kiểm thử runtime và môi trường

DSL có thể phụ thuộc runtime host, operating system, architecture, database, timezone, locale và backend.

### Runtime compatibility

Kiểm tra các runtime version được hỗ trợ:
- JDK hoặc CLR version.
- Garbage collector behavior nếu ảnh hưởng resource contract.
- Reflection hoặc classloading.
- Threading và async runtime.
- Serialization library.
- Native dependency.

### Operating system và architecture

Một DSL có host action gọi executable hoặc file API có thể hoạt động khác trên Windows, Linux và macOS. Kiểm tra path separator, case sensitivity, file permissions, line endings, process handling và native library.

### Database và backend

Nếu DSL query được compile sang SQL hoặc backend-specific operation, cần kiểm tra:
- SQL dialect.
- Type mapping.
- Collation.
- NULL behavior.
- Transaction isolation.
- Date/time functions.
- JSON/array support.
- Index capability.
- Error mapping.

### Locale và timezone

Không nên để semantics của DSL phụ thuộc locale của máy một cách ngầm định. Nếu DSL có format/parse date hoặc string comparison, test cần chạy với locale/timezone được hỗ trợ và xác nhận behavior.

### Container và deployment environment

Nếu DSL chạy trong container, kiểm tra runtime image, permissions, filesystem mount, environment variables, network policy và resource limits. Một image mới có thể thay đổi JDK, locale hoặc shared library mà không thay đổi source DSL.

## Kiểm thử tương thích giữa nhiều phiên bản cùng lúc

Trong quá trình rollout, producer và consumer có thể chạy version khác nhau. Ví dụ host service mới gửi event mà worker cũ vẫn đang xử lý.

### Rolling upgrade

Một deployment thường không thay tất cả instance cùng một lúc. Cần kiểm tra:
- Runtime cũ và mới cùng đọc source hoặc message schema.
- Event được gửi trong thời gian rollout.
- Cache namespace không trộn artifact.
- Persisted state được đọc bởi cả version cần hỗ trợ.
- Rollback về version cũ có thể thực hiện không.

### N-1 và N-2 compatibility

Một policy phổ biến là runtime mới hỗ trợ source hoặc artifact của một số major/minor version gần trước đó. Phạm vi N-1/N-2 phải được công bố rõ.

### Mixed-version host

Nếu host application và DSL runtime được nâng độc lập, cần kiểm tra ma trận host/runtime:
- Host mới với runtime cũ.
- Host cũ với runtime mới.
- Plugin cũ với host mới.
- Worker mới với event từ producer cũ.
- Worker cũ với event từ producer mới.

Không phải mọi tổ hợp đều phải được hỗ trợ. Unsupported combination cần bị phát hiện sớm bằng startup validation hoặc deployment gate.

### Rollback compatibility

Nâng cấp thành công nhưng rollback thất bại là rủi ro thường bị bỏ qua. Nếu version mới ghi format dữ liệu mà version cũ không đọc được, rollback application có thể không phục hồi service.

Có thể dùng expand-and-contract migration:
1. Mở rộng schema để cả version cũ và mới đọc được.
2. Deploy version mới.
3. Chuyển traffic và migrate data.
4. Chỉ xóa field cũ sau khi version cũ không còn chạy và rollback window đã kết thúc.

## Conformance suite và reference implementation

Một cách mạnh để kiểm tra tương thích là duy trì conformance suite mô tả behavior bắt buộc của DSL.

### Language conformance tests

Mỗi test có thể gồm:
- Source DSL.
- Language version.
- Expected parse result.
- Expected diagnostics.
- Expected evaluation result.
- Expected error category.
- Feature flags.
- Runtime requirements.

Các implementation hoặc runtime version phải chạy cùng suite để xác nhận tuân thủ.

### Reference interpreter

Một reference interpreter đơn giản có thể đóng vai trò oracle cho semantics. Optimized runtime hoặc backend-specific compiler chạy cùng input và so sánh kết quả.

Reference implementation nên ưu tiên tính rõ ràng và đúng semantics, không nhất thiết tối ưu hiệu năng.

### Test vector

Test vector có thể bao phủ:
- Operator precedence.
- Numeric boundary.
- Null semantics.
- Type coercion.
- Function overload.
- Collection behavior.
- Date/time.
- Error handling.
- Side effect contract.
- Serialization.

### Conformance report

Report cần ghi:
- Implementation/version.
- Test suite version.
- Supported language features.
- Passed/failed/skipped.
- Known deviations.
- Platform.
- Host API version.

Không nên chỉ ghi một nhãn compliant nếu còn feature chưa được kiểm tra.

## Differential testing và cross-version testing

Differential testing chạy cùng chương trình trên nhiều implementation hoặc version rồi so sánh kết quả.

### Cross-version execution

Với source và input cố định:
1. Chạy trên runtime cũ.
2. Chạy trên runtime mới.
3. Thu result, diagnostics và side effect.
4. Chuẩn hóa các giá trị không ổn định.
5. So sánh theo contract.
6. Phân loại khác biệt.

Không nên so sánh raw serialized output nếu thứ tự map hoặc internal IDs không được bảo đảm.

### Differential testing giữa backend

Một DSL có thể chạy trên in-memory interpreter và SQL backend. Chạy cùng query trên hai backend với cùng dataset giúp phát hiện khác biệt về null, collation, numeric precision và ordering.

### Metamorphic testing

Khi không có expected output dễ viết, có thể kiểm tra quan hệ phải giữ:
- Parse rồi pretty-print rồi parse lại cho canonical AST tương đương.
- Chạy cùng pure expression nhiều lần với context giống nhau cho cùng result.
- Migration giữ invariant.
- Source không đổi với cùng parser config tạo cùng canonical AST.
- Hai backend trả cùng kết quả theo semantics DSL.

### Fuzzing grammar và serialization

Fuzzing source DSL hoặc serialized artifact có thể phát hiện parser crash, deserialization bug và behavior không ổn định. Fuzz input cần chạy trong sandbox, giới hạn resource và lưu seed để tái hiện lỗi.

## Kiểm thử deprecation và migration

Thay đổi không tương thích cần có quy trình chuyển đổi.

### Deprecation warning

Compiler hoặc language server có thể phát warning khi source dùng syntax/API sắp bị loại bỏ. Warning nên có:
- Mã ổn định.
- Version bắt đầu deprecated.
- Version dự kiến removal nếu đã công bố.
- Replacement được đề xuất.
- Source span.

### Migration tool

Migration tool có thể chuyển:
- Keyword cũ sang keyword mới.
- Function call cũ sang API mới.
- Type alias sang type chuẩn.
- Field cũ sang schema mới.
- Configuration option cũ sang option mới.

Migration cần idempotent hoặc có version marker để tránh áp dụng nhiều lần làm hỏng source.

### Migration correctness

Test nên xác nhận:
- Source cũ được transform.
- Source mới parse được.
- Semantics tương đương trong phạm vi đã cam kết.
- Comment và formatting được giữ nếu tool yêu cầu.
- Diagnostic chỉ ra construct không thể tự động migrate.
- File không bị ghi một phần khi migration thất bại.

### Dual support window

Có thể hỗ trợ cả syntax cũ và mới trong một khoảng thời gian. Cần quy định syntax cũ được parse, warning hay bị reject trong từng language version.

### Removal test

Khi bỏ feature, test version mới phải xác nhận:
- Source version cũ được xử lý theo policy.
- Diagnostics đúng.
- Migration path hoạt động.
- Không còn implicit fallback làm behavior khó đoán.

## Golden tests, snapshot và contract fixtures

Golden test lưu kết quả kỳ vọng để phát hiện thay đổi giữa phiên bản.

### Golden source và AST

Có thể lưu source, canonical AST và diagnostics. Snapshot cần loại bỏ thông tin không ổn định như timestamp hoặc random node ID.

### Golden execution result

Lưu input, result, error category và side effect record. Với dữ liệu thời gian hoặc random, inject clock/random source để test xác định.

### Golden plan

Với DSL query hoặc workflow, có thể lưu logical/physical plan hoặc state graph. Snapshot nên tập trung vào contract quan trọng thay vì mọi internal detail, nếu không một refactor implementation vô hại sẽ tạo quá nhiều thay đổi.

### Snapshot update review

Khi golden file thay đổi, reviewer cần biết thay đổi là:
- Cải thiện representation không đổi semantics.
- Thay đổi behavior có chủ đích.
- Regression.
- Test fixture được cập nhật sai.

Không nên tự động chấp nhận mọi snapshot mới chỉ để làm test pass.

## Kiểm thử performance compatibility

Compatibility cũng có thể bao gồm performance contract, nhất là DSL chạy trong request path hoặc xử lý workload lớn.

### Performance regression

Một runtime mới có thể giữ đúng result nhưng parse chậm hơn nhiều, tăng memory hoặc tạo nhiều query hơn.

Có thể theo dõi:
- Parse/compile latency.
- Evaluation latency.
- Allocation và retained heap.
- Cache hit ratio.
- Query count.
- Number of host calls.
- Workflow step duration.
- Throughput và tail latency.

### Benchmark corpus

Dùng corpus đại diện:
- Source nhỏ và lớn.
- Module có nhiều import.
- Expression sâu.
- Query nhiều join.
- Workflow nhiều transition.
- Plugin nhiều extension.
- Concurrent execution.
- Cold cache và warm cache.

### Không dùng ngưỡng quá nhạy

Benchmark CI có thể dao động theo máy và tải. Nên chạy trên môi trường kiểm soát, dùng nhiều lần đo và so sánh phân phối. Smoke test có thể kiểm tra giới hạn rộng, còn benchmark chuyên sâu chạy riêng.

### Resource compatibility

Nếu version mới dùng memory hoặc thread nhiều hơn, nó có thể không phù hợp với môi trường host cũ. Cần kiểm tra CPU, memory, file handles, network calls và cancellation behavior.

## Compatibility testing cho DSL có Language Server

Language server cung cấp parser, diagnostics, completion, hover, navigation và refactoring cho editor. Nó cần tương thích với cả language version lẫn LSP client.

### Editor và protocol version

Kiểm tra:
- Client capability negotiation.
- LSP protocol version được hỗ trợ.
- didOpen/didChange document version.
- Completion item capability.
- Diagnostic format.
- Semantic tokens.
- Cancellation.
- Workspace folder handling.
- Dynamic registration.

### Language version awareness

Language server cần parse source theo language version khai báo trong project hoặc file. Nếu server mới tự động dùng grammar mới cho source cũ, diagnostics có thể khác compiler thực thi.

### Shared parser behavior

Nếu compiler và language server dùng parser khác nhau hoặc config khác nhau, source có thể được editor chấp nhận nhưng runtime từ chối. Compatibility suite nên dùng chung corpus cho cả hai.

### Cache và index version

AST cache, symbol index và compiled artifact cần version namespace. Khi language server update, cache cũ phải được invalidation hoặc migrate.

### Editor compatibility matrix

Có thể kiểm tra một số client và version được hỗ trợ, nhưng cần phân biệt protocol conformance với UI behavior riêng của editor.

## Compatibility testing trong CI/CD và release process

Compatibility suite cần được chạy như một phần của release gate.

Một pipeline minh họa:

~~~text
Build candidate runtime
        |
        v
Run unit and semantic tests
        |
        v
Run previous-version source corpus
        |
        v
Run API and plugin compatibility matrix
        |
        v
Run artifact and data migration tests
        |
        v
Run cross-backend / environment tests
        |
        v
Run performance regression suite
        |
        v
Generate compatibility report
        |
        v
Release approval
~~~

### Version matrix automation

CI có thể build nhiều runtime hoặc host version và chạy cùng fixtures. Cần pin toolchain, dependency và container image để kết quả tái lập.

### Compatibility gate

Release gate có thể yêu cầu:
- Không có unexpected source parse regression.
- Không có semantic difference ngoài allowlist.
- Plugin API contract pass.
- Artifact migration pass.
- Supported runtime matrix pass.
- Performance regression nằm trong giới hạn.
- Deprecation warning và migration guide đã cập nhật.

### Release candidate

Chạy suite trên release candidate trước khi publish. Có thể dùng canary hoặc shadow execution để so sánh behavior trên workload không tạo side effect.

### Shadow execution

Cùng input có thể được đánh giá trên runtime cũ và mới trong chế độ không commit side effect. So sánh kết quả giúp phát hiện behavior drift. Cần đảm bảo shadow runtime không gọi external action thật hoặc làm lộ dữ liệu.

### Rollout và rollback

Theo dõi metrics sau rollout:
- Parse failure.
- Runtime exception.
- Semantic decision drift.
- Plugin load failure.
- Artifact load failure.
- Latency và memory.
- Migration error.

Rollback plan cần tính đến data format và persisted state đã được version mới ghi.

## Quản lý compatibility contract và tài liệu

Compatibility chỉ kiểm thử được khi contract được mô tả.

Một compatibility contract có thể ghi:
- Language version.
- Runtime version range.
- Host API version range.
- Plugin API range.
- Artifact format versions.
- Supported platforms.
- Deprecated features.
- Breaking changes.
- Migration requirements.
- Error/diagnostic guarantees.
- Performance expectations nếu có.

### Public và internal API

Không phải mọi internal class hoặc AST node đều là public contract. Nếu người dùng plugin được phép truy cập một type, nó có thể trở thành API cần versioning. Cần phân loại rõ public, experimental và internal.

### Experimental feature

Feature thử nghiệm có thể thay đổi nhanh hơn nhưng phải được đánh dấu và có policy. Không nên vô tình để feature experimental được xem là cam kết ổn định.

### Compatibility notes

Release notes nên mô tả:
- Những gì vẫn tương thích.
- Những gì deprecated.
- Những gì thay đổi behavior.
- Những gì cần rebuild/migrate.
- Các tổ hợp version không còn hỗ trợ.
- Cách chạy compatibility checker.

### Support window

Nêu rõ thời gian hỗ trợ version cũ và chính sách security update. Không nên để người dùng suy đoán một runtime cũ được hỗ trợ vô thời hạn.

## Những lỗi thường gặp khi kiểm thử tương thích

### Chỉ kiểm tra compile success

Source có thể compile nhưng runtime behavior thay đổi. Cần semantic fixtures và side effect contract.

### Chỉ dùng source mới

Test chỉ viết theo grammar mới không phát hiện source cũ bị phá. Cần corpus từ các release trước.

### So sánh output không chuẩn hóa

Timestamp, map order hoặc generated ID có thể khác dù semantics tương đương. Chuẩn hóa các phần không thuộc contract trước khi so sánh.

### Không kiểm tra plugin/API

Host binding và extension có thể là nơi dễ bị breaking change. Cần contract suite và version matrix.

### Bỏ qua persisted artifact và state

Source compatibility không đảm bảo serialized AST, bytecode hoặc workflow instance cũ có thể được nạp. Cần test artifact và data migration.

### Không test mixed-version deployment

Rolling upgrade tạo thời gian các producer/consumer khác version cùng hoạt động. Cần test compatibility trong thời gian chuyển đổi.

### Chấp nhận mọi golden snapshot mới

Snapshot mới có thể chứa regression. Cần review khác biệt và xác định semantics có thay đổi có chủ đích không.

### Không kiểm tra rollback

Runtime mới có thể ghi data mà runtime cũ không đọc được. Migration cần hỗ trợ rollback window hoặc kế hoạch phục hồi.

### Không version cache

AST hoặc compiled cache từ parser/compiler cũ có thể bị dùng sai. Cache key cần bao gồm format và toolchain fingerprint.

### Không định nghĩa deprecation window

Người dùng không có thời gian chuyển đổi và feature bị xóa đột ngột. Cần warning, migration tool và lịch removal rõ.

### Chỉ test một môi trường

Khác biệt OS, runtime, database và locale có thể làm behavior thay đổi. Cần matrix phù hợp với support policy.

## Quy trình xây dựng bộ kiểm thử tương thích cho DSL

Một quy trình có thể đi theo các bước:

1. **Lập compatibility contract:** xác định cam kết về source, syntax, semantics, API, artifact, data và runtime.
2. **Version hóa các thành phần:** language, grammar, runtime, host API, plugin API và artifact format.
3. **Thu thập fixture lịch sử:** source, input/output, diagnostics, plugin và persisted data từ các release được hỗ trợ.
4. **Xây conformance suite:** test syntax, type, null, numeric, error, side effect và host binding.
5. **Kiểm tra backward compatibility:** chạy source/artifact cũ trên candidate runtime.
6. **Kiểm tra forward và mixed-version:** chỉ trong các tổ hợp được công bố.
7. **Kiểm tra API/plugin:** signature, behavior, lifecycle và permission contract.
8. **Kiểm tra schema và migration:** data cũ, workflow state, serialized artifact và rollback.
9. **Chạy differential test:** so sánh runtime cũ/mới và backend khác nhau.
10. **Chạy performance compatibility:** benchmark parse, evaluation, memory và throughput.
11. **Tự động hóa matrix CI:** pin environment và tạo compatibility report.
12. **Quản lý deprecation:** warning, migration tool, support window và removal test.
13. **Kiểm soát release:** gate, canary, shadow execution và rollback plan.
14. **Duy trì contract:** cập nhật tài liệu, fixtures và version matrix sau mỗi release.

Mỗi compatibility test nên ghi rõ cặp version đang được kiểm tra, contract nào được xác nhận, dữ liệu đầu vào và lý do khác biệt được chấp nhận. Điều đó giúp test suite trở thành bằng chứng có thể đọc và tái lập, thay vì chỉ là một tập lệnh chạy qua CI.

## Kết luận

Kiểm thử tương thích bảo đảm DSL tiếp tục hoạt động theo các contract đã công bố khi language, runtime, host API, plugin, artifact, schema hoặc môi trường thay đổi. Nó cần kiểm tra nhiều chiều: source và syntax, semantics và type, API và extension, serialized artifact và persisted data, runtime và backend, cũng như các deployment có nhiều version cùng tồn tại.

Một bộ kiểm thử có giá trị kết hợp source corpus lịch sử, conformance suite, semantic fixtures, API contract tests, artifact migration tests, differential testing và performance regression tests. Versioning, deprecation, migration và compatibility matrix cần được xác định trước để người dùng biết tổ hợp nào được hỗ trợ và thay đổi nào cần hành động.

Compatibility testing nên chạy tự động trong CI và được dùng làm release gate. Khi kết hợp kiểm tra mixed-version deployment, shadow execution, canary và rollback planning, nhóm phát triển có thể nâng cấp DSL có kiểm soát mà vẫn bảo vệ source, dữ liệu và hành vi nghiệp vụ đang được sử dụng.
